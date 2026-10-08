"""
Documentos del WMS en PDF.

    GET /wms/documentos/oc/{id}            Orden de compra (para enviar al proveedor)
    GET /wms/documentos/recepcion/{id}     Acta de recepción (con novedades)
    GET /wms/documentos/orden-salida/{id}  Orden de salida / pedido
    GET /wms/documentos/picking/{id}       Hoja de picking (ruta por ubicación, casillas para marcar)
    GET /wms/documentos/despacho/{id}      Remisión de despacho (transporte, peso, lotes, firmas)
    GET /wms/documentos/traslado/{id}      Traslado entre bodegas

La maqueta está en app/core/documentos_pdf.py; aquí solo se reúnen los datos.
"""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import documentos_pdf as doc
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSCliente, WMSDespacho, WMSDespachoDetalle, WMSLote, WMSOrdenCompra, WMSOrdenCompraDetalle,
    WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSPickingDetalle, WMSPickingTarea, WMSProducto, WMSProductoEmpaque,
    WMSProveedor, WMSRecepcion, WMSRecepcionDetalle, WMSTransportadora, WMSTraslado, WMSTrasladoDetalle, WMSUbicacion,
)

router = APIRouter(prefix="/wms/documentos", tags=["WMS · Documentos PDF"])

NIVEL = {"CAJA": ("caja", "cajas"), "MASTER": ("máster", "másters"), "ESTIBA": ("estiba", "estibas")}


async def _empresa(db: AsyncSession) -> Dict:
    from app.infrastructure.models.erp import ERPEmpresa
    e = (await db.execute(select(ERPEmpresa).where(ERPEmpresa.deleted_at.is_(None)).order_by(ERPEmpresa.id).limit(1))).scalar()
    if e:
        return {"nombre": e.nombre_comercial or e.razon_social, "nit": e.nit, "direccion": e.direccion,
                "ciudad": e.ciudad, "telefono": e.telefono, "email": e.email}
    return {"nombre": "Daily Logistics"}


def _pdf(contenido: bytes, nombre: str, descargar: bool) -> Response:
    modo = "attachment" if descargar else "inline"
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'{modo}; filename="{nombre}.pdf"'})


async def _prod(db, cache: Dict[int, WMSProducto], pid: int) -> Optional[WMSProducto]:
    if pid not in cache:
        cache[pid] = await db.get(WMSProducto, pid)
    return cache[pid]


