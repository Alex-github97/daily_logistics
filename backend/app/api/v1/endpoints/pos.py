"""POS · Punto de venta. La lógica de dinero e inventario vive en
`core/pos_servicio.py`; aquí están las rutas, la configuración y las consultas."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import pos_servicio as srv, wms_inventario as inv
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.erp import ERPEmpresa
from app.infrastructure.models.erp_facturacion import ERPResolucionFacturacion
from app.infrastructure.models.pos import (
    POSCaja, POSDevolucion, POSListaPrecio, POSMovimientoCaja, POSPago, POSPrecio, POSTurno, POSVenta,
    POSVentaLinea,
)
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import WMSAlmacen, WMSProducto, WMSZona

router = APIRouter(prefix="/pos", tags=["POS"])

ETIQUETA_MEDIO = {"EFECTIVO": "Efectivo", "TARJETA_DEBITO": "Tarjeta débito", "TARJETA_CREDITO": "Tarjeta crédito",
                  "NEQUI": "Nequi", "DAVIPLATA": "Daviplata", "TRANSFERENCIA": "Transferencia", "QR": "QR"}


def _f(v):
    return float(v) if isinstance(v, Decimal) else v


async def _nombres(db) -> Dict[int, str]:
    return {u.id: f"{u.nombre} {u.apellido}".strip() for u in (await db.execute(select(Usuario))).scalars()}


@router.get("/medios")
async def medios():
    return [{"valor": k, "nombre": v} for k, v in ETIQUETA_MEDIO.items()]


# ── Configuración: cajas ─────────────────────────────────────────────────────

class CajaIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=20)
    nombre: str = Field(min_length=1, max_length=120)
    almacen_id: int
    lista_id: int
    empresa_id: Optional[int] = None
    resolucion_id: Optional[int] = None
    descuento_maximo: float = Field(default=0, ge=0, le=100)
    activa: bool = True


async def _caja_dict(db, c: POSCaja) -> dict:
    alm = await db.get(WMSAlmacen, c.almacen_id)
    lista = await db.get(POSListaPrecio, c.lista_id)
    res = await db.get(ERPResolucionFacturacion, c.resolucion_id) if c.resolucion_id else None
    abierto = (await db.execute(select(POSTurno).where(POSTurno.caja_id == c.id, POSTurno.estado == "ABIERTO"))).scalars().first()
    nombres = await _nombres(db) if abierto else {}
    return {"id": c.id, "codigo": c.codigo, "nombre": c.nombre, "almacen_id": c.almacen_id,
            "almacen_nombre": alm.nombre if alm else None, "lista_id": c.lista_id,
            "lista_nombre": lista.nombre if lista else None, "empresa_id": c.empresa_id,
            "resolucion_id": c.resolucion_id,
            "resolucion": f"{res.prefijo} {res.desde}–{res.hasta} (vence {res.vigencia_hasta})" if res else None,
            "descuento_maximo": _f(c.descuento_maximo), "activa": c.activa,
            "turno_abierto": {"id": abierto.id, "cajero": nombres.get(abierto.cajero_id)} if abierto else None,
            "zonas_vendibles": len(await inv.ubicaciones_vendibles(db, c.almacen_id))}


async def _validar_caja(db, data: CajaIn):
    if not await db.get(WMSAlmacen, data.almacen_id):
        raise HTTPException(422, "El almacén no existe.")
    if not await db.get(POSListaPrecio, data.lista_id):
        raise HTTPException(422, "La lista de precios no existe.")
    if data.resolucion_id:
        res = await db.get(ERPResolucionFacturacion, data.resolucion_id)
        if res is None or res.tipo_documento not in ("POS", "FACTURA_VENTA"):
            raise HTTPException(422, "La resolución no existe o no es de factura/POS.")


@router.get("/cajas")
async def listar_cajas(db: AsyncSession = Depends(get_db)):
    return [await _caja_dict(db, c) for c in (await db.execute(select(POSCaja).order_by(POSCaja.codigo))).scalars()]


@router.post("/cajas", status_code=201)
async def crear_caja(data: CajaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_admin)):
    await _validar_caja(db, data)
    c = POSCaja(**data.model_dump())
    db.add(c)
    await db.commit()
    return await _caja_dict(db, c)


@router.put("/cajas/{cid}")
async def editar_caja(cid: int, data: CajaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_admin)):
    c = await db.get(POSCaja, cid)
    if c is None:
        raise HTTPException(404, "Caja no encontrada")
    await _validar_caja(db, data)
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    await db.commit()
    return await _caja_dict(db, c)


# ── Configuración: listas de precios ─────────────────────────────────────────

class ListaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: Optional[str] = None
    activa: bool = True


class PrecioIn(BaseModel):
    producto_id: int
    precio: Optional[float] = Field(default=None, ge=0)


@router.get("/listas")
async def listar_listas(db: AsyncSession = Depends(get_db)):
    conteo = dict((await db.execute(select(POSPrecio.lista_id, func.count()).group_by(POSPrecio.lista_id))).all())
    return [{"id": l.id, "nombre": l.nombre, "descripcion": l.descripcion, "activa": l.activa,
             "productos": conteo.get(l.id, 0)}
            for l in (await db.execute(select(POSListaPrecio).order_by(POSListaPrecio.nombre))).scalars()]


@router.post("/listas", status_code=201)
async def crear_lista(data: ListaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_admin)):
    l = POSListaPrecio(**data.model_dump())
    db.add(l)
    await db.commit()
    return {"id": l.id, **data.model_dump()}


@router.put("/listas/{lid}")
async def editar_lista(lid: int, data: ListaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_admin)):
    l = await db.get(POSListaPrecio, lid)
    if l is None:
        raise HTTPException(404, "Lista no encontrada")
    for k, v in data.model_dump().items():
        setattr(l, k, v)
    await db.commit()
    return {"id": l.id, **data.model_dump()}


@router.get("/listas/{lid}/precios")
async def precios_de_lista(lid: int, q: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Todos los productos activos con su precio en la lista (o sin precio)."""
    precios = {p.producto_id: p.precio for p in (await db.execute(select(POSPrecio).where(POSPrecio.lista_id == lid))).scalars()}
    consulta = select(WMSProducto).where(WMSProducto.activo.isnot(False))
    if q:
        consulta = consulta.where(or_(WMSProducto.nombre.ilike(f"%{q}%"), WMSProducto.sku.ilike(f"%{q}%"),
                                      WMSProducto.codigo_barras.ilike(f"%{q}%")))
    salida = []
    for p in (await db.execute(consulta.order_by(WMSProducto.nombre).limit(1000))).scalars():
        precio = precios.get(p.id)
        costo = Decimal(p.costo_promedio or 0)
        base = (precio / (1 + Decimal(p.tarifa_iva) / 100)) if precio else None
        salida.append({"producto_id": p.id, "sku": p.sku, "nombre": p.nombre, "codigo_barras": p.codigo_barras,
                       "tarifa_iva": _f(p.tarifa_iva), "costo_promedio": _f(costo), "precio": _f(precio),
                       "margen_pct": round(float((base - costo) / base * 100), 1) if base and base > 0 else None})
    return salida


