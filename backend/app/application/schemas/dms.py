"""
Módulo DMS (Document Management System) — Schemas Pydantic
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


# ─── DMSCarpeta ────────────────────────────────────────────────────────────────

class DMSCarpetaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    padre_id: Optional[int] = None
    ruta: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    es_publica: bool = False
    creado_por_id: Optional[int] = None

class DMSCarpetaUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    padre_id: Optional[int] = None
    ruta: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    es_publica: Optional[bool] = None

class DMSCarpetaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    descripcion: Optional[str] = None
    padre_id: Optional[int] = None
    ruta: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    es_publica: bool
    creado_por_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ─── DMSCategoria ──────────────────────────────────────────────────────────────

class DMSCategoriaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    codigo: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    activo: bool = True

class DMSCategoriaUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    codigo: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    activo: Optional[bool] = None

class DMSCategoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    descripcion: Optional[str] = None
    codigo: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── DMSTipoDocumento ──────────────────────────────────────────────────────────

class DMSTipoDocumentoCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    categoria_id: int
    codigo: Optional[str] = None
    extensiones_permitidas: Optional[str] = None
    requiere_firma: bool = False
    requiere_aprobacion: bool = False
    dias_vigencia: Optional[int] = None
    activo: bool = True

class DMSTipoDocumentoUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    categoria_id: Optional[int] = None
    codigo: Optional[str] = None
    extensiones_permitidas: Optional[str] = None
    requiere_firma: Optional[bool] = None
    requiere_aprobacion: Optional[bool] = None
    dias_vigencia: Optional[int] = None
    activo: Optional[bool] = None

class DMSTipoDocumentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    descripcion: Optional[str] = None
    categoria_id: int
    codigo: Optional[str] = None
    extensiones_permitidas: Optional[str] = None
    requiere_firma: bool
    requiere_aprobacion: bool
    dias_vigencia: Optional[int] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── DMSCampoMetadato ──────────────────────────────────────────────────────────

class DMSCampoMetadatoCreate(BaseModel):
    tipo_documento_id: int
    nombre: str
    etiqueta: str
    tipo_dato: str = "texto"
    opciones: Optional[str] = None
    requerido: bool = False
    orden: int = 0

class DMSCampoMetadatoUpdate(BaseModel):
    nombre: Optional[str] = None
    etiqueta: Optional[str] = None
    tipo_dato: Optional[str] = None
    opciones: Optional[str] = None
    requerido: Optional[bool] = None
    orden: Optional[int] = None

class DMSCampoMetadatoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo_documento_id: int
    nombre: str
    etiqueta: str
    tipo_dato: str
    opciones: Optional[str] = None
    requerido: bool
    orden: int
    created_at: Optional[datetime] = None


# ─── DMSDocumento ──────────────────────────────────────────────────────────────

class DMSDocumentoCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    carpeta_id: Optional[int] = None
    estado: str = "BORRADOR"
    version_actual: str = "1.0"
    version_numero: int = 1
    tags: Optional[str] = None
    es_confidencial: bool = False
    permite_descarga: bool = True
    permite_impresion: bool = True
    fecha_vigencia_inicio: Optional[datetime] = None
    fecha_vigencia_fin: Optional[datetime] = None
    propietario_id: Optional[int] = None
    hcm_colaborador_id: Optional[int] = None
    hcm_conductor_id: Optional[int] = None
    tms_vehiculo_id: Optional[int] = None
    modulo_origen: Optional[str] = None
    referencia_externa_id: Optional[int] = None

class DMSDocumentoUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    carpeta_id: Optional[int] = None
    estado: Optional[str] = None
    version_actual: Optional[str] = None
    version_numero: Optional[int] = None
    tags: Optional[str] = None
    es_confidencial: Optional[bool] = None
    permite_descarga: Optional[bool] = None
    permite_impresion: Optional[bool] = None
    fecha_vigencia_inicio: Optional[datetime] = None
    fecha_vigencia_fin: Optional[datetime] = None
    propietario_id: Optional[int] = None
    hcm_colaborador_id: Optional[int] = None
    hcm_conductor_id: Optional[int] = None
    tms_vehiculo_id: Optional[int] = None
    modulo_origen: Optional[str] = None
    referencia_externa_id: Optional[int] = None

class DMSDocumentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    carpeta_id: Optional[int] = None
    estado: str
    version_actual: str
    version_numero: int
    tags: Optional[str] = None
    es_confidencial: bool
    permite_descarga: bool
    permite_impresion: bool
    fecha_vigencia_inicio: Optional[datetime] = None
    fecha_vigencia_fin: Optional[datetime] = None
    propietario_id: Optional[int] = None
    hcm_colaborador_id: Optional[int] = None
    hcm_conductor_id: Optional[int] = None
    tms_vehiculo_id: Optional[int] = None
    modulo_origen: Optional[str] = None
    referencia_externa_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class DMSDocumentoListResponse(BaseModel):
    """Schema reducido para listados paginados de documentos."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: Optional[str] = None
    nombre: str
    tipo_nombre: Optional[str] = None
    estado: str
    version_actual: str
    fecha_vigencia_inicio: Optional[datetime] = None
    fecha_vigencia_fin: Optional[datetime] = None
    propietario_id: Optional[int] = None
    propietario_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    es_confidencial: bool = False
    permite_descarga: bool = True
    permite_impresion: bool = True
    # El formulario de edición parte de la fila del listado: sin estos campos,
    # guardar un documento le borraba la carpeta, el tipo y las etiquetas.
    descripcion: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    carpeta_id: Optional[int] = None
    tags: Optional[str] = None
    # Lo decide el servidor con las mismas reglas con que atiende la descarga.
    puede_descargar: bool = True


