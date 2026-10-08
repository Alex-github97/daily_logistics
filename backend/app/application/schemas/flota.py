from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ─── Catálogos ─────────────────────────────────────────────────────────────────

class FlotaMarcaCreate(BaseModel):
    nombre: str
    activo: bool = True

class FlotaMarcaUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None

class FlotaMarcaResponse(BaseModel):
    id: int; nombre: str; activo: bool
    class Config: from_attributes = True


class FlotaTipoVehiculoCreate(BaseModel):
    nombre: str; descripcion: Optional[str] = None; activo: bool = True

class FlotaTipoVehiculoUpdate(BaseModel):
    nombre: Optional[str] = None; descripcion: Optional[str] = None; activo: Optional[bool] = None

class FlotaTipoVehiculoResponse(BaseModel):
    id: int; nombre: str; descripcion: Optional[str]; activo: bool
    class Config: from_attributes = True


class FlotaTipoCombustibleCreate(BaseModel):
    nombre: str; unidad: str = "GALON"; activo: bool = True

class FlotaTipoCombustibleUpdate(BaseModel):
    nombre: Optional[str] = None; unidad: Optional[str] = None; activo: Optional[bool] = None

class FlotaTipoCombustibleResponse(BaseModel):
    id: int; nombre: str; unidad: str; activo: bool
    class Config: from_attributes = True


class FlotaCentroCostoCreate(BaseModel):
    codigo: str; nombre: str; descripcion: Optional[str] = None; activo: bool = True

class FlotaCentroCostoUpdate(BaseModel):
    codigo: Optional[str] = None; nombre: Optional[str] = None
    descripcion: Optional[str] = None; activo: Optional[bool] = None

class FlotaCentroCostoResponse(BaseModel):
    id: int; codigo: str; nombre: str; descripcion: Optional[str]; activo: bool
    class Config: from_attributes = True


class FlotaProveedorCreate(BaseModel):
    nombre: str; nit: Optional[str] = None; contacto: Optional[str] = None
    telefono: Optional[str] = None; email: Optional[str] = None
    tipo: str = "GENERAL"; activo: bool = True

class FlotaProveedorUpdate(BaseModel):
    nombre: Optional[str] = None; nit: Optional[str] = None; contacto: Optional[str] = None
    telefono: Optional[str] = None; email: Optional[str] = None
    tipo: Optional[str] = None; activo: Optional[bool] = None

class FlotaProveedorResponse(BaseModel):
    id: int; nombre: str; nit: Optional[str]; contacto: Optional[str]
    telefono: Optional[str]; email: Optional[str]; tipo: str; activo: bool
    class Config: from_attributes = True


# ─── Vehículos ─────────────────────────────────────────────────────────────────

class FlotaVehiculoCreate(BaseModel):
    placa: str
    marca_id: Optional[int] = None
    tipo_vehiculo_id: Optional[int] = None
    linea: Optional[str] = None
    modelo: Optional[int] = None
    color: Optional[str] = None
    tipo_medicion: str = "KM"
    tipo_trabajo: str = "NORMAL"
    combustible_principal_id: Optional[int] = None
    combustible_secundario_id: Optional[int] = None
    centro_costo_id: Optional[int] = None
    ciudad: Optional[str] = None
    nro_motor: Optional[str] = None
    nro_serie: Optional[str] = None
    fecha_compra: Optional[date] = None
    medicion_compra: float = 0
    precio_compra: Optional[float] = None
    distancia_max_dia: Optional[float] = None
    distancia_prom_dia: Optional[float] = None
    horas_operativas_mes: Optional[float] = None
    rendimiento_ideal: Optional[float] = None
    observaciones: Optional[str] = None

