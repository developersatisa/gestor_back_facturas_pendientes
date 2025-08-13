from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.interfaces.facturas_controller import router as facturas_router

# Orígenes permitidos para CORS
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://10.150.22.15:5173",
    "http://10.15.29.7:5173",  # Frontend del proyecto separado
    "*"  # Temporal para desarrollo
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

# Health check
@app.get("/health", tags=["Status"])
def health_check():
    return {
        "status": "ok",
        "title": "API Facturas Atisa",
        "version": "1.0.0"
    } 