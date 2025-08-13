from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Base de datos para facturas (x3v12)
    DATABASE_FACTURAS_URL: str
    # Base de datos para clientes (ATISA_Input)
    DATABASE_CLIENTES_URL: str
    ADMIN_API_KEY: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FILE_STORAGE_ROOT: str
    CLIENT_ID: Optional[str] = None
    CLIENT_SECRET: Optional[str] = None
    TENANT_ID: Optional[str] = None
    REDIRECT_URI: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()

def get_db_facturas_url():
    return settings.DATABASE_FACTURAS_URL

def get_db_clientes_url():
    return settings.DATABASE_CLIENTES_URL 