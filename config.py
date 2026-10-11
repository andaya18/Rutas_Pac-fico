"""Definición declarativa de módulos, campos, permisos y navegación.

Agregar un módulo nuevo = agregar un diccionario aquí (la interfaz CRUD se genera sola).
"""

ROLES = {
    "admin": "Administrador del sistema", "gerencia": "Gerencia", "operaciones": "Operaciones y despacho",
    "seguridad": "Seguridad vial", "flota": "Flota y mantenimiento", "administrativo": "Personal administrativo",
    "conductor": "Conductor", "socio": "Socio / propietario", "auditor": "Auditor",
}

# Etiquetas de menú que cambian según el rol
LABELS_ROL = {
    "conductor": {"viajes": "Mis viajes", "capacitaciones": "Mis capacitaciones", "documentos": "Mis documentos",
                  "incidentes": "Reportar novedad", "conductores": "Mi perfil", "incumplimientos": "Mis observaciones"},
    "socio": {"vehiculos": "Mis unidades", "viajes": "Viajes de mis unidades", "documentos": "Documentos",
              "mantenimientos": "Mantenimiento", "socios": "Mi perfil"},
}

CAT = "catalogo"  # marcador: opciones tomadas de la tabla catalogos


def F(name, label, t="text", req=False, opts=None, fk=None, cat=None, default=None, help=None,
      full=False, restricted=False, hidden_form=False):
    return dict(name=name, label=label, t=t, req=req, opts=opts, fk=fk, cat=cat, default=default, help=help,
                full=full, restricted=restricted, hidden_form=hidden_form)


# Etiqueta SQL para mostrar un registro de cada tabla referenciada
FK_LABEL = {
    "conductores": "nombres||' '||apellidos||CASE WHEN estado<>'Activo' THEN ' ('||estado||')' ELSE '' END",
    "vehiculos": "placa||' - '||COALESCE(tipo,'')||CASE WHEN estado<>'Disponible' AND estado<>'Asignado' THEN ' ('||estado||')' ELSE '' END",
    "socios": "nombre",
    "rutas": "nombre",
    "proveedores": "nombre",
    "viajes": "codigo",
    "capacitaciones": "titulo",
    "usuarios": "nombre",
}

EST_ACTIVO = ["Activo", "Inactivo"]
SEVERIDAD = ["Baja", "Media", "Alta", "Crítica"]

# Un viaje en estos estados no consume la unidad/conductor para chequeos de conflicto
VIAJE_LIBRE = ("Cancelado", "Finalizado")

MODULES = {}

# ----------------------------------------------------------------- PERSONAS
MODULES["conductores"] = dict(
    titulo="Conductores", singular="conductor", grupo="Personas", icon="user", prefijo="CND",
    subtitulo="Registro de conductores, licencias y su historial de capacitación y seguridad.",
    fields=[
        F("codigo", "Código interno", help="Déjalo vacío para generarlo automáticamente."),
        F("nombres", "Nombres", req=True), F("apellidos", "Apellidos", req=True),
        F("tipo_id", "Tipo de identificación", "select", req=True, opts=["Cédula", "Pasaporte"], default="Cédula"),
        F("identificacion", "Número de identificación", req=True, help="Solo números para cédula (10 dígitos)."),
        F("telefono", "Teléfono", "tel"), F("email", "Correo electrónico", "email"),
        F("fecha_ingreso", "Fecha de ingreso", "date", default="today"),
        F("estado", "Estado", "select", req=True, opts=["Activo", "Inactivo", "Suspendido", "Pendiente de validación"], default="Activo"),
        F("licencia_tipo", "Tipo de licencia", "select", req=True, opts=["Tipo C", "Tipo D", "Tipo E"], default="Tipo D"),
        F("licencia_vence", "La licencia vence el", "date", req=True),
        F("observaciones", "Observaciones administrativas", "textarea", full=True, restricted=True),
    ],
    columns=[("codigo", "Código", "bold"), ("nombre", "Conductor", "two", "licencia_tipo"),
             ("identificacion", "Identificación", "mask"), ("licencia_vence", "Licencia vence", "date_warn"),
             ("estado", "Estado", "pill")],
    extra={"nombre": "nombres||' '||apellidos"},
    search=["codigo", "nombres", "apellidos", "identificacion"], filters=["estado", "licencia_tipo"],
    kpis=[("Total de conductores", None, "blue", "user"),
          ("Licencias por vencer (30 días)", "licencia_vence BETWEEN '{hoy}' AND '{hoy30}'", "warn", "alert"),
          ("Suspendidos o pendientes", "estado IN ('Suspendido','Pendiente de validación')", "danger", "x")],
    states=["Activo", "Inactivo", "Suspendido", "Pendiente de validación"], reason_states=["Suspendido", "Inactivo"],
    default_sort=("apellidos", "asc"),
    related=[
        ("Documentos", "SELECT tipo, fecha_vencimiento, ({vig}) AS vigencia, validacion FROM documentos WHERE conductor_id=:id ORDER BY fecha_vencimiento",
         [("tipo", "Documento", "text"), ("fecha_vencimiento", "Vence", "date"), ("vigencia", "Vigencia", "pill"), ("validacion", "Validación", "pill")]),
        ("Viajes", "SELECT v.codigo, v.fecha_hora, r.nombre AS ruta, v.estado FROM viajes v JOIN rutas r ON r.id=v.ruta_id WHERE v.conductor_id=:id ORDER BY v.fecha_hora DESC LIMIT 20",
         [("codigo", "Viaje", "bold"), ("fecha_hora", "Salida", "dt"), ("ruta", "Ruta", "text"), ("estado", "Estado", "pill")]),
        ("Capacitaciones", "SELECT c.titulo, a.fecha_limite, CASE WHEN a.estado IN ('Asignada','En progreso') AND a.fecha_limite<'{hoy}' THEN 'Vencida' ELSE a.estado END AS estado, a.nota FROM asignaciones_cap a JOIN capacitaciones c ON c.id=a.capacitacion_id WHERE a.conductor_id=:id ORDER BY a.fecha_limite",
         [("titulo", "Capacitación", "text"), ("fecha_limite", "Fecha límite", "date"), ("estado", "Estado", "pill"), ("nota", "Nota", "text")]),
        ("Seguridad", "SELECT codigo, fecha_hora, categoria, estado FROM incumplimientos WHERE conductor_id=:id {solo_confirmados} ORDER BY fecha_hora DESC",
         [("codigo", "Registro", "bold"), ("fecha_hora", "Fecha", "dt"), ("categoria", "Categoría", "text"), ("estado", "Estado", "pill")]),
    ],
)

