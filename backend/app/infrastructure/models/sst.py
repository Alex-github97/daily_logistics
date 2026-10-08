import enum
from sqlalchemy import Column, Integer, String, Boolean, Enum, Float, Date, Text, UniqueConstraint
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


# ─── Enums ────────────────────────────────────────────────────────────────────

class TipoIncidenteSST(str, enum.Enum):
    ACCIDENTE_TRABAJO = "ACCIDENTE_TRABAJO"
    INCIDENTE         = "INCIDENTE"
    ENFERMEDAD_LABORAL= "ENFERMEDAD_LABORAL"
    CASI_ACCIDENTE    = "CASI_ACCIDENTE"

class GravedadSST(str, enum.Enum):
    LEVE      = "LEVE"
    MODERADO  = "MODERADO"
    GRAVE     = "GRAVE"
    MUY_GRAVE = "MUY_GRAVE"
    MORTAL    = "MORTAL"

class EstadoIncidenteSST(str, enum.Enum):
    REPORTADO       = "REPORTADO"
    EN_INVESTIGACION= "EN_INVESTIGACION"
    INVESTIGADO     = "INVESTIGADO"
    CERRADO         = "CERRADO"

class ClasePeligroSST(str, enum.Enum):
    FISICO              = "FISICO"
    QUIMICO             = "QUIMICO"
    BIOLOGICO           = "BIOLOGICO"
    BIOMECANICO         = "BIOMECANICO"
    PSICOSOCIAL         = "PSICOSOCIAL"
    SEGURIDAD           = "SEGURIDAD"
    FENOMENOS_NATURALES = "FENOMENOS_NATURALES"
    PUBLICO             = "PUBLICO"

class NivelRiesgoSST(str, enum.Enum):
    ACEPTABLE   = "ACEPTABLE"
    BAJO        = "BAJO"
    MEDIO       = "MEDIO"
    ALTO        = "ALTO"
    INACEPTABLE = "INACEPTABLE"

class EstadoInspeccionSST(str, enum.Enum):
    PROGRAMADA = "PROGRAMADA"
    EN_CURSO   = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    CANCELADA  = "CANCELADA"

class TipoEPP(str, enum.Enum):
    CABEZA      = "CABEZA"
    OJOS_CARA   = "OJOS_CARA"
    AUDITIVO    = "AUDITIVO"
    RESPIRATORIO= "RESPIRATORIO"
    MANOS       = "MANOS"
    PIES        = "PIES"
    CUERPO      = "CUERPO"
    CAIDAS      = "CAIDAS"

class EstadoCapacitacionSST(str, enum.Enum):
    PROGRAMADA = "PROGRAMADA"
    EN_CURSO   = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    CANCELADA  = "CANCELADA"

class TipoDocumentoSST(str, enum.Enum):
    POLITICA    = "POLITICA"
    PROCEDIMIENTO = "PROCEDIMIENTO"
    INSTRUCTIVO = "INSTRUCTIVO"
    FORMATO     = "FORMATO"
    REGISTRO    = "REGISTRO"
    PROGRAMA    = "PROGRAMA"
    PLAN        = "PLAN"


# ─── Modelos ──────────────────────────────────────────────────────────────────

