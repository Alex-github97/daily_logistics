from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import relationship
import enum
from app.infrastructure.models.base import Base, TimestampMixin


# ─── Enums ────────────────────────────────────────────────────────────────────

class TipoFabricacionEnum(enum.Enum):
    DISCRETA   = 'DISCRETA'
    PROCESOS   = 'PROCESOS'
    CONTINUA   = 'CONTINUA'
    LOTES      = 'LOTES'
    MAQUILA    = 'MAQUILA'
    REEMPAQUE  = 'REEMPAQUE'
    KITTING    = 'KITTING'

class EstadoOrdenProduccionEnum(enum.Enum):
    PLANEADA      = 'PLANEADA'
    LIBERADA      = 'LIBERADA'
    EN_EJECUCION  = 'EN_EJECUCION'
    SUSPENDIDA    = 'SUSPENDIDA'
    CERRADA       = 'CERRADA'
    CANCELADA     = 'CANCELADA'

class TipoProductoMESEnum(enum.Enum):
    MATERIA_PRIMA     = 'MATERIA_PRIMA'
    SEMIELABORADO     = 'SEMIELABORADO'
    PRODUCTO_TERMINADO = 'PRODUCTO_TERMINADO'
    SUBPRODUCTO       = 'SUBPRODUCTO'
    EMPAQUE           = 'EMPAQUE'
    HERRAMIENTA       = 'HERRAMIENTA'

class TipoBOMEnum(enum.Enum):
    SIMPLE       = 'SIMPLE'
    MULTINIVEL   = 'MULTINIVEL'
    CONFIGURABLE = 'CONFIGURABLE'
    ALTERNATIVA  = 'ALTERNATIVA'

class EstadoLoteMESEnum(enum.Enum):
    ACTIVO    = 'ACTIVO'
    BLOQUEADO = 'BLOQUEADO'
    LIBERADO  = 'LIBERADO'
    CONSUMIDO = 'CONSUMIDO'
    VENCIDO   = 'VENCIDO'
    RECHAZADO = 'RECHAZADO'

class TipoParadaMESEnum(enum.Enum):
    PLANEADA       = 'PLANEADA'
    NO_PLANEADA    = 'NO_PLANEADA'
    CALIDAD        = 'CALIDAD'
    MANTENIMIENTO  = 'MANTENIMIENTO'
    SETUP          = 'SETUP'
    MATERIAL       = 'MATERIAL'

class ResultadoInspeccionMESEnum(enum.Enum):
    APROBADO    = 'APROBADO'
    RECHAZADO   = 'RECHAZADO'
    CONDICIONAL = 'CONDICIONAL'
    PENDIENTE   = 'PENDIENTE'

class TipoScrapMESEnum(enum.Enum):
    NORMAL            = 'NORMAL'
    REPROCESO         = 'REPROCESO'
    DESECHO_PELIGROSO = 'DESECHO_PELIGROSO'
    SUBPRODUCTO       = 'SUBPRODUCTO'

class EstadoEjecucionMESEnum(enum.Enum):
    PENDIENTE   = 'PENDIENTE'
    EN_PROGRESO = 'EN_PROGRESO'
    PAUSADA     = 'PAUSADA'
    COMPLETADA  = 'COMPLETADA'
    CANCELADA   = 'CANCELADA'

class TurnoMESEnum(enum.Enum):
    MANANA   = 'MANANA'
    TARDE    = 'TARDE'
    NOCHE    = 'NOCHE'
    FLEXIBLE = 'FLEXIBLE'

class PrioridadOrdenMESEnum(enum.Enum):
    BAJA    = 'BAJA'
    NORMAL  = 'NORMAL'
    ALTA    = 'ALTA'
    URGENTE = 'URGENTE'
    CRITICA = 'CRITICA'

class TipoInspeccionMESEnum(enum.Enum):
    INICIO_PRODUCCION = 'INICIO_PRODUCCION'
    EN_PROCESO        = 'EN_PROCESO'
    FINAL_LINEA       = 'FINAL_LINEA'
    LIBERACION        = 'LIBERACION'

class TipoMovimientoWIPEnum(enum.Enum):
    ENTRADA      = 'ENTRADA'
    SALIDA       = 'SALIDA'
    TRANSFERENCIA = 'TRANSFERENCIA'
    AJUSTE       = 'AJUSTE'

class NivelAlertaMESEnum(enum.Enum):
    INFO       = 'INFO'
    ADVERTENCIA = 'ADVERTENCIA'
    CRITICA    = 'CRITICA'
    EMERGENCIA = 'EMERGENCIA'


# ─── Models (FK-safe order: parents before children) ─────────────────────────

class MESPlanta(Base, TimestampMixin):
    __tablename__ = 'mes_planta'
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(30), unique=True, nullable=False)
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    ciudad      = Column(String(100), nullable=True)
    pais        = Column(String(100), nullable=True)
    tipo_fabricacion = Column(SAEnum(TipoFabricacionEnum), nullable=False, default=TipoFabricacionEnum.DISCRETA)
    activo      = Column(Boolean, default=True, nullable=False)
    lineas      = relationship('MESLinea', back_populates='planta', lazy='dynamic')


