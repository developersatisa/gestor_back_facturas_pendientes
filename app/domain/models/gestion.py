from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text
from app.config.database import GestionBase
from sqlalchemy.ext.declarative import declarative_base


class Consultor(GestionBase):
    __tablename__ = "consultores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    # estado: 'activo' | 'inactivo' | 'vacaciones'
    estado = Column(String(20), nullable=False, default="activo")
    email = Column(String(255), nullable=True)
    # Campos de Teams eliminados: usar email como UPN para Teams
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)

    # RelaciÃ³n ORM omitida para evitar crear claves forÃ¡neas en BD


class ClienteConsultor(GestionBase):
    __tablename__ = "cliente_consultor"

    id = Column(Integer, primary_key=True, autoincrement=False)
    idcliente = Column(Integer, nullable=False, index=True)
    # Sin clave forÃ¡nea: solo referencia lÃ³gica a consultores.id
    consultor_id = Column(Integer, nullable=False, index=True)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)

    # RelaciÃ³n ORM omitida para evitar crear claves forÃ¡neas en BD


# Nota: FacturaCambio se mapea en una base separada para evitar que create_all la cree automÃ¡ticamente.
GestionOptionalBase = declarative_base()

class FacturaCambio(GestionOptionalBase):
    __tablename__ = "factura_cambios"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # AsociaciÃ³n con cliente y factura
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
    
    # Orden de columnas en BD: id, idcliente, tercero, tipo, asiento, accion_tipo, descripcion, aviso, destinatario, envio_estado, consultor_id, usuario, seguimiento_id, enviada_en, creado_en, usuario_modificacion, fecha_modificacion
    # Nota: El orden físico en SQL Server no afecta la funcionalidad, SQLAlchemy usa nombres de columnas

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Asociación con cliente y factura
    idcliente = Column(Integer, index=True, nullable=True)
    tercero = Column(String(50), index=True, nullable=False)
    tipo = Column(String(10), nullable=False)
    asiento = Column(String(50), nullable=False)

    # Datos de la acción
    accion_tipo = Column(String(50), nullable=True)  # p.ej., 'Email', 'Llamada', 'Visita', 'Aplazamiento', etc. Nullable para acciones placeholder
    descripcion = Column(Text, nullable=True)
    aviso = Column(DateTime, nullable=True)
    
    # Estado de notificación
    destinatario = Column(String(255), nullable=True)
    envio_estado = Column(String(50), nullable=True)  # p.ej., 'enviada', 'fallo'
    
    # Usuario y consultor
    consultor_id = Column(Integer, nullable=True)
    usuario = Column(String(100), nullable=True)
    
    # Seguimiento (grupo lógico de acciones masivas)
    seguimiento_id = Column(Integer, nullable=True)
    
    # Timestamps
    enviada_en = Column(DateTime, nullable=True)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Auditoría
    usuario_modificacion = Column(String(100), nullable=True)
    fecha_modificacion = Column(DateTime, nullable=True)

    # Sin restricciones adicionales


class SeguimientoAcciones(GestionBase):
    __tablename__ = "seguimiento_acciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)


class Seguimiento(GestionBase):
    __tablename__ = "seguimientos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    idcliente = Column(Integer, index=True, nullable=True)
    tercero = Column(String(50), index=True, nullable=False)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)
    usuario = Column(String(100), nullable=True)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)


class SeguimientoFactura(GestionBase):
    __tablename__ = "seguimiento_facturas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seguimiento_id = Column(Integer, index=True, nullable=False)
    # referencia a factura
    tipo = Column(String(10), nullable=False)
    asiento = Column(String(50), nullable=False)
    # opcionalmente guardar importes para totales rápidos
    importe = Column(Numeric(18, 2), nullable=True)
    pendiente = Column(Numeric(18, 2), nullable=True)
    creado_en = Column(DateTime, nullable=False, default=datetime.utcnow)

