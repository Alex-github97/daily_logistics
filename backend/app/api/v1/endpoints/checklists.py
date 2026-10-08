"""
Checklists — configuración.

La jerarquía, en el orden en que se llena:

    Clasificación → cómo se responde (Bueno/Regular/Malo, Sí/No, un número…)
    Sistema       → el sistema mecánico o electrónico del activo
    Pregunta      → pertenece a un sistema y usa una clasificación
    Plantilla     → escoge preguntas del banco y declara a qué activos aplica

Las preguntas son un banco global. «Nivel de aceite del motor» se escribe una
vez y sirve en la preoperacional diaria, en la entrega de turno y en la
revisión mensual; y el tablero puede contar cuántas veces falló esa pregunta
sumando todas las plantillas, cosa imposible cuando cada plantilla tenía copias
propias.

La ejecución vive en `checklists_ejecucion.py`.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.infrastructure.models.eam import EAMActivo
from app.infrastructure.models.checklist import (
    ChkClasificacion, ChkOpcion, ChkSistema, ChkPregunta,
    ChkCategoria, ChkHallazgo,
    ChkPlantilla, ChkPlantillaTipo, ChkPlantillaPregunta, ChkEjecucion,
)

router = APIRouter(prefix="/eam/chk", tags=["CMMS/EAM · Checklists"])

TIPOS_CLASIFICACION = {
    "OPCIONES": "Escoger una opción",
    "NUMERO": "Un número, con rango aceptable",
    "TEXTO": "Texto libre",
    "FECHA": "Una fecha",
}


async def _repetido(db: AsyncSession, modelo, campo: str, valor: str,
                    excluir: Optional[int] = None, extra=None) -> bool:
    col = getattr(modelo, campo)
    cond = [func.lower(col) == (valor or "").strip().lower()]
    if excluir:
        cond.append(modelo.id != excluir)
    if extra is not None:
        cond.append(extra)
    r = await db.execute(select(func.count()).select_from(modelo).where(and_(*cond)))
    return bool(r.scalar())


async def _subir_version(db: AsyncSession, plantilla_id: int) -> None:
    """Sube la versión si la plantilla ya se usó.

    Solo si ya se usó: mientras se arma, cada pregunta que se agrega subiría la
    versión y el número perdería todo significado.
    """
    r = await db.execute(select(func.count()).select_from(ChkEjecucion)
                         .where(ChkEjecucion.plantilla_id == plantilla_id))
    if r.scalar():
        p = await db.get(ChkPlantilla, plantilla_id)
        if p:
            p.version = (p.version or 1) + 1


# ══════════════════════════════════════════════════════════════════════════════
# 1 · CLASIFICACIONES Y SUS OPCIONES
# ══════════════════════════════════════════════════════════════════════════════

class OpcionIn(BaseModel):
    nombre: str
    orden: int = 0
    conforme: Optional[bool] = None
    puntaje: float = 1
    color: Optional[str] = None


class OpcionOut(OpcionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clasificacion_id: int


class ClasificacionIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    tipo: str = "OPCIONES"
    unidad: Optional[str] = None
    valor_min: Optional[float] = None
    valor_max: Optional[float] = None
    activo: bool = True
    opciones: List[OpcionIn] = []


class ClasificacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    unidad: Optional[str] = None
    valor_min: Optional[float] = None
    valor_max: Optional[float] = None
    activo: bool
    opciones: List[OpcionOut] = []
    usos: Optional[int] = None


@router.get("/tipos-clasificacion", response_model=List[Dict[str, str]])
async def tipos_clasificacion():
    return [{"clave": k, "label": v} for k, v in TIPOS_CLASIFICACION.items()]


async def _con_opciones(db: AsyncSession, filas: List[ChkClasificacion]) -> List[Dict[str, Any]]:
    ids = [c.id for c in filas]
    por_clasificacion: Dict[int, List[Any]] = {}
    usos: Dict[int, int] = {}
    if ids:
        r = await db.execute(select(ChkOpcion).where(and_(
            ChkOpcion.clasificacion_id.in_(ids), ChkOpcion.activo.is_(True)))
            .order_by(ChkOpcion.orden, ChkOpcion.id))
        for o in r.scalars().all():
            por_clasificacion.setdefault(o.clasificacion_id, []).append(
                OpcionOut.model_validate(o).model_dump())
        r = await db.execute(select(ChkPregunta.clasificacion_id, func.count(ChkPregunta.id))
                             .where(and_(ChkPregunta.clasificacion_id.in_(ids),
                                         ChkPregunta.activo.is_(True)))
                             .group_by(ChkPregunta.clasificacion_id))
        usos = {k: v for k, v in r.all()}

    salida = []
    for c in filas:
        d = ClasificacionOut.model_validate(c).model_dump()
        d["opciones"] = por_clasificacion.get(c.id, [])
        d["usos"] = usos.get(c.id, 0)
        salida.append(d)
    return salida


@router.get("/clasificaciones", response_model=List[ClasificacionOut])
async def listar_clasificaciones(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ChkClasificacion)
                         .where(ChkClasificacion.activo.is_(True))
                         .order_by(ChkClasificacion.nombre))
    return await _con_opciones(db, list(r.scalars().all()))


@router.post("/clasificaciones", response_model=ClasificacionOut, status_code=201)
async def crear_clasificacion(data: ClasificacionIn, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio")
    if data.tipo not in TIPOS_CLASIFICACION:
        raise HTTPException(400, f"Tipo no válido: {', '.join(TIPOS_CLASIFICACION)}")
    if data.tipo == "OPCIONES" and len(data.opciones) < 2:
        raise HTTPException(
            400, "Una clasificación de opciones necesita al menos dos: con una sola no hay "
                 "nada que escoger")
    if await _repetido(db, ChkClasificacion, "nombre", nombre):
        raise HTTPException(409, f"Ya existe la clasificación «{nombre}»")

    obj = ChkClasificacion(**data.model_dump(exclude={"opciones"}), )
    obj.nombre = nombre
    db.add(obj); await db.flush()
    for i, o in enumerate(data.opciones):
        db.add(ChkOpcion(clasificacion_id=obj.id, **{**o.model_dump(),
                                                     "orden": o.orden or i}))
    await db.commit(); await db.refresh(obj)
    return (await _con_opciones(db, [obj]))[0]


@router.put("/clasificaciones/{cid}", response_model=ClasificacionOut)
async def editar_clasificacion(cid: int, data: ClasificacionIn,
                               db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkClasificacion, cid)
    if not obj:
        raise HTTPException(404, "Esa clasificación no existe")
    if await _repetido(db, ChkClasificacion, "nombre", data.nombre, excluir=cid):
        raise HTTPException(409, "Ya existe otra clasificación con ese nombre")

    for k, v in data.model_dump(exclude={"opciones"}).items():
        setattr(obj, k, v)

    # Las opciones se reemplazan por las que lleguen. Las que desaparecen se
    # desactivan y no se borran: hay respuestas históricas apuntándoles, y la
    # inspección de ayer tiene que seguir mostrando qué se respondió.
    r = await db.execute(select(ChkOpcion).where(ChkOpcion.clasificacion_id == cid))
    existentes = {o.nombre.strip().lower(): o for o in r.scalars().all()}
    vistos = set()
    for i, fila in enumerate(data.opciones):
        clave = fila.nombre.strip().lower()
        vistos.add(clave)
        o = existentes.get(clave)
        if not o:
            o = ChkOpcion(clasificacion_id=cid, nombre=fila.nombre.strip())
            db.add(o)
        o.orden = fila.orden or i
        o.conforme = fila.conforme
        o.puntaje = fila.puntaje
        o.color = fila.color
        o.activo = True
    for clave, o in existentes.items():
        if clave not in vistos:
            o.activo = False

    await db.commit(); await db.refresh(obj)
    return (await _con_opciones(db, [obj]))[0]


@router.delete("/clasificaciones/{cid}", status_code=204)
async def borrar_clasificacion(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkClasificacion, cid)
    if not obj:
        raise HTTPException(404, "Esa clasificación no existe")
    r = await db.execute(select(func.count()).select_from(ChkPregunta).where(and_(
        ChkPregunta.clasificacion_id == cid, ChkPregunta.activo.is_(True))))
    usos = r.scalar() or 0
    if usos:
        raise HTTPException(
            409, f"No se puede desactivar: {usos} preguntas la están usando. Cámbieles la "
                 f"clasificación primero.")
    obj.activo = False
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# 2 · SISTEMAS
# ══════════════════════════════════════════════════════════════════════════════

class SistemaIn(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    orden: int = 0
    activo: bool = True


class SistemaOut(SistemaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    preguntas: Optional[int] = None


@router.get("/sistemas", response_model=List[SistemaOut])
async def listar_sistemas(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ChkSistema).where(ChkSistema.activo.is_(True))
                         .order_by(ChkSistema.orden, ChkSistema.nombre))
    filas = list(r.scalars().all())
    r = await db.execute(select(ChkPregunta.sistema_id, func.count(ChkPregunta.id))
                         .where(ChkPregunta.activo.is_(True))
                         .group_by(ChkPregunta.sistema_id))
    conteo = {k: v for k, v in r.all()}
    salida = []
    for s in filas:
        d = SistemaOut.model_validate(s).model_dump()
        d["preguntas"] = conteo.get(s.id, 0)
        salida.append(d)
    return salida


@router.post("/sistemas", response_model=SistemaOut, status_code=201)
async def crear_sistema(data: SistemaIn, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio")
    if await _repetido(db, ChkSistema, "nombre", nombre):
        raise HTTPException(409, f"Ya existe el sistema «{nombre}»")
    obj = ChkSistema(**{**data.model_dump(), "nombre": nombre})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return SistemaOut.model_validate(obj)


@router.put("/sistemas/{sid}", response_model=SistemaOut)
async def editar_sistema(sid: int, data: SistemaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkSistema, sid)
    if not obj:
        raise HTTPException(404, "Ese sistema no existe")
    if await _repetido(db, ChkSistema, "nombre", data.nombre, excluir=sid):
        raise HTTPException(409, "Ya existe otro sistema con ese nombre")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return SistemaOut.model_validate(obj)


@router.delete("/sistemas/{sid}", status_code=204)
async def borrar_sistema(sid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkSistema, sid)
    if not obj:
        raise HTTPException(404, "Ese sistema no existe")
    r = await db.execute(select(func.count()).select_from(ChkPregunta).where(and_(
        ChkPregunta.sistema_id == sid, ChkPregunta.activo.is_(True))))
    if r.scalar():
        raise HTTPException(
            409, "No se puede desactivar: tiene preguntas activas. Muévalas o desactívelas "
                 "primero.")
    obj.activo = False
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# 3 · BANCO DE PREGUNTAS
# ══════════════════════════════════════════════════════════════════════════════

class PreguntaIn(BaseModel):
    sistema_id: int
    clasificacion_id: int
    texto: str
    ayuda: Optional[str] = None
    orden: int = 0
    critico: bool = False
    requiere_foto: bool = False
    exige_observacion_no_conforme: bool = True
    peso: float = 1
    activo: bool = True


class PreguntaOut(PreguntaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sistema: Optional[str] = None
    clasificacion: Optional[str] = None
    clasificacion_tipo: Optional[str] = None
    usos: Optional[int] = None


@router.get("/preguntas", response_model=List[PreguntaOut])
async def listar_preguntas(sistema_id: Optional[int] = None,
                           buscar: Optional[str] = None,
                           db: AsyncSession = Depends(get_db)):
    q = (select(ChkPregunta, ChkSistema.nombre, ChkClasificacion.nombre,
                ChkClasificacion.tipo)
         .join(ChkSistema, ChkSistema.id == ChkPregunta.sistema_id)
         .join(ChkClasificacion, ChkClasificacion.id == ChkPregunta.clasificacion_id)
         .where(ChkPregunta.activo.is_(True))
         .order_by(ChkSistema.orden, ChkSistema.nombre, ChkPregunta.orden, ChkPregunta.id))
    if sistema_id:
        q = q.where(ChkPregunta.sistema_id == sistema_id)
    if buscar:
        q = q.where(ChkPregunta.texto.ilike(f"%{buscar}%"))
    filas = (await db.execute(q)).all()

    ids = [p.id for p, *_ in filas]
    usos: Dict[int, int] = {}
    if ids:
        r = await db.execute(
            select(ChkPlantillaPregunta.pregunta_id, func.count(ChkPlantillaPregunta.id))
            .where(and_(ChkPlantillaPregunta.pregunta_id.in_(ids),
                        ChkPlantillaPregunta.activo.is_(True)))
            .group_by(ChkPlantillaPregunta.pregunta_id))
        usos = {k: v for k, v in r.all()}

    salida = []
    for p, sistema, clasificacion, tipo in filas:
        d = PreguntaOut.model_validate(p).model_dump()
        d.update(sistema=sistema, clasificacion=clasificacion,
                 clasificacion_tipo=tipo, usos=usos.get(p.id, 0))
        salida.append(d)
    return salida


@router.post("/preguntas", response_model=PreguntaOut, status_code=201)
async def crear_pregunta(data: PreguntaIn, db: AsyncSession = Depends(get_db)):
    if not (data.texto or "").strip():
        raise HTTPException(400, "El texto de la pregunta es obligatorio")
    if not await db.get(ChkSistema, data.sistema_id):
        raise HTTPException(400, "Ese sistema no existe")
    if not await db.get(ChkClasificacion, data.clasificacion_id):
        raise HTTPException(400, "Esa clasificación no existe")
    obj = ChkPregunta(**{**data.model_dump(), "texto": data.texto.strip()})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return PreguntaOut.model_validate(obj)


@router.put("/preguntas/{pid}", response_model=PreguntaOut)
async def editar_pregunta(pid: int, data: PreguntaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkPregunta, pid)
    if not obj:
        raise HTTPException(404, "Esa pregunta no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    # Editar una pregunta afecta a todas las plantillas que la usan.
    r = await db.execute(select(ChkPlantillaPregunta.plantilla_id).distinct()
                         .where(ChkPlantillaPregunta.pregunta_id == pid))
    for (plid,) in r.all():
        await _subir_version(db, plid)
    await db.commit(); await db.refresh(obj)
    return PreguntaOut.model_validate(obj)


@router.delete("/preguntas/{pid}", status_code=204)
async def borrar_pregunta(pid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkPregunta, pid)
    if not obj:
        raise HTTPException(404, "Esa pregunta no existe")
    # Nunca se borra: hay respuestas históricas apuntando acá.
    obj.activo = False
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGOS DE APOYO
# ══════════════════════════════════════════════════════════════════════════════

class CategoriaIn(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    color: Optional[str] = None
    activo: bool = True


class CategoriaOut(CategoriaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class HallazgoIn(BaseModel):
    codigo: str
    nombre: str
    categoria: Optional[str] = None
    severidad: str = "MODERADO"
    descripcion: Optional[str] = None
    accion_sugerida: Optional[str] = None
    genera_ot: bool = False
    activo: bool = True


class HallazgoOut(HallazgoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.get("/categorias", response_model=List[CategoriaOut])
async def listar_categorias(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ChkCategoria).where(ChkCategoria.activo.is_(True))
                         .order_by(ChkCategoria.nombre))
    return list(r.scalars().all())


@router.post("/categorias", response_model=CategoriaOut, status_code=201)
async def crear_categoria(data: CategoriaIn, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio")
    if await _repetido(db, ChkCategoria, "nombre", nombre):
        raise HTTPException(409, f"Ya existe la categoría «{nombre}»")
    obj = ChkCategoria(**{**data.model_dump(), "nombre": nombre})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/categorias/{cid}", response_model=CategoriaOut)
async def editar_categoria(cid: int, data: CategoriaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkCategoria, cid)
    if not obj:
        raise HTTPException(404, "Esa categoría no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/categorias/{cid}", status_code=204)
async def borrar_categoria(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkCategoria, cid)
    if not obj:
        raise HTTPException(404, "Esa categoría no existe")
    obj.activo = False
    await db.commit()


@router.get("/hallazgos", response_model=List[HallazgoOut])
async def listar_hallazgos(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ChkHallazgo).where(ChkHallazgo.activo.is_(True))
                         .order_by(ChkHallazgo.categoria, ChkHallazgo.nombre))
    return list(r.scalars().all())


@router.post("/hallazgos", response_model=HallazgoOut, status_code=201)
async def crear_hallazgo(data: HallazgoIn, db: AsyncSession = Depends(get_db)):
    codigo = (data.codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(400, "El código es obligatorio")
    if await _repetido(db, ChkHallazgo, "codigo", codigo):
        raise HTTPException(409, f"Ya existe el hallazgo «{codigo}»")
    obj = ChkHallazgo(**{**data.model_dump(), "codigo": codigo})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/hallazgos/{hid}", response_model=HallazgoOut)
async def editar_hallazgo(hid: int, data: HallazgoIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkHallazgo, hid)
    if not obj:
        raise HTTPException(404, "Ese hallazgo no existe")
    for k, v in data.model_dump().items():
        setattr(obj, k, v.strip().upper() if k == "codigo" and isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/hallazgos/{hid}", status_code=204)
async def borrar_hallazgo(hid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkHallazgo, hid)
    if not obj:
        raise HTTPException(404, "Ese hallazgo no existe")
    obj.activo = False
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# 4 · PLANTILLAS
# ══════════════════════════════════════════════════════════════════════════════

class TipoAplicaIn(BaseModel):
    tipo_activo: str
    marca: Optional[str] = None
    linea: Optional[str] = None


class TipoAplicaOut(TipoAplicaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PlantillaIn(BaseModel):
    codigo: str
    nombre: str
    categoria_id: Optional[int] = None
    descripcion: Optional[str] = None
    periodicidad_dias: Optional[int] = None
    requiere_firma: bool = False
    umbral_aprobacion: float = 100
    critico_reprueba: bool = True
    genera_ot: bool = False
    pide_medidor: bool = False
    activo: bool = True


class PlantillaOut(PlantillaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int
    categoria: Optional[str] = None
    total_preguntas: Optional[int] = None
    ejecuciones: Optional[int] = None
    tipos: List[TipoAplicaOut] = []


async def _plantillas_detalladas(db: AsyncSession, filas) -> List[Dict[str, Any]]:
    ids = [p.id for p, _ in filas]
    preguntas: Dict[int, int] = {}
    ejecuciones: Dict[int, int] = {}
    tipos: Dict[int, List[Any]] = {}
    if ids:
        r = await db.execute(
            select(ChkPlantillaPregunta.plantilla_id, func.count(ChkPlantillaPregunta.id))
            .where(and_(ChkPlantillaPregunta.plantilla_id.in_(ids),
                        ChkPlantillaPregunta.activo.is_(True)))
            .group_by(ChkPlantillaPregunta.plantilla_id))
        preguntas = {k: v for k, v in r.all()}
        r = await db.execute(select(ChkEjecucion.plantilla_id, func.count(ChkEjecucion.id))
                             .where(ChkEjecucion.plantilla_id.in_(ids))
                             .group_by(ChkEjecucion.plantilla_id))
        ejecuciones = {k: v for k, v in r.all()}
        r = await db.execute(select(ChkPlantillaTipo)
                             .where(ChkPlantillaTipo.plantilla_id.in_(ids)))
        for t in r.scalars().all():
            tipos.setdefault(t.plantilla_id, []).append(
                TipoAplicaOut.model_validate(t).model_dump())

    salida = []
    for p, categoria in filas:
        d = PlantillaOut.model_validate(p).model_dump()
        d.update(categoria=categoria,
                 total_preguntas=preguntas.get(p.id, 0),
                 ejecuciones=ejecuciones.get(p.id, 0),
                 tipos=tipos.get(p.id, []))
        salida.append(d)
    return salida


@router.get("/plantillas", response_model=List[PlantillaOut])
async def listar_plantillas(activo_id: Optional[int] = None,
                            db: AsyncSession = Depends(get_db)):
    """Las plantillas. Con `activo_id`, solo las que aplican a ese equipo.

    Es lo que hace que al elegir el activo aparezcan únicamente los checklists
    configurados para su categoría, en vez de la lista completa.
    """
    q = (select(ChkPlantilla, ChkCategoria.nombre)
         .outerjoin(ChkCategoria, ChkCategoria.id == ChkPlantilla.categoria_id)
         .where(ChkPlantilla.activo.is_(True)).order_by(ChkPlantilla.codigo))

    if activo_id:
        activo = await db.get(EAMActivo, activo_id)
        if not activo:
            raise HTTPException(404, "Ese activo no existe")
        # Aplica si algún renglón de tipo coincide. La marca y la línea afinan:
        # vacías significan «cualquiera dentro de ese tipo».
        coincide = (
            select(ChkPlantillaTipo.plantilla_id)
            .where(and_(
                ChkPlantillaTipo.tipo_activo == activo.tipo_activo,
                or_(ChkPlantillaTipo.marca.is_(None), ChkPlantillaTipo.marca == activo.marca),
                or_(ChkPlantillaTipo.linea.is_(None), ChkPlantillaTipo.linea == activo.linea)))
        )
        q = q.where(ChkPlantilla.id.in_(coincide))

    return await _plantillas_detalladas(db, (await db.execute(q)).all())


@router.post("/plantillas", response_model=PlantillaOut, status_code=201)
async def crear_plantilla(data: PlantillaIn, db: AsyncSession = Depends(get_db)):
    codigo = (data.codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(400, "El código es obligatorio")
    if await _repetido(db, ChkPlantilla, "codigo", codigo):
        raise HTTPException(409, f"Ya existe una plantilla con el código «{codigo}»")
    obj = ChkPlantilla(**{**data.model_dump(), "codigo": codigo}, version=1)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return (await _plantillas_detalladas(db, [(obj, None)]))[0]


@router.put("/plantillas/{pid}", response_model=PlantillaOut)
async def editar_plantilla(pid: int, data: PlantillaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkPlantilla, pid)
    if not obj:
        raise HTTPException(404, "Esa plantilla no existe")
    cambia_calificacion = (obj.umbral_aprobacion != data.umbral_aprobacion
                           or obj.critico_reprueba != data.critico_reprueba)
    for k, v in data.model_dump().items():
        setattr(obj, k, v.strip().upper() if k == "codigo" and isinstance(v, str) else v)
    if cambia_calificacion:
        await _subir_version(db, pid)
    await db.commit(); await db.refresh(obj)
    return (await _plantillas_detalladas(db, [(obj, None)]))[0]


@router.delete("/plantillas/{pid}", status_code=204)
async def borrar_plantilla(pid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkPlantilla, pid)
    if not obj:
        raise HTTPException(404, "Esa plantilla no existe")
    obj.activo = False
    await db.commit()


class DuplicarIn(BaseModel):
    codigo: str
    nombre: str


@router.post("/plantillas/{pid}/duplicar", response_model=PlantillaOut, status_code=201)
async def duplicar(pid: int, data: DuplicarIn, db: AsyncSession = Depends(get_db)):
    """Copia una plantilla con sus preguntas y sus tipos de activo."""
    origen = await db.get(ChkPlantilla, pid)
    if not origen:
        raise HTTPException(404, "Esa plantilla no existe")
    codigo = (data.codigo or "").strip().upper()
    if await _repetido(db, ChkPlantilla, "codigo", codigo):
        raise HTTPException(409, f"Ya existe una plantilla con el código «{codigo}»")

    nueva = ChkPlantilla(
        codigo=codigo, nombre=data.nombre, categoria_id=origen.categoria_id,
        descripcion=origen.descripcion, periodicidad_dias=origen.periodicidad_dias,
        requiere_firma=origen.requiere_firma, umbral_aprobacion=origen.umbral_aprobacion,
        critico_reprueba=origen.critico_reprueba, genera_ot=origen.genera_ot,
        pide_medidor=origen.pide_medidor, version=1)
    db.add(nueva); await db.flush()

    r = await db.execute(select(ChkPlantillaPregunta).where(and_(
        ChkPlantillaPregunta.plantilla_id == pid, ChkPlantillaPregunta.activo.is_(True))))
    for x in r.scalars().all():
        db.add(ChkPlantillaPregunta(
            plantilla_id=nueva.id, pregunta_id=x.pregunta_id, orden=x.orden,
            obligatorio=x.obligatorio, peso_override=x.peso_override,
            critico_override=x.critico_override, foto_override=x.foto_override))
    r = await db.execute(select(ChkPlantillaTipo).where(ChkPlantillaTipo.plantilla_id == pid))
    for t in r.scalars().all():
        db.add(ChkPlantillaTipo(plantilla_id=nueva.id, tipo_activo=t.tipo_activo,
                                marca=t.marca, linea=t.linea))
    await db.commit(); await db.refresh(nueva)
    return (await _plantillas_detalladas(db, [(nueva, None)]))[0]


# ── Preguntas de la plantilla ────────────────────────────────────────────────

class SeleccionIn(BaseModel):
    """Los identificadores de las preguntas del banco que componen la plantilla."""
    pregunta_ids: List[int]


class PlantillaPreguntaIn(BaseModel):
    obligatorio: Optional[bool] = None
    peso_override: Optional[float] = None
    critico_override: Optional[bool] = None
    foto_override: Optional[bool] = None
    orden: Optional[int] = None


@router.get("/plantillas/{pid}/estructura", response_model=Dict[str, Any])
async def estructura(pid: int, db: AsyncSession = Depends(get_db)):
    """La plantilla armada: sus preguntas agrupadas por sistema, listas para llenar."""
    p = await db.get(ChkPlantilla, pid)
    if not p:
        raise HTTPException(404, "Esa plantilla no existe")

    r = await db.execute(
        select(ChkPlantillaPregunta, ChkPregunta, ChkSistema, ChkClasificacion)
        .join(ChkPregunta, ChkPregunta.id == ChkPlantillaPregunta.pregunta_id)
        .join(ChkSistema, ChkSistema.id == ChkPregunta.sistema_id)
        .join(ChkClasificacion, ChkClasificacion.id == ChkPregunta.clasificacion_id)
        .where(and_(ChkPlantillaPregunta.plantilla_id == pid,
                    ChkPlantillaPregunta.activo.is_(True),
                    ChkPregunta.activo.is_(True)))
        .order_by(ChkSistema.orden, ChkSistema.nombre, ChkPlantillaPregunta.orden))
    filas = r.all()

    # Opciones de cada clasificación usada, en una sola consulta.
    clasif_ids = {c.id for _, _, _, c in filas}
    opciones: Dict[int, List[Dict[str, Any]]] = {}
    if clasif_ids:
        r = await db.execute(select(ChkOpcion).where(and_(
            ChkOpcion.clasificacion_id.in_(clasif_ids), ChkOpcion.activo.is_(True)))
            .order_by(ChkOpcion.orden, ChkOpcion.id))
        for o in r.scalars().all():
            opciones.setdefault(o.clasificacion_id, []).append(
                {"id": o.id, "nombre": o.nombre, "conforme": o.conforme,
                 "puntaje": o.puntaje, "color": o.color})

    sistemas: Dict[int, Dict[str, Any]] = {}
    for pp, preg, sis, cla in filas:
        bloque = sistemas.setdefault(sis.id, {
            "id": sis.id, "nombre": sis.nombre, "codigo": sis.codigo, "preguntas": []})
        bloque["preguntas"].append({
            "plantilla_pregunta_id": pp.id,
            "pregunta_id": preg.id,
            "texto": preg.texto, "ayuda": preg.ayuda,
            "orden": pp.orden,
            "obligatorio": pp.obligatorio,
            # El override manda; vacío, lo que diga la pregunta del banco.
            "critico": pp.critico_override if pp.critico_override is not None else preg.critico,
            "requiere_foto": pp.foto_override if pp.foto_override is not None else preg.requiere_foto,
            "peso": pp.peso_override if pp.peso_override is not None else preg.peso,
            "exige_observacion_no_conforme": preg.exige_observacion_no_conforme,
            "clasificacion": {
                "id": cla.id, "nombre": cla.nombre, "tipo": cla.tipo,
                "unidad": cla.unidad, "valor_min": cla.valor_min, "valor_max": cla.valor_max,
                "opciones": opciones.get(cla.id, []),
            },
        })

    bloques = list(sistemas.values())
    total = sum(len(b["preguntas"]) for b in bloques)
    criticos = sum(1 for b in bloques for x in b["preguntas"] if x["critico"])
    return {"plantilla": (await _plantillas_detalladas(db, [(p, None)]))[0],
            "sistemas": bloques, "total_preguntas": total, "criticas": criticos}


@router.put("/plantillas/{pid}/preguntas", response_model=Dict[str, Any])
async def fijar_preguntas(pid: int, data: SeleccionIn, db: AsyncSession = Depends(get_db)):
    """Define qué preguntas del banco componen la plantilla.

    Se manda la lista completa y el orden es el de la lista. Las que salen se
    desactivan en vez de borrarse: hay respuestas históricas apuntándoles.
    """
    if not await db.get(ChkPlantilla, pid):
        raise HTTPException(404, "Esa plantilla no existe")

    r = await db.execute(select(ChkPlantillaPregunta)
                         .where(ChkPlantillaPregunta.plantilla_id == pid))
    existentes = {x.pregunta_id: x for x in r.scalars().all()}

    agregadas = 0
    for orden, preg_id in enumerate(data.pregunta_ids):
        fila = existentes.get(preg_id)
        if not fila:
            if not await db.get(ChkPregunta, preg_id):
                continue
            fila = ChkPlantillaPregunta(plantilla_id=pid, pregunta_id=preg_id)
            db.add(fila)
            agregadas += 1
        fila.orden = orden
        fila.activo = True
    seleccionadas = set(data.pregunta_ids)
    quitadas = 0
    for preg_id, fila in existentes.items():
        if preg_id not in seleccionadas and fila.activo:
            fila.activo = False
            quitadas += 1

    await _subir_version(db, pid)
    await db.commit()
    return {"total": len(data.pregunta_ids), "agregadas": agregadas, "quitadas": quitadas}


@router.put("/plantilla-preguntas/{ppid}", response_model=Dict[str, Any])
async def ajustar_pregunta(ppid: int, data: PlantillaPreguntaIn,
                           db: AsyncSession = Depends(get_db)):
    """Ajusta una pregunta solo dentro de esta plantilla, sin tocar el banco."""
    obj = await db.get(ChkPlantillaPregunta, ppid)
    if not obj:
        raise HTTPException(404, "Esa pregunta no está en la plantilla")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await _subir_version(db, obj.plantilla_id)
    await db.commit()
    return {"id": obj.id, "orden": obj.orden}


# ── Tipos de activo a los que aplica ─────────────────────────────────────────

@router.get("/plantillas/{pid}/tipos", response_model=List[TipoAplicaOut])
async def listar_tipos(pid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ChkPlantillaTipo)
                         .where(ChkPlantillaTipo.plantilla_id == pid)
                         .order_by(ChkPlantillaTipo.tipo_activo))
    return list(r.scalars().all())


@router.post("/plantillas/{pid}/tipos", response_model=TipoAplicaOut, status_code=201)
async def agregar_tipo(pid: int, data: TipoAplicaIn, db: AsyncSession = Depends(get_db)):
    if not await db.get(ChkPlantilla, pid):
        raise HTTPException(404, "Esa plantilla no existe")
    r = await db.execute(select(func.count()).select_from(ChkPlantillaTipo).where(and_(
        ChkPlantillaTipo.plantilla_id == pid,
        ChkPlantillaTipo.tipo_activo == data.tipo_activo,
        ChkPlantillaTipo.marca.is_(None) if data.marca is None
        else ChkPlantillaTipo.marca == data.marca)))
    if r.scalar():
        raise HTTPException(409, "Esa combinación ya está registrada")
    obj = ChkPlantillaTipo(plantilla_id=pid, **data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/plantilla-tipos/{tid}", status_code=204)
async def quitar_tipo(tid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChkPlantillaTipo, tid)
    if not obj:
        raise HTTPException(404, "Ese registro no existe")
    await db.delete(obj); await db.commit()
