"""
Centro de informes del CMMS.

CÓMO ESTÁ ARMADO, Y POR QUÉ ASÍ
Cada informe declara sus columnas y su consulta en un solo sitio, y hay UN
endpoint genérico que los ejecuta. La alternativa —un endpoint por informe—
significaba veinte funciones casi iguales y un frontend con veinte pantallas
casi iguales.

Además, los informes que ya existen en otros módulos NO se recalculan acá: la
analítica de combustible, la de causa raíz y la de inventario viven en sus
módulos y el centro solo las lista y enlaza. Volver a escribir esas fórmulas
sería la tercera copia, y la tercera copia es la que empieza a dar una cifra
distinta.

LO QUE SÍ VIVE ACÁ
Los informes transversales —los que cruzan varios módulos y no son de ninguno—:
costos por activo y por centro de costo, cumplimiento del plan, y el detalle
plano de órdenes que la gente necesita para llevarse a Excel.
"""
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_, desc, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.confiabilidad import ordenes_del_periodo, horas_entre
from app.infrastructure.models.eam import (
    EAMActivo, EAMOrdenTrabajo, EAMOTMaterial, EAMOTManoObra,
    EAMPlanMantenimiento, EAMPlanActivo,
)

router = APIRouter(prefix="/eam/reportes", tags=["CMMS/EAM · Reportes"])


class Columna(BaseModel):
    clave: str
    titulo: str
    # texto | numero | moneda | fecha | porcentaje — lo usa la pantalla para
    # alinear y formatear, y el Excel para no exportar números como texto.
    tipo: str = "texto"


class Informe(BaseModel):
    clave: str
    nombre: str
    descripcion: str
    categoria: str
    columnas: List[Columna]
    # Los informes que viven en otro módulo se listan pero se abren allá.
    ruta_modulo: Optional[str] = None


def _col(clave: str, titulo: str, tipo: str = "texto") -> Columna:
    return Columna(clave=clave, titulo=titulo, tipo=tipo)


# ── Informes que se ejecutan acá ─────────────────────────────────────────────

async def _ordenes_detalle(db: AsyncSession, desde: datetime, **_) -> List[Dict[str, Any]]:
    """El detalle plano de órdenes: la base de casi cualquier pregunta."""
    filas = []
    for o, a in await ordenes_del_periodo(db, desde):
        horas = horas_entre(o.fecha_inicio, o.fecha_fin)
        filas.append({
            "numero": o.numero, "fecha": o.fecha_fin, "activo": a.placa or a.codigo,
            "activo_nombre": a.nombre, "marca": a.marca, "linea": a.linea,
            "tipo_ot": o.tipo_ot, "prioridad": o.prioridad,
            "es_falla": "Sí" if o.es_falla else "No",
            "descripcion": (o.descripcion or "")[:200],
            "tecnico": o.tecnico_asignado, "centro_costo": o.centro_costo,
            "horas": round(horas, 1) if horas else None,
            "costo_mano_obra": round(o.costo_mano_obra or 0, 2),
            "costo_repuestos": round(o.costo_repuestos or 0, 2),
            "costo_servicios": round(o.costo_servicios or 0, 2),
            "costo_total": round(o.costo_total or 0, 2),
            "odometro": o.odometro,
        })
    return filas


async def _costo_por_activo(db: AsyncSession, desde: datetime, **_) -> List[Dict[str, Any]]:
    acumulado: Dict[int, Dict[str, Any]] = {}
    for o, a in await ordenes_del_periodo(db, desde):
        d = acumulado.setdefault(a.id, {
            "activo": a.placa or a.codigo, "nombre": a.nombre, "marca": a.marca,
            "linea": a.linea, "tipo": a.tipo_activo,
            "ordenes": 0, "fallas": 0, "preventivas": 0,
            "mano_obra": 0.0, "repuestos": 0.0, "servicios": 0.0, "total": 0.0})
        d["ordenes"] += 1
        d["fallas"] += 1 if o.es_falla else 0
        d["preventivas"] += 0 if o.es_falla else 1
        d["mano_obra"] += o.costo_mano_obra or 0
        d["repuestos"] += o.costo_repuestos or 0
        d["servicios"] += o.costo_servicios or 0
        d["total"] += o.costo_total or 0
    filas = list(acumulado.values())
    for f in filas:
        for k in ("mano_obra", "repuestos", "servicios", "total"):
            f[k] = round(f[k], 2)
        # La proporción correctivo/preventivo dice más que el costo suelto: una
        # flota cara pero preventiva es un problema distinto a una barata que
        # solo se atiende cuando se rompe.
        f["pct_correctivo"] = (round(f["fallas"] / f["ordenes"] * 100, 1)
                               if f["ordenes"] else None)
    return sorted(filas, key=lambda x: -x["total"])


