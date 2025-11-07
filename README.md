# 🧾 Sistema de Gestión de Facturas Pendientes - ATISA

## 📋 Descripción del Proyecto

Este proyecto es un **backend robusto y escalable** desarrollado para **ATISA** que se encarga de gestionar las facturas impagadas y pendientes de los distintos clientes. El sistema proporciona una API REST completa que permite consultar, filtrar y analizar el estado financiero de las facturas de manera eficiente.

## 🏗️ Arquitectura del Sistema

El proyecto sigue una **arquitectura limpia (Clean Architecture)** con separación clara de responsabilidades:

```
📁 facturas_backend/
├── 🐍 app/
│   ├── 📁 application/          # Casos de uso (Use Cases)
│   ├── 📁 domain/              # Modelos de dominio y lógica de negocio
│   ├── 📁 infrastructure/      # Repositorios y acceso a datos
│   ├── 📁 interfaces/          # Controladores y endpoints de la API
│   └── 📁 config/              # Configuración de base de datos y settings
├── 🧪 tests/                   # Pruebas unitarias y de integración
├── 📋 requirements.txt          # Dependencias del proyecto
└── 🚀 main.py                  # Punto de entrada de la aplicación
```

## 🚀 Tecnologías Utilizadas

### Backend
- **FastAPI**: Framework web moderno y rápido para Python
- **Python 3.11**: Versión estable y optimizada
- **SQLAlchemy**: ORM para gestión de base de datos
- **Pydantic**: Validación de datos y serialización
- **PyODBC**: Conector para base de datos SQL Server

### Base de Datos
- **MariaDB/MySQL**: Sistema de gestión de base de datos relacional
- **SQL Server**: Base de datos corporativa de ATISA

### DevOps & Testing
- **Pytest**: Framework de testing
- **Uvicorn**: Servidor ASGI para FastAPI

## 📊 Funcionalidades Principales

### 1. 🧾 Gestión de Facturas
- **Consulta de facturas por cliente**: Obtener todas las facturas de un cliente específico
- **Filtrado avanzado**: Filtrar por fechas, nivel de reclamación, importes, etc.
- **Agrupación por cliente**: Resumen de facturas pendientes por cliente
- **Estadísticas generales**: Métricas y KPIs del sistema de facturación

### 2. 👥 Gestión de Clientes
- **Información del cliente**: Datos completos del cliente asociado a cada factura
- **Resumen financiero**: Estado de cuenta consolidado por cliente
- **Historial de pagos**: Seguimiento de pagos y vencimientos

### 3. 📈 Análisis y Reportes
- **Estadísticas en tiempo real**: Métricas actualizadas del sistema
- **Filtros personalizables**: Consultas específicas según necesidades del negocio
- **Exportación de datos**: Preparado para integración con sistemas de reporting

## 🔌 Endpoints de la API

### Base URL
```
http://localhost:8000
```

### Endpoints Disponibles

#### 🧾 Facturas
```http
GET /api/facturas-cliente/{idcliente}
```
**Descripción**: Obtiene todas las facturas de un cliente específico
**Parámetros**:
- `idcliente` (path): Identificador único del cliente

**Respuesta**: Lista de facturas con datos del cliente incluidos

#### 👥 Clientes
```http
GET /api/clientes-con-resumen
```
**Descripción**: Obtiene un resumen de clientes con sus facturas agrupadas
**Parámetros de consulta**:
- `tercero` (opcional): Filtro por código de cliente
- `fecha_desde` (opcional): Fecha de inicio para el filtro
- `fecha_hasta` (opcional): Fecha de fin para el filtro
- `nivel_reclamacion` (opcional): Filtro por nivel de reclamación

**Respuesta**: Lista de clientes con resumen de facturas pendientes

#### 📊 Estadísticas
```http
GET /api/estadisticas
```
**Descripción**: Obtiene estadísticas generales del sistema de facturación
**Respuesta**: Métricas consolidadas del sistema

## 🔄 Estado actual del backend (resumen)

- `/api/estadisticas` devuelve campos extra usados por el frontend:
  - `sociedades_con_montos`: deuda agregada por sociedad (CPY_0).
  - `facturas_mas_vencidas`: listado de facturas vencidas (ordenadas) para tabla con paginación.
- `/api/clientes-con-resumen`:
  - Aplica filtro por sociedades `CPY_0 IN ('S005','S001','S010')` para que el conteo de facturas y deuda coincidan con negocio.
  - Evita el error de PyODBC “Connection is busy with results for another command” consumiendo primero la consulta de sociedades y después la principal.
  - El controlador captura excepciones y responde `[]` para no romper el frontend (se deja traza en logs).

#### 🏥 Health Check
```http
GET /health
```
**Descripción**: Verificación del estado de la API
**Respuesta**: Estado del servicio y versión

## 🗄️ Modelo de Datos

