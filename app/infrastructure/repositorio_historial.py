from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.domain.models.historial import HistorialFactura


class RepositorioHistorial:
    def __init__(self, db_session: Session):
        self.db = db_session

    def registrar_evento(
        self,
        *,
        tercero: str,
        tipo: str,
        asiento: str,
        estado_nuevo: str,
        estado_anterior: Optional[str] = None,
        motivo: Optional[str] = None,
        nueva_fecha: Optional[str] = None,
        usuario: Optional[str] = None,
    ) -> Dict[str, Any]:
        evento = HistorialFactura(
            tercero=tercero,
            tipo=tipo,
            asiento=str(asiento),
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            motivo=motivo,
            nueva_fecha=nueva_fecha,
            usuario=usuario,
        )
        self.db.add(evento)
        self.db.commit()
        self.db.refresh(evento)
        return self._to_dict(evento)

    def listar(
        self,
        *,
        tercero: Optional[str] = None,
        tipo: Optional[str] = None,
        asiento: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        q = self.db.query(HistorialFactura)
        if tercero:
            q = q.filter(HistorialFactura.tercero == tercero)
        if tipo:
            q = q.filter(HistorialFactura.tipo == tipo)
        if asiento:
            q = q.filter(HistorialFactura.asiento == str(asiento))
        q = q.order_by(desc(HistorialFactura.creado_en)).limit(limit)
        return [self._to_dict(item) for item in q.all()]

    @staticmethod
    def _to_dict(item: HistorialFactura) -> Dict[str, Any]:
        return {
            "id": item.id,
            "tercero": item.tercero,
            "tipo": item.tipo,
            "asiento": item.asiento,
            "estado_anterior": item.estado_anterior,
            "estado_nuevo": item.estado_nuevo,
            "motivo": item.motivo,
            "nueva_fecha": item.nueva_fecha,
            "usuario": item.usuario,
            "creado_en": item.creado_en.isoformat(),
        }