# ─── DMSVersion ────────────────────────────────────────────────────────────────

class DMSVersionCreate(BaseModel):
    documento_id: int
    numero_version: str
    version_numero: int
    es_mayor: bool = False
    nombre_archivo: str
    ruta_archivo: Optional[str] = None
    url_archivo: Optional[str] = None
    tamanio_bytes: Optional[int] = None
    tipo_mime: Optional[str] = None
    hash_md5: Optional[str] = None
    comentario: Optional[str] = None
    ocr_texto: Optional[str] = None
    creado_por_id: Optional[int] = None

class DMSVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento_id: int
    numero_version: str
    version_numero: int
    es_mayor: bool
    nombre_archivo: str
    ruta_archivo: Optional[str] = None
    url_archivo: Optional[str] = None
    tamanio_bytes: Optional[int] = None
    tipo_mime: Optional[str] = None
    hash_md5: Optional[str] = None
    comentario: Optional[str] = None
    ocr_texto: Optional[str] = None
    creado_por_id: Optional[int] = None
    created_at: Optional[datetime] = None


# ─── DMSMetadatoValor ──────────────────────────────────────────────────────────

class DMSMetadatoValorCreate(BaseModel):
    documento_id: int
    campo_id: int
    valor_texto: Optional[str] = None
    valor_numero: Optional[Decimal] = None
    valor_fecha: Optional[datetime] = None
    valor_booleano: Optional[bool] = None

class DMSMetadatoValorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento_id: int
    campo_id: int
    valor_texto: Optional[str] = None
    valor_numero: Optional[Decimal] = None
    valor_fecha: Optional[datetime] = None
    valor_booleano: Optional[bool] = None
    created_at: Optional[datetime] = None


# ─── DMSFirma ──────────────────────────────────────────────────────────────────

class DMSFirmaCreate(BaseModel):
    documento_id: int
    version_id: Optional[int] = None
    firmante_id: int
    tipo_firma: str
    estado: str = "PENDIENTE"
    fecha_firma: Optional[datetime] = None
    ip_firma: Optional[str] = None
    dispositivo: Optional[str] = None
    observaciones: Optional[str] = None
    orden: int = 0

class DMSFirmaUpdate(BaseModel):
    estado: Optional[str] = None
    fecha_firma: Optional[datetime] = None
    ip_firma: Optional[str] = None
    dispositivo: Optional[str] = None
    observaciones: Optional[str] = None

class DMSFirmaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento_id: int
    version_id: Optional[int] = None
    firmante_id: int
    tipo_firma: str
    estado: str
    fecha_firma: Optional[datetime] = None
    ip_firma: Optional[str] = None
    dispositivo: Optional[str] = None
    observaciones: Optional[str] = None
    orden: int
    created_at: Optional[datetime] = None


# ─── DMSWorkflow ───────────────────────────────────────────────────────────────

class DMSWorkflowCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    activo: bool = True
    dias_limite: Optional[int] = None

class DMSWorkflowUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    activo: Optional[bool] = None
    dias_limite: Optional[int] = None

class DMSWorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    descripcion: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    activo: bool
    dias_limite: Optional[int] = None
    created_at: Optional[datetime] = None


# ─── DMSWorkflowPaso ───────────────────────────────────────────────────────────

class DMSWorkflowPasoCreate(BaseModel):
    workflow_id: int
    nombre: str
    tipo: str
    orden: int = 0
    responsable_id: Optional[int] = None
    responsable_rol: Optional[str] = None
    dias_limite: Optional[int] = None
    es_obligatorio: bool = True

class DMSWorkflowPasoUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    orden: Optional[int] = None
    responsable_id: Optional[int] = None
    responsable_rol: Optional[str] = None
    dias_limite: Optional[int] = None
    es_obligatorio: Optional[bool] = None

class DMSWorkflowPasoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workflow_id: int
    nombre: str
    tipo: str
    orden: int
    responsable_id: Optional[int] = None
    responsable_rol: Optional[str] = None
    dias_limite: Optional[int] = None
    es_obligatorio: bool
    created_at: Optional[datetime] = None


# ─── DMSInstancia ──────────────────────────────────────────────────────────────

class DMSInstanciaCreate(BaseModel):
    workflow_id: int
    documento_id: int
    iniciado_por_id: Optional[int] = None
    paso_actual: int = 0
    fecha_inicio: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None

class DMSInstanciaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workflow_id: int
    documento_id: int
    estado: str
    iniciado_por_id: Optional[int] = None
    paso_actual: int
    fecha_inicio: Optional[datetime] = None
    fecha_limite: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    comentario_cierre: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── DMSInstanciaPaso ──────────────────────────────────────────────────────────

class DMSInstanciaPasoUpdate(BaseModel):
    estado: Optional[str] = None
    asignado_a_id: Optional[int] = None
    fecha_asignacion: Optional[datetime] = None
    fecha_respuesta: Optional[datetime] = None
    comentario: Optional[str] = None
    accion: Optional[str] = None

class DMSInstanciaPasoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instancia_id: int
    paso_id: int
    estado: str
    asignado_a_id: Optional[int] = None
    fecha_asignacion: Optional[datetime] = None
    fecha_respuesta: Optional[datetime] = None
    comentario: Optional[str] = None
    accion: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── DMSExpediente ─────────────────────────────────────────────────────────────

class DMSExpedienteCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    tipo: str
    estado: str = "activo"
    descripcion: Optional[str] = None
    hcm_colaborador_id: Optional[int] = None
    hcm_conductor_id: Optional[int] = None
    tms_vehiculo_id: Optional[int] = None
    propietario_id: Optional[int] = None
    completitud_pct: Optional[Decimal] = None

class DMSExpedienteUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    descripcion: Optional[str] = None
    hcm_colaborador_id: Optional[int] = None
    hcm_conductor_id: Optional[int] = None
    tms_vehiculo_id: Optional[int] = None
    propietario_id: Optional[int] = None
    completitud_pct: Optional[Decimal] = None

class DMSExpedienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: Optional[str] = None
    nombre: str
    tipo: str
    estado: str
    descripcion: Optional[str] = None
    hcm_colaborador_id: Optional[int] = None
    hcm_conductor_id: Optional[int] = None
    tms_vehiculo_id: Optional[int] = None
    propietario_id: Optional[int] = None
    completitud_pct: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ─── DMSExpedienteDocumento ────────────────────────────────────────────────────

class DMSExpedienteDocumentoCreate(BaseModel):
    expediente_id: int
    documento_id: int
    tipo_requerido: Optional[str] = None
    es_obligatorio: bool = False

class DMSExpedienteDocumentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    expediente_id: int
    documento_id: int
    tipo_requerido: Optional[str] = None
    es_obligatorio: bool
    created_at: Optional[datetime] = None


# ─── DMSRetencion ─────────────────────────────────────────────────────────────

class DMSRetencionCreate(BaseModel):
    nombre: str
    tipo_documento_id: Optional[int] = None
    dias_retencion_activo: int
    dias_retencion_total: int
    accion_vencimiento: str = "archivar"
    normativa: Optional[str] = None
    activo: bool = True

class DMSRetencionUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo_documento_id: Optional[int] = None
    dias_retencion_activo: Optional[int] = None
    dias_retencion_total: Optional[int] = None
    accion_vencimiento: Optional[str] = None
    normativa: Optional[str] = None
    activo: Optional[bool] = None

class DMSRetencionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo_documento_id: Optional[int] = None
    dias_retencion_activo: int
    dias_retencion_total: int
    accion_vencimiento: str
    normativa: Optional[str] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── DMSAuditoria ─────────────────────────────────────────────────────────────

class DMSAuditoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento_id: Optional[int] = None
    version_id: Optional[int] = None
    usuario_id: Optional[int] = None
    accion: str
    detalle: Optional[str] = None
    ip_origen: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── DMSNotificacion ──────────────────────────────────────────────────────────

class DMSNotificacionCreate(BaseModel):
    usuario_id: int
    documento_id: Optional[int] = None
    tipo: str
    titulo: str
    mensaje: str
    leida: bool = False
    accion_url: Optional[str] = None

class DMSNotificacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usuario_id: int
    documento_id: Optional[int] = None
    tipo: str
    titulo: str
    mensaje: str
    leida: bool
    accion_url: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── DMSKPIDiario ─────────────────────────────────────────────────────────────

class DMSKPIDiarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha: datetime
    total_documentos: int
    documentos_creados: int
    documentos_aprobados: int
    documentos_vencidos: int
    firmas_pendientes: int
    firmas_completadas: int
    workflows_activos: int
    tamanio_total_mb: Optional[Decimal] = None
    created_at: Optional[datetime] = None


# ─── Dashboard KPIs ───────────────────────────────────────────────────────────

class DMSDashboardKPIs(BaseModel):
    """KPIs agregados para el dashboard del módulo DMS."""
    total_documentos: int = 0
    documentos_activos: int = 0
    documentos_vencidos: int = 0
    documentos_proximos_vencer: int = 0
    firmas_pendientes: int = 0
    workflows_activos: int = 0
    expedientes_activos: int = 0
    cumplimiento_pct: float = 0.0
    categorias_total: int = 0
    versiones_hoy: int = 0
    tamanio_total_mb: float = 0.0
    alertas_criticas: int = 0
    documentos_creados_hoy: int = 0
    aprobaciones_pendientes: int = 0
