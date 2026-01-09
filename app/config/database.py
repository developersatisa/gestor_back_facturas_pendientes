from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from app.config.settings import (
    get_db_facturas_url,
    get_db_clientes_url,
    get_historial_db_url,
    get_odbc_driver_name,
)
from app.infrastructure.database_migrations import (
    initialize_gestion_tables,
    create_cliente_consultor_indexes,
    initialize_facturas_pago_table,
)
import logging

logger = logging.getLogger("db")


def _augment_pyodbc_url(url_str: str) -> str:
    """Ensure pyodbc URL includes an explicit driver to avoid IM002.

    If using mssql+pyodbc without `driver=` or `odbc_connect=`, append
    `driver=<name>&TrustServerCertificate=yes&Connection+Timeout=60`.
    
    Supports:
    - Named instances: IP\INSTANCE
    - Port-based connections: IP,port or IP:port
    - Uses odbc_connect for better compatibility with special characters in passwords.
    """
    try:
        if url_str and url_str.startswith("mssql+pyodbc") and "odbc_connect=" not in url_str:
            import re
            from urllib.parse import quote_plus, unquote, parse_qs, urlparse
            
            # Extraer parámetros de la URL para respetar Encrypt y otros parámetros
            parsed = urlparse(url_str)
            query_params = parse_qs(parsed.query)
            
            # Determinar valores de Encrypt y TrustServerCertificate desde la URL
            encrypt_value = "no"
            if "Encrypt" in query_params:
                encrypt_value = query_params["Encrypt"][0].lower()
            elif "Encrypt=yes" in url_str or "Encrypt%3Dyes" in url_str:
                encrypt_value = "yes"
            
            trust_cert = "yes"
            if "TrustServerCertificate" in query_params:
                trust_cert = query_params["TrustServerCertificate"][0].lower()
            elif "TrustServerCertificate=no" in url_str or "TrustServerCertificate%3Dno" in url_str:
                trust_cert = "no"
            
            # Patrón 1: Instancia nombrada con IP: IP\INSTANCE
            pattern_instance = r'mssql\+pyodbc://([^:]+):([^@]+)@(\d+\.\d+\.\d+\.\d+)\\([^/]+)/([^?]+)'
            match_instance = re.search(pattern_instance, url_str)
            
            if match_instance:
                # Tenemos una instancia con nombre usando IP - usar odbc_connect
                user = match_instance.group(1)
                password = unquote(match_instance.group(2))  # Decodificar contraseña
                ip = match_instance.group(3)
                instance = match_instance.group(4)
                database = match_instance.group(5)
                
                driver = get_odbc_driver_name()
                server_name = f"{ip}\\{instance}"
                
                # Construir cadena ODBC respetando los valores de Encrypt de la URL
                odbc_str = (
                    f"DRIVER={{{driver}}};"
                    f"SERVER={server_name};"
                    f"DATABASE={database};"
                    f"UID={user};"
                    f"PWD={password};"
                    f"TrustServerCertificate={trust_cert};"
                    f"Encrypt={encrypt_value};"
                    f"Connection Timeout=60;"
                    f"MultiSubnetFailover=no"
                )
                
                odbc_encoded = quote_plus(odbc_str)
                url_str = f"mssql+pyodbc://?odbc_connect={odbc_encoded}"
                logger.info(f"Construida cadena ODBC para instancia nombrada: {server_name} (BD: {database}, Encrypt={encrypt_value})")
                return url_str
            
            # Patrón 2: Conexión por puerto con formato IP,puerto o IP:puerto
            pattern_port_comma = r'mssql\+pyodbc://([^:]+):([^@]+)@(\d+\.\d+\.\d+\.\d+),(\d+)/([^?]+)'
            pattern_port_colon = r'mssql\+pyodbc://([^:]+):([^@]+)@(\d+\.\d+\.\d+\.\d+):(\d+)/([^?]+)'
            
            match_port_comma = re.search(pattern_port_comma, url_str)
            match_port_colon = re.search(pattern_port_colon, url_str)
            
            if match_port_comma or match_port_colon:
                match_port = match_port_comma or match_port_colon
                user = match_port.group(1)
                password = unquote(match_port.group(2))  # Decodificar contraseña
                ip = match_port.group(3)
                port = match_port.group(4)
                database = match_port.group(5)
                
                driver = get_odbc_driver_name()
                # Formato ODBC para puerto: IP,puerto (con coma)
                server_name = f"{ip},{port}"
                
                # Construir cadena ODBC respetando los valores de Encrypt de la URL
                odbc_str = (
                    f"DRIVER={{{driver}}};"
                    f"SERVER={server_name};"
                    f"DATABASE={database};"
                    f"UID={user};"
                    f"PWD={password};"
                    f"TrustServerCertificate={trust_cert};"
                    f"Encrypt={encrypt_value};"
                    f"Connection Timeout=60;"
                    f"MultiSubnetFailover=no"
                )
                
                odbc_encoded = quote_plus(odbc_str)
                url_str = f"mssql+pyodbc://?odbc_connect={odbc_encoded}"
                logger.info(f"Construida cadena ODBC para conexión por puerto: {server_name} (BD: {database}, Encrypt={encrypt_value})")
                return url_str
            
            # Si no hay instancia nombrada ni puerto, procesar normalmente
            # Asegurar que tenga driver
            if "driver=" not in url_str:
                driver = get_odbc_driver_name().replace(" ", "+")
                sep = "&" if "?" in url_str else "?"
                url_str = f"{url_str}{sep}driver={driver}"
            
            # Asegurar que tenga TrustServerCertificate (solo si no está ya especificado)
            if "TrustServerCertificate=" not in url_str and "TrustServerCertificate%3D" not in url_str:
                sep = "&" if "?" in url_str else "?"
                url_str = f"{url_str}{sep}TrustServerCertificate=yes"
            
            # Asegurar que tenga Connection Timeout aumentado
            if "Connection+Timeout=" not in url_str and "Connection%20Timeout=" not in url_str:
                sep = "&" if "?" in url_str else "?"
                url_str = f"{url_str}{sep}Connection+Timeout=60"
    except Exception as e:
        logger.warning(f"Error procesando URL pyodbc: {e}")
    return url_str


