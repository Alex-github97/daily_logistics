"""
El recorrido de una línea y los totales de una orden, en un solo sitio.

POR QUÉ EXISTE ESTE ARCHIVO
Porque `orden.cantidad_producida` y `orden.cantidad_scrap` tenían dos dueños que
se pisaban:

  - El terminal de planta (`/mes/planta/avance`) los REEMPLAZABA con el avance
    de la última estación.
  - El cierre de una ejecución (`/mes/ejecuciones/{id}/cerrar`) los ACUMULABA
    con `+=`.

Con las dos vías en uso, el que escribía último ganaba: cerrar una ejecución
sumaba scrap encima del total de las estaciones —contándolo dos veces— y el
siguiente reporte de una estación borraba lo que había sumado la ejecución. La
tasa de scrap del tablero sale de ese campo, así que el número que se mira para
decidir era el resultado de una carrera.

LA REGLA
Los totales de la orden son **derivados**: no los acumula nadie, se recalculan
desde donde de verdad está el dato. Y hay dos fuentes según cómo se produzca:

  - **Con esquema de línea** —la línea tiene estaciones y hay avances— lo
    producido es lo que entregó la ÚLTIMA estación. No la suma de todas: una
    pieza que pasa por cinco máquinas contaría cinco veces y el cumplimiento
    saldría al 500%.
  - **Sin esquema** lo producido es la suma de las ejecuciones cerradas.

El scrap, en cambio, siempre es una SUMA: cada pérdida ocurre una sola vez y en
un solo lugar. Y su libro es `mes_scrap`, que es donde queda la causa y el
costo; el `cantidad_scrap` de cada estación se conserva porque es lo que sostiene
la regla de «una estación no puede procesar más de lo que le entregaron».
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.mes import (
    MESAvanceEstacion, MESEjecucion, MESFlujoConexion, MESFlujoNodo,
    MESOrdenProduccion, MESScrap, EstadoEjecucionMESEnum,
)


def valor(x: Any) -> Any:
    """El valor de un enum, o el dato tal cual si ya es texto."""
    return x.value if hasattr(x, "value") else x


def ahora() -> datetime:
    return datetime.now(timezone.utc)


# ─── Ordenar las estaciones como las recorre el material ──────────────────────

def ordenar_estaciones(nodos: List[MESFlujoNodo],
                       conexiones: List[MESFlujoConexion]) -> List[MESFlujoNodo]:
    """Pone las estaciones en el orden en que el material las atraviesa.

    Es un orden topológico: primero lo que no depende de nada —las entradas de
    material—, después lo que solo depende de eso, y así. No se usa la posición
    en el lienzo porque el dibujo puede estar acomodado de cualquier forma y una
    línea que se devuelve para reproceso quedaría al revés.

    Los ciclos —que existen: un reproceso devuelve material a una etapa
    anterior— romperían un orden topológico estricto, así que lo que queda sin
    resolver se agrega al final por su posición horizontal. Es una salida
    deliberada: mejor mostrar todas las estaciones en un orden aproximado que
    esconder las que participan en un ciclo.
    """
    # Los retrabajos y el scrap no marcan el avance del material hacia adelante.
    hacia_adelante = [c for c in conexiones
                      if valor(c.tipo) in ("NORMAL", "ALTERNA")]
    entrantes: Dict[int, set] = {n.id: set() for n in nodos}
    for c in hacia_adelante:
        if c.destino_id in entrantes and c.origen_id in entrantes:
            entrantes[c.destino_id].add(c.origen_id)

    por_id = {n.id: n for n in nodos}
    listos = sorted([n for n in nodos if not entrantes[n.id]],
                    key=lambda n: (n.pos_x, n.pos_y))
    orden: List[MESFlujoNodo] = []
    vistos: set = set()

    while listos:
        actual = listos.pop(0)
        if actual.id in vistos:
            continue
        vistos.add(actual.id)
        orden.append(actual)
        siguientes = sorted(
            [por_id[c.destino_id] for c in hacia_adelante
             if c.origen_id == actual.id and c.destino_id in por_id],
            key=lambda n: (n.pos_x, n.pos_y))
        for s in siguientes:
            if s.id in vistos:
                continue
            entrantes[s.id].discard(actual.id)
            if not entrantes[s.id]:
                listos.append(s)

    faltantes = sorted([n for n in nodos if n.id not in vistos],
                       key=lambda n: (n.pos_x, n.pos_y))
    return orden + faltantes


def predecesores(nodo_id: int, conexiones: List[MESFlujoConexion]) -> List[int]:
    return [c.origen_id for c in conexiones
            if c.destino_id == nodo_id and valor(c.tipo) in ("NORMAL", "ALTERNA")]


# ─── Los totales de la orden ──────────────────────────────────────────────────

async def recalcular_totales_orden(db: AsyncSession,
                                   orden: MESOrdenProduccion) -> Dict[str, float]:
    """Recalcula lo producido y el scrap de la orden desde sus fuentes.

    No hace commit: lo deja en la sesión para que la operación que la llamó
    cierre su propia transacción. Devuelve los dos números y de dónde salieron,
    que es lo que necesita mostrar quien reporta.
    """
    producido = 0.0
    fuente = "ejecuciones"

    avances = list((await db.execute(
        select(MESAvanceEstacion).where(
            MESAvanceEstacion.orden_id == orden.id))).scalars().all())

    if avances and orden.linea_id:
        nodos = list((await db.execute(
            select(MESFlujoNodo).where(
                MESFlujoNodo.linea_id == orden.linea_id,
                MESFlujoNodo.activo.is_(True)))).scalars().all())
        conexiones = list((await db.execute(
            select(MESFlujoConexion).where(
                MESFlujoConexion.linea_id == orden.linea_id))).scalars().all())
        ordenadas = ordenar_estaciones(nodos, conexiones)
        if ordenadas:
            ultimo = ordenadas[-1]
            por_nodo = {a.nodo_id: a for a in avances}
            # Si la última estación todavía no ha reportado, lo producido de la
            # orden es cero y no el avance de una estación intermedia: hasta que
            # no sale por el final de la línea, no hay producto terminado.
            producido = (por_nodo[ultimo.id].cantidad_producida or 0.0) \
                if ultimo.id in por_nodo else 0.0
            fuente = "estaciones"

    if fuente == "ejecuciones":
        producido = float(await db.scalar(
            select(func.coalesce(func.sum(MESEjecucion.cantidad_producida), 0.0))
            .where(MESEjecucion.orden_id == orden.id,
                   MESEjecucion.estado == EstadoEjecucionMESEnum.COMPLETADA)) or 0.0)

    # El scrap sale de su libro, no de los contadores de cada vía: es donde
    # queda la causa y el costo, y es lo que muestra la pantalla de Scrap.
    scrap = float(await db.scalar(
        select(func.coalesce(func.sum(MESScrap.cantidad), 0.0))
        .where(MESScrap.orden_id == orden.id)) or 0.0)

    orden.cantidad_producida = round(producido, 4)
    orden.cantidad_scrap = round(scrap, 4)
    return {"cantidad_producida": orden.cantidad_producida,
            "cantidad_scrap": orden.cantidad_scrap,
            "fuente_producido": fuente}


def registrar_scrap(db: AsyncSession, *, orden_id: int, producto_id: int,
                    cantidad: float, causa: str,
                    operario_id: Optional[int] = None,
                    es_reprocesable: bool = False,
                    observaciones: Optional[str] = None) -> Optional[MESScrap]:
    """Anota una pérdida en el libro de scrap.

    Lo usan todas las vías que reportan pérdida —el terminal de planta y el
    cierre de una ejecución— para que la pantalla de Scrap muestre todo lo que
    se perdió y no solo lo que alguien registró a mano. Antes el terminal
    guardaba el scrap en su propio contador y la pantalla de Scrap no se
    enteraba: dos cifras distintas de lo mismo.
    """
    if not cantidad or cantidad <= 0:
        return None
    obj = MESScrap(orden_id=orden_id, producto_id=producto_id,
                   operario_id=operario_id, causa=causa[:200],
                   cantidad=round(cantidad, 4), fecha_registro=ahora(),
                   es_reprocesable=es_reprocesable, observaciones=observaciones)
    db.add(obj)
    return obj
