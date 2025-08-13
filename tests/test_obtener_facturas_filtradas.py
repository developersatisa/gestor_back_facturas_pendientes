import pytest
from app.application.obtener_facturas_filtradas import ObtenerFacturasFiltradas
from app.domain.models.Factura import Factura
from datetime import date

class FakeRepo:
    def obtener_facturas(self, **kwargs):
        return [
            Factura(tipo="AB", asiento="1", sociedad="S1", planta="P1", moneda="EUR", colectivo="C1", tercero="T1", vencimiento=date.today(), forma_pago="FP", sentido="D", importe=100.0, pago=0.0, nivel_reclamacion=2, fecha_reclamacion=None, check_pago=False),
            Factura(tipo="AA", asiento="2", sociedad="S1", planta="P1", moneda="EUR", colectivo="C1", tercero="T2", vencimiento=date.today(), forma_pago="FP", sentido="D", importe=200.0, pago=0.0, nivel_reclamacion=3, fecha_reclamacion=None, check_pago=False),
        ]

def test_filtrado_y_estado():
    use_case = ObtenerFacturasFiltradas(FakeRepo())
    result = use_case.execute(sociedad="S1")
    assert len(result) == 1
    assert result[0]["estado"] == "amarillo" 