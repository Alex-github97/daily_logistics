"""
Lubricación — configuración, ciclo de vida y evaluación.

Acompaña a `lubricacion.py`, que solo lee boletines por OCR. Acá vive lo demás:
los catálogos que hay que configurar antes de operar, el ciclo de vida de cada
carga de aceite y el motor que convierte números en severidades.

Las rutas cuelgan de `/eam/lube/...` a propósito. Lubricación no es un módulo
aparte: es una capa del CMMS, y el prefijo lo dice para que el control de
acceso por módulo (`ModulosMiddleware`) la trate como parte de EAM y no haya
que contratar nada nuevo.

EL EVALUADOR
Es lo que separa «registrar muestras» de «analizar lubricación». Cada resultado
se compara contra tres clases de límite y se queda con la peor:

  ABSOLUTO      el tope del fabricante o del laboratorio.
  TASA_CAMBIO   cuánto subió por cada 100 unidades de vida desde la muestra
                anterior. Es el que detecta la falla antes de que el valor
                absoluto se salga.
  ESTADISTICO   media + 2σ de la propia flota, y solo cuando hay al menos
                MIN_MUESTRAS_ESTADISTICA mediciones. Con menos historia el
                desvío estándar es ruido y genera alarmas falsas, que es la
                forma más rápida de que un programa de análisis se abandone.
"""
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.eam import EAMActivo
from app.infrastructure.models.lubricacion import (
    LubeMarca, LubeTipoCompartimento, LubeProducto, LubeAplicacion,
    LubeParametro, LubeLimite, LubeLaboratorio, LubeMetodoMuestreo,
    LubeMotivoDrenaje, LubeModoFalla,
    LubeCompartimento, LubeCarga, LubeRelleno,
    LubeMuestra, LubeResultado, LubeDiagnostico,
)

router = APIRouter(prefix="/eam/lube", tags=["CMMS/EAM · Lubricación"])

# Por debajo de esto, la media y el desvío de la flota no son representativos.
MIN_MUESTRAS_ESTADISTICA = 20

# Orden de gravedad, para poder quedarse con la peor de varias evaluaciones.
ORDEN_ESTADO = {"NORMAL": 0, "MARGINAL": 1, "CRITICO": 2}


def _usuario(u: Usuario) -> str:
    return getattr(u, "username", None) or getattr(u, "nombre", None) or "—"


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGOS
# ══════════════════════════════════════════════════════════════════════════════

class MarcaIn(BaseModel):
    nombre: str
    activo: bool = True


