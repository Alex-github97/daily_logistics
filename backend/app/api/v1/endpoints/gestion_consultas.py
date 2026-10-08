"""
Búsqueda con el lenguaje de filtros, y los filtros guardados.

Todo lo que llega acá pasa por `gestion_consultas.compilar`, que analiza, valida
y construye. No hay una segunda ruta: si la hubiera, sería por donde entraría lo
que la primera rechaza.

Se guarda el **texto** del filtro, nunca el SQL. El SQL se vuelve a generar en
cada consulta desde el árbol validado, así que un filtro guardado hace mucho no
puede saltarse una comprobación que se agregó después.
"""
import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import gestion_consultas
from app.core.database import get_db_plataforma
from app.core.gestion_permisos import limitar, proyectos_visibles
from app.core.permisos_consola import Miembro, exigir
from app.api.v1.endpoints.gestion_incidencias import MAX_POR_PAGINA, Tarjeta, _tarjetas
from app.infrastructure.models.gestion import GPFiltro, GPIncidencia

router = APIRouter(prefix="/gestion", tags=["Gestión"])

# Tope de ejecución por consulta. Un filtro pesado no puede quedarse con una
# conexión indefinidamente: con cuatro procesos y un pozo de conexiones acotado,
# dos consultas atascadas dejan sin atender a todos los demás.
TIMEOUT_MS = 10_000


class Busqueda(BaseModel):
    expresion: str = ""
    limite: int = Field(50, ge=1, le=MAX_POR_PAGINA)
    cursor: Optional[str] = None
    con_total: bool = False


class Pagina(BaseModel):
    resultados: List[Tarjeta]
    siguiente: Optional[str] = None
    total: Optional[int] = None
    # Se devuelve lo que se entendió: sirve para que el constructor visual pinte
    # el filtro y para depurar cuando alguien dice «no trae lo que debería».
    orden: Optional[dict] = None


class FiltroEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    descripcion: Optional[str] = None
    expresion: str = ""
    columnas: List[str] = []
    orden_por: Optional[str] = None
    orden_asc: bool = False
    compartido: bool = False


class FiltroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    descripcion: Optional[str] = None
    expresion: str
    columnas: List[str] = []
    orden_por: Optional[str] = None
    orden_asc: bool = False
    autor: str
    compartido: bool = False


# ─── Cursor sobre un orden cualquiera ─────────────────────────────────────────

def _valor_orden(inc: GPIncidencia, campo) -> Any:
    """El valor por el que va ordenada esta fila."""
    if campo is None:
        return inc.actualizado
    if campo.referencia is not None:
        return getattr(inc, campo.referencia.columna.key, None)
    if campo.personalizado:
        return (inc.campos or {}).get(campo.personalizado)
    return getattr(inc, campo.columna.key, None)


def _empacar(valor: Any, ident: int) -> str:
    if isinstance(valor, datetime):
        crudo = valor.isoformat()
    elif valor is None:
        crudo = None
    else:
        crudo = str(valor)
    return base64.urlsafe_b64encode(
        json.dumps({"v": crudo, "id": ident}).encode()).decode()


def _desempacar(cursor: str, campo):
    try:
        datos = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        ident = int(datos["id"])
        crudo = datos.get("v")
    except Exception:
        raise HTTPException(400, "El cursor de paginación no es válido.")

    if crudo is None:
        return None, ident

    tipo = campo.tipo if campo is not None else "FECHA_HORA"
    try:
        if tipo in ("FECHA", "FECHA_HORA"):
            momento = datetime.fromisoformat(crudo)
            return (momento if momento.tzinfo
                    else momento.replace(tzinfo=timezone.utc)), ident
        if tipo in ("NUMERO", "DECIMAL", "REFERENCIA"):
            return (float(crudo) if "." in crudo else int(crudo)), ident
    except ValueError:
        raise HTTPException(400, "El cursor de paginación no es válido.")
    return crudo, ident


def _despues_de(expresion, valor, ident: int, ascendente: bool):
    """La condición «lo que va después de aquí», para el orden dado.

    Los nulos van siempre al final, así que la frontera tiene dos mitades: si el
    cursor apunta a una fila con valor, lo siguiente son las de valor posterior,
    las nulas, y las de igual valor con id menor; si apunta a una nula, ya solo
    quedan nulas. Sin este cuidado, una columna con huecos —`vence`, por
    ejemplo— hace que el recorrido pierda filas.
    """
    if valor is None:
        return (expresion.is_(None) &
                (GPIncidencia.id > ident if ascendente else GPIncidencia.id < ident))

    mas_alla = expresion > valor if ascendente else expresion < valor
    return or_(
        mas_alla,
        expresion.is_(None),
        (expresion == valor) & (
            GPIncidencia.id > ident if ascendente else GPIncidencia.id < ident),
    )


# ─── Búsqueda ─────────────────────────────────────────────────────────────────