@router.put("/listas/{lid}/precios")
async def guardar_precios(lid: int, datos: List[PrecioIn], db: AsyncSession = Depends(get_db),
                          _: Usuario = Depends(require_admin)):
    if not await db.get(POSListaPrecio, lid):
        raise HTTPException(404, "Lista no encontrada")
    actuales = {p.producto_id: p for p in (await db.execute(select(POSPrecio).where(POSPrecio.lista_id == lid))).scalars()}
    for d in datos:
        p = actuales.get(d.producto_id)
        if d.precio is None:
            if p:
                await db.delete(p)
        elif p:
            p.precio = d.precio
        else:
            if not await db.get(WMSProducto, d.producto_id):
                raise HTTPException(422, f"Producto {d.producto_id} no existe.")
            db.add(POSPrecio(lista_id=lid, producto_id=d.producto_id, precio=d.precio))
    await db.commit()
    return {"guardados": len(datos)}


# ── Configuración: qué se vende y cómo ───────────────────────────────────────

@router.get("/zonas")
async def zonas(db: AsyncSession = Depends(get_db)):
    alm = {a.id: a.nombre for a in (await db.execute(select(WMSAlmacen))).scalars()}
    return [{"id": z.id, "codigo": z.codigo, "nombre": z.nombre, "tipo": z.tipo, "almacen_id": z.almacen_id,
             "almacen_nombre": alm.get(z.almacen_id), "vendible_pos": z.vendible_pos, "activo": z.activo}
            for z in (await db.execute(select(WMSZona).order_by(WMSZona.almacen_id, WMSZona.codigo))).scalars()]


