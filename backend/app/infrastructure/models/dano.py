import enum
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Text, Float, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


class ResponsableDano(str, enum.Enum):
    CLIENTE = "CLIENTE"
    TRANSPORTADORA = "TRANSPORTADORA"
    PROVEEDOR = "PROVEEDOR"
    OPERACION_INTERNA = "OPERACION_INTERNA"
    DESCONOCIDO = "DESCONOCIDO"


class AccionRecomendada(str, enum.Enum):
    REPARAR = "REPARAR"
    DAR_BAJA = "DAR_BAJA"
    DISPOSICION_FINAL = "DISPOSICION_FINAL"
    MONITOREAR = "MONITOREAR"
    REPONER = "REPONER"


class CodigoDano(Base, TimestampMixin):
    __tablename__ = "codigos_dano"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(30), unique=True, nullable=False)
    descripcion = Column(String(300), nullable=False)
    categoria = Column(String(100), nullable=True)
    costo_reparacion_promedio = Column(Float, nullable=True)
    activo = Column(Integer, default=1)

    eventos = relationship("EventoDano", back_populates="codigo_dano")


class EventoDano(Base, TimestampMixin):
    __tablename__ = "eventos_dano"

    id = Column(Integer, primary_key=True, index=True)
    estiba_id = Column(Integer, ForeignKey("estibas.id"), nullable=False, index=True)
    codigo_dano_id = Column(Integer, ForeignKey("codigos_dano.id"), nullable=False)
    nivel_dano = Column(String(20), nullable=False)
    responsable = Column(Enum(ResponsableDano), nullable=False, default=ResponsableDano.DESCONOCIDO)
    accion_recomendada = Column(Enum(AccionRecomendada), nullable=True)
    descripcion_detalle = Column(Text, nullable=True)
    costo_reparacion = Column(Float, nullable=True)
    costo_reposicion = Column(Float, nullable=True)
    fotos = Column(JSON, default=list)
    fecha_evento = Column(DateTime(timezone=True), server_default=func.now())
    fecha_reparacion = Column(DateTime(timezone=True), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    resuelto = Column(Integer, default=0)

    estiba = relationship("Estiba", back_populates="eventos_dano")
    codigo_dano = relationship("CodigoDano", back_populates="eventos")
    usuario = relationship("Usuario")
