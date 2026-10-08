from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_token
from app.infrastructure.repositories.usuario_repository import UsuarioRepository
from app.infrastructure.models.usuario import Usuario, RolUsuario

# auto_error=False → devuelve None en vez de 403 cuando no hay token; nosotros levantamos 401
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionó token de acceso",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    # Solo el token de acceso abre la API. Sin esta comprobación, el token de
    # refresco que entrega el login (válido 7 días) servía igual que el de
    # acceso (8 horas), y cualquier otro token firmado con un `sub` numérico —el
    # de un dispositivo, por ejemplo— se habría tomado por ese usuario.
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido",
                            headers={"WWW-Authenticate": "Bearer"})
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    repo = UsuarioRepository(db)
    user = await repo.get_by_id(int(user_id))
    if not user or not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")
    # Si lo volvieron usuario del portal de un depositante después de entrar,
    # su sesión vieja (sin el depositante en el token) ya no sirve: así nadie
    # conserva acceso amplio hasta que el token venza.
    if not payload.get("dep") and user.rol != "ADMINISTRADOR":
        from app.infrastructure.models.wms import WMSDepositanteUsuario
        if (await db.execute(select(WMSDepositanteUsuario.id).where(
                WMSDepositanteUsuario.usuario_id == user.id))).first():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Su acceso cambió: vuelva a iniciar sesión.")
    return user


async def require_admin(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.rol not in [RolUsuario.ADMINISTRADOR]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol de administrador")
    return current_user


async def require_supervisor(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.rol not in [RolUsuario.ADMINISTRADOR, RolUsuario.SUPERVISOR_LOGISTICO]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    return current_user


async def require_operador(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.rol not in [
        RolUsuario.ADMINISTRADOR, RolUsuario.SUPERVISOR_LOGISTICO, RolUsuario.OPERADOR_BODEGA
    ]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    return current_user


async def require_conductor(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Permite acceso a conductores y cualquier rol superior."""
    allowed = [
        RolUsuario.ADMINISTRADOR, RolUsuario.SUPERVISOR_LOGISTICO,
        RolUsuario.OPERADOR_BODEGA, RolUsuario.CONDUCTOR,
    ]
    if current_user.rol not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    return current_user


def require_module_permission(module: str):
    """
    Verifica acceso a un módulo específico.
    - Roles sistema (ADMINISTRADOR, SUPERVISOR, OPERADOR) conservan su acceso actual.
    - Roles personalizados: se consulta permisos[module] en el JSON del rol.
    Uso: Depends(require_module_permission("estibas"))
    """
    async def _check(current_user: Usuario = Depends(get_current_user)) -> Usuario:
        # Roles sistema con acceso operacional completo — ruta rápida
        if current_user.rol in [
            RolUsuario.ADMINISTRADOR,
            RolUsuario.SUPERVISOR_LOGISTICO,
            RolUsuario.OPERADOR_BODEGA,
        ]:
            return current_user
        # Roles personalizados o restringidos: verificar el JSON permisos del rol
        if current_user.permisos.get(module, False):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado",
        )
    return _check
