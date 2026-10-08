"""
La venta y la devolución del POS, en una sola transacción cada una.

VENTA. Precios de la lista de la caja (el cliente no los manda: los toma el
servidor), descuento hasta el tope de la caja, IVA discriminado dentro del
precio, existencias asignadas por FEFO en las zonas vendibles del almacén y
bloqueadas mientras se descuentan, número de la resolución DIAN, CUFE, factura
en el ERP ya pagada y un solo comprobante contable:

    caja (efectivo) + banco (los demás medios)  =  ingreso + IVA generado
    costo de ventas                              =  inventario

Si cualquier paso falla —no hay existencia, la resolución venció, falta una
regla contable— no queda nada a medias: ni existencia descontada, ni número
gastado, ni factura, ni asiento.

DEVOLUCIÓN. Lo que vuelve en buen estado regresa a la ubicación de donde salió
(vendible); lo dañado va a la zona de cuarentena del almacén. Nota crédito con
CUDE en el ERP y el asiento inverso.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import erp_motor, facturacion_dian as dian, wms_inventario as inv
from app.infrastructure.models.erp import (
    ERPEmpresa, ERPFacturaCliente, ERPLineaFacturaCliente, EstadoFactura, TipoComprobante,
)
from app.infrastructure.models.erp_facturacion import ERPLineaNotaCredito, ERPNotaCreditoCliente
from app.infrastructure.models.erp_nucleo import ERPTercero
from app.infrastructure.models.pos import (
    MedioPagoPOS, POSCaja, POSDevolucion, POSMovimientoCaja, POSPago, POSPrecio, POSTurno,
    POSVenta, POSVentaLinea,
)
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import WMSProducto, WMSUbicacion, WMSZona

CENTAVO = Decimal("0.01")
MEDIOS = [m.value for m in MedioPagoPOS]


def d(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v or 0))


def r2(v) -> Decimal:
    return d(v).quantize(CENTAVO, ROUND_HALF_UP)


def ahora() -> datetime:
    return datetime.now(timezone.utc)


async def turno_abierto(db: AsyncSession, usuario_id: int, caja_id: Optional[int] = None) -> POSTurno:
    q = select(POSTurno).where(POSTurno.cajero_id == usuario_id, POSTurno.estado == "ABIERTO")
    if caja_id:
        q = q.where(POSTurno.caja_id == caja_id)
    t = (await db.execute(q)).scalars().first()
    if t is None:
        raise HTTPException(409, "No tiene un turno de caja abierto. Abra turno antes de vender.")
    return t


def liquidar_linea(precio, cantidad, descuento_pct, tarifa) -> Dict[str, Decimal]:
    """Precio al público con IVA incluido → base, IVA y total de la línea."""
    bruto = d(precio) * d(cantidad)
    descuento = r2(bruto * d(descuento_pct) / 100)
    total = r2(bruto - descuento)
    tarifa = d(tarifa)
    base = r2(total / (1 + tarifa / 100)) if tarifa > 0 else total
    return {"bruto": r2(bruto), "descuento": descuento, "total": total, "base": base, "iva": total - base}


async def _tercero(db, empresa_id: int, nombre: str, documento: Optional[str], email: Optional[str]) -> Optional[int]:
    if not documento:
        return None
    t = (await db.execute(select(ERPTercero).where(
        ERPTercero.empresa_id == empresa_id, ERPTercero.numero_identificacion == documento))).scalar_one_or_none()
    if t is None:
        es_nit = len(documento) >= 9 and documento.startswith(("8", "9"))
        t = ERPTercero(empresa_id=empresa_id, tipo_identificacion="NIT" if es_nit else "CC",
                       numero_identificacion=documento, razon_social=nombre, email=email,
                       es_persona_natural=not es_nit, es_cliente=True, origen="POS")
        db.add(t)
        await db.flush()
    elif not t.es_cliente:
        t.es_cliente = True
    return t.id


async def _empresa(db, caja: POSCaja) -> ERPEmpresa:
    emp = await db.get(ERPEmpresa, caja.empresa_id) if caja.empresa_id else (
        await db.execute(select(ERPEmpresa).order_by(ERPEmpresa.id).limit(1))).scalar()
    if emp is None:
        raise HTTPException(422, "Cree primero la empresa en Finanzas: la factura necesita emisor.")
    return emp


async def vender(db: AsyncSession, yo: Usuario, caja_id: int, lineas: List[dict], pagos: List[dict],
                 cliente: dict) -> POSVenta:
    caja = await db.get(POSCaja, caja_id)
    if caja is None or not caja.activa:
        raise HTTPException(404, "Caja no encontrada o inactiva.")
    turno = await turno_abierto(db, yo.id, caja_id)
    if not lineas:
        raise HTTPException(422, "La venta no tiene productos.")
    if not caja.resolucion_id:
        raise HTTPException(422, "La caja no tiene resolución de facturación asignada (POS · Configuración).")
    empresa = await _empresa(db, caja)
    ubicaciones = await inv.ubicaciones_vendibles(db, caja.almacen_id)
    if not ubicaciones:
        raise HTTPException(422, "El almacén de la caja no tiene zonas habilitadas para vender.")

    precios = {p.producto_id: p.precio for p in (await db.execute(select(POSPrecio).where(
        POSPrecio.lista_id == caja.lista_id, POSPrecio.producto_id.in_([l["producto_id"] for l in lineas])))).scalars()}
    momento = ahora()
    venta = POSVenta(numero="(pendiente)", turno_id=turno.id, caja_id=caja.id, cajero_id=yo.id, fecha=momento,
                     cliente_nombre=(cliente.get("nombre") or "Consumidor final").strip()[:300],
                     cliente_documento=(cliente.get("documento") or None), cliente_email=cliente.get("email"),
                     subtotal=0, impuestos=0, total=0, descuento=0, costo_total=0)
    subtotal = impuestos = total = descuento = costo_total = Decimal(0)
    referencia = f"POS-{caja.codigo}"
    detalle: List[POSVentaLinea] = []
    for l in lineas:
        prod = await db.get(WMSProducto, l["producto_id"])
        if prod is None or not prod.activo:
            raise HTTPException(422, f"Producto {l['producto_id']} no existe o está inactivo.")
        if l["producto_id"] not in precios:
            raise HTTPException(422, f"«{prod.nombre}» no tiene precio en la lista de la caja.")
        cantidad = d(l["cantidad"])
        if cantidad <= 0:
            raise HTTPException(422, "Las cantidades deben ser mayores que cero.")
        desc = d(l.get("descuento_pct") or 0)
        if desc < 0 or desc > d(caja.descuento_maximo):
            raise HTTPException(422, f"El descuento máximo autorizado en esta caja es {caja.descuento_maximo}%.")
        liq = liquidar_linea(precios[l["producto_id"]], cantidad, desc, prod.tarifa_iva)
        try:
            asignaciones = await inv.asignar_fefo(db, prod.id, ubicaciones, cantidad)
            for a in asignaciones:
                await inv.sacar(db, producto_id=prod.id, ubicacion_id=a.ubicacion_id, lote_id=a.lote_id,
                                contenedor_id=a.contenedor_id, cantidad=a.cantidad, tipo="DESPACHO",
                                referencia=referencia, usuario_id=yo.id, notas="Venta POS",
                                documento_tipo="POS_VENTA")
        except inv.StockInsuficiente as e:
            raise HTTPException(409, str(e))
        costo_u = d(prod.costo_promedio)
        detalle.append(POSVentaLinea(producto_id=prod.id, descripcion=prod.nombre, cantidad=cantidad,
                                     precio_unitario=r2(precios[prod.id]), descuento_pct=desc,
                                     tarifa_iva=d(prod.tarifa_iva), base=liq["base"], iva=liq["iva"],
                                     total=liq["total"], costo_unitario=costo_u,
                                     salidas=[{"ubicacion_id": a.ubicacion_id, "lote_id": a.lote_id,
                                               "contenedor_id": a.contenedor_id,
                                               "cantidad": float(a.cantidad)} for a in asignaciones]))
        subtotal += liq["base"]; impuestos += liq["iva"]; total += liq["total"]; descuento += liq["descuento"]
        costo_total += r2(costo_u * cantidad)

    # Pagos: lo no efectivo debe cuadrar exacto; el efectivo puede sobrar (cambio).
    pagado = {m: Decimal(0) for m in MEDIOS}
    for p in pagos:
        if p["medio"] not in MEDIOS:
            raise HTTPException(422, f"Medio de pago desconocido: {p['medio']}")
        if d(p["monto"]) <= 0:
            raise HTTPException(422, "Los pagos deben ser mayores que cero.")
        pagado[p["medio"]] += d(p["monto"])
    no_efectivo = sum(v for m, v in pagado.items() if m != "EFECTIVO")
    if no_efectivo > total:
        raise HTTPException(422, "Los pagos con tarjeta o transferencia superan el total: el cambio solo se da en efectivo.")
    efectivo_aplicado = total - no_efectivo
    if pagado["EFECTIVO"] < efectivo_aplicado:
        raise HTTPException(422, f"Falta por pagar {r2(efectivo_aplicado - pagado['EFECTIVO'])}.")
    venta.recibido = r2(pagado["EFECTIVO"]) if pagado["EFECTIVO"] else None
    venta.cambio = r2(pagado["EFECTIVO"] - efectivo_aplicado)

    # Número de la resolución (atómico) y CUFE.
    try:
        numero, res = await dian.tomar_numero(db, caja.resolucion_id)
    except dian.ResolucionInvalida as e:
        raise HTTPException(409, str(e))
    venta.numero = numero
    venta.subtotal, venta.impuestos, venta.total = r2(subtotal), r2(impuestos), r2(total)
    venta.descuento, venta.costo_total = r2(descuento), r2(costo_total)
    venta.cufe = dian.codigo_unico(numero, momento.date(), dian.hora_colombia(momento), subtotal, impuestos, 0, 0,
                                   total, empresa.nit, venta.cliente_documento, res.clave_tecnica, res.ambiente)
    venta.tercero_id = await _tercero(db, empresa.id, venta.cliente_nombre, venta.cliente_documento, venta.cliente_email)
    venta.lineas = detalle
    venta.pagos = [POSPago(medio=m, monto=r2(efectivo_aplicado if m == "EFECTIVO" else v),
                           referencia=next((p.get("referencia") for p in pagos if p["medio"] == m and p.get("referencia")), None))
                   for m, v in pagado.items() if v > 0]
    db.add(venta)
    await db.flush()

    # Factura en el ERP, ya pagada.
    fac = ERPFacturaCliente(empresa_id=empresa.id, numero=numero, cliente_nombre=venta.cliente_nombre,
                            cliente_nit=venta.cliente_documento, cliente_email=venta.cliente_email,
                            fecha=momento.date(), fecha_vencimiento=momento.date(),
                            subtotal=venta.subtotal, total_impuestos=venta.impuestos, total=venta.total, saldo=0,
                            estado=EstadoFactura.PAGADA, moneda="COP", concepto=f"Venta POS {caja.nombre}",
                            cufe=venta.cufe, numero_electronico=numero, resolucion_id=res.id, origen="POS",
                            estado_dian="POR_TRANSMITIR")
    db.add(fac)
    await db.flush()
    for ln in detalle:
        db.add(ERPLineaFacturaCliente(factura_id=fac.id, descripcion=ln.descripcion, cantidad=float(ln.cantidad),
                                      precio_unitario=float(r2(ln.base / ln.cantidad)) if ln.cantidad else 0,
                                      descuento_pct=0, subtotal=float(ln.base), total_impuesto=float(ln.iva),
                                      total=float(ln.total)))
    venta.factura_id = fac.id

    # Un solo comprobante: cobro + ingreso + IVA + costo de ventas.
    asiento = [erp_motor.Linea("ingreso", credito=venta.subtotal, tercero_id=venta.tercero_id)]
    if venta.impuestos:
        asiento.append(erp_motor.Linea("iva_generado", credito=venta.impuestos, tercero_id=venta.tercero_id))
    if efectivo_aplicado > 0:
        asiento.append(erp_motor.Linea("caja", debito=r2(efectivo_aplicado)))
    if no_efectivo > 0:
        asiento.append(erp_motor.Linea("banco", debito=r2(no_efectivo)))
    if venta.costo_total > 0:
        asiento += [erp_motor.Linea("costo_venta", debito=venta.costo_total),
                    erp_motor.Linea("inventario", credito=venta.costo_total)]
    try:
        comp = await erp_motor.asentar(db, empresa_id=empresa.id, evento="POS_VENTA", tipo=TipoComprobante.INGRESO,
                                       fecha=momento.date(), concepto=f"Venta POS {numero}", lineas=asiento,
                                       usuario=yo.username, documento_tipo="POS_VENTA", documento_id=venta.id,
                                       documento_numero=numero)
    except erp_motor.ErrorContable as e:
        raise HTTPException(422, f"No se pudo contabilizar la venta: {e}")
    venta.comprobante_id = comp.id
    return venta


async def devolver(db: AsyncSession, yo: Usuario, venta_id: int, lineas: List[dict], motivo: str,
                   medio_reembolso: str) -> POSDevolucion:
    venta = await db.get(POSVenta, venta_id)
    if venta is None:
        raise HTTPException(404, "Venta no encontrada.")
    if medio_reembolso not in MEDIOS:
        raise HTTPException(422, "Medio de reembolso desconocido.")
    if not (motivo or "").strip():
        raise HTTPException(422, "Diga el motivo de la devolución.")
    turno = await turno_abierto(db, yo.id)
    caja = await db.get(POSCaja, venta.caja_id)
    empresa = await _empresa(db, caja)
    por_id = {ln.id: ln for ln in (await db.execute(select(POSVentaLinea).where(
        POSVentaLinea.venta_id == venta_id).with_for_update())).scalars()}

    cuarentena = None
    subtotal = impuestos = total = costo = Decimal(0)
    registro, nc_lineas = [], []
    momento = ahora()
    ref = f"DEV-{venta.numero}"
    for l in lineas:
        ln = por_id.get(l["linea_id"])
        if ln is None:
            raise HTTPException(422, "Una línea no pertenece a esta venta.")
        cant = d(l["cantidad"])
        if cant <= 0 or cant > d(ln.cantidad) - d(ln.cantidad_devuelta):
            raise HTTPException(422, f"«{ln.descripcion}»: se pueden devolver hasta "
                                     f"{(d(ln.cantidad) - d(ln.cantidad_devuelta)):g} unidades.")
        f = cant / d(ln.cantidad)
        base, iva, tot = r2(d(ln.base) * f), r2(d(ln.iva) * f), r2(d(ln.total) * f)
        estado = l.get("estado", "BUENO")
        if estado == "BUENO":
            origen = (ln.salidas or [{}])[0]
            ubic, lote = origen.get("ubicacion_id"), origen.get("lote_id")
        else:
            if cuarentena is None:
                cuarentena = (await db.execute(select(WMSUbicacion.id).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
                                               .where(WMSZona.almacen_id == caja.almacen_id, WMSZona.tipo == "CUARENTENA",
                                                      WMSUbicacion.activo.isnot(False))
                                               .order_by(WMSUbicacion.id).limit(1))).scalar()
                if cuarentena is None:
                    raise HTTPException(422, "El almacén no tiene zona de CUARENTENA para recibir mercancía dañada.")
            ubic, lote = cuarentena, (ln.salidas or [{}])[0].get("lote_id")
        await inv.entrar(db, producto_id=ln.producto_id, ubicacion_id=ubic, lote_id=lote, cantidad=cant,
                         tipo="DEVOLUCION", referencia=ref, usuario_id=yo.id, documento_tipo="POS_DEVOLUCION",
                         notas=f"Devolución POS ({'buen estado' if estado == 'BUENO' else 'dañado'})",
                         costo_unitario=ln.costo_unitario)
        ln.cantidad_devuelta = d(ln.cantidad_devuelta) + cant
        subtotal += base; impuestos += iva; total += tot; costo += r2(d(ln.costo_unitario) * cant)
        registro.append({"linea_id": ln.id, "cantidad": float(cant), "estado": estado, "ubicacion_id": ubic})
        nc_lineas.append(ERPLineaNotaCredito(descripcion=ln.descripcion, cantidad=cant,
                                             precio_unitario=r2(base / cant), tarifa_iva=ln.tarifa_iva,
                                             subtotal=base, impuesto=iva, total=tot))
    if not registro:
        raise HTTPException(422, "Indique qué se devuelve.")

    n_prev = (await db.execute(select(func.count()).select_from(POSDevolucion).where(
        POSDevolucion.venta_id == venta_id))).scalar() or 0
    numero_nc = f"NC{venta.numero}-{n_prev + 1}"
    res = await db.get(dian.ERPResolucionFacturacion, caja.resolucion_id) if caja.resolucion_id else None
    completa = all(d(x.cantidad_devuelta) >= d(x.cantidad) for x in por_id.values())
    nota = ERPNotaCreditoCliente(empresa_id=empresa.id, numero=numero_nc, factura_id=venta.factura_id,
                                 fecha=momento.date(), concepto="2" if completa and n_prev == 0 else "1",
                                 motivo=motivo, subtotal=r2(subtotal), total_impuestos=r2(impuestos), total=r2(total),
                                 cude=dian.codigo_unico(numero_nc, momento.date(), dian.hora_colombia(momento),
                                                        subtotal, impuestos, 0, 0, total, empresa.nit,
                                                        venta.cliente_documento, res.clave_tecnica if res else "",
                                                        res.ambiente if res else "2"),
                                 origen="POS", creado_por=yo.username, lineas=nc_lineas)
    db.add(nota)
    dev = POSDevolucion(venta_id=venta_id, turno_id=turno.id, cajero_id=yo.id, fecha=momento, motivo=motivo,
                        medio_reembolso=medio_reembolso, subtotal=r2(subtotal), impuestos=r2(impuestos),
                        total=r2(total), costo_total=r2(costo), lineas=registro)
    db.add(dev)
    await db.flush()
    dev.nota_credito_id = nota.id

    asiento = [erp_motor.Linea("devolucion", debito=r2(subtotal), tercero_id=venta.tercero_id),
               erp_motor.Linea("caja" if medio_reembolso == "EFECTIVO" else "banco", credito=r2(total))]
    if impuestos:
        asiento.append(erp_motor.Linea("iva_generado", debito=r2(impuestos), tercero_id=venta.tercero_id))
    if costo > 0:
        asiento += [erp_motor.Linea("inventario", debito=r2(costo)), erp_motor.Linea("costo_venta", credito=r2(costo))]
    try:
        comp = await erp_motor.asentar(db, empresa_id=empresa.id, evento="POS_DEVOLUCION", tipo=TipoComprobante.EGRESO,
                                       fecha=momento.date(), concepto=f"Devolución POS {numero_nc}", lineas=asiento,
                                       usuario=yo.username, documento_tipo="POS_DEVOLUCION", documento_id=dev.id,
                                       documento_numero=numero_nc)
    except erp_motor.ErrorContable as e:
        raise HTTPException(422, f"No se pudo contabilizar la devolución: {e}")
    dev.comprobante_id = nota.comprobante_id = comp.id
    venta.estado = "DEVUELTA" if completa else "DEVUELTA_PARCIAL"
    return dev


async def resumen_turno(db: AsyncSession, turno: POSTurno) -> dict:
    """Lo que debería haber en la caja, por medio de pago."""
    esperado = {m: Decimal(0) for m in MEDIOS}
    esperado["EFECTIVO"] = d(turno.base_inicial)
    ventas = (await db.execute(select(POSPago.medio, func.sum(POSPago.monto)).join(POSVenta, POSVenta.id == POSPago.venta_id)
                               .where(POSVenta.turno_id == turno.id).group_by(POSPago.medio))).all()
    for medio, monto in ventas:
        esperado[medio] += d(monto)
    devs = (await db.execute(select(POSDevolucion.medio_reembolso, func.sum(POSDevolucion.total))
                             .where(POSDevolucion.turno_id == turno.id).group_by(POSDevolucion.medio_reembolso))).all()
    for medio, monto in devs:
        esperado[medio] -= d(monto)
    movs = (await db.execute(select(POSMovimientoCaja.tipo, func.sum(POSMovimientoCaja.monto))
                             .where(POSMovimientoCaja.turno_id == turno.id).group_by(POSMovimientoCaja.tipo))).all()
    for tipo, monto in movs:
        esperado["EFECTIVO"] += d(monto) if tipo == "INGRESO" else -d(monto)
    n_ventas, total_ventas = (await db.execute(select(func.count(), func.coalesce(func.sum(POSVenta.total), 0))
                                               .where(POSVenta.turno_id == turno.id))).one()
    total_dev = (await db.execute(select(func.coalesce(func.sum(POSDevolucion.total), 0))
                                  .where(POSDevolucion.turno_id == turno.id))).scalar()
    return {"esperado": {m: float(r2(v)) for m, v in esperado.items() if v or m == "EFECTIVO"},
            "ventas": n_ventas, "total_ventas": float(total_ventas), "total_devoluciones": float(total_dev),
            "movimientos": {t: float(m) for t, m in movs}}
