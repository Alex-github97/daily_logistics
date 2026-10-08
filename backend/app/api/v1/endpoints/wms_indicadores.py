"""
WMS · Indicadores: tablero, ficha de cada indicador (con serie y detalle),
metas por almacén y productividad por operario.
Prefijo: /wms
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_kpi as kpi
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSKPIMeta, WMSOrdenSalida, WMSPickingDetalle, WMSPickingTarea, WMSTarea,
)

router = APIRouter(prefix="/wms", tags=["wms-indicadores"])
log = logging.getLogger(__name__)


def _hoy_bogota() -> date:
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def _ctx(desde, hasta, almacen_id, depositante_id) -> kpi.Ctx:
    hasta = hasta or _hoy_bogota()
    desde = desde or (hasta - timedelta(days=29))
    if desde > hasta:
        raise HTTPException(422, "La fecha inicial es posterior a la final.")
    return kpi.Ctx(desde, hasta, almacen_id, depositante_id)


async def _metas(db: AsyncSession, almacen_id: Optional[int]) -> dict:
    """La meta del almacén si la hay; si no, la general; si no, la sugerida."""
    filas = (await db.execute(select(WMSKPIMeta).where(
        (WMSKPIMeta.almacen_id.is_(None)) | (WMSKPIMeta.almacen_id == almacen_id)))).scalars().all()
    out = {f.clave: f.meta for f in kpi.CATALOGO}
    for m in sorted(filas, key=lambda m: m.almacen_id is not None):
        out[m.clave] = m.meta
    return out


async def _calcular(db, clave: str, ctx: kpi.Ctx) -> kpi.Resultado:
    try:
        return await kpi.CALCULOS[clave](db, ctx)
    except Exception as e:     # un indicador roto no tumba el tablero
        log.exception("Indicador %s", clave)
        await db.rollback()
        return kpi.Resultado(None, avisos=[f"No se pudo calcular: {type(e).__name__}"])


def _ficha(f: kpi.Ficha, meta: float) -> dict:
    return {**asdict(f), "meta_sugerida": f.meta, "meta": meta}


@router.get("/indicadores/catalogo")
async def catalogo(almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    metas = await _metas(db, almacen_id)
    return [_ficha(f, metas[f.clave]) for f in kpi.CATALOGO]


@router.get("/indicadores")
async def tablero(desde: Optional[date] = None, hasta: Optional[date] = None, almacen_id: Optional[int] = None,
                  depositante_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    ctx = _ctx(desde, hasta, almacen_id, depositante_id)
    previo = kpi.Ctx(ctx.desde - timedelta(days=ctx.dias), ctx.desde - timedelta(days=1), almacen_id, depositante_id)
    metas = await _metas(db, almacen_id)
    out = []
    for f in kpi.CATALOGO:
        r = await _calcular(db, f.clave, ctx)
        antes = None if f.instantaneo else (await _calcular(db, f.clave, previo)).valor
        out.append({"clave": f.clave, "nombre": f.nombre, "categoria": f.categoria, "unidad": f.unidad, "sentido": f.sentido,
                    "especializado": f.especializado, "instantaneo": f.instantaneo, "valor": r.valor,
                    "numerador": r.numerador, "denominador": r.denominador, "muestras": r.muestras, "avisos": r.avisos,
                    "meta": metas[f.clave], "semaforo": kpi.semaforo(f, r.valor, metas[f.clave]), "anterior": antes})
    return {"desde": ctx.desde.isoformat(), "hasta": ctx.hasta.isoformat(), "indicadores": out}


def _cortes(ctx: kpi.Ctx):
    """Hasta 12 cortes: semanas si el periodo es corto, meses si es largo."""
    if ctx.dias <= 98:
        paso = 7
        inicio = ctx.desde
        while inicio <= ctx.hasta:
            yield inicio, min(inicio + timedelta(days=paso - 1), ctx.hasta)
            inicio += timedelta(days=paso)
    else:
        inicio = ctx.desde.replace(day=1)
        while inicio <= ctx.hasta:
            sig = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
            yield max(inicio, ctx.desde), min(sig - timedelta(days=1), ctx.hasta)
            inicio = sig


@router.get("/indicadores/operarios")
async def operarios(desde: Optional[date] = None, hasta: Optional[date] = None, almacen_id: Optional[int] = None,
                    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Productividad por persona: tareas de ubicación y líneas de alistamiento por hora."""
    ctx = _ctx(desde, hasta, almacen_id, None)
    personas: dict = {}

    def p(uid):
        return personas.setdefault(uid, {"usuario_id": uid, "tareas": 0, "horas_ubicacion": 0.0, "desvios": 0,
                                         "lineas": 0, "horas_alistamiento": 0.0, "tareas_alistamiento": 0})
    q = select(WMSTarea).where(WMSTarea.estado == "COMPLETADA", WMSTarea.terminada_en >= ctx.ini, WMSTarea.terminada_en < ctx.fin,
                               WMSTarea.operario_id.isnot(None))
    if almacen_id:
        q = q.where(WMSTarea.almacen_id == almacen_id)
    for t in (await db.execute(q)).scalars():
        d = p(t.operario_id)
        d["tareas"] += 1
        d["horas_ubicacion"] += max(0.0, kpi._h(t.iniciada_en, t.terminada_en) or 0)
        d["desvios"] += bool(t.ubicacion_sugerida_id and t.ubicacion_destino_id != t.ubicacion_sugerida_id)
    q = (select(WMSPickingTarea).join(WMSOrdenSalida, WMSOrdenSalida.id == WMSPickingTarea.orden_id)
         .where(WMSPickingTarea.estado == "COMPLETADA", WMSPickingTarea.fecha_fin >= ctx.ini, WMSPickingTarea.fecha_fin < ctx.fin,
                WMSPickingTarea.operario_id.isnot(None)))
    if almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == almacen_id)
    tareas = (await db.execute(q)).scalars().all()
    lineas = dict((await db.execute(select(WMSPickingDetalle.tarea_id, func.count()).where(
        WMSPickingDetalle.tarea_id.in_([t.id for t in tareas] or [0]), WMSPickingDetalle.confirmado.is_(True))
        .group_by(WMSPickingDetalle.tarea_id))).all())
    for t in tareas:
        d = p(t.operario_id)
        d["tareas_alistamiento"] += 1
        d["lineas"] += lineas.get(t.id, 0)
        d["horas_alistamiento"] += max(0.0, kpi._h(t.fecha_inicio, t.fecha_fin) or 0)
    nombres = {u.id: f"{u.nombre} {u.apellido}".strip() for u in (await db.execute(
        select(Usuario).where(Usuario.id.in_(list(personas) or [0])))).scalars()}
    out = []
    for uid, d in personas.items():
        out.append({**d, "nombre": nombres.get(uid, f"Usuario {uid}"),
                    "horas_ubicacion": round(d["horas_ubicacion"], 2), "horas_alistamiento": round(d["horas_alistamiento"], 2),
                    "tareas_por_hora": round(d["tareas"] / d["horas_ubicacion"], 1) if d["horas_ubicacion"] else None,
                    "lineas_por_hora": round(d["lineas"] / d["horas_alistamiento"], 1) if d["horas_alistamiento"] else None,
                    "desvio_pct": round(d["desvios"] / d["tareas"] * 100, 1) if d["tareas"] else None})
    return sorted(out, key=lambda d: -(d["lineas"] + d["tareas"]))


