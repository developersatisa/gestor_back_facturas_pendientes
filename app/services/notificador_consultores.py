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
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
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

    def __init__(self, db_session: Session, repo_facturas=None, repo_clientes=None):
        self.db = db_session
        # Repositorios base (pueden venir inyectados para tests); si no, se crean bajo demanda.
        self.repo_facturas = repo_facturas
        self.repo_clientes = repo_clientes
        self._facturas_db_session = None
        self._clientes_db_session = None

    def notificar_accion(self, accion: AccionFactura) -> bool:
        """
        Intenta enviar la notificación de una acción.
        Retorna True si se envió correctamente, False en caso contrario.
        
        Prioridad para obtener el destinatario:
        1. Campo `destinatario` de la acción (si existe)
        2. Email del consultor desde `consultor_id` (si existe)
        3. Consultor asignado al cliente (fallback)
        """
        destinatario_email: Optional[str] = None
        consultor: Optional[DatosConsultor] = None
        
        # Prioridad 1: Usar el destinatario ya establecido en la acción
        if accion.destinatario and accion.destinatario.strip():
            destinatario_email = accion.destinatario.strip()
            # Si hay consultor_id, obtener el consultor para construir el mensaje
            if accion.consultor_id:
                consultor_entidad = self.db.get(Consultor, accion.consultor_id)
                if consultor_entidad:
                    consultor = DatosConsultor(entidad=consultor_entidad, asignacion=None)
        
        # Prioridad 2: Si no hay destinatario pero hay consultor_id, obtener su email
        if not destinatario_email and accion.consultor_id:
            consultor_entidad = self.db.get(Consultor, accion.consultor_id)
            if consultor_entidad and consultor_entidad.email:
                destinatario_email = consultor_entidad.email.strip()
                consultor = DatosConsultor(entidad=consultor_entidad, asignacion=None)
        
        # Prioridad 3: Resolver consultor desde la asignación del cliente
        if not consultor or not consultor.entidad:
            consultor = self._resolver_consultor(accion)
            if consultor and consultor.entidad and consultor.entidad.email:
                if not destinatario_email:
                    destinatario_email = consultor.entidad.email.strip()
                if accion.consultor_id is None:
                    accion.consultor_id = consultor.entidad.id
        
        if not consultor or not consultor.entidad:
            return False
        
        if not destinatario_email:
            logger.warning("El consultor %s no tiene email configurado; no se puede enviar la notificacion de la accion %s", consultor.entidad.nombre, accion.id)
            return False

        # Enviar solo por email; 'accion_tipo' se incluye como instrucción en el mensaje
        subject, cuerpo = self._construir_mensaje(accion, consultor)
        accion.consultor_id = consultor.entidad.id
        
        enviado = self._intentar_email([destinatario_email], subject, cuerpo)
        if enviado:
            accion.destinatario = destinatario_email
            return True
        else:
            logger.warning("No se pudo enviar la notificacion por email para la accion %s", accion.id)
            return False

    def _intentar_email(self, destinatarios: Sequence[Optional[str]], subject: str, cuerpo: str) -> bool:
        correos = [d.strip() for d in destinatarios if d and d.strip()]
        if not correos:
            return False

        host = settings.get_notifier_smtp_host()
        if not host:
            return False

        remitente = settings.get_notifier_smtp_from()
        if not remitente:
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
        
        # Obtener nombre del cliente
        nombre_cliente = self._obtener_nombre_cliente(accion)
        
        # Obtener nombre de factura (ID de factura como SE0025001972)
        nombre_factura = self._obtener_nombre_factura(accion)
        referencia = nombre_factura or f"{accion.tipo or ''}-{accion.asiento or ''}".strip("-")
        
        aviso = self._formatear_datetime(accion.aviso)
        creado = self._formatear_datetime(accion.creado_en)

        # Construir texto del cliente: "Nombre del cliente (ID interno)"
        texto_cliente = nombre_cliente
        if cliente_id:
            texto_cliente = f"{nombre_cliente} ({cliente_id})" if nombre_cliente else f"Cliente {cliente_id}"
        elif accion.tercero:
            texto_cliente = nombre_cliente if nombre_cliente else f"Cliente {accion.tercero}"

        subject = f"[Gestion Facturas] Accion ({accion.accion_tipo or 'N/A'}) - Cliente {accion.tercero or cliente_id}"

        canal = (accion.accion_tipo or 'N/A').strip()
        portal_url = "https://demoimpagos.atisa.es/dashboard"

        cuerpo = [
            f"Hola {consultor.entidad.nombre or 'consultor'},",
            "",
            f"Se ha registrado una nueva accion.",
            f"- Tipo de accion (canal): {canal.lower()}",
            f"- Cliente: {texto_cliente or 'Desconocido'}",
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

        # Usar CRLF para asegurar saltos de línea consistentes en clientes de correo.
        return subject, "\r\n".join(cuerpo)

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

        # Intentar resolver los nombres de factura una vez para todas las acciones
        self._anotar_nombres_factura(acciones)

        subject = f"[Gestion Facturas] Acciones agrupadas ({canal}) - Cliente {primera.tercero or cliente_id} - {len(acciones)} facturas"

        # Obtener nombre del cliente
        nombre_cliente = self._obtener_nombre_cliente(primera)
        
        # Construir texto del cliente: "Nombre del cliente (ID interno)"
        texto_cliente = nombre_cliente
        if cliente_id:
            texto_cliente = f"{nombre_cliente} ({cliente_id})" if nombre_cliente else f"Cliente {cliente_id}"
        elif primera.tercero:
            texto_cliente = nombre_cliente if nombre_cliente else f"Cliente {primera.tercero}"

        cuerpo = [
            f"Hola {consultor.entidad.nombre or 'consultor'},",
            "",
            f"Se han registrado {len(acciones)} acciones agrupadas para el mismo seguimiento.",
            "",
            "═══════════════════════════════════════════════════════════",
            "📋 INFORMACIÓN GENERAL DEL SEGUIMIENTO",
            "═══════════════════════════════════════════════════════════",
        ]

        info_lines = [
            f"Tipo de acción (canal): {canal.lower()}",
            f"Cliente: {texto_cliente or 'Desconocido'}",
            f"Descripción común: {primera.descripcion or 'Sin descripción'}",
            f"Fecha de aviso: {aviso}",
            f"Registrado por: {primera.usuario or 'Sistema'} el {creado}",
        ]
        for linea in info_lines:
            cuerpo.append(linea)
            cuerpo.append("")  # línea en blanco para forzar salto incluso en clientes que reflow

        cuerpo.extend([
            "═══════════════════════════════════════════════════════════",
            f"📄 FACTURAS INCLUIDAS ({len(acciones)} facturas)",
            "═══════════════════════════════════════════════════════════",
        ])

        # Listar todas las facturas de forma clara
        for idx, accion in enumerate(acciones, 1):
            # Obtener nombre de factura (ID de factura como SE0025001972)
            nombre_factura = self._obtener_nombre_factura(accion)
            referencia = nombre_factura or f"{accion.tipo or ''}-{accion.asiento or ''}".strip("-")
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

        # Usar CRLF para asegurar saltos de línea consistentes en clientes de correo.
        return subject, "\r\n".join(cuerpo)

    def _obtener_nombre_cliente(self, accion: AccionFactura) -> Optional[str]:
        """Obtiene el nombre del cliente desde la base de datos"""
        try:
            repo_clientes = self._get_repo_clientes()
            if not repo_clientes:
                return None

            # Intentar obtener el cliente usando tercero sin ceros (formato en BD)
            tercero_sin_ceros = str(int(accion.tercero)) if accion.tercero and accion.tercero.isdigit() else accion.tercero
            datos_cliente = repo_clientes.obtener_cliente(tercero_sin_ceros)
            if datos_cliente:
                return datos_cliente.get('razsoc') or None
        except Exception as e:
            pass
        
        return None

    def _obtener_nombre_factura(self, accion: AccionFactura) -> Optional[str]:
        """Obtiene el nombre de factura (ID de factura completo como AC0025007959) desde la base de datos."""
        # 1) Usar cualquier dato ya resuelto previamente (p.ej. al filtrar pendientes)
        try:
            nombre_cache = getattr(accion, "_nombre_factura_resuelta", None) or getattr(accion, "nombre_factura", None)
            if nombre_cache:
                return str(nombre_cache).strip()
        except Exception:
            pass

        # 2) Consultar en X3 usando el repositorio de facturas real
        try:
            repo_facturas = self._get_repo_facturas()
            if not repo_facturas:
                return None
            
            tercero = (accion.tercero or "").strip()
            if not tercero:
                return None
            
            tipo_objetivo = (accion.tipo or "").strip()
            asiento_objetivo = str(accion.asiento or "").strip()
            
            if not tipo_objetivo or not asiento_objetivo:
                return None
            
            factura_detalle = repo_facturas.obtener_factura_especifica(
                tercero=tercero,
                tipo=tipo_objetivo,
                asiento=asiento_objetivo,
            )
            
            if factura_detalle:
                nombre_factura = factura_detalle.get("nombre_factura")
                if nombre_factura:
                    return str(nombre_factura).strip()
            
            # Intentar busqueda alternativa: buscar en todas las facturas del cliente
            try:
                facturas_cliente = repo_facturas.obtener_facturas(tercero=tercero)
                for factura in facturas_cliente:
                    if (str(factura.get("tipo", "")).strip() == tipo_objetivo and 
                        str(factura.get("asiento", "")).strip() == asiento_objetivo):
                        nombre_alt = factura.get("nombre_factura")
                        if nombre_alt:
                            return str(nombre_alt).strip()
            except Exception:
                pass
        except Exception:
            pass
        
        return None

    def _get_repo_facturas(self) -> Optional[RepositorioFacturas]:
        """Obtiene un repositorio de facturas usando la base de datos real de X3."""
        try:
            if self.repo_facturas:
                return self.repo_facturas
            from app.config.database import FacturasSessionLocal
            self._facturas_db_session = FacturasSessionLocal()
            self.repo_facturas = RepositorioFacturas(self._facturas_db_session)
            return self.repo_facturas
        except Exception:
            return None

    def _get_repo_clientes(self) -> Optional[RepositorioClientes]:
        """Obtiene un repositorio de clientes usando la base de datos de clientes."""
        try:
            if self.repo_clientes:
                return self.repo_clientes
            from app.config.database import ClientesSessionLocal
            self._clientes_db_session = ClientesSessionLocal()
            self.repo_clientes = RepositorioClientes(self._clientes_db_session)
            return self.repo_clientes
        except Exception:
            return None

    def __del__(self):
        """Cierra las sesiones auxiliares creadas bajo demanda."""
        for ses in (self._facturas_db_session, self._clientes_db_session):
            try:
                if ses:
                    ses.close()
            except Exception:
                pass

    def _anotar_nombres_factura(self, acciones: Sequence[AccionFactura]) -> None:
        """
        Intenta resolver y cachear el nombre de factura para todas las acciones usando una sola consulta al
        repositorio (cuando es posible).
        """
        if not acciones:
            return

        repo_facturas = self._get_repo_facturas()
        if not repo_facturas:
            return

        tercero = (acciones[0].tercero or "").strip()
        facturas_cliente = None
        try:
            facturas_cliente = repo_facturas.obtener_facturas(tercero=tercero)
        except Exception:
            facturas_cliente = None

        for accion in acciones:
            if getattr(accion, "_nombre_factura_resuelta", None) or getattr(accion, "nombre_factura", None):
                continue

            tipo_obj = (accion.tipo or "").strip()
            asiento_obj = str(accion.asiento or "").strip()
            nombre_encontrado = None

            if facturas_cliente:
                for factura in facturas_cliente:
                    if (str(factura.get("tipo", "")).strip() == tipo_obj and
                        str(factura.get("asiento", "")).strip() == asiento_obj):
                        nombre_alt = factura.get("nombre_factura")
                        if nombre_alt:
                            nombre_encontrado = str(nombre_alt).strip()
                        break

            if not nombre_encontrado:
                try:
                    detalle = repo_facturas.obtener_factura_especifica(
                        tercero=tercero,
                        tipo=tipo_obj,
                        asiento=asiento_obj,
                    )
                    if detalle and detalle.get("nombre_factura"):
                        nombre_encontrado = str(detalle.get("nombre_factura")).strip()
                except Exception:
                    pass

            if nombre_encontrado:
                try:
                    setattr(accion, "_nombre_factura_resuelta", nombre_encontrado)
                except Exception:
                    pass

    @staticmethod
    def _formatear_datetime(valor: Optional[datetime]) -> str:
        if not valor:
            return "No indicado"
        try:
            return valor.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(valor)

    
