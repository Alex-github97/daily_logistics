"""
Módulo de Gestión de Flotas — Modelos de base de datos
Prefijo de tabla: fleet_
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ─── Catálogos ─────────────────────────────────────────────────────────────────

class FlotaMarca(Base, TimestampMixin):
    __tablename__ = "fleet_marcas"
    id      = Column(Integer, primary_key=True, index=True)
    nombre  = Column(String(100), nullable=False, unique=True)
    activo  = Column(Boolean, default=True)
    vehiculos = relationship("FlotaVehiculo", back_populates="marca")


class FlotaTipoVehiculo(Base, TimestampMixin):
    __tablename__ = "fleet_tipos_vehiculo"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(100), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)
    activo      = Column(Boolean, default=True)
    vehiculos   = relationship("FlotaVehiculo", back_populates="tipo_vehiculo")


class FlotaTipoCombustible(Base, TimestampMixin):
    __tablename__ = "fleet_tipos_combustible"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(60), nullable=False, unique=True)
    unidad = Column(String(20), default="GALON")  # GALON, LITRO, KWH
    activo = Column(Boolean, default=True)


class FlotaCentroCosto(Base, TimestampMixin):
    __tablename__ = "fleet_centros_costo"
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(30), nullable=False, unique=True)
    nombre      = Column(String(120), nullable=False)
    descripcion = Column(String(255), nullable=True)
    activo      = Column(Boolean, default=True)


class FlotaProveedor(Base, TimestampMixin):
    __tablename__ = "fleet_proveedores"
    id       = Column(Integer, primary_key=True, index=True)
    nombre   = Column(String(150), nullable=False)
    nit      = Column(String(30), nullable=True)
    contacto = Column(String(100), nullable=True)
    telefono = Column(String(30), nullable=True)
    email    = Column(String(120), nullable=True)
    tipo     = Column(String(30), default="GENERAL")  # COMBUSTIBLE, REPUESTOS, TALLER, GENERAL
    activo   = Column(Boolean, default=True)
    combustibles = relationship("FlotaRegistroCombustible", back_populates="proveedor")
    ordenes      = relationship("FlotaOrdenTrabajo", back_populates="proveedor")


# ─── Vehículos ─────────────────────────────────────────────────────────────────

class FlotaVehiculo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fleet_vehiculos"
    id               = Column(Integer, primary_key=True, index=True)
    placa            = Column(String(20), nullable=False, unique=True, index=True)
    marca_id         = Column(Integer, ForeignKey("fleet_marcas.id"), nullable=True)
    tipo_vehiculo_id = Column(Integer, ForeignKey("fleet_tipos_vehiculo.id"), nullable=True)
    linea            = Column(String(80), nullable=True)
    modelo           = Column(Integer, nullable=True)   # Año modelo
    color            = Column(String(40), nullable=True)
    tipo_medicion    = Column(String(20), default="KM")      # KM, HORAS, AMBOS
    tipo_trabajo     = Column(String(20), default="NORMAL")  # BAJO, NORMAL, SEVERO
    combustible_principal_id  = Column(Integer, ForeignKey("fleet_tipos_combustible.id"), nullable=True)
    combustible_secundario_id = Column(Integer, ForeignKey("fleet_tipos_combustible.id"), nullable=True)
    centro_costo_id  = Column(Integer, ForeignKey("fleet_centros_costo.id"), nullable=True)
    ciudad           = Column(String(100), nullable=True)
    nro_motor        = Column(String(60), nullable=True)
    nro_serie        = Column(String(60), nullable=True)
    fecha_compra     = Column(Date, nullable=True)
    medicion_compra  = Column(Float, default=0)
    precio_compra    = Column(Float, nullable=True)
    distancia_max_dia    = Column(Float, nullable=True)
    distancia_prom_dia   = Column(Float, nullable=True)
    horas_operativas_mes = Column(Float, nullable=True)
    rendimiento_ideal    = Column(Float, nullable=True)   # km/galón
    fecha_baja    = Column(Date, nullable=True)
    motivo_baja   = Column(String(255), nullable=True)
    observaciones = Column(Text, nullable=True)

    marca         = relationship("FlotaMarca", back_populates="vehiculos")
    tipo_vehiculo = relationship("FlotaTipoVehiculo", back_populates="vehiculos")
    mediciones    = relationship("FlotaMedicion", back_populates="vehiculo", order_by="FlotaMedicion.fecha.desc()")
    documentos    = relationship("FlotaDocumentoVehiculo", back_populates="vehiculo")
    combustibles  = relationship("FlotaRegistroCombustible", back_populates="vehiculo", order_by="FlotaRegistroCombustible.fecha.desc()")
    ordenes       = relationship("FlotaOrdenTrabajo", back_populates="vehiculo")


class FlotaMedicion(Base, TimestampMixin):
    __tablename__ = "fleet_mediciones"
    id                = Column(Integer, primary_key=True, index=True)
    vehiculo_id       = Column(Integer, ForeignKey("fleet_vehiculos.id"), nullable=False)
    tipo              = Column(String(20), default="ODOMETRO")  # ODOMETRO, HOROMETRO
    valor             = Column(Float, nullable=False)
    fecha             = Column(Date, nullable=False)
    observaciones     = Column(String(255), nullable=True)
    registrado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    vehiculo          = relationship("FlotaVehiculo", back_populates="mediciones")


class FlotaDocumentoVehiculo(Base, TimestampMixin):
    __tablename__ = "fleet_documentos_vehiculo"
    id                = Column(Integer, primary_key=True, index=True)
    vehiculo_id       = Column(Integer, ForeignKey("fleet_vehiculos.id"), nullable=False)
    tipo_documento    = Column(String(80), nullable=False)  # SOAT, RTM, TARJETA_OPERACION, etc.
    numero            = Column(String(60), nullable=True)
    fecha_expedicion  = Column(Date, nullable=True)
    fecha_vencimiento = Column(Date, nullable=False)
    entidad_emisora   = Column(String(120), nullable=True)
    archivo_url       = Column(String(500), nullable=True)
    vehiculo          = relationship("FlotaVehiculo", back_populates="documentos")


# ─── Personal ──────────────────────────────────────────────────────────────────

class FlotaPersonal(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fleet_personal"
    id               = Column(Integer, primary_key=True, index=True)
    tipo             = Column(String(20), default="CONDUCTOR")  # CONDUCTOR, MECANICO
    nombres          = Column(String(100), nullable=False)
    apellidos        = Column(String(100), nullable=False)
    tipo_documento   = Column(String(20), default="CC")
    numero_documento = Column(String(30), nullable=False)
    fecha_nacimiento = Column(Date, nullable=True)
    telefono         = Column(String(30), nullable=True)
    email            = Column(String(120), nullable=True)
    direccion        = Column(String(255), nullable=True)
    foto_url         = Column(String(500), nullable=True)
    especialidad     = Column(String(100), nullable=True)   # Para mecánicos
    conductor_id     = Column(Integer, ForeignKey("conductores.id"), nullable=True)
    activo           = Column(Boolean, default=True)
    documentos       = relationship("FlotaDocumentoPersonal", back_populates="personal")
    ordenes          = relationship("FlotaOrdenTrabajo", back_populates="mecanico")


class FlotaDocumentoPersonal(Base, TimestampMixin):
    __tablename__ = "fleet_documentos_personal"
    id                = Column(Integer, primary_key=True, index=True)
    personal_id       = Column(Integer, ForeignKey("fleet_personal.id"), nullable=False)
    tipo_documento    = Column(String(80), nullable=False)
    numero            = Column(String(60), nullable=True)
    categoria         = Column(String(20), nullable=True)  # Para licencias: B1, C1, C2...
    fecha_expedicion  = Column(Date, nullable=True)
    fecha_vencimiento = Column(Date, nullable=False)
    archivo_url       = Column(String(500), nullable=True)
    personal          = relationship("FlotaPersonal", back_populates="documentos")


# ─── Combustible ───────────────────────────────────────────────────────────────

class FlotaRegistroCombustible(Base, TimestampMixin):
    __tablename__ = "fleet_combustible"
    id                  = Column(Integer, primary_key=True, index=True)
    vehiculo_id         = Column(Integer, ForeignKey("fleet_vehiculos.id"), nullable=False)
    fecha               = Column(Date, nullable=False)
    medicion_actual     = Column(Float, nullable=True)
    cantidad            = Column(Float, nullable=False)
    unidad              = Column(String(20), default="GALON")
    valor_unitario      = Column(Float, nullable=True)
    valor_total         = Column(Float, nullable=True)
    tipo_combustible_id = Column(Integer, ForeignKey("fleet_tipos_combustible.id"), nullable=True)
    proveedor_id        = Column(Integer, ForeignKey("fleet_proveedores.id"), nullable=True)
    estacion            = Column(String(120), nullable=True)
    numero_factura      = Column(String(60), nullable=True)
    archivo_url         = Column(String(500), nullable=True)
    observaciones       = Column(String(255), nullable=True)
    registrado_por_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    vehiculo  = relationship("FlotaVehiculo", back_populates="combustibles")
    proveedor = relationship("FlotaProveedor", back_populates="combustibles")


# ─── Mantenimiento ─────────────────────────────────────────────────────────────

class FlotaTipoTrabajo(Base, TimestampMixin):
    __tablename__ = "fleet_tipos_trabajo"
    id                    = Column(Integer, primary_key=True, index=True)
    nombre                = Column(String(150), nullable=False)
    sistema               = Column(String(80), nullable=True)
    subsistema            = Column(String(80), nullable=True)
    tipo                  = Column(String(30), default="PREVENTIVO")  # PREVENTIVO, CORRECTIVO, PREV_CORR
    nivel_criticidad      = Column(String(20), default="MEDIA")       # BAJA, MEDIA, ALTA, CRITICA
    tiempo_estimado_horas = Column(Float, nullable=True)
    costo_estimado        = Column(Float, nullable=True)
    periodicidad_tipo     = Column(String(20), nullable=True)  # KM, HORAS, DIAS, MENSUAL, ANUAL
    periodicidad_valor    = Column(Float, nullable=True)
    activo                = Column(Boolean, default=True)
    ordenes_detalle       = relationship("FlotaOrdenTrabajoDetalle", back_populates="tipo_trabajo")


class FlotaOrdenTrabajo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fleet_ordenes_trabajo"
    id                = Column(Integer, primary_key=True, index=True)
    numero            = Column(String(20), nullable=False, unique=True, index=True)
    vehiculo_id       = Column(Integer, ForeignKey("fleet_vehiculos.id"), nullable=False)
    fecha_apertura    = Column(Date, nullable=False)
    fecha_cierre      = Column(Date, nullable=True)
    medicion_apertura = Column(Float, nullable=True)
    medicion_cierre   = Column(Float, nullable=True)
    personal_id       = Column(Integer, ForeignKey("fleet_personal.id"), nullable=True)
    tipo_taller       = Column(String(20), default="INTERNO")  # INTERNO, EXTERNO
    proveedor_id      = Column(Integer, ForeignKey("fleet_proveedores.id"), nullable=True)
    estado            = Column(String(20), default="ABIERTA")  # ABIERTA, EN_PROCESO, CERRADA, CANCELADA
    costo_repuestos   = Column(Float, default=0)
    costo_mano_obra   = Column(Float, default=0)
    observaciones     = Column(Text, nullable=True)
    creado_por_id     = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    vehiculo  = relationship("FlotaVehiculo", back_populates="ordenes")
    mecanico  = relationship("FlotaPersonal", back_populates="ordenes")
    proveedor = relationship("FlotaProveedor", back_populates="ordenes")
    detalles  = relationship("FlotaOrdenTrabajoDetalle", back_populates="orden", cascade="all, delete-orphan")


class FlotaOrdenTrabajoDetalle(Base, TimestampMixin):
    __tablename__ = "fleet_ordenes_trabajo_detalle"
    id              = Column(Integer, primary_key=True, index=True)
    orden_id        = Column(Integer, ForeignKey("fleet_ordenes_trabajo.id"), nullable=False)
    tipo_trabajo_id = Column(Integer, ForeignKey("fleet_tipos_trabajo.id"), nullable=True)
    descripcion     = Column(String(255), nullable=False)
    costo_repuestos = Column(Float, default=0)
    costo_mano_obra = Column(Float, default=0)
    estado          = Column(String(20), default="PENDIENTE")  # PENDIENTE, EN_PROCESO, COMPLETADO
    orden           = relationship("FlotaOrdenTrabajo", back_populates="detalles")
    tipo_trabajo    = relationship("FlotaTipoTrabajo", back_populates="ordenes_detalle")


# ─── Catálogo de Repuestos ─────────────────────────────────────────────────────

class FlotaRepuesto(Base, TimestampMixin):
    __tablename__ = "fleet_repuestos"
    id                = Column(Integer, primary_key=True, index=True)
    codigo            = Column(String(60), nullable=False, unique=True, index=True)
    nombre            = Column(String(200), nullable=False)
    descripcion       = Column(Text, nullable=True)
    categoria         = Column(String(60), nullable=True)   # MOTOR, FRENOS, SUSPENSION, ELECTRICO, FILTROS, NEUMATICOS, OTRO
    sistema           = Column(String(80), nullable=True)
    unidad            = Column(String(30), default="UNIDAD")  # UNIDAD, LITRO, KG, METRO, SET
    costo_referencia  = Column(Float, nullable=True)
    stock_minimo      = Column(Integer, default=0)
    activo            = Column(Boolean, default=True)
    rutinas_repuesto  = relationship("FlotaRutinaDetalleRepuesto", back_populates="repuesto")


# ─── Rutinas de Mantenimiento ──────────────────────────────────────────────────

class FlotaRutinaMantenimiento(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fleet_rutinas"
    id                         = Column(Integer, primary_key=True, index=True)
    codigo                     = Column(String(30), nullable=False, unique=True, index=True)
    nombre                     = Column(String(200), nullable=False)
    descripcion                = Column(Text, nullable=True)
    tipo                       = Column(String(30), default="PREVENTIVO")   # PREVENTIVO, PREDICTIVO, INSPECCION, CORRECTIVO
    nivel_criticidad           = Column(String(20), default="MEDIA")        # BAJA, MEDIA, ALTA, CRITICA
    aplica_tipo_trabajo_severo = Column(Boolean, default=False)             # Sólo condición SEVERO
    intervalo_km               = Column(Float, nullable=True)               # Cada N km
    intervalo_horas            = Column(Float, nullable=True)               # Cada N horas motor
    intervalo_dias             = Column(Integer, nullable=True)             # Cada N días calendario
    tolerancia_pct             = Column(Float, default=10.0)               # % tolerancia sobre el intervalo
    tiempo_estimado_horas      = Column(Float, nullable=True)               # Tiempo de ejecución
    costo_estimado_mano_obra   = Column(Float, nullable=True)
    instrucciones_generales    = Column(Text, nullable=True)
    activo                     = Column(Boolean, default=True)
    trabajos    = relationship("FlotaRutinaDetalleTrabajo",  back_populates="rutina", cascade="all, delete-orphan", order_by="FlotaRutinaDetalleTrabajo.orden")
    repuestos   = relationship("FlotaRutinaDetalleRepuesto", back_populates="rutina", cascade="all, delete-orphan")
    secuencias  = relationship("FlotaSecuenciaRutina", back_populates="rutina")
    modos_falla = relationship("FlotaModoFalla", back_populates="rutina_correctiva")
    umbrales    = relationship("FlotaUmbralCBM", back_populates="rutina_trigger")


class FlotaRutinaDetalleTrabajo(Base, TimestampMixin):
    __tablename__ = "fleet_rutinas_trabajos"
    id              = Column(Integer, primary_key=True, index=True)
    rutina_id       = Column(Integer, ForeignKey("fleet_rutinas.id"), nullable=False)
    tipo_trabajo_id = Column(Integer, ForeignKey("fleet_tipos_trabajo.id"), nullable=False)
    orden           = Column(Integer, default=1)
    obligatorio     = Column(Boolean, default=True)
    instrucciones   = Column(Text, nullable=True)
    rutina      = relationship("FlotaRutinaMantenimiento", back_populates="trabajos")
    tipo_trabajo = relationship("FlotaTipoTrabajo")


class FlotaRutinaDetalleRepuesto(Base, TimestampMixin):
    __tablename__ = "fleet_rutinas_repuestos"
    id          = Column(Integer, primary_key=True, index=True)
    rutina_id   = Column(Integer, ForeignKey("fleet_rutinas.id"), nullable=False)
    repuesto_id = Column(Integer, ForeignKey("fleet_repuestos.id"), nullable=False)
    cantidad    = Column(Float, default=1)
    obligatorio = Column(Boolean, default=True)
    rutina   = relationship("FlotaRutinaMantenimiento", back_populates="repuestos")
    repuesto = relationship("FlotaRepuesto", back_populates="rutinas_repuesto")


# ─── Secuencias de Mantenimiento ───────────────────────────────────────────────

class FlotaSecuenciaMantenimiento(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fleet_secuencias"
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(30), nullable=False, unique=True, index=True)
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    # Aplicabilidad por defecto (se puede sobrescribir en asignaciones)
    aplica_tipo_trabajo = Column(String(20), nullable=True)  # BAJO, NORMAL, SEVERO o NULL=Todos
    activo      = Column(Boolean, default=True)
    rutinas      = relationship("FlotaSecuenciaRutina",     back_populates="secuencia", cascade="all, delete-orphan", order_by="FlotaSecuenciaRutina.orden")
    asignaciones = relationship("FlotaAsignacionSecuencia", back_populates="secuencia",  cascade="all, delete-orphan")


class FlotaSecuenciaRutina(Base, TimestampMixin):
    """Rutina dentro de una secuencia con disparadores propios o heredados de la rutina."""
    __tablename__ = "fleet_secuencias_rutinas"
    id                     = Column(Integer, primary_key=True, index=True)
    secuencia_id           = Column(Integer, ForeignKey("fleet_secuencias.id"), nullable=False)
    rutina_id              = Column(Integer, ForeignKey("fleet_rutinas.id"), nullable=False)
    orden                  = Column(Integer, default=1)
    intervalo_km_override  = Column(Float, nullable=True)    # Sobreescribe intervalo_km de la rutina
    intervalo_dias_override = Column(Integer, nullable=True)  # Sobreescribe intervalo_dias
    notas                  = Column(String(255), nullable=True)
    secuencia = relationship("FlotaSecuenciaMantenimiento", back_populates="rutinas")
    rutina    = relationship("FlotaRutinaMantenimiento",    back_populates="secuencias")


# ─── Grupos de Vehículos ───────────────────────────────────────────────────────

class FlotaGrupoVehiculo(Base, TimestampMixin):
    __tablename__ = "fleet_grupos_vehiculo"
    id                   = Column(Integer, primary_key=True, index=True)
    nombre               = Column(String(150), nullable=False)
    descripcion          = Column(String(255), nullable=True)
    tipo_vehiculo_id     = Column(Integer, ForeignKey("fleet_tipos_vehiculo.id"), nullable=True)
    marca_id             = Column(Integer, ForeignKey("fleet_marcas.id"), nullable=True)
    tipo_trabajo_filtro  = Column(String(20), nullable=True)  # BAJO | NORMAL | SEVERO — NULL = todos
    ciudad               = Column(String(100), nullable=True)
    activo               = Column(Boolean, default=True)
    tipo_vehiculo = relationship("FlotaTipoVehiculo")
    marca         = relationship("FlotaMarca")
    asignaciones  = relationship("FlotaAsignacionSecuencia", back_populates="grupo")


# ─── Asignaciones de Secuencias ────────────────────────────────────────────────

class FlotaAsignacionSecuencia(Base, TimestampMixin):
    """Asocia una secuencia a un vehículo individual o a un grupo."""
    __tablename__ = "fleet_asignaciones_secuencia"
    id              = Column(Integer, primary_key=True, index=True)
    secuencia_id    = Column(Integer, ForeignKey("fleet_secuencias.id"), nullable=False)
    vehiculo_id     = Column(Integer, ForeignKey("fleet_vehiculos.id"), nullable=True)
    grupo_id        = Column(Integer, ForeignKey("fleet_grupos_vehiculo.id"), nullable=True)
    fecha_inicio    = Column(Date, nullable=False)
    medicion_inicio = Column(Float, nullable=True)
    activa          = Column(Boolean, default=True)
    notas           = Column(String(255), nullable=True)
    secuencia = relationship("FlotaSecuenciaMantenimiento", back_populates="asignaciones")
    vehiculo  = relationship("FlotaVehiculo")
    grupo     = relationship("FlotaGrupoVehiculo", back_populates="asignaciones")


# ─── FMEA / RCM — Modos de Falla ──────────────────────────────────────────────

class FlotaModoFalla(Base, TimestampMixin):
    """
    Análisis de Modos de Falla y Efectos (FMEA/AMEF).
    RPN = Severidad × Ocurrencia × Detección (1-10 cada uno).
    """
    __tablename__ = "fleet_modos_falla"
    id                  = Column(Integer, primary_key=True, index=True)
    sistema             = Column(String(80), nullable=False)
    subsistema          = Column(String(80), nullable=True)
    funcion             = Column(String(255), nullable=False)   # Función esperada del sistema
    falla_funcional     = Column(String(255), nullable=False)   # En qué falla
    modo_falla          = Column(String(255), nullable=False)   # Cómo falla
    efecto              = Column(String(255), nullable=True)    # Consecuencia
    causa               = Column(String(255), nullable=True)    # Causa raíz probable
    severidad           = Column(Integer, nullable=True)        # S: 1-10
    ocurrencia          = Column(Integer, nullable=True)        # O: 1-10
    deteccion           = Column(Integer, nullable=True)        # D: 1-10
    rpn                 = Column(Integer, nullable=True)        # RPN = S × O × D (calculado)
    accion_recomendada  = Column(String(255), nullable=True)
    tipo_vehiculo_id    = Column(Integer, ForeignKey("fleet_tipos_vehiculo.id"), nullable=True)
    rutina_correctiva_id = Column(Integer, ForeignKey("fleet_rutinas.id"), nullable=True)  # Rutina preventiva vinculada
    activo              = Column(Boolean, default=True)
    tipo_vehiculo    = relationship("FlotaTipoVehiculo")
    rutina_correctiva = relationship("FlotaRutinaMantenimiento", back_populates="modos_falla")


# ─── CBM — Umbrales de Condición ──────────────────────────────────────────────

class FlotaUmbralCBM(Base, TimestampMixin):
    """
    Condition-Based Maintenance: parámetros medibles con umbrales de alerta.
    Cuando el valor supera el umbral crítico, se genera una alerta de OT.
    """
    __tablename__ = "fleet_umbrales_cbm"
    id                  = Column(Integer, primary_key=True, index=True)
    parametro           = Column(String(100), nullable=False)    # e.g. "Presión aceite", "Temperatura refrigerante"
    descripcion         = Column(String(255), nullable=True)
    unidad              = Column(String(30), nullable=True)       # PSI, °C, bar, mm, %
    umbral_advertencia  = Column(Float, nullable=True)            # Alerta amarilla
    umbral_critico      = Column(Float, nullable=True)            # Alerta roja → genera OT
    direccion           = Column(String(10), default="MAYOR")     # MAYOR | MENOR (sobre/bajo el umbral)
    vehiculo_id         = Column(Integer, ForeignKey("fleet_vehiculos.id"), nullable=True)
    tipo_vehiculo_id    = Column(Integer, ForeignKey("fleet_tipos_vehiculo.id"), nullable=True)
    rutina_trigger_id   = Column(Integer, ForeignKey("fleet_rutinas.id"), nullable=True)
    activo              = Column(Boolean, default=True)
    vehiculo      = relationship("FlotaVehiculo")
    tipo_vehiculo = relationship("FlotaTipoVehiculo")
    rutina_trigger = relationship("FlotaRutinaMantenimiento", back_populates="umbrales")
