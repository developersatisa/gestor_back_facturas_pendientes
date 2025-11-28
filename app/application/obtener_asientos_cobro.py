from typing import List, Optional
from datetime import date
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas
from app.application.obtener_facturas_filtradas import categorizar_estado


class ObtenerAsientosCobro:
    def __init__(self, repo: RepositorioFacturas):
        self.repo = repo

    def execute(
        self,
        sociedad: Optional[str] = None,
        tercero: Optional[str] = None,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        tipos: Optional[List[str]] = None,
    ) -> List[dict]:
        """
        Obtiene asientos de cobro (p.ej. COB/VTO) para un tercero o una sociedad.
        """
        asientos = self.repo.obtener_asientos_cobro(
            sociedad=sociedad,
            tercero=tercero,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            tipos=tipos,
        )

        resultado: List[dict] = []
        for asiento in asientos:
            estado = categorizar_estado(asiento)
            resultado.append({**asiento, "estado": estado})
        return resultado

