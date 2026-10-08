from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.infrastructure.models.movimiento import TipoMovimiento


class MovimientoCreate(BaseModel):
    estiba_id: int
    tipo: TipoMovimiento
    ubicacion_origen_id: Optional[int] = None
    ubicacion_destino_id: Optional[int] = None
    vehiculo_id: Optional[int] = None
    manifiesto_id: Optional[int] = None
    conductor_id: Optional[int] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    observaciones: Optional[str] = None
    metadatos: Optional[dict] = None


class RegistrarCargaRequest(BaseModel):
    estiba_ids: List[int]
    manifiesto_id: int
    vehiculo_id: int
    ubicacion_origen_id: int
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    observaciones: Optional[str] = None


class RegistrarDescargaRequest(BaseModel):
    estiba_ids: List[int]
    manifiesto_id: Optional[int] = None
    vehiculo_id: Optional[int] = None
    ubicacion_destino_id: int
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    observaciones: Optional[str] = None


class MovimientoResponse(BaseModel):
    id: int
    estiba_id: int
    tipo: TipoMovimiento
    ubicacion_origen_id: Optional[int] = None
    ubicacion_destino_id: Optional[int] = None
    vehiculo_id: Optional[int] = None
    manifiesto_id: Optional[int] = None
    usuario_id: int
    fecha_movimiento: datetime
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    observaciones: Optional[str] = None
    estado_estiba_antes: Optional[str] = None
    estado_estiba_despues: Optional[str] = None

    model_config = {"from_attributes": True}


class TrazabilidadItem(BaseModel):
    id: int
    tipo: str
    descripcion: str
    ubicacion: Optional[str] = None
    vehiculo: Optional[str] = None
    manifiesto: Optional[str] = None
    usuario: str
    fecha: datetime
    fotos: List[str] = []

    model_config = {"from_attributes": True}


class MovimientoBulkCreate(BaseModel):
    items: List[MovimientoCreate]


class BulkMovimientoError(BaseModel):
    fila: int
    estiba_id: Optional[int] = None
    mensaje: str


class MovimientoBulkResponse(BaseModel):
    exitosos: int
    errores: List[BulkMovimientoError]
    total: int
