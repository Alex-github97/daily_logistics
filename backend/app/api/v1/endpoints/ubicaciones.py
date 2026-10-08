from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.ubicacion import Ubicacion, TipoUbicacion
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.repositories.base_repository import BaseRepository

router = APIRouter(prefix="/ubicaciones", tags=["Ubicaciones"])


class UbicacionCreate(BaseModel):
    codigo: str
    nombre: str
    tipo: TipoUbicacion
    descripcion: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    pais: str = "Colombia"
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    capacidad_estibas: Optional[int] = None
    codigo_sap: Optional[str] = None
    es_disposicion_final: bool = False


class UbicacionResponse(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo: TipoUbicacion
    descripcion: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    pais: str = "Colombia"
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    capacidad_estibas: Optional[int] = None
    es_disposicion_final: bool = False
    activo: bool

    model_config = {"from_attributes": True}


@router.get("/", response_model=List[UbicacionResponse])
async def listar_ubicaciones(
    tipo: Optional[TipoUbicacion] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Ubicacion).where(Ubicacion.activo == True)
    if tipo:
        query = query.where(Ubicacion.tipo == tipo)
    if search:
        query = query.where(Ubicacion.nombre.ilike(f"%{search}%"))
    query = query.order_by(Ubicacion.nombre)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/", response_model=UbicacionResponse, status_code=201)
async def crear_ubicacion(
    data: UbicacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    ubicacion = Ubicacion(**data.model_dump())
    db.add(ubicacion)
    await db.flush()
    await db.refresh(ubicacion)
    return ubicacion


@router.get("/{ubicacion_id}", response_model=UbicacionResponse)
async def obtener_ubicacion(
    ubicacion_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Ubicacion).where(Ubicacion.id == ubicacion_id))
    ub = result.scalar_one_or_none()
    if not ub:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")
    return ub


class UbicacionUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[TipoUbicacion] = None
    descripcion: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    capacidad_estibas: Optional[int] = None
    codigo_sap: Optional[str] = None
    es_disposicion_final: Optional[bool] = None


@router.put("/{ubicacion_id}", response_model=UbicacionResponse)
async def actualizar_ubicacion(
    ubicacion_id: int,
    data: UbicacionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    result = await db.execute(select(Ubicacion).where(Ubicacion.id == ubicacion_id))
    ub = result.scalar_one_or_none()
    if not ub:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ub, field, value)
    await db.flush()
    await db.refresh(ub)
    return ub


@router.delete("/{ubicacion_id}", status_code=204)
async def eliminar_ubicacion(
    ubicacion_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    result = await db.execute(select(Ubicacion).where(Ubicacion.id == ubicacion_id))
    ub = result.scalar_one_or_none()
    if not ub:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")
    ub.activo = False
    await db.flush()


@router.get("/{ubicacion_id}/estibas")
async def estibas_en_ubicacion(
    ubicacion_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from app.infrastructure.models.estiba import Estiba
    result = await db.execute(
        select(Estiba.id, Estiba.codigo_interno, Estiba.estado, Estiba.tipo_propietario)
        .where(Estiba.ubicacion_actual_id == ubicacion_id, Estiba.activo == True)
    )
    rows = result.all()
    return [{"id": r.id, "codigo": r.codigo_interno, "estado": r.estado, "propietario": r.tipo_propietario} for r in rows]
