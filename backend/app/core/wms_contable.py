"""
Lo que el WMS le cuenta al ERP.

Antes solo el POS escribía en la contabilidad: la bodega recibía, despachaba y
ajustaba sin que el ERP se enterara, y la cuenta de inventario quedaba en
negativo porque el POS la acreditaba al vender lo que nadie había debitado al
comprar. Acá se contabiliza cada hecho que cambia el VALOR del inventario:

  recepción     inventario        / mercancía recibida por facturar (220510)
  despacho      costo de ventas   / inventario, y la factura de venta
  devolución    inventario        / costo de ventas, y la nota crédito
  faltante      merma             / inventario
  sobrante      inventario        / sobrantes

El valor sale del kárdex: cada movimiento ya lleva su costo unitario (el de la
compra al entrar, el promedio al salir), así que lo contabilizado es
exactamente lo que movió el inventario. Cada movimiento contabilizado guarda su
comprobante, y un movimiento con comprobante no se vuelve a contabilizar.

Solo la mercancía PROPIA. La de un depositante 3PL está en la bodega pero no es
de la empresa: no es inventario suyo y su servicio se cobra por la liquidación.

Si la empresa no ha configurado Finanzas (no hay empresa en el ERP), no se
contabiliza nada: el WMS funciona solo. Si la configuró y el asiento no se puede
hacer (período cerrado, regla faltante), la operación falla, igual que en el
POS: es lo que impide que quede mercancía movida sin su asiento.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import erp_motor, facturacion_dian as dian
from app.core.wms_operacion import depositante_propio
from app.infrastructure.models.erp import (
    ERPEmpresa, ERPFacturaCliente, ERPLineaFacturaCliente, EstadoFactura, TipoComprobante,
)
from app.infrastructure.models.erp_facturacion import (
    ERPLineaNotaCredito, ERPNotaCreditoCliente, ERPResolucionFacturacion,
)
from app.infrastructure.models.erp_nucleo import ERPTercero
from app.infrastructure.models.wms import (
    WMSCliente, WMSDespacho, WMSDespachoDetalle, WMSDevolucion, WMSMovimientoInventario as M,
    WMSOrdenCompra, WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSProducto, WMSProveedor, WMSRecepcion,
)

CENT = Decimal("0.01")


def r2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, ROUND_HALF_UP)


def hoy():
    """Fecha de Bogotá: un despacho a las 8 p. m. es de hoy, no de mañana UTC."""
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


async def empresa(db: AsyncSession) -> Optional[ERPEmpresa]:
    return (await db.execute(select(ERPEmpresa).order_by(ERPEmpresa.id).limit(1))).scalar()


def valor(movs: Iterable[M]) -> Decimal:
    return sum((r2(Decimal(str(m.cantidad)) * Decimal(str(m.costo_unitario or 0))) for m in movs), Decimal(0))


async def _propios(db: AsyncSession, documento_tipo: str, documento_id: int, sentido: str,
                   tipos: Optional[Iterable[str]] = None) -> List[M]:
    """Movimientos sin contabilizar de un documento, de mercancía propia.
    `sentido`: ENTRADA (llega de fuera de la bodega) o SALIDA (se va de ella)."""
    await db.flush()
    propio = await depositante_propio(db)
    q = select(M).where(M.documento_tipo == documento_tipo, M.documento_id == documento_id,
                        M.comprobante_id.is_(None),
                        or_(M.depositante_id == propio, M.depositante_id.is_(None)))
    if sentido == "ENTRADA":
        q = q.where(M.ubicacion_origen_id.is_(None), M.ubicacion_destino_id.isnot(None))
    else:
        q = q.where(M.ubicacion_origen_id.isnot(None), M.ubicacion_destino_id.is_(None))
    if tipos:
        q = q.where(M.tipo.in_(list(tipos)))
    return list((await db.execute(q)).scalars())


async def _asentar(db, emp: ERPEmpresa, evento: str, concepto: str, lineas, usuario: str,
                   documento_tipo: str, documento_id: int, numero: str, movs: List[M]):
    try:
        comp = await erp_motor.asentar(db, empresa_id=emp.id, evento=evento, tipo=TipoComprobante.DIARIO,
                                       fecha=hoy(), concepto=concepto, lineas=lineas, usuario=usuario,
                                       documento_tipo=documento_tipo, documento_id=documento_id,
                                       documento_numero=numero)
    except erp_motor.ErrorContable as e:
        raise HTTPException(422, f"No se pudo contabilizar en Finanzas: {e.detail if hasattr(e, 'detail') else e}")
    for m in movs:
        m.comprobante_id = comp.id
    return comp


async def tercero(db, emp: ERPEmpresa, nombre: str, nit: Optional[str], email: Optional[str] = None,
                  cliente: bool = False, proveedor: bool = False) -> Optional[ERPTercero]:
    if not nit:
        return None
    nit = nit.split("-")[0].strip()
    t = (await db.execute(select(ERPTercero).where(ERPTercero.empresa_id == emp.id,
                                                  ERPTercero.numero_identificacion == nit))).scalar_one_or_none()
    if t is None:
        es_nit = len(nit) >= 9 and nit.startswith(("8", "9"))
        t = ERPTercero(empresa_id=emp.id, tipo_identificacion="NIT" if es_nit else "CC", numero_identificacion=nit,
                       razon_social=nombre, email=email, es_persona_natural=not es_nit,
                       es_cliente=cliente, es_proveedor=proveedor, origen="WMS")
        db.add(t)
        await db.flush()
    else:
        t.es_cliente = t.es_cliente or cliente
        t.es_proveedor = t.es_proveedor or proveedor
    return t


# ─── Recepción ────────────────────────────────────────────────────────────────

async def contabilizar_recepcion(db: AsyncSession, rec: WMSRecepcion, usuario: str):
    emp = await empresa(db)
    if emp is None:
        return None
    movs = await _propios(db, "RECEPCION", rec.id, "ENTRADA")
    total = valor(movs)
    if total <= 0:
        return None
    prov = None
    if rec.orden_compra_id:
        oc = await db.get(WMSOrdenCompra, rec.orden_compra_id)
        p = await db.get(WMSProveedor, oc.proveedor_id) if oc else None
        prov = await tercero(db, emp, p.nombre, p.nit, p.email, proveedor=True) if p else None
    tid = prov.id if prov else None
    return await _asentar(db, emp, "INVENTARIO_ENTRADA", f"Recepción {rec.numero_recepcion}",
                          [erp_motor.Linea("inventario", debito=total, tercero_id=tid),
                           erp_motor.Linea("por_facturar", credito=total, tercero_id=tid)],
                          usuario, "wms_recepcion", rec.id, rec.numero_recepcion, movs)


async def valor_por_facturar(db: AsyncSession, rec: WMSRecepcion) -> Decimal:
    """Lo que la recepción dejó en «mercancía recibida por facturar»."""
    movs = (await db.execute(select(M).where(M.documento_tipo == "RECEPCION", M.documento_id == rec.id,
                                             M.comprobante_id.isnot(None),
                                             M.ubicacion_origen_id.is_(None)))).scalars()
    return valor(movs)


# ─── Despacho y factura de venta ──────────────────────────────────────────────

async def contabilizar_despacho(db: AsyncSession, despacho: WMSDespacho, usuario: str):
    """El costo de lo que salió, siempre; la factura, si se puede (si no, queda
    pendiente con el motivo y se factura después desde el despacho)."""
    emp = await empresa(db)
    if emp is None:
        return None
    movs = await _propios(db, "DESPACHO", despacho.id, "SALIDA", ("DESPACHO",))
    costo = valor(movs)
    if costo > 0:
        await _asentar(db, emp, "INVENTARIO_SALIDA", f"Costo del despacho {despacho.numero_despacho}",
                       [erp_motor.Linea("costo_venta", debito=costo), erp_motor.Linea("inventario", credito=costo)],
                       usuario, "wms_despacho", despacho.id, despacho.numero_despacho, movs)
    if not movs:
        return None   # nada propio: mercancía de un 3PL, que no se vende sino que se custodia
    try:
        async with db.begin_nested():
            await facturar_despacho(db, despacho, usuario)
    except HTTPException as e:
        despacho.aviso_factura = str(e.detail)[:300]


async def _lineas_venta(db, despacho: WMSDespacho, precios: Optional[Dict[int, float]]):
    """Lo propio del despacho, con su precio (de la orden o el que se indique)."""
    propio = await depositante_propio(db)
    dets = (await db.execute(select(WMSDespachoDetalle, WMSProducto).join(
        WMSProducto, WMSProducto.id == WMSDespachoDetalle.producto_id).where(
        WMSDespachoDetalle.despacho_id == despacho.id))).all()
    precio_orden = {d.producto_id: d.precio_unitario for d in (await db.execute(select(WMSOrdenSalidaDetalle).where(
        WMSOrdenSalidaDetalle.orden_id == despacho.orden_id))).scalars()}
    lineas, sin_precio = [], []
    for det, prod in dets:
        if prod.depositante_id not in (None, propio):
            continue
        precio = (precios or {}).get(prod.id, precio_orden.get(prod.id))
        if precio is None or precio <= 0:
            sin_precio.append(prod.sku)
            continue
        base = r2(Decimal(str(det.cantidad)) * Decimal(str(precio)))
        tarifa = Decimal(str(prod.tarifa_iva or 0))
        lineas.append({"producto": prod, "cantidad": Decimal(str(det.cantidad)), "precio": r2(precio),
                       "base": base, "tarifa": tarifa, "iva": r2(base * tarifa / 100)})
    return lineas, sin_precio


async def resolucion_vigente(db, empresa_id: int) -> ERPResolucionFacturacion:
    h = hoy()
    res = (await db.execute(select(ERPResolucionFacturacion).where(
        ERPResolucionFacturacion.empresa_id == empresa_id, ERPResolucionFacturacion.tipo_documento == "FACTURA_VENTA",
        ERPResolucionFacturacion.activa.is_(True), ERPResolucionFacturacion.vigencia_desde <= h,
        ERPResolucionFacturacion.vigencia_hasta >= h).order_by(ERPResolucionFacturacion.id))).scalars().first()
    if res is None:
        raise HTTPException(422, "No hay resolución de factura electrónica de venta vigente: registre una en "
                                 "POS · Configuración → Resoluciones DIAN y facture desde el despacho.")
    return res


async def facturar_despacho(db: AsyncSession, despacho: WMSDespacho, usuario: str,
                            precios: Optional[Dict[int, float]] = None) -> ERPFacturaCliente:
    if despacho.factura_id:
        raise HTTPException(409, "El despacho ya está facturado.")
    emp = await empresa(db)
    if emp is None:
        raise HTTPException(422, "Configure primero la empresa en Finanzas: la factura necesita emisor.")
    orden = await db.get(WMSOrdenSalida, despacho.orden_id)
    cli = await db.get(WMSCliente, orden.cliente_id)
    lineas, sin_precio = await _lineas_venta(db, despacho, precios)
    if sin_precio:
        raise HTTPException(422, f"La orden {orden.numero_orden} no tiene precio para {', '.join(sin_precio)}: "
                                 "indíquelo al facturar el despacho.")
    if not lineas:
        raise HTTPException(422, "El despacho no tiene mercancía propia que facturar.")
    if not cli or not cli.nit:
        raise HTTPException(422, f"El cliente {cli.nombre if cli else ''} no tiene NIT: complételo y facture desde el despacho.")
    res = await resolucion_vigente(db, emp.id)
    t = await tercero(db, emp, cli.nombre, cli.nit, cli.email, cliente=True)
    try:
        numero, res = await dian.tomar_numero(db, res.id)
    except dian.ResolucionInvalida as e:
        raise HTTPException(409, str(e))
    subtotal = sum((l["base"] for l in lineas), Decimal(0))
    iva = sum((l["iva"] for l in lineas), Decimal(0))
    total = subtotal + iva
    h, momento = hoy(), datetime.now(timezone.utc)
    fac = ERPFacturaCliente(
        empresa_id=emp.id, numero=numero, cliente_nombre=t.razon_social or cli.nombre,
        cliente_nit=t.numero_identificacion, cliente_email=cli.email, fecha=h,
        fecha_vencimiento=h + timedelta(days=30), subtotal=subtotal, total_impuestos=iva, total=total, saldo=total,
        estado=EstadoFactura.EMITIDA, moneda="COP",
        concepto=f"Despacho {despacho.numero_despacho} · orden {orden.numero_orden}",
        cufe=dian.codigo_unico(numero, h, dian.hora_colombia(momento), subtotal, iva, 0, 0, total, emp.nit,
                               t.numero_identificacion, res.clave_tecnica, res.ambiente),
        numero_electronico=numero, resolucion_id=res.id, origen="WMS", estado_dian="POR_TRANSMITIR")
    db.add(fac)
    await db.flush()
    for l in lineas:
        db.add(ERPLineaFacturaCliente(
            factura_id=fac.id, descripcion=f"{l['producto'].sku} · {l['producto'].nombre}"[:500],
            cantidad=l["cantidad"], precio_unitario=l["precio"], descuento_pct=0, subtotal=l["base"],
            total_impuesto=l["iva"], total=l["base"] + l["iva"]))
    asiento = [erp_motor.Linea("cartera", debito=total, tercero_id=t.id),
               erp_motor.Linea("ingreso", credito=subtotal, tercero_id=t.id)]
    if iva:
        asiento.append(erp_motor.Linea("iva_generado", credito=iva, tercero_id=t.id))
    try:
        await erp_motor.asentar(db, empresa_id=emp.id, evento="VENTA_FACTURA", tipo=TipoComprobante.DIARIO, fecha=h,
                                concepto=f"Factura {numero} - {cli.nombre} (despacho {despacho.numero_despacho})",
                                lineas=asiento, usuario=usuario, documento_tipo="factura_cliente",
                                documento_id=fac.id, documento_numero=numero)
    except erp_motor.ErrorContable as e:
        raise HTTPException(422, f"No se pudo contabilizar la factura: {e.detail if hasattr(e, 'detail') else e}")
    despacho.factura_id, despacho.aviso_factura = fac.id, None
    return fac


# ─── Devolución del cliente ───────────────────────────────────────────────────

async def contabilizar_devolucion(db: AsyncSession, dev: WMSDevolucion, usuario: str):
    """Lo que vuelve a la bodega revierte su costo de venta; y si lo despachado
    estaba facturado, la nota crédito por lo devuelto (aunque se destruya: el
    cliente igual lo devolvió)."""
    emp = await empresa(db)
    if emp is None or dev.tipo != "CLIENTE":
        return None
    movs = await _propios(db, "DEVOLUCION", dev.id, "ENTRADA")
    costo = valor(movs)
    if costo > 0:
        await _asentar(db, emp, "INVENTARIO_DEVOLUCION", f"Devolución {dev.numero_devolucion}: reingreso al inventario",
                       [erp_motor.Linea("inventario", debito=costo), erp_motor.Linea("costo_venta", credito=costo)],
                       usuario, "wms_devolucion", dev.id, dev.numero_devolucion, movs)
    if dev.nota_credito_id or not dev.orden_referencia_id:
        return None
    fac = (await db.execute(select(ERPFacturaCliente).join(WMSDespacho, WMSDespacho.factura_id == ERPFacturaCliente.id)
                            .where(WMSDespacho.orden_id == dev.orden_referencia_id)
                            .order_by(WMSDespacho.id))).scalars().first()
    if fac is None:
        return None
    propio = await depositante_propio(db)
    precio = {d.producto_id: d.precio_unitario for d in (await db.execute(select(WMSOrdenSalidaDetalle).where(
        WMSOrdenSalidaDetalle.orden_id == dev.orden_referencia_id))).scalars()}
    nc_lineas, subtotal, iva = [], Decimal(0), Decimal(0)
    for det in dev.detalles:
        prod = await db.get(WMSProducto, det.producto_id)
        if prod.depositante_id not in (None, propio) or not precio.get(det.producto_id):
            continue
        cant = Decimal(str(det.cantidad))
        base = r2(cant * Decimal(str(precio[det.producto_id])))
        imp = r2(base * Decimal(str(prod.tarifa_iva or 0)) / 100)
        subtotal += base
        iva += imp
        nc_lineas.append(ERPLineaNotaCredito(descripcion=f"{prod.sku} · {prod.nombre}"[:500], cantidad=cant,
                                             precio_unitario=r2(precio[det.producto_id]), tarifa_iva=prod.tarifa_iva or 0,
                                             subtotal=base, impuesto=imp, total=base + imp))
    total = subtotal + iva
    if total <= 0:
        return None
    n_prev = (await db.execute(select(func.count()).select_from(ERPNotaCreditoCliente).where(
        ERPNotaCreditoCliente.factura_id == fac.id))).scalar() or 0
    numero = f"NC{fac.numero}-{n_prev + 1}"
    res = await db.get(ERPResolucionFacturacion, fac.resolucion_id) if fac.resolucion_id else None
    h, momento = hoy(), datetime.now(timezone.utc)
    nota = ERPNotaCreditoCliente(
        empresa_id=emp.id, numero=numero, factura_id=fac.id, fecha=h, concepto="1",
        motivo=dev.motivo or "Devolución de mercancía", subtotal=subtotal, total_impuestos=iva, total=total,
        cude=dian.codigo_unico(numero, h, dian.hora_colombia(momento), subtotal, iva, 0, 0, total, emp.nit,
                               fac.cliente_nit, res.clave_tecnica if res else "", res.ambiente if res else "2"),
        origen="WMS", creado_por=usuario, lineas=nc_lineas)
    db.add(nota)
    await db.flush()
    t = (await db.execute(select(ERPTercero).where(ERPTercero.empresa_id == emp.id,
                                                  ERPTercero.numero_identificacion == fac.cliente_nit))).scalar()
    tid = t.id if t else None
    lineas = [erp_motor.Linea("ingreso", debito=subtotal, tercero_id=tid),
              erp_motor.Linea("cartera", credito=total, tercero_id=tid)]
    if iva:
        lineas.append(erp_motor.Linea("iva_generado", debito=iva, tercero_id=tid))
    try:
        comp = await erp_motor.asentar(db, empresa_id=emp.id, evento="VENTA_NOTA_CREDITO", tipo=TipoComprobante.DIARIO,
                                       fecha=h, concepto=f"Nota crédito {numero} - devolución {dev.numero_devolucion}",
                                       lineas=lineas, usuario=usuario, documento_tipo="nota_credito",
                                       documento_id=nota.id, documento_numero=numero)
    except erp_motor.ErrorContable as e:
        raise HTTPException(422, f"No se pudo contabilizar la nota crédito: {e.detail if hasattr(e, 'detail') else e}")
    nota.comprobante_id = comp.id
    fac.saldo = max(Decimal(0), r2(fac.saldo) - total)
    dev.nota_credito_id = nota.id
    return nota


# ─── Faltantes y sobrantes ────────────────────────────────────────────────────

async def contabilizar_ajuste(db: AsyncSession, movs: List[M], usuario: str, concepto: str,
                              documento_tipo: str, documento_id: Optional[int]):
    """Un ajuste (manual, por conteo, por baja o por faltante en tránsito):
    lo que falta es merma y lo que sobra, sobrante."""
    emp = await empresa(db)
    if emp is None or not movs:
        return
    await db.flush()
    propio = await depositante_propio(db)
    movs = [m for m in movs if m.comprobante_id is None and m.depositante_id in (None, propio)]
    menos = [m for m in movs if m.ubicacion_origen_id and not m.ubicacion_destino_id]
    mas = [m for m in movs if m.ubicacion_destino_id and not m.ubicacion_origen_id]
    ref = f"{documento_tipo}-{documento_id}" if documento_id else documento_tipo
    if valor(menos) > 0:
        v = valor(menos)
        await _asentar(db, emp, "INVENTARIO_MERMA", f"{concepto}: faltante", [
            erp_motor.Linea("merma", debito=v), erp_motor.Linea("inventario", credito=v)],
            usuario, documento_tipo, documento_id or 0, ref, menos)
    if valor(mas) > 0:
        v = valor(mas)
        await _asentar(db, emp, "INVENTARIO_SOBRANTE", f"{concepto}: sobrante", [
            erp_motor.Linea("inventario", debito=v), erp_motor.Linea("sobrante", credito=v)],
            usuario, documento_tipo, documento_id or 0, ref, mas)
