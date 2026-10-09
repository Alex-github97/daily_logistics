"""
WMS · Constructor de bodega. Prefijo: /wms/layout

El layout es la bodega dibujada en metros: estanterías (selectivas, góndolas,
cantiléver), almacenamiento en piso, áreas, muros y columnas. Cada estructura
se configura con parámetros (módulos, posiciones por módulo, niveles, medidas)
y de ahí salen:

- las ubicaciones del WMS (se crean, se actualizan o se adoptan las que ya
  existen con el mismo código) — `POST /generar`, con simulación previa;
- la bodega 3D (`escena_layout`, que usa /wms/mapa/3d cuando hay layout).

El plano del almacén (el de /wms/mapa/plano) es solo el fondo para calcar,
escalado con `escala_m_px`.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSInventarioUbicacion, WMSLayout, WMSLayoutElemento, WMSLayoutPosicion, WMSMapaFoto, WMSPlano,
    WMSUbicacion, WMSZona,
)

router = APIRouter(prefix="/wms/layout", tags=["wms-layout"])

ESTANTERIAS = ("SELECTIVO", "GONDOLA", "CANTILEVER")
CON_POSICIONES = ESTANTERIAS + ("PISO",)
TIPOS = CON_POSICIONES + ("ZONA", "MURO", "COLUMNA", "POLIMURO", "POLIZONA")
FORMAS = ("POLIMURO", "POLIZONA")
TIPO_UBICACION = {"SELECTIVO": "PALLET", "CANTILEVER": "ESTANDAR", "GONDOLA": "ESTANDAR", "PISO": "SUELO"}
PATRON = "{pasillo}-{estanteria}-{posicion}-{nivel}"


# ─── Esquemas ────────────────────────────────────────────────────────────────

class PuntoIn(BaseModel):
    x: float = Field(ge=-5000, le=5000)
    y: float = Field(ge=-5000, le=5000)
    s: float = Field(0, ge=-2000, le=2000)        # flecha del arco hacia el siguiente punto


class FormaIn(BaseModel):
    puntos: List[PuntoIn]
    cerrado: bool = False


class ConfigIn(BaseModel):
    ancho_m: float = Field(gt=1, le=2000)
    largo_m: float = Field(gt=1, le=2000)
    escala_m_px: Optional[float] = Field(None, gt=0)
    plano_x_m: float = 0
    plano_y_m: float = 0
    patron_codigo: str = Field(PATRON, min_length=3, max_length=80)
    contorno: Optional[List[PuntoIn]] = None


class ElementoIn(BaseModel):
    id: Optional[int] = None
    clave: Optional[str] = None            # id temporal del navegador para los nuevos
    tipo: str
    nombre: Optional[str] = Field(None, max_length=60)
    pasillo: Optional[str] = Field(None, max_length=20)
    estanteria: Optional[str] = Field(None, max_length=20)
    zona_id: Optional[int] = None
    ubicacion_id: Optional[int] = None
    foto_id: Optional[int] = None
    categoria: Optional[str] = Field(None, max_length=30)
    color: Optional[str] = Field(None, max_length=9)
    x_m: float
    y_m: float
    rotacion: float = 0
    modulos: int = Field(1, ge=1, le=200)
    por_modulo: int = Field(1, ge=1, le=10)
    niveles: int = Field(1, ge=1, le=30)
    frente_cm: float = Field(270, gt=10, le=2000)
    fondo_cm: float = Field(100, gt=5, le=2000)
    alto_nivel_cm: float = Field(150, gt=10, le=1500)
    capacidad_kg: Optional[float] = Field(None, ge=0)
    largo_m: Optional[float] = Field(None, gt=0, le=2000)
    ancho_m: Optional[float] = Field(None, gt=0, le=2000)
    forma: Optional[FormaIn] = None


class LayoutIn(BaseModel):
    config: ConfigIn
    elementos: List[ElementoIn]


class GenerarIn(BaseModel):
    simular: bool = True
    # Las ubicaciones ya ligadas conservan su código (lo usan etiquetas, POS,
    # documentos); solo se renombran al patrón si se pide.
    renombrar: bool = False
    elemento_ids: Optional[List[int]] = None


# ─── Utilidades ──────────────────────────────────────────────────────────────

def posiciones_de(e) -> int:
    return e.modulos * e.por_modulo


def niveles_de(e) -> int:
    # En piso cada posición es una sola ubicación; los «niveles» son estibas apiladas.
    return 1 if e.tipo == "PISO" else e.niveles


def huella(e) -> tuple:
    """(largo, fondo) en metros, antes de rotar."""
    if e.tipo in CON_POSICIONES:
        return e.modulos * e.frente_cm / 100, e.fondo_cm / 100
    return e.largo_m or 4, e.ancho_m or (0.25 if e.tipo == "MURO" else 4)


def codigo_de(patron: str, alm: str, zona: str, pasillo, estanteria, nivel: int, posicion: int) -> str:
    try:
        return patron.format(almacen=alm, zona=zona, pasillo=pasillo or "", estanteria=estanteria or "",
                             nivel=nivel, posicion=posicion).strip("-_. ")
    except (KeyError, ValueError, IndexError) as ex:
        raise HTTPException(422, f"El patrón de código «{patron}» no es válido ({ex}). "
                                 "Use {almacen} {zona} {pasillo} {estanteria} {posicion} {nivel}.")


async def _almacen(db, almacen_id: int) -> WMSAlmacen:
    a = await db.get(WMSAlmacen, almacen_id)
    if a is None:
        raise HTTPException(404, "Almacén no encontrado.")
    return a


async def _config(db, almacen_id: int, crear: bool = False) -> Optional[WMSLayout]:
    c = (await db.execute(select(WMSLayout).where(WMSLayout.almacen_id == almacen_id))).scalar_one_or_none()
    if c is None and crear:
        c = WMSLayout(almacen_id=almacen_id, ancho_m=40, largo_m=30, plano_x_m=0, plano_y_m=0, patron_codigo=PATRON)
        db.add(c)
        await db.flush()
    return c


async def _existencias(db, ubicacion_ids) -> Dict[int, float]:
    ids = list(ubicacion_ids)
    if not ids:
        return {}
    filas = (await db.execute(select(
        WMSInventarioUbicacion.ubicacion_id,
        func.sum(WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada
                 + WMSInventarioUbicacion.cantidad_bloqueada)).where(
        WMSInventarioUbicacion.ubicacion_id.in_(ids)).group_by(WMSInventarioUbicacion.ubicacion_id))).all()
    return {u: float(t or 0) for u, t in filas}


def _elem_dict(e: WMSLayoutElemento) -> dict:
    return {k: getattr(e, k) for k in (
        "id", "tipo", "nombre", "pasillo", "estanteria", "zona_id", "ubicacion_id", "foto_id", "categoria", "color",
        "x_m", "y_m", "rotacion", "modulos", "por_modulo", "niveles", "frente_cm", "fondo_cm", "alto_nivel_cm",
        "capacidad_kg", "largo_m", "ancho_m", "orden", "forma")}


# ─── Leer y guardar ──────────────────────────────────────────────────────────

@router.get("")
async def ver_layout(almacen_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from app.api.v1.endpoints.wms_mapa import _derivado, _estado_ubicaciones, _existe
    alm = await _almacen(db, almacen_id)
    c = await _config(db, almacen_id)
    elementos = (await db.execute(select(WMSLayoutElemento).where(WMSLayoutElemento.almacen_id == almacen_id)
                                  .order_by(WMSLayoutElemento.orden, WMSLayoutElemento.id))).scalars().all()
    pos = (await db.execute(select(WMSLayoutPosicion).where(
        WMSLayoutPosicion.elemento_id.in_([e.id for e in elementos] or [0])))).scalars().all()
    por_elem = defaultdict(list)
    for p in pos:
        por_elem[p.elemento_id].append(p)
    uids = {p.ubicacion_id for p in pos} | {e.ubicacion_id for e in elementos if e.ubicacion_id}
    est = await _estado_ubicaciones(db, almacen_id, uids) if uids else {}
    salida = []
    for e in elementos:
        d = _elem_dict(e)
        ps = [p for p in por_elem[e.id] if p.nivel <= niveles_de(e) and p.posicion <= posiciones_de(e)]
        ocup = sum(1 for p in ps if est.get(p.ubicacion_id, {}).get("estado") not in (None, "VACIA"))
        codigos = sorted(est[p.ubicacion_id]["codigo"] or "" for p in ps if p.ubicacion_id in est)
        d.update(vinculadas=len(ps), sobrantes=len(por_elem[e.id]) - len(ps), ocupadas=ocup,
                 ocupacion_pct=round(ocup / len(ps) * 100, 1) if ps else None,
                 codigos=[codigos[0], codigos[-1]] if codigos else [])
        if e.ubicacion_id and e.ubicacion_id in est:
            d.update(ocupacion_area=est[e.ubicacion_id])
        salida.append(d)
    plano = (await db.execute(select(WMSPlano).where(WMSPlano.almacen_id == almacen_id))).scalar_one_or_none()
    zonas = (await db.execute(select(WMSZona).where(WMSZona.almacen_id == almacen_id, WMSZona.activo.is_(True))
                              .order_by(WMSZona.codigo))).scalars().all()
    areas = (await db.execute(select(WMSUbicacion).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
        WMSZona.almacen_id == almacen_id, WMSUbicacion.activo.is_(True), WMSUbicacion.estanteria.is_(None))
        .order_by(WMSUbicacion.codigo))).scalars().all()
    fotos = (await db.execute(select(WMSMapaFoto).where(WMSMapaFoto.almacen_id == almacen_id)
                              .order_by(WMSMapaFoto.nombre))).scalars().all()
    return {
        "almacen": {"id": alm.id, "codigo": alm.codigo, "nombre": alm.nombre},
        "config": {"ancho_m": c.ancho_m, "largo_m": c.largo_m, "escala_m_px": c.escala_m_px, "plano_x_m": c.plano_x_m,
                   "plano_y_m": c.plano_y_m, "patron_codigo": c.patron_codigo, "contorno": c.contorno} if c else None,
        "elementos": salida,
        "plano": {"id": plano.id, "ancho": plano.ancho, "alto": plano.alto,
                  "vectorizado": _existe(_derivado(plano.archivo, ".svg"))} if plano else None,
        "zonas": [{"id": z.id, "codigo": z.codigo, "nombre": z.nombre, "tipo": z.tipo} for z in zonas],
        "ubicaciones_area": [{"id": u.id, "codigo": u.codigo} for u in areas],
        "fotos": [{"id": f.id, "nombre": f.nombre} for f in fotos],
    }


@router.put("")
async def guardar_layout(almacen_id: int, data: LayoutIn, db: AsyncSession = Depends(get_db),
                         _=Depends(get_current_user)):
    """Guarda el layout completo. Lo que no viene se quita; quitar (o achicar)
    una estructura con mercancía en las posiciones que desaparecen se rechaza."""
    await _almacen(db, almacen_id)
    codigo_de(data.config.patron_codigo, "ALM", "ZON", "A", "01", 1, 1)   # valida el patrón
    if data.config.contorno is not None and 0 < len(data.config.contorno) < 3:
        raise HTTPException(422, "El contorno de la bodega necesita al menos 3 puntos.")
    c = await _config(db, almacen_id, crear=True)
    for k, v in data.config.model_dump().items():
        setattr(c, k, v)
    c.contorno = c.contorno or None

    zonas_ok = set((await db.execute(select(WMSZona.id).where(WMSZona.almacen_id == almacen_id))).scalars())
    actuales = {e.id: e for e in (await db.execute(select(WMSLayoutElemento).where(
        WMSLayoutElemento.almacen_id == almacen_id))).scalars()}
    pos = (await db.execute(select(WMSLayoutPosicion).where(
        WMSLayoutPosicion.elemento_id.in_(list(actuales) or [0])))).scalars().all()
    stock = await _existencias(db, {p.ubicacion_id for p in pos})
    por_elem = defaultdict(list)
    for p in pos:
        por_elem[p.elemento_id].append(p)

    def con_mercancia(eid, niveles=0, posiciones=0) -> List[WMSLayoutPosicion]:
        return [p for p in por_elem[eid] if (p.nivel > niveles or p.posicion > posiciones) and stock.get(p.ubicacion_id, 0) > 0]

    vienen = {d.id for d in data.elementos if d.id}
    desactivadas = 0
    for eid, e in actuales.items():
        if eid not in vienen:
            if con_mercancia(eid):
                raise HTTPException(409, f"«{e.nombre or e.tipo}» tiene mercancía en sus ubicaciones: muévala antes de quitar la estructura.")
            for p in por_elem[eid]:
                u = await db.get(WMSUbicacion, p.ubicacion_id)
                if u and u.activo:
                    u.activo = False
                    desactivadas += 1
            await db.delete(e)

    ids = {}
    for orden, d in enumerate(data.elementos):
        if d.tipo not in TIPOS:
            raise HTTPException(422, f"Tipo de estructura desconocido: {d.tipo}.")
        if d.tipo in FORMAS:
            minimo = 2 if d.tipo == "POLIMURO" else 3
            if not d.forma or len(d.forma.puntos) < minimo:
                raise HTTPException(422, f"«{d.nombre or d.tipo}» necesita al menos {minimo} puntos.")
        if d.zona_id and d.zona_id not in zonas_ok:
            raise HTTPException(422, f"La zona de «{d.nombre or d.tipo}» no es de este almacén.")
        campos = d.model_dump(exclude={"id", "clave"})
        if d.id:
            e = actuales.get(d.id)
            if e is None:
                raise HTTPException(404, f"La estructura {d.id} no es de este almacén.")
            prueba = WMSLayoutElemento(**campos)
            perdidas = con_mercancia(e.id, niveles_de(prueba), posiciones_de(prueba))
            if perdidas:
                raise HTTPException(409, f"«{d.nombre or d.tipo}»: no se puede achicar, hay mercancía en "
                                         f"{len(perdidas)} posiciones que dejarían de existir.")
        else:
            e = WMSLayoutElemento(almacen_id=almacen_id)
            db.add(e)
        for k, v in campos.items():
            setattr(e, k, v)
        e.orden = orden
        await db.flush()
        if d.clave:
            ids[d.clave] = e.id
    await db.flush()
    resp = await ver_layout(almacen_id, db)
    resp.update(ids=ids, desactivadas=desactivadas)
    return resp


# ─── Generar las ubicaciones del WMS ─────────────────────────────────────────

@router.post("/generar")
async def generar_ubicaciones(almacen_id: int, data: GenerarIn, db: AsyncSession = Depends(get_db),
                              _=Depends(get_current_user)):
    """Crea, actualiza o adopta (por código) la ubicación de cada posición de
    cada estructura; las posiciones que sobran se desactivan si están vacías.
    Con `simular` solo dice lo que haría."""
    alm = await _almacen(db, almacen_id)
    c = await _config(db, almacen_id)
    if c is None:
        raise HTTPException(422, "Guarde el layout antes de generar las ubicaciones.")
    q = select(WMSLayoutElemento).where(WMSLayoutElemento.almacen_id == almacen_id,
                                        WMSLayoutElemento.tipo.in_(CON_POSICIONES)).order_by(WMSLayoutElemento.orden)
    if data.elemento_ids:
        q = q.where(WMSLayoutElemento.id.in_(data.elemento_ids))
    elementos = (await db.execute(q)).scalars().all()
    zonas = {z.id: z for z in (await db.execute(select(WMSZona).where(WMSZona.almacen_id == almacen_id))).scalars()}
    pos = (await db.execute(select(WMSLayoutPosicion).where(
        WMSLayoutPosicion.elemento_id.in_([e.id for e in elementos] or [0])))).scalars().all()
    enlazada = {(p.elemento_id, p.nivel, p.posicion): p for p in pos}
    # Ubicaciones ya tomadas por otra estructura (de cualquier almacén).
    tomadas = {u: eid for eid, u in (await db.execute(select(WMSLayoutPosicion.elemento_id, WMSLayoutPosicion.ubicacion_id))).all()}
    por_codigo = {u.codigo: u for u in (await db.execute(select(WMSUbicacion))).scalars()}
    por_id = {u.id: u for u in por_codigo.values()}
    stock = await _existencias(db, {p.ubicacion_id for p in pos})
    planeados = set()
    resumen, conflictos = [], []
    acciones = []   # (accion, elemento, nivel, posicion, ubicacion|None, codigo, enlace|None)

    for e in elementos:
        r = {"elemento_id": e.id, "nombre": e.nombre or f"{e.pasillo}-{e.estanteria}", "crear": 0, "actualizar": 0,
             "adoptar": 0, "desactivar": 0, "renombrar": 0, "conflictos": 0, "codigos": []}
        resumen.append(r)
        zona = zonas.get(e.zona_id)
        if zona is None:
            conflictos.append({"elemento": r["nombre"], "detalle": "No tiene zona del WMS asignada."})
            r["conflictos"] += 1
            continue
        for n in range(1, niveles_de(e) + 1):
            for p in range(1, posiciones_de(e) + 1):
                cod = codigo_de(c.patron_codigo, alm.codigo, zona.codigo, e.pasillo, e.estanteria, n, p)
                link = enlazada.get((e.id, n, p))
                u = por_id.get(link.ubicacion_id) if link else None
                renombra = bool(u and u.codigo != cod)
                if renombra and not data.renombrar:
                    cod, renombra = u.codigo, False
                if len(cod) > 30:
                    conflictos.append({"elemento": r["nombre"], "detalle": f"El código «{cod}» pasa de 30 caracteres."})
                    r["conflictos"] += 1
                    continue
                if cod in planeados:
                    conflictos.append({"elemento": r["nombre"], "detalle": f"El código «{cod}» se repite: revise pasillo, estantería y patrón."})
                    r["conflictos"] += 1
                    continue
                planeados.add(cod)
                r["codigos"] = [r["codigos"][0], cod] if r["codigos"] else [cod, cod]
                existente = por_codigo.get(cod)
                if link:
                    if renombra:
                        if existente is not None and existente.id != u.id:
                            conflictos.append({"elemento": r["nombre"], "detalle": f"No se puede renombrar {u.codigo} a {cod}: ese código ya existe."})
                            r["conflictos"] += 1
                            continue
                        r["renombrar"] += 1
                    acciones.append(("actualizar", e, n, p, u, cod, link))
                    r["actualizar"] += 1
                elif existente is not None:
                    if tomadas.get(existente.id):
                        conflictos.append({"elemento": r["nombre"], "detalle": f"{cod} ya es de otra estructura del layout."})
                        r["conflictos"] += 1
                        continue
                    if existente.zona_id not in zonas:
                        conflictos.append({"elemento": r["nombre"], "detalle": f"{cod} ya existe en otro almacén: cambie el patrón (p. ej. con {{almacen}})."})
                        r["conflictos"] += 1
                        continue
                    acciones.append(("adoptar", e, n, p, existente, cod, None))
                    r["adoptar"] += 1
                else:
                    acciones.append(("crear", e, n, p, None, cod, None))
                    r["crear"] += 1
        for (eid, n, p), link in enlazada.items():
            if eid == e.id and (n > niveles_de(e) or p > posiciones_de(e)):
                if stock.get(link.ubicacion_id, 0) > 0:
                    u = por_id.get(link.ubicacion_id)
                    conflictos.append({"elemento": r["nombre"], "detalle": f"{u.codigo if u else link.ubicacion_id} sobra pero tiene mercancía."})
                    r["conflictos"] += 1
                else:
                    acciones.append(("desactivar", e, n, p, por_id.get(link.ubicacion_id), None, link))
                    r["desactivar"] += 1

    if not data.simular:
        for accion, e, n, p, u, cod, link in acciones:
            if accion == "desactivar":
                if u is not None:
                    u.activo = False
                await db.delete(link)
                continue
            if u is None:
                u = WMSUbicacion(codigo=cod, zona_id=e.zona_id)
                db.add(u)
            frente = e.frente_cm / e.por_modulo
            alto = e.alto_nivel_cm * (e.niveles if e.tipo == "PISO" else 1)
            u.codigo, u.zona_id, u.activo = cod, e.zona_id, True
            u.pasillo, u.estanteria, u.nivel, u.posicion = e.pasillo, e.estanteria, str(n), str(p)
            u.tipo = TIPO_UBICACION.get(e.tipo, "ESTANDAR")
            u.largo_cm, u.ancho_cm, u.alto_cm = frente, e.fondo_cm, alto
            u.capacidad_m3 = round(frente * e.fondo_cm * alto / 1e6, 4)
            u.capacidad_kg = e.capacidad_kg
            await db.flush()
            if link is None:
                db.add(WMSLayoutPosicion(elemento_id=e.id, nivel=n, posicion=p, ubicacion_id=u.id))
            else:
                link.ubicacion_id = u.id
        await db.flush()

    tot = defaultdict(int)
    for r in resumen:
        for k in ("crear", "actualizar", "adoptar", "desactivar", "renombrar", "conflictos"):
            tot[k] += r[k]
    return {"simulado": data.simular, "totales": tot, "elementos": resumen, "conflictos": conflictos[:200]}


# ─── Estado de una estructura (vista de frente) ──────────────────────────────

@router.get("/estructuras")
async def listar_estructuras(almacen_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Las estructuras con posiciones del layout, con su ocupación (para la
    lista de la pestaña Estanterías)."""
    datos = await ver_layout(almacen_id, db)
    return [{k: e[k] for k in ("id", "tipo", "nombre", "pasillo", "estanteria", "modulos", "por_modulo", "niveles",
                                "foto_id", "vinculadas", "ocupadas", "ocupacion_pct", "zona_id")}
            | {"nombre": e["nombre"] or "-".join(x for x in (e["pasillo"], e["estanteria"]) if x),
               "posiciones": e["modulos"] * e["por_modulo"], "niveles_vista": 1 if e["tipo"] == "PISO" else e["niveles"]}
            for e in datos["elementos"] if e["tipo"] in CON_POSICIONES]