MODULES["personal"] = dict(
    titulo="Personal", singular="persona", grupo="Personas", icon="users", prefijo="PER",
    subtitulo="Personal administrativo y operativo que no conduce unidades.",
    fields=[F("codigo", "Código interno", help="Déjalo vacío para generarlo automáticamente."),
            F("nombres", "Nombres y apellidos", req=True), F("area", "Área", "select", opts=["Administración", "Operaciones", "Seguridad vial", "Taller", "Gerencia", "Otra"]),
            F("cargo", "Cargo"), F("telefono", "Teléfono", "tel"), F("email", "Correo electrónico", "email"),
            F("estado", "Estado", "select", req=True, opts=EST_ACTIVO, default="Activo")],
    columns=[("codigo", "Código", "bold"), ("nombres", "Nombre", "two", "cargo"), ("area", "Área", "text"),
             ("telefono", "Teléfono", "text"), ("estado", "Estado", "pill")],
    search=["codigo", "nombres", "cargo"], filters=["area", "estado"],
    kpis=[("Total de personal", None, "blue", "users"), ("Activos", "estado='Activo'", "blue", "check"), ("Inactivos", "estado='Inactivo'", "danger", "x")],
    states=EST_ACTIVO,
)

MODULES["socios"] = dict(
    titulo="Socios y propietarios", singular="socio", grupo="Personas", icon="handshake", prefijo="SOC",
    subtitulo="Socios o propietarios y las unidades vinculadas a cada uno.",
    fields=[F("codigo", "Código de socio", help="Déjalo vacío para generarlo automáticamente."),
            F("nombre", "Nombres o razón social", req=True),
            F("tipo_id", "Tipo de identificación", "select", opts=["Cédula", "RUC", "Pasaporte"], default="Cédula"),
            F("identificacion", "Identificación"), F("telefono", "Teléfono", "tel"), F("email", "Correo electrónico", "email"),
            F("estado", "Estado", "select", req=True, opts=EST_ACTIVO, default="Activo"),
            F("fecha_registro", "Fecha de registro", "date", default="today"),
            F("observaciones", "Observaciones", "textarea", full=True)],
    columns=[("codigo", "Código", "bold"), ("nombre", "Socio / propietario", "two", "email"),
             ("identificacion", "Identificación", "mask"), ("unidades", "Unidades", "text"), ("estado", "Estado", "pill")],
    extra={"unidades": "(SELECT COUNT(*) FROM vehiculos v WHERE v.socio_id=t.id)"},
    search=["codigo", "nombre", "identificacion"], filters=["estado"],
    kpis=[("Total de socios", None, "blue", "handshake"), ("Con unidades vinculadas", "id IN (SELECT socio_id FROM vehiculos WHERE socio_id IS NOT NULL)", "blue", "bus"),
          ("Inactivos", "estado='Inactivo'", "danger", "x")],
    states=EST_ACTIVO,
    related=[("Unidades", "SELECT placa, tipo, marca, estado FROM vehiculos WHERE socio_id=:id ORDER BY placa",
              [("placa", "Placa", "bold"), ("tipo", "Tipo", "text"), ("marca", "Marca", "text"), ("estado", "Estado", "pill")])],
)

MODULES["proveedores"] = dict(
    titulo="Proveedores", singular="proveedor", grupo="Personas", icon="wrench", prefijo="PRV",
    subtitulo="Talleres y empresas que prestan servicios a la cooperativa.",
    fields=[F("codigo", "Código", help="Déjalo vacío para generarlo automáticamente."), F("nombre", "Nombre o razón social", req=True),
            F("servicio", "Servicio", "select", opts=["Mantenimiento", "Repuestos", "Llantas", "Asistencia", "Limpieza", "Otro"]),
            F("contacto", "Persona de contacto"), F("telefono", "Teléfono", "tel"), F("email", "Correo electrónico", "email"),
            F("estado", "Estado", "select", req=True, opts=EST_ACTIVO, default="Activo")],
    columns=[("codigo", "Código", "bold"), ("nombre", "Proveedor", "two", "contacto"), ("servicio", "Servicio", "text"),
             ("telefono", "Teléfono", "text"), ("estado", "Estado", "pill")],
    search=["codigo", "nombre", "contacto"], filters=["servicio", "estado"],
    kpis=[("Total de proveedores", None, "blue", "wrench"), ("Activos", "estado='Activo'", "blue", "check"), ("Inactivos", "estado='Inactivo'", "danger", "x")],
    states=EST_ACTIVO,
    related=[("Servicios", "SELECT m.codigo, v.placa, m.tipo, m.estado FROM mantenimientos m JOIN vehiculos v ON v.id=m.vehiculo_id WHERE m.proveedor_id=:id ORDER BY m.id DESC",
              [("codigo", "Orden", "bold"), ("placa", "Unidad", "text"), ("tipo", "Tipo", "text"), ("estado", "Estado", "pill")])],
)

