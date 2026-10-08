from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, Column, Integer, String, Boolean, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import date, datetime, timezone
import json
from app.core.database import get_db, Base
from app.core.dependencies import get_current_user, require_operador, require_supervisor
from app.infrastructure.models.manifiesto import Manifiesto, EstadoManifiesto, ManifiestoHistorial, TipoCambioEstado
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/manifiestos", tags=["Manifiestos"])


async def _detectar_faltantes(db: AsyncSession, manifiesto_id: int, manifiesto_numero: str) -> int:
    """Marca como FALTANTE toda estiba cargada en el manifiesto que no fue descargada, y crea alertas."""
    from sqlalchemy.orm import selectinload
    from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento
    from app.infrastructure.models.estiba import Estiba, EstadoEstiba
    from app.infrastructure.models.alerta import Alerta, TipoAlerta, NivelAlerta

    result = await db.execute(
        select(Movimiento)
        .where(Movimiento.manifiesto_id == manifiesto_id, Movimiento.tipo == TipoMovimiento.CARGA)
        .options(selectinload(Movimiento.estiba))
    )
    faltantes = 0
    for mov in result.scalars().all():
        estiba = mov.estiba
        if not estiba:
            continue
        if estiba.estado in (EstadoEstiba.CARGADA, EstadoEstiba.EN_TRANSITO):
            estiba.estado = EstadoEstiba.FALTANTE
            db.add(Alerta(
                tipo=TipoAlerta.ESTIBA_FALTANTE,
                nivel=NivelAlerta.CRITICA,
                titulo=f"Estiba faltante — manifiesto {manifiesto_numero}",
                descripcion=(
                    f"La estiba {estiba.codigo_interno} estaba cargada en el manifiesto "
                    f"{manifiesto_numero} pero no fue encontrada al cierre del viaje."
                ),
                estiba_id=estiba.id,
                manifiesto_id=manifiesto_id,
            ))
            faltantes += 1
    return faltantes


async def _verificar_stock_minimo(db: AsyncSession, ubicacion_id: int, manifiesto_id: int, manifiesto_numero: str) -> None:
    """Crea alertas STOCK_BAJO para tipos de estiba que caigan bajo el mínimo configurado en esta bodega."""
    from app.infrastructure.models.estiba import Estiba, EstadoEstiba, EstibaStockMinimo
    from app.infrastructure.models.alerta import Alerta, TipoAlerta, NivelAlerta

    configs_r = await db.execute(
        select(EstibaStockMinimo)
        .where(EstibaStockMinimo.ubicacion_id == ubicacion_id, EstibaStockMinimo.activo == True)
    )
    configs = configs_r.scalars().all()
    if not configs:
        return

    # Cargar alertas STOCK_BAJO activas para evitar duplicados
    existing_r = await db.execute(
        select(Alerta).where(Alerta.tipo == TipoAlerta.STOCK_BAJO, Alerta.resuelta == False)
    )
    alerted: set = set()
    for ea in existing_r.scalars().all():
        try:
            m = json.loads(ea.metadatos or '{}')
            alerted.add((m.get('ubicacion_id'), m.get('tipo_estiba')))
        except Exception:
            pass

    for config in configs:
        key = (config.ubicacion_id, config.tipo_estiba.value)
        if key in alerted:
            continue

        count_r = await db.execute(
            select(func.count(Estiba.id)).where(
                Estiba.ubicacion_actual_id == ubicacion_id,
                Estiba.tipo == config.tipo_estiba,
                Estiba.estado == EstadoEstiba.EN_INVENTARIO,
            )
        )
        stock_actual = count_r.scalar_one() or 0

        if stock_actual < config.cantidad_minima:
            db.add(Alerta(
                tipo=TipoAlerta.STOCK_BAJO,
                nivel=NivelAlerta.ADVERTENCIA,
                titulo=f"Stock bajo: estibas {config.tipo_estiba.value} en bodega",
                descripcion=(
                    f"Stock actual: {stock_actual} | Mínimo configurado: {config.cantidad_minima}. "
                    f"Detectado al cargar manifiesto {manifiesto_numero}."
                ),
                manifiesto_id=manifiesto_id,
                metadatos=json.dumps({
                    "ubicacion_id": ubicacion_id,
                    "tipo_estiba":  config.tipo_estiba.value,
                    "stock_actual": stock_actual,
                    "stock_minimo": config.cantidad_minima,
                }),
            ))


class ClienteManifiesto(Base):
    __tablename__ = "clientes_manifiestos"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False, unique=True)
    nit = Column(String(50), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)


class ClienteCreate(BaseModel):
    nombre: str
    nit: Optional[str] = None


