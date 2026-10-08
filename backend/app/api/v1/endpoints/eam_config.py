"""
Centros de costo y tipos de trabajo del CMMS.

Estos dos catálogos se mostraban en la pantalla de configuración pero no
existían: la página los tenía escritos a mano y los guardaba en memoria, así
que lo que se creaba desaparecía al recargar. Acá quedan de verdad.

El centro de costo tiene tabla propia y no va al catálogo maestro porque carga
atributos del negocio —ciudad y plataforma—, que es la regla del módulo para
decidir dónde vive cada cosa.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.infrastructure.models.eam import EAMCentroCosto, EAMTipoTrabajo

router = APIRouter(prefix="/eam", tags=["CMMS/EAM"])


# ─── Centros de costo ─────────────────────────────────────────────────────────

class CentroCostoBase(BaseModel):
    codigo: str
    nombre: str
    ciudad: Optional[str] = None
    plataforma: Optional[str] = None
    activo: bool = True


class CentroCostoResponse(CentroCostoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.get("/catalogos/centros-costo", response_model=List[CentroCostoResponse])
async def listar_centros(db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMCentroCosto).where(EAMCentroCosto.activo == True)  # noqa: E712
        .order_by(EAMCentroCosto.codigo))
    return list(r.scalars().all())


@router.post("/catalogos/centros-costo", response_model=CentroCostoResponse, status_code=201)
async def crear_centro(data: CentroCostoBase, db: AsyncSession = Depends(get_db)):
    codigo = (data.codigo or "").strip()
    if not codigo:
        raise HTTPException(400, "El código es obligatorio")
    ya = await db.execute(select(func.count()).select_from(EAMCentroCosto).where(
        func.lower(EAMCentroCosto.codigo) == codigo.lower()))
    if ya.scalar():
        raise HTTPException(409, f"Ya existe un centro de costo con el código «{codigo}»")
    obj = EAMCentroCosto(**{**data.model_dump(), "codigo": codigo})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/catalogos/centros-costo/{cid}", response_model=CentroCostoResponse)
async def editar_centro(cid: int, data: CentroCostoBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMCentroCosto, cid)
    if not obj:
        raise HTTPException(404, "Ese centro de costo no existe")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(obj, campo, valor)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/catalogos/centros-costo/{cid}", status_code=204)
async def borrar_centro(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMCentroCosto, cid)
    if not obj:
        raise HTTPException(404, "Ese centro de costo no existe")
    # Se desactiva en vez de borrarse: puede estar referenciado en costos ya
    # registrados, y borrarlo dejaría esos costos sin a dónde imputarse.
    obj.activo = False
    await db.commit()


# ─── Tipos de trabajo ─────────────────────────────────────────────────────────

CATEGORIAS = ("PREVENTIVO", "CORRECTIVO", "PREDICTIVO", "INSPECCION", "EMERGENCIA")


class TipoTrabajoBase(BaseModel):
    nombre: str
    categoria: Optional[str] = None
    descripcion: Optional[str] = None
    # Texto y no número: hay trabajos cuya duración es "Variable".
    duracion: Optional[str] = None
    requiere_taller: bool = False
    requiere_materiales: bool = False
    sistema: Optional[str] = None
    subsistema: Optional[str] = None
    activo: bool = True


class TipoTrabajoResponse(TipoTrabajoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int

    # Un tipo de trabajo creado por la ruta corta —o importado— deja estas dos
    # banderas en NULL, y entonces la respuesta no validaba y la pantalla de
    # configuración entera respondía 500. Un NULL acá significa «no se declaró»,
    # que para una bandera es lo mismo que «no»: se traduce y se sigue, en vez
    # de tumbar el listado completo por dos columnas sin llenar.
    @field_validator("requiere_taller", "requiere_materiales", mode="before")
    @classmethod
    def _sin_declarar_es_no(cls, v):
        return False if v is None else v


@router.get("/catalogos/tipos-trabajo-completo", response_model=List[TipoTrabajoResponse])
async def listar_tipos(db: AsyncSession = Depends(get_db)):
    """Con todos los campos.

    La ruta lleva sufijo porque `/catalogos/tipos-trabajo` ya existía devolviendo
    solo nombre y categoría, y hay pantallas que la consumen así.
    """
    r = await db.execute(
        select(EAMTipoTrabajo).where(EAMTipoTrabajo.activo == True)  # noqa: E712
        .order_by(EAMTipoTrabajo.nombre))
    return list(r.scalars().all())


def _validar_categoria(categoria: Optional[str]) -> Optional[str]:
    if not categoria:
        return None
    valor = categoria.strip().upper()
    if valor not in CATEGORIAS:
        raise HTTPException(
            400,
            f"«{categoria}» no es una categoría válida. Use una de: {', '.join(CATEGORIAS)}.",
        )
    return valor


@router.post("/catalogos/tipos-trabajo-completo", response_model=TipoTrabajoResponse,
             status_code=201)
async def crear_tipo(data: TipoTrabajoBase, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio")
    ya = await db.execute(select(func.count()).select_from(EAMTipoTrabajo).where(
        func.lower(EAMTipoTrabajo.nombre) == nombre.lower()))
    if ya.scalar():
        raise HTTPException(409, f"Ya existe un tipo de trabajo llamado «{nombre}»")
    obj = EAMTipoTrabajo(**{
        **data.model_dump(), "nombre": nombre,
        "categoria": _validar_categoria(data.categoria),
    })
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/catalogos/tipos-trabajo-completo/{tid}", response_model=TipoTrabajoResponse)
async def editar_tipo(tid: int, data: TipoTrabajoBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMTipoTrabajo, tid)
    if not obj:
        raise HTTPException(404, "Ese tipo de trabajo no existe")
    cambios = data.model_dump(exclude_unset=True)
    if "categoria" in cambios:
        cambios["categoria"] = _validar_categoria(cambios["categoria"])
    for campo, valor in cambios.items():
        setattr(obj, campo, valor)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/catalogos/tipos-trabajo-completo/{tid}", status_code=204)
async def borrar_tipo(tid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMTipoTrabajo, tid)
    if not obj:
        raise HTTPException(404, "Ese tipo de trabajo no existe")
    # Se desactiva: las OTs ya emitidas lo referencian.
    obj.activo = False
    await db.commit()

# ─── Umbrales de aviso ────────────────────────────────────────────────────────

@router.get("/parametros")
async def listar_parametros_eam(db: AsyncSession = Depends(get_db)):
    from app.core.parametros_eam import PARAMETROS_EAM, leer_parametros_eam
    valores = await leer_parametros_eam(db)
    return [{"clave": k, "valor": valores[k], **d} for k, d in PARAMETROS_EAM.items()]


@router.put("/parametros")
async def guardar_parametros_eam(data: dict, db: AsyncSession = Depends(get_db)):
    from app.core.parametros_eam import PARAMETROS_EAM
    from app.infrastructure.models.eam import EAMParametro
    for clave, valor in data.items():
        if clave not in PARAMETROS_EAM:
            raise HTTPException(422, f"Parámetro desconocido: {clave}")
        d = PARAMETROS_EAM[clave]
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(422, f"{d['descripcion']}: debe ser un número")
        if not d["min"] <= valor <= d["max"]:
            raise HTTPException(422, f"{d['descripcion']}: entre {d['min']} y {d['max']}")
        fila = (await db.execute(select(EAMParametro).where(EAMParametro.clave == clave))).scalar_one_or_none()
        if fila:
            fila.valor = valor
        else:
            db.add(EAMParametro(clave=clave, valor=valor))
    await db.commit()
    return await listar_parametros_eam(db)


# ─── Horas programadas por activo (base de la disponibilidad) ────────────────

@router.get("/disponibilidad-activos")
async def horas_por_activo(db: AsyncSession = Depends(get_db)):
    from app.infrastructure.models.eam import EAMActivo
    filas = (await db.execute(select(EAMActivo).where(EAMActivo.activo.is_(True)).order_by(EAMActivo.codigo))).scalars().all()
    return [{"id": a.id, "codigo": a.codigo, "nombre": a.nombre, "tipo_activo": a.tipo_activo,
             "centro_costo": a.centro_costo, "horas_programadas_mes": a.horas_programadas_mes} for a in filas]


class HorasIn(BaseModel):
    activo_ids: List[int]
    horas_programadas_mes: Optional[float] = None

    @field_validator("horas_programadas_mes")
    @classmethod
    def _rango(cls, v):
        if v is not None and not 0 < v <= 744:
            raise ValueError("Entre 1 y 744 horas al mes (31 días × 24 h)")
        return v


@router.put("/disponibilidad-activos")
async def fijar_horas(data: HorasIn, db: AsyncSession = Depends(get_db)):
    """Fija las horas programadas de uno o varios activos a la vez (por
    ejemplo, todos los montacargas a un turno). Vacío = operación continua."""
    from app.infrastructure.models.eam import EAMActivo
    filas = (await db.execute(select(EAMActivo).where(EAMActivo.id.in_(data.activo_ids)))).scalars().all()
    for a in filas:
        a.horas_programadas_mes = data.horas_programadas_mes
    await db.commit()
    return {"actualizados": len(filas)}