class MESLinea(Base, TimestampMixin):
    __tablename__ = 'mes_linea'
    id          = Column(Integer, primary_key=True, index=True)
    planta_id   = Column(Integer, ForeignKey('mes_planta.id'), nullable=False)
    codigo      = Column(String(30), nullable=False)
    nombre      = Column(String(200), nullable=False)
    capacidad_hora = Column(Float, nullable=True)
    unidad_medida  = Column(String(30), nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)
    planta      = relationship('MESPlanta', back_populates='lineas')
    celdas      = relationship('MESCeldaTrabajo', back_populates='linea', lazy='dynamic')


class MESTurno(Base, TimestampMixin):
    __tablename__ = 'mes_turno'
    id          = Column(Integer, primary_key=True, index=True)
    planta_id   = Column(Integer, ForeignKey('mes_planta.id'), nullable=False)
    nombre      = Column(String(100), nullable=False)
    tipo        = Column(SAEnum(TurnoMESEnum), nullable=False, default=TurnoMESEnum.MANANA)
    hora_inicio = Column(String(8), nullable=False)
    hora_fin    = Column(String(8), nullable=False)
    duracion_horas = Column(Float, nullable=False, default=8.0)
    activo      = Column(Boolean, default=True, nullable=False)


class MESCeldaTrabajo(Base, TimestampMixin):
    __tablename__ = 'mes_celda_trabajo'
    id          = Column(Integer, primary_key=True, index=True)
    linea_id    = Column(Integer, ForeignKey('mes_linea.id'), nullable=False)
    codigo      = Column(String(30), nullable=False)
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)
    linea       = relationship('MESLinea', back_populates='celdas')
    equipos     = relationship('MESEquipo', back_populates='celda', lazy='dynamic')


class MESEquipo(Base, TimestampMixin):
    __tablename__ = 'mes_equipo'
    id          = Column(Integer, primary_key=True, index=True)
    celda_id    = Column(Integer, ForeignKey('mes_celda_trabajo.id'), nullable=True)
    codigo      = Column(String(30), unique=True, nullable=False)
    nombre      = Column(String(200), nullable=False)
    marca       = Column(String(100), nullable=True)
    modelo      = Column(String(100), nullable=True)
    serial      = Column(String(100), nullable=True)
    eam_activo_id = Column(Integer, nullable=True)
    capacidad_hora = Column(Float, nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)
    celda       = relationship('MESCeldaTrabajo', back_populates='equipos')


class MESOperario(Base, TimestampMixin):
    __tablename__ = 'mes_operario'
    id            = Column(Integer, primary_key=True, index=True)
    codigo        = Column(String(30), unique=True, nullable=False)
    nombre        = Column(String(200), nullable=False)
    cedula        = Column(String(30), nullable=True)
    cargo         = Column(String(100), nullable=True)
    planta_id     = Column(Integer, ForeignKey('mes_planta.id'), nullable=True)
    hcm_empleado_id = Column(Integer, nullable=True)
    # Un usuario de la plataforma por operario.
    #
    # Sin esto, la terminal de planta se identifica con un código que cualquiera
    # puede escribir, y el registro dice quién DIJO que era, no quién era. Con
    # el usuario detrás, cada avance queda firmado por una cuenta real — y es lo
    # único que permite medir la productividad de cada operario, que es la mitad
    # de la razón por la que existe un MES.
    usuario_id    = Column(Integer, ForeignKey('usuarios.id', ondelete='SET NULL'),
                           nullable=True, unique=True)
    # El PIN con el que se identifica en la terminal. No reemplaza la contraseña
    # de su cuenta: la terminal queda abierta con la sesión de la planta y el PIN
    # dice cuál de los operarios está reportando. Pedir una contraseña larga en
    # un teclado con guantes termina en que todos comparten una sesión, y ahí se
    # pierde exactamente lo que se quería medir.
    pin           = Column(String(8), nullable=True)
    activo        = Column(Boolean, default=True, nullable=False)
    certificaciones = relationship('MESCertificacion', back_populates='operario', lazy='dynamic')


class MESCertificacion(Base, TimestampMixin):
    __tablename__ = 'mes_certificacion'
    id           = Column(Integer, primary_key=True, index=True)
    operario_id  = Column(Integer, ForeignKey('mes_operario.id'), nullable=False)
    nombre       = Column(String(200), nullable=False)
    entidad      = Column(String(200), nullable=True)
    fecha_emision  = Column(DateTime(timezone=True), nullable=True)
    fecha_vencimiento = Column(DateTime(timezone=True), nullable=True)
    activo       = Column(Boolean, default=True, nullable=False)
    operario     = relationship('MESOperario', back_populates='certificaciones')


