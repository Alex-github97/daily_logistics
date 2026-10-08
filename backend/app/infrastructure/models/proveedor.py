import enum
from sqlalchemy import Column, Integer, String, Boolean, Enum, Float, Date, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


class TipoProveedor(Base):
    __tablename__ = "tipos_proveedor"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    activo = Column(Boolean, nullable=False, default=True)


class EstadoContrato(str, enum.Enum):
    ACTIVO = "ACTIVO"
    VENCIDO = "VENCIDO"
    SUSPENDIDO = "SUSPENDIDO"
    POR_VENCER = "POR_VENCER"


class Proveedor(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True, index=True)
    nit = Column(String(30), unique=True, nullable=False, index=True)
    razon_social = Column(String(300), nullable=False)
    nombre_comercial = Column(String(300), nullable=True)
    tipo = Column(String(100), nullable=False, default="COMPRA")
    contacto_nombre = Column(String(150), nullable=True)
    contacto_email = Column(String(200), nullable=True)
    contacto_telefono = Column(String(30), nullable=True)
    direccion = Column(String(300), nullable=True)
    ciudad = Column(String(100), nullable=True)
    codigo_sap = Column(String(50), nullable=True, index=True)
    observaciones = Column(Text, nullable=True)

    contratos = relationship("Contrato", back_populates="proveedor")
    estibas = relationship("Estiba", back_populates="proveedor")


class Contrato(Base, TimestampMixin):
    __tablename__ = "contratos"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(100), unique=True, nullable=False, index=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=False)
    tipo = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=True)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=True)
    valor_unitario = Column(Float, nullable=True)
    moneda = Column(String(10), default="COP")
    condiciones_pago = Column(Text, nullable=True)
    estado = Column(Enum(EstadoContrato), nullable=False, default=EstadoContrato.ACTIVO)
    dias_alerta_vencimiento = Column(Integer, default=30)
    documento_url = Column(String(500), nullable=True)
    codigo_sap = Column(String(50), nullable=True)

    proveedor = relationship("Proveedor", back_populates="contratos")
    estibas = relationship("Estiba", back_populates="contrato")


