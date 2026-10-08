from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_operador, require_supervisor, require_module_permission

_require_estibas = require_module_permission("estibas")
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.estiba import Estiba, EstadoEstiba, TipoEstiba, EstibaStockMinimo
from app.application.services.estiba_service import EstibaService
from app.application.schemas.estiba import (
    EstibaCreate, EstibaUpdate, EstibaResponse, EstibaListResponse, EstibaKPIs,
    EstibaBulkCreate, EstibaBulkResponse,
)


class ConfirmarPerdidaRequest(BaseModel):
    observacion: str

class RecuperarFaltanteRequest(BaseModel):
    observacion: str
    ubicacion_id: Optional[int] = None

class StockMinimoCreate(BaseModel):
    ubicacion_id: int
    tipo_estiba: str
    cantidad_minima: int

class StockMinimoUpdate(BaseModel):
    cantidad_minima: Optional[int] = None
    activo: Optional[bool] = None

class StockMinimoResponse(BaseModel):
    id: int
    ubicacion_id: int
    tipo_estiba: str
    cantidad_minima: int
    activo: bool
    model_config = {"from_attributes": True}

router = APIRouter(prefix="/estibas", tags=["Estibas"])


@router.get("/kpis", response_model=EstibaKPIs)
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = EstibaService(db)
    kpis = await service.get_kpis()
    return EstibaKPIs(**kpis)


@router.get("/", response_model=EstibaListResponse)
async def listar_estibas(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    estado: Optional[str] = Query(None),
    tipo_propietario: Optional[str] = Query(None),
    ubicacion_id: Optional[int] = Query(None),
    proveedor_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, min_length=2),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = EstibaService(db)
    return await service.listar_estibas(
        page=page, page_size=page_size, estado=estado,
        tipo_propietario=tipo_propietario, ubicacion_id=ubicacion_id,
        proveedor_id=proveedor_id, search=search,
    )


@router.post("/", response_model=EstibaResponse, status_code=201)
async def crear_estiba(
    data: EstibaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_estibas),
):
    service = EstibaService(db)
    return await service.crear_estiba(data, current_user)


@router.post("/bulk", response_model=EstibaBulkResponse)
async def crear_estibas_masivo(
    data: EstibaBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_estibas),
):
    service = EstibaService(db)
    exitosos = 0
    errores = []

    for i, item in enumerate(data.items):
        try:
            async with db.begin_nested():
                await service.crear_estiba(item, current_user)
            exitosos += 1
        except HTTPException as e:
            errores.append({"fila": i + 2, "codigo": item.codigo_interno, "mensaje": e.detail})
        except Exception as e:
            errores.append({"fila": i + 2, "codigo": item.codigo_interno, "mensaje": str(e)})

    return {"exitosos": exitosos, "errores": errores, "total": len(data.items)}


@router.get("/buscar/{codigo}", response_model=EstibaResponse)
async def buscar_por_codigo(
    codigo: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = EstibaService(db)
    return await service.buscar_por_codigo(codigo)


@router.get("/{estiba_id}", response_model=EstibaResponse)
async def obtener_estiba(
    estiba_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = EstibaService(db)
    return await service.obtener_estiba(estiba_id)


@router.put("/{estiba_id}", response_model=EstibaResponse)
async def actualizar_estiba(
    estiba_id: int, data: EstibaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_estibas),
):
    service = EstibaService(db)
    return await service.actualizar_estiba(estiba_id, data)


@router.post("/{estiba_id}/dar-baja")
async def dar_baja(
    estiba_id: int,
    motivo: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_estibas),
):
    service = EstibaService(db)
    estiba = await service.dar_de_baja(estiba_id, motivo, current_user)
    return {"message": "Estiba dada de baja exitosamente", "id": estiba.id}


@router.delete("/{estiba_id}", status_code=204)
async def eliminar_estiba(
    estiba_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_estibas),
):
    service = EstibaService(db)
    await service.eliminar_estiba(estiba_id)


