from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from pydantic import BaseModel
from datetime import date
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.proveedor import Proveedor, Contrato, EstadoContrato, TipoProveedor
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/proveedores", tags=["Proveedores"])

TipoProveedorCatalogo = TipoProveedor


class TipoProveedorCreate(BaseModel):
    nombre: str


class TipoProveedorResponse(BaseModel):
    id: int
    nombre: str
    activo: bool
    model_config = {"from_attributes": True}


class ProveedorCreate(BaseModel):
    nit: str
    razon_social: str
    nombre_comercial: Optional[str] = None
    tipo: str = "COMPRA"
    contacto_nombre: Optional[str] = None
    contacto_email: Optional[str] = None
    contacto_telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    codigo_sap: Optional[str] = None


class ProveedorResponse(ProveedorCreate):
    id: int
    activo: bool
    model_config = {"from_attributes": True}


class ContratoCreate(BaseModel):
    numero: str
    proveedor_id: int
    tipo: str
    descripcion: Optional[str] = None
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    valor_unitario: Optional[float] = None
    moneda: str = "COP"
    condiciones_pago: Optional[str] = None
    dias_alerta_vencimiento: int = 30


class ContratoResponse(ContratoCreate):
    id: int
    estado: EstadoContrato
    model_config = {"from_attributes": True}


# ── Tipos de proveedor ────────────────────────────────────────────────────────

@router.get("/tipos", response_model=List[TipoProveedorResponse])
async def listar_tipos(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(TipoProveedorCatalogo)
        .where(TipoProveedorCatalogo.activo == True)
        .order_by(TipoProveedorCatalogo.nombre)
    )
    return list(result.scalars().all())


@router.post("/tipos", response_model=TipoProveedorResponse, status_code=201)
async def crear_tipo(
    data: TipoProveedorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    nombre = data.nombre.strip().upper()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    existing = await db.execute(
        select(TipoProveedorCatalogo).where(TipoProveedorCatalogo.nombre == nombre)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un tipo con ese nombre")
    tipo = TipoProveedorCatalogo(nombre=nombre)
    db.add(tipo)
    await db.commit()
    await db.refresh(tipo)
    return tipo


@router.delete("/tipos/{tipo_id}", status_code=204)
async def eliminar_tipo(
    tipo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    tipo = await db.get(TipoProveedorCatalogo, tipo_id)
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo no encontrado")
    tipo.activo = False
    await db.commit()


# ── Proveedores ───────────────────────────────────────────────────────────────

@router.get("/", response_model=List[ProveedorResponse])
async def listar_proveedores(
    tipo: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(Proveedor).where(Proveedor.activo == True)
    if tipo:
        query = query.where(Proveedor.tipo == tipo)
    if search:
        query = query.where(
            Proveedor.razon_social.ilike(f"%{search}%") | Proveedor.nit.ilike(f"%{search}%")
        )
    result = await db.execute(query.order_by(Proveedor.razon_social))
    return list(result.scalars().all())


@router.post("/", response_model=ProveedorResponse, status_code=201)
async def crear_proveedor(
    data: ProveedorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    proveedor = Proveedor(**data.model_dump())
    db.add(proveedor)
    await db.flush()
    await db.refresh(proveedor)
    return proveedor


@router.get("/{proveedor_id}", response_model=ProveedorResponse)
async def obtener_proveedor(
    proveedor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Proveedor).where(Proveedor.id == proveedor_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return p


@router.get("/{proveedor_id}/contratos", response_model=List[ContratoResponse])
async def contratos_proveedor(
    proveedor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Contrato).where(Contrato.proveedor_id == proveedor_id).order_by(Contrato.fecha_inicio.desc())
    )
    return list(result.scalars().all())


@router.post("/contratos", response_model=ContratoResponse, status_code=201)
async def crear_contrato(
    data: ContratoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    contrato = Contrato(**data.model_dump())
    db.add(contrato)
    await db.flush()
    await db.refresh(contrato)
    return contrato