async def _costo_por_centro(db: AsyncSession, desde: datetime, **_) -> List[Dict[str, Any]]:
    acumulado: Dict[str, Dict[str, Any]] = {}
    for o, a in await ordenes_del_periodo(db, desde):
        clave = o.centro_costo or "Sin centro de costo"
        d = acumulado.setdefault(clave, {
            "centro_costo": clave, "ciudad": o.ciudad, "ordenes": 0,
            "activos": set(), "mano_obra": 0.0, "repuestos": 0.0,
            "servicios": 0.0, "total": 0.0})
        d["ordenes"] += 1
        d["activos"].add(a.id)
        d["mano_obra"] += o.costo_mano_obra or 0
        d["repuestos"] += o.costo_repuestos or 0
        d["servicios"] += o.costo_servicios or 0
        d["total"] += o.costo_total or 0
    filas = []
    for d in acumulado.values():
        d["activos"] = len(d["activos"])
        for k in ("mano_obra", "repuestos", "servicios", "total"):
            d[k] = round(d[k], 2)
        filas.append(d)
    return sorted(filas, key=lambda x: -x["total"])


async def _cumplimiento_plan(db: AsyncSession, desde: datetime, **_) -> List[Dict[str, Any]]:
    """Rutinas por activo, con su vencimiento.

    Se lee de `eam_plan_activo` y no de las órdenes: la rutina puede estar
    vencida justamente porque NO se generó la orden, y mirar solo lo ejecutado
    dejaría fuera lo que más importa.
    """
    ahora = datetime.utcnow()
    r = await db.execute(
        select(EAMPlanActivo, EAMPlanMantenimiento, EAMActivo)
        .join(EAMPlanMantenimiento, EAMPlanMantenimiento.id == EAMPlanActivo.plan_id)
        .join(EAMActivo, EAMActivo.id == EAMPlanActivo.activo_id)
        .where(EAMActivo.activo.is_(True))
        .order_by(EAMPlanActivo.proxima_fecha))
    from app.core.parametros_eam import leer_parametros_eam
    aviso_pm = (await leer_parametros_eam(db))['pm_dias_aviso']
    filas = []
    for pa, plan, activo in r.all():
        dias = (pa.proxima_fecha - ahora).days if pa.proxima_fecha else None
        filas.append({
            "activo": activo.placa or activo.codigo, "nombre": activo.nombre,
            "marca": activo.marca, "linea": activo.linea,
            "plan": plan.nombre,
            "ultima_ejecucion": pa.ultima_ejecucion_fecha,
            "proxima": pa.proxima_fecha,
            "proximo_odometro": pa.proximo_odometro,
            "odometro_actual": activo.odometro_actual,
            "dias": dias,
            "estado": ("SIN PROGRAMAR" if dias is None
                       else "VENCIDA" if dias < 0
                       else "PRÓXIMA" if dias <= aviso_pm else "AL DÍA"),
        })
    return filas


async def _mano_obra(db: AsyncSession, desde: datetime, **_) -> List[Dict[str, Any]]:
    """Horas y costo por técnico y por contratista."""
    r = await db.execute(
        select(EAMOTManoObra, EAMOrdenTrabajo, EAMActivo)
        .join(EAMOrdenTrabajo, EAMOrdenTrabajo.id == EAMOTManoObra.ot_id)
        .join(EAMActivo, EAMActivo.id == EAMOrdenTrabajo.activo_id)
        .where(and_(EAMOrdenTrabajo.fecha_fin.isnot(None),
                    EAMOrdenTrabajo.fecha_fin >= desde)))
    filas = []
    for linea, ot, activo in r.all():
        filas.append({
            "orden": ot.numero, "fecha": ot.fecha_fin,
            "activo": activo.placa or activo.codigo,
            "actividad": linea.actividad, "sistema": linea.sistema,
            "ejecutor": linea.tecnico or "Contratista",
            "horas": linea.horas, "tarifa": linea.tarifa_hora,
            "costo": round(linea.costo_total or 0, 2),
        })
    return sorted(filas, key=lambda x: -(x["costo"] or 0))


