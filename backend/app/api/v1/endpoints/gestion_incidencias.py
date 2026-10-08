"""
Incidencias: listar, ver, crear, editar, mover, comentar y adjuntar.

Dos cosas que gobiernan este archivo:

**Se pagina por cursor, no por página.** `OFFSET 500000` recorre medio millón de
filas para descartarlas, y con una lista que cambia mientras se recorre, la
página 3 se salta o repite filas. El cursor apunta a `(actualizado, id)` —el
orden total estricto del índice— y sigue siendo correcto aunque entren
incidencias nuevas mientras alguien baja.

**Todo cambio queda en el historial.** No como cortesía: de ahí salen las
métricas, y un tiempo de ciclo calculado sobre el estado de hoy mostraría el
pasado como si siempre hubiera sido así.
"""
import base64
import hashlib
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import (
    gestion_campos, gestion_formulario, gestion_incidencias, gestion_workflow,
)
from app.core.config import settings
from app.core.database import get_db_plataforma
from app.core.gestion_permisos import exigir_proyecto, limitar, proyectos_visibles
from app.core.permisos_consola import Miembro, exigir
from app.infrastructure.models.gestion import (
    GPAdjunto, GPComentario, GPEstado, GPHistorial, GPIncidencia, GPPrioridad,
    GPTiempoTrabajo,
    GPProyecto, GPTipoIncidencia, GPVinculo, TIPOS_VINCULO,
)
from app.infrastructure.models.soporte import SoporteTicket

router = APIRouter(prefix="/gestion", tags=["Gestión"])

ALMACEN = Path(settings.UPLOAD_DIR) / "gestion"
MAX_BYTES = 15 * 1024 * 1024
EXTENSIONES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".txt", ".log", ".csv",
    ".xlsx", ".xls", ".docx", ".doc", ".zip", ".json", ".sql", ".md",
}

# Tope duro del tamaño de página. No es una preferencia: sin él, `limite=100000`
# desde el navegador arma una respuesta que tumba el proceso.
MAX_POR_PAGINA = 100


# ─── Cursor ───────────────────────────────────────────────────────────────────

def _cursor_de(inc: GPIncidencia) -> str:
    """Codifica dónde quedó el recorrido: la marca de tiempo y el id."""
    marca = inc.actualizado.isoformat() if inc.actualizado else ""
    return base64.urlsafe_b64encode(f"{marca}|{inc.id}".encode()).decode()


def _leer_cursor(cursor: str):
    try:
        marca, ident = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(marca), int(ident)
    except Exception:
        # Un cursor ilegible es casi siempre un enlace viejo. Se rechaza en vez
        # de empezar desde el principio en silencio, que se lee como que la
        # paginación se rompió.
        raise HTTPException(400, "El cursor de paginación no es válido.")


# ─── Formas ───────────────────────────────────────────────────────────────────

class Tarjeta(BaseModel):
    id: int
    clave: str
    proyecto_id: int
    resumen: str
    tipo: Optional[str] = None
    tipo_id: Optional[int] = None
    icono: Optional[str] = None
    estado: Optional[str] = None
    estado_id: Optional[int] = None
    categoria: Optional[str] = None
    color_estado: Optional[str] = None
    prioridad: Optional[str] = None
    prioridad_id: Optional[int] = None
    color_prioridad: Optional[str] = None
    asignado: Optional[str] = None
    reporta: Optional[str] = None
    puntos: Optional[int] = None
    padre_id: Optional[int] = None
    sprint_id: Optional[int] = None
    etiquetas: List[str] = []
    campos: Dict[str, Any] = {}
    vence: Optional[datetime] = None
    actualizado: Optional[datetime] = None
    ticket_id: Optional[int] = None


class Pagina(BaseModel):
    resultados: List[Tarjeta]
    siguiente: Optional[str] = None
    total: Optional[int] = None


class ComentarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    autor: str
    cuerpo: str
    interno: bool
    editado: bool
    created_at: Optional[datetime] = None


class AdjuntoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo_mime: Optional[str] = None
    tamano: Optional[int] = None
    subido_por: Optional[str] = None
    creado: Optional[datetime] = None


class HistorialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    campo: str
    anterior: Optional[str] = None
    nuevo: Optional[str] = None
    autor: Optional[str] = None
    creado: Optional[datetime] = None


class IncidenciaEntrada(BaseModel):
    """Lo que llega al crear.

    `proyecto_id` y `tipo_id` van aparte de `campos` porque no son campos del
    formulario: son la coordenada que decide QUE formulario aplica. Todo lo demas
    —titulo, responsable, prioridad, sprint, y lo que el administrador haya
    definido— llega en `campos`, y el motor decide que es valido, si va a una
    columna o al jsonb, y que es obligatorio.

    Enumerar los campos aca era lo que obligaba a tocar tres archivos cada vez
    que se agregaba uno.
    """

    model_config = ConfigDict(extra="forbid")

    proyecto_id: int
    tipo_id: int
    campos: Dict[str, Any] = {}