### Entidad Factura
```python
class Factura(BaseModel):
    tipo: str                    # Tipo de factura
    asiento: int                 # Número de asiento contable
    sociedad: str                # Código de sociedad
    planta: str                  # Código de planta
    moneda: str                  # Moneda de la factura
    colectivo: str               # Colectivo contable
    tercero: str                 # Código del cliente
    vencimiento: datetime        # Fecha de vencimiento
    forma_pago: str              # Forma de pago
    sentido: int                 # Sentido de la operación
    importe: Decimal             # Importe de la factura
    pago: Optional[Decimal]      # Importe pagado (opcional)
    nivel_reclamacion: Optional[int]      # Nivel de reclamación
    fecha_reclamacion: Optional[datetime] # Fecha de reclamación
    check_pago: Optional[int]    # Indicador de pago
```

## 🚀 Instalación y Configuración

### Prerrequisitos
- Python 3.11 o superior
- MariaDB/MySQL o SQL Server

### 1. Clonar el Repositorio
```bash
git clone https://github.com/developersatisa/gestor_back_facturas_pendientes.git
cd gestor_back_facturas_pendientes
```

### 2. Crear Entorno Virtual
```bash
python -m venv venv
# En Windows:
venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate
```

### 3. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar Variables de Entorno
Crear archivo `.env` en la raíz del proyecto:
```env
# Configuración de Base de Datos
DATABASE_URL_FACTURAS=your_database_connection_string
DATABASE_URL_CLIENTES=your_database_connection_string

# Configuración de la API
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True

# Notificador de consultores (opcional)
NOTIFIER_SMTP_HOST=smtp.servidor.com
NOTIFIER_SMTP_PORT=587
NOTIFIER_SMTP_USER=usuario
NOTIFIER_SMTP_PASSWORD=clave
NOTIFIER_SMTP_FROM=notificaciones@dominio.com
NOTIFIER_SMTP_STARTTLS=1

```

### 5. Ejecutar la Aplicación
```bash
# Desarrollo
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Producción
uvicorn main:app --host 0.0.0.0 --port 8000
```


## 🧪 Testing

### Ejecutar Pruebas
```bash
# Todas las pruebas
pytest

# Pruebas específicas
pytest tests/test_facturas_endpoint.py

# Con cobertura
pytest --cov=app tests/
```

### Estructura de Tests
```
tests/
├── test_facturas_endpoint.py      # Pruebas de endpoints de facturas
└── test_obtener_facturas_filtradas.py  # Pruebas de lógica de negocio
```

## 🔧 Configuración de Base de Datos

### Conexión SQL Server
```python
# app/config/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "mssql+pyodbc://username:password@server/database?driver=ODBC+Driver+17+for+SQL+Server"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

### Conexión MariaDB/MySQL
```python
# app/config/database.py
DATABASE_URL = "mysql+pymysql://username:password@localhost/database_name"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

## 📚 Casos de Uso

### 1. Obtener Facturas de un Cliente
```python
from app.application.obtener_facturas_filtradas import ObtenerFacturasFiltradas

# Ejecutar caso de uso
use_case = ObtenerFacturasFiltradas(repositorio)
facturas = use_case.execute(tercero="CLIENTE001")
```

### 2. Calcular Estadísticas
```python
from app.application.obtener_estadisticas_facturas import ObtenerEstadisticasFacturas

# Ejecutar caso de uso
use_case = ObtenerEstadisticasFacturas(repositorio_facturas, repositorio_clientes)
estadisticas = use_case.execute()
```

### 3. Agrupar Facturas por Cliente
```python
from app.application.obtener_facturas_agrupadas_por_cliente import ObtenerFacturasAgrupadasPorCliente

# Ejecutar caso de uso
use_case = ObtenerFacturasAgrupadasPorCliente(repositorio_facturas, repositorio_clientes)
clientes_con_facturas = use_case.execute(fecha_desde="2024-01-01")
```

## 🔒 Seguridad y Configuración

### CORS
La API está configurada para permitir conexiones desde:
- Frontend local (puerto 5173)
- Frontend de desarrollo (puerto 3000)
- IPs específicas de la red corporativa
- Configuración temporal para desarrollo

### Logging
- Nivel de logging configurado en INFO
- Logs de operaciones de facturas
- Logs de errores y excepciones

### Manejo de Errores
- Respuestas HTTP apropiadas
- Logging detallado de errores
- Manejo de excepciones en todos los endpoints

## 📈 Monitoreo y Logs

### Health Check
```bash
curl http://localhost:8000/health
```

### Logs de la Aplicación
Los logs se generan automáticamente y incluyen:
- Operaciones de consulta de facturas
- Errores de base de datos
- Métricas de rendimiento
- Accesos a la API

## 🚀 Despliegue en Producción

### Variables de Entorno de Producción
```env
DEBUG=False
LOG_LEVEL=WARNING
DATABASE_URL_FACTURAS=production_connection_string
DATABASE_URL_CLIENTES=production_connection_string
# Notificador de consultores (opcional)
NOTIFIER_SMTP_HOST=smtp.servidor.com
NOTIFIER_SMTP_PORT=587
NOTIFIER_SMTP_USER=usuario
NOTIFIER_SMTP_PASSWORD=clave
NOTIFIER_SMTP_FROM=notificaciones@dominio.com
NOTIFIER_SMTP_STARTTLS=1

```