@router.get("/estructuras/{eid}/estado")
async def estado_estructura(eid: int, producto_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
                            _=Depends(get_current_user)):
    """Cada posición (nivel × posición) de la estructura con su ubicación,
    ocupación y contenido."""
    from app.api.v1.endpoints.wms_mapa import _estado_ubicaciones
    e = await db.get(WMSLayoutElemento, eid)
    if e is None or e.tipo not in CON_POSICIONES:
        raise HTTPException(404, "Estructura no encontrada.")
    pos = (await db.execute(select(WMSLayoutPosicion).where(WMSLayoutPosicion.elemento_id == eid))).scalars().all()
    enl = {(p.nivel, p.posicion): p.ubicacion_id for p in pos}
    est = await _estado_ubicaciones(db, e.almacen_id, set(enl.values()), producto_id) if enl else {}
    celdas = []
    for n in range(1, niveles_de(e) + 1):
        for p in range(1, posiciones_de(e) + 1):
            uid = enl.get((n, p))
            x = est.get(uid) if uid else None
            celdas.append({"nivel": n, "posicion": p, "ubicacion_id": uid,
                           **(x if x else {"codigo": None, "unidades": 0, "ocupacion_pct": None, "estado": "SIN_ASIGNAR",
                                           "contenido": [], "resaltar": False})})
    resumen = defaultdict(int)
    for c in celdas:
        resumen[c["estado"]] += 1
    zona = await db.get(WMSZona, e.zona_id) if e.zona_id else None
    largo, fondo = huella(e)
    return {"estructura": _elem_dict(e) | {"nombre": e.nombre or "-".join(x for x in (e.pasillo, e.estanteria) if x),
                                           "zona": zona.codigo if zona else None, "largo_m": largo, "fondo_m": fondo,
                                           "posiciones": posiciones_de(e), "niveles_vista": niveles_de(e)},
            "celdas": celdas, "resumen": resumen}


