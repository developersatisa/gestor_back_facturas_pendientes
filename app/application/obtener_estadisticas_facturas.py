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
        
        # Totales unificados (empresas, facturas, monto neto)
        query_totales = """
        WITH base AS (
          SELECT BPR_0, AMTCUR_0, PAYCUR_0, SNS_0, FLGCLE_0, DUDDAT_0, TYP_0
          FROM x3v12.ATISAINT.GACCDUDATE
          WHERE SAC_0='4300' AND TYP_0 NOT IN ('AA','ZZ')
            AND DUDDAT_0 < GETDATE() AND FLGCLE_0 <> 2
        ),
        agg AS (
          SELECT
            BPR_0,
            SUM(CASE WHEN (FLGCLE_0=1) AND (SNS_0<>-1) AND (AMTCUR_0-ISNULL(PAYCUR_0,0))>0 THEN 1 ELSE 0 END) AS total_facturas,
            SUM(CASE
                  WHEN (SNS_0=-1 OR FLGCLE_0=-1 OR AMTCUR_0<0) THEN -ABS(AMTCUR_0)
                  WHEN (FLGCLE_0=1) AND (SNS_0<>-1) AND (AMTCUR_0-ISNULL(PAYCUR_0,0))>0 THEN (AMTCUR_0-ISNULL(PAYCUR_0,0))
                  ELSE 0
                END) AS monto_neto
          FROM base
          GROUP BY BPR_0
        )
        SELECT
          (SELECT COUNT(1) FROM agg WHERE monto_neto > 0) AS total_empresas_pendientes,
          (SELECT COALESCE(SUM(total_facturas),0) FROM agg) AS total_facturas_pendientes,
          (SELECT COALESCE(SUM(monto_neto),0) FROM agg) AS monto_total_adeudado;
        """

        # Empresas TOP 50 por monto neto
        query_empresas_montos = """
        WITH base AS (
          SELECT BPR_0, AMTCUR_0, PAYCUR_0, SNS_0, FLGCLE_0, DUDDAT_0, TYP_0
          FROM x3v12.ATISAINT.GACCDUDATE
          WHERE SAC_0='4300' AND TYP_0 NOT IN ('AA','ZZ')
            AND DUDDAT_0 < GETDATE() AND FLGCLE_0 <> 2
        )
        SELECT TOP 50
          BPR_0 as tercero_original,
          SUM(CASE
                WHEN (SNS_0=-1 OR FLGCLE_0=-1 OR AMTCUR_0<0) THEN -ABS(AMTCUR_0)
                WHEN (FLGCLE_0=1) AND (SNS_0<>-1) AND (AMTCUR_0-ISNULL(PAYCUR_0,0))>0 THEN (AMTCUR_0-ISNULL(PAYCUR_0,0))
                ELSE 0
              END) as monto_total
        FROM base
        GROUP BY BPR_0
        HAVING SUM(CASE
                      WHEN (SNS_0=-1 OR FLGCLE_0=-1 OR AMTCUR_0<0) THEN -ABS(AMTCUR_0)
                      WHEN (FLGCLE_0=1) AND (SNS_0<>-1) AND (AMTCUR_0-ISNULL(PAYCUR_0,0))>0 THEN (AMTCUR_0-ISNULL(PAYCUR_0,0))
                      ELSE 0
                    END) > 0
        ORDER BY monto_total DESC;
        """
        
        # Ejecutar las consultas
        from sqlalchemy import text
        
        try:
            logger.info("Calculando totales unificados para dashboard...")
            res_tot = self.repo_facturas.db.execute(text(query_totales)).fetchone()
            total_empresas = int(res_tot.total_empresas_pendientes or 0)
            total_facturas = int(res_tot.total_facturas_pendientes or 0)
            monto_total = float(res_tot.monto_total_adeudado or 0.0)
            
            logger.info("Ejecutando consulta 4: Empresas con montos...")
            # Consulta 4: Empresas con montos (LIMITADO A 50)
            result_empresas_montos = self.repo_facturas.db.execute(text(query_empresas_montos))
            empresas_montos = []
            
            logger.info("Procesando empresas y buscando clientes...")
            for i, row in enumerate(result_empresas_montos):
                tercero_original = row.tercero_original
                try:
                    tercero_sin_ceros = str(int(tercero_original))
                except Exception:
                    tercero_sin_ceros = str(tercero_original)
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
                    "vencidas": True,
                    "flgcle_excluir": 2
                },
                "nota": "Mostrando solo las 50 empresas con mayor monto pendiente"
            }
            
        except Exception as e:
            logger.error(f"Error en el cálculo de estadísticas: {e}")
            raise e 
