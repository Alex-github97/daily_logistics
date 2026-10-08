"""
Canales de venta en línea (marketplaces y tiendas) — API de Daily Logistics.

Rutas con sesión (módulo WMS):     /wms/canales/...
Rutas públicas (sin sesión):       /integraciones/{token}            avisos de las plataformas
                                   /integraciones/mercadolibre/callback   autorización OAuth
"""
import io
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.core.marketplace import servicio
from app.core.marketplace.adaptadores import ADAPTADORES, CAMPOS, MercadoLibre, adaptador, normalizar_estandar
from app.core.marketplace.base import ErrorConector
from app.core.tenant import esquema_actual, ESQUEMA_PLATAFORMA
from app.infrastructure.models.marketplace import (
    MKPBitacora, MKPConector, MKPPedido, MKPPedidoLinea, MKPPublicacion, MKPRegistroPublico, TIPOS_CONECTOR,
)
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSInventarioUbicacion, WMSOrdenSalida, WMSProducto, WMSUbicacion, WMSZona,
)

router = APIRouter(tags=["Canales de venta"])

NOMBRES = {"MERCADOLIBRE": "MercadoLibre", "SHOPIFY": "Shopify", "WOOCOMMERCE": "WooCommerce", "VTEX": "VTEX",
           "RAPPI": "Rappi", "WEBHOOK": "Webhook genérico", "ARCHIVO": "Importación de archivos"}
OCULTO = "••••••"


def _url_publica(request: Request) -> str:
    """Dirección pública de la herramienta (la que ven las plataformas).

    En producción la fija DL_URL_PUBLICA. Si no, la del navegador que hizo la
    petición: detrás del proxy de desarrollo, `base_url` es el nombre interno
    del contenedor y no le sirve a nadie de afuera."""
    if os.getenv("DL_URL_PUBLICA"):
        return os.getenv("DL_URL_PUBLICA").rstrip("/")
    from urllib.parse import urlsplit
    ref = urlsplit(request.headers.get("referer") or "")
    if ref.scheme and ref.netloc:
        return f"{ref.scheme}://{ref.netloc}"
    return str(request.base_url).rstrip("/")


def _secretos(tipo: str) -> set:
    return {c for c, _, secreto in CAMPOS.get(tipo, []) if secreto}


