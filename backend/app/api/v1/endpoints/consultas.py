import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Any, Dict, List

from app.core.database import get_db
from app.core.dependencies import require_supervisor

router = APIRouter(prefix="/consultas", tags=["consultas"])


class ConsultaRequest(BaseModel):
    sql: str
    limite: int = 5000


class ConsultaResponse(BaseModel):
    columnas: List[str]
    filas: List[List[Any]]
    total_filas: int
    tiempo_ms: float


@router.post("/ejecutar", response_model=ConsultaResponse)
async def ejecutar_consulta(
    request: ConsultaRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_supervisor),
):
    sql = request.sql.strip().rstrip(";")

    if not sql.upper().startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten consultas SELECT",
        )

    if sql.upper().count("SELECT") > 1 and any(
        kw in sql.upper() for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sentencia no permitida",
        )

    limite = min(max(1, request.limite), 5000)
    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {limite}"

    start = time.perf_counter()
    try:
        result = await db.execute(text(sql))
        rows = result.fetchall()
        columnas = list(result.keys())
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        return ConsultaResponse(
            columnas=columnas,
            filas=[[str(v) if v is not None else None for v in row] for row in rows],
            total_filas=len(rows),
            tiempo_ms=elapsed_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error en consulta: {str(e)}",
        )


@router.get("/schema")
async def get_schema(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_supervisor),
) -> Dict[str, List[str]]:
    result = await db.execute(text("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """))
    schema: Dict[str, List[str]] = {}
    for row in result.all():
        schema.setdefault(row.table_name, []).append(row.column_name)
    return schema
