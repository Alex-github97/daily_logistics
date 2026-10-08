"""
Los permisos de Finanzas, comprobados en el SERVIDOR.

En el resto de la plataforma los perfiles de usuario solo esconden pantallas: la
API no los verifica, y quien arme la petición a mano entra igual. Está
documentado y es un hueco conocido.

En Finanzas eso no se puede dejar así. La diferencia entre «ve la cartera» y
«cierra el período» no es cosmética: un período cerrado es lo que respalda una
declaración presentada, y quien pueda reabrirlo puede cambiar lo declarado. Un
control que solo esconde el botón no controla nada.

Los permisos salen del perfil del usuario —`usuarios.rol_id` → `roles.permisos`—,
que es la misma fuente que ya usa el portal. No se inventa un sistema paralelo.

`ADMINISTRADOR` pasa sin comprobación, igual que en el resto de la plataforma.
Cambiarlo acá y no en los demás módulos dejaría a un administrador con menos
acceso a Finanzas que al resto, que es justo lo contrario de lo que se espera.
"""
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permisos_perfil import POR_CLAVE
from app.infrastructure.models.rol import Rol
from app.infrastructure.models.usuario import Usuario


async def permisos_de(db: AsyncSession, usuario: Usuario) -> dict:
    """El mapa de permisos del perfil de este usuario.

    Sale de `rol_id` y no del nombre del rol: guardar solo el nombre fue lo que
    dejó usuarios con el mapa vacío y sin nada visible, sin ningún mensaje que lo
    explicara.
    """
    rol_id = getattr(usuario, "rol_id", None)
    if not rol_id:
        return {}
    permisos = (await db.execute(select(Rol.permisos).where(
        Rol.id == rol_id))).scalar()
    return permisos or {}


def _es_administrador(usuario: Usuario) -> bool:
    rol = getattr(usuario, "rol", None)
    return str(getattr(rol, "value", rol) or "").upper() == "ADMINISTRADOR"


def exigir(*claves: str):
    """Dependencia que exige uno de esos permisos de Finanzas.

    Se pasa con CUALQUIERA de los indicados, no con todos: hay operaciones que
    admiten dos caminos —ver un libro vale con `fin_contabilidad` o con
    `fin_reportes`— y exigir los dos obligaría a repartir permisos de más.

    El mensaje nombra el permiso que falta. «No autorizado» a secas obliga a
    quien lo recibe a adivinar qué pedirle a su administrador.
    """
    async def guardia(
        usuario: Usuario = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Usuario:
        if _es_administrador(usuario):
            return usuario

        permisos = await permisos_de(db, usuario)

        # Sin el módulo contratado y habilitado, ni siquiera se entra. Es la
        # llave de la puerta; los demás afinan qué se hace adentro.
        if not permisos.get("erp"):
            raise HTTPException(
                403,
                "Su perfil no tiene acceso al módulo financiero. Pídalo a quien "
                "administre los usuarios de su empresa.")

        if any(permisos.get(c) for c in claves):
            return usuario

        nombres = [POR_CLAVE[c].nombre for c in claves if c in POR_CLAVE]
        raise HTTPException(
            403,
            f"Para esto hace falta el permiso «{nombres[0] if nombres else claves[0]}»"
            + (f" o alguno de: {', '.join(nombres[1:])}" if len(nombres) > 1 else "")
            + ". Su perfil no lo tiene.")

    return guardia


# Los que se usan a diario, con nombre corto para que las firmas se lean.
ver_contabilidad = exigir("fin_contabilidad", "fin_reportes")
crear_comprobantes = exigir("fin_comprobantes")
contabilizar = exigir("fin_contabilizar")
anular = exigir("fin_anular")
ver_cartera = exigir("fin_cartera", "fin_contabilidad")
registrar_pagos = exigir("fin_pagos")
ver_tesoreria = exigir("fin_tesoreria")
conciliar = exigir("fin_conciliar")
ver_impuestos = exigir("fin_impuestos", "fin_contabilidad")
manejar_periodos = exigir("fin_periodos")
ver_reportes = exigir("fin_reportes", "fin_contabilidad")
parametrizar = exigir("fin_parametrizar")
ver_terceros = exigir("fin_terceros", "fin_contabilidad", "fin_cartera")
editar_terceros = exigir("fin_terceros")
