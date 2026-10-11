"""Esquema SQL (SQLite) y datos de demostración para Rutas del Pacífico.

TODOS los datos sembrados son FICTICIOS y existen solo para demostrar el sistema.
"""
import sqlite3
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS socios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL, tipo_id TEXT, identificacion TEXT,
  telefono TEXT, email TEXT, estado TEXT NOT NULL DEFAULT 'Activo',
  fecha_registro TEXT, observaciones TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS conductores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, nombres TEXT NOT NULL, apellidos TEXT NOT NULL,
  tipo_id TEXT, identificacion TEXT, telefono TEXT, email TEXT, fecha_ingreso TEXT,
  estado TEXT NOT NULL DEFAULT 'Activo', licencia_tipo TEXT, licencia_vence TEXT,
  observaciones TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS personal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, nombres TEXT NOT NULL, area TEXT, cargo TEXT,
  telefono TEXT, email TEXT, estado TEXT NOT NULL DEFAULT 'Activo',
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS proveedores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL, servicio TEXT, contacto TEXT,
  telefono TEXT, email TEXT, estado TEXT NOT NULL DEFAULT 'Activo',
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS vehiculos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, placa TEXT UNIQUE NOT NULL, tipo TEXT, marca TEXT, modelo TEXT,
  anio INTEGER, capacidad INTEGER, socio_id INTEGER REFERENCES socios(id),
  estado TEXT NOT NULL DEFAULT 'Disponible', ultima_revision TEXT, prox_mantenimiento TEXT,
  observaciones TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS rutas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL, origen TEXT NOT NULL, destino TEXT NOT NULL,
  paradas TEXT, frecuencia TEXT, duracion_horas REAL, estado TEXT NOT NULL DEFAULT 'Activa',
  observaciones TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS viajes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, ruta_id INTEGER NOT NULL REFERENCES rutas(id),
  fecha_hora TEXT NOT NULL, vehiculo_id INTEGER REFERENCES vehiculos(id),
  conductor_id INTEGER REFERENCES conductores(id), estado TEXT NOT NULL DEFAULT 'Planificado',
  hora_real_salida TEXT, hora_real_llegada TEXT, observaciones TEXT, motivo_cambio TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS capacitaciones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL, tema TEXT, tipo TEXT, descripcion TEXT,
  duracion_min INTEGER, responsable TEXT, nota_minima INTEGER DEFAULT 70, recurso_url TEXT,
  estado TEXT NOT NULL DEFAULT 'Borrador',
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS preguntas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  capacitacion_id INTEGER NOT NULL REFERENCES capacitaciones(id) ON DELETE CASCADE,
  texto TEXT NOT NULL, opcion_a TEXT NOT NULL, opcion_b TEXT NOT NULL,
  opcion_c TEXT, opcion_d TEXT, correcta TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asignaciones_cap (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  capacitacion_id INTEGER NOT NULL REFERENCES capacitaciones(id) ON DELETE CASCADE,
  conductor_id INTEGER NOT NULL REFERENCES conductores(id),
  fecha_asignacion TEXT, fecha_limite TEXT, estado TEXT NOT NULL DEFAULT 'Asignada',
  nota INTEGER, intentos INTEGER NOT NULL DEFAULT 0, fecha_resultado TEXT,
  UNIQUE(capacitacion_id, conductor_id)
);
CREATE TABLE IF NOT EXISTS intentos_eval (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asignacion_id INTEGER NOT NULL REFERENCES asignaciones_cap(id) ON DELETE CASCADE,
  fecha TEXT, nota INTEGER, aprobado INTEGER
);
CREATE TABLE IF NOT EXISTS incumplimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, fecha_hora TEXT NOT NULL,
  conductor_id INTEGER REFERENCES conductores(id), vehiculo_id INTEGER REFERENCES vehiculos(id),
  viaje_id INTEGER REFERENCES viajes(id), categoria TEXT NOT NULL, lugar TEXT,
  descripcion TEXT NOT NULL, fuente TEXT, severidad TEXT, estado TEXT NOT NULL DEFAULT 'Reportado',
  responsable TEXT, decision TEXT, accion TEXT, fecha_cierre TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS incidentes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, fecha_hora TEXT NOT NULL, tipo TEXT NOT NULL,
  ruta_id INTEGER REFERENCES rutas(id), lugar TEXT,
  vehiculo_id INTEGER REFERENCES vehiculos(id), conductor_id INTEGER REFERENCES conductores(id),
  urgencia TEXT, descripcion TEXT NOT NULL, responsable TEXT,
  estado TEXT NOT NULL DEFAULT 'Nuevo', acciones TEXT, causa TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS hallazgos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, fecha TEXT NOT NULL, ruta_id INTEGER REFERENCES rutas(id),
  tramo TEXT, tipo TEXT, prioridad TEXT, descripcion TEXT NOT NULL, responsable TEXT,
  estado TEXT NOT NULL DEFAULT 'Abierto',
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS mantenimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL, vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id),
  tipo TEXT NOT NULL, proveedor_id INTEGER REFERENCES proveedores(id), descripcion TEXT,
  fecha_programada TEXT, fecha_recepcion TEXT, fecha_entrega TEXT, costo REAL,
  estado TEXT NOT NULL DEFAULT 'Solicitado', observaciones TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL, descripcion TEXT,
  conductor_id INTEGER REFERENCES conductores(id), vehiculo_id INTEGER REFERENCES vehiculos(id),
  socio_id INTEGER REFERENCES socios(id),
  fecha_emision TEXT, fecha_vencimiento TEXT,
  validacion TEXT NOT NULL DEFAULT 'Pendiente de revisión', validado_por TEXT, validado_en TEXT,
  archivo TEXT,
  creado_por TEXT, creado_en TEXT, actualizado_por TEXT, actualizado_en TEXT
);
CREATE TABLE IF NOT EXISTS catalogos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  categoria TEXT NOT NULL, valor TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'Activo',
  UNIQUE(categoria, valor)
);
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  rol TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'Activo',
  conductor_id INTEGER REFERENCES conductores(id), socio_id INTEGER REFERENCES socios(id),
  creado_en TEXT
);
CREATE TABLE IF NOT EXISTS auditoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL, usuario TEXT, accion TEXT, modulo TEXT, registro INTEGER,
  resumen TEXT, resultado TEXT DEFAULT 'Correcto', motivo TEXT
);
CREATE TABLE IF NOT EXISTS notif_leidas (
  usuario_id INTEGER NOT NULL, clave TEXT NOT NULL, PRIMARY KEY (usuario_id, clave)
);
"""

CATALOGOS = {
    "tipo_documento": ["Licencia de conducir", "Certificado médico", "Matrícula", "Revisión técnica vehicular",
                       "Póliza de seguro", "Permiso de operación", "Contrato / convenio", "Otro"],
    "tipo_vehiculo": ["Bus interprovincial", "Bus de dos pisos", "Minibús", "Furgoneta"],
    "tema_capacitacion": ["Inducción a la seguridad vial", "Manejo defensivo", "Exceso de velocidad",
                          "Distracciones al volante", "Uso del cinturón de seguridad", "Distancia de seguimiento",
                          "Cansancio y somnolencia", "Pausas y descanso", "Conducción en condiciones adversas",
                          "Procedimiento posterior a un incidente", "Inspección básica antes del viaje",
                          "Reconocer, evaluar y actuar ante peligros", "Paradas autorizadas y rutas",
                          "Uso responsable del teléfono", "Comunicación y reporte de novedades",
                          "Procedimientos internos de emergencia"],
    "categoria_incumplimiento": ["Exceso de velocidad", "Uso de teléfono o distracción", "Cinturón de seguridad",
                                 "Parada no autorizada", "Incumplimiento de ruta u horario",
                                 "Incumplimiento de pausas o descansos", "Somnolencia observada",
                                 "Fumar en lugar prohibido", "Incumplimiento de normas internas", "Otro"],
    "tipo_incidente": ["Falla mecánica", "Avería eléctrica", "Neumático dañado", "Obstrucción o cierre de vía",
                       "Condiciones climáticas adversas", "Tráfico o retraso", "Accidente o siniestro vial",
                       "Situación de inseguridad", "Problema con una parada", "Otro"],
    "tipo_hallazgo": ["Obstáculo en la vía", "Daño en la calzada", "Zona de riesgo", "Cierre de vía",
                      "Señalización deficiente", "Otro"],
}


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db(path, reset=False):
    import os
    if reset and os.path.exists(path):
        os.remove(path)
    db = connect(path)
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        seed(db)
    db.commit()
    db.close()


def seed(db):
    hoy = date.today()
    d = lambda n: (hoy + timedelta(days=n)).isoformat()
    dt = lambda n, h: f"{d(n)}T{h}"
    ahora = f"{hoy.isoformat()}T07:00"
    pw = generate_password_hash("Demo2026!")
    SYS = "Datos de demostración"

    for cat, vals in CATALOGOS.items():
        for v in vals:
            db.execute("INSERT INTO catalogos(categoria,valor) VALUES (?,?)", (cat, v))

    def ins(table, **kw):
        if table not in ("usuarios", "catalogos", "auditoria"):
            kw.setdefault("creado_por", SYS)
            kw.setdefault("creado_en", ahora)
        cols = ",".join(kw)
        cur = db.execute(f"INSERT INTO {table}({cols}) VALUES ({','.join('?' * len(kw))})", list(kw.values()))
        return cur.lastrowid

    # ---- Socios
    socios = ["Marco Villamar Ortiz", "Sandra Quinde Mora", "Hermanos Zambrano (demo)", "Jorge Intriago Peña",
              "Compañía Costa Viva (demo)", "Patricia Loor Segarra"]
    sid = []
    for i, n in enumerate(socios, 1):
        sid.append(ins("socios", codigo=f"SOC-{i:04d}", nombre=n, tipo_id="Cédula" if i not in (3, 5) else "RUC",
                       identificacion=f"09{i:02d}0000{i:02d}", telefono=f"099000{i:04d}",
                       email=f"socio{i}@demo.test", estado="Activo" if i != 6 else "Inactivo",
                       fecha_registro=d(-900 + i * 40)))

    # ---- Conductores
    nombres = [("Luis Alberto", "Mendoza Cedeño"), ("Carlos Andrés", "Reyes Macías"), ("José Manuel", "Alvarado Pinargote"),
               ("Fabián Esteban", "Cevallos Rivas"), ("Wilson Enrique", "Párraga Vera"), ("Diego Armando", "Tigua Bravo"),
               ("Néstor Iván", "Baque Salazar"), ("Edison Patricio", "Moreira Cobos"), ("Ángel Gabriel", "Pilay Suárez"),
               ("Byron Xavier", "Ortega Lucas"), ("Henry Fernando", "Franco Mero"), ("Oswaldo Rafael", "Chávez Toala")]
    lic_vence = [220, 15, 380, -12, 540, 25, 700, 95, 260, 410, 120, 600]
    est_c = ["Activo"] * 9 + ["Suspendido", "Pendiente de validación", "Activo"]
    cid = []
    for i, (n, a) in enumerate(nombres, 1):
        cid.append(ins("conductores", codigo=f"CND-{i:04d}", nombres=n, apellidos=a, tipo_id="Cédula",
                       identificacion=f"0999{i:06d}", telefono=f"098000{i:04d}", email=f"conductor{i}@demo.test",
                       fecha_ingreso=d(-1500 + i * 70), estado=est_c[i - 1],
                       licencia_tipo="Tipo E" if i == 7 else "Tipo D", licencia_vence=d(lic_vence[i - 1]),
                       observaciones="Observación administrativa de demostración." if i == 10 else None))

    # ---- Personal
    pers = [("Andrea Salazar Mora", "Administración", "Asistente documental"), ("Ricardo Bajaña Ponce", "Operaciones", "Despachador"),
            ("Mónica Zúñiga Lara", "Seguridad vial", "Analista de seguridad"), ("Pablo Neira Gómez", "Taller", "Jefe de taller")]
    for i, (n, a, c) in enumerate(pers, 1):
        ins("personal", codigo=f"PER-{i:04d}", nombres=n, area=a, cargo=c, telefono=f"097000{i:04d}",
            email=f"personal{i}@demo.test")

    # ---- Proveedores
    provs = [("Taller Mecánico El Pacífico (demo)", "Mantenimiento"), ("Llantas y Servicios Costa (demo)", "Llantas"),
             ("Repuestos Diésel Guayas (demo)", "Repuestos"), ("Asistencia Vial 24h (demo)", "Asistencia")]
    pid = []
    for i, (n, s) in enumerate(provs, 1):
        pid.append(ins("proveedores", codigo=f"PRV-{i:04d}", nombre=n, servicio=s, contacto="Contacto demo",
                       telefono=f"042000{i:04d}", email=f"proveedor{i}@demo.test"))

    # ---- Vehículos
    veh = [("GBA-1021", "Bus interprovincial", "Hino", "AK8", 2019, 42), ("GBC-2034", "Bus interprovincial", "Mercedes-Benz", "O-500", 2020, 44),
           ("GCD-3045", "Bus de dos pisos", "Scania", "K410", 2021, 52), ("GDE-4056", "Bus interprovincial", "Volkswagen", "17.230", 2018, 42),
           ("GEF-5067", "Minibús", "Hino", "FC", 2022, 28), ("GFG-6078", "Bus interprovincial", "Mercedes-Benz", "OF-1721", 2017, 40),
           ("GGH-7089", "Bus interprovincial", "Scania", "K360", 2023, 46), ("GHJ-8090", "Bus interprovincial", "Hino", "RK8", 2016, 40),
           ("GJK-9101", "Bus de dos pisos", "Volvo", "B380R", 2022, 50), ("GKL-1112", "Minibús", "Chevrolet", "NQR", 2015, 26)]
    est_v = ["Disponible"] * 7 + ["En mantenimiento", "Fuera de servicio", "Inactivo"]
    vid = []
    for i, (p, t, m, mo, a, cap) in enumerate(veh, 1):
        vid.append(ins("vehiculos", codigo=f"UN-{i:03d}", placa=p, tipo=t, marca=m, modelo=mo, anio=a, capacidad=cap,
                       socio_id=sid[(i - 1) % 5], estado=est_v[i - 1], ultima_revision=d(-60 - i * 9),
                       prox_mantenimiento=d([40, 6, 75, 20, -4, 110, 55, -10, 200, 300][i - 1])))

    # ---- Rutas
    rutas = [("RT-001", "Guayaquil - Machala", "Guayaquil", "Machala", "Naranjal, Pasaje", "Cada 60 min (05:00 a 20:00)", 3.5),
             ("RT-002", "Guayaquil - Manta", "Guayaquil", "Manta", "Jipijapa, Montecristi", "Cada 90 min (05:30 a 19:00)", 4.5),
             ("RT-003", "Guayaquil - Quito", "Guayaquil", "Quito", "Babahoyo, Quevedo, Santo Domingo", "Salidas a las 08:00 y 21:00", 8.5),
             ("RT-004", "Guayaquil - Esmeraldas", "Guayaquil", "Esmeraldas", "Quevedo, Santo Domingo", "Salida diaria 20:30", 9.0),
             ("RT-005", "Machala - Loja", "Machala", "Loja", "Santa Rosa, Catacocha", "Salidas a las 06:00 y 14:00", 5.0),
             ("RT-006", "Guayaquil - Salinas", "Guayaquil", "Salinas", "Progreso, Playas", "Cada 45 min (05:00 a 19:00)", 2.5)]
    rid = []
    for c, n, o, de, pa, fr, du in rutas:
        rid.append(ins("rutas", codigo=c, nombre=n, origen=o, destino=de, paradas=pa, frecuencia=fr,
                       duracion_horas=du, estado="Activa", observaciones="Horarios y duraciones de demostración."))
    db.execute("UPDATE rutas SET estado='Inactiva' WHERE codigo='RT-004'")

    # ---- Viajes (sin conflictos: cada unidad/conductor 1 viaje por día)
    av = [vid[i] for i in range(7)]
    ac = [cid[i] for i in (0, 1, 2, 4, 5, 6, 7)]
    horas = ["06:00", "14:00"]
    rutas_usables = [rid[0], rid[1], rid[2], rid[4], rid[5]]
    vj = []
    k = 0
    for dia in range(-3, 4):
        for h in range(2):
            est = "Finalizado" if dia < 0 else ("En curso" if dia == 0 and h == 0 else ("Confirmado" if dia <= 1 else "Planificado"))
            v, c = av[k % 7], ac[k % 7]
            sal = dt(dia, horas[h]) if est in ("Finalizado", "En curso") else None
            vj.append(ins("viajes", codigo=f"VJ-{k + 1:04d}", ruta_id=rutas_usables[k % 5], fecha_hora=dt(dia, horas[h]),
                          vehiculo_id=v, conductor_id=c, estado=est, hora_real_salida=sal,
                          hora_real_llegada=dt(dia, "11:00") if est == "Finalizado" else None))
            k += 1
    db.execute("UPDATE viajes SET estado='Con novedad', observaciones='Retraso por tráfico en la vía.' WHERE id=?", (vj[1],))
    db.execute("UPDATE viajes SET estado='Cancelado', motivo_cambio='Unidad reasignada por mantenimiento.' WHERE id=?", (vj[12],))
    ins("viajes", codigo=f"VJ-{k + 1:04d}", ruta_id=rid[2], fecha_hora=dt(2, "21:00"), estado="Planificado",
        observaciones="Pendiente de asignar unidad y conductor.")

    # ---- Documentos
    def doc(tipo, v, **tit):
        ins("documentos", tipo=tipo, fecha_emision=d(-365), fecha_vencimiento=d(v) if v is not None else None,
            validacion="Validado", validado_por="Mónica Zúñiga", validado_en=ahora, **tit)
    for i, c in enumerate(cid):
        doc("Licencia de conducir", lic_vence[i], conductor_id=c)
        doc("Certificado médico", [60, 200, 12, 330, -20, 150, 90, 28, 400, 20, 250, 140][i], conductor_id=c)
    for i, v in enumerate(vid):
        doc("Matrícula", [300, 25, 410, 150, 200, -5, 330, 90, 500, 60][i], vehiculo_id=v)
        doc("Revisión técnica vehicular", [120, 18, 260, 8, 210, 140, 340, -30, 480, 75][i], vehiculo_id=v)
        doc("Póliza de seguro", [180, 220, 90, 55, 300, 27, 400, 130, 520, 16][i], vehiculo_id=v)
    ins("documentos", tipo="Contrato / convenio", descripcion="Convenio de socio (demo)", socio_id=sid[0],
        fecha_emision=d(-400), fecha_vencimiento=None, validacion="Pendiente de revisión")
    ins("documentos", tipo="Permiso de operación", descripcion="Copia ilegible, se solicita nueva carga",
        vehiculo_id=vid[3], fecha_emision=d(-200), fecha_vencimiento=d(160), validacion="Rechazado")
    db.execute("UPDATE documentos SET validacion='Pendiente de revisión', validado_por=NULL WHERE id IN (7,40)")

    # ---- Capacitaciones
    caps = [("Manejo defensivo", "Manejo defensivo", "Cuestionario", 45, "Publicada"),
            ("Cansancio, somnolencia y pausas", "Cansancio y somnolencia", "Charla", 30, "Publicada"),
            ("Inspección básica antes del viaje", "Inspección básica antes del viaje", "Cuestionario", 40, "Publicada"),
            ("Procedimiento posterior a un incidente", "Procedimiento posterior a un incidente", "Video", 25, "Publicada"),
            ("Uso responsable del teléfono al conducir", "Uso responsable del teléfono", "Documento", 20, "Borrador"),
            ("Inducción a la seguridad vial", "Inducción a la seguridad vial", "Charla", 60, "Archivada")]
    capid = []
    for i, (t, te, ty, du, es) in enumerate(caps, 1):
        capid.append(ins("capacitaciones", codigo=f"CAP-{i:04d}", titulo=t, tema=te, tipo=ty,
                         descripcion="Contenido de demostración; adaptar a políticas aprobadas por la cooperativa.",
                         duracion_min=du, responsable="Mónica Zúñiga", nota_minima=70, estado=es,
                         recurso_url="https://example.com/recurso-demo" if ty in ("Video", "Documento") else None))
    qs = {0: [("¿Cuál es el objetivo principal del manejo defensivo?", "Llegar más rápido", "Anticipar riesgos y evitar colisiones", "Reducir el consumo de combustible", "Adelantar con seguridad", "B"),
              ("Para mantener una distancia de seguimiento segura conviene:", "Pegarse al vehículo de adelante", "Dejar un intervalo de tiempo suficiente que aumente con lluvia o poca visibilidad", "Usar solo las luces altas", "Mirar únicamente el espejo", "B"),
              ("Si aparece un peligro adelante, la secuencia correcta es:", "Ignorar y acelerar", "Reconocer, evaluar y actuar", "Tocar la bocina y no frenar", "Apagar las luces", "B")],
          2: [("Antes de iniciar el viaje se debe revisar como mínimo:", "Solo el volumen de la radio", "Neumáticos, luces, frenos y fluidos", "Únicamente la limpieza exterior", "Nada, si la unidad salió ayer", "B"),
              ("Si se detecta una falla que afecta la seguridad:", "Se inicia el viaje y se reporta al llegar", "No se inicia el viaje y se reporta la novedad", "Se espera a que empeore", "Se ignora", "B")]}
    for ci, lst in qs.items():
        for t, a, b, c, dd, r in lst:
            db.execute("INSERT INTO preguntas(capacitacion_id,texto,opcion_a,opcion_b,opcion_c,opcion_d,correcta) VALUES (?,?,?,?,?,?,?)",
                       (capid[ci], t, a, b, c, dd, r))
    for i, c in enumerate(cid):
        if est_c[i] != "Activo":
            continue
        db.execute("INSERT INTO asignaciones_cap(capacitacion_id,conductor_id,fecha_asignacion,fecha_limite,estado,nota,intentos,fecha_resultado) VALUES (?,?,?,?,?,?,?,?)",
                   (capid[0], c, d(-30), d(-5) if i == 3 else d(20), "Aprobada" if i % 3 == 0 else ("No aprobada" if i == 4 else "Asignada"),
                    90 if i % 3 == 0 else (50 if i == 4 else None), 1 if i % 3 == 0 or i == 4 else 0, d(-10) if i % 3 == 0 or i == 4 else None))
        db.execute("INSERT INTO asignaciones_cap(capacitacion_id,conductor_id,fecha_asignacion,fecha_limite,estado,nota,intentos,fecha_resultado) VALUES (?,?,?,?,?,?,?,?)",
                   (capid[1], c, d(-15), d(15), "Completada" if i % 2 == 0 else "Asignada", None, 0, d(-3) if i % 2 == 0 else None))
        if i < 5:
            db.execute("INSERT INTO asignaciones_cap(capacitacion_id,conductor_id,fecha_asignacion,fecha_limite,estado) VALUES (?,?,?,?,?)",
                       (capid[2], c, d(-2), d(25), "Asignada"))

    # ---- Incumplimientos
    cats = ["Exceso de velocidad", "Uso de teléfono o distracción", "Parada no autorizada", "Incumplimiento de ruta u horario",
            "Incumplimiento de pausas o descansos", "Cinturón de seguridad", "Exceso de velocidad", "Somnolencia observada"]
    ests = ["Confirmado", "En revisión", "Reportado", "Cerrado", "Descartado", "Reportado", "Confirmado", "En revisión"]
    dias = [-8, -14, -2, -40, -33, -1, -75, -20]
    for i in range(8):
        ins("incumplimientos", codigo=f"INC-{i + 1:04d}", fecha_hora=dt(dias[i], "10:30"), conductor_id=cid[i % 7],
            vehiculo_id=vid[i % 7], categoria=cats[i], lugar="Referencia de demostración (tramo de ruta)",
            descripcion="Descripción objetiva de demostración del hecho reportado.", fuente="Reporte del despachador",
            severidad=["Media", "Alta", "Baja", "Media", "Baja", "Media", "Alta", "Alta"][i], estado=ests[i],
            responsable="Mónica Zúñiga" if ests[i] != "Reportado" else None,
            decision="Se revisó la evidencia y se confirmó el hecho." if ests[i] in ("Confirmado", "Cerrado") else (
                "Evidencia insuficiente; se descarta." if ests[i] == "Descartado" else None),
            accion="Capacitación de refuerzo asignada." if ests[i] in ("Confirmado", "Cerrado") else None,
            fecha_cierre=d(dias[i] + 6) if ests[i] in ("Cerrado", "Descartado") else None)

    # ---- Incidentes
    inc = [("Falla mecánica", -3, "En atención", "Alta"), ("Neumático dañado", -12, "Resuelto", "Media"),
           ("Tráfico o retraso", -1, "Nuevo", "Baja"), ("Obstrucción o cierre de vía", -25, "Cerrado", "Alta"),
           ("Condiciones climáticas adversas", -50, "Cerrado", "Media"), ("Avería eléctrica", -95, "Cerrado", "Media"),
           ("Falla mecánica", 0, "Nuevo", "Alta")]
    for i, (t, dd, es, ur) in enumerate(inc):
        ins("incidentes", codigo=f"NOV-{i + 1:04d}", fecha_hora=dt(dd, "15:10"), tipo=t, ruta_id=rid[i % 3],
            lugar="Referencia descrita (demostración)", vehiculo_id=vid[i % 7], conductor_id=cid[i % 7], urgencia=ur,
            descripcion="Descripción de demostración del evento en ruta.", estado=es,
            responsable="Pablo Neira" if es != "Nuevo" else None,
            acciones="Se coordinó asistencia con proveedor." if es != "Nuevo" else None)

    # ---- Hallazgos
    for i, (t, p, es) in enumerate([("Daño en la calzada", "Alta", "Abierto"), ("Señalización deficiente", "Media", "En seguimiento"),
                                    ("Zona de riesgo", "Alta", "Abierto"), ("Obstáculo en la vía", "Baja", "Resuelto")], 1):
        ins("hallazgos", codigo=f"HV-{i:04d}", fecha=d(-i * 6), ruta_id=rid[i % 3], tramo="Tramo de demostración",
            tipo=t, prioridad=p, descripcion="Hallazgo de demostración durante una inspección.",
            responsable="Mónica Zúñiga", estado=es)

    # ---- Mantenimientos
    mm = [(7, "Correctivo", "En ejecución", -4, 1400), (0, "Preventivo", "Aprobado", 12, 380), (1, "Preventivo", "Solicitado", 6, None),
          (3, "Preventivo", "Finalizado", -45, 420), (4, "Correctivo", "Finalizado", -80, 960), (8, "Correctivo", "Esperando repuesto", -9, 2100)]
    for i, (vi, t, es, dd, co) in enumerate(mm, 1):
        ins("mantenimientos", codigo=f"MT-{i:04d}", vehiculo_id=vid[vi], tipo=t, proveedor_id=pid[i % 2],
            descripcion="Trabajo de demostración.", fecha_programada=d(dd), fecha_recepcion=d(dd) if es in ("En ejecución", "Finalizado", "Esperando repuesto") else None,
            fecha_entrega=d(dd + 5) if es == "Finalizado" else None, costo=co, estado=es)

    # ---- Usuarios demo
    users = [("Administrador Demo", "admin@rutaspacifico.demo", "admin", None, None),
             ("Gerencia Demo", "gerencia@rutaspacifico.demo", "gerencia", None, None),
             ("Despachador Demo", "operaciones@rutaspacifico.demo", "operaciones", None, None),
             ("Mónica Zúñiga", "seguridad@rutaspacifico.demo", "seguridad", None, None),
             ("Pablo Neira", "flota@rutaspacifico.demo", "flota", None, None),
             ("Andrea Salazar", "administrativo@rutaspacifico.demo", "administrativo", None, None),
             ("Luis Mendoza", "conductor@rutaspacifico.demo", "conductor", cid[0], None),
             ("Marco Villamar", "socio@rutaspacifico.demo", "socio", None, sid[0]),
             ("Auditor Demo", "auditor@rutaspacifico.demo", "auditor", None, None)]
    for n, e, r, c, s in users:
        ins("usuarios", nombre=n, email=e, password_hash=pw, rol=r, conductor_id=c, socio_id=s, creado_en=ahora)

    ins("auditoria", fecha=ahora, usuario=SYS, accion="Carga inicial", modulo="sistema", registro=None,
        resumen="Se cargaron datos de demostración (ficticios).", resultado="Correcto")