def _log_available_odbc_drivers():
    try:
        import pyodbc  # type: ignore
        drivers = pyodbc.drivers()
    except Exception as e:
        logger.warning(f"No se pudieron listar drivers ODBC: {e}")

# Configuración para base de datos de facturas (x3v12)
FACTURAS_DATABASE_URL = _augment_pyodbc_url(get_db_facturas_url())
facturas_engine = create_engine(
    FACTURAS_DATABASE_URL,
    pool_size=5,            # Pool pequeño para evitar conexiones colgadas
    max_overflow=5,         # Overflow mínimo
    pool_timeout=30,        # Timeout razonable
    pool_recycle=300,       # Reciclar conexiones cada 5 minutos (muy frecuente)
    pool_pre_ping=True,     # Verificar conexiones antes de usar
    pool_reset_on_return='rollback',  # Rollback para limpiar transacciones
    echo=False,             # Desactivar logging SQL
    connect_args={
        "timeout": 60,      # Timeout aumentado para conexiones lentas/instancias con nombre
        "autocommit": False,
        "charset": "utf8mb4"
    }
)
FacturasSessionLocal = sessionmaker(bind=facturas_engine)

# Configuración para base de datos de clientes (ATISA_Input)
CLIENTES_DATABASE_URL = _augment_pyodbc_url(get_db_clientes_url())
clientes_engine = create_engine(
    CLIENTES_DATABASE_URL,
    pool_size=5,            # Pool pequeño para evitar conexiones colgadas
    max_overflow=5,         # Overflow mínimo
    pool_timeout=30,        # Timeout razonable
    pool_recycle=300,       # Reciclar conexiones cada 5 minutos (muy frecuente)
    pool_pre_ping=True,     # Verificar conexiones antes de usar
    pool_reset_on_return='rollback',  # Rollback para limpiar transacciones
    echo=False,             # Desactivar logging SQL
    connect_args={
        "timeout": 60,      # Timeout aumentado para conexiones lentas/instancias con nombre
        "autocommit": False,
        "charset": "utf8mb4"
    }
)
ClientesSessionLocal = sessionmaker(bind=clientes_engine)

Base = declarative_base()

def get_facturas_db():
    """Dependency para obtener sesión de base de datos de facturas"""
    db = FacturasSessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión de facturas: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception as e:
            logger.warning(f"Error cerrando sesión de facturas: {e}")

def get_clientes_db():
    """Dependency para obtener sesión de base de datos de clientes"""
    db = ClientesSessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión de clientes: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception as e:
            logger.warning(f"Error cerrando sesión de clientes: {e}") 

