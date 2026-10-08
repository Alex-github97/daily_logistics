from __future__ import annotations
from datetime import date
from typing import Optional, List
from pydantic import BaseModel


# ─── Sedes y Espacios ──────────────────────────────────────────────────────────

class LocativaSedeCreate(BaseModel):
    nombre: str; codigo: Optional[str] = None; direccion: Optional[str] = None
    ciudad: Optional[str] = None; area_m2: Optional[float] = None; activo: bool = True

class LocativaSedeUpdate(BaseModel):
    nombre: Optional[str] = None; codigo: Optional[str] = None
    direccion: Optional[str] = None; ciudad: Optional[str] = None
    area_m2: Optional[float] = None; activo: Optional[bool] = None

class LocativaSedeResponse(BaseModel):
    id: int; nombre: str; codigo: Optional[str]; direccion: Optional[str]
    ciudad: Optional[str]; area_m2: Optional[float]; activo: bool
    class Config: from_attributes = True


class LocativaEspacioCreate(BaseModel):
    sede_id: int; nombre: str; codigo: Optional[str] = None
    tipo: str = "OFICINA"; edificio: Optional[str] = None; piso: Optional[str] = None
    area_m2: Optional[float] = None; capacidad_personas: Optional[int] = None
    responsable: Optional[str] = None; activo: bool = True

class LocativaEspacioUpdate(BaseModel):
    nombre: Optional[str] = None; codigo: Optional[str] = None
    tipo: Optional[str] = None; edificio: Optional[str] = None; piso: Optional[str] = None
    area_m2: Optional[float] = None; capacidad_personas: Optional[int] = None
    responsable: Optional[str] = None; activo: Optional[bool] = None

class LocativaEspacioResponse(BaseModel):
    id: int; sede_id: int; nombre: str; codigo: Optional[str]; tipo: str
    edificio: Optional[str]; piso: Optional[str]; area_m2: Optional[float]
    capacidad_personas: Optional[int]; responsable: Optional[str]; activo: bool
    class Config: from_attributes = True


# ─── Catálogos ─────────────────────────────────────────────────────────────────

class LocativaCategoriaCreate(BaseModel):
    nombre: str; codigo: Optional[str] = None; descripcion: Optional[str] = None; activo: bool = True

class LocativaCategoriaUpdate(BaseModel):
    nombre: Optional[str] = None; codigo: Optional[str] = None
    descripcion: Optional[str] = None; activo: Optional[bool] = None

class LocativaCategoriaResponse(BaseModel):
    id: int; nombre: str; codigo: Optional[str]; descripcion: Optional[str]; activo: bool
    class Config: from_attributes = True


class LocativaModoFallaCreate(BaseModel):
    codigo: Optional[str] = None; nombre: str; categoria_falla: Optional[str] = None
    descripcion: Optional[str] = None; es_iso14224: bool = True; activo: bool = True

class LocativaModoFallaResponse(BaseModel):
    id: int; codigo: Optional[str]; nombre: str; categoria_falla: Optional[str]
    descripcion: Optional[str]; es_iso14224: bool; activo: bool
    class Config: from_attributes = True


class LocativaProveedorCreate(BaseModel):
    nombre: str; nit: Optional[str] = None; tipo: str = "CONTRATISTA"
    contacto: Optional[str] = None; telefono: Optional[str] = None
    email: Optional[str] = None; especialidad: Optional[str] = None
    fecha_contrato_inicio: Optional[date] = None
    fecha_contrato_vencimiento: Optional[date] = None; activo: bool = True

class LocativaProveedorUpdate(BaseModel):
    nombre: Optional[str] = None; nit: Optional[str] = None; tipo: Optional[str] = None
    contacto: Optional[str] = None; telefono: Optional[str] = None
    email: Optional[str] = None; especialidad: Optional[str] = None
    fecha_contrato_inicio: Optional[date] = None
    fecha_contrato_vencimiento: Optional[date] = None; activo: Optional[bool] = None

class LocativaProveedorResponse(BaseModel):
    id: int; nombre: str; nit: Optional[str]; tipo: str; contacto: Optional[str]
    telefono: Optional[str]; email: Optional[str]; especialidad: Optional[str]
    calificacion: Optional[float]; fecha_contrato_inicio: Optional[date]
    fecha_contrato_vencimiento: Optional[date]; activo: bool
    class Config: from_attributes = True


