from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum
from app.infrastructure.models.base import Base, TimestampMixin


# ─── Enums ────────────────────────────────────────────────────────────────────

class TipoPronosticoAPSEnum(enum.Enum):
    ESTADISTICO  = 'ESTADISTICO'
    ML           = 'ML'
    HIBRIDO      = 'HIBRIDO'
    COLABORATIVO = 'COLABORATIVO'
    CONSENSO     = 'CONSENSO'

class MetodoPronosticoAPSEnum(enum.Enum):
    PROMEDIO_MOVIL    = 'PROMEDIO_MOVIL'
    SUAVIZACION_EXP   = 'SUAVIZACION_EXP'
    REGRESION         = 'REGRESION'
    ARIMA             = 'ARIMA'
    LSTM              = 'LSTM'
    ENSEMBLE          = 'ENSEMBLE'

class EstadoPlanAPSEnum(enum.Enum):
    BORRADOR    = 'BORRADOR'
    EN_REVISION = 'EN_REVISION'
    APROBADO    = 'APROBADO'
    PUBLICADO   = 'PUBLICADO'
    ARCHIVADO   = 'ARCHIVADO'

class TipoPlanAPSEnum(enum.Enum):
    MPS     = 'MPS'
    MRP     = 'MRP'
    CRP     = 'CRP'
    DRP     = 'DRP'
    TRP     = 'TRP'
    S_AND_OP = 'S_AND_OP'
    IBP     = 'IBP'

class HorizontePlanAPSEnum(enum.Enum):
    SEMANAL     = 'SEMANAL'
    MENSUAL     = 'MENSUAL'
    TRIMESTRAL  = 'TRIMESTRAL'
    SEMESTRAL   = 'SEMESTRAL'
    ANUAL       = 'ANUAL'

class TipoRestriccionAPSEnum(enum.Enum):
    DURA   = 'DURA'
    BLANDA = 'BLANDA'

class TipoRecursoAPSEnum(enum.Enum):
    EQUIPO      = 'EQUIPO'
    PERSONAL    = 'PERSONAL'
    TRANSPORTE  = 'TRANSPORTE'
    BODEGA      = 'BODEGA'
    MATERIAL    = 'MATERIAL'
    LINEA       = 'LINEA'

class TipoEscenarioAPSEnum(enum.Enum):
    BASE       = 'BASE'
    OPTIMISTA  = 'OPTIMISTA'
    PESIMISTA  = 'PESIMISTA'
    WHAT_IF    = 'WHAT_IF'
    SIMULACION = 'SIMULACION'

class EstadoEscenarioAPSEnum(enum.Enum):
    BORRADOR       = 'BORRADOR'
    EN_SIMULACION  = 'EN_SIMULACION'
    COMPLETADO     = 'COMPLETADO'
    APROBADO       = 'APROBADO'

class TipoAlertaAPSEnum(enum.Enum):
    QUIEBRE_STOCK  = 'QUIEBRE_STOCK'
    EXCESO_INV     = 'EXCESO_INV'
    CAPACIDAD      = 'CAPACIDAD'
    INCUMPLIMIENTO = 'INCUMPLIMIENTO'
    RIESGO         = 'RIESGO'
    DEMANDA        = 'DEMANDA'

class NivelAlertaAPSEnum(enum.Enum):
    INFO        = 'INFO'
    ADVERTENCIA = 'ADVERTENCIA'
    CRITICA     = 'CRITICA'
    EMERGENCIA  = 'EMERGENCIA'

class TipoOrdenSugeridaAPSEnum(enum.Enum):
    COMPRA      = 'COMPRA'
    PRODUCCION  = 'PRODUCCION'
    TRASLADO    = 'TRASLADO'
    REPOSICION  = 'REPOSICION'


# ─── Models (FK-safe order) ───────────────────────────────────────────────────

