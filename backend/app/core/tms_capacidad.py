"""
Capacidad de los vehículos y carga que se les asigna.

- Cada tipo de vehículo tiene un peso y un volumen máximos configurables
  (TMS › Configuración › Tipos de vehículo). Un vehículo con capacidad propia
  usa la menor entre la suya y la de su tipo; sin capacidad propia, la del tipo.
- La carga de un viaje es su peso y volumen; la de un pedido se estima con los
  empaques del maestro (cajas completas primero, luego unidades sueltas).
- `exigir` bloquea la asignación de un vehículo cuando lo que ya lleva más la
  carga nueva supera su capacidad (con la tolerancia configurada).
- `sugerir` propone el tipo de vehículo más pequeño donde cabe la carga y los
  vehículos disponibles que la pueden llevar.
"""
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.tms import (
    EstadoViajeTMSEnum, EstadoVehiculoTMSEnum, TipoVehiculoTMSEnum, TMSParametro,
    TMSTipoVehiculoCapacidad, TMSVehiculo, TMSViaje,
)
from app.infrastructure.models.wms import WMSProducto, WMSProductoEmpaque

# Valores de referencia para empezar (Colombia). Cada empresa los ajusta.
DEFECTOS: Dict[str, Tuple[str, float, float]] = {
    "MOTOCICLETA":     ("Motocicleta",                       40,     0.15),
    "AUTOMOVIL":       ("Automóvil",                        350,     0.6),
    "CAMIONETA":       ("Camioneta",                        900,     3.0),
    "VAN":             ("Van / furgoneta",                 1500,     8.0),
    "CAMION_SENCILLO": ("Camión sencillo (C2)",            9000,    38.0),
    "REFRIGERADO":     ("Camión refrigerado",              8000,    32.0),
    "DOBLE_TROQUE":    ("Doble troque (C3)",              17000,    50.0),
    "REMOLQUE":        ("Remolque",                       10000,    45.0),
    "CARROTANQUE":     ("Carrotanque",                    30000,    36.0),
    "PORTACONTENEDOR": ("Portacontenedor",                28000,    67.0),
    "PLATAFORMA":      ("Plataforma",                     34000,    75.0),
    "SEMIRREMOLQUE":   ("Semirremolque",                  34000,    85.0),
    "TRACTOCAMION":    ("Tractocamión con semirremolque", 34000,    85.0),
}
NOMBRES = {k: v[0] for k, v in DEFECTOS.items()}
ACTIVOS = (EstadoViajeTMSEnum.ASIGNADO, EstadoViajeTMSEnum.EN_TRANSITO)


def _v(x):
    return x.value if hasattr(x, "value") else x


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return round(a / b * 100, 1) if a is not None and b else None


# ─── Tipos de vehículo ────────────────────────────────────────────────────────

async def tipos(db: AsyncSession) -> List[TMSTipoVehiculoCapacidad]:
    """Las capacidades por tipo; la primera vez se siembran los valores de referencia."""
    filas = {t.tipo: t for t in (await db.execute(select(TMSTipoVehiculoCapacidad))).scalars().all()}
    faltan = [t.value for t in TipoVehiculoTMSEnum if t.value not in filas]
    for t in faltan:
        _, kg, m3 = DEFECTOS.get(t, (t, None, None))
        filas[t] = TMSTipoVehiculoCapacidad(tipo=t, capacidad_kg=kg, volumen_m3=m3, activo=True)
        db.add(filas[t])
    if faltan:
        await db.flush()
    orden = list(DEFECTOS)
    return sorted(filas.values(), key=lambda t: orden.index(t.tipo) if t.tipo in orden else 99)


def tipo_dict(t: TMSTipoVehiculoCapacidad) -> dict:
    return {"tipo": t.tipo, "nombre": NOMBRES.get(t.tipo, t.tipo), "capacidad_kg": t.capacidad_kg,
            "volumen_m3": t.volumen_m3, "activo": t.activo}


async def capacidad_de(db: AsyncSession, veh: TMSVehiculo) -> Tuple[Optional[float], Optional[float]]:
    t = (await db.execute(select(TMSTipoVehiculoCapacidad).where(
        TMSTipoVehiculoCapacidad.tipo == _v(veh.tipo_vehiculo)))).scalar()
    def menor(propia, del_tipo):
        vals = [x for x in (propia, del_tipo) if x]
        return min(vals) if vals else None
    return (menor(veh.capacidad_kg, t.capacidad_kg if t else None),
            menor(veh.volumen_m3, t.volumen_m3 if t else None))


