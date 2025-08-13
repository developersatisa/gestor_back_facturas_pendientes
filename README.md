# Facturas Backend (FastAPI + Hexagonal)

## Estructura del Proyecto

```
app/
  domain/models/Factura.py         # Entidad de dominio
  application/obtener_facturas_filtradas.py  # Caso de uso
  infrastructure/repositorio_facturas.py     # Acceso a datos
  interfaces/facturas_controller.py          # API FastAPI
  config/settings.py                # Configuración
main.py                             # Entrypoint FastAPI
```

## Variables de Entorno

Ver `.env.example`:
- `DB_URL`: Cadena de conexión a SQL Server

## Comandos

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar en desarrollo
uvicorn main:app --reload

# Ejecutar en producción (Docker)
docker build -t facturas-backend .
docker run -p 8000:8000 --env-file .env facturas-backend
```

## Pruebas

```bash
pytest
```

- Pruebas unitarias de casos de uso con mocks
- Pruebas de integración del endpoint `/api/facturas`

## Notas
- Arquitectura hexagonal (Clean Architecture)
- Seguridad básica, validaciones, logging, CORS
- Documentación automática OpenAPI en `/docs` 