class ClienteResponse(BaseModel):
    id: int
    nombre: str
    nit: Optional[str] = None
    activo: bool
    model_config = {"from_attributes": True}


# Transiciones de corrección permitidas (hacia atrás).
# Solo SUPERVISOR y ADMIN pueden ejecutarlas.
_REVERT_TRANS: dict[EstadoManifiesto, EstadoManifiesto] = {
    EstadoManifiesto.EN_CARGUE:   EstadoManifiesto.PROGRAMADO,
    EstadoManifiesto.EN_TRANSITO: EstadoManifiesto.EN_CARGUE,
    EstadoManifiesto.ENTREGADO:   EstadoManifiesto.EN_TRANSITO,
    EstadoManifiesto.CANCELADO:   EstadoManifiesto.PROGRAMADO,
    EstadoManifiesto.CON_NOVEDAD: EstadoManifiesto.EN_TRANSITO,
}


class RevertirEstadoRequest(BaseModel):
    observacion: str


class ManifiestoCreate(BaseModel):
    numero: str
    vehiculo_id: int
    conductor_id: Optional[int] = None
    origen_id: int
    destino_id: int
    cliente_nombre: Optional[str] = None
    cliente_nit: Optional[str] = None
    fecha_programada: date
    observaciones: Optional[str] = None


class ManifiestoResponse(BaseModel):
    id: int
    numero: str
    vehiculo_id: int
    conductor_id: Optional[int] = None
    origen_id: int
    destino_id: int
    cliente_nombre: Optional[str] = None
    cliente_nit: Optional[str] = None
    fecha_programada: date
    fecha_salida: Optional[datetime] = None
    fecha_llegada: Optional[datetime] = None
    estado: EstadoManifiesto
    total_estibas_cargadas: int
    total_estibas_descargadas: int
    observaciones: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("/", response_model=List[ManifiestoResponse])
async def listar_manifiestos(
    estado: Optional[EstadoManifiesto] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Manifiesto).offset(skip).limit(limit).order_by(Manifiesto.fecha_programada.desc())
    if estado:
        query = query.where(Manifiesto.estado == estado)
    if fecha_desde:
        query = query.where(Manifiesto.fecha_programada >= fecha_desde)
    if fecha_hasta:
        query = query.where(Manifiesto.fecha_programada <= fecha_hasta)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/", response_model=ManifiestoResponse, status_code=201)
async def crear_manifiesto(
    data: ManifiestoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    existing = await db.execute(select(Manifiesto).where(Manifiesto.numero == data.numero))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"El manifiesto {data.numero} ya existe")

    manifiesto = Manifiesto(**data.model_dump(), usuario_creacion_id=current_user.id)
    db.add(manifiesto)
    await db.flush()
    await db.refresh(manifiesto)
    return manifiesto


# ── Clientes de manifiestos ───────────────────────────────────────────────────

@router.get("/clientes", response_model=List[ClienteResponse])
async def listar_clientes(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(ClienteManifiesto)
        .where(ClienteManifiesto.activo == True)
        .order_by(ClienteManifiesto.nombre)
    )
    return list(result.scalars().all())


