"""
WMS · Maquila (servicios de valor agregado): armar kits, reempacar, etiquetar
y desarmar. Todo movimiento pasa por `wms_inventario.mover`: los componentes
se reservan al iniciar, se consumen al terminar y el resultado entra con su
costo (componentes + mano de obra).
Prefijo: /wms
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import floor
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_inventario as inv
from app.core import wms_operacion as op
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSDepositante, WMSInventarioUbicacion, WMSMaquilaComponente, WMSMaquilaOrden, WMSMaquilaReceta, WMSOrdenSalida,
    WMSOrdenSalidaDetalle, WMSProducto, WMSUbicacion, WMSZona,
)

router = APIRouter(prefix="/wms/maquila", tags=["wms-maquila"])


async def _mover(db, **kw):
    try:
        return await inv.mover(db, **kw)
    except inv.StockInsuficiente as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Recetas ──────────────────────────────────────────────────────────────────

class ComponenteIn(BaseModel):
    producto_id: int
    cantidad: float = Field(gt=0)


class RecetaIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=150)
    tipo: Literal["KIT", "REEMPAQUE", "ETIQUETADO", "DESARME"] = "KIT"
    producto_resultado_id: int
    minutos_por_unidad: float = Field(default=0, ge=0)
    costo_mano_obra_unidad: float = Field(default=0, ge=0)
    instrucciones: Optional[str] = None
    activo: bool = True
    componentes: List[ComponenteIn]


async def _componentes(db, receta_id) -> List[WMSMaquilaComponente]:
    return (await db.execute(select(WMSMaquilaComponente).where(WMSMaquilaComponente.receta_id == receta_id))).scalars().all()


async def _receta_dict(db, r: WMSMaquilaReceta) -> dict:
    comps = await _componentes(db, r.id)
    prods = {p.id: p for p in (await db.execute(select(WMSProducto).where(
        WMSProducto.id.in_([c.producto_id for c in comps] + [r.producto_resultado_id])))).scalars()}
    res = prods.get(r.producto_resultado_id)
    costo_comp = sum(c.cantidad * float(prods[c.producto_id].costo_promedio or 0) for c in comps if c.producto_id in prods)
    return {"id": r.id, "codigo": r.codigo, "nombre": r.nombre, "tipo": r.tipo, "producto_resultado_id": r.producto_resultado_id,
            "resultado_sku": res.sku if res else None, "resultado": res.nombre if res else None,
            "minutos_por_unidad": r.minutos_por_unidad, "costo_mano_obra_unidad": r.costo_mano_obra_unidad,
            "instrucciones": r.instrucciones, "activo": r.activo,
            "componentes": [{"producto_id": c.producto_id, "sku": prods[c.producto_id].sku if c.producto_id in prods else None,
                             "nombre": prods[c.producto_id].nombre if c.producto_id in prods else None,
                             "cantidad": c.cantidad} for c in comps],
            "costo_estandar_unidad": round(costo_comp + r.costo_mano_obra_unidad, 4) if r.tipo != "DESARME" else None}


async def _validar_receta(db, data: RecetaIn):
    ids = [c.producto_id for c in data.componentes]
    if not ids:
        raise HTTPException(422, "La receta necesita al menos un componente.")
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Cada componente va una sola vez.")
    if data.producto_resultado_id in ids:
        raise HTTPException(422, "El resultado no puede ser componente de sí mismo.")
    # Una receta es de un solo dueño: no se arma un kit con mercancía de dos depositantes.
    await op.resolver_depositante(db, None, ids + [data.producto_resultado_id])


@router.get("/recetas")
async def listar_recetas(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return [await _receta_dict(db, r) for r in (await db.execute(select(WMSMaquilaReceta).order_by(WMSMaquilaReceta.codigo))).scalars()]


@router.post("/recetas", status_code=201)
async def crear_receta(data: RecetaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    await _validar_receta(db, data)
    if (await db.execute(select(WMSMaquilaReceta.id).where(WMSMaquilaReceta.codigo == data.codigo))).first():
        raise HTTPException(409, "Ya hay una receta con ese código.")
    r = WMSMaquilaReceta(**data.model_dump(exclude={"componentes"}))
    db.add(r)
    await db.flush()
    for c in data.componentes:
        db.add(WMSMaquilaComponente(receta_id=r.id, producto_id=c.producto_id, cantidad=c.cantidad))
    await db.flush()
    return await _receta_dict(db, r)


@router.put("/recetas/{rid}")
async def editar_receta(rid: int, data: RecetaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    r = await db.get(WMSMaquilaReceta, rid)
    if r is None:
        raise HTTPException(404, "Receta no encontrada.")
    await _validar_receta(db, data)
    abiertas = (await db.execute(select(WMSMaquilaOrden.id).where(WMSMaquilaOrden.receta_id == rid,
                                                                  WMSMaquilaOrden.estado == "EN_PROCESO"))).first()
    if abiertas:
        raise HTTPException(409, "Hay órdenes en proceso con esta receta: termínelas antes de cambiarla.")
    for k, v in data.model_dump(exclude={"componentes"}).items():
        setattr(r, k, v)
    for c in await _componentes(db, rid):
        await db.delete(c)
    await db.flush()
    for c in data.componentes:
        db.add(WMSMaquilaComponente(receta_id=rid, producto_id=c.producto_id, cantidad=c.cantidad))
    await db.flush()
    return await _receta_dict(db, r)


async def _disponible_alistable(db, almacen_id: int, producto_id: int) -> float:
    v = (await db.execute(select(func.coalesce(func.sum(WMSInventarioUbicacion.cantidad_disponible), 0))
                          .join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id)
                          .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
                          .where(WMSInventarioUbicacion.producto_id == producto_id, WMSZona.almacen_id == almacen_id,
                                 WMSZona.tipo.notin_(inv.ZONAS_NO_ALISTABLES)))).scalar()
    return float(v or 0)


def _consumos(r: WMSMaquilaReceta, comps, cantidad: float) -> List[tuple]:
    """(producto, cantidad) que se consumen para `cantidad` unidades."""
    if r.tipo == "DESARME":
        return [(r.producto_resultado_id, cantidad)]
    return [(c.producto_id, c.cantidad * cantidad) for c in comps]


@router.get("/recetas/{rid}/posible")
async def posible(rid: int, almacen_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Cuántas unidades se pueden hacer con lo disponible, cuántas pide la
    demanda pendiente y cuántas se sugiere hacer."""
    r = await db.get(WMSMaquilaReceta, rid)
    if r is None:
        raise HTTPException(404, "Receta no encontrada.")
    comps = await _componentes(db, rid)
    limites = []
    for pid, por_unidad in _consumos(r, comps, 1):
        disp = await _disponible_alistable(db, almacen_id, pid)
        limites.append({"producto_id": pid, "disponible": disp, "por_unidad": por_unidad,
                        "alcanza_para": floor(disp / por_unidad + 1e-9) if por_unidad else 0})
    maximo = min((x["alcanza_para"] for x in limites), default=0)
    sugerido = maximo
    demanda = stock = None
    if r.tipo != "DESARME":
        demanda = float((await db.execute(select(func.coalesce(func.sum(
            WMSOrdenSalidaDetalle.cantidad_solicitada - WMSOrdenSalidaDetalle.cantidad_preparada), 0))
            .join(WMSOrdenSalida, WMSOrdenSalida.id == WMSOrdenSalidaDetalle.orden_id)
            .where(WMSOrdenSalida.almacen_id == almacen_id, WMSOrdenSalida.deleted_at.is_(None),
                   WMSOrdenSalida.estado.in_(("PENDIENTE", "EN_PICKING")),
                   WMSOrdenSalidaDetalle.producto_id == r.producto_resultado_id))).scalar() or 0)
        stock = await _disponible_alistable(db, almacen_id, r.producto_resultado_id)
        sugerido = min(maximo, max(0, int(demanda - stock + 0.999)))
    cuello = min(limites, key=lambda x: x["alcanza_para"]) if limites else None
    return {"maximo": maximo, "limites": limites, "cuello_de_botella": cuello, "demanda_pendiente": demanda,
            "existencia_resultado": stock, "sugerido": sugerido}


