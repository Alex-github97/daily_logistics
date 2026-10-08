import enum
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Text, Boolean, func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


class TipoAlerta(str, enum.Enum):
    ESTIBA_FUERA_TIEMPO   = "ESTIBA_FUERA_TIEMPO"
    CONTRATO_POR_VENCER   = "CONTRATO_POR_VENCER"
    DANO_RECURRENTE       = "DANO_RECURRENTE"
    DIFERENCIA_INVENTARIO = "DIFERENCIA_INVENTARIO"
    ESTIBA_PERDIDA        = "ESTIBA_PERDIDA"
    MANIFIESTO_RETRASADO  = "MANIFIESTO_RETRASADO"
    CAPACIDAD_BAJA        = "CAPACIDAD_BAJA"
    ESTIBA_FALTANTE       = "ESTIBA_FALTANTE"
    STOCK_BAJO            = "STOCK_BAJO"


class NivelAlerta(str, enum.Enum):
    INFO = "INFO"
    ADVERTENCIA = "ADVERTENCIA"
    CRITICA = "CRITICA"


class Alerta(Base, TimestampMixin):
    __tablename__ = "alertas"

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(Enum(TipoAlerta), nullable=False, index=True)
    nivel = Column(Enum(NivelAlerta), nullable=False, default=NivelAlerta.ADVERTENCIA)
    titulo = Column(String(300), nullable=False)
    descripcion = Column(Text, nullable=True)
    estiba_id = Column(Integer, ForeignKey("estibas.id"), nullable=True)
    manifiesto_id = Column(Integer, ForeignKey("manifiestos.id"), nullable=True)
    contrato_id = Column(Integer, ForeignKey("contratos.id"), nullable=True)
    leida = Column(Boolean, default=False)
    resuelta = Column(Boolean, default=False)
    fecha_resolucion = Column(DateTime(timezone=True), nullable=True)
    usuario_resolucion_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    metadatos = Column(String(2000), nullable=True)

    estiba = relationship("Estiba")
    usuario_resolucion = relationship("Usuario")
