from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.config.database import get_gestion_db, init_gestion_db, GestionBase, get_clientes_db, get_facturas_db
from app.infrastructure.repositorio_registro_facturas import RepositorioRegistroFacturas
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
from app.infrastructure.repositorio_gestion import RepositorioGestion
from app.infrastructure.data_enrichers import enrich_aviso_with_names
from app.infrastructure.factura_verification import cliente_tiene_facturas_pendientes
from app.utils.error_handlers import handle_error

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
    consultor_id: Optional[int] = None


class AccionFacturaOut(BaseModel):
    id: int
    idcliente: Optional[int]
    tercero: str
    tipo: str
    asiento: str
    accion_tipo: Optional[str]  
    descripcion: Optional[str]
    aviso: Optional[str]
    usuario: Optional[str]
    consultor_id: Optional[int]
    enviada_en: Optional[str]
    destinatario: Optional[str]
    envio_estado: Optional[str]
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


@router.delete("/facturas/acciones/{accion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_accion(accion_id: int, repo: RepositorioRegistroFacturas = Depends(get_repo)):
    try:
        eliminado = repo.eliminar_accion(accion_id)
        if not eliminado:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acción no encontrada")
        return None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error eliminando acción de factura")


class EmitirPendientesOut(BaseModel):
    enviados: int


@router.post("/facturas/acciones/emitir-pendientes", response_model=EmitirPendientesOut)
def emitir_pendientes(fecha: Optional[str] = None, repo: RepositorioRegistroFacturas = Depends(get_repo)):
    try:
        enviados = repo.enviar_pendientes(fecha_iso=fecha)
        return {"enviados": enviados}
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error emitiendo acciones pendientes")


class ProximoAvisoOut(BaseModel):
    id: int
    idcliente: Optional[int]
    tercero: str
    tipo: str
    asiento: str
    accion_tipo: Optional[str]
    descripcion: Optional[str]
    aviso: Optional[str]
    usuario: Optional[str]
    consultor_id: Optional[int]
    consultor_nombre: Optional[str]
    cliente_nombre: Optional[str]
    creado_en: str


def get_repo_clientes(db: Session = Depends(get_clientes_db)):
    return RepositorioClientes(db)

def get_repo_gestion(db: Session = Depends(get_gestion_db)):
    return RepositorioGestion(db)

def get_repo_facturas(db: Session = Depends(get_facturas_db)):
    return RepositorioFacturas(db)


@router.get("/facturas/acciones/proximos-avisos", response_model=List[ProximoAvisoOut])
def listar_proximos_avisos(
    limit: int = 50,
    repo: RepositorioRegistroFacturas = Depends(get_repo),
    repo_clientes: RepositorioClientes = Depends(get_repo_clientes),
    repo_gestion: RepositorioGestion = Depends(get_repo_gestion),
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
):
    """Obtiene los próximos avisos (acciones con fecha de aviso >= hoy) de todos los clientes y consultores.
    Solo incluye avisos de clientes que tienen facturas pendientes."""
    try:
        avisos = repo.listar_proximos_avisos(limit=limit * 2)  # Obtener más para compensar los filtrados
        
        resultado = []
        for aviso in avisos:
            tercero = str(aviso.get('tercero') or aviso.get('idcliente') or '')
            if not tercero:
                continue
            
            # Filtrar: solo avisos de clientes con facturas pendientes
            if not cliente_tiene_facturas_pendientes(repo_facturas, tercero):
                continue
            
            # Enriquecer con nombres de cliente y consultor
            aviso_enriquecido = enrich_aviso_with_names(aviso, repo_clientes, repo_gestion)
            resultado.append(aviso_enriquecido)
            
            # Limitar a la cantidad solicitada
            if len(resultado) >= limit:
                break
        
        return resultado
    except Exception as e:
        raise handle_error(e, "obtener próximos avisos", "Error obteniendo próximos avisos")
