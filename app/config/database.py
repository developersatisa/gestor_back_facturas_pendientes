from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from app.config.settings import (
    get_db_facturas_url,
    get_db_clientes_url,
    get_historial_db_url,
)

# Configuración para base de datos de facturas (x3v12)
FACTURAS_DATABASE_URL = get_db_facturas_url()
facturas_engine = create_engine(FACTURAS_DATABASE_URL)
FacturasSessionLocal = sessionmaker(bind=facturas_engine)

# Configuración para base de datos de clientes (ATISA_Input)
CLIENTES_DATABASE_URL = get_db_clientes_url()
clientes_engine = create_engine(CLIENTES_DATABASE_URL)
ClientesSessionLocal = sessionmaker(bind=clientes_engine)

Base = declarative_base()

def get_facturas_db():
    """Dependency para obtener sesión de base de datos de facturas"""
    db = FacturasSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_clientes_db():
    """Dependency para obtener sesión de base de datos de clientes"""
    db = ClientesSessionLocal()
    try:
        yield db
    finally:
        db.close() 

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
    finally:
        db.close()

def init_historial_db(metadata):
    """Crea tablas del historial si no existen.

    Recibe el objeto Base.metadata del historial para evitar dependencia circular.
    """
    metadata.create_all(bind=historial_engine)

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
    finally:
        db.close()


def init_gestion_db(metadata):
    """Crea tablas de gestión en el engine configurado (clientes o override)."""
    metadata.create_all(bind=gestion_engine)


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
    """Añade columnas nuevas si faltan (idcliente en acciones y cambios).

    Soporta MSSQL y SQLite. Silencioso si no aplica o ya existen.
    """
    try:
        with gestion_engine.begin() as conn:
            # Detectar dialecto
            dialect = conn.dialect.name
            if dialect == 'mssql':
                # factura_acciones.idcliente
                conn.execute(text("IF COL_LENGTH('dbo.factura_acciones','idcliente') IS NULL ALTER TABLE dbo.factura_acciones ADD idcliente INT NULL;"))
                # Limpieza en facturas_cambio_pago: asegurar columna monto_pagado y eliminar creado_en si existe
                # facturas_cambio_pago.monto_pagado (si existe la tabla)
                conn.execute(text("IF 1=0 AND OBJECT_ID('dbo.facturas_cambio_pago','U') IS NOT NULL AND COL_LENGTH('dbo.facturas_cambio_pago','monto_pagado') IS NULL ALTER TABLE dbo.facturas_cambio_pago ADD monto_pagado DECIMAL(18,2) NULL;"))
                # facturas_cambio_pago.idcliente (guardar BPR_0 como NVARCHAR)
                conn.execute(text("IF 1=0 AND OBJECT_ID('dbo.facturas_cambio_pago','U') IS NOT NULL AND COL_LENGTH('dbo.facturas_cambio_pago','idcliente') IS NULL ALTER TABLE dbo.facturas_cambio_pago ADD idcliente NVARCHAR(50) NULL;"))
                # Eliminar default constraint y columna creado_en si existe
                conn.execute(text("IF 1=0 AND OBJECT_ID('dbo.facturas_cambio_pago','U') IS NOT NULL AND COL_LENGTH('dbo.facturas_cambio_pago','creado_en') IS NOT NULL BEGIN IF OBJECT_ID('DF_facturas_cambio_pago_creado','D') IS NOT NULL ALTER TABLE dbo.facturas_cambio_pago DROP CONSTRAINT DF_facturas_cambio_pago_creado; ALTER TABLE dbo.facturas_cambio_pago DROP COLUMN creado_en; END"))
            else:
                # SQLite u otros: intentar ALTER TABLE ADD COLUMN en factura_acciones si no existe
                try:
                    conn.execute(text("ALTER TABLE factura_acciones ADD COLUMN idcliente INTEGER"))
                except Exception:
                    pass
                # Intentar añadir columnas en facturas_cambio_pago si existe
                try:
                    conn.execute(text("/* disabled */ SELECT 1"))
                except Exception:
                    pass
                try:
                    conn.execute(text("/* disabled */ SELECT 1"))
                except Exception:
                    pass
    except Exception:
        # No bloquear arranque por migración suave
        pass


