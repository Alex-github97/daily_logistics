from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.application.services.dashboard_service import DashboardService
from app.application.schemas.dashboard import DashboardResponse, RetornoData

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = DashboardService(db)
    return await service.get_dashboard()


@router.get("/kpis")
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = DashboardService(db)
    dashboard = await service.get_dashboard()
    return dashboard.kpis


@router.get("/tendencia-movimientos")
async def tendencia_movimientos(
    dias: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = DashboardService(db)
    return await service._get_tendencia_movimientos(dias=dias)


@router.get("/retorno", response_model=RetornoData)
async def get_retorno_data(
    bodega_id: Optional[int] = Query(None, description="ID de la ubicación cliente para filtrar"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    service = DashboardService(db)
    return await service.get_retorno_data(bodega_id=bodega_id)