class IncidenciaCambio(BaseModel):
    """Lo que llega al editar.

    `extra="forbid"` no es celo: sin él, Pydantic DESCARTA en silencio lo que no
    reconoce. Una pantalla que mandara `{"asignado": "ana"}` en la raíz en vez de
    dentro de `campos` recibía un 200 y no guardaba nada —y eso fue exactamente
    lo que pasó—. Es la peor forma de fallar: la interfaz dice que guardó.

    El estado NO está: se mueve por una transición, que es la que aplica las
    reglas del flujo. Si el PUT pudiera cambiarlo, el motor de workflow sería una
    sugerencia.
    """

    model_config = ConfigDict(extra="forbid")

    # Cambiar el tipo puede cambiar qué campos aplican, así que va aparte: no es
    # un campo del formulario, es la coordenada que decide cuál aplica.
    tipo_id: Optional[int] = None
    campos: Dict[str, Any] = {}


class ComentarioEntrada(BaseModel):
    cuerpo: str = Field(min_length=1)
    interno: bool = False
    menciones: List[str] = []


class VinculoEntrada(BaseModel):
    destino_id: int
    tipo: str


class TransicionEntrada(BaseModel):
    transicion_id: int
    comentario: Optional[str] = None


# ─── Ayudas ───────────────────────────────────────────────────────────────────

async def _tarjetas(db: AsyncSession, incidencias: List[GPIncidencia]) -> List[Tarjeta]:
    """Arma las tarjetas resolviendo los nombres en tres consultas, no en 3×N.

    Traer proyecto, tipo, estado y prioridad por cada fila es el patrón que hace
    que una lista de cincuenta tarjetas dispare doscientas consultas.
    """
    if not incidencias:
        return []

    proyectos = {
        p.id: p for p in (await db.execute(select(GPProyecto).where(
            GPProyecto.id.in_({i.proyecto_id for i in incidencias})))).scalars().all()
    }
    tipos = {
        t.id: t for t in (await db.execute(select(GPTipoIncidencia).where(
            GPTipoIncidencia.id.in_({i.tipo_id for i in incidencias})))).scalars().all()
    }
    estados = {
        e.id: e for e in (await db.execute(select(GPEstado).where(
            GPEstado.id.in_({i.estado_id for i in incidencias})))).scalars().all()
    }
    ids_prioridad = {i.prioridad_id for i in incidencias if i.prioridad_id}
    prioridades = {
        p.id: p for p in (await db.execute(select(GPPrioridad).where(
            GPPrioridad.id.in_(ids_prioridad)))).scalars().all()
    } if ids_prioridad else {}

    salida = []
    for i in incidencias:
        proyecto = proyectos.get(i.proyecto_id)
        tipo = tipos.get(i.tipo_id)
        estado = estados.get(i.estado_id)
        prioridad = prioridades.get(i.prioridad_id) if i.prioridad_id else None
        salida.append(Tarjeta(
            id=i.id,
            clave=gestion_incidencias.clave_de(proyecto, i) if proyecto else str(i.id),
            proyecto_id=i.proyecto_id,
            resumen=i.resumen,
            tipo=tipo.nombre if tipo else None,
            tipo_id=i.tipo_id,
            icono=tipo.icono if tipo else None,
            estado=estado.nombre if estado else None,
            estado_id=i.estado_id,
            categoria=estado.categoria if estado else None,
            color_estado=estado.color if estado else None,
            prioridad=prioridad.nombre if prioridad else None,
            prioridad_id=i.prioridad_id,
            color_prioridad=prioridad.color if prioridad else None,
            asignado=i.asignado, reporta=i.reporta, puntos=i.puntos,
            padre_id=i.padre_id, sprint_id=i.sprint_id,
            etiquetas=list(i.etiquetas or []), campos=dict(i.campos or {}),
            vence=i.vence, actualizado=i.actualizado, ticket_id=i.ticket_id,
        ))
    return salida


async def _incidencia_visible(db: AsyncSession, quien: Miembro,
                              incidencia_id: int,
                              escritura: bool = False):
    """La incidencia y su proyecto, comprobando el acceso al objeto concreto."""
    inc = (await db.execute(select(GPIncidencia).where(
        GPIncidencia.id == incidencia_id))).scalar_one_or_none()
    if inc is None:
        raise HTTPException(404, "Esa incidencia no existe.")
    proyecto = await exigir_proyecto(db, quien, inc.proyecto_id, escritura=escritura)
    return inc, proyecto


def _tocar(inc: GPIncidencia) -> None:
    inc.actualizado = datetime.now(timezone.utc)


# ─── Listado ──────────────────────────────────────────────────────────────────

