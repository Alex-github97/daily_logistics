"""
Portal del depositante (cliente del 3PL): su inventario, sus movimientos de
entrada y salida, sus órdenes, sus recepciones y sus facturas. Nada más.
Prefijo: /wms/portal

El depositante sale del token (firmado al entrar) y se vuelve a comprobar
contra el vínculo en la base: si lo desvinculan, su sesión deja de servir.
La barrera global (`auth_global`) impide que ese token abra cualquier otra ruta.

Al final están las rutas internas para vincular usuarios a un depositante.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.core.security import decode_token
from app.core.wms_slotting import volumenes
from app.infrastructure.models.erp import ERPFacturaCliente
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSCliente, WMSDepositante, WMSDepositanteUsuario, WMSDespacho, WMSInventarioUbicacion, WMSLiquidacion3PL, WMSLote,
    WMSMovimientoInventario, WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSProducto, WMSRecepcion, WMSRecepcionDetalle,
)

router = APIRouter(prefix="/wms", tags=["wms-portal"])
M = WMSMovimientoInventario


async def mi_depositante(request: Request, db: AsyncSession = Depends(get_db),
                         yo: Usuario = Depends(get_current_user)) -> WMSDepositante:
    datos = decode_token((request.headers.get("authorization") or "")[7:])
    dep_id = datos.get("dep")
    if not dep_id:
        raise HTTPException(403, "Esta sección es para los usuarios del portal de clientes.")
    vinculo = (await db.execute(select(WMSDepositanteUsuario).where(
        WMSDepositanteUsuario.usuario_id == yo.id, WMSDepositanteUsuario.depositante_id == dep_id))).scalar_one_or_none()
    dep = await db.get(WMSDepositante, dep_id)
    if vinculo is None or dep is None or not dep.activo:
        raise HTTPException(401, "Su acceso al portal cambió: vuelva a iniciar sesión.")
    return dep


def _rango(desde: Optional[date], hasta: Optional[date]):
    hasta = hasta or (datetime.now(timezone.utc) - timedelta(hours=5)).date()
    desde = desde or hasta - timedelta(days=30)
    return (datetime.combine(desde, time.min, timezone.utc) + timedelta(hours=5),
            datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc) + timedelta(hours=5), desde, hasta)


@router.get("/portal/resumen")
async def resumen(db: AsyncSession = Depends(get_db), dep: WMSDepositante = Depends(mi_depositante)):
    prods = list((await db.execute(select(WMSProducto.id).where(WMSProducto.depositante_id == dep.id))).scalars())
    total = WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada + WMSInventarioUbicacion.cantidad_bloqueada
    filas = (await db.execute(select(WMSInventarioUbicacion.producto_id, func.sum(total), func.sum(WMSInventarioUbicacion.cantidad_disponible),
                                     func.sum(WMSInventarioUbicacion.cantidad_bloqueada))
                              .where(WMSInventarioUbicacion.producto_id.in_(prods or [0]), total > 0)
                              .group_by(WMSInventarioUbicacion.producto_id))).all()
    vol = await volumenes(db, prods)
    en_curso = (await db.execute(select(func.count()).select_from(WMSOrdenSalida).where(
        WMSOrdenSalida.depositante_id == dep.id, WMSOrdenSalida.deleted_at.is_(None),
        WMSOrdenSalida.estado.in_(("PENDIENTE", "EN_PICKING", "EMPACANDO", "DESPACHADO"))))).scalar()
    return {"depositante": {"id": dep.id, "nombre": dep.nombre, "nit": dep.nit},
            "referencias": len(filas), "unidades": float(sum(f[1] for f in filas)),
            "disponibles": float(sum(f[2] for f in filas)), "bloqueadas": float(sum(f[3] for f in filas)),
            "m3": round(sum(float(f[1]) * (vol.get(f[0]) or 0) for f in filas), 3), "ordenes_en_curso": en_curso}


@router.get("/portal/inventario")
async def inventario(q: Optional[str] = None, db: AsyncSession = Depends(get_db), dep: WMSDepositante = Depends(mi_depositante)):
    """Existencias por producto y lote (sin las ubicaciones internas de la bodega)."""
    consulta = select(WMSProducto).where(WMSProducto.depositante_id == dep.id)
    if q:
        consulta = consulta.where(or_(WMSProducto.sku.ilike(f"%{q}%"), WMSProducto.nombre.ilike(f"%{q}%")))
    prods = {p.id: p for p in (await db.execute(consulta)).scalars()}
    filas = (await db.execute(select(WMSInventarioUbicacion).where(WMSInventarioUbicacion.producto_id.in_(list(prods) or [0])))).scalars().all()
    lotes = {l.id: l for l in (await db.execute(select(WMSLote).where(WMSLote.id.in_({f.lote_id for f in filas if f.lote_id} or {0})))).scalars()}
    agg = defaultdict(lambda: {"disponible": 0.0, "reservado": 0.0, "bloqueado": 0.0})
    for f in filas:
        a = agg[(f.producto_id, f.lote_id)]
        a["disponible"] += f.cantidad_disponible or 0
        a["reservado"] += f.cantidad_reservada or 0
        a["bloqueado"] += f.cantidad_bloqueada or 0
    out = []
    for (pid, lid), a in agg.items():
        if a["disponible"] + a["reservado"] + a["bloqueado"] <= 0:
            continue
        p, l = prods[pid], lotes.get(lid)
        out.append({"producto_id": pid, "sku": p.sku, "nombre": p.nombre, "lote": l.numero_lote if l else None,
                    "vence": l.fecha_vencimiento.isoformat() if l and l.fecha_vencimiento else None, **a,
                    "total": a["disponible"] + a["reservado"] + a["bloqueado"]})
    return sorted(out, key=lambda x: (x["sku"], x["vence"] or "9999"))


@router.get("/portal/movimientos")
async def movimientos(desde: Optional[date] = None, hasta: Optional[date] = None, producto_id: Optional[int] = None,
                      db: AsyncSession = Depends(get_db), dep: WMSDepositante = Depends(mi_depositante)):
    """Entradas y salidas de su mercancía (los traslados internos no se muestran)."""
    ini, fin, _d, _h = _rango(desde, hasta)
    q = select(M, WMSProducto).join(WMSProducto, WMSProducto.id == M.producto_id).where(
        WMSProducto.depositante_id == dep.id, M.created_at >= ini, M.created_at < fin,
        or_(M.ubicacion_origen_id.is_(None), M.ubicacion_destino_id.is_(None)))
    if producto_id:
        q = q.where(M.producto_id == producto_id)
    filas = (await db.execute(q.order_by(M.created_at.desc()).limit(2000))).all()
    lotes = dict((await db.execute(select(WMSLote.id, WMSLote.numero_lote).where(
        WMSLote.id.in_({m.lote_id for m, _ in filas if m.lote_id} or {0})))).all())
    nombre = {"RECEPCION": "Recepción", "DESPACHO": "Despacho", "DEVOLUCION": "Devolución", "AJUSTE": "Ajuste de inventario",
              "CONTEO": "Ajuste por conteo", "MAQUILA_CONSUMO": "Consumo en maquila", "MAQUILA_PRODUCCION": "Producido en maquila"}
    return [{"fecha": m.created_at.isoformat(), "tipo": nombre.get(m.tipo, m.tipo.title()), "sku": p.sku, "producto": p.nombre,
             "lote": lotes.get(m.lote_id), "entrada": m.cantidad if m.ubicacion_origen_id is None else 0,
             "salida": m.cantidad if m.ubicacion_destino_id is None else 0, "documento": m.referencia_documento,
             "notas": m.notas if m.tipo in ("AJUSTE", "CONTEO") else None} for m, p in filas]


@router.get("/portal/ordenes")
async def ordenes(db: AsyncSession = Depends(get_db), dep: WMSDepositante = Depends(mi_depositante)):
    filas = (await db.execute(select(WMSOrdenSalida, WMSCliente).join(WMSCliente, WMSCliente.id == WMSOrdenSalida.cliente_id)
                              .where(WMSOrdenSalida.depositante_id == dep.id, WMSOrdenSalida.deleted_at.is_(None))
                              .order_by(WMSOrdenSalida.id.desc()).limit(300))).all()
    ids = [o.id for o, _ in filas]
    lineas = defaultdict(lambda: [0.0, 0.0])
    for d in (await db.execute(select(WMSOrdenSalidaDetalle).where(WMSOrdenSalidaDetalle.orden_id.in_(ids or [0])))).scalars():
        lineas[d.orden_id][0] += d.cantidad_solicitada
        lineas[d.orden_id][1] += d.cantidad_despachada or 0
    desp = defaultdict(list)
    for d in (await db.execute(select(WMSDespacho).where(WMSDespacho.orden_id.in_(ids or [0]), WMSDespacho.deleted_at.is_(None)))).scalars():
        desp[d.orden_id].append({"numero": d.numero_despacho, "fecha": d.fecha_despacho.isoformat(), "estado": d.estado,
                                 "entregado": d.fecha_entrega_real.isoformat() if d.fecha_entrega_real else None})
    return [{"numero": o.numero_orden, "destinatario": c.nombre, "emitida": o.fecha_emision.isoformat(),
             "requerida": o.fecha_requerida.isoformat() if o.fecha_requerida else None, "estado": o.estado,
             "pedido": lineas[o.id][0], "despachado": lineas[o.id][1], "despachos": desp[o.id]} for o, c in filas]


@router.get("/portal/recepciones")
async def recepciones(db: AsyncSession = Depends(get_db), dep: WMSDepositante = Depends(mi_depositante)):
    recs = (await db.execute(select(WMSRecepcion).where(WMSRecepcion.depositante_id == dep.id, WMSRecepcion.deleted_at.is_(None))
                             .order_by(WMSRecepcion.id.desc()).limit(300))).scalars().all()
    unidades = dict((await db.execute(select(WMSRecepcionDetalle.recepcion_id, func.sum(WMSRecepcionDetalle.cantidad_recibida))
                                      .where(WMSRecepcionDetalle.recepcion_id.in_([r.id for r in recs] or [0]))
                                      .group_by(WMSRecepcionDetalle.recepcion_id))).all())
    return [{"numero": r.numero_recepcion, "fecha": r.fecha_recepcion.isoformat(), "estado": r.estado,
             "unidades": float(unidades.get(r.id) or 0)} for r in recs]


@router.get("/portal/facturacion")
async def facturacion(db: AsyncSession = Depends(get_db), dep: WMSDepositante = Depends(mi_depositante)):
    """Sus liquidaciones ya facturadas, con el detalle de lo cobrado."""
    filas = (await db.execute(select(WMSLiquidacion3PL).where(WMSLiquidacion3PL.depositante_id == dep.id,
                                                              WMSLiquidacion3PL.estado == "FACTURADA")
                              .order_by(WMSLiquidacion3PL.hasta.desc()))).scalars().all()
    facts = {f.id: f for f in (await db.execute(select(ERPFacturaCliente).where(
        ERPFacturaCliente.id.in_([l.factura_id for l in filas if l.factura_id] or [0])))).scalars()}
    return [{"liquidacion": l.numero, "desde": l.desde.isoformat(), "hasta": l.hasta.isoformat(), "subtotal": l.subtotal,
             "iva": l.iva, "total": l.total, "factura": facts[l.factura_id].numero if l.factura_id in facts else None,
             "saldo": float(facts[l.factura_id].saldo) if l.factura_id in facts else None,
             "vence": facts[l.factura_id].fecha_vencimiento.isoformat() if l.factura_id in facts else None,
             "lineas": l.lineas} for l in filas]


# ── Administración de los usuarios del portal (personal interno) ─────────────

class VinculoIn(BaseModel):
    usuario_id: int


@router.get("/depositantes/{did}/usuarios")
async def usuarios_portal(did: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    filas = (await db.execute(select(Usuario).join(WMSDepositanteUsuario, WMSDepositanteUsuario.usuario_id == Usuario.id)
                              .where(WMSDepositanteUsuario.depositante_id == did))).scalars().all()
    return [{"id": u.id, "username": u.username, "nombre": f"{u.nombre} {u.apellido}".strip(), "email": u.email,
             "activo": u.activo} for u in filas]


@router.post("/depositantes/{did}/usuarios", status_code=201)
async def vincular(did: int, data: VinculoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_supervisor)):
    if await db.get(WMSDepositante, did) is None:
        raise HTTPException(404, "Depositante no encontrado.")
    u = await db.get(Usuario, data.usuario_id)
    if u is None:
        raise HTTPException(404, "Usuario no encontrado.")
    if u.rol == "ADMINISTRADOR":
        raise HTTPException(422, "Un administrador no puede ser usuario del portal: créele un usuario aparte al cliente.")
    actual = (await db.execute(select(WMSDepositanteUsuario).where(WMSDepositanteUsuario.usuario_id == u.id))).scalar_one_or_none()
    if actual and actual.depositante_id != did:
        raise HTTPException(409, "Ese usuario ya es del portal de otro depositante.")
    if actual is None:
        db.add(WMSDepositanteUsuario(usuario_id=u.id, depositante_id=did))
    return {"ok": True}


@router.delete("/depositantes/{did}/usuarios/{uid}")
async def desvincular(did: int, uid: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_supervisor)):
    v = (await db.execute(select(WMSDepositanteUsuario).where(WMSDepositanteUsuario.usuario_id == uid,
                                                              WMSDepositanteUsuario.depositante_id == did))).scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Ese usuario no es del portal de este depositante.")
    await db.delete(v)
    return {"ok": True}