# -------------------------------------------------------------------- FLOTA
MODULES["vehiculos"] = dict(
    titulo="Vehículos", singular="vehículo", grupo="Flota", icon="bus", prefijo="UN",
    subtitulo="Administra la flota, su estado operativo, documentos y mantenimiento.",
    fields=[F("codigo", "Código interno", help="Déjalo vacío para generarlo automáticamente."),
            F("placa", "Placa", req=True, help="Formato: ABC-1234"),
            F("tipo", "Tipo de unidad", "select", req=True, cat="tipo_vehiculo"),
            F("marca", "Marca", req=True), F("modelo", "Modelo"), F("anio", "Año", "number"),
            F("capacidad", "Capacidad (pasajeros)", "number"),
            F("socio_id", "Propietario o socio", "fk", fk="socios"),
            F("estado", "Estado", "select", req=True, opts=["Disponible", "Asignado", "En mantenimiento", "Fuera de servicio", "Inactivo"], default="Disponible"),
            F("ultima_revision", "Última revisión", "date"), F("prox_mantenimiento", "Próximo mantenimiento", "date"),
            F("observaciones", "Observaciones", "textarea", full=True)],
    columns=[("codigo", "Código", "bold"), ("placa", "Unidad", "two", "marca_modelo"), ("tipo", "Tipo", "text"),
             ("socio_id", "Propietario", "fk"), ("prox_mantenimiento", "Próx. mantenimiento", "date_warn_mt"), ("estado", "Estado", "pill")],
    extra={"marca_modelo": "marca||' '||COALESCE(modelo,'')"},
    search=["codigo", "placa", "marca", "modelo"], filters=["estado", "tipo"],
    kpis=[("Total de vehículos", None, "blue", "bus"),
          ("En mantenimiento o fuera de servicio", "estado IN ('En mantenimiento','Fuera de servicio')", "warn", "wrench"),
          ("Con documentos vencidos", "id IN (SELECT vehiculo_id FROM documentos WHERE vehiculo_id IS NOT NULL AND fecha_vencimiento<'{hoy}')", "danger", "alert")],
    states=["Disponible", "Asignado", "En mantenimiento", "Fuera de servicio", "Inactivo"], reason_all=True,
    default_sort=("codigo", "asc"),
    related=[
        ("Documentos", "SELECT tipo, fecha_vencimiento, ({vig}) AS vigencia, validacion FROM documentos WHERE vehiculo_id=:id ORDER BY fecha_vencimiento",
         [("tipo", "Documento", "text"), ("fecha_vencimiento", "Vence", "date"), ("vigencia", "Vigencia", "pill"), ("validacion", "Validación", "pill")]),
        ("Mantenimiento", "SELECT codigo, tipo, fecha_programada, estado FROM mantenimientos WHERE vehiculo_id=:id ORDER BY id DESC",
         [("codigo", "Orden", "bold"), ("tipo", "Tipo", "text"), ("fecha_programada", "Fecha", "date"), ("estado", "Estado", "pill")]),
        ("Viajes", "SELECT v.codigo, v.fecha_hora, r.nombre AS ruta, v.estado FROM viajes v JOIN rutas r ON r.id=v.ruta_id WHERE v.vehiculo_id=:id ORDER BY v.fecha_hora DESC LIMIT 15",
         [("codigo", "Viaje", "bold"), ("fecha_hora", "Salida", "dt"), ("ruta", "Ruta", "text"), ("estado", "Estado", "pill")]),
    ],
)