class FlotaVehiculoUpdate(BaseModel):
    placa: Optional[str] = None
    marca_id: Optional[int] = None
    tipo_vehiculo_id: Optional[int] = None
    linea: Optional[str] = None
    modelo: Optional[int] = None
    color: Optional[str] = None
    tipo_medicion: Optional[str] = None
    tipo_trabajo: Optional[str] = None
    combustible_principal_id: Optional[int] = None
    combustible_secundario_id: Optional[int] = None
    centro_costo_id: Optional[int] = None
    ciudad: Optional[str] = None
    nro_motor: Optional[str] = None
    nro_serie: Optional[str] = None
    fecha_compra: Optional[date] = None
    medicion_compra: Optional[float] = None
    precio_compra: Optional[float] = None
    distancia_max_dia: Optional[float] = None
    distancia_prom_dia: Optional[float] = None
    horas_operativas_mes: Optional[float] = None
    rendimiento_ideal: Optional[float] = None
    observaciones: Optional[str] = None

class FlotaVehiculoBaja(BaseModel):
    fecha_baja: date
    motivo_baja: str

class FlotaMarcaBrief(BaseModel):
    id: int; nombre: str
    class Config: from_attributes = True

class FlotaTipoVehiculoBrief(BaseModel):
    id: int; nombre: str
    class Config: from_attributes = True

class FlotaVehiculoResponse(BaseModel):
    id: int; placa: str
    marca_id: Optional[int]; marca: Optional[FlotaMarcaBrief]
    tipo_vehiculo_id: Optional[int]; tipo_vehiculo: Optional[FlotaTipoVehiculoBrief]
    linea: Optional[str]; modelo: Optional[int]; color: Optional[str]
    tipo_medicion: str; tipo_trabajo: str
    combustible_principal_id: Optional[int]; combustible_secundario_id: Optional[int]
    centro_costo_id: Optional[int]; ciudad: Optional[str]
    nro_motor: Optional[str]; nro_serie: Optional[str]
    fecha_compra: Optional[date]; medicion_compra: float; precio_compra: Optional[float]
    distancia_max_dia: Optional[float]; distancia_prom_dia: Optional[float]
    horas_operativas_mes: Optional[float]; rendimiento_ideal: Optional[float]
    fecha_baja: Optional[date]; motivo_baja: Optional[str]
    observaciones: Optional[str]; activo: bool
    created_at: Optional[datetime]
    class Config: from_attributes = True


# ─── Mediciones ────────────────────────────────────────────────────────────────

class FlotaMedicionCreate(BaseModel):
    vehiculo_id: int; tipo: str = "ODOMETRO"; valor: float
    fecha: date; observaciones: Optional[str] = None

class FlotaMedicionResponse(BaseModel):
    id: int; vehiculo_id: int; tipo: str; valor: float
    fecha: date; observaciones: Optional[str]; created_at: Optional[datetime]
    class Config: from_attributes = True


# ─── Documentos Vehículo ───────────────────────────────────────────────────────

class FlotaDocumentoVehiculoCreate(BaseModel):
    vehiculo_id: int; tipo_documento: str; numero: Optional[str] = None
    fecha_expedicion: Optional[date] = None; fecha_vencimiento: date
    entidad_emisora: Optional[str] = None; archivo_url: Optional[str] = None

class FlotaDocumentoVehiculoUpdate(BaseModel):
    tipo_documento: Optional[str] = None; numero: Optional[str] = None
    fecha_expedicion: Optional[date] = None; fecha_vencimiento: Optional[date] = None
    entidad_emisora: Optional[str] = None; archivo_url: Optional[str] = None

class FlotaDocumentoVehiculoResponse(BaseModel):
    id: int; vehiculo_id: int; tipo_documento: str; numero: Optional[str]
    fecha_expedicion: Optional[date]; fecha_vencimiento: date
    entidad_emisora: Optional[str]; archivo_url: Optional[str]
    estado_semaforo: str = "VIGENTE"  # calculado en endpoint
    dias_para_vencer: Optional[int] = None
    created_at: Optional[datetime]
    class Config: from_attributes = True


# ─── Personal ──────────────────────────────────────────────────────────────────

