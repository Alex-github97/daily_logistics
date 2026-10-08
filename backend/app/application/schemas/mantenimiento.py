from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from app.infrastructure.models.mantenimiento import TipoMantenimiento


class MantenimientoCreate(BaseModel):
    estiba_id: int
    fecha: date
    tipo: TipoMantenimiento
    descripcion: Optional[str] = None
    costo: float = Field(..., ge=0, description="Costo en COP")
    proveedor_id: int = Field(..., description="ID del proveedor registrado en el sistema")


class MantenimientoResponse(BaseModel):
    id: int
    estiba_id: int
    estiba_codigo: Optional[str] = None
    fecha: date
    tipo: TipoMantenimiento
    descripcion: Optional[str] = None
    costo: float
    proveedor_id: int
    proveedor_nombre: Optional[str] = None
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MantenimientoListResponse(BaseModel):
    items: List[MantenimientoResponse]
    total: int
    total_costo: float


class CostoEstibaItem(BaseModel):
    estiba_id: int
    codigo_interno: Optional[str] = None
    tipo: str
    estado: str
    fecha_ingreso: Optional[date] = None
    tipo_propietario: str
    valor_compra: Optional[float] = None
    total_costo_mantenimiento: float
    cantidad_mantenimientos: int


class CostosReporteResponse(BaseModel):
    items: List[CostoEstibaItem]
    total: int
    total_costos_acumulados: float
    page: int
    page_size: int
    pages: int
