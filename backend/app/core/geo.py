"""
Ubicación en el mapa de bodegas, pedidos y paradas de los viajes.

DE DÓNDE SALEN LAS COORDENADAS
- La bodega: de su dirección y ciudad (o del punto que se fije a mano en el
  mapa de Configuración › Almacenes). Es el ORIGEN de todo lo que despacha.
- El pedido: de la dirección de compra que trae la solicitud del cliente
  (marketplace o tienda). Es el DESTINO de la entrega.
- Los viajes y sus paradas heredan esas coordenadas al crearse; lo que falte
  (viajes creados a mano, direcciones que aún no se ubicaban) lo completa el
  ciclo de fondo de este módulo.

CÓMO SE UBICA UNA DIRECCIÓN
Con Nominatim (OpenStreetMap), sin llave. Su política pide máximo una consulta
por segundo e identificar la aplicación; por eso hay una sola cola para todo el
proceso, caché en memoria y un ciclo de fondo con presupuesto de tiempo, en vez
de consultar mientras el usuario espera (salvo una bodega, que es una sola).

Primero se intenta la dirección completa; si no aparece, o aparece a más de
60 km de su ciudad (una «Calle 10» de otro municipio), se usa el centro de la
ciudad y se marca la precisión como CIUDAD: el punto es aproximado y la pantalla
lo dice. Si aparece la vía pero no la placa (frecuente con la nomenclatura
colombiana en OpenStreetMap) la precisión es VIA: también aproximada. Si ni la ciudad aparece, queda NO_ENCONTRADA y no se reintenta.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import time
import unicodedata
from typing import Optional

import httpx
from sqlalchemy import or_, select

log = logging.getLogger(__name__)

URL = "https://nominatim.openstreetmap.org/search"
AGENTE = "DailyLogistics/1.0 (gestion logistica)"
PAISES = {"colombia": "co", "ecuador": "ec", "peru": "pe", "panama": "pa", "venezuela": "ve", "mexico": "mx", "chile": "cl"}
RADIO_CIUDAD_KM = 60
INTERVALO = 90            # segundos entre vueltas del ciclo
PRESUPUESTO_S = 25        # tiempo máximo de consultas por cliente y vuelta

_cache: dict[str, Optional[tuple[float, float, bool]]] = {}
_cola = asyncio.Lock()
_ultima = 0.0


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


ABREVIATURAS = [
    (r"\b(cra|cr|kra|kr|carr)\.?\b", "Carrera"), (r"\b(cll|cl|clle)\.?\b", "Calle"), (r"\b(av|avda)\.?\b", "Avenida"),
    (r"\b(dg|diag)\.?\b", "Diagonal"), (r"\b(tv|tr|trans|transv)\.?\b", "Transversal"), (r"\b(ak)\.?\b", "Avenida Carrera"),
    (r"\b(ac)\.?\b", "Avenida Calle"),
]
# Lo que sobra después de la placa: apartamento, torre, local… confunde al buscador.
COMPLEMENTO = re.compile(r"\b(apto|apartamento|ap|torre|int|interior|oficina|of|local|piso|casa|bloque|conjunto|edificio|barrio|bodega)\b.*$", re.I)


def limpiar_direccion(d: str) -> str:
    d = COMPLEMENTO.sub("", d or "").strip(" ,.-")
    for patron, nombre in ABREVIATURAS:
        d = re.sub(patron, nombre, d, flags=re.I)
    # «Calle 13 # 68-45» / «Calle 13 No. 68-45» → «Calle 13 68-45»
    d = re.sub(r"\s*(#|n[o°º]\.?|num\.?)\s*", " ", d, flags=re.I)
    return re.sub(r"\s+", " ", d).strip(" ,")


def distancia_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


async def _consultar(q: str, pais: Optional[str], limite: int = 1) -> list[dict]:
    """Una consulta a Nominatim, en la cola única (≥1,1 s entre consultas)."""
    global _ultima
    params = {"q": q, "format": "json", "limit": limite, "addressdetails": 1}
    cc = PAISES.get(_sin_tildes((pais or "colombia").lower()).strip())
    if cc:
        params["countrycodes"] = cc
    async with _cola:
        espera = 1.1 - (time.monotonic() - _ultima)
        if espera > 0:
            await asyncio.sleep(espera)
        try:
            async with httpx.AsyncClient(timeout=12, headers={"User-Agent": AGENTE, "Accept-Language": "es"}) as c:
                r = await c.get(URL, params=params)
            return r.json() if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError) as e:
            log.info("Geocodificación no disponible: %s", e)
            raise
        finally:
            _ultima = time.monotonic()


async def _punto(q: str, pais: Optional[str]) -> Optional[tuple[float, float, bool]]:
    """(lat, lng, con_placa): con_placa = el resultado es el predio (trae número), no toda la vía."""
    clave = f"{q}|{pais}".lower()
    if clave in _cache:
        return _cache[clave]
    res = await _consultar(q, pais)
    p = (float(res[0]["lat"]), float(res[0]["lon"]), bool((res[0].get("address") or {}).get("house_number"))) if res else None
    _cache[clave] = p
    return p


async def ubicar(direccion: Optional[str], ciudad: Optional[str], pais: Optional[str] = "Colombia") -> dict:
    """{lat, lng, precision: DIRECCION | VIA | CIUDAD | NO_ENCONTRADA}. Lanza httpx.HTTPError sin conexión."""
    pais = pais or "Colombia"
    ciudad = (ciudad or "").strip()
    centro = await _punto(f"{ciudad}, {pais}", pais) if ciudad else None
    d = limpiar_direccion(direccion or "")
    # Con el barrio o la referencia que venga después de la coma, y sin ella.
    for intento in dict.fromkeys([d, d.split(",")[0].strip()]):
        if not (intento and re.search(r"\d", intento)):
            continue
        p = await _punto(f"{intento}, {ciudad}, {pais}" if ciudad else f"{intento}, {pais}", pais)
        if p and (not centro or distancia_km(p[:2], centro[:2]) <= RADIO_CIUDAD_KM):
            # Sin placa, el punto es el de la vía (puede quedar a varias cuadras).
            return {"lat": round(p[0], 6), "lng": round(p[1], 6), "precision": "DIRECCION" if p[2] else "VIA"}
    if centro:
        return {"lat": round(centro[0], 6), "lng": round(centro[1], 6), "precision": "CIUDAD"}
    return {"lat": None, "lng": None, "precision": "NO_ENCONTRADA"}


async def buscar(q: str, pais: Optional[str] = "Colombia") -> list[dict]:
    """Candidatos para un buscador (hasta 5)."""
    res = await _consultar(limpiar_direccion(q) or q, pais, limite=5)
    return [{"nombre": r.get("display_name"), "lat": round(float(r["lat"]), 6), "lng": round(float(r["lon"]), 6)} for r in res]


def _texto_parada(direccion: Optional[str]) -> Optional[str]:
    """Las paradas de origen guardan «Bodega X — Calle 1 # 2-3»: se usa lo de después de la raya."""
    if not direccion:
        return None
    return direccion.split(" — ")[-1].strip()


