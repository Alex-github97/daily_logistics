"""
WMS · Consolidación de salida y solicitud de transporte. Prefijo: /wms/consolidacion

Lo alistado (picking terminado) espera en el staging de salida. Aquí:

1. Cada orden tiene un DESTINO (obligatorio). Solo se consolidan juntas las
   órdenes del mismo destino: el consolidado (estiba, jaula, bolsa) nace con el
   destino de su primera orden y rechaza las de otro.
2. Se consolida por lotes (varias órdenes en un consolidado) o individual (una
   orden, un consolidado). El consolidado se cierra con sus bultos y tiene
   etiqueta con código de barras.
3. Se asigna el modo de despacho (en lote o uno a uno): paqueteo urbano propio
   o tercerizado, paqueteo nacional tercerizado, o viaje con flota propia.
4. «Solicitar transporte» lo envía al TMS (una solicitud por modo y
   transportadora). Allí se asigna a los vehículos y se despacha.
"""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.marketplace import MKPConector, MKPPedido
from app.infrastructure.models.tms import TMSSolicitudTransporte
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSCliente, WMSConsolidado, WMSConsolidadoOrden, WMSOrdenSalida, WMSOrdenSalidaDetalle,
    WMSPickingDetalle, WMSPickingTarea, WMSTransportadora,
)

router = APIRouter(prefix="/wms/consolidacion", tags=["wms-consolidacion"])

MODOS = {
    "PAQUETEO_URBANO_PROPIO": "Paqueteo urbano propio",
    "PAQUETEO_URBANO_TERCERO": "Paqueteo urbano tercerizado",
    "PAQUETEO_NACIONAL_TERCERO": "Paqueteo nacional tercerizado",
    "FLOTA_PROPIA": "Viaje con flota propia",
}
TERCERIZADOS = ("PAQUETEO_URBANO_TERCERO", "PAQUETEO_NACIONAL_TERCERO")
ACTIVOS = ("ABIERTO", "CERRADO", "SOLICITADO", "EN_CARGUE")


def clave_destino(texto: Optional[str]) -> Optional[str]:
    """«Bogotá D.C.» → «BOGOTA D.C.»: sin tildes, en mayúsculas, sin espacios dobles."""
    if not texto or not texto.strip():
        return None
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())[:80]


async def _numero(db, Modelo, col, prefijo) -> str:
    from app.api.v1.endpoints.wms import _next_numero
    return await _next_numero(db, Modelo, col, prefijo)


async def _pendiente_por_orden(db, orden_ids) -> Dict[int, Dict[int, float]]:
    """Lo alistado sin despachar de cada orden, por producto."""
    filas = (await db.execute(select(WMSPickingTarea.orden_id, WMSPickingDetalle.producto_id,
                                     func.sum(WMSPickingDetalle.cantidad_pickeada - WMSPickingDetalle.cantidad_despachada))
                              .join(WMSPickingDetalle, WMSPickingDetalle.tarea_id == WMSPickingTarea.id)
                              .where(WMSPickingTarea.orden_id.in_(list(orden_ids) or [0]), WMSPickingDetalle.confirmado.is_(True))
                              .group_by(WMSPickingTarea.orden_id, WMSPickingDetalle.producto_id))).all()
    out: Dict[int, Dict[int, float]] = defaultdict(dict)
    for o, p, n in filas:
        if n and n > 0:
            out[o][p] = float(n)
    return out


async def _alistadas(db, almacen_id: Optional[int]) -> List[WMSOrdenSalida]:
    """Órdenes con todo su picking terminado y algo alistado sin despachar."""
    q = select(WMSOrdenSalida).where(WMSOrdenSalida.estado.notin_(("DESPACHADO", "ENTREGADO", "CANCELADO")),
                                     WMSOrdenSalida.deleted_at.is_(None))
    if almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == almacen_id)
    ordenes = (await db.execute(q)).scalars().all()
    if not ordenes:
        return []
    tareas = defaultdict(list)
    for o, e in (await db.execute(select(WMSPickingTarea.orden_id, WMSPickingTarea.estado).where(
            WMSPickingTarea.orden_id.in_([o.id for o in ordenes])))).all():
        tareas[o].append(e)
    pend = await _pendiente_por_orden(db, [o.id for o in ordenes])
    return [o for o in ordenes if tareas[o.id] and all(e in ("COMPLETADA", "CANCELADA") for e in tareas[o.id])
            and any(e == "COMPLETADA" for e in tareas[o.id]) and pend.get(o.id)]