# ── Órdenes ──────────────────────────────────────────────────────────────────

class OrdenIn(BaseModel):
    receta_id: int
    almacen_id: int
    cantidad: float = Field(gt=0)
    notas: Optional[str] = None


async def _orden_dict(db, o: WMSMaquilaOrden) -> dict:
    r = await db.get(WMSMaquilaReceta, o.receta_id)
    ub = await db.get(WMSUbicacion, o.ubicacion_destino_id) if o.ubicacion_destino_id else None
    return {"id": o.id, "numero": o.numero, "receta_id": o.receta_id, "receta": r.nombre if r else None, "tipo": r.tipo if r else None,
            "almacen_id": o.almacen_id, "depositante_id": o.depositante_id, "cantidad_plan": o.cantidad_plan,
            "cantidad_hecha": o.cantidad_hecha, "estado": o.estado, "reservas": o.reservas or [],
            "ubicacion_destino": ub.codigo if ub else None, "costo_unitario": o.costo_unitario,
            "minutos_estandar": round((r.minutos_por_unidad if r else 0) * (o.cantidad_hecha or o.cantidad_plan), 1),
            "minutos_reales": o.minutos_reales, "creada": o.created_at.isoformat() if o.created_at else None,
            "iniciada_en": o.iniciada_en.isoformat() if o.iniciada_en else None,
            "terminada_en": o.terminada_en.isoformat() if o.terminada_en else None, "notas": o.notas}


