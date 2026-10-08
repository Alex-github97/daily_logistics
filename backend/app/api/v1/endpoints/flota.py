"""
API endpoints — Gestión de Flotas
Prefijo: /flota
"""
from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, extract
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.flota import (
    FlotaMarca, FlotaTipoVehiculo, FlotaTipoCombustible, FlotaCentroCosto,
    FlotaProveedor, FlotaVehiculo, FlotaMedicion, FlotaDocumentoVehiculo,
    FlotaPersonal, FlotaDocumentoPersonal, FlotaRegistroCombustible,
    FlotaTipoTrabajo, FlotaOrdenTrabajo, FlotaOrdenTrabajoDetalle,
    FlotaRepuesto, FlotaRutinaMantenimiento, FlotaRutinaDetalleTrabajo,
    FlotaRutinaDetalleRepuesto, FlotaSecuenciaMantenimiento, FlotaSecuenciaRutina,
    FlotaGrupoVehiculo, FlotaAsignacionSecuencia, FlotaModoFalla, FlotaUmbralCBM,
)
from app.application.schemas.flota import (
    FlotaMarcaCreate, FlotaMarcaUpdate, FlotaMarcaResponse,
    FlotaTipoVehiculoCreate, FlotaTipoVehiculoUpdate, FlotaTipoVehiculoResponse,
    FlotaTipoCombustibleCreate, FlotaTipoCombustibleUpdate, FlotaTipoCombustibleResponse,
    FlotaCentroCostoCreate, FlotaCentroCostoUpdate, FlotaCentroCostoResponse,
    FlotaProveedorCreate, FlotaProveedorUpdate, FlotaProveedorResponse,
    FlotaVehiculoCreate, FlotaVehiculoUpdate, FlotaVehiculoResponse, FlotaVehiculoBaja,
    FlotaMedicionCreate, FlotaMedicionResponse,
    FlotaDocumentoVehiculoCreate, FlotaDocumentoVehiculoUpdate, FlotaDocumentoVehiculoResponse,
    FlotaPersonalCreate, FlotaPersonalUpdate, FlotaPersonalResponse,
    FlotaDocumentoPersonalCreate, FlotaDocumentoPersonalResponse,
    FlotaCombustibleCreate, FlotaCombustibleUpdate, FlotaCombustibleResponse,
    FlotaTipoTrabajoCreate, FlotaTipoTrabajoUpdate, FlotaTipoTrabajoResponse,
    FlotaOrdenCreate, FlotaOrdenUpdate, FlotaOrdenEstado, FlotaOrdenResponse,
    FlotaKPIs,
    FlotaRepuestoCreate, FlotaRepuestoUpdate, FlotaRepuestoResponse,
    FlotaRutinaCreate, FlotaRutinaUpdate, FlotaRutinaResponse,
    FlotaRutinaTrabajoResponse, FlotaRutinaRepuestoResponse,
    FlotaSecuenciaCreate, FlotaSecuenciaUpdate, FlotaSecuenciaResponse, FlotaSecuenciaRutinaResponse,
    FlotaGrupoCreate, FlotaGrupoUpdate, FlotaGrupoResponse,
    FlotaAsignacionCreate, FlotaAsignacionUpdate, FlotaAsignacionResponse,
    FlotaModoFallaCreate, FlotaModoFallaUpdate, FlotaModoFallaResponse,
    FlotaUmbralCBMCreate, FlotaUmbralCBMUpdate, FlotaUmbralCBMResponse,
    FlotaProximoMantenimiento,
)

router = APIRouter(prefix="/flota", tags=["flota"])


def _semaforo(fecha_venc: date) -> tuple[str, int]:
    hoy = date.today()
    dias = (fecha_venc - hoy).days
    if dias < 0:
        return "VENCIDO", dias
    elif dias <= 30:
        return "POR_VENCER", dias
    return "VIGENTE", dias


# ─── Catálogos ─────────────────────────────────────────────────────────────────

@router.get("/marcas/", response_model=List[FlotaMarcaResponse])
async def listar_marcas(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(FlotaMarca).order_by(FlotaMarca.nombre))
    return r.scalars().all()

