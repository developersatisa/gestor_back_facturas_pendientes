from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session
from app.config.database import get_historial_db, init_historial_db, HistorialBase
from app.infrastructure.repositorio_historial import RepositorioHistorial

router = APIRouter(prefix="/api", tags=["Historial"])


class EventoHistorialIn(BaseModel):
    tercero: str = Field(..., description="Código de cliente (BPR_0)")
    tipo: str = Field(..., description="Tipo de factura (TYP_0)")
    asiento: str = Field(..., description="Asiento/identificador de factura (ACCNUM_0)")
    estado_nuevo: str = Field(..., description="Nuevo estado: 'pagada' | 'aplazada' | otro")
    estado_anterior: Optional[str] = Field(None, description="Estado anterior si se conoce")
    motivo: Optional[str] = Field(None, description="Motivo del cambio o comentario")
    nueva_fecha: Optional[str] = Field(None, description="Nueva fecha (ISO) si aplica (aplazamiento)")
    usuario: Optional[str] = Field(None, description="Usuario que realiza el cambio")


class EventoHistorialOut(BaseModel):
    id: int
    tercero: str
    tipo: str
    asiento: str
    estado_anterior: Optional[str]
    estado_nuevo: str
    motivo: Optional[str]
    nueva_fecha: Optional[str]
    usuario: Optional[str]
    creado_en: str


def get_repo_historial(db: Session = Depends(get_historial_db)):
    return RepositorioHistorial(db)


@router.post("/historial-facturas", response_model=EventoHistorialOut)
def registrar_evento_historial(payload: EventoHistorialIn, repo: RepositorioHistorial = Depends(get_repo_historial)):
    try:
        evento = repo.registrar_evento(
            tercero=payload.tercero,
            tipo=payload.tipo,
            asiento=payload.asiento,
            estado_nuevo=payload.estado_nuevo,
            estado_anterior=payload.estado_anterior,
            motivo=payload.motivo,
            nueva_fecha=payload.nueva_fecha,
            usuario=payload.usuario,
        )
        return evento
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error guardando evento de historial")


@router.get("/historial-facturas", response_model=List[EventoHistorialOut])
def listar_historial(
    tercero: Optional[str] = None,
    tipo: Optional[str] = None,
    asiento: Optional[str] = None,
    limit: int = 200,
    repo: RepositorioHistorial = Depends(get_repo_historial),
):
    try:
        return repo.listar(tercero=tercero, tipo=tipo, asiento=asiento, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error obteniendo historial")