MODULES["mantenimientos"] = dict(
    titulo="Mantenimiento", singular="orden de mantenimiento", grupo="Flota", icon="wrench", prefijo="MT",
    subtitulo="Órdenes preventivas y correctivas. Una unidad vuelve a estar disponible solo con confirmación explícita.",
    fields=[F("codigo", "Código de orden", help="Déjalo vacío para generarlo automáticamente."),
            F("vehiculo_id", "Vehículo", "fk", req=True, fk="vehiculos"),
            F("tipo", "Tipo", "select", req=True, opts=["Preventivo", "Correctivo"]),
            F("proveedor_id", "Proveedor", "fk", fk="proveedores"),
            F("descripcion", "Diagnóstico o trabajo a realizar", "textarea", full=True),
            F("fecha_programada", "Fecha programada", "date"), F("fecha_recepcion", "Recepción en taller", "date"),
            F("fecha_entrega", "Entrega de la unidad", "date"), F("costo", "Costo (USD, si se conoce)", "number"),
            F("estado", "Estado", "select", req=True, default="Solicitado",
              opts=["Solicitado", "Pendiente de diagnóstico", "Cotización pendiente", "Aprobado", "En ejecución", "Esperando repuesto", "Finalizado", "Cancelado"]),
            F("observaciones", "Observaciones", "textarea", full=True)],
    columns=[("codigo", "Orden", "bold"), ("vehiculo_id", "Vehículo", "fk"), ("tipo", "Tipo", "text"),
             ("fecha_programada", "Programada", "date_warn_mt"), ("proveedor_id", "Proveedor", "fk"), ("estado", "Estado", "pill")],
    search=["codigo", "descripcion"], filters=["estado", "tipo"],
    kpis=[("Órdenes abiertas", "estado NOT IN ('Finalizado','Cancelado')", "blue", "wrench"),
          ("Programadas en 15 días", "estado NOT IN ('Finalizado','Cancelado') AND fecha_programada BETWEEN '{hoy}' AND '{hoy15}'", "warn", "calendar"),
          ("Atrasadas", "estado IN ('Solicitado','Aprobado','Pendiente de diagnóstico','Cotización pendiente') AND fecha_programada<'{hoy}'", "danger", "alert")],
    states=["Solicitado", "Pendiente de diagnóstico", "Cotización pendiente", "Aprobado", "En ejecución", "Esperando repuesto", "Finalizado", "Cancelado"],
    reason_states=["Cancelado"], default_sort=("id", "desc"),
    related=[],
)

MODULES["documentos"] = dict(
    titulo="Documentos", singular="documento", grupo="Flota", icon="file", prefijo=None,
    subtitulo="Documentos de conductores, vehículos y socios con control de vencimientos y validación.",
    state_field="validacion",
    fields=[F("tipo", "Tipo de documento", "select", req=True, cat="tipo_documento"),
            F("descripcion", "Descripción", full=True),
            F("conductor_id", "Conductor", "fk", fk="conductores", help="Elige un titular: conductor, vehículo o socio."),
            F("vehiculo_id", "Vehículo", "fk", fk="vehiculos"), F("socio_id", "Socio", "fk", fk="socios"),
            F("fecha_emision", "Fecha de emisión", "date"),
            F("fecha_vencimiento", "Fecha de vencimiento", "date", help="Déjala vacía si el documento no vence."),
            F("validacion", "Validación", "select", req=True, opts=["Pendiente de revisión", "Validado", "Rechazado"], default="Pendiente de revisión"),
            F("archivo", "Archivo (PDF o imagen, máx. 5 MB)", "file", full=True)],
    columns=[("tipo", "Documento", "two", "descripcion"), ("titular", "Titular", "text"),
             ("fecha_vencimiento", "Vence", "date"), ("vigencia", "Vigencia", "pill"), ("validacion", "Validación", "pill")],
    extra={"vigencia": "{vig}",
           "titular": "COALESCE((SELECT nombres||' '||apellidos FROM conductores WHERE id=t.conductor_id),(SELECT placa FROM vehiculos WHERE id=t.vehiculo_id),(SELECT nombre FROM socios WHERE id=t.socio_id),'Organización')"},
    search=["tipo", "descripcion"], filters=["tipo", "validacion", "vigencia"],
    filter_options={"vigencia": ["Vigente", "Próximo a vencer", "Vencido", "Sin vencimiento"]},
    kpis=[("Total de documentos", None, "blue", "file"),
          ("Próximos a vencer (30 días)", "fecha_vencimiento BETWEEN '{hoy}' AND '{hoy30}'", "warn", "alert"),
          ("Vencidos", "fecha_vencimiento<'{hoy}'", "danger", "x")],
    states=["Pendiente de revisión", "Validado", "Rechazado"], reason_states=["Rechazado"], default_sort=("fecha_vencimiento", "asc"),
    related=[],
)

# -------------------------------------------------------------- OPERACIONES
MODULES["rutas"] = dict(
    titulo="Rutas y frecuencias", singular="ruta", grupo="Operaciones", icon="route", prefijo="RT",
    subtitulo="Rutas autorizadas, paradas y frecuencias planificadas.",
    fields=[F("codigo", "Código de ruta", help="Déjalo vacío para generarlo automáticamente."),
            F("nombre", "Nombre descriptivo", req=True), F("origen", "Origen", req=True), F("destino", "Destino", req=True),
            F("paradas", "Paradas autorizadas", "textarea", full=True), F("frecuencia", "Frecuencia u horarios"),
            F("duracion_horas", "Duración estimada (horas)", "number", help="Solo si es un dato validado."),
            F("estado", "Estado", "select", req=True, opts=["Activa", "Inactiva"], default="Activa"),
            F("observaciones", "Observaciones operativas", "textarea", full=True)],
    columns=[("codigo", "Código", "bold"), ("nombre", "Ruta", "two", "paradas"), ("frecuencia", "Frecuencia", "text"),
             ("duracion_horas", "Duración (h)", "text"), ("estado", "Estado", "pill")],
    search=["codigo", "nombre", "origen", "destino"], filters=["estado"],
    kpis=[("Total de rutas", None, "blue", "route"), ("Activas", "estado='Activa'", "blue", "check"), ("Inactivas", "estado='Inactiva'", "danger", "x")],
    states=["Activa", "Inactiva"],
    related=[("Próximos viajes", "SELECT codigo, fecha_hora, estado FROM viajes WHERE ruta_id=:id AND fecha_hora>='{hoy}' ORDER BY fecha_hora LIMIT 15",
              [("codigo", "Viaje", "bold"), ("fecha_hora", "Salida", "dt"), ("estado", "Estado", "pill")])],
)

