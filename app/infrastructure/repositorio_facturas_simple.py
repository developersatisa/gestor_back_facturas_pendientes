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
                'tercero': row.tercero,
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
                    "tercero": row.tercero,
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

class RepositorioClientes:
    def __init__(self, db_session: Session):
        self.db = db_session

    def obtener_cliente(self, codigo_tercero: str) -> Optional[Dict[str, Any]]:
        """Obtiene datos de un cliente específico"""
        query = """
        SELECT idcliente, razsoc, cif, cif_empresa, cif_factura
        FROM dbo.clientes 
        WHERE idcliente = :codigo_tercero
        """
        
        result = self.db.execute(text(query), {"codigo_tercero": codigo_tercero})
        row = result.fetchone()
        
        if row:
            return {
                'idcliente': row.idcliente,
                'razsoc': row.razsoc,
                'cif': row.cif,
                'cif_empresa': row.cif_empresa,
                'cif_factura': getattr(row, "cif_factura", None)
            }
        return None
 
