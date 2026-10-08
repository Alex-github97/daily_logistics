from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from app.infrastructure.repositories.base_repository import BaseRepository
from app.infrastructure.models.estiba import Estiba, EstadoEstiba, TipoPropietario



class EstibaRepository(BaseRepository[Estiba]):
    def __init__(self, db: AsyncSession):
        super().__init__(Estiba, db)

    async def create(self, obj: Estiba) -> Estiba:
        await super().create(obj)
        return await self.get_with_relations(obj.id)

    async def update(self, obj: Estiba, data: Dict[str, Any]) -> Estiba:
        await super().update(obj, data)
        return await self.get_with_relations(obj.id)

    async def get_by_codigo(self, codigo: str) -> Optional[Estiba]:
        result = await self.db.execute(
            select(Estiba)
            .where(
                or_(
                    Estiba.codigo_interno == codigo,
                    Estiba.codigo_qr == codigo,
                    Estiba.codigo_rfid == codigo,
                ),
                Estiba.activo == True,
            )
            .options(
                selectinload(Estiba.ubicacion_actual),
                selectinload(Estiba.proveedor),
                selectinload(Estiba.contrato),
                selectinload(Estiba.movimientos),
                selectinload(Estiba.eventos_dano),
            )
        )
        return result.scalar_one_or_none()

    async def get_with_relations(self, estiba_id: int) -> Optional[Estiba]:
        result = await self.db.execute(
            select(Estiba)
            .where(Estiba.id == estiba_id)
            .options(
                selectinload(Estiba.ubicacion_actual),
                selectinload(Estiba.proveedor),
                selectinload(Estiba.contrato),
                selectinload(Estiba.movimientos),
                selectinload(Estiba.eventos_dano),
            )
        )
        return result.scalar_one_or_none()

    async def get_filtered(
        self, skip: int = 0, limit: int = 50,
        estado: Optional[str] = None,
        tipo_propietario: Optional[str] = None,
        ubicacion_id: Optional[int] = None,
        proveedor_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> tuple[List[Estiba], int]:
        base_filter = Estiba.activo == True
        query = (
            select(Estiba)
            .where(base_filter)
            .options(
                selectinload(Estiba.ubicacion_actual),
                selectinload(Estiba.proveedor),
                selectinload(Estiba.contrato),
            )
        )
        count_query = select(func.count(Estiba.id)).where(base_filter)

        filters = []
        if estado:
            filters.append(Estiba.estado == estado)
        if tipo_propietario:
            filters.append(Estiba.tipo_propietario == tipo_propietario)
        if ubicacion_id:
            filters.append(Estiba.ubicacion_actual_id == ubicacion_id)
        if proveedor_id:
            filters.append(Estiba.proveedor_id == proveedor_id)
        if search:
            filters.append(
                or_(
                    Estiba.codigo_interno.ilike(f"%{search}%"),
                    Estiba.codigo_qr.ilike(f"%{search}%"),
                    Estiba.codigo_rfid.ilike(f"%{search}%"),
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.offset(skip).limit(limit).order_by(Estiba.codigo_interno)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_kpis(self) -> Dict[str, int]:
        result = await self.db.execute(
            select(Estiba.estado, func.count(Estiba.id))
            .where(Estiba.activo == True)
            .group_by(Estiba.estado)
        )
        rows = result.all()
        kpis = {estado.value: 0 for estado in EstadoEstiba}
        kpis["total"] = 0
        for estado, count in rows:
            kpis[estado] = count
            kpis["total"] += count
        return kpis

    async def get_by_ubicacion(self, ubicacion_id: int) -> List[Estiba]:
        result = await self.db.execute(
            select(Estiba).where(
                Estiba.ubicacion_actual_id == ubicacion_id,
                Estiba.activo == True,
            )
        )
        return list(result.scalars().all())
