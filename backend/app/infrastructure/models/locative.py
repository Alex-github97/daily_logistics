"""
Módulo Mantenimiento Locativo — Modelos de base de datos
Prefijo: loca_
Normas: ISO 55000/55001 · ISO 41001 · ISO 31000 · ISO 14224 · ISO 50001 · IEC 60300 · EN 16646 · IAS 16/36
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Text, Date, Index
from sqlalchemy.orm import relationship
from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ─── Catálogos / Configuración ─────────────────────────────────────────────────

class LocativaSede(Base, TimestampMixin):
    __tablename__ = "loca_sedes"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(150), nullable=False)
    codigo      = Column(String(30), nullable=True, unique=True)
    direccion   = Column(String(255), nullable=True)
    ciudad      = Column(String(100), nullable=True)
    area_m2     = Column(Float, nullable=True)
    activo      = Column(Boolean, default=True)
    espacios    = relationship("LocativaEspacio", back_populates="sede")
    activos     = relationship("LocativaActivo", back_populates="sede")


class LocativaEspacio(Base, TimestampMixin):
    __tablename__ = "loca_espacios"
    id                  = Column(Integer, primary_key=True, index=True)
    sede_id             = Column(Integer, ForeignKey("loca_sedes.id"), nullable=False)
    nombre              = Column(String(150), nullable=False)
    codigo              = Column(String(30), nullable=True)
    tipo                = Column(String(50), default="OFICINA")  # OFICINA, BODEGA, BAÑO, ZONA_TECNICA, PARKING, OTRO
    edificio            = Column(String(80), nullable=True)
    piso                = Column(String(20), nullable=True)
    area_m2             = Column(Float, nullable=True)
    capacidad_personas  = Column(Integer, nullable=True)
    responsable         = Column(String(120), nullable=True)
    activo              = Column(Boolean, default=True)
    sede                = relationship("LocativaSede", back_populates="espacios")
    activos             = relationship("LocativaActivo", back_populates="espacio")


class LocativaCategoria(Base, TimestampMixin):
    """Categorías locativas (ISO 14224 asset taxonomy)"""
    __tablename__ = "loca_categorias"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(100), nullable=False, unique=True)
    codigo      = Column(String(20), nullable=True)
    descripcion = Column(String(255), nullable=True)
    activo      = Column(Boolean, default=True)
    activos     = relationship("LocativaActivo", back_populates="categoria")


class LocativaModoFalla(Base, TimestampMixin):
    """Catálogo de modos de falla — ISO 14224 §8"""
    __tablename__ = "loca_modos_falla"
    id              = Column(Integer, primary_key=True, index=True)
    codigo          = Column(String(20), nullable=True)
    nombre          = Column(String(150), nullable=False)
    categoria_falla = Column(String(80), nullable=True)  # Mecánica, Eléctrica, Estructural, etc.
    descripcion     = Column(String(255), nullable=True)
    es_iso14224     = Column(Boolean, default=True)
    activo          = Column(Boolean, default=True)


class LocativaProveedor(Base, TimestampMixin):
    __tablename__ = "loca_proveedores"
    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(150), nullable=False)
    nit             = Column(String(30), nullable=True)
    tipo            = Column(String(50), default="CONTRATISTA")  # CONTRATISTA, REPUESTOS, TALLER, OTRO
    contacto        = Column(String(100), nullable=True)
    telefono        = Column(String(30), nullable=True)
    email           = Column(String(120), nullable=True)
    especialidad    = Column(String(200), nullable=True)
    calificacion    = Column(Float, nullable=True)
    fecha_contrato_inicio   = Column(Date, nullable=True)
    fecha_contrato_vencimiento = Column(Date, nullable=True)
    activo          = Column(Boolean, default=True)
    ordenes         = relationship("LocativaOrdenTrabajo", back_populates="contratista")


# ─── Activos (IAS 16, ISO 55001, ISO 14224) ────────────────────────────────────

class LocativaActivo(Base, TimestampMixin, SoftDeleteMixin):
    """Registro maestro de activos físicos e infraestructura"""
    __tablename__ = "loca_activos"

    id                      = Column(Integer, primary_key=True, index=True)
    tag                     = Column(String(60), nullable=False, unique=True, index=True)
    nombre                  = Column(String(200), nullable=False)
    descripcion             = Column(Text, nullable=True)

    # Clasificación y jerarquía (ISO 14224 §5)
    categoria_id            = Column(Integer, ForeignKey("loca_categorias.id"), nullable=True)
    clase_equipo            = Column(String(80), nullable=True)
    nivel_jerarquia         = Column(String(20), default="EQUIPO")  # PLANTA, SISTEMA, EQUIPO, COMPONENTE
    padre_id                = Column(Integer, ForeignKey("loca_activos.id"), nullable=True)

    # Ubicación
    sede_id                 = Column(Integer, ForeignKey("loca_sedes.id"), nullable=True)
    espacio_id              = Column(Integer, ForeignKey("loca_espacios.id"), nullable=True)
    edificio                = Column(String(80), nullable=True)
    piso                    = Column(String(20), nullable=True)

    # Estado y criticidad
    estado                  = Column(String(30), default="OPERATIVO")  # OPERATIVO, EN_MANTENIMIENTO, FUERA_SERVICIO, BAJA, CUARENTENA
    criticidad              = Column(String(20), default="ESTANDAR")   # CRITICO, IMPORTANTE, ESTANDAR
    justificacion_criticidad = Column(String(255), nullable=True)

    # Datos técnicos
    fabricante              = Column(String(120), nullable=True)
    marca                   = Column(String(80), nullable=True)
    modelo                  = Column(String(80), nullable=True)
    numero_serie            = Column(String(80), nullable=True)
    numero_parte            = Column(String(80), nullable=True)
    especificaciones        = Column(Text, nullable=True)  # JSON de especificaciones técnicas

    # Datos financieros — IAS 16
    fecha_adquisicion       = Column(Date, nullable=True)
    fecha_puesta_servicio   = Column(Date, nullable=True)
    costo_adquisicion       = Column(Float, nullable=True)
    valor_residual          = Column(Float, default=0)
    vida_util_anos          = Column(Float, nullable=True)
    metodo_depreciacion     = Column(String(30), default="LINEA_RECTA")  # LINEA_RECTA, SALDOS_DECRECIENTES, UNIDADES_PRODUCCION
    modelo_medicion         = Column(String(20), default="COSTO")        # COSTO, REVALUACION
    depreciacion_acumulada  = Column(Float, default=0)
    deterioro_acumulado     = Column(Float, default=0)
    centro_costo            = Column(String(60), nullable=True)

    # Datos de confiabilidad (ISO 14224)
    funcion_requerida       = Column(Text, nullable=True)
    modo_falla_esperado     = Column(String(255), nullable=True)

    # Garantía
    garantia_inicio         = Column(Date, nullable=True)
    garantia_vencimiento    = Column(Date, nullable=True)

    # Baja
    fecha_baja              = Column(Date, nullable=True)
    motivo_baja             = Column(String(255), nullable=True)
    valor_rescate           = Column(Float, nullable=True)

    activo                  = Column(Boolean, default=True)

    categoria   = relationship("LocativaCategoria", back_populates="activos")
    sede        = relationship("LocativaSede", back_populates="activos")
    espacio     = relationship("LocativaEspacio", back_populates="activos")
    documentos  = relationship("LocativaActivoDocumento", back_populates="activo")
    ordenes     = relationship("LocativaOrdenTrabajo", back_populates="activo")
    fallas      = relationship("LocativaRegistroFalla", back_populates="activo")


class LocativaActivoDocumento(Base, TimestampMixin):
    __tablename__ = "loca_activo_documentos"
    id                  = Column(Integer, primary_key=True, index=True)
    activo_id           = Column(Integer, ForeignKey("loca_activos.id"), nullable=False)
    tipo                = Column(String(60), nullable=False)  # MANUAL, CERTIFICADO, PLANO, GARANTIA, FOTO, OTRO
    nombre              = Column(String(200), nullable=False)
    descripcion         = Column(String(255), nullable=True)
    archivo_url         = Column(String(500), nullable=True)
    fecha_documento     = Column(Date, nullable=True)
    fecha_vencimiento   = Column(Date, nullable=True)
    activo              = relationship("LocativaActivo", back_populates="documentos")


# ─── Mantenimiento (ISO 41001, EN 16646, IEC 60300) ───────────────────────────

class LocativaCatalogoTarea(Base, TimestampMixin):
    """Catálogo de tareas de mantenimiento"""
    __tablename__ = "loca_catalogo_tareas"
    id                      = Column(Integer, primary_key=True, index=True)
    codigo                  = Column(String(30), nullable=True)
    nombre                  = Column(String(200), nullable=False)
    tipo                    = Column(String(30), default="PREVENTIVO")  # PREVENTIVO, CORRECTIVO, PREDICTIVO, MEJORATIVO, INSPECCION
    categoria_activo        = Column(String(100), nullable=True)
    descripcion             = Column(Text, nullable=True)
    tiempo_estimado_hrs     = Column(Float, nullable=True)
    epp_requerido           = Column(String(255), nullable=True)
    referencia_normativa    = Column(String(200), nullable=True)  # e.g. "ISO 14224 §9.3"
    criticidad              = Column(String(20), default="MEDIA")
    activo                  = Column(Boolean, default=True)


class LocativaOrdenTrabajo(Base, TimestampMixin, SoftDeleteMixin):
    """Orden de trabajo — ciclo de vida completo"""
    __tablename__ = "loca_ordenes_trabajo"

    id                          = Column(Integer, primary_key=True, index=True)
    numero                      = Column(String(20), nullable=False, unique=True, index=True)
    tipo                        = Column(String(30), default="PREVENTIVO")  # PREVENTIVO, CORRECTIVO, PREDICTIVO, INSPECCION, EMERGENCIA
    activo_id                   = Column(Integer, ForeignKey("loca_activos.id"), nullable=True)
    sede_id                     = Column(Integer, ForeignKey("loca_sedes.id"), nullable=True)
    descripcion                 = Column(Text, nullable=False)
    prioridad                   = Column(String(20), default="MEDIA")   # EMERGENCIA, ALTA, MEDIA, BAJA
    estado                      = Column(String(20), default="ABIERTA") # ABIERTA, ASIGNADA, EN_PROGRESO, CERRADA, CANCELADA, VERIFICADA
    fecha_apertura              = Column(Date, nullable=False)
    fecha_programada            = Column(Date, nullable=True)
    fecha_inicio_real           = Column(Date, nullable=True)
    fecha_cierre                = Column(Date, nullable=True)
    tiempo_estimado_hrs         = Column(Float, nullable=True)
    tiempo_real_hrs             = Column(Float, nullable=True)
    tecnico_id                  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    contratista_id              = Column(Integer, ForeignKey("loca_proveedores.id"), nullable=True)
    requiere_permiso            = Column(Boolean, default=False)
    requiere_parada             = Column(Boolean, default=False)
    tiempo_indisponibilidad_hrs = Column(Float, nullable=True)
    trabajo_realizado           = Column(Text, nullable=True)
    causa_raiz                  = Column(String(200), nullable=True)
    estado_post_intervencion    = Column(String(30), nullable=True)
    costo_mano_obra             = Column(Float, default=0)
    costo_materiales            = Column(Float, default=0)
    costo_externo               = Column(Float, default=0)
    es_capitalizable            = Column(Boolean, default=False)  # IAS 16
    referencia_normativa        = Column(String(200), nullable=True)
    observaciones               = Column(Text, nullable=True)
    creado_por_id               = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    activo      = relationship("LocativaActivo", back_populates="ordenes")
    sede        = relationship("LocativaSede")
    contratista = relationship("LocativaProveedor", back_populates="ordenes")
    checklist   = relationship("LocativaOTChecklist", back_populates="orden", cascade="all, delete-orphan")
    materiales  = relationship("LocativaOTMaterial", back_populates="orden", cascade="all, delete-orphan")


class LocativaOTChecklist(Base, TimestampMixin):
    __tablename__ = "loca_ot_checklist"
    id          = Column(Integer, primary_key=True, index=True)
    orden_id    = Column(Integer, ForeignKey("loca_ordenes_trabajo.id"), nullable=False)
    paso        = Column(Integer, nullable=False, default=1)
    descripcion = Column(String(500), nullable=False)
    completado  = Column(Boolean, default=False)
    observacion = Column(String(255), nullable=True)
    orden       = relationship("LocativaOrdenTrabajo", back_populates="checklist")


class LocativaOTMaterial(Base, TimestampMixin):
    __tablename__ = "loca_ot_materiales"
    id              = Column(Integer, primary_key=True, index=True)
    orden_id        = Column(Integer, ForeignKey("loca_ordenes_trabajo.id"), nullable=False)
    descripcion     = Column(String(200), nullable=False)
    cantidad        = Column(Float, default=1)
    unidad          = Column(String(20), default="UN")
    costo_unitario  = Column(Float, nullable=True)
    costo_total     = Column(Float, nullable=True)
    orden           = relationship("LocativaOrdenTrabajo", back_populates="materiales")


class LocativaRegistroFalla(Base, TimestampMixin):
    """Registro de fallas — ISO 14224 §8"""
    __tablename__ = "loca_registro_fallas"
    id                      = Column(Integer, primary_key=True, index=True)
    activo_id               = Column(Integer, ForeignKey("loca_activos.id"), nullable=False)
    fecha_deteccion         = Column(Date, nullable=False)
    fecha_inicio_falla      = Column(Date, nullable=True)
    modo_falla_id           = Column(Integer, ForeignKey("loca_modos_falla.id"), nullable=True)
    descripcion_falla       = Column(Text, nullable=False)
    causa_raiz              = Column(String(200), nullable=True)
    parte_fallada           = Column(String(150), nullable=True)
    consecuencia            = Column(String(50), default="FALLA_FUNCIONAL_TOTAL")  # SIN_EFECTO, DEGRADACION, PARCIAL, TOTAL, SEGURA
    detectada_por           = Column(String(50), default="REPORTE_USUARIO")        # INSPECCION, ALARMA, VISIBLE, REPORTE_USUARIO
    horas_indisponibilidad  = Column(Float, nullable=True)
    tiempo_respuesta_hrs    = Column(Float, nullable=True)
    tiempo_reparacion_hrs   = Column(Float, nullable=True)
    costo_total             = Column(Float, nullable=True)
    orden_trabajo_id        = Column(Integer, ForeignKey("loca_ordenes_trabajo.id"), nullable=True)
    activo                  = relationship("LocativaActivo", back_populates="fallas")
    modo_falla              = relationship("LocativaModoFalla")


# ─── Gestión de Riesgos (ISO 31000) ───────────────────────────────────────────

class LocativaRiesgo(Base, TimestampMixin):
    """Registro de riesgos — ISO 31000:2018"""
    __tablename__ = "loca_riesgos"
    id              = Column(Integer, primary_key=True, index=True)
    codigo          = Column(String(30), nullable=True, unique=True)
    descripcion     = Column(Text, nullable=False)
    categoria       = Column(String(50), default="OPERACIONAL")  # SEGURIDAD, OPERACIONAL, FINANCIERO, REGULATORIO, AMBIENTAL, REPUTACIONAL
    activo_id       = Column(Integer, ForeignKey("loca_activos.id"), nullable=True)
    sede_id         = Column(Integer, ForeignKey("loca_sedes.id"), nullable=True)
    causas          = Column(Text, nullable=True)
    consecuencias   = Column(Text, nullable=True)
    fuente          = Column(String(20), default="INTERNO")  # INTERNO, EXTERNO
    responsable     = Column(String(120), nullable=True)
    fecha_identificacion    = Column(Date, nullable=True)

    # Análisis de riesgo (probabilidad e impacto 1-5)
    probabilidad            = Column(Integer, nullable=True)
    impacto_personas        = Column(Integer, nullable=True)
    impacto_operacional     = Column(Integer, nullable=True)
    impacto_financiero      = Column(Integer, nullable=True)
    impacto_ambiental       = Column(Integer, nullable=True)
    nivel_inherente         = Column(Integer, nullable=True)   # Probabilidad × max(impactos)
    controles_existentes    = Column(Text, nullable=True)
    nivel_residual          = Column(Integer, nullable=True)
    aceptabilidad           = Column(String(20), nullable=True)  # ACEPTABLE, TOLERABLE, INACEPTABLE

    estado          = Column(String(20), default="ACTIVO")  # ACTIVO, EN_TRATAMIENTO, CERRADO
    ultima_revision = Column(Date, nullable=True)

    tratamientos = relationship("LocativaRiesgoTratamiento", back_populates="riesgo", cascade="all, delete-orphan")


class LocativaRiesgoTratamiento(Base, TimestampMixin):
    __tablename__ = "loca_riesgo_tratamientos"
    id                      = Column(Integer, primary_key=True, index=True)
    riesgo_id               = Column(Integer, ForeignKey("loca_riesgos.id"), nullable=False)
    estrategia              = Column(String(30), default="REDUCIR")  # EVITAR, REDUCIR, TRANSFERIR, ACEPTAR
    descripcion             = Column(Text, nullable=False)
    responsable             = Column(String(120), nullable=True)
    fecha_limite            = Column(Date, nullable=True)
    nivel_residual_objetivo = Column(Integer, nullable=True)
    estado                  = Column(String(20), default="PENDIENTE")  # PENDIENTE, EN_PROGRESO, IMPLEMENTADO, VERIFICADO
    observaciones           = Column(Text, nullable=True)
    riesgo                  = relationship("LocativaRiesgo", back_populates="tratamientos")


# ─── Gestión de Energía (ISO 50001) ────────────────────────────────────────────

class LocativaMedidor(Base, TimestampMixin):
    """Puntos de medición energética"""
    __tablename__ = "loca_medidores"
    id              = Column(Integer, primary_key=True, index=True)
    codigo          = Column(String(60), nullable=False, unique=True)
    nombre          = Column(String(150), nullable=False)
    tipo_energia    = Column(String(30), default="ELECTRICIDAD")  # ELECTRICIDAD, GAS, AGUA, DIESEL, VAPOR
    unidad          = Column(String(20), default="kWh")
    sede_id         = Column(Integer, ForeignKey("loca_sedes.id"), nullable=True)
    espacio_id      = Column(Integer, ForeignKey("loca_espacios.id"), nullable=True)
    activo_id       = Column(Integer, ForeignKey("loca_activos.id"), nullable=True)
    tarifa_unidad   = Column(Float, nullable=True)
    linea_base_mensual = Column(Float, nullable=True)  # Consumo de referencia (EnB)
    activo          = Column(Boolean, default=True)
    lecturas        = relationship("LocativaLecturaEnergia", back_populates="medidor")


class LocativaLecturaEnergia(Base, TimestampMixin):
    __tablename__ = "loca_lecturas_energia"
    id                  = Column(Integer, primary_key=True, index=True)
    medidor_id          = Column(Integer, ForeignKey("loca_medidores.id"), nullable=False)
    fecha               = Column(Date, nullable=False)
    valor_lectura       = Column(Float, nullable=False)
    consumo_periodo     = Column(Float, nullable=True)  # Diferencia con lectura anterior
    costo_periodo       = Column(Float, nullable=True)
    anomalo             = Column(Boolean, default=False)
    observaciones       = Column(String(255), nullable=True)
    registrado_por_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    medidor             = relationship("LocativaMedidor", back_populates="lecturas")
