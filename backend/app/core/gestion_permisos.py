"""
Quién ve qué, dentro del módulo de gestión.

El permiso de consola (`gestion.ver`, `gestion.trabajar`) responde «¿puede hacer
esta clase de cosa?». Acá se responde la pregunta que falta y que es la que de
verdad protege: **¿puede hacerlo sobre ESTE objeto?**. Sin la segunda, cualquiera
con `gestion.ver` alcanza el proyecto reservado de dirección escribiendo su id en
la URL.

Se comprueba en el servidor y no en la pantalla. En el resto de la plataforma los
perfiles de usuario solo esconden pantallas —la API no los verifica— y eso es un
hueco conocido; este módulo no lo repite.

Un proyecto restringido responde **404 y no 403** a quien no es miembro. Un 403
confirma que el proyecto existe, y con eso solo ya se puede ir sondeando ids
hasta reconstruir el mapa de lo que hay.
"""
from typing import Iterable, Optional, Set

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permisos_consola import Miembro
from app.infrastructure.models.gestion import GPProyecto, GPProyectoMiembro


async def proyectos_visibles(db: AsyncSession, quien: Miembro) -> Optional[Set[int]]:
    """Los proyectos que esta persona puede ver. `None` significa «todos».

    Devolver `None` en vez de la lista completa no es un atajo: con muchos
    proyectos, arrastrar un `IN (...)` de mil elementos a cada consulta le impide
    al planificador usar los índices por proyecto. Cuando no hay ninguno
    restringido —el caso normal— no hace falta filtrar nada.
    """
    r = await db.execute(
        select(GPProyecto.id).where(GPProyecto.restringido.is_(True)))
    restringidos = {i for (i,) in r.all()}
    if not restringidos:
        return None

    r = await db.execute(
        select(GPProyectoMiembro.proyecto_id).where(
            GPProyectoMiembro.usuario == quien.usuario))
    mios = {i for (i,) in r.all()}

    r = await db.execute(select(GPProyecto.id))
    todos = {i for (i,) in r.all()}
    return (todos - restringidos) | (restringidos & mios)


def limitar(consulta, visibles: Optional[Set[int]], columna):
    """Aplica el filtro de proyectos visibles a una consulta, si hace falta."""
    if visibles is None:
        return consulta
    if not visibles:
        # Sin ningún proyecto visible: una condición imposible es más clara y más
        # segura que devolver la consulta sin filtrar.
        return consulta.where(columna.in_([-1]))
    return consulta.where(columna.in_(visibles))


async def exigir_proyecto(db: AsyncSession, quien: Miembro, proyecto_id: int,
                          escritura: bool = False) -> GPProyecto:
    """El proyecto, si esta persona puede llegar a él. Si no, corta la petición.

    `escritura` exige además que el proyecto no esté archivado: un proyecto
    archivado se consulta pero no recibe trabajo nuevo, o el archivo dejaría de
    significar nada.
    """
    proyecto = (await db.execute(
        select(GPProyecto).where(GPProyecto.id == proyecto_id))).scalar_one_or_none()
    if proyecto is None:
        raise HTTPException(404, "Ese proyecto no existe.")

    if proyecto.restringido:
        es_miembro = (await db.execute(
            select(GPProyectoMiembro.id).where(
                GPProyectoMiembro.proyecto_id == proyecto_id,
                GPProyectoMiembro.usuario == quien.usuario))).first()
        if not es_miembro:
            # 404 y no 403: ver arriba.
            raise HTTPException(404, "Ese proyecto no existe.")

    if escritura and proyecto.archivado:
        raise HTTPException(
            409,
            f"«{proyecto.nombre}» está archivado. Reactívelo antes de agregarle "
            f"trabajo.")

    return proyecto


async def es_miembro_de(db: AsyncSession, usuario: str, proyecto_id: int) -> bool:
    fila = (await db.execute(
        select(GPProyectoMiembro.id).where(
            GPProyectoMiembro.proyecto_id == proyecto_id,
            GPProyectoMiembro.usuario == usuario))).first()
    return fila is not None


async def roles_en(db: AsyncSession, usuario: str,
                   proyectos: Iterable[int]) -> dict:
    """El rol de esta persona en cada uno de esos proyectos."""
    ids = list(proyectos)
    if not ids:
        return {}
    r = await db.execute(
        select(GPProyectoMiembro.proyecto_id, GPProyectoMiembro.rol).where(
            GPProyectoMiembro.usuario == usuario,
            GPProyectoMiembro.proyecto_id.in_(ids)))
    return {pid: rol for pid, rol in r.all()}
