from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, Numeric, Text
from app.config.database import GestionBase
from sqlalchemy.ext.declarative import declarative_base


class Consultor(GestionBase):
    __tablename__ = "consultores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    # estado: 'activo' | 'inactivo' | 'vacaciones'
    estado = Column(String(20), nullable=False, default="activo")
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relación ORM omitida para evitar crear claves foráneas en BD


class ClienteConsultor(GestionBase):
    __tablename__ = "cliente_consultor"

    id = Column(Integer, primary_key=True, autoincrement=True)
    idcliente = Column(Integer, nullable=False, index=True)
    # Sin clave foránea: solo referencia lógica a consultores.id
    consultor_id = Column(Integer, nullable=False, index=True)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relación ORM omitida para evitar crear claves foráneas en BD
    __table_args__ = (
        UniqueConstraint("idcliente", name="uq_cliente_unico"),
    )


# Nota: FacturaCambio se mapea en una base separada para evitar que create_all la cree automáticamente.
GestionOptionalBase = declarative_base()

class FacturaCambio(GestionOptionalBase):
    __tablename__ = "factura_cambios"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Asociación con cliente y factura
    idcliente = Column(Integer, index=True, nullable=True)
    tercero = Column(String(50), index=True, nullable=False)
    tipo = Column(String(10), nullable=False)
    asiento = Column(String(50), nullable=False)

    # Cambios registrados (opcionales si no aplican)
    numero_anterior = Column(String(50), nullable=True)
    numero_nuevo = Column(String(50), nullable=True)

    monto_anterior = Column(Numeric(18, 2), nullable=True)
    monto_nuevo = Column(Numeric(18, 2), nullable=True)

    vencimiento_anterior = Column(DateTime, nullable=True)
    vencimiento_nuevo = Column(DateTime, nullable=True)

    motivo = Column(Text, nullable=True)
    usuario = Column(String(100), nullable=True)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)


class AccionFactura(GestionBase):
    __tablename__ = "factura_acciones"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Asociación con cliente y factura
    idcliente = Column(Integer, index=True, nullable=True)
    tercero = Column(String(50), index=True, nullable=False)
    tipo = Column(String(10), nullable=False)
    asiento = Column(String(50), nullable=False)

    # Datos de la acción
    accion_tipo = Column(String(50), nullable=False)  # p.ej., 'Email', 'Llamada', 'Visita', 'Aplazamiento', etc.
    descripcion = Column(Text, nullable=True)
    aviso = Column(DateTime, nullable=True)
    usuario = Column(String(100), nullable=True)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Sin restricciones adicionales