MODULES["viajes"] = dict(
    titulo="Programación de viajes", singular="viaje", grupo="Operaciones", icon="calendar", prefijo="VJ",
    subtitulo="Asigna unidad y conductor a cada servicio. El sistema detecta conflictos de horario y disponibilidad.",
    fields=[F("codigo", "Código del viaje", help="Déjalo vacío para generarlo automáticamente."),
            F("ruta_id", "Ruta", "fk", req=True, fk="rutas"),
            F("fecha_hora", "Salida planificada", "datetime", req=True),
            F("vehiculo_id", "Vehículo", "fk", fk="vehiculos"), F("conductor_id", "Conductor", "fk", fk="conductores"),
            F("estado", "Estado", "select", req=True, default="Planificado",
              opts=["Planificado", "Confirmado", "En curso", "Finalizado", "Cancelado", "Con novedad"]),
            F("hora_real_salida", "Salida real registrada", "datetime", help="Distinta de la planificada."),
            F("hora_real_llegada", "Llegada real registrada", "datetime"),
            F("motivo_cambio", "Motivo del cambio", help="Obligatorio al modificar la asignación de un viaje existente."),
            F("observaciones", "Observaciones", "textarea", full=True)],
    columns=[("codigo", "Viaje", "bold"), ("ruta_id", "Ruta", "fk"), ("fecha_hora", "Salida planificada", "dt"),
             ("vehiculo_id", "Vehículo", "fk"), ("conductor_id", "Conductor", "fk"), ("estado", "Estado", "pill")],
    search=["codigo", "observaciones"], filters=["estado", "ruta_id"],
    kpis=[("Viajes de hoy", "substr(fecha_hora,1,10)='{hoy}'", "blue", "calendar"),
          ("Sin unidad o conductor", "(vehiculo_id IS NULL OR conductor_id IS NULL) AND estado IN ('Planificado','Confirmado')", "warn", "alert"),
          ("Con novedad o cancelados", "estado IN ('Con novedad','Cancelado')", "danger", "x")],
    states=["Planificado", "Confirmado", "En curso", "Finalizado", "Cancelado", "Con novedad"],
    reason_states=["Cancelado", "Con novedad"], default_sort=("fecha_hora", "desc"), reason_field="motivo_cambio",
    related=[("Incumplimientos del viaje", "SELECT codigo, categoria, estado FROM incumplimientos WHERE viaje_id=:id",
              [("codigo", "Registro", "bold"), ("categoria", "Categoría", "text"), ("estado", "Estado", "pill")])],
)

# ----------------------------------------------------------- SEGURIDAD VIAL
MODULES["capacitaciones"] = dict(
    titulo="Capacitaciones y evaluaciones", singular="capacitación", grupo="Seguridad vial", icon="book", prefijo="CAP",
    subtitulo="Charlas y material formativo, con cuestionarios que registran resultados por conductor.",
    fields=[F("codigo", "Código", help="Déjalo vacío para generarlo automáticamente."),
            F("titulo", "Título", "text", req=True), F("tema", "Tema", "select", cat="tema_capacitacion"),
            F("tipo", "Tipo de contenido", "select", req=True, opts=["Charla", "Video", "Audio", "Documento", "Cuestionario"]),
            F("descripcion", "Descripción y objetivo", "textarea", full=True),
            F("duracion_min", "Duración (minutos)", "number"), F("responsable", "Responsable"),
            F("nota_minima", "Calificación mínima para aprobar (%)", "number", default="70"),
            F("recurso_url", "Enlace al recurso (video, audio o documento)", "text"),
            F("estado", "Estado", "select", req=True, opts=["Borrador", "Publicada", "Archivada"], default="Borrador")],
    columns=[("codigo", "Código", "bold"), ("titulo", "Capacitación", "two", "tema"), ("tipo", "Tipo", "text"),
             ("asignados", "Asignados", "text"), ("completadas", "Completadas", "text"), ("estado", "Estado", "pill")],
    extra={"asignados": "(SELECT COUNT(*) FROM asignaciones_cap a WHERE a.capacitacion_id=t.id)",
           "completadas": "(SELECT COUNT(*) FROM asignaciones_cap a WHERE a.capacitacion_id=t.id AND a.estado IN ('Completada','Aprobada'))"},
    search=["codigo", "titulo", "tema"], filters=["estado", "tipo"],
    kpis=[("Capacitaciones publicadas", "estado='Publicada'", "blue", "book"),
          ("Asignaciones pendientes", "id IN (SELECT capacitacion_id FROM asignaciones_cap WHERE estado IN ('Asignada','En progreso','No aprobada'))", "warn", "alert"),
          ("En borrador", "estado='Borrador'", "danger", "file")],
    states=["Borrador", "Publicada", "Archivada"], default_sort=("id", "desc"), related=[],
)

