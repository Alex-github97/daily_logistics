"""
Lubricación — modelo de datos.

Va en archivo aparte y no dentro de `eam.py` porque ese archivo ya pasa de
1.300 líneas; pero **no es un módulo independiente**: cada compartimento cuelga
de `eam_activo`, los diagnósticos abren órdenes en `eam_orden_trabajo` y los
análisis alimentan el mismo tablero de mantenimiento. Es una capa más del CMMS.

LA DECISIÓN QUE ORDENA TODO EL MODELO
En llantas la entidad rastreada es el neumático: tiene identidad, ocupa una
posición, se inspecciona, se mide su desgaste, cuesta por kilómetro y muere por
una causa codificada. El equivalente en lubricación **no es el punto de
engrase**: es la **carga de aceite**. Un llenado concreto, en un compartimento
concreto, que vive unas horas, se muestrea, se rellena y se drena por un motivo.

    llantas                        lubricación
    ─────────────────────────      ──────────────────────────────
    neumático (serie)              carga de aceite
    posición en el vehículo        compartimento del activo
    vida (nueva/reencauchada)      vida de la carga + rellenos
    inspección (mm, psi)           muestra (espectrometría, ISO 4406…)
    mm por cada 1.000 km           ppm por cada 100 horas
    costo por kilómetro            costo por hora lubricada
    motivo de fin de vida          motivo de drenaje

Si la entidad principal fuera el punto de lubricación, esto sería un calendario
de engrase. Con la carga como entidad se puede responder «cuántas horas rindió,
cuánto costó la hora y por qué se drenó», que es lo que hace rentable el
programa.

POR QUÉ LOS RESULTADOS VAN EN FILAS Y NO EN COLUMNAS
La tabla anterior (`eam_muestra_aceite`) tenía doce columnas fijas —hierro,
cobre, aluminio…— mientras el lector de boletines que ya existe reconoce más de
treinta parámetros. Todo lo demás se extraía y se botaba. Acá cada resultado es
una fila (`eam_lube_resultado`), así que agregar TAN, PQ o un conteo de
partículas es cargar un dato en el catálogo, no migrar la base.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Text,
    ForeignKey, UniqueConstraint, Index,
)
from app.infrastructure.models.base import Base, TimestampMixin


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGOS — la configuración previa, con la misma jerarquía que llantas
# ══════════════════════════════════════════════════════════════════════════════

class LubeMarca(Base, TimestampMixin):
    """Marca de lubricante (Shell, Mobil, Chevron). Nivel 1 de la jerarquía."""
    __tablename__ = "eam_lube_marca"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_lube_marca_nombre"),)
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)


class LubeTipoCompartimento(Base, TimestampMixin):
    """Familia de compartimento: motor diésel, hidráulico, transmisión, mando
    final, compresor…

    Es el eje que gobierna los límites de alarma. Cincuenta ppm de hierro no
    significan nada en un motor diésel y son alarma en una caja de engranajes:
    sin esta clasificación, cualquier límite es un promedio inútil.
    """
    __tablename__ = "eam_lube_tipo_compartimento"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_lube_tipo_comp_nombre"),)
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(40), nullable=True)
    nombre      = Column(String(120), nullable=False)
    descripcion = Column(String(300), nullable=True)
    # Con qué se mide la vida del aceite en esta familia.
    unidad_vida = Column(String(10), default="HORAS", nullable=False)  # HORAS|KM|DIAS
    activo      = Column(Boolean, default=True, nullable=False)


class LubeProducto(Base, TimestampMixin):
    """Producto concreto de una marca (Rimula R4X 15W-40). Nivel 2.

    Espeja `eam_referencia_neumatico`: la referencia pertenece a una marca.
    """
    __tablename__ = "eam_lube_producto"
    __table_args__ = (UniqueConstraint("marca_id", "nombre", name="uq_eam_lube_producto"),)
    id        = Column(Integer, primary_key=True, index=True)
    marca_id  = Column(Integer, ForeignKey("eam_lube_marca.id", ondelete="CASCADE"), nullable=False)
    nombre    = Column(String(150), nullable=False)
    # MOTOR | HIDRAULICO | ENGRANAJES | TRANSMISION | GRASA | REFRIGERANTE | OTRO
    familia   = Column(String(30), nullable=True)
    grado_sae = Column(String(30), nullable=True)   # 15W-40
    grado_iso = Column(String(30), nullable=True)   # ISO VG 46
    # Sintético, mineral, semisintético.
    base      = Column(String(30), nullable=True)
    activo    = Column(Boolean, default=True, nullable=False)


class LubeAplicacion(Base, TimestampMixin):
    """El cruce producto × tipo de compartimento, con los parámetros técnicos.

    Mismo patrón que `eam_referencia_dimension`, y por la misma razón: el dato
    no pertenece ni al producto ni al compartimento por separado. El mismo
    aceite dura 500 horas en un motor y 4.000 en un sistema hidráulico, y su
    meta de limpieza es mucho más exigente en el hidráulico. Poner la vida
    recomendada en el producto obligaría a inventar un producto por aplicación.
    """
    __tablename__ = "eam_lube_aplicacion"
    __table_args__ = (
        UniqueConstraint("producto_id", "tipo_compartimento_id", name="uq_eam_lube_aplicacion"),
    )
    id                    = Column(Integer, primary_key=True, index=True)
    producto_id           = Column(Integer, ForeignKey("eam_lube_producto.id", ondelete="CASCADE"), nullable=False)
    tipo_compartimento_id = Column(Integer, ForeignKey("eam_lube_tipo_compartimento.id", ondelete="CASCADE"), nullable=False)
    # Vida recomendada, en la unidad que declara el tipo de compartimento.
    vida_recomendada      = Column(Float, nullable=True)
    vida_maxima           = Column(Float, nullable=True)
    # Meta de limpieza ISO 4406, guardada como texto ("18/16/13") porque son
    # tres números que solo tienen sentido juntos.
    meta_iso4406          = Column(String(20), nullable=True)
    volumen_tipico        = Column(Float, nullable=True)   # litros
    costo_litro           = Column(Float, nullable=True)
    observaciones         = Column(Text, nullable=True)
    activo                = Column(Boolean, default=True, nullable=False)


class LubeParametro(Base, TimestampMixin):
    """Catálogo de parámetros de análisis: Fe, Cu, viscosidad, TBN, ISO 4406…

    Es lo que convierte los resultados en filas. El lector de boletines ya
    reconoce estos códigos; acá se les da unidad, grupo y orden de presentación.
    """
    __tablename__ = "eam_lube_parametro"
    __table_args__ = (UniqueConstraint("codigo", name="uq_eam_lube_parametro_codigo"),)
    id     = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(30), nullable=False)     # fe, cu, viscosidad, iso4406
    nombre = Column(String(120), nullable=False)
    unidad = Column(String(20), nullable=True)      # ppm, cSt, mgKOH/g
    # DESGASTE | CONTAMINACION | ADITIVO | PROPIEDAD — agrupa la lectura del
    # boletín y permite diagnosticar por familia y no parámetro por parámetro.
    grupo  = Column(String(20), default="PROPIEDAD", nullable=False)
    # Qué origen delata el elemento: "camisas y anillos", "bronces", "polvo".
    # Es lo que traduce un número a una causa probable.
    origen_probable = Column(String(200), nullable=True)
    # Los códigos ISO no son números: no se promedian ni se grafican igual.
    es_texto = Column(Boolean, default=False, nullable=False)
    # Para la viscosidad, alejarse en cualquier dirección es malo.
    bidireccional = Column(Boolean, default=False, nullable=False)
    orden  = Column(Integer, default=0)
    activo = Column(Boolean, default=True, nullable=False)


class LubeLimite(Base, TimestampMixin):
    """Límites de alarma. El corazón analítico del módulo.

    Tres naturalezas distintas, y las tres hacen falta:

    ABSOLUTO      el valor que el fabricante o el laboratorio declara tope.
    ESTADISTICO   media + 2σ de la propia flota; solo sirve con historia, pero
                  es el que se ajusta a cómo opera *esta* empresa.
    TASA_CAMBIO   cuánto sube el parámetro por cada 100 horas de aceite. Es el
                  que casi nadie implementa y el que detecta la falla antes: un
                  hierro que pasa de 12 a 34 ppm en 80 horas es una alarma
                  aunque 34 esté cómodamente «dentro de límite».

    El ámbito va de lo general a lo particular: un límite por tipo de
    compartimento cubre toda la flota, y uno por compartimento concreto manda
    sobre el anterior para el equipo que se sale de la norma.
    """
    __tablename__ = "eam_lube_limite"
    __table_args__ = (
        Index("ix_eam_lube_limite_busqueda", "tipo_compartimento_id", "parametro_id", "tipo"),
    )
    id                    = Column(Integer, primary_key=True, index=True)
    parametro_id          = Column(Integer, ForeignKey("eam_lube_parametro.id", ondelete="CASCADE"), nullable=False)
    tipo_compartimento_id = Column(Integer, ForeignKey("eam_lube_tipo_compartimento.id", ondelete="CASCADE"), nullable=True)
    # Afinamientos opcionales: por producto, o para un compartimento concreto.
    producto_id           = Column(Integer, ForeignKey("eam_lube_producto.id", ondelete="CASCADE"), nullable=True)
    compartimento_id      = Column(Integer, ForeignKey("eam_lube_compartimento.id", ondelete="CASCADE"), nullable=True)

    tipo   = Column(String(20), default="ABSOLUTO", nullable=False)  # ABSOLUTO|ESTADISTICO|TASA_CAMBIO
    # Umbrales. En parámetros bidireccionales (viscosidad) se usan los cuatro.
    marginal_min = Column(Float, nullable=True)
    marginal_max = Column(Float, nullable=True)
    critico_min  = Column(Float, nullable=True)
    critico_max  = Column(Float, nullable=True)
    # OEM | LABORATORIO | FLOTA | NORMA — de dónde salió el número. Importa para
    # poder defenderlo en una auditoría.
    fuente = Column(String(20), default="OEM", nullable=True)
    nota   = Column(String(300), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)


class LubeLaboratorio(Base, TimestampMixin):
    """Laboratorio que procesa las muestras."""
    __tablename__ = "eam_lube_laboratorio"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_lube_lab_nombre"),)
    id        = Column(Integer, primary_key=True, index=True)
    nombre    = Column(String(150), nullable=False)
    contacto  = Column(String(150), nullable=True)
    telefono  = Column(String(50), nullable=True)
    correo    = Column(String(150), nullable=True)
    # Días que suele tardar el resultado: sirve para saber si una muestra está
    # demorada o perdida.
    dias_respuesta = Column(Integer, nullable=True)
    activo    = Column(Boolean, default=True, nullable=False)


class LubeMetodoMuestreo(Base, TimestampMixin):
    """Cómo se tomó la muestra, con su calidad asociada.

    No es un adorno: una muestra tomada por el tapón de drenaje arrastra el
    sedimento del fondo y da lecturas altas que no representan al aceite en
    circulación. Sin registrar el método, un histórico mezcla peras con
    manzanas y las tendencias no significan nada.
    """
    __tablename__ = "eam_lube_metodo_muestreo"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_lube_metodo_nombre"),)
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(120), nullable=False)
    # RECOMENDADO | ACEPTABLE | NO_RECOMENDADO
    calidad     = Column(String(20), default="ACEPTABLE", nullable=False)
    descripcion = Column(String(300), nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)


class LubeMotivoDrenaje(Base, TimestampMixin):
    """Por qué se sacó la carga. Espeja `eam_motivo_fin_vida` de llantas.

    Es el dato que permite la pregunta que paga el programa: ¿cuántas cargas se
    drenaron por calendario estando el aceite todavía bueno?
    """
    __tablename__ = "eam_lube_motivo_drenaje"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_lube_motivo_nombre"),)
    id     = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(40), nullable=True)
    nombre = Column(String(150), nullable=False)
    # CALENDARIO | CONDICION | FALLA | CONTAMINACION | INTERVENCION
    categoria   = Column(String(30), default="CALENDARIO", nullable=False)
    # Si el drenaje era evitable, cuenta como oportunidad perdida en el tablero.
    evitable    = Column(Boolean, default=False, nullable=False)
    descripcion = Column(String(300), nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)


class LubeModoFalla(Base, TimestampMixin):
    """Catálogo de modos de falla del lubricante. Espeja el catálogo de daños de
    llantas: es lo que permite agrupar «por qué falla» en el tablero."""
    __tablename__ = "eam_lube_modo_falla"
    __table_args__ = (UniqueConstraint("codigo", name="uq_eam_lube_modo_falla_codigo"),)
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(40), nullable=False)
    nombre      = Column(String(150), nullable=False)
    # DESGASTE | CONTAMINACION | DEGRADACION | DILUCION | REFRIGERANTE | ADITIVOS
    categoria   = Column(String(30), default="DESGASTE", nullable=False)
    severidad   = Column(String(20), default="MODERADO", nullable=False)
    descripcion = Column(String(400), nullable=True)
    accion_sugerida = Column(String(300), nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# NÚCLEO OPERATIVO — el ciclo de vida
# ══════════════════════════════════════════════════════════════════════════════

class LubeCompartimento(Base, TimestampMixin):
    """El punto lubricado de un activo: el motor de la VH-001, el hidráulico del
    montacargas. Es la «posición» del módulo de llantas.

    Cuelga de `eam_activo` —y opcionalmente del `eam_componente` que ya existe—
    para que el análisis herede la jerarquía del CMMS: tipo de activo, marca y
    línea. Sin eso no se podría responder «qué le falla a esta flota», que es
    justo lo que el tablero de mantenimiento ya hace con las causas raíz.
    """
    __tablename__ = "eam_lube_compartimento"
    __table_args__ = (
        UniqueConstraint("activo_id", "codigo", name="uq_eam_lube_comp_activo_codigo"),
    )
    id            = Column(Integer, primary_key=True, index=True)
    activo_id     = Column(Integer, ForeignKey("eam_activo.id", ondelete="CASCADE"), nullable=False, index=True)
    componente_id = Column(Integer, ForeignKey("eam_componente.id"), nullable=True)
    tipo_compartimento_id = Column(Integer, ForeignKey("eam_lube_tipo_compartimento.id"), nullable=False)

    codigo = Column(String(40), nullable=False)     # MOT, HID, DIF-POST
    nombre = Column(String(150), nullable=False)
    capacidad_litros = Column(Float, nullable=True)

    # Lo que *debería* llevar. La carga real puede diferir, y esa diferencia es
    # un hallazgo: producto equivocado en el compartimento.
    producto_recomendado_id = Column(Integer, ForeignKey("eam_lube_producto.id"), nullable=True)
    meta_iso4406 = Column(String(20), nullable=True)

    # Cada cuánto se muestrea y con qué método. La adherencia al muestreo se
    # mide contra esto.
    frecuencia_muestreo = Column(Float, nullable=True)   # en la unidad del tipo
    metodo_muestreo_id  = Column(Integer, ForeignKey("eam_lube_metodo_muestreo.id"), nullable=True)
    # Un compartimento sin puerto de muestreo condena la calidad del dato; se
    # registra para poder priorizar la adecuación de los equipos.
    tiene_puerto_muestreo = Column(Boolean, default=False, nullable=False)

    critico = Column(Boolean, default=False, nullable=False)
    activo  = Column(Boolean, default=True, nullable=False)
    observaciones = Column(Text, nullable=True)


class LubeCarga(Base, TimestampMixin):
    """Una carga de aceite: el llenado concreto que vive en un compartimento.

    Es la entidad equivalente al neumático. Tiene fecha de nacimiento, acumula
    horas, recibe rellenos, se muestrea y muere por un motivo. Solo puede haber
    una carga ACTIVA por compartimento a la vez; abrir una nueva cierra la
    anterior.
    """
    __tablename__ = "eam_lube_carga"
    __table_args__ = (
        Index("ix_eam_lube_carga_comp_estado", "compartimento_id", "estado"),
    )
    id               = Column(Integer, primary_key=True, index=True)
    compartimento_id = Column(Integer, ForeignKey("eam_lube_compartimento.id", ondelete="CASCADE"), nullable=False)
    producto_id      = Column(Integer, ForeignKey("eam_lube_producto.id"), nullable=True)

    fecha_llenado = Column(DateTime, nullable=False)
    # Lectura del equipo al llenar. La vida del aceite se calcula contra esto,
    # no contra la fecha: un equipo parado no envejece su aceite igual.
    medidor_inicio = Column(Float, nullable=True)
    volumen_litros = Column(Float, nullable=True)
    costo_aceite   = Column(Float, nullable=True)
    costo_filtro   = Column(Float, nullable=True)
    costo_mano_obra = Column(Float, nullable=True)

    estado = Column(String(20), default="ACTIVA", nullable=False)   # ACTIVA | DRENADA

    fecha_drenaje    = Column(DateTime, nullable=True)
    medidor_fin      = Column(Float, nullable=True)
    motivo_drenaje_id = Column(Integer, ForeignKey("eam_lube_motivo_drenaje.id"), nullable=True)
    # Vida lograda, en la unidad del tipo de compartimento. Se guarda calculada
    # al cerrar para no tener que recomputarla en cada informe.
    vida_lograda     = Column(Float, nullable=True)

    orden_trabajo_id = Column(Integer, ForeignKey("eam_orden_trabajo.id"), nullable=True)
    observaciones    = Column(Text, nullable=True)
    registrado_por   = Column(String(100), nullable=True)


class LubeRelleno(Base, TimestampMixin):
    """Reposición de aceite sobre una carga viva.

    Importa por dos razones: el consumo alto delata una fuga o un desgaste, y
    el aceite nuevo «rejuvenece» la carga —diluye los metales—, así que una
    tendencia que ignore los rellenos lee mejoras que no existen.
    """
    __tablename__ = "eam_lube_relleno"
    id       = Column(Integer, primary_key=True, index=True)
    carga_id = Column(Integer, ForeignKey("eam_lube_carga.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha    = Column(DateTime, nullable=False)
    litros   = Column(Float, nullable=False)
    medidor  = Column(Float, nullable=True)
    costo    = Column(Float, nullable=True)
    motivo   = Column(String(200), nullable=True)
    registrado_por = Column(String(100), nullable=True)


class LubeMuestra(Base, TimestampMixin):
    """Una muestra de aceite. Es la «inspección» del módulo de llantas.

    `horas_aceite` no es opcional en la práctica: 30 ppm de hierro a las 500
    horas y a las 50 horas son diagnósticos opuestos. Sin ese dato la muestra
    es un número suelto y no una medición.
    """
    __tablename__ = "eam_lube_muestra"
    __table_args__ = (
        UniqueConstraint("numero", name="uq_eam_lube_muestra_numero"),
        Index("ix_eam_lube_muestra_carga_fecha", "carga_id", "fecha_toma"),
    )
    id       = Column(Integer, primary_key=True, index=True)
    numero   = Column(String(60), nullable=False)
    carga_id = Column(Integer, ForeignKey("eam_lube_carga.id", ondelete="CASCADE"), nullable=True, index=True)
    # Se guarda también el compartimento: una muestra puede llegar antes de que
    # se haya registrado la carga, y perderla por eso sería absurdo.
    compartimento_id = Column(Integer, ForeignKey("eam_lube_compartimento.id"), nullable=False, index=True)

    fecha_toma     = Column(DateTime, nullable=False)
    fecha_recepcion = Column(DateTime, nullable=True)
    fecha_resultado = Column(DateTime, nullable=True)

    medidor_equipo = Column(Float, nullable=True)   # lectura del equipo
    horas_aceite   = Column(Float, nullable=True)   # vida de la carga al momento
    laboratorio_id = Column(Integer, ForeignKey("eam_lube_laboratorio.id"), nullable=True)
    metodo_id      = Column(Integer, ForeignKey("eam_lube_metodo_muestreo.id"), nullable=True)

    # NORMAL | MARGINAL | CRITICO | ACCION_INMEDIATA — lo calcula el evaluador
    # contra los límites, y un analista puede sobreescribirlo.
    severidad      = Column(String(20), default="PENDIENTE", nullable=False)
    severidad_manual = Column(Boolean, default=False, nullable=False)

    estado = Column(String(20), default="TOMADA", nullable=False)  # TOMADA|ENVIADA|CON_RESULTADO|ANULADA
    archivo_boletin = Column(String(400), nullable=True)
    observaciones   = Column(Text, nullable=True)
    registrado_por  = Column(String(100), nullable=True)


class LubeResultado(Base, TimestampMixin):
    """Un valor medido de una muestra. Una fila por parámetro.

    Éste es el cambio estructural frente al modelo anterior de doce columnas
    fijas: agregar un parámetro nuevo es cargar una fila en el catálogo, no
    migrar la base ni tocar el código.
    """
    __tablename__ = "eam_lube_resultado"
    __table_args__ = (
        UniqueConstraint("muestra_id", "parametro_id", name="uq_eam_lube_resultado"),
    )
    id           = Column(Integer, primary_key=True, index=True)
    muestra_id   = Column(Integer, ForeignKey("eam_lube_muestra.id", ondelete="CASCADE"), nullable=False, index=True)
    parametro_id = Column(Integer, ForeignKey("eam_lube_parametro.id"), nullable=False)
    valor        = Column(Float, nullable=True)
    # Los códigos ISO 4406 y las lecturas cualitativas no son números.
    valor_texto  = Column(String(60), nullable=True)

    # Resultado de la evaluación, guardado para no reevaluar en cada consulta.
    estado       = Column(String(20), default="NORMAL", nullable=False)  # NORMAL|MARGINAL|CRITICO
    # Variación por cada 100 unidades de vida respecto de la muestra anterior:
    # es la señal temprana.
    tasa_cambio  = Column(Float, nullable=True)
    disparo_por  = Column(String(20), nullable=True)  # ABSOLUTO|ESTADISTICO|TASA_CAMBIO


class LubeDiagnostico(Base, TimestampMixin):
    """El cierre del ciclo: qué se concluyó, qué se hizo y si se acertó.

    Sin la confirmación posterior el programa nunca aprende. Es la misma idea
    del análisis de causa raíz que ya existe en las órdenes, y se conecta con
    él: si el diagnóstico se confirma en una intervención, ese hallazgo alimenta
    el tablero de mantenimiento.
    """
    __tablename__ = "eam_lube_diagnostico"
    id         = Column(Integer, primary_key=True, index=True)
    muestra_id = Column(Integer, ForeignKey("eam_lube_muestra.id", ondelete="CASCADE"), nullable=False, index=True)
    modo_falla_id = Column(Integer, ForeignKey("eam_lube_modo_falla.id"), nullable=True)

    severidad     = Column(String(20), default="NORMAL", nullable=False)
    conclusion    = Column(Text, nullable=True)
    recomendacion = Column(Text, nullable=True)

    # A dónde fue a parar la recomendación.
    orden_trabajo_id = Column(Integer, ForeignKey("eam_orden_trabajo.id"), nullable=True)
    causa_raiz_id    = Column(Integer, ForeignKey("eam_causa_raiz.id"), nullable=True)

    # PENDIENTE | CONFIRMADO | DESMENTIDO — lo que se encontró al intervenir.
    # Es lo que permite medir si el programa acierta.
    verificacion = Column(String(20), default="PENDIENTE", nullable=False)
    hallazgo     = Column(Text, nullable=True)
    fecha_verificacion = Column(Date, nullable=True)

    analista   = Column(String(120), nullable=True)
    automatico = Column(Boolean, default=False, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# El criterio de la empresa por encima del de referencia
# ══════════════════════════════════════════════════════════════════════════════

class LubeAjusteNorma(Base, TimestampMixin):
    """Lo que esta empresa cambió del criterio de interpretación.

    POR QUÉ NO SE SIEMBRAN LOS VALORES Y YA
    Porque entonces no se sabría cuáles son de referencia y cuáles se tocaron.
    El criterio de referencia vive en `core/normas_lubricacion`, en el código,
    versionado y con su fuente; acá viven ÚNICAMENTE las diferencias. Un
    parámetro sin fila usa el valor publicado, y borrar la fila lo devuelve
    exactamente a como estaba.

    Eso permite lo que hace útil a la pantalla: mostrar «0,5 % — ajustado por la
    empresa; la referencia de Tormos es 0,2 %», en vez de un 0,5 % suelto que
    parece norma internacional y no lo es. Un criterio ajustado sigue siendo
    legítimo —el fabricante del motor manda sobre la literatura—, pero tiene que
    verse que es de la casa.

    POR QUÉ `motivo` NO ES OPCIONAL
    Un límite cambiado sin razón escrita es indistinguible de un error de
    digitación, y seis meses después nadie recuerda si el 0,5 lo puso el
    fabricante o alguien que se equivocó de tecla. La razón es lo que convierte
    el ajuste en una decisión defendible.

    POR QUÉ UNA TABLA Y NO TRES
    Los tres ámbitos —un límite, una constante del motor de cálculo, una regla—
    se editan en la misma pantalla, se listan juntos y se restauran igual. Tres
    tablas darían tres endpoints y tres formularios para lo mismo. El precio es
    que cada fila usa solo las columnas de su ámbito, y por eso todas son
    opcionales.
    """
    __tablename__ = "eam_lube_ajuste_norma"
    __table_args__ = (
        UniqueConstraint("ambito", "clave", name="uq_eam_lube_ajuste_norma"),
    )
    id = Column(Integer, primary_key=True, index=True)

    # LIMITE  un umbral de un parámetro en una familia de compartimento.
    # MOTOR   una constante del motor de cálculo: percentiles, saltos, desvíos.
    # REGLA   una regla de diagnóstico: apagarla, reordenarla o reescribirla.
    ambito = Column(String(20), nullable=False)

    # Qué identifica lo ajustado dentro de su ámbito:
    #   LIMITE → "MOT:agua"            familia de compartimento y parámetro
    #   MOTOR  → "percentil_condena"   nombre de la constante
    #   REGLA  → "AGUA"                código de la regla
    clave = Column(String(80), nullable=False)

    # ── Ámbito LIMITE ────────────────────────────────────────────────────────
    precaucion = Column(Float, nullable=True)
    condena    = Column(Float, nullable=True)

    # ── Ámbito MOTOR ─────────────────────────────────────────────────────────
    valor = Column(Float, nullable=True)

    # ── Ámbito REGLA ─────────────────────────────────────────────────────────
    # Apagar una regla no la borra: la saca de la evaluación y deja constancia
    # de que se apagó y por qué.
    activa    = Column(Boolean, nullable=True)
    severidad = Column(String(20), nullable=True)
    urgencia  = Column(Integer, nullable=True)
    # El orden manda sobre el de referencia: es lo que decide qué regla gana
    # cuando encajan varias.
    orden     = Column(Integer, nullable=True)
    lectura   = Column(Text, nullable=True)
    accion    = Column(Text, nullable=True)

    # ── Trazabilidad del ajuste ──────────────────────────────────────────────
    motivo       = Column(Text, nullable=False)
    ajustado_por = Column(String(120), nullable=True)
