"""
Lubricación — compartimentos, cargas, muestras y evaluación.

La toma de registros y el motor analítico. Los catálogos que esto consume están
en `lubricacion_gestion.py`, y el lector de boletines en `lubricacion.py`.

EL CICLO, EN UNA FRASE
Un activo tiene compartimentos; un compartimento tiene una carga viva a la vez;
la carga recibe rellenos y se muestrea; cada muestra se evalúa contra los
límites y produce una severidad; una severidad alta abre un diagnóstico, y el
diagnóstico se confirma o se desmiente cuando se interviene el equipo.

Ese último paso es el que casi ningún programa cierra, y es el que permite
medir si el análisis está sirviendo o solo generando papel.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.eam import EAMActivo
from app.infrastructure.models.lubricacion import (
    LubeTipoCompartimento, LubeProducto, LubeMarca, LubeAplicacion,
    LubeParametro, LubeLimite, LubeMotivoDrenaje, LubeModoFalla,
    LubeCompartimento, LubeCarga, LubeRelleno,
    LubeMuestra, LubeResultado, LubeDiagnostico,
)

router = APIRouter(prefix="/eam/lube", tags=["CMMS/EAM · Lubricación"])

MIN_MUESTRAS_ESTADISTICA = 20
ORDEN_ESTADO = {"NORMAL": 0, "MARGINAL": 1, "CRITICO": 2}


def _quien(u: Usuario) -> str:
    return getattr(u, "username", None) or getattr(u, "nombre", None) or "—"


# ══════════════════════════════════════════════════════════════════════════════
# COMPARTIMENTOS
# ══════════════════════════════════════════════════════════════════════════════

class CompartimentoIn(BaseModel):
    activo_id: int
    componente_id: Optional[int] = None
    tipo_compartimento_id: int
    codigo: str
    nombre: str
    capacidad_litros: Optional[float] = None
    producto_recomendado_id: Optional[int] = None
    meta_iso4406: Optional[str] = None
    frecuencia_muestreo: Optional[float] = None
    metodo_muestreo_id: Optional[int] = None
    tiene_puerto_muestreo: bool = False
    critico: bool = False
    observaciones: Optional[str] = None
    activo: bool = True


class CompartimentoOut(CompartimentoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo_codigo: Optional[str] = None
    activo_nombre: Optional[str] = None
    tipo_compartimento: Optional[str] = None
    unidad_vida: Optional[str] = None
    # Estado derivado de la carga viva, que es lo que se quiere ver en la lista.
    carga_id: Optional[int] = None
    producto_actual: Optional[str] = None
    vida_actual: Optional[float] = None
    vida_recomendada: Optional[float] = None
    severidad_ultima: Optional[str] = None
    fecha_ultima_muestra: Optional[datetime] = None


async def _enriquecer_compartimentos(db: AsyncSession, filas) -> List[Dict[str, Any]]:
    """Añade a cada compartimento el estado de su carga viva y su última muestra.

    Se hace en una pasada por lote y no con una consulta por fila: una flota de
    doscientos equipos con seis compartimentos cada uno son mil doscientas
    consultas, y la pantalla tardaría más en pintar que en cargarse.
    """
    salida = []
    ids = [c.id for c, *_ in filas]
    if not ids:
        return salida

    # Carga viva de cada compartimento.
    r = await db.execute(
        select(LubeCarga, LubeProducto.nombre)
        .outerjoin(LubeProducto, LubeProducto.id == LubeCarga.producto_id)
        .where(and_(LubeCarga.compartimento_id.in_(ids), LubeCarga.estado == "ACTIVA")))
    cargas = {c.compartimento_id: (c, prod) for c, prod in r.all()}

    # Última muestra con resultado de cada compartimento.
    r = await db.execute(
        select(LubeMuestra.compartimento_id, LubeMuestra.severidad,
               func.max(LubeMuestra.fecha_toma))
        .where(and_(LubeMuestra.compartimento_id.in_(ids),
                    LubeMuestra.estado != "ANULADA"))
        .group_by(LubeMuestra.compartimento_id, LubeMuestra.severidad))
    ultimas: Dict[int, Any] = {}
    for cid, sev, fecha in r.all():
        if cid not in ultimas or (fecha and fecha > ultimas[cid][1]):
            ultimas[cid] = (sev, fecha)

    # Vida recomendada del par producto × tipo, para el semáforo de cambio.
    r = await db.execute(select(LubeAplicacion).where(LubeAplicacion.activo.is_(True)))
    vidas = {(a.producto_id, a.tipo_compartimento_id): a.vida_recomendada
             for a in r.scalars().all()}

    # Último medidor conocido de cada carga viva. La vida del aceite se cuenta
    # contra la lectura del equipo, y esa lectura entra por dos vías: la muestra
    # y el relleno. Se toma la mayor de ambas porque cualquiera pudo ser la
    # última en registrarse.
    ids_carga = [c.id for c, _ in cargas.values()]
    medidores: Dict[int, float] = {}
    if ids_carga:
        for consulta in (
            select(LubeMuestra.carga_id, func.max(LubeMuestra.medidor_equipo))
            .where(and_(LubeMuestra.carga_id.in_(ids_carga),
                        LubeMuestra.medidor_equipo.isnot(None)))
            .group_by(LubeMuestra.carga_id),
            select(LubeRelleno.carga_id, func.max(LubeRelleno.medidor))
            .where(and_(LubeRelleno.carga_id.in_(ids_carga),
                        LubeRelleno.medidor.isnot(None)))
            .group_by(LubeRelleno.carga_id),
        ):
            for cid, valor in (await db.execute(consulta)).all():
                if valor is not None:
                    medidores[cid] = max(medidores.get(cid, valor), valor)

    for comp, act_codigo, act_nombre, tipo_nombre, unidad in filas:
        d = CompartimentoOut.model_validate(comp).model_dump()
        d.update(activo_codigo=act_codigo, activo_nombre=act_nombre,
                 tipo_compartimento=tipo_nombre, unidad_vida=unidad)
        carga, producto = cargas.get(comp.id, (None, None))
        if carga:
            d["carga_id"] = carga.id
            d["producto_actual"] = producto
            ultimo = medidores.get(carga.id)
            d["vida_actual"] = (round(ultimo - carga.medidor_inicio, 2)
                                if ultimo is not None and carga.medidor_inicio is not None
                                else None)
            d["vida_recomendada"] = vidas.get((carga.producto_id, comp.tipo_compartimento_id))
        sev, fecha = ultimas.get(comp.id, (None, None))
        d["severidad_ultima"], d["fecha_ultima_muestra"] = sev, fecha
        salida.append(d)
    return salida


@router.get("/compartimentos", response_model=List[CompartimentoOut])
async def listar_compartimentos(activo_id: Optional[int] = None,
                                tipo_compartimento_id: Optional[int] = None,
                                solo_criticos: bool = False,
                                db: AsyncSession = Depends(get_db)):
    q = (select(LubeCompartimento, EAMActivo.codigo, EAMActivo.nombre,
                LubeTipoCompartimento.nombre, LubeTipoCompartimento.unidad_vida)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .join(LubeTipoCompartimento,
               LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
         .where(LubeCompartimento.activo.is_(True))
         .order_by(EAMActivo.codigo, LubeCompartimento.codigo))
    if activo_id:
        q = q.where(LubeCompartimento.activo_id == activo_id)
    if tipo_compartimento_id:
        q = q.where(LubeCompartimento.tipo_compartimento_id == tipo_compartimento_id)
    if solo_criticos:
        q = q.where(LubeCompartimento.critico.is_(True))
    return await _enriquecer_compartimentos(db, (await db.execute(q)).all())


@router.post("/compartimentos", response_model=CompartimentoOut, status_code=201)
async def crear_compartimento(data: CompartimentoIn, db: AsyncSession = Depends(get_db)):
    if not await db.get(EAMActivo, data.activo_id):
        raise HTTPException(400, "Ese activo no existe")
    if not await db.get(LubeTipoCompartimento, data.tipo_compartimento_id):
        raise HTTPException(400, "Ese tipo de compartimento no existe")
    codigo = (data.codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(400, "El código del compartimento es obligatorio")
    ya = await db.execute(select(func.count()).select_from(LubeCompartimento).where(and_(
        LubeCompartimento.activo_id == data.activo_id,
        func.upper(LubeCompartimento.codigo) == codigo)))
    if ya.scalar():
        raise HTTPException(409, f"Ese activo ya tiene un compartimento «{codigo}»")
    obj = LubeCompartimento(**{**data.model_dump(), "codigo": codigo})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return CompartimentoOut.model_validate(obj)


@router.put("/compartimentos/{cid}", response_model=CompartimentoOut)
async def editar_compartimento(cid: int, data: CompartimentoIn,
                               db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeCompartimento, cid)
    if not obj:
        raise HTTPException(404, "Ese compartimento no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return CompartimentoOut.model_validate(obj)


@router.delete("/compartimentos/{cid}", status_code=204)
async def borrar_compartimento(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeCompartimento, cid)
    if not obj:
        raise HTTPException(404, "Ese compartimento no existe")
    obj.activo = False
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# CARGAS — la entidad con vida propia
# ══════════════════════════════════════════════════════════════════════════════

class CargaIn(BaseModel):
    compartimento_id: int
    producto_id: Optional[int] = None
    fecha_llenado: datetime
    medidor_inicio: Optional[float] = None
    volumen_litros: Optional[float] = None
    costo_aceite: Optional[float] = None
    costo_filtro: Optional[float] = None
    costo_mano_obra: Optional[float] = None
    orden_trabajo_id: Optional[int] = None
    observaciones: Optional[str] = None


class DrenajeIn(BaseModel):
    fecha_drenaje: datetime
    medidor_fin: Optional[float] = None
    motivo_drenaje_id: Optional[int] = None
    observaciones: Optional[str] = None


class CargaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    compartimento_id: int
    producto_id: Optional[int] = None
    fecha_llenado: datetime
    medidor_inicio: Optional[float] = None
    volumen_litros: Optional[float] = None
    costo_aceite: Optional[float] = None
    costo_filtro: Optional[float] = None
    costo_mano_obra: Optional[float] = None
    estado: str
    fecha_drenaje: Optional[datetime] = None
    medidor_fin: Optional[float] = None
    motivo_drenaje_id: Optional[int] = None
    vida_lograda: Optional[float] = None
    orden_trabajo_id: Optional[int] = None
    observaciones: Optional[str] = None
    registrado_por: Optional[str] = None
    producto: Optional[str] = None
    motivo: Optional[str] = None
    litros_repuestos: Optional[float] = None
    costo_total: Optional[float] = None
    costo_por_unidad_vida: Optional[float] = None


async def _carga_detallada(db: AsyncSession, carga: LubeCarga) -> Dict[str, Any]:
    d = CargaOut.model_validate(carga).model_dump()
    if carga.producto_id:
        p = await db.get(LubeProducto, carga.producto_id)
        d["producto"] = p.nombre if p else None
    if carga.motivo_drenaje_id:
        m = await db.get(LubeMotivoDrenaje, carga.motivo_drenaje_id)
        d["motivo"] = m.nombre if m else None

    r = await db.execute(select(func.coalesce(func.sum(LubeRelleno.litros), 0),
                                func.coalesce(func.sum(LubeRelleno.costo), 0))
                         .where(LubeRelleno.carga_id == carga.id))
    litros, costo_rellenos = r.one()
    d["litros_repuestos"] = float(litros or 0)

    total = sum(v or 0 for v in (carga.costo_aceite, carga.costo_filtro,
                                 carga.costo_mano_obra)) + float(costo_rellenos or 0)
    d["costo_total"] = total or None
    # El costo por hora lubricada es el número que hace comparable una carga con
    # otra. Sin vida lograda no se puede calcular todavía.
    if total and carga.vida_lograda:
        d["costo_por_unidad_vida"] = round(total / carga.vida_lograda, 2)
    return d


@router.get("/cargas", response_model=List[CargaOut])
async def listar_cargas(compartimento_id: Optional[int] = None,
                        estado: Optional[str] = None,
                        db: AsyncSession = Depends(get_db)):
    q = select(LubeCarga).order_by(desc(LubeCarga.fecha_llenado))
    if compartimento_id:
        q = q.where(LubeCarga.compartimento_id == compartimento_id)
    if estado:
        q = q.where(LubeCarga.estado == estado)
    return [await _carga_detallada(db, c) for c in (await db.execute(q)).scalars().all()]


@router.post("/cargas", response_model=CargaOut, status_code=201)
async def abrir_carga(data: CargaIn, db: AsyncSession = Depends(get_db),
                      usuario: Usuario = Depends(get_current_user)):
    """Abre una carga nueva. Si había una viva, la cierra automáticamente.

    Dos cargas activas en el mismo compartimento no significan nada físicamente
    —el aceite es uno solo—, y permitirlo rompería toda la trazabilidad de vida
    y de costo. Por eso el cierre es automático y no un paso que se pueda
    olvidar.
    """
    comp = await db.get(LubeCompartimento, data.compartimento_id)
    if not comp:
        raise HTTPException(400, "Ese compartimento no existe")

    r = await db.execute(select(LubeCarga).where(and_(
        LubeCarga.compartimento_id == data.compartimento_id,
        LubeCarga.estado == "ACTIVA")))
    anterior = r.scalar_one_or_none()
    if anterior:
        anterior.estado = "DRENADA"
        anterior.fecha_drenaje = data.fecha_llenado
        anterior.medidor_fin = data.medidor_inicio
        if data.medidor_inicio is not None and anterior.medidor_inicio is not None:
            anterior.vida_lograda = round(data.medidor_inicio - anterior.medidor_inicio, 2)

    obj = LubeCarga(**data.model_dump(), estado="ACTIVA", registrado_por=_quien(usuario))
    db.add(obj); await db.commit(); await db.refresh(obj)
    return await _carga_detallada(db, obj)


@router.post("/cargas/{cid}/drenar", response_model=CargaOut)
async def drenar_carga(cid: int, data: DrenajeIn, db: AsyncSession = Depends(get_db)):
    carga = await db.get(LubeCarga, cid)
    if not carga:
        raise HTTPException(404, "Esa carga no existe")
    if carga.estado == "DRENADA":
        raise HTTPException(409, "Esa carga ya fue drenada")
    carga.estado = "DRENADA"
    carga.fecha_drenaje = data.fecha_drenaje
    carga.medidor_fin = data.medidor_fin
    carga.motivo_drenaje_id = data.motivo_drenaje_id
    if data.observaciones:
        carga.observaciones = data.observaciones
    if data.medidor_fin is not None and carga.medidor_inicio is not None:
        carga.vida_lograda = round(data.medidor_fin - carga.medidor_inicio, 2)
    await db.commit(); await db.refresh(carga)
    return await _carga_detallada(db, carga)


class RellenoIn(BaseModel):
    carga_id: int
    fecha: datetime
    litros: float
    medidor: Optional[float] = None
    costo: Optional[float] = None
    motivo: Optional[str] = None


class RellenoOut(RellenoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    registrado_por: Optional[str] = None


@router.get("/rellenos", response_model=List[RellenoOut])
async def listar_rellenos(carga_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(LubeRelleno).where(LubeRelleno.carga_id == carga_id)
                         .order_by(LubeRelleno.fecha))
    return list(r.scalars().all())


@router.post("/rellenos", response_model=RellenoOut, status_code=201)
async def crear_relleno(data: RellenoIn, db: AsyncSession = Depends(get_db),
                        usuario: Usuario = Depends(get_current_user)):
    carga = await db.get(LubeCarga, data.carga_id)
    if not carga:
        raise HTTPException(400, "Esa carga no existe")
    if carga.estado != "ACTIVA":
        raise HTTPException(409, "No se puede rellenar una carga ya drenada")
    if data.litros <= 0:
        raise HTTPException(400, "Los litros deben ser mayores que cero")
    obj = LubeRelleno(**data.model_dump(), registrado_por=_quien(usuario))
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# EL EVALUADOR
# ══════════════════════════════════════════════════════════════════════════════

def _peor(a: str, b: str) -> str:
    return a if ORDEN_ESTADO.get(a, 0) >= ORDEN_ESTADO.get(b, 0) else b


def _contra_umbrales(valor: float, lim: LubeLimite) -> str:
    """Compara un valor contra los cuatro umbrales de un límite.

    Se miran mínimos y máximos siempre que estén definidos, no solo el máximo:
    en el hierro lo peligroso es que suba, pero en el TBN lo peligroso es que
    baje —el aceite perdió su reserva alcalina— y en la viscosidad lo es
    alejarse en cualquier dirección.
    """
    if lim.critico_max is not None and valor > lim.critico_max:
        return "CRITICO"
    if lim.critico_min is not None and valor < lim.critico_min:
        return "CRITICO"
    if lim.marginal_max is not None and valor > lim.marginal_max:
        return "MARGINAL"
    if lim.marginal_min is not None and valor < lim.marginal_min:
        return "MARGINAL"
    return "NORMAL"


async def _limites_por_tipo(db: AsyncSession, parametro_id: int,
                            comp: LubeCompartimento,
                            producto_id: Optional[int]) -> Dict[str, LubeLimite]:
    """El límite más específico de cada clase, para un parámetro.

    La especificidad va de lo particular a lo general, y el primero que exista
    manda: un equipo que legítimamente corre con más hierro que el resto de la
    flota puede tener su propio límite sin que haya que relajar el de todos.
    """
    r = await db.execute(select(LubeLimite).where(and_(
        LubeLimite.parametro_id == parametro_id, LubeLimite.activo.is_(True))))
    candidatos = list(r.scalars().all())

    def rango(l: LubeLimite) -> int:
        if l.compartimento_id == comp.id:
            return 0
        if l.producto_id and producto_id and l.producto_id == producto_id \
                and l.tipo_compartimento_id == comp.tipo_compartimento_id:
            return 1
        if l.tipo_compartimento_id == comp.tipo_compartimento_id and not l.producto_id:
            return 2
        if l.tipo_compartimento_id is None and l.compartimento_id is None \
                and l.producto_id is None:
            return 3
        return 99   # no aplica a este compartimento

    elegidos: Dict[str, LubeLimite] = {}
    for lim in sorted(candidatos, key=rango):
        if rango(lim) == 99:
            continue
        elegidos.setdefault(lim.tipo, lim)
    return elegidos


async def _estadistico(db: AsyncSession, parametro_id: int,
                       tipo_compartimento_id: int) -> Optional[Dict[str, float]]:
    """Media y desvío de la flota para ese parámetro y esa familia.

    Se calcula sobre la marcha en vez de guardarse: la referencia se mueve con
    cada muestra nueva, y un número congelado envejece mal. Debajo del mínimo de
    muestras se devuelve None a propósito —con poca historia el desvío es ruido
    y solo produce alarmas falsas, que es la forma más rápida de que la gente
    deje de creerle al sistema.
    """
    r = await db.execute(
        select(func.avg(LubeResultado.valor), func.stddev_samp(LubeResultado.valor),
               func.count(LubeResultado.id))
        .join(LubeMuestra, LubeMuestra.id == LubeResultado.muestra_id)
        .join(LubeCompartimento, LubeCompartimento.id == LubeMuestra.compartimento_id)
        .where(and_(LubeResultado.parametro_id == parametro_id,
                    LubeCompartimento.tipo_compartimento_id == tipo_compartimento_id,
                    LubeResultado.valor.isnot(None),
                    LubeMuestra.estado != "ANULADA")))
    media, desvio, n = r.one()
    if not n or n < MIN_MUESTRAS_ESTADISTICA or media is None or not desvio:
        return None
    return {"media": float(media), "desvio": float(desvio), "n": int(n)}


async def _muestra_anterior(db: AsyncSession, muestra: LubeMuestra) -> Optional[LubeMuestra]:
    """La muestra previa de la MISMA carga.

    De la misma carga y no del mismo compartimento: al cambiar el aceite los
    metales vuelven a cero, y comparar contra la carga anterior daría una
    «mejora» espectacular que no significa nada.
    """
    if not muestra.carga_id:
        return None
    r = await db.execute(
        select(LubeMuestra).where(and_(
            LubeMuestra.carga_id == muestra.carga_id,
            LubeMuestra.id != muestra.id,
            LubeMuestra.fecha_toma < muestra.fecha_toma,
            LubeMuestra.estado != "ANULADA"))
        .order_by(desc(LubeMuestra.fecha_toma)).limit(1))
    return r.scalar_one_or_none()


async def evaluar_muestra(db: AsyncSession, muestra: LubeMuestra) -> Dict[str, Any]:
    """Evalúa todos los resultados de una muestra y fija su severidad."""
    comp = await db.get(LubeCompartimento, muestra.compartimento_id)
    if not comp:
        raise HTTPException(400, "La muestra apunta a un compartimento que no existe")
    carga = await db.get(LubeCarga, muestra.carga_id) if muestra.carga_id else None
    producto_id = carga.producto_id if carga else None

    r = await db.execute(select(LubeResultado).where(LubeResultado.muestra_id == muestra.id))
    resultados = list(r.scalars().all())

    anterior = await _muestra_anterior(db, muestra)
    previos: Dict[int, float] = {}
    if anterior:
        r = await db.execute(select(LubeResultado).where(
            LubeResultado.muestra_id == anterior.id))
        previos = {x.parametro_id: x.valor for x in r.scalars().all() if x.valor is not None}

    detalle = []
    for res in resultados:
        if res.valor is None:
            res.estado, res.disparo_por, res.tasa_cambio = "NORMAL", None, None
            continue

        limites = await _limites_por_tipo(db, res.parametro_id, comp, producto_id)
        estado, disparo = "NORMAL", None

        # 1) Absoluto.
        if "ABSOLUTO" in limites:
            e = _contra_umbrales(res.valor, limites["ABSOLUTO"])
            if ORDEN_ESTADO[e] > ORDEN_ESTADO[estado]:
                estado, disparo = e, "ABSOLUTO"

        # 2) Tasa de cambio, normalizada por vida del aceite.
        tasa = None
        anterior_valor = previos.get(res.parametro_id)
        if (anterior_valor is not None and anterior and muestra.horas_aceite is not None
                and anterior.horas_aceite is not None):
            delta = muestra.horas_aceite - anterior.horas_aceite
            if delta > 0:
                tasa = round((res.valor - anterior_valor) / delta * 100, 3)
                if "TASA_CAMBIO" in limites:
                    e = _contra_umbrales(tasa, limites["TASA_CAMBIO"])
                    if ORDEN_ESTADO[e] > ORDEN_ESTADO[estado]:
                        estado, disparo = e, "TASA_CAMBIO"
        res.tasa_cambio = tasa

        # 3) Estadístico: el guardado manda; si no, se calcula de la flota.
        if "ESTADISTICO" in limites:
            e = _contra_umbrales(res.valor, limites["ESTADISTICO"])
            if ORDEN_ESTADO[e] > ORDEN_ESTADO[estado]:
                estado, disparo = e, "ESTADISTICO"
        else:
            est = await _estadistico(db, res.parametro_id, comp.tipo_compartimento_id)
            if est:
                if res.valor > est["media"] + 3 * est["desvio"]:
                    estado, disparo = _peor(estado, "CRITICO"), "ESTADISTICO"
                elif res.valor > est["media"] + 2 * est["desvio"]:
                    if ORDEN_ESTADO["MARGINAL"] > ORDEN_ESTADO[estado]:
                        estado, disparo = "MARGINAL", "ESTADISTICO"

        res.estado, res.disparo_por = estado, disparo
        detalle.append({"parametro_id": res.parametro_id, "valor": res.valor,
                        "estado": estado, "disparo_por": disparo, "tasa_cambio": tasa})

    criticos = sum(1 for d in detalle if d["estado"] == "CRITICO")
    marginales = sum(1 for d in detalle if d["estado"] == "MARGINAL")

    # Un solo parámetro crítico es una alerta; dos o más apuntando a la vez son
    # un patrón, y ahí la máquina no debería seguir trabajando sin revisión.
    if criticos >= 2:
        severidad = "ACCION_INMEDIATA"
    elif criticos == 1:
        severidad = "CRITICO"
    elif marginales:
        severidad = "MARGINAL"
    else:
        severidad = "NORMAL"

    if not muestra.severidad_manual:
        muestra.severidad = severidad
    await db.commit()
    return {"severidad": severidad, "criticos": criticos, "marginales": marginales,
            "comparada_con": anterior.numero if anterior else None, "detalle": detalle}


# ══════════════════════════════════════════════════════════════════════════════
# MUESTRAS
# ══════════════════════════════════════════════════════════════════════════════

class ResultadoIn(BaseModel):
    # Se acepta por código o por id: el lector de boletines devuelve códigos.
    parametro_id: Optional[int] = None
    codigo: Optional[str] = None
    valor: Optional[float] = None
    valor_texto: Optional[str] = None


class MuestraIn(BaseModel):
    numero: str
    compartimento_id: int
    carga_id: Optional[int] = None
    fecha_toma: datetime
    fecha_recepcion: Optional[datetime] = None
    fecha_resultado: Optional[datetime] = None
    medidor_equipo: Optional[float] = None
    horas_aceite: Optional[float] = None
    laboratorio_id: Optional[int] = None
    metodo_id: Optional[int] = None
    archivo_boletin: Optional[str] = None
    observaciones: Optional[str] = None
    resultados: List[ResultadoIn] = []


class MuestraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero: str
    compartimento_id: int
    carga_id: Optional[int] = None
    fecha_toma: datetime
    fecha_resultado: Optional[datetime] = None
    medidor_equipo: Optional[float] = None
    horas_aceite: Optional[float] = None
    laboratorio_id: Optional[int] = None
    metodo_id: Optional[int] = None
    severidad: str
    severidad_manual: bool
    estado: str
    observaciones: Optional[str] = None
    registrado_por: Optional[str] = None
    activo_codigo: Optional[str] = None
    compartimento: Optional[str] = None
    resultados: List[Dict[str, Any]] = []


async def _resolver_parametros(db: AsyncSession, filas: List[ResultadoIn]) -> List[Dict[str, Any]]:
    """Convierte códigos a identificadores y descarta lo que no esté catalogado.

    Se ignora en silencio lo desconocido en vez de fallar: un boletín trae
    campos que no son mediciones (nombre del equipo, fecha) y hacer fallar la
    carga entera por eso obligaría a limpiar el archivo a mano.
    """
    r = await db.execute(select(LubeParametro).where(LubeParametro.activo.is_(True)))
    por_codigo = {p.codigo.lower(): p for p in r.scalars().all()}
    por_id = {p.id: p for p in por_codigo.values()}

    salida = []
    for f in filas:
        p = por_id.get(f.parametro_id) if f.parametro_id else \
            por_codigo.get((f.codigo or "").strip().lower())
        if not p:
            continue
        if f.valor is None and not f.valor_texto:
            continue
        salida.append({"parametro_id": p.id, "valor": f.valor, "valor_texto": f.valor_texto})
    return salida


@router.get("/muestras", response_model=List[MuestraOut])
async def listar_muestras(compartimento_id: Optional[int] = None,
                          activo_id: Optional[int] = None,
                          carga_id: Optional[int] = None,
                          severidad: Optional[str] = None,
                          limite: int = Query(200, le=1000),
                          db: AsyncSession = Depends(get_db)):
    q = (select(LubeMuestra, EAMActivo.codigo, LubeCompartimento.nombre)
         .join(LubeCompartimento, LubeCompartimento.id == LubeMuestra.compartimento_id)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .order_by(desc(LubeMuestra.fecha_toma)).limit(limite))
    if compartimento_id:
        q = q.where(LubeMuestra.compartimento_id == compartimento_id)
    if activo_id:
        q = q.where(LubeCompartimento.activo_id == activo_id)
    if carga_id:
        q = q.where(LubeMuestra.carga_id == carga_id)
    if severidad:
        q = q.where(LubeMuestra.severidad == severidad)

    salida = []
    for m, act, comp in (await db.execute(q)).all():
        d = MuestraOut.model_validate(m).model_dump()
        d["activo_codigo"], d["compartimento"] = act, comp
        salida.append(d)
    return salida


@router.get("/muestras/{mid}", response_model=MuestraOut)
async def obtener_muestra(mid: int, db: AsyncSession = Depends(get_db)):
    m = await db.get(LubeMuestra, mid)
    if not m:
        raise HTTPException(404, "Esa muestra no existe")
    comp = await db.get(LubeCompartimento, m.compartimento_id)
    act = await db.get(EAMActivo, comp.activo_id) if comp else None

    r = await db.execute(
        select(LubeResultado, LubeParametro)
        .join(LubeParametro, LubeParametro.id == LubeResultado.parametro_id)
        .where(LubeResultado.muestra_id == mid)
        .order_by(LubeParametro.orden))
    d = MuestraOut.model_validate(m).model_dump()
    d["activo_codigo"] = act.codigo if act else None
    d["compartimento"] = comp.nombre if comp else None
    d["resultados"] = [{
        "id": res.id, "parametro_id": par.id, "codigo": par.codigo, "nombre": par.nombre,
        "unidad": par.unidad, "grupo": par.grupo, "origen_probable": par.origen_probable,
        "valor": res.valor, "valor_texto": res.valor_texto,
        "estado": res.estado, "tasa_cambio": res.tasa_cambio,
        "disparo_por": res.disparo_por,
    } for res, par in r.all()]
    return d


@router.post("/muestras", response_model=Dict[str, Any], status_code=201)
async def crear_muestra(data: MuestraIn, db: AsyncSession = Depends(get_db),
                        usuario: Usuario = Depends(get_current_user)):
    """Registra una muestra con sus resultados y la evalúa de una vez."""
    comp = await db.get(LubeCompartimento, data.compartimento_id)
    if not comp:
        raise HTTPException(400, "Ese compartimento no existe")
    numero = (data.numero or "").strip()
    if not numero:
        raise HTTPException(400, "El número de muestra es obligatorio")
    ya = await db.execute(select(func.count()).select_from(LubeMuestra)
                          .where(func.lower(LubeMuestra.numero) == numero.lower()))
    if ya.scalar():
        raise HTTPException(409, f"Ya hay una muestra con el número «{numero}»")

    # Si no dicen a qué carga pertenece, se asume la viva del compartimento.
    carga_id = data.carga_id
    carga = None
    if carga_id:
        carga = await db.get(LubeCarga, carga_id)
    else:
        r = await db.execute(select(LubeCarga).where(and_(
            LubeCarga.compartimento_id == comp.id, LubeCarga.estado == "ACTIVA")))
        carga = r.scalar_one_or_none()
        carga_id = carga.id if carga else None

    # Las horas del aceite se derivan si no las mandan: es el dato sin el cual
    # la muestra no se puede interpretar, así que se calcula en vez de perderlo.
    horas = data.horas_aceite
    if horas is None and carga and carga.medidor_inicio is not None \
            and data.medidor_equipo is not None:
        horas = round(data.medidor_equipo - carga.medidor_inicio, 2)

    # Se excluye todo lo que se pasa aparte más abajo; si `numero` siguiera acá
    # llegaría dos veces al constructor.
    campos = data.model_dump(exclude={"resultados", "carga_id", "horas_aceite", "numero"})
    muestra = LubeMuestra(**campos, carga_id=carga_id, horas_aceite=horas,
                          numero=numero, registrado_por=_quien(usuario),
                          estado="CON_RESULTADO" if data.resultados else "TOMADA")
    db.add(muestra); await db.commit(); await db.refresh(muestra)

    for fila in await _resolver_parametros(db, data.resultados):
        db.add(LubeResultado(muestra_id=muestra.id, **fila))
    await db.commit()

    evaluacion = await evaluar_muestra(db, muestra) if data.resultados else None
    return {"id": muestra.id, "numero": muestra.numero, "horas_aceite": horas,
            "carga_id": carga_id, "evaluacion": evaluacion}


@router.post("/muestras/{mid}/reevaluar", response_model=Dict[str, Any])
async def reevaluar(mid: int, db: AsyncSession = Depends(get_db)):
    """Vuelve a evaluar una muestra. Se usa al cambiar los límites."""
    m = await db.get(LubeMuestra, mid)
    if not m:
        raise HTTPException(404, "Esa muestra no existe")
    m.severidad_manual = False
    return await evaluar_muestra(db, m)


class SeveridadIn(BaseModel):
    severidad: str
    nota: Optional[str] = None


@router.put("/muestras/{mid}/severidad", response_model=Dict[str, Any])
async def fijar_severidad(mid: int, data: SeveridadIn, db: AsyncSession = Depends(get_db)):
    """Permite que un analista corrija la severidad calculada.

    El motor ordena y prioriza, pero la última palabra de un diagnóstico es de
    una persona. Queda marcada como manual para que una reevaluación posterior
    no la pise sin que nadie se entere.
    """
    m = await db.get(LubeMuestra, mid)
    if not m:
        raise HTTPException(404, "Esa muestra no existe")
    if data.severidad not in ("NORMAL", "MARGINAL", "CRITICO", "ACCION_INMEDIATA"):
        raise HTTPException(400, "Severidad no válida")
    m.severidad, m.severidad_manual = data.severidad, True
    if data.nota:
        m.observaciones = ((m.observaciones or "") + f"\n[Severidad manual] {data.nota}").strip()
    await db.commit()
    return {"id": m.id, "severidad": m.severidad, "manual": True}


@router.get("/muestras/{mid}/tendencia", response_model=Dict[str, Any])
async def tendencia(mid: int, db: AsyncSession = Depends(get_db)):
    """Serie histórica de los parámetros de la carga a la que pertenece la muestra."""
    m = await db.get(LubeMuestra, mid)
    if not m:
        raise HTTPException(404, "Esa muestra no existe")
    if not m.carga_id:
        return {"muestras": [], "series": {}}

    r = await db.execute(select(LubeMuestra).where(and_(
        LubeMuestra.carga_id == m.carga_id, LubeMuestra.estado != "ANULADA"))
        .order_by(LubeMuestra.fecha_toma))
    muestras = list(r.scalars().all())
    ids = [x.id for x in muestras]
    if not ids:
        return {"muestras": [], "series": {}}

    r = await db.execute(
        select(LubeResultado, LubeParametro.codigo, LubeParametro.nombre, LubeParametro.unidad)
        .join(LubeParametro, LubeParametro.id == LubeResultado.parametro_id)
        .where(LubeResultado.muestra_id.in_(ids)))
    series: Dict[str, Dict[str, Any]] = {}
    for res, codigo, nombre, unidad in r.all():
        s = series.setdefault(codigo, {"nombre": nombre, "unidad": unidad, "puntos": []})
        s["puntos"].append({"muestra_id": res.muestra_id, "valor": res.valor,
                            "estado": res.estado})
    return {
        "muestras": [{"id": x.id, "numero": x.numero, "fecha": x.fecha_toma,
                      "horas_aceite": x.horas_aceite, "severidad": x.severidad}
                     for x in muestras],
        "series": series,
    }


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNÓSTICO — el cierre del ciclo
# ══════════════════════════════════════════════════════════════════════════════

class DiagnosticoIn(BaseModel):
    muestra_id: int
    modo_falla_id: Optional[int] = None
    severidad: str = "NORMAL"
    conclusion: Optional[str] = None
    recomendacion: Optional[str] = None
    orden_trabajo_id: Optional[int] = None
    causa_raiz_id: Optional[int] = None
    analista: Optional[str] = None


class VerificacionIn(BaseModel):
    verificacion: str          # CONFIRMADO | DESMENTIDO
    hallazgo: Optional[str] = None


class DiagnosticoOut(DiagnosticoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    verificacion: str
    hallazgo: Optional[str] = None
    automatico: bool = False


@router.get("/diagnosticos", response_model=List[DiagnosticoOut])
async def listar_diagnosticos(muestra_id: Optional[int] = None,
                              verificacion: Optional[str] = None,
                              db: AsyncSession = Depends(get_db)):
    q = select(LubeDiagnostico).order_by(desc(LubeDiagnostico.id))
    if muestra_id:
        q = q.where(LubeDiagnostico.muestra_id == muestra_id)
    if verificacion:
        q = q.where(LubeDiagnostico.verificacion == verificacion)
    return list((await db.execute(q)).scalars().all())


@router.post("/diagnosticos", response_model=DiagnosticoOut, status_code=201)
async def crear_diagnostico(data: DiagnosticoIn, db: AsyncSession = Depends(get_db),
                            usuario: Usuario = Depends(get_current_user)):
    if not await db.get(LubeMuestra, data.muestra_id):
        raise HTTPException(400, "Esa muestra no existe")
    obj = LubeDiagnostico(**{**data.model_dump(),
                             "analista": data.analista or _quien(usuario)})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/diagnosticos/{did}/verificar", response_model=DiagnosticoOut)
async def verificar(did: int, data: VerificacionIn, db: AsyncSession = Depends(get_db)):
    """Registra qué se encontró al intervenir.

    Es el paso que cierra el ciclo y el que casi ningún programa hace. Sin él no
    se puede responder si el análisis está acertando, y un programa que no se
    mide termina siendo un gasto que nadie defiende.
    """
    obj = await db.get(LubeDiagnostico, did)
    if not obj:
        raise HTTPException(404, "Ese diagnóstico no existe")
    if data.verificacion not in ("CONFIRMADO", "DESMENTIDO", "PENDIENTE"):
        raise HTTPException(400, "La verificación debe ser CONFIRMADO, DESMENTIDO o PENDIENTE")
    obj.verificacion = data.verificacion
    obj.hallazgo = data.hallazgo
    obj.fecha_verificacion = datetime.utcnow().date()
    await db.commit(); await db.refresh(obj)
    return obj
