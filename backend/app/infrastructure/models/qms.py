from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, BigInteger, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TipoProcesoQMSEnum(str, enum.Enum):
    ESTRATEGICO = "ESTRATEGICO"
    MISIONAL    = "MISIONAL"
    APOYO       = "APOYO"
    EVALUACION  = "EVALUACION"


class EstadoProcesoQMSEnum(str, enum.Enum):
    ACTIVO   = "ACTIVO"
    INACTIVO = "INACTIVO"
    REVISION = "REVISION"


class ClasificacionNCQMSEnum(str, enum.Enum):
    MENOR   = "MENOR"
    MAYOR   = "MAYOR"
    CRITICA = "CRITICA"


class EstadoNCQMSEnum(str, enum.Enum):
    ABIERTA        = "ABIERTA"
    EN_TRATAMIENTO = "EN_TRATAMIENTO"
    VERIFICACION   = "VERIFICACION"
    CERRADA        = "CERRADA"


class OrigenNCQMSEnum(str, enum.Enum):
    AUDITORIA  = "AUDITORIA"
    CLIENTE    = "CLIENTE"
    OPERACION  = "OPERACION"
    TRANSPORTE = "TRANSPORTE"
    WMS        = "WMS"
    HCM        = "HCM"
    PROVEEDOR  = "PROVEEDOR"
    INCIDENTE  = "INCIDENTE"


class TipoAuditoriaQMSEnum(str, enum.Enum):
    INTERNA       = "INTERNA"
    EXTERNA       = "EXTERNA"
    CLIENTE       = "CLIENTE"
    CERTIFICACION = "CERTIFICACION"
    PROVEEDOR     = "PROVEEDOR"


class EstadoAuditoriaQMSEnum(str, enum.Enum):
    PLANIFICADA  = "PLANIFICADA"
    EN_EJECUCION = "EN_EJECUCION"
    COMPLETADA   = "COMPLETADA"
    CANCELADA    = "CANCELADA"


class EstadoHallazgoQMSEnum(str, enum.Enum):
    ABIERTO        = "ABIERTO"
    EN_TRATAMIENTO = "EN_TRATAMIENTO"
    VERIFICACION   = "VERIFICACION"
    CERRADO        = "CERRADO"


class TipoCAPAQMSEnum(str, enum.Enum):
    CORRECTIVA = "CORRECTIVA"
    PREVENTIVA = "PREVENTIVA"
    MEJORA     = "MEJORA"


class EstadoCAPAQMSEnum(str, enum.Enum):
    ABIERTA      = "ABIERTA"
    EN_CURSO     = "EN_CURSO"
    VERIFICACION = "VERIFICACION"
    CERRADA      = "CERRADA"
    VENCIDA      = "VENCIDA"


class PrioridadRiesgoQMSEnum(str, enum.Enum):
    BAJA    = "BAJA"
    MEDIA   = "MEDIA"
    ALTA    = "ALTA"
    CRITICA = "CRITICA"


class EstadoMejoraQMSEnum(str, enum.Enum):
    IDEA       = "IDEA"
    EVALUACION = "EVALUACION"
    APROBADA   = "APROBADA"
    EN_CURSO   = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    RECHAZADA  = "RECHAZADA"


class TipoEncuestaQMSEnum(str, enum.Enum):
    CLIENTE   = "CLIENTE"
    EMPLEADO  = "EMPLEADO"
    PROVEEDOR = "PROVEEDOR"
    INTERNO   = "INTERNO"


