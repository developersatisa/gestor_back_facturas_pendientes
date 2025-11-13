from typing import List, Optional, Dict, Any, Iterable, Set
from datetime import datetime, date
import logging
import re

from sqlalchemy.orm import Session
from sqlalchemy import select, desc, or_
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
                from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
                from app.config.database import FacturasSessionLocal, ClientesSessionLocal
                
                # Crear sesiones específicas para facturas y clientes
                facturas_db = FacturasSessionLocal()
                clientes_db = ClientesSessionLocal()
                try:
                    repo_facturas_instance = RepositorioFacturas(facturas_db)
                    repo_clientes_instance = RepositorioClientes(clientes_db)
                    notificador = NotificadorConsultores(self.db, repo_facturas=repo_facturas_instance, repo_clientes=repo_clientes_instance)
                    notificador.notificar_accion(item)
                finally:
                    # Cerrar las sesiones de facturas y clientes
                    try:
                        facturas_db.close()
                    except Exception:
                        pass
                    try:
                        clientes_db.close()
                    except Exception:
                        pass
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

    def _formatear_fecha_reclamacion(self, fecha_reclamacion: Any) -> Optional[str]:
        """
        Formatea una fecha de reclamación al formato día/mes/año (DD/MM/YYYY).
        
        Args:
            fecha_reclamacion: Fecha en formato datetime, date o string
        
        Returns:
            String con la fecha formateada o None si no se puede parsear
        """
        if not fecha_reclamacion:
            return None
        
        # Si es datetime o date, formatear directamente
        if isinstance(fecha_reclamacion, datetime):
            return fecha_reclamacion.strftime('%d/%m/%Y')
        elif isinstance(fecha_reclamacion, date):
            return fecha_reclamacion.strftime('%d/%m/%Y')
        
        # Si es string, intentar parsear en diferentes formatos
        fecha_str = str(fecha_reclamacion).strip()
        if not fecha_str:
            return None
        
        # Intentar diferentes formatos de fecha comunes
        formatos_fecha = [
            '%Y-%m-%d',           # 2024-12-05
            '%Y-%m-%dT%H:%M:%S',  # 2024-12-05T10:30:00
            '%Y-%m-%d %H:%M:%S',  # 2024-12-05 10:30:00
            '%d/%m/%Y',           # 05/12/2024
            '%d-%m-%Y',           # 05-12-2024
        ]
        
        for formato in formatos_fecha:
            try:
                # Si el formato incluye tiempo pero la cadena no, usar solo la parte de fecha
                if 'T' in fecha_str and 'T' not in formato:
                    fecha_str_limpia = fecha_str.split('T')[0]
                elif ' ' in fecha_str and ' ' not in formato and 'T' not in formato:
                    fecha_str_limpia = fecha_str.split(' ')[0]
                else:
                    fecha_str_limpia = fecha_str
                
                fecha_parsed = datetime.strptime(fecha_str_limpia, formato)
                return fecha_parsed.strftime('%d/%m/%Y')
            except (ValueError, AttributeError):
                continue
        
        # Si no se pudo parsear, intentar extraer solo números (YYYY-MM-DD)
        try:
            # Buscar patrón YYYY-MM-DD o YYYY/MM/DD
            patron = r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'
            match = re.search(patron, fecha_str)
            if match:
                año, mes, dia = match.groups()
                fecha_parsed = datetime(int(año), int(mes), int(dia))
                return fecha_parsed.strftime('%d/%m/%Y')
        except (ValueError, AttributeError):
            pass
        
        # Si todo falla, loguear y devolver el string original
        logger.warning(f"No se pudo parsear la fecha de reclamación: {fecha_reclamacion} (tipo: {type(fecha_reclamacion)})")
        return fecha_str

    def _normalizar_idcliente(self, idcliente: Optional[int], tercero: Optional[str]) -> Optional[int]:
        """
        Normaliza el idcliente a partir del tercero si no está disponible.
        
        Args:
            idcliente: ID del cliente (opcional)
            tercero: Código del tercero/cliente (opcional)
        
        Returns:
            ID del cliente normalizado o None
        """
        if idcliente:
            return idcliente
        
        if not tercero:
            return None
        
        try:
            idcliente_normalizado = int(str(tercero).lstrip('0') or '0')
            return idcliente_normalizado if idcliente_normalizado > 0 else None
        except (ValueError, TypeError):
            return None

    def _existe_accion_reclamacion(self, tercero: str, tipo: str, asiento: str, nivel: int) -> bool:
        """
        Verifica si ya existe una acción automática de reclamación para una factura específica.
        
        La verificación es muy estricta: busca acciones del sistema que coincidan exactamente
        con tipo, asiento y nivel de reclamación. La combinación tipo+asiento+nivel debe ser única
        para acciones del sistema, independientemente del formato del tercero.
        
        Args:
            tercero: Código del tercero/cliente
            tipo: Tipo de factura
            asiento: Número de asiento
            nivel: Nivel de reclamación
        
        Returns:
            True si existe una acción, False en caso contrario
        """
        # La clave única para acciones del sistema es: tipo + asiento + nivel + usuario Sistema
        # No dependemos del tercero porque puede haber variaciones en formato
        # Una factura (tipo+asiento) solo puede tener UNA acción del sistema por nivel
        query = select(AccionFactura).where(
            AccionFactura.tipo == tipo,
            AccionFactura.asiento == str(asiento),
            AccionFactura.usuario == "Sistema",
            AccionFactura.accion_tipo == "Sistema",
            AccionFactura.descripcion.like(f"%Reclamación automática%Nivel de reclamación {nivel}%")
        )
        
        # Ejecutar la consulta sin filtrar por tercero
        # Esto asegura que una factura solo tenga una acción del sistema por nivel,
        # independientemente de cómo se busque el cliente
        acciones_existentes = self.db.execute(query).scalars().all()
        
        # Si encontramos alguna acción del sistema con esta combinación, ya existe
        if len(acciones_existentes) > 0:
            logger.debug(
                f"Acción del sistema ya existe para factura {tipo}-{asiento} nivel {nivel} (tercero: {tercero}). "
                f"Encontradas {len(acciones_existentes)} acciones existentes."
            )
            return True
        
        return False

    def _convertir_fecha_reclamacion_a_datetime(self, fecha_reclamacion: Any) -> datetime:
        """
        Convierte la fecha de reclamación a un objeto datetime.
        
        Args:
            fecha_reclamacion: Fecha en cualquier formato (datetime, date, string)
        
        Returns:
            datetime: Objeto datetime con la fecha de reclamación
        """
        if isinstance(fecha_reclamacion, datetime):
            return fecha_reclamacion
        elif isinstance(fecha_reclamacion, date):
            return datetime.combine(fecha_reclamacion, datetime.min.time())
        elif fecha_reclamacion:
            try:
                fecha_str = str(fecha_reclamacion)
                if 'T' in fecha_str:
                    return datetime.strptime(fecha_str.split('T')[0], '%Y-%m-%d')
                else:
                    return datetime.strptime(fecha_str, '%Y-%m-%d')
            except (ValueError, AttributeError):
                logger.warning(f"No se pudo parsear fecha_reclamacion: {fecha_reclamacion}")
        
        return datetime.utcnow()  # Fallback a fecha actual

    def _obtener_id_accion_insertada(
        self,
        tercero: str,
        tipo: str,
        asiento: str
    ) -> Optional[int]:
        """
        Obtiene el ID de la acción insertada recientemente.
        
        Args:
            tercero: Código del tercero/cliente
            tipo: Tipo de factura
            asiento: Número de asiento
        
        Returns:
            ID de la acción o None si no se encuentra
        """
        from sqlalchemy import text
        
        # Intentar obtener con SCOPE_IDENTITY()
        try:
            sql_get_id = text("SELECT SCOPE_IDENTITY() as id")
            id_result = self.db.execute(sql_get_id)
            id_row = id_result.fetchone()
            if id_row and id_row[0]:
                return int(id_row[0])
        except Exception:
            pass
        
        # Fallback: buscar por criterios
        try:
            sql_get_id_fallback = text("""
                SELECT TOP 1 id 
                FROM factura_acciones 
                WHERE tercero = :tercero 
                  AND tipo = :tipo 
                  AND asiento = :asiento 
                  AND accion_tipo = 'Sistema'
                  AND usuario = 'Sistema'
                ORDER BY id DESC
            """)
            
            id_result = self.db.execute(sql_get_id_fallback, {
                'tercero': tercero,
                'tipo': tipo,
                'asiento': str(asiento)
            })
            id_row = id_result.fetchone()
            if id_row:
                return int(id_row[0])
        except Exception as e:
            logger.error(f"Error obteniendo ID de acción insertada: {e}")
        
        return None

    def _verificar_y_corregir_valores_accion(
        self,
        accion_id: int,
        fecha_reclamacion_dt: datetime
    ) -> None:
        """
        Verifica y corrige los valores de una acción del sistema si es necesario.
        
        Args:
            accion_id: ID de la acción a verificar
            fecha_reclamacion_dt: Fecha de reclamación esperada
        """
        from sqlalchemy import text
        
        try:
            sql_verify = text("""
                SELECT aviso, destinatario, consultor_id 
                FROM factura_acciones 
                WHERE id = :id
            """)
            
            verify_result = self.db.execute(sql_verify, {'id': accion_id})
            verify_row = verify_result.fetchone()
            
            if not verify_row:
                logger.error(f"No se encontró la acción con ID {accion_id} para verificar valores")
                return
            
            aviso_db, destinatario_db, consultor_id_db = verify_row
            
            # Si los valores no son correctos, actualizar directamente
            if aviso_db is None or destinatario_db != 'Sistema' or consultor_id_db is not None:
                logger.warning(
                    f"Valores incorrectos en BD para acción ID {accion_id}. "
                    f"Corrigiendo: aviso={aviso_db}, destinatario='{destinatario_db}', consultor_id={consultor_id_db}"
                )
                
                sql_update = text("""
                    UPDATE factura_acciones 
                    SET aviso = :aviso,
                        destinatario = 'Sistema',
                        consultor_id = NULL
                    WHERE id = :id
                """)
                
                self.db.execute(sql_update, {
                    'id': accion_id,
                    'aviso': fecha_reclamacion_dt
                })
                self.db.commit()
        except Exception as e:
            logger.error(f"Error verificando/corrigiendo valores en BD para acción ID {accion_id}: {e}")

    def _crear_accion_reclamacion_automatica(
        self,
        factura: Dict[str, Any],
        idcliente: Optional[int],
        tercero: str
    ) -> bool:
        """
        Crea una acción automática de reclamación para una factura.
        
        Args:
            factura: Diccionario con los datos de la factura
            idcliente: ID del cliente
            tercero: Código del tercero/cliente
        
        Returns:
            True si se creó la acción, False en caso contrario
        """
        nivel = factura.get('nivel_reclamacion')
        fecha_reclamacion = factura.get('fecha_reclamacion')
        tipo = factura.get('tipo')
        asiento = factura.get('asiento')
        tercero_factura = factura.get('tercero') or tercero
        
        # Verificar si ya existe una acción para esta factura con este nivel
        if self._existe_accion_reclamacion(tercero_factura, tipo, str(asiento), nivel):
            return False
        
        try:
            # Formatear fecha de reclamación para la descripción
            fecha_str = self._formatear_fecha_reclamacion(fecha_reclamacion)
            if not fecha_str:
                logger.warning(
                    f"No se pudo formatear la fecha de reclamación para factura {tipo}-{asiento}. "
                    f"Valor original: {fecha_reclamacion} (tipo: {type(fecha_reclamacion)})"
                )
                return False
            
            descripcion = f"Reclamación automática: Nivel de reclamación {nivel} enviado el {fecha_str}"
            
            # Convertir fecha de reclamación a datetime
            fecha_reclamacion_dt = self._convertir_fecha_reclamacion_a_datetime(fecha_reclamacion)
            idcliente_final = self._normalizar_idcliente(idcliente, tercero_factura)
            
            # Insertar acción usando SQL directo para garantizar valores correctos
            from sqlalchemy import text
            
            sql_insert = text("""
                INSERT INTO factura_acciones 
                (idcliente, tercero, tipo, asiento, accion_tipo, descripcion, aviso, usuario, 
                 consultor_id, destinatario, enviada_en, envio_estado, creado_en)
                VALUES 
                (:idcliente, :tercero, :tipo, :asiento, :accion_tipo, :descripcion, :aviso, :usuario, 
                 :consultor_id, :destinatario, :enviada_en, :envio_estado, GETDATE())
            """)
            
            params = {
                'idcliente': idcliente_final,
                'tercero': tercero_factura,
                'tipo': tipo,
                'asiento': str(asiento),
                'accion_tipo': 'Sistema',
                'descripcion': descripcion,
                'aviso': fecha_reclamacion_dt,
                'usuario': 'Sistema',
                'consultor_id': None,
                'destinatario': 'Sistema',
                'enviada_en': fecha_reclamacion_dt,
                'envio_estado': 'enviada'
            }
            
            # Ejecutar INSERT
            self.db.execute(sql_insert, params)
            self.db.commit()
            
            # Obtener ID de la acción insertada
            accion_id = self._obtener_id_accion_insertada(tercero_factura, tipo, str(asiento))
            if not accion_id:
                logger.error(f"No se pudo obtener ID de la acción insertada para {tipo}-{asiento}")
                return False
            
            # Verificar y corregir valores si es necesario
            self._verificar_y_corregir_valores_accion(accion_id, fecha_reclamacion_dt)
            
            logger.info(f"Acción del sistema creada para factura {tipo}-{asiento} nivel {nivel}")
            return True
            
        except Exception as e:
            logger.warning(f"Error creando acción automática para factura {tipo}-{asiento}: {e}")
            self.db.rollback()
            return False

    def crear_acciones_automaticas_reclamacion(
        self,
        *,
        idcliente: Optional[int] = None,
        tercero: Optional[str] = None,
        repo_facturas=None,
    ) -> Dict[str, Any]:
        """
        Crea acciones automáticas del sistema para facturas con nivel de reclamación 1, 2 o 3.
        
        El método procesa todas las facturas del cliente y crea acciones automáticas para aquellas
        que tienen nivel de reclamación 1, 2 o 3, evitando duplicados.
        
        Args:
            idcliente: ID del cliente (opcional)
            tercero: Código del tercero/cliente (opcional, al menos uno debe proporcionarse)
            repo_facturas: Instancia de RepositorioFacturas para obtener facturas
        
        Returns:
            Dict con estadísticas:
                - acciones_creadas: Número de acciones nuevas creadas
                - acciones_existentes: Número de acciones que ya existían
                - facturas_procesadas: Total de facturas con reclamación procesadas
        
        Raises:
            ValueError: Si no se proporciona repo_facturas o al menos uno de idcliente/tercero
        """
        if not repo_facturas:
            raise ValueError("Se requiere repo_facturas para obtener las facturas")
        
        if not idcliente and not tercero:
            raise ValueError("Se requiere al menos idcliente o tercero")
        
        # Obtener facturas del cliente
        facturas = repo_facturas.obtener_facturas(tercero=tercero)
        
        # Filtrar facturas con nivel de reclamación 1, 2 o 3 que tengan fecha de reclamación
        niveles_validos = {1, 2, 3}
        facturas_con_reclamacion = [
            f for f in facturas
            if f.get('nivel_reclamacion') in niveles_validos and f.get('fecha_reclamacion')
        ]
        
        acciones_creadas = 0
        acciones_existentes = 0
        
        for factura in facturas_con_reclamacion:
            tercero_factura = factura.get('tercero') or tercero
            
            # Verificar si ya existe una acción para esta factura ANTES de intentar crear
            nivel = factura.get('nivel_reclamacion')
            tipo = factura.get('tipo')
            asiento = factura.get('asiento')
            
            # Verificación doble: antes y dentro del método de creación
            if self._existe_accion_reclamacion(tercero_factura, tipo, str(asiento), nivel):
                acciones_existentes += 1
                logger.debug(f"Acción del sistema ya existe para {tipo}-{asiento} nivel {nivel}, omitiendo creación")
                continue
            
            # Crear acción automática (el método también verifica duplicados internamente)
            if self._crear_accion_reclamacion_automatica(factura, idcliente, tercero):
                acciones_creadas += 1
                logger.info(f"Acción del sistema creada para factura {tipo}-{asiento} nivel {nivel}")
            else:
                # Si no se creó, probablemente ya existía (verificado dentro del método)
                acciones_existentes += 1
        
        logger.info(
            f"Procesadas {len(facturas_con_reclamacion)} facturas con reclamación. "
            f"Creadas {acciones_creadas} acciones nuevas, {acciones_existentes} ya existían."
        )
        
        return {
            "acciones_creadas": acciones_creadas,
            "acciones_existentes": acciones_existentes,
            "facturas_procesadas": len(facturas_con_reclamacion)
        }

    def actualizar_accion(
        self,
        accion_id: int,
        *,
        accion_tipo: Optional[str] = None,
        descripcion: Optional[str] = None,
        aviso: Optional[str] = None,
        consultor_id: Optional[int] = None,
        idcliente: Optional[int] = None,
        tercero: Optional[str] = None,
        usuario: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Actualiza una acción existente. Solo se puede actualizar si la fecha de aviso es futura."""
        accion = self.db.get(AccionFactura, accion_id)
        if not accion:
            raise ValueError(f"Acción con ID {accion_id} no encontrada")
        
        # Regla: solo se puede editar si la fecha de aviso es futura (aún no ha llegado ese día)
        # Si no tiene fecha de aviso, se puede editar siempre
        if accion.aviso is not None:
            hoy = datetime.utcnow().date()
            fecha_aviso = accion.aviso.date()
            # Solo permitir editar si la fecha de aviso es FUTURA (mayor que hoy)
            if fecha_aviso <= hoy:
                raise PermissionError(f"La acción no se puede editar. La fecha de aviso ({fecha_aviso.strftime('%Y-%m-%d')}) ya ha pasado o es hoy.")
        
        def _parse_dt(val: Optional[str]) -> Optional[datetime]:
            if not val:
                return None
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(val, fmt)
                except ValueError:
                    continue
            return None
        
        # Actualizar campos si se proporcionan
        if accion_tipo is not None:
            accion.accion_tipo = accion_tipo
        if descripcion is not None:
            accion.descripcion = descripcion
        if aviso is not None:
            accion.aviso = _parse_dt(aviso)
        
        # Actualizar consultor y destinatario si se proporciona
        if consultor_id is not None or idcliente is not None or tercero is not None:
            consultor_final_id, destinatario_email = self._obtener_email_consultor(
                consultor_id if consultor_id is not None else accion.consultor_id,
                idcliente if idcliente is not None else accion.idcliente,
                tercero if tercero is not None else accion.tercero
            )
            accion.consultor_id = consultor_final_id
            accion.destinatario = destinatario_email
        
        # Establecer campos de auditoría de modificación
        accion.usuario_modificacion = usuario
        accion.fecha_modificacion = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(accion)
        return self._accion_to_dict(accion)

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

    def listar_proximos_avisos(self, *, limit: int = 50, repo_facturas=None) -> List[Dict[str, Any]]:
        """Obtiene los próximos avisos (acciones con fecha de aviso >= hoy), ordenados por fecha ascendente."""
        from datetime import date as date_type
        hoy = datetime.utcnow().date()
        
        stmt = select(AccionFactura).where(
            AccionFactura.aviso.isnot(None),
            AccionFactura.aviso >= datetime.combine(hoy, datetime.min.time())
        ).order_by(AccionFactura.aviso.asc()).limit(limit)
        
        rows = self.db.execute(stmt).scalars().all()
        resultado = []
        facturas_cache = {}
        
        for x in rows:
            accion_dict = self._accion_to_dict(x)
            # Obtener nombre_factura si hay repo_facturas disponible
            if repo_facturas:
                _, nombre_factura = self._factura_sigue_pendiente(x, repo_facturas, facturas_cache)
                if nombre_factura:
                    accion_dict["nombre_factura"] = nombre_factura
            resultado.append(accion_dict)
        
        return resultado

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
            "usuario_modificacion": x.usuario_modificacion,
            "fecha_modificacion": x.fecha_modificacion.isoformat() if x.fecha_modificacion else None,
            "seguimiento_id": x.seguimiento_id,
        }


