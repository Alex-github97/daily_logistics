"""GRC — Gobierno, Riesgo y Cumplimiento.

Cada recurso (comités, políticas, riesgos, controles…) se declara una vez con
lo que lo hace particular —qué campos son personas, cuáles son catálogos, de
quién depende, qué calcula el servidor— y las cinco rutas (listar, ver, crear,
editar, retirar) salen de esa declaración. Así todas validan igual, todas dejan
historial y ninguna acepta texto donde va una persona o un catálogo.
"""
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple, Type

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import grc_servicio as srv
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.grc import (
    EstadoHallazgoGRCEnum, EstadoPoliticaGRCEnum, GRCAuditoria, GRCComite, GRCComiteMiembro,
    GRCComiteSesion, GRCContinuidad, GRCControl, GRCEvaluacionTercero, GRCEvidencia,
    GRCHallazgo, GRCIncidente, GRCKri, GRCKriMedicion, GRCMatrizCumplimiento, GRCObligacion,
    GRCPlanAccion, GRCPolitica, GRCPoliticaAceptacion, GRCPruebaControl, GRCRiesgo,
    GRCRiesgoControl, GRCSimulacro, GRCTercero, GRCTratamiento, GRCVinculo,
    EstadoCumplimientoGRCEnum,
)
from app.application.schemas import grc as esq

router = APIRouter(prefix="/grc", tags=["GRC"])

GLOBAL_PROCESO = ("GLOBAL", "PROCESO", "proceso")
GLOBAL_AREA = ("GLOBAL", "AREA", "área")


async def _next_code(db: AsyncSession, prefix: str, model) -> str:
    """Siguiente consecutivo del año: el mayor sufijo usado, no un conteo
    (contar choca con el UNIQUE en cuanto se retira una fila)."""
    patron = f"{prefix}-{date.today().year}-"
    maximo = 0
    for (codigo,) in (await db.execute(select(model.codigo).where(model.codigo.like(f"{patron}%")))).all():
        sufijo = (codigo or "")[len(patron):]
        if sufijo.isdigit():
            maximo = max(maximo, int(sufijo))
    return f"{patron}{maximo + 1:03d}"


async def _vivo(db: AsyncSession, model, id: int, nombre: str):
    obj = await db.get(model, id)
    if obj is None or getattr(obj, "deleted_at", None) is not None:
        raise HTTPException(404, f"{nombre} no encontrado")
    return obj


Hook = Optional[Callable[..., Awaitable[Any]]]


class Recurso:
    def __init__(self, ruta: str, clave: str, nombre: str, modelo, entrada: Type[BaseModel], *,
                 prefijo: Optional[str] = None,
                 personas: Sequence[str] = (), listas_personas: Sequence[str] = (),
                 catalogos: Optional[Dict[str, tuple]] = None,
                 padres: Optional[Dict[str, Tuple[Any, str]]] = None,
                 no_columnas: Sequence[str] = (),
                 filtros: Sequence[str] = (), orden=None,
                 antes: Hook = None, despues: Hook = None, enriquecer: Hook = None,
                 al_retirar: Hook = None):
        self.ruta, self.clave, self.nombre, self.modelo, self.entrada = ruta, clave, nombre, modelo, entrada
        self.prefijo = prefijo
        self.personas, self.listas_personas = tuple(personas), tuple(listas_personas)
        self.catalogos = catalogos or {}
        self.padres = padres or {}
        self.no_columnas = tuple(no_columnas)
        self.filtros, self.orden = tuple(filtros), orden
        self.antes, self.despues, self.enriquecer, self.al_retirar = antes, despues, enriquecer, al_retirar

    async def salida(self, db: AsyncSession, objs: list, usuarios=None) -> List[dict]:
        usuarios = usuarios if usuarios is not None else await srv.mapa_usuarios(db)
        filas = [srv.como_dict(o, usuarios, self.personas, self.listas_personas) for o in objs]
        if self.enriquecer and filas:
            await self.enriquecer(db, objs, filas, usuarios)
        return filas

    async def validar(self, db: AsyncSession, datos: dict, actual: Optional[dict]) -> None:
        await srv.validar_catalogos(db, datos, self.catalogos)
        campos = [c for c in self.personas + self.listas_personas if c in datos]
        await srv.validar_personas(db, {c: datos[c] for c in campos}, actual or {})
        for campo, (modelo, etiqueta) in self.padres.items():
            vid = datos.get(campo)
            if vid is not None and (actual or {}).get(campo) != vid:
                padre = await db.get(modelo, vid)
                if padre is None or getattr(padre, "deleted_at", None) is not None:
                    raise HTTPException(422, f"{etiqueta} elegido no existe.")