async def tolerancia_pct(db: AsyncSession) -> float:
    v = (await db.execute(select(TMSParametro.valor).where(TMSParametro.clave == "capacidad_tolerancia_pct"))).scalar()
    return float(v or 0)


async def carga_activa(db: AsyncSession, vehiculo_id: int, excluir_viaje_id: Optional[int] = None) -> Tuple[float, float]:
    q = select(func.coalesce(func.sum(TMSViaje.peso_kg), 0), func.coalesce(func.sum(TMSViaje.volumen_m3), 0)).where(
        TMSViaje.deleted_at.is_(None), TMSViaje.estado.in_(ACTIVOS), TMSViaje.vehiculo_id == vehiculo_id)
    if excluir_viaje_id:
        q = q.where(TMSViaje.id != excluir_viaje_id)
    kg, m3 = (await db.execute(q)).one()
    return float(kg or 0), float(m3 or 0)


# ─── Verificación ─────────────────────────────────────────────────────────────

async def verificar(db: AsyncSession, veh: TMSVehiculo, peso_kg: Optional[float], volumen_m3: Optional[float],
                    excluir_viaje_id: Optional[int] = None) -> dict:
    cap_kg, cap_m3 = await capacidad_de(db, veh)
    cargado_kg, cargado_m3 = await carga_activa(db, veh.id, excluir_viaje_id)
    tol = 1 + await tolerancia_pct(db) / 100
    total_kg, total_m3 = cargado_kg + (peso_kg or 0), cargado_m3 + (volumen_m3 or 0)
    motivos, avisos = [], []
    if cap_kg and total_kg > cap_kg * tol:
        motivos.append(f"peso {total_kg:,.0f} kg supera la capacidad de {cap_kg:,.0f} kg")
    if cap_m3 and total_m3 > cap_m3 * tol:
        motivos.append(f"volumen {total_m3:,.2f} m³ supera la capacidad de {cap_m3:,.2f} m³")
    if not cap_kg:
        avisos.append("el vehículo y su tipo no tienen capacidad de peso configurada")
    if not cap_m3:
        avisos.append("el vehículo y su tipo no tienen capacidad de volumen configurada")
    if not peso_kg:
        avisos.append("la carga no tiene peso calculado")
    if not volumen_m3:
        avisos.append("la carga no tiene volumen calculado")
    return {
        "vehiculo_id": veh.id, "placa": veh.placa, "tipo": _v(veh.tipo_vehiculo),
        "tipo_nombre": NOMBRES.get(_v(veh.tipo_vehiculo), _v(veh.tipo_vehiculo)),
        "capacidad_kg": cap_kg, "capacidad_m3": cap_m3,
        "cargado_kg": round(cargado_kg, 2), "cargado_m3": round(cargado_m3, 3),
        "carga_kg": peso_kg, "carga_m3": volumen_m3,
        "uso_kg_pct": _pct(total_kg, cap_kg), "uso_m3_pct": _pct(total_m3, cap_m3),
        "ok": not motivos, "motivos": motivos, "avisos": avisos,
    }


async def exigir(db: AsyncSession, veh: TMSVehiculo, peso_kg, volumen_m3, excluir_viaje_id=None) -> dict:
    r = await verificar(db, veh, peso_kg, volumen_m3, excluir_viaje_id)
    if not r["ok"]:
        raise HTTPException(409, f"El vehículo {veh.placa} ({r['tipo_nombre']}) no puede llevar esta carga: "
                                 + "; ".join(r["motivos"]) + ". Elija un vehículo más grande o divida la carga.")
    return r


# ─── Estimación de la carga a partir de productos ─────────────────────────────

