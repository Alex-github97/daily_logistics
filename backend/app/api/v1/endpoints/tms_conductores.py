"""
Conductores administrados desde el TMS (propio de Daily Logistics).

En la plataforma madre los conductores se crean en Gestión Humana: primero el
colaborador y luego su ficha de conductor. Daily Logistics no tiene ese módulo,
así que el TMS los crea en un solo paso. Por debajo se siguen guardando en las
mismas tablas (`hcm_colaborador` + `hcm_conductor`), que son las que leen la
planeación y los viajes: un conductor creado aquí se puede asignar de una vez.

El colaborador se crea con lo mínimo que exige el modelo. La empresa de nómina
que pide cada colaborador se crea sola la primera vez y es una por esquema, o
sea una por cliente.
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.hcm import (
    EscalaOperativaEnum, HCMColaborador, HCMConductor, HCMConductorCobertura,
    HCMConductorDocumento, HCMConductorVehiculoTipo, HCMEmpresa, TipoDocumentoEnum,
    TipoLicenciaEnum, TipoVehiculoAutorizadoEnum,
)

router = APIRouter(prefix="/tms/conductores", tags=["TMS · Conductores"])

_PREFIJO_CODIGO = "COND-"


class ConductorTMSIn(BaseModel):
    # Persona
    tipo_documento: TipoDocumentoEnum = TipoDocumentoEnum.CC
    numero_documento: str = Field(min_length=3, max_length=30)
    nombres: str = Field(min_length=1, max_length=150)
    apellidos: str = Field(min_length=1, max_length=150)
    telefono: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=200)
    ciudad: Optional[str] = Field(default=None, max_length=100)
    # Licencia
    num_licencia: str = Field(min_length=3, max_length=50)
    tipo_licencia: TipoLicenciaEnum
    fecha_expedicion_licencia: date
    fecha_vencimiento_licencia: date
    anos_experiencia: int = Field(default=0, ge=0, le=70)
    restricciones: Optional[str] = None
    vehiculos_tipos: List[TipoVehiculoAutorizadoEnum] = []
    coberturas: List[EscalaOperativaEnum] = []
    activo_conduccion: bool = True

    @field_validator("numero_documento", "num_licencia", "nombres", "apellidos")
    @classmethod
    def _sin_espacios(cls, v: str) -> str:
        return v.strip()

    @field_validator("fecha_vencimiento_licencia")
    @classmethod
    def _vence_despues(cls, v: date, info):
        exp = info.data.get("fecha_expedicion_licencia")
        if exp and v <= exp:
            raise ValueError("La licencia debe vencer después de su fecha de expedición")
        return v


class ConductorTMSOut(BaseModel):
    """Los mismos campos de `/hcm/conductores`, más los de la persona para editarla."""
    id: int
    colaborador_id: int
    colaborador_nombre: Optional[str] = None
    colaborador_documento: Optional[str] = None
    colaborador_codigo: Optional[str] = None
    colaborador_telefono: Optional[str] = None
    colaborador_ciudad: Optional[str] = None
    tipo_documento: Optional[str] = None
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    email: Optional[str] = None
    num_licencia: str
    tipo_licencia: str
    fecha_expedicion_licencia: date
    fecha_vencimiento_licencia: date
    restricciones: Optional[str] = None
    anos_experiencia: int
    activo_conduccion: bool
    vehiculos_tipos: List[str] = []
    coberturas: List[str] = []
    documentos_count: int = 0
    dias_hasta_vencimiento: int = 0
    created_at: Optional[datetime] = None


def _valor(x) -> str:
    return getattr(x, "value", x)


async def _respuesta(db: AsyncSession, cond: HCMConductor) -> ConductorTMSOut:
    colab = await db.get(HCMColaborador, cond.colaborador_id)
    tipos = (await db.execute(select(HCMConductorVehiculoTipo.tipo_vehiculo).where(
        HCMConductorVehiculoTipo.conductor_id == cond.id))).scalars().all()
    escalas = (await db.execute(select(HCMConductorCobertura.escala).where(
        HCMConductorCobertura.conductor_id == cond.id))).scalars().all()
    docs = (await db.execute(select(func.count()).select_from(HCMConductorDocumento).where(
        HCMConductorDocumento.conductor_id == cond.id))).scalar() or 0
    return ConductorTMSOut(
        id=cond.id,
        colaborador_id=cond.colaborador_id,
        colaborador_nombre=f"{colab.nombres} {colab.apellidos}".strip() if colab else None,
        colaborador_documento=colab.numero_documento if colab else None,
        colaborador_codigo=colab.codigo_empleado if colab else None,
        colaborador_telefono=colab.telefono if colab else None,
        colaborador_ciudad=colab.ciudad if colab else None,
        tipo_documento=_valor(colab.tipo_documento) if colab else None,
        nombres=colab.nombres if colab else None,
        apellidos=colab.apellidos if colab else None,
        email=colab.email if colab else None,
        num_licencia=cond.num_licencia,
        tipo_licencia=_valor(cond.tipo_licencia),
        fecha_expedicion_licencia=cond.fecha_expedicion_licencia,
        fecha_vencimiento_licencia=cond.fecha_vencimiento_licencia,
        restricciones=cond.restricciones,
        anos_experiencia=cond.anos_experiencia or 0,
        activo_conduccion=bool(cond.activo_conduccion),
        vehiculos_tipos=[_valor(t) for t in tipos],
        coberturas=[_valor(e) for e in escalas],
        documentos_count=docs,
        dias_hasta_vencimiento=(cond.fecha_vencimiento_licencia - date.today()).days,
        created_at=cond.created_at,
    )


async def _empresa_nomina(db: AsyncSession, ciudad: Optional[str]) -> HCMEmpresa:
    """La empresa a la que pertenece el colaborador; se crea sola la primera vez."""
    emp = (await db.execute(select(HCMEmpresa).order_by(HCMEmpresa.id).limit(1))).scalar()
    if emp:
        return emp
    emp = HCMEmpresa(nombre="Operación de transporte", nit="TMS-CONDUCTORES",
                     ciudad=ciudad or "Bogotá", pais="Colombia", activo=True)
    db.add(emp)
    await db.flush()
    return emp


async def _codigo_nuevo(db: AsyncSession) -> str:
    codigos = (await db.execute(select(HCMColaborador.codigo_empleado).where(
        HCMColaborador.codigo_empleado.like(f"{_PREFIJO_CODIGO}%")))).scalars().all()
    mayor = max((int(c[len(_PREFIJO_CODIGO):]) for c in codigos
                 if c[len(_PREFIJO_CODIGO):].isdigit()), default=0)
    return f"{_PREFIJO_CODIGO}{mayor + 1:04d}"


async def _licencia_libre(db: AsyncSession, num: str, propio: Optional[int] = None) -> None:
    q = select(HCMConductor.id).where(HCMConductor.num_licencia == num)
    if propio:
        q = q.where(HCMConductor.id != propio)
    if (await db.execute(q)).first():
        raise HTTPException(409, f"Ya existe un conductor con la licencia «{num}»")


async def _fijar_listas(db: AsyncSession, cond_id: int, data: ConductorTMSIn) -> None:
    await db.execute(sa_delete(HCMConductorVehiculoTipo).where(HCMConductorVehiculoTipo.conductor_id == cond_id))
    await db.execute(sa_delete(HCMConductorCobertura).where(HCMConductorCobertura.conductor_id == cond_id))
    for tipo in dict.fromkeys(data.vehiculos_tipos):
        db.add(HCMConductorVehiculoTipo(conductor_id=cond_id, tipo_vehiculo=tipo))
    for escala in dict.fromkeys(data.coberturas):
        db.add(HCMConductorCobertura(conductor_id=cond_id, escala=escala))


@router.get("", response_model=List[ConductorTMSOut])
async def listar(
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(HCMConductor).order_by(HCMConductor.id.desc())
    if activo is not None:
        q = q.where(HCMConductor.activo_conduccion == activo)
    return [await _respuesta(db, c) for c in (await db.execute(q)).scalars().all()]


@router.post("", response_model=ConductorTMSOut, status_code=201)
async def crear(
    data: ConductorTMSIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await _licencia_libre(db, data.num_licencia)

    # Si la persona ya existe (por ejemplo, otro rol en la empresa), se reutiliza.
    colab = (await db.execute(select(HCMColaborador).where(
        HCMColaborador.numero_documento == data.numero_documento))).scalar_one_or_none()
    if colab:
        ya = (await db.execute(select(HCMConductor.id).where(
            HCMConductor.colaborador_id == colab.id))).first()
        if ya:
            raise HTTPException(409, f"La persona con documento {data.numero_documento} ya es conductor")
    else:
        emp = await _empresa_nomina(db, data.ciudad)
        colab = HCMColaborador(
            tipo_documento=data.tipo_documento, numero_documento=data.numero_documento,
            nombres=data.nombres, apellidos=data.apellidos, telefono=data.telefono,
            email=data.email, ciudad=data.ciudad, pais="Colombia",
            codigo_empleado=await _codigo_nuevo(db), empresa_id=emp.id,
        )
        db.add(colab)
        await db.flush()

    cond = HCMConductor(
        colaborador_id=colab.id, num_licencia=data.num_licencia, tipo_licencia=data.tipo_licencia,
        fecha_expedicion_licencia=data.fecha_expedicion_licencia,
        fecha_vencimiento_licencia=data.fecha_vencimiento_licencia,
        anos_experiencia=data.anos_experiencia, restricciones=data.restricciones,
        activo_conduccion=data.activo_conduccion,
    )
    db.add(cond)
    await db.flush()
    await _fijar_listas(db, cond.id, data)
    await db.commit()
    await db.refresh(cond)
    return await _respuesta(db, cond)


@router.put("/{conductor_id}", response_model=ConductorTMSOut)
async def actualizar(
    conductor_id: int,
    data: ConductorTMSIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    cond = await db.get(HCMConductor, conductor_id)
    if not cond:
        raise HTTPException(404, "Conductor no encontrado")
    await _licencia_libre(db, data.num_licencia, propio=cond.id)

    colab = await db.get(HCMColaborador, cond.colaborador_id)
    if colab:
        if data.numero_documento != colab.numero_documento:
            otro = (await db.execute(select(HCMColaborador.id).where(
                HCMColaborador.numero_documento == data.numero_documento,
                HCMColaborador.id != colab.id))).first()
            if otro:
                raise HTTPException(409, f"Ya existe otra persona con el documento {data.numero_documento}")
        colab.tipo_documento = data.tipo_documento
        colab.numero_documento = data.numero_documento
        colab.nombres, colab.apellidos = data.nombres, data.apellidos
        colab.telefono, colab.email, colab.ciudad = data.telefono, data.email, data.ciudad

    cond.num_licencia = data.num_licencia
    cond.tipo_licencia = data.tipo_licencia
    cond.fecha_expedicion_licencia = data.fecha_expedicion_licencia
    cond.fecha_vencimiento_licencia = data.fecha_vencimiento_licencia
    cond.anos_experiencia = data.anos_experiencia
    cond.restricciones = data.restricciones
    cond.activo_conduccion = data.activo_conduccion
    await _fijar_listas(db, cond.id, data)
    await db.commit()
    await db.refresh(cond)
    return await _respuesta(db, cond)
