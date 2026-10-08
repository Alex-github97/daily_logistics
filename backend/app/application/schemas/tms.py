"""
Módulo TMS (Transportation Management System) — Schemas Pydantic v2
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from app.infrastructure.models.tms import (
    TipoVehiculoTMSEnum,
    TipoCarroceriaTMSEnum,
    EstadoVehiculoTMSEnum,
    TipoServicioTMSEnum,
    EstadoViajeTMSEnum,
    TipoParadaTMSEnum,
    EstadoParadaTMSEnum,
    TipoEventoTMSEnum,
    TipoDocumentoTMSEnum,
    EstadoDocumentoTMSEnum,
    EstadoLiquidacionTMSEnum,
    NivelAlertaTMSEnum,
    TipoAlertaTMSEnum,
)


# ─── TMSZona ───────────────────────────────────────────────────────────────────

class TMSZonaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    ciudades: Optional[str] = None


class TMSZonaUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    ciudades: Optional[str] = None
    activo: Optional[bool] = None


class TMSZonaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: Optional[str] = None
    ciudades: Optional[str] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── TMSTipoServicio ───────────────────────────────────────────────────────────

class TMSTipoServicioCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    codigo: str


class TMSTipoServicioUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    codigo: Optional[str] = None
    activo: Optional[bool] = None


class TMSTipoServicioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: Optional[str] = None
    codigo: str
    activo: bool
    created_at: Optional[datetime] = None


# ─── TMSVehiculo ──────────────────────────────────────────────────────────────

class TMSVehiculoCreate(BaseModel):
    placa: str
    tipo_vehiculo: TipoVehiculoTMSEnum
    tipo_carroceria: Optional[TipoCarroceriaTMSEnum] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    anio: Optional[int] = None
    configuracion: Optional[str] = None
    capacidad_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    num_ejes: Optional[int] = None
    peso_bruto_kg: Optional[float] = None
    empresa_id: Optional[int] = None
    flota_vehiculo_id: Optional[int] = None
    propietario: Optional[str] = None


class TMSVehiculoUpdate(BaseModel):
    placa: Optional[str] = None
    tipo_vehiculo: Optional[TipoVehiculoTMSEnum] = None
    tipo_carroceria: Optional[TipoCarroceriaTMSEnum] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    anio: Optional[int] = None
    configuracion: Optional[str] = None
    capacidad_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    num_ejes: Optional[int] = None
    peso_bruto_kg: Optional[float] = None
    estado_operativo: Optional[EstadoVehiculoTMSEnum] = None
    empresa_id: Optional[int] = None
    flota_vehiculo_id: Optional[int] = None
    propietario: Optional[str] = None
    activo: Optional[bool] = None


class TMSVehiculoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    placa: str
    tipo_vehiculo: TipoVehiculoTMSEnum
    tipo_carroceria: Optional[TipoCarroceriaTMSEnum] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    anio: Optional[int] = None
    configuracion: Optional[str] = None
    capacidad_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    num_ejes: Optional[int] = None
    peso_bruto_kg: Optional[float] = None
    estado_operativo: EstadoVehiculoTMSEnum
    empresa_id: Optional[int] = None
    flota_vehiculo_id: Optional[int] = None
    propietario: Optional[str] = None
    activo: bool
    viajes_activos: int = 0
    created_at: Optional[datetime] = None


# ─── TMSViaje ─────────────────────────────────────────────────────────────────

class TMSViajeCreate(BaseModel):
    tipo_servicio: TipoServicioTMSEnum
    vehiculo_id: Optional[int] = None
    conductor_hcm_id: Optional[int] = None
    conductor_legacy_id: Optional[int] = None
    empresa_id: Optional[int] = None
    generador_id: Optional[int] = None
    flete_id: Optional[int] = None
    wms_despacho_id: Optional[int] = None
    origen_ciudad: Optional[str] = None
    origen_direccion: Optional[str] = None
    origen_lat: Optional[float] = None
    origen_lng: Optional[float] = None
    destino_ciudad: Optional[str] = None
    destino_direccion: Optional[str] = None
    destino_lat: Optional[float] = None
    destino_lng: Optional[float] = None
    fecha_programada_cargue: Optional[datetime] = None
    fecha_programada_entrega: Optional[datetime] = None
    distancia_km: Optional[float] = None
    peso_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    num_entregas: int = 1
    descripcion_carga: Optional[str] = None
    valor_flete: Optional[float] = None
    notas: Optional[str] = None


class TMSViajeUpdate(BaseModel):
    tipo_servicio: Optional[TipoServicioTMSEnum] = None
    estado: Optional[EstadoViajeTMSEnum] = None
    vehiculo_id: Optional[int] = None
    conductor_hcm_id: Optional[int] = None
    conductor_legacy_id: Optional[int] = None
    empresa_id: Optional[int] = None
    generador_id: Optional[int] = None
    flete_id: Optional[int] = None
    wms_despacho_id: Optional[int] = None
    origen_ciudad: Optional[str] = None
    origen_direccion: Optional[str] = None
    origen_lat: Optional[float] = None
    origen_lng: Optional[float] = None
    destino_ciudad: Optional[str] = None
    destino_direccion: Optional[str] = None
    destino_lat: Optional[float] = None
    destino_lng: Optional[float] = None
    fecha_programada_cargue: Optional[datetime] = None
    fecha_real_cargue: Optional[datetime] = None
    fecha_programada_entrega: Optional[datetime] = None
    fecha_real_entrega: Optional[datetime] = None
    distancia_km: Optional[float] = None
    peso_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    num_entregas: Optional[int] = None
    descripcion_carga: Optional[str] = None
    valor_flete: Optional[float] = None
    otif_on_time: Optional[bool] = None
    otif_in_full: Optional[bool] = None
    notas: Optional[str] = None


class TMSViajeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    tipo_servicio: TipoServicioTMSEnum
    estado: EstadoViajeTMSEnum
    vehiculo_id: Optional[int] = None
    vehiculo_placa: Optional[str] = None
    conductor_hcm_id: Optional[int] = None
    conductor_nombre: Optional[str] = None
    conductor_legacy_id: Optional[int] = None
    empresa_id: Optional[int] = None
    generador_id: Optional[int] = None
    generador_nombre: Optional[str] = None
    flete_id: Optional[int] = None
    wms_despacho_id: Optional[int] = None
    origen_ciudad: Optional[str] = None
    destino_ciudad: Optional[str] = None
    origen_direccion: Optional[str] = None
    destino_direccion: Optional[str] = None
    fecha_programada_cargue: Optional[datetime] = None
    fecha_real_cargue: Optional[datetime] = None
    fecha_programada_entrega: Optional[datetime] = None
    fecha_real_entrega: Optional[datetime] = None
    distancia_km: Optional[float] = None
    peso_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    num_entregas: int
    valor_flete: Optional[float] = None
    otif_on_time: Optional[bool] = None
    otif_in_full: Optional[bool] = None
    # Qué se transportó. Es lo único que identifica la carga en un listado, y
    # sin ello la torre de control muestra viajes sin decir de qué son.
    descripcion_carga: Optional[str] = None
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── TMSParada ────────────────────────────────────────────────────────────────

class TMSParadaCreate(BaseModel):
    viaje_id: int
    secuencia: int
    tipo: TipoParadaTMSEnum
    ciudad: str
    direccion: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    tiempo_estimado_llegada: Optional[datetime] = None
    tiempo_estimado_salida: Optional[datetime] = None
    contacto: Optional[str] = None
    telefono_contacto: Optional[str] = None
    observaciones: Optional[str] = None


class TMSParadaUpdate(BaseModel):
    viaje_id: Optional[int] = None
    secuencia: Optional[int] = None
    tipo: Optional[TipoParadaTMSEnum] = None
    ciudad: Optional[str] = None
    direccion: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    estado: Optional[EstadoParadaTMSEnum] = None
    tiempo_estimado_llegada: Optional[datetime] = None
    tiempo_real_llegada: Optional[datetime] = None
    tiempo_estimado_salida: Optional[datetime] = None
    tiempo_real_salida: Optional[datetime] = None
    contacto: Optional[str] = None
    telefono_contacto: Optional[str] = None
    observaciones: Optional[str] = None


class TMSParadaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viaje_id: int
    secuencia: int
    tipo: TipoParadaTMSEnum
    ciudad: str
    direccion: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    estado: EstadoParadaTMSEnum
    tiempo_estimado_llegada: Optional[datetime] = None
    tiempo_real_llegada: Optional[datetime] = None
    tiempo_estimado_salida: Optional[datetime] = None
    tiempo_real_salida: Optional[datetime] = None
    contacto: Optional[str] = None
    telefono_contacto: Optional[str] = None
    observaciones: Optional[str] = None


# ─── TMSEvento ────────────────────────────────────────────────────────────────

class TMSEventoCreate(BaseModel):
    viaje_id: int
    parada_id: Optional[int] = None
    tipo_evento: TipoEventoTMSEnum
    descripcion: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    velocidad_kmh: Optional[float] = None
    datos_adicionales: Optional[str] = None


class TMSEventoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viaje_id: int
    parada_id: Optional[int] = None
    tipo_evento: TipoEventoTMSEnum
    descripcion: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    velocidad_kmh: Optional[float] = None
    timestamp: datetime
    datos_adicionales: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── TMSDocumento ─────────────────────────────────────────────────────────────

class TMSDocumentoCreate(BaseModel):
    viaje_id: int
    tipo_documento: TipoDocumentoTMSEnum
    numero: Optional[str] = None
    fecha_emision: Optional[date] = None
    archivo_url: Optional[str] = None
    observaciones: Optional[str] = None


class TMSDocumentoUpdate(BaseModel):
    tipo_documento: Optional[TipoDocumentoTMSEnum] = None
    numero: Optional[str] = None
    fecha_emision: Optional[date] = None
    archivo_url: Optional[str] = None
    estado: Optional[EstadoDocumentoTMSEnum] = None
    observaciones: Optional[str] = None


class TMSDocumentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viaje_id: int
    tipo_documento: TipoDocumentoTMSEnum
    numero: Optional[str] = None
    fecha_emision: Optional[date] = None
    archivo_url: Optional[str] = None
    estado: EstadoDocumentoTMSEnum
    observaciones: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── TMSPOD ───────────────────────────────────────────────────────────────────

class TMSPODCreate(BaseModel):
    viaje_id: int
    parada_id: Optional[int] = None
    receptor_nombre: Optional[str] = None
    receptor_documento: Optional[str] = None
    firma_url: Optional[str] = None
    foto_url: Optional[str] = None
    foto_url2: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    fecha_hora: Optional[datetime] = None
    observaciones: Optional[str] = None


class TMSPODResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viaje_id: int
    parada_id: Optional[int] = None
    receptor_nombre: Optional[str] = None
    receptor_documento: Optional[str] = None
    firma_url: Optional[str] = None
    foto_url: Optional[str] = None
    foto_url2: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    fecha_hora: Optional[datetime] = None
    observaciones: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── TMSRuta ──────────────────────────────────────────────────────────────────

class TMSRutaCreate(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    origen: str
    destino: str
    distancia_km: Optional[float] = None
    tiempo_estimado_min: Optional[int] = None
    tipo_servicio: Optional[TipoServicioTMSEnum] = None
    costo_referencia: Optional[float] = None


class TMSRutaUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    origen: Optional[str] = None
    destino: Optional[str] = None
    distancia_km: Optional[float] = None
    tiempo_estimado_min: Optional[int] = None
    tipo_servicio: Optional[TipoServicioTMSEnum] = None
    costo_referencia: Optional[float] = None
    activo: Optional[bool] = None


class TMSRutaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    codigo: Optional[str] = None
    origen: str
    destino: str
    distancia_km: Optional[float] = None
    tiempo_estimado_min: Optional[int] = None
    tipo_servicio: Optional[TipoServicioTMSEnum] = None
    costo_referencia: Optional[float] = None
    activo: bool
    created_at: Optional[datetime] = None


# ─── TMSPuntoRuta ─────────────────────────────────────────────────────────────

class TMSPuntoRutaCreate(BaseModel):
    # Lo pone la URL (/rutas/{ruta_id}/puntos); se acepta por compatibilidad.
    ruta_id: Optional[int] = None
    secuencia: int
    ciudad: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    tipo: Optional[TipoParadaTMSEnum] = None
    tiempo_estimado_minutos: Optional[int] = None


class TMSPuntoRutaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ruta_id: int
    secuencia: int
    ciudad: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    tipo: Optional[TipoParadaTMSEnum] = None
    tiempo_estimado_minutos: Optional[int] = None


# ─── TMSCostoViaje ────────────────────────────────────────────────────────────

class TMSCostoViajeCreate(BaseModel):
    viaje_id: int
    combustible: float = 0
    peajes: float = 0
    viaticos: float = 0
    horas_extras: float = 0
    mantenimiento: float = 0
    costos_indirectos: float = 0
    valor_flete_cobrado: float = 0
    notas: Optional[str] = None


class TMSCostoViajeUpdate(BaseModel):
    combustible: Optional[float] = None
    peajes: Optional[float] = None
    viaticos: Optional[float] = None
    horas_extras: Optional[float] = None
    mantenimiento: Optional[float] = None
    costos_indirectos: Optional[float] = None
    valor_flete_cobrado: Optional[float] = None
    notas: Optional[str] = None


class TMSCostoViajeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viaje_id: int
    combustible: float
    peajes: float
    viaticos: float
    horas_extras: float
    mantenimiento: float
    costos_indirectos: float
    valor_flete_cobrado: float
    costo_total: float
    costo_por_km: Optional[float] = None
    costo_por_entrega: Optional[float] = None
    margen: float
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── TMSLiquidacion ───────────────────────────────────────────────────────────

class TMSLiquidacionCreate(BaseModel):
    viaje_id: int
    conductor_hcm_id: Optional[int] = None
    conductor_legacy_id: Optional[int] = None
    periodo: Optional[str] = None
    valor_flete: float = 0
    bonificaciones: float = 0
    descuentos: float = 0
    anticipos: float = 0
    notas: Optional[str] = None


class TMSLiquidacionUpdate(BaseModel):
    conductor_hcm_id: Optional[int] = None
    conductor_legacy_id: Optional[int] = None
    periodo: Optional[str] = None
    valor_flete: Optional[float] = None
    bonificaciones: Optional[float] = None
    descuentos: Optional[float] = None
    anticipos: Optional[float] = None
    estado: Optional[EstadoLiquidacionTMSEnum] = None
    notas: Optional[str] = None


class TMSLiquidacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viaje_id: int
    conductor_hcm_id: Optional[int] = None
    conductor_nombre: Optional[str] = None
    conductor_legacy_id: Optional[int] = None
    periodo: Optional[str] = None
    valor_flete: float
    bonificaciones: float
    descuentos: float
    anticipos: float
    total_a_pagar: float
    estado: EstadoLiquidacionTMSEnum
    pagado_en: Optional[datetime] = None
    notas: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── TMSOTIFRegistro ──────────────────────────────────────────────────────────

class TMSOTIFRegistroCreate(BaseModel):
    viaje_id: int
    fecha: date
    on_time: bool
    in_full: bool
    cliente: Optional[str] = None
    ruta: Optional[str] = None
    observaciones: Optional[str] = None


class TMSOTIFRegistroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viaje_id: int
    fecha: date
    on_time: bool
    in_full: bool
    otif: bool
    cliente: Optional[str] = None
    ruta: Optional[str] = None
    observaciones: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── TMSAlerta ────────────────────────────────────────────────────────────────

class TMSAlertaCreate(BaseModel):
    tipo: TipoAlertaTMSEnum
    nivel: NivelAlertaTMSEnum
    mensaje: str
    viaje_id: Optional[int] = None
    vehiculo_id: Optional[int] = None
    conductor_id: Optional[int] = None


class TMSAlertaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: TipoAlertaTMSEnum
    nivel: NivelAlertaTMSEnum
    mensaje: str
    viaje_id: Optional[int] = None
    # El código del viaje, no solo su identificador. Una alerta que dice «viaje
    # 4127» no le sirve a nadie en una torre de control: hay que poder buscarla
    # por el código con el que el viaje se conoce.
    viaje_codigo: Optional[str] = None
    vehiculo_id: Optional[int] = None
    vehiculo_placa: Optional[str] = None
    conductor_id: Optional[int] = None
    leida: bool
    fecha_alerta: datetime


# ─── Responses de listas y agregados ──────────────────────────────────────────

class TMSViajeListResponse(BaseModel):
    items: List[TMSViajeResponse]
    total: int
    page: int
    per_page: int


class TMSDashboardKPIs(BaseModel):
    viajes_hoy: int
    viajes_en_transito: int
    viajes_completados_hoy: int
    viajes_programados: int
    vehiculos_activos: int
    vehiculos_disponibles: int
    conductores_activos: int
    otif_rate: float
    on_time_rate: float
    in_full_rate: float
    # Viajes entregados en el mes: con 0 los porcentajes no tienen datos.
    entregados_mes: int = 0
    costo_promedio_km: float
    km_recorridos_mes: float
    alertas_criticas: int
    alertas_activas: int


class TMSAlertasActivasResponse(BaseModel):
    alertas: List[TMSAlertaResponse]