class MESProducto(Base, TimestampMixin):
    __tablename__ = 'mes_producto'
    id            = Column(Integer, primary_key=True, index=True)
    # El código lo arma el sistema con el tipo y la familia —`PT-BOLSA-0001`—.
    # Se sigue guardando como texto y no como tres columnas porque es el
    # identificador que la gente dice en voz alta y escribe en las etiquetas.
    codigo        = Column(String(50), unique=True, nullable=False)
    nombre        = Column(String(300), nullable=False)
    # La familia es la segunda mitad del código: BOLSA, LAMINA, RESINA. Va como
    # texto libre normalizado y no como catálogo aparte porque nace del uso —el
    # que registra el primer producto de una familia la está creando— y una
    # tabla más obligaría a configurar antes de poder trabajar.
    familia       = Column(String(60), nullable=True, index=True)
    descripcion   = Column(Text, nullable=True)
    tipo          = Column(SAEnum(TipoProductoMESEnum), nullable=False, default=TipoProductoMESEnum.PRODUCTO_TERMINADO)
    unidad_medida = Column(String(30), nullable=False, default='UN')
    peso_kg       = Column(Float, nullable=True)
    vida_util_dias = Column(Integer, nullable=True)
    requiere_lote = Column(Boolean, default=True, nullable=False)
    activo        = Column(Boolean, default=True, nullable=False)
    boms          = relationship('MESBOM', back_populates='producto', lazy='dynamic')
    recetas       = relationship('MESReceta', back_populates='producto', lazy='dynamic')


class MESBOM(Base, TimestampMixin):
    __tablename__ = 'mes_bom'
    id          = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    version     = Column(String(20), nullable=False, default='1.0')
    tipo        = Column(SAEnum(TipoBOMEnum), nullable=False, default=TipoBOMEnum.SIMPLE)
    descripcion = Column(Text, nullable=True)
    vigente     = Column(Boolean, default=True, nullable=False)
    fecha_vigencia_inicio = Column(DateTime(timezone=True), nullable=True)
    fecha_vigencia_fin    = Column(DateTime(timezone=True), nullable=True)
    producto    = relationship('MESProducto', back_populates='boms')
    detalles    = relationship('MESBOMDetalle', back_populates='bom', lazy='dynamic')


class MESBOMDetalle(Base, TimestampMixin):
    __tablename__ = 'mes_bom_detalle'
    id           = Column(Integer, primary_key=True, index=True)
    bom_id       = Column(Integer, ForeignKey('mes_bom.id'), nullable=False)
    componente_id = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    nivel        = Column(Integer, nullable=False, default=1)
    cantidad     = Column(Float, nullable=False)
    unidad_medida = Column(String(30), nullable=False, default='UN')
    merma_pct    = Column(Float, nullable=False, default=0.0)
    es_critico   = Column(Boolean, default=False, nullable=False)
    bom          = relationship('MESBOM', back_populates='detalles')


class MESReceta(Base, TimestampMixin):
    __tablename__ = 'mes_receta'
    id           = Column(Integer, primary_key=True, index=True)
    producto_id  = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    version      = Column(String(20), nullable=False, default='1.0')
    nombre       = Column(String(200), nullable=False)
    descripcion  = Column(Text, nullable=True)
    rendimiento_pct = Column(Float, nullable=False, default=100.0)
    tiempo_proceso_min = Column(Float, nullable=True)
    temperatura  = Column(Float, nullable=True)
    vigente      = Column(Boolean, default=True, nullable=False)
    producto     = relationship('MESProducto', back_populates='recetas')
    detalles     = relationship('MESRecetaDetalle', back_populates='receta', lazy='dynamic')


class MESRecetaDetalle(Base, TimestampMixin):
    __tablename__ = 'mes_receta_detalle'
    id            = Column(Integer, primary_key=True, index=True)
    receta_id     = Column(Integer, ForeignKey('mes_receta.id'), nullable=False)
    ingrediente_id = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    cantidad      = Column(Float, nullable=False)
    porcentaje    = Column(Float, nullable=True)
    unidad_medida = Column(String(30), nullable=False, default='KG')
    orden         = Column(Integer, nullable=False, default=1)
    es_critico    = Column(Boolean, default=False, nullable=False)
    receta        = relationship('MESReceta', back_populates='detalles')


class MESOperacion(Base, TimestampMixin):
    __tablename__ = 'mes_operacion'
    id            = Column(Integer, primary_key=True, index=True)
    celda_id      = Column(Integer, ForeignKey('mes_celda_trabajo.id'), nullable=True)
    codigo        = Column(String(30), nullable=False)
    nombre        = Column(String(200), nullable=False)
    # De qué clase es: preparación, transformación, corte, empaque… Sale del
    # catálogo `MES/TIPO_OPERACION`. La operación es la de esta planta —«raspado
    # de casco», «embandado»— y el tipo es lo que permite compararla con la de
    # otra planta que llama distinto a lo mismo.
    tipo          = Column(String(80), nullable=True, index=True)
    descripcion   = Column(Text, nullable=True)
    tiempo_std_min = Column(Float, nullable=True)
    requiere_inspeccion = Column(Boolean, default=False, nullable=False)
    activo        = Column(Boolean, default=True, nullable=False)


