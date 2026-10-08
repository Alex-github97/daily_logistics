"""
API endpoints — QMS (Quality Management System)
Prefijo: /qms
"""
from datetime import date, datetime
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.infrastructure.models.mes import MESOEERegistro, MESOrdenProduccion, MESParada
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.qms import (
    QMSProceso, QMSProcedimiento, QMSIndicador, QMSMetaIndicador,
    QMSMedicionIndicador, QMSNoConformidad, QMSHallazgo, QMSAuditoria,
    QMSAuditoriaHallazgo, QMSCAPA, QMSCAPATarea, QMSRiesgo,
    QMSQueja, QMSEvaluacionProveedor, QMSCambio, QMSMejora,
    QMSEncuesta, QMSEncuestaRespuesta, QMSCompetenciaProceso, QMSKPIDiario,
    QMSCertificacion, QMSParametro,
    EstadoAuditoriaQMSEnum, EstadoCAPAQMSEnum, EstadoHallazgoQMSEnum,
    EstadoMejoraQMSEnum, EstadoNCQMSEnum, PrioridadRiesgoQMSEnum,
)
from app.application.schemas.qms import (
    QMSProcesoCreate, QMSProcesoUpdate, QMSProcesoResponse,
    QMSProcedimientoCreate, QMSProcedimientoUpdate, QMSProcedimientoResponse,
    QMSIndicadorCreate, QMSIndicadorUpdate, QMSIndicadorResponse,
    QMSMetaIndicadorCreate, QMSMetaIndicadorResponse,
    QMSMedicionIndicadorCreate, QMSMedicionIndicadorResponse,
    QMSNoConformidadCreate, QMSNoConformidadUpdate, QMSNoConformidadResponse,
    QMSHallazgoCreate, QMSHallazgoUpdate, QMSHallazgoResponse,
    QMSAuditoriaCreate, QMSAuditoriaUpdate, QMSAuditoriaResponse,
    QMSAuditoriaHallazgoCreate, QMSAuditoriaHallazgoResponse,
    QMSCAPACreate, QMSCAPAUpdate, QMSCAPAResponse,
    QMSCAPATareaCreate, QMSCAPATareaUpdate, QMSCAPATareaResponse,
    QMSRiesgoCreate, QMSRiesgoUpdate, QMSRiesgoResponse,
    QMSQuejaCreate, QMSQuejaUpdate, QMSQuejaResponse,
    QMSEvaluacionProveedorCreate, QMSEvaluacionProveedorUpdate, QMSEvaluacionProveedorResponse,
    QMSCambioCreate, QMSCambioUpdate, QMSCambioResponse,
    QMSMejoraCreate, QMSMejoraUpdate, QMSMejoraResponse,
    QMSEncuestaCreate, QMSEncuestaUpdate, QMSEncuestaResponse,
    QMSEncuestaRespuestaCreate, QMSEncuestaRespuestaResponse,
    QMSCompetenciaProcesoCreate, QMSCompetenciaProcesoResponse,
    QMSKPIDiarioResponse, QMSDashboardKPIs,
)

router = APIRouter(prefix="/qms", tags=["QMS"])


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _calcular_prioridad_riesgo(nivel: int) -> str:
    """Determina la prioridad de un riesgo según su nivel (prob * impacto)."""
    if nivel <= 4:
        return "BAJA"
    elif nivel <= 9:
        return "MEDIA"
    elif nivel <= 14:
        return "ALTA"
    else:
        return "CRITICA"


def _calcular_clasificacion_proveedor(puntaje: float) -> str:
    """Determina la clasificación de un proveedor según su puntaje total."""
    if puntaje >= 90:
        return "excelente"
    elif puntaje >= 75:
        return "bueno"
    elif puntaje >= 60:
        return "regular"
    else:
        return "deficiente"


# ===========================================================================
# 1. DASHBOARD KPIs
# ===========================================================================

