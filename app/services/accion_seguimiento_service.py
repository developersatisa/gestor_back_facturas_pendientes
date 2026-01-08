"""
Servicio para gestión de acciones de seguimiento.
"""
from typing import List, Optional, Tuple, Set
from datetime import datetime
from sqlalchemy.orm import Session
from app.domain.models.gestion import AccionFactura
from app.utils.error_handlers import handle_validation_error
from app.utils.factura_helpers import normalize_factura_key


def parse_aviso_date(aviso: Optional[str]) -> Optional[datetime]:
    """
    Parsea una fecha de aviso desde string ISO a datetime.
    
    Args:
        aviso: String de fecha en formato ISO (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)
    
    Returns:
        datetime o None si no se puede parsear
    """
    if not aviso or not aviso.strip():
        return None
    
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(aviso.strip(), fmt)
        except Exception:
            continue
    return None


def validate_aviso_date(aviso: Optional[str]) -> None:
    """
    Valida que la fecha de aviso sea parseable.
    
    Raises:
        HTTPException si la fecha no es válida
    """
    if aviso and aviso.strip() and parse_aviso_date(aviso) is None:
        raise handle_validation_error("Formato de fecha inválido", "aviso")


def group_acciones_by_placeholder(acciones: List[AccionFactura]) -> Tuple[List[AccionFactura], List[AccionFactura]]:
    """
    Separa acciones en placeholder y con datos comunes.
    
    Args:
        acciones: Lista de acciones a clasificar
    
    Returns:
        Tupla (acciones_placeholder, acciones_con_comun)
    """
    acciones_placeholder = [
        a for a in acciones 
        if not a.accion_tipo and not a.descripcion and not a.aviso
    ]
    acciones_con_comun = [
        a for a in acciones 
        if a.accion_tipo or a.descripcion or a.aviso
    ]
    return acciones_placeholder, acciones_con_comun


def find_acciones_group(
    acciones: List[AccionFactura],
    accion_referencia: AccionFactura
) -> List[AccionFactura]:
    """
    Encuentra todas las acciones que pertenecen al mismo grupo que la acción de referencia.
    
    Un grupo se define por (accion_tipo, descripcion, aviso).
    
    Args:
        acciones: Lista de acciones a buscar
        accion_referencia: Acción de referencia para encontrar el grupo
    
    Returns:
        Lista de acciones del mismo grupo
    """
    return [
        a for a in acciones 
        if (a.accion_tipo or '') == (accion_referencia.accion_tipo or '') and
           (a.descripcion or '') == (accion_referencia.descripcion or '') and
           (a.aviso or None) == (accion_referencia.aviso or None)
    ]


def build_factura_set_from_payload(facturas: List[dict]) -> Set[Tuple[str, str]]:
    """
    Construye un set de tuplas (tipo, asiento) desde el payload de facturas.
    
    Args:
        facturas: Lista de diccionarios con facturas
    
    Returns:
        Set de tuplas (tipo, asiento) normalizadas
    """
    return {
        normalize_factura_key(f)
        for f in facturas
        if f.get("tipo") and f.get("asiento")
    }


def build_factura_set_from_acciones(acciones: List[AccionFactura]) -> Set[Tuple[str, str]]:
    """
    Construye un set de tuplas (tipo, asiento) desde una lista de acciones.
    
    Args:
        acciones: Lista de acciones
    
    Returns:
        Set de tuplas (tipo, asiento) normalizadas
    """
    return {
        (acc.tipo or "", str(acc.asiento or ""))
        for acc in acciones
    }

