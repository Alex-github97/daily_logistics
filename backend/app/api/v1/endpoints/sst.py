"""
Seguridad y salud en el trabajo (SG-SST).

Las diez pantallas del módulo eran maqueta; el servidor solo sabía listar y
crear. Aquí queda completo: editar y retirar cada registro, emergencias
(brigada y simulacros), los períodos con trabajadores y horas-hombre, y los
indicadores calculados con ellos.

DOS DECISIONES QUE NO SON OBVIAS

· El nivel de riesgo se CALCULA con la GTC 45 (deficiencia × exposición ×
  consecuencia) y no se elige de una lista. La maqueta dejaba escoger «alto» o
  «medio» a mano junto a una probabilidad y un impacto que no lo determinaban.

· Los indicadores (frecuencia, severidad, lesión incapacitante) necesitan la
  exposición: cuántas horas-hombre se trabajaron. Sin períodos registrados
  no se inventa un índice: se devuelve vacío y la pantalla lo dice.
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.sst import (
    SstIncidente, SstRiesgo, SstInspeccion, SstEntregaEPP, SstCapacitacion, SstDocumento,
    SstBrigadista, SstSimulacro, SstPeriodo, SstConfig,
    TipoIncidenteSST, GravedadSST, EstadoIncidenteSST, ClasePeligroSST, NivelRiesgoSST,
    EstadoInspeccionSST, TipoEPP, EstadoCapacitacionSST, TipoDocumentoSST,
)

router = APIRouter(prefix="/sst", tags=["SST"])


# ─── Ayudas ───────────────────────────────────────────────────────────────────

def _v(x):
    return x.value if hasattr(x, "value") else x


def _f(d):
    return d.isoformat() if d else None


async def _gen_numero(db: AsyncSession, model, prefix: str) -> str:
    # Se cuentan también los retirados (borrado suave): así el consecutivo no
    # repite un número que ya existió.
    year = date.today().year
    res = await db.execute(select(func.count(model.id)))
    seq = (res.scalar_one() or 0) + 1
    return f"{prefix}-{year}-{seq:05d}"


async def _obtener(db: AsyncSession, model, id: int, nombre: str):
    obj = await db.get(model, id)
    if not obj or getattr(obj, "deleted_at", None) is not None:
        raise HTTPException(404, f"{nombre} no encontrado")
    return obj


async def _retirar(db: AsyncSession, model, id: int, nombre: str):
    obj = await _obtener(db, model, id, nombre)
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()


def _vivos(model):
    return select(model).where(model.deleted_at.is_(None))


# ─── Diccionarios de salida ───────────────────────────────────────────────────

def _inc_dict(r: SstIncidente) -> dict:
    return {
        "id": r.id, "numero": r.numero, "tipo": _v(r.tipo), "gravedad": _v(r.gravedad),
        "estado": _v(r.estado), "fecha_evento": _f(r.fecha_evento), "hora_evento": r.hora_evento,
        "lugar": r.lugar, "trabajador": r.trabajador, "cargo": r.cargo, "area": r.area,
        "descripcion": r.descripcion, "causa_inmediata": r.causa_inmediata,
        "causa_basica": r.causa_basica, "dias_incapacidad": r.dias_incapacidad or 0,
        "acciones_correctivas": r.acciones_correctivas, "investigador": r.investigador,
        "fecha_cierre": _f(r.fecha_cierre),
    }


# ── GTC 45 ──
# Los valores permitidos de cada factor son los de la guía; cualquier otro
# número no significa nada en la tabla.
ND_VALIDOS = (0, 2, 6, 10)          # deficiencia: no significativo, bajo, medio, alto, muy alto(10)
NE_VALIDOS = (1, 2, 3, 4)           # exposición: esporádica … continua
NC_VALIDOS = (10, 25, 60, 100)      # consecuencia: leve, grave, muy grave, mortal


def _gtc45(nd: Optional[int], ne: Optional[int], nc: Optional[int]) -> dict:
    """Nivel de probabilidad, de riesgo e interpretación según la GTC 45."""
    if nd is None or ne is None or nc is None:
        return {"nivel_probabilidad": None, "nivel_riesgo_valor": None,
                "interpretacion": None, "aceptabilidad": None}
    np_ = nd * ne
    nr = np_ * nc
    if nr >= 600:
        interp, acept = "I", "No aceptable"
    elif nr >= 150:
        interp, acept = "II", "No aceptable o aceptable con control específico"
    elif nr >= 40:
        interp, acept = "III", "Mejorable"
    else:
        interp, acept = "IV", "Aceptable"
    return {"nivel_probabilidad": np_, "nivel_riesgo_valor": nr,
            "interpretacion": interp, "aceptabilidad": acept}


# Cómo se ve cada interpretación en la escala que ya usaban el tablero y los
# filtros. «BAJO» no tiene par en la GTC 45 y queda sin uso.
_NIVEL_POR_INTERP = {"I": NivelRiesgoSST.INACEPTABLE, "II": NivelRiesgoSST.ALTO,
                     "III": NivelRiesgoSST.MEDIO, "IV": NivelRiesgoSST.ACEPTABLE}


def _riesgo_dict(r: SstRiesgo) -> dict:
    return {
        "id": r.id, "codigo": r.codigo, "proceso": r.proceso, "area": r.area,
        "actividad": r.actividad, "clase_peligro": _v(r.clase_peligro),
        "descripcion_peligro": r.descripcion_peligro, "efecto_posible": r.efecto_posible,
        "nivel_deficiencia": r.nivel_deficiencia, "nivel_exposicion": r.nivel_exposicion,
        "nivel_consecuencia": r.nivel_consecuencia,
        **_gtc45(r.nivel_deficiencia, r.nivel_exposicion, r.nivel_consecuencia),
        "nivel_riesgo": _v(r.nivel_riesgo),
        "expuestos": r.expuestos,
        "controles_existentes": r.controles_existentes,
        "controles_propuestos": r.controles_propuestos,
        "responsable": r.responsable, "fecha_revision": _f(r.fecha_revision),
    }


def _insp_dict(r: SstInspeccion) -> dict:
    return {
        "id": r.id, "numero": r.numero, "tipo": r.tipo, "area": r.area, "estado": _v(r.estado),
        "fecha_programada": _f(r.fecha_programada), "fecha_realizacion": _f(r.fecha_realizacion),
        "inspector": r.inspector, "descripcion": r.descripcion,
        "hallazgos_count": r.hallazgos_count or 0, "puntuacion": r.puntuacion,
        "observaciones": r.observaciones,
    }


def _epp_dict(r: SstEntregaEPP) -> dict:
    hoy = date.today()
    return {
        "id": r.id, "numero": r.numero, "trabajador": r.trabajador, "cargo": r.cargo, "area": r.area,
        "tipo_epp": _v(r.tipo_epp), "descripcion_epp": r.descripcion_epp, "cantidad": r.cantidad,
        "fecha_entrega": _f(r.fecha_entrega), "fecha_vencimiento": _f(r.fecha_vencimiento),
        "firma_recibido": bool(r.firma_recibido), "devuelto": bool(r.devuelto),
        "fecha_devolucion": _f(r.fecha_devolucion), "motivo_devolucion": r.motivo_devolucion,
        # Se calcula: guardado, un «vigente» miente al día siguiente de vencer.
        "vencido": bool(r.fecha_vencimiento and r.fecha_vencimiento < hoy and not r.devuelto),
    }


def _cap_dict(r: SstCapacitacion) -> dict:
    return {
        "id": r.id, "codigo": r.codigo, "titulo": r.titulo, "tipo": r.tipo, "modalidad": r.modalidad,
        "estado": _v(r.estado), "instructor": r.instructor,
        "fecha_inicio": _f(r.fecha_inicio), "fecha_fin": _f(r.fecha_fin),
        "duracion_horas": r.duracion_horas, "max_participantes": r.max_participantes,
        "participantes": r.participantes or 0, "area_dirigida": r.area_dirigida,
        "descripcion": r.descripcion, "evaluacion_prom": r.evaluacion_prom,
    }


def _doc_dict(r: SstDocumento) -> dict:
    hoy = date.today()
    return {
        "id": r.id, "codigo": r.codigo, "titulo": r.titulo, "tipo": _v(r.tipo),
        "version": r.version, "estado": r.estado,
        "area_responsable": r.area_responsable, "responsable": r.responsable,
        "fecha_aprobacion": _f(r.fecha_aprobacion), "fecha_revision": _f(r.fecha_revision),
        "descripcion": r.descripcion, "url_documento": r.url_documento,
        "revision_vencida": bool(r.fecha_revision and r.fecha_revision < hoy),
    }


def _brig_dict(r: SstBrigadista) -> dict:
    return {
        "id": r.id, "nombre": r.nombre, "cargo": r.cargo, "area": r.area, "rol": r.rol,
        "telefono": r.telefono, "certificado_hasta": _f(r.certificado_hasta),
        "certificado_vigente": bool(r.certificado_hasta and r.certificado_hasta >= date.today()),
    }


def _sim_dict(r: SstSimulacro) -> dict:
    return {
        "id": r.id, "fecha": _f(r.fecha), "tipo": r.tipo, "participantes": r.participantes,
        "tiempo_respuesta_seg": r.tiempo_respuesta_seg, "resultado": r.resultado,
        "observaciones": r.observaciones, "acciones_mejora": r.acciones_mejora,
    }


# ─── Tablero ──────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_sst_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    hoy = date.today()
    anio = hoy.year
    vivo = SstIncidente.deleted_at.is_(None)

    # Antes «incidentes del año» contaba todos los de la historia.
    incidentes_anio = (await db.execute(select(func.count(SstIncidente.id)).where(
        vivo, func.extract("year", SstIncidente.fecha_evento) == anio))).scalar_one()
    accidentes_at = (await db.execute(select(func.count(SstIncidente.id)).where(
        vivo, SstIncidente.tipo == TipoIncidenteSST.ACCIDENTE_TRABAJO,
        func.extract("year", SstIncidente.fecha_evento) == anio))).scalar_one()
    abiertos = (await db.execute(select(func.count(SstIncidente.id)).where(
        vivo, SstIncidente.estado != EstadoIncidenteSST.CERRADO))).scalar_one()
    inspecciones_pendientes = (await db.execute(select(func.count(SstInspeccion.id)).where(
        SstInspeccion.deleted_at.is_(None),
        SstInspeccion.estado == EstadoInspeccionSST.PROGRAMADA))).scalar_one()
    riesgos_criticos = (await db.execute(select(func.count(SstRiesgo.id)).where(
        SstRiesgo.deleted_at.is_(None),
        SstRiesgo.nivel_riesgo.in_([NivelRiesgoSST.ALTO, NivelRiesgoSST.INACEPTABLE])))).scalar_one()
    epp_vencidos = (await db.execute(select(func.count(SstEntregaEPP.id)).where(
        SstEntregaEPP.deleted_at.is_(None), SstEntregaEPP.devuelto.is_(False),
        SstEntregaEPP.fecha_vencimiento < hoy))).scalar_one()

    last_at = (await db.execute(
        select(SstIncidente.fecha_evento)
        .where(vivo, SstIncidente.tipo == TipoIncidenteSST.ACCIDENTE_TRABAJO)
        .order_by(SstIncidente.fecha_evento.desc()).limit(1))).scalar_one_or_none()

    proximas = (await db.execute(
        _vivos(SstInspeccion).where(SstInspeccion.estado == EstadoInspeccionSST.PROGRAMADA,
                                    SstInspeccion.fecha_programada >= hoy)
        .order_by(SstInspeccion.fecha_programada).limit(5))).scalars().all()

    return {
        # Sin accidentes registrados no hay un conteo que dar: nulo, no cero.
        # Cero decía «hubo un accidente hoy».
        "dias_sin_accidente": (hoy - last_at).days if last_at else None,
        "ultimo_accidente": _f(last_at),
        "incidentes_anio": incidentes_anio,
        "accidentes_trabajo": accidentes_at,
        "incidentes_abiertos": abiertos,
        "inspecciones_pendientes": inspecciones_pendientes,
        "riesgos_criticos": riesgos_criticos,
        "epp_vencidos": epp_vencidos,
        "proximas_inspecciones": [_insp_dict(i) for i in proximas],
    }


# ─── Incidentes ───────────────────────────────────────────────────────────────

class IncidenteIn(BaseModel):
    tipo: TipoIncidenteSST
    gravedad: Optional[GravedadSST] = None
    fecha_evento: date
    hora_evento: Optional[str] = None
    lugar: Optional[str] = None
    trabajador: Optional[str] = None
    cargo: Optional[str] = None
    area: Optional[str] = None
    descripcion: Optional[str] = None
    causa_inmediata: Optional[str] = None
    causa_basica: Optional[str] = None
    dias_incapacidad: int = 0
    acciones_correctivas: Optional[str] = None
    investigador: Optional[str] = None


def _validar_incidente(d: IncidenteIn):
    if d.fecha_evento > date.today():
        raise HTTPException(422, "La fecha del evento no puede ser futura")
    if d.dias_incapacidad < 0:
        raise HTTPException(422, "Los días de incapacidad no pueden ser negativos")


@router.get("/incidentes")
async def list_incidentes(
    skip: int = Query(0), limit: int = Query(200, le=1000),
    estado: Optional[EstadoIncidenteSST] = None,
    tipo: Optional[TipoIncidenteSST] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = _vivos(SstIncidente)
    if estado: q = q.where(SstIncidente.estado == estado)
    if tipo:   q = q.where(SstIncidente.tipo == tipo)
    q = q.order_by(SstIncidente.fecha_evento.desc(), SstIncidente.id.desc()).offset(skip).limit(limit)
    return [_inc_dict(r) for r in (await db.execute(q)).scalars().all()]


@router.post("/incidentes", status_code=201)
async def create_incidente(data: IncidenteIn, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    _validar_incidente(data)
    obj = SstIncidente(numero=await _gen_numero(db, SstIncidente, "SST-INC"), **data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _inc_dict(obj)


@router.put("/incidentes/{id}")
async def update_incidente(id: int, data: IncidenteIn, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    _validar_incidente(data)
    obj = await _obtener(db, SstIncidente, id, "Incidente")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return _inc_dict(obj)


@router.patch("/incidentes/{id}/estado")
async def cambiar_estado_incidente(
    id: int, estado: EstadoIncidenteSST,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    obj = await _obtener(db, SstIncidente, id, "Incidente")
    # Un accidente no se cierra sin investigar: es lo que la norma exige y lo
    # que evita que se repita.
    if estado == EstadoIncidenteSST.CERRADO and obj.tipo == TipoIncidenteSST.ACCIDENTE_TRABAJO \
            and not (obj.causa_inmediata or obj.causa_basica):
        raise HTTPException(400, "Registra las causas de la investigación antes de cerrar el accidente")
    obj.estado = estado
    obj.fecha_cierre = date.today() if estado == EstadoIncidenteSST.CERRADO else None
    await db.commit()
    return _inc_dict(obj)


@router.delete("/incidentes/{id}", status_code=204)
async def delete_incidente(id: int, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstIncidente, id, "Incidente")


# ─── Riesgos (matriz GTC 45) ──────────────────────────────────────────────────

class RiesgoIn(BaseModel):
    proceso: Optional[str] = None
    area: Optional[str] = None
    actividad: Optional[str] = None
    clase_peligro: Optional[ClasePeligroSST] = None
    descripcion_peligro: Optional[str] = None
    efecto_posible: Optional[str] = None
    nivel_deficiencia: int
    nivel_exposicion: int
    nivel_consecuencia: int
    expuestos: Optional[int] = None
    controles_existentes: Optional[str] = None
    controles_propuestos: Optional[str] = None
    responsable: Optional[str] = None
    fecha_revision: Optional[date] = None


def _aplicar_riesgo(obj: SstRiesgo, d: RiesgoIn):
    if d.nivel_deficiencia not in ND_VALIDOS:
        raise HTTPException(422, f"Nivel de deficiencia: uno de {ND_VALIDOS}")
    if d.nivel_exposicion not in NE_VALIDOS:
        raise HTTPException(422, f"Nivel de exposición: uno de {NE_VALIDOS}")
    if d.nivel_consecuencia not in NC_VALIDOS:
        raise HTTPException(422, f"Nivel de consecuencia: uno de {NC_VALIDOS}")
    for k, v in d.model_dump().items():
        setattr(obj, k, v)
    # El nivel se guarda además de calcularse porque el tablero y el filtro lo
    # consultan en SQL; se reescribe en cada guardado desde sus factores.
    obj.nivel_riesgo = _NIVEL_POR_INTERP[_gtc45(d.nivel_deficiencia, d.nivel_exposicion,
                                                 d.nivel_consecuencia)["interpretacion"]]


@router.get("/riesgos")
async def list_riesgos(
    nivel: Optional[NivelRiesgoSST] = None,
    clase: Optional[ClasePeligroSST] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = _vivos(SstRiesgo)
    if nivel: q = q.where(SstRiesgo.nivel_riesgo == nivel)
    if clase: q = q.where(SstRiesgo.clase_peligro == clase)
    filas = [_riesgo_dict(r) for r in (await db.execute(q.order_by(SstRiesgo.id.desc()))).scalars().all()]
    # Lo más peligroso primero.
    return sorted(filas, key=lambda r: -(r["nivel_riesgo_valor"] or -1))


@router.post("/riesgos", status_code=201)
async def create_riesgo(data: RiesgoIn, db: AsyncSession = Depends(get_db),
                        current_user: Usuario = Depends(get_current_user)):
    obj = SstRiesgo(codigo=await _gen_numero(db, SstRiesgo, "IPER"))
    _aplicar_riesgo(obj, data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _riesgo_dict(obj)


@router.put("/riesgos/{id}")
async def update_riesgo(id: int, data: RiesgoIn, db: AsyncSession = Depends(get_db),
                        current_user: Usuario = Depends(get_current_user)):
    obj = await _obtener(db, SstRiesgo, id, "Riesgo")
    _aplicar_riesgo(obj, data)
    await db.commit()
    return _riesgo_dict(obj)


@router.delete("/riesgos/{id}", status_code=204)
async def delete_riesgo(id: int, db: AsyncSession = Depends(get_db),
                        current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstRiesgo, id, "Riesgo")


# ─── Inspecciones ─────────────────────────────────────────────────────────────

class InspeccionIn(BaseModel):
    tipo: str = "PLANEADA"
    area: Optional[str] = None
    fecha_programada: Optional[date] = None
    inspector: Optional[str] = None
    descripcion: Optional[str] = None
    hallazgos_count: int = 0
    puntuacion: Optional[float] = None
    observaciones: Optional[str] = None


def _validar_insp(d: InspeccionIn):
    if d.hallazgos_count < 0:
        raise HTTPException(422, "Los hallazgos no pueden ser negativos")
    if d.puntuacion is not None and not 0 <= d.puntuacion <= 100:
        raise HTTPException(422, "La puntuación va de 0 a 100")


@router.get("/inspecciones")
async def list_inspecciones(
    estado: Optional[EstadoInspeccionSST] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = _vivos(SstInspeccion)
    if estado: q = q.where(SstInspeccion.estado == estado)
    q = q.order_by(SstInspeccion.fecha_programada.desc().nullslast(), SstInspeccion.id.desc())
    return [_insp_dict(r) for r in (await db.execute(q)).scalars().all()]


@router.post("/inspecciones", status_code=201)
async def create_inspeccion(data: InspeccionIn, db: AsyncSession = Depends(get_db),
                            current_user: Usuario = Depends(get_current_user)):
    _validar_insp(data)
    obj = SstInspeccion(numero=await _gen_numero(db, SstInspeccion, "SST-INSP"), **data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _insp_dict(obj)


@router.put("/inspecciones/{id}")
async def update_inspeccion(id: int, data: InspeccionIn, db: AsyncSession = Depends(get_db),
                            current_user: Usuario = Depends(get_current_user)):
    _validar_insp(data)
    obj = await _obtener(db, SstInspeccion, id, "Inspección")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return _insp_dict(obj)


@router.patch("/inspecciones/{id}/estado")
async def cambiar_estado_inspeccion(
    id: int, estado: EstadoInspeccionSST,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    obj = await _obtener(db, SstInspeccion, id, "Inspección")
    obj.estado = estado
    obj.fecha_realizacion = date.today() if estado == EstadoInspeccionSST.COMPLETADA else obj.fecha_realizacion
    await db.commit()
    return _insp_dict(obj)


@router.delete("/inspecciones/{id}", status_code=204)
async def delete_inspeccion(id: int, db: AsyncSession = Depends(get_db),
                            current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstInspeccion, id, "Inspección")


# ─── EPP ──────────────────────────────────────────────────────────────────────

class EPPIn(BaseModel):
    trabajador: str
    cargo: Optional[str] = None
    area: Optional[str] = None
    tipo_epp: TipoEPP
    descripcion_epp: Optional[str] = None
    cantidad: int = 1
    fecha_entrega: date
    fecha_vencimiento: Optional[date] = None
    firma_recibido: bool = False


class DevolucionEPP(BaseModel):
    motivo: Optional[str] = None


def _validar_epp(d: EPPIn):
    if not d.trabajador.strip():
        raise HTTPException(422, "Falta el trabajador")
    if d.cantidad < 1:
        raise HTTPException(422, "La cantidad debe ser al menos 1")
    if d.fecha_vencimiento and d.fecha_vencimiento < d.fecha_entrega:
        raise HTTPException(422, "El EPP no puede vencer antes de entregarse")


@router.get("/epp")
async def list_epp(
    trabajador: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = _vivos(SstEntregaEPP)
    if trabajador: q = q.where(SstEntregaEPP.trabajador.ilike(f"%{trabajador}%"))
    q = q.order_by(SstEntregaEPP.fecha_entrega.desc(), SstEntregaEPP.id.desc())
    return [_epp_dict(r) for r in (await db.execute(q)).scalars().all()]


@router.post("/epp", status_code=201)
async def create_epp(data: EPPIn, db: AsyncSession = Depends(get_db),
                     current_user: Usuario = Depends(get_current_user)):
    _validar_epp(data)
    obj = SstEntregaEPP(numero=await _gen_numero(db, SstEntregaEPP, "EPP"), **data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _epp_dict(obj)


@router.put("/epp/{id}")
async def update_epp(id: int, data: EPPIn, db: AsyncSession = Depends(get_db),
                     current_user: Usuario = Depends(get_current_user)):
    _validar_epp(data)
    obj = await _obtener(db, SstEntregaEPP, id, "Entrega de EPP")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return _epp_dict(obj)


@router.post("/epp/{id}/devolver")
async def devolver_epp(id: int, data: DevolucionEPP, db: AsyncSession = Depends(get_db),
                       current_user: Usuario = Depends(get_current_user)):
    obj = await _obtener(db, SstEntregaEPP, id, "Entrega de EPP")
    if obj.devuelto:
        raise HTTPException(400, "Este EPP ya fue devuelto")
    obj.devuelto = True
    obj.fecha_devolucion = date.today()
    obj.motivo_devolucion = (data.motivo or "").strip() or None
    await db.commit()
    return _epp_dict(obj)


@router.delete("/epp/{id}", status_code=204)
async def delete_epp(id: int, db: AsyncSession = Depends(get_db),
                     current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstEntregaEPP, id, "Entrega de EPP")


# ─── Capacitaciones ───────────────────────────────────────────────────────────

class CapacitacionIn(BaseModel):
    titulo: str
    tipo: Optional[str] = None
    modalidad: Optional[str] = None
    estado: EstadoCapacitacionSST = EstadoCapacitacionSST.PROGRAMADA
    instructor: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    duracion_horas: Optional[float] = None
    max_participantes: Optional[int] = None
    participantes: int = 0
    area_dirigida: Optional[str] = None
    descripcion: Optional[str] = None
    evaluacion_prom: Optional[float] = None


def _validar_cap(d: CapacitacionIn):
    if not d.titulo.strip():
        raise HTTPException(422, "Falta el título")
    if d.fecha_inicio and d.fecha_fin and d.fecha_fin < d.fecha_inicio:
        raise HTTPException(422, "La capacitación no puede terminar antes de empezar")
    if d.max_participantes is not None and d.participantes > d.max_participantes:
        raise HTTPException(422, "Hay más participantes que el cupo")
    if d.evaluacion_prom is not None and not 0 <= d.evaluacion_prom <= 5:
        raise HTTPException(422, "La evaluación va de 0 a 5")


@router.get("/capacitaciones")
async def list_capacitaciones(
    estado: Optional[EstadoCapacitacionSST] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = _vivos(SstCapacitacion)
    if estado: q = q.where(SstCapacitacion.estado == estado)
    q = q.order_by(SstCapacitacion.fecha_inicio.desc().nullslast(), SstCapacitacion.id.desc())
    return [_cap_dict(r) for r in (await db.execute(q)).scalars().all()]


@router.post("/capacitaciones", status_code=201)
async def create_capacitacion(data: CapacitacionIn, db: AsyncSession = Depends(get_db),
                              current_user: Usuario = Depends(get_current_user)):
    _validar_cap(data)
    obj = SstCapacitacion(codigo=await _gen_numero(db, SstCapacitacion, "CAP-SST"), **data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _cap_dict(obj)


@router.put("/capacitaciones/{id}")
async def update_capacitacion(id: int, data: CapacitacionIn, db: AsyncSession = Depends(get_db),
                              current_user: Usuario = Depends(get_current_user)):
    _validar_cap(data)
    obj = await _obtener(db, SstCapacitacion, id, "Capacitación")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return _cap_dict(obj)


@router.delete("/capacitaciones/{id}", status_code=204)
async def delete_capacitacion(id: int, db: AsyncSession = Depends(get_db),
                              current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstCapacitacion, id, "Capacitación")


# ─── Documentos ───────────────────────────────────────────────────────────────

class DocumentoIn(BaseModel):
    titulo: str
    tipo: TipoDocumentoSST
    version: str = "1.0"
    estado: str = "VIGENTE"
    area_responsable: Optional[str] = None
    responsable: Optional[str] = None
    fecha_aprobacion: Optional[date] = None
    fecha_revision: Optional[date] = None
    descripcion: Optional[str] = None
    url_documento: Optional[str] = None


ESTADOS_DOC = ("VIGENTE", "EN_REVISION", "OBSOLETO")


def _validar_doc(d: DocumentoIn):
    if not d.titulo.strip():
        raise HTTPException(422, "Falta el título")
    if d.estado not in ESTADOS_DOC:
        raise HTTPException(422, f"Estado: uno de {ESTADOS_DOC}")


@router.get("/documentos")
async def list_documentos(
    tipo: Optional[TipoDocumentoSST] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = _vivos(SstDocumento)
    if tipo: q = q.where(SstDocumento.tipo == tipo)
    return [_doc_dict(r) for r in (await db.execute(q.order_by(SstDocumento.id.desc()))).scalars().all()]


@router.post("/documentos", status_code=201)
async def create_documento(data: DocumentoIn, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    _validar_doc(data)
    obj = SstDocumento(codigo=await _gen_numero(db, SstDocumento, "DOC-SST"), **data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _doc_dict(obj)


@router.put("/documentos/{id}")
async def update_documento(id: int, data: DocumentoIn, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    _validar_doc(data)
    obj = await _obtener(db, SstDocumento, id, "Documento")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return _doc_dict(obj)


@router.delete("/documentos/{id}", status_code=204)
async def delete_documento(id: int, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstDocumento, id, "Documento")


# ─── Emergencias: brigada y simulacros ───────────────────────────────────────

class BrigadistaIn(BaseModel):
    nombre: str
    cargo: Optional[str] = None
    area: Optional[str] = None
    rol: str
    telefono: Optional[str] = None
    certificado_hasta: Optional[date] = None


class SimulacroIn(BaseModel):
    fecha: date
    tipo: str
    participantes: Optional[int] = None
    tiempo_respuesta_seg: Optional[int] = None
    resultado: Optional[str] = None
    observaciones: Optional[str] = None
    acciones_mejora: Optional[str] = None


RESULTADOS_SIM = ("SATISFACTORIO", "ACEPTABLE", "DEFICIENTE")


def _validar_brig(d: BrigadistaIn):
    if not d.nombre.strip() or not d.rol.strip():
        raise HTTPException(422, "Faltan el nombre o el rol")


def _validar_sim(d: SimulacroIn):
    if not d.tipo.strip():
        raise HTTPException(422, "Falta el tipo de simulacro")
    if d.resultado and d.resultado not in RESULTADOS_SIM:
        raise HTTPException(422, f"Resultado: uno de {RESULTADOS_SIM}")
    if (d.participantes is not None and d.participantes < 0) or (d.tiempo_respuesta_seg is not None and d.tiempo_respuesta_seg < 0):
        raise HTTPException(422, "Participantes y tiempo no pueden ser negativos")


@router.get("/brigada")
async def list_brigada(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    q = _vivos(SstBrigadista).order_by(SstBrigadista.rol, SstBrigadista.nombre)
    return [_brig_dict(r) for r in (await db.execute(q)).scalars().all()]


@router.post("/brigada", status_code=201)
async def create_brigadista(data: BrigadistaIn, db: AsyncSession = Depends(get_db),
                            current_user: Usuario = Depends(get_current_user)):
    _validar_brig(data)
    obj = SstBrigadista(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _brig_dict(obj)


@router.put("/brigada/{id}")
async def update_brigadista(id: int, data: BrigadistaIn, db: AsyncSession = Depends(get_db),
                            current_user: Usuario = Depends(get_current_user)):
    _validar_brig(data)
    obj = await _obtener(db, SstBrigadista, id, "Brigadista")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return _brig_dict(obj)


@router.delete("/brigada/{id}", status_code=204)
async def delete_brigadista(id: int, db: AsyncSession = Depends(get_db),
                            current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstBrigadista, id, "Brigadista")


@router.get("/simulacros")
async def list_simulacros(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    q = _vivos(SstSimulacro).order_by(SstSimulacro.fecha.desc())
    return [_sim_dict(r) for r in (await db.execute(q)).scalars().all()]


@router.post("/simulacros", status_code=201)
async def create_simulacro(data: SimulacroIn, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    _validar_sim(data)
    obj = SstSimulacro(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _sim_dict(obj)


@router.put("/simulacros/{id}")
async def update_simulacro(id: int, data: SimulacroIn, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    _validar_sim(data)
    obj = await _obtener(db, SstSimulacro, id, "Simulacro")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return _sim_dict(obj)


@router.delete("/simulacros/{id}", status_code=204)
async def delete_simulacro(id: int, db: AsyncSession = Depends(get_db),
                           current_user: Usuario = Depends(get_current_user)):
    await _retirar(db, SstSimulacro, id, "Simulacro")


# ─── Períodos (exposición) ───────────────────────────────────────────────────

class PeriodoIn(BaseModel):
    anio: int
    mes: int
    trabajadores: int
    horas_hombre: float
    dias_ausencia_medica: float = 0
    dias_programados: Optional[float] = None


def _periodo_dict(p: SstPeriodo) -> dict:
    return {"id": p.id, "anio": p.anio, "mes": p.mes, "trabajadores": p.trabajadores,
            "horas_hombre": p.horas_hombre, "dias_ausencia_medica": p.dias_ausencia_medica or 0,
            "dias_programados": p.dias_programados}


@router.get("/periodos")
async def list_periodos(anio: Optional[int] = None, db: AsyncSession = Depends(get_db),
                        current_user: Usuario = Depends(get_current_user)):
    q = select(SstPeriodo)
    if anio: q = q.where(SstPeriodo.anio == anio)
    q = q.order_by(SstPeriodo.anio.desc(), SstPeriodo.mes.desc())
    return [_periodo_dict(p) for p in (await db.execute(q)).scalars().all()]


@router.put("/periodos")
async def guardar_periodo(data: PeriodoIn, db: AsyncSession = Depends(get_db),
                          current_user: Usuario = Depends(get_current_user)):
    """Crea o reemplaza el mes: hay uno solo por año y mes."""
    if not 1 <= data.mes <= 12:
        raise HTTPException(422, "El mes va de 1 a 12")
    if data.trabajadores <= 0 or data.horas_hombre <= 0:
        raise HTTPException(422, "Trabajadores y horas-hombre deben ser mayores que cero")
    if data.dias_ausencia_medica < 0:
        raise HTTPException(422, "Los días de ausencia no pueden ser negativos")
    p = (await db.execute(select(SstPeriodo).where(SstPeriodo.anio == data.anio,
                                                   SstPeriodo.mes == data.mes))).scalar_one_or_none()
    if not p:
        p = SstPeriodo(anio=data.anio, mes=data.mes)
        db.add(p)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return _periodo_dict(p)


@router.delete("/periodos/{id}", status_code=204)
async def delete_periodo(id: int, db: AsyncSession = Depends(get_db),
                         current_user: Usuario = Depends(get_current_user)):
    p = await db.get(SstPeriodo, id)
    if not p:
        raise HTTPException(404, "Período no encontrado")
    await db.delete(p)
    await db.commit()


# ─── Indicadores ──────────────────────────────────────────────────────────────

@router.get("/indicadores")
async def indicadores(anio: Optional[int] = None, db: AsyncSession = Depends(get_db),
                      current_user: Usuario = Depends(get_current_user)):
    """Indicadores del SG-SST por mes y del año, calculados con los registros.

    Con horas-hombre (NTC 3701):
      IF  = AT con incapacidad × 1.000.000 / horas-hombre
      IS  = días perdidos × 1.000.000 / horas-hombre
      ILI = IF × IS / 1.000
    Con trabajadores (Resolución 0312 de 2019, art. 30):
      Frecuencia = AT del mes × 100 / trabajadores
      Severidad  = días de incapacidad por AT × 100 / trabajadores
      Ausentismo = días de ausencia médica × 100 / días programados

    Un mes sin período registrado no tiene índice: sale nulo. Dividir por una
    exposición inventada daría una cifra que parece medida y no lo es.
    """
    anio = anio or date.today().year
    periodos = {p.mes: p for p in (await db.execute(
        select(SstPeriodo).where(SstPeriodo.anio == anio))).scalars().all()}
    incs = (await db.execute(_vivos(SstIncidente).where(
        func.extract("year", SstIncidente.fecha_evento) == anio))).scalars().all()
    insps = (await db.execute(_vivos(SstInspeccion).where(
        func.extract("year", SstInspeccion.fecha_programada) == anio))).scalars().all()
    caps = (await db.execute(_vivos(SstCapacitacion).where(
        func.extract("year", SstCapacitacion.fecha_inicio) == anio))).scalars().all()

    def ronda(x, n=2):
        return round(x, n) if x is not None else None

    meses = []
    for m in range(1, 13):
        del_mes = [i for i in incs if i.fecha_evento.month == m]
        at = [i for i in del_mes if i.tipo == TipoIncidenteSST.ACCIDENTE_TRABAJO]
        at_incap = [i for i in at if (i.dias_incapacidad or 0) > 0]
        dias = sum(i.dias_incapacidad or 0 for i in at)
        p = periodos.get(m)
        hh = p.horas_hombre if p else None
        tr = p.trabajadores if p else None
        if_ = len(at_incap) * 1_000_000 / hh if hh else None
        is_ = dias * 1_000_000 / hh if hh else None
        meses.append({
            "mes": m, "accidentes": len(at), "incidentes": len(del_mes) - len(at),
            "dias_perdidos": dias, "trabajadores": tr, "horas_hombre": hh,
            "if": ronda(if_), "is": ronda(is_),
            "ili": ronda(if_ * is_ / 1000, 3) if if_ is not None and is_ is not None else None,
            "frecuencia_0312": ronda(len(at) * 100 / tr) if tr else None,
            "severidad_0312": ronda(dias * 100 / tr) if tr else None,
            "ausentismo": ronda(p.dias_ausencia_medica * 100 / p.dias_programados)
                          if p and p.dias_programados else None,
            "inspecciones_programadas": sum(1 for i in insps if i.fecha_programada and i.fecha_programada.month == m
                                            and _v(i.estado) != "CANCELADA"),
            "inspecciones_completadas": sum(1 for i in insps if i.fecha_programada and i.fecha_programada.month == m
                                            and _v(i.estado) == "COMPLETADA"),
            "capacitaciones_programadas": sum(1 for c in caps if c.fecha_inicio and c.fecha_inicio.month == m
                                              and _v(c.estado) != "CANCELADA"),
            "capacitaciones_completadas": sum(1 for c in caps if c.fecha_inicio and c.fecha_inicio.month == m
                                              and _v(c.estado) == "COMPLETADA"),
            "participantes": sum(c.participantes or 0 for c in caps if c.fecha_inicio and c.fecha_inicio.month == m),
        })

    # Del año: sobre los meses con período. Un accidente en un mes sin horas
    # registradas no entra al índice anual, y se avisa cuántos quedaron fuera.
    con_p = [x for x in meses if x["horas_hombre"]]
    hh_anio = sum(x["horas_hombre"] for x in con_p)
    at_anio = sum(1 for i in incs if i.tipo == TipoIncidenteSST.ACCIDENTE_TRABAJO
                  and (i.dias_incapacidad or 0) > 0 and i.fecha_evento.month in periodos)
    dias_anio = sum(x["dias_perdidos"] for x in con_p)
    if_a = at_anio * 1_000_000 / hh_anio if hh_anio else None
    is_a = dias_anio * 1_000_000 / hh_anio if hh_anio else None
    at_total = [i for i in incs if i.tipo == TipoIncidenteSST.ACCIDENTE_TRABAJO]
    mortales = sum(1 for i in at_total if i.gravedad == GravedadSST.MORTAL)
    ip, ic = sum(x["inspecciones_programadas"] for x in meses), sum(x["inspecciones_completadas"] for x in meses)
    cp, cc = sum(x["capacitaciones_programadas"] for x in meses), sum(x["capacitaciones_completadas"] for x in meses)

    epp = (await db.execute(_vivos(SstEntregaEPP).where(SstEntregaEPP.devuelto.is_(False)))).scalars().all()
    hoy = date.today()
    epp_vig = [e for e in epp if not (e.fecha_vencimiento and e.fecha_vencimiento < hoy)]

    return {
        "anio": anio,
        "meses": meses,
        "anual": {
            "if": ronda(if_a), "is": ronda(is_a),
            "ili": ronda(if_a * is_a / 1000, 3) if if_a is not None and is_a is not None else None,
            "meses_con_periodo": len(con_p),
            "accidentes_sin_periodo": sum(1 for i in at_total if i.fecha_evento.month not in periodos),
            "proporcion_at_mortales": ronda(mortales * 100 / len(at_total)) if at_total else None,
            "cumplimiento_inspecciones": ronda(ic * 100 / ip) if ip else None,
            "cumplimiento_capacitaciones": ronda(cc * 100 / cp) if cp else None,
            "epp_vigentes_pct": ronda(len(epp_vig) * 100 / len(epp)) if epp else None,
        },
        "epp_por_tipo": [{"tipo": t.value, "cantidad": sum(e.cantidad or 0 for e in epp if e.tipo_epp == t)}
                         for t in TipoEPP],
    }


# ─── Configuración ───────────────────────────────────────────────────────────

# Lo que se configura, con su valor por defecto. Las metas las lee la pantalla
# de indicadores para decir si cada cifra cumple.
CONFIG_SST: Dict[str, str] = {
    "empresa": "", "nit": "", "arl": "", "clase_riesgo": "",
    "responsable_sst": "", "correo_responsable": "",
    "meta_if": "10", "meta_is": "100", "meta_dias_sin_accidente": "60",
    "meta_cumplimiento_capacitaciones": "90", "meta_cumplimiento_inspecciones": "95",
    "meta_epp_vigentes": "100",
}


@router.get("/config")
async def leer_config(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    guardado = {c.clave: c.valor for c in (await db.execute(select(SstConfig))).scalars().all()}
    return {k: guardado.get(k, d) for k, d in CONFIG_SST.items()}


@router.put("/config")
async def guardar_config(data: Dict[str, str], db: AsyncSession = Depends(get_db),
                         current_user: Usuario = Depends(get_current_user)):
    desconocidas = set(data) - set(CONFIG_SST)
    if desconocidas:
        raise HTTPException(422, f"Clave desconocida: {', '.join(sorted(desconocidas))}")
    for k, v in data.items():
        if k.startswith("meta_"):
            try:
                if float(v) < 0:
                    raise ValueError
            except ValueError:
                raise HTTPException(422, f"{k}: debe ser un número no negativo")
    existentes = {c.clave: c for c in (await db.execute(
        select(SstConfig).where(SstConfig.clave.in_(list(data))))).scalars().all()}
    for k, v in data.items():
        if k in existentes:
            existentes[k].valor = v.strip()
        else:
            db.add(SstConfig(clave=k, valor=v.strip()))
    await db.commit()
    return await leer_config(db, current_user)
