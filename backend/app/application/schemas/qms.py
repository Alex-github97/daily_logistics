from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


# ---------------------------------------------------------------------------
# QMSProceso
# ---------------------------------------------------------------------------

class QMSProcesoCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    estado: Optional[str] = None
    padre_id: Optional[int] = None
    responsable_id: Optional[int] = None
    objetivo: Optional[str] = None
    alcance: Optional[str] = None
    norma_iso: Optional[str] = None
    orden: Optional[int] = 0


class QMSProcesoUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    padre_id: Optional[int] = None
    responsable_id: Optional[int] = None
    objetivo: Optional[str] = None
    alcance: Optional[str] = None
    norma_iso: Optional[str] = None
    orden: Optional[int] = None


class QMSProcesoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    estado: str
    padre_id: Optional[int] = None
    responsable_id: Optional[int] = None
    objetivo: Optional[str] = None
    alcance: Optional[str] = None
    norma_iso: Optional[str] = None
    orden: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSProcedimiento
# ---------------------------------------------------------------------------

class QMSProcedimientoCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    tipo: Optional[str] = None
    version: Optional[str] = "1.0"
    estado: Optional[str] = "vigente"
    dms_documento_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_vigencia: Optional[datetime] = None
    activo: Optional[bool] = True


class QMSProcedimientoUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    tipo: Optional[str] = None
    version: Optional[str] = None
    estado: Optional[str] = None
    dms_documento_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_vigencia: Optional[datetime] = None
    activo: Optional[bool] = None


class QMSProcedimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    tipo: Optional[str] = None
    version: str
    estado: str
    dms_documento_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_vigencia: Optional[datetime] = None
    activo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSIndicador
# ---------------------------------------------------------------------------

class QMSIndicadorCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    tipo: Optional[str] = None
    formula: Optional[str] = None
    unidad: Optional[str] = None
    frecuencia: Optional[str] = None
    meta: Optional[float] = None
    meta_min: Optional[float] = None
    meta_max: Optional[float] = None
    responsable_id: Optional[int] = None
    activo: Optional[bool] = True
    modulo_origen: Optional[str] = None


class QMSIndicadorUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    tipo: Optional[str] = None
    formula: Optional[str] = None
    unidad: Optional[str] = None
    frecuencia: Optional[str] = None
    meta: Optional[float] = None
    meta_min: Optional[float] = None
    meta_max: Optional[float] = None
    responsable_id: Optional[int] = None
    activo: Optional[bool] = None
    modulo_origen: Optional[str] = None


class QMSIndicadorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    tipo: Optional[str] = None
    formula: Optional[str] = None
    unidad: Optional[str] = None
    frecuencia: Optional[str] = None
    meta: Optional[float] = None
    meta_min: Optional[float] = None
    meta_max: Optional[float] = None
    responsable_id: Optional[int] = None
    activo: bool
    modulo_origen: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSMetaIndicador
# ---------------------------------------------------------------------------

class QMSMetaIndicadorCreate(BaseModel):
    indicador_id: int
    periodo: str
    meta: float
    meta_min: Optional[float] = None
    meta_max: Optional[float] = None
    activo: Optional[bool] = True


class QMSMetaIndicadorUpdate(BaseModel):
    periodo: Optional[str] = None
    meta: Optional[float] = None
    meta_min: Optional[float] = None
    meta_max: Optional[float] = None
    activo: Optional[bool] = None


class QMSMetaIndicadorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    indicador_id: int
    periodo: str
    meta: float
    meta_min: Optional[float] = None
    meta_max: Optional[float] = None
    activo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSMedicionIndicador
# ---------------------------------------------------------------------------

class QMSMedicionIndicadorCreate(BaseModel):
    indicador_id: int
    periodo: str
    valor: float
    cumple_meta: Optional[bool] = None
    variacion_pct: Optional[float] = None
    observaciones: Optional[str] = None
    registrado_por_id: Optional[int] = None


class QMSMedicionIndicadorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    indicador_id: int
    periodo: str
    valor: float
    cumple_meta: Optional[bool] = None
    variacion_pct: Optional[float] = None
    observaciones: Optional[str] = None
    registrado_por_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSNoConformidad
# ---------------------------------------------------------------------------

class QMSNoConformidadCreate(BaseModel):
    codigo: Optional[str] = None
    titulo: str
    descripcion: str
    clasificacion: str
    estado: Optional[str] = None
    origen: str
    proceso_id: Optional[int] = None
    area: Optional[str] = None
    responsable_id: Optional[int] = None
    detectado_por_id: Optional[int] = None
    fecha_deteccion: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    causa_raiz: Optional[str] = None
    herramienta_analisis: Optional[str] = None
    impacto: Optional[str] = None
    norma_afectada: Optional[str] = None
    auditoria_id: Optional[int] = None
    requiere_capa: Optional[bool] = True


class QMSNoConformidadUpdate(BaseModel):
    codigo: Optional[str] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    clasificacion: Optional[str] = None
    estado: Optional[str] = None
    origen: Optional[str] = None
    proceso_id: Optional[int] = None
    area: Optional[str] = None
    responsable_id: Optional[int] = None
    detectado_por_id: Optional[int] = None
    fecha_deteccion: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    causa_raiz: Optional[str] = None
    herramienta_analisis: Optional[str] = None
    impacto: Optional[str] = None
    norma_afectada: Optional[str] = None
    auditoria_id: Optional[int] = None
    requiere_capa: Optional[bool] = None


class QMSNoConformidadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    titulo: str
    descripcion: str
    clasificacion: str
    estado: str
    origen: str
    proceso_id: Optional[int] = None
    area: Optional[str] = None
    responsable_id: Optional[int] = None
    detectado_por_id: Optional[int] = None
    fecha_deteccion: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    causa_raiz: Optional[str] = None
    herramienta_analisis: Optional[str] = None
    impacto: Optional[str] = None
    norma_afectada: Optional[str] = None
    auditoria_id: Optional[int] = None
    requiere_capa: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSHallazgo
# ---------------------------------------------------------------------------

class QMSHallazgoCreate(BaseModel):
    codigo: Optional[str] = None
    descripcion: str
    tipo: Optional[str] = None
    estado: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    auditoria_id: Optional[int] = None
    nc_id: Optional[int] = None
    impacto: Optional[str] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    evidencia: Optional[str] = None


class QMSHallazgoUpdate(BaseModel):
    codigo: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    auditoria_id: Optional[int] = None
    nc_id: Optional[int] = None
    impacto: Optional[str] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    evidencia: Optional[str] = None


class QMSHallazgoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    descripcion: str
    tipo: Optional[str] = None
    estado: str
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    auditoria_id: Optional[int] = None
    nc_id: Optional[int] = None
    impacto: Optional[str] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    evidencia: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSAuditoria
# ---------------------------------------------------------------------------

class QMSAuditoriaCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    tipo: str
    estado: Optional[str] = None
    norma: Optional[str] = None
    proceso_ids: Optional[str] = None
    auditor_lider_id: Optional[int] = None
    empresa_auditora: Optional[str] = None
    fecha_inicio_plan: Optional[datetime] = None
    fecha_fin_plan: Optional[datetime] = None
    fecha_inicio_real: Optional[datetime] = None
    fecha_fin_real: Optional[datetime] = None
    objetivo: Optional[str] = None
    alcance: Optional[str] = None
    conclusion: Optional[str] = None
    resultado: Optional[str] = None


class QMSAuditoriaUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    norma: Optional[str] = None
    proceso_ids: Optional[str] = None
    auditor_lider_id: Optional[int] = None
    empresa_auditora: Optional[str] = None
    fecha_inicio_plan: Optional[datetime] = None
    fecha_fin_plan: Optional[datetime] = None
    fecha_inicio_real: Optional[datetime] = None
    fecha_fin_real: Optional[datetime] = None
    objetivo: Optional[str] = None
    alcance: Optional[str] = None
    conclusion: Optional[str] = None
    resultado: Optional[str] = None


class QMSAuditoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    nombre: str
    tipo: str
    estado: str
    norma: Optional[str] = None
    proceso_ids: Optional[str] = None
    auditor_lider_id: Optional[int] = None
    empresa_auditora: Optional[str] = None
    fecha_inicio_plan: Optional[datetime] = None
    fecha_fin_plan: Optional[datetime] = None
    fecha_inicio_real: Optional[datetime] = None
    fecha_fin_real: Optional[datetime] = None
    objetivo: Optional[str] = None
    alcance: Optional[str] = None
    conclusion: Optional[str] = None
    resultado: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSAuditoriaHallazgo
# ---------------------------------------------------------------------------

class QMSAuditoriaHallazgoCreate(BaseModel):
    auditoria_id: int
    hallazgo_id: int


class QMSAuditoriaHallazgoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    auditoria_id: int
    hallazgo_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSCAPA
# ---------------------------------------------------------------------------

class QMSCAPACreate(BaseModel):
    codigo: Optional[str] = None
    tipo: str
    estado: Optional[str] = None
    titulo: str
    descripcion: str
    nc_id: Optional[int] = None
    hallazgo_id: Optional[int] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    verificado_por_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    causa_raiz: Optional[str] = None
    efectividad: Optional[str] = None
    porcentaje_avance: Optional[int] = 0


class QMSCAPAUpdate(BaseModel):
    codigo: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    nc_id: Optional[int] = None
    hallazgo_id: Optional[int] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    verificado_por_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    causa_raiz: Optional[str] = None
    efectividad: Optional[str] = None
    porcentaje_avance: Optional[int] = None


class QMSCAPAResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    tipo: str
    estado: str
    titulo: str
    descripcion: str
    nc_id: Optional[int] = None
    hallazgo_id: Optional[int] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    verificado_por_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    causa_raiz: Optional[str] = None
    efectividad: Optional[str] = None
    porcentaje_avance: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSCAPATarea
# ---------------------------------------------------------------------------

class QMSCAPATareaCreate(BaseModel):
    capa_id: int
    descripcion: str
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    completada: Optional[bool] = False
    fecha_completado: Optional[datetime] = None
    orden: Optional[int] = 0


class QMSCAPATareaUpdate(BaseModel):
    descripcion: Optional[str] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    completada: Optional[bool] = None
    fecha_completado: Optional[datetime] = None
    orden: Optional[int] = None


class QMSCAPATareaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capa_id: int
    descripcion: str
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    completada: bool
    fecha_completado: Optional[datetime] = None
    orden: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSRiesgo
# ---------------------------------------------------------------------------

class QMSRiesgoCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    probabilidad: int
    impacto: int
    nivel_riesgo: int
    prioridad: str
    estado: Optional[str] = "activo"
    controles: Optional[str] = None
    plan_mitigacion: Optional[str] = None
    responsable_id: Optional[int] = None
    norma_iso: Optional[str] = None
    fecha_revision: Optional[datetime] = None


class QMSRiesgoUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    probabilidad: Optional[int] = None
    impacto: Optional[int] = None
    nivel_riesgo: Optional[int] = None
    prioridad: Optional[str] = None
    estado: Optional[str] = None
    controles: Optional[str] = None
    plan_mitigacion: Optional[str] = None
    responsable_id: Optional[int] = None
    norma_iso: Optional[str] = None
    fecha_revision: Optional[datetime] = None


class QMSRiesgoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    probabilidad: int
    impacto: int
    nivel_riesgo: int
    prioridad: str
    estado: str
    controles: Optional[str] = None
    plan_mitigacion: Optional[str] = None
    responsable_id: Optional[int] = None
    norma_iso: Optional[str] = None
    fecha_revision: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSQueja
# ---------------------------------------------------------------------------

