from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Generador de Carga ────────────────────────────────────────────────────────

class GeneradorCargaBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=300)
    nit: Optional[str] = Field(None, max_length=30)
    contacto: Optional[str] = Field(None, max_length=150)
    telefono: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=200)
    ciudad: Optional[str] = Field(None, max_length=100)


class GeneradorCargaCreate(GeneradorCargaBase):
    pass


class GeneradorCargaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=300)
    nit: Optional[str] = Field(None, max_length=30)
    contacto: Optional[str] = Field(None, max_length=150)
    telefono: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=200)
    ciudad: Optional[str] = Field(None, max_length=100)


class GeneradorCargaResponse(GeneradorCargaBase):
    id: int
    activo: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Vehículo Flete (del conductor) ────────────────────────────────────────────

class VehiculoFleteBase(BaseModel):
    placa: str = Field(..., min_length=4, max_length=15)
    tipo_vehiculo: str = Field(..., max_length=30)
    tipo_carroceria: Optional[str] = Field(None, max_length=30)
    marca: Optional[str] = Field(None, max_length=80)
    modelo: Optional[str] = Field(None, max_length=50)
    anio: Optional[int] = Field(None, ge=1950, le=2030)
    capacidad_kg: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None


class VehiculoFleteCreate(VehiculoFleteBase):
    conductor_id: int


class VehiculoFleteUpdate(BaseModel):
    placa: Optional[str] = Field(None, min_length=4, max_length=15)
    tipo_vehiculo: Optional[str] = Field(None, max_length=30)
    tipo_carroceria: Optional[str] = Field(None, max_length=30)
    marca: Optional[str] = Field(None, max_length=80)
    modelo: Optional[str] = Field(None, max_length=50)
    anio: Optional[int] = Field(None, ge=1950, le=2030)
    capacidad_kg: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None


class VehiculoFleteResponse(VehiculoFleteBase):
    id: int
    conductor_id: int
    conductor_nombre: Optional[str] = None
    activo: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Conductor (vista simplificada para dropdowns) ─────────────────────────────

class ConductorBrief(BaseModel):
    id: int
    nombre: str
    apellido: str
    cedula: Optional[str] = None
    telefono: Optional[str] = None
    usuario_id: Optional[int] = None
    model_config = {"from_attributes": True}


class ConductorConVehiculos(ConductorBrief):
    vehiculos_flete: List[VehiculoFleteResponse] = []
    model_config = {"from_attributes": True}


# ── Flete ─────────────────────────────────────────────────────────────────────

class FleteBase(BaseModel):
    ciudad_origen: str = Field(..., min_length=2, max_length=150)
    ciudad_destino: str = Field(..., min_length=2, max_length=150)
    tipo_vehiculo: str = Field(..., max_length=30)
    tipo_carroceria: Optional[str] = Field(None, max_length=30)
    generador_id: Optional[int] = None
    descripcion_carga: Optional[str] = Field(None, max_length=500)
    peso_kg: Optional[float] = Field(None, ge=0)
    num_entregas: Optional[int] = Field(1, ge=1)
    distancia_km: Optional[float] = Field(None, ge=0)
    fecha_hora_cargue: datetime
    fecha_hora_entrega: Optional[datetime] = None
    valor_flete: Optional[float] = Field(None, ge=0)
    es_negociable: bool = False
    notas: Optional[str] = None


class FleteCreate(FleteBase):
    pass


class FleteUpdate(BaseModel):
    ciudad_origen: Optional[str] = Field(None, min_length=2, max_length=150)
    ciudad_destino: Optional[str] = Field(None, min_length=2, max_length=150)
    tipo_vehiculo: Optional[str] = Field(None, max_length=30)
    tipo_carroceria: Optional[str] = Field(None, max_length=30)
    generador_id: Optional[int] = None
    descripcion_carga: Optional[str] = Field(None, max_length=500)
    peso_kg: Optional[float] = Field(None, ge=0)
    num_entregas: Optional[int] = Field(None, ge=1)
    distancia_km: Optional[float] = Field(None, ge=0)
    fecha_hora_cargue: Optional[datetime] = None
    fecha_hora_entrega: Optional[datetime] = None
    valor_flete: Optional[float] = Field(None, ge=0)
    es_negociable: Optional[bool] = None
    estado: Optional[str] = None
    notas: Optional[str] = None


class FleteAsignar(BaseModel):
    conductor_id: int
    vehiculo_flete_id: int


class FleteResponse(FleteBase):
    id: int
    estado: str
    conductor_id: Optional[int] = None
    vehiculo_flete_id: Optional[int] = None
    creado_por_id: Optional[int] = None
    activo: bool
    created_at: datetime
    generador_nombre: Optional[str] = None
    conductor_nombre: Optional[str] = None
    vehiculo_placa: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Enturnamiento ─────────────────────────────────────────────────────────────

class EnturnamientoBase(BaseModel):
    conductor_id: int
    ciudad_disponible: str = Field(..., min_length=2, max_length=150)
    fecha_hora_disponible: datetime
    tipo_vehiculo: Optional[str] = Field(None, max_length=30)
    tipo_carroceria: Optional[str] = Field(None, max_length=30)
    notas: Optional[str] = None


class EnturnamientoCreate(EnturnamientoBase):
    pass


class EnturnamientoAsignar(BaseModel):
    flete_id: int


class EnturnamientoResponse(EnturnamientoBase):
    id: int
    estado: str
    flete_asignado_id: Optional[int] = None
    activo: bool
    created_at: datetime
    conductor_nombre: Optional[str] = None
    conductor_cedula: Optional[str] = None
    model_config = {"from_attributes": True}
