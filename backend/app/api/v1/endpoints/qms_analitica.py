"""
Analítica de calidad: tendencias, problemas recurrentes con la eficacia de sus
CAPA, y proveedores en caída.

La pantalla «IA» de QMS mostraba «insights» con confianza del 94 %, una
«correlación 0,74» entre hallazgos y rotación de personal, un Ishikawa con
causas fijas y una predicción de NC para julio, todo escrito a mano. Aquí:

  Tendencias   ¿las NC de un proceso de verdad suben, o fue un mal mes?
               Carta c por mes y Mann-Kendall por proceso, origen y gravedad.
  Recurrentes  NC que hablan de lo mismo con otras palabras, agrupadas por
               texto; y si después de cerrar su CAPA el problema volvió. Esa
               es la verificación de eficacia que pide ISO 9001 (10.2.1 d).
  Proveedores  tendencia del puntaje con intervalo; solo se proyecta el cruce
               del mínimo si la caída es estadísticamente clara.
"""
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.qms import _leer_parametros
from app.core.analitica.estadistica import carta_c, mann_kendall, regresion_lineal
from app.core.analitica.texto import agrupar
from app.core.database import get_db
from app.infrastructure.models.qms import (
    QMSCAPA, QMSEvaluacionProveedor, QMSNoConformidad, QMSProceso, QMSQueja,
)

router = APIRouter(prefix="/qms/analitica", tags=["QMS · Analítica"])

MESES_TENDENCIA = 24
DIAS_PARA_JUZGAR_CAPA = 90


def _n(f: Optional[datetime]) -> Optional[datetime]:
    if f is None:
        return None
    return f.astimezone(timezone.utc).replace(tzinfo=None) if f.tzinfo else f


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _val(e) -> Optional[str]:
    return e.value if hasattr(e, "value") else e


def _mes(f: datetime) -> str:
    return f"{f.year}-{f.month:02d}"


def _meses(desde: datetime, hasta: datetime) -> List[str]:
    salida, y, m = [], desde.year, desde.month
    while (y, m) <= (hasta.year, hasta.month):
        salida.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return salida


async def _ncs(db: AsyncSession):
    ncs = [n for n in (await db.execute(select(QMSNoConformidad).where(QMSNoConformidad.activo.is_(True)))).scalars().all()
           if _n(n.fecha_deteccion or n.created_at)]
    procesos = {p.id: p.nombre for p in (await db.execute(select(QMSProceso))).scalars().all()}
    return ncs, procesos


def _fecha(n) -> datetime:
    return _n(n.fecha_deteccion or n.created_at)


# ─── Tendencias ───────────────────────────────────────────────────────────────

