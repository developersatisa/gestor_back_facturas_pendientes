from typing import Dict, Any, List
from datetime import date
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
import logging

logger = logging.getLogger(__name__)

class ObtenerFacturasAgrupadasPorCliente:
    def __init__(self, repo_facturas: RepositorioFacturas, repo_clientes: RepositorioClientes, repo_gestion=None):
        self.repo_facturas = repo_facturas
        self.repo_clientes = repo_clientes
        self.repo_gestion = repo_gestion

    def execute(
        self,
        sociedad: str = None,
        tercero: str = None,
        fecha_desde: date = None,
        fecha_hasta: date = None,
        nivel_reclamacion: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene facturas agrupadas por cliente con resumen de montos
        """
        logger.info("Iniciando obtención de facturas agrupadas por cliente...")
        
        # Consulta para obtener facturas agrupadas por cliente (condiciones solicitadas)
        # - SAC_0 en ('4300','4302')
        # - Excluir tipos 'AA' y 'ZZ'
        # - Solo vencidas a hoy (DUDDAT_0 < GETDATE())
        # IMPORTANTE: Usar las mismas condiciones que el Excel para mantener consistencia
        query = """
        SELECT 
          BPR_0 as tercero,
          -- Contar solo facturas con saldo pendiente (excluye abonos)
          SUM(
            CASE 
              WHEN (FLGCLE_0 = 1) AND (SNS_0 <> -1) AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0 THEN 1
              ELSE 0
            END
          ) as total_facturas,
          -- Monto pendiente neto = (pendiente facturas) - (abonos)
          SUM(
            CASE 
              WHEN (SNS_0 = -1 OR FLGCLE_0 = -1 OR AMTCUR_0 < 0) THEN -ABS(AMTCUR_0)
              WHEN (FLGCLE_0 = 1) AND (SNS_0 <> -1) AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0 
                THEN (AMTCUR_0 - ISNULL(PAYCUR_0,0)) 
              ELSE 0 
            END
          ) as monto_pendiente,
          MAX(LEVFUP_0) as nivel_reclamacion_max
        FROM 
          x3v12.ATISAINT.GACCDUDATE
        WHERE 
          SAC_0 IN ('4300','4302')
          AND TYP_0 NOT IN ('AA', 'ZZ')
          AND DUDDAT_0 < GETDATE()
          AND FLGCLE_0 <> 2
          AND CPY_0 IN ('S005','S001','S010')
          -- Misma condición que el Excel: solo incluir facturas con saldo pendiente o abonos
          AND (
            (SNS_0 = -1 OR FLGCLE_0 = -1 OR AMTCUR_0 < 0) OR
            ((FLGCLE_0 = 1) AND (SNS_0 <> -1) AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0)
          )

        """
        
        params = {}
        
        # Sin filtros adicionales (se solicitó quitar todos excepto búsqueda en frontend)
        
        query += """
        GROUP BY 
          BPR_0
        ORDER BY 
          monto_pendiente DESC
        """

        # Consulta auxiliar: sociedades por cliente (CPY_0) con saldo pendiente
        # IMPORTANTE: Usar las mismas condiciones que el Excel y la consulta principal
        query_sociedades = """
        SELECT BPR_0 as tercero, CPY_0 as sociedad
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE SAC_0 IN ('4300','4302')
          AND TYP_0 NOT IN ('AA','ZZ')
          AND DUDDAT_0 < GETDATE()
          AND FLGCLE_0 <> 2
          AND CPY_0 IN ('S005','S001','S010')
          -- Misma condición que el Excel: solo incluir facturas con saldo pendiente o abonos
          AND (
            (SNS_0 = -1 OR FLGCLE_0 = -1 OR AMTCUR_0 < 0) OR
            ((FLGCLE_0 = 1) AND (SNS_0 <> -1) AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0)
          )
        GROUP BY BPR_0, CPY_0
        """
        
        from sqlalchemy import text
        
        try:
            logger.info("Ejecutando consulta de facturas agrupadas por cliente...")
            # Para evitar 'Connection is busy with results for another command' en pyodbc,
            # ejecutamos y consumimos primero la consulta de sociedades y luego la principal.
            res_soc = self.repo_facturas.db.execute(text(query_sociedades))
            filas_soc = res_soc.fetchall()
            sociedades_map = {}
            for row in filas_soc:
                try:
                    key = str(row.tercero).strip()
                except Exception:
                    key = str(row[0]).strip()
                try:
                    soc = str(row.sociedad).strip()
                except Exception:
                    soc = str(row[1]).strip()
                if key not in sociedades_map:
                    sociedades_map[key] = set()
                if soc:
                    sociedades_map[key].add(soc)

            # Ahora ejecutamos la consulta principal y la iteramos
            res_main = self.repo_facturas.db.execute(text(query), params)
            clientes_con_facturas = []

            # Mapa de asignaciones de consultor por idcliente (int)
            asignaciones_map = {}
            try:
                if self.repo_gestion is not None:
                    asignaciones = self.repo_gestion.listar_asignaciones()
                    for a in asignaciones:
                        try:
                            asignaciones_map[int(a.get('idcliente'))] = a.get('consultor_nombre')
                        except Exception:
                            continue
            except Exception:
                # No bloquear respuesta si falla la consulta de asignaciones
                asignaciones_map = {}
            
            for row in res_main:
                tercero_original = str(row.tercero).strip() if row.tercero is not None else ''
                # Normalizar ID: intentar quitar ceros; si no es numérico, usar original
                try:
                    tercero_sin_ceros = str(int(tercero_original))
                except Exception:
                    tercero_sin_ceros = tercero_original
                
                # Buscar datos del cliente
                datos_cliente = {}
                if tercero_sin_ceros:
                    datos_cliente = self.repo_clientes.obtener_cliente(tercero_sin_ceros) or {}
                    if datos_cliente:
                        logger.debug(f"Cliente encontrado con código normalizado '{tercero_sin_ceros}': {datos_cliente.get('razsoc', 'Sin nombre')}")
                if not datos_cliente and tercero_original and tercero_original != tercero_sin_ceros:
                    datos_cliente = self.repo_clientes.obtener_cliente(tercero_original) or {}
                    if datos_cliente:
                        logger.debug(f"Cliente encontrado con código original '{tercero_original}': {datos_cliente.get('razsoc', 'Sin nombre')}")

                if not datos_cliente:
                    logger.warning(f"No se encontraron datos del cliente para tercero '{tercero_original}' (normalizado: '{tercero_sin_ceros}')")
                    datos_cliente = {
                        "idcliente": tercero_sin_ceros or tercero_original,
                        "razsoc": None,
                        "cif": None,
                        "cif_empresa": None,
                        "cif_factura": None,
                    }
                # Consultor asignado (si existe asignación)
                consultor_nombre = None
                try:
                    key1 = int(tercero_sin_ceros) if str(tercero_sin_ceros).isdigit() else None
                    key2 = int(tercero_original) if str(tercero_original).isdigit() else None
                    consultor_nombre = (asignaciones_map.get(key1) if key1 is not None else None) or (asignaciones_map.get(key2) if key2 is not None else None)
                except Exception:
                    consultor_nombre = None
                
                # Monto pendiente ya viene calculado desde SQL
                monto_pendiente = float(row.monto_pendiente) if row.monto_pendiente else 0.0
                logger.debug(
                    "Resumen cliente %s (normalizado %s): saldo bruto=%.4f, facturas=%s",
                    tercero_original,
                    tercero_sin_ceros,
                    monto_pendiente,
                    getattr(row, "total_facturas", None),
                )
                
                # Determinar estado basado en nivel de reclamación
                nivel_max = row.nivel_reclamacion_max or 0
                if nivel_max >= 3:
                    estado = "rojo"
                elif nivel_max == 2:
                    estado = "amarillo"
                else:
                    estado = "verde"
                
                # Filtrar clientes sin saldo pendiente neto significativo
                if round(monto_pendiente, 2) <= 0:
                    continue
                
                # Acceso seguro a alias agregados (según driver pueden variar may/min)
                cliente_info = {
                    "idcliente": tercero_original or tercero_sin_ceros,
                    "idcliente_normalizado": tercero_sin_ceros,
                    "nombre_cliente": (datos_cliente.get('razsoc') if datos_cliente else None) or 'Sin nombre',
                    "cif_cliente": (datos_cliente.get('cif') if datos_cliente else None) or 'Sin CIF',
                    "cif_empresa": (datos_cliente.get('cif_empresa') if datos_cliente else None) or 'Sin CIF empresa',
                    "cif_factura": (datos_cliente.get('cif_factura') if datos_cliente else None) or 'Sin CIF facturación',
                    "numero_facturas": row.total_facturas,
                    "monto_debe": monto_pendiente,
                    "estado": estado,
                    "consultor_asignado": consultor_nombre,
                    "sociedades": sorted(list(sociedades_map.get(tercero_original, set()) | sociedades_map.get(tercero_sin_ceros, set()))),
                }
                
                clientes_con_facturas.append(cliente_info)
            
            logger.info(f"Procesamiento completado. {len(clientes_con_facturas)} clientes encontrados.")
            
            return clientes_con_facturas
            
        except Exception as e:
            logger.error(f"Error en el procesamiento: {e}")
            raise e 
