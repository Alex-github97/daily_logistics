from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor, require_operador
from app.infrastructure.models.usuario import Usuario, RolUsuario
from app.infrastructure.models.vehiculo import Conductor
from app.infrastructure.models.flete import (
    GeneradorCarga, VehiculoFlete, Flete, Enturnamiento,
    EstadoFlete, EstadoEnturnamiento,
)
from app.application.schemas.flete import (
    GeneradorCargaCreate, GeneradorCargaUpdate, GeneradorCargaResponse,
    VehiculoFleteCreate, VehiculoFleteUpdate, VehiculoFleteResponse,
    FleteCreate, FleteUpdate, FleteAsignar, FleteResponse,
    EnturnamientoCreate, EnturnamientoAsignar, EnturnamientoResponse,
    ConductorBrief, ConductorConVehiculos,
)

router = APIRouter(prefix="/fletes", tags=["Fletes"])


def _require_conductor_or_above(current_user: Usuario) -> None:
    allowed = [
        RolUsuario.ADMINISTRADOR, RolUsuario.SUPERVISOR_LOGISTICO,
        RolUsuario.OPERADOR_BODEGA, RolUsuario.CONDUCTOR,
    ]
    if current_user.rol not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")


# ── Conductores ───────────────────────────────────────────────────────────────

