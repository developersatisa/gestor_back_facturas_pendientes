from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from app.domain.models.gestion import FacturaCambio, AccionFactura

logger = logging.getLogger(__name__)


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
        consultor_id: Optional[int] = None,
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
            consultor_id=consultor_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        # Enviar solo si hay fecha de aviso y es hoy o en el pasado
        try:
            enviar_ahora = False
            if item.aviso is not None:
                hoy = datetime.utcnow().date()
                enviar_ahora = item.aviso.date() <= hoy
            if enviar_ahora:
                from app.services.notificador_consultores import NotificadorConsultores

                notificador = NotificadorConsultores(self.db)
                notificador.notificar_accion(item)
                item.enviada_en = datetime.utcnow()
                item.envio_estado = "enviada"
                self.db.commit()
        except Exception as notify_error:
            logger.warning("No se pudo enviar la notificacion al consultor: %s", notify_error)
            try:
                item.envio_estado = "fallo"
                self.db.commit()
            except Exception:
                pass
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

    def eliminar_accion(self, accion_id: int) -> bool:
        accion = self.db.get(AccionFactura, accion_id)
        if not accion:
            return False
        # Regla: solo se puede borrar si la fecha de aviso es futura (aún no ha llegado ese día)
        # Si no tiene fecha de aviso, se puede borrar siempre
        if accion.aviso is not None:
            hoy = datetime.utcnow().date()
            fecha_aviso = accion.aviso.date()
            # Solo permitir eliminar si la fecha de aviso es FUTURA (mayor que hoy)
            if fecha_aviso <= hoy:
                raise PermissionError(f"La acción no se puede eliminar. La fecha de aviso ({fecha_aviso.strftime('%Y-%m-%d')}) ya ha pasado o es hoy.")
        self.db.delete(accion)
        self.db.commit()
        return True

    # Envío programado de acciones
    def listar_pendientes_envio(self, *, fecha_iso: Optional[str] = None) -> List[AccionFactura]:
        fecha = None
        if fecha_iso:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                try:
                    fecha = datetime.strptime(fecha_iso, fmt).date()
                    break
                except ValueError:
                    continue
        if fecha is None:
            fecha = datetime.utcnow().date()

        stmt = select(AccionFactura).where(
            AccionFactura.aviso.isnot(None),
            AccionFactura.enviada_en.is_(None),
        )
        rows = self.db.execute(stmt).scalars().all()
        return [x for x in rows if x.aviso and x.aviso.date() <= fecha]

    def enviar_pendientes(self, *, fecha_iso: Optional[str] = None) -> int:
        pendientes = self.listar_pendientes_envio(fecha_iso=fecha_iso)
        if not pendientes:
            return 0
        
        from app.services.notificador_consultores import NotificadorConsultores
        notificador = NotificadorConsultores(self.db)
        
        # Separar acciones individuales de acciones agrupadas (con seguimiento_id)
        acciones_individuales = []
        acciones_agrupadas = {}  # { (seguimiento_id, consultor_id): [acciones] }
        
        for item in pendientes:
            if item.seguimiento_id is not None and item.consultor_id is not None:
                # Es una acción agrupada
                key = (item.seguimiento_id, item.consultor_id)
                if key not in acciones_agrupadas:
                    acciones_agrupadas[key] = []
                acciones_agrupadas[key].append(item)
            else:
                # Es una acción individual
                acciones_individuales.append(item)
        
        enviados = 0
        
        # Enviar acciones individuales una por una
        for item in acciones_individuales:
            try:
                notificador.notificar_accion(item)
                item.enviada_en = datetime.utcnow()
                item.envio_estado = "enviada"
                enviados += 1
            except Exception as exc:
                logger.warning("Fallo al enviar accion %s: %s", item.id, exc)
                item.envio_estado = "fallo"
        
        # Enviar acciones agrupadas (un correo por grupo)
        for acciones_grupo in acciones_agrupadas.values():
            try:
                notificador.notificar_acciones_agrupadas(acciones_grupo)
                enviados += len(acciones_grupo)
            except Exception as exc:
                logger.warning("Fallo al enviar acciones agrupadas: %s", exc)
                for item in acciones_grupo:
                    item.envio_estado = "fallo"
        
        self.db.commit()
        return enviados

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

    def listar_proximos_avisos(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtiene los próximos avisos (acciones con fecha de aviso >= hoy), ordenados por fecha ascendente."""
        from datetime import date as date_type
        hoy = datetime.utcnow().date()
        
        stmt = select(AccionFactura).where(
            AccionFactura.aviso.isnot(None),
            AccionFactura.aviso >= datetime.combine(hoy, datetime.min.time())
        ).order_by(AccionFactura.aviso.asc()).limit(limit)
        
        rows = self.db.execute(stmt).scalars().all()
        return [self._accion_to_dict(x) for x in rows]

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
            "consultor_id": x.consultor_id,
            "enviada_en": x.enviada_en.isoformat() if x.enviada_en else None,
            "destinatario": x.destinatario,
            "envio_estado": x.envio_estado,
            "creado_en": x.creado_en.isoformat(),
        }


