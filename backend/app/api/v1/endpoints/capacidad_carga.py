"""
Capacidad de vehículos (TMS) y sugerencia de vehículo para la carga (WMS).

  /tms/config/tipos-vehiculo            peso y volumen máximos por tipo
  /tms/vehiculos/{id}/verificar-carga   ¿cabe esta carga en este vehículo?
  /tms/viajes/{id}/vehiculos-aptos      tipo recomendado y vehículos que pueden llevar el viaje
  /wms/carga/estimar                    peso, volumen y vehículo sugerido para órdenes, un despacho o un traslado
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import tms_capacidad
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.tms import TMSTipoVehiculoCapacidad, TMSVehiculo, TMSViaje
from app.infrastructure.models.wms import (
    WMSDespachoDetalle, WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSTrasladoDetalle,
)

router = APIRouter(tags=["Capacidad de vehículos y carga"])


# ─── TMS: tipos de vehículo ───────────────────────────────────────────────────

@router.get("/tms/config/tipos-vehiculo")
async def listar_tipos(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    lista = [tms_capacidad.tipo_dict(t) for t in await tms_capacidad.tipos(db)]
    await db.commit()
    return lista


class TipoIn(BaseModel):
    capacidad_kg: Optional[float] = Field(default=None, gt=0)
    volumen_m3: Optional[float] = Field(default=None, gt=0)
    activo: bool = True


@router.put("/tms/config/tipos-vehiculo/{tipo}")
async def editar_tipo(tipo: str, data: TipoIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    await tms_capacidad.tipos(db)
    t = (await db.execute(select(TMSTipoVehiculoCapacidad).where(TMSTipoVehiculoCapacidad.tipo == tipo))).scalar()
    if not t:
        raise HTTPException(404, "Tipo de vehículo no encontrado")
    t.capacidad_kg, t.volumen_m3, t.activo = data.capacidad_kg, data.volumen_m3, data.activo
    await db.commit()
    return tms_capacidad.tipo_dict(t)


# ─── TMS: verificación ────────────────────────────────────────────────────────

@router.get("/tms/vehiculos/{vehiculo_id}/verificar-carga")
async def verificar_carga(vehiculo_id: int, peso_kg: Optional[float] = None, volumen_m3: Optional[float] = None,
                          viaje_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    veh = await db.get(TMSVehiculo, vehiculo_id)
    if not veh:
        raise HTTPException(404, "Vehículo no encontrado")
    if viaje_id and peso_kg is None and volumen_m3 is None:
        v = await db.get(TMSViaje, viaje_id)
        if v:
            peso_kg, volumen_m3 = v.peso_kg, v.volumen_m3
    r = await tms_capacidad.verificar(db, veh, peso_kg, volumen_m3, excluir_viaje_id=viaje_id)
    await db.commit()
    return r


@router.get("/tms/viajes/{viaje_id}/vehiculos-aptos")
async def vehiculos_aptos(viaje_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    v = await db.get(TMSViaje, viaje_id)
    if not v:
        raise HTTPException(404, "Viaje no encontrado")
    r = await tms_capacidad.sugerir(db, v.peso_kg, v.volumen_m3)
    await db.commit()
    return r


# ─── WMS: estimación de la carga y vehículo sugerido ──────────────────────────

class Linea(BaseModel):
    producto_id: int
    cantidad: float = Field(gt=0)


class EstimarIn(BaseModel):
    orden_ids: List[int] = []
    despacho_id: Optional[int] = None
    traslado_id: Optional[int] = None
    lineas: List[Linea] = []


@router.post("/wms/carga/estimar")
async def estimar(data: EstimarIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Peso y volumen de lo que se va a mover y el vehículo que conviene."""
    lineas = [(l.producto_id, l.cantidad) for l in data.lineas]
    if data.orden_ids:
        dets = (await db.execute(select(WMSOrdenSalidaDetalle).join(
            WMSOrdenSalida, WMSOrdenSalida.id == WMSOrdenSalidaDetalle.orden_id).where(
            WMSOrdenSalidaDetalle.orden_id.in_(data.orden_ids)))).scalars().all()
        lineas += [(d.producto_id, (d.cantidad_solicitada or 0) - (d.cantidad_despachada or 0)) for d in dets]
    if data.despacho_id:
        dets = (await db.execute(select(WMSDespachoDetalle).where(WMSDespachoDetalle.despacho_id == data.despacho_id))).scalars().all()
        lineas += [(d.producto_id, d.cantidad) for d in dets]
    if data.traslado_id:
        dets = (await db.execute(select(WMSTrasladoDetalle).where(WMSTrasladoDetalle.traslado_id == data.traslado_id))).scalars().all()
        lineas += [(d.producto_id, d.cantidad) for d in dets]
    est = await tms_capacidad.estimar_carga(db, lineas)
    sug = await tms_capacidad.sugerir(db, est["peso_kg"], est["volumen_m3"])
    await db.commit()
    return {**est, "sugerencia": sug}
