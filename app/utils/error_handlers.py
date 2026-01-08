"""
Utilidades para manejo consistente de errores en controladores.
"""
from fastapi import HTTPException, status
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def handle_error(
    error: Exception,
    operation: str,
    default_message: str = "Error interno del servidor",
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    log_error: bool = True
) -> HTTPException:
    """
    Maneja errores de forma consistente y lanza HTTPException.
    
    Args:
        error: Excepción capturada
        operation: Descripción de la operación que falló
        default_message: Mensaje por defecto si no se puede extraer del error
        status_code: Código HTTP de error
        log_error: Si se debe registrar el error en logs
    
    Returns:
        HTTPException para lanzar
    """
    if log_error:
        logger.error(f"Error en {operation}: {str(error)}", exc_info=True)
    
    detail = str(error) if str(error) else default_message
    return HTTPException(status_code=status_code, detail=detail)


def handle_db_error(
    error: Exception,
    operation: str,
    entity: str = "entidad"
) -> HTTPException:
    """
    Maneja errores específicos de base de datos.
    
    Args:
        error: Excepción de base de datos
        operation: Operación que falló (crear, actualizar, eliminar, obtener)
        entity: Nombre de la entidad afectada
    
    Returns:
        HTTPException para lanzar
    """
    messages = {
        "crear": f"No se pudo crear {entity}",
        "actualizar": f"No se pudo actualizar {entity}",
        "eliminar": f"No se pudo eliminar {entity}",
        "obtener": f"No se pudo obtener {entity}",
    }
    default_message = messages.get(operation, f"Error en operación {operation} de {entity}")
    return handle_error(error, f"{operation} {entity}", default_message)


def handle_validation_error(
    message: str,
    field: Optional[str] = None
) -> HTTPException:
    """
    Maneja errores de validación.
    
    Args:
        message: Mensaje de error
        field: Campo que falló la validación (opcional)
    
    Returns:
        HTTPException con código 400
    """
    detail = f"Error de validación en {field}: {message}" if field else message
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail
    )

