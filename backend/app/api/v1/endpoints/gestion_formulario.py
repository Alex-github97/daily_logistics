"""
El esquema del formulario, y los catálogos que no existían: versiones,
componentes y tipos de vínculo.

`GET /gestion/formulario` devuelve, en una sola petición, qué se pide para un
proyecto y un tipo concretos: las secciones, sus campos, las opciones ya
resueltas, los valores por defecto y —si se está editando— lo que hay guardado.

La pantalla no decide nada. Recorre eso y dibuja. Es lo que hace que agregar un
campo, cambiarlo de sección o marcarlo obligatorio no toque el frontend.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import gestion_formulario
from app.core.database import get_db_plataforma
from app.core.gestion_permisos import exigir_proyecto
from app.core.permisos_consola import Miembro, exigir
from app.infrastructure.models.gestion import (
    SECCIONES, TIPOS_CAMPO, TIPOS_DE_ENTIDAD, TIPOS_MULTIPLES,
    GPComponente, GPIncidencia, GPTipoVinculo, GPVersion,
)

router = APIRouter(prefix="/gestion", tags=["Gestión"])


@router.get("/formulario")
async def formulario(
    proyecto_id: Optional[int] = None,
    tipo_id: Optional[int] = None,
    incidencia_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Qué se pide para este proyecto y este tipo.

    Se vuelve a pedir cuando cambie cualquiera de los dos: los campos que
    dependen del proyecto —sprint, épica, versión, componente— traen otras
    opciones, y el tipo puede cambiar qué campos aplican. Cada campo declara de
    qué depende, así que la pantalla no lleva esa regla escrita.
    """
    if proyecto_id is not None:
        await exigir_proyecto(db, quien, proyecto_id)

    incidencia = None
    if incidencia_id is not None:
        incidencia = (await db.execute(select(GPIncidencia).where(
            GPIncidencia.id == incidencia_id))).scalar_one_or_none()
        if incidencia is None:
            raise HTTPException(404, "Esa incidencia no existe.")
        await exigir_proyecto(db, quien, incidencia.proyecto_id)
        proyecto_id = incidencia.proyecto_id
        tipo_id = incidencia.tipo_id

    return await gestion_formulario.esquema(
        db, proyecto_id, tipo_id, quien.usuario, incidencia)


@router.get("/formulario/vocabulario")
async def vocabulario(quien: Miembro = Depends(exigir("gestion.ver"))):
    """Con qué se puede configurar un campo.

    Sale del mismo sitio del que se valida: una lista escrita en la pantalla de
    configuración acabaría ofreciendo un tipo que el servidor rechaza.
    """
    return {
        "tipos": [
            {"clave": t, "entidad": TIPOS_DE_ENTIDAD.get(t),
             "multiple": t in TIPOS_MULTIPLES}
            for t in TIPOS_CAMPO
        ],
        "secciones": [{"clave": c, "titulo": t} for c, t in SECCIONES],
        "entidades": sorted(set(TIPOS_DE_ENTIDAD.values())),
        "defectos": [
            {"clave": "@yo", "nombre": "Quien está creando"},
            {"clave": "@hoy", "nombre": "Hoy"},
            {"clave": "@ahora", "nombre": "Este instante"},
            {"clave": "@sprint_activo", "nombre": "El sprint en curso"},
        ],
    }


# ─── Versiones ────────────────────────────────────────────────────────────────

class VersionEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    descripcion: Optional[str] = None
    fecha: Optional[str] = None
    liberada: bool = False


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    proyecto_id: int
    nombre: str
    descripcion: Optional[str] = None
    fecha: Optional[Any] = None
    liberada: bool
    archivada: bool
    orden: int
    incidencias: int = 0


