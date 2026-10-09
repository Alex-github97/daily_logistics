"""
Módulo WMS (Warehouse Management System) — Schemas Pydantic
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, ConfigDict, Field


# ─── Catálogos ─────────────────────────────────────────────────────────────────

class WMSTipoZonaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    activo: bool = True

class WMSTipoZonaUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class WMSTipoZonaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; descripcion: Optional[str] = None; activo: bool


class WMSTipoUbicacionCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    activo: bool = True

class WMSTipoUbicacionUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class WMSTipoUbicacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; descripcion: Optional[str] = None; activo: bool


class WMSUnidadMedidaCreate(BaseModel):
    nombre: str
    abreviatura: Optional[str] = None
    activo: bool = True

class WMSUnidadMedidaUpdate(BaseModel):
    nombre: Optional[str] = None
    abreviatura: Optional[str] = None
    activo: Optional[bool] = None

class WMSUnidadMedidaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; abreviatura: Optional[str] = None; activo: bool


class WMSMotivoMovimientoCreate(BaseModel):
    nombre: str
    tipo: str = "RESERVA"  # RESERVA / BLOQUEO
    activo: bool = True

class WMSMotivoMovimientoUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    activo: Optional[bool] = None

class WMSMotivoMovimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; tipo: str; activo: bool


class WMSCategoriaProductoCreate(BaseModel):
    nombre: str
    activo: bool = True

class WMSCategoriaProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None

class WMSCategoriaProductoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; activo: bool


class WMSFamiliaProductoCreate(BaseModel):
    nombre: str
    categoria_id: int
    activo: bool = True

class WMSFamiliaProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria_id: Optional[int] = None
    activo: Optional[bool] = None

class WMSFamiliaProductoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; categoria_id: int; activo: bool
    categoria_nombre: Optional[str] = None


class WMSPaisCreate(BaseModel):
    nombre: str
    codigo_iso: Optional[str] = None
    activo: bool = True

class WMSPaisUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo_iso: Optional[str] = None
    activo: Optional[bool] = None

class WMSPaisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; codigo_iso: Optional[str] = None; activo: bool
    created_at: Optional[datetime] = None


class WMSCiudadCreate(BaseModel):
    nombre: str
    pais_id: int
    activo: bool = True

class WMSCiudadUpdate(BaseModel):
    nombre: Optional[str] = None
    pais_id: Optional[int] = None
    activo: Optional[bool] = None

class WMSCiudadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; nombre: str; pais_id: int; activo: bool
    pais_nombre: Optional[str] = None
    created_at: Optional[datetime] = None


class WMSAlmacenCreate(BaseModel):
    codigo: str
    nombre: str
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    flujo_recepcion: str = Field(default="DIRECTO", pattern="^(DIRECTO|DIRIGIDO)$")
    activo: bool = True
    lat: Optional[float] = Field(None, ge=-90, le=90)        # punto fijado a mano en el mapa
    lng: Optional[float] = Field(None, ge=-180, le=180)

class WMSAlmacenUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    flujo_recepcion: Optional[str] = Field(default=None, pattern="^(DIRECTO|DIRIGIDO)$")
    activo: Optional[bool] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    reubicar: bool = False                                  # volver a ubicar desde la dirección

class WMSAlmacenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str
    direccion: Optional[str]; ciudad: Optional[str]; pais: Optional[str]; activo: bool
    flujo_recepcion: str = "DIRECTO"
    lat: Optional[float] = None
    lng: Optional[float] = None
    geo_precision: Optional[str] = None
    created_at: Optional[datetime] = None


class WMSZonaCreate(BaseModel):
    almacen_id: int
    codigo: str
    nombre: str
    tipo: str = "ALMACENAMIENTO"
    temperatura_controlada: bool = False
    vendible_pos: bool = False
    activo: bool = True

class WMSZonaUpdate(BaseModel):
    codigo: Optional[str] = None
    almacen_id: Optional[int] = None
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    temperatura_controlada: Optional[bool] = None
    vendible_pos: Optional[bool] = None
    activo: Optional[bool] = None

class WMSZonaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; almacen_id: int; codigo: str; nombre: str
    tipo: str; temperatura_controlada: bool; activo: bool
    vendible_pos: bool = False
    created_at: Optional[datetime] = None


class WMSUbicacionCreate(BaseModel):
    zona_id: int
    codigo: str
    pasillo: Optional[str] = None
    estanteria: Optional[str] = None
    nivel: Optional[str] = None
    posicion: Optional[str] = None
    tipo: str = "ESTANDAR"
    capacidad_kg: Optional[float] = None
    capacidad_m3: Optional[float] = None
    largo_cm: Optional[float] = Field(default=None, gt=0)
    ancho_cm: Optional[float] = Field(default=None, gt=0)
    alto_cm: Optional[float] = Field(default=None, gt=0)
    orden_recorrido: Optional[int] = Field(default=None, ge=1)
    activo: bool = True

class WMSUbicacionUpdate(BaseModel):
    codigo: Optional[str] = None
    zona_id: Optional[int] = None
    pasillo: Optional[str] = None
    estanteria: Optional[str] = None
    nivel: Optional[str] = None
    posicion: Optional[str] = None
    tipo: Optional[str] = None
    capacidad_kg: Optional[float] = None
    capacidad_m3: Optional[float] = None
    largo_cm: Optional[float] = Field(default=None, gt=0)
    ancho_cm: Optional[float] = Field(default=None, gt=0)
    alto_cm: Optional[float] = Field(default=None, gt=0)
    orden_recorrido: Optional[int] = Field(default=None, ge=1)
    activo: Optional[bool] = None

class WMSUbicacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; zona_id: int; codigo: str
    pasillo: Optional[str]; estanteria: Optional[str]; nivel: Optional[str]; posicion: Optional[str]
    tipo: str; capacidad_kg: Optional[float]; capacidad_m3: Optional[float]; activo: bool
    largo_cm: Optional[float] = None; ancho_cm: Optional[float] = None; alto_cm: Optional[float] = None
    orden_recorrido: Optional[int] = None
    created_at: Optional[datetime] = None


class WMSProductoCreate(BaseModel):
    sku: str
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    familia: Optional[str] = None
    unidad_medida: str = "UNIDAD"
    peso_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    requiere_refrigeracion: bool = False
    requiere_serial: bool = False
    requiere_lote: bool = False
    vida_util_dias: Optional[int] = None
    imagen_url: Optional[str] = None
    codigo_barras: Optional[str] = None
    tarifa_iva: float = 19
    depositante_id: Optional[int] = None  # vacío = la mercancía propia
    activo: bool = True

class WMSProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    familia: Optional[str] = None
    unidad_medida: Optional[str] = None
    peso_kg: Optional[float] = None
    volumen_m3: Optional[float] = None
    requiere_refrigeracion: Optional[bool] = None
    requiere_serial: Optional[bool] = None
    requiere_lote: Optional[bool] = None
    vida_util_dias: Optional[int] = None
    imagen_url: Optional[str] = None
    codigo_barras: Optional[str] = None
    tarifa_iva: Optional[float] = None
    depositante_id: Optional[int] = None
    activo: Optional[bool] = None

class WMSProductoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; sku: str; nombre: str; descripcion: Optional[str]
    categoria: Optional[str]; familia: Optional[str]; unidad_medida: str
    peso_kg: Optional[float]; volumen_m3: Optional[float]
    requiere_refrigeracion: bool; requiere_serial: bool; requiere_lote: bool
    vida_util_dias: Optional[int]; imagen_url: Optional[str]; activo: bool
    codigo_barras: Optional[str] = None
    tarifa_iva: float = 19
    costo_promedio: float = 0
    depositante_id: Optional[int] = None
    created_at: Optional[datetime] = None


class WMSLoteCreate(BaseModel):
    producto_id: int
    numero_lote: str
    fecha_fabricacion: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    proveedor_lote: Optional[str] = None
    activo: bool = True

class WMSLoteUpdate(BaseModel):
    numero_lote: Optional[str] = None
    fecha_fabricacion: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    proveedor_lote: Optional[str] = None
    activo: Optional[bool] = None

class WMSLoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; producto_id: int; numero_lote: str
    fecha_fabricacion: Optional[date]; fecha_vencimiento: Optional[date]
    proveedor_lote: Optional[str]; activo: bool
    created_at: Optional[datetime] = None


class WMSSerieCreate(BaseModel):
    producto_id: int
    lote_id: Optional[int] = None
    numero_serie: str
    estado: str = "DISPONIBLE"
    activo: bool = True

class WMSSerieUpdate(BaseModel):
    lote_id: Optional[int] = None
    estado: Optional[str] = None
    activo: Optional[bool] = None

class WMSSerieResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; producto_id: int; lote_id: Optional[int]
    numero_serie: str; estado: str; activo: bool
    created_at: Optional[datetime] = None


class WMSProveedorCreate(BaseModel):
    codigo: str
    nombre: str
    nit: Optional[str] = None
    contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    activo: bool = True

class WMSProveedorUpdate(BaseModel):
    nombre: Optional[str] = None
    nit: Optional[str] = None
    contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    activo: Optional[bool] = None

class WMSProveedorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str; nit: Optional[str]
    contacto: Optional[str]; email: Optional[str]; telefono: Optional[str]
    ciudad: Optional[str]; pais: Optional[str]; activo: bool
    created_at: Optional[datetime] = None


class WMSClienteCreate(BaseModel):
    codigo: str
    nombre: str
    nit: Optional[str] = None
    contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    segmento: Optional[str] = None
    activo: bool = True

class WMSClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    nit: Optional[str] = None
    contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    segmento: Optional[str] = None
    activo: Optional[bool] = None

class WMSClienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str; nit: Optional[str]
    contacto: Optional[str]; email: Optional[str]; telefono: Optional[str]
    ciudad: Optional[str]; pais: Optional[str]; segmento: Optional[str]; activo: bool
    created_at: Optional[datetime] = None


class WMSTransportadoraCreate(BaseModel):
    codigo: str
    nombre: str
    nit: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    activo: bool = True

class WMSTransportadoraUpdate(BaseModel):
    nombre: Optional[str] = None
    nit: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    activo: Optional[bool] = None

class WMSTransportadoraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str; nit: Optional[str]
    contacto: Optional[str]; telefono: Optional[str]; activo: bool
    created_at: Optional[datetime] = None


# ─── Brief (nested) ────────────────────────────────────────────────────────────

class WMSProductoBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; sku: str; nombre: str; unidad_medida: str

class WMSLoteBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero_lote: str; fecha_vencimiento: Optional[date]

class WMSUbicacionBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str
    pasillo: Optional[str] = None; estanteria: Optional[str] = None
    nivel: Optional[str] = None; posicion: Optional[str] = None

class WMSAlmacenBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str

class WMSClienteBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str

class WMSProveedorBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str


# ─── Inbound ───────────────────────────────────────────────────────────────────

class WMSOrdenCompraDetalleCreate(BaseModel):
    producto_id: int
    cantidad_solicitada: float = Field(gt=0)
    precio_unitario: Optional[float] = None
    unidad_medida: Optional[str] = None

class WMSOrdenCompraDetalleUpdate(BaseModel):
    cantidad_solicitada: Optional[float] = None
    cantidad_recibida: Optional[float] = None
    precio_unitario: Optional[float] = None

class WMSOrdenCompraDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; orden_id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    cantidad_solicitada: float; cantidad_recibida: float
    precio_unitario: Optional[float]; unidad_medida: Optional[str]

class WMSOrdenCompraCreate(BaseModel):
    numero_oc: Optional[str] = None  # autogenerado si viene vacío
    proveedor_id: int
    almacen_id: int
    fecha_emision: Optional[date] = None  # por defecto hoy
    fecha_esperada: Optional[date] = None
    estado: str = "PENDIENTE"
    notas: Optional[str] = None
    depositante_id: Optional[int] = None  # vacío = el de sus productos
    detalles: List[WMSOrdenCompraDetalleCreate] = []

class WMSOrdenCompraUpdate(BaseModel):
    fecha_esperada: Optional[date] = None
    estado: Optional[str] = None
    notas: Optional[str] = None

class WMSOrdenCompraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero_oc: str; proveedor_id: int
    proveedor: Optional[WMSProveedorBrief] = None
    almacen_id: int
    almacen: Optional[WMSAlmacenBrief] = None
    fecha_emision: date; fecha_esperada: Optional[date]
    estado: str; notas: Optional[str]
    depositante_id: Optional[int] = None
    detalles: List[WMSOrdenCompraDetalleResponse] = []
    created_at: Optional[datetime] = None
    # Se puede corregir o eliminar: estado inicial, sin recepciones ni cambios de estado.
    editable: bool = False


class WMSRecepcionDetalleCreate(BaseModel):
    producto_id: int
    lote_id: Optional[int] = None
    cantidad_esperada: Optional[float] = None
    cantidad_recibida: float = 0
    ubicacion_id: Optional[int] = None
    contenedor_id: Optional[int] = None
    estado_calidad: str = "APROBADO"
    notas: Optional[str] = None
    novedad: Optional[str] = Field(default=None, max_length=30)

class WMSRecepcionDetalleUpdate(BaseModel):
    lote_id: Optional[int] = None
    cantidad_recibida: Optional[float] = None
    ubicacion_id: Optional[int] = None
    estado_calidad: Optional[str] = None
    notas: Optional[str] = None

class WMSRecepcionDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; recepcion_id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    lote_id: Optional[int]
    lote: Optional[WMSLoteBrief] = None
    cantidad_esperada: Optional[float]; cantidad_recibida: float
    ubicacion_id: Optional[int]
    ubicacion: Optional[WMSUbicacionBrief] = None
    contenedor_id: Optional[int] = None
    estado_calidad: str; notas: Optional[str]
    novedad: Optional[str] = None

class WMSRecepcionCreate(BaseModel):
    numero_recepcion: Optional[str] = None  # autogenerado si viene vacío
    tipo: str = "CONTRA_OC"
    orden_compra_id: Optional[int] = None
    almacen_id: int
    fecha_recepcion: Optional[date] = None  # por defecto hoy
    estado: str = "BORRADOR"
    notas: Optional[str] = None
    depositante_id: Optional[int] = None
    muelle: Optional[str] = None
    fecha_llegada: Optional[datetime] = None
    inicio_descargue: Optional[datetime] = None
    fin_descargue: Optional[datetime] = None
    detalles: List[WMSRecepcionDetalleCreate] = []

class WMSRecepcionUpdate(BaseModel):
    tipo: Optional[str] = None
    orden_compra_id: Optional[int] = None
    fecha_recepcion: Optional[date] = None
    estado: Optional[str] = None
    notas: Optional[str] = None
    muelle: Optional[str] = None
    fecha_llegada: Optional[datetime] = None
    inicio_descargue: Optional[datetime] = None
    fin_descargue: Optional[datetime] = None

class WMSRecepcionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero_recepcion: str; tipo: str
    orden_compra_id: Optional[int]
    almacen_id: int
    almacen: Optional[WMSAlmacenBrief] = None
    fecha_recepcion: date; estado: str
    operario_id: Optional[int]; notas: Optional[str]
    depositante_id: Optional[int] = None
    muelle: Optional[str] = None
    fecha_llegada: Optional[datetime] = None
    inicio_descargue: Optional[datetime] = None
    fin_descargue: Optional[datetime] = None
    completada_en: Optional[datetime] = None
    detalles: List[WMSRecepcionDetalleResponse] = []
    created_at: Optional[datetime] = None


# ─── Inventario ────────────────────────────────────────────────────────────────

class WMSInventarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    ubicacion_id: int
    ubicacion: Optional[WMSUbicacionBrief] = None
    lote_id: Optional[int]
    lote: Optional[WMSLoteBrief] = None
    contenedor_id: Optional[int] = None
    contenedor_codigo: Optional[str] = None
    cantidad_disponible: float; cantidad_reservada: float; cantidad_bloqueada: float
    updated_at: Optional[datetime] = None

class WMSAjusteInventario(BaseModel):
    producto_id: int
    ubicacion_id: int
    lote_id: Optional[int] = None
    contenedor_id: Optional[int] = None
    cantidad_nueva: float = Field(ge=0)  # valor absoluto del disponible resultante
    # Qué estado se ajusta: el disponible, o lo retenido en cuarentena (para dar de baja lo dañado).
    estado: Literal["DISPONIBLE", "BLOQUEADO"] = "DISPONIBLE"
    # Un ajuste sin explicación no se puede auditar.
    motivo: str = Field(min_length=3, max_length=300)

class WMSTransferenciaInventario(BaseModel):
    producto_id: int
    ubicacion_origen_id: int
    ubicacion_destino_id: int
    lote_id: Optional[int] = None
    contenedor_id: Optional[int] = None
    cantidad: float = Field(gt=0)
    notas: Optional[str] = None
    # Gestión del transporte del traslado: NINGUNA (no se gestiona en plataforma)
    # o TMS (crea un viaje en el módulo TMS para su gestión).
    gestion_transporte: str = "NINGUNA"
    transportadora: Optional[str] = None
    descripcion_carga: Optional[str] = None

class WMSReservaBloqueo(BaseModel):
    producto_id: int
    ubicacion_id: int
    lote_id: Optional[int] = None
    contenedor_id: Optional[int] = None
    cantidad: float = Field(gt=0)
    accion: str  # RESERVAR / LIBERAR / BLOQUEAR / DESBLOQUEAR
    motivo: Optional[str] = None

class WMSMovimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; tipo: str; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    ubicacion_origen_id: Optional[int]; ubicacion_destino_id: Optional[int]
    lote_id: Optional[int]; serie_id: Optional[int]
    cantidad: float; referencia_documento: Optional[str]
    usuario_id: Optional[int]; notas: Optional[str]
    contenedor_id: Optional[int] = None
    contenedor_destino_id: Optional[int] = None
    depositante_id: Optional[int] = None
    almacen_id: Optional[int] = None
    documento_tipo: Optional[str] = None
    documento_id: Optional[int] = None
    tarea_id: Optional[int] = None
    estado_origen: Optional[str] = None
    estado_destino: Optional[str] = None
    saldo_origen: Optional[float] = None
    saldo_destino: Optional[float] = None
    created_at: Optional[datetime] = None


class WMSConteoDetalleCreate(BaseModel):
    producto_id: int
    ubicacion_id: int
    lote_id: Optional[int] = None
    cantidad_sistema: float = 0

class WMSConteoDetalleUpdate(BaseModel):
    cantidad_fisica: Optional[float] = None
    ajustado: Optional[bool] = None

class WMSConteoDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; conteo_id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    ubicacion_id: int
    ubicacion: Optional[WMSUbicacionBrief] = None
    contenedor_id: Optional[int] = None
    lote_id: Optional[int]; cantidad_sistema: float
    cantidad_fisica: Optional[float]; diferencia: Optional[float]; ajustado: bool

class WMSConteoCreate(BaseModel):
    almacen_id: int
    tipo: str = "CICLICO"
    fecha_programada: date
    notas: Optional[str] = None
    detalles: List[WMSConteoDetalleCreate] = []

class WMSConteoUpdate(BaseModel):
    estado: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    notas: Optional[str] = None

class WMSConteoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; almacen_id: int
    almacen: Optional[WMSAlmacenBrief] = None
    tipo: str; estado: str; fecha_programada: date
    fecha_inicio: Optional[datetime]; fecha_fin: Optional[datetime]
    operario_id: Optional[int]; notas: Optional[str]
    detalles: List[WMSConteoDetalleResponse] = []
    created_at: Optional[datetime] = None


# ─── Outbound ──────────────────────────────────────────────────────────────────

class WMSOrdenSalidaDetalleCreate(BaseModel):
    producto_id: int
    lote_id: Optional[int] = None
    cantidad_solicitada: float = Field(gt=0)
    precio_unitario: Optional[float] = None

class WMSOrdenSalidaDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; orden_id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    lote_id: Optional[int]; cantidad_solicitada: float
    cantidad_preparada: float; cantidad_despachada: float
    precio_unitario: Optional[float]; estado: str

class WMSOrdenSalidaCreate(BaseModel):
    numero_orden: Optional[str] = None  # autogenerado si viene vacío
    cliente_id: int
    almacen_id: int
    fecha_emision: Optional[date] = None  # por defecto hoy
    fecha_requerida: Optional[date] = None
    estado: str = "PENDIENTE"
    prioridad: str = "NORMAL"
    canal: Optional[str] = None
    depositante_id: Optional[int] = None
    detalles: List[WMSOrdenSalidaDetalleCreate] = []

class WMSOrdenSalidaUpdate(BaseModel):
    fecha_requerida: Optional[date] = None
    estado: Optional[str] = None
    prioridad: Optional[str] = None
    canal: Optional[str] = None

class WMSOrdenSalidaEstado(BaseModel):
    estado: str

class WMSOrdenSalidaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero_orden: str; cliente_id: int
    cliente: Optional[WMSClienteBrief] = None
    almacen_id: int
    almacen: Optional[WMSAlmacenBrief] = None
    fecha_emision: date; fecha_requerida: Optional[date]
    estado: str; prioridad: str; canal: Optional[str]
    depositante_id: Optional[int] = None
    detalles: List[WMSOrdenSalidaDetalleResponse] = []
    created_at: Optional[datetime] = None


class WMSPickingDetalleCreate(BaseModel):
    producto_id: int
    ubicacion_id: int
    lote_id: Optional[int] = None
    cantidad_solicitada: float

class WMSPickingDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; tarea_id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    ubicacion_id: int
    ubicacion: Optional[WMSUbicacionBrief] = None
    lote_id: Optional[int]; cantidad_solicitada: float
    cantidad_pickeada: float; confirmado: bool
    contenedor_id: Optional[int] = None
    cantidad_despachada: float = 0
    timestamp_confirmacion: Optional[datetime]

class WMSPickingTareaCreate(BaseModel):
    orden_id: int
    tipo: str = "SINGLE"
    detalles: List[WMSPickingDetalleCreate] = []

class WMSPickingTareaUpdate(BaseModel):
    estado: Optional[str] = None
    operario_id: Optional[int] = None

class WMSPickingConfirmItem(BaseModel):
    detalle_id: int
    cantidad_pickeada: float = Field(gt=0)
    # Lo que el operario escaneó. Si viene, tiene que coincidir: es la
    # verificación que evita sacar de la ubicación equivocada.
    ubicacion_codigo: Optional[str] = None
    producto_codigo: Optional[str] = None

class WMSPickingTareaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; orden_id: int; operario_id: Optional[int]
    tipo: str; estado: str
    fecha_asignacion: Optional[datetime]; fecha_inicio: Optional[datetime]; fecha_fin: Optional[datetime]
    ubicaciones_visitadas: int; items_pickeados: int
    detalles: List[WMSPickingDetalleResponse] = []
    created_at: Optional[datetime] = None


class WMSDespachoDetalleCreate(BaseModel):
    producto_id: int
    lote_id: Optional[int] = None
    cantidad: float = Field(gt=0)
    numero_tracking: Optional[str] = None

class WMSDespachoDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; despacho_id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    lote_id: Optional[int]; cantidad: float; numero_tracking: Optional[str]
    contenedor_id: Optional[int] = None

class WMSDespachoCreate(BaseModel):
    numero_despacho: Optional[str] = None  # autogenerado si viene vacío
    orden_id: int
    transportadora_id: Optional[int] = None
    vehiculo_placa: Optional[str] = None
    conductor_nombre: Optional[str] = None
    fecha_despacho: Optional[date] = None  # por defecto hoy
    fecha_entrega_estimada: Optional[date] = None
    estado: str = "PREPARANDO"
    peso_total_kg: Optional[float] = None
    volumen_total_m3: Optional[float] = None
    notas: Optional[str] = None
    muelle: Optional[str] = None
    inicio_cargue: Optional[datetime] = None
    fin_cargue: Optional[datetime] = None
    detalles: List[WMSDespachoDetalleCreate] = []
    # NINGUNA (no gestiona transporte en plataforma) o TMS (crea viaje en TMS)
    gestion_transporte: str = "NINGUNA"
    # Vehículo del TMS (opcional): se verifica su capacidad y queda en el viaje.
    tms_vehiculo_id: Optional[int] = None

class WMSDespachoUpdate(BaseModel):
    transportadora_id: Optional[int] = None
    vehiculo_placa: Optional[str] = None
    conductor_nombre: Optional[str] = None
    fecha_entrega_estimada: Optional[date] = None
    fecha_entrega_real: Optional[date] = None
    estado: Optional[str] = None
    peso_total_kg: Optional[float] = None
    volumen_total_m3: Optional[float] = None
    notas: Optional[str] = None

class WMSDespachoEstado(BaseModel):
    estado: str
    fecha_entrega_real: Optional[date] = None

class WMSDespachoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero_despacho: str; orden_id: int
    transportadora_id: Optional[int]; vehiculo_placa: Optional[str]
    conductor_nombre: Optional[str]; fecha_despacho: date
    fecha_entrega_estimada: Optional[date]; fecha_entrega_real: Optional[date]
    estado: str; peso_total_kg: Optional[float]; volumen_total_m3: Optional[float]
    notas: Optional[str]
    muelle: Optional[str] = None
    inicio_cargue: Optional[datetime] = None
    fin_cargue: Optional[datetime] = None
    factura_id: Optional[int] = None
    factura_numero: Optional[str] = None
    aviso_factura: Optional[str] = None
    detalles: List[WMSDespachoDetalleResponse] = []
    created_at: Optional[datetime] = None


# ─── Devoluciones ──────────────────────────────────────────────────────────────

class WMSDevolucionDetalleCreate(BaseModel):
    producto_id: int
    lote_id: Optional[int] = None
    cantidad: float
    estado_calidad: str = "BUENO"
    accion: str = "REINGRESAR"

class WMSDevolucionDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; devolucion_id: int; producto_id: int
    producto: Optional[WMSProductoBrief] = None
    lote_id: Optional[int]; cantidad: float
    estado_calidad: str; accion: str; reingresado: bool

class WMSDevolucionCreate(BaseModel):
    numero_devolucion: str
    tipo: str
    orden_referencia_id: Optional[int] = None
    cliente_id: Optional[int] = None
    proveedor_id: Optional[int] = None
    almacen_id: int
    fecha_recepcion: date
    estado: str = "RECIBIDA"
    motivo: Optional[str] = None
    notas: Optional[str] = None
    detalles: List[WMSDevolucionDetalleCreate] = []

class WMSDevolucionUpdate(BaseModel):
    estado: Optional[str] = None
    motivo: Optional[str] = None
    notas: Optional[str] = None

class WMSDevolucionProcesar(BaseModel):
    estado: str  # APROBADA / RECHAZADA / REINGRESADA

class WMSDevolucionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero_devolucion: str; tipo: str
    orden_referencia_id: Optional[int]; cliente_id: Optional[int]; proveedor_id: Optional[int]
    almacen_id: int; fecha_recepcion: date; estado: str
    motivo: Optional[str]; notas: Optional[str]
    nota_credito_id: Optional[int] = None
    detalles: List[WMSDevolucionDetalleResponse] = []
    created_at: Optional[datetime] = None


# ─── Trazabilidad ──────────────────────────────────────────────────────────────

class WMSEventoTrazabilidadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; tipo_evento: str; entidad_tipo: Optional[str]; entidad_id: Optional[int]
    descripcion: Optional[str]; datos_adicionales: Optional[Dict[str, Any]]
    usuario_id: Optional[int]; ubicacion_id: Optional[int]
    producto_id: Optional[int]; lote_id: Optional[int]
    created_at: Optional[datetime] = None


# ─── KPIs & Dashboard ──────────────────────────────────────────────────────────

class WMSKPIs(BaseModel):
    # On-Time
    ordenes_entregadas_total: int = 0
    ordenes_on_time: int = 0
    on_time_pct: float = 0.0
    # In-Full
    ordenes_in_full: int = 0
    in_full_pct: float = 0.0
    # OTIF
    ordenes_otif: int = 0
    otif_pct: float = 0.0
    # Cuántas órdenes entran en el cálculo: con 0 el indicador no tiene datos
    # (no es que la bodega esté en 0 %).
    otif_base: int = 0
    perfect_base: int = 0
    # Perfect Order
    ordenes_perfect: int = 0
    perfect_order_pct: float = 0.0
    # Fill Rate
    unidades_solicitadas: float = 0.0
    unidades_despachadas: float = 0.0
    fill_rate_pct: float = 0.0
    # Inventory Accuracy
    ubicaciones_contadas: int = 0
    ubicaciones_correctas: int = 0
    inventory_accuracy_pct: float = 0.0
    # Pendientes
    recepciones_pendientes: int = 0
    ordenes_salida_pendientes: int = 0
    # Por estado (outbound)
    ordenes_por_estado: Dict[str, int] = {}

    # Los nombres que pide el tablero.
    #
    # La pantalla lee `ot_pct`, `if_pct`, `fill_rate`… y acá se devolvía
    # `on_time_pct`, `in_full_pct`, `fill_rate_pct`. De los seis indicadores solo
    # coincidía `otif_pct`, así que el tablero mostraba un número y cinco ceros
    # —y el cero se lee como «la bodega va mal», no como «falta un campo».
    #
    # Se agregan en vez de renombrar porque los nombres largos ya están
    # publicados: cambiarlos rompería a cualquiera que consuma el endpoint.
    ot_pct: float = 0.0
    if_pct: float = 0.0
    perfect_order_rate: float = 0.0
    fill_rate: float = 0.0
    inventory_accuracy: float = 0.0
    pending_recepciones: int = 0
    pending_ordenes_salida: int = 0
    urgent_recepciones: int = 0
    active_picking_tasks: int = 0
    recent_ordenes_compra: List[Dict[str, Any]] = []
    recent_ordenes_salida: List[Dict[str, Any]] = []

class WMSAlertasResponse(BaseModel):
    recepciones_pendientes: int = 0
    ordenes_urgentes: int = 0
    ordenes_vencidas: int = 0
    productos_proximos_vencer: int = 0
    alertas: List[Dict[str, Any]] = []

class WMSKPIDiarioCreate(BaseModel):
    fecha: date
    almacen_id: Optional[int] = None
    ordenes_total: int = 0
    ordenes_on_time: int = 0
    ordenes_in_full: int = 0
    ordenes_otif: int = 0
    ordenes_perfect: int = 0
    fill_rate: Optional[float] = None
    inventory_accuracy: Optional[float] = None
    cost_per_order: Optional[float] = None
    dock_to_stock_minutes: Optional[float] = None
    picking_accuracy: Optional[float] = None
    shipping_accuracy: Optional[float] = None

class WMSKPIDiarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; fecha: date; almacen_id: Optional[int]
    ordenes_total: int; ordenes_on_time: int; ordenes_in_full: int
    ordenes_otif: int; ordenes_perfect: int
    fill_rate: Optional[float]; inventory_accuracy: Optional[float]
    cost_per_order: Optional[float]; dock_to_stock_minutes: Optional[float]
    picking_accuracy: Optional[float]; shipping_accuracy: Optional[float]
    created_at: Optional[datetime] = None


class WMSFacturarDespacho(BaseModel):
    # Precio sin IVA por producto, para lo que la orden no traía con precio.
    precios: Dict[int, float] = {}
