"""
Confiabilidad del CMMS — indicadores, Pareto, FMEA y calibraciones.

Las fórmulas viven en `core/confiabilidad.py` porque también las usa el tablero.
Tres copias de la misma fórmula terminan dando tres cifras distintas del mismo
equipo.

QUÉ RESPONDE ESTE MÓDULO
  Indicadores  MTBF, MTTR y disponibilidad, por flota, marca, línea y activo
  Pareto       qué pocos activos concentran las fallas y el costo
  FMEA         modos de falla con su número de prioridad de riesgo
  Calibración  instrumentos y sus vencimientos
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.confiabilidad import (
    ordenes_del_periodo, mttr, mtbf, disponibilidad, agrupar, horas_entre,
)
from app.infrastructure.models.eam import (
    EAMActivo, EAMOrdenTrabajo, EAMFMEA, EAMCalibracion, EAMComponente,
    EAMCausaRaiz,
)

router = APIRouter(prefix="/eam/confiabilidad", tags=["CMMS/EAM · Confiabilidad"])


@router.get("/indicadores", response_model=Dict[str, Any])
async def indicadores(dias: int = Query(180, ge=30, le=1825),
                      tipo_activo: Optional[str] = None,
                      marca: Optional[str] = None,
                      db: AsyncSession = Depends(get_db)):
    desde = datetime.utcnow() - timedelta(days=dias)
    ordenes = await ordenes_del_periodo(db, desde, tipo_activo, marca)

    q = select(EAMActivo).where(EAMActivo.activo.is_(True))
    if tipo_activo:
        q = q.where(EAMActivo.tipo_activo == tipo_activo)
    if marca:
        q = q.where(EAMActivo.marca == marca)
    # La lista y no solo el conteo: cada activo aporta sus propias horas
    # programadas al tiempo de referencia de la disponibilidad.
    lista_activos = list((await db.execute(q)).scalars().all())
    total_activos = len(lista_activos)

    valor_mttr, casos_mttr = mttr(ordenes)
    valor_mtbf, activos_mtbf = mtbf(ordenes)
    fallas = sum(1 for o, _ in ordenes if o.es_falla)

    return {
        "periodo_dias": dias,
        "activos": total_activos,
        "ordenes": len(ordenes),
        "fallas": fallas,
        "costo_total": round(sum(o.costo_total or 0 for o, _ in ordenes), 2),
        "costo_fallas": round(sum(o.costo_total or 0 for o, _ in ordenes if o.es_falla), 2),
        "mttr_horas": valor_mttr, "mttr_casos": casos_mttr,
        "mtbf_horas": valor_mtbf, "mtbf_activos": activos_mtbf,
        "disponibilidad": disponibilidad(ordenes, lista_activos, dias),
        "por_marca": agrupar(ordenes, lambda a: a.marca, dias),
        "por_linea": agrupar(ordenes, lambda a: (f"{a.marca or ''} {a.linea}".strip()
                                                 if a.linea else None), dias),
        "por_tipo": agrupar(ordenes, lambda a: a.tipo_activo, dias),
        "por_activo": agrupar(ordenes, lambda a: a.placa or a.codigo, dias),
    }


@router.get("/pareto", response_model=Dict[str, Any])
async def pareto(dias: int = Query(180, ge=30, le=1825),
                 criterio: str = Query("costo", pattern="^(costo|fallas|horas)$"),
                 db: AsyncSession = Depends(get_db)):
    """Qué pocos activos concentran el problema.

    El valor de un Pareto no es la lista ordenada —eso ya lo da cualquier
    tabla— sino el corte: cuántos equipos hay que atender para cubrir el 80%.
    Por eso se devuelve el acumulado y el número de activos hasta ese punto.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    ordenes = await ordenes_del_periodo(db, desde)

    acumulados: Dict[int, Dict[str, Any]] = {}
    for o, a in ordenes:
        d = acumulados.setdefault(a.id, {
            "activo_id": a.id, "placa": a.placa or a.codigo, "nombre": a.nombre,
            "marca": a.marca, "linea": a.linea,
            "costo": 0.0, "fallas": 0, "horas": 0.0, "ordenes": 0})
        d["costo"] += o.costo_total or 0
        d["ordenes"] += 1
        if o.es_falla:
            d["fallas"] += 1
        if o.afecta_disponibilidad:
            d["horas"] += horas_entre(o.fecha_inicio, o.fecha_fin) or 0

    filas = sorted(acumulados.values(), key=lambda x: -x[criterio])
    total = sum(f[criterio] for f in filas)
    corte_80 = None
    acumulado = 0.0
    for i, f in enumerate(filas, start=1):
        acumulado += f[criterio]
        f["acumulado"] = round(acumulado, 2)
        f["acumulado_pct"] = round(acumulado / total * 100, 1) if total else None
        f["costo"] = round(f["costo"], 2)
        f["horas"] = round(f["horas"], 1)
        if corte_80 is None and total and acumulado >= total * 0.8:
            corte_80 = i

    return {
        "criterio": criterio, "periodo_dias": dias,
        "total": round(total, 2),
        "activos": len(filas),
        # Cuántos equipos explican el 80%. Es el número que decide dónde poner
        # el esfuerzo la semana entrante.
        "activos_80pct": corte_80,
        "filas": filas,
    }


