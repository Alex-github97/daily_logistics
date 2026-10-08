from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    ForeignKey, Enum as SQLEnum, Numeric,
)
from sqlalchemy.orm import relationship
from enum import Enum
from app.infrastructure.models.base import Base, TimestampMixin


class ModalidadCursoEnum(str, Enum):
    VIRTUAL      = "VIRTUAL"
    PRESENCIAL   = "PRESENCIAL"
    HIBRIDO      = "HIBRIDO"
    MICROLEARNING = "MICROLEARNING"
    WEBINAR      = "WEBINAR"
    SIMULACION   = "SIMULACION"


class NivelCursoEnum(str, Enum):
    BASICO      = "BASICO"
    INTERMEDIO  = "INTERMEDIO"
    AVANZADO    = "AVANZADO"
    EXPERTO     = "EXPERTO"


class EstadoCursoEnum(str, Enum):
    BORRADOR   = "BORRADOR"
    PUBLICADO  = "PUBLICADO"
    ARCHIVADO  = "ARCHIVADO"
    REVISION   = "REVISION"


class TipoProgramaEnum(str, Enum):
    DIPLOMADO        = "DIPLOMADO"
    CERTIFICACION    = "CERTIFICACION"
    RUTA_APRENDIZAJE = "RUTA_APRENDIZAJE"
    CARRERA_INTERNA  = "CARRERA_INTERNA"
    INDUCCION        = "INDUCCION"


class EstadoInscripcionEnum(str, Enum):
    INSCRITO    = "INSCRITO"
    EN_PROGRESO = "EN_PROGRESO"
    COMPLETADO  = "COMPLETADO"
    ABANDONADO  = "ABANDONADO"
    PENDIENTE   = "PENDIENTE"


class TipoEvaluacionEnum(str, Enum):
    DIAGNOSTICO     = "DIAGNOSTICO"
    FORMATIVO       = "FORMATIVO"
    CERTIFICACION   = "CERTIFICACION"
    RECERTIFICACION = "RECERTIFICACION"
    PRACTICO        = "PRACTICO"


class TipoPreguntaEnum(str, Enum):
    MULTIPLE         = "MULTIPLE"
    VERDADERO_FALSO  = "VERDADERO_FALSO"
    CASO_PRACTICO    = "CASO_PRACTICO"
    RESPUESTA_ABIERTA = "RESPUESTA_ABIERTA"


class NivelCompetenciaEnum(str, Enum):
    INICIAL    = "INICIAL"
    BASICO     = "BASICO"
    INTERMEDIO = "INTERMEDIO"
    AVANZADO   = "AVANZADO"
    EXPERTO    = "EXPERTO"


class EstadoCertificacionEnum(str, Enum):
    VIGENTE    = "VIGENTE"
    VENCIDA    = "VENCIDA"
    POR_VENCER = "POR_VENCER"
    CANCELADA  = "CANCELADA"


class TipoContenidoEnum(str, Enum):
    VIDEO         = "VIDEO"
    DOCUMENTO     = "DOCUMENTO"
    PRESENTACION  = "PRESENTACION"
    QUIZ          = "QUIZ"
    SIMULACION    = "SIMULACION"
    ENLACE        = "ENLACE"
    SCORM         = "SCORM"


class TipoInstructorEnum(str, Enum):
    INTERNO  = "INTERNO"
    EXTERNO  = "EXTERNO"
    EXPERTO  = "EXPERTO"


# ─── Entities (FK-safe order) ───────────────────────────────────────────────

class LMSFacultad(Base, TimestampMixin):
    __tablename__ = "lms_facultad"
    id          = Column(Integer, primary_key=True)
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text)
    color       = Column(String(20), default="#D97706")
    icono       = Column(String(50), default="School")
    activo      = Column(Boolean, default=True)

    escuelas = relationship("LMSEscuela", back_populates="facultad", cascade="all, delete-orphan")


class LMSEscuela(Base, TimestampMixin):
    __tablename__ = "lms_escuela"
    id           = Column(Integer, primary_key=True)
    facultad_id  = Column(Integer, ForeignKey("lms_facultad.id"), nullable=False)
    nombre       = Column(String(200), nullable=False)
    descripcion  = Column(Text)
    activo       = Column(Boolean, default=True)

    facultad  = relationship("LMSFacultad", back_populates="escuelas")
    programas = relationship("LMSPrograma", back_populates="escuela")