async def ubicar_almacen(alm) -> None:
    """Ubica la bodega si no tiene punto (o si se le borró al cambiar la dirección)."""
    if alm.lat is not None or alm.geo_precision == "MANUAL":
        return
    r = await ubicar(alm.direccion, alm.ciudad, alm.pais)
    alm.lat, alm.lng, alm.geo_precision = r["lat"], r["lng"], r["precision"]


# ─── Ciclo de fondo ──────────────────────────────────────────────────────────

async def sincronizar_bodegas(db) -> None:
    """Los viajes que aún no salen toman el punto actual de su bodega de origen
    (y de la de destino en los traslados): si se corrige el pin de la bodega,
    se corrige el mapa de sus viajes. Se reconoce la bodega por el nombre con
    que empieza la dirección («CEDI Bogotá — Cra 68 …»).

    Tres UPDATE por conjuntos que solo tocan las filas cuyo punto cambió: con
    miles de viajes programados, recorrerlos uno a uno en cada vuelta del ciclo
    bloqueaba filas y frenaba la creación de despachos."""
    from sqlalchemy import text
    sin_salir = "('PROGRAMADO', 'ASIGNADO')"
    await db.execute(text(f"""
        UPDATE tms_viaje v SET origen_lat = a.lat, origen_lng = a.lng
          FROM wms_almacenes a
         WHERE a.lat IS NOT NULL AND v.estado IN {sin_salir} AND v.deleted_at IS NULL
           AND (v.origen_direccion = a.nombre OR v.origen_direccion LIKE a.nombre || ' — %')
           AND (v.origen_lat IS DISTINCT FROM a.lat OR v.origen_lng IS DISTINCT FROM a.lng)"""))
    await db.execute(text(f"""
        UPDATE tms_viaje v SET destino_lat = a.lat, destino_lng = a.lng
          FROM wms_almacenes a
         WHERE a.lat IS NOT NULL AND v.estado IN {sin_salir} AND v.deleted_at IS NULL
           AND (v.destino_direccion = a.nombre OR v.destino_direccion LIKE a.nombre || ' — %')
           AND (v.destino_lat IS DISTINCT FROM a.lat OR v.destino_lng IS DISTINCT FROM a.lng)"""))
    await db.execute(text(f"""
        UPDATE tms_parada p SET lat = a.lat, lng = a.lng
          FROM wms_almacenes a, tms_viaje v
         WHERE v.id = p.viaje_id AND a.lat IS NOT NULL AND v.estado IN {sin_salir}
           AND (p.tipo IN ('ORIGEN', 'DESTINO') OR p.secuencia = 1)
           AND (p.direccion = a.nombre OR p.direccion LIKE a.nombre || ' — %')
           AND (p.lat IS DISTINCT FROM a.lat OR p.lng IS DISTINCT FROM a.lng)"""))
    await db.flush()


