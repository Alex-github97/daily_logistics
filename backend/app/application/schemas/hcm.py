"""
Módulo HCM (Human Capital Management) — Schemas Pydantic v2
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


# ─── Empresa ───────────────────────────────────────────────────────────────────

class HCMEmpresaCreate(BaseModel):
    nombre: str
    nit: str
    pais: str = "Colombia"
    ciudad: str
    telefono: Optional[str] = None
    email: Optional[str] = None

class HCMEmpresaUpdate(BaseModel):
    nombre: Optional[str] = None
    nit: Optional[str] = None
    pais: Optional[str] = None
    ciudad: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    activo: Optional[bool] = None

class HCMEmpresaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    nit: str
    pais: str
    ciudad: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── Sede ──────────────────────────────────────────────────────────────────────

class HCMSedeCreate(BaseModel):
    empresa_id: int
    nombre: str
    ciudad: str
    departamento: str
    pais: str = "Colombia"
    direccion: Optional[str] = None
    telefono: Optional[str] = None

class HCMSedeUpdate(BaseModel):
    nombre: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    pais: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    activo: Optional[bool] = None

class HCMSedeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    nombre: str
    ciudad: str
    departamento: str
    pais: str
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── Área ──────────────────────────────────────────────────────────────────────

class HCMAreaCreate(BaseModel):
    empresa_id: int
    nombre: str
    descripcion: Optional[str] = None
    area_padre_id: Optional[int] = None

class HCMAreaUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    area_padre_id: Optional[int] = None
    activo: Optional[bool] = None

class HCMAreaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    nombre: str
    descripcion: Optional[str] = None
    area_padre_id: Optional[int] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── Cargo ─────────────────────────────────────────────────────────────────────

class HCMCargoCreate(BaseModel):
    empresa_id: int
    area_id: Optional[int] = None
    nombre: str
    nivel: Optional[str] = None
    descripcion: Optional[str] = None
    salario_minimo: Optional[float] = None
    salario_maximo: Optional[float] = None

class HCMCargoUpdate(BaseModel):
    area_id: Optional[int] = None
    nombre: Optional[str] = None
    nivel: Optional[str] = None
    descripcion: Optional[str] = None
    salario_minimo: Optional[float] = None
    salario_maximo: Optional[float] = None
    activo: Optional[bool] = None

class HCMCargoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    area_id: Optional[int] = None
    nombre: str
    nivel: Optional[str] = None
    descripcion: Optional[str] = None
    salario_minimo: Optional[float] = None
    salario_maximo: Optional[float] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── Centro de Costo ───────────────────────────────────────────────────────────

class HCMCentroCostoCreate(BaseModel):
    empresa_id: int
    codigo: str
    nombre: str

class HCMCentroCostoUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    activo: Optional[bool] = None

class HCMCentroCostoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    codigo: str
    nombre: str
    activo: bool
    created_at: Optional[datetime] = None


# ─── Colaborador ───────────────────────────────────────────────────────────────

class HCMColaboradorCreate(BaseModel):
    tipo_documento: str
    numero_documento: str
    nombres: str
    apellidos: str
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    nacionalidad: Optional[str] = None
    estado_civil: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    pais: Optional[str] = "Colombia"
    telefono: Optional[str] = None
    email: Optional[str] = None
    foto_url: Optional[str] = None
    codigo_empleado: Optional[str] = None
    empresa_id: int
    sede_id: Optional[int] = None
    area_id: Optional[int] = None
    cargo_id: Optional[int] = None
    centro_costo_id: Optional[int] = None
    jefe_id: Optional[int] = None
    tipo_contrato: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    salario_base: float = 0
    tipo_salario: Optional[str] = None
    auxilio_transporte: float = 0
    bonificaciones_fijas: float = 0

class HCMColaboradorUpdate(BaseModel):
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    nacionalidad: Optional[str] = None
    estado_civil: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    pais: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    foto_url: Optional[str] = None
    codigo_empleado: Optional[str] = None
    sede_id: Optional[int] = None
    area_id: Optional[int] = None
    cargo_id: Optional[int] = None
    centro_costo_id: Optional[int] = None
    jefe_id: Optional[int] = None
    tipo_contrato: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    fecha_retiro: Optional[date] = None
    estado_laboral: Optional[str] = None
    salario_base: Optional[float] = None
    tipo_salario: Optional[str] = None
    auxilio_transporte: Optional[float] = None
    bonificaciones_fijas: Optional[float] = None

class HCMColaboradorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo_documento: str
    numero_documento: str
    nombres: str
    apellidos: str
    nombre_completo: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    nacionalidad: Optional[str] = None
    estado_civil: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    pais: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    foto_url: Optional[str] = None
    codigo_empleado: str
    empresa_id: int
    empresa_nombre: Optional[str] = None
    sede_id: Optional[int] = None
    sede_nombre: Optional[str] = None
    area_id: Optional[int] = None
    area_nombre: Optional[str] = None
    cargo_id: Optional[int] = None
    cargo_nombre: Optional[str] = None
    centro_costo_id: Optional[int] = None
    jefe_id: Optional[int] = None
    jefe_nombre: Optional[str] = None
    tipo_contrato: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    fecha_retiro: Optional[date] = None
    estado_laboral: str
    salario_base: float
    tipo_salario: Optional[str] = None
    auxilio_transporte: float
    bonificaciones_fijas: float
    usuario_id: Optional[int] = None
    es_conductor: bool = False
    created_at: Optional[datetime] = None


class HCMColaboradorListResponse(BaseModel):
    items: List[HCMColaboradorResponse]
    total: int
    page: int
    per_page: int


# ─── Historial de Colaborador ──────────────────────────────────────────────────

class HCMColaboradorHistorialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    campo: str
    valor_anterior: Optional[str] = None
    valor_nuevo: Optional[str] = None
    usuario_cambio: Optional[str] = None
    fecha_cambio: datetime


# ─── Asignar Usuario ───────────────────────────────────────────────────────────

class HCMAsignarUsuarioRequest(BaseModel):
    usuario_id: Optional[int] = None


# ─── Contrato ──────────────────────────────────────────────────────────────────

class HCMContratoCreate(BaseModel):
    colaborador_id: int
    tipo_contrato: str
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    salario: float
    notas: Optional[str] = None
    archivo_url: Optional[str] = None

class HCMContratoUpdate(BaseModel):
    tipo_contrato: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    salario: Optional[float] = None
    estado: Optional[str] = None
    notas: Optional[str] = None
    archivo_url: Optional[str] = None

class HCMContratoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    tipo_contrato: str
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    salario: float
    estado: str
    notas: Optional[str] = None
    archivo_url: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Conductor ─────────────────────────────────────────────────────────────────

class HCMConductorCreate(BaseModel):
    colaborador_id: int
    num_licencia: str
    tipo_licencia: str
    fecha_expedicion_licencia: date
    fecha_vencimiento_licencia: date
    restricciones: Optional[str] = None
    anos_experiencia: int = 0
    certificaciones: Optional[str] = None
    vehiculos_tipos: List[str] = []
    coberturas: List[str] = []

class HCMConductorUpdate(BaseModel):
    num_licencia: Optional[str] = None
    tipo_licencia: Optional[str] = None
    fecha_expedicion_licencia: Optional[date] = None
    fecha_vencimiento_licencia: Optional[date] = None
    restricciones: Optional[str] = None
    anos_experiencia: Optional[int] = None
    certificaciones: Optional[str] = None
    activo_conduccion: Optional[bool] = None
    vehiculos_tipos: Optional[List[str]] = None
    coberturas: Optional[List[str]] = None

class HCMConductorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    colaborador_documento: Optional[str] = None
    colaborador_codigo: Optional[str] = None
    colaborador_telefono: Optional[str] = None
    colaborador_ciudad: Optional[str] = None
    num_licencia: str
    tipo_licencia: str
    fecha_expedicion_licencia: date
    fecha_vencimiento_licencia: date
    restricciones: Optional[str] = None
    anos_experiencia: int
    activo_conduccion: bool
    vehiculos_tipos: List[str] = []
    coberturas: List[str] = []
    documentos_count: int = 0
    dias_hasta_vencimiento: int = 0
    created_at: Optional[datetime] = None


# ─── Conductor Documento ───────────────────────────────────────────────────────

class HCMConductorDocumentoCreate(BaseModel):
    conductor_id: int
    tipo_documento: str
    numero: Optional[str] = None
    fecha_emision: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    archivo_url: Optional[str] = None
    notas: Optional[str] = None

class HCMConductorDocumentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conductor_id: int
    tipo_documento: str
    numero: Optional[str] = None
    fecha_emision: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    archivo_url: Optional[str] = None
    estado: str
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Conductor Accidente ───────────────────────────────────────────────────────

class HCMConductorAccidenteCreate(BaseModel):
    conductor_id: int
    fecha: date
    descripcion: str
    tipo: str
    consecuencias: Optional[str] = None
    dias_incapacidad: int = 0
    archivo_url: Optional[str] = None

class HCMConductorAccidenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conductor_id: int
    fecha: date
    descripcion: str
    tipo: str
    consecuencias: Optional[str] = None
    dias_incapacidad: int
    archivo_url: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Nómina Periodo ────────────────────────────────────────────────────────────

class HCMNominaPeriodoCreate(BaseModel):
    empresa_id: int
    nombre: str
    fecha_inicio: date
    fecha_fin: date
    notas: Optional[str] = None

class HCMNominaPeriodoUpdate(BaseModel):
    nombre: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    notas: Optional[str] = None

class HCMNominaPeriodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    nombre: str
    fecha_inicio: date
    fecha_fin: date
    estado: str
    total_devengado: float
    total_deducido: float
    total_neto: float
    empleados_count: int
    # La tabla de períodos lee `num_empleados`, no `empleados_count`: la columna
    # «Empleados» salía en blanco en todos los períodos. Se agrega en vez de
    # renombrar porque el nombre largo ya está publicado en el endpoint.
    num_empleados: int = 0
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Nómina Detalle ────────────────────────────────────────────────────────────

class HCMNominaDetalleCreate(BaseModel):
    periodo_id: int
    colaborador_id: int
    salario_base: float = 0
    horas_extras: float = 0
    recargo_nocturno: float = 0
    dominicales: float = 0
    festivos: float = 0
    bonificaciones: float = 0
    comisiones: float = 0
    viaticos: float = 0
    auxilio_transporte: float = 0
    otros_devengados: float = 0
    salud: float = 0
    pension: float = 0
    fondo_solidaridad: float = 0
    retencion_fuente: float = 0
    embargo: float = 0
    otros_descuentos: float = 0

class HCMNominaDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    periodo_id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    salario_base: float
    horas_extras: float
    recargo_nocturno: float
    dominicales: float
    festivos: float
    bonificaciones: float
    comisiones: float
    viaticos: float
    auxilio_transporte: float
    otros_devengados: float
    total_devengado: float
    salud: float
    pension: float
    fondo_solidaridad: float
    retencion_fuente: float
    embargo: float
    otros_descuentos: float
    total_deducido: float
    neto_pagado: float
    created_at: Optional[datetime] = None


# ─── Novedad ───────────────────────────────────────────────────────────────────

class HCMNovedadCreate(BaseModel):
    colaborador_id: int
    periodo_id: Optional[int] = None
    tipo_novedad: str
    descripcion: Optional[str] = None
    valor: float
    fecha: date
    aprobado_por: Optional[str] = None
    notas: Optional[str] = None

class HCMNovedadUpdate(BaseModel):
    tipo_novedad: Optional[str] = None
    descripcion: Optional[str] = None
    valor: Optional[float] = None
    fecha: Optional[date] = None
    aprobado_por: Optional[str] = None
    notas: Optional[str] = None

class HCMNovedadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    periodo_id: Optional[int] = None
    periodo_nombre: Optional[str] = None
    tipo_novedad: str
    descripcion: Optional[str] = None
    valor: float
    fecha: date
    aprobado_por: Optional[str] = None
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Liquidación ───────────────────────────────────────────────────────────────

class HCMLiquidacionCreate(BaseModel):
    colaborador_id: int
    fecha_liquidacion: date
    motivo_retiro: str
    dias_trabajados: int = 0
    prima: float = 0
    cesantias: float = 0
    intereses_cesantias: float = 0
    vacaciones_compensadas: float = 0
    indemnizacion: float = 0
    otros_conceptos: float = 0
    deducciones: float = 0
    notas: Optional[str] = None

class HCMLiquidacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    fecha_liquidacion: date
    motivo_retiro: str
    dias_trabajados: int
    prima: float
    cesantias: float
    intereses_cesantias: float
    vacaciones_compensadas: float
    indemnizacion: float
    otros_conceptos: float
    deducciones: float
    total_pagar: float
    estado: str
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Incapacidad ───────────────────────────────────────────────────────────────

class HCMIncapacidadCreate(BaseModel):
    colaborador_id: int
    tipo_incapacidad: str
    diagnostico: Optional[str] = None
    entidad_emisora: Optional[str] = None
    fecha_inicio: date
    fecha_fin: date
    dias: int = 0
    costo_empresa: float = 0
    costo_eps: float = 0
    archivo_url: Optional[str] = None
    notas: Optional[str] = None

class HCMIncapacidadUpdate(BaseModel):
    tipo_incapacidad: Optional[str] = None
    diagnostico: Optional[str] = None
    entidad_emisora: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    dias: Optional[int] = None
    costo_empresa: Optional[float] = None
    costo_eps: Optional[float] = None
    archivo_url: Optional[str] = None
    estado: Optional[str] = None
    notas: Optional[str] = None

class HCMIncapacidadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    tipo_incapacidad: str
    diagnostico: Optional[str] = None
    entidad_emisora: Optional[str] = None
    fecha_inicio: date
    fecha_fin: date
    dias: int
    costo_empresa: float
    costo_eps: float
    archivo_url: Optional[str] = None
    estado: str
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Vacación ──────────────────────────────────────────────────────────────────

class HCMVacacionCreate(BaseModel):
    colaborador_id: int
    fecha_inicio: date
    fecha_fin: date
    dias_disfrutados: int = 0
    tipo: str = "DISFRUTE"
    notas: Optional[str] = None

class HCMVacacionUpdate(BaseModel):
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    dias_disfrutados: Optional[int] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    aprobado_por: Optional[str] = None
    notas: Optional[str] = None

class HCMVacacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    fecha_inicio: date
    fecha_fin: date
    dias_disfrutados: int
    tipo: str
    estado: str
    aprobado_por: Optional[str] = None
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Vacante ───────────────────────────────────────────────────────────────────

class HCMVacanteCreate(BaseModel):
    empresa_id: int
    cargo_id: Optional[int] = None
    titulo: str
    num_vacantes: int = 1
    descripcion: Optional[str] = None
    requisitos: Optional[str] = None
    salario_min: Optional[float] = None
    salario_max: Optional[float] = None
    fecha_apertura: date
    fecha_cierre: Optional[date] = None
    tipo_contrato: Optional[str] = None
    modalidad: Optional[str] = None

class HCMVacanteUpdate(BaseModel):
    cargo_id: Optional[int] = None
    titulo: Optional[str] = None
    num_vacantes: Optional[int] = None
    descripcion: Optional[str] = None
    requisitos: Optional[str] = None
    salario_min: Optional[float] = None
    salario_max: Optional[float] = None
    fecha_apertura: Optional[date] = None
    fecha_cierre: Optional[date] = None
    estado: Optional[str] = None
    tipo_contrato: Optional[str] = None
    modalidad: Optional[str] = None

class HCMVacanteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    cargo_id: Optional[int] = None
    cargo_nombre: Optional[str] = None
    titulo: str
    num_vacantes: int
    descripcion: Optional[str] = None
    requisitos: Optional[str] = None
    salario_min: Optional[float] = None
    salario_max: Optional[float] = None
    fecha_apertura: date
    fecha_cierre: Optional[date] = None
    estado: str
    tipo_contrato: Optional[str] = None
    modalidad: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Postulación ───────────────────────────────────────────────────────────────

class HCMPostulacionCreate(BaseModel):
    vacante_id: int
    nombres: str
    apellidos: str
    email: str
    telefono: Optional[str] = None
    cv_url: Optional[str] = None
    notas: Optional[str] = None

class HCMPostulacionUpdate(BaseModel):
    estado: Optional[str] = None
    puntuacion: Optional[float] = None
    notas: Optional[str] = None

class HCMPostulacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vacante_id: int
    vacante_titulo: Optional[str] = None
    nombres: str
    apellidos: str
    email: str
    telefono: Optional[str] = None
    cv_url: Optional[str] = None
    fecha_postulacion: Optional[date] = None
    estado: str
    puntuacion: Optional[float] = None
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Entrevista ────────────────────────────────────────────────────────────────

class HCMEntrevistaCreate(BaseModel):
    postulacion_id: int
    fecha: datetime
    tipo: str
    entrevistador: str
    notas: Optional[str] = None

class HCMEntrevistaUpdate(BaseModel):
    resultado: Optional[str] = None
    calificacion: Optional[float] = None
    notas: Optional[str] = None

class HCMEntrevistaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    postulacion_id: int
    postulante_nombre: Optional[str] = None
    fecha: datetime
    tipo: str
    entrevistador: str
    resultado: Optional[str] = None
    calificacion: Optional[float] = None
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Evaluación ────────────────────────────────────────────────────────────────

class HCMEvaluacionCreate(BaseModel):
    colaborador_id: int
    periodo: str
    tipo_evaluacion: str
    evaluador_id: Optional[int] = None
    fecha: date
    notas: Optional[str] = None

class HCMEvaluacionUpdate(BaseModel):
    periodo: Optional[str] = None
    tipo_evaluacion: Optional[str] = None
    evaluador_id: Optional[int] = None
    fecha: Optional[date] = None
    estado: Optional[str] = None
    notas: Optional[str] = None

class HCMEvaluacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    periodo: str
    tipo_evaluacion: str
    evaluador_id: Optional[int] = None
    evaluador_nombre: Optional[str] = None
    fecha: date
    calificacion_total: Optional[float] = None
    estado: str
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Evaluación Detalle ────────────────────────────────────────────────────────

class HCMEvaluacionDetalleCreate(BaseModel):
    evaluacion_id: int
    criterio: str
    competencia: Optional[str] = None
    calificacion: float = 0
    peso: float = 1.0
    observacion: Optional[str] = None

class HCMEvaluacionDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    evaluacion_id: int
    criterio: str
    competencia: Optional[str] = None
    calificacion: float
    peso: float
    observacion: Optional[str] = None

class HCMEvaluacionDetallesBulk(BaseModel):
    detalles: List[HCMEvaluacionDetalleCreate]


# ─── Capacitación ──────────────────────────────────────────────────────────────

class HCMCapacitacionCreate(BaseModel):
    empresa_id: int
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    duracion_horas: float = 0
    instructor: Optional[str] = None
    modalidad: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    obligatoria: bool = False
    aplica_conductores: bool = False

class HCMCapacitacionUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    duracion_horas: Optional[float] = None
    instructor: Optional[str] = None
    modalidad: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    obligatoria: Optional[bool] = None
    aplica_conductores: Optional[bool] = None
    activo: Optional[bool] = None

class HCMCapacitacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    duracion_horas: float
    instructor: Optional[str] = None
    modalidad: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    obligatoria: bool
    aplica_conductores: bool
    activo: bool
    created_at: Optional[datetime] = None


# ─── Colaborador Capacitación ──────────────────────────────────────────────────

class HCMColaboradorCapacitacionCreate(BaseModel):
    colaborador_id: int
    capacitacion_id: int

class HCMColaboradorCapacitacionUpdateCompletar(BaseModel):
    calificacion: Optional[float] = None
    fecha_vencimiento: Optional[date] = None

class HCMColaboradorCapacitacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    capacitacion_id: int
    capacitacion_nombre: Optional[str] = None
    estado: str
    fecha_completado: Optional[date] = None
    calificacion: Optional[float] = None
    certificado_url: Optional[str] = None
    fecha_vencimiento: Optional[date] = None
    notas: Optional[str] = None
    created_at: Optional[datetime] = None

class HCMCapacitacionAsignarRequest(BaseModel):
    colaborador_ids: List[int]


# ─── SST Incidente ─────────────────────────────────────────────────────────────

class HCMSSTIncidenteCreate(BaseModel):
    empresa_id: int
    sede_id: Optional[int] = None
    colaborador_id: Optional[int] = None
    fecha: date
    tipo_sst: str
    descripcion: str
    causa: Optional[str] = None
    consecuencias: Optional[str] = None
    dias_incapacidad: int = 0
    medidas_correctivas: Optional[str] = None

class HCMSSTIncidenteUpdate(BaseModel):
    sede_id: Optional[int] = None
    colaborador_id: Optional[int] = None
    fecha: Optional[date] = None
    tipo_sst: Optional[str] = None
    descripcion: Optional[str] = None
    causa: Optional[str] = None
    consecuencias: Optional[str] = None
    dias_incapacidad: Optional[int] = None
    investigado: Optional[bool] = None
    medidas_correctivas: Optional[str] = None
    estado: Optional[str] = None
    archivo_url: Optional[str] = None

class HCMSSTIncidenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    sede_id: Optional[int] = None
    colaborador_id: Optional[int] = None
    colaborador_nombre: Optional[str] = None
    fecha: date
    tipo_sst: str
    descripcion: str
    causa: Optional[str] = None
    consecuencias: Optional[str] = None
    dias_incapacidad: int
    investigado: bool
    medidas_correctivas: Optional[str] = None
    estado: str
    archivo_url: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── SST Riesgo ────────────────────────────────────────────────────────────────

class HCMSSTRiesgoCreate(BaseModel):
    empresa_id: int
    area_id: Optional[int] = None
    fuente: str
    descripcion: str
    probabilidad: int
    impacto: int
    control: Optional[str] = None
    responsable_id: Optional[int] = None
    fecha_revision: Optional[date] = None

class HCMSSTRiesgoUpdate(BaseModel):
    area_id: Optional[int] = None
    fuente: Optional[str] = None
    descripcion: Optional[str] = None
    probabilidad: Optional[int] = None
    impacto: Optional[int] = None
    nivel_riesgo: Optional[int] = None
    control: Optional[str] = None
    responsable_id: Optional[int] = None
    fecha_revision: Optional[date] = None
    estado: Optional[str] = None

class HCMSSTRiesgoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    area_id: Optional[int] = None
    area_nombre: Optional[str] = None
    fuente: str
    descripcion: str
    probabilidad: int
    impacto: int
    nivel_riesgo: int
    control: Optional[str] = None
    responsable_id: Optional[int] = None
    responsable_nombre: Optional[str] = None
    fecha_revision: Optional[date] = None
    estado: str
    created_at: Optional[datetime] = None


# ─── SST Inspección ────────────────────────────────────────────────────────────

class HCMSSTInspeccionCreate(BaseModel):
    empresa_id: int
    sede_id: Optional[int] = None
    fecha: date
    tipo: str
    inspector_id: Optional[int] = None
    hallazgos: Optional[str] = None
    acciones: Optional[str] = None

class HCMSSTInspeccionUpdate(BaseModel):
    sede_id: Optional[int] = None
    fecha: Optional[date] = None
    tipo: Optional[str] = None
    inspector_id: Optional[int] = None
    hallazgos: Optional[str] = None
    acciones: Optional[str] = None
    estado: Optional[str] = None
    archivo_url: Optional[str] = None

class HCMSSTInspeccionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    sede_id: Optional[int] = None
    fecha: date
    tipo: str
    inspector_id: Optional[int] = None
    inspector_nombre: Optional[str] = None
    hallazgos: Optional[str] = None
    acciones: Optional[str] = None
    estado: str
    archivo_url: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Dashboard ─────────────────────────────────────────────────────────────────

class HCMKPIsDashboard(BaseModel):
    headcount_total: int
    headcount_activo: int
    headcount_retirado: int
    nuevos_ingresos_mes: int
    rotacion_mensual: float
    conductores_activos: int
    conductores_licencias_por_vencer: int
    incapacidades_activas: int
    vacaciones_pendientes: int
    ausentismo_rate: float
    costo_nomina_mes: float

class HCMAlertaItem(BaseModel):
    tipo: str
    mensaje: str
    colaborador_id: Optional[int] = None
    colaborador_nombre: Optional[str] = None
    dias_restantes: Optional[int] = None
    nivel: str  # "danger", "warning", "info"
