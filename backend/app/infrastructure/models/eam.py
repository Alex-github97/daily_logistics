import enum
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, Date, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.infrastructure.models.base import Base, TimestampMixin


# ─── Enums ────────────────────────────────────────────────────────────────────

class TipoActivoEAMEnum(str, enum.Enum):
    VEHICULO         = "VEHICULO"
    REMOLQUE         = "REMOLQUE"
    MOTOCICLETA      = "MOTOCICLETA"
    MONTACARGAS      = "MONTACARGAS"
    EQUIPO_PATIO     = "EQUIPO_PATIO"
    EQUIPO_LOGISTICO = "EQUIPO_LOGISTICO"
    MAQUINARIA       = "MAQUINARIA"
    INFRAESTRUCTURA  = "INFRAESTRUCTURA"
    BODEGA           = "BODEGA"
    EDIFICACION      = "EDIFICACION"
    EQUIPO_TECNOLOGICO = "EQUIPO_TECNOLOGICO"
    EQUIPO_INDUSTRIAL  = "EQUIPO_INDUSTRIAL"
    HERRAMIENTA        = "HERRAMIENTA"
    ACTIVO_CRITICO     = "ACTIVO_CRITICO"
    OTRO               = "OTRO"

class EstadoActivoEAMEnum(str, enum.Enum):
    OPERATIVO        = "OPERATIVO"
    EN_MANTENIMIENTO = "EN_MANTENIMIENTO"
    FUERA_DE_SERVICIO = "FUERA_DE_SERVICIO"
    DADO_DE_BAJA     = "DADO_DE_BAJA"
    STANDBY          = "STANDBY"
    EN_GARANTIA      = "EN_GARANTIA"

class CriticidadEAMEnum(str, enum.Enum):
    BAJA    = "BAJA"
    MEDIA   = "MEDIA"
    ALTA    = "ALTA"
    CRITICA = "CRITICA"

class TipoOTEAMEnum(str, enum.Enum):
    PREVENTIVA  = "PREVENTIVA"
    CORRECTIVA  = "CORRECTIVA"
    PREDICTIVA  = "PREDICTIVA"
    EMERGENCIA  = "EMERGENCIA"
    CAMPANA     = "CAMPANA"
    CALIBRACION = "CALIBRACION"
    INSPECCION  = "INSPECCION"
    RCA         = "RCA"

class EstadoOTEAMEnum(str, enum.Enum):
    PENDIENTE            = "PENDIENTE"
    ASIGNADA             = "ASIGNADA"
    EN_EJECUCION         = "EN_EJECUCION"
    EN_ESPERA_REPUESTOS  = "EN_ESPERA_REPUESTOS"
    COMPLETADA           = "COMPLETADA"
    CANCELADA            = "CANCELADA"
    PENDIENTE_APROBACION = "PENDIENTE_APROBACION"

class TipoPreguntaEAMEnum(str, enum.Enum):
    SI_NO      = "SI_NO"
    ESCALA     = "ESCALA"
    LISTA      = "LISTA"
    NUMERICO   = "NUMERICO"
    FOTOGRAFICO = "FOTOGRAFICO"
    TEXTO      = "TEXTO"

class TipoMantenimientoEAMEnum(str, enum.Enum):
    TIEMPO    = "TIEMPO"
    USO       = "USO"
    CONDICION = "CONDICION"

class UnidadUsoEAMEnum(str, enum.Enum):
    KILOMETROS = "KILOMETROS"
    HORAS      = "HORAS"
    CICLOS     = "CICLOS"
    DIAS       = "DIAS"
    SEMANAS    = "SEMANAS"
    MESES      = "MESES"

class EstadoNeumaticEAMEnum(str, enum.Enum):
    INSTALADO  = "INSTALADO"
    ALMACENADO = "ALMACENADO"
    REENCAUCHE = "REENCAUCHE"
    BAJA       = "BAJA"

class TipoMovNeumaticEAMEnum(str, enum.Enum):
    INSTALACION = "INSTALACION"
    ROTACION    = "ROTACION"
    DESMONTAJE  = "DESMONTAJE"
    REENCAUCHE  = "REENCAUCHE"
    BAJA        = "BAJA"

class EstadoGarantiaEAMEnum(str, enum.Enum):
    VIGENTE   = "VIGENTE"
    VENCIDA   = "VENCIDA"
    RECLAMADA = "RECLAMADA"
    CANCELADA = "CANCELADA"

class ContaminacionAceiteEAMEnum(str, enum.Enum):
    NORMAL   = "NORMAL"
    MODERADA = "MODERADA"
    CRITICA  = "CRITICA"

class EstadoCalibracionEAMEnum(str, enum.Enum):
    VIGENTE  = "VIGENTE"
    VENCIDA  = "VENCIDA"
    PENDIENTE = "PENDIENTE"

class PrioridadOTEAMEnum(str, enum.Enum):
    BAJA    = "BAJA"
    MEDIA   = "MEDIA"
    ALTA    = "ALTA"
    URGENTE = "URGENTE"


# ─── Catálogos maestros ───────────────────────────────────────────────────────

class EAMTipoTrabajo(Base, TimestampMixin):
    __tablename__ = "eam_tipo_trabajo"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(100), nullable=False)
    descripcion = Column(Text)
    categoria   = Column(String(50))  # PREVENTIVO, CORRECTIVO, PREDICTIVO…
    # Texto y no número: hay trabajos cuya duración es "Variable" y forzar horas
    # obligaría a inventar un valor.
    duracion            = Column(String(40))
    requiere_taller     = Column(Boolean, default=False)
    requiere_materiales = Column(Boolean, default=False)
    sistema             = Column(String(100))
    subsistema          = Column(String(100))
    activo      = Column(Boolean, default=True)


class EAMCentroCosto(Base, TimestampMixin):
    """A dónde se cargan los costos de mantenimiento.

    Tiene tabla propia y no va al catálogo maestro porque carga atributos del
    negocio —ciudad y plataforma—, que es la regla del módulo para decidir.
    """

    __tablename__ = "eam_centro_costo"
    id         = Column(Integer, primary_key=True, index=True)
    codigo     = Column(String(40), unique=True, nullable=False, index=True)
    nombre     = Column(String(150), nullable=False)
    ciudad     = Column(String(100))
    plataforma = Column(String(120))
    activo     = Column(Boolean, default=True)


class EAMActividad(Base, TimestampMixin):
    __tablename__ = "eam_actividad"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(100), nullable=False)  # Inspeccionar, Lubricar, Reemplazar...
    descripcion = Column(Text)
    activo      = Column(Boolean, default=True)


class EAMRepuesto(Base, TimestampMixin):
    __tablename__ = "eam_repuesto"
    id             = Column(Integer, primary_key=True, index=True)
    codigo         = Column(String(50), unique=True, nullable=False)
    nombre         = Column(String(200), nullable=False)
    descripcion    = Column(Text)
    categoria      = Column(String(100))
    unidad_medida  = Column(String(30))
    costo_unitario = Column(Float, default=0)
    stock_minimo   = Column(Integer, default=0)
    stock_actual   = Column(Integer, default=0)
    proveedor_ppal = Column(String(100))
    activo         = Column(Boolean, default=True)


class EAMFallaCatalogo(Base, TimestampMixin):
    __tablename__ = "eam_falla_catalogo"
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(30), unique=True)
    descripcion = Column(String(200), nullable=False)
    tipo_activo = Column(String(50))
    activo      = Column(Boolean, default=True)


class EAMCausaCatalogo(Base, TimestampMixin):
    __tablename__ = "eam_causa_catalogo"
    id          = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String(200), nullable=False)
    activo      = Column(Boolean, default=True)


class EAMSolucionCatalogo(Base, TimestampMixin):
    __tablename__ = "eam_solucion_catalogo"
    id          = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String(200), nullable=False)
    activo      = Column(Boolean, default=True)


class EAMContratista(Base, TimestampMixin):
    __tablename__ = "eam_contratista"
    id           = Column(Integer, primary_key=True, index=True)
    nombre       = Column(String(200), nullable=False)
    nit          = Column(String(30))
    tipo         = Column(String(50))  # TALLER, PROVEEDOR, TECNICO_EXTERNO, LABORATORIO
    especialidad = Column(String(200))
    contacto     = Column(String(100))
    telefono     = Column(String(30))
    email        = Column(String(100))
    ciudad       = Column(String(100))
    calificacion = Column(Float, default=5.0)
    activo       = Column(Boolean, default=True)


# ─── Catálogo de tipos de activo ───────────────────────────────────────────────

