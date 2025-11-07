"""
Utilidades para verificar estado de facturas de clientes.
"""
from typing import List, Dict, Any
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas
from app.infrastructure.tercero_helpers import normalizar_tercero


def cliente_tiene_facturas_pendientes(
    repo_facturas: RepositorioFacturas,
    tercero: str
) -> bool:
    """
    Verifica si un cliente tiene facturas pendientes.
    
    Intenta con el tercero original y si no encuentra, intenta con el normalizado.
    
    Args:
        repo_facturas: Repositorio de facturas
        tercero: Código del tercero
    
    Returns:
        True si el cliente tiene facturas con saldo pendiente > 0, False en caso contrario
    """
    if not tercero:
        return False
    
    tercero_str = str(tercero).strip()
    if not tercero_str:
        return False
    
    # Intentar con el tercero tal cual
    try:
        facturas = repo_facturas.obtener_facturas(tercero=tercero_str)
        if facturas and len(facturas) > 0:
            if any(f.get('pendiente', 0) > 0 for f in facturas):
                return True
    except Exception:
        pass
    
    # Si no se encontraron, intentar con el tercero normalizado
    try:
        tercero_normalizado = normalizar_tercero(tercero_str)
        if tercero_normalizado != tercero_str:
            facturas = repo_facturas.obtener_facturas(tercero=tercero_normalizado)
            if facturas and len(facturas) > 0:
                return any(f.get('pendiente', 0) > 0 for f in facturas)
    except Exception:
        pass
    
    return False

