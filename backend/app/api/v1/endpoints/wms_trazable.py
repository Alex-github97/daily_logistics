"""
WMS trazable: depositantes (3PL), estibas (LPN), tareas de ubicación, kárdex
con saldo y recorrido de un lote de punta a punta (para un retiro de mercado).
Prefijo: /wms
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_inventario as inv
from app.core import wms_operacion as op
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSCliente, WMSContenedor, WMSDepositante, WMSDespacho, WMSEventoTrazabilidad,
    WMSInventarioUbicacion, WMSLote, WMSMovimientoInventario, WMSOrdenCompra, WMSOrdenSalida, WMSProducto,
    WMSProveedor, WMSRecepcion, WMSRecepcionDetalle, WMSTarea, WMSUbicacion, WMSZona,
)

router = APIRouter(prefix="/wms", tags=["wms-trazable"])


async def _nombres(db: AsyncSession, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: f"{u.nombre} {u.apellido}".strip()
            for u in (await db.execute(select(Usuario).where(Usuario.id.in_(ids)))).scalars()}


async def _codigos(db: AsyncSession, Modelo, campo, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(Modelo.id, campo).where(Modelo.id.in_(ids)))).all())


def _f(v):
    return float(v) if v is not None else None


async def _mover(db, **kw):
    try:
        return await inv.mover(db, **kw)
    except inv.StockInsuficiente as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


async def _ubicacion(db: AsyncSession, ubicacion_id: Optional[int], codigo: Optional[str]) -> WMSUbicacion:
    if ubicacion_id:
        u = await db.get(WMSUbicacion, ubicacion_id)
    elif codigo:
        u = (await db.execute(select(WMSUbicacion).where(func.upper(WMSUbicacion.codigo) == codigo.strip().upper())
                              )).scalar_one_or_none()
    else:
        raise HTTPException(422, "Indique la ubicación (escanee su código).")
    if u is None or u.activo is False:
        raise HTTPException(404, "La ubicación no existe o está inactiva.")
    return u


# ── Depositantes ─────────────────────────────────────────────────────────────

class DepositanteIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=150)
    nit: Optional[str] = None
    contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    propio: bool = False
    tercero_id: Optional[int] = None
    notas: Optional[str] = None
    activo: bool = True


def _dep_dict(d: WMSDepositante, resumen: dict) -> dict:
    r = resumen.get(d.id, {})
    return {"id": d.id, "codigo": d.codigo, "nombre": d.nombre, "nit": d.nit, "contacto": d.contacto,
            "email": d.email, "telefono": d.telefono, "propio": d.propio, "tercero_id": d.tercero_id,
            "notas": d.notas, "activo": d.activo, "productos": r.get("productos", 0),
            "unidades": r.get("unidades", 0.0), "ubicaciones": r.get("ubicaciones", 0),
            "valor": r.get("valor", 0.0)}


async def _resumen_depositantes(db: AsyncSession) -> dict:
    productos = dict((await db.execute(select(WMSProducto.depositante_id, func.count())
                                       .group_by(WMSProducto.depositante_id))).all())
    total = WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada \
        + WMSInventarioUbicacion.cantidad_bloqueada
    filas = (await db.execute(
        select(WMSProducto.depositante_id, func.sum(total), func.count(func.distinct(WMSInventarioUbicacion.ubicacion_id)),
               func.sum(total * WMSProducto.costo_promedio))
        .join(WMSProducto, WMSProducto.id == WMSInventarioUbicacion.producto_id)
        .where(total > 0).group_by(WMSProducto.depositante_id))).all()
    out = {k: {"productos": v} for k, v in productos.items()}
    for dep, unidades, ubic, valor in filas:
        out.setdefault(dep, {}).update(unidades=float(unidades or 0), ubicaciones=ubic, valor=float(valor or 0))
    return out


@router.get("/depositantes")
async def listar_depositantes(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    resumen = await _resumen_depositantes(db)
    filas = (await db.execute(select(WMSDepositante).order_by(WMSDepositante.propio.desc(), WMSDepositante.nombre))).scalars()
    return [_dep_dict(d, resumen) for d in filas]


@router.post("/depositantes", status_code=201)
async def crear_depositante(data: DepositanteIn, db: AsyncSession = Depends(get_db),
                            _: Usuario = Depends(require_supervisor)):
    if (await db.execute(select(WMSDepositante.id).where(func.upper(WMSDepositante.codigo) == data.codigo.upper()))).first():
        raise HTTPException(409, "Ya existe un depositante con ese código.")
    if data.propio and (await db.execute(select(WMSDepositante.id).where(WMSDepositante.propio.is_(True)))).first():
        raise HTTPException(409, "Ya hay un depositante marcado como mercancía propia.")
    d = WMSDepositante(**data.model_dump())
    db.add(d)
    await db.flush()
    return _dep_dict(d, {})


@router.put("/depositantes/{did}")
async def editar_depositante(did: int, data: DepositanteIn, db: AsyncSession = Depends(get_db),
                             _: Usuario = Depends(require_supervisor)):
    d = await db.get(WMSDepositante, did)
    if d is None:
        raise HTTPException(404, "Depositante no encontrado.")
    if data.propio and not d.propio and (await db.execute(select(WMSDepositante.id).where(
            WMSDepositante.propio.is_(True), WMSDepositante.id != did))).first():
        raise HTTPException(409, "Ya hay un depositante marcado como mercancía propia.")
    if not data.activo and d.activo:
        resumen = await _resumen_depositantes(db)
        if resumen.get(did, {}).get("unidades", 0) > 0:
            raise HTTPException(409, "El depositante tiene mercancía en bodega: no se puede inactivar.")
    for k, v in data.model_dump().items():
        setattr(d, k, v)
    return _dep_dict(d, await _resumen_depositantes(db))


# ── Estibas (LPN) ────────────────────────────────────────────────────────────

class ContenedorIn(BaseModel):
    almacen_id: int
    ubicacion_id: Optional[int] = None
    ubicacion_codigo: Optional[str] = None
    tipo: str = Field(default="ESTIBA", pattern="^(ESTIBA|CAJA|CANASTA|CONTENEDOR)$")
    depositante_id: Optional[int] = None
    notas: Optional[str] = None


class MoverContenedorIn(BaseModel):
    ubicacion_id: Optional[int] = None
    ubicacion_codigo: Optional[str] = None


class AgregarIn(BaseModel):
    producto_id: int
    lote_id: Optional[int] = None
    cantidad: float = Field(gt=0)


async def _cont_dict(db: AsyncSession, c: WMSContenedor, con_contenido: bool = False) -> dict:
    ub = await db.get(WMSUbicacion, c.ubicacion_id) if c.ubicacion_id else None
    dep = await db.get(WMSDepositante, c.depositante_id) if c.depositante_id else None
    alm = await db.get(WMSAlmacen, c.almacen_id)
    filas = await op.contenido(db, c.id)
    out = {"id": c.id, "codigo": c.codigo, "tipo": c.tipo, "estado": c.estado, "almacen_id": c.almacen_id,
           "almacen": alm.nombre if alm else None, "ubicacion_id": c.ubicacion_id,
           "ubicacion": ub.codigo if ub else None, "depositante_id": c.depositante_id,
           "depositante": dep.nombre if dep else None, "documento_tipo": c.documento_tipo,
           "documento_id": c.documento_id, "largo_cm": c.largo_cm, "ancho_cm": c.ancho_cm, "alto_cm": c.alto_cm,
           "peso_kg": c.peso_kg, "notas": c.notas, "creado": c.created_at.isoformat() if c.created_at else None,
           "lineas": len(filas), "unidades": sum(inv.total_fila(f) for f in filas)}
    if con_contenido:
        prods = await _codigos(db, WMSProducto, WMSProducto.nombre, [f.producto_id for f in filas])
        skus = await _codigos(db, WMSProducto, WMSProducto.sku, [f.producto_id for f in filas])
        lotes = await _codigos(db, WMSLote, WMSLote.numero_lote, [f.lote_id for f in filas])
        out["contenido"] = [{"producto_id": f.producto_id, "sku": skus.get(f.producto_id),
                             "producto": prods.get(f.producto_id), "lote_id": f.lote_id,
                             "lote": lotes.get(f.lote_id), "disponible": f.cantidad_disponible,
                             "reservado": f.cantidad_reservada, "bloqueado": f.cantidad_bloqueada} for f in filas]
    return out


@router.get("/contenedores")
async def listar_contenedores(almacen_id: Optional[int] = None, estado: Optional[str] = None,
                              q: Optional[str] = None, limite: int = Query(200, le=1000),
                              db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = select(WMSContenedor)
    if almacen_id:
        c = c.where(WMSContenedor.almacen_id == almacen_id)
    if estado:
        c = c.where(WMSContenedor.estado.in_(estado.split(",")))
    else:
        c = c.where(WMSContenedor.estado.notin_(("VACIO", "ANULADO", "DESPACHADO")))
    if q:
        c = c.where(WMSContenedor.codigo.ilike(f"%{q.strip()}%"))
    filas = (await db.execute(c.order_by(WMSContenedor.id.desc()).limit(limite))).scalars().all()
    return [await _cont_dict(db, x) for x in filas]


@router.post("/contenedores", status_code=201)
async def crear_contenedor(data: ContenedorIn, db: AsyncSession = Depends(get_db),
                           yo: Usuario = Depends(get_current_user)):
    ub = await _ubicacion(db, data.ubicacion_id, data.ubicacion_codigo) \
        if (data.ubicacion_id or data.ubicacion_codigo) else None
    if ub and await inv.almacen_de(db, ub.id) != data.almacen_id:
        raise HTTPException(422, "La ubicación no es de ese almacén.")
    c = await op.crear_contenedor(db, almacen_id=data.almacen_id, ubicacion_id=ub.id if ub else None,
                                  depositante_id=data.depositante_id, tipo=data.tipo, usuario_id=yo.id,
                                  notas=data.notas)
    return await _cont_dict(db, c, True)


async def _contenedor(db: AsyncSession, cid: int) -> WMSContenedor:
    c = await db.get(WMSContenedor, cid)
    if c is None:
        raise HTTPException(404, "Estiba no encontrada.")
    return c


@router.get("/contenedores/codigo/{codigo}")
async def contenedor_por_codigo(codigo: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = (await db.execute(select(WMSContenedor).where(func.upper(WMSContenedor.codigo) == codigo.strip().upper())
                          )).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, f"No hay estiba con código {codigo}.")
    return await _cont_dict(db, c, True)


@router.get("/contenedores/{cid}")
async def ver_contenedor(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await _contenedor(db, cid)
    out = await _cont_dict(db, c, True)
    movs = (await db.execute(select(WMSMovimientoInventario).where(or_(
        WMSMovimientoInventario.contenedor_id == cid, WMSMovimientoInventario.contenedor_destino_id == cid))
        .order_by(WMSMovimientoInventario.id))).scalars().all()
    out["historia"] = await _movimientos_dict(db, movs)
    return out


@router.post("/contenedores/{cid}/mover")
async def mover_contenedor(cid: int, data: MoverContenedorIn, db: AsyncSession = Depends(get_db),
                           yo: Usuario = Depends(get_current_user)):
    c = await _contenedor(db, cid)
    if c.estado in ("DESPACHADO", "ANULADO", "VACIO"):
        raise HTTPException(409, f"La estiba está {c.estado.lower()}: no se puede mover.")
    ub = await _ubicacion(db, data.ubicacion_id, data.ubicacion_codigo)
    if await inv.almacen_de(db, ub.id) != c.almacen_id:
        raise HTTPException(422, "La estiba solo se mueve dentro de su almacén (entre almacenes es un traslado).")
    n = await op.mover_contenedor(db, c, ub.id, usuario_id=yo.id)
    return {**await _cont_dict(db, c, True), "lineas_movidas": n}


@router.post("/contenedores/{cid}/agregar")
async def agregar_a_contenedor(cid: int, data: AgregarIn, db: AsyncSession = Depends(get_db),
                               yo: Usuario = Depends(get_current_user)):
    """Arma la estiba con mercancía suelta de su misma ubicación."""
    c = await _contenedor(db, cid)
    if c.estado not in ("ABIERTO", "VACIO") or not c.ubicacion_id:
        raise HTTPException(409, "Solo se agrega a una estiba abierta y ubicada.")
    prod = await db.get(WMSProducto, data.producto_id)
    if prod and c.depositante_id and prod.depositante_id != c.depositante_id:
        raise HTTPException(422, "Ese producto es de otro depositante que la estiba.")
    await _mover(db, tipo="CONSOLIDACION", producto_id=data.producto_id, cantidad=data.cantidad, lote_id=data.lote_id,
                 origen=c.ubicacion_id, destino=c.ubicacion_id, contenedor_origen=None, contenedor_destino=c.id,
                 documento_tipo="LPN", documento_id=c.id, referencia=c.codigo, usuario_id=yo.id,
                 notas="Armado de estiba")
    if c.depositante_id is None and prod:
        c.depositante_id = prod.depositante_id
    return await _cont_dict(db, c, True)


@router.post("/contenedores/{cid}/cerrar")
async def cerrar_contenedor(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await _contenedor(db, cid)
    if c.estado != "ABIERTO":
        raise HTTPException(409, f"La estiba está {c.estado.lower()}.")
    if not await op.contenido(db, cid):
        raise HTTPException(409, "La estiba está vacía.")
    c.estado = "CERRADO"
    return await _cont_dict(db, c, True)


# ── Tareas ───────────────────────────────────────────────────────────────────

class CompletarTareaIn(BaseModel):
    ubicacion_id: Optional[int] = None
    ubicacion_codigo: Optional[str] = None
    motivo_desvio: Optional[str] = Field(default=None, max_length=200)


class CancelarIn(BaseModel):
    motivo: str = Field(min_length=3)


async def _tareas_dict(db: AsyncSession, tareas: List[WMSTarea]) -> list:
    ubic = await _codigos(db, WMSUbicacion, WMSUbicacion.codigo,
                          [x for t in tareas for x in (t.ubicacion_origen_id, t.ubicacion_sugerida_id, t.ubicacion_destino_id)])
    prods = await _codigos(db, WMSProducto, WMSProducto.nombre, [t.producto_id for t in tareas])
    skus = await _codigos(db, WMSProducto, WMSProducto.sku, [t.producto_id for t in tareas])
    lotes = await _codigos(db, WMSLote, WMSLote.numero_lote, [t.lote_id for t in tareas])
    lpns = await _codigos(db, WMSContenedor, WMSContenedor.codigo, [t.contenedor_id for t in tareas])
    gente = await _nombres(db, [t.operario_id for t in tareas])

    def minutos(a, b):
        return round((b - a).total_seconds() / 60, 1) if a and b else None
    return [{"id": t.id, "tipo": t.tipo, "estado": t.estado, "prioridad": t.prioridad, "almacen_id": t.almacen_id,
             "producto_id": t.producto_id, "sku": skus.get(t.producto_id), "producto": prods.get(t.producto_id),
             "lote": lotes.get(t.lote_id), "contenedor_id": t.contenedor_id, "contenedor": lpns.get(t.contenedor_id),
             "cantidad": t.cantidad, "origen": ubic.get(t.ubicacion_origen_id),
             "sugerida_id": t.ubicacion_sugerida_id, "sugerida": ubic.get(t.ubicacion_sugerida_id),
             "razon_sugerencia": t.razon_sugerencia, "destino": ubic.get(t.ubicacion_destino_id),
             "motivo_desvio": t.motivo_desvio, "documento_tipo": t.documento_tipo, "documento_id": t.documento_id,
             "operario": gente.get(t.operario_id), "creada": t.created_at.isoformat() if t.created_at else None,
             "iniciada": t.iniciada_en.isoformat() if t.iniciada_en else None,
             "terminada": t.terminada_en.isoformat() if t.terminada_en else None,
             "espera_min": minutos(t.created_at, t.iniciada_en), "ejecucion_min": minutos(t.iniciada_en, t.terminada_en),
             "notas": t.notas} for t in tareas]


@router.get("/tareas")
async def listar_tareas(estado: Optional[str] = None, tipo: Optional[str] = None, almacen_id: Optional[int] = None,
                        limite: int = Query(200, le=1000), db: AsyncSession = Depends(get_db),
                        _=Depends(get_current_user)):
    q = select(WMSTarea)
    if estado:
        q = q.where(WMSTarea.estado.in_(estado.split(",")))
    if tipo:
        q = q.where(WMSTarea.tipo == tipo)
    if almacen_id:
        q = q.where(WMSTarea.almacen_id == almacen_id)
    tareas = (await db.execute(q.order_by(WMSTarea.prioridad, WMSTarea.id.desc()).limit(limite))).scalars().all()
    return await _tareas_dict(db, tareas)


async def _tarea(db: AsyncSession, tid: int) -> WMSTarea:
    t = (await db.execute(select(WMSTarea).where(WMSTarea.id == tid).with_for_update())).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Tarea no encontrada.")
    return t


@router.post("/tareas/{tid}/iniciar")
async def iniciar_tarea(tid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    t = await _tarea(db, tid)
    if t.estado != "PENDIENTE":
        raise HTTPException(409, f"La tarea está {t.estado.lower()}.")
    t.estado, t.operario_id, t.iniciada_en = "EN_CURSO", yo.id, op.ahora()
    t.asignada_en = t.asignada_en or t.iniciada_en
    return (await _tareas_dict(db, [t]))[0]


@router.post("/tareas/{tid}/completar")
async def completar_tarea(tid: int, data: CompletarTareaIn, db: AsyncSession = Depends(get_db),
                          yo: Usuario = Depends(get_current_user)):
    t = await _tarea(db, tid)
    if t.estado not in ("PENDIENTE", "EN_CURSO"):
        raise HTTPException(409, f"La tarea está {t.estado.lower()}.")
    ub = await _ubicacion(db, data.ubicacion_id, data.ubicacion_codigo)
    zona = await db.get(WMSZona, ub.zona_id)
    if zona.almacen_id != t.almacen_id:
        raise HTTPException(422, "Esa ubicación es de otro almacén.")
    if zona.tipo in ("RECEPCION", "DESPACHO"):
        raise HTTPException(422, f"No se ubica mercancía en una zona de {zona.tipo.lower()}.")
    if ub.id == t.ubicacion_origen_id:
        raise HTTPException(422, "El destino es la misma ubicación de origen.")
    # Si no va a donde se sugirió, se pide el porqué: es lo que permite
    # corregir las reglas de ubicación con datos de la operación.
    if t.ubicacion_sugerida_id and ub.id != t.ubicacion_sugerida_id and not (data.motivo_desvio or "").strip():
        raise HTTPException(422, "La ubicación no es la sugerida: indique el motivo del cambio.")
    ahora = op.ahora()
    if t.iniciada_en is None:
        t.iniciada_en, t.operario_id = ahora, yo.id
    t.operario_id = t.operario_id or yo.id
    if t.contenedor_id:
        c = await db.get(WMSContenedor, t.contenedor_id)
        await op.mover_contenedor(db, c, ub.id, usuario_id=yo.id, tarea_id=t.id, tipo="UBICACION",
                                  documento_tipo=t.documento_tipo, documento_id=t.documento_id)
    else:
        await _mover(db, tipo="UBICACION", producto_id=t.producto_id, cantidad=t.cantidad, lote_id=t.lote_id,
                     origen=t.ubicacion_origen_id, destino=ub.id, usuario_id=yo.id, tarea_id=t.id,
                     documento_tipo=t.documento_tipo, documento_id=t.documento_id)
    t.ubicacion_destino_id = ub.id
    t.motivo_desvio = (data.motivo_desvio or "").strip() or None
    t.estado, t.terminada_en = "COMPLETADA", ahora
    return (await _tareas_dict(db, [t]))[0]


@router.post("/tareas/{tid}/cancelar")
async def cancelar_tarea(tid: int, data: CancelarIn, db: AsyncSession = Depends(get_db),
                         _: Usuario = Depends(require_supervisor)):
    t = await _tarea(db, tid)
    if t.estado in ("COMPLETADA", "CANCELADA"):
        raise HTTPException(409, f"La tarea ya está {t.estado.lower()}.")
    # La mercancía se queda donde está (en la zona de recepción); cancelar no la mueve.
    t.estado, t.notas, t.terminada_en = "CANCELADA", data.motivo, op.ahora()
    return (await _tareas_dict(db, [t]))[0]


@router.post("/tareas/{tid}/resugerir")
async def resugerir(tid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    t = await _tarea(db, tid)
    if t.estado not in ("PENDIENTE", "EN_CURSO"):
        raise HTTPException(409, "Solo se resugiere una tarea abierta.")
    t.ubicacion_sugerida_id, t.razon_sugerencia = await op.sugerir_ubicacion(db, t.almacen_id, t.producto_id, t.lote_id,
                                                                             t.cantidad or 0)
    return (await _tareas_dict(db, [t]))[0]


# ── Kárdex ───────────────────────────────────────────────────────────────────

M = WMSMovimientoInventario


async def _movimientos_dict(db: AsyncSession, movs, signos: Optional[list] = None, saldo0: float = 0) -> list:
    ubic = await _codigos(db, WMSUbicacion, WMSUbicacion.codigo,
                          [x for m in movs for x in (m.ubicacion_origen_id, m.ubicacion_destino_id)])
    prods = await _codigos(db, WMSProducto, WMSProducto.nombre, [m.producto_id for m in movs])
    skus = await _codigos(db, WMSProducto, WMSProducto.sku, [m.producto_id for m in movs])
    lotes = await _codigos(db, WMSLote, WMSLote.numero_lote, [m.lote_id for m in movs])
    lpns = await _codigos(db, WMSContenedor, WMSContenedor.codigo,
                          [x for m in movs for x in (m.contenedor_id, m.contenedor_destino_id)])
    gente = await _nombres(db, [m.usuario_id for m in movs])
    saldo, out = saldo0, []
    for i, m in enumerate(movs):
        fila = {"id": m.id, "fecha": m.created_at.isoformat() if m.created_at else None, "tipo": m.tipo,
                "producto_id": m.producto_id, "sku": skus.get(m.producto_id), "producto": prods.get(m.producto_id),
                "lote": lotes.get(m.lote_id), "cantidad": m.cantidad,
                "origen": ubic.get(m.ubicacion_origen_id), "destino": ubic.get(m.ubicacion_destino_id),
                "estado_origen": m.estado_origen, "estado_destino": m.estado_destino,
                "contenedor": lpns.get(m.contenedor_id), "contenedor_destino": lpns.get(m.contenedor_destino_id),
                "saldo_origen": m.saldo_origen, "saldo_destino": m.saldo_destino,
                "documento_tipo": m.documento_tipo, "documento_id": m.documento_id,
                "referencia": m.referencia_documento, "tarea_id": m.tarea_id,
                "costo_unitario": _f(m.costo_unitario), "usuario": gente.get(m.usuario_id), "notas": m.notas}
        if signos is not None:
            saldo += signos[i] * m.cantidad
            fila["efecto"] = signos[i] * m.cantidad
            fila["saldo"] = round(saldo, 6)
        out.append(fila)
    return out


def _signo(ubicacion_id, contenedor_id):
    """Cuánto suma cada movimiento al saldo del alcance consultado."""
    if ubicacion_id:
        return (case((M.ubicacion_destino_id == ubicacion_id, 1), else_=0)
                - case((M.ubicacion_origen_id == ubicacion_id, 1), else_=0))
    if contenedor_id:
        return (case((and_(M.ubicacion_destino_id.isnot(None), M.contenedor_destino_id == contenedor_id), 1), else_=0)
                - case((and_(M.ubicacion_origen_id.isnot(None), M.contenedor_id == contenedor_id), 1), else_=0))
    # Producto, lote, depositante o almacén: solo entradas y salidas; los
    # traslados y cambios de estado no cambian lo que hay.
    return (case((M.ubicacion_origen_id.is_(None), 1), else_=0)
            - case((M.ubicacion_destino_id.is_(None), 1), else_=0))


@router.get("/kardex")
async def kardex(producto_id: Optional[int] = None, lote_id: Optional[int] = None,
                 ubicacion_id: Optional[int] = None, contenedor_id: Optional[int] = None,
                 depositante_id: Optional[int] = None, almacen_id: Optional[int] = None,
                 desde: Optional[date] = None, hasta: Optional[date] = None,
                 incluir_estados: bool = False, limite: int = Query(3000, le=10000),
                 db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Kárdex con saldo acumulado. El saldo es físico (disponible + reservado +
    bloqueado). Al final compara el saldo del kárdex contra la existencia actual:
    si no cuadran, alguien movió inventario sin dejar rastro."""
    if not any((producto_id, lote_id, ubicacion_id, contenedor_id, depositante_id, almacen_id)):
        raise HTTPException(422, "Filtre por producto, lote, ubicación, estiba, depositante o almacén.")
    filtros = []
    if producto_id:
        filtros.append(M.producto_id == producto_id)
    if lote_id:
        filtros.append(M.lote_id == lote_id)
    if ubicacion_id:
        filtros.append(or_(M.ubicacion_origen_id == ubicacion_id, M.ubicacion_destino_id == ubicacion_id))
    if contenedor_id:
        filtros.append(or_(M.contenedor_id == contenedor_id, M.contenedor_destino_id == contenedor_id))
    if depositante_id:
        filtros.append(M.depositante_id == depositante_id)
    if almacen_id:
        filtros.append(M.almacen_id == almacen_id)
    signo = _signo(ubicacion_id, contenedor_id)
    ini = datetime.combine(desde, time.min, timezone.utc) + timedelta(hours=5) if desde else None
    fin = datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc) + timedelta(hours=5) if hasta else None
    saldo_inicial = 0.0
    if ini:
        saldo_inicial = float((await db.execute(select(func.coalesce(func.sum(signo * M.cantidad), 0))
                                                .where(*filtros, M.created_at < ini))).scalar() or 0)
    rango = [*filtros, *([M.created_at >= ini] if ini else []), *([M.created_at < fin] if fin else [])]
    if not incluir_estados:
        # Reservar, liberar y bloquear no mueven mercancía: se ocultan salvo que se pidan.
        rango.append(or_(M.ubicacion_origen_id.is_(None), M.ubicacion_destino_id.is_(None),
                         M.ubicacion_origen_id != M.ubicacion_destino_id,
                         func.coalesce(M.contenedor_id, 0) != func.coalesce(M.contenedor_destino_id, 0)))
    total = (await db.execute(select(func.count()).select_from(M).where(*rango))).scalar()
    filas = (await db.execute(select(M, signo.label("s")).where(*rango).order_by(M.created_at, M.id).limit(limite))).all()
    movs = [m for m, _s in filas]
    detalle = await _movimientos_dict(db, movs, [s for _m, s in filas], saldo_inicial)
    saldo_final = detalle[-1]["saldo"] if detalle else saldo_inicial

    # Conciliación contra la existencia actual (solo si el kárdex llega a hoy).
    existencia = None
    if not hasta or hasta >= date.today():
        q = select(func.coalesce(func.sum(WMSInventarioUbicacion.cantidad_disponible
                                          + WMSInventarioUbicacion.cantidad_reservada
                                          + WMSInventarioUbicacion.cantidad_bloqueada), 0))
        if depositante_id or almacen_id:
            q = q.join(WMSProducto, WMSProducto.id == WMSInventarioUbicacion.producto_id)
        if almacen_id:
            q = q.join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id) \
                 .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(WMSZona.almacen_id == almacen_id)
        if producto_id:
            q = q.where(WMSInventarioUbicacion.producto_id == producto_id)
        if lote_id:
            q = q.where(WMSInventarioUbicacion.lote_id == lote_id)
        if ubicacion_id:
            q = q.where(WMSInventarioUbicacion.ubicacion_id == ubicacion_id)
        if contenedor_id:
            q = q.where(WMSInventarioUbicacion.contenedor_id == contenedor_id)
        if depositante_id:
            q = q.where(WMSProducto.depositante_id == depositante_id)
        existencia = float((await db.execute(q)).scalar() or 0)
    completo = total <= limite
    return {"saldo_inicial": saldo_inicial, "saldo_final": saldo_final, "movimientos": detalle,
            "total_movimientos": total, "completo": completo,
            "existencia_actual": existencia,
            "diferencia": round(existencia - saldo_final, 6) if existencia is not None and completo and not desde else None}