@router.get("/tendencias", response_model=Dict[str, Any])
async def tendencias(db: AsyncSession = Depends(get_db)):
    ncs, procesos = await _ncs(db)
    ahora = _ahora()
    if not ncs:
        return {"meses": [], "carta": {"suficiente": False, "puntos": 0, "minimo": 12}, "grupos": [], "quejas": None, "cierre": None}
    inicio = max(min(_fecha(n) for n in ncs), datetime(ahora.year - MESES_TENDENCIA // 12, ahora.month, 1))
    meses = _meses(inicio, ahora)
    # El mes en curso está incompleto: contarlo como un mes entero lo haría
    # parecer una caída. Se excluye de las pruebas y se muestra aparte.
    completos = meses[:-1]

    def serie(filtro) -> List[int]:
        c = defaultdict(int)
        for n in ncs:
            if filtro(n):
                c[_mes(_fecha(n))] += 1
        return [c[m] for m in completos]

    total = serie(lambda n: True)
    grupos = []
    dimensiones = [
        ("Proceso", lambda n: procesos.get(n.proceso_id) if n.proceso_id else None),
        ("Origen", lambda n: _val(n.origen)),
        ("Gravedad", lambda n: _val(n.clasificacion)),
    ]
    for dim, clave in dimensiones:
        for nivel in sorted({clave(n) for n in ncs if clave(n)}):
            s = serie(lambda n, nivel=nivel, clave=clave: clave(n) == nivel)
            if sum(s) < 5:
                continue
            mk = mann_kendall(s)
            grupos.append({"dimension": dim, "nivel": nivel, "total": sum(s), "serie": s, **mk})
    grupos.sort(key=lambda g: ({"SUBE": 0, "BAJA": 1, "ESTABLE": 2}.get(g.get("tendencia"), 3), g.get("p", 1)))

    # Quejas por mes
    quejas = [q for q in (await db.execute(select(QMSQueja).where(QMSQueja.activo.is_(True)))).scalars().all()
              if _n(q.created_at) and _n(q.created_at) >= inicio]
    cq = defaultdict(int)
    for q in quejas:
        cq[_mes(_n(q.created_at))] += 1
    serie_q = [cq[m] for m in completos]

    # Días para cerrar, por mes de detección
    cierre_mes = defaultdict(list)
    for n in ncs:
        if n.fecha_cierre and _n(n.fecha_cierre) >= _fecha(n):
            cierre_mes[_mes(_fecha(n))].append((_n(n.fecha_cierre) - _fecha(n)).days)
    medianas = [median(cierre_mes[m]) for m in completos if cierre_mes.get(m)]
    return {
        "meses": completos, "mes_en_curso": {"mes": meses[-1], "nc": sum(1 for n in ncs if _mes(_fecha(n)) == meses[-1])},
        "carta": carta_c(total, completos), "tendencia_total": mann_kendall(total), "total": total,
        "grupos": grupos,
        "quejas": {"serie": serie_q, "total": sum(serie_q), **mann_kendall(serie_q)},
        "cierre": {"meses_con_cierres": len(medianas), "mediana_dias": median(medianas) if medianas else None,
                   **mann_kendall(medianas)},
    }


# ─── Problemas recurrentes y eficacia de CAPA ────────────────────────────────

@router.get("/recurrentes", response_model=Dict[str, Any])
async def problemas_recurrentes(db: AsyncSession = Depends(get_db)):
    ncs, procesos = await _ncs(db)
    ahora = _ahora()
    textos = [" ".join(filter(None, [n.titulo, n.descripcion, n.causa_raiz])) for n in ncs]
    r = agrupar(textos)
    capas = [c for c in (await db.execute(select(QMSCAPA).where(QMSCAPA.activo.is_(True)))).scalars().all()]
    capas_de_nc = defaultdict(list)
    for c in capas:
        if c.nc_id:
            capas_de_nc[c.nc_id].append(c)

    grupos = []
    agrupadas = set()
    for g in r["grupos"]:
        miembros = sorted((ncs[i] for i in g["indices"]), key=_fecha)
        agrupadas.update(n.id for n in miembros)
        evaluacion_capas = []
        for n in miembros:
            for c in capas_de_nc.get(n.id, []):
                if _val(c.estado) != "CERRADA" or not c.fecha_cierre:
                    evaluacion_capas.append({"capa": c.codigo or f"CAPA {c.id}", "titulo": c.titulo,
                                             "estado": _val(c.estado), "veredicto": "ABIERTA"})
                    continue
                cierre = _n(c.fecha_cierre)
                despues = [m for m in miembros if _fecha(m) > cierre]
                dias = (ahora - cierre).days
                veredicto = ("INEFICAZ" if despues else
                             "MUY_PRONTO" if dias < DIAS_PARA_JUZGAR_CAPA else "SIN_REINCIDENCIA")
                evaluacion_capas.append({
                    "capa": c.codigo or f"CAPA {c.id}", "titulo": c.titulo, "estado": "CERRADA",
                    "cerrada": cierre.date().isoformat(), "dias_desde_cierre": dias,
                    "reincidencias": len(despues),
                    "reincidencias_codigos": [m.codigo or f"NC {m.id}" for m in despues][:8],
                    "veredicto": veredicto,
                })
        ultimos90 = sum(1 for n in miembros if (ahora - _fecha(n)).days <= 90)
        grupos.append({
            "terminos": g["terminos"], "cantidad": len(miembros), "ultimos_90_dias": ultimos90,
            "desde": _fecha(miembros[0]).date().isoformat(), "hasta": _fecha(miembros[-1]).date().isoformat(),
            "procesos": sorted({procesos.get(n.proceso_id, "Sin proceso") for n in miembros}),
            "abiertas": sum(1 for n in miembros if _val(n.estado) != "CERRADA"),
            "sin_capa": sum(1 for n in miembros if not capas_de_nc.get(n.id)),
            "ncs": [{"id": n.id, "codigo": n.codigo, "titulo": n.titulo, "fecha": _fecha(n).date().isoformat(),
                     "estado": _val(n.estado), "proceso": procesos.get(n.proceso_id)} for n in miembros],
            "capas": evaluacion_capas,
        })
    ineficaces = sum(1 for g in grupos for c in g["capas"] if c["veredicto"] == "INEFICAZ")
    return {"suficiente": r["suficiente"], "ncs_analizadas": r["textos"], "ncs_agrupadas": len(agrupadas),
            "capas_ineficaces": ineficaces, "grupos": grupos, "dias_para_juzgar": DIAS_PARA_JUZGAR_CAPA}


# ─── Proveedores ──────────────────────────────────────────────────────────────

def _mes_del_periodo(p: Optional[str]) -> Optional[int]:
    """El período de una evaluación como número de mes (año*12 + mes).

    Las evaluaciones se registran por mes (2026-03), trimestre (2026-T1),
    semestre (2026-S1) o año (2026). Se toma el último mes del período. Antes
    se suponía siempre mes y un trimestre tumbaba la analítica entera.
    """
    import re
    if not p:
        return None
    p = p.strip().upper()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", p)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)) * 12 + int(m.group(2))
    m = re.fullmatch(r"(\d{4})-?([TQS])(\d)", p)
    if m:
        n = int(m.group(3))
        meses = 6 if m.group(2) == "S" else 3
        if 1 <= n <= 12 // meses:
            return int(m.group(1)) * 12 + n * meses
    m = re.fullmatch(r"(\d{4})", p)
    if m:
        return int(m.group(1)) * 12 + 12
    return None


@router.get("/proveedores", response_model=Dict[str, Any])
async def proveedores_en_caida(db: AsyncSession = Depends(get_db)):
    minimo = (await _leer_parametros(db))["proveedor_puntaje_minimo"]
    evals = [e for e in (await db.execute(select(QMSEvaluacionProveedor))).scalars().all()
             if e.puntaje_total is not None and _mes_del_periodo(e.periodo) is not None]
    por = defaultdict(list)
    for e in evals:
        por[(e.proveedor_nit or e.proveedor_nombre.strip().upper())].append(e)
    salida = []
    for _, es in por.items():
        idx = _mes_del_periodo
        es.sort(key=lambda e: idx(e.periodo))
        base = idx(es[0].periodo)
        x = [idx(e.periodo) - base for e in es]
        y = [float(e.puntaje_total) for e in es]
        reg = regresion_lineal(x, y)
        fila = {"proveedor": es[-1].proveedor_nombre, "nit": es[-1].proveedor_nit, "evaluaciones": len(es),
                "ultimo": y[-1], "ultimo_periodo": es[-1].periodo, "promedio": round(sum(y) / len(y), 1),
                "serie": [{"periodo": e.periodo, "puntaje": v} for e, v in zip(es, y)],
                "bajo_minimo": y[-1] < minimo, **reg}
        fila["meses_para_minimo"] = None
        if reg.get("suficiente") and reg["significativa"] and reg["pendiente"] < 0:
            actual = reg["intercepto"] + reg["pendiente"] * x[-1]
            if actual > minimo:
                fila["meses_para_minimo"] = round((minimo - actual) / reg["pendiente"], 1)
        fila["estado"] = ("BAJO_MINIMO" if fila["bajo_minimo"] else
                          "EN_CAIDA" if reg.get("significativa") and reg["pendiente"] < 0 else
                          "MEJORA" if reg.get("significativa") and reg["pendiente"] > 0 else
                          "ESTABLE" if reg.get("suficiente") else "POCOS_DATOS")
        salida.append(fila)
    orden = {"BAJO_MINIMO": 0, "EN_CAIDA": 1, "ESTABLE": 2, "MEJORA": 3, "POCOS_DATOS": 4}
    salida.sort(key=lambda f: (orden[f["estado"]], f.get("meses_para_minimo") or 999))
    return {"minimo": minimo, "proveedores": salida}
