"""
Configuración general de la empresa (propio de Daily Logistics).

Los datos de facturación de la empresa —razón social, NIT, dirección— los
necesitan el POS y los despachos del WMS para emitir facturas. En la plataforma
madre se cargan en el ERP; Daily Logistics no lo tiene, así que se administran
aquí. Al guardarlos por primera vez se siembra el plan de cuentas y las reglas
contables, sin las cuales la primera factura fallaría.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.erp import ERPEmpresa
from app.infrastructure.models.erp_facturacion import ERPResolucionFacturacion
from app.infrastructure.models.rol import Rol
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/configuracion", tags=["Configuración general"])


class EmpresaIn(BaseModel):
    razon_social: str = Field(min_length=2, max_length=300)
    nit: str = Field(min_length=3, max_length=30)
    nombre_comercial: Optional[str] = Field(default=None, max_length=300)
    ciudad: Optional[str] = Field(default=None, max_length=100)
    direccion: Optional[str] = Field(default=None, max_length=300)
    telefono: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=200)
    regimen_fiscal: Optional[str] = Field(default=None, max_length=100)
    sector: Optional[str] = Field(default=None, max_length=100)


class EmpresaOut(EmpresaIn):
    id: int
    moneda_base: str = "COP"


async def _empresa(db: AsyncSession) -> Optional[ERPEmpresa]:
    # La misma que usan POS y WMS para facturar: la primera activa.
    return (await db.execute(select(ERPEmpresa).where(ERPEmpresa.activo == True)  # noqa: E712
                             .order_by(ERPEmpresa.id).limit(1))).scalar()


def _salida(e: ERPEmpresa) -> EmpresaOut:
    return EmpresaOut(
        id=e.id, razon_social=e.razon_social, nit=e.nit, nombre_comercial=e.nombre_comercial,
        ciudad=e.ciudad, direccion=e.direccion, telefono=e.telefono, email=e.email,
        regimen_fiscal=e.regimen_fiscal, sector=e.sector, moneda_base=e.moneda_base or "COP",
    )


@router.get("/empresa", response_model=Optional[EmpresaOut])
async def ver_empresa(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    e = await _empresa(db)
    return _salida(e) if e else None


@router.put("/empresa", response_model=EmpresaOut)
async def guardar_empresa(
    data: EmpresaIn,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_admin),
):
    e = await _empresa(db)
    nueva = e is None
    if nueva:
        e = ERPEmpresa(pais="Colombia", moneda_base="COP", activo=True,
                       razon_social=data.razon_social.strip(), nit=data.nit.strip())
        db.add(e)
    for campo, valor in data.model_dump().items():
        setattr(e, campo, valor.strip() if isinstance(valor, str) else valor)
    await db.flush()

    if nueva:
        # Plan de cuentas y reglas contables: sin ellos la primera factura falla.
        from app.core import erp_semilla
        await erp_semilla.sembrar_parametros(db)
        await erp_semilla.sembrar_empresa(db, e.id)

    await db.commit()
    await db.refresh(e)
    return _salida(e)


@router.get("/resumen")
async def resumen(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Lo que el centro de configuración muestra: qué está listo y qué falta."""
    from app.infrastructure.models.hcm import HCMConductor
    from app.infrastructure.models.pos import POSCaja
    from app.infrastructure.models.tms import TMSVehiculo
    from app.infrastructure.models.wms import WMSAlmacen, WMSProducto

    async def contar(modelo, *filtros) -> int:
        q = select(func.count()).select_from(modelo)
        for f in filtros:
            q = q.where(f)
        return (await db.execute(q)).scalar() or 0

    return {
        "empresa": (await _empresa(db)) is not None,
        "usuarios": await contar(Usuario, Usuario.activo == True),  # noqa: E712
        "roles": await contar(Rol),
        "almacenes": await contar(WMSAlmacen),
        "productos": await contar(WMSProducto),
        "vehiculos": await contar(TMSVehiculo),
        "conductores": await contar(HCMConductor, HCMConductor.activo_conduccion == True),  # noqa: E712
        "cajas": await contar(POSCaja),
        "resoluciones": await contar(ERPResolucionFacturacion),
    }