async def estimar_carga(db: AsyncSession, lineas: Iterable[Tuple[int, float]]) -> dict:
    """Peso y volumen de una lista (producto_id, unidades): primero cajas o
    másters completas con sus medidas, el resto como unidades sueltas."""
    agrupado: Dict[int, float] = {}
    for pid, cant in lineas:
        if pid and cant and cant > 0:
            agrupado[pid] = agrupado.get(pid, 0) + float(cant)
    peso = vol = 0.0
    sin_peso, sin_volumen, detalle = [], [], []
    for pid, cant in agrupado.items():
        prod = await db.get(WMSProducto, pid)
        if not prod:
            continue
        emps = (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id == pid))).scalars().all()
        und = next((e for e in emps if e.nivel == "UNIDAD"), None)
        u_peso = prod.peso_kg or (und.peso_kg if und else None)
        u_vol = prod.volumen_m3 or (und and und.largo_cm and und.ancho_cm and und.alto_cm
                                    and und.largo_cm * und.ancho_cm * und.alto_cm / 1e6) or None
        restante, p_peso, p_vol, partes, falta_p, falta_v = cant, 0.0, 0.0, [], False, False
        for e in sorted((e for e in emps if e.nivel in ("ESTIBA", "MASTER", "CAJA") and (e.unidades or 0) > 1),
                        key=lambda e: -e.unidades):
            n = int(restante // e.unidades)
            if n <= 0:
                continue
            e_vol = e.largo_cm * e.ancho_cm * e.alto_cm / 1e6 if (e.largo_cm and e.ancho_cm and e.alto_cm) else (
                u_vol * e.unidades if u_vol else None)
            e_peso = e.peso_kg or (u_peso * e.unidades if u_peso else None)
            if e_vol is None and e_peso is None:
                continue
            p_vol += n * (e_vol or 0); p_peso += n * (e_peso or 0)
            falta_v |= e_vol is None; falta_p |= e_peso is None
            restante -= n * e.unidades
            partes.append(f"{n} {e.nivel.lower()} ×{e.unidades:g}")
        if restante > 1e-9:
            p_vol += restante * (u_vol or 0); p_peso += restante * (u_peso or 0)
            falta_v |= u_vol is None; falta_p |= u_peso is None
            partes.append(f"{restante:g} und")
        if falta_p:
            sin_peso.append(prod.sku)
        if falta_v:
            sin_volumen.append(prod.sku)
        peso += p_peso; vol += p_vol
        detalle.append({"sku": prod.sku, "nombre": prod.nombre, "unidades": cant, "como": " + ".join(partes),
                        "peso_kg": round(p_peso, 2), "volumen_m3": round(p_vol, 4)})
    return {"peso_kg": round(peso, 2), "volumen_m3": round(vol, 4), "sin_peso": sin_peso,
            "sin_volumen": sin_volumen, "detalle": detalle}


# ─── Sugerencia ───────────────────────────────────────────────────────────────

async def sugerir(db: AsyncSession, peso_kg: Optional[float], volumen_m3: Optional[float]) -> dict:
    tol = 1 + await tolerancia_pct(db) / 100
    peso_kg, volumen_m3 = peso_kg or 0, volumen_m3 or 0

    def cabe(kg, m3):
        return ((not peso_kg or (kg is not None and peso_kg <= kg * tol))
                and (not volumen_m3 or (m3 is not None and volumen_m3 <= m3 * tol)))

    lista = []
    for t in await tipos(db):
        if not t.activo:
            continue
        lista.append({**tipo_dict(t), "cabe": cabe(t.capacidad_kg, t.volumen_m3),
                      "uso_kg_pct": _pct(peso_kg, t.capacidad_kg), "uso_m3_pct": _pct(volumen_m3, t.volumen_m3)})
    lista.sort(key=lambda x: ((x["capacidad_kg"] or 1e12), (x["volumen_m3"] or 1e12)))
    recomendado = next((x for x in lista if x["cabe"]), None)

    vehiculos = []
    for v in (await db.execute(select(TMSVehiculo).where(
            TMSVehiculo.deleted_at.is_(None), TMSVehiculo.estado_operativo == EstadoVehiculoTMSEnum.DISPONIBLE))).scalars().all():
        cap_kg, cap_m3 = await capacidad_de(db, v)
        ckg, cm3 = await carga_activa(db, v.id)
        libre_kg = cap_kg - ckg if cap_kg else None
        libre_m3 = cap_m3 - cm3 if cap_m3 else None
        if cabe(libre_kg, libre_m3):
            vehiculos.append({"id": v.id, "placa": v.placa, "tipo": _v(v.tipo_vehiculo),
                              "tipo_nombre": NOMBRES.get(_v(v.tipo_vehiculo), _v(v.tipo_vehiculo)),
                              "capacidad_kg": cap_kg, "capacidad_m3": cap_m3,
                              "uso_kg_pct": _pct(ckg + peso_kg, cap_kg), "uso_m3_pct": _pct(cm3 + volumen_m3, cap_m3)})
    # Primero los que quedan más llenos: el vehículo justo, no el más grande.
    vehiculos.sort(key=lambda x: -max(x["uso_kg_pct"] or 0, x["uso_m3_pct"] or 0))
    return {"peso_kg": peso_kg, "volumen_m3": volumen_m3, "recomendado": recomendado, "tipos": lista,
            "vehiculos": vehiculos[:10], "tolerancia_pct": round((tol - 1) * 100, 1)}
