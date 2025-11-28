from typing import Dict, Any, List
from datetime import date
import logging
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
from app.infrastructure.tercero_helpers import formatear_tercero_para_facturas

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
        # Si el motor no es MSSQL (p.ej. SQLite en desarrollo), devolver valores seguros
        try:
            bind = self.repo_facturas.db.get_bind()  # type: ignore[attr-defined]
            if not bind or bind.dialect.name != 'mssql':
                return {
                    "total_empresas_pendientes": 0,
                    "total_facturas_pendientes": 0,
                    "monto_total_adeudado": 0.0,
                    "empresas_con_montos": [],
                    "sociedades_con_montos": [],
                    "facturas_mas_vencidas": [],
                    "saldo_resumen": {
                        "all": {"total_empresas": 0, "total_facturas": 0, "total_monto": 0.0},
                        "cliente_debe_empresa": {"total_empresas": 0, "total_facturas": 0, "total_monto": 0.0},
                        "empresa_debe_cliente": {"total_empresas": 0, "total_facturas": 0, "total_monto": 0.0},
                    },
                    "filtros_aplicados": {
                        "tipo_excluido": ["AA", "ZZ"],
                        "colectivo": ["4300", "4302"],
                        "vencidas": True,
                        "flgcle_excluir": 2,
                    },
                    "nota": "Sin conexión MSSQL configurada; devolviendo valores vacíos (desarrollo)",
                }
        except Exception:
            return {
                "total_empresas_pendientes": 0,
                "total_facturas_pendientes": 0,
                "monto_total_adeudado": 0.0,
                "empresas_con_montos": [],
                "sociedades_con_montos": [],
                "facturas_mas_vencidas": [],
                "saldo_resumen": {
                    "all": {"total_empresas": 0, "total_facturas": 0, "total_monto": 0.0},
                    "cliente_debe_empresa": {"total_empresas": 0, "total_facturas": 0, "total_monto": 0.0},
                    "empresa_debe_cliente": {"total_empresas": 0, "total_facturas": 0, "total_monto": 0.0},
                },
                "filtros_aplicados": {
                    "tipo_excluido": ["AA", "ZZ"],
                    "colectivo": ["4300", "4302"],
                    "vencidas": True,
                    "flgcle_excluir": 2,
                },
                "nota": "Error detectando motor de BD; devolviendo valores vacíos",
            }

        # Totales unificados (empresas, facturas, monto neto)
        # IMPORTANTE: Incluye filtro de sociedades para que coincida con el Excel
        query_totales = """
        WITH base AS (
          SELECT BPR_0, AMTCUR_0, PAYCUR_0, SNS_0, FLGCLE_0, DUDDAT_0, TYP_0
          FROM x3v12.ATISAINT.GACCDUDATE
          WHERE SAC_0 IN ('4300','4302') AND TYP_0 NOT IN ('AA','ZZ')
            AND DUDDAT_0 < GETDATE() AND FLGCLE_0 <> 2
            AND CPY_0 IN ('S005','S001','S010')
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
          (SELECT COUNT(1) FROM agg WHERE monto_neto <> 0) AS total_empresas_total,
          (SELECT COUNT(1) FROM agg WHERE monto_neto > 0) AS total_empresas_cliente_debe,
          (SELECT COUNT(1) FROM agg WHERE monto_neto < 0) AS total_empresas_empresa_debe,
          (SELECT COALESCE(SUM(total_facturas),0) FROM agg) AS total_facturas_total,
          (SELECT COALESCE(SUM(total_facturas),0) FROM agg WHERE monto_neto > 0) AS total_facturas_cliente_debe,
          (SELECT COALESCE(SUM(total_facturas),0) FROM agg WHERE monto_neto < 0) AS total_facturas_empresa_debe,
          (SELECT COALESCE(SUM(monto_neto),0) FROM agg WHERE monto_neto > 0) AS monto_total_cliente_debe,
          (SELECT COALESCE(SUM(ABS(monto_neto)),0) FROM agg WHERE monto_neto < 0) AS monto_total_empresa_debe;
        """

        # Empresas TOP 50 por monto neto
        query_empresas_montos = """
        WITH base AS (
          SELECT BPR_0, AMTCUR_0, PAYCUR_0, SNS_0, FLGCLE_0, DUDDAT_0, TYP_0
          FROM x3v12.ATISAINT.GACCDUDATE
          WHERE SAC_0 IN ('4300','4302') AND TYP_0 NOT IN ('AA','ZZ')
            AND DUDDAT_0 < GETDATE() AND FLGCLE_0 <> 2
        ),
        empresas_agg AS (
          SELECT
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
                      END) <> 0
        )
        SELECT TOP 50
          tercero_original,
          monto_total
        FROM empresas_agg
        ORDER BY ABS(monto_total) DESC;
        """

        # Sociedades TOP por monto neto (CPY_0)
        query_sociedades_montos = """
        WITH base AS (
          SELECT CPY_0, AMTCUR_0, PAYCUR_0, SNS_0, FLGCLE_0, DUDDAT_0, TYP_0
          FROM x3v12.ATISAINT.GACCDUDATE
          WHERE SAC_0 IN ('4300','4302') AND TYP_0 NOT IN ('AA','ZZ')
            AND DUDDAT_0 < GETDATE() AND FLGCLE_0 <> 2
        )
        SELECT
          CPY_0 as sociedad,
          SUM(CASE
                WHEN (SNS_0=-1 OR FLGCLE_0=-1 OR AMTCUR_0<0) THEN -ABS(AMTCUR_0)
                WHEN (FLGCLE_0=1) AND (SNS_0<>-1) AND (AMTCUR_0-ISNULL(PAYCUR_0,0))>0 THEN (AMTCUR_0-ISNULL(PAYCUR_0,0))
                ELSE 0
              END) as monto_total
        FROM base
        GROUP BY CPY_0
        HAVING SUM(CASE
                      WHEN (SNS_0=-1 OR FLGCLE_0=-1 OR AMTCUR_0<0) THEN -ABS(AMTCUR_0)
                      WHEN (FLGCLE_0=1) AND (SNS_0<>-1) AND (AMTCUR_0-ISNULL(PAYCUR_0,0))>0 THEN (AMTCUR_0-ISNULL(PAYCUR_0,0))
                      ELSE 0
                    END) > 0
        ORDER BY monto_total DESC;
        """

        # Facturas más vencidas (desc por días vencidos)
        query_facturas_mas_vencidas = """
        SELECT TOP 50
          TYP_0 as tipo,
          ACCNUM_0 as asiento,
          BPR_0 as tercero,
          CPY_0 as sociedad,
          DUDDAT_0 as vencimiento,
          DATEDIFF(day, DUDDAT_0, GETDATE()) as dias_vencidos,
          AMTCUR_0 as importe,
          ISNULL(PAYCUR_0,0) as pago,
          (AMTCUR_0 - ISNULL(PAYCUR_0,0)) as pendiente
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE SAC_0 IN ('4300','4302') AND TYP_0 NOT IN ('AA','ZZ')
          AND DUDDAT_0 < GETDATE() AND FLGCLE_0 <> 2
          AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0
        ORDER BY DATEDIFF(day, DUDDAT_0, GETDATE()) DESC;
        """
        
        # Ejecutar las consultas
        from sqlalchemy import text
        
        try:
            res_tot = self.repo_facturas.db.execute(text(query_totales)).fetchone()
            total_empresas = int(res_tot.total_empresas_total or 0)
            total_empresas_cliente = int(res_tot.total_empresas_cliente_debe or 0)
            total_empresas_empresa = int(res_tot.total_empresas_empresa_debe or 0)
            total_facturas = int(res_tot.total_facturas_total or 0)
            total_facturas_cliente = int(res_tot.total_facturas_cliente_debe or 0)
            total_facturas_empresa = int(res_tot.total_facturas_empresa_debe or 0)
            monto_cliente = float(res_tot.monto_total_cliente_debe or 0.0)
            monto_empresa = float(res_tot.monto_total_empresa_debe or 0.0)
            monto_total = float(monto_cliente + monto_empresa)
            saldo_resumen = {
                "all": {
                    "total_empresas": total_empresas,
                    "total_facturas": total_facturas,
                    "total_monto": monto_total,
                },
                "cliente_debe_empresa": {
                    "total_empresas": total_empresas_cliente,
                    "total_facturas": total_facturas_cliente,
                    "total_monto": monto_cliente,
                },
                "empresa_debe_cliente": {
                    "total_empresas": total_empresas_empresa,
                    "total_facturas": total_facturas_empresa,
                    "total_monto": monto_empresa,
                },
            }
            
            # Consulta 4: Empresas con montos (LIMITADO A 50)
            result_empresas_montos = self.repo_facturas.db.execute(text(query_empresas_montos))
            empresas_montos = []
            
            for i, row in enumerate(result_empresas_montos):
                raw_tercero = getattr(row, 'tercero_original', None)
                tercero_original = formatear_tercero_para_facturas(raw_tercero) or (str(raw_tercero).strip() if raw_tercero else '')
                try:
                    tercero_sin_ceros = str(int(tercero_original))
                except Exception:
                    tercero_sin_ceros = str(tercero_original)
                monto = float(row.monto_total) if row.monto_total else 0.0
                
                # Buscar datos del cliente en la base de datos de clientes usando el tercero sin ceros
                datos_cliente = self.repo_clientes.obtener_cliente(tercero_sin_ceros)
                
                # Crear objeto con idcliente, nombre y monto
                saldo_tipo = "cliente_debe_empresa" if monto > 0 else "empresa_debe_cliente" if monto < 0 else "equilibrado"
                empresa_info = {
                    "idcliente": tercero_original,  # Mantener el original para referencia
                    "nombre": datos_cliente.get('razsoc', 'Sin nombre') if datos_cliente else 'Sin nombre',
                    "monto": monto,
                    "monto_absoluto": abs(monto),
                    "saldo_tipo": saldo_tipo,
                }
                empresas_montos.append(empresa_info)
            
            result_sociedades = self.repo_facturas.db.execute(text(query_sociedades_montos))
            sociedades_montos: List[Dict[str, Any]] = []
            # Intentar enriquecer con nombres si existen en repositorio (constante en infra)
            try:
                from app.infrastructure.repositorio_facturas_simple import SOCIEDADES_LABELS
            except Exception:
                SOCIEDADES_LABELS = {}
            for row in result_sociedades:
                codigo = str(row.sociedad).strip() if row.sociedad is not None else ''
                monto = float(row.monto_total) if row.monto_total else 0.0
                sociedades_montos.append({
                    "codigo": codigo,
                    "nombre": SOCIEDADES_LABELS.get(codigo, codigo),
                    "monto": monto,
                })

            result_vencidas = self.repo_facturas.db.execute(text(query_facturas_mas_vencidas))
            facturas_vencidas: List[Dict[str, Any]] = []
            for row in result_vencidas:
                importe = float(row.importe) if row.importe is not None else 0.0
                pago = float(row.pago) if row.pago is not None else 0.0
                pendiente = float(row.pendiente) if row.pendiente is not None else max(0.0, importe - pago)
                facturas_vencidas.append({
                    "tipo": row.tipo,
                    "asiento": row.asiento,
                    "tercero": formatear_tercero_para_facturas(getattr(row, 'tercero', None)),
                    "sociedad": row.sociedad,
                    "vencimiento": row.vencimiento,
                    "dias_vencidos": int(row.dias_vencidos or 0),
                    "importe": importe,
                    "pago": pago,
                    "pendiente": pendiente,
                })
            
            return {
                "total_empresas_pendientes": total_empresas,
                "total_facturas_pendientes": total_facturas,
                "monto_total_adeudado": float(monto_total) if monto_total else 0.0,
                "empresas_con_montos": empresas_montos,
                "sociedades_con_montos": sociedades_montos,
                "facturas_mas_vencidas": facturas_vencidas,
                "saldo_resumen": saldo_resumen,
                "filtros_aplicados": {
                    "tipo_excluido": ["AA", "ZZ"],
                    "colectivo": ["4300", "4302"],
                    "vencidas": True,
                    "flgcle_excluir": 2
                },
                "nota": "Mostrando solo las 50 empresas con mayor monto pendiente"
            }
            
        except Exception as e:
            logger.error(f"Error en el cálculo de estadísticas: {e}")
            raise e 