class LMSInstructor(Base, TimestampMixin):
    __tablename__ = "lms_instructor"
    id           = Column(Integer, primary_key=True)
    nombre       = Column(String(200), nullable=False)
    email        = Column(String(200))
    especialidad = Column(String(200))
    tipo         = Column(SQLEnum(TipoInstructorEnum), default=TipoInstructorEnum.INTERNO)
    activo       = Column(Boolean, default=True)

    cursos = relationship("LMSCurso", back_populates="instructor")


class LMSCompetencia(Base, TimestampMixin):
    __tablename__ = "lms_competencia"
    id          = Column(Integer, primary_key=True)
    codigo      = Column(String(20), unique=True)
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text)
    categoria   = Column(String(100))
    activo      = Column(Boolean, default=True)

    cursos_asociados = relationship("LMSCursoCompetencia", back_populates="competencia")
    matriz_cargos    = relationship("LMSMatrizCompetencia", back_populates="competencia")


class LMSPrograma(Base, TimestampMixin):
    __tablename__ = "lms_programa"
    id              = Column(Integer, primary_key=True)
    escuela_id      = Column(Integer, ForeignKey("lms_escuela.id"), nullable=False)
    codigo          = Column(String(20), unique=True)
    nombre          = Column(String(200), nullable=False)
    descripcion     = Column(Text)
    tipo            = Column(SQLEnum(TipoProgramaEnum), nullable=False)
    duracion_horas  = Column(Integer, default=0)
    activo          = Column(Boolean, default=True)

    escuela = relationship("LMSEscuela", back_populates="programas")
    cursos  = relationship("LMSProgramaCurso", back_populates="programa")


class LMSCurso(Base, TimestampMixin):
    __tablename__ = "lms_curso"
    id                  = Column(Integer, primary_key=True)
    codigo              = Column(String(20), unique=True)
    nombre              = Column(String(200), nullable=False)
    descripcion         = Column(Text)
    instructor_id       = Column(Integer, ForeignKey("lms_instructor.id"))
    modalidad           = Column(SQLEnum(ModalidadCursoEnum), nullable=False)
    nivel               = Column(SQLEnum(NivelCursoEnum), nullable=False)
    estado              = Column(SQLEnum(EstadoCursoEnum), default=EstadoCursoEnum.BORRADOR)
    duracion_horas      = Column(Numeric(6, 2), default=0)
    categoria           = Column(String(100))
    es_obligatorio      = Column(Boolean, default=False)
    puntaje_aprobacion  = Column(Integer, default=70)

    instructor   = relationship("LMSInstructor", back_populates="cursos")
    modulos      = relationship("LMSModulo", back_populates="curso", cascade="all, delete-orphan")
    competencias = relationship("LMSCursoCompetencia", back_populates="curso")
    inscripciones = relationship("LMSInscripcion", back_populates="curso")
    evaluaciones = relationship("LMSEvaluacion", back_populates="curso")


class LMSModulo(Base, TimestampMixin):
    __tablename__ = "lms_modulo"
    id             = Column(Integer, primary_key=True)
    curso_id       = Column(Integer, ForeignKey("lms_curso.id"), nullable=False)
    nombre         = Column(String(200), nullable=False)
    orden          = Column(Integer, default=0)
    duracion_horas = Column(Numeric(5, 2), default=0)

    curso      = relationship("LMSCurso", back_populates="modulos")
    contenidos = relationship("LMSContenido", back_populates="modulo", cascade="all, delete-orphan")


class LMSContenido(Base, TimestampMixin):
    __tablename__ = "lms_contenido"
    id                = Column(Integer, primary_key=True)
    modulo_id         = Column(Integer, ForeignKey("lms_modulo.id"), nullable=False)
    tipo              = Column(SQLEnum(TipoContenidoEnum), nullable=False)
    titulo            = Column(String(200), nullable=False)
    descripcion       = Column(Text)
    url               = Column(Text)
    duracion_minutos  = Column(Integer, default=0)
    orden             = Column(Integer, default=0)

    modulo    = relationship("LMSModulo", back_populates="contenidos")
    progresos = relationship("LMSProgreso", back_populates="contenido")


class LMSCursoCompetencia(Base, TimestampMixin):
    __tablename__ = "lms_curso_competencia"
    id              = Column(Integer, primary_key=True)
    curso_id        = Column(Integer, ForeignKey("lms_curso.id"), nullable=False)
    competencia_id  = Column(Integer, ForeignKey("lms_competencia.id"), nullable=False)
    nivel_desarrolla = Column(SQLEnum(NivelCompetenciaEnum))

    curso       = relationship("LMSCurso", back_populates="competencias")
    competencia = relationship("LMSCompetencia", back_populates="cursos_asociados")


