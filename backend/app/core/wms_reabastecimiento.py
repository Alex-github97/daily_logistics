"""
Frentes de picking y reabastecimiento.

Un frente es la ubicación de la que se alista (o se vende, en la sala POS) un
producto, con mínimo y máximo expresados en unidades o en un nivel de empaque
(cajas, máster, estibas). Cuando lo que hay en el frente más lo que ya viene en
camino queda por debajo del mínimo, se crea una tarea de REABASTECIMIENTO:

- origen: la reserva del mismo producto en el almacén (zonas de almacenamiento,
  fuera de la sala POS y de otros frentes del producto), por vencimiento (FEFO);
- cantidad: hasta el máximo, redondeada al empaque del frente si lo hay;
- estado: POR_APROBAR si el almacén exige aprobación del supervisor, si no
  PENDIENTE (lista para asignar);
- una sola tarea abierta por frente: lo que ya viene en camino cuenta.

Lo llaman el ciclo de fondo (cada minuto, todos los clientes), el botón
«Evaluar ahora» y el picking cuando los frentes no le alcanzan (urgente).
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.wms import (
    WMSConfigTareas, WMSFrentePicking, WMSInventarioUbicacion, WMSLote, WMSProducto, WMSProductoEmpaque, WMSTarea,
    WMSUbicacion, WMSZona,
)

ABIERTAS = ("POR_APROBAR", "PENDIENTE", "ASIGNADA", "EN_CURSO")
ZONAS_SIN_RESERVA = ("RECEPCION", "CUARENTENA", "DESPACHO", "TRANSITO")
UNIDADES = ("UNIDAD", "CAJA", "MASTER", "ESTIBA")


# ── Configuración ────────────────────────────────────────────────────────────

async def config(db: AsyncSession, almacen_id: int, crear: bool = False) -> WMSConfigTareas:
    c = (await db.execute(select(WMSConfigTareas).where(WMSConfigTareas.almacen_id == almacen_id))).scalar_one_or_none()
    if c is None:
        c = WMSConfigTareas(almacen_id=almacen_id, reabastecimiento_activo=True, requiere_aprobacion=True,
                            picking_solo_frentes=True, picking_reserva_si_falta=False, picking_excluir_pos=True,
                            exigir_escaneo_origen=True, liberar_asignada_min=15, alerta_en_curso_min=30,
                            nivel_montacargas=2)
        if crear:
            db.add(c)
            await db.flush()
    return c


async def factor(db: AsyncSession, producto_id: int, unidad: str) -> Optional[float]:
    """Unidades base de un nivel de empaque (UNIDAD = 1; None si el producto no tiene ese empaque)."""
    if unidad == "UNIDAD":
        return 1.0
    u = (await db.execute(select(WMSProductoEmpaque.unidades).where(
        WMSProductoEmpaque.producto_id == producto_id, WMSProductoEmpaque.nivel == unidad))).scalar()
    return float(u) if u and u > 0 else None


# ── Reglas para el picking ───────────────────────────────────────────────────

async def reglas_picking(db: AsyncSession, almacen_id: int, producto_id: int) -> Tuple[Optional[List[int]], bool, bool]:
    """(ubicaciones de frente habilitadas o None si no aplica, ¿puede tomar de la
    reserva si faltan?, ¿excluir la sala POS?)."""
    c = await config(db, almacen_id)
    frentes = None
    if c.picking_solo_frentes:
        ids = (await db.execute(select(WMSFrentePicking.ubicacion_id).join(
            WMSUbicacion, WMSUbicacion.id == WMSFrentePicking.ubicacion_id).join(
            WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
            WMSFrentePicking.almacen_id == almacen_id, WMSFrentePicking.producto_id == producto_id,
            WMSFrentePicking.activo.is_(True), WMSZona.vendible_pos.isnot(True)))).scalars().all()
        frentes = list(ids) or None
    return frentes, bool(c.picking_reserva_si_falta), bool(c.picking_excluir_pos)


# ── Estado de los frentes ────────────────────────────────────────────────────

async def _fisico(db: AsyncSession, pares: Sequence[Tuple[int, int]]) -> Dict[Tuple[int, int], float]:
    """Lo que hay físicamente (disponible + reservado) por (producto, ubicación)."""
    if not pares:
        return {}
    prods = {p for p, _ in pares}
    ubics = {u for _, u in pares}
    filas = (await db.execute(select(
        WMSInventarioUbicacion.producto_id, WMSInventarioUbicacion.ubicacion_id,
        func.sum(WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada)).where(
        WMSInventarioUbicacion.producto_id.in_(prods), WMSInventarioUbicacion.ubicacion_id.in_(ubics)).group_by(
        WMSInventarioUbicacion.producto_id, WMSInventarioUbicacion.ubicacion_id))).all()
    return {(p, u): float(n or 0) for p, u, n in filas}


async def _en_camino(db: AsyncSession, pares: Sequence[Tuple[int, int]]) -> Dict[Tuple[int, int], float]:
    if not pares:
        return {}
    filas = (await db.execute(select(WMSTarea.producto_id, WMSTarea.ubicacion_sugerida_id, func.sum(WMSTarea.cantidad)).where(
        WMSTarea.tipo == "REABASTECIMIENTO", WMSTarea.estado.in_(ABIERTAS),
        WMSTarea.ubicacion_sugerida_id.in_({u for _, u in pares})).group_by(
        WMSTarea.producto_id, WMSTarea.ubicacion_sugerida_id))).all()
    return {(p, u): float(n or 0) for p, u, n in filas}


async def estado_frentes(db: AsyncSession, frentes: Sequence[WMSFrentePicking]) -> Dict[int, dict]:
    pares = [(f.producto_id, f.ubicacion_id) for f in frentes]
    fis, cam = await _fisico(db, pares), await _en_camino(db, pares)
    out = {}
    for f in frentes:
        k = await factor(db, f.producto_id, f.unidad)
        minimo_u = f.minimo * (k or 1)
        maximo_u = f.maximo * (k or 1)
        actual = fis.get((f.producto_id, f.ubicacion_id), 0.0)
        camino = cam.get((f.producto_id, f.ubicacion_id), 0.0)
        estado = ("SIN_EMPAQUE" if k is None else "AGOTADO" if actual <= 0 else "BAJO" if actual < minimo_u
                  else "SOBRE" if maximo_u and actual > maximo_u else "OK")
        out[f.id] = {"factor": k, "minimo_u": minimo_u, "maximo_u": maximo_u, "actual": actual, "en_camino": camino,
                     "estado": estado, "pct": round(actual / maximo_u * 100, 1) if maximo_u else None}
    return out


# ── Crear tareas ─────────────────────────────────────────────────────────────

async def _reserva(db: AsyncSession, almacen_id: int, producto_id: int, excluir: Sequence[int]) -> list:
    """Filas de reserva del producto, en orden FEFO, sin lotes vencidos ni inactivos."""
    hoy = date.today()
    return (await db.execute(
        select(WMSInventarioUbicacion, WMSLote.fecha_vencimiento)
        .join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id)
        .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
        .outerjoin(WMSLote, WMSLote.id == WMSInventarioUbicacion.lote_id)
        .where(WMSInventarioUbicacion.producto_id == producto_id, WMSInventarioUbicacion.cantidad_disponible > 0,
               WMSZona.almacen_id == almacen_id, WMSZona.tipo.notin_(ZONAS_SIN_RESERVA), WMSZona.activo.isnot(False),
               WMSZona.vendible_pos.isnot(True), WMSUbicacion.activo.isnot(False),
               WMSInventarioUbicacion.ubicacion_id.notin_(list(excluir) or [0]),
               (WMSLote.id.is_(None)) | ((WMSLote.activo.isnot(False)) &
                                         ((WMSLote.fecha_vencimiento.is_(None)) | (WMSLote.fecha_vencimiento >= hoy))))
        .order_by(WMSLote.fecha_vencimiento.asc().nullslast(), WMSInventarioUbicacion.cantidad_disponible.asc(),
                  WMSInventarioUbicacion.id))).all()


async def reabastecer_frente(db: AsyncSession, f: WMSFrentePicking, est: dict, *, urgente: bool = False,
                             extra: float = 0) -> Tuple[List[WMSTarea], Optional[str]]:
    """Tareas para llevar el frente hasta su máximo (más `extra` si el picking
    pidió más de lo que cabe). Devuelve (tareas, aviso)."""
    c = await config(db, f.almacen_id)
    k = est["factor"] or 1
    objetivo = max(est["maximo_u"], est["minimo_u"]) + extra
    falta = objetivo - est["actual"] - est["en_camino"]
    if falta <= 0:
        return [], None
    todos_frentes = (await db.execute(select(WMSFrentePicking.ubicacion_id).where(
        WMSFrentePicking.producto_id == f.producto_id))).scalars().all()
    filas = await _reserva(db, f.almacen_id, f.producto_id, todos_frentes)
    if not filas:
        return [], "SIN_RESERVA"
    prod = await db.get(WMSProducto, f.producto_id)
    ubic = await db.get(WMSUbicacion, f.ubicacion_id)
    # Lo que otras tareas abiertas ya van a sacar de cada origen no está libre.
    comprometido = {(u, l, c): float(n or 0) for u, l, c, n in (await db.execute(select(
        WMSTarea.ubicacion_origen_id, WMSTarea.lote_id, WMSTarea.contenedor_origen_id, func.sum(WMSTarea.cantidad)).where(
        WMSTarea.tipo == "REABASTECIMIENTO", WMSTarea.estado.in_(ABIERTAS), WMSTarea.producto_id == f.producto_id)
        .group_by(WMSTarea.ubicacion_origen_id, WMSTarea.lote_id, WMSTarea.contenedor_origen_id))).all()}
    creadas = []
    for fila, _vence in filas:
        if falta <= 0 or len(creadas) >= 3:
            break
        hay = float(fila.cantidad_disponible or 0) - comprometido.get((fila.ubicacion_id, fila.lote_id, fila.contenedor_id), 0)
        cant = min(hay, falta)
        if k > 1:          # redondear al empaque del frente, sin pasar de lo que hay en el origen
            cant = min(hay, math.ceil(cant / k) * k)
        if cant <= 0:
            continue
        agotado = est["actual"] <= 0
        t = WMSTarea(
            tipo="REABASTECIMIENTO", estado="POR_APROBAR" if c.requiere_aprobacion else "PENDIENTE",
            prioridad=1 if urgente else 2 if agotado else 3, almacen_id=f.almacen_id,
            depositante_id=prod.depositante_id if prod else None, producto_id=f.producto_id, lote_id=fila.lote_id,
            cantidad=cant, ubicacion_origen_id=fila.ubicacion_id, contenedor_origen_id=fila.contenedor_id,
            ubicacion_sugerida_id=f.ubicacion_id, documento_tipo="FRENTE", documento_id=f.id,
            razon_sugerencia=(f"{'Urgente: el picking no alcanza · ' if urgente else ''}Frente {ubic.codigo if ubic else ''} "
                              f"{'agotado' if agotado else 'bajo el mínimo'} ({est['actual']:g} de mín. {est['minimo_u']:g})")[:200])
        db.add(t)
        creadas.append(t)
        falta -= cant
    await db.flush()
    return creadas, None


async def evaluar(db: AsyncSession, almacen_id: Optional[int] = None, producto_ids: Optional[Sequence[int]] = None) -> dict:
    """Revisa los frentes activos y crea lo que haga falta."""
    q = select(WMSFrentePicking).where(WMSFrentePicking.activo.is_(True))
    if almacen_id:
        q = q.where(WMSFrentePicking.almacen_id == almacen_id)
    if producto_ids:
        q = q.where(WMSFrentePicking.producto_id.in_(list(producto_ids)))
    frentes = (await db.execute(q)).scalars().all()
    activos = {}
    creadas, sin_reserva = [], []
    est = await estado_frentes(db, frentes)
    for f in frentes:
        if f.almacen_id not in activos:
            activos[f.almacen_id] = (await config(db, f.almacen_id)).reabastecimiento_activo
        e = est[f.id]
        if not activos[f.almacen_id] or e["estado"] == "SIN_EMPAQUE":
            continue
        if e["actual"] + e["en_camino"] < e["minimo_u"] or (e["minimo_u"] == 0 and e["actual"] + e["en_camino"] <= 0 and e["maximo_u"] > 0):
            ts, aviso = await reabastecer_frente(db, f, e)
            creadas += ts
            if aviso == "SIN_RESERVA":
                sin_reserva.append(f.id)
    return {"creadas": [t.id for t in creadas], "sin_reserva": sin_reserva, "frentes": len(frentes)}


async def urgente_por_picking(db: AsyncSession, almacen_id: int, producto_id: int, faltante: float) -> List[WMSTarea]:
    """El picking no alcanzó en los frentes: pide reabastecer el frente principal
    (con lo que falta para el pedido además del máximo)."""
    f = (await db.execute(select(WMSFrentePicking).join(WMSUbicacion, WMSUbicacion.id == WMSFrentePicking.ubicacion_id)
                          .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
        WMSFrentePicking.almacen_id == almacen_id, WMSFrentePicking.producto_id == producto_id,
        WMSFrentePicking.activo.is_(True), WMSZona.vendible_pos.isnot(True))
        .order_by(WMSFrentePicking.prioridad, WMSFrentePicking.id).limit(1))).scalar_one_or_none()
    if f is None or not (await config(db, almacen_id)).reabastecimiento_activo:
        return []
    est = (await estado_frentes(db, [f]))[f.id]
    if est["estado"] == "SIN_EMPAQUE":
        return []
    ts, _ = await reabastecer_frente(db, f, est, urgente=True, extra=max(0.0, float(faltante)))
    # Lo que ya venía en camino para ese frente pasa a urgente.
    for t in (await db.execute(select(WMSTarea).where(
            WMSTarea.documento_tipo == "FRENTE", WMSTarea.documento_id == f.id, WMSTarea.estado.in_(ABIERTAS),
            WMSTarea.prioridad > 1))).scalars():
        t.prioridad = 1
        if not (t.razon_sugerencia or "").startswith("Urgente"):
            t.razon_sugerencia = ("Urgente: el picking no alcanza · " + (t.razon_sugerencia or ""))[:200]
    return ts