class QMSQuejaCreate(BaseModel):
    codigo: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = "abierta"
    descripcion: str
    origen: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cliente_nit: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    respuesta: Optional[str] = None
    satisfaccion_resultado: Optional[int] = None
    nc_id: Optional[int] = None
    tms_viaje_id: Optional[int] = None


class QMSQuejaUpdate(BaseModel):
    codigo: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    descripcion: Optional[str] = None
    origen: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cliente_nit: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    respuesta: Optional[str] = None
    satisfaccion_resultado: Optional[int] = None
    nc_id: Optional[int] = None
    tms_viaje_id: Optional[int] = None


class QMSQuejaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    tipo: Optional[str] = None
    estado: str
    descripcion: str
    origen: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cliente_nit: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    respuesta: Optional[str] = None
    satisfaccion_resultado: Optional[int] = None
    nc_id: Optional[int] = None
    tms_viaje_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSEvaluacionProveedor
# ---------------------------------------------------------------------------

class QMSEvaluacionProveedorCreate(BaseModel):
    proveedor_nombre: str
    proveedor_nit: Optional[str] = None
    periodo: str
    calidad: Optional[float] = None
    cumplimiento: Optional[float] = None
    servicio: Optional[float] = None
    tiempos: Optional[float] = None
    puntaje_total: Optional[float] = None
    clasificacion: Optional[str] = None
    observaciones: Optional[str] = None
    evaluado_por_id: Optional[int] = None
    proceso_id: Optional[int] = None


class QMSEvaluacionProveedorUpdate(BaseModel):
    proveedor_nombre: Optional[str] = None
    proveedor_nit: Optional[str] = None
    periodo: Optional[str] = None
    calidad: Optional[float] = None
    cumplimiento: Optional[float] = None
    servicio: Optional[float] = None
    tiempos: Optional[float] = None
    puntaje_total: Optional[float] = None
    clasificacion: Optional[str] = None
    observaciones: Optional[str] = None
    evaluado_por_id: Optional[int] = None
    proceso_id: Optional[int] = None


class QMSEvaluacionProveedorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_nombre: str
    proveedor_nit: Optional[str] = None
    periodo: str
    calidad: Optional[float] = None
    cumplimiento: Optional[float] = None
    servicio: Optional[float] = None
    tiempos: Optional[float] = None
    puntaje_total: Optional[float] = None
    clasificacion: Optional[str] = None
    observaciones: Optional[str] = None
    evaluado_por_id: Optional[int] = None
    proceso_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSCambio
# ---------------------------------------------------------------------------

class QMSCambioCreate(BaseModel):
    codigo: Optional[str] = None
    titulo: str
    descripcion: str
    tipo: Optional[str] = None
    estado: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    aprobado_por_id: Optional[int] = None
    impacto: Optional[str] = None
    evaluacion: Optional[str] = None
    fecha_solicitado: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None
    fecha_implementacion: Optional[datetime] = None
    norma_afectada: Optional[str] = None


class QMSCambioUpdate(BaseModel):
    codigo: Optional[str] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    aprobado_por_id: Optional[int] = None
    impacto: Optional[str] = None
    evaluacion: Optional[str] = None
    fecha_solicitado: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None
    fecha_implementacion: Optional[datetime] = None
    norma_afectada: Optional[str] = None


class QMSCambioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    titulo: str
    descripcion: str
    tipo: Optional[str] = None
    estado: str
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    aprobado_por_id: Optional[int] = None
    impacto: Optional[str] = None
    evaluacion: Optional[str] = None
    fecha_solicitado: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None
    fecha_implementacion: Optional[datetime] = None
    norma_afectada: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSMejora
# ---------------------------------------------------------------------------

class QMSMejoraCreate(BaseModel):
    codigo: Optional[str] = None
    titulo: str
    descripcion: str
    estado: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_completado: Optional[datetime] = None
    beneficio_esperado: Optional[str] = None
    ahorro_estimado: Optional[float] = None
    ahorro_real: Optional[float] = None
    impacto: Optional[str] = None
    retorno_estimado_meses: Optional[int] = None