class MarcaOut(MarcaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TipoCompIn(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    unidad_vida: str = "HORAS"
    activo: bool = True


class TipoCompOut(TipoCompIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ProductoIn(BaseModel):
    marca_id: int
    nombre: str
    familia: Optional[str] = None
    grado_sae: Optional[str] = None
    grado_iso: Optional[str] = None
    base: Optional[str] = None
    activo: bool = True


class ProductoOut(ProductoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    marca: Optional[str] = None


class AplicacionIn(BaseModel):
    producto_id: int
    tipo_compartimento_id: int
    vida_recomendada: Optional[float] = None
    vida_maxima: Optional[float] = None
    meta_iso4406: Optional[str] = None
    volumen_tipico: Optional[float] = None
    costo_litro: Optional[float] = None
    observaciones: Optional[str] = None
    activo: bool = True


class AplicacionOut(AplicacionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    producto: Optional[str] = None
    tipo_compartimento: Optional[str] = None


class ParametroIn(BaseModel):
    codigo: str
    nombre: str
    unidad: Optional[str] = None
    grupo: str = "PROPIEDAD"
    origen_probable: Optional[str] = None
    es_texto: bool = False
    bidireccional: bool = False
    orden: int = 0
    activo: bool = True


class ParametroOut(ParametroIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LimiteIn(BaseModel):
    parametro_id: int
    tipo_compartimento_id: Optional[int] = None
    producto_id: Optional[int] = None
    compartimento_id: Optional[int] = None
    tipo: str = "ABSOLUTO"
    marginal_min: Optional[float] = None
    marginal_max: Optional[float] = None
    critico_min: Optional[float] = None
    critico_max: Optional[float] = None
    fuente: Optional[str] = "OEM"
    nota: Optional[str] = None
    activo: bool = True


class LimiteOut(LimiteIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parametro: Optional[str] = None
    tipo_compartimento: Optional[str] = None


class SimpleNombreIn(BaseModel):
    """Cuerpo común de los catálogos que solo llevan nombre y estado."""
    nombre: str
    activo: bool = True


class LaboratorioIn(SimpleNombreIn):
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    correo: Optional[str] = None
    dias_respuesta: Optional[int] = None


class LaboratorioOut(LaboratorioIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MetodoIn(SimpleNombreIn):
    calidad: str = "ACEPTABLE"
    descripcion: Optional[str] = None


class MetodoOut(MetodoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MotivoIn(SimpleNombreIn):
    codigo: Optional[str] = None
    categoria: str = "CALENDARIO"
    evitable: bool = False
    descripcion: Optional[str] = None


class MotivoOut(MotivoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ModoFallaIn(BaseModel):
    codigo: str
    nombre: str
    categoria: str = "DESGASTE"
    severidad: str = "MODERADO"
    descripcion: Optional[str] = None
    accion_sugerida: Optional[str] = None
    activo: bool = True


class ModoFallaOut(ModoFallaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


async def _existe_nombre(db: AsyncSession, modelo, nombre: str, excluir: Optional[int] = None,
                         campo: str = "nombre", extra=None) -> bool:
    col = getattr(modelo, campo)
    cond = [func.lower(col) == (nombre or "").strip().lower()]
    if excluir:
        cond.append(modelo.id != excluir)
    if extra is not None:
        cond.append(extra)
    r = await db.execute(select(func.count()).select_from(modelo).where(and_(*cond)))
    return bool(r.scalar())


# ─── Marcas ───────────────────────────────────────────────────────────────────

@router.get("/marcas", response_model=List[MarcaOut])
async def listar_marcas(incluir_inactivos: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(LubeMarca).order_by(LubeMarca.nombre)
    if not incluir_inactivos:
        q = q.where(LubeMarca.activo.is_(True))
    return list((await db.execute(q)).scalars().all())


@router.post("/marcas", response_model=MarcaOut, status_code=201)
async def crear_marca(data: MarcaIn, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre de la marca es obligatorio")
    if await _existe_nombre(db, LubeMarca, nombre):
        raise HTTPException(409, f"Ya existe la marca «{nombre}»")
    obj = LubeMarca(nombre=nombre, activo=data.activo)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/marcas/{mid}", response_model=MarcaOut)
async def editar_marca(mid: int, data: MarcaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeMarca, mid)
    if not obj:
        raise HTTPException(404, "Esa marca no existe")
    nombre = (data.nombre or "").strip()
    if await _existe_nombre(db, LubeMarca, nombre, excluir=mid):
        raise HTTPException(409, f"Ya existe otra marca «{nombre}»")
    obj.nombre, obj.activo = nombre, data.activo
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/marcas/{mid}", status_code=204)
async def borrar_marca(mid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeMarca, mid)
    if not obj:
        raise HTTPException(404, "Esa marca no existe")
    # Se desactiva: puede estar referenciada por productos ya usados en cargas.
    obj.activo = False
    await db.commit()


# ─── Tipos de compartimento ───────────────────────────────────────────────────

@router.get("/tipos-compartimento", response_model=List[TipoCompOut])
async def listar_tipos(incluir_inactivos: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(LubeTipoCompartimento).order_by(LubeTipoCompartimento.nombre)
    if not incluir_inactivos:
        q = q.where(LubeTipoCompartimento.activo.is_(True))
    return list((await db.execute(q)).scalars().all())


@router.post("/tipos-compartimento", response_model=TipoCompOut, status_code=201)
async def crear_tipo(data: TipoCompIn, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio")
    if await _existe_nombre(db, LubeTipoCompartimento, nombre):
        raise HTTPException(409, f"Ya existe el tipo «{nombre}»")
    obj = LubeTipoCompartimento(**{**data.model_dump(), "nombre": nombre})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/tipos-compartimento/{tid}", response_model=TipoCompOut)
async def editar_tipo(tid: int, data: TipoCompIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeTipoCompartimento, tid)
    if not obj:
        raise HTTPException(404, "Ese tipo no existe")
    if await _existe_nombre(db, LubeTipoCompartimento, data.nombre, excluir=tid):
        raise HTTPException(409, "Ya existe otro tipo con ese nombre")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/tipos-compartimento/{tid}", status_code=204)
async def borrar_tipo(tid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeTipoCompartimento, tid)
    if not obj:
        raise HTTPException(404, "Ese tipo no existe")
    obj.activo = False
    await db.commit()


# ─── Productos ────────────────────────────────────────────────────────────────

@router.get("/productos", response_model=List[ProductoOut])
async def listar_productos(marca_id: Optional[int] = None, incluir_inactivos: bool = False,
                           db: AsyncSession = Depends(get_db)):
    q = select(LubeProducto, LubeMarca.nombre).join(
        LubeMarca, LubeMarca.id == LubeProducto.marca_id).order_by(
        LubeMarca.nombre, LubeProducto.nombre)
    if marca_id:
        q = q.where(LubeProducto.marca_id == marca_id)
    if not incluir_inactivos:
        q = q.where(LubeProducto.activo.is_(True))
    salida = []
    for prod, marca in (await db.execute(q)).all():
        d = ProductoOut.model_validate(prod).model_dump()
        d["marca"] = marca
        salida.append(d)
    return salida


@router.post("/productos", response_model=ProductoOut, status_code=201)
async def crear_producto(data: ProductoIn, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre del producto es obligatorio")
    if not await db.get(LubeMarca, data.marca_id):
        raise HTTPException(400, "Esa marca no existe")
    # La unicidad es por marca: dos marcas pueden tener un «15W-40».
    if await _existe_nombre(db, LubeProducto, nombre,
                            extra=(LubeProducto.marca_id == data.marca_id)):
        raise HTTPException(409, f"Esa marca ya tiene el producto «{nombre}»")
    obj = LubeProducto(**{**data.model_dump(), "nombre": nombre})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/productos/{pid}", response_model=ProductoOut)
async def editar_producto(pid: int, data: ProductoIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeProducto, pid)
    if not obj:
        raise HTTPException(404, "Ese producto no existe")
    if await _existe_nombre(db, LubeProducto, data.nombre, excluir=pid,
                            extra=(LubeProducto.marca_id == data.marca_id)):
        raise HTTPException(409, "Esa marca ya tiene otro producto con ese nombre")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/productos/{pid}", status_code=204)
async def borrar_producto(pid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeProducto, pid)
    if not obj:
        raise HTTPException(404, "Ese producto no existe")
    obj.activo = False
    await db.commit()


# ─── Aplicaciones (producto × tipo de compartimento) ──────────────────────────

@router.get("/aplicaciones", response_model=List[AplicacionOut])
async def listar_aplicaciones(producto_id: Optional[int] = None,
                              tipo_compartimento_id: Optional[int] = None,
                              db: AsyncSession = Depends(get_db)):
    q = (select(LubeAplicacion, LubeProducto.nombre, LubeTipoCompartimento.nombre)
         .join(LubeProducto, LubeProducto.id == LubeAplicacion.producto_id)
         .join(LubeTipoCompartimento,
               LubeTipoCompartimento.id == LubeAplicacion.tipo_compartimento_id)
         .where(LubeAplicacion.activo.is_(True))
         .order_by(LubeProducto.nombre))
    if producto_id:
        q = q.where(LubeAplicacion.producto_id == producto_id)
    if tipo_compartimento_id:
        q = q.where(LubeAplicacion.tipo_compartimento_id == tipo_compartimento_id)
    salida = []
    for ap, prod, tipo in (await db.execute(q)).all():
        d = AplicacionOut.model_validate(ap).model_dump()
        d["producto"], d["tipo_compartimento"] = prod, tipo
        salida.append(d)
    return salida


@router.post("/aplicaciones", response_model=AplicacionOut, status_code=201)
async def crear_aplicacion(data: AplicacionIn, db: AsyncSession = Depends(get_db)):
    ya = await db.execute(select(LubeAplicacion).where(and_(
        LubeAplicacion.producto_id == data.producto_id,
        LubeAplicacion.tipo_compartimento_id == data.tipo_compartimento_id)))
    existente = ya.scalar_one_or_none()
    if existente:
        # Reactivar y actualizar es lo que espera quien vuelve a cargarla.
        for k, v in data.model_dump().items():
            setattr(existente, k, v)
        existente.activo = True
        await db.commit(); await db.refresh(existente)
        obj = existente
    else:
        obj = LubeAplicacion(**data.model_dump())
        db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/aplicaciones/{aid}", response_model=AplicacionOut)
async def editar_aplicacion(aid: int, data: AplicacionIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeAplicacion, aid)
    if not obj:
        raise HTTPException(404, "Esa aplicación no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/aplicaciones/{aid}", status_code=204)
async def borrar_aplicacion(aid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeAplicacion, aid)
    if not obj:
        raise HTTPException(404, "Esa aplicación no existe")
    obj.activo = False
    await db.commit()


# ─── Parámetros de análisis ───────────────────────────────────────────────────

@router.get("/parametros", response_model=List[ParametroOut])
async def listar_parametros(grupo: Optional[str] = None, incluir_inactivos: bool = False,
                            db: AsyncSession = Depends(get_db)):
    q = select(LubeParametro).order_by(LubeParametro.orden, LubeParametro.nombre)
    if grupo:
        q = q.where(LubeParametro.grupo == grupo)
    if not incluir_inactivos:
        q = q.where(LubeParametro.activo.is_(True))
    return list((await db.execute(q)).scalars().all())


@router.post("/parametros", response_model=ParametroOut, status_code=201)
async def crear_parametro(data: ParametroIn, db: AsyncSession = Depends(get_db)):
    codigo = (data.codigo or "").strip().lower()
    if not codigo:
        raise HTTPException(400, "El código es obligatorio")
    if await _existe_nombre(db, LubeParametro, codigo, campo="codigo"):
        raise HTTPException(409, f"Ya existe el parámetro «{codigo}»")
    obj = LubeParametro(**{**data.model_dump(), "codigo": codigo})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/parametros/{pid}", response_model=ParametroOut)
async def editar_parametro(pid: int, data: ParametroIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeParametro, pid)
    if not obj:
        raise HTTPException(404, "Ese parámetro no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v.strip().lower() if k == "codigo" and isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/parametros/{pid}", status_code=204)
async def borrar_parametro(pid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeParametro, pid)
    if not obj:
        raise HTTPException(404, "Ese parámetro no existe")
    obj.activo = False
    await db.commit()


# ─── Límites ──────────────────────────────────────────────────────────────────

@router.get("/limites", response_model=List[LimiteOut])
async def listar_limites(tipo_compartimento_id: Optional[int] = None,
                         parametro_id: Optional[int] = None,
                         db: AsyncSession = Depends(get_db)):
    q = (select(LubeLimite, LubeParametro.nombre, LubeTipoCompartimento.nombre)
         .join(LubeParametro, LubeParametro.id == LubeLimite.parametro_id)
         .outerjoin(LubeTipoCompartimento,
                    LubeTipoCompartimento.id == LubeLimite.tipo_compartimento_id)
         .where(LubeLimite.activo.is_(True))
         .order_by(LubeParametro.orden))
    if tipo_compartimento_id:
        q = q.where(LubeLimite.tipo_compartimento_id == tipo_compartimento_id)
    if parametro_id:
        q = q.where(LubeLimite.parametro_id == parametro_id)
    salida = []
    for lim, par, tipo in (await db.execute(q)).all():
        d = LimiteOut.model_validate(lim).model_dump()
        d["parametro"], d["tipo_compartimento"] = par, tipo
        salida.append(d)
    return salida


@router.post("/limites", response_model=LimiteOut, status_code=201)
async def crear_limite(data: LimiteIn, db: AsyncSession = Depends(get_db)):
    if data.tipo not in ("ABSOLUTO", "ESTADISTICO", "TASA_CAMBIO"):
        raise HTTPException(400, "El tipo debe ser ABSOLUTO, ESTADISTICO o TASA_CAMBIO")
    if all(v is None for v in (data.marginal_min, data.marginal_max,
                               data.critico_min, data.critico_max)):
        raise HTTPException(
            400, "Hay que definir al menos un umbral; un límite sin números no evalúa nada")
    obj = LubeLimite(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/limites/{lid}", response_model=LimiteOut)
async def editar_limite(lid: int, data: LimiteIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeLimite, lid)
    if not obj:
        raise HTTPException(404, "Ese límite no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/limites/{lid}", status_code=204)
async def borrar_limite(lid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeLimite, lid)
    if not obj:
        raise HTTPException(404, "Ese límite no existe")
    obj.activo = False
    await db.commit()


# ─── Catálogos simples (laboratorios, métodos, motivos, modos de falla) ───────

def _cruds_simples(ruta: str, modelo, EntradaModel, SalidaModel, etiqueta: str):
    """Genera el CRUD de los catálogos que se comportan igual.

    Se escriben por generador y no a mano cuatro veces porque son idénticos
    salvo el modelo: cuatro copias del mismo código son cuatro sitios donde
    corregir el mismo error.
    """

    @router.get(f"/{ruta}", response_model=List[SalidaModel], name=f"listar_{ruta}")
    async def _listar(incluir_inactivos: bool = False, db: AsyncSession = Depends(get_db)):
        q = select(modelo).order_by(modelo.nombre)
        if not incluir_inactivos:
            q = q.where(modelo.activo.is_(True))
        return list((await db.execute(q)).scalars().all())

    @router.post(f"/{ruta}", response_model=SalidaModel, status_code=201, name=f"crear_{ruta}")
    async def _crear(data: EntradaModel, db: AsyncSession = Depends(get_db)):
        nombre = (data.nombre or "").strip()
        if not nombre:
            raise HTTPException(400, "El nombre es obligatorio")
        if await _existe_nombre(db, modelo, nombre):
            raise HTTPException(409, f"Ya existe {etiqueta} «{nombre}»")
        obj = modelo(**{**data.model_dump(), "nombre": nombre})
        db.add(obj); await db.commit(); await db.refresh(obj)
        return obj

    @router.put(f"/{ruta}/{{oid}}", response_model=SalidaModel, name=f"editar_{ruta}")
    async def _editar(oid: int, data: EntradaModel, db: AsyncSession = Depends(get_db)):
        obj = await db.get(modelo, oid)
        if not obj:
            raise HTTPException(404, f"No existe {etiqueta} con ese identificador")
        if await _existe_nombre(db, modelo, data.nombre, excluir=oid):
            raise HTTPException(409, "Ya existe otro con ese nombre")
        for k, v in data.model_dump().items():
            setattr(obj, k, v)
        await db.commit(); await db.refresh(obj)
        return obj

    @router.delete(f"/{ruta}/{{oid}}", status_code=204, name=f"borrar_{ruta}")
    async def _borrar(oid: int, db: AsyncSession = Depends(get_db)):
        obj = await db.get(modelo, oid)
        if not obj:
            raise HTTPException(404, f"No existe {etiqueta} con ese identificador")
        obj.activo = False
        await db.commit()


_cruds_simples("laboratorios", LubeLaboratorio, LaboratorioIn, LaboratorioOut, "el laboratorio")
_cruds_simples("metodos-muestreo", LubeMetodoMuestreo, MetodoIn, MetodoOut, "el método")
_cruds_simples("motivos-drenaje", LubeMotivoDrenaje, MotivoIn, MotivoOut, "el motivo")


@router.get("/modos-falla", response_model=List[ModoFallaOut])
async def listar_modos(incluir_inactivos: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(LubeModoFalla).order_by(LubeModoFalla.categoria, LubeModoFalla.nombre)
    if not incluir_inactivos:
        q = q.where(LubeModoFalla.activo.is_(True))
    return list((await db.execute(q)).scalars().all())


@router.post("/modos-falla", response_model=ModoFallaOut, status_code=201)
async def crear_modo(data: ModoFallaIn, db: AsyncSession = Depends(get_db)):
    codigo = (data.codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(400, "El código es obligatorio")
    if await _existe_nombre(db, LubeModoFalla, codigo, campo="codigo"):
        raise HTTPException(409, f"Ya existe el modo de falla «{codigo}»")
    obj = LubeModoFalla(**{**data.model_dump(), "codigo": codigo})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/modos-falla/{mid}", response_model=ModoFallaOut)
async def editar_modo(mid: int, data: ModoFallaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeModoFalla, mid)
    if not obj:
        raise HTTPException(404, "Ese modo de falla no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v.strip().upper() if k == "codigo" and isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/modos-falla/{mid}", status_code=204)
async def borrar_modo(mid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(LubeModoFalla, mid)
    if not obj:
        raise HTTPException(404, "Ese modo de falla no existe")
    obj.activo = False
    await db.commit()
