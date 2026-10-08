"""GRC — configuración propia del módulo, agenda de vencimientos, tablero y
reporte para la junta.

La matriz de riesgo, las bandas de prioridad, el apetito por categoría y los
plazos de aviso viven en la base y cada cálculo los lee: cambiarlos aquí cambia
de verdad la prioridad de los riesgos y lo que aparece en la agenda.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas import grc as esq
from app.core import grc_servicio as srv
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.catalogo import CatalogoMaestro
from app.infrastructure.models.grc import (
    EfectividadControlGRCEnum, EstadoHallazgoGRCEnum, EstadoPoliticaGRCEnum, EstadoRiesgoGRCEnum,
    GRCAuditoria, GRCBandaRiesgo, GRCComite, GRCComiteSesion, GRCContinuidad, GRCControl,
    GRCEscala, GRCEvidencia, GRCHallazgo, GRCIncidente, GRCKri, GRCKriMedicion,
    GRCMatrizCumplimiento, GRCObligacion, GRCParametro, GRCPlanAccion, GRCPolitica, GRCRiesgo,
    GRCTercero, GRCTratamiento, PrioridadRiesgoGRCEnum,
)
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/grc", tags=["GRC"])

ORDEN_BANDAS = ["baja", "media", "alta", "critica"]
PARAMETROS = {
    "dias_aviso_vencimiento": ("Días de aviso antes de vencer", "Políticas, obligaciones, evidencias y revisiones.", 1, 365),
    "dias_aviso_prueba_control": ("Días de aviso antes de probar un control", "Cuándo aparece en la agenda la próxima prueba.", 1, 180),
    "dias_plazo_hallazgo": ("Plazo por defecto de un hallazgo (días)", "Fecha límite que se propone al abrir un hallazgo.", 1, 365),
}


# ── Matriz ───────────────────────────────────────────────────────────────────

@router.get("/config/matriz")
async def matriz(db: AsyncSession = Depends(get_db)):
    escala = (await db.execute(select(GRCEscala).order_by(GRCEscala.eje, GRCEscala.valor))).scalars().all()
    bandas = (await db.execute(select(GRCBandaRiesgo).order_by(GRCBandaRiesgo.minimo))).scalars().all()
    return {
        "escala": [{"eje": e.eje, "valor": e.valor, "nombre": e.nombre, "descripcion": e.descripcion} for e in escala],
        "bandas": [{"prioridad": srv.valor_json(b.prioridad), "minimo": b.minimo, "color": b.color,
                    "respuesta": b.respuesta} for b in bandas],
    }


@router.put("/config/escala")
async def guardar_escala(datos: List[esq.EscalaIn], db: AsyncSession = Depends(get_db),
                         _: Usuario = Depends(require_admin)):
    for d in datos:
        fila = (await db.execute(select(GRCEscala).where(GRCEscala.eje == d.eje, GRCEscala.valor == d.valor))).scalar()
        if fila is None:
            fila = GRCEscala(eje=d.eje, valor=d.valor)
            db.add(fila)
        fila.nombre, fila.descripcion = d.nombre.strip(), d.descripcion
    await db.commit()
    return await matriz(db)


@router.put("/config/bandas")
async def guardar_bandas(datos: List[esq.BandaIn], db: AsyncSession = Depends(get_db),
                         yo: Usuario = Depends(require_admin)):
    por = {d.prioridad: d for d in datos}
    if set(por) != set(ORDEN_BANDAS):
        raise HTTPException(422, "Defina las cuatro bandas: baja, media, alta y crítica.")
    minimos = [por[p].minimo for p in ORDEN_BANDAS]
    if minimos[0] != 1 or any(b <= a for a, b in zip(minimos, minimos[1:])):
        raise HTTPException(422, "La banda baja empieza en 1 y cada banda debe empezar más arriba que la anterior.")
    for p in ORDEN_BANDAS:
        enum = PrioridadRiesgoGRCEnum(p)
        fila = (await db.execute(select(GRCBandaRiesgo).where(GRCBandaRiesgo.prioridad == enum))).scalar()
        if fila is None:
            fila = GRCBandaRiesgo(prioridad=enum)
            db.add(fila)
        fila.minimo, fila.color, fila.respuesta = por[p].minimo, por[p].color, por[p].respuesta
    await db.flush()
    # Las bandas deciden la prioridad: todos los riesgos se reclasifican ya.
    cache = await srv.bandas(db)
    for r in (await db.execute(select(GRCRiesgo).where(GRCRiesgo.deleted_at.is_(None)))).scalars():
        r.prioridad = await srv.prioridad_de(db, r.nivel_residual or r.nivel_inherente, cache)
    await srv.registrar(db, "config", 0, "editar", yo.id, "bandas", None, minimos)
    await db.commit()
    return await matriz(db)


# ── Apetito por categoría ────────────────────────────────────────────────────

@router.get("/config/apetito")
async def apetito(db: AsyncSession = Depends(get_db)):
    meta = await srv.metadatos_catalogo(db, "GRC", "CATEGORIA_RIESGO")
    return [{"categoria": n, "apetito": (m or {}).get("apetito")} for n, m in sorted(meta.items())]


@router.put("/config/apetito")
async def guardar_apetito(datos: List[esq.ApetitoIn], db: AsyncSession = Depends(get_db),
                          _: Usuario = Depends(require_admin)):
    for d in datos:
        fila = (await db.execute(select(CatalogoMaestro).where(
            CatalogoMaestro.modulo == "GRC", CatalogoMaestro.tipo == "CATEGORIA_RIESGO",
            CatalogoMaestro.nombre == d.categoria))).scalar()
        if fila is None:
            raise HTTPException(422, f"La categoría «{d.categoria}» no existe.")
        meta = dict(fila.metadatos or {}) if isinstance(fila.metadatos, dict) else {}
        if d.apetito is None:
            meta.pop("apetito", None)
        else:
            meta["apetito"] = d.apetito
        fila.metadatos = meta or None
    await db.commit()
    return await apetito(db)


# ── Parámetros ───────────────────────────────────────────────────────────────

@router.get("/config/parametros")
async def parametros(db: AsyncSession = Depends(get_db)):
    salida = []
    for clave, (nombre, ayuda, mn, mx) in PARAMETROS.items():
        salida.append({"clave": clave, "nombre": nombre, "ayuda": ayuda, "minimo": mn, "maximo": mx,
                       "valor": await srv.parametro(db, clave, 30)})
    return salida


@router.put("/config/parametros")
async def guardar_parametros(datos: Dict[str, int], db: AsyncSession = Depends(get_db),
                             _: Usuario = Depends(require_admin)):
    for clave, valor in datos.items():
        if clave not in PARAMETROS:
            raise HTTPException(422, f"Parámetro desconocido: {clave}")
        _, _, mn, mx = PARAMETROS[clave]
        if not mn <= valor <= mx:
            raise HTTPException(422, f"«{PARAMETROS[clave][0]}» va de {mn} a {mx}.")
        fila = (await db.execute(select(GRCParametro).where(GRCParametro.clave == clave))).scalar()
        if fila is None:
            db.add(GRCParametro(clave=clave, valor=str(valor)))
        else:
            fila.valor = str(valor)
    await db.commit()
    return await parametros(db)


# ── Agenda: todo lo que vence ────────────────────────────────────────────────

@router.get("/agenda")
async def agenda(dias: int = Query(60, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    """Lo vencido y lo que vence en los próximos `dias`: pruebas de control,
    revisiones de políticas y planes de continuidad, obligaciones, evaluaciones
    de cumplimiento, hallazgos, planes de acción, tratamientos, evidencias,
    sesiones de comité y KRI sin medir este mes."""
    hoy = date.today()
    limite = hoy + timedelta(days=dias)
    aviso = await srv.parametro(db, "dias_aviso_vencimiento", 30)
    aviso_prueba = await srv.parametro(db, "dias_aviso_prueba_control", 15)
    usuarios = await srv.mapa_usuarios(db)
    items: List[dict] = []

    def poner(tipo, entidad, id_, codigo, titulo, fecha, responsable_id, ventana=aviso):
        if fecha is None or fecha > limite:
            return
        estado = "vencido" if fecha < hoy else ("por_vencer" if (fecha - hoy).days <= ventana else "programado")
        items.append({"tipo": tipo, "entidad": entidad, "id": id_, "codigo": codigo, "titulo": titulo,
                      "fecha": fecha.isoformat(), "dias": (fecha - hoy).days, "estado": estado,
                      "responsable": usuarios.get(responsable_id)})

    for c in (await db.execute(select(GRCControl).where(GRCControl.deleted_at.is_(None)))).scalars():
        poner("Prueba de control", "control", c.id, c.codigo, c.nombre, c.proxima_evaluacion, c.responsable_id, aviso_prueba)
    for p in (await db.execute(select(GRCPolitica).where(
            GRCPolitica.deleted_at.is_(None), GRCPolitica.estado.in_(
                [EstadoPoliticaGRCEnum.PUBLICADA, EstadoPoliticaGRCEnum.APROBADA])))).scalars():
        poner("Revisión de política", "politica", p.id, p.codigo, p.nombre, p.fecha_revision, p.propietario_id)
    for o in (await db.execute(select(GRCObligacion).where(GRCObligacion.deleted_at.is_(None)))).scalars():
        poner("Vencimiento de obligación", "obligacion", o.id, o.codigo, o.nombre, o.fecha_vencimiento, o.responsable_id)
    ultimas: Dict[int, GRCMatrizCumplimiento] = {}
    for e in (await db.execute(select(GRCMatrizCumplimiento).where(GRCMatrizCumplimiento.deleted_at.is_(None))
                               .order_by(GRCMatrizCumplimiento.ultima_evaluacion.asc().nullsfirst()))).scalars():
        ultimas[e.obligacion_id] = e
    obl = dict((await db.execute(select(GRCObligacion.id, GRCObligacion.nombre).where(GRCObligacion.deleted_at.is_(None)))).all())
    for oid, e in ultimas.items():
        if oid in obl:
            poner("Evaluación de cumplimiento", "obligacion", oid, None, obl[oid], e.proxima_evaluacion, e.responsable_id)
    for h in (await db.execute(select(GRCHallazgo).where(
            GRCHallazgo.deleted_at.is_(None), GRCHallazgo.estado != EstadoHallazgoGRCEnum.CERRADO))).scalars():
        poner("Cierre de hallazgo", "hallazgo", h.id, h.codigo, h.titulo, h.fecha_limite, h.responsable_id)
    for p in (await db.execute(select(GRCPlanAccion).where(
            GRCPlanAccion.deleted_at.is_(None), GRCPlanAccion.avance < 100))).scalars():
        poner("Plan de acción", "hallazgo", p.hallazgo_id, None, p.accion[:120], p.fecha_objetivo, p.responsable_id)
    for t in (await db.execute(select(GRCTratamiento).where(
            GRCTratamiento.deleted_at.is_(None), GRCTratamiento.avance < 100))).scalars():
        poner("Tratamiento de riesgo", "riesgo", t.riesgo_id, None, (t.descripcion or "Tratamiento")[:120],
              t.fecha_objetivo, t.responsable_id)
    for e in (await db.execute(select(GRCEvidencia).where(GRCEvidencia.deleted_at.is_(None)))).scalars():
        poner("Vencimiento de evidencia", e.referencia_tipo, e.referencia_id, None, e.nombre, e.fecha_vencimiento,
              e.responsable_id)
    for c in (await db.execute(select(GRCContinuidad).where(GRCContinuidad.deleted_at.is_(None)))).scalars():
        d = await srv.dias_de(db, c.periodicidad_revision)
        if d and c.ultima_revision:
            poner("Revisión de plan de continuidad", "continuidad", c.id, None, c.proceso,
                  c.ultima_revision + timedelta(days=d), c.responsable_id)
    proximas = (await db.execute(select(GRCComiteSesion.comite_id, func.max(GRCComiteSesion.proxima))
                                 .where(GRCComiteSesion.deleted_at.is_(None)).group_by(GRCComiteSesion.comite_id))).all()
    comites = {c.id: c for c in (await db.execute(select(GRCComite).where(GRCComite.deleted_at.is_(None)))).scalars()}
    for cid, prox in proximas:
        if cid in comites:
            poner("Sesión de comité", "comite", cid, None, comites[cid].nombre, prox, comites[cid].secretario_id)
    periodo = hoy.strftime("%Y-%m")
    medidos = set((await db.execute(select(GRCKriMedicion.kri_id).where(GRCKriMedicion.periodo == periodo))).scalars())
    fin_mes = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    for k in (await db.execute(select(GRCKri).where(GRCKri.deleted_at.is_(None)))).scalars():
        if k.id not in medidos:
            poner("Medición de KRI", "riesgo", k.riesgo_id, None, k.nombre, fin_mes, k.responsable_id)

    items.sort(key=lambda x: x["fecha"])
    resumen = Counter(i["estado"] for i in items)
    return {"items": items, "vencidos": resumen.get("vencido", 0), "por_vencer": resumen.get("por_vencer", 0)}


# ── Tablero ──────────────────────────────────────────────────────────────────

async def _n(db, modelo, *cond) -> int:
    return (await db.execute(select(func.count()).select_from(modelo).where(modelo.deleted_at.is_(None), *cond))).scalar() or 0


@router.get("/tablero")
async def tablero(db: AsyncSession = Depends(get_db)):
    hoy = date.today()
    abiertos = [EstadoRiesgoGRCEnum.IDENTIFICADO, EstadoRiesgoGRCEnum.EN_ANALISIS, EstadoRiesgoGRCEnum.TRATAMIENTO]
    riesgos = (await db.execute(select(GRCRiesgo).where(GRCRiesgo.deleted_at.is_(None)))).scalars().all()
    apetito = await srv.metadatos_catalogo(db, "GRC", "CATEGORIA_RIESGO")
    controles = (await db.execute(select(GRCControl).where(GRCControl.deleted_at.is_(None)))).scalars().all()
    probados = [c for c in controles if c.efectividad != EfectividadControlGRCEnum.NO_PROBADO]
    efectivos = [c for c in probados if c.efectividad == EfectividadControlGRCEnum.EFECTIVO]
    evals = (await db.execute(select(GRCObligacion.estado_cumplimiento, func.count()).where(
        GRCObligacion.deleted_at.is_(None)).group_by(GRCObligacion.estado_cumplimiento))).all()
    por_estado = {srv.valor_json(e): n for e, n in evals}
    aplicables = sum(n for e, n in por_estado.items() if e not in ("no_aplica", "en_evaluacion"))
    cumplen = por_estado.get("cumple", 0) + 0.5 * por_estado.get("cumple_parcial", 0)

    calor_inh: Dict[str, int] = defaultdict(int)
    calor_res: Dict[str, int] = defaultdict(int)
    fuera = []
    for r in riesgos:
        if r.probabilidad_inherente and r.impacto_inherente:
            calor_inh[f"{r.probabilidad_inherente}-{r.impacto_inherente}"] += 1
        if r.probabilidad_residual and r.impacto_residual:
            calor_res[f"{r.probabilidad_residual}-{r.impacto_residual}"] += 1
        tope = (apetito.get(r.tipo) or {}).get("apetito")
        nivel = r.nivel_residual or r.nivel_inherente
        if tope and nivel and nivel > int(tope) and r.estado in abiertos:
            fuera.append({"id": r.id, "codigo": r.codigo, "nombre": r.nombre, "nivel": nivel, "apetito": int(tope)})

    kris = (await db.execute(select(GRCKri).where(GRCKri.deleted_at.is_(None)))).scalars().all()
    ultimas: Dict[int, GRCKriMedicion] = {}
    for m in (await db.execute(select(GRCKriMedicion).order_by(GRCKriMedicion.periodo))).scalars():
        ultimas[m.kri_id] = m
    estados_kri = Counter(srv.estado_kri(ultimas[k.id].valor if k.id in ultimas else None, k.direccion,
                                         k.umbral_alerta, k.umbral_critico) for k in kris)
    ag = await agenda(60, db)
    top = sorted([r for r in riesgos if r.estado in abiertos],
                 key=lambda r: -(r.nivel_residual or r.nivel_inherente or 0))[:8]
    usuarios = await srv.mapa_usuarios(db)
    return {
        "riesgos": {"total": len(riesgos), "abiertos": sum(1 for r in riesgos if r.estado in abiertos),
                    "criticos": sum(1 for r in riesgos if r.prioridad == PrioridadRiesgoGRCEnum.CRITICA
                                    and r.estado in abiertos),
                    "fuera_de_apetito": fuera,
                    "por_prioridad": dict(Counter(srv.valor_json(r.prioridad) or "sin_evaluar" for r in riesgos))},
        "calor_inherente": calor_inh, "calor_residual": calor_res,
        "controles": {"total": len(controles), "probados": len(probados), "efectivos": len(efectivos),
                      "efectividad_pct": round(len(efectivos) / len(probados) * 100, 1) if probados else None,
                      "prueba_vencida": sum(1 for c in controles if c.proxima_evaluacion and c.proxima_evaluacion < hoy)},
        "cumplimiento": {"por_estado": por_estado,
                         "indice_pct": round(cumplen / aplicables * 100, 1) if aplicables else None},
        "hallazgos": {"abiertos": await _n(db, GRCHallazgo, GRCHallazgo.estado != EstadoHallazgoGRCEnum.CERRADO),
                      "vencidos": await _n(db, GRCHallazgo, GRCHallazgo.estado != EstadoHallazgoGRCEnum.CERRADO,
                                           GRCHallazgo.fecha_limite < hoy)},
        "incidentes": {"abiertos": await _n(db, GRCIncidente, GRCIncidente.estado != "cerrado"),
                       "ultimos_90": await _n(db, GRCIncidente, GRCIncidente.fecha_ocurrencia >= hoy - timedelta(days=90))},
        "politicas": {"publicadas": await _n(db, GRCPolitica, GRCPolitica.estado == EstadoPoliticaGRCEnum.PUBLICADA),
                      "en_revision": await _n(db, GRCPolitica, GRCPolitica.estado == EstadoPoliticaGRCEnum.EN_REVISION),
                      "revision_vencida": await _n(db, GRCPolitica, GRCPolitica.estado == EstadoPoliticaGRCEnum.PUBLICADA,
                                                   GRCPolitica.fecha_revision < hoy)},
        "auditorias": {"en_curso": await _n(db, GRCAuditoria, GRCAuditoria.estado.in_(["en_ejecucion", "en_revision"]))},
        "terceros": {"criticos": await _n(db, GRCTercero, GRCTercero.nivel_riesgo.in_(["alto", "critico"]),
                                          GRCTercero.estado == "activo")},
        "kris": dict(estados_kri),
        "agenda": {"vencidos": ag["vencidos"], "por_vencer": ag["por_vencer"], "proximos": ag["items"][:10]},
        "top_riesgos": [{"id": r.id, "codigo": r.codigo, "nombre": r.nombre, "tipo": r.tipo,
                         "nivel_inherente": r.nivel_inherente, "nivel_residual": r.nivel_residual,
                         "prioridad": srv.valor_json(r.prioridad), "responsable": usuarios.get(r.responsable_id)}
                        for r in top],
    }


# ── Responsables: qué tiene a cargo cada persona ─────────────────────────────

@router.get("/responsables")
async def responsables(db: AsyncSession = Depends(get_db)):
    conteo: Dict[int, dict] = {}
    for p in await srv.personas_grc(db):
        conteo[p["id"]] = {"usuario_id": p["id"], "nombre": p["nombre"], "cargo": p["cargo"],
                           "riesgos": 0, "controles": 0, "obligaciones": 0, "hallazgos_abiertos": 0,
                           "planes_pendientes": 0}

    async def sumar(modelo, clave, *cond):
        for uid, n in (await db.execute(select(modelo.responsable_id, func.count()).where(
                modelo.deleted_at.is_(None), modelo.responsable_id.isnot(None), *cond)
                .group_by(modelo.responsable_id))).all():
            if uid in conteo:
                conteo[uid][clave] += n

    await sumar(GRCRiesgo, "riesgos", GRCRiesgo.estado.notin_([EstadoRiesgoGRCEnum.CERRADO, EstadoRiesgoGRCEnum.MITIGADO]))
    await sumar(GRCControl, "controles")
    await sumar(GRCObligacion, "obligaciones")
    await sumar(GRCHallazgo, "hallazgos_abiertos", GRCHallazgo.estado != EstadoHallazgoGRCEnum.CERRADO)
    await sumar(GRCPlanAccion, "planes_pendientes", GRCPlanAccion.avance < 100)
    return sorted(conteo.values(), key=lambda x: -(x["riesgos"] + x["controles"] + x["obligaciones"]
                                                     + x["hallazgos_abiertos"] + x["planes_pendientes"]))


# ── Reporte para la junta ────────────────────────────────────────────────────

@router.get("/reporte-junta")
async def reporte_junta(db: AsyncSession = Depends(get_db)):
    """Lo que una junta directiva o un ente de control pide ver: perfil de
    riesgo, cumplimiento por marco normativo, eficacia del control interno,
    hallazgos e incidentes."""
    t = await tablero(db)
    por_marco: Dict[str, Counter] = defaultdict(Counter)
    for o in (await db.execute(select(GRCObligacion).where(GRCObligacion.deleted_at.is_(None)))).scalars():
        por_marco[o.marco or "Sin marco"][srv.valor_json(o.estado_cumplimiento)] += 1
    marcos = []
    for marco, c in sorted(por_marco.items()):
        aplic = sum(n for e, n in c.items() if e not in ("no_aplica", "en_evaluacion"))
        marcos.append({"marco": marco, "obligaciones": sum(c.values()), **dict(c),
                       "indice_pct": round((c.get("cumple", 0) + 0.5 * c.get("cumple_parcial", 0)) / aplic * 100, 1)
                       if aplic else None})
    sev = Counter(srv.valor_json(h.severidad) or "sin_severidad" for h in (await db.execute(select(GRCHallazgo).where(
        GRCHallazgo.deleted_at.is_(None), GRCHallazgo.estado != EstadoHallazgoGRCEnum.CERRADO))).scalars())
    perdida = (await db.execute(select(func.coalesce(func.sum(GRCIncidente.perdida_estimada), 0)).where(
        GRCIncidente.deleted_at.is_(None), GRCIncidente.fecha_ocurrencia >= date.today() - timedelta(days=365)))).scalar()
    return {"fecha": date.today().isoformat(), "tablero": t, "cumplimiento_por_marco": marcos,
            "hallazgos_abiertos_por_severidad": dict(sev), "perdida_incidentes_12m": float(perdida or 0)}
