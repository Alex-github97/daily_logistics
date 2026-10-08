"""
Analítica de riesgo: incidentes y contraste de la matriz de riesgos con lo que
de verdad pasó.

La pantalla «IA» de GRC mostraba insights con confianza del 88 al 97 %
(«riesgos cibernéticos en Q3», «anomalía SARLAFT»), predicciones de riesgo y
recomendaciones, todo escrito a mano. Aquí:

  Incidentes  tendencia mensual, incidentes que se repiten (agrupados por
              texto) y tiempo de resolución con Kaplan-Meier, que cuenta los
              abiertos en vez de ignorarlos.
  Matriz      ¿la evaluación de riesgos acierta? Por proceso, el riesgo
              residual evaluado contra los incidentes que ocurrieron. Un
              proceso con incidentes graves y riesgo «bajo» está subestimado;
              un control «efectivo» en un proceso donde siguen pasando
              incidentes graves necesita probarse de nuevo.

No hay aprendizaje automático aquí a propósito: los incidentes son pocos y
cada uno distinto. Un modelo entrenado con veinte eventos inventaría patrones.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analitica.estadistica import carta_c, kaplan_meier, mann_kendall, spearman, supervivencia_en
from app.core.analitica.texto import agrupar
from app.core.database import get_db
from app.infrastructure.models.grc import GRCControl, GRCIncidente, GRCRiesgo, GRCRiesgoControl

router = APIRouter(prefix="/grc/analitica", tags=["GRC · Analítica"])

GRAVES = {"ALTA", "CRITICA"}


def _n(f: Optional[datetime]) -> Optional[datetime]:
    if f is None:
        return None
    if not isinstance(f, datetime):
        f = datetime(f.year, f.month, f.day)
    return f.astimezone(timezone.utc).replace(tzinfo=None) if f.tzinfo else f


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _val(e) -> Optional[str]:
    """El valor del enum en mayúsculas: los de GRC se guardan en minúscula
    («alta», «efectivo») y compararlos contra «ALTA» fallaría en silencio."""
    v = e.value if hasattr(e, "value") else e
    return v.upper() if isinstance(v, str) else v


def _normalizador():
    """El proceso como se escribió la primera vez. Se compara sin mayúsculas ni
    espacios de más («Transporte» y «transporte » son el mismo), pero se
    muestra con su nombre original. Uno por consulta: un diccionario del
    módulo lo compartirían todas las empresas que atiende el proceso."""
    vistos: Dict[str, str] = {}

    def proc(t: Optional[str]) -> Optional[str]:
        if not t or not t.strip():
            return None
        limpio = " ".join(t.split())
        return vistos.setdefault(limpio.lower(), limpio)
    return proc


def _nivel(n: Optional[int]) -> str:
    if n is None:
        return "SIN_EVALUAR"
    return "CRITICO" if n >= 15 else "ALTO" if n >= 10 else "MODERADO" if n >= 5 else "BAJO"


async def _incidentes(db: AsyncSession) -> List[GRCIncidente]:
    return [i for i in (await db.execute(select(GRCIncidente).where(GRCIncidente.activo.is_(True)))).scalars().all()
            if _n(i.fecha_ocurrencia or i.created_at)]


def _fecha(i) -> datetime:
    return _n(i.fecha_ocurrencia or i.created_at)


# ─── Incidentes ───────────────────────────────────────────────────────────────

@router.get("/incidentes", response_model=Dict[str, Any])
async def analisis_incidentes(db: AsyncSession = Depends(get_db)):
    _proc = _normalizador()
    inc = await _incidentes(db)
    ahora = _ahora()
    if not inc:
        return {"total": 0, "carta": {"suficiente": False, "puntos": 0, "minimo": 12}, "tendencias": [],
                "resolucion": [], "abiertos": [], "recurrentes": []}
    inicio = max(min(_fecha(i) for i in inc), ahora - timedelta(days=730))
    meses = []
    y, m = inicio.year, inicio.month
    while (y, m) < (ahora.year, ahora.month):          # sin el mes en curso
        meses.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1

    def serie(f):
        c = defaultdict(int)
        for i in inc:
            if f(i):
                c[f"{_fecha(i).year}-{_fecha(i).month:02d}"] += 1
        return [c[x] for x in meses]

    total = serie(lambda i: True)
    tendencias = []
    for dim, clave in (("Tipo", lambda i: (i.tipo or "").strip().capitalize() or None),
                       ("Severidad", lambda i: _val(i.severidad)), ("Proceso", lambda i: _proc(i.proceso))):
        for nivel in sorted({clave(i) for i in inc if clave(i)}):
            s = serie(lambda i, nivel=nivel, clave=clave: clave(i) == nivel)
            if sum(s) >= 5:
                tendencias.append({"dimension": dim, "nivel": nivel, "total": sum(s), "serie": s, **mann_kendall(s)})
    tendencias.sort(key=lambda g: ({"SUBE": 0, "BAJA": 1, "ESTABLE": 2}.get(g.get("tendencia"), 3), g.get("p", 1)))

    # Resolución: días desde que ocurrió hasta que se cerró; los abiertos, censurados hoy.
    def dias(i):
        fin = _n(i.fecha_cierre) if (i.estado or "").lower() == "cerrado" and i.fecha_cierre else ahora
        return max((fin - _fecha(i)).total_seconds() / 86400, 0.01)
    cerrado = lambda i: (i.estado or "").lower() == "cerrado" and i.fecha_cierre is not None
    resolucion, curvas = [], {}
    for sev in ["CRITICA", "ALTA", "MEDIA", "BAJA", None]:
        grupo = [i for i in inc if (sev is None or _val(i.severidad) == sev)]
        if not grupo:
            continue
        km = kaplan_meier([dias(i) for i in grupo], [cerrado(i) for i in grupo])
        curvas[sev or "TODAS"] = km
        resolucion.append({"severidad": sev or "TODAS", **{k: v for k, v in km.items() if k != "curva"},
                           "curva": km.get("curva", [])[::max(1, len(km.get("curva", [])) // 60)]})

    duraciones_cerrados = defaultdict(list)
    for i in inc:
        if cerrado(i):
            duraciones_cerrados[_val(i.severidad)].append(dias(i))
    abiertos = []
    for i in inc:
        if cerrado(i):
            continue
        d = dias(i)
        previos = duraciones_cerrados.get(_val(i.severidad)) or [x for v in duraciones_cerrados.values() for x in v]
        mas_lento_que = round(sum(1 for x in previos if x < d) / len(previos) * 100) if previos else None
        km = curvas.get(_val(i.severidad)) if curvas.get(_val(i.severidad), {}).get("suficiente") else curvas.get("TODAS")
        prob = None
        # Más allá del último cierre observado la curva no sabe nada: se
        # queda plana y daría 0 %, que se leería como «no se cerrará nunca».
        if km and km.get("suficiente") and km["curva"] and d <= km["curva"][-1][0]:
            s_hoy = supervivencia_en(km["curva"], d)
            if s_hoy > 0:
                prob = round((1 - supervivencia_en(km["curva"], d + 30) / s_hoy) * 100, 1)
        abiertos.append({"id": i.id, "codigo": i.codigo, "titulo": i.titulo, "severidad": _val(i.severidad),
                         "proceso": _proc(i.proceso), "dias_abierto": round(d),
                         # Qué parte de los ya cerrados de su severidad se cerró más rápido.
                         "mas_lento_que_pct": mas_lento_que,
                         "prob_cierre_30d": prob})
    abiertos.sort(key=lambda a: -a["dias_abierto"])

    textos = [" ".join(filter(None, [i.titulo, i.descripcion, i.causa_raiz])) for i in inc]
    grupos = agrupar(textos)
    recurrentes = []
    for g in grupos["grupos"]:
        miembros = sorted((inc[k] for k in g["indices"]), key=_fecha)
        recurrentes.append({
            "terminos": g["terminos"], "cantidad": len(miembros),
            "titulo": miembros[-1].titulo, "desde": _fecha(miembros[0]).date().isoformat(),
            "hasta": _fecha(miembros[-1]).date().isoformat(),
            "graves": sum(1 for x in miembros if _val(x.severidad) in GRAVES),
            "procesos": sorted({_proc(x.proceso) or "Sin proceso" for x in miembros}),
            "con_leccion": sum(1 for x in miembros if (x.lecciones_aprendidas or "").strip()),
            "incidentes": [{"codigo": x.codigo, "titulo": x.titulo, "fecha": _fecha(x).date().isoformat(),
                            "severidad": _val(x.severidad), "estado": x.estado} for x in miembros][-12:],
        })
    return {"total": len(inc), "meses": meses, "carta": carta_c(total, meses), "tendencia_total": mann_kendall(total),
            "tendencias": tendencias, "resolucion": resolucion, "abiertos": abiertos[:30], "recurrentes": recurrentes}


# ─── ¿La matriz acierta? ──────────────────────────────────────────────────────

@router.get("/matriz", response_model=Dict[str, Any])
async def contraste_matriz(meses: int = Query(12, ge=3, le=60), db: AsyncSession = Depends(get_db)):
    _proc = _normalizador()
    ahora = _ahora()
    desde = ahora - timedelta(days=30 * meses)
    riesgos = [r for r in (await db.execute(select(GRCRiesgo).where(GRCRiesgo.activo.is_(True)))).scalars().all()
               if _val(r.estado) != "CERRADO"]
    inc = [i for i in await _incidentes(db) if _fecha(i) >= desde]
    controles = {c.id: c for c in (await db.execute(select(GRCControl).where(GRCControl.activo.is_(True)))).scalars().all()}
    enlaces = (await db.execute(select(GRCRiesgoControl))).scalars().all()

    procesos: Dict[str, Dict] = defaultdict(lambda: {"riesgos": [], "incidentes": []})
    for r in riesgos:
        if _proc(r.proceso):
            procesos[_proc(r.proceso)]["riesgos"].append(r)
    for i in inc:
        if _proc(i.proceso):
            procesos[_proc(i.proceso)]["incidentes"].append(i)

    filas = []
    for nombre, d in procesos.items():
        niveles = [r.nivel_residual or r.nivel_inherente for r in d["riesgos"] if (r.nivel_residual or r.nivel_inherente)]
        maximo = max(niveles) if niveles else None
        graves = sum(1 for i in d["incidentes"] if _val(i.severidad) in GRAVES)
        n_inc = len(d["incidentes"])
        if not d["riesgos"] and n_inc:
            veredicto = "SIN_RIESGOS"
        elif graves >= 1 and maximo is not None and maximo < 10:
            veredicto = "SUBESTIMADO"
        elif n_inc == 0 and maximo is not None and maximo >= 15:
            veredicto = "SIN_EVIDENCIA"
        else:
            veredicto = "COHERENTE"
        filas.append({"proceso": nombre, "riesgos": len(d["riesgos"]), "nivel_maximo": maximo,
                      "zona": _nivel(maximo), "incidentes": n_inc, "graves": graves, "veredicto": veredicto,
                      "riesgo_mayor": max(d["riesgos"], key=lambda r: r.nivel_residual or r.nivel_inherente or 0).nombre
                      if d["riesgos"] else None})
    orden = {"SUBESTIMADO": 0, "SIN_RIESGOS": 1, "SIN_EVIDENCIA": 2, "COHERENTE": 3}
    filas.sort(key=lambda f: (orden[f["veredicto"]], -f["graves"], -f["incidentes"]))

    evaluados = [f for f in filas if f["nivel_maximo"] is not None]
    correlacion = spearman([f["nivel_maximo"] for f in evaluados], [f["incidentes"] for f in evaluados])

    # Controles declarados efectivos donde siguen pasando incidentes graves
    riesgo_proceso = {r.id: _proc(r.proceso) for r in riesgos}
    procesos_de_control = defaultdict(set)
    for e in enlaces:
        if e.riesgo_id in riesgo_proceso and riesgo_proceso[e.riesgo_id]:
            procesos_de_control[e.control_id].add(riesgo_proceso[e.riesgo_id])
    for c in controles.values():
        if _proc(c.proceso):
            procesos_de_control[c.id].add(_proc(c.proceso))
    graves_por_proceso = {f["proceso"]: f["graves"] for f in filas}
    en_duda = []
    for cid, procs in procesos_de_control.items():
        c = controles.get(cid)
        if not c or _val(c.efectividad) != "EFECTIVO":
            continue
        g = sum(graves_por_proceso.get(p, 0) for p in procs)
        if g:
            en_duda.append({"control": c.nombre, "codigo": c.codigo, "procesos": sorted(procs), "incidentes_graves": g,
                            "ultima_evaluacion": c.ultima_evaluacion.isoformat() if c.ultima_evaluacion else None})
    en_duda.sort(key=lambda x: -x["incidentes_graves"])
    return {"meses": meses, "procesos": filas, "correlacion": correlacion, "controles_en_duda": en_duda,
            "incidentes_sin_proceso": sum(1 for i in inc if not _proc(i.proceso))}
