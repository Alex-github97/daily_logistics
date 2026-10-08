"""
Mesa de ayuda: tickets, conversación y adjuntos.

Vive en el esquema `public` y no dentro del de cada cliente, a diferencia de
todo lo operativo. La razón es la cola: soporte necesita ver de un vistazo lo
de todas las empresas, y si cada ticket viviera en su esquema habría que
recorrer los veinte esquemas en cada consulta para armar una sola lista.

Además, un ticket no es información del cliente sobre su operación: es una
conversación entre él y quien opera la plataforma.
"""
import sqlalchemy as sa
from app.infrastructure.models.base import Base, TimestampMixin
from app.core.tenant import ESQUEMA_PLATAFORMA


# Estados del flujo, en el orden en que ocurren.
ESTADOS = ("NUEVO", "EN_PROGRESO", "ESPERANDO_CLIENTE", "RESUELTO", "CERRADO")

# La criticidad la fija soporte, no quien reporta: todo el mundo cree que lo
# suyo es urgente, y si la decidiera el usuario la cola dejaría de ordenar nada.
CRITICIDADES = ("BAJA", "MEDIA", "ALTA", "CRITICA")

# Lo que sí declara el usuario: cuánto lo afecta. Sirve de punto de partida
# para la criticidad, pero no la determina.
IMPACTOS = ("CONSULTA", "MOLESTIA", "BLOQUEA_TAREA", "OPERACION_DETENIDA")


class SoporteTicket(Base, TimestampMixin):
    """Un requerimiento de soporte."""

    __tablename__ = "soporte_ticket"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id     = sa.Column(sa.Integer, primary_key=True, index=True)
    # Consecutivo visible: es lo que la gente cita por teléfono.
    numero = sa.Column(sa.String(24), unique=True, nullable=False, index=True)

    # De qué empresa viene. Se guarda también el código porque el ticket se
    # consulta por él en cada petición del portal.
    cliente_id     = sa.Column(sa.Integer, nullable=False, index=True)
    cliente_codigo = sa.Column(sa.String(40), nullable=False, index=True)

    # Quién lo abrió, dentro de esa empresa.
    autor        = sa.Column(sa.String(80), nullable=False)
    autor_nombre = sa.Column(sa.String(160))
    autor_email  = sa.Column(sa.String(200))

    asunto      = sa.Column(sa.String(200), nullable=False)
    categoria   = sa.Column(sa.String(60))     # Error, Duda, Mejora, Datos…
    modulo      = sa.Column(sa.String(40))     # dónde le pasó
    impacto     = sa.Column(sa.String(30), default="MOLESTIA")

    estado      = sa.Column(sa.String(30), default="NUEVO", index=True)
    criticidad  = sa.Column(sa.String(20), default="MEDIA", index=True)
    asignado_a  = sa.Column(sa.String(80), index=True)

    # Para medir la atención sin depender de la memoria de nadie.
    primera_respuesta_en = sa.Column(sa.DateTime)
    resuelto_en          = sa.Column(sa.DateTime)
    cerrado_en           = sa.Column(sa.DateTime)
    # Se toca con cada mensaje: es por lo que se ordena la cola.
    ultima_actividad     = sa.Column(sa.DateTime, index=True)

    # ── Gestión ágil ──
    # Qué clase de trabajo es. Se propone desde la categoría que eligió el
    # cliente, pero el equipo lo corrige: quien reporta llama "error" a casi
    # todo.
    tipo_trabajo = sa.Column(sa.String(20), default="ERROR", index=True)
    # Estimación en puntos. Vacío = sin estimar, que es distinto de cero: una
    # solicitud sin estimar no puede entrar a un sprint con compromiso.
    puntos       = sa.Column(sa.Integer)
    sprint_id    = sa.Column(sa.Integer, index=True)
    epica_id     = sa.Column(sa.Integer, index=True)
    # Posición en el backlog. Se deja como float para poder insertar entre dos
    # sin reordenar toda la lista en cada arrastre.
    orden        = sa.Column(sa.Float, default=0, index=True)
    etiquetas    = sa.Column(sa.JSON)
    # Cuándo empezó a trabajarse de verdad. Con esto y `resuelto_en` sale el
    # tiempo de ciclo, que es lo que el equipo puede mejorar; el tiempo desde
    # que se creó incluye la espera en el backlog, que depende de otra cosa.
    iniciado_en  = sa.Column(sa.DateTime)


class SoporteMensaje(Base):
    """Cada intervención en la conversación de un ticket."""

    __tablename__ = "soporte_mensaje"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id        = sa.Column(sa.Integer, primary_key=True, index=True)
    ticket_id = sa.Column(sa.Integer, nullable=False, index=True)

    autor        = sa.Column(sa.String(80), nullable=False)
    autor_nombre = sa.Column(sa.String(160))
    # Distingue quién habla sin tener que cruzar con la tabla de usuarios, que
    # además vive en otro esquema.
    es_soporte   = sa.Column(sa.Boolean, default=False)

    cuerpo = sa.Column(sa.Text, nullable=False)
    # Nota interna del equipo: el cliente no la ve. Sin esto, coordinar entre
    # dos personas de soporte obligaría a salirse de la herramienta.
    interno = sa.Column(sa.Boolean, default=False)

    creado_en = sa.Column(sa.DateTime, nullable=False, index=True)