async def _empaque(db, pid: int, unidades: float) -> str:
    """«3 cajas ×24 + 5 und»: cómo se ve físicamente la cantidad."""
    emps = (await db.execute(select(WMSProductoEmpaque).where(
        WMSProductoEmpaque.producto_id == pid, WMSProductoEmpaque.nivel.in_(list(NIVEL))))).scalars().all()
    resto, partes = float(unidades or 0), []
    for e in sorted(emps, key=lambda e: -e.unidades):
        if e.unidades and e.unidades > 1:
            n = int(resto // e.unidades)
            if n:
                partes.append(f"{n} {NIVEL[e.nivel][n > 1]} ×{doc.num(e.unidades)}")
                resto -= n * e.unidades
    if resto > 1e-9 or not partes:
        partes.append(f"{doc.num(resto)} und")
    return " + ".join(partes)


def _lote(l: Optional[WMSLote]) -> str:
    if not l:
        return "-"
    return l.numero_lote + (f" (vence {doc.fecha(l.fecha_vencimiento)})" if l.fecha_vencimiento else "")


# ─── Orden de compra ─────────────────────────────────────────────────────────
@router.get("/oc/{oc_id}")
async def pdf_oc(oc_id: int, descargar: bool = Query(False), db: AsyncSession = Depends(get_db),
                 yo: Usuario = Depends(get_current_user)):
    oc = await db.get(WMSOrdenCompra, oc_id)
    if not oc or oc.deleted_at:
        raise HTTPException(404, "Orden de compra no encontrada")
    from app.infrastructure.models.wms import WMSEstadoOC
    prov, alm = await db.get(WMSProveedor, oc.proveedor_id), await db.get(WMSAlmacen, oc.almacen_id)
    estado = (await db.execute(select(WMSEstadoOC.nombre).where(WMSEstadoOC.codigo == oc.estado))).scalar() or oc.estado
    dets = (await db.execute(select(WMSOrdenCompraDetalle).where(WMSOrdenCompraDetalle.orden_id == oc.id)
                             .order_by(WMSOrdenCompraDetalle.id))).scalars().all()
    cache: Dict[int, WMSProducto] = {}
    filas, total = [], 0.0
    for i, d in enumerate(dets, 1):
        p = await _prod(db, cache, d.producto_id)
        sub = (d.cantidad_solicitada or 0) * (d.precio_unitario or 0)
        total += sub
        filas.append([i, p.sku if p else d.producto_id, p.nombre if p else "-", doc.num(d.cantidad_solicitada),
                      d.unidad_medida or (p.unidad_medida if p else ""), doc.dinero(d.precio_unitario), doc.dinero(sub),
                      doc.num(d.cantidad_recibida)])
    pdf = doc.construir(
        empresa=await _empresa(db), titulo="Orden de compra", numero=oc.numero_oc, estado=estado, usuario=yo.username,
        datos=[("Proveedor", prov.nombre if prov else "-"), ("NIT", prov.nit if prov else "-"),
               ("Contacto", " · ".join(x for x in (prov.contacto, prov.telefono, prov.email) if x) if prov else "-"),
               ("Ciudad", prov.ciudad if prov else "-"),
               ("Fecha de emisión", doc.fecha(oc.fecha_emision)), ("Entrega esperada", doc.fecha(oc.fecha_esperada)),
               ("Entregar en", f"{alm.nombre} — {alm.direccion or ''}".strip(" —") if alm else "-"),
               ("Ciudad de entrega", alm.ciudad if alm else "-")],
        tablas=[{"columnas": [("#", 4, "C"), ("SKU", 13, "L"), ("Producto", 34, "L"), ("Cantidad", 10, "R"),
                              ("Unidad", 9, "C"), ("Precio unit.", 12, "R"), ("Subtotal", 13, "R"), ("Recibido", 9, "R")],
                 "filas": filas, "totales": [("Total de la orden", doc.dinero(total))]}],
        notas=oc.notas, firmas=["Elaboró", "Aprobó", "Proveedor (aceptación)"])
    return _pdf(pdf, f"OC_{oc.numero_oc}", descargar)


# ─── Recepción ───────────────────────────────────────────────────────────────
@router.get("/recepcion/{rec_id}")
async def pdf_recepcion(rec_id: int, descargar: bool = Query(False), db: AsyncSession = Depends(get_db),
                        yo: Usuario = Depends(get_current_user)):
    r = await db.get(WMSRecepcion, rec_id)
    if not r or r.deleted_at:
        raise HTTPException(404, "Recepción no encontrada")
    alm = await db.get(WMSAlmacen, r.almacen_id)
    oc = await db.get(WMSOrdenCompra, r.orden_compra_id) if r.orden_compra_id else None
    prov = await db.get(WMSProveedor, oc.proveedor_id) if oc else None
    dets = (await db.execute(select(WMSRecepcionDetalle).where(WMSRecepcionDetalle.recepcion_id == r.id)
                             .order_by(WMSRecepcionDetalle.id))).scalars().all()
    cache: Dict[int, WMSProducto] = {}
    filas, con_novedad = [], 0
    for i, d in enumerate(dets, 1):
        p = await _prod(db, cache, d.producto_id)
        u = await db.get(WMSUbicacion, d.ubicacion_id) if d.ubicacion_id else None
        l = await db.get(WMSLote, d.lote_id) if d.lote_id else None
        con_novedad += bool(d.novedad)
        filas.append([i, p.sku if p else "-", p.nombre if p else "-", _lote(l), doc.num(d.cantidad_esperada),
                      doc.num(d.cantidad_recibida), await _empaque(db, d.producto_id, d.cantidad_recibida),
                      u.codigo if u else "-", (d.novedad or "-").replace("_", " ").capitalize(), d.estado_calidad or "-"])
    pdf = doc.construir(
        empresa=await _empresa(db), titulo="Acta de recepción", numero=r.numero_recepcion, estado=r.estado,
        usuario=yo.username, horizontal=True,
        datos=[("Tipo", (r.tipo or "").replace("_", " ").capitalize()), ("Orden de compra", oc.numero_oc if oc else "Sin OC (ciega)"),
               ("Proveedor", prov.nombre if prov else "-"), ("Almacén", alm.nombre if alm else "-"),
               ("Fecha", doc.fecha(r.fecha_recepcion)), ("Muelle", r.muelle or "-"),
               ("Llegada", doc.fecha(r.fecha_llegada, True)), ("Completada", doc.fecha(r.completada_en, True))],
        tablas=[{"columnas": [("#", 3, "C"), ("SKU", 10, "L"), ("Producto", 24, "L"), ("Lote", 15, "L"), ("Esperado", 8, "R"),
                              ("Recibido", 8, "R"), ("Empaque", 16, "L"), ("Ubicación", 10, "L"), ("Novedad", 10, "L"), ("Calidad", 9, "L")],
                 "filas": filas, "totales": [("Líneas con novedad", str(con_novedad))]}],
        notas=r.notas, firmas=["Recibió (bodega)", "Entregó (proveedor/transportador)", "Verificó"])
    return _pdf(pdf, f"Recepcion_{r.numero_recepcion}", descargar)


# ─── Orden de salida ─────────────────────────────────────────────────────────
async def _orden(db, oid: int):
    o = await db.get(WMSOrdenSalida, oid)
    if not o or o.deleted_at:
        raise HTTPException(404, "Orden de salida no encontrada")
    return o, await db.get(WMSCliente, o.cliente_id), await db.get(WMSAlmacen, o.almacen_id)


ESTADO_LINEA = {"PENDIENTE": "Pendiente", "RESERVADO": "Reservado", "EN_PREPARACION": "En preparación",
                "PREPARADO": "Preparado", "DESPACHO_PARCIAL": "Despacho parcial", "DESPACHADO": "Despachado",
                "ENTREGA_PARCIAL": "Entrega parcial", "ENTREGADO": "Entregado", "CANCELADO": "Cancelado"}


@router.get("/orden-salida/{oid}")
async def pdf_orden_salida(oid: int, descargar: bool = Query(False), db: AsyncSession = Depends(get_db),
                           yo: Usuario = Depends(get_current_user)):
    o, cli, alm = await _orden(db, oid)
    dets = (await db.execute(select(WMSOrdenSalidaDetalle).where(WMSOrdenSalidaDetalle.orden_id == o.id)
                             .order_by(WMSOrdenSalidaDetalle.id))).scalars().all()
    cache: Dict[int, WMSProducto] = {}
    filas, total = [], 0.0
    for i, d in enumerate(dets, 1):
        p = await _prod(db, cache, d.producto_id)
        sub = (d.cantidad_solicitada or 0) * (d.precio_unitario or 0)
        total += sub
        filas.append([i, p.sku if p else "-", p.nombre if p else "-", doc.num(d.cantidad_solicitada),
                      await _empaque(db, d.producto_id, d.cantidad_solicitada), doc.num(d.cantidad_despachada),
                      doc.dinero(d.precio_unitario), doc.dinero(sub), ESTADO_LINEA.get(d.estado, d.estado)])
    pdf = doc.construir(
        empresa=await _empresa(db), titulo="Orden de salida", numero=o.numero_orden, estado=o.estado, usuario=yo.username,
        datos=[("Cliente", cli.nombre if cli else "-"), ("NIT", cli.nit if cli else "-"),
               ("Contacto", " · ".join(x for x in (cli.contacto, cli.telefono) if x) if cli else "-"),
               ("Ciudad", cli.ciudad if cli else "-"), ("Almacén", alm.nombre if alm else "-"),
               ("Emisión", doc.fecha(o.fecha_emision)), ("Requerida", doc.fecha(o.fecha_requerida)),
               ("Prioridad · canal", f"{o.prioridad or '-'} · {o.canal or 'directo'}")],
        tablas=[{"columnas": [("#", 3, "C"), ("SKU", 11, "L"), ("Producto", 27, "L"), ("Pedido", 8, "R"), ("Empaque", 17, "L"),
                              ("Despachado", 9, "R"), ("Precio", 10, "R"), ("Subtotal", 11, "R"), ("Estado", 11, "L")],
                 "filas": filas, "totales": [("Total", doc.dinero(total))] if total else []}],
        firmas=["Elaboró", "Autorizó"])
    return _pdf(pdf, f"Orden_{o.numero_orden}", descargar)


# ─── Hoja de picking ─────────────────────────────────────────────────────────
@router.get("/picking/{tarea_id}")
async def pdf_picking(tarea_id: int, descargar: bool = Query(False), db: AsyncSession = Depends(get_db),
                      yo: Usuario = Depends(get_current_user)):
    t = await db.get(WMSPickingTarea, tarea_id)
    if not t:
        raise HTTPException(404, "Tarea de picking no encontrada")
    o, cli, alm = await _orden(db, t.orden_id)
    dets = (await db.execute(select(WMSPickingDetalle, WMSUbicacion).outerjoin(
        WMSUbicacion, WMSUbicacion.id == WMSPickingDetalle.ubicacion_id).where(WMSPickingDetalle.tarea_id == t.id))).all()
    # El recorrido: por el orden de recorrido de la ubicación y luego su código.
    dets.sort(key=lambda r: ((r[1].orden_recorrido if r[1] and r[1].orden_recorrido is not None else 10 ** 6),
                             r[1].codigo if r[1] else ""))
    cache: Dict[int, WMSProducto] = {}
    filas, total = [], 0.0
    for i, (d, u) in enumerate(dets, 1):
        p = await _prod(db, cache, d.producto_id)
        l = await db.get(WMSLote, d.lote_id) if d.lote_id else None
        total += d.cantidad_solicitada or 0
        origen = d.ubicacion_alistada_id and await db.get(WMSUbicacion, d.ubicacion_alistada_id)
        ubic = (origen.codigo if origen else (u.codigo if u else "-"))
        filas.append([i, ubic, p.sku if p else "-", p.nombre if p else "-", _lote(l), doc.num(d.cantidad_solicitada),
                      await _empaque(db, d.producto_id, d.cantidad_solicitada),
                      doc.num(d.cantidad_pickeada) if d.confirmado else "______", "☑" if d.confirmado else "☐"])
    pdf = doc.construir(
        empresa=await _empresa(db), titulo="Hoja de picking", numero=o.numero_orden, estado=t.estado,
        usuario=yo.username, horizontal=True,
        datos=[("Orden", o.numero_orden), ("Cliente", cli.nombre if cli else "-"), ("Almacén", alm.nombre if alm else "-"),
               ("Prioridad", o.prioridad or "-"), ("Requerida", doc.fecha(o.fecha_requerida)),
               ("Tipo de tarea", t.tipo or "-"), ("Asignada", doc.fecha(t.fecha_asignacion, True)), ("Tarea", f"#{t.id}")],
        tablas=[{"titulo": "Recorrido sugerido (en orden de ubicación)",
                 "columnas": [("#", 3, "C"), ("Ubicación", 10, "L"), ("SKU", 10, "L"), ("Producto", 24, "L"), ("Lote", 15, "L"),
                              ("Cantidad", 8, "R"), ("Empaque", 16, "L"), ("Alistado", 8, "C"), ("✓", 4, "C")],
                 "filas": filas, "totales": [("Unidades a alistar", doc.num(total))]}],
        notas="Al terminar, lleve la mercancía a la zona de staging de salida y confirme la tarea en el sistema "
              "(Ejecutar picking): botones, escáner o RFID.",
        firmas=["Operario que alistó", "Verificó"])
    return _pdf(pdf, f"Picking_{o.numero_orden}", descargar)


# ─── Remisión de despacho ────────────────────────────────────────────────────
@router.get("/despacho/{desp_id}")
async def pdf_despacho(desp_id: int, descargar: bool = Query(False), db: AsyncSession = Depends(get_db),
                       yo: Usuario = Depends(get_current_user)):
    d = await db.get(WMSDespacho, desp_id)
    if not d or d.deleted_at:
        raise HTTPException(404, "Despacho no encontrado")
    o, cli, alm = await _orden(db, d.orden_id)
    tr = await db.get(WMSTransportadora, d.transportadora_id) if d.transportadora_id else None
    from app.infrastructure.models.tms import TMSViaje
    viaje = (await db.execute(select(TMSViaje).where(TMSViaje.wms_despacho_id == d.id))).scalar()
    dets = (await db.execute(select(WMSDespachoDetalle).where(WMSDespachoDetalle.despacho_id == d.id)
                             .order_by(WMSDespachoDetalle.id))).scalars().all()
    cache: Dict[int, WMSProducto] = {}
    filas, total = [], 0.0
    for i, x in enumerate(dets, 1):
        p = await _prod(db, cache, x.producto_id)
        l = await db.get(WMSLote, x.lote_id) if x.lote_id else None
        total += x.cantidad or 0
        filas.append([i, p.sku if p else "-", p.nombre if p else "-", _lote(l), doc.num(x.cantidad),
                      await _empaque(db, x.producto_id, x.cantidad), "☐"])
    destino = (viaje.destino_direccion if viaje and viaje.destino_direccion else None) or (cli.nombre if cli else "-")
    # Vehículo y conductor: los del viaje del TMS si el despacho no los trae.
    placa, conductor = d.vehiculo_placa, d.conductor_nombre
    if viaje:
        from app.infrastructure.models.tms import TMSVehiculo
        from app.infrastructure.models.hcm import HCMColaborador, HCMConductor
        if not placa and viaje.vehiculo_id:
            v = await db.get(TMSVehiculo, viaje.vehiculo_id)
            placa = v.placa if v else None
        if not conductor and viaje.conductor_hcm_id:
            conductor = (await db.execute(select(HCMColaborador.nombres + " " + HCMColaborador.apellidos).join(
                HCMConductor, HCMConductor.colaborador_id == HCMColaborador.id).where(
                HCMConductor.id == viaje.conductor_hcm_id))).scalar()
    pdf = doc.construir(
        empresa=await _empresa(db), titulo="Remisión de despacho", numero=d.numero_despacho, estado=d.estado,
        usuario=yo.username,
        datos=[("Orden de salida", o.numero_orden), ("Cliente", cli.nombre if cli else "-"),
               ("Destino", destino), ("Ciudad", (viaje.destino_ciudad if viaje else None) or (cli.ciudad if cli else "-")),
               ("Origen", alm.nombre if alm else "-"), ("Fecha de despacho", doc.fecha(d.fecha_despacho)),
               ("Entrega estimada", doc.fecha(d.fecha_entrega_estimada)), ("Transportadora", tr.nombre if tr else "Propia"),
               ("Placa · conductor", f"{placa or '-'} · {conductor or '-'}"),
               ("Viaje TMS", viaje.codigo if viaje else "-"),
               ("Peso total", f"{doc.num(d.peso_total_kg, 2)} kg" if d.peso_total_kg else "-"),
               ("Volumen total", f"{doc.num(d.volumen_total_m3, 3)} m³" if d.volumen_total_m3 else "-")],
        tablas=[{"columnas": [("#", 4, "C"), ("SKU", 12, "L"), ("Producto", 28, "L"), ("Lote", 18, "L"), ("Cantidad", 10, "R"),
                              ("Empaque", 18, "L"), ("Recibido", 10, "C")],
                 "filas": filas, "totales": [("Unidades despachadas", doc.num(total))]}],
        notas=d.notas, firmas=["Despachó (bodega)", "Transportador", "Recibió (cliente)"])
    return _pdf(pdf, f"Despacho_{d.numero_despacho}", descargar)


# ─── Traslado ────────────────────────────────────────────────────────────────
@router.get("/traslado/{tid}")
async def pdf_traslado(tid: int, descargar: bool = Query(False), db: AsyncSession = Depends(get_db),
                       yo: Usuario = Depends(get_current_user)):
    t = await db.get(WMSTraslado, tid)
    if not t:
        raise HTTPException(404, "Traslado no encontrado")
    ori, des = await db.get(WMSAlmacen, t.almacen_origen_id), await db.get(WMSAlmacen, t.almacen_destino_id)
    dets = (await db.execute(select(WMSTrasladoDetalle).where(WMSTrasladoDetalle.traslado_id == t.id)
                             .order_by(WMSTrasladoDetalle.id))).scalars().all()
    cache: Dict[int, WMSProducto] = {}
    filas, total = [], 0.0
    for i, x in enumerate(dets, 1):
        p = await _prod(db, cache, x.producto_id)
        l = await db.get(WMSLote, x.lote_id) if x.lote_id else None
        uo = await db.get(WMSUbicacion, x.ubicacion_origen_id) if x.ubicacion_origen_id else None
        ud = await db.get(WMSUbicacion, x.ubicacion_destino_id) if x.ubicacion_destino_id else None
        total += x.cantidad or 0
        filas.append([i, p.sku if p else "-", p.nombre if p else "-", _lote(l), uo.codigo if uo else "-",
                      doc.num(x.cantidad), await _empaque(db, x.producto_id, x.cantidad),
                      doc.num(x.cantidad_recibida) if x.cantidad_recibida is not None else "______", ud.codigo if ud else "-"])
    pdf = doc.construir(
        empresa=await _empresa(db), titulo="Traslado entre bodegas", numero=t.numero, estado=t.estado,
        usuario=yo.username, horizontal=True,
        datos=[("Origen", f"{ori.nombre} — {ori.ciudad or ''}".strip(" —") if ori else "-"),
               ("Destino", f"{des.nombre} — {des.ciudad or ''}".strip(" —") if des else "-"),
               ("Salió", doc.fecha(t.despachado_en, True)), ("Recibido", doc.fecha(t.recibido_en, True)),
               ("Viaje TMS", t.tms_codigo or "-"), ("Líneas", str(len(dets)))],
        tablas=[{"columnas": [("#", 3, "C"), ("SKU", 10, "L"), ("Producto", 24, "L"), ("Lote", 15, "L"), ("Sale de", 10, "L"),
                              ("Cantidad", 8, "R"), ("Empaque", 15, "L"), ("Llegó", 8, "R"), ("Ubicado en", 10, "L")],
                 "filas": filas, "totales": [("Unidades trasladadas", doc.num(total))]}],
        notas=t.notas, firmas=["Despachó (origen)", "Transportador", "Recibió (destino)"])
    return _pdf(pdf, f"Traslado_{t.numero}", descargar)