class FlotaPersonalCreate(BaseModel):
    tipo: str = "CONDUCTOR"
    nombres: str; apellidos: str
    tipo_documento: str = "CC"; numero_documento: str
    fecha_nacimiento: Optional[date] = None
    telefono: Optional[str] = None; email: Optional[str] = None
    direccion: Optional[str] = None; foto_url: Optional[str] = None
    especialidad: Optional[str] = None; conductor_id: Optional[int] = None

class FlotaPersonalUpdate(BaseModel):
    tipo: Optional[str] = None
    nombres: Optional[str] = None; apellidos: Optional[str] = None
    tipo_documento: Optional[str] = None; numero_documento: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    telefono: Optional[str] = None; email: Optional[str] = None
    direccion: Optional[str] = None; foto_url: Optional[str] = None
    especialidad: Optional[str] = None; activo: Optional[bool] = None

class FlotaPersonalResponse(BaseModel):
    id: int; tipo: str; nombres: str; apellidos: str
    tipo_documento: str; numero_documento: str
    fecha_nacimiento: Optional[date]; telefono: Optional[str]; email: Optional[str]
    direccion: Optional[str]; foto_url: Optional[str]; especialidad: Optional[str]
    conductor_id: Optional[int]; activo: bool
    created_at: Optional[datetime]
    class Config: from_attributes = True


# ─── Documentos Personal ───────────────────────────────────────────────────────

class FlotaDocumentoPersonalCreate(BaseModel):
    personal_id: int; tipo_documento: str; numero: Optional[str] = None
    categoria: Optional[str] = None
    fecha_expedicion: Optional[date] = None; fecha_vencimiento: date
    archivo_url: Optional[str] = None

class FlotaDocumentoPersonalResponse(BaseModel):
    id: int; personal_id: int; tipo_documento: str; numero: Optional[str]
    categoria: Optional[str]; fecha_expedicion: Optional[date]; fecha_vencimiento: date
    archivo_url: Optional[str]; estado_semaforo: str = "VIGENTE"
    dias_para_vencer: Optional[int] = None; created_at: Optional[datetime]
    class Config: from_attributes = True


# ─── Combustible ───────────────────────────────────────────────────────────────

class FlotaCombustibleCreate(BaseModel):
    vehiculo_id: int; fecha: date; medicion_actual: Optional[float] = None
    cantidad: float; unidad: str = "GALON"
    valor_unitario: Optional[float] = None; valor_total: Optional[float] = None
    tipo_combustible_id: Optional[int] = None; proveedor_id: Optional[int] = None
    estacion: Optional[str] = None; numero_factura: Optional[str] = None
    archivo_url: Optional[str] = None; observaciones: Optional[str] = None

class FlotaCombustibleUpdate(BaseModel):
    fecha: Optional[date] = None; medicion_actual: Optional[float] = None
    cantidad: Optional[float] = None; unidad: Optional[str] = None
    valor_unitario: Optional[float] = None; valor_total: Optional[float] = None
    tipo_combustible_id: Optional[int] = None; proveedor_id: Optional[int] = None
    estacion: Optional[str] = None; numero_factura: Optional[str] = None
    observaciones: Optional[str] = None

class FlotaVehiculoBrief(BaseModel):
    id: int; placa: str
    class Config: from_attributes = True

class FlotaCombustibleResponse(BaseModel):
    id: int; vehiculo_id: int; vehiculo: Optional[FlotaVehiculoBrief]
    fecha: date; medicion_actual: Optional[float]; cantidad: float; unidad: str
    valor_unitario: Optional[float]; valor_total: Optional[float]
    tipo_combustible_id: Optional[int]; proveedor_id: Optional[int]
    estacion: Optional[str]; numero_factura: Optional[str]; observaciones: Optional[str]
    created_at: Optional[datetime]
    class Config: from_attributes = True


# ─── Tipos de Trabajo ──────────────────────────────────────────────────────────

