import enum
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, Float, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


class TipoVehiculoFlete(str, enum.Enum):
    TRACTOCAMION = "TRACTOCAMION"
    CAMION_SENCILLO = "CAMION_SENCILLO"
    DOBLETROQUE = "DOBLETROQUE"
    PATINETA = "PATINETA"
    TURBO = "TURBO"


class TipoCarroceria(str, enum.Enum):
    ESTACAS = "ESTACAS"
    PLANCHA = "PLANCHA"
    CONTENEDOR = "CONTENEDOR"
    FURGON = "FURGON"
    CISTERNA = "CISTERNA"
    REFRIGERADO = "REFRIGERADO"
    PLATAFORMA = "PLATAFORMA"


class EstadoFlete(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    ASIGNADO = "ASIGNADO"
    EN_CURSO = "EN_CURSO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


class EstadoEnturnamiento(str, enum.Enum):
    ACTIVO = "ACTIVO"
    ASIGNADO = "ASIGNADO"
    INACTIVO = "INACTIVO"


class GeneradorCarga(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "generadores_carga"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(300), nullable=False)
    nit = Column(String(30), nullable=True, index=True)
    contacto = Column(String(150), nullable=True)
    telefono = Column(String(30), nullable=True)
    email = Column(String(200), nullable=True)
    ciudad = Column(String(100), nullable=True)

    fletes = relationship("Flete", back_populates="generador")


class VehiculoFlete(Base, TimestampMixin, SoftDeleteMixin):
    """Vehículos registrados por conductores para el módulo de fletes.
    Independiente de la tabla 'vehiculos' usada en manifiestos."""
    __tablename__ = "vehiculos_flete"

    id = Column(Integer, primary_key=True, index=True)
    conductor_id = Column(Integer, ForeignKey("conductores.id"), nullable=False, index=True)
    placa = Column(String(15), nullable=False, index=True)
    tipo_vehiculo = Column(String(30), nullable=False)
    tipo_carroceria = Column(String(30), nullable=True)
    marca = Column(String(80), nullable=True)
    modelo = Column(String(50), nullable=True)
    anio = Column(Integer, nullable=True)
    capacidad_kg = Column(Float, nullable=True)
    observaciones = Column(Text, nullable=True)

    conductor = relationship("Conductor", back_populates="vehiculos_flete")
    fletes = relationship("Flete", back_populates="vehiculo_flete")


class Flete(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fletes"

    id = Column(Integer, primary_key=True, index=True)
    ciudad_origen = Column(String(150), nullable=False)
    ciudad_destino = Column(String(150), nullable=False)
    tipo_vehiculo = Column(String(30), nullable=False)
    tipo_carroceria = Column(String(30), nullable=True)
    generador_id = Column(Integer, ForeignKey("generadores_carga.id"), nullable=True)
    descripcion_carga = Column(String(500), nullable=True)
    peso_kg = Column(Float, nullable=True)
    distancia_km = Column(Float, nullable=True)
    num_entregas = Column(Integer, nullable=True, default=1)
    fecha_hora_cargue = Column(DateTime(timezone=True), nullable=False)
    fecha_hora_entrega = Column(DateTime(timezone=True), nullable=True)
    valor_flete = Column(Float, nullable=True)
    es_negociable = Column(Boolean, default=False)
    estado = Column(String(20), default=EstadoFlete.PENDIENTE.value, nullable=False)
    conductor_id = Column(Integer, ForeignKey("conductores.id"), nullable=True)
    vehiculo_flete_id = Column(Integer, ForeignKey("vehiculos_flete.id"), nullable=True)
    notas = Column(Text, nullable=True)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    generador = relationship("GeneradorCarga", back_populates="fletes")
    conductor = relationship("Conductor", back_populates="fletes")
    vehiculo_flete = relationship("VehiculoFlete", back_populates="fletes")
    creado_por = relationship("Usuario")


class Enturnamiento(Base, TimestampMixin, SoftDeleteMixin):
    """Cola de conductores disponibles sin viaje asignado."""
    __tablename__ = "enturnamiento"

    id = Column(Integer, primary_key=True, index=True)
    conductor_id = Column(Integer, ForeignKey("conductores.id"), nullable=False, index=True)
    ciudad_disponible = Column(String(150), nullable=False)
    fecha_hora_disponible = Column(DateTime(timezone=True), nullable=False)
    tipo_vehiculo = Column(String(30), nullable=True)
    tipo_carroceria = Column(String(30), nullable=True)
    estado = Column(String(20), default=EstadoEnturnamiento.ACTIVO.value, nullable=False)
    flete_asignado_id = Column(Integer, ForeignKey("fletes.id"), nullable=True)
    notas = Column(Text, nullable=True)

    conductor = relationship("Conductor", back_populates="enturnamiento")
    flete_asignado = relationship("Flete")
