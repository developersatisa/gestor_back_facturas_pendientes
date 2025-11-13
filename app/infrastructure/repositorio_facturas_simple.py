from typing import List, Optional, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.domain.constants import SOCIEDADES_NAMES

# Mantener compatibilidad con código existente
SOCIEDADES_LABELS = SOCIEDADES_NAMES

class RepositorioFacturas:
    def __init__(self, db_session: Session):
        self.db = db_session

    def obtener_facturas(
        self,
        sociedad: Optional[str] = None,
        tercero: Optional[str] = None,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        nivel_reclamacion: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Obtiene facturas usando SQL directo con filtros.

        Nota: requiere MSSQL (SAGE X3). En otros motores (p.ej. SQLite
        por defecto en desarrollo) devuelve una lista vacía para evitar errores.
        """

        try:
            bind = self.db.get_bind()  # type: ignore[attr-defined]
            if not bind or bind.dialect.name != 'mssql':
                return []
        except Exception:
            return []
        
        query = """
        SELECT TYP_0 as tipo, ACCNUM_0 as asiento, NUM_0 as nombre_factura, CPY_0 as sociedad, FCY_0 as planta, 
               CUR_0 as moneda, SAC_0 as colectivo, BPR_0 as tercero, DUDDAT_0 as vencimiento, 
               PAM_0 as forma_pago, SNS_0 as sentido, AMTCUR_0 as importe, PAYCUR_0 as pago, 
               LEVFUP_0 as nivel_reclamacion, DATFUP_0 as fecha_reclamacion, FLGCLE_0 as check_pago
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE 1=1
        """
        
        params = {}
        
        # Filtros fijos
        query += " AND TYP_0 NOT IN ('AA', 'ZZ')"
        query += " AND SAC_0 IN ('4300','4302')"
        # Limitar a las sociedades permitidas (CPY_0): S005, S001, S010
        query += " AND CPY_0 IN ('S005','S001','S010')"
        # Solo facturas vencidas: DUDDAT_0 anterior a la fecha actual
        query += " AND DUDDAT_0 < GETDATE()"
        # Mostrar solo facturas con importe pendiente: importe > pagado
        query += " AND (AMTCUR_0 - ISNULL(PAYCUR_0, 0)) > 0"
        
        # Filtros opcionales
        if sociedad:
            query += " AND CPY_0 = :sociedad"
            params["sociedad"] = sociedad
        if tercero:
            tercero_str = str(tercero).strip()
            tercero_sin_ceros = tercero_str.lstrip('0') or tercero_str
            params["tercero"] = tercero_str
            params["tercero_sin_ceros"] = tercero_sin_ceros
            len_tercero = len(tercero_sin_ceros) or 1
            params["len_tercero"] = len_tercero
            query += """
            AND (
                BPR_0 = :tercero
                OR LTRIM(RTRIM(BPR_0)) = :tercero
                OR LTRIM(RTRIM(BPR_0)) = :tercero_sin_ceros
                OR RIGHT(LTRIM(RTRIM(BPR_0)), :len_tercero) = :tercero_sin_ceros
            )
            """
        if fecha_desde:
            query += " AND DUDDAT_0 >= :fecha_desde"
            params["fecha_desde"] = fecha_desde
        if fecha_hasta:
            query += " AND DUDDAT_0 <= :fecha_hasta"
            params["fecha_hasta"] = fecha_hasta
        if nivel_reclamacion is not None:
            query += " AND LEVFUP_0 = :nivel_reclamacion"
            params["nivel_reclamacion"] = nivel_reclamacion
        
        # Ordenar por fecha de vencimiento (más cercanas primero)
        query += " ORDER BY DUDDAT_0 ASC"
        
        # Ejecutar query
        result = self.db.execute(text(query), params)
        
        # Convertir a formato de respuesta
        facturas = []
        for row in result:
            # Formatear valores decimales para evitar notación científica
            importe = float(row.importe) if row.importe is not None else 0.0
            pago = float(row.pago) if row.pago is not None else 0.0
            pendiente = round(importe - pago, 2)
            if pendiente <= 0:
                # Seguridad adicional por si el filtro SQL no aplica por driver
                continue
            
            factura_dict = {
                'tipo': row.tipo,
                'asiento': row.asiento,
                'nombre_factura': getattr(row, 'nombre_factura', None),
                'sociedad': row.sociedad,
                'sociedad_nombre': SOCIEDADES_LABELS.get(str(row.sociedad).strip(), None),
                'planta': row.planta,
                'moneda': row.moneda,
                'colectivo': row.colectivo,
                'tercero': str(row.tercero).strip() if getattr(row, 'tercero', None) is not None else None,
                'vencimiento': row.vencimiento,
                'forma_pago': row.forma_pago,
                'sentido': row.sentido,
                'importe': importe,
                'pago': pago,
                'pendiente': pendiente,
                'nivel_reclamacion': row.nivel_reclamacion,
                'fecha_reclamacion': row.fecha_reclamacion,
                'check_pago': row.check_pago
            }
            facturas.append(factura_dict)
        
        return facturas

    def buscar_por_numero(self, numero: str) -> List[Dict[str, Any]]:
        """Busca facturas por coincidencia con número o asiento."""
        patron = (numero or "").strip()
        if not patron:
            return []

        try:
            bind = self.db.get_bind()  # type: ignore[attr-defined]
            if not bind or bind.dialect.name != 'mssql':
                return []
        except Exception:
            return []

        query = """
        SELECT TOP 25 TYP_0 as tipo, ACCNUM_0 as asiento, NUM_0 as nombre_factura, CPY_0 as sociedad,
               FCY_0 as planta, CUR_0 as moneda, SAC_0 as colectivo, BPR_0 as tercero,
               DUDDAT_0 as vencimiento, PAM_0 as forma_pago, SNS_0 as sentido,
               AMTCUR_0 as importe, PAYCUR_0 as pago, LEVFUP_0 as nivel_reclamacion,
               DATFUP_0 as fecha_reclamacion, FLGCLE_0 as check_pago
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE 1=1
          AND TYP_0 NOT IN ('AA', 'ZZ')
          AND SAC_0 IN ('4300','4302')
          AND CPY_0 IN ('S005','S001','S010')
          AND DUDDAT_0 < GETDATE()
          AND (AMTCUR_0 - ISNULL(PAYCUR_0, 0)) > 0
          AND (ACCNUM_0 LIKE :patron OR NUM_0 LIKE :patron)
        ORDER BY DUDDAT_0 DESC
        """
        params = {"patron": f"%{patron}%"}

        result = self.db.execute(text(query), params)

        coincidencias: List[Dict[str, Any]] = []
        for row in result:
            importe = float(row.importe) if row.importe is not None else 0.0
            pago = float(row.pago) if row.pago is not None else 0.0
            pendiente = max(0.0, round(importe - pago, 2))

            coincidencias.append(
                {
                    "tipo": row.tipo,
                    "asiento": row.asiento,
                    "nombre_factura": getattr(row, "nombre_factura", None),
                    "sociedad": row.sociedad,
                    "sociedad_nombre": SOCIEDADES_LABELS.get(str(row.sociedad).strip(), None),
                    "planta": row.planta,
                    "moneda": row.moneda,
                    "colectivo": row.colectivo,
                    "tercero": str(row.tercero).strip() if getattr(row, 'tercero', None) is not None else None,
                    "vencimiento": row.vencimiento,
                    "forma_pago": row.forma_pago,
                    "sentido": row.sentido,
                    "importe": importe,
                    "pago": pago,
                    "pendiente": pendiente,
                    "nivel_reclamacion": row.nivel_reclamacion,
                    "fecha_reclamacion": row.fecha_reclamacion,
                    "check_pago": row.check_pago,
                }
            )
        return coincidencias


    def buscar_por_numero_incluyendo_pagadas(self, numero: str) -> List[Dict[str, Any]]:
        """Busca facturas por número o asiento sin filtrar por saldo pendiente."""
        patron = (numero or "").strip()
        if not patron:
            return []

        try:
            bind = self.db.get_bind()  # type: ignore[attr-defined]
            if not bind or bind.dialect.name != 'mssql':
                return []
        except Exception:
            return []

        query = """
        SELECT TOP 25 TYP_0 as tipo, ACCNUM_0 as asiento, NUM_0 as nombre_factura, CPY_0 as sociedad,
               FCY_0 as planta, CUR_0 as moneda, SAC_0 as colectivo, BPR_0 as tercero,
               DUDDAT_0 as vencimiento, PAM_0 as forma_pago, SNS_0 as sentido,
               AMTCUR_0 as importe, PAYCUR_0 as pago, LEVFUP_0 as nivel_reclamacion,
               DATFUP_0 as fecha_reclamacion, FLGCLE_0 as check_pago
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE 1=1
          AND TYP_0 NOT IN ('AA', 'ZZ')
          AND SAC_0 IN ('4300','4302')
          AND CPY_0 IN ('S005','S001','S010')
          AND DUDDAT_0 < GETDATE()
          AND (ACCNUM_0 LIKE :patron OR NUM_0 LIKE :patron)
        ORDER BY DUDDAT_0 DESC
        """
        params = {"patron": f"%{patron}%"}

        result = self.db.execute(text(query), params)

        coincidencias: List[Dict[str, Any]] = []
        for row in result:
            importe = float(row.importe) if row.importe is not None else 0.0
            pago = float(row.pago) if row.pago is not None else 0.0
            pendiente = round(importe - pago, 2)

            coincidencias.append(
                {
                    "tipo": row.tipo,
                    "asiento": row.asiento,
                    "nombre_factura": getattr(row, "nombre_factura", None),
                    "sociedad": row.sociedad,
                    "sociedad_nombre": SOCIEDADES_LABELS.get(str(row.sociedad).strip(), None),
                    "planta": row.planta,
                    "moneda": row.moneda,
                    "colectivo": row.colectivo,
                    "tercero": str(row.tercero).strip() if getattr(row, 'tercero', None) is not None else None,
                    "vencimiento": row.vencimiento,
                    "forma_pago": row.forma_pago,
                    "sentido": row.sentido,
                    "importe": importe,
                    "pago": pago,
                    "pendiente": pendiente,
                    "nivel_reclamacion": row.nivel_reclamacion,
                    "fecha_reclamacion": row.fecha_reclamacion,
                    "check_pago": row.check_pago,
                }
            )
        return coincidencias

    def obtener_factura_especifica(
        self,
        *,
        tercero: str,
        tipo: str,
        asiento: str,
    ) -> Optional[Dict[str, Any]]:
        """Obtiene una factura concreta sin filtrar por estado o vencimiento."""
        try:
            bind = self.db.get_bind()  # type: ignore[attr-defined]
            if not bind or bind.dialect.name != 'mssql':
                return None
        except Exception:
            return None

        tercero_str = str(tercero).strip()
        tercero_sin_ceros = tercero_str.lstrip('0') or tercero_str

        # Convertir asiento a entero si es posible, para la comparación en SQL
        try:
            asiento_int = int(asiento) if asiento else None
        except (ValueError, TypeError):
            asiento_int = None

        query = """
        SELECT TOP 1
            TYP_0 as tipo,
            ACCNUM_0 as asiento,
            NUM_0 as nombre_factura,
            CPY_0 as sociedad,
            SAC_0 as colectivo,
            BPR_0 as tercero,
            DUDDAT_0 as vencimiento,
            AMTCUR_0 as importe,
            PAYCUR_0 as pago,
            FLGCLE_0 as check_pago
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE TYP_0 = :tipo
          AND (
            ACCNUM_0 = :asiento_int
            OR CAST(ACCNUM_0 AS VARCHAR(50)) = :asiento
          )
          AND SAC_0 IN ('4300','4302')
          AND CPY_0 IN ('S005','S001','S010')
          AND (
                BPR_0 = :tercero
                OR LTRIM(RTRIM(BPR_0)) = :tercero
                OR LTRIM(RTRIM(BPR_0)) = :tercero_sin_ceros
                OR RIGHT(LTRIM(RTRIM(BPR_0)), :len_tercero) = :tercero_sin_ceros
              )
        """

        params = {
            "tipo": tipo,
            "asiento": str(asiento).strip(),
            "asiento_int": asiento_int,
            "tercero": tercero_str,
            "tercero_sin_ceros": tercero_sin_ceros,
            "len_tercero": len(tercero_sin_ceros) or 1,
        }

        result = self.db.execute(text(query), params)
        row = result.fetchone()
        
        # Si no se encuentra con los filtros restrictivos, intentar sin filtros de SAC_0 y CPY_0
        if not row:
            query_sin_filtros = """
            SELECT TOP 1
                TYP_0 as tipo,
                ACCNUM_0 as asiento,
                NUM_0 as nombre_factura,
                CPY_0 as sociedad,
                SAC_0 as colectivo,
                BPR_0 as tercero,
                DUDDAT_0 as vencimiento,
                AMTCUR_0 as importe,
                PAYCUR_0 as pago,
                FLGCLE_0 as check_pago
            FROM x3v12.ATISAINT.GACCDUDATE
            WHERE TYP_0 = :tipo
              AND (
                ACCNUM_0 = :asiento_int
                OR CAST(ACCNUM_0 AS VARCHAR(50)) = :asiento
              )
              AND (
                    BPR_0 = :tercero
                    OR LTRIM(RTRIM(BPR_0)) = :tercero
                    OR LTRIM(RTRIM(BPR_0)) = :tercero_sin_ceros
                    OR RIGHT(LTRIM(RTRIM(BPR_0)), :len_tercero) = :tercero_sin_ceros
                  )
            """
            try:
                result_sin_filtros = self.db.execute(text(query_sin_filtros), params)
                row = result_sin_filtros.fetchone()
            except Exception:
                pass
        
        if not row:
            return None

        importe = float(row.importe) if row.importe is not None else 0.0
        pago = float(row.pago) if row.pago is not None else 0.0
        pendiente = round(importe - pago, 2)

        # Obtener nombre_factura (NUM_0) con manejo robusto
        nombre_factura = self._extraer_nombre_factura(row)

        return {
            "tipo": row.tipo,
            "asiento": row.asiento,
            "nombre_factura": nombre_factura,
            "sociedad": row.sociedad,
            "colectivo": row.colectivo,
            "tercero": str(row.tercero).strip() if getattr(row, "tercero", None) is not None else None,
            "vencimiento": row.vencimiento,
            "importe": importe,
            "pago": pago,
            "pendiente": pendiente,
            "check_pago": row.check_pago,
        }
    
    def _extraer_nombre_factura(self, row) -> Optional[str]:
        """Extrae el nombre de factura (NUM_0) de una fila de resultado SQL."""
        try:
            # Intentar con el alias del SELECT
            nombre_factura = getattr(row, "nombre_factura", None)
            if nombre_factura:
                return str(nombre_factura).strip()
            
            # Intentar acceder como diccionario (SQLAlchemy Row)
            if hasattr(row, '_mapping'):
                nombre_factura = row._mapping.get('nombre_factura')
                if nombre_factura:
                    return str(nombre_factura).strip()
            
            # Fallback: intentar por índice (NUM_0 es la tercera columna, índice 2)
            if hasattr(row, '__getitem__'):
                try:
                    nombre_factura = row[2]
                    if nombre_factura:
                        return str(nombre_factura).strip()
                except (IndexError, TypeError):
                    pass
        except Exception:
            pass
        
        return None

class RepositorioClientes:
    def __init__(self, db_session: Session):
        self.db = db_session

    def obtener_cliente(self, codigo_tercero: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene datos de un cliente específico.
        
        IMPORTANTE: Busca primero coincidencias exactas para evitar falsos positivos.
        Por ejemplo, al buscar '7535' no debe encontrar '17535' aunque termine en '7535'.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        codigo_original = str(codigo_tercero).strip()
        codigo_trim = codigo_original.lstrip('0') or codigo_original
        
        try:
            codigo_int = int(codigo_trim)
        except Exception:
            codigo_int = None

        # Buscar primero con coincidencias exactas
        row = self._buscar_cliente_exacto(codigo_original, codigo_trim, codigo_int)
        
        # Si no se encontró, intentar búsqueda más flexible con restricción de longitud
        if not row and codigo_int is not None:
            row = self._buscar_cliente_flexible(codigo_trim, codigo_int)
        
        if row:
            return self._procesar_resultado_cliente(row, codigo_tercero)
        
        logger.debug(f"No se encontró cliente para código '{codigo_tercero}'")
        return None

    def _buscar_cliente_exacto(
        self, 
        codigo_original: str, 
        codigo_trim: str, 
        codigo_int: Optional[int]
    ) -> Optional[Any]:
        """Busca cliente con coincidencias exactas"""
        import logging
        logger = logging.getLogger(__name__)
        
        query = """
        SELECT TOP 1
            LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50)))) AS idcliente,
            NULLIF(LTRIM(RTRIM(razsoc)), '') AS razsoc,
            NULLIF(LTRIM(RTRIM(cif)), '') AS cif,
            NULLIF(LTRIM(RTRIM(cif_empresa)), '') AS cif_empresa,
            NULLIF(LTRIM(RTRIM(cif_factura)), '') AS cif_factura
        FROM dbo.clientes 
        WHERE
            LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50)))) = :codigo_tercero
            OR LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50)))) = :codigo_trim
            OR (
                :codigo_int IS NOT NULL
                AND TRY_CONVERT(INT, LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50))))) = :codigo_int
                AND LEN(LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50))))) <= LEN(:codigo_trim) + 1
            )
        ORDER BY 
            CASE 
                WHEN LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50)))) = :codigo_trim THEN 1
                WHEN LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50)))) = :codigo_tercero THEN 2
                ELSE 3
            END
        """
        
        try:
            result = self.db.execute(text(query), {
                "codigo_tercero": codigo_original,
                "codigo_trim": codigo_trim,
                "codigo_int": codigo_int,
            })
            return result.fetchone()
        except Exception as e:
            logger.warning(f"Error en búsqueda exacta de cliente: {e}")
            return None

    def _buscar_cliente_flexible(self, codigo_trim: str, codigo_int: int) -> Optional[Any]:
        """
        Busca cliente con comparación numérica pero con restricción de longitud.
        
        IMPORTANTE: Si buscamos '7535' (4 dígitos), solo busca idcliente con 4 o 5 caracteres
        (ej: '7535' o '07535'). NO busca '17535' (5 dígitos) aunque numéricamente termine en '7535'.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        len_buscado = len(codigo_trim)
        query = """
        SELECT TOP 1
            LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50)))) AS idcliente,
            NULLIF(LTRIM(RTRIM(razsoc)), '') AS razsoc,
            NULLIF(LTRIM(RTRIM(cif)), '') AS cif,
            NULLIF(LTRIM(RTRIM(cif_empresa)), '') AS cif_empresa,
            NULLIF(LTRIM(RTRIM(cif_factura)), '') AS cif_factura
        FROM dbo.clientes 
        WHERE TRY_CONVERT(INT, LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50))))) = :codigo_int
          AND LEN(LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50))))) BETWEEN :len_min AND :len_max
        ORDER BY 
            CASE 
                WHEN LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50)))) = :codigo_trim THEN 1
                ELSE 2
            END,
            LEN(LTRIM(RTRIM(CAST(idcliente AS NVARCHAR(50))))) ASC
        """
        
        try:
            result = self.db.execute(text(query), {
                "codigo_int": codigo_int,
                "codigo_trim": codigo_trim,
                "len_min": len_buscado,
                "len_max": len_buscado + 1
            })
            return result.fetchone()
        except Exception as e:
            logger.warning(f"Error en búsqueda flexible de cliente: {e}")
        return None

    def _procesar_resultado_cliente(self, row: Any, codigo_tercero: str) -> Dict[str, Any]:
        """Procesa el resultado de la consulta y retorna un diccionario limpio"""
        import logging
        logger = logging.getLogger(__name__)
        
        def _clean(value):
            if value is None:
                return None
            texto = str(value).strip()
            return texto or None
        
        cliente_data = {
            'idcliente': _clean(getattr(row, "idcliente", None)),
            'razsoc': _clean(getattr(row, "razsoc", None)),
            'cif': _clean(getattr(row, "cif", None)),
            'cif_empresa': _clean(getattr(row, "cif_empresa", None)),
            'cif_factura': _clean(getattr(row, "cif_factura", None)),
        }
        
        logger.debug(f"Cliente encontrado para código '{codigo_tercero}': {cliente_data.get('razsoc', 'Sin nombre')}")
        return cliente_data
 
