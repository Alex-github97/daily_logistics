"""
Analítica de planta: control estadístico, pérdidas de OEE, paradas y qué
explica el desperdicio.

La pantalla «IA» de MES mostraba equipos con probabilidad de falla, una
secuenciación «óptima», un scrap «óptimo» por producto y anomalías, todo
escrito a mano. Aquí cada cifra sale de las corridas, paradas, registros de OEE
e inspecciones de la planta, con los métodos de `core/analitica`.

LO QUE CADA PESTAÑA RESPONDE
  SPC          ¿el proceso cambió? (no: ¿es bueno?)
  Pérdidas     ¿dónde se van los minutos, y qué factor explica la caída?
  Paradas      ¿qué causas pesan, qué equipo se degrada, cuál parará pronto?
  Desperdicio  ¿qué operario, turno, equipo o producto desperdicia más que el
               resto, más allá del azar?
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analitica import predictivo
from app.core.analitica.estadistica import carta_imr, carta_p_laney, comparar_grupos
from app.core.analitica.weibull import ajustar_weibull, prob_falla_condicional
from app.core.database import get_db
from app.infrastructure.models.mes import (
    MESCeldaTrabajo, MESEjecucion, MESEquipo, MESInspeccion, MESLinea, MESOEERegistro,
    MESOperario, MESOrdenProduccion, MESParada, MESProducto, MESScrap,
)

router = APIRouter(prefix="/mes/analitica", tags=["MES · Analítica"])

NO_PLANEADAS = {"NO_PLANEADA", "MANTENIMIENTO"}
HORIZONTE_PARADA_DIAS = 7


def _n(f: Optional[datetime]) -> Optional[datetime]:
    """A UTC sin zona: las columnas de MES guardan zona y las comparaciones
    entre fechas con y sin zona fallan en Python."""
    if f is None:
        return None
    return f.astimezone(timezone.utc).replace(tzinfo=None) if f.tzinfo else f


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _val(e) -> Optional[str]:
    return e.value if hasattr(e, "value") else e


async def _nombres(db: AsyncSession):
    lineas = {l.id: l.nombre for l in (await db.execute(select(MESLinea))).scalars().all()}
    productos = {p.id: p.nombre for p in (await db.execute(select(MESProducto))).scalars().all()}
    operarios = {o.id: o.nombre for o in (await db.execute(select(MESOperario))).scalars().all()}
    celdas = {c.id: c.linea_id for c in (await db.execute(select(MESCeldaTrabajo))).scalars().all()}
    equipos = {e.id: e for e in (await db.execute(select(MESEquipo))).scalars().all()}
    return lineas, productos, operarios, equipos, celdas


async def _corridas(db: AsyncSession) -> List[Dict]:
    """Cada ejecución terminada con lo que produjo y desperdició."""
    lineas, productos, operarios, equipos, _ = await _nombres(db)
    filas = (await db.execute(
        select(MESEjecucion, MESOrdenProduccion)
        .join(MESOrdenProduccion, MESOrdenProduccion.id == MESEjecucion.orden_id))).all()
    salida = []
    for e, o in filas:
        total = (e.cantidad_producida or 0) + (e.cantidad_scrap or 0)
        fecha = _n(e.fecha_fin or e.fecha_inicio)
        if total <= 0 or not fecha or _val(e.estado) == "CANCELADA":
            continue
        salida.append({
            "id": e.id, "orden": o.numero, "fecha": fecha,
            "linea_id": o.linea_id, "linea": lineas.get(o.linea_id),
            "producto": productos.get(o.producto_id), "operario": operarios.get(e.operario_id),
            "equipo_id": e.equipo_id, "equipo": equipos[e.equipo_id].nombre if e.equipo_id in equipos else None,
            "turno": _val(e.turno), "producida": e.cantidad_producida or 0, "scrap": e.cantidad_scrap or 0,
            "total": total, "tasa": 100 * (e.cantidad_scrap or 0) / total,
        })
    return sorted(salida, key=lambda c: c["fecha"])


# ─── Tablero de planta ────────────────────────────────────────────────────────

@router.get("/tablero", response_model=Dict[str, Any])
async def tablero_planta(db: AsyncSession = Depends(get_db)):
    """Lo que el tablero de MES mostraba escrito a mano —líneas, órdenes
    activas, paradas en curso, alertas y tendencias— calculado de la planta.

    OEE por línea con los últimos 7 días (un solo turno es ruido); producción
    y desperdicio del día; paradas abiertas con los minutos que llevan.
    """
    from app.infrastructure.models.mes import MESPlanta, EstadoOrdenProduccionEnum, ResultadoInspeccionMESEnum
    lineas, productos, operarios, equipos, celdas = await _nombres(db)
    plantas = {p.id: p.nombre for p in (await db.execute(select(MESPlanta))).scalars().all()}
    planta_de = {l.id: plantas.get(l.planta_id) for l in (await db.execute(select(MESLinea))).scalars().all()}
    ahora = _ahora()
    hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    hace7, hace14 = ahora - timedelta(days=7), hoy - timedelta(days=13)

    regs = [r for r in (await db.execute(select(MESOEERegistro).where(MESOEERegistro.fecha >= hace14))).scalars().all()]
    corridas = [c for c in await _corridas(db) if c["fecha"] >= hace14]
    ordenes = (await db.execute(select(MESOrdenProduccion).where(MESOrdenProduccion.estado.in_(
        [EstadoOrdenProduccionEnum.LIBERADA, EstadoOrdenProduccionEnum.EN_EJECUCION])))).scalars().all()
    abiertas = (await db.execute(select(MESParada).where(MESParada.fecha_fin.is_(None)))).scalars().all()
    ejecs = {e.id: e for e in (await db.execute(select(MESEjecucion))).scalars().all()}
    orden_de = {o.id: o for o in (await db.execute(select(MESOrdenProduccion))).scalars().all()}
    insp_pend = len((await db.execute(select(MESInspeccion.id).where(
        MESInspeccion.resultado == ResultadoInspeccionMESEnum.PENDIENTE))).all())

    def linea_de_parada(p):
        if p.ejecucion_id and p.ejecucion_id in ejecs:
            o = orden_de.get(ejecs[p.ejecucion_id].orden_id)
            if o and o.linea_id:
                return o.linea_id
        e = equipos.get(p.equipo_id)
        return celdas.get(e.celda_id) if e and e.celda_id else None

    paradas = []
    for p in abiertas:
        lid = linea_de_parada(p)
        paradas.append({"id": p.id, "tipo": _val(p.tipo), "causa": p.causa, "descripcion": p.descripcion,
                        "equipo": equipos[p.equipo_id].nombre if p.equipo_id in equipos else None,
                        "linea": lineas.get(lid), "planta": planta_de.get(lid),
                        "inicio": _n(p.fecha_inicio).isoformat() if p.fecha_inicio else None,
                        "minutos": round((ahora - _n(p.fecha_inicio)).total_seconds() / 60) if p.fecha_inicio else None})
    paradas.sort(key=lambda x: -(x["minutos"] or 0))

    filas_ord = []
    for o in ordenes:
        plan = o.cantidad_planificada or 0
        fin = _n(o.fecha_fin_plan)
        filas_ord.append({"id": o.id, "numero": o.numero, "producto": productos.get(o.producto_id), "linea": lineas.get(o.linea_id),
                          "planta": planta_de.get(o.linea_id), "estado": _val(o.estado), "planificada": plan,
                          "producida": o.cantidad_producida or 0,
                          "avance_pct": round((o.cantidad_producida or 0) / plan * 100, 1) if plan else None,
                          "fin_plan": fin.date().isoformat() if fin else None, "atrasada": bool(fin and fin < ahora)})
    filas_ord.sort(key=lambda x: (not x["atrasada"], x["fin_plan"] or "9999"))

    filas_lin = []
    for lid, nombre in lineas.items():
        r7 = [r for r in regs if r.linea_id == lid and _n(r.fecha) >= hace7]
        per = _perdidas(r7) if r7 else None
        c_hoy = [c for c in corridas if c["linea_id"] == lid and c["fecha"] >= hoy]
        tot = sum(c["total"] for c in c_hoy)
        filas_lin.append({"linea_id": lid, "nombre": nombre, "planta": planta_de.get(lid),
                          "oee_7d": per["oee"] if per else None, "disponibilidad": per["disponibilidad"] if per else None,
                          "rendimiento": per["rendimiento"] if per else None, "calidad": per["calidad"] if per else None,
                          "produccion_hoy": sum(c["producida"] for c in c_hoy),
                          "scrap_hoy_pct": round(sum(c["scrap"] for c in c_hoy) / tot * 100, 2) if tot else None,
                          "ordenes_activas": sum(1 for o in ordenes if o.linea_id == lid),
                          "paradas_abiertas": sum(1 for p in paradas if p["linea"] == nombre)})

    tendencia = []
    for k in range(14):
        d0 = hace14 + timedelta(days=k)
        d1 = d0 + timedelta(days=1)
        per = _perdidas([r for r in regs if d0 <= _n(r.fecha) < d1])
        cs = [c for c in corridas if d0 <= c["fecha"] < d1]
        tot = sum(c["total"] for c in cs)
        tendencia.append({"dia": d0.date().isoformat(), "oee": per["oee"] if per else None,
                          "produccion": sum(c["producida"] for c in cs),
                          "scrap_pct": round(sum(c["scrap"] for c in cs) / tot * 100, 2) if tot else None})

    alertas = []
    for p in paradas:
        if (p["minutos"] or 0) >= 60:
            alertas.append({"nivel": "CRITICA" if p["minutos"] >= 240 else "ADVERTENCIA",
                            "titulo": f"Parada abierta hace {p['minutos'] // 60} h {p['minutos'] % 60} min",
                            "detalle": f"{p['equipo'] or p['linea'] or 'Sin equipo'}: {p['causa']}"})
    for o in filas_ord:
        if o["atrasada"]:
            alertas.append({"nivel": "ADVERTENCIA", "titulo": f"Orden {o['numero']} pasó su fecha de fin",
                            "detalle": f"{o['producto']}: {o['avance_pct'] if o['avance_pct'] is not None else '—'} % de avance, debía terminar el {o['fin_plan']}"})
    for l in filas_lin:
        if l["oee_7d"] is not None and l["oee_7d"] < 65:
            alertas.append({"nivel": "ADVERTENCIA", "titulo": f"{l['nombre']}: OEE de 7 días en {l['oee_7d']} %",
                            "detalle": "Por debajo de 65 %: revisar la pestaña de pérdidas en la analítica de planta."})
    if insp_pend:
        alertas.append({"nivel": "INFO", "titulo": f"{insp_pend} inspecciones esperan dictamen", "detalle": "Lotes que no se pueden liberar hasta decidir."})

    per7 = _perdidas([r for r in regs if _n(r.fecha) >= hace7])
    c_hoy = [c for c in corridas if c["fecha"] >= hoy]
    tot_hoy = sum(c["total"] for c in c_hoy)
    activas = [{"id": e.id, "orden": orden_de[e.orden_id].numero if e.orden_id in orden_de else None,
                "equipo_id": e.equipo_id, "equipo": equipos[e.equipo_id].nombre if e.equipo_id in equipos else None,
                "linea": lineas.get(orden_de[e.orden_id].linea_id) if e.orden_id in orden_de else None}
               for e in ejecs.values() if _val(e.estado) in ("EN_PROGRESO", "PAUSADA")]
    return {
        "kpis": {"oee_7d": per7["oee"] if per7 else None, "produccion_hoy": sum(c["producida"] for c in c_hoy),
                 "scrap_hoy_pct": round(sum(c["scrap"] for c in c_hoy) / tot_hoy * 100, 2) if tot_hoy else None,
                 "ordenes_activas": len(ordenes), "ordenes_atrasadas": sum(1 for o in filas_ord if o["atrasada"]),
                 "paradas_abiertas": len(paradas), "inspecciones_pendientes": insp_pend},
        "lineas": filas_lin, "paradas": paradas, "ordenes": filas_ord, "tendencia": tendencia,
        "alertas": alertas, "ejecuciones_activas": activas,
    }


# ─── SPC ──────────────────────────────────────────────────────────────────────

@router.get("/spc", response_model=Dict[str, Any])
async def control_estadistico(db: AsyncSession = Depends(get_db)):
    lineas, *_ = await _nombres(db)
    corridas = await _corridas(db)
    por_linea = defaultdict(list)
    for c in corridas:
        por_linea[c["linea"] or "Sin línea"].append(c)
    desperdicio = [{"nombre": l, **carta_p_laney([c["scrap"] for c in cs], [c["total"] for c in cs],
                                                 [f'{c["orden"]} · {c["fecha"]:%d/%m %H:%M}' for c in cs])}
                   for l, cs in por_linea.items()]

    oee = (await db.execute(select(MESOEERegistro).order_by(MESOEERegistro.fecha))).scalars().all()
    oee_linea = defaultdict(list)
    for r in oee:
        if r.oee is not None:
            oee_linea[lineas.get(r.linea_id, f"Línea {r.linea_id}")].append(r)
    cartas_oee = [{"nombre": l, **carta_imr([r.oee for r in rs],
                                            [f'{_n(r.fecha):%d/%m} {_val(r.turno).lower()}' for r in rs])}
                  for l, rs in oee_linea.items()]

    insp = [i for i in (await db.execute(select(MESInspeccion).order_by(MESInspeccion.fecha_inspeccion))).scalars().all()
            if i.muestra_tam]
    carta_insp = carta_p_laney([i.muestra_defectos for i in insp], [i.muestra_tam for i in insp],
                               [f'{_n(i.fecha_inspeccion):%d/%m %H:%M}' for i in insp])
    return {"desperdicio": desperdicio, "oee": cartas_oee, "inspeccion": {"nombre": "Defectos en inspección", **carta_insp}}


# ─── Pérdidas de OEE ──────────────────────────────────────────────────────────

def _perdidas(registros) -> Optional[Dict]:
    """Minutos perdidos por factor. OEE = D·R·C sale exacto de las sumas, así
    que la caída entre periodos se reparte entre los tres sin residuo."""
    tp = sum(r.tiempo_planificado_min for r in registros)
    if tp <= 0:
        return None
    to = sum(r.tiempo_operativo_min for r in registros)
    rend = lambda r: min(1.0, r.produccion_real / r.produccion_nominal) if r.produccion_nominal else 1.0
    cal = lambda r: (r.produccion_buena / r.produccion_real) if r.produccion_real else 1.0
    util_r = sum(r.tiempo_operativo_min * rend(r) for r in registros)
    util_c = sum(r.tiempo_operativo_min * rend(r) * cal(r) for r in registros)
    D = to / tp
    R = util_r / to if to else 0
    C = util_c / util_r if util_r else 0
    return {
        "registros": len(registros), "planificado_min": round(tp),
        "perdida_disponibilidad_min": round(tp - to), "perdida_rendimiento_min": round(to - util_r),
        "perdida_calidad_min": round(util_r - util_c), "util_min": round(util_c),
        "disponibilidad": round(D * 100, 1), "rendimiento": round(R * 100, 1),
        "calidad": round(C * 100, 1), "oee": round(D * R * C * 100, 1),
    }


@router.get("/perdidas", response_model=Dict[str, Any])
async def perdidas_oee(dias: int = Query(30, ge=7, le=365), db: AsyncSession = Depends(get_db)):
    import math
    lineas, _, _, equipos, _ = await _nombres(db)
    ahora = _ahora()
    desde, antes = ahora - timedelta(days=dias), ahora - timedelta(days=2 * dias)
    regs = (await db.execute(select(MESOEERegistro))).scalars().all()
    actual = [r for r in regs if _n(r.fecha) >= desde]
    previo = [r for r in regs if antes <= _n(r.fecha) < desde]

    salida_lineas = []
    for lid in sorted({r.linea_id for r in actual}):
        a = _perdidas([r for r in actual if r.linea_id == lid])
        p = _perdidas([r for r in previo if r.linea_id == lid])
        explicacion = None
        # Repartir un cambio de medio punto entre tres factores es repartir
        # ruido: solo se explica un cambio de al menos dos puntos de OEE.
        if a and p and a["oee"] > 0 and p["oee"] > 0 and abs(a["oee"] - p["oee"]) >= 2:
            # ln(OEE) = ln D + ln R + ln C: cada factor explica su parte del cambio.
            d = {k: math.log(a[k] / p[k]) if a[k] > 0 and p[k] > 0 else 0.0
                 for k in ("disponibilidad", "rendimiento", "calidad")}
            total = sum(d.values()) or 1e-9
            explicacion = {k: round(v / total * 100) for k, v in d.items()}
        salida_lineas.append({"linea": lineas.get(lid, f"Línea {lid}"), "actual": a, "anterior": p,
                              "cambio_oee": round(a["oee"] - p["oee"], 1) if a and p else None,
                              "explicacion": explicacion})

    def por(clave, nombre):
        g = defaultdict(list)
        for r in actual:
            k = clave(r)
            if k:
                g[k].append(r)
        filas = [{"nombre": nombre(k), **_perdidas(rs)} for k, rs in g.items() if _perdidas(rs)]
        return sorted(filas, key=lambda x: x["oee"])

    return {
        "dias": dias, "lineas": salida_lineas,
        "equipos": por(lambda r: r.equipo_id, lambda k: equipos[k].nombre if k in equipos else f"Equipo {k}"),
        "turnos": por(lambda r: _val(r.turno), lambda k: k.capitalize()),
    }


# ─── Paradas ──────────────────────────────────────────────────────────────────

def _duracion(p: MESParada) -> float:
    if p.duracion_min:
        return p.duracion_min
    if p.fecha_inicio and p.fecha_fin:
        return max(0.0, (_n(p.fecha_fin) - _n(p.fecha_inicio)).total_seconds() / 60)
    return 0.0


ETIQUETAS_PARADA = {
    "horas_desde_parada": "Horas desde la última parada no planeada",
    "sin_parada_previa": "Sin paradas no planeadas antes",
    "paradas_7d": "Paradas no planeadas en 7 días",
    "paradas_30d": "Paradas no planeadas en 30 días",
    "minutos_parada_30d": "Minutos de parada en 30 días",
    "unidades_7d": "Unidades producidas en 7 días",
    "desperdicio_7d": "Desperdicio en 7 días (%)",
    "equipo": "Equipo",
}


@router.get("/paradas", response_model=Dict[str, Any])
async def analisis_paradas(dias: int = Query(180, ge=30, le=1825), db: AsyncSession = Depends(get_db)):
    _, _, _, equipos, _ = await _nombres(db)
    ahora = _ahora()
    todas = [p for p in (await db.execute(select(MESParada))).scalars().all() if p.fecha_inicio]
    recientes = [p for p in todas if _n(p.fecha_inicio) >= ahora - timedelta(days=dias)]

    # Pareto por causa
    causas = defaultdict(lambda: {"minutos": 0.0, "eventos": 0, "tipo": set()})
    for p in recientes:
        c = causas[p.causa.strip()]
        c["minutos"] += _duracion(p); c["eventos"] += 1; c["tipo"].add(_val(p.tipo))
    total_min = sum(c["minutos"] for c in causas.values()) or 1
    pareto, acumulado = [], 0.0
    for causa, c in sorted(causas.items(), key=lambda x: -x[1]["minutos"]):
        acumulado += c["minutos"]
        pareto.append({"causa": causa, "minutos": round(c["minutos"]), "eventos": c["eventos"],
                       "tipos": sorted(c["tipo"]), "pct": round(c["minutos"] / total_min * 100, 1),
                       "acumulado": round(acumulado / total_min * 100, 1)})

    # Weibull del tiempo entre paradas no planeadas, por equipo
    no_plan = defaultdict(list)
    for p in todas:
        if _val(p.tipo) in NO_PLANEADAS and p.equipo_id:
            no_plan[p.equipo_id].append(_n(p.fecha_inicio))
    primera = defaultdict(lambda: ahora)
    for p in todas:
        if p.equipo_id:
            primera[p.equipo_id] = min(primera[p.equipo_id], _n(p.fecha_inicio))
    corridas = await _corridas(db)
    for c in corridas:
        if c["equipo_id"]:
            primera[c["equipo_id"]] = min(primera[c["equipo_id"]], c["fecha"])

    por_equipo = []
    for eid, fechas in no_plan.items():
        fechas.sort()
        horas = lambda a, b: (b - a).total_seconds() / 3600
        tiempos, fallo = [horas(primera[eid], fechas[0])], [False]
        tiempos += [horas(a, b) for a, b in zip(fechas, fechas[1:])]
        fallo += [True] * (len(fechas) - 1)
        tiempos.append(horas(fechas[-1], ahora)); fallo.append(False)
        aj = ajustar_weibull(tiempos, fallo)
        fila = {"equipo_id": eid, "equipo": equipos[eid].nombre if eid in equipos else f"Equipo {eid}",
                "paradas": len(fechas), "horas_desde_ultima": round(horas(fechas[-1], ahora), 1), **aj}
        if aj.get("suficiente"):
            fila["prob_7d"] = round(prob_falla_condicional(fila["horas_desde_ultima"], 24 * HORIZONTE_PARADA_DIAS,
                                                           aj["beta"], aj["eta"]) * 100, 1)
        por_equipo.append(fila)
    por_equipo.sort(key=lambda f: (not f.get("suficiente"), -(f.get("prob_7d") or 0)))

    # Aprendizaje automático: foto diaria de cada equipo
    prod = defaultdict(list)
    for c in corridas:
        if c["equipo_id"]:
            prod[c["equipo_id"]].append(c)
    min_de = defaultdict(list)
    for p in todas:
        if _val(p.tipo) in NO_PLANEADAS and p.equipo_id:
            min_de[p.equipo_id].append((_n(p.fecha_inicio), _duracion(p)))

    def variables(eid, corte):
        ev = [f for f in no_plan.get(eid, []) if f <= corte]
        ult = max(ev) if ev else None
        cs = [c for c in prod.get(eid, []) if corte - timedelta(days=7) < c["fecha"] <= corte]
        tot = sum(c["total"] for c in cs)
        return {
            "horas_desde_parada": min((corte - ult).total_seconds() / 3600, 24 * 90) if ult else None,
            "sin_parada_previa": 0 if ult else 1,
            "paradas_7d": sum(1 for f in ev if f > corte - timedelta(days=7)),
            "paradas_30d": sum(1 for f in ev if f > corte - timedelta(days=30)),
            "minutos_parada_30d": sum(m for f, m in min_de.get(eid, []) if corte - timedelta(days=30) < f <= corte),
            "unidades_7d": tot,
            "desperdicio_7d": (sum(c["scrap"] for c in cs) / tot * 100) if tot else None,
            "equipo": equipos[eid].codigo if eid in equipos else str(eid),
        }

    filas, y, fechas_corte = [], [], []
    activos = [eid for eid, e in equipos.items() if e.activo and eid in primera]
    for eid in activos:
        corte = primera[eid] + timedelta(days=14)
        while corte <= ahora - timedelta(days=HORIZONTE_PARADA_DIAS):
            filas.append(variables(eid, corte))
            fin = corte + timedelta(days=HORIZONTE_PARADA_DIAS)
            y.append(int(any(corte < f <= fin for f in no_plan.get(eid, []))))
            fechas_corte.append(corte)
            corte += timedelta(days=1)
    modelo = predictivo.entrenar(filas, y, fechas_corte, categoricas=["equipo"], etiquetas=ETIQUETAS_PARADA)
    riesgo = []
    if modelo.get("suficiente"):
        actuales = {eid: variables(eid, ahora) for eid in activos}
        for (eid, v), prob in zip(actuales.items(), predictivo.predecir(modelo, list(actuales.values()))):
            riesgo.append({"equipo_id": eid, "equipo": equipos[eid].nombre, "prob_7d": round(float(prob) * 100, 1),
                           "fuera_de_experiencia": predictivo.fuera_de_experiencia(modelo, v, ETIQUETAS_PARADA),
                           "paradas_30d": v["paradas_30d"],
                           "horas_desde_parada": round(v["horas_desde_parada"]) if v["horas_desde_parada"] is not None else None})
        riesgo.sort(key=lambda r: -r["prob_7d"])

    return {"dias": dias, "pareto": pareto, "minutos_totales": round(total_min) if recientes else 0,
            "eventos": len(recientes), "weibull": por_equipo,
            "prediccion": {**predictivo.publico(modelo), "horizonte_dias": HORIZONTE_PARADA_DIAS, "equipos": riesgo}}


# ─── Desperdicio ──────────────────────────────────────────────────────────────

@router.get("/desperdicio", response_model=Dict[str, Any])
async def que_explica_el_desperdicio(dias: int = Query(180, ge=30, le=1825), db: AsyncSession = Depends(get_db)):
    ahora = _ahora()
    corridas = [c for c in await _corridas(db) if c["fecha"] >= ahora - timedelta(days=dias)]
    factores = {"operario": "Operario", "turno": "Turno", "equipo": "Equipo", "producto": "Producto", "linea": "Línea"}
    comparaciones = comparar_grupos(corridas, factores)

    scraps = [s for s in (await db.execute(select(MESScrap))).scalars().all()
              if _n(s.fecha_registro) >= ahora - timedelta(days=dias)]
    causas = defaultdict(lambda: {"cantidad": 0.0, "costo": 0.0, "registros": 0})
    for s in scraps:
        c = causas[s.causa.strip()]
        c["cantidad"] += s.cantidad or 0
        c["costo"] += s.costo_total or 0
        c["registros"] += 1
    total_costo = sum(c["costo"] for c in causas.values())
    pareto = sorted(({"causa": k, "cantidad": round(v["cantidad"], 1), "costo": round(v["costo"]),
                      "registros": v["registros"],
                      "pct_costo": round(v["costo"] / total_costo * 100, 1) if total_costo else None}
                     for k, v in causas.items()), key=lambda x: -(x["costo"] or x["cantidad"]))
    unidades = sum(c["total"] for c in corridas)
    return {
        "dias": dias, "corridas": len(corridas),
        "tasa_global": round(sum(c["scrap"] for c in corridas) / unidades * 100, 2) if unidades else None,
        "comparaciones": comparaciones, "pareto_causas": pareto,
    }
