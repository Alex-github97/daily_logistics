"""
Servicio de canales de venta: lo que pasa con un pedido desde que llega hasta
que se entrega, y la sincronización del stock con cada plataforma.

    llega el pedido (webhook, consulta periódica o archivo)
      → se registra una sola vez (conector + número de pedido)
      → se mapea cada línea a un producto del WMS
      → si está pagado: orden de salida + alistamiento (reserva FEFO) = COMPROMETIDO
      → picking confirmado: la mercancía pasa al staging de salida = EN_STAGING
      → despacho + viaje en el TMS = DESPACHADO (se avisa a la plataforma con la guía)
      → viaje entregado = ENTREGADO (se avisa a la plataforma)

El stock publicado sale de lo DISPONIBLE en las zonas alistables del almacén
del conector: lo comprometido y lo que está en staging ya no se ofrece.
"""
import logging
from datetime import datetime, timedelta, timezone
from math import floor
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_inventario, wms_operacion as op
from app.core.marketplace.adaptadores import adaptador
from app.core.marketplace.base import ErrorConector, LineaNorm, PedidoNorm
from app.infrastructure.models.marketplace import (
    MKPBitacora, MKPColaEstado, MKPColaStock, MKPConector, MKPPedido, MKPPedidoLinea, MKPPublicacion,
)
from app.infrastructure.models.wms import (
    WMSCliente, WMSDespacho, WMSInventarioUbicacion, WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSPickingDetalle,
    WMSPickingTarea, WMSUbicacion, WMSZona,
)

log = logging.getLogger("uvicorn.error")

ESTADOS_ABIERTOS = ("RECIBIDO", "CON_NOVEDAD", "COMPROMETIDO", "EN_STAGING")


async def registrar(db: AsyncSession, conector_id: Optional[int], tipo: str, ok: bool, mensaje: str) -> None:
    db.add(MKPBitacora(conector_id=conector_id, tipo=tipo, ok=ok, mensaje=mensaje[:2000]))


def guardar_credenciales(conector: MKPConector, ad) -> None:
    if ad.credenciales_cambiaron:
        conector.credenciales = dict(ad.credenciales)


# ── Mapeo de productos ────────────────────────────────────────────────────────

async def resolver_linea(db: AsyncSession, conector: MKPConector, l: LineaNorm) -> Tuple[Optional[int], float]:
    """(producto, unidades por cada unidad vendida). Primero la publicación
    mapeada; si no, el SKU contra el maestro (SKU, código de barras o código de
    empaque: un SKU de caja trae sus 12 unidades)."""
    if l.ref_externa:
        q = select(MKPPublicacion).where(MKPPublicacion.conector_id == conector.id,
                                         MKPPublicacion.ref_externa == str(l.ref_externa),
                                         MKPPublicacion.ref_variante == str(l.ref_variante or ""),
                                         MKPPublicacion.activo.is_(True))
        pub = (await db.execute(q)).scalar()
        if pub and pub.producto_id:
            return pub.producto_id, float(pub.unidades or 1)
    if l.sku:
        from app.api.v1.endpoints.wms_codigos import _resolver
        r = await _resolver(db, l.sku)
        if r and r[0].activo:
            return r[0].id, float(r[2])
    return None, 1.0


async def cliente_del_conector(db: AsyncSession, conector: MKPConector) -> int:
    """El cliente WMS a cuyo nombre quedan las órdenes del canal (se crea solo)."""
    if conector.cliente_id:
        return conector.cliente_id
    codigo = f"CANAL-{conector.id}"
    cli = (await db.execute(select(WMSCliente).where(WMSCliente.codigo == codigo))).scalar()
    if cli is None:
        cli = WMSCliente(codigo=codigo, nombre=f"{conector.nombre} (canal en línea)", segmento="ECOMMERCE", activo=True)
        db.add(cli)
        await db.flush()
    conector.cliente_id = cli.id
    return cli.id


# ── Pedidos ───────────────────────────────────────────────────────────────────