class EAMTipoActivo(Base, TimestampMixin):
    """Catálogo de tipos de activo (jerarquía sobre EAMActivo.tipo_activo, guardado
    como texto por código — mismo patrón usado en los catálogos de WMS). La bandera
    `usa_llantas` determina qué activos aparecen como vehículo seleccionable en el
    módulo de Neumáticos."""
    __tablename__ = "eam_tipo_activo"
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(50), unique=True, nullable=False)
    nombre      = Column(String(100), nullable=False)
    usa_llantas = Column(Boolean, default=False)
    activo      = Column(Boolean, default=True)


# ─── Maestro de activos ───────────────────────────────────────────────────────

class EAMActivo(Base, TimestampMixin):
    __tablename__ = "eam_activo"
    id                   = Column(Integer, primary_key=True, index=True)
    codigo               = Column(String(50), unique=True, nullable=False)
    nombre               = Column(String(200), nullable=False)
    tipo_activo          = Column(String(50))   # TipoActivoEAMEnum
    estado               = Column(String(30), default="OPERATIVO")
    criticidad           = Column(String(20), default="MEDIA")
    parent_id            = Column(Integer, ForeignKey("eam_activo.id"), nullable=True)
    marca                = Column(String(100))
    linea                = Column(String(100))   # jerarquía marca > línea > modelo
    modelo               = Column(String(100))
    anio                 = Column(Integer)
    numero_serie         = Column(String(100))   # serie generica (activos que no son vehiculo)
    numero_motor         = Column(String(100))
    numero_chasis        = Column(String(100))
    numero_carroceria    = Column(String(100))
    observaciones        = Column(Text)
    observaciones_adicionales = Column(Text)
    cuenta_contable      = Column(String(80))
    centro_costo         = Column(String(120))
    placa                = Column(String(20))
    color                = Column(String(50))
    fecha_adquisicion    = Column(Date)
    costo_adquisicion    = Column(Float)
    valor_libro          = Column(Float)
    depreciacion_anual   = Column(Float)
    vida_util_anios      = Column(Integer)
    vida_util_km         = Column(Float)
    ubicacion            = Column(String(200))
    sede                 = Column(String(100))
    area                 = Column(String(100))
    responsable          = Column(String(100))
    odometro_actual      = Column(Float, default=0)
    horometro_actual     = Column(Float, default=0)
    # Horas que el activo debe estar disponible al mes (720 = continuo; un
    # turno ≈ 176). Es la base del cálculo de disponibilidad; vacío = continuo.
    horas_programadas_mes = Column(Float, nullable=True)
    tipo_combustible     = Column(String(50))
    capacidad_combustible = Column(Float)
    numero_ejes          = Column(Integer, nullable=True)   # para layout de neumáticos
    layout_llantas       = Column(JSON, nullable=True)      # llantas por eje; NULL = patrón clásico (eje1=2, resto=4)
    tiene_repuesto       = Column(Boolean, default=True)
    cantidad_repuestos   = Column(Integer, default=1)
    motor_marca          = Column(String(100), nullable=True)
    motor_linea          = Column(String(100), nullable=True)
    motor_cc             = Column(Float, nullable=True)
    imagen_url           = Column(String(500))
    especificaciones     = Column(JSON)
    activo               = Column(Boolean, default=True)
    # Trazabilidad del "espejo" cuando este activo representa un vehículo creado
    # originalmente en otro módulo (TMS, Flota) y vinculado aquí para poder
    # llevarle historial de mantenimiento/neumáticos. origen='EAM' = nativo.
    origen               = Column(String(20), default="EAM")
    origen_id            = Column(Integer, nullable=True)


class EAMComponente(Base, TimestampMixin):
    __tablename__ = "eam_componente"
    id           = Column(Integer, primary_key=True, index=True)
    activo_id    = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    nombre       = Column(String(100), nullable=False)
    descripcion  = Column(Text)
    numero_parte = Column(String(100))
    marca        = Column(String(100))
    estado       = Column(String(30), default="BUENO")
    criticidad   = Column(String(20), default="MEDIA")
    vida_util_horas = Column(Float)
    horas_actuales  = Column(Float, default=0)


class EAMDocumentoActivo(Base, TimestampMixin):
    __tablename__ = "eam_documento_activo"
    id                = Column(Integer, primary_key=True, index=True)
    activo_id         = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    tipo              = Column(String(50))  # MANUAL, GARANTIA, POLIZA, CERT_REVISION, SOAT, TECNICO_MECANICA
    nombre            = Column(String(200), nullable=False)
    numero            = Column(String(100))
    fecha_expedicion  = Column(Date)
    fecha_vencimiento = Column(Date)
    url               = Column(String(500))
    activo            = Column(Boolean, default=True)


# ─── Checklists ───────────────────────────────────────────────────────────────

class EAMChecklistPlantilla(Base, TimestampMixin):
    __tablename__ = "eam_checklist_plantilla"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(200), nullable=False)
    tipo_activo = Column(String(50))
    descripcion = Column(Text)
    activo      = Column(Boolean, default=True)


class EAMChecklistPregunta(Base, TimestampMixin):
    __tablename__ = "eam_checklist_pregunta"
    id             = Column(Integer, primary_key=True, index=True)
    plantilla_id   = Column(Integer, ForeignKey("eam_checklist_plantilla.id"), nullable=False)
    orden          = Column(Integer, default=0)
    seccion        = Column(String(100))
    pregunta       = Column(String(300), nullable=False)
    tipo_respuesta = Column(String(20))  # TipoPreguntaEAMEnum
    opciones       = Column(JSON)
    requiere_foto  = Column(Boolean, default=False)
    requiere_firma = Column(Boolean, default=False)
    critica        = Column(Boolean, default=False)
    activo         = Column(Boolean, default=True)


# ─── Planes de mantenimiento ──────────────────────────────────────────────────

class EAMPlanMantenimiento(Base, TimestampMixin):
    """Rutina programada, definida sobre la jerarquía del catálogo.

    El alcance se declara por niveles — tipo → marca → línea — y la rutina cubre
    a todo activo que encaje: así una rutina de 5.000 km se escribe una vez y no
    una por cada tractocamión de la flota. `activo_id` sigue existiendo para la
    rutina que aplica a un solo equipo.

    Acá no se guarda cumplimiento: cada activo cubierto lleva su propio
    kilometraje, así que su vencimiento vive en EAMPlanActivo.
    """

    __tablename__ = "eam_plan_mantenimiento"
    id             = Column(Integer, primary_key=True, index=True)
    nombre         = Column(String(200), nullable=False)
    activo_id      = Column(Integer, ForeignKey("eam_activo.id"), nullable=True)
    # Niveles del alcance. En NULL, el nivel no restringe.
    tipo_activo    = Column(String(50))
    marca          = Column(String(100))
    linea          = Column(String(100))
    tipo_mant      = Column(String(30))  # TIEMPO, USO, CONDICION
    frecuencia     = Column(Integer)
    unidad         = Column(String(20))  # DIAS, SEMANAS, MESES, KM, HORAS
    tipo_ot        = Column(String(30), default="PREVENTIVA")
    checklist_id   = Column(Integer, ForeignKey("eam_checklist_plantilla.id"), nullable=True)
    descripcion    = Column(Text)
    costo_estimado = Column(Float)
    activo         = Column(Boolean, default=True)

    # La rutina se arma como la OT que va a generar: trabajos por un lado y
    # materiales por el otro.
    tareas = relationship(
        "EAMPlanDetalle", back_populates="plan",
        cascade="all, delete-orphan", lazy="selectin",
    )
    repuestos = relationship(
        "EAMPlanRepuesto", back_populates="plan",
        cascade="all, delete-orphan", lazy="selectin",
    )


