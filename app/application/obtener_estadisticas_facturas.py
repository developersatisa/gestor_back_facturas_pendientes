from typing import Dict, Any, List
from datetime import date
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
import logging

logger = logging.getLogger(__name__)

class ObtenerEstadisticasFacturas:
    def __init__(self, repo_facturas: RepositorioFacturas, repo_clientes: RepositorioClientes):
        self.repo_facturas = repo_facturas
        self.repo_clientes = repo_clientes

    def execute(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas resumidas de facturas usando consultas SQL directas:
        - Total de empresas con facturas pendientes (sin repetir empresas)
        - Total de facturas pendientes
        - Monto total adeudado (en moneda original)
        - Lista de empresas con sus montos y datos de cliente (limitado a 50)
        """
        logger.info("Iniciando cálculo de estadísticas...")
        
        # 1. Total de empresas con facturas pendientes (sin repetir empresas)
        query_empresas = """
        SELECT 
          COUNT(DISTINCT BPR_0) AS total_empresas_pendientes
        FROM 
          x3v12.ATISAINT.GACCDUDATE
        WHERE 
          TYP_0 NOT IN ('AA', 'ZZ')
          AND SAC_0 = '4300'
          AND FLGCLE_0 = 1
        """
        
        # 2. Total de facturas pendientes
        query_facturas = """
        SELECT 
          COUNT(*) AS total_facturas_pendientes
        FROM 
          x3v12.ATISAINT.GACCDUDATE
        WHERE 
          TYP_0 NOT IN ('AA', 'ZZ')
          AND SAC_0 = '4300'
          AND FLGCLE_0 = 1
        """
        
        # 3. Monto total adeudado (en moneda original)
        query_monto = """
        SELECT 
          SUM(AMTCUR_0) AS monto_total_adeudado
        FROM 
          x3v12.ATISAINT.GACCDUDATE
        WHERE 
          TYP_0 NOT IN ('AA', 'ZZ')
          AND SAC_0 = '4300'
          AND FLGCLE_0 = 1
        """
        
        # 4. Lista de empresas con sus montos totales (LIMITADO A 50 para evitar timeout)
        query_empresas_montos = """
        SELECT TOP 50
          CAST(BPR_0 AS INT) as tercero_sin_ceros,
          BPR_0 as tercero_original,
          SUM(AMTCUR_0) as monto_total
        FROM 
          x3v12.ATISAINT.GACCDUDATE
        WHERE 
          TYP_0 NOT IN ('AA', 'ZZ')
          AND SAC_0 = '4300'
          AND FLGCLE_0 = 1
        GROUP BY 
          BPR_0
        ORDER BY 
          monto_total DESC
        """
        
        # Ejecutar las consultas
        from sqlalchemy import text
        
        try:
            logger.info("Ejecutando consulta 1: Total de empresas...")
            # Consulta 1: Total de empresas
            result_empresas = self.repo_facturas.db.execute(text(query_empresas))
            total_empresas = result_empresas.fetchone()[0] or 0
            logger.info(f"Total empresas: {total_empresas}")
            
            logger.info("Ejecutando consulta 2: Total de facturas...")
            # Consulta 2: Total de facturas
            result_facturas = self.repo_facturas.db.execute(text(query_facturas))
            total_facturas = result_facturas.fetchone()[0] or 0
            logger.info(f"Total facturas: {total_facturas}")
            
            logger.info("Ejecutando consulta 3: Monto total...")
            # Consulta 3: Monto total
            result_monto = self.repo_facturas.db.execute(text(query_monto))
            monto_total = result_monto.fetchone()[0] or 0.0
            logger.info(f"Monto total: {monto_total}")
            
            logger.info("Ejecutando consulta 4: Empresas con montos...")
            # Consulta 4: Empresas con montos (LIMITADO A 50)
            result_empresas_montos = self.repo_facturas.db.execute(text(query_empresas_montos))
            empresas_montos = []
            
            logger.info("Procesando empresas y buscando clientes...")
            for i, row in enumerate(result_empresas_montos):
                tercero_original = row.tercero_original
                tercero_sin_ceros = str(row.tercero_sin_ceros)  # Convertir a string sin ceros
                monto = float(row.monto_total) if row.monto_total else 0.0
                
                logger.info(f"Procesando empresa {i+1}: {tercero_original} -> {tercero_sin_ceros}")
                
                # Buscar datos del cliente en la base de datos de clientes usando el tercero sin ceros
                datos_cliente = self.repo_clientes.obtener_cliente(tercero_sin_ceros)
                
                # Crear objeto con idcliente, nombre y monto
                empresa_info = {
                    "idcliente": tercero_original,  # Mantener el original para referencia
                    "nombre": datos_cliente.get('razsoc', 'Sin nombre') if datos_cliente else 'Sin nombre',
                    "monto": monto
                }
                empresas_montos.append(empresa_info)
            
            logger.info(f"Procesamiento completado. {len(empresas_montos)} empresas procesadas.")
            
            return {
                "total_empresas_pendientes": total_empresas,
                "total_facturas_pendientes": total_facturas,
                "monto_total_adeudado": float(monto_total) if monto_total else 0.0,
                "empresas_con_montos": empresas_montos,
                "filtros_aplicados": {
                    "tipo_excluido": ["AA", "ZZ"],
                    "colectivo": "4300",
                    "check_pago": 1
                },
                "nota": "Mostrando solo las 50 empresas con mayor monto pendiente"
            }
            
        except Exception as e:
            logger.error(f"Error en el cálculo de estadísticas: {e}")
            raise e 