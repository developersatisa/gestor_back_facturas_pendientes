from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.application.obtener_facturas_filtradas import ObtenerFacturasFiltradas
from app.application.obtener_estadisticas_facturas import ObtenerEstadisticasFacturas
from app.application.obtener_facturas_agrupadas_por_cliente import ObtenerFacturasAgrupadasPorCliente
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
from app.domain.models.Factura import Factura
from app.config.database import get_facturas_db, get_clientes_db
import logging

router = APIRouter()

# Configuración de logging
logger = logging.getLogger("facturas")

# Dependency para el repositorio
def get_repo_facturas(db: Session = Depends(get_facturas_db)):
    return RepositorioFacturas(db)

def get_repo_clientes(db: Session = Depends(get_clientes_db)):
    return RepositorioClientes(db)

@router.get("/api/facturas-cliente/{idcliente}", response_model=List[dict], tags=["Facturas"])
def obtener_facturas_cliente(
    idcliente: str,
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
    repo_clientes: RepositorioClientes = Depends(get_repo_clientes),
):
    try:
        # Obtener facturas del cliente específico
        use_case = ObtenerFacturasFiltradas(repo_facturas)
        facturas = use_case.execute(
            tercero=idcliente,  # Usar el idcliente como tercero
        )
        
        # Obtener datos del cliente
        datos_cliente = repo_clientes.obtener_cliente(idcliente)
        
        # Agregar datos del cliente a cada factura
        facturas_con_cliente = []
        for factura in facturas:
            factura_dict = factura.copy()
            factura_dict['datos_cliente'] = datos_cliente if datos_cliente else None
            facturas_con_cliente.append(factura_dict)
        
        logger.info(f"Facturas encontradas para cliente {idcliente}: {len(facturas_con_cliente)}")
        return facturas_con_cliente
    except Exception as e:
        logger.error(f"Error al obtener facturas del cliente {idcliente}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor")

@router.get("/api/clientes-con-resumen", response_model=List[dict], tags=["Clientes"])
def obtener_clientes_con_resumen(
    tercero: Optional[str] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    nivel_reclamacion: Optional[int] = Query(None),
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
    repo_clientes: RepositorioClientes = Depends(get_repo_clientes),
):
    try:
        # Obtener facturas agrupadas por cliente
        use_case = ObtenerFacturasAgrupadasPorCliente(repo_facturas, repo_clientes)
        clientes_con_facturas = use_case.execute(
            tercero=tercero,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            nivel_reclamacion=nivel_reclamacion,
        )
        
        logger.info(f"Clientes con resumen encontrados: {len(clientes_con_facturas)}")
        return clientes_con_facturas
    except Exception as e:
        logger.error(f"Error al obtener clientes con resumen: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor")

@router.get("/api/estadisticas", response_model=dict, tags=["Estadísticas"])
def obtener_estadisticas(
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
    repo_clientes: RepositorioClientes = Depends(get_repo_clientes),
):
    try:
        use_case = ObtenerEstadisticasFacturas(repo_facturas, repo_clientes)
        estadisticas = use_case.execute()
        logger.info(f"Estadísticas calculadas: {estadisticas}")
        return estadisticas
    except Exception as e:
        logger.error(f"Error al obtener estadísticas: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor")


