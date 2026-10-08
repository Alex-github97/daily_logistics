import enum
from sqlalchemy import Column, Integer, String, Boolean, Enum, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


class TipoVehiculo(str, enum.Enum):
    CAMION = "CAMION"
    TRACTOMULA = "TRACTOMULA"
    FURGON = "FURGON"
    CAMIONETA = "CAMIONETA"
    MULA = "MULA"
    TURBO = "TURBO"
    PATINETA = "PATINETA"


class EstadoVehiculo(str, enum.Enum):
    DISPONIBLE = "DISPONIBLE"
    EN_RUTA = "EN_RUTA"
    MANTENIMIENTO = "MANTENIMIENTO"
    INACTIVO = "INACTIVO"


class Transportadora(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "transportadoras"

    id = Column(Integer, primary_key=True, index=True)
    nit = Column(String(30), unique=True, nullable=False, index=True)
    razon_social = Column(String(300), nullable=False)
    nombre_comercial = Column(String(300), nullable=True)
    contacto = Column(String(150), nullable=True)
    telefono = Column(String(30), nullable=True)
    email = Column(String(200), nullable=True)
    ciudad = Column(String(100), nullable=True)

    vehiculos = relationship("Vehiculo", back_populates="transportadora")


class Conductor(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "conductores"

    id = Column(Integer, primary_key=True, index=True)
    cedula = Column(String(30), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    telefono = Column(String(30), nullable=True)
    licencia = Column(String(50), nullable=True)
    transportadora_id = Column(Integer, ForeignKey("transportadoras.id"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, unique=True)

    transportadora = relationship("Transportadora")
    manifiestos = relationship("Manifiesto", back_populates="conductor")
    usuario = relationship("Usuario")
    vehiculos_flete = relationship("VehiculoFlete", back_populates="conductor")
    fletes = relationship("Flete", back_populates="conductor")
    enturnamiento = relationship("Enturnamiento", back_populates="conductor")


class Vehiculo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "vehiculos"

    id = Column(Integer, primary_key=True, index=True)
    placa = Column(String(15), unique=True, nullable=False, index=True)
    tipo = Column(Enum(TipoVehiculo), nullable=False)
    marca = Column(String(80), nullable=True)
    modelo = Column(String(50), nullable=True)
    capacidad_estibas = Column(Integer, nullable=True)
    capacidad_carga_kg = Column(Float, nullable=True)
    transportadora_id = Column(Integer, ForeignKey("transportadoras.id"), nullable=True)
    estado = Column(Enum(EstadoVehiculo), default=EstadoVehiculo.DISPONIBLE)
    observaciones = Column(Text, nullable=True)

    transportadora = relationship("Transportadora", back_populates="vehiculos")
    manifiestos = relationship("Manifiesto", back_populates="vehiculo")