async def _repuestos_consumidos(db: AsyncSession, desde: datetime, **_) -> List[Dict[str, Any]]:
    r = await db.execute(
        select(EAMOTMaterial, EAMOrdenTrabajo, EAMActivo)
        .join(EAMOrdenTrabajo, EAMOrdenTrabajo.id == EAMOTMaterial.ot_id)
        .join(EAMActivo, EAMActivo.id == EAMOrdenTrabajo.activo_id)
        .where(and_(EAMOrdenTrabajo.fecha_fin.isnot(None),
                    EAMOrdenTrabajo.fecha_fin >= desde)))
    filas = []
    for linea, ot, activo in r.all():
        filas.append({
            "orden": ot.numero, "fecha": ot.fecha_fin,
            "activo": activo.placa or activo.codigo, "marca": activo.marca,
            "repuesto": linea.descripcion, "cantidad": linea.cantidad,
            "unidad": linea.unidad,
            "costo_unit": round(linea.costo_unit or 0, 2),
            "costo_total": round(linea.costo_total or 0, 2),
        })
    return sorted(filas, key=lambda x: -(x["costo_total"] or 0))


# ── El catálogo ──────────────────────────────────────────────────────────────

EJECUTORES: Dict[str, Callable] = {
    "ordenes": _ordenes_detalle,
    "costo_activo": _costo_por_activo,
    "costo_centro": _costo_por_centro,
    "cumplimiento_plan": _cumplimiento_plan,
    "mano_obra": _mano_obra,
    "repuestos": _repuestos_consumidos,
}

