from typing import List, Optional
from datetime import date
from app.domain.models.Factura import Factura

class EstadoFactura:
    ROJO = "rojo"
    AMARILLO = "amarillo"
    VERDE = "verde"

def categorizar_estado(factura: dict) -> str:
    # Lógica de ejemplo para categorizar estado
    nivel_reclamacion = factura.get('nivel_reclamacion')
    if nivel_reclamacion and nivel_reclamacion >= 3:
        return EstadoFactura.ROJO
    elif nivel_reclamacion == 2:
        return EstadoFactura.AMARILLO
    else:
        return EstadoFactura.VERDE

class ObtenerFacturasFiltradas:
    def __init__(self, repo):
        self.repo = repo

    def execute(
        self,
        sociedad: Optional[str] = None,
        tercero: Optional[str] = None,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        nivel_reclamacion: Optional[int] = None,
    ) -> List[dict]:
        facturas = self.repo.obtener_facturas(
            sociedad=sociedad,
            tercero=tercero,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            nivel_reclamacion=nivel_reclamacion,
        )
        # Excluir TYP_0 'AA', 'ZZ' y categorizar
        resultado = []
        for f in facturas:
            if f.get('tipo') in ("AA", "ZZ"):
                continue
            estado = categorizar_estado(f)
            resultado.append({**f, "estado": estado})
        return resultado 