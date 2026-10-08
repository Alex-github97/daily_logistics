"""GRC — lo que une los registros entre sí.

Personas asignables, riesgo↔control, vínculos muchos-a-muchos, el flujo de
aprobación y aceptación de políticas, mediciones de KRI, evidencias con
archivo, historial y la ficha de cada registro con todo lo que tiene alrededor.
"""
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.grc import TIPOS_REFERENCIA, _next_code, _vivo, router as _grc  # noqa: F401
from app.application.schemas import grc as esq
from app.core import grc_servicio as srv
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.tenant import esquema_actual
from app.infrastructure.models.grc import (
    EstadoPoliticaGRCEnum, GRCAuditoria, GRCComite, GRCComiteSesion, GRCContinuidad, GRCControl,
    GRCEvaluacionTercero, GRCEvidencia, GRCHallazgo, GRCHistorial, GRCIncidente, GRCKri,
    GRCKriMedicion, GRCMatrizCumplimiento, GRCObligacion, GRCPlanAccion, GRCPolitica,
    GRCPoliticaAceptacion, GRCPruebaControl, GRCRiesgo, GRCRiesgoControl, GRCSimulacro, GRCTercero,
    GRCTratamiento, GRCVinculo,
)
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/grc", tags=["GRC"])


# ── Personas ─────────────────────────────────────────────────────────────────

@router.get("/personas")
async def personas(db: AsyncSession = Depends(get_db)):
    """Usuarios activos con acceso al módulo GRC: los únicos que se pueden
    asignar como responsables, aprobadores, auditores o miembros."""
    return await srv.personas_grc(db)


# ── Riesgo ↔ control ─────────────────────────────────────────────────────────

async def _controles_de(db, riesgo_id: int) -> List[dict]:
    usuarios = await srv.mapa_usuarios(db)
    filas = (await db.execute(select(GRCRiesgoControl, GRCControl)
                              .join(GRCControl, GRCControl.id == GRCRiesgoControl.control_id)
                              .where(GRCRiesgoControl.riesgo_id == riesgo_id,
                                     GRCControl.deleted_at.is_(None)))).all()
    return [{"vinculo_id": rc.id, "control_id": c.id, "codigo": c.codigo, "nombre": c.nombre,
             "tipo": srv.valor_json(c.tipo), "efectividad": srv.valor_json(c.efectividad),
             "responsable_nombre": usuarios.get(c.responsable_id), "observaciones": rc.observaciones}
            for rc, c in filas]


@router.get("/riesgos/{riesgo_id}/controles")
async def controles_del_riesgo(riesgo_id: int, db: AsyncSession = Depends(get_db)):
    await _vivo(db, GRCRiesgo, riesgo_id, "Riesgo")
    return await _controles_de(db, riesgo_id)


@router.post("/riesgos/{riesgo_id}/controles", status_code=201)
async def vincular_control(riesgo_id: int, data: esq.RiesgoControlIn, db: AsyncSession = Depends(get_db),
                           yo: Usuario = Depends(get_current_user)):
    riesgo = await _vivo(db, GRCRiesgo, riesgo_id, "Riesgo")
    control = await _vivo(db, GRCControl, data.control_id, "Control")
    existe = (await db.execute(select(GRCRiesgoControl).where(
        GRCRiesgoControl.riesgo_id == riesgo_id, GRCRiesgoControl.control_id == data.control_id))).scalar()
    if existe:
        raise HTTPException(409, "Ese control ya mitiga este riesgo.")
    db.add(GRCRiesgoControl(riesgo_id=riesgo_id, control_id=data.control_id, observaciones=data.observaciones))
    await db.flush()
    await srv.recalcular_riesgo(db, riesgo)
    await srv.registrar(db, "riesgo", riesgo_id, "vincular", yo.id, "control", None, control.codigo)
    await db.commit()
    return await _controles_de(db, riesgo_id)


