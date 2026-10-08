"""
APS — planeación avanzada, con el motor de `app/core/aps/motor.py`.

La versión anterior de este módulo era un cascarón: el tablero devolvía cifras
escritas en el código (exactitud 91,4 %, OTIF 96,2 %), las simulaciones
quedaban «en ejecución» para siempre, la capacidad comprometida era siempre
cero y el inventario óptimo se digitaba a mano. Las pantallas eran maqueta.

Aquí se guarda lo que una persona decide o registra —maestros, demanda real,
pronósticos publicados y sus ajustes, órdenes aprobadas, escenarios, ciclos
S&OP— y todo lo demás se calcula: pronóstico, inventario objetivo, DRP, MPS,
MRP, carga de capacidad, transporte, alertas y KPIs.

EL CICLO SE CIERRA
  Una orden sugerida que se aprueba entra al plan siguiente como recepción
  programada: el motor no vuelve a sugerir lo que ya se decidió. Al marcarla
  recibida, su cantidad se suma al stock de la ubicación (y en un traslado se
  descuenta del origen), que es el punto de partida del plan siguiente.
"""
import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.aps.motor import CONFIG_DEFECTO, Datos, calcular, mes_actual, sumar_meses
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.tenant import esquema_actual
from app.infrastructure.models.aps import (
    APSColaboracion, APSConfig, APSDemanda, APSDetallePeriodo, APSEscenario, APSOrdenSugerida,
    APSParametro, APSPlanDetalle, APSPlanMaestro, APSCargaCapacidad, APSProducto, APSPronostico,
    APSRecurso, APSRestriccion, APSResultadoSimulacion, APSRuta, APSSimulacion, APSSOIPCiclo,
    APSSOIPRevision, APSUbicacion,
    EstadoEscenarioAPSEnum, EstadoPlanAPSEnum, HorizontePlanAPSEnum, TipoEscenarioAPSEnum, TipoOrdenSugeridaAPSEnum,
    TipoPlanAPSEnum, TipoPronosticoAPSEnum, TipoRecursoAPSEnum, TipoRestriccionAPSEnum,
)
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/aps", tags=["APS"])

PERIODO = r"^\d{4}-(0[1-9]|1[0-2])$"


def _val(e):
    return e.value if hasattr(e, "value") else e


def _dump(o, campos):
    return {c: _val(getattr(o, c)) for c in campos}


# ─── Motor con caché por empresa ──────────────────────────────────────────────

TABLAS_MOTOR = ("aps_demanda", "aps_parametro", "aps_producto", "aps_ubicacion", "aps_recurso", "aps_ruta",
                "aps_config", "aps_restriccion", "aps_detalle_periodo", "aps_colaboracion",
                "aps_orden_sugerida", "aps_pronostico")
_CACHE: Dict[tuple, tuple] = {}


async def _firma(db: AsyncSession) -> tuple:
    """Última modificación y conteo de cada tabla que usa el motor. Si algo
    cambia —aunque lo haya cambiado otro proceso del servidor— la firma cambia
    y el plan se recalcula; un borrado cambia el conteo."""
    sql = " UNION ALL ".join(f"SELECT '{t}', max(updated_at), count(*) FROM {t}" for t in TABLAS_MOTOR)
    return tuple((await db.execute(text(sql))).all())


async def _datos(db: AsyncSession) -> Datos:
    inicio = mes_actual()
    ubic = {u.id: {"codigo": u.codigo, "nombre": u.nombre, "tipo": u.tipo, "abastecida_por_id": u.abastecida_por_id}
            for u in (await db.execute(select(APSUbicacion).where(APSUbicacion.activo.is_(True)))).scalars().all()}
    prods = {p.id: {"codigo": p.codigo, "nombre": p.nombre, "familia": p.familia, "costo_unitario": p.costo_unitario,
                    "lead_time_dias": p.lead_time_dias, "peso_kg": p.peso_kg}
             for p in (await db.execute(select(APSProducto).where(APSProducto.activo.is_(True)))).scalars().all()}
    recs = {r.id: {"codigo": r.codigo, "nombre": r.nombre, "capacidad_diaria": r.capacidad_diaria,
                   "eficiencia_pct": r.eficiencia_pct}
            for r in (await db.execute(select(APSRecurso).where(APSRecurso.activo.is_(True)))).scalars().all()}
    rutas = [{"producto_id": r.producto_id, "recurso_id": r.recurso_id, "horas_por_unidad": r.horas_por_unidad}
             for r in (await db.execute(select(APSRuta))).scalars().all()
             if r.producto_id in prods and r.recurso_id in recs]
    params = {(p.producto_id, p.ubicacion_id): {
        "stock_actual": p.stock_actual, "nivel_servicio_pct": p.nivel_servicio_pct,
        "lote_minimo_compra": p.lote_minimo_compra, "lote_produccion": p.lote_produccion,
        "lead_time_compra_dias": p.lead_time_compra_dias, "lead_time_produccion_dias": p.lead_time_produccion_dias}
        for p in (await db.execute(select(APSParametro))).scalars().all()}
    demanda: Dict[tuple, Dict[str, float]] = defaultdict(dict)
    for d in (await db.execute(select(APSDemanda))).scalars().all():
        demanda[(d.producto_id, d.ubicacion_id)][d.periodo] = d.cantidad
    config = {c.clave: c.valor for c in (await db.execute(select(APSConfig))).scalars().all()}

    # Pronósticos publicados: el activo manda en el plan; todos sirven para medir exactitud.
    pubs = (await db.execute(select(APSPronostico).where(APSPronostico.tipo == TipoPronosticoAPSEnum.CONSENSO)
                             .order_by(APSPronostico.created_at))).scalars().all()
    detalles = defaultdict(list)
    for dp in (await db.execute(select(APSDetallePeriodo))).scalars().all():
        detalles[dp.pronostico_id].append(dp)
    ajustes = defaultdict(float)
    for c in (await db.execute(select(APSColaboracion).where(APSColaboracion.aprobado.is_(True)))).scalars().all():
        ajustes[(c.pronostico_id, c.periodo)] += c.cantidad_ajuste
    consenso: Dict[tuple, Dict[str, float]] = defaultdict(dict)
    ultimo_por_periodo: Dict[tuple, float] = {}
    for p in pubs:
        for dp in detalles[p.id]:
            valor = max(0.0, dp.cantidad_pronosticada + ajustes[(p.id, dp.periodo)])
            ultimo_por_periodo[(p.producto_id, p.ubicacion_id, dp.periodo)] = valor
            if p.activo and dp.periodo >= inicio:
                consenso[(p.producto_id, p.ubicacion_id)][dp.periodo] = valor
    publicados = [{"producto_id": pid, "ubicacion_id": uid, "periodo": per, "pronostico": v,
                   "real": demanda.get((pid, uid), {}).get(per, 0.0)}
                  for (pid, uid, per), v in ultimo_por_periodo.items() if per < inicio]

    programadas = []
    for o in (await db.execute(select(APSOrdenSugerida).where(APSOrdenSugerida.estado == "APROBADA"))).scalars().all():
        f = o.fecha_requerida
        programadas.append({"producto_id": o.producto_id, "ubicacion_id": o.ubicacion_id, "tipo": _val(o.tipo),
                            "cantidad": o.cantidad, "periodo": f"{f.year}-{f.month:02d}"})
    bodega, camion = {}, {}
    for r in (await db.execute(select(APSRestriccion).where(APSRestriccion.activo.is_(True)))).scalars().all():
        if r.ambito == "BODEGA" and r.ubicacion_id and r.valor_max:
            bodega[r.ubicacion_id] = r.valor_max
        if r.ambito == "TRANSPORTE" and r.ubicacion_id and r.valor_max:
            camion[r.ubicacion_id] = r.valor_max
    return Datos(ubicaciones=ubic, productos=prods, recursos=recs, rutas=rutas, parametros=params,
                 demanda=dict(demanda), config=config, consenso=dict(consenso), programadas=programadas,
                 bodega_max=bodega, camion_kg=camion, publicados=publicados)


