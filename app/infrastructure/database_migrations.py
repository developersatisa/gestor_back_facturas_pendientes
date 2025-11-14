"""
Módulo para gestión de migraciones y creación de tablas de base de datos.

Este módulo centraliza toda la lógica de creación de tablas y migraciones,
separándola de la configuración de conexiones.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine
import logging

logger = logging.getLogger("db.migrations")


def _is_mssql(engine: Engine) -> bool:
    """Verifica si el motor de base de datos es MSSQL."""
    try:
        return engine.dialect.name == 'mssql'
    except Exception:
        return False


def create_consultores_table(conn) -> None:
    """Crea la tabla de consultores si no existe."""
    conn.execute(text("""
        IF OBJECT_ID(N'dbo.consultores', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.consultores (
                id INT IDENTITY(1,1) PRIMARY KEY,
                nombre NVARCHAR(150) NOT NULL,
                estado NVARCHAR(20) NOT NULL CONSTRAINT DF_consultores_estado DEFAULT('activo'),
                email NVARCHAR(255) NULL,
                eliminado BIT NOT NULL CONSTRAINT DF_consultores_eliminado DEFAULT(0),
                creado_en DATETIME2 NOT NULL CONSTRAINT DF_consultores_creado DEFAULT(SYSDATETIME())
            );
        END
    """))


def create_factura_acciones_table(conn) -> None:
    """Crea la tabla de acciones de facturas si no existe."""
    conn.execute(text("""
        IF OBJECT_ID(N'dbo.factura_acciones', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.factura_acciones (
                id INT IDENTITY(1,1) PRIMARY KEY,
                idcliente INT NULL,
                tercero NVARCHAR(50) NOT NULL,
                tipo NVARCHAR(10) NOT NULL,
                asiento NVARCHAR(50) NOT NULL,
                accion_tipo NVARCHAR(50) NULL,
                descripcion NVARCHAR(MAX) NULL,
                aviso DATETIME2 NULL,
                destinatario NVARCHAR(255) NULL,
                envio_estado NVARCHAR(50) NULL,
                consultor_id INT NULL,
                usuario NVARCHAR(100) NULL,
                seguimiento_id INT NULL,
                enviada_en DATETIME2 NULL,
                creado_en DATETIME2 NOT NULL CONSTRAINT DF_factura_acciones_creado DEFAULT(SYSDATETIME()),
                usuario_modificacion NVARCHAR(100) NULL,
                fecha_modificacion DATETIME2 NULL
            );
        END
    """))


def migrate_factura_acciones_columns(conn) -> None:
    """Añade columnas adicionales a factura_acciones si faltan."""
    # Columnas adicionales si faltan
    conn.execute(text("IF COL_LENGTH('dbo.factura_acciones','seguimiento_id') IS NULL ALTER TABLE dbo.factura_acciones ADD seguimiento_id INT NULL;"))
    conn.execute(text("IF COL_LENGTH('dbo.factura_acciones','usuario_modificacion') IS NULL ALTER TABLE dbo.factura_acciones ADD usuario_modificacion NVARCHAR(100) NULL;"))
    conn.execute(text("IF COL_LENGTH('dbo.factura_acciones','fecha_modificacion') IS NULL ALTER TABLE dbo.factura_acciones ADD fecha_modificacion DATETIME2 NULL;"))
    
    # Migración: hacer accion_tipo nullable para permitir acciones placeholder
    conn.execute(text("""
        IF COL_LENGTH('dbo.factura_acciones','accion_tipo') IS NOT NULL 
        AND COLUMNPROPERTY(OBJECT_ID('dbo.factura_acciones'), 'accion_tipo', 'AllowsNull') = 0
        BEGIN
            ALTER TABLE dbo.factura_acciones ALTER COLUMN accion_tipo NVARCHAR(50) NULL;
        END
    """))


def migrate_consultores_columns(conn) -> None:
    """Añade columnas nuevas a consultores si faltan."""
    # Agregar columna email si no existe
    conn.execute(text("IF COL_LENGTH('dbo.consultores','email') IS NULL ALTER TABLE dbo.consultores ADD email NVARCHAR(255) NULL;"))


def create_cliente_consultor_indexes(conn) -> None:
    """Crea índices para la tabla cliente_consultor."""
    table_name = "cliente_consultor"
    
    # Obtener schema de la tabla
    result = conn.execute(
        text("""
            SELECT s.name
            FROM sys.tables t
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE t.name = :table_name
        """),
        {"table_name": table_name},
    ).first()

    if not result:
        return

    schema = result[0] or 'dbo'
    schema_prefix = f"[{schema}]." if schema else ""
    full_qualified = f"{schema}.{table_name}" if schema else table_name
    constraint_name = "uq_cliente_unico"
    index_name = "IX_cliente_consultor_idcliente_creado"

    # Eliminar constraint única legacy si existe
    conn.execute(text(f"""
        IF EXISTS (
            SELECT 1
            FROM sys.key_constraints
            WHERE parent_object_id = OBJECT_ID(N'{full_qualified}')
              AND name = N'{constraint_name}'
        )
        BEGIN
            ALTER TABLE {schema_prefix}[{table_name}] DROP CONSTRAINT {constraint_name};
        END
    """))
    
    # Crear índice no único para mejorar consultas
    conn.execute(text(f"""
        IF NOT EXISTS (
            SELECT 1
            FROM sys.indexes
            WHERE name = N'{index_name}'
              AND object_id = OBJECT_ID(N'{full_qualified}')
        )
        BEGIN
            CREATE INDEX {index_name}
            ON {schema_prefix}[{table_name}] (idcliente, creado_en DESC, id DESC);
        END
    """))


def create_facturas_pago_schema_and_table(conn) -> None:
    """Crea el esquema ATISAINT y la tabla facturas_cambio_pago."""
    # Crear esquema ATISAINT si no existe
    conn.execute(text("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ATISAINT') EXEC('CREATE SCHEMA ATISAINT');"))
    
    # Crear tabla si no existe
    conn.execute(text("""
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
    """))
    
    # Crear índice para mejorar consultas
    conn.execute(text("""
        IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_facturas_cambio_pago_factura_id' AND object_id = OBJECT_ID('ATISAINT.facturas_cambio_pago'))
        BEGIN
            CREATE INDEX IX_facturas_cambio_pago_factura_id ON ATISAINT.facturas_cambio_pago(factura_id);
        END
    """))


def initialize_gestion_tables(engine) -> None:
    """
    Inicializa todas las tablas de gestión en MSSQL.
    
    Args:
        engine: SQLAlchemy engine para la base de datos de gestión
    """
    if not _is_mssql(engine):
        return
    
    try:
        with engine.begin() as conn:
            create_consultores_table(conn)
            create_factura_acciones_table(conn)
            migrate_factura_acciones_columns(conn)
            migrate_consultores_columns(conn)
            create_cliente_consultor_indexes(conn)
    except Exception as e:
        logger.warning(f"Error inicializando tablas de gestión: {e}")


def initialize_facturas_pago_table(engine) -> None:
    """
    Inicializa la tabla de pagos en la base de datos de facturas.
    
    Args:
        engine: SQLAlchemy engine para la base de datos de facturas
    """
    if not _is_mssql(engine):
        return
    
    try:
        with engine.begin() as conn:
            create_facturas_pago_schema_and_table(conn)
    except Exception as e:
        logger.warning(f"Error inicializando tabla de pagos: {e}")

