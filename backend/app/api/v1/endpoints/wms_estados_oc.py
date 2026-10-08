"""
WMS · Estados de la orden de compra (configuración del módulo, Daily Logistics).

Ver `app/core/wms_estados_oc.py` para el significado de cada rol.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_estados_oc as eoc
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.wms import WMSEstadoOC, WMSOrdenCompra

router = APIRouter(prefix="/wms", tags=["WMS · Estados de OC"])


class EstadoIn(BaseModel):
    codigo: Optional[str] = Field(default=None, max_length=20)   # solo al crear
    nombre: str = Field(min_length=2, max_length=60)
    color: str = Field(default="#64748B", max_length=20)
    orden: int = 0
    rol: Optional[str] = None
    activo: bool = True


class CambioEstado(BaseModel):
    estado: str


def _dict(e: WMSEstadoOC, usos: int = 0) -> dict:
    return {"id": e.id, "codigo": e.codigo, "nombre": e.nombre, "color": e.color, "orden": e.orden,
            "rol": e.rol, "rol_descripcion": eoc.ROLES.get(e.rol) if e.rol else None,
            "obligatorio": e.rol in eoc.ROLES_OBLIGATORIOS, "activo": e.activo, "usos": usos}


async def _usos(db: AsyncSession) -> dict:
    return dict((await db.execute(select(WMSOrdenCompra.estado, func.count()).where(
        WMSOrdenCompra.deleted_at.is_(None)).group_by(WMSOrdenCompra.estado))).all())


async def _fijar_rol(db: AsyncSession, e: WMSEstadoOC, rol: Optional[str]) -> None:
    if rol is not None and rol not in eoc.ROLES:
        raise HTTPException(422, f"Rol desconocido: {rol}")
    if e.rol in eoc.ROLES_OBLIGATORIOS and rol != e.rol:
        raise HTTPException(422, "Este estado tiene un rol que el sistema necesita. Asígnele ese rol a otro "
                                 "estado y el de este se liberará solo.")
    if rol:
        # Cada rol lo tiene un solo estado: se le quita al que lo tuviera.
        otro = (await db.execute(select(WMSEstadoOC).where(WMSEstadoOC.rol == rol, WMSEstadoOC.id != (e.id or 0)))).scalar()
        if otro:
            otro.rol = None
            await db.flush()
    e.rol = rol


@router.get("/estados-oc")
async def listar(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    estados = await eoc.listar(db)
    usos = await _usos(db)
    await db.commit()   # por si se sembraron los estados por defecto
    return {"estados": [_dict(e, usos.get(e.codigo, 0)) for e in estados],
            "roles": [{"rol": r, "descripcion": d, "obligatorio": r in eoc.ROLES_OBLIGATORIOS}
                      for r, d in eoc.ROLES.items()]}


@router.post("/estados-oc", status_code=201)
async def crear(data: EstadoIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    await eoc.asegurar(db)
    base = (data.codigo or data.nombre).strip().upper()
    codigo = re.sub(r"[^A-Z0-9_]", "_", base.replace(" ", "_"))[:20].strip("_")
    if not codigo:
        raise HTTPException(422, "Código inválido")
    if (await db.execute(select(WMSEstadoOC.id).where(WMSEstadoOC.codigo == codigo))).first():
        raise HTTPException(409, f"Ya existe un estado con el código {codigo}")
    e = WMSEstadoOC(codigo=codigo, nombre=data.nombre.strip(), color=data.color, orden=data.orden, activo=data.activo)
    db.add(e)
    await db.flush()
    if data.rol:
        await _fijar_rol(db, e, data.rol)
    await db.commit()
    return _dict(e)


@router.put("/estados-oc/{eid}")
async def actualizar(eid: int, data: EstadoIn, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    e = await db.get(WMSEstadoOC, eid)
    if not e:
        raise HTTPException(404, "Estado no encontrado")
    if not data.activo and e.rol in eoc.ROLES_OBLIGATORIOS:
        raise HTTPException(422, "No se puede desactivar un estado con un rol que el sistema necesita.")
    e.nombre, e.color, e.orden, e.activo = data.nombre.strip(), data.color, data.orden, data.activo
    await _fijar_rol(db, e, data.rol)
    await db.commit()
    return _dict(e, (await _usos(db)).get(e.codigo, 0))


@router.delete("/estados-oc/{eid}", status_code=204)
async def eliminar(eid: int, db: AsyncSession = Depends(get_db), _=Depends(require_supervisor)):
    e = await db.get(WMSEstadoOC, eid)
    if not e:
        raise HTTPException(404, "Estado no encontrado")
    if e.rol in eoc.ROLES_OBLIGATORIOS:
        raise HTTPException(422, "No se puede eliminar un estado con un rol que el sistema necesita.")
    if (await _usos(db)).get(e.codigo):
        raise HTTPException(409, "Hay órdenes de compra en este estado: desactívelo en lugar de eliminarlo.")
    await db.delete(e)
    await db.commit()


@router.post("/ordenes-compra/{oc_id}/estado")
async def cambiar_estado(oc_id: int, data: CambioEstado, db: AsyncSession = Depends(get_db),
                         yo=Depends(get_current_user)):
    """Cambio manual de estado (p. ej. a «Aprobada», «Cerrada» o «Anulada»)."""
    oc = await db.get(WMSOrdenCompra, oc_id)
    if not oc or oc.deleted_at:
        raise HTTPException(404, "Orden de compra no encontrada")
    if not await eoc.existe(db, data.estado):
        raise HTTPException(422, f"El estado «{data.estado}» no existe o está inactivo.")
    if data.estado != oc.estado:
        # Queda registrado: una OC que ya cambió de estado deja de ser editable.
        from app.infrastructure.models.wms import WMSHistorialEstado
        db.add(WMSHistorialEstado(entidad_tipo="ORDEN_COMPRA", entidad_id=oc.id, estado_anterior=oc.estado,
                                  estado_nuevo=data.estado, tipo_cambio="AVANCE", usuario_id=yo.id))
    oc.estado = data.estado
    await db.commit()
    return {"id": oc.id, "numero_oc": oc.numero_oc, "estado": oc.estado}


# ─── Edición y eliminación de la OC mientras está en su estado inicial ───────
#
# Una OC recién emitida se puede corregir (proveedor, almacén, fechas, artículos,
# cantidades y precios) o eliminar, mientras: su estado tenga el rol INICIAL, no
# tenga ninguna recepción y nunca haya cambiado de estado. Después de eso es un
# documento con historia y solo admite cambios de estado.

async def edicion_bloqueada(db: AsyncSession, oc: WMSOrdenCompra) -> Optional[str]:
    """Por qué la OC ya no se puede editar (None si se puede)."""
    from app.infrastructure.models.wms import WMSHistorialEstado, WMSRecepcion
    if await eoc.rol_de(db, oc.estado) != "INICIAL":
        return "La orden ya no está en su estado inicial."
    rec = (await db.execute(select(WMSRecepcion.numero_recepcion).where(
        WMSRecepcion.orden_compra_id == oc.id, WMSRecepcion.deleted_at.is_(None)).limit(1))).scalar()
    if rec:
        return f"La orden ya tiene la recepción {rec}."
    cambio = (await db.execute(select(func.count()).select_from(WMSHistorialEstado).where(
        WMSHistorialEstado.entidad_tipo == "ORDEN_COMPRA", WMSHistorialEstado.entidad_id == oc.id))).scalar()
    if cambio:
        return "La orden ya tuvo cambios de estado."
    return None


async def ids_editables(db: AsyncSession, ocs) -> set:
    """Las OC de la lista que se pueden editar (en pocas consultas)."""
    from app.infrastructure.models.wms import WMSHistorialEstado, WMSRecepcion
    iniciales = set(await eoc.codigos_con_rol(db, ["INICIAL"]))
    cand = [o.id for o in ocs if o.estado in iniciales]
    if not cand:
        return set()
    con_rec = set((await db.execute(select(WMSRecepcion.orden_compra_id).where(
        WMSRecepcion.orden_compra_id.in_(cand), WMSRecepcion.deleted_at.is_(None)))).scalars())
    con_cambio = set((await db.execute(select(WMSHistorialEstado.entidad_id).where(
        WMSHistorialEstado.entidad_tipo == "ORDEN_COMPRA", WMSHistorialEstado.entidad_id.in_(cand)))).scalars())
    return set(cand) - con_rec - con_cambio


class LineaOCIn(BaseModel):
    id: Optional[int] = None                  # línea existente; sin id = nueva
    producto_id: int
    cantidad_solicitada: float = Field(gt=0)
    precio_unitario: Optional[float] = Field(default=None, ge=0)
    unidad_medida: Optional[str] = None


class EdicionOC(BaseModel):
    proveedor_id: int
    almacen_id: int
    fecha_emision: Optional[str] = None
    fecha_esperada: Optional[str] = None
    notas: Optional[str] = None
    detalles: list[LineaOCIn] = Field(min_length=1)


@router.put("/ordenes-compra/{oc_id}/edicion")
async def editar_oc(oc_id: int, data: EdicionOC, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from datetime import date as _date
    from app.core import wms_operacion as op
    from app.infrastructure.models.wms import WMSAlmacen, WMSOrdenCompraDetalle, WMSProducto, WMSProveedor
    oc = await db.get(WMSOrdenCompra, oc_id)
    if not oc or oc.deleted_at:
        raise HTTPException(404, "Orden de compra no encontrada")
    motivo = await edicion_bloqueada(db, oc)
    if motivo:
        raise HTTPException(409, f"No se puede editar la OC {oc.numero_oc}: {motivo}")
    if not await db.get(WMSProveedor, data.proveedor_id):
        raise HTTPException(422, "Proveedor no encontrado")
    if not await db.get(WMSAlmacen, data.almacen_id):
        raise HTTPException(422, "Almacén no encontrado")
    for l in data.detalles:
        if not await db.get(WMSProducto, l.producto_id):
            raise HTTPException(422, f"El producto {l.producto_id} no existe")
    oc.proveedor_id, oc.almacen_id, oc.notas = data.proveedor_id, data.almacen_id, data.notas
    if data.fecha_emision:
        oc.fecha_emision = _date.fromisoformat(data.fecha_emision)
    oc.fecha_esperada = _date.fromisoformat(data.fecha_esperada) if data.fecha_esperada else None
    actuales = {d.id: d for d in (await db.execute(select(WMSOrdenCompraDetalle).where(
        WMSOrdenCompraDetalle.orden_id == oc.id))).scalars()}
    quedan = set()
    for l in data.detalles:
        d = actuales.get(l.id) if l.id else None
        if d is None:
            d = WMSOrdenCompraDetalle(orden_id=oc.id, cantidad_recibida=0)
            db.add(d)
        d.producto_id, d.cantidad_solicitada, d.precio_unitario = l.producto_id, l.cantidad_solicitada, l.precio_unitario
        d.unidad_medida = l.unidad_medida or d.unidad_medida or "UNIDAD"
        if l.id:
            quedan.add(l.id)
    for i, d in actuales.items():
        if i not in quedan:
            await db.delete(d)
    oc.depositante_id = await op.resolver_depositante(db, oc.depositante_id, [l.producto_id for l in data.detalles])
    await db.commit()
    return {"id": oc.id, "numero_oc": oc.numero_oc, "lineas": len(data.detalles)}


@router.delete("/ordenes-compra/{oc_id}")
async def eliminar_oc(oc_id: int, db: AsyncSession = Depends(get_db), yo=Depends(get_current_user)):
    """Borrado lógico: el número no se reutiliza y queda la traza de quién la eliminó."""
    from datetime import datetime, timezone
    from app.infrastructure.models.wms import WMSHistorialEstado
    oc = await db.get(WMSOrdenCompra, oc_id)
    if not oc or oc.deleted_at:
        raise HTTPException(404, "Orden de compra no encontrada")
    motivo = await edicion_bloqueada(db, oc)
    if motivo:
        raise HTTPException(409, f"No se puede eliminar la OC {oc.numero_oc}: {motivo} Use el estado «Anulada».")
    db.add(WMSHistorialEstado(entidad_tipo="ORDEN_COMPRA", entidad_id=oc.id, estado_anterior=oc.estado,
                              estado_nuevo="ELIMINADA", tipo_cambio="CORRECCION", usuario_id=yo.id,
                              observacion="Eliminada en estado inicial"))
    oc.deleted_at, oc.activo = datetime.now(timezone.utc), False
    await db.commit()
    return {"ok": True, "numero_oc": oc.numero_oc}