class MESOrdenProduccion(Base, TimestampMixin):
    __tablename__ = 'mes_orden_produccion'
    id              = Column(Integer, primary_key=True, index=True)
    numero          = Column(String(50), unique=True, nullable=False)
    producto_id     = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    linea_id        = Column(Integer, ForeignKey('mes_linea.id'), nullable=True)
    bom_id          = Column(Integer, ForeignKey('mes_bom.id'), nullable=True)
    receta_id       = Column(Integer, ForeignKey('mes_receta.id'), nullable=True)
    estado          = Column(SAEnum(EstadoOrdenProduccionEnum), nullable=False, default=EstadoOrdenProduccionEnum.PLANEADA)
    prioridad       = Column(SAEnum(PrioridadOrdenMESEnum), nullable=False, default=PrioridadOrdenMESEnum.NORMAL)
    cantidad_planificada = Column(Float, nullable=False)
    cantidad_producida   = Column(Float, nullable=False, default=0.0)
    cantidad_scrap       = Column(Float, nullable=False, default=0.0)
    unidad_medida   = Column(String(30), nullable=False, default='UN')
    fecha_inicio_plan = Column(DateTime(timezone=True), nullable=True)
    fecha_fin_plan    = Column(DateTime(timezone=True), nullable=True)
    fecha_inicio_real = Column(DateTime(timezone=True), nullable=True)
    fecha_fin_real    = Column(DateTime(timezone=True), nullable=True)
    responsable_id  = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)
    observaciones   = Column(Text, nullable=True)
    costo_material  = Column(Float, nullable=False, default=0.0)
    costo_mano_obra = Column(Float, nullable=False, default=0.0)
    costo_indirecto = Column(Float, nullable=False, default=0.0)


class MESOrdenOperacion(Base, TimestampMixin):
    __tablename__ = 'mes_orden_operacion'
    id              = Column(Integer, primary_key=True, index=True)
    orden_id        = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=False)
    operacion_id    = Column(Integer, ForeignKey('mes_operacion.id'), nullable=False)
    secuencia       = Column(Integer, nullable=False, default=1)
    estado          = Column(SAEnum(EstadoEjecucionMESEnum), nullable=False, default=EstadoEjecucionMESEnum.PENDIENTE)
    tiempo_std_min  = Column(Float, nullable=True)
    tiempo_real_min = Column(Float, nullable=True)
    cantidad_plan   = Column(Float, nullable=True)
    cantidad_real   = Column(Float, nullable=True)


class MESLote(Base, TimestampMixin):
    __tablename__ = 'mes_lote'
    id             = Column(Integer, primary_key=True, index=True)
    numero_lote    = Column(String(100), unique=True, nullable=False)
    orden_id       = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=True)
    producto_id    = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    estado         = Column(SAEnum(EstadoLoteMESEnum), nullable=False, default=EstadoLoteMESEnum.ACTIVO)
    cantidad       = Column(Float, nullable=False)
    unidad_medida  = Column(String(30), nullable=False, default='UN')
    fecha_fabricacion  = Column(DateTime(timezone=True), nullable=True)
    fecha_vencimiento  = Column(DateTime(timezone=True), nullable=True)
    fecha_liberacion   = Column(DateTime(timezone=True), nullable=True)
    responsable_liberacion = Column(String(200), nullable=True)
    observaciones  = Column(Text, nullable=True)


class MESEjecucion(Base, TimestampMixin):
    __tablename__ = 'mes_ejecucion'
    id               = Column(Integer, primary_key=True, index=True)
    orden_id         = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=False)
    orden_operacion_id = Column(Integer, ForeignKey('mes_orden_operacion.id'), nullable=True)
    operario_id      = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)
    equipo_id        = Column(Integer, ForeignKey('mes_equipo.id'), nullable=True)
    turno            = Column(SAEnum(TurnoMESEnum), nullable=False, default=TurnoMESEnum.MANANA)
    estado           = Column(SAEnum(EstadoEjecucionMESEnum), nullable=False, default=EstadoEjecucionMESEnum.PENDIENTE)
    fecha_inicio     = Column(DateTime(timezone=True), nullable=True)
    fecha_fin        = Column(DateTime(timezone=True), nullable=True)
    cantidad_producida = Column(Float, nullable=False, default=0.0)
    cantidad_scrap   = Column(Float, nullable=False, default=0.0)
    observaciones    = Column(Text, nullable=True)
    paradas          = relationship('MESParada', back_populates='ejecucion', lazy='dynamic')