class FlotaTipoTrabajoCreate(BaseModel):
    nombre: str; sistema: Optional[str] = None; subsistema: Optional[str] = None
    tipo: str = "PREVENTIVO"; nivel_criticidad: str = "MEDIA"
    tiempo_estimado_horas: Optional[float] = None; costo_estimado: Optional[float] = None
    periodicidad_tipo: Optional[str] = None; periodicidad_valor: Optional[float] = None

class FlotaTipoTrabajoUpdate(BaseModel):
    nombre: Optional[str] = None; sistema: Optional[str] = None; subsistema: Optional[str] = None
    tipo: Optional[str] = None; nivel_criticidad: Optional[str] = None
    tiempo_estimado_horas: Optional[float] = None; costo_estimado: Optional[float] = None
    periodicidad_tipo: Optional[str] = None; periodicidad_valor: Optional[float] = None
    activo: Optional[bool] = None

class FlotaTipoTrabajoResponse(BaseModel):
    id: int; nombre: str; sistema: Optional[str]; subsistema: Optional[str]
    tipo: str; nivel_criticidad: str
    tiempo_estimado_horas: Optional[float]; costo_estimado: Optional[float]
    periodicidad_tipo: Optional[str]; periodicidad_valor: Optional[float]; activo: bool
    class Config: from_attributes = True


# ─── Órdenes de Trabajo ────────────────────────────────────────────────────────

class FlotaOrdenDetalleCreate(BaseModel):
    tipo_trabajo_id: Optional[int] = None; descripcion: str
    costo_repuestos: float = 0; costo_mano_obra: float = 0

class FlotaOrdenDetalleResponse(BaseModel):
    id: int; orden_id: int; tipo_trabajo_id: Optional[int]
    descripcion: str; costo_repuestos: float; costo_mano_obra: float; estado: str
    class Config: from_attributes = True

class FlotaOrdenCreate(BaseModel):
    vehiculo_id: int; fecha_apertura: date
    medicion_apertura: Optional[float] = None; personal_id: Optional[int] = None
    tipo_taller: str = "INTERNO"; proveedor_id: Optional[int] = None
    observaciones: Optional[str] = None
    detalles: List[FlotaOrdenDetalleCreate] = []

class FlotaOrdenUpdate(BaseModel):
    fecha_cierre: Optional[date] = None; medicion_cierre: Optional[float] = None
    personal_id: Optional[int] = None; tipo_taller: Optional[str] = None
    proveedor_id: Optional[int] = None; observaciones: Optional[str] = None
    costo_repuestos: Optional[float] = None; costo_mano_obra: Optional[float] = None

class FlotaOrdenEstado(BaseModel):
    estado: str  # ABIERTA, EN_PROCESO, CERRADA, CANCELADA

class FlotaPersonalBrief(BaseModel):
    id: int; nombres: str; apellidos: str
    class Config: from_attributes = True

class FlotaOrdenResponse(BaseModel):
    id: int; numero: str; vehiculo_id: int; vehiculo: Optional[FlotaVehiculoBrief]
    fecha_apertura: date; fecha_cierre: Optional[date]
    medicion_apertura: Optional[float]; medicion_cierre: Optional[float]
    personal_id: Optional[int]; mecanico: Optional[FlotaPersonalBrief]
    tipo_taller: str; proveedor_id: Optional[int]; estado: str
    costo_repuestos: float; costo_mano_obra: float
    observaciones: Optional[str]; creado_por_id: Optional[int]
    detalles: List[FlotaOrdenDetalleResponse] = []
    created_at: Optional[datetime]
    class Config: from_attributes = True


# ─── Repuestos ─────────────────────────────────────────────────────────────────

class FlotaRepuestoCreate(BaseModel):
    codigo: str; nombre: str; descripcion: Optional[str] = None
    categoria: Optional[str] = None; sistema: Optional[str] = None
    unidad: str = "UNIDAD"; costo_referencia: Optional[float] = None
    stock_minimo: int = 0; activo: bool = True

