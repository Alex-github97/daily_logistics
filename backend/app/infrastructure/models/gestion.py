"""
Gestión de proyectos e incidencias.

Vive en `public`, junto a la mesa de ayuda y por la misma razón: el equipo que
opera la plataforma necesita ver de un vistazo el trabajo de todas las empresas.
Si cada incidencia viviera en el esquema de su cliente habría que recorrer los
veinte esquemas para armar un solo backlog.

La pieza central es `gp_incidencia` y es deliberadamente estrecha: identidad,
proyecto, tipo, estado, prioridad, personas, jerarquía y fechas. Nada del
negocio de nadie. Todo lo que varía entre un proyecto y otro entra por campos
configurables, que se guardan en una columna `jsonb` y se describen en
`gp_campo`. La regla que gobierna este archivo: **si atender una necesidad nueva
exige un ALTER TABLE, el diseño falló**.

Por qué jsonb y no EAV (entidad-atributo-valor, una fila por campo): con EAV,
filtrar por cuatro campos son cuatro JOIN, y leer cien incidencias con diez
campos cada una son mil filas que hay que recomponer en memoria. Con jsonb, una
incidencia es una fila. Lo que EAV daba —tipado e índices por campo— se recupera
con el registro de definiciones, que valida en la aplicación, y con un índice por
expresión creado sobre cada campo que se marque como filtrable.

Dimensionado sin techo, porque no sabemos hasta dónde llegue esto:
  · Las claves son BIGINT. Cambiar el tipo de una llave primaria con millones de
    filas ya escritas es una operación de horas con la tabla bloqueada.
  · El historial va particionado por año (ver `main.py`): es la tabla que de
    verdad explota —una veintena de filas por cada incidencia— y convertirla en
    particionada después obliga a reescribirla entera.
  · La numeración visible es por proyecto y sale de un contador propio, no de un
    `max(numero)+1` global: eso último es una carrera y un punto de contención
    que se nota justo cuando el sistema empieza a importar.
  · Los índices están pensados para paginar por cursor. `OFFSET 500000` recorre
    medio millón de filas para descartarlas.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from app.infrastructure.models.base import Base, TimestampMixin
from app.core.tenant import ESQUEMA_PLATAFORMA

ESQ = ESQUEMA_PLATAFORMA


def _fk(tabla: str) -> str:
    """Referencia a otra tabla del módulo, calificada con su esquema.

    Hay que calificarla: el `search_path` de la petición apunta al esquema del
    cliente, así que una referencia a secas se resolvería allí y no encontraría
    nada.
    """
    return f"{ESQ}.{tabla}"


# ─── Vocabulario ──────────────────────────────────────────────────────────────
#
# Van como tuplas de texto y no como enums de PostgreSQL a propósito: un enum de
# base de datos exige un ALTER TYPE para agregar un valor, y estas listas están
# hechas para que crezcan. Lo que sí es configurable de verdad —estados, tipos de
# incidencia, prioridades— vive en tablas, no acá; esto es solo lo que el motor
# necesita entender por sí mismo.

# La categoría dice qué significa un estado para las métricas. El nombre del
# estado lo pone cada equipo ("En revisión", "Esperando QA"), pero el motor tiene
# que saber si eso cuenta como trabajo en curso o como terminado; si no, no hay
# forma de calcular tiempo de ciclo ni de dibujar un burndown.
CATEGORIAS_ESTADO = ("SIN_CLASIFICAR", "POR_HACER", "EN_CURSO", "TERMINADO")

# Cómo se relacionan dos incidencias. Cada vínculo se guarda una sola vez y se
# lee en los dos sentidos: guardarlo dos veces obliga a mantenerlos sincronizados
# y tarde o temprano quedan contradiciéndose.
TIPOS_VINCULO = ("BLOQUEA", "DUPLICA", "RELACIONA", "CAUSA")

# Los tipos de campo que el motor sabe validar, mostrar y filtrar. Agregar uno
# es registrar su validador y su control de formulario, no tocar tablas.
TIPOS_CAMPO = (
    # De dato
    "TEXTO", "TEXTO_LARGO", "TEXTO_RICO", "NUMERO", "DECIMAL",
    "FECHA", "FECHA_HORA", "BOOLEANO", "URL", "CORREO",
    # De selección, con opciones propias
    "LISTA", "LISTA_MULTIPLE", "ETIQUETAS",
    # De selección, con opciones que salen de una entidad del sistema. Son los
    # que hacen falta para que el formulario no tenga controles cableados: un
    # campo de tipo SPRINT sabe pedirle los sprints al proyecto en curso.
    "USUARIO", "USUARIOS", "PROYECTO", "INCIDENCIA", "TIPO_INCIDENCIA",
    "SPRINT", "EPICA", "VERSION", "COMPONENTE", "PRIORIDAD", "ESTADO",
    # Archivos
    "ADJUNTO",
)

# Los que se resuelven consultando una tabla en vez de una lista escrita a mano.
TIPOS_DE_ENTIDAD = {
    "USUARIO": "usuario", "USUARIOS": "usuario",
    "PROYECTO": "proyecto", "INCIDENCIA": "incidencia",
    "TIPO_INCIDENCIA": "tipo_incidencia", "SPRINT": "sprint", "EPICA": "epica",
    "VERSION": "version", "COMPONENTE": "componente",
    "PRIORIDAD": "prioridad", "ESTADO": "estado",
}

# Los que admiten varios valores a la vez.
TIPOS_MULTIPLES = ("LISTA_MULTIPLE", "ETIQUETAS", "USUARIOS", "COMPONENTE")

# Las secciones del formulario, en el orden en que se muestran. No es adorno:
# con veinte campos en una sola lista, llenar el formulario es un recorrido a
# ciegas.
SECCIONES = (
    ("PRINCIPAL", "Información principal"),
    ("AGIL", "Planificación"),
    ("CLASIFICACION", "Clasificación"),
    ("DETALLE", "Detalle de la incidencia"),
    ("FECHAS", "Fechas"),
    ("AVANZADO", "Avanzado"),
)

# De dónde salen las opciones de un campo de selección.
ORIGENES = ("PROPIO", "ENTIDAD")

# Dónde se guarda su valor.
ALMACENAMIENTOS = ("JSONB", "COLUMNA")

# Qué puede hacer alguien dentro de un proyecto. El permiso se comprueba en el
# servidor, en cada endpoint y contra el objeto concreto: la pregunta no es
# "¿puede ver incidencias?" sino "¿puede ver ESTA?".
ROLES_PROYECTO = ("LIDER", "MIEMBRO", "OBSERVADOR")

ESTADOS_SPRINT = ("PLANEADO", "ACTIVO", "CERRADO")

# Nivel en la jerarquía. Un tipo de incidencia declara en qué nivel vive, y con
# eso el motor sabe qué puede colgar de qué sin que nadie codifique las reglas.
NIVELES = ("EPICA", "NORMAL", "SUBTAREA")


# ─── Configuración: cómo se comporta cada proyecto ────────────────────────────

class GPWorkflow(Base, TimestampMixin):
    """Un flujo de estados con sus transiciones.

    Los estados y las transiciones son datos, no código. Cambiar cómo trabaja un
    equipo es configurar, no desplegar.
    """

    __tablename__ = "gp_workflow"
    __table_args__ = {"schema": ESQ}

    id          = sa.Column(sa.BigInteger, primary_key=True)
    nombre      = sa.Column(sa.String(120), nullable=False)
    descripcion = sa.Column(sa.Text)
    # El que se ofrece a los proyectos nuevos. Solo uno puede serlo.
    por_defecto = sa.Column(sa.Boolean, default=False, nullable=False)
    # Se archiva en vez de borrarse: hay incidencias que apuntan a sus estados.
    archivado   = sa.Column(sa.Boolean, default=False, nullable=False)


class GPEstado(Base):
    """Una posición dentro de un flujo."""

    __tablename__ = "gp_estado"
    __table_args__ = (
        sa.UniqueConstraint("workflow_id", "clave", name="uq_gp_estado_clave"),
        sa.Index("ix_gp_estado_workflow", "workflow_id", "orden"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    workflow_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_workflow.id")),
                            nullable=False)

    clave     = sa.Column(sa.String(40), nullable=False)
    nombre    = sa.Column(sa.String(60), nullable=False)
    # Qué significa para las métricas. Ver CATEGORIAS_ESTADO.
    categoria = sa.Column(sa.String(20), default="POR_HACER", nullable=False)
    color     = sa.Column(sa.String(9))
    orden     = sa.Column(sa.Integer, default=0, nullable=False)

    # Dónde entra una incidencia recién creada.
    inicial = sa.Column(sa.Boolean, default=False, nullable=False)

    # Límite de trabajo en curso. Vacío = sin límite. Cuando se supera, el
    # servidor rechaza la transición: un límite que se puede exceder en silencio
    # no limita nada, y el problema que resuelve —empezar diez cosas y no
    # terminar ninguna— es justo el que aparece cuando nadie lo hace cumplir.
    limite_wip = sa.Column(sa.Integer)


class GPTransicion(Base):
    """Un movimiento permitido entre dos estados.

    Las condiciones, validaciones y acciones se guardan como listas de objetos
    `{"clave": "...", "config": {...}}`. La clave resuelve una función registrada
    en el servidor: agregar una regla nueva es registrar una función, y usarla es
    configurar. Guardar código aquí sería darle a quien configure la capacidad de
    ejecutar lo que quiera dentro del proceso.
    """

    __tablename__ = "gp_transicion"
    __table_args__ = (
        sa.Index("ix_gp_transicion_origen", "workflow_id", "origen_id"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    workflow_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_workflow.id")),
                            nullable=False)
    nombre      = sa.Column(sa.String(60), nullable=False)

    # Vacío = se puede llegar desde cualquier estado. Es lo que hace posible un
    # "Cancelar" sin declarar una transición por cada estado de origen.
    origen_id  = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_estado.id")))
    destino_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_estado.id")),
                           nullable=False)

    # ¿Quién puede moverla? ¿Hay cupo en la columna de destino?
    condiciones  = sa.Column(JSONB, default=list, nullable=False)
    # ¿Qué campos exige antes de dejar pasar?
    validaciones = sa.Column(JSONB, default=list, nullable=False)
    # Qué pasa después: asignar, comentar, notificar, sellar una fecha.
    acciones     = sa.Column(JSONB, default=list, nullable=False)

    orden = sa.Column(sa.Integer, default=0, nullable=False)


class GPProyecto(Base, TimestampMixin):
    """Un espacio de trabajo con su propia configuración y su propia numeración."""

    __tablename__ = "gp_proyecto"
    __table_args__ = (
        sa.Index("ix_gp_proyecto_archivado", "archivado", "nombre"),
        {"schema": ESQ},
    )

    id = sa.Column(sa.BigInteger, primary_key=True)

    # El prefijo de las claves visibles: ERP-123. Es lo que la gente cita.
    clave  = sa.Column(sa.String(12), unique=True, nullable=False, index=True)
    nombre = sa.Column(sa.String(160), nullable=False)
    descripcion = sa.Column(sa.Text)
    icono  = sa.Column(sa.String(16))
    color  = sa.Column(sa.String(9))

    lider       = sa.Column(sa.String(80), index=True)
    workflow_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_workflow.id")))

    # El consecutivo de este proyecto. Se incrementa con
    # `UPDATE ... RETURNING`, que toma el bloqueo de la fila y serializa solo a
    # quienes creen incidencias en ESTE proyecto. Un contador global sería un
    # cuello de botella para todos a la vez, y `max(numero)+1` es una carrera:
    # dos altas simultáneas leen el mismo máximo y producen la misma clave.
    contador = sa.Column(sa.BigInteger, default=0, nullable=False)

    # Solo los miembros lo ven. Por omisión un proyecto es visible para todo el
    # equipo: esconder por defecto hace que la gente no encuentre su trabajo.
    restringido = sa.Column(sa.Boolean, default=False, nullable=False)

    # Cada solicitud de soporte crea su incidencia automáticamente. Encendido por
    # omisión: así nada se pierde porque alguien olvidó clasificar. Las consultas
    # que se resuelven en el chat quedan en estado SIN_CLASIFICAR y no ensucian
    # el backlog ni las métricas. Si en un proyecto resulta ser ruido, se apaga
    # y clasificar pasa a ser un clic desde la cola.
    incidencia_automatica = sa.Column(sa.Boolean, default=True, nullable=False)

    archivado = sa.Column(sa.Boolean, default=False, nullable=False)


class GPProyectoMiembro(Base):
    """Quién participa en un proyecto y con qué alcance."""

    __tablename__ = "gp_proyecto_miembro"
    __table_args__ = (
        sa.UniqueConstraint("proyecto_id", "usuario", name="uq_gp_miembro"),
        sa.Index("ix_gp_miembro_usuario", "usuario"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")),
                            nullable=False)
    # El `username` del operador. No se referencia `usuarios.id` porque esa tabla
    # vive dentro del esquema de cada cliente y esto vive en `public`.
    usuario = sa.Column(sa.String(80), nullable=False)
    rol     = sa.Column(sa.String(20), default="MIEMBRO", nullable=False)


class GPVersion(Base, TimestampMixin):
    """Una versión del producto: en cuál se vio un fallo y en cuál se corrige.

    Va en tabla y no en un campo de texto porque son dos preguntas distintas
    —«versión afectada» y «versión en la que se corrige»— sobre la MISMA lista, y
    porque hace falta poder preguntar «qué entra en la 2.4» sin que la respuesta
    dependa de que todo el mundo la haya escrito igual.
    """

    __tablename__ = "gp_version"
    __table_args__ = (
        sa.UniqueConstraint("proyecto_id", "nombre", name="uq_gp_version"),
        sa.Index("ix_gp_version_proyecto", "proyecto_id", "orden"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")),
                            nullable=False)

    nombre      = sa.Column(sa.String(60), nullable=False)
    descripcion = sa.Column(sa.Text)
    fecha       = sa.Column(sa.Date)
    # Liberada = ya salió. No se borra: hay incidencias que la mencionan y el
    # historial de qué se entregó cuándo es justo lo que se quiere conservar.
    liberada    = sa.Column(sa.Boolean, default=False, nullable=False)
    archivada   = sa.Column(sa.Boolean, default=False, nullable=False)
    orden       = sa.Column(sa.Integer, default=0, nullable=False)


class GPComponente(Base, TimestampMixin):
    """Una pieza del producto: API, interfaz, base de datos, integraciones…

    Lleva responsable propio porque el sentido de dividir en componentes es que
    cada uno tenga a alguien que responda por él; sin eso es una etiqueta más.
    """

    __tablename__ = "gp_componente"
    __table_args__ = (
        sa.UniqueConstraint("proyecto_id", "nombre", name="uq_gp_componente"),
        sa.Index("ix_gp_componente_proyecto", "proyecto_id", "orden"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")),
                            nullable=False)

    nombre      = sa.Column(sa.String(80), nullable=False)
    descripcion = sa.Column(sa.Text)
    # A quién se le asigna por omisión lo que caiga en este componente.
    responsable = sa.Column(sa.String(80))
    color       = sa.Column(sa.String(9))
    archivado   = sa.Column(sa.Boolean, default=False, nullable=False)
    orden       = sa.Column(sa.Integer, default=0, nullable=False)


class GPTipoVinculo(Base):
    """Cómo se pueden relacionar dos incidencias, con su nombre en cada sentido.

    El nombre inverso es lo que hace falta: el vínculo se guarda una sola vez
    —A bloquea a B— y se lee en los dos sentidos, así que hay que saber cómo se
    llama visto desde B («bloqueada por»). Guardar las dos mitades obligaría a
    mantenerlas sincronizadas y tarde o temprano quedarían contradiciéndose.
    """

    __tablename__ = "gp_tipo_vinculo"
    __table_args__ = {"schema": ESQ}

    id      = sa.Column(sa.BigInteger, primary_key=True)
    clave   = sa.Column(sa.String(30), unique=True, nullable=False)
    # Cómo se lee desde el origen: «bloquea a».
    nombre  = sa.Column(sa.String(60), nullable=False)
    # Y desde el destino: «bloqueada por».
    inverso = sa.Column(sa.String(60), nullable=False)
    orden   = sa.Column(sa.Integer, default=0, nullable=False)
    activo  = sa.Column(sa.Boolean, default=True, nullable=False)


class GPTipoIncidencia(Base):
    """Error, Mejora, Tarea, Épica… con el flujo que le corresponde a cada uno.

    Un error y una mejora no se priorizan igual ni recorren los mismos estados.
    Con `proyecto_id` vacío el tipo es global y sirve a todos los proyectos.
    """

    __tablename__ = "gp_tipo_incidencia"
    __table_args__ = (
        sa.Index("ix_gp_tipo_proyecto", "proyecto_id", "orden"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")))

    clave  = sa.Column(sa.String(40), nullable=False)
    nombre = sa.Column(sa.String(60), nullable=False)
    icono  = sa.Column(sa.String(16))
    color  = sa.Column(sa.String(9))

    # De qué nivel es. El motor deduce de acá qué puede colgar de qué, en vez de
    # llevar las reglas de jerarquía escritas en el código.
    nivel = sa.Column(sa.String(20), default="NORMAL", nullable=False)

    # Vacío = usa el del proyecto.
    workflow_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_workflow.id")))
    orden       = sa.Column(sa.Integer, default=0, nullable=False)
    archivado   = sa.Column(sa.Boolean, default=False, nullable=False)


class GPPrioridad(Base):
    """La escala de prioridades, configurable como todo lo demás.

    Va en tabla y no como lista fija porque cada organización usa la suya, y
    porque el orden importa: es por lo que se ordena una cola.
    """

    __tablename__ = "gp_prioridad"
    __table_args__ = {"schema": ESQ}

    id     = sa.Column(sa.BigInteger, primary_key=True)
    clave  = sa.Column(sa.String(30), unique=True, nullable=False)
    nombre = sa.Column(sa.String(60), nullable=False)
    color  = sa.Column(sa.String(9))
    # Menor = más urgente, para poder ordenar ascendente sin invertir nada.
    orden  = sa.Column(sa.Integer, default=0, nullable=False)
    por_defecto = sa.Column(sa.Boolean, default=False, nullable=False)


# ─── Campos configurables ─────────────────────────────────────────────────────

class GPCampo(Base, TimestampMixin):
    """La definición de un campo. El valor vive en `gp_incidencia.campos`.

    Esta tabla es la única fuente de verdad: de acá salen el formulario, la
    validación del servidor y lo que el motor de filtros acepta como
    identificador. Que sean la misma definición es lo que impide el caso clásico
    —la pantalla acepta un campo que el servidor descarta al guardar—.
    """

    __tablename__ = "gp_campo"
    __table_args__ = (
        sa.Index("ix_gp_campo_filtrable", "filtrable"),
        {"schema": ESQ},
    )

    id = sa.Column(sa.BigInteger, primary_key=True)

    # Con lo que se nombra el campo en un filtro y la llave dentro del jsonb.
    # Se restringe a minúsculas, dígitos y guion bajo al crearlo: termina dentro
    # de una expresión de índice, y ahí no puede entrar nada arbitrario.
    clave       = sa.Column(sa.String(60), unique=True, nullable=False)
    nombre      = sa.Column(sa.String(120), nullable=False)
    descripcion = sa.Column(sa.Text)
    ayuda       = sa.Column(sa.String(300))

    tipo = sa.Column(sa.String(30), nullable=False)

    # ── De dónde salen las opciones ──
    #
    # PROPIO   → de `gp_campo_opcion`, la lista que el administrador escribe.
    # ENTIDAD  → de una tabla del sistema: usuarios, sprints, épicas, versiones…
    #
    # Esta distinción es lo que evita el error de tener un catálogo «Proyecto»
    # paralelo a la tabla de proyectos. Cuando el origen es una entidad, las
    # opciones se consultan en el momento y se filtran por el proyecto en curso,
    # así que un sprint nuevo aparece en el formulario sin que nadie configure
    # nada.
    origen  = sa.Column(sa.String(20), default="PROPIO", nullable=False)
    # Qué entidad, cuando el origen es ENTIDAD. Ver `ENTIDADES` en
    # `core/gestion_formulario.py`, que es la lista cerrada de lo consultable.
    entidad = sa.Column(sa.String(40))

    # ── Dónde se guarda el valor ──
    #
    # JSONB   → en `gp_incidencia.campos`. Es lo normal: un campo que el
    #           administrador crea no puede agregar una columna a la tabla.
    # COLUMNA → en una columna de `gp_incidencia`. Solo para los del sistema
    #           —título, responsable, prioridad, sprint…—, que existían antes que
    #           este registro.
    #
    # Tenerlos a los dos en el MISMO registro es lo que permite que el formulario
    # se dibuje entero desde la configuración. Con los nativos por fuera, la
    # pantalla tendría una mitad cableada y otra dinámica, y ordenar un campo
    # propio por encima del título sería imposible.
    almacenamiento = sa.Column(sa.String(12), default="JSONB", nullable=False)
    # La columna, cuando el almacenamiento es COLUMNA.
    columna = sa.Column(sa.String(40))

    # En qué parte del formulario aparece. Con veinte campos en una sola lista,
    # llenar el formulario se vuelve un recorrido a ciegas.
    seccion = sa.Column(sa.String(30), default="DETALLE", nullable=False)
    # Orden dentro de su sección, cuando el esquema no diga otra cosa.
    orden   = sa.Column(sa.Integer, default=0, nullable=False)

    # Reglas propias del tipo: mínimo, máximo, expresión regular, decimales.
    # Las aplica el servidor, no el navegador.
    validacion = sa.Column(JSONB, default=dict, nullable=False)
    # Lo que se propone al crear. Puede ser vacío, que es distinto de cero.
    # Admite señales que el servidor resuelve: "@yo", "@hoy", "@sprint_activo".
    valor_defecto = sa.Column(JSONB)

    # Se puede nombrar en un filtro. Al marcarlo, el servidor crea el índice por
    # expresión correspondiente; al desmarcarlo, lo borra. Así se paga un índice
    # por cada campo que de verdad se consulta y ninguno por los demás, sin que
    # nadie tenga que escribir SQL.
    filtrable = sa.Column(sa.Boolean, default=False, nullable=False)
    ordenable = sa.Column(sa.Boolean, default=False, nullable=False)

    # Los del sistema no se pueden borrar ni renombrar: hay filtros guardados y
    # tableros que los nombran.
    del_sistema = sa.Column(sa.Boolean, default=False, nullable=False)
    archivado   = sa.Column(sa.Boolean, default=False, nullable=False)


class GPCampoOpcion(Base):
    """Cada opción de un campo de lista."""

    __tablename__ = "gp_campo_opcion"
    __table_args__ = (
        sa.UniqueConstraint("campo_id", "valor", name="uq_gp_campo_opcion"),
        sa.Index("ix_gp_campo_opcion", "campo_id", "orden"),
        {"schema": ESQ},
    )

    id       = sa.Column(sa.BigInteger, primary_key=True)
    campo_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_campo.id")),
                         nullable=False)

    valor    = sa.Column(sa.String(120), nullable=False)
    etiqueta = sa.Column(sa.String(160), nullable=False)
    color    = sa.Column(sa.String(9))
    orden    = sa.Column(sa.Integer, default=0, nullable=False)
    # Se archiva y no se borra: hay incidencias que ya la guardaron.
    archivada = sa.Column(sa.Boolean, default=False, nullable=False)


class GPEsquemaCampo(Base):
    """Qué campos aplican a un tipo de incidencia dentro de un proyecto.

    Sin esto, o todos los campos salen en todos los formularios, o hay que
    programar cada combinación. Con `proyecto_id` vacío la regla es global.
    """

    __tablename__ = "gp_esquema_campo"
    __table_args__ = (
        sa.Index("ix_gp_esquema_busca", "proyecto_id", "tipo_id", "orden"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")))
    tipo_id     = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_tipo_incidencia.id")))
    campo_id    = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_campo.id")),
                            nullable=False)

    obligatorio = sa.Column(sa.Boolean, default=False, nullable=False)
    # Se ve pero no se edita: útil para lo que llena una automatización.
    solo_lectura = sa.Column(sa.Boolean, default=False, nullable=False)
    # Sale del formulario sin borrar la regla ni los valores ya escritos. Es lo
    # que permite apagar un campo para un tipo concreto sin tocar a los demás.
    visible = sa.Column(sa.Boolean, default=True, nullable=False)
    orden = sa.Column(sa.Integer, default=0, nullable=False)


# ─── El núcleo ────────────────────────────────────────────────────────────────

class GPIncidencia(Base, TimestampMixin):
    """Una unidad de trabajo. La tabla que no debería cambiar nunca.

    Sobre los dos títulos: cuando una incidencia nace de una solicitud de
    soporte, `resumen` arranca como copia del asunto que escribió el cliente y a
    partir de ahí el equipo lo reescribe libremente, a medida que entiende mejor
    el pedido. El asunto original se queda intacto en `soporte_ticket` porque es
    lo que el cliente ve en su conversación y es la evidencia de qué fue lo que
    pidió: si fueran el mismo campo, reescribirlo le cambiaría al cliente el
    título de su propio chat por uno que él nunca escribió.
    """

    __tablename__ = "gp_incidencia"
    __table_args__ = (
        # La clave visible. Única dentro del proyecto, no en toda la base.
        sa.UniqueConstraint("proyecto_id", "numero", name="uq_gp_incidencia_numero"),

        # El orden natural de una lista, y el que permite paginar por cursor:
        # se incluye `id` para desempatar, porque sin un orden total estricto el
        # cursor repite o se salta filas cuando dos comparten fecha.
        sa.Index("ix_gp_inc_proy_actualizado", "proyecto_id",
                 sa.text("actualizado DESC"), sa.text("id DESC")),

        # El tablero y las listas por estado.
        sa.Index("ix_gp_inc_proy_estado", "proyecto_id", "estado_id", "orden"),
        # "lo mío", que es la consulta más frecuente de todas.
        sa.Index("ix_gp_inc_asignado", "asignado", "estado_id"),
        # El tablero de sprint.
        sa.Index("ix_gp_inc_sprint", "sprint_id", "orden"),
        # Subtareas de una incidencia.
        sa.Index("ix_gp_inc_padre", "padre_id"),
        # Vencimientos.
        sa.Index("ix_gp_inc_vence", "vence"),

        # Pertenencia y existencia dentro de los campos configurables. `jsonb_path_ops`
        # es más pequeño y más rápido que el GIN por omisión, a cambio de soportar
        # menos operadores; los que perdemos no los usa el motor de filtros.
        sa.Index("ix_gp_inc_campos", "campos",
                 postgresql_using="gin",
                 postgresql_ops={"campos": "jsonb_path_ops"}),

        # Búsqueda de texto.
        sa.Index("ix_gp_inc_busqueda", "busqueda", postgresql_using="gin"),

        {"schema": ESQ},
    )

    id = sa.Column(sa.BigInteger, primary_key=True)

    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")),
                            nullable=False)
    # El consecutivo dentro del proyecto. Junto con la clave del proyecto forma
    # la clave visible (ERP-123), que se arma al mostrar y no se guarda: guardarla
    # obligaría a reescribir todas las incidencias si un proyecto se renombra.
    numero = sa.Column(sa.BigInteger, nullable=False)

    tipo_id      = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_tipo_incidencia.id")),
                             nullable=False)
    estado_id    = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_estado.id")),
                             nullable=False)
    prioridad_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_prioridad.id")))

    # El título de trabajo. Se reescribe tantas veces como haga falta y cada
    # reescritura queda en `gp_historial`.
    resumen     = sa.Column(sa.String(300), nullable=False)
    descripcion = sa.Column(sa.Text)

    reporta  = sa.Column(sa.String(80), index=True)
    asignado = sa.Column(sa.String(80))

    # Jerarquía. Una sola columna: qué puede colgar de qué lo decide el nivel del
    # tipo, no una tabla de parentesco aparte.
    padre_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_incidencia.id")))

    sprint_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_sprint.id")))
    # Estimación en puntos. Vacío = sin estimar, que no es lo mismo que cero: sin
    # estimar no puede entrar a un sprint con compromiso.
    puntos    = sa.Column(sa.Integer)
    # Posición en el backlog. Float para poder insertar entre dos sin reordenar
    # la lista entera en cada arrastre.
    orden     = sa.Column(sa.Float, default=0, nullable=False)

    etiquetas = sa.Column(JSONB, default=list, nullable=False)

    # Todo lo configurable. La forma es {clave_del_campo: valor}.
    campos = sa.Column(JSONB, default=dict, nullable=False)

    # Cuándo se PLANEA empezarla. Junto con `vence` forma la barra del Gantt.
    # Es distinto de `iniciado`, que es cuándo empezó de verdad: comparar los dos
    # es justamente lo que dice si el plan se está cumpliendo, y con una sola
    # columna esa comparación no existe.
    inicio_plan = sa.Column(sa.DateTime(timezone=True))
    vence    = sa.Column(sa.DateTime(timezone=True))
    # Cuándo empezó a trabajarse de verdad. Con esto y `resuelto` sale el tiempo
    # de ciclo, que es lo que el equipo puede mejorar; medir desde que se creó
    # incluye la espera en el backlog, que depende de otra cosa.
    iniciado = sa.Column(sa.DateTime(timezone=True))
    resuelto = sa.Column(sa.DateTime(timezone=True))

    # Se toca con cada cambio. Es por lo que se ordena y por donde pagina el
    # cursor, así que lleva su propio índice compuesto arriba.
    actualizado = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(),
                            nullable=False)

    # De qué solicitud de soporte nació, si nació de una. Vacío en el trabajo
    # interno —una mejora que nadie pidió, deuda técnica—, que es precisamente el
    # caso por el que ticket e incidencia son dos tablas y no una.
    ticket_id = sa.Column(sa.Integer, index=True)

    # Se calcula en la base y no en la aplicación: así no hay forma de que una
    # ruta que actualice el texto olvide refrescar el índice de búsqueda.
    # 'spanish' va literal porque `to_tsvector` solo es inmutable —y por tanto
    # utilizable en una columna generada— cuando la configuración es constante.
    busqueda = sa.Column(
        TSVECTOR,
        sa.Computed(
            "to_tsvector('spanish', "
            "coalesce(resumen, '') || ' ' || coalesce(descripcion, ''))",
            persisted=True,
        ),
    )


class GPSprint(Base, TimestampMixin):
    """Una iteración de un proyecto."""

    __tablename__ = "gp_sprint"
    __table_args__ = (
        sa.Index("ix_gp_sprint_proyecto", "proyecto_id", "estado"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    # Por proyecto y no global: con muchos proyectos, un sprint único obligaría a
    # todos los equipos a moverse al mismo ritmo.
    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")),
                            nullable=False)

    nombre   = sa.Column(sa.String(120), nullable=False)
    # Para qué es esta iteración. Un sprint sin objetivo es una lista de tareas.
    objetivo = sa.Column(sa.Text)
    inicio   = sa.Column(sa.Date)
    fin      = sa.Column(sa.Date)
    estado   = sa.Column(sa.String(20), default="PLANEADO", nullable=False)

    # Se congelan al cerrar: la velocidad histórica no puede cambiar porque
    # después alguien reestime algo viejo.
    puntos_comprometidos = sa.Column(sa.Integer)
    puntos_completados   = sa.Column(sa.Integer)
    cerrado_en           = sa.Column(sa.DateTime(timezone=True))


class GPComentario(Base, TimestampMixin):
    """Una intervención en la discusión de una incidencia."""

    __tablename__ = "gp_comentario"
    __table_args__ = (
        sa.Index("ix_gp_comentario_inc", "incidencia_id", "id"),
        {"schema": ESQ},
    )

    id            = sa.Column(sa.BigInteger, primary_key=True)
    incidencia_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_incidencia.id")),
                              nullable=False)

    autor  = sa.Column(sa.String(80), nullable=False)
    cuerpo = sa.Column(sa.Text, nullable=False)

    # A quién se nombró. Se guarda resuelto y no se vuelve a analizar el texto:
    # así una edición posterior no dispara notificaciones repetidas.
    menciones = sa.Column(JSONB, default=list, nullable=False)

    # Solo lo ve el equipo. Existe por lo mismo que la nota interna de soporte:
    # sin ella, coordinar entre dos personas obliga a salirse de la herramienta.
    interno = sa.Column(sa.Boolean, default=False, nullable=False)
    editado = sa.Column(sa.Boolean, default=False, nullable=False)


class GPAdjunto(Base):
    """Un archivo de una incidencia.

    Se guarda la ruta, no el contenido: la base no es lugar para binarios. La
    descarga pasa por un endpoint que comprueba permisos y no por una carpeta
    pública — un pantallazo puede traer datos de otra empresa.
    """

    __tablename__ = "gp_adjunto"
    __table_args__ = (
        sa.Index("ix_gp_adjunto_inc", "incidencia_id"),
        {"schema": ESQ},
    )

    id            = sa.Column(sa.BigInteger, primary_key=True)
    incidencia_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_incidencia.id")),
                              nullable=False)
    comentario_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_comentario.id")))

    nombre    = sa.Column(sa.String(255), nullable=False)
    tipo_mime = sa.Column(sa.String(120))
    tamano    = sa.Column(sa.BigInteger)
    ruta      = sa.Column(sa.String(400), nullable=False)

    subido_por = sa.Column(sa.String(80))
    creado     = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(),
                           nullable=False)


class GPTiempoTrabajo(Base):
    """Un tramo de tiempo trabajado sobre una incidencia.

    POR QUÉ TRAMOS Y NO UN CONTADOR
    Un solo número «minutos trabajados» no sabe responder quién los trabajó ni
    cuándo, y no se puede corregir sin borrar lo demás. Con tramos, el total es
    una suma y cada tramo conserva su autor y sus horas: eso es lo que permite
    facturar, medir y, sobre todo, revisar.

    POR QUÉ EL RELOJ VIVE EN EL SERVIDOR
    `fin` en blanco significa «corriendo». El tiempo se calcula al cerrar, contra
    el reloj del servidor. Si lo llevara el navegador, cerrar la pestaña perdería
    el tramo y dos personas en husos distintos reportarían horas incompatibles.

    `motivo` distingue una pausa de un cierre. Las dos detienen el reloj; lo que
    cambia es la intención, y esa intención es la que después explica un tramo de
    diez minutos entre dos jornadas.
    """

    __tablename__ = "gp_tiempo"
    __table_args__ = {"schema": ESQ}

    id            = sa.Column(sa.BigInteger, primary_key=True)
    incidencia_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_incidencia.id"),
                                                           ondelete="CASCADE"),
                              nullable=False, index=True)
    usuario   = sa.Column(sa.String(80), nullable=False, index=True)
    inicio    = sa.Column(sa.DateTime(timezone=True), nullable=False,
                          server_default=sa.func.now())
    fin       = sa.Column(sa.DateTime(timezone=True))
    segundos  = sa.Column(sa.Integer, nullable=False, server_default="0")
    # PAUSA o FIN. En blanco mientras el tramo sigue corriendo.
    motivo    = sa.Column(sa.String(10))
    nota      = sa.Column(sa.String(300))


class GPVinculo(Base):
    """Una relación entre dos incidencias.

    Se guarda una sola vez y se lee en los dos sentidos: guardar las dos mitades
    obliga a mantenerlas sincronizadas y tarde o temprano quedan contradiciéndose
    —A bloquea a B, pero B no está bloqueada por A—.
    """

    __tablename__ = "gp_vinculo"
    __table_args__ = (
        sa.UniqueConstraint("origen_id", "destino_id", "tipo", name="uq_gp_vinculo"),
        sa.Index("ix_gp_vinculo_destino", "destino_id"),
        {"schema": ESQ},
    )

    id         = sa.Column(sa.BigInteger, primary_key=True)
    origen_id  = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_incidencia.id")),
                           nullable=False)
    destino_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_incidencia.id")),
                           nullable=False)
    tipo       = sa.Column(sa.String(20), nullable=False)

    autor  = sa.Column(sa.String(80))
    creado = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(),
                       nullable=False)


class GPHistorial(Base):
    """Cada cambio de campo, con quién y cuándo.

    Existe por dos razones que van juntas: explica por qué algo terminó donde
    terminó —incluido cómo una queja vaga se fue convirtiendo en un requerimiento
    concreto, que es lo que hace falta el día que haya una discusión con un
    cliente— y es de donde salen las métricas. Un burndown calculado sobre el
    estado de hoy mentiría: mostraría el pasado como si siempre hubiera sido así.

    Es la tabla que crece de verdad —una veintena de filas por incidencia—, así
    que va particionada por año. La partición la crea `main.py` antes de que
    `create_all` la vea; acá solo se declara su forma. La llave primaria incluye
    `creado` porque PostgreSQL exige que la clave de partición esté en todo
    índice único.
    """

    __tablename__ = "gp_historial"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", "creado", name="pk_gp_historial"),
        sa.Index("ix_gp_hist_inc", "incidencia_id", "creado"),
        sa.Index("ix_gp_hist_fecha", "creado"),
        {"schema": ESQ, "postgresql_partition_by": "RANGE (creado)"},
    )

    # BIGSERIAL explícito: con la llave primaria compuesta, SQLAlchemy no
    # supondría que esta columna se autoincrementa.
    id = sa.Column(sa.BigInteger, sa.Identity(), nullable=False)

    # Sin llave foránea, a diferencia del resto del módulo: una referencia desde
    # una tabla particionada obliga a PostgreSQL a comprobarla partición por
    # partición, y este es el camino caliente —cada cambio de cada incidencia
    # escribe acá—. La integridad la garantiza que solo el servicio escribe esta
    # tabla, y borrar una incidencia arrastra su historial explícitamente.
    incidencia_id = sa.Column(sa.BigInteger, nullable=False)

    campo    = sa.Column(sa.String(60), nullable=False)
    # Se guardan como texto y no con el tipo original: es un registro para leer y
    # para contar transiciones, no para volver a cargar. Recortados, porque una
    # descripción de veinte mil caracteres no aporta nada al historial.
    anterior = sa.Column(sa.String(500))
    nuevo    = sa.Column(sa.String(500))

    autor  = sa.Column(sa.String(80))
    creado = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(),
                       nullable=False)


class GPFiltro(Base, TimestampMixin):
    """Un filtro guardado.

    Se guarda el texto del filtro, no el SQL: el SQL se genera cada vez a partir
    del árbol validado. Guardar SQL sería aceptar consultas escritas por el
    usuario, que es exactamente lo que el motor existe para evitar.
    """

    __tablename__ = "gp_filtro"
    __table_args__ = (
        sa.Index("ix_gp_filtro_autor", "autor"),
        {"schema": ESQ},
    )

    id     = sa.Column(sa.BigInteger, primary_key=True)
    nombre = sa.Column(sa.String(160), nullable=False)
    descripcion = sa.Column(sa.Text)

    expresion = sa.Column(sa.Text, nullable=False)
    # Qué columnas mostrar y por cuál ordenar, para que la lista se reabra igual.
    columnas  = sa.Column(JSONB, default=list, nullable=False)
    orden_por = sa.Column(sa.String(120))
    orden_asc = sa.Column(sa.Boolean, default=False, nullable=False)

    autor      = sa.Column(sa.String(80), nullable=False)
    compartido = sa.Column(sa.Boolean, default=False, nullable=False)


# ─── Pizarras ─────────────────────────────────────────────────────────────────
#
# Un tablero de indicadores armado por quien lo usa. Cada recuadro se apoya en el
# MISMO lenguaje de filtros que la lista: así lo que se ve en una pizarra siempre
# se puede abrir como lista y revisar fila por fila. Un panel cuyo número no se
# puede desglosar es un número en el que nadie confía.

class GPPizarra(Base, TimestampMixin):
    """Un tablero de indicadores."""

    __tablename__ = "gp_pizarra"
    __table_args__ = (
        sa.Index("ix_gp_pizarra_autor", "autor"),
        {"schema": ESQ},
    )

    id          = sa.Column(sa.BigInteger, primary_key=True)
    nombre      = sa.Column(sa.String(160), nullable=False)
    descripcion = sa.Column(sa.Text)
    # Vacío = de toda la organización. Con proyecto, sus recuadros lo dan por
    # supuesto y no hay que repetirlo en cada filtro.
    proyecto_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_proyecto.id")))

    autor      = sa.Column(sa.String(80), nullable=False)
    compartida = sa.Column(sa.Boolean, default=True, nullable=False)


class GPWidget(Base):
    """Un recuadro de una pizarra.

    La posición se guarda en la fila y no en un JSON de la pizarra: así mover un
    recuadro escribe una fila y no reescribe el tablero entero, y dos personas
    reacomodando a la vez no se pisan.
    """

    __tablename__ = "gp_widget"
    __table_args__ = (
        sa.Index("ix_gp_widget_pizarra", "pizarra_id", "orden"),
        {"schema": ESQ},
    )

    id         = sa.Column(sa.BigInteger, primary_key=True)
    pizarra_id = sa.Column(sa.BigInteger, sa.ForeignKey(_fk("gp_pizarra.id")),
                           nullable=False)

    # CONTADOR · LISTA · AGRUPADO · VELOCIDAD · BURNDOWN · CARGA
    tipo   = sa.Column(sa.String(30), nullable=False)
    titulo = sa.Column(sa.String(160), nullable=False)

    # El filtro que alimenta el recuadro, en el lenguaje de consultas. Se guarda
    # el texto y nunca SQL: el SQL se regenera desde el árbol validado en cada
    # consulta, así que una pizarra vieja no se salta una comprobación nueva.
    expresion = sa.Column(sa.Text, default="", nullable=False)
    # Por qué campo agrupar, para los recuadros de tipo AGRUPADO.
    agrupar_por = sa.Column(sa.String(60))

    # Cómo se dibuja: colores, si va como barras o como anillo, cuántas filas.
    config = sa.Column(JSONB, default=dict, nullable=False)

    # Rejilla de 12 columnas, como la del resto de la consola.
    x     = sa.Column(sa.Integer, default=0, nullable=False)
    y     = sa.Column(sa.Integer, default=0, nullable=False)
    ancho = sa.Column(sa.Integer, default=4, nullable=False)
    alto  = sa.Column(sa.Integer, default=1, nullable=False)
    orden = sa.Column(sa.Integer, default=0, nullable=False)