class QMSMejoraUpdate(BaseModel):
    codigo: Optional[str] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[str] = None
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_completado: Optional[datetime] = None
    beneficio_esperado: Optional[str] = None
    ahorro_estimado: Optional[float] = None
    ahorro_real: Optional[float] = None
    impacto: Optional[str] = None
    retorno_estimado_meses: Optional[int] = None


class QMSMejoraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: Optional[str] = None
    titulo: str
    descripcion: str
    estado: str
    proceso_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    fecha_completado: Optional[datetime] = None
    beneficio_esperado: Optional[str] = None
    ahorro_estimado: Optional[float] = None
    ahorro_real: Optional[float] = None
    impacto: Optional[str] = None
    retorno_estimado_meses: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSEncuesta
# ---------------------------------------------------------------------------

class QMSEncuestaCreate(BaseModel):
    nombre: str
    tipo: str
    descripcion: Optional[str] = None
    activa: Optional[bool] = True
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    preguntas: Optional[str] = None
    proceso_id: Optional[int] = None


class QMSEncuestaUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    activa: Optional[bool] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    preguntas: Optional[str] = None
    total_respuestas: Optional[int] = None
    nps_score: Optional[float] = None
    csat_score: Optional[float] = None
    proceso_id: Optional[int] = None


class QMSEncuestaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: str
    descripcion: Optional[str] = None
    activa: bool
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    preguntas: Optional[str] = None
    total_respuestas: int
    nps_score: Optional[float] = None
    csat_score: Optional[float] = None
    proceso_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSEncuestaRespuesta
# ---------------------------------------------------------------------------

class QMSEncuestaRespuestaCreate(BaseModel):
    encuesta_id: int
    respondente_nombre: Optional[str] = None
    respondente_tipo: Optional[str] = None
    respuestas: Optional[str] = None
    nps_valor: Optional[int] = None
    csat_valor: Optional[int] = None
    comentario: Optional[str] = None


class QMSEncuestaRespuestaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    encuesta_id: int
    respondente_nombre: Optional[str] = None
    respondente_tipo: Optional[str] = None
    respuestas: Optional[str] = None
    nps_valor: Optional[int] = None
    csat_valor: Optional[int] = None
    comentario: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSCompetenciaProceso
# ---------------------------------------------------------------------------

class QMSCompetenciaProcesoCreate(BaseModel):
    proceso_id: int
    cargo: str
    competencia: str
    nivel_requerido: str
    norma_iso: Optional[str] = None
    activo: Optional[bool] = True


class QMSCompetenciaProcesoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proceso_id: int
    cargo: str
    competencia: str
    nivel_requerido: str
    norma_iso: Optional[str] = None
    activo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSKPIDiario
# ---------------------------------------------------------------------------

class QMSKPIDiarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: datetime
    nc_abiertas: int
    nc_cerradas_hoy: int
    hallazgos_abiertos: int
    capas_vencidas: int
    auditorias_pendientes: int
    indice_calidad: float
    otif_rate: float
    nps_promedio: float
    mejoras_activas: int
    riesgos_criticos: int
    quejas_abiertas: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# QMSDashboardKPIs
# ---------------------------------------------------------------------------

class QMSDashboardKPIs(BaseModel):
    nc_abiertas: int = 0
    nc_cerradas_mes: int = 0
    hallazgos_abiertos: int = 0
    hallazgos_cerrados_mes: int = 0
    capas_vencidas: int = 0
    capas_activas: int = 0
    auditorias_pendientes: int = 0
    auditorias_completadas_mes: int = 0
    indice_calidad: float = 0.0
    otif_rate: float = 0.0
    nps_promedio: float = 0.0
    mejoras_activas: int = 0
    riesgos_criticos: int = 0
    quejas_abiertas: int = 0
    quejas_cerradas_mes: int = 0
