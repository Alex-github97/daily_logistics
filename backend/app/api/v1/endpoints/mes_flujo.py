"""
El esquema de una línea de producción: qué máquinas la componen y en qué orden.

POR QUÉ UN GRAFO Y NO UNA LISTA
Una línea no es una fila de máquinas numeradas. Se abre en dos cuando hay dos
envasadoras en paralelo, se devuelve cuando hay reproceso, y recibe materia
prima en varios puntos, no solo al principio. Un campo `orden` en la máquina
solo sabe describir una fila india; todas las demás formas existen en una
planta real y se perderían.

Por eso el esquema se guarda como nodos y conexiones, y por eso las
coordenadas viven en la base y no en el navegador: el dibujo describe el
proceso, no a quien lo dibujó, y quien abra la línea mañana tiene que ver lo
mismo.

CÓMO SE GUARDA
El lienzo se manda entero en un PUT y no por diferencias sueltas. Mover tres
máquinas, borrar una conexión y agregar dos nodos es una sola edición para
quien la hace; partirla en ocho peticiones abre la puerta a que la mitad se
aplique y el esquema quede a medias. Los nodos nuevos viajan con un id
negativo —el que les puso la pantalla— y acá se traducen a los definitivos.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.infrastructure.models.mes import (
    MESPlanta, MESLinea, MESCeldaTrabajo, MESEquipo, MESProducto, MESOperacion,
    MESFlujoNodo, MESFlujoConexion,
    MESOrdenProduccion, MESEjecucion, MESParada,
    TipoNodoFlujoEnum, TipoConexionFlujoEnum,
    EstadoOrdenProduccionEnum, EstadoEjecucionMESEnum,
)

router = APIRouter(prefix='/mes', tags=['MES · Esquema de planta'])


# ─── Esquemas ─────────────────────────────────────────────────────────────────

class NodoIn(BaseModel):
    # Negativo = nodo recién puesto en el lienzo que todavía no existe en la
    # base. La pantalla necesita un id para poder conectarlo antes de guardar.
    id: Optional[int] = None
    tipo: str = 'EQUIPO'
    equipo_id: Optional[int] = None
    producto_id: Optional[int] = None
    operacion_id: Optional[int] = None
    nombre: Optional[str] = None
    pos_x: float = 0
    pos_y: float = 0
    cantidad_por_unidad: Optional[float] = None
    unidad_medida: Optional[str] = None
    tiempo_ciclo_seg: Optional[float] = None
    es_cuello_botella: bool = False
    notas: Optional[str] = None


class ConexionIn(BaseModel):
    origen_id: int
    destino_id: int
    tipo: str = 'NORMAL'
    etiqueta: Optional[str] = None


class FlujoIn(BaseModel):
    nodos: List[NodoIn] = []
    conexiones: List[ConexionIn] = []


class NodoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    linea_id: int
    tipo: str
    equipo_id: Optional[int] = None
    producto_id: Optional[int] = None
    operacion_id: Optional[int] = None
    nombre: Optional[str] = None
    pos_x: float
    pos_y: float
    cantidad_por_unidad: Optional[float] = None
    unidad_medida: Optional[str] = None
    tiempo_ciclo_seg: Optional[float] = None
    es_cuello_botella: bool = False
    notas: Optional[str] = None
    # Se resuelven al leer, para que el lienzo pinte sin pedir tres listas más.
    equipo_codigo: Optional[str] = None
    equipo_nombre: Optional[str] = None
    producto_codigo: Optional[str] = None
    producto_nombre: Optional[str] = None
    producto_tipo: Optional[str] = None
    operacion_nombre: Optional[str] = None
    etiqueta: Optional[str] = None


class ConexionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    origen_id: int
    destino_id: int
    tipo: str
    etiqueta: Optional[str] = None


class FlujoOut(BaseModel):
    linea_id: int
    linea_nombre: Optional[str] = None
    planta_id: Optional[int] = None
    planta_nombre: Optional[str] = None
    nodos: List[NodoOut] = []
    conexiones: List[ConexionOut] = []
    # Lo que el esquema deja ver de un vistazo, calculado y no escrito a mano.
    resumen: Dict[str, Any] = {}


def _valor(x) -> Optional[str]:
    """El nombre del enum, venga como enum o como texto ya plano."""
    return getattr(x, 'value', x)


# ─── Leer ─────────────────────────────────────────────────────────────────────

async def _armar_flujo(db: AsyncSession, linea: MESLinea) -> FlujoOut:
    r = await db.execute(select(MESFlujoNodo).where(and_(
        MESFlujoNodo.linea_id == linea.id, MESFlujoNodo.activo == True)))
    nodos = list(r.scalars().all())

    r = await db.execute(select(MESFlujoConexion)
                         .where(MESFlujoConexion.linea_id == linea.id))
    conexiones = list(r.scalars().all())

    equipos = {e.id: e for e in (await db.execute(select(MESEquipo))).scalars().all()}
    productos = {p.id: p for p in (await db.execute(select(MESProducto))).scalars().all()}
    operaciones = {o.id: o for o in (await db.execute(select(MESOperacion))).scalars().all()}
    planta = await db.get(MESPlanta, linea.planta_id)

    salida: List[NodoOut] = []
    for n in nodos:
        item = NodoOut.model_validate(n)
        item.tipo = _valor(n.tipo)
        eq = equipos.get(n.equipo_id) if n.equipo_id else None
        pr = productos.get(n.producto_id) if n.producto_id else None
        op = operaciones.get(n.operacion_id) if n.operacion_id else None
        if eq:
            item.equipo_codigo, item.equipo_nombre = eq.codigo, eq.nombre
        if pr:
            item.producto_codigo, item.producto_nombre = pr.codigo, pr.nombre
            item.producto_tipo = _valor(pr.tipo)
        if op:
            item.operacion_nombre = op.nombre
        # Lo que se pinta dentro de la caja: el nombre propio si lo tiene, y si
        # no, el de la máquina o el del material. Un nodo sin etiqueta sería
        # una caja muda en el diagrama.
        item.etiqueta = (n.nombre or (eq.nombre if eq else None)
                         or (pr.nombre if pr else None) or _valor(n.tipo).capitalize())
        salida.append(item)

    conexiones_out = []
    for c in conexiones:
        item = ConexionOut.model_validate(c)
        item.tipo = _valor(c.tipo)
        conexiones_out.append(item)

    return FlujoOut(
        linea_id=linea.id, linea_nombre=linea.nombre,
        planta_id=linea.planta_id, planta_nombre=planta.nombre if planta else None,
        nodos=salida, conexiones=conexiones_out,
        resumen=_resumen(salida, conexiones_out),
    )


def _resumen(nodos: List[NodoOut], conexiones: List[ConexionOut]) -> Dict[str, Any]:
    """Lo que el esquema dice de sí mismo.

    Las tres advertencias no son adorno: un nodo suelto casi siempre es una
    máquina que alguien puso y olvidó conectar, y una línea sin entrada de
    material o sin salida de producto está a medio dibujar. Vale más avisarlo
    en la pantalla que descubrirlo cuando la orden no encuentre por dónde
    empezar.
    """
    con_origen = {c.origen_id for c in conexiones}
    con_destino = {c.destino_id for c in conexiones}
    sueltos = [n for n in nodos if n.id not in con_origen and n.id not in con_destino]

    equipos = [n for n in nodos if n.tipo == 'EQUIPO']
    tiempos = [n.tiempo_ciclo_seg for n in equipos if n.tiempo_ciclo_seg]
    return {
        'nodos': len(nodos),
        'equipos': len(equipos),
        'entradas': len([n for n in nodos if n.tipo == 'ENTRADA']),
        'salidas': len([n for n in nodos if n.tipo == 'SALIDA']),
        'inspecciones': len([n for n in nodos if n.tipo == 'INSPECCION']),
        'conexiones': len(conexiones),
        'retrabajos': len([c for c in conexiones if c.tipo == 'RETRABAJO']),
        'nodos_sueltos': [n.etiqueta for n in sueltos],
        'sin_entrada': not any(n.tipo == 'ENTRADA' for n in nodos),
        'sin_salida': not any(n.tipo == 'SALIDA' for n in nodos),
        # El ciclo de la línea lo marca su etapa más lenta, no la suma: las
        # máquinas trabajan a la vez, y la línea entrega al ritmo del cuello
        # de botella.
        'ciclo_linea_seg': max(tiempos) if tiempos else None,
        'cuello_botella': next(
            (n.etiqueta for n in equipos
             if n.tiempo_ciclo_seg and tiempos and n.tiempo_ciclo_seg == max(tiempos)),
            None),
    }


@router.get('/lineas/{linea_id}/flujo', response_model=FlujoOut)
async def ver_flujo(linea_id: int, db: AsyncSession = Depends(get_db)):
    linea = await db.get(MESLinea, linea_id)
    if not linea:
        raise HTTPException(404, 'Esa línea no existe')
    return await _armar_flujo(db, linea)


# ─── Guardar ──────────────────────────────────────────────────────────────────

def _enum(valor: str, tipo, campo: str):
    try:
        return tipo(valor)
    except ValueError:
        permitidos = ', '.join(x.value for x in tipo)
        raise HTTPException(400, f'{campo} «{valor}» no es válido. Use uno de: {permitidos}.')


@router.put('/lineas/{linea_id}/flujo', response_model=FlujoOut)
async def guardar_flujo(linea_id: int, data: FlujoIn, db: AsyncSession = Depends(get_db)):
    """Reemplaza el esquema de la línea por el que manda la pantalla."""
    linea = await db.get(MESLinea, linea_id)
    if not linea:
        raise HTTPException(404, 'Esa línea no existe')

    # Un nodo de equipo sin equipo, o de entrada sin material, es una caja vacía
    # que después nadie sabe qué representaba. Se rechaza al guardar, que es
    # cuando quien dibuja todavía tiene el contexto en la cabeza.
    for n in data.nodos:
        tipo = _enum(n.tipo, TipoNodoFlujoEnum, 'El tipo de nodo')
        if tipo is TipoNodoFlujoEnum.EQUIPO and not n.equipo_id:
            raise HTTPException(400, 'Cada nodo de máquina tiene que apuntar a un '
                                     'equipo del catálogo.')
        if tipo in (TipoNodoFlujoEnum.ENTRADA, TipoNodoFlujoEnum.SALIDA) and not n.producto_id:
            faltante = 'la materia prima que entra' if tipo is TipoNodoFlujoEnum.ENTRADA \
                else 'el producto que sale'
            raise HTTPException(400, f'Indique {faltante}: un nodo de '
                                     f'{tipo.value.lower()} sin material no dice nada.')
        if n.equipo_id and not await db.get(MESEquipo, n.equipo_id):
            raise HTTPException(400, f'El equipo {n.equipo_id} no existe.')
        if n.producto_id and not await db.get(MESProducto, n.producto_id):
            raise HTTPException(400, f'El material {n.producto_id} no existe.')
        if n.operacion_id and not await db.get(MESOperacion, n.operacion_id):
            raise HTTPException(400, f'La operación {n.operacion_id} no existe.')

    # Lo que había, para saber qué se borró.
    r = await db.execute(select(MESFlujoNodo).where(MESFlujoNodo.linea_id == linea_id))
    previos = {n.id: n for n in r.scalars().all()}

    # Las conexiones se rehacen enteras: son baratas de recrear y reconciliar
    # aristas una por una solo agregaría estados intermedios raros.
    await db.execute(MESFlujoConexion.__table__.delete()
                     .where(MESFlujoConexion.linea_id == linea_id))

    traduccion: Dict[int, int] = {}     # id del lienzo → id de la base
    vistos = set()
    for n in data.nodos:
        campos = n.model_dump(exclude={'id', 'tipo'})
        obj = previos.get(n.id) if n.id and n.id > 0 else None
        if obj is None:
            obj = MESFlujoNodo(linea_id=linea_id)
            db.add(obj)
        for campo, valor in campos.items():
            setattr(obj, campo, valor)
        obj.tipo = _enum(n.tipo, TipoNodoFlujoEnum, 'El tipo de nodo')
        obj.activo = True
        await db.flush()
        if n.id is not None:
            traduccion[n.id] = obj.id
        traduccion[obj.id] = obj.id
        vistos.add(obj.id)

    # Lo que ya no está en el lienzo se retira. Se borra de verdad y no se
    # desactiva: un nodo es el dibujo de una etapa, no un registro histórico;
    # lo que produjo esa etapa vive en las órdenes y no se toca.
    for nid, obj in previos.items():
        if nid not in vistos:
            await db.delete(obj)

    for c in data.conexiones:
        origen = traduccion.get(c.origen_id)
        destino = traduccion.get(c.destino_id)
        if not origen or not destino:
            continue    # apunta a un nodo que ya no está: la conexión sobra
        if origen == destino:
            raise HTTPException(400, 'Una etapa no se puede conectar consigo misma.')
        db.add(MESFlujoConexion(
            linea_id=linea_id, origen_id=origen, destino_id=destino,
            tipo=_enum(c.tipo, TipoConexionFlujoEnum, 'El tipo de conexión'),
            etiqueta=c.etiqueta))

    await db.commit()
    return await _armar_flujo(db, linea)


# ─── El tablero de la planta ──────────────────────────────────────────────────

@router.get('/plantas/{planta_id}/tablero')
async def tablero_planta(planta_id: int, db: AsyncSession = Depends(get_db)):
    """Cómo está la planta ahora: sus líneas, sus máquinas y qué se produce.

    Sale de las órdenes y las ejecuciones reales. Es la vista que reemplaza a
    la pantalla de planta que mostraba cifras escritas en el código.
    """
    planta = await db.get(MESPlanta, planta_id)
    if not planta:
        raise HTTPException(404, 'Esa planta no existe')

    r = await db.execute(select(MESLinea).where(and_(
        MESLinea.planta_id == planta_id, MESLinea.activo == True))
        .order_by(MESLinea.codigo))
    lineas = list(r.scalars().all())
    ids = [l.id for l in lineas]

    # Celdas y equipos de esas líneas, en dos consultas y no en una por línea.
    celdas: Dict[int, List[MESCeldaTrabajo]] = {}
    if ids:
        r = await db.execute(select(MESCeldaTrabajo).where(and_(
            MESCeldaTrabajo.linea_id.in_(ids), MESCeldaTrabajo.activo == True)))
        for c in r.scalars().all():
            celdas.setdefault(c.linea_id, []).append(c)

    celda_ids = [c.id for grupo in celdas.values() for c in grupo]
    equipos_por_celda: Dict[int, List[MESEquipo]] = {}
    if celda_ids:
        r = await db.execute(select(MESEquipo).where(and_(
            MESEquipo.celda_id.in_(celda_ids), MESEquipo.activo == True)))
        for e in r.scalars().all():
            equipos_por_celda.setdefault(e.celda_id, []).append(e)

    # Cuántos nodos tiene dibujado cada línea: es lo que distingue una línea
    # configurada de una que solo tiene máquinas sueltas.
    nodos_por_linea: Dict[int, int] = {}
    if ids:
        r = await db.execute(select(MESFlujoNodo.linea_id, func.count())
                             .where(and_(MESFlujoNodo.linea_id.in_(ids),
                                         MESFlujoNodo.activo == True))
                             .group_by(MESFlujoNodo.linea_id))
        nodos_por_linea = {lid: n for lid, n in r.all()}

    # Órdenes vivas por línea.
    abiertas = (EstadoOrdenProduccionEnum.LIBERADA,
                EstadoOrdenProduccionEnum.EN_EJECUCION,
                EstadoOrdenProduccionEnum.SUSPENDIDA)
    ordenes_por_linea: Dict[int, List[MESOrdenProduccion]] = {}
    if ids:
        r = await db.execute(select(MESOrdenProduccion).where(and_(
            MESOrdenProduccion.linea_id.in_(ids),
            MESOrdenProduccion.estado.in_(abiertas))))
        for o in r.scalars().all():
            ordenes_por_linea.setdefault(o.linea_id, []).append(o)

    salida = []
    for l in lineas:
        mis_celdas = celdas.get(l.id, [])
        equipos = [e for c in mis_celdas for e in equipos_por_celda.get(c.id, [])]
        ordenes = ordenes_por_linea.get(l.id, [])
        planificado = sum(o.cantidad_planificada or 0 for o in ordenes)
        producido = sum(o.cantidad_producida or 0 for o in ordenes)
        scrap = sum(o.cantidad_scrap or 0 for o in ordenes)
        salida.append({
            'id': l.id, 'codigo': l.codigo, 'nombre': l.nombre,
            'capacidad_hora': l.capacidad_hora, 'unidad_medida': l.unidad_medida,
            'celdas': [{'id': c.id, 'codigo': c.codigo, 'nombre': c.nombre,
                        'equipos': len(equipos_por_celda.get(c.id, []))}
                       for c in mis_celdas],
            'total_celdas': len(mis_celdas),
            'total_equipos': len(equipos),
            'nodos_esquema': nodos_por_linea.get(l.id, 0),
            'tiene_esquema': nodos_por_linea.get(l.id, 0) > 0,
            'ordenes_abiertas': len(ordenes),
            'cantidad_planificada': planificado,
            'cantidad_producida': producido,
            'cantidad_scrap': scrap,
            'avance_pct': round(producido / planificado * 100, 1) if planificado else None,
            'scrap_pct': round(scrap / (producido + scrap) * 100, 1)
                         if (producido + scrap) else None,
            'estado': ('PRODUCIENDO' if ordenes else
                       'CONFIGURADA' if nodos_por_linea.get(l.id) else 'SIN ESQUEMA'),
        })

    return {
        'planta': {'id': planta.id, 'codigo': planta.codigo, 'nombre': planta.nombre,
                   'ciudad': planta.ciudad,
                   'tipo_fabricacion': _valor(planta.tipo_fabricacion)},
        'lineas': salida,
        'totales': {
            'lineas': len(lineas),
            'celdas': sum(x['total_celdas'] for x in salida),
            'equipos': sum(x['total_equipos'] for x in salida),
            'lineas_con_esquema': len([x for x in salida if x['tiene_esquema']]),
            'ordenes_abiertas': sum(x['ordenes_abiertas'] for x in salida),
            'produccion_en_curso': sum(x['cantidad_producida'] for x in salida),
        },
    }
