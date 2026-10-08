"""
Reglas de operación del WMS que comparten varios endpoints: el dueño de cada
documento (3PL), las estibas (LPN), dónde guardar lo que llega y las tareas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.wms import (
    WMSContenedor, WMSDepositante, WMSInventarioUbicacion, WMSProducto, WMSTarea, WMSUbicacion, WMSZona,
)
from app.core import wms_inventario as inv


def ahora() -> datetime:
    return datetime.now(timezone.utc)


# ── Depositantes ─────────────────────────────────────────────────────────────

async def depositante_propio(db: AsyncSession) -> int:
    """La empresa misma como depositante. Se crea la primera vez que hace falta."""
    d = (await db.execute(select(WMSDepositante.id).where(WMSDepositante.propio.is_(True))
                          .order_by(WMSDepositante.id).limit(1))).scalar()
    if d is None:
        nuevo = WMSDepositante(codigo="PROPIO", nombre="Mercancía propia", propio=True, activo=True)
        db.add(nuevo)
        await db.flush()
        d = nuevo.id
    return d


async def resolver_depositante(db: AsyncSession, depositante_id: Optional[int],
                               producto_ids: Iterable[int]) -> Optional[int]:
    """El dueño de un documento. Un documento es de un solo depositante: sus
    productos tienen que ser todos de él. Si no se dice, se toma de los productos."""
    ids = sorted({p for p in producto_ids if p})
    duenos = dict((await db.execute(select(WMSProducto.id, WMSProducto.depositante_id)
                                    .where(WMSProducto.id.in_(ids)))).all()) if ids else {}
    faltan = [p for p in ids if p not in duenos]
    if faltan:
        raise HTTPException(422, f"Productos que no existen: {faltan}.")
    distintos = {d for d in duenos.values()}
    if depositante_id is None:
        if len(distintos) > 1:
            raise HTTPException(422, "El documento mezcla mercancía de varios depositantes; sepárelo por dueño.")
        return next(iter(distintos), None)
    if await db.get(WMSDepositante, depositante_id) is None:
        raise HTTPException(422, "El depositante no existe.")
    ajenos = [p for p, d in duenos.items() if d != depositante_id]
    if ajenos:
        nombres = (await db.execute(select(WMSProducto.sku).where(WMSProducto.id.in_(ajenos)))).scalars().all()
        raise HTTPException(422, f"Estos productos no son del depositante del documento: {', '.join(nombres)}.")
    return depositante_id


# ── Estibas (LPN) ────────────────────────────────────────────────────────────

async def nuevo_codigo_lpn(db: AsyncSession) -> str:
    n = ((await db.execute(select(func.max(WMSContenedor.id)))).scalar() or 0) + 1
    while True:
        codigo = f"LPN{n:08d}"
        if (await db.execute(select(WMSContenedor.id).where(WMSContenedor.codigo == codigo))).first() is None:
            return codigo
        n += 1


async def crear_contenedor(db: AsyncSession, *, almacen_id: int, ubicacion_id: Optional[int],
                           depositante_id: Optional[int], tipo: str = "ESTIBA", usuario_id: Optional[int] = None,
                           documento_tipo: Optional[str] = None, documento_id: Optional[int] = None,
                           notas: Optional[str] = None) -> WMSContenedor:
    c = WMSContenedor(codigo=await nuevo_codigo_lpn(db), tipo=tipo, estado="ABIERTO", almacen_id=almacen_id,
                      ubicacion_id=ubicacion_id, depositante_id=depositante_id, creado_por_id=usuario_id,
                      documento_tipo=documento_tipo, documento_id=documento_id, notas=notas)
    db.add(c)
    await db.flush()
    return c


async def contenido(db: AsyncSession, contenedor_id: int):
    await db.flush()
    return (await db.execute(select(WMSInventarioUbicacion).where(
        WMSInventarioUbicacion.contenedor_id == contenedor_id,
        (WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada
         + WMSInventarioUbicacion.cantidad_bloqueada) > 0))).scalars().all()


async def mover_contenedor(db: AsyncSession, cont: WMSContenedor, destino: int, *, usuario_id: Optional[int],
                           tarea_id: Optional[int] = None, tipo: str = "TRANSFERENCIA",
                           documento_tipo: Optional[str] = None, documento_id: Optional[int] = None) -> int:
    """Lleva la estiba entera a otra ubicación: cada línea de su contenido deja
    su movimiento en el kárdex, en el estado en que estaba."""
    if cont.ubicacion_id == destino:
        return 0
    lineas = 0
    for f in await contenido(db, cont.id):
        for estado, col in inv.ESTADOS.items():
            q = getattr(f, col) or 0
            if q > 0:
                await inv.mover(db, tipo=tipo, producto_id=f.producto_id, cantidad=q, lote_id=f.lote_id,
                                origen=f.ubicacion_id, destino=destino, estado_origen=estado, estado_destino=estado,
                                contenedor_origen=cont.id, usuario_id=usuario_id, tarea_id=tarea_id,
                                documento_tipo=documento_tipo or "LPN", documento_id=documento_id or cont.id,
                                referencia=cont.codigo)
                lineas += 1
    cont.ubicacion_id = destino
    return lineas


# ── Dónde guardar ────────────────────────────────────────────────────────────

async def sugerir_ubicacion(db: AsyncSession, almacen_id: int, producto_id: int,
                            lote_id: Optional[int] = None, cantidad: float = 0) -> Tuple[Optional[int], Optional[str]]:
    """Ubicación sugerida para guardar un producto, con su razón.

    1. Donde ya está el mismo producto y lote (consolidar: menos ubicaciones
       abiertas, picking más corto).
    2. Una ubicación vacía de una zona de almacenamiento, en orden de código
       (de adelante hacia atrás).
    2. Si no, la del slotting: las A al frente en zona dorada, las B y C
       desde el fondo, y que quepa si hay medidas (`wms_slotting`)."""
    base = (select(WMSUbicacion.id, WMSUbicacion.codigo)
            .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
            .where(WMSZona.almacen_id == almacen_id, WMSZona.tipo == "ALMACENAMIENTO",
                   WMSZona.activo.isnot(False), WMSUbicacion.activo.isnot(False)))
    ya = (await db.execute(base.join(WMSInventarioUbicacion, WMSInventarioUbicacion.ubicacion_id == WMSUbicacion.id)
                           .where(WMSInventarioUbicacion.producto_id == producto_id,
                                  WMSInventarioUbicacion.lote_id.is_(None) if lote_id is None
                                  else WMSInventarioUbicacion.lote_id == lote_id,
                                  WMSInventarioUbicacion.cantidad_disponible > 0)
                           .order_by(WMSUbicacion.codigo).limit(1))).first()
    if ya:
        return ya.id, f"Consolidar con el mismo producto{' y lote' if lote_id else ''} en {ya.codigo}"
    from app.core.wms_slotting import mejor_para_guardar
    sug, razon = await mejor_para_guardar(db, almacen_id, producto_id, cantidad)
    if sug:
        return sug, razon
    ocupadas = select(WMSInventarioUbicacion.ubicacion_id).where(
        (WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada
         + WMSInventarioUbicacion.cantidad_bloqueada) > 0)
    vacia = (await db.execute(base.where(WMSUbicacion.id.notin_(ocupadas)).order_by(WMSUbicacion.codigo)
                              .limit(1))).first()
    if vacia:
        return vacia.id, f"Ubicación vacía {vacia.codigo}"
    return None, None


# ── Tareas ───────────────────────────────────────────────────────────────────

async def crear_tarea_ubicacion(db: AsyncSession, *, almacen_id: int, producto_id: int, lote_id: Optional[int],
                                contenedor_id: Optional[int], cantidad: float, origen: int,
                                sugerida: Optional[int], razon: Optional[str], depositante_id: Optional[int],
                                documento_tipo: str, documento_id: int, prioridad: int = 5) -> WMSTarea:
    if sugerida is None:
        sugerida, razon = await sugerir_ubicacion(db, almacen_id, producto_id, lote_id, cantidad)
    t = WMSTarea(tipo="UBICACION", estado="PENDIENTE", prioridad=prioridad, almacen_id=almacen_id,
                 depositante_id=depositante_id, producto_id=producto_id, lote_id=lote_id,
                 contenedor_id=contenedor_id, cantidad=cantidad, ubicacion_origen_id=origen,
                 ubicacion_sugerida_id=sugerida, razon_sugerencia=razon,
                 documento_tipo=documento_tipo, documento_id=documento_id)
    db.add(t)
    await db.flush()
    return t
