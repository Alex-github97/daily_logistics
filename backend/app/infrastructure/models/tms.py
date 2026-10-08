"""
Módulo TMS (Transportation Management System) — Modelos de base de datos
Prefijo de tabla: tms_
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, ForeignKey, Text,
    Date, DateTime, UniqueConstraint, Enum as SAEnum, func
)
from sqlalchemy.orm import relationship
from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ─── Enumeraciones ─────────────────────────────────────────────────────────────

class TipoVehiculoTMSEnum(str, enum.Enum):
    MOTOCICLETA       = "MOTOCICLETA"
    AUTOMOVIL         = "AUTOMOVIL"
    CAMIONETA         = "CAMIONETA"
    VAN               = "VAN"
    CAMION_SENCILLO   = "CAMION_SENCILLO"
    DOBLE_TROQUE      = "DOBLE_TROQUE"
    TRACTOCAMION      = "TRACTOCAMION"
    REMOLQUE          = "REMOLQUE"
    SEMIRREMOLQUE     = "SEMIRREMOLQUE"
    CARROTANQUE       = "CARROTANQUE"
    REFRIGERADO       = "REFRIGERADO"
    PLATAFORMA        = "PLATAFORMA"
    PORTACONTENEDOR   = "PORTACONTENEDOR"


class TipoCarroceriaTMSEnum(str, enum.Enum):
    ESTACAS              = "ESTACAS"
    PLANCHA              = "PLANCHA"
    CONTENEDOR           = "CONTENEDOR"
    FURGON               = "FURGON"
    CISTERNA             = "CISTERNA"
    REFRIGERADO_CAR      = "REFRIGERADO_CAR"
    PLATAFORMA_CAR       = "PLATAFORMA_CAR"
    PORTACONTENEDOR_CAR  = "PORTACONTENEDOR_CAR"
    VAIVEN               = "VAIVEN"


class EstadoVehiculoTMSEnum(str, enum.Enum):
    DISPONIBLE        = "DISPONIBLE"
    EN_VIAJE          = "EN_VIAJE"
    EN_MANTENIMIENTO  = "EN_MANTENIMIENTO"
    FUERA_SERVICIO    = "FUERA_SERVICIO"


class TipoServicioTMSEnum(str, enum.Enum):
    TERRESTRE_URBANO    = "TERRESTRE_URBANO"
    TERRESTRE_REGIONAL  = "TERRESTRE_REGIONAL"
    TERRESTRE_NACIONAL  = "TERRESTRE_NACIONAL"
    INTERNACIONAL       = "INTERNACIONAL"
    DISTRIBUCION        = "DISTRIBUCION"
    ULTIMA_MILLA        = "ULTIMA_MILLA"
    PRIMERA_MILLA       = "PRIMERA_MILLA"
    CROSS_DOCKING       = "CROSS_DOCKING"
    DEDICADO            = "DEDICADO"
    TERCERIZADO         = "TERCERIZADO"


class EstadoViajeTMSEnum(str, enum.Enum):
    PROGRAMADO  = "PROGRAMADO"
    ASIGNADO    = "ASIGNADO"
    EN_TRANSITO = "EN_TRANSITO"
    ENTREGADO   = "ENTREGADO"
    CERRADO     = "CERRADO"
    CANCELADO   = "CANCELADO"


class TipoParadaTMSEnum(str, enum.Enum):
    ORIGEN             = "ORIGEN"
    PARADA_INTERMEDIA  = "PARADA_INTERMEDIA"
    DESTINO            = "DESTINO"
    CROSS_DOCK         = "CROSS_DOCK"


class EstadoParadaTMSEnum(str, enum.Enum):
    PENDIENTE   = "PENDIENTE"
    EN_CURSO    = "EN_CURSO"
    COMPLETADA  = "COMPLETADA"
    SALTADA     = "SALTADA"


class TipoEventoTMSEnum(str, enum.Enum):
    SALIDA_ORIGEN          = "SALIDA_ORIGEN"
    LLEGADA_PARADA         = "LLEGADA_PARADA"
    SALIDA_PARADA          = "SALIDA_PARADA"
    LLEGADA_DESTINO        = "LLEGADA_DESTINO"
    INCIDENTE              = "INCIDENTE"
    PARADA_NO_PROGRAMADA   = "PARADA_NO_PROGRAMADA"
    RETRASO                = "RETRASO"
    ACTUALIZACION_GPS      = "ACTUALIZACION_GPS"
    DETENCION              = "DETENCION"


class TipoDocumentoTMSEnum(str, enum.Enum):
    REMESA       = "REMESA"
    MANIFIESTO   = "MANIFIESTO"
    CUMPLIDO     = "CUMPLIDO"
    POD          = "POD"
    FACTURA      = "FACTURA"
    SEGURO       = "SEGURO"
    PERMISO      = "PERMISO"
    CARTA_PORTE  = "CARTA_PORTE"


class EstadoDocumentoTMSEnum(str, enum.Enum):
    PENDIENTE  = "PENDIENTE"
    GENERADO   = "GENERADO"
    FIRMADO    = "FIRMADO"
    RECHAZADO  = "RECHAZADO"
    ANULADO    = "ANULADO"


class EstadoLiquidacionTMSEnum(str, enum.Enum):
    BORRADOR   = "BORRADOR"
    PENDIENTE  = "PENDIENTE"
    APROBADA   = "APROBADA"
    PAGADA     = "PAGADA"
    RECHAZADA  = "RECHAZADA"


class NivelAlertaTMSEnum(str, enum.Enum):
    CRITICA  = "CRITICA"
    ALTA     = "ALTA"
    MEDIA    = "MEDIA"
    BAJA     = "BAJA"
    INFO     = "INFO"


class TipoAlertaTMSEnum(str, enum.Enum):
    VENCIMIENTO_DOCUMENTO    = "VENCIMIENTO_DOCUMENTO"
    RETRASO_VIAJE            = "RETRASO_VIAJE"
    SIN_GPS                  = "SIN_GPS"
    VELOCIDAD_EXCESIVA       = "VELOCIDAD_EXCESIVA"
    DESVIO_RUTA              = "DESVIO_RUTA"
    CONDUCTOR_SIN_DESCANSO   = "CONDUCTOR_SIN_DESCANSO"
    VEHICULO_FUERA_SERVICIO  = "VEHICULO_FUERA_SERVICIO"


# ─── Modelos ───────────────────────────────────────────────────────────────────

class TMSZona(Base, TimestampMixin):
    """Zonas geográficas de operación TMS."""
    __tablename__ = "tms_zona"

    id           = Column(Integer, primary_key=True, index=True)
    nombre       = Column(String(200), nullable=False)
    descripcion  = Column(Text, nullable=True)
    ciudades     = Column(Text, nullable=True)   # JSON list serializado como texto
    activo       = Column(Boolean, default=True, nullable=False)


class TMSTipoServicio(Base, TimestampMixin):
    """Catálogo de tipos de servicio TMS."""
    __tablename__ = "tms_tipo_servicio"

    id           = Column(Integer, primary_key=True, index=True)
    nombre       = Column(String(100), nullable=False)
    descripcion  = Column(Text, nullable=True)
    codigo       = Column(String(20), nullable=False, unique=True)
    activo       = Column(Boolean, default=True, nullable=False)


class TMSParametro(Base, TimestampMixin):
    """Los parámetros con que el TMS decide. Solo entran los que algo lee: una
    cifra que se configura y nadie consulta es decoración."""
    __tablename__ = "tms_parametro"

    id           = Column(Integer, primary_key=True, index=True)
    clave        = Column(String(60), nullable=False, unique=True)
    valor        = Column(Float, nullable=False)


class TMSTipoVehiculoCapacidad(Base, TimestampMixin):
    """Capacidad máxima de cada tipo de vehículo (configurable en TMS ›
    Configuración). Un vehículo sin capacidad propia usa la de su tipo; con
    capacidad propia, la menor de las dos: el tipo es el techo."""
    __tablename__ = "tms_tipo_vehiculo_capacidad"

    id           = Column(Integer, primary_key=True)
    tipo         = Column(String(30), nullable=False, unique=True)
    capacidad_kg = Column(Float, nullable=True)
    volumen_m3   = Column(Float, nullable=True)
    activo       = Column(Boolean, nullable=False, default=True)


class TMSVehiculo(Base, TimestampMixin, SoftDeleteMixin):
    """Vehículos registrados en el TMS."""
    __tablename__ = "tms_vehiculo"

    id                = Column(Integer, primary_key=True, index=True)
    placa             = Column(String(15), nullable=False, unique=True, index=True)
    tipo_vehiculo     = Column(
        SAEnum(TipoVehiculoTMSEnum, name="tms_tipo_vehiculo_enum"),
        nullable=False,
    )
    tipo_carroceria   = Column(
        SAEnum(TipoCarroceriaTMSEnum, name="tms_tipo_carroceria_enum"),
        nullable=True,
    )
    marca             = Column(String(80), nullable=True)
    modelo            = Column(String(50), nullable=True)
    anio              = Column(Integer, nullable=True)
    configuracion     = Column(String(100), nullable=True)
    capacidad_kg      = Column(Float, nullable=True)
    volumen_m3        = Column(Float, nullable=True)
    num_ejes          = Column(Integer, nullable=True)
    peso_bruto_kg     = Column(Float, nullable=True)
    estado_operativo  = Column(
        SAEnum(EstadoVehiculoTMSEnum, name="tms_estado_vehiculo_enum"),
        nullable=False,
        default=EstadoVehiculoTMSEnum.DISPONIBLE,
    )
    empresa_id        = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=True)
    flota_vehiculo_id = Column(Integer, ForeignKey("fleet_vehiculos.id"), nullable=True)
    propietario       = Column(String(200), nullable=True)

    # Relationships
    viajes  = relationship("TMSViaje", back_populates="vehiculo")
    alertas = relationship("TMSAlerta", back_populates="vehiculo")


class TMSViaje(Base, TimestampMixin, SoftDeleteMixin):
    """Viaje / trayecto gestionado por el TMS."""
    __tablename__ = "tms_viaje"

    id                         = Column(Integer, primary_key=True, index=True)
    codigo                     = Column(String(30), nullable=False, unique=True, index=True)
    tipo_servicio              = Column(
        SAEnum(TipoServicioTMSEnum, name="tms_tipo_servicio_enum"),
        nullable=False,
    )
    estado                     = Column(
        SAEnum(EstadoViajeTMSEnum, name="tms_estado_viaje_enum"),
        nullable=False,
        default=EstadoViajeTMSEnum.PROGRAMADO,
    )
    vehiculo_id                = Column(Integer, ForeignKey("tms_vehiculo.id"), nullable=True)
    conductor_hcm_id           = Column(Integer, ForeignKey("hcm_conductor.id"), nullable=True)
    conductor_legacy_id        = Column(Integer, ForeignKey("conductores.id"), nullable=True)
    empresa_id                 = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=True)
    generador_id               = Column(Integer, ForeignKey("generadores_carga.id"), nullable=True)
    flete_id                   = Column(Integer, ForeignKey("fletes.id"), nullable=True)
    wms_despacho_id            = Column(Integer, ForeignKey("wms_despachos.id"), nullable=True)
    origen_ciudad              = Column(String(200), nullable=True)
    origen_direccion           = Column(String(300), nullable=True)
    origen_lat                 = Column(Float, nullable=True)
    origen_lng                 = Column(Float, nullable=True)
    destino_ciudad             = Column(String(200), nullable=True)
    destino_direccion          = Column(String(300), nullable=True)
    destino_lat                = Column(Float, nullable=True)
    destino_lng                = Column(Float, nullable=True)
    fecha_programada_cargue    = Column(DateTime(timezone=True), nullable=True)
    fecha_real_cargue          = Column(DateTime(timezone=True), nullable=True)
    fecha_programada_entrega   = Column(DateTime(timezone=True), nullable=True)
    fecha_real_entrega         = Column(DateTime(timezone=True), nullable=True)
    distancia_km               = Column(Float, nullable=True)
    peso_kg                    = Column(Float, nullable=True)
    volumen_m3                 = Column(Float, nullable=True)
    num_entregas               = Column(Integer, nullable=False, default=1)
    descripcion_carga          = Column(Text, nullable=True)
    valor_flete                = Column(Float, nullable=True)
    otif_on_time               = Column(Boolean, nullable=True)
    otif_in_full               = Column(Boolean, nullable=True)
    # Qué faltó cuando la entrega no llegó completa. Sin el motivo, el
    # in-full dice que algo falló pero no qué corregir.
    otif_motivo                = Column(String(300), nullable=True)
    notas                      = Column(Text, nullable=True)
    creado_por_id              = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    # Relationships
    vehiculo     = relationship("TMSVehiculo", back_populates="viajes")
    paradas      = relationship("TMSParada", back_populates="viaje")
    eventos      = relationship("TMSEvento", back_populates="viaje")
    documentos   = relationship("TMSDocumento", back_populates="viaje")
    pod          = relationship("TMSPOD", back_populates="viaje", uselist=False)
    costo        = relationship("TMSCostoViaje", back_populates="viaje", uselist=False)
    liquidacion  = relationship("TMSLiquidacion", back_populates="viaje", uselist=False)
    alertas      = relationship("TMSAlerta", back_populates="viaje")


class TMSParada(Base, TimestampMixin):
    """Paradas dentro de un viaje TMS."""
    __tablename__ = "tms_parada"

    id                       = Column(Integer, primary_key=True, index=True)
    viaje_id                 = Column(Integer, ForeignKey("tms_viaje.id"), nullable=False)
    secuencia                = Column(Integer, nullable=False)
    tipo                     = Column(
        SAEnum(TipoParadaTMSEnum, name="tms_tipo_parada_enum"),
        nullable=False,
    )
    ciudad                   = Column(String(200), nullable=False)
    direccion                = Column(String(300), nullable=True)
    lat                      = Column(Float, nullable=True)
    lng                      = Column(Float, nullable=True)
    estado                   = Column(
        SAEnum(EstadoParadaTMSEnum, name="tms_estado_parada_enum"),
        nullable=False,
        default=EstadoParadaTMSEnum.PENDIENTE,
    )
    tiempo_estimado_llegada  = Column(DateTime(timezone=True), nullable=True)
    tiempo_real_llegada      = Column(DateTime(timezone=True), nullable=True)
    tiempo_estimado_salida   = Column(DateTime(timezone=True), nullable=True)
    tiempo_real_salida       = Column(DateTime(timezone=True), nullable=True)
    contacto                 = Column(String(150), nullable=True)
    telefono_contacto        = Column(String(30), nullable=True)
    observaciones            = Column(Text, nullable=True)

    # Relationships
    viaje = relationship("TMSViaje", back_populates="paradas")


class TMSEvento(Base, TimestampMixin):
    """Eventos de trazabilidad registrados durante un viaje."""
    __tablename__ = "tms_evento"

    id                 = Column(Integer, primary_key=True, index=True)
    viaje_id           = Column(Integer, ForeignKey("tms_viaje.id"), nullable=False)
    parada_id          = Column(Integer, ForeignKey("tms_parada.id"), nullable=True)
    tipo_evento        = Column(
        SAEnum(TipoEventoTMSEnum, name="tms_tipo_evento_enum"),
        nullable=False,
    )
    descripcion        = Column(Text, nullable=True)
    lat                = Column(Float, nullable=True)
    lng                = Column(Float, nullable=True)
    velocidad_kmh      = Column(Float, nullable=True)
    timestamp          = Column(DateTime(timezone=True), nullable=False, default=func.now())
    datos_adicionales  = Column(Text, nullable=True)
    registrado_por_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    # Relationships
    viaje = relationship("TMSViaje", back_populates="eventos")


class TMSDocumento(Base, TimestampMixin):
    """Documentos asociados a un viaje TMS."""
    __tablename__ = "tms_documento"

    id              = Column(Integer, primary_key=True, index=True)
    viaje_id        = Column(Integer, ForeignKey("tms_viaje.id"), nullable=False)
    tipo_documento  = Column(
        SAEnum(TipoDocumentoTMSEnum, name="tms_tipo_documento_enum"),
        nullable=False,
    )
    numero          = Column(String(100), nullable=True)
    fecha_emision   = Column(Date, nullable=True)
    archivo_url     = Column(String(500), nullable=True)
    estado          = Column(
        SAEnum(EstadoDocumentoTMSEnum, name="tms_estado_documento_enum"),
        nullable=False,
        default=EstadoDocumentoTMSEnum.PENDIENTE,
    )
    observaciones   = Column(Text, nullable=True)

    # Relationships
    viaje = relationship("TMSViaje", back_populates="documentos")


class TMSPOD(Base, TimestampMixin):
    """Prueba de entrega (Proof of Delivery) de un viaje."""
    __tablename__ = "tms_pod"

    id                  = Column(Integer, primary_key=True, index=True)
    viaje_id            = Column(Integer, ForeignKey("tms_viaje.id"), nullable=False, unique=True)
    parada_id           = Column(Integer, ForeignKey("tms_parada.id"), nullable=True)
    receptor_nombre     = Column(String(200), nullable=True)
    receptor_documento  = Column(String(50), nullable=True)
    firma_url           = Column(String(500), nullable=True)
    foto_url            = Column(String(500), nullable=True)
    foto_url2           = Column(String(500), nullable=True)
    lat                 = Column(Float, nullable=True)
    lng                 = Column(Float, nullable=True)
    fecha_hora          = Column(DateTime(timezone=True), nullable=True)
    observaciones       = Column(Text, nullable=True)
    registrado_por_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    # Relationships
    viaje = relationship("TMSViaje", back_populates="pod")


class TMSRuta(Base, TimestampMixin):
    """Rutas predefinidas para operaciones TMS."""
    __tablename__ = "tms_ruta"

    id                     = Column(Integer, primary_key=True, index=True)
    nombre                 = Column(String(200), nullable=False)
    codigo                 = Column(String(30), nullable=True, unique=True)
    origen                 = Column(String(200), nullable=False)
    destino                = Column(String(200), nullable=False)
    distancia_km           = Column(Float, nullable=True)
    tiempo_estimado_min    = Column(Integer, nullable=True)
    tipo_servicio          = Column(
        SAEnum(TipoServicioTMSEnum, name="tms_ruta_tipo_servicio_enum"),
        nullable=True,
    )
    costo_referencia       = Column(Float, nullable=True)
    activo                 = Column(Boolean, default=True, nullable=False)

    # Relationships
    puntos = relationship("TMSPuntoRuta", back_populates="ruta")


class TMSPuntoRuta(Base, TimestampMixin):
    """Puntos intermedios de una ruta TMS."""
    __tablename__ = "tms_punto_ruta"

    id                       = Column(Integer, primary_key=True, index=True)
    ruta_id                  = Column(Integer, ForeignKey("tms_ruta.id"), nullable=False)
    secuencia                = Column(Integer, nullable=False)
    ciudad                   = Column(String(200), nullable=False)
    lat                      = Column(Float, nullable=True)
    lng                      = Column(Float, nullable=True)
    tipo                     = Column(
        SAEnum(TipoParadaTMSEnum, name="tms_punto_tipo_enum"),
        nullable=True,
    )
    tiempo_estimado_minutos  = Column(Integer, nullable=True)

    # Relationships
    ruta = relationship("TMSRuta", back_populates="puntos")


class TMSCostoViaje(Base, TimestampMixin):
    """Desglose de costos de un viaje TMS."""
    __tablename__ = "tms_costo_viaje"

    id                    = Column(Integer, primary_key=True, index=True)
    viaje_id              = Column(Integer, ForeignKey("tms_viaje.id"), nullable=False, unique=True)
    combustible           = Column(Float, nullable=False, default=0)
    peajes                = Column(Float, nullable=False, default=0)
    viaticos              = Column(Float, nullable=False, default=0)
    horas_extras          = Column(Float, nullable=False, default=0)
    mantenimiento         = Column(Float, nullable=False, default=0)
    costos_indirectos     = Column(Float, nullable=False, default=0)
    valor_flete_cobrado   = Column(Float, nullable=False, default=0)
    costo_total           = Column(Float, nullable=False, default=0)
    costo_por_km          = Column(Float, nullable=False, default=0)
    costo_por_entrega     = Column(Float, nullable=False, default=0)
    margen                = Column(Float, nullable=False, default=0)
    notas                 = Column(Text, nullable=True)

    # Relationships
    viaje = relationship("TMSViaje", back_populates="costo")


class TMSLiquidacion(Base, TimestampMixin):
    """Liquidación de pago a conductor por viaje TMS."""
    __tablename__ = "tms_liquidacion"

    id                   = Column(Integer, primary_key=True, index=True)
    viaje_id             = Column(Integer, ForeignKey("tms_viaje.id"), nullable=False, unique=True)
    conductor_hcm_id     = Column(Integer, ForeignKey("hcm_conductor.id"), nullable=True)
    conductor_legacy_id  = Column(Integer, ForeignKey("conductores.id"), nullable=True)
    periodo              = Column(String(50), nullable=True)
    valor_flete          = Column(Float, nullable=False, default=0)
    bonificaciones       = Column(Float, nullable=False, default=0)
    descuentos           = Column(Float, nullable=False, default=0)
    anticipos            = Column(Float, nullable=False, default=0)
    total_a_pagar        = Column(Float, nullable=False, default=0)
    estado               = Column(
        SAEnum(EstadoLiquidacionTMSEnum, name="tms_estado_liquidacion_enum"),
        nullable=False,
        default=EstadoLiquidacionTMSEnum.BORRADOR,
    )
    pagado_en            = Column(DateTime(timezone=True), nullable=True)
    aprobado_por_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    notas                = Column(Text, nullable=True)

    # Relationships
    viaje = relationship("TMSViaje", back_populates="liquidacion")


class TMSOTIFRegistro(Base, TimestampMixin):
    """Registro OTIF (On Time In Full) por viaje."""
    __tablename__ = "tms_otif_registro"

    id            = Column(Integer, primary_key=True, index=True)
    viaje_id      = Column(Integer, ForeignKey("tms_viaje.id"), nullable=False, unique=True)
    fecha         = Column(Date, nullable=False)
    on_time       = Column(Boolean, nullable=False, default=False)
    in_full       = Column(Boolean, nullable=False, default=False)
    otif          = Column(Boolean, nullable=False, default=False)
    cliente       = Column(String(200), nullable=True)
    ruta          = Column(String(200), nullable=True)
    observaciones = Column(Text, nullable=True)


class TMSAlerta(Base, TimestampMixin):
    """Alertas operativas TMS para vehículos, conductores y viajes."""
    __tablename__ = "tms_alerta"

    id            = Column(Integer, primary_key=True, index=True)
    tipo          = Column(
        SAEnum(TipoAlertaTMSEnum, name="tms_tipo_alerta_enum"),
        nullable=False,
    )
    nivel         = Column(
        SAEnum(NivelAlertaTMSEnum, name="tms_nivel_alerta_enum"),
        nullable=False,
    )
    mensaje       = Column(Text, nullable=False)
    viaje_id      = Column(Integer, ForeignKey("tms_viaje.id"), nullable=True)
    vehiculo_id   = Column(Integer, ForeignKey("tms_vehiculo.id"), nullable=True)
    conductor_id  = Column(Integer, ForeignKey("hcm_conductor.id"), nullable=True)
    leida         = Column(Boolean, nullable=False, default=False)
    fecha_alerta  = Column(DateTime(timezone=True), nullable=False, default=func.now())

    # Relationships
    viaje    = relationship("TMSViaje", back_populates="alertas")
    vehiculo = relationship("TMSVehiculo", back_populates="alertas")


class TMSKPIDiario(Base, TimestampMixin):
    """KPIs diarios agregados por empresa para el TMS."""
    __tablename__ = "tms_kpi_diario"
    __table_args__ = (
        UniqueConstraint("empresa_id", "fecha", name="uq_tms_kpi_empresa_fecha"),
    )

    id                    = Column(Integer, primary_key=True, index=True)
    empresa_id            = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=True)
    fecha                 = Column(Date, nullable=False)
    viajes_programados    = Column(Integer, nullable=False, default=0)
    viajes_completados    = Column(Integer, nullable=False, default=0)
    viajes_cancelados     = Column(Integer, nullable=False, default=0)
    on_time_rate          = Column(Float, nullable=False, default=0)
    in_full_rate          = Column(Float, nullable=False, default=0)
    otif_rate             = Column(Float, nullable=False, default=0)
    costo_promedio_km     = Column(Float, nullable=False, default=0)
    km_recorridos         = Column(Float, nullable=False, default=0)
    km_vacios             = Column(Float, nullable=False, default=0)
    utilizacion_flota     = Column(Float, nullable=False, default=0)
    conductores_activos   = Column(Integer, nullable=False, default=0)