# Configuración para base de datos de historial (local, SQLite por defecto)
HISTORIAL_DATABASE_URL = get_historial_db_url()
historial_engine = create_engine(HISTORIAL_DATABASE_URL)
HistorialSessionLocal = sessionmaker(bind=historial_engine)

# Base separada para el historial (permite distinto motor)
HistorialBase = declarative_base()

def get_historial_db():
    """Dependency para obtener sesión de base de datos de historial"""
    db = HistorialSessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión de historial: {e}")
        db.rollback()
        raise
    finally:
        try:
            db.close()
        except Exception as e:
            logger.warning(f"Error cerrando sesión de historial: {e}")

def init_historial_db(metadata):
    """Crea tablas del historial si no existen.

    Recibe el objeto Base.metadata del historial para evitar dependencia circular.
    """
    metadata.create_all(bind=historial_engine)


def log_odbc_env_diagnostics():
    """Optional helper to log pyodbc driver availability at startup."""
    try:
        if FACTURAS_DATABASE_URL.startswith("mssql+pyodbc") or CLIENTES_DATABASE_URL.startswith("mssql+pyodbc"):
            _log_available_odbc_drivers()
            # Log información sobre las URLs de conexión (sin contraseñas)
            if FACTURAS_DATABASE_URL.startswith("mssql+pyodbc"):
                # Extraer información sin exponer contraseñas
                import re
                match = re.search(r'mssql\+pyodbc://([^:]+):[^@]+@([^?]+)', FACTURAS_DATABASE_URL)
                if match:
                    logger.info(f"URL Facturas: mssql+pyodbc://{match.group(1)}:***@{match.group(2)}")
            if CLIENTES_DATABASE_URL.startswith("mssql+pyodbc"):
                import re
                match = re.search(r'mssql\+pyodbc://([^:]+):[^@]+@([^?]+)', CLIENTES_DATABASE_URL)
                if match:
                    logger.info(f"URL Clientes: mssql+pyodbc://{match.group(1)}:***@{match.group(2)}")
    except Exception as e:
        logger.warning(f"Error en diagnóstico ODBC: {e}")


def log_pool_status():
    """Log del estado actual de los pools de conexión para diagnóstico."""
    try:
        # Pool de facturas
        facturas_pool = facturas_engine.pool
        
        # Pool de clientes
        clientes_pool = clientes_engine.pool
    except Exception as e:
        logger.warning(f"Error obteniendo estado del pool: {e}")


def force_pool_cleanup():
    """Fuerza la limpieza de conexiones inactivas en todos los pools."""
    try:
        facturas_engine.pool.recreate()
        clientes_engine.pool.recreate()
    except Exception as e:
        logger.error(f"Error recreando pools: {e}")


def cleanup_stale_connections():
    """Limpia conexiones colgadas específicamente para MySQL/MariaDB."""
    try:
        # Para MySQL/MariaDB, ejecutar comandos de limpieza
        with facturas_engine.connect() as conn:
            # Matar conexiones inactivas (más de 5 minutos)
            conn.execute(text("""
                SELECT CONCAT('KILL ', id, ';') as kill_command 
                FROM information_schema.processlist 
                WHERE command = 'Sleep' 
                AND time > 300 
                AND user != 'system user'
                AND db IS NOT NULL
            """))
            
        with clientes_engine.connect() as conn:
            conn.execute(text("""
                SELECT CONCAT('KILL ', id, ';') as kill_command 
                FROM information_schema.processlist 
                WHERE command = 'Sleep' 
                AND time > 300 
                AND user != 'system user'
                AND db IS NOT NULL
            """))
            
    except Exception as e:
        logger.warning(f"No se pudieron limpiar conexiones colgadas: {e}")


