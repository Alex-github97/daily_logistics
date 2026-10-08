import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, Date, DateTime, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


class EstadoManifiesto(str, enum.Enum):
    PROGRAMADO = "PROGRAMADO"
    EN_CARGUE = "EN_CARGUE"
    EN_TRANSITO = "EN_TRANSITO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"
    CON_NOVEDAD = "CON_NOVEDAD"


class Manifiesto(Base, TimestampMixin):
    __tablename__ = "manifiestos"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(50), unique=True, nullable=False, index=True)
    vehiculo_id = Column(Integer, ForeignKey("vehiculos.id"), nullable=False)
    conductor_id = Column(Integer, ForeignKey("conductores.id"), nullable=True)
    origen_id = Column(Integer, ForeignKey("ubicaciones.id"), nullable=False)
    destino_id = Column(Integer, ForeignKey("ubicaciones.id"), nullable=False)
    cliente_nombre = Column(String(300), nullable=True)
    cliente_nit = Column(String(30), nullable=True)
    fecha_programada = Column(Date, nullable=False)
    fecha_salida = Column(DateTime(timezone=True), nullable=True)
    fecha_llegada = Column(DateTime(timezone=True), nullable=True)
    estado = Column(Enum(EstadoManifiesto), nullable=False, default=EstadoManifiesto.PROGRAMADO)
    total_estibas_cargadas = Column(Integer, default=0)
    total_estibas_descargadas = Column(Integer, default=0)
    observaciones = Column(Text, nullable=True)
    numero_sap = Column(String(80), nullable=True)
    usuario_creacion_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    vehiculo = relationship("Vehiculo", back_populates="manifiestos")
    conductor = relationship("Conductor", back_populates="manifiestos")
    origen = relationship("Ubicacion", foreign_keys=[origen_id])
    destino = relationship("Ubicacion", foreign_keys=[destino_id])
    usuario_creacion = relationship("Usuario")
    movimientos = relationship("Movimiento", back_populates="manifiesto")
    historial = relationship("ManifiestoHistorial", back_populates="manifiesto", order_by="ManifiestoHistorial.fecha.desc()")


class TipoCambioEstado(str, enum.Enum):
    AVANCE    = "AVANCE"     # transición normal hacia adelante
    CORRECCION = "CORRECCION"  # reversión ejecutada por supervisor/admin


class ManifiestoHistorial(Base):
    """Registro inmutable de cada cambio de estado en un manifiesto."""
    __tablename__ = "manifiesto_historial"

    id              = Column(Integer, primary_key=True, index=True)
    manifiesto_id   = Column(Integer, ForeignKey("manifiestos.id", ondelete="CASCADE"), nullable=False, index=True)
    estado_anterior = Column(String(30), nullable=True)   # NULL solo en la creación inicial
    estado_nuevo    = Column(String(30), nullable=False)
    tipo_cambio     = Column(Enum(TipoCambioEstado), nullable=False, default=TipoCambioEstado.AVANCE)
    observacion     = Column(Text, nullable=True)          # obligatorio en correcciones
    usuario_id      = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha           = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    manifiesto = relationship("Manifiesto", back_populates="historial")
    usuario    = relationship("Usuario")