class FlotaRepuestoUpdate(BaseModel):
    codigo: Optional[str] = None; nombre: Optional[str] = None
    descripcion: Optional[str] = None; categoria: Optional[str] = None
    sistema: Optional[str] = None; unidad: Optional[str] = None
    costo_referencia: Optional[float] = None; stock_minimo: Optional[int] = None
    activo: Optional[bool] = None

class FlotaRepuestoResponse(BaseModel):
    id: int; codigo: str; nombre: str; descripcion: Optional[str]
    categoria: Optional[str]; sistema: Optional[str]; unidad: str
    costo_referencia: Optional[float]; stock_minimo: int; activo: bool
    class Config: from_attributes = True


# ─── Rutinas de Mantenimiento ──────────────────────────────────────────────────

class FlotaRutinaTrabajoItem(BaseModel):
    tipo_trabajo_id: int; orden: int = 1
    obligatorio: bool = True; instrucciones: Optional[str] = None

class FlotaRutinaRepuestoItem(BaseModel):
    repuesto_id: int; cantidad: float = 1; obligatorio: bool = True

class FlotaRutinaCreate(BaseModel):
    codigo: str; nombre: str; descripcion: Optional[str] = None
    tipo: str = "PREVENTIVO"; nivel_criticidad: str = "MEDIA"
    aplica_tipo_trabajo_severo: bool = False
    intervalo_km: Optional[float] = None; intervalo_horas: Optional[float] = None
    intervalo_dias: Optional[int] = None; tolerancia_pct: float = 10.0
    tiempo_estimado_horas: Optional[float] = None
    costo_estimado_mano_obra: Optional[float] = None
    instrucciones_generales: Optional[str] = None
    trabajos: List[FlotaRutinaTrabajoItem] = []
    repuestos: List[FlotaRutinaRepuestoItem] = []

class FlotaRutinaUpdate(BaseModel):
    nombre: Optional[str] = None; descripcion: Optional[str] = None
    tipo: Optional[str] = None; nivel_criticidad: Optional[str] = None
    aplica_tipo_trabajo_severo: Optional[bool] = None
    intervalo_km: Optional[float] = None; intervalo_horas: Optional[float] = None
    intervalo_dias: Optional[int] = None; tolerancia_pct: Optional[float] = None
    tiempo_estimado_horas: Optional[float] = None
    costo_estimado_mano_obra: Optional[float] = None
    instrucciones_generales: Optional[str] = None; activo: Optional[bool] = None
    trabajos: Optional[List[FlotaRutinaTrabajoItem]] = None
    repuestos: Optional[List[FlotaRutinaRepuestoItem]] = None

class FlotaRutinaTrabajoResponse(BaseModel):
    id: int; rutina_id: int; tipo_trabajo_id: int
    tipo_trabajo_nombre: Optional[str] = None
    orden: int; obligatorio: bool; instrucciones: Optional[str]
    class Config: from_attributes = True

class FlotaRutinaRepuestoResponse(BaseModel):
    id: int; rutina_id: int; repuesto_id: int
    repuesto_codigo: Optional[str] = None; repuesto_nombre: Optional[str] = None
    repuesto_unidad: Optional[str] = None; costo_referencia: Optional[float] = None
    cantidad: float; obligatorio: bool
    class Config: from_attributes = True

class FlotaRutinaResponse(BaseModel):
    id: int; codigo: str; nombre: str; descripcion: Optional[str]
    tipo: str; nivel_criticidad: str; aplica_tipo_trabajo_severo: bool
    intervalo_km: Optional[float]; intervalo_horas: Optional[float]; intervalo_dias: Optional[int]
    tolerancia_pct: float; tiempo_estimado_horas: Optional[float]
    costo_estimado_mano_obra: Optional[float]; instrucciones_generales: Optional[str]; activo: bool
    trabajos: List[FlotaRutinaTrabajoResponse] = []
    repuestos: List[FlotaRutinaRepuestoResponse] = []
    class Config: from_attributes = True


# ─── Secuencias de Mantenimiento ───────────────────────────────────────────────