@router.post("/clientes", response_model=ClienteResponse, status_code=201)
async def crear_cliente(
    data: ClienteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    nombre = data.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    existing = await db.execute(
        select(ClienteManifiesto).where(ClienteManifiesto.nombre == nombre)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese nombre")
    cliente = ClienteManifiesto(nombre=nombre, nit=data.nit)
    db.add(cliente)
    await db.commit()
    await db.refresh(cliente)
    return cliente


@router.delete("/clientes/{cliente_id}", status_code=204)
async def eliminar_cliente(
    cliente_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    cliente = await db.get(ClienteManifiesto, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    cliente.activo = False
    await db.commit()


@router.get("/{manifiesto_id}", response_model=ManifiestoResponse)
async def obtener_manifiesto(
    manifiesto_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Manifiesto).where(Manifiesto.id == manifiesto_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Manifiesto no encontrado")
    return m


@router.patch("/{manifiesto_id}/estado")
async def cambiar_estado_manifiesto(
    manifiesto_id: int,
    nuevo_estado: EstadoManifiesto,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_operador),
):
    result = await db.execute(select(Manifiesto).where(Manifiesto.id == manifiesto_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Manifiesto no encontrado")
    estado_anterior = m.estado
    m.estado = nuevo_estado
    if nuevo_estado == EstadoManifiesto.EN_TRANSITO and not m.fecha_salida:
        m.fecha_salida = datetime.now(timezone.utc)
    if nuevo_estado == EstadoManifiesto.ENTREGADO and not m.fecha_llegada:
        m.fecha_llegada = datetime.now(timezone.utc)

    db.add(ManifiestoHistorial(
        manifiesto_id=manifiesto_id,
        estado_anterior=estado_anterior.value,
        estado_nuevo=nuevo_estado.value,
        tipo_cambio=TipoCambioEstado.AVANCE,
        usuario_id=current_user.id,
    ))

    # Al salir en tránsito: verificar stock mínimo en bodega de origen
    if nuevo_estado == EstadoManifiesto.EN_TRANSITO and m.origen_id:
        await _verificar_stock_minimo(db, m.origen_id, manifiesto_id, m.numero)

    # Al marcar como entregado: detectar estibas que no llegaron
    faltantes = 0
    if nuevo_estado == EstadoManifiesto.ENTREGADO:
        faltantes = await _detectar_faltantes(db, manifiesto_id, m.numero)

    await db.commit()
    resp: dict = {"message": "Estado actualizado", "estado": nuevo_estado.value}
    if faltantes:
        resp["faltantes_detectados"] = faltantes
        resp["advertencia"] = f"Se detectaron {faltantes} estiba(s) faltante(s). Revisa la sección de alertas."
    return resp


@router.post("/{manifiesto_id}/estado/revertir")
async def revertir_estado_manifiesto(
    manifiesto_id: int,
    data: RevertirEstadoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    """Corrige un estado registrado por error. Solo SUPERVISOR y ADMIN.
    La observación es obligatoria para dejar trazabilidad del motivo."""
    if not data.observacion or not data.observacion.strip():
        raise HTTPException(status_code=400, detail="La observación es obligatoria para corregir un estado")

    result = await db.execute(select(Manifiesto).where(Manifiesto.id == manifiesto_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Manifiesto no encontrado")

    estado_anterior = m.estado
    estado_destino = _REVERT_TRANS.get(estado_anterior)
    if not estado_destino:
        raise HTTPException(
            status_code=400,
            detail=f"El estado '{estado_anterior.value}' no puede ser revertido",
        )

    m.estado = estado_destino

    # Limpiar fechas automáticas que ya no aplican
    if estado_anterior == EstadoManifiesto.EN_TRANSITO:
        m.fecha_salida = None
    if estado_anterior == EstadoManifiesto.ENTREGADO:
        m.fecha_llegada = None

    db.add(ManifiestoHistorial(
        manifiesto_id=manifiesto_id,
        estado_anterior=estado_anterior.value,
        estado_nuevo=estado_destino.value,
        tipo_cambio=TipoCambioEstado.CORRECCION,
        observacion=data.observacion.strip(),
        usuario_id=current_user.id,
    ))
    await db.flush()
    return {
        "message": "Estado corregido",
        "estado_anterior": estado_anterior.value,
        "estado": estado_destino.value,
    }


@router.get("/{manifiesto_id}/historial")
async def historial_manifiesto(
    manifiesto_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(ManifiestoHistorial)
        .where(ManifiestoHistorial.manifiesto_id == manifiesto_id)
        .options(selectinload(ManifiestoHistorial.usuario))
        .order_by(ManifiestoHistorial.fecha.desc())
    )
    registros = list(result.scalars().all())
    return [
        {
            "id":              r.id,
            "estado_anterior": r.estado_anterior,
            "estado_nuevo":    r.estado_nuevo,
            "tipo_cambio":     r.tipo_cambio.value,
            "observacion":     r.observacion,
            "usuario":         f"{r.usuario.nombre} {r.usuario.apellido}" if r.usuario else "Sistema",
            "fecha":           r.fecha.isoformat(),
        }
        for r in registros
    ]


@router.get("/{manifiesto_id}/estibas")
async def estibas_en_manifiesto(
    manifiesto_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload
    from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento

    result = await db.execute(
        select(Movimiento)
        .where(Movimiento.manifiesto_id == manifiesto_id, Movimiento.tipo == TipoMovimiento.CARGA)
        .options(selectinload(Movimiento.estiba))
        .order_by(Movimiento.fecha_movimiento)
    )
    cargas = list(result.scalars().all())
    items = []
    for mov in cargas:
        if not mov.estiba:
            continue
        estiba = mov.estiba
        estado_val = estiba.estado.value if estiba.estado else "DESCONOCIDO"
        ya_descargada = estado_val not in ("EN_TRANSITO", "CARGADA", "FALTANTE")
        items.append({
            "estiba_id": estiba.id,
            "codigo_interno": estiba.codigo_interno,
            "estado_actual": estado_val,
            "fecha_carga": mov.fecha_movimiento.isoformat(),
            "ya_descargada": ya_descargada,
        })
    return items