@router.get("/incidencias", response_model=Pagina)
async def listar(
    proyecto_id: Optional[int] = None,
    estado_id: Optional[int] = None,
    categoria: Optional[str] = None,
    tipo_id: Optional[int] = None,
    prioridad_id: Optional[int] = None,
    asignado: Optional[str] = None,
    padre_id: Optional[int] = None,
    sprint_id: Optional[int] = None,
    texto: Optional[str] = None,
    sin_clasificar: Optional[bool] = None,
    limite: int = Query(50, ge=1, le=MAX_POR_PAGINA),
    cursor: Optional[str] = None,
    con_total: bool = False,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Las incidencias que esta persona puede ver, paginadas por cursor.

    `con_total` es opcional porque contar es caro: obliga a recorrer todo lo que
    cumple el filtro, mientras que la página solo toca lo que devuelve. La
    pantalla lo pide cuando de verdad va a mostrar el número.
    """
    visibles = await proyectos_visibles(db, quien)
    if proyecto_id is not None:
        await exigir_proyecto(db, quien, proyecto_id)

    consulta = select(GPIncidencia)
    consulta = limitar(consulta, visibles, GPIncidencia.proyecto_id)

    if proyecto_id is not None:
        consulta = consulta.where(GPIncidencia.proyecto_id == proyecto_id)
    if estado_id is not None:
        consulta = consulta.where(GPIncidencia.estado_id == estado_id)
    if tipo_id is not None:
        consulta = consulta.where(GPIncidencia.tipo_id == tipo_id)
    if prioridad_id is not None:
        consulta = consulta.where(GPIncidencia.prioridad_id == prioridad_id)
    if asignado:
        consulta = consulta.where(GPIncidencia.asignado == asignado)
    if padre_id is not None:
        consulta = consulta.where(GPIncidencia.padre_id == padre_id)
    if sprint_id is not None:
        consulta = consulta.where(GPIncidencia.sprint_id == sprint_id)

    if categoria or sin_clasificar is not None:
        sub = select(GPEstado.id)
        if categoria:
            sub = sub.where(GPEstado.categoria == categoria.upper())
        elif sin_clasificar:
            sub = sub.where(GPEstado.categoria == "SIN_CLASIFICAR")
        else:
            sub = sub.where(GPEstado.categoria != "SIN_CLASIFICAR")
        consulta = consulta.where(GPIncidencia.estado_id.in_(sub))

    if texto:
        # Búsqueda por el índice de texto completo, con respaldo por prefijo para
        # que buscar la clave visible («SOP-12») o un fragmento corto también
        # encuentre algo: `to_tsquery` no sirve para eso.
        aguja = texto.strip()
        consulta = consulta.where(or_(
            GPIncidencia.busqueda.op("@@")(
                func.plainto_tsquery("spanish", aguja)),
            GPIncidencia.resumen.ilike(f"%{aguja}%"),
        ))

    total = None
    if con_total:
        total = (await db.execute(
            select(func.count()).select_from(consulta.subquery()))).scalar() or 0

    if cursor:
        marca, ident = _leer_cursor(cursor)
        # La misma pareja que ordena. Sin el desempate por id, dos incidencias
        # con la misma marca de tiempo hacen que el cursor repita una y se salte
        # la otra.
        consulta = consulta.where(or_(
            GPIncidencia.actualizado < marca,
            (GPIncidencia.actualizado == marca) & (GPIncidencia.id < ident),
        ))

    consulta = consulta.order_by(
        GPIncidencia.actualizado.desc(), GPIncidencia.id.desc()
    ).limit(limite + 1)   # una de más: así se sabe si hay página siguiente

    filas = list((await db.execute(consulta)).scalars().all())
    hay_mas = len(filas) > limite
    filas = filas[:limite]

    return Pagina(
        resultados=await _tarjetas(db, filas),
        siguiente=_cursor_de(filas[-1]) if hay_mas and filas else None,
        total=total,
    )


@router.get("/incidencias/{incidencia_id}")
async def ver(
    incidencia_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """La incidencia con todo lo que su pantalla necesita.

    Incluye las transiciones disponibles ya evaluadas: quien mira la pantalla
    tiene que ver los botones que de verdad puede usar, no todos los del flujo.
    """
    inc, proyecto = await _incidencia_visible(db, quien, incidencia_id)
    tarjeta = (await _tarjetas(db, [inc]))[0]

    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == inc.tipo_id))).scalar_one()
    workflow_id = await gestion_incidencias.workflow_de(db, proyecto, tipo)

    comentarios = list((await db.execute(select(GPComentario).where(
        GPComentario.incidencia_id == incidencia_id
    ).order_by(GPComentario.id))).scalars().all())

    adjuntos = list((await db.execute(select(GPAdjunto).where(
        GPAdjunto.incidencia_id == incidencia_id
    ).order_by(GPAdjunto.id))).scalars().all())

    historial = list((await db.execute(select(GPHistorial).where(
        GPHistorial.incidencia_id == incidencia_id
    ).order_by(GPHistorial.creado.desc()).limit(200))).scalars().all())

    hijas = list((await db.execute(select(GPIncidencia).where(
        GPIncidencia.padre_id == incidencia_id
    ).order_by(GPIncidencia.orden))).scalars().all())

    r = await db.execute(select(GPVinculo).where(or_(
        GPVinculo.origen_id == incidencia_id,
        GPVinculo.destino_id == incidencia_id)))
    vinculos_crudos = list(r.scalars().all())
    otros = {
        v.destino_id if v.origen_id == incidencia_id else v.origen_id
        for v in vinculos_crudos
    }
    relacionadas = await _tarjetas(db, list((await db.execute(
        select(GPIncidencia).where(GPIncidencia.id.in_(otros))
    )).scalars().all())) if otros else []
    por_id = {t.id: t for t in relacionadas}

    campos = gestion_campos.descripcion_de(
        await gestion_campos.campos_aplicables(db, proyecto.id, inc.tipo_id))

    return {
        "incidencia": tarjeta,
        "descripcion": inc.descripcion,
        # De qué nivel es, para saber qué puede colgar de ella. La regla vive en
        # el servidor; la pantalla la usa para no ofrecer lo que va a rechazar.
        "nivel": tipo.nivel,
        "inicio_plan": inc.inicio_plan,
        "iniciado": inc.iniciado,
        "resuelto": inc.resuelto,
        "creado": inc.created_at,
        "proyecto": {"id": proyecto.id, "clave": proyecto.clave,
                     "nombre": proyecto.nombre},
        "definicion_campos": campos,
        "transiciones": await gestion_workflow.disponibles(db, inc, workflow_id, quien),
        "comentarios": [ComentarioResponse.model_validate(c) for c in comentarios],
        "adjuntos": [AdjuntoResponse.model_validate(a) for a in adjuntos],
        "historial": [HistorialResponse.model_validate(h) for h in historial],
        "subtareas": await _tarjetas(db, hijas),
        "vinculos": [
            {"id": v.id, "tipo": v.tipo,
             "sentido": "sale" if v.origen_id == incidencia_id else "entra",
             "otra": por_id.get(
                 v.destino_id if v.origen_id == incidencia_id else v.origen_id)}
            for v in vinculos_crudos
        ],
    }


# ─── Alta y edición ───────────────────────────────────────────────────────────

@router.post("/incidencias", status_code=201)
async def crear(
    data: IncidenciaEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Da de alta una incidencia con lo que diga la configuración.

    El servidor no confía en que la pantalla mandó lo correcto: vuelve a resolver
    qué campos aplican, valida cada valor contra su tipo, comprueba que las
    referencias existan y sean de este proyecto, y exige los obligatorios. Una
    petición armada a mano se topa con lo mismo.
    """
    proyecto = await exigir_proyecto(db, quien, data.proyecto_id, escritura=True)
    tipo = await gestion_incidencias.tipo_valido(db, data.tipo_id, proyecto.id)

    aplicables = await gestion_formulario.campos_del(db, proyecto.id, tipo.id)
    await gestion_formulario.cargar_opciones(db, aplicables, proyecto.id, quien.usuario)

    # Los valores por defecto se aplican ANTES de validar y solo donde no llegó
    # nada: si se aplicaran después, un obligatorio con defecto se rechazaría por
    # vacío aunque el servidor supiera con qué llenarlo.
    defectos = await gestion_formulario._defectos(
        db, aplicables, proyecto.id, quien.usuario)
    entrantes = {**{k: v for k, v in defectos.items()
                    if data.campos.get(k) in (None, "", [])},
                 **{k: v for k, v in data.campos.items() if v not in (None, "", [])}}

    columnas, jsonb = await gestion_formulario.validar(
        db, aplicables, entrantes, proyecto.id)

    # Todo lo validado va por `columnas`, incluido el título: sacarlo a mano era
    # duplicar el reparto que el motor ya hizo, y lo que se saca en un sitio y no
    # en el otro es lo que después se guarda en ninguna parte.
    inc = await gestion_incidencias.crear(
        db, proyecto, tipo_id=tipo.id, resumen="", descripcion=None,
        autor=quien.usuario, campos=jsonb, columnas=columnas,
    )
    await db.commit()
    await db.refresh(inc)
    return (await _tarjetas(db, [inc]))[0]


@router.put("/incidencias/{incidencia_id}")
async def editar(
    incidencia_id: int, data: IncidenciaCambio,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Edita la incidencia y deja constancia de cada campo que cambió.

    Los obligatorios no se exigen al editar: obligar a llenar un campo que se
    volvió obligatorio después impediría corregir un título.
    """
    inc, proyecto = await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    registrados: List[tuple] = []

    if data.tipo_id is not None and data.tipo_id != inc.tipo_id:
        nuevo_tipo = await gestion_incidencias.tipo_valido(db, data.tipo_id, proyecto.id)
        anterior = (await db.execute(select(GPTipoIncidencia).where(
            GPTipoIncidencia.id == inc.tipo_id))).scalar_one_or_none()
        registrados.append(
            ("tipo", anterior.nombre if anterior else None, nuevo_tipo.nombre))
        inc.tipo_id = nuevo_tipo.id

    if not data.campos:
        if registrados:
            gestion_incidencias.anotar_varios(db, inc.id, registrados, quien.usuario)
            _tocar(inc)
            await db.commit()
            await db.refresh(inc)
        return (await _tarjetas(db, [inc]))[0]

    aplicables = await gestion_formulario.campos_del(db, proyecto.id, inc.tipo_id)
    await gestion_formulario.cargar_opciones(db, aplicables, proyecto.id, quien.usuario)

    antes_jsonb = dict(inc.campos or {})
    columnas, jsonb = await gestion_formulario.validar(
        db, aplicables, data.campos, proyecto.id,
        previos=antes_jsonb, exigir_obligatorios=False)

    # El padre necesita su comprobación propia: la jerarquía depende del nivel
    # del tipo y de que no se forme un ciclo, y eso no lo sabe un validador de
    # campo.
    if "padre_id" in columnas:
        destino = columnas["padre_id"]
        if destino is not None:
            tipo = (await db.execute(select(GPTipoIncidencia).where(
                GPTipoIncidencia.id == inc.tipo_id))).scalar_one()
            await gestion_incidencias.validar_padre(
                db, destino, proyecto.id, tipo, hijo_id=inc.id)

    for columna, valor in columnas.items():
        anterior = getattr(inc, columna, None)
        if anterior == valor:
            continue
        if columna == "resumen":
            valor = (valor or "").strip()[:300]
            if not valor:
                raise HTTPException(422, "El título no puede quedar vacío.")
        setattr(inc, columna, valor)
        registrados.append((columna, anterior, valor))

    if jsonb != antes_jsonb:
        inc.campos = jsonb
        for clave in sorted(set(antes_jsonb) | set(jsonb)):
            if antes_jsonb.get(clave) != jsonb.get(clave):
                registrados.append((clave, antes_jsonb.get(clave), jsonb.get(clave)))

    if registrados:
        gestion_incidencias.anotar_varios(db, inc.id, registrados, quien.usuario)
        _tocar(inc)

    await db.commit()
    await db.refresh(inc)
    return (await _tarjetas(db, [inc]))[0]


@router.post("/incidencias/{incidencia_id}/transicion")
async def transicionar(
    incidencia_id: int, data: TransicionEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Mueve la incidencia por una transición del flujo, con sus reglas."""
    inc, proyecto = await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == inc.tipo_id))).scalar_one()
    workflow_id = await gestion_incidencias.workflow_de(db, proyecto, tipo)

    cambios = await gestion_workflow.aplicar(
        db, inc, data.transicion_id, workflow_id, quien)
    gestion_incidencias.anotar_varios(db, inc.id, cambios, quien.usuario)

    if data.comentario and data.comentario.strip():
        db.add(GPComentario(
            incidencia_id=inc.id, autor=quien.usuario,
            cuerpo=data.comentario.strip(), menciones=[], interno=False))

    _tocar(inc)
    await db.commit()
    await db.refresh(inc)

    return {
        "incidencia": (await _tarjetas(db, [inc]))[0],
        "transiciones": await gestion_workflow.disponibles(db, inc, workflow_id, quien),
    }


