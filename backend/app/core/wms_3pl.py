"""
Facturación del servicio logístico (3PL) a cada depositante.

**Almacenamiento día a día, del kárdex.** Se parte de la existencia de hoy de
los productos del depositante y se deshacen los movimientos hacia atrás: al
cruzar la medianoche de cada día (hora de Bogotá) se toma la foto de lo que
había. De cada foto salen las unidades, los m³ (con el volumen medido de cada
producto), las posiciones ocupadas y las estibas. Así se puede liquidar
cualquier periodo pasado sin una tarea nocturna, y el número es auditable: es
la misma historia que muestra el kárdex.

**Actividad.** Unidades recibidas y recepciones, unidades despachadas, líneas
alistadas y órdenes despachadas en el periodo; y la maquila terminada, a la
mano de obra de su receta.

**Tarifas.** La del depositante para cada concepto; si no tiene, la general.
El mínimo mensual se prorratea por los días del periodo y, si lo liquidado no
llega, se agrega un ajuste.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.wms_slotting import volumenes
from app.infrastructure.models.wms import (
    WMSContenedor, WMSDespacho, WMSInventarioUbicacion, WMSMaquilaOrden, WMSMaquilaReceta, WMSMovimientoInventario,
    WMSOrdenSalida, WMSPickingDetalle, WMSPickingTarea, WMSProducto, WMSTarifa3PL, WMSUbicacion, WMSZona,
)

M = WMSMovimientoInventario
CONCEPTOS = {
    "ALM_M3_DIA": ("Almacenamiento por m³-día", "m³-día"),
    "ALM_POSICION_DIA": ("Almacenamiento por posición-día", "posición-día"),
    "ALM_ESTIBA_DIA": ("Almacenamiento por estiba-día", "estiba-día"),
    "REC_UNIDAD": ("Recepción por unidad", "unidad"),
    "REC_DOCUMENTO": ("Recepción por documento", "recepción"),
    "DESP_UNIDAD": ("Despacho por unidad", "unidad"),
    "DESP_LINEA": ("Alistamiento por línea", "línea"),
    "DESP_ORDEN": ("Despacho por orden", "orden"),
    "MINIMO_MES": ("Mínimo mensual", "mes"),
}
ZONAS_NO_FACTURABLES = ("RECEPCION", "DESPACHO")


def fin_del_dia(d: date) -> datetime:
    """Medianoche de Bogotá al final del día d, en UTC."""
    return datetime.combine(d + timedelta(days=1), time.min, timezone.utc) + timedelta(hours=5)


async def ocupacion_diaria(db: AsyncSession, depositante_id: int, desde: date, hasta: date) -> dict:
    prods = list((await db.execute(select(WMSProducto.id).where(WMSProducto.depositante_id == depositante_id))).scalars())
    dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    if not prods:
        return {"dias": [{"fecha": d.isoformat(), "unidades": 0, "m3": 0, "posiciones": 0, "estibas": 0} for d in dias],
                "avisos": []}
    vol = await volumenes(db, prods)
    no_facturables = set((await db.execute(select(WMSUbicacion.id).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id)
                                           .where(WMSZona.tipo.in_(ZONAS_NO_FACTURABLES)))).scalars())
    estado: Dict[tuple, float] = defaultdict(float)
    for f in (await db.execute(select(WMSInventarioUbicacion).where(WMSInventarioUbicacion.producto_id.in_(prods)))).scalars():
        estado[(f.ubicacion_id, f.producto_id, f.contenedor_id)] += (f.cantidad_disponible or 0) + (f.cantidad_reservada or 0) \
            + (f.cantidad_bloqueada or 0)
    movs = (await db.execute(select(M).where(M.producto_id.in_(prods), M.created_at >= fin_del_dia(desde))
                             .order_by(M.created_at.desc(), M.id.desc()))).scalars().all()
    tipos_lpn = dict((await db.execute(select(WMSContenedor.id, WMSContenedor.tipo))).all())
    i, negativos, fotos = 0, False, {}
    for d in reversed(dias):
        corte = fin_del_dia(d)
        while i < len(movs) and movs[i].created_at >= corte:
            m = movs[i]
            if m.ubicacion_destino_id is not None:
                estado[(m.ubicacion_destino_id, m.producto_id, m.contenedor_destino_id)] -= m.cantidad
            if m.ubicacion_origen_id is not None:
                estado[(m.ubicacion_origen_id, m.producto_id, m.contenedor_id)] += m.cantidad
            i += 1
        unidades = m3 = 0.0
        posiciones, estibas = set(), set()
        for (u, p, c), q in estado.items():
            if q < -1e-6:
                negativos = True
            if q <= 1e-9 or u in no_facturables:
                continue
            unidades += q
            m3 += q * (vol.get(p) or 0)
            posiciones.add(u)
            if c and tipos_lpn.get(c) == "ESTIBA":
                estibas.add(c)
        fotos[d] = {"fecha": d.isoformat(), "unidades": round(unidades, 3), "m3": round(m3, 4),
                    "posiciones": len(posiciones), "estibas": len(estibas)}
    avisos = []
    sin_vol = [p for p in prods if p not in vol]
    if sin_vol:
        avisos.append(f"{len(sin_vol)} productos del depositante no tienen volumen medido: no suman m³ (cubíquelos).")
    if negativos:
        avisos.append("El kárdex de algún producto no cuadra hacia atrás (movimientos anteriores al kárdex completo): "
                      "revise la conciliación en Trazabilidad.")
    return {"dias": [fotos[d] for d in dias], "avisos": avisos}


async def actividad(db: AsyncSession, depositante_id: int, desde: date, hasta: date) -> dict:
    ini, fin = fin_del_dia(desde - timedelta(days=1)), fin_del_dia(hasta)
    base = [M.depositante_id == depositante_id, M.created_at >= ini, M.created_at < fin]
    rec_u, rec_docs = (await db.execute(select(func.coalesce(func.sum(M.cantidad), 0), func.count(func.distinct(M.documento_id)))
                                        .where(*base, M.tipo == "RECEPCION", M.ubicacion_origen_id.is_(None)))).one()
    desp_u = (await db.execute(select(func.coalesce(func.sum(M.cantidad), 0)).where(
        *base, M.tipo == "DESPACHO", M.ubicacion_destino_id.is_(None),
        func.coalesce(M.documento_tipo, "") != "POS_VENTA"))).scalar()
    # Órdenes despachadas: las del depositante con un despacho en el periodo.
    ordenes = (await db.execute(select(func.count(func.distinct(WMSDespacho.orden_id)))
                                .join(WMSOrdenSalida, WMSOrdenSalida.id == WMSDespacho.orden_id)
                                .where(WMSOrdenSalida.depositante_id == depositante_id, WMSDespacho.deleted_at.is_(None),
                                       WMSDespacho.created_at >= ini, WMSDespacho.created_at < fin))).scalar()
    lineas = (await db.execute(select(func.count()).select_from(WMSPickingDetalle)
                               .join(WMSPickingTarea, WMSPickingTarea.id == WMSPickingDetalle.tarea_id)
                               .join(WMSOrdenSalida, WMSOrdenSalida.id == WMSPickingTarea.orden_id)
                               .where(WMSOrdenSalida.depositante_id == depositante_id, WMSPickingDetalle.confirmado.is_(True),
                                      WMSPickingDetalle.cantidad_pickeada > 0,
                                      WMSPickingDetalle.timestamp_confirmacion >= ini,
                                      WMSPickingDetalle.timestamp_confirmacion < fin))).scalar()
    maquila = (await db.execute(select(WMSMaquilaOrden, WMSMaquilaReceta).join(WMSMaquilaReceta, WMSMaquilaReceta.id == WMSMaquilaOrden.receta_id)
                                .where(WMSMaquilaOrden.depositante_id == depositante_id, WMSMaquilaOrden.estado == "TERMINADA",
                                       WMSMaquilaOrden.terminada_en >= ini, WMSMaquilaOrden.terminada_en < fin))).all()
    return {"rec_unidades": float(rec_u or 0), "rec_documentos": int(rec_docs or 0), "desp_unidades": float(desp_u or 0),
            "desp_lineas": int(lineas or 0), "desp_ordenes": int(ordenes or 0),
            "maquila": [{"numero": o.numero, "receta": r.nombre, "unidades": o.cantidad_hecha or 0,
                         "valor": round(r.costo_mano_obra_unidad * (o.cantidad_hecha or 0), 2)} for o, r in maquila]}


async def tarifas_efectivas(db: AsyncSession, depositante_id: int) -> Dict[str, WMSTarifa3PL]:
    filas = (await db.execute(select(WMSTarifa3PL).where(
        WMSTarifa3PL.activo.is_(True),
        (WMSTarifa3PL.depositante_id.is_(None)) | (WMSTarifa3PL.depositante_id == depositante_id)))).scalars().all()
    out: Dict[str, WMSTarifa3PL] = {}
    for t in sorted(filas, key=lambda t: t.depositante_id is not None):   # la del depositante gana
        out[t.concepto] = t
    return out


def _linea(concepto: str, cantidad: float, tarifa: WMSTarifa3PL, descripcion: Optional[str] = None) -> dict:
    nombre, unidad = CONCEPTOS[concepto]
    sub = round(cantidad * tarifa.valor, 2)
    return {"concepto": concepto, "descripcion": descripcion or nombre, "cantidad": round(cantidad, 4), "unidad": unidad,
            "tarifa": tarifa.valor, "subtotal": sub, "iva_pct": tarifa.iva_pct, "iva": round(sub * tarifa.iva_pct / 100, 2),
            "propia": tarifa.depositante_id is not None}


async def liquidar(db: AsyncSession, depositante_id: int, desde: date, hasta: date) -> dict:
    ocu = await ocupacion_diaria(db, depositante_id, desde, hasta)
    act = await actividad(db, depositante_id, desde, hasta)
    tar = await tarifas_efectivas(db, depositante_id)
    d = ocu["dias"]
    cantidades = {
        "ALM_M3_DIA": sum(x["m3"] for x in d), "ALM_POSICION_DIA": sum(x["posiciones"] for x in d),
        "ALM_ESTIBA_DIA": sum(x["estibas"] for x in d), "REC_UNIDAD": act["rec_unidades"],
        "REC_DOCUMENTO": act["rec_documentos"], "DESP_UNIDAD": act["desp_unidades"], "DESP_LINEA": act["desp_lineas"],
        "DESP_ORDEN": act["desp_ordenes"],
    }
    lineas = [_linea(c, q, tar[c]) for c, q in cantidades.items() if c in tar and q > 0]
    for mq in act["maquila"]:
        if mq["valor"] > 0:
            iva = tar["DESP_UNIDAD"].iva_pct if "DESP_UNIDAD" in tar else 19
            lineas.append({"concepto": "MAQUILA", "descripcion": f"Maquila {mq['numero']} · {mq['receta']}", "cantidad": mq["unidades"],
                           "unidad": "unidad", "tarifa": round(mq["valor"] / mq["unidades"], 4) if mq["unidades"] else 0,
                           "subtotal": mq["valor"], "iva_pct": iva, "iva": round(mq["valor"] * iva / 100, 2), "propia": True})
    if "MINIMO_MES" in tar:
        minimo = round(tar["MINIMO_MES"].valor * len(d) / 30, 2)
        actual = sum(x["subtotal"] for x in lineas)
        if actual < minimo:
            t = tar["MINIMO_MES"]
            falta = round(minimo - actual, 2)
            lineas.append({"concepto": "MINIMO_MES", "descripcion": f"Ajuste al mínimo ({len(d)} días de {t.valor:,.0f} al mes)",
                           "cantidad": 1, "unidad": "ajuste", "tarifa": falta, "subtotal": falta, "iva_pct": t.iva_pct,
                           "iva": round(falta * t.iva_pct / 100, 2), "propia": t.depositante_id is not None})
    avisos = list(ocu["avisos"])
    sin_tarifa = [CONCEPTOS[c][0] for c, q in cantidades.items() if q > 0 and c not in tar]
    if sin_tarifa:
        avisos.append("Hubo actividad sin tarifa (no se cobra): " + ", ".join(sin_tarifa) + ".")
    subtotal = round(sum(x["subtotal"] for x in lineas), 2)
    iva = round(sum(x["iva"] for x in lineas), 2)
    return {"lineas": lineas, "diario": d, "actividad": act, "subtotal": subtotal, "iva": iva,
            "total": round(subtotal + iva, 2), "avisos": avisos,
            "promedios": {"m3": round(sum(x["m3"] for x in d) / len(d), 4) if d else 0,
                          "posiciones": round(sum(x["posiciones"] for x in d) / len(d), 1) if d else 0,
                          "estibas": round(sum(x["estibas"] for x in d) / len(d), 1) if d else 0}}