@router.get("/criticidad", response_model=List[Dict[str, Any]])
async def criticidad(dias: int = Query(365, ge=90, le=1825),
                     db: AsyncSession = Depends(get_db)):
    """Cruce de frecuencia de falla contra costo, por activo.

    Es lo que separa «se daña seguido pero es barato» de «se daña poco y cuesta
    una fortuna»: dos problemas distintos que un solo ranking mezcla y que se
    atienden de forma diferente.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    ordenes = await ordenes_del_periodo(db, desde)

    por_activo: Dict[int, Dict[str, Any]] = {}
    for o, a in ordenes:
        d = por_activo.setdefault(a.id, {
            "activo_id": a.id, "placa": a.placa or a.codigo, "nombre": a.nombre,
            "marca": a.marca, "linea": a.linea, "criticidad_declarada": a.criticidad,
            "fallas": 0, "costo": 0.0, "horas_fuera": 0.0})
        if o.es_falla:
            d["fallas"] += 1
            d["costo"] += o.costo_total or 0
        if o.afecta_disponibilidad:
            d["horas_fuera"] += horas_entre(o.fecha_inicio, o.fecha_fin) or 0

    filas = [f for f in por_activo.values() if f["fallas"]]
    if not filas:
        return []

    # Los cortes salen de la mediana de la propia flota, no de un número fijo:
    # «cinco fallas al año» significa cosas distintas en una flota de camiones y
    # en una de montacargas.
    fallas_orden = sorted(f["fallas"] for f in filas)
    costos_orden = sorted(f["costo"] for f in filas)
    mediana = lambda xs: xs[len(xs) // 2]
    corte_fallas, corte_costo = mediana(fallas_orden), mediana(costos_orden)

    for f in filas:
        alta_frecuencia = f["fallas"] > corte_fallas
        alto_costo = f["costo"] > corte_costo
        f["costo"] = round(f["costo"], 2)
        f["horas_fuera"] = round(f["horas_fuera"], 1)
        f["costo_por_falla"] = round(f["costo"] / f["fallas"], 2) if f["fallas"] else None
        f["cuadrante"] = ("CRITICO" if alta_frecuencia and alto_costo
                          else "COSTOSO" if alto_costo
                          else "REPETITIVO" if alta_frecuencia
                          else "CONTROLADO")
    return sorted(filas, key=lambda x: (-x["fallas"], -x["costo"]))


# ══════════════════════════════════════════════════════════════════════════════
# FMEA
# ══════════════════════════════════════════════════════════════════════════════

class FMEAIn(BaseModel):
    activo_id: int
    componente_id: Optional[int] = None
    funcion: str
    modo_falla: str
    efecto_falla: Optional[str] = None
    causa_falla: Optional[str] = None
    severidad: int = 1
    ocurrencia: int = 1
    detectabilidad: int = 1
    accion_recomendada: Optional[str] = None
    responsable: Optional[str] = None


class FMEAOut(FMEAIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    npn: Optional[int] = None
    activo_codigo: Optional[str] = None
    activo_nombre: Optional[str] = None
    componente: Optional[str] = None
    nivel: Optional[str] = None


def _nivel(npn: Optional[int]) -> str:
    """Franjas del número de prioridad de riesgo.

    Los cortes en 100 y 200 son la convención de la industria sobre una escala
    de 1 a 10 en los tres factores. Se dejan explícitos para que quien los
    quiera mover sepa dónde están, en vez de descubrirlos leyendo colores.
    """
    if npn is None:
        return "SIN_EVALUAR"
    return "ALTO" if npn >= 200 else "MEDIO" if npn >= 100 else "BAJO"


@router.get("/fmea", response_model=List[FMEAOut])
async def listar_fmea(activo_id: Optional[int] = None,
                      db: AsyncSession = Depends(get_db)):
    q = (select(EAMFMEA, EAMActivo, EAMComponente)
         .join(EAMActivo, EAMActivo.id == EAMFMEA.activo_id)
         .outerjoin(EAMComponente, EAMComponente.id == EAMFMEA.componente_id)
         .order_by(desc(EAMFMEA.npn)))
    if activo_id:
        q = q.where(EAMFMEA.activo_id == activo_id)
    salida = []
    for f, activo, comp in (await db.execute(q)).all():
        d = FMEAOut.model_validate(f).model_dump()
        d.update(activo_codigo=activo.codigo, activo_nombre=activo.nombre,
                 componente=comp.nombre if comp else None, nivel=_nivel(f.npn))
        salida.append(d)
    return salida


@router.post("/fmea", response_model=FMEAOut, status_code=201)
async def crear_fmea(data: FMEAIn, db: AsyncSession = Depends(get_db)):
    for campo, valor in (("severidad", data.severidad), ("ocurrencia", data.ocurrencia),
                         ("detectabilidad", data.detectabilidad)):
        if not 1 <= valor <= 10:
            raise HTTPException(400, f"«{campo}» va de 1 a 10; llegó {valor}")
    if not await db.get(EAMActivo, data.activo_id):
        raise HTTPException(400, "Ese activo no existe")
    # El NPR lo calcula el servidor: es un producto de tres números y dejarlo al
    # navegador solo abre la puerta a que alguien guarde uno que no cuadra.
    npn = data.severidad * data.ocurrencia * data.detectabilidad
    obj = EAMFMEA(**data.model_dump(), npn=npn)
    db.add(obj); await db.commit(); await db.refresh(obj)
    d = FMEAOut.model_validate(obj).model_dump()
    d["nivel"] = _nivel(npn)
    return d


@router.put("/fmea/{fid}", response_model=FMEAOut)
async def editar_fmea(fid: int, data: FMEAIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMFMEA, fid)
    if not obj:
        raise HTTPException(404, "Ese análisis no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    obj.npn = data.severidad * data.ocurrencia * data.detectabilidad
    await db.commit(); await db.refresh(obj)
    d = FMEAOut.model_validate(obj).model_dump()
    d["nivel"] = _nivel(obj.npn)
    return d


@router.delete("/fmea/{fid}", status_code=204)
async def borrar_fmea(fid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMFMEA, fid)
    if not obj:
        raise HTTPException(404, "Ese análisis no existe")
    await db.delete(obj); await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# CALIBRACIONES
# ══════════════════════════════════════════════════════════════════════════════

class CalibracionIn(BaseModel):
    activo_id: int
    tipo_instrumento: Optional[str] = None
    numero_certificado: Optional[str] = None
    laboratorio: Optional[str] = None
    acreditacion: Optional[str] = None
    fecha_calibracion: date
    fecha_vencimiento: date
    resultado: str = "CONFORME"
    incertidumbre: Optional[str] = None
    patron_utilizado: Optional[str] = None
    observaciones: Optional[str] = None


class CalibracionOut(CalibracionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    estado: str
    activo_codigo: Optional[str] = None
    activo_nombre: Optional[str] = None
    dias_para_vencer: Optional[int] = None


def _estado_calibracion(vencimiento: date, aviso: float = 30) -> str:
    hoy = date.today()
    if vencimiento < hoy:
        return "VENCIDA"
    return "POR_VENCER" if (vencimiento - hoy).days <= aviso else "VIGENTE"


@router.get("/calibraciones", response_model=List[CalibracionOut])
async def listar_calibraciones(activo_id: Optional[int] = None,
                               db: AsyncSession = Depends(get_db)):
    q = (select(EAMCalibracion, EAMActivo)
         .join(EAMActivo, EAMActivo.id == EAMCalibracion.activo_id)
         .order_by(EAMCalibracion.fecha_vencimiento))
    if activo_id:
        q = q.where(EAMCalibracion.activo_id == activo_id)

    salida = []
    hoy = date.today()
    from app.core.parametros_eam import leer_parametros_eam
    aviso = (await leer_parametros_eam(db))['calibracion_dias_aviso']
    for c, activo in (await db.execute(q)).all():
        # El estado se recalcula al leer y se persiste si cambió: una
        # calibración no vence porque alguien abra la pantalla, vence sola con
        # el calendario, y guardarlo mantiene coherentes los conteos del tablero.
        estado = _estado_calibracion(c.fecha_vencimiento, aviso)
        if c.estado != estado:
            c.estado = estado
        d = CalibracionOut.model_validate(c).model_dump()
        d.update(activo_codigo=activo.codigo, activo_nombre=activo.nombre,
                 estado=estado, dias_para_vencer=(c.fecha_vencimiento - hoy).days)
        salida.append(d)
    await db.commit()
    return salida


@router.post("/calibraciones", response_model=CalibracionOut, status_code=201)
async def crear_calibracion(data: CalibracionIn, db: AsyncSession = Depends(get_db)):
    if data.fecha_vencimiento <= data.fecha_calibracion:
        raise HTTPException(
            400, "El vencimiento tiene que ser posterior a la fecha de calibración")
    if not await db.get(EAMActivo, data.activo_id):
        raise HTTPException(400, "Ese activo no existe")
    obj = EAMCalibracion(**data.model_dump(),
                         estado=_estado_calibracion(data.fecha_vencimiento))
    db.add(obj); await db.commit(); await db.refresh(obj)
    d = CalibracionOut.model_validate(obj).model_dump()
    d["dias_para_vencer"] = (obj.fecha_vencimiento - date.today()).days
    return d


@router.put("/calibraciones/{cid}", response_model=CalibracionOut)
async def editar_calibracion(cid: int, data: CalibracionIn,
                             db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMCalibracion, cid)
    if not obj:
        raise HTTPException(404, "Esa calibración no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    obj.estado = _estado_calibracion(data.fecha_vencimiento)
    await db.commit(); await db.refresh(obj)
    d = CalibracionOut.model_validate(obj).model_dump()
    d["dias_para_vencer"] = (obj.fecha_vencimiento - date.today()).days
    return d


@router.delete("/calibraciones/{cid}", status_code=204)
async def borrar_calibracion(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMCalibracion, cid)
    if not obj:
        raise HTTPException(404, "Esa calibración no existe")
    await db.delete(obj); await db.commit()