# ─── Activos ───────────────────────────────────────────────────────────────────

class LocativaActivoCreate(BaseModel):
    tag: str; nombre: str; descripcion: Optional[str] = None
    categoria_id: Optional[int] = None; clase_equipo: Optional[str] = None
    nivel_jerarquia: str = "EQUIPO"; padre_id: Optional[int] = None
    sede_id: Optional[int] = None; espacio_id: Optional[int] = None
    edificio: Optional[str] = None; piso: Optional[str] = None
    estado: str = "OPERATIVO"; criticidad: str = "ESTANDAR"
    justificacion_criticidad: Optional[str] = None
    fabricante: Optional[str] = None; marca: Optional[str] = None
    modelo: Optional[str] = None; numero_serie: Optional[str] = None
    numero_parte: Optional[str] = None; especificaciones: Optional[str] = None
    fecha_adquisicion: Optional[date] = None
    fecha_puesta_servicio: Optional[date] = None
    costo_adquisicion: Optional[float] = None; valor_residual: float = 0
    vida_util_anos: Optional[float] = None
    metodo_depreciacion: str = "LINEA_RECTA"; modelo_medicion: str = "COSTO"
    centro_costo: Optional[str] = None
    funcion_requerida: Optional[str] = None; modo_falla_esperado: Optional[str] = None
    garantia_inicio: Optional[date] = None; garantia_vencimiento: Optional[date] = None

class LocativaActivoUpdate(BaseModel):
    nombre: Optional[str] = None; descripcion: Optional[str] = None
    categoria_id: Optional[int] = None; clase_equipo: Optional[str] = None
    nivel_jerarquia: Optional[str] = None; padre_id: Optional[int] = None
    sede_id: Optional[int] = None; espacio_id: Optional[int] = None
    edificio: Optional[str] = None; piso: Optional[str] = None
    estado: Optional[str] = None; criticidad: Optional[str] = None
    justificacion_criticidad: Optional[str] = None
    fabricante: Optional[str] = None; marca: Optional[str] = None
    modelo: Optional[str] = None; numero_serie: Optional[str] = None
    especificaciones: Optional[str] = None
    fecha_adquisicion: Optional[date] = None
    fecha_puesta_servicio: Optional[date] = None
    costo_adquisicion: Optional[float] = None; valor_residual: Optional[float] = None
    vida_util_anos: Optional[float] = None
    metodo_depreciacion: Optional[str] = None; centro_costo: Optional[str] = None
    funcion_requerida: Optional[str] = None
    garantia_inicio: Optional[date] = None; garantia_vencimiento: Optional[date] = None
    activo: Optional[bool] = None

class LocativaActivoBaja(BaseModel):
    fecha_baja: date; motivo_baja: str; valor_rescate: Optional[float] = None

class LocativaActivoResponse(BaseModel):
    id: int; tag: str; nombre: str; descripcion: Optional[str]
    categoria_id: Optional[int]; clase_equipo: Optional[str]
    nivel_jerarquia: str; padre_id: Optional[int]
    sede_id: Optional[int]; espacio_id: Optional[int]
    edificio: Optional[str]; piso: Optional[str]
    estado: str; criticidad: str; justificacion_criticidad: Optional[str]
    fabricante: Optional[str]; marca: Optional[str]; modelo: Optional[str]
    numero_serie: Optional[str]; numero_parte: Optional[str]
    especificaciones: Optional[str]
    fecha_adquisicion: Optional[date]; fecha_puesta_servicio: Optional[date]
    costo_adquisicion: Optional[float]; valor_residual: float
    vida_util_anos: Optional[float]; metodo_depreciacion: str
    modelo_medicion: str; depreciacion_acumulada: float; deterioro_acumulado: float
    centro_costo: Optional[str]; funcion_requerida: Optional[str]
    garantia_inicio: Optional[date]; garantia_vencimiento: Optional[date]
    fecha_baja: Optional[date]; motivo_baja: Optional[str]; activo: bool
    # Computed
    valor_libros: Optional[float] = None
    depreciacion_anual: Optional[float] = None
    class Config: from_attributes = True


class LocativaActivoDocumentoCreate(BaseModel):
    activo_id: int; tipo: str; nombre: str; descripcion: Optional[str] = None
    archivo_url: Optional[str] = None; fecha_documento: Optional[date] = None
    fecha_vencimiento: Optional[date] = None

