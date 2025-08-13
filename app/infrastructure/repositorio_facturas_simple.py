from typing import List, Optional, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text

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
        """Obtiene facturas usando SQL directo con filtros"""
        
        query = """
        SELECT TYP_0 as tipo, ACCNUM_0 as asiento, CPY_0 as sociedad, FCY_0 as planta, 
               CUR_0 as moneda, SAC_0 as colectivo, BPR_0 as tercero, DUDDAT_0 as vencimiento, 
               PAM_0 as forma_pago, SNS_0 as sentido, AMTCUR_0 as importe, PAYCUR_0 as pago, 
               LEVFUP_0 as nivel_reclamacion, DATFUP_0 as fecha_reclamacion, FLGCLE_0 as check_pago
        FROM x3v12.ATISAINT.GACCDUDATE
        WHERE 1=1
        """
        
        params = {}
        
        # Filtros fijos
        query += " AND TYP_0 NOT IN ('AA', 'ZZ')"
        query += " AND SAC_0 = '4300'"
        query += " AND FLGCLE_0 = 1"
        
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
            
            factura_dict = {
                'tipo': row.tipo,
                'asiento': row.asiento,
                'sociedad': row.sociedad,
                'planta': row.planta,
                'moneda': row.moneda,
                'colectivo': row.colectivo,
                'tercero': row.tercero,
                'vencimiento': row.vencimiento,
                'forma_pago': row.forma_pago,
                'sentido': row.sentido,
                'importe': importe,
                'pago': pago,
                'nivel_reclamacion': row.nivel_reclamacion,
                'fecha_reclamacion': row.fecha_reclamacion,
                'check_pago': row.check_pago
            }
            facturas.append(factura_dict)
        
        return facturas

class RepositorioClientes:
    def __init__(self, db_session: Session):
        self.db = db_session

    def obtener_cliente(self, codigo_tercero: str) -> Optional[Dict[str, Any]]:
        """Obtiene datos de un cliente específico"""
        query = """
        SELECT idcliente, razsoc, cif, cif_empresa
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
                'cif_empresa': row.cif_empresa
            }
        return None
 