from typing import Dict, Any, List
from datetime import date
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
import logging

logger = logging.getLogger(__name__)

class ObtenerFacturasAgrupadasPorCliente:
    def __init__(self, repo_facturas: RepositorioFacturas, repo_clientes: RepositorioClientes):
        self.repo_facturas = repo_facturas
        self.repo_clientes = repo_clientes

    def execute(
        self,
        tercero: str = None,
        fecha_desde: date = None,
        fecha_hasta: date = None,
        nivel_reclamacion: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene facturas agrupadas por cliente con resumen de montos
        """
        logger.info("Iniciando obtención de facturas agrupadas por cliente...")
        
        # Consulta para obtener facturas agrupadas por cliente
        query = """
        SELECT 
          BPR_0 as tercero,
          COUNT(*) as total_facturas,
          SUM(AMTCUR_0) as monto_total,
          SUM(PAYCUR_0) as pago_total,
          MAX(LEVFUP_0) as nivel_reclamacion_max
        FROM 
          x3v12.ATISAINT.GACCDUDATE
        WHERE 
          TYP_0 NOT IN ('AA', 'ZZ')
          AND SAC_0 = '4300'
          AND FLGCLE_0 = 1
        """
        
        params = {}
        
        # Filtros opcionales
        if tercero:
            query += " AND BPR_0 = :tercero"
            params["tercero"] = tercero
        if fecha_desde:
            query += " AND DUDDAT_0 >= :fecha_desde"
            params["fecha_desde"] = fecha_desde
        if fecha_hasta:
            query += " AND DUDDAT_0 <= :fecha_hasta"
            params["fecha_hasta"] = fecha_hasta
        if nivel_reclamacion is not None:
            query += " AND LEVFUP_0 = :nivel_reclamacion"
            params["nivel_reclamacion"] = nivel_reclamacion
        
        query += """
        GROUP BY 
          BPR_0
        ORDER BY 
          monto_total DESC
        """
        
        from sqlalchemy import text
        
        try:
            logger.info("Ejecutando consulta de facturas agrupadas por cliente...")
            result = self.repo_facturas.db.execute(text(query), params)
            
            clientes_con_facturas = []
            
            for row in result:
                tercero_original = row.tercero
                tercero_sin_ceros = str(int(row.tercero))  # Eliminar ceros a la izquierda
                
                # Buscar datos del cliente
                datos_cliente = self.repo_clientes.obtener_cliente(tercero_sin_ceros)
                
                # Calcular monto pendiente
                monto_total = float(row.monto_total) if row.monto_total else 0.0
                pago_total = float(row.pago_total) if row.pago_total else 0.0
                monto_pendiente = monto_total - pago_total
                
                # Determinar estado basado en nivel de reclamación
                nivel_max = row.nivel_reclamacion_max or 0
                if nivel_max >= 3:
                    estado = "rojo"
                elif nivel_max == 2:
                    estado = "amarillo"
                else:
                    estado = "verde"
                
                cliente_info = {
                    "idcliente": tercero_original,
                    "nombre_cliente": datos_cliente.get('razsoc', 'Sin nombre') if datos_cliente else 'Sin nombre',
                    "cif_cliente": datos_cliente.get('cif', 'Sin CIF') if datos_cliente else 'Sin CIF',
                    "numero_facturas": row.total_facturas,
                    "monto_debe": monto_pendiente,
                    "estado": estado
                }
                
                clientes_con_facturas.append(cliente_info)
            
            logger.info(f"Procesamiento completado. {len(clientes_con_facturas)} clientes encontrados.")
            
            return clientes_con_facturas
            
        except Exception as e:
            logger.error(f"Error en el procesamiento: {e}")
            raise e 