class ZonaIn(BaseModel):
    vendible_pos: bool


@router.put("/zonas/{zid}")
async def marcar_zona(zid: int, data: ZonaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_admin)):
    z = await db.get(WMSZona, zid)
    if z is None:
        raise HTTPException(404, "Zona no encontrada")
    if data.vendible_pos and (z.tipo or "").upper() in ("RECEPCION", "CUARENTENA", "DESPACHO", "TRANSITO"):
        raise HTTPException(422, f"Una zona de {z.tipo.lower()} no se vende: lo que hay ahí no está disponible.")
    z.vendible_pos = data.vendible_pos
    await db.commit()
    return {"id": z.id, "vendible_pos": z.vendible_pos}


class ProductoPOSIn(BaseModel):
    codigo_barras: Optional[str] = Field(default=None, max_length=60)
    tarifa_iva: float = Field(ge=0, le=100)


@router.put("/productos/{pid}")
async def producto_pos(pid: int, data: ProductoPOSIn, db: AsyncSession = Depends(get_db),
                       _: Usuario = Depends(require_admin)):
    p = await db.get(WMSProducto, pid)
    if p is None:
        raise HTTPException(404, "Producto no encontrado")
    cb = (data.codigo_barras or "").strip() or None
    if cb:
        otro = (await db.execute(select(WMSProducto.id).where(WMSProducto.codigo_barras == cb, WMSProducto.id != pid))).scalar()
        if otro:
            raise HTTPException(409, "Ese código de barras ya lo tiene otro producto.")
    p.codigo_barras, p.tarifa_iva = cb, data.tarifa_iva
    await db.commit()
    return {"id": p.id, "codigo_barras": p.codigo_barras, "tarifa_iva": _f(p.tarifa_iva)}


# ── Catálogo de venta de una caja ────────────────────────────────────────────

@router.get("/cajas/{cid}/catalogo")
async def catalogo(cid: int, q: Optional[str] = None, limite: int = Query(60, ge=1, le=300),
                   db: AsyncSession = Depends(get_db)):
    """Lo que esta caja puede vender: con precio en su lista y existencia en
    las zonas vendibles de su almacén. Busca por nombre, SKU o código de barras."""
    caja = await db.get(POSCaja, cid)
    if caja is None:
        raise HTTPException(404, "Caja no encontrada")
    consulta = (select(WMSProducto, POSPrecio.precio).join(POSPrecio, POSPrecio.producto_id == WMSProducto.id)
                .where(POSPrecio.lista_id == caja.lista_id, WMSProducto.activo.isnot(False)))
    if q:
        t = q.strip()
        consulta = consulta.where(or_(WMSProducto.nombre.ilike(f"%{t}%"), WMSProducto.sku.ilike(f"%{t}%"),
                                      WMSProducto.codigo_barras == t))
    filas = (await db.execute(consulta.order_by(WMSProducto.nombre).limit(limite))).all()
    ubic = await inv.ubicaciones_vendibles(db, caja.almacen_id)
    disp = await inv.disponible_en(db, [p.id for p, _ in filas], ubic)
    return [{"producto_id": p.id, "sku": p.sku, "nombre": p.nombre, "codigo_barras": p.codigo_barras,
             "unidad": p.unidad_medida, "precio": _f(precio), "tarifa_iva": _f(p.tarifa_iva),
             "disponible": float(disp.get(p.id, 0)), "imagen_url": p.imagen_url} for p, precio in filas]