class APSUbicacion(Base, TimestampMixin):
    __tablename__ = 'aps_ubicacion'
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(30), unique=True, nullable=False)
    nombre      = Column(String(200), nullable=False)
    tipo        = Column(String(50), nullable=False, default='PLANTA')
    ciudad      = Column(String(100), nullable=True)
    pais        = Column(String(100), nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)
    # De qué planta se surte un centro de distribución: el DRP convierte su
    # necesidad en traslados desde ahí, y esos traslados son demanda de la planta.
    abastecida_por_id = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)


class APSDemanda(Base, TimestampMixin):
    """Demanda real por producto, ubicación y mes. Es la única entrada que el
    pronóstico necesita; todo lo demás del plan sale de aquí."""
    __tablename__ = 'aps_demanda'
    __table_args__ = (UniqueConstraint('producto_id', 'ubicacion_id', 'periodo', name='uq_aps_demanda'),)
    id           = Column(Integer, primary_key=True, index=True)
    producto_id  = Column(Integer, ForeignKey('aps_producto.id'), nullable=False, index=True)
    ubicacion_id = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=False)
    periodo      = Column(String(7), nullable=False)          # YYYY-MM
    cantidad     = Column(Float, nullable=False, default=0.0)


class APSRuta(Base, TimestampMixin):
    """Cuánto de un recurso consume una unidad de producto. Sin ruta, el
    producto se compra; con ruta, se fabrica y carga la capacidad."""
    __tablename__ = 'aps_ruta'
    __table_args__ = (UniqueConstraint('producto_id', 'recurso_id', name='uq_aps_ruta'),)
    id               = Column(Integer, primary_key=True, index=True)
    producto_id      = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    recurso_id       = Column(Integer, ForeignKey('aps_recurso.id'), nullable=False)
    horas_por_unidad = Column(Float, nullable=False)


class APSConfig(Base, TimestampMixin):
    """Parámetros del motor de planeación. Solo los que el motor lee."""
    __tablename__ = 'aps_config'
    id    = Column(Integer, primary_key=True, index=True)
    clave = Column(String(60), unique=True, nullable=False)
    valor = Column(Float, nullable=False)


class APSProducto(Base, TimestampMixin):
    __tablename__ = 'aps_producto'
    id             = Column(Integer, primary_key=True, index=True)
    codigo         = Column(String(50), unique=True, nullable=False)
    nombre         = Column(String(300), nullable=False)
    familia        = Column(String(100), nullable=True)
    categoria      = Column(String(100), nullable=True)
    unidad_medida  = Column(String(30), nullable=False, default='UN')
    lead_time_dias = Column(Integer, nullable=False, default=0)
    costo_unitario = Column(Float, nullable=True)
    precio_venta   = Column(Float, nullable=True)
    activo         = Column(Boolean, default=True, nullable=False)
    peso_kg        = Column(Float, nullable=True)   # para consolidar traslados en camiones


class APSRecurso(Base, TimestampMixin):
    __tablename__ = 'aps_recurso'
    id               = Column(Integer, primary_key=True, index=True)
    ubicacion_id     = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)
    codigo           = Column(String(30), unique=True, nullable=False)
    nombre           = Column(String(200), nullable=False)
    tipo             = Column(SAEnum(TipoRecursoAPSEnum), nullable=False)
    capacidad_diaria = Column(Float, nullable=True)
    unidad_capacidad = Column(String(30), nullable=True)
    eficiencia_pct   = Column(Float, nullable=False, default=85.0)
    activo           = Column(Boolean, default=True, nullable=False)


