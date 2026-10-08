from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from app.infrastructure.models.estiba import (
    EstadoEstiba, TipoPropietario, TipoEstiba, MaterialEstiba, NivelDano
)


class EstibaBase(BaseModel):
    codigo_interno: str = Field(..., min_length=3, max_length=80)
    tipo: TipoEstiba = TipoEstiba.MADERA
    material: MaterialEstiba = MaterialEstiba.MADERA_PINO
    largo_cm: float = 120.0
    ancho_cm: float = 100.0
    alto_cm: float = 15.0
    peso_kg: float = 25.0
    capacidad_carga_kg: float = 1000.0
    tipo_propietario: TipoPropietario = TipoPropietario.PROPIA
    proveedor_id: Optional[int] = None
    contrato_id: Optional[int] = None
    fecha_ingreso: date
    fecha_fabricacion: Optional[date] = None
    vida_util_anos: int = 5
    valor_compra: Optional[float] = None
    valor_actual: Optional[float] = None
    moneda: str = "COP"
    observaciones: Optional[str] = None


class EstibaCreate(EstibaBase):
    ubicacion_inicial_id: Optional[int] = None


class EstibaUpdate(BaseModel):
    tipo: Optional[TipoEstiba] = None
    material: Optional[MaterialEstiba] = None
    largo_cm: Optional[float] = None
    ancho_cm: Optional[float] = None
    alto_cm: Optional[float] = None
    peso_kg: Optional[float] = None
    capacidad_carga_kg: Optional[float] = None
    tipo_propietario: Optional[TipoPropietario] = None
    proveedor_id: Optional[int] = None
    contrato_id: Optional[int] = None
    estado: Optional[EstadoEstiba] = None
    ubicacion_actual_id: Optional[int] = None
    valor_actual: Optional[float] = None
    observaciones: Optional[str] = None
    nivel_dano: Optional[NivelDano] = None


class UbicacionBasica(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo: str
    model_config = {"from_attributes": True}


class ProveedorBasico(BaseModel):
    id: int
    nit: str
    razon_social: str
    model_config = {"from_attributes": True}


class EstibaResponse(EstibaBase):
    id: int
    codigo_qr: Optional[str] = None
    codigo_rfid: Optional[str] = None
    codigo_sap: Optional[str] = None
    estado: EstadoEstiba
    nivel_dano: Optional[NivelDano] = None
    total_usos: int
    total_km_recorridos: float
    ubicacion_actual: Optional[UbicacionBasica] = None
    proveedor: Optional[ProveedorBasico] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EstibaListResponse(BaseModel):
    items: List[EstibaResponse]
    total: int
    page: int
    page_size: int
    pages: int


class EstibaKPIs(BaseModel):
    total: int
    DISPONIBLE: int = 0
    EN_TRANSITO: int = 0
    CARGADA: int = 0
    EN_CLIENTE: int = 0
    PENDIENTE_RETORNO: int = 0
    EN_REPARACION: int = 0
    DANADA: int = 0
    PERDIDA: int = 0
    BAJA: int = 0
    DISPOSICION_FINAL: int = 0
    EN_INVENTARIO: int = 0


class EstibaBulkError(BaseModel):
    fila: int
    codigo: str
    mensaje: str


class EstibaBulkCreate(BaseModel):
    items: List[EstibaCreate]


class EstibaBulkResponse(BaseModel):
    exitosos: int
    errores: List[EstibaBulkError]
    total: int
