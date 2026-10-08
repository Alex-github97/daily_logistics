import enum
from sqlalchemy import Column, Integer, String, Float, Date, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


class TipoMantenimiento(str, enum.Enum):
    PREVENTIVO = "PREVENTIVO"
    CORRECTIVO = "CORRECTIVO"
    REPARACION = "REPARACION"
    INSPECCION = "INSPECCION"
    LIMPIEZA = "LIMPIEZA"
    PINTURA = "PINTURA"
    REFUERZO = "REFUERZO"


class MantenimientoEstiba(Base, TimestampMixin):
    __tablename__ = "mantenimientos_estiba"

    id = Column(Integer, primary_key=True, index=True)
    estiba_id = Column(Integer, ForeignKey("estibas.id"), nullable=False, index=True)
    fecha = Column(Date, nullable=False)
    tipo = Column(Enum(TipoMantenimiento), nullable=False)
    descripcion = Column(Text, nullable=True)
    costo = Column(Float, nullable=False, default=0.0)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    estiba = relationship("Estiba", back_populates="mantenimientos")
    proveedor = relationship("Proveedor")
    usuario = relationship("Usuario")
