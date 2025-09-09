from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from app.domain.models.gestion import FacturaCambio, AccionFactura


class RepositorioRegistroFacturas:
    def __init__(self, db_session: Session):
        self.db = db_session

    # Cambios
    def registrar_cambio(
        self,
        *,
        idcliente: Optional[int] = None,
        tercero: str,
        tipo: str,
        asiento: str,
        numero_anterior: Optional[str] = None,
        numero_nuevo: Optional[str] = None,
        monto_anterior: Optional[float] = None,
        monto_nuevo: Optional[float] = None,
        vencimiento_anterior: Optional[str] = None,
        vencimiento_nuevo: Optional[str] = None,
        motivo: Optional[str] = None,
        usuario: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Normalizar fechas ISO (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)
        def _parse_dt(val: Optional[str]) -> Optional[datetime]:
            if not val:
                return None
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(val, fmt)
                except ValueError:
                    continue
            return None

        item = FacturaCambio(
            idcliente=idcliente,
            tercero=tercero,
            tipo=tipo,
            asiento=str(asiento),
            numero_anterior=numero_anterior,
            numero_nuevo=numero_nuevo,
            monto_anterior=monto_anterior,
            monto_nuevo=monto_nuevo,
            vencimiento_anterior=_parse_dt(vencimiento_anterior),
            vencimiento_nuevo=_parse_dt(vencimiento_nuevo),
            motivo=motivo,
            usuario=usuario,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._cambio_to_dict(item)

    def listar_cambios(self, *, idcliente: Optional[int] = None, tercero: Optional[str] = None, tipo: Optional[str] = None, asiento: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        stmt = select(FacturaCambio)
        if idcliente is not None:
            stmt = stmt.where(FacturaCambio.idcliente == idcliente)
        if tercero:
            stmt = stmt.where(FacturaCambio.tercero == tercero)
        if tipo:
            stmt = stmt.where(FacturaCambio.tipo == tipo)
        if asiento:
            stmt = stmt.where(FacturaCambio.asiento == str(asiento))
        stmt = stmt.order_by(desc(FacturaCambio.creado_en)).limit(limit)
        rows = self.db.execute(stmt).scalars().all()
        return [self._cambio_to_dict(x) for x in rows]

    # Acciones
    def registrar_accion(
        self,
        *,
        idcliente: Optional[int] = None,
        tercero: str,
        tipo: str,
        asiento: str,
        accion_tipo: str,
        descripcion: Optional[str] = None,
        aviso: Optional[str] = None,
        usuario: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _parse_dt(val: Optional[str]) -> Optional[datetime]:
            if not val:
                return None
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(val, fmt)
                except ValueError:
                    continue
            return None

        item = AccionFactura(
            idcliente=idcliente,
            tercero=tercero,
            tipo=tipo,
            asiento=str(asiento),
            accion_tipo=accion_tipo,
            descripcion=descripcion,
            aviso=_parse_dt(aviso),
            usuario=usuario,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._accion_to_dict(item)

    def listar_acciones(self, *, idcliente: Optional[int] = None, tercero: Optional[str] = None, tipo: Optional[str] = None, asiento: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        stmt = select(AccionFactura)
        if idcliente is not None:
            stmt = stmt.where(AccionFactura.idcliente == idcliente)
        if tercero:
            stmt = stmt.where(AccionFactura.tercero == tercero)
        if tipo:
            stmt = stmt.where(AccionFactura.tipo == tipo)
        if asiento:
            stmt = stmt.where(AccionFactura.asiento == str(asiento))
        stmt = stmt.order_by(desc(AccionFactura.creado_en)).limit(limit)
        rows = self.db.execute(stmt).scalars().all()
        return [self._accion_to_dict(x) for x in rows]

    @staticmethod
    def _cambio_to_dict(x: FacturaCambio) -> Dict[str, Any]:
        return {
            "id": x.id,
            "idcliente": x.idcliente,
            "tercero": x.tercero,
            "tipo": x.tipo,
            "asiento": x.asiento,
            "numero_anterior": x.numero_anterior,
            "numero_nuevo": x.numero_nuevo,
            "monto_anterior": float(x.monto_anterior) if x.monto_anterior is not None else None,
            "monto_nuevo": float(x.monto_nuevo) if x.monto_nuevo is not None else None,
            "vencimiento_anterior": x.vencimiento_anterior.isoformat() if x.vencimiento_anterior else None,
            "vencimiento_nuevo": x.vencimiento_nuevo.isoformat() if x.vencimiento_nuevo else None,
            "motivo": x.motivo,
            "usuario": x.usuario,
            "creado_en": x.creado_en.isoformat(),
        }

    @staticmethod
    def _accion_to_dict(x: AccionFactura) -> Dict[str, Any]:
        return {
            "id": x.id,
            "idcliente": x.idcliente,
            "tercero": x.tercero,
            "tipo": x.tipo,
            "asiento": x.asiento,
            "accion_tipo": x.accion_tipo,
            "descripcion": x.descripcion,
            "aviso": x.aviso.isoformat() if x.aviso else None,
            "usuario": x.usuario,
            "creado_en": x.creado_en.isoformat(),
        }
