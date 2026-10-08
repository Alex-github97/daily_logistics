"""
La guardia de permisos de la consola.

`require_operador` responde «¿es del equipo que opera la plataforma?». Esto
responde la pregunta siguiente, que es la que faltaba: «¿y puede hacer *esto*?».

Arranque sin quedarse por fuera
-------------------------------
Antes de que exista el primer miembro no hay a quién consultarle el rol, y si se
negara todo, nadie podría crear al primero. Mientras la tabla esté vacía, todo
administrador de la empresa operadora se trata como propietario. Al crear el
primer miembro esa concesión desaparece sola: desde ahí manda la tabla.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_plataforma
from app.core.roles_consola import permisos_de, POR_CLAVE
from app.core.security import decode_token
from app.infrastructure.models.plataforma import PlataformaCliente, PlataformaMiembro


class Miembro:
    """Quién está actuando y qué puede hacer."""

    def __init__(self, usuario: str, rol: str, permisos: tuple, implicito: bool = False):
        self.usuario = usuario
        self.rol = rol
        self.permisos = permisos
        # True cuando el rol no viene de la tabla sino de la concesión de
        # arranque; la consola lo usa para avisar que falta formalizar el equipo.
        self.implicito = implicito

    def puede(self, permiso: str) -> bool:
        return permiso in self.permisos


def _usuario_y_empresa(request: Request):
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Sesión no válida")
    try:
        datos = decode_token(auth[7:])
    except Exception:
        raise HTTPException(401, "Sesión no válida")
    if datos.get("type") != "access":   # el de refresco no abre la API
        raise HTTPException(401, "Sesión no válida")
    # `usr` es el nombre de usuario; `sub` lleva el id. Se prefiere el nombre
    # porque es lo que guarda la tabla del equipo. Las sesiones abiertas antes
    # de que el token lo incluyera caen al id, y el servidor las tratará como
    # no-miembro: basta con volver a entrar.
    return str(datos.get("usr") or datos.get("sub") or ""), str(datos.get("cli") or "")


async def miembro_actual(
    request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
) -> Miembro:
    """El miembro del equipo que hace la petición.

    Comprueba primero que la empresa de la sesión sea la que opera la
    plataforma: sin eso, un administrador de cualquier empresa cliente podría
    figurar en la tabla del equipo y entrar.
    """
    usuario, empresa = _usuario_y_empresa(request)
    if not usuario or not empresa:
        raise HTTPException(403, "La sesión no indica usuario o empresa")

    cliente = (await db.execute(select(PlataformaCliente).where(
        PlataformaCliente.codigo == empresa))).scalar_one_or_none()
    if not cliente or not cliente.es_operador:
        raise HTTPException(
            403, "Solo quien opera la plataforma puede entrar a la consola.")

    fila = (await db.execute(select(PlataformaMiembro).where(
        PlataformaMiembro.usuario == usuario))).scalar_one_or_none()

    if fila:
        if not fila.activo:
            raise HTTPException(
                403, "Su acceso a la consola está desactivado. Consúltelo con el propietario.")
        return Miembro(usuario, fila.rol, permisos_de(fila.rol))

    # No está en la tabla. Solo pasa si el equipo aún no se ha formalizado.
    hay_equipo = (await db.execute(
        select(func.count()).select_from(PlataformaMiembro))).scalar() or 0
    if hay_equipo:
        raise HTTPException(
            403,
            "No hace parte del equipo de la consola. Pida que lo agreguen en "
            "Equipo, indicando qué rol necesita.",
        )
    return Miembro(usuario, "PROPIETARIO", permisos_de("PROPIETARIO"), implicito=True)


def exigir(permiso: str):
    """Dependencia que exige un permiso concreto.

    Se usa como `Depends(exigir("contabilidad.editar"))`. El mensaje nombra el
    rol que sí lo tiene, para que quien lo recibe sepa qué pedir en vez de
    quedarse con un «no autorizado» a secas.
    """
    async def guardia(quien: Miembro = Depends(miembro_actual)) -> Miembro:
        if not quien.puede(permiso):
            con_permiso = [r.nombre for r in POR_CLAVE.values() if permiso in r.permisos]
            detalle = f"Su rol ({quien.rol}) no tiene «{permiso}»."
            if con_permiso:
                detalle += f" Lo tienen: {', '.join(con_permiso)}."
            raise HTTPException(403, detalle)
        return quien
    return guardia
