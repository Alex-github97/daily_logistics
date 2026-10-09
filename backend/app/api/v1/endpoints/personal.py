"""
WFM · Personal operativo. Prefijo: /personal

- Estaciones de trabajo (qué tareas reciben y en qué zonas).
- Personas: perfil operativo, carné para el kiosco y habilidades.
- Programación: quién va a qué estación cada día.
- Jornadas: entrada (en su dispositivo o con carné en el kiosco), pausas,
  cambio de estación por el supervisor y salida.
- Tablero en vivo, «mis tareas» y productividad (por persona y por estación).
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import personal as per
from app.core import wms_tareas_dirigidas as wtd
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.personal import (
    FUNCIONES_WMS, HABILIDADES, PerEstacion, PerJornada, PerPerfil, PerProgramacion,
)
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import WMSAlmacen, WMSPickingTarea, WMSTarea, WMSZona

router = APIRouter(prefix="/personal", tags=["wfm-personal"])
TIPOS_ESTACION = ("RECEPCION", "UBICACION", "REABASTECIMIENTO", "PICKING", "EMPAQUE", "DESPACHO", "CONTEO", "CAJA",
                  "CONDUCCION", "GENERAL")
TURNOS = ("DIA", "MANANA", "TARDE", "NOCHE")


def _nombre(u: Optional[Usuario]) -> Optional[str]:
    return f"{u.nombre} {u.apellido or ''}".strip() if u else None


async def _usuarios(db, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u for u in (await db.execute(select(Usuario).where(Usuario.id.in_(ids)))).scalars()}


async def _tareas(db, tareas):
    from app.api.v1.endpoints.wms_trazable import _tareas_dict
    return await _tareas_dict(db, tareas)


# ═════════════════════════════════════════════════════════════════════════════
# Estaciones
# ═════════════════════════════════════════════════════════════════════════════
class EstacionIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=120)
    tipo: str = "GENERAL"
    almacen_id: Optional[int] = None
    funciones: List[str] = []
    zonas: List[int] = []
    requiere_montacargas: bool = False
    capacidad: int = Field(1, ge=1, le=200)
    color: Optional[str] = Field(None, max_length=9)
    activo: bool = True
    notas: Optional[str] = None


def _est_dict(e: PerEstacion) -> dict:
    return {k: getattr(e, k) for k in ("id", "codigo", "nombre", "tipo", "almacen_id", "funciones", "zonas",
                                       "requiere_montacargas", "capacidad", "color", "activo", "notas")} | {
        "funciones": e.funciones or per.FUNCIONES_DE_TIPO.get(e.tipo, []), "zonas": e.zonas or []}


async def _validar_estacion(db, d: EstacionIn, eid: Optional[int] = None) -> None:
    if d.tipo not in TIPOS_ESTACION:
        raise HTTPException(422, f"Tipo de estación inválido: use {', '.join(TIPOS_ESTACION)}.")
    malas = [f for f in d.funciones if f not in FUNCIONES_WMS]
    if malas:
        raise HTTPException(422, f"Funciones desconocidas: {', '.join(malas)}.")
    if d.almacen_id and await db.get(WMSAlmacen, d.almacen_id) is None:
        raise HTTPException(404, "Almacén no encontrado.")
    if d.zonas:
        if not d.almacen_id:
            raise HTTPException(422, "Para limitar zonas, indique el almacén de la estación.")
        ok = set((await db.execute(select(WMSZona.id).where(WMSZona.almacen_id == d.almacen_id,
                                                            WMSZona.id.in_(d.zonas)))).scalars())
        if ok != set(d.zonas):
            raise HTTPException(422, "Alguna zona no es de ese almacén.")
    dup = (await db.execute(select(PerEstacion.id).where(func.upper(PerEstacion.codigo) == d.codigo.strip().upper(),
                                                         PerEstacion.id != (eid or 0)))).first()
    if dup:
        raise HTTPException(409, f"Ya existe una estación con código {d.codigo}.")


@router.get("/estaciones")
async def listar_estaciones(almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(PerEstacion)
    if almacen_id:
        q = q.where((PerEstacion.almacen_id == almacen_id) | (PerEstacion.almacen_id.is_(None)))
    return [_est_dict(e) for e in (await db.execute(q.order_by(PerEstacion.codigo))).scalars()]


@router.post("/estaciones", status_code=201)
async def crear_estacion(d: EstacionIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    await _validar_estacion(db, d)
    e = PerEstacion(**(d.model_dump() | {"codigo": d.codigo.strip().upper(), "funciones": d.funciones or None,
                                         "zonas": d.zonas or None}))
    db.add(e)
    await db.flush()
    return _est_dict(e)


@router.put("/estaciones/{eid}")
async def editar_estacion(eid: int, d: EstacionIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    e = await db.get(PerEstacion, eid)
    if e is None:
        raise HTTPException(404, "Estación no encontrada.")
    await _validar_estacion(db, d, eid)
    for k, v in (d.model_dump() | {"codigo": d.codigo.strip().upper(), "funciones": d.funciones or None,
                                   "zonas": d.zonas or None}).items():
        setattr(e, k, v)
    await db.flush()
    return _est_dict(e)


@router.delete("/estaciones/{eid}", status_code=204)
async def borrar_estacion(eid: int, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    e = await db.get(PerEstacion, eid)
    if e is None:
        raise HTTPException(404, "Estación no encontrada.")
    en_uso = (await db.execute(select(PerJornada.id).where(PerJornada.estacion_id == eid,
                                                           PerJornada.estado.in_(("ACTIVA", "PAUSADA"))))).first()
    if en_uso:
        raise HTTPException(409, "Hay personas trabajando en esta estación: muévalas o desactívela.")
    usada = (await db.execute(select(PerJornada.id).where(PerJornada.estacion_id == eid))).first()
    if usada:          # tiene historia: se desactiva para no perder la trazabilidad
        e.activo = False
        return
    await db.delete(e)


# ═════════════════════════════════════════════════════════════════════════════
# Personas (perfil operativo)
# ═════════════════════════════════════════════════════════════════════════════
class PerfilIn(BaseModel):
    carne: Optional[str] = Field(None, max_length=40)
    cargo: Optional[str] = Field(None, max_length=80)
    habilidades: List[str] = []
    almacen_id: Optional[int] = None
    estacion_id: Optional[int] = None
    activo: bool = True


@router.get("/personas")
async def listar_personas(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    usuarios = (await db.execute(select(Usuario).where(Usuario.activo.isnot(False)).order_by(Usuario.nombre))).scalars().all()
    perfiles = {p.usuario_id: p for p in (await db.execute(select(PerPerfil))).scalars()}
    abiertas = {j.usuario_id: j for j in (await db.execute(select(PerJornada).where(
        PerJornada.estado.in_(("ACTIVA", "PAUSADA"))))).scalars()}
    out = []
    for u in usuarios:
        p = perfiles.get(u.id)
        j = abiertas.get(u.id)
        out.append({"usuario_id": u.id, "nombre": _nombre(u), "username": u.username, "rol": u.rol,
                    "carne": p.carne if p else None, "cargo": (p.cargo if p else None) or u.cargo,
                    "habilidades": (p.habilidades or []) if p else [], "almacen_id": p.almacen_id if p else None,
                    "estacion_id": p.estacion_id if p else None, "activo": p.activo if p else True,
                    "con_perfil": p is not None, "jornada": {"id": j.id, "estado": j.estado, "estacion_id": j.estacion_id} if j else None})
    return out


@router.put("/personas/{uid}")
async def guardar_persona(uid: int, d: PerfilIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    if await db.get(Usuario, uid) is None:
        raise HTTPException(404, "Usuario no encontrado.")
    malas = [h for h in d.habilidades if h not in HABILIDADES]
    if malas:
        raise HTTPException(422, f"Habilidades desconocidas: {', '.join(malas)}.")
    carne = (d.carne or "").strip().upper() or None
    if carne:
        dup = (await db.execute(select(PerPerfil.id).where(PerPerfil.carne == carne, PerPerfil.usuario_id != uid))).first()
        if dup:
            raise HTTPException(409, f"El carné {carne} ya es de otra persona.")
    if d.estacion_id and await db.get(PerEstacion, d.estacion_id) is None:
        raise HTTPException(404, "Estación no encontrada.")
    p = await per.perfil(db, uid)
    if p is None:
        p = PerPerfil(usuario_id=uid)
        db.add(p)
    p.carne, p.cargo, p.habilidades = carne, d.cargo, d.habilidades
    p.almacen_id, p.estacion_id, p.activo = d.almacen_id, d.estacion_id, d.activo
    await db.flush()
    return {"usuario_id": uid, "carne": p.carne}


@router.post("/personas/{uid}/carne")
async def generar_carne(uid: int, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    """Un código de carné nuevo (para imprimir y escanear en el kiosco)."""
    if await db.get(Usuario, uid) is None:
        raise HTTPException(404, "Usuario no encontrado.")
    p = await per.perfil(db, uid)
    if p is None:
        p = PerPerfil(usuario_id=uid, habilidades=[], activo=True)
        db.add(p)
    while True:
        c = f"P{uid:04d}-{secrets.token_hex(2).upper()}"
        if not (await db.execute(select(PerPerfil.id).where(PerPerfil.carne == c))).first():
            break
    p.carne = c
    await db.flush()
    return {"usuario_id": uid, "carne": c}


# ═════════════════════════════════════════════════════════════════════════════
# Programación
# ═════════════════════════════════════════════════════════════════════════════
class ProgramacionIn(BaseModel):
    fecha: date
    usuario_id: int
    estacion_id: int
    turno: str = "DIA"
    hora_inicio: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    hora_fin: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    notas: Optional[str] = Field(None, max_length=200)


@router.get("/programacion")
async def ver_programacion(fecha: date, almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
                           _=Depends(get_current_user)):
    q = select(PerProgramacion, PerEstacion).join(PerEstacion, PerEstacion.id == PerProgramacion.estacion_id).where(
        PerProgramacion.fecha == fecha)
    if almacen_id:
        q = q.where((PerEstacion.almacen_id == almacen_id) | (PerEstacion.almacen_id.is_(None)))
    filas = (await db.execute(q.order_by(PerEstacion.codigo, PerProgramacion.hora_inicio))).all()
    us = await _usuarios(db, [p.usuario_id for p, _ in filas])
    return [{"id": p.id, "fecha": p.fecha.isoformat(), "turno": p.turno, "hora_inicio": p.hora_inicio, "hora_fin": p.hora_fin,
             "usuario_id": p.usuario_id, "persona": _nombre(us.get(p.usuario_id)), "estacion_id": e.id,
             "estacion": e.nombre, "notas": p.notas} for p, e in filas]


@router.post("/programacion", status_code=201)
async def programar(d: ProgramacionIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    if d.turno not in TURNOS:
        raise HTTPException(422, f"Turno inválido: use {', '.join(TURNOS)}.")
    e = await db.get(PerEstacion, d.estacion_id)
    if e is None or not e.activo:
        raise HTTPException(404, "Estación no encontrada o inactiva.")
    if await db.get(Usuario, d.usuario_id) is None:
        raise HTTPException(404, "Persona no encontrada.")
    if e.requiere_montacargas:
        p = await per.perfil(db, d.usuario_id)
        if not p or "MONTACARGAS" not in (p.habilidades or []):
            raise HTTPException(409, f"{e.nombre} exige montacargas y la persona no tiene esa habilidad registrada.")
    prog = (await db.execute(select(PerProgramacion).where(PerProgramacion.fecha == d.fecha, PerProgramacion.usuario_id == d.usuario_id,
                                                           PerProgramacion.turno == d.turno))).scalar_one_or_none()
    if prog is None:
        prog = PerProgramacion(fecha=d.fecha, usuario_id=d.usuario_id, turno=d.turno)
        db.add(prog)
    prog.estacion_id, prog.hora_inicio, prog.hora_fin, prog.notas = d.estacion_id, d.hora_inicio, d.hora_fin, d.notas
    await db.flush()
    ocupacion = (await db.execute(select(func.count()).where(PerProgramacion.fecha == d.fecha,
                                                             PerProgramacion.estacion_id == d.estacion_id))).scalar()
    return {"id": prog.id, "aviso": f"{e.nombre} queda con {ocupacion} personas (capacidad {e.capacidad})." if ocupacion > e.capacidad else None}


@router.delete("/programacion/{pid}", status_code=204)
async def desprogramar(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    p = await db.get(PerProgramacion, pid)
    if p is None:
        raise HTTPException(404, "No encontrada.")
    await db.delete(p)


class CopiarIn(BaseModel):
    desde: date
    hacia: date


@router.post("/programacion/copiar")
async def copiar_programacion(d: CopiarIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    """Copia la programación de un día a otro (lo que ya esté en el destino se conserva)."""
    if d.desde == d.hacia:
        raise HTTPException(422, "Elija días distintos.")
    origen = (await db.execute(select(PerProgramacion).where(PerProgramacion.fecha == d.desde))).scalars().all()
    ya = {(p.usuario_id, p.turno) for p in (await db.execute(select(PerProgramacion).where(PerProgramacion.fecha == d.hacia))).scalars()}
    n = 0
    for p in origen:
        if (p.usuario_id, p.turno) in ya:
            continue
        db.add(PerProgramacion(fecha=d.hacia, usuario_id=p.usuario_id, turno=p.turno, estacion_id=p.estacion_id,
                               hora_inicio=p.hora_inicio, hora_fin=p.hora_fin, notas=p.notas))
        n += 1
    return {"copiadas": n}


# ═════════════════════════════════════════════════════════════════════════════
# Jornadas
# ═════════════════════════════════════════════════════════════════════════════
async def _jornada_dict(db, j: PerJornada, met: Optional[dict] = None, us: Optional[dict] = None,
                        estaciones: Optional[dict] = None) -> dict:
    met = met if met is not None else (await per.metricas(db, [j]))[j.id]
    us = us if us is not None else await _usuarios(db, [j.usuario_id])
    est = (estaciones or {}).get(j.estacion_id) if estaciones is not None else (await db.get(PerEstacion, j.estacion_id) if j.estacion_id else None)
    pausa = next((p for p in met["pausas"] if p["fin"] is None), None)
    return {"id": j.id, "usuario_id": j.usuario_id, "persona": _nombre(us.get(j.usuario_id)), "almacen_id": j.almacen_id,
            "estado": j.estado, "inicio": j.inicio.isoformat(), "fin": j.fin.isoformat() if j.fin else None,
            "estacion_id": j.estacion_id, "estacion": est.nombre if est else None, "estacion_codigo": est.codigo if est else None,
            "funciones": j.funciones or [], "zonas": j.zonas or [], "montacargas": j.montacargas,
            "cierre_auto": j.cierre_auto, "origen": j.origen, "pausa_actual": pausa, **met}


class IniciarIn(BaseModel):
    almacen_id: Optional[int] = None
    estacion_id: Optional[int] = None
    funciones: List[str] = []
    zonas: List[int] = []
    montacargas: bool = False


@router.get("/mi-jornada")
async def mi_jornada(db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    j = await per.jornada_abierta(db, yo.id)
    prog = await per.programado(db, yo.id)
    p = await per.perfil(db, yo.id)
    est_prog = await db.get(PerEstacion, prog.estacion_id) if prog else None
    return {"jornada": await _jornada_dict(db, j) if j else None,
            "programado": {"estacion_id": prog.estacion_id, "estacion": est_prog.nombre if est_prog else None,
                           "turno": prog.turno, "hora_inicio": prog.hora_inicio, "hora_fin": prog.hora_fin} if prog else None,
            "perfil": {"carne": p.carne, "habilidades": p.habilidades or [], "estacion_id": p.estacion_id,
                       "almacen_id": p.almacen_id} if p else None}


@router.get("/mis-tareas")
async def mis_tareas(db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Lo que la persona tiene en sus manos y lo que espera en la cola de su estación."""
    j = await per.jornada_abierta(db, yo.id)
    actual = await wtd.tarea_actual(db, yo.id)
    en_cola = 0
    if j:
        a = await per.alcance(db, j)
        if a["funciones"]:
            en_cola = (await db.execute(select(func.count()).where(
                WMSTarea.almacen_id == a["almacen_id"], WMSTarea.estado == "PENDIENTE",
                WMSTarea.tipo.in_(a["funciones"])))).scalar() or 0
    picking = (await db.execute(select(WMSPickingTarea).where(WMSPickingTarea.operario_id == yo.id,
                                                              WMSPickingTarea.estado.in_(("PENDIENTE", "EN_PROGRESO")))
                                .order_by(WMSPickingTarea.id))).scalars().all()
    hoy = datetime.combine(date.today(), time.min).astimezone(timezone.utc)
    hechas = (await db.execute(select(func.count()).where(WMSTarea.operario_id == yo.id, WMSTarea.estado == "COMPLETADA",
                                                          WMSTarea.terminada_en >= hoy))).scalar() or 0
    return {"actual": (await _tareas(db, [actual]))[0] if actual else None, "en_cola": en_cola, "hechas_hoy": hechas,
            "picking": [{"id": t.id, "orden_id": t.orden_id, "tipo": t.tipo, "estado": t.estado, "items": t.items_pickeados,
                         "asignada": t.fecha_asignacion.isoformat() if t.fecha_asignacion else None} for t in picking]}