class LocativaActivoDocumentoResponse(BaseModel):
    id: int; activo_id: int; tipo: str; nombre: str; descripcion: Optional[str]
    archivo_url: Optional[str]; fecha_documento: Optional[date]
    fecha_vencimiento: Optional[date]
    estado_semaforo: Optional[str] = None
    class Config: from_attributes = True


# ─── Catálogo de Tareas ────────────────────────────────────────────────────────

class LocativaCatalogoTareaCreate(BaseModel):
    codigo: Optional[str] = None; nombre: str; tipo: str = "PREVENTIVO"
    categoria_activo: Optional[str] = None; descripcion: Optional[str] = None
    tiempo_estimado_hrs: Optional[float] = None; epp_requerido: Optional[str] = None
    referencia_normativa: Optional[str] = None; criticidad: str = "MEDIA"; activo: bool = True

class LocativaCatalogoTareaUpdate(BaseModel):
    nombre: Optional[str] = None; tipo: Optional[str] = None
    categoria_activo: Optional[str] = None; descripcion: Optional[str] = None
    tiempo_estimado_hrs: Optional[float] = None; epp_requerido: Optional[str] = None
    referencia_normativa: Optional[str] = None; criticidad: Optional[str] = None
    activo: Optional[bool] = None

class LocativaCatalogoTareaResponse(BaseModel):
    id: int; codigo: Optional[str]; nombre: str; tipo: str
    categoria_activo: Optional[str]; descripcion: Optional[str]
    tiempo_estimado_hrs: Optional[float]; epp_requerido: Optional[str]
    referencia_normativa: Optional[str]; criticidad: str; activo: bool
    class Config: from_attributes = True


# ─── Órdenes de Trabajo ────────────────────────────────────────────────────────

class LocativaOTChecklistItem(BaseModel):
    paso: int; descripcion: str

class LocativaOTMaterialItem(BaseModel):
    descripcion: str; cantidad: float = 1; unidad: str = "UN"
    costo_unitario: Optional[float] = None

class LocativaOTCreate(BaseModel):
    tipo: str = "PREVENTIVO"; activo_id: Optional[int] = None; sede_id: Optional[int] = None
    descripcion: str; prioridad: str = "MEDIA"
    fecha_apertura: date; fecha_programada: Optional[date] = None
    tiempo_estimado_hrs: Optional[float] = None
    tecnico_id: Optional[int] = None; contratista_id: Optional[int] = None
    requiere_permiso: bool = False; requiere_parada: bool = False
    referencia_normativa: Optional[str] = None; observaciones: Optional[str] = None
    checklist: List[LocativaOTChecklistItem] = []
    materiales: List[LocativaOTMaterialItem] = []

class LocativaOTUpdate(BaseModel):
    tipo: Optional[str] = None; descripcion: Optional[str] = None
    prioridad: Optional[str] = None; fecha_programada: Optional[date] = None
    fecha_inicio_real: Optional[date] = None; fecha_cierre: Optional[date] = None
    tiempo_estimado_hrs: Optional[float] = None; tiempo_real_hrs: Optional[float] = None
    tecnico_id: Optional[int] = None; contratista_id: Optional[int] = None
    requiere_permiso: Optional[bool] = None; requiere_parada: Optional[bool] = None
    tiempo_indisponibilidad_hrs: Optional[float] = None
    trabajo_realizado: Optional[str] = None; causa_raiz: Optional[str] = None
    estado_post_intervencion: Optional[str] = None
    costo_mano_obra: Optional[float] = None; costo_materiales: Optional[float] = None
    costo_externo: Optional[float] = None; es_capitalizable: Optional[bool] = None
    observaciones: Optional[str] = None

class LocativaOTEstadoUpdate(BaseModel):
    estado: str; observaciones: Optional[str] = None
    fecha_cierre: Optional[date] = None; tiempo_real_hrs: Optional[float] = None
    trabajo_realizado: Optional[str] = None; causa_raiz: Optional[str] = None
    estado_post_intervencion: Optional[str] = None

class LocativaOTChecklistResponse(BaseModel):
    id: int; paso: int; descripcion: str; completado: bool; observacion: Optional[str]
    class Config: from_attributes = True

