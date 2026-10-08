from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from pydantic import BaseModel
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.vehiculo import Vehiculo, Transportadora, Conductor, TipoVehiculo, EstadoVehiculo
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/vehiculos", tags=["Vehículos"])


class VehiculoCreate(BaseModel):
    placa: str
    tipo: TipoVehiculo
    marca: Optional[str] = None
    modelo: Optional[str] = None
    capacidad_estibas: Optional[int] = None
    capacidad_carga_kg: Optional[float] = None
    transportadora_id: Optional[int] = None


class VehiculoResponse(BaseModel):
    id: int
    placa: str
    tipo: TipoVehiculo
    marca: Optional[str] = None
    modelo: Optional[str] = None
    capacidad_estibas: Optional[int] = None
    estado: EstadoVehiculo
    transportadora_id: Optional[int] = None
    activo: bool

    model_config = {"from_attributes": True}


class TransportadoraCreate(BaseModel):
    nit: str
    razon_social: str
    nombre_comercial: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None


class TransportadoraResponse(TransportadoraCreate):
    id: int
    activo: bool
    model_config = {"from_attributes": True}


@router.get("/", response_model=List[VehiculoResponse])
async def listar_vehiculos(
    estado: Optional[EstadoVehiculo] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Vehiculo).where(Vehiculo.activo == True)
    if estado:
        query = query.where(Vehiculo.estado == estado)
    result = await db.execute(query.order_by(Vehiculo.placa))
    return list(result.scalars().all())


@router.post("/", response_model=VehiculoResponse, status_code=201)
async def crear_vehiculo(
    data: VehiculoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    vehiculo = Vehiculo(**data.model_dump())
    db.add(vehiculo)
    await db.flush()
    await db.refresh(vehiculo)
    return vehiculo


@router.get("/transportadoras", response_model=List[TransportadoraResponse])
async def listar_transportadoras(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Transportadora).where(Transportadora.activo == True).order_by(Transportadora.razon_social))
    return list(result.scalars().all())


@router.post("/transportadoras", response_model=TransportadoraResponse, status_code=201)
async def crear_transportadora(
    data: TransportadoraCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    t = Transportadora(**data.model_dump())
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return t
