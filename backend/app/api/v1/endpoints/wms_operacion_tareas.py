"""
WMS · Operación de tareas. Prefijo: /wms

- Frentes de picking (mínimo / máximo por producto y ubicación, alternos).
- Parámetros de tareas y reabastecimiento por almacén.
- Reabastecimiento: evaluar, aprobar, rechazar.
- (Las jornadas de las personas viven en el módulo WFM · Personal: /personal.)
- Asignación dirigida: «Tomar siguiente», confirmar origen, reasignar.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import personal as per
from app.core import wms_tareas_dirigidas as wtd
from app.core import wms_reabastecimiento as reab
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSFrentePicking, WMSProducto, WMSTarea, WMSUbicacion, WMSZona,
)

router = APIRouter(prefix="/wms", tags=["wms-operacion-tareas"])
ZONAS_NO_FRENTE = ("RECEPCION", "CUARENTENA", "DESPACHO", "TRANSITO")


async def _tareas(db, tareas):
    from app.api.v1.endpoints.wms_trazable import _tareas_dict
    return await _tareas_dict(db, tareas)


async def _nombres(db, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: f"{u.nombre} {u.apellido or ''}".strip()
            for u in (await db.execute(select(Usuario).where(Usuario.id.in_(ids)))).scalars()}


# ═════════════════════════════════════════════════════════════════════════════
# Parámetros
# ═════════════════════════════════════════════════════════════════════════════
CAMPOS_CFG = ("reabastecimiento_activo", "requiere_aprobacion", "picking_solo_frentes", "picking_reserva_si_falta",
              "picking_excluir_pos", "exigir_escaneo_origen", "liberar_asignada_min", "alerta_en_curso_min",
              "nivel_montacargas")


class ConfigIn(BaseModel):
    reabastecimiento_activo: bool = True
    requiere_aprobacion: bool = True
    picking_solo_frentes: bool = True
    picking_reserva_si_falta: bool = False
    picking_excluir_pos: bool = True
    exigir_escaneo_origen: bool = True
    liberar_asignada_min: int = Field(15, ge=1, le=480)
    alerta_en_curso_min: int = Field(30, ge=1, le=480)
    nivel_montacargas: int = Field(2, ge=1, le=30)


@router.get("/config-tareas")
async def ver_config(almacen_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await reab.config(db, almacen_id)
    return {k: getattr(c, k) for k in CAMPOS_CFG}


@router.put("/config-tareas")
async def guardar_config(almacen_id: int, data: ConfigIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    if await db.get(WMSAlmacen, almacen_id) is None:
        raise HTTPException(404, "Almacén no encontrado.")
    c = await reab.config(db, almacen_id, crear=True)
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    return {k: getattr(c, k) for k in CAMPOS_CFG}


# ═════════════════════════════════════════════════════════════════════════════
# Frentes de picking
# ═════════════════════════════════════════════════════════════════════════════
class FrenteIn(BaseModel):
    almacen_id: int
    producto_id: int
    ubicacion_id: int
    unidad: str = "UNIDAD"
    minimo: float = Field(0, ge=0)
    maximo: float = Field(0, ge=0)
    prioridad: int = Field(1, ge=1, le=20)
    activo: bool = True


async def _frentes_dict(db, frentes) -> list:
    est = await reab.estado_frentes(db, frentes)
    prods = {p.id: p for p in (await db.execute(select(WMSProducto).where(
        WMSProducto.id.in_({f.producto_id for f in frentes} or {0})))).scalars()}
    ubic = {u.id: u for u in (await db.execute(select(WMSUbicacion).where(
        WMSUbicacion.id.in_({f.ubicacion_id for f in frentes} or {0})))).scalars()}
    zonas = {z.id: z for z in (await db.execute(select(WMSZona).where(
        WMSZona.id.in_({u.zona_id for u in ubic.values()} or {0})))).scalars()}
    abiertas = dict((await db.execute(select(WMSTarea.documento_id, func.count()).where(
        WMSTarea.documento_tipo == "FRENTE", WMSTarea.estado.in_(reab.ABIERTAS),
        WMSTarea.documento_id.in_([f.id for f in frentes] or [0])).group_by(WMSTarea.documento_id))).all())
    out = []
    for f in frentes:
        p, u = prods.get(f.producto_id), ubic.get(f.ubicacion_id)
        z = zonas.get(u.zona_id) if u else None
        out.append({"id": f.id, "almacen_id": f.almacen_id, "producto_id": f.producto_id, "sku": p.sku if p else None,
                    "producto": p.nombre if p else None, "ubicacion_id": f.ubicacion_id, "ubicacion": u.codigo if u else None,
                    "zona": z.codigo if z else None, "sala_pos": bool(z and z.vendible_pos), "unidad": f.unidad,
                    "minimo": f.minimo, "maximo": f.maximo, "prioridad": f.prioridad, "activo": f.activo,
                    "tareas_abiertas": abiertas.get(f.id, 0), **est[f.id]})
    return out


@router.get("/frentes")
async def listar_frentes(almacen_id: int, producto_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
                         _=Depends(get_current_user)):
    q = select(WMSFrentePicking).where(WMSFrentePicking.almacen_id == almacen_id)
    if producto_id:
        q = q.where(WMSFrentePicking.producto_id == producto_id)
    frentes = (await db.execute(q.order_by(WMSFrentePicking.producto_id, WMSFrentePicking.prioridad))).scalars().all()
    return await _frentes_dict(db, frentes)


async def _validar_frente(db, d: FrenteIn, fid: Optional[int] = None) -> None:
    if d.unidad not in reab.UNIDADES:
        raise HTTPException(422, f"Unidad inválida: use {', '.join(reab.UNIDADES)}.")
    if d.maximo and d.minimo > d.maximo:
        raise HTTPException(422, "El mínimo no puede ser mayor que el máximo.")
    if d.maximo <= 0:
        raise HTTPException(422, "Indique el máximo del frente (hasta cuánto se llena).")
    u = await db.get(WMSUbicacion, d.ubicacion_id)
    z = await db.get(WMSZona, u.zona_id) if u else None
    if u is None or z is None or z.almacen_id != d.almacen_id:
        raise HTTPException(422, "La ubicación no es de este almacén.")
    if z.tipo in ZONAS_NO_FRENTE:
        raise HTTPException(422, f"Una ubicación de {z.tipo.lower()} no puede ser frente de picking.")
    if await db.get(WMSProducto, d.producto_id) is None:
        raise HTTPException(404, "Producto no encontrado.")
    if await reab.factor(db, d.producto_id, d.unidad) is None:
        raise HTTPException(422, f"El producto no tiene empaque «{d.unidad.lower()}» registrado (Cubicaje › Productos).")
    dup = (await db.execute(select(WMSFrentePicking.id).where(
        WMSFrentePicking.producto_id == d.producto_id, WMSFrentePicking.ubicacion_id == d.ubicacion_id,
        WMSFrentePicking.id != (fid or 0)))).first()
    if dup:
        raise HTTPException(409, "Ese producto ya tiene un frente en esa ubicación.")


@router.post("/frentes", status_code=201)
async def crear_frente(d: FrenteIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    await _validar_frente(db, d)
    f = WMSFrentePicking(**d.model_dump())
    db.add(f)
    await db.flush()
    return (await _frentes_dict(db, [f]))[0]


@router.put("/frentes/{fid}")
async def editar_frente(fid: int, d: FrenteIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    f = await db.get(WMSFrentePicking, fid)
    if f is None:
        raise HTTPException(404, "Frente no encontrado.")
    await _validar_frente(db, d, fid)
    for k, v in d.model_dump().items():
        setattr(f, k, v)
    await db.flush()
    return (await _frentes_dict(db, [f]))[0]


@router.delete("/frentes/{fid}", status_code=204)
async def borrar_frente(fid: int, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    f = await db.get(WMSFrentePicking, fid)
    if f is None:
        raise HTTPException(404, "Frente no encontrado.")
    abiertas = (await db.execute(select(WMSTarea.id).where(WMSTarea.documento_tipo == "FRENTE", WMSTarea.documento_id == fid,
                                                           WMSTarea.estado.in_(reab.ABIERTAS)))).first()
    if abiertas:
        raise HTTPException(409, "El frente tiene reabastecimientos abiertos: termínelos o cancélelos, o deshabilítelo.")
    await db.delete(f)


# ═════════════════════════════════════════════════════════════════════════════
# Reabastecimiento
# ═════════════════════════════════════════════════════════════════════════════
@router.post("/reabastecimiento/evaluar")
async def evaluar(almacen_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await reab.evaluar(db, almacen_id)


class IdsIn(BaseModel):
    ids: List[int] = Field(min_length=1)


class MotivoIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=200)


@router.post("/tareas/aprobar")
async def aprobar(data: IdsIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(require_supervisor)):
    tareas = (await db.execute(select(WMSTarea).where(WMSTarea.id.in_(data.ids)).with_for_update())).scalars().all()
    hechas = []
    for t in tareas:
        if t.estado != "POR_APROBAR":
            continue
        t.estado, t.aprobada_por_id, t.aprobada_en = "PENDIENTE", yo.id, per.ahora()
        hechas.append(t)
    return {"aprobadas": len(hechas), "tareas": await _tareas(db, hechas)}


@router.post("/tareas/{tid}/rechazar")
async def rechazar(tid: int, data: MotivoIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(require_supervisor)):
    t = (await db.execute(select(WMSTarea).where(WMSTarea.id == tid).with_for_update())).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Tarea no encontrada.")
    if t.estado != "POR_APROBAR":
        raise HTTPException(409, "Solo se rechaza una tarea por aprobar.")
    t.estado, t.notas, t.aprobada_por_id, t.terminada_en = "RECHAZADA", data.motivo, yo.id, per.ahora()
    return (await _tareas(db, [t]))[0]


class ReasignarIn(BaseModel):
    operario_id: Optional[int] = None       # None = devolver a la cola


@router.post("/tareas/{tid}/reasignar")
async def reasignar(tid: int, data: ReasignarIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    t = (await db.execute(select(WMSTarea).where(WMSTarea.id == tid).with_for_update())).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Tarea no encontrada.")
    if t.estado not in ("PENDIENTE", "ASIGNADA", "EN_CURSO"):
        raise HTTPException(409, f"No se reasigna una tarea {t.estado.lower()}.")
    if data.operario_id is None:
        t.estado, t.operario_id, t.asignada_en, t.iniciada_en, t.jornada_id, t.origen_confirmado = \
            "PENDIENTE", None, None, None, None, None
    else:
        j = await per.jornada_abierta(db, data.operario_id)
        if j is None or j.almacen_id != t.almacen_id:
            raise HTTPException(409, "Ese operario no tiene jornada abierta en este almacén.")
        if await wtd.tarea_actual(db, data.operario_id):
            raise HTTPException(409, "Ese operario ya tiene una tarea en sus manos.")
        t.estado, t.operario_id, t.asignada_en, t.jornada_id = "ASIGNADA", data.operario_id, per.ahora(), j.id
        t.iniciada_en, t.origen_confirmado = None, None
    return (await _tareas(db, [t]))[0]


# ═════════════════════════════════════════════════════════════════════════════
# Operario: tomar siguiente y confirmar origen
# ═════════════════════════════════════════════════════════════════════════════
@router.post("/tareas/siguiente")
async def tomar_siguiente(db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    t = await wtd.siguiente(db, yo.id)
    return {"tarea": (await _tareas(db, [t]))[0] if t else None}


class OrigenIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=60)


@router.post("/tareas/{tid}/confirmar-origen")
async def confirmar_origen(tid: int, data: OrigenIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    t = (await db.execute(select(WMSTarea).where(WMSTarea.id == tid).with_for_update())).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Tarea no encontrada.")
    if t.estado not in ("PENDIENTE", "ASIGNADA", "EN_CURSO"):
        raise HTTPException(409, f"La tarea está {t.estado.lower()}.")
    if t.operario_id and t.operario_id != yo.id:
        raise HTTPException(409, "La tarea está asignada a otro operario.")
    await wtd.confirmar_origen(db, t, data.codigo)
    t.operario_id = yo.id
    if t.jornada_id is None:
        j = await per.jornada_abierta(db, yo.id)
        t.jornada_id = j.id if j else None
    return (await _tareas(db, [t]))[0]


class NovedadIn(BaseModel):
    tipo: str = Field(pattern="^(FALTANTE|DANADO|UBICACION_BLOQUEADA|OTRO)$")
    detalle: Optional[str] = Field(None, max_length=200)


@router.post("/tareas/{tid}/novedad")
async def novedad(tid: int, data: NovedadIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """El operario no puede hacer la tarea: vuelve a la cola con la novedad
    anotada (prioridad alta para que el supervisor la vea)."""
    t = (await db.execute(select(WMSTarea).where(WMSTarea.id == tid).with_for_update())).scalar_one_or_none()
    if t is None or t.estado not in ("ASIGNADA", "EN_CURSO"):
        raise HTTPException(409, "Solo se reporta una novedad sobre una tarea en sus manos.")
    texto = {"FALTANTE": "Faltante en origen", "DANADO": "Mercancía dañada", "UBICACION_BLOQUEADA": "Ubicación bloqueada",
             "OTRO": "Novedad"}[data.tipo]
    t.notas = f"{(t.notas or '').strip()} [{per.ahora():%d/%m %H:%M}] {texto}: {data.detalle or ''}".strip()[:2000]
    t.estado, t.operario_id, t.asignada_en, t.iniciada_en, t.jornada_id, t.origen_confirmado = \
        "PENDIENTE", None, None, None, None, None
    t.prioridad = min(t.prioridad, 1)
    if data.tipo != "OTRO" and t.tipo == "REABASTECIMIENTO":
        # No se vuelve a ofrecer hasta que el supervisor la revise.
        t.estado = "POR_APROBAR"
    return (await _tareas(db, [t]))[0]