class MESParada(Base, TimestampMixin):
    """Una detención de la producción: cuánto duró y por qué.

    Cuelga de una ejecución o de una estación, y por eso las dos son opcionales.
    Antes solo existía la ejecución, así que una avería no se podía reportar
    desde donde ocurre —la máquina— y quedaba fuera del registro. Saber que una
    estación produjo 200 unidades sin saber que estuvo parada tres horas no
    sirve para calcular el OEE, que es el indicador por el que existe un MES.
    """

    __tablename__ = 'mes_parada'
    id            = Column(Integer, primary_key=True, index=True)
    ejecucion_id  = Column(Integer, ForeignKey('mes_ejecucion.id'), nullable=True)
    avance_id     = Column(Integer,
                           ForeignKey('mes_avance_estacion.id', ondelete='CASCADE'),
                           nullable=True, index=True)
    operario_id   = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)
    equipo_id     = Column(Integer, ForeignKey('mes_equipo.id'), nullable=True)
    tipo          = Column(SAEnum(TipoParadaMESEnum), nullable=False)
    causa         = Column(String(200), nullable=False)
    descripcion   = Column(Text, nullable=True)
    fecha_inicio  = Column(DateTime(timezone=True), nullable=False)
    fecha_fin     = Column(DateTime(timezone=True), nullable=True)
    duracion_min  = Column(Float, nullable=True)
    ot_mantenimiento_id = Column(Integer, nullable=True)
    ejecucion     = relationship('MESEjecucion', back_populates='paradas')


class MESConsumoMaterial(Base, TimestampMixin):
    __tablename__ = 'mes_consumo_material'
    id            = Column(Integer, primary_key=True, index=True)
    orden_id      = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=False)
    producto_id   = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    lote_id       = Column(Integer, ForeignKey('mes_lote.id'), nullable=True)
    cantidad_plan = Column(Float, nullable=False)
    cantidad_real = Column(Float, nullable=False, default=0.0)
    unidad_medida = Column(String(30), nullable=False, default='UN')
    fecha_consumo = Column(DateTime(timezone=True), nullable=True)
    operario_id   = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)


class MESWIP(Base, TimestampMixin):
    """El libro de movimientos del material en proceso, módulo por módulo.

    Es la única fuente de dónde está el material: el saldo de un módulo es la
    suma de sus movimientos y no una columna que alguien mantenga a mano.

    POR QUÉ HAY DOS CELDAS Y NO UNA
    Un traslado entre módulos tiene dos extremos. Con una sola columna, una
    TRANSFERENCIA salía del origen y no entraba a ninguna parte: el material
    desaparecía del saldo. Era el caso que hacía inservible el inventario en
    proceso, y por eso `celda_destino_id` es obligatorio en los traslados y va
    vacío en el resto de los movimientos.
    """

    __tablename__ = 'mes_wip'
    id            = Column(Integer, primary_key=True, index=True)
    orden_id      = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=False)
    celda_id      = Column(Integer, ForeignKey('mes_celda_trabajo.id'), nullable=False)
    # Solo en los traslados: el módulo que recibe.
    celda_destino_id = Column(Integer, ForeignKey('mes_celda_trabajo.id'), nullable=True)
    producto_id   = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    lote_id       = Column(Integer, ForeignKey('mes_lote.id'), nullable=True)
    tipo_mov      = Column(SAEnum(TipoMovimientoWIPEnum), nullable=False)
    cantidad      = Column(Float, nullable=False)
    unidad_medida = Column(String(30), nullable=False, default='UN')
    fecha_mov     = Column(DateTime(timezone=True), nullable=False)
    # El movimiento que nació de una devolución queda amarrado a ella: es lo
    # que permite responder «¿por qué salió material de este módulo?».
    devolucion_id = Column(Integer, ForeignKey('mes_devolucion.id', ondelete='SET NULL'),
                           nullable=True, index=True)
    observaciones = Column(Text, nullable=True)


class MESInspeccion(Base, TimestampMixin):
    __tablename__ = 'mes_inspeccion'
    id             = Column(Integer, primary_key=True, index=True)
    orden_id       = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=False)
    lote_id        = Column(Integer, ForeignKey('mes_lote.id'), nullable=True)
    operario_id    = Column(Integer, ForeignKey('mes_operario.id'), nullable=False)
    tipo           = Column(SAEnum(TipoInspeccionMESEnum), nullable=False)
    resultado      = Column(SAEnum(ResultadoInspeccionMESEnum), nullable=False, default=ResultadoInspeccionMESEnum.PENDIENTE)
    fecha_inspeccion = Column(DateTime(timezone=True), nullable=False)
    muestra_tam    = Column(Integer, nullable=True)
    muestra_defectos = Column(Integer, nullable=False, default=0)
    observaciones  = Column(Text, nullable=True)
    qms_nc_id      = Column(Integer, nullable=True)
    defectos       = relationship('MESDefecto', back_populates='inspeccion', lazy='dynamic')


class MESDefecto(Base, TimestampMixin):
    __tablename__ = 'mes_defecto'
    id             = Column(Integer, primary_key=True, index=True)
    inspeccion_id  = Column(Integer, ForeignKey('mes_inspeccion.id'), nullable=False)
    codigo_defecto = Column(String(50), nullable=False)
    descripcion    = Column(String(300), nullable=False)
    cantidad       = Column(Integer, nullable=False, default=1)
    ubicacion      = Column(String(200), nullable=True)
    causa_raiz     = Column(String(300), nullable=True)
    inspeccion     = relationship('MESInspeccion', back_populates='defectos')


