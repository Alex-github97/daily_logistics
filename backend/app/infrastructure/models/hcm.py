"""
Módulo HCM (Human Capital Management / Gestión Humana) — Modelos de base de datos
Prefijo de tabla: hcm_
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, ForeignKey, Text,
    Date, DateTime, UniqueConstraint, func, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ─── Enumeraciones ─────────────────────────────────────────────────────────────

class TipoDocumentoEnum(str, enum.Enum):
    CC = "CC"
    CE = "CE"
    PA = "PA"
    NIT = "NIT"
    TI = "TI"

class GeneroEnum(str, enum.Enum):
    MASCULINO = "MASCULINO"
    FEMENINO = "FEMENINO"
    NO_BINARIO = "NO_BINARIO"
    PREFIERO_NO_DECIR = "PREFIERO_NO_DECIR"

class EstadoLaboralEnum(str, enum.Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"
    VACACIONES = "VACACIONES"
    INCAPACIDAD = "INCAPACIDAD"
    RETIRADO = "RETIRADO"
    SUSPENSION = "SUSPENSION"

class TipoContratoEnum(str, enum.Enum):
    INDEFINIDO = "INDEFINIDO"
    FIJO = "FIJO"
    OBRA_LABOR = "OBRA_LABOR"
    PRESTACION_SERVICIOS = "PRESTACION_SERVICIOS"
    APRENDIZAJE = "APRENDIZAJE"
    TEMPORAL = "TEMPORAL"

class TipoLicenciaEnum(str, enum.Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"

class TipoVehiculoAutorizadoEnum(str, enum.Enum):
    MOTOCICLETA = "MOTOCICLETA"
    AUTOMOVIL = "AUTOMOVIL"
    CAMIONETA = "CAMIONETA"
    CAMION_RIGIDO = "CAMION_RIGIDO"
    TRACTOCAMION = "TRACTOCAMION"
    DOBLE_TROQUE = "DOBLE_TROQUE"
    ARTICULADO = "ARTICULADO"
    MONTACARGAS = "MONTACARGAS"
    REACH_STACKER = "REACH_STACKER"
    EQUIPO_ESPECIAL = "EQUIPO_ESPECIAL"

class EscalaOperativaEnum(str, enum.Enum):
    URBANA = "URBANA"
    METROPOLITANA = "METROPOLITANA"
    REGIONAL = "REGIONAL"
    NACIONAL = "NACIONAL"
    INTERNACIONAL = "INTERNACIONAL"

class TipoIncapacidadEnum(str, enum.Enum):
    ENFERMEDAD_COMUN = "ENFERMEDAD_COMUN"
    ACCIDENTE_LABORAL = "ACCIDENTE_LABORAL"
    ENFERMEDAD_LABORAL = "ENFERMEDAD_LABORAL"
    MATERNIDAD = "MATERNIDAD"
    PATERNIDAD = "PATERNIDAD"
    RIESGO_PROFESIONAL = "RIESGO_PROFESIONAL"

class EstadoNominaEnum(str, enum.Enum):
    BORRADOR = "BORRADOR"
    EN_PROCESO = "EN_PROCESO"
    CERRADA = "CERRADA"
    PAGADA = "PAGADA"

class TipoEvaluacionEnum(str, enum.Enum):
    NOVENTA = "90"
    CIENTO_OCHENTA = "180"
    TRESCIENTOS_SESENTA = "360"

class EstadoVacanteEnum(str, enum.Enum):
    ABIERTA = "ABIERTA"
    EN_PROCESO = "EN_PROCESO"
    CERRADA = "CERRADA"
    CANCELADA = "CANCELADA"

class EstadoPostulacionEnum(str, enum.Enum):
    NUEVA = "NUEVA"
    EN_REVISION = "EN_REVISION"
    ENTREVISTA = "ENTREVISTA"
    CONTRATADO = "CONTRATADO"
    DESCARTADO = "DESCARTADO"

class TipoSSTEnum(str, enum.Enum):
    ACCIDENTE = "ACCIDENTE"
    INCIDENTE = "INCIDENTE"
    CASI_ACCIDENTE = "CASI_ACCIDENTE"

class EstadoDocConductorEnum(str, enum.Enum):
    VIGENTE = "VIGENTE"
    POR_VENCER = "POR_VENCER"
    VENCIDO = "VENCIDO"

class TipoNovedadEnum(str, enum.Enum):
    HORA_EXTRA = "HORA_EXTRA"
    RECARGO_NOCTURNO = "RECARGO_NOCTURNO"
    DOMINICAL = "DOMINICAL"
    FESTIVO = "FESTIVO"
    BONIFICACION = "BONIFICACION"
    COMISION = "COMISION"
    VIATICO = "VIATICO"
    DESCUENTO = "DESCUENTO"
    EMBARGO = "EMBARGO"
    RETENCION = "RETENCION"
    OTRO = "OTRO"

class EstadoCapacitacionEnum(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    EN_CURSO = "EN_CURSO"
    COMPLETADO = "COMPLETADO"
    VENCIDO = "VENCIDO"


# ─── 1. Empresa ────────────────────────────────────────────────────────────────

class HCMEmpresa(Base, TimestampMixin):
    __tablename__ = "hcm_empresa"

    id       = Column(Integer, primary_key=True, index=True)
    nombre   = Column(String(200), nullable=False)
    nit      = Column(String(20), nullable=False, unique=True, index=True)
    pais     = Column(String(100), nullable=False, default="Colombia")
    ciudad   = Column(String(100), nullable=False)
    telefono = Column(String(30), nullable=True)
    email    = Column(String(200), nullable=True)
    activo   = Column(Boolean, default=True)

    sedes          = relationship("HCMSede", back_populates="empresa")
    areas          = relationship("HCMArea", back_populates="empresa")
    cargos         = relationship("HCMCargo", back_populates="empresa")
    centros_costo  = relationship("HCMCentroCosto", back_populates="empresa")
    colaboradores  = relationship("HCMColaborador", back_populates="empresa")
    nomina_periodos = relationship("HCMNominaPeriodo", back_populates="empresa")
    vacantes       = relationship("HCMVacante", back_populates="empresa")
    capacitaciones = relationship("HCMCapacitacion", back_populates="empresa")
    sst_incidentes = relationship("HCMSSTIncidente", back_populates="empresa")
    sst_riesgos    = relationship("HCMSSTRiesgo", back_populates="empresa")
    sst_inspecciones = relationship("HCMSSTInspeccion", back_populates="empresa")
    kpis_diarios   = relationship("HCMKPIDiario", back_populates="empresa")


# ─── 2. Sede ──────────────────────────────────────────────────────────────────

class HCMSede(Base, TimestampMixin):
    __tablename__ = "hcm_sede"

    id           = Column(Integer, primary_key=True, index=True)
    empresa_id   = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    nombre       = Column(String(200), nullable=False)
    ciudad       = Column(String(100), nullable=False)
    departamento = Column(String(100), nullable=False)
    pais         = Column(String(100), nullable=False, default="Colombia")
    direccion    = Column(String(300), nullable=True)
    telefono     = Column(String(30), nullable=True)
    activo       = Column(Boolean, default=True)

    empresa      = relationship("HCMEmpresa", back_populates="sedes")
    colaboradores = relationship("HCMColaborador", back_populates="sede")
    sst_incidentes = relationship("HCMSSTIncidente", back_populates="sede")
    sst_inspecciones = relationship("HCMSSTInspeccion", back_populates="sede")


# ─── 3. Área ──────────────────────────────────────────────────────────────────

class HCMArea(Base, TimestampMixin):
    __tablename__ = "hcm_area"

    id            = Column(Integer, primary_key=True, index=True)
    empresa_id    = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    nombre        = Column(String(200), nullable=False)
    descripcion   = Column(Text, nullable=True)
    area_padre_id = Column(Integer, ForeignKey("hcm_area.id"), nullable=True)
    activo        = Column(Boolean, default=True)

    empresa      = relationship("HCMEmpresa", back_populates="areas")
    area_padre   = relationship("HCMArea", remote_side="HCMArea.id", foreign_keys=[area_padre_id])
    sub_areas    = relationship("HCMArea", back_populates="area_padre", foreign_keys=[area_padre_id])
    cargos       = relationship("HCMCargo", back_populates="area")
    colaboradores = relationship("HCMColaborador", back_populates="area")
    sst_riesgos  = relationship("HCMSSTRiesgo", back_populates="area")


# ─── 4. Cargo ─────────────────────────────────────────────────────────────────

class HCMCargo(Base, TimestampMixin):
    __tablename__ = "hcm_cargo"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    area_id         = Column(Integer, ForeignKey("hcm_area.id"), nullable=True)
    nombre          = Column(String(200), nullable=False)
    nivel           = Column(String(50), nullable=True)
    descripcion     = Column(Text, nullable=True)
    salario_minimo  = Column(Float, nullable=True)
    salario_maximo  = Column(Float, nullable=True)
    activo          = Column(Boolean, default=True)

    empresa      = relationship("HCMEmpresa", back_populates="cargos")
    area         = relationship("HCMArea", back_populates="cargos")
    colaboradores = relationship("HCMColaborador", back_populates="cargo")
    vacantes     = relationship("HCMVacante", back_populates="cargo")


# ─── 5. Centro de Costo ───────────────────────────────────────────────────────

class HCMCentroCosto(Base, TimestampMixin):
    __tablename__ = "hcm_centro_costo"

    id         = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    codigo     = Column(String(20), nullable=False)
    nombre     = Column(String(200), nullable=False)
    activo     = Column(Boolean, default=True)

    empresa      = relationship("HCMEmpresa", back_populates="centros_costo")
    colaboradores = relationship("HCMColaborador", back_populates="centro_costo")


# ─── 6. Colaborador ───────────────────────────────────────────────────────────

class HCMColaborador(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "hcm_colaborador"

    id                 = Column(Integer, primary_key=True, index=True)

    # Datos personales
    tipo_documento     = Column(SAEnum(TipoDocumentoEnum, name="hcm_tipo_documento_enum"), nullable=False)
    numero_documento   = Column(String(30), nullable=False, unique=True, index=True)
    nombres            = Column(String(150), nullable=False)
    apellidos          = Column(String(150), nullable=False)
    fecha_nacimiento   = Column(Date, nullable=True)
    genero             = Column(SAEnum(GeneroEnum, name="hcm_genero_enum"), nullable=True)
    nacionalidad       = Column(String(100), nullable=True)
    estado_civil       = Column(String(50), nullable=True)
    direccion          = Column(String(300), nullable=True)
    ciudad             = Column(String(100), nullable=True)
    departamento       = Column(String(100), nullable=True)
    pais               = Column(String(100), nullable=True, default="Colombia")
    telefono           = Column(String(30), nullable=True)
    email              = Column(String(200), nullable=True)
    foto_url           = Column(String(500), nullable=True)

    # Datos laborales
    codigo_empleado    = Column(String(20), nullable=False, unique=True, index=True)
    empresa_id         = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    sede_id            = Column(Integer, ForeignKey("hcm_sede.id"), nullable=True)
    area_id            = Column(Integer, ForeignKey("hcm_area.id"), nullable=True)
    cargo_id           = Column(Integer, ForeignKey("hcm_cargo.id"), nullable=True)
    centro_costo_id    = Column(Integer, ForeignKey("hcm_centro_costo.id"), nullable=True)
    jefe_id            = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=True)
    tipo_contrato      = Column(SAEnum(TipoContratoEnum, name="hcm_tipo_contrato_enum"), nullable=True)
    fecha_ingreso      = Column(Date, nullable=True)
    fecha_retiro       = Column(Date, nullable=True)
    estado_laboral     = Column(SAEnum(EstadoLaboralEnum, name="hcm_estado_laboral_enum"), nullable=False, default=EstadoLaboralEnum.ACTIVO)

    # Datos salariales
    salario_base          = Column(Float, nullable=False, default=0)
    tipo_salario          = Column(String(50), nullable=True)
    auxilio_transporte    = Column(Float, nullable=False, default=0)
    bonificaciones_fijas  = Column(Float, nullable=False, default=0)

    # Vínculo con sistema de autenticación (opcional)
    usuario_id         = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    # Relaciones
    empresa      = relationship("HCMEmpresa", back_populates="colaboradores")
    sede         = relationship("HCMSede", back_populates="colaboradores")
    area         = relationship("HCMArea", back_populates="colaboradores")
    cargo        = relationship("HCMCargo", back_populates="colaboradores")
    centro_costo = relationship("HCMCentroCosto", back_populates="colaboradores")
    jefe         = relationship("HCMColaborador", remote_side="HCMColaborador.id", foreign_keys=[jefe_id])
    subordinados = relationship("HCMColaborador", back_populates="jefe", foreign_keys=[jefe_id])
    usuario      = relationship("Usuario", foreign_keys=[usuario_id])

    historial        = relationship("HCMColaboradorHistorial", back_populates="colaborador")
    contratos        = relationship("HCMContrato", back_populates="colaborador")
    conductor        = relationship("HCMConductor", back_populates="colaborador", uselist=False)
    nomina_detalles  = relationship("HCMNominaDetalle", back_populates="colaborador")
    novedades        = relationship("HCMNovedad", back_populates="colaborador")
    liquidacion      = relationship("HCMLiquidacion", back_populates="colaborador", uselist=False)
    incapacidades    = relationship("HCMIncapacidad", back_populates="colaborador")
    vacaciones       = relationship("HCMVacacion", back_populates="colaborador")
    evaluaciones     = relationship("HCMEvaluacion", back_populates="colaborador", foreign_keys="HCMEvaluacion.colaborador_id")
    evaluaciones_como_evaluador = relationship("HCMEvaluacion", back_populates="evaluador", foreign_keys="HCMEvaluacion.evaluador_id")
    capacitaciones   = relationship("HCMColaboradorCapacitacion", back_populates="colaborador")
    sst_incidentes   = relationship("HCMSSTIncidente", back_populates="colaborador")
    sst_riesgos_responsable = relationship("HCMSSTRiesgo", back_populates="responsable")
    sst_inspecciones_inspector = relationship("HCMSSTInspeccion", back_populates="inspector")


# ─── 7. Historial de Colaborador ──────────────────────────────────────────────

class HCMColaboradorHistorial(Base):
    __tablename__ = "hcm_colaborador_historial"

    id              = Column(Integer, primary_key=True, index=True)
    colaborador_id  = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)
    campo           = Column(String(100), nullable=False)
    valor_anterior  = Column(Text, nullable=True)
    valor_nuevo     = Column(Text, nullable=True)
    usuario_cambio  = Column(String(100), nullable=True)
    fecha_cambio    = Column(DateTime(timezone=True), nullable=False, default=func.now())

    colaborador = relationship("HCMColaborador", back_populates="historial")


# ─── 8. Contrato ──────────────────────────────────────────────────────────────

class HCMContrato(Base, TimestampMixin):
    __tablename__ = "hcm_contrato"

    id              = Column(Integer, primary_key=True, index=True)
    colaborador_id  = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)
    tipo_contrato   = Column(SAEnum(TipoContratoEnum, name="hcm_contrato_tipo_enum"), nullable=False)
    fecha_inicio    = Column(Date, nullable=False)
    fecha_fin       = Column(Date, nullable=True)
    salario         = Column(Float, nullable=False)
    estado          = Column(String(50), nullable=False, default="ACTIVO")
    notas           = Column(Text, nullable=True)
    archivo_url     = Column(String(500), nullable=True)

    colaborador = relationship("HCMColaborador", back_populates="contratos")


# ─── 9. Conductor ─────────────────────────────────────────────────────────────

class HCMConductor(Base, TimestampMixin):
    __tablename__ = "hcm_conductor"

    id                         = Column(Integer, primary_key=True, index=True)
    colaborador_id             = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False, unique=True)
    num_licencia               = Column(String(50), nullable=False, unique=True)
    tipo_licencia              = Column(SAEnum(TipoLicenciaEnum, name="hcm_tipo_licencia_enum"), nullable=False)
    fecha_expedicion_licencia  = Column(Date, nullable=False)
    fecha_vencimiento_licencia = Column(Date, nullable=False)
    restricciones              = Column(Text, nullable=True)
    anos_experiencia           = Column(Integer, nullable=False, default=0)
    certificaciones            = Column(Text, nullable=True)
    activo_conduccion          = Column(Boolean, default=True)

    colaborador       = relationship("HCMColaborador", back_populates="conductor")
    vehiculos_tipos   = relationship("HCMConductorVehiculoTipo", back_populates="conductor")
    coberturas        = relationship("HCMConductorCobertura", back_populates="conductor")
    documentos        = relationship("HCMConductorDocumento", back_populates="conductor")
    accidentes        = relationship("HCMConductorAccidente", back_populates="conductor")


# ─── 10. Conductor — Tipo de Vehículo Autorizado ──────────────────────────────

class HCMConductorVehiculoTipo(Base):
    __tablename__ = "hcm_conductor_vehiculo_tipo"
    __table_args__ = (UniqueConstraint("conductor_id", "tipo_vehiculo"),)

    id           = Column(Integer, primary_key=True, index=True)
    conductor_id = Column(Integer, ForeignKey("hcm_conductor.id"), nullable=False)
    tipo_vehiculo = Column(SAEnum(TipoVehiculoAutorizadoEnum, name="hcm_tipo_vehiculo_auth_enum"), nullable=False)

    conductor = relationship("HCMConductor", back_populates="vehiculos_tipos")


# ─── 11. Conductor — Cobertura Operativa ──────────────────────────────────────

class HCMConductorCobertura(Base):
    __tablename__ = "hcm_conductor_cobertura"
    __table_args__ = (UniqueConstraint("conductor_id", "escala"),)

    id           = Column(Integer, primary_key=True, index=True)
    conductor_id = Column(Integer, ForeignKey("hcm_conductor.id"), nullable=False)
    escala       = Column(SAEnum(EscalaOperativaEnum, name="hcm_escala_operativa_enum"), nullable=False)

    conductor = relationship("HCMConductor", back_populates="coberturas")


# ─── 12. Conductor — Documento ────────────────────────────────────────────────

class HCMConductorDocumento(Base, TimestampMixin):
    __tablename__ = "hcm_conductor_documento"

    id                = Column(Integer, primary_key=True, index=True)
    conductor_id      = Column(Integer, ForeignKey("hcm_conductor.id"), nullable=False)
    tipo_documento    = Column(String(100), nullable=False)
    numero            = Column(String(100), nullable=True)
    fecha_emision     = Column(Date, nullable=True)
    fecha_vencimiento = Column(Date, nullable=True)
    archivo_url       = Column(String(500), nullable=True)
    estado            = Column(SAEnum(EstadoDocConductorEnum, name="hcm_estado_doc_conductor_enum"), nullable=False, default=EstadoDocConductorEnum.VIGENTE)
    notas             = Column(Text, nullable=True)

    conductor = relationship("HCMConductor", back_populates="documentos")


# ─── 13. Conductor — Accidente ────────────────────────────────────────────────

class HCMConductorAccidente(Base, TimestampMixin):
    __tablename__ = "hcm_conductor_accidente"

    id               = Column(Integer, primary_key=True, index=True)
    conductor_id     = Column(Integer, ForeignKey("hcm_conductor.id"), nullable=False)
    fecha            = Column(Date, nullable=False)
    descripcion      = Column(Text, nullable=False)
    tipo             = Column(String(50), nullable=False)
    consecuencias    = Column(Text, nullable=True)
    dias_incapacidad = Column(Integer, nullable=False, default=0)
    archivo_url      = Column(String(500), nullable=True)

    conductor = relationship("HCMConductor", back_populates="accidentes")


# ─── 14. Nómina — Período ─────────────────────────────────────────────────────

class HCMNominaPeriodo(Base, TimestampMixin):
    __tablename__ = "hcm_nomina_periodo"

    id               = Column(Integer, primary_key=True, index=True)
    empresa_id       = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    nombre           = Column(String(100), nullable=False)
    fecha_inicio     = Column(Date, nullable=False)
    fecha_fin        = Column(Date, nullable=False)
    estado           = Column(SAEnum(EstadoNominaEnum, name="hcm_estado_nomina_enum"), nullable=False, default=EstadoNominaEnum.BORRADOR)
    total_devengado  = Column(Float, nullable=False, default=0)
    total_deducido   = Column(Float, nullable=False, default=0)
    total_neto       = Column(Float, nullable=False, default=0)
    empleados_count  = Column(Integer, nullable=False, default=0)

    @property
    def num_empleados(self) -> int:
        """El nombre con el que la pantalla lee este mismo dato.

        Va como propiedad del modelo y no como cálculo suelto en cada endpoint
        para que cualquier respuesta que serialice un período lo traiga, sin que
        nadie tenga que acordarse de agregarlo.
        """
        return self.empleados_count or 0
    notas            = Column(Text, nullable=True)

    empresa  = relationship("HCMEmpresa", back_populates="nomina_periodos")
    detalles = relationship("HCMNominaDetalle", back_populates="periodo")
    novedades = relationship("HCMNovedad", back_populates="periodo")


# ─── 15. Nómina — Detalle ─────────────────────────────────────────────────────

class HCMNominaDetalle(Base, TimestampMixin):
    __tablename__ = "hcm_nomina_detalle"
    __table_args__ = (UniqueConstraint("periodo_id", "colaborador_id"),)

    id                  = Column(Integer, primary_key=True, index=True)
    periodo_id          = Column(Integer, ForeignKey("hcm_nomina_periodo.id"), nullable=False)
    colaborador_id      = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)

    # Devengados
    salario_base        = Column(Float, nullable=False, default=0)
    horas_extras        = Column(Float, nullable=False, default=0)
    recargo_nocturno    = Column(Float, nullable=False, default=0)
    dominicales         = Column(Float, nullable=False, default=0)
    festivos            = Column(Float, nullable=False, default=0)
    bonificaciones      = Column(Float, nullable=False, default=0)
    comisiones          = Column(Float, nullable=False, default=0)
    viaticos            = Column(Float, nullable=False, default=0)
    auxilio_transporte  = Column(Float, nullable=False, default=0)
    otros_devengados    = Column(Float, nullable=False, default=0)
    total_devengado     = Column(Float, nullable=False, default=0)

    # Deducciones
    salud               = Column(Float, nullable=False, default=0)
    pension             = Column(Float, nullable=False, default=0)
    fondo_solidaridad   = Column(Float, nullable=False, default=0)
    retencion_fuente    = Column(Float, nullable=False, default=0)
    embargo             = Column(Float, nullable=False, default=0)
    otros_descuentos    = Column(Float, nullable=False, default=0)
    total_deducido      = Column(Float, nullable=False, default=0)

    neto_pagado         = Column(Float, nullable=False, default=0)

    periodo     = relationship("HCMNominaPeriodo", back_populates="detalles")
    colaborador = relationship("HCMColaborador", back_populates="nomina_detalles")


# ─── 16. Novedad ──────────────────────────────────────────────────────────────

class HCMNovedad(Base, TimestampMixin):
    __tablename__ = "hcm_novedad"

    id              = Column(Integer, primary_key=True, index=True)
    colaborador_id  = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)
    periodo_id      = Column(Integer, ForeignKey("hcm_nomina_periodo.id"), nullable=True)
    tipo_novedad    = Column(SAEnum(TipoNovedadEnum, name="hcm_tipo_novedad_enum"), nullable=False)
    descripcion     = Column(String(300), nullable=True)
    valor           = Column(Float, nullable=False)
    fecha           = Column(Date, nullable=False)
    aprobado_por    = Column(String(100), nullable=True)
    notas           = Column(Text, nullable=True)

    colaborador = relationship("HCMColaborador", back_populates="novedades")
    periodo     = relationship("HCMNominaPeriodo", back_populates="novedades")


# ─── 17. Liquidación ──────────────────────────────────────────────────────────

class HCMLiquidacion(Base, TimestampMixin):
    __tablename__ = "hcm_liquidacion"

    id                      = Column(Integer, primary_key=True, index=True)
    colaborador_id          = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False, unique=True)
    fecha_liquidacion       = Column(Date, nullable=False)
    motivo_retiro           = Column(String(200), nullable=False)
    dias_trabajados         = Column(Integer, nullable=False, default=0)
    prima                   = Column(Float, nullable=False, default=0)
    cesantias               = Column(Float, nullable=False, default=0)
    intereses_cesantias     = Column(Float, nullable=False, default=0)
    vacaciones_compensadas  = Column(Float, nullable=False, default=0)
    indemnizacion           = Column(Float, nullable=False, default=0)
    otros_conceptos         = Column(Float, nullable=False, default=0)
    deducciones             = Column(Float, nullable=False, default=0)
    total_pagar             = Column(Float, nullable=False, default=0)
    estado                  = Column(String(50), nullable=False, default="PENDIENTE")
    notas                   = Column(Text, nullable=True)

    colaborador = relationship("HCMColaborador", back_populates="liquidacion")


# ─── 18. Incapacidad ──────────────────────────────────────────────────────────

class HCMIncapacidad(Base, TimestampMixin):
    __tablename__ = "hcm_incapacidad"

    id               = Column(Integer, primary_key=True, index=True)
    colaborador_id   = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)
    tipo_incapacidad = Column(SAEnum(TipoIncapacidadEnum, name="hcm_tipo_incapacidad_enum"), nullable=False)
    diagnostico      = Column(String(300), nullable=True)
    entidad_emisora  = Column(String(200), nullable=True)
    fecha_inicio     = Column(Date, nullable=False)
    fecha_fin        = Column(Date, nullable=False)
    dias             = Column(Integer, nullable=False, default=0)
    costo_empresa    = Column(Float, nullable=False, default=0)
    costo_eps        = Column(Float, nullable=False, default=0)
    archivo_url      = Column(String(500), nullable=True)
    estado           = Column(String(50), nullable=False, default="ACTIVA")
    notas            = Column(Text, nullable=True)

    colaborador = relationship("HCMColaborador", back_populates="incapacidades")


# ─── 19. Vacación ─────────────────────────────────────────────────────────────

class HCMVacacion(Base, TimestampMixin):
    __tablename__ = "hcm_vacacion"

    id                 = Column(Integer, primary_key=True, index=True)
    colaborador_id     = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)
    fecha_inicio       = Column(Date, nullable=False)
    fecha_fin          = Column(Date, nullable=False)
    dias_disfrutados   = Column(Integer, nullable=False, default=0)
    tipo               = Column(String(50), nullable=False, default="DISFRUTE")
    estado             = Column(String(50), nullable=False, default="PENDIENTE")
    aprobado_por       = Column(String(100), nullable=True)
    notas              = Column(Text, nullable=True)

    colaborador = relationship("HCMColaborador", back_populates="vacaciones")


# ─── 20. Vacante ──────────────────────────────────────────────────────────────

class HCMVacante(Base, TimestampMixin):
    __tablename__ = "hcm_vacante"

    id             = Column(Integer, primary_key=True, index=True)
    empresa_id     = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    cargo_id       = Column(Integer, ForeignKey("hcm_cargo.id"), nullable=True)
    titulo         = Column(String(200), nullable=False)
    num_vacantes   = Column(Integer, nullable=False, default=1)
    descripcion    = Column(Text, nullable=True)
    requisitos     = Column(Text, nullable=True)
    salario_min    = Column(Float, nullable=True)
    salario_max    = Column(Float, nullable=True)
    fecha_apertura = Column(Date, nullable=False)
    fecha_cierre   = Column(Date, nullable=True)
    estado         = Column(SAEnum(EstadoVacanteEnum, name="hcm_estado_vacante_enum"), nullable=False, default=EstadoVacanteEnum.ABIERTA)
    tipo_contrato  = Column(SAEnum(TipoContratoEnum, name="hcm_vacante_tipo_contrato_enum"), nullable=True)
    modalidad      = Column(String(50), nullable=True)

    empresa      = relationship("HCMEmpresa", back_populates="vacantes")
    cargo        = relationship("HCMCargo", back_populates="vacantes")
    postulaciones = relationship("HCMPostulacion", back_populates="vacante")


# ─── 21. Postulación ──────────────────────────────────────────────────────────

class HCMPostulacion(Base, TimestampMixin):
    __tablename__ = "hcm_postulacion"

    id                 = Column(Integer, primary_key=True, index=True)
    vacante_id         = Column(Integer, ForeignKey("hcm_vacante.id"), nullable=False)
    nombres            = Column(String(150), nullable=False)
    apellidos          = Column(String(150), nullable=False)
    email              = Column(String(200), nullable=False)
    telefono           = Column(String(30), nullable=True)
    cv_url             = Column(String(500), nullable=True)
    fecha_postulacion  = Column(Date, nullable=False)
    estado             = Column(SAEnum(EstadoPostulacionEnum, name="hcm_estado_postulacion_enum"), nullable=False, default=EstadoPostulacionEnum.NUEVA)
    puntuacion         = Column(Float, nullable=True)
    notas              = Column(Text, nullable=True)

    vacante      = relationship("HCMVacante", back_populates="postulaciones")
    entrevistas  = relationship("HCMEntrevista", back_populates="postulacion")


# ─── 22. Entrevista ───────────────────────────────────────────────────────────

class HCMEntrevista(Base, TimestampMixin):
    __tablename__ = "hcm_entrevista"

    id              = Column(Integer, primary_key=True, index=True)
    postulacion_id  = Column(Integer, ForeignKey("hcm_postulacion.id"), nullable=False)
    fecha           = Column(DateTime(timezone=True), nullable=False)
    tipo            = Column(String(50), nullable=False)
    entrevistador   = Column(String(150), nullable=False)
    resultado       = Column(String(50), nullable=True)
    calificacion    = Column(Float, nullable=True)
    notas           = Column(Text, nullable=True)

    postulacion = relationship("HCMPostulacion", back_populates="entrevistas")


# ─── 23. Evaluación ───────────────────────────────────────────────────────────

class HCMEvaluacion(Base, TimestampMixin):
    __tablename__ = "hcm_evaluacion"

    id                 = Column(Integer, primary_key=True, index=True)
    colaborador_id     = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)
    periodo            = Column(String(50), nullable=False)
    tipo_evaluacion    = Column(SAEnum(TipoEvaluacionEnum, name="hcm_tipo_evaluacion_enum"), nullable=False)
    evaluador_id       = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=True)
    fecha              = Column(Date, nullable=False)
    calificacion_total = Column(Float, nullable=True)
    estado             = Column(String(50), nullable=False, default="PENDIENTE")
    notas              = Column(Text, nullable=True)

    colaborador = relationship("HCMColaborador", back_populates="evaluaciones", foreign_keys=[colaborador_id])
    evaluador   = relationship("HCMColaborador", back_populates="evaluaciones_como_evaluador", foreign_keys=[evaluador_id])
    detalles    = relationship("HCMEvaluacionDetalle", back_populates="evaluacion")


# ─── 24. Evaluación — Detalle ─────────────────────────────────────────────────

class HCMEvaluacionDetalle(Base):
    __tablename__ = "hcm_evaluacion_detalle"

    id            = Column(Integer, primary_key=True, index=True)
    evaluacion_id = Column(Integer, ForeignKey("hcm_evaluacion.id"), nullable=False)
    criterio      = Column(String(200), nullable=False)
    competencia   = Column(String(200), nullable=True)
    calificacion  = Column(Float, nullable=False, default=0)
    peso          = Column(Float, nullable=False, default=1.0)
    observacion   = Column(Text, nullable=True)

    evaluacion = relationship("HCMEvaluacion", back_populates="detalles")


# ─── 25. Capacitación ─────────────────────────────────────────────────────────

class HCMCapacitacion(Base, TimestampMixin):
    __tablename__ = "hcm_capacitacion"

    id                 = Column(Integer, primary_key=True, index=True)
    empresa_id         = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    nombre             = Column(String(200), nullable=False)
    descripcion        = Column(Text, nullable=True)
    tipo               = Column(String(50), nullable=False)
    duracion_horas     = Column(Float, nullable=False, default=0)
    instructor         = Column(String(200), nullable=True)
    modalidad          = Column(String(50), nullable=True)
    fecha_inicio       = Column(Date, nullable=True)
    fecha_fin          = Column(Date, nullable=True)
    obligatoria        = Column(Boolean, nullable=False, default=False)
    aplica_conductores = Column(Boolean, nullable=False, default=False)
    activo             = Column(Boolean, nullable=False, default=True)

    empresa      = relationship("HCMEmpresa", back_populates="capacitaciones")
    asignaciones = relationship("HCMColaboradorCapacitacion", back_populates="capacitacion")


# ─── 26. Colaborador — Capacitación ──────────────────────────────────────────

class HCMColaboradorCapacitacion(Base, TimestampMixin):
    __tablename__ = "hcm_colaborador_capacitacion"
    __table_args__ = (UniqueConstraint("colaborador_id", "capacitacion_id"),)

    id               = Column(Integer, primary_key=True, index=True)
    colaborador_id   = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=False)
    capacitacion_id  = Column(Integer, ForeignKey("hcm_capacitacion.id"), nullable=False)
    estado           = Column(SAEnum(EstadoCapacitacionEnum, name="hcm_estado_capacitacion_enum"), nullable=False, default=EstadoCapacitacionEnum.PENDIENTE)
    fecha_completado = Column(Date, nullable=True)
    calificacion     = Column(Float, nullable=True)
    certificado_url  = Column(String(500), nullable=True)
    fecha_vencimiento = Column(Date, nullable=True)
    notas            = Column(Text, nullable=True)

    colaborador  = relationship("HCMColaborador", back_populates="capacitaciones")
    capacitacion = relationship("HCMCapacitacion", back_populates="asignaciones")


# ─── 27. SST — Incidente ──────────────────────────────────────────────────────

class HCMSSTIncidente(Base, TimestampMixin):
    __tablename__ = "hcm_sst_incidente"

    id                   = Column(Integer, primary_key=True, index=True)
    empresa_id           = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    sede_id              = Column(Integer, ForeignKey("hcm_sede.id"), nullable=True)
    colaborador_id       = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=True)
    fecha                = Column(Date, nullable=False)
    tipo_sst             = Column(SAEnum(TipoSSTEnum, name="hcm_tipo_sst_enum"), nullable=False)
    descripcion          = Column(Text, nullable=False)
    causa                = Column(Text, nullable=True)
    consecuencias        = Column(Text, nullable=True)
    dias_incapacidad     = Column(Integer, nullable=False, default=0)
    investigado          = Column(Boolean, nullable=False, default=False)
    medidas_correctivas  = Column(Text, nullable=True)
    estado               = Column(String(50), nullable=False, default="ABIERTO")
    archivo_url          = Column(String(500), nullable=True)

    empresa      = relationship("HCMEmpresa", back_populates="sst_incidentes")
    sede         = relationship("HCMSede", back_populates="sst_incidentes")
    colaborador  = relationship("HCMColaborador", back_populates="sst_incidentes")


# ─── 28. SST — Riesgo ─────────────────────────────────────────────────────────

class HCMSSTRiesgo(Base, TimestampMixin):
    __tablename__ = "hcm_sst_riesgo"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    area_id         = Column(Integer, ForeignKey("hcm_area.id"), nullable=True)
    fuente          = Column(String(200), nullable=False)
    descripcion     = Column(Text, nullable=False)
    probabilidad    = Column(Integer, nullable=False)
    impacto         = Column(Integer, nullable=False)
    nivel_riesgo    = Column(Integer, nullable=False, default=0)
    control         = Column(Text, nullable=True)
    responsable_id  = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=True)
    fecha_revision  = Column(Date, nullable=True)
    estado          = Column(String(50), nullable=False, default="ACTIVO")

    empresa     = relationship("HCMEmpresa", back_populates="sst_riesgos")
    area        = relationship("HCMArea", back_populates="sst_riesgos")
    responsable = relationship("HCMColaborador", back_populates="sst_riesgos_responsable")


# ─── 29. SST — Inspección ─────────────────────────────────────────────────────

class HCMSSTInspeccion(Base, TimestampMixin):
    __tablename__ = "hcm_sst_inspeccion"

    id           = Column(Integer, primary_key=True, index=True)
    empresa_id   = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    sede_id      = Column(Integer, ForeignKey("hcm_sede.id"), nullable=True)
    fecha        = Column(Date, nullable=False)
    tipo         = Column(String(100), nullable=False)
    inspector_id = Column(Integer, ForeignKey("hcm_colaborador.id"), nullable=True)
    hallazgos    = Column(Text, nullable=True)
    acciones     = Column(Text, nullable=True)
    estado       = Column(String(50), nullable=False, default="PENDIENTE")
    archivo_url  = Column(String(500), nullable=True)

    empresa   = relationship("HCMEmpresa", back_populates="sst_inspecciones")
    sede      = relationship("HCMSede", back_populates="sst_inspecciones")
    inspector = relationship("HCMColaborador", back_populates="sst_inspecciones_inspector")


# ─── 30. KPI Diario ───────────────────────────────────────────────────────────

class HCMKPIDiario(Base, TimestampMixin):
    __tablename__ = "hcm_kpi_diario"
    __table_args__ = (UniqueConstraint("empresa_id", "fecha"),)

    id                              = Column(Integer, primary_key=True, index=True)
    empresa_id                      = Column(Integer, ForeignKey("hcm_empresa.id"), nullable=False)
    fecha                           = Column(Date, nullable=False)
    headcount_total                 = Column(Integer, nullable=False, default=0)
    headcount_activo                = Column(Integer, nullable=False, default=0)
    headcount_retirado              = Column(Integer, nullable=False, default=0)
    nuevos_ingresos                 = Column(Integer, nullable=False, default=0)
    rotacion_mensual                = Column(Float, nullable=False, default=0.0)
    conductores_activos             = Column(Integer, nullable=False, default=0)
    conductores_licencias_por_vencer = Column(Integer, nullable=False, default=0)
    ausentismo_rate                 = Column(Float, nullable=False, default=0.0)
    costo_nomina_mes                = Column(Float, nullable=False, default=0.0)

    empresa = relationship("HCMEmpresa", back_populates="kpis_diarios")
