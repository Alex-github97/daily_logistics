"""
El único camino para mover existencias del WMS.

Todo cambio de stock —recibir, ubicar, trasladar, reservar, bloquear, alistar,
despachar, contar, devolver, vender en el POS— pasa por `mover`. Así:

- la fila de existencia se lee con `FOR UPDATE`: quien llega segundo espera y
  ve el saldo ya descontado;
- una salida mayor que lo que hay en ese estado se RECHAZA (`StockInsuficiente`).
  El ajuste viejo truncaba a cero en silencio y las unidades desaparecían sin
  dejar rastro;
- cada movimiento queda en el kárdex con origen, destino, lote, estiba,
  depositante, almacén, documento, tarea, estados (disponible/reservado/
  bloqueado) y el saldo en que quedaron las dos filas tocadas: el historial de
  una ubicación se puede reconstruir sin consultar nada más;
- las entradas valorizadas recalculan el costo promedio ponderado.

Una fila de existencia es (producto, ubicación, lote, estiba). Sus tres
cantidades son estados de la misma mercancía física: reservar o bloquear es un
movimiento entre estados de la misma fila, que también queda en el kárdex.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.wms import (
    WMSContenedor, WMSInventarioUbicacion, WMSLote, WMSMovimientoInventario, WMSProducto, WMSUbicacion, WMSZona,
)

CUATRO = Decimal("0.0001")
ESTADOS = {"DISPONIBLE": "cantidad_disponible", "RESERVADO": "cantidad_reservada", "BLOQUEADO": "cantidad_bloqueada"}
# Zonas de las que nunca se alista: lo que está ahí no está listo para salir.
ZONAS_NO_ALISTABLES = ("RECEPCION", "CUARENTENA", "DESPACHO", "TRANSITO")
_MISMA = object()


class StockInsuficiente(Exception):
    def __init__(self, producto: str, pedido: Decimal, disponible: Decimal, estado: str = "DISPONIBLE"):
        self.producto, self.pedido, self.disponible = producto, pedido, disponible
        que = {"DISPONIBLE": "existencias disponibles", "RESERVADO": "existencias reservadas",
               "BLOQUEADO": "existencias bloqueadas"}[estado]
        super().__init__(f"No hay {que} suficientes de «{producto}»: se piden {pedido:g}, hay {disponible:g}.")


def _d(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v or 0))


def total_fila(f: WMSInventarioUbicacion) -> float:
    return float(_d(f.cantidad_disponible) + _d(f.cantidad_reservada) + _d(f.cantidad_bloqueada))


async def fila(db: AsyncSession, producto_id: int, ubicacion_id: int, lote_id: Optional[int],
               contenedor_id: Optional[int] = None, crear: bool = False) -> Optional[WMSInventarioUbicacion]:
    """La fila de existencia, bloqueada. Con `crear`, la crea si no existe sin
    pisarse con otra transacción que la esté creando al mismo tiempo."""
    # La sesión no hace autoflush: sin esto, `populate_existing` recargaría la
    # fila desde la base y pisaría un cambio de esta misma petición aún no escrito.
    await db.flush()
    if crear:
        await db.execute(text("""
            INSERT INTO wms_inventario_ubicacion (producto_id, ubicacion_id, lote_id, contenedor_id,
                cantidad_disponible, cantidad_reservada, cantidad_bloqueada, created_at, updated_at)
            VALUES (:p, :u, :l, :c, 0, 0, 0, now(), now())
            ON CONFLICT (producto_id, ubicacion_id, (COALESCE(lote_id, 0)), (COALESCE(contenedor_id, 0)))
            DO NOTHING"""), {"p": producto_id, "u": ubicacion_id, "l": lote_id, "c": contenedor_id})
    q = select(WMSInventarioUbicacion).where(
        WMSInventarioUbicacion.producto_id == producto_id,
        WMSInventarioUbicacion.ubicacion_id == ubicacion_id,
        WMSInventarioUbicacion.lote_id.is_(None) if lote_id is None else WMSInventarioUbicacion.lote_id == lote_id,
        WMSInventarioUbicacion.contenedor_id.is_(None) if contenedor_id is None
        else WMSInventarioUbicacion.contenedor_id == contenedor_id,
    ).with_for_update().execution_options(populate_existing=True)
    return (await db.execute(q)).scalar_one_or_none()


async def almacen_de(db: AsyncSession, ubicacion_id: Optional[int]) -> Optional[int]:
    if not ubicacion_id:
        return None
    return (await db.execute(select(WMSZona.almacen_id).join(WMSUbicacion, WMSUbicacion.zona_id == WMSZona.id)
                             .where(WMSUbicacion.id == ubicacion_id))).scalar()


async def existencia_total(db: AsyncSession, producto_id: int) -> Decimal:
    await db.flush()
    v = (await db.execute(select(func.coalesce(func.sum(
        WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada
        + WMSInventarioUbicacion.cantidad_bloqueada), 0)).where(
        WMSInventarioUbicacion.producto_id == producto_id))).scalar()
    return _d(v)


async def costear_entrada(db: AsyncSession, producto_id: int, cantidad, costo_unitario) -> Decimal:
    """Promedio ponderado: (existencia × costo actual + entrada × costo de la
    entrada) / existencia nueva. Se llama ANTES de sumar la cantidad."""
    prod = (await db.execute(select(WMSProducto).where(WMSProducto.id == producto_id)
                             .with_for_update())).scalar_one()
    cantidad, costo = _d(cantidad), _d(costo_unitario) if costo_unitario is not None else None
    if costo is None or cantidad <= 0:
        return _d(prod.costo_promedio)
    previa = await existencia_total(db, producto_id)
    actual = _d(prod.costo_promedio)
    total = previa + cantidad
    prod.costo_promedio = ((previa * actual + cantidad * costo) / total).quantize(CUATRO, ROUND_HALF_UP) \
        if total > 0 else costo
    return _d(prod.costo_promedio)


async def mover(db: AsyncSession, *, tipo: str, producto_id: int, cantidad, lote_id: Optional[int] = None,
                origen: Optional[int] = None, destino: Optional[int] = None,
                estado_origen: str = "DISPONIBLE", estado_destino: str = "DISPONIBLE",
                contenedor_origen: Optional[int] = None, contenedor_destino=_MISMA,
                documento_tipo: Optional[str] = None, documento_id: Optional[int] = None,
                referencia: Optional[str] = None, usuario_id: Optional[int] = None,
                tarea_id: Optional[int] = None, notas: Optional[str] = None,
                costo_unitario=None) -> WMSMovimientoInventario:
    """Mueve `cantidad` del producto.

    - sin origen: entra (recepción, devolución, sobrante de conteo);
    - sin destino: sale (despacho, venta, faltante de conteo, destrucción);
    - con los dos: traslado, o cambio de estado si es la misma fila.
    """
    cantidad = _d(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad del movimiento debe ser mayor que cero.")
    if origen is None and destino is None:
        raise ValueError("Un movimiento necesita origen, destino o ambos.")
    if contenedor_destino is _MISMA:
        contenedor_destino = contenedor_origen
    prod = await db.get(WMSProducto, producto_id)
    if prod is None:
        raise ValueError(f"El producto {producto_id} no existe.")

    # Solo las entradas valorizadas mueven el costo promedio (antes de sumar).
    if origen is None and costo_unitario is not None:
        costo = await costear_entrada(db, producto_id, cantidad, costo_unitario)
        costo_mov = _d(costo_unitario)
    else:
        costo_mov = _d(prod.costo_promedio)

    f_origen = f_destino = None
    if origen is not None:
        f_origen = await fila(db, producto_id, origen, lote_id, contenedor_origen)
        col = ESTADOS[estado_origen]
        hay = _d(getattr(f_origen, col)) if f_origen else Decimal(0)
        if f_origen is None or hay < cantidad:
            raise StockInsuficiente(prod.nombre, cantidad, hay, estado_origen)
        setattr(f_origen, col, float(hay - cantidad))
    if destino is not None:
        misma = origen == destino and contenedor_destino == contenedor_origen
        f_destino = f_origen if misma else await fila(db, producto_id, destino, lote_id, contenedor_destino, crear=True)
        col = ESTADOS[estado_destino]
        setattr(f_destino, col, float(_d(getattr(f_destino, col)) + cantidad))

    if contenedor_destino and destino is not None:
        cont = await db.get(WMSContenedor, contenedor_destino)
        if cont is not None:
            cont.ubicacion_id = destino
            if cont.estado == "VACIO":
                cont.estado = "ABIERTO"

    mov = WMSMovimientoInventario(
        tipo=tipo, producto_id=producto_id, lote_id=lote_id, cantidad=float(cantidad),
        ubicacion_origen_id=origen, ubicacion_destino_id=destino,
        contenedor_id=contenedor_origen if origen is not None else contenedor_destino,
        contenedor_destino_id=contenedor_destino if destino is not None else None,
        depositante_id=prod.depositante_id, almacen_id=await almacen_de(db, destino or origen),
        documento_tipo=documento_tipo, documento_id=documento_id, tarea_id=tarea_id,
        estado_origen=estado_origen if origen is not None else None,
        estado_destino=estado_destino if destino is not None else None,
        saldo_origen=total_fila(f_origen) if f_origen is not None else None,
        saldo_destino=total_fila(f_destino) if f_destino is not None else None,
        costo_unitario=costo_mov, referencia_documento=referencia, usuario_id=usuario_id, notas=notas)
    db.add(mov)
    if contenedor_origen and contenedor_origen != contenedor_destino:
        await db.flush()
        await revisar_contenedor(db, contenedor_origen)
    return mov


async def revisar_contenedor(db: AsyncSession, contenedor_id: int) -> None:
    """Una estiba que se quedó sin nada pasa a VACIA (salvo si ya se despachó)."""
    queda = (await db.execute(select(func.coalesce(func.sum(
        WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada
        + WMSInventarioUbicacion.cantidad_bloqueada), 0)).where(
        WMSInventarioUbicacion.contenedor_id == contenedor_id))).scalar()
    cont = await db.get(WMSContenedor, contenedor_id)
    if cont is not None and _d(queda) <= 0 and cont.estado not in ("DESPACHADO", "ANULADO"):
        cont.estado = "VACIO"


# ── Atajos que usa el POS ─────────────────────────────────────────────────────

async def entrar(db: AsyncSession, *, producto_id: int, ubicacion_id: int, lote_id: Optional[int],
                 cantidad, tipo: str, referencia: Optional[str], usuario_id: Optional[int],
                 notas: Optional[str] = None, costo_unitario=None, contenedor_id: Optional[int] = None,
                 documento_tipo: Optional[str] = None, documento_id: Optional[int] = None) -> WMSMovimientoInventario:
    return await mover(db, tipo=tipo, producto_id=producto_id, cantidad=cantidad, lote_id=lote_id,
                       destino=ubicacion_id, contenedor_destino=contenedor_id, referencia=referencia,
                       usuario_id=usuario_id, notas=notas, costo_unitario=costo_unitario,
                       documento_tipo=documento_tipo, documento_id=documento_id)


async def sacar(db: AsyncSession, *, producto_id: int, ubicacion_id: int, lote_id: Optional[int],
                cantidad, tipo: str, referencia: Optional[str], usuario_id: Optional[int],
                notas: Optional[str] = None, contenedor_id: Optional[int] = None,
                documento_tipo: Optional[str] = None, documento_id: Optional[int] = None) -> WMSMovimientoInventario:
    return await mover(db, tipo=tipo, producto_id=producto_id, cantidad=cantidad, lote_id=lote_id,
                       origen=ubicacion_id, contenedor_origen=contenedor_id, referencia=referencia,
                       usuario_id=usuario_id, notas=notas, documento_tipo=documento_tipo, documento_id=documento_id)


# ── Elegir de dónde sale ──────────────────────────────────────────────────────

@dataclass
class Asignacion:
    ubicacion_id: int
    lote_id: Optional[int]
    cantidad: Decimal
    contenedor_id: Optional[int] = None
    vence: Optional[date] = None


def _lote_vigente(minimo: date):
    return (WMSLote.id.is_(None)) | ((WMSLote.activo.isnot(False)) &
                                     ((WMSLote.fecha_vencimiento.is_(None)) | (WMSLote.fecha_vencimiento >= minimo)))


async def ubicaciones_vendibles(db: AsyncSession, almacen_id: int) -> List[int]:
    return list((await db.execute(select(WMSUbicacion.id).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
        WMSZona.almacen_id == almacen_id, WMSZona.vendible_pos.is_(True), WMSZona.activo.isnot(False),
        WMSUbicacion.activo.isnot(False)))).scalars())


async def ubicacion_de_zona(db: AsyncSession, almacen_id: int, tipo_zona: str) -> Optional[int]:
    """La primera ubicación activa de la zona de ese tipo en el almacén."""
    return (await db.execute(select(WMSUbicacion.id).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
        WMSZona.almacen_id == almacen_id, WMSZona.tipo == tipo_zona, WMSZona.activo.isnot(False),
        WMSUbicacion.activo.isnot(False)).order_by(WMSUbicacion.codigo).limit(1))).scalar()


async def disponible_en(db: AsyncSession, producto_ids: Sequence[int], ubicacion_ids: Sequence[int]) -> dict:
    """Disponible por producto en esas ubicaciones (sin lotes vencidos ni bloqueados)."""
    if not producto_ids or not ubicacion_ids:
        return {}
    filas = (await db.execute(
        select(WMSInventarioUbicacion.producto_id, func.sum(WMSInventarioUbicacion.cantidad_disponible))
        .outerjoin(WMSLote, WMSLote.id == WMSInventarioUbicacion.lote_id)
        .where(WMSInventarioUbicacion.producto_id.in_(producto_ids),
               WMSInventarioUbicacion.ubicacion_id.in_(ubicacion_ids),
               WMSInventarioUbicacion.cantidad_disponible > 0, _lote_vigente(date.today()))
        .group_by(WMSInventarioUbicacion.producto_id))).all()
    return {pid: _d(n) for pid, n in filas}


async def _asignar(db: AsyncSession, producto_id: int, cantidad, filtro, parcial: bool,
                   minimo: date) -> List[Asignacion]:
    cantidad = _d(cantidad)
    await db.flush()
    filas = (await db.execute(
        select(WMSInventarioUbicacion, WMSLote.fecha_vencimiento)
        .join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id)
        .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
        .outerjoin(WMSLote, WMSLote.id == WMSInventarioUbicacion.lote_id)
        .where(WMSInventarioUbicacion.producto_id == producto_id, WMSInventarioUbicacion.cantidad_disponible > 0,
               WMSUbicacion.activo.isnot(False), _lote_vigente(minimo), *filtro)
        # FEFO; a igual vencimiento, primero lo suelto y lo que menos queda
        # (vacía ubicaciones en vez de abrir otra estiba).
        .order_by(WMSLote.fecha_vencimiento.asc().nullslast(), WMSInventarioUbicacion.contenedor_id.asc().nullsfirst(),
                  WMSInventarioUbicacion.cantidad_disponible.asc(), WMSInventarioUbicacion.id)
        .with_for_update(of=WMSInventarioUbicacion))).all()
    faltan, salida = cantidad, []
    for f, vence in filas:
        if faltan <= 0:
            break
        tomar = min(faltan, _d(f.cantidad_disponible))
        salida.append(Asignacion(f.ubicacion_id, f.lote_id, tomar, f.contenedor_id, vence))
        faltan -= tomar
    if faltan > 0 and not parcial:
        prod = await db.get(WMSProducto, producto_id)
        raise StockInsuficiente(prod.nombre if prod else str(producto_id), cantidad, cantidad - faltan)
    return salida


async def asignar_fefo(db: AsyncSession, producto_id: int, ubicacion_ids: Sequence[int],
                       cantidad) -> List[Asignacion]:
    """POS: de qué ubicaciones vendibles sale una venta (todo o nada)."""
    return await _asignar(db, producto_id, cantidad, [WMSInventarioUbicacion.ubicacion_id.in_(ubicacion_ids)],
                          False, date.today())


async def asignar_alistamiento(db: AsyncSession, producto_id: int, almacen_id: int, cantidad,
                               lote_id: Optional[int] = None, dias_vida_minima: int = 0) -> List[Asignacion]:
    """Picking: FEFO en las zonas alistables del almacén, nunca de recepción,
    cuarentena ni despacho, y con la vida útil mínima que exige el cliente.
    Puede quedar corto: lo que falta lo reporta quien llama."""
    filtro = [WMSZona.almacen_id == almacen_id, WMSZona.tipo.notin_(ZONAS_NO_ALISTABLES), WMSZona.activo.isnot(False)]
    if lote_id:
        filtro.append(WMSInventarioUbicacion.lote_id == lote_id)
    return await _asignar(db, producto_id, cantidad, filtro, True, date.today() + timedelta(days=dias_vida_minima))


async def multiplo_de_empaque(db: AsyncSession, producto_id: int, cantidad) -> Decimal:
    """El empaque más grande (caja, máster, estiba) que la cantidad completa
    exacto: 24 und de un producto en cajas de 12 → 12. 1 si no aplica."""
    from app.infrastructure.models.wms import WMSProductoEmpaque
    c = _d(cantidad)
    unidades = (await db.execute(select(WMSProductoEmpaque.unidades).where(
        WMSProductoEmpaque.producto_id == producto_id, WMSProductoEmpaque.nivel != "UNIDAD"))).scalars().all()
    validos = [_d(u) for u in unidades if u and _d(u) > 1 and c % _d(u) == 0]
    return max(validos, default=Decimal(1))


async def asignar_por_empaque(db: AsyncSession, producto_id: int, almacen_id: int, cantidad,
                              lote_id: Optional[int] = None, dias_vida_minima: int = 0,
                              multiplo=None) -> List[Asignacion]:
    """Como `asignar_alistamiento` (FEFO, zonas alistables), pero si lo pedido son
    empaques completos (2 cajas de 12) primero toma empaques completos de cada
    ubicación y solo lo que falte sale suelto. Así dos cajas no salen como «10 de
    aquí y 14 de allá» cuando una ubicación las tiene completas.

    `multiplo` None = se deduce de los empaques del producto."""
    m = _d(multiplo) if multiplo else await multiplo_de_empaque(db, producto_id, cantidad)
    if m <= 1:
        return await asignar_alistamiento(db, producto_id, almacen_id, cantidad, lote_id, dias_vida_minima)
    # Todo lo disponible, en orden FEFO (queda bloqueado para esta transacción).
    filas = await asignar_alistamiento(db, producto_id, almacen_id, Decimal(10) ** 9, lote_id, dias_vida_minima)
    tomado = [Decimal(0)] * len(filas)
    faltan = _d(cantidad)
    for i, f in enumerate(filas):                       # 1) empaques completos
        if faltan < m:
            break
        n = min(_d(f.cantidad) // m, faltan // m)
        tomado[i] += n * m
        faltan -= n * m
    for i, f in enumerate(filas):                       # 2) lo que quede, suelto
        if faltan <= 0:
            break
        t = min(faltan, _d(f.cantidad) - tomado[i])
        if t > 0:
            tomado[i] += t
            faltan -= t
    salida = []
    for f, t in zip(filas, tomado):
        if t > 0:
            f.cantidad = t
            salida.append(f)
    return salida


# ── Staging de salida ─────────────────────────────────────────────────────────
#
# El área de preparación de despachos: lo ya alistado espera aquí al vehículo.
# Es una zona tipo DESPACHO (no se alista, no se vende en POS, no se factura
# como almacenaje) con una ubicación, y se crea sola la primera vez.

async def ubicacion_staging(db: AsyncSession, almacen_id: int) -> int:
    """La ubicación de staging de salida del almacén (la crea si no existe)."""
    existente = (await db.execute(
        select(WMSUbicacion.id).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
        .where(WMSZona.almacen_id == almacen_id, WMSZona.tipo == "DESPACHO",
               WMSZona.activo.isnot(False), WMSUbicacion.activo.isnot(False))
        .order_by(WMSUbicacion.id).limit(1))).scalar()
    if existente:
        return existente
    from app.infrastructure.models.wms import WMSAlmacen
    alm = await db.get(WMSAlmacen, almacen_id)
    base = f"STG-{(alm.codigo if alm else almacen_id)}"[:24]
    zona = (await db.execute(select(WMSZona).where(
        WMSZona.almacen_id == almacen_id, WMSZona.tipo == "DESPACHO").limit(1))).scalar()
    if zona is None:
        zona = WMSZona(almacen_id=almacen_id, codigo=base, nombre="Staging de salida (pedidos por despachar)",
                       tipo="DESPACHO", activo=True)
        db.add(zona)
        await db.flush()
    ub = WMSUbicacion(zona_id=zona.id, codigo=f"{base}-01", tipo="ESTANDAR", activo=True)
    db.add(ub)
    await db.flush()
    return ub.id