class MESScrap(Base, TimestampMixin):
    __tablename__ = 'mes_scrap'
    id            = Column(Integer, primary_key=True, index=True)
    orden_id      = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=False)
    producto_id   = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    operario_id   = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)
    tipo          = Column(SAEnum(TipoScrapMESEnum), nullable=False, default=TipoScrapMESEnum.NORMAL)
    causa         = Column(String(200), nullable=False)
    cantidad      = Column(Float, nullable=False)
    unidad_medida = Column(String(30), nullable=False, default='UN')
    costo_unitario = Column(Float, nullable=True)
    costo_total   = Column(Float, nullable=True)
    fecha_registro = Column(DateTime(timezone=True), nullable=False)
    es_reprocesable = Column(Boolean, default=False, nullable=False)
    observaciones = Column(Text, nullable=True)


class MESDevolucion(Base, TimestampMixin):
    """Producto averiado que un módulo devuelve al módulo que lo hizo.

    POR QUÉ NO ES SCRAP
    El scrap es material que se pierde: se da de baja y no vuelve. Una
    devolución es material que **sí vuelve**: el módulo que la recibe lo repara
    y lo reingresa al flujo. Meter las dos cosas en la misma tabla haría que la
    tasa de scrap contara como pérdida lo que solo fue un reproceso, y eso
    cambia la única cifra con la que se negocia una línea.

    POR QUÉ MUEVE EL WIP Y NO UN CONTADOR
    Registrar la devolución sin mover el material dejaría el saldo del módulo
    diciendo que todavía tiene unidades que ya devolvió. Cada devolución genera
    sus movimientos en `mes_wip` —salida del que devuelve, entrada al que tiene
    que rehacer— y al reprocesarse genera los dos de vuelta. El saldo siempre
    es la suma del libro.
    """

    __tablename__ = 'mes_devolucion'
    id            = Column(Integer, primary_key=True, index=True)
    orden_id      = Column(Integer, ForeignKey('mes_orden_produccion.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    # El módulo que detectó la avería y devuelve.
    celda_origen_id  = Column(Integer, ForeignKey('mes_celda_trabajo.id'), nullable=False)
    # El módulo que tiene que rehacerlo.
    celda_destino_id = Column(Integer, ForeignKey('mes_celda_trabajo.id'), nullable=False)
    producto_id   = Column(Integer, ForeignKey('mes_producto.id'), nullable=False)
    lote_id       = Column(Integer, ForeignKey('mes_lote.id'), nullable=True)
    operario_id   = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)
    cantidad      = Column(Float, nullable=False)
    unidad_medida = Column(String(30), nullable=False, default='UN')
    # Qué falla tiene. Es el dato que, agrupado, dice qué módulo genera el
    # reproceso y por qué.
    motivo        = Column(String(200), nullable=False)
    descripcion   = Column(Text, nullable=True)
    # PENDIENTE mientras el módulo destino no la haya reprocesado.
    estado        = Column(String(20), nullable=False, default='PENDIENTE')
    fecha         = Column(DateTime(timezone=True), nullable=False)
    fecha_reproceso = Column(DateTime(timezone=True), nullable=True)
    observaciones_reproceso = Column(Text, nullable=True)


class MESOEERegistro(Base, TimestampMixin):
    __tablename__ = 'mes_oee_registro'
    id               = Column(Integer, primary_key=True, index=True)
    linea_id         = Column(Integer, ForeignKey('mes_linea.id'), nullable=False)
    equipo_id        = Column(Integer, ForeignKey('mes_equipo.id'), nullable=True)
    fecha            = Column(DateTime(timezone=True), nullable=False)
    turno            = Column(SAEnum(TurnoMESEnum), nullable=False, default=TurnoMESEnum.MANANA)
    tiempo_planificado_min = Column(Float, nullable=False)
    tiempo_paradas_min     = Column(Float, nullable=False, default=0.0)
    tiempo_operativo_min   = Column(Float, nullable=False)
    velocidad_nominal      = Column(Float, nullable=True)
    velocidad_real         = Column(Float, nullable=True)
    produccion_real        = Column(Float, nullable=False)
    produccion_nominal     = Column(Float, nullable=False)
    produccion_buena       = Column(Float, nullable=False)
    disponibilidad   = Column(Float, nullable=True)
    rendimiento      = Column(Float, nullable=True)
    calidad          = Column(Float, nullable=True)
    oee              = Column(Float, nullable=True)


class MESChecklistPlantilla(Base, TimestampMixin):
    __tablename__ = 'mes_checklist_plantilla'
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    aplica_a    = Column(String(100), nullable=False, default='ORDEN')
    activo      = Column(Boolean, default=True, nullable=False)
    preguntas   = relationship('MESChecklistPregunta', back_populates='plantilla', lazy='dynamic')


class MESChecklistPregunta(Base, TimestampMixin):
    __tablename__ = 'mes_checklist_pregunta'
    id            = Column(Integer, primary_key=True, index=True)
    plantilla_id  = Column(Integer, ForeignKey('mes_checklist_plantilla.id'), nullable=False)
    orden         = Column(Integer, nullable=False, default=1)
    pregunta      = Column(String(500), nullable=False)
    tipo          = Column(String(30), nullable=False, default='SI_NO')
    obligatoria   = Column(Boolean, default=True, nullable=False)
    critica       = Column(Boolean, default=False, nullable=False)
    plantilla     = relationship('MESChecklistPlantilla', back_populates='preguntas')


class MESChecklistEjecucion(Base, TimestampMixin):
    __tablename__ = 'mes_checklist_ejecucion'
    id            = Column(Integer, primary_key=True, index=True)
    orden_id      = Column(Integer, ForeignKey('mes_orden_produccion.id'), nullable=False)
    plantilla_id  = Column(Integer, ForeignKey('mes_checklist_plantilla.id'), nullable=False)
    operario_id   = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)
    fecha         = Column(DateTime(timezone=True), nullable=False)
    estado        = Column(String(30), nullable=False, default='COMPLETO')
    observaciones = Column(Text, nullable=True)