@router.get("/conductores/", response_model=List[ConductorBrief])
async def listar_conductores(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Lista todos los conductores activos con su enlace a usuario."""
    result = await db.execute(
        select(Conductor).where(Conductor.activo == True).order_by(Conductor.nombre)
    )
    conductores = result.scalars().all()
    return [
        ConductorBrief(
            id=c.id,
            nombre=c.nombre,
            apellido=c.apellido,
            cedula=c.cedula,
            telefono=c.telefono,
            usuario_id=c.usuario_id,
        )
        for c in conductores
    ]


@router.get("/conductores/{conductor_id}/vehiculos", response_model=List[VehiculoFleteResponse])
async def vehiculos_de_conductor(
    conductor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(VehiculoFlete)
        .where(and_(VehiculoFlete.conductor_id == conductor_id, VehiculoFlete.activo == True))
        .order_by(VehiculoFlete.placa)
    )
    vehiculos = result.scalars().all()
    conductor = await db.get(Conductor, conductor_id)
    nombre_conductor = f"{conductor.nombre} {conductor.apellido}" if conductor else None
    return [
        VehiculoFleteResponse(
            **{c: getattr(v, c) for c in ["id", "conductor_id", "placa", "tipo_vehiculo",
               "tipo_carroceria", "marca", "modelo", "anio", "capacidad_kg", "observaciones",
               "activo", "created_at"]},
            conductor_nombre=nombre_conductor,
        )
        for v in vehiculos
    ]


# ── Vehículos Flete ───────────────────────────────────────────────────────────

@router.get("/vehiculos/", response_model=List[VehiculoFleteResponse])
async def listar_vehiculos_flete(
    conductor_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _require_conductor_or_above(current_user)
    query = select(VehiculoFlete).where(VehiculoFlete.activo == True)
    if conductor_id:
        query = query.where(VehiculoFlete.conductor_id == conductor_id)
    result = await db.execute(query.order_by(VehiculoFlete.placa))
    vehiculos = result.scalars().all()
    out = []
    for v in vehiculos:
        conductor = await db.get(Conductor, v.conductor_id)
        out.append(VehiculoFleteResponse(
            id=v.id,
            conductor_id=v.conductor_id,
            placa=v.placa,
            tipo_vehiculo=v.tipo_vehiculo,
            tipo_carroceria=v.tipo_carroceria,
            marca=v.marca,
            modelo=v.modelo,
            anio=v.anio,
            capacidad_kg=v.capacidad_kg,
            observaciones=v.observaciones,
            activo=v.activo,
            created_at=v.created_at,
            conductor_nombre=f"{conductor.nombre} {conductor.apellido}" if conductor else None,
        ))
    return out


@router.post("/vehiculos/", response_model=VehiculoFleteResponse, status_code=status.HTTP_201_CREATED)
async def crear_vehiculo_flete(
    data: VehiculoFleteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _require_conductor_or_above(current_user)
    conductor = await db.get(Conductor, data.conductor_id)
    if not conductor or not conductor.activo:
        raise HTTPException(status_code=404, detail="Conductor no encontrado")
    vehiculo = VehiculoFlete(**data.model_dump())
    db.add(vehiculo)
    await db.flush()
    await db.refresh(vehiculo)
    return VehiculoFleteResponse(
        **{c: getattr(vehiculo, c) for c in ["id", "conductor_id", "placa", "tipo_vehiculo",
           "tipo_carroceria", "marca", "modelo", "anio", "capacidad_kg", "observaciones",
           "activo", "created_at"]},
        conductor_nombre=f"{conductor.nombre} {conductor.apellido}",
    )


@router.put("/vehiculos/{vehiculo_id}", response_model=VehiculoFleteResponse)
async def actualizar_vehiculo_flete(
    vehiculo_id: int,
    data: VehiculoFleteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _require_conductor_or_above(current_user)
    vehiculo = await db.get(VehiculoFlete, vehiculo_id)
    if not vehiculo or not vehiculo.activo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(vehiculo, field, value)
    await db.flush()
    conductor = await db.get(Conductor, vehiculo.conductor_id)
    return VehiculoFleteResponse(
        **{c: getattr(vehiculo, c) for c in ["id", "conductor_id", "placa", "tipo_vehiculo",
           "tipo_carroceria", "marca", "modelo", "anio", "capacidad_kg", "observaciones",
           "activo", "created_at"]},
        conductor_nombre=f"{conductor.nombre} {conductor.apellido}" if conductor else None,
    )


@router.delete("/vehiculos/{vehiculo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_vehiculo_flete(
    vehiculo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    vehiculo = await db.get(VehiculoFlete, vehiculo_id)
    if not vehiculo or not vehiculo.activo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    vehiculo.activo = False


# ── Generadores de Carga ──────────────────────────────────────────────────────

@router.get("/generadores/", response_model=List[GeneradorCargaResponse])
async def listar_generadores(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(GeneradorCarga).where(GeneradorCarga.activo == True).order_by(GeneradorCarga.nombre)
    )
    return result.scalars().all()


@router.post("/generadores/", response_model=GeneradorCargaResponse, status_code=status.HTTP_201_CREATED)
async def crear_generador(
    data: GeneradorCargaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    generador = GeneradorCarga(**data.model_dump())
    db.add(generador)
    await db.flush()
    await db.refresh(generador)
    return generador


@router.put("/generadores/{generador_id}", response_model=GeneradorCargaResponse)
async def actualizar_generador(
    generador_id: int,
    data: GeneradorCargaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    generador = await db.get(GeneradorCarga, generador_id)
    if not generador or not generador.activo:
        raise HTTPException(status_code=404, detail="Generador de carga no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(generador, field, value)
    await db.flush()
    return generador


@router.delete("/generadores/{generador_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_generador(
    generador_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    generador = await db.get(GeneradorCarga, generador_id)
    if not generador or not generador.activo:
        raise HTTPException(status_code=404, detail="Generador de carga no encontrado")
    generador.activo = False


# ── Fletes ────────────────────────────────────────────────────────────────────

def _flete_to_response(flete: Flete, generador: GeneradorCarga = None,
                        conductor: Conductor = None, vehiculo: VehiculoFlete = None) -> FleteResponse:
    return FleteResponse(
        id=flete.id,
        ciudad_origen=flete.ciudad_origen,
        ciudad_destino=flete.ciudad_destino,
        tipo_vehiculo=flete.tipo_vehiculo,
        tipo_carroceria=flete.tipo_carroceria,
        generador_id=flete.generador_id,
        descripcion_carga=flete.descripcion_carga,
        peso_kg=flete.peso_kg,
        num_entregas=flete.num_entregas,
        distancia_km=flete.distancia_km,
        fecha_hora_cargue=flete.fecha_hora_cargue,
        fecha_hora_entrega=flete.fecha_hora_entrega,
        valor_flete=flete.valor_flete,
        es_negociable=flete.es_negociable,
        estado=flete.estado,
        conductor_id=flete.conductor_id,
        vehiculo_flete_id=flete.vehiculo_flete_id,
        notas=flete.notas,
        creado_por_id=flete.creado_por_id,
        activo=flete.activo,
        created_at=flete.created_at,
        generador_nombre=generador.nombre if generador else None,
        conductor_nombre=f"{conductor.nombre} {conductor.apellido}" if conductor else None,
        vehiculo_placa=vehiculo.placa if vehiculo else None,
    )


@router.get("/", response_model=List[FleteResponse])
async def listar_fletes(
    estado: Optional[str] = Query(None),
    tipo_vehiculo: Optional[str] = Query(None),
    ciudad_origen: Optional[str] = Query(None),
    ciudad_destino: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Flete).where(Flete.activo == True)
    if estado:
        query = query.where(Flete.estado == estado)
    if tipo_vehiculo:
        query = query.where(Flete.tipo_vehiculo == tipo_vehiculo)
    if ciudad_origen:
        query = query.where(Flete.ciudad_origen.ilike(f"%{ciudad_origen}%"))
    if ciudad_destino:
        query = query.where(Flete.ciudad_destino.ilike(f"%{ciudad_destino}%"))

    # Si es conductor, solo ve sus propios fletes
    if current_user.rol == RolUsuario.CONDUCTOR:
        conductor_result = await db.execute(
            select(Conductor).where(Conductor.usuario_id == current_user.id)
        )
        conductor = conductor_result.scalar_one_or_none()
        if conductor:
            query = query.where(Flete.conductor_id == conductor.id)
        else:
            return []

    result = await db.execute(query.order_by(Flete.fecha_hora_cargue.desc()))
    fletes = result.scalars().all()
    out = []
    for f in fletes:
        generador = await db.get(GeneradorCarga, f.generador_id) if f.generador_id else None
        conductor = await db.get(Conductor, f.conductor_id) if f.conductor_id else None
        vehiculo = await db.get(VehiculoFlete, f.vehiculo_flete_id) if f.vehiculo_flete_id else None
        out.append(_flete_to_response(f, generador, conductor, vehiculo))
    return out


@router.get("/{flete_id}", response_model=FleteResponse)
async def obtener_flete(
    flete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    flete = await db.get(Flete, flete_id)
    if not flete or not flete.activo:
        raise HTTPException(status_code=404, detail="Flete no encontrado")
    generador = await db.get(GeneradorCarga, flete.generador_id) if flete.generador_id else None
    conductor = await db.get(Conductor, flete.conductor_id) if flete.conductor_id else None
    vehiculo = await db.get(VehiculoFlete, flete.vehiculo_flete_id) if flete.vehiculo_flete_id else None
    return _flete_to_response(flete, generador, conductor, vehiculo)


@router.post("/", response_model=FleteResponse, status_code=status.HTTP_201_CREATED)
async def crear_flete(
    data: FleteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    flete = Flete(**data.model_dump(), creado_por_id=current_user.id)
    db.add(flete)
    await db.flush()
    await db.refresh(flete)
    generador = await db.get(GeneradorCarga, flete.generador_id) if flete.generador_id else None
    return _flete_to_response(flete, generador)


@router.put("/{flete_id}", response_model=FleteResponse)
async def actualizar_flete(
    flete_id: int,
    data: FleteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    flete = await db.get(Flete, flete_id)
    if not flete or not flete.activo:
        raise HTTPException(status_code=404, detail="Flete no encontrado")
    if flete.estado == EstadoFlete.COMPLETADO.value:
        raise HTTPException(status_code=400, detail="No se puede modificar un flete completado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(flete, field, value)
    await db.flush()
    generador = await db.get(GeneradorCarga, flete.generador_id) if flete.generador_id else None
    conductor = await db.get(Conductor, flete.conductor_id) if flete.conductor_id else None
    vehiculo = await db.get(VehiculoFlete, flete.vehiculo_flete_id) if flete.vehiculo_flete_id else None
    return _flete_to_response(flete, generador, conductor, vehiculo)


@router.patch("/{flete_id}/asignar", response_model=FleteResponse)
async def asignar_conductor_a_flete(
    flete_id: int,
    data: FleteAsignar,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    flete = await db.get(Flete, flete_id)
    if not flete or not flete.activo:
        raise HTTPException(status_code=404, detail="Flete no encontrado")
    if flete.estado not in [EstadoFlete.PENDIENTE.value, EstadoFlete.ASIGNADO.value]:
        raise HTTPException(status_code=400, detail="Solo se pueden asignar fletes en estado PENDIENTE o ASIGNADO")

    conductor = await db.get(Conductor, data.conductor_id)
    if not conductor or not conductor.activo:
        raise HTTPException(status_code=404, detail="Conductor no encontrado")

    vehiculo = await db.get(VehiculoFlete, data.vehiculo_flete_id)
    if not vehiculo or not vehiculo.activo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    if vehiculo.conductor_id != data.conductor_id:
        raise HTTPException(status_code=400, detail="El vehículo no pertenece al conductor seleccionado")

    flete.conductor_id = data.conductor_id
    flete.vehiculo_flete_id = data.vehiculo_flete_id
    flete.estado = EstadoFlete.ASIGNADO.value

    # Si hay enturnamiento activo para este conductor, marcarlo como asignado
    enturnamiento_result = await db.execute(
        select(Enturnamiento).where(
            and_(
                Enturnamiento.conductor_id == data.conductor_id,
                Enturnamiento.estado == EstadoEnturnamiento.ACTIVO.value,
                Enturnamiento.activo == True,
            )
        )
    )
    enturnamiento = enturnamiento_result.scalar_one_or_none()
    if enturnamiento:
        enturnamiento.estado = EstadoEnturnamiento.ASIGNADO.value
        enturnamiento.flete_asignado_id = flete_id

    await db.flush()
    generador = await db.get(GeneradorCarga, flete.generador_id) if flete.generador_id else None
    return _flete_to_response(flete, generador, conductor, vehiculo)


@router.patch("/{flete_id}/desasignar", response_model=FleteResponse)
async def desasignar_conductor(
    flete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    flete = await db.get(Flete, flete_id)
    if not flete or not flete.activo:
        raise HTTPException(status_code=404, detail="Flete no encontrado")
    if flete.estado not in [EstadoFlete.ASIGNADO.value]:
        raise HTTPException(status_code=400, detail="Solo se pueden desasignar fletes en estado ASIGNADO")
    flete.conductor_id = None
    flete.vehiculo_flete_id = None
    flete.estado = EstadoFlete.PENDIENTE.value
    await db.flush()
    generador = await db.get(GeneradorCarga, flete.generador_id) if flete.generador_id else None
    return _flete_to_response(flete, generador)


@router.patch("/{flete_id}/estado", response_model=FleteResponse)
async def cambiar_estado_flete(
    flete_id: int,
    estado: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    estados_validos = [e.value for e in EstadoFlete]
    if estado not in estados_validos:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Válidos: {estados_validos}")
    flete = await db.get(Flete, flete_id)
    if not flete or not flete.activo:
        raise HTTPException(status_code=404, detail="Flete no encontrado")
    flete.estado = estado
    await db.flush()
    generador = await db.get(GeneradorCarga, flete.generador_id) if flete.generador_id else None
    conductor = await db.get(Conductor, flete.conductor_id) if flete.conductor_id else None
    vehiculo = await db.get(VehiculoFlete, flete.vehiculo_flete_id) if flete.vehiculo_flete_id else None
    return _flete_to_response(flete, generador, conductor, vehiculo)


@router.delete("/{flete_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_flete(
    flete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    flete = await db.get(Flete, flete_id)
    if not flete or not flete.activo:
        raise HTTPException(status_code=404, detail="Flete no encontrado")
    if flete.estado in [EstadoFlete.EN_CURSO.value]:
        raise HTTPException(status_code=400, detail="No se puede eliminar un flete en curso")
    flete.activo = False


# ── Enturnamiento ─────────────────────────────────────────────────────────────

def _enturnamiento_to_response(e: Enturnamiento, conductor: Conductor = None) -> EnturnamientoResponse:
    return EnturnamientoResponse(
        id=e.id,
        conductor_id=e.conductor_id,
        ciudad_disponible=e.ciudad_disponible,
        fecha_hora_disponible=e.fecha_hora_disponible,
        tipo_vehiculo=e.tipo_vehiculo,
        tipo_carroceria=e.tipo_carroceria,
        notas=e.notas,
        estado=e.estado,
        flete_asignado_id=e.flete_asignado_id,
        activo=e.activo,
        created_at=e.created_at,
        conductor_nombre=f"{conductor.nombre} {conductor.apellido}" if conductor else None,
        conductor_cedula=conductor.cedula if conductor else None,
    )


@router.get("/enturnamiento/", response_model=List[EnturnamientoResponse])
async def listar_enturnamiento(
    estado: Optional[str] = Query(None, description="ACTIVO | ASIGNADO | INACTIVO"),
    tipo_vehiculo: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Enturnamiento).where(Enturnamiento.activo == True)
    if estado:
        query = query.where(Enturnamiento.estado == estado)
    else:
        query = query.where(Enturnamiento.estado == EstadoEnturnamiento.ACTIVO.value)
    if tipo_vehiculo:
        query = query.where(Enturnamiento.tipo_vehiculo == tipo_vehiculo)

    # Conductor solo ve su propio enturnamiento
    if current_user.rol == RolUsuario.CONDUCTOR:
        conductor_result = await db.execute(
            select(Conductor).where(Conductor.usuario_id == current_user.id)
        )
        conductor = conductor_result.scalar_one_or_none()
        if conductor:
            query = query.where(Enturnamiento.conductor_id == conductor.id)
        else:
            return []

    result = await db.execute(query.order_by(Enturnamiento.fecha_hora_disponible))
    enturnados = result.scalars().all()
    out = []
    for e in enturnados:
        conductor = await db.get(Conductor, e.conductor_id)
        out.append(_enturnamiento_to_response(e, conductor))
    return out


@router.post("/enturnamiento/", response_model=EnturnamientoResponse, status_code=status.HTTP_201_CREATED)
async def crear_enturnamiento(
    data: EnturnamientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _require_conductor_or_above(current_user)
    conductor = await db.get(Conductor, data.conductor_id)
    if not conductor or not conductor.activo:
        raise HTTPException(status_code=404, detail="Conductor no encontrado")

    # Verificar que no tenga un enturnamiento activo ya
    existing = await db.execute(
        select(Enturnamiento).where(
            and_(
                Enturnamiento.conductor_id == data.conductor_id,
                Enturnamiento.estado == EstadoEnturnamiento.ACTIVO.value,
                Enturnamiento.activo == True,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="El conductor ya tiene un enturnamiento activo. Inactívelo antes de crear uno nuevo.",
        )

    enturnamiento = Enturnamiento(**data.model_dump())
    db.add(enturnamiento)
    await db.flush()
    await db.refresh(enturnamiento)
    return _enturnamiento_to_response(enturnamiento, conductor)


@router.patch("/enturnamiento/{enturnamiento_id}/inactivar", response_model=EnturnamientoResponse)
async def inactivar_enturnamiento(
    enturnamiento_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _require_conductor_or_above(current_user)
    e = await db.get(Enturnamiento, enturnamiento_id)
    if not e or not e.activo:
        raise HTTPException(status_code=404, detail="Enturnamiento no encontrado")
    e.estado = EstadoEnturnamiento.INACTIVO.value
    await db.flush()
    conductor = await db.get(Conductor, e.conductor_id)
    return _enturnamiento_to_response(e, conductor)


@router.patch("/enturnamiento/{enturnamiento_id}/asignar-flete", response_model=EnturnamientoResponse)
async def asignar_flete_desde_enturnamiento(
    enturnamiento_id: int,
    data: EnturnamientoAsignar,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    e = await db.get(Enturnamiento, enturnamiento_id)
    if not e or not e.activo:
        raise HTTPException(status_code=404, detail="Enturnamiento no encontrado")
    if e.estado != EstadoEnturnamiento.ACTIVO.value:
        raise HTTPException(status_code=400, detail="Solo se puede asignar un enturnamiento en estado ACTIVO")

    flete = await db.get(Flete, data.flete_id)
    if not flete or not flete.activo:
        raise HTTPException(status_code=404, detail="Flete no encontrado")
    if flete.estado != EstadoFlete.PENDIENTE.value:
        raise HTTPException(status_code=400, detail="Solo se pueden asignar fletes en estado PENDIENTE")

    # Buscar el vehículo del conductor para autocompletar
    vehiculo_result = await db.execute(
        select(VehiculoFlete).where(
            and_(VehiculoFlete.conductor_id == e.conductor_id, VehiculoFlete.activo == True)
        ).limit(1)
    )
    vehiculo = vehiculo_result.scalar_one_or_none()

    flete.conductor_id = e.conductor_id
    flete.vehiculo_flete_id = vehiculo.id if vehiculo else None
    flete.estado = EstadoFlete.ASIGNADO.value

    e.estado = EstadoEnturnamiento.ASIGNADO.value
    e.flete_asignado_id = data.flete_id

    await db.flush()
    conductor = await db.get(Conductor, e.conductor_id)
    return _enturnamiento_to_response(e, conductor)
