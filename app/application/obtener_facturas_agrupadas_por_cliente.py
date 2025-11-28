from typing import Dict, Any, List, Optional, Tuple
from datetime import date
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
from app.infrastructure.tercero_helpers import formatear_tercero_para_facturas
import logging

logger = logging.getLogger(__name__)

# Constantes para las consultas SQL
CONDICIONES_FACTURAS_BASE = """
    SAC_0 IN ('4300','4302')
    AND TYP_0 NOT IN ('AA', 'ZZ')
    AND DUDDAT_0 < GETDATE()
    AND FLGCLE_0 <> 2
    AND CPY_0 IN ('S005','S001','S010')
    AND (
        (SNS_0 = -1 OR FLGCLE_0 = -1 OR AMTCUR_0 < 0) OR
        ((FLGCLE_0 = 1) AND (SNS_0 <> -1) AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0)
    )
"""


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
        try:
            # Obtener sociedades por cliente
            sociedades_map = self._obtener_sociedades_por_cliente()
            
            # Obtener asignaciones de consultores
            asignaciones_map = self._obtener_asignaciones_consultores()
            
            # Obtener facturas agrupadas por cliente
            filas_main = self._ejecutar_consulta_principal()
            
            # Procesar cada cliente
            clientes_con_facturas = []
            for row in filas_main:
                cliente_info = self._procesar_cliente(row, sociedades_map, asignaciones_map)
                if cliente_info:
                    clientes_con_facturas.append(cliente_info)
            
            return clientes_con_facturas
            
        except Exception as e:
            logger.error(f"Error en el procesamiento: {e}")
            raise

    def _obtener_sociedades_por_cliente(self) -> Dict[str, set]:
        """Obtiene las sociedades (CPY_0) agrupadas por tercero"""
        from sqlalchemy import text
        
        query = f"""
        SELECT BPR_0 as tercero, CPY_0 as sociedad
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE {CONDICIONES_FACTURAS_BASE}
        GROUP BY BPR_0, CPY_0
        """
        
        res_soc = self.repo_facturas.db.execute(text(query))
        filas_soc = res_soc.fetchall()
        
        sociedades_map = {}
        for row in filas_soc:
            try:
                raw_tercero = row.tercero
                soc = str(row.sociedad).strip()
            except Exception:
                raw_tercero = row[0] if hasattr(row, '__getitem__') else None
                soc = str(row[1]).strip()
            
            key = formatear_tercero_para_facturas(raw_tercero) or (str(raw_tercero).strip() if raw_tercero is not None else '')
            
            if key not in sociedades_map:
                sociedades_map[key] = set()
            if soc:
                sociedades_map[key].add(soc)
                key_sin_ceros = self._normalizar_tercero(key)
                if key_sin_ceros and key_sin_ceros != key:
                    if key_sin_ceros not in sociedades_map:
                        sociedades_map[key_sin_ceros] = set()
                    sociedades_map[key_sin_ceros].add(soc)
        
        return sociedades_map

    def _obtener_asignaciones_consultores(self) -> Dict[int, str]:
        """Obtiene el mapa de asignaciones de consultores por idcliente"""
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
            logger.warning("No se pudieron obtener las asignaciones de consultores")
        
        return asignaciones_map

    def _ejecutar_consulta_principal(self) -> List:
        """Ejecuta la consulta principal de facturas agrupadas por cliente"""
        from sqlalchemy import text
        
        query = f"""
        SELECT 
          BPR_0 as tercero,
          SUM(
            CASE 
              WHEN (FLGCLE_0 = 1) AND (SNS_0 <> -1) AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0 THEN 1
              ELSE 0
            END
          ) as total_facturas,
          SUM(
            CASE 
              WHEN (SNS_0 = -1 OR FLGCLE_0 = -1 OR AMTCUR_0 < 0) THEN -ABS(AMTCUR_0)
              WHEN (FLGCLE_0 = 1) AND (SNS_0 <> -1) AND (AMTCUR_0 - ISNULL(PAYCUR_0,0)) > 0 
                THEN (AMTCUR_0 - ISNULL(PAYCUR_0,0)) 
              ELSE 0 
            END
          ) as monto_pendiente,
          MAX(LEVFUP_0) as nivel_reclamacion_max
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE {CONDICIONES_FACTURAS_BASE}
        GROUP BY BPR_0
        ORDER BY monto_pendiente DESC
        """
        
        res_main = self.repo_facturas.db.execute(text(query))
        return res_main.fetchall()

    def _procesar_cliente(
        self, 
        row: Any, 
        sociedades_map: Dict[str, set], 
        asignaciones_map: Dict[int, str]
    ) -> Optional[Dict[str, Any]]:
        """Procesa una fila de cliente y retorna su información"""
        valor_crudo = getattr(row, 'tercero', None)
        if valor_crudo is None and hasattr(row, '__getitem__'):
            try:
                valor_crudo = row[0]
            except Exception:
                valor_crudo = None
        
        tercero_original = formatear_tercero_para_facturas(valor_crudo) or (str(valor_crudo).strip() if valor_crudo else '')
        tercero_sin_ceros = self._normalizar_tercero(tercero_original)
        
        # Buscar datos del cliente
        datos_cliente = self._buscar_datos_cliente(tercero_sin_ceros, tercero_original)
        
        # Determinar idcliente final
        idcliente_final = self._determinar_idcliente_final(
            tercero_original, 
            tercero_sin_ceros, 
            datos_cliente
        )
        
        # Obtener consultor asignado
        consultor_nombre = self._obtener_consultor_asignado(
            idcliente_final, 
            tercero_sin_ceros, 
            tercero_original, 
            asignaciones_map
        )
        
        # Calcular monto y estado
        saldo_neto = float(row.monto_pendiente) if row.monto_pendiente else 0.0
        saldo_neto = round(saldo_neto, 2)
        if abs(saldo_neto) < 0.01:
            return None

        saldo_tipo = "cliente_debe_empresa" if saldo_neto > 0 else "empresa_debe_cliente"
        monto_absoluto = abs(saldo_neto)

        estado = self._determinar_estado(row.nivel_reclamacion_max)
        
        # Construir información del cliente
        return {
            "idcliente": idcliente_final,
            "idcliente_normalizado": tercero_sin_ceros,
            "nombre_cliente": datos_cliente.get('razsoc') or 'Sin nombre',
            "cif_cliente": datos_cliente.get('cif') or 'Sin CIF',
            "cif_empresa": datos_cliente.get('cif_empresa') or 'Sin CIF empresa',
            "cif_factura": datos_cliente.get('cif_factura') or 'Sin CIF facturación',
            "numero_facturas": row.total_facturas,
            "monto_debe": monto_absoluto,
            "saldo_neto": saldo_neto,
            "saldo_tipo": saldo_tipo,
            "cliente_debe_empresa": saldo_neto > 0,
            "empresa_debe_cliente": saldo_neto < 0,
            "estado": estado,
            "consultor_asignado": consultor_nombre,
            "sociedades": sorted(list(
                sociedades_map.get(tercero_original, set()) | 
                sociedades_map.get(tercero_sin_ceros, set())
            )),
        }

    def _normalizar_tercero(self, tercero_original: str) -> str:
        """Normaliza el tercero quitando ceros iniciales"""
        try:
            return str(int(tercero_original))
        except Exception:
            return tercero_original

    def _buscar_datos_cliente(self, tercero_sin_ceros: str, tercero_original: str) -> Dict[str, Any]:
        """Busca los datos del cliente en la base de datos con varios intentos."""
        if not tercero_sin_ceros and not tercero_original:
            return self._crear_datos_cliente_vacio(tercero_sin_ceros)
        
        # Intento 1: tercero sin ceros (formato que usa la tabla clientes)
        datos_cliente = self.repo_clientes.obtener_cliente(tercero_sin_ceros) or {}
        
        # Intento 2: si no hay resultado, probar con el valor original (con ceros o espacios)
        if not datos_cliente and tercero_original and tercero_original != tercero_sin_ceros:
            datos_cliente = self.repo_clientes.obtener_cliente(tercero_original) or {}
        
        if not datos_cliente:
            return self._crear_datos_cliente_vacio(tercero_sin_ceros or tercero_original)
        
        return datos_cliente

    def _crear_datos_cliente_vacio(self, tercero_sin_ceros: str) -> Dict[str, Any]:
        """Crea un diccionario vacío con los datos del cliente"""
        return {
            "idcliente": tercero_sin_ceros,
            "razsoc": f"Cliente {tercero_sin_ceros or 'N/D'}",
            "cif": None,
            "cif_empresa": None,
            "cif_factura": None,
        }

    def _determinar_idcliente_final(
        self, 
        tercero_original: str, 
        tercero_sin_ceros: str, 
        datos_cliente: Dict[str, Any]
    ) -> str:
        """
        Determina el idcliente final a usar.
        
        IMPORTANTE: 
        - En la tabla clientes, el idcliente se almacena SIN ceros iniciales (ej: '7535')
        - En GACCDUDATE (facturas), el BPR_0 se almacena CON ceros iniciales (ej: '07535')
        - Para buscar facturas en GACCDUDATE, debemos usar tercero_original (con ceros)
        - Para buscar en la tabla clientes, usamos tercero_sin_ceros (sin ceros)
        """
        idcliente_cliente = datos_cliente.get('idcliente')
        
        if not idcliente_cliente:
            return tercero_original or tercero_sin_ceros
        
        try:
            # Comparar numéricamente para ver si son el mismo número
            idcliente_limpio = str(idcliente_cliente).strip().lstrip('0') or '0'
            tercero_limpio = str(tercero_original).strip().lstrip('0') or '0'
            
            idcliente_int = int(idcliente_limpio) if idcliente_limpio.isdigit() else 0
            tercero_int = int(tercero_limpio) if tercero_limpio.isdigit() else 0
            
            if idcliente_int == tercero_int and idcliente_int > 0:
                # Son el mismo número (ej: "7535" en clientes y "07535" en facturas)
                # Usar tercero_original para mantener consistencia con las facturas (BPR_0)
                return tercero_original
            else:
                # Son diferentes números, usar el idcliente del cliente
                return idcliente_cliente
        except Exception:
            # Si hay error en la conversión, usar el tercero_original
            return tercero_original or tercero_sin_ceros

    def _obtener_consultor_asignado(
        self,
        idcliente_final: str,
        tercero_sin_ceros: str,
        tercero_original: str,
        asignaciones_map: Dict[int, str]
    ) -> Optional[str]:
        """Obtiene el consultor asignado para el cliente"""
        try:
            # Intentar buscar el consultor usando diferentes variantes del idcliente
            keys = []
            
            try:
                if str(idcliente_final).isdigit():
                    keys.append(int(idcliente_final))
            except Exception:
                pass
            
            try:
                if str(tercero_sin_ceros).isdigit():
                    keys.append(int(tercero_sin_ceros))
            except Exception:
                pass
                
            try:
                if str(tercero_original).isdigit():
                    keys.append(int(tercero_original))
            except Exception:
                pass
            
            # Buscar en el mapa de asignaciones
            for key in keys:
                consultor = asignaciones_map.get(key)
                if consultor:
                    return consultor
            
            return None
        except Exception:
            return None

    def _determinar_estado(self, nivel_reclamacion_max: Optional[int]) -> str:
        """Determina el estado del cliente basado en el nivel de reclamación"""
        nivel_max = nivel_reclamacion_max or 0
        if nivel_max >= 3:
            return "rojo"
        elif nivel_max == 2:
            return "amarillo"
        else:
            return "verde"