class APSRestriccion(Base, TimestampMixin):
    __tablename__ = 'aps_restriccion'
    id           = Column(Integer, primary_key=True, index=True)
    ubicacion_id = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)
    recurso_id   = Column(Integer, ForeignKey('aps_recurso.id'), nullable=True)
    tipo         = Column(SAEnum(TipoRestriccionAPSEnum), nullable=False)
    nombre       = Column(String(200), nullable=False)
    descripcion  = Column(Text, nullable=True)
    valor_min    = Column(Float, nullable=True)
    valor_max    = Column(Float, nullable=True)
    activo       = Column(Boolean, default=True, nullable=False)
    # Qué limita: el tipo dice si es dura o blanda; el ámbito, sobre qué. El
    # motor aplica BODEGA (unidades máximas en la ubicación) y TRANSPORTE (kg
    # por vehículo desde la ubicación); OTRA queda registrada sin aplicarse.
    ambito       = Column(String(30), nullable=False, default='OTRA')


class APSParametro(Base, TimestampMixin):
    __tablename__ = 'aps_parametro'
    id                  = Column(Integer, primary_key=True, index=True)
    producto_id         = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    ubicacion_id        = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=False)
    stock_seguridad     = Column(Float, nullable=False, default=0.0)
    stock_minimo        = Column(Float, nullable=False, default=0.0)
    stock_maximo        = Column(Float, nullable=True)
    stock_objetivo      = Column(Float, nullable=True)
    punto_reorden       = Column(Float, nullable=False, default=0.0)
    lote_minimo_compra  = Column(Float, nullable=True)
    lote_produccion     = Column(Float, nullable=True)
    lead_time_compra_dias = Column(Integer, nullable=True)
    lead_time_produccion_dias = Column(Integer, nullable=True)
    nivel_servicio_pct  = Column(Float, nullable=False, default=95.0)
    dias_cobertura      = Column(Float, nullable=True)
    # Existencias hoy en esa ubicación: el punto de partida de la proyección.
    stock_actual        = Column(Float, nullable=False, default=0.0)


class APSPronostico(Base, TimestampMixin):
    __tablename__ = 'aps_pronostico'
    id            = Column(Integer, primary_key=True, index=True)
    producto_id   = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    ubicacion_id  = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)
    tipo          = Column(SAEnum(TipoPronosticoAPSEnum), nullable=False)
    metodo        = Column(SAEnum(MetodoPronosticoAPSEnum), nullable=True)
    horizonte     = Column(SAEnum(HorizontePlanAPSEnum), nullable=False)
    fecha_inicio  = Column(DateTime(timezone=True), nullable=False)
    fecha_fin     = Column(DateTime(timezone=True), nullable=False)
    version       = Column(String(20), nullable=False, default='1.0')
    accuracy_pct  = Column(Float, nullable=True)
    bias_pct      = Column(Float, nullable=True)
    mape_pct      = Column(Float, nullable=True)
    activo        = Column(Boolean, default=True, nullable=False)
    detalles      = relationship('APSDetallePeriodo', back_populates='pronostico', lazy='dynamic')
    colaboraciones = relationship('APSColaboracion', back_populates='pronostico', lazy='dynamic')


class APSDetallePeriodo(Base, TimestampMixin):
    __tablename__ = 'aps_detalle_periodo'
    id              = Column(Integer, primary_key=True, index=True)
    pronostico_id   = Column(Integer, ForeignKey('aps_pronostico.id'), nullable=False)
    periodo         = Column(String(20), nullable=False)
    fecha_inicio    = Column(DateTime(timezone=True), nullable=False)
    fecha_fin       = Column(DateTime(timezone=True), nullable=False)
    cantidad_pronosticada = Column(Float, nullable=False)
    cantidad_real   = Column(Float, nullable=True)
    cantidad_consenso = Column(Float, nullable=True)
    limite_inferior = Column(Float, nullable=True)
    limite_superior = Column(Float, nullable=True)
    pronostico      = relationship('APSPronostico', back_populates='detalles')


