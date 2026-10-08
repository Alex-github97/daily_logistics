"""
El motor de planeación: de la demanda histórica al plan, en cascada.

    demanda por producto y ubicación
      → pronóstico (o el consenso publicado, si lo hay)
      → inventario objetivo: stock de seguridad, punto de reorden, EOQ
      → DRP: cada centro de distribución pide traslados a la planta que lo surte
      → MPS/MRP: la planta cubre su demanda más esos traslados, con lotes y
        tiempos de entrega, y salen las órdenes sugeridas
      → RCCP: las órdenes de producción cargan los recursos según sus rutas
      → transporte: los traslados se consolidan en camiones por peso
      → alertas y KPIs, calculados de todo lo anterior

Todo es una función pura de los datos que recibe (`Datos`): no lee la base.
Así se puede probar con números conocidos y correr escenarios cambiando solo
los supuestos, sin tocar nada guardado.

CONVENCIONES
  Periodos mensuales «AAAA-MM». El plan arranca en el mes en curso; la
  historia llega hasta el mes anterior (el mes en curso está incompleto y
  ajustar con él haría parecer que la demanda cae).
  Un tiempo de entrega se convierte a meses redondeando al más cercano: con
  cubetas mensuales, una orden de 10 días se lanza y llega el mismo mes.
  El stock de seguridad cubre el error del pronóstico durante el tiempo de
  entrega más un mes de revisión: σ·√(1 + LT/30).
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from app.core.aps.pronostico import pronosticar, z_servicio

CONFIG_DEFECTO = {
    "horizonte_meses": {"defecto": 6, "min": 2, "max": 24, "descripcion": "Meses que abarca el plan"},
    "dias_habiles_mes": {"defecto": 22, "min": 1, "max": 31, "descripcion": "Días hábiles por mes para la capacidad"},
    "costo_pedido": {"defecto": 150000, "min": 0, "max": 1e9, "descripcion": "Costo de emitir un pedido u orden (para el EOQ)"},
    "tasa_posesion_anual_pct": {"defecto": 25, "min": 0, "max": 100, "descripcion": "Costo anual de mantener inventario, % del costo unitario"},
    "nivel_servicio_pct": {"defecto": 95, "min": 50, "max": 99.9, "descripcion": "Nivel de servicio cuando el producto no tiene uno propio"},
    "lead_time_traslado_dias": {"defecto": 3, "min": 0, "max": 90, "descripcion": "Días de un traslado entre ubicaciones"},
    "capacidad_camion_kg": {"defecto": 30000, "min": 100, "max": 60000, "descripcion": "Capacidad de un camión si la ubicación no tiene restricción propia"},
}


TIPO_LEGIBLE = {"PRODUCCION": "producción", "COMPRA": "compra", "TRASLADO": "traslado"}


def mes_actual(hoy: Optional[date] = None) -> str:
    hoy = hoy or date.today()
    return f"{hoy.year}-{hoy.month:02d}"


def sumar_meses(periodo: str, n: int) -> str:
    y, m = int(periodo[:4]), int(periodo[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12}-{t % 12 + 1:02d}"


def meses_entre(a: str, b: str) -> int:
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


def meses_de_entrega(dias: float) -> int:
    """Meses de anticipación con cubetas mensuales, redondeando al más
    cercano: una orden de 10 días se lanza a comienzo de mes y llega ese mismo
    mes. Redondear siempre hacia arriba marcaba como atrasada toda la
    necesidad del mes en curso, una alarma falsa que tapaba las verdaderas."""
    return max(0, math.floor((dias or 0) / 30 + 0.5))


@dataclass
class Datos:
    ubicaciones: Dict[int, dict]
    productos: Dict[int, dict]
    recursos: Dict[int, dict]
    rutas: List[dict]                                   # producto_id, recurso_id, horas_por_unidad
    parametros: Dict[Tuple[int, int], dict]             # (producto, ubicacion) → parámetros
    demanda: Dict[Tuple[int, int], Dict[str, float]]    # (producto, ubicacion) → periodo → cantidad
    config: Dict[str, float]
    consenso: Dict[Tuple[int, int], Dict[str, float]] = field(default_factory=dict)
    programadas: List[dict] = field(default_factory=list)   # órdenes aprobadas aún no recibidas
    bodega_max: Dict[int, float] = field(default_factory=dict)
    camion_kg: Dict[int, float] = field(default_factory=dict)
    publicados: List[dict] = field(default_factory=list)    # detalle publicado vs real, para exactitud
    hoy: Optional[date] = None


def calcular(d: Datos, delta_demanda_pct: float = 0.0, delta_capacidad_pct: float = 0.0,
             delta_costo_pct: float = 0.0) -> Dict:
    cfg = {k: float(d.config.get(k, v["defecto"])) for k, v in CONFIG_DEFECTO.items()}
    H = int(cfg["horizonte_meses"])
    inicio = mes_actual(d.hoy)
    periodos = [sumar_meses(inicio, i) for i in range(H)]
    fd, fc, fk = 1 + delta_demanda_pct / 100, 1 + delta_capacidad_pct / 100, 1 + delta_costo_pct / 100
    costo = lambda pid: (d.productos[pid].get("costo_unitario") or 0) * fk
    lt_traslado = cfg["lead_time_traslado_dias"]

    # ── 1. Pronóstico por serie ──────────────────────────────────────────────
    series = {}
    for (pid, uid), hist in d.demanda.items():
        if pid not in d.productos or uid not in d.ubicaciones:
            continue
        previos = sorted(p for p in hist if p < inicio)
        if not previos:
            continue
        meses = [sumar_meses(previos[0], i) for i in range(meses_entre(previos[0], inicio))]
        y = [hist.get(m, 0.0) for m in meses]
        r = pronosticar(y, H)
        consenso = d.consenso.get((pid, uid), {})
        plan = [(consenso[p] if p in consenso else r["pronostico"][i]) * fd for i, p in enumerate(periodos)]
        series[(pid, uid)] = {"producto_id": pid, "ubicacion_id": uid, "historia": dict(zip(meses, y)),
                              "estadistico": r, "demanda_plan": plan,
                              "usa_consenso": [p in consenso for p in periodos]}

    # ── 2. Inventario objetivo ───────────────────────────────────────────────
    def es_surtida(uid):
        return bool(d.ubicaciones[uid].get("abastecida_por_id")) and d.ubicaciones[uid].get("abastecida_por_id") in d.ubicaciones

    tiene_ruta = {r["producto_id"] for r in d.rutas}
    inventario = {}
    ultimos12 = lambda hist: [v for _, v in sorted(hist.items())[-12:]]
    for key, s in series.items():
        pid, uid = key
        prm = d.parametros.get(key, {})
        prod = d.productos[pid]
        lt = lt_traslado if es_surtida(uid) else (prm.get("lead_time_produccion_dias") if pid in tiene_ruta
                                                  else prm.get("lead_time_compra_dias")) or prod.get("lead_time_dias") or 0
        ns = prm.get("nivel_servicio_pct") or cfg["nivel_servicio_pct"]
        media = sum(s["demanda_plan"][:3]) / min(3, len(s["demanda_plan"]))
        sigma = s["estadistico"].get("rmse") or 0.0
        ss = z_servicio(ns) * sigma * math.sqrt(1 + lt / 30)
        anual = media * 12
        h = costo(pid) * cfg["tasa_posesion_anual_pct"] / 100
        eoq = math.sqrt(2 * anual * cfg["costo_pedido"] / h) if h > 0 and anual > 0 and cfg["costo_pedido"] > 0 else None
        stock = prm.get("stock_actual") or 0.0
        h12 = ultimos12(s["historia"])
        media12 = sum(h12) / len(h12) if h12 else 0
        cv = (math.sqrt(sum((v - media12) ** 2 for v in h12) / len(h12)) / media12) if media12 > 0 and len(h12) > 1 else None
        inventario[key] = {
            "producto_id": pid, "ubicacion_id": uid, "lead_time_dias": lt, "nivel_servicio_pct": ns,
            "demanda_mensual": round(media, 2), "error_pronostico": round(sigma, 2),
            "stock_seguridad": round(ss, 1), "punto_reorden": round(media * lt / 30 + ss, 1),
            "eoq": round(eoq, 1) if eoq else None,
            "stock_maximo": round(ss + (eoq or media), 1),
            "stock_actual": stock, "valor_stock": round(stock * costo(pid), 0),
            "cobertura_dias": round(stock / (media / 30), 1) if media > 0 else None,
            "valor_anual": round(sum(h12) * costo(pid), 0), "cv": round(cv, 2) if cv is not None else None,
        }
    # ABC por valor anual; XYZ por variabilidad
    orden = sorted(inventario.values(), key=lambda x: -x["valor_anual"])
    total_valor = sum(x["valor_anual"] for x in orden) or 1
    acum = 0.0
    for x in orden:
        previo = acum / total_valor
        acum += x["valor_anual"]
        x["abc"] = "A" if previo < 0.8 else "B" if previo < 0.95 else "C"
        x["xyz"] = None if x["cv"] is None else "X" if x["cv"] <= 0.5 else "Y" if x["cv"] <= 1.0 else "Z"

    # ── 3. Recepciones programadas (órdenes ya aprobadas) ────────────────────
    recibe = defaultdict(float)          # (pid, uid, periodo) → cantidad que llega
    envia = defaultdict(float)           # (pid, uid_origen, periodo) → cantidad que sale
    for o in d.programadas:
        per = max(o["periodo"], inicio)
        recibe[(o["producto_id"], o["ubicacion_id"], per)] += o["cantidad"]
        if o["tipo"] == "TRASLADO":
            origen = d.ubicaciones.get(o["ubicacion_id"], {}).get("abastecida_por_id")
            if origen:
                envia[(o["producto_id"], origen, max(sumar_meses(per, -meses_de_entrega(lt_traslado)), inicio))] += o["cantidad"]

    def planear(pid, uid, bruta, tipo, lote_min, lt_dias):
        """Proyección de stock y recepciones planificadas de una serie."""
        prm = d.parametros.get((pid, uid), {})
        inv = inventario.get((pid, uid))
        ss = inv["stock_seguridad"] if inv else 0.0
        stock = prm.get("stock_actual") or 0.0
        off = meses_de_entrega(lt_dias)
        filas, ordenes = [], []
        for i, per in enumerate(periodos):
            prog = recibe.get((pid, uid, per), 0.0)
            disponible = stock + prog - bruta[i]
            planificada = 0.0
            if disponible < ss:
                planificada = ss - disponible
                if lote_min and planificada < lote_min:
                    planificada = lote_min
                planificada = math.ceil(planificada)
            stock = disponible + planificada
            if planificada:
                lanzar = i - off
                ordenes.append({"producto_id": pid, "ubicacion_id": uid, "tipo": tipo, "cantidad": planificada,
                                "periodo_recepcion": per,
                                "periodo_lanzamiento": periodos[lanzar] if lanzar >= 0 else sumar_meses(inicio, lanzar),
                                "atrasada": lanzar < 0, "meses_atraso": -lanzar if lanzar < 0 else 0,
                                "costo": round(planificada * costo(pid), 0)})
            filas.append({"periodo": per, "demanda": round(bruta[i], 1), "programadas": round(prog, 1),
                          "planificadas": planificada, "stock_final": round(stock, 1),
                          "stock_seguridad": round(ss, 1), "bajo_seguridad": disponible < ss})
        return filas, ordenes

    # ── 4. DRP: centros de distribución ──────────────────────────────────────
    drp, traslados = [], []
    for key, s in series.items():
        pid, uid = key
        if not es_surtida(uid):
            continue
        filas, ords = planear(pid, uid, s["demanda_plan"], "TRASLADO", None, lt_traslado)
        origen = d.ubicaciones[uid]["abastecida_por_id"]
        for o in ords:
            o["origen_id"] = origen
            envio_i = periodos.index(o["periodo_recepcion"]) - meses_de_entrega(lt_traslado)
            o["periodo_envio"] = periodos[envio_i] if envio_i >= 0 else inicio
            envia[(pid, origen, o["periodo_envio"])] += o["cantidad"]
            traslados.append(o)
        drp.append({"producto_id": pid, "ubicacion_id": uid, "origen_id": origen, "filas": filas})

    # ── 5. MPS / MRP: nodos que se abastecen solos (plantas) ─────────────────
    mps, ordenes = [], []
    nodos = {(pid, uid) for (pid, uid) in series if not es_surtida(uid)}
    nodos |= {(pid, uid) for (pid, uid, _) in envia if not es_surtida(uid)}
    for pid, uid in sorted(nodos):
        if pid not in d.productos or uid not in d.ubicaciones:
            continue
        propia = series.get((pid, uid), {}).get("demanda_plan", [0.0] * H)
        dependiente = [envia.get((pid, uid, p), 0.0) for p in periodos]
        bruta = [a + b for a, b in zip(propia, dependiente)]
        prm = d.parametros.get((pid, uid), {})
        fabrica = pid in tiene_ruta
        tipo = "PRODUCCION" if fabrica else "COMPRA"
        lote = prm.get("lote_produccion") if fabrica else prm.get("lote_minimo_compra")
        lt = (prm.get("lead_time_produccion_dias") if fabrica else prm.get("lead_time_compra_dias")) \
            or d.productos[pid].get("lead_time_dias") or 0
        filas, ords = planear(pid, uid, bruta, tipo, lote, lt)
        for f_, dep in zip(filas, dependiente):
            f_["traslados"] = round(dep, 1)
        ordenes += ords
        mps.append({"producto_id": pid, "ubicacion_id": uid, "tipo": tipo, "lote": lote, "lead_time_dias": lt, "filas": filas})

    # ── 6. RCCP: carga de las órdenes de producción sobre los recursos ───────
    carga = defaultdict(float)
    por_recurso = defaultdict(list)
    for r in d.rutas:
        por_recurso[r["producto_id"]].append(r)
    for o in ordenes:
        if o["tipo"] != "PRODUCCION":
            continue
        for r in por_recurso.get(o["producto_id"], []):
            carga[(r["recurso_id"], o["periodo_recepcion"])] += o["cantidad"] * r["horas_por_unidad"]
    capacidad = []
    for rid, rec in d.recursos.items():
        cap = (rec.get("capacidad_diaria") or 0) * cfg["dias_habiles_mes"] * (rec.get("eficiencia_pct") or 100) / 100 * fc
        for per in periodos:
            c = carga.get((rid, per), 0.0)
            capacidad.append({"recurso_id": rid, "periodo": per, "carga_horas": round(c, 1),
                              "capacidad_horas": round(cap, 1),
                              "uso_pct": round(c / cap * 100, 1) if cap > 0 else None,
                              "sobrecarga": cap > 0 and c > cap, "sin_capacidad": cap <= 0 and c > 0})

    # ── 7. Transporte: traslados consolidados en camiones ────────────────────
    cargas = defaultdict(lambda: {"kg": 0.0, "unidades": 0.0, "sin_peso": set(), "lineas": []})
    for t in traslados:
        k = (t["origen_id"], t["ubicacion_id"], t["periodo_envio"])
        peso = d.productos[t["producto_id"]].get("peso_kg")
        if peso:
            cargas[k]["kg"] += t["cantidad"] * peso
        else:
            cargas[k]["sin_peso"].add(d.productos[t["producto_id"]]["codigo"])
        cargas[k]["unidades"] += t["cantidad"]
        cargas[k]["lineas"].append({"producto_id": t["producto_id"], "cantidad": t["cantidad"]})
    transporte = []
    for (o, dst, per), c in sorted(cargas.items(), key=lambda x: x[0][2]):
        cap = d.camion_kg.get(o) or cfg["capacidad_camion_kg"]
        camiones = max(1, math.ceil(c["kg"] / cap)) if c["kg"] else None
        transporte.append({"origen_id": o, "destino_id": dst, "periodo": per, "kg": round(c["kg"], 1),
                           "unidades": c["unidades"], "capacidad_camion_kg": cap, "camiones": camiones,
                           "ocupacion_pct": round(c["kg"] / (camiones * cap) * 100, 1) if camiones else None,
                           "productos_sin_peso": sorted(c["sin_peso"]), "lineas": c["lineas"]})

    # ── 8. Alertas ───────────────────────────────────────────────────────────
    alertas = []
    nombre_p = lambda pid: d.productos[pid]["nombre"]
    nombre_u = lambda uid: d.ubicaciones[uid]["nombre"]
    for o in ordenes + traslados:
        if o["atrasada"]:
            alertas.append({"tipo": "QUIEBRE_STOCK", "nivel": "CRITICA", "producto_id": o["producto_id"], "ubicacion_id": o["ubicacion_id"],
                            "titulo": f"{nombre_p(o['producto_id'])} en {nombre_u(o['ubicacion_id'])}: {TIPO_LEGIBLE.get(o['tipo'], o['tipo'].lower())} atrasada",
                            "detalle": f"Para recibir {o['cantidad']:.0f} en {o['periodo_recepcion']} había que lanzarla hace {o['meses_atraso']} mes(es): riesgo de quiebre."})
    for key, x in inventario.items():
        if x["stock_actual"] > x["stock_maximo"] * 1.5 and (x["cobertura_dias"] or 0) > 90:
            alertas.append({"tipo": "EXCESO_INV", "nivel": "ADVERTENCIA", "producto_id": key[0], "ubicacion_id": key[1],
                            "titulo": f"{nombre_p(key[0])} en {nombre_u(key[1])}: exceso de inventario",
                            "detalle": f"{x['stock_actual']:.0f} unidades, {x['cobertura_dias']:.0f} días de cobertura; el máximo calculado es {x['stock_maximo']:.0f}."})
    for c in capacidad:
        if c["sobrecarga"] or c["sin_capacidad"]:
            rec = d.recursos[c["recurso_id"]]
            alertas.append({"tipo": "CAPACIDAD", "nivel": "CRITICA" if (c["uso_pct"] or 999) > 120 else "ADVERTENCIA",
                            "recurso_id": c["recurso_id"],
                            "titulo": f"{rec['nombre']} sobrecargado en {c['periodo']}",
                            "detalle": (f"Carga {c['carga_horas']:.0f} h de {c['capacidad_horas']:.0f} h ({c['uso_pct']:.0f} %)."
                                        if not c["sin_capacidad"] else f"Tiene {c['carga_horas']:.0f} h de carga y no tiene capacidad registrada.")})
    for uid, maximo in d.bodega_max.items():
        for per_i, per in enumerate(periodos):
            total = sum(f_["stock_final"] for grupo in (mps, drp) for s in grupo if s["ubicacion_id"] == uid
                        for f_ in [s["filas"][per_i]])
            if total > maximo:
                alertas.append({"tipo": "RIESGO", "nivel": "ADVERTENCIA", "ubicacion_id": uid,
                                "titulo": f"{nombre_u(uid)} excede su capacidad de bodega en {per}",
                                "detalle": f"Stock proyectado {total:.0f} unidades; máximo {maximo:.0f}."})
                break
    for key, s in series.items():
        sesgo = s["estadistico"].get("sesgo")
        if sesgo is not None and abs(sesgo) > 25 and s["estadistico"].get("suficiente"):
            alertas.append({"tipo": "DEMANDA", "nivel": "INFO", "producto_id": key[0], "ubicacion_id": key[1],
                            "titulo": f"{nombre_p(key[0])} en {nombre_u(key[1])}: pronóstico con sesgo",
                            "detalle": f"En la validación el pronóstico {'sobreestimó' if sesgo > 0 else 'subestimó'} {abs(sesgo):.0f} %."})
    orden_nivel = {"CRITICA": 0, "ADVERTENCIA": 1, "INFO": 2}
    alertas.sort(key=lambda a: orden_nivel[a["nivel"]])

    # ── 9. KPIs ──────────────────────────────────────────────────────────────
    val = [s["estadistico"] for s in series.values() if s["estadistico"].get("suficiente")]
    peso_val = [(v, sum(v_ for v_ in list(s["historia"].values())[-6:])) for s, v in
                ((s, s["estadistico"]) for s in series.values()) if v.get("suficiente") and v.get("wape") is not None]
    tot = sum(w for _, w in peso_val)
    exactitud_val = round(100 - sum(v["wape"] * w for v, w in peso_val) / tot, 1) if tot else None
    pub_real = sum(p["real"] for p in d.publicados)
    exactitud_pub = round(100 - sum(abs(p["pronostico"] - p["real"]) for p in d.publicados) / pub_real * 100, 1) if pub_real else None
    sesgo_pub = round(sum(p["pronostico"] - p["real"] for p in d.publicados) / pub_real * 100, 1) if pub_real else None
    valor_inv = sum(x["valor_stock"] for x in inventario.values())
    demanda_mes = sum(x["demanda_mensual"] for x in inventario.values())
    stock_total = sum(x["stock_actual"] for x in inventario.values())
    usos = [c["uso_pct"] for c in capacidad if c["uso_pct"] is not None]
    proyectado = [sum(f_["stock_final"] * costo(s["producto_id"]) for s in mps + drp for f_ in [s["filas"][i]])
                  for i in range(H)]
    costo_anual = sum(x["demanda_mensual"] * 12 * costo(x["producto_id"]) for x in inventario.values())
    inv_prom = sum(proyectado) / H if H else 0
    kpis = {
        "series": len(series), "series_con_historia_suficiente": len(val),
        "exactitud_validacion_pct": exactitud_val,
        "exactitud_publicada_pct": exactitud_pub, "sesgo_publicado_pct": sesgo_pub,
        "periodos_publicados_evaluados": len(d.publicados),
        "valor_inventario": round(valor_inv, 0),
        "cobertura_dias": round(stock_total / (demanda_mes / 30), 1) if demanda_mes > 0 else None,
        "rotacion_proyectada": round(costo_anual / inv_prom, 2) if inv_prom > 0 else None,
        "uso_capacidad_promedio_pct": round(sum(usos) / len(usos), 1) if usos else None,
        "uso_capacidad_maximo_pct": max(usos) if usos else None,
        "recursos_sobrecargados": len({c["recurso_id"] for c in capacidad if c["sobrecarga"]}),
        "ordenes_sugeridas": len(ordenes) + len(traslados),
        "ordenes_atrasadas": sum(1 for o in ordenes + traslados if o["atrasada"]),
        "costo_ordenes": round(sum(o["costo"] for o in ordenes), 0),
        "unidades_produccion": sum(o["cantidad"] for o in ordenes if o["tipo"] == "PRODUCCION"),
        "unidades_compra": sum(o["cantidad"] for o in ordenes if o["tipo"] == "COMPRA"),
        "inventario_proyectado_promedio": round(inv_prom, 0),
        "alertas_criticas": sum(1 for a in alertas if a["nivel"] == "CRITICA"),
        "alertas": len(alertas),
    }
    return {"periodos": periodos, "inicio": inicio, "config": cfg, "series": list(series.values()),
            "inventario": list(inventario.values()), "drp": drp, "traslados": traslados, "mps": mps,
            "ordenes": ordenes, "capacidad": capacidad, "transporte": transporte,
            "alertas": alertas, "kpis": kpis}
