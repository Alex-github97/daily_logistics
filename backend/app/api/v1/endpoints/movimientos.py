import io
import math
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_operador, require_module_permission

_require_movimientos = require_module_permission("movimientos")
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.movimiento import TipoMovimiento
from app.application.services.movimiento_service import MovimientoService
from app.application.schemas.movimiento import (
    MovimientoCreate, RegistrarCargaRequest, RegistrarDescargaRequest, MovimientoResponse,
    MovimientoBulkCreate, MovimientoBulkResponse,
)

router = APIRouter(prefix="/movimientos", tags=["Movimientos"])


@router.post("/", response_model=MovimientoResponse, status_code=201)
async def registrar_movimiento(
    data: MovimientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_movimientos),
):
    service = MovimientoService(db)
    return await service.registrar_movimiento(data, current_user)


@router.post("/carga-masiva")
async def registrar_carga_masiva(
    data: RegistrarCargaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_movimientos),
):
    service = MovimientoService(db)
    movimientos = await service.registrar_carga_masiva(data, current_user)
    return {"message": f"{len(movimientos)} estibas cargadas exitosamente", "count": len(movimientos)}


@router.post("/descarga-masiva")
async def registrar_descarga_masiva(
    data: RegistrarDescargaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_movimientos),
):
    service = MovimientoService(db)
    movimientos = await service.registrar_descarga_masiva(data, current_user)
    return {"message": f"{len(movimientos)} estibas descargadas exitosamente", "count": len(movimientos)}


@router.post("/bulk", response_model=MovimientoBulkResponse)
async def registrar_movimientos_masivo(
    data: MovimientoBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_require_movimientos),
):
    service = MovimientoService(db)
    exitosos = 0
    errores = []

    for i, item in enumerate(data.items):
        try:
            async with db.begin_nested():
                await service.registrar_movimiento(item, current_user)
            exitosos += 1
        except HTTPException as e:
            errores.append({"fila": i + 2, "estiba_id": item.estiba_id, "mensaje": e.detail})
        except Exception as e:
            errores.append({"fila": i + 2, "estiba_id": item.estiba_id, "mensaje": str(e)})

    return {"exitosos": exitosos, "errores": errores, "total": len(data.items)}


def _parse_rango(fecha_inicio: Optional[str], fecha_fin: Optional[str]):
    fi = datetime.fromisoformat(fecha_inicio) if fecha_inicio else None
    ff = datetime.fromisoformat(fecha_fin + "T23:59:59") if fecha_fin else None
    return fi, ff


@router.get("/resumen")
async def resumen_movimientos(
    fecha_inicio: Optional[str] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    fi, ff = _parse_rango(fecha_inicio, fecha_fin)
    service = MovimientoService(db)
    return await service.obtener_resumen(fi, ff)


@router.get("/lista")
async def listar_movimientos(
    fecha_inicio: Optional[str] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="YYYY-MM-DD"),
    tipo: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    fi, ff = _parse_rango(fecha_inicio, fecha_fin)
    tipo_enum = TipoMovimiento(tipo) if tipo else None
    service = MovimientoService(db)
    return await service.listar_movimientos(fi, ff, tipo_enum, page, page_size)


@router.get("/exportar")
async def exportar_movimientos(
    fecha_inicio: Optional[str] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="YYYY-MM-DD"),
    tipo: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    import pandas as pd

    fi, ff = _parse_rango(fecha_inicio, fecha_fin)
    tipo_enum = TipoMovimiento(tipo) if tipo else None
    service = MovimientoService(db)

    resumen = await service.obtener_resumen(fi, ff)
    data = await service.listar_movimientos(fi, ff, tipo_enum, 1, 5000)

    totales = resumen["totales"]
    por_tipo = resumen["por_tipo"]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_resumen = pd.DataFrame([
            {"Concepto": "Entradas (Carga + Recepción)", "Cantidad": totales["entradas"]},
            {"Concepto": "Salidas (Descarga + Disposición)", "Cantidad": totales["salidas"]},
            {"Concepto": "Transferencias / Retornos", "Cantidad": totales["transferencias"]},
            {"Concepto": "Otros (Inventario, Reparación, etc.)", "Cantidad": totales["otros"]},
            {"Concepto": "TOTAL MOVIMIENTOS", "Cantidad": totales["total"]},
            {"Concepto": "BALANCE (Entradas − Salidas)", "Cantidad": totales["balance"]},
        ])
        df_resumen.to_excel(writer, sheet_name="Resumen", index=False)

        if por_tipo:
            df_tipo = pd.DataFrame([
                {"Tipo de Movimiento": k, "Cantidad": v} for k, v in sorted(por_tipo.items())
            ])
            df_tipo.to_excel(writer, sheet_name="Por Tipo", index=False)

        items = data["items"]
        if items:
            df_det = pd.DataFrame(items)
            df_det.rename(columns={
                "id": "ID",
                "tipo": "Tipo",
                "fecha": "Fecha",
                "estiba_id": "Estiba ID",
                "estiba_codigo": "Código Estiba",
                "usuario": "Usuario",
                "ubicacion_origen": "Origen",
                "ubicacion_destino": "Destino",
                "vehiculo": "Vehículo",
                "estado_antes": "Estado Antes",
                "estado_despues": "Estado Después",
                "observaciones": "Observaciones",
            }, inplace=True)
            df_det.to_excel(writer, sheet_name="Movimientos", index=False)

    output.seek(0)
    suffix_ini = fecha_inicio or "inicio"
    suffix_fin = fecha_fin or "fin"
    filename = f"movimientos_{suffix_ini}_{suffix_fin}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/recientes")
async def movimientos_recientes(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from app.infrastructure.repositories.movimiento_repository import MovimientoRepository
    repo = MovimientoRepository(db)
    movimientos = await repo.get_recientes(limit=limit)
    return [
        {
            "id": m.id, "tipo": m.tipo.value, "estiba_id": m.estiba_id,
            "fecha": m.fecha_movimiento.isoformat(),
            "usuario": m.usuario.nombre_completo if m.usuario else "Sistema",
            "ubicacion_destino": m.ubicacion_destino.nombre if m.ubicacion_destino else None,
        }
        for m in movimientos
    ]
