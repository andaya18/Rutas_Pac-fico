"""Sistema web de gestión integral - Cooperativa de Transporte Interprovincial Rutas del Pacífico.

Flask + SQLite. Ejecutar:  python app.py       (reiniciar datos de demo:  python app.py --reset)
"""
import csv
import io
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import database as dbm
from config import (CAT_NOMBRES, FK_LABEL, LABELS_ROL, MODULES, NAV, PERMS, PILL, ROLES, SCOPES, VIAJE_LIBRE)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "rutas_pacifico.db")
UPLOADS = os.path.join(BASE, "uploads")
PER_PAGE = 10
MAX_INTENTOS_EVAL = 3

app = Flask(__name__)
os.makedirs(UPLOADS, exist_ok=True)
_key = os.path.join(BASE, ".secret_key")
if not os.path.exists(_key):
    with open(_key, "w") as fh:
        fh.write(secrets.token_hex(32))
app.secret_key = open(_key).read().strip()
app.config.update(MAX_CONTENT_LENGTH=6 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=8))

VIG = ("CASE WHEN fecha_vencimiento IS NULL OR fecha_vencimiento='' THEN 'Sin vencimiento' "
       "WHEN fecha_vencimiento<'{hoy}' THEN 'Vencido' WHEN fecha_vencimiento<='{hoy30}' THEN 'Próximo a vencer' ELSE 'Vigente' END")


