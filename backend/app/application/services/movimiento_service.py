import math
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.infrastructure.repositories.estiba_repository import EstibaRepository
from app.infrastructure.repositories.movimiento_repository import MovimientoRepository
from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento
from app.infrastructure.models.estiba import EstadoEstiba
from app.infrastructure.models.ubicacion import Ubicacion, TipoUbicacion
from app.infrastructure.models.usuario import Usuario
from app.application.schemas.movimiento import (
    MovimientoCreate, RegistrarCargaRequest, RegistrarDescargaRequest
)

# Desde la perspectiva del inventario de bodegas:
# CARGA = la estiba SALE de la bodega al vehículo → SALIDA
# DESCARGA = la estiba LLEGA a una bodega → ENTRADA
_TIPOS_ENTRADA = {"RECEPCION", "DESCARGA"}
_TIPOS_SALIDA = {"CARGA", "DISPOSICION_FINAL"}
_TIPOS_TRANSF = {"TRANSFERENCIA", "RETORNO"}

TRANSICIONES_VALIDAS = {
    TipoMovimiento.CARGA: [EstadoEstiba.EN_INVENTARIO, EstadoEstiba.DISPONIBLE, EstadoEstiba.PENDIENTE_RETORNO],
    TipoMovimiento.DESCARGA: [EstadoEstiba.EN_TRANSITO, EstadoEstiba.CARGADA],
    TipoMovimiento.RETORNO: [EstadoEstiba.EN_CLIENTE, EstadoEstiba.PENDIENTE_RETORNO],
    TipoMovimiento.DISPOSICION_FINAL: list(EstadoEstiba),
    TipoMovimiento.BAJA: list(EstadoEstiba),
}

ESTADO_DESTINO = {
    TipoMovimiento.CARGA: EstadoEstiba.EN_TRANSITO,
    TipoMovimiento.DESCARGA: EstadoEstiba.EN_CLIENTE,
    TipoMovimiento.RETORNO: EstadoEstiba.EN_INVENTARIO,
    TipoMovimiento.TRANSFERENCIA: EstadoEstiba.EN_INVENTARIO,
    TipoMovimiento.RECEPCION: EstadoEstiba.EN_INVENTARIO,
    TipoMovimiento.REPARACION: EstadoEstiba.EN_REPARACION,
    TipoMovimiento.BAJA: EstadoEstiba.BAJA,
    TipoMovimiento.DISPOSICION_FINAL: EstadoEstiba.DISPOSICION_FINAL,
    TipoMovimiento.INVENTARIO: EstadoEstiba.EN_INVENTARIO,
}