async def _motor(db: AsyncSession, demanda: float = 0, capacidad: float = 0, costo: float = 0) -> Dict:
    clave = (esquema_actual(), await _firma(db), mes_actual(), demanda, capacidad, costo)
    ahora = time.monotonic()
    guardado = _CACHE.get(clave)
    if guardado and ahora - guardado[0] < 600:
        return guardado[1]
    datos = await _datos(db)
    r = calcular(datos, demanda, capacidad, costo)
    r["_datos"] = datos
    # La caché no crece sin límite: se quedan las 20 más recientes.
    if len(_CACHE) > 20:
        for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:len(_CACHE) - 20]:
            _CACHE.pop(k, None)
    _CACHE[clave] = (ahora, r)
    return r


def _nombres(r: Dict) -> Dict:
    d: Datos = r["_datos"]
    return {"productos": {k: {"codigo": v["codigo"], "nombre": v["nombre"], "familia": v.get("familia")} for k, v in d.productos.items()},
            "ubicaciones": {k: {"codigo": v["codigo"], "nombre": v["nombre"]} for k, v in d.ubicaciones.items()},
            "recursos": {k: {"codigo": v["codigo"], "nombre": v["nombre"]} for k, v in d.recursos.items()}}


# ─── Maestros ─────────────────────────────────────────────────────────────────

class UbicacionIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1)
    tipo: str = "PLANTA"
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    abastecida_por_id: Optional[int] = None


class ProductoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=50)
    nombre: str = Field(min_length=1)
    familia: Optional[str] = None
    categoria: Optional[str] = None
    unidad_medida: str = "UN"
    lead_time_dias: int = Field(0, ge=0, le=365)
    costo_unitario: Optional[float] = Field(None, ge=0)
    precio_venta: Optional[float] = Field(None, ge=0)
    peso_kg: Optional[float] = Field(None, ge=0)


class RecursoIn(BaseModel):
    ubicacion_id: Optional[int] = None
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1)
    tipo: str = "LINEA"
    capacidad_diaria: Optional[float] = Field(None, ge=0)
    unidad_capacidad: Optional[str] = "horas"
    eficiencia_pct: float = Field(85.0, gt=0, le=100)


class RutaIn(BaseModel):
    producto_id: int
    recurso_id: int
    horas_por_unidad: float = Field(gt=0)


class ParametroIn(BaseModel):
    producto_id: int
    ubicacion_id: int
    stock_actual: float = Field(0.0, ge=0)
    nivel_servicio_pct: float = Field(95.0, ge=50, le=99.9)
    lote_minimo_compra: Optional[float] = Field(None, ge=0)
    lote_produccion: Optional[float] = Field(None, ge=0)
    lead_time_compra_dias: Optional[int] = Field(None, ge=0, le=365)
    lead_time_produccion_dias: Optional[int] = Field(None, ge=0, le=365)


class RestriccionIn(BaseModel):
    ubicacion_id: Optional[int] = None
    recurso_id: Optional[int] = None
    tipo: str = "DURA"
    ambito: str = Field("OTRA", pattern=r"^(BODEGA|TRANSPORTE|OTRA)$")
    nombre: str = Field(min_length=1)
    descripcion: Optional[str] = None
    valor_min: Optional[float] = None
    valor_max: Optional[float] = None


MAESTROS = {
    "ubicaciones": (APSUbicacion, UbicacionIn, ["id", "codigo", "nombre", "tipo", "ciudad", "pais", "abastecida_por_id", "activo"], True),
    "productos": (APSProducto, ProductoIn, ["id", "codigo", "nombre", "familia", "categoria", "unidad_medida", "lead_time_dias",
                                            "costo_unitario", "precio_venta", "peso_kg", "activo"], True),
    "recursos": (APSRecurso, RecursoIn, ["id", "ubicacion_id", "codigo", "nombre", "tipo", "capacidad_diaria",
                                         "unidad_capacidad", "eficiencia_pct", "activo"], True),
    "rutas": (APSRuta, RutaIn, ["id", "producto_id", "recurso_id", "horas_por_unidad"], False),
    "parametros": (APSParametro, ParametroIn, ["id", "producto_id", "ubicacion_id", "stock_actual", "nivel_servicio_pct",
                                               "lote_minimo_compra", "lote_produccion", "lead_time_compra_dias",
                                               "lead_time_produccion_dias"], False),
    "restricciones": (APSRestriccion, RestriccionIn, ["id", "ubicacion_id", "recurso_id", "tipo", "ambito", "nombre", "descripcion",
                                                      "valor_min", "valor_max", "activo"], True),
}
ENUMS = {"recursos": ("tipo", TipoRecursoAPSEnum), "restricciones": ("tipo", TipoRestriccionAPSEnum)}


