import os
from functools import lru_cache
from dotenv import load_dotenv

# Carga variables desde .env si existe
load_dotenv()

# Valores por defecto seguros para desarrollo (evitan fallos al importar)
DEFAULT_FACTURAS_URL = os.getenv("DEFAULT_SQLALCHEMY_URL_FACTURAS", "sqlite:///./facturas.db")
DEFAULT_CLIENTES_URL = os.getenv("DEFAULT_SQLALCHEMY_URL_CLIENTES", "sqlite:///./clientes.db")
DEFAULT_HISTORIAL_URL = os.getenv("DEFAULT_HISTORIAL_SQLALCHEMY_URL", "sqlite:///./facturas_historial.db")
DEFAULT_GESTION_URL = os.getenv("DEFAULT_SQLALCHEMY_URL_GESTION", "sqlite:///./gestion_facturas.db")
DEFAULT_FRONTEND_BASE = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
DEFAULT_AUTH_REDIRECT = os.getenv("AUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
DEFAULT_JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-this")
DEFAULT_JWT_EXPIRES = int(os.getenv("JWT_EXPIRES_SECONDS", "3600"))
DEFAULT_ODBC_DRIVER = os.getenv("ODBC_DRIVER_NAME", os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server"))


def _get_first_env(keys: list[str], default: str) -> str:
    """Devuelve el primer valor definido entre varias claves de entorno."""
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return default


@lru_cache()
def get_db_facturas_url() -> str:
    """Obtiene la URL de conexión para la BD de facturas.

    Acepta múltiples nombres de variables para compatibilidad:
    - DATABASE_URL_FACTURAS (preferida)
    - DATABASE_FACTURAS_URL (compatibilidad con .env existente)
    """
    return _get_first_env([
        "DATABASE_URL_FACTURAS",
        "DATABASE_FACTURAS_URL",
    ], DEFAULT_FACTURAS_URL)


@lru_cache()
def get_db_clientes_url() -> str:
    """Obtiene la URL de conexión para la BD de clientes.

    Acepta múltiples nombres de variables para compatibilidad:
    - DATABASE_URL_CLIENTES (preferida)
    - DATABASE_CLIENTES_URL (compatibilidad con .env existente)
    """
    return _get_first_env([
        "DATABASE_URL_CLIENTES",
        "DATABASE_CLIENTES_URL",
    ], DEFAULT_CLIENTES_URL)


@lru_cache()
def get_historial_db_url() -> str:
    """Obtiene la URL de conexión para la BD local de historial.

    Variables aceptadas (en orden):
    - HISTORIAL_DATABASE_URL
    - DATABASE_URL_HISTORIAL
    - DATABASE_HISTORIAL_URL
    Si ninguna está definida, usa SQLite local ./facturas_historial.db
    """
    return _get_first_env([
        "HISTORIAL_DATABASE_URL",
        "DATABASE_URL_HISTORIAL",
        "DATABASE_HISTORIAL_URL",
    ], DEFAULT_HISTORIAL_URL)


@lru_cache()
def get_gestion_db_url() -> str:
    """Obtiene la URL de conexión para la BD de gestión (consultores y asignaciones).

    Variables aceptadas (en orden):
    - GESTION_DATABASE_URL
    - DATABASE_URL_GESTION
    - DATABASE_GESTION_URL
    Si ninguna está definida, usa SQLite local ./gestion_facturas.db
    """
    return _get_first_env([
        "GESTION_DATABASE_URL",
        "DATABASE_URL_GESTION",
        "DATABASE_GESTION_URL",
    ], DEFAULT_GESTION_URL)


# Azure AD / Auth settings
@lru_cache()
def get_azure_client_id() -> str:
    return _get_first_env([
        "AZURE_CLIENT_ID",
        "CLIENT_ID",
    ], "")


@lru_cache()
def get_azure_tenant_id() -> str:
    return _get_first_env([
        "AZURE_TENANT_ID",
        "TENANT_ID",
    ], "common")


@lru_cache()
def get_azure_client_secret() -> str:
    return _get_first_env([
        "AZURE_CLIENT_SECRET",
        "CLIENT_SECRET",
    ], "")


@lru_cache()
def get_frontend_base_url() -> str:
    return _get_first_env([
        "FRONTEND_BASE_URL",
    ], DEFAULT_FRONTEND_BASE)


@lru_cache()
def get_auth_redirect_uri() -> str:
    return _get_first_env([
        "AUTH_REDIRECT_URI",
    ], DEFAULT_AUTH_REDIRECT)


@lru_cache()
def get_jwt_secret() -> str:
    return _get_first_env([
        "JWT_SECRET",
    ], DEFAULT_JWT_SECRET)


@lru_cache()
def get_jwt_expires_seconds() -> int:
    try:
        return int(_get_first_env([
            "JWT_EXPIRES_SECONDS",
        ], str(DEFAULT_JWT_EXPIRES)))
    except Exception:
        return DEFAULT_JWT_EXPIRES


# ODBC driver name for pyodbc (MSSQL)
@lru_cache()
def get_odbc_driver_name() -> str:
    return DEFAULT_ODBC_DRIVER
