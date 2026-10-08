"""
API endpoints — TMS (Transportation Management System)
Prefijo: /tms
"""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, and_, or_, delete as sa_delete, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.tms import (
    TMSZona, TMSTipoServicio, TMSVehiculo, TMSViaje, TMSParada,
    TMSEvento, TMSDocumento, TMSPOD, TMSRuta, TMSPuntoRuta,
    TMSCostoViaje, TMSLiquidacion, TMSOTIFRegistro, TMSAlerta, TMSKPIDiario,
    EstadoVehiculoTMSEnum, EstadoViajeTMSEnum, EstadoLiquidacionTMSEnum,
    NivelAlertaTMSEnum, TipoEventoTMSEnum, TipoServicioTMSEnum, TMSParametro,
)
from app.application.schemas.tms import (
    TMSZonaCreate, TMSZonaUpdate, TMSZonaResponse,
    TMSTipoServicioCreate, TMSTipoServicioUpdate, TMSTipoServicioResponse,
    TMSVehiculoCreate, TMSVehiculoUpdate, TMSVehiculoResponse,
    TMSViajeCreate, TMSViajeUpdate, TMSViajeResponse, TMSViajeListResponse,
    TMSParadaCreate, TMSParadaUpdate, TMSParadaResponse,
    TMSEventoCreate, TMSEventoResponse,
    TMSDocumentoCreate, TMSDocumentoUpdate, TMSDocumentoResponse,
    TMSPODCreate, TMSPODResponse,
    TMSRutaCreate, TMSRutaUpdate, TMSRutaResponse,
    TMSPuntoRutaCreate, TMSPuntoRutaResponse,
    TMSCostoViajeCreate, TMSCostoViajeUpdate, TMSCostoViajeResponse,
    TMSLiquidacionCreate, TMSLiquidacionUpdate, TMSLiquidacionResponse,
    TMSOTIFRegistroCreate, TMSOTIFRegistroResponse,
    TMSAlertaCreate, TMSAlertaResponse,
    TMSDashboardKPIs,
)

router = APIRouter(prefix="/tms", tags=["tms"])


# ─── Utilidades internas ───────────────────────────────────────────────────────

def _ahora() -> datetime:
    """La hora actual CON zona horaria.

    Las columnas de fecha de TMS son `timezone=True` y lo que llega del
    formulario trae zona. Con `datetime.utcnow()` —sin zona— marcar un viaje
    como ENTREGADO respondía 500 en cuanto tenía fecha de entrega programada:
    Python no compara una fecha con zona contra otra sin ella, y la cuenta de
    puntualidad reventaba justo antes de guardar.
    """
    return datetime.now(timezone.utc)


def _calcular_costos(
    combustible: float,
    peajes: float,
    viaticos: float,
    horas_extras: float,
    mantenimiento: float,
    costos_indirectos: float,
    valor_flete_cobrado: float,
    distancia_km: Optional[float],
    num_entregas: Optional[int],
) -> dict:
    costo_total = combustible + peajes + viaticos + horas_extras + mantenimiento + costos_indirectos
    margen = valor_flete_cobrado - costo_total
    costo_por_km = costo_total / distancia_km if distancia_km and distancia_km > 0 else 0.0
    costo_por_entrega = costo_total / num_entregas if num_entregas and num_entregas > 0 else 0.0
    return {
        "costo_total": costo_total,
        "margen": margen,
        "costo_por_km": costo_por_km,
        "costo_por_entrega": costo_por_entrega,
    }


async def _viaje_to_response(db: AsyncSession, viaje: TMSViaje) -> TMSViajeResponse:
    """Construye TMSViajeResponse con campos calculados (placa, conductor)."""
    vehiculo_placa = None
    if viaje.vehiculo_id:
        veh = await db.get(TMSVehiculo, viaje.vehiculo_id)
        if veh:
            vehiculo_placa = veh.placa

    conductor_nombre = None
    if viaje.conductor_hcm_id:
        # El nombre está en el colaborador, no en el conductor: `HCMConductor`
        # solo guarda la licencia y la experiencia. Antes se buscaba
        # `cond.nombre_completo` con un getattr y un `except` que se lo tragaba
        # todo, así que la columna «Conductor» salía vacía en cada viaje y nadie
        # veía ningún error.
        from app.infrastructure.models.hcm import HCMColaborador, HCMConductor
        conductor_nombre = (await db.execute(
            select(HCMColaborador.nombres + " " + HCMColaborador.apellidos)
            .join(HCMConductor, HCMConductor.colaborador_id == HCMColaborador.id)
            .where(HCMConductor.id == viaje.conductor_hcm_id)
        )).scalar()
    if not conductor_nombre and viaje.conductor_legacy_id:
        try:
            from app.infrastructure.models.conductor import Conductor
            cond = await db.get(Conductor, viaje.conductor_legacy_id)
            if cond:
                conductor_nombre = getattr(cond, "nombre_completo", None) or getattr(cond, "nombre", None)
        except Exception:
            pass

    generador_nombre = None

    return TMSViajeResponse(
        id=viaje.id,
        codigo=viaje.codigo,
        tipo_servicio=viaje.tipo_servicio,
        estado=viaje.estado,
        vehiculo_id=viaje.vehiculo_id,
        vehiculo_placa=vehiculo_placa,
        conductor_hcm_id=viaje.conductor_hcm_id,
        conductor_nombre=conductor_nombre,
        conductor_legacy_id=viaje.conductor_legacy_id,
        empresa_id=viaje.empresa_id,
        generador_id=viaje.generador_id,
        generador_nombre=generador_nombre,
        flete_id=viaje.flete_id,
        wms_despacho_id=viaje.wms_despacho_id,
        origen_ciudad=viaje.origen_ciudad,
        destino_ciudad=viaje.destino_ciudad,
        origen_direccion=viaje.origen_direccion,
        destino_direccion=viaje.destino_direccion,
        fecha_programada_cargue=viaje.fecha_programada_cargue,
        fecha_real_cargue=viaje.fecha_real_cargue,
        fecha_programada_entrega=viaje.fecha_programada_entrega,
        fecha_real_entrega=viaje.fecha_real_entrega,
        distancia_km=viaje.distancia_km,
        peso_kg=viaje.peso_kg,
        volumen_m3=viaje.volumen_m3,
        num_entregas=viaje.num_entregas,
        valor_flete=viaje.valor_flete,
        otif_on_time=viaje.otif_on_time,
        otif_in_full=viaje.otif_in_full,
        descripcion_carga=viaje.descripcion_carga,
        notas=viaje.notas,
        created_at=viaje.created_at,
    )


# ─── DASHBOARD — KPIs ─────────────────────────────────────────────────────────

@router.get("/dashboard/kpis", response_model=TMSDashboardKPIs)
async def dashboard_kpis(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    hoy = date.today()
    inicio_mes = datetime(hoy.year, hoy.month, 1)

    # viajes_hoy
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            func.date(TMSViaje.fecha_programada_cargue) == hoy,
        )
    )
    viajes_hoy = r.scalar() or 0

    # viajes_en_transito
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.EN_TRANSITO,
        )
    )
    viajes_en_transito = r.scalar() or 0

    # viajes_completados_hoy
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado.in_([EstadoViajeTMSEnum.ENTREGADO,
                                 EstadoViajeTMSEnum.CERRADO]),
            func.date(TMSViaje.fecha_real_entrega) == hoy,
        )
    )
    viajes_completados_hoy = r.scalar() or 0

    # viajes_programados
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.PROGRAMADO,
        )
    )
    viajes_programados = r.scalar() or 0

    # vehiculos_activos (EN_VIAJE)
    r = await db.execute(
        select(func.count(TMSVehiculo.id)).where(
            TMSVehiculo.deleted_at.is_(None),
            TMSVehiculo.estado_operativo == EstadoVehiculoTMSEnum.EN_VIAJE,
        )
    )
    vehiculos_activos = r.scalar() or 0

    # vehiculos_disponibles
    r = await db.execute(
        select(func.count(TMSVehiculo.id)).where(
            TMSVehiculo.deleted_at.is_(None),
            TMSVehiculo.estado_operativo == EstadoVehiculoTMSEnum.DISPONIBLE,
        )
    )
    vehiculos_disponibles = r.scalar() or 0

    # conductores_activos (distinct conductor_hcm_id en viajes EN_TRANSITO)
    r = await db.execute(
        select(func.count(func.distinct(TMSViaje.conductor_hcm_id))).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.EN_TRANSITO,
            TMSViaje.conductor_hcm_id.isnot(None),
        )
    )
    conductores_hcm = r.scalar() or 0

    r2 = await db.execute(
        select(func.count(func.distinct(TMSViaje.conductor_legacy_id))).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.EN_TRANSITO,
            TMSViaje.conductor_legacy_id.isnot(None),
            TMSViaje.conductor_hcm_id.is_(None),
        )
    )
    conductores_legacy = r2.scalar() or 0
    conductores_activos = conductores_hcm + conductores_legacy

    # OTIF del mes (viajes ENTREGADOS este mes)
    r = await db.execute(
        select(
            func.count(TMSViaje.id),
            # `cast(..., type_=None)` produce un NullType y PostgreSQL no puede
            # compilarlo: el endpoint entero respondía 500 y el tablero mostraba
            # ceros, porque la pantalla cae a `?? 0` cuando la consulta falla.
            # Un cero se lee como «la operación va mal», no como «esto está roto».
            func.sum(
                func.cast(
                    and_(
                        TMSViaje.otif_on_time.is_(True),
                        TMSViaje.otif_in_full.is_(True),
                    ),
                    Integer,
                )
            ),
            func.sum(func.cast(TMSViaje.otif_on_time.is_(True), Integer)),
            func.sum(func.cast(TMSViaje.otif_in_full.is_(True), Integer)),
            # Cuántos se pueden juzgar: un viaje sin fecha prometida no es
            # «tarde», simplemente no entra en la puntualidad.
            func.count(TMSViaje.otif_on_time),
            func.count(TMSViaje.otif_in_full),
            func.count(TMSViaje.id).filter(TMSViaje.otif_on_time.isnot(None), TMSViaje.otif_in_full.isnot(None)),
        ).where(
            TMSViaje.deleted_at.is_(None),
            # ENTREGADO y CERRADO: cerrar un viaje es un trámite administrativo
            # posterior a la entrega, no la deshace. Contando solo ENTREGADO, el
            # OTIF del mes se derrumbaba a medida que se cerraban los viajes.
            TMSViaje.estado.in_([EstadoViajeTMSEnum.ENTREGADO,
                                 EstadoViajeTMSEnum.CERRADO]),
            TMSViaje.fecha_real_entrega >= inicio_mes,
        )
    )
    row = r.one()
    total_entregados_mes = row[0] or 0
    otif_count = int(row[1] or 0)
    on_time_count = int(row[2] or 0)
    in_full_count = int(row[3] or 0)

    base_ot, base_if, base_otif = int(row[4] or 0), int(row[5] or 0), int(row[6] or 0)
    otif_rate = round(otif_count / base_otif * 100, 2) if base_otif else 0.0
    on_time_rate = round(on_time_count / base_ot * 100, 2) if base_ot else 0.0
    in_full_rate = round(in_full_count / base_if * 100, 2) if base_if else 0.0

    # costo_promedio_km
    r = await db.execute(select(func.avg(TMSCostoViaje.costo_por_km)))
    costo_promedio_km = float(r.scalar() or 0.0)

    # km_recorridos_mes
    r = await db.execute(
        select(func.sum(TMSViaje.distancia_km)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado.in_([EstadoViajeTMSEnum.ENTREGADO,
                                 EstadoViajeTMSEnum.CERRADO]),
            TMSViaje.fecha_real_entrega >= inicio_mes,
        )
    )
    km_recorridos_mes = float(r.scalar() or 0.0)

    # alertas_criticas (CRITICA y no leída)
    r = await db.execute(
        select(func.count(TMSAlerta.id)).where(
            TMSAlerta.nivel == NivelAlertaTMSEnum.CRITICA,
            TMSAlerta.leida == False,
        )
    )
    alertas_criticas = r.scalar() or 0

    # alertas_activas (no leída)
    r = await db.execute(
        select(func.count(TMSAlerta.id)).where(TMSAlerta.leida == False)
    )
    alertas_activas = r.scalar() or 0

    return TMSDashboardKPIs(
        viajes_hoy=viajes_hoy,
        viajes_en_transito=viajes_en_transito,
        viajes_completados_hoy=viajes_completados_hoy,
        viajes_programados=viajes_programados,
        vehiculos_activos=vehiculos_activos,
        vehiculos_disponibles=vehiculos_disponibles,
        conductores_activos=conductores_activos,
        otif_rate=otif_rate,
        on_time_rate=on_time_rate,
        in_full_rate=in_full_rate,
        entregados_mes=total_entregados_mes,
        costo_promedio_km=costo_promedio_km,
        km_recorridos_mes=km_recorridos_mes,
        alertas_criticas=alertas_criticas,
        alertas_activas=alertas_activas,
    )


