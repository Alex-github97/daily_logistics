"""
Indicadores del WMS: el catálogo con la ficha de cada uno y su cálculo.

Cada indicador declara qué mide, con qué fórmula, de qué datos sale, cómo se
calcula paso a paso, hacia dónde es mejor y una meta sugerida (editable por
almacén). El cálculo devuelve el valor, el numerador y el denominador, el
detalle (los registros detrás del número) y los avisos de calidad de datos:
cuántos registros quedaron por fuera y por qué. Un indicador sin sus avisos
puede verse bien y estar midiendo la mitad de la operación.

Los periodos son días de Bogotá: la medianoche local son las 05:00 UTC.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean
from typing import Callable, Dict, List, Optional

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.wms import (
    WMSConteoDetalle, WMSConteoInventario, WMSDespacho, WMSDespachoDetalle, WMSDevolucion, WMSDevolucionDetalle,
    WMSEventoTrazabilidad, WMSHistorialEstado, WMSInventarioUbicacion, WMSLote, WMSMovimientoInventario,
    WMSOrdenCompra, WMSOrdenCompraDetalle, WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSPickingDetalle,
    WMSPickingTarea, WMSProducto, WMSRecepcion, WMSRecepcionDetalle, WMSTarea, WMSUbicacion, WMSZona,
)

M = WMSMovimientoInventario


@dataclass
class Ficha:
    clave: str
    nombre: str
    categoria: str
    unidad: str                 # "%", "h", "min", "días", "veces/año", "líneas/h", "tareas/h"
    sentido: str                # "mayor" (más es mejor) o "menor"
    meta: float
    definicion: str
    formula: str
    fuente: str
    como: List[str]
    referencia: str = ""
    especializado: bool = False
    instantaneo: bool = False   # se mide sobre el estado actual, no sobre el periodo


@dataclass
class Ctx:
    desde: date
    hasta: date
    almacen_id: Optional[int] = None
    depositante_id: Optional[int] = None

    @property
    def ini(self) -> datetime:
        return datetime.combine(self.desde, time.min, timezone.utc) + timedelta(hours=5)

    @property
    def fin(self) -> datetime:
        return datetime.combine(self.hasta + timedelta(days=1), time.min, timezone.utc) + timedelta(hours=5)

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1


@dataclass
class Resultado:
    valor: Optional[float]
    numerador: Optional[float] = None
    denominador: Optional[float] = None
    muestras: int = 0
    detalle: List[dict] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)


def _pct(n, d) -> Optional[float]:
    return round(n / d * 100, 2) if d else None


def _h(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if not a or not b:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return (b - a).total_seconds() / 3600


def _iso(v):
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else v


# ════════════════════════════════════════════════════════════════════════════
#  RECEPCIÓN
# ════════════════════════════════════════════════════════════════════════════

async def _recepciones(db, ctx: Ctx):
    q = select(WMSRecepcion).where(WMSRecepcion.deleted_at.is_(None), WMSRecepcion.estado == "COMPLETA",
                                   func.coalesce(WMSRecepcion.completada_en, WMSRecepcion.updated_at) >= ctx.ini,
                                   func.coalesce(WMSRecepcion.completada_en, WMSRecepcion.updated_at) < ctx.fin)
    if ctx.almacen_id:
        q = q.where(WMSRecepcion.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSRecepcion.depositante_id == ctx.depositante_id)
    return (await db.execute(q)).scalars().all()


async def dock_to_stock(db, ctx: Ctx) -> Resultado:
    recs = await _recepciones(db, ctx)
    ids = [r.id for r in recs]
    tareas = defaultdict(list)
    for t in (await db.execute(select(WMSTarea).where(WMSTarea.documento_tipo == "RECEPCION",
                                                      WMSTarea.documento_id.in_(ids or [0])))).scalars():
        tareas[t.documento_id].append(t)
    horas, detalle, sin_llegada, sin_ubicar = [], [], 0, 0
    for r in recs:
        if not r.fecha_llegada:
            sin_llegada += 1
            continue
        ts = tareas.get(r.id, [])
        if ts and any(t.estado in ("PENDIENTE", "EN_CURSO") for t in ts):
            sin_ubicar += 1
            continue
        hechas = [t.terminada_en for t in ts if t.estado == "COMPLETADA" and t.terminada_en]
        fin = max(hechas) if hechas else r.completada_en
        h = _h(r.fecha_llegada, fin)
        if h is None:
            sin_llegada += 1
            continue
        horas.append(h)
        detalle.append({"recepcion": r.numero_recepcion, "llegada": _iso(r.fecha_llegada), "disponible": _iso(fin),
                        "horas": round(h, 2), "ubicacion_dirigida": bool(ts)})
    avisos = []
    if sin_llegada:
        avisos.append(f"{sin_llegada} recepciones sin hora de llegada no se cuentan (registradas antes de que se tomara).")
    if sin_ubicar:
        avisos.append(f"{sin_ubicar} recepciones tienen estibas sin ubicar todavía: entran cuando se terminen sus tareas.")
    return Resultado(round(mean(horas), 2) if horas else None, sum(horas), len(horas), len(horas),
                     sorted(detalle, key=lambda d: -d["horas"]), avisos)


async def tiempo_descargue(db, ctx: Ctx) -> Resultado:
    recs = await _recepciones(db, ctx)
    mins, detalle = [], []
    for r in recs:
        h = _h(r.inicio_descargue, r.fin_descargue)
        if h is not None and h >= 0:
            mins.append(h * 60)
            detalle.append({"recepcion": r.numero_recepcion, "muelle": r.muelle, "minutos": round(h * 60, 1)})
    faltan = len(recs) - len(mins)
    return Resultado(round(mean(mins), 1) if mins else None, sum(mins), len(mins), len(mins),
                     sorted(detalle, key=lambda d: -d["minutos"]),
                     [f"{faltan} recepciones sin inicio de descargue registrado no se cuentan."] if faltan else [])


async def recepcion_a_tiempo(db, ctx: Ctx) -> Resultado:
    recs = [r for r in await _recepciones(db, ctx) if r.orden_compra_id]
    ocs = {o.id: o for o in (await db.execute(select(WMSOrdenCompra).where(
        WMSOrdenCompra.id.in_([r.orden_compra_id for r in recs] or [0])))).scalars()}
    a_tiempo, base, detalle, sin_fecha = 0, 0, [], 0
    for r in recs:
        oc = ocs.get(r.orden_compra_id)
        if not oc or not oc.fecha_esperada:
            sin_fecha += 1
            continue
        base += 1
        ok = r.fecha_recepcion <= oc.fecha_esperada
        a_tiempo += ok
        detalle.append({"recepcion": r.numero_recepcion, "orden_compra": oc.numero_oc, "esperada": _iso(oc.fecha_esperada),
                        "recibida": _iso(r.fecha_recepcion), "a_tiempo": ok,
                        "dias_tarde": max(0, (r.fecha_recepcion - oc.fecha_esperada).days)})
    return Resultado(_pct(a_tiempo, base), a_tiempo, base, base, sorted(detalle, key=lambda d: -d["dias_tarde"]),
                     [f"{sin_fecha} recepciones contra una OC sin fecha esperada no se cuentan."] if sin_fecha else [])


async def exactitud_recepcion(db, ctx: Ctx) -> Resultado:
    recs = {r.id: r for r in await _recepciones(db, ctx)}
    dets = (await db.execute(select(WMSRecepcionDetalle).where(WMSRecepcionDetalle.recepcion_id.in_(list(recs) or [0])))).scalars().all()
    con = [d for d in dets if d.cantidad_esperada is not None]
    bien = [d for d in con if abs((d.cantidad_recibida or 0) - d.cantidad_esperada) < 1e-9]
    detalle = [{"recepcion": recs[d.recepcion_id].numero_recepcion, "producto_id": d.producto_id,
                "esperada": d.cantidad_esperada, "recibida": d.cantidad_recibida,
                "diferencia": round((d.cantidad_recibida or 0) - d.cantidad_esperada, 3)} for d in con if d not in bien]
    sin = len(dets) - len(con)
    return Resultado(_pct(len(bien), len(con)), len(bien), len(con), len(con), detalle,
                     [f"{sin} líneas sin cantidad esperada (recepción ciega) no se cuentan."] if sin else [])


async def fill_rate_proveedor(db, ctx: Ctx) -> Resultado:
    q = select(WMSOrdenCompra).where(WMSOrdenCompra.deleted_at.is_(None), WMSOrdenCompra.estado != "CANCELADA",
                                     WMSOrdenCompra.fecha_esperada >= ctx.desde, WMSOrdenCompra.fecha_esperada <= ctx.hasta)
    if ctx.almacen_id:
        q = q.where(WMSOrdenCompra.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSOrdenCompra.depositante_id == ctx.depositante_id)
    ocs = {o.id: o for o in (await db.execute(q)).scalars()}
    dets = (await db.execute(select(WMSOrdenCompraDetalle).where(WMSOrdenCompraDetalle.orden_id.in_(list(ocs) or [0])))).scalars().all()
    pedido = sum(d.cantidad_solicitada or 0 for d in dets)
    recibido = sum(min(d.cantidad_recibida or 0, d.cantidad_solicitada or 0) for d in dets)
    detalle = [{"orden_compra": ocs[d.orden_id].numero_oc, "producto_id": d.producto_id, "pedido": d.cantidad_solicitada,
                "recibido": d.cantidad_recibida} for d in dets if (d.cantidad_recibida or 0) < (d.cantidad_solicitada or 0)]
    return Resultado(_pct(recibido, pedido), recibido, pedido, len(dets), detalle)


# ════════════════════════════════════════════════════════════════════════════
#  TAREAS DE BODEGA
# ════════════════════════════════════════════════════════════════════════════

async def _tareas(db, ctx: Ctx, tipo="UBICACION"):
    q = select(WMSTarea).where(WMSTarea.tipo == tipo, WMSTarea.estado == "COMPLETADA",
                               WMSTarea.terminada_en >= ctx.ini, WMSTarea.terminada_en < ctx.fin)
    if ctx.almacen_id:
        q = q.where(WMSTarea.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSTarea.depositante_id == ctx.depositante_id)
    return (await db.execute(q)).scalars().all()


async def ubicacion_sugerida_cumplida(db, ctx: Ctx) -> Resultado:
    ts = [t for t in await _tareas(db, ctx) if t.ubicacion_sugerida_id]
    cumplidas = [t for t in ts if t.ubicacion_destino_id == t.ubicacion_sugerida_id]
    detalle = [{"tarea": t.id, "motivo": t.motivo_desvio, "sugerida_id": t.ubicacion_sugerida_id,
                "destino_id": t.ubicacion_destino_id} for t in ts if t not in cumplidas]
    return Resultado(_pct(len(cumplidas), len(ts)), len(cumplidas), len(ts), len(ts), detalle)


async def espera_tareas(db, ctx: Ctx) -> Resultado:
    ts = await _tareas(db, ctx)
    mins = [(t.id, _h(t.created_at, t.iniciada_en) * 60) for t in ts if t.iniciada_en]
    return Resultado(round(mean(m for _, m in mins), 1) if mins else None, sum(m for _, m in mins), len(mins), len(mins),
                     [{"tarea": i, "minutos": round(m, 1)} for i, m in sorted(mins, key=lambda x: -x[1])])


async def productividad_ubicacion(db, ctx: Ctx) -> Resultado:
    ts = await _tareas(db, ctx)
    con = [(t, _h(t.iniciada_en, t.terminada_en)) for t in ts if t.iniciada_en and t.terminada_en]
    horas = sum(h for _, h in con if h and h > 0)
    return Resultado(round(len(con) / horas, 2) if horas else None, len(con), round(horas, 3), len(con),
                     [{"tarea": t.id, "minutos": round(h * 60, 1)} for t, h in con])


# ════════════════════════════════════════════════════════════════════════════
#  INVENTARIO
# ════════════════════════════════════════════════════════════════════════════

async def _conteos(db, ctx: Ctx):
    q = (select(WMSConteoDetalle, WMSConteoInventario)
         .join(WMSConteoInventario, WMSConteoInventario.id == WMSConteoDetalle.conteo_id)
         .where(WMSConteoDetalle.cantidad_fisica.isnot(None),
                WMSConteoInventario.fecha_programada >= ctx.desde, WMSConteoInventario.fecha_programada <= ctx.hasta))
    if ctx.almacen_id:
        q = q.where(WMSConteoInventario.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.join(WMSProducto, WMSProducto.id == WMSConteoDetalle.producto_id).where(WMSProducto.depositante_id == ctx.depositante_id)
    return (await db.execute(q)).all()


async def exactitud_inventario(db, ctx: Ctx) -> Resultado:
    filas = await _conteos(db, ctx)
    bien = [d for d, _c in filas if abs(d.diferencia or 0) < 1e-9]
    detalle = [{"conteo": c.id, "producto_id": d.producto_id, "ubicacion_id": d.ubicacion_id, "sistema": d.cantidad_sistema,
                "fisico": d.cantidad_fisica, "diferencia": d.diferencia} for d, c in filas if abs(d.diferencia or 0) >= 1e-9]
    return Resultado(_pct(len(bien), len(filas)), len(bien), len(filas), len(filas), detalle,
                     [] if filas else ["No hubo conteos en el periodo: sin conteos no se sabe qué tan exacto es el inventario."])


async def _costos(db, ids) -> dict:
    ids = set(ids)
    return {p: float(c or 0) for p, c in (await db.execute(select(WMSProducto.id, WMSProducto.costo_promedio)
                                                          .where(WMSProducto.id.in_(ids or {0})))).all()}


async def exactitud_valor(db, ctx: Ctx) -> Resultado:
    filas = await _conteos(db, ctx)
    costo = await _costos(db, [d.producto_id for d, _ in filas])
    sistema = sum((d.cantidad_sistema or 0) * costo.get(d.producto_id, 0) for d, _ in filas)
    error = sum(abs(d.diferencia or 0) * costo.get(d.producto_id, 0) for d, _ in filas)
    avisos = [] if sistema else ["Sin conteos valorizables en el periodo (o productos sin costo)."]
    return Resultado(round((1 - error / sistema) * 100, 2) if sistema else None, round(sistema - error, 2), round(sistema, 2),
                     len(filas), [], avisos)


async def _salidas_valor(db, ctx: Ctx, tipos=("DESPACHO",)) -> float:
    q = select(func.coalesce(func.sum(M.cantidad * func.coalesce(M.costo_unitario, WMSProducto.costo_promedio)), 0)) \
        .join(WMSProducto, WMSProducto.id == M.producto_id) \
        .where(M.tipo.in_(tipos), M.ubicacion_destino_id.is_(None), M.created_at >= ctx.ini, M.created_at < ctx.fin)
    if ctx.almacen_id:
        q = q.where(M.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(M.depositante_id == ctx.depositante_id)
    return float((await db.execute(q)).scalar() or 0)


async def merma(db, ctx: Ctx) -> Resultado:
    perdido = await _salidas_valor(db, ctx, ("AJUSTE", "CONTEO"))
    vendido = await _salidas_valor(db, ctx)
    return Resultado(_pct(perdido, vendido), round(perdido, 2), round(vendido, 2), 0, [],
                     [] if vendido else ["Sin salidas valorizadas en el periodo."])


async def _valor_en(db, ctx: Ctx, momento: datetime) -> float:
    """Valor del inventario en un momento: la existencia actual menos lo que
    entró y más lo que salió después (kárdex), al costo promedio vigente."""
    q = select(WMSInventarioUbicacion.producto_id, func.sum(
        WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada
        + WMSInventarioUbicacion.cantidad_bloqueada))
    if ctx.almacen_id:
        q = q.join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id) \
             .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(WMSZona.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.join(WMSProducto, WMSProducto.id == WMSInventarioUbicacion.producto_id) \
             .where(WMSProducto.depositante_id == ctx.depositante_id)
    hoy = dict((p, float(c or 0)) for p, c in (await db.execute(q.group_by(WMSInventarioUbicacion.producto_id))).all())
    # Entradas suman, salidas restan; traslados y cambios de estado no cambian el total.
    signo = func.coalesce(func.sum(case((M.ubicacion_origen_id.is_(None), M.cantidad), else_=0)
                                   - case((M.ubicacion_destino_id.is_(None), M.cantidad), else_=0)), 0)
    mq = select(M.producto_id, signo).where(M.created_at >= momento)
    if ctx.almacen_id:
        mq = mq.where(M.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        mq = mq.where(M.depositante_id == ctx.depositante_id)
    despues = dict((p, float(v or 0)) for p, v in (await db.execute(mq.group_by(M.producto_id))).all())
    ids = set(hoy) | set(despues)
    costo = await _costos(db, ids)
    return sum(max(0.0, hoy.get(p, 0) - despues.get(p, 0)) * costo.get(p, 0) for p in ids)


async def _inventario_promedio(db, ctx: Ctx) -> float:
    return (await _valor_en(db, ctx, ctx.ini) + await _valor_en(db, ctx, ctx.fin)) / 2


async def rotacion(db, ctx: Ctx) -> Resultado:
    costo_ventas = await _salidas_valor(db, ctx)
    promedio = await _inventario_promedio(db, ctx)
    anual = costo_ventas * 365 / ctx.dias
    return Resultado(round(anual / promedio, 2) if promedio else None, round(anual, 2), round(promedio, 2), 0, [],
                     [] if promedio else ["Sin inventario valorizado en el periodo."])


async def dias_inventario(db, ctx: Ctx) -> Resultado:
    costo_ventas = await _salidas_valor(db, ctx)
    promedio = await _inventario_promedio(db, ctx)
    diario = costo_ventas / ctx.dias
    return Resultado(round(promedio / diario, 1) if diario else None, round(promedio, 2), round(diario, 2), 0, [],
                     [] if diario else ["Sin salidas en el periodo: el inventario no se está consumiendo."])


async def _stock_actual(db, ctx: Ctx):
    total = WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada \
        + WMSInventarioUbicacion.cantidad_bloqueada
    q = select(WMSInventarioUbicacion.producto_id, WMSInventarioUbicacion.lote_id, func.sum(total)).where(total > 0)
    if ctx.almacen_id:
        q = q.join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id) \
             .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(WMSZona.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.join(WMSProducto, WMSProducto.id == WMSInventarioUbicacion.producto_id) \
             .where(WMSProducto.depositante_id == ctx.depositante_id)
    return (await db.execute(q.group_by(WMSInventarioUbicacion.producto_id, WMSInventarioUbicacion.lote_id))).all()


async def sin_movimiento(db, ctx: Ctx) -> Resultado:
    filas = await _stock_actual(db, ctx)
    por_prod = defaultdict(float)
    for p, _l, q in filas:
        por_prod[p] += float(q)
    corte = datetime.now(timezone.utc) - timedelta(days=90)
    ultima = dict((await db.execute(select(M.producto_id, func.max(M.created_at)).where(
        M.producto_id.in_(list(por_prod) or [0]), M.tipo == "DESPACHO", M.ubicacion_destino_id.is_(None))
        .group_by(M.producto_id))).all())
    costo = await _costos(db, por_prod)
    quietos = [p for p in por_prod if not ultima.get(p) or ultima[p] < corte]
    valor_total = sum(q * costo.get(p, 0) for p, q in por_prod.items())
    valor_quieto = sum(por_prod[p] * costo.get(p, 0) for p in quietos)
    detalle = [{"producto_id": p, "unidades": por_prod[p], "valor": round(por_prod[p] * costo.get(p, 0), 2),
                "ultima_salida": _iso(ultima.get(p))} for p in quietos]
    return Resultado(_pct(len(quietos), len(por_prod)), len(quietos), len(por_prod), len(por_prod),
                     sorted(detalle, key=lambda d: -d["valor"]),
                     [f"Valor sin movimiento: {valor_quieto:,.0f} de {valor_total:,.0f} ({_pct(valor_quieto, valor_total) or 0}%)."])


async def inventario_vencido(db, ctx: Ctx) -> Resultado:
    filas = await _stock_actual(db, ctx)
    lotes = {l.id: l for l in (await db.execute(select(WMSLote).where(
        WMSLote.id.in_({l for _p, l, _q in filas if l} or {0})))).scalars()}
    hoy = date.today()
    total = sum(float(q) for *_x, q in filas)
    vencido = [(p, l, float(q)) for p, l, q in filas if l and lotes.get(l) and lotes[l].fecha_vencimiento
               and lotes[l].fecha_vencimiento < hoy]
    unidades = sum(q for *_x, q in vencido)
    return Resultado(_pct(unidades, total), unidades, total, len(filas),
                     [{"producto_id": p, "lote": lotes[l].numero_lote, "vencio": _iso(lotes[l].fecha_vencimiento),
                       "unidades": q} for p, l, q in vencido])


async def utilizacion_cubica(db, ctx: Ctx) -> Resultado:
    from app.api.v1.endpoints.wms_cubicaje import ocupacion
    ubic = [u for u in await ocupacion(db, ctx.almacen_id) if u["zona_tipo"] not in ("RECEPCION", "DESPACHO", "TRANSITO")]
    cap = sum(u["capacidad_m3"] or 0 for u in ubic)
    ocu = sum(u["ocupado_m3"] for u in ubic)
    sin = sum(1 for u in ubic if not u["capacidad_m3"])
    sin_vol = sum(u["unidades_sin_volumen"] for u in ubic)
    avisos = []
    if sin:
        avisos.append(f"{sin} ubicaciones sin medidas no suman capacidad.")
    if sin_vol:
        avisos.append(f"{sin_vol:,.0f} unidades de productos sin cubicar no suman volumen: el indicador queda por debajo de la realidad.")
    llenas = [u["codigo"] for u in ubic if (u["ocupacion_pct"] or 0) > 100]
    if llenas:
        avisos.append(f"{len(llenas)} ubicaciones tienen más volumen que su capacidad ({', '.join(llenas[:5])}"
                      f"{'…' if len(llenas) > 5 else ''}): revise sus medidas o las del producto.")
    return Resultado(_pct(ocu, cap), round(ocu, 3), round(cap, 3), len(ubic),
                     sorted([{"ubicacion": u["codigo"], "ocupacion_pct": u["ocupacion_pct"]} for u in ubic if u["capacidad_m3"]],
                            key=lambda d: -(d["ocupacion_pct"] or 0)), avisos)


async def ocupacion_posiciones(db, ctx: Ctx) -> Resultado:
    from app.api.v1.endpoints.wms_cubicaje import ocupacion
    ubic = [u for u in await ocupacion(db, ctx.almacen_id) if u["zona_tipo"] not in ("RECEPCION", "DESPACHO", "TRANSITO")]
    llenas = [u for u in ubic if u["unidades"] > 0]
    return Resultado(_pct(len(llenas), len(ubic)), len(llenas), len(ubic), len(ubic))


# ════════════════════════════════════════════════════════════════════════════
#  ALISTAMIENTO Y DESPACHO
# ════════════════════════════════════════════════════════════════════════════

async def _lineas_alistadas(db, ctx: Ctx):
    q = (select(WMSPickingDetalle, WMSPickingTarea, WMSOrdenSalida)
         .join(WMSPickingTarea, WMSPickingTarea.id == WMSPickingDetalle.tarea_id)
         .join(WMSOrdenSalida, WMSOrdenSalida.id == WMSPickingTarea.orden_id)
         .where(WMSPickingDetalle.confirmado.is_(True), WMSPickingDetalle.timestamp_confirmacion >= ctx.ini,
                WMSPickingDetalle.timestamp_confirmacion < ctx.fin))
    if ctx.almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSOrdenSalida.depositante_id == ctx.depositante_id)
    return (await db.execute(q)).all()


async def lineas_completas(db, ctx: Ctx) -> Resultado:
    filas = await _lineas_alistadas(db, ctx)
    bien = [d for d, _t, _o in filas if abs(d.cantidad_pickeada - d.cantidad_solicitada) < 1e-9]
    detalle = [{"orden": o.numero_orden, "tarea": t.id, "producto_id": d.producto_id, "pedido": d.cantidad_solicitada,
                "alistado": d.cantidad_pickeada} for d, t, o in filas if d not in bien]
    return Resultado(_pct(len(bien), len(filas)), len(bien), len(filas), len(filas), detalle)


async def alistamiento_verificado(db, ctx: Ctx) -> Resultado:
    q = select(WMSEventoTrazabilidad).where(WMSEventoTrazabilidad.tipo_evento == "PICKING_CONFIRMADO",
                                            WMSEventoTrazabilidad.created_at >= ctx.ini,
                                            WMSEventoTrazabilidad.created_at < ctx.fin)
    evs = (await db.execute(q)).scalars().all()
    si = [e for e in evs if (e.datos_adicionales or {}).get("verificado")]
    return Resultado(_pct(len(si), len(evs)), len(si), len(evs), len(evs), [],
                     [] if evs else ["Sin confirmaciones de alistamiento registradas en el periodo."])


async def productividad_picking(db, ctx: Ctx) -> Resultado:
    q = (select(WMSPickingTarea).join(WMSOrdenSalida, WMSOrdenSalida.id == WMSPickingTarea.orden_id)
         .where(WMSPickingTarea.estado == "COMPLETADA", WMSPickingTarea.fecha_fin >= ctx.ini, WMSPickingTarea.fecha_fin < ctx.fin))
    if ctx.almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSOrdenSalida.depositante_id == ctx.depositante_id)
    tareas = (await db.execute(q)).scalars().all()
    lineas = dict((await db.execute(select(WMSPickingDetalle.tarea_id, func.count()).where(
        WMSPickingDetalle.tarea_id.in_([t.id for t in tareas] or [0]), WMSPickingDetalle.confirmado.is_(True))
        .group_by(WMSPickingDetalle.tarea_id))).all())
    con = [(t, _h(t.fecha_inicio, t.fecha_fin)) for t in tareas if t.fecha_inicio and t.fecha_fin]
    horas = sum(h for _, h in con if h and h > 0)
    n = sum(lineas.get(t.id, 0) for t, h in con if h and h > 0)
    sin = len(tareas) - len(con)
    return Resultado(round(n / horas, 1) if horas else None, n, round(horas, 3), len(con),
                     [{"tarea": t.id, "lineas": lineas.get(t.id, 0), "minutos": round(h * 60, 1)} for t, h in con],
                     [f"{sin} tareas sin hora de inicio no se cuentan."] if sin else [])


async def _ordenes_despachadas(db, ctx: Ctx):
    """Órdenes cuyo PRIMER despacho cae en el periodo, con sus despachos."""
    q = select(WMSOrdenSalida).where(WMSOrdenSalida.deleted_at.is_(None))
    if ctx.almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSOrdenSalida.depositante_id == ctx.depositante_id)
    primeros = (select(WMSDespacho.orden_id, func.min(WMSDespacho.created_at).label("primero"))
                .where(WMSDespacho.deleted_at.is_(None)).group_by(WMSDespacho.orden_id).subquery())
    q = q.join(primeros, primeros.c.orden_id == WMSOrdenSalida.id).where(primeros.c.primero >= ctx.ini, primeros.c.primero < ctx.fin)
    ordenes = (await db.execute(q)).scalars().all()
    desp = defaultdict(list)
    for d in (await db.execute(select(WMSDespacho).where(WMSDespacho.orden_id.in_([o.id for o in ordenes] or [0]),
                                                        WMSDespacho.deleted_at.is_(None)))).scalars():
        desp[d.orden_id].append(d)
    return ordenes, desp


async def ciclo_orden(db, ctx: Ctx) -> Resultado:
    ordenes, desp = await _ordenes_despachadas(db, ctx)
    horas = [(o, _h(o.created_at, min(d.created_at for d in desp[o.id]))) for o in ordenes if desp[o.id]]
    horas = [(o, h) for o, h in horas if h is not None and h >= 0]
    return Resultado(round(mean(h for _, h in horas), 2) if horas else None, sum(h for _, h in horas), len(horas), len(horas),
                     sorted([{"orden": o.numero_orden, "horas": round(h, 2)} for o, h in horas], key=lambda d: -d["horas"]))


async def despacho_a_tiempo(db, ctx: Ctx) -> Resultado:
    ordenes, desp = await _ordenes_despachadas(db, ctx)
    con = [o for o in ordenes if o.fecha_requerida]
    detalle, ok = [], 0
    for o in con:
        f = min(d.fecha_despacho for d in desp[o.id])
        a_tiempo = f <= o.fecha_requerida
        ok += a_tiempo
        detalle.append({"orden": o.numero_orden, "requerida": _iso(o.fecha_requerida), "despachada": _iso(f), "a_tiempo": a_tiempo})
    sin = len(ordenes) - len(con)
    return Resultado(_pct(ok, len(con)), ok, len(con), len(con), [d for d in detalle if not d["a_tiempo"]],
                     [f"{sin} órdenes sin fecha requerida no se cuentan."] if sin else [])


async def _ordenes_entregadas(db, ctx: Ctx):
    """Órdenes ENTREGADAS cuya última entrega cae en el periodo."""
    ult = (select(WMSDespacho.orden_id, func.max(WMSDespacho.fecha_entrega_real).label("ultima"))
           .where(WMSDespacho.deleted_at.is_(None), WMSDespacho.fecha_entrega_real.isnot(None))
           .group_by(WMSDespacho.orden_id).subquery())
    q = (select(WMSOrdenSalida, ult.c.ultima).join(ult, ult.c.orden_id == WMSOrdenSalida.id)
         .where(WMSOrdenSalida.deleted_at.is_(None), WMSOrdenSalida.estado == "ENTREGADO",
                ult.c.ultima >= ctx.desde, ult.c.ultima <= ctx.hasta))
    if ctx.almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSOrdenSalida.depositante_id == ctx.depositante_id)
    filas = (await db.execute(q)).all()
    ids = [o.id for o, _u in filas]
    completas = set(ids) - set((await db.execute(select(WMSOrdenSalidaDetalle.orden_id).where(
        WMSOrdenSalidaDetalle.orden_id.in_(ids or [0]),
        WMSOrdenSalidaDetalle.cantidad_despachada < WMSOrdenSalidaDetalle.cantidad_solicitada))).scalars())
    return filas, completas


async def otif(db, ctx: Ctx) -> Resultado:
    filas, completas = await _ordenes_entregadas(db, ctx)
    con = [(o, u) for o, u in filas if o.fecha_requerida]
    detalle, ok = [], 0
    for o, u in con:
        a_tiempo, completa = u <= o.fecha_requerida, o.id in completas
        ok += a_tiempo and completa
        if not (a_tiempo and completa):
            detalle.append({"orden": o.numero_orden, "requerida": _iso(o.fecha_requerida), "entregada": _iso(u),
                            "a_tiempo": a_tiempo, "completa": completa})
    sin = len(filas) - len(con)
    return Resultado(_pct(ok, len(con)), ok, len(con), len(con), detalle,
                     [f"{sin} órdenes entregadas sin fecha requerida no se cuentan."] if sin else [])


async def orden_perfecta(db, ctx: Ctx) -> Resultado:
    filas, completas = await _ordenes_entregadas(db, ctx)
    con = [(o, u) for o, u in filas if o.fecha_requerida]
    ids = [o.id for o, _ in con]
    devueltas = set((await db.execute(select(WMSDevolucion.orden_referencia_id).where(
        WMSDevolucion.orden_referencia_id.in_(ids or [0])))).scalars())
    desp_orden = dict((await db.execute(select(WMSDespacho.id, WMSDespacho.orden_id).where(
        WMSDespacho.orden_id.in_(ids or [0])))).all())
    con_incidencia = {desp_orden[i] for i in (await db.execute(select(WMSHistorialEstado.entidad_id).where(
        WMSHistorialEstado.entidad_tipo == "DESPACHO", WMSHistorialEstado.estado_nuevo == "INCIDENCIA",
        WMSHistorialEstado.entidad_id.in_(list(desp_orden) or [0])))).scalars()}
    detalle, ok = [], 0
    for o, u in con:
        fallas = [x for x, malo in (("tarde", u > o.fecha_requerida), ("incompleta", o.id not in completas),
                                    ("con devolución", o.id in devueltas), ("con incidencia", o.id in con_incidencia)) if malo]
        ok += not fallas
        if fallas:
            detalle.append({"orden": o.numero_orden, "fallas": ", ".join(fallas)})
    return Resultado(_pct(ok, len(con)), ok, len(con), len(con), detalle)


async def _ordenes_cerradas(db, ctx: Ctx):
    q = select(WMSOrdenSalida).where(WMSOrdenSalida.deleted_at.is_(None), WMSOrdenSalida.estado.in_(("DESPACHADO", "ENTREGADO")),
                                     WMSOrdenSalida.fecha_emision >= ctx.desde, WMSOrdenSalida.fecha_emision <= ctx.hasta)
    if ctx.almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.where(WMSOrdenSalida.depositante_id == ctx.depositante_id)
    ordenes = {o.id: o for o in (await db.execute(q)).scalars()}
    dets = (await db.execute(select(WMSOrdenSalidaDetalle).where(WMSOrdenSalidaDetalle.orden_id.in_(list(ordenes) or [0])))).scalars().all()
    return ordenes, dets


async def fill_rate_lineas(db, ctx: Ctx) -> Resultado:
    ordenes, dets = await _ordenes_cerradas(db, ctx)
    llenas = [d for d in dets if (d.cantidad_despachada or 0) >= d.cantidad_solicitada]
    return Resultado(_pct(len(llenas), len(dets)), len(llenas), len(dets), len(dets),
                     [{"orden": ordenes[d.orden_id].numero_orden, "producto_id": d.producto_id, "pedido": d.cantidad_solicitada,
                       "despachado": d.cantidad_despachada} for d in dets if d not in llenas])


async def fill_rate_unidades(db, ctx: Ctx) -> Resultado:
    _ordenes, dets = await _ordenes_cerradas(db, ctx)
    pedido = sum(d.cantidad_solicitada for d in dets)
    servido = sum(min(d.cantidad_despachada or 0, d.cantidad_solicitada) for d in dets)
    return Resultado(_pct(servido, pedido), servido, pedido, len(dets))


async def tiempo_cargue(db, ctx: Ctx) -> Resultado:
    q = select(WMSDespacho).where(WMSDespacho.deleted_at.is_(None), WMSDespacho.created_at >= ctx.ini, WMSDespacho.created_at < ctx.fin)
    if ctx.almacen_id or ctx.depositante_id:
        q = q.join(WMSOrdenSalida, WMSOrdenSalida.id == WMSDespacho.orden_id)
        if ctx.almacen_id:
            q = q.where(WMSOrdenSalida.almacen_id == ctx.almacen_id)
        if ctx.depositante_id:
            q = q.where(WMSOrdenSalida.depositante_id == ctx.depositante_id)
    ds = (await db.execute(q)).scalars().all()
    mins = [(d, _h(d.inicio_cargue, d.fin_cargue) * 60) for d in ds if d.inicio_cargue and d.fin_cargue]
    sin = len(ds) - len(mins)
    return Resultado(round(mean(m for _, m in mins), 1) if mins else None, sum(m for _, m in mins), len(mins), len(mins),
                     [{"despacho": d.numero_despacho, "muelle": d.muelle, "minutos": round(m, 1)} for d, m in mins],
                     [f"{sin} despachos sin inicio y fin de cargue registrados no se cuentan."] if sin else [])


async def tasa_devolucion(db, ctx: Ctx) -> Resultado:
    q = (select(func.coalesce(func.sum(WMSDevolucionDetalle.cantidad), 0))
         .join(WMSDevolucion, WMSDevolucion.id == WMSDevolucionDetalle.devolucion_id)
         .where(WMSDevolucion.tipo == "CLIENTE", WMSDevolucion.fecha_recepcion >= ctx.desde,
                WMSDevolucion.fecha_recepcion <= ctx.hasta))
    if ctx.almacen_id:
        q = q.where(WMSDevolucion.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        q = q.join(WMSProducto, WMSProducto.id == WMSDevolucionDetalle.producto_id).where(WMSProducto.depositante_id == ctx.depositante_id)
    devuelto = float((await db.execute(q)).scalar() or 0)
    sq = select(func.coalesce(func.sum(M.cantidad), 0)).where(M.tipo == "DESPACHO", M.ubicacion_destino_id.is_(None),
                                                              M.created_at >= ctx.ini, M.created_at < ctx.fin)
    if ctx.almacen_id:
        sq = sq.where(M.almacen_id == ctx.almacen_id)
    if ctx.depositante_id:
        sq = sq.where(M.depositante_id == ctx.depositante_id)
    despachado = float((await db.execute(sq)).scalar() or 0)
    return Resultado(_pct(devuelto, despachado), devuelto, despachado, 0)


# ════════════════════════════════════════════════════════════════════════════
#  CATÁLOGO
# ════════════════════════════════════════════════════════════════════════════

CATALOGO: List[Ficha] = [
    Ficha("dock_to_stock", "De muelle a estantería (dock to stock)", "Recepción", "h", "menor", 8,
          "Cuánto tarda la mercancía, desde que el vehículo llega al muelle, en quedar ubicada y disponible para alistar.",
          "Promedio de (fin de la ubicación − llegada al muelle) por recepción",
          "Recepción: hora de llegada (se toma al registrarla). Fin: la última tarea de ubicación terminada de esa recepción; "
          "si el almacén recibe directo, el cierre de la recepción.",
          ["Se toman las recepciones cerradas en el periodo.",
           "Para cada una: la llegada al muelle y el momento en que la última estiba quedó ubicada.",
           "Se descartan las que tienen estibas sin ubicar (todavía no están disponibles) y las que no tienen hora de llegada.",
           "Se promedian las horas."],
          "Las bodegas de mejor desempeño ubican el mismo día; más de 24 h suele indicar cuellos de botella en el muelle."),
    Ficha("tiempo_descargue", "Tiempo de descargue", "Recepción", "min", "menor", 60,
          "Lo que dura descargar un vehículo en el muelle.", "Promedio de (fin del descargue − inicio del descargue)",
          "Recepción: inicio y fin de descargue registrados.",
          ["Recepciones cerradas en el periodo con inicio y fin de descargue.", "Se promedian los minutos."],
          especializado=True),
    Ficha("recepcion_a_tiempo", "Recepciones a tiempo (proveedor)", "Recepción", "%", "mayor", 95,
          "Qué parte de lo pedido a proveedores llegó en la fecha prometida o antes.",
          "Recepciones con fecha ≤ fecha esperada de su OC ÷ recepciones contra OC con fecha esperada × 100",
          "Recepción (fecha) y orden de compra (fecha esperada).",
          ["Recepciones contra OC cerradas en el periodo.", "Se cuentan las que llegaron a más tardar la fecha esperada.",
           "Las OC sin fecha esperada no se pueden juzgar y quedan por fuera."]),
    Ficha("exactitud_recepcion", "Exactitud de recepción", "Recepción", "%", "mayor", 99,
          "Qué parte de las líneas recibidas coincidió exactamente con lo esperado.",
          "Líneas con recibido = esperado ÷ líneas con cantidad esperada × 100",
          "Detalle de recepción (cantidad esperada y recibida).",
          ["Líneas de las recepciones cerradas en el periodo que traen cantidad esperada.",
           "Una línea está bien si lo recibido es igual a lo esperado.", "Las recepciones ciegas no se cuentan."]),
    Ficha("fill_rate_proveedor", "Cumplimiento del proveedor (unidades)", "Recepción", "%", "mayor", 98,
          "Qué parte de las unidades pedidas a proveedores se recibió.",
          "Σ recibido (hasta lo pedido) ÷ Σ pedido × 100",
          "Órdenes de compra con fecha esperada en el periodo y sus líneas.",
          ["Órdenes de compra no canceladas que se esperaban en el periodo.",
           "Se suma lo recibido, sin pasar de lo pedido en cada línea, y se divide por lo pedido."]),
    Ficha("ubicacion_sugerida_cumplida", "Ubicaciones en la sugerida", "Almacenamiento", "%", "mayor", 90,
          "Qué tanto se sigue la ubicación que sugiere el sistema. Por debajo de la meta, las reglas de ubicación no "
          "reflejan la bodega real: los motivos de desvío dicen qué corregir.",
          "Tareas ubicadas en la sugerida ÷ tareas con sugerencia × 100",
          "Tareas de ubicación terminadas (ubicación sugerida, real y motivo del desvío).",
          ["Tareas de ubicación terminadas en el periodo que tenían sugerencia.",
           "Se cuentan las que terminaron en la ubicación sugerida.", "El detalle muestra los desvíos con su motivo."],
          especializado=True),
    Ficha("espera_tareas", "Espera de las tareas", "Almacenamiento", "min", "menor", 30,
          "Cuánto esperan las tareas antes de que alguien las tome. Mide si hay gente suficiente en el turno.",
          "Promedio de (inicio − creación) de las tareas", "Tareas de ubicación terminadas.",
          ["Tareas terminadas en el periodo que se tomaron explícitamente.", "Se promedian los minutos de espera."],
          especializado=True),
    Ficha("productividad_ubicacion", "Productividad de ubicación", "Productividad", "tareas/h", "mayor", 12,
          "Cuántas estibas o líneas ubica una persona por hora trabajada en ubicar.",
          "Tareas terminadas ÷ horas de ejecución (inicio a fin)", "Tareas de ubicación con inicio y fin.",
          ["Tareas terminadas en el periodo con hora de inicio y de fin.", "Se divide el número de tareas por las horas sumadas."],
          especializado=True),
    Ficha("exactitud_inventario", "Exactitud del inventario (por registro)", "Inventario", "%", "mayor", 99.5,
          "Qué parte de los registros contados (producto, ubicación, lote) coincidió con el sistema.",
          "Registros contados sin diferencia ÷ registros contados × 100",
          "Conteos físicos (sistema tomado al contar y cantidad física).",
          ["Líneas de los conteos programados en el periodo que tienen cantidad física.",
           "El sistema se toma en el momento de contar (no al programar el conteo).",
           "Una línea está bien si no hay diferencia; cualquier diferencia, de más o de menos, cuenta como error."],
          "Es el indicador base de una bodega: sin él, todos los demás se calculan sobre datos dudosos."),
    Ficha("exactitud_valor", "Exactitud del inventario (en valor)", "Inventario", "%", "mayor", 99.5,
          "Lo mismo que la exactitud por registro, pero pesando cada diferencia por su costo.",
          "1 − Σ |diferencia| × costo ÷ Σ sistema × costo, × 100",
          "Conteos físicos y costo promedio de cada producto.",
          ["Mismas líneas de conteo.", "Cada diferencia se valoriza al costo promedio y se suma en valor absoluto.",
           "Se divide por el valor de lo que el sistema decía que había."]),
    Ficha("merma", "Merma (shrinkage)", "Inventario", "%", "menor", 0.5,
          "Valor perdido por faltantes de ajustes y conteos frente al valor que salió por despachos.",
          "Valor de salidas por ajuste y conteo ÷ valor despachado × 100",
          "Kárdex: movimientos de salida tipo AJUSTE y CONTEO, y DESPACHO, a su costo.",
          ["Se suman las salidas de inventario por ajuste o conteo del periodo, valorizadas.",
           "Se divide por el valor de lo despachado en el mismo periodo."]),
    Ficha("rotacion", "Rotación del inventario", "Inventario", "veces/año", "mayor", 8,
          "Cuántas veces al año se renueva el inventario.",
          "Costo de lo despachado anualizado ÷ inventario promedio valorizado",
          "Kárdex (salidas a su costo) e inventario reconstruido al inicio y al fin del periodo.",
          ["Se valoriza lo despachado en el periodo y se lleva a un año (× 365 ÷ días del periodo).",
           "El inventario al inicio y al fin se reconstruye con el kárdex desde la existencia actual.",
           "Se divide lo anualizado por el promedio de los dos."]),
    Ficha("dias_inventario", "Días de inventario", "Inventario", "días", "menor", 45,
          "Para cuántos días alcanza el inventario al ritmo de salida del periodo.",
          "Inventario promedio valorizado ÷ costo despachado por día", "Mismos datos que la rotación.",
          ["Inventario promedio como en la rotación.", "Costo despachado del periodo dividido por sus días.",
           "Se divide el primero por el segundo."]),
    Ficha("sin_movimiento", "Referencias sin movimiento (90 días)", "Inventario", "%", "menor", 10,
          "Qué parte de las referencias con existencia no ha tenido una salida en 90 días (obsolescencia).",
          "Referencias con existencia y sin despacho en 90 días ÷ referencias con existencia × 100",
          "Existencias actuales y última salida de cada producto en el kárdex.",
          ["Referencias con existencia hoy.", "Se busca su último despacho.",
           "Se cuentan las que no salen hace más de 90 días; el aviso dice cuánto valor representan."],
          instantaneo=True),
    Ficha("inventario_vencido", "Inventario vencido", "Inventario", "%", "menor", 0.5,
          "Qué parte de las unidades en bodega está en lotes ya vencidos.",
          "Unidades en lotes vencidos ÷ unidades en bodega × 100", "Existencias actuales por lote y fecha de vencimiento.",
          ["Existencias actuales por lote.", "Se suman las de lotes con vencimiento anterior a hoy."], instantaneo=True),
    Ficha("utilizacion_cubica", "Utilización cúbica", "Espacio", "%", "mayor", 85,
          "Qué parte del volumen útil de las ubicaciones está ocupado por mercancía.",
          "Σ unidades × volumen unitario ÷ Σ capacidad de las ubicaciones × 100",
          "Medidas de las ubicaciones, volumen medido de cada producto (cubicaje) y existencias.",
          ["Ubicaciones de almacenamiento (sin recepción ni despacho).",
           "Volumen ocupado = unidades × volumen de la unidad medida.",
           "Las ubicaciones sin medidas y los productos sin cubicar quedan por fuera y se avisan."],
          "Por encima de ~85 % la operación se entorpece (no hay espacio para mover); por debajo de ~60 % se paga espacio vacío.",
          especializado=True, instantaneo=True),
    Ficha("ocupacion_posiciones", "Ocupación de posiciones", "Espacio", "%", "mayor", 85,
          "Qué parte de las ubicaciones tiene mercancía.", "Ubicaciones con existencia ÷ ubicaciones × 100",
          "Ubicaciones y existencias actuales.", ["Ubicaciones de almacenamiento.", "Se cuentan las que tienen algo."],
          instantaneo=True),
    Ficha("lineas_completas", "Líneas alistadas completas", "Alistamiento", "%", "mayor", 99,
          "Qué parte de las líneas de alistamiento se alistó completa.",
          "Líneas con alistado = pedido ÷ líneas confirmadas × 100", "Detalle de las tareas de alistamiento.",
          ["Líneas confirmadas en el periodo.", "Una línea está completa si se alistó todo lo reservado."]),
    Ficha("alistamiento_verificado", "Alistamiento verificado por escaneo", "Alistamiento", "%", "mayor", 100,
          "Qué parte de las líneas se confirmó escaneando ubicación o producto. La verificación es lo que evita el error de "
          "alistamiento antes de que llegue al cliente.",
          "Confirmaciones con escaneo ÷ confirmaciones × 100", "Eventos de confirmación de alistamiento.",
          ["Confirmaciones de alistamiento del periodo.", "Se cuentan las que llevaron escaneo."], especializado=True),
    Ficha("productividad_picking", "Productividad de alistamiento", "Productividad", "líneas/h", "mayor", 60,
          "Cuántas líneas alista una persona por hora de alistamiento.",
          "Líneas confirmadas ÷ horas de las tareas (inicio a fin)", "Tareas de alistamiento con inicio y fin.",
          ["Tareas de alistamiento terminadas en el periodo con hora de inicio.",
           "Se suman sus líneas confirmadas y sus horas.", "Se dividen."]),
    Ficha("ciclo_orden", "Ciclo de la orden", "Despacho", "h", "menor", 24,
          "Cuánto pasa desde que se registra la orden hasta que sale su primer despacho.",
          "Promedio de (primer despacho − registro de la orden)", "Órdenes de salida y sus despachos.",
          ["Órdenes cuyo primer despacho cae en el periodo.", "Se promedian las horas desde su registro."]),
    Ficha("despacho_a_tiempo", "Despachos a tiempo", "Despacho", "%", "mayor", 95,
          "Qué parte de las órdenes salió de la bodega a más tardar la fecha requerida.",
          "Órdenes despachadas ≤ fecha requerida ÷ órdenes con fecha requerida × 100", "Órdenes y su primer despacho.",
          ["Órdenes cuyo primer despacho cae en el periodo y tienen fecha requerida.", "Se cuentan las que salieron a tiempo."]),
    Ficha("otif", "OTIF (a tiempo y completo)", "Servicio al cliente", "%", "mayor", 95,
          "Qué parte de las órdenes llegó al cliente a tiempo Y completa.",
          "Órdenes entregadas a tiempo y completas ÷ órdenes entregadas con fecha requerida × 100",
          "Órdenes, sus líneas (pedido y despachado) y la entrega real de sus despachos.",
          ["Órdenes entregadas cuya última entrega cae en el periodo.",
           "A tiempo: la última entrega es a más tardar la fecha requerida.",
           "Completa: todas sus líneas se despacharon completas.",
           "Se evalúa orden por orden: las dos condiciones a la vez (antes se aproximaba con el menor de dos conteos)."],
          "Es el indicador de servicio que más miran los clientes; por debajo de 90 % suele haber reclamos."),
    Ficha("orden_perfecta", "Orden perfecta", "Servicio al cliente", "%", "mayor", 90,
          "Qué parte de las órdenes no tuvo ningún problema: a tiempo, completa, sin devolución y sin incidencia en el transporte.",
          "Órdenes sin ninguna falla ÷ órdenes entregadas con fecha requerida × 100",
          "Las del OTIF, más las devoluciones asociadas a la orden y el historial de estados del despacho.",
          ["Mismas órdenes del OTIF.", "Se marca cada falla: tarde, incompleta, con devolución, con incidencia.",
           "Solo cuentan las que no tienen ninguna; el detalle dice qué falló en las demás."]),
    Ficha("fill_rate_lineas", "Nivel de servicio por línea", "Servicio al cliente", "%", "mayor", 98,
          "Qué parte de las líneas pedidas se despachó completa.", "Líneas completas ÷ líneas × 100",
          "Órdenes emitidas en el periodo ya despachadas y sus líneas.",
          ["Órdenes emitidas en el periodo y ya despachadas o entregadas.", "Se cuentan las líneas despachadas completas."]),
    Ficha("fill_rate_unidades", "Nivel de servicio por unidad", "Servicio al cliente", "%", "mayor", 99,
          "Qué parte de las unidades pedidas se despachó.", "Σ despachado (hasta lo pedido) ÷ Σ pedido × 100",
          "Mismas órdenes y líneas.", ["Mismas líneas.", "Se suman las unidades despachadas sin pasar de lo pedido."]),
    Ficha("tiempo_cargue", "Tiempo de cargue", "Despacho", "min", "menor", 45,
          "Lo que dura cargar un vehículo.", "Promedio de (fin del cargue − inicio del cargue)",
          "Despachos con inicio y fin de cargue.", ["Despachos del periodo con los dos tiempos.", "Se promedian."],
          especializado=True),
    Ficha("tasa_devolucion", "Devoluciones de clientes", "Servicio al cliente", "%", "menor", 2,
          "Unidades que los clientes devolvieron frente a las despachadas.",
          "Unidades devueltas por clientes ÷ unidades despachadas × 100", "Devoluciones de clientes y kárdex de despachos.",
          ["Unidades de devoluciones de clientes recibidas en el periodo.", "Unidades despachadas en el periodo.", "Se dividen."]),
]

CALCULOS: Dict[str, Callable] = {
    "dock_to_stock": dock_to_stock, "tiempo_descargue": tiempo_descargue, "recepcion_a_tiempo": recepcion_a_tiempo,
    "exactitud_recepcion": exactitud_recepcion, "fill_rate_proveedor": fill_rate_proveedor,
    "ubicacion_sugerida_cumplida": ubicacion_sugerida_cumplida, "espera_tareas": espera_tareas,
    "productividad_ubicacion": productividad_ubicacion, "exactitud_inventario": exactitud_inventario,
    "exactitud_valor": exactitud_valor, "merma": merma, "rotacion": rotacion, "dias_inventario": dias_inventario,
    "sin_movimiento": sin_movimiento, "inventario_vencido": inventario_vencido, "utilizacion_cubica": utilizacion_cubica,
    "ocupacion_posiciones": ocupacion_posiciones, "lineas_completas": lineas_completas,
    "alistamiento_verificado": alistamiento_verificado, "productividad_picking": productividad_picking,
    "ciclo_orden": ciclo_orden, "despacho_a_tiempo": despacho_a_tiempo, "otif": otif, "orden_perfecta": orden_perfecta,
    "fill_rate_lineas": fill_rate_lineas, "fill_rate_unidades": fill_rate_unidades, "tiempo_cargue": tiempo_cargue,
    "tasa_devolucion": tasa_devolucion,
}
FICHAS = {f.clave: f for f in CATALOGO}
assert set(FICHAS) == set(CALCULOS), "cada indicador del catálogo necesita su cálculo"


def semaforo(f: Ficha, valor: Optional[float], meta: float) -> Optional[str]:
    """verde = cumple la meta; amarillo = a menos del 10 % de cumplirla; rojo = más lejos."""
    if valor is None:
        return None
    if f.unidad == "%" and valor > 100.0001:
        return "rojo"     # un porcentaje imposible es un error de datos, no un buen resultado
    if f.sentido == "mayor":
        if valor >= meta:
            return "verde"
        return "amarillo" if valor >= meta * 0.9 else "rojo"
    if valor <= meta:
        return "verde"
    return "amarillo" if valor <= meta * 1.1 else "rojo"
