"""
WFM · Personal operativo: jornadas, estaciones de trabajo y tiempos.

- La persona marca la entrada (en su dispositivo o con el carné en el kiosco).
  Su estación sale de la programación del día; si no la hay, de su estación
  habitual; si tampoco, trabaja sin estación con las funciones que elija.
- La estación dice qué tareas recibe y en qué zonas; si exige montacargas, la
  persona debe tener esa habilidad.
- Pausas (descanso, almuerzo…), cambio de estación por el supervisor y salida.
- Métricas: jornada, pausas, tiempo en tareas, tiempo sin tarea, utilización,
  tareas por hora, y tiempo por estación.

Las tareas son de cada módulo (hoy, las del WMS): este módulo solo dice quién
está trabajando, dónde y con qué alcance.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.personal import (
    FUNCIONES_WMS, PerEstacion, PerJornada, PerJornadaPausa, PerJornadaTramo, PerPerfil, PerProgramacion,
)

MOTIVOS_PAUSA = ("DESCANSO", "ALMUERZO", "CAPACITACION", "REUNION", "OTRO")
# Funciones por defecto según el tipo de estación.
FUNCIONES_DE_TIPO = {
    "RECEPCION": ["UBICACION"], "UBICACION": ["UBICACION", "MOVIMIENTO"], "REABASTECIMIENTO": ["REABASTECIMIENTO"],
    "PICKING": ["REABASTECIMIENTO"], "GENERAL": list(FUNCIONES_WMS),
}


def ahora() -> datetime:
    return datetime.now(timezone.utc)


async def jornada_abierta(db: AsyncSession, usuario_id: Optional[int]) -> Optional[PerJornada]:
    if not usuario_id:
        return None
    return (await db.execute(select(PerJornada).where(PerJornada.usuario_id == usuario_id,
                                                      PerJornada.estado.in_(("ACTIVA", "PAUSADA")))
                             .order_by(PerJornada.id.desc()).limit(1))).scalar_one_or_none()


async def perfil(db: AsyncSession, usuario_id: int) -> Optional[PerPerfil]:
    return (await db.execute(select(PerPerfil).where(PerPerfil.usuario_id == usuario_id))).scalar_one_or_none()


def _minutos_del_dia(hhmm: Optional[str]) -> Optional[int]:
    try:
        h, m = (hhmm or "").split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


async def programado(db: AsyncSession, usuario_id: int, dia: Optional[date] = None) -> Optional[PerProgramacion]:
    """La programación de hoy para la persona (la del horario en curso si hay varias)."""
    filas = (await db.execute(select(PerProgramacion).where(PerProgramacion.usuario_id == usuario_id,
                                                            PerProgramacion.fecha == (dia or date.today()))
                              .order_by(PerProgramacion.hora_inicio))).scalars().all()
    if len(filas) <= 1:
        return filas[0] if filas else None
    t = datetime.now()
    m = t.hour * 60 + t.minute
    for p in filas:
        a, b = _minutos_del_dia(p.hora_inicio), _minutos_del_dia(p.hora_fin)
        if a is not None and b is not None and a <= m < b:
            return p
    return filas[0]


async def alcance(db: AsyncSession, j: PerJornada) -> dict:
    """Qué puede recibir la persona en esta jornada: almacén, funciones, zonas, montacargas."""
    est = await db.get(PerEstacion, j.estacion_id) if j.estacion_id else None
    p = await perfil(db, j.usuario_id)
    hab = set((p.habilidades or []) if p else [])
    if est:
        funciones = [f for f in (est.funciones or FUNCIONES_DE_TIPO.get(est.tipo, [])) if f in FUNCIONES_WMS]
        zonas = est.zonas or []
        almacen = est.almacen_id or j.almacen_id
    else:
        funciones = [f for f in (j.funciones or FUNCIONES_WMS) if f in FUNCIONES_WMS]
        zonas = j.zonas or []
        almacen = j.almacen_id
    return {"estacion": est, "almacen_id": almacen, "funciones": funciones, "zonas": zonas,
            "montacargas": j.montacargas or "MONTACARGAS" in hab}


async def _validar_estacion(db: AsyncSession, est: PerEstacion, usuario_id: int) -> None:
    if not est.activo:
        raise HTTPException(409, f"La estación {est.codigo} está inactiva.")
    if est.requiere_montacargas:
        p = await perfil(db, usuario_id)
        if not p or "MONTACARGAS" not in (p.habilidades or []):
            raise HTTPException(409, f"La estación {est.codigo} exige montacargas y la persona no tiene esa habilidad registrada.")


async def iniciar(db: AsyncSession, usuario_id: int, *, almacen_id: Optional[int] = None, estacion_id: Optional[int] = None,
                  funciones: Optional[List[str]] = None, zonas: Optional[List[int]] = None, montacargas: bool = False,
                  origen: str = "APP") -> PerJornada:
    if await jornada_abierta(db, usuario_id):
        raise HTTPException(409, "Ya tiene una jornada abierta.")
    p = await perfil(db, usuario_id)
    if p and not p.activo:
        raise HTTPException(409, "La persona está inactiva en el módulo de personal.")
    if estacion_id is None:
        prog = await programado(db, usuario_id)
        estacion_id = prog.estacion_id if prog else (p.estacion_id if p else None)
    est = await db.get(PerEstacion, estacion_id) if estacion_id else None
    if est:
        await _validar_estacion(db, est, usuario_id)
    almacen = (est.almacen_id if est and est.almacen_id else None) or almacen_id or (p.almacen_id if p else None)
    if not almacen:
        raise HTTPException(422, "Indique el almacén (o asigne a la persona una estación o un almacén habitual).")
    malas = [f for f in (funciones or []) if f not in FUNCIONES_WMS]
    if malas:
        raise HTTPException(422, f"Funciones desconocidas: {', '.join(malas)}.")
    t = ahora()
    j = PerJornada(usuario_id=usuario_id, almacen_id=almacen, estado="ACTIVA", inicio=t, estacion_id=est.id if est else None,
                   funciones=funciones or None, zonas=zonas or None, montacargas=montacargas, origen=origen)
    db.add(j)
    await db.flush()
    db.add(PerJornadaTramo(jornada_id=j.id, estacion_id=j.estacion_id, inicio=t))
    await db.flush()
    return j


async def _liberar_tareas(db: AsyncSession, usuario_id: int, incluir_en_curso: bool) -> None:
    from app.core import wms_tareas_dirigidas as wtd
    await wtd.liberar_de(db, usuario_id, incluir_en_curso)


async def pausar(db: AsyncSession, j: PerJornada, motivo: str) -> None:
    from app.core import wms_tareas_dirigidas as wtd
    if j.estado != "ACTIVA":
        raise HTTPException(409, "La jornada no está activa.")
    if motivo not in MOTIVOS_PAUSA:
        raise HTTPException(422, "Motivo de pausa inválido.")
    t = await wtd.tarea_actual(db, j.usuario_id)
    if t and t.estado == "EN_CURSO":
        raise HTTPException(409, "Termine (o reporte) la tarea en curso antes de pausar.")
    await _liberar_tareas(db, j.usuario_id, False)
    db.add(PerJornadaPausa(jornada_id=j.id, motivo=motivo, inicio=ahora()))
    j.estado = "PAUSADA"
    await db.flush()


async def reanudar(db: AsyncSession, j: PerJornada) -> None:
    if j.estado != "PAUSADA":
        raise HTTPException(409, "La jornada no está en pausa.")
    for p in (await db.execute(select(PerJornadaPausa).where(PerJornadaPausa.jornada_id == j.id,
                                                             PerJornadaPausa.fin.is_(None)))).scalars():
        p.fin = ahora()
    j.estado = "ACTIVA"
    await db.flush()


async def cerrar(db: AsyncSession, j: PerJornada, auto: bool = False, forzar: bool = False) -> None:
    from app.core import wms_tareas_dirigidas as wtd
    if not forzar and not auto:
        t = await wtd.tarea_actual(db, j.usuario_id)
        if t and t.estado == "EN_CURSO":
            raise HTTPException(409, "Termine (o reporte) la tarea en curso antes de cerrar la jornada.")
    fin = ahora()
    for p in (await db.execute(select(PerJornadaPausa).where(PerJornadaPausa.jornada_id == j.id,
                                                             PerJornadaPausa.fin.is_(None)))).scalars():
        p.fin = fin
    for tr in (await db.execute(select(PerJornadaTramo).where(PerJornadaTramo.jornada_id == j.id,
                                                              PerJornadaTramo.fin.is_(None)))).scalars():
        tr.fin = fin
    await _liberar_tareas(db, j.usuario_id, True)
    j.estado, j.fin, j.cierre_auto = "CERRADA", fin, auto
    await db.flush()


async def mover_estacion(db: AsyncSession, j: PerJornada, estacion_id: Optional[int]) -> None:
    """El supervisor cambia a la persona de estación (o la deja sin estación)."""
    from app.core import wms_tareas_dirigidas as wtd
    if j.estado == "CERRADA":
        raise HTTPException(409, "La jornada está cerrada.")
    est = await db.get(PerEstacion, estacion_id) if estacion_id else None
    if estacion_id and est is None:
        raise HTTPException(404, "Estación no encontrada.")
    if est:
        await _validar_estacion(db, est, j.usuario_id)
    t = await wtd.tarea_actual(db, j.usuario_id)
    if t and t.estado == "EN_CURSO":
        raise HTTPException(409, "La persona tiene una tarea en curso: muévala cuando la termine.")
    await _liberar_tareas(db, j.usuario_id, False)
    fin = ahora()
    for tr in (await db.execute(select(PerJornadaTramo).where(PerJornadaTramo.jornada_id == j.id,
                                                              PerJornadaTramo.fin.is_(None)))).scalars():
        tr.fin = fin
    j.estacion_id = est.id if est else None
    if est and est.almacen_id:
        j.almacen_id = est.almacen_id
    db.add(PerJornadaTramo(jornada_id=j.id, estacion_id=j.estacion_id, inicio=fin))
    await db.flush()


async def cerrar_olvidadas(db: AsyncSession, horas: int = 14) -> int:
    n = 0
    for j in (await db.execute(select(PerJornada).where(PerJornada.estado.in_(("ACTIVA", "PAUSADA"))))).scalars().all():
        if (ahora() - j.inicio).total_seconds() > horas * 3600:
            await cerrar(db, j, auto=True)
            n += 1
    return n


# ── Métricas ─────────────────────────────────────────────────────────────────

async def metricas(db: AsyncSession, jornadas: List[PerJornada]) -> Dict[int, dict]:
    from app.infrastructure.models.wms import WMSTarea
    if not jornadas:
        return {}
    ids = [j.id for j in jornadas]
    pausas = (await db.execute(select(PerJornadaPausa).where(PerJornadaPausa.jornada_id.in_(ids)))).scalars().all()
    tramos = (await db.execute(select(PerJornadaTramo).where(PerJornadaTramo.jornada_id.in_(ids)))).scalars().all()
    tareas = (await db.execute(select(WMSTarea).where(WMSTarea.jornada_id.in_(ids)))).scalars().all()
    est = {e.id: e for e in (await db.execute(select(PerEstacion).where(
        PerEstacion.id.in_({t.estacion_id for t in tramos if t.estacion_id} or {0})))).scalars()}
    out, t0 = {}, ahora()
    for j in jornadas:
        fin = j.fin or t0
        total = max(0.0, (fin - j.inicio).total_seconds() / 60)
        ps = [p for p in pausas if p.jornada_id == j.id]
        en_pausa = sum(((p.fin or t0) - p.inicio).total_seconds() / 60 for p in ps)
        ts = [t for t in tareas if t.jornada_id == j.id]
        hechas = [t for t in ts if t.estado == "COMPLETADA"]
        productivo = sum(((t.terminada_en or t0) - t.iniciada_en).total_seconds() / 60
                         for t in ts if t.iniciada_en and t.estado in ("COMPLETADA", "EN_CURSO"))
        disponible = max(0.0, total - en_pausa)
        por_tipo: Dict[str, int] = {}
        for t in hechas:
            por_tipo[t.tipo] = por_tipo.get(t.tipo, 0) + 1
        out[j.id] = {
            "minutos": round(total, 1), "pausa_min": round(en_pausa, 1), "productivo_min": round(productivo, 1),
            "sin_tarea_min": round(max(0.0, disponible - productivo), 1),
            "utilizacion_pct": round(productivo / disponible * 100, 1) if disponible > 0 else None,
            "tareas": len(hechas), "por_tipo": por_tipo,
            "tareas_hora": round(len(hechas) / (disponible / 60), 2) if disponible >= 1 else None,
            "pausas": [{"motivo": p.motivo, "inicio": p.inicio.isoformat(), "fin": p.fin.isoformat() if p.fin else None,
                        "min": round(((p.fin or t0) - p.inicio).total_seconds() / 60, 1)} for p in ps],
            "tramos": [{"estacion_id": tr.estacion_id, "estacion": est[tr.estacion_id].nombre if tr.estacion_id in est else None,
                        "inicio": tr.inicio.isoformat(), "fin": tr.fin.isoformat() if tr.fin else None,
                        "min": round(((tr.fin or t0) - tr.inicio).total_seconds() / 60, 1)}
                       for tr in sorted((x for x in tramos if x.jornada_id == j.id), key=lambda x: x.inicio)],
        }
    return out