def ensure_gestion_tables():
    """Crea explícitamente tablas de acciones y cambios en MSSQL si no existen.

    En otros motores se confía en SQLAlchemy create_all.
    """
    try:
        with gestion_engine.begin() as conn:
            dialect = conn.dialect.name
            if dialect == 'mssql':
                # Tabla factura_acciones
                conn.execute(text(
                    """
                    IF OBJECT_ID(N'dbo.factura_acciones', N'U') IS NULL
                    BEGIN
                        CREATE TABLE dbo.factura_acciones (
                            id INT IDENTITY(1,1) PRIMARY KEY,
                            idcliente INT NULL,
                            tercero NVARCHAR(50) NOT NULL,
                            tipo NVARCHAR(10) NOT NULL,
                            asiento NVARCHAR(50) NOT NULL,
                            accion_tipo NVARCHAR(50) NOT NULL,
                            descripcion NVARCHAR(MAX) NULL,
                            aviso DATETIME2 NULL,
                            usuario NVARCHAR(100) NULL,
                            creado_en DATETIME2 NOT NULL CONSTRAINT DF_factura_acciones_creado DEFAULT(SYSDATETIME())
                        );
                    END
                    """
                ))
                # Tabla facturas_cambio_pago (historial de pagos de facturas, mínima)
                conn.execute(text(
                    """
                    -- deshabilitado: creación movida a x3v12.ATISAINT
                    IF 1=0 AND OBJECT_ID(N'dbo.facturas_cambio_pago', N'U') IS NULL
                    BEGIN
                        CREATE TABLE dbo.facturas_cambio_pago (
                            id INT IDENTITY(1,1) PRIMARY KEY,
                            factura_id NVARCHAR(64) NOT NULL,
                            fecha_cambio DATE NOT NULL,
                            monto_pagado DECIMAL(18,2) NULL,
                            idcliente NVARCHAR(50) NULL
                        );
                    END
                    """
                ))
            else:
                # No crear explícitamente en otros motores aquí; se gestionará vía ORM/migraciones si aplica.
                pass
    except Exception:
        # No bloquear el arranque si falla
        pass


def ensure_facturas_pago_table():
    """
    Crea el esquema ATISAINT (si no existe) y la tabla ATISAINT.facturas_cambio_pago con columnas:
    - id INT IDENTITY PK
    - factura_id NVARCHAR(64) NOT NULL (SIN restricción UNIQUE para permitir múltiples pagos)
    - fecha_cambio DATE NOT NULL
    - monto_pagado DECIMAL(18,2) NULL
    - idcliente NVARCHAR(50) NULL

    En motores no MSSQL, intenta crear una tabla equivalente sin esquema.
    """
    try:
        with facturas_engine.begin() as conn:
            dialect = conn.dialect.name
            if dialect == 'mssql':
                # Crear esquema ATISAINT si no existe
                conn.execute(text("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ATISAINT') EXEC('CREATE SCHEMA ATISAINT');"))
                
                # Crear tabla solo si no existe (sin restricción UNIQUE)
                conn.execute(text(
                    """
                    IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'ATISAINT.facturas_cambio_pago') AND type in (N'U'))
                    BEGIN
                        CREATE TABLE ATISAINT.facturas_cambio_pago (
                            id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                            factura_id NVARCHAR(64) NOT NULL,
                            fecha_cambio DATE NOT NULL,
                            monto_pagado DECIMAL(18,2) NULL,
                            idcliente NVARCHAR(50) NULL
                        );
                    END
                    """
                ))
                
                # Crear índice para mejorar consultas por factura_id (solo si no existe)
                conn.execute(text("""
                    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_facturas_cambio_pago_factura_id' AND object_id = OBJECT_ID('ATISAINT.facturas_cambio_pago'))
                    BEGIN
                        CREATE INDEX IX_facturas_cambio_pago_factura_id ON ATISAINT.facturas_cambio_pago(factura_id);
                    END
                """))
    except Exception:
        # No bloquear arranque
        pass
