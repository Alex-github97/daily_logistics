from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from app.infrastructure.repositories.base_repository import BaseRepository
from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento


class MovimientoRepository(BaseRepository[Movimiento]):
    def __init__(self, db: AsyncSession):
        super().__init__(Movimiento, db)

    async def get_by_estiba(self, estiba_id: int, limit: int = 100) -> List[Movimiento]:
        result = await self.db.execute(
            select(Movimiento)
            .where(Movimiento.estiba_id == estiba_id)
            .options(
                selectinload(Movimiento.ubicacion_origen),
                selectinload(Movimiento.ubicacion_destino),
                selectinload(Movimiento.vehiculo),
                selectinload(Movimiento.manifiesto),
                selectinload(Movimiento.usuario),
            )
            .order_by(Movimiento.fecha_movimiento.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_manifiesto(self, manifiesto_id: int) -> List[Movimiento]:
        result = await self.db.execute(
            select(Movimiento)
            .where(Movimiento.manifiesto_id == manifiesto_id)
            .options(selectinload(Movimiento.estiba))
            .order_by(Movimiento.fecha_movimiento)
        )
        return list(result.scalars().all())

    async def count_by_tipo(self, tipo: TipoMovimiento) -> int:
        result = await self.db.execute(
            select(func.count(Movimiento.id)).where(Movimiento.tipo == tipo)
        )
        return result.scalar_one()

    async def get_recientes(self, limit: int = 20) -> List[Movimiento]:
        result = await self.db.execute(
            select(Movimiento)
            .options(
                selectinload(Movimiento.estiba),
                selectinload(Movimiento.usuario),
                selectinload(Movimiento.ubicacion_destino),
            )
            .order_by(Movimiento.fecha_movimiento.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def _build_conditions(
        self,
        fecha_inicio: Optional[datetime],
        fecha_fin: Optional[datetime],
        tipo: Optional[TipoMovimiento],
    ) -> list:
        conds = []
        if fecha_inicio:
            conds.append(Movimiento.fecha_movimiento >= fecha_inicio)
        if fecha_fin:
            conds.append(Movimiento.fecha_movimiento <= fecha_fin)
        if tipo:
            conds.append(Movimiento.tipo == tipo)
        return conds

    async def get_con_filtros(
        self,
        fecha_inicio: Optional[datetime],
        fecha_fin: Optional[datetime],
        tipo: Optional[TipoMovimiento],
        page: int,
        page_size: int,
    ) -> Tuple[List[Movimiento], int]:
        conds = self._build_conditions(fecha_inicio, fecha_fin, tipo)
        where = and_(*conds) if conds else True

        total_res = await self.db.execute(
            select(func.count(Movimiento.id)).where(where)
        )
        total = total_res.scalar_one()

        result = await self.db.execute(
            select(Movimiento)
            .where(where)
            .options(
                selectinload(Movimiento.estiba),
                selectinload(Movimiento.usuario),
                selectinload(Movimiento.ubicacion_origen),
                selectinload(Movimiento.ubicacion_destino),
                selectinload(Movimiento.vehiculo),
            )
            .order_by(Movimiento.fecha_movimiento.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_resumen_por_tipo(
        self,
        fecha_inicio: Optional[datetime],
        fecha_fin: Optional[datetime],
    ) -> dict:
        conds = self._build_conditions(fecha_inicio, fecha_fin, None)
        where = and_(*conds) if conds else True

        result = await self.db.execute(
            select(Movimiento.tipo, func.count(Movimiento.id).label("cantidad"))
            .where(where)
            .group_by(Movimiento.tipo)
        )
        return {row.tipo.value: row.cantidad for row in result.all()}
