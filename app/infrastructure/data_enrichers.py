"""
Utilidades para enriquecer datos con información de clientes y consultores.
"""
from typing import Optional, Dict, Any
from app.infrastructure.repositorio_facturas_simple import RepositorioClientes
from app.infrastructure.repositorio_gestion import RepositorioGestion
from app.infrastructure.tercero_helpers import obtener_nombre_cliente


def enrich_with_cliente_nombre(
    repo_clientes: RepositorioClientes,
    tercero: str,
    idcliente: Optional[int] = None
) -> Optional[str]:
    """
    Obtiene el nombre del cliente a partir de tercero o idcliente.
    
    Args:
        repo_clientes: Repositorio de clientes
        tercero: Código del tercero
        idcliente: ID del cliente (opcional)
    
    Returns:
        Nombre del cliente o None si no se encuentra
    """
    try:
        tercero_to_use = str(tercero) if tercero else (str(idcliente) if idcliente else '')
        if not tercero_to_use:
            return None
        
        return obtener_nombre_cliente(repo_clientes, tercero_to_use)
    except Exception:
        return None


def enrich_with_consultor_nombre(
    repo_gestion: RepositorioGestion,
    consultor_id: Optional[int]
) -> Optional[str]:
    """
    Obtiene el nombre del consultor a partir de su ID.
    
    Args:
        repo_gestion: Repositorio de gestión
        consultor_id: ID del consultor
    
    Returns:
        Nombre del consultor o None si no se encuentra
    """
    if not consultor_id:
        return None
    
    try:
        consultor = repo_gestion.obtener_consultor(consultor_id)
        return consultor.get('nombre') if consultor else None
    except Exception:
        return None


def enrich_aviso_with_names(
    aviso: Dict[str, Any],
    repo_clientes: RepositorioClientes,
    repo_gestion: RepositorioGestion
) -> Dict[str, Any]:
    """
    Enriquece un aviso con nombres de cliente y consultor.
    
    Args:
        aviso: Diccionario con datos del aviso
        repo_clientes: Repositorio de clientes
        repo_gestion: Repositorio de gestión
    
    Returns:
        Diccionario enriquecido con cliente_nombre y consultor_nombre
    """
    tercero = str(aviso.get('tercero') or aviso.get('idcliente') or '')
    cliente_nombre = enrich_with_cliente_nombre(
        repo_clientes,
        tercero,
        aviso.get('idcliente')
    )
    consultor_nombre = enrich_with_consultor_nombre(
        repo_gestion,
        aviso.get('consultor_id')
    )
    
    return {
        **aviso,
        'cliente_nombre': cliente_nombre,
        'consultor_nombre': consultor_nombre,
    }


def enrich_factura_with_cliente(
    factura: Dict[str, Any],
    repo_clientes: RepositorioClientes,
    tercero: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enriquece una factura con datos del cliente.
    
    Args:
        factura: Diccionario con datos de la factura
        repo_clientes: Repositorio de clientes
        tercero: Código del tercero (opcional, se usa el de la factura si no se proporciona)
    
    Returns:
        Diccionario de factura con datos_cliente añadido
    """
    tercero_to_use = tercero or factura.get('tercero')
    if not tercero_to_use:
        factura['datos_cliente'] = None
        return factura
    
    try:
        datos_cliente = repo_clientes.obtener_cliente(str(tercero_to_use))
        if datos_cliente:
            factura['datos_cliente'] = {
                "id": datos_cliente.get("idcliente"),
                "nombre": (datos_cliente.get("razsoc") or "").strip(),
                "cif": (datos_cliente.get("cif") or "").strip(),
                "cif_empresa": (datos_cliente.get("cif_empresa") or "").strip(),
                "cif_factura": (datos_cliente.get("cif_factura") or "").strip(),
            }
        else:
            factura['datos_cliente'] = None
    except Exception:
        factura['datos_cliente'] = None
    
    return factura