class APSColaboracion(Base, TimestampMixin):
    __tablename__ = 'aps_colaboracion'
    id              = Column(Integer, primary_key=True, index=True)
    pronostico_id   = Column(Integer, ForeignKey('aps_pronostico.id'), nullable=False)
    periodo         = Column(String(20), nullable=False)
    area            = Column(String(100), nullable=False)
    usuario         = Column(String(200), nullable=False)
    cantidad_ajuste = Column(Float, nullable=False)
    justificacion   = Column(Text, nullable=True)
    aprobado        = Column(Boolean, default=False, nullable=False)
    pronostico      = relationship('APSPronostico', back_populates='colaboraciones')


class APSEscenario(Base, TimestampMixin):
    __tablename__ = 'aps_escenario'
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(200), nullable=False)
    tipo        = Column(SAEnum(TipoEscenarioAPSEnum), nullable=False)
    estado      = Column(SAEnum(EstadoEscenarioAPSEnum), nullable=False, default=EstadoEscenarioAPSEnum.BORRADOR)
    descripcion = Column(Text, nullable=True)
    supuesto_demanda_delta_pct = Column(Float, nullable=True)
    supuesto_capacidad_delta_pct = Column(Float, nullable=True)
    supuesto_costo_delta_pct   = Column(Float, nullable=True)
    creado_por  = Column(String(200), nullable=True)
    aprobado    = Column(Boolean, default=False, nullable=False)
    simulaciones = relationship('APSSimulacion', back_populates='escenario', lazy='dynamic')


class APSPlanMaestro(Base, TimestampMixin):
    __tablename__ = 'aps_plan_maestro'
    id             = Column(Integer, primary_key=True, index=True)
    escenario_id   = Column(Integer, ForeignKey('aps_escenario.id'), nullable=True)
    nombre         = Column(String(200), nullable=False)
    tipo           = Column(SAEnum(TipoPlanAPSEnum), nullable=False, default=TipoPlanAPSEnum.MPS)
    estado         = Column(SAEnum(EstadoPlanAPSEnum), nullable=False, default=EstadoPlanAPSEnum.BORRADOR)
    horizonte      = Column(SAEnum(HorizontePlanAPSEnum), nullable=False, default=HorizontePlanAPSEnum.MENSUAL)
    fecha_inicio   = Column(DateTime(timezone=True), nullable=False)
    fecha_fin      = Column(DateTime(timezone=True), nullable=False)
    version        = Column(String(20), nullable=False, default='1.0')
    adherencia_pct = Column(Float, nullable=True)
    creado_por     = Column(String(200), nullable=True)
    observaciones  = Column(Text, nullable=True)
    detalles       = relationship('APSPlanDetalle', back_populates='plan', lazy='dynamic')


class APSPlanDetalle(Base, TimestampMixin):
    __tablename__ = 'aps_plan_detalle'
    id            = Column(Integer, primary_key=True, index=True)
    plan_id       = Column(Integer, ForeignKey('aps_plan_maestro.id'), nullable=False)
    producto_id   = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    ubicacion_id  = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)
    recurso_id    = Column(Integer, ForeignKey('aps_recurso.id'), nullable=True)
    periodo       = Column(String(20), nullable=False)
    fecha_inicio  = Column(DateTime(timezone=True), nullable=False)
    fecha_fin     = Column(DateTime(timezone=True), nullable=False)
    cantidad_plan = Column(Float, nullable=False)
    cantidad_real = Column(Float, nullable=True)
    costo_total   = Column(Float, nullable=True)
    plan          = relationship('APSPlanMaestro', back_populates='detalles')