async def ingresar_pedido(db: AsyncSession, conector: MKPConector, p: PedidoNorm,
                          usuario_id: Optional[int] = None) -> MKPPedido:
    """Registra o actualiza un pedido. Idempotente: el mismo pedido no entra dos veces."""
    existente = (await db.execute(select(MKPPedido).where(
        MKPPedido.conector_id == conector.id, MKPPedido.pedido_externo == p.pedido_externo))).scalar()
    if existente:
        existente.estado_externo = p.estado_externo or existente.estado_externo
        if p.cancelado and existente.estado in ESTADOS_ABIERTOS:
            await cancelar_pedido(db, existente, "Cancelado en la plataforma", usuario_id)
        elif existente.estado == "RECIBIDO" and p.pagado and not existente.orden_salida_id:
            await comprometer(db, conector, existente, usuario_id)
        return existente

    pedido = MKPPedido(
        conector_id=conector.id, pedido_externo=p.pedido_externo, estado_externo=p.estado_externo,
        fecha_pedido=p.fecha or datetime.now(timezone.utc), comprador=p.comprador, documento=p.documento,
        telefono=p.telefono, email=p.email, direccion=p.direccion, ciudad=p.ciudad, total=p.total,
        envio_externo=p.envio_externo, crudo=p.crudo, estado="RECIBIDO")
    db.add(pedido)
    await db.flush()
    for l in p.lineas:
        if not l.cantidad or l.cantidad <= 0:
            continue
        pid, unidades = await resolver_linea(db, conector, l)
        db.add(MKPPedidoLinea(pedido_id=pedido.id, ref_externa=l.ref_externa, ref_variante=l.ref_variante, sku_externo=l.sku,
                              titulo=l.titulo, cantidad=l.cantidad, precio=l.precio, producto_id=pid,
                              unidades=(l.cantidad * unidades) if pid else None))
    await db.flush()
    await registrar(db, conector.id, "PEDIDO", True, f"Pedido {p.pedido_externo} recibido ({len(p.lineas)} líneas)")
    if p.cancelado:
        pedido.estado = "CANCELADO"
    elif not p.pagado:
        pedido.novedad = "Esperando confirmación de pago en la plataforma"
    else:
        await comprometer(db, conector, pedido, usuario_id)
    return pedido


async def comprometer(db: AsyncSession, conector: MKPConector, pedido: MKPPedido,
                      usuario_id: Optional[int] = None) -> None:
    """Crea la orden de salida y reserva el inventario (picking FEFO).

    Desde aquí las unidades ya no son disponibles: el stock publicado baja."""
    lineas = (await db.execute(select(MKPPedidoLinea).where(MKPPedidoLinea.pedido_id == pedido.id))).scalars().all()
    sin_mapear = [l.sku_externo or l.titulo or l.ref_externa for l in lineas if not l.producto_id]
    if sin_mapear:
        pedido.estado = "CON_NOVEDAD"
        pedido.novedad = "Productos sin mapear: " + ", ".join(str(x) for x in sin_mapear)
        await registrar(db, conector.id, "PEDIDO", False, f"Pedido {pedido.pedido_externo}: {pedido.novedad}")
        return
    por_producto: Dict[int, float] = {}
    for l in lineas:
        por_producto[l.producto_id] = por_producto.get(l.producto_id, 0) + float(l.unidades or 0)

    from app.api.v1.endpoints.wms import _next_numero, crear_alistamiento
    orden = WMSOrdenSalida(
        numero_orden=await _next_numero(db, WMSOrdenSalida, WMSOrdenSalida.numero_orden, "OS"),
        cliente_id=await cliente_del_conector(db, conector), almacen_id=conector.almacen_id,
        fecha_emision=datetime.now(timezone.utc).date(), estado="PENDIENTE", prioridad="ALTA",
        canal=conector.tipo[:30],
        depositante_id=await op.resolver_depositante(db, None, list(por_producto)))
    db.add(orden)
    await db.flush()
    for pid, cant in por_producto.items():
        db.add(WMSOrdenSalidaDetalle(orden_id=orden.id, producto_id=pid, cantidad_solicitada=cant))
    await db.flush()
    pedido.orden_salida_id = orden.id
    await crear_alistamiento(db, orden.id, "SINGLE", 0, 30, usuario_id)
    await db.flush()

    dets = (await db.execute(select(WMSOrdenSalidaDetalle).where(WMSOrdenSalidaDetalle.orden_id == orden.id))).scalars().all()
    faltan = [(d.producto_id, d.cantidad_solicitada - (d.cantidad_preparada or 0)) for d in dets
              if (d.cantidad_preparada or 0) < d.cantidad_solicitada]
    if faltan:
        pedido.estado = "CON_NOVEDAD"
        pedido.novedad = "Stock insuficiente: " + ", ".join(f"producto {p} faltan {c:g}" for p, c in faltan)
    else:
        pedido.estado = "COMPROMETIDO"
        pedido.novedad = None
    await registrar(db, conector.id, "PEDIDO", not faltan,
                    f"Pedido {pedido.pedido_externo} → orden {orden.numero_orden}"
                    + (f" con novedad: {pedido.novedad}" if faltan else " (inventario comprometido)"))
    # Algunas plataformas exigen «tomar» el pedido (VTEX start-handling, Rappi take).
    try:
        ad = adaptador(conector)
        await ad.confirmar_recepcion(pedido)
        guardar_credenciales(conector, ad)
    except ErrorConector as e:
        await registrar(db, conector.id, "ESTADO", False, f"Pedido {pedido.pedido_externo}: no se pudo confirmar la recepción: {e}")