async def _validar_maestro(db, nombre, data, id_=None):
    modelo = MAESTROS[nombre][0]
    if nombre in ("ubicaciones", "productos", "recursos"):
        q = select(modelo).where(modelo.codigo == data["codigo"])
        otro = (await db.execute(q)).scalars().first()
        if otro and otro.id != id_:
            raise HTTPException(400, f"Ya existe el código {data['codigo']}")
    if nombre == "ubicaciones" and data.get("abastecida_por_id"):
        if data["abastecida_por_id"] == id_:
            raise HTTPException(400, "Una ubicación no puede abastecerse a sí misma")
        origen = await db.get(APSUbicacion, data["abastecida_por_id"])
        if not origen or origen.abastecida_por_id:
            raise HTTPException(400, "La ubicación que abastece debe ser una planta, que no dependa a su vez de otra")
    if nombre in ("rutas", "parametros"):
        campos = ("producto_id", "recurso_id") if nombre == "rutas" else ("producto_id", "ubicacion_id")
        q = select(modelo).where(*[getattr(modelo, c) == data[c] for c in campos])
        otro = (await db.execute(q)).scalars().first()
        if otro and otro.id != id_:
            raise HTTPException(400, "Ya existe un registro para esa combinación; edítelo")
    if nombre in ENUMS:
        campo, enum = ENUMS[nombre]
        try:
            data[campo] = enum(data[campo])
        except ValueError:
            raise HTTPException(422, f"Tipo no válido: {data[campo]}")
    return data


def _registrar_maestro(nombre: str):
    modelo, esquema, campos, blando = MAESTROS[nombre]

    @router.get(f"/{nombre}", name=f"aps_listar_{nombre}")
    async def listar(db: AsyncSession = Depends(get_db)):
        q = select(modelo)
        if blando:
            q = q.where(modelo.activo.is_(True))
        return [_dump(o, campos) for o in (await db.execute(q.order_by(modelo.id))).scalars().all()]

    @router.post(f"/{nombre}", status_code=201, name=f"aps_crear_{nombre}")
    async def crear(data: esquema, db: AsyncSession = Depends(get_db)):  # type: ignore[valid-type]
        d = await _validar_maestro(db, nombre, data.model_dump())
        obj = modelo(**d)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _dump(obj, campos)

    @router.put(f"/{nombre}/{{id_}}", name=f"aps_editar_{nombre}")
    async def editar(id_: int, data: esquema, db: AsyncSession = Depends(get_db)):  # type: ignore[valid-type]
        obj = await db.get(modelo, id_)
        if not obj:
            raise HTTPException(404, "No encontrado")
        d = await _validar_maestro(db, nombre, data.model_dump(), id_)
        for k, v in d.items():
            setattr(obj, k, v)
        await db.commit()
        await db.refresh(obj)
        return _dump(obj, campos)

    @router.delete(f"/{nombre}/{{id_}}", status_code=204, name=f"aps_retirar_{nombre}")
    async def retirar(id_: int, db: AsyncSession = Depends(get_db)):
        obj = await db.get(modelo, id_)
        if not obj:
            raise HTTPException(404, "No encontrado")
        if blando:
            obj.activo = False
        else:
            await db.delete(obj)
        await db.commit()


for _m in MAESTROS:
    _registrar_maestro(_m)


# ─── Configuración del motor ─────────────────────────────────────────────────

@router.get("/config")
async def leer_config(db: AsyncSession = Depends(get_db)):
    guardados = {c.clave: c.valor for c in (await db.execute(select(APSConfig))).scalars().all()}
    return [{"clave": k, "valor": guardados.get(k, v["defecto"]), **v} for k, v in CONFIG_DEFECTO.items()]


@router.put("/config")
async def guardar_config(data: Dict[str, float], db: AsyncSession = Depends(get_db)):
    for clave, valor in data.items():
        if clave not in CONFIG_DEFECTO:
            raise HTTPException(422, f"Parámetro desconocido: {clave}")
        d = CONFIG_DEFECTO[clave]
        if not d["min"] <= valor <= d["max"]:
            raise HTTPException(422, f"{d['descripcion']}: entre {d['min']} y {d['max']}")
        fila = (await db.execute(select(APSConfig).where(APSConfig.clave == clave))).scalar_one_or_none()
        if fila:
            fila.valor = valor
        else:
            db.add(APSConfig(clave=clave, valor=valor))
    await db.commit()
    return await leer_config(db)


# ─── Demanda histórica ────────────────────────────────────────────────────────

class DemandaIn(BaseModel):
    producto_id: int
    ubicacion_id: int
    periodo: str = Field(pattern=PERIODO)
    cantidad: float = Field(ge=0)


@router.get("/demanda")
async def listar_demanda(producto_id: Optional[int] = None, ubicacion_id: Optional[int] = None,
                         db: AsyncSession = Depends(get_db)):
    q = select(APSDemanda)
    if producto_id:
        q = q.where(APSDemanda.producto_id == producto_id)
    if ubicacion_id:
        q = q.where(APSDemanda.ubicacion_id == ubicacion_id)
    filas = (await db.execute(q.order_by(APSDemanda.periodo.desc()).limit(2000))).scalars().all()
    return [_dump(d, ["id", "producto_id", "ubicacion_id", "periodo", "cantidad"]) for d in filas]


async def _guardar_demanda(db, pid, uid, periodo, cantidad):
    fila = (await db.execute(select(APSDemanda).where(
        APSDemanda.producto_id == pid, APSDemanda.ubicacion_id == uid, APSDemanda.periodo == periodo))).scalar_one_or_none()
    if fila:
        fila.cantidad = cantidad
    else:
        db.add(APSDemanda(producto_id=pid, ubicacion_id=uid, periodo=periodo, cantidad=cantidad))


@router.post("/demanda", status_code=201)
async def registrar_demanda(data: DemandaIn, db: AsyncSession = Depends(get_db)):
    if data.periodo > mes_actual():
        raise HTTPException(400, "La demanda real no puede ser de un mes futuro; eso es un pronóstico")
    if not await db.get(APSProducto, data.producto_id) or not await db.get(APSUbicacion, data.ubicacion_id):
        raise HTTPException(400, "Producto o ubicación no existe")
    await _guardar_demanda(db, data.producto_id, data.ubicacion_id, data.periodo, data.cantidad)
    await db.commit()
    return {"ok": True}


@router.delete("/demanda/{id_}", status_code=204)
async def borrar_demanda(id_: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSDemanda, id_)
    if obj:
        await db.delete(obj)
        await db.commit()


class CargaIn(BaseModel):
    texto: str = Field(min_length=1, max_length=2_000_000)


