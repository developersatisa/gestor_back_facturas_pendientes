"""
Utilidades para normalización y manejo de terceros
"""
from typing import Optional


def normalizar_tercero(tercero: str) -> str:
    """
    Normaliza un tercero eliminando ceros a la izquierda.
    
    Args:
        tercero: Código del tercero (puede tener ceros a la izquierda)
    
    Returns:
        Tercero normalizado sin ceros a la izquierda
    """
    if not tercero:
        return ''
    
    try:
        return str(int(str(tercero).strip()))
    except (ValueError, TypeError):
        return str(tercero).strip()


def intentar_obtener_cliente(repo_clientes, tercero: str) -> dict:
    """
    Intenta obtener los datos de un cliente usando el tercero original y normalizado.
    
    Args:
        repo_clientes: Repositorio de clientes
        tercero: Código del tercero
    
    Returns:
        Diccionario con los datos del cliente o None si no se encuentra
    """
    if not tercero:
        return None
    
    # Intentar con el tercero tal cual
    try:
        cliente = repo_clientes.obtener_cliente(tercero)
        if cliente:
            return cliente
    except Exception:
        pass
    
    # Intentar con el tercero normalizado
    try:
        tercero_normalizado = normalizar_tercero(tercero)
        if tercero_normalizado != tercero:
            cliente = repo_clientes.obtener_cliente(tercero_normalizado)
            if cliente:
                return cliente
    except Exception:
        pass
    
    return None


def obtener_nombre_cliente(repo_clientes, tercero: str) -> Optional[str]:
    """
    Obtiene el nombre de un cliente a partir de su tercero.
    
    Args:
        repo_clientes: Repositorio de clientes
        tercero: Código del tercero
    
    Returns:
        Nombre del cliente o None si no se encuentra
    """
    cliente = intentar_obtener_cliente(repo_clientes, tercero)
    if not cliente:
        return None
    
    return cliente.get('razsoc') or cliente.get('nombre') or None