class EAMPlanActivo(Base, TimestampMixin):
    """Cumplimiento de una rutina en un activo concreto.

    Es lo que hace que la plantilla sirva para toda la flota: la rutina es una
    sola, pero cada activo tiene su última ejecución y su próximo vencimiento,
    calculados con su propio odómetro.
    """

    __tablename__ = "eam_plan_activo"
    __table_args__ = (
        UniqueConstraint("plan_id", "activo_id", name="uq_plan_activo"),
    )
    id        = Column(Integer, primary_key=True, index=True)
    plan_id   = Column(Integer, ForeignKey("eam_plan_mantenimiento.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    activo_id = Column(Integer, ForeignKey("eam_activo.id"), nullable=False, index=True)
    ultima_ejecucion_fecha     = Column(DateTime)
    ultima_ejecucion_odometro  = Column(Float)
    ultima_ejecucion_horometro = Column(Float)
    # Si se borra la OT, la rutina conserva su cumplimiento y solo pierde el
    # vínculo: el mantenimiento se hizo aunque el papel ya no esté.
    ultima_ot_id               = Column(
        Integer, ForeignKey("eam_orden_trabajo.id", ondelete="SET NULL"), nullable=True)
    proxima_fecha              = Column(DateTime)
    proximo_odometro           = Column(Float)
    proximo_horometro          = Column(Float)


class EAMPlanDetalle(Base, TimestampMixin):
    """Trabajo de la rutina. Solo mano de obra: los materiales van aparte, en
    EAMPlanRepuesto, igual que en la OT."""

    __tablename__ = "eam_plan_detalle"
    id                = Column(Integer, primary_key=True, index=True)
    plan_id           = Column(Integer, ForeignKey("eam_plan_mantenimiento.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    actividad_id      = Column(Integer, ForeignKey("eam_actividad.id"), nullable=True)
    descripcion       = Column(String(200), nullable=False)
    tiempo_estimado   = Column(Float)
    costo_mano_obra   = Column(Float, default=0)
    orden             = Column(Integer, default=0)

    plan = relationship("EAMPlanMantenimiento", back_populates="tareas")


class EAMPlanRepuesto(Base, TimestampMixin):
    """Material que consume la rutina cada vez que se ejecuta.

    Se guarda el precio de referencia aparte del catálogo: sirve para estimar
    el costo de la rutina aunque el precio del repuesto cambie después.
    """

    __tablename__ = "eam_plan_repuesto"
    id              = Column(Integer, primary_key=True, index=True)
    plan_id         = Column(Integer, ForeignKey("eam_plan_mantenimiento.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    repuesto_id     = Column(Integer, ForeignKey("eam_repuesto.id"), nullable=True)
    descripcion     = Column(String(200), nullable=False)
    cantidad        = Column(Float, default=1)
    unidad          = Column(String(30))
    costo_unitario  = Column(Float, default=0)
    orden           = Column(Integer, default=0)

    plan = relationship("EAMPlanMantenimiento", back_populates="repuestos")


# ─── Órdenes de trabajo ───────────────────────────────────────────────────────

class EAMOrdenTrabajo(Base, TimestampMixin):
    __tablename__ = "eam_orden_trabajo"
    id                    = Column(Integer, primary_key=True, index=True)
    numero                = Column(String(30), unique=True, nullable=False)
    activo_id             = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    tipo_ot               = Column(String(30))
    tipo_trabajo_id       = Column(Integer, ForeignKey("eam_tipo_trabajo.id"), nullable=True)
    estado                = Column(String(30), default="PENDIENTE")
    prioridad             = Column(String(20), default="MEDIA")
    descripcion           = Column(Text, nullable=False)
    falla_id              = Column(Integer, ForeignKey("eam_falla_catalogo.id"), nullable=True)
    causa_id              = Column(Integer, ForeignKey("eam_causa_catalogo.id"), nullable=True)
    solucion_id           = Column(Integer, ForeignKey("eam_solucion_catalogo.id"), nullable=True)
    plan_id               = Column(Integer, ForeignKey("eam_plan_mantenimiento.id"), nullable=True)
    contratista_id        = Column(Integer, ForeignKey("eam_contratista.id"), nullable=True)
    tecnico_asignado      = Column(String(100))
    fecha_requerida       = Column(DateTime)
    fecha_inicio          = Column(DateTime)
    fecha_fin             = Column(DateTime)
    odometro              = Column(Float)
    horometro             = Column(Float)
    costo_mano_obra       = Column(Float, default=0)
    costo_repuestos       = Column(Float, default=0)
    costo_servicios       = Column(Float, default=0)
    costo_total           = Column(Float, default=0)
    tiempo_estimado_horas = Column(Float)
    tiempo_real_horas     = Column(Float)
    observaciones         = Column(Text)
    creado_por            = Column(String(100))
    # Imputación contable y sede donde se atiende la OT.
    centro_costo          = Column(String(120))
    ciudad                = Column(String(100))
    # Si el activo queda fuera de servicio mientras dure la OT, y si el
    # origen fue una falla o un trabajo programado.
    afecta_disponibilidad = Column(Boolean, default=True)
    es_falla              = Column(Boolean, default=False)
    fecha_posible_cierre  = Column(DateTime)

    # Las líneas viven en eam_ot_mano_obra y eam_ot_material, que ya existían
    # sin usarse. Se cargan siempre porque la ficha de la OT las necesita.
    trabajos  = relationship(
        "EAMOTManoObra", back_populates="ot",
        cascade="all, delete-orphan", lazy="selectin",
    )
    repuestos = relationship(
        "EAMOTMaterial", back_populates="ot",
        cascade="all, delete-orphan", lazy="selectin",
    )


class EAMChecklistEjecucion(Base, TimestampMixin):
    __tablename__ = "eam_checklist_ejecucion"
    id            = Column(Integer, primary_key=True, index=True)
    plantilla_id  = Column(Integer, ForeignKey("eam_checklist_plantilla.id"), nullable=False)
    activo_id     = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    ot_id         = Column(Integer, ForeignKey("eam_orden_trabajo.id"), nullable=True)
    ejecutado_por = Column(String(100))
    fecha_inicio  = Column(DateTime)
    fecha_fin     = Column(DateTime)
    estado        = Column(String(30))
    pct_conforme  = Column(Float, default=0)
    observaciones = Column(Text)
    firma_url     = Column(String(500))


class EAMChecklistRespuesta(Base, TimestampMixin):
    __tablename__ = "eam_checklist_respuesta"
    id           = Column(Integer, primary_key=True, index=True)
    ejecucion_id = Column(Integer, ForeignKey("eam_checklist_ejecucion.id"), nullable=False)
    pregunta_id  = Column(Integer, ForeignKey("eam_checklist_pregunta.id"), nullable=False)
    respuesta    = Column(Text)
    conforme     = Column(Boolean)
    observacion  = Column(Text)
    foto_url     = Column(String(500))


class EAMOTMaterial(Base, TimestampMixin):
    """Repuesto consumido en una OT. El precio se congela al registrarlo."""

    __tablename__ = "eam_ot_material"
    id          = Column(Integer, primary_key=True, index=True)
    ot_id       = Column(Integer, ForeignKey("eam_orden_trabajo.id"), nullable=False, index=True)
    repuesto_id = Column(Integer, ForeignKey("eam_repuesto.id"), nullable=True)
    descripcion = Column(String(200))
    cantidad    = Column(Float, nullable=False)
    unidad      = Column(String(30))
    costo_unit  = Column(Float)
    costo_total = Column(Float)
    # Quién suministró el repuesto. NULL = taller interno; puede diferir del
    # proveedor principal de la OT.
    contratista_id = Column(Integer, ForeignKey("eam_contratista.id"), nullable=True)
    # De qué bodega sale. Vacío = la bodega por defecto del inventario. Sin
    # `repuesto_id` la línea es material suelto y no toca existencias.
    bodega_id      = Column(Integer, ForeignKey("eam_inv_bodega.id"), nullable=True)

    ot = relationship("EAMOrdenTrabajo", back_populates="repuestos")


class EAMOTManoObra(Base, TimestampMixin):
    """Cada labor hecha dentro de una OT, con su mano de obra.

    `tecnico` es opcional: una OT se cotiza por trabajo antes de saber quién
    la va a ejecutar.
    """

    __tablename__ = "eam_ot_mano_obra"
    id          = Column(Integer, primary_key=True, index=True)
    ot_id       = Column(Integer, ForeignKey("eam_orden_trabajo.id"), nullable=False, index=True)
    tecnico     = Column(String(100))
    actividad   = Column(String(300))
    fecha       = Column(DateTime)
    horas       = Column(Float)
    tarifa_hora = Column(Float)
    costo_total = Column(Float)
    # Encuadre del trabajo dentro del activo.
    tipo_trabajo_id = Column(Integer, ForeignKey("eam_tipo_trabajo.id"), nullable=True)
    sistema     = Column(String(100))
    subsistema  = Column(String(100))
    observaciones = Column(Text)
    # Quién ejecutó el trabajo. NULL = taller interno, y en ese caso el
    # responsable es `tecnico`. Puede diferir del proveedor principal de la OT.
    contratista_id = Column(Integer, ForeignKey("eam_contratista.id"), nullable=True)

    ot = relationship("EAMOrdenTrabajo", back_populates="trabajos")


# ─── Lubricación ──────────────────────────────────────────────────────────────

class EAMMuestraAceite(Base, TimestampMixin):
    __tablename__ = "eam_muestra_aceite"
    id              = Column(Integer, primary_key=True, index=True)
    activo_id       = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    componente_id   = Column(Integer, ForeignKey("eam_componente.id"), nullable=True)
    numero_muestra  = Column(String(50), unique=True, nullable=False)
    fecha_toma      = Column(DateTime, nullable=False)
    tipo_lubricante = Column(String(100))
    horas_aceite    = Column(Float)
    horas_equipo    = Column(Float)
    odometro        = Column(Float)
    laboratorio     = Column(String(100))
    hierro_ppm      = Column(Float)
    cobre_ppm       = Column(Float)
    aluminio_ppm    = Column(Float)
    silicio_ppm     = Column(Float)
    sodio_ppm       = Column(Float)
    agua_pct        = Column(Float)
    viscosidad_40   = Column(Float)
    viscosidad_100  = Column(Float)
    indice_viscosidad = Column(Float)
    tbn             = Column(Float)
    contaminacion   = Column(String(20), default="NORMAL")
    diagnostico     = Column(Text)
    recomendacion   = Column(Text)
    alerta          = Column(Boolean, default=False)


# ─── Neumáticos ───────────────────────────────────────────────────────────────

class EAMNeumatico(Base, TimestampMixin):
    __tablename__ = "eam_neumatico"
    id               = Column(Integer, primary_key=True, index=True)
    codigo           = Column(String(50), unique=True, nullable=False)
    marca            = Column(String(100))
    referencia       = Column(String(100))
    medida           = Column(String(50))
    tipo             = Column(String(50))
    estado           = Column(String(30), default="ALMACENADO")
    activo_id        = Column(Integer, ForeignKey("eam_activo.id"), nullable=True)
    posicion         = Column(String(30))
    fecha_instalacion = Column(Date)
    km_inicio        = Column(Float, default=0)
    km_actual        = Column(Float, default=0)
    km_total         = Column(Float, default=0)
    vida_util_km     = Column(Float)
    profundidad_diseño = Column(Float)
    profundidad_actual = Column(Float)
    costo            = Column(Float)
    proveedor        = Column(String(100))
    reencauches      = Column(Integer, default=0)
    # Llanta que entra al inventario ya usada: se captura su profundidad y
    # kilometraje actuales en lugar de asumir que arranca nueva.
    es_usada         = Column(Boolean, default=False)
    bodega_id        = Column(Integer, ForeignKey("eam_bodega_neumatico.id"), nullable=True)
    dano_id          = Column(Integer, ForeignKey("eam_dano_neumatico_catalogo.id"), nullable=True)
    motivo_baja      = Column(String(255), nullable=True)
    fecha_baja       = Column(Date, nullable=True)
    # tipo de uso: DIRECCIONAL / TRACCION / REMOLQUE / MULTIPOSICION / REPUESTO
    tipo_uso            = Column(String(20), nullable=True)
    presion_recomendada = Column(Float, nullable=True)   # psi
    presion_actual      = Column(Float, nullable=True)   # psi (última inspección)
    # orientación de montaje: NORMAL / INVERTIDA (para volteo de duales)
    orientacion         = Column(String(15), default="NORMAL")
    profundidad_externa = Column(Float, nullable=True)   # mm hombro externo
    profundidad_interna = Column(Float, nullable=True)   # mm hombro interno
    zona_id             = Column(Integer, ForeignKey("eam_zona_neumatico.id"), nullable=True)
    motivo_fin_vida_id  = Column(Integer, ForeignKey("eam_motivo_fin_vida.id"), nullable=True)
    dot                 = Column(String(20), nullable=True)   # código DOT (fecha de fabricación)
    tipo_rin            = Column(String(30), nullable=True)   # ACERO / ALUMINIO / OTRO


class EAMMovimientoNeumatico(Base, TimestampMixin):
    __tablename__ = "eam_movimiento_neumatico"
    id              = Column(Integer, primary_key=True, index=True)
    neumatico_id    = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    tipo_movimiento = Column(String(30))
    activo_id       = Column(Integer, ForeignKey("eam_activo.id"), nullable=True)
    posicion_origen = Column(String(30))
    posicion        = Column(String(30))   # posición destino
    bodega_id       = Column(Integer, ForeignKey("eam_bodega_neumatico.id"), nullable=True)
    km_odometro     = Column(Float)
    # Los equipos que no llevan odómetro se miden por horas.
    horometro       = Column(Float)
    fecha           = Column(DateTime)      # fecha y hora del movimiento
    observaciones   = Column(Text)
    tecnico         = Column(String(100))


class EAMBodegaNeumatico(Base, TimestampMixin):
    """Bodega de almacenamiento de neumáticos (fuera de vehículo)."""
    __tablename__ = "eam_bodega_neumatico"
    id        = Column(Integer, primary_key=True, index=True)
    codigo    = Column(String(50), unique=True, nullable=False)
    nombre    = Column(String(150), nullable=False)
    ubicacion = Column(String(200))
    capacidad = Column(Integer, nullable=True)
    activo    = Column(Boolean, default=True)


class EAMMarcaNeumatico(Base, TimestampMixin):
    """Marca de llanta o de banda de reencauche. `ambito` separa ambos catálogos
    (una misma marca puede fabricar los dos, pero con referencias distintas)."""
    __tablename__ = "eam_marca_neumatico"
    __table_args__ = (UniqueConstraint("nombre", "ambito", name="uq_eam_marca_neumatico_nombre_ambito"),)
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False)
    ambito = Column(String(10), nullable=False, default="LLANTA")   # LLANTA | BANDA
    activo = Column(Boolean, default=True)


class EAMDimensionNeumatico(Base, TimestampMixin):
    """Dimensión/medida (ej. 295/80R22.5)."""
    __tablename__ = "eam_dimension_neumatico"
    __table_args__ = (UniqueConstraint("nombre", "ambito", name="uq_eam_dimension_neumatico_nombre_ambito"),)
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(60), nullable=False)
    ambito = Column(String(10), nullable=False, default="LLANTA")
    activo = Column(Boolean, default=True)


class EAMReferenciaNeumatico(Base, TimestampMixin):
    """Referencia (diseño/modelo) que pertenece a una marca."""
    __tablename__ = "eam_referencia_neumatico"
    __table_args__ = (UniqueConstraint("marca_id", "nombre", name="uq_eam_referencia_neumatico_marca_nombre"),)
    id       = Column(Integer, primary_key=True, index=True)
    marca_id = Column(Integer, ForeignKey("eam_marca_neumatico.id", ondelete="CASCADE"), nullable=False)
    nombre   = Column(String(120), nullable=False)
    ambito   = Column(String(10), nullable=False, default="LLANTA")
    tipo_uso = Column(String(20), nullable=True)   # sugerencia: DIRECCIONAL/TRACCION/...
    activo   = Column(Boolean, default=True)


class EAMReferenciaDimension(Base, TimestampMixin):
    """Profundidad inicial de una referencia EN una dimensión concreta: la misma
    referencia calza distinto según la medida, por eso el dato vive aquí y no en
    la referencia ni en la dimensión por separado."""
    __tablename__ = "eam_referencia_dimension"
    __table_args__ = (UniqueConstraint("referencia_id", "dimension_id", name="uq_eam_referencia_dimension"),)
    id                  = Column(Integer, primary_key=True, index=True)
    referencia_id       = Column(Integer, ForeignKey("eam_referencia_neumatico.id", ondelete="CASCADE"), nullable=False)
    dimension_id        = Column(Integer, ForeignKey("eam_dimension_neumatico.id", ondelete="CASCADE"), nullable=False)
    profundidad_inicial = Column(Float, nullable=False)
    profundidad_minima  = Column(Float, nullable=True)
    vida_util_km        = Column(Float, nullable=True)
    presion_recomendada = Column(Float, nullable=True)
    activo              = Column(Boolean, default=True)


class EAMNeumaticoCatalogo(Base, TimestampMixin):
    """Catálogo configurable de atributos de neumáticos: marcas, medidas,
    referencias y vidas útiles (una fila por opción, discriminada por tipo)."""
    __tablename__ = "eam_neumatico_catalogo"
    id     = Column(Integer, primary_key=True, index=True)
    tipo   = Column(String(20), nullable=False)   # MARCA / MEDIDA / REFERENCIA / VIDA
    nombre = Column(String(120), nullable=False)
    valor  = Column(Float, nullable=True)          # p.ej. vida útil en km
    activo = Column(Boolean, default=True)


class EAMDanoNeumaticoCatalogo(Base, TimestampMixin):
    """Catálogo configurable de daños/causas de descarte de neumáticos."""
    __tablename__ = "eam_dano_neumatico_catalogo"
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(50), unique=True, nullable=False)
    nombre      = Column(String(150), nullable=False)
    severidad   = Column(String(20), default="MODERADO")   # LEVE/MODERADO/GRAVE
    descripcion = Column(String(300))
    # accion sugerida: REENCAUCHE / DESCARTE / INSPECCION
    accion      = Column(String(30), default="INSPECCION")
    activo      = Column(Boolean, default=True)


class EAMInspeccionNeumatico(Base, TimestampMixin):
    """Inspección periódica de un neumático: profundidad multipunto, presión y estado."""
    __tablename__ = "eam_inspeccion_neumatico"
    id                 = Column(Integer, primary_key=True, index=True)
    neumatico_id       = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    fecha              = Column(DateTime, nullable=False)
    profundidad_izq    = Column(Float, nullable=True)   # mm
    profundidad_centro = Column(Float, nullable=True)   # mm
    profundidad_der    = Column(Float, nullable=True)   # mm
    presion_psi        = Column(Float, nullable=True)
    km_odometro        = Column(Float, nullable=True)
    posicion           = Column(String(30), nullable=True)
    estado_visual      = Column(String(30), nullable=True)   # BUENO/REGULAR/CRITICO
    observaciones      = Column(Text, nullable=True)
    tecnico            = Column(String(100), nullable=True)


class EAMReencaucheLote(Base, TimestampMixin):
    """Encabezado de un lote de reencauche enviado a un proveedor."""
    __tablename__ = "eam_reencauche_lote"
    id            = Column(Integer, primary_key=True, index=True)
    codigo        = Column(String(40), unique=True, nullable=False)
    fecha_envio   = Column(Date, nullable=False)
    proveedor     = Column(String(150), nullable=True)
    remision      = Column(String(80), nullable=True)
    observaciones = Column(Text, nullable=True)
    estado        = Column(String(20), default="ABIERTO")   # ABIERTO / CERRADO


class EAMReencaucheDetalle(Base, TimestampMixin):
    """Detalle por neumático dentro de un lote de reencauche."""
    __tablename__ = "eam_reencauche_detalle"
    id                = Column(Integer, primary_key=True, index=True)
    lote_id           = Column(Integer, ForeignKey("eam_reencauche_lote.id"), nullable=False)
    neumatico_id      = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    banda             = Column(String(80), nullable=True)   # legacy: texto libre si no viene del catálogo
    banda_id          = Column(Integer, ForeignKey("eam_banda_reencauche.id"), nullable=True)
    # PENDIENTE / REENCAUCHADA / REMANENTE / RECHAZO
    resultado         = Column(String(20), default="PENDIENTE")
    profundidad_nueva = Column(Float, nullable=True)
    vida_remanente_km = Column(Float, nullable=True)
    costo             = Column(Float, nullable=True)


class EAMNeumaticoConfig(Base, TimestampMixin):
    """Parámetros globales del módulo de llantas (fila única id=1)."""
    __tablename__ = "eam_neumatico_config"
    id                   = Column(Integer, primary_key=True, index=True)
    montaje_estricto     = Column(Boolean, default=True)
    profundidad_minima   = Column(Float, default=3.0)    # mm
    presion_min          = Column(Float, default=90.0)   # psi
    presion_max          = Column(Float, default=120.0)  # psi
    umbral_desalineacion = Column(Float, default=2.0)    # mm de diferencia por eje
    # Cuánto puede SUBIR una profundidad respecto de la anterior sin que se
    # considere un error. Un profundímetro no da el mismo número dos veces
    # seguidas —cambia el punto exacto del surco, la presión de la mano—, así que
    # rechazar cualquier aumento haría rebotar mediciones legítimas y la gente
    # aprendería a rodear la validación. Medio milímetro cubre esa variación;
    # más que eso es un dato equivocado, porque una llanta no recupera labrado.
    tolerancia_profundidad = Column(Float, default=0.5)   # mm


# ─── Catálogos de configuración de llantas (zonas, bandas, motivos, ajustes,
#     esquemas de vehículo y trabajos con periodicidad) ────────────────────────

class EAMZonaNeumatico(Base, TimestampMixin):
    """Zona de segmentación/visibilidad de llantas (p.ej. por sede o regional)."""
    __tablename__ = "eam_zona_neumatico"
    id     = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(30), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    activo = Column(Boolean, default=True)


class EAMBandaReencauche(Base, TimestampMixin):
    """Catálogo de bandas (insumo) usadas al reencauchar una carcasa."""
    __tablename__ = "eam_banda_reencauche"
    id                   = Column(Integer, primary_key=True, index=True)
    marca                = Column(String(100), nullable=False)
    referencia           = Column(String(100))
    dimension            = Column(String(50))
    profundidad_original = Column(Float, nullable=True)
    profundidad_minima   = Column(Float, nullable=True)
    tipo_posicion        = Column(String(20), nullable=True)   # DIRECCIONAL/TRACCION/REMOLQUE/MULTIPOSICION
    sentido_rotacion     = Column(String(20), nullable=True)   # UNIDIRECCIONAL/BIDIRECCIONAL
    reesculturable       = Column(Boolean, default=False)
    costo_defecto        = Column(Float, nullable=True)
    presion_minima       = Column(Float, nullable=True)
    presion_maxima       = Column(Float, nullable=True)
    comentarios          = Column(Text, nullable=True)
    activo               = Column(Boolean, default=True)


class EAMMotivoFinVida(Base, TimestampMixin):
    """Causa de descarte o de cierre de una vida de la llanta (explosión, desgaste normal, etc.)."""
    __tablename__ = "eam_motivo_fin_vida"
    id               = Column(Integer, primary_key=True, index=True)
    nombre           = Column(String(150), nullable=False)
    aplica_descarte  = Column(Boolean, default=True)
    aplica_fin_vida  = Column(Boolean, default=True)
    activo           = Column(Boolean, default=True)


class EAMAjusteNeumaticoCatalogo(Base, TimestampMixin):
    """Categorías de ajuste (deducción de valor) definidas libremente por el usuario."""
    __tablename__ = "eam_ajuste_neumatico_catalogo"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    activo = Column(Boolean, default=True)


class EAMAjusteNeumatico(Base, TimestampMixin):
    """Aplicación real de un ajuste sobre una llanta específica (reduce su valor para CPK)."""
    __tablename__ = "eam_ajuste_neumatico"
    id            = Column(Integer, primary_key=True, index=True)
    neumatico_id  = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    motivo_id     = Column(Integer, ForeignKey("eam_ajuste_neumatico_catalogo.id"), nullable=False)
    fecha         = Column(Date, nullable=False)
    valor         = Column(Float, nullable=False)
    comentarios   = Column(Text, nullable=True)


class EAMEsquemaVehiculo(Base, TimestampMixin):
    """Plantilla reutilizable de configuración de ejes/repuestos por tipo de vehículo."""
    __tablename__ = "eam_esquema_vehiculo"
    id                  = Column(Integer, primary_key=True, index=True)
    codigo              = Column(String(30), unique=True, nullable=True)
    nombre              = Column(String(150), nullable=False)
    tipo_activo         = Column(String(30), nullable=True)
    numero_ejes         = Column(Integer, nullable=False, default=2)
    # Cantidad de llantas por cada eje, en orden (ej. [2,4,4] = eje1 simple,
    # ejes 2-3 duales). Si es NULL, se asume el patrón clásico (eje1=2, resto=4).
    layout              = Column(JSON, nullable=True)
    tiene_repuesto      = Column(Boolean, default=True)
    cantidad_repuestos  = Column(Integer, default=1)
    observaciones       = Column(Text, nullable=True)
    activo              = Column(Boolean, default=True)


class EAMEsquemaAsignacion(Base, TimestampMixin):
    """Historial de asignación de un esquema de llantas a un vehículo, con vigencia."""
    __tablename__ = "eam_esquema_asignacion"
    id             = Column(Integer, primary_key=True, index=True)
    activo_id      = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    esquema_id     = Column(Integer, ForeignKey("eam_esquema_vehiculo.id"), nullable=False)
    fecha_vigencia = Column(Date, nullable=False)
    observaciones  = Column(Text, nullable=True)


class EAMTrabajoNeumatico(Base, TimestampMixin):
    """Tipo de trabajo/reparación aplicable a una llanta (más allá de inspección/rotación)."""
    __tablename__ = "eam_trabajo_neumatico"
    id                 = Column(Integer, primary_key=True, index=True)
    nombre             = Column(String(150), nullable=False)
    observaciones      = Column(Text, nullable=True)
    es_predeterminado  = Column(Boolean, default=False)
    activo             = Column(Boolean, default=True)


class EAMPeriodicidadTrabajoNeumatico(Base, TimestampMixin):
    """Frecuencia (km/horas/días) con la que debe repetirse un trabajo, por tipo de vehículo."""
    __tablename__ = "eam_periodicidad_trabajo_neumatico"
    id           = Column(Integer, primary_key=True, index=True)
    trabajo_id   = Column(Integer, ForeignKey("eam_trabajo_neumatico.id"), nullable=False)
    tipo_activo  = Column(String(30), nullable=True)
    valor        = Column(Float, nullable=False)
    unidad       = Column(String(15), nullable=False, default="KILOMETROS")   # KILOMETROS/HORAS/DIAS
    activo       = Column(Boolean, default=True)


class EAMTrabajoRealizadoNeumatico(Base, TimestampMixin):
    """Registro de un trabajo/reparación efectivamente realizado sobre una llanta."""
    __tablename__ = "eam_trabajo_realizado_neumatico"
    id              = Column(Integer, primary_key=True, index=True)
    neumatico_id    = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    trabajo_id      = Column(Integer, ForeignKey("eam_trabajo_neumatico.id"), nullable=False)
    fecha           = Column(DateTime, nullable=False)
    km_odometro     = Column(Float, nullable=True)
    cantidad        = Column(Integer, default=1)
    costo_unitario  = Column(Float, nullable=True)
    proveedor       = Column(String(150), nullable=True)
    observaciones   = Column(Text, nullable=True)


class EAMReesculturado(Base, TimestampMixin):
    """Re-grooving: corta más profundidad en el remanente de caucho sin cambiar
    la carcasa. Es la única transición del ciclo de vida que se puede deshacer."""
    __tablename__ = "eam_reesculturado_neumatico"
    id                     = Column(Integer, primary_key=True, index=True)
    neumatico_id           = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    fecha                  = Column(DateTime, nullable=False)
    km_odometro            = Column(Float, nullable=True)
    proveedor              = Column(String(150), nullable=True)
    costo                  = Column(Float, nullable=True)
    profundidad_anterior   = Column(Float, nullable=True)
    profundidad_nueva      = Column(Float, nullable=True)
    deshecho               = Column(Boolean, default=False)
    fecha_deshecho         = Column(DateTime, nullable=True)


class EAMVidaNeumatico(Base, TimestampMixin):
    """Periodo operativo de una llanta entre cambios de carcasa (nueva → reencauchada
    → ...). Cada vida acumula sus propias métricas de km y costo."""
    __tablename__ = "eam_vida_neumatico"
    id                   = Column(Integer, primary_key=True, index=True)
    neumatico_id         = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    numero_vida          = Column(Integer, nullable=False, default=1)
    tipo                 = Column(String(20), nullable=False, default="NUEVA")   # NUEVA/REENCAUCHADA
    fecha_inicio         = Column(DateTime, nullable=False)
    fecha_fin            = Column(DateTime, nullable=True)
    km_inicio            = Column(Float, default=0)
    km_fin               = Column(Float, nullable=True)
    costo                = Column(Float, nullable=True)
    profundidad_inicial  = Column(Float, nullable=True)
    profundidad_final    = Column(Float, nullable=True)
    motivo_cierre_id     = Column(Integer, ForeignKey("eam_motivo_fin_vida.id"), nullable=True)


class EAMCongeladoNeumatico(Base, TimestampMixin):
    """Encabezado de un snapshot ('congelado') del catálogo de llantas, para
    comparar la evolución de costo/km y mm/km entre periodos."""
    __tablename__ = "eam_congelado_neumatico"
    id          = Column(Integer, primary_key=True, index=True)
    fecha       = Column(DateTime, nullable=False)
    descripcion = Column(String(255), nullable=True)


class EAMCongeladoDetalleNeumatico(Base, TimestampMixin):
    """Fila de un snapshot: valores calculados de una llanta al momento de congelar."""
    __tablename__ = "eam_congelado_detalle_neumatico"
    id              = Column(Integer, primary_key=True, index=True)
    congelado_id    = Column(Integer, ForeignKey("eam_congelado_neumatico.id"), nullable=False)
    neumatico_id    = Column(Integer, ForeignKey("eam_neumatico.id"), nullable=False)
    codigo          = Column(String(50), nullable=False)
    marca           = Column(String(100), nullable=True)
    medida          = Column(String(50), nullable=True)
    estado          = Column(String(30), nullable=True)
    km_total        = Column(Float, nullable=True)
    costo           = Column(Float, nullable=True)
    costo_neto      = Column(Float, nullable=True)
    cpk             = Column(Float, nullable=True)
    costo_mm        = Column(Float, nullable=True)
    mm_gastados     = Column(Float, nullable=True)


# ─── Combustible ──────────────────────────────────────────────────────────────

class EAMRegistroCombustible(Base, TimestampMixin):
    __tablename__ = "eam_registro_combustible"
    __table_args__ = (
        Index("ix_eam_combustible_activo_fecha", "activo_id", "fecha"),
    )
    id               = Column(Integer, primary_key=True, index=True)
    activo_id        = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    fecha            = Column(DateTime, nullable=False)
    tipo_combustible = Column(String(50))

    # La cantidad lleva su unidad al lado. En Colombia el combustible se compra
    # por galones y el rendimiento se mide en km/gal, pero hay equipos que se
    # cargan por litros: guardar el número sin decir de qué es la receta para
    # que alguien divida peras entre manzanas.
    cantidad = Column(Float, nullable=False)
    unidad   = Column(String(10), default="GALON", nullable=False)   # GALON | LITRO

    precio_unitario = Column(Float)
    subtotal        = Column(Float)
    iva_pct         = Column(Float, default=0)
    iva_valor       = Column(Float)
    costo_total     = Column(Float)

    odometro   = Column(Float)
    horometro  = Column(Float)

    # Kilómetros recorridos desde el tanqueo lleno anterior, y el rendimiento
    # que resulta. Se calculan al registrar y se guardan: recomputarlos en cada
    # informe obligaría a recorrer todo el histórico del vehículo.
    km_recorridos = Column(Float, nullable=True)
    rendimiento   = Column(Float, nullable=True)   # km por galón

    # Sin esto el rendimiento no se puede calcular de forma confiable: solo
    # entre dos tanqueos llenos se sabe cuánto combustible consumió realmente
    # la distancia recorrida.
    tanque_lleno = Column(Boolean, default=True, nullable=False)

    # Meta vigente al momento del tanqueo y si la cumplió. Se congelan porque
    # las metas cambian, y un registro de hace un año tiene que seguir
    # explicando por qué generó o no una alerta.
    meta_km_gal = Column(Float, nullable=True)
    cumple_meta = Column(Boolean, nullable=True)
    desviacion_pct = Column(Float, nullable=True)

    proveedor     = Column(String(100))
    factura       = Column(String(60))
    conductor     = Column(String(100))
    estacion      = Column(String(150))
    observaciones = Column(Text)
    registrado_por = Column(String(100))


class EAMMetaRendimiento(Base, TimestampMixin):
    """Meta de kilómetros por galón, declarada por jerarquía.

    El ámbito va de lo general a lo particular y el más específico manda:

        tipo de activo → marca → línea → marca de motor → línea de motor

    Cualquier nivel vacío significa «cualquiera». Así se puede fijar una meta
    para toda la flota de tractocamiones y afinarla para los que llevan un motor
    concreto, sin escribir una meta por placa.

    La tolerancia existe porque un rendimiento nunca da exacto: un tanqueo en
    montaña rinde menos que uno en carretera plana, y alertar por una décima
    convertiría el módulo en ruido que nadie mira.
    """
    __tablename__ = "eam_meta_rendimiento"
    id = Column(Integer, primary_key=True, index=True)

    tipo_activo = Column(String(50), nullable=True, index=True)
    marca       = Column(String(100), nullable=True)
    linea       = Column(String(100), nullable=True)
    motor_marca = Column(String(100), nullable=True)
    motor_linea = Column(String(100), nullable=True)

    meta_km_gal    = Column(Float, nullable=False)
    # Porcentaje por debajo de la meta que se tolera antes de alertar.
    tolerancia_pct = Column(Float, default=5, nullable=False)
    tipo_combustible = Column(String(50), nullable=True)

    nota   = Column(String(300), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)


# ─── Garantías ────────────────────────────────────────────────────────────────

class EAMGarantia(Base, TimestampMixin):
    __tablename__ = "eam_garantia"
    id              = Column(Integer, primary_key=True, index=True)
    activo_id       = Column(Integer, ForeignKey("eam_activo.id"), nullable=True)
    tipo            = Column(String(50))  # ACTIVO, REPUESTO, SERVICIO
    descripcion     = Column(String(300), nullable=False)
    proveedor       = Column(String(100))
    numero_garantia = Column(String(100))
    fecha_inicio    = Column(Date, nullable=False)
    fecha_fin       = Column(Date, nullable=False)
    condiciones     = Column(Text)
    estado          = Column(String(30), default="VIGENTE")
    valor_cubierto  = Column(Float)
    # Contador y última fecha de reclamo. Se conservan porque la API los expone
    # desde antes, pero la API los CALCULA desde `eam_garantia_reclamacion`: un
    # contador guardado se desincroniza en cuanto alguien borra un reclamo, y
    # entonces la pantalla dice «3 reclamaciones» sobre una lista de dos.
    reclamaciones   = Column(Integer, default=0)
    ultimo_reclamo  = Column(Date)

    # ── Lo que la pantalla mostraba y la tabla no guardaba ──
    # Qué cubre, una por línea. Va como texto y no como tabla aparte porque es
    # una lista de frases que solo se lee completa; nadie filtra por ella.
    cobertura          = Column(Text)
    contacto_proveedor = Column(String(120))
    telefono_proveedor = Column(String(40))
    # Nombre del documento del contrato. El archivo en sí va por adjuntos.
    documento          = Column(String(300))
    # Quién responde por la garantía adentro, no en el proveedor.
    responsable        = Column(String(120))


class EAMParametro(Base, TimestampMixin):
    """Umbrales de aviso del CMMS. Solo entran los que algún cálculo lee: la
    pantalla de umbrales tenía siete valores que no llegaban a ninguna parte,
    y mientras tanto garantías avisaba a 90 días y el tablero a 30."""
    __tablename__ = "eam_parametro"
    id    = Column(Integer, primary_key=True, index=True)
    clave = Column(String(60), unique=True, nullable=False)
    valor = Column(Float, nullable=False)


class EAMAdjuntoGarantia(Base, TimestampMixin):
    """Los documentos de una garantía: el contrato, la factura de compra, el
    certificado del fabricante. Antes solo se podía escribir el NOMBRE del
    documento y el archivo había que subirlo aparte en otro lado.

    Mismo criterio que los adjuntos de OT: la ruta en disco lleva el esquema,
    y la descarga pasa por la API, nunca por una carpeta pública.
    """
    __tablename__ = "eam_adjunto_garantia"
    id          = Column(Integer, primary_key=True, index=True)
    garantia_id = Column(Integer, ForeignKey("eam_garantia.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre      = Column(String(200), nullable=False)
    ruta        = Column(String(400), nullable=False)
    tipo_mime   = Column(String(120))
    tamano      = Column(Integer)
    subido_por  = Column(String(120))


class EAMGarantiaReclamacion(Base, TimestampMixin):
    """Un reclamo hecho al proveedor al amparo de una garantía.

    Es la parte que decide si el módulo sirve: una garantía sin reclamos es un
    archivo de documentos, y lo que la vuelve dinero es cuánto se pidió, cuánto
    se recuperó y en cuántos días. De ahí sale la tasa de recuperación, que es
    el único número con el que se puede negociar el siguiente contrato.
    """
    __tablename__ = "eam_garantia_reclamacion"
    id               = Column(Integer, primary_key=True, index=True)
    garantia_id      = Column(Integer, ForeignKey("eam_garantia.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    fecha            = Column(Date, nullable=False)
    descripcion      = Column(Text, nullable=False)
    monto_solicitado = Column(Float)
    monto_recuperado = Column(Float)
    # EN_PROCESO | APROBADA | RECHAZADA | CERRADA
    estado           = Column(String(20), default="EN_PROCESO", nullable=False)
    responsable      = Column(String(120))
    resolucion       = Column(Text)
    # Cuándo se cerró la gestión. Los días de gestión se derivan de acá y no se
    # guardan: un número de días guardado se queda quieto mientras el reclamo
    # sigue abierto, y es justo el dato que hay que vigilar.
    fecha_cierre     = Column(Date)


# ─── FMEA ─────────────────────────────────────────────────────────────────────

class EAMFMEA(Base, TimestampMixin):
    __tablename__ = "eam_fmea"
    id                 = Column(Integer, primary_key=True, index=True)
    activo_id          = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    componente_id      = Column(Integer, ForeignKey("eam_componente.id"), nullable=True)
    funcion            = Column(String(300), nullable=False)
    modo_falla         = Column(String(300), nullable=False)
    efecto_falla       = Column(Text)
    causa_falla        = Column(Text)
    severidad          = Column(Integer)
    ocurrencia         = Column(Integer)
    detectabilidad     = Column(Integer)
    npn                = Column(Integer)
    accion_recomendada = Column(Text)
    responsable        = Column(String(100))
    fecha_accion       = Column(Date)
    estado             = Column(String(30), default="PENDIENTE")
    severidad_post     = Column(Integer)
    ocurrencia_post    = Column(Integer)
    detectabilidad_post = Column(Integer)
    npn_post           = Column(Integer)


# ─── Calibraciones ────────────────────────────────────────────────────────────

class EAMCalibracion(Base, TimestampMixin):
    __tablename__ = "eam_calibracion"
    id                 = Column(Integer, primary_key=True, index=True)
    activo_id          = Column(Integer, ForeignKey("eam_activo.id"), nullable=False)
    tipo_instrumento   = Column(String(100))
    numero_certificado = Column(String(100))
    laboratorio        = Column(String(200))
    acreditacion       = Column(String(100))
    fecha_calibracion  = Column(Date, nullable=False)
    fecha_vencimiento  = Column(Date, nullable=False)
    resultado          = Column(String(50))  # CONFORME, NO_CONFORME
    estado             = Column(String(30), default="VIGENTE")
    incertidumbre      = Column(String(100))
    patron_utilizado   = Column(String(200))
    observaciones      = Column(Text)


# ─── KPIs diarios ─────────────────────────────────────────────────────────────

class EAMKPIDiario(Base, TimestampMixin):
    __tablename__ = "eam_kpi_diario"
    id                     = Column(Integer, primary_key=True, index=True)
    fecha                  = Column(Date, nullable=False, unique=True)
    total_activos          = Column(Integer, default=0)
    activos_operativos     = Column(Integer, default=0)
    activos_mantenimiento  = Column(Integer, default=0)
    activos_fuera_servicio = Column(Integer, default=0)
    disponibilidad_pct     = Column(Float, default=0)
    ots_abiertas           = Column(Integer, default=0)
    ots_completadas        = Column(Integer, default=0)
    ots_vencidas           = Column(Integer, default=0)
    ots_preventivas        = Column(Integer, default=0)
    ots_correctivas        = Column(Integer, default=0)
    ots_predictivas        = Column(Integer, default=0)
    cumplimiento_pm_pct    = Column(Float, default=0)
    mtbf_horas             = Column(Float, default=0)
    mttr_horas             = Column(Float, default=0)
    backlog_horas          = Column(Float, default=0)
    costo_mantenimiento    = Column(Float, default=0)
    costo_combustible      = Column(Float, default=0)
    costo_total            = Column(Float, default=0)
    indice_confiabilidad   = Column(Float, default=0)
    alertas_activas        = Column(Integer, default=0)

# ──────────────────────────────────────────
# CATÁLOGO DE VEHÍCULOS / ACTIVOS
# ──────────────────────────────────────────
#
# Misma idea que el catálogo de llantas (marca > referencia > dimensión): el
# dato se preconfigura una vez y en la creación del activo se elige de listas
# encadenadas. Sin esto la ficha técnica se llena a mano y termina con
# "Kenworth", "KENWORTH" y "Ken worth" como tres marcas distintas, lo que
# arruina cualquier reporte por marca o por línea.
#
# La jerarquía es: tipo de activo > marca > línea > modelo. El modelo es la
# hoja y lleva la ficha técnica de referencia (motor, combustible, ejes), que
# el activo hereda al crearse — igual que la referencia+dimensión de una llanta
# aporta su profundidad inicial.


class EAMMotorActivo(Base, TimestampMixin):
    """Catálogo de motores. Se comparte entre modelos: el mismo Cummins ISX15
    monta en varias líneas de varias marcas."""
    __tablename__ = "eam_motor_activo"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_motor_activo_nombre"),)
    id           = Column(Integer, primary_key=True, index=True)
    nombre       = Column(String(120), nullable=False)
    marca        = Column(String(100), nullable=True)   # Cummins, Detroit, Paccar…
    cilindraje_cc = Column(Float, nullable=True)
    potencia_hp  = Column(Float, nullable=True)
    activo       = Column(Boolean, default=True)


class EAMTipoCombustible(Base, TimestampMixin):
    """Catálogo plano de combustibles (Diésel, Gasolina, GNV, Eléctrico…)."""
    __tablename__ = "eam_tipo_combustible"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_tipo_combustible_nombre"),)
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(80), nullable=False)
    activo = Column(Boolean, default=True)


class EAMMarcaActivo(Base, TimestampMixin):
    """Marca del activo, opcionalmente acotada a un tipo.

    `tipo_activo` nulo = la marca sirve para cualquier tipo. Con valor, solo se
    ofrece en ese tipo: así al crear un montacargas no aparecen marcas de
    tractocamión. Se permite el mismo nombre en tipos distintos porque hay
    fabricantes que hacen de todo (Toyota hace carros y montacargas).
    """
    __tablename__ = "eam_marca_activo"
    __table_args__ = (UniqueConstraint("nombre", "tipo_activo", name="uq_eam_marca_activo_nombre_tipo"),)
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(120), nullable=False)
    tipo_activo = Column(String(50), nullable=True)   # código de eam_tipo_activo
    activo      = Column(Boolean, default=True)


class EAMLineaActivo(Base, TimestampMixin):
    """Línea comercial que pertenece a una marca (Kenworth > T880)."""
    __tablename__ = "eam_linea_activo"
    __table_args__ = (UniqueConstraint("marca_id", "nombre", name="uq_eam_linea_activo_marca_nombre"),)
    id       = Column(Integer, primary_key=True, index=True)
    marca_id = Column(Integer, ForeignKey("eam_marca_activo.id", ondelete="CASCADE"), nullable=False)
    nombre   = Column(String(120), nullable=False)
    activo   = Column(Boolean, default=True)


class EAMModeloActivo(Base, TimestampMixin):
    """Versión concreta de una línea, con su ficha técnica de referencia.

    Es la hoja de la jerarquía. Al crear un activo con este modelo se heredan
    motor, combustible, ejes y vida útil, de modo que dos vehículos iguales no
    queden con datos técnicos distintos por quien los registró.
    """
    __tablename__ = "eam_modelo_activo"
    __table_args__ = (UniqueConstraint("linea_id", "nombre", name="uq_eam_modelo_activo_linea_nombre"),)
    id       = Column(Integer, primary_key=True, index=True)
    linea_id = Column(Integer, ForeignKey("eam_linea_activo.id", ondelete="CASCADE"), nullable=False)
    nombre   = Column(String(120), nullable=False)

    anio_desde = Column(Integer, nullable=True)
    anio_hasta = Column(Integer, nullable=True)

    # Ficha técnica que hereda el activo
    motor_id              = Column(Integer, ForeignKey("eam_motor_activo.id", ondelete="SET NULL"), nullable=True)
    tipo_combustible      = Column(String(80), nullable=True)
    capacidad_combustible = Column(Float, nullable=True)
    numero_ejes           = Column(Integer, nullable=True)
    esquema_codigo        = Column(String(50), nullable=True)   # código de eam_esquema_vehiculo
    vida_util_anios       = Column(Integer, nullable=True)
    vida_util_km          = Column(Float, nullable=True)
    capacidad_kg          = Column(Float, nullable=True)

    activo = Column(Boolean, default=True)

class EAMCatalogoActivo(Base, TimestampMixin):
    """Catálogo plano y multi-tipo de los campos organizativos del activo.

    Una sola tabla con discriminador en lugar de seis tablas casi idénticas:
    sede, área, ubicación, responsable, cuenta contable y centro de costo
    comparten forma (nombre + código opcional) y solo cambian de significado.

    Existe por lo mismo que el resto del catálogo: si la ubicación se escribe a
    mano, "Bodega Norte", "bodega norte" y "Bod. Norte" cuentan como tres y
    ningún reporte por ubicación cuadra.
    """
    __tablename__ = "eam_catalogo_activo"
    __table_args__ = (UniqueConstraint("tipo", "nombre", name="uq_eam_catalogo_activo_tipo_nombre"),)
    id     = Column(Integer, primary_key=True, index=True)
    # SEDE | AREA | UBICACION | RESPONSABLE | CUENTA_CONTABLE | CENTRO_COSTO
    tipo   = Column(String(30), nullable=False, index=True)
    nombre = Column(String(160), nullable=False)
    codigo = Column(String(60), nullable=True)   # p. ej. el número de la cuenta contable
    activo = Column(Boolean, default=True)



class EAMAdjuntoOT(Base, TimestampMixin):
    """Los documentos de una orden de trabajo.

    Vive en el esquema del cliente, a diferencia de los adjuntos de soporte:
    una cotización o una factura de mantenimiento son datos operativos suyos, no
    una conversación con quien opera la plataforma.

    Se guarda la ruta y no el contenido: la base no es lugar para binarios. Y la
    ruta lleva el esquema adentro porque dos empresas pueden tener la OT número
    5 — sin eso, una sobrescribiría el archivo de la otra.
    """

    __tablename__ = "eam_adjunto_ot"

    id     = Column(Integer, primary_key=True, index=True)
    ot_id  = Column(Integer, ForeignKey("eam_orden_trabajo.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    # Se copia el número de la OT para poder buscar por él sin cruzar tablas:
    # es como la gente pide los documentos ("los de la OT-2026-0042").
    ot_numero = Column(String(30), index=True)

    # COTIZACION, FACTURA, ORDEN_COMPRA, INFORME_TECNICO, OTRO
    tipo   = Column(String(30), nullable=False, index=True)
    nombre = Column(String(255), nullable=False)
    ruta   = Column(String(400), nullable=False)
    tipo_mime = Column(String(120))
    tamano    = Column(Integer)

    # Datos del documento en sí. Sirven para encontrarlo y para cuadrar costos
    # sin tener que abrir el archivo.
    numero_documento = Column(String(80), index=True)
    fecha_documento  = Column(Date)
    valor            = Column(Float)
    proveedor        = Column(String(160))
    notas            = Column(String(400))

    subido_por = Column(String(80))


# ─── Análisis de causa raíz ───────────────────────────────────────────────────
#
# Un informe estructurado, no un archivo adjunto. La diferencia importa: de un
# PDF adjunto no se puede sacar "cuál es la falla que más nos cuesta en los
# Freightliner"; de campos con estructura, sí. El PDF exportable se genera a
# partir de estos datos, no al revés.

METODOLOGIAS_RCA = ("CINCO_PORQUES", "ISHIKAWA", "ARBOL_FALLOS", "OTRA")
ESTADOS_RCA = ("BORRADOR", "EN_ANALISIS", "CERRADO")


class EAMCausaRaiz(Base, TimestampMixin):
    """El análisis de por qué falló, asociado a una orden de trabajo."""

    __tablename__ = "eam_causa_raiz"

    id        = Column(Integer, primary_key=True, index=True)
    # Uno por orden: dos análisis de la misma falla se contradicen entre sí.
    ot_id     = Column(Integer, ForeignKey("eam_orden_trabajo.id", ondelete="CASCADE"),
                       nullable=False, unique=True, index=True)
    ot_numero = Column(String(30), index=True)
    # Se copia del activo de la OT al guardar, para no depender de que la OT
    # siga existiendo cuando se consulte el histórico.
    activo_id = Column(Integer, index=True)

    fecha_analisis = Column(Date)
    analista       = Column(String(120))
    participantes  = Column(String(400))
    metodologia    = Column(String(30), default="CINCO_PORQUES")
    estado         = Column(String(20), default="BORRADOR", index=True)

    # Qué pasó y cómo nos enteramos.
    descripcion_evento = Column(Text)
    deteccion          = Column(String(300))

    # La clasificación: es lo que después se puede contar y comparar.
    modo_falla     = Column(String(120), index=True)
    categoria_causa = Column(String(120), index=True)

    # El análisis en sí. Los porqués van en JSON porque son una lista de pasos
    # de longitud variable, no cinco campos fijos: a veces bastan tres.
    porques                = Column(JSON)
    causa_inmediata        = Column(Text)
    causa_raiz             = Column(Text)
    factores_contribuyentes = Column(Text)

    # Consecuencias, para poder ordenar por lo que más duele.
    horas_parada     = Column(Float)
    costo_estimado   = Column(Float)
    hubo_lesion      = Column(Boolean, default=False)
    hubo_ambiental   = Column(Boolean, default=False)

    conclusiones          = Column(Text)
    # Si lo que se hizo sirvió. Sin esto, el análisis termina en una lista de
    # buenas intenciones que nadie vuelve a mirar.
    verificacion_eficacia = Column(Text)
    fecha_verificacion    = Column(Date)
    eficaz                = Column(Boolean)

    elaborado_por = Column(String(80))


class EAMCausaRaizAccion(Base):
    """Lo que se decidió hacer para que no vuelva a pasar."""

    __tablename__ = "eam_causa_raiz_accion"

    id            = Column(Integer, primary_key=True, index=True)
    causa_raiz_id = Column(Integer, ForeignKey("eam_causa_raiz.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    # CORRECTIVA arregla lo que pasó; PREVENTIVA evita que vuelva. Mezclarlas
    # hace que un análisis parezca completo cuando solo se apagó el incendio.
    tipo          = Column(String(20), default="CORRECTIVA")
    descripcion   = Column(Text, nullable=False)
    responsable   = Column(String(120))
    fecha_compromiso = Column(Date)
    estado        = Column(String(20), default="PENDIENTE")
    fecha_cierre  = Column(Date)
    orden         = Column(Integer, default=0)


class EAMCausaRaizEvidencia(Base, TimestampMixin):
    """Fotos y archivos que sustentan el análisis.

    Van aparte de los adjuntos de la OT: aquellos son los soportes comerciales
    —cotización, factura, orden de compra— y estos son la evidencia técnica que
    se embebe en el informe exportado.
    """

    __tablename__ = "eam_causa_raiz_evidencia"

    id            = Column(Integer, primary_key=True, index=True)
    causa_raiz_id = Column(Integer, ForeignKey("eam_causa_raiz.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    nombre      = Column(String(255), nullable=False)
    ruta        = Column(String(400), nullable=False)
    tipo_mime   = Column(String(120))
    tamano      = Column(Integer)
    # El pie de foto del informe. Una evidencia sin explicación no prueba nada.
    descripcion = Column(String(400))
    orden       = Column(Integer, default=0)
    subido_por  = Column(String(80))
