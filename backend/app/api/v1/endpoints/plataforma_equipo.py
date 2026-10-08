"""
El equipo de la consola: quién entra y con qué rol.

Es distinto de los usuarios de una empresa. `usuarios` dice quién puede entrar a
la plataforma de la empresa operadora; esto dice quién además administra la
plataforma entera y hasta dónde llega su alcance.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_plataforma
from app.core.permisos_consola import Miembro, exigir, miembro_actual
from app.core.roles_consola import PERMISOS, ROLES, POR_CLAVE
from app.infrastructure.models.plataforma import PlataformaCliente, PlataformaMiembro
from app.api.v1.endpoints.plataforma import _anotar, _sesion_de

router = APIRouter(prefix="/plataforma", tags=["Consola del operador"])


class RolDisponible(BaseModel):
    clave: str
    nombre: str
    descripcion: str
    permisos: List[str]


class PermisoDisponible(BaseModel):
    clave: str
    descripcion: str


class MiembroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usuario: str
    nombre: Optional[str] = None
    email: Optional[str] = None
    rol: str
    activo: bool
    notas: Optional[str] = None


class MiembroNuevo(BaseModel):
    usuario: str
    rol: str = "CONSULTA"
    notas: Optional[str] = None


class MiembroCambios(BaseModel):
    rol: Optional[str] = None
    activo: Optional[bool] = None
    notas: Optional[str] = None


class QuienSoy(BaseModel):
    usuario: str
    rol: str
    permisos: List[str]
    # True mientras el equipo no se haya formalizado: en ese estado todo
    # administrador de la empresa operadora entra como propietario.
    implicito: bool


@router.get("/equipo/quien-soy", response_model=QuienSoy)
async def quien_soy(quien: Miembro = Depends(miembro_actual)):
    """Lo que puede hacer quien está conectado.

    La consola la usa para no mostrar secciones que el servidor va a rechazar:
    ofrecer un botón que siempre falla es peor que no mostrarlo.
    """
    return QuienSoy(usuario=quien.usuario, rol=quien.rol,
                    permisos=list(quien.permisos), implicito=quien.implicito)


@router.get("/equipo/roles", response_model=List[RolDisponible])
async def roles(_: Miembro = Depends(miembro_actual)):
    return [
        RolDisponible(clave=r.clave, nombre=r.nombre, descripcion=r.descripcion,
                      permisos=list(r.permisos))
        for r in ROLES
    ]


@router.get("/equipo/permisos", response_model=List[PermisoDisponible])
async def permisos(_: Miembro = Depends(miembro_actual)):
    return [PermisoDisponible(clave=p.clave, descripcion=p.descripcion) for p in PERMISOS]


@router.get("/equipo", response_model=List[MiembroResponse])
async def listar(
    db: AsyncSession = Depends(get_db_plataforma),
    _: Miembro = Depends(exigir("equipo.gestionar")),
):
    r = await db.execute(select(PlataformaMiembro).order_by(PlataformaMiembro.usuario))
    return [MiembroResponse.model_validate(m) for m in r.scalars().all()]


class CandidatoResponse(BaseModel):
    username: str
    nombre: str
    email: Optional[str] = None
    ya_es_miembro: bool


@router.get("/equipo/candidatos", response_model=List[CandidatoResponse])
async def candidatos(
    db: AsyncSession = Depends(get_db_plataforma),
    _: Miembro = Depends(exigir("equipo.gestionar")),
):
    """Los usuarios de la empresa operadora, para elegir a quién dar acceso.

    Se listan de su esquema y no se crean acá: el equipo se arma sobre gente que
    ya tiene con qué entrar, no inventando credenciales nuevas.
    """
    operador = (await db.execute(select(PlataformaCliente).where(
        PlataformaCliente.es_operador == True))).scalar_one_or_none()  # noqa: E712
    if not operador:
        raise HTTPException(404, "No hay ninguna empresa marcada como operadora")

    miembros = {m.usuario for m in (await db.execute(
        select(PlataformaMiembro))).scalars().all()}

    async with _sesion_de(operador.esquema) as s:
        filas = (await s.execute(text(
            "SELECT username, nombre, apellido, email FROM usuarios "
            "WHERE activo ORDER BY username"))).all()

    return [
        CandidatoResponse(
            username=u, nombre=f"{n or ''} {a or ''}".strip() or u,
            email=e, ya_es_miembro=u in miembros)
        for u, n, a, e in filas
    ]


@router.post("/equipo", response_model=MiembroResponse, status_code=201)
async def agregar(
    data: MiembroNuevo, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("equipo.gestionar")),
):
    usuario = (data.usuario or "").strip().lower()
    if not usuario:
        raise HTTPException(400, "Indique el usuario")
    rol = (data.rol or "").upper()
    if rol not in POR_CLAVE:
        raise HTTPException(
            400, f"Rol inválido. Use uno de: {', '.join(POR_CLAVE)}.")

    ya = (await db.execute(select(PlataformaMiembro).where(
        PlataformaMiembro.usuario == usuario))).scalar_one_or_none()
    if ya:
        raise HTTPException(409, f"«{usuario}» ya hace parte del equipo")

    operador = (await db.execute(select(PlataformaCliente).where(
        PlataformaCliente.es_operador == True))).scalar_one_or_none()  # noqa: E712
    if not operador:
        raise HTTPException(404, "No hay ninguna empresa marcada como operadora")

    # Tiene que existir como usuario de la empresa operadora: si no, se estaría
    # dando acceso a la consola a alguien que ni siquiera puede iniciar sesión.
    async with _sesion_de(operador.esquema) as s:
        fila = (await s.execute(
            text("SELECT nombre, apellido, email FROM usuarios WHERE username = :u"),
            {"u": usuario})).first()
    if not fila:
        raise HTTPException(
            404,
            f"No existe el usuario «{usuario}» en {operador.nombre}. Créelo primero "
            "en Empresas → Usuarios; el equipo se arma sobre gente que ya puede entrar.",
        )

    miembro = PlataformaMiembro(
        usuario=usuario,
        nombre=f"{fila[0] or ''} {fila[1] or ''}".strip() or usuario,
        email=fila[2], rol=rol, activo=True, notas=data.notas)
    db.add(miembro)
    await _anotar(db, request, "equipo.alta", operador.codigo, f"«{usuario}» como {rol}")
    await db.commit(); await db.refresh(miembro)
    return MiembroResponse.model_validate(miembro)


async def _quedaria_sin_propietario(
    db: AsyncSession, miembro_id: int, rol_nuevo: Optional[str], activo_nuevo: Optional[bool],
) -> bool:
    """Si el cambio dejaría la consola sin ningún propietario activo.

    Sin propietario nadie puede volver a administrar el equipo, y recuperarlo
    exigiría entrar a la base a mano.
    """
    r = await db.execute(select(PlataformaMiembro).where(
        PlataformaMiembro.rol == "PROPIETARIO", PlataformaMiembro.activo == True))  # noqa: E712
    propietarios = list(r.scalars().all())
    otros = [p for p in propietarios if p.id != miembro_id]
    if otros:
        return False
    # El que se está tocando es el único propietario activo.
    sigue_siendo = (rol_nuevo or "PROPIETARIO") == "PROPIETARIO"
    sigue_activo = activo_nuevo if activo_nuevo is not None else True
    return not (sigue_siendo and sigue_activo)


@router.put("/equipo/{miembro_id}", response_model=MiembroResponse)
async def editar(
    miembro_id: int, data: MiembroCambios, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("equipo.gestionar")),
):
    miembro = await db.get(PlataformaMiembro, miembro_id)
    if not miembro:
        raise HTTPException(404, "Ese miembro no existe")

    cambios = data.model_dump(exclude_unset=True)
    if cambios.get("rol"):
        cambios["rol"] = cambios["rol"].upper()
        if cambios["rol"] not in POR_CLAVE:
            raise HTTPException(400, f"Rol inválido. Use uno de: {', '.join(POR_CLAVE)}.")

    if miembro.rol == "PROPIETARIO" and await _quedaria_sin_propietario(
            db, miembro_id, cambios.get("rol"), cambios.get("activo")):
        raise HTTPException(
            409,
            "Es el único propietario activo. Si se le quita el rol o se desactiva, "
            "nadie podría volver a administrar el equipo. Nombre otro propietario primero.",
        )

    # Quitarse a uno mismo la gestión del equipo es la otra forma de quedarse
    # sin poder volver a entrar a esta sección.
    if miembro.usuario == quien.usuario and cambios.get("rol"):
        nuevos = POR_CLAVE[cambios["rol"]].permisos
        if "equipo.gestionar" not in nuevos:
            raise HTTPException(
                409,
                "Con ese rol usted perdería el acceso a esta sección. Pídale a otro "
                "propietario que haga el cambio.",
            )

    for campo, valor in cambios.items():
        setattr(miembro, campo, valor)
    operador = (await db.execute(select(PlataformaCliente).where(
        PlataformaCliente.es_operador == True))).scalar_one_or_none()  # noqa: E712
    await _anotar(db, request, "equipo.edicion",
                  operador.codigo if operador else None,
                  f"«{miembro.usuario}»: {', '.join(cambios)}")
    await db.commit(); await db.refresh(miembro)
    return MiembroResponse.model_validate(miembro)


@router.delete("/equipo/{miembro_id}", status_code=204)
async def quitar(
    miembro_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("equipo.gestionar")),
):
    """Le quita el acceso a la consola. No borra su usuario de la plataforma."""
    miembro = await db.get(PlataformaMiembro, miembro_id)
    if not miembro:
        raise HTTPException(404, "Ese miembro no existe")
    if miembro.rol == "PROPIETARIO" and await _quedaria_sin_propietario(
            db, miembro_id, None, False):
        raise HTTPException(
            409,
            "Es el único propietario activo: sacarlo dejaría la consola sin quien "
            "administre el equipo. Nombre otro propietario primero.",
        )
    if miembro.usuario == quien.usuario:
        raise HTTPException(
            409, "No puede sacarse a usted mismo. Pídaselo a otro propietario.")

    usuario = miembro.usuario
    await db.delete(miembro)
    operador = (await db.execute(select(PlataformaCliente).where(
        PlataformaCliente.es_operador == True))).scalar_one_or_none()  # noqa: E712
    await _anotar(db, request, "equipo.baja",
                  operador.codigo if operador else None, f"«{usuario}»")
    await db.commit()
