# Facturas Impagadas - Backend (FastAPI)

Servicio FastAPI que expone la API corporativa de facturas pendientes de ATISA. Consolida datos de Sage X3 (SQL Server) y bases auxiliares SQLite/MariaDB, gestiona consultores y registra acciones comerciales. Incluye autenticacion Azure AD (MSAL) y genera reportes (Excel, resumenes KPI) consumidos por el frontend Vite/React.

---

## Contenido express

1. [Resumen funcional](#resumen-funcional)  
2. [Arquitectura](#arquitectura)  
3. [Requisitos](#requisitos)  
4. [Configuracion local](#configuracion-local)  
5. [Variables de entorno](#variables-de-entorno)  
6. [Ejecucion diaria](#ejecucion-diaria)  
7. [Routers y endpoints](#routers-y-endpoints)  
8. [Scripts y jobs](#scripts-y-jobs)  
9. [Testing](#testing)  
10. [Despliegue](#despliegue)  
11. [Soporte rapido](#soporte-rapido)

---

## Resumen funcional

- Dashboard de KPI: totales por sociedad, niveles de reclamacion y clientes con deuda.
- Buscador avanzado de facturas (por numero, asiento, sociedad) con enriquecimiento de datos de cliente.
- API de consultores: alta/baja logica, asignaciones, proximos avisos y resumen de cartera.
- Registro de acciones: crear, editar, eliminar y listar acciones comerciales y cambios de estado.
- Seguimientos simples y seguimientos por lotes (cabecera + detalle de facturas involucradas).
- Exportador Excel agrupado por sociedad para reportes ejecutivos.
- Autenticacion Azure AD con callback `/auth/callback`, bridge `/auth/return` y diagnostico `/auth/debug`.
- Servicios auxiliares: envio programado de correos/Teams y healthcheck (`/health`).

## Arquitectura

```
facturas_backend/
  app/
    application/      # Casos de uso (obtener estadisticas, resumenes, etc.)
    auth/             # Rutas y helpers MSAL + JWT
    config/           # Settings, SQLAlchemy, inicializacion de tablas
    domain/           # Modelos ORM y constantes
    infrastructure/   # Repositorios contra SQL Server / SQLite
    interfaces/       # Routers FastAPI
    services/         # Azure Graph, notificador, servicios de negocio
    utils/            # Helpers varios (errores, formato)
  scripts/            # Jobs ejecutables (ej. enviar_acciones_pendientes)
  migrations/         # Tablas auxiliares
  main.py             # Punto de entrada
  requirements.txt
```

## Requisitos

- Python 3.11
- SQL Server con driver ODBC 18 (msodbcsql18). En local se puede usar SQLite por defecto.
- Credenciales Azure AD (CLIENT_ID, TENANT_ID, CLIENT_SECRET) y redirect autorizado.
- Acceso a las vistas/tables `x3v12.ATISAINT.GACCDUDATE`, historial y pagos.
- Para produccion Linux: `unixODBC` + `msodbcsql18` instalados.

## Configuracion local

```bash
git clone <repo>
cd facturas_impagadas/facturas_backend
python -m venv venv
venv\Scripts\activate      # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
# Opcional: copiar .env.local -> .env y ajustar cadenas de conexion
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

La documentacion interactiva queda en `http://localhost:8000/docs`.

## Variables de entorno

| Clave | Explicacion |
| --- | --- |
| `DATABASE_URL_FACTURAS` | Conexion principal (SQL Server). Por defecto `sqlite:///./facturas.db` |
| `DATABASE_URL_CLIENTES` | Fuente de clientes (SQL Server). Por defecto `sqlite:///./clientes.db` |
| `GESTION_DATABASE_URL` | BD para consultores/asignaciones. Por defecto `sqlite:///./gestion_facturas.db` |
| `HISTORIAL_DATABASE_URL` | BD local para historial (`sqlite:///./facturas_historial.db`) |
| `AUTH_REDIRECT_URI` | URL registrada en Azure (`https://demoimpagos.atisa.es/auth/callback`) |
| `FRONTEND_BASE_URL` | Donde redirigir despues del login (produccion: `https://demoimpagos.atisa.es`) |
| `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID` | Credenciales MSAL |
| `AZURE_ALLOWED_DOMAINS` | Lista (coma) de dominios permitidos para login |
| `JWT_SECRET`, `JWT_EXPIRES_SECONDS` | Firma y expiracion del token local |
| `ODBC_DRIVER_NAME` | Forzar nombre del driver (fallback: `ODBC Driver 18 for SQL Server`) |
| `NOTIFIER_SMTP_*`, `NOTIFIER_TEAMS_*` | Configuracion del notificador de consultores |

Guarda estos valores en un `.env` y FastAPI los cargara via `dotenv`.

## Ejecucion diaria

- **Levantar API**: `uvicorn main:app --reload --port 8520` o usar `python main.py` (arranca en 8520).
- **Compilar rapido**: `python -m py_compile app/interfaces/*.py` (igual que indica `GUIA_DESPLIEGUE.md`).
- **Healthcheck**: `curl http://127.0.0.1:8520/health`.
- **Diagnostico Azure**: `curl http://127.0.0.1:8520/auth/debug`.
- **Validar drivers ODBC**: `python -c "from app.config.database import log_odbc_env_diagnostics; log_odbc_env_diagnostics()"`.

## Routers y endpoints

| Archivo | Prefijo | Highlights |
| --- | --- | --- |
| `app/interfaces/facturas_controller.py` | `/api` | Facturas por cliente, busqueda por numero, resumenes por cliente/sociedad, estadisticas, Excel, historial de pagos, acciones, cambios |
| `app/interfaces/historial_controller.py` | `/api` | CRUD liviano de historial de facturas locales |
| `app/interfaces/consultores_controller.py` | `/api` | CRUD de consultores, asignaciones, proximos avisos, exportaciones |
| `app/interfaces/registro_facturas_controller.py` | `/api` | Registro estructurado de cambios y comentarios |
| `app/interfaces/seguimientos_controller.py` | `/api` | Crear/listar seguimientos basicos |
| `app/interfaces/seguimiento_acciones_controller.py` | `/api` | Cabeceras, acciones y facturas asociadas a seguimientos complejos |
| `app/auth/routes.py` | `/auth` | Login Azure, callback, `me`, logout local/azure, debug |
| `main.py` | `/auth/return`, `/health` | Bridge HTML que guarda el token y health endpoint |

Todos los controladores usan repositorios en `app/infrastructure` (SQLAlchemy) y casos de uso en `app/application` para mantener la logica desacoplada. Helpers en `app/utils` estandarizan errores y formato.

## Scripts y jobs

- `scripts/enviar_acciones_pendientes.py`: envia emails o mensajes de Teams a consultores con acciones proximas. Se ejecuta via `cron` en produccion (ver entrada exacta en `GUIA_DESPLIEGUE.md`). Localmente:

  ```bash
  source venv/bin/activate
  python scripts/enviar_acciones_pendientes.py --dry-run
  ```

- Services esperados en produccion: `facturas-backend.service` (API) y `facturas-frontend.service`. El script anterior se agenda desde `crontab` apuntando al mismo entorno virtual.

## Testing

- Ejecuta `pytest` para las pruebas incluidas (mock de repositorios, helpers, etc.).
- No hay formateador automatico configurado; manten PEP8 o agrega `ruff/black` si lo necesitas.
- Antes de hacer push revisa importaciones con `python -m py_compile ...` como indica la guia.

## Despliegue

Flujo basico (resumen, revisa `GUIA_DESPLIEGUE.md` para el detalle):

1. En local: `python -m py_compile` sobre los controladores listados y `npm run build` en el frontend.
2. `git add . && git commit && git push origin master` (backend y frontend por separado).
3. En IASERVER: `git pull origin master` dentro de `/home/produccion/facturas_impagadas/facturas_backend`.
4. Reinicia el servicio: `sudo systemctl restart facturas-backend.service` y verifica `sudo systemctl status ...`.
5. Comprueba `/health`, `/auth/debug` y el login real. Si cambiaste nginx, ejecuta `sudo nginx -t` y `sudo systemctl reload nginx`.

## Soporte rapido

- **Login falla**: revisa `AUTH_REDIRECT_URI`, `FRONTEND_BASE_URL` y el bloque `/auth` de nginx (orden y destino). Usa `/auth/debug` para confirmar configuracion.
- **Error IM002**: el servidor no encuentra el driver ODBC. Corre `log_odbc_env_diagnostics()` para listar drivers instalados.
- **Consultores no se crean**: borra `gestion_facturas.db` local o confirma permisos sobre la BD configurada en `GESTION_DATABASE_URL`.
- **Excel de sociedades devuelve 503**: solo funciona con SQL Server; con SQLite se bloquea para evitar datos inconsistentes.
- **Acciones automaticas**: si el cron no envia correos, revisa `/var/log/facturas_acciones.log` en el servidor y los `NOTIFIER_SMTP_*` definidos.

Documenta cualquier cambio relevante tambien en `GUIA_DESPLIEGUE.md` para mantener despliegues sin sorpresas.
