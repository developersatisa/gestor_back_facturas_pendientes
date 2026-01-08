"""
Utilidades para formatear y procesar datos de facturas.
"""
from typing import Dict, Any, Optional


def format_factura_search_result(item: Dict[str, Any], datos_cliente: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Formatea un resultado de búsqueda de factura para la respuesta API.
    
    Args:
        item: Diccionario con datos de la factura
        datos_cliente: Datos del cliente formateados (opcional)
    
    Returns:
        Diccionario formateado para la respuesta
    """
    return {
        "numero": item.get("nombre_factura") or item.get("asiento"),
        "tipo": item.get("tipo"),
        "asiento": item.get("asiento"),
        "tercero": str(item.get("tercero") or "").strip() or None,
        "sociedad": item.get("sociedad"),
        "sociedad_nombre": item.get("sociedad_nombre"),
        "vencimiento": item.get("vencimiento"),
        "pendiente": item.get("pendiente"),
        "importe": item.get("importe"),
        "pago": item.get("pago"),
        "empresa": datos_cliente,
    }


def normalize_factura_key(factura: Dict[str, Any]) -> tuple:
    """
    Normaliza una factura a una tupla (tipo, asiento) para comparaciones.
    
    Args:
        factura: Diccionario con datos de factura
    
    Returns:
        Tupla (tipo, asiento) normalizada
    """
    tipo = (factura.get("tipo") or "").strip()
    asiento = str(factura.get("asiento") or "").strip()
    return (tipo, asiento)

