"""
API endpoints — WMS (Warehouse Management System)
Prefijo: /wms
"""
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, and_, or_, Integer, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core import wms_inventario
from app.core import wms_operacion as op
from app.core import wms_contable
from app.core import wms_estados_oc
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSTipoZona, WMSTipoUbicacion, WMSUnidadMedida, WMSMotivoMovimiento, WMSCategoriaProducto, WMSFamiliaProducto,
    WMSPais, WMSCiudad,
    WMSAlmacen, WMSZona, WMSUbicacion, WMSProducto, WMSLote, WMSSerie,
    WMSProveedor, WMSCliente, WMSTransportadora,
    WMSOrdenCompra, WMSOrdenCompraDetalle,
    WMSRecepcion, WMSRecepcionDetalle,
    WMSInventarioUbicacion, WMSMovimientoInventario,
    WMSConteoInventario, WMSConteoDetalle,
    WMSOrdenSalida, WMSOrdenSalidaDetalle,
    WMSPickingTarea, WMSPickingDetalle,
    WMSDespacho, WMSDespachoDetalle, WMSHistorialEstado,
    WMSDevolucion, WMSDevolucionDetalle,
    WMSEventoTrazabilidad, WMSKPIDiario, WMSContenedor,
)
from app.infrastructure.models.tms import TMSViaje, TMSVehiculo, TipoServicioTMSEnum, EstadoViajeTMSEnum

# ─── WMS — revertir estado ────────────────────────────────────────────────────
_REVERT_DESPACHO_TRANS: dict[str, str] = {
    "LISTO":       "PREPARANDO",
    "EN_TRANSITO": "LISTO",
    "ENTREGADO":   "EN_TRANSITO",
    "INCIDENCIA":  "EN_TRANSITO",
}

# Transiciones de avance permitidas para un despacho
_DESPACHO_ESTADOS = {"PREPARANDO", "LISTO", "EN_TRANSITO", "ENTREGADO", "INCIDENCIA"}
_DESPACHO_TRANS_NEXT: dict[str, set[str]] = {
    "PREPARANDO":  {"LISTO", "INCIDENCIA"},
    "LISTO":       {"EN_TRANSITO", "INCIDENCIA"},
    "EN_TRANSITO": {"ENTREGADO", "INCIDENCIA"},
    "INCIDENCIA":  {"EN_TRANSITO", "LISTO"},
    "ENTREGADO":   set(),
}


class RevertirDespachoRequest(BaseModel):
    observacion: str
from app.application.schemas.wms import (
    WMSTipoZonaCreate, WMSTipoZonaUpdate, WMSTipoZonaResponse,
    WMSTipoUbicacionCreate, WMSTipoUbicacionUpdate, WMSTipoUbicacionResponse,
    WMSMotivoMovimientoCreate, WMSMotivoMovimientoUpdate, WMSMotivoMovimientoResponse,
    WMSUnidadMedidaCreate, WMSUnidadMedidaUpdate, WMSUnidadMedidaResponse,
    WMSCategoriaProductoCreate, WMSCategoriaProductoUpdate, WMSCategoriaProductoResponse,
    WMSFamiliaProductoCreate, WMSFamiliaProductoUpdate, WMSFamiliaProductoResponse,
    WMSPaisCreate, WMSPaisUpdate, WMSPaisResponse,
    WMSCiudadCreate, WMSCiudadUpdate, WMSCiudadResponse,
    WMSAlmacenCreate, WMSAlmacenUpdate, WMSAlmacenResponse,
    WMSZonaCreate, WMSZonaUpdate, WMSZonaResponse,
    WMSUbicacionCreate, WMSUbicacionUpdate, WMSUbicacionResponse,
    WMSProductoCreate, WMSProductoUpdate, WMSProductoResponse,
    WMSLoteCreate, WMSLoteUpdate, WMSLoteResponse,
    WMSSerieCreate, WMSSerieUpdate, WMSSerieResponse,
    WMSProveedorCreate, WMSProveedorUpdate, WMSProveedorResponse,
    WMSClienteCreate, WMSClienteUpdate, WMSClienteResponse,
    WMSTransportadoraCreate, WMSTransportadoraUpdate, WMSTransportadoraResponse,
    WMSOrdenCompraCreate, WMSOrdenCompraUpdate, WMSOrdenCompraResponse,
    WMSRecepcionCreate, WMSRecepcionUpdate, WMSRecepcionResponse,
    WMSInventarioResponse, WMSAjusteInventario, WMSTransferenciaInventario, WMSReservaBloqueo, WMSMovimientoResponse,
    WMSConteoCreate, WMSConteoUpdate, WMSConteoResponse, WMSConteoDetalleUpdate,
    WMSOrdenSalidaCreate, WMSOrdenSalidaUpdate, WMSOrdenSalidaEstado, WMSOrdenSalidaResponse,
    WMSPickingTareaCreate, WMSPickingTareaUpdate, WMSPickingTareaResponse, WMSPickingConfirmItem,
    WMSDespachoCreate, WMSDespachoDetalleCreate, WMSDespachoUpdate, WMSDespachoEstado, WMSDespachoResponse,
    WMSDevolucionCreate, WMSDevolucionUpdate, WMSDevolucionProcesar, WMSDevolucionResponse,
    WMSEventoTrazabilidadResponse,
    WMSKPIs, WMSAlertasResponse, WMSFacturarDespacho,
)

router = APIRouter(prefix="/wms", tags=["wms"])


# ─── Utilidades internas ───────────────────────────────────────────────────────

async def _registrar_evento(
    db: AsyncSession,
    tipo_evento: str,
    descripcion: str,
    entidad_tipo: Optional[str] = None,
    entidad_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    producto_id: Optional[int] = None,
    lote_id: Optional[int] = None,
    ubicacion_id: Optional[int] = None,
    datos: Optional[Dict[str, Any]] = None,
):
    ev = WMSEventoTrazabilidad(
        tipo_evento=tipo_evento,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        descripcion=descripcion,
        datos_adicionales=datos,
        usuario_id=usuario_id,
        producto_id=producto_id,
        lote_id=lote_id,
        ubicacion_id=ubicacion_id,
    )
    db.add(ev)


async def _mover(db: AsyncSession, **kw):
    """`wms_inventario.mover` con los errores convertidos en respuestas: falta
    de existencias es un conflicto (409), un dato imposible es 422."""
    try:
        return await wms_inventario.mover(db, **kw)
    except wms_inventario.StockInsuficiente as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


def _capacidad_por_medidas(u: WMSUbicacion) -> None:
    """Con las tres medidas internas, la capacidad en m³ es su producto: no se
    escribe a mano (se desalineaba de las medidas)."""
    if u.largo_cm and u.ancho_cm and u.alto_cm:
        u.capacidad_m3 = round(u.largo_cm * u.ancho_cm * u.alto_cm / 1_000_000, 4)


# Series numéricas estilo ERP: 10 dígitos, la serie indica el tipo de documento
# y el consecutivo es continuo (no reinicia por año). Clave = tabla:prefijo.
SERIES_DOCUMENTO = {
    "wms_ordenes_compra:OC": 4_500_000_000,
    "wms_recepciones:REC": 5_000_000_000,
    "wms_ordenes_salida:OS": 8_000_000_000,
    "wms_despachos:DESP": 8_100_000_000,
    "wms_traslados:TRL": 4_900_000_000,
}
# Las series numéricas no reinician: su contador se guarda con año 0.
_SIN_ANIO = 0


def _formato_numero(clave: str, prefix: str, anio: int, n: int) -> str:
    """4500000042 para los documentos con serie; PREFIJO-AAAA-NNNNN para los demás
    (p. ej. los códigos de viaje del TMS que se crean desde el WMS)."""
    base = SERIES_DOCUMENTO.get(clave)
    return str(base + n) if base else f"{prefix}-{anio}-{n:05d}"


async def _next_numero(db: AsyncSession, Model, numero_col, prefix: str) -> str:
    """Siguiente número del documento (ver SERIES_DOCUMENTO).

    El contador vive en `doc_consecutivos` y se incrementa con una sola sentencia
    atómica (INSERT … ON CONFLICT … RETURNING) dentro de la transacción del
    documento: dos guardados simultáneos no pueden recibir el mismo número, y si
    el guardado falla el incremento se deshace con él (sin huecos)."""
    clave = f"{Model.__tablename__}:{prefix}"
    anio = _SIN_ANIO if clave in SERIES_DOCUMENTO else date.today().year
    while True:
        n = (await db.execute(text(
            "INSERT INTO doc_consecutivos (clave, anio, ultimo) VALUES (:c, :a, 1) "
            "ON CONFLICT (clave, anio) DO UPDATE SET ultimo = doc_consecutivos.ultimo + 1 "
            "RETURNING ultimo"), {"c": clave, "a": anio})).scalar_one()
        candidato = _formato_numero(clave, prefix, anio, n)
        # Defensa: si alguien registró ese número a mano (integración), se salta.
        if (await db.execute(select(Model.id).where(numero_col == candidato))).first() is None:
            return candidato


# Documentos cuyo próximo número se puede consultar (para mostrarlo en el formulario).
_DOCUMENTOS = {
    "OC": ("wms_ordenes_compra", "OC"),
    "REC": ("wms_recepciones", "REC"),
    "OS": ("wms_ordenes_salida", "OS"),
    "DESP": ("wms_despachos", "DESP"),
    "TRL": ("wms_traslados", "TRL"),
}