@router.get("/dashboard", response_model=QMSDashboardKPIs)
async def get_qms_dashboard(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Las cifras del sistema de calidad, tal como las pide el tablero.

    DOS COSAS QUE ESTABAN MAL Y POR QUÉ IMPORTAN

    · **Se calculaban ocho cifras que nadie veía.** La función construía el
      resultado con nombres —`capa_abiertas`, `auditorias_en_curso`,
      `mejoras_implementadas`— que el esquema de respuesta no declara. Pydantic
      descarta en silencio lo que no conoce, así que el trabajo se hacía y el
      tablero mostraba el cero por defecto de cada campo. No fallaba nada: solo
      decía que no había nada.

    · **Los estados se comparaban con cadenas escritas a mano.** Media docena en
      minúscula contra enums en mayúscula. La base rechazaba el texto y toda la
      consulta caía con un 500, con lo que el tablero entero del módulo no
      abría.

    Ahora las comparaciones van contra el enum cuando la columna es un enum, y
    contra la cadena cuando la columna es texto —`qms_riesgo.estado` y
    `qms_queja.estado` lo son—. Mezclarlos es justamente lo que produjo el fallo.
    """
    hoy = date.today()
    inicio_mes = datetime(hoy.year, hoy.month, 1)

    # Lo cerrado «este mes» se cuenta por la FECHA DE CIERRE, no por la de
    # última modificación: `updated_at` cambia al reasignar el responsable o al
    # corregir una tilde, y contarlo así infla el mes con ediciones que no
    # cerraron nada.
    async def contar(modelo, *condiciones) -> int:
        r = await db.execute(select(func.count(modelo.id)).where(and_(*condiciones)))
        return r.scalar() or 0

    # ── No conformidades ──────────────────────────────────────────────────────
    nc_abiertas = await contar(
        QMSNoConformidad,
        QMSNoConformidad.deleted_at.is_(None),
        QMSNoConformidad.estado != EstadoNCQMSEnum.CERRADA,
    )
    nc_cerradas_mes = await contar(
        QMSNoConformidad,
        QMSNoConformidad.deleted_at.is_(None),
        QMSNoConformidad.estado == EstadoNCQMSEnum.CERRADA,
        QMSNoConformidad.fecha_cierre >= inicio_mes,
    )

    # ── Hallazgos ─────────────────────────────────────────────────────────────
    hallazgos_abiertos = await contar(
        QMSHallazgo,
        QMSHallazgo.deleted_at.is_(None),
        QMSHallazgo.estado != EstadoHallazgoQMSEnum.CERRADO,
    )
    hallazgos_cerrados_mes = await contar(
        QMSHallazgo,
        QMSHallazgo.deleted_at.is_(None),
        QMSHallazgo.estado == EstadoHallazgoQMSEnum.CERRADO,
        QMSHallazgo.fecha_cierre >= inicio_mes,
    )

    # ── Acciones correctivas ──────────────────────────────────────────────────
    #
    # «Activa» es todo lo que no está cerrado, incluidas las vencidas: una acción
    # vencida sigue pendiente de hacerse. Sacarlas del recuento de activas haría
    # que el tablero mejore justo cuando el trabajo se atrasa.
    capas_activas = await contar(
        QMSCAPA,
        QMSCAPA.deleted_at.is_(None),
        QMSCAPA.estado != EstadoCAPAQMSEnum.CERRADA,
    )
    # Vencida es lo que ya pasó su fecha límite, se haya marcado o no. La marca
    # depende de que alguien la ponga; la fecha, no.
    capas_vencidas = await contar(
        QMSCAPA,
        QMSCAPA.deleted_at.is_(None),
        QMSCAPA.estado != EstadoCAPAQMSEnum.CERRADA,
        or_(
            QMSCAPA.estado == EstadoCAPAQMSEnum.VENCIDA,
            and_(QMSCAPA.fecha_limite.isnot(None),
                 QMSCAPA.fecha_limite < datetime.utcnow()),
        ),
    )

    # ── Auditorías ────────────────────────────────────────────────────────────
    #
    # Pendiente es lo que aún hay que hacer: lo planificado y lo que está en
    # ejecución. Contar solo lo que ya empezó esconde justamente lo que no ha
    # empezado y debería.
    auditorias_pendientes = await contar(
        QMSAuditoria,
        QMSAuditoria.deleted_at.is_(None),
        QMSAuditoria.estado.in_([EstadoAuditoriaQMSEnum.PLANIFICADA,
                                 EstadoAuditoriaQMSEnum.EN_EJECUCION]),
    )
    auditorias_completadas_mes = await contar(
        QMSAuditoria,
        QMSAuditoria.deleted_at.is_(None),
        QMSAuditoria.estado == EstadoAuditoriaQMSEnum.COMPLETADA,
        QMSAuditoria.fecha_fin_real >= inicio_mes,
    )

    # ── Riesgos y quejas ──────────────────────────────────────────────────────
    #
    # `prioridad` es un enum; `estado` en riesgos y quejas es texto libre. Por
    # eso una comparación va contra el enum y la otra contra la cadena.
    riesgos_criticos = await contar(
        QMSRiesgo,
        QMSRiesgo.deleted_at.is_(None),
        QMSRiesgo.prioridad == PrioridadRiesgoQMSEnum.CRITICA,
    )
    quejas_abiertas = await contar(
        QMSQueja,
        QMSQueja.deleted_at.is_(None),
        QMSQueja.estado != "cerrada",
    )
    quejas_cerradas_mes = await contar(
        QMSQueja,
        QMSQueja.deleted_at.is_(None),
        QMSQueja.estado == "cerrada",
        QMSQueja.fecha_cierre >= inicio_mes,
    )

    # ── Mejoras ───────────────────────────────────────────────────────────────
    #
    # Activa es la que está en marcha o aprobada esperando arrancar. Las ideas y
    # las que están en evaluación todavía no son trabajo comprometido.
    mejoras_activas = await contar(
        QMSMejora,
        QMSMejora.deleted_at.is_(None),
        QMSMejora.estado.in_([EstadoMejoraQMSEnum.APROBADA,
                              EstadoMejoraQMSEnum.EN_CURSO]),
    )

    # ── Satisfacción ──────────────────────────────────────────────────────────
    #
    # El NPS se promedia solo sobre las encuestas que TIENEN uno calculado. Meter
    # las encuestas sin respuestas como cero hunde la cifra y hace creer que los
    # clientes están molestos cuando lo que pasa es que nadie contestó.
    r = await db.execute(
        select(func.avg(QMSEncuesta.nps_score)).where(
            QMSEncuesta.nps_score.isnot(None))
    )
    nps_promedio = round(float(r.scalar() or 0.0), 2)

    # ── Cumplimiento de entregas ──────────────────────────────────────────────
    #
    # El OTIF no lo mide calidad: lo miden transporte y bodega. Aquí solo se
    # refleja si alguien lo configuró como indicador del sistema. Si no está, se
    # devuelve cero y la pantalla dice que no hay medición, en vez de inventar
    # un porcentaje que después alguien lleva a un comité.
    r = await db.execute(
        select(QMSMedicionIndicador.valor)
        .join(QMSIndicador, QMSIndicador.id == QMSMedicionIndicador.indicador_id)
        .where(QMSIndicador.nombre.ilike("%OTIF%"))
        # Se ordena por `periodo`, que es texto «AAAA-MM»: ordenado como texto
        # da el mismo resultado que ordenado como fecha. No hay columna de
        # fecha en la tabla de mediciones.
        .order_by(QMSMedicionIndicador.periodo.desc())
        .limit(1)
    )
    otif_rate = round(float(r.scalar() or 0.0), 2)

    # ── Índice de calidad ─────────────────────────────────────────────────────
    #
    # Base cien, descontando lo que está sin resolver. Es una convención de la
    # casa, no una norma: por eso se calcula a la vista y no se guarda, para que
    # nadie compare el índice de hoy con uno de hace un año calculado de otra
    # forma sin darse cuenta.
    indice_calidad = round(max(0.0, 100.0
                               - nc_abiertas * 2
                               - riesgos_criticos * 3
                               - capas_vencidas * 2), 2)

    return QMSDashboardKPIs(
        nc_abiertas=nc_abiertas,
        nc_cerradas_mes=nc_cerradas_mes,
        hallazgos_abiertos=hallazgos_abiertos,
        hallazgos_cerrados_mes=hallazgos_cerrados_mes,
        capas_vencidas=capas_vencidas,
        capas_activas=capas_activas,
        auditorias_pendientes=auditorias_pendientes,
        auditorias_completadas_mes=auditorias_completadas_mes,
        indice_calidad=indice_calidad,
        otif_rate=otif_rate,
        nps_promedio=nps_promedio,
        mejoras_activas=mejoras_activas,
        riesgos_criticos=riesgos_criticos,
        quejas_abiertas=quejas_abiertas,
        quejas_cerradas_mes=quejas_cerradas_mes,
    )


# ===========================================================================
# 2. PROCESOS
# ===========================================================================

@router.get("/procesos/arbol")
async def arbol_procesos(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Retorna la jerarquía padre-hijo para el mapa de procesos."""
    r = await db.execute(
        select(QMSProceso).where(QMSProceso.activo == True).order_by(QMSProceso.nombre)
    )
    todos = r.scalars().all()

    # Construir árbol
    mapa: dict = {}
    raices: list = []
    for p in todos:
        mapa[p.id] = {"id": p.id, "nombre": p.nombre, "tipo": p.tipo, "hijos": []}
    for p in todos:
        if p.padre_id and p.padre_id in mapa:
            mapa[p.padre_id]["hijos"].append(mapa[p.id])
        elif not p.padre_id:
            raices.append(mapa[p.id])
    return raices


@router.get("/procesos", response_model=List[QMSProcesoResponse])
async def listar_procesos(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    padre_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSProceso).where(QMSProceso.activo == True)
    if tipo:
        q = q.where(QMSProceso.tipo == tipo)
    if estado:
        q = q.where(QMSProceso.estado == estado)
    if padre_id is not None:
        q = q.where(QMSProceso.padre_id == padre_id)
    q = q.order_by(QMSProceso.nombre).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/procesos", response_model=QMSProcesoResponse, status_code=201)
async def crear_proceso(
    data: QMSProcesoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSProceso(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/procesos/{proceso_id}", response_model=QMSProcesoResponse)
async def obtener_proceso(
    proceso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSProceso, proceso_id)
    if not item or not item.activo:
        raise HTTPException(status_code=404, detail="Proceso no encontrado")
    return item


@router.put("/procesos/{proceso_id}", response_model=QMSProcesoResponse)
async def actualizar_proceso(
    proceso_id: int,
    data: QMSProcesoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSProceso, proceso_id)
    if not item or not item.activo:
        raise HTTPException(status_code=404, detail="Proceso no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/procesos/{proceso_id}", status_code=204)
async def eliminar_proceso(
    proceso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSProceso, proceso_id)
    if not item or not item.activo:
        raise HTTPException(status_code=404, detail="Proceso no encontrado")
    item.activo = False
    await db.commit()


# ===========================================================================
# 3. PROCEDIMIENTOS
# ===========================================================================

@router.get("/procedimientos", response_model=List[QMSProcedimientoResponse])
async def listar_procedimientos(
    proceso_id: Optional[int] = None,
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSProcedimiento).where(QMSProcedimiento.activo.is_(True))
    if proceso_id is not None:
        q = q.where(QMSProcedimiento.proceso_id == proceso_id)
    if tipo:
        q = q.where(QMSProcedimiento.tipo == tipo)
    if estado:
        q = q.where(QMSProcedimiento.estado == estado)
    q = q.order_by(QMSProcedimiento.nombre).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/procedimientos", response_model=QMSProcedimientoResponse, status_code=201)
async def crear_procedimiento(
    data: QMSProcedimientoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSProcedimiento(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/procedimientos/{proc_id}", response_model=QMSProcedimientoResponse)
async def actualizar_procedimiento(
    proc_id: int,
    data: QMSProcedimientoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSProcedimiento, proc_id)
    if not item or not item.activo:
        raise HTTPException(status_code=404, detail="Ese procedimiento no existe.")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/procedimientos/{proc_id}", status_code=204)
async def eliminar_procedimiento(
    proc_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSProcedimiento, proc_id)
    if not item or not item.activo:
        raise HTTPException(status_code=404, detail="Ese procedimiento no existe.")
    # Se desactiva en vez de borrarse: un procedimiento retirado sigue siendo la
    # versión bajo la que se hicieron las auditorías del año pasado, y borrarlo
    # dejaría esos hallazgos citando algo que ya no existe.
    item.activo = False
    await db.commit()


# ===========================================================================
# 4. INDICADORES Y MEDICIONES
# ===========================================================================

@router.get("/indicadores", response_model=List[QMSIndicadorResponse])
async def listar_indicadores(
    proceso_id: Optional[int] = None,
    tipo: Optional[str] = None,
    activo: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSIndicador)
    if proceso_id is not None:
        q = q.where(QMSIndicador.proceso_id == proceso_id)
    if tipo:
        q = q.where(QMSIndicador.tipo == tipo)
    if activo is not None:
        q = q.where(QMSIndicador.activo == activo)
    q = q.order_by(QMSIndicador.nombre).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/indicadores", response_model=QMSIndicadorResponse, status_code=201)
async def crear_indicador(
    data: QMSIndicadorCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSIndicador(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


def _f(v):
    return float(v) if v is not None else None

@router.get("/indicadores/tablero")
async def tablero_indicadores(
    solo_activos: bool = True,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Tablero de KPIs: cada indicador configurado con su última medición,
    cumplimiento vs meta y un histórico corto para el sparkline."""
    q = select(QMSIndicador)
    if solo_activos:
        q = q.where(QMSIndicador.activo == True)
    r = await db.execute(q.order_by(QMSIndicador.nombre))
    out = []
    for ind in r.scalars().all():
        rm = await db.execute(
            select(QMSMedicionIndicador)
            .where(QMSMedicionIndicador.indicador_id == ind.id)
            .order_by(QMSMedicionIndicador.periodo.desc())
            .limit(8)
        )
        meds = rm.scalars().all()
        ultima = meds[0] if meds else None
        out.append({
            "id": ind.id, "codigo": ind.codigo, "nombre": ind.nombre,
            "tipo": ind.tipo, "unidad": ind.unidad, "frecuencia": ind.frecuencia,
            "modulo_origen": ind.modulo_origen, "proceso_id": ind.proceso_id, "activo": ind.activo,
            "meta": _f(ind.meta), "meta_min": _f(ind.meta_min), "meta_max": _f(ind.meta_max),
            "valor_actual": _f(ultima.valor) if ultima else None,
            "periodo_actual": ultima.periodo if ultima else None,
            "cumple": ultima.cumple_meta if ultima else None,
            "variacion_pct": _f(ultima.variacion_pct) if ultima else None,
            "historico": [_f(m.valor) for m in reversed(meds)],
        })
    return out

@router.get("/mediciones", response_model=List[QMSMedicionIndicadorResponse])
async def listar_mediciones(
    indicador_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSMedicionIndicador)
    if indicador_id is not None:
        q = q.where(QMSMedicionIndicador.indicador_id == indicador_id)
    q = q.order_by(QMSMedicionIndicador.created_at.desc()).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()

# ─── Fuentes de indicadores de la plataforma (para arrastrar al QMS) ──────────
# `auto`=True: el valor se calcula desde los datos reales del módulo origen.
# `direccion`: 'mayor' → cumple si valor >= meta; 'menor' → cumple si valor <= meta.
PLATFORM_SOURCES: List[dict] = [
    {"key": "MES_OEE",            "nombre": "OEE Global (MES)",                 "modulo": "MES",      "unidad": "%",   "tipo": "operativo",   "meta": 85, "direccion": "mayor", "auto": True},
    {"key": "MES_CUMPLIMIENTO",   "nombre": "Cumplimiento de producción (MES)", "modulo": "MES",      "unidad": "%",   "tipo": "operativo",   "meta": 95, "direccion": "mayor", "auto": True},
    {"key": "MES_SCRAP",          "nombre": "Scrap rate (MES)",                 "modulo": "MES",      "unidad": "%",   "tipo": "operativo",   "meta": 3,  "direccion": "menor", "auto": True},
    {"key": "MES_PARADAS",        "nombre": "Minutos de parada (MES)",          "modulo": "MES",      "unidad": "min", "tipo": "operativo",   "meta": 0,  "direccion": "menor", "auto": True},
    {"key": "TMS_OTIF",           "nombre": "OTIF Transporte (TMS)",            "modulo": "TMS",      "unidad": "%",   "tipo": "operativo",   "meta": 95, "direccion": "mayor", "auto": False},
    {"key": "WMS_EXACTITUD",      "nombre": "Exactitud de inventario (WMS)",    "modulo": "WMS",      "unidad": "%",   "tipo": "operativo",   "meta": 98, "direccion": "mayor", "auto": False},
    {"key": "WMS_RECHAZO",        "nombre": "Índice de rechazo (WMS)",          "modulo": "WMS",      "unidad": "%",   "tipo": "operativo",   "meta": 1,  "direccion": "menor", "auto": False},
    {"key": "CRM_SATISFACCION",   "nombre": "Satisfacción del cliente (CRM)",   "modulo": "CRM",      "unidad": "/5",  "tipo": "tactico",     "meta": 4.5, "direccion": "mayor", "auto": False},
    {"key": "SST_ACCIDENTES",     "nombre": "Accidentes SST",                   "modulo": "SST",      "unidad": "und", "tipo": "estrategico", "meta": 0,  "direccion": "menor", "auto": False},
    {"key": "COMPRAS_PROVEEDORES","nombre": "Proveedores aprobados (Compras)",  "modulo": "Compras",  "unidad": "%",   "tipo": "tactico",     "meta": 90, "direccion": "mayor", "auto": False},
    {"key": "EAM_DISPONIBILIDAD", "nombre": "Disponibilidad de flota (EAM)",    "modulo": "EAM",      "unidad": "%",   "tipo": "operativo",   "meta": 92, "direccion": "mayor", "auto": False},
]
_SOURCE_BY_KEY = {s["key"]: s for s in PLATFORM_SOURCES}


def _cumple(valor: Optional[float], meta: Optional[float], direccion: str) -> Optional[bool]:
    if valor is None or meta is None:
        return None
    return valor <= meta if direccion == "menor" else valor >= meta


def _rango_periodos(desde: str, hasta: str) -> List[str]:
    y1, m1 = int(desde[:4]), int(desde[5:7])
    y2, m2 = int(hasta[:4]), int(hasta[5:7])
    out: List[str] = []
    y, m = y1, m1
    while (y, m) <= (y2, m2) and len(out) < 60:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


async def _serie_fuente(db: AsyncSession, key: str, desde: str, hasta: str) -> Dict[str, float]:
    """Calcula el valor real del indicador por período (YYYY-MM) desde el módulo origen."""
    out: Dict[str, float] = {}
    if key == "MES_OEE":
        per = func.to_char(MESOEERegistro.fecha, "YYYY-MM")
        q = select(per, func.avg(MESOEERegistro.oee)).where(per >= desde, per <= hasta).group_by(per)
        for p, v in (await db.execute(q)).all():
            if v is not None:
                out[p] = round(float(v), 2)
    elif key in ("MES_CUMPLIMIENTO", "MES_SCRAP"):
        per = func.to_char(MESOrdenProduccion.fecha_fin_real, "YYYY-MM")
        q = (select(per, func.sum(MESOrdenProduccion.cantidad_producida), func.sum(MESOrdenProduccion.cantidad_scrap),
                    func.sum(MESOrdenProduccion.cantidad_planificada))
             .where(MESOrdenProduccion.fecha_fin_real.isnot(None), per >= desde, per <= hasta).group_by(per))
        for p, prod, scrap, plan in (await db.execute(q)).all():
            prod = float(prod or 0); scrap = float(scrap or 0); plan = float(plan or 0)
            if key == "MES_CUMPLIMIENTO" and plan > 0:
                out[p] = round(prod / plan * 100, 2)
            elif key == "MES_SCRAP" and (prod + scrap) > 0:
                out[p] = round(scrap / (prod + scrap) * 100, 2)
    elif key == "MES_PARADAS":
        per = func.to_char(MESParada.fecha_inicio, "YYYY-MM")
        q = select(per, func.sum(MESParada.duracion_min)).where(per >= desde, per <= hasta).group_by(per)
        for p, v in (await db.execute(q)).all():
            out[p] = round(float(v or 0), 1)
    return out


@router.get("/fuentes")
async def fuentes_indicadores(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Catálogo de indicadores disponibles en la plataforma para arrastrar al QMS."""
    r = await db.execute(select(QMSIndicador.codigo))
    existentes = {c for (c,) in r.all() if c}
    return [{**s, "importado": s["key"] in existentes} for s in PLATFORM_SOURCES]


class ImportarReq(BaseModel):
    claves: List[str]

@router.post("/indicadores/importar")
async def importar_indicadores(data: ImportarReq, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Da de alta en el QMS los indicadores seleccionados del resto de módulos."""
    creados = 0
    for key in data.claves:
        src = _SOURCE_BY_KEY.get(key)
        if not src:
            continue
        ex = await db.execute(select(QMSIndicador).where(QMSIndicador.codigo == key))
        if ex.scalar_one_or_none():
            continue
        db.add(QMSIndicador(
            codigo=key, nombre=src["nombre"], modulo_origen=src["modulo"], unidad=src["unidad"],
            tipo=src["tipo"], frecuencia="mensual", meta=src["meta"], activo=True,
        ))
        creados += 1
    await db.commit()
    return {"creados": creados}


class SincronizarReq(BaseModel):
    desde: str   # YYYY-MM
    hasta: str

@router.post("/indicadores/sincronizar")
async def sincronizar_indicadores(data: SincronizarReq, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Arrastra (upsert) los valores reales por período de los indicadores automáticos."""
    r = await db.execute(select(QMSIndicador).where(QMSIndicador.codigo.isnot(None)))
    inds = r.scalars().all()
    total, autos = 0, 0
    for ind in inds:
        src = _SOURCE_BY_KEY.get(ind.codigo or "")
        if not src or not src["auto"]:
            continue
        autos += 1
        serie = await _serie_fuente(db, ind.codigo, data.desde, data.hasta)
        meta = float(ind.meta) if ind.meta is not None else None
        for periodo, valor in serie.items():
            ex = await db.execute(
                select(QMSMedicionIndicador).where(
                    QMSMedicionIndicador.indicador_id == ind.id,
                    QMSMedicionIndicador.periodo == periodo,
                )
            )
            m = ex.scalar_one_or_none()
            cumple = _cumple(valor, meta, src["direccion"])
            if m:
                m.valor = valor; m.cumple_meta = cumple
            else:
                db.add(QMSMedicionIndicador(indicador_id=ind.id, periodo=periodo, valor=valor, cumple_meta=cumple))
            total += 1
    await db.commit()
    return {"indicadores_automaticos": autos, "mediciones_sincronizadas": total}


@router.get("/matriz")
async def matriz_cumplimiento(
    desde: str = Query(..., description="YYYY-MM"),
    hasta: str = Query(..., description="YYYY-MM"),
    modulo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Matriz de cumplimiento indicadores × períodos (auditoría y seguimiento)."""
    periodos = _rango_periodos(desde, hasta)
    q = select(QMSIndicador).where(QMSIndicador.activo == True)
    if modulo:
        q = q.where(QMSIndicador.modulo_origen == modulo)
    r = await db.execute(q.order_by(QMSIndicador.modulo_origen, QMSIndicador.nombre))
    filas = []
    for ind in r.scalars().all():
        rm = await db.execute(
            select(QMSMedicionIndicador).where(
                QMSMedicionIndicador.indicador_id == ind.id,
                QMSMedicionIndicador.periodo >= desde,
                QMSMedicionIndicador.periodo <= hasta,
            )
        )
        med = {m.periodo: m for m in rm.scalars().all()}
        valores = {}
        cumplidos = contados = 0
        for p in periodos:
            m = med.get(p)
            if m:
                valores[p] = {"valor": float(m.valor), "cumple": m.cumple_meta}
                contados += 1
                if m.cumple_meta:
                    cumplidos += 1
            else:
                valores[p] = None
        filas.append({
            "id": ind.id, "codigo": ind.codigo, "nombre": ind.nombre,
            "modulo_origen": ind.modulo_origen, "unidad": ind.unidad,
            "meta": float(ind.meta) if ind.meta is not None else None,
            "auto": _SOURCE_BY_KEY.get(ind.codigo or "", {}).get("auto", False),
            "valores": valores,
            "cumplimiento_pct": round(cumplidos / contados * 100, 1) if contados else None,
        })
    return {"periodos": periodos, "filas": filas}


@router.get("/indicadores/{ind_id}", response_model=QMSIndicadorResponse)
async def obtener_indicador(
    ind_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSIndicador, ind_id)
    if not item:
        raise HTTPException(status_code=404, detail="Indicador no encontrado")
    return item


@router.put("/indicadores/{ind_id}", response_model=QMSIndicadorResponse)
async def actualizar_indicador(
    ind_id: int,
    data: QMSIndicadorUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSIndicador, ind_id)
    if not item:
        raise HTTPException(status_code=404, detail="Indicador no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/indicadores/{ind_id}/mediciones", response_model=List[QMSMedicionIndicadorResponse])
async def listar_mediciones_indicador(
    ind_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = (
        select(QMSMedicionIndicador)
        .where(QMSMedicionIndicador.indicador_id == ind_id)
        # La medición no tiene fecha: tiene período (YYYY-MM), que ordena igual.
        .order_by(QMSMedicionIndicador.periodo.desc(), QMSMedicionIndicador.id.desc())
        .offset(skip)
        .limit(limit)
    )
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/mediciones", response_model=QMSMedicionIndicadorResponse, status_code=201)
async def registrar_medicion(
    data: QMSMedicionIndicadorCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSMedicionIndicador(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/metas", response_model=List[QMSMetaIndicadorResponse])
async def listar_metas(
    indicador_id: Optional[int] = None,
    periodo: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSMetaIndicador)
    if indicador_id is not None:
        q = q.where(QMSMetaIndicador.indicador_id == indicador_id)
    if periodo:
        q = q.where(QMSMetaIndicador.periodo == periodo)
    q = q.order_by(QMSMetaIndicador.id.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/metas", response_model=QMSMetaIndicadorResponse, status_code=201)
async def crear_meta(
    data: QMSMetaIndicadorCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSMetaIndicador(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


# ===========================================================================
# 5. NO CONFORMIDADES
# ===========================================================================

@router.get("/no-conformidades", response_model=List[QMSNoConformidadResponse])
async def listar_no_conformidades(
    estado: Optional[str] = None,
    clasificacion: Optional[str] = None,
    origen: Optional[str] = None,
    proceso_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSNoConformidad).where(QMSNoConformidad.deleted_at.is_(None))
    if estado:
        q = q.where(QMSNoConformidad.estado == estado)
    if clasificacion:
        q = q.where(QMSNoConformidad.clasificacion == clasificacion)
    if origen:
        q = q.where(QMSNoConformidad.origen == origen)
    if proceso_id is not None:
        q = q.where(QMSNoConformidad.proceso_id == proceso_id)
    q = q.order_by(QMSNoConformidad.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/no-conformidades", response_model=QMSNoConformidadResponse, status_code=201)
async def crear_no_conformidad(
    data: QMSNoConformidadCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # Auto-generar código NC-YYYY-NNN
    result = await db.execute(select(func.count(QMSNoConformidad.id)))
    n = (result.scalar() or 0) + 1
    codigo = f"NC-{datetime.now().year}-{n:03d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    item = QMSNoConformidad(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/no-conformidades/{nc_id}", response_model=QMSNoConformidadResponse)
async def obtener_no_conformidad(
    nc_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSNoConformidad, nc_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="No conformidad no encontrada")
    return item


@router.put("/no-conformidades/{nc_id}", response_model=QMSNoConformidadResponse)
async def actualizar_no_conformidad(
    nc_id: int,
    data: QMSNoConformidadUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSNoConformidad, nc_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="No conformidad no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/no-conformidades/{nc_id}", status_code=204)
async def eliminar_no_conformidad(
    nc_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSNoConformidad, nc_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="No conformidad no encontrada")
    item.deleted_at = datetime.utcnow()
    await db.commit()


@router.put("/no-conformidades/{nc_id}/cerrar", response_model=QMSNoConformidadResponse)
async def cerrar_no_conformidad(
    nc_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSNoConformidad, nc_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="No conformidad no encontrada")
    if item.estado == "cerrada":
        raise HTTPException(status_code=400, detail="La no conformidad ya está cerrada")
    item.estado = "cerrada"
    item.fecha_cierre = datetime.utcnow()
    if body.get("observaciones_cierre"):
        item.observaciones_cierre = body["observaciones_cierre"]
    await db.commit()
    await db.refresh(item)
    return item


# ===========================================================================
# 6. HALLAZGOS
# ===========================================================================

@router.get("/hallazgos", response_model=List[QMSHallazgoResponse])
async def listar_hallazgos(
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    auditoria_id: Optional[int] = None,
    proceso_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSHallazgo).where(QMSHallazgo.deleted_at.is_(None))
    if estado:
        q = q.where(QMSHallazgo.estado == estado)
    if tipo:
        q = q.where(QMSHallazgo.tipo == tipo)
    if auditoria_id is not None:
        q = q.where(QMSHallazgo.auditoria_id == auditoria_id)
    if proceso_id is not None:
        q = q.where(QMSHallazgo.proceso_id == proceso_id)
    q = q.order_by(QMSHallazgo.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/hallazgos", response_model=QMSHallazgoResponse, status_code=201)
async def crear_hallazgo(
    data: QMSHallazgoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSHallazgo(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/hallazgos/{hall_id}", response_model=QMSHallazgoResponse)
async def obtener_hallazgo(
    hall_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSHallazgo, hall_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")
    return item


@router.put("/hallazgos/{hall_id}", response_model=QMSHallazgoResponse)
async def actualizar_hallazgo(
    hall_id: int,
    data: QMSHallazgoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSHallazgo, hall_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/hallazgos/{hall_id}", status_code=204)
async def eliminar_hallazgo(
    hall_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSHallazgo, hall_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")
    item.deleted_at = datetime.utcnow()
    await db.commit()


# ===========================================================================
# 7. AUDITORIAS
# ===========================================================================

@router.get("/auditorias", response_model=List[QMSAuditoriaResponse])
async def listar_auditorias(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSAuditoria).where(QMSAuditoria.deleted_at.is_(None))
    if tipo:
        q = q.where(QMSAuditoria.tipo == tipo)
    if estado:
        q = q.where(QMSAuditoria.estado == estado)
    q = q.order_by(QMSAuditoria.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/auditorias", response_model=QMSAuditoriaResponse, status_code=201)
async def crear_auditoria(
    data: QMSAuditoriaCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # Auto-generar código AUD-YYYY-NNN
    result = await db.execute(select(func.count(QMSAuditoria.id)))
    n = (result.scalar() or 0) + 1
    codigo = f"AUD-{datetime.now().year}-{n:03d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    item = QMSAuditoria(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/auditorias/{aud_id}", response_model=QMSAuditoriaResponse)
async def obtener_auditoria(
    aud_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSAuditoria, aud_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    return item


@router.put("/auditorias/{aud_id}", response_model=QMSAuditoriaResponse)
async def actualizar_auditoria(
    aud_id: int,
    data: QMSAuditoriaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSAuditoria, aud_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/auditorias/{aud_id}", status_code=204)
async def eliminar_auditoria(
    aud_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSAuditoria, aud_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    item.deleted_at = datetime.utcnow()
    await db.commit()


@router.post("/auditorias/{aud_id}/hallazgos", response_model=QMSAuditoriaHallazgoResponse, status_code=201)
async def agregar_hallazgo_auditoria(
    aud_id: int,
    data: QMSAuditoriaHallazgoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    aud = await db.get(QMSAuditoria, aud_id)
    if not aud or aud.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    payload = data.model_dump()
    payload["auditoria_id"] = aud_id
    item = QMSAuditoriaHallazgo(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


# ===========================================================================
# 8. CAPA (Acción Correctiva / Preventiva / de Mejora)
# ===========================================================================

@router.get("/capas", response_model=List[QMSCAPAResponse])
async def listar_capas(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    nc_id: Optional[int] = None,
    proceso_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSCAPA).where(QMSCAPA.deleted_at.is_(None))
    if tipo:
        q = q.where(QMSCAPA.tipo == tipo)
    if estado:
        q = q.where(QMSCAPA.estado == estado)
    if nc_id is not None:
        q = q.where(QMSCAPA.nc_id == nc_id)
    if proceso_id is not None:
        q = q.where(QMSCAPA.proceso_id == proceso_id)
    q = q.order_by(QMSCAPA.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/capas", response_model=QMSCAPAResponse, status_code=201)
async def crear_capa(
    data: QMSCAPACreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # Auto-generar código CAPA-YYYY-NNN
    result = await db.execute(select(func.count(QMSCAPA.id)))
    n = (result.scalar() or 0) + 1
    codigo = f"CAPA-{datetime.now().year}-{n:03d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    item = QMSCAPA(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/capas/{capa_id}", response_model=QMSCAPAResponse)
async def obtener_capa(
    capa_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCAPA, capa_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="CAPA no encontrada")
    return item


@router.put("/capas/{capa_id}", response_model=QMSCAPAResponse)
async def actualizar_capa(
    capa_id: int,
    data: QMSCAPAUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCAPA, capa_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="CAPA no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/capas/{capa_id}", status_code=204)
async def eliminar_capa(
    capa_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCAPA, capa_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="CAPA no encontrada")
    item.deleted_at = datetime.utcnow()
    await db.commit()


@router.get("/capas/{capa_id}/tareas", response_model=List[QMSCAPATareaResponse])
async def listar_tareas_capa(
    capa_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = (
        select(QMSCAPATarea)
        .where(QMSCAPATarea.capa_id == capa_id)
        .order_by(QMSCAPATarea.orden)
    )
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/capas/{capa_id}/tareas", response_model=QMSCAPATareaResponse, status_code=201)
async def agregar_tarea_capa(
    capa_id: int,
    data: QMSCAPATareaCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    capa = await db.get(QMSCAPA, capa_id)
    if not capa or capa.deleted_at is not None:
        raise HTTPException(status_code=404, detail="CAPA no encontrada")
    payload = data.model_dump()
    payload["capa_id"] = capa_id
    item = QMSCAPATarea(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/capa-tareas/{tarea_id}", response_model=QMSCAPATareaResponse)
async def actualizar_tarea_capa(
    tarea_id: int,
    data: QMSCAPATareaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCAPATarea, tarea_id)
    if not item:
        raise HTTPException(status_code=404, detail="Tarea CAPA no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


# ===========================================================================
# 9. RIESGOS
# ===========================================================================

@router.get("/riesgos", response_model=List[QMSRiesgoResponse])
async def listar_riesgos(
    prioridad: Optional[str] = None,
    estado: Optional[str] = None,
    proceso_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSRiesgo).where(QMSRiesgo.deleted_at.is_(None))
    if prioridad:
        q = q.where(QMSRiesgo.prioridad == prioridad)
    if estado:
        q = q.where(QMSRiesgo.estado == estado)
    if proceso_id is not None:
        q = q.where(QMSRiesgo.proceso_id == proceso_id)
    q = q.order_by(QMSRiesgo.nivel_riesgo.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/riesgos", response_model=QMSRiesgoResponse, status_code=201)
async def crear_riesgo(
    data: QMSRiesgoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    payload = data.model_dump()
    # Auto-calcular nivel_riesgo y prioridad
    nivel = payload.get("probabilidad", 1) * payload.get("impacto", 1)
    payload["nivel_riesgo"] = nivel
    payload["prioridad"] = _calcular_prioridad_riesgo(nivel)
    item = QMSRiesgo(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/riesgos/{riesgo_id}", response_model=QMSRiesgoResponse)
async def obtener_riesgo(
    riesgo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSRiesgo, riesgo_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Riesgo no encontrado")
    return item


@router.put("/riesgos/{riesgo_id}", response_model=QMSRiesgoResponse)
async def actualizar_riesgo(
    riesgo_id: int,
    data: QMSRiesgoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSRiesgo, riesgo_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Riesgo no encontrado")
    payload = data.model_dump(exclude_unset=True)
    # Recalcular nivel y prioridad si cambian probabilidad o impacto
    prob = payload.get("probabilidad", item.probabilidad)
    imp = payload.get("impacto", item.impacto)
    if "probabilidad" in payload or "impacto" in payload:
        nivel = prob * imp
        payload["nivel_riesgo"] = nivel
        payload["prioridad"] = _calcular_prioridad_riesgo(nivel)
    for k, v in payload.items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/riesgos/{riesgo_id}", status_code=204)
async def eliminar_riesgo(
    riesgo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSRiesgo, riesgo_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Riesgo no encontrado")
    item.deleted_at = datetime.utcnow()
    await db.commit()


# ===========================================================================
# 10. QUEJAS Y RECLAMOS
# ===========================================================================

@router.get("/quejas", response_model=List[QMSQuejaResponse])
async def listar_quejas(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    origen: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSQueja).where(QMSQueja.deleted_at.is_(None))
    if tipo:
        q = q.where(QMSQueja.tipo == tipo)
    if estado:
        q = q.where(QMSQueja.estado == estado)
    if origen:
        q = q.where(QMSQueja.origen == origen)
    q = q.order_by(QMSQueja.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/quejas", response_model=QMSQuejaResponse, status_code=201)
async def crear_queja(
    data: QMSQuejaCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # Auto-generar código QRE-YYYY-NNN
    result = await db.execute(select(func.count(QMSQueja.id)))
    n = (result.scalar() or 0) + 1
    codigo = f"QRE-{datetime.now().year}-{n:03d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    item = QMSQueja(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/quejas/{queja_id}", response_model=QMSQuejaResponse)
async def obtener_queja(
    queja_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSQueja, queja_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Queja no encontrada")
    return item


@router.put("/quejas/{queja_id}", response_model=QMSQuejaResponse)
async def actualizar_queja(
    queja_id: int,
    data: QMSQuejaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSQueja, queja_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Queja no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/quejas/{queja_id}", status_code=204)
async def eliminar_queja(
    queja_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSQueja, queja_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Queja no encontrada")
    item.deleted_at = datetime.utcnow()
    await db.commit()


# ===========================================================================
# 11. EVALUACION DE PROVEEDORES
# ===========================================================================

@router.get("/evaluaciones-proveedores", response_model=List[QMSEvaluacionProveedorResponse])
async def listar_evaluaciones_proveedores(
    proveedor_nit: Optional[str] = None,
    periodo: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSEvaluacionProveedor)
    if proveedor_nit:
        q = q.where(QMSEvaluacionProveedor.proveedor_nit == proveedor_nit)
    if periodo:
        q = q.where(QMSEvaluacionProveedor.periodo == periodo)
    q = q.order_by(QMSEvaluacionProveedor.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/evaluaciones-proveedores", response_model=QMSEvaluacionProveedorResponse, status_code=201)
async def crear_evaluacion_proveedor(
    data: QMSEvaluacionProveedorCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    payload = data.model_dump()
    # Auto-calcular puntaje_total promedio de 4 criterios
    calidad = payload.get("calidad", 0) or 0
    cumplimiento = payload.get("cumplimiento", 0) or 0
    servicio = payload.get("servicio", 0) or 0
    tiempos = payload.get("tiempos", 0) or 0
    puntaje_total = (calidad + cumplimiento + servicio + tiempos) / 4
    payload["puntaje_total"] = round(puntaje_total, 2)
    payload["clasificacion"] = _calcular_clasificacion_proveedor(puntaje_total)
    item = QMSEvaluacionProveedor(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/evaluaciones-proveedores/{eval_id}", response_model=QMSEvaluacionProveedorResponse)
async def actualizar_evaluacion_proveedor(
    eval_id: int,
    data: QMSEvaluacionProveedorUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSEvaluacionProveedor, eval_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evaluación de proveedor no encontrada")
    payload = data.model_dump(exclude_unset=True)
    # Recalcular puntaje si se actualizan criterios
    criterios = {"calidad", "cumplimiento", "servicio", "tiempos"}
    if criterios.intersection(payload.keys()):
        cal = payload.get("calidad", item.calidad) or 0
        cum = payload.get("cumplimiento", item.cumplimiento) or 0
        ser = payload.get("servicio", item.servicio) or 0
        tie = payload.get("tiempos", item.tiempos) or 0
        puntaje_total = (cal + cum + ser + tie) / 4
        payload["puntaje_total"] = round(puntaje_total, 2)
        payload["clasificacion"] = _calcular_clasificacion_proveedor(puntaje_total)
    for k, v in payload.items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/evaluaciones-proveedores/resumen")
async def resumen_evaluaciones_proveedores(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Resumen por proveedor con su última clasificación y puntaje."""
    # Subconsulta: última evaluación por proveedor_nit
    subq = (
        select(
            QMSEvaluacionProveedor.proveedor_nit,
            func.max(QMSEvaluacionProveedor.id).label("last_id"),
        )
        .group_by(QMSEvaluacionProveedor.proveedor_nit)
        .subquery()
    )
    stmt = select(QMSEvaluacionProveedor).join(
        subq,
        and_(
            QMSEvaluacionProveedor.proveedor_nit == subq.c.proveedor_nit,
            QMSEvaluacionProveedor.id == subq.c.last_id,
        ),
    )
    r = await db.execute(stmt)
    items = r.scalars().all()
    return [
        {
            "proveedor_nit": e.proveedor_nit,
            "ultima_clasificacion": e.clasificacion,
            "ultimo_puntaje": e.puntaje_total,
            "ultimo_periodo": e.periodo,
        }
        for e in items
    ]


# ===========================================================================
# 12. CAMBIOS
# ===========================================================================

@router.get("/cambios", response_model=List[QMSCambioResponse])
async def listar_cambios(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    proceso_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSCambio).where(QMSCambio.deleted_at.is_(None))
    if tipo:
        q = q.where(QMSCambio.tipo == tipo)
    if estado:
        q = q.where(QMSCambio.estado == estado)
    if proceso_id is not None:
        q = q.where(QMSCambio.proceso_id == proceso_id)
    q = q.order_by(QMSCambio.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/cambios", response_model=QMSCambioResponse, status_code=201)
async def crear_cambio(
    data: QMSCambioCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # Auto-generar código CHG-YYYY-NNN
    result = await db.execute(select(func.count(QMSCambio.id)))
    n = (result.scalar() or 0) + 1
    codigo = f"CHG-{datetime.now().year}-{n:03d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    item = QMSCambio(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/cambios/{cambio_id}", response_model=QMSCambioResponse)
async def obtener_cambio(
    cambio_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCambio, cambio_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Cambio no encontrado")
    return item


@router.put("/cambios/{cambio_id}", response_model=QMSCambioResponse)
async def actualizar_cambio(
    cambio_id: int,
    data: QMSCambioUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCambio, cambio_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Cambio no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/cambios/{cambio_id}", status_code=204)
async def eliminar_cambio(
    cambio_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCambio, cambio_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Cambio no encontrado")
    item.deleted_at = datetime.utcnow()
    await db.commit()


# ===========================================================================
# 13. MEJORA CONTINUA
# ===========================================================================

@router.get("/mejoras", response_model=List[QMSMejoraResponse])
async def listar_mejoras(
    estado: Optional[str] = None,
    proceso_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSMejora).where(QMSMejora.deleted_at.is_(None))
    if estado:
        q = q.where(QMSMejora.estado == estado)
    if proceso_id is not None:
        q = q.where(QMSMejora.proceso_id == proceso_id)
    q = q.order_by(QMSMejora.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/mejoras", response_model=QMSMejoraResponse, status_code=201)
async def crear_mejora(
    data: QMSMejoraCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # Auto-generar código MJR-YYYY-NNN
    result = await db.execute(select(func.count(QMSMejora.id)))
    n = (result.scalar() or 0) + 1
    codigo = f"MJR-{datetime.now().year}-{n:03d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    item = QMSMejora(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/mejoras/{mejora_id}", response_model=QMSMejoraResponse)
async def obtener_mejora(
    mejora_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSMejora, mejora_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Mejora no encontrada")
    return item


@router.put("/mejoras/{mejora_id}", response_model=QMSMejoraResponse)
async def actualizar_mejora(
    mejora_id: int,
    data: QMSMejoraUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSMejora, mejora_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Mejora no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/mejoras/{mejora_id}", status_code=204)
async def eliminar_mejora(
    mejora_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSMejora, mejora_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Mejora no encontrada")
    item.deleted_at = datetime.utcnow()
    await db.commit()


# ===========================================================================
# 14. ENCUESTAS
# ===========================================================================

@router.get("/encuestas", response_model=List[QMSEncuestaResponse])
async def listar_encuestas(
    tipo: Optional[str] = None,
    activa: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # `qms_encuesta` no lleva borrado suave: lo que tiene es la bandera
    # `activa`, que además significa otra cosa —si está recibiendo respuestas—.
    # Por eso aquí se listan todas y el filtro de `activa` lo pide quien llama.
    q = select(QMSEncuesta)
    if tipo:
        q = q.where(QMSEncuesta.tipo == tipo)
    if activa is not None:
        q = q.where(QMSEncuesta.activa == activa)
    q = q.order_by(QMSEncuesta.created_at.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/encuestas", response_model=QMSEncuestaResponse, status_code=201)
async def crear_encuesta(
    data: QMSEncuestaCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSEncuesta(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/encuestas/{enc_id}", response_model=QMSEncuestaResponse)
async def obtener_encuesta(
    enc_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSEncuesta, enc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")
    return item


@router.put("/encuestas/{enc_id}", response_model=QMSEncuestaResponse)
async def actualizar_encuesta(
    enc_id: int,
    data: QMSEncuestaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSEncuesta, enc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/encuestas/{enc_id}/respuestas", response_model=QMSEncuestaRespuestaResponse, status_code=201)
async def registrar_respuesta_encuesta(
    enc_id: int,
    data: QMSEncuestaRespuestaCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    enc = await db.get(QMSEncuesta, enc_id)
    if not enc:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")
    if not enc.activa:
        raise HTTPException(status_code=400, detail="La encuesta no está activa")
    payload = data.model_dump()
    payload["encuesta_id"] = enc_id
    if payload.get("nps_valor") is not None and not 0 <= payload["nps_valor"] <= 10:
        raise HTTPException(status_code=422, detail="El NPS va de 0 a 10")
    if payload.get("csat_valor") is not None and not 1 <= payload["csat_valor"] <= 5:
        raise HTTPException(status_code=422, detail="El CSAT va de 1 a 5")
    item = QMSEncuestaRespuesta(**payload)
    db.add(item)
    await db.flush()
    await _recalcular_encuesta(db, enc)
    await db.commit()
    await db.refresh(item)
    return item


async def _recalcular_encuesta(db: AsyncSession, enc: QMSEncuesta) -> None:
    """Total, NPS y CSAT de la encuesta, sacados de sus respuestas.

    Las tres columnas existían y nadie las escribía: la encuesta decía cero
    respuestas aunque las tuviera, y el NPS del tablero de calidad —que promedia
    `nps_score`— salía siempre en cero. Se recalculan desde las respuestas en
    vez de acumularse, así que no pueden desviarse de ellas.

    NPS es el estándar: % de promotores (9-10) menos % de detractores (0-6),
    sobre quienes contestaron esa pregunta. CSAT es el % de satisfechos (4-5).
    """
    r = await db.execute(
        select(
            func.count(QMSEncuestaRespuesta.id),
            func.count(QMSEncuestaRespuesta.nps_valor),
            func.count().filter(QMSEncuestaRespuesta.nps_valor >= 9),
            func.count().filter(QMSEncuestaRespuesta.nps_valor <= 6),
            func.count(QMSEncuestaRespuesta.csat_valor),
            func.count().filter(QMSEncuestaRespuesta.csat_valor >= 4),
        ).where(QMSEncuestaRespuesta.encuesta_id == enc.id))
    total, con_nps, promotores, detractores, con_csat, satisfechos = r.one()
    enc.total_respuestas = total
    enc.nps_score = (round((promotores - detractores) * 100.0 / con_nps, 2)
                     if con_nps else None)
    enc.csat_score = round(satisfechos * 100.0 / con_csat, 2) if con_csat else None


@router.get("/encuestas/{enc_id}/respuestas", response_model=List[QMSEncuestaRespuestaResponse])
async def listar_respuestas_encuesta(
    enc_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = (
        select(QMSEncuestaRespuesta)
        .where(QMSEncuestaRespuesta.encuesta_id == enc_id)
        .order_by(QMSEncuestaRespuesta.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    r = await db.execute(q)
    return r.scalars().all()


# ===========================================================================
# 15. COMPETENCIAS POR PROCESO
# ===========================================================================

@router.get("/competencias-proceso", response_model=List[QMSCompetenciaProcesoResponse])
async def listar_competencias_proceso(
    proceso_id: Optional[int] = None,
    cargo: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSCompetenciaProceso)
    if proceso_id is not None:
        q = q.where(QMSCompetenciaProceso.proceso_id == proceso_id)
    if cargo:
        q = q.where(QMSCompetenciaProceso.cargo == cargo)
    q = q.order_by(QMSCompetenciaProceso.id).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/competencias-proceso", response_model=QMSCompetenciaProcesoResponse, status_code=201)
async def crear_competencia_proceso(
    data: QMSCompetenciaProcesoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSCompetenciaProceso(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/competencias-proceso/{comp_id}", status_code=204)
async def eliminar_competencia_proceso(
    comp_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCompetenciaProceso, comp_id)
    if not item:
        raise HTTPException(status_code=404, detail="Competencia de proceso no encontrada")
    await db.delete(item)
    await db.commit()


# ===========================================================================
# 16. KPI DIARIO
# ===========================================================================

@router.get("/kpi-diario", response_model=List[QMSKPIDiarioResponse])
async def listar_kpi_diario(
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(QMSKPIDiario)
    if fecha_inicio:
        q = q.where(QMSKPIDiario.fecha >= fecha_inicio)
    if fecha_fin:
        q = q.where(QMSKPIDiario.fecha <= fecha_fin)
    q = q.order_by(QMSKPIDiario.fecha.desc()).offset(skip).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/kpi-diario/calcular", response_model=QMSKPIDiarioResponse, status_code=201)
async def calcular_kpi_diario(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Calcula y guarda el KPI del día actual basado en datos reales de BD."""
    hoy = date.today()

    # Verificar si ya existe KPI para hoy
    existing = await db.execute(
        select(QMSKPIDiario).where(QMSKPIDiario.fecha == hoy)
    )
    kpi_existente = existing.scalar_one_or_none()

    # NC abiertas
    r = await db.execute(
        select(func.count(QMSNoConformidad.id)).where(
            and_(
                QMSNoConformidad.deleted_at.is_(None),
                QMSNoConformidad.estado != "cerrada",
            )
        )
    )
    nc_abiertas = r.scalar() or 0

    # NC cerradas hoy
    r = await db.execute(
        select(func.count(QMSNoConformidad.id)).where(
            and_(
                QMSNoConformidad.deleted_at.is_(None),
                QMSNoConformidad.estado == "cerrada",
                func.date(QMSNoConformidad.fecha_cierre) == hoy,
            )
        )
    )
    nc_cerradas_hoy = r.scalar() or 0

    # CAPA abiertas
    r = await db.execute(
        select(func.count(QMSCAPA.id)).where(
            and_(
                QMSCAPA.deleted_at.is_(None),
                QMSCAPA.estado != "cerrada",
            )
        )
    )
    capa_abiertas = r.scalar() or 0

    # Riesgos activos totales
    r = await db.execute(
        select(func.count(QMSRiesgo.id)).where(
            and_(
                QMSRiesgo.deleted_at.is_(None),
                QMSRiesgo.estado == "activo",
            )
        )
    )
    riesgos_activos = r.scalar() or 0

    # Quejas abiertas
    r = await db.execute(
        select(func.count(QMSQueja.id)).where(
            and_(
                QMSQueja.deleted_at.is_(None),
                QMSQueja.estado != "cerrada",
            )
        )
    )
    quejas_abiertas = r.scalar() or 0

    # Indice calidad del día
    indice_calidad = round(max(0.0, 100.0 - (nc_abiertas * 2) - (riesgos_activos * 0.5)), 2)

    datos_kpi = {
        "fecha": hoy,
        "nc_abiertas": nc_abiertas,
        "nc_cerradas_hoy": nc_cerradas_hoy,
        "capa_abiertas": capa_abiertas,
        "riesgos_activos": riesgos_activos,
        "quejas_abiertas": quejas_abiertas,
        "indice_calidad": indice_calidad,
    }

    if kpi_existente:
        # Actualizar el existente
        for k, v in datos_kpi.items():
            setattr(kpi_existente, k, v)
        await db.commit()
        await db.refresh(kpi_existente)
        return kpi_existente
    else:
        item = QMSKPIDiario(**datos_kpi)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item


# ===========================================================================
# CERTIFICACIONES Y UMBRALES (configuración del módulo)
# ===========================================================================

# Días antes del vencimiento en que una certificación pasa a «por vencer». Una
# recertificación se agenda con meses de anticipación; noventa días es el
# margen que dan los organismos para programar la auditoría.
DIAS_POR_VENCER_CERTIFICACION = 90


class CertificacionIn(BaseModel):
    norma: str
    titulo: Optional[str] = None
    certificadora: Optional[str] = None
    numero_certificado: Optional[str] = None
    fecha_otorgamiento: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    alcance: Optional[str] = None
    en_implementacion: bool = False


def _estado_certificacion(c: QMSCertificacion, hoy: date) -> str:
    if c.en_implementacion:
        return "EN_IMPLEMENTACION"
    if c.fecha_vencimiento is None:
        return "VIGENTE"
    dias = (c.fecha_vencimiento.date() - hoy).days
    if dias < 0:
        return "VENCIDA"
    return "POR_VENCER" if dias <= DIAS_POR_VENCER_CERTIFICACION else "VIGENTE"


def _certificacion_dict(c: QMSCertificacion) -> dict:
    hoy = date.today()
    return {
        "id": c.id, "norma": c.norma, "titulo": c.titulo,
        "certificadora": c.certificadora, "numero_certificado": c.numero_certificado,
        "fecha_otorgamiento": c.fecha_otorgamiento.date().isoformat() if c.fecha_otorgamiento else None,
        "fecha_vencimiento": c.fecha_vencimiento.date().isoformat() if c.fecha_vencimiento else None,
        "alcance": c.alcance, "en_implementacion": bool(c.en_implementacion),
        "estado": _estado_certificacion(c, hoy),
        "dias_para_vencer": ((c.fecha_vencimiento.date() - hoy).days
                             if c.fecha_vencimiento and not c.en_implementacion else None),
    }


def _validar_certificacion(data: CertificacionIn) -> dict:
    if not data.norma.strip():
        raise HTTPException(status_code=422, detail="Falta la norma")
    if (data.fecha_otorgamiento and data.fecha_vencimiento
            and data.fecha_vencimiento < data.fecha_otorgamiento):
        raise HTTPException(status_code=422,
                            detail="La certificación no puede vencer antes de otorgarse")
    payload = data.model_dump()
    payload["norma"] = data.norma.strip()
    for campo in ("fecha_otorgamiento", "fecha_vencimiento"):
        v = payload[campo]
        payload[campo] = datetime(v.year, v.month, v.day) if v else None
    return payload


@router.get("/certificaciones")
async def listar_certificaciones(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    r = await db.execute(select(QMSCertificacion)
                         .where(QMSCertificacion.activo.is_(True))
                         .order_by(QMSCertificacion.norma))
    return [_certificacion_dict(c) for c in r.scalars().all()]


@router.post("/certificaciones", status_code=201)
async def crear_certificacion(
    data: CertificacionIn,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = QMSCertificacion(**_validar_certificacion(data))
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _certificacion_dict(item)


@router.put("/certificaciones/{cert_id}")
async def actualizar_certificacion(
    cert_id: int,
    data: CertificacionIn,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCertificacion, cert_id)
    if not item or not item.activo:
        raise HTTPException(status_code=404, detail="Certificación no encontrada")
    for k, v in _validar_certificacion(data).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return _certificacion_dict(item)


@router.delete("/certificaciones/{cert_id}", status_code=204)
async def eliminar_certificacion(
    cert_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = await db.get(QMSCertificacion, cert_id)
    if not item or not item.activo:
        raise HTTPException(status_code=404, detail="Certificación no encontrada")
    item.activo = False
    await db.commit()


# Los umbrales que existen, con su valor por defecto y su rango. Solo entran
# los que algo lee: el tablero de calidad arma sus alertas con los cuatro
# primeros y la evaluación de proveedores marca con el último.
PARAMETROS_QMS: Dict[str, dict] = {
    "capa_dias_aviso":          {"defecto": 7,  "min": 1, "max": 90,
                                 "descripcion": "Días antes del vencimiento para alertar una CAPA"},
    "auditoria_dias_aviso":     {"defecto": 15, "min": 1, "max": 120,
                                 "descripcion": "Días antes de una auditoría para recordarla"},
    "nc_mayor_dias_cierre":     {"defecto": 30, "min": 1, "max": 365,
                                 "descripcion": "Días máximos para cerrar una NC mayor o crítica"},
    "nc_menor_dias_cierre":     {"defecto": 60, "min": 1, "max": 365,
                                 "descripcion": "Días máximos para cerrar una NC menor"},
    "proveedor_puntaje_minimo": {"defecto": 60, "min": 0, "max": 100,
                                 "descripcion": "Puntaje por debajo del cual un proveedor queda en alerta"},
}


async def _leer_parametros(db: AsyncSession) -> Dict[str, float]:
    r = await db.execute(select(QMSParametro))
    guardados = {p.clave: float(p.valor) for p in r.scalars().all()}
    return {k: guardados.get(k, float(d["defecto"])) for k, d in PARAMETROS_QMS.items()}


@router.get("/parametros")
async def listar_parametros_qms(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    valores = await _leer_parametros(db)
    return [{"clave": k, "valor": valores[k], **d} for k, d in PARAMETROS_QMS.items()]


@router.put("/parametros")
async def guardar_parametros_qms(
    data: Dict[str, float],
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    desconocidos = set(data) - set(PARAMETROS_QMS)
    if desconocidos:
        raise HTTPException(status_code=422,
                            detail=f"Parámetro desconocido: {', '.join(sorted(desconocidos))}")
    for clave, valor in data.items():
        d = PARAMETROS_QMS[clave]
        if not d["min"] <= valor <= d["max"]:
            raise HTTPException(status_code=422,
                                detail=f"{d['descripcion']}: entre {d['min']} y {d['max']}")
    r = await db.execute(select(QMSParametro).where(QMSParametro.clave.in_(list(data))))
    existentes = {p.clave: p for p in r.scalars().all()}
    for clave, valor in data.items():
        if clave in existentes:
            existentes[clave].valor = valor
        else:
            db.add(QMSParametro(clave=clave, valor=valor))
    await db.commit()
    return await listar_parametros_qms(db, usuario)
