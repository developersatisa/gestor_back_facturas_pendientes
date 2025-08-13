from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

class Factura(BaseModel):
    tipo: str = Field(..., alias="tipo")
    asiento: int
    sociedad: str
    planta: str
    moneda: str
    colectivo: str
    tercero: str
    vencimiento: datetime
    forma_pago: str
    sentido: int
    importe: Decimal
    pago: Optional[Decimal] = None
    nivel_reclamacion: Optional[int] = None
    fecha_reclamacion: Optional[datetime] = None
    check_pago: Optional[int] = None 