def montar(rec: Recurso):
    entrada = rec.entrada

    async def listar(request: Request, db: AsyncSession = Depends(get_db)):
        q = select(rec.modelo).where(rec.modelo.deleted_at.is_(None))
        for f in rec.filtros:
            v = request.query_params.get(f)
            if v not in (None, ""):
                col = getattr(rec.modelo, f)
                q = q.where(col == (int(v) if f.endswith("_id") else v))
        if rec.orden is not None:
            q = q.order_by(*rec.orden) if isinstance(rec.orden, (list, tuple)) else q.order_by(rec.orden)
        return await rec.salida(db, list((await db.execute(q)).scalars()))

    async def ver(id: int, db: AsyncSession = Depends(get_db)):
        obj = await _vivo(db, rec.modelo, id, rec.nombre)
        return (await rec.salida(db, [obj]))[0]

    async def crear(data: entrada, db: AsyncSession = Depends(get_db),  # type: ignore[valid-type]
                    yo: Usuario = Depends(get_current_user)):
        datos = data.model_dump()
        extras = {k: datos.pop(k) for k in rec.no_columnas if k in datos}
        await rec.validar(db, datos, None)
        obj = rec.modelo(**datos)
        if rec.prefijo:
            obj.codigo = await _next_code(db, rec.prefijo, rec.modelo)
        if rec.antes:
            await rec.antes(db, obj, datos, extras, None, yo)
        db.add(obj)
        await db.flush()
        if rec.despues:
            await rec.despues(db, obj, extras, True, yo)
        await srv.registrar(db, rec.clave, obj.id, "crear", yo.id)
        await db.commit()
        await db.refresh(obj)
        return (await rec.salida(db, [obj]))[0]

    async def editar(id: int, data: entrada, db: AsyncSession = Depends(get_db),  # type: ignore[valid-type]
                     yo: Usuario = Depends(get_current_user)):
        obj = await _vivo(db, rec.modelo, id, rec.nombre)
        antes = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        datos = data.model_dump()
        extras = {k: datos.pop(k) for k in rec.no_columnas if k in datos}
        await rec.validar(db, datos, antes)
        for k, v in datos.items():
            setattr(obj, k, v)
        # La regla de la entidad va después de aplicar el formulario: lo que
        # el servidor calcula no puede quedar pisado por un vacío del formulario.
        if rec.antes:
            await rec.antes(db, obj, datos, extras, antes, yo)
        await db.flush()
        if rec.despues:
            await rec.despues(db, obj, extras, False, yo)
        for c in obj.__table__.columns:
            # Las marcas de tiempo quedan vencidas tras el flush; leerlas
            # dispararía una consulta perezosa fuera de lugar.
            if c.name in ("updated_at", "created_at"):
                continue
            a, n = antes.get(c.name), getattr(obj, c.name)
            if srv.valor_json(a) != srv.valor_json(n):
                await srv.registrar(db, rec.clave, obj.id, "editar", yo.id, c.name, a, n)
        await db.commit()
        await db.refresh(obj)
        return (await rec.salida(db, [obj]))[0]

    async def retirar(id: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
        obj = await _vivo(db, rec.modelo, id, rec.nombre)
        if rec.al_retirar:
            await rec.al_retirar(db, obj)
        obj.deleted_at = srv.AHORA()
        if hasattr(obj, "activo"):
            obj.activo = False
        await srv.registrar(db, rec.clave, obj.id, "retirar", yo.id)
        await db.flush()
        if rec.despues:
            await rec.despues(db, obj, {}, None, yo)   # None = se retiró
        await db.commit()

    r = rec.ruta
    router.add_api_route(f"/{r}", listar, methods=["GET"], name=f"listar_{r}")
    router.add_api_route(f"/{r}/{{id}}", ver, methods=["GET"], name=f"ver_{r}")
    router.add_api_route(f"/{r}", crear, methods=["POST"], status_code=201, name=f"crear_{r}")
    router.add_api_route(f"/{r}/{{id}}", editar, methods=["PUT"], name=f"editar_{r}")
    router.add_api_route(f"/{r}/{{id}}", retirar, methods=["DELETE"], status_code=204, name=f"retirar_{r}")


async def _contar(db, columna, ids, *cond) -> Dict[int, int]:
    if not ids:
        return {}
    filas = (await db.execute(select(columna, func.count()).where(columna.in_(ids), *cond)
                              .group_by(columna))).all()
    return dict(filas)


def _hoy() -> date:
    return date.today()


# ═════════════════════════════════════════════════════════════════════════════
# GOBIERNO
# ═════════════════════════════════════════════════════════════════════════════

async def _comite_despues(db, obj, extras, creando, yo):
    if creando is None or "miembros" not in extras:
        return
    nuevos = set(extras["miembros"] or [])
    await srv.validar_personas(db, {"miembros": list(nuevos)}, {})
    actuales = {m.usuario_id: m for m in (await db.execute(
        select(GRCComiteMiembro).where(GRCComiteMiembro.comite_id == obj.id))).scalars()}
    for uid, m in actuales.items():
        if uid not in nuevos:
            await db.delete(m)
    for uid in nuevos - set(actuales):
        db.add(GRCComiteMiembro(comite_id=obj.id, usuario_id=uid))


async def _comite_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    miembros: Dict[int, list] = {}
    for m in (await db.execute(select(GRCComiteMiembro).where(GRCComiteMiembro.comite_id.in_(ids)))).scalars():
        miembros.setdefault(m.comite_id, []).append(m.usuario_id)
    riesgos = await _contar(db, GRCRiesgo.comite_id, ids, GRCRiesgo.deleted_at.is_(None))
    ultima = dict((await db.execute(select(GRCComiteSesion.comite_id, func.max(GRCComiteSesion.fecha))
                                    .where(GRCComiteSesion.comite_id.in_(ids), GRCComiteSesion.deleted_at.is_(None))
                                    .group_by(GRCComiteSesion.comite_id))).all())
    proxima = dict((await db.execute(select(GRCComiteSesion.comite_id, func.max(GRCComiteSesion.proxima))
                                     .where(GRCComiteSesion.comite_id.in_(ids), GRCComiteSesion.deleted_at.is_(None))
                                     .group_by(GRCComiteSesion.comite_id))).all())
    for f in filas:
        f["miembros"] = miembros.get(f["id"], [])
        f["miembros_nombres"] = [usuarios.get(u, f"#{u}") for u in f["miembros"]]
        f["riesgos"] = riesgos.get(f["id"], 0)
        f["ultima_sesion"] = srv.valor_json(ultima.get(f["id"]))
        f["proxima_sesion"] = srv.valor_json(proxima.get(f["id"]))


montar(Recurso("comites", "comite", "Comité", GRCComite, esq.ComiteIn,
               personas=("presidente_id", "secretario_id"), no_columnas=("miembros",),
               catalogos={"tipo": ("GRC", "TIPO_COMITE", "tipo de comité"),
                          "periodicidad": ("GRC", "PERIODICIDAD", "periodicidad")},
               orden=GRCComite.nombre, despues=_comite_despues, enriquecer=_comite_enriquecer))


async def _sesion_despues(db, obj, extras, creando, yo):
    if creando is None or "riesgos" not in extras:
        return
    await db.execute(text("DELETE FROM grc_vinculo WHERE origen_tipo = 'sesion' AND origen_id = :i"), {"i": obj.id})
    for rid in set(extras["riesgos"] or []):
        await _vivo(db, GRCRiesgo, rid, "Riesgo")
        db.add(GRCVinculo(origen_tipo="sesion", origen_id=obj.id, destino_tipo="riesgo", destino_id=rid))


async def _sesion_enriquecer(db, objs, filas, usuarios):
    comites = {c.id: c for c in (await db.execute(select(GRCComite).where(
        GRCComite.id.in_([o.comite_id for o in objs])))).scalars()}
    vinc: Dict[int, list] = {}
    for v in (await db.execute(select(GRCVinculo).where(
            GRCVinculo.origen_tipo == "sesion", GRCVinculo.origen_id.in_([o.id for o in objs])))).scalars():
        vinc.setdefault(v.origen_id, []).append(v.destino_id)
    for f in filas:
        c = comites.get(f["comite_id"])
        f["comite_nombre"] = c.nombre if c else None
        quorum = c.quorum_minimo if c else None
        f["quorum_ok"] = None if not quorum else len(f["asistentes"] or []) >= quorum
        f["riesgos"] = vinc.get(f["id"], [])


montar(Recurso("sesiones", "sesion", "Sesión", GRCComiteSesion, esq.SesionIn,
               listas_personas=("asistentes",), no_columnas=("riesgos",),
               padres={"comite_id": (GRCComite, "El comité")}, filtros=("comite_id",),
               orden=GRCComiteSesion.fecha.desc(), despues=_sesion_despues, enriquecer=_sesion_enriquecer))


async def _politica_antes(db, obj, datos, extras, antes, yo):
    if antes is None:
        obj.estado = EstadoPoliticaGRCEnum.BORRADOR
        return
    aprobada = antes.get("estado") in (EstadoPoliticaGRCEnum.APROBADA, EstadoPoliticaGRCEnum.PUBLICADA)
    if not aprobada:
        return
    if datos.get("version") != antes.get("version"):
        # Versión nueva: vuelve a revisión y a aprobación. Las aceptaciones
        # son por versión, así que se piden de nuevo solas.
        obj.estado = EstadoPoliticaGRCEnum.EN_REVISION
        obj.fecha_aprobacion = None
        return
    # Cambiar el texto de una política aprobada sin subir la versión dejaría
    # aceptaciones firmadas sobre un contenido distinto.
    if any(srv.valor_json(datos.get(k)) != srv.valor_json(antes.get(k))
           for k in ("alcance", "descripcion", "nombre")):
        raise HTTPException(409, "La política ya está aprobada: para cambiar su contenido suba la versión "
                                 "(vuelve a revisión y las aceptaciones se piden de nuevo).")


async def _politica_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    acept: Dict[Tuple[int, str], int] = {}
    for pid, ver, n in (await db.execute(select(GRCPoliticaAceptacion.politica_id, GRCPoliticaAceptacion.version,
                                                func.count()).where(GRCPoliticaAceptacion.politica_id.in_(ids))
                                         .group_by(GRCPoliticaAceptacion.politica_id, GRCPoliticaAceptacion.version))).all():
        acept[(pid, ver)] = n
    personas = len(await srv.personas_grc(db))
    hoy = _hoy()
    for f in filas:
        f["aceptaciones"] = acept.get((f["id"], f["version"]), 0)
        f["aceptaciones_esperadas"] = personas if f["aceptaciones_requeridas"] else 0
        f["vencida"] = bool(f["estado"] == "publicada" and f["fecha_revision"]
                            and date.fromisoformat(f["fecha_revision"]) < hoy)


montar(Recurso("politicas", "politica", "Política", GRCPolitica, esq.PoliticaIn, prefijo="POL",
               personas=("propietario_id", "aprobador_id"),
               catalogos={"tipo": ("GRC", "TIPO_POLITICA", "tipo de política"),
                          "periodicidad_revision": ("GRC", "PERIODICIDAD", "periodicidad")},
               filtros=("estado",), orden=GRCPolitica.nombre,
               antes=_politica_antes, enriquecer=_politica_enriquecer))


# ═════════════════════════════════════════════════════════════════════════════
# CUMPLIMIENTO
# ═════════════════════════════════════════════════════════════════════════════

async def _vinculos_de(db, tipo: str, ids: List[int]) -> Dict[int, Dict[str, int]]:
    """Cuántos vínculos tiene cada registro, por tipo del otro extremo."""
    salida: Dict[int, Dict[str, int]] = {}
    if not ids:
        return salida
    for o_t, o_id, d_t, d_id in (await db.execute(select(
            GRCVinculo.origen_tipo, GRCVinculo.origen_id, GRCVinculo.destino_tipo, GRCVinculo.destino_id))).all():
        if o_t == tipo and o_id in ids:
            salida.setdefault(o_id, {}).setdefault(d_t, 0)
            salida[o_id][d_t] += 1
        if d_t == tipo and d_id in ids:
            salida.setdefault(d_id, {}).setdefault(o_t, 0)
            salida[d_id][o_t] += 1
    return salida


async def _obligacion_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    vinc = await _vinculos_de(db, "obligacion", ids)
    ultimas = {}
    for e in (await db.execute(select(GRCMatrizCumplimiento).where(
            GRCMatrizCumplimiento.obligacion_id.in_(ids), GRCMatrizCumplimiento.deleted_at.is_(None))
            .order_by(GRCMatrizCumplimiento.ultima_evaluacion.asc().nullsfirst(), GRCMatrizCumplimiento.id))).scalars():
        ultimas[e.obligacion_id] = e
    hoy = _hoy()
    for f in filas:
        v = vinc.get(f["id"], {})
        f["controles"] = v.get("control", 0)
        f["politicas"] = v.get("politica", 0)
        e = ultimas.get(f["id"])
        f["ultima_evaluacion"] = srv.valor_json(e.ultima_evaluacion) if e else None
        f["proxima_evaluacion"] = srv.valor_json(e.proxima_evaluacion) if e else None
        f["puntaje"] = e.puntaje if e else None
        f["vencida"] = bool(f["fecha_vencimiento"] and date.fromisoformat(f["fecha_vencimiento"]) < hoy)


montar(Recurso("obligaciones", "obligacion", "Obligación", GRCObligacion, esq.ObligacionIn, prefijo="OBL",
               personas=("responsable_id",),
               catalogos={"tipo": ("GRC", "TIPO_OBLIGACION", "tipo de obligación"),
                          "marco": ("GRC", "MARCO_NORMATIVO", "marco normativo"),
                          "periodicidad": ("GRC", "PERIODICIDAD", "periodicidad"),
                          "pais": ("GLOBAL", "PAIS", "país"),
                          "proceso": GLOBAL_PROCESO, "area": GLOBAL_AREA},
               filtros=("tipo", "marco", "estado_cumplimiento"), orden=GRCObligacion.nombre,
               enriquecer=_obligacion_enriquecer))


async def _cumplimiento_antes(db, obj, datos, extras, antes, yo):
    if datos.get("estado") in (EstadoCumplimientoGRCEnum.CUMPLE, "cumple") and not (datos.get("evidencias") or "").strip():
        raise HTTPException(422, "Para marcar «cumple» hay que decir con qué evidencia.")
    obj.ultima_evaluacion = datos.get("ultima_evaluacion") or _hoy()
    oblig = await db.get(GRCObligacion, datos["obligacion_id"])
    dias = await srv.dias_de(db, oblig.periodicidad if oblig else None)
    obj.proxima_evaluacion = obj.ultima_evaluacion + timedelta(days=dias) if dias else None


async def _cumplimiento_despues(db, obj, extras, creando, yo):
    """El estado de la obligación es el de su evaluación más reciente."""
    ultima = (await db.execute(select(GRCMatrizCumplimiento).where(
        GRCMatrizCumplimiento.obligacion_id == obj.obligacion_id, GRCMatrizCumplimiento.deleted_at.is_(None))
        .order_by(GRCMatrizCumplimiento.ultima_evaluacion.desc().nullslast(), GRCMatrizCumplimiento.id.desc())
        .limit(1))).scalar()
    oblig = await db.get(GRCObligacion, obj.obligacion_id)
    if oblig:
        oblig.estado_cumplimiento = ultima.estado if ultima else EstadoCumplimientoGRCEnum.EN_EVALUACION


async def _cumplimiento_enriquecer(db, objs, filas, usuarios):
    obl = {o.id: o for o in (await db.execute(select(GRCObligacion).where(
        GRCObligacion.id.in_([x.obligacion_id for x in objs])))).scalars()}
    for f in filas:
        o = obl.get(f["obligacion_id"])
        f["obligacion_nombre"] = o.nombre if o else None
        f["obligacion_codigo"] = o.codigo if o else None
        f["marco"] = o.marco if o else None


montar(Recurso("cumplimiento", "cumplimiento", "Evaluación", GRCMatrizCumplimiento, esq.CumplimientoIn,
               personas=("responsable_id",), padres={"obligacion_id": (GRCObligacion, "La obligación")},
               catalogos={"proceso": GLOBAL_PROCESO, "area": GLOBAL_AREA},
               filtros=("obligacion_id", "estado"),
               orden=GRCMatrizCumplimiento.ultima_evaluacion.desc().nullslast(),
               antes=_cumplimiento_antes, despues=_cumplimiento_despues, enriquecer=_cumplimiento_enriquecer))


# ═════════════════════════════════════════════════════════════════════════════
# RIESGOS Y CONTROLES
# ═════════════════════════════════════════════════════════════════════════════

async def _control_despues(db, obj, extras, creando, yo):
    await srv.recalcular_control(db, obj)


async def _control_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    riesgos = await _contar(db, GRCRiesgoControl.control_id, ids)
    pruebas = await _contar(db, GRCPruebaControl.control_id, ids, GRCPruebaControl.deleted_at.is_(None))
    vinc = await _vinculos_de(db, "control", ids)
    hoy = _hoy()
    for f in filas:
        f["riesgos"] = riesgos.get(f["id"], 0)
        f["pruebas"] = pruebas.get(f["id"], 0)
        f["obligaciones"] = vinc.get(f["id"], {}).get("obligacion", 0)
        f["prueba_vencida"] = bool(f["proxima_evaluacion"] and date.fromisoformat(f["proxima_evaluacion"]) < hoy)


async def _control_retirar(db, obj):
    # Primero los riesgos que mitigaba: después de soltar los vínculos ya no
    # habría cómo saber cuáles recalcular.
    riesgos = (await db.execute(select(GRCRiesgoControl.riesgo_id).where(
        GRCRiesgoControl.control_id == obj.id))).scalars().all()
    await db.execute(text("DELETE FROM grc_riesgo_control WHERE control_id = :i"), {"i": obj.id})
    for rid in riesgos:
        r = await db.get(GRCRiesgo, rid)
        if r is not None and r.deleted_at is None:
            await srv.recalcular_riesgo(db, r)


montar(Recurso("controles", "control", "Control", GRCControl, esq.ControlIn, prefijo="CTL",
               personas=("responsable_id",),
               catalogos={"frecuencia": ("GRC", "FRECUENCIA_CONTROL", "frecuencia"),
                          "periodicidad_prueba": ("GRC", "PERIODICIDAD", "periodicidad de prueba"),
                          "proceso": GLOBAL_PROCESO, "area": GLOBAL_AREA},
               filtros=("tipo", "efectividad", "proceso"), orden=GRCControl.nombre,
               despues=_control_despues, enriquecer=_control_enriquecer, al_retirar=_control_retirar))


async def _prueba_despues(db, obj, extras, creando, yo):
    control = await db.get(GRCControl, obj.control_id)
    if control is not None:
        await srv.recalcular_control(db, control)


montar(Recurso("pruebas", "prueba", "Prueba", GRCPruebaControl, esq.PruebaIn,
               personas=("probador_id",), padres={"control_id": (GRCControl, "El control")},
               filtros=("control_id",), orden=GRCPruebaControl.fecha.desc(), despues=_prueba_despues))


async def _riesgo_despues(db, obj, extras, creando, yo):
    if creando is not None:
        await srv.recalcular_riesgo(db, obj)


async def _riesgo_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    controles = await _contar(db, GRCRiesgoControl.riesgo_id, ids)
    incidentes = await _contar(db, GRCIncidente.riesgo_id, ids, GRCIncidente.deleted_at.is_(None))
    hallazgos = await _contar(db, GRCHallazgo.riesgo_id, ids, GRCHallazgo.deleted_at.is_(None))
    kris = await _contar(db, GRCKri.riesgo_id, ids, GRCKri.deleted_at.is_(None))
    tratamientos = await _contar(db, GRCTratamiento.riesgo_id, ids, GRCTratamiento.deleted_at.is_(None))
    apetito = await srv.metadatos_catalogo(db, "GRC", "CATEGORIA_RIESGO")
    comites = dict((await db.execute(select(GRCComite.id, GRCComite.nombre))).all())
    terceros = dict((await db.execute(select(GRCTercero.id, GRCTercero.nombre))).all())
    for f in filas:
        f["controles"] = controles.get(f["id"], 0)
        f["incidentes"] = incidentes.get(f["id"], 0)
        f["hallazgos"] = hallazgos.get(f["id"], 0)
        f["kris"] = kris.get(f["id"], 0)
        f["tratamientos"] = tratamientos.get(f["id"], 0)
        f["comite_nombre"] = comites.get(f["comite_id"])
        f["tercero_nombre"] = terceros.get(f["tercero_id"])
        tope = (apetito.get(f["tipo"]) or {}).get("apetito")
        nivel = f["nivel_residual"] or f["nivel_inherente"]
        f["apetito"] = tope
        f["fuera_de_apetito"] = bool(tope and nivel and nivel > int(tope))


async def _riesgo_retirar(db, obj):
    await db.execute(text("DELETE FROM grc_riesgo_control WHERE riesgo_id = :i"), {"i": obj.id})


montar(Recurso("riesgos", "riesgo", "Riesgo", GRCRiesgo, esq.RiesgoIn, prefijo="RSK",
               personas=("responsable_id",),
               catalogos={"tipo": ("GRC", "CATEGORIA_RIESGO", "categoría de riesgo"),
                          "proceso": GLOBAL_PROCESO, "area": GLOBAL_AREA},
               padres={"comite_id": (GRCComite, "El comité"), "tercero_id": (GRCTercero, "El tercero")},
               filtros=("tipo", "estado", "prioridad", "proceso", "comite_id", "tercero_id", "responsable_id"),
               orden=(GRCRiesgo.nivel_residual.desc().nullslast(), GRCRiesgo.nivel_inherente.desc().nullslast()),
               despues=_riesgo_despues, enriquecer=_riesgo_enriquecer, al_retirar=_riesgo_retirar))


def _estado_por_avance(obj):
    obj.estado = "completado" if obj.avance >= 100 else ("en_curso" if obj.avance > 0 else "pendiente")


async def _avance_antes(db, obj, datos, extras, antes, yo):
    obj.avance = datos.get("avance") or 0
    _estado_por_avance(obj)


montar(Recurso("tratamientos", "tratamiento", "Tratamiento", GRCTratamiento, esq.TratamientoIn,
               personas=("responsable_id",), padres={"riesgo_id": (GRCRiesgo, "El riesgo")},
               filtros=("riesgo_id", "estado"), orden=GRCTratamiento.fecha_objetivo.asc().nullslast(),
               antes=_avance_antes))


async def _kri_antes(db, obj, datos, extras, antes, yo):
    a, c = datos["umbral_alerta"], datos["umbral_critico"]
    if datos.get("direccion", "sube") == "sube" and c < a:
        raise HTTPException(422, "Si el indicador empeora al subir, el umbral crítico debe ser mayor o igual al de alerta.")
    if datos.get("direccion") == "baja" and c > a:
        raise HTTPException(422, "Si el indicador empeora al bajar, el umbral crítico debe ser menor o igual al de alerta.")


async def _kri_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    ultimas: Dict[int, GRCKriMedicion] = {}
    for m in (await db.execute(select(GRCKriMedicion).where(GRCKriMedicion.kri_id.in_(ids))
                               .order_by(GRCKriMedicion.periodo))).scalars():
        ultimas[m.kri_id] = m
    riesgos = dict((await db.execute(select(GRCRiesgo.id, GRCRiesgo.nombre).where(
        GRCRiesgo.id.in_([o.riesgo_id for o in objs])))).all())
    for f in filas:
        m = ultimas.get(f["id"])
        f["riesgo_nombre"] = riesgos.get(f["riesgo_id"])
        f["ultimo_valor"] = float(m.valor) if m else None
        f["ultimo_periodo"] = m.periodo if m else None
        f["estado"] = srv.estado_kri(m.valor if m else None, f["direccion"], f["umbral_alerta"], f["umbral_critico"])


montar(Recurso("kris", "kri", "Indicador", GRCKri, esq.KriIn,
               personas=("responsable_id",), padres={"riesgo_id": (GRCRiesgo, "El riesgo")},
               catalogos={"periodicidad": ("GRC", "PERIODICIDAD", "periodicidad")},
               filtros=("riesgo_id",), orden=GRCKri.nombre, antes=_kri_antes, enriquecer=_kri_enriquecer))


# ═════════════════════════════════════════════════════════════════════════════
# AUDITORÍA, HALLAZGOS E INCIDENTES
# ═════════════════════════════════════════════════════════════════════════════

async def _auditoria_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    total = await _contar(db, GRCHallazgo.auditoria_id, ids, GRCHallazgo.deleted_at.is_(None))
    abiertos = await _contar(db, GRCHallazgo.auditoria_id, ids, GRCHallazgo.deleted_at.is_(None),
                             GRCHallazgo.estado != EstadoHallazgoGRCEnum.CERRADO)
    for f in filas:
        f["hallazgos"] = total.get(f["id"], 0)
        f["hallazgos_abiertos"] = abiertos.get(f["id"], 0)


async def _auditoria_antes(db, obj, datos, extras, antes, yo):
    if datos.get("fecha_inicio") and datos.get("fecha_fin") and datos["fecha_fin"] < datos["fecha_inicio"]:
        raise HTTPException(422, "La fecha de fin no puede ser anterior a la de inicio.")


montar(Recurso("auditorias", "auditoria", "Auditoría", GRCAuditoria, esq.AuditoriaIn, prefijo="AUD",
               personas=("auditor_lider_id",), listas_personas=("equipo",),
               catalogos={"tipo": ("GRC", "TIPO_AUDITORIA", "tipo de auditoría"),
                          "marco": ("GRC", "MARCO_NORMATIVO", "marco normativo"),
                          "proceso": GLOBAL_PROCESO, "area": GLOBAL_AREA},
               filtros=("estado", "tipo"), orden=GRCAuditoria.fecha_inicio.desc().nullslast(),
               antes=_auditoria_antes, enriquecer=_auditoria_enriquecer))


async def _hallazgo_antes(db, obj, datos, extras, antes, yo):
    if not datos.get("fecha_limite"):
        obj.fecha_limite = _hoy() + timedelta(days=await srv.parametro(db, "dias_plazo_hallazgo", 60))
    if datos.get("estado") == EstadoHallazgoGRCEnum.CERRADO and antes is not None:
        pendientes = (await db.execute(select(func.count()).select_from(GRCPlanAccion).where(
            GRCPlanAccion.hallazgo_id == obj.id, GRCPlanAccion.deleted_at.is_(None),
            GRCPlanAccion.avance < 100))).scalar()
        if pendientes:
            raise HTTPException(409, f"No se puede cerrar: tiene {pendientes} plan(es) de acción sin completar.")


async def _hallazgo_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    planes = await _contar(db, GRCPlanAccion.hallazgo_id, ids, GRCPlanAccion.deleted_at.is_(None))
    hechos = await _contar(db, GRCPlanAccion.hallazgo_id, ids, GRCPlanAccion.deleted_at.is_(None),
                           GRCPlanAccion.avance >= 100)
    auds = dict((await db.execute(select(GRCAuditoria.id, GRCAuditoria.codigo))).all())
    rsk = dict((await db.execute(select(GRCRiesgo.id, GRCRiesgo.codigo))).all())
    ctl = dict((await db.execute(select(GRCControl.id, GRCControl.codigo))).all())
    inc = dict((await db.execute(select(GRCIncidente.id, GRCIncidente.codigo))).all())
    hoy = _hoy()
    for f in filas:
        f["planes"] = planes.get(f["id"], 0)
        f["planes_completos"] = hechos.get(f["id"], 0)
        f["auditoria_codigo"] = auds.get(f["auditoria_id"])
        f["riesgo_codigo"] = rsk.get(f["riesgo_id"])
        f["control_codigo"] = ctl.get(f["control_id"])
        f["incidente_codigo"] = inc.get(f["incidente_id"])
        f["vencido"] = bool(f["estado"] != "cerrado" and f["fecha_limite"]
                            and date.fromisoformat(f["fecha_limite"]) < hoy)


montar(Recurso("hallazgos", "hallazgo", "Hallazgo", GRCHallazgo, esq.HallazgoIn, prefijo="HAL",
               personas=("responsable_id",),
               catalogos={"tipo": ("GRC", "TIPO_HALLAZGO", "tipo de hallazgo"),
                          "proceso": GLOBAL_PROCESO, "area": GLOBAL_AREA},
               padres={"auditoria_id": (GRCAuditoria, "La auditoría"), "incidente_id": (GRCIncidente, "El incidente"),
                       "riesgo_id": (GRCRiesgo, "El riesgo"), "control_id": (GRCControl, "El control")},
               filtros=("estado", "severidad", "auditoria_id", "riesgo_id", "control_id", "incidente_id"),
               orden=GRCHallazgo.fecha_limite.asc().nullslast(),
               antes=_hallazgo_antes, enriquecer=_hallazgo_enriquecer))


montar(Recurso("planes", "plan", "Plan de acción", GRCPlanAccion, esq.PlanIn,
               personas=("responsable_id",), padres={"hallazgo_id": (GRCHallazgo, "El hallazgo")},
               filtros=("hallazgo_id", "estado"), orden=GRCPlanAccion.fecha_objetivo.asc().nullslast(),
               antes=_avance_antes))


async def _incidente_antes(db, obj, datos, extras, antes, yo):
    if datos.get("estado") == "cerrado":
        if not (datos.get("causa_raiz") or "").strip():
            raise HTTPException(422, "Para cerrar el incidente hay que registrar la causa raíz.")
        if not obj.fecha_cierre:
            obj.fecha_cierre = datetime.utcnow()
    else:
        obj.fecha_cierre = None
    if antes is None and not datos.get("reportado_por_id"):
        obj.reportado_por_id = yo.id


async def _incidente_enriquecer(db, objs, filas, usuarios):
    rsk = dict((await db.execute(select(GRCRiesgo.id, GRCRiesgo.codigo))).all())
    ctl = dict((await db.execute(select(GRCControl.id, GRCControl.codigo))).all())
    hal = await _contar(db, GRCHallazgo.incidente_id, [o.id for o in objs], GRCHallazgo.deleted_at.is_(None))
    for f in filas:
        f["riesgo_codigo"] = rsk.get(f["riesgo_id"])
        f["control_codigo"] = ctl.get(f["control_id"])
        f["hallazgos"] = hal.get(f["id"], 0)


montar(Recurso("incidentes", "incidente", "Incidente", GRCIncidente, esq.IncidenteIn, prefijo="INC",
               personas=("reportado_por_id", "responsable_id"),
               catalogos={"tipo": ("GRC", "TIPO_INCIDENTE", "tipo de incidente"),
                          "proceso": GLOBAL_PROCESO, "area": GLOBAL_AREA},
               padres={"riesgo_id": (GRCRiesgo, "El riesgo"), "control_id": (GRCControl, "El control")},
               filtros=("estado", "tipo", "severidad", "riesgo_id"),
               orden=GRCIncidente.fecha_ocurrencia.desc().nullslast(),
               antes=_incidente_antes, enriquecer=_incidente_enriquecer))


# ═════════════════════════════════════════════════════════════════════════════
# CONTINUIDAD
# ═════════════════════════════════════════════════════════════════════════════

async def _continuidad_antes(db, obj, datos, extras, antes, yo):
    rto, rpo, mtpd = datos.get("rto_horas"), datos.get("rpo_horas"), datos.get("mtpd_horas")
    if rto is not None and mtpd is not None and rto > mtpd:
        raise HTTPException(422, "El RTO no puede superar el tiempo máximo tolerable de interrupción (MTPD).")


async def _continuidad_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    ultimo: Dict[int, GRCSimulacro] = {}
    for s in (await db.execute(select(GRCSimulacro).where(GRCSimulacro.continuidad_id.in_(ids),
                                                          GRCSimulacro.deleted_at.is_(None))
                               .order_by(GRCSimulacro.fecha.asc().nullsfirst()))).scalars():
        ultimo[s.continuidad_id] = s
    vinc = await _vinculos_de(db, "continuidad", ids)
    hoy = _hoy()
    for f in filas:
        s = ultimo.get(f["id"])
        f["ultimo_simulacro"] = srv.valor_json(s.fecha) if s else None
        f["rto_logrado"] = s.rto_logrado_horas if s else None
        f["rto_cumplido"] = (None if not s or s.rto_logrado_horas is None or f["rto_horas"] is None
                             else s.rto_logrado_horas <= f["rto_horas"])
        f["riesgos"] = vinc.get(f["id"], {}).get("riesgo", 0)
        f["terceros"] = vinc.get(f["id"], {}).get("tercero", 0)
        dias = await srv.dias_de(db, f["periodicidad_revision"])
        prox = (date.fromisoformat(f["ultima_revision"]) + timedelta(days=dias)) if (dias and f["ultima_revision"]) else None
        f["proxima_revision"] = prox.isoformat() if prox else None
        f["revision_vencida"] = bool(prox and prox < hoy)


montar(Recurso("continuidad", "continuidad", "Plan de continuidad", GRCContinuidad, esq.ContinuidadIn,
               personas=("responsable_id",),
               catalogos={"proceso": ("GLOBAL", "PROCESO", "proceso"),
                          "sistemas_criticos": ("GRC", "SISTEMA_CRITICO", "sistema crítico"),
                          "periodicidad_revision": ("GRC", "PERIODICIDAD", "periodicidad")},
               filtros=("criticidad",), orden=GRCContinuidad.proceso,
               antes=_continuidad_antes, enriquecer=_continuidad_enriquecer))


async def _simulacro_enriquecer(db, objs, filas, usuarios):
    planes = dict((await db.execute(select(GRCContinuidad.id, GRCContinuidad.proceso))).all())
    for f in filas:
        f["continuidad_proceso"] = planes.get(f["continuidad_id"])


montar(Recurso("simulacros", "simulacro", "Simulacro", GRCSimulacro, esq.SimulacroIn,
               personas=("coordinador_id",), listas_personas=("participantes",),
               catalogos={"tipo": ("GRC", "TIPO_SIMULACRO", "tipo de simulacro"),
                          "resultado": ("GRC", "RESULTADO_SIMULACRO", "resultado")},
               padres={"continuidad_id": (GRCContinuidad, "El plan de continuidad")},
               filtros=("continuidad_id",), orden=GRCSimulacro.fecha.desc().nullslast(),
               enriquecer=_simulacro_enriquecer))


# ═════════════════════════════════════════════════════════════════════════════
# TERCEROS
# ═════════════════════════════════════════════════════════════════════════════

async def _tercero_antes(db, obj, datos, extras, antes, yo):
    for campo, tabla, etiqueta in (("proveedor_id", "proveedores", "El proveedor"),
                                   ("cliente_id", "crm_cliente", "El cliente")):
        vid = datos.get(campo)
        if vid is not None and not (await db.execute(text(f"SELECT 1 FROM {tabla} WHERE id = :i"), {"i": vid})).scalar():
            raise HTTPException(422, f"{etiqueta} elegido no existe.")


async def _tercero_enriquecer(db, objs, filas, usuarios):
    ids = [o.id for o in objs]
    ultima: Dict[int, GRCEvaluacionTercero] = {}
    for e in (await db.execute(select(GRCEvaluacionTercero).where(
            GRCEvaluacionTercero.tercero_id.in_(ids), GRCEvaluacionTercero.deleted_at.is_(None))
            .order_by(GRCEvaluacionTercero.fecha.asc().nullsfirst(), GRCEvaluacionTercero.id))).scalars():
        ultima[e.tercero_id] = e
    riesgos = await _contar(db, GRCRiesgo.tercero_id, ids, GRCRiesgo.deleted_at.is_(None))
    for f in filas:
        e = ultima.get(f["id"])
        f["ultimo_puntaje"] = float(e.puntaje_total) if e and e.puntaje_total is not None else None
        f["ultima_evaluacion"] = srv.valor_json(e.fecha) if e else None
        f["riesgos"] = riesgos.get(f["id"], 0)


montar(Recurso("terceros", "tercero", "Tercero", GRCTercero, esq.TerceroIn,
               personas=("responsable_id",),
               catalogos={"tipo": ("GRC", "TIPO_TERCERO", "tipo de tercero"),
                          "pais": ("GLOBAL", "PAIS", "país"),
                          "sector": ("CRM", "SECTOR_ECONOMICO", "sector")},
               filtros=("tipo", "nivel_riesgo", "estado"), orden=GRCTercero.nombre,
               antes=_tercero_antes, enriquecer=_tercero_enriquecer))


async def _evaluacion_antes(db, obj, datos, extras, antes, yo):
    notas = [datos.get(k) for k in ("cumplimiento_legal", "riesgo_reputacional", "solidez_financiera",
                                      "seguridad_info") if datos.get(k) is not None]
    if not notas:
        raise HTTPException(422, "Califique al menos un criterio.")
    obj.puntaje_total = round(sum(notas) / len(notas), 2)
    obj.clasificacion, _ = srv.clasificar_tercero(float(obj.puntaje_total))
    obj.fecha = datos.get("fecha") or _hoy()
    if not datos.get("periodo"):
        obj.periodo = obj.fecha.strftime("%Y-%m")
    if not datos.get("evaluador_id"):
        obj.evaluador_id = yo.id


async def _evaluacion_despues(db, obj, extras, creando, yo):
    ultima = (await db.execute(select(GRCEvaluacionTercero).where(
        GRCEvaluacionTercero.tercero_id == obj.tercero_id, GRCEvaluacionTercero.deleted_at.is_(None))
        .order_by(GRCEvaluacionTercero.fecha.desc().nullslast(), GRCEvaluacionTercero.id.desc()).limit(1))).scalar()
    tercero = await db.get(GRCTercero, obj.tercero_id)
    if tercero:
        tercero.nivel_riesgo = srv.clasificar_tercero(float(ultima.puntaje_total))[1] if ultima else None


montar(Recurso("evaluaciones", "evaluacion", "Evaluación", GRCEvaluacionTercero, esq.EvaluacionIn,
               personas=("evaluador_id",), padres={"tercero_id": (GRCTercero, "El tercero")},
               filtros=("tercero_id",), orden=GRCEvaluacionTercero.fecha.desc().nullslast(),
               antes=_evaluacion_antes, despues=_evaluacion_despues))


# ═════════════════════════════════════════════════════════════════════════════
# EVIDENCIAS (metadatos; el archivo va por grc_relaciones)
# ═════════════════════════════════════════════════════════════════════════════

TIPOS_REFERENCIA = {
    "riesgo": GRCRiesgo, "control": GRCControl, "prueba": GRCPruebaControl, "politica": GRCPolitica,
    "obligacion": GRCObligacion, "cumplimiento": GRCMatrizCumplimiento, "auditoria": GRCAuditoria,
    "hallazgo": GRCHallazgo, "plan": GRCPlanAccion, "incidente": GRCIncidente,
    "continuidad": GRCContinuidad, "simulacro": GRCSimulacro, "tercero": GRCTercero,
    "comite": GRCComite, "sesion": GRCComiteSesion, "tratamiento": GRCTratamiento,
    "evaluacion": GRCEvaluacionTercero, "kri": GRCKri,
}


async def _evidencia_antes(db, obj, datos, extras, antes, yo):
    modelo = TIPOS_REFERENCIA.get(datos["referencia_tipo"])
    if modelo is None:
        raise HTTPException(422, "Tipo de registro no admitido para evidencias.")
    await _vivo(db, modelo, datos["referencia_id"], "El registro")
    if antes is None and not datos.get("responsable_id"):
        obj.responsable_id = yo.id


montar(Recurso("evidencias", "evidencia", "Evidencia", GRCEvidencia, esq.EvidenciaIn,
               personas=("responsable_id",),
               catalogos={"tipo": ("GRC", "TIPO_EVIDENCIA", "tipo de evidencia")},
               filtros=("referencia_tipo", "referencia_id"), orden=GRCEvidencia.created_at.desc(),
               antes=_evidencia_antes))
