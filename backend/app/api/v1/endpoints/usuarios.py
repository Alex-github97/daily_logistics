from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.core.security import hash_password
from app.infrastructure.repositories.usuario_repository import UsuarioRepository
from app.infrastructure.models.usuario import Usuario, RolUsuario
from app.infrastructure.models.rol import Rol
from app.application.schemas.usuario import UsuarioCreate, UsuarioUpdate, UsuarioResponse

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


async def _resolve_rol_id(db: AsyncSession, rol_nombre: str) -> int | None:
    result = await db.execute(select(Rol).where(Rol.nombre == rol_nombre))
    rol = result.scalar_one_or_none()
    return rol.id if rol else None


@router.get("/roles-info")
async def info_roles(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_admin),
):
    result = await db.execute(select(Rol).order_by(Rol.es_sistema.desc(), Rol.nombre))
    roles = result.scalars().all()
    return [
        {
            "rol": r.nombre,
            "label": r.label or r.nombre,
            "descripcion": r.descripcion or "",
            "modulos": r.permisos or {},
        }
        for r in roles
    ]


@router.get("/", response_model=List[UsuarioResponse])
async def listar_usuarios(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    repo = UsuarioRepository(db)
    return await repo.get_activos()


@router.post("/", response_model=UsuarioResponse, status_code=201)
async def crear_usuario(
    data: UsuarioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    repo = UsuarioRepository(db)
    if await repo.get_by_email(data.email):
        raise HTTPException(status_code=409, detail="El email ya está registrado")
    if await repo.get_by_username(data.username):
        raise HTTPException(status_code=409, detail="El nombre de usuario ya está en uso")
    rol_id = await _resolve_rol_id(db, data.rol)
    user = Usuario(
        nombre=data.nombre, apellido=data.apellido, email=data.email,
        username=data.username, hashed_password=hash_password(data.password),
        rol=data.rol, rol_id=rol_id, telefono=data.telefono, cargo=data.cargo,
    )
    return await repo.create(user)


@router.get("/{usuario_id}", response_model=UsuarioResponse)
async def obtener_usuario(
    usuario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    repo = UsuarioRepository(db)
    user = await repo.get_by_id(usuario_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.put("/{usuario_id}", response_model=UsuarioResponse)
async def actualizar_usuario(
    usuario_id: int,
    data: UsuarioUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    repo = UsuarioRepository(db)
    user = await repo.get_by_id(usuario_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    update_data = data.model_dump(exclude_unset=True)
    if "rol" in update_data:
        rol_id = await _resolve_rol_id(db, update_data["rol"])
        update_data["rol_id"] = rol_id
    return await repo.update(user, update_data)


@router.put("/{usuario_id}/reset-password", status_code=200)
async def resetear_password(
    usuario_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    nueva_password = payload.get("nueva_password", "")
    if len(nueva_password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    repo = UsuarioRepository(db)
    user = await repo.get_by_id(usuario_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await repo.update(user, {"hashed_password": hash_password(nueva_password)})
    return {"detail": "Contraseña actualizada exitosamente"}


@router.delete("/{usuario_id}", status_code=204)
async def desactivar_usuario(
    usuario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    if usuario_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")
    repo = UsuarioRepository(db)
    user = await repo.get_by_id(usuario_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await repo.update(user, {"activo": False})