class MESKPIDiario(Base, TimestampMixin):
    __tablename__ = 'mes_kpi_diario'
    id               = Column(Integer, primary_key=True, index=True)
    fecha            = Column(DateTime(timezone=True), nullable=False)
    planta_id        = Column(Integer, ForeignKey('mes_planta.id'), nullable=True)
    ordenes_planeadas = Column(Integer, nullable=False, default=0)
    ordenes_completadas = Column(Integer, nullable=False, default=0)
    oee_promedio     = Column(Float, nullable=True)
    produccion_total = Column(Float, nullable=False, default=0.0)
    scrap_total      = Column(Float, nullable=False, default=0.0)
    scrap_pct        = Column(Float, nullable=True)
    cumplimiento_pct = Column(Float, nullable=True)
    paradas_min      = Column(Float, nullable=False, default=0.0)
    inspecciones     = Column(Integer, nullable=False, default=0)
    rechazos         = Column(Integer, nullable=False, default=0)
    first_pass_yield = Column(Float, nullable=True)


# ══════════════════════════════════════════════════════════════════════════════
# EL ESQUEMA DE LA LÍNEA
# ══════════════════════════════════════════════════════════════════════════════
#
# Una línea de producción no es una lista de máquinas: es un recorrido. Saber
# que la extrusora y la cortadora están en la línea 2 no dice nada; lo que
# importa es que el material entra por el mezclador, pasa a la extrusora y sale
# por la cortadora, y que si la extrusora se detiene, todo lo que va detrás se
# queda quieto.
#
# Por eso el esquema se guarda como un grafo —nodos y conexiones— y no como un
# campo `orden` en la máquina. Un número de orden solo sabe describir una fila
# india: no puede representar una línea que se abre en dos, un reproceso que
# devuelve material a una etapa anterior, ni dos entradas de materia prima que
# confluyen en la misma máquina. Todas esas formas existen en una planta real.
#
# Las coordenadas viven acá y no en el navegador porque el dibujo es del
# proceso, no de quien lo dibujó: quien abra la línea mañana tiene que ver el
# mismo esquema.


class TipoNodoFlujoEnum(enum.Enum):
    """Qué representa un nodo del esquema.

    Las máquinas son lo esperable, pero un esquema que solo tuviera máquinas no
    diría de dónde sale el material ni a dónde va. La entrada de materia prima y
    la salida de producto son parte del recorrido y por eso son nodos, no notas
    al margen.
    """
    EQUIPO     = 'EQUIPO'        # una máquina del catálogo
    ENTRADA    = 'ENTRADA'       # por acá entra una materia prima
    SALIDA     = 'SALIDA'        # por acá sale producto terminado o semielaborado
    INSPECCION = 'INSPECCION'    # punto de control de calidad
    BUFFER     = 'BUFFER'        # acumulación entre etapas


class TipoConexionFlujoEnum(enum.Enum):
    NORMAL    = 'NORMAL'      # el material sigue su curso
    RETRABAJO = 'RETRABAJO'   # vuelve atrás a corregirse
    SCRAP     = 'SCRAP'       # sale del proceso como desecho
    ALTERNA   = 'ALTERNA'     # ruta opcional, según el producto