class LMSMatrizCompetencia(Base, TimestampMixin):
    __tablename__ = "lms_matriz_competencia"
    id              = Column(Integer, primary_key=True)
    cargo           = Column(String(200), nullable=False)
    area            = Column(String(200))
    competencia_id  = Column(Integer, ForeignKey("lms_competencia.id"), nullable=False)
    nivel_requerido = Column(SQLEnum(NivelCompetenciaEnum), nullable=False)
    nivel_actual    = Column(SQLEnum(NivelCompetenciaEnum))
    brecha          = Column(Integer, default=0)

    competencia = relationship("LMSCompetencia", back_populates="matriz_cargos")


class LMSRutaAprendizaje(Base, TimestampMixin):
    __tablename__ = "lms_ruta_aprendizaje"
    id                   = Column(Integer, primary_key=True)
    codigo               = Column(String(20), unique=True)
    nombre               = Column(String(200), nullable=False)
    descripcion          = Column(Text)
    cargo_objetivo       = Column(String(200))
    area_objetivo        = Column(String(200))
    duracion_total_horas = Column(Numeric(7, 2), default=0)
    activo               = Column(Boolean, default=True)

    cursos       = relationship("LMSRutaCurso", back_populates="ruta", cascade="all, delete-orphan")
    inscripciones = relationship("LMSInscripcion", back_populates="ruta")


class LMSRutaCurso(Base, TimestampMixin):
    __tablename__ = "lms_ruta_curso"
    id         = Column(Integer, primary_key=True)
    ruta_id    = Column(Integer, ForeignKey("lms_ruta_aprendizaje.id"), nullable=False)
    curso_id   = Column(Integer, ForeignKey("lms_curso.id"), nullable=False)
    orden      = Column(Integer, default=0)
    obligatorio = Column(Boolean, default=True)

    ruta = relationship("LMSRutaAprendizaje", back_populates="cursos")


class LMSProgramaCurso(Base, TimestampMixin):
    __tablename__ = "lms_programa_curso"
    id          = Column(Integer, primary_key=True)
    programa_id = Column(Integer, ForeignKey("lms_programa.id"), nullable=False)
    curso_id    = Column(Integer, ForeignKey("lms_curso.id"), nullable=False)
    orden       = Column(Integer, default=0)
    obligatorio = Column(Boolean, default=True)

    programa = relationship("LMSPrograma", back_populates="cursos")


class LMSInscripcion(Base, TimestampMixin):
    __tablename__ = "lms_inscripcion"
    id           = Column(Integer, primary_key=True)
    usuario_id   = Column(Integer, nullable=False)
    curso_id     = Column(Integer, ForeignKey("lms_curso.id"))
    ruta_id      = Column(Integer, ForeignKey("lms_ruta_aprendizaje.id"))
    estado       = Column(SQLEnum(EstadoInscripcionEnum), default=EstadoInscripcionEnum.INSCRITO)
    fecha_inicio = Column(DateTime)
    fecha_fin    = Column(DateTime)
    progreso_pct = Column(Numeric(5, 2), default=0)
    nota_final   = Column(Numeric(5, 2))

    curso     = relationship("LMSCurso", back_populates="inscripciones")
    ruta      = relationship("LMSRutaAprendizaje", back_populates="inscripciones")
    progresos = relationship("LMSProgreso", back_populates="inscripcion")


class LMSProgreso(Base, TimestampMixin):
    __tablename__ = "lms_progreso"
    id               = Column(Integer, primary_key=True)
    inscripcion_id   = Column(Integer, ForeignKey("lms_inscripcion.id"), nullable=False)
    contenido_id     = Column(Integer, ForeignKey("lms_contenido.id"), nullable=False)
    completado       = Column(Boolean, default=False)
    fecha_completado = Column(DateTime)
    tiempo_minutos   = Column(Integer, default=0)

    inscripcion = relationship("LMSInscripcion", back_populates="progresos")
    contenido   = relationship("LMSContenido", back_populates="progresos")


