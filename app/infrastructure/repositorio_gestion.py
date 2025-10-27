from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import func, select, update, delete, text
from sqlalchemy.orm import Session

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
            .order_by(ClienteConsultor.creado_en.desc(), ClienteConsultor.id.desc())
            .limit(1)
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
        # Crear siempre un nuevo registro para mantener histórico
        ultimo_registro = (
            self.db.execute(
                select(ClienteConsultor)
                .where(ClienteConsultor.idcliente == idcliente)
                .order_by(ClienteConsultor.creado_en.desc(), ClienteConsultor.id.desc())
                .limit(1)
            )
            .scalar_one_or_none()
        )
        if ultimo_registro and ultimo_registro.consultor_id == consultor_id:
            # Ya se encuentra asignado al mismo consultor; evitar duplicar registros
            return self.obtener_asignacion(idcliente) or {
                "idcliente": idcliente,
                "consultor_id": consultor_id,
            }

        self._crear_cliente_consultor(idcliente=idcliente, consultor_id=consultor_id)
        self.db.commit()
        return self.obtener_asignacion(idcliente) or {"idcliente": idcliente, "consultor_id": consultor_id}

    def desasignar_consultor(self, idcliente: int) -> bool:
        stmt = delete(ClienteConsultor).where(ClienteConsultor.idcliente == idcliente)
        res = self.db.execute(stmt)
        self.db.commit()
        return res.rowcount > 0

    def listar_asignaciones(self) -> List[Dict[str, Any]]:
        subquery = (
            select(
                ClienteConsultor.idcliente,
                func.max(ClienteConsultor.id).label("max_id"),
            )
            .group_by(ClienteConsultor.idcliente)
            .subquery()
        )
        stmt = (
            select(ClienteConsultor, Consultor)
            .join(
                subquery,
                (ClienteConsultor.idcliente == subquery.c.idcliente)
                & (ClienteConsultor.id == subquery.c.max_id),
            )
            .join(Consultor, Consultor.id == ClienteConsultor.consultor_id)
        )
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

    def _crear_cliente_consultor(self, *, idcliente: int, consultor_id: int) -> ClienteConsultor:
        """Crea un registro calculando el siguiente ID valido cuando la tabla no usa IDENTITY."""
        next_id = self._obtener_siguiente_id_cliente_consultor()
        entity = ClienteConsultor(
            id=next_id,
            idcliente=idcliente,
            consultor_id=consultor_id,
            creado_en=datetime.utcnow(),
        )
        self.db.add(entity)
        # flush para reservar el ID dentro de la transaccion actual
        self.db.flush()
        return entity

    def _obtener_siguiente_id_cliente_consultor(self) -> int:
        tabla = ClienteConsultor.__table__
        nombre_completo = tabla.fullname if tabla.fullname else tabla.name
        dialecto = getattr(getattr(self.db, "bind", None), "dialect", None)
        if dialecto and dialecto.name == "mssql":
            consulta = text(
                f"SELECT ISNULL(MAX(id), 0) + 1 AS siguiente_id FROM {nombre_completo} WITH (UPDLOCK, HOLDLOCK)"
            )
            resultado = self.db.execute(consulta)
            siguiente_id = resultado.scalar_one()
        else:
            stmt = select(func.coalesce(func.max(ClienteConsultor.id), 0) + 1)
            resultado = self.db.execute(stmt)
            siguiente_id = resultado.scalar_one()
        if not isinstance(siguiente_id, int):
            siguiente_id = int(siguiente_id or 1)
        return max(siguiente_id, 1)

    # Historial de pago (tabla externa opcional, similar a gestion): dbo.facturas_cambio_pago
    # Estructura: factura_id (NVARCHAR), fecha_cambio (DATE), monto_pagado (DECIMAL, opcional), idcliente (NVARCHAR, opcional)
    def obtener_historial_pago_por_id(self, factura_id: str) -> Optional[Dict[str, Any]]:
        try:
            params: Dict[str, Any] = {"factura_id": str(factura_id)}
            where = "WHERE factura_id = :factura_id"
            # Resolver nombre de tabla según dialecto (MSSQL usa dbo., otros no)
            try:
                dialect = self.db.bind.dialect.name if hasattr(self.db, 'bind') else 'mssql'
            except Exception:
                dialect = 'mssql'
            table_name = 'dbo.facturas_cambio_pago' if dialect == 'mssql' else 'facturas_cambio_pago'
            top_clause = 'TOP 1 ' if dialect == 'mssql' else ''
            order_clause = 'ORDER BY fecha_cambio DESC'
            sql = text(
                f"SELECT {top_clause} factura_id, fecha_cambio, monto_pagado, idcliente FROM {table_name} {where} {order_clause}"
            )
            row = self.db.execute(sql, params).mappings().first()
            if not row:
                return None
            return {
                "factura_id": row.get("factura_id"),
                "fecha_cambio": row.get("fecha_cambio"),
                "monto_pagado": float(row.get("monto_pagado")) if row.get("monto_pagado") is not None else None,
                "idcliente": row.get("idcliente"),
                "creado_en": row.get("creado_en"),
            }
        except Exception:
            # Si la tabla no existe o hay error, devolver None para no romper el flujo
            return None

    # Compatibilidad: construir factura_id como "{tipo}-{asiento}" y consultar
    def obtener_historial_pago(self, *, tipo: str, asiento: str, tercero: Optional[str] = None, sociedad: Optional[str] = None) -> Optional[Dict[str, Any]]:
        factura_id = f"{str(tipo)}-{str(asiento)}"
        return self.obtener_historial_pago_por_id(factura_id)
