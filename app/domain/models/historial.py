from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.config.database import HistorialBase


class HistorialFactura(HistorialBase):
    __tablename__ = "historial_facturas"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identificación mínima de la factura (según datos que devuelve la API)
    tercero = Column(String(50), index=True, nullable=False)
    tipo = Column(String(10), nullable=False)
    asiento = Column(String(50), nullable=False)

    # Cambio de estado
    estado_anterior = Column(String(20), nullable=True)  # p.ej. 'impagada'
    estado_nuevo = Column(String(20), nullable=False)    # p.ej. 'pagada' | 'aplazada'

    # Motivo y metadatos
    motivo = Column(Text, nullable=True)
    nueva_fecha = Column(String(20), nullable=True)  # ISO-8601 opcional, si aplazado
    usuario = Column(String(100), nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)

