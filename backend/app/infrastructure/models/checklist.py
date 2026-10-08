"""
Checklists e inspecciones — modelo de datos.

LA JERARQUÍA DE CONFIGURACIÓN

    Clasificación → cómo se responde (Bueno/Regular/Malo, Sí/No, un número…)
    Sistema       → el sistema mecánico o electrónico del activo
    Pregunta      → pertenece a un sistema y se responde con una clasificación

Las preguntas son un **banco global**, no propiedad de una plantilla. «Nivel de
aceite del motor» se escribe una vez y sirve en la preoperacional diaria, en la
entrega de turno y en la revisión mensual. En el diseño anterior cada plantilla
tenía sus propias preguntas, así que la misma pregunta se repetía en cada una y
el tablero no podía agrupar «cuántas veces falló esto» entre plantillas.

    Plantilla → escoge del banco qué preguntas la componen
              → declara a qué tipos de activo aplica

Y al crear una inspección se elige primero el activo: solo aparecen las
plantillas configuradas para su tipo. Es el orden natural —se tiene el equipo
enfrente— y evita ofrecer una preoperacional de tractocamión para un
montacargas.

POR QUÉ LA CLASIFICACIÓN ES CONFIGURABLE Y NO UN ENUM
Antes el tipo de respuesta era una lista fija en el código. Cada empresa
califica distinto: unas usan Bueno/Regular/Malo, otras Cumple/No cumple, otras
una escala de 1 a 5. Cada opción declara si cuenta como conforme y cuánto
puntúa, así que «Regular» puede valer medio punto en vez de obligar a decidir
entre aprobado y reprobado.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint, Index,
)
from app.infrastructure.models.base import Base, TimestampMixin


# ══════════════════════════════════════════════════════════════════════════════
# NIVEL 1 · CLASIFICACIÓN — cómo se responde
# ══════════════════════════════════════════════════════════════════════════════

class ChkClasificacion(Base, TimestampMixin):
    """Una escala de respuesta reutilizable.

    `tipo` decide si se responde escogiendo una opción o escribiendo un valor:

        OPCIONES  Bueno / Regular / Malo, Sí / No, Cumple / No cumple…
        NUMERO    una medición, con su rango aceptable
        TEXTO     una nota libre
        FECHA     un vencimiento
    """
    __tablename__ = "eam_chk_clasificacion"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_chk_clasificacion_nombre"),)
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(120), nullable=False)
    descripcion = Column(String(300), nullable=True)
    tipo        = Column(String(20), default="OPCIONES", nullable=False)
    # Solo para NUMERO: fuera de este rango la respuesta se marca no conforme
    # sola, sin que el inspector tenga que decidirlo.
    unidad      = Column(String(20), nullable=True)
    valor_min   = Column(Float, nullable=True)
    valor_max   = Column(Float, nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)


class ChkOpcion(Base, TimestampMixin):
    """Una respuesta posible dentro de una clasificación.

    `conforme` y `puntaje` son lo que convierte una palabra en una calificación:
    «Bueno» conforme con puntaje 1, «Regular» con 0,5 y «Malo» no conforme con
    0. Sin el puntaje habría que decidir si Regular aprueba o reprueba, y ese
    matiz es justamente lo que se quiere registrar.
    """
    __tablename__ = "eam_chk_opcion"
    __table_args__ = (
        UniqueConstraint("clasificacion_id", "nombre", name="uq_eam_chk_opcion"),
    )
    id               = Column(Integer, primary_key=True, index=True)
    clasificacion_id = Column(Integer, ForeignKey("eam_chk_clasificacion.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    nombre  = Column(String(80), nullable=False)
    orden   = Column(Integer, default=0, nullable=False)
    # True cuenta como conforme, False como hallazgo, None es informativa y
    # queda fuera del cálculo.
    conforme = Column(Boolean, nullable=True)
    # De 0 a 1. Cuánto suma esta respuesta del peso de la pregunta.
    puntaje = Column(Float, default=1, nullable=False)
    color   = Column(String(9), nullable=True)
    activo  = Column(Boolean, default=True, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# NIVEL 2 · SISTEMA — qué parte del activo
# ══════════════════════════════════════════════════════════════════════════════

class ChkSistema(Base, TimestampMixin):
    """Sistema mecánico o electrónico del activo: motor, frenos, eléctrico,
    hidráulico, cabina, documentos.

    Es global y no por plantilla: así el tablero puede responder «qué sistema
    concentra los hallazgos» cruzando todas las inspecciones, que es la pregunta
    que lleva a una decisión de mantenimiento.
    """
    __tablename__ = "eam_chk_sistema"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_chk_sistema_nombre"),)
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(40), nullable=True)
    nombre      = Column(String(150), nullable=False)
    descripcion = Column(String(300), nullable=True)
    orden       = Column(Integer, default=0, nullable=False)
    activo      = Column(Boolean, default=True, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# NIVEL 3 · PREGUNTA — el banco reutilizable
# ══════════════════════════════════════════════════════════════════════════════

class ChkPregunta(Base, TimestampMixin):
    """Una pregunta del banco. Pertenece a un sistema y usa una clasificación.

    Nunca se borra de verdad: se desactiva. Hay respuestas históricas apuntando
    acá, y borrarla dejaría inspecciones firmadas con respuestas sin pregunta.
    """
    __tablename__ = "eam_chk_pregunta"
    __table_args__ = (
        Index("ix_eam_chk_pregunta_sistema", "sistema_id", "orden"),
    )
    id               = Column(Integer, primary_key=True, index=True)
    sistema_id       = Column(Integer, ForeignKey("eam_chk_sistema.id"), nullable=False, index=True)
    clasificacion_id = Column(Integer, ForeignKey("eam_chk_clasificacion.id"), nullable=False)
    texto  = Column(String(400), nullable=False)
    ayuda  = Column(String(400), nullable=True)
    orden  = Column(Integer, default=0, nullable=False)

    # Valores por defecto. Una plantilla puede endurecerlos para su caso.
    critico       = Column(Boolean, default=False, nullable=False)
    requiere_foto = Column(Boolean, default=False, nullable=False)
    exige_observacion_no_conforme = Column(Boolean, default=True, nullable=False)
    peso          = Column(Float, default=1, nullable=False)
    activo        = Column(Boolean, default=True, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGOS DE APOYO
# ══════════════════════════════════════════════════════════════════════════════

class ChkCategoria(Base, TimestampMixin):
    """Para qué sirve la plantilla: preoperacional, seguridad, entrega, calidad."""
    __tablename__ = "eam_chk_categoria"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_chk_categoria_nombre"),)
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(40), nullable=True)
    nombre      = Column(String(120), nullable=False)
    descripcion = Column(String(300), nullable=True)
    color       = Column(String(9), nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)


class ChkHallazgo(Base, TimestampMixin):
    """Catálogo de hallazgos tipificados. Espeja el catálogo de daños de llantas:
    permite pasar de «hubo 40 no conformidades» a «la fuga de aceite aparece en
    12 equipos de la misma línea». Un texto libre no agrupa."""
    __tablename__ = "eam_chk_hallazgo"
    __table_args__ = (UniqueConstraint("codigo", name="uq_eam_chk_hallazgo_codigo"),)
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(40), nullable=False)
    nombre      = Column(String(200), nullable=False)
    categoria   = Column(String(40), nullable=True)
    severidad   = Column(String(20), default="MODERADO", nullable=False)
    descripcion = Column(String(400), nullable=True)
    accion_sugerida = Column(String(300), nullable=True)
    genera_ot   = Column(Boolean, default=False, nullable=False)
    activo      = Column(Boolean, default=True, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# PLANTILLA — arma el checklist con preguntas del banco
# ══════════════════════════════════════════════════════════════════════════════

class ChkPlantilla(Base, TimestampMixin):
    __tablename__ = "eam_chk_plantilla"
    __table_args__ = (UniqueConstraint("codigo", name="uq_eam_chk_plantilla_codigo"),)
    id           = Column(Integer, primary_key=True, index=True)
    codigo       = Column(String(40), nullable=False)
    nombre       = Column(String(200), nullable=False)
    categoria_id = Column(Integer, ForeignKey("eam_chk_categoria.id"), nullable=True)
    descripcion  = Column(Text, nullable=True)

    # Sube sola al tocar la estructura. Las ejecuciones guardan la suya, así que
    # una inspección firmada hace seis meses sigue significando lo mismo.
    version = Column(Integer, default=1, nullable=False)

    periodicidad_dias = Column(Integer, nullable=True)
    requiere_firma    = Column(Boolean, default=False, nullable=False)
    umbral_aprobacion = Column(Float, default=100, nullable=False)
    # Un ítem crítico no conforme reprueba sin importar el porcentaje: unos
    # frenos malos no se compensan con veinte respuestas buenas.
    critico_reprueba  = Column(Boolean, default=True, nullable=False)
    genera_ot         = Column(Boolean, default=False, nullable=False)
    pide_medidor      = Column(Boolean, default=False, nullable=False)
    activo            = Column(Boolean, default=True, nullable=False)


class ChkPlantillaTipo(Base, TimestampMixin):
    """A qué tipos de activo aplica la plantilla.

    Es una tabla y no una columna porque una misma inspección suele servir para
    varias categorías —un preoperacional de «vehículo» y «remolque»—, y porque
    es lo que filtra las plantillas cuando se elige el activo.
    """
    __tablename__ = "eam_chk_plantilla_tipo"
    __table_args__ = (
        UniqueConstraint("plantilla_id", "tipo_activo", name="uq_eam_chk_plantilla_tipo"),
    )
    id           = Column(Integer, primary_key=True, index=True)
    plantilla_id = Column(Integer, ForeignKey("eam_chk_plantilla.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    tipo_activo  = Column(String(50), nullable=False, index=True)
    # Afinamiento opcional dentro del tipo, con la jerarquía del CMMS.
    marca = Column(String(100), nullable=True)
    linea = Column(String(100), nullable=True)


class ChkPlantillaPregunta(Base, TimestampMixin):
    """Qué preguntas del banco componen la plantilla, y en qué orden.

    Los campos `_override` permiten que la misma pregunta sea crítica en la
    preoperacional diaria y no en la revisión mensual, sin duplicarla en el
    banco. Vacíos, manda lo que diga la pregunta.
    """
    __tablename__ = "eam_chk_plantilla_pregunta"
    __table_args__ = (
        UniqueConstraint("plantilla_id", "pregunta_id", name="uq_eam_chk_plantilla_pregunta"),
        Index("ix_eam_chk_plpr_orden", "plantilla_id", "orden"),
    )
    id           = Column(Integer, primary_key=True, index=True)
    plantilla_id = Column(Integer, ForeignKey("eam_chk_plantilla.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    pregunta_id  = Column(Integer, ForeignKey("eam_chk_pregunta.id"), nullable=False, index=True)
    orden        = Column(Integer, default=0, nullable=False)
    obligatorio  = Column(Boolean, default=True, nullable=False)
    peso_override    = Column(Float, nullable=True)
    critico_override = Column(Boolean, nullable=True)
    foto_override    = Column(Boolean, nullable=True)
    activo       = Column(Boolean, default=True, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# EJECUCIÓN
# ══════════════════════════════════════════════════════════════════════════════

class ChkEjecucion(Base, TimestampMixin):
    __tablename__ = "eam_chk_ejecucion"
    __table_args__ = (
        UniqueConstraint("numero", name="uq_eam_chk_ejecucion_numero"),
        Index("ix_eam_chk_ejecucion_activo_fecha", "activo_id", "fecha_inicio"),
    )
    id           = Column(Integer, primary_key=True, index=True)
    numero       = Column(String(40), nullable=False)
    plantilla_id = Column(Integer, ForeignKey("eam_chk_plantilla.id"), nullable=False, index=True)
    plantilla_version = Column(Integer, default=1, nullable=False)
    activo_id    = Column(Integer, ForeignKey("eam_activo.id"), nullable=False, index=True)
    ot_id        = Column(Integer, ForeignKey("eam_orden_trabajo.id"), nullable=True)

    ejecutado_por = Column(String(120), nullable=True)
    fecha_inicio  = Column(DateTime, nullable=False)
    fecha_fin     = Column(DateTime, nullable=True)

    estado    = Column(String(20), default="BORRADOR", nullable=False)
    resultado = Column(String(30), default="PENDIENTE", nullable=False)

    pct_conforme  = Column(Float, nullable=True)
    total_items   = Column(Integer, default=0)
    no_conformes  = Column(Integer, default=0)
    criticos_no_conformes = Column(Integer, default=0)

    odometro   = Column(Float, nullable=True)
    horometro  = Column(Float, nullable=True)
    ubicacion  = Column(String(200), nullable=True)
    latitud    = Column(Float, nullable=True)
    longitud   = Column(Float, nullable=True)

    observaciones = Column(Text, nullable=True)
    firma_nombre  = Column(String(150), nullable=True)
    firma_archivo = Column(String(400), nullable=True)
    firma_fecha   = Column(DateTime, nullable=True)


class ChkRespuesta(Base, TimestampMixin):
    """La respuesta a una pregunta dentro de una inspección.

    Apunta a la pregunta del banco y no a la fila de la plantilla: la pregunta
    es la entidad estable, y así el histórico sobrevive a que alguien saque esa
    pregunta de la plantilla.
    """
    __tablename__ = "eam_chk_respuesta"
    __table_args__ = (
        UniqueConstraint("ejecucion_id", "pregunta_id", name="uq_eam_chk_respuesta"),
    )
    id           = Column(Integer, primary_key=True, index=True)
    ejecucion_id = Column(Integer, ForeignKey("eam_chk_ejecucion.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    pregunta_id  = Column(Integer, ForeignKey("eam_chk_pregunta.id"), nullable=False)

    # La opción escogida, cuando la clasificación es de opciones.
    opcion_id    = Column(Integer, ForeignKey("eam_chk_opcion.id"), nullable=True)
    valor_texto  = Column(Text, nullable=True)
    valor_numero = Column(Float, nullable=True)

    # Se congelan al responder: si mañana cambia el puntaje de «Regular», la
    # inspección de ayer conserva la calificación con la que se firmó.
    conforme = Column(Boolean, nullable=True)
    puntaje  = Column(Float, nullable=True)

    observacion = Column(Text, nullable=True)
    hallazgo_id = Column(Integer, ForeignKey("eam_chk_hallazgo.id"), nullable=True)
    # El activo no tiene ese componente: sale del divisor en vez de contar como
    # fallo. Castigar a un equipo por no tener algo que nunca debió tener
    # produce números que nadie respeta.
    no_aplica   = Column(Boolean, default=False, nullable=False)


class ChkFoto(Base, TimestampMixin):
    """Evidencia fotográfica. Varias por respuesta, o de la inspección completa.

    La ruta lleva el esquema del cliente adentro: dos empresas pueden tener la
    inspección número 5, y sin eso la segunda pisaría el archivo de la primera.
    """
    __tablename__ = "eam_chk_foto"
    id           = Column(Integer, primary_key=True, index=True)
    ejecucion_id = Column(Integer, ForeignKey("eam_chk_ejecucion.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    respuesta_id = Column(Integer, ForeignKey("eam_chk_respuesta.id", ondelete="CASCADE"),
                          nullable=True, index=True)
    archivo   = Column(String(500), nullable=False)
    nombre    = Column(String(200), nullable=True)
    tipo_mime = Column(String(100), nullable=True)
    tamano    = Column(Integer, nullable=True)
    nota      = Column(String(300), nullable=True)
    subido_por = Column(String(120), nullable=True)


class ChkProgramacion(Base, TimestampMixin):
    """Cuándo le toca la próxima inspección a cada activo."""
    __tablename__ = "eam_chk_programacion"
    __table_args__ = (
        UniqueConstraint("plantilla_id", "activo_id", name="uq_eam_chk_programacion"),
    )
    id           = Column(Integer, primary_key=True, index=True)
    plantilla_id = Column(Integer, ForeignKey("eam_chk_plantilla.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    activo_id    = Column(Integer, ForeignKey("eam_activo.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    ultima_fecha = Column(DateTime, nullable=True)
    ultima_ejecucion_id = Column(
        Integer, ForeignKey("eam_chk_ejecucion.id", ondelete="SET NULL"), nullable=True)
    proxima_fecha = Column(DateTime, nullable=True)
    activo        = Column(Boolean, default=True, nullable=False)