class LMSEvaluacion(Base, TimestampMixin):
    __tablename__ = "lms_evaluacion"
    id                    = Column(Integer, primary_key=True)
    codigo                = Column(String(20), unique=True)
    curso_id              = Column(Integer, ForeignKey("lms_curso.id"))
    nombre                = Column(String(200), nullable=False)
    tipo                  = Column(SQLEnum(TipoEvaluacionEnum), nullable=False)
    descripcion           = Column(Text)
    tiempo_limite_min     = Column(Integer)
    intentos_maximos      = Column(Integer, default=3)
    puntaje_aprobacion    = Column(Integer, default=70)
    aleatorizar_preguntas = Column(Boolean, default=True)
    activo                = Column(Boolean, default=True)

    curso     = relationship("LMSCurso", back_populates="evaluaciones")
    preguntas = relationship("LMSEvaluacionPregunta", back_populates="evaluacion", cascade="all, delete-orphan")
    intentos  = relationship("LMSIntentoEvaluacion", back_populates="evaluacion")


class LMSPregunta(Base, TimestampMixin):
    __tablename__ = "lms_pregunta"
    id                = Column(Integer, primary_key=True)
    codigo            = Column(String(20), unique=True)
    tipo              = Column(SQLEnum(TipoPreguntaEnum), nullable=False)
    enunciado         = Column(Text, nullable=False)
    nivel_dificultad  = Column(String(20), default="MEDIO")
    categoria         = Column(String(100))
    puntaje           = Column(Integer, default=1)
    activo            = Column(Boolean, default=True)

    opciones     = relationship("LMSOpcionRespuesta", back_populates="pregunta", cascade="all, delete-orphan")
    evaluaciones = relationship("LMSEvaluacionPregunta", back_populates="pregunta")


class LMSOpcionRespuesta(Base, TimestampMixin):
    __tablename__ = "lms_opcion_respuesta"
    id          = Column(Integer, primary_key=True)
    pregunta_id = Column(Integer, ForeignKey("lms_pregunta.id"), nullable=False)
    texto       = Column(Text, nullable=False)
    es_correcta = Column(Boolean, default=False)
    orden       = Column(Integer, default=0)

    pregunta = relationship("LMSPregunta", back_populates="opciones")


class LMSEvaluacionPregunta(Base, TimestampMixin):
    __tablename__ = "lms_evaluacion_pregunta"
    id            = Column(Integer, primary_key=True)
    evaluacion_id = Column(Integer, ForeignKey("lms_evaluacion.id"), nullable=False)
    pregunta_id   = Column(Integer, ForeignKey("lms_pregunta.id"), nullable=False)
    orden         = Column(Integer, default=0)

    evaluacion = relationship("LMSEvaluacion", back_populates="preguntas")
    pregunta   = relationship("LMSPregunta", back_populates="evaluaciones")


class LMSIntentoEvaluacion(Base, TimestampMixin):
    __tablename__ = "lms_intento_evaluacion"
    id                 = Column(Integer, primary_key=True)
    evaluacion_id      = Column(Integer, ForeignKey("lms_evaluacion.id"), nullable=False)
    usuario_id         = Column(Integer, nullable=False)
    numero_intento     = Column(Integer, default=1)
    puntaje_obtenido   = Column(Numeric(5, 2))
    aprobado           = Column(Boolean, default=False)
    fecha_inicio       = Column(DateTime)
    fecha_fin          = Column(DateTime)
    tiempo_utilizado_min = Column(Integer)

    evaluacion = relationship("LMSEvaluacion", back_populates="intentos")
    respuestas = relationship("LMSRespuesta", back_populates="intento")


class LMSRespuesta(Base, TimestampMixin):
    __tablename__ = "lms_respuesta"
    id               = Column(Integer, primary_key=True)
    intento_id       = Column(Integer, ForeignKey("lms_intento_evaluacion.id"), nullable=False)
    pregunta_id      = Column(Integer, ForeignKey("lms_pregunta.id"), nullable=False)
    opcion_id        = Column(Integer, ForeignKey("lms_opcion_respuesta.id"))
    texto_respuesta  = Column(Text)
    es_correcta      = Column(Boolean)
    puntaje_obtenido = Column(Integer, default=0)

    intento = relationship("LMSIntentoEvaluacion", back_populates="respuestas")