class FlotaSecuenciaRutinaItem(BaseModel):
    rutina_id: int; orden: int = 1
    intervalo_km_override: Optional[float] = None
    intervalo_dias_override: Optional[int] = None; notas: Optional[str] = None

class FlotaSecuenciaCreate(BaseModel):
    codigo: str; nombre: str; descripcion: Optional[str] = None
    aplica_tipo_trabajo: Optional[str] = None; activo: bool = True
    rutinas: List[FlotaSecuenciaRutinaItem] = []

class FlotaSecuenciaUpdate(BaseModel):
    nombre: Optional[str] = None; descripcion: Optional[str] = None
    aplica_tipo_trabajo: Optional[str] = None; activo: Optional[bool] = None
    rutinas: Optional[List[FlotaSecuenciaRutinaItem]] = None

class FlotaSecuenciaRutinaResponse(BaseModel):
    id: int; secuencia_id: int; rutina_id: int
    rutina_codigo: Optional[str] = None; rutina_nombre: Optional[str] = None
    orden: int; intervalo_km_override: Optional[float]; intervalo_dias_override: Optional[int]
    notas: Optional[str]
    class Config: from_attributes = True

class FlotaSecuenciaResponse(BaseModel):
    id: int; codigo: str; nombre: str; descripcion: Optional[str]
    aplica_tipo_trabajo: Optional[str]; activo: bool
    rutinas: List[FlotaSecuenciaRutinaResponse] = []
    total_asignaciones: int = 0
    class Config: from_attributes = True


# ─── Grupos de Vehículos ───────────────────────────────────────────────────────

class FlotaGrupoCreate(BaseModel):
    nombre: str; descripcion: Optional[str] = None
    tipo_vehiculo_id: Optional[int] = None; marca_id: Optional[int] = None
    tipo_trabajo_filtro: Optional[str] = None; ciudad: Optional[str] = None
    activo: bool = True

class FlotaGrupoUpdate(BaseModel):
    nombre: Optional[str] = None; descripcion: Optional[str] = None
    tipo_vehiculo_id: Optional[int] = None; marca_id: Optional[int] = None
    tipo_trabajo_filtro: Optional[str] = None; ciudad: Optional[str] = None
    activo: Optional[bool] = None

class FlotaGrupoResponse(BaseModel):
    id: int; nombre: str; descripcion: Optional[str]
    tipo_vehiculo_id: Optional[int]; tipo_vehiculo_nombre: Optional[str] = None
    marca_id: Optional[int]; marca_nombre: Optional[str] = None
    tipo_trabajo_filtro: Optional[str]; ciudad: Optional[str]; activo: bool
    vehiculos_count: int = 0
    class Config: from_attributes = True


# ─── Asignaciones de Secuencias ────────────────────────────────────────────────

class FlotaAsignacionCreate(BaseModel):
    secuencia_id: int
    vehiculo_id: Optional[int] = None; grupo_id: Optional[int] = None
    fecha_inicio: date; medicion_inicio: Optional[float] = None
    activa: bool = True; notas: Optional[str] = None

class FlotaAsignacionUpdate(BaseModel):
    activa: Optional[bool] = None; notas: Optional[str] = None
    medicion_inicio: Optional[float] = None

class FlotaAsignacionResponse(BaseModel):
    id: int; secuencia_id: int; secuencia_nombre: Optional[str] = None
    vehiculo_id: Optional[int]; vehiculo_placa: Optional[str] = None
    grupo_id: Optional[int]; grupo_nombre: Optional[str] = None
    fecha_inicio: date; medicion_inicio: Optional[float]; activa: bool; notas: Optional[str]
    class Config: from_attributes = True


# ─── FMEA / RCM — Modos de Falla ──────────────────────────────────────────────

class FlotaModoFallaCreate(BaseModel):
    sistema: str; subsistema: Optional[str] = None; funcion: str
    falla_funcional: str; modo_falla: str
    efecto: Optional[str] = None; causa: Optional[str] = None
    severidad: Optional[int] = None; ocurrencia: Optional[int] = None; deteccion: Optional[int] = None
    accion_recomendada: Optional[str] = None
    tipo_vehiculo_id: Optional[int] = None; rutina_correctiva_id: Optional[int] = None
    activo: bool = True