class SstIncidente(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sst_incidentes"
    __table_args__ = {"extend_existing": True}

    id                   = Column(Integer, primary_key=True, index=True)
    numero               = Column(String(50), unique=True, nullable=False, index=True)
    tipo                 = Column(Enum(TipoIncidenteSST), nullable=False)
    gravedad             = Column(Enum(GravedadSST))
    estado               = Column(Enum(EstadoIncidenteSST), default=EstadoIncidenteSST.REPORTADO, nullable=False)
    fecha_evento         = Column(Date, nullable=False)
    hora_evento          = Column(String(5))
    lugar                = Column(String(200))
    trabajador           = Column(String(150))
    cargo                = Column(String(100))
    area                 = Column(String(100))
    descripcion          = Column(Text)
    causa_inmediata      = Column(Text)
    causa_basica         = Column(Text)
    dias_incapacidad     = Column(Integer, default=0)
    acciones_correctivas = Column(Text)
    investigador         = Column(String(150))
    fecha_cierre         = Column(Date)


class SstRiesgo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sst_riesgos"
    __table_args__ = {"extend_existing": True}

    id                   = Column(Integer, primary_key=True, index=True)
    codigo               = Column(String(50), unique=True, index=True)
    proceso              = Column(String(150))
    area                 = Column(String(100))
    actividad            = Column(String(200))
    clase_peligro        = Column(Enum(ClasePeligroSST))
    descripcion_peligro  = Column(Text)
    efecto_posible       = Column(Text)
    nivel_riesgo         = Column(Enum(NivelRiesgoSST))
    probabilidad         = Column(Integer)
    impacto              = Column(Integer)
    # GTC 45: el nivel de riesgo sale de estos tres, no se escoge a mano.
    # `probabilidad` e `impacto` quedan de la versión anterior, sin uso.
    nivel_deficiencia    = Column(Integer)
    nivel_exposicion     = Column(Integer)
    nivel_consecuencia   = Column(Integer)
    expuestos            = Column(Integer)
    controles_existentes = Column(Text)
    controles_propuestos = Column(Text)
    responsable          = Column(String(150))
    fecha_revision       = Column(Date)


class SstInspeccion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sst_inspecciones"
    __table_args__ = {"extend_existing": True}

    id                = Column(Integer, primary_key=True, index=True)
    numero            = Column(String(50), unique=True, nullable=False, index=True)
    tipo              = Column(String(50))
    area              = Column(String(100))
    estado            = Column(Enum(EstadoInspeccionSST), default=EstadoInspeccionSST.PROGRAMADA, nullable=False)
    fecha_programada  = Column(Date)
    fecha_realizacion = Column(Date)
    inspector         = Column(String(150))
    descripcion       = Column(Text)
    hallazgos_count   = Column(Integer, default=0)
    puntuacion        = Column(Float)
    observaciones     = Column(Text)


class SstEntregaEPP(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sst_entregas_epp"
    __table_args__ = {"extend_existing": True}

    id                = Column(Integer, primary_key=True, index=True)
    numero            = Column(String(50), unique=True, nullable=False, index=True)
    trabajador        = Column(String(150), nullable=False)
    cargo             = Column(String(100))
    area              = Column(String(100))
    tipo_epp          = Column(Enum(TipoEPP), nullable=False)
    descripcion_epp   = Column(String(200))
    cantidad          = Column(Integer, default=1)
    fecha_entrega     = Column(Date, nullable=False)
    fecha_vencimiento = Column(Date)
    firma_recibido    = Column(Boolean, default=False)
    devuelto          = Column(Boolean, default=False)
    fecha_devolucion  = Column(Date)
    motivo_devolucion = Column(Text)


class SstCapacitacion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sst_capacitaciones"
    __table_args__ = {"extend_existing": True}

    id                = Column(Integer, primary_key=True, index=True)
    codigo            = Column(String(50), unique=True, index=True)
    titulo            = Column(String(200), nullable=False)
    tipo              = Column(String(50))
    modalidad         = Column(String(50))
    estado            = Column(Enum(EstadoCapacitacionSST), default=EstadoCapacitacionSST.PROGRAMADA)
    instructor        = Column(String(150))
    fecha_inicio      = Column(Date)
    fecha_fin         = Column(Date)
    duracion_horas    = Column(Float)
    max_participantes = Column(Integer)
    participantes     = Column(Integer, default=0)
    area_dirigida     = Column(String(100))
    descripcion       = Column(Text)
    evaluacion_prom   = Column(Float)


class SstDocumento(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sst_documentos"
    __table_args__ = {"extend_existing": True}

    id               = Column(Integer, primary_key=True, index=True)
    codigo           = Column(String(50), unique=True, index=True)
    titulo           = Column(String(300), nullable=False)
    tipo             = Column(Enum(TipoDocumentoSST), nullable=False)
    version          = Column(String(20), default='1.0')
    estado           = Column(String(30), default='VIGENTE')
    area_responsable = Column(String(100))
    responsable      = Column(String(150))
    fecha_aprobacion = Column(Date)
    fecha_revision   = Column(Date)
    descripcion      = Column(Text)
    url_documento    = Column(String(500))


# ─── Emergencias, períodos y configuración ────────────────────────────────────

class SstBrigadista(Base, TimestampMixin, SoftDeleteMixin):
    """Integrante de la brigada de emergencias.

    La certificación no es un sí/no: vence. Se guarda hasta cuándo es válida y
    la pantalla calcula si está vigente, en vez de un «certificado: sí» que
    sigue diciendo sí años después de vencido.
    """
    __tablename__ = "sst_brigadistas"
    __table_args__ = {"extend_existing": True}

    id                 = Column(Integer, primary_key=True, index=True)
    nombre             = Column(String(150), nullable=False)
    cargo              = Column(String(100))
    area               = Column(String(100))
    rol                = Column(String(60), nullable=False)
    telefono           = Column(String(40))
    certificado_hasta  = Column(Date)


class SstSimulacro(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sst_simulacros"
    __table_args__ = {"extend_existing": True}

    id                   = Column(Integer, primary_key=True, index=True)
    fecha                = Column(Date, nullable=False)
    tipo                 = Column(String(120), nullable=False)
    participantes        = Column(Integer)
    tiempo_respuesta_seg = Column(Integer)
    resultado            = Column(String(30))
    observaciones        = Column(Text)
    acciones_mejora      = Column(Text)


class SstPeriodo(Base, TimestampMixin):
    """Trabajadores y horas-hombre de un mes.

    Sin este dato no hay indicador que calcular: la frecuencia y la severidad
    son accidentes y días perdidos DIVIDIDOS por la exposición. La maqueta
    mostraba un «IF 7,0» sin que el sistema supiera cuántas horas se trabajaron.
    """
    __tablename__ = "sst_periodos"
    __table_args__ = (UniqueConstraint("anio", "mes", name="uq_sst_periodo_mes"),
                      {"extend_existing": True})

    id              = Column(Integer, primary_key=True, index=True)
    anio            = Column(Integer, nullable=False)
    mes             = Column(Integer, nullable=False)
    trabajadores    = Column(Integer, nullable=False)
    horas_hombre    = Column(Float, nullable=False)
    dias_ausencia_medica = Column(Float, default=0)
    dias_programados     = Column(Float)


class SstConfig(Base, TimestampMixin):
    """Datos de la empresa ante la ARL y metas de los indicadores. Clave/valor."""
    __tablename__ = "sst_config"
    __table_args__ = {"extend_existing": True}

    id    = Column(Integer, primary_key=True, index=True)
    clave = Column(String(60), nullable=False, unique=True)
    valor = Column(Text)
