from typing import List, Optional
from datetime import date
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas
from app.application.obtener_facturas_filtradas import categorizar_estado


class ObtenerFacturasNegativas:
    def __init__(self, repo: RepositorioFacturas):
        self.repo = repo

    def execute(
        self,
        sociedad: Optional[str] = None,
        tercero: Optional[str] = None,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        nivel_reclamacion: Optional[int] = None,
    ) -> List[dict]:
        """
        Obtiene la lista de facturas con saldo negativo (el grupo debe dinero al cliente).
        """
        facturas = self.repo.obtener_facturas_negativas(
            sociedad=sociedad,
            tercero=tercero,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            nivel_reclamacion=nivel_reclamacion,
        )

        resultado: List[dict] = []
        for factura in facturas:
            estado = categorizar_estado(factura)
            resultado.append({**factura, "estado": estado})
        return resultado

