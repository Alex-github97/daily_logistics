"""
WMS · Cubicaje: empaques por producto, cubicadores (estación ESP32), sus
mediciones y calibración, armado de estibas y ocupación cúbica.
Prefijo: /wms

El cubicador se autentica con un token propio (tipo «cubicador»): no es una
sesión de usuario y no sirve como tal —`get_current_user` exige tipo
«access»—. Se guarda solo su huella; emitir uno nuevo revoca el anterior.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from statistics import median
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_cubicaje as cub
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.core.security import decode_token
from app.core.tenant import esquema_actual
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSCubicador, WMSInventarioUbicacion, WMSMedicion, WMSProducto, WMSProductoEmpaque, WMSUbicacion, WMSZona,
)

router = APIRouter(prefix="/wms", tags=["wms-cubicaje"])
NIVELES = ("UNIDAD", "CAJA", "MASTER", "ESTIBA")


def _ahora():
    return datetime.now(timezone.utc)


def _huella(jti: str) -> str:
    return hashlib.sha256(jti.encode()).hexdigest()


def _cal(c: WMSCubicador) -> dict:
    return {"base_x_mm": c.base_x_mm, "base_y_mm": c.base_y_mm, "base_z_mm": c.base_z_mm,
            "escala_x": c.escala_x, "escala_y": c.escala_y, "escala_z": c.escala_z,
            "tara_crudo": c.tara_crudo, "escala_peso": c.escala_peso}


def _cub_dict(c: WMSCubicador) -> dict:
    cal = c.calibracion or {}
    return {"id": c.id, "codigo": c.codigo, "nombre": c.nombre, "almacen_id": c.almacen_id, "activo": c.activo,
            "tiene_token": bool(c.token_huella), "token_emitido_en": c.token_emitido_en.isoformat() if c.token_emitido_en else None,
            "ultima_conexion": c.ultima_conexion.isoformat() if c.ultima_conexion else None, "firmware": c.firmware,
            "tolerancia_mm": c.tolerancia_mm, "notas": c.notas, **_cal(c),
            "calibrado": {"x": c.base_x_mm is not None, "y": c.base_y_mm is not None, "z": c.base_z_mm is not None,
                          "peso": c.escala_peso is not None},
            "muestras": {k: len(v) for k, v in cal.items()}}


# ── Autenticación del dispositivo ────────────────────────────────────────────

async def cubicador_actual(request: Request, db: AsyncSession = Depends(get_db)) -> WMSCubicador:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Falta el token del cubicador.")
    datos = decode_token(auth[7:])
    if datos.get("type") != "cubicador" or not str(datos.get("sub", "")).startswith("cub:"):
        raise HTTPException(401, "Ese token no es de un cubicador.")
    c = await db.get(WMSCubicador, int(str(datos["sub"])[4:]))
    if c is None or not c.activo or not c.token_huella or c.token_huella != _huella(datos.get("jti", "")):
        raise HTTPException(401, "Token de cubicador revocado o cubicador inactivo.")
    c.ultima_conexion = _ahora()
    return c


class LecturasIn(BaseModel):
    lecturas: Dict[str, List[float]]
    firmware: Optional[str] = Field(default=None, max_length=30)


@router.get("/cubicador/estado")
async def estado_dispositivo(c: WMSCubicador = Depends(cubicador_actual)):
    return {"codigo": c.codigo, "nombre": c.nombre, "tolerancia_mm": c.tolerancia_mm,
            "calibrado": _cub_dict(c)["calibrado"]}


@router.post("/cubicador/lecturas", status_code=201)
async def recibir_lecturas(data: LecturasIn, db: AsyncSession = Depends(get_db),
                           c: WMSCubicador = Depends(cubicador_actual)):
    if not any(data.lecturas.get(k) for k in ("x", "y", "z", "peso")):
        raise HTTPException(422, "La medición no trae lecturas.")
    if data.firmware:
        c.firmware = data.firmware
    m = cub.procesar_lecturas(data.lecturas, _cal(c), c.tolerancia_mm)
    med = WMSMedicion(cubicador_id=c.id, lecturas=data.lecturas, largo_cm=m.largo_cm, ancho_cm=m.ancho_cm,
                      alto_cm=m.alto_cm, peso_kg=m.peso_kg, dispersion_mm=m.dispersion_mm, estable=m.estable,
                      estado="PENDIENTE")
    db.add(med)
    await db.flush()
    return {"id": med.id, "largo_cm": m.largo_cm, "ancho_cm": m.ancho_cm, "alto_cm": m.alto_cm,
            "peso_kg": m.peso_kg, "estable": m.estable, "dispersion_mm": m.dispersion_mm, "avisos": m.avisos}


# ── Administración de cubicadores ────────────────────────────────────────────

class CubicadorIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=120)
    almacen_id: Optional[int] = None
    activo: bool = True
    tolerancia_mm: float = Field(default=2.0, gt=0, le=20)
    notas: Optional[str] = None


@router.get("/cubicadores")
async def listar_cubicadores(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return [_cub_dict(c) for c in (await db.execute(select(WMSCubicador).order_by(WMSCubicador.codigo))).scalars()]


@router.post("/cubicadores", status_code=201)
async def crear_cubicador(data: CubicadorIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_supervisor)):
    if (await db.execute(select(WMSCubicador.id).where(WMSCubicador.codigo == data.codigo))).first():
        raise HTTPException(409, "Ya hay un cubicador con ese código.")
    c = WMSCubicador(**data.model_dump())
    db.add(c)
    await db.flush()
    return _cub_dict(c)


async def _cubicador(db, cid) -> WMSCubicador:
    c = await db.get(WMSCubicador, cid)
    if c is None:
        raise HTTPException(404, "Cubicador no encontrado.")
    return c


@router.put("/cubicadores/{cid}")
async def editar_cubicador(cid: int, data: CubicadorIn, db: AsyncSession = Depends(get_db),
                           _: Usuario = Depends(require_supervisor)):
    c = await _cubicador(db, cid)
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    return _cub_dict(c)


@router.post("/cubicadores/{cid}/token")
async def emitir_token(cid: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_supervisor)):
    """Emite el token del dispositivo. Se muestra UNA vez; el anterior queda revocado."""
    c = await _cubicador(db, cid)
    jti = secrets.token_urlsafe(24)
    token = jwt.encode({"sub": f"cub:{c.id}", "type": "cubicador", "esq": esquema_actual(), "jti": jti,
                        "iat": int(_ahora().timestamp())}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    c.token_huella, c.token_emitido_en = _huella(jti), _ahora()
    return {"token": token, "aviso": "Cópielo ahora en el archivo config.h del cubicador: no se vuelve a mostrar."}


@router.get("/cubicadores/{cid}/mediciones")
async def mediciones(cid: int, estado: Optional[str] = "PENDIENTE", despues_de: int = 0, limite: int = Query(50, le=500),
                     db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSMedicion).where(WMSMedicion.cubicador_id == cid, WMSMedicion.id > despues_de)
    if estado:
        q = q.where(WMSMedicion.estado.in_(estado.split(",")))
    filas = (await db.execute(q.order_by(WMSMedicion.id.desc()).limit(limite))).scalars().all()
    prods = dict((await db.execute(select(WMSProducto.id, WMSProducto.sku).where(
        WMSProducto.id.in_({m.producto_id for m in filas if m.producto_id} or {0})))).all())
    return [{"id": m.id, "fecha": m.created_at.isoformat() if m.created_at else None, "largo_cm": m.largo_cm,
             "ancho_cm": m.ancho_cm, "alto_cm": m.alto_cm, "peso_kg": m.peso_kg, "estable": m.estable,
             "dispersion_mm": m.dispersion_mm, "estado": m.estado, "producto": prods.get(m.producto_id),
             "nivel": m.nivel, "volumen_m3": cub.volumen_m3(m.largo_cm, m.ancho_cm, m.alto_cm)} for m in filas]


async def _medicion(db, mid) -> WMSMedicion:
    m = (await db.execute(select(WMSMedicion).where(WMSMedicion.id == mid).with_for_update())).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Medición no encontrada.")
    if m.estado != "PENDIENTE":
        raise HTTPException(409, f"La medición ya está {m.estado.lower()}.")
    return m


class AsignarIn(BaseModel):
    producto_id: int
    nivel: Literal["UNIDAD", "CAJA", "MASTER", "ESTIBA"]
    unidades: Optional[float] = Field(default=None, gt=0)
    codigo_barras: Optional[str] = Field(default=None, max_length=60)
    aceptar_inestable: bool = False


@router.post("/mediciones/{mid}/asignar")
async def asignar_medicion(mid: int, data: AsignarIn, db: AsyncSession = Depends(get_db),
                           yo: Usuario = Depends(get_current_user)):
    m = await _medicion(db, mid)
    if not m.estable and not data.aceptar_inestable:
        raise HTTPException(422, f"La medición fue inestable (±{m.dispersion_mm} mm): repítala o confírmela expresamente.")
    if not (m.largo_cm and m.ancho_cm and m.alto_cm):
        raise HTTPException(422, "La medición no tiene las tres medidas (¿cubicador sin calibrar?).")
    prod = await db.get(WMSProducto, data.producto_id)
    if prod is None:
        raise HTTPException(404, "Producto no encontrado.")
    unidades = 1 if data.nivel == "UNIDAD" else data.unidades
    if not unidades:
        raise HTTPException(422, f"Diga cuántas unidades lleva el nivel {data.nivel.lower()}.")
    emp = (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id == prod.id,
                                                            WMSProductoEmpaque.nivel == data.nivel))).scalar_one_or_none()
    if emp is None:
        emp = WMSProductoEmpaque(producto_id=prod.id, nivel=data.nivel)
        db.add(emp)
    emp.unidades, emp.largo_cm, emp.ancho_cm, emp.alto_cm = unidades, m.largo_cm, m.ancho_cm, m.alto_cm
    if m.peso_kg is not None:
        emp.peso_kg = m.peso_kg
    if data.codigo_barras:
        emp.codigo_barras = data.codigo_barras
    emp.fuente, emp.medicion_id, emp.medido_en, emp.medido_por_id = "CUBICADOR", m.id, _ahora(), yo.id
    _sincronizar_producto(prod, emp)
    m.estado, m.producto_id, m.nivel, m.asignada_por_id, m.asignada_en = "ASIGNADA", prod.id, data.nivel, yo.id, _ahora()
    await db.flush()
    return _emp_dict(emp)


@router.post("/mediciones/{mid}/descartar")
async def descartar_medicion(mid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    m = await _medicion(db, mid)
    m.estado, m.asignada_por_id, m.asignada_en = "DESCARTADA", yo.id, _ahora()
    return {"id": m.id, "estado": m.estado}


class CalibrarIn(BaseModel):
    largo_mm: Optional[float] = Field(default=None, gt=0)
    ancho_mm: Optional[float] = Field(default=None, gt=0)
    alto_mm: Optional[float] = Field(default=None, gt=0)
    # 0 = la báscula vacía (tara); > 0 = peso conocido del bloque.
    peso_g: Optional[float] = Field(default=None, ge=0)


@router.post("/mediciones/{mid}/calibrar")
async def calibrar_con_medicion(mid: int, data: CalibrarIn, db: AsyncSession = Depends(get_db),
                                _: Usuario = Depends(require_supervisor)):
    """Usa una medición de un bloque de medidas conocidas como muestra de
    calibración y recalcula la calibración de cada eje con todas sus muestras."""
    m = await _medicion(db, mid)
    c = await _cubicador(db, m.cubicador_id)
    cal = dict(c.calibracion or {})
    reales = {"x": data.largo_mm, "y": data.ancho_mm, "z": data.alto_mm}
    usados = []
    for eje, real in reales.items():
        vals = [v for v in (m.lecturas.get(eje) or []) if v]
        if real is not None and vals:
            cal.setdefault(eje, []).append([median(vals), real])
            usados.append(eje)
    crudos = [v for v in (m.lecturas.get("peso") or []) if v is not None]
    if data.peso_g is not None and crudos:
        cal.setdefault("peso", []).append([median(crudos), data.peso_g])
        usados.append("peso")
    if not usados:
        raise HTTPException(422, "Indique al menos una medida real que corresponda a las lecturas de la medición.")
    try:
        for eje in ("x", "y", "z"):
            if cal.get(eje):
                base, escala = cub.ajustar_eje([tuple(x) for x in cal[eje]])
                setattr(c, f"base_{eje}_mm", round(base, 3)); setattr(c, f"escala_{eje}", round(escala, 6))
        if cal.get("peso") and any(g == 0 for _, g in cal["peso"]) and any(g > 0 for _, g in cal["peso"]):
            c.tara_crudo, c.escala_peso = cub.ajustar_peso([tuple(x) for x in cal["peso"]])
    except ValueError as e:
        raise HTTPException(422, str(e))
    c.calibracion = cal
    m.estado = "CALIBRACION"
    return _cub_dict(c)


@router.post("/cubicadores/{cid}/calibracion/reiniciar")
async def reiniciar_calibracion(cid: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_supervisor)):
    c = await _cubicador(db, cid)
    c.calibracion = {}
    for eje in ("x", "y", "z"):
        setattr(c, f"base_{eje}_mm", None); setattr(c, f"escala_{eje}", 1.0)
    c.tara_crudo = c.escala_peso = None
    return _cub_dict(c)


# ── Empaques ─────────────────────────────────────────────────────────────────

def _emp_dict(e: WMSProductoEmpaque) -> dict:
    return {"id": e.id, "producto_id": e.producto_id, "nivel": e.nivel, "unidades": e.unidades,
            "largo_cm": e.largo_cm, "ancho_cm": e.ancho_cm, "alto_cm": e.alto_cm, "peso_kg": e.peso_kg,
            "volumen_m3": cub.volumen_m3(e.largo_cm, e.ancho_cm, e.alto_cm), "codigo_barras": e.codigo_barras,
            "cajas_por_cama": e.cajas_por_cama, "camas": e.camas, "apilable": e.apilable, "max_apilado": e.max_apilado,
            "fuente": e.fuente, "medido_en": e.medido_en.isoformat() if e.medido_en else None}


def _sincronizar_producto(prod: WMSProducto, emp: WMSProductoEmpaque) -> None:
    """La unidad medida es la verdad del producto: peso y volumen salen de ella."""
    if emp.nivel == "UNIDAD":
        v = cub.volumen_m3(emp.largo_cm, emp.ancho_cm, emp.alto_cm)
        if v:
            prod.volumen_m3 = v
        if emp.peso_kg:
            prod.peso_kg = emp.peso_kg


class EmpaqueIn(BaseModel):
    nivel: Literal["UNIDAD", "CAJA", "MASTER", "ESTIBA"]
    unidades: float = Field(gt=0)
    largo_cm: Optional[float] = Field(default=None, gt=0)
    ancho_cm: Optional[float] = Field(default=None, gt=0)
    alto_cm: Optional[float] = Field(default=None, gt=0)
    peso_kg: Optional[float] = Field(default=None, ge=0)
    codigo_barras: Optional[str] = Field(default=None, max_length=60)
    cajas_por_cama: Optional[int] = Field(default=None, gt=0)
    camas: Optional[int] = Field(default=None, gt=0)
    apilable: bool = True
    max_apilado: Optional[int] = Field(default=None, gt=0)


@router.get("/productos/{pid}/empaques")
async def ver_empaques(pid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    filas = (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id == pid))).scalars().all()
    return sorted([_emp_dict(e) for e in filas], key=lambda e: NIVELES.index(e["nivel"]))


@router.put("/productos/{pid}/empaques")
async def guardar_empaques(pid: int, data: List[EmpaqueIn], db: AsyncSession = Depends(get_db),
                           yo: Usuario = Depends(get_current_user)):
    """Reemplaza los niveles de empaque del producto (los que no vienen se borran).
    Las unidades tienen que crecer con el nivel: la caja lleva más que la unidad."""
    prod = await db.get(WMSProducto, pid)
    if prod is None:
        raise HTTPException(404, "Producto no encontrado.")
    niveles = [e.nivel for e in data]
    if len(set(niveles)) != len(niveles):
        raise HTTPException(422, "Cada nivel de empaque va una sola vez.")
    orden = sorted(data, key=lambda e: NIVELES.index(e.nivel))
    if orden and orden[0].nivel == "UNIDAD" and orden[0].unidades != 1:
        raise HTTPException(422, "La unidad lleva 1 unidad.")
    for a, b in zip(orden, orden[1:]):
        if b.unidades <= a.unidades:
            raise HTTPException(422, f"El nivel {b.nivel.lower()} debe llevar más unidades que {a.nivel.lower()}.")
    actuales = {e.nivel: e for e in (await db.execute(select(WMSProductoEmpaque).where(
        WMSProductoEmpaque.producto_id == pid))).scalars()}
    for nivel, e in actuales.items():
        if nivel not in niveles:
            await db.delete(e)
    for d in orden:
        e = actuales.get(d.nivel)
        if e is None:
            e = WMSProductoEmpaque(producto_id=pid, nivel=d.nivel)
            db.add(e)
        cambiaron_medidas = (e.largo_cm, e.ancho_cm, e.alto_cm, e.peso_kg) != (d.largo_cm, d.ancho_cm, d.alto_cm, d.peso_kg)
        for k, v in d.model_dump().items():
            setattr(e, k, v)
        if cambiaron_medidas:
            # Si alguien las corrige a mano, ya no son del cubicador.
            e.fuente, e.medicion_id, e.medido_en, e.medido_por_id = "MANUAL", None, _ahora(), yo.id
        _sincronizar_producto(prod, e)
    await db.flush()
    return await ver_empaques(pid, db)


# ── Armado de estiba ─────────────────────────────────────────────────────────

class EstibaIn(BaseModel):
    producto_id: Optional[int] = None
    nivel: Literal["UNIDAD", "CAJA", "MASTER"] = "CAJA"
    largo_cm: Optional[float] = Field(default=None, gt=0)
    ancho_cm: Optional[float] = Field(default=None, gt=0)
    alto_cm: Optional[float] = Field(default=None, gt=0)
    peso_kg: Optional[float] = Field(default=None, ge=0)
    base_largo_cm: float = Field(default=120, gt=0)
    base_ancho_cm: float = Field(default=100, gt=0)
    alto_max_cm: float = Field(default=150, gt=20)
    peso_max_kg: float = Field(default=1000, gt=0)
    guardar: bool = False


@router.post("/cubicaje/estiba")
async def calcular_estiba(data: EstibaIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Cuántas cajas por cama y cuántas camas. Con `guardar`, deja el nivel
    ESTIBA del producto con ese Ti×Hi."""
    l, a, h, p, max_ap, unidades = data.largo_cm, data.ancho_cm, data.alto_cm, data.peso_kg, None, None
    if data.producto_id:
        e = (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id == data.producto_id,
                                                              WMSProductoEmpaque.nivel == data.nivel))).scalar_one_or_none()
        if e is None or not (e.largo_cm and e.ancho_cm and e.alto_cm):
            raise HTTPException(422, f"El producto no tiene medido el nivel {data.nivel.lower()}.")
        l, a, h, p, max_ap, unidades = e.largo_cm, e.ancho_cm, e.alto_cm, e.peso_kg, e.max_apilado, e.unidades
    if not (l and a and h):
        raise HTTPException(422, "Indique el producto o las medidas de la caja.")
    try:
        r = cub.armar_estiba((l, a, h), p, (data.base_largo_cm, data.base_ancho_cm), data.alto_max_cm,
                             data.peso_max_kg, max_ap)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if data.guardar and data.producto_id and r["cajas"] > 0:
        est = (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id == data.producto_id,
                                                                WMSProductoEmpaque.nivel == "ESTIBA"))).scalar_one_or_none()
        if est is None:
            est = WMSProductoEmpaque(producto_id=data.producto_id, nivel="ESTIBA")
            db.add(est)
        est.unidades = r["cajas"] * (unidades or 1)
        est.cajas_por_cama, est.camas = r["ti"], r["hi"]
        est.largo_cm, est.ancho_cm, est.alto_cm = data.base_largo_cm, data.base_ancho_cm, r["alto_total_cm"]
        est.peso_kg = (r["peso_total_kg"] or 0) + 25 if r["peso_total_kg"] else None   # + la estiba de madera
        est.fuente = "MANUAL"
        r["guardado"] = True
    return r


