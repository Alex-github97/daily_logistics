from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.infrastructure.models.rol import Rol
from app.infrastructure.models.usuario import Usuario
from app.application.schemas.rol import RolCreate, RolUpdate, RolResponse

router = APIRouter(prefix="/roles", tags=["Roles"])


async def _count_users(db: AsyncSession, rol_id: int) -> int:
    result = await db.execute(
        select(func.count(Usuario.id)).where(
            Usuario.rol_id == rol_id,
            Usuario.activo == True,
        )
    )
    return result.scalar() or 0


@router.get("/", response_model=List[RolResponse])
async def listar_roles(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(Rol).order_by(Rol.es_sistema.desc(), Rol.nombre)
    )
    roles = result.scalars().all()

    counts_result = await db.execute(
        select(Usuario.rol_id, func.count(Usuario.id).label("total"))
        .where(Usuario.activo == True)
        .group_by(Usuario.rol_id)
    )
    counts = {row.rol_id: row.total for row in counts_result}

    return [
        RolResponse(
            id=r.id,
            nombre=r.nombre,
            label=r.label,
            descripcion=r.descripcion,
            color=r.color,
            permisos=r.permisos or {},
            es_sistema=r.es_sistema,
            total_usuarios=counts.get(r.id, 0),
            created_at=r.created_at,
        )
        for r in roles
    ]


@router.post("/", response_model=RolResponse, status_code=201)
async def crear_rol(
    data: RolCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    nombre = data.nombre.upper().replace(" ", "_")
    existing = await db.execute(select(Rol).where(Rol.nombre == nombre))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un rol con ese nombre")

    rol = Rol(
        nombre=nombre,
        label=data.label or data.nombre,
        descripcion=data.descripcion,
        color=data.color,
        permisos=dict(data.permisos),
        es_sistema=False,
    )
    db.add(rol)
    await db.commit()
    await db.refresh(rol)
    return RolResponse(
        id=rol.id, nombre=rol.nombre, label=rol.label, descripcion=rol.descripcion,
        color=rol.color, permisos=rol.permisos, es_sistema=rol.es_sistema,
        total_usuarios=0, created_at=rol.created_at,
    )


@router.put("/{rol_id}", response_model=RolResponse)
async def actualizar_rol(
    rol_id: int,
    data: RolUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(Rol).where(Rol.id == rol_id))
    rol = result.scalar_one_or_none()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    if data.nombre and data.nombre.upper().replace(" ", "_") != rol.nombre:
        if rol.es_sistema:
            raise HTTPException(status_code=400, detail="No se puede cambiar el nombre de un rol del sistema")
        nuevo_nombre = data.nombre.upper().replace(" ", "_")
        dup = await db.execute(select(Rol).where(Rol.nombre == nuevo_nombre, Rol.id != rol_id))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Ya existe un rol con ese nombre")
        rol.nombre = nuevo_nombre

    if data.label is not None:
        rol.label = data.label
    if data.descripcion is not None:
        rol.descripcion = data.descripcion
    if data.color is not None:
        rol.color = data.color
    if data.permisos is not None:
        rol.permisos = dict(data.permisos)

    await db.commit()
    await db.refresh(rol)
    total = await _count_users(db, rol_id)
    return RolResponse(
        id=rol.id, nombre=rol.nombre, label=rol.label, descripcion=rol.descripcion,
        color=rol.color, permisos=rol.permisos, es_sistema=rol.es_sistema,
        total_usuarios=total, created_at=rol.created_at,
    )


@router.delete("/{rol_id}", status_code=204)
async def eliminar_rol(
    rol_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(Rol).where(Rol.id == rol_id))
    rol = result.scalar_one_or_none()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    if rol.es_sistema:
        raise HTTPException(status_code=400, detail="No se pueden eliminar los roles del sistema")

    total = await _count_users(db, rol_id)
    if total > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar: {total} usuario(s) tienen este rol asignado",
        )

    await db.delete(rol)
    await db.commit()