@router.get("/trazabilidad/documento")
async def trazabilidad_documento(tipo: str, id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    movs = (await db.execute(select(M).where(M.documento_tipo == tipo.upper(), M.documento_id == id)
                             .order_by(M.id))).scalars().all()
    return await _movimientos_dict(db, movs)


# ── Recorrido de un lote (recall) ────────────────────────────────────────────

@router.get("/trazabilidad/lote/{lote_id}/recorrido")
async def recorrido_lote(lote_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """De dónde vino un lote, por dónde pasó, a quién se le entregó y dónde
    queda. Es lo que se necesita el día que hay que retirarlo del mercado."""
    lote = await db.get(WMSLote, lote_id)
    if lote is None:
        raise HTTPException(404, "Lote no encontrado.")
    prod = await db.get(WMSProducto, lote.producto_id)
    dep = await db.get(WMSDepositante, prod.depositante_id) if prod and prod.depositante_id else None

    # Origen: recepciones con su proveedor.
    origen = []
    for det, rec, oc, prov in (await db.execute(
            select(WMSRecepcionDetalle, WMSRecepcion, WMSOrdenCompra, WMSProveedor)
            .join(WMSRecepcion, WMSRecepcion.id == WMSRecepcionDetalle.recepcion_id)
            .outerjoin(WMSOrdenCompra, WMSOrdenCompra.id == WMSRecepcion.orden_compra_id)
            .outerjoin(WMSProveedor, WMSProveedor.id == WMSOrdenCompra.proveedor_id)
            .where(WMSRecepcionDetalle.lote_id == lote_id))).all():
        origen.append({"recepcion": rec.numero_recepcion, "recepcion_id": rec.id, "fecha": rec.fecha_recepcion.isoformat(),
                       "estado": rec.estado, "orden_compra": oc.numero_oc if oc else None,
                       "proveedor": prov.nombre if prov else (lote.proveedor_lote or None),
                       "cantidad": det.cantidad_recibida, "calidad": det.estado_calidad})

    # Destino: a quién salió. Despachos (con cliente) y ventas del POS.
    salidas = (await db.execute(select(M).where(M.lote_id == lote_id, M.ubicacion_destino_id.is_(None))
                                .order_by(M.created_at))).scalars().all()
    nums = {m.referencia_documento for m in salidas if m.tipo == "DESPACHO" and m.referencia_documento}
    ids = {m.documento_id for m in salidas if m.documento_tipo == "DESPACHO" and m.documento_id}
    desp = {}
    if nums or ids:
        for d, o, c in (await db.execute(
                select(WMSDespacho, WMSOrdenSalida, WMSCliente)
                .join(WMSOrdenSalida, WMSOrdenSalida.id == WMSDespacho.orden_id)
                .join(WMSCliente, WMSCliente.id == WMSOrdenSalida.cliente_id)
                .where(or_(WMSDespacho.id.in_(ids or {0}), WMSDespacho.numero_despacho.in_(nums or {""}))))).all():
            desp[d.id] = desp[d.numero_despacho] = (d, o, c)
    clientes: dict = {}
    destino = []
    for m in salidas:
        clave = m.documento_id if m.documento_tipo == "DESPACHO" else m.referencia_documento
        d_o_c = desp.get(clave) or desp.get(m.referencia_documento)
        if d_o_c:
            d, o, c = d_o_c
            quien, contacto, doc = c.nombre, " · ".join(x for x in (c.contacto, c.telefono, c.email) if x), d.numero_despacho
        elif m.documento_tipo == "POS_VENTA" or (m.notas or "").startswith("Venta POS"):
            quien, contacto, doc = "Venta de mostrador (POS)", None, m.referencia_documento
        else:
            quien, contacto, doc = {"CONTEO": "Faltante de conteo", "AJUSTE": "Ajuste de inventario"}.get(
                m.tipo, m.tipo.title()), None, m.referencia_documento
        destino.append({"fecha": m.created_at.isoformat(), "tipo": m.tipo, "a_quien": quien, "contacto": contacto,
                        "documento": doc, "cantidad": m.cantidad})
        k = (quien, contacto)
        clientes.setdefault(k, {"a_quien": quien, "contacto": contacto, "cantidad": 0.0, "documentos": set(),
                                "ultima": None})
        clientes[k]["cantidad"] += m.cantidad
        clientes[k]["documentos"].add(doc)
        clientes[k]["ultima"] = m.created_at.isoformat()

    # Dónde queda.
    queda = []
    for f, ub, cont in (await db.execute(
            select(WMSInventarioUbicacion, WMSUbicacion, WMSContenedor)
            .join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id)
            .outerjoin(WMSContenedor, WMSContenedor.id == WMSInventarioUbicacion.contenedor_id)
            .where(WMSInventarioUbicacion.lote_id == lote_id))).all():
        if inv.total_fila(f) > 0:
            queda.append({"ubicacion": ub.codigo, "contenedor": cont.codigo if cont else None,
                          "disponible": f.cantidad_disponible, "reservado": f.cantidad_reservada,
                          "bloqueado": f.cantidad_bloqueada})
    entradas = sum(o["cantidad"] for o in origen if o["calidad"] != "RECHAZADO")
    salido = sum(d["cantidad"] for d in destino)
    return {"lote": {"id": lote.id, "numero": lote.numero_lote, "vence": lote.fecha_vencimiento.isoformat()
                     if lote.fecha_vencimiento else None, "fabricado": lote.fecha_fabricacion.isoformat()
                     if lote.fecha_fabricacion else None, "activo": lote.activo},
            "producto": {"id": prod.id, "sku": prod.sku, "nombre": prod.nombre} if prod else None,
            "depositante": dep.nombre if dep else None,
            "origen": origen, "destino": destino,
            "clientes": [{**v, "documentos": sorted(x for x in v["documentos"] if x)} for v in clientes.values()],
            "queda": queda, "recibido": entradas, "salido": salido,
            "en_bodega": sum(q["disponible"] + q["reservado"] + q["bloqueado"] for q in queda)}


class RetirarLoteIn(BaseModel):
    motivo: str = Field(min_length=5)


@router.post("/trazabilidad/lote/{lote_id}/retener")
async def retener_lote(lote_id: int, data: RetirarLoteIn, db: AsyncSession = Depends(get_db),
                       yo: Usuario = Depends(require_supervisor)):
    """Retiene un lote: lo inactiva (ya no se alista ni se vende) y bloquea todo
    lo disponible en bodega. Lo reservado se informa: hay que sacarlo de las
    órdenes a mano."""
    lote = (await db.execute(select(WMSLote).where(WMSLote.id == lote_id).with_for_update())).scalar_one_or_none()
    if lote is None:
        raise HTTPException(404, "Lote no encontrado.")
    lote.activo = False
    bloqueado, reservado = 0.0, 0.0
    for f in (await db.execute(select(WMSInventarioUbicacion).where(
            WMSInventarioUbicacion.lote_id == lote_id).with_for_update())).scalars().all():
        if (f.cantidad_disponible or 0) > 0:
            q = f.cantidad_disponible
            await _mover(db, tipo="BLOQUEO", producto_id=f.producto_id, cantidad=q, lote_id=lote_id,
                         origen=f.ubicacion_id, destino=f.ubicacion_id, estado_origen="DISPONIBLE",
                         estado_destino="BLOQUEADO", contenedor_origen=f.contenedor_id, documento_tipo="RETENCION_LOTE",
                         documento_id=lote_id, usuario_id=yo.id, notas=data.motivo)
            bloqueado += q
        reservado += f.cantidad_reservada or 0
    db.add(WMSEventoTrazabilidad(tipo_evento="RETENCION_LOTE", entidad_tipo="LOTE", entidad_id=lote_id,
                                 descripcion=f"Lote {lote.numero_lote} retenido: {data.motivo}", usuario_id=yo.id,
                                 producto_id=lote.producto_id, lote_id=lote_id,
                                 datos_adicionales={"bloqueado": bloqueado, "reservado": reservado}))
    return {"lote": lote.numero_lote, "bloqueado": bloqueado, "reservado_en_ordenes": reservado}