# ── Ocupación cúbica ─────────────────────────────────────────────────────────

async def _vol_unitario(db: AsyncSession, producto_ids) -> dict:
    """Volumen de una unidad: el nivel UNIDAD medido; si no, el del producto."""
    ids = set(producto_ids)
    if not ids:
        return {}
    vol = {pid: v for pid, v in (await db.execute(select(WMSProducto.id, WMSProducto.volumen_m3)
                                                  .where(WMSProducto.id.in_(ids)))).all() if v}
    for e in (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id.in_(ids),
                                                               WMSProductoEmpaque.nivel == "UNIDAD"))).scalars():
        v = cub.volumen_m3(e.largo_cm, e.ancho_cm, e.alto_cm)
        if v:
            vol[e.producto_id] = v
    return vol


async def ocupacion(db: AsyncSession, almacen_id: Optional[int] = None) -> list:
    q = select(WMSUbicacion, WMSZona).join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).where(WMSUbicacion.activo.isnot(False))
    if almacen_id:
        q = q.where(WMSZona.almacen_id == almacen_id)
    ubic = (await db.execute(q.order_by(WMSUbicacion.codigo))).all()
    ids = [u.id for u, _z in ubic]
    total = WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada \
        + WMSInventarioUbicacion.cantidad_bloqueada
    filas = (await db.execute(select(WMSInventarioUbicacion.ubicacion_id, WMSInventarioUbicacion.producto_id,
                                     func.sum(total)).where(WMSInventarioUbicacion.ubicacion_id.in_(ids or [0]), total > 0)
                              .group_by(WMSInventarioUbicacion.ubicacion_id, WMSInventarioUbicacion.producto_id))).all()
    vol = await _vol_unitario(db, [p for _u, p, _q in filas])
    por_ubic: dict = {}
    for uid, pid, qty in filas:
        d = por_ubic.setdefault(uid, {"m3": 0.0, "unidades": 0.0, "sin_volumen": 0.0, "skus": 0})
        d["unidades"] += float(qty); d["skus"] += 1
        if pid in vol:
            d["m3"] += float(qty) * vol[pid]
        else:
            d["sin_volumen"] += float(qty)
    out = []
    for u, z in ubic:
        cap = cub.volumen_m3(u.largo_cm, u.ancho_cm, u.alto_cm) or u.capacidad_m3
        d = por_ubic.get(u.id, {"m3": 0.0, "unidades": 0.0, "sin_volumen": 0.0, "skus": 0})
        out.append({"id": u.id, "codigo": u.codigo, "zona": z.nombre, "zona_tipo": z.tipo, "almacen_id": z.almacen_id,
                    "pasillo": u.pasillo, "estanteria": u.estanteria, "nivel": u.nivel, "posicion": u.posicion,
                    "largo_cm": u.largo_cm, "ancho_cm": u.ancho_cm, "alto_cm": u.alto_cm, "capacidad_m3": cap,
                    "zona_id": z.id,
                    "area_m2": round(u.largo_cm * u.ancho_cm / 10_000, 3) if u.largo_cm and u.ancho_cm else None,
                    "capacidad_kg": u.capacidad_kg, "ocupado_m3": round(d["m3"], 4), "unidades": d["unidades"],
                    "skus": d["skus"], "unidades_sin_volumen": d["sin_volumen"],
                    "ocupacion_pct": round(d["m3"] / cap * 100, 1) if cap else None})
    return out


