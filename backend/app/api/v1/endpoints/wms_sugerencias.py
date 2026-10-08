"""
WMS · Sugerencias: slotting (ABC y reubicación), olas de alistamiento con
ruta, empaque y maquila.
Prefijo: /wms
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_cubicaje as cub
from app.core import wms_inventario as inv
from app.core import wms_slotting as sl
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSCajaEmpaque, WMSContenedor, WMSEmpaqueOrden, WMSInventarioUbicacion, WMSLote, WMSOla, WMSOrdenSalida,
    WMSOrdenSalidaDetalle, WMSPickingDetalle, WMSPickingTarea, WMSProducto, WMSProductoEmpaque, WMSTarea, WMSUbicacion,
    WMSZona,
)

router = APIRouter(prefix="/wms", tags=["wms-sugerencias"])


# ── Slotting ─────────────────────────────────────────────────────────────────

@router.get("/slotting/ubicaciones")
async def recorrido(almacen_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Las ubicaciones de almacenamiento en el orden del recorrido, con las preferentes marcadas."""
    return [u.__dict__ for u in await sl.ubicaciones_ordenadas(db, almacen_id)]


@router.get("/slotting/abc")
async def clasificacion(almacen_id: int, dias: int = Query(90, ge=7, le=730), db: AsyncSession = Depends(get_db),
                        _=Depends(get_current_user)):
    clases = await sl.abc(db, almacen_id, dias)
    ubic = {u.id: u for u in await sl.ubicaciones_ordenadas(db, almacen_id)}
    donde: dict = {}
    for f in (await db.execute(select(WMSInventarioUbicacion).where(
            WMSInventarioUbicacion.ubicacion_id.in_(list(ubic) or [0]),
            WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada > 0))).scalars():
        donde.setdefault(f.producto_id, []).append(ubic[f.ubicacion_id])
    prods = {p.id: p for p in (await db.execute(select(WMSProducto).where(WMSProducto.id.in_(list(clases) or [0])))).scalars()}
    out = []
    for pid, c in clases.items():
        lugares = sorted(donde.get(pid, []), key=lambda u: u.puesto)
        p = prods.get(pid)
        out.append({**c, "producto_id": pid, "sku": p.sku if p else None, "nombre": p.nombre if p else None,
                    "ubicaciones": [u.codigo for u in lugares], "en_preferente": any(u.preferente for u in lugares),
                    "mejor_puesto": lugares[0].puesto + 1 if lugares else None})
    orden = {"A": 0, "B": 1, "C": 2}
    return sorted(out, key=lambda x: (orden[x["clase"]], -x["lineas"]))


@router.get("/slotting/sugerencias")
async def sugerencias(almacen_id: int, dias: int = Query(90, ge=7, le=730), db: AsyncSession = Depends(get_db),
                      _=Depends(get_current_user)):
    return await sl.sugerencias(db, almacen_id, dias)


class MovimientoIn(BaseModel):
    producto_id: int
    lote_id: Optional[int] = None
    cantidad: float = Field(gt=0)
    origen_id: int
    destino_id: int
    razon: Optional[str] = Field(default=None, max_length=200)


class AplicarIn(BaseModel):
    almacen_id: int
    movimientos: List[MovimientoIn]


