import html
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
            # Si tenemos destinatario_email, enviar aunque no haya consultor asociado
            if destinatario_email:
                class _ConsultorAnon:
                    id = None
                    nombre = "Consultor"
                    email = destinatario_email
                consultor = DatosConsultor(entidad=_ConsultorAnon(), asignacion=None)
            else:
                return False
        
        if not destinatario_email:
            # Sin email en el consultor elegido, no enviamos (evita usar otros correos por error)
            logger.warning("El consultor %s no tiene email configurado; no se puede enviar la notificacion de la accion %s", consultor.entidad.nombre, accion.id)
            return False

        # Enviar solo por email; 'accion_tipo' se incluye como instrucción en el mensaje
        subject, cuerpo_html, cuerpo_texto = self._construir_mensaje(accion, consultor)
        accion.consultor_id = consultor.entidad.id
        
        enviado = self._intentar_email([destinatario_email], subject, cuerpo_html, cuerpo_texto)
        if enviado:
            accion.destinatario = destinatario_email
            return True
        else:
            logger.warning("No se pudo enviar la notificacion por email para la accion %s", accion.id)
            return False

    def _intentar_email(self, destinatarios: Sequence[Optional[str]], subject: str, cuerpo_html: str, cuerpo_texto: Optional[str] = None) -> bool:
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
        
        # Establecer contenido HTML
        mensaje.set_content(cuerpo_html, subtype='html')
        
        # Si hay versión texto plano, añadirla como alternativa
        if cuerpo_texto:
            mensaje.add_alternative(cuerpo_texto, subtype='plain')

        try:
            smtp = smtplib.SMTP(host, port, timeout=15)
            with smtp:
                if use_starttls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                
                # Intentar autenticación si hay credenciales
                # Si el servidor no soporta autenticación (relay interno), continuar sin auth
                if username and password:
                    try:
                        smtp.login(username, password)
                        logger.debug("Autenticación SMTP exitosa")
                    except smtplib.SMTPNotSupportedError:
                        # El servidor no soporta autenticación (relay interno), continuar sin auth
                        logger.debug("Servidor SMTP no soporta autenticación, enviando sin auth (relay interno)")
                    except smtplib.SMTPAuthenticationError as auth_exc:
                        # Error de credenciales - esto es un error real que debemos reportar
                        logger.warning("Error de autenticación SMTP (credenciales incorrectas): %s", auth_exc)
                        raise  # Re-lanzar para que se capture como error
                    except Exception as auth_exc:
                        # Otro error de autenticación - puede ser que el servidor no lo requiera
                        error_msg = str(auth_exc).lower()
                        if "auth" in error_msg and "not supported" in error_msg:
                            logger.debug("Servidor SMTP no soporta autenticación, enviando sin auth")
                        else:
                            # Error desconocido, intentar continuar sin auth
                            logger.debug("Error en autenticación SMTP (continuando sin auth): %s", auth_exc)
                
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
    ) -> tuple[str, str, str]:
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

        # Escapar valores para HTML
        nombre_consultor_html = html.escape(consultor.entidad.nombre or 'consultor')
        canal_html = html.escape(canal.upper())
        texto_cliente_html = html.escape(texto_cliente or 'Desconocido')
        referencia_html = html.escape(referencia or 'N/D')
        descripcion_html = html.escape(accion.descripcion or 'Sin descripción')
        aviso_html = html.escape(aviso)
        usuario_html = html.escape(accion.usuario or 'Sistema')
        creado_html = html.escape(creado)
        email_consultor_html = html.escape(consultor.entidad.email) if consultor.entidad.email else ""

        # Construir HTML del correo
        cuerpo_html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <style>
        /* Optimizaciones para Modo Oscuro */
        @media (prefers-color-scheme: dark) {{
            body, .bg-body {{ background-color: #000000 !important; }}
            .card {{ 
                background-color: #0a0a0a !important; 
                border: 1px solid #262626 !important; 
            }}
            .text-title {{ color: #ffffff !important; }}
            .text-content {{ color: #d4d4d8 !important; }}
            .text-label {{ color: #71717a !important; }}
            .data-section {{ background-color: #171717 !important; }}
            .header-line {{ border-bottom: 2px solid #ffffff !important; }}
            .cta-button {{ background-color: #ffffff !important; color: #000000 !important; }}
        }}
    </style>
</head>
<body class="bg-body" style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" class="bg-body" style="background-color: #f8fafc; padding: 60px 10px;">
        <tr>
            <td align="center">
                <table width="100%" border="0" cellspacing="0" cellpadding="0" class="card" style="max-width: 480px; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 24px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                    <tr>
                        <td style="padding: 40px;">
                            
                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td class="header-line" style="padding-bottom: 25px; border-bottom: 2px solid #000000;">
                                        <div class="text-label" style="color: #a1a1aa; font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 10px;">Atisa Gestión</div>
                                        <div class="text-title" style="color: #000000; font-size: 26px; font-weight: 800; line-height: 1.1; letter-spacing: -0.02em;">Recordatorio<br>de Acción</div>
                                    </td>
                                </tr>
                            </table>

                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding: 30px 0 20px 0;">
                                        <p class="text-content" style="margin: 0; color: #3f3f46; font-size: 15px; line-height: 1.6;">
                                            Hola <strong class="text-title" style="color: #000000;">{nombre_consultor_html}</strong>, se ha activado una tarea programada para la siguiente cuenta:
                                        </p>
                                    </td>
                                </tr>
                            </table>

                            <table width="100%" border="0" cellspacing="0" cellpadding="0" class="data-section" style="background-color: #f9fafb; border-radius: 12px; padding: 25px; margin-bottom: 25px;">
                                <tr>
                                    <td style="padding-bottom: 20px;">
                                        <div class="text-label" style="color: #71717a; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;">Cliente</div>
                                        <div class="text-title" style="color: #000000; font-size: 15px; font-weight: 700;">{texto_cliente_html}</div>
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td width="55%">
                                                    <div class="text-label" style="color: #71717a; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;">Referencia</div>
                                                    <div class="text-title" style="color: #000000; font-size: 13px; font-family: monospace; font-weight: 600;">{referencia_html}</div>
                                                </td>
                                                <td width="45%" style="text-align: right;">
                                                    <div class="text-label" style="color: #71717a; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;">Canal</div>
                                                    <div class="cta-button" style="display: inline-block; background-color: #000000; color: #ffffff; font-size: 9px; font-weight: 800; padding: 4px 10px; border-radius: 4px; text-transform: uppercase;">{canal_html}</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding-bottom: 35px; border-left: 3px solid #e5e7eb; padding-left: 20px;">
                                        <p class="text-content" style="margin: 0; color: #52525b; font-size: 14px; line-height: 1.6; font-style: italic;">
                                            "{descripcion_html}"
                                        </p>
                                    </td>
                                </tr>
                            </table>

                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td>
                                        <a href="{portal_url}" class="cta-button" style="display: block; background-color: #000000; color: #ffffff; text-align: center; padding: 20px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 14px; letter-spacing: 0.02em;">
                                            Abrir Gestión en Portal
                                        </a>
                                    </td>
                                </tr>
                            </table>

                        </td>
                    </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px;">
                    <tr>
                        <td style="padding: 30px 10px 0 10px; text-align: left;">
                            <p style="margin: 0; color: #a1a1aa; font-size: 11px; line-height: 1.8;">
                                Registrado por <span class="text-content" style="color: #71717a; font-weight: 600;">{usuario_html}</span><br>
                                {email_consultor_html if email_consultor_html else 'N/D'} • {creado_html}<br>
                                Atisa Gestión Operativa
                            </p>
                        </td>
                    </tr>
                </table>

            </td>
        </tr>
    </table>
</body>
</html>
"""

        # Versión texto plano como fallback
        cuerpo_texto = [
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
            cuerpo_texto.append(f"- Email del consultor: {consultor.entidad.email}")

        cuerpo_texto.extend([
            "",
            f"Accede al portal para gestionar el recordatorio: {portal_url}",
            f"Canal seleccionado: {canal.upper()}",
            "",
            "Gracias,",
            "Sistema de Gestion de Facturas Pendientes",
        ])

        return subject, cuerpo_html, "\r\n".join(cuerpo_texto)

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
        subject, cuerpo_html, cuerpo_texto = self._construir_mensaje_agrupado(acciones, consultor)
        enviado = self._intentar_email([destinatario_email], subject, cuerpo_html, cuerpo_texto)
        
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
    ) -> tuple[str, str, str]:
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

        # Escapar valores para HTML
        nombre_consultor_html = html.escape(consultor.entidad.nombre or 'consultor')
        canal_html = html.escape(canal.upper())
        texto_cliente_html = html.escape(texto_cliente or 'Desconocido')
        descripcion_html = html.escape(primera.descripcion or 'Sin descripción')
        aviso_html = html.escape(aviso)
        usuario_html = html.escape(primera.usuario or 'Sistema')
        creado_html = html.escape(creado)

        # Construir lista de referencias HTML
        referencias_html = ""
        for idx, accion in enumerate(acciones, 1):
            nombre_factura = self._obtener_nombre_factura(accion)
            referencia = nombre_factura or f"{accion.tipo or ''}-{accion.asiento or ''}".strip("-")
            referencia_html = html.escape(referencia or 'N/D')
            referencias_html += f"<tr><td>{idx}.</td><td><strong>{referencia_html}</strong></td></tr>"

        # Construir HTML del correo agrupado
        cuerpo_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        .container {{ font-family: 'Segoe UI', Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
        .header {{ background-color: #2c3e50; padding: 20px; text-align: center; color: white; }}
        .content {{ padding: 30px; background-color: #ffffff; }}
        .badge {{ background-color: #e67e22; color: white; padding: 4px 12px; border-radius: 15px; font-size: 12px; text-transform: uppercase; font-weight: bold; }}
        .detail-table {{ width: 100%; margin: 20px 0; border-collapse: collapse; }}
        .detail-table td {{ padding: 10px; border-bottom: 1px solid #f0f0f0; }}
        .label {{ font-weight: bold; color: #7f8c8d; width: 35%; }}
        .button-container {{ text-align: center; margin-top: 30px; }}
        .button {{ background-color: #3498db; color: white !important; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; }}
        .footer {{ background-color: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #95a5a6; }}
        .facturas-list {{ margin: 20px 0; }}
        .facturas-list table {{ width: 100%; border-collapse: collapse; }}
        .facturas-list td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin:0;">Notificación de Gestión - Acciones Agrupadas</h2>
        </div>
        <div class="content">
            <p>Hola <strong>{nombre_consultor_html}</strong>,</p>
            <p>Se han registrado <strong>{len(acciones)}</strong> acciones agrupadas para el mismo seguimiento:</p>
            
            <table class="detail-table">
                <tr>
                    <td class="label">Tipo de acción</td>
                    <td><span class="badge">{canal_html}</span></td>
                </tr>
                <tr>
                    <td class="label">Cliente</td>
                    <td>{texto_cliente_html}</td>
                </tr>
                <tr>
                    <td class="label">Descripción común</td>
                    <td>{descripcion_html}</td>
                </tr>
                <tr>
                    <td class="label">Fecha de aviso</td>
                    <td>{aviso_html}</td>
                </tr>
                <tr>
                    <td class="label">Registrado por</td>
                    <td>{usuario_html} el {creado_html}</td>
                </tr>
            </table>

            <div class="facturas-list">
                <h3>Facturas incluidas ({len(acciones)} facturas):</h3>
                <table>
                    {referencias_html}
                </table>
            </div>

            <div class="button-container">
                <a href="{portal_url}" class="button">Gestionar en el Portal</a>
            </div>
        </div>
        <div class="footer">
            Sistema de Gestión de Facturas Pendientes<br>
            Este es un correo automático, por favor no responda.
        </div>
    </div>
</body>
</html>
"""

        # Versión texto plano como fallback
        cuerpo_texto = [
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
            cuerpo_texto.append(linea)
            cuerpo_texto.append("")

        cuerpo_texto.extend([
            "═══════════════════════════════════════════════════════════",
            f"📄 FACTURAS INCLUIDAS ({len(acciones)} facturas)",
            "═══════════════════════════════════════════════════════════",
        ])

        for idx, accion in enumerate(acciones, 1):
            nombre_factura = self._obtener_nombre_factura(accion)
            referencia = nombre_factura or f"{accion.tipo or ''}-{accion.asiento or ''}".strip("-")
            cuerpo_texto.append(f"{idx}. Referencia: {referencia or 'N/D'}")

        cuerpo_texto.extend([
            "",
            "═══════════════════════════════════════════════════════════",
            "",
            f"🔗 Accede al portal para gestionar el recordatorio: {portal_url}",
            f"📞 Canal seleccionado: {canal.upper()}",
            "",
            "Gracias,",
            "Sistema de Gestion de Facturas Pendientes",
        ])

        return subject, cuerpo_html, "\r\n".join(cuerpo_texto)

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

    
