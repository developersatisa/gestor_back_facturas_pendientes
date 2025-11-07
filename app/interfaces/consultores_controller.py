from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Literal
from sqlalchemy.orm import Session
from app.config.database import get_gestion_db, init_gestion_db, GestionBase
from app.infrastructure.repositorio_gestion import RepositorioGestion

router = APIRouter(prefix="/api", tags=["Consultores"])


class ConsultorIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=150)
    estado: Literal['activo', 'inactivo', 'vacaciones'] = 'activo'
    email: Optional[EmailStr] = None

    @validator('email', pre=True)
    def _blank_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value


class ConsultorOut(BaseModel):
    id: int
    nombre: str
    estado: Literal['activo', 'inactivo', 'vacaciones']
    email: Optional[str]
    creado_en: Optional[str]


class AsignacionIn(BaseModel):
    idcliente: int
    consultor_id: int


def get_repo(db: Session = Depends(get_gestion_db)):
    return RepositorioGestion(db)


@router.get("/consultores", response_model=List[ConsultorOut])
def listar_consultores(solo_activos: bool = False, repo: RepositorioGestion = Depends(get_repo)):
    return repo.listar_consultores(solo_activos=solo_activos)


@router.post("/consultores", response_model=ConsultorOut, status_code=status.HTTP_201_CREATED)
def crear_consultor(payload: ConsultorIn, repo: RepositorioGestion = Depends(get_repo)):
    return repo.crear_consultor(
        nombre=payload.nombre,
        estado=payload.estado,
        email=payload.email,
    )


@router.put("/consultores/{consultor_id}", response_model=ConsultorOut)
def actualizar_consultor(consultor_id: int, payload: ConsultorIn, repo: RepositorioGestion = Depends(get_repo)):
    fields = {
        "nombre": payload.nombre,
        "estado": payload.estado,
        "email": payload.email,
    }
    updated = repo.actualizar_consultor(consultor_id, **fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultor no encontrado")
    return updated


@router.delete("/consultores/{consultor_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_consultor(consultor_id: int, repo: RepositorioGestion = Depends(get_repo)):
    ok = repo.eliminar_consultor(consultor_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultor no encontrado")
    return None


@router.get("/consultores/asignacion/{idcliente}")
def obtener_asignacion(idcliente: int, repo: RepositorioGestion = Depends(get_repo)):
    asign = repo.obtener_asignacion(idcliente)
    if not asign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente sin consultor asignado")
    return asign


@router.post("/consultores/asignar")
def asignar_consultor(payload: AsignacionIn, repo: RepositorioGestion = Depends(get_repo)):
    return repo.asignar_consultor(idcliente=payload.idcliente, consultor_id=payload.consultor_id)


@router.delete("/consultores/asignacion/{idcliente}", status_code=status.HTTP_204_NO_CONTENT)
def desasignar_consultor(idcliente: int, repo: RepositorioGestion = Depends(get_repo)):
    ok = repo.desasignar_consultor(idcliente)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente sin asignacion")
    return None


class AsignacionOut(BaseModel):
    idcliente: int
    consultor_id: int
    consultor_nombre: str
    consultor_estado: Literal['activo', 'inactivo', 'vacaciones']
    consultor_email: Optional[str]


@router.get("/consultores/asignaciones", response_model=List[AsignacionOut])
def listar_asignaciones(repo: RepositorioGestion = Depends(get_repo)):
    return repo.listar_asignaciones()