# ─── ALERTAS ──────────────────────────────────────────────────────────────────

@router.get("/alertas", response_model=List[TMSAlertaResponse])
async def listar_alertas(
    leida: Optional[bool] = None,
    nivel: Optional[str] = None,
    viaje_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(TMSAlerta)
    if leida is not None:
        q = q.where(TMSAlerta.leida == leida)
    if nivel:
        q = q.where(TMSAlerta.nivel == nivel)
    if viaje_id:
        q = q.where(TMSAlerta.viaje_id == viaje_id)
    q = q.order_by(TMSAlerta.fecha_alerta.desc()).limit(50)
    alertas = (await db.execute(q)).scalars().all()

    # El código del viaje y la placa, en dos consultas y no una por alerta.
    ids_viaje = {a.viaje_id for a in alertas if a.viaje_id}
    ids_vehiculo = {a.vehiculo_id for a in alertas if a.vehiculo_id}
    codigos = dict((await db.execute(
        select(TMSViaje.id, TMSViaje.codigo)
        .where(TMSViaje.id.in_(ids_viaje or {0})))).all())
    placas = dict((await db.execute(
        select(TMSVehiculo.id, TMSVehiculo.placa)
        .where(TMSVehiculo.id.in_(ids_vehiculo or {0})))).all())

    return [
        TMSAlertaResponse(
            id=a.id, tipo=a.tipo, nivel=a.nivel, mensaje=a.mensaje,
            viaje_id=a.viaje_id, viaje_codigo=codigos.get(a.viaje_id),
            vehiculo_id=a.vehiculo_id, vehiculo_placa=placas.get(a.vehiculo_id),
            conductor_id=a.conductor_id, leida=a.leida,
            fecha_alerta=a.fecha_alerta,
        )
        for a in alertas
    ]


@router.post("/alertas", response_model=TMSAlertaResponse, status_code=201)
async def crear_alerta(
    data: TMSAlertaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    alerta = TMSAlerta(**data.model_dump())
    db.add(alerta)
    await db.commit()
    await db.refresh(alerta)
    return alerta


@router.put("/alertas/{alerta_id}/leer")
async def marcar_alerta_leida(
    alerta_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    alerta = await db.get(TMSAlerta, alerta_id)
    if not alerta:
        raise HTTPException(404, "Alerta no encontrada")
    alerta.leida = True
    await db.commit()
    return {"mensaje": "Alerta marcada como leída"}


# ─── CONFIG — Zonas ───────────────────────────────────────────────────────────

@router.get("/config/zonas", response_model=List[TMSZonaResponse])
async def listar_zonas(
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(TMSZona)
    if activo is not None:
        q = q.where(TMSZona.activo == activo)
    r = await db.execute(q.order_by(TMSZona.nombre))
    return r.scalars().all()


@router.post("/config/zonas", response_model=TMSZonaResponse, status_code=201)
async def crear_zona(
    data: TMSZonaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    zona = TMSZona(**data.model_dump())
    db.add(zona)
    await db.commit()
    await db.refresh(zona)
    return zona


@router.put("/config/zonas/{zona_id}", response_model=TMSZonaResponse)
async def actualizar_zona(
    zona_id: int,
    data: TMSZonaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    zona = await db.get(TMSZona, zona_id)
    if not zona:
        raise HTTPException(404, "Zona no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(zona, k, v)
    await db.commit()
    await db.refresh(zona)
    return zona


@router.delete("/config/zonas/{zona_id}", status_code=204)
async def eliminar_zona(
    zona_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    zona = await db.get(TMSZona, zona_id)
    if not zona:
        raise HTTPException(404, "Zona no encontrada")
    await db.delete(zona)
    await db.commit()


def _ciudades(texto: Optional[str]) -> List[str]:
    """Las ciudades de una zona. Se guardaron de dos formas —separadas por
    barra o como lista JSON— y aquí se aceptan las dos."""
    if not texto:
        return []
    t = texto.strip()
    if t.startswith("["):
        import json
        try:
            return [str(c).strip() for c in json.loads(t) if str(c).strip()]
        except ValueError:
            pass
    return [c.strip() for c in t.replace(",", "|").split("|") if c.strip()]


def _clave_ciudad(c: str) -> str:
    import unicodedata
    c = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode()
    return " ".join(c.lower().replace("d.c.", "").replace(".", " ").split())


@router.get("/config/zonas-uso")
async def uso_zonas(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Cuántos viajes salen o llegan a cada zona, y qué ciudades con viajes no
    caen en ninguna. Se calcula cruzando las ciudades del viaje con las de la
    zona: los viajes no guardan zona, así que no hay otra forma honesta."""
    zonas = (await db.execute(select(TMSZona))).scalars().all()
    filas = (await db.execute(
        select(TMSViaje.origen_ciudad, TMSViaje.destino_ciudad)
        .where(TMSViaje.deleted_at.is_(None)))).all()
    de_zona = {z.id: {_clave_ciudad(c) for c in _ciudades(z.ciudades)} for z in zonas}
    cuenta = {z.id: 0 for z in zonas}
    sin_zona: dict = {}
    for o, d in filas:
        claves = {_clave_ciudad(c) for c in (o, d) if c}
        for zid, cs in de_zona.items():
            if claves & cs:
                cuenta[zid] += 1
        for c in (o, d):
            if c and not any(_clave_ciudad(c) in cs for cs in de_zona.values()):
                sin_zona[c.strip()] = sin_zona.get(c.strip(), 0) + 1
    return {
        "zonas": [{"zona_id": zid, "viajes": n} for zid, n in cuenta.items()],
        "ciudades_sin_zona": sorted(({"ciudad": c, "viajes": n} for c, n in sin_zona.items()),
                                    key=lambda x: -x["viajes"]),
    }


# ─── CONFIG — Parámetros ───────────────────────────────────────────────────────

# Solo entran los que algo lee. La pantalla tenía seis (horas de conducción,
# descanso, costo por km de referencia, empresa por defecto…) y ninguno lo
# consultaba nadie; la tolerancia de puntualidad sí decide el OTIF.
PARAMETROS_TMS = {
    "otif_tolerancia_min": {"defecto": 0, "min": 0, "max": 1440,
                            "descripcion": "Minutos de gracia sobre la hora programada para contar una entrega como puntual"},
    "capacidad_tolerancia_pct": {"defecto": 0, "min": 0, "max": 30,
                                 "descripcion": "Porcentaje que se permite cargar por encima de la capacidad del vehículo antes de bloquear la asignación"},
}


async def _leer_parametros_tms(db: AsyncSession) -> dict:
    guardados = {p.clave: p.valor for p in (await db.execute(select(TMSParametro))).scalars().all()}
    return {k: float(guardados.get(k, d["defecto"])) for k, d in PARAMETROS_TMS.items()}


async def _tolerancia_otif(db: AsyncSession) -> timedelta:
    return timedelta(minutes=(await _leer_parametros_tms(db))["otif_tolerancia_min"])


@router.get("/config/parametros")
async def listar_parametros_tms(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    valores = await _leer_parametros_tms(db)
    return [{"clave": k, "valor": valores[k], **d} for k, d in PARAMETROS_TMS.items()]


@router.put("/config/parametros")
async def guardar_parametros_tms(
    data: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    desconocidos = set(data) - set(PARAMETROS_TMS)
    if desconocidos:
        raise HTTPException(422, f"Parámetro desconocido: {', '.join(sorted(desconocidos))}")
    for clave, valor in data.items():
        d = PARAMETROS_TMS[clave]
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(422, f"{d['descripcion']}: debe ser un número")
        if not d["min"] <= valor <= d["max"]:
            raise HTTPException(422, f"{d['descripcion']}: entre {d['min']} y {d['max']}")
        fila = (await db.execute(select(TMSParametro).where(TMSParametro.clave == clave))).scalar_one_or_none()
        if fila:
            fila.valor = valor
        else:
            db.add(TMSParametro(clave=clave, valor=valor))
    await db.commit()
    return await listar_parametros_tms(db)


@router.get("/config/servicios-en-uso")
async def servicios_en_uso(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los tipos de servicio que el sistema reconoce, con cuántas rutas y
    viajes los usan. La lista la fija el sistema —viajes y rutas guardan uno de
    estos valores—; un tipo creado a mano en un catálogo aparte no lo podía
    escoger ningún formulario."""
    viajes = dict((await db.execute(
        select(TMSViaje.tipo_servicio, func.count()).where(TMSViaje.deleted_at.is_(None))
        .group_by(TMSViaje.tipo_servicio))).all())
    rutas = dict((await db.execute(
        select(TMSRuta.tipo_servicio, func.count()).group_by(TMSRuta.tipo_servicio))).all())
    return [{"tipo": t.value, "viajes": int(viajes.get(t, 0)), "rutas": int(rutas.get(t, 0))}
            for t in TipoServicioTMSEnum]


# ─── CONFIG — Tipos de Servicio ───────────────────────────────────────────────

@router.get("/config/tipos-servicio", response_model=List[TMSTipoServicioResponse])
async def listar_tipos_servicio(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    r = await db.execute(select(TMSTipoServicio).order_by(TMSTipoServicio.nombre))
    return r.scalars().all()


@router.post("/config/tipos-servicio", response_model=TMSTipoServicioResponse, status_code=201)
async def crear_tipo_servicio(
    data: TMSTipoServicioCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    ts = TMSTipoServicio(**data.model_dump())
    db.add(ts)
    await db.commit()
    await db.refresh(ts)
    return ts


@router.put("/config/tipos-servicio/{ts_id}", response_model=TMSTipoServicioResponse)
async def actualizar_tipo_servicio(
    ts_id: int,
    data: TMSTipoServicioUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    ts = await db.get(TMSTipoServicio, ts_id)
    if not ts:
        raise HTTPException(404, "Tipo de servicio no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ts, k, v)
    await db.commit()
    await db.refresh(ts)
    return ts


# ─── VEHÍCULOS ────────────────────────────────────────────────────────────────

@router.get("/vehiculos", response_model=List[TMSVehiculoResponse])
async def listar_vehiculos(
    estado_operativo: Optional[str] = None,
    tipo_vehiculo: Optional[str] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(TMSVehiculo).where(TMSVehiculo.deleted_at.is_(None))
    if estado_operativo:
        q = q.where(TMSVehiculo.estado_operativo == estado_operativo)
    if tipo_vehiculo:
        q = q.where(TMSVehiculo.tipo_vehiculo == tipo_vehiculo)
    r = await db.execute(q.order_by(TMSVehiculo.placa))
    vehiculos = r.scalars().all()

    resultado = []
    for veh in vehiculos:
        r2 = await db.execute(
            select(func.count(TMSViaje.id)).where(
                TMSViaje.deleted_at.is_(None),
                TMSViaje.vehiculo_id == veh.id,
                TMSViaje.estado == EstadoViajeTMSEnum.EN_TRANSITO,
            )
        )
        viajes_activos = r2.scalar() or 0
        resp = TMSVehiculoResponse.model_validate(veh)
        resp.viajes_activos = viajes_activos
        resultado.append(resp)

    return resultado


@router.post("/vehiculos", response_model=TMSVehiculoResponse, status_code=201)
async def crear_vehiculo(
    data: TMSVehiculoCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    veh = TMSVehiculo(**data.model_dump())
    db.add(veh)
    await db.commit()
    await db.refresh(veh)
    resp = TMSVehiculoResponse.model_validate(veh)
    resp.viajes_activos = 0
    return resp


@router.get("/vehiculos/{vehiculo_id}", response_model=TMSVehiculoResponse)
async def obtener_vehiculo(
    vehiculo_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    veh = await db.get(TMSVehiculo, vehiculo_id)
    if not veh or veh.deleted_at:
        raise HTTPException(404, "Vehículo no encontrado")
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.vehiculo_id == veh.id,
            TMSViaje.estado == EstadoViajeTMSEnum.EN_TRANSITO,
        )
    )
    viajes_activos = r.scalar() or 0
    resp = TMSVehiculoResponse.model_validate(veh)
    resp.viajes_activos = viajes_activos
    return resp


@router.put("/vehiculos/{vehiculo_id}", response_model=TMSVehiculoResponse)
async def actualizar_vehiculo(
    vehiculo_id: int,
    data: TMSVehiculoUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    veh = await db.get(TMSVehiculo, vehiculo_id)
    if not veh or veh.deleted_at:
        raise HTTPException(404, "Vehículo no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(veh, k, v)
    await db.commit()
    await db.refresh(veh)
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.vehiculo_id == veh.id,
            TMSViaje.estado == EstadoViajeTMSEnum.EN_TRANSITO,
        )
    )
    viajes_activos = r.scalar() or 0
    resp = TMSVehiculoResponse.model_validate(veh)
    resp.viajes_activos = viajes_activos
    return resp


@router.put("/vehiculos/{vehiculo_id}/estado")
async def actualizar_estado_vehiculo(
    vehiculo_id: int,
    estado_operativo: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    veh = await db.get(TMSVehiculo, vehiculo_id)
    if not veh or veh.deleted_at:
        raise HTTPException(404, "Vehículo no encontrado")
    veh.estado_operativo = estado_operativo
    await db.commit()
    return {"mensaje": "Estado actualizado"}


# ─── VIAJES ───────────────────────────────────────────────────────────────────

@router.get("/viajes", response_model=TMSViajeListResponse)
async def listar_viajes(
    estado: Optional[str] = None,
    empresa_id: Optional[int] = None,
    q: Optional[str] = Query(None, description="Buscar por código o ciudad"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(TMSViaje).where(TMSViaje.deleted_at.is_(None))
    if estado:
        stmt = stmt.where(TMSViaje.estado == estado)
    if empresa_id:
        stmt = stmt.where(TMSViaje.empresa_id == empresa_id)
    if q:
        stmt = stmt.where(
            or_(
                TMSViaje.codigo.ilike(f"%{q}%"),
                TMSViaje.origen_ciudad.ilike(f"%{q}%"),
                TMSViaje.destino_ciudad.ilike(f"%{q}%"),
            )
        )

    # Total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_r = await db.execute(count_stmt)
    total = total_r.scalar() or 0

    # Paginado
    stmt = stmt.order_by(TMSViaje.id.desc()).offset((page - 1) * per_page).limit(per_page)
    r = await db.execute(stmt)
    viajes = r.scalars().all()

    # Placas y conductores en dos consultas, no dos por viaje. Con la página de
    # cien viajes que permite el endpoint, lo anterior eran doscientos viajes a
    # la base para pintar una tabla.
    from app.infrastructure.models.hcm import HCMColaborador, HCMConductor
    ids_veh = {v.vehiculo_id for v in viajes if v.vehiculo_id}
    ids_cond = {v.conductor_hcm_id for v in viajes if v.conductor_hcm_id}
    placas = dict((await db.execute(
        select(TMSVehiculo.id, TMSVehiculo.placa)
        .where(TMSVehiculo.id.in_(ids_veh or {0})))).all())
    nombres = dict((await db.execute(
        select(HCMConductor.id,
               HCMColaborador.nombres + " " + HCMColaborador.apellidos)
        .join(HCMColaborador, HCMConductor.colaborador_id == HCMColaborador.id)
        .where(HCMConductor.id.in_(ids_cond or {0})))).all())

    items = [
        TMSViajeResponse(
            id=v.id, codigo=v.codigo, tipo_servicio=v.tipo_servicio,
            estado=v.estado, vehiculo_id=v.vehiculo_id,
            vehiculo_placa=placas.get(v.vehiculo_id),
            conductor_hcm_id=v.conductor_hcm_id,
            conductor_nombre=nombres.get(v.conductor_hcm_id),
            conductor_legacy_id=v.conductor_legacy_id, empresa_id=v.empresa_id,
            generador_id=v.generador_id, generador_nombre=None,
            flete_id=v.flete_id, wms_despacho_id=v.wms_despacho_id,
            origen_ciudad=v.origen_ciudad, destino_ciudad=v.destino_ciudad,
            fecha_programada_cargue=v.fecha_programada_cargue,
            fecha_real_cargue=v.fecha_real_cargue,
            fecha_programada_entrega=v.fecha_programada_entrega,
            fecha_real_entrega=v.fecha_real_entrega,
            distancia_km=v.distancia_km, peso_kg=v.peso_kg,
            num_entregas=v.num_entregas, valor_flete=v.valor_flete,
            otif_on_time=v.otif_on_time, otif_in_full=v.otif_in_full,
            descripcion_carga=v.descripcion_carga, notas=v.notas,
            created_at=v.created_at,
        )
        for v in viajes
    ]

    return TMSViajeListResponse(items=items, total=total, page=page, per_page=per_page)


@router.post("/viajes", response_model=TMSViajeResponse, status_code=201)
async def crear_viaje(
    data: TMSViajeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Generar código automático VJ-{YYYY}-{NNNNNN}
    anio = datetime.utcnow().year
    r = await db.execute(select(func.count(TMSViaje.id)))
    total = (r.scalar() or 0) + 1
    codigo = f"VJ-{anio}-{total:06d}"

    payload = data.model_dump()
    if payload.get("vehiculo_id"):
        from app.core import tms_capacidad
        veh = await db.get(TMSVehiculo, payload["vehiculo_id"])
        if not veh:
            raise HTTPException(404, "Vehículo no encontrado")
        await tms_capacidad.exigir(db, veh, payload.get("peso_kg"), payload.get("volumen_m3"))
    viaje = TMSViaje(**payload, codigo=codigo, creado_por_id=current_user.id)
    db.add(viaje)
    await db.commit()
    await db.refresh(viaje)
    return await _viaje_to_response(db, viaje)


@router.get("/viajes/{viaje_id}", response_model=TMSViajeResponse)
async def obtener_viaje(
    viaje_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    viaje = await db.get(TMSViaje, viaje_id)
    if not viaje or viaje.deleted_at:
        raise HTTPException(404, "Viaje no encontrado")
    return await _viaje_to_response(db, viaje)


@router.put("/viajes/{viaje_id}", response_model=TMSViajeResponse)
async def actualizar_viaje(
    viaje_id: int,
    data: TMSViajeUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    viaje = await db.get(TMSViaje, viaje_id)
    if not viaje or viaje.deleted_at:
        raise HTTPException(404, "Viaje no encontrado")
    cambios = data.model_dump(exclude_unset=True)
    for k, v in cambios.items():
        setattr(viaje, k, v)
    # Vehículo nuevo, o la carga cambió con vehículo puesto: se verifica la capacidad.
    if viaje.vehiculo_id and ({"vehiculo_id", "peso_kg", "volumen_m3"} & set(cambios)) and _val(viaje.estado) in (
            "PROGRAMADO", "ASIGNADO", "EN_TRANSITO"):
        from app.core import tms_capacidad
        veh = await db.get(TMSVehiculo, viaje.vehiculo_id)
        if not veh:
            raise HTTPException(404, "Vehículo no encontrado")
        await tms_capacidad.exigir(db, veh, viaje.peso_kg, viaje.volumen_m3, excluir_viaje_id=viaje.id)
    await db.commit()
    await db.refresh(viaje)
    return await _viaje_to_response(db, viaje)


@router.put("/viajes/{viaje_id}/estado")
async def actualizar_estado_viaje(
    viaje_id: int,
    estado: str = Query(...),
    notas: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    viaje = await db.get(TMSViaje, viaje_id)
    if not viaje or viaje.deleted_at:
        raise HTTPException(404, "Viaje no encontrado")

    estado_actual = viaje.estado.value if hasattr(viaje.estado, "value") else viaje.estado
    estado_nuevo = estado.upper()

    # Validar transiciones
    transiciones_validas = {
        "PROGRAMADO": ["ASIGNADO", "CANCELADO"],
        "ASIGNADO": ["EN_TRANSITO", "CANCELADO"],
        "EN_TRANSITO": ["ENTREGADO", "CANCELADO"],
        "ENTREGADO": ["CERRADO"],
        "CERRADO": [],
        "CANCELADO": [],
    }
    permitidos = transiciones_validas.get(estado_actual, [])
    if estado_nuevo not in permitidos:
        raise HTTPException(
            400,
            f"Transición no permitida: {estado_actual} → {estado_nuevo}. "
            f"Transiciones válidas: {permitidos}",
        )

    # Validaciones específicas de transición
    if estado_nuevo == "ASIGNADO":
        if not viaje.vehiculo_id or (not viaje.conductor_hcm_id and not viaje.conductor_legacy_id):
            raise HTTPException(400, "El viaje debe tener vehículo y conductor asignados para pasar a ASIGNADO")
        from app.core import tms_capacidad
        await tms_capacidad.exigir(db, await db.get(TMSVehiculo, viaje.vehiculo_id), viaje.peso_kg, viaje.volumen_m3,
                                   excluir_viaje_id=viaje.id)

    if estado_nuevo == "EN_TRANSITO":
        viaje.fecha_real_cargue = _ahora()

    if estado_nuevo == "ENTREGADO":
        viaje.fecha_real_entrega = _ahora()
        # Calcular OTIF
        if viaje.fecha_programada_entrega and viaje.fecha_real_entrega:
            viaje.otif_on_time = _a_tiempo(viaje, await _tolerancia_otif(db))
        else:
            viaje.otif_on_time = None
        if viaje.otif_in_full is None:
            viaje.otif_in_full = await _completo_segun_wms(db, viaje)

    viaje.estado = estado_nuevo
    if notas:
        viaje.notas = notas

    # Daily Logistics: el viaje que sale de un despacho del WMS mueve su estado.
    if viaje.wms_despacho_id and estado_nuevo in ("EN_TRANSITO", "ENTREGADO"):
        from app.core.marketplace.servicio import viaje_actualizado
        await viaje_actualizado(db, viaje.wms_despacho_id, estado_nuevo)

    await db.commit()
    await db.refresh(viaje)
    resp = await _viaje_to_response(db, viaje)
    return {"mensaje": "Estado actualizado", "viaje": resp}


@router.delete("/viajes/{viaje_id}", status_code=204)
async def eliminar_viaje(
    viaje_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    viaje = await db.get(TMSViaje, viaje_id)
    if not viaje or viaje.deleted_at:
        raise HTTPException(404, "Viaje no encontrado")
    viaje.deleted_at = _ahora()
    await db.commit()


# ─── PARADAS ──────────────────────────────────────────────────────────────────

@router.get("/viajes/{viaje_id}/paradas", response_model=List[TMSParadaResponse])
async def listar_paradas(
    viaje_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    r = await db.execute(
        select(TMSParada)
        .where(TMSParada.viaje_id == viaje_id)
        .order_by(TMSParada.secuencia)
    )
    return r.scalars().all()


@router.post("/paradas", response_model=TMSParadaResponse, status_code=201)
async def crear_parada(
    data: TMSParadaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    parada = TMSParada(**data.model_dump())
    db.add(parada)
    await db.commit()
    await db.refresh(parada)
    return parada


@router.put("/paradas/{parada_id}", response_model=TMSParadaResponse)
async def actualizar_parada(
    parada_id: int,
    data: TMSParadaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    parada = await db.get(TMSParada, parada_id)
    if not parada:
        raise HTTPException(404, "Parada no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(parada, k, v)
    await db.commit()
    await db.refresh(parada)
    return parada


@router.put("/paradas/{parada_id}/estado")
async def actualizar_estado_parada(
    parada_id: int,
    estado: str = Query(...),
    tiempo_real_llegada: Optional[datetime] = Query(None),
    tiempo_real_salida: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    parada = await db.get(TMSParada, parada_id)
    if not parada:
        raise HTTPException(404, "Parada no encontrada")
    parada.estado = estado
    if tiempo_real_llegada:
        parada.tiempo_real_llegada = tiempo_real_llegada
    if tiempo_real_salida:
        parada.tiempo_real_salida = tiempo_real_salida
    await db.commit()
    return {"mensaje": "Estado de parada actualizado"}


@router.delete("/paradas/{parada_id}", status_code=204)
async def eliminar_parada(
    parada_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    parada = await db.get(TMSParada, parada_id)
    if not parada:
        raise HTTPException(404, "Parada no encontrada")
    await db.delete(parada)
    await db.commit()


# ─── EVENTOS (Tracking) ───────────────────────────────────────────────────────

@router.get("/viajes/{viaje_id}/eventos", response_model=List[TMSEventoResponse])
async def listar_eventos(
    viaje_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    r = await db.execute(
        select(TMSEvento)
        .where(TMSEvento.viaje_id == viaje_id)
        .order_by(TMSEvento.timestamp.desc())
    )
    return r.scalars().all()


@router.post("/eventos", response_model=TMSEventoResponse, status_code=201)
async def crear_evento(
    data: TMSEventoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    evento = TMSEvento(**data.model_dump(), registrado_por_id=current_user.id)
    db.add(evento)
    await db.flush()

    # Si el evento es LLEGADA_DESTINO, actualizar estado del viaje si aplica
    if data.tipo_evento == TipoEventoTMSEnum.LLEGADA_DESTINO:
        viaje = await db.get(TMSViaje, data.viaje_id)
        if viaje and viaje.estado == EstadoViajeTMSEnum.EN_TRANSITO:
            viaje.estado = EstadoViajeTMSEnum.ENTREGADO
            viaje.fecha_real_entrega = _ahora()
            if viaje.fecha_programada_entrega and viaje.fecha_real_entrega:
                viaje.otif_on_time = _a_tiempo(viaje, await _tolerancia_otif(db))

    await db.commit()
    await db.refresh(evento)
    return evento


# ─── DOCUMENTOS ───────────────────────────────────────────────────────────────

@router.get("/viajes/{viaje_id}/documentos", response_model=List[TMSDocumentoResponse])
async def listar_documentos(
    viaje_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    r = await db.execute(
        select(TMSDocumento)
        .where(TMSDocumento.viaje_id == viaje_id)
        .order_by(TMSDocumento.id)
    )
    return r.scalars().all()


@router.post("/documentos", response_model=TMSDocumentoResponse, status_code=201)
async def crear_documento(
    data: TMSDocumentoCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    doc = TMSDocumento(**data.model_dump())
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.put("/documentos/{doc_id}", response_model=TMSDocumentoResponse)
async def actualizar_documento(
    doc_id: int,
    data: TMSDocumentoUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    doc = await db.get(TMSDocumento, doc_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(doc, k, v)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/documentos/{doc_id}", status_code=204)
async def eliminar_documento(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    doc = await db.get(TMSDocumento, doc_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    await db.delete(doc)
    await db.commit()


# ─── POD ──────────────────────────────────────────────────────────────────────

@router.get("/viajes/{viaje_id}/pod", response_model=TMSPODResponse)
async def obtener_pod(
    viaje_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    r = await db.execute(select(TMSPOD).where(TMSPOD.viaje_id == viaje_id))
    pod = r.scalar_one_or_none()
    if not pod:
        raise HTTPException(404, "POD no encontrado para este viaje")
    return pod


@router.post("/pod", response_model=TMSPODResponse, status_code=201)
async def crear_pod(
    data: TMSPODCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Verificar que no exista ya un POD para este viaje
    r = await db.execute(select(TMSPOD).where(TMSPOD.viaje_id == data.viaje_id))
    existente = r.scalar_one_or_none()
    if existente:
        raise HTTPException(409, "Ya existe un POD para este viaje")

    pod = TMSPOD(**data.model_dump(), registrado_por_id=current_user.id)
    db.add(pod)
    await db.commit()
    await db.refresh(pod)
    return pod


# ─── RUTAS ────────────────────────────────────────────────────────────────────

@router.get("/rutas", response_model=List[TMSRutaResponse])
async def listar_rutas(
    activo: Optional[bool] = None,
    origen: Optional[str] = None,
    destino: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(TMSRuta)
    if activo is not None:
        q = q.where(TMSRuta.activo == activo)
    if origen:
        q = q.where(TMSRuta.origen.ilike(f"%{origen}%"))
    if destino:
        q = q.where(TMSRuta.destino.ilike(f"%{destino}%"))
    r = await db.execute(q.order_by(TMSRuta.nombre))
    return r.scalars().all()


@router.post("/rutas", response_model=TMSRutaResponse, status_code=201)
async def crear_ruta(
    data: TMSRutaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    ruta = TMSRuta(**data.model_dump())
    db.add(ruta)
    await db.commit()
    await db.refresh(ruta)
    return ruta


@router.put("/rutas/{ruta_id}", response_model=TMSRutaResponse)
async def actualizar_ruta(
    ruta_id: int,
    data: TMSRutaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    ruta = await db.get(TMSRuta, ruta_id)
    if not ruta:
        raise HTTPException(404, "Ruta no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ruta, k, v)
    await db.commit()
    await db.refresh(ruta)
    return ruta


@router.get("/rutas/{ruta_id}/puntos", response_model=List[TMSPuntoRutaResponse])
async def listar_puntos_ruta(
    ruta_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    r = await db.execute(
        select(TMSPuntoRuta)
        .where(TMSPuntoRuta.ruta_id == ruta_id)
        .order_by(TMSPuntoRuta.secuencia)
    )
    return r.scalars().all()


@router.post("/rutas/{ruta_id}/puntos", response_model=TMSPuntoRutaResponse, status_code=201)
async def crear_punto_ruta(
    ruta_id: int,
    data: TMSPuntoRutaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    punto = TMSPuntoRuta(**data.model_dump(exclude={"ruta_id"}), ruta_id=ruta_id)
    db.add(punto)
    await db.commit()
    await db.refresh(punto)
    return punto


@router.delete("/rutas/{ruta_id}/puntos", status_code=204)
async def eliminar_puntos_ruta(
    ruta_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await db.execute(sa_delete(TMSPuntoRuta).where(TMSPuntoRuta.ruta_id == ruta_id))
    await db.commit()


# ─── COSTOS ───────────────────────────────────────────────────────────────────

@router.get("/viajes/{viaje_id}/costos", response_model=TMSCostoViajeResponse)
async def obtener_costos(
    viaje_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    r = await db.execute(select(TMSCostoViaje).where(TMSCostoViaje.viaje_id == viaje_id))
    costo = r.scalar_one_or_none()
    if not costo:
        raise HTTPException(404, "Costos no encontrados para este viaje")
    return costo


@router.post("/costos", response_model=TMSCostoViajeResponse, status_code=201)
async def crear_costos(
    data: TMSCostoViajeCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Verificar que no exista ya un registro de costos para este viaje
    r = await db.execute(select(TMSCostoViaje).where(TMSCostoViaje.viaje_id == data.viaje_id))
    if r.scalar_one_or_none():
        raise HTTPException(409, "Ya existen costos registrados para este viaje")

    # Obtener distancia y num_entregas del viaje
    viaje = await db.get(TMSViaje, data.viaje_id)
    distancia_km = viaje.distancia_km if viaje else None
    num_entregas = viaje.num_entregas if viaje else None

    calculos = _calcular_costos(
        combustible=data.combustible,
        peajes=data.peajes,
        viaticos=data.viaticos,
        horas_extras=data.horas_extras,
        mantenimiento=data.mantenimiento,
        costos_indirectos=data.costos_indirectos,
        valor_flete_cobrado=data.valor_flete_cobrado,
        distancia_km=distancia_km,
        num_entregas=num_entregas,
    )

    costo = TMSCostoViaje(
        **data.model_dump(),
        **calculos,
    )
    db.add(costo)
    await db.commit()
    await db.refresh(costo)
    return costo


@router.put("/costos/{costo_id}", response_model=TMSCostoViajeResponse)
async def actualizar_costos(
    costo_id: int,
    data: TMSCostoViajeUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    costo = await db.get(TMSCostoViaje, costo_id)
    if not costo:
        raise HTTPException(404, "Registro de costos no encontrado")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(costo, k, v)

    # Obtener distancia y num_entregas del viaje
    viaje = await db.get(TMSViaje, costo.viaje_id)
    distancia_km = viaje.distancia_km if viaje else None
    num_entregas = viaje.num_entregas if viaje else None

    calculos = _calcular_costos(
        combustible=costo.combustible,
        peajes=costo.peajes,
        viaticos=costo.viaticos,
        horas_extras=costo.horas_extras,
        mantenimiento=costo.mantenimiento,
        costos_indirectos=costo.costos_indirectos,
        valor_flete_cobrado=costo.valor_flete_cobrado,
        distancia_km=distancia_km,
        num_entregas=num_entregas,
    )
    for k, v in calculos.items():
        setattr(costo, k, v)

    await db.commit()
    await db.refresh(costo)
    return costo


# ─── LIQUIDACIONES ────────────────────────────────────────────────────────────

@router.get("/liquidaciones/resumen")
async def resumen_liquidaciones(
    conductor_hcm_id: Optional[int] = None,
    periodo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los totales por estado, contados en la base.

    Existe porque la pantalla sumaba los totales recorriendo la lista completa
    en el navegador. Eso obliga a bajarla entera —un año son 2.800 liquidaciones
    y casi un megabyte— y, peor, hace que cualquier tope que se le ponga a la
    lista rompa los totales sin que nadie lo note: seguirían apareciendo, solo
    que mal. Con el resumen aparte, la lista se puede paginar tranquila.
    """
    filtros = []
    if conductor_hcm_id:
        filtros.append(TMSLiquidacion.conductor_hcm_id == conductor_hcm_id)
    if periodo:
        filtros.append(TMSLiquidacion.periodo == periodo)

    filas = (await db.execute(
        select(TMSLiquidacion.estado,
               func.count(TMSLiquidacion.id),
               func.coalesce(func.sum(TMSLiquidacion.total_a_pagar), 0))
        .where(*filtros)
        .group_by(TMSLiquidacion.estado)
    )).all()

    por_estado = {
        (e.value if hasattr(e, "value") else str(e)): {"cantidad": n, "total": float(t)}
        for e, n, t in filas
    }
    pendientes = ("BORRADOR", "PENDIENTE", "APROBADA")
    return {
        "por_estado": por_estado,
        "cantidad_total": sum(v["cantidad"] for v in por_estado.values()),
        "total_pendiente": sum(v["total"] for k, v in por_estado.items()
                               if k in pendientes),
        "total_pagado": por_estado.get("PAGADA", {}).get("total", 0.0),
        "en_proceso": por_estado.get("PENDIENTE", {}).get("cantidad", 0),
        "por_liquidar": sum(v["cantidad"] for k, v in por_estado.items()
                            if k in ("BORRADOR", "PENDIENTE")),
    }


@router.get("/liquidaciones", response_model=List[TMSLiquidacionResponse])
async def listar_liquidaciones(
    respuesta: Response,
    estado: Optional[str] = None,
    conductor_hcm_id: Optional[int] = None,
    periodo: Optional[str] = None,
    limite: int = Query(200, ge=1, le=2000),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(TMSLiquidacion)
    if estado:
        q = q.where(TMSLiquidacion.estado == estado)
    if conductor_hcm_id:
        q = q.where(TMSLiquidacion.conductor_hcm_id == conductor_hcm_id)
    if periodo:
        q = q.where(TMSLiquidacion.periodo == periodo)

    # El total va en la cabecera y no en el cuerpo para no cambiarle la forma a
    # la respuesta, que ya está publicada como una lista.
    total = (await db.execute(
        select(func.count()).select_from(q.subquery()))).scalar() or 0
    respuesta.headers["X-Total-Count"] = str(total)
    respuesta.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    r = await db.execute(
        q.order_by(TMSLiquidacion.id.desc())
        .offset(desplazamiento).limit(limite))
    return r.scalars().all()


@router.post("/liquidaciones", response_model=TMSLiquidacionResponse, status_code=201)
async def crear_liquidacion(
    data: TMSLiquidacionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    total_a_pagar = data.valor_flete + data.bonificaciones - data.descuentos - data.anticipos
    liq = TMSLiquidacion(**data.model_dump(), total_a_pagar=total_a_pagar)
    db.add(liq)
    await db.commit()
    await db.refresh(liq)
    return liq


@router.put("/liquidaciones/{liq_id}", response_model=TMSLiquidacionResponse)
async def actualizar_liquidacion(
    liq_id: int,
    data: TMSLiquidacionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    liq = await db.get(TMSLiquidacion, liq_id)
    if not liq:
        raise HTTPException(404, "Liquidación no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(liq, k, v)
    # Recalcular total
    liq.total_a_pagar = liq.valor_flete + liq.bonificaciones - liq.descuentos - liq.anticipos
    await db.commit()
    await db.refresh(liq)
    return liq


@router.post("/liquidaciones/{liq_id}/aprobar")
async def aprobar_liquidacion(
    liq_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    liq = await db.get(TMSLiquidacion, liq_id)
    if not liq:
        raise HTTPException(404, "Liquidación no encontrada")
    liq.estado = EstadoLiquidacionTMSEnum.APROBADA
    liq.aprobado_por_id = current_user.id
    await db.commit()
    return {"mensaje": "Liquidación aprobada"}


@router.post("/liquidaciones/{liq_id}/pagar")
async def pagar_liquidacion(
    liq_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    liq = await db.get(TMSLiquidacion, liq_id)
    if not liq:
        raise HTTPException(404, "Liquidación no encontrada")
    liq.estado = EstadoLiquidacionTMSEnum.PAGADA
    liq.pagado_en = _ahora()
    await db.commit()
    return {"mensaje": "Liquidación marcada como pagada"}


# ─── OTIF ─────────────────────────────────────────────────────────────────────

@router.get("/otif", response_model=List[TMSOTIFRegistroResponse])
async def listar_otif(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    cliente: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(TMSOTIFRegistro)
    if fecha_desde:
        q = q.where(TMSOTIFRegistro.fecha >= fecha_desde)
    if fecha_hasta:
        q = q.where(TMSOTIFRegistro.fecha <= fecha_hasta)
    if cliente:
        q = q.where(TMSOTIFRegistro.cliente.ilike(f"%{cliente}%"))
    r = await db.execute(q.order_by(TMSOTIFRegistro.fecha.desc()))
    return r.scalars().all()


@router.post("/otif", response_model=TMSOTIFRegistroResponse, status_code=201)
async def crear_otif(
    data: TMSOTIFRegistroCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Verificar que no exista ya un registro OTIF para este viaje
    r = await db.execute(select(TMSOTIFRegistro).where(TMSOTIFRegistro.viaje_id == data.viaje_id))
    if r.scalar_one_or_none():
        raise HTTPException(409, "Ya existe un registro OTIF para este viaje")

    otif = data.on_time and data.in_full
    registro = TMSOTIFRegistro(**data.model_dump(), otif=otif)
    db.add(registro)
    await db.commit()
    await db.refresh(registro)
    return registro


@router.get("/otif/resumen")
async def resumen_otif(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Tasas OTIF del período, calculadas sobre los viajes entregados.

    Antes se contaba sobre `tms_otif_registro`, una tabla que nadie llenaba, y
    con `cast(..., type_=None)`, que PostgreSQL no sabe compilar: la ruta
    respondía 500. Ahora sale de la misma fuente que la lista por viaje, así
    que el resumen y el detalle no pueden contradecirse.

    Las tasas se calculan sobre lo que se sabe: un viaje sin confirmar si
    llegó completo no entra al denominador del in-full.
    """
    filas = await otif_por_viaje(fecha_desde, fecha_hasta, db, _)
    total = len(filas)
    con_ot = [f for f in filas if f["on_time"] is not None]
    con_if = [f for f in filas if f["in_full"] is not None]
    con_otif = [f for f in filas if f["otif"] is not None]
    tasa = lambda xs, k: round(sum(1 for f in xs if f[k]) / len(xs) * 100, 2) if xs else 0.0
    return {
        "on_time_rate": tasa(con_ot, "on_time"),
        "in_full_rate": tasa(con_if, "in_full"),
        "otif_rate": tasa(con_otif, "otif"),
        "total": total,
        "sin_confirmar_in_full": total - len(con_if),
    }


# ─── KPIs DIARIOS ─────────────────────────────────────────────────────────────

@router.get("/kpis/serie")
async def serie_kpis(
    dias: int = Query(14, ge=2, le=180),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """La serie de los últimos días, para las minigráficas de la torre.

    Existe porque la torre de control dibujaba sus tendencias con una lista de
    números escrita en el código: la misma curva para todos los clientes y para
    todos los días. Una tendencia inventada es peor que no tener tendencia,
    porque invita a decidir sobre ella.

    Se devuelven los días que existen, sin rellenar los faltantes: un día sin
    operación no es un día con cero OTIF, y dibujarlo como cero hundiría la curva
    cada fin de semana.
    """
    desde = date.today() - timedelta(days=dias)
    filas = (await db.execute(
        select(TMSKPIDiario)
        .where(TMSKPIDiario.fecha >= desde)
        .order_by(TMSKPIDiario.fecha.asc())
    )).scalars().all()
    return [{
        "fecha": f.fecha.isoformat(),
        "viajes_programados": f.viajes_programados,
        "viajes_completados": f.viajes_completados,
        "otif_rate": round(float(f.otif_rate or 0), 2),
        "on_time_rate": round(float(f.on_time_rate or 0), 2),
        "costo_promedio_km": round(float(f.costo_promedio_km or 0), 2),
        "km_recorridos": round(float(f.km_recorridos or 0), 1),
        "km_vacios": round(float(f.km_vacios or 0), 1),
        "utilizacion_flota": round(float(f.utilizacion_flota or 0), 2),
    } for f in filas]


@router.post("/kpis/calcular")
async def calcular_kpis_diarios(
    empresa_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    hoy = date.today()
    inicio_hoy = datetime(hoy.year, hoy.month, hoy.day)
    inicio_mes = datetime(hoy.year, hoy.month, 1)

    # Viajes programados hoy
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            func.date(TMSViaje.fecha_programada_cargue) == hoy,
            *([TMSViaje.empresa_id == empresa_id] if empresa_id else []),
        )
    )
    viajes_programados = r.scalar() or 0

    # Viajes completados hoy
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.ENTREGADO,
            func.date(TMSViaje.fecha_real_entrega) == hoy,
            *([TMSViaje.empresa_id == empresa_id] if empresa_id else []),
        )
    )
    viajes_completados = r.scalar() or 0

    # Viajes cancelados hoy
    r = await db.execute(
        select(func.count(TMSViaje.id)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.CANCELADO,
            func.date(TMSViaje.created_at) == hoy,
            *([TMSViaje.empresa_id == empresa_id] if empresa_id else []),
        )
    )
    viajes_cancelados = r.scalar() or 0

    # OTIF del mes
    r = await db.execute(
        select(
            func.count(TMSViaje.id),
            func.sum(func.cast(TMSViaje.otif_on_time.is_(True), Integer)),
            func.sum(func.cast(TMSViaje.otif_in_full.is_(True), Integer)),
            func.sum(
                func.cast(
                    and_(TMSViaje.otif_on_time.is_(True), TMSViaje.otif_in_full.is_(True)),
                    Integer,
                )
            ),
        ).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.ENTREGADO,
            TMSViaje.fecha_real_entrega >= inicio_mes,
            *([TMSViaje.empresa_id == empresa_id] if empresa_id else []),
        )
    )
    row = r.one()
    total_ent = row[0] or 0
    on_time_rate = round(int(row[1] or 0) / total_ent * 100, 2) if total_ent else 0.0
    in_full_rate = round(int(row[2] or 0) / total_ent * 100, 2) if total_ent else 0.0
    otif_rate = round(int(row[3] or 0) / total_ent * 100, 2) if total_ent else 0.0

    # KM recorridos y costo promedio km
    r = await db.execute(
        select(func.sum(TMSViaje.distancia_km)).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.ENTREGADO,
            func.date(TMSViaje.fecha_real_entrega) == hoy,
            *([TMSViaje.empresa_id == empresa_id] if empresa_id else []),
        )
    )
    km_recorridos = float(r.scalar() or 0.0)

    r = await db.execute(select(func.avg(TMSCostoViaje.costo_por_km)))
    costo_promedio_km = float(r.scalar() or 0.0)

    # Conductores activos hoy
    r = await db.execute(
        select(func.count(func.distinct(TMSViaje.conductor_hcm_id))).where(
            TMSViaje.deleted_at.is_(None),
            TMSViaje.estado == EstadoViajeTMSEnum.EN_TRANSITO,
            TMSViaje.conductor_hcm_id.isnot(None),
            *([TMSViaje.empresa_id == empresa_id] if empresa_id else []),
        )
    )
    conductores_activos = r.scalar() or 0

    # Upsert TMSKPIDiario
    r = await db.execute(
        select(TMSKPIDiario).where(
            TMSKPIDiario.fecha == hoy,
            *([TMSKPIDiario.empresa_id == empresa_id] if empresa_id else [TMSKPIDiario.empresa_id.is_(None)]),
        )
    )
    kpi = r.scalar_one_or_none()

    if kpi is None:
        kpi = TMSKPIDiario(
            empresa_id=empresa_id,
            fecha=hoy,
        )
        db.add(kpi)

    kpi.viajes_programados = viajes_programados
    kpi.viajes_completados = viajes_completados
    kpi.viajes_cancelados = viajes_cancelados
    kpi.on_time_rate = on_time_rate
    kpi.in_full_rate = in_full_rate
    kpi.otif_rate = otif_rate
    kpi.costo_promedio_km = costo_promedio_km
    kpi.km_recorridos = km_recorridos
    kpi.conductores_activos = conductores_activos

    await db.commit()
    return {"mensaje": "KPIs calculados"}


# ═════════════════════════════════════════════════════════════════════════════
# VISTAS DE CONJUNTO: costos, OTIF, planeación y documentos pendientes
#
# Las pantallas de Costos, OTIF, Planeación y Documentos eran maqueta. Lo que
# les faltaba del servidor no era el dato —ya estaba en los viajes— sino verlo
# junto: cada ruta existente respondía por UN viaje, y armar una tabla así
# costaba una consulta por fila.
# ═════════════════════════════════════════════════════════════════════════════

_ESTADOS_ENTREGADOS = [EstadoViajeTMSEnum.ENTREGADO, EstadoViajeTMSEnum.CERRADO]


def _val(x):
    return x.value if hasattr(x, "value") else x


async def _nombres_conductores(db: AsyncSession, viajes: List[TMSViaje]) -> dict:
    """Nombre del conductor de cada viaje, en UNA consulta y no en una por fila."""
    ids = {v.conductor_hcm_id for v in viajes if v.conductor_hcm_id}
    if not ids:
        return {}
    from app.infrastructure.models.hcm import HCMColaborador, HCMConductor
    r = await db.execute(
        select(HCMConductor.id, HCMColaborador.nombres + " " + HCMColaborador.apellidos)
        .join(HCMColaborador, HCMConductor.colaborador_id == HCMColaborador.id)
        .where(HCMConductor.id.in_(ids)))
    return dict(r.all())


async def _nombres_clientes(db: AsyncSession, viajes: List[TMSViaje]) -> dict:
    ids = {v.generador_id for v in viajes if v.generador_id}
    if not ids:
        return {}
    from app.infrastructure.models.flete import GeneradorCarga
    r = await db.execute(select(GeneradorCarga.id, GeneradorCarga.nombre)
                         .where(GeneradorCarga.id.in_(ids)))
    return dict(r.all())


# ─── Costos de todos los viajes ───────────────────────────────────────────────

@router.get("/costos")
async def listar_costos(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Cada viaje no cancelado con su desglose de costos, si lo tiene.

    El total, el margen y el costo por kilómetro se calculan aquí con la
    distancia ACTUAL del viaje. La tabla de costos también los guarda, pero
    fijados el día que se registraron: si después se corrige la distancia, el
    costo por kilómetro guardado miente.
    """
    q = (select(TMSViaje, TMSCostoViaje)
         .outerjoin(TMSCostoViaje, TMSCostoViaje.viaje_id == TMSViaje.id)
         .where(TMSViaje.deleted_at.is_(None),
                TMSViaje.estado != EstadoViajeTMSEnum.CANCELADO))
    fecha = func.coalesce(TMSViaje.fecha_real_entrega, TMSViaje.fecha_programada_cargue,
                          TMSViaje.created_at)
    if fecha_desde:
        q = q.where(fecha >= datetime(fecha_desde.year, fecha_desde.month, fecha_desde.day))
    if fecha_hasta:
        q = q.where(fecha < datetime(fecha_hasta.year, fecha_hasta.month, fecha_hasta.day)
                    + timedelta(days=1))
    filas = (await db.execute(q.order_by(TMSViaje.id.desc()))).all()
    viajes = [v for v, _c in filas]
    conductores = await _nombres_conductores(db, viajes)

    salida = []
    for v, c in filas:
        costo = None
        if c:
            total = (c.combustible + c.peajes + c.viaticos + c.horas_extras
                     + c.mantenimiento + c.costos_indirectos)
            flete = c.valor_flete_cobrado or 0.0
            costo = {
                "id": c.id, "combustible": c.combustible, "peajes": c.peajes,
                "viaticos": c.viaticos, "horas_extras": c.horas_extras,
                "mantenimiento": c.mantenimiento, "costos_indirectos": c.costos_indirectos,
                "valor_flete_cobrado": flete, "notas": c.notas,
                "costo_total": round(total, 2),
                "margen": round(flete - total, 2),
                "margen_pct": round((flete - total) / flete * 100, 2) if flete else None,
                "costo_por_km": round(total / v.distancia_km, 2) if v.distancia_km else None,
            }
        salida.append({
            "viaje_id": v.id, "codigo": v.codigo, "estado": _val(v.estado),
            "origen": v.origen_ciudad, "destino": v.destino_ciudad,
            "conductor": conductores.get(v.conductor_hcm_id),
            "distancia_km": v.distancia_km, "num_entregas": v.num_entregas,
            "valor_flete": v.valor_flete,
            "fecha": (v.fecha_real_entrega or v.fecha_programada_cargue or v.created_at),
            "costo": costo,
        })
    return salida


# ─── OTIF desde los viajes ────────────────────────────────────────────────────

class InFullIn(BaseModel):
    in_full: Optional[bool] = None
    motivo: Optional[str] = None


def _a_tiempo(v: TMSViaje, tolerancia: timedelta = timedelta(0)) -> Optional[bool]:
    """Se compara al leer, no se confía en la columna: si alguien corrige la
    fecha programada después de la entrega, la puntualidad cambia con ella.
    La tolerancia es el parámetro `otif_tolerancia_min` de la configuración."""
    if v.fecha_real_entrega and v.fecha_programada_entrega:
        prog = v.fecha_programada_entrega
        # Fecha sin hora (la del despacho del WMS se guarda a la medianoche):
        # cuenta todo ese día, en hora de Colombia. Antes una entrega a las 3 p. m.
        # del día prometido salía «tarde».
        if (prog.hour, prog.minute, prog.second) == (0, 0, 0):
            from zoneinfo import ZoneInfo
            real = v.fecha_real_entrega
            real_local = (real if real.tzinfo else real.replace(tzinfo=timezone.utc)).astimezone(ZoneInfo("America/Bogota"))
            return (real_local - tolerancia).date() <= prog.date()
        return v.fecha_real_entrega <= v.fecha_programada_entrega + tolerancia
    return v.otif_on_time


async def _completo_segun_wms(db: AsyncSession, viaje: TMSViaje) -> Optional[bool]:
    """In-full de un viaje que sale de un despacho del WMS: la orden quedó
    despachada completa. Sin despacho del WMS lo registra el TMS a mano."""
    if not viaje.wms_despacho_id:
        return None
    from app.infrastructure.models.wms import WMSDespacho, WMSOrdenSalidaDetalle
    desp = await db.get(WMSDespacho, viaje.wms_despacho_id)
    if not desp:
        return None
    faltan = (await db.execute(select(func.count()).select_from(WMSOrdenSalidaDetalle).where(
        WMSOrdenSalidaDetalle.orden_id == desp.orden_id,
        func.coalesce(WMSOrdenSalidaDetalle.cantidad_despachada, 0) < WMSOrdenSalidaDetalle.cantidad_solicitada))).scalar()
    return not faltan


@router.get("/otif/viajes")
async def otif_por_viaje(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los viajes entregados con su puntualidad y su completitud.

    POR QUÉ DESDE LOS VIAJES Y NO DESDE `tms_otif_registro`
    El viaje ya sabe si llegó a tiempo: se calcula al entregarlo. Lo que nadie
    registraba era si llegó COMPLETO, y por eso el OTIF del tablero —que se
    arma con los viajes— salía en cero. La tabla de registros era una segunda
    copia que ninguna pantalla llenaba; aquí se usa una sola fuente.

    `in_full` en nulo significa «nadie lo ha confirmado todavía», que no es lo
    mismo que «llegó incompleto». Se cuenta aparte para no castigar el
    indicador por una confirmación que falta.
    """
    q = select(TMSViaje).where(TMSViaje.deleted_at.is_(None),
                               TMSViaje.estado.in_(_ESTADOS_ENTREGADOS),
                               TMSViaje.fecha_real_entrega.isnot(None))
    if fecha_desde:
        q = q.where(TMSViaje.fecha_real_entrega >= datetime(fecha_desde.year, fecha_desde.month, fecha_desde.day))
    if fecha_hasta:
        q = q.where(TMSViaje.fecha_real_entrega < datetime(fecha_hasta.year, fecha_hasta.month, fecha_hasta.day) + timedelta(days=1))
    viajes = list((await db.execute(q.order_by(TMSViaje.fecha_real_entrega.desc()))).scalars().all())
    conductores = await _nombres_conductores(db, viajes)
    clientes = await _nombres_clientes(db, viajes)
    salida = []
    tolerancia = await _tolerancia_otif(db)
    for v in viajes:
        on_time = _a_tiempo(v, tolerancia)
        retraso = None
        if v.fecha_real_entrega and v.fecha_programada_entrega:
            retraso = round((v.fecha_real_entrega - v.fecha_programada_entrega).total_seconds() / 3600, 2)
        salida.append({
            "viaje_id": v.id, "codigo": v.codigo,
            "cliente": clientes.get(v.generador_id),
            "conductor": conductores.get(v.conductor_hcm_id),
            "origen": v.origen_ciudad, "destino": v.destino_ciudad,
            "fecha_programada": v.fecha_programada_entrega,
            "fecha_real": v.fecha_real_entrega,
            "horas_retraso": retraso,
            "on_time": on_time, "in_full": v.otif_in_full,
            "otif": (on_time and v.otif_in_full) if on_time is not None and v.otif_in_full is not None else None,
            "motivo": v.otif_motivo,
        })
    return salida


@router.put("/viajes/{viaje_id}/in-full")
async def confirmar_in_full(
    viaje_id: int,
    data: InFullIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Confirma si la entrega llegó completa. Es lo único del OTIF que decide
    una persona: la puntualidad sale de las fechas."""
    viaje = await db.get(TMSViaje, viaje_id)
    if not viaje or viaje.deleted_at:
        raise HTTPException(404, "Viaje no encontrado")
    if viaje.estado not in _ESTADOS_ENTREGADOS:
        raise HTTPException(400, "Solo se confirma la completitud de un viaje entregado")
    motivo = (data.motivo or "").strip() or None
    if data.in_full is False and not motivo:
        raise HTTPException(422, "Indica qué faltó en la entrega")
    viaje.otif_in_full = data.in_full
    viaje.otif_motivo = motivo
    await db.commit()
    return {"viaje_id": viaje.id, "in_full": viaje.otif_in_full, "motivo": viaje.otif_motivo}


# ─── Planeación: asignar vehículo y conductor ────────────────────────────────

class AsignacionIn(BaseModel):
    viaje_id: int
    vehiculo_id: int
    conductor_hcm_id: int


_ESTADOS_ACTIVOS = [EstadoViajeTMSEnum.ASIGNADO, EstadoViajeTMSEnum.EN_TRANSITO]


@router.get("/planeacion")
async def planeacion(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Lo que hace falta para asignar: los viajes programados que esperan
    recursos, los vehículos con la capacidad que les queda y los conductores
    con si ya están en un viaje.

    La capacidad libre no se guarda: es la capacidad del vehículo menos el
    peso de los viajes que tiene asignados o en tránsito. Guardada, quedaría
    ocupada para siempre el día que un viaje se cancelara sin descontarla.
    """
    from app.infrastructure.models.hcm import HCMColaborador, HCMConductor

    pendientes = list((await db.execute(
        select(TMSViaje).where(TMSViaje.deleted_at.is_(None),
                               TMSViaje.estado == EstadoViajeTMSEnum.PROGRAMADO)
        .order_by(func.coalesce(TMSViaje.fecha_programada_cargue, TMSViaje.created_at))
    )).scalars().all())
    clientes = await _nombres_clientes(db, pendientes)

    activos = list((await db.execute(
        select(TMSViaje).where(TMSViaje.deleted_at.is_(None),
                               TMSViaje.estado.in_(_ESTADOS_ACTIVOS))
    )).scalars().all())
    carga_por_vehiculo: dict = {}
    viaje_por_vehiculo: dict = {}
    viaje_por_conductor: dict = {}
    for v in activos:
        if v.vehiculo_id:
            carga_por_vehiculo[v.vehiculo_id] = carga_por_vehiculo.get(v.vehiculo_id, 0) + (v.peso_kg or 0)
            viaje_por_vehiculo.setdefault(v.vehiculo_id, v.codigo)
        if v.conductor_hcm_id:
            viaje_por_conductor.setdefault(v.conductor_hcm_id, v.codigo)

    vehiculos = (await db.execute(
        select(TMSVehiculo).where(TMSVehiculo.estado_operativo.in_(
            [EstadoVehiculoTMSEnum.DISPONIBLE, EstadoVehiculoTMSEnum.EN_VIAJE]))
        .order_by(TMSVehiculo.placa))).scalars().all()

    from app.core import tms_capacidad
    carga_m3_por_vehiculo: dict = {}
    for v in activos:
        if v.vehiculo_id:
            carga_m3_por_vehiculo[v.vehiculo_id] = carga_m3_por_vehiculo.get(v.vehiculo_id, 0) + (v.volumen_m3 or 0)
    capacidades = {x.id: await tms_capacidad.capacidad_de(db, x) for x in vehiculos}

    hoy = date.today()
    conductores = (await db.execute(
        select(HCMConductor.id, HCMColaborador.nombres, HCMColaborador.apellidos,
               HCMConductor.tipo_licencia, HCMConductor.fecha_vencimiento_licencia)
        .join(HCMColaborador, HCMConductor.colaborador_id == HCMColaborador.id)
        .order_by(HCMColaborador.nombres))).all()

    return {
        "pendientes": [{
            "viaje_id": v.id, "codigo": v.codigo,
            "cliente": clientes.get(v.generador_id),
            "origen": v.origen_ciudad, "destino": v.destino_ciudad,
            "peso_kg": v.peso_kg, "volumen_m3": v.volumen_m3,
            "tipo_servicio": _val(v.tipo_servicio),
            "fecha_cargue": v.fecha_programada_cargue,
            "fecha_entrega": v.fecha_programada_entrega,
            "valor_flete": v.valor_flete,
            "vehiculo_id": v.vehiculo_id, "conductor_hcm_id": v.conductor_hcm_id,
        } for v in pendientes],
        "vehiculos": [{
            "id": x.id, "placa": x.placa, "tipo": _val(x.tipo_vehiculo),
            "estado": _val(x.estado_operativo),
            "capacidad_kg": capacidades[x.id][0], "volumen_m3": capacidades[x.id][1],
            "carga_asignada_kg": round(carga_por_vehiculo.get(x.id, 0), 2),
            "carga_asignada_m3": round(carga_m3_por_vehiculo.get(x.id, 0), 3),
            "capacidad_libre_kg": (round(capacidades[x.id][0] - carga_por_vehiculo.get(x.id, 0), 2)
                                   if capacidades[x.id][0] is not None else None),
            "capacidad_libre_m3": (round(capacidades[x.id][1] - carga_m3_por_vehiculo.get(x.id, 0), 3)
                                   if capacidades[x.id][1] is not None else None),
            "viaje_activo": viaje_por_vehiculo.get(x.id),
        } for x in vehiculos],
        "conductores": [{
            "id": cid, "nombre": f"{n} {a}".strip(), "licencia": _val(tl),
            "licencia_vence": venc,
            "licencia_vencida": bool(venc and venc < hoy),
            "viaje_activo": viaje_por_conductor.get(cid),
        } for cid, n, a, tl, venc in conductores],
    }


@router.post("/planeacion/asignar")
async def asignar_viaje(
    data: AsignacionIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Asigna vehículo y conductor y pasa el viaje a ASIGNADO, todo o nada.

    Hecho en dos pasos desde la pantalla —guardar el viaje y después cambiarle
    el estado— un fallo en el segundo dejaba el viaje con recursos puestos y
    todavía PROGRAMADO, fuera de la cola y sin estar asignado.
    """
    from app.infrastructure.models.hcm import HCMConductor

    viaje = await db.get(TMSViaje, data.viaje_id)
    if not viaje or viaje.deleted_at:
        raise HTTPException(404, "Viaje no encontrado")
    if viaje.estado != EstadoViajeTMSEnum.PROGRAMADO:
        raise HTTPException(400, f"El viaje ya está {_val(viaje.estado)}")
    vehiculo = await db.get(TMSVehiculo, data.vehiculo_id)
    if not vehiculo:
        raise HTTPException(404, "Vehículo no encontrado")
    if vehiculo.estado_operativo in (EstadoVehiculoTMSEnum.EN_MANTENIMIENTO,
                                     EstadoVehiculoTMSEnum.FUERA_SERVICIO):
        raise HTTPException(400, f"El vehículo {vehiculo.placa} está {_val(vehiculo.estado_operativo)}")
    conductor = await db.get(HCMConductor, data.conductor_hcm_id)
    if not conductor:
        raise HTTPException(404, "Conductor no encontrado")
    if conductor.fecha_vencimiento_licencia and conductor.fecha_vencimiento_licencia < date.today():
        raise HTTPException(400, "La licencia del conductor está vencida")

    ocupado = (await db.execute(select(TMSViaje.codigo).where(
        TMSViaje.deleted_at.is_(None), TMSViaje.estado.in_(_ESTADOS_ACTIVOS),
        TMSViaje.conductor_hcm_id == conductor.id).limit(1))).scalar()
    if ocupado:
        raise HTTPException(400, f"El conductor ya está en el viaje {ocupado}")

    # Peso y volumen contra la capacidad del vehículo (la suya o la de su tipo).
    from app.core import tms_capacidad
    await tms_capacidad.exigir(db, vehiculo, viaje.peso_kg, viaje.volumen_m3, excluir_viaje_id=viaje.id)

    viaje.vehiculo_id = vehiculo.id
    viaje.conductor_hcm_id = conductor.id
    viaje.estado = EstadoViajeTMSEnum.ASIGNADO
    await db.commit()
    await db.refresh(viaje)
    return await _viaje_to_response(db, viaje)


# ─── Documentos: pruebas de entrega y faltantes ──────────────────────────────

# Qué documentos debe tener un viaje según dónde va. Antes de salir, la remesa
# y el manifiesto (sin ellos el vehículo no puede circular con carga); una vez
# entregado, además el cumplido. La prueba de entrega (POD) es su propio
# registro, no un documento.
_DOCS_REQUERIDOS = {
    "ASIGNADO":    ["REMESA", "MANIFIESTO"],
    "EN_TRANSITO": ["REMESA", "MANIFIESTO"],
    "ENTREGADO":   ["REMESA", "MANIFIESTO", "CUMPLIDO"],
}


@router.get("/documentos/pendientes")
async def documentos_pendientes(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Viajes en curso o entregados a los que les falta algún documento."""
    viajes = list((await db.execute(select(TMSViaje).where(
        TMSViaje.deleted_at.is_(None),
        TMSViaje.estado.in_([EstadoViajeTMSEnum.ASIGNADO, EstadoViajeTMSEnum.EN_TRANSITO,
                             EstadoViajeTMSEnum.ENTREGADO]))
        .order_by(TMSViaje.fecha_programada_cargue))).scalars().all())
    if not viajes:
        return []
    ids = [v.id for v in viajes]
    tiene: dict = {}
    for vid, tipo, estado in (await db.execute(
            select(TMSDocumento.viaje_id, TMSDocumento.tipo_documento, TMSDocumento.estado)
            .where(TMSDocumento.viaje_id.in_(ids)))).all():
        # Un documento rechazado no cuenta como presentado.
        if _val(estado) != "RECHAZADO":
            tiene.setdefault(vid, set()).add(_val(tipo))
    con_pod = set((await db.execute(select(TMSPOD.viaje_id).where(TMSPOD.viaje_id.in_(ids)))).scalars().all())

    salida = []
    for v in viajes:
        estado = _val(v.estado)
        faltan = [t for t in _DOCS_REQUERIDOS.get(estado, []) if t not in tiene.get(v.id, set())]
        if estado == "ENTREGADO" and v.id not in con_pod:
            faltan.append("POD")
        if faltan:
            salida.append({
                "viaje_id": v.id, "codigo": v.codigo, "estado": estado,
                "origen": v.origen_ciudad, "destino": v.destino_ciudad,
                "fecha_programada": v.fecha_programada_cargue,
                "faltantes": faltan,
            })
    return salida


@router.get("/pod")
async def listar_pods(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Todas las pruebas de entrega, con el viaje al que pertenecen."""
    filas = (await db.execute(
        select(TMSPOD, TMSViaje).join(TMSViaje, TMSViaje.id == TMSPOD.viaje_id)
        .order_by(TMSPOD.fecha_hora.desc().nullslast(), TMSPOD.id.desc()))).all()
    conductores = await _nombres_conductores(db, [v for _p, v in filas])
    return [{
        "id": p.id, "viaje_id": v.id, "codigo_viaje": v.codigo,
        "destino": v.destino_ciudad, "conductor": conductores.get(v.conductor_hcm_id),
        "receptor_nombre": p.receptor_nombre, "receptor_documento": p.receptor_documento,
        "lat": p.lat, "lng": p.lng, "fecha_hora": p.fecha_hora,
        "foto_url": p.foto_url, "firma_url": p.firma_url,
        "observaciones": p.observaciones,
    } for p, v in filas]


# ─── Estimador de ruta con datos propios ─────────────────────────────────────

@router.get("/rutas-estimar")
async def estimar_ruta(
    origen: str = Query(..., min_length=2),
    destino: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Distancia, duración y costo entre dos ciudades, con lo que ya se sabe.

    El «optimizador» de la pantalla de rutas inventaba la distancia con un
    número al azar entre 400 y 1.100 km y le sumaba tres alternativas fijas;
    cualquier par de ciudades daba un resultado distinto cada vez. Aquí no se
    calcula un recorrido —para eso haría falta un motor de mapas—: se reúne lo
    que la empresa ya registró entre esas dos ciudades.

      - Las rutas del catálogo con ese origen y destino, como alternativas.
      - Los viajes hechos entre ellas: distancia promedio, cuánto tardaron de
        verdad (del cargue real a la entrega real) y su costo por km.
      - El costo por km de toda la flota, para cuando la ruta no tiene viajes.

    Si no hay nada, se dice; un número inventado es peor que ninguno.
    """
    o, d = f"%{origen.strip()}%", f"%{destino.strip()}%"
    rutas = (await db.execute(
        select(TMSRuta).where(TMSRuta.activo.is_(True), TMSRuta.origen.ilike(o), TMSRuta.destino.ilike(d))
        .order_by(TMSRuta.distancia_km.asc().nullslast()))).scalars().all()

    viajes = (await db.execute(
        select(TMSViaje, TMSCostoViaje).outerjoin(TMSCostoViaje, TMSCostoViaje.viaje_id == TMSViaje.id)
        .where(TMSViaje.deleted_at.is_(None), TMSViaje.estado != EstadoViajeTMSEnum.CANCELADO,
               TMSViaje.origen_ciudad.ilike(o), TMSViaje.destino_ciudad.ilike(d)))).all()

    distancias = [v.distancia_km for v, _c in viajes if v.distancia_km]
    horas = [(v.fecha_real_entrega - v.fecha_real_cargue).total_seconds() / 3600
             for v, _c in viajes if v.fecha_real_entrega and v.fecha_real_cargue
             and v.fecha_real_entrega > v.fecha_real_cargue]
    costos_km = []
    for v, c in viajes:
        if c and v.distancia_km:
            total = c.combustible + c.peajes + c.viaticos + c.horas_extras + c.mantenimiento + c.costos_indirectos
            costos_km.append(total / v.distancia_km)

    # Costo por km de toda la flota: suma de costos sobre suma de km, no el
    # promedio de los cocientes, para que un viaje corto no pese lo que uno largo.
    flota = (await db.execute(
        select(func.sum(TMSCostoViaje.combustible + TMSCostoViaje.peajes + TMSCostoViaje.viaticos
                        + TMSCostoViaje.horas_extras + TMSCostoViaje.mantenimiento
                        + TMSCostoViaje.costos_indirectos),
               func.sum(TMSViaje.distancia_km))
        .join(TMSViaje, TMSViaje.id == TMSCostoViaje.viaje_id)
        .where(TMSViaje.distancia_km > 0, TMSViaje.deleted_at.is_(None)))).one()
    costo_km_flota = round(flota[0] / flota[1], 2) if flota[0] and flota[1] else None

    prom = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    return {
        "origen": origen.strip(), "destino": destino.strip(),
        "rutas": [{
            "id": r.id, "nombre": r.nombre, "codigo": r.codigo,
            "origen": r.origen, "destino": r.destino,
            "distancia_km": r.distancia_km, "tiempo_estimado_min": r.tiempo_estimado_min,
            "costo_referencia": r.costo_referencia,
        } for r in rutas],
        "historico": {
            "viajes": len(viajes),
            "distancia_km": prom(distancias),
            "horas_reales": prom(horas), "viajes_con_tiempo": len(horas),
            "costo_por_km": prom(costos_km), "viajes_con_costo": len(costos_km),
        },
        "costo_por_km_flota": costo_km_flota,
    }


@router.get("/rutas-analisis")
async def analisis_rutas(
    fecha_desde: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Desempeño por corredor (origen → destino), sacado de los viajes.

    La pestaña de análisis mostraba ocho rutas con OTIF, costo y tiempo
    escritos a mano. Se agrupa por las ciudades del viaje y no por la ruta del
    catálogo porque los viajes no guardan a qué ruta pertenecen: el corredor es
    lo único que todos tienen.
    """
    q = (select(TMSViaje, TMSCostoViaje)
         .outerjoin(TMSCostoViaje, TMSCostoViaje.viaje_id == TMSViaje.id)
         .where(TMSViaje.deleted_at.is_(None), TMSViaje.estado.in_(_ESTADOS_ENTREGADOS),
                TMSViaje.origen_ciudad.isnot(None), TMSViaje.destino_ciudad.isnot(None)))
    if fecha_desde:
        q = q.where(TMSViaje.fecha_real_entrega >= datetime(fecha_desde.year, fecha_desde.month, fecha_desde.day))
    grupos: dict = {}
    tolerancia = await _tolerancia_otif(db)
    for v, c in (await db.execute(q)).all():
        k = (v.origen_ciudad.strip(), v.destino_ciudad.strip())
        g = grupos.setdefault(k, {"n": 0, "ot": [], "otif": [], "costo": 0.0, "km": 0.0, "horas": []})
        g["n"] += 1
        a_tiempo = _a_tiempo(v, tolerancia)
        if a_tiempo is not None:
            g["ot"].append(a_tiempo)
            if v.otif_in_full is not None:
                g["otif"].append(a_tiempo and v.otif_in_full)
        if c and v.distancia_km:
            g["costo"] += c.combustible + c.peajes + c.viaticos + c.horas_extras + c.mantenimiento + c.costos_indirectos
            g["km"] += v.distancia_km
        if v.fecha_real_entrega and v.fecha_real_cargue and v.fecha_real_entrega > v.fecha_real_cargue:
            g["horas"].append((v.fecha_real_entrega - v.fecha_real_cargue).total_seconds() / 3600)
    pct = lambda xs: round(sum(1 for x in xs if x) / len(xs) * 100, 2) if xs else None
    return sorted([{
        "origen": o, "destino": d, "viajes": g["n"],
        "on_time_rate": pct(g["ot"]), "otif_rate": pct(g["otif"]),
        "costo_por_km": round(g["costo"] / g["km"], 2) if g["km"] else None,
        "horas_promedio": round(sum(g["horas"]) / len(g["horas"]), 2) if g["horas"] else None,
    } for (o, d), g in grupos.items()], key=lambda r: -r["viajes"])