async def _en_consolidado(db, orden_ids) -> Dict[int, WMSConsolidado]:
    filas = (await db.execute(select(WMSConsolidadoOrden.orden_id, WMSConsolidado).join(
        WMSConsolidado, WMSConsolidado.id == WMSConsolidadoOrden.consolidado_id).where(
        WMSConsolidadoOrden.orden_id.in_(list(orden_ids) or [0]), WMSConsolidado.estado.in_(ACTIVOS)))).all()
    return {o: c for o, c in filas}


async def _completar_destino(db, o: WMSOrdenSalida) -> None:
    """Si la orden no tiene destino, se toma del pedido del canal o del cliente."""
    if o.destino:
        return
    p = (await db.execute(select(MKPPedido).where(MKPPedido.orden_salida_id == o.id))).scalar()
    if p and p.ciudad:
        o.destino, o.destino_ciudad = clave_destino(p.ciudad), p.ciudad
        o.destino_direccion = o.destino_direccion or p.direccion
        o.destino_contacto = o.destino_contacto or p.comprador
        o.destino_telefono = o.destino_telefono or p.telefono
        return
    c = await db.get(WMSCliente, o.cliente_id)
    if c and c.ciudad:
        o.destino, o.destino_ciudad = clave_destino(c.ciudad), c.ciudad
        o.destino_contacto = o.destino_contacto or c.nombre
        o.destino_telefono = o.destino_telefono or c.telefono


