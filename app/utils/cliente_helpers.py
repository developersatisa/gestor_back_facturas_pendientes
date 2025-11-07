"""
Utilidades para formatear y procesar datos de clientes.
"""
from typing import Dict, Any, Optional


def format_cliente_data(cliente: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formatea los datos de un cliente para la respuesta API.
    
    Args:
        cliente: Diccionario con datos del cliente desde el repositorio
    
    Returns:
        Diccionario formateado con campos estándar
    """
    if not cliente:
        return None
    
    return {
        "id": cliente.get("idcliente"),
        "nombre": (cliente.get("razsoc") or "").strip(),
        "cif": (cliente.get("cif") or "").strip(),
        "cif_empresa": (cliente.get("cif_empresa") or "").strip(),
        "cif_factura": (cliente.get("cif_factura") or "").strip(),
    }


def build_cliente_cache_key(tercero: str) -> str:
    """
    Construye una clave de cache normalizada para un tercero.
    
    Args:
        tercero: Código del tercero
    
    Returns:
        Clave normalizada para cache
    """
    return str(tercero).strip()