class APSMRP(Base, TimestampMixin):
    __tablename__ = 'aps_mrp'
    id                  = Column(Integer, primary_key=True, index=True)
    plan_id             = Column(Integer, ForeignKey('aps_plan_maestro.id'), nullable=False)
    producto_id         = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    periodo             = Column(String(20), nullable=False)
    demanda_bruta       = Column(Float, nullable=False, default=0.0)
    stock_inicial       = Column(Float, nullable=False, default=0.0)
    recepciones_plan    = Column(Float, nullable=False, default=0.0)
    disponible_neto     = Column(Float, nullable=False, default=0.0)
    requerimiento_neto  = Column(Float, nullable=False, default=0.0)
    orden_sugerida      = Column(Float, nullable=False, default=0.0)
    tipo_orden          = Column(SAEnum(TipoOrdenSugeridaAPSEnum), nullable=True)
    fecha_emision       = Column(DateTime(timezone=True), nullable=True)
    fecha_recepcion     = Column(DateTime(timezone=True), nullable=True)


class APSCapacidad(Base, TimestampMixin):
    __tablename__ = 'aps_capacidad'
    id               = Column(Integer, primary_key=True, index=True)
    recurso_id       = Column(Integer, ForeignKey('aps_recurso.id'), nullable=False)
    periodo          = Column(String(20), nullable=False)
    fecha_inicio     = Column(DateTime(timezone=True), nullable=False)
    fecha_fin        = Column(DateTime(timezone=True), nullable=False)
    capacidad_total  = Column(Float, nullable=False)
    capacidad_disponible = Column(Float, nullable=False)
    capacidad_comprometida = Column(Float, nullable=False, default=0.0)
    porcentaje_uso   = Column(Float, nullable=True)
    turno            = Column(String(50), nullable=True)


class APSCargaCapacidad(Base, TimestampMixin):
    __tablename__ = 'aps_carga_capacidad'
    id          = Column(Integer, primary_key=True, index=True)
    plan_id     = Column(Integer, ForeignKey('aps_plan_maestro.id'), nullable=False)
    recurso_id  = Column(Integer, ForeignKey('aps_recurso.id'), nullable=False)
    periodo     = Column(String(20), nullable=False)
    carga       = Column(Float, nullable=False)
    capacidad   = Column(Float, nullable=False)
    pct_uso     = Column(Float, nullable=True)
    es_cuello   = Column(Boolean, default=False, nullable=False)


class APSInventarioOptimo(Base, TimestampMixin):
    __tablename__ = 'aps_inventario_optimo'
    id                = Column(Integer, primary_key=True, index=True)
    producto_id       = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    ubicacion_id      = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=False)
    stock_seguridad   = Column(Float, nullable=False)
    stock_minimo      = Column(Float, nullable=False)
    stock_maximo      = Column(Float, nullable=False)
    stock_objetivo    = Column(Float, nullable=False)
    punto_reorden     = Column(Float, nullable=False)
    eoq               = Column(Float, nullable=True)
    dias_inventario   = Column(Float, nullable=True)
    rotacion          = Column(Float, nullable=True)
    costo_posesion    = Column(Float, nullable=True)
    nivel_servicio_pct = Column(Float, nullable=False, default=95.0)
    fecha_calculo     = Column(DateTime(timezone=True), nullable=False)


class APSOrdenSugerida(Base, TimestampMixin):
    __tablename__ = 'aps_orden_sugerida'
    id              = Column(Integer, primary_key=True, index=True)
    plan_id         = Column(Integer, ForeignKey('aps_plan_maestro.id'), nullable=True)
    producto_id     = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    ubicacion_id    = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)
    tipo            = Column(SAEnum(TipoOrdenSugeridaAPSEnum), nullable=False)
    cantidad        = Column(Float, nullable=False)
    unidad_medida   = Column(String(30), nullable=False, default='UN')
    fecha_emision   = Column(DateTime(timezone=True), nullable=True)
    fecha_requerida = Column(DateTime(timezone=True), nullable=False)
    prioridad       = Column(String(20), nullable=False, default='NORMAL')
    estado          = Column(String(30), nullable=False, default='PENDIENTE')
    aprobada        = Column(Boolean, default=False, nullable=False)
    costo_estimado  = Column(Float, nullable=True)
    justificacion   = Column(Text, nullable=True)


