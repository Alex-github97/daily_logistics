"""
Resuelve a qué cliente pertenece cada petición, antes de que toque la base.

El inquilino sale del token firmado. En las rutas previas al login —donde
todavía no hay token— sale de la cabecera `X-Cliente`, que solo sirve para
consultar el registro y para autenticarse contra ese cliente; nunca para leer
datos, porque esas rutas no los tocan.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.security import decode_token
from app.core.tenant import (
    ESQUEMA_POR_DEFECTO, codigo_valido, fijar_esquema, nombre_esquema,
)

# Rutas que se atienden sin inquilino: son las que sirven para elegirlo, más el
# reporte de fallos de la interfaz.
#
# Ese último está aquí a propósito. Los fallos que más importa registrar ocurren
# justamente cuando algo va mal —una sesión a medias, un token ilegible, la
# propia pantalla de ingreso rompiéndose— y exigir inquilino dejaría fuera del
# registro los casos peores. Solo escribe en la bitácora y no devuelve nada.
RUTAS_SIN_CLIENTE = (
    "/api/v1/auth/clientes", "/api/v1/plataforma/fallo-interfaz",
    "/health", "/docs", "/openapi.json", "/redoc",
)


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        fijar_esquema(None)
        ruta = request.url.path

        if not any(ruta.startswith(p) for p in RUTAS_SIN_CLIENTE):
            # El esquema sale del token firmado. No se deduce del código: el
            # cliente que ya existía vive en "public" y su código es otro, así
            # que deducirlo lo mandaría a un esquema que no es el suyo.
            esquema = None
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                try:
                    esquema = decode_token(auth[7:]).get("esq")
                except Exception:
                    # Un token inválido lo rechaza después la dependencia de
                    # autenticación, con su propio mensaje.
                    esquema = None

            # El login todavía no tiene token: resuelve el esquema él mismo
            # contra el registro, que es la única fuente válida.
            fijar_esquema(esquema if esquema and codigo_valido(esquema.replace("cli_", ""))
                          else ESQUEMA_POR_DEFECTO)

        try:
            return await call_next(request)
        finally:
            fijar_esquema(None)