@router.get("/indicadores/{clave}")
async def ficha(clave: str, desde: Optional[date] = None, hasta: Optional[date] = None, almacen_id: Optional[int] = None,
                depositante_id: Optional[int] = None, detalle: int = Query(300, le=2000),
                db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    f = kpi.FICHAS.get(clave)
    if f is None:
        raise HTTPException(404, "Indicador desconocido.")
    ctx = _ctx(desde, hasta, almacen_id, depositante_id)
    metas = await _metas(db, almacen_id)
    r = await _calcular(db, clave, ctx)
    serie = []
    if not f.instantaneo:
        for a, b in _cortes(ctx):
            x = await _calcular(db, clave, kpi.Ctx(a, b, almacen_id, depositante_id))
            serie.append({"desde": a.isoformat(), "hasta": b.isoformat(), "valor": x.valor, "muestras": x.muestras})
    return {"ficha": _ficha(f, metas[clave]), "desde": ctx.desde.isoformat(), "hasta": ctx.hasta.isoformat(),
            "valor": r.valor, "numerador": r.numerador, "denominador": r.denominador, "muestras": r.muestras,
            "avisos": r.avisos, "semaforo": kpi.semaforo(f, r.valor, metas[clave]), "serie": serie,
            "detalle": r.detalle[:detalle], "detalle_total": len(r.detalle)}


class MetaIn(BaseModel):
    meta: float
    almacen_id: Optional[int] = None


@router.put("/indicadores/{clave}/meta")
async def fijar_meta(clave: str, data: MetaIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(require_supervisor)):
    f = kpi.FICHAS.get(clave)
    if f is None:
        raise HTTPException(404, "Indicador desconocido.")
    if f.unidad == "%" and not 0 <= data.meta <= 100:
        raise HTTPException(422, "Una meta en porcentaje va de 0 a 100.")
    if data.meta < 0:
        raise HTTPException(422, "La meta no puede ser negativa.")
    m = (await db.execute(select(WMSKPIMeta).where(
        WMSKPIMeta.clave == clave,
        WMSKPIMeta.almacen_id.is_(None) if data.almacen_id is None else WMSKPIMeta.almacen_id == data.almacen_id))).scalar_one_or_none()
    if m is None:
        m = WMSKPIMeta(clave=clave, almacen_id=data.almacen_id, meta=data.meta)
        db.add(m)
    m.meta, m.fijada_por_id = data.meta, yo.id
    return {"clave": clave, "almacen_id": data.almacen_id, "meta": data.meta}
