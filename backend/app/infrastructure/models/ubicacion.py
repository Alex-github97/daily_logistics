import enum
from sqlalchemy import Column, Integer, String, Boolean, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


class TipoUbicacion(str, enum.Enum):
    PLANTA = "PLANTA"
    BODEGA = "BODEGA"
    PATIO = "PATIO"
    CLIENTE = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"
    VEHICULO = "VEHICULO"
    TRANSITO = "TRANSITO"
    DISPOSICION_FINAL = "DISPOSICION_FINAL"
    EXTERNO = "EXTERNO"


class Ubicacion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "ubicaciones"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    tipo = Column(Enum(TipoUbicacion), nullable=False)
    descripcion = Column(Text, nullable=True)
    direccion = Column(String(300), nullable=True)
    ciudad = Column(String(100), nullable=True)
    departamento = Column(String(100), nullable=True)
    pais = Column(String(100), default="Colombia")
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)
    capacidad_estibas = Column(Integer, nullable=True)
    codigo_sap = Column(String(50), nullable=True)
    es_disposicion_final = Column(Boolean, default=False)

    estibas = relationship("Estiba", back_populates="ubicacion_actual", foreign_keys="Estiba.ubicacion_actual_id")