### Configuración del Servidor
```bash
# Usando systemctl (recomendado)
sudo systemctl start gestor-facturas-backend
sudo systemctl enable gestor-facturas-backend

# Verificar estado
sudo systemctl status gestor-facturas-backend
```

### Monitoreo
- Health checks automáticos
- Logs centralizados
- Métricas de rendimiento
- Alertas de errores

## 🤝 Contribución al Proyecto

### Flujo de Trabajo
1. Fork del repositorio
2. Crear rama feature: `git checkout -b feature/nueva-funcionalidad`
3. Commit de cambios: `git commit -m "Agregar nueva funcionalidad"`
4. Push a la rama: `git push origin feature/nueva-funcionalidad`
5. Crear Pull Request

### Estándares de Código
- Seguir PEP 8 para Python
- Documentar funciones y clases
- Incluir pruebas para nuevas funcionalidades
- Mantener cobertura de código alta

## 📞 Soporte y Contacto

### Equipo de Desarrollo
- **Desarrollador Principal**: Angel Rodriguez
- **Email**: angel.rodriguez@atisa.es
- **Organización**: ATISA

### Repositorio
- **GitHub**: [https://github.com/developersatisa/gestor_back_facturas_pendientes](https://github.com/developersatisa/gestor_back_facturas_pendientes)
- **Issues**: Reportar bugs y solicitar funcionalidades
- **Wiki**: Documentación adicional y guías

## 📄 Licencia

Este proyecto es propiedad de **ATISA** y está destinado para uso interno de la empresa.

## 🔄 Historial de Versiones

### v1.0.0 (Actual)
- ✅ API REST completa para gestión de facturas
- ✅ Integración con base de datos corporativa
- ✅ Sistema de filtrado y consultas avanzadas
- ✅ Arquitectura limpia y escalable
- ✅ Documentación completa
- ✅ Tests unitarios

---
**Desarrollado por el equipo de ATISA**

*Última actualización: Agosto 2025* 
## Cambios Recientes (Gestión / Sociedades / Registro)

- Gestión en BD real (ATISA_Input): consultores (`dbo.consultores`), asignaciones (`dbo.cliente_consultor`), registro de acciones (`dbo.factura_acciones`) y cambios (`dbo.factura_cambios`). Sin claves foráneas, creación automática al arranque si hay permisos.
- Endpoints nuevos:
  - Consultores: `GET/POST/PUT/DELETE /api/consultores`
  - Asignación: `GET /api/consultores/asignacion/{idcliente}`, `POST /api/consultores/asignar`, `DELETE /api/consultores/asignacion/{idcliente}`, `GET /api/consultores/asignaciones`
  - Registro de facturas: `POST/GET /api/facturas/acciones`, `POST/GET /api/facturas/cambios`
- Columnas de registro:
  - `factura_acciones`: `idcliente`, `tercero (BPR_0)`, `tipo (TYP_0)`, `asiento (ACCNUM_0)`, `accion_tipo`, `descripcion`, `aviso`, `usuario`, `creado_en`.
  - `factura_cambios`: `idcliente`, `tercero`, `tipo`, `asiento`, `numero_anterior/numero_nuevo`, `monto_anterior/monto_nuevo`, `vencimiento_anterior/vencimiento_nuevo`, `motivo`, `usuario`, `creado_en`.
- Filtro por sociedades (CPY_0): todas las consultas de facturas y estadísticas limitadas a `S005` (Grupo Atisa BPO), `S001` (Asesores Titulados), `S010` (Selier by Atisa). Endpoints aceptan `?sociedad=` para acotar.
// Nota: El criterio de selección vuelve al original del proyecto.
- Etiqueta de sociedad en respuestas de facturas: se añade `sociedad_nombre` junto a `sociedad`.
- Nombre de factura: se añade `nombre_factura` mapeado desde `NUM_0` en X3.
- Solo se consideran facturas vencidas en consultas: DUDDAT_0 < GETDATE().

### Automatización de avisos por correo

- Script CLI dedicado `facturas_backend/scripts/enviar_acciones_pendientes.py` que emite las acciones cuya fecha de aviso ya venció. Carga las variables de entorno vía `.env`, reutiliza `RepositorioRegistroFacturas.enviar_pendientes` y deja trazas legibles.
- Ejecución manual (útil para diagnóstico):
  ```bash
  cd facturas_backend
  source venv/bin/activate
  python scripts/enviar_acciones_pendientes.py --log-level DEBUG
  ```
- Programación con cron (ejemplo cada 5 minutos, como root):
  ```cron
  */5 * * * * cd /ruta/al/proyecto/facturas_backend && /usr/bin/env bash -lc 'source /ruta/al/venv/bin/activate && python scripts/enviar_acciones_pendientes.py >> /var/log/facturas_acciones.log 2>&1'
  ```
  - Asegúrate de `chmod +x` al script y de crear el log (`sudo touch /var/log/facturas_acciones.log`).
  - Define las variables SMTP (`NOTIFIER_SMTP_*`) en un entorno visible para cron (`/etc/environment` o similar).