async def cancelar_pedido(db: AsyncSession, pedido: MKPPedido, motivo: str, usuario_id: Optional[int] = None) -> None:
    """Anula el pedido y libera lo comprometido (lo que esté en staging vuelve a
    disponible allí; hay que reubicarlo)."""
    if pedido.orden_salida_id:
        orden = await db.get(WMSOrdenSalida, pedido.orden_salida_id)
        tareas = (await db.execute(select(WMSPickingTarea).where(WMSPickingTarea.orden_id == pedido.orden_salida_id))).scalars().all()
        for t in tareas:
            dets = (await db.execute(select(WMSPickingDetalle).where(WMSPickingDetalle.tarea_id == t.id))).scalars().all()
            for d in dets:
                reservado = (d.cantidad_pickeada if d.confirmado else d.cantidad_solicitada) - (d.cantidad_despachada or 0)
                if reservado > 0:
                    await wms_inventario.mover(
                        db, tipo="LIBERACION", producto_id=d.producto_id, cantidad=reservado, lote_id=d.lote_id,
                        origen=d.ubicacion_id, destino=d.ubicacion_id, estado_origen="RESERVADO", estado_destino="DISPONIBLE",
                        contenedor_origen=d.contenedor_id, documento_tipo="PICKING", documento_id=t.id,
                        usuario_id=usuario_id, notas=f"Pedido cancelado: {motivo}")
                    if not d.confirmado:
                        d.confirmado, d.cantidad_pickeada = True, 0
            if t.estado != "COMPLETADA":
                t.estado = "CANCELADA"
        if orden and orden.estado not in ("DESPACHADO", "ENTREGADO"):
            orden.estado = "CANCELADO"
    pedido.estado = "CANCELADO"
    pedido.novedad = motivo
    await registrar(db, pedido.conector_id, "PEDIDO", True, f"Pedido {pedido.pedido_externo} cancelado: {motivo}")


async def etapa(db: AsyncSession, pedido: MKPPedido) -> str:
    """El estado real del pedido según su orden: si el picking ya terminó, está
    en staging aunque nadie lo haya actualizado todavía."""
    if pedido.estado in ("COMPROMETIDO", "CON_NOVEDAD") and pedido.orden_salida_id:
        tareas = (await db.execute(select(WMSPickingTarea.estado).where(
            WMSPickingTarea.orden_id == pedido.orden_salida_id))).scalars().all()
        if tareas and all(t == "COMPLETADA" for t in tareas):
            return "EN_STAGING"
    return pedido.estado


# ── Stock ─────────────────────────────────────────────────────────────────────