@router.post("/incidencias/buscar", response_model=Pagina)
async def buscar(
    data: Busqueda,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Ejecuta un filtro escrito en el lenguaje de consultas."""
    campos = await gestion_consultas.registro(db)
    plan = gestion_consultas.compilar(data.expresion, campos, quien.usuario)
    condicion = plan.condicion
    campo_orden, expresion_orden, ascendente = (
        plan.campo_orden, plan.expresion_orden, plan.ascendente)

    consulta = select(GPIncidencia)
    # El permiso entra en el árbol, no se aplica al resultado: filtrar después
    # de consultar significa que la base ya leyó lo que no debía verse, y
    # cualquier conteo o agregado saldría contando de más.
    consulta = limitar(consulta, await proyectos_visibles(db, quien),
                       GPIncidencia.proyecto_id)
    if condicion is not None:
        consulta = consulta.where(condicion)

    # Tope de ejecución para esta transacción y no para la sesión: LOCAL se
    # deshace solo al terminar, así que no se queda pegado a la conexión, que se
    # reutiliza para todo lo demás.
    await db.execute(text(f"SET LOCAL statement_timeout = {TIMEOUT_MS}"))

    total = None
    if data.con_total:
        total = (await db.execute(
            select(func.count()).select_from(consulta.subquery()))).scalar() or 0

    if data.cursor:
        valor, ident = _desempacar(data.cursor, campo_orden)
        consulta = consulta.where(
            _despues_de(expresion_orden, valor, ident, ascendente))

    # El id desempata siempre. Sin un orden total estricto, dos filas con el
    # mismo valor hacen que el cursor repita una y se salte la otra.
    if ascendente:
        consulta = consulta.order_by(
            expresion_orden.asc().nullslast(), GPIncidencia.id.asc())
    else:
        consulta = consulta.order_by(
            expresion_orden.desc().nullslast(), GPIncidencia.id.desc())

    filas = list((await db.execute(consulta.limit(data.limite + 1))).scalars().all())
    hay_mas = len(filas) > data.limite
    filas = filas[:data.limite]

    return Pagina(
        resultados=await _tarjetas(db, filas),
        siguiente=(_empacar(_valor_orden(filas[-1], campo_orden), filas[-1].id)
                   if hay_mas and filas else None),
        total=total,
        orden=({"campo": plan.orden.campo, "ascendente": plan.orden.ascendente}
               if plan.orden else {"campo": "actualizado", "ascendente": False}),
    )


@router.post("/incidencias/validar")
async def validar_expresion(
    data: Busqueda,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Comprueba un filtro sin ejecutarlo.

    Es lo que permite que el editor marque el error mientras se escribe, en vez
    de esperar a que alguien pulse buscar y reciba una lista vacía sin
    explicación.
    """
    campos = await gestion_consultas.registro(db)
    try:
        gestion_consultas.compilar(data.expresion, campos, quien.usuario)
    except gestion_consultas.ErrorDeConsulta as e:
        return {"valido": False, "mensaje": e.mensaje, "posicion": e.posicion}
    return {"valido": True, "mensaje": None, "posicion": None}


@router.get("/consultas/campos")
async def campos_consultables(
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Con qué se puede armar un filtro: campos, operadores y funciones."""
    campos = await gestion_consultas.registro(db)
    return {
        "campos": gestion_consultas.catalogo(campos),
        "funciones": gestion_consultas.FUNCIONES,
        "topes": {
            "condiciones": gestion_consultas.MAX_CONDICIONES,
            "profundidad": gestion_consultas.MAX_PROFUNDIDAD,
            "elementos_en": gestion_consultas.MAX_EN,
            "largo": gestion_consultas.MAX_LARGO,
        },
    }


# ─── Filtros guardados ────────────────────────────────────────────────────────

@router.get("/filtros", response_model=List[FiltroResponse])
async def listar_filtros(
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    r = await db.execute(select(GPFiltro).where(or_(
        GPFiltro.autor == quien.usuario, GPFiltro.compartido.is_(True)
    )).order_by(GPFiltro.nombre))
    return list(r.scalars().all())


@router.post("/filtros", response_model=FiltroResponse, status_code=201)
async def guardar_filtro(
    data: FiltroEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Guarda un filtro, comprobándolo antes.

    Se valida al guardar y no solo al usar: un filtro roto guardado y compartido
    falla después en la cara de otra persona, que no sabe qué escribió quien lo
    creó ni puede arreglarlo.
    """
    campos = await gestion_consultas.registro(db)
    gestion_consultas.compilar(data.expresion, campos, quien.usuario)

    filtro = GPFiltro(
        nombre=data.nombre.strip(), descripcion=data.descripcion,
        expresion=data.expresion, columnas=data.columnas,
        orden_por=data.orden_por, orden_asc=data.orden_asc,
        autor=quien.usuario, compartido=data.compartido)
    db.add(filtro)
    await db.commit()
    await db.refresh(filtro)
    return filtro


@router.put("/filtros/{filtro_id}", response_model=FiltroResponse)
async def editar_filtro(
    filtro_id: int, data: FiltroEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    filtro = (await db.execute(select(GPFiltro).where(
        GPFiltro.id == filtro_id))).scalar_one_or_none()
    if filtro is None:
        raise HTTPException(404, "Ese filtro no existe.")
    if filtro.autor != quien.usuario:
        raise HTTPException(
            403, "Solo quien creó un filtro puede cambiarlo. Duplíquelo si "
                 "quiere una versión propia.")

    campos = await gestion_consultas.registro(db)
    gestion_consultas.compilar(data.expresion, campos, quien.usuario)

    for campo, valor in data.model_dump().items():
        setattr(filtro, campo, valor)
    await db.commit()
    await db.refresh(filtro)
    return filtro


@router.delete("/filtros/{filtro_id}", status_code=204)
async def borrar_filtro(
    filtro_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    filtro = (await db.execute(select(GPFiltro).where(
        GPFiltro.id == filtro_id))).scalar_one_or_none()
    if filtro is None:
        raise HTTPException(404, "Ese filtro no existe.")
    if filtro.autor != quien.usuario:
        raise HTTPException(403, "Solo quien creó un filtro puede borrarlo.")
    await db.delete(filtro)
    await db.commit()