async def completar(db, presupuesto_s: float = PRESUPUESTO_S) -> int:
    """Ubica lo pendiente: bodegas, pedidos por despachar, viajes y paradas abiertas."""
    from app.infrastructure.models.tms import EstadoViajeTMSEnum, TMSParada, TMSViaje
    from app.infrastructure.models.wms import WMSAlmacen, WMSOrdenSalida

    fin = time.monotonic() + presupuesto_s
    hechos = 0
    queda = lambda: time.monotonic() < fin  # noqa: E731

    for a in (await db.execute(select(WMSAlmacen).where(WMSAlmacen.lat.is_(None), WMSAlmacen.geo_precision.is_(None)))).scalars():
        if not queda():
            break
        await ubicar_almacen(a); hechos += 1
    await db.commit()

    # Los pedidos más recientes primero: son los que están por despacharse.
    ordenes = (await db.execute(select(WMSOrdenSalida).where(
        WMSOrdenSalida.destino_lat.is_(None), WMSOrdenSalida.destino_geo.is_(None),
        WMSOrdenSalida.destino_ciudad.isnot(None)).order_by(WMSOrdenSalida.id.desc()).limit(200))).scalars().all()
    for o in ordenes:
        if not queda():
            break
        r = await ubicar(o.destino_direccion, o.destino_ciudad, "Colombia")
        o.destino_lat, o.destino_lng, o.destino_geo = r["lat"], r["lng"], r["precision"]
        hechos += 1
    await db.commit()

    terminados = (EstadoViajeTMSEnum.ENTREGADO, EstadoViajeTMSEnum.CANCELADO)
    await sincronizar_bodegas(db)
    viajes = {v.id: v for v in (await db.execute(select(TMSViaje).where(
        TMSViaje.estado.notin_(terminados), TMSViaje.deleted_at.is_(None),
        or_(TMSViaje.origen_lat.is_(None), TMSViaje.destino_lat.is_(None))).limit(100))).scalars()}
    paradas = (await db.execute(select(TMSParada).join(TMSViaje, TMSViaje.id == TMSParada.viaje_id).where(
        TMSParada.lat.is_(None), TMSViaje.estado.notin_(terminados)).order_by(TMSParada.viaje_id, TMSParada.secuencia).limit(300))).scalars().all()
    for p in paradas:
        if not queda():
            break
        r = await ubicar(_texto_parada(p.direccion), p.ciudad, "Colombia")
        if r["lat"] is not None:
            p.lat, p.lng = r["lat"], r["lng"]; hechos += 1
    await db.flush()
    for v in viajes.values():
        if not queda():
            break
        ps = (await db.execute(select(TMSParada).where(TMSParada.viaje_id == v.id).order_by(TMSParada.secuencia))).scalars().all()
        if v.origen_lat is None:
            r = {"lat": ps[0].lat, "lng": ps[0].lng} if ps and ps[0].lat is not None else (
                await ubicar(_texto_parada(v.origen_direccion), v.origen_ciudad) if v.origen_ciudad else {"lat": None, "lng": None})
            v.origen_lat, v.origen_lng = r["lat"], r["lng"]
        if v.destino_lat is None:
            r = {"lat": ps[-1].lat, "lng": ps[-1].lng} if len(ps) > 1 and ps[-1].lat is not None else (
                await ubicar(v.destino_direccion if v.num_entregas in (None, 1) else None, v.destino_ciudad)
                if v.destino_ciudad and not re.match(r"^\d+ destinos$", v.destino_ciudad) else {"lat": None, "lng": None})
            v.destino_lat, v.destino_lng = r["lat"], r["lng"]
        hechos += 1
    await db.commit()
    return hechos


async def ciclo() -> None:
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal
    from app.core.wms_ciclo_tareas import _esquemas
    import zlib
    from app.core.database import engine
    await asyncio.sleep(20)
    while True:
        try:
            for esq in await _esquemas():
                clave = zlib.crc32(f"geo:{esq}".encode())
                async with engine.connect() as candado:
                    if not (await candado.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": clave})).scalar():
                        continue
                    try:
                        async with AsyncSessionLocal(info={"esquema": esq}) as db:
                            if (await db.execute(text("SELECT to_regclass('wms_almacenes')"))).scalar():
                                await completar(db)
                    except httpx.HTTPError:
                        break                               # sin conexión: se intenta en la próxima vuelta
                    except Exception as e:  # noqa: BLE001 — un cliente con error no frena a los demás
                        log.warning("Ubicación en mapa (%s): %s", esq, e)
                    finally:
                        await candado.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": clave})
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Ubicación en mapa: %s", e)
        await asyncio.sleep(INTERVALO)