async def _orden(db, oid) -> WMSMaquilaOrden:
    o = (await db.execute(select(WMSMaquilaOrden).where(WMSMaquilaOrden.id == oid).with_for_update())).scalar_one_or_none()
    if o is None:
        raise HTTPException(404, "Orden de maquila no encontrada.")
    return o


@router.get("/ordenes")
async def listar_ordenes(almacen_id: Optional[int] = None, estado: Optional[str] = None, db: AsyncSession = Depends(get_db),
                         _=Depends(get_current_user)):
    q = select(WMSMaquilaOrden)
    if almacen_id:
        q = q.where(WMSMaquilaOrden.almacen_id == almacen_id)
    if estado:
        q = q.where(WMSMaquilaOrden.estado.in_(estado.split(",")))
    return [await _orden_dict(db, o) for o in (await db.execute(q.order_by(WMSMaquilaOrden.id.desc()).limit(300))).scalars()]


@router.post("/ordenes", status_code=201)
async def crear_orden(data: OrdenIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    r = await db.get(WMSMaquilaReceta, data.receta_id)
    if r is None or not r.activo:
        raise HTTPException(422, "La receta no existe o está inactiva.")
    res = await db.get(WMSProducto, r.producto_resultado_id)
    n = (await db.execute(select(func.count()).select_from(WMSMaquilaOrden))).scalar() + 1
    numero = f"MAQ-{date.today().strftime('%Y%m%d')}-{n:04d}"
    while (await db.execute(select(WMSMaquilaOrden.id).where(WMSMaquilaOrden.numero == numero))).first():
        n += 1
        numero = f"MAQ-{date.today().strftime('%Y%m%d')}-{n:04d}"
    o = WMSMaquilaOrden(numero=numero, receta_id=r.id, almacen_id=data.almacen_id, cantidad_plan=data.cantidad,
                        depositante_id=res.depositante_id if res else None, estado="PLANEADA", notas=data.notas)
    db.add(o)
    await db.flush()
    return await _orden_dict(db, o)


@router.post("/ordenes/{oid}/iniciar")
async def iniciar(oid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Reserva lo que la orden va a consumir (FEFO, zonas alistables). Si falta
    algo no reserva nada y dice qué falta."""
    o = await _orden(db, oid)
    if o.estado != "PLANEADA":
        raise HTTPException(409, f"La orden está {o.estado.lower()}.")
    r = await db.get(WMSMaquilaReceta, o.receta_id)
    comps = await _componentes(db, r.id)
    plan = []
    faltan = []
    for pid, necesita in _consumos(r, comps, o.cantidad_plan):
        asign = await inv.asignar_alistamiento(db, pid, o.almacen_id, necesita)
        tiene = sum(float(a.cantidad) for a in asign)
        if tiene + 1e-9 < necesita:
            p = await db.get(WMSProducto, pid)
            faltan.append(f"{p.sku if p else pid}: necesita {necesita:g}, hay {tiene:g}")
        plan.append((pid, asign))
    if faltan:
        raise HTTPException(409, "No alcanza para la orden: " + "; ".join(faltan) + ".")
    reservas = []
    for pid, asign in plan:
        for a in asign:
            await _mover(db, tipo="RESERVA", producto_id=pid, cantidad=a.cantidad, lote_id=a.lote_id, origen=a.ubicacion_id,
                         destino=a.ubicacion_id, estado_origen="DISPONIBLE", estado_destino="RESERVADO",
                         contenedor_origen=a.contenedor_id, documento_tipo="MAQUILA", documento_id=o.id,
                         referencia=o.numero, usuario_id=yo.id, notas="Reserva para maquila")
            reservas.append({"producto_id": pid, "ubicacion_id": a.ubicacion_id, "lote_id": a.lote_id,
                             "contenedor_id": a.contenedor_id, "cantidad": float(a.cantidad)})
    o.reservas, o.estado, o.iniciada_en, o.operario_id = reservas, "EN_PROCESO", datetime.now(timezone.utc), yo.id
    return await _orden_dict(db, o)


class TerminarIn(BaseModel):
    cantidad_hecha: float = Field(gt=0)
    ubicacion_codigo: Optional[str] = None
    ubicacion_id: Optional[int] = None


@router.post("/ordenes/{oid}/terminar")
async def terminar(oid: int, data: TerminarIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    o = await _orden(db, oid)
    if o.estado != "EN_PROCESO":
        raise HTTPException(409, f"La orden está {o.estado.lower()}.")
    if data.cantidad_hecha > o.cantidad_plan + 1e-9:
        raise HTTPException(422, f"Se planearon {o.cantidad_plan:g}; no se pueden reportar {data.cantidad_hecha:g}.")
    if data.ubicacion_id:
        destino = await db.get(WMSUbicacion, data.ubicacion_id)
    elif data.ubicacion_codigo:
        destino = (await db.execute(select(WMSUbicacion).where(
            func.upper(WMSUbicacion.codigo) == data.ubicacion_codigo.strip().upper()))).scalar_one_or_none()
    else:
        destino = None
    if destino is None:
        raise HTTPException(422, "Indique dónde queda lo producido (escanee la ubicación).")
    if await inv.almacen_de(db, destino.id) != o.almacen_id:
        raise HTTPException(422, "La ubicación de destino es de otro almacén.")
    r = await db.get(WMSMaquilaReceta, o.receta_id)
    comps = await _componentes(db, r.id)
    doc = dict(documento_tipo="MAQUILA", documento_id=o.id, referencia=o.numero, usuario_id=yo.id)
    # 1. Consumir lo usado, de lo reservado; liberar el resto.
    usar = {pid: q for pid, q in _consumos(r, comps, data.cantidad_hecha)}
    costo_consumido = 0.0
    for res in o.reservas or []:
        pid = res["producto_id"]
        tomar = min(res["cantidad"], usar.get(pid, 0))
        sobra = res["cantidad"] - tomar
        if tomar > 1e-9:
            prod = await db.get(WMSProducto, pid)
            costo_consumido += tomar * float(prod.costo_promedio or 0)
            await _mover(db, tipo="MAQUILA_CONSUMO", producto_id=pid, cantidad=tomar, lote_id=res["lote_id"],
                         origen=res["ubicacion_id"], estado_origen="RESERVADO", contenedor_origen=res["contenedor_id"],
                         notas="Consumo en maquila", **doc)
            usar[pid] -= tomar
        if sobra > 1e-9:
            await _mover(db, tipo="LIBERACION", producto_id=pid, cantidad=sobra, lote_id=res["lote_id"],
                         origen=res["ubicacion_id"], destino=res["ubicacion_id"], estado_origen="RESERVADO",
                         estado_destino="DISPONIBLE", contenedor_origen=res["contenedor_id"],
                         notas="Sobrante de la maquila", **doc)
    mano_obra = r.costo_mano_obra_unidad * data.cantidad_hecha
    # 2. Producir.
    if r.tipo == "DESARME":
        # El costo del kit más la mano de obra se reparte entre los componentes
        # según su costo vigente (o por partes iguales si no tienen costo).
        prods = {p.id: p for p in (await db.execute(select(WMSProducto).where(
            WMSProducto.id.in_([c.producto_id for c in comps])))).scalars()}
        pesos = {c.producto_id: c.cantidad * float(prods[c.producto_id].costo_promedio or 0) for c in comps}
        base = sum(pesos.values())
        total = costo_consumido + mano_obra
        for c in comps:
            q = c.cantidad * data.cantidad_hecha
            parte = (pesos[c.producto_id] / base) if base else 1 / len(comps)
            await _mover(db, tipo="MAQUILA_PRODUCCION", producto_id=c.producto_id, cantidad=q, destino=destino.id,
                         costo_unitario=round(total * parte / q, 4), notas="Producido por desarme", **doc)
        o.costo_unitario = round(total / data.cantidad_hecha, 4)
    else:
        unitario = round((costo_consumido + mano_obra) / data.cantidad_hecha, 4)
        await _mover(db, tipo="MAQUILA_PRODUCCION", producto_id=r.producto_resultado_id, cantidad=data.cantidad_hecha,
                     destino=destino.id, costo_unitario=unitario, notas=f"Producido por maquila ({r.tipo.lower()})", **doc)
        o.costo_unitario = unitario
    ahora = datetime.now(timezone.utc)
    o.cantidad_hecha, o.ubicacion_destino_id, o.estado, o.terminada_en = data.cantidad_hecha, destino.id, "TERMINADA", ahora
    if o.iniciada_en:
        o.minutos_reales = round((ahora - o.iniciada_en).total_seconds() / 60, 1)
    return await _orden_dict(db, o)


@router.post("/ordenes/{oid}/cancelar")
async def cancelar(oid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    o = await _orden(db, oid)
    if o.estado not in ("PLANEADA", "EN_PROCESO"):
        raise HTTPException(409, f"La orden está {o.estado.lower()}.")
    for res in o.reservas or []:
        await _mover(db, tipo="LIBERACION", producto_id=res["producto_id"], cantidad=res["cantidad"], lote_id=res["lote_id"],
                     origen=res["ubicacion_id"], destino=res["ubicacion_id"], estado_origen="RESERVADO",
                     estado_destino="DISPONIBLE", contenedor_origen=res["contenedor_id"], documento_tipo="MAQUILA",
                     documento_id=o.id, referencia=o.numero, usuario_id=yo.id, notas="Maquila cancelada")
    o.estado, o.reservas = "CANCELADA", []
    return await _orden_dict(db, o)


@router.get("/resumen")
async def resumen(desde: Optional[date] = None, hasta: Optional[date] = None, almacen_id: Optional[int] = None,
                  db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Lo hecho por depositante: base para facturar el servicio de maquila."""
    hasta = hasta or date.today()
    desde = desde or hasta.replace(day=1)
    ini = datetime.combine(desde, time.min, timezone.utc) + timedelta(hours=5)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc) + timedelta(hours=5)
    q = select(WMSMaquilaOrden, WMSMaquilaReceta).join(WMSMaquilaReceta, WMSMaquilaReceta.id == WMSMaquilaOrden.receta_id) \
        .where(WMSMaquilaOrden.estado == "TERMINADA", WMSMaquilaOrden.terminada_en >= ini, WMSMaquilaOrden.terminada_en < fin)
    if almacen_id:
        q = q.where(WMSMaquilaOrden.almacen_id == almacen_id)
    por: dict = {}
    for o, r in (await db.execute(q)).all():
        d = por.setdefault(o.depositante_id, {"depositante_id": o.depositante_id, "ordenes": 0, "unidades": 0.0,
                                              "minutos_estandar": 0.0, "minutos_reales": 0.0, "mano_obra": 0.0})
        d["ordenes"] += 1
        d["unidades"] += o.cantidad_hecha or 0
        d["minutos_estandar"] += r.minutos_por_unidad * (o.cantidad_hecha or 0)
        d["minutos_reales"] += o.minutos_reales or 0
        d["mano_obra"] += r.costo_mano_obra_unidad * (o.cantidad_hecha or 0)
    nombres = dict((await db.execute(select(WMSDepositante.id, WMSDepositante.nombre).where(
        WMSDepositante.id.in_([k for k in por if k] or [0])))).all())
    return [{**d, "depositante": nombres.get(d["depositante_id"], "Sin depositante"),
             "eficiencia_pct": round(d["minutos_estandar"] / d["minutos_reales"] * 100, 1) if d["minutos_reales"] else None}
            for d in por.values()]