class MovimientoService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.estiba_repo = EstibaRepository(db)
        self.movimiento_repo = MovimientoRepository(db)

    async def registrar_movimiento(self, data: MovimientoCreate, usuario: Usuario) -> Movimiento:
        estiba = await self.estiba_repo.get_by_id(data.estiba_id)
        if not estiba:
            raise HTTPException(status_code=404, detail="Estiba no encontrada")

        estado_antes = estiba.estado
        nuevo_estado = ESTADO_DESTINO.get(data.tipo, estiba.estado)

        # Para DESCARGA: el estado final depende del tipo de bodega destino.
        # Solo es EN_CLIENTE si la ubicación tiene tipo=CLIENTE; bodegas propias → EN_INVENTARIO.
        if data.tipo == TipoMovimiento.DESCARGA and data.ubicacion_destino_id:
            res = await self.db.execute(select(Ubicacion).where(Ubicacion.id == data.ubicacion_destino_id))
            ub_dest = res.scalar_one_or_none()
            if ub_dest and ub_dest.tipo == TipoUbicacion.CLIENTE:
                nuevo_estado = EstadoEstiba.EN_CLIENTE
            else:
                nuevo_estado = EstadoEstiba.EN_INVENTARIO

        movimiento = Movimiento(
            estiba_id=data.estiba_id,
            tipo=data.tipo,
            ubicacion_origen_id=data.ubicacion_origen_id or estiba.ubicacion_actual_id,
            ubicacion_destino_id=data.ubicacion_destino_id,
            vehiculo_id=data.vehiculo_id,
            manifiesto_id=data.manifiesto_id,
            conductor_id=data.conductor_id,
            usuario_id=usuario.id,
            latitud=data.latitud,
            longitud=data.longitud,
            observaciones=data.observaciones,
            metadatos=data.metadatos or {},
            estado_estiba_antes=estado_antes.value if estado_antes else None,
            estado_estiba_despues=nuevo_estado.value,
        )

        estiba.estado = nuevo_estado
        if data.ubicacion_destino_id:
            estiba.ubicacion_actual_id = data.ubicacion_destino_id
        estiba.total_usos += 1

        return await self.movimiento_repo.create(movimiento)

    async def registrar_carga_masiva(
        self, data: RegistrarCargaRequest, usuario: Usuario
    ) -> List[Movimiento]:
        movimientos = []
        for estiba_id in data.estiba_ids:
            mv = MovimientoCreate(
                estiba_id=estiba_id,
                tipo=TipoMovimiento.CARGA,
                ubicacion_origen_id=data.ubicacion_origen_id,
                vehiculo_id=data.vehiculo_id,
                manifiesto_id=data.manifiesto_id,
                latitud=data.latitud,
                longitud=data.longitud,
                observaciones=data.observaciones,
            )
            movimiento = await self.registrar_movimiento(mv, usuario)
            movimientos.append(movimiento)
        return movimientos

    async def registrar_descarga_masiva(
        self, data: RegistrarDescargaRequest, usuario: Usuario
    ) -> List[Movimiento]:
        movimientos = []
        for estiba_id in data.estiba_ids:
            mv = MovimientoCreate(
                estiba_id=estiba_id,
                tipo=TipoMovimiento.DESCARGA,
                ubicacion_destino_id=data.ubicacion_destino_id,
                vehiculo_id=data.vehiculo_id,
                manifiesto_id=data.manifiesto_id,
                latitud=data.latitud,
                longitud=data.longitud,
                observaciones=data.observaciones,
            )
            movimiento = await self.registrar_movimiento(mv, usuario)
            movimientos.append(movimiento)
        return movimientos

    def _movimiento_a_dict(self, m: Movimiento) -> dict:
        return {
            "id": m.id,
            "tipo": m.tipo.value,
            "fecha": m.fecha_movimiento.isoformat(),
            "estiba_id": m.estiba_id,
            "estiba_codigo": m.estiba.codigo_interno if m.estiba else str(m.estiba_id),
            "usuario": m.usuario.nombre_completo if m.usuario else "Sistema",
            "ubicacion_origen": m.ubicacion_origen.nombre if m.ubicacion_origen else None,
            "ubicacion_destino": m.ubicacion_destino.nombre if m.ubicacion_destino else None,
            "vehiculo": m.vehiculo.placa if m.vehiculo else None,
            "estado_antes": m.estado_estiba_antes,
            "estado_despues": m.estado_estiba_despues,
            "observaciones": m.observaciones,
        }

    async def listar_movimientos(
        self,
        fecha_inicio: Optional[datetime],
        fecha_fin: Optional[datetime],
        tipo: Optional[TipoMovimiento],
        page: int,
        page_size: int,
    ) -> dict:
        items, total = await self.movimiento_repo.get_con_filtros(
            fecha_inicio, fecha_fin, tipo, page, page_size
        )
        pages = math.ceil(total / page_size) if total > 0 else 1
        return {
            "items": [self._movimiento_a_dict(m) for m in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }

    async def obtener_resumen(
        self,
        fecha_inicio: Optional[datetime],
        fecha_fin: Optional[datetime],
    ) -> dict:
        por_tipo = await self.movimiento_repo.get_resumen_por_tipo(fecha_inicio, fecha_fin)
        entradas = sum(v for k, v in por_tipo.items() if k in _TIPOS_ENTRADA)
        salidas = sum(v for k, v in por_tipo.items() if k in _TIPOS_SALIDA)
        transferencias = sum(v for k, v in por_tipo.items() if k in _TIPOS_TRANSF)
        otros = sum(v for k, v in por_tipo.items() if k not in _TIPOS_ENTRADA | _TIPOS_SALIDA | _TIPOS_TRANSF)
        total = sum(por_tipo.values())
        return {
            "por_tipo": por_tipo,
            "totales": {
                "entradas": entradas,
                "salidas": salidas,
                "transferencias": transferencias,
                "otros": otros,
                "total": total,
                "balance": entradas - salidas,
            },
        }

    async def obtener_trazabilidad(self, estiba_id: int) -> List[dict]:
        movimientos = await self.movimiento_repo.get_by_estiba(estiba_id)
        trazabilidad = []
        for m in movimientos:
            item = {
                "id": m.id,
                "tipo": m.tipo.value,
                "fecha": m.fecha_movimiento.isoformat(),
                "usuario": m.usuario.nombre_completo if m.usuario else "Sistema",
                "ubicacion_origen": m.ubicacion_origen.nombre if m.ubicacion_origen else None,
                "ubicacion_destino": m.ubicacion_destino.nombre if m.ubicacion_destino else None,
                "vehiculo": m.vehiculo.placa if m.vehiculo else None,
                "manifiesto": m.manifiesto.numero if m.manifiesto else None,
                "observaciones": m.observaciones,
                "estado_antes": m.estado_estiba_antes,
                "estado_despues": m.estado_estiba_despues,
                "latitud": m.latitud,
                "longitud": m.longitud,
            }
            trazabilidad.append(item)
        return trazabilidad