@router.get("/cubicaje/ubicaciones")
async def ocupacion_ubicaciones(almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
                                _=Depends(get_current_user)):
    return await ocupacion(db, almacen_id)


@router.get("/cubicaje/resumen")
async def resumen(almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    ubic = await ocupacion(db, almacen_id)
    almac = [u for u in ubic if u["zona_tipo"] not in ("RECEPCION", "DESPACHO", "TRANSITO")]
    cap = sum(u["capacidad_m3"] or 0 for u in almac)
    ocu = sum(u["ocupado_m3"] for u in almac)
    prods = (await db.execute(select(WMSProducto.id).where(WMSProducto.activo.isnot(False)))).scalars().all()
    medidos = set((await db.execute(select(WMSProductoEmpaque.producto_id).where(
        WMSProductoEmpaque.nivel == "UNIDAD", WMSProductoEmpaque.largo_cm.isnot(None)))).scalars())
    por_cubicador = set((await db.execute(select(WMSProductoEmpaque.producto_id).where(
        WMSProductoEmpaque.fuente == "CUBICADOR"))).scalars())
    con_stock = {u["id"] for u in almac if u["unidades"] > 0}
    return {"capacidad_m3": round(cap, 3), "ocupado_m3": round(ocu, 3),
            "utilizacion_cubica_pct": round(ocu / cap * 100, 1) if cap else None,
            "ubicaciones": len(almac), "ubicaciones_ocupadas": len(con_stock),
            "ocupacion_posiciones_pct": round(len(con_stock) / len(almac) * 100, 1) if almac else None,
            "ubicaciones_sin_medidas": sum(1 for u in almac if not u["capacidad_m3"]),
            "skus": len(prods), "skus_medidos": len(medidos & set(prods)),
            "cobertura_cubicaje_pct": round(len(medidos & set(prods)) / len(prods) * 100, 1) if prods else None,
            "skus_por_cubicador": len(por_cubicador & set(prods)),
            "unidades_sin_volumen": sum(u["unidades_sin_volumen"] for u in almac),
            **_area_de_piso(ubic)}


def _area_de_piso(ubic: list) -> dict:
    """Metros cuadrados de piso: los niveles de una misma estantería comparten
    la huella (pasillo + estantería + posición), así que se cuentan una vez;
    la huella está ocupada si cualquiera de sus niveles tiene mercancía."""
    huellas: dict = {}
    for u in ubic:
        if u["pasillo"] or u["estanteria"]:
            clave = (u["zona_id"], u["pasillo"], u["estanteria"], u["posicion"])
        else:
            clave = ("u", u["id"])
        h = huellas.setdefault(clave, {"zona": u["zona"], "zona_tipo": u["zona_tipo"], "area": None, "ocupada": False})
        if u["area_m2"]:
            h["area"] = max(h["area"] or 0, u["area_m2"])
        h["ocupada"] |= u["unidades"] > 0
    zonas: dict = {}
    for h in huellas.values():
        z = zonas.setdefault(h["zona"], {"zona": h["zona"], "tipo": h["zona_tipo"], "area_m2": 0.0, "ocupada_m2": 0.0,
                                         "huellas": 0, "huellas_sin_medidas": 0})
        z["huellas"] += 1
        if h["area"] is None:
            z["huellas_sin_medidas"] += 1
            continue
        z["area_m2"] += h["area"]
        if h["ocupada"]:
            z["ocupada_m2"] += h["area"]
    lista = []
    for z in zonas.values():
        z["area_m2"], z["ocupada_m2"] = round(z["area_m2"], 2), round(z["ocupada_m2"], 2)
        z["libre_m2"] = round(z["area_m2"] - z["ocupada_m2"], 2)
        z["ocupacion_pct"] = round(z["ocupada_m2"] / z["area_m2"] * 100, 1) if z["area_m2"] else None
        lista.append(z)
    total = sum(z["area_m2"] for z in lista)
    ocupada = sum(z["ocupada_m2"] for z in lista)
    return {"area_m2": round(total, 2), "area_ocupada_m2": round(ocupada, 2), "area_libre_m2": round(total - ocupada, 2),
            "ocupacion_area_pct": round(ocupada / total * 100, 1) if total else None,
            "huellas_sin_medidas": sum(z["huellas_sin_medidas"] for z in lista),
            "area_por_zona": sorted(lista, key=lambda z: -z["area_m2"])}


@router.get("/cubicaje/productos")
async def productos_cubicaje(q: Optional[str] = None, depositante_id: Optional[int] = None, solo_sin_medir: bool = False,
                             db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    consulta = select(WMSProducto).where(WMSProducto.activo.isnot(False))
    if q:
        consulta = consulta.where(WMSProducto.sku.ilike(f"%{q}%") | WMSProducto.nombre.ilike(f"%{q}%")
                                  | WMSProducto.codigo_barras.ilike(f"%{q}%"))
    if depositante_id:
        consulta = consulta.where(WMSProducto.depositante_id == depositante_id)
    prods = (await db.execute(consulta.order_by(WMSProducto.sku).limit(1000))).scalars().all()
    emps: dict = {}
    for e in (await db.execute(select(WMSProductoEmpaque).where(
            WMSProductoEmpaque.producto_id.in_([p.id for p in prods] or [0])))).scalars():
        emps.setdefault(e.producto_id, {})[e.nivel] = e
    out = []
    for p in prods:
        niv = emps.get(p.id, {})
        u = niv.get("UNIDAD")
        medido = bool(u and u.largo_cm and u.ancho_cm and u.alto_cm)
        if solo_sin_medir and medido:
            continue
        out.append({"id": p.id, "sku": p.sku, "nombre": p.nombre, "codigo_barras": p.codigo_barras,
                    "depositante_id": p.depositante_id, "niveles": sorted(niv, key=NIVELES.index),
                    "medido": medido, "fuente": u.fuente if u else None,
                    "unidad": _emp_dict(u) if u else None, "peso_kg": p.peso_kg, "volumen_m3": p.volumen_m3,
                    "estiba": {"ti": niv["ESTIBA"].cajas_por_cama, "hi": niv["ESTIBA"].camas,
                               "unidades": niv["ESTIBA"].unidades} if "ESTIBA" in niv else None})
    return out