MODULES["incumplimientos"] = dict(
    titulo="Incumplimientos", singular="incumplimiento", grupo="Seguridad vial", icon="shield", prefijo="INC",
    subtitulo="Un reporte inicial no es un caso confirmado: cada decisión se revisa por una persona y queda registrada.",
    fields=[F("codigo", "Código", help="Déjalo vacío para generarlo automáticamente."),
            F("fecha_hora", "Fecha y hora del hecho", "datetime", req=True, default="now"),
            F("conductor_id", "Conductor", "fk", req=True, fk="conductores"), F("vehiculo_id", "Vehículo", "fk", fk="vehiculos"),
            F("viaje_id", "Viaje", "fk", fk="viajes"), F("categoria", "Categoría", "select", req=True, cat="categoria_incumplimiento"),
            F("lugar", "Lugar o referencia"), F("fuente", "Fuente del reporte"),
            F("severidad", "Severidad", "select", opts=SEVERIDAD, default="Media"),
            F("descripcion", "Descripción objetiva", "textarea", req=True, full=True, help="Describe hechos observables, sin juicios."),
            F("responsable", "Responsable de la revisión"), F("accion", "Acción preventiva o correctiva", "textarea", full=True),
            F("decision", "Decisión y justificación", "textarea", full=True, hidden_form=True),
            F("estado", "Estado", "select", req=True, opts=["Reportado", "En revisión", "Confirmado", "Descartado", "Cerrado"], default="Reportado")],
    columns=[("codigo", "Código", "bold"), ("conductor_id", "Conductor", "fk"), ("categoria", "Categoría", "two", "lugar"),
             ("fecha_hora", "Fecha", "dt"), ("severidad", "Severidad", "pill"), ("estado", "Estado", "pill")],
    search=["codigo", "descripcion", "lugar"], filters=["estado", "categoria", "severidad"],
    kpis=[("Pendientes de revisión", "estado IN ('Reportado','En revisión')", "warn", "alert"),
          ("Confirmados", "estado='Confirmado'", "blue", "shield"), ("Severidad alta o crítica", "severidad IN ('Alta','Crítica') AND estado NOT IN ('Descartado','Cerrado')", "danger", "x")],
    states=["Reportado", "En revisión", "Confirmado", "Descartado", "Cerrado"],
    reason_states=["Confirmado", "Descartado", "Cerrado"], reason_field="decision", default_sort=("fecha_hora", "desc"),
    related=[], note="No se aplican puntos ni sanciones automáticas: toda medida requiere revisión humana y una política aprobada.",
)

MODULES["incidentes"] = dict(
    titulo="Incidentes y novedades en ruta", singular="novedad", grupo="Seguridad vial", icon="alert", prefijo="NOV",
    subtitulo="Fallas, retrasos, cierres de vía y siniestros que afectan personas, unidades o el servicio.",
    form_warning="Reporta únicamente con el vehículo detenido en un lugar seguro. Nunca manipules el teléfono mientras conduces.",
    fields=[F("codigo", "Código", help="Déjalo vacío para generarlo automáticamente."),
            F("fecha_hora", "Fecha y hora", "datetime", req=True, default="now"),
            F("tipo", "Tipo de novedad", "select", req=True, cat="tipo_incidente"),
            F("urgencia", "Urgencia", "select", req=True, opts=["Baja", "Media", "Alta", "Crítica"], default="Media"),
            F("ruta_id", "Ruta", "fk", fk="rutas"), F("lugar", "Ubicación descrita", help="Ej.: km 45, cerca de la parada X."),
            F("vehiculo_id", "Vehículo", "fk", fk="vehiculos"), F("conductor_id", "Conductor", "fk", fk="conductores"),
            F("descripcion", "Descripción", "textarea", req=True, full=True),
            F("responsable", "Responsable de seguimiento"), F("causa", "Causa confirmada"),
            F("acciones", "Acciones tomadas", "textarea", full=True),
            F("estado", "Estado", "select", req=True, opts=["Nuevo", "En atención", "Derivado", "Resuelto", "Cerrado"], default="Nuevo")],
    columns=[("codigo", "Código", "bold"), ("tipo", "Novedad", "two", "lugar"), ("fecha_hora", "Fecha", "dt"),
             ("vehiculo_id", "Vehículo", "fk"), ("urgencia", "Urgencia", "pill"), ("estado", "Estado", "pill")],
    search=["codigo", "descripcion", "lugar"], filters=["estado", "tipo", "urgencia"],
    kpis=[("Sin atender", "estado='Nuevo'", "warn", "alert"), ("Abiertas", "estado IN ('Nuevo','En atención','Derivado')", "blue", "route"),
          ("Urgencia alta o crítica abiertas", "urgencia IN ('Alta','Crítica') AND estado IN ('Nuevo','En atención','Derivado')", "danger", "x")],
    states=["Nuevo", "En atención", "Derivado", "Resuelto", "Cerrado"], reason_states=["Cerrado"], default_sort=("fecha_hora", "desc"),
    force_self={"conductor_id": "conductor_id"}, related=[],
)

