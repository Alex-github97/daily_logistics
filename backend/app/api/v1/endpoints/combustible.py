"""
Combustible — transacciones, rendimiento y metas de km/galón.

CÓMO SE CALCULA EL RENDIMIENTO, Y POR QUÉ ASÍ
El método es «tanque a tanque», que es el único confiable:

    rendimiento = (odómetro actual − odómetro del último tanqueo lleno)
                  ÷ (galones cargados desde ese tanqueo, éste incluido)

Solo entre dos tanques llenos se sabe cuánto combustible consumió realmente la
distancia recorrida. Dividir los galones de un tanqueo por los kilómetros desde
el tanqueo anterior —sin exigir que ambos sean llenos— da números que suben y
bajan según cuánto quedaba en el tanque, y una flota entera tomando decisiones
sobre ese ruido es peor que no medir.

Por eso los tanqueos parciales no producen rendimiento: se acumulan y entran al
cálculo del siguiente tanque lleno.

LAS METAS
Se declaran por jerarquía —tipo → marca → línea → marca de motor → línea de
motor— y manda la más específica. Un tanqueo por debajo de su meta, descontada
la tolerancia, genera alerta.

La meta y el resultado se congelan en el registro: las metas cambian, y un
tanqueo de hace un año tiene que seguir explicando por qué alertó o no.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_, or_, desc, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.eam import (
    EAMActivo, EAMRegistroCombustible, EAMMetaRendimiento, EAMTipoCombustible,
)

router = APIRouter(prefix="/eam/combustible", tags=["CMMS/EAM · Combustible"])

# Factor exacto de la conversión. Se declara acá y no se reparte por el código
# para que exista un solo sitio donde mirarlo.
LITROS_POR_GALON = 3.785411784


def _a_galones(cantidad: float, unidad: str) -> float:
    return cantidad / LITROS_POR_GALON if (unidad or "GALON").upper() == "LITRO" else cantidad


def _quien(u: Usuario) -> str:
    return getattr(u, "username", None) or getattr(u, "nombre", None) or "—"


# ══════════════════════════════════════════════════════════════════════════════
# METAS
# ══════════════════════════════════════════════════════════════════════════════

class MetaIn(BaseModel):
    tipo_activo: Optional[str] = None
    marca: Optional[str] = None
    linea: Optional[str] = None
    motor_marca: Optional[str] = None
    motor_linea: Optional[str] = None
    meta_km_gal: float
    tolerancia_pct: float = 5
    tipo_combustible: Optional[str] = None
    nota: Optional[str] = None
    activo: bool = True


class MetaOut(MetaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # Cuántos niveles declara. Es lo que decide cuál gana cuando varias aplican.
    especificidad: Optional[int] = None


def _especificidad(m: EAMMetaRendimiento) -> int:
    return sum(1 for v in (m.tipo_activo, m.marca, m.linea,
                           m.motor_marca, m.motor_linea) if v)


@router.get("/metas", response_model=List[MetaOut])
async def listar_metas(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMMetaRendimiento)
                         .where(EAMMetaRendimiento.activo.is_(True)))
    filas = sorted(r.scalars().all(), key=lambda m: (-_especificidad(m), m.id))
    salida = []
    for m in filas:
        d = MetaOut.model_validate(m).model_dump()
        d["especificidad"] = _especificidad(m)
        salida.append(d)
    return salida


@router.post("/metas", response_model=MetaOut, status_code=201)
async def crear_meta(data: MetaIn, db: AsyncSession = Depends(get_db)):
    if data.meta_km_gal <= 0:
        raise HTTPException(400, "La meta debe ser mayor que cero")
    if not any((data.tipo_activo, data.marca, data.linea,
                data.motor_marca, data.motor_linea)):
        raise HTTPException(
            400, "Declare al menos un nivel: tipo de activo, marca, línea o motor. Una meta "
                 "sin ámbito se aplicaría a toda la flota por igual, que es justo lo que se "
                 "quiere evitar.")
    obj = EAMMetaRendimiento(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    d = MetaOut.model_validate(obj).model_dump()
    d["especificidad"] = _especificidad(obj)
    return d


@router.put("/metas/{mid}", response_model=MetaOut)
async def editar_meta(mid: int, data: MetaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMetaRendimiento, mid)
    if not obj:
        raise HTTPException(404, "Esa meta no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    d = MetaOut.model_validate(obj).model_dump()
    d["especificidad"] = _especificidad(obj)
    return d


@router.delete("/metas/{mid}", status_code=204)
async def borrar_meta(mid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMetaRendimiento, mid)
    if not obj:
        raise HTTPException(404, "Esa meta no existe")
    obj.activo = False
    await db.commit()


async def _meta_de(db: AsyncSession, activo: EAMActivo,
                   tipo_combustible: Optional[str] = None) -> Optional[EAMMetaRendimiento]:
    """La meta que aplica a un activo. Gana la más específica.

    Un nivel vacío en la meta significa «cualquiera»; un nivel con valor tiene
    que coincidir. Entre las que aplican se escoge la que declare más niveles:
    una meta para «Kenworth T800 con motor Cummins» debe pesar más que una para
    todos los tractocamiones.
    """
    r = await db.execute(select(EAMMetaRendimiento)
                         .where(EAMMetaRendimiento.activo.is_(True)))
    candidatas = []
    for m in r.scalars().all():
        if m.tipo_activo and m.tipo_activo != activo.tipo_activo:
            continue
        if m.marca and m.marca != activo.marca:
            continue
        if m.linea and m.linea != activo.linea:
            continue
        if m.motor_marca and m.motor_marca != activo.motor_marca:
            continue
        if m.motor_linea and m.motor_linea != activo.motor_linea:
            continue
        if m.tipo_combustible and tipo_combustible and m.tipo_combustible != tipo_combustible:
            continue
        candidatas.append(m)
    if not candidatas:
        return None
    return sorted(candidatas, key=lambda m: (-_especificidad(m), m.id))[0]


# ══════════════════════════════════════════════════════════════════════════════
# TRANSACCIONES
# ══════════════════════════════════════════════════════════════════════════════

class RegistroIn(BaseModel):
    activo_id: int
    fecha: datetime
    tipo_combustible: Optional[str] = None
    cantidad: float
    unidad: str = "GALON"
    precio_unitario: Optional[float] = None
    iva_pct: float = 0
    odometro: Optional[float] = None
    horometro: Optional[float] = None
    tanque_lleno: bool = True
    proveedor: Optional[str] = None
    factura: Optional[str] = None
    conductor: Optional[str] = None
    estacion: Optional[str] = None
    observaciones: Optional[str] = None


class RegistroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo_id: int
    fecha: datetime
    tipo_combustible: Optional[str] = None
    cantidad: float
    unidad: str
    precio_unitario: Optional[float] = None
    subtotal: Optional[float] = None
    iva_pct: Optional[float] = None
    iva_valor: Optional[float] = None
    costo_total: Optional[float] = None
    odometro: Optional[float] = None
    horometro: Optional[float] = None
    km_recorridos: Optional[float] = None
    rendimiento: Optional[float] = None
    tanque_lleno: bool
    meta_km_gal: Optional[float] = None
    cumple_meta: Optional[bool] = None
    desviacion_pct: Optional[float] = None
    proveedor: Optional[str] = None
    factura: Optional[str] = None
    conductor: Optional[str] = None
    estacion: Optional[str] = None
    observaciones: Optional[str] = None
    registrado_por: Optional[str] = None
    # Del activo, para no pedir una consulta por fila en la pantalla.
    placa: Optional[str] = None
    activo_codigo: Optional[str] = None
    activo_nombre: Optional[str] = None
    marca: Optional[str] = None
    linea: Optional[str] = None


def _calcular_importe(data: RegistroIn) -> Dict[str, Optional[float]]:
    """Subtotal, IVA y total a partir del precio unitario.

    Se calcula acá y no en la pantalla porque el total es un dato contable: si
    lo arma el navegador, dos versiones distintas del frontend pueden guardar
    cifras distintas para la misma compra.
    """
    if data.precio_unitario is None:
        return {"subtotal": None, "iva_valor": None, "costo_total": None}
    subtotal = round(data.cantidad * data.precio_unitario, 2)
    iva = round(subtotal * (data.iva_pct or 0) / 100, 2)
    return {"subtotal": subtotal, "iva_valor": iva,
            "costo_total": round(subtotal + iva, 2)}


async def _rendimiento_tanque_a_tanque(
        db: AsyncSession, activo_id: int, fecha: datetime,
        odometro: Optional[float], galones: float,
        tanque_lleno: bool) -> Dict[str, Optional[float]]:
    """Kilómetros y km/gal desde el último tanqueo lleno.

    Devuelve todo en None cuando no se puede calcular con honestidad: sin
    odómetro, sin tanqueo lleno anterior, o si el odómetro no avanzó. Inventar
    un rendimiento en esos casos contamina el promedio de toda la flota.
    """
    vacio = {"km_recorridos": None, "rendimiento": None}
    if not tanque_lleno or odometro is None:
        return vacio

    r = await db.execute(
        select(EAMRegistroCombustible)
        .where(and_(EAMRegistroCombustible.activo_id == activo_id,
                    EAMRegistroCombustible.fecha < fecha,
                    EAMRegistroCombustible.tanque_lleno.is_(True),
                    EAMRegistroCombustible.odometro.isnot(None)))
        .order_by(desc(EAMRegistroCombustible.fecha)).limit(1))
    anterior = r.scalar_one_or_none()
    if not anterior or anterior.odometro is None:
        return vacio

    km = odometro - anterior.odometro
    if km <= 0:
        return vacio

    # Los tanqueos parciales entre ambos tanques llenos también se consumieron
    # en esa distancia: si se ignoran, el rendimiento sale inflado.
    r = await db.execute(
        select(EAMRegistroCombustible)
        .where(and_(EAMRegistroCombustible.activo_id == activo_id,
                    EAMRegistroCombustible.fecha > anterior.fecha,
                    EAMRegistroCombustible.fecha < fecha)))
    intermedios = sum(_a_galones(x.cantidad, x.unidad) for x in r.scalars().all())

    total_galones = galones + intermedios
    if total_galones <= 0:
        return vacio
    return {"km_recorridos": round(km, 1),
            "rendimiento": round(km / total_galones, 2)}


@router.get("/registros", response_model=List[RegistroOut])
async def listar(activo_id: Optional[int] = None, marca: Optional[str] = None,
                 desde: Optional[datetime] = None, hasta: Optional[datetime] = None,
                 solo_alertas: bool = False, limite: int = Query(300, le=2000),
                 db: AsyncSession = Depends(get_db)):
    q = (select(EAMRegistroCombustible, EAMActivo)
         .join(EAMActivo, EAMActivo.id == EAMRegistroCombustible.activo_id)
         .order_by(desc(EAMRegistroCombustible.fecha)).limit(limite))
    if activo_id:
        q = q.where(EAMRegistroCombustible.activo_id == activo_id)
    if marca:
        q = q.where(EAMActivo.marca == marca)
    if desde:
        q = q.where(EAMRegistroCombustible.fecha >= desde)
    if hasta:
        q = q.where(EAMRegistroCombustible.fecha <= hasta)
    if solo_alertas:
        q = q.where(EAMRegistroCombustible.cumple_meta.is_(False))

    salida = []
    for reg, activo in (await db.execute(q)).all():
        d = RegistroOut.model_validate(reg).model_dump()
        d.update(placa=activo.placa, activo_codigo=activo.codigo,
                 activo_nombre=activo.nombre, marca=activo.marca, linea=activo.linea)
        salida.append(d)
    return salida


@router.post("/registros", response_model=RegistroOut, status_code=201)
async def crear(data: RegistroIn, db: AsyncSession = Depends(get_db),
                usuario: Usuario = Depends(get_current_user)):
    activo = await db.get(EAMActivo, data.activo_id)
    if not activo:
        raise HTTPException(400, "Ese activo no existe")
    if data.cantidad <= 0:
        raise HTTPException(400, "La cantidad debe ser mayor que cero")
    if data.unidad.upper() not in ("GALON", "LITRO"):
        raise HTTPException(400, "La unidad debe ser GALON o LITRO")

    # Un odómetro que retrocede casi siempre es un dedazo, y arruina el
    # rendimiento de este tanqueo y del siguiente. Se rechaza al capturarlo,
    # que es cuando la persona todavía tiene el recibo en la mano.
    if data.odometro is not None:
        r = await db.execute(
            select(func.max(EAMRegistroCombustible.odometro))
            .where(and_(EAMRegistroCombustible.activo_id == data.activo_id,
                        EAMRegistroCombustible.fecha <= data.fecha)))
        tope = r.scalar()
        if tope is not None and data.odometro < tope:
            raise HTTPException(
                400, f"El odómetro ({data.odometro:,.0f}) es menor que el último registrado "
                     f"({tope:,.0f}). Verifique la lectura.")

    galones = _a_galones(data.cantidad, data.unidad)
    importe = _calcular_importe(data)
    calculo = await _rendimiento_tanque_a_tanque(
        db, data.activo_id, data.fecha, data.odometro, galones, data.tanque_lleno)

    # Meta y cumplimiento, congelados en el registro.
    meta = await _meta_de(db, activo, data.tipo_combustible)
    meta_valor = meta.meta_km_gal if meta else None
    cumple = None
    desviacion = None
    if meta and calculo["rendimiento"] is not None:
        piso = meta.meta_km_gal * (1 - (meta.tolerancia_pct or 0) / 100)
        cumple = calculo["rendimiento"] >= piso
        desviacion = round(
            (calculo["rendimiento"] - meta.meta_km_gal) / meta.meta_km_gal * 100, 1)

    obj = EAMRegistroCombustible(
        **data.model_dump(exclude={"unidad"}), unidad=data.unidad.upper(),
        **importe, **calculo,
        meta_km_gal=meta_valor, cumple_meta=cumple, desviacion_pct=desviacion,
        registrado_por=_quien(usuario))
    db.add(obj)

    # El odómetro del activo se mueve con el tanqueo: es la lectura más
    # frecuente que existe, y de ella dependen los planes por kilometraje.
    if data.odometro is not None and data.odometro > (activo.odometro_actual or 0):
        activo.odometro_actual = data.odometro
    if data.horometro is not None and data.horometro > (activo.horometro_actual or 0):
        activo.horometro_actual = data.horometro

    await db.commit(); await db.refresh(obj)
    d = RegistroOut.model_validate(obj).model_dump()
    d.update(placa=activo.placa, activo_codigo=activo.codigo,
             activo_nombre=activo.nombre, marca=activo.marca, linea=activo.linea)
    return d


@router.delete("/registros/{rid}", status_code=204)
async def borrar(rid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMRegistroCombustible, rid)
    if not obj:
        raise HTTPException(404, "Ese registro no existe")
    await db.delete(obj); await db.commit()


@router.post("/recalcular", response_model=Dict[str, Any])
async def recalcular(activo_id: Optional[int] = None,
                     db: AsyncSession = Depends(get_db)):
    """Vuelve a calcular rendimiento y cumplimiento de todo el histórico.

    Hace falta al cambiar una meta o al corregir un odómetro viejo: el
    rendimiento de un tanqueo depende del anterior, así que un dato corregido
    hacia atrás deja desactualizado todo lo que vino después.
    """
    q = select(EAMRegistroCombustible).order_by(
        EAMRegistroCombustible.activo_id, EAMRegistroCombustible.fecha)
    if activo_id:
        q = q.where(EAMRegistroCombustible.activo_id == activo_id)
    registros = list((await db.execute(q)).scalars().all())

    activos: Dict[int, EAMActivo] = {}
    tocados = 0
    for reg in registros:
        if reg.activo_id not in activos:
            activos[reg.activo_id] = await db.get(EAMActivo, reg.activo_id)
        activo = activos[reg.activo_id]
        if not activo:
            continue

        galones = _a_galones(reg.cantidad, reg.unidad)
        calculo = await _rendimiento_tanque_a_tanque(
            db, reg.activo_id, reg.fecha, reg.odometro, galones, reg.tanque_lleno)
        reg.km_recorridos = calculo["km_recorridos"]
        reg.rendimiento = calculo["rendimiento"]

        meta = await _meta_de(db, activo, reg.tipo_combustible)
        reg.meta_km_gal = meta.meta_km_gal if meta else None
        if meta and reg.rendimiento is not None:
            piso = meta.meta_km_gal * (1 - (meta.tolerancia_pct or 0) / 100)
            reg.cumple_meta = reg.rendimiento >= piso
            reg.desviacion_pct = round(
                (reg.rendimiento - meta.meta_km_gal) / meta.meta_km_gal * 100, 1)
        else:
            reg.cumple_meta = None
            reg.desviacion_pct = None
        tocados += 1

    await db.commit()
    return {"recalculados": tocados}


# ══════════════════════════════════════════════════════════════════════════════
# INFORMES Y ALERTAS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/rendimiento", response_model=Dict[str, Any])
async def rendimiento(dias: int = Query(180, ge=7, le=1825),
                      tipo_activo: Optional[str] = None,
                      marca: Optional[str] = None,
                      db: AsyncSession = Depends(get_db)):
    """Kilómetros por galón por vehículo, marca, línea y motor.

    Solo entran los tanqueos con rendimiento calculado: los que no se pudieron
    medir se cuentan aparte, para que se vea cuánta de la flota está quedando
    fuera del informe en vez de esconderlo.
    """
    desde = datetime.utcnow() - timedelta(days=dias)

    base = (select(EAMRegistroCombustible, EAMActivo)
            .join(EAMActivo, EAMActivo.id == EAMRegistroCombustible.activo_id)
            .where(EAMRegistroCombustible.fecha >= desde))
    if tipo_activo:
        base = base.where(EAMActivo.tipo_activo == tipo_activo)
    if marca:
        base = base.where(EAMActivo.marca == marca)
    filas = (await db.execute(base)).all()

    total = len(filas)
    medibles = [(r, a) for r, a in filas if r.rendimiento is not None]
    sin_medir = total - len(medibles)

    galones_totales = sum(_a_galones(r.cantidad, r.unidad) for r, _ in filas)
    costo_total = sum(r.costo_total or 0 for r, _ in filas)
    km_totales = sum(r.km_recorridos or 0 for r, _ in medibles)

    def _agrupar(clave):
        """Promedio ponderado por kilómetros, no promedio de promedios.

        Un tanqueo de 800 km y otro de 50 no valen lo mismo: promediar sus
        rendimientos daría más peso al viaje corto.
        """
        grupos: Dict[str, Dict[str, float]] = {}
        for r, a in medibles:
            etiqueta = clave(a)
            if not etiqueta:
                continue
            g = grupos.setdefault(etiqueta, {
                "km": 0.0, "galones": 0.0, "costo": 0.0, "tanqueos": 0,
                "alertas": 0, "meta": None})
            g["km"] += r.km_recorridos or 0
            g["galones"] += _a_galones(r.cantidad, r.unidad)
            g["costo"] += r.costo_total or 0
            g["tanqueos"] += 1
            if r.cumple_meta is False:
                g["alertas"] += 1
            if r.meta_km_gal:
                g["meta"] = r.meta_km_gal
        salida = []
        for etiqueta, g in grupos.items():
            rend = round(g["km"] / g["galones"], 2) if g["galones"] else None
            salida.append({
                "etiqueta": etiqueta, "km": round(g["km"], 1),
                "galones": round(g["galones"], 1), "costo": round(g["costo"], 2),
                "tanqueos": g["tanqueos"], "alertas": g["alertas"],
                "rendimiento": rend, "meta": g["meta"],
                "costo_por_km": round(g["costo"] / g["km"], 2) if g["km"] else None,
                "desviacion_pct": (round((rend - g["meta"]) / g["meta"] * 100, 1)
                                   if rend and g["meta"] else None),
            })
        return sorted(salida, key=lambda x: -(x["km"] or 0))

    return {
        "periodo_dias": dias,
        "tanqueos": total,
        "sin_rendimiento": sin_medir,
        "km_totales": round(km_totales, 1),
        "galones_totales": round(galones_totales, 1),
        "costo_total": round(costo_total, 2),
        "rendimiento_flota": round(km_totales / sum(
            _a_galones(r.cantidad, r.unidad) for r, _ in medibles), 2) if medibles else None,
        "costo_por_km": round(costo_total / km_totales, 2) if km_totales else None,
        "por_vehiculo": _agrupar(lambda a: a.placa or a.codigo),
        "por_marca": _agrupar(lambda a: a.marca),
        "por_linea": _agrupar(lambda a: f"{a.marca or ''} {a.linea}".strip() if a.linea else None),
        "por_motor": _agrupar(lambda a: f"{a.motor_marca or ''} {a.motor_linea or ''}".strip() or None),
    }


@router.get("/alertas", response_model=List[Dict[str, Any]])
async def alertas(dias: int = Query(90, ge=7, le=730),
                  db: AsyncSession = Depends(get_db)):
    """Vehículos por debajo de su meta.

    Se agrupa por vehículo y no se lista tanqueo por tanqueo: un mal tanqueo
    puede ser una carretera en subida, pero tres seguidos son un problema del
    equipo. La alerta señala el vehículo, que es sobre lo que se actúa.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    r = await db.execute(
        select(EAMRegistroCombustible, EAMActivo)
        .join(EAMActivo, EAMActivo.id == EAMRegistroCombustible.activo_id)
        .where(and_(EAMRegistroCombustible.fecha >= desde,
                    EAMRegistroCombustible.rendimiento.isnot(None),
                    EAMRegistroCombustible.meta_km_gal.isnot(None)))
        .order_by(EAMRegistroCombustible.fecha))

    por_activo: Dict[int, Dict[str, Any]] = {}
    for reg, activo in r.all():
        d = por_activo.setdefault(activo.id, {
            "activo_id": activo.id, "placa": activo.placa or activo.codigo,
            "activo": activo.nombre, "marca": activo.marca, "linea": activo.linea,
            "motor": f"{activo.motor_marca or ''} {activo.motor_linea or ''}".strip() or None,
            "meta": reg.meta_km_gal, "km": 0.0, "galones": 0.0,
            "tanqueos": 0, "incumplidos": 0, "ultimo": None})
        d["km"] += reg.km_recorridos or 0
        d["galones"] += _a_galones(reg.cantidad, reg.unidad)
        d["tanqueos"] += 1
        if reg.cumple_meta is False:
            d["incumplidos"] += 1
        d["ultimo"] = reg.fecha
        d["meta"] = reg.meta_km_gal

    salida = []
    for d in por_activo.values():
        if not d["galones"]:
            continue
        promedio = round(d["km"] / d["galones"], 2)
        meta = d["meta"]
        if promedio >= meta:
            continue
        desviacion = round((promedio - meta) / meta * 100, 1)
        salida.append({
            **d, "km": round(d["km"], 1), "galones": round(d["galones"], 1),
            "rendimiento": promedio, "desviacion_pct": desviacion,
            # Tres tanqueos por debajo ya no es la carretera: es el equipo.
            "severidad": "ALTA" if (d["incumplidos"] >= 3 or desviacion <= -15)
                         else "MEDIA",
        })
    return sorted(salida, key=lambda x: x["desviacion_pct"])


@router.get("/tipos", response_model=List[str])
async def tipos_combustible(db: AsyncSession = Depends(get_db)):
    """Los del catálogo del CMMS, para no inventar una lista paralela."""
    r = await db.execute(select(EAMTipoCombustible.nombre)
                         .where(EAMTipoCombustible.activo.is_(True))
                         .order_by(EAMTipoCombustible.nombre))
    return [n for (n,) in r.all()]