# ============================================================ utilidades base
def get_db():
    if "db" not in g:
        g.db = dbm.connect(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


def q(sql, params=()):
    return get_db().execute(sql, list(params)).fetchall()


def q1(sql, params=()):
    r = get_db().execute(sql, list(params)).fetchone()
    return r[0] if r is not None and len(r) == 1 else r


def fechas():
    h = date.today()
    return {"hoy": h.isoformat(), "hoy15": (h + timedelta(days=15)).isoformat(), "hoy30": (h + timedelta(days=30)).isoformat()}


def fmt(sql, **extra):
    """Sustituye marcadores {hoy}, {hoy30}, {vig}, etc. en SQL de configuración."""
    ctx = fechas()
    ctx["solo_confirmados"] = "AND estado IN ('Confirmado','Cerrado')" if getattr(g, "user", None) and g.user["rol"] == "conductor" else ""
    ctx.update(extra)
    sql = sql.replace("{vig}", VIG)
    for k, v in ctx.items():
        sql = sql.replace("{" + k + "}", v)
    return sql


def fdate(v):
    if not v:
        return "—"
    try:
        return datetime.strptime(v[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return v


def fdt(v):
    if not v:
        return "—"
    try:
        return datetime.strptime(v[:16].replace("T", " "), "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return v


def pill_class(v):
    for k, lst in PILL.items():
        if v in lst:
            return k
    return "off"


def pill(v):
    if v in (None, ""):
        return Markup('<span class="muted" title="No disponible">—</span>')
    return Markup(f'<span class="pill p-{pill_class(v)}">{escape(v)}</span>')


def mask_id(v):
    if not v:
        return "—"
    return "•" * max(len(v) - 3, 3) + v[-3:]


def render_cell(row, col):
    """Devuelve el HTML (seguro) de una celda según su tipo."""
    key, kind = col[0], col[2]
    r = row
    val = r[key] if key in r.keys() else None
    if kind == "pill":
        return pill(val)
    if kind == "bold":
        return Markup(f'<span class="code">{escape(val if val else "—")}</span>')
    if kind == "date":
        return Markup(escape(fdate(val)))
    if kind == "dt":
        return Markup(escape(fdt(val)))
    if kind == "fk":
        lab = r[key + "__l"] if (key + "__l") in r.keys() else None
        return Markup(escape(lab)) if lab else Markup('<span class="muted" title="No asignado">—</span>')
    if kind == "mask":
        full = g.user["rol"] in ("admin", "administrativo")
        return Markup(escape(val if (full and val) else mask_id(val)))
    if kind == "two":
        sub = r[col[3]] if len(col) > 3 and col[3] in r.keys() else None
        s = f'<span class="sub">{escape(sub)}</span>' if sub else ""
        return Markup(f'<span class="main">{escape(val if val else "—")}</span>{s}')
    if kind in ("date_warn", "date_warn_mt"):
        if not val:
            return Markup('<span class="muted" title="No disponible">—</span>')
        h = fechas()
        extra = ""
        cerrado = "estado" in r.keys() and r["estado"] in ("Finalizado", "Cancelado")
        if not cerrado:
            if val < h["hoy"]:
                extra = ' <span class="pill p-bad">' + ("Vencida" if kind == "date_warn" else "Atrasado") + "</span>"
            elif val <= h["hoy30"] and kind == "date_warn":
                extra = ' <span class="pill p-warn">Por vencer</span>'
            elif val <= h["hoy15"]:
                extra = ' <span class="pill p-warn">Próximo</span>'
        return Markup(escape(fdate(val)) + extra)
    if kind == "role":
        return Markup(escape(ROLES.get(val, val)))
    if kind == "catname":
        return Markup(escape(CAT_NOMBRES.get(val, val)))
    if val is None:
        return Markup('<span class="muted" title="No disponible">—</span>')
    return Markup(escape(val))


app.jinja_env.filters["cell"] = render_cell
app.jinja_env.filters["fdate"] = fdate
app.jinja_env.filters["fdt"] = fdt
app.jinja_env.filters["pill"] = pill


# ============================================================ sesión y seguridad
@app.before_request
def antes():
    g.user = None
    uid = session.get("uid")
    if uid:
        g.user = get_db().execute("SELECT * FROM usuarios WHERE id=? AND estado='Activo'", (uid,)).fetchone()
        if not g.user:
            session.clear()
    if request.endpoint in ("login", "static", "login_demo") or request.endpoint is None:
        pass
    elif not g.user:
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify(ok=False, message="Tu sesión expiró. Inicia sesión de nuevo."), 401
        return redirect(url_for("login", next=request.path))
    if request.method == "POST":
        tok = request.headers.get("X-CSRF-Token") or request.form.get("csrf")
        if not tok or tok != session.get("csrf"):
            return jsonify(ok=False, message="La sesión de seguridad expiró. Recarga la página."), 400


@app.after_request
def cabeceras(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self'; frame-ancestors 'none'"
    return resp


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def level(mod):
    if not g.user:
        return None
    p = PERMS.get(mod, {})
    rol = g.user["rol"]
    if rol in p.get("w", []):
        return "w"
    if rol in p.get("r", []):
        return "r"
    if rol in p.get("c", []):
        return "c"
    return None


def can_create(mod):
    return level(mod) == "w" or (g.user and g.user["rol"] in PERMS.get(mod, {}).get("c", []))


def need(mod, write=False):
    lv = level(mod)
    if not lv or (write and lv != "w"):
        abort(403)
    return MODULES[mod]


def scope(mod):
    key = (mod, g.user["rol"])
    if key not in SCOPES:
        return "1=1", []
    sql, fld = SCOPES[key]
    n = 2 if fld.endswith("2") else 1
    fld = fld.rstrip("2")
    val = g.user[fld]
    if val is None:
        return "0=1", []
    return sql, [val] * n


def audit(accion, modulo, registro=None, resumen="", resultado="Correcto", motivo=None):
    get_db().execute("INSERT INTO auditoria(fecha,usuario,accion,modulo,registro,resumen,resultado,motivo) VALUES (?,?,?,?,?,?,?,?)",
                     (datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), g.user["nombre"] if g.user else "Anónimo", accion, modulo,
                      registro, resumen[:500], resultado, motivo))


def ahora():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


# ============================================================ opciones de campos
def field_options(f):
    if f["fk"]:
        rows = q(f"SELECT id, {FK_LABEL[f['fk']]} AS l FROM {f['fk']} ORDER BY l")
        return [(str(r["id"]), r["l"]) for r in rows]
    if f["cat"]:
        return [(r["valor"], r["valor"]) for r in q("SELECT valor FROM catalogos WHERE categoria=? AND estado='Activo' ORDER BY valor", (f["cat"],))]
    if f["name"] == "rol":
        return [(k, v) for k, v in ROLES.items()]
    if f["name"] == "categoria" and f["opts"]:
        return [(o, CAT_NOMBRES.get(o, o)) for o in f["opts"]]
    return [(o, o) for o in (f["opts"] or [])]


def form_fields(m):
    """Campos visibles en el formulario para el usuario actual."""
    mod = next(k for k, v in MODULES.items() if v is m)
    fs = [f for f in m["fields"] if not f.get("hidden_form")]
    if level(mod) != "w":  # solo crea: formulario reducido de reporte
        rep = ["fecha_hora", "tipo", "urgencia", "ruta_id", "lugar", "vehiculo_id", "descripcion"]
        fs = [f for f in fs if f["name"] in rep]
    return fs


def default_value(f):
    d = f["default"]
    if d == "today":
        return date.today().isoformat()
    if d == "now":
        return ahora()
    return d


def next_code(mod, prefijo):
    n = (q1(f"SELECT COALESCE(MAX(id),0) FROM {mod}") or 0) + 1
    while q1(f"SELECT COUNT(*) FROM {mod} WHERE codigo=?", (f"{prefijo}-{n:04d}",)):
        n += 1
    return f"{prefijo}-{n:04d}"


# ============================================================ consultas de listado
def select_parts(mod):
    m = MODULES[mod]
    sel = ["t.*"]
    for f in m["fields"]:
        if f["fk"]:
            sel.append(f"(SELECT {FK_LABEL[f['fk']]} FROM {f['fk']} WHERE id=t.{f['name']}) AS {f['name']}__l")
    for k, v in m.get("extra", {}).items():
        sel.append(f"({fmt(v)}) AS {k}")
    return ", ".join(sel)


def filter_defs(mod):
    m = MODULES[mod]
    out = []
    for key in m["filters"]:
        f = next((x for x in m["fields"] if x["name"] == key), None)
        label = f["label"] if f else key.capitalize()
        if key in m.get("filter_options", {}):
            opts = [(o, o) for o in m["filter_options"][key]]
        elif m.get("dynamic_filters"):
            opts = [(r[0], r[0]) for r in q(f"SELECT DISTINCT {key} FROM {mod} WHERE {key} IS NOT NULL ORDER BY 1")]
        elif f:
            opts = field_options(f)
        else:
            opts = []
        if key == "vigencia":
            label = "Vigencia"
        if key == "estado" and not f:
            label = "Estado"
        if key == "validacion":
            label = "Validación"
        out.append(dict(key=key, label=label, options=opts, selected=request.args.get(key, "")))
    return out


def list_query(mod, args, limit=None, offset=0):
    m = MODULES[mod]
    where, params = [], []
    sc, sp = scope(mod)
    where.append(f"({sc})")
    params += sp
    qq = (args.get("q") or "").strip()
    if qq:
        like = f"%{qq}%"
        parts = []
        for c in m["search"]:
            expr = fmt(m.get("extra", {}).get(c, f"t.{c}"))
            parts.append(f"{expr} LIKE ?")
            params.append(like)
        where.append("(" + " OR ".join(parts) + ")")
    for key in m["filters"]:
        v = args.get(key)
        if v:
            expr = fmt(m["extra"][key]) if key in m.get("extra", {}) else f"t.{key}"
            where.append(f"({expr})=?")
            params.append(v)
    k = args.get("k")
    if k and k.isdigit() and int(k) < len(m["kpis"]) and m["kpis"][int(k)][1]:
        where.append("(" + fmt(m["kpis"][int(k)][1]) + ")")
    w = " AND ".join(where)
    total = q1(f"SELECT COUNT(*) FROM (SELECT {select_parts(mod)} FROM {mod} t WHERE {w})", params)
    sort, d = m.get("default_sort", ("id", "asc"))
    s = args.get("sort")
    allowed = {c[0] for c in m["columns"]} | {f["name"] for f in m["fields"]}
    if s in allowed:
        sort, d = s, "desc" if args.get("dir") == "desc" else "asc"
    f_ = next((x for x in m["fields"] if x["name"] == sort), None)
    order = f"{sort}__l" if f_ and f_["fk"] else (sort if sort in m.get("extra", {}) else f"t.{sort}")
    sql = f"SELECT {select_parts(mod)} FROM {mod} t WHERE {w} ORDER BY {order} {d.upper()}, t.id DESC"
    if limit:
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
    return sql, params, total, sort, d


def kpi_counts(mod):
    m = MODULES[mod]
    sc, sp = scope(mod)
    res = []
    for i, (label, wh, color, icon) in enumerate(m["kpis"]):
        w = f"({sc})" + (f" AND ({fmt(wh)})" if wh else "")
        res.append(dict(label=label, value=q1(f"SELECT COUNT(*) FROM {mod} t WHERE {w}", sp), color=color, icon=icon, idx=i, active=request.args.get("k") == str(i)))
    return res


def fetch_row(mod, rid):
    sc, sp = scope(mod)
    return get_db().execute(f"SELECT {select_parts(mod)} FROM {mod} t WHERE t.id=? AND ({sc})", [rid] + sp).fetchone()


# ============================================================ contexto de plantillas
def build_notifs():
    if "notifs" in g.__dict__:
        return g.notifs
    items = []
    if not g.user:
        return []
    rol, h = g.user["rol"], fechas()
    leidas = {r[0] for r in q("SELECT clave FROM notif_leidas WHERE usuario_id=?", (g.user["id"],))}

    def add(key, nivel, titulo, detalle, link):
        items.append(dict(key=key, nivel=nivel, titulo=titulo, detalle=detalle, link=link, leida=key in leidas))

    if level("documentos"):
        sc, sp = scope("documentos")
        for r in q(f"SELECT t.id, t.tipo, t.fecha_vencimiento, ({fmt('{vig}')}) AS vig, {fmt(MODULES['documentos']['extra']['titular'])} AS titular "
                   f"FROM documentos t WHERE ({sc}) AND t.fecha_vencimiento IS NOT NULL AND t.fecha_vencimiento<='{h['hoy30']}' "
                   f"ORDER BY t.fecha_vencimiento LIMIT 25", sp):
            vencido = r["vig"] == "Vencido"
            add(f"doc:{r['id']}:{r['vig']}", "Alta" if vencido else "Media",
                f"{r['tipo']} {'vencido' if vencido else 'próximo a vencer'}",
                f"{r['titular']} - vence {fdate(r['fecha_vencimiento'])}", url_for("listado", mod="documentos", q=r["tipo"], vigencia=r["vig"]))
    if level("mantenimientos") and rol != "socio":
        for r in q("SELECT m.id, m.codigo, m.fecha_programada, v.placa FROM mantenimientos m JOIN vehiculos v ON v.id=m.vehiculo_id "
                   "WHERE m.estado IN ('Solicitado','Aprobado','Pendiente de diagnóstico','Cotización pendiente') AND m.fecha_programada<=? ORDER BY m.fecha_programada LIMIT 10", (h["hoy15"],)):
            atras = r["fecha_programada"] < h["hoy"]
            add(f"mt:{r['id']}:{atras}", "Alta" if atras else "Media", f"Mantenimiento {'atrasado' if atras else 'próximo'}",
                f"{r['placa']} - {r['codigo']} ({fdate(r['fecha_programada'])})", url_for("listado", mod="mantenimientos", q=r["codigo"]))
    if rol in ("operaciones", "gerencia", "admin") and level("viajes"):
        n = q1("SELECT COUNT(*) FROM viajes WHERE (vehiculo_id IS NULL OR conductor_id IS NULL) AND estado IN ('Planificado','Confirmado')")
        if n:
            add(f"vj-sin:{n}", "Alta", f"{n} viaje(s) pendiente(s) de asignación", "Falta unidad o conductor.", url_for("listado", mod="viajes", k=1))
    if level("capacitaciones"):
        if rol == "conductor" and g.user["conductor_id"]:
            for r in q("SELECT a.id, c.titulo, a.fecha_limite, a.estado FROM asignaciones_cap a JOIN capacitaciones c ON c.id=a.capacitacion_id "
                       "WHERE a.conductor_id=? AND a.estado IN ('Asignada','En progreso','No aprobada') AND c.estado='Publicada' ORDER BY a.fecha_limite", (g.user["conductor_id"],)):
                venc = r["fecha_limite"] and r["fecha_limite"] < h["hoy"]
                add(f"cap:{r['id']}:{r['estado']}", "Alta" if venc else "Media", "Capacitación vencida" if venc else "Capacitación pendiente",
                    f"{r['titulo']} - límite {fdate(r['fecha_limite'])}", url_for("evaluar", aid=r["id"]))
        else:
            n = q1("SELECT COUNT(*) FROM asignaciones_cap WHERE estado IN ('Asignada','En progreso') AND fecha_limite<?", (h["hoy"],))
            if n:
                add(f"capv:{n}", "Media", f"{n} capacitación(es) con fecha límite vencida", "Conductores que aún no completan su capacitación.", url_for("listado", mod="capacitaciones", k=1))
    if level("incidentes") and rol != "conductor":
        for r in q("SELECT id, codigo, tipo, urgencia FROM incidentes WHERE estado='Nuevo' ORDER BY fecha_hora DESC LIMIT 8"):
            add(f"inc:{r['id']}", "Alta" if r["urgencia"] in ("Alta", "Crítica") else "Media", "Novedad sin atender", f"{r['codigo']} - {r['tipo']}",
                url_for("listado", mod="incidentes", q=r["codigo"]))
    if level("incumplimientos") and rol in ("seguridad", "gerencia", "admin"):
        n = q1("SELECT COUNT(*) FROM incumplimientos WHERE estado='Reportado'")
        if n:
            add(f"incu:{n}", "Media", f"{n} incumplimiento(s) pendiente(s) de revisión", "Reportes que aún no tienen revisión.", url_for("listado", mod="incumplimientos", estado="Reportado"))
    if level("hallazgos") and rol in ("seguridad", "operaciones", "gerencia", "admin"):
        n = q1("SELECT COUNT(*) FROM hallazgos WHERE estado IN ('Abierto','En seguimiento') AND (responsable IS NULL OR responsable='')")
        if n:
            add(f"hv:{n}", "Media", f"{n} hallazgo(s) vial(es) sin responsable", "Asigna un responsable de seguimiento.", url_for("listado", mod="hallazgos", k=1))
    rank = {"Alta": 0, "Media": 1}
    items.sort(key=lambda i: (i["leida"], rank.get(i["nivel"], 2)))
    g.notifs = items
    return items


@app.context_processor
def contexto():
    def nav():
        if not g.user:
            return []
        lab = LABELS_ROL.get(g.user["rol"], {})
        out = []
        for grupo, mods in NAV:
            its = []
            for k in mods:
                if k == "reportes":
                    if reportes_permitidos():
                        its.append(dict(key=k, label="Reportes", icon="chart", url=url_for("reportes")))
                elif level(k):
                    mm = MODULES[k]
                    its.append(dict(key=k, label=lab.get(k, mm["titulo"]), icon=mm["icon"], url=url_for("listado", mod=k)))
            if its:
                out.append((grupo, its))
        return out
    return dict(csrf=csrf_token(), nav=nav, notifs=build_notifs, ROLES=ROLES, hoy=fechas()["hoy"], level=level,
                can_create=can_create, rol_label=ROLES.get(g.user["rol"]) if g.user else "")


# ============================================================ login / logout
INTENTOS = {}


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("inicio"))
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        clave = (request.remote_addr or "?", email)
        n, t = INTENTOS.get(clave, (0, 0))
        if n >= 5 and time.time() - t < 300:
            error = "Demasiados intentos. Espera 5 minutos e inténtalo de nuevo."
        else:
            u = get_db().execute("SELECT * FROM usuarios WHERE lower(email)=?", (email,)).fetchone()
            if u and u["estado"] == "Activo" and check_password_hash(u["password_hash"], request.form.get("password") or ""):
                INTENTOS.pop(clave, None)
                session.clear()
                session["uid"] = u["id"]
                session.permanent = True
                g.user = u
                audit("Inicio de sesión", "sesión", u["id"], f"Ingreso de {u['nombre']}")
                get_db().commit()
                nxt = request.args.get("next") or ""
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("inicio"))
            INTENTOS[clave] = (n + 1 if time.time() - t < 300 else 1, time.time())
            error = "Correo o contraseña incorrectos."
    demo = get_db().execute("SELECT nombre,email,rol FROM usuarios WHERE estado='Activo' ORDER BY id").fetchall()
    return render_template("login.html", error=error, demo=demo)


@app.post("/salir")
def logout():
    audit("Cierre de sesión", "sesión", g.user["id"], "Cierre de sesión")
    get_db().commit()
    session.clear()
    return redirect(url_for("login"))


# ============================================================ inicio / dashboard
def cnt(mod, where="1=1", params=()):
    if not level(mod):
        return 0
    sc, sp = scope(mod)
    return q1(f"SELECT COUNT(*) FROM {mod} t WHERE ({sc}) AND ({fmt(where)})", sp + list(params)) or 0


def card(label, value, sub, color, icon, link):
    return dict(label=label, value=value, sub=sub, color=color, icon=icon, link=link)


@app.route("/")
def inicio():
    rol = g.user["rol"]
    dias = request.args.get("dias", "90")
    dias = int(dias) if dias in ("30", "90", "365") else 90
    desde = (date.today() - timedelta(days=dias)).isoformat()
    L = lambda mod, **kw: url_for("listado", mod=mod, **kw)
    top, mini, panels = [], [], []

    if rol in ("gerencia", "admin", "auditor"):
        dv = cnt("documentos", "fecha_vencimiento<='{hoy30}'")
        ya_venc = cnt("documentos", "fecha_vencimiento<'{hoy}'")
        sin_atender = cnt("incidentes", "estado='Nuevo'")
        top = [card("Vehículos disponibles", cnt("vehiculos", "estado='Disponible'"), f"de {cnt('vehiculos')} registrados", "blue", "bus", L("vehiculos", estado="Disponible")),
               card("Documentos vencidos o por vencer", dv, f"{ya_venc} ya vencidos", "warn", "file", L("documentos", k=1)),
               card("Novedades abiertas", cnt("incidentes", "estado IN ('Nuevo','En atención','Derivado')"), f"{sin_atender} sin atender", "danger", "alert", L("incidentes", k=1))]
        mini = [("Conductores activos", cnt("conductores", "estado='Activo'"), L("conductores", estado="Activo")),
                ("En mantenimiento", cnt("vehiculos", "estado='En mantenimiento'"), L("vehiculos", estado="En mantenimiento")),
                ("Viajes de hoy", cnt("viajes", "substr(fecha_hora,1,10)='{hoy}'"), L("viajes", k=0)),
                ("Capacitaciones pendientes", q1("SELECT COUNT(*) FROM asignaciones_cap WHERE estado IN ('Asignada','En progreso','No aprobada')"), L("capacitaciones", k=1)),
                ("Incumplimientos por revisar", cnt("incumplimientos", "estado IN ('Reportado','En revisión')"), L("incumplimientos", k=0))]
    elif rol == "operaciones":
        top = [card("Viajes de hoy", cnt("viajes", "substr(fecha_hora,1,10)='{hoy}'"), "programados para hoy", "blue", "calendar", L("viajes", k=0)),
               card("Sin unidad o conductor", cnt("viajes", "(vehiculo_id IS NULL OR conductor_id IS NULL) AND estado IN ('Planificado','Confirmado')"), "requieren asignación", "warn", "alert", L("viajes", k=1)),
               card("Unidades disponibles", cnt("vehiculos", "estado='Disponible'"), f"de {cnt('vehiculos')} registradas", "blue", "bus", L("vehiculos", estado="Disponible"))]
        mini = [("Conductores activos", cnt("conductores", "estado='Activo'"), L("conductores", estado="Activo")),
                ("Rutas activas", cnt("rutas", "estado='Activa'"), L("rutas", estado="Activa")),
                ("Con novedad o cancelados", cnt("viajes", "estado IN ('Con novedad','Cancelado')"), L("viajes", k=2))]
    elif rol == "seguridad":
        top = [card("Asignaciones pendientes", q1("SELECT COUNT(*) FROM asignaciones_cap WHERE estado IN ('Asignada','En progreso','No aprobada')"), "capacitaciones por completar", "warn", "book", L("capacitaciones", k=1)),
               card("Incumplimientos por revisar", cnt("incumplimientos", "estado IN ('Reportado','En revisión')"), "reportados o en revisión", "blue", "shield", L("incumplimientos", k=0)),
               card("Novedades abiertas", cnt("incidentes", "estado IN ('Nuevo','En atención','Derivado')"), "incidentes en seguimiento", "danger", "alert", L("incidentes", k=1))]
        mini = [("Capacitaciones publicadas", cnt("capacitaciones", "estado='Publicada'"), L("capacitaciones", estado="Publicada")),
                ("Hallazgos viales abiertos", cnt("hallazgos", "estado IN ('Abierto','En seguimiento')"), L("hallazgos", k=0))]
    elif rol == "flota":
        top = [card("En mantenimiento", cnt("vehiculos", "estado IN ('En mantenimiento','Fuera de servicio')"), "unidades fuera de operación", "warn", "wrench", L("vehiculos", k=1)),
               card("Mantenimientos próximos", cnt("mantenimientos", "estado NOT IN ('Finalizado','Cancelado') AND fecha_programada BETWEEN '{hoy}' AND '{hoy15}'"), "en los próximos 15 días", "blue", "calendar", L("mantenimientos", k=1)),
               card("Documentos vehiculares vencidos", q1("SELECT COUNT(*) FROM documentos WHERE vehiculo_id IS NOT NULL AND fecha_vencimiento<?", (fechas()["hoy"],)), "requieren renovación", "danger", "file", L("vehiculos", k=2))]
        mini = [("Unidades disponibles", cnt("vehiculos", "estado='Disponible'"), L("vehiculos", estado="Disponible")),
                ("Órdenes atrasadas", cnt("mantenimientos", "estado IN ('Solicitado','Aprobado','Pendiente de diagnóstico','Cotización pendiente') AND fecha_programada<'{hoy}'"), L("mantenimientos", k=2))]
    elif rol == "administrativo":
        top = [card("Documentos por revisar", cnt("documentos", "validacion='Pendiente de revisión'"), "pendientes de validación", "warn", "file", L("documentos", validacion="Pendiente de revisión")),
               card("Documentos vencidos", cnt("documentos", "fecha_vencimiento<'{hoy}'"), "requieren renovación", "danger", "alert", L("documentos", vigencia="Vencido")),
               card("Conductores activos", cnt("conductores", "estado='Activo'"), f"de {cnt('conductores')} registrados", "blue", "user", L("conductores", estado="Activo"))]
        mini = [("Licencias por vencer", cnt("conductores", "licencia_vence BETWEEN '{hoy}' AND '{hoy30}'"), L("conductores", k=1)),
                ("Socios activos", cnt("socios", "estado='Activo'"), L("socios", estado="Activo"))]
    elif rol == "conductor":
        cid = g.user["conductor_id"] or 0
        top = [card("Mis próximos viajes", cnt("viajes", "fecha_hora>='{hoy}' AND estado NOT IN ('Cancelado','Finalizado')"), "asignados a ti", "blue", "calendar", L("viajes")),
               card("Capacitaciones pendientes", q1("SELECT COUNT(*) FROM asignaciones_cap WHERE conductor_id=? AND estado IN ('Asignada','En progreso','No aprobada')", (cid,)), "por completar", "warn", "book", L("capacitaciones")),
               card("Documentos por vencer", cnt("documentos", "fecha_vencimiento<='{hoy30}'"), "vencidos o próximos a vencer", "danger", "file", L("documentos"))]
    elif rol == "socio":
        top = [card("Mis unidades", cnt("vehiculos"), "vinculadas a tu cuenta", "blue", "bus", L("vehiculos")),
               card("En mantenimiento", cnt("vehiculos", "estado IN ('En mantenimiento','Fuera de servicio')"), "unidades fuera de operación", "warn", "wrench", L("vehiculos", k=1)),
               card("Documentos por vencer", cnt("documentos", "fecha_vencimiento<='{hoy30}'"), "vencidos o próximos a vencer", "danger", "file", L("documentos", k=1))]

    # Paneles
    if level("viajes"):
        sc, sp = scope("viajes")
        rows = q(f"SELECT t.codigo, substr(t.fecha_hora,12,5) AS hora, (SELECT nombre FROM rutas WHERE id=t.ruta_id) AS ruta, "
                 f"(SELECT placa FROM vehiculos WHERE id=t.vehiculo_id) AS unidad, (SELECT nombres||' '||apellidos FROM conductores WHERE id=t.conductor_id) AS conductor, t.estado "
                 f"FROM viajes t WHERE ({sc}) AND substr(t.fecha_hora,1,10)>=? ORDER BY t.fecha_hora LIMIT 6", sp + [fechas()["hoy"]])
        panels.append(dict(tipo="tabla", titulo="Próximos viajes" if rol in ("conductor", "socio") else "Viajes de hoy y próximos", sub="Desde hoy en adelante",
                           cols=[("codigo", "Viaje", "bold"), ("hora", "Hora", "text"), ("ruta", "Ruta", "text"), ("unidad", "Unidad", "text"), ("conductor", "Conductor", "text"), ("estado", "Estado", "pill")],
                           rows=rows, link=L("viajes"), wide=True))
    if rol in ("gerencia", "admin", "auditor", "seguridad") and level("incumplimientos"):
        r = q("SELECT categoria, COUNT(*) n FROM incumplimientos WHERE substr(fecha_hora,1,10)>=? AND estado<>'Descartado' GROUP BY categoria ORDER BY n DESC LIMIT 6", (desde,))
        panels.append(dict(tipo="hbars", titulo="Incumplimientos por categoría", sub=f"Últimos {dias} días, sin contar descartados. Incluye reportes aún sin confirmar.",
                           datos=[(x["categoria"], x["n"]) for x in r], tono="blue"))
    if rol in ("gerencia", "admin", "auditor", "seguridad", "operaciones", "flota") and level("incidentes"):
        r = q("SELECT substr(fecha_hora,1,7) mes, COUNT(*) n FROM incidentes WHERE substr(fecha_hora,1,10)>=? GROUP BY mes ORDER BY mes", (desde,))
        panels.append(dict(tipo="cols", titulo="Novedades por mes", sub=f"Últimos {dias} días", datos=[(x["mes"], x["n"]) for x in r]))
    if rol in ("gerencia", "admin", "auditor", "flota", "socio") and level("documentos"):
        sc, sp = scope("documentos")
        r = q(f"SELECT ({fmt('{vig}')}) AS v, COUNT(*) n FROM documentos t WHERE ({sc}) AND vehiculo_id IS NOT NULL GROUP BY v", sp)
        orden = {"Vigente": 0, "Próximo a vencer": 1, "Vencido": 2, "Sin vencimiento": 3}
        panels.append(dict(tipo="hbars", titulo="Estado documental de la flota", sub="Documentos de vehículos a la fecha de hoy",
                           datos=sorted([(x["v"], x["n"]) for x in r], key=lambda a: orden.get(a[0], 9)), tono="estado"))
    if rol in ("gerencia", "admin", "auditor", "seguridad"):
        r = q("SELECT CASE WHEN estado IN ('Asignada','En progreso') AND fecha_limite<? THEN 'Vencida' ELSE estado END e, COUNT(*) n FROM asignaciones_cap GROUP BY e", (fechas()["hoy"],))
        panels.append(dict(tipo="hbars", titulo="Cumplimiento de capacitaciones", sub="Asignaciones por estado", datos=[(x["e"], x["n"]) for x in r], tono="estado"))

    return render_template("inicio.html", top=top, mini=mini, panels=panels, dias=dias, desde=desde,
                           atencion=[n for n in build_notifs() if not n["leida"]][:6], hoy_fmt=fdate(fechas()["hoy"]))


# ============================================================ listado genérico
@app.route("/m/<mod>")
def listado(mod):
    if mod not in MODULES:
        abort(404)
    m = need(mod)
    page = max(int(request.args.get("page", 1) or 1), 1) if (request.args.get("page", "1") or "1").isdigit() else 1
    sql, params, total, sort, d = list_query(mod, request.args, PER_PAGE, (page - 1) * PER_PAGE)
    rows = q(sql, params)
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    lab = LABELS_ROL.get(g.user["rol"], {}).get(mod, m["titulo"])
    fields = form_fields(m) if not m.get("readonly") else []
    form = [dict(f, options=field_options(f) if (f["fk"] or f["cat"] or f["opts"] is not None or f["name"] == "rol") else None,
                 default_val=default_value(f)) for f in fields]
    qs = {k: v for k, v in request.args.items() if k not in ("page",)}
    return render_template("listado.html", mod=mod, m=m, titulo=lab, rows=rows, total=total, page=page, pages=pages, per=PER_PAGE,
                           first=(page - 1) * PER_PAGE + 1 if total else 0, last=min(page * PER_PAGE, total),
                           kpis=kpi_counts(mod), filtros=filter_defs(mod), sort=sort, dir=d, qs=qs, form=form,
                           lv=level(mod), crear=can_create(mod) and not m.get("readonly"), q=request.args.get("q", ""),
                           estado_options=[(s, s) for s in m["states"]])


@app.get("/m/<mod>/exportar.csv")
def exportar(mod):
    if mod not in MODULES:
        abort(404)
    m = need(mod)
    if g.user["rol"] in ("conductor", "socio"):
        abort(403)
    sql, params, total, _, _ = list_query(mod, request.args)
    rows = q(sql, params)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"{m['titulo']} - Rutas del Pacífico"])
    filtros = ", ".join(f"{k}={v}" for k, v in request.args.items() if v and k not in ("sort", "dir", "page")) or "sin filtros"
    w.writerow([f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", f"Usuario: {g.user['nombre']}", f"Filtros: {filtros}"])
    w.writerow([])
    w.writerow([c[1] for c in m["columns"]])
    for r in rows:
        w.writerow([_plain(r, c) for c in m["columns"]])
    audit("Exportación", mod, None, f"Exportó {len(rows)} registros de {m['titulo']} ({filtros})")
    get_db().commit()
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={mod}_{date.today().isoformat()}.csv"})


def _plain(r, c):
    key, kind = c[0], c[2]
    v = r[key] if key in r.keys() else None
    if kind == "fk":
        return r[key + "__l"] if (key + "__l") in r.keys() else ""
    if kind == "mask":
        return v if g.user["rol"] in ("admin", "administrativo") else mask_id(v)
    if kind in ("date", "date_warn", "date_warn_mt"):
        return fdate(v) if v else "No disponible"
    if kind == "dt":
        return fdt(v) if v else "No disponible"
    if kind == "role":
        return ROLES.get(v, v)
    return "" if v is None else v


@app.get("/m/<mod>/<int:rid>/json")
def registro_json(mod, rid):
    m = need(mod)
    row = fetch_row(mod, rid)
    if not row:
        abort(404)
    data = {f["name"]: row[f["name"]] for f in m["fields"] if f["t"] not in ("password", "file") and f["name"] in row.keys()}
    return jsonify(data)


@app.get("/m/<mod>/<int:rid>/detalle")
def detalle(mod, rid):
    m = need(mod)
    if m.get("no_detail"):
        abort(404)
    row = fetch_row(mod, rid)
    if not row:
        abort(404)
    full = g.user["rol"] in ("admin", "administrativo")
    campos = []
    for f in m["fields"]:
        if f["t"] in ("password",) or (f["restricted"] and not full):
            continue
        v = row[f["name"]] if f["name"] in row.keys() else None
        if f["fk"]:
            html = escape(row[f["name"] + "__l"]) if row[f["name"] + "__l"] else Markup('<span class="muted">—</span>')
        elif f["t"] == "date":
            html = fdate(v)
        elif f["t"] == "datetime":
            html = fdt(v)
        elif f["name"] in ("estado", "validacion", "severidad", "urgencia", "prioridad"):
            html = pill(v)
        elif f["name"] == "identificacion":
            html = v if full and v else mask_id(v)
        elif f["name"] == "rol":
            html = ROLES.get(v, v)
        elif f["t"] == "file":
            html = Markup(f'<a href="{url_for("archivo", nombre=v)}" target="_blank" rel="noopener">Abrir archivo</a>') if v else Markup('<span class="muted">Sin archivo</span>')
        else:
            html = v if v not in (None, "") else Markup('<span class="muted">—</span>')
        campos.append((f["label"], html, f["full"]))
    rels = []
    for titulo, sql, cols in m.get("related", []):
        rels.append((titulo, cols, get_db().execute(fmt(sql), {"id": rid}).fetchall()))
    hist = q("SELECT fecha, usuario, accion, resumen, motivo FROM auditoria WHERE modulo=? AND registro=? ORDER BY id DESC LIMIT 30", (mod, rid))
    extra = {}
    if mod == "capacitaciones":
        extra["preguntas"] = q("SELECT * FROM preguntas WHERE capacitacion_id=? ORDER BY id", (rid,))
        asig_sql = ("SELECT a.*, c.nombres||' '||c.apellidos AS conductor, CASE WHEN a.estado IN ('Asignada','En progreso') AND a.fecha_limite<? THEN 'Vencida' ELSE a.estado END AS estado_v "
                    "FROM asignaciones_cap a JOIN conductores c ON c.id=a.conductor_id WHERE a.capacitacion_id=?")
        pr = [fechas()["hoy"], rid]
        if g.user["rol"] == "conductor":
            asig_sql += " AND a.conductor_id=?"
            pr.append(g.user["conductor_id"] or 0)
        extra["asignados"] = q(asig_sql + " ORDER BY c.apellidos", pr)
        extra["conductores"] = q("SELECT id, nombres||' '||apellidos AS n FROM conductores WHERE estado='Activo' ORDER BY apellidos") if level(mod) == "w" else []
    if mod == "documentos" and row["archivo"]:
        pass
    titulo = None
    for c in m["columns"]:
        if c[2] in ("bold", "two"):
            titulo = row[c[0]]
            break
    estado = row[m.get("state_field", "estado")] if m.get("state_field", "estado") in row.keys() else None
    return render_template("partials/detalle.html", mod=mod, m=m, row=row, campos=campos, rels=rels, hist=hist, titulo=titulo,
                           estado=estado, extra=extra, lv=level(mod), maxint=MAX_INTENTOS_EVAL)


# ============================================================ validaciones por módulo
def _dt(s):
    return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")


def v_conductores(data, old, errors, warns, rid):
    if data.get("tipo_id") == "Cédula" and data.get("identificacion") and not re.fullmatch(r"\d{10}", data["identificacion"]):
        errors["identificacion"] = "La cédula debe tener 10 dígitos numéricos."
    if data.get("identificacion") and "identificacion" not in errors:
        if q1("SELECT COUNT(*) FROM conductores WHERE identificacion=? AND id<>?", (data["identificacion"], rid or 0)):
            errors["identificacion"] = "Ya existe un conductor con esa identificación."


def v_vehiculos(data, old, errors, warns, rid):
    if data.get("placa"):
        p = data["placa"].upper().replace(" ", "")
        if not re.fullmatch(r"[A-Z]{3}-?\d{3,4}", p):
            errors["placa"] = "Formato esperado: ABC-1234."
        else:
            data["placa"] = p if "-" in p else p[:3] + "-" + p[3:]
    if data.get("anio") is not None and not (1980 <= int(data["anio"]) <= date.today().year + 1):
        errors["anio"] = "Ingresa un año válido."
    if data.get("capacidad") is not None and int(data["capacidad"]) <= 0:
        errors["capacidad"] = "La capacidad debe ser mayor que cero."


def v_viajes(data, old, errors, warns, rid):
    ruta = get_db().execute("SELECT duracion_horas FROM rutas WHERE id=?", (data["ruta_id"],)).fetchone() if data.get("ruta_id") else None
    dur = (ruta["duracion_horas"] if ruta and ruta["duracion_horas"] else 4)
    if not data.get("fecha_hora"):
        return
    ini = _dt(data["fecha_hora"])
    activo = data.get("estado") not in VIAJE_LIBRE
    if activo:
        if data.get("vehiculo_id"):
            v = get_db().execute("SELECT placa, estado FROM vehiculos WHERE id=?", (data["vehiculo_id"],)).fetchone()
            if v["estado"] in ("En mantenimiento", "Fuera de servicio", "Inactivo"):
                errors["vehiculo_id"] = f"La unidad {v['placa']} está '{v['estado']}' y no puede asignarse."
        if data.get("conductor_id"):
            c = get_db().execute("SELECT estado FROM conductores WHERE id=?", (data["conductor_id"],)).fetchone()
            if c["estado"] != "Activo":
                errors["conductor_id"] = f"El conductor está '{c['estado']}' y no puede asignarse."
        d0 = (ini - timedelta(days=1)).strftime("%Y-%m-%d")
        d1 = (ini + timedelta(days=1)).strftime("%Y-%m-%d")
        for key, quien in (("vehiculo_id", "La unidad"), ("conductor_id", "El conductor")):
            if data.get(key) and key not in errors:
                for o in q(f"SELECT v.codigo, v.fecha_hora, r.duracion_horas FROM viajes v JOIN rutas r ON r.id=v.ruta_id WHERE v.{key}=? AND v.id<>? "
                           f"AND v.estado NOT IN ('Cancelado','Finalizado') AND substr(v.fecha_hora,1,10) BETWEEN ? AND ?", (data[key], rid or 0, d0, d1)):
                    s2 = _dt(o["fecha_hora"])
                    d2 = o["duracion_horas"] or 4
                    if ini < s2 + timedelta(hours=d2) and s2 < ini + timedelta(hours=dur):
                        errors[key] = f"{quien} ya está asignad{'a' if quien == 'La unidad' else 'o'} al viaje {o['codigo']} en un horario que se cruza."
                        break
        # advertencias de documentos
        if data.get("vehiculo_id"):
            n = q1("SELECT COUNT(*) FROM documentos WHERE vehiculo_id=? AND fecha_vencimiento<?", (data["vehiculo_id"], fechas()["hoy"]))
            if n:
                warns.append(f"La unidad asignada tiene {n} documento(s) vencido(s).")
        if data.get("conductor_id"):
            n = q1("SELECT COUNT(*) FROM documentos WHERE conductor_id=? AND fecha_vencimiento<?", (data["conductor_id"], fechas()["hoy"]))
            if n:
                warns.append(f"El conductor asignado tiene {n} documento(s) vencido(s).")
    if old:
        cambio = any(str(data.get(k) or "") != str(old[k] or "") for k in ("ruta_id", "fecha_hora", "vehiculo_id", "conductor_id"))
        if cambio and not data.get("motivo_cambio"):
            errors["motivo_cambio"] = "Indica el motivo del cambio de asignación."


def v_documentos(data, old, errors, warns, rid):
    if data.get("fecha_emision") and data.get("fecha_vencimiento") and data["fecha_vencimiento"] < data["fecha_emision"]:
        errors["fecha_vencimiento"] = "El vencimiento no puede ser anterior a la emisión."


def v_mantenimientos(data, old, errors, warns, rid):
    if data.get("fecha_recepcion") and data.get("fecha_entrega") and data["fecha_entrega"] < data["fecha_recepcion"]:
        errors["fecha_entrega"] = "La entrega no puede ser anterior a la recepción."
    if data.get("costo") is not None and float(data["costo"]) < 0:
        errors["costo"] = "El costo no puede ser negativo."


def v_capacitaciones(data, old, errors, warns, rid):
    if data.get("nota_minima") is not None and not (0 <= float(data["nota_minima"]) <= 100):
        errors["nota_minima"] = "Debe estar entre 0 y 100."
    if rid and data.get("estado") == "Publicada" and data.get("tipo") == "Cuestionario" and not q1("SELECT COUNT(*) FROM preguntas WHERE capacitacion_id=?", (rid,)):
        errors["estado"] = "Agrega al menos una pregunta antes de publicar un cuestionario."


def v_usuarios(data, old, errors, warns, rid):
    pw = data.get("password")
    if not rid and not pw:
        errors["password"] = "La contraseña es obligatoria para un usuario nuevo."
    if pw and len(pw) < 8:
        errors["password"] = "Debe tener al menos 8 caracteres."
    if data.get("rol") == "conductor" and not data.get("conductor_id"):
        errors["conductor_id"] = "Vincula un conductor para este rol."
    if data.get("rol") == "socio" and not data.get("socio_id"):
        errors["socio_id"] = "Vincula un socio para este rol."
    if rid == g.user["id"] and (data.get("estado") == "Inactivo" or data.get("rol") != g.user["rol"]):
        errors["rol"] = "No puedes cambiar tu propio rol ni desactivar tu propia cuenta."


VALIDATORS = {"conductores": v_conductores, "vehiculos": v_vehiculos, "viajes": v_viajes, "documentos": v_documentos,
              "mantenimientos": v_mantenimientos, "capacitaciones": v_capacitaciones, "usuarios": v_usuarios}


def parse_form(m, form):
    data, errors = {}, {}
    for f in form_fields(m):
        n = f["name"]
        if f["t"] == "file":
            continue
        v = (form.get(n) or "").strip()
        if f["t"] == "password":
            data[n] = v
            continue
        if v == "":
            if f["req"]:
                errors[n] = "Este campo es obligatorio."
            data[n] = None
            continue
        t = f["t"]
        try:
            if t == "number":
                x = float(v.replace(",", "."))
                v = int(x) if x == int(x) else x
            elif t == "date":
                date.fromisoformat(v)
            elif t == "datetime":
                datetime.strptime(v[:16], "%Y-%m-%dT%H:%M")
                v = v[:16]
            elif t == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
                raise ValueError
            elif t == "fk":
                v = int(v)
                if not q1(f"SELECT COUNT(*) FROM {f['fk']} WHERE id=?", (v,)):
                    raise ValueError
            elif t == "select":
                if v not in [o for o, _ in field_options(f)]:
                    raise ValueError
        except (ValueError, TypeError):
            errors[n] = "Valor no válido."
            continue
        data[n] = v
    return data, errors


def diff_summary(m, old, data):
    partes = []
    for f in form_fields(m):
        n = f["name"]
        if f["t"] in ("password", "file") or n not in data:
            continue
        a, b = old[n], data[n]
        if str(a if a is not None else "") != str(b if b is not None else ""):
            def show(val):
                if val in (None, ""):
                    return "vacío"
                if f["fk"]:
                    lab = q1(f"SELECT {FK_LABEL[f['fk']]} FROM {f['fk']} WHERE id=?", (val,))
                    return lab or val
                return val
            partes.append(f"{f['label']}: {show(a)} → {show(b)}")
    if m is MODULES["usuarios"] and data.get("password"):
        partes.append("Contraseña actualizada")
    return "; ".join(partes) or "Sin cambios en los campos"


def guardar_archivo(mod, rid):
    f = request.files.get("archivo")
    if not f or not f.filename:
        return None, None
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg"):
        return None, "Solo se admiten archivos PDF, PNG o JPG."
    nombre = f"{mod}_{rid}_{secrets.token_hex(4)}{ext}"
    f.save(os.path.join(UPLOADS, secure_filename(nombre)))
    return nombre, None


@app.get("/archivos/<nombre>")
def archivo(nombre):
    if not level("documentos"):
        abort(403)
    sc, sp = scope("documentos")
    if not q1(f"SELECT COUNT(*) FROM documentos t WHERE t.archivo=? AND ({sc})", [nombre] + sp):
        abort(404)
    audit("Descarga", "documentos", None, f"Abrió el archivo {nombre}")
    get_db().commit()
    return send_from_directory(UPLOADS, nombre)


@app.post("/m/<mod>/guardar")
def guardar(mod):
    if mod not in MODULES or MODULES[mod].get("readonly"):
        abort(404)
    m = MODULES[mod]
    rid = request.form.get("id")
    rid = int(rid) if rid and rid.isdigit() else None
    if rid:
        need(mod, write=True)
        old = fetch_row(mod, rid)
        if not old:
            abort(404)
    else:
        if not can_create(mod):
            abort(403)
        old = None
    data, errors = parse_form(m, request.form)
    warns = []
    fn = VALIDATORS.get(mod)
    if fn:
        fn(data, old, errors, warns, rid)
    if mod == "documentos" and not errors:
        pass
    # campos forzados para quien solo reporta (conductor)
    if not rid and level(mod) != "w":
        for campo, ufield in m.get("force_self", {}).items():
            data[campo] = g.user[ufield]
        if not data.get("conductor_id") and "conductor_id" in [f["name"] for f in m["fields"]]:
            errors["__all__"] = "Tu usuario no está vinculado a un conductor. Pide a un administrador que lo vincule."
    if errors:
        return jsonify(ok=False, errors=errors, message="Revisa los campos marcados.")
    db = get_db()
    # normalizaciones y extras
    password = data.pop("password", None) if mod == "usuarios" else None
    if m.get("prefijo") and "codigo" in [f["name"] for f in m["fields"]] and not data.get("codigo"):
        if rid:
            data["codigo"] = old["codigo"]
        else:
            data["codigo"] = next_code(mod, m["prefijo"])
    if mod == "documentos" and data.get("validacion") in ("Validado", "Rechazado") and (not old or old["validacion"] != data["validacion"]):
        data["validado_por"], data["validado_en"] = g.user["nombre"], ahora()
    if mod == "documentos":
        nombre, err = guardar_archivo(mod, rid or "nuevo")
        if err:
            return jsonify(ok=False, errors={"archivo": err}, message="Revisa los campos marcados.")
        if nombre:
            data["archivo"] = nombre
    try:
        if rid:
            data["actualizado_por"], data["actualizado_en"] = g.user["nombre"], ahora()
            if password:
                data["password_hash"] = generate_password_hash(password)
            sets = ", ".join(f"{k}=?" for k in data)
            resumen = diff_summary(m, old, data)
            db.execute(f"UPDATE {mod} SET {sets} WHERE id=?", list(data.values()) + [rid])
            accion = "Edición"
        else:
            if "creado_por" in [r[1] for r in db.execute(f"PRAGMA table_info({mod})")]:
                data["creado_por"], data["creado_en"] = g.user["nombre"], ahora()
            if mod == "usuarios":
                data["password_hash"] = generate_password_hash(password)
                data["creado_en"] = ahora()
            cols = ",".join(data)
            cur = db.execute(f"INSERT INTO {mod}({cols}) VALUES ({','.join('?' * len(data))})", list(data.values()))
            rid = cur.lastrowid
            accion, resumen = "Creación", f"Nuevo registro en {m['titulo']}: {data.get('codigo') or data.get('nombre') or data.get('tipo') or rid}"
    except sqlite3.IntegrityError as e:
        db.rollback()
        mt = re.search(r"UNIQUE constraint failed: \w+\.(\w+)", str(e))
        campo = mt.group(1) if mt else "__all__"
        return jsonify(ok=False, errors={campo: "Ya existe un registro con este valor."}, message="Revisa los campos marcados.")
    # efectos secundarios
    if mod == "mantenimientos" and data.get("estado") in ("En ejecución", "Esperando repuesto") and data.get("vehiculo_id"):
        db.execute("UPDATE vehiculos SET estado='En mantenimiento' WHERE id=? AND estado IN ('Disponible','Asignado')", (data["vehiculo_id"],))
        audit("Cambio de estado", "vehiculos", data["vehiculo_id"], "Estado: pasa a 'En mantenimiento' por orden de mantenimiento", motivo=f"Orden {data.get('codigo')}")
    audit(accion, mod, rid, resumen, motivo=data.get("motivo_cambio"))
    db.commit()
    msg = 'Cambios guardados correctamente.' if accion == 'Edición' else 'Registro creado correctamente.'
    flash(msg + ((" Atención: " + " ".join(warns)) if warns else ""), "warn" if warns else "ok")
    return jsonify(ok=True, message=msg, id=rid)


@app.post("/m/<mod>/<int:rid>/estado")
def cambiar_estado(mod, rid):
    m = need(mod, write=True)
    sf = m.get("state_field", "estado")
    row = fetch_row(mod, rid)
    if not row or not m["states"]:
        abort(404)
    nuevo = (request.form.get("nuevo") or "").strip()
    motivo = (request.form.get("motivo") or "").strip()
    if nuevo not in m["states"]:
        return jsonify(ok=False, message="Estado no válido.")
    if nuevo == row[sf]:
        return jsonify(ok=False, message="El registro ya tiene ese estado.")
    if (m.get("reason_all") or nuevo in m.get("reason_states", [])) and not motivo:
        return jsonify(ok=False, message="Indica el motivo del cambio.", errors={"motivo": "El motivo es obligatorio para este cambio."})
    db = get_db()
    sets = {sf: nuevo, "actualizado_por": g.user["nombre"], "actualizado_en": ahora()} if "actualizado_por" in row.keys() else {sf: nuevo}
    if mod == "vehiculos" and nuevo == "Disponible":
        if q1("SELECT COUNT(*) FROM mantenimientos WHERE vehiculo_id=? AND estado IN ('En ejecución','Esperando repuesto')", (rid,)):
            return jsonify(ok=False, message="La unidad tiene un mantenimiento en ejecución. Finaliza o cancela la orden antes de liberarla.")
    if mod == "viajes" and nuevo in ("Confirmado", "En curso") and (not row["vehiculo_id"] or not row["conductor_id"]):
        return jsonify(ok=False, message="Asigna unidad y conductor antes de confirmar el viaje.")
    if mod == "capacitaciones" and nuevo == "Publicada" and row["tipo"] == "Cuestionario" and not q1("SELECT COUNT(*) FROM preguntas WHERE capacitacion_id=?", (rid,)):
        return jsonify(ok=False, message="Agrega al menos una pregunta antes de publicar el cuestionario.")
    if mod == "usuarios" and rid == g.user["id"] and nuevo == "Inactivo":
        return jsonify(ok=False, message="No puedes desactivar tu propia cuenta.")
    if m.get("reason_field") and motivo:
        sets[m["reason_field"]] = motivo
    if mod == "incumplimientos" and nuevo in ("Cerrado", "Descartado"):
        sets["fecha_cierre"] = date.today().isoformat()
    if mod == "incumplimientos" and not row["responsable"] and nuevo != "Reportado":
        sets["responsable"] = g.user["nombre"]
    if mod == "mantenimientos" and nuevo == "Finalizado" and not row["fecha_entrega"]:
        sets["fecha_entrega"] = date.today().isoformat()
    if mod == "documentos" and nuevo in ("Validado", "Rechazado"):
        sets["validado_por"], sets["validado_en"] = g.user["nombre"], ahora()
    db.execute(f"UPDATE {mod} SET {', '.join(k + '=?' for k in sets)} WHERE id=?", list(sets.values()) + [rid])
    if mod == "mantenimientos" and nuevo in ("En ejecución", "Esperando repuesto"):
        db.execute("UPDATE vehiculos SET estado='En mantenimiento' WHERE id=? AND estado IN ('Disponible','Asignado')", (row["vehiculo_id"],))
    audit("Cambio de estado", mod, rid, f"{m['singular'].capitalize()}: {row[sf]} → {nuevo}", motivo=motivo or None)
    db.commit()
    flash("Estado actualizado.", "ok")
    return jsonify(ok=True, message="Estado actualizado.")


@app.post("/m/<mod>/<int:rid>/eliminar")
def eliminar(mod, rid):
    m = need(mod, write=True)
    if m.get("readonly"):
        abort(404)
    row = fetch_row(mod, rid)
    if not row:
        abort(404)
    if mod == "usuarios" and rid == g.user["id"]:
        return jsonify(ok=False, message="No puedes eliminar tu propia cuenta.")
    nombre = row["codigo"] if "codigo" in row.keys() else (row["nombre"] if "nombre" in row.keys() else rid)
    try:
        get_db().execute(f"DELETE FROM {mod} WHERE id=?", (rid,))
    except sqlite3.IntegrityError:
        get_db().rollback()
        audit("Eliminación", mod, rid, f"Intento fallido de eliminar {nombre}: tiene registros relacionados", resultado="Fallido")
        get_db().commit()
        return jsonify(ok=False, message="No se puede eliminar: tiene registros relacionados. Cambia su estado a inactivo en su lugar.")
    audit("Eliminación", mod, rid, f"Eliminó {m['singular']} {nombre}")
    get_db().commit()
    flash(f"{m['singular'].capitalize()} eliminado.", "ok")
    return jsonify(ok=True, message="Eliminado.")


# ============================================================ capacitaciones y evaluaciones
@app.post("/cap/<int:cid>/asignar")
def cap_asignar(cid):
    need("capacitaciones", write=True)
    cap = q1("SELECT * FROM capacitaciones WHERE id=?", (cid,))
    if not cap:
        abort(404)
    ids = request.form.getlist("conductores")
    if request.form.get("todos"):
        ids = [str(r["id"]) for r in q("SELECT id FROM conductores WHERE estado='Activo'")]
    limite = request.form.get("fecha_limite") or ""
    try:
        date.fromisoformat(limite)
    except ValueError:
        return jsonify(ok=False, message="Indica una fecha límite válida.")
    if not ids:
        return jsonify(ok=False, message="Selecciona al menos un conductor.")
    n = 0
    for i in ids:
        if i.isdigit():
            cur = get_db().execute("INSERT OR IGNORE INTO asignaciones_cap(capacitacion_id,conductor_id,fecha_asignacion,fecha_limite) VALUES (?,?,?,?)",
                                   (cid, int(i), date.today().isoformat(), limite))
            n += cur.rowcount
    audit("Asignación", "capacitaciones", cid, f"Asignó la capacitación a {n} conductor(es), límite {fdate(limite)}")
    get_db().commit()
    return jsonify(ok=True, message=f"Se asignó a {n} conductor(es)." + (" Algunos ya la tenían asignada." if n < len(ids) else ""))


@app.post("/cap/<int:cid>/pregunta")
def cap_pregunta(cid):
    need("capacitaciones", write=True)
    f = {k: (request.form.get(k) or "").strip() for k in ("texto", "opcion_a", "opcion_b", "opcion_c", "opcion_d", "correcta")}
    if not (f["texto"] and f["opcion_a"] and f["opcion_b"]) or f["correcta"] not in ("A", "B", "C", "D"):
        return jsonify(ok=False, message="Completa la pregunta, al menos dos opciones y marca la correcta.")
    if f["correcta"] in ("C", "D") and not f["opcion_" + f["correcta"].lower()]:
        return jsonify(ok=False, message="La respuesta correcta apunta a una opción vacía.")
    get_db().execute("INSERT INTO preguntas(capacitacion_id,texto,opcion_a,opcion_b,opcion_c,opcion_d,correcta) VALUES (?,?,?,?,?,?,?)",
                     (cid, f["texto"], f["opcion_a"], f["opcion_b"], f["opcion_c"] or None, f["opcion_d"] or None, f["correcta"]))
    audit("Edición", "capacitaciones", cid, "Agregó una pregunta al cuestionario")
    get_db().commit()
    return jsonify(ok=True, message="Pregunta agregada.")


@app.post("/pregunta/<int:pid>/eliminar")
def pregunta_eliminar(pid):
    need("capacitaciones", write=True)
    cid = q1("SELECT capacitacion_id FROM preguntas WHERE id=?", (pid,))
    get_db().execute("DELETE FROM preguntas WHERE id=?", (pid,))
    audit("Edición", "capacitaciones", cid, "Eliminó una pregunta del cuestionario")
    get_db().commit()
    return jsonify(ok=True, message="Pregunta eliminada.")


@app.post("/asig/<int:aid>/<accion>")
def asig_accion(aid, accion):
    need("capacitaciones", write=True)
    a = q1("SELECT * FROM asignaciones_cap WHERE id=?", (aid,))
    if not a or accion not in ("asistencia", "reabrir", "quitar"):
        abort(404)
    if accion == "asistencia":
        get_db().execute("UPDATE asignaciones_cap SET estado='Completada', fecha_resultado=? WHERE id=?", (date.today().isoformat(), aid))
        msg = "Asistencia registrada."
    elif accion == "reabrir":
        get_db().execute("UPDATE asignaciones_cap SET estado='Asignada', intentos=0 WHERE id=?", (aid,))
        msg = "Se autorizó un nuevo ciclo de intentos."
    else:
        get_db().execute("DELETE FROM asignaciones_cap WHERE id=?", (aid,))
        msg = "Asignación retirada."
    audit("Asignación", "capacitaciones", a["capacitacion_id"], f"{msg} (asignación {aid})")
    get_db().commit()
    return jsonify(ok=True, message=msg)


@app.route("/evaluar/<int:aid>", methods=["GET", "POST"])
def evaluar(aid):
    a = get_db().execute("SELECT a.*, c.titulo, c.tipo, c.descripcion, c.recurso_url, c.nota_minima, c.estado AS cap_estado FROM asignaciones_cap a "
                         "JOIN capacitaciones c ON c.id=a.capacitacion_id WHERE a.id=?", (aid,)).fetchone()
    if not a or g.user["rol"] != "conductor" or a["conductor_id"] != g.user["conductor_id"]:
        abort(403)
    preguntas = q("SELECT * FROM preguntas WHERE capacitacion_id=? ORDER BY id", (a["capacitacion_id"],))
    cerrada = a["estado"] in ("Aprobada", "Completada")
    sin_intentos = a["estado"] == "No aprobada" and a["intentos"] >= MAX_INTENTOS_EVAL
    resultado = None
    if request.method == "POST" and not cerrada and not sin_intentos and a["cap_estado"] == "Publicada":
        if not preguntas:
            get_db().execute("UPDATE asignaciones_cap SET estado='Completada', fecha_resultado=? WHERE id=?", (date.today().isoformat(), aid))
            audit("Capacitación", "capacitaciones", a["capacitacion_id"], "Confirmó haber revisado el contenido")
            get_db().commit()
            flash("Registramos que completaste esta capacitación.", "ok")
            return redirect(url_for("listado", mod="capacitaciones"))
        ok = sum(1 for p in preguntas if request.form.get(f"p{p['id']}") == p["correcta"])
        nota = round(ok * 100 / len(preguntas))
        aprobado = nota >= a["nota_minima"]
        get_db().execute("INSERT INTO intentos_eval(asignacion_id,fecha,nota,aprobado) VALUES (?,?,?,?)", (aid, ahora(), nota, int(aprobado)))
        get_db().execute("UPDATE asignaciones_cap SET estado=?, nota=?, intentos=intentos+1, fecha_resultado=? WHERE id=?",
                         ("Aprobada" if aprobado else "No aprobada", nota, date.today().isoformat(), aid))
        audit("Evaluación", "capacitaciones", a["capacitacion_id"], f"Resultado {nota}% ({'aprobada' if aprobado else 'no aprobada'}), intento {a['intentos'] + 1}")
        get_db().commit()
        resultado = dict(nota=nota, aprobado=aprobado, ok=ok, total=len(preguntas), minimo=a["nota_minima"])
        a = get_db().execute("SELECT a.*, c.titulo, c.tipo, c.descripcion, c.recurso_url, c.nota_minima, c.estado AS cap_estado FROM asignaciones_cap a "
                             "JOIN capacitaciones c ON c.id=a.capacitacion_id WHERE a.id=?", (aid,)).fetchone()
        cerrada = a["estado"] in ("Aprobada", "Completada")
        sin_intentos = a["estado"] == "No aprobada" and a["intentos"] >= MAX_INTENTOS_EVAL
    return render_template("evaluar.html", a=a, preguntas=preguntas, cerrada=cerrada, sin_intentos=sin_intentos, resultado=resultado, maxint=MAX_INTENTOS_EVAL)


# ============================================================ reportes
REPORTES = {
    "documentos": dict(titulo="Documentos vencidos y próximos a vencer", roles=["gerencia", "admin", "auditor", "flota", "administrativo"], fecha="t.fecha_vencimiento",
                       sql="SELECT t.tipo, " + MODULES["documentos"]["extra"]["titular"] + " AS titular, t.fecha_vencimiento, ({vig}) AS vigencia, t.validacion FROM documentos t "
                           "WHERE t.fecha_vencimiento IS NOT NULL AND t.fecha_vencimiento<='{hoy30}' {rango} ORDER BY t.fecha_vencimiento",
                       cols=[("tipo", "Documento", "text"), ("titular", "Titular", "text"), ("fecha_vencimiento", "Vence", "date"), ("vigencia", "Vigencia", "pill"), ("validacion", "Validación", "pill")]),
    "flota": dict(titulo="Inventario de vehículos por estado", roles=["gerencia", "admin", "auditor", "flota", "operaciones"], fecha=None,
                  sql="SELECT estado, COUNT(*) AS cantidad FROM vehiculos t GROUP BY estado ORDER BY cantidad DESC",
                  cols=[("estado", "Estado", "pill"), ("cantidad", "Cantidad", "text")]),
    "conductores": dict(titulo="Conductores activos e inactivos", roles=["gerencia", "admin", "auditor", "administrativo", "seguridad"], fecha=None,
                        sql="SELECT estado, COUNT(*) AS cantidad FROM conductores t GROUP BY estado ORDER BY cantidad DESC",
                        cols=[("estado", "Estado", "pill"), ("cantidad", "Cantidad", "text")]),
    "viajes": dict(titulo="Viajes programados y su estado", roles=["gerencia", "admin", "auditor", "operaciones"], fecha="t.fecha_hora",
                   sql="SELECT t.codigo, r.nombre AS ruta, t.fecha_hora, v.placa AS unidad, c.nombres||' '||c.apellidos AS conductor, t.estado FROM viajes t JOIN rutas r ON r.id=t.ruta_id "
                       "LEFT JOIN vehiculos v ON v.id=t.vehiculo_id LEFT JOIN conductores c ON c.id=t.conductor_id WHERE 1=1 {rango} ORDER BY t.fecha_hora",
                   cols=[("codigo", "Viaje", "bold"), ("ruta", "Ruta", "text"), ("fecha_hora", "Salida planificada", "dt"), ("unidad", "Unidad", "text"), ("conductor", "Conductor", "text"), ("estado", "Estado", "pill")]),
    "capacitaciones": dict(titulo="Capacitaciones asignadas, completadas y pendientes", roles=["gerencia", "admin", "auditor", "seguridad"], fecha=None,
                           sql="SELECT c.titulo, COUNT(a.id) AS asignadas, SUM(CASE WHEN a.estado IN ('Completada','Aprobada') THEN 1 ELSE 0 END) AS completadas, "
                               "SUM(CASE WHEN a.estado IN ('Asignada','En progreso','No aprobada') THEN 1 ELSE 0 END) AS pendientes FROM capacitaciones c LEFT JOIN asignaciones_cap a ON a.capacitacion_id=c.id GROUP BY c.id ORDER BY c.titulo",
                           cols=[("titulo", "Capacitación", "text"), ("asignadas", "Asignadas", "text"), ("completadas", "Completadas", "text"), ("pendientes", "Pendientes", "text")]),
    "evaluaciones": dict(titulo="Resultados de evaluaciones", roles=["gerencia", "admin", "auditor", "seguridad"], fecha="a.fecha_resultado",
                         sql="SELECT c.nombres||' '||c.apellidos AS conductor, k.titulo, a.nota, a.intentos, a.estado, a.fecha_resultado FROM asignaciones_cap a JOIN conductores c ON c.id=a.conductor_id "
                             "JOIN capacitaciones k ON k.id=a.capacitacion_id WHERE a.nota IS NOT NULL {rango} ORDER BY a.fecha_resultado DESC",
                         cols=[("conductor", "Conductor", "text"), ("titulo", "Capacitación", "text"), ("nota", "Nota (%)", "text"), ("intentos", "Intentos", "text"), ("estado", "Resultado", "pill"), ("fecha_resultado", "Fecha", "date")]),
    "incumplimientos": dict(titulo="Incumplimientos por categoría y estado", roles=["gerencia", "admin", "auditor", "seguridad"], fecha="t.fecha_hora",
                            sql="SELECT t.categoria, t.estado, COUNT(*) AS cantidad FROM incumplimientos t WHERE 1=1 {rango} GROUP BY t.categoria, t.estado ORDER BY t.categoria",
                            cols=[("categoria", "Categoría", "text"), ("estado", "Estado", "pill"), ("cantidad", "Cantidad", "text")]),
    "incidentes": dict(titulo="Novedades por tipo y estado", roles=["gerencia", "admin", "auditor", "seguridad", "operaciones", "flota"], fecha="t.fecha_hora",
                       sql="SELECT t.tipo, t.estado, COUNT(*) AS cantidad FROM incidentes t WHERE 1=1 {rango} GROUP BY t.tipo, t.estado ORDER BY t.tipo",
                       cols=[("tipo", "Tipo", "text"), ("estado", "Estado", "pill"), ("cantidad", "Cantidad", "text")]),
    "mantenimientos": dict(titulo="Mantenimientos por vehículo", roles=["gerencia", "admin", "auditor", "flota"], fecha="m.fecha_programada",
                           sql="SELECT v.placa, COUNT(*) AS ordenes, SUM(m.costo) AS costo FROM mantenimientos m JOIN vehiculos v ON v.id=m.vehiculo_id WHERE 1=1 {rango} GROUP BY v.id ORDER BY v.placa",
                           cols=[("placa", "Unidad", "bold"), ("ordenes", "Órdenes", "text"), ("costo", "Costo registrado (USD)", "text")]),
    "hallazgos": dict(titulo="Hallazgos viales y su seguimiento", roles=["gerencia", "admin", "auditor", "seguridad", "operaciones"], fecha="t.fecha",
                      sql="SELECT t.codigo, r.nombre AS ruta, t.tipo, t.prioridad, t.estado, t.fecha FROM hallazgos t LEFT JOIN rutas r ON r.id=t.ruta_id WHERE 1=1 {rango} ORDER BY t.fecha DESC",
                      cols=[("codigo", "Código", "bold"), ("ruta", "Ruta", "text"), ("tipo", "Tipo", "text"), ("prioridad", "Prioridad", "pill"), ("estado", "Estado", "pill"), ("fecha", "Fecha", "date")]),
}


def reportes_permitidos():
    return {k: v for k, v in REPORTES.items() if g.user["rol"] in v["roles"]}


def correr_reporte(key):
    rp = reportes_permitidos().get(key)
    if not rp:
        abort(403 if key in REPORTES else 404)
    desde, hasta = request.args.get("desde") or "", request.args.get("hasta") or ""
    params, rango = [], ""
    if rp["fecha"]:
        if desde:
            rango += f" AND substr({rp['fecha']},1,10)>=?"
            params.append(desde)
        if hasta:
            rango += f" AND substr({rp['fecha']},1,10)<=?"
            params.append(hasta)
    rows = q(fmt(rp["sql"]).replace("{rango}", rango), params)
    periodo = "Todo el historial disponible" if not (desde or hasta) or not rp["fecha"] else f"Desde {fdate(desde) if desde else 'el inicio'} hasta {fdate(hasta) if hasta else 'hoy'}"
    return rp, rows, desde, hasta, periodo


@app.route("/reportes")
def reportes():
    perm = reportes_permitidos()
    if not perm:
        abort(403)
    key = request.args.get("r") or next(iter(perm))
    rp, rows, desde, hasta, periodo = correr_reporte(key)
    return render_template("reportes.html", perm=perm, key=key, rp=rp, rows=rows, desde=desde, hasta=hasta, periodo=periodo,
                           generado=datetime.now().strftime("%d/%m/%Y %H:%M"))


@app.get("/reportes/exportar.csv")
def reporte_csv():
    key = request.args.get("r", "")
    rp, rows, desde, hasta, periodo = correr_reporte(key)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([rp["titulo"]])
    w.writerow([f"Periodo: {periodo}", f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", f"Usuario: {g.user['nombre']}"])
    w.writerow([])
    w.writerow([c[1] for c in rp["cols"]])
    for r in rows:
        w.writerow([_plain(r, c) if r[c[0]] is not None else "No disponible" for c in rp["cols"]])
    audit("Exportación", "reportes", None, f"Exportó el reporte '{rp['titulo']}' ({periodo})")
    get_db().commit()
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=reporte_{key}_{date.today().isoformat()}.csv"})


# ============================================================ búsqueda y notificaciones
@app.route("/buscar")
def buscar():
    term = (request.args.get("q") or "").strip()
    grupos = []
    if term:
        for mod in ("conductores", "vehiculos", "rutas", "viajes", "socios", "proveedores", "documentos", "incidentes", "incumplimientos"):
            if not level(mod):
                continue
            sql, params, total, _, _ = list_query(mod, {"q": term}, 5)
            rows = q(sql, params)
            if rows:
                m = MODULES[mod]
                grupos.append(dict(mod=mod, titulo=LABELS_ROL.get(g.user["rol"], {}).get(mod, m["titulo"]), total=total, rows=rows, cols=m["columns"][:4]))
    return render_template("buscar.html", term=term, grupos=grupos)


@app.get("/notificaciones")
def notificaciones():
    return render_template("notificaciones.html", items=build_notifs())


@app.post("/notificaciones/leer")
def notif_leer():
    clave = request.form.get("clave")
    claves = [i["key"] for i in build_notifs()] if clave == "*" else [clave]
    for c in claves:
        if c:
            get_db().execute("INSERT OR IGNORE INTO notif_leidas(usuario_id,clave) VALUES (?,?)", (g.user["id"], c))
    get_db().commit()
    return jsonify(ok=True)


@app.errorhandler(403)
def e403(_):
    return render_template("error.html", codigo=403, titulo="Sin acceso", texto="Tu rol no tiene permiso para ver o hacer esto. Si lo necesitas, pide a un administrador que revise tus permisos."), 403


@app.errorhandler(404)
def e404(_):
    return render_template("error.html", codigo=404, titulo="No encontramos esa página", texto="El registro o la página ya no existe, o no tienes acceso a ella."), 404


@app.errorhandler(413)
def e413(_):
    return jsonify(ok=False, message="El archivo supera los 5 MB."), 413


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    dbm.init_db(DB_PATH, reset=reset)
    print("\n  Rutas del Pacífico listo en  http://127.0.0.1:5000\n  (datos de demostración: contraseña de las cuentas demo = Demo2026!)\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
else:
    dbm.init_db(DB_PATH)
