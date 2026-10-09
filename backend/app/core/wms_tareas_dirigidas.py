"""
WMS · Asignación dirigida de tareas a las personas en jornada (módulo WFM).

«Tomar siguiente» entrega a quien tiene la jornada ACTIVA la mejor tarea para
él según el alcance de su estación (almacén, tipos de tarea, zonas,
montacargas): prioridad, cercanía (orden de recorrido desde donde dejó la
última) y antigüedad. El operario no escoge.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import personal as per
from app.infrastructure.models.wms import WMSContenedor, WMSTarea, WMSUbicacion


async def tarea_actual(db: AsyncSession, usuario_id: int) -> Optional[WMSTarea]:
    return (await db.execute(select(WMSTarea).where(WMSTarea.operario_id == usuario_id,
                                                    WMSTarea.estado.in_(("ASIGNADA", "EN_CURSO")))
                             .order_by(WMSTarea.estado.desc(), WMSTarea.id).limit(1))).scalar_one_or_none()


async def liberar_de(db: AsyncSession, usuario_id: int, incluir_en_curso: bool) -> None:
    """Lo que la persona tiene asignado (y en curso, si se pide) vuelve a la cola."""
    estados = ("ASIGNADA", "EN_CURSO") if incluir_en_curso else ("ASIGNADA",)
    for t in (await db.execute(select(WMSTarea).where(WMSTarea.operario_id == usuario_id,
                                                      WMSTarea.estado.in_(estados)))).scalars():
        t.estado, t.operario_id, t.asignada_en, t.iniciada_en, t.jornada_id, t.origen_confirmado = \
            "PENDIENTE", None, None, None, None, None


async def confirmar_origen(db: AsyncSession, t: WMSTarea, codigo: str) -> None:
    """El operario escaneó el origen: la ubicación o la estiba que debe tomar."""
    c = (codigo or "").strip().upper()
    if not c:
        raise HTTPException(422, "Escanee la ubicación de origen.")
    ok = False
    if t.ubicacion_origen_id:
        u = await db.get(WMSUbicacion, t.ubicacion_origen_id)
        ok = bool(u and u.codigo.upper() == c)
    for cid in (t.contenedor_id, t.contenedor_origen_id):
        if not ok and cid:
            e = await db.get(WMSContenedor, cid)
            ok = bool(e and e.codigo.upper() == c)
    if not ok:
        raise HTTPException(422, f"«{codigo}» no es el origen de la tarea: vaya a la ubicación indicada.")
    t.origen_confirmado = True
    if t.estado in ("PENDIENTE", "ASIGNADA"):
        t.estado, t.iniciada_en = "EN_CURSO", t.iniciada_en or per.ahora()


def _nivel(u: Optional[WMSUbicacion]) -> int:
    try:
        return int(u.nivel) if u and u.nivel else 1
    except ValueError:
        return 1


async def siguiente(db: AsyncSession, usuario_id: int) -> Optional[WMSTarea]:
    """La tarea que le toca a la persona (la que ya tiene, o la mejor libre)."""
    from app.core import wms_reabastecimiento as reab
    from app.core.wms_slotting import clave_recorrido
    j = await per.jornada_abierta(db, usuario_id)
    if j is None:
        raise HTTPException(409, "Marque su entrada (inicie su jornada en Personal) para recibir tareas.")
    if j.estado == "PAUSADA":
        raise HTTPException(409, "Su jornada está en pausa: reanúdela para recibir tareas.")
    actual = await tarea_actual(db, usuario_id)
    if actual:
        return actual
    a = await per.alcance(db, j)
    if not a["funciones"]:
        return None
    cfg = await reab.config(db, a["almacen_id"])
    candidatas = (await db.execute(select(WMSTarea).where(
        WMSTarea.almacen_id == a["almacen_id"], WMSTarea.estado == "PENDIENTE", WMSTarea.tipo.in_(a["funciones"]))
        .order_by(WMSTarea.prioridad, WMSTarea.id).limit(200)
        .with_for_update(skip_locked=True))).scalars().all()
    if not candidatas:
        return None
    ids_u = {x for t in candidatas for x in (t.ubicacion_origen_id, t.ubicacion_sugerida_id) if x}
    ubic = {u.id: u for u in (await db.execute(select(WMSUbicacion).where(WMSUbicacion.id.in_(ids_u or {0})))).scalars()}
    zonas = set(a["zonas"] or [])
    ultima = (await db.execute(select(WMSTarea.ubicacion_destino_id).where(
        WMSTarea.operario_id == usuario_id, WMSTarea.estado == "COMPLETADA")
        .order_by(WMSTarea.terminada_en.desc().nullslast()).limit(1))).scalar()
    u_ultima = await db.get(WMSUbicacion, ultima) if ultima else None
    orden = sorted({**ubic, **({u_ultima.id: u_ultima} if u_ultima else {})}.values(), key=clave_recorrido)
    pos = {u.id: i for i, u in enumerate(orden)}
    punto = pos.get(u_ultima.id, 0) if u_ultima else 0

    def apta(t: WMSTarea) -> bool:
        uo, ud = ubic.get(t.ubicacion_origen_id), ubic.get(t.ubicacion_sugerida_id)
        if zonas and not ({u.zona_id for u in (uo, ud) if u} & zonas):
            return False
        if not a["montacargas"]:
            for u in (uo, ud):
                if u and (u.tipo or "").upper() == "PALLET" and _nivel(u) >= (cfg.nivel_montacargas or 2):
                    return False
        return True

    aptas = [t for t in candidatas if apta(t)]
    if not aptas:
        return None
    mejor = min(aptas, key=lambda t: (t.prioridad, abs(pos.get(t.ubicacion_origen_id, punto) - punto), t.id))
    mejor.estado, mejor.operario_id, mejor.asignada_en, mejor.jornada_id = "ASIGNADA", usuario_id, per.ahora(), j.id
    return mejor


async def liberar_vencidas(db: AsyncSession) -> int:
    """Tareas asignadas que nadie empezó a tiempo vuelven a la cola."""
    from app.core import wms_reabastecimiento as reab
    n = 0
    for t in (await db.execute(select(WMSTarea).where(WMSTarea.estado == "ASIGNADA"))).scalars().all():
        cfg = await reab.config(db, t.almacen_id)
        if t.asignada_en and (per.ahora() - t.asignada_en).total_seconds() > (cfg.liberar_asignada_min or 15) * 60:
            t.estado, t.operario_id, t.asignada_en, t.jornada_id = "PENDIENTE", None, None, None
            n += 1
    return n
