from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config.settings import get_db_facturas_url, get_db_clientes_url

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