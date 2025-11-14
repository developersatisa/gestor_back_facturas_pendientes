from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import func, select, update, delete, text
from sqlalchemy.orm import Session

from app.domain.models.gestion import Consultor, ClienteConsultor, AccionFactura


class RepositorioGestion:
    def __init__(self, db_session: Session):
        self.db = db_session

    # Consultores
    def listar_consultores(self, solo_activos: bool = False) -> List[Dict[str, Any]]:
        """
        Lista los consultores, excluyendo los eliminados.
        
        Args:
            solo_activos: Si es True, solo muestra consultores con estado 'activo'
        
        Returns:
            Lista de consultores (sin incluir eliminados)
        """
        stmt = select(Consultor).where(Consultor.eliminado == False)
        if solo_activos:
            stmt = stmt.where(Consultor.estado == 'activo')
        rows = self.db.execute(stmt).scalars().all()
        return [self._consultor_to_dict(c) for c in rows]

    def crear_consultor(
        self,
        nombre: str,
        estado: str = 'activo',
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        c = Consultor(
            nombre=nombre,
            estado=estado,
            email=self._normalizar_campo(email),
        )
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        return self._consultor_to_dict(c)

    def actualizar_consultor(self, consultor_id: int, **fields) -> Optional[Dict[str, Any]]:
        cleaned: Dict[str, Any] = {}
        for key, value in fields.items():
            if key in {"email"}:
                if isinstance(value, str):
                    value = value.strip()
                cleaned[key] = value or None
            else:
                cleaned[key] = value
        stmt = (
            update(Consultor)
            .where(Consultor.id == consultor_id)
            .values(**cleaned)
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

    def _obtener_nombre_cliente(self, repo_clientes, idcliente: int) -> Optional[str]:
        """Obtiene el nombre de un cliente desde el repositorio."""
        if not repo_clientes or not idcliente:
            return None
        try:
            cliente_data = repo_clientes.obtener_cliente(str(idcliente))
            return cliente_data.get('razsoc') if cliente_data else None
        except Exception:
            return None

    def _obtener_nombre_factura(self, repo_facturas, accion: AccionFactura) -> Optional[str]:
        """Obtiene el nombre_factura (NUM_0) de una acción desde el repositorio."""
        if not repo_facturas or not accion.tipo or not accion.asiento:
            return None
        try:
            tercero = accion.tercero or (str(accion.idcliente) if accion.idcliente else '')
            factura_data = repo_facturas.obtener_factura_especifica(
                tercero=tercero,
                tipo=accion.tipo,
                asiento=str(accion.asiento)
            )
            return factura_data.get('nombre_factura') if factura_data else None
        except Exception:
            return None

    def _obtener_clientes_con_nombres(self, clientes_ids: List[int], repo_clientes) -> List[Dict[str, Any]]:
        """Obtiene la lista de clientes con sus nombres."""
        if not repo_clientes:
            return [{"idcliente": id, "nombre": f"Cliente {id}"} for id in clientes_ids]
        
        clientes_con_nombres = []
        for idcliente in clientes_ids:
            nombre_cliente = self._obtener_nombre_cliente(repo_clientes, idcliente)
            clientes_con_nombres.append({
                "idcliente": idcliente,
                "nombre": nombre_cliente or f"Cliente {idcliente}"
            })
        return clientes_con_nombres

    def _procesar_acciones_por_cliente(
        self, 
        acciones: List[AccionFactura], 
        repo_clientes, 
        repo_facturas
    ) -> List[Dict[str, Any]]:
        """Procesa y agrupa las acciones por cliente."""
        acciones_por_cliente = {}
        
        for accion in acciones:
            clave = f"{accion.tercero}_{accion.idcliente or 'sin_id'}"
            
            # Inicializar entrada si no existe
            if clave not in acciones_por_cliente:
                nombre_cliente = self._obtener_nombre_cliente(repo_clientes, accion.idcliente)
                acciones_por_cliente[clave] = {
                    "tercero": accion.tercero,
                    "idcliente": accion.idcliente,
                    "nombre_cliente": nombre_cliente,
                    "facturas": set(),
                    "total_acciones": 0
                }
            
            # Obtener nombre de factura o usar fallback
            nombre_factura = self._obtener_nombre_factura(repo_facturas, accion)
            identificador_factura = nombre_factura or f"{accion.tipo}-{accion.asiento}"
            
            acciones_por_cliente[clave]["facturas"].add(identificador_factura)
            acciones_por_cliente[clave]["total_acciones"] += 1
        
        # Convertir a lista ordenada
        return [
            {
                "tercero": datos["tercero"],
                "idcliente": datos["idcliente"],
                "nombre_cliente": datos["nombre_cliente"],
                "facturas": sorted(list(datos["facturas"])),
                "total_acciones": datos["total_acciones"]
            }
            for datos in acciones_por_cliente.values()
        ]

    def obtener_info_eliminacion_consultor(self, consultor_id: int, repo_clientes=None, repo_facturas=None) -> Dict[str, Any]:
        """
        Obtiene información sobre el impacto de eliminar un consultor.
        
        Args:
            consultor_id: ID del consultor
            repo_clientes: Repositorio de clientes opcional para obtener nombres
            repo_facturas: Repositorio de facturas opcional para obtener nombres de facturas
        
        Returns:
            Dict con información sobre clientes asociados y acciones relacionadas
        """
        consultor = self.db.get(Consultor, consultor_id)
        if not consultor:
            return {
                "existe": False,
                "clientes_asociados": [],
                "acciones": [],
                "total_clientes": 0,
                "total_acciones": 0
            }
        
        # Obtener IDs de clientes asociados
        stmt_clientes = select(ClienteConsultor.idcliente).where(
            ClienteConsultor.consultor_id == consultor_id
        ).distinct()
        clientes_ids = [row[0] for row in self.db.execute(stmt_clientes).all()]
        
        # Obtener clientes con nombres
        clientes_con_nombres = self._obtener_clientes_con_nombres(clientes_ids, repo_clientes)
        
        # Obtener acciones relacionadas
        stmt_acciones = (
            select(AccionFactura)
            .where(AccionFactura.consultor_id == consultor_id)
            .order_by(AccionFactura.creado_en.desc())
            .limit(100)
        )
        acciones = self.db.execute(stmt_acciones).scalars().all()
        
        # Procesar y agrupar acciones por cliente
        acciones_resumen = self._procesar_acciones_por_cliente(acciones, repo_clientes, repo_facturas)
        
        return {
            "existe": True,
            "consultor_nombre": consultor.nombre,
            "clientes_asociados": clientes_con_nombres,
            "acciones_resumen": acciones_resumen,
            "total_clientes": len(clientes_ids),
            "total_acciones": len(acciones)
        }

    def eliminar_consultor(self, consultor_id: int) -> bool:
        """
        Elimina un consultor de forma lógica (marcándolo como eliminado) y elimina
        todas sus asociaciones con clientes.
        
        Args:
            consultor_id: ID del consultor a eliminar
        
        Returns:
            True si se eliminó correctamente, False si no se encontró
        """
        # Verificar que el consultor existe y no está ya eliminado
        consultor = self.db.get(Consultor, consultor_id)
        if not consultor or consultor.eliminado == True:
            return False
        
        res = None
        try:
            # 1. Eliminar todas las asociaciones con clientes
            stmt_delete_asignaciones = delete(ClienteConsultor).where(
                ClienteConsultor.consultor_id == consultor_id
            )
            self.db.execute(stmt_delete_asignaciones)
            
            # 2. Marcar el consultor como eliminado (eliminado = True)
            stmt_update = (
                update(Consultor)
                .where(Consultor.id == consultor_id)
                .values(eliminado=True)
                .execution_options(synchronize_session="fetch")
            )
            res = self.db.execute(stmt_update)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise
        
        return res.rowcount > 0 if res else False

    # Asignaciones
    def obtener_asignacion(self, idcliente: int) -> Optional[Dict[str, Any]]:
        stmt = (
            select(ClienteConsultor, Consultor)
            .join(Consultor, Consultor.id == ClienteConsultor.consultor_id)
            .where(
                ClienteConsultor.idcliente == idcliente,
                Consultor.eliminado == False  # Excluir consultores eliminados
            )
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
            "consultor_email": c.email,
        }

    def asignar_consultor(self, idcliente: int, consultor_id: int) -> Dict[str, Any]:
        # Verificar que el consultor existe y no está eliminado
        consultor = self.db.get(Consultor, consultor_id)
        if not consultor:
            raise ValueError(f"Consultor con ID {consultor_id} no encontrado")
        if consultor.eliminado == True:
            raise ValueError(f"No se puede asignar un consultor eliminado (ID: {consultor_id})")
        
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
        # Actualizar acciones existentes para reflejar el nuevo consultor en el campo usuario
        try:
            c = self.db.get(Consultor, consultor_id)
            nuevo_nombre = c.nombre if c else None
            if nuevo_nombre:
                from sqlalchemy import update
                upd = (
                    update(AccionFactura)
                    .where(AccionFactura.idcliente == idcliente)
                    .values(usuario=nuevo_nombre)
                    .execution_options(synchronize_session="fetch")
                )
                self.db.execute(upd)
        except Exception:
            # No bloquear la asignación si falla la actualización de acciones
            pass
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
            .where(Consultor.eliminado == False)  # Excluir consultores eliminados
        )
        rows = self.db.execute(stmt).all()
        out: List[Dict[str, Any]] = []
        for cc, c in rows:
            out.append({
                "idcliente": cc.idcliente,
                "consultor_id": c.id,
                "consultor_nombre": c.nombre,
                "consultor_estado": c.estado,
                "consultor_email": c.email,
            })
        return out

    @staticmethod
    def _consultor_to_dict(c: Consultor) -> Dict[str, Any]:
        return {
            "id": c.id,
            "nombre": c.nombre,
            "estado": c.estado,
            "email": c.email,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
        }

    @staticmethod
    def _normalizar_campo(valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        if isinstance(valor, str):
            limpio = valor.strip()
            return limpio or None
        return str(valor) or None

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