@router.get("/proyectos/{proyecto_id}/versiones", response_model=List[VersionResponse])
async def listar_versiones(
    proyecto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    await exigir_proyecto(db, quien, proyecto_id)
    r = await db.execute(select(GPVersion).where(
        GPVersion.proyecto_id == proyecto_id
    ).order_by(GPVersion.orden, GPVersion.nombre))
    versiones = list(r.scalars().all())

    # Cuántas la mencionan, en una sola consulta sobre el jsonb. Sin este número,
    # archivar una versión es a ciegas.
    cuentas: Dict[str, int] = {}
    if versiones:
        for clave in ("version_afectada", "version_corrige"):
            r = await db.execute(
                select(GPIncidencia.campos[clave].astext, func.count())
                .where(GPIncidencia.proyecto_id == proyecto_id,
                       GPIncidencia.campos.has_key(clave))
                .group_by(GPIncidencia.campos[clave].astext))
            for valor, cuantas in r.all():
                if valor:
                    cuentas[valor] = cuentas.get(valor, 0) + cuantas

    salida = []
    for v in versiones:
        ficha = VersionResponse.model_validate(v)
        ficha.incidencias = cuentas.get(str(v.id), 0)
        salida.append(ficha)
    return salida


@router.post("/proyectos/{proyecto_id}/versiones", response_model=VersionResponse,
             status_code=201)
async def crear_version(
    proyecto_id: int, data: VersionEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    await exigir_proyecto(db, quien, proyecto_id, escritura=True)
    ya = (await db.execute(select(GPVersion.id).where(
        GPVersion.proyecto_id == proyecto_id,
        func.upper(GPVersion.nombre) == data.nombre.strip().upper()))).first()
    if ya:
        raise HTTPException(409, f"Ese proyecto ya tiene la versión «{data.nombre}».")

    cuantas = (await db.execute(select(func.count()).select_from(GPVersion)
                                .where(GPVersion.proyecto_id == proyecto_id))).scalar() or 0
    version = GPVersion(
        proyecto_id=proyecto_id, nombre=data.nombre.strip(),
        descripcion=data.descripcion, fecha=data.fecha or None,
        liberada=data.liberada, archivada=False, orden=cuantas)
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return VersionResponse.model_validate(version)


@router.put("/versiones/{version_id}", response_model=VersionResponse)
async def editar_version(
    version_id: int, data: VersionEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    version = (await db.execute(select(GPVersion).where(
        GPVersion.id == version_id))).scalar_one_or_none()
    if version is None:
        raise HTTPException(404, "Esa versión no existe.")
    await exigir_proyecto(db, quien, version.proyecto_id, escritura=True)

    version.nombre = data.nombre.strip()
    version.descripcion = data.descripcion
    version.fecha = data.fecha or None
    version.liberada = data.liberada
    await db.commit()
    await db.refresh(version)
    return VersionResponse.model_validate(version)


@router.delete("/versiones/{version_id}", status_code=204)
async def archivar_version(
    version_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Se archiva, no se borra.

    Hay incidencias que la mencionan, y el registro de qué se entregó en cada
    versión es justo lo que se quiere conservar.
    """
    version = (await db.execute(select(GPVersion).where(
        GPVersion.id == version_id))).scalar_one_or_none()
    if version is None:
        raise HTTPException(404, "Esa versión no existe.")
    await exigir_proyecto(db, quien, version.proyecto_id, escritura=True)
    version.archivada = True
    await db.commit()


# ─── Componentes ──────────────────────────────────────────────────────────────

class ComponenteEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: Optional[str] = None
    responsable: Optional[str] = None
    color: Optional[str] = None


class ComponenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    proyecto_id: int
    nombre: str
    descripcion: Optional[str] = None
    responsable: Optional[str] = None
    color: Optional[str] = None
    archivado: bool
    orden: int


@router.get("/proyectos/{proyecto_id}/componentes",
            response_model=List[ComponenteResponse])
async def listar_componentes(
    proyecto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    await exigir_proyecto(db, quien, proyecto_id)
    r = await db.execute(select(GPComponente).where(
        GPComponente.proyecto_id == proyecto_id
    ).order_by(GPComponente.orden, GPComponente.nombre))
    return list(r.scalars().all())


@router.post("/proyectos/{proyecto_id}/componentes",
             response_model=ComponenteResponse, status_code=201)
async def crear_componente(
    proyecto_id: int, data: ComponenteEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    await exigir_proyecto(db, quien, proyecto_id, escritura=True)
    ya = (await db.execute(select(GPComponente.id).where(
        GPComponente.proyecto_id == proyecto_id,
        func.upper(GPComponente.nombre) == data.nombre.strip().upper()))).first()
    if ya:
        raise HTTPException(409, f"Ese proyecto ya tiene «{data.nombre}».")

    cuantos = (await db.execute(select(func.count()).select_from(GPComponente)
                                .where(GPComponente.proyecto_id == proyecto_id))).scalar() or 0
    componente = GPComponente(
        proyecto_id=proyecto_id, nombre=data.nombre.strip(),
        descripcion=data.descripcion, responsable=data.responsable,
        color=data.color, archivado=False, orden=cuantos)
    db.add(componente)
    await db.commit()
    await db.refresh(componente)
    return componente


@router.delete("/componentes/{componente_id}", status_code=204)
async def archivar_componente(
    componente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    componente = (await db.execute(select(GPComponente).where(
        GPComponente.id == componente_id))).scalar_one_or_none()
    if componente is None:
        raise HTTPException(404, "Ese componente no existe.")
    await exigir_proyecto(db, quien, componente.proyecto_id, escritura=True)
    componente.archivado = True
    await db.commit()


# ─── Tipos de vínculo ─────────────────────────────────────────────────────────

class TipoVinculoEntrada(BaseModel):
    clave: str = Field(min_length=2, max_length=30)
    nombre: str = Field(min_length=1, max_length=60)
    inverso: str = Field(min_length=1, max_length=60)


@router.get("/tipos-vinculo")
async def listar_tipos_vinculo(
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Cómo se pueden relacionar dos incidencias, con su nombre en cada sentido."""
    r = await db.execute(select(GPTipoVinculo).where(
        GPTipoVinculo.activo.is_(True)).order_by(GPTipoVinculo.orden))
    return [
        {"clave": t.clave, "nombre": t.nombre, "inverso": t.inverso}
        for t in r.scalars().all()
    ]


@router.post("/tipos-vinculo", status_code=201)
async def crear_tipo_vinculo(
    data: TipoVinculoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    clave = data.clave.strip().upper()
    ya = (await db.execute(select(GPTipoVinculo.id).where(
        GPTipoVinculo.clave == clave))).first()
    if ya:
        raise HTTPException(409, f"Ya hay un tipo de vínculo «{clave}».")

    cuantos = (await db.execute(
        select(func.count()).select_from(GPTipoVinculo))).scalar() or 0
    tipo = GPTipoVinculo(
        clave=clave, nombre=data.nombre.strip(), inverso=data.inverso.strip(),
        orden=cuantos, activo=True)
    db.add(tipo)
    await db.commit()
    await db.refresh(tipo)
    return {"clave": tipo.clave, "nombre": tipo.nombre, "inverso": tipo.inverso}