# ─── Conversación ─────────────────────────────────────────────────────────────

@router.post("/incidencias/{incidencia_id}/comentarios",
             response_model=ComentarioResponse, status_code=201)
async def comentar(
    incidencia_id: int, data: ComentarioEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    inc, _ = await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    cuerpo = data.cuerpo.strip()
    if not cuerpo:
        raise HTTPException(422, "El comentario está vacío.")

    comentario = GPComentario(
        incidencia_id=inc.id, autor=quien.usuario, cuerpo=cuerpo,
        # Se guardan resueltas y no se vuelve a analizar el texto: si se
        # recalcularan al editar, una corrección de ortografía volvería a
        # notificar a todo el mundo.
        menciones=sorted({m.strip() for m in data.menciones if m.strip()}),
        interno=bool(data.interno),
    )
    db.add(comentario)
    _tocar(inc)
    await db.commit()
    await db.refresh(comentario)
    return comentario


@router.put("/comentarios/{comentario_id}", response_model=ComentarioResponse)
async def editar_comentario(
    comentario_id: int, data: ComentarioEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    comentario = (await db.execute(select(GPComentario).where(
        GPComentario.id == comentario_id))).scalar_one_or_none()
    if comentario is None:
        raise HTTPException(404, "Ese comentario no existe.")
    await _incidencia_visible(db, quien, comentario.incidencia_id, escritura=True)

    if comentario.autor != quien.usuario:
        raise HTTPException(403, "Solo quien escribió un comentario puede editarlo.")

    comentario.cuerpo = data.cuerpo.strip()
    comentario.editado = True
    await db.commit()
    await db.refresh(comentario)
    return comentario


# ─── Vínculos ─────────────────────────────────────────────────────────────────

@router.post("/incidencias/{incidencia_id}/vinculos", status_code=201)
async def vincular(
    incidencia_id: int, data: VinculoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Relaciona dos incidencias. Se guarda una vez y se lee en los dos sentidos."""
    inc, _ = await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    tipo = (data.tipo or "").upper()
    if tipo not in TIPOS_VINCULO:
        raise HTTPException(422, f"Tipo de vínculo no válido. Son: {', '.join(TIPOS_VINCULO)}.")
    if data.destino_id == incidencia_id:
        raise HTTPException(400, "Una incidencia no se puede vincular consigo misma.")

    # El destino también tiene que ser visible: si no, vincular sería una forma
    # de confirmar que existe una incidencia de un proyecto reservado.
    await _incidencia_visible(db, quien, data.destino_id)

    ya = (await db.execute(select(GPVinculo).where(
        GPVinculo.origen_id == incidencia_id,
        GPVinculo.destino_id == data.destino_id,
        GPVinculo.tipo == tipo))).scalar_one_or_none()
    if ya is not None:
        return {"id": ya.id, "tipo": ya.tipo}

    vinculo = GPVinculo(origen_id=incidencia_id, destino_id=data.destino_id,
                        tipo=tipo, autor=quien.usuario)
    db.add(vinculo)
    gestion_incidencias.anotar(
        db, inc.id, "vinculo", None, f"{tipo} → {data.destino_id}", quien.usuario)
    _tocar(inc)
    await db.commit()
    await db.refresh(vinculo)
    return {"id": vinculo.id, "tipo": vinculo.tipo}


@router.delete("/vinculos/{vinculo_id}", status_code=204)
async def desvincular(
    vinculo_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    vinculo = (await db.execute(select(GPVinculo).where(
        GPVinculo.id == vinculo_id))).scalar_one_or_none()
    if vinculo is None:
        raise HTTPException(404, "Ese vínculo no existe.")
    await _incidencia_visible(db, quien, vinculo.origen_id, escritura=True)
    await db.delete(vinculo)
    await db.commit()


# ─── Adjuntos ─────────────────────────────────────────────────────────────────

def _nombre_seguro(nombre: str) -> str:
    """El nombre lo escribe quien sube el archivo: fuera rutas y caracteres raros."""
    limpio = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.basename(nombre or "archivo"))
    return limpio[:120] or "archivo"


@router.post("/incidencias/{incidencia_id}/adjuntos",
             response_model=List[AdjuntoResponse], status_code=201)
async def adjuntar(
    incidencia_id: int,
    archivos: List[UploadFile] = File(...),
    comentario_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    inc, _ = await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    ALMACEN.mkdir(parents=True, exist_ok=True)

    guardados = []
    for archivo in archivos:
        contenido = await archivo.read()
        nombre = _nombre_seguro(archivo.filename or "archivo")
        if not contenido:
            raise HTTPException(400, f"«{nombre}» está vacío.")
        if len(contenido) > MAX_BYTES:
            raise HTTPException(
                400,
                f"«{nombre}» pesa {len(contenido) // (1024 * 1024)} MB y el "
                f"máximo son {MAX_BYTES // (1024 * 1024)} MB.")
        extension = os.path.splitext(nombre)[1].lower()
        if extension not in EXTENSIONES:
            raise HTTPException(
                400,
                f"No se admiten archivos «{extension or 'sin extensión'}». "
                f"Se aceptan: {', '.join(sorted(e.lstrip('.') for e in EXTENSIONES))}.")

        firma = hashlib.md5(contenido).hexdigest()[:10]
        relativa = f"gestion/i{inc.id}_{firma}_{nombre}"
        (Path(settings.UPLOAD_DIR) / relativa).write_bytes(contenido)

        adjunto = GPAdjunto(
            incidencia_id=inc.id, comentario_id=comentario_id, nombre=nombre,
            tipo_mime=archivo.content_type or mimetypes.guess_type(nombre)[0],
            tamano=len(contenido), ruta=relativa, subido_por=quien.usuario,
        )
        db.add(adjunto)
        guardados.append(adjunto)

    gestion_incidencias.anotar(
        db, inc.id, "adjunto", None,
        ", ".join(a.nombre for a in guardados), quien.usuario)
    _tocar(inc)
    await db.commit()
    for a in guardados:
        await db.refresh(a)
    return guardados


@router.get("/adjuntos/{adjunto_id}")
async def descargar(
    adjunto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Descarga con permiso comprobado.

    No se sirve por carpeta pública a propósito: un pantallazo adjunto puede
    traer datos de otra empresa, y una URL adivinable los deja a la vista.
    """
    adjunto = (await db.execute(select(GPAdjunto).where(
        GPAdjunto.id == adjunto_id))).scalar_one_or_none()
    if adjunto is None:
        raise HTTPException(404, "Ese archivo no existe.")
    await _incidencia_visible(db, quien, adjunto.incidencia_id)

    ruta = Path(settings.UPLOAD_DIR) / adjunto.ruta
    try:
        # Que la ruta guardada no se haya salido de la carpeta de subidas.
        ruta.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(400, "La ruta del archivo no es válida.")
    if not ruta.exists():
        raise HTTPException(404, "El archivo ya no está en el servidor.")

    return FileResponse(ruta, filename=adjunto.nombre,
                        media_type=adjunto.tipo_mime or "application/octet-stream")


# ─── El puente con la mesa de ayuda ───────────────────────────────────────────

@router.post("/tickets/{ticket_id}/incidencia", status_code=201)
async def desde_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Convierte una solicitud de soporte en trabajo interno.

    El asunto del cliente se copia y su ticket no se toca: sigue viendo en su
    conversación exactamente lo que escribió. Desde acá el equipo reescribe el
    título tantas veces como haga falta.

    Llamarla dos veces devuelve la misma incidencia, no crea otra.
    """
    ticket = (await db.execute(select(SoporteTicket).where(
        SoporteTicket.id == ticket_id))).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(404, "Esa solicitud no existe.")

    inc = await gestion_incidencias.promover_ticket(db, ticket, quien.usuario)
    if inc is None:
        raise HTTPException(
            409,
            "No hay ningún proyecto que reciba las solicitudes de soporte. "
            "Marque «crear incidencia automáticamente» en el proyecto que deba "
            "recibirlas.")
    await db.commit()
    await db.refresh(inc)
    return (await _tarjetas(db, [inc]))[0]


# ─── Mover a cualquier estado ─────────────────────────────────────────────────

class MoverEntrada(BaseModel):
    estado_id: int
    comentario: Optional[str] = None


@router.post("/incidencias/{incidencia_id}/estado")
async def mover_a_estado(
    incidencia_id: int, data: MoverEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Lleva la incidencia a cualquier estado del flujo, incluso hacia atrás.

    POR QUÉ EXISTE, HABIENDO TRANSICIONES
    El flujo declarado describe el camino normal, y sirve para eso. Pero el
    trabajo real se devuelve: algo que se dio por hecho no estaba, una revisión
    encuentra un problema, alguien movió la tarjeta por error. Sin una salida, la
    gente resuelve eso creando una incidencia nueva —y entonces el historial de
    la original miente, porque nunca vuelve atrás.

    No se salta el control: se registra que fue un movimiento manual, con quién
    lo hizo y desde dónde. El límite de trabajo en curso del estado de destino SÍ
    se respeta, porque ese límite existe para proteger al equipo y no para
    describir el camino.
    """
    inc, proyecto = await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == inc.tipo_id))).scalar_one()
    workflow_id = await gestion_incidencias.workflow_de(db, proyecto, tipo)

    destino = (await db.execute(select(GPEstado).where(
        GPEstado.id == data.estado_id,
        GPEstado.workflow_id == workflow_id))).scalar_one_or_none()
    if destino is None:
        raise HTTPException(404, "Ese estado no pertenece al flujo de esta incidencia.")
    if destino.id == inc.estado_id:
        raise HTTPException(409, "La incidencia ya está en ese estado.")

    lleno = await gestion_workflow.hay_cupo(db, destino, proyecto.id, inc.id)
    if lleno:
        raise HTTPException(409, lleno)

    anterior = (await db.execute(select(GPEstado).where(
        GPEstado.id == inc.estado_id))).scalar_one_or_none()
    inc.estado_id = destino.id

    # Las mismas marcas que pone el camino declarado. Si el salto manual no las
    # pusiera, una incidencia cerrada por aquí quedaría sin fecha de cierre y no
    # contaría en ningún informe de cumplimiento —el atajo mentiría, y sería
    # invisible hasta el cierre de mes.
    ahora = datetime.now(timezone.utc)
    if destino.categoria == "EN_CURSO" and not inc.iniciado:
        # No se vuelve a sellar al reempezar: el tiempo de ciclo mediría solo la
        # última vuelta y escondería las anteriores.
        inc.iniciado = ahora
        gestion_incidencias.anotar(db, inc.id, "iniciado", None, ahora, quien.usuario)

    if destino.categoria == "TERMINADO":
        antes = inc.resuelto
        inc.resuelto = ahora
        gestion_incidencias.anotar(db, inc.id, "resuelto", antes, ahora, quien.usuario)
    elif anterior is not None and anterior.categoria == "TERMINADO" and inc.resuelto:
        # Reabrir borra la fecha de cierre: una incidencia que volvió a abrirse y
        # conserva la suya miente en cualquier informe de cumplimiento.
        antes = inc.resuelto
        inc.resuelto = None
        gestion_incidencias.anotar(db, inc.id, "resuelto", antes, None, quien.usuario)

    gestion_incidencias.anotar(
        db, inc.id, "estado",
        anterior.nombre if anterior else None, destino.nombre, quien.usuario)
    gestion_incidencias.anotar(
        db, inc.id, "movimiento", None,
        f"movida a mano a «{destino.nombre}»", quien.usuario)

    if data.comentario and data.comentario.strip():
        db.add(GPComentario(
            incidencia_id=inc.id, autor=quien.usuario,
            cuerpo=data.comentario.strip(), menciones=[], interno=False))

    _tocar(inc)
    await db.commit()
    await db.refresh(inc)
    return {
        "incidencia": (await _tarjetas(db, [inc]))[0],
        "transiciones": await gestion_workflow.disponibles(db, inc, workflow_id, quien),
    }