@router.delete("/riesgos/{riesgo_id}/controles/{control_id}", status_code=204)
async def desvincular_control(riesgo_id: int, control_id: int, db: AsyncSession = Depends(get_db),
                              yo: Usuario = Depends(get_current_user)):
    riesgo = await _vivo(db, GRCRiesgo, riesgo_id, "Riesgo")
    await db.execute(text("DELETE FROM grc_riesgo_control WHERE riesgo_id = :r AND control_id = :c"),
                     {"r": riesgo_id, "c": control_id})
    await db.flush()
    await srv.recalcular_riesgo(db, riesgo)
    await srv.registrar(db, "riesgo", riesgo_id, "desvincular", yo.id, "control", control_id, None)
    await db.commit()


# ── Vínculos muchos-a-muchos ─────────────────────────────────────────────────

PARES = {
    frozenset(("obligacion", "control")), frozenset(("obligacion", "politica")),
    frozenset(("politica", "control")), frozenset(("obligacion", "riesgo")),
    frozenset(("continuidad", "riesgo")), frozenset(("continuidad", "tercero")),
    frozenset(("sesion", "riesgo")),
}


async def _etiqueta(db, tipo: str, id_: int) -> Optional[dict]:
    modelo = TIPOS_REFERENCIA.get(tipo)
    obj = await db.get(modelo, id_) if modelo else None
    if obj is None or getattr(obj, "deleted_at", None) is not None:
        return None
    nombre = (getattr(obj, "nombre", None) or getattr(obj, "titulo", None) or getattr(obj, "proceso", None)
              or getattr(obj, "accion", None) or str(getattr(obj, "fecha", "")))
    return {"tipo": tipo, "id": id_, "codigo": getattr(obj, "codigo", None), "nombre": nombre}


@router.get("/vinculos")
async def vinculos(tipo: str, id: int, db: AsyncSession = Depends(get_db)):
    filas = (await db.execute(select(GRCVinculo).where(or_(
        (GRCVinculo.origen_tipo == tipo) & (GRCVinculo.origen_id == id),
        (GRCVinculo.destino_tipo == tipo) & (GRCVinculo.destino_id == id))))).scalars().all()
    salida = []
    for v in filas:
        otro_t, otro_id = (v.destino_tipo, v.destino_id) if (v.origen_tipo == tipo and v.origen_id == id) \
            else (v.origen_tipo, v.origen_id)
        etq = await _etiqueta(db, otro_t, otro_id)
        if etq:
            salida.append({"vinculo_id": v.id, "nota": v.nota, **etq})
    return salida