class APSSimulacion(Base, TimestampMixin):
    __tablename__ = 'aps_simulacion'
    id             = Column(Integer, primary_key=True, index=True)
    escenario_id   = Column(Integer, ForeignKey('aps_escenario.id'), nullable=False)
    nombre         = Column(String(200), nullable=False)
    estado         = Column(String(30), nullable=False, default='PENDIENTE')
    duracion_seg   = Column(Float, nullable=True)
    resultado_kpi  = Column(Text, nullable=True)
    error          = Column(Text, nullable=True)
    fecha_inicio   = Column(DateTime(timezone=True), nullable=True)
    fecha_fin      = Column(DateTime(timezone=True), nullable=True)
    escenario      = relationship('APSEscenario', back_populates='simulaciones')
    resultados     = relationship('APSResultadoSimulacion', back_populates='simulacion', lazy='dynamic')


class APSResultadoSimulacion(Base, TimestampMixin):
    __tablename__ = 'aps_resultado_simulacion'
    id            = Column(Integer, primary_key=True, index=True)
    simulacion_id = Column(Integer, ForeignKey('aps_simulacion.id'), nullable=False)
    metrica       = Column(String(100), nullable=False)
    valor_base    = Column(Float, nullable=True)
    valor_escenario = Column(Float, nullable=True)
    delta         = Column(Float, nullable=True)
    delta_pct     = Column(Float, nullable=True)
    simulacion    = relationship('APSSimulacion', back_populates='resultados')


class APSAlerta(Base, TimestampMixin):
    __tablename__ = 'aps_alerta'
    id            = Column(Integer, primary_key=True, index=True)
    producto_id   = Column(Integer, ForeignKey('aps_producto.id'), nullable=True)
    ubicacion_id  = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)
    tipo          = Column(SAEnum(TipoAlertaAPSEnum), nullable=False)
    nivel         = Column(SAEnum(NivelAlertaAPSEnum), nullable=False)
    titulo        = Column(String(300), nullable=False)
    descripcion   = Column(Text, nullable=True)
    valor_actual  = Column(Float, nullable=True)
    valor_umbral  = Column(Float, nullable=True)
    fecha_quiebre_estimada = Column(DateTime(timezone=True), nullable=True)
    resuelta      = Column(Boolean, default=False, nullable=False)
    accion_recomendada = Column(Text, nullable=True)


class APSSOIPCiclo(Base, TimestampMixin):
    __tablename__ = 'aps_soip_ciclo'
    id            = Column(Integer, primary_key=True, index=True)
    nombre        = Column(String(200), nullable=False)
    periodo       = Column(String(20), nullable=False)
    fecha_inicio  = Column(DateTime(timezone=True), nullable=False)
    fecha_cierre  = Column(DateTime(timezone=True), nullable=True)
    estado        = Column(String(30), nullable=False, default='ABIERTO')
    facilitador   = Column(String(200), nullable=True)
    acuerdos      = Column(Text, nullable=True)
    revisiones    = relationship('APSSOIPRevision', back_populates='ciclo', lazy='dynamic')


class APSSOIPRevision(Base, TimestampMixin):
    __tablename__ = 'aps_soip_revision'
    id          = Column(Integer, primary_key=True, index=True)
    ciclo_id    = Column(Integer, ForeignKey('aps_soip_ciclo.id'), nullable=False)
    tipo        = Column(String(50), nullable=False)
    fecha       = Column(DateTime(timezone=True), nullable=False)
    asistentes  = Column(Text, nullable=True)
    compromisos = Column(Text, nullable=True)
    estado      = Column(String(30), nullable=False, default='PENDIENTE')
    ciclo       = relationship('APSSOIPCiclo', back_populates='revisiones')