class SoporteAdjunto(Base):
    """Un archivo del ticket.

    Se guarda la ruta y no el contenido: la base no es lugar para binarios. La
    descarga pasa por un endpoint que comprueba permisos, no por una carpeta
    pública — un pantallazo de soporte puede traer datos de otra empresa.
    """

    __tablename__ = "soporte_adjunto"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = sa.Column(sa.Integer, primary_key=True, index=True)
    ticket_id  = sa.Column(sa.Integer, nullable=False, index=True)
    mensaje_id = sa.Column(sa.Integer, index=True)

    nombre    = sa.Column(sa.String(255), nullable=False)
    tipo_mime = sa.Column(sa.String(120))
    tamano    = sa.Column(sa.Integer)
    # Ruta relativa dentro de UPLOAD_DIR.
    ruta      = sa.Column(sa.String(400), nullable=False)

    subido_por = sa.Column(sa.String(80))
    creado_en  = sa.Column(sa.DateTime, nullable=False)


# ─── Gestión ágil ─────────────────────────────────────────────────────────────
#
# Lo de arriba resuelve "un cliente escribe y alguien responde". Esto resuelve
# la otra mitad: cómo el equipo decide qué hace primero, cuánto cabe en una
# iteración y si está mejorando o no.

# Qué clase de trabajo es. Un error y una mejora no se priorizan igual ni se
# estiman igual, y mezclarlos en una sola bolsa oculta cuánto se va en apagar
# incendios.
TIPOS_TRABAJO = ("ERROR", "MEJORA", "TAREA", "CONSULTA")

# Escala de Fibonacci. Es a propósito imprecisa: obliga a discutir el tamaño
# relativo en vez de fingir que se puede estimar en horas.
PUNTOS = (1, 2, 3, 5, 8, 13, 21)

ESTADOS_SPRINT = ("PLANEADO", "ACTIVO", "CERRADO")


class SoporteEpica(Base, TimestampMixin):
    """Un objetivo grande que agrupa varias solicitudes."""

    __tablename__ = "soporte_epica"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id          = sa.Column(sa.Integer, primary_key=True, index=True)
    nombre      = sa.Column(sa.String(160), nullable=False)
    descripcion = sa.Column(sa.Text)
    color       = sa.Column(sa.String(9))
    # Se archiva en vez de borrarse: sus solicitudes la referencian.
    archivada   = sa.Column(sa.Boolean, default=False)


class SoporteSprint(Base, TimestampMixin):
    """Una iteración con fecha de inicio y de fin.

    Solo puede haber una activa: dos iteraciones simultáneas hacen que
    "en qué estamos trabajando" deje de tener una respuesta.
    """

    __tablename__ = "soporte_sprint"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id       = sa.Column(sa.Integer, primary_key=True, index=True)
    nombre   = sa.Column(sa.String(120), nullable=False)
    # Para qué es esta iteración. Un sprint sin objetivo es una lista de tareas.
    objetivo = sa.Column(sa.Text)
    inicio   = sa.Column(sa.Date)
    fin      = sa.Column(sa.Date)
    estado   = sa.Column(sa.String(20), default="PLANEADO", index=True)

    # Se congela al cerrar: la velocidad histórica no puede cambiar porque
    # después alguien reestime una solicitud vieja.
    puntos_comprometidos = sa.Column(sa.Integer)
    puntos_completados   = sa.Column(sa.Integer)
    cerrado_en           = sa.Column(sa.DateTime)


class SoporteEvento(Base):
    """Cada cambio relevante de una solicitud.

    Existe por dos razones que van juntas: da el historial que explica por qué
    algo terminó donde terminó, y es de donde salen las métricas. Un burndown
    calculado sobre el estado actual mentiría —mostraría el pasado como si
    siempre hubiera sido así—; sobre los eventos, no.
    """

    __tablename__ = "soporte_evento"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id        = sa.Column(sa.Integer, primary_key=True, index=True)
    ticket_id = sa.Column(sa.Integer, nullable=False, index=True)
    campo     = sa.Column(sa.String(40), nullable=False)   # estado, puntos, sprint…
    anterior  = sa.Column(sa.String(120))
    nuevo     = sa.Column(sa.String(120))
    autor     = sa.Column(sa.String(80))
    fecha     = sa.Column(sa.DateTime, nullable=False, index=True)


class SoporteColumna(Base):
    """Las columnas del tablero y su límite de trabajo en curso.

    El límite no es un adorno: cuando se supera, el servidor rechaza el
    movimiento. Un límite que se puede exceder en silencio no limita nada, y el
    problema que resuelve —empezar diez cosas y no terminar ninguna— es
    exactamente el que aparece cuando nadie lo hace cumplir.
    """

    __tablename__ = "soporte_columna"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = sa.Column(sa.Integer, primary_key=True, index=True)
    estado     = sa.Column(sa.String(30), unique=True, nullable=False)
    titulo     = sa.Column(sa.String(60), nullable=False)
    orden      = sa.Column(sa.Integer, default=0)
    # Vacío = sin límite. Solo tiene sentido en las columnas de trabajo activo.
    limite_wip = sa.Column(sa.Integer)