# ─── Importar lo que ya existe ───────────────────────────────────────────────

@router.post("/importar")
async def importar(almacen_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Arma el layout desde las ubicaciones que ya existen (agrupadas por
    pasillo y estantería) y, si hay fotos calibradas con marca en el plano,
    con la posición y la escala del mapa actual."""
    from app.api.v1.endpoints.wms_mapa import escena_fotos
    await _almacen(db, almacen_id)
    if (await db.execute(select(func.count(WMSLayoutElemento.id)).where(WMSLayoutElemento.almacen_id == almacen_id))).scalar():
        raise HTTPException(409, "Este almacén ya tiene layout: impórtelo solo sobre un layout vacío.")
    ubic = (await db.execute(select(WMSUbicacion).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(
        WMSZona.almacen_id == almacen_id, WMSUbicacion.activo.is_(True)))).scalars().all()
    grupos = defaultdict(list)
    for u in ubic:
        if u.pasillo and u.estanteria and (u.nivel or "").isdigit() and (u.posicion or "").isdigit():
            grupos[(u.pasillo, u.estanteria)].append(u)
    if not grupos:
        raise HTTPException(422, "No hay ubicaciones con pasillo, estantería, nivel y posición para importar.")
    mapa = await escena_fotos(db, almacen_id)
    lugar = {(r["pasillo"], r["estanteria"]): r for r in mapa["racks"] if r.get("pasillo") and r.get("estanteria")}
    plano = (await db.execute(select(WMSPlano).where(WMSPlano.almacen_id == almacen_id))).scalar_one_or_none()
    c = await _config(db, almacen_id, crear=True)
    piso = mapa.get("piso")
    if piso and piso.get("plano_id") and plano:
        c.ancho_m, c.largo_m = round(piso["ancho_m"], 2), round(piso["largo_m"], 2)
        c.escala_m_px = piso["ancho_m"] / plano.ancho
    mediana = lambda us, a, d: statistics.median([getattr(u, a) for u in us if getattr(u, a)]) if any(getattr(u, a) for u in us) else d
    sueltos_y = 3.0
    for orden, ((pas, est), us) in enumerate(sorted(grupos.items())):
        niveles = max(int(u.nivel) for u in us)
        posiciones = max(int(u.posicion) for u in us)
        fondo = mediana(us, "ancho_cm", 100)
        tipo = "GONDOLA" if fondo <= 60 else "SELECTIVO"
        e = WMSLayoutElemento(almacen_id=almacen_id, tipo=tipo, nombre=f"{pas}-{est}", pasillo=pas, estanteria=est,
                              zona_id=statistics.mode([u.zona_id for u in us]), modulos=posiciones, por_modulo=1,
                              niveles=niveles, frente_cm=mediana(us, "largo_cm", 270), fondo_cm=fondo,
                              alto_nivel_cm=mediana(us, "alto_cm", 150), capacidad_kg=mediana(us, "capacidad_kg", None),
                              orden=orden)
        r = lugar.get((pas, est))
        if r and piso and piso.get("plano_id"):
            e.x_m, e.y_m, e.rotacion, e.foto_id = round(r["x"], 2), round(r["z"], 2), r["rotacion"], r["foto_id"]
        else:
            e.x_m, e.y_m, e.rotacion = 3 + e.modulos * e.frente_cm / 200, sueltos_y, 0
            sueltos_y += 3.5
            c.largo_m = max(c.largo_m, sueltos_y + 2)
            c.ancho_m = max(c.ancho_m, e.modulos * e.frente_cm / 100 + 6)
        db.add(e)
        await db.flush()
        for u in us:
            db.add(WMSLayoutPosicion(elemento_id=e.id, nivel=int(u.nivel), posicion=int(u.posicion), ubicacion_id=u.id))
    await db.flush()
    return await ver_layout(almacen_id, db)


# ─── Bodega 3D desde el layout ───────────────────────────────────────────────

async def escena_layout(db, almacen_id: int, producto_id: Optional[int] = None) -> Optional[dict]:
    from app.api.v1.endpoints.wms_mapa import _estado_ubicaciones
    c = await _config(db, almacen_id)
    if c is None:
        return None
    elementos = (await db.execute(select(WMSLayoutElemento).where(WMSLayoutElemento.almacen_id == almacen_id)
                                  .order_by(WMSLayoutElemento.orden, WMSLayoutElemento.id))).scalars().all()
    if not elementos:
        return None
    pos = (await db.execute(select(WMSLayoutPosicion).where(
        WMSLayoutPosicion.elemento_id.in_([e.id for e in elementos])))).scalars().all()
    enl = {(p.elemento_id, p.nivel, p.posicion): p.ubicacion_id for p in pos}
    uids = set(enl.values()) | {e.ubicacion_id for e in elementos if e.ubicacion_id}
    est = await _estado_ubicaciones(db, almacen_id, uids, producto_id) if uids else {}
    racks, areas = [], []
    for e in elementos:
        largo, fondo = huella(e)
        if e.tipo not in CON_POSICIONES:
            a = est.get(e.ubicacion_id) if e.ubicacion_id else None
            areas.append({"id": f"e{e.id}", "elemento_id": e.id, "tipo": e.tipo, "nombre": e.nombre, "categoria": e.categoria,
                          "color": e.color, "x": e.x_m, "z": e.y_m, "largo_m": largo, "ancho_m": fondo, "rotacion": e.rotacion,
                          "ocupacion": a, "forma": e.forma, "espesor_m": (e.fondo_cm or 20) / 100})
            continue
        niv, tot = niveles_de(e), posiciones_de(e)
        lista, ocupadas, vinc = [], 0, 0
        for n in range(1, niv + 1):
            for p in range(1, tot + 1):
                uid = enl.get((e.id, n, p))
                x = est.get(uid) if uid else None
                vinc += bool(uid)
                ocupada = bool(x and x["estado"] != "VACIA")
                ocupadas += ocupada
                lista.append({"nivel": n, "posicion": p, "ubicacion_id": uid, "codigo": x["codigo"] if x else None,
                              "estado": x["estado"] if x else "SIN_ASIGNAR", "ocupacion_pct": x["ocupacion_pct"] if x else None,
                              "unidades": x["unidades"] if x else 0, "contenido": x["contenido"][:3] if x else [],
                              "resaltar": bool(x and x["resaltar"])})
        total = vinc or niv * tot
        racks.append({"id": f"e{e.id}", "elemento_id": e.id, "foto_id": e.foto_id, "tipo": e.tipo, "color": e.color,
                      "nombre": e.nombre or f"{e.pasillo or ''}-{e.estanteria or ''}".strip("-"),
                      "pasillo": e.pasillo, "estanteria": e.estanteria,
                      "niveles": niv, "niveles_apilados": e.niveles if e.tipo == "PISO" else None,
                      "posiciones": tot, "por_modulo": e.por_modulo,
                      "frente_m": e.frente_cm / 100 / e.por_modulo, "fondo_m": fondo, "alto_nivel_m": e.alto_nivel_cm / 100,
                      "largo_m": largo, "alto_m": e.alto_nivel_cm / 100 * e.niveles,
                      "ocupadas": ocupadas, "celdas_total": total, "ocupacion_pct": round(ocupadas / total * 100, 1) if total else 0,
                      "unidades": sum(x["unidades"] for x in lista), "x": e.x_m, "z": e.y_m, "rotacion": e.rotacion,
                      "celdas": lista})
    plano = (await db.execute(select(WMSPlano).where(WMSPlano.almacen_id == almacen_id))).scalar_one_or_none()
    piso = {"ancho_m": c.ancho_m, "largo_m": c.largo_m, "plano_id": None, "plano_rect": None, "contorno": c.contorno}
    if plano and c.escala_m_px:
        piso.update(plano_id=plano.id, plano_rect={"x": c.plano_x_m, "y": c.plano_y_m,
                                                   "w": plano.ancho * c.escala_m_px, "h": plano.alto * c.escala_m_px})
    tot = sum(r["celdas_total"] for r in racks)
    return {"piso": piso, "racks": racks, "areas": areas, "origen": "layout",
            "resumen": {"estanterias": len(racks), "posiciones": tot, "ocupadas": sum(r["ocupadas"] for r in racks),
                        "unidades": sum(r["unidades"] for r in racks)}}
