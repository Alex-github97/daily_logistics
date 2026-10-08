from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_operador
from app.infrastructure.models.dano import CodigoDano, EventoDano, ResponsableDano, AccionRecomendada
from app.infrastructure.models.estiba import NivelDano
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/danos", tags=["Daños"])


class CodigoDanoCreate(BaseModel):
    codigo: str
    descripcion: str
    categoria: Optional[str] = None
    costo_reparacion_promedio: Optional[float] = None


class CodigoDanoUpdate(BaseModel):
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    costo_reparacion_promedio: Optional[float] = None


class CodigoDanoResponse(BaseModel):
    id: int
    codigo: str
    descripcion: str
    categoria: Optional[str] = None
    costo_reparacion_promedio: Optional[float] = None
    model_config = {"from_attributes": True}


class EventoDanoCreate(BaseModel):
    estiba_id: int
    codigo_dano_id: int
    nivel_dano: NivelDano
    responsable: ResponsableDano = ResponsableDano.DESCONOCIDO
    accion_recomendada: Optional[AccionRecomendada] = None
    descripcion_detalle: Optional[str] = None
    costo_reparacion: Optional[float] = None
    costo_reposicion: Optional[float] = None


class EventoDanoUpdate(BaseModel):
    nivel_dano: Optional[NivelDano] = None
    responsable: Optional[ResponsableDano] = None
    accion_recomendada: Optional[AccionRecomendada] = None
    descripcion_detalle: Optional[str] = None
    costo_reparacion: Optional[float] = None
    costo_reposicion: Optional[float] = None
    resuelto: Optional[int] = None


class EventoDanoResponse(BaseModel):
    id: int
    estiba_id: int
    codigo_dano_id: int
    nivel_dano: str
    responsable: ResponsableDano
    accion_recomendada: Optional[AccionRecomendada] = None
    descripcion_detalle: Optional[str] = None
    costo_reparacion: Optional[float] = None
    fecha_evento: datetime
    resuelto: int
    model_config = {"from_attributes": True}


class EventoDanoFullResponse(BaseModel):
    id: int
    estiba_id: int
    codigo_dano_id: int
    codigo_dano: CodigoDanoResponse
    nivel_dano: str
    responsable: ResponsableDano
    accion_recomendada: Optional[AccionRecomendada] = None
    descripcion_detalle: Optional[str] = None
    costo_reparacion: Optional[float] = None
    costo_reposicion: Optional[float] = None
    fecha_evento: datetime
    resuelto: int
    model_config = {"from_attributes": True}


@router.get("/codigos", response_model=List[CodigoDanoResponse])
async def listar_codigos_dano(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(CodigoDano).where(CodigoDano.activo == 1).order_by(CodigoDano.codigo))
    return list(result.scalars().all())


@router.post("/codigos", response_model=CodigoDanoResponse, status_code=201)
async def crear_codigo_dano(
    data: CodigoDanoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    codigo = CodigoDano(**data.model_dump())
    db.add(codigo)
    await db.flush()
    await db.refresh(codigo)
    return codigo


@router.put("/codigos/{codigo_id}", response_model=CodigoDanoResponse)
async def actualizar_codigo_dano(
    codigo_id: int,
    data: CodigoDanoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    result = await db.execute(select(CodigoDano).where(CodigoDano.id == codigo_id, CodigoDano.activo == 1))
    codigo = result.scalar_one_or_none()
    if not codigo:
        raise HTTPException(status_code=404, detail="Código de daño no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(codigo, field, value)
    await db.flush()
    await db.refresh(codigo)
    return codigo


@router.delete("/codigos/{codigo_id}", status_code=204)
async def eliminar_codigo_dano(
    codigo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    result = await db.execute(select(CodigoDano).where(CodigoDano.id == codigo_id))
    codigo = result.scalar_one_or_none()
    if not codigo:
        raise HTTPException(status_code=404, detail="Código de daño no encontrado")
    codigo.activo = 0
    await db.flush()


@router.get("/eventos", response_model=List[EventoDanoFullResponse])
async def listar_eventos_estiba(
    estiba_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(EventoDano)
        .where(EventoDano.estiba_id == estiba_id)
        .options(selectinload(EventoDano.codigo_dano))
        .order_by(EventoDano.fecha_evento.desc())
    )
    return list(result.scalars().all())


@router.post("/eventos", response_model=EventoDanoFullResponse, status_code=201)
async def registrar_evento_dano(
    data: EventoDanoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    evento = EventoDano(**data.model_dump(), usuario_id=current_user.id)
    db.add(evento)
    await db.flush()

    from app.infrastructure.models.estiba import Estiba, EstadoEstiba
    estiba_result = await db.execute(select(Estiba).where(Estiba.id == data.estiba_id))
    estiba = estiba_result.scalar_one_or_none()
    if estiba:
        if data.nivel_dano in [NivelDano.GRAVE, NivelDano.TOTAL]:
            estiba.estado = EstadoEstiba.DANADA
        elif data.nivel_dano == NivelDano.MODERADO:
            estiba.estado = EstadoEstiba.EN_REPARACION
        estiba.nivel_dano = data.nivel_dano
        await db.flush()

    result2 = await db.execute(
        select(EventoDano).where(EventoDano.id == evento.id).options(selectinload(EventoDano.codigo_dano))
    )
    return result2.scalar_one()


@router.put("/eventos/{evento_id}", response_model=EventoDanoFullResponse)
async def actualizar_evento_dano(
    evento_id: int,
    data: EventoDanoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    result = await db.execute(
        select(EventoDano).where(EventoDano.id == evento_id).options(selectinload(EventoDano.codigo_dano))
    )
    evento = result.scalar_one_or_none()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento de daño no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(evento, field, value)
    await db.flush()
    await db.refresh(evento)
    result2 = await db.execute(
        select(EventoDano).where(EventoDano.id == evento_id).options(selectinload(EventoDano.codigo_dano))
    )
    return result2.scalar_one()


@router.delete("/eventos/{evento_id}", status_code=204)
async def eliminar_evento_dano(
    evento_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    result = await db.execute(select(EventoDano).where(EventoDano.id == evento_id))
    evento = result.scalar_one_or_none()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento de daño no encontrado")
    await db.delete(evento)
    await db.flush()


@router.get("/estadisticas")
async def estadisticas_danos(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from sqlalchemy import func
    result = await db.execute(
        select(CodigoDano.codigo, CodigoDano.descripcion, func.count(EventoDano.id).label("total"),
               func.sum(EventoDano.costo_reparacion).label("costo_total"))
        .join(EventoDano, EventoDano.codigo_dano_id == CodigoDano.id)
        .group_by(CodigoDano.id, CodigoDano.codigo, CodigoDano.descripcion)
        .order_by(func.count(EventoDano.id).desc())
    )
    rows = result.all()
    return [
        {"codigo": r.codigo, "descripcion": r.descripcion, "total": r.total, "costo_total": r.costo_total or 0}
        for r in rows
    ]