async def _ordenes_dict(db, ordenes: List[WMSOrdenSalida]) -> List[dict]:
    from app.core import tms_capacidad
    pend = await _pendiente_por_orden(db, [o.id for o in ordenes])
    pedidos = {p.orden_salida_id: p for p in (await db.execute(select(MKPPedido).where(
        MKPPedido.orden_salida_id.in_([o.id for o in ordenes] or [0])))).scalars()}
    conectores = {c.id: c for c in (await db.execute(select(MKPConector))).scalars()}
    clientes = {c.id: c for c in (await db.execute(select(WMSCliente).where(
        WMSCliente.id.in_({o.cliente_id for o in ordenes} or {0})))).scalars()}
    cons = await _en_consolidado(db, [o.id for o in ordenes])
    out = []
    for o in ordenes:
        lineas = pend.get(o.id, {})
        est = await tms_capacidad.estimar_carga(db, list(lineas.items())) if lineas else {"peso_kg": None, "volumen_m3": None}
        p = pedidos.get(o.id)
        c = cons.get(o.id)
        out.append({"id": o.id, "numero": o.numero_orden, "cliente": clientes[o.cliente_id].nombre if o.cliente_id in clientes else None,
                    "almacen_id": o.almacen_id, "canal": o.canal, "prioridad": o.prioridad,
                    "pedido": p.pedido_externo if p else None,
                    "plataforma": conectores[p.conector_id].nombre if p and p.conector_id in conectores else None,
                    "destino": o.destino, "destino_ciudad": o.destino_ciudad, "destino_direccion": o.destino_direccion,
                    "destino_contacto": o.destino_contacto, "destino_telefono": o.destino_telefono,
                    "destino_lat": o.destino_lat, "destino_lng": o.destino_lng, "destino_geo": o.destino_geo,
                    "unidades": round(sum(lineas.values()), 3), "productos": len(lineas),
                    "peso_kg": est["peso_kg"], "volumen_m3": est["volumen_m3"],
                    "consolidado_id": c.id if c else None, "consolidado": c.codigo if c else None})
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Órdenes por consolidar y su destino
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/por-consolidar")
async def por_consolidar(almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    ordenes = await _alistadas(db, almacen_id)
    cons = await _en_consolidado(db, [o.id for o in ordenes])
    libres = [o for o in ordenes if o.id not in cons]
    for o in libres:
        await _completar_destino(db, o)
    await db.flush()
    return await _ordenes_dict(db, sorted(libres, key=lambda o: (o.destino or "~", o.id)))


class DestinoIn(BaseModel):
    destino: str = Field(min_length=2, max_length=80)
    ciudad: Optional[str] = Field(None, max_length=120)
    direccion: Optional[str] = Field(None, max_length=300)
    contacto: Optional[str] = Field(None, max_length=200)
    telefono: Optional[str] = Field(None, max_length=40)


@router.put("/ordenes/{oid}/destino")
async def guardar_destino(oid: int, d: DestinoIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    o = await db.get(WMSOrdenSalida, oid)
    if o is None:
        raise HTTPException(404, "Orden no encontrada.")
    c = (await _en_consolidado(db, [oid])).get(oid)
    if c and clave_destino(d.destino) != c.destino:
        raise HTTPException(409, f"La orden está en el consolidado {c.codigo} (destino {c.destino}): sáquela antes de cambiar su destino.")
    antes = (o.destino_direccion, o.destino_ciudad)
    o.destino = clave_destino(d.destino)
    o.destino_ciudad = d.ciudad or o.destino_ciudad or d.destino
    o.destino_direccion, o.destino_contacto, o.destino_telefono = d.direccion, d.contacto, d.telefono
    if antes != (o.destino_direccion, o.destino_ciudad):
        o.destino_lat = o.destino_lng = o.destino_geo = None     # el ciclo de fondo la vuelve a ubicar
    await db.flush()
    return (await _ordenes_dict(db, [o]))[0]


# ═════════════════════════════════════════════════════════════════════════════
# Consolidados
# ═════════════════════════════════════════════════════════════════════════════
async def _cons_dict(db, cs: List[WMSConsolidado]) -> List[dict]:
    rel = defaultdict(list)
    for r in (await db.execute(select(WMSConsolidadoOrden).where(
            WMSConsolidadoOrden.consolidado_id.in_([c.id for c in cs] or [0])))).scalars():
        rel[r.consolidado_id].append(r)
    ordenes = {o.id: o for o in (await db.execute(select(WMSOrdenSalida).where(
        WMSOrdenSalida.id.in_({r.orden_id for rs in rel.values() for r in rs} or {0})))).scalars()}
    pedidos = {p.orden_salida_id: p.pedido_externo for p in (await db.execute(select(MKPPedido).where(
        MKPPedido.orden_salida_id.in_(list(ordenes) or [0])))).scalars()}
    trans = {t.id: t.nombre for t in (await db.execute(select(WMSTransportadora))).scalars()}
    sols = {s.id: s.codigo for s in (await db.execute(select(TMSSolicitudTransporte).where(
        TMSSolicitudTransporte.id.in_({c.solicitud_id for c in cs if c.solicitud_id} or {0})))).scalars()}
    out = []
    for c in cs:
        rs = rel[c.id]
        out.append({"id": c.id, "codigo": c.codigo, "almacen_id": c.almacen_id, "destino": c.destino, "destino_ciudad": c.destino_ciudad,
                    "estado": c.estado, "individual": c.individual, "modo_despacho": c.modo_despacho,
                    "modo_nombre": MODOS.get(c.modo_despacho or ""), "transportadora_id": c.transportadora_id,
                    "transportadora": trans.get(c.transportadora_id), "guia": c.guia, "bultos": c.bultos,
                    "peso_kg": c.peso_kg, "volumen_m3": c.volumen_m3, "solicitud": sols.get(c.solicitud_id),
                    "cargue_id": c.cargue_id, "viaje_id": c.viaje_id, "notas": c.notas,
                    "creado": c.created_at.isoformat() if c.created_at else None,
                    "ordenes": [{"orden_id": r.orden_id, "numero": ordenes[r.orden_id].numero_orden if r.orden_id in ordenes else None,
                                 "pedido": pedidos.get(r.orden_id),
                                 "direccion": ordenes[r.orden_id].destino_direccion if r.orden_id in ordenes else None,
                                 "contacto": ordenes[r.orden_id].destino_contacto if r.orden_id in ordenes else None,
                                 "peso_kg": r.peso_kg, "volumen_m3": r.volumen_m3} for r in rs]})
    return out


async def _cons(db, cid: int, estados=None) -> WMSConsolidado:
    c = (await db.execute(select(WMSConsolidado).where(WMSConsolidado.id == cid).with_for_update())).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Consolidado no encontrado.")
    if estados and c.estado not in estados:
        raise HTTPException(409, f"El consolidado {c.codigo} está {c.estado.lower().replace('_', ' ')}.")
    return c


async def _agregar(db, c: WMSConsolidado, orden_ids: List[int]) -> None:
    """Agrega órdenes alistadas del mismo destino (la regla que separa la consolidación)."""
    from app.core import tms_capacidad
    alistadas = {o.id: o for o in await _alistadas(db, c.almacen_id)}
    ya = await _en_consolidado(db, orden_ids)
    pend = await _pendiente_por_orden(db, orden_ids)
    for oid in orden_ids:
        o = alistadas.get(oid)
        if o is None:
            o2 = await db.get(WMSOrdenSalida, oid)
            raise HTTPException(409, f"La orden {o2.numero_orden if o2 else oid} no está alistada (su picking no ha terminado) o es de otro almacén.")
        if oid in ya:
            raise HTTPException(409, f"La orden {o.numero_orden} ya está en el consolidado {ya[oid].codigo}.")
        await _completar_destino(db, o)
        if not o.destino:
            raise HTTPException(422, f"La orden {o.numero_orden} no tiene destino: asígnelo antes de consolidar.")
        if o.destino != c.destino:
            raise HTTPException(409, f"La orden {o.numero_orden} va para {o.destino} y el consolidado {c.codigo} es para {c.destino}: "
                                     "no se mezclan destinos. Consolídela aparte.")
        est = await tms_capacidad.estimar_carga(db, list(pend.get(oid, {}).items()))
        db.add(WMSConsolidadoOrden(consolidado_id=c.id, orden_id=oid, peso_kg=est["peso_kg"], volumen_m3=est["volumen_m3"]))
    await db.flush()
    await _totales(db, c)


async def _totales(db, c: WMSConsolidado) -> None:
    rs = (await db.execute(select(WMSConsolidadoOrden).where(WMSConsolidadoOrden.consolidado_id == c.id))).scalars().all()
    c.peso_kg = round(sum(r.peso_kg or 0 for r in rs), 3) if rs and all(r.peso_kg is not None for r in rs) else None
    c.volumen_m3 = round(sum(r.volumen_m3 or 0 for r in rs), 4) if rs and all(r.volumen_m3 is not None for r in rs) else None


class ConsolidarIn(BaseModel):
    orden_ids: List[int] = Field(min_length=1)
    individual: bool = False      # True: un consolidado por orden (ya cerrado)
    bultos: Optional[int] = Field(None, ge=1)


@router.post("/consolidados", status_code=201)
async def consolidar(d: ConsolidarIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    ordenes = [await db.get(WMSOrdenSalida, i) for i in d.orden_ids]
    if any(o is None for o in ordenes):
        raise HTTPException(404, "Alguna orden no existe.")
    for o in ordenes:
        await _completar_destino(db, o)
    sin = [o.numero_orden for o in ordenes if not o.destino]
    if sin:
        raise HTTPException(422, f"Asigne el destino a: {', '.join(sin)}. Sin destino no se consolida.")
    if len({o.almacen_id for o in ordenes}) > 1:
        raise HTTPException(409, "Las órdenes son de almacenes distintos.")
    grupos = [[o] for o in ordenes] if d.individual else [ordenes]
    if not d.individual and len({o.destino for o in ordenes}) > 1:
        raise HTTPException(409, "Las órdenes tienen destinos distintos (" + ", ".join(sorted({o.destino for o in ordenes}))
                                 + "): un consolidado lleva un solo destino. Consolide por destino o use «individual».")
    creados = []
    for g in grupos:
        c = WMSConsolidado(codigo=await _numero(db, WMSConsolidado, WMSConsolidado.codigo, "CON"), almacen_id=g[0].almacen_id,
                           destino=g[0].destino, destino_ciudad=g[0].destino_ciudad, estado="ABIERTO", individual=d.individual,
                           bultos=d.bultos or len(g), creado_por_id=yo.id)
        db.add(c)
        await db.flush()
        await _agregar(db, c, [o.id for o in g])
        if d.individual:
            c.estado, c.cerrado_en = "CERRADO", datetime.now(timezone.utc)
        creados.append(c)
    await db.flush()
    return await _cons_dict(db, creados)


class OrdenesIn(BaseModel):
    orden_ids: List[int] = Field(min_length=1)


@router.post("/consolidados/{cid}/ordenes")
async def agregar_ordenes(cid: int, d: OrdenesIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await _cons(db, cid, ("ABIERTO",))
    await _agregar(db, c, d.orden_ids)
    return (await _cons_dict(db, [c]))[0]


@router.delete("/consolidados/{cid}/ordenes/{oid}")
async def quitar_orden(cid: int, oid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await _cons(db, cid, ("ABIERTO",))
    r = (await db.execute(select(WMSConsolidadoOrden).where(WMSConsolidadoOrden.consolidado_id == cid,
                                                            WMSConsolidadoOrden.orden_id == oid))).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "La orden no está en el consolidado.")
    await db.delete(r)
    await db.flush()
    await _totales(db, c)
    return (await _cons_dict(db, [c]))[0]


class CerrarIn(BaseModel):
    bultos: int = Field(ge=1, le=999)
    notas: Optional[str] = Field(None, max_length=300)


@router.post("/consolidados/{cid}/cerrar")
async def cerrar(cid: int, d: CerrarIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await _cons(db, cid, ("ABIERTO",))
    n = (await db.execute(select(func.count()).where(WMSConsolidadoOrden.consolidado_id == cid))).scalar()
    if not n:
        raise HTTPException(409, "El consolidado está vacío.")
    c.estado, c.bultos, c.notas, c.cerrado_en = "CERRADO", d.bultos, d.notas, datetime.now(timezone.utc)
    return (await _cons_dict(db, [c]))[0]


@router.post("/consolidados/{cid}/reabrir")
async def reabrir(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await _cons(db, cid, ("CERRADO",))
    c.estado, c.cerrado_en = "ABIERTO", None
    return (await _cons_dict(db, [c]))[0]


@router.post("/consolidados/{cid}/anular")
async def anular(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Deshace el consolidado: sus órdenes vuelven a «por consolidar»."""
    c = await _cons(db, cid, ("ABIERTO", "CERRADO"))
    for r in (await db.execute(select(WMSConsolidadoOrden).where(WMSConsolidadoOrden.consolidado_id == cid))).scalars().all():
        await db.delete(r)
    c.estado = "ANULADO"
    return {"ok": True}


class ModoIn(BaseModel):
    ids: List[int] = Field(min_length=1)
    modo: str
    transportadora_id: Optional[int] = None
    guia: Optional[str] = Field(None, max_length=80)


@router.post("/modo")
async def asignar_modo(d: ModoIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Modo de despacho para uno o varios consolidados (en lote o individual)."""
    if d.modo not in MODOS:
        raise HTTPException(422, f"Modo inválido: use {', '.join(MODOS)}.")
    if d.modo in TERCERIZADOS:
        if not d.transportadora_id or await db.get(WMSTransportadora, d.transportadora_id) is None:
            raise HTTPException(422, "Un despacho tercerizado necesita la transportadora.")
    cs = []
    for cid in d.ids:
        c = await _cons(db, cid, ("ABIERTO", "CERRADO"))
        c.modo_despacho = d.modo
        c.transportadora_id = d.transportadora_id if d.modo in TERCERIZADOS else None
        if d.guia and len(d.ids) == 1:
            c.guia = d.guia
        cs.append(c)
    return await _cons_dict(db, cs)


class SolicitarIn(BaseModel):
    ids: List[int] = Field(min_length=1)
    notas: Optional[str] = Field(None, max_length=500)


@router.post("/solicitar-transporte")
async def solicitar_transporte(d: SolicitarIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Envía al TMS los consolidados cerrados y con modo: una solicitud por
    almacén, modo y transportadora."""
    cs = [await _cons(db, cid) for cid in d.ids]
    for c in cs:
        if c.estado != "CERRADO":
            raise HTTPException(409, f"{c.codigo} está {c.estado.lower()}: ciérrelo antes de solicitar transporte.")
        if not c.modo_despacho:
            raise HTTPException(409, f"{c.codigo} no tiene modo de despacho.")
    grupos = defaultdict(list)
    for c in cs:
        grupos[(c.almacen_id, c.modo_despacho, c.transportadora_id)].append(c)
    sols = []
    for (alm, modo, trans), g in grupos.items():
        s = TMSSolicitudTransporte(codigo=await _numero(db, TMSSolicitudTransporte, TMSSolicitudTransporte.codigo, "SOL"),
                                   almacen_id=alm, modo_despacho=modo, transportadora_id=trans, estado="PENDIENTE",
                                   solicitado_por_id=yo.id, notas=d.notas)
        db.add(s)
        await db.flush()
        for c in g:
            c.estado, c.solicitud_id = "SOLICITADO", s.id
        sols.append({"codigo": s.codigo, "modo": MODOS[modo], "consolidados": len(g)})
    return {"solicitudes": sols}


@router.get("/consolidados")
async def listar(almacen_id: Optional[int] = None, estado: Optional[str] = None, db: AsyncSession = Depends(get_db),
                 _=Depends(get_current_user)):
    q = select(WMSConsolidado)
    if almacen_id:
        q = q.where(WMSConsolidado.almacen_id == almacen_id)
    q = q.where(WMSConsolidado.estado.in_(estado.split(","))) if estado else q.where(WMSConsolidado.estado != "ANULADO")
    cs = (await db.execute(q.order_by(WMSConsolidado.id.desc()).limit(500))).scalars().all()
    return await _cons_dict(db, cs)


@router.get("/modos")
async def modos(_=Depends(get_current_user)):
    return [{"clave": k, "nombre": v, "tercerizado": k in TERCERIZADOS} for k, v in MODOS.items()]


@router.get("/consolidados/{cid}/etiqueta")
async def etiqueta(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Etiqueta del consolidado (código de barras que se escanea al cargar el vehículo)."""
    from fpdf import FPDF
    c = await db.get(WMSConsolidado, cid)
    if c is None:
        raise HTTPException(404, "Consolidado no encontrado.")
    info = (await _cons_dict(db, [c]))[0]
    alm = await db.get(WMSAlmacen, c.almacen_id)
    pdf = FPDF(orientation="L", unit="mm", format=(100, 150))
    pdf.add_font("dj", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    pdf.add_font("dj", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    for b in range(1, max(1, c.bultos) + 1):
        pdf.add_page()
        pdf.set_auto_page_break(False)
        pdf.set_font("dj", "B", 11); pdf.set_xy(6, 5); pdf.cell(0, 6, f"{alm.nombre if alm else ''} · CONSOLIDADO")
        pdf.set_font("dj", "B", 30); pdf.set_xy(6, 12); pdf.cell(0, 13, c.destino[:22])
        pdf.set_font("dj", "", 10); pdf.set_xy(6, 26)
        pdf.cell(0, 5, f"{info['modo_nombre'] or 'Modo de despacho por asignar'}{' · ' + info['transportadora'] if info['transportadora'] else ''}")
        pdf.set_xy(6, 32); pdf.cell(0, 5, f"{len(info['ordenes'])} pedido(s) · bulto {b} de {c.bultos}"
                                         + (f" · {c.peso_kg:g} kg" if c.peso_kg else ""))
        pdf.set_fill_color(0, 0, 0)
        pdf.code39(f"*{c.codigo}*", x=8, y=42, w=0.75, h=26)
        pdf.set_font("dj", "B", 16); pdf.set_xy(6, 70); pdf.cell(138, 8, c.codigo, align="C")
        pdf.set_font("dj", "", 7.5); pdf.set_xy(6, 80)
        pdf.multi_cell(138, 3.6, "Pedidos: " + ", ".join((o["pedido"] or o["numero"] or "") for o in info["ordenes"])[:380])
    return Response(bytes(pdf.output()), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{c.codigo}.pdf"'})