# ── Turnos de caja ───────────────────────────────────────────────────────────

class AbrirIn(BaseModel):
    caja_id: int
    base_inicial: float = Field(ge=0)


class MovCajaIn(BaseModel):
    tipo: Literal["INGRESO", "RETIRO"]
    monto: float = Field(gt=0)
    motivo: str = Field(min_length=3, max_length=300)


class CerrarIn(BaseModel):
    contado: Dict[str, float]
    observaciones: Optional[str] = None


async def _turno_dict(db, t: POSTurno, nombres=None) -> dict:
    nombres = nombres or await _nombres(db)
    caja = await db.get(POSCaja, t.caja_id)
    return {"id": t.id, "caja_id": t.caja_id, "caja_nombre": caja.nombre if caja else None, "cajero_id": t.cajero_id,
            "cajero": nombres.get(t.cajero_id), "apertura": t.apertura.isoformat(), "base_inicial": _f(t.base_inicial),
            "cierre": t.cierre.isoformat() if t.cierre else None, "estado": t.estado, "esperado": t.esperado,
            "contado": t.contado, "diferencia": _f(t.diferencia), "observaciones": t.observaciones,
            "resumen": await srv.resumen_turno(db, t)}


@router.post("/turnos/abrir", status_code=201)
async def abrir_turno(data: AbrirIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    caja = await db.get(POSCaja, data.caja_id)
    if caja is None or not caja.activa:
        raise HTTPException(404, "Caja no encontrada o inactiva.")
    if (await db.execute(select(POSTurno).where(POSTurno.caja_id == caja.id, POSTurno.estado == "ABIERTO"))).scalars().first():
        raise HTTPException(409, "Esa caja ya tiene un turno abierto.")
    if (await db.execute(select(POSTurno).where(POSTurno.cajero_id == yo.id, POSTurno.estado == "ABIERTO"))).scalars().first():
        raise HTTPException(409, "Ya tiene un turno abierto en otra caja; ciérrelo primero.")
    t = POSTurno(caja_id=caja.id, cajero_id=yo.id, apertura=srv.ahora(), base_inicial=data.base_inicial)
    db.add(t)
    await db.commit()
    return await _turno_dict(db, t)


@router.get("/turnos/actual")
async def turno_actual(db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    t = (await db.execute(select(POSTurno).where(POSTurno.cajero_id == yo.id, POSTurno.estado == "ABIERTO"))).scalars().first()
    return await _turno_dict(db, t) if t else None


@router.get("/turnos")
async def listar_turnos(desde: Optional[date] = None, hasta: Optional[date] = None, caja_id: Optional[int] = None,
                        db: AsyncSession = Depends(get_db)):
    q = select(POSTurno).order_by(POSTurno.apertura.desc()).limit(200)
    if caja_id:
        q = q.where(POSTurno.caja_id == caja_id)
    if desde:
        q = q.where(POSTurno.apertura >= datetime.combine(desde, time.min, timezone.utc))
    if hasta:
        q = q.where(POSTurno.apertura < datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc))
    nombres = await _nombres(db)
    return [await _turno_dict(db, t, nombres) for t in (await db.execute(q)).scalars()]


@router.post("/turnos/{tid}/movimientos", status_code=201)
async def movimiento_caja(tid: int, data: MovCajaIn, db: AsyncSession = Depends(get_db),
                          yo: Usuario = Depends(get_current_user)):
    t = await db.get(POSTurno, tid)
    if t is None or t.estado != "ABIERTO":
        raise HTTPException(409, "El turno no está abierto.")
    if t.cajero_id != yo.id:
        raise HTTPException(403, "Solo el cajero del turno registra movimientos de su caja.")
    if data.tipo == "RETIRO":
        efectivo = Decimal(str((await srv.resumen_turno(db, t))["esperado"].get("EFECTIVO", 0)))
        if Decimal(str(data.monto)) > efectivo:
            raise HTTPException(422, f"No hay tanto efectivo en la caja (hay {efectivo}).")
    db.add(POSMovimientoCaja(turno_id=tid, tipo=data.tipo, monto=data.monto, motivo=data.motivo, usuario_id=yo.id))
    await db.commit()
    return await _turno_dict(db, t)


@router.post("/turnos/{tid}/cerrar")
async def cerrar_turno(tid: int, data: CerrarIn, db: AsyncSession = Depends(get_db),
                       yo: Usuario = Depends(get_current_user)):
    t = await db.get(POSTurno, tid)
    if t is None or t.estado != "ABIERTO":
        raise HTTPException(409, "El turno no está abierto.")
    es_admin = str(getattr(yo.rol, "value", yo.rol)).upper() == "ADMINISTRADOR"
    if t.cajero_id != yo.id and not es_admin:
        raise HTTPException(403, "Solo el cajero del turno (o un administrador) puede cerrarlo.")
    esperado = (await srv.resumen_turno(db, t))["esperado"]
    medios = set(esperado) | set(data.contado)
    diferencias = {m: round(float(data.contado.get(m, 0)) - float(esperado.get(m, 0)), 2) for m in medios}
    if diferencias and any(abs(v) >= 0.01 for v in diferencias.values()) and not (data.observaciones or "").strip():
        raise HTTPException(422, "Hay diferencias en el arqueo: explíquelas en las observaciones.")
    t.esperado, t.contado = esperado, {m: float(v) for m, v in data.contado.items()}
    t.diferencia = round(sum(diferencias.values()), 2)
    t.observaciones, t.cierre, t.estado = data.observaciones, srv.ahora(), "CERRADO"
    await db.commit()
    return {**(await _turno_dict(db, t)), "diferencias": diferencias}


# ── Ventas ───────────────────────────────────────────────────────────────────

class LineaIn(BaseModel):
    producto_id: int
    cantidad: float = Field(gt=0)
    descuento_pct: float = Field(default=0, ge=0, le=100)


class PagoIn(BaseModel):
    medio: str
    monto: float = Field(gt=0)
    referencia: Optional[str] = Field(default=None, max_length=80)


class ClienteIn(BaseModel):
    nombre: Optional[str] = None
    documento: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = None


class VentaIn(BaseModel):
    caja_id: int
    lineas: List[LineaIn]
    pagos: List[PagoIn]
    cliente: ClienteIn = ClienteIn()


async def _venta_dict(db, v: POSVenta, detalle=True) -> dict:
    nombres = await _nombres(db)
    caja = await db.get(POSCaja, v.caja_id)
    out = {"id": v.id, "numero": v.numero, "fecha": v.fecha.isoformat(), "caja_id": v.caja_id,
           "caja_nombre": caja.nombre if caja else None, "cajero": nombres.get(v.cajero_id),
           "cliente_nombre": v.cliente_nombre, "cliente_documento": v.cliente_documento,
           "subtotal": _f(v.subtotal), "descuento": _f(v.descuento), "impuestos": _f(v.impuestos), "total": _f(v.total),
           "costo_total": _f(v.costo_total), "recibido": _f(v.recibido), "cambio": _f(v.cambio), "estado": v.estado,
           "cufe": v.cufe, "factura_id": v.factura_id}
    if detalle:
        lineas = (await db.execute(select(POSVentaLinea).where(POSVentaLinea.venta_id == v.id).order_by(POSVentaLinea.id))).scalars()
        pagos = (await db.execute(select(POSPago).where(POSPago.venta_id == v.id))).scalars()
        out["lineas"] = [{"id": l.id, "producto_id": l.producto_id, "descripcion": l.descripcion,
                          "cantidad": _f(l.cantidad), "precio_unitario": _f(l.precio_unitario),
                          "descuento_pct": _f(l.descuento_pct), "tarifa_iva": _f(l.tarifa_iva), "base": _f(l.base),
                          "iva": _f(l.iva), "total": _f(l.total), "cantidad_devuelta": _f(l.cantidad_devuelta)}
                         for l in lineas]
        out["pagos"] = [{"medio": p.medio, "nombre": ETIQUETA_MEDIO.get(p.medio, p.medio), "monto": _f(p.monto),
                         "referencia": p.referencia} for p in pagos]
        emp = await db.get(ERPEmpresa, caja.empresa_id) if caja and caja.empresa_id else (
            await db.execute(select(ERPEmpresa).order_by(ERPEmpresa.id).limit(1))).scalar()
        res = await db.get(ERPResolucionFacturacion, caja.resolucion_id) if caja and caja.resolucion_id else None
        out["emisor"] = {"razon_social": emp.razon_social, "nit": emp.nit, "direccion": emp.direccion,
                         "telefono": emp.telefono} if emp else None
        out["resolucion"] = (f"Resolución DIAN {res.numero_resolucion} del {res.fecha_resolucion}, "
                             f"{res.prefijo}{res.desde} a {res.prefijo}{res.hasta}, vigente hasta {res.vigencia_hasta}") if res else None
    return out


@router.post("/ventas", status_code=201)
async def registrar_venta(data: VentaIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    venta = await srv.vender(db, yo, data.caja_id, [l.model_dump() for l in data.lineas],
                             [p.model_dump() for p in data.pagos], data.cliente.model_dump())
    await db.commit()
    return await _venta_dict(db, venta)


@router.get("/ventas")
async def listar_ventas(desde: Optional[date] = None, hasta: Optional[date] = None, caja_id: Optional[int] = None,
                        turno_id: Optional[int] = None, q: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    consulta = select(POSVenta).order_by(POSVenta.fecha.desc()).limit(500)
    if caja_id:
        consulta = consulta.where(POSVenta.caja_id == caja_id)
    if turno_id:
        consulta = consulta.where(POSVenta.turno_id == turno_id)
    if desde:
        consulta = consulta.where(POSVenta.fecha >= datetime.combine(desde, time.min, timezone.utc))
    if hasta:
        consulta = consulta.where(POSVenta.fecha < datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc))
    if q:
        consulta = consulta.where(or_(POSVenta.numero.ilike(f"%{q}%"), POSVenta.cliente_nombre.ilike(f"%{q}%"),
                                      POSVenta.cliente_documento.ilike(f"%{q}%")))
    return [await _venta_dict(db, v, detalle=False) for v in (await db.execute(consulta)).scalars()]


@router.get("/ventas/{vid}")
async def ver_venta(vid: int, db: AsyncSession = Depends(get_db)):
    v = await db.get(POSVenta, vid)
    if v is None:
        raise HTTPException(404, "Venta no encontrada")
    return await _venta_dict(db, v)


# ── Devoluciones ─────────────────────────────────────────────────────────────

class LineaDevIn(BaseModel):
    linea_id: int
    cantidad: float = Field(gt=0)
    estado: Literal["BUENO", "DANADO"] = "BUENO"


class DevolucionIn(BaseModel):
    venta_id: int
    motivo: str = Field(min_length=3)
    medio_reembolso: str = "EFECTIVO"
    lineas: List[LineaDevIn]


@router.post("/devoluciones", status_code=201)
async def registrar_devolucion(data: DevolucionIn, db: AsyncSession = Depends(get_db),
                               yo: Usuario = Depends(get_current_user)):
    dev = await srv.devolver(db, yo, data.venta_id, [l.model_dump() for l in data.lineas], data.motivo,
                             data.medio_reembolso)
    await db.commit()
    venta = await db.get(POSVenta, data.venta_id)
    return {"id": dev.id, "total": _f(dev.total), "nota_credito_id": dev.nota_credito_id,
            "venta": await _venta_dict(db, venta)}


@router.get("/devoluciones")
async def listar_devoluciones(desde: Optional[date] = None, hasta: Optional[date] = None,
                              db: AsyncSession = Depends(get_db)):
    q = select(POSDevolucion).order_by(POSDevolucion.fecha.desc()).limit(300)
    if desde:
        q = q.where(POSDevolucion.fecha >= datetime.combine(desde, time.min, timezone.utc))
    if hasta:
        q = q.where(POSDevolucion.fecha < datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc))
    nombres = await _nombres(db)
    salida = []
    for d in (await db.execute(q)).scalars():
        v = await db.get(POSVenta, d.venta_id)
        salida.append({"id": d.id, "fecha": d.fecha.isoformat(), "venta_numero": v.numero if v else None,
                       "cliente": v.cliente_nombre if v else None, "motivo": d.motivo, "total": _f(d.total),
                       "medio_reembolso": ETIQUETA_MEDIO.get(d.medio_reembolso, d.medio_reembolso),
                       "cajero": nombres.get(d.cajero_id), "lineas": d.lineas})
    return salida


# ── Tablero ──────────────────────────────────────────────────────────────────

@router.get("/tablero")
async def tablero(desde: Optional[date] = None, hasta: Optional[date] = None, db: AsyncSession = Depends(get_db)):
    hasta = hasta or (datetime.now(timezone.utc) - timedelta(hours=5)).date()
    desde = desde or hasta
    # Días de Bogotá: la medianoche local son las 05:00 UTC.
    ini = datetime.combine(desde, time.min, timezone.utc) + timedelta(hours=5)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc) + timedelta(hours=5)
    rango = (POSVenta.fecha >= ini, POSVenta.fecha < fin)
    n, total, base, iva, costo = (await db.execute(select(
        func.count(), func.coalesce(func.sum(POSVenta.total), 0), func.coalesce(func.sum(POSVenta.subtotal), 0),
        func.coalesce(func.sum(POSVenta.impuestos), 0), func.coalesce(func.sum(POSVenta.costo_total), 0)).where(*rango))).one()
    dev = (await db.execute(select(func.coalesce(func.sum(POSDevolucion.total), 0)).where(
        POSDevolucion.fecha >= ini, POSDevolucion.fecha < fin))).scalar()
    por_medio = (await db.execute(select(POSPago.medio, func.sum(POSPago.monto)).join(POSVenta, POSVenta.id == POSPago.venta_id)
                                  .where(*rango).group_by(POSPago.medio))).all()
    por_caja = (await db.execute(select(POSCaja.nombre, func.count(POSVenta.id), func.sum(POSVenta.total))
                                 .join(POSCaja, POSCaja.id == POSVenta.caja_id).where(*rango).group_by(POSCaja.nombre))).all()
    top = (await db.execute(select(POSVentaLinea.descripcion, func.sum(POSVentaLinea.cantidad), func.sum(POSVentaLinea.total),
                                   func.sum(POSVentaLinea.base - POSVentaLinea.costo_unitario * POSVentaLinea.cantidad))
                            .join(POSVenta, POSVenta.id == POSVentaLinea.venta_id).where(*rango)
                            .group_by(POSVentaLinea.descripcion).order_by(func.sum(POSVentaLinea.total).desc()).limit(10))).all()
    abiertos = (await db.execute(select(func.count()).select_from(POSTurno).where(POSTurno.estado == "ABIERTO"))).scalar()
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "ventas": n, "total": float(total),
            "base": float(base), "iva": float(iva), "costo": float(costo),
            "margen": float(base - costo), "margen_pct": round(float((base - costo) / base * 100), 1) if base else None,
            "ticket_promedio": round(float(total) / n, 0) if n else 0, "devoluciones": float(dev),
            "turnos_abiertos": abiertos,
            "por_medio": [{"medio": ETIQUETA_MEDIO.get(m, m), "total": float(t)} for m, t in por_medio],
            "por_caja": [{"caja": c, "ventas": k, "total": float(t or 0)} for c, k, t in por_caja],
            "top_productos": [{"producto": p, "cantidad": float(c), "total": float(t), "margen": float(mg or 0)}
                              for p, c, t, mg in top]}