class EstadoCambioQMSEnum(str, enum.Enum):
    SOLICITADO    = "SOLICITADO"
    EN_EVALUACION = "EN_EVALUACION"
    APROBADO      = "APROBADO"
    EN_CURSO      = "EN_CURSO"
    IMPLEMENTADO  = "IMPLEMENTADO"
    RECHAZADO     = "RECHAZADO"


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class QMSProceso(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_proceso"

    id             = Column(Integer, primary_key=True, index=True)
    codigo         = Column(String(50), nullable=True, unique=True)
    nombre         = Column(String(300), nullable=False)
    descripcion    = Column(Text, nullable=True)
    tipo           = Column(SAEnum(TipoProcesoQMSEnum), nullable=False)
    estado         = Column(SAEnum(EstadoProcesoQMSEnum), nullable=False, default=EstadoProcesoQMSEnum.ACTIVO)
    padre_id       = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    responsable_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    objetivo       = Column(Text, nullable=True)
    alcance        = Column(Text, nullable=True)
    norma_iso      = Column(String(200), nullable=True)
    orden          = Column(Integer, default=0)

    padre         = relationship("QMSProceso", remote_side="QMSProceso.id", foreign_keys=[padre_id])
    hijos         = relationship("QMSProceso", foreign_keys=[padre_id], back_populates="padre")
    responsable   = relationship("Usuario", foreign_keys=[responsable_id])
    procedimientos = relationship("QMSProcedimiento", back_populates="proceso")
    indicadores   = relationship("QMSIndicador", back_populates="proceso")
    no_conformidades = relationship("QMSNoConformidad", back_populates="proceso")
    hallazgos     = relationship("QMSHallazgo", back_populates="proceso")
    capas         = relationship("QMSCAPA", back_populates="proceso")
    riesgos       = relationship("QMSRiesgo", back_populates="proceso")
    quejas        = relationship("QMSQueja", back_populates="proceso")
    cambios       = relationship("QMSCambio", back_populates="proceso")
    mejoras       = relationship("QMSMejora", back_populates="proceso")
    encuestas     = relationship("QMSEncuesta", back_populates="proceso")
    competencias  = relationship("QMSCompetenciaProceso", back_populates="proceso")
    evaluaciones_proveedor = relationship("QMSEvaluacionProveedor", back_populates="proceso")


class QMSProcedimiento(Base, TimestampMixin):
    __tablename__ = "qms_procedimiento"

    id                  = Column(Integer, primary_key=True, index=True)
    codigo              = Column(String(50), nullable=True, unique=True)
    nombre              = Column(String(300), nullable=False)
    descripcion         = Column(Text, nullable=True)
    proceso_id          = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    tipo                = Column(String(50), nullable=True)  # procedimiento/instructivo/manual/politica/formato
    version             = Column(String(20), default="1.0")
    estado              = Column(String(50), default="vigente")
    dms_documento_id    = Column(Integer, nullable=True)
    responsable_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_vigencia      = Column(DateTime(timezone=True), nullable=True)
    activo              = Column(Boolean, default=True)

    proceso    = relationship("QMSProceso", back_populates="procedimientos")
    responsable = relationship("Usuario", foreign_keys=[responsable_id])


class QMSIndicador(Base, TimestampMixin):
    __tablename__ = "qms_indicador"

    id             = Column(Integer, primary_key=True, index=True)
    codigo         = Column(String(50), nullable=True, unique=True)
    nombre         = Column(String(300), nullable=False)
    descripcion    = Column(Text, nullable=True)
    proceso_id     = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    tipo           = Column(String(50), nullable=True)  # estrategico/tactico/operativo
    formula        = Column(Text, nullable=True)
    unidad         = Column(String(50), nullable=True)
    frecuencia     = Column(String(50), nullable=True)  # diario/semanal/mensual/trimestral/anual
    meta           = Column(Numeric(18, 4), nullable=True)
    meta_min       = Column(Numeric(18, 4), nullable=True)
    meta_max       = Column(Numeric(18, 4), nullable=True)
    responsable_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    activo         = Column(Boolean, default=True)
    modulo_origen  = Column(String(50), nullable=True)  # WMS/TMS/HCM para KPIs calculados

    proceso    = relationship("QMSProceso", back_populates="indicadores")
    responsable = relationship("Usuario", foreign_keys=[responsable_id])
    metas      = relationship("QMSMetaIndicador", back_populates="indicador")
    mediciones = relationship("QMSMedicionIndicador", back_populates="indicador")


class QMSMetaIndicador(Base, TimestampMixin):
    __tablename__ = "qms_meta_indicador"

    id           = Column(Integer, primary_key=True, index=True)
    indicador_id = Column(Integer, ForeignKey("qms_indicador.id"), nullable=False)
    periodo      = Column(String(20), nullable=False)  # YYYY-MM
    meta         = Column(Numeric(18, 4), nullable=False)
    meta_min     = Column(Numeric(18, 4), nullable=True)
    meta_max     = Column(Numeric(18, 4), nullable=True)
    activo       = Column(Boolean, default=True)

    indicador = relationship("QMSIndicador", back_populates="metas")


class QMSMedicionIndicador(Base, TimestampMixin):
    __tablename__ = "qms_medicion_indicador"

    id                  = Column(Integer, primary_key=True, index=True)
    indicador_id        = Column(Integer, ForeignKey("qms_indicador.id"), nullable=False)
    periodo             = Column(String(20), nullable=False)  # YYYY-MM o YYYY-WW
    valor               = Column(Numeric(18, 4), nullable=False)
    cumple_meta         = Column(Boolean, nullable=True)
    variacion_pct       = Column(Numeric(10, 2), nullable=True)
    observaciones       = Column(Text, nullable=True)
    registrado_por_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    indicador       = relationship("QMSIndicador", back_populates="mediciones")
    registrado_por  = relationship("Usuario", foreign_keys=[registrado_por_id])


class QMSAuditoria(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_auditoria"

    id                  = Column(Integer, primary_key=True, index=True)
    codigo              = Column(String(50), nullable=True, unique=True)
    nombre              = Column(String(500), nullable=False)
    tipo                = Column(SAEnum(TipoAuditoriaQMSEnum), nullable=False)
    estado              = Column(SAEnum(EstadoAuditoriaQMSEnum), nullable=False, default=EstadoAuditoriaQMSEnum.PLANIFICADA)
    norma               = Column(String(200), nullable=True)
    proceso_ids         = Column(Text, nullable=True)  # JSON array de process IDs
    auditor_lider_id    = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    empresa_auditora    = Column(String(200), nullable=True)
    fecha_inicio_plan   = Column(DateTime(timezone=True), nullable=True)
    fecha_fin_plan      = Column(DateTime(timezone=True), nullable=True)
    fecha_inicio_real   = Column(DateTime(timezone=True), nullable=True)
    fecha_fin_real      = Column(DateTime(timezone=True), nullable=True)
    objetivo            = Column(Text, nullable=True)
    alcance             = Column(Text, nullable=True)
    conclusion          = Column(Text, nullable=True)
    resultado           = Column(String(50), nullable=True)  # aprobado/condicionado/rechazado

    auditor_lider   = relationship("Usuario", foreign_keys=[auditor_lider_id])
    no_conformidades = relationship("QMSNoConformidad", back_populates="auditoria")
    hallazgos       = relationship("QMSHallazgo", back_populates="auditoria")
    auditoria_hallazgos = relationship("QMSAuditoriaHallazgo", back_populates="auditoria")


class QMSNoConformidad(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_no_conformidad"

    id                   = Column(Integer, primary_key=True, index=True)
    codigo               = Column(String(50), nullable=True, unique=True)
    titulo               = Column(String(500), nullable=False)
    descripcion          = Column(Text, nullable=False)
    clasificacion        = Column(SAEnum(ClasificacionNCQMSEnum), nullable=False)
    estado               = Column(SAEnum(EstadoNCQMSEnum), nullable=False, default=EstadoNCQMSEnum.ABIERTA)
    origen               = Column(SAEnum(OrigenNCQMSEnum), nullable=False)
    proceso_id           = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    area                 = Column(String(200), nullable=True)
    responsable_id       = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    detectado_por_id     = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_deteccion      = Column(DateTime(timezone=True), nullable=True)
    fecha_limite         = Column(DateTime(timezone=True), nullable=True)
    fecha_cierre         = Column(DateTime(timezone=True), nullable=True)
    causa_raiz           = Column(Text, nullable=True)
    herramienta_analisis = Column(String(100), nullable=True)
    impacto              = Column(Text, nullable=True)
    norma_afectada       = Column(String(200), nullable=True)
    auditoria_id         = Column(Integer, ForeignKey("qms_auditoria.id"), nullable=True)
    requiere_capa        = Column(Boolean, default=True)

    proceso       = relationship("QMSProceso", back_populates="no_conformidades")
    responsable   = relationship("Usuario", foreign_keys=[responsable_id])
    detectado_por = relationship("Usuario", foreign_keys=[detectado_por_id])
    auditoria     = relationship("QMSAuditoria", back_populates="no_conformidades")
    hallazgos     = relationship("QMSHallazgo", back_populates="nc")
    capas         = relationship("QMSCAPA", back_populates="nc")
    quejas        = relationship("QMSQueja", back_populates="nc")


class QMSHallazgo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_hallazgo"

    id             = Column(Integer, primary_key=True, index=True)
    codigo         = Column(String(50), nullable=True, unique=True)
    descripcion    = Column(Text, nullable=False)
    tipo           = Column(String(50), nullable=True)  # no_conformidad/observacion/oportunidad_mejora
    estado         = Column(SAEnum(EstadoHallazgoQMSEnum), nullable=False, default=EstadoHallazgoQMSEnum.ABIERTO)
    proceso_id     = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    responsable_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    auditoria_id   = Column(Integer, ForeignKey("qms_auditoria.id"), nullable=True)
    nc_id          = Column(Integer, ForeignKey("qms_no_conformidad.id"), nullable=True)
    impacto        = Column(String(50), nullable=True)  # alto/medio/bajo
    fecha_limite   = Column(DateTime(timezone=True), nullable=True)
    fecha_cierre   = Column(DateTime(timezone=True), nullable=True)
    evidencia      = Column(Text, nullable=True)

    proceso     = relationship("QMSProceso", back_populates="hallazgos")
    responsable = relationship("Usuario", foreign_keys=[responsable_id])
    auditoria   = relationship("QMSAuditoria", back_populates="hallazgos")
    nc          = relationship("QMSNoConformidad", back_populates="hallazgos")
    capas       = relationship("QMSCAPA", back_populates="hallazgo")
    auditoria_hallazgos = relationship("QMSAuditoriaHallazgo", back_populates="hallazgo")


class QMSAuditoriaHallazgo(Base, TimestampMixin):
    __tablename__ = "qms_auditoria_hallazgo"

    id           = Column(Integer, primary_key=True, index=True)
    auditoria_id = Column(Integer, ForeignKey("qms_auditoria.id"), nullable=False)
    hallazgo_id  = Column(Integer, ForeignKey("qms_hallazgo.id"), nullable=False)

    auditoria = relationship("QMSAuditoria", back_populates="auditoria_hallazgos")
    hallazgo  = relationship("QMSHallazgo", back_populates="auditoria_hallazgos")


class QMSCAPA(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_capa"

    id                  = Column(Integer, primary_key=True, index=True)
    codigo              = Column(String(50), nullable=True, unique=True)
    tipo                = Column(SAEnum(TipoCAPAQMSEnum), nullable=False)
    estado              = Column(SAEnum(EstadoCAPAQMSEnum), nullable=False, default=EstadoCAPAQMSEnum.ABIERTA)
    titulo              = Column(String(500), nullable=False)
    descripcion         = Column(Text, nullable=False)
    nc_id               = Column(Integer, ForeignKey("qms_no_conformidad.id"), nullable=True)
    hallazgo_id         = Column(Integer, ForeignKey("qms_hallazgo.id"), nullable=True)
    proceso_id          = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    responsable_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    verificado_por_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_limite        = Column(DateTime(timezone=True), nullable=True)
    fecha_cierre        = Column(DateTime(timezone=True), nullable=True)
    causa_raiz          = Column(Text, nullable=True)
    efectividad         = Column(Text, nullable=True)
    porcentaje_avance   = Column(Integer, default=0)

    nc             = relationship("QMSNoConformidad", back_populates="capas")
    hallazgo       = relationship("QMSHallazgo", back_populates="capas")
    proceso        = relationship("QMSProceso", back_populates="capas")
    responsable    = relationship("Usuario", foreign_keys=[responsable_id])
    verificado_por = relationship("Usuario", foreign_keys=[verificado_por_id])
    tareas         = relationship("QMSCAPATarea", back_populates="capa")


class QMSCAPATarea(Base, TimestampMixin):
    __tablename__ = "qms_capa_tarea"

    id               = Column(Integer, primary_key=True, index=True)
    capa_id          = Column(Integer, ForeignKey("qms_capa.id"), nullable=False)
    descripcion      = Column(Text, nullable=False)
    responsable_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_limite     = Column(DateTime(timezone=True), nullable=True)
    completada       = Column(Boolean, default=False)
    fecha_completado = Column(DateTime(timezone=True), nullable=True)
    orden            = Column(Integer, default=0)

    capa        = relationship("QMSCAPA", back_populates="tareas")
    responsable = relationship("Usuario", foreign_keys=[responsable_id])


class QMSRiesgo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_riesgo"

    id               = Column(Integer, primary_key=True, index=True)
    codigo           = Column(String(50), nullable=True, unique=True)
    nombre           = Column(String(300), nullable=False)
    descripcion      = Column(Text, nullable=True)
    proceso_id       = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    probabilidad     = Column(Integer, nullable=False)  # 1-5
    impacto          = Column(Integer, nullable=False)  # 1-5
    nivel_riesgo     = Column(Integer, nullable=False)  # probabilidad * impacto, stored
    prioridad        = Column(SAEnum(PrioridadRiesgoQMSEnum), nullable=False)
    estado           = Column(String(50), default="activo")
    controles        = Column(Text, nullable=True)
    plan_mitigacion  = Column(Text, nullable=True)
    responsable_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    norma_iso        = Column(String(100), nullable=True)
    fecha_revision   = Column(DateTime(timezone=True), nullable=True)

    proceso     = relationship("QMSProceso", back_populates="riesgos")
    responsable = relationship("Usuario", foreign_keys=[responsable_id])


class QMSQueja(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_queja"

    id                    = Column(Integer, primary_key=True, index=True)
    codigo                = Column(String(50), nullable=True, unique=True)
    tipo                  = Column(String(50), nullable=True)  # queja/reclamo/sugerencia/felicitacion
    estado                = Column(String(50), default="abierta")
    descripcion           = Column(Text, nullable=False)
    origen                = Column(String(50), nullable=True)  # cliente/operacion/proveedor/interno
    cliente_nombre        = Column(String(300), nullable=True)
    cliente_nit           = Column(String(30), nullable=True)
    proceso_id            = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    responsable_id        = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_limite          = Column(DateTime(timezone=True), nullable=True)
    fecha_cierre          = Column(DateTime(timezone=True), nullable=True)
    respuesta             = Column(Text, nullable=True)
    satisfaccion_resultado = Column(Integer, nullable=True)  # 1-5
    nc_id                 = Column(Integer, ForeignKey("qms_no_conformidad.id"), nullable=True)
    tms_viaje_id          = Column(Integer, nullable=True)

    proceso     = relationship("QMSProceso", back_populates="quejas")
    responsable = relationship("Usuario", foreign_keys=[responsable_id])
    nc          = relationship("QMSNoConformidad", back_populates="quejas")


class QMSEvaluacionProveedor(Base, TimestampMixin):
    __tablename__ = "qms_evaluacion_proveedor"

    id               = Column(Integer, primary_key=True, index=True)
    proveedor_nombre = Column(String(300), nullable=False)
    proveedor_nit    = Column(String(30), nullable=True)
    periodo          = Column(String(20), nullable=False)  # YYYY-MM
    calidad          = Column(Numeric(5, 2), nullable=True)
    cumplimiento     = Column(Numeric(5, 2), nullable=True)
    servicio         = Column(Numeric(5, 2), nullable=True)
    tiempos          = Column(Numeric(5, 2), nullable=True)
    puntaje_total    = Column(Numeric(5, 2), nullable=True)
    clasificacion    = Column(String(50), nullable=True)  # excelente/bueno/regular/deficiente
    observaciones    = Column(Text, nullable=True)
    evaluado_por_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    proceso_id       = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)

    evaluado_por = relationship("Usuario", foreign_keys=[evaluado_por_id])
    proceso      = relationship("QMSProceso", back_populates="evaluaciones_proveedor")


class QMSCambio(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_cambio"

    id                   = Column(Integer, primary_key=True, index=True)
    codigo               = Column(String(50), nullable=True, unique=True)
    titulo               = Column(String(500), nullable=False)
    descripcion          = Column(Text, nullable=False)
    tipo                 = Column(String(50), nullable=True)  # proceso/operativo/tecnologico/normativo
    estado               = Column(SAEnum(EstadoCambioQMSEnum), nullable=False, default=EstadoCambioQMSEnum.SOLICITADO)
    proceso_id           = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    responsable_id       = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    aprobado_por_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    impacto              = Column(Text, nullable=True)
    evaluacion           = Column(Text, nullable=True)
    fecha_solicitado     = Column(DateTime(timezone=True), nullable=True)
    fecha_limite         = Column(DateTime(timezone=True), nullable=True)
    fecha_implementacion = Column(DateTime(timezone=True), nullable=True)
    norma_afectada       = Column(String(200), nullable=True)

    proceso      = relationship("QMSProceso", back_populates="cambios")
    responsable  = relationship("Usuario", foreign_keys=[responsable_id])
    aprobado_por = relationship("Usuario", foreign_keys=[aprobado_por_id])


class QMSMejora(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "qms_mejora"

    id                      = Column(Integer, primary_key=True, index=True)
    codigo                  = Column(String(50), nullable=True, unique=True)
    titulo                  = Column(String(500), nullable=False)
    descripcion             = Column(Text, nullable=False)
    estado                  = Column(SAEnum(EstadoMejoraQMSEnum), nullable=False, default=EstadoMejoraQMSEnum.IDEA)
    proceso_id              = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)
    responsable_id          = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_limite            = Column(DateTime(timezone=True), nullable=True)
    fecha_completado        = Column(DateTime(timezone=True), nullable=True)
    beneficio_esperado      = Column(Text, nullable=True)
    ahorro_estimado         = Column(Numeric(18, 2), nullable=True)
    ahorro_real             = Column(Numeric(18, 2), nullable=True)
    impacto                 = Column(String(50), nullable=True)
    retorno_estimado_meses  = Column(Integer, nullable=True)

    proceso     = relationship("QMSProceso", back_populates="mejoras")
    responsable = relationship("Usuario", foreign_keys=[responsable_id])


class QMSEncuesta(Base, TimestampMixin):
    __tablename__ = "qms_encuesta"

    id               = Column(Integer, primary_key=True, index=True)
    nombre           = Column(String(300), nullable=False)
    tipo             = Column(SAEnum(TipoEncuestaQMSEnum), nullable=False)
    descripcion      = Column(Text, nullable=True)
    activa           = Column(Boolean, default=True)
    fecha_inicio     = Column(DateTime(timezone=True), nullable=True)
    fecha_fin        = Column(DateTime(timezone=True), nullable=True)
    preguntas        = Column(Text, nullable=True)  # JSON structure
    total_respuestas = Column(Integer, default=0)
    nps_score        = Column(Numeric(5, 2), nullable=True)
    csat_score       = Column(Numeric(5, 2), nullable=True)
    proceso_id       = Column(Integer, ForeignKey("qms_proceso.id"), nullable=True)

    proceso    = relationship("QMSProceso", back_populates="encuestas")
    respuestas = relationship("QMSEncuestaRespuesta", back_populates="encuesta")


class QMSEncuestaRespuesta(Base, TimestampMixin):
    __tablename__ = "qms_encuesta_respuesta"

    id                  = Column(Integer, primary_key=True, index=True)
    encuesta_id         = Column(Integer, ForeignKey("qms_encuesta.id"), nullable=False)
    respondente_nombre  = Column(String(200), nullable=True)
    respondente_tipo    = Column(String(50), nullable=True)
    respuestas          = Column(Text, nullable=True)  # JSON
    nps_valor           = Column(Integer, nullable=True)   # 0-10
    csat_valor          = Column(Integer, nullable=True)   # 1-5
    comentario          = Column(Text, nullable=True)

    encuesta = relationship("QMSEncuesta", back_populates="respuestas")


class QMSCompetenciaProceso(Base, TimestampMixin):
    __tablename__ = "qms_competencia_proceso"

    id               = Column(Integer, primary_key=True, index=True)
    proceso_id       = Column(Integer, ForeignKey("qms_proceso.id"), nullable=False)
    cargo            = Column(String(200), nullable=False)
    competencia      = Column(String(300), nullable=False)
    nivel_requerido  = Column(String(50), nullable=False)
    norma_iso        = Column(String(100), nullable=True)
    activo           = Column(Boolean, default=True)

    proceso = relationship("QMSProceso", back_populates="competencias")


class QMSKPIDiario(Base, TimestampMixin):
    __tablename__ = "qms_kpi_diario"

    id                     = Column(Integer, primary_key=True, index=True)
    fecha                  = Column(DateTime(timezone=True), nullable=False)
    nc_abiertas            = Column(Integer, default=0)
    nc_cerradas_hoy        = Column(Integer, default=0)
    hallazgos_abiertos     = Column(Integer, default=0)
    capas_vencidas         = Column(Integer, default=0)
    auditorias_pendientes  = Column(Integer, default=0)
    indice_calidad         = Column(Numeric(5, 2), default=0)
    otif_rate              = Column(Numeric(5, 2), default=0)
    nps_promedio           = Column(Numeric(5, 2), default=0)
    mejoras_activas        = Column(Integer, default=0)
    riesgos_criticos       = Column(Integer, default=0)
    quejas_abiertas        = Column(Integer, default=0)


class QMSCertificacion(Base, TimestampMixin):
    """Las normas en que la empresa está certificada o trabajando para estarlo.

    La pantalla de configuración traía seis certificaciones escritas a mano,
    con certificadora y fechas: le decía a cualquier empresa que estaba
    certificada en ISO 9001 por un organismo que nunca la auditó. Es el dato
    que más cuidado pide del módulo, porque se muestra a clientes.

    El estado —vigente, por vencer, vencida— NO se guarda: sale de
    `fecha_vencimiento` contra el día de hoy. Guardado, mentiría al día
    siguiente de vencer. Lo único que decide una persona es si la norma está
    todavía en implementación.
    """
    __tablename__ = "qms_certificacion"

    id                 = Column(Integer, primary_key=True, index=True)
    norma              = Column(String(60), nullable=False)
    titulo             = Column(String(200), nullable=True)
    certificadora      = Column(String(200), nullable=True)
    numero_certificado = Column(String(100), nullable=True)
    fecha_otorgamiento = Column(DateTime(timezone=True), nullable=True)
    fecha_vencimiento  = Column(DateTime(timezone=True), nullable=True)
    alcance            = Column(Text, nullable=True)
    en_implementacion  = Column(Boolean, nullable=False, default=False)
    activo             = Column(Boolean, nullable=False, default=True)


class QMSParametro(Base, TimestampMixin):
    """Los umbrales con que el módulo decide qué alertar.

    Clave y valor: los lee el tablero de calidad para armar sus alertas y la
    evaluación de proveedores para marcar a los que quedan por debajo. Un
    umbral que se configura y nadie lee es solo decoración, así que aquí solo
    entran los que algo usa.
    """
    __tablename__ = "qms_parametro"

    id          = Column(Integer, primary_key=True, index=True)
    clave       = Column(String(60), nullable=False, unique=True)
    valor       = Column(Numeric(12, 2), nullable=False)