MODULES["hallazgos"] = dict(
    titulo="Inspecciones de vías", singular="hallazgo vial", grupo="Seguridad vial", icon="map", prefijo="HV",
    subtitulo="Hallazgos observados en rutas y tramos, con prioridad y seguimiento.",
    fields=[F("codigo", "Código", help="Déjalo vacío para generarlo automáticamente."),
            F("fecha", "Fecha de inspección", "date", req=True, default="today"),
            F("ruta_id", "Ruta", "fk", req=True, fk="rutas"), F("tramo", "Tramo o referencia"),
            F("tipo", "Tipo de hallazgo", "select", req=True, cat="tipo_hallazgo"),
            F("prioridad", "Prioridad", "select", req=True, opts=["Baja", "Media", "Alta", "Crítica"], default="Media"),
            F("descripcion", "Descripción", "textarea", req=True, full=True), F("responsable", "Responsable de seguimiento"),
            F("estado", "Estado", "select", req=True, opts=["Abierto", "En seguimiento", "Resuelto", "Cerrado"], default="Abierto")],
    columns=[("codigo", "Código", "bold"), ("tipo", "Hallazgo", "two", "tramo"), ("ruta_id", "Ruta", "fk"),
             ("fecha", "Fecha", "date"), ("prioridad", "Prioridad", "pill"), ("estado", "Estado", "pill")],
    search=["codigo", "descripcion", "tramo"], filters=["estado", "tipo", "prioridad"],
    kpis=[("Abiertos", "estado IN ('Abierto','En seguimiento')", "blue", "map"), ("Sin responsable", "(responsable IS NULL OR responsable='') AND estado IN ('Abierto','En seguimiento')", "warn", "alert"),
          ("Prioridad alta o crítica", "prioridad IN ('Alta','Crítica') AND estado IN ('Abierto','En seguimiento')", "danger", "x")],
    states=["Abierto", "En seguimiento", "Resuelto", "Cerrado"], default_sort=("fecha", "desc"), related=[],
    note="El mapa de incidencias no está disponible: aún no existen coordenadas ni integración cartográfica. Se muestra la vista de lista.",
)

# ------------------------------------------------- CONFIGURACIÓN / AUDITORÍA
MODULES["usuarios"] = dict(
    titulo="Usuarios y roles", singular="usuario", grupo="Configuración", icon="key", prefijo=None,
    subtitulo="Cuentas de acceso, roles y vinculación con conductores o socios.",
    fields=[F("nombre", "Nombre completo", req=True), F("email", "Correo (usuario de acceso)", "email", req=True),
            F("password", "Contraseña", "password", help="Mínimo 8 caracteres. Déjala vacía al editar para no cambiarla."),
            F("rol", "Rol", "select", req=True, opts=list(ROLES)), 
            F("conductor_id", "Conductor vinculado", "fk", fk="conductores", help="Solo para el rol Conductor."),
            F("socio_id", "Socio vinculado", "fk", fk="socios", help="Solo para el rol Socio."),
            F("estado", "Estado", "select", req=True, opts=EST_ACTIVO, default="Activo")],
    columns=[("nombre", "Usuario", "two", "email"), ("rol", "Rol", "role"), ("estado", "Estado", "pill")],
    search=["nombre", "email"], filters=["rol", "estado"],
    kpis=[("Total de usuarios", None, "blue", "key"), ("Activos", "estado='Activo'", "blue", "check"), ("Inactivos", "estado='Inactivo'", "danger", "x")],
    states=EST_ACTIVO, default_sort=("nombre", "asc"), related=[], reason_states=["Inactivo"],
)

MODULES["catalogos"] = dict(
    titulo="Catálogos", singular="valor de catálogo", grupo="Configuración", icon="settings", prefijo=None,
    subtitulo="Listas editables (tipos de documento, categorías, etc.) sin tocar el código.",
    fields=[F("categoria", "Catálogo", "select", req=True,
              opts=["tipo_documento", "tipo_vehiculo", "tema_capacitacion", "categoria_incumplimiento", "tipo_incidente", "tipo_hallazgo"]),
            F("valor", "Valor", req=True), F("estado", "Estado", "select", req=True, opts=EST_ACTIVO, default="Activo")],
    columns=[("categoria", "Catálogo", "catname"), ("valor", "Valor", "bold"), ("estado", "Estado", "pill")],
    search=["valor"], filters=["categoria", "estado"],
    kpis=[("Valores totales", None, "blue", "settings"), ("Activos", "estado='Activo'", "blue", "check"), ("Inactivos", "estado='Inactivo'", "danger", "x")],
    states=EST_ACTIVO, default_sort=("categoria", "asc"), related=[],
)

MODULES["auditoria"] = dict(
    titulo="Auditoría", singular="evento", grupo="Configuración", icon="eye", prefijo=None, readonly=True, no_detail=True,
    subtitulo="Bitácora de acciones relevantes. Solo lectura: nadie puede editar ni borrar el historial.",
    fields=[F("modulo", "Módulo", "select", opts=[]), F("accion", "Acción", "select", opts=[])],
    columns=[("fecha", "Fecha", "dt"), ("usuario", "Usuario", "text"), ("accion", "Acción", "text"),
             ("modulo", "Módulo", "text"), ("resumen", "Resumen", "text"), ("resultado", "Resultado", "pill")],
    search=["usuario", "resumen", "modulo"], filters=["modulo", "accion"], dynamic_filters=True,
    kpis=[("Eventos registrados", None, "blue", "eye"), ("Eventos de hoy", "substr(fecha,1,10)='{hoy}'", "blue", "calendar"),
          ("Con resultado fallido", "resultado<>'Correcto'", "danger", "x")],
    states=[], default_sort=("id", "desc"), related=[],
)

