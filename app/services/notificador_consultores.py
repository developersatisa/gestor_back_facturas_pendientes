import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.models.gestion import AccionFactura, ClienteConsultor, Consultor
logger = logging.getLogger("notificaciones.consultores")


@dataclass
class DatosConsultor:
    entidad: Consultor
    asignacion: Optional[ClienteConsultor]


class NotificadorConsultores:
    """
    Gestiona el envio de notificaciones a los consultores cuando se registra una accion.

    Canal soportado:
      - Email (SMTP configurable mediante variables de entorno).
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        pass

    def notificar_accion(self, accion: AccionFactura) -> None:
        consultor = self._resolver_consultor(accion)
        if not consultor or not consultor.entidad:
            logger.info("Accion %s registrada sin consultor asignado; no se envia notificacion", accion.id)
            return

        # Enviar solo por email; 'accion_tipo' se incluye como instrucción en el mensaje
        subject, cuerpo = self._construir_mensaje(accion, consultor)
        accion.consultor_id = consultor.entidad.id
        destinatario_email: Optional[str] = (consultor.entidad.email or "").strip() or None

        if destinatario_email:
            enviado = self._intentar_email([destinatario_email], subject, cuerpo)
            if enviado:
                accion.destinatario = destinatario_email
            else:
                logger.warning("No se pudo enviar la notificacion por email para la accion %s", accion.id)
        else:
            logger.warning("El consultor %s no tiene email configurado; no se puede enviar la notificacion de la accion %s", consultor.entidad.nombre, accion.id)

    def _intentar_email(self, destinatarios: Sequence[Optional[str]], subject: str, cuerpo: str) -> bool:
        correos = [d.strip() for d in destinatarios if d and d.strip()]
        if not correos:
            logger.debug("Notificacion por email omitida: destinatarios vacios")
            return False

        host = settings.get_notifier_smtp_host()
        if not host:
            logger.debug("Notificacion por email omitida: NOTIFIER_SMTP_HOST no definido")
            return False

        remitente = settings.get_notifier_smtp_from()
        if not remitente:
            logger.debug("Notificacion por email omitida: remitente no definido")
            return False

        port = settings.get_notifier_smtp_port()
        username = settings.get_notifier_smtp_user()
        password = settings.get_notifier_smtp_password()
        use_starttls = settings.get_notifier_smtp_starttls()

        mensaje = EmailMessage()
        mensaje["Subject"] = subject
        mensaje["From"] = remitente
        mensaje["To"] = ", ".join(correos)
        mensaje.set_content(cuerpo)

        try:
            smtp = smtplib.SMTP(host, port, timeout=15)
            with smtp:
                if use_starttls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                if username:
                    smtp.login(username, password)
                smtp.send_message(mensaje)
            logger.info("Notificacion por email enviada a %s", mensaje["To"])
            return True
        except Exception as exc:
            logger.warning("Error enviando email de notificacion: %s", exc)
            return False

    def _resolver_consultor(self, accion: AccionFactura) -> Optional[DatosConsultor]:
        candidatos = []
        if accion.idcliente is not None:
            candidatos.append(accion.idcliente)
        if accion.tercero:
            try:
                candidatos.append(int(str(accion.tercero)))
            except (TypeError, ValueError):
                pass

        for idcliente in candidatos:
            stmt = (
                select(ClienteConsultor)
                .where(ClienteConsultor.idcliente == idcliente)
                .order_by(ClienteConsultor.creado_en.desc(), ClienteConsultor.id.desc())
                .limit(1)
            )
            asignacion = self.db.execute(stmt).scalars().first()
            if asignacion:
                consultor = self.db.get(Consultor, asignacion.consultor_id)
                if consultor:
                    return DatosConsultor(entidad=consultor, asignacion=asignacion)
        return None

    def _construir_mensaje(
        self,
        accion: AccionFactura,
        consultor: DatosConsultor,
    ) -> tuple[str, str]:
        cliente_id = consultor.asignacion.idcliente if consultor.asignacion else accion.idcliente
        referencia = f"{accion.tipo or ''}-{accion.asiento or ''}".strip("-")
        aviso = self._formatear_datetime(accion.aviso)
        creado = self._formatear_datetime(accion.creado_en)

        subject = f"[Gestion Facturas] Accion ({accion.accion_tipo or 'N/A'}) - Cliente {accion.tercero or cliente_id}"

        canal = (accion.accion_tipo or 'N/A').strip()
        portal_url = "https://demoimpagos.atisa.es/dashboard"

        cuerpo = [
            f"Hola {consultor.entidad.nombre or 'consultor'},",
            "",
            f"Se ha registrado una nueva accion.",
            f"- Tipo de accion (canal): {canal.lower()}",
            f"- Cliente (tercero): {accion.tercero or 'Desconocido'}",
            f"- ID Cliente interno: {cliente_id or 'N/D'}",
            f"- Referencia: {referencia or 'N/D'}",
            f"- Descripcion: {accion.descripcion or 'Sin descripcion'}",
            f"- Fecha de aviso: {aviso}",
            f"- Registrada por: {accion.usuario or 'Sistema'} el {creado}",
        ]

        if consultor.entidad.email:
            cuerpo.append(f"- Email del consultor: {consultor.entidad.email}")

        cuerpo.extend([
            "",
            f"Accede al portal para gestionar el recordatorio: {portal_url}",
            f"Canal seleccionado: {canal.upper()}",
            "",
            "Gracias,",
            "Sistema de Gestion de Facturas Pendientes",
        ])

        return subject, "\n".join(cuerpo)

    def notificar_acciones_agrupadas(self, acciones: Sequence[AccionFactura]) -> bool:
        """
        Notifica múltiples acciones agrupadas (del mismo seguimiento) en un solo correo.
        Todas las acciones deben tener el mismo consultor_id y seguimiento_id.
        """
        if not acciones:
            return False
        
        # Verificar que todas las acciones tengan el mismo consultor y seguimiento
        primera = acciones[0]
        consultor = self._resolver_consultor(primera)
        if not consultor or not consultor.entidad:
            logger.info("Acciones agrupadas sin consultor asignado; no se envia notificacion")
            return False
        
        destinatario_email: Optional[str] = (consultor.entidad.email or "").strip() or None
        if not destinatario_email:
            logger.warning("El consultor %s no tiene email configurado; no se puede enviar la notificacion", consultor.entidad.nombre)
            return False

        # Construir mensaje agrupado
        subject, cuerpo = self._construir_mensaje_agrupado(acciones, consultor)
        enviado = self._intentar_email([destinatario_email], subject, cuerpo)
        
        if enviado:
            # Marcar todas las acciones como enviadas
            for accion in acciones:
                accion.destinatario = destinatario_email
                accion.enviada_en = datetime.utcnow()
                accion.envio_estado = "enviada"
            logger.info("Notificacion agrupada enviada para %d acciones del seguimiento %s", len(acciones), primera.seguimiento_id)
        else:
            for accion in acciones:
                accion.envio_estado = "fallo"
            logger.warning("No se pudo enviar la notificacion agrupada para %d acciones", len(acciones))
        
        return enviado

    def _construir_mensaje_agrupado(
        self,
        acciones: Sequence[AccionFactura],
        consultor: DatosConsultor,
    ) -> tuple[str, str]:
        """Construye un mensaje agrupado para múltiples acciones del mismo seguimiento."""
        primera = acciones[0]
        cliente_id = consultor.asignacion.idcliente if consultor.asignacion else primera.idcliente
        canal = (primera.accion_tipo or 'N/A').strip()
        portal_url = "https://demoimpagos.atisa.es/dashboard"
        aviso = self._formatear_datetime(primera.aviso)
        creado = self._formatear_datetime(primera.creado_en)

        subject = f"[Gestion Facturas] Acciones agrupadas ({canal}) - Cliente {primera.tercero or cliente_id} - {len(acciones)} facturas"

        cuerpo = [
            f"Hola {consultor.entidad.nombre or 'consultor'},",
            "",
            f"Se han registrado {len(acciones)} acciones agrupadas para el mismo seguimiento.",
            "",
            "═══════════════════════════════════════════════════════════",
            "📋 INFORMACIÓN GENERAL DEL SEGUIMIENTO",
            "═══════════════════════════════════════════════════════════",
            f"Tipo de acción (canal): {canal.lower()}",
            f"Cliente (tercero): {primera.tercero or 'Desconocido'}",
            f"ID Cliente interno: {cliente_id or 'N/D'}",
            f"Descripción común: {primera.descripcion or 'Sin descripción'}",
            f"Fecha de aviso: {aviso}",
            f"Registrado por: {primera.usuario or 'Sistema'} el {creado}",
            "",
            "═══════════════════════════════════════════════════════════",
            f"📄 FACTURAS INCLUIDAS ({len(acciones)} facturas)",
            "═══════════════════════════════════════════════════════════",
        ]

        # Listar todas las facturas de forma clara
        for idx, accion in enumerate(acciones, 1):
            referencia = f"{accion.tipo or ''}-{accion.asiento or ''}".strip("-")
            cuerpo.append(f"{idx}. Referencia: {referencia or 'N/D'}")

        cuerpo.extend([
            "",
            "═══════════════════════════════════════════════════════════",
            "",
            f"🔗 Accede al portal para gestionar el recordatorio: {portal_url}",
            f"📞 Canal seleccionado: {canal.upper()}",
            "",
            "Gracias,",
            "Sistema de Gestion de Facturas Pendientes",
        ])

        return subject, "\n".join(cuerpo)

    @staticmethod
    def _formatear_datetime(valor: Optional[datetime]) -> str:
        if not valor:
            return "No indicado"
        try:
            return valor.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(valor)

    