@router.post("/demanda/carga")
async def cargar_demanda(data: CargaIn, db: AsyncSession = Depends(get_db)):
    """Pegado desde una hoja de cálculo: producto, ubicación, AAAA-MM, cantidad
    por línea, separados por tabulación, punto y coma o coma. Todo o nada: si
    una línea tiene error no se guarda ninguna, y se dice cuál falló."""
    import re
    prods = {p.codigo.upper(): p.id for p in (await db.execute(select(APSProducto))).scalars().all()}
    ubics = {u.codigo.upper(): u.id for u in (await db.execute(select(APSUbicacion))).scalars().all()}
    errores, validas = [], []
    tope = mes_actual()
    for n, linea in enumerate(data.texto.splitlines(), start=1):
        if not linea.strip():
            continue
        partes = [p.strip() for p in re.split(r"[\t;]|,(?=\S)", linea)]
        if n == 1 and not re.match(PERIODO, partes[2] if len(partes) > 2 else ""):
            continue                                            # encabezado
        if len(partes) < 4:
            errores.append(f"Línea {n}: se esperan 4 columnas"); continue
        cod_p, cod_u, per, cant = partes[:4]
        try:
            cantidad = float(cant.replace(",", "."))
        except ValueError:
            errores.append(f"Línea {n}: cantidad «{cant}» no es un número"); continue
        if cod_p.upper() not in prods:
            errores.append(f"Línea {n}: producto «{cod_p}» no existe"); continue
        if cod_u.upper() not in ubics:
            errores.append(f"Línea {n}: ubicación «{cod_u}» no existe"); continue
        if not re.match(PERIODO, per) or per > tope:
            errores.append(f"Línea {n}: periodo «{per}» inválido o futuro"); continue
        if cantidad < 0:
            errores.append(f"Línea {n}: cantidad negativa"); continue
        validas.append((prods[cod_p.upper()], ubics[cod_u.upper()], per, cantidad))
    if errores:
        return {"guardadas": 0, "errores": errores[:50], "total_errores": len(errores)}
    for v in validas:
        await _guardar_demanda(db, *v)
    await db.commit()
    return {"guardadas": len(validas), "errores": []}


# ─── Pronóstico, publicación y consenso ──────────────────────────────────────