def _conector_dict(c: MKPConector, request: Request, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ocultos = _secretos(c.tipo) | {"access_token", "refresh_token"}
    cred = {k: (OCULTO if (k in ocultos and v) else v) for k, v in (c.credenciales or {}).items()
            if k not in ("expira",)}
    ad = ADAPTADORES[c.tipo]
    return {
        "id": c.id, "tipo": c.tipo, "tipo_nombre": NOMBRES.get(c.tipo, c.tipo), "nombre": c.nombre, "activo": c.activo,
        "almacen_id": c.almacen_id, "cliente_id": c.cliente_id, "credenciales": cred, "config": c.config or {},
        "colchon_stock": c.colchon_stock, "sincronizar_stock": c.sincronizar_stock, "importar_pedidos": c.importar_pedidos,
        "estado_conexion": c.estado_conexion, "ultimo_error": c.ultimo_error,
        "ultima_sync_pedidos": c.ultima_sync_pedidos, "ultima_sync_stock": c.ultima_sync_stock,
        "url_webhook": f"{_url_publica(request)}/api/v1/integraciones/{c.token_webhook}",
        "autorizado": bool((c.credenciales or {}).get("refresh_token")) if c.tipo == "MERCADOLIBRE" else None,
        "capacidades": ad.capacidades.__dict__, **(extra or {}),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Conectores
# ═════════════════════════════════════════════════════════════════════════════

class ConectorIn(BaseModel):
    tipo: str
    nombre: str = Field(min_length=2, max_length=120)
    almacen_id: int
    credenciales: Dict[str, Any] = {}
    config: Dict[str, Any] = {}
    colchon_stock: int = Field(default=0, ge=0)
    sincronizar_stock: bool = True
    importar_pedidos: bool = True
    activo: bool = True


@router.get("/wms/canales/tipos")
async def tipos(_=Depends(get_current_user)):
    return [{"tipo": t, "nombre": NOMBRES[t],
             "campos": [{"clave": c, "etiqueta": e, "secreto": s} for c, e, s in CAMPOS.get(t, [])],
             "capacidades": ADAPTADORES[t].capacidades.__dict__} for t in TIPOS_CONECTOR]


@router.get("/wms/canales/conectores")
async def listar_conectores(request: Request, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    conectores = (await db.execute(select(MKPConector).order_by(MKPConector.nombre))).scalars().all()
    pubs = dict((await db.execute(select(MKPPublicacion.conector_id, func.count()).where(
        MKPPublicacion.producto_id.isnot(None)).group_by(MKPPublicacion.conector_id))).all())
    abiertos = dict((await db.execute(select(MKPPedido.conector_id, func.count()).where(
        MKPPedido.estado.in_(servicio.ESTADOS_ABIERTOS)).group_by(MKPPedido.conector_id))).all())
    return [_conector_dict(c, request, {"publicaciones_mapeadas": pubs.get(c.id, 0),
                                        "pedidos_abiertos": abiertos.get(c.id, 0)}) for c in conectores]


@router.post("/wms/canales/conectores", status_code=201)
async def crear_conector(data: ConectorIn, request: Request, db: AsyncSession = Depends(get_db),
                         _: Usuario = Depends(require_supervisor)):
    if data.tipo not in TIPOS_CONECTOR:
        raise HTTPException(422, "Tipo de canal desconocido")
    if not await db.get(WMSAlmacen, data.almacen_id):
        raise HTTPException(422, "Almacén no encontrado")
    c = MKPConector(tipo=data.tipo, nombre=data.nombre.strip(), almacen_id=data.almacen_id,
                    credenciales={k: v for k, v in data.credenciales.items() if v not in (None, "", OCULTO)},
                    config=data.config, colchon_stock=data.colchon_stock, sincronizar_stock=data.sincronizar_stock,
                    importar_pedidos=data.importar_pedidos, activo=data.activo, token_webhook=secrets.token_urlsafe(24))
    db.add(c)
    await db.flush()
    db.add(MKPRegistroPublico(token=c.token_webhook, esquema=esquema_actual() or ESQUEMA_PLATAFORMA,
                              conector_id=c.id, tipo=c.tipo))
    await servicio.cliente_del_conector(db, c)
    await servicio.registrar(db, c.id, "CONEXION", True, f"Canal «{c.nombre}» creado")
    await db.commit()
    return _conector_dict(c, request)


@router.put("/wms/canales/conectores/{cid}")
async def actualizar_conector(cid: int, data: ConectorIn, request: Request, db: AsyncSession = Depends(get_db),
                              _: Usuario = Depends(require_supervisor)):
    c = await db.get(MKPConector, cid)
    if not c:
        raise HTTPException(404, "Canal no encontrado")
    cred = dict(c.credenciales or {})
    for k, v in data.credenciales.items():
        if v == OCULTO:
            continue                       # no se cambió: se conserva el secreto guardado
        if v in (None, ""):
            cred.pop(k, None)
        else:
            cred[k] = v
    c.nombre, c.almacen_id, c.credenciales, c.config = data.nombre.strip(), data.almacen_id, cred, data.config
    c.colchon_stock, c.sincronizar_stock, c.importar_pedidos, c.activo = (
        data.colchon_stock, data.sincronizar_stock, data.importar_pedidos, data.activo)
    await db.commit()
    return _conector_dict(c, request)


@router.post("/wms/canales/conectores/{cid}/probar")
async def probar_conector(cid: int, request: Request, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await db.get(MKPConector, cid)
    if not c:
        raise HTTPException(404, "Canal no encontrado")
    ad = adaptador(c)
    try:
        detalle = await ad.probar()
        c.estado_conexion, c.ultimo_error = "OK", None
        servicio.guardar_credenciales(c, ad)
        await servicio.registrar(db, c.id, "CONEXION", True, f"Conexión verificada: {detalle}")
        await db.commit()
        return {"ok": True, "detalle": detalle}
    except ErrorConector as e:
        c.estado_conexion, c.ultimo_error = "ERROR", str(e)[:1000]
        await servicio.registrar(db, c.id, "CONEXION", False, str(e))
        await db.commit()
        return {"ok": False, "detalle": str(e)}


@router.post("/wms/canales/conectores/{cid}/sincronizar")
async def sincronizar(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Ahora mismo: trae pedidos nuevos y publica el stock de todo lo mapeado."""
    c = await db.get(MKPConector, cid)
    if not c:
        raise HTTPException(404, "Canal no encontrado")
    resultado: Dict[str, Any] = {}
    try:
        resultado["pedidos"] = await servicio.traer_pedidos(db, c) if c.importar_pedidos else 0
        enviadas, errores = await servicio.sincronizar_stock(db, c, forzar=True) if c.sincronizar_stock else (0, 0)
        resultado.update(stock_enviado=enviadas, stock_errores=errores)
        c.estado_conexion, c.ultimo_error = "OK", None
    except ErrorConector as e:
        c.estado_conexion, c.ultimo_error = "ERROR", str(e)[:1000]
        await servicio.registrar(db, c.id, "CONEXION", False, str(e))
        resultado["error"] = str(e)
    await db.commit()
    return resultado


@router.get("/wms/canales/conectores/{cid}/mercadolibre/autorizar")
async def autorizar_mercadolibre(cid: int, request: Request, db: AsyncSession = Depends(get_db),
                                 _: Usuario = Depends(require_supervisor)):
    c = await db.get(MKPConector, cid)
    if not c or c.tipo != "MERCADOLIBRE":
        raise HTTPException(404, "Canal de MercadoLibre no encontrado")
    try:
        url = MercadoLibre(c.credenciales, c.config).url_autorizacion(
            f"{_url_publica(request)}/api/v1/integraciones/mercadolibre/callback", c.token_webhook)
    except ErrorConector as e:
        raise HTTPException(422, str(e))
    return {"url": url}


@router.get("/wms/canales/bitacora")
async def bitacora(conector_id: Optional[int] = None, limite: int = Query(100, le=500),
                   db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(MKPBitacora).order_by(MKPBitacora.id.desc()).limit(limite)
    if conector_id:
        q = q.where(MKPBitacora.conector_id == conector_id)
    return [{"id": b.id, "conector_id": b.conector_id, "fecha": b.fecha, "tipo": b.tipo, "ok": b.ok, "mensaje": b.mensaje}
            for b in (await db.execute(q)).scalars().all()]


# ═════════════════════════════════════════════════════════════════════════════
# Publicaciones (mapeo de SKU)
# ═════════════════════════════════════════════════════════════════════════════

class PublicacionIn(BaseModel):
    producto_id: Optional[int] = None
    unidades: float = Field(default=1, gt=0)
    activo: bool = True


class PublicacionNueva(PublicacionIn):
    ref_externa: str = Field(min_length=1)
    ref_variante: str = ""
    sku_externo: Optional[str] = None
    titulo: Optional[str] = None


def _pub_dict(p: MKPPublicacion, prod: Optional[WMSProducto]) -> Dict[str, Any]:
    return {"id": p.id, "conector_id": p.conector_id, "ref_externa": p.ref_externa, "ref_variante": p.ref_variante,
            "sku_externo": p.sku_externo, "titulo": p.titulo, "producto_id": p.producto_id,
            "producto": {"sku": prod.sku, "nombre": prod.nombre} if prod else None, "unidades": p.unidades,
            "activo": p.activo, "ultimo_stock_enviado": p.ultimo_stock_enviado, "ultimo_envio": p.ultimo_envio,
            "ultimo_error": p.ultimo_error}


@router.get("/wms/canales/conectores/{cid}/publicaciones")
async def listar_publicaciones(cid: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    filas = (await db.execute(select(MKPPublicacion, WMSProducto).outerjoin(
        WMSProducto, WMSProducto.id == MKPPublicacion.producto_id).where(MKPPublicacion.conector_id == cid)
        .order_by(MKPPublicacion.producto_id.is_(None).desc(), MKPPublicacion.titulo))).all()
    return [_pub_dict(p, prod) for p, prod in filas]


@router.post("/wms/canales/conectores/{cid}/publicaciones/traer")
async def traer_publicaciones(cid: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_supervisor)):
    """Trae las publicaciones de la plataforma y mapea solas las que tengan un SKU
    que exista en el maestro (SKU, código de barras o código de empaque)."""
    c = await db.get(MKPConector, cid)
    if not c:
        raise HTTPException(404, "Canal no encontrado")
    ad = adaptador(c)
    try:
        externas = await ad.publicaciones()
    except ErrorConector as e:
        raise HTTPException(502, str(e))
    servicio.guardar_credenciales(c, ad)
    from app.api.v1.endpoints.wms_codigos import _resolver
    nuevas = mapeadas = 0
    # Una plataforma puede repetir la misma publicación entre páginas.
    externas = list({(e.ref_externa, e.ref_variante or ""): e for e in externas}.values())
    for e in externas:
        p = (await db.execute(select(MKPPublicacion).where(
            MKPPublicacion.conector_id == cid, MKPPublicacion.ref_externa == e.ref_externa,
            MKPPublicacion.ref_variante == (e.ref_variante or "")))).scalar()
        if p is None:
            p = MKPPublicacion(conector_id=cid, ref_externa=e.ref_externa, ref_variante=e.ref_variante or "")
            db.add(p)
            nuevas += 1
        p.ref_inventario, p.sku_externo, p.titulo = e.ref_inventario, e.sku, e.titulo
        if p.producto_id is None and e.sku:
            r = await _resolver(db, e.sku)
            if r:
                p.producto_id, p.unidades = r[0].id, r[2]
                mapeadas += 1
    await servicio.registrar(db, cid, "CONEXION", True,
                             f"{len(externas)} publicaciones leídas ({nuevas} nuevas, {mapeadas} mapeadas por SKU)")
    await db.commit()
    return {"leidas": len(externas), "nuevas": nuevas, "mapeadas": mapeadas}


@router.post("/wms/canales/conectores/{cid}/publicaciones", status_code=201)
async def crear_publicacion(cid: int, data: PublicacionNueva, db: AsyncSession = Depends(get_db),
                            _: Usuario = Depends(require_supervisor)):
    p = MKPPublicacion(conector_id=cid, ref_externa=data.ref_externa.strip(), ref_variante=data.ref_variante.strip(),
                       sku_externo=data.sku_externo, titulo=data.titulo, producto_id=data.producto_id,
                       unidades=data.unidades, activo=data.activo)
    db.add(p)
    await db.commit()
    return _pub_dict(p, await db.get(WMSProducto, p.producto_id) if p.producto_id else None)


@router.put("/wms/canales/publicaciones/{pid}")
async def actualizar_publicacion(pid: int, data: PublicacionIn, db: AsyncSession = Depends(get_db),
                                 _: Usuario = Depends(require_supervisor)):
    p = await db.get(MKPPublicacion, pid)
    if not p:
        raise HTTPException(404, "Publicación no encontrada")
    p.producto_id, p.unidades, p.activo = data.producto_id, data.unidades, data.activo
    p.ultimo_stock_enviado = None            # que se vuelva a publicar con el mapeo nuevo
    await db.commit()
    return _pub_dict(p, await db.get(WMSProducto, p.producto_id) if p.producto_id else None)


# ═════════════════════════════════════════════════════════════════════════════
# Pedidos
# ═════════════════════════════════════════════════════════════════════════════

async def _pedido_dict(db: AsyncSession, p: MKPPedido, conectores: Dict[int, MKPConector],
                       con_lineas: bool = True) -> Dict[str, Any]:
    c = conectores.get(p.conector_id)
    orden = await db.get(WMSOrdenSalida, p.orden_salida_id) if p.orden_salida_id else None
    d = {"id": p.id, "conector_id": p.conector_id, "canal": c.nombre if c else None, "tipo": c.tipo if c else None,
         "pedido_externo": p.pedido_externo, "estado": p.estado, "etapa": await servicio.etapa(db, p),
         "estado_externo": p.estado_externo, "novedad": p.novedad, "fecha_pedido": p.fecha_pedido,
         "comprador": p.comprador, "telefono": p.telefono, "direccion": p.direccion, "ciudad": p.ciudad,
         "total": float(p.total) if p.total is not None else None, "orden_salida_id": p.orden_salida_id,
         "numero_orden": orden.numero_orden if orden else None, "despacho_id": p.despacho_id, "tracking": p.tracking,
         "almacen_id": c.almacen_id if c else None}
    if con_lineas:
        filas = (await db.execute(select(MKPPedidoLinea, WMSProducto).outerjoin(
            WMSProducto, WMSProducto.id == MKPPedidoLinea.producto_id).where(MKPPedidoLinea.pedido_id == p.id))).all()
        d["lineas"] = [{"id": l.id, "sku_externo": l.sku_externo, "titulo": l.titulo, "cantidad": l.cantidad,
                        "precio": float(l.precio) if l.precio is not None else None, "producto_id": l.producto_id,
                        "producto": {"sku": prod.sku, "nombre": prod.nombre} if prod else None, "unidades": l.unidades}
                       for l, prod in filas]
    return d


@router.get("/wms/canales/pedidos")
async def listar_pedidos(estado: Optional[str] = None, conector_id: Optional[int] = None, q: Optional[str] = None,
                         limite: int = Query(200, le=1000), db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    stmt = select(MKPPedido).order_by(MKPPedido.id.desc()).limit(limite)
    if estado:
        stmt = stmt.where(MKPPedido.estado.in_(estado.split(",")))
    if conector_id:
        stmt = stmt.where(MKPPedido.conector_id == conector_id)
    if q:
        t = f"%{q.strip()}%"
        stmt = stmt.where(or_(MKPPedido.pedido_externo.ilike(t), MKPPedido.comprador.ilike(t), MKPPedido.ciudad.ilike(t)))
    conectores = {c.id: c for c in (await db.execute(select(MKPConector))).scalars().all()}
    return [await _pedido_dict(db, p, conectores) for p in (await db.execute(stmt)).scalars().all()]


@router.post("/wms/canales/pedidos/{pid}/reprocesar")
async def reprocesar(pid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Después de mapear un SKU o recibir mercancía: vuelve a intentar comprometer."""
    p = await db.get(MKPPedido, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    c = await db.get(MKPConector, p.conector_id)
    if p.estado not in ("RECIBIDO", "CON_NOVEDAD"):
        raise HTTPException(409, "Solo se reprocesan pedidos recibidos o con novedad")
    for l in (await db.execute(select(MKPPedidoLinea).where(MKPPedidoLinea.pedido_id == p.id))).scalars().all():
        if not l.producto_id:
            from app.core.marketplace.base import LineaNorm
            pid_, u = await servicio.resolver_linea(db, c, LineaNorm(cantidad=l.cantidad, ref_externa=l.ref_externa,
                                                                    ref_variante=l.ref_variante, sku=l.sku_externo))
            l.producto_id, l.unidades = pid_, (l.cantidad * u if pid_ else None)
    if p.orden_salida_id:
        # Ya hay orden: se intenta reservar lo que faltó.
        from app.api.v1.endpoints.wms import crear_alistamiento
        await crear_alistamiento(db, p.orden_salida_id, "SINGLE", 0, 30, yo.id)
        from app.infrastructure.models.wms import WMSOrdenSalidaDetalle
        dets = (await db.execute(select(WMSOrdenSalidaDetalle).where(WMSOrdenSalidaDetalle.orden_id == p.orden_salida_id))).scalars().all()
        faltan = [d for d in dets if (d.cantidad_preparada or 0) < d.cantidad_solicitada]
        p.estado, p.novedad = ("CON_NOVEDAD", p.novedad) if faltan else ("COMPROMETIDO", None)
    else:
        await servicio.comprometer(db, c, p, yo.id)
    await db.commit()
    return await _pedido_dict(db, p, {c.id: c})


class Motivo(BaseModel):
    motivo: str = Field(default="Cancelado manualmente", max_length=300)


@router.post("/wms/canales/pedidos/{pid}/cancelar")
async def cancelar(pid: int, data: Motivo, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    p = await db.get(MKPPedido, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    if p.estado not in servicio.ESTADOS_ABIERTOS:
        raise HTTPException(409, "El pedido ya salió o ya estaba cancelado")
    await servicio.cancelar_pedido(db, p, data.motivo, yo.id)
    await db.commit()
    return {"ok": True}


# ── Pedidos por despachar (staging de salida) ─────────────────────────────────

@router.get("/wms/canales/por-despachar")
async def por_despachar(almacen_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    conectores = {c.id: c for c in (await db.execute(select(MKPConector))).scalars().all()}
    pedidos = (await db.execute(select(MKPPedido).where(
        MKPPedido.estado.in_(("COMPROMETIDO", "CON_NOVEDAD", "EN_STAGING")), MKPPedido.orden_salida_id.isnot(None))
        .order_by(MKPPedido.fecha_pedido))).scalars().all()
    lista = []
    for p in pedidos:
        d = await _pedido_dict(db, p, conectores)
        if almacen_id and d["almacen_id"] != almacen_id:
            continue
        lista.append(d)
    # Lo que físicamente está en el staging de salida, por producto.
    q = (select(WMSProducto.sku, WMSProducto.nombre, WMSAlmacen.nombre, func.sum(WMSInventarioUbicacion.cantidad_reservada))
         .join(WMSUbicacion, WMSUbicacion.id == WMSInventarioUbicacion.ubicacion_id)
         .join(WMSZona, WMSZona.id == WMSUbicacion.zona_id).join(WMSAlmacen, WMSAlmacen.id == WMSZona.almacen_id)
         .join(WMSProducto, WMSProducto.id == WMSInventarioUbicacion.producto_id)
         .where(WMSZona.tipo == "DESPACHO", WMSInventarioUbicacion.cantidad_reservada > 0)
         .group_by(WMSProducto.sku, WMSProducto.nombre, WMSAlmacen.nombre))
    if almacen_id:
        q = q.where(WMSZona.almacen_id == almacen_id)
    staging = [{"sku": s, "nombre": n, "almacen": a, "unidades": float(u or 0)} for s, n, a, u in (await db.execute(q)).all()]
    return {"pedidos": lista, "staging": staging}


class DespacharIn(BaseModel):
    pedido_ids: List[int] = Field(min_length=1)


@router.post("/wms/canales/despachar")
async def despachar(data: DespacharIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Despacha pedidos que están en staging: despacho WMS + viaje en el TMS con
    la dirección del comprador; la plataforma recibe «enviado» con la guía."""
    from app.api.v1.endpoints.wms import crear_despacho
    from app.application.schemas.wms import WMSDespachoCreate
    from app.infrastructure.models.tms import TMSViaje
    resultados = []
    for pid in data.pedido_ids:
        p = await db.get(MKPPedido, pid)
        if not p:
            resultados.append({"pedido_id": pid, "ok": False, "detalle": "No existe"})
            continue
        if await servicio.etapa(db, p) != "EN_STAGING":
            resultados.append({"pedido_id": pid, "pedido": p.pedido_externo, "ok": False,
                               "detalle": "Todavía no está alistado (falta terminar el picking)"})
            continue
        try:
            desp = await crear_despacho(WMSDespachoCreate(
                orden_id=p.orden_salida_id, gestion_transporte="TMS",
                notas=f"Pedido {p.pedido_externo} · {p.comprador or ''}"), db, yo)
            viaje = (await db.execute(select(TMSViaje).where(TMSViaje.wms_despacho_id == desp.id))).scalar()
            if viaje:
                viaje.destino_ciudad = p.ciudad or viaje.destino_ciudad
                viaje.destino_direccion = " · ".join(x for x in (p.direccion, p.comprador, p.telefono) if x)[:300] or viaje.destino_direccion
            p = await db.get(MKPPedido, pid)
            p.estado, p.despacho_id = "DESPACHADO", desp.id
            p.tracking = viaje.codigo if viaje else desp.numero_despacho
            await servicio.encolar_estado(db, p.id, "ENVIADO")
            await servicio.registrar(db, p.conector_id, "PEDIDO", True,
                                     f"Pedido {p.pedido_externo} despachado ({desp.numero_despacho}, viaje {p.tracking})")
            await db.commit()
            resultados.append({"pedido_id": pid, "pedido": p.pedido_externo, "ok": True,
                               "despacho": desp.numero_despacho, "tracking": p.tracking})
        except HTTPException as e:
            await db.rollback()
            resultados.append({"pedido_id": pid, "pedido": p.pedido_externo, "ok": False, "detalle": e.detail})
    return {"resultados": resultados}


# ── Importación de pedidos (Excel / CSV) ──────────────────────────────────────

COLUMNAS = ["pedido", "fecha", "comprador", "documento", "telefono", "email", "direccion", "ciudad",
            "sku", "cantidad", "precio", "titulo"]


@router.get("/wms/canales/importar/plantilla")
async def plantilla(_=Depends(get_current_user)):
    import pandas as pd
    df = pd.DataFrame([
        {"pedido": "PED-1001", "fecha": "2026-10-07", "comprador": "Ana Gómez", "documento": "1020304050",
         "telefono": "3001234567", "email": "ana@correo.com", "direccion": "Cra 7 # 72-10 apto 501", "ciudad": "Bogotá",
         "sku": "BEB-000001", "cantidad": 2, "precio": 3500, "titulo": "Gaseosa cola 350 ml"},
        {"pedido": "PED-1001", "fecha": "2026-10-07", "comprador": "Ana Gómez", "documento": "1020304050",
         "telefono": "3001234567", "email": "ana@correo.com", "direccion": "Cra 7 # 72-10 apto 501", "ciudad": "Bogotá",
         "sku": "BEB-000001-CJ", "cantidad": 1, "precio": 39000, "titulo": "Gaseosa cola caja x12"},
    ], columns=COLUMNAS)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Pedidos")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="plantilla_pedidos.xlsx"'})


def _leer_archivo(nombre: str, contenido: bytes):
    import pandas as pd
    n = (nombre or "").lower()
    try:
        if n.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contenido), dtype=str)
        else:
            texto = contenido.decode("utf-8-sig", errors="replace")
            df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"No se pudo leer el archivo: {e}")
    df.columns = [str(c).strip().lower() for c in df.columns]
    faltan = [c for c in ("pedido", "sku", "cantidad") if c not in df.columns]
    if faltan:
        raise HTTPException(422, f"Faltan columnas obligatorias: {', '.join(faltan)}. Descargue la plantilla.")
    return df.fillna("")


def _agrupar(df) -> List[Dict[str, Any]]:
    pedidos: Dict[str, Dict[str, Any]] = {}
    for _, f in df.iterrows():
        ref = str(f.get("pedido", "")).strip()
        if not ref:
            continue
        p = pedidos.setdefault(ref, {c: str(f.get(c, "")).strip() or None for c in COLUMNAS if c not in ("sku", "cantidad", "precio", "titulo")})
        p["pedido"] = ref
        p.setdefault("lineas", []).append({"sku": str(f.get("sku", "")).strip(), "cantidad": str(f.get("cantidad", "")).strip(),
                                           "precio": str(f.get("precio", "")).strip() or None,
                                           "titulo": str(f.get("titulo", "")).strip() or None})
    return list(pedidos.values())


@router.post("/wms/canales/importar/previsualizar")
async def previsualizar(archivo: UploadFile = File(...), conector_id: int = Form(...),
                        db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    c = await db.get(MKPConector, conector_id)
    if not c:
        raise HTTPException(404, "Canal no encontrado")
    pedidos = _agrupar(_leer_archivo(archivo.filename, await archivo.read()))
    from app.api.v1.endpoints.wms_codigos import _resolver
    existentes = set((await db.execute(select(MKPPedido.pedido_externo).where(
        MKPPedido.conector_id == conector_id, MKPPedido.pedido_externo.in_([p["pedido"] for p in pedidos])))).scalars())
    for p in pedidos:
        p["ya_existe"] = p["pedido"] in existentes
        for l in p["lineas"]:
            try:
                cant = float(str(l["cantidad"]).replace(",", "."))
            except ValueError:
                cant = 0
            r = await _resolver(db, l["sku"]) if l["sku"] else None
            l["cantidad"] = cant
            l["producto"] = {"sku": r[0].sku, "nombre": r[0].nombre, "unidades": r[2]} if r else None
            l["error"] = None if (r and cant > 0) else ("Cantidad inválida" if cant <= 0 else "SKU no existe en el maestro")
        p["valido"] = not p["ya_existe"] and all(not l["error"] for l in p["lineas"])
    return {"pedidos": pedidos, "validos": sum(p["valido"] for p in pedidos), "total": len(pedidos)}


class ImportarIn(BaseModel):
    conector_id: int
    pedidos: List[Dict[str, Any]]


@router.post("/wms/canales/importar/confirmar")
async def confirmar_importacion(data: ImportarIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    c = await db.get(MKPConector, data.conector_id)
    if not c:
        raise HTTPException(404, "Canal no encontrado")
    creados = 0
    for bruto in data.pedidos:
        p = normalizar_estandar(bruto)
        if p:
            await servicio.ingresar_pedido(db, c, p, yo.id)
            creados += 1
    await servicio.registrar(db, c.id, "IMPORTACION", True, f"{creados} pedidos importados desde archivo por {yo.username}")
    await db.commit()
    return {"importados": creados}


# ═════════════════════════════════════════════════════════════════════════════
# Rutas públicas: avisos de las plataformas y autorización de MercadoLibre
# ═════════════════════════════════════════════════════════════════════════════

async def _registro(token: str) -> Optional[MKPRegistroPublico]:
    async with AsyncSessionLocal(info={"esquema": ESQUEMA_PLATAFORMA}) as s:
        return await s.get(MKPRegistroPublico, token)


async def _procesar_aviso(esquema: str, conector_id: int, cuerpo: Any, encabezados: Dict[str, str]) -> None:
    async with AsyncSessionLocal(info={"esquema": esquema}) as db:
        c = await db.get(MKPConector, conector_id)
        if not c or not c.activo:
            return
        ad = adaptador(c)
        try:
            p = ad.pedido_de_webhook(cuerpo)
            pedidos = [p] if p else [await ad.pedido(ref) for ref in ad.refs_de_webhook(cuerpo, encabezados)]
            for p in pedidos:
                if p:
                    await servicio.ingresar_pedido(db, c, p)
            servicio.guardar_credenciales(c, ad)
            if not pedidos:
                await servicio.registrar(db, c.id, "WEBHOOK", True, "Aviso recibido sin pedidos que procesar")
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            await servicio.registrar(db, c.id, "WEBHOOK", False, f"Error procesando aviso: {e}")
        await db.commit()


@router.post("/integraciones/{token}", include_in_schema=False)
async def aviso(token: str, request: Request, tareas: BackgroundTasks):
    """Avisos de las plataformas. Se responde de inmediato (MercadoLibre exige
    respuesta rápida) y el pedido se procesa justo después."""
    reg = await _registro(token)
    if not reg:
        raise HTTPException(404, "Canal no encontrado")
    crudo = await request.body()
    encabezados = {k.lower(): v for k, v in request.headers.items()}
    async with AsyncSessionLocal(info={"esquema": reg.esquema}) as db:
        c = await db.get(MKPConector, reg.conector_id)
        if not c or not adaptador(c).verificar_firma(crudo, encabezados):
            raise HTTPException(401, "Firma inválida")
    try:
        import json as _json
        cuerpo = _json.loads(crudo or b"{}")
    except ValueError:
        raise HTTPException(400, "El cuerpo debe ser JSON")
    tareas.add_task(_procesar_aviso, reg.esquema, reg.conector_id, cuerpo, encabezados)
    return {"recibido": True}


@router.get("/integraciones/mercadolibre/callback", include_in_schema=False)
async def callback_mercadolibre(request: Request, code: str = "", state: str = ""):
    reg = await _registro(state)
    if not reg or not code:
        return HTMLResponse("<h3>Autorización inválida o vencida.</h3>", status_code=400)
    async with AsyncSessionLocal(info={"esquema": reg.esquema}) as db:
        c = await db.get(MKPConector, reg.conector_id)
        ad = MercadoLibre(c.credenciales, c.config)
        try:
            await ad.canjear_codigo(code, f"{_url_publica(request)}/api/v1/integraciones/mercadolibre/callback")
            c.credenciales = dict(ad.credenciales)
            c.estado_conexion, c.ultimo_error = "OK", None
            await servicio.registrar(db, c.id, "CONEXION", True, "Cuenta de MercadoLibre autorizada")
            await db.commit()
        except ErrorConector as e:
            await servicio.registrar(db, c.id, "CONEXION", False, f"Autorización de MercadoLibre: {e}")
            await db.commit()
            return HTMLResponse(f"<h3>No se pudo autorizar: {e}</h3>", status_code=400)
    return HTMLResponse("<h2>✔ Cuenta de MercadoLibre conectada a Daily Logistics.</h2><p>Puede cerrar esta ventana.</p>")
