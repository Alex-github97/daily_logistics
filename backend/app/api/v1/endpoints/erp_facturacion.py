"""Finanzas · Resoluciones de facturación DIAN y notas crédito de venta."""
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.core.facturacion_dian import restantes
from app.infrastructure.models.erp import ERPEmpresa, ERPFacturaCliente
from app.infrastructure.models.erp_facturacion import ERPNotaCreditoCliente, ERPResolucionFacturacion
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/erp", tags=["ERP · Facturación"])


class ResolucionIn(BaseModel):
    empresa_id: Optional[int] = None
    tipo_documento: Literal["FACTURA_VENTA", "POS", "NOTA_CREDITO"] = "POS"
    numero_resolucion: str = Field(min_length=1, max_length=40)
    fecha_resolucion: date
    prefijo: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9]+$")
    desde: int = Field(ge=1)
    hasta: int = Field(ge=1)
    vigencia_desde: date
    vigencia_hasta: date
    clave_tecnica: Optional[str] = Field(default=None, max_length=120)
    ambiente: Literal["1", "2"] = "2"
    activa: bool = True
    aviso_restantes: int = Field(default=100, ge=0)

    @model_validator(mode="after")
    def _rangos(self):
        if self.hasta < self.desde:
            raise ValueError("El rango termina antes de empezar.")
        if self.vigencia_hasta < self.vigencia_desde:
            raise ValueError("La vigencia termina antes de empezar.")
        return self


def _dict(r: ERPResolucionFacturacion) -> dict:
    hoy = date.today()
    quedan = restantes(r)
    return {**{c.name: (getattr(r, c.name).isoformat() if isinstance(getattr(r, c.name), date) else getattr(r, c.name))
               for c in r.__table__.columns if c.name not in ("created_at", "updated_at")},
            "restantes": quedan, "vigente": r.activa and r.vigencia_desde <= hoy <= r.vigencia_hasta and quedan > 0,
            "alerta": (r.vigencia_hasta - hoy).days <= 30 or quedan <= r.aviso_restantes,
            "siguiente": f"{r.prefijo}{max(r.actual or 0, r.desde - 1) + 1}" if quedan > 0 else None}


@router.get("/resoluciones")
async def resoluciones(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return [_dict(r) for r in (await db.execute(select(ERPResolucionFacturacion)
                                                .order_by(ERPResolucionFacturacion.vigencia_hasta.desc()))).scalars()]


async def _empresa(db, empresa_id):
    if empresa_id:
        if not await db.get(ERPEmpresa, empresa_id):
            raise HTTPException(422, "La empresa no existe.")
        return empresa_id
    eid = (await db.execute(select(ERPEmpresa.id).order_by(ERPEmpresa.id).limit(1))).scalar()
    if eid is None:
        raise HTTPException(422, "Cree primero la empresa.")
    return eid


@router.post("/resoluciones", status_code=201)
async def crear_resolucion(data: ResolucionIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_admin)):
    datos = data.model_dump()
    datos["empresa_id"] = await _empresa(db, data.empresa_id)
    datos["prefijo"] = data.prefijo.upper()
    r = ERPResolucionFacturacion(**datos, actual=data.desde - 1)
    db.add(r)
    await db.commit()
    return _dict(r)


@router.put("/resoluciones/{rid}")
async def editar_resolucion(rid: int, data: ResolucionIn, db: AsyncSession = Depends(get_db),
                            _: Usuario = Depends(require_admin)):
    r = await db.get(ERPResolucionFacturacion, rid)
    if r is None:
        raise HTTPException(404, "Resolución no encontrada")
    usados = (r.actual or 0) >= r.desde
    if usados and (data.prefijo.upper() != r.prefijo or data.desde != r.desde):
        raise HTTPException(409, "Ya se numeró con esta resolución: el prefijo y el inicio del rango no se cambian.")
    if usados and data.hasta < (r.actual or 0):
        raise HTTPException(409, f"El rango no puede terminar antes del último número usado ({r.actual}).")
    for k, v in data.model_dump().items():
        if k == "empresa_id":
            continue
        setattr(r, k, v.upper() if k == "prefijo" else v)
    await db.commit()
    return _dict(r)


@router.get("/notas-credito")
async def notas_credito(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    filas = (await db.execute(select(ERPNotaCreditoCliente, ERPFacturaCliente.numero, ERPFacturaCliente.cliente_nombre)
                              .join(ERPFacturaCliente, ERPFacturaCliente.id == ERPNotaCreditoCliente.factura_id)
                              .order_by(ERPNotaCreditoCliente.fecha.desc(), ERPNotaCreditoCliente.id.desc())
                              .limit(500))).all()
    return [{"id": n.id, "numero": n.numero, "fecha": n.fecha.isoformat(), "factura": num, "cliente": cli,
             "concepto": n.concepto, "motivo": n.motivo, "subtotal": float(n.subtotal),
             "impuestos": float(n.total_impuestos), "total": float(n.total), "cude": n.cude,
             "estado_dian": n.estado_dian, "origen": n.origen} for n, num, cli in filas]