# ------------------------------------------------------------------ PERMISOS
# w = escribe, r = lee, c = solo crea
PERMS = {
    "conductores": {"w": ["admin", "administrativo"], "r": ["gerencia", "operaciones", "seguridad", "auditor", "conductor", "flota"]},
    "personal": {"w": ["admin", "administrativo"], "r": ["gerencia", "auditor"]},
    "socios": {"w": ["admin", "administrativo"], "r": ["gerencia", "flota", "auditor", "socio"]},
    "proveedores": {"w": ["admin", "administrativo", "flota"], "r": ["gerencia", "auditor"]},
    "vehiculos": {"w": ["admin", "flota"], "r": ["gerencia", "operaciones", "seguridad", "administrativo", "auditor", "socio"]},
    "mantenimientos": {"w": ["admin", "flota"], "r": ["gerencia", "operaciones", "auditor", "socio"]},
    "documentos": {"w": ["admin", "administrativo", "flota"], "r": ["gerencia", "auditor", "seguridad", "conductor", "socio"]},
    "rutas": {"w": ["admin", "operaciones"], "r": ["gerencia", "seguridad", "conductor", "auditor", "flota"]},
    "viajes": {"w": ["admin", "operaciones"], "r": ["gerencia", "seguridad", "flota", "auditor", "conductor", "socio"]},
    "capacitaciones": {"w": ["admin", "seguridad"], "r": ["gerencia", "auditor", "conductor"]},
    "incumplimientos": {"w": ["admin", "seguridad"], "r": ["gerencia", "auditor", "operaciones", "conductor"]},
    "incidentes": {"w": ["admin", "seguridad", "operaciones", "flota"], "r": ["gerencia", "auditor", "conductor"], "c": ["conductor"]},
    "hallazgos": {"w": ["admin", "seguridad", "operaciones"], "r": ["gerencia", "auditor", "flota"]},
    "usuarios": {"w": ["admin"], "r": []},
    "catalogos": {"w": ["admin"], "r": ["auditor"]},
    "auditoria": {"w": [], "r": ["admin", "auditor", "gerencia"]},
}

# Alcance por fila para los roles con acceso restringido a lo propio.
# valor: (cláusula SQL con alias t, campo del usuario que se enlaza)
SCOPES = {
    ("conductores", "conductor"): ("t.id=?", "conductor_id"),
    ("viajes", "conductor"): ("t.conductor_id=?", "conductor_id"),
    ("documentos", "conductor"): ("t.conductor_id=?", "conductor_id"),
    ("incumplimientos", "conductor"): ("t.conductor_id=? AND t.estado IN ('Confirmado','Cerrado')", "conductor_id"),
    ("incidentes", "conductor"): ("t.conductor_id=?", "conductor_id"),
    ("capacitaciones", "conductor"): ("t.id IN (SELECT capacitacion_id FROM asignaciones_cap WHERE conductor_id=?)", "conductor_id"),
    ("socios", "socio"): ("t.id=?", "socio_id"),
    ("vehiculos", "socio"): ("t.socio_id=?", "socio_id"),
    ("viajes", "socio"): ("t.vehiculo_id IN (SELECT id FROM vehiculos WHERE socio_id=?)", "socio_id"),
    ("mantenimientos", "socio"): ("t.vehiculo_id IN (SELECT id FROM vehiculos WHERE socio_id=?)", "socio_id"),
    ("documentos", "socio"): ("(t.socio_id=? OR t.vehiculo_id IN (SELECT id FROM vehiculos WHERE socio_id=?))", "socio_id2"),
}

# Orden y agrupación del menú
NAV = [
    ("Operaciones", ["viajes", "rutas"]),
    ("Personas", ["conductores", "personal", "socios", "proveedores"]),
    ("Flota", ["vehiculos", "mantenimientos", "documentos"]),
    ("Seguridad vial", ["capacitaciones", "incumplimientos", "incidentes", "hallazgos"]),
    ("Análisis", ["reportes"]),
    ("Configuración", ["usuarios", "catalogos", "auditoria"]),
]

CAT_NOMBRES = {
    "tipo_documento": "Tipos de documento", "tipo_vehiculo": "Tipos de vehículo", "tema_capacitacion": "Temas de capacitación",
    "categoria_incumplimiento": "Categorías de incumplimiento", "tipo_incidente": "Tipos de incidente", "tipo_hallazgo": "Tipos de hallazgo",
}

# Colores de estado (siempre acompañados de texto)
PILL = {
    "ok": ["Activo", "Activa", "Disponible", "Finalizado", "Resuelto", "Validado", "Vigente", "Aprobada", "Completada",
           "Publicada", "Aprobado", "Correcto", "Baja"],
    "warn": ["Pendiente de validación", "Pendiente de revisión", "Próximo a vencer", "En mantenimiento", "En revisión",
             "En atención", "Reportado", "Solicitado", "Pendiente de diagnóstico", "Cotización pendiente",
             "Esperando repuesto", "Con novedad", "Abierto", "En seguimiento", "Asignada", "En progreso", "Derivado",
             "Nuevo", "Media"],
    "bad": ["Vencido", "Vencida", "Fuera de servicio", "Suspendido", "Rechazado", "No aprobada", "Alta", "Crítica", "Fallido"],
    "info": ["Planificado", "Confirmado", "En curso", "En ejecución", "Asignado", "Preventivo", "Correctivo"],
    "off": ["Inactivo", "Inactiva", "Cancelado", "Descartado", "Cerrado", "Borrador", "Archivada", "Sin vencimiento"],
}
