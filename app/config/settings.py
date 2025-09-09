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
