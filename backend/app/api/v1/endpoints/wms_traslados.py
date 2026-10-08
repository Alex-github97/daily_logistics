"""
Traslados entre almacenes, con la mercancía en tránsito.

Antes un traslado entre bodegas movía el stock al instante: salía de Bogotá y
aparecía en Medellín aunque el camión ni hubiera salido, y el POS de la tienda
podía venderlo. Y si se mandaban tres productos, el TMS recibía tres viajes.

Ahora un traslado es un documento con varias líneas y un solo viaje:
  1. al despachar, la mercancía pasa a la ubicación de TRÁNSITO del almacén
     destino: sigue siendo inventario (y de la empresa), pero no se alista ni se
     vende en ninguna parte;
  2. al recibir, el destino dice cuánto llegó y dónde lo guarda. Lo que no llegó
     sale del tránsito como faltante, y si es mercancía propia se contabiliza
     como merma.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import wms_contable, wms_inventario
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.tms import EstadoViajeTMSEnum, TipoServicioTMSEnum, TMSViaje
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSLote, WMSMovimientoInventario, WMSProducto, WMSTraslado, WMSTrasladoDetalle, WMSUbicacion, WMSZona,
)

router = APIRouter(prefix="/wms/traslados", tags=["WMS · Traslados"])


class LineaTraslado(BaseModel):
    producto_id: int
    ubicacion_origen_id: int
    cantidad: float = Field(gt=0)
    lote_id: Optional[int] = None
    contenedor_id: Optional[int] = None
    # Dónde se guardará en el destino (se puede decidir al recibir).
    ubicacion_destino_id: Optional[int] = None


class TrasladoIn(BaseModel):
    almacen_origen_id: int
    almacen_destino_id: int
    lineas: List[LineaTraslado] = Field(min_length=1)
    # TMS: crea UN viaje del transporte para todo el traslado.
    gestion_transporte: str = "NINGUNA"
    notas: Optional[str] = None


class LineaRecibo(BaseModel):
    detalle_id: int
    cantidad_recibida: float = Field(ge=0)
    ubicacion_destino_id: Optional[int] = None


class ReciboIn(BaseModel):
    # Vacío: llegó todo y se guarda donde dice cada línea (o en almacenamiento).
    lineas: List[LineaRecibo] = []
    notas: Optional[str] = None


async def _mover(db, **kw):
    try:
        return await wms_inventario.mover(db, **kw)
    except wms_inventario.StockInsuficiente as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


async def ubicacion_transito(db: AsyncSession, alm: WMSAlmacen) -> int:
    """La ubicación de tránsito del almacén; se crea la primera vez."""
    u = (await db.execute(select(WMSUbicacion.id).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
        WMSZona.almacen_id == alm.id, WMSZona.tipo == "TRANSITO").order_by(WMSUbicacion.id).limit(1))).scalar()
    if u:
        return u
    z = WMSZona(almacen_id=alm.id, codigo=f"TRN-{alm.id}", nombre=f"En tránsito hacia {alm.nombre}"[:150],
                tipo="TRANSITO", activo=True)
    db.add(z)
    await db.flush()
    ub = WMSUbicacion(zona_id=z.id, codigo=f"TRANSITO-{alm.id}", tipo="TRANSITO", activo=True)
    db.add(ub)
    await db.flush()
    return ub.id


async def _almacen_de(db, ubicacion_id: int) -> Optional[int]:
    return (await db.execute(select(WMSZona.almacen_id).join(WMSUbicacion, WMSUbicacion.zona_id == WMSZona.id)
                             .where(WMSUbicacion.id == ubicacion_id))).scalar()


async def _numero(db) -> str:
    from app.api.v1.endpoints.wms import _next_numero
    return await _next_numero(db, WMSTraslado, WMSTraslado.numero, "TRL")


async def crear_traslado(db: AsyncSession, yo: Usuario, data: TrasladoIn) -> WMSTraslado:
    if data.almacen_origen_id == data.almacen_destino_id:
        raise HTTPException(422, "Origen y destino son el mismo almacén: eso es una transferencia interna.")
    ori = await db.get(WMSAlmacen, data.almacen_origen_id)
    des = await db.get(WMSAlmacen, data.almacen_destino_id)
    if ori is None or des is None:
        raise HTTPException(404, "Almacén no encontrado.")
    transito = await ubicacion_transito(db, des)
    t = WMSTraslado(numero=await _numero(db), almacen_origen_id=ori.id, almacen_destino_id=des.id,
                    ubicacion_transito_id=transito, estado="EN_TRANSITO", despachado_en=datetime.now(timezone.utc),
                    usuario_id=yo.id, notas=data.notas)
    db.add(t)
    await db.flush()
    peso = volumen = 0.0
    nombres = []
    for ln in data.lineas:
        if await _almacen_de(db, ln.ubicacion_origen_id) != ori.id:
            raise HTTPException(422, "Una ubicación de origen no es del almacén de origen.")
        if ln.ubicacion_destino_id and await _almacen_de(db, ln.ubicacion_destino_id) != des.id:
            raise HTTPException(422, "Una ubicación de destino no es del almacén de destino.")
        prod = await db.get(WMSProducto, ln.producto_id)
        if prod is None:
            raise HTTPException(404, "Producto no encontrado.")
        await _mover(db, tipo="TRANSFERENCIA", producto_id=ln.producto_id, cantidad=ln.cantidad, lote_id=ln.lote_id,
                     origen=ln.ubicacion_origen_id, destino=transito, contenedor_origen=ln.contenedor_id,
                     contenedor_destino=None, documento_tipo="TRASLADO", documento_id=t.id, referencia=t.numero,
                     usuario_id=yo.id, notas=f"En tránsito hacia {des.nombre}")
        db.add(WMSTrasladoDetalle(traslado_id=t.id, producto_id=ln.producto_id, lote_id=ln.lote_id, cantidad=ln.cantidad,
                                  ubicacion_origen_id=ln.ubicacion_origen_id, ubicacion_destino_id=ln.ubicacion_destino_id))
        peso += (prod.peso_kg or 0) * ln.cantidad
        volumen += (prod.volumen_m3 or 0) * ln.cantidad
        nombres.append(f"{ln.cantidad:g} × {prod.nombre}")

    if (data.gestion_transporte or "").upper() == "TMS":
        from app.api.v1.endpoints.wms import _next_numero
        codigo = await _next_numero(db, TMSViaje, TMSViaje.codigo, "TRAS")
        misma = bool(ori.ciudad and ori.ciudad == des.ciudad)
        viaje = TMSViaje(
            codigo=codigo,
            tipo_servicio=TipoServicioTMSEnum.TERRESTRE_URBANO if misma else TipoServicioTMSEnum.TERRESTRE_NACIONAL,
            estado=EstadoViajeTMSEnum.PROGRAMADO, origen_ciudad=ori.ciudad,
            origen_direccion=f"{ori.nombre} — {ori.direccion or ''}".strip(" —"), destino_ciudad=des.ciudad,
            destino_direccion=f"{des.nombre} — {des.direccion or ''}".strip(" —"),
            peso_kg=round(peso, 2) or None, volumen_m3=round(volumen, 3) or None, num_entregas=1,
            fecha_programada_cargue=datetime.now(timezone.utc),
            descripcion_carga=f"Traslado {t.numero}: " + "; ".join(nombres)[:900],
            notas=f"Generado desde WMS · traslado {t.numero} entre almacenes. {data.notas or ''}".strip(),
            creado_por_id=yo.id)
        db.add(viaje)
        await db.flush()
        t.tms_viaje_id, t.tms_codigo = viaje.id, codigo
    return t


async def _dict(db, t: WMSTraslado) -> dict:
    alm = dict((await db.execute(select(WMSAlmacen.id, WMSAlmacen.nombre).where(
        WMSAlmacen.id.in_([t.almacen_origen_id, t.almacen_destino_id])))).all())
    pids = [d.producto_id for d in t.detalles]
    prods = {p.id: p for p in (await db.execute(select(WMSProducto).where(WMSProducto.id.in_(pids or [0])))).scalars()}
    uids = {u for d in t.detalles for u in (d.ubicacion_origen_id, d.ubicacion_destino_id) if u}
    ubic = dict((await db.execute(select(WMSUbicacion.id, WMSUbicacion.codigo).where(WMSUbicacion.id.in_(uids or [0])))).all())
    lids = [d.lote_id for d in t.detalles if d.lote_id]
    lotes = dict((await db.execute(select(WMSLote.id, WMSLote.numero_lote).where(WMSLote.id.in_(lids or [0])))).all())
    return {
        "id": t.id, "numero": t.numero, "estado": t.estado,
        "almacen_origen_id": t.almacen_origen_id, "almacen_origen": alm.get(t.almacen_origen_id),
        "almacen_destino_id": t.almacen_destino_id, "almacen_destino": alm.get(t.almacen_destino_id),
        "tms_codigo": t.tms_codigo, "despachado_en": t.despachado_en, "recibido_en": t.recibido_en, "notas": t.notas,
        "lineas": [{"id": d.id, "producto_id": d.producto_id, "sku": prods[d.producto_id].sku if d.producto_id in prods else None,
                    "producto": prods[d.producto_id].nombre if d.producto_id in prods else None,
                    "lote": lotes.get(d.lote_id), "lote_id": d.lote_id, "cantidad": d.cantidad,
                    "cantidad_recibida": d.cantidad_recibida,
                    "ubicacion_origen": ubic.get(d.ubicacion_origen_id), "ubicacion_destino_id": d.ubicacion_destino_id,
                    "ubicacion_destino": ubic.get(d.ubicacion_destino_id)} for d in t.detalles],
    }


async def _cargar(db, tid: int, bloquear=False) -> WMSTraslado:
    q = select(WMSTraslado).options(selectinload(WMSTraslado.detalles)).where(WMSTraslado.id == tid)
    if bloquear:
        q = q.with_for_update(of=WMSTraslado)
    t = (await db.execute(q)).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Traslado no encontrado.")
    return t


@router.get("")
async def listar(estado: Optional[str] = None, almacen_id: Optional[int] = None, limite: int = Query(200, le=1000),
                 db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSTraslado).options(selectinload(WMSTraslado.detalles)).order_by(WMSTraslado.id.desc()).limit(limite)
    if estado:
        q = q.where(WMSTraslado.estado == estado)
    if almacen_id:
        q = q.where((WMSTraslado.almacen_origen_id == almacen_id) | (WMSTraslado.almacen_destino_id == almacen_id))
    return [await _dict(db, t) for t in (await db.execute(q)).scalars()]


@router.get("/{tid}")
async def ver(tid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await _dict(db, await _cargar(db, tid))


@router.post("", status_code=201)
async def crear(data: TrasladoIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    t = await crear_traslado(db, yo, data)
    await db.commit()
    return await _dict(db, await _cargar(db, t.id))


@router.post("/{tid}/recibir")
async def recibir(tid: int, data: ReciboIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    t = await _cargar(db, tid, bloquear=True)
    if t.estado != "EN_TRANSITO":
        raise HTTPException(409, f"El traslado ya está {t.estado.lower()}.")
    por_det = {ln.detalle_id: ln for ln in data.lineas}
    if set(por_det) - {d.id for d in t.detalles}:
        raise HTTPException(422, "Una línea no pertenece a este traslado.")
    almacenaje = await wms_inventario.ubicacion_de_zona(db, t.almacen_destino_id, "ALMACENAMIENTO")
    faltantes: List[WMSMovimientoInventario] = []
    for d in t.detalles:
        ln = por_det.get(d.id)
        llego = d.cantidad if ln is None else ln.cantidad_recibida
        if llego > d.cantidad + 1e-9:
            raise HTTPException(422, f"Llegaron más de las {d.cantidad:g} unidades despachadas: regístrelo como una recepción aparte.")
        destino = (ln.ubicacion_destino_id if ln and ln.ubicacion_destino_id else None) or d.ubicacion_destino_id or almacenaje
        if destino is None:
            raise HTTPException(422, "El almacén destino no tiene ubicaciones de almacenamiento: indique dónde se guarda.")
        if await _almacen_de(db, destino) != t.almacen_destino_id:
            raise HTTPException(422, "La ubicación de destino no es del almacén que recibe.")
        if llego > 0:
            await _mover(db, tipo="TRANSFERENCIA", producto_id=d.producto_id, cantidad=llego, lote_id=d.lote_id,
                         origen=t.ubicacion_transito_id, destino=destino, documento_tipo="TRASLADO", documento_id=t.id,
                         referencia=t.numero, usuario_id=yo.id, notas="Recibido del traslado")
        falta = d.cantidad - llego
        if falta > 1e-9:
            faltantes.append(await _mover(db, tipo="AJUSTE", producto_id=d.producto_id, cantidad=falta, lote_id=d.lote_id,
                                          origen=t.ubicacion_transito_id, documento_tipo="TRASLADO", documento_id=t.id,
                                          referencia=t.numero, usuario_id=yo.id,
                                          notas=f"No llegó en el traslado {t.numero}"))
        d.cantidad_recibida, d.ubicacion_destino_id = llego, destino
    await wms_contable.contabilizar_ajuste(db, faltantes, yo.username, f"Faltante en el traslado {t.numero}",
                                           "TRASLADO", t.id)
    t.estado, t.recibido_en, t.recibido_por_id = "RECIBIDO", datetime.now(timezone.utc), yo.id
    if data.notas:
        t.notas = f"{t.notas or ''} | Recibo: {data.notas}".strip(" |")
    if t.tms_viaje_id:
        viaje = await db.get(TMSViaje, t.tms_viaje_id)
        if viaje and viaje.estado not in (EstadoViajeTMSEnum.ENTREGADO, EstadoViajeTMSEnum.CERRADO, EstadoViajeTMSEnum.CANCELADO):
            viaje.estado = EstadoViajeTMSEnum.ENTREGADO
            # Sin fecha real de entrega el viaje no entraba en el OTIF del TMS.
            viaje.fecha_real_entrega = t.recibido_en
            viaje.otif_in_full = not faltantes
            if viaje.fecha_programada_entrega:
                from app.api.v1.endpoints.tms import _a_tiempo
                viaje.otif_on_time = _a_tiempo(viaje)
    await db.commit()
    return await _dict(db, await _cargar(db, t.id))
