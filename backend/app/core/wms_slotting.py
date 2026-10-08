"""
Slotting: dónde debería estar cada producto.

**Recorrido.** Cada ubicación tiene un lugar en el recorrido de alistamiento:
el que se le configure (`orden_recorrido`) o, si no, el de una serpentina por
pasillos: el pasillo 1 se recorre hacia el fondo, el 2 hacia el frente, y así.
Es la ruta clásica (S-shape) de una bodega de pasillos paralelos.

**Ubicaciones preferentes.** Las del primer tramo del recorrido (el 30 % más
cercano) en la zona dorada: niveles 1 y 2, a la altura de la cintura y el
pecho, donde se alista sin escalera ni agacharse.

**ABC.** Por número de líneas alistadas en los últimos 90 días: A son las
referencias que suman el 80 % de las líneas, B el siguiente 15 %, C el resto
(incluye las que tienen existencia y no se alistaron).

**Sugerencias.** Una A que no tiene nada en ubicaciones preferentes: llevarla a
la mejor preferente libre (si hay medidas, que quepa). Una C que ocupa una
preferente cuando hay A afuera: sacarla a la última libre del recorrido.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_cubicaje as cub
from app.infrastructure.models.wms import (
    WMSInventarioUbicacion, WMSOrdenSalida, WMSPickingDetalle, WMSPickingTarea, WMSProducto, WMSProductoEmpaque,
    WMSUbicacion, WMSZona,
)

NIVELES_DORADOS = {1, 2}
TRAMO_PREFERENTE = 0.30
ZONAS_ALMACENAJE = ("ALMACENAMIENTO",)


def _num(texto: Optional[str]) -> Optional[int]:
    m = re.search(r"\d+", texto or "")
    return int(m.group()) if m else None


def clave_recorrido(u: WMSUbicacion) -> Tuple:
    """Orden de la ubicación en la serpentina por pasillos."""
    if u.orden_recorrido:
        return (0, u.orden_recorrido, 0, 0, u.codigo)
    pasillo = _num(u.pasillo)
    pos = _num(u.posicion) or _num(u.estanteria) or 0
    if pasillo is None:
        return (2, 0, 0, 0, u.codigo)
    sentido = 1 if pasillo % 2 else -1          # impar hacia el fondo, par de regreso
    return (1, pasillo, sentido * pos, _num(u.nivel) or 0, u.codigo)


@dataclass
class Ubic:
    id: int
    codigo: str
    puesto: int            # lugar en el recorrido (0 = primera)
    nivel: Optional[int]
    preferente: bool
    capacidad_m3: Optional[float]
    ocupado_m3: float
    unidades: float


async def ubicaciones_ordenadas(db: AsyncSession, almacen_id: int) -> List[Ubic]:
    filas = (await db.execute(select(WMSUbicacion).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
        WMSZona.almacen_id == almacen_id, WMSZona.tipo.in_(ZONAS_ALMACENAJE), WMSZona.activo.isnot(False),
        WMSUbicacion.activo.isnot(False)))).scalars().all()
    filas = sorted(filas, key=clave_recorrido)
    total = WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada \
        + WMSInventarioUbicacion.cantidad_bloqueada
    stock = (await db.execute(select(WMSInventarioUbicacion.ubicacion_id, WMSInventarioUbicacion.producto_id, func.sum(total))
                              .where(WMSInventarioUbicacion.ubicacion_id.in_([u.id for u in filas] or [0]), total > 0)
                              .group_by(WMSInventarioUbicacion.ubicacion_id, WMSInventarioUbicacion.producto_id))).all()
    vol = await volumenes(db, {p for _u, p, _q in stock})
    ocupado, unidades = defaultdict(float), defaultdict(float)
    for uid, pid, q in stock:
        unidades[uid] += float(q)
        ocupado[uid] += float(q) * (vol.get(pid) or 0)
    corte = max(1, round(len(filas) * TRAMO_PREFERENTE))
    out = []
    for i, u in enumerate(filas):
        nivel = _num(u.nivel)
        out.append(Ubic(u.id, u.codigo, i, nivel, i < corte and (nivel is None or nivel in NIVELES_DORADOS),
                        cub.volumen_m3(u.largo_cm, u.ancho_cm, u.alto_cm) or u.capacidad_m3, ocupado[u.id], unidades[u.id]))
    return out


async def volumenes(db: AsyncSession, producto_ids) -> Dict[int, float]:
    ids = set(producto_ids)
    vol = {p: v for p, v in (await db.execute(select(WMSProducto.id, WMSProducto.volumen_m3)
                                              .where(WMSProducto.id.in_(ids or {0})))).all() if v}
    for e in (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id.in_(ids or {0}),
                                                               WMSProductoEmpaque.nivel == "UNIDAD"))).scalars():
        v = cub.volumen_m3(e.largo_cm, e.ancho_cm, e.alto_cm)
        if v:
            vol[e.producto_id] = v
    return vol


async def abc(db: AsyncSession, almacen_id: int, dias: int = 90) -> Dict[int, dict]:
    """Clase ABC de cada producto con existencia o alistado en el almacén."""
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    lineas = dict((await db.execute(
        select(WMSPickingDetalle.producto_id, func.count())
        .join(WMSPickingTarea, WMSPickingTarea.id == WMSPickingDetalle.tarea_id)
        .join(WMSOrdenSalida, WMSOrdenSalida.id == WMSPickingTarea.orden_id)
        .where(WMSOrdenSalida.almacen_id == almacen_id, WMSPickingDetalle.confirmado.is_(True),
               WMSPickingDetalle.timestamp_confirmacion >= desde)
        .group_by(WMSPickingDetalle.producto_id))).all())
    unidades = dict((await db.execute(
        select(WMSPickingDetalle.producto_id, func.sum(WMSPickingDetalle.cantidad_pickeada))
        .join(WMSPickingTarea, WMSPickingTarea.id == WMSPickingDetalle.tarea_id)
        .join(WMSOrdenSalida, WMSOrdenSalida.id == WMSPickingTarea.orden_id)
        .where(WMSOrdenSalida.almacen_id == almacen_id, WMSPickingDetalle.confirmado.is_(True),
               WMSPickingDetalle.timestamp_confirmacion >= desde)
        .group_by(WMSPickingDetalle.producto_id))).all())
    con_stock = set((await db.execute(
        select(WMSInventarioUbicacion.producto_id).join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id)
        .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
        .where(WMSZona.almacen_id == almacen_id, WMSInventarioUbicacion.cantidad_disponible > 0))).scalars())
    total = sum(lineas.values())
    out, acumulado = {}, 0
    for pid, n in sorted(lineas.items(), key=lambda x: -x[1]):
        # La clase la decide dónde EMPIEZA el producto en la curva: el que
        # cruza el 80 % todavía es A.
        clase = "A" if acumulado < total * 0.80 else "B" if acumulado < total * 0.95 else "C"
        acumulado += n
        out[pid] = {"clase": clase, "lineas": n, "unidades": float(unidades.get(pid) or 0),
                    "participacion_pct": round(n / total * 100, 2) if total else 0}
    for pid in con_stock - set(out):
        out[pid] = {"clase": "C", "lineas": 0, "unidades": 0.0, "participacion_pct": 0}
    return out


async def sugerencias(db: AsyncSession, almacen_id: int, dias: int = 90, limite: int = 50) -> List[dict]:
    clases = await abc(db, almacen_id, dias)
    ubic = await ubicaciones_ordenadas(db, almacen_id)
    por_id = {u.id: u for u in ubic}
    filas = (await db.execute(select(WMSInventarioUbicacion).where(
        WMSInventarioUbicacion.ubicacion_id.in_(list(por_id) or [0]),
        WMSInventarioUbicacion.cantidad_disponible > 0))).scalars().all()
    por_producto = defaultdict(list)
    for f in filas:
        por_producto[f.producto_id].append(f)
    vol = await volumenes(db, por_producto)
    nombres = dict((await db.execute(select(WMSProducto.id, WMSProducto.sku).where(
        WMSProducto.id.in_(list(por_producto) or [0])))).all())
    libres = [u for u in ubic if u.unidades == 0]
    usadas: set = set()
    out = []

    def cabe(u: Ubic, pid, cantidad) -> bool:
        return not (u.capacidad_m3 and vol.get(pid)) or vol[pid] * cantidad <= u.capacidad_m3

    # 1. Las A que viven lejos.
    for pid, info in sorted(clases.items(), key=lambda x: -x[1]["lineas"]):
        if info["clase"] != "A" or pid not in por_producto:
            continue
        actuales = por_producto[pid]
        if any(por_id[f.ubicacion_id].preferente for f in actuales):
            continue
        origen = min(actuales, key=lambda f: por_id[f.ubicacion_id].puesto)   # la más cercana de las suyas
        if origen.contenedor_id:
            continue   # las estibas se mueven enteras desde Estibas
        destino = next((u for u in libres if u.preferente and u.id not in usadas
                        and cabe(u, pid, origen.cantidad_disponible)), None)
        if destino is None:
            continue
        usadas.add(destino.id)
        ahorro = por_id[origen.ubicacion_id].puesto - destino.puesto
        out.append({"tipo": "ACERCAR", "producto_id": pid, "sku": nombres.get(pid), "clase": "A", "lineas": info["lineas"],
                    "lote_id": origen.lote_id, "cantidad": origen.cantidad_disponible,
                    "origen_id": origen.ubicacion_id, "origen": por_id[origen.ubicacion_id].codigo,
                    "destino_id": destino.id, "destino": destino.codigo,
                    "razon": f"Clase A ({info['lineas']} líneas en {dias} días) lejos del frente: queda {ahorro} posiciones "
                             f"antes en el recorrido y en zona dorada."})
        if len(out) >= limite:
            return out
    # 2. Las C que ocupan una preferente, si alguna A quedó afuera sin lugar.
    a_afuera = any(info["clase"] == "A" and pid in por_producto
                   and not any(por_id[f.ubicacion_id].preferente for f in por_producto[pid])
                   for pid, info in clases.items()) or not [u for u in libres if u.preferente and u.id not in usadas]
    if a_afuera:
        atras = [u for u in reversed(libres) if not u.preferente and u.id not in usadas]
        for f in sorted(filas, key=lambda f: por_id[f.ubicacion_id].puesto):
            u = por_id[f.ubicacion_id]
            if not u.preferente or f.contenedor_id or clases.get(f.producto_id, {}).get("clase") != "C":
                continue
            destino = next((x for x in atras if x.id not in usadas and cabe(x, f.producto_id, f.cantidad_disponible)), None)
            if destino is None:
                break
            usadas.add(destino.id)
            out.append({"tipo": "ALEJAR", "producto_id": f.producto_id, "sku": nombres.get(f.producto_id), "clase": "C",
                        "lineas": clases[f.producto_id]["lineas"], "lote_id": f.lote_id, "cantidad": f.cantidad_disponible,
                        "origen_id": u.id, "origen": u.codigo, "destino_id": destino.id, "destino": destino.codigo,
                        "razon": "Clase C en una ubicación preferente: liberarla para una referencia de alta rotación."})
            if len(out) >= limite:
                break
    return out


async def mejor_para_guardar(db: AsyncSession, almacen_id: int, producto_id: int, cantidad: float) -> Tuple[Optional[int], Optional[str]]:
    """Ubicación libre para lo que llega, según su clase: las A al frente en
    zona dorada; las B y C desde el fondo (no gastan lo preferente). Si hay
    medidas, que quepa."""
    clase = (await abc(db, almacen_id)).get(producto_id, {}).get("clase", "C")
    ubic = await ubicaciones_ordenadas(db, almacen_id)
    vol = (await volumenes(db, [producto_id])).get(producto_id)
    libres = [u for u in ubic if u.unidades == 0 and (not (u.capacidad_m3 and vol) or vol * cantidad <= u.capacidad_m3)]
    if not libres:
        return None, None
    if clase == "A":
        u = next((x for x in libres if x.preferente), libres[0])
        return u.id, f"Clase A: ubicación libre {u.codigo}, al frente del recorrido{' y en zona dorada' if u.preferente else ''}"
    no_pref = [x for x in libres if not x.preferente] or libres
    u = no_pref[-1] if clase == "C" else no_pref[0]
    return u.id, f"Clase {clase}: ubicación libre {u.codigo}, sin gastar las preferentes"
