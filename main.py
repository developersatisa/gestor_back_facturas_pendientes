import os

from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.interfaces.facturas_controller import router as facturas_router
from app.interfaces.historial_controller import router as historial_router
from app.interfaces.consultores_controller import router as consultores_router
from app.interfaces.registro_facturas_controller import router as registro_facturas_router
from app.interfaces.seguimiento_acciones_controller import router as seguimiento_acciones_router
from app.auth.routes import router as auth_router
from app.config.database import (
    init_historial_db,
    HistorialBase,
    init_gestion_db,
    GestionBase,
    ensure_clientes_database,
    ensure_gestion_columns,
    ensure_gestion_tables,
    ensure_facturas_pago_table,
    log_odbc_env_diagnostics,
)

# Orígenes permitidos para CORS
origins = [
    "http://localhost:3520",
    "http://10.150.22.15:3520",
    "https://demoimpagos.atisa.es",
    "http://demoimpagos.atisa.es",
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
app.include_router(seguimiento_acciones_router)
app.include_router(auth_router)

# Fallback para /auth/return cuando el frontend BrowserRouter
# no es servido directamente por el proxy.
@app.get("/auth/return", include_in_schema=False, response_class=HTMLResponse)
def auth_return_bridge(token: Optional[str] = None):
    html = """<!DOCTYPE html>
<html lang=\"es\">
  <head>
    <meta charset=\"utf-8\" />
    <meta http-equiv=\"Cache-Control\" content=\"no-store, max-age=0\" />
    <title>Procesando autenticación…</title>
    <style>
      body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
      .card { background: rgba(15, 23, 42, 0.85); padding: 2rem 2.5rem; border-radius: 1rem; box-shadow: 0 20px 40px rgba(15, 23, 42, 0.35); max-width: 420px; text-align: center; }
      h1 { font-size: 1.5rem; margin-bottom: 0.75rem; }
      p { opacity: 0.8; margin-bottom: 0; }
      .spinner { width: 48px; height: 48px; border-radius: 50%; border: 4px solid rgba(148, 163, 184, 0.35); border-top-color: #38bdf8; margin: 0 auto 1.5rem; animation: spin 1s linear infinite; }
      @keyframes spin { to { transform: rotate(360deg); } }
    </style>
  </head>
  <body>
    <div class=\"card\">
      <div class=\"spinner\"></div>
      <h1>Procesando inicio de sesión…</h1>
      <p>Estamos validando tus credenciales. Serás redirigido automáticamente.</p>
    </div>
    <script>
      (function() {
        try {
          var params = new URLSearchParams(window.location.search);
          var token = params.get('token') || TOKEN_PLACEHOLDER;
          if (token) {
            try { localStorage.setItem('auth_token', token); } catch (err) { console.error('No se pudo guardar el token:', err); }
            var evt;
            try { evt = new Event('auth-token-changed'); window.dispatchEvent(evt); } catch (_) {}
            window.location.replace('/dashboard');
            return;
          }
        } catch (error) {
          console.error('Error procesando token:', error);
        }
        window.location.replace('/login');
      })();
    </script>
  </body>
</html>"""
    token_js_literal = repr(token) if token else "null"
    return HTMLResponse(content=html.replace("TOKEN_PLACEHOLDER", token_js_literal))

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
        # Diagnóstico de drivers ODBC disponibles (útil para errores IM002)
        log_odbc_env_diagnostics()
    except Exception:
        pass
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
    uvicorn.run(app, host="0.0.0.0", port=8520)