@router.post("/jornadas/iniciar", status_code=201)
async def iniciar(d: IniciarIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    j = await per.iniciar(db, yo.id, almacen_id=d.almacen_id, estacion_id=d.estacion_id, funciones=d.funciones,
                          zonas=d.zonas, montacargas=d.montacargas, origen="APP")
    return await _jornada_dict(db, j)


class PausaIn(BaseModel):
    motivo: str


@router.post("/jornadas/pausar")
async def pausar(d: PausaIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    j = await per.jornada_abierta(db, yo.id)
    if j is None:
        raise HTTPException(409, "No tiene una jornada abierta.")
    await per.pausar(db, j, d.motivo)
    return await _jornada_dict(db, j)


@router.post("/jornadas/reanudar")
async def reanudar(db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    j = await per.jornada_abierta(db, yo.id)
    if j is None:
        raise HTTPException(409, "No tiene una jornada abierta.")
    await per.reanudar(db, j)
    return await _jornada_dict(db, j)


@router.post("/jornadas/cerrar")
async def cerrar(db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    j = await per.jornada_abierta(db, yo.id)
    if j is None:
        raise HTTPException(409, "No tiene una jornada abierta.")
    await per.cerrar(db, j)
    return await _jornada_dict(db, j)


@router.post("/jornadas/{jid}/cerrar")
async def cerrar_de_otro(jid: int, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    """El supervisor cierra la jornada de alguien que se fue sin marcar la salida."""
    j = await db.get(PerJornada, jid)
    if j is None or j.estado == "CERRADA":
        raise HTTPException(409, "La jornada no está abierta.")
    await per.cerrar(db, j, forzar=True)
    return await _jornada_dict(db, j)


class EstacionDeJornadaIn(BaseModel):
    estacion_id: Optional[int] = None


@router.post("/jornadas/{jid}/estacion")
async def mover_de_estacion(jid: int, d: EstacionDeJornadaIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    j = await db.get(PerJornada, jid)
    if j is None:
        raise HTTPException(404, "Jornada no encontrada.")
    await per.mover_estacion(db, j, d.estacion_id)
    return await _jornada_dict(db, j)


async def _jornadas(db, almacen_id, desde, hasta, abiertas) -> List[PerJornada]:
    q = select(PerJornada)
    if almacen_id:
        q = q.where(PerJornada.almacen_id == almacen_id)
    if abiertas:
        q = q.where(PerJornada.estado.in_(("ACTIVA", "PAUSADA")))
    else:
        d0 = datetime.combine(desde or (date.today() - timedelta(days=7)), time.min).astimezone(timezone.utc)
        d1 = datetime.combine((hasta or date.today()) + timedelta(days=1), time.min).astimezone(timezone.utc)
        q = q.where(PerJornada.inicio >= d0, PerJornada.inicio < d1)
    return (await db.execute(q.order_by(PerJornada.inicio.desc()).limit(1000))).scalars().all()


@router.get("/jornadas")
async def listar_jornadas(almacen_id: Optional[int] = None, desde: Optional[date] = None, hasta: Optional[date] = None,
                          abiertas: bool = False, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    js = await _jornadas(db, almacen_id, desde, hasta, abiertas)
    met = await per.metricas(db, js)
    us = await _usuarios(db, [j.usuario_id for j in js])
    est = {e.id: e for e in (await db.execute(select(PerEstacion))).scalars()}
    actuales = {t.operario_id: t for t in (await db.execute(select(WMSTarea).where(
        WMSTarea.operario_id.in_([j.usuario_id for j in js] or [0]), WMSTarea.estado.in_(("ASIGNADA", "EN_CURSO"))))).scalars()}
    td = {t["id"]: t for t in await _tareas(db, list(actuales.values()))}
    return [await _jornada_dict(db, j, met[j.id], us, est) | {
        "tarea": td.get(actuales[j.usuario_id].id) if j.estado != "CERRADA" and j.usuario_id in actuales else None} for j in js]


@router.get("/productividad")
async def productividad(almacen_id: Optional[int] = None, desde: Optional[date] = None, hasta: Optional[date] = None,
                        db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Por persona y por estación en el periodo."""
    js = await _jornadas(db, almacen_id, desde, hasta, False)
    met = await per.metricas(db, js)
    us = await _usuarios(db, [j.usuario_id for j in js])
    personas, estaciones = {}, {}
    for j in js:
        m = met[j.id]
        r = personas.setdefault(j.usuario_id, {"usuario_id": j.usuario_id, "persona": _nombre(us.get(j.usuario_id)),
                                               "jornadas": 0, "minutos": 0.0, "pausa_min": 0.0, "productivo_min": 0.0,
                                               "tareas": 0, "por_tipo": {}})
        r["jornadas"] += 1
        for k in ("minutos", "pausa_min", "productivo_min"):
            r[k] += m[k]
        r["tareas"] += m["tareas"]
        for k, v in m["por_tipo"].items():
            r["por_tipo"][k] = r["por_tipo"].get(k, 0) + v
        for tr in m["tramos"]:
            e = estaciones.setdefault(tr["estacion_id"] or 0, {"estacion_id": tr["estacion_id"], "estacion": tr["estacion"] or "Sin estación",
                                                                 "minutos": 0.0, "personas": set()})
            e["minutos"] += tr["min"]
            e["personas"].add(j.usuario_id)
    for r in personas.values():
        disp = r["minutos"] - r["pausa_min"]
        r["utilizacion_pct"] = round(r["productivo_min"] / disp * 100, 1) if disp > 0 else None
        r["tareas_hora"] = round(r["tareas"] / (disp / 60), 2) if disp >= 1 else None
        r["horas"] = round(r["minutos"] / 60, 2)
        for k in ("minutos", "pausa_min", "productivo_min"):
            r[k] = round(r[k], 1)
    return {"personas": sorted(personas.values(), key=lambda r: -r["tareas"]),
            "estaciones": sorted(({**e, "horas": round(e["minutos"] / 60, 2), "personas": len(e["personas"])}
                                  for e in estaciones.values()), key=lambda e: -e["minutos"])}


# ═════════════════════════════════════════════════════════════════════════════
# Kiosco (marcar con el carné) y tablero en vivo
# ═════════════════════════════════════════════════════════════════════════════
class MarcarIn(BaseModel):
    carne: str = Field(min_length=1, max_length=40)


@router.post("/kiosco/marcar")
async def marcar(d: MarcarIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    """El equipo del kiosco (con sesión de supervisor) lee el carné: si la persona
    no tiene jornada abierta, marca la entrada; si la tiene, la salida."""
    p = (await db.execute(select(PerPerfil).where(PerPerfil.carne == d.carne.strip().upper()))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Carné no registrado.")
    if not p.activo:
        raise HTTPException(409, "La persona está inactiva en Personal.")
    u = await db.get(Usuario, p.usuario_id)
    j = await per.jornada_abierta(db, p.usuario_id)
    if j is None:
        j = await per.iniciar(db, p.usuario_id, origen="KIOSCO")
        dj = await _jornada_dict(db, j)
        return {"accion": "ENTRADA", "persona": _nombre(u), "estacion": dj["estacion"], "jornada": dj}
    await per.cerrar(db, j, forzar=True)
    dj = await _jornada_dict(db, j)
    return {"accion": "SALIDA", "persona": _nombre(u), "estacion": dj["estacion"], "jornada": dj}


@router.get("/tablero")
async def tablero(almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Cada estación con quién está programado hoy, quién está trabajando y en
    qué; las personas en jornada sin estación y las programadas que no llegan."""
    hoy = date.today()
    q = select(PerEstacion).where(PerEstacion.activo.is_(True))
    if almacen_id:
        q = q.where((PerEstacion.almacen_id == almacen_id) | (PerEstacion.almacen_id.is_(None)))
    estaciones = (await db.execute(q.order_by(PerEstacion.codigo))).scalars().all()
    progs = (await db.execute(select(PerProgramacion).where(PerProgramacion.fecha == hoy))).scalars().all()
    abiertas = await _jornadas(db, almacen_id, None, None, True)
    jd = {j["usuario_id"]: j for j in await listar_jornadas(almacen_id, None, None, True, db)}
    us = await _usuarios(db, [p.usuario_id for p in progs] + [j.usuario_id for j in abiertas])
    presentes = {j.usuario_id for j in abiertas}
    cola = dict((await db.execute(select(WMSTarea.tipo, func.count()).where(
        WMSTarea.estado == "PENDIENTE", *( [WMSTarea.almacen_id == almacen_id] if almacen_id else [])).group_by(WMSTarea.tipo))).all())
    out = []
    for e in estaciones:
        funciones = e.funciones or per.FUNCIONES_DE_TIPO.get(e.tipo, [])
        out.append({**_est_dict(e),
                    "programados": [{"usuario_id": p.usuario_id, "persona": _nombre(us.get(p.usuario_id)), "turno": p.turno,
                                     "hora_inicio": p.hora_inicio, "hora_fin": p.hora_fin, "presente": p.usuario_id in presentes,
                                     "programacion_id": p.id} for p in progs if p.estacion_id == e.id],
                    "trabajando": [jd[j.usuario_id] for j in abiertas if j.estacion_id == e.id and j.usuario_id in jd],
                    "en_cola": sum(cola.get(f, 0) for f in funciones if f in FUNCIONES_WMS)})
    sin_estacion = [jd[j.usuario_id] for j in abiertas if not j.estacion_id and j.usuario_id in jd]
    ausentes = [{"usuario_id": p.usuario_id, "persona": _nombre(us.get(p.usuario_id)), "estacion_id": p.estacion_id,
                 "turno": p.turno, "hora_inicio": p.hora_inicio} for p in progs if p.usuario_id not in presentes
                and any(e.id == p.estacion_id for e in estaciones)]
    return {"estaciones": out, "sin_estacion": sin_estacion, "ausentes": ausentes,
            "resumen": {"programados": len({p.usuario_id for p in progs if any(e.id == p.estacion_id for e in estaciones)}),
                        "presentes": len(abiertas), "en_pausa": sum(1 for j in abiertas if j.estado == "PAUSADA"),
                        "con_tarea": sum(1 for j in jd.values() if j.get("tarea")), "ausentes": len(ausentes),
                        "en_cola": sum(cola.values())}}
