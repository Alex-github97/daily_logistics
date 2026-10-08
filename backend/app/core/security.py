from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: Any, expires_delta: Optional[timedelta] = None,
    cliente: Optional[str] = None, esquema: Optional[str] = None,
    usuario: Optional[str] = None, depositante: Optional[int] = None,
) -> str:
    """El cliente viaja dentro del token, firmado.

    Si el inquilino se tomara de una cabecera suelta, cualquiera podría pedir
    datos de otro cliente con su propio token: el usuario es válido, solo cambia
    a qué esquema apunta. Yendo firmado, cambiarlo invalida la firma.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(subject), "exp": expire, "type": "access"}
    if cliente:
        payload["cli"] = cliente
    if esquema:
        payload["esq"] = esquema
    # El nombre de usuario, además del id. `sub` lleva el id, que es lo correcto
    # para identificar, pero todo lo que se muestra o se compara con una tabla
    # —el autor de un mensaje de soporte, el miembro del equipo— usa el nombre.
    # Sin esto había que consultar la base en cada petición solo para saberlo, y
    # los mensajes salían firmados con un número.
    if usuario:
        payload["usr"] = usuario
    # Usuario del portal de un depositante: la API solo le abre su portal.
    if depositante:
        payload["dep"] = depositante
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: Any, cliente: Optional[str] = None, esquema: Optional[str] = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(subject), "exp": expire, "type": "refresh"}
    if cliente:
        payload["cli"] = cliente
    if esquema:
        payload["esq"] = esquema
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