CATALOGO: List[Informe] = [
    Informe(clave="ordenes", nombre="Órdenes de trabajo", categoria="Operación",
            descripcion="Detalle plano de las órdenes cerradas, con sus costos "
                        "desagregados. Es la base de casi cualquier pregunta.",
            columnas=[
                _col("numero", "Número"), _col("fecha", "Cierre", "fecha"),
                _col("activo", "Activo"), _col("activo_nombre", "Nombre"),
                _col("marca", "Marca"), _col("linea", "Línea"),
                _col("tipo_ot", "Tipo"), _col("prioridad", "Prioridad"),
                _col("es_falla", "¿Falla?"), _col("descripcion", "Descripción"),
                _col("tecnico", "Técnico"), _col("centro_costo", "Centro de costo"),
                _col("horas", "Horas", "numero"),
                _col("costo_mano_obra", "Mano de obra", "moneda"),
                _col("costo_repuestos", "Repuestos", "moneda"),
                _col("costo_servicios", "Servicios", "moneda"),
                _col("costo_total", "Total", "moneda"),
                _col("odometro", "Odómetro", "numero"),
            ]),
    Informe(clave="costo_activo", nombre="Costo por activo", categoria="Costos",
            descripcion="Cuánto costó cada equipo, y qué proporción fue correctivo. "
                        "Una flota cara pero preventiva es un problema distinto a "
                        "una barata que solo se atiende cuando se rompe.",
            columnas=[
                _col("activo", "Activo"), _col("nombre", "Nombre"),
                _col("marca", "Marca"), _col("linea", "Línea"), _col("tipo", "Tipo"),
                _col("ordenes", "Órdenes", "numero"), _col("fallas", "Fallas", "numero"),
                _col("preventivas", "Preventivas", "numero"),
                _col("pct_correctivo", "% correctivo", "porcentaje"),
                _col("mano_obra", "Mano de obra", "moneda"),
                _col("repuestos", "Repuestos", "moneda"),
                _col("servicios", "Servicios", "moneda"),
                _col("total", "Total", "moneda"),
            ]),
    Informe(clave="costo_centro", nombre="Costo por centro de costo",
            categoria="Costos",
            descripcion="El corte contable: a dónde se imputó el gasto de "
                        "mantenimiento del periodo.",
            columnas=[
                _col("centro_costo", "Centro de costo"), _col("ciudad", "Ciudad"),
                _col("activos", "Activos", "numero"), _col("ordenes", "Órdenes", "numero"),
                _col("mano_obra", "Mano de obra", "moneda"),
                _col("repuestos", "Repuestos", "moneda"),
                _col("servicios", "Servicios", "moneda"),
                _col("total", "Total", "moneda"),
            ]),
    Informe(clave="cumplimiento_plan", nombre="Cumplimiento del plan",
            categoria="Programación",
            descripcion="Rutinas por activo con su vencimiento. Sale de la "
                        "programación y no de lo ejecutado: una rutina vencida lo "
                        "está justamente porque no se generó la orden.",
            columnas=[
                _col("activo", "Activo"), _col("nombre", "Nombre"),
                _col("marca", "Marca"), _col("linea", "Línea"), _col("plan", "Rutina"),
                _col("ultima_ejecucion", "Última ejecución", "fecha"),
                _col("proxima", "Próxima", "fecha"),
                _col("proximo_odometro", "Próximo odómetro", "numero"),
                _col("odometro_actual", "Odómetro actual", "numero"),
                _col("dias", "Días", "numero"), _col("estado", "Estado"),
            ]),
    Informe(clave="mano_obra", nombre="Mano de obra", categoria="Operación",
            descripcion="Horas y costo por técnico y por contratista, línea a línea.",
            columnas=[
                _col("orden", "Orden"), _col("fecha", "Fecha", "fecha"),
                _col("activo", "Activo"), _col("actividad", "Actividad"),
                _col("sistema", "Sistema"), _col("ejecutor", "Ejecutor"),
                _col("horas", "Horas", "numero"), _col("tarifa", "Tarifa", "moneda"),
                _col("costo", "Costo", "moneda"),
            ]),
    Informe(clave="repuestos", nombre="Repuestos consumidos", categoria="Costos",
            descripcion="Qué se montó en cada equipo y cuánto costó.",
            columnas=[
                _col("orden", "Orden"), _col("fecha", "Fecha", "fecha"),
                _col("activo", "Activo"), _col("marca", "Marca"),
                _col("repuesto", "Repuesto"), _col("cantidad", "Cantidad", "numero"),
                _col("unidad", "Unidad"), _col("costo_unit", "Costo unitario", "moneda"),
                _col("costo_total", "Costo total", "moneda"),
            ]),
    # Los que ya viven en otro módulo se listan para que se sepa que existen,
    # pero se abren allá. Recalcularlos acá sería la tercera copia de la misma
    # fórmula, y la tercera copia es la que empieza a dar otra cifra.
    Informe(clave="combustible", nombre="Rendimiento de combustible",
            categoria="Flota", ruta_modulo="/eam/combustible", columnas=[],
            descripcion="Kilómetros por galón por vehículo, marca, línea y motor, "
                        "con las metas y sus alertas."),
    Informe(clave="lubricacion", nombre="Análisis de lubricación",
            categoria="Confiabilidad", ruta_modulo="/eam/lubricacion", columnas=[],
            descripcion="Muestras de aceite, severidades y costo por hora lubricada."),
    Informe(clave="inventario", nombre="Inventario y rotación",
            categoria="Costos", ruta_modulo="/eam/inventario", columnas=[],
            descripcion="Existencias por bodega, kárdex y material dormido."),
    Informe(clave="checklists", nombre="Inspecciones", categoria="Operación",
            ruta_modulo="/eam/checklists", columnas=[],
            descripcion="Conformidad por sistema y preguntas más reprobadas."),
    Informe(clave="llantas", nombre="Gestión de llantas", categoria="Flota",
            ruta_modulo="/eam/neumaticos/reportes", columnas=[],
            descripcion="Costo por kilómetro, desgaste y motivos de fin de vida."),
    Informe(clave="causa_raiz", nombre="Causas de falla", categoria="Confiabilidad",
            ruta_modulo="/eam/ordenes-trabajo", columnas=[],
            descripcion="Análisis de causa raíz agrupados por marca y línea."),
]


@router.get("/catalogo", response_model=List[Informe])
async def catalogo():
    """Qué informes hay. Los que traen `ruta_modulo` se abren en su módulo."""
    return CATALOGO


@router.get("/{clave}", response_model=Dict[str, Any])
async def ejecutar(clave: str, dias: int = Query(180, ge=7, le=1825),
                   db: AsyncSession = Depends(get_db)):
    informe = next((i for i in CATALOGO if i.clave == clave), None)
    if not informe:
        raise HTTPException(404, "Ese informe no existe")
    if informe.ruta_modulo:
        raise HTTPException(
            400, f"«{informe.nombre}» se consulta en su propio módulo: {informe.ruta_modulo}")

    desde = datetime.utcnow() - timedelta(days=dias)
    filas = await EJECUTORES[clave](db, desde)
    return {
        "clave": clave, "nombre": informe.nombre,
        "columnas": [c.model_dump() for c in informe.columnas],
        "periodo_dias": dias, "total": len(filas), "filas": filas,
    }