class APSDistribucion(Base, TimestampMixin):
    __tablename__ = 'aps_distribucion'
    id              = Column(Integer, primary_key=True, index=True)
    plan_id         = Column(Integer, ForeignKey('aps_plan_maestro.id'), nullable=True)
    origen_id       = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=False)
    destino_id      = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=False)
    producto_id     = Column(Integer, ForeignKey('aps_producto.id'), nullable=False)
    cantidad        = Column(Float, nullable=False)
    unidad_medida   = Column(String(30), nullable=False, default='UN')
    fecha_emision   = Column(DateTime(timezone=True), nullable=True)
    fecha_llegada   = Column(DateTime(timezone=True), nullable=True)
    tipo_movimiento = Column(String(50), nullable=False, default='TRASLADO')
    estado          = Column(String(30), nullable=False, default='SUGERIDA')
    costo_estimado  = Column(Float, nullable=True)


class APSTransporte(Base, TimestampMixin):
    __tablename__ = 'aps_transporte'
    id              = Column(Integer, primary_key=True, index=True)
    plan_id         = Column(Integer, ForeignKey('aps_plan_maestro.id'), nullable=True)
    origen_id       = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=False)
    destino_id      = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=False)
    tipo_vehiculo   = Column(String(50), nullable=True)
    capacidad_kg    = Column(Float, nullable=True)
    carga_kg        = Column(Float, nullable=True)
    pct_uso         = Column(Float, nullable=True)
    fecha_despacho  = Column(DateTime(timezone=True), nullable=True)
    fecha_entrega   = Column(DateTime(timezone=True), nullable=True)
    estado          = Column(String(30), nullable=False, default='SUGERIDA')
    costo_estimado  = Column(Float, nullable=True)
    tms_viaje_id    = Column(Integer, nullable=True)


class APSAuditoria(Base, TimestampMixin):
    __tablename__ = 'aps_auditoria'
    id          = Column(Integer, primary_key=True, index=True)
    entidad     = Column(String(100), nullable=False)
    entidad_id  = Column(Integer, nullable=True)
    accion      = Column(String(100), nullable=False)
    usuario     = Column(String(200), nullable=True)
    datos_antes = Column(Text, nullable=True)
    datos_despues = Column(Text, nullable=True)
    justificacion = Column(Text, nullable=True)


class APSConsenso(Base, TimestampMixin):
    __tablename__ = 'aps_consenso'
    id                  = Column(Integer, primary_key=True, index=True)
    pronostico_id       = Column(Integer, ForeignKey('aps_pronostico.id'), nullable=False)
    periodo             = Column(String(20), nullable=False)
    cantidad_estadistica = Column(Float, nullable=True)
    ajuste_comercial    = Column(Float, nullable=True)
    ajuste_operaciones  = Column(Float, nullable=True)
    ajuste_finanzas     = Column(Float, nullable=True)
    cantidad_consenso   = Column(Float, nullable=False)
    aprobado_por        = Column(String(200), nullable=True)
    fecha_aprobacion    = Column(DateTime(timezone=True), nullable=True)


class APSKPIDiario(Base, TimestampMixin):
    __tablename__ = 'aps_kpi_diario'
    id                  = Column(Integer, primary_key=True, index=True)
    fecha               = Column(DateTime(timezone=True), nullable=False)
    ubicacion_id        = Column(Integer, ForeignKey('aps_ubicacion.id'), nullable=True)
    forecast_accuracy   = Column(Float, nullable=True)
    bias                = Column(Float, nullable=True)
    otif                = Column(Float, nullable=True)
    fill_rate           = Column(Float, nullable=True)
    inventory_turns     = Column(Float, nullable=True)
    days_of_inventory   = Column(Float, nullable=True)
    service_level       = Column(Float, nullable=True)
    capacity_utilization = Column(Float, nullable=True)
    perfect_order       = Column(Float, nullable=True)
    schedule_adherence  = Column(Float, nullable=True)
    alertas_activas     = Column(Integer, nullable=False, default=0)
    ordenes_sugeridas   = Column(Integer, nullable=False, default=0)