def get_connection_stats():
    """Obtiene estadísticas de conexiones activas."""
    stats = {}
    try:
        with facturas_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_connections,
                    SUM(CASE WHEN command = 'Sleep' THEN 1 ELSE 0 END) as sleeping_connections,
                    SUM(CASE WHEN time > 300 THEN 1 ELSE 0 END) as stale_connections
                FROM information_schema.processlist 
                WHERE user != 'system user'
            """))
            row = result.fetchone()
            stats['facturas'] = {
                'total': row[0] if row else 0,
                'sleeping': row[1] if row else 0,
                'stale': row[2] if row else 0
            }
    except Exception as e:
        stats['facturas'] = {'error': str(e)}
    
    try:
        with clientes_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_connections,
                    SUM(CASE WHEN command = 'Sleep' THEN 1 ELSE 0 END) as sleeping_connections,
                    SUM(CASE WHEN time > 300 THEN 1 ELSE 0 END) as stale_connections
                FROM information_schema.processlist 
                WHERE user != 'system user'
            """))
            row = result.fetchone()
            stats['clientes'] = {
                'total': row[0] if row else 0,
                'sleeping': row[1] if row else 0,
                'stale': row[2] if row else 0
            }
    except Exception as e:
        stats['clientes'] = {'error': str(e)}
    
    return stats

"""
Gestión (consultores, asignaciones y registro de facturas)
- Siempre usa la misma BD que clientes (ATISA_Input)
"""
GestionBase = declarative_base()
gestion_engine = clientes_engine
GestionSessionLocal = ClientesSessionLocal


def get_gestion_db():
    """Sesión para tablas de gestión (usa override si está definido)."""
    db = GestionSessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión de gestión: {e}")
        db.rollback()
        raise
    finally:
        try:
            db.close()
        except Exception as e:
            logger.warning(f"Error cerrando sesión de gestión: {e}")


def init_gestion_db(metadata):
    """
    Crea tablas de gestión usando SQLAlchemy metadata y luego aplica migraciones.
    
    Args:
        metadata: SQLAlchemy metadata del GestionBase
    """
    try:
        if gestion_engine.dialect.name == 'mssql':
            metadata.create_all(bind=gestion_engine)
            _ensure_cliente_consultor_schema()
    except Exception:
        # No bloquear arranque
        pass


# Utilidades de inicialización condicional de BD (para MSSQL)
def _ensure_database_exists_for_url(db_url: str):
    try:
        url = make_url(db_url)
    except Exception:
        return

    # Solo aplica a MSSQL; en SQLite y otros no es necesario
    if not str(url.drivername).startswith("mssql"):
        return

    target_db = url.database
    if not target_db:
        return

    # Construir URL a la BD 'master'
    master_url = url.set(database="master")

    try:
        master_engine = create_engine(master_url)
        with master_engine.connect() as conn:
            # Crear BD si no existe
            conn.execute(text(f"IF DB_ID(N'{target_db}') IS NULL CREATE DATABASE [{target_db}];"))
    except Exception:
        # En caso de fallo, no bloquear el arranque
        pass


def ensure_clientes_database():
    """Garantiza que la BD de clientes exista (solo MSSQL)."""
    _ensure_database_exists_for_url(CLIENTES_DATABASE_URL)


def ensure_gestion_database():
    """Compatibilidad: la gestión usa la BD de clientes, no hay override."""
    # No-op; se garantiza con ensure_clientes_database()
    return None


def ensure_gestion_columns():
    """
    DEPRECATED: Esta función se mantiene por compatibilidad pero la lógica
    se ha movido a database_migrations.py
    
    La migración de columnas ahora se hace automáticamente en initialize_gestion_tables().
    """
    # La lógica se movió a database_migrations.migrate_consultores_columns()
    # y database_migrations.migrate_factura_acciones_columns()
    pass


def ensure_gestion_tables():
    """
    Crea explícitamente tablas de gestión en MSSQL si no existen.

    DEPRECATED: Esta función ahora delega a database_migrations.initialize_gestion_tables()
    para mantener el código organizado.
    """
    initialize_gestion_tables(gestion_engine)


def _ensure_cliente_consultor_schema():
    """
    Ajusta la tabla cliente_consultor para que permita histórico de asignaciones.

    DEPRECATED: Esta función ahora delega a database_migrations.create_cliente_consultor_indexes()
    para mantener el código organizado.
    """
    try:
        with gestion_engine.begin() as conn:
            if gestion_engine.dialect.name == 'mssql':
                create_cliente_consultor_indexes(conn)
    except Exception:
        pass


def ensure_facturas_pago_table():
    """
    Crea el esquema ATISAINT (si no existe) y la tabla ATISAINT.facturas_cambio_pago.
    
    DEPRECATED: Esta función ahora delega a database_migrations.initialize_facturas_pago_table()
    para mantener el código organizado.
    """
    initialize_facturas_pago_table(facturas_engine)
