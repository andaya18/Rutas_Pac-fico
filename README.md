# Rutas del Pacífico – Sistema web de gestión integral (prototipo funcional)

Python + Flask + SQLite. Interfaz en español, inspirada en el diseño de referencia (barra lateral azul, tarjetas de indicadores, tablas con filtros).
**Todos los datos son ficticios (datos de demostración).**

## Requisitos
- Python 3.10 o superior (https://www.python.org/downloads/ — en Windows marca "Add Python to PATH")

## Ejecutar (Windows, macOS o Linux)
```bash
cd rutas_pacifico
python -m venv venv
# Windows:      venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Abre **http://127.0.0.1:5000** en el navegador.

La base de datos `rutas_pacifico.db` se crea sola la primera vez, con datos de demostración.
Para volver a los datos originales: `python app.py --reset`

## Cuentas de demostración (contraseña de todas: `Demo2026!`)
| Rol | Correo |
|---|---|
| Administrador | admin@rutaspacifico.demo |
| Gerencia | gerencia@rutaspacifico.demo |
| Operaciones / despacho | operaciones@rutaspacifico.demo |
| Seguridad vial | seguridad@rutaspacifico.demo |
| Flota y mantenimiento | flota@rutaspacifico.demo |
| Personal administrativo | administrativo@rutaspacifico.demo |
| Conductor | conductor@rutaspacifico.demo |
| Socio / propietario | socio@rutaspacifico.demo |
| Auditor | auditor@rutaspacifico.demo |

## Estructura
- `app.py` rutas, permisos, validaciones, dashboard, reportes, auditoría
- `config.py` módulos, campos, permisos y menú (agregar un módulo = agregar un diccionario)
- `database.py` esquema SQL y datos de demostración
- `templates/`, `static/` interfaz

## Qué hace
Inicio de sesión por rol · panel por perfil · conductores, personal, socios, proveedores · vehículos, mantenimiento, documentos con vencimientos ·
rutas y programación de viajes (detecta conflictos, unidades no disponibles, pide motivo al cambiar) · capacitaciones con cuestionarios y resultados ·
incumplimientos con revisión humana (sin sanciones automáticas) · novedades en ruta · inspecciones de vías · reportes con CSV · notificaciones ·
auditoría de solo lectura · catálogos editables · usuarios y roles.

## Límites (según la especificación)
No incluye venta de boletos, pagos, nómina, GPS, cámaras ni mapa de incidencias. Los procesos y permisos deben validarse con la cooperativa.
Para un despliegue real: usar HTTPS, un servidor WSGI (gunicorn/waitress), base de datos de producción y copias de seguridad.
