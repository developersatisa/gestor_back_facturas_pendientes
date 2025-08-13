from typing import List, Optional
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.domain.models.Factura import Factura
import os

class RepositorioFacturas:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)

    def obtener_facturas(
        self,
        sociedad: Optional[str] = None,
        tercero: Optional[str] = None,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        nivel_reclamacion: Optional[int] = None,
    ) -> List[Factura]:
        query = """
        SELECT TYP_0 as tipo, ACCNUM_0 as asiento, CPY_0 as sociedad, FCY_0 as planta, CUR_0 as moneda, SAC_0 as colectivo, BPR_0 as tercero, DUDDAT_0 as vencimiento, PAM_0 as forma_pago, SNS_0 as sentido, AMTCUR_0 as importe, PAYCUR_0 as pago, LEVFUP_0 as nivel_reclamacion, DATFUP_0 as fecha_reclamacion, FLGCLE_0 as check_pago
        FROM ATISAINT.GACCDUDATE
        WHERE 1=1
        """
        params = {}
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
            query += " AND NRECL_0 = :nivel_reclamacion"
            params["nivel_reclamacion"] = nivel_reclamacion
        # Excluir TYP_0 'AA', 'ZZ' y filtrar por SAC_0 = '4300' y FLGCLE_0 = 1
        query += " AND TYP_0 NOT IN ('AA', 'ZZ')"
        query += " AND SAC_0 = '4300'"
        query += " AND FLGCLE_0 = 1"
        with self.Session() as session:
            result = session.execute(text(query), params)
            facturas = []
            for row in result:
                # Convertir a diccionario de forma segura
                row_dict = {}
                for i, value in enumerate(row):
                    if hasattr(row, '_fields') and i < len(row._fields):
                        key = row._fields[i]
                    else:
                        key = f"col_{i}"
                    row_dict[key] = value
                facturas.append(Factura(**row_dict))
        return facturas

class RepositorioClientes:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)

    def obtener_cliente(self, codigo_tercero: str):
        """Obtiene datos de un cliente específico"""
        query = """
        SELECT * FROM dbo.clientes WHERE idcliente = :codigo_tercero
        """
        with self.Session() as session:
            result = session.execute(text(query), {"codigo_tercero": codigo_tercero})
            return result.fetchone()

    def obtener_clientes(self):
        """Obtiene todos los clientes"""
        query = """
        SELECT * FROM dbo.clientes
        """
        with self.Session() as session:
            result = session.execute(text(query))
            clientes = []
            for row in result:
                # Convertir a diccionario de forma segura
                cliente_dict = {}
                for i, value in enumerate(row):
                    if hasattr(row, '_fields') and i < len(row._fields):
                        key = row._fields[i]
                    else:
                        key = f"col_{i}"
                    cliente_dict[key] = value
                clientes.append(cliente_dict)
            return clientes 