@router.get("/{estiba_id}/trazabilidad")
async def trazabilidad_estiba(
    estiba_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from app.application.services.movimiento_service import MovimientoService
    service = MovimientoService(db)
    return await service.obtener_trazabilidad(estiba_id)


@router.post("/{estiba_id}/confirmar-perdida")
async def confirmar_perdida(
    estiba_id: int,
    data: ConfirmarPerdidaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    """Confirma definitivamente la pérdida de una estiba FALTANTE. Solo SUPERVISOR/ADMIN."""
    if not data.observacion or not data.observacion.strip():
        raise HTTPException(400, "La observación es obligatoria para confirmar una pérdida")

    estiba = await db.get(Estiba, estiba_id)
    if not estiba:
        raise HTTPException(404, "Estiba no encontrada")
    if estiba.estado != EstadoEstiba.FALTANTE:
        raise HTTPException(
            400,
            f"Solo se pueden dar de baja estibas en estado FALTANTE. Estado actual: {estiba.estado.value}",
        )

    estado_anterior = estiba.estado.value
    estiba.estado = EstadoEstiba.PERDIDA
    estiba.observaciones = f"PÉRDIDA CONFIRMADA: {data.observacion.strip()}"

    from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento
    movimiento = Movimiento(
        estiba_id=estiba_id,
        tipo=TipoMovimiento.BAJA,
        usuario_id=current_user.id,
        ubicacion_origen_id=estiba.ubicacion_actual_id,
        observaciones=f"Pérdida confirmada desde estado FALTANTE. {data.observacion.strip()}",
        estado_estiba_antes=estado_anterior,
        estado_estiba_despues=EstadoEstiba.PERDIDA.value,
        metadatos={"motivo": "FALTANTE_CONFIRMADO", "valor_estiba": float(estiba.valor_actual or 0)},
    )
    db.add(movimiento)

    from app.infrastructure.models.alerta import Alerta, TipoAlerta
    alerts_r = await db.execute(
        select(Alerta).where(
            Alerta.estiba_id == estiba_id,
            Alerta.tipo == TipoAlerta.ESTIBA_FALTANTE,
            Alerta.resuelta == False,
        )
    )
    for alerta in alerts_r.scalars().all():
        alerta.resuelta = True
        alerta.leida = True
        alerta.fecha_resolucion = datetime.now(timezone.utc)
        alerta.usuario_resolucion_id = current_user.id

    await db.commit()
    return {"message": "Pérdida confirmada. Estiba marcada como PERDIDA.", "id": estiba_id}


@router.post("/{estiba_id}/recuperar-faltante")
async def recuperar_faltante(
    estiba_id: int,
    data: RecuperarFaltanteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    """Recupera una estiba FALTANTE que fue encontrada. Solo SUPERVISOR/ADMIN."""
    if not data.observacion or not data.observacion.strip():
        raise HTTPException(400, "La observación es obligatoria para registrar la recuperación")

    estiba = await db.get(Estiba, estiba_id)
    if not estiba:
        raise HTTPException(404, "Estiba no encontrada")
    if estiba.estado != EstadoEstiba.FALTANTE:
        raise HTTPException(400, "Solo se pueden recuperar estibas en estado FALTANTE")

    estado_anterior = estiba.estado.value
    estiba.estado = EstadoEstiba.EN_INVENTARIO
    if data.ubicacion_id:
        estiba.ubicacion_actual_id = data.ubicacion_id
    estiba.observaciones = f"RECUPERADA: {data.observacion.strip()}"

    from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento
    movimiento = Movimiento(
        estiba_id=estiba_id,
        tipo=TipoMovimiento.RETORNO,
        usuario_id=current_user.id,
        ubicacion_origen_id=estiba.ubicacion_actual_id,
        ubicacion_destino_id=data.ubicacion_id,
        observaciones=f"Estiba recuperada desde estado FALTANTE. {data.observacion.strip()}",
        estado_estiba_antes=estado_anterior,
        estado_estiba_despues=EstadoEstiba.EN_INVENTARIO.value,
        metadatos={"motivo": "FALTANTE_RECUPERADO"},
    )
    db.add(movimiento)

    from app.infrastructure.models.alerta import Alerta, TipoAlerta
    alerts_r = await db.execute(
        select(Alerta).where(
            Alerta.estiba_id == estiba_id,
            Alerta.tipo == TipoAlerta.ESTIBA_FALTANTE,
            Alerta.resuelta == False,
        )
    )
    for alerta in alerts_r.scalars().all():
        alerta.resuelta = True
        alerta.leida = True
        alerta.fecha_resolucion = datetime.now(timezone.utc)
        alerta.usuario_resolucion_id = current_user.id

    await db.commit()
    return {"message": "Estiba recuperada y vuelta a inventario.", "id": estiba_id}


# ── Stock Mínimo por Bodega ──────────────────────────────────────────────────

async def _evaluar_config_stock(db: AsyncSession, config: EstibaStockMinimo, manifiesto_id: int | None = None) -> bool:
    """Evalúa una regla de stock mínimo y crea alerta STOCK_BAJO si aplica. Retorna True si creó alerta."""
    from app.infrastructure.models.alerta import Alerta, TipoAlerta, NivelAlerta
    from app.infrastructure.models.ubicacion import Ubicacion
    import json

    if not config.activo:
        return False

    count_r = await db.execute(
        select(func.count(Estiba.id)).where(
            Estiba.ubicacion_actual_id == config.ubicacion_id,
            Estiba.tipo == config.tipo_estiba,
            Estiba.estado == EstadoEstiba.EN_INVENTARIO,
        )
    )
    stock_actual = count_r.scalar_one() or 0

    if stock_actual >= config.cantidad_minima:
        return False

    # Verificar si ya existe una alerta activa para esta combinación
    existing_r = await db.execute(
        select(Alerta).where(Alerta.tipo == TipoAlerta.STOCK_BAJO, Alerta.resuelta == False)
    )
    for ea in existing_r.scalars().all():
        try:
            m = json.loads(ea.metadatos or '{}')
            if m.get('ubicacion_id') == config.ubicacion_id and m.get('tipo_estiba') == config.tipo_estiba.value:
                return False
        except Exception:
            pass

    ub_r = await db.execute(select(Ubicacion).where(Ubicacion.id == config.ubicacion_id))
    ub = ub_r.scalar_one_or_none()
    ubicacion_nombre = ub.nombre if ub else f"bodega ID {config.ubicacion_id}"

    db.add(Alerta(
        tipo=TipoAlerta.STOCK_BAJO,
        nivel=NivelAlerta.ADVERTENCIA,
        titulo=f"Stock bajo: estibas {config.tipo_estiba.value} en {ubicacion_nombre}",
        descripcion=f"Stock actual: {stock_actual} | Mínimo configurado: {config.cantidad_minima}.",
        manifiesto_id=manifiesto_id,
        metadatos=json.dumps({
            "ubicacion_id": config.ubicacion_id,
            "tipo_estiba":  config.tipo_estiba.value,
            "stock_actual": stock_actual,
            "stock_minimo": config.cantidad_minima,
        }),
    ))
    return True


@router.get("/stock-minimo/resumen")
async def resumen_stock_minimo(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Lista configuraciones de stock mínimo con el conteo actual de estibas EN_INVENTARIO."""
    from sqlalchemy.orm import selectinload
    configs_r = await db.execute(
        select(EstibaStockMinimo)
        .options(selectinload(EstibaStockMinimo.ubicacion))
        .order_by(EstibaStockMinimo.ubicacion_id, EstibaStockMinimo.tipo_estiba)
    )
    configs = configs_r.scalars().all()

    result = []
    for c in configs:
        count_r = await db.execute(
            select(func.count(Estiba.id)).where(
                Estiba.ubicacion_actual_id == c.ubicacion_id,
                Estiba.tipo == c.tipo_estiba,
                Estiba.estado == EstadoEstiba.EN_INVENTARIO,
            )
        )
        stock_actual = count_r.scalar_one() or 0
        result.append({
            "id":              c.id,
            "ubicacion_id":    c.ubicacion_id,
            "ubicacion_nombre": c.ubicacion.nombre if c.ubicacion else None,
            "tipo_estiba":     c.tipo_estiba.value,
            "cantidad_minima": c.cantidad_minima,
            "stock_actual":    stock_actual,
            "activo":          c.activo,
        })
    return result


@router.post("/stock-minimo", response_model=StockMinimoResponse, status_code=201)
async def crear_stock_minimo(
    data: StockMinimoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    try:
        tipo = TipoEstiba(data.tipo_estiba)
    except ValueError:
        raise HTTPException(400, f"Tipo de estiba inválido: {data.tipo_estiba}")

    existing = await db.execute(
        select(EstibaStockMinimo).where(
            EstibaStockMinimo.ubicacion_id == data.ubicacion_id,
            EstibaStockMinimo.tipo_estiba == tipo,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Ya existe una configuración para esta bodega y tipo de estiba")

    config = EstibaStockMinimo(
        ubicacion_id=data.ubicacion_id,
        tipo_estiba=tipo,
        cantidad_minima=data.cantidad_minima,
    )
    db.add(config)
    await db.flush()
    await _evaluar_config_stock(db, config)
    await db.commit()
    await db.refresh(config)
    return config


@router.put("/stock-minimo/{config_id}", response_model=StockMinimoResponse)
async def actualizar_stock_minimo(
    config_id: int,
    data: StockMinimoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    config = await db.get(EstibaStockMinimo, config_id)
    if not config:
        raise HTTPException(404, "Configuración no encontrada")
    if data.cantidad_minima is not None:
        config.cantidad_minima = data.cantidad_minima
    if data.activo is not None:
        config.activo = data.activo
    await db.flush()
    await _evaluar_config_stock(db, config)

    await db.commit()
    await db.refresh(config)
    return config


@router.delete("/stock-minimo/{config_id}", status_code=204)
async def eliminar_stock_minimo(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_supervisor),
):
    config = await db.get(EstibaStockMinimo, config_id)
    if not config:
        raise HTTPException(404, "Configuración no encontrada")
    await db.delete(config)
    await db.commit()
