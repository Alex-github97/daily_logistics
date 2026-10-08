import enum
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Text, Float, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


class TipoMovimiento(str, enum.Enum):
    CARGA = "CARGA"
    DESCARGA = "DESCARGA"
    TRANSFERENCIA = "TRANSFERENCIA"
    RETORNO = "RETORNO"
    RECEPCION = "RECEPCION"
    INVENTARIO = "INVENTARIO"
    REPARACION = "REPARACION"
    BAJA = "BAJA"
    DISPOSICION_FINAL = "DISPOSICION_FINAL"
    INSPECCION = "INSPECCION"


class Movimiento(Base, TimestampMixin):
    __tablename__ = "movimientos"

    id = Column(Integer, primary_key=True, index=True)
    estiba_id = Column(Integer, ForeignKey("estibas.id"), nullable=False, index=True)
    tipo = Column(Enum(TipoMovimiento), nullable=False, index=True)

    ubicacion_origen_id = Column(Integer, ForeignKey("ubicaciones.id"), nullable=True)
    ubicacion_destino_id = Column(Integer, ForeignKey("ubicaciones.id"), nullable=True)

    vehiculo_id = Column(Integer, ForeignKey("vehiculos.id"), nullable=True)
    manifiesto_id = Column(Integer, ForeignKey("manifiestos.id"), nullable=True)
    conductor_id = Column(Integer, ForeignKey("conductores.id"), nullable=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)

    fecha_movimiento = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)

    observaciones = Column(Text, nullable=True)
    fotos = Column(JSON, default=list)
    metadatos = Column(JSON, default=dict)

    estado_estiba_antes = Column(String(50), nullable=True)
    estado_estiba_despues = Column(String(50), nullable=True)

    estiba = relationship("Estiba", back_populates="movimientos")
    ubicacion_origen = relationship("Ubicacion", foreign_keys=[ubicacion_origen_id])
    ubicacion_destino = relationship("Ubicacion", foreign_keys=[ubicacion_destino_id])
    vehiculo = relationship("Vehiculo")
    manifiesto = relationship("Manifiesto", back_populates="movimientos")
    conductor = relationship("Conductor")
    usuario = relationship("Usuario")
