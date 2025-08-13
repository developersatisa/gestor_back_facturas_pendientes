import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_get_facturas(client, monkeypatch):
    class FakeRepo:
        def obtener_facturas(self, **kwargs):
            from app.domain.models.Factura import Factura
            from datetime import date
            return [
                Factura(tipo="AB", asiento="1", sociedad="S1", planta="P1", moneda="EUR", colectivo="C1", tercero="T1", vencimiento=date.today(), forma_pago="FP", sentido="D", importe=100.0, pago=0.0, nivel_reclamacion=2, fecha_reclamacion=None, check_pago=False),
            ]
    from app.interfaces.facturas_controller import get_repo
    monkeypatch.setattr("app.interfaces.facturas_controller.get_repo", lambda: FakeRepo())
    response = client.get("/api/facturas?sociedad=S1")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["sociedad"] == "S1" 