@router.get("/pronostico")
async def resumen_pronostico(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    filas = []
    for s in r["series"]:
        e = s["estadistico"]
        filas.append({"producto_id": s["producto_id"], "ubicacion_id": s["ubicacion_id"], "metodo": e.get("metodo"),
                      "nombre_metodo": e.get("nombre"), "meses": e.get("meses"), "suficiente": e.get("suficiente"),
                      "wape": e.get("wape"), "sesgo": e.get("sesgo"), "fva_pct": e.get("fva_pct"),
                      "clase": e["clase"]["tipo"], "proximo": s["demanda_plan"][0] if s["demanda_plan"] else None,
                      "usa_consenso": any(s["usa_consenso"])})
    return {"periodos": r["periodos"], "series": filas, **_nombres(r)}


@router.get("/pronostico/serie")
async def detalle_serie(producto_id: int, ubicacion_id: int, db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    s = next((x for x in r["series"] if x["producto_id"] == producto_id and x["ubicacion_id"] == ubicacion_id), None)
    if not s:
        raise HTTPException(404, "Esa combinación no tiene demanda registrada")
    pub = (await db.execute(select(APSPronostico).where(
        APSPronostico.producto_id == producto_id, APSPronostico.ubicacion_id == ubicacion_id,
        APSPronostico.activo.is_(True), APSPronostico.tipo == TipoPronosticoAPSEnum.CONSENSO))).scalars().first()
    publicado = None
    if pub:
        det = (await db.execute(select(APSDetallePeriodo).where(APSDetallePeriodo.pronostico_id == pub.id)
                                .order_by(APSDetallePeriodo.periodo))).scalars().all()
        ajustes = (await db.execute(select(APSColaboracion).where(APSColaboracion.pronostico_id == pub.id)
                                    .order_by(APSColaboracion.created_at))).scalars().all()
        aprobado = defaultdict(float)
        for a in ajustes:
            if a.aprobado:
                aprobado[a.periodo] += a.cantidad_ajuste
        publicado = {"id": pub.id, "version": pub.version, "fecha": pub.created_at.isoformat() if pub.created_at else None,
                     "detalles": [{"periodo": d.periodo, "estadistico": d.cantidad_pronosticada,
                                   "inferior": d.limite_inferior, "superior": d.limite_superior,
                                   "ajuste_aprobado": aprobado[d.periodo],
                                   "consenso": max(0.0, d.cantidad_pronosticada + aprobado[d.periodo])} for d in det],
                     "ajustes": [_dump(a, ["id", "periodo", "area", "usuario", "cantidad_ajuste", "justificacion", "aprobado"])
                                 for a in ajustes]}
    return {"periodos": r["periodos"], "historia": s["historia"], "estadistico": s["estadistico"],
            "demanda_plan": s["demanda_plan"], "publicado": publicado}


class PublicarIn(BaseModel):
    producto_id: int
    ubicacion_id: int


@router.post("/pronostico/publicar", status_code=201)
async def publicar(data: PublicarIn, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    """Congela el pronóstico estadístico de hoy como versión oficial. Desde ese
    momento se le pueden hacer ajustes por área y, cuando pasen los meses, se
    mide su exactitud contra lo que de verdad se vendió."""
    r = await _motor(db)
    s = next((x for x in r["series"] if x["producto_id"] == data.producto_id and x["ubicacion_id"] == data.ubicacion_id), None)
    if not s:
        raise HTTPException(404, "Esa combinación no tiene demanda registrada")
    e = s["estadistico"]
    previos = (await db.execute(select(APSPronostico).where(
        APSPronostico.producto_id == data.producto_id, APSPronostico.ubicacion_id == data.ubicacion_id,
        APSPronostico.tipo == TipoPronosticoAPSEnum.CONSENSO))).scalars().all()
    for p in previos:
        p.activo = False
    periodos = r["periodos"]
    ini, fin = periodos[0], periodos[-1]
    pron = APSPronostico(producto_id=data.producto_id, ubicacion_id=data.ubicacion_id, tipo=TipoPronosticoAPSEnum.CONSENSO,
                         horizonte=HorizontePlanAPSEnum.MENSUAL,
                         fecha_inicio=datetime(int(ini[:4]), int(ini[5:]), 1, tzinfo=timezone.utc),
                         fecha_fin=datetime(int(fin[:4]), int(fin[5:]), 1, tzinfo=timezone.utc),
                         version=f"v{len(previos) + 1} · {e.get('metodo')}",
                         mape_pct=e.get("wape"), bias_pct=e.get("sesgo"),
                         accuracy_pct=100 - e["wape"] if e.get("wape") is not None else None)
    db.add(pron)
    await db.flush()
    for i, per in enumerate(periodos):
        f = datetime(int(per[:4]), int(per[5:]), 1, tzinfo=timezone.utc)
        db.add(APSDetallePeriodo(pronostico_id=pron.id, periodo=per, fecha_inicio=f, fecha_fin=f,
                                 cantidad_pronosticada=e["pronostico"][i],
                                 limite_inferior=e.get("inferior", [None] * len(periodos))[i],
                                 limite_superior=e.get("superior", [None] * len(periodos))[i]))
    await db.commit()
    return {"id": pron.id, "version": pron.version}


class AjusteIn(BaseModel):
    pronostico_id: int
    periodo: str = Field(pattern=PERIODO)
    area: str = Field(min_length=1)
    cantidad_ajuste: float
    justificacion: str = Field(min_length=3)


@router.post("/pronostico/ajustes", status_code=201)
async def proponer_ajuste(data: AjusteIn, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    pub = await db.get(APSPronostico, data.pronostico_id)
    if not pub or not pub.activo:
        raise HTTPException(400, "Solo se ajusta la versión publicada vigente")
    det = (await db.execute(select(APSDetallePeriodo).where(
        APSDetallePeriodo.pronostico_id == pub.id, APSDetallePeriodo.periodo == data.periodo))).scalar_one_or_none()
    if not det:
        raise HTTPException(400, "Ese mes no está en el horizonte publicado")
    if det.cantidad_pronosticada + data.cantidad_ajuste < 0:
        raise HTTPException(400, "El ajuste dejaría la demanda en negativo")
    obj = APSColaboracion(pronostico_id=pub.id, periodo=data.periodo, area=data.area,
                          usuario=getattr(usuario, "username", None) or "usuario",
                          cantidad_ajuste=data.cantidad_ajuste, justificacion=data.justificacion)
    db.add(obj)
    await db.commit()
    return {"id": obj.id}


@router.patch("/pronostico/ajustes/{id_}/aprobar")
async def aprobar_ajuste(id_: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSColaboracion, id_)
    if not obj:
        raise HTTPException(404, "Ajuste no encontrado")
    obj.aprobado = True
    await db.commit()
    return {"ok": True}


@router.delete("/pronostico/ajustes/{id_}", status_code=204)
async def retirar_ajuste(id_: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSColaboracion, id_)
    if obj and obj.aprobado:
        raise HTTPException(400, "Un ajuste aprobado ya forma parte del consenso")
    if obj:
        await db.delete(obj)
        await db.commit()


@router.get("/pronostico/exactitud")
async def exactitud_publicada(db: AsyncSession = Depends(get_db)):
    """Lo publicado contra lo que pasó, por mes y por familia."""
    r = await _motor(db)
    d: Datos = r["_datos"]
    por_mes, por_familia = defaultdict(lambda: [0.0, 0.0, 0.0]), defaultdict(lambda: [0.0, 0.0, 0.0])
    for p in d.publicados:
        fam = d.productos.get(p["producto_id"], {}).get("familia") or "Sin familia"
        for acum in (por_mes[p["periodo"]], por_familia[fam]):
            acum[0] += abs(p["pronostico"] - p["real"])
            acum[1] += p["pronostico"] - p["real"]
            acum[2] += p["real"]
    fila = lambda k, v: {"clave": k, "exactitud_pct": round(100 - v[0] / v[2] * 100, 1) if v[2] else None,
                         "sesgo_pct": round(v[1] / v[2] * 100, 1) if v[2] else None, "real": v[2]}
    validacion = defaultdict(lambda: [0.0, 0.0])
    for s in r["series"]:
        e = s["estadistico"]
        if e.get("wape") is None:
            continue
        fam = d.productos[s["producto_id"]].get("familia") or "Sin familia"
        vol = sum(list(s["historia"].values())[-6:])
        validacion[fam][0] += e["wape"] * vol
        validacion[fam][1] += vol
    return {"por_mes": [fila(k, v) for k, v in sorted(por_mes.items())],
            "por_familia": [fila(k, v) for k, v in sorted(por_familia.items())],
            "validacion_por_familia": [{"familia": k, "exactitud_pct": round(100 - v[0] / v[1], 1) if v[1] else None}
                                       for k, v in sorted(validacion.items())],
            "kpis": r["kpis"]}


# ─── Plan: MPS, MRP, órdenes ─────────────────────────────────────────────────

@router.get("/plan")
async def plan_vigente(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    return {"periodos": r["periodos"], "mps": r["mps"], "ordenes": r["ordenes"], "traslados": r["traslados"],
            "kpis": r["kpis"], **_nombres(r)}


class AprobarIn(BaseModel):
    producto_id: int
    ubicacion_id: int
    tipo: str
    cantidad: float = Field(gt=0)
    periodo_recepcion: str = Field(pattern=PERIODO)
    costo: Optional[float] = None
    justificacion: Optional[str] = None


@router.post("/ordenes", status_code=201)
async def aprobar_orden(data: AprobarIn, db: AsyncSession = Depends(get_db)):
    """Convierte una sugerencia del plan en una orden aprobada. Desde ahí es
    una recepción programada y el plan deja de sugerirla."""
    try:
        tipo = TipoOrdenSugeridaAPSEnum(data.tipo)
    except ValueError:
        raise HTTPException(422, "Tipo de orden no válido")
    per = data.periodo_recepcion
    obj = APSOrdenSugerida(producto_id=data.producto_id, ubicacion_id=data.ubicacion_id, tipo=tipo,
                           cantidad=data.cantidad, fecha_requerida=datetime(int(per[:4]), int(per[5:]), 1, tzinfo=timezone.utc),
                           prioridad="NORMAL", costo_estimado=data.costo, justificacion=data.justificacion,
                           estado="APROBADA", aprobada=True)
    db.add(obj)
    await db.commit()
    return {"id": obj.id}


@router.get("/ordenes")
async def listar_ordenes(estado: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = select(APSOrdenSugerida)
    if estado:
        q = q.where(APSOrdenSugerida.estado == estado)
    filas = (await db.execute(q.order_by(APSOrdenSugerida.fecha_requerida))).scalars().all()
    return [{**_dump(o, ["id", "producto_id", "ubicacion_id", "tipo", "cantidad", "estado", "costo_estimado", "justificacion"]),
             "periodo": f"{o.fecha_requerida.year}-{o.fecha_requerida.month:02d}"} for o in filas]


@router.patch("/ordenes/{id_}/recibir")
async def recibir_orden(id_: int, db: AsyncSession = Depends(get_db)):
    """La orden llegó: su cantidad pasa al stock de la ubicación. En un
    traslado, sale del origen."""
    o = await db.get(APSOrdenSugerida, id_)
    if not o or o.estado != "APROBADA":
        raise HTTPException(400, "Solo se recibe una orden aprobada y pendiente")

    async def mover(uid, cantidad):
        prm = (await db.execute(select(APSParametro).where(
            APSParametro.producto_id == o.producto_id, APSParametro.ubicacion_id == uid))).scalar_one_or_none()
        if not prm:
            prm = APSParametro(producto_id=o.producto_id, ubicacion_id=uid, stock_actual=0.0)
            db.add(prm)
        prm.stock_actual = max(0.0, (prm.stock_actual or 0) + cantidad)

    await mover(o.ubicacion_id, o.cantidad)
    if _val(o.tipo) == "TRASLADO":
        destino = await db.get(APSUbicacion, o.ubicacion_id)
        if destino and destino.abastecida_por_id:
            await mover(destino.abastecida_por_id, -o.cantidad)
    o.estado = "RECIBIDA"
    await db.commit()
    return {"ok": True}


@router.patch("/ordenes/{id_}/cancelar")
async def cancelar_orden(id_: int, db: AsyncSession = Depends(get_db)):
    o = await db.get(APSOrdenSugerida, id_)
    if not o or o.estado != "APROBADA":
        raise HTTPException(400, "Solo se cancela una orden aprobada y pendiente")
    o.estado = "CANCELADA"
    await db.commit()
    return {"ok": True}


class GuardarPlanIn(BaseModel):
    nombre: str = Field(min_length=3)
    observaciones: Optional[str] = None


@router.post("/planes", status_code=201)
async def guardar_version(data: GuardarPlanIn, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    """Guarda una foto del plan: lo que se decidió en una reunión queda
    registrado aunque el plan vivo cambie mañana con nueva demanda."""
    r = await _motor(db)
    per = r["periodos"]
    plan = APSPlanMaestro(nombre=data.nombre, tipo=TipoPlanAPSEnum.MPS, estado=EstadoPlanAPSEnum.BORRADOR,
                          horizonte=HorizontePlanAPSEnum.MENSUAL,
                          fecha_inicio=datetime(int(per[0][:4]), int(per[0][5:]), 1, tzinfo=timezone.utc),
                          fecha_fin=datetime(int(per[-1][:4]), int(per[-1][5:]), 1, tzinfo=timezone.utc),
                          creado_por=getattr(usuario, "username", None), observaciones=data.observaciones)
    db.add(plan)
    await db.flush()
    costo = {k: v.get("costo_unitario") or 0 for k, v in r["_datos"].productos.items()}
    for m in r["mps"] + r["drp"]:
        for f in m["filas"]:
            if f["planificadas"]:
                fecha = datetime(int(f["periodo"][:4]), int(f["periodo"][5:]), 1, tzinfo=timezone.utc)
                db.add(APSPlanDetalle(plan_id=plan.id, producto_id=m["producto_id"], ubicacion_id=m["ubicacion_id"],
                                      periodo=f["periodo"], fecha_inicio=fecha, fecha_fin=fecha,
                                      cantidad_plan=f["planificadas"], costo_total=f["planificadas"] * costo[m["producto_id"]]))
    for c in r["capacidad"]:
        db.add(APSCargaCapacidad(plan_id=plan.id, recurso_id=c["recurso_id"], periodo=c["periodo"], carga=c["carga_horas"],
                                 capacidad=c["capacidad_horas"], pct_uso=c["uso_pct"], es_cuello=c["sobrecarga"]))
    await db.commit()
    return {"id": plan.id}


@router.get("/planes")
async def listar_versiones(db: AsyncSession = Depends(get_db)):
    planes = (await db.execute(select(APSPlanMaestro).order_by(APSPlanMaestro.created_at.desc()))).scalars().all()
    detalles = defaultdict(lambda: [0, 0.0])
    for d in (await db.execute(select(APSPlanDetalle))).scalars().all():
        detalles[d.plan_id][0] += 1
        detalles[d.plan_id][1] += d.costo_total or 0
    return [{**_dump(p, ["id", "nombre", "estado", "creado_por", "observaciones"]),
             "fecha": p.created_at.isoformat() if p.created_at else None,
             "desde": p.fecha_inicio.strftime("%Y-%m"), "hasta": p.fecha_fin.strftime("%Y-%m"),
             "lineas": detalles[p.id][0], "costo": round(detalles[p.id][1])} for p in planes]


# ─── Vistas calculadas ───────────────────────────────────────────────────────

@router.get("/capacidad")
async def carga_capacidad(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    resumen = []
    for rid in r["_datos"].recursos:
        filas = [c for c in r["capacidad"] if c["recurso_id"] == rid]
        usos = [c["uso_pct"] for c in filas if c["uso_pct"] is not None]
        resumen.append({"recurso_id": rid, "uso_maximo_pct": max(usos) if usos else None,
                        "uso_promedio_pct": round(sum(usos) / len(usos), 1) if usos else None,
                        "meses_sobrecarga": sum(1 for c in filas if c["sobrecarga"]),
                        "carga_total_horas": round(sum(c["carga_horas"] for c in filas), 1)})
    resumen.sort(key=lambda x: -(x["uso_maximo_pct"] or 0))
    return {"periodos": r["periodos"], "capacidad": r["capacidad"], "resumen": resumen,
            "cuello": resumen[0] if resumen and (resumen[0]["uso_maximo_pct"] or 0) > 0 else None, **_nombres(r)}


@router.get("/inventario")
async def inventario_objetivo(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    matriz = defaultdict(int)
    for x in r["inventario"]:
        matriz[f"{x['abc']}{x['xyz'] or '-'}"] += 1
    return {"inventario": r["inventario"], "matriz": dict(matriz), "kpis": r["kpis"], **_nombres(r)}


@router.get("/distribucion")
async def distribucion(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    d: Datos = r["_datos"]
    red = [{"id": uid, "nombre": u["nombre"], "codigo": u["codigo"], "tipo": u.get("tipo"),
            "abastecida_por_id": u.get("abastecida_por_id")} for uid, u in d.ubicaciones.items()]
    return {"periodos": r["periodos"], "red": red, "drp": r["drp"], "traslados": r["traslados"], **_nombres(r)}


@router.get("/transporte")
async def transporte(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    return {"periodos": r["periodos"], "cargas": r["transporte"], **_nombres(r)}


@router.get("/alertas")
async def alertas(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    return {"alertas": r["alertas"], **_nombres(r)}


@router.get("/kpis")
async def kpis(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    return {"kpis": r["kpis"], "config": r["config"], "inicio": r["inicio"]}


@router.get("/tablero")
async def tablero(db: AsyncSession = Depends(get_db)):
    r = await _motor(db)
    d: Datos = r["_datos"]
    maestros = {"productos": len(d.productos), "ubicaciones": len(d.ubicaciones), "recursos": len(d.recursos),
                "series_demanda": len(d.demanda)}
    return {"kpis": r["kpis"], "alertas": r["alertas"][:8], "maestros": maestros, "periodos": r["periodos"],
            "capacidad": r["capacidad"], **_nombres(r)}


# ─── Escenarios ──────────────────────────────────────────────────────────────

class EscenarioIn(BaseModel):
    nombre: str = Field(min_length=3)
    tipo: str = "WHAT_IF"
    descripcion: Optional[str] = None
    supuesto_demanda_delta_pct: float = Field(0.0, ge=-90, le=300)
    supuesto_capacidad_delta_pct: float = Field(0.0, ge=-90, le=300)
    supuesto_costo_delta_pct: float = Field(0.0, ge=-90, le=300)


CAMPOS_ESC = ["id", "nombre", "tipo", "descripcion", "supuesto_demanda_delta_pct", "supuesto_capacidad_delta_pct",
              "supuesto_costo_delta_pct", "estado", "aprobado", "creado_por"]


@router.get("/escenarios")
async def listar_escenarios(db: AsyncSession = Depends(get_db)):
    return [_dump(e, CAMPOS_ESC) for e in (await db.execute(select(APSEscenario).order_by(APSEscenario.id))).scalars().all()]


@router.post("/escenarios", status_code=201)
async def crear_escenario(data: EscenarioIn, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    try:
        tipo = TipoEscenarioAPSEnum(data.tipo)
    except ValueError:
        raise HTTPException(422, "Tipo de escenario no válido")
    obj = APSEscenario(**{**data.model_dump(), "tipo": tipo}, creado_por=getattr(usuario, "username", None))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _dump(obj, CAMPOS_ESC)


@router.put("/escenarios/{id_}")
async def editar_escenario(id_: int, data: EscenarioIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSEscenario, id_)
    if not obj:
        raise HTTPException(404, "Escenario no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, TipoEscenarioAPSEnum(v) if k == "tipo" else v)
    await db.commit()
    return _dump(obj, CAMPOS_ESC)


@router.delete("/escenarios/{id_}", status_code=204)
async def borrar_escenario(id_: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSEscenario, id_)
    if obj:
        for s in (await db.execute(select(APSSimulacion).where(APSSimulacion.escenario_id == id_))).scalars().all():
            for res in (await db.execute(select(APSResultadoSimulacion).where(APSResultadoSimulacion.simulacion_id == s.id))).scalars().all():
                await db.delete(res)
            await db.delete(s)
        await db.delete(obj)
        await db.commit()


METRICAS = [
    ("unidades_produccion", "Unidades a producir"), ("unidades_compra", "Unidades a comprar"),
    ("costo_ordenes", "Costo de producción y compras"), ("inventario_proyectado_promedio", "Inventario promedio proyectado ($)"),
    ("uso_capacidad_maximo_pct", "Uso máximo de capacidad (%)"), ("recursos_sobrecargados", "Recursos sobrecargados"),
    ("ordenes_atrasadas", "Órdenes atrasadas (riesgo de quiebre)"), ("alertas_criticas", "Alertas críticas"),
]


@router.post("/escenarios/{id_}/simular")
async def simular(id_: int, db: AsyncSession = Depends(get_db)):
    """Corre el plan completo con los supuestos del escenario y lo compara con
    el plan base. No guarda órdenes: solo el resultado de la comparación."""
    esc = await db.get(APSEscenario, id_)
    if not esc:
        raise HTTPException(404, "Escenario no encontrado")
    t0 = time.monotonic()
    base = await _motor(db)
    alt = await _motor(db, esc.supuesto_demanda_delta_pct or 0, esc.supuesto_capacidad_delta_pct or 0,
                       esc.supuesto_costo_delta_pct or 0)
    sim = APSSimulacion(escenario_id=id_, nombre=f"{esc.nombre} {datetime.now(timezone.utc):%Y-%m-%d %H:%M}",
                        estado="COMPLETADO", duracion_seg=round(time.monotonic() - t0, 2))
    db.add(sim)
    await db.flush()
    salida = []
    for clave, nombre in METRICAS:
        vb, ve = base["kpis"].get(clave), alt["kpis"].get(clave)
        delta = (ve - vb) if vb is not None and ve is not None else None
        pct = round(delta / vb * 100, 1) if delta is not None and vb else None
        db.add(APSResultadoSimulacion(simulacion_id=sim.id, metrica=nombre, valor_base=vb, valor_escenario=ve,
                                      delta=delta, delta_pct=pct))
        salida.append({"clave": clave, "metrica": nombre, "base": vb, "escenario": ve, "delta": delta, "delta_pct": pct})
    esc.estado = EstadoEscenarioAPSEnum.COMPLETADO
    await db.commit()
    return {"simulacion_id": sim.id, "resultados": salida, "alertas_escenario": alt["alertas"][:10]}


@router.get("/escenarios/{id_}/resultados")
async def resultados(id_: int, db: AsyncSession = Depends(get_db)):
    sim = (await db.execute(select(APSSimulacion).where(APSSimulacion.escenario_id == id_)
                            .order_by(APSSimulacion.id.desc()))).scalars().first()
    if not sim:
        return {"simulacion": None, "resultados": []}
    res = (await db.execute(select(APSResultadoSimulacion).where(APSResultadoSimulacion.simulacion_id == sim.id)
                            .order_by(APSResultadoSimulacion.id))).scalars().all()
    return {"simulacion": _dump(sim, ["id", "nombre", "estado", "duracion_seg"]) | {"fecha": sim.created_at.isoformat() if sim.created_at else None},
            "resultados": [_dump(x, ["metrica", "valor_base", "valor_escenario", "delta", "delta_pct"]) for x in res]}


# ─── S&OP ────────────────────────────────────────────────────────────────────

class CicloIn(BaseModel):
    nombre: str = Field(min_length=3)
    periodo: str = Field(pattern=PERIODO)
    fecha_inicio: datetime
    facilitador: Optional[str] = None
    acuerdos: Optional[str] = None


class RevisionIn(BaseModel):
    ciclo_id: int
    tipo: str = Field(min_length=3)
    fecha: datetime
    asistentes: Optional[str] = None
    compromisos: Optional[str] = None


CAMPOS_CICLO = ["id", "nombre", "periodo", "facilitador", "acuerdos", "estado"]
CAMPOS_REV = ["id", "ciclo_id", "tipo", "asistentes", "compromisos", "estado"]


@router.get("/soip/ciclos")
async def ciclos(db: AsyncSession = Depends(get_db)):
    return [{**_dump(c, CAMPOS_CICLO), "fecha_inicio": c.fecha_inicio.isoformat() if c.fecha_inicio else None,
             "fecha_cierre": c.fecha_cierre.isoformat() if c.fecha_cierre else None}
            for c in (await db.execute(select(APSSOIPCiclo).order_by(APSSOIPCiclo.periodo.desc()))).scalars().all()]


@router.post("/soip/ciclos", status_code=201)
async def crear_ciclo(data: CicloIn, db: AsyncSession = Depends(get_db)):
    obj = APSSOIPCiclo(**data.model_dump())
    db.add(obj)
    await db.commit()
    return {"id": obj.id}


@router.put("/soip/ciclos/{id_}")
async def editar_ciclo(id_: int, data: CicloIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSSOIPCiclo, id_)
    if not obj:
        raise HTTPException(404, "Ciclo no encontrado")
    if obj.estado == "CERRADO":
        raise HTTPException(400, "Un ciclo cerrado no se edita: sus acuerdos ya son registro")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    return {"ok": True}


@router.patch("/soip/ciclos/{id_}/cerrar")
async def cerrar_ciclo(id_: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSSOIPCiclo, id_)
    if not obj:
        raise HTTPException(404, "Ciclo no encontrado")
    if not (obj.acuerdos or "").strip():
        raise HTTPException(400, "Registre los acuerdos del ciclo antes de cerrarlo")
    obj.estado = "CERRADO"
    obj.fecha_cierre = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.get("/soip/revisiones")
async def revisiones(ciclo_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(APSSOIPRevision)
    if ciclo_id:
        q = q.where(APSSOIPRevision.ciclo_id == ciclo_id)
    return [{**_dump(r, CAMPOS_REV), "fecha": r.fecha.isoformat() if r.fecha else None}
            for r in (await db.execute(q.order_by(APSSOIPRevision.fecha))).scalars().all()]


@router.post("/soip/revisiones", status_code=201)
async def crear_revision(data: RevisionIn, db: AsyncSession = Depends(get_db)):
    ciclo = await db.get(APSSOIPCiclo, data.ciclo_id)
    if not ciclo or ciclo.estado == "CERRADO":
        raise HTTPException(400, "El ciclo no existe o ya está cerrado")
    obj = APSSOIPRevision(**data.model_dump())
    db.add(obj)
    await db.commit()
    return {"id": obj.id}


@router.delete("/soip/revisiones/{id_}", status_code=204)
async def borrar_revision(id_: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(APSSOIPRevision, id_)
    if obj:
        await db.delete(obj)
        await db.commit()


@router.get("/soip/resumen")
async def resumen_soip(periodo: str = Query(pattern=PERIODO), db: AsyncSession = Depends(get_db)):
    """Demanda contra oferta del mes, por familia: el tablero de la reunión."""
    r = await _motor(db)
    d: Datos = r["_datos"]
    if periodo not in r["periodos"]:
        return {"periodo": periodo, "en_horizonte": False, "periodos": r["periodos"]}
    i = r["periodos"].index(periodo)
    fam = lambda pid: d.productos[pid].get("familia") or "Sin familia"
    costo = lambda pid: d.productos[pid].get("costo_unitario") or 0
    filas = defaultdict(lambda: {"demanda": 0.0, "produccion": 0.0, "compras": 0.0, "stock_final": 0.0, "valor_stock": 0.0})
    for s in r["series"]:
        filas[fam(s["producto_id"])]["demanda"] += s["demanda_plan"][i]
    for m in r["mps"]:
        f = m["filas"][i]
        clave = "produccion" if m["tipo"] == "PRODUCCION" else "compras"
        filas[fam(m["producto_id"])][clave] += f["planificadas"] + f["programadas"]
    for m in r["mps"] + r["drp"]:
        f = m["filas"][i]
        filas[fam(m["producto_id"])]["stock_final"] += f["stock_final"]
        filas[fam(m["producto_id"])]["valor_stock"] += f["stock_final"] * costo(m["producto_id"])
    cap = [c for c in r["capacidad"] if c["periodo"] == periodo]
    return {"periodo": periodo, "en_horizonte": True,
            "familias": [{"familia": k, **{kk: round(vv, 1) for kk, vv in v.items()}} for k, v in sorted(filas.items())],
            "capacidad": cap, "alertas": [a for a in r["alertas"] if periodo in a["titulo"] or a["nivel"] == "CRITICA"][:10],
            **_nombres(r)}


# ─── Analítica de la demanda ─────────────────────────────────────────────────

@router.get("/analitica")
async def analitica(db: AsyncSession = Depends(get_db)):
    """Qué tan pronosticable es cada producto, qué método ganó y cuánto le
    aporta sobre el ingenuo, y los meses de demanda atípicos que distorsionan
    el pronóstico (un pedido extraordinario, un error de digitación)."""
    r = await _motor(db)
    series, atipicos, clases = [], [], defaultdict(int)
    for s in r["series"]:
        e = s["estadistico"]
        clases[e["clase"]["tipo"]] += 1
        series.append({"producto_id": s["producto_id"], "ubicacion_id": s["ubicacion_id"], "clase": e["clase"],
                       "metodo": e.get("nombre"), "wape": e.get("wape"), "sesgo": e.get("sesgo"), "fva_pct": e.get("fva_pct"),
                       "comparacion": e.get("comparacion", []), "meses": e.get("meses"), "suficiente": e.get("suficiente")})
        hist = list(s["historia"].items())
        vals = np.array([v for _, v in hist], float)
        if len(vals) >= 12:
            med = float(np.median(vals))
            mad = float(np.median(np.abs(vals - med)))
            if mad > 0:
                for per, v in hist:
                    z = 0.6745 * (v - med) / mad
                    if abs(z) > 3.5:
                        atipicos.append({"producto_id": s["producto_id"], "ubicacion_id": s["ubicacion_id"], "periodo": per,
                                         "cantidad": v, "mediana": med, "z": round(z, 1)})
    atipicos.sort(key=lambda a: -abs(a["z"]))
    return {"series": series, "clases": dict(clases), "atipicos": atipicos[:50], "kpis": r["kpis"], **_nombres(r)}
