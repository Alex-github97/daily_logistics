"""
Autenticación por omisión para toda la API.

De las 1.236 rutas, 470 no pedían token: se podía leer y escribir sin
identificarse. Poner la dependencia en cada una era editar 470 firmas y, sobre
todo, dejar la puerta abierta a que la próxima ruta naciera igual de expuesta.

Acá se exige token en todas y se exime a mano el puñado que debe ser público.
El defecto pasa a ser seguro: una ruta nueva queda protegida sin que nadie tenga
que acordarse.
"""
from fastapi import Depends, HTTPException, Request, status

from app.core.security import decode_token

# Lo único que se atiende sin sesión, y por qué.
RUTAS_PUBLICAS = (
    "/api/v1/auth/login",              # todavía no hay sesión
    "/api/v1/auth/clientes",           # paso previo: a qué empresa se entra
    "/api/v1/ags/publico",             # reserva de citas por parte del cliente final
    "/api/v1/landing/contenido",       # la pagina publica la ve cualquiera
    # El reporte de una pantalla que se rompio. Va sin sesion a proposito: los
    # fallos que mas importa registrar son justamente los que ocurren cuando
    # algo va mal —una sesion a medias, un token ilegible, la propia pantalla de
    # ingreso rompiendose— y exigir token dejaria fuera del registro los casos
    # peores. Solo escribe en la bitacora, recorta todo lo que llega y no
    # devuelve nada: no sirve para leer ni para deducir si un dato existe.
    "/api/v1/plataforma/fallo-interfaz",
    # Avisos de pedidos de los marketplaces y la vuelta de la autorización de
    # MercadoLibre: los llaman las plataformas. Cada canal se identifica por un
    # token largo e impredecible y, cuando la plataforma firma, se verifica.
    "/api/v1/integraciones/",
    "/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
)


# Rutas de dispositivos: no aceptan sesión de usuario, sino el token del equipo.
RUTAS_DISPOSITIVO = ("/api/v1/wms/cubicador/",)

# Lo único que abre el token de un usuario del portal de un depositante.
RUTAS_PORTAL = ("/api/v1/wms/portal/", "/api/v1/auth/me", "/api/v1/auth/change-password")


def es_publica(ruta: str) -> bool:
    return any(ruta.startswith(p) for p in RUTAS_PUBLICAS)


async def exigir_sesion(request: Request) -> None:
    """Exige token salvo en las rutas públicas.

    Se resuelve por ruta y no por router para que las excepciones queden
    enumeradas en un solo sitio, a la vista.
    """
    if es_publica(request.url.path):
        return
    # OPTIONS lo manda el navegador antes de la petición real, sin cabeceras.
    if request.method == "OPTIONS":
        return
    credenciales = request.headers.get("authorization") or ""
    if not credenciales.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionó token de acceso",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Se verifica la firma y el vencimiento, no solo que venga algo: comprobar
    # únicamente que la cabecera existe dejaría pasar cualquier texto.
    # `decode_token` lanza 401 por su cuenta si no cuadra.
    payload = decode_token(credenciales[7:])
    # El cubicador (un ESP32) tiene su propio token, que solo abre sus dos
    # rutas; allí la dependencia `cubicador_actual` lo valida contra la huella
    # guardada. En el resto de la API solo vale el token de acceso.
    if request.url.path.startswith(RUTAS_DISPOSITIVO) and payload.get("type") == "cubicador":
        return
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token no sirve para acceder; use el de acceso, no el de refresco",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Un cliente del 3PL ve su portal y nada más: ni el inventario de otros
    # depositantes ni los demás módulos. El depositante va firmado en el token.
    if payload.get("dep") and not request.url.path.startswith(RUTAS_PORTAL):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Su usuario es del portal de clientes: solo puede consultar su mercancía.")