class LMSCertificacion(Base, TimestampMixin):
    __tablename__ = "lms_certificacion"
    id              = Column(Integer, primary_key=True)
    codigo          = Column(String(20), unique=True)
    nombre          = Column(String(200), nullable=False)
    descripcion     = Column(Text)
    curso_id        = Column(Integer, ForeignKey("lms_curso.id"))
    programa_id     = Column(Integer, ForeignKey("lms_programa.id"))
    vigencia_meses  = Column(Integer, default=12)
    entidad_emisora = Column(String(200))
    activo          = Column(Boolean, default=True)

    certificados = relationship("LMSCertificadoUsuario", back_populates="certificacion")


class LMSCertificadoUsuario(Base, TimestampMixin):
    __tablename__ = "lms_certificado_usuario"
    id                  = Column(Integer, primary_key=True)
    certificacion_id    = Column(Integer, ForeignKey("lms_certificacion.id"), nullable=False)
    usuario_id          = Column(Integer, nullable=False)
    numero_certificado  = Column(String(50), unique=True)
    fecha_emision       = Column(DateTime, nullable=False)
    fecha_vencimiento   = Column(DateTime)
    estado              = Column(SQLEnum(EstadoCertificacionEnum), default=EstadoCertificacionEnum.VIGENTE)
    url_certificado     = Column(Text)

    certificacion = relationship("LMSCertificacion", back_populates="certificados")


class LMSInsignia(Base, TimestampMixin):
    __tablename__ = "lms_insignia"
    id               = Column(Integer, primary_key=True)
    nombre           = Column(String(200), nullable=False)
    descripcion      = Column(Text)
    icono            = Column(String(50))
    color            = Column(String(20), default="#D97706")
    tipo             = Column(String(50))
    criterio         = Column(Text)
    puntos_otorgados = Column(Integer, default=0)
    activo           = Column(Boolean, default=True)

    usuarios = relationship("LMSInsigniaUsuario", back_populates="insignia")


class LMSInsigniaUsuario(Base, TimestampMixin):
    __tablename__ = "lms_insignia_usuario"
    id              = Column(Integer, primary_key=True)
    insignia_id     = Column(Integer, ForeignKey("lms_insignia.id"), nullable=False)
    usuario_id      = Column(Integer, nullable=False)
    fecha_obtenida  = Column(DateTime, nullable=False)
    curso_id        = Column(Integer, ForeignKey("lms_curso.id"))

    insignia = relationship("LMSInsignia", back_populates="usuarios")


class LMSForo(Base, TimestampMixin):
    __tablename__ = "lms_foro"
    id          = Column(Integer, primary_key=True)
    curso_id    = Column(Integer, ForeignKey("lms_curso.id"))
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text)
    activo      = Column(Boolean, default=True)

    hilos = relationship("LMSHiloForo", back_populates="foro", cascade="all, delete-orphan")


class LMSHiloForo(Base, TimestampMixin):
    __tablename__ = "lms_hilo_foro"
    id         = Column(Integer, primary_key=True)
    foro_id    = Column(Integer, ForeignKey("lms_foro.id"), nullable=False)
    usuario_id = Column(Integer, nullable=False)
    titulo     = Column(String(300), nullable=False)
    contenido  = Column(Text, nullable=False)
    fijado     = Column(Boolean, default=False)

    foro        = relationship("LMSForo", back_populates="hilos")
    comentarios = relationship("LMSComentario", back_populates="hilo", cascade="all, delete-orphan")


class LMSComentario(Base, TimestampMixin):
    __tablename__ = "lms_comentario"
    id         = Column(Integer, primary_key=True)
    hilo_id    = Column(Integer, ForeignKey("lms_hilo_foro.id"), nullable=False)
    usuario_id = Column(Integer, nullable=False)
    contenido  = Column(Text, nullable=False)

    hilo = relationship("LMSHiloForo", back_populates="comentarios")


class LMSKPIDiario(Base, TimestampMixin):
    __tablename__ = "lms_kpi_diario"
    id                   = Column(Integer, primary_key=True)
    fecha                = Column(Date, nullable=False)
    total_usuarios       = Column(Integer, default=0)
    usuarios_activos     = Column(Integer, default=0)
    cursos_publicados    = Column(Integer, default=0)
    inscripciones_activas = Column(Integer, default=0)
    completados_hoy      = Column(Integer, default=0)
    horas_capacitacion   = Column(Numeric(10, 2), default=0)
    tasa_finalizacion    = Column(Numeric(5, 2), default=0)
    certificados_emitidos = Column(Integer, default=0)
    certificados_vencidos = Column(Integer, default=0)
    brechas_competencias = Column(Integer, default=0)
