"""
Pizarras: tableros de indicadores armados por quien los usa.

Cada recuadro se apoya en el MISMO lenguaje de filtros que la lista, y por una
razón concreta: cualquier número de una pizarra se puede abrir como lista y
revisar fila por fila. Un panel cuya cifra no se puede desglosar es una cifra en
la que nadie confía, y termina ignorándose.

Los recuadros se calculan en el servidor y no en el navegador. Contar en el
navegador exigiría bajarse todas las incidencias para sumar seis números.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.gestion_incidencias import _tarjetas
from app.core import gestion_consultas
from app.core.database import get_db_plataforma
from app.core.gestion_permisos import limitar, proyectos_visibles
from app.core.permisos_consola import Miembro, exigir
from app.infrastructure.models.gestion import (
    GPEstado, GPIncidencia, GPPizarra, GPPrioridad, GPProyecto,
    GPTipoIncidencia, GPWidget,
)

router = APIRouter(prefix="/gestion", tags=["Gestión"])

# Cómo se puede resumir. Cada uno resuelve a una columna o a una referencia; no
# se acepta un campo cualquiera porque agrupar por texto libre produce mil
# categorías de una fila cada una, que no resume nada.
AGRUPACIONES = {
    "estado": (GPEstado, GPIncidencia.estado_id, GPEstado.nombre, GPEstado.orden),
    "categoria": (GPEstado, GPIncidencia.estado_id, GPEstado.categoria, GPEstado.orden),
    "tipo": (GPTipoIncidencia, GPIncidencia.tipo_id, GPTipoIncidencia.nombre,
             GPTipoIncidencia.orden),
    "prioridad": (GPPrioridad, GPIncidencia.prioridad_id, GPPrioridad.nombre,
                  GPPrioridad.orden),
    "proyecto": (GPProyecto, GPIncidencia.proyecto_id, GPProyecto.nombre,
                 GPProyecto.nombre),
}

TIPOS_WIDGET = ("CONTADOR", "LISTA", "AGRUPADO", "CARGA")


class WidgetEntrada(BaseModel):
    tipo: str
    titulo: str = Field(min_length=1, max_length=160)
    expresion: str = ""
    agrupar_por: Optional[str] = None
    config: Dict[str, Any] = {}
    x: int = 0
    y: int = 0
    ancho: int = 4
    alto: int = 1


class WidgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pizarra_id: int
    tipo: str
    titulo: str
    expresion: str
    agrupar_por: Optional[str] = None
    config: Dict[str, Any] = {}
    x: int
    y: int
    ancho: int
    alto: int


class PizarraEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    descripcion: Optional[str] = None
    proyecto_id: Optional[int] = None
    compartida: bool = True


class PizarraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    descripcion: Optional[str] = None
    proyecto_id: Optional[int] = None
    autor: str
    compartida: bool
    widgets: List[WidgetResponse] = []


# ─── Pizarras ─────────────────────────────────────────────────────────────────

@router.get("/pizarras", response_model=List[PizarraResponse])
async def listar(
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    r = await db.execute(select(GPPizarra).where(or_(
        GPPizarra.autor == quien.usuario, GPPizarra.compartida.is_(True)
    )).order_by(GPPizarra.nombre))
    pizarras = list(r.scalars().all())
    if not pizarras:
        return []

    r = await db.execute(select(GPWidget).where(
        GPWidget.pizarra_id.in_([p.id for p in pizarras])
    ).order_by(GPWidget.y, GPWidget.x))
    por_pizarra: Dict[int, List[GPWidget]] = {}
    for w in r.scalars().all():
        por_pizarra.setdefault(w.pizarra_id, []).append(w)

    salida = []
    for p in pizarras:
        ficha = PizarraResponse.model_validate(p)
        ficha.widgets = [WidgetResponse.model_validate(w)
                         for w in por_pizarra.get(p.id, [])]
        salida.append(ficha)
    return salida


@router.post("/pizarras", response_model=PizarraResponse, status_code=201)
async def crear(
    data: PizarraEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    pizarra = GPPizarra(
        nombre=data.nombre.strip(), descripcion=data.descripcion,
        proyecto_id=data.proyecto_id, autor=quien.usuario,
        compartida=data.compartida)
    db.add(pizarra)
    await db.commit()
    await db.refresh(pizarra)
    return PizarraResponse.model_validate(pizarra)


@router.delete("/pizarras/{pizarra_id}", status_code=204)
async def borrar(
    pizarra_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    pizarra = await _mia(db, quien, pizarra_id)
    for w in (await db.execute(select(GPWidget).where(
            GPWidget.pizarra_id == pizarra_id))).scalars().all():
        await db.delete(w)
    await db.delete(pizarra)
    await db.commit()


async def _mia(db: AsyncSession, quien: Miembro, pizarra_id: int) -> GPPizarra:
    pizarra = (await db.execute(select(GPPizarra).where(
        GPPizarra.id == pizarra_id))).scalar_one_or_none()
    if pizarra is None:
        raise HTTPException(404, "Esa pizarra no existe.")
    if pizarra.autor != quien.usuario:
        raise HTTPException(
            403, "Solo quien creó una pizarra puede cambiarla. Duplíquela si "
                 "quiere una versión propia.")
    return pizarra


# ─── Recuadros ────────────────────────────────────────────────────────────────

@router.post("/pizarras/{pizarra_id}/widgets", response_model=WidgetResponse,
             status_code=201)
async def agregar_widget(
    pizarra_id: int, data: WidgetEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    await _mia(db, quien, pizarra_id)

    if data.tipo not in TIPOS_WIDGET:
        raise HTTPException(422, f"Tipo no válido. Son: {', '.join(TIPOS_WIDGET)}.")
    if data.tipo == "AGRUPADO" and data.agrupar_por not in AGRUPACIONES:
        raise HTTPException(
            422, f"Para agrupar hay que escoger uno de: {', '.join(AGRUPACIONES)}.")

    # El filtro se valida al guardarlo, no solo al pintarlo: un recuadro roto en
    # una pizarra compartida falla después en la cara de otra persona, que no
    # sabe qué escribió quien la armó ni puede arreglarlo.
    campos = await gestion_consultas.registro(db)
    gestion_consultas.compilar(data.expresion, campos, quien.usuario)

    widget = GPWidget(
        pizarra_id=pizarra_id, tipo=data.tipo, titulo=data.titulo.strip(),
        expresion=data.expresion, agrupar_por=data.agrupar_por,
        config=data.config, x=data.x, y=data.y,
        ancho=max(2, min(12, data.ancho)), alto=max(1, min(4, data.alto)))
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return WidgetResponse.model_validate(widget)


@router.delete("/widgets/{widget_id}", status_code=204)
async def quitar_widget(
    widget_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    widget = (await db.execute(select(GPWidget).where(
        GPWidget.id == widget_id))).scalar_one_or_none()
    if widget is None:
        raise HTTPException(404, "Ese recuadro no existe.")
    await _mia(db, quien, widget.pizarra_id)
    await db.delete(widget)
    await db.commit()


class Posicion(BaseModel):
    id: int
    x: int
    y: int
    ancho: int
    alto: int


@router.put("/pizarras/{pizarra_id}/disposicion")
async def guardar_disposicion(
    pizarra_id: int, posiciones: List[Posicion],
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    await _mia(db, quien, pizarra_id)
    widgets = {
        w.id: w for w in (await db.execute(select(GPWidget).where(
            GPWidget.pizarra_id == pizarra_id))).scalars().all()
    }
    for p in posiciones:
        w = widgets.get(p.id)
        if w is None:
            continue
        w.x, w.y = p.x, p.y
        w.ancho = max(2, min(12, p.ancho))
        w.alto = max(1, min(4, p.alto))
    await db.commit()
    return {"guardados": len(posiciones)}


# ─── Cálculo ──────────────────────────────────────────────────────────────────

@router.get("/widgets/{widget_id}/datos")
async def datos_widget(
    widget_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Lo que muestra un recuadro, calculado en el servidor.

    El filtro del recuadro se combina con los proyectos que puede ver quien mira:
    la misma pizarra le muestra a cada quien lo que le corresponde, sin tener que
    armar una copia por persona.
    """
    widget = (await db.execute(select(GPWidget).where(
        GPWidget.id == widget_id))).scalar_one_or_none()
    if widget is None:
        raise HTTPException(404, "Ese recuadro no existe.")

    pizarra = (await db.execute(select(GPPizarra).where(
        GPPizarra.id == widget.pizarra_id))).scalar_one_or_none()
    if pizarra is None:
        raise HTTPException(404, "Ese recuadro no tiene pizarra.")
    if pizarra.autor != quien.usuario and not pizarra.compartida:
        raise HTTPException(404, "Ese recuadro no existe.")

    campos = await gestion_consultas.registro(db)
    plan = gestion_consultas.compilar(widget.expresion, campos, quien.usuario)

    base = select(GPIncidencia)
    base = limitar(base, await proyectos_visibles(db, quien), GPIncidencia.proyecto_id)
    if pizarra.proyecto_id is not None:
        base = base.where(GPIncidencia.proyecto_id == pizarra.proyecto_id)
    if plan.condicion is not None:
        base = base.where(plan.condicion)

    await db.execute(text("SET LOCAL statement_timeout = 10000"))

    if widget.tipo == "CONTADOR":
        sub = base.subquery()
        fila = (await db.execute(
            select(func.count(), func.coalesce(func.sum(sub.c.puntos), 0))
            .select_from(sub))).first()
        return {"tipo": "CONTADOR", "valor": fila[0] or 0, "puntos": int(fila[1] or 0)}

    if widget.tipo == "LISTA":
        cuantas = int(widget.config.get("filas", 8))
        filas = list((await db.execute(
            base.order_by(GPIncidencia.actualizado.desc(), GPIncidencia.id.desc())
                .limit(max(1, min(25, cuantas))))).scalars().all())
        return {"tipo": "LISTA", "filas": await _tarjetas(db, filas)}

    if widget.tipo == "AGRUPADO":
        modelo, columna, etiqueta, orden = AGRUPACIONES[widget.agrupar_por or "estado"]
        sub = base.subquery()
        consulta = (
            select(etiqueta, func.count(),
                   func.coalesce(func.sum(sub.c.puntos), 0))
            .select_from(sub)
            .join(modelo, modelo.id == sub.c[columna.key])
            .group_by(etiqueta, orden)
            .order_by(orden)
        )
        r = await db.execute(consulta)
        return {
            "tipo": "AGRUPADO",
            "agrupar_por": widget.agrupar_por,
            "grupos": [
                {"etiqueta": e or "—", "cuantas": c, "puntos": int(p or 0)}
                for e, c, p in r.all()
            ],
        }

    if widget.tipo == "CARGA":
        sub = base.subquery()
        r = await db.execute(
            select(sub.c.asignado, func.count(),
                   func.coalesce(func.sum(sub.c.puntos), 0))
            .select_from(sub).group_by(sub.c.asignado))
        return {
            "tipo": "CARGA",
            "personas": sorted(
                [{"usuario": u or "sin asignar", "cuantas": c, "puntos": int(p or 0)}
                 for u, c, p in r.all()],
                key=lambda x: -x["cuantas"]),
        }

    raise HTTPException(500, f"El recuadro es de un tipo que el servidor no dibuja "
                             f"({widget.tipo}).")


@router.get("/pizarras/catalogo")
async def catalogo(
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Qué recuadros se pueden agregar y cómo se pueden agrupar."""
    return {
        "tipos": [
            {"clave": "CONTADOR", "nombre": "Un número",
             "descripcion": "Cuántas cumplen el filtro"},
            {"clave": "AGRUPADO", "nombre": "Barras por categoría",
             "descripcion": "Reparto por estado, tipo, prioridad o proyecto"},
            {"clave": "LISTA", "nombre": "Lista corta",
             "descripcion": "Las últimas que cumplen el filtro"},
            {"clave": "CARGA", "nombre": "Carga por persona",
             "descripcion": "Cuánto tiene cada quien encima"},
        ],
        "agrupaciones": list(AGRUPACIONES),
    }