class MESFlujoNodo(Base, TimestampMixin):
    """Un punto del esquema de una línea, con su posición en el lienzo."""

    __tablename__ = 'mes_flujo_nodo'
    id         = Column(Integer, primary_key=True, index=True)
    linea_id   = Column(Integer, ForeignKey('mes_linea.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    tipo       = Column(SAEnum(TipoNodoFlujoEnum), nullable=False,
                        default=TipoNodoFlujoEnum.EQUIPO)
    # La máquina que ocupa el nodo. Va vacía en entradas, salidas y buffers.
    equipo_id  = Column(Integer, ForeignKey('mes_equipo.id'), nullable=True)
    # El material que entra o el producto que sale, según el tipo de nodo. Es lo
    # que conecta el esquema con el catálogo de materias primas.
    producto_id = Column(Integer, ForeignKey('mes_producto.id'), nullable=True)
    # Qué se hace en este punto. Permite que el esquema diga «acá se troquela» y
    # no solo «acá está la troqueladora».
    operacion_id = Column(Integer, ForeignKey('mes_operacion.id'), nullable=True)

    # El nombre propio del nodo. Si viene vacío se muestra el de la máquina o el
    # del producto; sirve para distinguir dos prensas iguales en el mismo
    # esquema («Prensa 1 · desbaste» y «Prensa 2 · acabado»).
    nombre     = Column(String(200), nullable=True)
    pos_x      = Column(Float, nullable=False, default=0.0)
    pos_y      = Column(Float, nullable=False, default=0.0)
    # Cuántas unidades del material entran por cada unidad producida. Solo tiene
    # sentido en los nodos de entrada.
    cantidad_por_unidad = Column(Float, nullable=True)
    unidad_medida = Column(String(30), nullable=True)
    tiempo_ciclo_seg = Column(Float, nullable=True)
    # Un cuello de botella declarado se pinta distinto: es la máquina que marca
    # el ritmo de toda la línea y conviene que salte a la vista.
    es_cuello_botella = Column(Boolean, default=False, nullable=False)
    notas      = Column(Text, nullable=True)
    activo     = Column(Boolean, default=True, nullable=False)


class MESAvanceEstacion(Base, TimestampMixin):
    """Lo que una estación de la línea hizo con una orden.

    POR QUÉ EXISTE
    Una orden de producción no pasa de «planeada» a «cerrada» de un salto: la
    recorre la línea, estación por estación. Sin este registro, el sistema solo
    sabe cuánto se produjo en total y no dónde está la orden ahora mismo, que es
    justo lo que pregunta quien la está esperando. También es lo que hace posible
    la trazabilidad de verdad: qué máquina, qué operario y a qué hora tocó cada
    unidad.

    LA REGLA QUE LO SOSTIENE
    Una estación no puede producir más de lo que le entregó la anterior. Sin esa
    restricción, la suma de avances puede superar lo que entró a la línea y el
    tablero mostraría un cumplimiento imposible. Se valida al registrar, no al
    consultar: un dato imposible no debe llegar a guardarse.

    Hay un registro por orden y estación —de ahí la restricción única—: el
    operario suma sobre el mismo registro cada vez que reporta, y así queda
    cuánto lleva esa estación en total, no una lista de eventos que haya que
    sumar en cada consulta.
    """

    __tablename__ = 'mes_avance_estacion'
    __table_args__ = (
        UniqueConstraint('orden_id', 'nodo_id', name='uq_avance_orden_nodo'),
    )

    id          = Column(Integer, primary_key=True, index=True)
    orden_id    = Column(Integer, ForeignKey('mes_orden_produccion.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    nodo_id     = Column(Integer, ForeignKey('mes_flujo_nodo.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    operario_id = Column(Integer, ForeignKey('mes_operario.id'), nullable=True)
    turno       = Column(SAEnum(TurnoMESEnum), nullable=False,
                         default=TurnoMESEnum.MANANA)
    estado      = Column(SAEnum(EstadoEjecucionMESEnum), nullable=False,
                         default=EstadoEjecucionMESEnum.PENDIENTE)
    # Lo bueno que salió de esta estación y lo que se perdió en ella. El scrap se
    # anota donde ocurre y no al final, porque saber en qué máquina se pierde el
    # material es la mitad del valor de medirlo.
    cantidad_producida = Column(Float, nullable=False, default=0.0)
    cantidad_scrap     = Column(Float, nullable=False, default=0.0)
    fecha_inicio  = Column(DateTime(timezone=True), nullable=True)
    fecha_fin     = Column(DateTime(timezone=True), nullable=True)
    observaciones = Column(Text, nullable=True)


class MESFlujoConexion(Base, TimestampMixin):
    """Por dónde pasa el material de un nodo al siguiente."""

    __tablename__ = 'mes_flujo_conexion'
    id        = Column(Integer, primary_key=True, index=True)
    linea_id  = Column(Integer, ForeignKey('mes_linea.id', ondelete='CASCADE'),
                       nullable=False, index=True)
    origen_id  = Column(Integer, ForeignKey('mes_flujo_nodo.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    destino_id = Column(Integer, ForeignKey('mes_flujo_nodo.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    tipo      = Column(SAEnum(TipoConexionFlujoEnum), nullable=False,
                       default=TipoConexionFlujoEnum.NORMAL)
    etiqueta  = Column(String(120), nullable=True)