@router.post("/vinculos", status_code=201)
async def vincular(data: esq.VinculoIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    if frozenset((data.origen_tipo, data.destino_tipo)) not in PARES:
        raise HTTPException(422, f"No se vinculan registros de tipo {data.origen_tipo} con {data.destino_tipo}.")
    for t, i in ((data.origen_tipo, data.origen_id), (data.destino_tipo, data.destino_id)):
        if await _etiqueta(db, t, i) is None:
            raise HTTPException(422, f"El registro {t} {i} no existe.")
    ya = (await db.execute(select(GRCVinculo).where(or_(
        (GRCVinculo.origen_tipo == data.origen_tipo) & (GRCVinculo.origen_id == data.origen_id)
        & (GRCVinculo.destino_tipo == data.destino_tipo) & (GRCVinculo.destino_id == data.destino_id),
        (GRCVinculo.origen_tipo == data.destino_tipo) & (GRCVinculo.origen_id == data.destino_id)
        & (GRCVinculo.destino_tipo == data.origen_tipo) & (GRCVinculo.destino_id == data.origen_id))))).scalar()
    if ya:
        raise HTTPException(409, "Esos dos registros ya están vinculados.")
    v = GRCVinculo(**data.model_dump())
    db.add(v)
    await db.flush()
    await srv.registrar(db, data.origen_tipo, data.origen_id, "vincular", yo.id, data.destino_tipo, None, data.destino_id)
    await db.commit()
    return {"id": v.id}


@router.delete("/vinculos/{vid}", status_code=204)
async def desvincular(vid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    v = await db.get(GRCVinculo, vid)
    if v is None:
        raise HTTPException(404, "Vínculo no encontrado")
    await srv.registrar(db, v.origen_tipo, v.origen_id, "desvincular", yo.id, v.destino_tipo, v.destino_id, None)
    await db.delete(v)
    await db.commit()


# ── KRI: mediciones ──────────────────────────────────────────────────────────

@router.get("/kris/{kri_id}/mediciones")
async def mediciones(kri_id: int, db: AsyncSession = Depends(get_db)):
    kri = await _vivo(db, GRCKri, kri_id, "Indicador")
    filas = (await db.execute(select(GRCKriMedicion).where(GRCKriMedicion.kri_id == kri_id)
                              .order_by(GRCKriMedicion.periodo))).scalars().all()
    return [{"id": m.id, "periodo": m.periodo, "valor": float(m.valor), "nota": m.nota,
             "estado": srv.estado_kri(m.valor, kri.direccion, kri.umbral_alerta, kri.umbral_critico)}
            for m in filas]


@router.post("/kris/{kri_id}/mediciones", status_code=201)
async def medir(kri_id: int, data: esq.MedicionKriIn, db: AsyncSession = Depends(get_db),
                yo: Usuario = Depends(get_current_user)):
    """Registra o corrige el valor de un período (uno por mes)."""
    await _vivo(db, GRCKri, kri_id, "Indicador")
    m = (await db.execute(select(GRCKriMedicion).where(GRCKriMedicion.kri_id == kri_id,
                                                       GRCKriMedicion.periodo == data.periodo))).scalar()
    if m is None:
        m = GRCKriMedicion(kri_id=kri_id, periodo=data.periodo)
        db.add(m)
    m.valor, m.nota, m.registrado_por_id = data.valor, data.nota, yo.id
    await srv.registrar(db, "kri", kri_id, "medir", yo.id, data.periodo, None, data.valor)
    await db.commit()
    return await mediciones(kri_id, db)


@router.delete("/kris/mediciones/{mid}", status_code=204)
async def borrar_medicion(mid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    m = await db.get(GRCKriMedicion, mid)
    if m is None:
        raise HTTPException(404, "Medición no encontrada")
    await srv.registrar(db, "kri", m.kri_id, "borrar_medicion", yo.id, m.periodo, m.valor, None)
    await db.delete(m)
    await db.commit()


# ── Políticas: flujo de aprobación y aceptaciones ────────────────────────────

TRANSICIONES = {
    "borrador": {"en_revision"},
    "en_revision": {"aprobada", "borrador"},
    "aprobada": {"publicada", "en_revision", "archivada"},
    "publicada": {"archivada", "en_revision"},
    "vencida": {"en_revision", "archivada"},
    "archivada": {"borrador"},
}


def _es_admin(u: Usuario) -> bool:
    return str(getattr(u.rol, "value", u.rol) or "").upper() == "ADMINISTRADOR"


@router.post("/politicas/{pid}/estado")
async def cambiar_estado_politica(pid: int, data: esq.CambioEstadoIn, db: AsyncSession = Depends(get_db),
                                  yo: Usuario = Depends(get_current_user)):
    pol = await _vivo(db, GRCPolitica, pid, "Política")
    actual = srv.valor_json(pol.estado)
    destino = data.estado
    if destino not in TRANSICIONES.get(actual, set()):
        raise HTTPException(409, f"Una política {actual.replace('_', ' ')} no pasa a {destino.replace('_', ' ')}.")
    if destino == "aprobada":
        if not pol.aprobador_id:
            raise HTTPException(409, "Asigne primero quién aprueba la política.")
        if pol.aprobador_id != yo.id and not _es_admin(yo):
            raise HTTPException(403, "Solo el aprobador asignado (o un administrador) puede aprobarla.")
        pol.fecha_aprobacion = date.today()
    if destino == "borrador" and actual == "en_revision" and not (data.comentario or "").strip():
        raise HTTPException(422, "Al devolver una política a borrador diga qué hay que corregir.")
    if destino == "publicada" and not pol.fecha_vigencia:
        pol.fecha_vigencia = date.today()
    pol.estado = EstadoPoliticaGRCEnum(destino)
    await srv.registrar(db, "politica", pid, "estado", yo.id, "estado", actual,
                        destino + (f" — {data.comentario}" if data.comentario else ""))
    await db.commit()
    return {"estado": destino}


@router.post("/politicas/{pid}/aceptar")
async def aceptar_politica(pid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    pol = await _vivo(db, GRCPolitica, pid, "Política")
    if srv.valor_json(pol.estado) != "publicada":
        raise HTTPException(409, "Solo se aceptan políticas publicadas.")
    ya = (await db.execute(select(GRCPoliticaAceptacion).where(
        GRCPoliticaAceptacion.politica_id == pid, GRCPoliticaAceptacion.usuario_id == yo.id,
        GRCPoliticaAceptacion.version == pol.version))).scalar()
    if ya is None:
        db.add(GRCPoliticaAceptacion(politica_id=pid, usuario_id=yo.id, version=pol.version,
                                     fecha=datetime.now(timezone.utc)))
        await srv.registrar(db, "politica", pid, "aceptar", yo.id, "version", None, pol.version)
        await db.commit()
    return {"aceptada": True, "version": pol.version}


@router.get("/politicas/{pid}/aceptaciones")
async def aceptaciones(pid: int, db: AsyncSession = Depends(get_db)):
    """Quién aceptó la versión vigente y quién falta."""
    pol = await _vivo(db, GRCPolitica, pid, "Política")
    hechas = {a.usuario_id: a.fecha for a in (await db.execute(select(GRCPoliticaAceptacion).where(
        GRCPoliticaAceptacion.politica_id == pid, GRCPoliticaAceptacion.version == pol.version))).scalars()}
    return [{"usuario_id": p["id"], "nombre": p["nombre"], "cargo": p["cargo"],
             "fecha": srv.valor_json(hechas.get(p["id"]))} for p in await srv.personas_grc(db)]


@router.get("/mis-politicas-pendientes")
async def mis_pendientes(db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    pols = (await db.execute(select(GRCPolitica).where(
        GRCPolitica.deleted_at.is_(None), GRCPolitica.aceptaciones_requeridas.is_(True),
        GRCPolitica.estado == EstadoPoliticaGRCEnum.PUBLICADA))).scalars().all()
    hechas = {(a.politica_id, a.version) for a in (await db.execute(select(GRCPoliticaAceptacion).where(
        GRCPoliticaAceptacion.usuario_id == yo.id))).scalars()}
    return [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "version": p.version}
            for p in pols if (p.id, p.version) not in hechas]


# ── Incidente → hallazgo ─────────────────────────────────────────────────────

@router.post("/incidentes/{iid}/hallazgo", status_code=201)
async def hallazgo_desde_incidente(iid: int, db: AsyncSession = Depends(get_db),
                                   yo: Usuario = Depends(get_current_user)):
    """Abre un hallazgo con lo que ya se sabe del incidente: el riesgo que se
    materializó, el control que falló y la causa. De ahí salen los planes."""
    inc = await _vivo(db, GRCIncidente, iid, "Incidente")
    plazo = await srv.parametro(db, "dias_plazo_hallazgo", 60)
    from datetime import timedelta
    h = GRCHallazgo(codigo=await _next_code(db, "HAL", GRCHallazgo), incidente_id=inc.id,
                    riesgo_id=inc.riesgo_id, control_id=inc.control_id,
                    titulo=f"Incidente {inc.codigo}: {inc.titulo}"[:300], descripcion=inc.descripcion,
                    severidad=inc.severidad, proceso=inc.proceso, area=inc.area,
                    responsable_id=inc.responsable_id, causa_raiz=inc.causa_raiz, impacto=inc.impacto,
                    fecha_limite=date.today() + timedelta(days=plazo))
    db.add(h)
    await db.flush()
    await srv.registrar(db, "hallazgo", h.id, "crear", yo.id, "incidente", None, inc.codigo)
    await db.commit()
    return {"id": h.id, "codigo": h.codigo}


# ── Evidencias con archivo ───────────────────────────────────────────────────

MAX_BYTES = 25 * 1024 * 1024


def _carpeta() -> Path:
    return Path(settings.UPLOAD_DIR).resolve() / "grc" / (esquema_actual() or "public")


@router.post("/evidencias/archivo", status_code=201)
async def subir_evidencia(referencia_tipo: str = Form(...), referencia_id: int = Form(...),
                          nombre: Optional[str] = Form(None), tipo: Optional[str] = Form(None),
                          descripcion: Optional[str] = Form(None),
                          fecha_vencimiento: Optional[date] = Form(None),
                          archivo: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                          yo: Usuario = Depends(get_current_user)):
    modelo = TIPOS_REFERENCIA.get(referencia_tipo)
    if modelo is None:
        raise HTTPException(422, "Tipo de registro no admitido para evidencias.")
    await _vivo(db, modelo, referencia_id, "El registro")
    datos = {"tipo": tipo}
    await srv.validar_catalogos(db, datos, {"tipo": ("GRC", "TIPO_EVIDENCIA", "tipo de evidencia")})
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(422, "El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo supera 25 MB.")
    carpeta = _carpeta()
    carpeta.mkdir(parents=True, exist_ok=True)
    seguro = "".join(c for c in (archivo.filename or "archivo") if c.isalnum() or c in "._- ")[:120] or "archivo"
    destino = carpeta / f"{uuid.uuid4().hex[:12]}_{seguro}"
    destino.write_bytes(contenido)
    ev = GRCEvidencia(nombre=(nombre or archivo.filename or "Evidencia")[:300], tipo=datos["tipo"],
                      descripcion=descripcion, fecha_vencimiento=fecha_vencimiento,
                      ruta_archivo=str(destino.relative_to(Path(settings.UPLOAD_DIR).resolve())),
                      tamano_bytes=len(contenido), responsable_id=yo.id,
                      referencia_tipo=referencia_tipo, referencia_id=referencia_id,
                      fecha_emision=date.today())
    db.add(ev)
    await db.flush()
    await srv.registrar(db, referencia_tipo, referencia_id, "evidencia", yo.id, "archivo", None, ev.nombre)
    await db.commit()
    return {"id": ev.id, "nombre": ev.nombre}


@router.get("/evidencias/{eid}/descargar")
async def descargar_evidencia(eid: int, db: AsyncSession = Depends(get_db)):
    ev = await _vivo(db, GRCEvidencia, eid, "Evidencia")
    if not ev.ruta_archivo:
        raise HTTPException(404, "La evidencia no tiene archivo (es un enlace o un registro).")
    base = Path(settings.UPLOAD_DIR).resolve()
    ruta = (base / ev.ruta_archivo).resolve()
    if base not in ruta.parents or not ruta.exists():
        raise HTTPException(404, "El archivo no está disponible.")
    return FileResponse(ruta, filename=ruta.name.split("_", 1)[-1])


# ── Historial ────────────────────────────────────────────────────────────────

ETIQUETAS_CAMPO = {"responsable_id": "responsable", "propietario_id": "propietario", "aprobador_id": "aprobador",
                   "presidente_id": "presidente", "secretario_id": "secretario", "auditor_lider_id": "auditor líder",
                   "probabilidad_inherente": "probabilidad", "impacto_inherente": "impacto",
                   "nivel_residual": "nivel residual", "nivel_inherente": "nivel inherente"}


@router.get("/historial")
async def historial(entidad: str, id: int, db: AsyncSession = Depends(get_db)):
    usuarios = await srv.mapa_usuarios(db)
    filas = (await db.execute(select(GRCHistorial).where(GRCHistorial.entidad == entidad,
                                                         GRCHistorial.entidad_id == id)
                              .order_by(GRCHistorial.fecha.desc(), GRCHistorial.id.desc()).limit(300))).scalars()
    salida = []
    for h in filas:
        ant, nue = h.anterior, h.nuevo
        if h.campo and h.campo.endswith("_id") and h.campo in ETIQUETAS_CAMPO:
            ant = usuarios.get(int(ant)) if ant and ant.isdigit() else ant
            nue = usuarios.get(int(nue)) if nue and nue.isdigit() else nue
        salida.append({"fecha": srv.valor_json(h.fecha), "accion": h.accion,
                       "campo": ETIQUETAS_CAMPO.get(h.campo, (h.campo or "").replace("_", " ")) or None,
                       "anterior": ant, "nuevo": nue, "usuario": usuarios.get(h.usuario_id)})
    return salida


# ── Ficha: el registro y todo lo que tiene alrededor ─────────────────────────

def _mini(o, usuarios, extra=()) -> dict:
    d = {"id": o.id, "codigo": getattr(o, "codigo", None),
         "nombre": getattr(o, "nombre", None) or getattr(o, "titulo", None) or getattr(o, "accion", None)
         or getattr(o, "proceso", None) or getattr(o, "periodo", None)}
    for c in ("estado", "efectividad", "prioridad", "severidad", "nivel_residual", "fecha", "fecha_limite",
              "fecha_objetivo", "avance", "resultado", "puntaje_total", "fecha_ocurrencia", *extra):
        if hasattr(o, c):
            d[c] = srv.valor_json(getattr(o, c))
    if getattr(o, "responsable_id", None):
        d["responsable_nombre"] = usuarios.get(o.responsable_id)
    return d


async def _lista(db, modelo, *cond, orden=None):
    q = select(modelo).where(modelo.deleted_at.is_(None), *cond)
    if orden is not None:
        q = q.order_by(orden)
    return list((await db.execute(q)).scalars())


@router.get("/ficha/{tipo}/{id}")
async def ficha(tipo: str, id: int, db: AsyncSession = Depends(get_db)):
    modelo = TIPOS_REFERENCIA.get(tipo)
    if modelo is None:
        raise HTTPException(404, "Tipo de registro desconocido")
    obj = await _vivo(db, modelo, id, "Registro")
    usuarios = await srv.mapa_usuarios(db)
    rel: Dict[str, list] = {}
    m = lambda xs: [_mini(x, usuarios) for x in xs]   # noqa: E731

    if tipo == "riesgo":
        rel["controles"] = await _controles_de(db, id)
        rel["tratamientos"] = m(await _lista(db, GRCTratamiento, GRCTratamiento.riesgo_id == id))
        rel["kris"] = m(await _lista(db, GRCKri, GRCKri.riesgo_id == id))
        rel["incidentes"] = m(await _lista(db, GRCIncidente, GRCIncidente.riesgo_id == id,
                                           orden=GRCIncidente.fecha_ocurrencia.desc().nullslast()))
        rel["hallazgos"] = m(await _lista(db, GRCHallazgo, GRCHallazgo.riesgo_id == id))
    elif tipo == "control":
        rel["pruebas"] = m(await _lista(db, GRCPruebaControl, GRCPruebaControl.control_id == id,
                                        orden=GRCPruebaControl.fecha.desc()))
        ids = (await db.execute(select(GRCRiesgoControl.riesgo_id).where(GRCRiesgoControl.control_id == id))).scalars().all()
        rel["riesgos"] = m(await _lista(db, GRCRiesgo, GRCRiesgo.id.in_(ids))) if ids else []
        rel["incidentes"] = m(await _lista(db, GRCIncidente, GRCIncidente.control_id == id))
        rel["hallazgos"] = m(await _lista(db, GRCHallazgo, GRCHallazgo.control_id == id))
    elif tipo == "obligacion":
        rel["evaluaciones"] = m(await _lista(db, GRCMatrizCumplimiento, GRCMatrizCumplimiento.obligacion_id == id,
                                             orden=GRCMatrizCumplimiento.ultima_evaluacion.desc().nullslast()))
    elif tipo == "auditoria":
        rel["hallazgos"] = m(await _lista(db, GRCHallazgo, GRCHallazgo.auditoria_id == id))
    elif tipo == "hallazgo":
        rel["planes"] = m(await _lista(db, GRCPlanAccion, GRCPlanAccion.hallazgo_id == id,
                                       orden=GRCPlanAccion.fecha_objetivo.asc().nullslast()))
    elif tipo == "incidente":
        rel["hallazgos"] = m(await _lista(db, GRCHallazgo, GRCHallazgo.incidente_id == id))
    elif tipo == "comite":
        rel["sesiones"] = m(await _lista(db, GRCComiteSesion, GRCComiteSesion.comite_id == id,
                                         orden=GRCComiteSesion.fecha.desc()))
        rel["riesgos"] = m(await _lista(db, GRCRiesgo, GRCRiesgo.comite_id == id))
    elif tipo == "continuidad":
        rel["simulacros"] = m(await _lista(db, GRCSimulacro, GRCSimulacro.continuidad_id == id,
                                           orden=GRCSimulacro.fecha.desc().nullslast()))
    elif tipo == "tercero":
        rel["evaluaciones"] = m(await _lista(db, GRCEvaluacionTercero, GRCEvaluacionTercero.tercero_id == id,
                                             orden=GRCEvaluacionTercero.fecha.desc().nullslast()))
        rel["riesgos"] = m(await _lista(db, GRCRiesgo, GRCRiesgo.tercero_id == id))
    rel["vinculos"] = await vinculos(tipo, id, db)
    evid = await _lista(db, GRCEvidencia, GRCEvidencia.referencia_tipo == tipo, GRCEvidencia.referencia_id == id,
                        orden=GRCEvidencia.created_at.desc())
    rel["evidencias"] = [{"id": e.id, "nombre": e.nombre, "tipo": e.tipo, "url": e.url,
                          "archivo": bool(e.ruta_archivo), "tamano_bytes": e.tamano_bytes,
                          "fecha_vencimiento": srv.valor_json(e.fecha_vencimiento),
                          "responsable_nombre": usuarios.get(e.responsable_id)} for e in evid]
    return {"tipo": tipo, "registro": srv.como_dict(obj, usuarios), "relacionados": rel,
            "historial": await historial(tipo, id, db)}


# ── Terceros: de dónde pueden venir ──────────────────────────────────────────

@router.get("/terceros-fuentes")
async def fuentes_de_terceros(db: AsyncSession = Depends(get_db)):
    """Proveedores (SCM) y clientes (CRM) que ya existen, para crear el
    tercero desde ellos en vez de volver a escribirlo."""
    prov = (await db.execute(text(
        "SELECT id, razon_social AS nombre, nit FROM proveedores WHERE activo ORDER BY razon_social"))).mappings().all()
    try:
        cli = (await db.execute(text(
            "SELECT id, razon_social AS nombre, nit FROM crm_cliente "
            "WHERE coalesce(activo, true) ORDER BY razon_social"))).mappings().all()
    except Exception:   # noqa: BLE001 — esquema sin CRM
        await db.rollback()
        cli = []
    return {"proveedores": [dict(p) for p in prov], "clientes": [dict(c) for c in cli]}
