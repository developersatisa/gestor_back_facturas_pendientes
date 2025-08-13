from typing import List, Optional, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, not_
from app.domain.models.Factura import Factura
from app.domain.models.sqlalchemy_models import Factura as FacturaORM, Cliente as ClienteORM

class RepositorioFacturasORM:
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
        """Obtiene facturas usando ORM con filtros"""
        
        # Construir query base
        query = self.db.query(FacturaORM)
        
        # Aplicar filtros
        filters = []
        
        # Filtros fijos
        filters.append(FacturaORM.TYP_0.notin_(['AA', 'ZZ']))
        filters.append(FacturaORM.SAC_0 == '4300')
        filters.append(FacturaORM.FLGCLE_0 == 1)
        
        # Filtros opcionales
        if sociedad:
            filters.append(FacturaORM.CPY_0 == sociedad)
        if tercero:
            filters.append(FacturaORM.BPR_0 == tercero)
        if fecha_desde:
            filters.append(FacturaORM.DUDDAT_0 >= fecha_desde)
        if fecha_hasta:
            filters.append(FacturaORM.DUDDAT_0 <= fecha_hasta)
        if nivel_reclamacion is not None:
            filters.append(FacturaORM.LEVFUP_0 == nivel_reclamacion)
        
        # Aplicar todos los filtros
        query = query.filter(and_(*filters))
        
        # Ejecutar query
        facturas_orm = query.all()
        
        # Convertir a formato de respuesta
        facturas = []
        for factura_orm in facturas_orm:
            factura_dict = {
                'tipo': factura_orm.TYP_0,
                'asiento': factura_orm.ACCNUM_0,
                'sociedad': factura_orm.CPY_0,
                'planta': factura_orm.FCY_0,
                'moneda': factura_orm.CUR_0,
                'colectivo': factura_orm.SAC_0,
                'tercero': factura_orm.BPR_0,
                'vencimiento': factura_orm.DUDDAT_0,
                'forma_pago': factura_orm.PAM_0,
                'sentido': factura_orm.SNS_0,
                'importe': factura_orm.AMTCUR_0,
                'pago': factura_orm.PAYCUR_0,
                'nivel_reclamacion': factura_orm.LEVFUP_0,
                'fecha_reclamacion': factura_orm.DATFUP_0,
                'check_pago': factura_orm.FLGCLE_0
            }
            facturas.append(factura_dict)
        
        return facturas

class RepositorioClientesORM:
    def __init__(self, db_session: Session):
        self.db = db_session

    def obtener_cliente(self, codigo_tercero: str) -> Optional[Dict[str, Any]]:
        """Obtiene datos de un cliente específico"""
        cliente_orm = self.db.query(ClienteORM).filter(
            ClienteORM.idcliente == codigo_tercero
        ).first()
        
        if cliente_orm:
            return {
                'idcliente': cliente_orm.idcliente,
                'nombre': cliente_orm.nombre,
                'email': cliente_orm.email,
                'telefono': cliente_orm.telefono,
                'direccion': cliente_orm.direccion
            }
        return None

    def obtener_clientes(self) -> List[Dict[str, Any]]:
        """Obtiene todos los clientes"""
        clientes_orm = self.db.query(ClienteORM).all()
        
        clientes = []
        for cliente_orm in clientes_orm:
            cliente_dict = {
                'idcliente': cliente_orm.idcliente,
                'nombre': cliente_orm.nombre,
                'email': cliente_orm.email,
                'telefono': cliente_orm.telefono,
                'direccion': cliente_orm.direccion
            }
            clientes.append(cliente_dict)
        
        return clientes 