@router.get("/incidencias/{incidencia_id}/estados")
async def estados_del_flujo(
    incidencia_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Todos los estados a los que se puede llevar esta incidencia."""
    inc, proyecto = await _incidencia_visible(db, quien, incidencia_id)
    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == inc.tipo_id))).scalar_one()
    workflow_id = await gestion_incidencias.workflow_de(db, proyecto, tipo)
    estados = (await db.execute(select(GPEstado).where(
        GPEstado.workflow_id == workflow_id).order_by(GPEstado.orden))).scalars().all()
    return [{
        "id": e.id, "nombre": e.nombre, "categoria": e.categoria,
        "color": e.color, "actual": e.id == inc.estado_id,
    } for e in estados]


# ─── El reloj de trabajo ──────────────────────────────────────────────────────

class CierreTiempo(BaseModel):
    nota: Optional[str] = None


async def _tramo_abierto(db: AsyncSession, incidencia_id: int,
                         usuario: str) -> Optional[GPTiempoTrabajo]:
    return (await db.execute(select(GPTiempoTrabajo).where(
        GPTiempoTrabajo.incidencia_id == incidencia_id,
        GPTiempoTrabajo.usuario == usuario,
        GPTiempoTrabajo.fin.is_(None),
    ).order_by(GPTiempoTrabajo.id.desc()).limit(1))).scalar_one_or_none()


@router.post("/incidencias/{incidencia_id}/tiempo/iniciar", status_code=201)
async def iniciar_tiempo(
    incidencia_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Arranca el reloj sobre esta incidencia, para esta persona.

    Cada quien tiene su propio reloj: dos personas pueden trabajar a la vez sobre
    la misma incidencia y cada una cuenta sus horas. Un reloj compartido sumaría
    el doble del tiempo real.

    Volver a arrancar con un tramo abierto no crea otro: devuelve el que ya
    estaba corriendo. Sin eso, un doble clic duplica el tiempo del día.
    """
    await _incidencia_visible(db, quien, incidencia_id, escritura=True)

    abierto = await _tramo_abierto(db, incidencia_id, quien.usuario)
    if abierto is not None:
        return {"id": abierto.id, "inicio": abierto.inicio, "ya_corria": True}

    tramo = GPTiempoTrabajo(
        incidencia_id=incidencia_id, usuario=quien.usuario,
        inicio=datetime.now(timezone.utc), segundos=0)
    db.add(tramo)
    gestion_incidencias.anotar(db, incidencia_id, "tiempo", None,
                               "inició el trabajo", quien.usuario)
    await db.commit()
    await db.refresh(tramo)
    return {"id": tramo.id, "inicio": tramo.inicio, "ya_corria": False}


async def _cerrar_tramo(db: AsyncSession, incidencia_id: int, quien: Miembro,
                        motivo: str, nota: Optional[str]) -> dict:
    tramo = await _tramo_abierto(db, incidencia_id, quien.usuario)
    if tramo is None:
        raise HTTPException(409, "No hay ningún tramo corriendo para usted.")

    tramo.fin = datetime.now(timezone.utc)
    # El inicio llega con zona si viene de la base y sin ella si lo puso esta
    # misma petición. Restar uno de cada clase revienta, así que se igualan antes
    # de restar en vez de confiar en de dónde salió el valor.
    inicio = tramo.inicio
    if inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=timezone.utc)
    tramo.segundos = max(0, int((tramo.fin - inicio).total_seconds()))
    tramo.motivo = motivo
    if nota:
        tramo.nota = nota[:300]

    minutos = round(tramo.segundos / 60)
    gestion_incidencias.anotar(
        db, incidencia_id, "tiempo", None,
        f"{'pausó' if motivo == 'PAUSA' else 'finalizó'} tras {minutos} min",
        quien.usuario)
    await db.commit()
    return {"id": tramo.id, "segundos": tramo.segundos, "minutos": minutos,
            "motivo": motivo}


