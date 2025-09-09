from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.config.database import get_gestion_db, init_gestion_db, GestionBase
from app.infrastructure.repositorio_registro_facturas import RepositorioRegistroFacturas

router = APIRouter(prefix="/api", tags=["Registro Facturas"])


class CambioFacturaIn(BaseModel):
    idcliente: Optional[int] = None
    tercero: str
    tipo: str
    asiento: str
    numero_anterior: Optional[str] = None
    numero_nuevo: Optional[str] = None
    monto_anterior: Optional[float] = None
    monto_nuevo: Optional[float] = None
    vencimiento_anterior: Optional[str] = None  # ISO
    vencimiento_nuevo: Optional[str] = None     # ISO
    motivo: Optional[str] = None
    usuario: Optional[str] = None


class CambioFacturaOut(BaseModel):
    id: int
    idcliente: Optional[int]
    tercero: str
    tipo: str
    asiento: str
    numero_anterior: Optional[str]
    numero_nuevo: Optional[str]
    monto_anterior: Optional[float]
    monto_nuevo: Optional[float]
    vencimiento_anterior: Optional[str]
    vencimiento_nuevo: Optional[str]
    motivo: Optional[str]
    usuario: Optional[str]
    creado_en: str


class AccionFacturaIn(BaseModel):
    idcliente: Optional[int] = None
    tercero: str
    tipo: str
    asiento: str
    accion_tipo: str = Field(..., description="Email | Llamada | Visita | SMS | Otro | Aplazamiento ...")
    descripcion: Optional[str] = None
    aviso: Optional[str] = None
    usuario: Optional[str] = None


class AccionFacturaOut(BaseModel):
    id: int
    idcliente: Optional[int]
    tercero: str
    tipo: str
    asiento: str
    accion_tipo: str
    descripcion: Optional[str]
    aviso: Optional[str]
    usuario: Optional[str]
    creado_en: str


def get_repo(db: Session = Depends(get_gestion_db)):
    return RepositorioRegistroFacturas(db)


@router.post("/facturas/cambios", response_model=CambioFacturaOut, status_code=status.HTTP_201_CREATED)
def registrar_cambio(payload: CambioFacturaIn, repo: RepositorioRegistroFacturas = Depends(get_repo)):
    try:
        return repo.registrar_cambio(**payload.model_dump())
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error registrando cambio de factura")


@router.get("/facturas/cambios", response_model=List[CambioFacturaOut])
def listar_cambios(idcliente: Optional[int] = None, tercero: Optional[str] = None, tipo: Optional[str] = None, asiento: Optional[str] = None, limit: int = 200, repo: RepositorioRegistroFacturas = Depends(get_repo)):
    try:
        return repo.listar_cambios(idcliente=idcliente, tercero=tercero, tipo=tipo, asiento=asiento, limit=limit)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error obteniendo cambios de factura")


@router.post("/facturas/acciones", response_model=AccionFacturaOut, status_code=status.HTTP_201_CREATED)
def registrar_accion(payload: AccionFacturaIn, repo: RepositorioRegistroFacturas = Depends(get_repo)):
    try:
        return repo.registrar_accion(**payload.model_dump())
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error registrando acción de factura")


@router.get("/facturas/acciones", response_model=List[AccionFacturaOut])
def listar_acciones(idcliente: Optional[int] = None, tercero: Optional[str] = None, tipo: Optional[str] = None, asiento: Optional[str] = None, limit: int = 200, repo: RepositorioRegistroFacturas = Depends(get_repo)):
    try:
        return repo.listar_acciones(idcliente=idcliente, tercero=tercero, tipo=tipo, asiento=asiento, limit=limit)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error obteniendo acciones de factura")
