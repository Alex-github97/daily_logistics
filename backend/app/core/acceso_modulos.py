"""
Hace cumplir qué módulos tiene contratados cada empresa.

Ocultar un módulo en el menú no es control de acceso: quien escriba la URL a
mano entra igual. La comprobación tiene que estar del lado del servidor, y por
eso vive acá y se aplica a toda petición de la API.

El resultado se guarda en memoria por unos segundos porque, si no, cada
petición del portal costaría una consulta extra solo para volver a preguntar lo
mismo. Cuando el operador cambia los módulos de una empresa llama a `olvidar()`,
así que el cambio se ve de inmediato y no dentro de un minuto.
"""
import time
from typing import Dict, Optional, Set, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import AsyncSessionLocal
from app.core.modulos import ESENCIALES, POR_CLAVE, modulo_de_ruta
from app.core.security import decode_token
from app.core.tenant import ESQUEMA_PLATAFORMA

# código de empresa -> (módulos, momento en que se leyó)
_cache: Dict[str, Tuple[Set[str], float]] = {}
_VIGENCIA = 30.0  # segundos


def olvidar(codigo: Optional[str] = None) -> None:
    """Descarta lo memorizado, para que el próximo acceso lo vuelva a leer."""
    if codigo is None:
        _cache.clear()
    else:
        _cache.pop(codigo, None)


async def modulos_de(codigo: str) -> Set[str]:
    """Los módulos activos de una empresa, con los esenciales siempre incluidos."""
    guardado = _cache.get(codigo)
    if guardado and (time.monotonic() - guardado[1]) < _VIGENCIA:
        return guardado[0]

    async with AsyncSessionLocal() as s:
        await s.execute(text(f'SET search_path TO "{ESQUEMA_PLATAFORMA}"'))
        r = await s.execute(text(
            "SELECT m.modulo FROM plataforma_modulo_cliente m "
            "JOIN plataforma_cliente c ON c.id = m.cliente_id "
            "WHERE c.codigo = :c AND m.activo"), {"c": codigo})
        contratados = {fila[0] for fila in r.all()}

        # Una empresa sin ninguna fila es una que se dio de alta antes de que
        # esto existiera. Negarle todo la dejaría fuera de su propia
        # plataforma, así que se le permite todo hasta que se le asigne algo.
        if not contratados:
            r2 = await s.execute(text(
                "SELECT count(*) FROM plataforma_modulo_cliente m "
                "JOIN plataforma_cliente c ON c.id = m.cliente_id WHERE c.codigo = :c"),
                {"c": codigo})
            if not (r2.scalar() or 0):
                contratados = {"*"}

    modulos = set(contratados) | set(ESENCIALES)
    _cache[codigo] = (modulos, time.monotonic())
    return modulos


class ModulosMiddleware(BaseHTTPMiddleware):
    """Corta las peticiones a módulos que la empresa no tiene contratados."""

    async def dispatch(self, request: Request, call_next):
        ruta = request.url.path
        if not ruta.startswith("/api/v1"):
            return await call_next(request)

        modulo = modulo_de_ruta(ruta)
        # Ruta que no pertenece a ningún módulo: no hay nada que cobrar ni que
        # negar, y `exigir_sesion` ya decide si necesita token.
        if modulo is None or modulo in ESENCIALES:
            return await call_next(request)

        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return await call_next(request)   # sin sesión: lo resuelve la autenticación
        try:
            codigo = decode_token(auth[7:]).get("cli")
        except Exception:
            return await call_next(request)   # token ilegible: lo resuelve la autenticación
        if not codigo:
            return await call_next(request)

        permitidos = await modulos_de(str(codigo))
        if "*" not in permitidos and modulo not in permitidos:
            nombre = POR_CLAVE[modulo].nombre if modulo in POR_CLAVE else modulo
            return JSONResponse(
                status_code=403,
                content={"detail": f"Su empresa no tiene contratado el módulo «{nombre}». "
                                   f"Consúltelo con su administrador."},
            )
        return await call_next(request)