class FlotaModoFallaUpdate(BaseModel):
    sistema: Optional[str] = None; subsistema: Optional[str] = None
    funcion: Optional[str] = None; falla_funcional: Optional[str] = None; modo_falla: Optional[str] = None
    efecto: Optional[str] = None; causa: Optional[str] = None
    severidad: Optional[int] = None; ocurrencia: Optional[int] = None; deteccion: Optional[int] = None
    accion_recomendada: Optional[str] = None
    tipo_vehiculo_id: Optional[int] = None; rutina_correctiva_id: Optional[int] = None
    activo: Optional[bool] = None

class FlotaModoFallaResponse(BaseModel):
    id: int; sistema: str; subsistema: Optional[str]; funcion: str
    falla_funcional: str; modo_falla: str; efecto: Optional[str]; causa: Optional[str]
    severidad: Optional[int]; ocurrencia: Optional[int]; deteccion: Optional[int]; rpn: Optional[int]
    accion_recomendada: Optional[str]; tipo_vehiculo_id: Optional[int]
    rutina_correctiva_id: Optional[int]; rutina_nombre: Optional[str] = None; activo: bool
    class Config: from_attributes = True


# ─── CBM — Umbrales de Condición ──────────────────────────────────────────────

class FlotaUmbralCBMCreate(BaseModel):
    parametro: str; descripcion: Optional[str] = None; unidad: Optional[str] = None
    umbral_advertencia: Optional[float] = None; umbral_critico: Optional[float] = None
    direccion: str = "MAYOR"
    vehiculo_id: Optional[int] = None; tipo_vehiculo_id: Optional[int] = None
    rutina_trigger_id: Optional[int] = None; activo: bool = True

class FlotaUmbralCBMUpdate(BaseModel):
    parametro: Optional[str] = None; descripcion: Optional[str] = None; unidad: Optional[str] = None
    umbral_advertencia: Optional[float] = None; umbral_critico: Optional[float] = None
    direccion: Optional[str] = None
    vehiculo_id: Optional[int] = None; tipo_vehiculo_id: Optional[int] = None
    rutina_trigger_id: Optional[int] = None; activo: Optional[bool] = None

class FlotaUmbralCBMResponse(BaseModel):
    id: int; parametro: str; descripcion: Optional[str]; unidad: Optional[str]
    umbral_advertencia: Optional[float]; umbral_critico: Optional[float]; direccion: str
    vehiculo_id: Optional[int]; vehiculo_placa: Optional[str] = None
    tipo_vehiculo_id: Optional[int]; tipo_vehiculo_nombre: Optional[str] = None
    rutina_trigger_id: Optional[int]; rutina_nombre: Optional[str] = None; activo: bool
    class Config: from_attributes = True


# ─── Próximos Mantenimientos ───────────────────────────────────────────────────

class FlotaProximoMantenimiento(BaseModel):
    vehiculo_id: int; vehiculo_placa: str
    rutina_id: int; rutina_codigo: str; rutina_nombre: str
    secuencia_nombre: Optional[str]
    tipo: str; nivel_criticidad: str
    medicion_actual: Optional[float]
    intervalo_km: Optional[float]; km_restantes: Optional[float]
    intervalo_dias: Optional[int]; dias_restantes: Optional[int]
    vencido: bool


# ─── Dashboard KPIs ────────────────────────────────────────────────────────────

class FlotaKPIs(BaseModel):
    total_vehiculos: int
    vehiculos_activos: int
    vehiculos_en_mantenimiento: int
    total_personal: int
    conductores_activos: int
    mecanicos: int
    ordenes_abiertas: int
    ordenes_en_proceso: int
    documentos_vencidos: int
    documentos_por_vencer: int
    litros_mes_actual: float
    costo_combustible_mes: float
    costo_mantenimiento_mes: float
