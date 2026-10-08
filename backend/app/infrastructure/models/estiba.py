import enum
from sqlalchemy import (
    Column, Integer, String, Boolean, Enum, Float, Date, Text,
    ForeignKey, DateTime, JSON, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


class EstadoEstiba(str, enum.Enum):
    DISPONIBLE = "DISPONIBLE"
    EN_TRANSITO = "EN_TRANSITO"
    CARGADA = "CARGADA"
    EN_CLIENTE = "EN_CLIENTE"
    PENDIENTE_RETORNO = "PENDIENTE_RETORNO"
    EN_REPARACION = "EN_REPARACION"
    DANADA = "DANADA"
    FALTANTE = "FALTANTE"
    PERDIDA = "PERDIDA"
    BAJA = "BAJA"
    DISPOSICION_FINAL = "DISPOSICION_FINAL"
    EN_INVENTARIO = "EN_INVENTARIO"


class TipoPropietario(str, enum.Enum):
    PROPIA = "PROPIA"
    ALQUILADA = "ALQUILADA"
    CLIENTE = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"
    TERCERO = "TERCERO"


class TipoEstiba(str, enum.Enum):
    MADERA = "MADERA"
    PLASTICO = "PLASTICO"
    METAL = "METAL"
    CARTON = "CARTON"
    MIXTA = "MIXTA"


class MaterialEstiba(str, enum.Enum):
    MADERA_PINO = "MADERA_PINO"
    MADERA_EUCALIPTO = "MADERA_EUCALIPTO"
    PLASTICO_HDPE = "PLASTICO_HDPE"
    ACERO = "ACERO"
    ALUMINIO = "ALUMINIO"
    CARTON_CORRUGADO = "CARTON_CORRUGADO"


class NivelDano(str, enum.Enum):
    LEVE = "LEVE"
    MODERADO = "MODERADO"
    GRAVE = "GRAVE"
    TOTAL = "TOTAL"


class Estiba(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "estibas"

    id = Column(Integer, primary_key=True, index=True)
    codigo_interno = Column(String(80), unique=True, nullable=False, index=True)
    codigo_qr = Column(Text, nullable=True, unique=True)
    codigo_rfid = Column(String(200), nullable=True, unique=True, index=True)
    codigo_sap = Column(String(80), nullable=True, index=True)

    tipo = Column(Enum(TipoEstiba), nullable=False, default=TipoEstiba.MADERA)
    material = Column(Enum(MaterialEstiba), nullable=False, default=MaterialEstiba.MADERA_PINO)
    largo_cm = Column(Float, default=120.0)
    ancho_cm = Column(Float, default=100.0)
    alto_cm = Column(Float, default=15.0)
    peso_kg = Column(Float, default=25.0)
    capacidad_carga_kg = Column(Float, default=1000.0)

    tipo_propietario = Column(Enum(TipoPropietario), nullable=False, default=TipoPropietario.PROPIA)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=True)
    contrato_id = Column(Integer, ForeignKey("contratos.id"), nullable=True)

    estado = Column(Enum(EstadoEstiba), nullable=False, default=EstadoEstiba.EN_INVENTARIO, index=True)
    ubicacion_actual_id = Column(Integer, ForeignKey("ubicaciones.id"), nullable=True, index=True)

    fecha_ingreso = Column(Date, nullable=False)
    fecha_fabricacion = Column(Date, nullable=True)
    vida_util_anos = Column(Integer, default=5)

    valor_compra = Column(Float, nullable=True)
    valor_actual = Column(Float, nullable=True)
    moneda = Column(String(10), default="COP")

    nivel_dano = Column(Enum(NivelDano), nullable=True)
    observaciones = Column(Text, nullable=True)

    total_usos = Column(Integer, default=0)
    total_km_recorridos = Column(Float, default=0.0)

    fotos = Column(JSON, default=list)
    metadatos = Column(JSON, default=dict)

    proveedor = relationship("Proveedor", back_populates="estibas")
    contrato = relationship("Contrato", back_populates="estibas")
    ubicacion_actual = relationship("Ubicacion", back_populates="estibas", foreign_keys=[ubicacion_actual_id])
    movimientos = relationship("Movimiento", back_populates="estiba", order_by="Movimiento.fecha_movimiento.desc()")
    eventos_dano = relationship("EventoDano", back_populates="estiba")
    mantenimientos = relationship("MantenimientoEstiba", back_populates="estiba", order_by="MantenimientoEstiba.fecha.desc()")


class EstibaStockMinimo(Base, TimestampMixin):
    """Configuración del stock mínimo de estibas por bodega y tipo."""
    __tablename__ = "estiba_stock_minimo"
    __table_args__ = (
        UniqueConstraint("ubicacion_id", "tipo_estiba", name="uq_stock_minimo_ubicacion_tipo"),
    )

    id              = Column(Integer, primary_key=True, index=True)
    ubicacion_id    = Column(Integer, ForeignKey("ubicaciones.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo_estiba     = Column(Enum(TipoEstiba), nullable=False)
    cantidad_minima = Column(Integer, nullable=False)
    activo          = Column(Boolean, nullable=False, default=True)

    ubicacion = relationship("Ubicacion")