@router.get("/consecutivos/{tipo}/siguiente")
async def siguiente_numero(tipo: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """El número que tendría el próximo documento. Es una vista previa: el número
    se asigna de verdad al guardar (otro usuario puede tomarlo antes)."""
    if tipo not in _DOCUMENTOS:
        raise HTTPException(404, "Tipo de documento desconocido")
    tabla, prefix = _DOCUMENTOS[tipo]
    clave = f"{tabla}:{prefix}"
    anio = _SIN_ANIO if clave in SERIES_DOCUMENTO else date.today().year
    ultimo = (await db.execute(text(
        "SELECT ultimo FROM doc_consecutivos WHERE clave = :c AND anio = :a"),
        {"c": clave, "a": anio})).scalar() or 0
    return {"tipo": tipo, "siguiente": _formato_numero(clave, prefix, anio, ultimo + 1)}


async def _almacen_de_ubicacion(db: AsyncSession, ubicacion_id: int):
    """Devuelve el WMSAlmacen al que pertenece una ubicación (via zona)."""
    r = await db.execute(
        select(WMSAlmacen)
        .join(WMSZona, WMSAlmacen.id == WMSZona.almacen_id)
        .join(WMSUbicacion, WMSZona.id == WMSUbicacion.zona_id)
        .where(WMSUbicacion.id == ubicacion_id)
    )
    return r.scalar_one_or_none()


async def _bloquear_si_dependientes(db: AsyncSession, DepModel, fk_col, valor: int, etiqueta: str):
    """Lanza 409 si existen registros dependientes que impedirían el borrado."""
    r = await db.execute(select(func.count(DepModel.id)).where(fk_col == valor))
    n = r.scalar() or 0
    if n:
        raise HTTPException(409, f"No se puede eliminar: existen {n} {etiqueta} asociados")


# ─── CATÁLOGOS — Tipos de Zona ────────────────────────────────────────────────

def _simple_crud(Model, router, prefix, tag, SchemaCreate, SchemaUpdate, SchemaResponse):
    """Helper — genera CRUD genérico para catálogos simples sin relaciones."""
    pass  # se expande manualmente por endpoint

@router.get("/tipos-zona/", response_model=List[WMSTipoZonaResponse])
async def listar_tipos_zona(activo: Optional[bool] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSTipoZona)
    if activo is not None: q = q.where(WMSTipoZona.activo == activo)
    r = await db.execute(q.order_by(WMSTipoZona.nombre))
    return list(r.scalars().all())

@router.post("/tipos-zona/", response_model=WMSTipoZonaResponse, status_code=201)
async def crear_tipo_zona(data: WMSTipoZonaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSTipoZona(**data.model_dump()); db.add(obj); await db.flush(); await db.refresh(obj); return obj

@router.put("/tipos-zona/{id}", response_model=WMSTipoZonaResponse)
async def actualizar_tipo_zona(id: int, data: WMSTipoZonaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSTipoZona).where(WMSTipoZona.id == id))
    obj = r.scalar_one_or_none()
    if not obj: raise HTTPException(404, "No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(obj, k, v)
    await db.flush(); await db.refresh(obj); return obj

@router.delete("/tipos-zona/{id}", status_code=204)
async def eliminar_tipo_zona(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSTipoZona).where(WMSTipoZona.id == id))
    obj = r.scalar_one_or_none()
    if obj: await db.delete(obj); await db.flush()


# ─── CATÁLOGOS — Tipos de Ubicación ───────────────────────────────────────────

@router.get("/tipos-ubicacion/", response_model=List[WMSTipoUbicacionResponse])
async def listar_tipos_ubicacion(activo: Optional[bool] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSTipoUbicacion)
    if activo is not None: q = q.where(WMSTipoUbicacion.activo == activo)
    r = await db.execute(q.order_by(WMSTipoUbicacion.nombre))
    return list(r.scalars().all())

@router.post("/tipos-ubicacion/", response_model=WMSTipoUbicacionResponse, status_code=201)
async def crear_tipo_ubicacion(data: WMSTipoUbicacionCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSTipoUbicacion(**data.model_dump()); db.add(obj); await db.flush(); await db.refresh(obj); return obj

@router.put("/tipos-ubicacion/{id}", response_model=WMSTipoUbicacionResponse)
async def actualizar_tipo_ubicacion(id: int, data: WMSTipoUbicacionUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSTipoUbicacion).where(WMSTipoUbicacion.id == id))
    obj = r.scalar_one_or_none()
    if not obj: raise HTTPException(404, "No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(obj, k, v)
    await db.flush(); await db.refresh(obj); return obj

@router.delete("/tipos-ubicacion/{id}", status_code=204)
async def eliminar_tipo_ubicacion(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSTipoUbicacion).where(WMSTipoUbicacion.id == id))
    obj = r.scalar_one_or_none()
    if obj: await db.delete(obj); await db.flush()


# ─── CATÁLOGOS — Unidades de Medida ───────────────────────────────────────────

@router.get("/unidades-medida/", response_model=List[WMSUnidadMedidaResponse])
async def listar_unidades_medida(activo: Optional[bool] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSUnidadMedida)
    if activo is not None: q = q.where(WMSUnidadMedida.activo == activo)
    r = await db.execute(q.order_by(WMSUnidadMedida.nombre))
    return list(r.scalars().all())

@router.post("/unidades-medida/", response_model=WMSUnidadMedidaResponse, status_code=201)
async def crear_unidad_medida(data: WMSUnidadMedidaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSUnidadMedida(**data.model_dump()); db.add(obj); await db.flush(); await db.refresh(obj); return obj

@router.put("/unidades-medida/{id}", response_model=WMSUnidadMedidaResponse)
async def actualizar_unidad_medida(id: int, data: WMSUnidadMedidaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSUnidadMedida).where(WMSUnidadMedida.id == id))
    obj = r.scalar_one_or_none()
    if not obj: raise HTTPException(404, "No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(obj, k, v)
    await db.flush(); await db.refresh(obj); return obj

@router.delete("/unidades-medida/{id}", status_code=204)
async def eliminar_unidad_medida(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSUnidadMedida).where(WMSUnidadMedida.id == id))
    obj = r.scalar_one_or_none()
    if obj: await db.delete(obj); await db.flush()


# ─── CATÁLOGOS — Motivos de Reserva/Bloqueo ───────────────────────────────────

@router.get("/motivos-movimiento/", response_model=List[WMSMotivoMovimientoResponse])
async def listar_motivos_movimiento(
    tipo: Optional[str] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSMotivoMovimiento)
    if tipo:
        q = q.where(WMSMotivoMovimiento.tipo == tipo)
    if activo is not None:
        q = q.where(WMSMotivoMovimiento.activo == activo)
    r = await db.execute(q.order_by(WMSMotivoMovimiento.nombre))
    return r.scalars().all()

@router.post("/motivos-movimiento/", response_model=WMSMotivoMovimientoResponse, status_code=201)
async def crear_motivo_movimiento(data: WMSMotivoMovimientoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSMotivoMovimiento(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/motivos-movimiento/{id}", response_model=WMSMotivoMovimientoResponse)
async def actualizar_motivo_movimiento(id: int, data: WMSMotivoMovimientoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(WMSMotivoMovimiento, id)
    if not obj:
        raise HTTPException(404, "Motivo no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/motivos-movimiento/{id}", status_code=204)
async def eliminar_motivo_movimiento(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(WMSMotivoMovimiento, id)
    if obj:
        await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Categorías de Producto ───────────────────────────────────────

@router.get("/categorias-producto/", response_model=List[WMSCategoriaProductoResponse])
async def listar_categorias(activo: Optional[bool] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSCategoriaProducto)
    if activo is not None: q = q.where(WMSCategoriaProducto.activo == activo)
    r = await db.execute(q.order_by(WMSCategoriaProducto.nombre))
    return list(r.scalars().all())

@router.post("/categorias-producto/", response_model=WMSCategoriaProductoResponse, status_code=201)
async def crear_categoria(data: WMSCategoriaProductoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSCategoriaProducto(**data.model_dump()); db.add(obj); await db.flush(); await db.refresh(obj); return obj

@router.put("/categorias-producto/{id}", response_model=WMSCategoriaProductoResponse)
async def actualizar_categoria(id: int, data: WMSCategoriaProductoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSCategoriaProducto).where(WMSCategoriaProducto.id == id))
    obj = r.scalar_one_or_none()
    if not obj: raise HTTPException(404, "No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(obj, k, v)
    await db.flush(); await db.refresh(obj); return obj

@router.delete("/categorias-producto/{id}", status_code=204)
async def eliminar_categoria(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSCategoriaProducto).where(WMSCategoriaProducto.id == id))
    obj = r.scalar_one_or_none()
    if obj:
        await _bloquear_si_dependientes(db, WMSFamiliaProducto, WMSFamiliaProducto.categoria_id, id, "familias")
        await db.delete(obj); await db.flush()


# ─── CATÁLOGOS — Familias de Producto ─────────────────────────────────────────

@router.get("/familias-producto/", response_model=List[WMSFamiliaProductoResponse])
async def listar_familias(
    activo: Optional[bool] = None,
    categoria_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSFamiliaProducto).options(selectinload(WMSFamiliaProducto.categoria))
    if activo is not None: q = q.where(WMSFamiliaProducto.activo == activo)
    if categoria_id is not None: q = q.where(WMSFamiliaProducto.categoria_id == categoria_id)
    r = await db.execute(q.order_by(WMSFamiliaProducto.nombre))
    items = list(r.scalars().all())
    return [WMSFamiliaProductoResponse(id=f.id, nombre=f.nombre, categoria_id=f.categoria_id, activo=f.activo, categoria_nombre=f.categoria.nombre if f.categoria else None) for f in items]

@router.post("/familias-producto/", response_model=WMSFamiliaProductoResponse, status_code=201)
async def crear_familia(data: WMSFamiliaProductoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSFamiliaProducto(**data.model_dump()); db.add(obj); await db.flush()
    await db.refresh(obj)
    r = await db.execute(select(WMSCategoriaProducto).where(WMSCategoriaProducto.id == obj.categoria_id))
    cat = r.scalar_one_or_none()
    return WMSFamiliaProductoResponse(id=obj.id, nombre=obj.nombre, categoria_id=obj.categoria_id, activo=obj.activo, categoria_nombre=cat.nombre if cat else None)

@router.put("/familias-producto/{id}", response_model=WMSFamiliaProductoResponse)
async def actualizar_familia(id: int, data: WMSFamiliaProductoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSFamiliaProducto).options(selectinload(WMSFamiliaProducto.categoria)).where(WMSFamiliaProducto.id == id))
    obj = r.scalar_one_or_none()
    if not obj: raise HTTPException(404, "No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(obj, k, v)
    await db.flush(); await db.refresh(obj)
    r2 = await db.execute(select(WMSCategoriaProducto).where(WMSCategoriaProducto.id == obj.categoria_id))
    cat = r2.scalar_one_or_none()
    return WMSFamiliaProductoResponse(id=obj.id, nombre=obj.nombre, categoria_id=obj.categoria_id, activo=obj.activo, categoria_nombre=cat.nombre if cat else None)

@router.delete("/familias-producto/{id}", status_code=204)
async def eliminar_familia(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSFamiliaProducto).where(WMSFamiliaProducto.id == id))
    obj = r.scalar_one_or_none()
    if obj: await db.delete(obj); await db.flush()


# ─── CATÁLOGOS — Países ────────────────────────────────────────────────────────

@router.get("/paises/", response_model=List[WMSPaisResponse])
async def listar_paises(activo: Optional[bool] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSPais)
    if activo is not None:
        q = q.where(WMSPais.activo == activo)
    r = await db.execute(q.order_by(WMSPais.nombre))
    return list(r.scalars().all())

@router.post("/paises/", response_model=WMSPaisResponse, status_code=201)
async def crear_pais(data: WMSPaisCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSPais(**data.model_dump())
    db.add(obj); await db.flush(); await db.refresh(obj)
    return obj

@router.put("/paises/{pais_id}", response_model=WMSPaisResponse)
async def actualizar_pais(pais_id: int, data: WMSPaisUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSPais).where(WMSPais.id == pais_id))
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "País no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.flush(); await db.refresh(obj)
    return obj

@router.delete("/paises/{pais_id}", status_code=204)
async def eliminar_pais(pais_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSPais).where(WMSPais.id == pais_id))
    obj = r.scalar_one_or_none()
    if obj:
        await _bloquear_si_dependientes(db, WMSCiudad, WMSCiudad.pais_id, pais_id, "ciudades")
        await db.delete(obj)
        await db.flush()


# ─── CATÁLOGOS — Ciudades ──────────────────────────────────────────────────────

@router.get("/ciudades/", response_model=List[WMSCiudadResponse])
async def listar_ciudades(
    activo: Optional[bool] = None,
    pais_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSCiudad).options(selectinload(WMSCiudad.pais))
    if activo is not None:
        q = q.where(WMSCiudad.activo == activo)
    if pais_id is not None:
        q = q.where(WMSCiudad.pais_id == pais_id)
    r = await db.execute(q.order_by(WMSCiudad.nombre))
    items = list(r.scalars().all())
    return [
        WMSCiudadResponse(
            id=c.id, nombre=c.nombre, pais_id=c.pais_id,
            activo=c.activo, pais_nombre=c.pais.nombre if c.pais else None,
            created_at=c.created_at,
        )
        for c in items
    ]

@router.post("/ciudades/", response_model=WMSCiudadResponse, status_code=201)
async def crear_ciudad(data: WMSCiudadCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = WMSCiudad(**data.model_dump())
    db.add(obj); await db.flush()
    await db.refresh(obj)
    r = await db.execute(select(WMSPais).where(WMSPais.id == obj.pais_id))
    p = r.scalar_one_or_none()
    return WMSCiudadResponse(id=obj.id, nombre=obj.nombre, pais_id=obj.pais_id, activo=obj.activo, pais_nombre=p.nombre if p else None, created_at=obj.created_at)

@router.put("/ciudades/{ciudad_id}", response_model=WMSCiudadResponse)
async def actualizar_ciudad(ciudad_id: int, data: WMSCiudadUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSCiudad).options(selectinload(WMSCiudad.pais)).where(WMSCiudad.id == ciudad_id))
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Ciudad no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.flush(); await db.refresh(obj)
    r2 = await db.execute(select(WMSPais).where(WMSPais.id == obj.pais_id))
    p = r2.scalar_one_or_none()
    return WMSCiudadResponse(id=obj.id, nombre=obj.nombre, pais_id=obj.pais_id, activo=obj.activo, pais_nombre=p.nombre if p else None, created_at=obj.created_at)

@router.delete("/ciudades/{ciudad_id}", status_code=204)
async def eliminar_ciudad(ciudad_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(WMSCiudad).where(WMSCiudad.id == ciudad_id))
    obj = r.scalar_one_or_none()
    if obj:
        await db.delete(obj)
        await db.flush()


# ─── CATÁLOGOS — Almacenes ─────────────────────────────────────────────────────

@router.get("/almacenes/", response_model=List[WMSAlmacenResponse])
async def listar_almacenes(
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSAlmacen)
    if activo is not None:
        q = q.where(WMSAlmacen.activo == activo)
    r = await db.execute(q.order_by(WMSAlmacen.nombre))
    return r.scalars().all()


@router.post("/almacenes/", response_model=WMSAlmacenResponse, status_code=201)
async def crear_almacen(
    data: WMSAlmacenCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = WMSAlmacen(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/almacenes/{almacen_id}", response_model=WMSAlmacenResponse)
async def actualizar_almacen(
    almacen_id: int,
    data: WMSAlmacenUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSAlmacen, almacen_id)
    if not obj:
        raise HTTPException(404, "Almacén no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/almacenes/{almacen_id}", status_code=204)
async def eliminar_almacen(
    almacen_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSAlmacen, almacen_id)
    if not obj:
        raise HTTPException(404, "Almacén no encontrado")
    await _bloquear_si_dependientes(db, WMSZona, WMSZona.almacen_id, almacen_id, "zonas")
    await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Zonas ────────────────────────────────────────────────────────

@router.get("/zonas/", response_model=List[WMSZonaResponse])
async def listar_zonas(
    almacen_id: Optional[int] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSZona)
    if almacen_id:
        q = q.where(WMSZona.almacen_id == almacen_id)
    if activo is not None:
        q = q.where(WMSZona.activo == activo)
    r = await db.execute(q.order_by(WMSZona.codigo))
    return r.scalars().all()


@router.post("/zonas/", response_model=WMSZonaResponse, status_code=201)
async def crear_zona(
    data: WMSZonaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = WMSZona(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/zonas/{zona_id}", response_model=WMSZonaResponse)
async def actualizar_zona(
    zona_id: int,
    data: WMSZonaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSZona, zona_id)
    if not obj:
        raise HTTPException(404, "Zona no encontrada")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/zonas/{zona_id}", status_code=204)
async def eliminar_zona(
    zona_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSZona, zona_id)
    if not obj:
        raise HTTPException(404, "Zona no encontrada")
    await _bloquear_si_dependientes(db, WMSUbicacion, WMSUbicacion.zona_id, zona_id, "ubicaciones")
    await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Ubicaciones ──────────────────────────────────────────────────

@router.get("/ubicaciones/", response_model=List[WMSUbicacionResponse])
async def listar_ubicaciones(
    zona_id: Optional[int] = None,
    tipo: Optional[str] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSUbicacion)
    if zona_id:
        q = q.where(WMSUbicacion.zona_id == zona_id)
    if tipo:
        q = q.where(WMSUbicacion.tipo == tipo)
    if activo is not None:
        q = q.where(WMSUbicacion.activo == activo)
    r = await db.execute(q.order_by(WMSUbicacion.codigo))
    return r.scalars().all()


@router.post("/ubicaciones/", response_model=WMSUbicacionResponse, status_code=201)
async def crear_ubicacion(
    data: WMSUbicacionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = WMSUbicacion(**data.model_dump())
    _capacidad_por_medidas(obj)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/ubicaciones/{ubicacion_id}", response_model=WMSUbicacionResponse)
async def actualizar_ubicacion(
    ubicacion_id: int,
    data: WMSUbicacionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSUbicacion, ubicacion_id)
    if not obj:
        raise HTTPException(404, "Ubicación no encontrada")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    _capacidad_por_medidas(obj)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/ubicaciones/{ubicacion_id}", status_code=204)
async def eliminar_ubicacion(
    ubicacion_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSUbicacion, ubicacion_id)
    if not obj:
        raise HTTPException(404, "Ubicación no encontrada")
    await _bloquear_si_dependientes(db, WMSInventarioUbicacion, WMSInventarioUbicacion.ubicacion_id, ubicacion_id, "registros de inventario")
    await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Productos ────────────────────────────────────────────────────

@router.get("/productos/", response_model=List[WMSProductoResponse])
async def listar_productos(
    categoria: Optional[str] = None,
    activo: Optional[bool] = None,
    q: Optional[str] = Query(None, description="Buscar por SKU o nombre"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(WMSProducto)
    if categoria:
        stmt = stmt.where(WMSProducto.categoria == categoria)
    if activo is not None:
        stmt = stmt.where(WMSProducto.activo == activo)
    if q:
        stmt = stmt.where(
            or_(WMSProducto.sku.ilike(f"%{q}%"), WMSProducto.nombre.ilike(f"%{q}%"))
        )
    r = await db.execute(stmt.order_by(WMSProducto.nombre))
    return r.scalars().all()


@router.post("/productos/", response_model=WMSProductoResponse, status_code=201)
async def crear_producto(
    data: WMSProductoCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    payload = data.model_dump()
    # Todo producto tiene dueño: sin decirlo, es mercancía propia.
    if payload.get("depositante_id") is None:
        payload["depositante_id"] = await op.depositante_propio(db)
    obj = WMSProducto(**payload)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/productos/{producto_id}", response_model=WMSProductoResponse)
async def actualizar_producto(
    producto_id: int,
    data: WMSProductoUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSProducto, producto_id)
    if not obj:
        raise HTTPException(404, "Producto no encontrado")
    if data.depositante_id is not None and data.depositante_id != obj.depositante_id:
        # Cambiar el dueño de mercancía que está en bodega sería traspasarla sin
        # documento: solo se permite mientras no haya existencias.
        if await wms_inventario.existencia_total(db, producto_id) > 0:
            raise HTTPException(409, "El producto tiene existencias: no se le puede cambiar el depositante.")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/productos/{producto_id}", status_code=204)
async def eliminar_producto(
    producto_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSProducto, producto_id)
    if not obj:
        raise HTTPException(404, "Producto no encontrado")
    await _bloquear_si_dependientes(db, WMSInventarioUbicacion, WMSInventarioUbicacion.producto_id, producto_id, "registros de inventario")
    await _bloquear_si_dependientes(db, WMSLote, WMSLote.producto_id, producto_id, "lotes")
    await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Lotes ────────────────────────────────────────────────────────

@router.get("/lotes/", response_model=List[WMSLoteResponse])
async def listar_lotes(
    producto_id: Optional[int] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSLote)
    if producto_id:
        q = q.where(WMSLote.producto_id == producto_id)
    if activo is not None:
        q = q.where(WMSLote.activo == activo)
    r = await db.execute(q.order_by(WMSLote.numero_lote))
    return r.scalars().all()


@router.post("/lotes/", response_model=WMSLoteResponse, status_code=201)
async def crear_lote(
    data: WMSLoteCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = WMSLote(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/lotes/{lote_id}", response_model=WMSLoteResponse)
async def actualizar_lote(
    lote_id: int,
    data: WMSLoteUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSLote, lote_id)
    if not obj:
        raise HTTPException(404, "Lote no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/lotes/{lote_id}", status_code=204)
async def eliminar_lote(
    lote_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSLote, lote_id)
    if not obj:
        raise HTTPException(404, "Lote no encontrado")
    await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Proveedores WMS ──────────────────────────────────────────────

@router.get("/proveedores/", response_model=List[WMSProveedorResponse])
async def listar_proveedores_wms(
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSProveedor)
    if activo is not None:
        q = q.where(WMSProveedor.activo == activo)
    r = await db.execute(q.order_by(WMSProveedor.nombre))
    return r.scalars().all()


@router.post("/proveedores/", response_model=WMSProveedorResponse, status_code=201)
async def crear_proveedor_wms(
    data: WMSProveedorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = WMSProveedor(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/proveedores/{proveedor_id}", response_model=WMSProveedorResponse)
async def actualizar_proveedor_wms(
    proveedor_id: int,
    data: WMSProveedorUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSProveedor, proveedor_id)
    if not obj:
        raise HTTPException(404, "Proveedor no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/proveedores/{proveedor_id}", status_code=204)
async def eliminar_proveedor_wms(
    proveedor_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSProveedor, proveedor_id)
    if not obj:
        raise HTTPException(404, "Proveedor no encontrado")
    await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Clientes WMS ─────────────────────────────────────────────────

@router.get("/clientes/", response_model=List[WMSClienteResponse])
async def listar_clientes_wms(
    segmento: Optional[str] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSCliente)
    if segmento:
        q = q.where(WMSCliente.segmento == segmento)
    if activo is not None:
        q = q.where(WMSCliente.activo == activo)
    r = await db.execute(q.order_by(WMSCliente.nombre))
    return r.scalars().all()


@router.post("/clientes/", response_model=WMSClienteResponse, status_code=201)
async def crear_cliente_wms(
    data: WMSClienteCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = WMSCliente(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/clientes/{cliente_id}", response_model=WMSClienteResponse)
async def actualizar_cliente_wms(
    cliente_id: int,
    data: WMSClienteUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSCliente, cliente_id)
    if not obj:
        raise HTTPException(404, "Cliente no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/clientes/{cliente_id}", status_code=204)
async def eliminar_cliente_wms(
    cliente_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSCliente, cliente_id)
    if not obj:
        raise HTTPException(404, "Cliente no encontrado")
    await db.delete(obj); await db.commit()


# ─── CATÁLOGOS — Transportadoras ──────────────────────────────────────────────

@router.get("/transportadoras/", response_model=List[WMSTransportadoraResponse])
async def listar_transportadoras(
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(WMSTransportadora)
    if activo is not None:
        q = q.where(WMSTransportadora.activo == activo)
    r = await db.execute(q.order_by(WMSTransportadora.nombre))
    return r.scalars().all()


@router.post("/transportadoras/", response_model=WMSTransportadoraResponse, status_code=201)
async def crear_transportadora(
    data: WMSTransportadoraCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = WMSTransportadora(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/transportadoras/{trans_id}", response_model=WMSTransportadoraResponse)
async def actualizar_transportadora(
    trans_id: int,
    data: WMSTransportadoraUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSTransportadora, trans_id)
    if not obj:
        raise HTTPException(404, "Transportadora no encontrada")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/transportadoras/{trans_id}", status_code=204)
async def eliminar_transportadora(
    trans_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSTransportadora, trans_id)
    if not obj:
        raise HTTPException(404, "Transportadora no encontrada")
    await db.delete(obj); await db.commit()


# ─── INBOUND — Órdenes de Compra ──────────────────────────────────────────────

@router.get("/ordenes-compra/", response_model=List[WMSOrdenCompraResponse])
async def listar_ordenes_compra(
    estado: Optional[str] = None,
    proveedor_id: Optional[int] = None,
    almacen_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(WMSOrdenCompra)
        .options(
            selectinload(WMSOrdenCompra.proveedor),
            selectinload(WMSOrdenCompra.almacen),
            selectinload(WMSOrdenCompra.detalles).selectinload(WMSOrdenCompraDetalle.producto),
        )
        .where(WMSOrdenCompra.deleted_at.is_(None))
    )
    if estado:
        q = q.where(WMSOrdenCompra.estado == estado)
    if proveedor_id:
        q = q.where(WMSOrdenCompra.proveedor_id == proveedor_id)
    if almacen_id:
        q = q.where(WMSOrdenCompra.almacen_id == almacen_id)
    r = await db.execute(q.order_by(WMSOrdenCompra.fecha_emision.desc()))
    ocs = r.scalars().all()
    # Si todavía se puede corregir o eliminar (estado inicial, sin recepciones
    # ni cambios de estado): la pantalla muestra los botones según esto.
    from app.api.v1.endpoints.wms_estados_oc import ids_editables
    editables = await ids_editables(db, ocs)
    for o in ocs:
        o.editable = o.id in editables
    return ocs


@router.post("/ordenes-compra/", response_model=WMSOrdenCompraResponse, status_code=201)
async def crear_orden_compra(
    data: WMSOrdenCompraCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    payload = data.model_dump(exclude={"detalles"})
    if not payload.get("numero_oc"):
        payload["numero_oc"] = await _next_numero(db, WMSOrdenCompra, WMSOrdenCompra.numero_oc, "OC")
    if not payload.get("fecha_emision"):
        payload["fecha_emision"] = date.today()
    payload["depositante_id"] = await op.resolver_depositante(
        db, payload.get("depositante_id"), [d.producto_id for d in data.detalles])
    # Estado configurable: si no viene uno válido, el que la empresa marcó como inicial.
    if not payload.get("estado") or payload["estado"] == "PENDIENTE" or not await wms_estados_oc.existe(db, payload["estado"]):
        payload["estado"] = await wms_estados_oc.codigo_de(db, "INICIAL") or "PENDIENTE"
    oc = WMSOrdenCompra(**payload)
    db.add(oc)
    await db.flush()
    for d in data.detalles:
        det = WMSOrdenCompraDetalle(orden_id=oc.id, **d.model_dump())
        db.add(det)
    await db.commit()
    r = await db.execute(
        select(WMSOrdenCompra)
        .options(
            selectinload(WMSOrdenCompra.proveedor),
            selectinload(WMSOrdenCompra.almacen),
            selectinload(WMSOrdenCompra.detalles).selectinload(WMSOrdenCompraDetalle.producto),
        )
        .where(WMSOrdenCompra.id == oc.id)
    )
    return r.scalar_one()


@router.put("/ordenes-compra/{oc_id}", response_model=WMSOrdenCompraResponse)
async def actualizar_orden_compra(
    oc_id: int,
    data: WMSOrdenCompraUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSOrdenCompra, oc_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Orden de compra no encontrada")
    if data.estado and not await wms_estados_oc.existe(db, data.estado):
        raise HTTPException(422, f"El estado «{data.estado}» no existe o está inactivo.")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit()
    r = await db.execute(
        select(WMSOrdenCompra)
        .options(
            selectinload(WMSOrdenCompra.proveedor),
            selectinload(WMSOrdenCompra.almacen),
            selectinload(WMSOrdenCompra.detalles).selectinload(WMSOrdenCompraDetalle.producto),
        )
        .where(WMSOrdenCompra.id == oc_id)
    )
    return r.scalar_one()


# ─── INBOUND — Recepciones ────────────────────────────────────────────────────

@router.get("/recepciones/", response_model=List[WMSRecepcionResponse])
async def listar_recepciones(
    estado: Optional[str] = None,
    almacen_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(WMSRecepcion)
        .options(
            selectinload(WMSRecepcion.almacen),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.producto),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.lote),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.ubicacion),
        )
        .where(WMSRecepcion.deleted_at.is_(None))
    )
    if estado:
        q = q.where(WMSRecepcion.estado == estado)
    if almacen_id:
        q = q.where(WMSRecepcion.almacen_id == almacen_id)
    r = await db.execute(q.order_by(WMSRecepcion.fecha_recepcion.desc()))
    return r.scalars().all()


@router.post("/recepciones/", response_model=WMSRecepcionResponse, status_code=201)
async def crear_recepcion(
    data: WMSRecepcionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    payload = data.model_dump(exclude={"detalles"})
    if not payload.get("numero_recepcion"):
        payload["numero_recepcion"] = await _next_numero(db, WMSRecepcion, WMSRecepcion.numero_recepcion, "REC")
    if not payload.get("fecha_recepcion"):
        payload["fecha_recepcion"] = date.today()
    # La OC tiene que admitir recepciones; al registrar una, pasa a «en recepción».
    if payload.get("orden_compra_id"):
        oc_rec = await db.get(WMSOrdenCompra, payload["orden_compra_id"])
        if not oc_rec or oc_rec.deleted_at:
            raise HTTPException(404, "Orden de compra no encontrada")
        rol_oc = await wms_estados_oc.rol_de(db, oc_rec.estado)
        if rol_oc in wms_estados_oc.ROLES_SIN_RECEPCION:
            raise HTTPException(409, f"La orden {oc_rec.numero_oc} está «{oc_rec.estado}» y ya no admite recepciones.")
        if rol_oc != "RECIBIDA_PARCIAL":
            en_recepcion = await wms_estados_oc.codigo_de(db, "EN_RECEPCION")
            if en_recepcion:
                oc_rec.estado = en_recepcion
    # El dueño: el de la orden de compra, o el de los productos.
    if payload.get("orden_compra_id") and not payload.get("depositante_id"):
        oc = await db.get(WMSOrdenCompra, payload["orden_compra_id"])
        payload["depositante_id"] = oc.depositante_id if oc else None
    payload["depositante_id"] = await op.resolver_depositante(
        db, payload.get("depositante_id"), [d.producto_id for d in data.detalles])
    # Registrar la recepción es que el vehículo ya está en el muelle.
    if not payload.get("fecha_llegada"):
        payload["fecha_llegada"] = op.ahora()
    rec = WMSRecepcion(**payload, operario_id=current_user.id)
    db.add(rec)
    await db.flush()
    for d in data.detalles:
        if not d.producto_id:
            raise HTTPException(400, "Cada línea de recepción debe tener un producto válido")
        det = WMSRecepcionDetalle(recepcion_id=rec.id, **d.model_dump())
        db.add(det)
    await db.commit()
    r = await db.execute(
        select(WMSRecepcion)
        .options(
            selectinload(WMSRecepcion.almacen),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.producto),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.lote),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.ubicacion),
        )
        .where(WMSRecepcion.id == rec.id)
    )
    return r.scalar_one()


@router.put("/recepciones/{rec_id}", response_model=WMSRecepcionResponse)
async def actualizar_recepcion(
    rec_id: int,
    data: WMSRecepcionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSRecepcion, rec_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Recepción no encontrada")
    if obj.estado == "COMPLETA":
        raise HTTPException(400, "No se puede modificar una recepción completa")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit()
    r = await db.execute(
        select(WMSRecepcion)
        .options(
            selectinload(WMSRecepcion.almacen),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.producto),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.lote),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.ubicacion),
        )
        .where(WMSRecepcion.id == rec_id)
    )
    return r.scalar_one()


@router.post("/recepciones/{rec_id}/completar", response_model=WMSRecepcionResponse)
async def completar_recepcion(
    rec_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Cierra la recepción (PUT_AWAY): actualiza inventario por ubicación para
    cada detalle con estado_calidad APROBADO y con ubicacion_id asignada.
    """
    r = await db.execute(
        select(WMSRecepcion)
        .options(
            selectinload(WMSRecepcion.almacen),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.producto),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.lote),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.ubicacion),
        )
        .where(WMSRecepcion.id == rec_id)
    )
    rec = r.scalar_one_or_none()
    if not rec or rec.deleted_at:
        raise HTTPException(404, "Recepción no encontrada")
    if rec.estado == "COMPLETA":
        raise HTTPException(400, "Recepción ya está completa")

    # El dueño se verifica también al cerrar: una línea agregada después no
    # puede meter mercancía de otro depositante.
    rec.depositante_id = await op.resolver_depositante(
        db, rec.depositante_id, [d.producto_id for d in rec.detalles])
    almacen = rec.almacen
    dirigido = (almacen.flujo_recepcion or "DIRECTO") == "DIRIGIDO"

    # Precio de compra por producto, de la orden de compra: es lo que valoriza
    # la entrada y alimenta el costo promedio con que el POS calcula el costo
    # de ventas. Sin orden, la entrada entra al costo promedio vigente.
    precio_oc: dict = {}
    if rec.orden_compra_id:
        for ocd in (await db.execute(select(WMSOrdenCompraDetalle).where(
                WMSOrdenCompraDetalle.orden_id == rec.orden_compra_id))).scalars():
            if ocd.precio_unitario is not None:
                precio_oc[ocd.producto_id] = ocd.precio_unitario

    # Dónde cae la mercancía: en el flujo dirigido, la zona de recepción (luego
    # una tarea la ubica); en el directo, la ubicación de la línea o una de
    # almacenamiento. Antes caía en «la primera ubicación del almacén», que
    # podía ser cuarentena o despacho.
    staging = await wms_inventario.ubicacion_de_zona(db, rec.almacen_id, "RECEPCION")
    if dirigido and staging is None:
        raise HTTPException(422, f"El almacén {almacen.nombre} recibe con ubicación dirigida y no tiene "
                                 "zona de RECEPCION con ubicaciones.")
    por_defecto = await wms_inventario.ubicacion_de_zona(db, rec.almacen_id, "ALMACENAMIENTO")
    cuarentena = await wms_inventario.ubicacion_de_zona(db, rec.almacen_id, "CUARENTENA")
    doc = dict(documento_tipo="RECEPCION", documento_id=rec.id, referencia=rec.numero_recepcion,
               usuario_id=current_user.id)
    tareas = 0

    for det in rec.detalles:
        if det.cantidad_recibida <= 0:
            continue
        costo = precio_oc.get(det.producto_id)
        if det.estado_calidad == "RECHAZADO":
            # No entra al inventario, pero queda constancia de que llegó y se rechazó.
            await _registrar_evento(
                db, "RECEPCION_RECHAZADA", f"Rechazadas {det.cantidad_recibida:g} und en {rec.numero_recepcion}",
                entidad_tipo="WMSRecepcion", entidad_id=rec_id, usuario_id=current_user.id,
                producto_id=det.producto_id, lote_id=det.lote_id, datos={"notas": det.notas})
            continue
        if det.estado_calidad in ("CUARENTENA", "INSPECCION"):
            # Entra, pero bloqueada: está físicamente en la bodega y no se puede alistar.
            destino = cuarentena or det.ubicacion_id or staging or por_defecto
            if destino is None:
                raise HTTPException(422, "El almacén no tiene dónde dejar la mercancía en cuarentena.")
            det.ubicacion_id = destino
            await _mover(db, tipo="RECEPCION", producto_id=det.producto_id, cantidad=det.cantidad_recibida,
                         lote_id=det.lote_id, destino=destino, estado_destino="BLOQUEADO",
                         contenedor_destino=det.contenedor_id, costo_unitario=costo,
                         notas=f"Recepción en {det.estado_calidad.lower()}", **doc)
            continue
        if dirigido:
            lpn = det.contenedor_id
            if lpn is None:
                c = await op.crear_contenedor(db, almacen_id=rec.almacen_id, ubicacion_id=staging,
                                              depositante_id=rec.depositante_id, usuario_id=current_user.id,
                                              documento_tipo="RECEPCION", documento_id=rec.id)
                lpn = det.contenedor_id = c.id
            mov = await _mover(db, tipo="RECEPCION", producto_id=det.producto_id, cantidad=det.cantidad_recibida,
                               lote_id=det.lote_id, destino=staging, contenedor_destino=lpn, costo_unitario=costo,
                               notas="Recibido en muelle; pendiente de ubicar", **doc)
            await op.crear_tarea_ubicacion(
                db, almacen_id=rec.almacen_id, producto_id=det.producto_id, lote_id=det.lote_id,
                contenedor_id=lpn, cantidad=det.cantidad_recibida, origen=staging,
                sugerida=det.ubicacion_id, razon="Indicada en la recepción" if det.ubicacion_id else None,
                depositante_id=rec.depositante_id, documento_tipo="RECEPCION", documento_id=rec.id)
            tareas += 1
            destino_ubic = staging
        else:
            destino_ubic = det.ubicacion_id or por_defecto or staging
            if destino_ubic is None:
                raise HTTPException(422, f"El almacén {almacen.nombre} no tiene ubicaciones de almacenamiento.")
            det.ubicacion_id = destino_ubic
            mov = await _mover(db, tipo="RECEPCION", producto_id=det.producto_id, cantidad=det.cantidad_recibida,
                               lote_id=det.lote_id, destino=destino_ubic, contenedor_destino=det.contenedor_id,
                               costo_unitario=costo, notas=f"Recepción {rec.numero_recepcion} completada", **doc)
        await _registrar_evento(
            db, "RECEPCION_COMPLETADA",
            f"Ingreso {det.cantidad_recibida:g} und de producto {det.producto_id}",
            entidad_tipo="WMSRecepcion", entidad_id=rec_id,
            usuario_id=current_user.id,
            producto_id=det.producto_id, lote_id=det.lote_id,
            ubicacion_id=destino_ubic, datos={"contenedor_id": det.contenedor_id, "dirigido": dirigido},
        )
    rec.completada_en = op.ahora()
    if rec.fin_descargue is None:
        rec.fin_descargue = rec.completada_en
    rec.estado = "COMPLETA"

    # Actualizar OC si aplica: COMPLETA solo si todas las líneas quedan cubiertas.
    if rec.orden_compra_id:
        oc = await db.get(WMSOrdenCompra, rec.orden_compra_id)
        if oc:
            oc_dets_r = await db.execute(
                select(WMSOrdenCompraDetalle).where(WMSOrdenCompraDetalle.orden_id == oc.id)
            )
            oc_dets = oc_dets_r.scalars().all()
            for ocd in oc_dets:
                for det in rec.detalles:
                    if det.producto_id == ocd.producto_id:
                        ocd.cantidad_recibida = (ocd.cantidad_recibida or 0) + det.cantidad_recibida
            completa = oc_dets and all(
                (ocd.cantidad_recibida or 0) >= (ocd.cantidad_solicitada or 0) for ocd in oc_dets
            )
            oc.estado = (await wms_estados_oc.codigo_de(db, "RECIBIDA" if completa else "RECIBIDA_PARCIAL")
                         or ("COMPLETA" if completa else "PARCIAL"))

    # La mercancía propia entra al inventario del ERP contra «por facturar».
    await wms_contable.contabilizar_recepcion(db, rec, current_user.username)
    await db.commit()
    r2 = await db.execute(
        select(WMSRecepcion)
        .options(
            selectinload(WMSRecepcion.almacen),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.producto),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.lote),
            selectinload(WMSRecepcion.detalles).selectinload(WMSRecepcionDetalle.ubicacion),
        )
        .where(WMSRecepcion.id == rec_id)
    )
    return r2.scalar_one()


# ─── INVENTARIO ────────────────────────────────────────────────────────────────

@router.get("/inventario/", response_model=List[WMSInventarioResponse])
async def ver_inventario(
    almacen_id: Optional[int] = None,
    producto_id: Optional[int] = None,
    ubicacion_id: Optional[int] = None,
    lote_id: Optional[int] = None,
    zona: Optional[str] = None,
    producto: Optional[str] = None,
    depositante_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(WMSInventarioUbicacion)
        .options(
            selectinload(WMSInventarioUbicacion.producto),
            selectinload(WMSInventarioUbicacion.ubicacion),
            selectinload(WMSInventarioUbicacion.lote),
        )
    )
    if producto_id:
        q = q.where(WMSInventarioUbicacion.producto_id == producto_id)
    if ubicacion_id:
        q = q.where(WMSInventarioUbicacion.ubicacion_id == ubicacion_id)
    if lote_id:
        q = q.where(WMSInventarioUbicacion.lote_id == lote_id)
    if almacen_id or (zona and zona.strip()):
        q = q.join(WMSUbicacion, WMSInventarioUbicacion.ubicacion_id == WMSUbicacion.id)\
             .join(WMSZona, WMSUbicacion.zona_id == WMSZona.id)
        if almacen_id:
            q = q.where(WMSZona.almacen_id == almacen_id)
        if zona and zona.strip():
            like = f"%{zona.strip()}%"
            q = q.where(or_(WMSZona.codigo.ilike(like), WMSZona.nombre.ilike(like), WMSZona.tipo.ilike(like)))
    if producto and producto.strip():
        like = f"%{producto.strip()}%"
        q = q.join(WMSProducto, WMSInventarioUbicacion.producto_id == WMSProducto.id)\
             .where(or_(WMSProducto.sku.ilike(like), WMSProducto.nombre.ilike(like)))
    if depositante_id:
        q = q.where(WMSInventarioUbicacion.producto_id.in_(
            select(WMSProducto.id).where(WMSProducto.depositante_id == depositante_id)))
    filas = (await db.execute(q)).scalars().all()
    # El código de la estiba de cada fila (lo que el operario ve en la etiqueta).
    ids = {f.contenedor_id for f in filas if f.contenedor_id}
    if ids:
        codigos = dict((await db.execute(select(WMSContenedor.id, WMSContenedor.codigo)
                                          .where(WMSContenedor.id.in_(ids)))).all())
        for f in filas:
            f.contenedor_codigo = codigos.get(f.contenedor_id)
    return filas


@router.post("/inventario/ajuste/", response_model=WMSMovimientoResponse, status_code=201)
async def ajustar_inventario(
    data: WMSAjusteInventario,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Ajuste manual: deja el DISPONIBLE de la fila en `cantidad_nueva`. El
    kárdex guarda la diferencia, el motivo y en qué quedó la fila."""
    f = await wms_inventario.fila(db, data.producto_id, data.ubicacion_id, data.lote_id, data.contenedor_id)
    # BLOQUEADO ajusta lo retenido (cuarentena): así se da de baja lo dañado.
    estado = data.estado
    cantidad_anterior = (getattr(f, wms_inventario.ESTADOS[estado]) or 0) if f else 0
    delta = data.cantidad_nueva - cantidad_anterior
    if abs(delta) < 1e-9:
        raise HTTPException(422, f"La ubicación ya tiene {cantidad_anterior:g} disponibles: no hay nada que ajustar.")
    mov = await _mover(db, tipo="AJUSTE", producto_id=data.producto_id, cantidad=abs(delta), lote_id=data.lote_id,
                       origen=data.ubicacion_id if delta < 0 else None,
                       destino=data.ubicacion_id if delta > 0 else None,
                       contenedor_origen=data.contenedor_id, contenedor_destino=data.contenedor_id,
                       documento_tipo="AJUSTE", referencia="AJUSTE_MANUAL", usuario_id=current_user.id,
                       notas=data.motivo, estado_origen=estado, estado_destino=estado)
    await wms_contable.contabilizar_ajuste(db, [mov], current_user.username, f"Ajuste de inventario ({data.motivo})",
                                           "AJUSTE", mov.id)
    await _registrar_evento(
        db, "AJUSTE_INVENTARIO",
        f"Ajuste de {cantidad_anterior:g} a {data.cantidad_nueva:g} unidades — {data.motivo}",
        entidad_tipo="WMSInventarioUbicacion",
        usuario_id=current_user.id,
        producto_id=data.producto_id, lote_id=data.lote_id, ubicacion_id=data.ubicacion_id,
        datos={"anterior": cantidad_anterior, "nueva": data.cantidad_nueva, "motivo": data.motivo},
    )
    await db.commit()
    r2 = await db.execute(
        select(WMSMovimientoInventario)
        .options(selectinload(WMSMovimientoInventario.producto))
        .where(WMSMovimientoInventario.id == mov.id)
    )
    return r2.scalar_one()


@router.post("/inventario/transferencia/", response_model=WMSMovimientoResponse, status_code=201)
async def transferir_inventario(
    data: WMSTransferenciaInventario,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Mueve stock de una ubicación a otra.

    Dentro del mismo almacén el movimiento es inmediato. Entre almacenes es un
    traslado: la mercancía queda en tránsito hasta que el destino la recibe
    (ver `wms_traslados`), y no aparece disponible en el destino antes de llegar."""
    if data.ubicacion_origen_id == data.ubicacion_destino_id:
        raise HTTPException(422, "El origen y el destino son la misma ubicación.")
    alm_o = await _almacen_de_ubicacion(db, data.ubicacion_origen_id)
    alm_d = await _almacen_de_ubicacion(db, data.ubicacion_destino_id)
    if alm_o and alm_d and alm_o.id != alm_d.id:
        from app.api.v1.endpoints.wms_traslados import LineaTraslado, TrasladoIn, crear_traslado
        t = await crear_traslado(db, current_user, TrasladoIn(
            almacen_origen_id=alm_o.id, almacen_destino_id=alm_d.id, gestion_transporte=data.gestion_transporte,
            notas=data.notas, lineas=[LineaTraslado(
                producto_id=data.producto_id, ubicacion_origen_id=data.ubicacion_origen_id, cantidad=data.cantidad,
                lote_id=data.lote_id, contenedor_id=data.contenedor_id, ubicacion_destino_id=data.ubicacion_destino_id)]))
        await _registrar_evento(
            db, "TRANSFERENCIA",
            f"Traslado {t.numero}: {data.cantidad:g} und en tránsito de {alm_o.nombre} a {alm_d.nombre}"
            + (f" · transporte TMS {t.tms_codigo}" if t.tms_codigo else ""),
            entidad_tipo="TRASLADO", entidad_id=t.id, usuario_id=current_user.id,
            producto_id=data.producto_id, lote_id=data.lote_id, ubicacion_id=t.ubicacion_transito_id,
            datos={"origen_id": data.ubicacion_origen_id, "destino_id": data.ubicacion_destino_id,
                   "cantidad": data.cantidad, "traslado": t.numero})
        await db.commit()
        r2 = await db.execute(
            select(WMSMovimientoInventario).options(selectinload(WMSMovimientoInventario.producto))
            .where(WMSMovimientoInventario.documento_tipo == "TRASLADO", WMSMovimientoInventario.documento_id == t.id)
            .order_by(WMSMovimientoInventario.id).limit(1))
        return r2.scalar_one()
    mov = await _mover(db, tipo="TRANSFERENCIA", producto_id=data.producto_id, cantidad=data.cantidad,
                 lote_id=data.lote_id, origen=data.ubicacion_origen_id, destino=data.ubicacion_destino_id,
                 contenedor_origen=data.contenedor_id, contenedor_destino=None,
                 documento_tipo="TRASLADO", usuario_id=current_user.id, notas=data.notas)

    referencia = "TRANSFERENCIA"
    notas = data.notas
    tms_codigo: Optional[str] = None

    # Gestión de transporte por TMS: crea un viaje de traslado entre almacenes.
    if (data.gestion_transporte or "").upper() == "TMS":
        alm_ori = await _almacen_de_ubicacion(db, data.ubicacion_origen_id)
        alm_des = await _almacen_de_ubicacion(db, data.ubicacion_destino_id)
        tms_codigo = await _next_numero(db, TMSViaje, TMSViaje.codigo, "TRAS")
        prod = await db.get(WMSProducto, data.producto_id)
        # Datos logísticos derivados del producto y la cantidad trasladada
        peso = round((prod.peso_kg or 0) * data.cantidad, 2) if prod else None
        volumen = round((prod.volumen_m3 or 0) * data.cantidad, 3) if prod else None
        # Servicio urbano si es dentro de la misma ciudad; nacional si es intermunicipal
        misma_ciudad = bool(alm_ori and alm_des and alm_ori.ciudad and alm_ori.ciudad == alm_des.ciudad)
        tipo_serv = TipoServicioTMSEnum.TERRESTRE_URBANO if misma_ciudad else TipoServicioTMSEnum.TERRESTRE_NACIONAL
        viaje = TMSViaje(
            codigo=tms_codigo,
            tipo_servicio=tipo_serv,
            estado=EstadoViajeTMSEnum.PROGRAMADO,
            origen_ciudad=(alm_ori.ciudad if alm_ori else None),
            origen_direccion=(f"{alm_ori.nombre} — {alm_ori.direccion or ''}".strip(" —") if alm_ori else None),
            destino_ciudad=(alm_des.ciudad if alm_des else None),
            destino_direccion=(f"{alm_des.nombre} — {alm_des.direccion or ''}".strip(" —") if alm_des else None),
            peso_kg=peso or None,
            volumen_m3=volumen or None,
            num_entregas=1,
            fecha_programada_cargue=datetime.now(timezone.utc),
            descripcion_carga=data.descripcion_carga or (f"Traslado de {data.cantidad:g} x {prod.nombre}" if prod else f"Traslado de {data.cantidad:g} unidades"),
            notas=f"Generado desde WMS · traslado entre almacenes. {data.notas or ''}".strip(),
            creado_por_id=current_user.id,
        )
        db.add(viaje)
        referencia = f"TRASLADO/TMS:{tms_codigo}"
        notas = f"{notas or ''} | Transporte gestionado por TMS ({tms_codigo})".strip(" |")

    # El movimiento ya quedó en el kárdex; se le completa la referencia del traslado.
    mov.referencia_documento, mov.notas = referencia, notas
    # Evento de trazabilidad (ISO 9001 §8.5.2): la transferencia queda en el
    # historial del producto, del lote y de ambas ubicaciones.
    await _registrar_evento(
        db, "TRANSFERENCIA",
        f"Transferencia de {data.cantidad:g} und · ubicación {data.ubicacion_origen_id} → {data.ubicacion_destino_id}"
        + (f" · transporte TMS {tms_codigo}" if tms_codigo else ""),
        entidad_tipo="MOVIMIENTO", usuario_id=current_user.id,
        producto_id=data.producto_id, lote_id=data.lote_id,
        ubicacion_id=data.ubicacion_destino_id,
        datos={"origen_id": data.ubicacion_origen_id, "destino_id": data.ubicacion_destino_id,
               "cantidad": data.cantidad, "referencia": referencia},
    )
    await db.commit()
    r2 = await db.execute(
        select(WMSMovimientoInventario)
        .options(selectinload(WMSMovimientoInventario.producto))
        .where(WMSMovimientoInventario.id == mov.id)
    )
    return r2.scalar_one()


@router.post("/inventario/reserva-bloqueo/", response_model=WMSInventarioResponse)
async def reservar_bloquear_inventario(
    data: WMSReservaBloqueo,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Reserva / libera / bloquea / desbloquea stock de una ubicación.
    Mueve cantidades entre disponible ↔ reservada ↔ bloqueada sin cambiar el total.
    """
    accion = (data.accion or "").upper()
    if accion not in ("RESERVAR", "LIBERAR", "BLOQUEAR", "DESBLOQUEAR"):
        raise HTTPException(400, "Acción inválida (RESERVAR/LIBERAR/BLOQUEAR/DESBLOQUEAR)")

    # Reservar o bloquear es un movimiento entre estados de la misma fila: queda en el kárdex.
    de, a, tipo = {"RESERVAR": ("DISPONIBLE", "RESERVADO", "RESERVA"),
                   "LIBERAR": ("RESERVADO", "DISPONIBLE", "LIBERACION"),
                   "BLOQUEAR": ("DISPONIBLE", "BLOQUEADO", "BLOQUEO"),
                   "DESBLOQUEAR": ("BLOQUEADO", "DISPONIBLE", "DESBLOQUEO")}[accion]
    c = data.cantidad
    await _mover(db, tipo=tipo, producto_id=data.producto_id, cantidad=c, lote_id=data.lote_id,
                 origen=data.ubicacion_id, destino=data.ubicacion_id, estado_origen=de, estado_destino=a,
                 contenedor_origen=data.contenedor_id, documento_tipo="MANUAL", usuario_id=current_user.id,
                 notas=data.motivo)
    inv = await wms_inventario.fila(db, data.producto_id, data.ubicacion_id, data.lote_id, data.contenedor_id)

    await _registrar_evento(
        db, f"INV_{accion}",
        f"{accion} {c:g} unidades del producto {data.producto_id}" + (f" — {data.motivo}" if data.motivo else ""),
        entidad_tipo="WMSInventarioUbicacion", entidad_id=inv.id,
        usuario_id=current_user.id,
        producto_id=data.producto_id, lote_id=data.lote_id, ubicacion_id=data.ubicacion_id,
    )
    await db.commit()
    r2 = await db.execute(
        select(WMSInventarioUbicacion)
        .options(
            selectinload(WMSInventarioUbicacion.producto),
            selectinload(WMSInventarioUbicacion.ubicacion),
            selectinload(WMSInventarioUbicacion.lote),
        )
        .where(WMSInventarioUbicacion.id == inv.id)
    )
    return r2.scalar_one()


async def _listar_movimientos(db: AsyncSession, tipo: str, limite: int = 100):
    r = await db.execute(
        select(WMSMovimientoInventario)
        .options(selectinload(WMSMovimientoInventario.producto))
        .where(WMSMovimientoInventario.tipo == tipo)
        .order_by(WMSMovimientoInventario.id.desc())
        .limit(limite)
    )
    return r.scalars().all()


@router.get("/inventario/movimientos/", response_model=List[WMSMovimientoResponse])
async def listar_movimientos_inventario(
    tipo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(WMSMovimientoInventario)
        .options(selectinload(WMSMovimientoInventario.producto))
        .order_by(WMSMovimientoInventario.id.desc())
        .limit(200)
    )
    if tipo:
        q = q.where(WMSMovimientoInventario.tipo == tipo)
    r = await db.execute(q)
    return r.scalars().all()


@router.get("/inventario/ajustes/", response_model=List[WMSMovimientoResponse])
async def historial_ajustes(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await _listar_movimientos(db, "AJUSTE")


@router.get("/inventario/transferencias/", response_model=List[WMSMovimientoResponse])
async def historial_transferencias(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await _listar_movimientos(db, "TRANSFERENCIA")


# ─── INVENTARIO — Conteos ─────────────────────────────────────────────────────

@router.get("/conteos/", response_model=List[WMSConteoResponse])
async def listar_conteos(
    estado: Optional[str] = None,
    almacen_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(WMSConteoInventario)
        .options(
            selectinload(WMSConteoInventario.almacen),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.producto),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.ubicacion),
        )
    )
    if estado:
        q = q.where(WMSConteoInventario.estado == estado)
    if almacen_id:
        q = q.where(WMSConteoInventario.almacen_id == almacen_id)
    r = await db.execute(q.order_by(WMSConteoInventario.fecha_programada.desc()))
    return r.scalars().all()


@router.post("/conteos/", response_model=WMSConteoResponse, status_code=201)
async def crear_conteo(
    data: WMSConteoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    payload = data.model_dump(exclude={"detalles"})
    conteo = WMSConteoInventario(**payload, operario_id=current_user.id)
    db.add(conteo)
    await db.flush()

    if data.detalles:
        for d in data.detalles:
            # Cargar cantidad_sistema del inventario actual
            inv_stmt = select(WMSInventarioUbicacion).where(
                and_(
                    WMSInventarioUbicacion.producto_id == d.producto_id,
                    WMSInventarioUbicacion.ubicacion_id == d.ubicacion_id,
                    WMSInventarioUbicacion.lote_id == d.lote_id,
                )
            )
            inv_r = await db.execute(inv_stmt.where(WMSInventarioUbicacion.contenedor_id.is_(None)))
            inv = inv_r.scalars().first()
            det = WMSConteoDetalle(
                conteo_id=conteo.id,
                producto_id=d.producto_id,
                ubicacion_id=d.ubicacion_id,
                lote_id=d.lote_id,
                # Lo que hay físicamente: disponible, reservado y bloqueado están
                # en el estante. Comparar solo el disponible daba sobrantes falsos.
                cantidad_sistema=wms_inventario.total_fila(inv) if inv else 0,
            )
            db.add(det)
    else:
        # Sin detalles explícitos: tomar una foto del inventario del almacén
        # (todas las ubicaciones con stock) para que el operario capture el físico.
        inv_r = await db.execute(
            select(WMSInventarioUbicacion)
            .join(WMSUbicacion, WMSInventarioUbicacion.ubicacion_id == WMSUbicacion.id)
            .join(WMSZona, WMSUbicacion.zona_id == WMSZona.id)
            .where(WMSZona.almacen_id == conteo.almacen_id)
            .order_by(WMSInventarioUbicacion.ubicacion_id.asc())
        )
        for inv in inv_r.scalars().all():
            det = WMSConteoDetalle(
                conteo_id=conteo.id,
                producto_id=inv.producto_id,
                ubicacion_id=inv.ubicacion_id,
                lote_id=inv.lote_id,
                contenedor_id=inv.contenedor_id,
                cantidad_sistema=wms_inventario.total_fila(inv),
            )
            db.add(det)

    await db.commit()
    r = await db.execute(
        select(WMSConteoInventario)
        .options(
            selectinload(WMSConteoInventario.almacen),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.producto),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.ubicacion),
        )
        .where(WMSConteoInventario.id == conteo.id)
    )
    return r.scalar_one()


@router.put("/conteos/{conteo_id}/detalles/{detalle_id}", response_model=WMSConteoResponse)
async def actualizar_detalle_conteo(
    conteo_id: int,
    detalle_id: int,
    data: WMSConteoDetalleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Captura la cantidad física de una línea del conteo (marca el conteo EN_PROCESO)."""
    conteo = await db.get(WMSConteoInventario, conteo_id)
    if not conteo:
        raise HTTPException(404, "Conteo no encontrado")
    if conteo.estado == "COMPLETO":
        raise HTTPException(400, "El conteo ya está completo")
    det = await db.get(WMSConteoDetalle, detalle_id)
    if not det or det.conteo_id != conteo_id:
        raise HTTPException(404, "Detalle de conteo no encontrado")

    if data.cantidad_fisica is not None:
        if data.cantidad_fisica < 0:
            raise HTTPException(400, "La cantidad física no puede ser negativa")
        # El sistema se toma en el momento de contar, no al programar el conteo:
        # lo que entró o salió entre tanto no es una diferencia de inventario.
        f = await wms_inventario.fila(db, det.producto_id, det.ubicacion_id, det.lote_id, det.contenedor_id)
        det.cantidad_sistema = wms_inventario.total_fila(f) if f else 0
        det.cantidad_fisica = data.cantidad_fisica
        det.diferencia = data.cantidad_fisica - det.cantidad_sistema
    if data.ajustado is not None:
        det.ajustado = data.ajustado
    if conteo.estado == "PROGRAMADO":
        conteo.estado = "EN_PROCESO"
        if not conteo.fecha_inicio:
            conteo.fecha_inicio = datetime.utcnow()

    await db.commit()
    r = await db.execute(
        select(WMSConteoInventario)
        .options(
            selectinload(WMSConteoInventario.almacen),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.producto),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.ubicacion),
        )
        .where(WMSConteoInventario.id == conteo_id)
    )
    return r.scalar_one()


@router.put("/conteos/{conteo_id}/completar", response_model=WMSConteoResponse)
async def completar_conteo(
    conteo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Reconcilia el conteo: calcula diferencias y genera ajustes de inventario."""
    r = await db.execute(
        select(WMSConteoInventario)
        .options(
            selectinload(WMSConteoInventario.almacen),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.producto),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.ubicacion),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.lote),
        )
        .where(WMSConteoInventario.id == conteo_id)
    )
    conteo = r.scalar_one_or_none()
    if not conteo:
        raise HTTPException(404, "Conteo no encontrado")
    if conteo.estado == "COMPLETO":
        raise HTTPException(400, "Conteo ya está completo")

    for det in conteo.detalles:
        if det.cantidad_fisica is None:
            continue
        f = await wms_inventario.fila(db, det.producto_id, det.ubicacion_id, det.lote_id, det.contenedor_id)
        det.cantidad_sistema = wms_inventario.total_fila(f) if f else 0
        det.diferencia = det.cantidad_fisica - det.cantidad_sistema
        if abs(det.diferencia) > 1e-9:
            comun = dict(tipo="CONTEO", producto_id=det.producto_id, lote_id=det.lote_id,
                         documento_tipo="CONTEO", documento_id=conteo_id, referencia=f"CONTEO-{conteo_id}",
                         usuario_id=current_user.id, notas="Ajuste por conteo físico")
            if det.diferencia > 0:
                await _mover(db, cantidad=det.diferencia, destino=det.ubicacion_id,
                             contenedor_destino=det.contenedor_id, **comun)
            else:
                # El faltante sale primero de lo disponible, luego de lo bloqueado y
                # por último de lo reservado (eso deja corta una orden: se avisa).
                falta = -det.diferencia
                for estado in ("DISPONIBLE", "BLOQUEADO", "RESERVADO"):
                    hay = getattr(f, wms_inventario.ESTADOS[estado]) or 0
                    tomar = min(hay, falta)
                    if tomar > 0:
                        await _mover(db, cantidad=tomar, origen=det.ubicacion_id, estado_origen=estado,
                                     contenedor_origen=det.contenedor_id, **comun)
                        falta -= tomar
                        if estado == "RESERVADO":
                            await _registrar_evento(
                                db, "ALERTA_RESERVA", f"El faltante del conteo #{conteo_id} tocó mercancía "
                                f"reservada ({tomar:g} und): revise las órdenes en alistamiento.",
                                entidad_tipo="CONTEO", entidad_id=conteo_id, usuario_id=current_user.id,
                                producto_id=det.producto_id, lote_id=det.lote_id, ubicacion_id=det.ubicacion_id)
            await _registrar_evento(
                db, "AJUSTE",
                f"Ajuste por conteo físico #{conteo_id}: {'+' if det.diferencia > 0 else ''}{det.diferencia:g} und "
                f"({det.producto.nombre if det.producto else det.producto_id})",
                entidad_tipo="CONTEO", entidad_id=conteo_id, usuario_id=current_user.id,
                producto_id=det.producto_id, lote_id=det.lote_id, ubicacion_id=det.ubicacion_id,
                datos={"sistema": det.cantidad_sistema, "fisica": det.cantidad_fisica,
                       "diferencia": det.diferencia},
            )
        det.ajustado = True

    conteo.estado = "COMPLETO"
    conteo.fecha_fin = datetime.utcnow()
    await db.flush()
    ajustes = (await db.execute(select(WMSMovimientoInventario).where(
        WMSMovimientoInventario.documento_tipo == "CONTEO",
        WMSMovimientoInventario.documento_id == conteo_id))).scalars().all()
    await wms_contable.contabilizar_ajuste(db, list(ajustes), current_user.username,
                                           f"Conteo físico #{conteo_id}", "CONTEO", conteo_id)
    await db.commit()

    r2 = await db.execute(
        select(WMSConteoInventario)
        .options(
            selectinload(WMSConteoInventario.almacen),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.producto),
            selectinload(WMSConteoInventario.detalles).selectinload(WMSConteoDetalle.ubicacion),
        )
        .where(WMSConteoInventario.id == conteo_id)
    )
    return r2.scalar_one()


# ─── OUTBOUND — Órdenes de Salida ─────────────────────────────────────────────

@router.get("/ordenes-salida/", response_model=List[WMSOrdenSalidaResponse])
async def listar_ordenes_salida(
    respuesta: Response,
    estado: Optional[str] = Query(
        None, description="Uno o varios separados por coma: EN_PICKING,EMPACANDO"),
    prioridad: Optional[str] = None,
    cliente_id: Optional[int] = None,
    almacen_id: Optional[int] = None,
    limite: int = Query(200, ge=1, le=1000),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Las órdenes de salida, paginadas.

    Sin tope, este endpoint devolvía TODAS las órdenes con todas sus líneas y el
    producto de cada línea. Con un año de operación son 3.258 órdenes, casi diez
    mil líneas, 1,2 MB por respuesta y más de dos minutos de espera. Las
    pantallas de alistamiento y de despacho lo llamaban al abrirse.

    `estado` acepta varios separados por coma porque la pantalla de despacho
    filtraba en el navegador —se traía el año entero para quedarse con las
    órdenes en alistamiento— y ese filtro pertenece al servidor.
    """
    q = (
        select(WMSOrdenSalida)
        .options(
            selectinload(WMSOrdenSalida.cliente),
            selectinload(WMSOrdenSalida.almacen),
            selectinload(WMSOrdenSalida.detalles).selectinload(WMSOrdenSalidaDetalle.producto),
        )
        .where(WMSOrdenSalida.deleted_at.is_(None))
    )
    if estado:
        estados = [e.strip() for e in estado.split(",") if e.strip()]
        q = q.where(WMSOrdenSalida.estado.in_(estados))
    if prioridad:
        q = q.where(WMSOrdenSalida.prioridad == prioridad)
    if cliente_id:
        q = q.where(WMSOrdenSalida.cliente_id == cliente_id)
    if almacen_id:
        q = q.where(WMSOrdenSalida.almacen_id == almacen_id)

    total = (await db.execute(
        select(func.count()).select_from(
            q.with_only_columns(WMSOrdenSalida.id).order_by(None).subquery()
        ))).scalar() or 0
    respuesta.headers["X-Total-Count"] = str(total)
    respuesta.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    r = await db.execute(
        q.order_by(WMSOrdenSalida.fecha_emision.desc(), WMSOrdenSalida.id.desc())
        .offset(desplazamiento).limit(limite))
    return r.scalars().all()


@router.post("/ordenes-salida/", response_model=WMSOrdenSalidaResponse, status_code=201)
async def crear_orden_salida(
    data: WMSOrdenSalidaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    payload = data.model_dump(exclude={"detalles"})
    if not payload.get("numero_orden"):
        payload["numero_orden"] = await _next_numero(db, WMSOrdenSalida, WMSOrdenSalida.numero_orden, "OS")
    if not payload.get("fecha_emision"):
        payload["fecha_emision"] = date.today()
    payload["depositante_id"] = await op.resolver_depositante(
        db, payload.get("depositante_id"), [d.producto_id for d in data.detalles])
    orden = WMSOrdenSalida(**payload)
    db.add(orden)
    await db.flush()
    for d in data.detalles:
        det = WMSOrdenSalidaDetalle(orden_id=orden.id, **d.model_dump())
        db.add(det)
    await db.commit()
    r = await db.execute(
        select(WMSOrdenSalida)
        .options(
            selectinload(WMSOrdenSalida.cliente),
            selectinload(WMSOrdenSalida.almacen),
            selectinload(WMSOrdenSalida.detalles).selectinload(WMSOrdenSalidaDetalle.producto),
        )
        .where(WMSOrdenSalida.id == orden.id)
    )
    return r.scalar_one()


@router.put("/ordenes-salida/{orden_id}/estado", response_model=WMSOrdenSalidaResponse)
async def actualizar_estado_orden_salida(
    orden_id: int,
    data: WMSOrdenSalidaEstado,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSOrdenSalida, orden_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Orden de salida no encontrada")
    obj.estado = data.estado
    await db.commit()
    r = await db.execute(
        select(WMSOrdenSalida)
        .options(
            selectinload(WMSOrdenSalida.cliente),
            selectinload(WMSOrdenSalida.almacen),
            selectinload(WMSOrdenSalida.detalles).selectinload(WMSOrdenSalidaDetalle.producto),
        )
        .where(WMSOrdenSalida.id == orden_id)
    )
    return r.scalar_one()


async def crear_alistamiento(db: AsyncSession, orden_id: int, tipo: str, dias_vida_minima: int,
                             dias_alerta_vencimiento: int, usuario_id: int, ola_id: Optional[int] = None) -> WMSPickingTarea:
    """Genera la tarea de alistamiento de una orden (FEFO, reservando). La
    usan el endpoint de una orden y las olas."""
    r = await db.execute(
        select(WMSOrdenSalida)
        .options(
            selectinload(WMSOrdenSalida.detalles).selectinload(WMSOrdenSalidaDetalle.producto),
        )
        .where(WMSOrdenSalida.id == orden_id, WMSOrdenSalida.deleted_at.is_(None))
    )
    orden = r.scalar_one_or_none()
    if not orden:
        raise HTTPException(404, "Orden de salida no encontrada")
    if orden.estado not in ("PENDIENTE", "EN_PICKING"):
        raise HTTPException(400, f"Estado {orden.estado} no permite generar picking")

    tarea = WMSPickingTarea(
        orden_id=orden_id,
        ola_id=ola_id,
        operario_id=usuario_id,
        tipo=tipo,
        estado="PENDIENTE",
        fecha_asignacion=datetime.utcnow(),
    )
    db.add(tarea)
    await db.flush()

    hoy = date.today()
    fecha_min_venc = hoy + timedelta(days=dias_vida_minima)   # el lote debe vencer DESPUÉS de esta fecha
    fecha_alerta   = hoy + timedelta(days=dias_alerta_vencimiento)

    faltantes: list[str] = []
    por_vencer: list[str] = []
    for det in orden.detalles:
        cantidad_pendiente = det.cantidad_solicitada - det.cantidad_preparada
        if cantidad_pendiente <= 0:
            continue

        # FEFO en las zonas alistables del almacén de la orden: nunca de
        # recepción, cuarentena ni despacho (antes se podía alistar mercancía
        # que todavía no estaba ubicada o que estaba en cuarentena), sin lotes
        # vencidos, bloqueados ni con menos vida útil que la exigida.
        # Si lo pedido son cajas completas, salen cajas completas de cada ubicación.
        asignaciones = await wms_inventario.asignar_por_empaque(
            db, det.producto_id, orden.almacen_id, cantidad_pendiente,
            lote_id=det.lote_id, dias_vida_minima=dias_vida_minima)
        preparado = 0.0
        for a in asignaciones:
            tomar = float(a.cantidad)
            await _mover(db, tipo="RESERVA", producto_id=det.producto_id, cantidad=tomar, lote_id=a.lote_id,
                         origen=a.ubicacion_id, destino=a.ubicacion_id, estado_origen="DISPONIBLE",
                         estado_destino="RESERVADO", contenedor_origen=a.contenedor_id,
                         documento_tipo="ORDEN_SALIDA", documento_id=orden.id, referencia=orden.numero_orden,
                         usuario_id=usuario_id, notas=f"Reserva para alistamiento (tarea {tarea.id})")
            cantidad_pendiente -= tomar
            preparado += tomar
            db.add(WMSPickingDetalle(tarea_id=tarea.id, producto_id=det.producto_id, ubicacion_id=a.ubicacion_id,
                                     lote_id=a.lote_id, contenedor_id=a.contenedor_id, cantidad_solicitada=tomar))
            if a.vence and a.vence <= fecha_alerta:
                lote = await db.get(WMSLote, a.lote_id)
                por_vencer.append(f"{lote.numero_lote if lote else a.lote_id} (vence en {(a.vence - hoy).days}d, {tomar:g} und)")

        # Reflejar avance de reserva en la línea de la orden
        det.cantidad_preparada = (det.cantidad_preparada or 0) + preparado
        if cantidad_pendiente > 0:
            faltantes.append(f"producto {det.producto_id}: faltan {cantidad_pendiente:g}")

    orden.estado = "EN_PICKING"
    if faltantes:
        await _registrar_evento(
            db, "PICKING_PARCIAL",
            "Picking parcial por stock elegible insuficiente (FEFO, sin vencidos/bloqueados): "
            + "; ".join(faltantes),
            entidad_tipo="WMSOrdenSalida", entidad_id=orden_id,
            usuario_id=usuario_id,
        )
    if por_vencer:
        await _registrar_evento(
            db, "ALERTA_VENCIMIENTO",
            "Lotes próximos a vencer asignados en picking: " + "; ".join(por_vencer),
            entidad_tipo="WMSOrdenSalida", entidad_id=orden_id,
            usuario_id=usuario_id,
        )
    return tarea


@router.post("/ordenes-salida/{orden_id}/generar-picking", response_model=WMSPickingTareaResponse, status_code=201)
async def generar_picking(
    orden_id: int,
    tipo: str = Query("SINGLE"),
    dias_vida_minima: int = Query(0, ge=0, description="Vida útil mínima (días) exigida al momento del despacho"),
    dias_alerta_vencimiento: int = Query(30, ge=0, description="Umbral para marcar lotes próximos a vencer"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Auto-genera una tarea de picking a partir del inventario disponible aplicando
    FEFO (First-Expired, First-Out): asigna primero los lotes que vencen antes.

    Control ISO 9001 §8.5.4 (preservación) / §8.7 (no conforme): NO se asignan
    lotes vencidos, lotes bloqueados (activo=False) ni lotes cuya vida útil
    remanente sea menor a `dias_vida_minima`. Los lotes próximos a vencer
    (dentro de `dias_alerta_vencimiento`) se asignan pero se registra alerta.
    """
    tarea = await crear_alistamiento(db, orden_id, tipo, dias_vida_minima, dias_alerta_vencimiento, current_user.id)
    await db.commit()

    r2 = await db.execute(
        select(WMSPickingTarea)
        .options(
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.producto),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.ubicacion),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.lote),
        )
        .where(WMSPickingTarea.id == tarea.id)
    )
    return r2.scalar_one()


# ─── OUTBOUND — Picking ───────────────────────────────────────────────────────

@router.get("/picking-tareas/", response_model=List[WMSPickingTareaResponse])
async def listar_picking_tareas(
    respuesta: Response,
    estado: Optional[str] = None,
    orden_id: Optional[int] = None,
    limite: int = Query(200, ge=1, le=1000),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Las tareas de alistamiento.

    Va paginado: sin tope devolvía la operación completa. Un año de bodega son
    miles de filas, y la pantalla que lo llama solo muestra las primeras. El
    total va en la cabecera `X-Total-Count` para no cambiarle la forma a la
    respuesta, que ya está publicada como una lista.
    """
    q = (
        select(WMSPickingTarea)
        .options(
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.producto),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.ubicacion),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.lote),
        )
    )
    if estado:
        q = q.where(WMSPickingTarea.estado == estado)
    if orden_id:
        q = q.where(WMSPickingTarea.orden_id == orden_id)
    total = (await db.execute(
        select(func.count()).select_from(
            q.with_only_columns(WMSPickingTarea.id).order_by(None).subquery()
        ))).scalar() or 0
    respuesta.headers["X-Total-Count"] = str(total)
    respuesta.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    r = await db.execute(
        q.order_by(WMSPickingTarea.id.desc()).offset(desplazamiento).limit(limite))
    return r.scalars().all()


@router.post("/picking-tareas/", response_model=WMSPickingTareaResponse, status_code=201)
async def crear_picking_tarea(
    data: WMSPickingTareaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    tarea = WMSPickingTarea(
        orden_id=data.orden_id,
        operario_id=current_user.id,
        tipo=data.tipo,
        estado="PENDIENTE",
        fecha_asignacion=datetime.utcnow(),
    )
    db.add(tarea)
    await db.flush()
    for d in data.detalles:
        det = WMSPickingDetalle(tarea_id=tarea.id, **d.model_dump())
        db.add(det)
    await db.commit()
    r = await db.execute(
        select(WMSPickingTarea)
        .options(
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.producto),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.ubicacion),
        )
        .where(WMSPickingTarea.id == tarea.id)
    )
    return r.scalar_one()


@router.put("/picking-tareas/{tarea_id}", response_model=WMSPickingTareaResponse)
async def actualizar_picking_tarea(
    tarea_id: int,
    data: WMSPickingTareaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    obj = await db.get(WMSPickingTarea, tarea_id)
    if not obj:
        raise HTTPException(404, "Tarea de picking no encontrada")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    if data.estado == "EN_PROGRESO" and not obj.fecha_inicio:
        obj.fecha_inicio = datetime.utcnow()
    await db.commit()
    r = await db.execute(
        select(WMSPickingTarea)
        .options(
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.producto),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.ubicacion),
        )
        .where(WMSPickingTarea.id == tarea_id)
    )
    return r.scalar_one()


async def confirmar_linea(db: AsyncSession, tarea: WMSPickingTarea, det: WMSPickingDetalle, cantidad: float,
                          usuario_id: int, ubicacion_codigo: Optional[str] = None,
                          producto_codigo: Optional[str] = None, permitir_cero: bool = False) -> None:
    """Confirma una línea de alistamiento (con verificación por escaneo si
    viene). La usan el endpoint de una tarea y las olas."""
    # En una ola, un faltante puede dejar una línea en cero: se confirma vacía
    # y todo lo reservado vuelve a disponible.
    if cantidad < 0 or (cantidad == 0 and not permitir_cero) or cantidad > det.cantidad_solicitada:
        raise HTTPException(
            400,
            f"La cantidad pickeada debe estar entre 0 y {det.cantidad_solicitada:g}",
        )

    # Verificación por escaneo: si el operario escaneó, tiene que ser la
    # ubicación y el producto de la línea. Así se detecta en el acto el error
    # de alistamiento, en vez de que lo descubra el cliente.
    if ubicacion_codigo:
        ub = await db.get(WMSUbicacion, det.ubicacion_id)
        if ub and ubicacion_codigo.strip().upper() != ub.codigo.upper():
            raise HTTPException(422, f"Ubicación equivocada: escaneó {ubicacion_codigo}, la línea es de {ub.codigo}.")
    if producto_codigo:
        pr = await db.get(WMSProducto, det.producto_id)
        # También valen los códigos de sus empaques (caja, máster, estiba).
        from app.infrastructure.models.wms import WMSProductoEmpaque
        empaques = (await db.execute(select(WMSProductoEmpaque.codigo_barras).where(
            WMSProductoEmpaque.producto_id == pr.id))).scalars().all()
        validos = {c.upper() for c in (pr.sku, pr.codigo_barras, *empaques) if c}
        if producto_codigo.strip().upper() not in validos:
            raise HTTPException(422, f"Producto equivocado: escaneó {producto_codigo}, la línea es {pr.sku}.")

    ahora = datetime.now(timezone.utc)
    if tarea.fecha_inicio is None:
        tarea.fecha_inicio = ahora
        tarea.estado = "EN_PROGRESO"
    det.cantidad_pickeada = cantidad
    det.confirmado = True
    det.timestamp_confirmacion = ahora


    # Si se alista menos de lo reservado, el sobrante vuelve a estar disponible.
    sobrante = det.cantidad_solicitada - cantidad
    if sobrante > 0:
        await _mover(db, tipo="LIBERACION", producto_id=det.producto_id, cantidad=sobrante, lote_id=det.lote_id,
                     origen=det.ubicacion_id, destino=det.ubicacion_id, estado_origen="RESERVADO",
                     estado_destino="DISPONIBLE", contenedor_origen=det.contenedor_id,
                     documento_tipo="PICKING", documento_id=tarea.id, usuario_id=usuario_id,
                     notas="Alistado menos de lo reservado")
    await _registrar_evento(
        db, "PICKING_CONFIRMADO",
        f"Alistadas {cantidad:g} de {det.cantidad_solicitada:g} und (tarea {tarea.id})",
        entidad_tipo="PICKING", entidad_id=tarea.id, usuario_id=usuario_id,
        producto_id=det.producto_id, lote_id=det.lote_id, ubicacion_id=det.ubicacion_id,
        datos={"verificado": bool(ubicacion_codigo or producto_codigo), "sobrante": sobrante})

    # Lo alistado pasa al staging de salida del almacén: el inventario muestra
    # dónde está físicamente mientras espera el despacho. Sigue reservado para
    # la orden, y el despacho lo saca de allí (por eso `ubicacion_id` cambia).
    if cantidad > 0:
        orden_st = await db.get(WMSOrdenSalida, tarea.orden_id)
        staging = await wms_inventario.ubicacion_staging(db, orden_st.almacen_id) if orden_st else None
        if staging and staging != det.ubicacion_id:
            await _mover(db, tipo="STAGING", producto_id=det.producto_id, cantidad=cantidad, lote_id=det.lote_id,
                         origen=det.ubicacion_id, destino=staging, estado_origen="RESERVADO",
                         estado_destino="RESERVADO", contenedor_origen=det.contenedor_id, contenedor_destino=None,
                         documento_tipo="PICKING", documento_id=tarea.id, usuario_id=usuario_id,
                         notas="Alistado: pasa al staging de salida")
            det.ubicacion_alistada_id = det.ubicacion_id
            det.ubicacion_id = staging
            det.contenedor_id = None

    tarea.items_pickeados = (tarea.items_pickeados or 0) + 1

    # Verificar si todos los ítems están confirmados
    todos_r = await db.execute(
        select(WMSPickingDetalle).where(WMSPickingDetalle.tarea_id == tarea.id)
    )
    todos = todos_r.scalars().all()
    tarea.ubicaciones_visitadas = len({d.ubicacion_id for d in todos if d.confirmado})
    if all(d.confirmado for d in todos):
        tarea.estado = "COMPLETADA"
        tarea.fecha_fin = ahora



@router.post("/picking-tareas/{tarea_id}/confirmar-item", response_model=WMSPickingTareaResponse)
async def confirmar_item_picking(
    tarea_id: int,
    data: WMSPickingConfirmItem,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Confirma el picking de un ítem específico (simula escaneo)."""
    tarea = await db.get(WMSPickingTarea, tarea_id)
    if not tarea:
        raise HTTPException(404, "Tarea de picking no encontrada")
    det = await db.get(WMSPickingDetalle, data.detalle_id)
    if not det or det.tarea_id != tarea_id:
        raise HTTPException(404, "Detalle de picking no encontrado")
    if det.confirmado:
        raise HTTPException(400, "Ítem ya confirmado")
    await confirmar_linea(db, tarea, det, data.cantidad_pickeada, current_user.id,
                          data.ubicacion_codigo, data.producto_codigo)

    await db.commit()
    r = await db.execute(
        select(WMSPickingTarea)
        .options(
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.producto),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.ubicacion),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.lote),
        )
        .where(WMSPickingTarea.id == tarea_id)
    )
    return r.scalar_one()


class _LineaLote(BaseModel):
    detalle_id: int
    cantidad: float = Field(ge=0)
    producto_codigo: Optional[str] = None
    ubicacion_codigo: Optional[str] = None


class _ConfirmarLote(BaseModel):
    lineas: List[_LineaLote] = Field(min_length=1)


@router.post("/picking-tareas/{tarea_id}/confirmar-lote", response_model=WMSPickingTareaResponse)
async def confirmar_lote_picking(
    tarea_id: int,
    data: _ConfirmarLote,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Confirma varias líneas de una vez (pantalla de ejecución de la tarea).

    Todo o nada: si una línea falla (código equivocado, cantidad fuera de
    rango), no se confirma ninguna. Una línea en 0 es «no había»: lo reservado
    vuelve a quedar disponible."""
    tarea = await db.get(WMSPickingTarea, tarea_id)
    if not tarea:
        raise HTTPException(404, "Tarea de picking no encontrada")
    for ln in data.lineas:
        det = await db.get(WMSPickingDetalle, ln.detalle_id)
        if not det or det.tarea_id != tarea_id:
            raise HTTPException(404, f"La línea {ln.detalle_id} no es de esta tarea")
        if det.confirmado:
            continue
        await confirmar_linea(db, tarea, det, ln.cantidad, current_user.id,
                              ln.ubicacion_codigo, ln.producto_codigo, permitir_cero=True)
    await db.commit()
    r = await db.execute(
        select(WMSPickingTarea)
        .options(
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.producto),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.ubicacion),
            selectinload(WMSPickingTarea.detalles).selectinload(WMSPickingDetalle.lote),
        )
        .where(WMSPickingTarea.id == tarea_id)
    )
    return r.scalar_one()


# ─── OUTBOUND — Despachos ─────────────────────────────────────────────────────

@router.get("/despachos/", response_model=List[WMSDespachoResponse])
async def listar_despachos(
    respuesta: Response,
    estado: Optional[str] = None,
    orden_id: Optional[int] = None,
    limite: int = Query(200, ge=1, le=1000),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los despachos.

    Va paginado: sin tope devolvía la operación completa. Un año de bodega son
    miles de filas, y la pantalla que lo llama solo muestra las primeras. El
    total va en la cabecera `X-Total-Count` para no cambiarle la forma a la
    respuesta, que ya está publicada como una lista.
    """
    q = (
        select(WMSDespacho)
        .options(
            selectinload(WMSDespacho.transportadora),
            selectinload(WMSDespacho.detalles).selectinload(WMSDespachoDetalle.producto),
            selectinload(WMSDespacho.detalles).selectinload(WMSDespachoDetalle.lote),
        )
        .where(WMSDespacho.deleted_at.is_(None))
    )
    if estado:
        q = q.where(WMSDespacho.estado == estado)
    if orden_id:
        q = q.where(WMSDespacho.orden_id == orden_id)
    total = (await db.execute(
        select(func.count()).select_from(
            q.with_only_columns(WMSDespacho.id).order_by(None).subquery()
        ))).scalar() or 0
    respuesta.headers["X-Total-Count"] = str(total)
    respuesta.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    r = await db.execute(
        q.order_by(WMSDespacho.fecha_despacho.desc()).offset(desplazamiento).limit(limite))
    return await _con_factura(db, r.scalars().all())


async def _con_factura(db: AsyncSession, despachos):
    """Le pone a cada despacho el número de su factura del ERP."""
    from app.infrastructure.models.erp import ERPFacturaCliente
    ids = [d.factura_id for d in despachos if d.factura_id]
    numeros = dict((await db.execute(select(ERPFacturaCliente.id, ERPFacturaCliente.numero).where(
        ERPFacturaCliente.id.in_(ids)))).all()) if ids else {}
    for d in despachos:
        d.factura_numero = numeros.get(d.factura_id)
    return despachos


@router.post("/despachos/{despacho_id}/facturar", response_model=WMSDespachoResponse)
async def facturar_despacho(despacho_id: int, data: WMSFacturarDespacho, db: AsyncSession = Depends(get_db),
                            current_user: Usuario = Depends(require_supervisor)):
    """Factura un despacho que no se pudo facturar al salir (orden sin precio,
    cliente sin NIT, sin resolución vigente)."""
    d = (await db.execute(select(WMSDespacho).where(WMSDespacho.id == despacho_id).with_for_update())).scalar_one_or_none()
    if d is None:
        raise HTTPException(404, "Despacho no encontrado")
    await wms_contable.facturar_despacho(db, d, current_user.username, data.precios or None)
    await db.commit()
    r = await db.execute(select(WMSDespacho).options(
        selectinload(WMSDespacho.transportadora),
        selectinload(WMSDespacho.detalles).selectinload(WMSDespachoDetalle.producto),
        selectinload(WMSDespacho.detalles).selectinload(WMSDespachoDetalle.lote),
    ).where(WMSDespacho.id == despacho_id))
    return (await _con_factura(db, [r.scalar_one()]))[0]


@router.post("/despachos/", response_model=WMSDespachoResponse, status_code=201)
async def crear_despacho(
    data: WMSDespachoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Cargar la orden (con detalles) para validar/descontar contra su almacén.
    orden_r = await db.execute(
        select(WMSOrdenSalida)
        .options(selectinload(WMSOrdenSalida.detalles))
        .where(WMSOrdenSalida.id == data.orden_id, WMSOrdenSalida.deleted_at.is_(None))
    )
    orden = orden_r.scalar_one_or_none()
    if not orden:
        raise HTTPException(404, "Orden de salida no encontrada")

    # Determinar las líneas a despachar: las provistas o, si no vienen, las
    # confirmadas en el picking de la orden.
    # Lo alistado de ESTA orden que todavía no ha salido: es lo único que el
    # despacho puede consumir. Antes descontaba cualquier reserva del producto en
    # el almacén, aunque fuera de otra orden.
    alistado = (await db.execute(
        select(WMSPickingDetalle)
        .join(WMSPickingTarea, WMSPickingDetalle.tarea_id == WMSPickingTarea.id)
        .where(WMSPickingTarea.orden_id == orden.id, WMSPickingDetalle.confirmado == True,
               WMSPickingDetalle.cantidad_pickeada > WMSPickingDetalle.cantidad_despachada)
        .order_by(WMSPickingDetalle.id)
        .with_for_update(of=WMSPickingDetalle))).scalars().all()
    lineas = list(data.detalles)
    if not lineas:
        agrupado: dict = {}
        for pd in alistado:
            k = (pd.producto_id, pd.lote_id)
            agrupado[k] = agrupado.get(k, 0) + (pd.cantidad_pickeada - (pd.cantidad_despachada or 0))
        lineas = [WMSDespachoDetalleCreate(producto_id=p_, lote_id=l_, cantidad=c_)
                  for (p_, l_), c_ in agrupado.items() if c_ > 0]
    if not lineas:
        raise HTTPException(400, "No hay ítems para despachar (sin detalles ni picking confirmado)")

    # `gestion_transporte` no es columna: decide más abajo si se crea el viaje en TMS.
    payload = data.model_dump(exclude={"detalles", "gestion_transporte", "tms_vehiculo_id"})
    if not payload.get("numero_despacho"):
        payload["numero_despacho"] = await _next_numero(db, WMSDespacho, WMSDespacho.numero_despacho, "DESP")
    if not payload.get("fecha_despacho"):
        payload["fecha_despacho"] = date.today()
    # Peso y volumen: los de los bultos empacados, si no se escriben a mano.
    if payload.get("peso_total_kg") is None or payload.get("volumen_total_m3") is None:
        from app.infrastructure.models.wms import WMSEmpaqueOrden
        from app.core.wms_cubicaje import volumen_m3
        bultos = (await db.execute(select(WMSEmpaqueOrden).where(WMSEmpaqueOrden.orden_id == orden.id))).scalars().all()
        if bultos:
            if payload.get("peso_total_kg") is None and all(b.peso_kg is not None for b in bultos):
                payload["peso_total_kg"] = round(sum(b.peso_kg for b in bultos), 3)
            if payload.get("volumen_total_m3") is None:
                payload["volumen_total_m3"] = round(sum(volumen_m3(b.largo_cm, b.ancho_cm, b.alto_cm) or 0 for b in bultos), 4)
    # Sin bultos empacados: peso y volumen estimados con los empaques del
    # maestro (solo si todos los productos tienen el dato; a medias engañaría).
    from app.core import tms_capacidad
    if payload.get("peso_total_kg") is None or payload.get("volumen_total_m3") is None:
        est = await tms_capacidad.estimar_carga(db, [(d.producto_id, d.cantidad) for d in lineas])
        if payload.get("peso_total_kg") is None and est["peso_kg"] and not est["sin_peso"]:
            payload["peso_total_kg"] = est["peso_kg"]
        if payload.get("volumen_total_m3") is None and est["volumen_m3"] and not est["sin_volumen"]:
            payload["volumen_total_m3"] = est["volumen_m3"]
    # Vehículo del TMS elegido desde el WMS: se verifica que la carga quepa.
    vehiculo_tms = None
    if data.tms_vehiculo_id:
        vehiculo_tms = await db.get(TMSVehiculo, data.tms_vehiculo_id)
        if not vehiculo_tms or vehiculo_tms.deleted_at:
            raise HTTPException(404, "Vehículo no encontrado")
        await tms_capacidad.exigir(db, vehiculo_tms, payload.get("peso_total_kg"), payload.get("volumen_total_m3"))
        payload["vehiculo_placa"] = vehiculo_tms.placa
    despacho = WMSDespacho(**payload)
    db.add(despacho)
    await db.flush()

    for d in lineas:
        det = WMSDespachoDetalle(despacho_id=despacho.id, **d.model_dump())
        db.add(det)

        # Sale de las ubicaciones exactas donde se alistó, en el estado reservado.
        fuentes = [pd for pd in alistado if pd.producto_id == d.producto_id
                   and (d.lote_id is None or pd.lote_id == d.lote_id)]
        hay = sum(pd.cantidad_pickeada - (pd.cantidad_despachada or 0) for pd in fuentes)
        if hay + 1e-9 < d.cantidad:
            raise HTTPException(
                400,
                f"Lo alistado para la orden no alcanza para el producto {d.producto_id} "
                f"(alistado sin despachar {hay:g}, requerido {d.cantidad:g}). "
                "Genere y confirme el alistamiento antes de despachar.",
            )
        pendiente = d.cantidad
        for pd in fuentes:
            if pendiente <= 1e-9:
                break
            tomar = min(pd.cantidad_pickeada - (pd.cantidad_despachada or 0), pendiente)
            if tomar <= 0:
                continue
            await _mover(db, tipo="DESPACHO", producto_id=pd.producto_id, cantidad=tomar, lote_id=pd.lote_id,
                         origen=pd.ubicacion_id, estado_origen="RESERVADO", contenedor_origen=pd.contenedor_id,
                         documento_tipo="DESPACHO", documento_id=despacho.id,
                         referencia=payload["numero_despacho"], usuario_id=current_user.id,
                         notas=f"Orden {orden.numero_orden}")
            pd.cantidad_despachada = (pd.cantidad_despachada or 0) + tomar
            pendiente -= tomar

        # Actualizar cantidad_despachada de la línea de la orden
        for od in orden.detalles:
            # La línea de la orden casi nunca pide un lote: se surte con los que
            # asigne el FEFO. Exigir el mismo lote dejaba sin descontar lo
            # despachado de todo producto con lote, y la orden parecía incompleta.
            if od.producto_id == d.producto_id and (od.lote_id is None or d.lote_id is None or od.lote_id == d.lote_id):
                od.cantidad_despachada = (od.cantidad_despachada or 0) + d.cantidad
                break

    # Derivar estado de la orden: DESPACHADO si todas las líneas quedan cubiertas.
    if orden.detalles and all(
        (od.cantidad_despachada or 0) >= (od.cantidad_solicitada or 0) for od in orden.detalles
    ):
        orden.estado = "DESPACHADO"
    else:
        orden.estado = "EMPACANDO"

    # Gestión de transporte por TMS: crea el viaje del despacho (vinculado).
    if (data.gestion_transporte or "").upper() == "TMS":
        alm = await db.get(WMSAlmacen, orden.almacen_id)
        cli = await db.get(WMSCliente, orden.cliente_id)
        tms_codigo = await _next_numero(db, TMSViaje, TMSViaje.codigo, "DESP")
        fcarga = datetime.combine(despacho.fecha_despacho, datetime.min.time()) if despacho.fecha_despacho else datetime.now(timezone.utc)
        fentrega = datetime.combine(despacho.fecha_entrega_estimada, datetime.min.time()) if despacho.fecha_entrega_estimada else None
        viaje = TMSViaje(
            codigo=tms_codigo,
            tipo_servicio=TipoServicioTMSEnum.DISTRIBUCION,
            estado=EstadoViajeTMSEnum.PROGRAMADO,
            wms_despacho_id=despacho.id,
            vehiculo_id=(vehiculo_tms.id if vehiculo_tms else None),
            origen_ciudad=(alm.ciudad if alm else None),
            origen_direccion=(f"{alm.nombre} — {alm.direccion or ''}".strip(" —") if alm else None),
            destino_ciudad=(cli.ciudad if cli else None),
            destino_direccion=(cli.nombre if cli else None),
            # Los del despacho: si se calcularon desde los bultos, `data` no los trae.
            peso_kg=despacho.peso_total_kg,
            volumen_m3=despacho.volumen_total_m3,
            num_entregas=1,
            fecha_programada_cargue=fcarga,
            fecha_programada_entrega=fentrega,
            descripcion_carga=f"Despacho {payload['numero_despacho']} — orden {orden.numero_orden}",
            notas=f"Generado desde WMS · despacho. Placa {despacho.vehiculo_placa or '-'} · conductor {despacho.conductor_nombre or '-'}",
            creado_por_id=current_user.id,
        )
        db.add(viaje)
        despacho.notas = f"{despacho.notas or ''} | Transporte gestionado por TMS ({tms_codigo})".strip(" |")

    # Evento de trazabilidad por cada línea despachada (ISO 9001 §8.5.2)
    for d in lineas:
        await _registrar_evento(
            db, "DESPACHO",
            f"Despacho {payload['numero_despacho']} · orden {orden.numero_orden} · {d.cantidad:g} und",
            entidad_tipo="DESPACHO", entidad_id=despacho.id, usuario_id=current_user.id,
            producto_id=d.producto_id, lote_id=d.lote_id,
            datos={"numero_despacho": payload["numero_despacho"], "orden": orden.numero_orden,
                   "cantidad": d.cantidad},
        )

    # El costo de lo que salió y la factura de venta (si se puede; si no, queda el aviso).
    await wms_contable.contabilizar_despacho(db, despacho, current_user.username)
    await db.commit()
    r = await db.execute(
        select(WMSDespacho)
        .options(
            selectinload(WMSDespacho.transportadora),
            selectinload(WMSDespacho.detalles).selectinload(WMSDespachoDetalle.producto),
            selectinload(WMSDespacho.detalles).selectinload(WMSDespachoDetalle.lote),
        )
        .where(WMSDespacho.id == despacho.id)
    )
    return (await _con_factura(db, [r.scalar_one()]))[0]


@router.put("/despachos/{despacho_id}/estado", response_model=WMSDespachoResponse)
async def actualizar_estado_despacho(
    despacho_id: int,
    data: WMSDespachoEstado,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    obj = await db.get(WMSDespacho, despacho_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Despacho no encontrado")
    if data.estado not in _DESPACHO_ESTADOS:
        raise HTTPException(400, f"Estado de despacho inválido: {data.estado}")
    estado_anterior = obj.estado
    if data.estado != estado_anterior and data.estado not in _DESPACHO_TRANS_NEXT.get(estado_anterior, set()):
        raise HTTPException(
            400, f"Transición no permitida: {estado_anterior} → {data.estado}"
        )
    obj.estado = data.estado
    if data.fecha_entrega_real:
        obj.fecha_entrega_real = data.fecha_entrega_real
    if data.estado == "ENTREGADO":
        if not obj.fecha_entrega_real:
            obj.fecha_entrega_real = date.today()
        orden = await db.get(WMSOrdenSalida, obj.orden_id)
        if orden:
            orden.estado = "ENTREGADO"
    db.add(WMSHistorialEstado(
        entidad_tipo="DESPACHO",
        entidad_id=despacho_id,
        estado_anterior=estado_anterior,
        estado_nuevo=data.estado,
        tipo_cambio="AVANCE",
        usuario_id=current_user.id,
    ))
    await db.commit()
    r = await db.execute(
        select(WMSDespacho)
        .options(
            selectinload(WMSDespacho.transportadora),
            selectinload(WMSDespacho.detalles).selectinload(WMSDespachoDetalle.producto),
        )
        .where(WMSDespacho.id == despacho_id)
    )
    return r.scalar_one()


@router.get("/despachos/{despacho_id}/historial")
async def historial_despacho(
    despacho_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Retorna el historial completo de cambios de estado del despacho."""
    result = await db.execute(
        select(WMSHistorialEstado)
        .options(selectinload(WMSHistorialEstado.usuario))
        .where(
            WMSHistorialEstado.entidad_tipo == "DESPACHO",
            WMSHistorialEstado.entidad_id == despacho_id,
        )
        .order_by(WMSHistorialEstado.fecha.asc())
    )
    registros = list(result.scalars().all())
    return [
        {
            "id":              r.id,
            "estado_anterior": r.estado_anterior,
            "estado_nuevo":    r.estado_nuevo,
            "tipo_cambio":     r.tipo_cambio,
            "observacion":     r.observacion,
            "usuario":         f"{r.usuario.nombre} {r.usuario.apellido}" if r.usuario else "Sistema",
            "fecha":           r.fecha.isoformat(),
        }
        for r in registros
    ]


@router.post("/despachos/{despacho_id}/estado/revertir")
async def revertir_estado_despacho(
    despacho_id: int,
    data: RevertirDespachoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    """Corrige un estado de despacho registrado por error. Solo SUPERVISOR y ADMIN."""
    if not data.observacion or not data.observacion.strip():
        raise HTTPException(400, "La observación es obligatoria para revertir un estado")

    obj = await db.get(WMSDespacho, despacho_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Despacho no encontrado")

    estado_destino = _REVERT_DESPACHO_TRANS.get(obj.estado)
    if not estado_destino:
        raise HTTPException(400, f"El estado '{obj.estado}' no puede ser revertido")

    estado_anterior = obj.estado
    obj.estado = estado_destino

    if estado_anterior == "ENTREGADO":
        obj.fecha_entrega_real = None
        orden = await db.get(WMSOrdenSalida, obj.orden_id)
        if orden:
            orden.estado = "DESPACHADO"

    db.add(WMSHistorialEstado(
        entidad_tipo="DESPACHO",
        entidad_id=despacho_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_destino,
        tipo_cambio="CORRECCION",
        observacion=data.observacion.strip(),
        usuario_id=current_user.id,
    ))
    await db.commit()
    return {
        "message": "Estado revertido",
        "estado_anterior": estado_anterior,
        "estado": estado_destino,
    }


# ─── DEVOLUCIONES ─────────────────────────────────────────────────────────────

@router.get("/devoluciones/", response_model=List[WMSDevolucionResponse])
async def listar_devoluciones(
    respuesta: Response,
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    almacen_id: Optional[int] = None,
    limite: int = Query(200, ge=1, le=1000),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Las devoluciones.

    Va paginado: sin tope devolvía la operación completa. Un año de bodega son
    miles de filas, y la pantalla que lo llama solo muestra las primeras. El
    total va en la cabecera `X-Total-Count` para no cambiarle la forma a la
    respuesta, que ya está publicada como una lista.
    """
    q = (
        select(WMSDevolucion)
        .options(
            selectinload(WMSDevolucion.almacen),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.producto),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.lote),
        )
    )
    if estado:
        q = q.where(WMSDevolucion.estado == estado)
    if tipo:
        q = q.where(WMSDevolucion.tipo == tipo)
    if almacen_id:
        q = q.where(WMSDevolucion.almacen_id == almacen_id)
    total = (await db.execute(
        select(func.count()).select_from(
            q.with_only_columns(WMSDevolucion.id).order_by(None).subquery()
        ))).scalar() or 0
    respuesta.headers["X-Total-Count"] = str(total)
    respuesta.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    r = await db.execute(
        q.order_by(WMSDevolucion.fecha_recepcion.desc()).offset(desplazamiento).limit(limite))
    return r.scalars().all()


@router.post("/devoluciones/", response_model=WMSDevolucionResponse, status_code=201)
async def crear_devolucion(
    data: WMSDevolucionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    payload = data.model_dump(exclude={"detalles"})
    dev = WMSDevolucion(**payload)
    db.add(dev)
    await db.flush()
    for d in data.detalles:
        det = WMSDevolucionDetalle(devolucion_id=dev.id, **d.model_dump())
        db.add(det)
    await db.commit()
    r = await db.execute(
        select(WMSDevolucion)
        .options(
            selectinload(WMSDevolucion.almacen),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.producto),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.lote),
        )
        .where(WMSDevolucion.id == dev.id)
    )
    return r.scalar_one()


@router.put("/devoluciones/{dev_id}/procesar", response_model=WMSDevolucionResponse)
async def procesar_devolucion(
    dev_id: int,
    data: WMSDevolucionProcesar,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Procesa la devolución: si estado=REINGRESADA, ingresa inventario
    para los ítems con accion=REINGRESAR.
    """
    r = await db.execute(
        select(WMSDevolucion)
        .options(
            selectinload(WMSDevolucion.almacen),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.producto),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.lote),
        )
        .where(WMSDevolucion.id == dev_id)
    )
    dev = r.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Devolución no encontrada")

    dev.estado = data.estado

    if data.estado == "REINGRESADA":
        # Cada línea va a donde dice su acción. Antes todo caía en «la primera
        # ubicación del almacén», aunque la línea dijera cuarentena o destruir.
        alm = await db.get(WMSAlmacen, dev.almacen_id)
        dirigido = alm is not None and (alm.flujo_recepcion or "DIRECTO") == "DIRIGIDO"
        recepcion = await wms_inventario.ubicacion_de_zona(db, dev.almacen_id, "RECEPCION")
        almacenaje = await wms_inventario.ubicacion_de_zona(db, dev.almacen_id, "ALMACENAMIENTO")
        cuarentena = await wms_inventario.ubicacion_de_zona(db, dev.almacen_id, "CUARENTENA")
        doc = dict(documento_tipo="DEVOLUCION", documento_id=dev.id, referencia=dev.numero_devolucion,
                   usuario_id=current_user.id)
        for det in dev.detalles:
            if det.reingresado:
                continue
            nombre = det.producto.nombre if det.producto else det.producto_id
            if det.accion == "REINGRESAR":
                destino = (recepcion if dirigido else almacenaje) or recepcion or almacenaje
                if destino is None:
                    raise HTTPException(422, "El almacén no tiene ubicaciones de recepción ni de almacenamiento.")
                lpn = None
                if dirigido and destino == recepcion:
                    c = await op.crear_contenedor(db, almacen_id=dev.almacen_id, ubicacion_id=destino,
                                                  depositante_id=det.producto.depositante_id if det.producto else None,
                                                  usuario_id=current_user.id, documento_tipo="DEVOLUCION",
                                                  documento_id=dev.id)
                    lpn = c.id
                await _mover(db, tipo="DEVOLUCION", producto_id=det.producto_id, cantidad=det.cantidad,
                             lote_id=det.lote_id, destino=destino, contenedor_destino=lpn,
                             notas="Reingreso por devolución", **doc)
                if lpn:
                    await op.crear_tarea_ubicacion(
                        db, almacen_id=dev.almacen_id, producto_id=det.producto_id, lote_id=det.lote_id,
                        contenedor_id=lpn, cantidad=det.cantidad, origen=destino, sugerida=None, razon=None,
                        depositante_id=det.producto.depositante_id if det.producto else None,
                        documento_tipo="DEVOLUCION", documento_id=dev.id)
                ubic_evento, texto = destino, "Reingreso"
            elif det.accion == "CUARENTENA":
                if cuarentena is None:
                    raise HTTPException(422, "El almacén no tiene zona de CUARENTENA para recibir esta devolución.")
                await _mover(db, tipo="DEVOLUCION", producto_id=det.producto_id, cantidad=det.cantidad,
                             lote_id=det.lote_id, destino=cuarentena, estado_destino="BLOQUEADO",
                             notas=f"Devolución a cuarentena ({det.estado_calidad})", **doc)
                ubic_evento, texto = cuarentena, "A cuarentena (bloqueado)"
            else:
                # DESTRUIR / DEVOLVER_PROVEEDOR: no vuelve al inventario, pero queda constancia.
                ubic_evento, texto = None, ("Para destrucción" if det.accion == "DESTRUIR"
                                            else "Para devolver al proveedor")
            det.reingresado = True
            await _registrar_evento(
                db, "DEVOLUCION",
                f"{texto} — devolución {dev.numero_devolucion}: {det.cantidad:g} und ({nombre})",
                entidad_tipo="DEVOLUCION", entidad_id=dev.id, usuario_id=current_user.id,
                producto_id=det.producto_id, lote_id=det.lote_id, ubicacion_id=ubic_evento,
                datos={"numero_devolucion": dev.numero_devolucion, "accion": det.accion,
                       "estado_calidad": det.estado_calidad, "cantidad": det.cantidad},
            )

    if data.estado == "REINGRESADA":
        # Lo que vuelve revierte su costo de venta; si estaba facturado, nota crédito.
        await wms_contable.contabilizar_devolucion(db, dev, current_user.username)
    await db.commit()
    r2 = await db.execute(
        select(WMSDevolucion)
        .options(
            selectinload(WMSDevolucion.almacen),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.producto),
            selectinload(WMSDevolucion.detalles).selectinload(WMSDevolucionDetalle.lote),
        )
        .where(WMSDevolucion.id == dev_id)
    )
    return r2.scalar_one()


# ─── CONTROL DE VENCIMIENTOS (FEFO) ───────────────────────────────────────────

@router.get("/inventario/vencimientos")
async def inventario_vencimientos(
    dias: int = Query(30, ge=0, description="Umbral de días para 'por vencer'"),
    almacen_id: Optional[int] = None,
    incluir_vencidos: bool = True,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Inventario perecedero (con lote y fecha de vencimiento) clasificado por
    estado de vida útil — insumo de FEFO y control ISO 9001 §8.5.4."""
    hoy = date.today()
    limite = hoy + timedelta(days=dias)
    q = (
        select(WMSInventarioUbicacion, WMSLote, WMSProducto, WMSUbicacion)
        .join(WMSLote, WMSInventarioUbicacion.lote_id == WMSLote.id)
        .join(WMSProducto, WMSInventarioUbicacion.producto_id == WMSProducto.id)
        .join(WMSUbicacion, WMSInventarioUbicacion.ubicacion_id == WMSUbicacion.id)
        .join(WMSZona, WMSUbicacion.zona_id == WMSZona.id)
        .where(
            WMSLote.fecha_vencimiento.isnot(None),
            WMSInventarioUbicacion.cantidad_disponible > 0,
            WMSLote.fecha_vencimiento <= limite,
        )
    )
    if almacen_id:
        q = q.where(WMSZona.almacen_id == almacen_id)
    q = q.order_by(WMSLote.fecha_vencimiento.asc())
    r = await db.execute(q)

    filas = []
    for inv, lote, prod, ubic in r.all():
        dias_rest = (lote.fecha_vencimiento - hoy).days
        if dias_rest < 0 and not incluir_vencidos:
            continue
        estado = "VENCIDO" if dias_rest < 0 else ("CRITICO" if dias_rest <= 7 else "POR_VENCER")
        if not lote.activo:
            estado = "BLOQUEADO"
        filas.append({
            "inventario_id": inv.id,
            "producto": {"id": prod.id, "sku": prod.sku, "nombre": prod.nombre},
            "lote": lote.numero_lote,
            "ubicacion": ubic.codigo,
            "fecha_vencimiento": lote.fecha_vencimiento.isoformat(),
            "dias_restantes": dias_rest,
            "cantidad_disponible": inv.cantidad_disponible,
            "estado": estado,
        })
    resumen = {
        "vencidos":    sum(1 for f in filas if f["estado"] == "VENCIDO"),
        "criticos":    sum(1 for f in filas if f["estado"] == "CRITICO"),
        "por_vencer":  sum(1 for f in filas if f["estado"] == "POR_VENCER"),
        "bloqueados":  sum(1 for f in filas if f["estado"] == "BLOQUEADO"),
    }
    return {"resumen": resumen, "items": filas}


# ─── TRAZABILIDAD ─────────────────────────────────────────────────────────────

from app.infrastructure.models.usuario import Usuario as _UsuarioModel


def _serialize_evento(ev: WMSEventoTrazabilidad, usuario_nombre: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id":               ev.id,
        "tipo_evento":      ev.tipo_evento,
        "descripcion":      ev.descripcion,
        "fecha_hora":       ev.created_at.isoformat() if ev.created_at else None,
        "usuario_nombre":   usuario_nombre,
        "datos_adicionales": ev.datos_adicionales,
    }


async def _eventos_con_usuario(db: AsyncSession, eventos: list) -> list:
    usuario_ids = {ev.usuario_id for ev in eventos if ev.usuario_id}
    nombres: Dict[int, str] = {}
    if usuario_ids:
        u_r = await db.execute(
            select(_UsuarioModel).where(_UsuarioModel.id.in_(usuario_ids))
        )
        for u in u_r.scalars().all():
            nombres[u.id] = f"{u.nombre} {u.apellido}"
    return [_serialize_evento(ev, nombres.get(ev.usuario_id)) for ev in eventos]


@router.get("/trazabilidad/producto/{sku}")
async def trazabilidad_producto(
    sku: str,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    prod_r = await db.execute(select(WMSProducto).where(WMSProducto.sku == sku))
    prod = prod_r.scalar_one_or_none()
    if not prod:
        raise HTTPException(404, f"Producto con SKU '{sku}' no encontrado")

    stock_r = await db.execute(
        select(func.coalesce(func.sum(WMSInventarioUbicacion.cantidad_disponible), 0.0))
        .where(WMSInventarioUbicacion.producto_id == prod.id)
    )
    stock_total = float(stock_r.scalar() or 0)

    ev_r = await db.execute(
        select(WMSEventoTrazabilidad)
        .where(WMSEventoTrazabilidad.producto_id == prod.id)
        .order_by(WMSEventoTrazabilidad.created_at.asc())
        .limit(limit)
    )
    eventos_raw = list(ev_r.scalars().all())
    eventos = await _eventos_con_usuario(db, eventos_raw)

    return {
        "nombre":      prod.nombre,
        "sku":         prod.sku,
        "stock_total": stock_total,
        "eventos":     eventos,
    }


@router.get("/trazabilidad/lote/{numero_lote}")
async def trazabilidad_lote(
    numero_lote: str,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    lote_r = await db.execute(select(WMSLote).where(WMSLote.numero_lote == numero_lote))
    lote = lote_r.scalars().first()
    if not lote:
        raise HTTPException(404, f"Lote '{numero_lote}' no encontrado")

    ev_r = await db.execute(
        select(WMSEventoTrazabilidad)
        .where(WMSEventoTrazabilidad.lote_id == lote.id)
        .order_by(WMSEventoTrazabilidad.created_at.asc())
        .limit(limit)
    )
    eventos_raw = list(ev_r.scalars().all())
    eventos = await _eventos_con_usuario(db, eventos_raw)

    venc = lote.fecha_vencimiento.isoformat() if lote.fecha_vencimiento else None
    estado = "vencido" if (lote.fecha_vencimiento and str(lote.fecha_vencimiento) < str(date.today())) else "activo"

    return {
        "numero_lote":      lote.numero_lote,
        "fecha_vencimiento": venc,
        "estado":           estado if lote.activo else "inactivo",
        "eventos":          eventos,
    }


@router.get("/trazabilidad/ubicacion/{codigo}")
async def trazabilidad_ubicacion(
    codigo: str,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    ubic_r = await db.execute(
        select(WMSUbicacion)
        .options(selectinload(WMSUbicacion.zona))
        .where(WMSUbicacion.codigo == codigo)
    )
    ubic = ubic_r.scalar_one_or_none()
    if not ubic:
        raise HTTPException(404, f"Ubicación '{codigo}' no encontrada")

    ev_r = await db.execute(
        select(WMSEventoTrazabilidad)
        .where(WMSEventoTrazabilidad.ubicacion_id == ubic.id)
        .order_by(WMSEventoTrazabilidad.created_at.asc())
        .limit(limit)
    )
    eventos_raw = list(ev_r.scalars().all())
    eventos = await _eventos_con_usuario(db, eventos_raw)

    return {
        "codigo":    ubic.codigo,
        "zona":      ubic.zona.nombre if ubic.zona else "—",
        "capacidad": ubic.capacidad_kg,
        "eventos":   eventos,
    }


# ─── DASHBOARD — KPIs ─────────────────────────────────────────────────────────

@router.get("/dashboard/kpis", response_model=WMSKPIs)
async def dashboard_kpis(
    almacen_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    hoy = date.today()
    # Por omisión, los últimos 90 días. Antes se calculaba `f_desde`/`f_hasta` y
    # NO se usaban en ninguna consulta: los indicadores salían sobre toda la
    # historia y el selector de período de la pantalla no hacía nada. Un OTIF de
    # tres años no le sirve a nadie para decidir hoy.
    f_desde = fecha_desde or (hoy - timedelta(days=90))
    f_hasta = fecha_hasta or hoy

    # Base filter para órdenes de salida entregadas
    filtro_base = [
        WMSOrdenSalida.deleted_at.is_(None),
        WMSOrdenSalida.estado == "ENTREGADO",
        WMSOrdenSalida.fecha_emision >= f_desde,
        WMSOrdenSalida.fecha_emision <= f_hasta,
    ]
    if almacen_id:
        filtro_base.append(WMSOrdenSalida.almacen_id == almacen_id)

    # Total entregadas en el período (usando fecha de despacho vía join)
    total_r = await db.execute(
        select(func.count(WMSOrdenSalida.id)).where(*filtro_base)
    )
    ordenes_entregadas_total = total_r.scalar() or 0

    # On-Time: entregadas donde fecha_entrega_real <= fecha_requerida
    ot_r = await db.execute(
        select(func.count(WMSDespacho.id))
        .join(WMSOrdenSalida, WMSDespacho.orden_id == WMSOrdenSalida.id)
        .where(
            WMSDespacho.deleted_at.is_(None),
            WMSDespacho.estado == "ENTREGADO",
            WMSOrdenSalida.fecha_requerida.isnot(None),
            WMSDespacho.fecha_entrega_real <= WMSOrdenSalida.fecha_requerida,
            WMSOrdenSalida.fecha_emision >= f_desde,
            WMSOrdenSalida.fecha_emision <= f_hasta,
            *([WMSOrdenSalida.almacen_id == almacen_id] if almacen_id else []),
        ))
    ordenes_on_time = ot_r.scalar() or 0

    # In-Full: todas las líneas de la orden completas (cantidad_despachada >= cantidad_solicitada)
    # Usamos subquery: ordenes donde ningún detalle tenga cantidad_despachada < cantidad_solicitada
    if_r = await db.execute(
        select(func.count(WMSOrdenSalida.id))
        .where(
            *filtro_base,
            ~WMSOrdenSalida.id.in_(
                select(WMSOrdenSalidaDetalle.orden_id).where(
                    WMSOrdenSalidaDetalle.cantidad_despachada < WMSOrdenSalidaDetalle.cantidad_solicitada
                )
            ),
        )
    )
    ordenes_in_full = if_r.scalar() or 0

    # OTIF y orden perfecta orden por orden (antes: el menor de dos conteos, y
    # la orden perfecta era una copia del OTIF). Ver app/core/wms_kpi.py.
    from app.core import wms_kpi
    ctx_kpi = wms_kpi.Ctx(f_desde, f_hasta, almacen_id)
    r_otif = await wms_kpi.otif(db, ctx_kpi)
    r_perf = await wms_kpi.orden_perfecta(db, ctx_kpi)
    ordenes_otif = int(r_otif.numerador or 0)
    ordenes_perfect = int(r_perf.numerador or 0)

    on_time_pct = round(ordenes_on_time / ordenes_entregadas_total * 100, 2) if ordenes_entregadas_total else 0.0
    in_full_pct = round(ordenes_in_full / ordenes_entregadas_total * 100, 2) if ordenes_entregadas_total else 0.0
    otif_pct = r_otif.valor or 0.0
    perfect_pct = r_perf.valor or 0.0

    # Fill Rate: unidades despachadas / unidades solicitadas, solo de las órdenes
    # que ya tuvieron despacho. Con todas, una orden recién creada contaba como
    # «no surtida» y el indicador bajaba solo por tener pedidos en preparación.
    con_despacho = select(WMSDespacho.orden_id).where(WMSDespacho.deleted_at.is_(None))
    fr_r = await db.execute(
        select(
            func.sum(WMSOrdenSalidaDetalle.cantidad_solicitada),
            func.sum(WMSOrdenSalidaDetalle.cantidad_despachada),
        )
        .join(WMSOrdenSalida, WMSOrdenSalidaDetalle.orden_id == WMSOrdenSalida.id)
        .where(WMSOrdenSalida.deleted_at.is_(None),
               WMSOrdenSalida.id.in_(con_despacho),
               WMSOrdenSalida.fecha_emision >= f_desde,
               WMSOrdenSalida.fecha_emision <= f_hasta,
               *([WMSOrdenSalida.almacen_id == almacen_id] if almacen_id else []))
    )
    fr_row = fr_r.one()
    unidades_sol = fr_row[0] or 0.0
    unidades_des = fr_row[1] or 0.0
    fill_rate_pct = round(unidades_des / unidades_sol * 100, 2) if unidades_sol else 0.0

    # Inventory Accuracy: ubicaciones contadas correctamente (diferencia==0) / total contadas
    ia_r = await db.execute(
        select(
            func.count(WMSConteoDetalle.id),
            func.sum(
                func.cast(
                    and_(WMSConteoDetalle.cantidad_fisica.isnot(None), WMSConteoDetalle.diferencia == 0),
                    Integer,
                )
            ),
        )
        # Se filtraba por `ajustado == True`, y `ajustado` solo es cierto cuando
        # HUBO diferencia. Es decir: se tomaban únicamente las posiciones
        # descuadradas y luego se contaba cuántas de ellas tenían diferencia
        # cero. Ninguna, por definición. La exactitud de inventario salía en 0%
        # pasara lo que pasara — y es el primer número que mira un jefe de
        # bodega. Lo correcto es el universo contado: toda posición con conteo
        # físico registrado.
        .where(WMSConteoDetalle.cantidad_fisica.isnot(None))
        .join(WMSConteoInventario,
              WMSConteoDetalle.conteo_id == WMSConteoInventario.id)
        # Cuenta cuando se hizo el conteo (fecha_fin), no cuando se programó: un
        # conteo adelantado no aparecía hasta que llegaba su fecha programada.
        .where(func.coalesce(func.date(WMSConteoInventario.fecha_fin), WMSConteoInventario.fecha_programada) >= f_desde,
               func.coalesce(func.date(WMSConteoInventario.fecha_fin), WMSConteoInventario.fecha_programada) <= f_hasta,
               *([WMSConteoInventario.almacen_id == almacen_id]
                 if almacen_id else []))
    )
    ia_row = ia_r.one()
    ubic_contadas = ia_row[0] or 0
    ubic_correctas = int(ia_row[1] or 0)
    ia_pct = round(ubic_correctas / ubic_contadas * 100, 2) if ubic_contadas else 0.0

    # Pendientes
    rec_pend_r = await db.execute(
        select(func.count(WMSRecepcion.id)).where(
            WMSRecepcion.deleted_at.is_(None),
            WMSRecepcion.estado.in_(["BORRADOR", "EN_PROCESO"]),
            *([WMSRecepcion.almacen_id == almacen_id] if almacen_id else []),
        )
    )
    recepciones_pendientes = rec_pend_r.scalar() or 0

    ord_pend_r = await db.execute(
        select(func.count(WMSOrdenSalida.id)).where(
            WMSOrdenSalida.deleted_at.is_(None),
            WMSOrdenSalida.estado.in_(["PENDIENTE", "EN_PICKING", "EMPACANDO"]),
            *([WMSOrdenSalida.almacen_id == almacen_id] if almacen_id else []),
        )
    )
    ordenes_salida_pendientes = ord_pend_r.scalar() or 0

    # Órdenes por estado
    estados_r = await db.execute(
        select(WMSOrdenSalida.estado, func.count(WMSOrdenSalida.id))
        .where(WMSOrdenSalida.deleted_at.is_(None),
               *([WMSOrdenSalida.almacen_id == almacen_id] if almacen_id else []))
        .group_by(WMSOrdenSalida.estado)
    )
    ordenes_por_estado = {row[0]: row[1] for row in estados_r.all()}

    # Recepciones urgentes: mercancía que se esperaba y NO ha llegado.
    #
    # Contar toda orden en estado PARCIAL da un número inflado y sin sentido: una
    # orden que llegó incompleta hace ocho meses quedó PARCIAL para siempre y
    # seguiría apareciendo como urgente. Lo urgente es lo que no tiene ninguna
    # recepción y ya pasó de fecha — eso sí es algo que alguien tiene que llamar
    # a reclamar hoy.
    # OC que siguen esperando mercancía, según los estados que configuró la empresa.
    oc_abiertas = await wms_estados_oc.codigos_con_rol(db, ("INICIAL", "EN_RECEPCION", "RECIBIDA_PARCIAL"))
    urg_r = await db.execute(
        select(func.count(WMSOrdenCompra.id)).where(
            WMSOrdenCompra.deleted_at.is_(None),
            WMSOrdenCompra.estado.in_(oc_abiertas),
            WMSOrdenCompra.fecha_esperada < hoy,
            ~select(WMSRecepcion.id).where(
                WMSRecepcion.orden_compra_id == WMSOrdenCompra.id,
                WMSRecepcion.estado == "COMPLETA",
                WMSRecepcion.deleted_at.is_(None),
            ).exists(),
            *([WMSOrdenCompra.almacen_id == almacen_id] if almacen_id else []),
        )
    )
    urgent_recepciones = urg_r.scalar() or 0

    # Las dos listas que el tablero pinta debajo de los indicadores. No existían
    # en la respuesta, así que las dos tablas decían «Sin órdenes recientes»
    # aunque hubiera miles: el tablero se leía como una bodega detenida.
    oc_r = await db.execute(
        select(WMSOrdenCompra, WMSProveedor.nombre)
        .join(WMSProveedor, WMSOrdenCompra.proveedor_id == WMSProveedor.id)
        .where(WMSOrdenCompra.deleted_at.is_(None),
               *([WMSOrdenCompra.almacen_id == almacen_id] if almacen_id else []))
        .order_by(WMSOrdenCompra.fecha_emision.desc(), WMSOrdenCompra.id.desc())
        .limit(8)
    )
    recent_ordenes_compra = [
        {"id": oc.id, "numero_oc": oc.numero_oc, "proveedor_nombre": proveedor,
         "estado": oc.estado,
         "fecha_esperada": oc.fecha_esperada.isoformat() if oc.fecha_esperada else None}
        for oc, proveedor in oc_r.all()
    ]

    os_r = await db.execute(
        select(WMSOrdenSalida, WMSCliente.nombre)
        .join(WMSCliente, WMSOrdenSalida.cliente_id == WMSCliente.id)
        .where(WMSOrdenSalida.deleted_at.is_(None),
               *([WMSOrdenSalida.almacen_id == almacen_id] if almacen_id else []))
        .order_by(WMSOrdenSalida.fecha_emision.desc(), WMSOrdenSalida.id.desc())
        .limit(8)
    )
    recent_ordenes_salida = [
        {"id": o.id, "numero_orden": o.numero_orden, "cliente_nombre": cliente,
         "estado": o.estado, "prioridad": o.prioridad,
         "fecha_requerida": o.fecha_requerida.isoformat() if o.fecha_requerida else None}
        for o, cliente in os_r.all()
    ]

    pick_r = await db.execute(
        select(func.count(WMSPickingTarea.id))
        .join(WMSOrdenSalida, WMSPickingTarea.orden_id == WMSOrdenSalida.id)
        .where(WMSPickingTarea.estado.in_(["PENDIENTE", "EN_PROGRESO"]),
               *([WMSOrdenSalida.almacen_id == almacen_id] if almacen_id else []))
    )
    active_picking_tasks = pick_r.scalar() or 0

    return WMSKPIs(
        ordenes_entregadas_total=ordenes_entregadas_total,
        ordenes_on_time=ordenes_on_time,
        on_time_pct=on_time_pct,
        ordenes_in_full=ordenes_in_full,
        in_full_pct=in_full_pct,
        ordenes_otif=ordenes_otif,
        otif_pct=otif_pct,
        otif_base=int(r_otif.denominador or 0),
        perfect_base=int(r_perf.denominador or 0),
        ordenes_perfect=ordenes_perfect,
        perfect_order_pct=perfect_pct,
        unidades_solicitadas=unidades_sol,
        unidades_despachadas=unidades_des,
        fill_rate_pct=fill_rate_pct,
        ubicaciones_contadas=ubic_contadas,
        ubicaciones_correctas=ubic_correctas,
        inventory_accuracy_pct=ia_pct,
        recepciones_pendientes=recepciones_pendientes,
        ordenes_salida_pendientes=ordenes_salida_pendientes,
        ordenes_por_estado=ordenes_por_estado,
        # Los mismos valores con el nombre que usa el tablero.
        ot_pct=on_time_pct,
        if_pct=in_full_pct,
        perfect_order_rate=perfect_pct,
        fill_rate=fill_rate_pct,
        inventory_accuracy=ia_pct,
        pending_recepciones=recepciones_pendientes,
        pending_ordenes_salida=ordenes_salida_pendientes,
        urgent_recepciones=urgent_recepciones,
        active_picking_tasks=active_picking_tasks,
        recent_ordenes_compra=recent_ordenes_compra,
        recent_ordenes_salida=recent_ordenes_salida,
    )


@router.get("/dashboard/alertas", response_model=WMSAlertasResponse)
async def dashboard_alertas(
    almacen_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    hoy = date.today()
    alertas = []

    # Recepciones pendientes (BORRADOR o EN_PROCESO)
    rec_q = select(func.count(WMSRecepcion.id)).where(
        WMSRecepcion.deleted_at.is_(None),
        WMSRecepcion.estado.in_(["BORRADOR", "EN_PROCESO"]),
    )
    if almacen_id:
        rec_q = rec_q.where(WMSRecepcion.almacen_id == almacen_id)
    rec_r = await db.execute(rec_q)
    recepciones_pendientes = rec_r.scalar() or 0
    if recepciones_pendientes:
        alertas.append({"tipo": "RECEPCION_PENDIENTE", "mensaje": f"{recepciones_pendientes} recepciones en proceso", "count": recepciones_pendientes})

    # Órdenes urgentes pendientes
    urg_q = select(func.count(WMSOrdenSalida.id)).where(
        WMSOrdenSalida.deleted_at.is_(None),
        WMSOrdenSalida.prioridad.in_(["ALTA", "URGENTE"]),
        WMSOrdenSalida.estado.in_(["PENDIENTE", "EN_PICKING"]),
    )
    if almacen_id:
        urg_q = urg_q.where(WMSOrdenSalida.almacen_id == almacen_id)
    urg_r = await db.execute(urg_q)
    ordenes_urgentes = urg_r.scalar() or 0
    if ordenes_urgentes:
        alertas.append({"tipo": "ORDEN_URGENTE", "mensaje": f"{ordenes_urgentes} órdenes urgentes sin despachar", "count": ordenes_urgentes})

    # Órdenes vencidas (fecha_requerida < hoy y no entregadas)
    venc_q = select(func.count(WMSOrdenSalida.id)).where(
        WMSOrdenSalida.deleted_at.is_(None),
        WMSOrdenSalida.fecha_requerida < hoy,
        WMSOrdenSalida.estado.notin_(["ENTREGADO", "CANCELADO"]),
    )
    if almacen_id:
        venc_q = venc_q.where(WMSOrdenSalida.almacen_id == almacen_id)
    venc_r = await db.execute(venc_q)
    ordenes_vencidas = venc_r.scalar() or 0
    if ordenes_vencidas:
        alertas.append({"tipo": "ORDEN_VENCIDA", "mensaje": f"{ordenes_vencidas} órdenes con fecha vencida", "count": ordenes_vencidas})

    # Lotes próximos a vencer (dentro de 30 días)
    limite_venc = hoy + timedelta(days=30)
    prox_venc_q = select(func.count(WMSLote.id)).where(
        WMSLote.activo == True,
        WMSLote.fecha_vencimiento.isnot(None),
        WMSLote.fecha_vencimiento <= limite_venc,
        WMSLote.fecha_vencimiento >= hoy,
    )
    prox_r = await db.execute(prox_venc_q)
    productos_proximos_vencer = prox_r.scalar() or 0
    if productos_proximos_vencer:
        alertas.append({"tipo": "LOTE_PROXIMO_VENCER", "mensaje": f"{productos_proximos_vencer} lotes vencen en los próximos 30 días", "count": productos_proximos_vencer})

    return WMSAlertasResponse(
        recepciones_pendientes=recepciones_pendientes,
        ordenes_urgentes=ordenes_urgentes,
        ordenes_vencidas=ordenes_vencidas,
        productos_proximos_vencer=productos_proximos_vencer,
        alertas=alertas,
    )
