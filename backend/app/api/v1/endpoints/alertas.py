from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.alerta import Alerta, TipoAlerta, NivelAlerta
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/alertas", tags=["Alertas"])


class AlertaResponse(BaseModel):
    id: int
    tipo: TipoAlerta
    nivel: NivelAlerta
    titulo: str
    descripcion: Optional[str] = None
    estiba_id: Optional[int] = None
    manifiesto_id: Optional[int] = None
    leida: bool
    resuelta: bool
    created_at: datetime
    fecha_resolucion: Optional[datetime] = None
    metadatos: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("/", response_model=List[AlertaResponse])
async def listar_alertas(
    resuelta: Optional[bool] = Query(None),
    nivel: Optional[NivelAlerta] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Alerta)
    if resuelta is not None:
        query = query.where(Alerta.resuelta == resuelta)
    if nivel:
        query = query.where(Alerta.nivel == nivel)
    query = query.order_by(Alerta.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.patch("/{alerta_id}/leer")
async def marcar_leida(
    alerta_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Alerta).where(Alerta.id == alerta_id))
    alerta = result.scalar_one_or_none()
    if alerta:
        alerta.leida = True
        await db.flush()
    return {"message": "Alerta marcada como leída"}


class ResolverAlertaRequest(BaseModel):
    observacion: str


@router.patch("/{alerta_id}/resolver")
async def resolver_alerta(
    alerta_id: int,
    data: ResolverAlertaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if not data.observacion or not data.observacion.strip():
        from fastapi import HTTPException
        raise HTTPException(400, "La observación es obligatoria para resolver una alerta")
    from datetime import timezone
    import json
    result = await db.execute(select(Alerta).where(Alerta.id == alerta_id))
    alerta = result.scalar_one_or_none()
    if alerta:
        alerta.resuelta = True
        alerta.leida = True
        alerta.fecha_resolucion = datetime.now(timezone.utc)
        alerta.usuario_resolucion_id = current_user.id
        existing = {}
        if alerta.metadatos:
            try:
                existing = json.loads(alerta.metadatos)
            except Exception:
                pass
        existing["observacion_resolucion"] = data.observacion.strip()
        existing["resuelto_por"] = current_user.nombre
        alerta.metadatos = json.dumps(existing, ensure_ascii=False)
        await db.flush()
    return {"message": "Alerta resuelta exitosamente"}


@router.get("/no-leidas/count")
async def count_no_leidas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(Alerta.id)).where(Alerta.leida == False, Alerta.resuelta == False)
    )
    return {"count": result.scalar_one()}
