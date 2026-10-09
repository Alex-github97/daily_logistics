"""
TMS · Solicitudes de transporte y asignación de carga a vehículos. Prefijo: /tms

El WMS envía consolidados (con destino y modo de despacho) en solicitudes de
transporte. Aquí se arma la carga de cada vehículo:

- se abre un cargue (vehículo propio, o transportadora + placa si es tercerizado);
- se le asignan consolidados con clic o escaneando su etiqueta (radiofrecuencia
  o lector de código de barras), verificando peso y volumen contra la capacidad;
- al confirmar nacen los despachos del WMS (uno por orden, que sacan el
  inventario del staging) y el viaje del TMS con una parada por destino o por
  dirección de entrega. De ahí sigue el flujo normal del viaje (conductor,
  salida, entrega, POD) y los pedidos de marketplace reciben su guía.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import tms_capacidad
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.marketplace import MKPPedido
from app.infrastructure.models.tms import (
    EstadoParadaTMSEnum, EstadoViajeTMSEnum, TipoParadaTMSEnum, TipoServicioTMSEnum, TMSCargue, TMSParada,
    TMSSolicitudTransporte, TMSVehiculo, TMSViaje, TMSViajeDespacho,
)
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSConsolidado, WMSConsolidadoOrden, WMSOrdenSalida, WMSTransportadora,
)

router = APIRouter(prefix="/tms", tags=["tms-cargue"])

MODOS = {
    "PAQUETEO_URBANO_PROPIO": "Paqueteo urbano propio",
    "PAQUETEO_URBANO_TERCERO": "Paqueteo urbano tercerizado",
    "PAQUETEO_NACIONAL_TERCERO": "Paqueteo nacional tercerizado",
    "FLOTA_PROPIA": "Viaje con flota propia",
}
TERCERIZADOS = ("PAQUETEO_URBANO_TERCERO", "PAQUETEO_NACIONAL_TERCERO")
SERVICIO = {"PAQUETEO_URBANO_PROPIO": TipoServicioTMSEnum.ULTIMA_MILLA, "PAQUETEO_URBANO_TERCERO": TipoServicioTMSEnum.TERCERIZADO,
            "PAQUETEO_NACIONAL_TERCERO": TipoServicioTMSEnum.TERCERIZADO, "FLOTA_PROPIA": TipoServicioTMSEnum.DISTRIBUCION}
# Paqueteo: una parada por dirección de entrega; viaje: una por destino.
POR_DIRECCION = ("PAQUETEO_URBANO_PROPIO", "PAQUETEO_URBANO_TERCERO")


async def _numero(db, Modelo, col, prefijo) -> str:
    from app.api.v1.endpoints.wms import _next_numero
    return await _next_numero(db, Modelo, col, prefijo)


async def _cons_dict(db, cs):
    from app.api.v1.endpoints.wms_consolidacion import _cons_dict
    return await _cons_dict(db, cs)


# ═════════════════════════════════════════════════════════════════════════════
# Solicitudes
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/solicitudes-transporte")
async def solicitudes(estado: Optional[str] = None, almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
                      _=Depends(get_current_user)):
    q = select(TMSSolicitudTransporte)
    if estado:
        q = q.where(TMSSolicitudTransporte.estado.in_(estado.split(",")))
    if almacen_id:
        q = q.where(TMSSolicitudTransporte.almacen_id == almacen_id)
    ss = (await db.execute(q.order_by(TMSSolicitudTransporte.id.desc()).limit(300))).scalars().all()
    cuenta = defaultdict(lambda: defaultdict(int))
    for sid, est, n, peso, vol, bultos in (await db.execute(select(
            WMSConsolidado.solicitud_id, WMSConsolidado.estado, func.count(), func.sum(WMSConsolidado.peso_kg),
            func.sum(WMSConsolidado.volumen_m3), func.sum(WMSConsolidado.bultos)).where(
            WMSConsolidado.solicitud_id.in_([s.id for s in ss] or [0])).group_by(WMSConsolidado.solicitud_id, WMSConsolidado.estado))).all():
        c = cuenta[sid]
        c[est] += n
        c["total"] += n
        c["peso"] += float(peso or 0)
        c["vol"] += float(vol or 0)
        c["bultos"] += int(bultos or 0)
    trans = {t.id: t.nombre for t in (await db.execute(select(WMSTransportadora))).scalars()}
    alms = {a.id: a.nombre for a in (await db.execute(select(WMSAlmacen))).scalars()}
    return [{"id": s.id, "codigo": s.codigo, "almacen": alms.get(s.almacen_id), "almacen_id": s.almacen_id,
             "modo_despacho": s.modo_despacho, "modo_nombre": MODOS.get(s.modo_despacho), "transportadora": trans.get(s.transportadora_id),
             "estado": s.estado, "creada": s.created_at.isoformat() if s.created_at else None, "notas": s.notas,
             "consolidados": cuenta[s.id]["total"], "pendientes": cuenta[s.id]["SOLICITADO"], "en_cargue": cuenta[s.id]["EN_CARGUE"],
             "despachados": cuenta[s.id]["DESPACHADO"] + cuenta[s.id]["ENTREGADO"], "bultos": cuenta[s.id]["bultos"],
             "peso_kg": round(cuenta[s.id]["peso"], 2), "volumen_m3": round(cuenta[s.id]["vol"], 3)} for s in ss]


@router.get("/carga-pendiente")
async def carga_pendiente(almacen_id: Optional[int] = None, modo: Optional[str] = None, db: AsyncSession = Depends(get_db),
                          _=Depends(get_current_user)):
    """Consolidados con transporte solicitado que todavía no van en ningún vehículo."""
    q = select(WMSConsolidado).where(WMSConsolidado.estado == "SOLICITADO")
    if almacen_id:
        q = q.where(WMSConsolidado.almacen_id == almacen_id)
    if modo:
        q = q.where(WMSConsolidado.modo_despacho == modo)
    cs = (await db.execute(q.order_by(WMSConsolidado.destino, WMSConsolidado.id))).scalars().all()
    return await _cons_dict(db, cs)


async def _actualizar_solicitudes(db, ids) -> None:
    for sid in {i for i in ids if i}:
        s = await db.get(TMSSolicitudTransporte, sid)
        ests = (await db.execute(select(WMSConsolidado.estado).where(WMSConsolidado.solicitud_id == sid))).scalars().all()
        if not ests:
            s.estado = "CANCELADA"
        elif all(e in ("DESPACHADO", "ENTREGADO") for e in ests):
            s.estado = "ATENDIDA"
        elif any(e in ("EN_CARGUE", "DESPACHADO", "ENTREGADO") for e in ests):
            s.estado = "EN_CARGUE"
        else:
            s.estado = "PENDIENTE"


class DevolverIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=200)


@router.post("/carga-pendiente/{cid}/devolver")
async def devolver_al_wms(cid: int, d: DevolverIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """El TMS no lo puede atender (o hay que corregirlo): el consolidado vuelve
    al WMS cerrado y sin solicitud."""
    c = (await db.execute(select(WMSConsolidado).where(WMSConsolidado.id == cid).with_for_update())).scalar_one_or_none()
    if c is None or c.estado != "SOLICITADO":
        raise HTTPException(409, "Solo se devuelve un consolidado con transporte solicitado y sin cargue.")
    sid = c.solicitud_id
    c.estado, c.solicitud_id = "CERRADO", None
    c.notas = f"{c.notas or ''} [Devuelto por TMS: {d.motivo}]".strip()
    await db.flush()
    await _actualizar_solicitudes(db, [sid])
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════════════
# Cargues
# ═════════════════════════════════════════════════════════════════════════════
async def _cargue(db, cid: int, armando: bool = True) -> TMSCargue:
    k = (await db.execute(select(TMSCargue).where(TMSCargue.id == cid).with_for_update())).scalar_one_or_none()
    if k is None:
        raise HTTPException(404, "Cargue no encontrado.")
    if armando and k.estado != "ARMANDO":
        raise HTTPException(409, f"El cargue {k.codigo} ya está {k.estado.lower()}.")
    return k


async def _cargue_dict(db, k: TMSCargue) -> dict:
    cs = (await db.execute(select(WMSConsolidado).where(WMSConsolidado.cargue_id == k.id).order_by(WMSConsolidado.destino))).scalars().all()
    info = await _cons_dict(db, cs)
    peso = sum(c.peso_kg or 0 for c in cs)
    vol = sum(c.volumen_m3 or 0 for c in cs)
    sin_peso = any(c.peso_kg is None for c in cs)
    sin_vol = any(c.volumen_m3 is None for c in cs)
    veh = await db.get(TMSVehiculo, k.vehiculo_id) if k.vehiculo_id else None
    cap = await tms_capacidad.verificar(db, veh, peso or None, vol or None) if veh else None
    trans = await db.get(WMSTransportadora, k.transportadora_id) if k.transportadora_id else None
    destinos = OrderedDict()
    for c in info:
        destinos.setdefault(c["destino"], {"destino": c["destino"], "consolidados": 0, "pedidos": 0, "bultos": 0})
        d = destinos[c["destino"]]
        d["consolidados"] += 1
        d["pedidos"] += len(c["ordenes"])
        d["bultos"] += c["bultos"]
    viaje = await db.get(TMSViaje, k.viaje_id) if k.viaje_id else None
    return {"id": k.id, "codigo": k.codigo, "almacen_id": k.almacen_id, "modo_despacho": k.modo_despacho,
            "modo_nombre": MODOS.get(k.modo_despacho), "tercerizado": k.modo_despacho in TERCERIZADOS,
            "vehiculo_id": k.vehiculo_id, "vehiculo": f"{veh.placa}" if veh else None,
            "transportadora_id": k.transportadora_id, "transportadora": trans.nombre if trans else None,
            "placa_tercero": k.placa_tercero, "estado": k.estado, "notas": k.notas,
            "viaje_id": k.viaje_id, "viaje": viaje.codigo if viaje else None,
            "consolidados": info, "destinos": list(destinos.values()),
            "totales": {"consolidados": len(cs), "pedidos": sum(len(c["ordenes"]) for c in info), "bultos": sum(c.bultos for c in cs),
                        "peso_kg": round(peso, 2), "volumen_m3": round(vol, 3), "sin_peso": sin_peso, "sin_volumen": sin_vol},
            "capacidad": cap}


class CargueIn(BaseModel):
    almacen_id: int
    modo_despacho: str
    vehiculo_id: Optional[int] = None
    transportadora_id: Optional[int] = None
    placa_tercero: Optional[str] = Field(None, max_length=20)
    notas: Optional[str] = Field(None, max_length=500)


async def _validar_cargue(db, d: CargueIn) -> None:
    if d.modo_despacho not in MODOS:
        raise HTTPException(422, "Modo de despacho inválido.")
    if d.modo_despacho in TERCERIZADOS:
        if not d.transportadora_id or await db.get(WMSTransportadora, d.transportadora_id) is None:
            raise HTTPException(422, "Elija la transportadora que recoge la carga.")
    elif d.vehiculo_id:
        v = await db.get(TMSVehiculo, d.vehiculo_id)
        if v is None or v.deleted_at:
            raise HTTPException(404, "Vehículo no encontrado.")


@router.get("/cargues")
async def listar_cargues(estado: Optional[str] = "ARMANDO", db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(TMSCargue)
    if estado:
        q = q.where(TMSCargue.estado.in_(estado.split(",")))
    ks = (await db.execute(q.order_by(TMSCargue.id.desc()).limit(100))).scalars().all()
    return [await _cargue_dict(db, k) for k in ks]


@router.post("/cargues", status_code=201)
async def crear_cargue(d: CargueIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    await _validar_cargue(db, d)
    k = TMSCargue(codigo=await _numero(db, TMSCargue, TMSCargue.codigo, "CAR"), almacen_id=d.almacen_id, modo_despacho=d.modo_despacho,
                  vehiculo_id=d.vehiculo_id if d.modo_despacho not in TERCERIZADOS else None,
                  transportadora_id=d.transportadora_id if d.modo_despacho in TERCERIZADOS else None,
                  placa_tercero=(d.placa_tercero or "").upper() or None, estado="ARMANDO", creado_por_id=yo.id, notas=d.notas)
    db.add(k)
    await db.flush()
    return await _cargue_dict(db, k)


@router.get("/cargues/{cid}")
async def ver_cargue(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await _cargue_dict(db, await _cargue(db, cid, armando=False))


@router.put("/cargues/{cid}")
async def editar_cargue(cid: int, d: CargueIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    k = await _cargue(db, cid)
    await _validar_cargue(db, d)
    if d.modo_despacho != k.modo_despacho:
        n = (await db.execute(select(func.count()).where(WMSConsolidado.cargue_id == k.id))).scalar()
        if n:
            raise HTTPException(409, "El cargue ya tiene consolidados de otro modo de despacho: quítelos primero.")
        k.modo_despacho = d.modo_despacho
    k.vehiculo_id = d.vehiculo_id if k.modo_despacho not in TERCERIZADOS else None
    k.transportadora_id = d.transportadora_id if k.modo_despacho in TERCERIZADOS else None
    k.placa_tercero = (d.placa_tercero or "").upper() or None
    k.notas = d.notas
    await db.flush()
    r = await _cargue_dict(db, k)
    if r["capacidad"] and not r["capacidad"]["ok"]:
        raise HTTPException(409, f"La carga ya armada no cabe en {r['vehiculo']}: " + "; ".join(r["capacidad"]["motivos"]) + ".")
    return r


class AsignarIn(BaseModel):
    codigo: Optional[str] = Field(None, max_length=40)       # escaneado
    consolidado_id: Optional[int] = None                    # con clic


@router.post("/cargues/{cid}/asignar")
async def asignar(cid: int, d: AsignarIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    k = await _cargue(db, cid)
    q = select(WMSConsolidado).with_for_update()
    if d.consolidado_id:
        q = q.where(WMSConsolidado.id == d.consolidado_id)
    elif d.codigo:
        q = q.where(func.upper(WMSConsolidado.codigo) == d.codigo.strip().strip("*").upper())
    else:
        raise HTTPException(422, "Escanee la etiqueta o elija el consolidado.")
    c = (await db.execute(q)).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, f"«{d.codigo}» no es la etiqueta de ningún consolidado.")
    if c.cargue_id == k.id:
        raise HTTPException(409, f"{c.codigo} ya está en este cargue.")
    if c.estado != "SOLICITADO":
        raise HTTPException(409, f"{c.codigo} está {c.estado.lower().replace('_', ' ')}: solo se cargan consolidados con transporte solicitado.")
    if c.almacen_id != k.almacen_id:
        raise HTTPException(409, f"{c.codigo} sale de otro almacén.")
    if c.modo_despacho != k.modo_despacho:
        raise HTTPException(409, f"{c.codigo} va por {MODOS.get(c.modo_despacho, c.modo_despacho)} y este cargue es de {MODOS[k.modo_despacho]}.")
    if k.modo_despacho in TERCERIZADOS and c.transportadora_id != k.transportadora_id:
        raise HTTPException(409, f"{c.codigo} está asignado a otra transportadora.")
    if k.vehiculo_id:
        veh = await db.get(TMSVehiculo, k.vehiculo_id)
        cs = (await db.execute(select(WMSConsolidado).where(WMSConsolidado.cargue_id == k.id))).scalars().all()
        peso = sum(x.peso_kg or 0 for x in cs) + (c.peso_kg or 0)
        vol = sum(x.volumen_m3 or 0 for x in cs) + (c.volumen_m3 or 0)
        r = await tms_capacidad.verificar(db, veh, peso or None, vol or None)
        if not r["ok"]:
            raise HTTPException(409, f"{c.codigo} no cabe en {veh.placa}: " + "; ".join(r["motivos"]) + ".")
    c.cargue_id, c.estado = k.id, "EN_CARGUE"
    await db.flush()
    await _actualizar_solicitudes(db, [c.solicitud_id])
    return await _cargue_dict(db, k)


class QuitarIn(BaseModel):
    consolidado_id: int


@router.post("/cargues/{cid}/quitar")
async def quitar(cid: int, d: QuitarIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    k = await _cargue(db, cid)
    c = await db.get(WMSConsolidado, d.consolidado_id)
    if c is None or c.cargue_id != k.id:
        raise HTTPException(404, "El consolidado no está en este cargue.")
    c.cargue_id, c.estado = None, "SOLICITADO"
    await db.flush()
    await _actualizar_solicitudes(db, [c.solicitud_id])
    return await _cargue_dict(db, k)


@router.post("/cargues/{cid}/cancelar")
async def cancelar(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    k = await _cargue(db, cid)
    sols = []
    for c in (await db.execute(select(WMSConsolidado).where(WMSConsolidado.cargue_id == k.id))).scalars().all():
        c.cargue_id, c.estado = None, "SOLICITADO"
        sols.append(c.solicitud_id)
    k.estado = "CANCELADO"
    await db.flush()
    await _actualizar_solicitudes(db, sols)
    return {"ok": True}


class ConfirmarIn(BaseModel):
    fecha_programada_cargue: Optional[datetime] = None
    fecha_programada_entrega: Optional[datetime] = None
    notas: Optional[str] = Field(None, max_length=500)


@router.post("/cargues/{cid}/confirmar")
async def confirmar(cid: int, d: ConfirmarIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Cierra el cargue: un despacho del WMS por orden (sale del staging) y un
    viaje del TMS con sus paradas. Si se interrumpe a mitad, se puede volver a
    confirmar: lo ya despachado no se repite."""
    from app.api.v1.endpoints.wms import crear_despacho
    from app.application.schemas.wms import WMSDespachoCreate
    from app.core.marketplace import servicio as mkp
    k = await _cargue(db, cid)
    cs = (await db.execute(select(WMSConsolidado).where(WMSConsolidado.cargue_id == k.id).order_by(WMSConsolidado.destino))).scalars().all()
    if not cs:
        raise HTTPException(409, "El cargue está vacío: asigne consolidados.")
    tercero = k.modo_despacho in TERCERIZADOS
    veh = await db.get(TMSVehiculo, k.vehiculo_id) if k.vehiculo_id else None
    if not tercero and veh is None:
        raise HTTPException(422, "Elija el vehículo antes de confirmar el cargue.")
    if tercero and not k.transportadora_id:
        raise HTTPException(422, "Elija la transportadora antes de confirmar el cargue.")
    peso = sum(c.peso_kg or 0 for c in cs) or None
    vol = sum(c.volumen_m3 or 0 for c in cs) or None
    if veh:
        await tms_capacidad.exigir(db, veh, peso, vol)
    placa = veh.placa if veh else k.placa_tercero
    cargue_codigo, cargue_id = k.codigo, k.id
    ids_cons = [c.id for c in cs]

    # 1. Un despacho por orden (crear_despacho confirma su propia transacción).
    rels = (await db.execute(select(WMSConsolidadoOrden).where(WMSConsolidadoOrden.consolidado_id.in_(ids_cons)))).scalars().all()
    for r in rels:
        if r.despacho_id:
            continue
        c = next(x for x in cs if x.id == r.consolidado_id)
        desp = await crear_despacho(WMSDespachoCreate(
            orden_id=r.orden_id, gestion_transporte="NINGUNA", transportadora_id=c.transportadora_id, vehiculo_placa=placa,
            peso_total_kg=r.peso_kg, volumen_total_m3=r.volumen_m3, estado="LISTO",
            notas=f"Cargue {cargue_codigo} · consolidado {c.codigo}"), db, yo)
        r2 = await db.get(WMSConsolidadoOrden, r.id)
        r2.despacho_id = desp.id
        await db.commit()

    # 2. El viaje con sus paradas.
    k = await _cargue(db, cargue_id)
    cs = (await db.execute(select(WMSConsolidado).where(WMSConsolidado.id.in_(ids_cons)).order_by(WMSConsolidado.destino))).scalars().all()
    rels = (await db.execute(select(WMSConsolidadoOrden).where(WMSConsolidadoOrden.consolidado_id.in_(ids_cons)))).scalars().all()
    ordenes = {o.id: o for o in (await db.execute(select(WMSOrdenSalida).where(WMSOrdenSalida.id.in_([r.orden_id for r in rels])))).scalars()}
    alm = await db.get(WMSAlmacen, k.almacen_id)
    if alm is not None and alm.lat is None:
        # El origen del viaje es la bodega: se ubica ahora si aún no tenía punto.
        from app.core import geo
        try:
            await geo.ubicar_almacen(alm)
        except Exception:  # noqa: BLE001 — sin conexión, el ciclo de fondo lo completa
            pass
    trans = await db.get(WMSTransportadora, k.transportadora_id) if k.transportadora_id else None
    ciudades = sorted({c.destino_ciudad or c.destino for c in cs})
    viaje = TMSViaje(
        codigo=await _numero(db, TMSViaje, TMSViaje.codigo, "VJ"), tipo_servicio=SERVICIO[k.modo_despacho],
        estado=EstadoViajeTMSEnum.ASIGNADO if veh else EstadoViajeTMSEnum.PROGRAMADO, vehiculo_id=veh.id if veh else None,
        origen_ciudad=alm.ciudad if alm else None,
        origen_direccion=f"{alm.nombre} — {alm.direccion or ''}".strip(" —") if alm else None,
        origen_lat=alm.lat if alm else None, origen_lng=alm.lng if alm else None,
        destino_ciudad=ciudades[0] if len(ciudades) == 1 else f"{len(ciudades)} destinos",
        destino_direccion=", ".join(ciudades)[:300], peso_kg=peso, volumen_m3=vol, num_entregas=len(rels),
        fecha_programada_cargue=d.fecha_programada_cargue or datetime.now(timezone.utc), fecha_programada_entrega=d.fecha_programada_entrega,
        descripcion_carga=f"Cargue {k.codigo} · {len(cs)} consolidados · {len(rels)} pedidos · {sum(c.bultos for c in cs)} bultos · {MODOS[k.modo_despacho]}",
        notas=(f"Transportadora {trans.nombre} · placa {k.placa_tercero or '-'}. " if trans else "") + (d.notas or ""),
        wms_despacho_id=rels[0].despacho_id if rels else None, creado_por_id=yo.id)
    db.add(viaje)
    await db.flush()
    sec = 1
    db.add(TMSParada(viaje_id=viaje.id, secuencia=sec, tipo=TipoParadaTMSEnum.ORIGEN, ciudad=(alm.ciudad if alm else None) or "Origen",
                     direccion=viaje.origen_direccion, lat=alm.lat if alm else None, lng=alm.lng if alm else None,
                     estado=EstadoParadaTMSEnum.PENDIENTE))
    paradas = OrderedDict()
    for c in cs:
        for r in sorted((x for x in rels if x.consolidado_id == c.id), key=lambda x: x.orden_id):
            o = ordenes.get(r.orden_id)
            clave = (c.destino, (o.destino_direccion or "") if k.modo_despacho in POR_DIRECCION else "")
            paradas.setdefault(clave, {"ciudad": (o.destino_ciudad if o else None) or c.destino_ciudad or c.destino,
                                       "direccion": clave[1] or None, "contacto": o.destino_contacto if o else None,
                                       "telefono": o.destino_telefono if o else None, "rels": [],
                                       # punto de la dirección de compra (en paqueteo, uno por dirección)
                                       "lat": o.destino_lat if o else None, "lng": o.destino_lng if o else None,
                                       "geo": o.destino_geo if o else None})["rels"].append((r, c))
    for i, (clave, p) in enumerate(paradas.items()):
        sec += 1
        par = TMSParada(viaje_id=viaje.id, secuencia=sec,
                        tipo=TipoParadaTMSEnum.DESTINO if i == len(paradas) - 1 else TipoParadaTMSEnum.PARADA_INTERMEDIA,
                        ciudad=p["ciudad"][:200], direccion=(p["direccion"] or None), contacto=(p["contacto"] or "")[:150] or None,
                        telefono_contacto=(p["telefono"] or "")[:30] or None, estado=EstadoParadaTMSEnum.PENDIENTE,
                        # Por ciudad (viaje nacional/flota) el punto es la ciudad, no la casa del primer pedido.
                        lat=p["lat"] if clave[1] else None, lng=p["lng"] if clave[1] else None,
                        observaciones="Entregar: " + ", ".join(sorted({c.codigo for _, c in p["rels"]})))
        db.add(par)
        await db.flush()
        if i == len(paradas) - 1 and len(paradas) == 1 and par.lat is not None:
            viaje.destino_lat, viaje.destino_lng = par.lat, par.lng
        for r, c in p["rels"]:
            db.add(TMSViajeDespacho(viaje_id=viaje.id, despacho_id=r.despacho_id, consolidado_id=c.id, parada_id=par.id))

    # 3. Consolidados, solicitudes, cargue y pedidos de los canales.
    for c in cs:
        c.estado, c.viaje_id = "DESPACHADO", viaje.id
    k.estado, k.viaje_id, k.confirmado_en = "CONFIRMADO", viaje.id, datetime.now(timezone.utc)
    await db.flush()
    await _actualizar_solicitudes(db, [c.solicitud_id for c in cs])
    for r in rels:
        p = (await db.execute(select(MKPPedido).where(MKPPedido.orden_salida_id == r.orden_id))).scalar()
        if p and p.estado not in ("DESPACHADO", "ENTREGADO", "CANCELADO"):
            c = next(x for x in cs if x.id == r.consolidado_id)
            p.estado, p.despacho_id, p.tracking = "DESPACHADO", r.despacho_id, c.guia or viaje.codigo
            await mkp.encolar_estado(db, p.id, "ENVIADO")
            await mkp.registrar(db, p.conector_id, "PEDIDO", True, f"Pedido {p.pedido_externo} cargado en {viaje.codigo} ({k.codigo})")
    await db.flush()
    return {"viaje_id": viaje.id, "viaje": viaje.codigo, "despachos": len(rels), "paradas": len(paradas), "cargue": await _cargue_dict(db, k)}


# ═════════════════════════════════════════════════════════════════════════════
# Lo que lleva un viaje (para la ficha del viaje)
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/viajes/{vid}/carga")
async def carga_del_viaje(vid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    links = (await db.execute(select(TMSViajeDespacho).where(TMSViajeDespacho.viaje_id == vid))).scalars().all()
    cs = (await db.execute(select(WMSConsolidado).where(WMSConsolidado.id.in_({l.consolidado_id for l in links if l.consolidado_id} or {0})))).scalars().all()
    return {"consolidados": await _cons_dict(db, cs), "despachos": len(links)}
