"""
GRC - Governance, Risk & Compliance
ISO 31000 · ISO 37301 · ISO 27001 · ISO 22301 · COSO ERM · COBIT · NIST CSF

CÓMO ESTÁ ARMADO
- Lo que CLASIFICA (categoría de riesgo, tipo de comité, marco normativo,
  periodicidad, tipo de hallazgo…) vive en el catálogo maestro (módulo GRC) y
  se configura en Configuración GRC. Las columnas guardan el nombre del valor y
  el servidor lo valida contra el catálogo.
- Lo que gobierna un FLUJO o un CÁLCULO (estados, severidad, naturaleza del
  control, estrategia de tratamiento) es código: cambiarlo a mano rompería la
  lógica que lo usa.
- Las PERSONAS son usuarios de la plataforma con acceso al módulo GRC
  (`*_id → usuarios.id`), no nombres escritos a mano: un nombre mal escrito
  partía en dos al responsable y nadie podía preguntar «qué tiene a cargo».
- Procesos y áreas son los catálogos compartidos de la plataforma (GLOBAL).
- Lo que se relaciona se relaciona con llave: riesgo↔control, control→prueba,
  auditoría→hallazgo→plan, incidente→riesgo/control, y el resto de vínculos
  muchos-a-muchos van por `grc_vinculo`.
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Date, DateTime,
    Numeric, ForeignKey, Enum, JSON, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ────────────────────────────────────────────
# Enums: solo lo que gobierna flujos y cálculos
# ────────────────────────────────────────────

class PrioridadRiesgoGRCEnum(str, enum.Enum):
    BAJA    = "baja"
    MEDIA   = "media"
    ALTA    = "alta"
    CRITICA = "critica"

class EstadoRiesgoGRCEnum(str, enum.Enum):
    IDENTIFICADO = "identificado"
    EN_ANALISIS  = "en_analisis"
    TRATAMIENTO  = "tratamiento"
    ACEPTADO     = "aceptado"
    MITIGADO     = "mitigado"
    CERRADO      = "cerrado"

class TratamientoRiesgoGRCEnum(str, enum.Enum):
    """Las cuatro respuestas de ISO 31000: son la norma, no una preferencia."""
    MITIGAR    = "mitigar"
    TRANSFERIR = "transferir"
    EVITAR     = "evitar"
    ACEPTAR    = "aceptar"

class TipoControlGRCEnum(str, enum.Enum):
    """Naturaleza del control. Decide qué reduce: el preventivo la
    probabilidad, el detectivo y el correctivo el impacto."""
    PREVENTIVO    = "preventivo"
    DETECTIVO     = "detectivo"
    CORRECTIVO    = "correctivo"
    COMPENSATORIO = "compensatorio"

class EfectividadControlGRCEnum(str, enum.Enum):
    EFECTIVO              = "efectivo"
    PARCIALMENTE_EFECTIVO = "parcialmente_efectivo"
    INEFECTIVO            = "inefectivo"
    NO_PROBADO            = "no_probado"

class EstadoPoliticaGRCEnum(str, enum.Enum):
    BORRADOR    = "borrador"
    EN_REVISION = "en_revision"
    APROBADA    = "aprobada"
    PUBLICADA   = "publicada"
    VENCIDA     = "vencida"
    ARCHIVADA   = "archivada"

class EstadoCumplimientoGRCEnum(str, enum.Enum):
    CUMPLE         = "cumple"
    CUMPLE_PARCIAL = "cumple_parcial"
    NO_CUMPLE      = "no_cumple"
    NO_APLICA      = "no_aplica"
    EN_EVALUACION  = "en_evaluacion"

class EstadoAuditoriaGRCEnum(str, enum.Enum):
    PLANIFICADA   = "planificada"
    EN_EJECUCION  = "en_ejecucion"
    EN_REVISION   = "en_revision"
    COMPLETADA    = "completada"
    CANCELADA     = "cancelada"

class SeveridadGRCEnum(str, enum.Enum):
    BAJA    = "baja"
    MEDIA   = "media"
    ALTA    = "alta"
    CRITICA = "critica"

class EstadoHallazgoGRCEnum(str, enum.Enum):
    ABIERTO        = "abierto"
    EN_REMEDIACION = "en_remediacion"
    VERIFICACION   = "verificacion"
    CERRADO        = "cerrado"
    VENCIDO        = "vencido"


def _usuario(nullable=True):
    return Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=nullable)


# ────────────────────────────────────────────
# Gobierno
# ────────────────────────────────────────────

class GRCComite(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_comite'
    id            = Column(Integer, primary_key=True)
    nombre        = Column(String(200), nullable=False)
    tipo          = Column(String(100))          # catálogo GRC/TIPO_COMITE
    periodicidad  = Column(String(50))           # catálogo GRC/PERIODICIDAD
    presidente_id = _usuario()
    secretario_id = _usuario()
    descripcion   = Column(Text)
    quorum_minimo = Column(Integer)              # asistentes para decidir
    activo        = Column(Boolean, default=True)
    riesgos       = relationship('GRCRiesgo', back_populates='comite')


class GRCComiteMiembro(Base, TimestampMixin):
    __tablename__ = 'grc_comite_miembro'
    __table_args__ = (UniqueConstraint('comite_id', 'usuario_id', name='uq_grc_comite_miembro'),)
    id         = Column(Integer, primary_key=True)
    comite_id  = Column(Integer, ForeignKey('grc_comite.id', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='CASCADE'), nullable=False)
    rol        = Column(String(30), default='miembro')   # miembro | invitado
    con_voto   = Column(Boolean, default=True)


class GRCComiteSesion(Base, TimestampMixin, SoftDeleteMixin):
    """Una reunión del comité, con su acta."""
    __tablename__ = 'grc_comite_sesion'
    id           = Column(Integer, primary_key=True)
    comite_id    = Column(Integer, ForeignKey('grc_comite.id', ondelete='CASCADE'), nullable=False, index=True)
    fecha        = Column(Date, nullable=False)
    asistentes   = Column(JSON, default=list)    # ids de usuario
    temas        = Column(Text)
    decisiones   = Column(Text)
    proxima      = Column(Date)
    acta_url     = Column(Text)


class GRCPolitica(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_politica'
    id                     = Column(Integer, primary_key=True)
    codigo                 = Column(String(30), unique=True)
    nombre                 = Column(String(300), nullable=False)
    tipo                   = Column(String(100))     # catálogo GRC/TIPO_POLITICA
    version                = Column(String(20), default='1.0')
    estado                 = Column(Enum(EstadoPoliticaGRCEnum), default=EstadoPoliticaGRCEnum.BORRADOR)
    propietario_id         = _usuario()
    aprobador_id           = _usuario()
    fecha_aprobacion       = Column(Date)
    fecha_vigencia         = Column(Date)
    fecha_revision         = Column(Date)
    periodicidad_revision  = Column(String(50))      # catálogo GRC/PERIODICIDAD
    alcance                = Column(Text)
    descripcion            = Column(Text)
    dms_documento_id       = Column(Integer)
    aceptaciones_requeridas = Column(Boolean, default=False)


class GRCPoliticaAceptacion(Base, TimestampMixin):
    """Quién leyó y aceptó qué versión. Antes era un contador sin nombres."""
    __tablename__ = 'grc_politica_aceptacion'
    __table_args__ = (UniqueConstraint('politica_id', 'usuario_id', 'version',
                                       name='uq_grc_politica_aceptacion'),)
    id          = Column(Integer, primary_key=True)
    politica_id = Column(Integer, ForeignKey('grc_politica.id', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id  = Column(Integer, ForeignKey('usuarios.id', ondelete='CASCADE'), nullable=False)
    version     = Column(String(20), nullable=False)
    fecha       = Column(DateTime(timezone=True), nullable=False)


# ────────────────────────────────────────────
# Cumplimiento
# ────────────────────────────────────────────

class GRCObligacion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_obligacion'
    id                  = Column(Integer, primary_key=True)
    codigo              = Column(String(30), unique=True)
    nombre              = Column(String(300), nullable=False)
    tipo                = Column(String(100))     # catálogo GRC/TIPO_OBLIGACION
    marco               = Column(String(200))     # catálogo GRC/MARCO_NORMATIVO
    articulo            = Column(String(200))     # numeral o artículo dentro del marco
    pais                = Column(String(100))     # catálogo GLOBAL/PAIS
    proceso             = Column(String(200))     # catálogo GLOBAL/PROCESO
    area                = Column(String(200))     # catálogo GLOBAL/AREA
    descripcion         = Column(Text)
    fecha_vigencia      = Column(Date)
    fecha_vencimiento   = Column(Date)
    periodicidad        = Column(String(50))      # cada cuánto se evalúa (GRC/PERIODICIDAD)
    responsable_id      = _usuario()
    estado_cumplimiento = Column(Enum(EstadoCumplimientoGRCEnum), default=EstadoCumplimientoGRCEnum.EN_EVALUACION)
    cumplimientos       = relationship('GRCMatrizCumplimiento', back_populates='obligacion')


class GRCMatrizCumplimiento(Base, TimestampMixin, SoftDeleteMixin):
    """Una evaluación de cumplimiento de una obligación."""
    __tablename__ = 'grc_matriz_cumplimiento'
    id                 = Column(Integer, primary_key=True)
    obligacion_id      = Column(Integer, ForeignKey('grc_obligacion.id'), nullable=False)
    proceso            = Column(String(200))
    area               = Column(String(200))
    responsable_id     = _usuario()
    estado             = Column(Enum(EstadoCumplimientoGRCEnum), default=EstadoCumplimientoGRCEnum.EN_EVALUACION)
    puntaje            = Column(Integer)
    ultima_evaluacion  = Column(Date)
    proxima_evaluacion = Column(Date)
    evidencias         = Column(Text)
    observaciones      = Column(Text)
    obligacion         = relationship('GRCObligacion', back_populates='cumplimientos')


# ────────────────────────────────────────────
# Riesgos y controles
# ────────────────────────────────────────────

class GRCControl(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_control'
    id                  = Column(Integer, primary_key=True)
    codigo              = Column(String(30), unique=True)
    nombre              = Column(String(300), nullable=False)
    tipo                = Column(Enum(TipoControlGRCEnum))
    descripcion         = Column(Text)
    proceso             = Column(String(200))     # GLOBAL/PROCESO
    area                = Column(String(200))     # GLOBAL/AREA
    responsable_id      = _usuario()
    frecuencia          = Column(String(100))     # GRC/FRECUENCIA_CONTROL: cada cuánto OPERA
    periodicidad_prueba = Column(String(50))      # GRC/PERIODICIDAD: cada cuánto se PRUEBA
    # La efectividad y las fechas de prueba salen de las pruebas registradas;
    # no se escriben a mano.
    efectividad         = Column(Enum(EfectividadControlGRCEnum), default=EfectividadControlGRCEnum.NO_PROBADO)
    ultima_evaluacion   = Column(Date)
    proxima_evaluacion  = Column(Date)
    automatizado        = Column(Boolean, default=False)
    activo              = Column(Boolean, default=True)
    pruebas             = relationship('GRCPruebaControl', back_populates='control')


class GRCPruebaControl(Base, TimestampMixin, SoftDeleteMixin):
    """Prueba de diseño o de efectividad operativa de un control."""
    __tablename__ = 'grc_prueba_control'
    id            = Column(Integer, primary_key=True)
    control_id    = Column(Integer, ForeignKey('grc_control.id', ondelete='CASCADE'), nullable=False, index=True)
    tipo          = Column(String(20), nullable=False, default='efectividad')   # diseno | efectividad
    fecha         = Column(Date, nullable=False)
    probador_id   = _usuario()
    resultado     = Column(Enum(EfectividadControlGRCEnum), nullable=False)
    muestra       = Column(Integer)
    excepciones   = Column(Integer)
    procedimiento = Column(Text)
    conclusion    = Column(Text)
    control       = relationship('GRCControl', back_populates='pruebas')


class GRCRiesgo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_riesgo'
    id                      = Column(Integer, primary_key=True)
    codigo                  = Column(String(30), unique=True)
    nombre                  = Column(String(300), nullable=False)
    descripcion             = Column(Text)
    causas                  = Column(Text)
    consecuencias           = Column(Text)
    tipo                    = Column(String(100))      # GRC/CATEGORIA_RIESGO
    proceso                 = Column(String(200))      # GLOBAL/PROCESO
    area                    = Column(String(200))      # GLOBAL/AREA
    responsable_id          = _usuario()
    probabilidad_inherente  = Column(Integer)
    impacto_inherente       = Column(Integer)
    nivel_inherente         = Column(Integer)
    # El residual se CALCULA con los controles vinculados y su efectividad.
    probabilidad_residual   = Column(Integer)
    impacto_residual        = Column(Integer)
    nivel_residual          = Column(Integer)
    prioridad               = Column(Enum(PrioridadRiesgoGRCEnum))
    estado                  = Column(Enum(EstadoRiesgoGRCEnum), default=EstadoRiesgoGRCEnum.IDENTIFICADO)
    tratamiento             = Column(Enum(TratamientoRiesgoGRCEnum))
    comite_id               = Column(Integer, ForeignKey('grc_comite.id'))
    tercero_id              = Column(Integer, ForeignKey('grc_tercero.id', ondelete='SET NULL'))
    fecha_revision          = Column(Date)
    comite                  = relationship('GRCComite', back_populates='riesgos')
    controles               = relationship('GRCRiesgoControl', back_populates='riesgo')
    tratamientos            = relationship('GRCTratamiento', back_populates='riesgo')


class GRCRiesgoControl(Base, TimestampMixin):
    __tablename__ = 'grc_riesgo_control'
    __table_args__ = (UniqueConstraint('riesgo_id', 'control_id', name='uq_grc_riesgo_control'),)
    id                      = Column(Integer, primary_key=True)
    riesgo_id               = Column(Integer, ForeignKey('grc_riesgo.id'), nullable=False)
    control_id              = Column(Integer, ForeignKey('grc_control.id'), nullable=False)
    efectividad_sobre_riesgo = Column(Integer)
    observaciones           = Column(Text)
    riesgo                  = relationship('GRCRiesgo', back_populates='controles')
    control                 = relationship('GRCControl')


class GRCTratamiento(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_tratamiento'
    id             = Column(Integer, primary_key=True)
    riesgo_id      = Column(Integer, ForeignKey('grc_riesgo.id'), nullable=False)
    tipo           = Column(Enum(TratamientoRiesgoGRCEnum))
    descripcion    = Column(Text)
    responsable_id = _usuario()
    fecha_objetivo = Column(Date)
    estado         = Column(String(50), default='pendiente')
    avance         = Column(Integer, default=0)
    evidencia_url  = Column(Text)
    riesgo         = relationship('GRCRiesgo', back_populates='tratamientos')


class GRCKri(Base, TimestampMixin, SoftDeleteMixin):
    """Indicador clave de riesgo: la señal temprana de que un riesgo se acerca."""
    __tablename__ = 'grc_kri'
    id              = Column(Integer, primary_key=True)
    riesgo_id       = Column(Integer, ForeignKey('grc_riesgo.id', ondelete='CASCADE'), nullable=False, index=True)
    nombre          = Column(String(300), nullable=False)
    unidad          = Column(String(50))
    # sube = más es peor (p. ej. accidentes); baja = menos es peor (p. ej. cobertura)
    direccion       = Column(String(10), nullable=False, default='sube')
    umbral_alerta   = Column(Numeric(18, 4), nullable=False)
    umbral_critico  = Column(Numeric(18, 4), nullable=False)
    periodicidad    = Column(String(50))     # GRC/PERIODICIDAD
    responsable_id  = _usuario()
    descripcion     = Column(Text)


class GRCKriMedicion(Base, TimestampMixin):
    __tablename__ = 'grc_kri_medicion'
    __table_args__ = (UniqueConstraint('kri_id', 'periodo', name='uq_grc_kri_medicion'),)
    id         = Column(Integer, primary_key=True)
    kri_id     = Column(Integer, ForeignKey('grc_kri.id', ondelete='CASCADE'), nullable=False, index=True)
    periodo    = Column(String(10), nullable=False)    # AAAA-MM
    valor      = Column(Numeric(18, 4), nullable=False)
    nota       = Column(Text)
    registrado_por_id = _usuario()


# ────────────────────────────────────────────
# Evidencias (archivos adjuntos a cualquier registro)
# ────────────────────────────────────────────

class GRCEvidencia(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_evidencia'
    id                = Column(Integer, primary_key=True)
    nombre            = Column(String(300), nullable=False)
    tipo              = Column(String(100))      # GRC/TIPO_EVIDENCIA
    descripcion       = Column(Text)
    url               = Column(Text)
    ruta_archivo      = Column(String(500))      # relativa a UPLOAD_DIR
    tamano_bytes      = Column(Integer)
    dms_documento_id  = Column(Integer)
    fecha_emision     = Column(Date)
    fecha_vencimiento = Column(Date)
    responsable_id    = _usuario()
    referencia_tipo   = Column(String(100), index=True)
    referencia_id     = Column(Integer, index=True)
    activa            = Column(Boolean, default=True)


# ────────────────────────────────────────────
# Auditoría
# ────────────────────────────────────────────

class GRCAuditoria(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_auditoria'
    id               = Column(Integer, primary_key=True)
    codigo           = Column(String(30), unique=True)
    nombre           = Column(String(300), nullable=False)
    tipo             = Column(String(100))          # GRC/TIPO_AUDITORIA
    estado           = Column(Enum(EstadoAuditoriaGRCEnum), default=EstadoAuditoriaGRCEnum.PLANIFICADA)
    auditor_lider_id = _usuario()
    equipo           = Column(JSON, default=list)   # ids de usuario
    proceso          = Column(String(200))          # GLOBAL/PROCESO auditado
    area             = Column(String(200))          # GLOBAL/AREA auditada
    marco            = Column(String(200))          # GRC/MARCO_NORMATIVO: criterio
    fecha_inicio     = Column(Date)
    fecha_fin        = Column(Date)
    fecha_reporte    = Column(Date)
    alcance          = Column(Text)
    criterios        = Column(Text)
    presupuesto      = Column(Numeric(15, 2))
    observaciones    = Column(Text)
    hallazgos        = relationship('GRCHallazgo', back_populates='auditoria')


class GRCHallazgo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_hallazgo'
    id            = Column(Integer, primary_key=True)
    codigo        = Column(String(30), unique=True)
    auditoria_id  = Column(Integer, ForeignKey('grc_auditoria.id'))
    incidente_id  = Column(Integer, ForeignKey('grc_incidente.id', ondelete='SET NULL'))
    riesgo_id     = Column(Integer, ForeignKey('grc_riesgo.id', ondelete='SET NULL'))
    control_id    = Column(Integer, ForeignKey('grc_control.id', ondelete='SET NULL'))
    titulo        = Column(String(300), nullable=False)
    descripcion   = Column(Text)
    tipo          = Column(String(100))       # GRC/TIPO_HALLAZGO
    severidad     = Column(Enum(SeveridadGRCEnum))
    proceso       = Column(String(200))
    area          = Column(String(200))
    responsable_id = _usuario()
    fecha_limite  = Column(Date)
    estado        = Column(Enum(EstadoHallazgoGRCEnum), default=EstadoHallazgoGRCEnum.ABIERTO)
    impacto       = Column(Text)
    recomendacion = Column(Text)
    causa_raiz    = Column(Text)
    auditoria     = relationship('GRCAuditoria', back_populates='hallazgos')
    planes        = relationship('GRCPlanAccion', back_populates='hallazgo')


class GRCPlanAccion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_plan_accion'
    id             = Column(Integer, primary_key=True)
    hallazgo_id    = Column(Integer, ForeignKey('grc_hallazgo.id'), nullable=False)
    accion         = Column(Text, nullable=False)
    responsable_id = _usuario()
    fecha_objetivo = Column(Date)
    estado         = Column(String(50), default='pendiente')
    avance         = Column(Integer, default=0)
    evidencia      = Column(Text)
    observaciones  = Column(Text)
    hallazgo       = relationship('GRCHallazgo', back_populates='planes')


# ────────────────────────────────────────────
# Incidentes
# ────────────────────────────────────────────

class GRCIncidente(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_incidente'
    id                  = Column(Integer, primary_key=True)
    codigo              = Column(String(30), unique=True)
    titulo              = Column(String(300), nullable=False)
    tipo                = Column(String(100))     # GRC/TIPO_INCIDENTE
    descripcion         = Column(Text)
    severidad           = Column(Enum(SeveridadGRCEnum))
    urgencia            = Column(Enum(SeveridadGRCEnum))
    impacto             = Column(Text)
    perdida_estimada    = Column(Numeric(15, 2))
    proceso             = Column(String(200))
    area                = Column(String(200))
    riesgo_id           = Column(Integer, ForeignKey('grc_riesgo.id', ondelete='SET NULL'))
    control_id          = Column(Integer, ForeignKey('grc_control.id', ondelete='SET NULL'))
    reportado_por_id    = _usuario()
    responsable_id      = _usuario()
    fecha_ocurrencia    = Column(DateTime)
    fecha_cierre        = Column(DateTime)
    estado              = Column(String(50), default='abierto')
    causa_raiz          = Column(Text)
    acciones_tomadas    = Column(Text)
    lecciones_aprendidas = Column(Text)


# ────────────────────────────────────────────
# Continuidad del negocio
# ────────────────────────────────────────────

class GRCContinuidad(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_continuidad'
    id                      = Column(Integer, primary_key=True)
    proceso                 = Column(String(300), nullable=False)   # GLOBAL/PROCESO
    criticidad              = Column(Enum(SeveridadGRCEnum))
    rto_horas               = Column(Integer)
    rpo_horas               = Column(Integer)
    mtpd_horas              = Column(Integer)     # tiempo máximo tolerable de interrupción
    impacto_financiero_hora = Column(Numeric(15, 2))
    impacto_operativo       = Column(Text)
    sistemas_criticos       = Column(JSON, default=list)   # valores de GRC/SISTEMA_CRITICO
    responsable_id          = _usuario()
    plan_contingencia       = Column(Text)
    estado_plan             = Column(String(50), default='activo')
    ultima_revision         = Column(Date)
    periodicidad_revision   = Column(String(50))   # GRC/PERIODICIDAD
    simulacros              = relationship('GRCSimulacro', back_populates='continuidad')


class GRCSimulacro(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_simulacro'
    id             = Column(Integer, primary_key=True)
    continuidad_id = Column(Integer, ForeignKey('grc_continuidad.id'))
    nombre         = Column(String(300))
    fecha          = Column(Date)
    tipo           = Column(String(100))     # GRC/TIPO_SIMULACRO
    resultado      = Column(String(100))     # GRC/RESULTADO_SIMULACRO
    coordinador_id = _usuario()
    participantes  = Column(JSON, default=list)   # ids de usuario
    rto_logrado_horas = Column(Integer)
    observaciones  = Column(Text)
    lecciones      = Column(Text)
    continuidad    = relationship('GRCContinuidad', back_populates='simulacros')


# ────────────────────────────────────────────
# Terceros
# ────────────────────────────────────────────

class GRCTercero(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_tercero'
    id             = Column(Integer, primary_key=True)
    nombre         = Column(String(300), nullable=False)
    nit            = Column(String(50))
    tipo           = Column(String(100))     # GRC/TIPO_TERCERO
    pais           = Column(String(100))     # GLOBAL/PAIS
    sector         = Column(String(200))     # CRM/SECTOR_ECONOMICO
    contacto       = Column(String(200))     # persona externa: texto legítimo
    contacto_email = Column(String(200))
    proveedor_id   = Column(Integer, ForeignKey('proveedores.id', ondelete='SET NULL'))
    cliente_id     = Column(Integer, ForeignKey('crm_cliente.id', ondelete='SET NULL'))
    responsable_id = _usuario()              # quién lo administra adentro
    criticidad     = Column(Enum(SeveridadGRCEnum))   # qué tan dependiente es la empresa de él
    nivel_riesgo   = Column(String(50))      # sale de la última evaluación
    estado         = Column(String(50), default='activo')
    evaluaciones   = relationship('GRCEvaluacionTercero', back_populates='tercero')


class GRCEvaluacionTercero(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'grc_evaluacion_tercero'
    id                  = Column(Integer, primary_key=True)
    tercero_id          = Column(Integer, ForeignKey('grc_tercero.id'), nullable=False)
    periodo             = Column(String(20))
    fecha               = Column(Date)
    cumplimiento_legal  = Column(Integer)
    riesgo_reputacional = Column(Integer)
    solidez_financiera  = Column(Integer)
    seguridad_info      = Column(Integer)
    puntaje_total       = Column(Numeric(5, 2))
    clasificacion       = Column(String(50))
    evaluador_id        = _usuario()
    observaciones       = Column(Text)
    tercero             = relationship('GRCTercero', back_populates='evaluaciones')


# ────────────────────────────────────────────
# Vínculos, historial y configuración
# ────────────────────────────────────────────

class GRCVinculo(Base, TimestampMixin):
    """Relaciones muchos-a-muchos entre registros GRC que no llevan atributos
    propios: obligación↔control, obligación↔política, política↔control,
    continuidad↔riesgo, continuidad↔tercero, sesión de comité↔riesgo.

    Los tipos se validan en el servidor contra la lista de pares permitidos;
    una tabla por par serían seis tablas casi vacías con la misma forma.
    """
    __tablename__ = 'grc_vinculo'
    __table_args__ = (
        UniqueConstraint('origen_tipo', 'origen_id', 'destino_tipo', 'destino_id', name='uq_grc_vinculo'),
        Index('ix_grc_vinculo_destino', 'destino_tipo', 'destino_id'),
    )
    id           = Column(Integer, primary_key=True)
    origen_tipo  = Column(String(30), nullable=False)
    origen_id    = Column(Integer, nullable=False)
    destino_tipo = Column(String(30), nullable=False)
    destino_id   = Column(Integer, nullable=False)
    nota         = Column(String(300))


class GRCHistorial(Base):
    """Qué cambió, cuándo y quién. La trazabilidad que un auditor externo pide."""
    __tablename__ = 'grc_historial'
    __table_args__ = (Index('ix_grc_historial_entidad', 'entidad', 'entidad_id'),)
    id         = Column(Integer, primary_key=True)
    entidad    = Column(String(30), nullable=False)
    entidad_id = Column(Integer, nullable=False)
    accion     = Column(String(30), nullable=False)    # crear | editar | estado | retirar | vincular…
    campo      = Column(String(60))
    anterior   = Column(Text)
    nuevo      = Column(Text)
    usuario_id = _usuario()
    fecha      = Column(DateTime(timezone=True), nullable=False)


class GRCEscala(Base, TimestampMixin):
    """Los cinco niveles de probabilidad y de impacto, con lo que significan
    en esta empresa. La matriz deja de ser un dibujo fijo."""
    __tablename__ = 'grc_escala'
    __table_args__ = (UniqueConstraint('eje', 'valor', name='uq_grc_escala'),)
    id          = Column(Integer, primary_key=True)
    eje         = Column(String(15), nullable=False)    # probabilidad | impacto
    valor       = Column(Integer, nullable=False)       # 1..5
    nombre      = Column(String(60), nullable=False)
    descripcion = Column(Text)


class GRCBandaRiesgo(Base, TimestampMixin):
    """Desde qué nivel (probabilidad × impacto) un riesgo es bajo, medio, alto
    o crítico, y qué respuesta exige."""
    __tablename__ = 'grc_banda_riesgo'
    id        = Column(Integer, primary_key=True)
    prioridad = Column(Enum(PrioridadRiesgoGRCEnum), nullable=False, unique=True)
    minimo    = Column(Integer, nullable=False)
    color     = Column(String(10))
    respuesta = Column(Text)


class GRCParametro(Base, TimestampMixin):
    """Umbrales de aviso y plazos. Solo existen los que algún cálculo lee."""
    __tablename__ = 'grc_parametro'
    id    = Column(Integer, primary_key=True)
    clave = Column(String(60), nullable=False, unique=True)
    valor = Column(String(100), nullable=False)