class LocativaOTMaterialResponse(BaseModel):
    id: int; descripcion: str; cantidad: float; unidad: str
    costo_unitario: Optional[float]; costo_total: Optional[float]
    class Config: from_attributes = True

class LocativaOTResponse(BaseModel):
    id: int; numero: str; tipo: str; activo_id: Optional[int]; sede_id: Optional[int]
    descripcion: str; prioridad: str; estado: str
    fecha_apertura: date; fecha_programada: Optional[date]
    fecha_inicio_real: Optional[date]; fecha_cierre: Optional[date]
    tiempo_estimado_hrs: Optional[float]; tiempo_real_hrs: Optional[float]
    tecnico_id: Optional[int]; contratista_id: Optional[int]
    requiere_permiso: bool; requiere_parada: bool
    tiempo_indisponibilidad_hrs: Optional[float]
    trabajo_realizado: Optional[str]; causa_raiz: Optional[str]
    estado_post_intervencion: Optional[str]
    costo_mano_obra: float; costo_materiales: float; costo_externo: float
    es_capitalizable: bool; referencia_normativa: Optional[str]; observaciones: Optional[str]
    checklist: List[LocativaOTChecklistResponse] = []
    materiales: List[LocativaOTMaterialResponse] = []
    costo_total: Optional[float] = None
    class Config: from_attributes = True


# ─── Registro de Fallas (ISO 14224) ───────────────────────────────────────────

class LocativaFallaCreate(BaseModel):
    activo_id: int; fecha_deteccion: date; fecha_inicio_falla: Optional[date] = None
    modo_falla_id: Optional[int] = None; descripcion_falla: str
    causa_raiz: Optional[str] = None; parte_fallada: Optional[str] = None
    consecuencia: str = "FALLA_FUNCIONAL_TOTAL"
    detectada_por: str = "REPORTE_USUARIO"
    horas_indisponibilidad: Optional[float] = None
    tiempo_respuesta_hrs: Optional[float] = None
    tiempo_reparacion_hrs: Optional[float] = None
    costo_total: Optional[float] = None
    orden_trabajo_id: Optional[int] = None

class LocativaFallaResponse(BaseModel):
    id: int; activo_id: int; fecha_deteccion: date; fecha_inicio_falla: Optional[date]
    modo_falla_id: Optional[int]; descripcion_falla: str; causa_raiz: Optional[str]
    parte_fallada: Optional[str]; consecuencia: str; detectada_por: str
    horas_indisponibilidad: Optional[float]; tiempo_respuesta_hrs: Optional[float]
    tiempo_reparacion_hrs: Optional[float]; costo_total: Optional[float]
    orden_trabajo_id: Optional[int]
    class Config: from_attributes = True


# ─── Riesgos (ISO 31000) ──────────────────────────────────────────────────────

class LocativaRiesgoCreate(BaseModel):
    codigo: Optional[str] = None; descripcion: str; categoria: str = "OPERACIONAL"
    activo_id: Optional[int] = None; sede_id: Optional[int] = None
    causas: Optional[str] = None; consecuencias: Optional[str] = None
    fuente: str = "INTERNO"; responsable: Optional[str] = None
    fecha_identificacion: Optional[date] = None
    probabilidad: Optional[int] = None
    impacto_personas: Optional[int] = None; impacto_operacional: Optional[int] = None
    impacto_financiero: Optional[int] = None; impacto_ambiental: Optional[int] = None
    controles_existentes: Optional[str] = None

class LocativaRiesgoUpdate(BaseModel):
    descripcion: Optional[str] = None; categoria: Optional[str] = None
    activo_id: Optional[int] = None; sede_id: Optional[int] = None
    causas: Optional[str] = None; consecuencias: Optional[str] = None
    fuente: Optional[str] = None; responsable: Optional[str] = None
    fecha_identificacion: Optional[date] = None
    probabilidad: Optional[int] = None
    impacto_personas: Optional[int] = None; impacto_operacional: Optional[int] = None
    impacto_financiero: Optional[int] = None; impacto_ambiental: Optional[int] = None
    controles_existentes: Optional[str] = None; nivel_residual: Optional[int] = None
    aceptabilidad: Optional[str] = None; estado: Optional[str] = None
    ultima_revision: Optional[date] = None

