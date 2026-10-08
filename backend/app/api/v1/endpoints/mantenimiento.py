from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, Column, Integer, String, Boolean
from pydantic import BaseModel
import math

from app.core.database import get_db, Base
from app.core.dependencies import get_current_user, require_operador
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.mantenimiento import MantenimientoEstiba
from app.infrastructure.models.estiba import Estiba, TipoEstiba, EstadoEstiba, TipoPropietario
from app.infrastructure.models.proveedor import Proveedor


class ActividadMantenimiento(Base):
    __tablename__ = "actividades_mantenimiento"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False, unique=True)
    activo = Column(Boolean, nullable=False, default=True)


class ActividadCreate(BaseModel):
    nombre: str

class ActividadResponse(BaseModel):
    id: int
    nombre: str
    activo: bool
    model_config = {"from_attributes": True}
from app.application.schemas.mantenimiento import (
    MantenimientoCreate, MantenimientoResponse,
    MantenimientoListResponse, CostosReporteResponse, CostoEstibaItem,
)

router = APIRouter(prefix="/mantenimientos", tags=["Mantenimiento"])


@router.get("/reporte-costos", response_model=CostosReporteResponse)
async def reporte_costos(
    tipo: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    tipo_propietario: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = (
        select(
            Estiba.id,
            Estiba.codigo_interno,
            Estiba.tipo,
            Estiba.estado,
            Estiba.fecha_ingreso,
            Estiba.tipo_propietario,
            Estiba.valor_compra,
            func.coalesce(func.sum(MantenimientoEstiba.costo), 0.0).label("total_costo_mantenimiento"),
            func.count(MantenimientoEstiba.id).label("cantidad_mantenimientos"),
        )
        .outerjoin(MantenimientoEstiba, MantenimientoEstiba.estiba_id == Estiba.id)
        .where(Estiba.activo == True)
        .group_by(Estiba.id, Estiba.codigo_interno, Estiba.tipo, Estiba.estado,
                  Estiba.fecha_ingreso, Estiba.tipo_propietario, Estiba.valor_compra)
    )

    if tipo:
        query = query.where(Estiba.tipo == tipo)
    if estado:
        query = query.where(Estiba.estado == estado)
    if tipo_propietario:
        query = query.where(Estiba.tipo_propietario == tipo_propietario)

    count_result = await db.execute(
        select(func.count()).select_from(
            select(Estiba.id).where(Estiba.activo == True)
            .filter(*(
                ([Estiba.tipo == tipo] if tipo else []) +
                ([Estiba.estado == estado] if estado else []) +
                ([Estiba.tipo_propietario == tipo_propietario] if tipo_propietario else [])
            ))
            .subquery()
        )
    )
    total = count_result.scalar_one()

    total_costo_result = await db.execute(
        select(func.coalesce(func.sum(MantenimientoEstiba.costo), 0.0))
    )
    total_costos = total_costo_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(func.coalesce(func.sum(MantenimientoEstiba.costo), 0.0).desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    items = [
        CostoEstibaItem(
            estiba_id=row.id,
            codigo_interno=row.codigo_interno,
            tipo=row.tipo.value if hasattr(row.tipo, "value") else str(row.tipo),
            estado=row.estado.value if hasattr(row.estado, "value") else str(row.estado),
            fecha_ingreso=row.fecha_ingreso,
            tipo_propietario=row.tipo_propietario.value if hasattr(row.tipo_propietario, "value") else str(row.tipo_propietario),
            valor_compra=row.valor_compra,
            total_costo_mantenimiento=float(row.total_costo_mantenimiento),
            cantidad_mantenimientos=int(row.cantidad_mantenimientos),
        )
        for row in rows
    ]

    return CostosReporteResponse(
        items=items,
        total=total,
        total_costos_acumulados=float(total_costos),
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.get("/", response_model=MantenimientoListResponse)
async def listar_mantenimientos(
    estiba_id: Optional[int] = Query(None),
    tipo: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = (
        select(MantenimientoEstiba, Estiba.codigo_interno, Usuario.nombre, Proveedor.razon_social)
        .join(Estiba, MantenimientoEstiba.estiba_id == Estiba.id)
        .join(Proveedor, MantenimientoEstiba.proveedor_id == Proveedor.id)
        .outerjoin(Usuario, MantenimientoEstiba.usuario_id == Usuario.id)
    )

    if estiba_id:
        query = query.where(MantenimientoEstiba.estiba_id == estiba_id)
    if tipo:
        query = query.where(MantenimientoEstiba.tipo == tipo)
    if desde:
        query = query.where(MantenimientoEstiba.fecha >= desde)
    if hasta:
        query = query.where(MantenimientoEstiba.fecha <= hasta)

    query = query.order_by(MantenimientoEstiba.fecha.desc())
    result = await db.execute(query)
    rows = result.all()

    total_costo_q = select(func.coalesce(func.sum(MantenimientoEstiba.costo), 0.0))
    if estiba_id:
        total_costo_q = total_costo_q.where(MantenimientoEstiba.estiba_id == estiba_id)
    if tipo:
        total_costo_q = total_costo_q.where(MantenimientoEstiba.tipo == tipo)
    if desde:
        total_costo_q = total_costo_q.where(MantenimientoEstiba.fecha >= desde)
    if hasta:
        total_costo_q = total_costo_q.where(MantenimientoEstiba.fecha <= hasta)
    tc_result = await db.execute(total_costo_q)
    total_costo = tc_result.scalar_one()

    items = []
    for mant, codigo, usuario_nombre, proveedor_nombre in rows:
        items.append(MantenimientoResponse(
            id=mant.id,
            estiba_id=mant.estiba_id,
            estiba_codigo=codigo,
            fecha=mant.fecha,
            tipo=mant.tipo,
            descripcion=mant.descripcion,
            costo=mant.costo,
            proveedor_id=mant.proveedor_id,
            proveedor_nombre=proveedor_nombre,
            usuario_id=mant.usuario_id,
            usuario_nombre=usuario_nombre,
            created_at=mant.created_at,
        ))

    return MantenimientoListResponse(items=items, total=len(items), total_costo=float(total_costo))


@router.post("/", response_model=MantenimientoResponse, status_code=201)
async def registrar_mantenimiento(
    data: MantenimientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    estiba = await db.get(Estiba, data.estiba_id)
    if not estiba or not estiba.activo:
        raise HTTPException(status_code=404, detail="Estiba no encontrada")

    proveedor = await db.get(Proveedor, data.proveedor_id)
    if not proveedor or not proveedor.activo:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    mant = MantenimientoEstiba(
        estiba_id=data.estiba_id,
        fecha=data.fecha,
        tipo=data.tipo,
        descripcion=data.descripcion,
        costo=data.costo,
        proveedor_id=data.proveedor_id,
        usuario_id=current_user.id,
    )
    db.add(mant)
    await db.commit()
    await db.refresh(mant)

    return MantenimientoResponse(
        id=mant.id,
        estiba_id=mant.estiba_id,
        estiba_codigo=estiba.codigo_interno,
        fecha=mant.fecha,
        tipo=mant.tipo,
        descripcion=mant.descripcion,
        costo=mant.costo,
        proveedor_id=mant.proveedor_id,
        proveedor_nombre=proveedor.razon_social,
        usuario_id=mant.usuario_id,
        usuario_nombre=current_user.nombre,
        created_at=mant.created_at,
    )


@router.delete("/{mantenimiento_id}", status_code=204)
async def eliminar_mantenimiento(
    mantenimiento_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    mant = await db.get(MantenimientoEstiba, mantenimiento_id)
    if not mant:
        raise HTTPException(status_code=404, detail="Registro de mantenimiento no encontrado")
    await db.delete(mant)
    await db.commit()


# ── Actividades de mantenimiento ─────────────────────────────────────────────

@router.get("/actividades", response_model=List[ActividadResponse])
async def listar_actividades(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(ActividadMantenimiento)
        .where(ActividadMantenimiento.activo == True)
        .order_by(ActividadMantenimiento.nombre)
    )
    return list(result.scalars().all())


@router.post("/actividades", response_model=ActividadResponse, status_code=201)
async def crear_actividad(
    data: ActividadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    nombre = data.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    existing = await db.execute(
        select(ActividadMantenimiento).where(ActividadMantenimiento.nombre == nombre)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe una actividad con ese nombre")
    actividad = ActividadMantenimiento(nombre=nombre)
    db.add(actividad)
    await db.commit()
    await db.refresh(actividad)
    return actividad


@router.delete("/actividades/{actividad_id}", status_code=204)
async def eliminar_actividad(
    actividad_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    actividad = await db.get(ActividadMantenimiento, actividad_id)
    if not actividad:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    actividad.activo = False
    await db.commit()
