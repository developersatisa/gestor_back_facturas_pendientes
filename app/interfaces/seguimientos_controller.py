from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.config.database import get_gestion_db
from app.domain.models.gestion import Seguimiento, SeguimientoFactura, AccionFactura


router = APIRouter(prefix="/api", tags=["Seguimientos"])


class FacturaRef(BaseModel):
    tipo: str = Field(..., min_length=1, max_length=10)
    asiento: str = Field(..., min_length=1, max_length=50)
    importe: Optional[float] = None
    pendiente: Optional[float] = None


class SeguimientoIn(BaseModel):
    idcliente: Optional[int] = None
    tercero: str = Field(..., min_length=1, max_length=50)
    nombre: str = Field(..., min_length=2, max_length=150)
    descripcion: Optional[str] = None
    usuario: Optional[str] = None
    facturas: List[FacturaRef] = Field(default_factory=list)


class SeguimientoOut(BaseModel):
    id: int
    idcliente: Optional[int]
    tercero: str
    nombre: str
    descripcion: Optional[str]
    usuario: Optional[str]
    creado_en: str
    total_pendiente: float
    num_facturas: int
    facturas: List[FacturaRef]


def _seguimiento_to_out(db: Session, seg: Seguimiento) -> SeguimientoOut:
    lineas = db.execute(
        select(SeguimientoFactura).where(SeguimientoFactura.seguimiento_id == seg.id)
    ).scalars().all()
    total_pendiente = float(sum((l.pendiente or 0) for l in lineas)) if lineas else 0.0
    return SeguimientoOut(
        id=seg.id,
        idcliente=seg.idcliente,
        tercero=seg.tercero,
        nombre=seg.nombre,
        descripcion=seg.descripcion,
        usuario=seg.usuario,
        creado_en=seg.creado_en.isoformat() if seg.creado_en else "",
        total_pendiente=total_pendiente,
        num_facturas=len(lineas),
        facturas=[FacturaRef(tipo=l.tipo, asiento=l.asiento, importe=float(l.importe or 0), pendiente=float(l.pendiente or 0)) for l in lineas]
    )


@router.post("/seguimientos", response_model=SeguimientoOut, status_code=status.HTTP_201_CREATED)
def crear_seguimiento(payload: SeguimientoIn, db: Session = Depends(get_gestion_db)):
    try:
        seg = Seguimiento(
            idcliente=payload.idcliente,
            tercero=payload.tercero.strip(),
            nombre=payload.nombre.strip(),
            descripcion=(payload.descripcion or None),
            usuario=(payload.usuario or None),
        )
        db.add(seg)
        db.flush()

        for f in payload.facturas:
            linea = SeguimientoFactura(
                seguimiento_id=seg.id,
                tipo=f.tipo.strip(),
                asiento=f.asiento.strip(),
                importe=f.importe,
                pendiente=f.pendiente,
            )
            db.add(linea)

        db.commit()
        db.refresh(seg)
        return _seguimiento_to_out(db, seg)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo crear el seguimiento")


@router.get("/seguimientos", response_model=List[SeguimientoOut])
def listar_seguimientos(idcliente: Optional[int] = None, tercero: Optional[str] = None, db: Session = Depends(get_gestion_db)):
    try:
        q = select(Seguimiento)
        if idcliente is not None:
            q = q.where(Seguimiento.idcliente == idcliente)
        if tercero:
            q = q.where(Seguimiento.tercero == tercero)
        q = q.order_by(Seguimiento.creado_en.desc())
        segs = db.execute(q).scalars().all()
        return [_seguimiento_to_out(db, s) for s in segs]
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudieron listar los seguimientos")


class AccionSeguimientoIn(BaseModel):
    accion_tipo: str = Field(..., min_length=1, max_length=50)
    descripcion: Optional[str] = None
    aviso: Optional[str] = None  # ISO date string
    usuario: Optional[str] = None


@router.post("/seguimientos/{seguimiento_id}/acciones", status_code=status.HTTP_201_CREATED)
def crear_acciones_para_seguimiento(seguimiento_id: int, payload: AccionSeguimientoIn, db: Session = Depends(get_gestion_db)):
    try:
        seg = db.get(Seguimiento, seguimiento_id)
        if not seg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seguimiento no encontrado")

        lineas = db.execute(
            select(SeguimientoFactura).where(SeguimientoFactura.seguimiento_id == seguimiento_id)
        ).scalars().all()
        if not lineas:
            return {"creadas": 0}

        creadas = 0
        from datetime import datetime
        aviso_dt = None
        if payload.aviso:
            try:
                aviso_dt = datetime.fromisoformat(payload.aviso)
            except Exception:
                aviso_dt = None

        for l in lineas:
            acc = AccionFactura(
                idcliente=seg.idcliente,
                tercero=seg.tercero,
                tipo=l.tipo,
                asiento=l.asiento,
                accion_tipo=payload.accion_tipo,
                descripcion=(payload.descripcion or None),
                aviso=aviso_dt,
                usuario=(payload.usuario or seg.usuario or None),
            )
            db.add(acc)
            creadas += 1
        db.commit()
        return {"creadas": creadas}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudieron crear las acciones del seguimiento")