@router.post("/incidencias/{incidencia_id}/tiempo/pausar")
async def pausar_tiempo(
    incidencia_id: int, datos: CierreTiempo,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Detiene el reloj. El trabajo sigue abierto y se puede reanudar."""
    await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    return await _cerrar_tramo(db, incidencia_id, quien, "PAUSA", datos.nota)


@router.post("/incidencias/{incidencia_id}/tiempo/finalizar")
async def finalizar_tiempo(
    incidencia_id: int, datos: CierreTiempo,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Detiene el reloj dando el trabajo por terminado.

    NO cierra la incidencia ni lo exige al revés: se puede cerrar una incidencia
    sin haber usado nunca el reloj. El registro de tiempo es para medir, no para
    poner una tranca en el camino de quien trabaja; en cuanto lo obstruye, la
    gente deja de usarlo y la medición se pierde igual.
    """
    await _incidencia_visible(db, quien, incidencia_id, escritura=True)
    return await _cerrar_tramo(db, incidencia_id, quien, "FIN", datos.nota)


@router.get("/incidencias/{incidencia_id}/tiempo")
async def tiempo_de_incidencia(
    incidencia_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Lo trabajado en esta incidencia: el total, por persona, y si hay reloj vivo."""
    await _incidencia_visible(db, quien, incidencia_id)
    tramos = (await db.execute(select(GPTiempoTrabajo).where(
        GPTiempoTrabajo.incidencia_id == incidencia_id,
    ).order_by(GPTiempoTrabajo.id.desc()))).scalars().all()

    por_persona: dict = {}
    total = 0
    for t in tramos:
        total += t.segundos or 0
        por_persona[t.usuario] = por_persona.get(t.usuario, 0) + (t.segundos or 0)

    mio = next((t for t in tramos
                if t.usuario == quien.usuario and t.fin is None), None)
    return {
        "total_segundos": total,
        "por_persona": [{"usuario": u, "segundos": s}
                        for u, s in sorted(por_persona.items(),
                                           key=lambda x: -x[1])],
        # El tramo propio corriendo, para que la pantalla siga el reloj en vivo
        # sin tener que adivinar desde cuándo.
        "corriendo": None if mio is None else {"id": mio.id, "inicio": mio.inicio},
        "tramos": [{
            "id": t.id, "usuario": t.usuario, "inicio": t.inicio, "fin": t.fin,
            "segundos": t.segundos, "motivo": t.motivo, "nota": t.nota,
        } for t in tramos[:40]],
    }


# ─── Borrar un adjunto ────────────────────────────────────────────────────────

@router.delete("/adjuntos/{adjunto_id}", status_code=204)
async def borrar_adjunto(
    adjunto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Quita un archivo subido por error.

    Se borra también del disco: dejar el archivo huérfano en la carpeta significa
    que sigue ahí, descargable por quien sepa la ruta, después de que alguien
    creyó haberlo eliminado. Si el archivo ya no está, se sigue adelante: lo que
    importa es que deje de figurar.
    """
    adjunto = (await db.execute(select(GPAdjunto).where(
        GPAdjunto.id == adjunto_id))).scalar_one_or_none()
    if adjunto is None:
        raise HTTPException(404, "Ese archivo no existe.")
    await _incidencia_visible(db, quien, adjunto.incidencia_id, escritura=True)

    nombre = adjunto.nombre
    try:
        (Path(settings.UPLOAD_DIR) / adjunto.ruta).unlink(missing_ok=True)
    except OSError:
        pass   # el registro se borra igual: lo que se ve es lo que importa

    await db.delete(adjunto)
    gestion_incidencias.anotar(db, adjunto.incidencia_id, "adjunto",
                               nombre, None, quien.usuario)
    await db.commit()
