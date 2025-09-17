from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.interfaces.facturas_controller import router as facturas_router
from app.interfaces.historial_controller import router as historial_router
from app.interfaces.consultores_controller import router as consultores_router
from app.interfaces.registro_facturas_controller import router as registro_facturas_router
from app.config.database import (
    init_historial_db,
    HistorialBase,
    init_gestion_db,
    GestionBase,
    ensure_clientes_database,
    ensure_gestion_columns,
    ensure_gestion_tables,
    ensure_facturas_pago_table,
)

# Orígenes permitidos para CORS
origins = [
    "http://localhost:5173",
    "http://10.150.22.15:5173"
]

app = FastAPI(
    title="API Facturas Atisa",
    version="1.0.0",
    description="API para gestión de facturas y clientes de Atisa"
)

# Middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de logging
logging.basicConfig(level=logging.INFO)

# Registro de routers
app.include_router(facturas_router)
app.include_router(historial_router)
app.include_router(consultores_router)
app.include_router(registro_facturas_router)

# Health check
@app.get("/health", tags=["Status"])
def health_check():
    return {
        "status": "ok",
        "title": "API Facturas Atisa",
        "version": "1.0.0"
    }

# Inicialización de BD local de historial y gestión
@app.on_event("startup")
def startup_event():
    try:
        init_historial_db(HistorialBase.metadata)
    except Exception:
        # No interrumpir el arranque por el historial
        pass
    try:
        # Asegurar BD de clientes (si apunta a MSSQL) para crear tablas de gestión ahí
        ensure_clientes_database()
        init_gestion_db(GestionBase.metadata)
        ensure_gestion_tables()
        ensure_gestion_columns()
    except Exception:
        pass
    try:
        # Asegurar tabla de pagos en BD de facturas (SAGE X3)
        ensure_facturas_pago_table()
    except Exception:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