@router.post("/marcas/", response_model=FlotaMarcaResponse, status_code=201)
async def crear_marca(data: FlotaMarcaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaMarca(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/marcas/{marca_id}", response_model=FlotaMarcaResponse)
async def actualizar_marca(marca_id: int, data: FlotaMarcaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaMarca, marca_id)
    if not obj: raise HTTPException(404, "Marca no encontrada")
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/marcas/{marca_id}", status_code=204)
async def eliminar_marca(marca_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaMarca, marca_id)
    if not obj: raise HTTPException(404, "Marca no encontrada")
    await db.delete(obj); await db.commit()


@router.get("/tipos-vehiculo/", response_model=List[FlotaTipoVehiculoResponse])
async def listar_tipos_vehiculo(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(FlotaTipoVehiculo).order_by(FlotaTipoVehiculo.nombre))
    return r.scalars().all()

@router.post("/tipos-vehiculo/", response_model=FlotaTipoVehiculoResponse, status_code=201)
async def crear_tipo_vehiculo(data: FlotaTipoVehiculoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaTipoVehiculo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/tipos-vehiculo/{id}", response_model=FlotaTipoVehiculoResponse)
async def actualizar_tipo_vehiculo(id: int, data: FlotaTipoVehiculoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaTipoVehiculo, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/tipos-vehiculo/{id}", status_code=204)
async def eliminar_tipo_vehiculo(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaTipoVehiculo, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


@router.get("/tipos-combustible/", response_model=List[FlotaTipoCombustibleResponse])
async def listar_tipos_combustible(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(FlotaTipoCombustible).order_by(FlotaTipoCombustible.nombre))
    return r.scalars().all()

@router.post("/tipos-combustible/", response_model=FlotaTipoCombustibleResponse, status_code=201)
async def crear_tipo_combustible(data: FlotaTipoCombustibleCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaTipoCombustible(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/tipos-combustible/{id}", response_model=FlotaTipoCombustibleResponse)
async def actualizar_tipo_combustible(id: int, data: FlotaTipoCombustibleUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaTipoCombustible, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/tipos-combustible/{id}", status_code=204)
async def eliminar_tipo_combustible(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaTipoCombustible, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


@router.get("/centros-costo/", response_model=List[FlotaCentroCostoResponse])
async def listar_centros_costo(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(FlotaCentroCosto).order_by(FlotaCentroCosto.nombre))
    return r.scalars().all()

@router.post("/centros-costo/", response_model=FlotaCentroCostoResponse, status_code=201)
async def crear_centro_costo(data: FlotaCentroCostoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaCentroCosto(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/centros-costo/{id}", response_model=FlotaCentroCostoResponse)
async def actualizar_centro_costo(id: int, data: FlotaCentroCostoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaCentroCosto, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/centros-costo/{id}", status_code=204)
async def eliminar_centro_costo(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaCentroCosto, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


@router.get("/proveedores/", response_model=List[FlotaProveedorResponse])
async def listar_proveedores(tipo: Optional[str] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(FlotaProveedor)
    if tipo: q = q.where(FlotaProveedor.tipo == tipo)
    r = await db.execute(q.order_by(FlotaProveedor.nombre))
    return r.scalars().all()

@router.post("/proveedores/", response_model=FlotaProveedorResponse, status_code=201)
async def crear_proveedor(data: FlotaProveedorCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaProveedor(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/proveedores/{id}", response_model=FlotaProveedorResponse)
async def actualizar_proveedor(id: int, data: FlotaProveedorUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaProveedor, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/proveedores/{id}", status_code=204)
async def eliminar_proveedor(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaProveedor, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ─── Vehículos ─────────────────────────────────────────────────────────────────

@router.get("/vehiculos/", response_model=List[FlotaVehiculoResponse])
async def listar_vehiculos(
    activo: Optional[bool] = None, ciudad: Optional[str] = None,
    tipo_vehiculo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    q = (select(FlotaVehiculo)
         .options(selectinload(FlotaVehiculo.marca), selectinload(FlotaVehiculo.tipo_vehiculo))
         .where(FlotaVehiculo.deleted_at == None))
    if activo is not None:
        q = q.where(FlotaVehiculo.activo == activo)
    if ciudad:
        q = q.where(FlotaVehiculo.ciudad.ilike(f"%{ciudad}%"))
    if tipo_vehiculo_id:
        q = q.where(FlotaVehiculo.tipo_vehiculo_id == tipo_vehiculo_id)
    r = await db.execute(q.order_by(FlotaVehiculo.placa))
    return r.scalars().all()

@router.post("/vehiculos/", response_model=FlotaVehiculoResponse, status_code=201)
async def crear_vehiculo(
    data: FlotaVehiculoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    obj = FlotaVehiculo(**data.model_dump())
    db.add(obj); await db.commit()
    r = await db.execute(
        select(FlotaVehiculo).options(selectinload(FlotaVehiculo.marca), selectinload(FlotaVehiculo.tipo_vehiculo))
        .where(FlotaVehiculo.id == obj.id)
    )
    return r.scalar_one()

@router.get("/vehiculos/{vehiculo_id}", response_model=FlotaVehiculoResponse)
async def obtener_vehiculo(vehiculo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(
        select(FlotaVehiculo)
        .options(selectinload(FlotaVehiculo.marca), selectinload(FlotaVehiculo.tipo_vehiculo))
        .where(FlotaVehiculo.id == vehiculo_id, FlotaVehiculo.deleted_at == None)
    )
    obj = r.scalar_one_or_none()
    if not obj: raise HTTPException(404, "Vehículo no encontrado")
    return obj

@router.put("/vehiculos/{vehiculo_id}", response_model=FlotaVehiculoResponse)
async def actualizar_vehiculo(
    vehiculo_id: int, data: FlotaVehiculoUpdate,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    obj = await db.get(FlotaVehiculo, vehiculo_id)
    if not obj or obj.deleted_at: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit()
    r = await db.execute(
        select(FlotaVehiculo).options(selectinload(FlotaVehiculo.marca), selectinload(FlotaVehiculo.tipo_vehiculo))
        .where(FlotaVehiculo.id == vehiculo_id)
    )
    return r.scalar_one()

@router.patch("/vehiculos/{vehiculo_id}/baja", response_model=FlotaVehiculoResponse)
async def dar_baja_vehiculo(
    vehiculo_id: int, data: FlotaVehiculoBaja,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    obj = await db.get(FlotaVehiculo, vehiculo_id)
    if not obj: raise HTTPException(404)
    obj.activo = False; obj.fecha_baja = data.fecha_baja; obj.motivo_baja = data.motivo_baja
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/vehiculos/{vehiculo_id}", status_code=204)
async def eliminar_vehiculo(vehiculo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from datetime import datetime
    obj = await db.get(FlotaVehiculo, vehiculo_id)
    if not obj: raise HTTPException(404)
    obj.deleted_at = datetime.utcnow(); await db.commit()


# ─── Mediciones ────────────────────────────────────────────────────────────────

@router.get("/vehiculos/{vehiculo_id}/mediciones", response_model=List[FlotaMedicionResponse])
async def listar_mediciones(vehiculo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(
        select(FlotaMedicion).where(FlotaMedicion.vehiculo_id == vehiculo_id).order_by(FlotaMedicion.fecha.desc())
    )
    return r.scalars().all()

@router.post("/vehiculos/{vehiculo_id}/mediciones", response_model=FlotaMedicionResponse, status_code=201)
async def registrar_medicion(
    vehiculo_id: int, data: FlotaMedicionCreate,
    db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)
):
    obj = FlotaMedicion(**data.model_dump(), registrado_por_id=current_user.id)
    obj.vehiculo_id = vehiculo_id
    db.add(obj); await db.commit(); await db.refresh(obj); return obj


# ─── Documentos Vehículo ───────────────────────────────────────────────────────

@router.get("/vehiculos/{vehiculo_id}/documentos", response_model=List[FlotaDocumentoVehiculoResponse])
async def listar_documentos_vehiculo(vehiculo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(
        select(FlotaDocumentoVehiculo).where(FlotaDocumentoVehiculo.vehiculo_id == vehiculo_id)
        .order_by(FlotaDocumentoVehiculo.fecha_vencimiento)
    )
    docs = r.scalars().all()
    result = []
    for d in docs:
        estado, dias = _semaforo(d.fecha_vencimiento)
        item = FlotaDocumentoVehiculoResponse.model_validate(d)
        item.estado_semaforo = estado; item.dias_para_vencer = dias
        result.append(item)
    return result

@router.post("/vehiculos/{vehiculo_id}/documentos", response_model=FlotaDocumentoVehiculoResponse, status_code=201)
async def crear_documento_vehiculo(
    vehiculo_id: int, data: FlotaDocumentoVehiculoCreate,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    obj = FlotaDocumentoVehiculo(**data.model_dump())
    obj.vehiculo_id = vehiculo_id
    db.add(obj); await db.commit(); await db.refresh(obj)
    estado, dias = _semaforo(obj.fecha_vencimiento)
    r = FlotaDocumentoVehiculoResponse.model_validate(obj)
    r.estado_semaforo = estado; r.dias_para_vencer = dias
    return r

@router.put("/documentos-vehiculo/{doc_id}", response_model=FlotaDocumentoVehiculoResponse)
async def actualizar_documento_vehiculo(
    doc_id: int, data: FlotaDocumentoVehiculoUpdate,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    obj = await db.get(FlotaDocumentoVehiculo, doc_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    estado, dias = _semaforo(obj.fecha_vencimiento)
    r = FlotaDocumentoVehiculoResponse.model_validate(obj)
    r.estado_semaforo = estado; r.dias_para_vencer = dias
    return r

@router.delete("/documentos-vehiculo/{doc_id}", status_code=204)
async def eliminar_documento_vehiculo(doc_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaDocumentoVehiculo, doc_id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ─── Documentos globales (semáforo) ────────────────────────────────────────────

@router.get("/documentos/", response_model=List[FlotaDocumentoVehiculoResponse])
async def listar_todos_documentos(
    estado: Optional[str] = None,  # VIGENTE, POR_VENCER, VENCIDO
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    r = await db.execute(select(FlotaDocumentoVehiculo).order_by(FlotaDocumentoVehiculo.fecha_vencimiento))
    docs = r.scalars().all()
    result = []
    for d in docs:
        sem, dias = _semaforo(d.fecha_vencimiento)
        if estado and sem != estado: continue
        item = FlotaDocumentoVehiculoResponse.model_validate(d)
        item.estado_semaforo = sem; item.dias_para_vencer = dias
        result.append(item)
    return result


# ─── Personal ──────────────────────────────────────────────────────────────────

@router.get("/personal/", response_model=List[FlotaPersonalResponse])
async def listar_personal(
    tipo: Optional[str] = None, activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    q = select(FlotaPersonal).where(FlotaPersonal.deleted_at == None)
    if tipo: q = q.where(FlotaPersonal.tipo == tipo)
    if activo is not None: q = q.where(FlotaPersonal.activo == activo)
    r = await db.execute(q.order_by(FlotaPersonal.apellidos))
    return r.scalars().all()

@router.post("/personal/", response_model=FlotaPersonalResponse, status_code=201)
async def crear_personal(data: FlotaPersonalCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaPersonal(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/personal/{id}", response_model=FlotaPersonalResponse)
async def actualizar_personal(id: int, data: FlotaPersonalUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaPersonal, id)
    if not obj or obj.deleted_at: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/personal/{id}", status_code=204)
async def eliminar_personal(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from datetime import datetime
    obj = await db.get(FlotaPersonal, id)
    if not obj: raise HTTPException(404)
    obj.deleted_at = datetime.utcnow(); await db.commit()

@router.get("/personal/{id}/documentos", response_model=List[FlotaDocumentoPersonalResponse])
async def listar_documentos_personal(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(
        select(FlotaDocumentoPersonal).where(FlotaDocumentoPersonal.personal_id == id)
        .order_by(FlotaDocumentoPersonal.fecha_vencimiento)
    )
    docs = r.scalars().all()
    result = []
    for d in docs:
        estado, dias = _semaforo(d.fecha_vencimiento)
        item = FlotaDocumentoPersonalResponse.model_validate(d)
        item.estado_semaforo = estado; item.dias_para_vencer = dias
        result.append(item)
    return result

@router.post("/personal/{id}/documentos", response_model=FlotaDocumentoPersonalResponse, status_code=201)
async def crear_documento_personal(
    id: int, data: FlotaDocumentoPersonalCreate,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    obj = FlotaDocumentoPersonal(**data.model_dump())
    obj.personal_id = id
    db.add(obj); await db.commit(); await db.refresh(obj)
    estado, dias = _semaforo(obj.fecha_vencimiento)
    r = FlotaDocumentoPersonalResponse.model_validate(obj)
    r.estado_semaforo = estado; r.dias_para_vencer = dias
    return r

@router.delete("/documentos-personal/{doc_id}", status_code=204)
async def eliminar_documento_personal(doc_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaDocumentoPersonal, doc_id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ─── Combustible ───────────────────────────────────────────────────────────────

@router.get("/combustible/", response_model=List[FlotaCombustibleResponse])
async def listar_combustible(
    vehiculo_id: Optional[int] = None,
    fecha_desde: Optional[date] = None, fecha_hasta: Optional[date] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    q = (select(FlotaRegistroCombustible)
         .options(selectinload(FlotaRegistroCombustible.vehiculo)))
    if vehiculo_id: q = q.where(FlotaRegistroCombustible.vehiculo_id == vehiculo_id)
    if fecha_desde: q = q.where(FlotaRegistroCombustible.fecha >= fecha_desde)
    if fecha_hasta: q = q.where(FlotaRegistroCombustible.fecha <= fecha_hasta)
    r = await db.execute(q.order_by(FlotaRegistroCombustible.fecha.desc()))
    return r.scalars().all()

@router.post("/combustible/", response_model=FlotaCombustibleResponse, status_code=201)
async def registrar_combustible(
    data: FlotaCombustibleCreate, db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    payload = data.model_dump()
    if payload.get("valor_unitario") and payload.get("cantidad") and not payload.get("valor_total"):
        payload["valor_total"] = round(payload["valor_unitario"] * payload["cantidad"], 2)
    payload["registrado_por_id"] = current_user.id
    obj = FlotaRegistroCombustible(**payload)
    db.add(obj); await db.commit()
    r = await db.execute(
        select(FlotaRegistroCombustible)
        .options(selectinload(FlotaRegistroCombustible.vehiculo))
        .where(FlotaRegistroCombustible.id == obj.id)
    )
    return r.scalar_one()

@router.put("/combustible/{id}", response_model=FlotaCombustibleResponse)
async def actualizar_combustible(id: int, data: FlotaCombustibleUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaRegistroCombustible, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit()
    r = await db.execute(
        select(FlotaRegistroCombustible).options(selectinload(FlotaRegistroCombustible.vehiculo))
        .where(FlotaRegistroCombustible.id == id)
    )
    return r.scalar_one()

@router.delete("/combustible/{id}", status_code=204)
async def eliminar_combustible(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaRegistroCombustible, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ─── Tipos de Trabajo ──────────────────────────────────────────────────────────

@router.get("/tipos-trabajo/", response_model=List[FlotaTipoTrabajoResponse])
async def listar_tipos_trabajo(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(FlotaTipoTrabajo).where(FlotaTipoTrabajo.activo == True).order_by(FlotaTipoTrabajo.nombre))
    return r.scalars().all()

@router.post("/tipos-trabajo/", response_model=FlotaTipoTrabajoResponse, status_code=201)
async def crear_tipo_trabajo(data: FlotaTipoTrabajoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaTipoTrabajo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/tipos-trabajo/{id}", response_model=FlotaTipoTrabajoResponse)
async def actualizar_tipo_trabajo(id: int, data: FlotaTipoTrabajoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaTipoTrabajo, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/tipos-trabajo/{id}", status_code=204)
async def eliminar_tipo_trabajo(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaTipoTrabajo, id)
    if not obj: raise HTTPException(404)
    obj.activo = False; await db.commit()


# ─── Órdenes de Trabajo ────────────────────────────────────────────────────────

async def _generar_numero_orden(db: AsyncSession) -> str:
    r = await db.execute(select(func.count(FlotaOrdenTrabajo.id)))
    n = (r.scalar() or 0) + 1
    return f"OT-{n:05d}"

@router.get("/ordenes/", response_model=List[FlotaOrdenResponse])
async def listar_ordenes(
    estado: Optional[str] = None, vehiculo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    q = (select(FlotaOrdenTrabajo)
         .options(
             selectinload(FlotaOrdenTrabajo.vehiculo),
             selectinload(FlotaOrdenTrabajo.mecanico),
             selectinload(FlotaOrdenTrabajo.detalles),
         )
         .where(FlotaOrdenTrabajo.deleted_at == None))
    if estado: q = q.where(FlotaOrdenTrabajo.estado == estado)
    if vehiculo_id: q = q.where(FlotaOrdenTrabajo.vehiculo_id == vehiculo_id)
    r = await db.execute(q.order_by(FlotaOrdenTrabajo.fecha_apertura.desc()))
    return r.scalars().all()

@router.post("/ordenes/", response_model=FlotaOrdenResponse, status_code=201)
async def crear_orden(
    data: FlotaOrdenCreate, db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    numero = await _generar_numero_orden(db)
    payload = data.model_dump(exclude={"detalles"})
    payload["numero"] = numero
    payload["creado_por_id"] = current_user.id
    orden = FlotaOrdenTrabajo(**payload)
    db.add(orden); await db.flush()
    for det in data.detalles:
        db.add(FlotaOrdenTrabajoDetalle(**det.model_dump(), orden_id=orden.id))
    await db.commit()
    r = await db.execute(
        select(FlotaOrdenTrabajo)
        .options(
            selectinload(FlotaOrdenTrabajo.vehiculo), selectinload(FlotaOrdenTrabajo.mecanico),
            selectinload(FlotaOrdenTrabajo.detalles),
        )
        .where(FlotaOrdenTrabajo.id == orden.id)
    )
    return r.scalar_one()

@router.patch("/ordenes/{id}/estado", response_model=FlotaOrdenResponse)
async def cambiar_estado_orden(id: int, data: FlotaOrdenEstado, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaOrdenTrabajo, id)
    if not obj: raise HTTPException(404)
    obj.estado = data.estado
    if data.estado == "CERRADA" and not obj.fecha_cierre:
        obj.fecha_cierre = date.today()
    await db.commit()
    r = await db.execute(
        select(FlotaOrdenTrabajo)
        .options(
            selectinload(FlotaOrdenTrabajo.vehiculo), selectinload(FlotaOrdenTrabajo.mecanico),
            selectinload(FlotaOrdenTrabajo.detalles),
        )
        .where(FlotaOrdenTrabajo.id == id)
    )
    return r.scalar_one()

@router.put("/ordenes/{id}", response_model=FlotaOrdenResponse)
async def actualizar_orden(id: int, data: FlotaOrdenUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaOrdenTrabajo, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit()
    r = await db.execute(
        select(FlotaOrdenTrabajo)
        .options(
            selectinload(FlotaOrdenTrabajo.vehiculo), selectinload(FlotaOrdenTrabajo.mecanico),
            selectinload(FlotaOrdenTrabajo.detalles),
        )
        .where(FlotaOrdenTrabajo.id == id)
    )
    return r.scalar_one()

@router.delete("/ordenes/{id}", status_code=204)
async def eliminar_orden(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from datetime import datetime
    obj = await db.get(FlotaOrdenTrabajo, id)
    if not obj: raise HTTPException(404)
    obj.deleted_at = datetime.utcnow(); await db.commit()


# ─── Dashboard KPIs ────────────────────────────────────────────────────────────

@router.get("/dashboard/kpis", response_model=FlotaKPIs)
async def dashboard_kpis(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    hoy = date.today()
    mes_inicio = hoy.replace(day=1)
    limite_por_vencer = hoy + timedelta(days=30)

    total_v = (await db.execute(select(func.count(FlotaVehiculo.id)).where(FlotaVehiculo.deleted_at == None))).scalar() or 0
    activos_v = (await db.execute(select(func.count(FlotaVehiculo.id)).where(FlotaVehiculo.deleted_at == None, FlotaVehiculo.activo == True))).scalar() or 0
    en_mant = (await db.execute(select(func.count(FlotaOrdenTrabajo.id)).where(FlotaOrdenTrabajo.estado.in_(["ABIERTA", "EN_PROCESO"]), FlotaOrdenTrabajo.deleted_at == None))).scalar() or 0

    total_p = (await db.execute(select(func.count(FlotaPersonal.id)).where(FlotaPersonal.deleted_at == None, FlotaPersonal.activo == True))).scalar() or 0
    conductores = (await db.execute(select(func.count(FlotaPersonal.id)).where(FlotaPersonal.tipo == "CONDUCTOR", FlotaPersonal.deleted_at == None, FlotaPersonal.activo == True))).scalar() or 0
    mecanicos = (await db.execute(select(func.count(FlotaPersonal.id)).where(FlotaPersonal.tipo == "MECANICO", FlotaPersonal.deleted_at == None, FlotaPersonal.activo == True))).scalar() or 0

    ordenes_abiertas = (await db.execute(select(func.count(FlotaOrdenTrabajo.id)).where(FlotaOrdenTrabajo.estado == "ABIERTA", FlotaOrdenTrabajo.deleted_at == None))).scalar() or 0
    ordenes_proceso = (await db.execute(select(func.count(FlotaOrdenTrabajo.id)).where(FlotaOrdenTrabajo.estado == "EN_PROCESO", FlotaOrdenTrabajo.deleted_at == None))).scalar() or 0

    docs_vencidos = (await db.execute(select(func.count(FlotaDocumentoVehiculo.id)).where(FlotaDocumentoVehiculo.fecha_vencimiento < hoy))).scalar() or 0
    docs_por_vencer = (await db.execute(select(func.count(FlotaDocumentoVehiculo.id)).where(FlotaDocumentoVehiculo.fecha_vencimiento >= hoy, FlotaDocumentoVehiculo.fecha_vencimiento <= limite_por_vencer))).scalar() or 0

    litros = (await db.execute(select(func.sum(FlotaRegistroCombustible.cantidad)).where(FlotaRegistroCombustible.fecha >= mes_inicio))).scalar() or 0.0
    costo_comb = (await db.execute(select(func.sum(FlotaRegistroCombustible.valor_total)).where(FlotaRegistroCombustible.fecha >= mes_inicio))).scalar() or 0.0

    costo_mant_q = select(
        func.sum(FlotaOrdenTrabajo.costo_repuestos + FlotaOrdenTrabajo.costo_mano_obra)
    ).where(FlotaOrdenTrabajo.fecha_apertura >= mes_inicio, FlotaOrdenTrabajo.deleted_at == None)
    costo_mant = (await db.execute(costo_mant_q)).scalar() or 0.0

    return FlotaKPIs(
        total_vehiculos=total_v, vehiculos_activos=activos_v, vehiculos_en_mantenimiento=en_mant,
        total_personal=total_p, conductores_activos=conductores, mecanicos=mecanicos,
        ordenes_abiertas=ordenes_abiertas, ordenes_en_proceso=ordenes_proceso,
        documentos_vencidos=docs_vencidos, documentos_por_vencer=docs_por_vencer,
        litros_mes_actual=round(litros, 2), costo_combustible_mes=round(costo_comb, 2),
        costo_mantenimiento_mes=round(costo_mant, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REPUESTOS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/repuestos/", response_model=List[FlotaRepuestoResponse])
async def listar_repuestos(
    categoria: Optional[str] = None, activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user),
):
    q = select(FlotaRepuesto).order_by(FlotaRepuesto.codigo)
    if categoria: q = q.where(FlotaRepuesto.categoria == categoria)
    if activo is not None: q = q.where(FlotaRepuesto.activo == activo)
    return (await db.execute(q)).scalars().all()

@router.post("/repuestos/", response_model=FlotaRepuestoResponse, status_code=201)
async def crear_repuesto(data: FlotaRepuestoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaRepuesto(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/repuestos/{id}", response_model=FlotaRepuestoResponse)
async def actualizar_repuesto(id: int, data: FlotaRepuestoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaRepuesto, id)
    if not obj: raise HTTPException(404, "Repuesto no encontrado")
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/repuestos/{id}", status_code=204)
async def eliminar_repuesto(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaRepuesto, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# RUTINAS DE MANTENIMIENTO
# ═══════════════════════════════════════════════════════════════════════════════

def _rutina_to_response(r: FlotaRutinaMantenimiento) -> FlotaRutinaResponse:
    trabajos_resp = [
        FlotaRutinaTrabajoResponse(
            id=t.id, rutina_id=t.rutina_id, tipo_trabajo_id=t.tipo_trabajo_id,
            tipo_trabajo_nombre=t.tipo_trabajo.nombre if t.tipo_trabajo else None,
            orden=t.orden, obligatorio=t.obligatorio, instrucciones=t.instrucciones,
        ) for t in (r.trabajos or [])
    ]
    repuestos_resp = [
        FlotaRutinaRepuestoResponse(
            id=rp.id, rutina_id=rp.rutina_id, repuesto_id=rp.repuesto_id,
            repuesto_codigo=rp.repuesto.codigo if rp.repuesto else None,
            repuesto_nombre=rp.repuesto.nombre if rp.repuesto else None,
            repuesto_unidad=rp.repuesto.unidad if rp.repuesto else None,
            costo_referencia=rp.repuesto.costo_referencia if rp.repuesto else None,
            cantidad=rp.cantidad, obligatorio=rp.obligatorio,
        ) for rp in (r.repuestos or [])
    ]
    return FlotaRutinaResponse(
        id=r.id, codigo=r.codigo, nombre=r.nombre, descripcion=r.descripcion,
        tipo=r.tipo, nivel_criticidad=r.nivel_criticidad,
        aplica_tipo_trabajo_severo=r.aplica_tipo_trabajo_severo,
        intervalo_km=r.intervalo_km, intervalo_horas=r.intervalo_horas,
        intervalo_dias=r.intervalo_dias, tolerancia_pct=r.tolerancia_pct,
        tiempo_estimado_horas=r.tiempo_estimado_horas,
        costo_estimado_mano_obra=r.costo_estimado_mano_obra,
        instrucciones_generales=r.instrucciones_generales, activo=r.activo,
        trabajos=trabajos_resp, repuestos=repuestos_resp,
    )


@router.get("/rutinas/", response_model=List[FlotaRutinaResponse])
async def listar_rutinas(
    tipo: Optional[str] = None, activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user),
):
    q = (
        select(FlotaRutinaMantenimiento)
        .options(
            selectinload(FlotaRutinaMantenimiento.trabajos).selectinload(FlotaRutinaDetalleTrabajo.tipo_trabajo),
            selectinload(FlotaRutinaMantenimiento.repuestos).selectinload(FlotaRutinaDetalleRepuesto.repuesto),
        )
        .where(FlotaRutinaMantenimiento.deleted_at == None)
        .order_by(FlotaRutinaMantenimiento.codigo)
    )
    if tipo: q = q.where(FlotaRutinaMantenimiento.tipo == tipo)
    if activo is not None: q = q.where(FlotaRutinaMantenimiento.activo == activo)
    rows = (await db.execute(q)).scalars().all()
    return [_rutina_to_response(r) for r in rows]


@router.get("/rutinas/{id}", response_model=FlotaRutinaResponse)
async def obtener_rutina(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = (
        select(FlotaRutinaMantenimiento)
        .options(
            selectinload(FlotaRutinaMantenimiento.trabajos).selectinload(FlotaRutinaDetalleTrabajo.tipo_trabajo),
            selectinload(FlotaRutinaMantenimiento.repuestos).selectinload(FlotaRutinaDetalleRepuesto.repuesto),
        )
        .where(FlotaRutinaMantenimiento.id == id, FlotaRutinaMantenimiento.deleted_at == None)
    )
    r = (await db.execute(q)).scalar_one_or_none()
    if not r: raise HTTPException(404, "Rutina no encontrada")
    return _rutina_to_response(r)


@router.post("/rutinas/", response_model=FlotaRutinaResponse, status_code=201)
async def crear_rutina(data: FlotaRutinaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    payload = data.model_dump(exclude={"trabajos", "repuestos"})
    obj = FlotaRutinaMantenimiento(**payload)
    db.add(obj)
    await db.flush()
    for t in data.trabajos:
        db.add(FlotaRutinaDetalleTrabajo(rutina_id=obj.id, **t.model_dump()))
    for rp in data.repuestos:
        db.add(FlotaRutinaDetalleRepuesto(rutina_id=obj.id, **rp.model_dump()))
    await db.commit()
    return await obtener_rutina(obj.id, db, _)


@router.put("/rutinas/{id}", response_model=FlotaRutinaResponse)
async def actualizar_rutina(id: int, data: FlotaRutinaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaRutinaMantenimiento, id)
    if not obj: raise HTTPException(404)
    payload = data.model_dump(exclude={"trabajos", "repuestos"}, exclude_none=True)
    for k, v in payload.items(): setattr(obj, k, v)
    if data.trabajos is not None:
        await db.execute(select(FlotaRutinaDetalleTrabajo).where(FlotaRutinaDetalleTrabajo.rutina_id == id))
        existing_t = (await db.execute(select(FlotaRutinaDetalleTrabajo).where(FlotaRutinaDetalleTrabajo.rutina_id == id))).scalars().all()
        for t in existing_t: await db.delete(t)
        for t in data.trabajos: db.add(FlotaRutinaDetalleTrabajo(rutina_id=id, **t.model_dump()))
    if data.repuestos is not None:
        existing_r = (await db.execute(select(FlotaRutinaDetalleRepuesto).where(FlotaRutinaDetalleRepuesto.rutina_id == id))).scalars().all()
        for rp in existing_r: await db.delete(rp)
        for rp in data.repuestos: db.add(FlotaRutinaDetalleRepuesto(rutina_id=id, **rp.model_dump()))
    await db.commit()
    return await obtener_rutina(id, db, _)


@router.delete("/rutinas/{id}", status_code=204)
async def eliminar_rutina(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from datetime import datetime
    obj = await db.get(FlotaRutinaMantenimiento, id)
    if not obj: raise HTTPException(404)
    obj.deleted_at = datetime.utcnow(); await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# SECUENCIAS DE MANTENIMIENTO
# ═══════════════════════════════════════════════════════════════════════════════

def _secuencia_to_response(s: FlotaSecuenciaMantenimiento) -> FlotaSecuenciaResponse:
    rutinas_resp = [
        FlotaSecuenciaRutinaResponse(
            id=sr.id, secuencia_id=sr.secuencia_id, rutina_id=sr.rutina_id,
            rutina_codigo=sr.rutina.codigo if sr.rutina else None,
            rutina_nombre=sr.rutina.nombre if sr.rutina else None,
            orden=sr.orden,
            intervalo_km_override=sr.intervalo_km_override,
            intervalo_dias_override=sr.intervalo_dias_override,
            notas=sr.notas,
        ) for sr in (s.rutinas or [])
    ]
    return FlotaSecuenciaResponse(
        id=s.id, codigo=s.codigo, nombre=s.nombre, descripcion=s.descripcion,
        aplica_tipo_trabajo=s.aplica_tipo_trabajo, activo=s.activo,
        rutinas=rutinas_resp,
        total_asignaciones=len(s.asignaciones) if s.asignaciones else 0,
    )


@router.get("/secuencias/", response_model=List[FlotaSecuenciaResponse])
async def listar_secuencias(
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user),
):
    q = (
        select(FlotaSecuenciaMantenimiento)
        .options(
            selectinload(FlotaSecuenciaMantenimiento.rutinas).selectinload(FlotaSecuenciaRutina.rutina),
            selectinload(FlotaSecuenciaMantenimiento.asignaciones),
        )
        .where(FlotaSecuenciaMantenimiento.deleted_at == None)
        .order_by(FlotaSecuenciaMantenimiento.codigo)
    )
    if activo is not None: q = q.where(FlotaSecuenciaMantenimiento.activo == activo)
    rows = (await db.execute(q)).scalars().all()
    return [_secuencia_to_response(s) for s in rows]


@router.get("/secuencias/{id}", response_model=FlotaSecuenciaResponse)
async def obtener_secuencia(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = (
        select(FlotaSecuenciaMantenimiento)
        .options(
            selectinload(FlotaSecuenciaMantenimiento.rutinas).selectinload(FlotaSecuenciaRutina.rutina),
            selectinload(FlotaSecuenciaMantenimiento.asignaciones),
        )
        .where(FlotaSecuenciaMantenimiento.id == id, FlotaSecuenciaMantenimiento.deleted_at == None)
    )
    s = (await db.execute(q)).scalar_one_or_none()
    if not s: raise HTTPException(404, "Secuencia no encontrada")
    return _secuencia_to_response(s)


@router.post("/secuencias/", response_model=FlotaSecuenciaResponse, status_code=201)
async def crear_secuencia(data: FlotaSecuenciaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    payload = data.model_dump(exclude={"rutinas"})
    obj = FlotaSecuenciaMantenimiento(**payload)
    db.add(obj); await db.flush()
    for r in data.rutinas:
        db.add(FlotaSecuenciaRutina(secuencia_id=obj.id, **r.model_dump()))
    await db.commit()
    return await obtener_secuencia(obj.id, db, _)


@router.put("/secuencias/{id}", response_model=FlotaSecuenciaResponse)
async def actualizar_secuencia(id: int, data: FlotaSecuenciaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaSecuenciaMantenimiento, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude={"rutinas"}, exclude_none=True).items(): setattr(obj, k, v)
    if data.rutinas is not None:
        existing = (await db.execute(select(FlotaSecuenciaRutina).where(FlotaSecuenciaRutina.secuencia_id == id))).scalars().all()
        for e in existing: await db.delete(e)
        for r in data.rutinas: db.add(FlotaSecuenciaRutina(secuencia_id=id, **r.model_dump()))
    await db.commit()
    return await obtener_secuencia(id, db, _)


@router.delete("/secuencias/{id}", status_code=204)
async def eliminar_secuencia(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from datetime import datetime
    obj = await db.get(FlotaSecuenciaMantenimiento, id)
    if not obj: raise HTTPException(404)
    obj.deleted_at = datetime.utcnow(); await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# GRUPOS DE VEHÍCULOS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/grupos-vehiculo/", response_model=List[FlotaGrupoResponse])
async def listar_grupos(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = (
        select(FlotaGrupoVehiculo)
        .options(selectinload(FlotaGrupoVehiculo.tipo_vehiculo), selectinload(FlotaGrupoVehiculo.marca))
        .order_by(FlotaGrupoVehiculo.nombre)
    )
    grupos = (await db.execute(q)).scalars().all()
    result = []
    for g in grupos:
        # Contar vehículos que coinciden con los filtros del grupo
        vq = select(func.count(FlotaVehiculo.id)).where(FlotaVehiculo.deleted_at == None, FlotaVehiculo.activo == True)
        if g.tipo_vehiculo_id: vq = vq.where(FlotaVehiculo.tipo_vehiculo_id == g.tipo_vehiculo_id)
        if g.marca_id: vq = vq.where(FlotaVehiculo.marca_id == g.marca_id)
        if g.tipo_trabajo_filtro: vq = vq.where(FlotaVehiculo.tipo_trabajo == g.tipo_trabajo_filtro)
        if g.ciudad: vq = vq.where(FlotaVehiculo.ciudad == g.ciudad)
        count = (await db.execute(vq)).scalar() or 0
        result.append(FlotaGrupoResponse(
            id=g.id, nombre=g.nombre, descripcion=g.descripcion,
            tipo_vehiculo_id=g.tipo_vehiculo_id,
            tipo_vehiculo_nombre=g.tipo_vehiculo.nombre if g.tipo_vehiculo else None,
            marca_id=g.marca_id,
            marca_nombre=g.marca.nombre if g.marca else None,
            tipo_trabajo_filtro=g.tipo_trabajo_filtro, ciudad=g.ciudad, activo=g.activo,
            vehiculos_count=count,
        ))
    return result


@router.post("/grupos-vehiculo/", response_model=FlotaGrupoResponse, status_code=201)
async def crear_grupo(data: FlotaGrupoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaGrupoVehiculo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return (await listar_grupos(db, _))[-1]  # Re-fetch with count


@router.put("/grupos-vehiculo/{id}", response_model=FlotaGrupoResponse)
async def actualizar_grupo(id: int, data: FlotaGrupoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaGrupoVehiculo, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit()
    grupos = await listar_grupos(db, _)
    return next(g for g in grupos if g.id == id)


@router.delete("/grupos-vehiculo/{id}", status_code=204)
async def eliminar_grupo(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaGrupoVehiculo, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# ASIGNACIONES DE SECUENCIAS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/asignaciones/", response_model=List[FlotaAsignacionResponse])
async def listar_asignaciones(
    vehiculo_id: Optional[int] = None, secuencia_id: Optional[int] = None,
    activa: Optional[bool] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user),
):
    q = (
        select(FlotaAsignacionSecuencia)
        .options(
            selectinload(FlotaAsignacionSecuencia.secuencia),
            selectinload(FlotaAsignacionSecuencia.vehiculo),
            selectinload(FlotaAsignacionSecuencia.grupo),
        )
        .order_by(FlotaAsignacionSecuencia.fecha_inicio.desc())
    )
    if vehiculo_id: q = q.where(FlotaAsignacionSecuencia.vehiculo_id == vehiculo_id)
    if secuencia_id: q = q.where(FlotaAsignacionSecuencia.secuencia_id == secuencia_id)
    if activa is not None: q = q.where(FlotaAsignacionSecuencia.activa == activa)
    rows = (await db.execute(q)).scalars().all()
    return [FlotaAsignacionResponse(
        id=a.id, secuencia_id=a.secuencia_id,
        secuencia_nombre=a.secuencia.nombre if a.secuencia else None,
        vehiculo_id=a.vehiculo_id,
        vehiculo_placa=a.vehiculo.placa if a.vehiculo else None,
        grupo_id=a.grupo_id,
        grupo_nombre=a.grupo.nombre if a.grupo else None,
        fecha_inicio=a.fecha_inicio, medicion_inicio=a.medicion_inicio,
        activa=a.activa, notas=a.notas,
    ) for a in rows]


@router.post("/asignaciones/", response_model=FlotaAsignacionResponse, status_code=201)
async def crear_asignacion(data: FlotaAsignacionCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    if not data.vehiculo_id and not data.grupo_id:
        raise HTTPException(400, "Debe especificar vehiculo_id o grupo_id")
    obj = FlotaAsignacionSecuencia(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return (await listar_asignaciones(db=db, _=_))[0]


@router.patch("/asignaciones/{id}", response_model=FlotaAsignacionResponse)
async def actualizar_asignacion(id: int, data: FlotaAsignacionUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaAsignacionSecuencia, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit()
    rows = await listar_asignaciones(db=db, _=_)
    return next(r for r in rows if r.id == id)


@router.delete("/asignaciones/{id}", status_code=204)
async def eliminar_asignacion(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaAsignacionSecuencia, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# FMEA — MODOS DE FALLA
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/modos-falla/", response_model=List[FlotaModoFallaResponse])
async def listar_modos_falla(
    sistema: Optional[str] = None, tipo_vehiculo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user),
):
    q = (
        select(FlotaModoFalla)
        .options(selectinload(FlotaModoFalla.rutina_correctiva))
        .where(FlotaModoFalla.activo == True)
        .order_by(FlotaModoFalla.rpn.desc().nullslast(), FlotaModoFalla.sistema)
    )
    if sistema: q = q.where(FlotaModoFalla.sistema == sistema)
    if tipo_vehiculo_id: q = q.where(FlotaModoFalla.tipo_vehiculo_id == tipo_vehiculo_id)
    rows = (await db.execute(q)).scalars().all()
    return [FlotaModoFallaResponse(
        id=m.id, sistema=m.sistema, subsistema=m.subsistema, funcion=m.funcion,
        falla_funcional=m.falla_funcional, modo_falla=m.modo_falla,
        efecto=m.efecto, causa=m.causa,
        severidad=m.severidad, ocurrencia=m.ocurrencia, deteccion=m.deteccion, rpn=m.rpn,
        accion_recomendada=m.accion_recomendada,
        tipo_vehiculo_id=m.tipo_vehiculo_id,
        rutina_correctiva_id=m.rutina_correctiva_id,
        rutina_nombre=m.rutina_correctiva.nombre if m.rutina_correctiva else None,
        activo=m.activo,
    ) for m in rows]


@router.post("/modos-falla/", response_model=FlotaModoFallaResponse, status_code=201)
async def crear_modo_falla(data: FlotaModoFallaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    payload = data.model_dump()
    s, o, d = payload.get("severidad"), payload.get("ocurrencia"), payload.get("deteccion")
    payload["rpn"] = s * o * d if s and o and d else None
    obj = FlotaModoFalla(**payload)
    db.add(obj); await db.commit(); await db.refresh(obj)
    rows = await listar_modos_falla(db=db, _=_)
    return next(r for r in rows if r.id == obj.id)


@router.put("/modos-falla/{id}", response_model=FlotaModoFallaResponse)
async def actualizar_modo_falla(id: int, data: FlotaModoFallaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaModoFalla, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    s, o, d = obj.severidad, obj.ocurrencia, obj.deteccion
    obj.rpn = s * o * d if s and o and d else None
    await db.commit()
    rows = await listar_modos_falla(db=db, _=_)
    return next(r for r in rows if r.id == id)


@router.delete("/modos-falla/{id}", status_code=204)
async def eliminar_modo_falla(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaModoFalla, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# CBM — UMBRALES DE CONDICIÓN
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/umbrales-cbm/", response_model=List[FlotaUmbralCBMResponse])
async def listar_umbrales(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = (
        select(FlotaUmbralCBM)
        .options(
            selectinload(FlotaUmbralCBM.vehiculo),
            selectinload(FlotaUmbralCBM.tipo_vehiculo),
            selectinload(FlotaUmbralCBM.rutina_trigger),
        )
        .where(FlotaUmbralCBM.activo == True)
        .order_by(FlotaUmbralCBM.parametro)
    )
    rows = (await db.execute(q)).scalars().all()
    return [FlotaUmbralCBMResponse(
        id=u.id, parametro=u.parametro, descripcion=u.descripcion, unidad=u.unidad,
        umbral_advertencia=u.umbral_advertencia, umbral_critico=u.umbral_critico,
        direccion=u.direccion,
        vehiculo_id=u.vehiculo_id, vehiculo_placa=u.vehiculo.placa if u.vehiculo else None,
        tipo_vehiculo_id=u.tipo_vehiculo_id,
        tipo_vehiculo_nombre=u.tipo_vehiculo.nombre if u.tipo_vehiculo else None,
        rutina_trigger_id=u.rutina_trigger_id,
        rutina_nombre=u.rutina_trigger.nombre if u.rutina_trigger else None,
        activo=u.activo,
    ) for u in rows]


@router.post("/umbrales-cbm/", response_model=FlotaUmbralCBMResponse, status_code=201)
async def crear_umbral(data: FlotaUmbralCBMCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = FlotaUmbralCBM(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    rows = await listar_umbrales(db, _)
    return next(r for r in rows if r.id == obj.id)


@router.put("/umbrales-cbm/{id}", response_model=FlotaUmbralCBMResponse)
async def actualizar_umbral(id: int, data: FlotaUmbralCBMUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaUmbralCBM, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit()
    rows = await listar_umbrales(db, _)
    return next(r for r in rows if r.id == id)


@router.delete("/umbrales-cbm/{id}", status_code=204)
async def eliminar_umbral(id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(FlotaUmbralCBM, id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# PRÓXIMOS MANTENIMIENTOS — Motor predictivo
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/proximos-mantenimientos/", response_model=List[FlotaProximoMantenimiento])
async def proximos_mantenimientos(
    vehiculo_id: Optional[int] = None,
    solo_vencidos: bool = False,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Calcula el estado de próximos mantenimientos para cada vehículo con
    secuencias asignadas. Compara la medición actual vs intervalo de cada rutina.
    """
    hoy = date.today()

    # Traer asignaciones activas con sus secuencias → rutinas
    asig_q = (
        select(FlotaAsignacionSecuencia)
        .options(
            selectinload(FlotaAsignacionSecuencia.secuencia).selectinload(
                FlotaSecuenciaMantenimiento.rutinas
            ).selectinload(FlotaSecuenciaRutina.rutina),
            selectinload(FlotaAsignacionSecuencia.vehiculo),
            selectinload(FlotaAsignacionSecuencia.grupo),
        )
        .where(FlotaAsignacionSecuencia.activa == True)
    )
    if vehiculo_id:
        asig_q = asig_q.where(FlotaAsignacionSecuencia.vehiculo_id == vehiculo_id)
    asignaciones = (await db.execute(asig_q)).scalars().all()

    # Mediciones actuales por vehículo
    med_q = (
        select(FlotaMedicion.vehiculo_id, func.max(FlotaMedicion.valor).label("ultima"))
        .where(FlotaMedicion.tipo == "ODOMETRO")
        .group_by(FlotaMedicion.vehiculo_id)
    )
    mediciones_map: dict[int, float] = {
        row.vehiculo_id: row.ultima
        for row in (await db.execute(med_q)).all()
    }

    # Última OT cerrada por vehículo+rutina para calcular offset
    ot_q = (
        select(FlotaOrdenTrabajo.vehiculo_id, FlotaOrdenTrabajo.medicion_apertura, FlotaOrdenTrabajo.fecha_apertura)
        .where(FlotaOrdenTrabajo.estado.in_(["CERRADA", "EN_PROCESO"]), FlotaOrdenTrabajo.deleted_at == None)
        .order_by(FlotaOrdenTrabajo.medicion_apertura.desc().nullslast())
    )

    result: list[FlotaProximoMantenimiento] = []

    for asig in asignaciones:
        veh = asig.vehiculo
        if not veh:
            continue

        med_actual = mediciones_map.get(veh.id)
        base_km = asig.medicion_inicio or 0
        base_fecha = asig.fecha_inicio

        for sr in (asig.secuencia.rutinas if asig.secuencia else []):
            rutina = sr.rutina
            if not rutina or not rutina.activo:
                continue

            int_km = sr.intervalo_km_override or rutina.intervalo_km
            int_dias = sr.intervalo_dias_override or rutina.intervalo_dias

            km_rest: Optional[float] = None
            dias_rest: Optional[int] = None
            vencido = False

            if int_km and med_actual is not None:
                prox_km = base_km + int_km
                km_rest = prox_km - med_actual
                if km_rest <= 0:
                    vencido = True

            if int_dias:
                prox_fecha = base_fecha + timedelta(days=int_dias)
                dias_rest = (prox_fecha - hoy).days
                if dias_rest <= 0:
                    vencido = True

            if solo_vencidos and not vencido:
                continue

            result.append(FlotaProximoMantenimiento(
                vehiculo_id=veh.id, vehiculo_placa=veh.placa,
                rutina_id=rutina.id, rutina_codigo=rutina.codigo, rutina_nombre=rutina.nombre,
                secuencia_nombre=asig.secuencia.nombre if asig.secuencia else None,
                tipo=rutina.tipo, nivel_criticidad=rutina.nivel_criticidad,
                medicion_actual=med_actual,
                intervalo_km=int_km, km_restantes=km_rest,
                intervalo_dias=int_dias, dias_restantes=dias_rest,
                vencido=vencido,
            ))

    result.sort(key=lambda x: (not x.vencido, x.km_restantes or 999999))
    return result