class LocativaRiesgoResponse(BaseModel):
    id: int; codigo: Optional[str]; descripcion: str; categoria: str
    activo_id: Optional[int]; sede_id: Optional[int]
    causas: Optional[str]; consecuencias: Optional[str]
    fuente: str; responsable: Optional[str]; fecha_identificacion: Optional[date]
    probabilidad: Optional[int]
    impacto_personas: Optional[int]; impacto_operacional: Optional[int]
    impacto_financiero: Optional[int]; impacto_ambiental: Optional[int]
    nivel_inherente: Optional[int]; controles_existentes: Optional[str]
    nivel_residual: Optional[int]; aceptabilidad: Optional[str]
    estado: str; ultima_revision: Optional[date]
    tratamientos: List["LocativaRiesgoTratamientoResponse"] = []
    class Config: from_attributes = True


class LocativaRiesgoTratamientoCreate(BaseModel):
    riesgo_id: int; estrategia: str = "REDUCIR"; descripcion: str
    responsable: Optional[str] = None; fecha_limite: Optional[date] = None
    nivel_residual_objetivo: Optional[int] = None

class LocativaRiesgoTratamientoUpdate(BaseModel):
    estrategia: Optional[str] = None; descripcion: Optional[str] = None
    responsable: Optional[str] = None; fecha_limite: Optional[date] = None
    nivel_residual_objetivo: Optional[int] = None; estado: Optional[str] = None
    observaciones: Optional[str] = None

class LocativaRiesgoTratamientoResponse(BaseModel):
    id: int; riesgo_id: int; estrategia: str; descripcion: str
    responsable: Optional[str]; fecha_limite: Optional[date]
    nivel_residual_objetivo: Optional[int]; estado: str; observaciones: Optional[str]
    class Config: from_attributes = True


# ─── Energía (ISO 50001) ──────────────────────────────────────────────────────

class LocativaMedidorCreate(BaseModel):
    codigo: str; nombre: str; tipo_energia: str = "ELECTRICIDAD"; unidad: str = "kWh"
    sede_id: Optional[int] = None; espacio_id: Optional[int] = None
    activo_id: Optional[int] = None; tarifa_unidad: Optional[float] = None
    linea_base_mensual: Optional[float] = None; activo: bool = True

class LocativaMedidorUpdate(BaseModel):
    nombre: Optional[str] = None; tipo_energia: Optional[str] = None
    unidad: Optional[str] = None; tarifa_unidad: Optional[float] = None
    linea_base_mensual: Optional[float] = None; activo: Optional[bool] = None

class LocativaMedidorResponse(BaseModel):
    id: int; codigo: str; nombre: str; tipo_energia: str; unidad: str
    sede_id: Optional[int]; espacio_id: Optional[int]; activo_id: Optional[int]
    tarifa_unidad: Optional[float]; linea_base_mensual: Optional[float]; activo: bool
    class Config: from_attributes = True


class LocativaLecturaCreate(BaseModel):
    medidor_id: int; fecha: date; valor_lectura: float
    observaciones: Optional[str] = None

class LocativaLecturaResponse(BaseModel):
    id: int; medidor_id: int; fecha: date; valor_lectura: float
    consumo_periodo: Optional[float]; costo_periodo: Optional[float]
    anomalo: bool; observaciones: Optional[str]
    class Config: from_attributes = True


# ─── Dashboard KPIs ────────────────────────────────────────────────────────────

class LocativaKPIs(BaseModel):
    # Activos
    total_activos: int = 0
    activos_operativos: int = 0
    activos_mantenimiento: int = 0
    activos_fuera_servicio: int = 0
    valor_libros_total: float = 0
    # OTs
    ots_abiertas: int = 0
    ots_en_progreso: int = 0
    ots_vencidas: int = 0
    ots_cerradas_mes: int = 0
    cumplimiento_preventivo: float = 0  # %
    costo_mantenimiento_mes: float = 0
    # Confiabilidad (ISO 14224)
    total_fallas_mes: int = 0
    mttr_promedio: float = 0    # Horas
    disponibilidad_promedio: float = 0  # %
    # Riesgos (ISO 31000)
    riesgos_inaceptables: int = 0
    riesgos_tolerables: int = 0
    riesgos_total: int = 0
    # Energía (ISO 50001)
    consumo_energia_mes: float = 0
    costo_energia_mes: float = 0
    # Documentos
    documentos_por_vencer: int = 0
    contratos_por_vencer: int = 0