async def disponible_publicable(db: AsyncSession, almacen_id: int, producto_ids: Iterable[int]) -> Dict[int, float]:
    ids = list(producto_ids)
    if not ids:
        return {}
    filas = (await db.execute(
        select(WMSInventarioUbicacion.producto_id, func.sum(WMSInventarioUbicacion.cantidad_disponible))
        .join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id)
        .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
        .where(WMSZona.almacen_id == almacen_id, WMSZona.tipo.notin_(wms_inventario.ZONAS_NO_ALISTABLES),
               WMSZona.activo.isnot(False), WMSUbicacion.activo.isnot(False),
               WMSInventarioUbicacion.producto_id.in_(ids))
        .group_by(WMSInventarioUbicacion.producto_id))).all()
    salida = {pid: 0.0 for pid in ids}
    salida.update({pid: float(c or 0) for pid, c in filas})
    return salida


async def sincronizar_stock(db: AsyncSession, conector: MKPConector, producto_ids: Optional[Iterable[int]] = None,
                            forzar: bool = False) -> Tuple[int, int]:
    """Publica el stock de las publicaciones mapeadas. Devuelve (enviadas, errores)."""
    ad = adaptador(conector)
    if not ad.capacidades.stock:
        return 0, 0
    q = select(MKPPublicacion).where(MKPPublicacion.conector_id == conector.id, MKPPublicacion.activo.is_(True),
                                     MKPPublicacion.producto_id.isnot(None))
    if producto_ids is not None:
        q = q.where(MKPPublicacion.producto_id.in_(list(producto_ids)))
    pubs = (await db.execute(q)).scalars().all()
    disp = await disponible_publicable(db, conector.almacen_id, {p.producto_id for p in pubs})
    enviadas = errores = 0
    for pub in pubs:
        cantidad = max(0, floor((disp.get(pub.producto_id, 0) - (conector.colchon_stock or 0)) / float(pub.unidades or 1)))
        if not forzar and pub.ultimo_stock_enviado == cantidad:
            continue
        try:
            await ad.publicar_stock(pub, cantidad)
            pub.ultimo_stock_enviado, pub.ultimo_envio, pub.ultimo_error = cantidad, datetime.now(timezone.utc), None
            enviadas += 1
        except ErrorConector as e:
            pub.ultimo_error = str(e)[:1000]
            errores += 1
            await registrar(db, conector.id, "STOCK", False, f"{pub.sku_externo or pub.ref_externa}: {e}")
    guardar_credenciales(conector, ad)
    conector.ultima_sync_stock = datetime.now(timezone.utc)
    if enviadas:
        await registrar(db, conector.id, "STOCK", True, f"Stock publicado en {enviadas} publicaciones")
    return enviadas, errores


async def procesar_cola_stock(db: AsyncSession) -> None:
    ids = (await db.execute(select(MKPColaStock.producto_id))).scalars().all()
    if not ids:
        return
    await db.execute(delete(MKPColaStock).where(MKPColaStock.producto_id.in_(ids)))
    conectores = (await db.execute(select(MKPConector).where(
        MKPConector.activo.is_(True), MKPConector.sincronizar_stock.is_(True)))).scalars().all()
    for c in conectores:
        try:
            await sincronizar_stock(db, c, ids)
        except Exception as e:  # noqa: BLE001 — un conector caído no frena a los demás
            await registrar(db, c.id, "STOCK", False, f"Error sincronizando: {e}")


# ── Estados hacia la plataforma ───────────────────────────────────────────────

async def encolar_estado(db: AsyncSession, pedido_id: int, evento: str) -> None:
    db.add(MKPColaEstado(pedido_id=pedido_id, evento=evento))