@router.post("/slotting/aplicar", status_code=201)
async def aplicar(data: AplicarIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Convierte las sugerencias aceptadas en tareas de movimiento: alguien
    las hace escaneando, y quedan en el kárdex como cualquier otra tarea."""
    if not data.movimientos:
        raise HTTPException(422, "No hay movimientos para aplicar.")
    creadas = []
    for m in data.movimientos:
        if m.origen_id == m.destino_id:
            raise HTTPException(422, "El origen y el destino son la misma ubicación.")
        for u in (m.origen_id, m.destino_id):
            if await inv.almacen_de(db, u) != data.almacen_id:
                raise HTTPException(422, "Las ubicaciones tienen que ser del almacén indicado.")
        f = await inv.fila(db, m.producto_id, m.origen_id, m.lote_id)
        if f is None or (f.cantidad_disponible or 0) < m.cantidad:
            raise HTTPException(409, "La existencia de origen cambió: recalcule las sugerencias.")
        abierta = (await db.execute(select(WMSTarea.id).where(
            WMSTarea.tipo == "MOVIMIENTO", WMSTarea.estado.in_(("PENDIENTE", "EN_CURSO")),
            WMSTarea.producto_id == m.producto_id, WMSTarea.ubicacion_origen_id == m.origen_id))).first()
        if abierta:
            continue      # ya hay una tarea abierta para mover eso
        prod = await db.get(WMSProducto, m.producto_id)
        t = WMSTarea(tipo="MOVIMIENTO", estado="PENDIENTE", prioridad=7, almacen_id=data.almacen_id,
                     depositante_id=prod.depositante_id if prod else None, producto_id=m.producto_id, lote_id=m.lote_id,
                     cantidad=m.cantidad, ubicacion_origen_id=m.origen_id, ubicacion_sugerida_id=m.destino_id,
                     razon_sugerencia=m.razon or "Reubicación por slotting", documento_tipo="SLOTTING")
        db.add(t)
        await db.flush()
        creadas.append(t.id)
    return {"tareas": creadas, "omitidas": len(data.movimientos) - len(creadas)}


# ── Olas de alistamiento ─────────────────────────────────────────────────────

PRIORIDAD = {"URGENTE": 0, "ALTA": 1, "NORMAL": 2, "BAJA": 3}


class OlaIn(BaseModel):
    almacen_id: int
    orden_ids: Optional[List[int]] = None
    hasta_fecha_requerida: Optional[date] = None
    prioridades: Optional[List[str]] = None
    max_ordenes: int = Field(default=30, ge=1, le=300)
    dias_vida_minima: int = Field(default=0, ge=0)


async def _siguiente_codigo(db) -> str:
    hoy = date.today().strftime("%Y%m%d")
    n = (await db.execute(select(func.count()).select_from(WMSOla))).scalar() + 1
    while (await db.execute(select(WMSOla.id).where(WMSOla.codigo == f"OLA-{hoy}-{n:04d}"))).first():
        n += 1
    return f"OLA-{hoy}-{n:04d}"


async def _rango_recorrido(db, almacen_id: int) -> dict:
    """Puesto de cada ubicación del almacén (todas las zonas) en la serpentina."""
    ubic = (await db.execute(select(WMSUbicacion).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
                             .where(WMSZona.almacen_id == almacen_id))).scalars().all()
    return {u.id: (i, u.codigo) for i, u in enumerate(sorted(ubic, key=sl.clave_recorrido))}


async def ruta_ola(db, ola: WMSOla) -> dict:
    """Las paradas de la ola en orden de recorrido: en cada una, cuánto sacar en
    total y a qué orden va cada parte. Compara el recorrido de la ola con el de
    alistar orden por orden."""
    tareas = (await db.execute(select(WMSPickingTarea).where(WMSPickingTarea.ola_id == ola.id))).scalars().all()
    ordenes = {o.id: o for o in (await db.execute(select(WMSOrdenSalida).where(
        WMSOrdenSalida.id.in_([t.orden_id for t in tareas] or [0])))).scalars()}
    tarea_orden = {t.id: ordenes.get(t.orden_id) for t in tareas}
    dets = (await db.execute(select(WMSPickingDetalle).where(
        WMSPickingDetalle.tarea_id.in_([t.id for t in tareas] or [0])))).scalars().all()
    puesto = await _rango_recorrido(db, ola.almacen_id)
    prods = {p.id: p for p in (await db.execute(select(WMSProducto).where(
        WMSProducto.id.in_({d.producto_id for d in dets} or {0})))).scalars()}
    lotes = dict((await db.execute(select(WMSLote.id, WMSLote.numero_lote).where(
        WMSLote.id.in_({d.lote_id for d in dets if d.lote_id} or {0})))).all())
    lpns = dict((await db.execute(select(WMSContenedor.id, WMSContenedor.codigo).where(
        WMSContenedor.id.in_({d.contenedor_id for d in dets if d.contenedor_id} or {0})))).all())
    paradas = defaultdict(list)
    for d in dets:
        paradas[(d.ubicacion_id, d.producto_id, d.lote_id, d.contenedor_id)].append(d)

    def prioridad(d):
        o = tarea_orden.get(d.tarea_id)
        if o is None:
            return (9, date.max, d.id)
        return (PRIORIDAD.get(o.prioridad, 2), o.fecha_requerida or date.max, d.id)
    out = []
    for (uid, pid, lid, cid), ds in sorted(paradas.items(), key=lambda kv: puesto.get(kv[0][0], (10 ** 6, ""))):
        ds = sorted(ds, key=prioridad)
        p = prods.get(pid)
        out.append({"ubicacion_id": uid, "ubicacion": puesto.get(uid, (0, "?"))[1], "puesto": puesto.get(uid, (0,))[0] + 1,
                    "producto_id": pid, "sku": p.sku if p else None, "producto": p.nombre if p else None,
                    "lote_id": lid, "lote": lotes.get(lid), "contenedor_id": cid, "contenedor": lpns.get(cid),
                    "cantidad": sum(d.cantidad_solicitada for d in ds if not d.confirmado),
                    "alistado": sum(d.cantidad_pickeada for d in ds if d.confirmado),
                    "hecha": all(d.confirmado for d in ds),
                    "reparto": [{"orden": tarea_orden[d.tarea_id].numero_orden if tarea_orden.get(d.tarea_id) else None,
                                 "tarea_id": d.tarea_id, "detalle_id": d.id, "cantidad": d.cantidad_solicitada,
                                 "alistado": d.cantidad_pickeada if d.confirmado else None} for d in ds]})

    # Recorrido: en la ola se camina una vez hasta la última parada; orden por
    # orden, cada orden camina hasta su propia última parada.
    def ultimo(ids):
        return max((puesto.get(u, (0,))[0] + 1 for u in ids), default=0)
    por_tarea = defaultdict(set)
    for d in dets:
        por_tarea[d.tarea_id].add(d.ubicacion_id)
    ola_puestos = ultimo({d.ubicacion_id for d in dets})
    separado = sum(ultimo(u) for u in por_tarea.values())
    return {"paradas": out, "visitas_ola": len(out), "visitas_orden_por_orden": sum(len(u) for u in por_tarea.values()),
            "recorrido_ola": ola_puestos, "recorrido_orden_por_orden": separado,
            "ahorro_recorrido_pct": round((1 - ola_puestos / separado) * 100, 1) if separado else None}


async def _ola_dict(db, ola: WMSOla, con_ruta: bool = True) -> dict:
    tareas = (await db.execute(select(WMSPickingTarea).where(WMSPickingTarea.ola_id == ola.id))).scalars().all()
    ordenes = {o.id: o for o in (await db.execute(select(WMSOrdenSalida).where(
        WMSOrdenSalida.id.in_([t.orden_id for t in tareas] or [0])))).scalars()}
    n_det = dict((await db.execute(select(WMSPickingDetalle.tarea_id, func.count()).where(
        WMSPickingDetalle.tarea_id.in_([t.id for t in tareas] or [0])).group_by(WMSPickingDetalle.tarea_id))).all())
    out = {"id": ola.id, "codigo": ola.codigo, "almacen_id": ola.almacen_id, "estado": ola.estado, "criterio": ola.criterio,
           "creada": ola.created_at.isoformat() if ola.created_at else None,
           "completada_en": ola.completada_en.isoformat() if ola.completada_en else None,
           "ordenes": [{"orden_id": t.orden_id, "numero": ordenes[t.orden_id].numero_orden, "tarea_id": t.id,
                        "prioridad": ordenes[t.orden_id].prioridad, "estado_tarea": t.estado,
                        "lineas": n_det.get(t.id, 0), "sin_existencia": n_det.get(t.id, 0) == 0} for t in tareas]}
    if con_ruta:
        out.update(await ruta_ola(db, ola))
    return out


@router.post("/olas", status_code=201)
async def crear_ola(data: OlaIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Agrupa órdenes pendientes del almacén (por prioridad y fecha requerida)
    y genera su alistamiento reservando con FEFO, como una sola ola."""
    from app.api.v1.endpoints.wms import crear_alistamiento
    q = select(WMSOrdenSalida).where(WMSOrdenSalida.deleted_at.is_(None), WMSOrdenSalida.almacen_id == data.almacen_id,
                                     WMSOrdenSalida.estado == "PENDIENTE")
    if data.orden_ids:
        q = q.where(WMSOrdenSalida.id.in_(data.orden_ids))
    if data.hasta_fecha_requerida:
        q = q.where(WMSOrdenSalida.fecha_requerida <= data.hasta_fecha_requerida)
    if data.prioridades:
        q = q.where(WMSOrdenSalida.prioridad.in_(data.prioridades))
    ordenes = sorted((await db.execute(q)).scalars().all(),
                     key=lambda o: (PRIORIDAD.get(o.prioridad, 2), o.fecha_requerida or date.max, o.id))[:data.max_ordenes]
    if data.orden_ids and len(ordenes) != len(set(data.orden_ids)):
        raise HTTPException(422, "Alguna orden no existe, no es de ese almacén o ya no está pendiente.")
    if not ordenes:
        raise HTTPException(422, "No hay órdenes pendientes que cumplan el criterio.")
    partes = [f"hasta {data.hasta_fecha_requerida}" if data.hasta_fecha_requerida else "",
              f"prioridad {'/'.join(data.prioridades)}" if data.prioridades else "",
              "órdenes elegidas" if data.orden_ids else ""]
    ola = WMSOla(codigo=await _siguiente_codigo(db), almacen_id=data.almacen_id, estado="ABIERTA",
                 criterio=", ".join(x for x in partes if x) or "pendientes por prioridad y fecha", creada_por_id=yo.id)
    db.add(ola)
    await db.flush()
    for o in ordenes:
        await crear_alistamiento(db, o.id, "WAVE", data.dias_vida_minima, 30, yo.id, ola.id)
    await db.flush()
    return await _ola_dict(db, ola)


@router.get("/olas")
async def listar_olas(almacen_id: Optional[int] = None, estado: Optional[str] = None, db: AsyncSession = Depends(get_db),
                      _=Depends(get_current_user)):
    q = select(WMSOla)
    if almacen_id:
        q = q.where(WMSOla.almacen_id == almacen_id)
    if estado:
        q = q.where(WMSOla.estado.in_(estado.split(",")))
    olas = (await db.execute(q.order_by(WMSOla.id.desc()).limit(200))).scalars().all()
    return [await _ola_dict(db, o, con_ruta=False) for o in olas]


async def _ola(db, oid) -> WMSOla:
    o = (await db.execute(select(WMSOla).where(WMSOla.id == oid).with_for_update())).scalar_one_or_none()
    if o is None:
        raise HTTPException(404, "Ola no encontrada.")
    return o


@router.get("/olas/{oid}")
async def ver_ola(oid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await _ola_dict(db, await _ola(db, oid))


class ParadaIn(BaseModel):
    ubicacion_id: int
    producto_id: int
    lote_id: Optional[int] = None
    contenedor_id: Optional[int] = None
    cantidad: float = Field(ge=0)
    ubicacion_codigo: Optional[str] = None
    producto_codigo: Optional[str] = None


@router.post("/olas/{oid}/parada")
async def confirmar_parada(oid: int, data: ParadaIn, db: AsyncSession = Depends(get_db),
                           yo: Usuario = Depends(get_current_user)):
    """Confirma una parada de la ola: lo alistado se reparte entre las órdenes
    por prioridad y fecha; si faltó, le falta a las últimas."""
    from app.api.v1.endpoints.wms import confirmar_linea
    ola = await _ola(db, oid)
    if ola.estado in ("COMPLETADA", "CANCELADA"):
        raise HTTPException(409, f"La ola está {ola.estado.lower()}.")
    ruta = await ruta_ola(db, ola)
    parada = next((p for p in ruta["paradas"] if (p["ubicacion_id"], p["producto_id"], p["lote_id"], p["contenedor_id"])
                   == (data.ubicacion_id, data.producto_id, data.lote_id, data.contenedor_id)), None)
    if parada is None:
        raise HTTPException(404, "Esa parada no es de esta ola.")
    pendientes = [r for r in parada["reparto"] if r["alistado"] is None]
    if not pendientes:
        raise HTTPException(409, "Esa parada ya está confirmada.")
    if data.cantidad > parada["cantidad"] + 1e-9:
        raise HTTPException(422, f"En esta parada se alistan {parada['cantidad']:g}, no {data.cantidad:g}.")
    queda = data.cantidad
    for r in pendientes:
        det = await db.get(WMSPickingDetalle, r["detalle_id"])
        tarea = await db.get(WMSPickingTarea, r["tarea_id"])
        tomar = min(queda, det.cantidad_solicitada)
        await confirmar_linea(db, tarea, det, tomar, yo.id, data.ubicacion_codigo, data.producto_codigo, permitir_cero=True)
        queda -= tomar
    ola.estado = "EN_CURSO"
    await db.flush()
    abiertas = (await db.execute(select(func.count()).select_from(WMSPickingDetalle)
                                 .join(WMSPickingTarea, WMSPickingTarea.id == WMSPickingDetalle.tarea_id)
                                 .where(WMSPickingTarea.ola_id == ola.id, WMSPickingDetalle.confirmado.isnot(True)))).scalar()
    if abiertas == 0:
        ola.estado, ola.completada_en = "COMPLETADA", datetime.now(timezone.utc)
    return await _ola_dict(db, ola)


# ── Empaque (cartonización) ──────────────────────────────────────────────────



class CajaIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=120)
    largo_cm: float = Field(gt=0)
    ancho_cm: float = Field(gt=0)
    alto_cm: float = Field(gt=0)
    peso_max_kg: float = Field(default=25, gt=0)
    tara_kg: float = Field(default=0, ge=0)
    costo: Optional[float] = Field(default=None, ge=0)
    activo: bool = True


def _caja_dict(c: WMSCajaEmpaque) -> dict:
    return {"id": c.id, "codigo": c.codigo, "nombre": c.nombre, "largo_cm": c.largo_cm, "ancho_cm": c.ancho_cm,
            "alto_cm": c.alto_cm, "peso_max_kg": c.peso_max_kg, "tara_kg": c.tara_kg, "costo": c.costo, "activo": c.activo,
            "volumen_m3": cub.volumen_m3(c.largo_cm, c.ancho_cm, c.alto_cm)}


@router.get("/cajas-empaque")
async def listar_cajas(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    cajas = (await db.execute(select(WMSCajaEmpaque))).scalars().all()
    return [_caja_dict(c) for c in sorted(cajas, key=lambda c: c.largo_cm * c.ancho_cm * c.alto_cm)]


@router.post("/cajas-empaque", status_code=201)
async def crear_caja(data: CajaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    if (await db.execute(select(WMSCajaEmpaque.id).where(WMSCajaEmpaque.codigo == data.codigo))).first():
        raise HTTPException(409, "Ya hay una caja con ese código.")
    c = WMSCajaEmpaque(**data.model_dump())
    db.add(c)
    await db.flush()
    return _caja_dict(c)


@router.put("/cajas-empaque/{cid}")
async def editar_caja(cid: int, data: CajaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    c = await db.get(WMSCajaEmpaque, cid)
    if c is None:
        raise HTTPException(404, "Caja no encontrada.")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    return _caja_dict(c)


async def _a_empacar(db, orden: WMSOrdenSalida) -> dict:
    """Lo que hay que empacar: lo alistado de la orden que todavía no ha salido;
    si no se ha alistado, lo pedido."""
    alistado = (await db.execute(select(WMSPickingDetalle.producto_id,
                                        func.sum(WMSPickingDetalle.cantidad_pickeada - WMSPickingDetalle.cantidad_despachada))
                                 .join(WMSPickingTarea, WMSPickingTarea.id == WMSPickingDetalle.tarea_id)
                                 .where(WMSPickingTarea.orden_id == orden.id, WMSPickingDetalle.confirmado.is_(True))
                                 .group_by(WMSPickingDetalle.producto_id))).all()
    if alistado:
        return {p: float(q) for p, q in alistado if q and q > 0}
    return {d.producto_id: float(d.cantidad_solicitada - (d.cantidad_despachada or 0)) for d in (await db.execute(
        select(WMSOrdenSalidaDetalle).where(WMSOrdenSalidaDetalle.orden_id == orden.id))).scalars()
        if d.cantidad_solicitada > (d.cantidad_despachada or 0)}


async def _orden(db, oid) -> WMSOrdenSalida:
    o = await db.get(WMSOrdenSalida, oid)
    if o is None or o.deleted_at:
        raise HTTPException(404, "Orden no encontrada.")
    return o


@router.post("/ordenes-salida/{oid}/empaque/sugerir")
async def sugerir_empaque(oid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    orden = await _orden(db, oid)
    cantidades = await _a_empacar(db, orden)
    if not cantidades:
        raise HTTPException(422, "La orden no tiene nada por empacar.")
    prods = {p.id: p for p in (await db.execute(select(WMSProducto).where(WMSProducto.id.in_(list(cantidades))))).scalars()}
    unidad = {e.producto_id: e for e in (await db.execute(select(WMSProductoEmpaque).where(
        WMSProductoEmpaque.producto_id.in_(list(cantidades)), WMSProductoEmpaque.nivel == "UNIDAD"))).scalars()}
    items, sin_medidas = [], []
    for pid, q in cantidades.items():
        e = unidad.get(pid)
        if not (e and e.largo_cm and e.ancho_cm and e.alto_cm):
            sin_medidas.append({"producto_id": pid, "sku": prods[pid].sku, "cantidad": q})
            continue
        items.append(cub.Item(pid, (e.largo_cm, e.ancho_cm, e.alto_cm), e.peso_kg or prods[pid].peso_kg or 0, int(round(q))))
    cajas = [cub.CajaTipo(c.id, c.codigo, (c.largo_cm, c.ancho_cm, c.alto_cm), c.peso_max_kg, c.tara_kg)
             for c in (await db.execute(select(WMSCajaEmpaque).where(WMSCajaEmpaque.activo.is_(True)))).scalars()]
    try:
        r = cub.cartonizar(items, cajas) if items else {"bultos": [], "sin_caja": [], "peso_total_kg": 0,
                                                       "volumen_total_m3": 0, "peso_facturable_kg": 0}
    except ValueError as e:
        raise HTTPException(422, str(e))
    for b in r["bultos"]:
        for c in b["contenido"]:
            c["producto_id"] = c.pop("clave")
            c["sku"] = prods[c["producto_id"]].sku
    for c in r["sin_caja"]:
        c["producto_id"] = c.pop("clave")
        c["sku"] = prods[c["producto_id"]].sku
    avisos = []
    if sin_medidas:
        avisos.append(f"{len(sin_medidas)} productos sin medidas de unidad no se pudieron acomodar: cubíquelos primero.")
    if r["sin_caja"]:
        avisos.append("Hay unidades que no caben en ninguna caja del catálogo: van en su propio empaque.")
    return {**r, "sin_medidas": sin_medidas, "avisos": avisos}


class BultoIn(BaseModel):
    caja_id: Optional[int] = None
    largo_cm: Optional[float] = Field(default=None, gt=0)
    ancho_cm: Optional[float] = Field(default=None, gt=0)
    alto_cm: Optional[float] = Field(default=None, gt=0)
    peso_kg: Optional[float] = Field(default=None, ge=0)
    contenido: List[dict]


class EmpaqueIn(BaseModel):
    bultos: List[BultoIn]


def _bulto_dict(b: WMSEmpaqueOrden, total: int) -> dict:
    return {"id": b.id, "numero": b.numero, "de": total, "caja_id": b.caja_id, "largo_cm": b.largo_cm, "ancho_cm": b.ancho_cm,
            "alto_cm": b.alto_cm, "peso_kg": b.peso_kg, "contenido": b.contenido,
            "volumen_m3": cub.volumen_m3(b.largo_cm, b.ancho_cm, b.alto_cm)}


@router.post("/ordenes-salida/{oid}/empaque/confirmar")
async def confirmar_empaque(oid: int, data: EmpaqueIn, db: AsyncSession = Depends(get_db),
                            yo: Usuario = Depends(get_current_user)):
    """Registra los bultos de la orden (reemplaza los anteriores). Lo empacado no
    puede pasar de lo que hay por empacar."""
    orden = await _orden(db, oid)
    if orden.estado in ("DESPACHADO", "ENTREGADO", "CANCELADO"):
        raise HTTPException(409, f"La orden está {orden.estado.lower()}.")
    if not data.bultos:
        raise HTTPException(422, "Indique al menos un bulto.")
    hay = await _a_empacar(db, orden)
    suma: dict = {}
    for b in data.bultos:
        for c in b.contenido:
            suma[int(c["producto_id"])] = suma.get(int(c["producto_id"]), 0) + float(c["cantidad"])
    for pid, q in suma.items():
        if q > hay.get(pid, 0) + 1e-9:
            raise HTTPException(422, f"Del producto {pid} se empacan {q:g} y hay {hay.get(pid, 0):g} por empacar.")
    for viejo in (await db.execute(select(WMSEmpaqueOrden).where(WMSEmpaqueOrden.orden_id == oid))).scalars():
        await db.delete(viejo)
    creados = []
    for n, b in enumerate(data.bultos, start=1):
        caja = await db.get(WMSCajaEmpaque, b.caja_id) if b.caja_id else None
        reg = WMSEmpaqueOrden(orden_id=oid, numero=n, caja_id=b.caja_id,
                              largo_cm=b.largo_cm or (caja.largo_cm if caja else None),
                              ancho_cm=b.ancho_cm or (caja.ancho_cm if caja else None),
                              alto_cm=b.alto_cm or (caja.alto_cm if caja else None),
                              peso_kg=b.peso_kg, contenido=b.contenido, creado_por_id=yo.id)
        db.add(reg)
        creados.append(reg)
    if orden.estado in ("PENDIENTE", "EN_PICKING"):
        orden.estado = "EMPACANDO"
    await db.flush()
    peso = sum(b.peso_kg or 0 for b in creados)
    vol = sum(cub.volumen_m3(b.largo_cm, b.ancho_cm, b.alto_cm) or 0 for b in creados)
    return {"bultos": [_bulto_dict(b, len(creados)) for b in creados], "peso_total_kg": round(peso, 3),
            "volumen_total_m3": round(vol, 4)}


@router.get("/ordenes-salida/{oid}/empaque")
async def ver_empaque(oid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    bultos = (await db.execute(select(WMSEmpaqueOrden).where(WMSEmpaqueOrden.orden_id == oid)
                               .order_by(WMSEmpaqueOrden.numero))).scalars().all()
    return {"bultos": [_bulto_dict(b, len(bultos)) for b in bultos],
            "peso_total_kg": round(sum(b.peso_kg or 0 for b in bultos), 3),
            "volumen_total_m3": round(sum(cub.volumen_m3(b.largo_cm, b.ancho_cm, b.alto_cm) or 0 for b in bultos), 4)}
