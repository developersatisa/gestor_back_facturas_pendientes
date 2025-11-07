from typing import List, Optional
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, text as sqltext

from app.config.database import get_gestion_db
from app.domain.models.gestion import AccionFactura, SeguimientoAcciones

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["Seguimiento Acciones"])


class SeguimientoAccionIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=150)


class SeguimientoAccionOut(BaseModel):
    id: int
    nombre: str
    creado_en: str


class AccionMasivaIn(BaseModel):
    idcliente: Optional[int] = None
    tercero: str
    consultor_id: int
    usuario: str  # De /auth/me.name
    accion_tipo: str
    descripcion: str
    aviso: Optional[str] = None  # ISO YYYY-MM-DD, opcional
    facturas: List[dict] = Field(default_factory=list)  # [{tipo, asiento}]
    editar_accion_comun_id: Optional[int] = None  # Si se proporciona, edita esa acción común. Si no, crea una nueva.


@router.post("/seguimiento-acciones", response_model=SeguimientoAccionOut, status_code=status.HTTP_201_CREATED)
def crear_seguimiento_acciones(payload: SeguimientoAccionIn, db: Session = Depends(get_gestion_db)):
    try:
        seg = SeguimientoAcciones(nombre=payload.nombre.strip())
        db.add(seg)
        db.commit()
        db.refresh(seg)
        return {
            "id": seg.id,
            "nombre": seg.nombre,
            "creado_en": seg.creado_en.isoformat() if seg.creado_en else "",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo crear el seguimiento: {str(e)}")


class FacturaSeguimientoOut(BaseModel):
    tipo: str
    asiento: str

class AccionCreadaOut(BaseModel):
    id: int
    tipo: str
    asiento: str
    accion_tipo: Optional[str] 
    descripcion: Optional[str]
    aviso: Optional[str]
    creado_en: str
    enviada_en: Optional[str]

class SeguimientoAccionListOut(BaseModel):
    id: int
    nombre: str
    creado_en: str
    num_acciones: int
    num_enviadas: int
    facturas: List[FacturaSeguimientoOut] = Field(default_factory=list)
    accion_comun: Optional[dict] = None  # { accion_tipo, descripcion, aviso }
    acciones_creadas: List[AccionCreadaOut] = Field(default_factory=list)


@router.get("/seguimiento-acciones", response_model=List[SeguimientoAccionListOut])
def listar_seguimientos(
    idcliente: Optional[int] = None,
    tercero: Optional[str] = None,
    pendientes: Optional[bool] = False,
    db: Session = Depends(get_gestion_db),
):
    try:
        # Consulta que devuelve cabeceras + conteo de acciones y enviadas
        # Nota: filtramos por idcliente/tercero en acciones (si existen), o devolvemos todas
        base_sql = (
            "SELECT sa.id, sa.nombre, sa.creado_en, "
            "  COUNT(a.id) AS num_acciones, "
            "  SUM(CASE WHEN a.enviada_en IS NOT NULL THEN 1 ELSE 0 END) AS num_enviadas "
            "FROM seguimiento_acciones sa "
            "LEFT JOIN factura_acciones a ON a.seguimiento_id = sa.id "
        )
        where_clauses = []
        params = {}
        if idcliente is not None:
            where_clauses.append("(a.idcliente = :idcliente OR a.idcliente IS NULL)")
            params["idcliente"] = idcliente
        if tercero:
            where_clauses.append("(a.tercero = :tercero OR a.tercero IS NULL)")
            params["tercero"] = tercero
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        group_sql = " GROUP BY sa.id, sa.nombre, sa.creado_en"
        order_sql = " ORDER BY sa.creado_en DESC"
        rows = db.execute(sqltext(base_sql + where_sql + group_sql + order_sql), params).all()

        # Obtener facturas asociadas a cada seguimiento, la acción común y todas las acciones creadas
        seguimiento_facturas = {}
        seguimiento_accion_comun = {}
        seguimiento_acciones_creadas = {}
        if rows:
            seguimiento_ids = [r[0] for r in rows]
            facturas_query = select(AccionFactura.seguimiento_id, AccionFactura.tipo, AccionFactura.asiento).where(
                AccionFactura.seguimiento_id.in_(seguimiento_ids)
            )
            if idcliente is not None:
                facturas_query = facturas_query.where(AccionFactura.idcliente == idcliente)
            if tercero:
                facturas_query = facturas_query.where(AccionFactura.tercero == tercero)
            
            facturas_rows = db.execute(facturas_query).all()
            for f_row in facturas_rows:
                seg_id = f_row[0]
                if seg_id not in seguimiento_facturas:
                    seguimiento_facturas[seg_id] = []
                # Evitar duplicados
                factura_key = (f_row[1], str(f_row[2]))
                if factura_key not in [(x["tipo"], x["asiento"]) for x in seguimiento_facturas[seg_id]]:
                    seguimiento_facturas[seg_id].append({"tipo": f_row[1], "asiento": str(f_row[2])})
            
            # Obtener la primera acción de cada seguimiento para mostrar la acción común
            # Usamos una consulta simple y luego agrupamos por seguimiento_id tomando la primera
            accion_comun_query = select(
                AccionFactura.seguimiento_id,
                AccionFactura.accion_tipo,
                AccionFactura.descripcion,
                AccionFactura.aviso,
                AccionFactura.creado_en
            ).where(
                AccionFactura.seguimiento_id.in_(seguimiento_ids)
            ).order_by(AccionFactura.seguimiento_id, AccionFactura.creado_en)
            if idcliente is not None:
                accion_comun_query = accion_comun_query.where(AccionFactura.idcliente == idcliente)
            if tercero:
                accion_comun_query = accion_comun_query.where(AccionFactura.tercero == tercero)
            
            accion_rows = db.execute(accion_comun_query).all()
            for a_row in accion_rows:
                seg_id = a_row[0]
                if seg_id not in seguimiento_accion_comun:
                    seguimiento_accion_comun[seg_id] = {
                        "accion_tipo": a_row[1] or "",
                        "descripcion": a_row[2] or "",
                        "aviso": a_row[3].isoformat().split('T')[0] if a_row[3] else ""
                    }
            
            # Obtener todas las acciones creadas de cada seguimiento
            acciones_creadas_query = select(
                AccionFactura.id,
                AccionFactura.seguimiento_id,
                AccionFactura.tipo,
                AccionFactura.asiento,
                AccionFactura.accion_tipo,
                AccionFactura.descripcion,
                AccionFactura.aviso,
                AccionFactura.creado_en,
                AccionFactura.enviada_en
            ).where(
                AccionFactura.seguimiento_id.in_(seguimiento_ids)
            ).order_by(AccionFactura.seguimiento_id, AccionFactura.creado_en.desc())
            if idcliente is not None:
                acciones_creadas_query = acciones_creadas_query.where(AccionFactura.idcliente == idcliente)
            if tercero:
                acciones_creadas_query = acciones_creadas_query.where(AccionFactura.tercero == tercero)
            
            acciones_rows = db.execute(acciones_creadas_query).all()
            for acc_row in acciones_rows:
                seg_id = acc_row[1]
                if seg_id not in seguimiento_acciones_creadas:
                    seguimiento_acciones_creadas[seg_id] = []
                seguimiento_acciones_creadas[seg_id].append({
                    "id": acc_row[0],
                    "tipo": acc_row[2] or "",
                    "asiento": str(acc_row[3] or ""),
                    "accion_tipo": acc_row[4] or "",
                    "descripcion": acc_row[5] or "",
                    "aviso": acc_row[6].isoformat().split('T')[0] if acc_row[6] else None,
                    "creado_en": acc_row[7].isoformat() if acc_row[7] else "",
                    "enviada_en": acc_row[8].isoformat().split('T')[0] if acc_row[8] else None
                })

        # Si piden pendientes, filtrar aquellos con num_enviadas = 0
        out = []
        for r in rows:
            item = {
                "id": r[0],
                "nombre": r[1],
                "creado_en": r[2].isoformat() if r[2] else "",
                "num_acciones": int(r[3] or 0),
                "num_enviadas": int(r[4] or 0),
                "facturas": seguimiento_facturas.get(r[0], []),
                "accion_comun": seguimiento_accion_comun.get(r[0]),
                "acciones_creadas": seguimiento_acciones_creadas.get(r[0], []),
            }
            if pendientes:
                if item["num_enviadas"] == 0:
                    out.append(item)
            else:
                out.append(item)
        return out
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudieron listar los seguimientos")

@router.post("/seguimiento-acciones/{seguimiento_id}/acciones", status_code=status.HTTP_201_CREATED)
def crear_acciones_de_seguimiento(seguimiento_id: int, payload: AccionMasivaIn, db: Session = Depends(get_gestion_db)):
    try:
        from datetime import datetime
        ahora = datetime.utcnow()
        def parse_date(s: Optional[str]):
            if not s or not s.strip():
                return None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(s.strip(), fmt)
                except Exception:
                    continue
            return None

        aviso_dt = parse_date(payload.aviso)
        # La fecha es opcional, solo validar si se proporciona
        if payload.aviso and payload.aviso.strip() and aviso_dt is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formato de fecha inválido")

        # Verificar si ya hay acciones placeholder (sin accion_tipo/descripcion/aviso)
        acciones_existentes = db.execute(
            select(AccionFactura).where(AccionFactura.seguimiento_id == seguimiento_id)
        ).scalars().all()
        
        acciones_placeholder = [a for a in acciones_existentes if not a.accion_tipo and not a.descripcion and not a.aviso]
        acciones_con_comun = [a for a in acciones_existentes if a.accion_tipo or a.descripcion or a.aviso]
        acciones_creadas = []
        acciones_a_actualizar = []
        
        # Si se está editando una acción común específica, solo actualizar esa
        if payload.editar_accion_comun_id is not None:
            logger.info(f"Editando acción común específica {payload.editar_accion_comun_id} para seguimiento {seguimiento_id}")
            # Buscar todas las acciones con los mismos valores (accion_tipo, descripcion, aviso) que la acción a editar
            accion_a_editar = next((a for a in acciones_con_comun if a.id == payload.editar_accion_comun_id), None)
            if not accion_a_editar:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró la acción común a editar")
            
            # Agrupar acciones por (accion_tipo, descripcion, aviso) para encontrar todas las acciones de ese grupo
            acciones_del_mismo_grupo = [
                a for a in acciones_con_comun 
                if (a.accion_tipo or '') == (accion_a_editar.accion_tipo or '') and
                   (a.descripcion or '') == (accion_a_editar.descripcion or '') and
                   (a.aviso or None) == (accion_a_editar.aviso or None)
            ]
            
            # Actualizar todas las acciones del mismo grupo
            facturas_payload_set = {((f.get("tipo") or "").strip(), str(f.get("asiento") or "").strip()) for f in payload.facturas}
            acciones_a_eliminar = []
            
            for acc in acciones_del_mismo_grupo:
                factura_key = (acc.tipo or "", str(acc.asiento or ""))
                if factura_key in facturas_payload_set:
                    # Actualizar la acción
                    acc.accion_tipo = payload.accion_tipo
                    acc.descripcion = payload.descripcion
                    acc.aviso = aviso_dt
                    acc.usuario = payload.usuario
                    acc.consultor_id = payload.consultor_id
                    acc.usuario_modificacion = payload.usuario
                    acc.fecha_modificacion = ahora
                    acciones_a_actualizar.append(acc)
                else:
                    # Eliminar acciones que ya no están en las facturas nuevas
                    acciones_a_eliminar.append(acc)
            
            # Eliminar acciones que ya no están en la nueva lista
            for acc in acciones_a_eliminar:
                db.delete(acc)
            
            # Crear nuevas acciones para facturas que no tienen acción de este grupo
            facturas_existentes_set = {(acc.tipo or "", str(acc.asiento or "")) for acc in acciones_del_mismo_grupo}
            for f in payload.facturas:
                tipo = (f.get("tipo") or "").strip()
                asiento = str(f.get("asiento") or "").strip()
                if not tipo or not asiento:
                    continue
                factura_key = (tipo, asiento)
                if factura_key not in facturas_existentes_set:
                    acc = AccionFactura(
                        idcliente=payload.idcliente,
                        tercero=payload.tercero,
                        tipo=tipo,
                        asiento=asiento,
                        accion_tipo=payload.accion_tipo,
                        descripcion=payload.descripcion,
                        aviso=aviso_dt,
                        usuario=payload.usuario,
                        consultor_id=payload.consultor_id,
                        seguimiento_id=seguimiento_id,
                    )
                    db.add(acc)
                    acciones_creadas.append(acc)
        
        # Si hay acciones placeholder, actualizarlas TODAS con la acción común
        elif acciones_placeholder:
            logger.info(f"Actualizando {len(acciones_placeholder)} acciones placeholder con acción común")
            # Actualizar TODAS las acciones placeholder del seguimiento con la acción común
            for acc in acciones_placeholder:
                acc.accion_tipo = payload.accion_tipo
                acc.descripcion = payload.descripcion
                acc.aviso = aviso_dt
                acc.usuario = payload.usuario
                acc.consultor_id = payload.consultor_id
                # Establecer campos de auditoría
                acc.usuario_modificacion = payload.usuario
                acc.fecha_modificacion = ahora
                acciones_a_actualizar.append(acc)
            
            # Si hay facturas en el payload que no tienen placeholder, crear nuevas acciones
            if payload.facturas:
                facturas_placeholder_set = {(acc.tipo or "", str(acc.asiento or "")) for acc in acciones_placeholder}
                for f in payload.facturas:
                    tipo = (f.get("tipo") or "").strip()
                    asiento = str(f.get("asiento") or "").strip()
                    if not tipo or not asiento:
                        continue
                    factura_key = (tipo, asiento)
                    if factura_key not in facturas_placeholder_set:
                        # Crear nueva acción para factura que no tiene placeholder
                        acc = AccionFactura(
                            idcliente=payload.idcliente,
                            tercero=payload.tercero,
                            tipo=tipo,
                            asiento=asiento,
                            accion_tipo=payload.accion_tipo,
                            descripcion=payload.descripcion,
                            aviso=aviso_dt,
                            usuario=payload.usuario,
                            consultor_id=payload.consultor_id,
                            seguimiento_id=seguimiento_id,
                        )
                        db.add(acc)
                        acciones_creadas.append(acc)
        
        # Si hay acciones comunes existentes Y no estamos editando, crear nuevas acciones sin modificar las existentes
        elif acciones_con_comun:
            logger.info(f"Creando nueva acción común para seguimiento {seguimiento_id} (hay {len(acciones_con_comun)} acciones comunes existentes)")
            # Crear nuevas acciones para todas las facturas del payload (sin modificar las existentes)
            for f in payload.facturas:
                tipo = (f.get("tipo") or "").strip()
                asiento = str(f.get("asiento") or "").strip()
                if not tipo or not asiento:
                    continue
                # Siempre crear nueva acción, incluso si ya existe una acción común para esa factura
                # Esto permite tener múltiples acciones comunes para las mismas facturas
                    acc = AccionFactura(
                        idcliente=payload.idcliente,
                        tercero=payload.tercero,
                        tipo=tipo,
                        asiento=asiento,
                        accion_tipo=payload.accion_tipo,
                        descripcion=payload.descripcion,
                        aviso=aviso_dt,
                        usuario=payload.usuario,
                        consultor_id=payload.consultor_id,
                        seguimiento_id=seguimiento_id,
                    )
                    db.add(acc)
                    acciones_creadas.append(acc)
            
        else:
            # No hay acciones placeholder ni comunes, crear todas nuevas
            for f in payload.facturas:
                tipo = (f.get("tipo") or "").strip()
                asiento = str(f.get("asiento") or "").strip()
                if not tipo or not asiento:
                    continue
                acc = AccionFactura(
                    idcliente=payload.idcliente,
                    tercero=payload.tercero,
                    tipo=tipo,
                    asiento=asiento,
                    accion_tipo=payload.accion_tipo,
                    descripcion=payload.descripcion,
                    aviso=aviso_dt,
                    usuario=payload.usuario,
                    consultor_id=payload.consultor_id,
                    seguimiento_id=seguimiento_id,
                )
                db.add(acc)
                acciones_creadas.append(acc)
        
        # Hacer commit para tener los IDs
        db.commit()
        
        # Refrescar todas las acciones (creadas y actualizadas) para tener los IDs asignados
        todas_acciones = list(acciones_creadas) + list(acciones_a_actualizar)
        
        for acc in todas_acciones:
            db.refresh(acc)
        
        # Enviar una sola notificación agrupada si hay acciones y deben enviarse ahora
        if todas_acciones:
            try:
                from app.services.notificador_consultores import NotificadorConsultores
                notificador = NotificadorConsultores(db)
                
                # Enviar solo si hay fecha de aviso y es hoy o en el pasado
                enviar_ahora = False
                if aviso_dt is not None:
                    hoy = datetime.utcnow().date()
                    enviar_ahora = aviso_dt.date() <= hoy
                
                if enviar_ahora:
                    notificador.notificar_acciones_agrupadas(todas_acciones)
                    db.commit()
            except Exception as notify_error:
                logger.warning("No se pudo enviar la notificacion agrupada al consultor: %s", notify_error)
                try:
                    for acc in todas_acciones:
                        acc.envio_estado = "fallo"
                    db.commit()
                except Exception:
                    pass
        
        return {"creadas": len(todas_acciones)}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Error creando acciones de seguimiento: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudieron crear las acciones")

@router.delete("/seguimiento-acciones/{seguimiento_id}/acciones", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_acciones_de_seguimiento(seguimiento_id: int, db: Session = Depends(get_gestion_db)):
    """Elimina todas las acciones asociadas a un seguimiento (acción común)."""
    try:
        from datetime import datetime
        # Verificar que existan acciones con seguimiento_id
        acciones = db.execute(
            select(AccionFactura).where(AccionFactura.seguimiento_id == seguimiento_id)
        ).scalars().all()
        
        if not acciones:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se encontraron acciones para este seguimiento")
        
        # Verificar que todas las acciones puedan ser eliminadas (fecha de aviso futura)
        hoy = datetime.utcnow().date()
        acciones_no_eliminables = [a for a in acciones if a.aviso and a.aviso.date() <= hoy]
        if acciones_no_eliminables:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No se pueden eliminar acciones. {len(acciones_no_eliminables)} acción(es) tienen fecha de aviso pasada o de hoy."
            )
        
        # Eliminar todas las acciones del seguimiento
        for accion in acciones:
            db.delete(accion)
        
        db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Error eliminando acciones de seguimiento: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudieron eliminar las acciones")

@router.delete("/seguimiento-acciones/{seguimiento_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_seguimiento_completo(seguimiento_id: int, db: Session = Depends(get_gestion_db)):
    """Elimina un seguimiento completo y todas sus acciones asociadas."""
    try:
        from datetime import datetime
        # Verificar que el seguimiento exista
        seguimiento = db.get(SeguimientoAcciones, seguimiento_id)
        if not seguimiento:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seguimiento no encontrado")
        
        # Obtener todas las acciones asociadas
        acciones = db.execute(
            select(AccionFactura).where(AccionFactura.seguimiento_id == seguimiento_id)
        ).scalars().all()
        
        # Verificar que todas las acciones puedan ser eliminadas (fecha de aviso futura)
        hoy = datetime.utcnow().date()
        acciones_no_eliminables = [a for a in acciones if a.aviso and a.aviso.date() <= hoy]
        if acciones_no_eliminables:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No se puede eliminar el seguimiento. {len(acciones_no_eliminables)} acción(es) tienen fecha de aviso pasada o de hoy."
            )
        
        # Eliminar todas las acciones del seguimiento
        for accion in acciones:
            db.delete(accion)
        
        # Eliminar el seguimiento
        db.delete(seguimiento)
        
        db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Error eliminando seguimiento completo: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo eliminar el seguimiento")


class ActualizarFacturasSeguimientoIn(BaseModel):
    facturas: List[dict] = Field(..., description="Lista de facturas [{tipo, asiento}]")
    idcliente: Optional[int] = None
    tercero: Optional[str] = None
    consultor_id: Optional[int] = None
    usuario: Optional[str] = None


@router.put("/seguimiento-acciones/{seguimiento_id}/facturas", status_code=status.HTTP_200_OK)
def actualizar_facturas_seguimiento(seguimiento_id: int, payload: ActualizarFacturasSeguimientoIn, db: Session = Depends(get_gestion_db)):
    """Actualiza las facturas asociadas a un seguimiento. Solo permitido si NO hay acción común creada."""
    try:
        # Verificar que el seguimiento exista
        seguimiento = db.get(SeguimientoAcciones, seguimiento_id)
        if not seguimiento:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seguimiento no encontrado")
        
        # Verificar que NO haya acción común (si hay acciones con accion_tipo/descripcion/aviso, no se puede editar)
        acciones_existentes = db.execute(
            select(AccionFactura).where(AccionFactura.seguimiento_id == seguimiento_id)
        ).scalars().all()
        
        # Si hay acciones con acción común (tienen accion_tipo, descripcion o aviso), no se puede editar
        acciones_con_comun = [a for a in acciones_existentes if a.accion_tipo or a.descripcion or a.aviso]
        if acciones_con_comun:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se pueden editar las facturas de un seguimiento que ya tiene una acción común creada."
            )
        
        # Eliminar todas las acciones placeholder existentes
        for accion in acciones_existentes:
            db.delete(accion)
        
        # Crear nuevas acciones placeholder con las facturas actualizadas
        # Necesitamos idcliente y tercero del seguimiento, los obtendremos de la primera acción o del request
        # Por ahora, creamos acciones placeholder sin accion_tipo/descripcion/aviso
        # Estas se actualizarán cuando se cree la acción común
        
        # Obtener datos de la primera acción existente para mantener idcliente y tercero
        # O usar los datos del payload si no hay acciones previas
        idcliente = payload.idcliente
        tercero = payload.tercero
        consultor_id = payload.consultor_id
        usuario = payload.usuario or "Sistema"
        
        if acciones_existentes:
            primera = acciones_existentes[0]
            # Usar datos existentes si no se proporcionan en el payload
            if idcliente is None:
                idcliente = primera.idcliente
            if not tercero:
                tercero = primera.tercero
            if consultor_id is None:
                consultor_id = primera.consultor_id
            if not usuario or usuario == "Sistema":
                usuario = primera.usuario or usuario
        
        # Validar que tenemos los datos mínimos requeridos
        if not tercero or not tercero.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El campo 'tercero' es requerido para crear acciones placeholder."
            )
        
        # Crear acciones placeholder con las nuevas facturas
        acciones_creadas = 0
        errores = []
        for f in payload.facturas:
            tipo = (f.get("tipo") or "").strip()
            asiento = str(f.get("asiento") or "").strip()
            if not tipo or not asiento:
                errores.append(f"Factura inválida: tipo o asiento vacío")
                continue
            
            try:
                acc = AccionFactura(
                    idcliente=idcliente,
                    tercero=tercero.strip(),
                    tipo=tipo,
                    asiento=asiento,
                    accion_tipo=None,  # Placeholder - sin acción común todavía
                    descripcion=None,
                    aviso=None,
                    usuario=usuario or "Sistema",
                    consultor_id=consultor_id,
                    seguimiento_id=seguimiento_id,
                )
                db.add(acc)
                acciones_creadas += 1
            except Exception as e:
                errores.append(f"Error creando acción para {tipo}-{asiento}: {str(e)}")
                logger.error(f"Error creando acción placeholder para {tipo}-{asiento}: {e}")
        
        # Si no se crearon acciones pero no hay errores, es válido (seguimiento sin facturas)
        if acciones_creadas == 0 and errores:
            error_msg = "No se pudieron crear acciones placeholder. "
            error_msg += "Errores: " + "; ".join(errores[:3])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        db.commit()
        if acciones_creadas == 0:
            mensaje = "Seguimiento actualizado sin facturas asociadas."
        else:
            mensaje = f"Facturas actualizadas. {acciones_creadas} factura(s) asociada(s)."
        if errores:
            mensaje += f" (Algunos errores: {len(errores)})"
        return {"message": mensaje, "actualizadas": acciones_creadas}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Error actualizando facturas de seguimiento: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudieron actualizar las facturas")


