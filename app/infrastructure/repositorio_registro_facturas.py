from typing import List, Optional, Dict, Any, Iterable, Set
from datetime import datetime, date
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
    def _obtener_email_consultor(self, consultor_id: Optional[int], idcliente: Optional[int] = None, tercero: Optional[str] = None) -> tuple[Optional[int], Optional[str]]:
        """
        Obtiene el ID del consultor y su email.
        
        Si se proporciona consultor_id, lo usa directamente.
        Si no, busca el consultor asignado al cliente.
        
        Returns:
            tuple: (consultor_id, email) o (None, None) si no se encuentra
        """
        from app.domain.models.gestion import ClienteConsultor, Consultor
        
        if consultor_id:
            consultor = self.db.get(Consultor, consultor_id)
            if consultor and consultor.email:
                return consultor_id, consultor.email.strip() or None
            return consultor_id, None
        
        # Buscar consultor asignado al cliente
        candidatos = []
        if idcliente is not None:
            candidatos.append(idcliente)
        if tercero:
            try:
                candidatos.append(int(str(tercero)))
            except (TypeError, ValueError):
                pass

        for idcliente_candidato in candidatos:
            stmt = (
                select(ClienteConsultor)
                .where(ClienteConsultor.idcliente == idcliente_candidato)
                .order_by(ClienteConsultor.creado_en.desc(), ClienteConsultor.id.desc())
                .limit(1)
            )
            asignacion = self.db.execute(stmt).scalars().first()
            if asignacion:
                consultor = self.db.get(Consultor, asignacion.consultor_id)
                email = consultor.email.strip() if (consultor and consultor.email) else None
                return asignacion.consultor_id, email
        
        return None, None

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

        consultor_final_id, destinatario_email = self._obtener_email_consultor(consultor_id, idcliente, tercero)

        item = AccionFactura(
            idcliente=idcliente,
            tercero=tercero,
            tipo=tipo,
            asiento=str(asiento),
            accion_tipo=accion_tipo,
            descripcion=descripcion,
            aviso=_parse_dt(aviso),
            usuario=usuario,
            consultor_id=consultor_final_id,
            destinatario=destinatario_email,
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
    def _parse_fecha(self, valor: Optional[str]) -> Optional[date]:
        if not valor:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(valor, fmt).date()
            except ValueError:
                continue
        return None

    def listar_pendientes_envio(
        self,
        *,
        fecha_iso: Optional[str] = None,
        fecha_desde_iso: Optional[str] = None,
        estados_excluidos: Optional[Iterable[str]] = None,
    ) -> List[AccionFactura]:
        fecha_limite = self._parse_fecha(fecha_iso) or datetime.utcnow().date()
        fecha_desde = self._parse_fecha(fecha_desde_iso)
        estados_excluidos_set: Set[str] = set(
            estado for estado in (estados_excluidos or ("omitida_pagada", "caducada")) if estado
        )

        stmt = select(AccionFactura).where(
            AccionFactura.aviso.isnot(None),
            AccionFactura.enviada_en.is_(None),
            AccionFactura.accion_tipo.isnot(None),
            AccionFactura.accion_tipo != "",
        )
        rows = self.db.execute(stmt).scalars().all()

        filtradas: List[AccionFactura] = []
        for accion in rows:
            if accion.aviso is None:
                continue
            aviso_fecha = accion.aviso.date()
            if aviso_fecha > fecha_limite:
                continue
            if fecha_desde and aviso_fecha < fecha_desde:
                continue
            if accion.envio_estado and accion.envio_estado in estados_excluidos_set:
                continue
            filtradas.append(accion)
        return filtradas

    def descartar_acciones_anteriores(
        self,
        *,
        fecha_iso: Optional[str],
        estado: str = "caducada",
    ) -> int:
        """
        Marca como procesadas (sin enviar) las acciones con aviso anterior a la fecha indicada.
        """
        fecha_limite = self._parse_fecha(fecha_iso)
        if not fecha_limite:
            return 0

        limite_dt = datetime.combine(fecha_limite, datetime.min.time())

        stmt = select(AccionFactura).where(
            AccionFactura.aviso.isnot(None),
            AccionFactura.enviada_en.is_(None),
            AccionFactura.aviso < limite_dt,
        )
        acciones = self.db.execute(stmt).scalars().all()
        if not acciones:
            return 0

        ahora = datetime.utcnow()
        for accion in acciones:
            accion.envio_estado = estado
            accion.enviada_en = ahora

        self.db.commit()
        return len(acciones)

    def _factura_sigue_pendiente(
        self,
        accion: AccionFactura,
        repo_facturas,
        facturas_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Comprueba si la factura asociada a la acción continúa con saldo pendiente y devuelve su nombre si existe."""
        if repo_facturas is None:
            return True, None

        try:
            tercero = (accion.tercero or "").strip()
            if not tercero:
                return True, None

            cache_key = tercero.lstrip("0") or tercero
            facturas: Optional[List[Dict[str, Any]]] = None

            if facturas_cache is not None:
                if cache_key in facturas_cache:
                    facturas = facturas_cache[cache_key]
                else:
                    facturas = repo_facturas.obtener_facturas(tercero=tercero)
                    facturas_cache[cache_key] = facturas
            else:
                facturas = repo_facturas.obtener_facturas(tercero=tercero)

            tipo_objetivo = (accion.tipo or "").strip()
            asiento_objetivo = str(accion.asiento or "").strip()

            if facturas:
                for factura in facturas:
                    tipo_factura = str(factura.get("tipo") or "").strip()
                    asiento_factura = str(factura.get("asiento") or "").strip()
                    if tipo_factura == tipo_objetivo and asiento_factura == asiento_objetivo:
                        nombre = (
                            factura.get("nombre_factura")
                            or factura.get("nombre")
                            or f"{tipo_factura}-{asiento_factura}"
                        )
                        return True, nombre

            # Si no aparece en la lista de facturas vencidas, comprobar con consulta directa
            factura_detalle = repo_facturas.obtener_factura_especifica(
                tercero=tercero,
                tipo=tipo_objetivo,
                asiento=asiento_objetivo,
            )
            if factura_detalle:
                pendiente = factura_detalle.get("pendiente", 0.0)
                if pendiente is None:
                    pendiente = 0.0
                if float(pendiente) > 0:
                    nombre = (
                        factura_detalle.get("nombre_factura")
                        or f"{factura_detalle.get('tipo', 'N/D')}-{factura_detalle.get('asiento', 'N/D')}"
                    )
                    return True, nombre

            return False, None
        except Exception:
            # Si no podemos comprobarlo (p.ej. sin acceso a X3), preferimos enviar.
            return True, None

    def enviar_pendientes(
        self,
        *,
        fecha_iso: Optional[str] = None,
        fecha_desde_iso: Optional[str] = None,
        repo_facturas=None,
        simular: bool = False,
        solo_filtrar: bool = False,
        mostrar_omitidas: bool = False,
    ) -> int:
        pendientes = self.listar_pendientes_envio(
            fecha_iso=fecha_iso,
            fecha_desde_iso=fecha_desde_iso,
            estados_excluidos=("omitida_pagada", "caducada", "omitida_sin_destinatario"),
        )
        if not pendientes:
            return 0
        
        # Filtrar facturas ya cobradas
        pendientes_filtrados: List[AccionFactura] = []
        facturas_cache: Dict[str, List[Dict[str, Any]]] = {}
        omitidas: List[Dict[str, Any]] = []
        for accion in pendientes:
            sigue_pendiente, nombre_factura = self._factura_sigue_pendiente(
                accion,
                repo_facturas,
                facturas_cache=facturas_cache,
            )
            if sigue_pendiente:
                if nombre_factura:
                    setattr(accion, "_nombre_factura_resuelta", nombre_factura)
                pendientes_filtrados.append(accion)
            else:
                accion.envio_estado = "omitida_pagada"
                if mostrar_omitidas:
                    omitidas.append(
                        {
                            "id": accion.id,
                            "idcliente": accion.idcliente,
                            "tercero": accion.tercero,
                            "factura": f"{accion.tipo or 'N/D'}-{accion.asiento or 'N/D'}",
                            "aviso": accion.aviso.isoformat() if accion.aviso else None,
                        }
                    )
        pendientes = pendientes_filtrados

        if not pendientes:
            if not simular:
                self.db.commit()
            if mostrar_omitidas and omitidas:
                for info in omitidas:
                    logger.info(
                        "ACCION OMITIDA (factura pagada) -> id=%s | idcliente=%s | tercero=%s | factura=%s | aviso=%s",
                        info["id"],
                        info["idcliente"],
                        info["tercero"],
                        info["factura"],
                        info["aviso"],
                    )
            return 0

        if solo_filtrar:
            if mostrar_omitidas and omitidas:
                for info in omitidas:
                    logger.info(
                        "ACCION OMITIDA (factura pagada) -> id=%s | idcliente=%s | tercero=%s | factura=%s | aviso=%s",
                        info["id"],
                        info["idcliente"],
                        info["tercero"],
                        info["factura"],
                        info["aviso"],
                    )
            resultado = []
            for accion in pendientes:
                resultado.append(
                    {
                        "id": accion.id,
                        "idcliente": accion.idcliente,
                        "tercero": accion.tercero,
                        "tipo": accion.tipo,
                        "asiento": accion.asiento,
                        "aviso": accion.aviso.isoformat() if accion.aviso else None,
                        "estado": accion.envio_estado,
                        "factura_nombre": getattr(accion, "_nombre_factura_resuelta", None)
                        or getattr(accion, "nombre_factura", None)
                        or f"{accion.tipo or 'N/D'}-{accion.asiento or 'N/D'}",
                    }
                )
            return resultado

        if simular:
            for accion in pendientes:
                logger.info(
                    "SIMULACION envío -> acción %s | tercero=%s | factura=%s",
                    accion.id,
                    accion.tercero or "N/D",
                    getattr(accion, "_nombre_factura_resuelta", None)
                    or getattr(accion, "nombre_factura", None)
                    or f"{accion.tipo or 'N/D'}-{accion.asiento or 'N/D'}",
                )
            return len(pendientes)
        
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
                enviado = notificador.notificar_accion(item)
                if enviado:
                    item.enviada_en = datetime.utcnow()
                    item.envio_estado = "enviada"
                    enviados += 1
                else:
                    # No se pudo enviar (sin destinatario, sin consultor, error de email, etc.)
                    item.envio_estado = "omitida_sin_destinatario"
                    logger.info("Accion %s omitida: no se pudo enviar (sin destinatario o consultor)", item.id)
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
        if mostrar_omitidas and omitidas:
            for info in omitidas:
                logger.info(
                    "ACCION OMITIDA (factura pagada) -> id=%s | idcliente=%s | tercero=%s | factura=%s | aviso=%s",
                    info["id"],
                    info["idcliente"],
                    info["tercero"],
                    info["factura"],
                    info["aviso"],
                )
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


