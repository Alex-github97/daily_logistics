"""
Tablero del CMMS, sobre datos reales.

La pantalla del tablero mostraba constantes escritas en el código: 127 activos,
una tabla de confiabilidad inventada y alertas que no correspondían a nada. Esto
la alimenta de la base.

SOBRE LAS MÉTRICAS DE CONFIABILIDAD
MTBF y MTTR se calculan de las órdenes, no se estiman:

  MTTR  promedio de (fecha_fin − fecha_inicio) de las órdenes marcadas como
        falla y ya cerradas. Es tiempo de reparación real.

  MTBF  por activo, el tiempo entre fallas consecutivas: (última − primera) /
        (número de fallas − 1). Se promedia entre los activos que tengan al
        menos dos fallas, porque con una sola no hay «entre».

Ambas se devuelven con el número de casos sobre el que se calcularon. Un MTBF
sacado de tres órdenes no significa lo mismo que uno sacado de trescientas, y
esconder ese detalle es la forma más fácil de que alguien tome una decisión
sobre un promedio que no aguanta.

Cuando no hay datos suficientes se devuelve `null`, nunca un cero: un cero se
lee como «se daña todo el tiempo» y sería exactamente lo contrario de la verdad.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.infrastructure.models.eam import (
    EAMActivo, EAMOrdenTrabajo, EAMPlanActivo, EAMPlanMantenimiento,
    EAMGarantia, EAMCalibracion,
)
from app.infrastructure.models.lubricacion import (
    LubeMuestra, LubeCompartimento,
)

router = APIRouter(prefix="/eam", tags=["CMMS/EAM"])

ESTADOS_ABIERTA = ("PENDIENTE", "ASIGNADA", "EN_EJECUCION", "EN_ESPERA_REPUESTOS")


def _horas(inicio: Optional[datetime], fin: Optional[datetime]) -> Optional[float]:
    if not inicio or not fin or fin < inicio:
        return None
    return (fin - inicio).total_seconds() / 3600


@router.get("/dashboard/completo")
async def tablero(
    dias: int = Query(90, ge=7, le=1095),
    tipo_activo: Optional[str] = None,
    marca: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ahora = datetime.utcnow()
    desde = ahora - timedelta(days=dias)

    def filtro_activo(q):
        if tipo_activo and tipo_activo != "Todos":
            q = q.where(EAMActivo.tipo_activo == tipo_activo)
        if marca:
            q = q.where(EAMActivo.marca == marca)
        return q

    # ── Activos ──────────────────────────────────────────────────────────────
    r = await db.execute(filtro_activo(
        select(EAMActivo.estado, func.count(EAMActivo.id))
        .where(EAMActivo.activo.is_(True)).group_by(EAMActivo.estado)))
    por_estado = {e or "SIN_ESTADO": c for e, c in r.all()}
    total_activos = sum(por_estado.values())
    operativos = por_estado.get("OPERATIVO", 0)
    disponibilidad = round(operativos / total_activos * 100, 1) if total_activos else None

    r = await db.execute(filtro_activo(
        select(EAMActivo.tipo_activo, func.count(EAMActivo.id),
               func.sum(case((EAMActivo.estado == "OPERATIVO", 1), else_=0)))
        .where(EAMActivo.activo.is_(True)).group_by(EAMActivo.tipo_activo)
        .order_by(func.count(EAMActivo.id).desc())))
    por_tipo = [{"etiqueta": t or "Sin tipo", "total": c, "operativos": int(o or 0),
                 "disponibilidad": round(int(o or 0) / c * 100, 1) if c else None}
                for t, c, o in r.all()]

    # ── Órdenes de trabajo ───────────────────────────────────────────────────
    base_ot = select(EAMOrdenTrabajo).join(EAMActivo, EAMActivo.id == EAMOrdenTrabajo.activo_id)
    if tipo_activo and tipo_activo != "Todos":
        base_ot = base_ot.where(EAMActivo.tipo_activo == tipo_activo)
    if marca:
        base_ot = base_ot.where(EAMActivo.marca == marca)

    r = await db.execute(base_ot.where(EAMOrdenTrabajo.estado.in_(ESTADOS_ABIERTA)))
    abiertas = list(r.scalars().all())

    conteo_estado: Dict[str, int] = defaultdict(int)
    conteo_prioridad: Dict[str, int] = defaultdict(int)
    vencidas = 0
    for ot in abiertas:
        conteo_estado[ot.estado or "SIN_ESTADO"] += 1
        conteo_prioridad[ot.prioridad or "SIN_PRIORIDAD"] += 1
        if ot.fecha_requerida and ot.fecha_requerida < ahora:
            vencidas += 1

    r = await db.execute(base_ot.where(and_(
        EAMOrdenTrabajo.estado == "COMPLETADA", EAMOrdenTrabajo.fecha_fin >= desde)))
    cerradas = list(r.scalars().all())

    costo_periodo = sum(ot.costo_total or 0 for ot in cerradas)
    costo_fallas = sum(ot.costo_total or 0 for ot in cerradas if ot.es_falla)

    # ── Confiabilidad ────────────────────────────────────────────────────────
    # MTTR: solo fallas cerradas con las dos fechas puestas.
    duraciones = [h for h in (_horas(ot.fecha_inicio, ot.fecha_fin)
                              for ot in cerradas if ot.es_falla) if h is not None]
    mttr = round(sum(duraciones) / len(duraciones), 1) if duraciones else None

    # MTBF: por activo, el tiempo entre fallas consecutivas.
    r = await db.execute(base_ot.where(and_(
        EAMOrdenTrabajo.es_falla.is_(True),
        EAMOrdenTrabajo.fecha_inicio.isnot(None),
        EAMOrdenTrabajo.fecha_inicio >= desde)))
    fallas_por_activo: Dict[int, List[datetime]] = defaultdict(list)
    for ot in r.scalars().all():
        fallas_por_activo[ot.activo_id].append(ot.fecha_inicio)

    intervalos: List[float] = []
    for fechas in fallas_por_activo.values():
        if len(fechas) < 2:
            continue
        fechas.sort()
        intervalos.append((fechas[-1] - fechas[0]).total_seconds() / 3600 / (len(fechas) - 1))
    mtbf = round(sum(intervalos) / len(intervalos), 1) if intervalos else None

    # ── Cumplimiento del plan de mantenimiento ───────────────────────────────
    r = await db.execute(
        select(func.count(EAMPlanActivo.id),
               func.sum(case((and_(EAMPlanActivo.proxima_fecha.isnot(None),
                                   EAMPlanActivo.proxima_fecha < ahora), 1), else_=0)))
        .join(EAMActivo, EAMActivo.id == EAMPlanActivo.activo_id)
        .where(EAMActivo.activo.is_(True)))
    total_rutinas, rutinas_vencidas = r.one()
    total_rutinas = int(total_rutinas or 0)
    rutinas_vencidas = int(rutinas_vencidas or 0)
    cumplimiento_pm = (round((total_rutinas - rutinas_vencidas) / total_rutinas * 100, 1)
                       if total_rutinas else None)

    # ── Tendencia mensual ────────────────────────────────────────────────────
    meses: Dict[str, Dict[str, Any]] = {}
    for ot in cerradas:
        if not ot.fecha_fin:
            continue
        clave = ot.fecha_fin.strftime("%Y-%m")
        m = meses.setdefault(clave, {"mes": clave, "ordenes": 0, "fallas": 0, "costo": 0.0})
        m["ordenes"] += 1
        m["fallas"] += 1 if ot.es_falla else 0
        m["costo"] += ot.costo_total or 0
    tendencia = [meses[k] for k in sorted(meses)]

    # ── Por marca y por línea ────────────────────────────────────────────────
    async def _agrupar(campo):
        q = (select(campo, func.count(EAMOrdenTrabajo.id),
                    func.sum(case((EAMOrdenTrabajo.es_falla.is_(True), 1), else_=0)),
                    func.sum(func.coalesce(EAMOrdenTrabajo.costo_total, 0)))
             .join(EAMOrdenTrabajo, EAMOrdenTrabajo.activo_id == EAMActivo.id)
             .where(and_(EAMOrdenTrabajo.fecha_fin >= desde, campo.isnot(None)))
             .group_by(campo).order_by(func.count(EAMOrdenTrabajo.id).desc()).limit(12))
        return [{"etiqueta": n, "ordenes": c, "fallas": int(f or 0), "costo": float(k or 0)}
                for n, c, f, k in (await db.execute(q)).all()]

    por_marca = await _agrupar(EAMActivo.marca)
    por_linea = await _agrupar(EAMActivo.linea)

    # ── Alertas críticas, todas reales ───────────────────────────────────────
    alertas: List[Dict[str, Any]] = []

    for ot in sorted([o for o in abiertas if o.fecha_requerida and o.fecha_requerida < ahora],
                     key=lambda o: o.fecha_requerida)[:8]:
        dias_v = (ahora - ot.fecha_requerida).days
        alertas.append({
            "tipo": "OT_VENCIDA", "referencia": ot.numero,
            "titulo": f"Orden {ot.numero} vencida hace {dias_v} {'día' if dias_v == 1 else 'días'}",
            "detalle": (ot.descripcion or "")[:140],
            "severidad": "CRITICA" if dias_v > 7 or ot.prioridad == "CRITICA" else "ALTA",
            "enlace": f"/eam/ordenes-trabajo?numero={ot.numero}",
        })

    r = await db.execute(
        select(LubeMuestra, EAMActivo.codigo, LubeCompartimento.nombre)
        .join(LubeCompartimento, LubeCompartimento.id == LubeMuestra.compartimento_id)
        .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
        .where(LubeMuestra.severidad.in_(("CRITICO", "ACCION_INMEDIATA")))
        .order_by(LubeMuestra.fecha_toma.desc()).limit(6))
    for m, codigo, comp in r.all():
        alertas.append({
            "tipo": "LUBRICACION", "referencia": m.numero,
            "titulo": f"Análisis de aceite {'con acción inmediata' if m.severidad == 'ACCION_INMEDIATA' else 'crítico'} en {codigo}",
            "detalle": f"{comp} · muestra {m.numero}",
            "severidad": "CRITICA" if m.severidad == "ACCION_INMEDIATA" else "ALTA",
            "enlace": "/eam/lubricacion",
        })

    r = await db.execute(select(func.count(EAMCalibracion.id))
                         .where(EAMCalibracion.estado == "VENCIDA"))
    calib_vencidas = r.scalar() or 0
    if calib_vencidas:
        alertas.append({
            "tipo": "CALIBRACION", "referencia": None,
            "titulo": f"{calib_vencidas} {'calibración vencida' if calib_vencidas == 1 else 'calibraciones vencidas'}",
            "detalle": "Equipos midiendo fuera de su certificación vigente",
            "severidad": "ALTA", "enlace": "/eam/confiabilidad",
        })

    from app.core.parametros_eam import leer_parametros_eam
    aviso_g = int((await leer_parametros_eam(db))['garantia_dias_aviso'])
    r = await db.execute(select(func.count(EAMGarantia.id)).where(and_(
        EAMGarantia.estado == "VIGENTE",
        EAMGarantia.fecha_fin <= (ahora + timedelta(days=aviso_g)).date())))
    garantias_por_vencer = r.scalar() or 0
    if garantias_por_vencer:
        alertas.append({
            "tipo": "GARANTIA", "referencia": None,
            "titulo": f"{garantias_por_vencer} {'garantía vence' if garantias_por_vencer == 1 else 'garantías vencen'} en {aviso_g} días",
            "detalle": "Conviene revisar pendientes antes de que expiren",
            "severidad": "MEDIA", "enlace": "/eam/garantias",
        })

    if rutinas_vencidas:
        alertas.append({
            "tipo": "PLAN", "referencia": None,
            "titulo": f"{rutinas_vencidas} {'rutina vencida' if rutinas_vencidas == 1 else 'rutinas de mantenimiento vencidas'}",
            "detalle": "Mantenimiento preventivo pasado de fecha",
            "severidad": "ALTA" if rutinas_vencidas > 5 else "MEDIA",
            "enlace": "/eam/planes",
        })

    orden_sev = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2}
    alertas.sort(key=lambda a: orden_sev.get(a["severidad"], 9))

    return {
        "periodo_dias": dias,
        "activos": {
            "total": total_activos, "operativos": operativos,
            "en_mantenimiento": por_estado.get("EN_MANTENIMIENTO", 0),
            "fuera_servicio": por_estado.get("FUERA_SERVICIO", 0),
            "disponibilidad_pct": disponibilidad,
            "por_estado": dict(por_estado), "por_tipo": por_tipo,
        },
        "ordenes": {
            "abiertas": len(abiertas), "vencidas": vencidas,
            "cerradas_periodo": len(cerradas),
            "por_estado": dict(conteo_estado), "por_prioridad": dict(conteo_prioridad),
            "costo_periodo": round(costo_periodo, 2),
            "costo_fallas": round(costo_fallas, 2),
        },
        "confiabilidad": {
            # Se devuelve la muestra junto al número: un MTBF de tres órdenes
            # no significa lo mismo que uno de trescientas.
            "mttr_horas": mttr, "mttr_casos": len(duraciones),
            "mtbf_horas": mtbf, "mtbf_activos": len(intervalos),
            "cumplimiento_pm_pct": cumplimiento_pm,
            "rutinas_totales": total_rutinas, "rutinas_vencidas": rutinas_vencidas,
        },
        "tendencia": tendencia,
        "por_marca": por_marca,
        "por_linea": por_linea,
        "alertas": alertas,
    }


@router.get("/dashboard/filtros")
async def filtros(db: AsyncSession = Depends(get_db)) -> Dict[str, List[str]]:
    """Los valores que existen de verdad, para no ofrecer filtros vacíos."""
    r = await db.execute(select(EAMActivo.tipo_activo).where(and_(
        EAMActivo.activo.is_(True), EAMActivo.tipo_activo.isnot(None))).distinct())
    tipos = sorted({t for (t,) in r.all() if t})
    r = await db.execute(select(EAMActivo.marca).where(and_(
        EAMActivo.activo.is_(True), EAMActivo.marca.isnot(None))).distinct())
    marcas = sorted({m for (m,) in r.all() if m})
    return {"tipos": tipos, "marcas": marcas}
