from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete
from app.domain.models.gestion import Consultor, ClienteConsultor


class RepositorioGestion:
    def __init__(self, db_session: Session):
        self.db = db_session

    # Consultores
    def listar_consultores(self, solo_activos: bool = False) -> List[Dict[str, Any]]:
        stmt = select(Consultor)
        if solo_activos:
            stmt = stmt.where(Consultor.estado == 'activo')
        rows = self.db.execute(stmt).scalars().all()
        return [self._consultor_to_dict(c) for c in rows]

    def crear_consultor(self, nombre: str, estado: str = 'activo') -> Dict[str, Any]:
        c = Consultor(nombre=nombre, estado=estado)
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        return self._consultor_to_dict(c)

    def actualizar_consultor(self, consultor_id: int, **fields) -> Optional[Dict[str, Any]]:
        stmt = (
            update(Consultor)
            .where(Consultor.id == consultor_id)
            .values(**fields)
            .execution_options(synchronize_session="fetch")
        )
        res = self.db.execute(stmt)
        if res.rowcount:
            self.db.commit()
            return self.obtener_consultor(consultor_id)
        return None

    def obtener_consultor(self, consultor_id: int) -> Optional[Dict[str, Any]]:
        c = self.db.get(Consultor, consultor_id)
        return self._consultor_to_dict(c) if c else None

    def eliminar_consultor(self, consultor_id: int) -> bool:
        stmt = delete(Consultor).where(Consultor.id == consultor_id)
        res = self.db.execute(stmt)
        self.db.commit()
        return res.rowcount > 0

    # Asignaciones
    def obtener_asignacion(self, idcliente: int) -> Optional[Dict[str, Any]]:
        stmt = (
            select(ClienteConsultor, Consultor)
            .join(Consultor, Consultor.id == ClienteConsultor.consultor_id)
            .where(ClienteConsultor.idcliente == idcliente)
        )
        row = self.db.execute(stmt).first()
        if not row:
            return None
        cc, c = row
        return {
            "idcliente": cc.idcliente,
            "consultor_id": c.id,
            "consultor_nombre": c.nombre,
            "consultor_estado": c.estado,
        }

    def asignar_consultor(self, idcliente: int, consultor_id: int) -> Dict[str, Any]:
        # upsert: si existe, actualiza; si no, crea
        current = self.db.execute(select(ClienteConsultor).where(ClienteConsultor.idcliente == idcliente)).scalar_one_or_none()
        if current:
            current.consultor_id = consultor_id
        else:
            current = ClienteConsultor(idcliente=idcliente, consultor_id=consultor_id)
            self.db.add(current)
        self.db.commit()
        return self.obtener_asignacion(idcliente) or {"idcliente": idcliente, "consultor_id": consultor_id}

    def desasignar_consultor(self, idcliente: int) -> bool:
        stmt = delete(ClienteConsultor).where(ClienteConsultor.idcliente == idcliente)
        res = self.db.execute(stmt)
        self.db.commit()
        return res.rowcount > 0

    def listar_asignaciones(self) -> List[Dict[str, Any]]:
        stmt = select(ClienteConsultor, Consultor).join(Consultor, Consultor.id == ClienteConsultor.consultor_id)
        rows = self.db.execute(stmt).all()
        out: List[Dict[str, Any]] = []
        for cc, c in rows:
            out.append({
                "idcliente": cc.idcliente,
                "consultor_id": c.id,
                "consultor_nombre": c.nombre,
                "consultor_estado": c.estado,
            })
        return out

    @staticmethod
    def _consultor_to_dict(c: Consultor) -> Dict[str, Any]:
        return {
            "id": c.id,
            "nombre": c.nombre,
            "estado": c.estado,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
        }