async def procesar_cola_estado(db: AsyncSession) -> None:
    pendientes = (await db.execute(select(MKPColaEstado).where(MKPColaEstado.intentos < 10)
                                   .order_by(MKPColaEstado.id).limit(50))).scalars().all()
    for item in pendientes:
        pedido = await db.get(MKPPedido, item.pedido_id)
        conector = await db.get(MKPConector, pedido.conector_id) if pedido else None
        if not pedido or not conector:
            await db.delete(item)
            continue
        ad = adaptador(conector)
        try:
            if item.evento == "ENVIADO" and ad.capacidades.envio:
                envio = await ad.marcar_enviado(pedido, pedido.tracking or "", "Daily Logistics")
                if envio:
                    pedido.envio_externo = envio
            elif item.evento == "ENTREGADO" and ad.capacidades.entrega:
                await ad.marcar_entregado(pedido)
            guardar_credenciales(conector, ad)
            await registrar(db, conector.id, "ESTADO", True, f"Pedido {pedido.pedido_externo}: {item.evento.lower()} informado")
            await db.delete(item)
        except ErrorConector as e:
            item.intentos += 1
            item.ultimo_error = str(e)[:1000]
            await registrar(db, conector.id, "ESTADO", False, f"Pedido {pedido.pedido_externo} ({item.evento}): {e}")


# ── Consulta periódica de pedidos ─────────────────────────────────────────────

async def traer_pedidos(db: AsyncSession, conector: MKPConector) -> int:
    ad = adaptador(conector)
    if not ad.capacidades.pedidos_api:
        return 0
    desde = conector.ultima_sync_pedidos or (datetime.now(timezone.utc) - timedelta(days=2))
    desde = desde - timedelta(minutes=10)      # solape: un pedido en el borde no se pierde
    pedidos = await ad.pedidos_recientes(desde)
    guardar_credenciales(conector, ad)
    for p in pedidos:
        if p:
            await ingresar_pedido(db, conector, p)
    conector.ultima_sync_pedidos = datetime.now(timezone.utc)
    return len(pedidos)


async def tick(db: AsyncSession) -> None:
    """Una vuelta del proceso de fondo en un esquema (empresa)."""
    ahora = datetime.now(timezone.utc)
    conectores = (await db.execute(select(MKPConector).where(MKPConector.activo.is_(True)))).scalars().all()
    for c in conectores:
        minutos = float((c.config or {}).get("consulta_minutos") or (1 if c.tipo == "RAPPI" else 5))
        if c.importar_pedidos and (not c.ultima_sync_pedidos or ahora - c.ultima_sync_pedidos >= timedelta(minutes=minutos)):
            try:
                await traer_pedidos(db, c)
                c.estado_conexion, c.ultimo_error = "OK", None
            except Exception as e:  # noqa: BLE001
                c.estado_conexion, c.ultimo_error = "ERROR", str(e)[:1000]
                c.ultima_sync_pedidos = ahora      # no reintentar en cada vuelta
                await registrar(db, c.id, "CONEXION", False, f"Consulta de pedidos: {e}")
            await db.commit()
    await procesar_cola_estado(db)
    await db.commit()
    await procesar_cola_stock(db)
    await db.commit()


# ── TMS → WMS → plataforma ────────────────────────────────────────────────────

async def viaje_actualizado(db: AsyncSession, despacho_id: int, estado_viaje: str) -> None:
    """El viaje de un despacho cambió: el despacho y la orden lo reflejan, y si
    el pedido vino de un canal, se le avisa a la plataforma."""
    despacho = await db.get(WMSDespacho, despacho_id)
    if not despacho:
        return
    if estado_viaje == "EN_TRANSITO" and despacho.estado in ("PREPARANDO", "LISTO"):
        despacho.estado = "EN_TRANSITO"
    if estado_viaje == "ENTREGADO" and despacho.estado != "ENTREGADO":
        despacho.estado = "ENTREGADO"
        # Sin la fecha real de entrega, el OTIF y el «a tiempo» no la cuentan.
        if not despacho.fecha_entrega_real:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo
            despacho.fecha_entrega_real = _dt.now(ZoneInfo("America/Bogota")).date()
        orden = await db.get(WMSOrdenSalida, despacho.orden_id)
        if orden and orden.estado != "CANCELADO":
            orden.estado = "ENTREGADO"
        pedido = (await db.execute(select(MKPPedido).where(MKPPedido.despacho_id == despacho.id))).scalar()
        if pedido and pedido.estado != "ENTREGADO":
            pedido.estado = "ENTREGADO"
            await encolar_estado(db, pedido.id, "ENTREGADO")
