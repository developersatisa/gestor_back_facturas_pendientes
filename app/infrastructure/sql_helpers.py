"""
Utilidades para construcción de queries SQL.

Este módulo proporciona funciones helper para construir queries SQL
de manera consistente y reutilizable.
"""
from app.domain.constants import (
    SQL_FILTROS_BASE,
    SQL_FILTRO_SOCIEDADES,
    SQL_CALCULO_MONTO_NETO,
    SQL_CALCULO_FACTURAS,
)


def build_base_filters(include_sociedades: bool = True) -> str:
    """
    Construye los filtros base para queries de facturas.
    
    Args:
        include_sociedades: Si True, incluye el filtro de sociedades
        
    Returns:
        String con los filtros SQL base
    """
    filters = SQL_FILTROS_BASE
    if include_sociedades:
        filters += "\n    " + SQL_FILTRO_SOCIEDADES
    return filters


def get_monto_neto_calculation() -> str:
    """
    Retorna el cálculo SQL para monto neto (pendiente - abonos).
    
    Returns:
        String con el CASE statement para cálculo de monto neto
    """
    return SQL_CALCULO_MONTO_NETO


def get_facturas_calculation() -> str:
    """
    Retorna el cálculo SQL para conteo de facturas.
    
    Returns:
        String con el CASE statement para conteo de facturas
    """
    return SQL_CALCULO_FACTURAS


def build_monto_neto_sum(alias: str = "monto_total") -> str:
    """
    Construye un SUM con el cálculo de monto neto.
    
    Args:
        alias: Nombre del alias para el resultado
        
    Returns:
        String con SUM(CASE...) as alias
    """
    return f"SUM({SQL_CALCULO_MONTO_NETO}) as {alias}"


def build_facturas_sum(alias: str = "total_facturas") -> str:
    """
    Construye un SUM con el cálculo de conteo de facturas.
    
    Args:
        alias: Nombre del alias para el resultado
        
    Returns:
        String con SUM(CASE...) as alias
    """
    return f"SUM({SQL_CALCULO_FACTURAS}) as {alias}"


def build_having_monto_neto() -> str:
    """
    Construye la cláusula HAVING para filtrar por monto neto > 0.
    
    Returns:
        String con HAVING SUM(...) > 0
    """
    return f"HAVING SUM({SQL_CALCULO_MONTO_NETO}) > 0"

