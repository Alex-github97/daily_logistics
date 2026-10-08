import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.mes_totales import (
    ahora as _ahora, recalcular_totales_orden, registrar_scrap,
)
from app.infrastructure.models.mes import (
    MESPlanta, MESLinea, MESTurno, MESCeldaTrabajo, MESEquipo,
    MESOperario, MESCertificacion, MESProducto, MESBOM, MESBOMDetalle,
    MESReceta, MESRecetaDetalle, MESOperacion, MESOrdenProduccion,
    MESOrdenOperacion, MESLote, MESEjecucion, MESParada,
    MESConsumoMaterial, MESWIP, MESDevolucion, MESInspeccion, MESDefecto,
    MESScrap, MESOEERegistro, MESChecklistPlantilla, MESChecklistPregunta,
    MESChecklistEjecucion, MESKPIDiario,
    EstadoOrdenProduccionEnum, PrioridadOrdenMESEnum,
    EstadoEjecucionMESEnum, ResultadoInspeccionMESEnum, EstadoLoteMESEnum,
    TipoMovimientoWIPEnum, TipoProductoMESEnum,
)

router = APIRouter(prefix='/mes', tags=['MES'])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class PlantaCreate(BaseModel):
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    tipo_fabricacion: str = 'DISCRETA'

class PlantaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str; tipo_fabricacion: str
    ciudad: Optional[str] = None; activo: bool

class LineaCreate(BaseModel):
    planta_id: int
    codigo: str
    nombre: str
    capacidad_hora: Optional[float] = None
    unidad_medida: Optional[str] = None

class LineaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; planta_id: int; codigo: str; nombre: str; activo: bool
    capacidad_hora: Optional[float] = None

class TurnoCreate(BaseModel):
    planta_id: int
    nombre: str
    tipo: str = 'MANANA'
    hora_inicio: str
    hora_fin: str
    duracion_horas: float = 8.0

class TurnoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; planta_id: int; nombre: str; tipo: str
    hora_inicio: str; hora_fin: str; duracion_horas: float; activo: bool

class EquipoCreate(BaseModel):
    celda_id: Optional[int] = None
    codigo: str
    nombre: str
    marca: Optional[str] = None
    modelo: Optional[str] = None
    capacidad_hora: Optional[float] = None

class EquipoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str; activo: bool
    celda_id: Optional[int] = None
    capacidad_hora: Optional[float] = None

class OperarioCreate(BaseModel):
    codigo: str
    nombre: str
    cedula: Optional[str] = None
    cargo: Optional[str] = None
    planta_id: Optional[int] = None

class OperarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; codigo: str; nombre: str; activo: bool
    cargo: Optional[str] = None; planta_id: Optional[int] = None

class ProductoCreate(BaseModel):
    # El código lo arma el sistema con el tipo y la familia. Se acepta escrito
    # a mano —hay productos que llegan con el código del cliente— pero si viene
    # vacío se genera, que es el caso normal.
    codigo: Optional[str] = None
    nombre: str
    tipo: str = 'PRODUCTO_TERMINADO'
    familia: Optional[str] = None
    unidad_medida: str = 'UN'
    descripcion: Optional[str] = None
    requiere_lote: bool = True
    peso_kg: Optional[float] = None
    vida_util_dias: Optional[int] = None

class ProductoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # Van TODOS los campos, no solo los de la tabla: el formulario de edición
    # los precarga desde acá, y los que faltaban se borraban al guardar porque
    # llegaban vacíos al servidor.
    id: int; codigo: str; nombre: str; tipo: str; unidad_medida: str; activo: bool
    familia: Optional[str] = None
    descripcion: Optional[str] = None
    requiere_lote: bool = True
    peso_kg: Optional[float] = None
    vida_util_dias: Optional[int] = None

class BOMCreate(BaseModel):
    producto_id: int
    version: str = '1.0'
    tipo: str = 'SIMPLE'
    descripcion: Optional[str] = None
    vigente: bool = True

class BOMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; producto_id: int; version: str; tipo: str; vigente: bool

class BOMDetalleCreate(BaseModel):
    bom_id: int
    componente_id: int
    nivel: int = 1
    cantidad: float
    unidad_medida: str = 'UN'
    merma_pct: float = 0.0

class BOMDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; bom_id: int; componente_id: int; cantidad: float
    unidad_medida: str; merma_pct: float; nivel: int

class RecetaCreate(BaseModel):
    producto_id: int
    version: str = '1.0'
    nombre: str
    rendimiento_pct: float = 100.0
    tiempo_proceso_min: Optional[float] = None
    vigente: bool = True

class RecetaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; producto_id: int; version: str; nombre: str
    rendimiento_pct: float; vigente: bool

class OrdenCreate(BaseModel):
    numero: str
    producto_id: int
    linea_id: Optional[int] = None
    bom_id: Optional[int] = None
    receta_id: Optional[int] = None
    cantidad_planificada: float
    prioridad: str = 'NORMAL'
    fecha_inicio_plan: Optional[datetime] = None
    fecha_fin_plan: Optional[datetime] = None

class OrdenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero: str; producto_id: int; estado: str; prioridad: str
    cantidad_planificada: float; cantidad_producida: float; cantidad_scrap: float
    linea_id: Optional[int] = None
    fecha_inicio_plan: Optional[datetime] = None
    fecha_fin_plan: Optional[datetime] = None
    fecha_inicio_real: Optional[datetime] = None
    fecha_fin_real: Optional[datetime] = None

class LoteCreate(BaseModel):
    numero_lote: str
    orden_id: Optional[int] = None
    producto_id: int
    cantidad: float
    unidad_medida: str = 'UN'
    fecha_fabricacion: Optional[datetime] = None
    fecha_vencimiento: Optional[datetime] = None

class LoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; numero_lote: str; producto_id: int; estado: str
    cantidad: float; unidad_medida: str
    # De qué orden salió. No se devolvía, y por eso la pantalla de trazabilidad
    # no podía buscar por número de orden: quien acababa de crear una orden la
    # escribía en el buscador y le respondía que no había coincidencias, como si
    # la orden no existiera.
    orden_id: Optional[int] = None

class EjecucionCreate(BaseModel):
    orden_id: int
    operario_id: Optional[int] = None
    equipo_id: Optional[int] = None
    turno: str = 'MANANA'

class EjecucionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; orden_id: int; estado: str; turno: str
    cantidad_producida: float; cantidad_scrap: float

class ParadaCreate(BaseModel):
    ejecucion_id: int
    tipo: str
    causa: str
    descripcion: Optional[str] = None
    equipo_id: Optional[int] = None

class InspeccionCreate(BaseModel):
    orden_id: int
    tipo: str
    operario_id: int
    lote_id: Optional[int] = None
    muestra_tam: Optional[int] = None

class InspeccionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; orden_id: int; tipo: str; resultado: str; operario_id: int
    muestra_tam: Optional[int] = None; muestra_defectos: int

class ScrapCreate(BaseModel):
    orden_id: int
    producto_id: int
    tipo: str = 'NORMAL'
    causa: str
    cantidad: float
    unidad_medida: str = 'UN'
    costo_unitario: Optional[float] = None
    es_reprocesable: bool = False

class ScrapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; orden_id: int; tipo: str; causa: str; cantidad: float
    costo_total: Optional[float] = None; es_reprocesable: bool

class OEECreate(BaseModel):
    linea_id: int
    equipo_id: Optional[int] = None
    turno: str = 'MANANA'
    tiempo_planificado_min: float
    tiempo_paradas_min: float = 0.0
    tiempo_operativo_min: float
    produccion_real: float
    produccion_nominal: float
    produccion_buena: float

class OEEResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; linea_id: int; turno: str
    fecha: Optional[datetime] = None
    equipo_id: Optional[int] = None
    tiempo_planificado_min: Optional[float] = None
    tiempo_paradas_min: Optional[float] = None
    tiempo_operativo_min: Optional[float] = None
    produccion_real: Optional[float] = None
    produccion_nominal: Optional[float] = None
    produccion_buena: Optional[float] = None
    disponibilidad: Optional[float] = None
    rendimiento: Optional[float] = None
    calidad: Optional[float] = None
    oee: Optional[float] = None


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get('/dashboard/kpis')
async def get_dashboard_kpis(db: AsyncSession = Depends(get_db)):
    plantas = await db.scalar(select(func.count(MESPlanta.id)).where(MESPlanta.activo == True))
    lineas  = await db.scalar(select(func.count(MESLinea.id)).where(MESLinea.activo == True))
    productos = await db.scalar(select(func.count(MESProducto.id)).where(MESProducto.activo == True))
    ordenes_activas = await db.scalar(
        select(func.count(MESOrdenProduccion.id)).where(
            MESOrdenProduccion.estado.in_([
                EstadoOrdenProduccionEnum.LIBERADA,
                EstadoOrdenProduccionEnum.EN_EJECUCION,
            ])
        )
    )
    boms = await db.scalar(select(func.count(MESBOM.id)).where(MESBOM.vigente == True))
    operarios = await db.scalar(select(func.count(MESOperario.id)).where(MESOperario.activo == True))
    # Indicadores operativos (sobre registros reales)
    oee_prom = await db.scalar(select(func.avg(MESOEERegistro.oee)))
    producido = await db.scalar(select(func.sum(MESOrdenProduccion.cantidad_producida)))
    scrap_total = await db.scalar(select(func.sum(MESOrdenProduccion.cantidad_scrap)))
    paradas_abiertas = await db.scalar(
        select(func.count(MESParada.id)).where(MESParada.fecha_fin.is_(None))
    )
    insp_pendientes = await db.scalar(
        select(func.count(MESInspeccion.id)).where(
            MESInspeccion.resultado == ResultadoInspeccionMESEnum.PENDIENTE
        )
    )
    total_prod = (producido or 0) + (scrap_total or 0)
    return {
        'plantas': plantas or 0,
        'lineas': lineas or 0,
        'productos': productos or 0,
        'ordenes_activas': ordenes_activas or 0,
        'boms_vigentes': boms or 0,
        'operarios': operarios or 0,
        'oee_promedio': round(oee_prom, 1) if oee_prom else None,
        'unidades_producidas': producido or 0,
        'scrap_rate': round((scrap_total or 0) / total_prod * 100, 2) if total_prod > 0 else 0,
        'paradas_abiertas': paradas_abiertas or 0,
        'inspecciones_pendientes': insp_pendientes or 0,
    }


# ─── Plantas ─────────────────────────────────────────────────────────────────

@router.get('/plantas', response_model=List[PlantaResponse])
async def list_plantas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESPlanta).where(MESPlanta.activo == True))
    return result.scalars().all()

@router.post('/plantas', response_model=PlantaResponse, status_code=201)
async def create_planta(data: PlantaCreate, db: AsyncSession = Depends(get_db)):
    obj = MESPlanta(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Líneas ──────────────────────────────────────────────────────────────────

@router.get('/lineas', response_model=List[LineaResponse])
async def list_lineas(planta_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESLinea).where(MESLinea.activo == True)
    if planta_id:
        q = q.where(MESLinea.planta_id == planta_id)
    result = await db.execute(q)
    return result.scalars().all()

@router.post('/lineas', response_model=LineaResponse, status_code=201)
async def create_linea(data: LineaCreate, db: AsyncSession = Depends(get_db)):
    obj = MESLinea(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Turnos ──────────────────────────────────────────────────────────────────

@router.get('/turnos', response_model=List[TurnoResponse])
async def list_turnos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESTurno).where(MESTurno.activo == True))
    return result.scalars().all()

@router.post('/turnos', response_model=TurnoResponse, status_code=201)
async def create_turno(data: TurnoCreate, db: AsyncSession = Depends(get_db)):
    obj = MESTurno(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Equipos ─────────────────────────────────────────────────────────────────

@router.get('/equipos', response_model=List[EquipoResponse])
async def list_equipos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESEquipo).where(MESEquipo.activo == True))
    return result.scalars().all()

@router.post('/equipos', response_model=EquipoResponse, status_code=201)
async def create_equipo(data: EquipoCreate, db: AsyncSession = Depends(get_db)):
    obj = MESEquipo(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Operarios ───────────────────────────────────────────────────────────────

@router.get('/operarios', response_model=List[OperarioResponse])
async def list_operarios(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESOperario).where(MESOperario.activo == True))
    return result.scalars().all()

@router.post('/operarios', response_model=OperarioResponse, status_code=201)
async def create_operario(data: OperarioCreate, db: AsyncSession = Depends(get_db)):
    obj = MESOperario(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Productos ───────────────────────────────────────────────────────────────

# ── El código del producto lo arma el sistema ────────────────────────────────
#
# `PT-BOLSA-0001`: qué es, de qué familia, y el consecutivo de esa combinación.
# Se lee de un golpe en una etiqueta y en una orden de producción, que es donde
# de verdad se usa.
#
# El consecutivo es POR TIPO Y FAMILIA, no global: así el primer producto de una
# familia nueva empieza en 0001 en vez de heredar un número alto que no dice
# nada, y dos familias no se pisan los números.

PREFIJO_TIPO_PRODUCTO = {
    'MATERIA_PRIMA': 'MP',
    'SEMIELABORADO': 'SE',
    'PRODUCTO_TERMINADO': 'PT',
    'SUBPRODUCTO': 'SP',
    'EMPAQUE': 'EM',
    'HERRAMIENTA': 'HE',
}

# Sin familia el código sería `PT--0001`, con un hueco donde debería ir algo.
FAMILIA_POR_OMISION = 'GEN'


def _normalizar_familia(familia: Optional[str]) -> str:
    """La familia como va en el código: sin tildes, sin espacios, en mayúsculas.

    Se normaliza para el código pero se guarda lo que escribió la persona: si se
    guardara normalizado, «Bolsa» y «BOLSA» quedarían como dos familias en la
    lista de selección y la siguiente persona no sabría cuál usar.
    """
    if not familia or not familia.strip():
        return FAMILIA_POR_OMISION
    limpio = unicodedata.normalize('NFD', familia.strip()) \
        .encode('ascii', 'ignore').decode('ascii')
    limpio = re.sub(r'[^A-Za-z0-9]+', '', limpio).upper()
    # Doce caracteres: más que eso no cabe legible en una etiqueta.
    return limpio[:12] or FAMILIA_POR_OMISION


async def _codigo_producto(db: AsyncSession, tipo: str,
                           familia: Optional[str]) -> str:
    prefijo = f"{PREFIJO_TIPO_PRODUCTO.get(tipo, 'PR')}-{_normalizar_familia(familia)}-"
    # Se mira el mayor en uso y no el conteo: contar repetiría números en cuanto
    # se desactive o se borre un producto.
    r = await db.execute(select(func.max(MESProducto.codigo))
                         .where(MESProducto.codigo.like(f"{prefijo}%")))
    ultimo = r.scalar()
    siguiente = 1
    if ultimo:
        try:
            siguiente = int(str(ultimo).rsplit('-', 1)[1]) + 1
        except (IndexError, ValueError):
            siguiente = 1
    return f"{prefijo}{siguiente:04d}"


@router.get('/productos/codigo-sugerido')
async def codigo_sugerido_producto(tipo: str = 'PRODUCTO_TERMINADO',
                                   familia: Optional[str] = None,
                                   db: AsyncSession = Depends(get_db)):
    """El código que le tocaría al siguiente producto de ese tipo y familia.

    Sirve para mostrarlo mientras se llena el formulario. Es una SUGERENCIA: el
    definitivo lo asigna el alta, porque entre que se muestra y se guarda otra
    persona puede haber creado uno.
    """
    if tipo not in PREFIJO_TIPO_PRODUCTO:
        raise HTTPException(422, f'Tipo de producto inválido: {tipo}')
    return {'codigo': await _codigo_producto(db, tipo, familia),
            'tipo': tipo, 'familia': (familia or '').strip() or None}


@router.get('/productos/familias')
async def familias_producto(db: AsyncSession = Depends(get_db)):
    """Las familias que ya existen, para no escribirlas dos veces distintas."""
    r = await db.execute(
        select(MESProducto.familia, func.count(MESProducto.id))
        .where(MESProducto.familia.isnot(None), MESProducto.familia != '')
        .group_by(MESProducto.familia).order_by(MESProducto.familia))
    return [{'familia': f, 'productos': n} for f, n in r.all()]


@router.get('/productos', response_model=List[ProductoResponse])
async def list_productos(tipo: Optional[str] = None,
                         familia: Optional[str] = None,
                         incluir_inactivos: bool = False,
                         db: AsyncSession = Depends(get_db)):
    q = select(MESProducto)
    if not incluir_inactivos:
        q = q.where(MESProducto.activo.is_(True))
    if tipo:
        if tipo not in PREFIJO_TIPO_PRODUCTO:
            raise HTTPException(422, f'Tipo de producto inválido: {tipo}')
        q = q.where(MESProducto.tipo == TipoProductoMESEnum[tipo])
    if familia:
        q = q.where(MESProducto.familia == familia)
    result = await db.execute(q.order_by(MESProducto.codigo))
    return result.scalars().all()


@router.post('/productos', response_model=ProductoResponse, status_code=201)
async def create_producto(data: ProductoCreate, db: AsyncSession = Depends(get_db)):
    if data.tipo not in PREFIJO_TIPO_PRODUCTO:
        raise HTTPException(422, f'Tipo de producto inválido: {data.tipo}')
    if not data.nombre.strip():
        raise HTTPException(422, 'El nombre del producto es obligatorio')

    campos = data.model_dump()
    campos['nombre'] = data.nombre.strip()
    campos['familia'] = (data.familia or '').strip() or None
    manual = (data.codigo or '').strip()

    # Dos personas creando a la vez pueden llegar al mismo consecutivo: el que
    # pierde la carrera choca con el índice único. Se vuelve a intentar con el
    # siguiente número en vez de devolverle un error que no entiende y que se
    # arregla solo. Con código escrito a mano no se reintenta: ahí el choque es
    # un dato repetido de verdad y hay que decirlo.
    intentos = 1 if manual else 5
    for intento in range(intentos):
        campos['codigo'] = manual or await _codigo_producto(
            db, data.tipo, campos['familia'])
        ya = await db.scalar(
            select(func.count()).select_from(MESProducto)
            .where(func.upper(MESProducto.codigo) == campos['codigo'].upper()))
        if ya:
            if manual:
                raise HTTPException(
                    409, f'Ya hay un producto con el código «{campos["codigo"]}»')
            continue
        obj = MESProducto(**campos)
        db.add(obj)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if intento == intentos - 1:
                raise HTTPException(
                    409, 'No se pudo asignar un código libre. Vuelva a intentarlo.')
            continue
        await db.refresh(obj)
        return obj

    raise HTTPException(409, 'No se pudo asignar un código libre. Vuelva a intentarlo.')


# ─── BOM ─────────────────────────────────────────────────────────────────────

@router.get('/bom', response_model=List[BOMResponse])
async def list_bom(producto_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESBOM).where(MESBOM.vigente == True)
    if producto_id:
        q = q.where(MESBOM.producto_id == producto_id)
    result = await db.execute(q)
    return result.scalars().all()

@router.post('/bom', response_model=BOMResponse, status_code=201)
async def create_bom(data: BOMCreate, db: AsyncSession = Depends(get_db)):
    obj = MESBOM(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.get('/bom/{bom_id}/detalles', response_model=List[BOMDetalleResponse])
async def get_bom_detalles(bom_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESBOMDetalle).where(MESBOMDetalle.bom_id == bom_id))
    return result.scalars().all()

@router.post('/bom/{bom_id}/detalles', response_model=BOMDetalleResponse, status_code=201)
async def add_bom_detalle(bom_id: int, data: BOMDetalleCreate, db: AsyncSession = Depends(get_db)):
    obj = MESBOMDetalle(**{**data.model_dump(), 'bom_id': bom_id})
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Celdas de trabajo ───────────────────────────────────────────────────────

class CeldaCreate(BaseModel):
    linea_id: int
    codigo: str
    nombre: str
    descripcion: Optional[str] = None

class CeldaResponse(CeldaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

@router.get('/celdas', response_model=List[CeldaResponse])
async def list_celdas(linea_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESCeldaTrabajo).where(MESCeldaTrabajo.activo == True)
    if linea_id:
        q = q.where(MESCeldaTrabajo.linea_id == linea_id)
    result = await db.execute(q)
    return result.scalars().all()

@router.post('/celdas', response_model=CeldaResponse, status_code=201)
async def create_celda(data: CeldaCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(MESLinea, data.linea_id):
        raise HTTPException(404, 'Línea no encontrada')
    obj = MESCeldaTrabajo(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── WIP (inventario en proceso) ─────────────────────────────────────────────

class WIPCreate(BaseModel):
    orden_id: int
    # El módulo desde donde se mueve. En una ENTRADA y en un AJUSTE es el que
    # recibe; en una SALIDA y en un TRANSFERENCIA es el que entrega.
    celda_id: int
    # Solo en los traslados: el módulo que recibe. Obligatorio ahí.
    celda_destino_id: Optional[int] = None
    producto_id: int
    lote_id: Optional[int] = None
    tipo_mov: str = 'ENTRADA'          # ENTRADA/SALIDA/TRANSFERENCIA/AJUSTE
    cantidad: float
    unidad_medida: str = 'UN'
    observaciones: Optional[str] = None

class WIPResponse(WIPCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha_mov: Optional[datetime] = None
    # Si el movimiento nació de una devolución, queda amarrado a ella.
    devolucion_id: Optional[int] = None

#
# EL SALDO DE UN MÓDULO ES LA SUMA DE SU LIBRO
#
# Nadie mantiene una columna de saldo: se suma el movimiento. Y cada tipo de
# movimiento tiene un efecto y solo uno:
#
#   ENTRADA        + al módulo
#   SALIDA         − al módulo
#   TRANSFERENCIA  − al origen  y  + al destino     ← los DOS extremos
#   AJUSTE         + al módulo (el ajuste negativo se registra como SALIDA)
#
# La TRANSFERENCIA es la que estaba mal: se contaba como una salida sin destino,
# así que trasladar material de un módulo a otro lo hacía desaparecer del
# inventario en proceso. Con un solo `celda_id` en la tabla no había dónde
# anotar el destino, y la pantalla ofrecía el movimiento igual.

def _efecto_wip(w: MESWIP) -> List[tuple]:
    """Los (celda, signo) que toca un movimiento. Uno, o dos si es traslado."""
    if w.tipo_mov == TipoMovimientoWIPEnum.TRANSFERENCIA:
        # Un traslado sin destino se cuenta solo como salida: es el dato viejo,
        # de antes de que existiera la columna, y perderlo del todo sería peor.
        if w.celda_destino_id:
            return [(w.celda_id, -1), (w.celda_destino_id, +1)]
        return [(w.celda_id, -1)]
    if w.tipo_mov == TipoMovimientoWIPEnum.SALIDA:
        return [(w.celda_id, -1)]
    return [(w.celda_id, +1)]


async def _saldos_wip(db: AsyncSession, *, orden_id: Optional[int] = None,
                      producto_id: Optional[int] = None) -> dict:
    q = select(MESWIP)
    if orden_id:
        q = q.where(MESWIP.orden_id == orden_id)
    if producto_id:
        q = q.where(MESWIP.producto_id == producto_id)
    saldos: dict = {}
    for w in (await db.execute(q)).scalars().all():
        for celda, signo in _efecto_wip(w):
            clave = (celda, w.producto_id)
            saldos[clave] = saldos.get(clave, 0.0) + signo * w.cantidad
    return saldos


async def _saldo_modulo(db: AsyncSession, celda_id: int, producto_id: int,
                        orden_id: Optional[int] = None) -> float:
    saldos = await _saldos_wip(db, orden_id=orden_id, producto_id=producto_id)
    return round(saldos.get((celda_id, producto_id), 0.0), 4)


@router.get('/wip', response_model=List[WIPResponse])
async def list_wip(
    orden_id: Optional[int] = None,
    celda_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(MESWIP)
    if orden_id:
        q = q.where(MESWIP.orden_id == orden_id)
    if celda_id:
        # Un traslado es del módulo que envía Y del que recibe: filtrando solo
        # por `celda_id`, al módulo destino no le aparecía lo que le llegó.
        q = q.where(or_(MESWIP.celda_id == celda_id,
                        MESWIP.celda_destino_id == celda_id))
    result = await db.execute(q.order_by(MESWIP.fecha_mov.desc()))
    return result.scalars().all()


@router.post('/wip', response_model=WIPResponse, status_code=201)
async def create_wip(data: WIPCreate, db: AsyncSession = Depends(get_db)):
    if data.tipo_mov not in TipoMovimientoWIPEnum.__members__:
        raise HTTPException(422, f'Tipo de movimiento inválido: {data.tipo_mov}')
    if data.cantidad <= 0:
        raise HTTPException(
            422, 'La cantidad debe ser mayor que cero. Para descontar material '
                 'use una SALIDA, no un AJUSTE negativo.')
    orden = await db.get(MESOrdenProduccion, data.orden_id)
    if not orden:
        raise HTTPException(404, 'Orden no encontrada')
    if orden.estado not in (EstadoOrdenProduccionEnum.LIBERADA,
                            EstadoOrdenProduccionEnum.EN_EJECUCION):
        raise HTTPException(409, f'La orden está {orden.estado.value}: el WIP solo se mueve con la orden liberada o en ejecución')
    origen = await db.get(MESCeldaTrabajo, data.celda_id)
    if not origen:
        raise HTTPException(404, 'Módulo de origen no encontrado')
    if not await db.get(MESProducto, data.producto_id):
        raise HTTPException(404, 'Producto no encontrado')

    es_traslado = data.tipo_mov == 'TRANSFERENCIA'
    if es_traslado:
        if not data.celda_destino_id:
            raise HTTPException(
                422, 'Un traslado necesita el módulo de destino: sin él, el '
                     'material sale de un lado y no entra a ninguno.')
        if data.celda_destino_id == data.celda_id:
            raise HTTPException(422, 'El origen y el destino son el mismo módulo')
        destino = await db.get(MESCeldaTrabajo, data.celda_destino_id)
        if not destino:
            raise HTTPException(404, 'Módulo de destino no encontrado')
    elif data.celda_destino_id:
        raise HTTPException(
            422, f'Un movimiento de tipo {data.tipo_mov} no lleva módulo de destino')

    # No se puede sacar de un módulo lo que no tiene. Se valida al registrar y
    # no al consultar: un saldo negativo no debe llegar a existir.
    if data.tipo_mov in ('SALIDA', 'TRANSFERENCIA'):
        saldo = await _saldo_modulo(db, data.celda_id, data.producto_id)
        if data.cantidad > saldo + 1e-6:
            raise HTTPException(
                409,
                f'El módulo {origen.nombre} tiene {saldo:g} de este producto y '
                f'se quieren mover {data.cantidad:g}.')

    obj = MESWIP(**data.model_dump(), fecha_mov=_ahora())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get('/wip/saldos')
async def saldos_wip(orden_id: Optional[int] = None,
                     db: AsyncSession = Depends(get_db)):
    """Saldo de material en proceso por (módulo, producto)."""
    saldos = await _saldos_wip(db, orden_id=orden_id)
    return [
        {'celda_id': c, 'producto_id': p, 'saldo': round(s, 3)}
        for (c, p), s in sorted(saldos.items()) if abs(s) > 1e-9
    ]


# ══════════════════════════════════════════════════════════════════════════════
# DEVOLUCIONES POR AVERÍA
#
# Un módulo recibe material del anterior, encuentra que viene averiado y lo
# devuelve para que lo rehagan.
#
# NO ES SCRAP, Y LA DIFERENCIA IMPORTA
# El scrap es material que se pierde y no vuelve. La devolución es material que
# vuelve: el módulo que la recibe la repara y la reingresa al flujo. Contarlas
# juntas metería el reproceso dentro de la tasa de scrap, que es la cifra con la
# que se juzga una línea.
#
# CADA DEVOLUCIÓN MUEVE EL MATERIAL DE VERDAD
# Se registra como un traslado en el libro de WIP —sale del que devuelve, entra
# al que tiene que rehacer— y al reprocesarse se registra el traslado de vuelta.
# Sin eso, el saldo del módulo seguiría diciendo que tiene unidades que ya
# devolvió.
# ══════════════════════════════════════════════════════════════════════════════

ESTADOS_DEVOLUCION = ('PENDIENTE', 'REPROCESADA')


class DevolucionCreate(BaseModel):
    orden_id: int
    # El módulo que detectó la avería y devuelve.
    celda_origen_id: int
    # El módulo que tiene que rehacerlo.
    celda_destino_id: int
    producto_id: int
    cantidad: float
    motivo: str
    lote_id: Optional[int] = None
    operario_id: Optional[int] = None
    unidad_medida: str = 'UN'
    descripcion: Optional[str] = None


class DevolucionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    orden_id: int
    celda_origen_id: int
    celda_destino_id: int
    producto_id: int
    lote_id: Optional[int] = None
    operario_id: Optional[int] = None
    cantidad: float
    unidad_medida: str
    motivo: str
    descripcion: Optional[str] = None
    estado: str
    fecha: Optional[datetime] = None
    fecha_reproceso: Optional[datetime] = None
    observaciones_reproceso: Optional[str] = None


class ReprocesoIn(BaseModel):
    observaciones: Optional[str] = None


@router.get('/devoluciones', response_model=List[DevolucionResponse])
async def list_devoluciones(orden_id: Optional[int] = None,
                            estado: Optional[str] = None,
                            celda_id: Optional[int] = None,
                            db: AsyncSession = Depends(get_db)):
    q = select(MESDevolucion)
    if orden_id:
        q = q.where(MESDevolucion.orden_id == orden_id)
    if estado:
        if estado not in ESTADOS_DEVOLUCION:
            raise HTTPException(422, f'Estado inválido: {", ".join(ESTADOS_DEVOLUCION)}')
        q = q.where(MESDevolucion.estado == estado)
    if celda_id:
        # Le sirve a los dos módulos: al que devolvió y al que debe rehacerlo.
        q = q.where(or_(MESDevolucion.celda_origen_id == celda_id,
                        MESDevolucion.celda_destino_id == celda_id))
    result = await db.execute(q.order_by(MESDevolucion.fecha.desc()))
    return result.scalars().all()


@router.get('/devoluciones/resumen')
async def resumen_devoluciones(db: AsyncSession = Depends(get_db)):
    """Qué módulo genera el reproceso y por qué.

    Es para lo que sirve medir devoluciones: una lista de eventos no dice nada,
    y agrupada por módulo responsable y motivo señala dónde está el problema.
    """
    r = await db.execute(
        select(MESDevolucion.celda_destino_id, MESDevolucion.motivo,
               func.count(MESDevolucion.id), func.sum(MESDevolucion.cantidad),
               func.sum(case((MESDevolucion.estado == 'PENDIENTE', 1), else_=0)))
        .group_by(MESDevolucion.celda_destino_id, MESDevolucion.motivo)
        .order_by(func.sum(MESDevolucion.cantidad).desc()))
    filas = [{'celda_id': c, 'motivo': m, 'devoluciones': n,
              'cantidad': round(float(cant or 0), 3), 'pendientes': int(pend or 0)}
             for c, m, n, cant, pend in r.all()]
    total = await db.scalar(
        select(func.coalesce(func.sum(MESDevolucion.cantidad), 0.0)))
    pendiente = await db.scalar(
        select(func.coalesce(func.sum(MESDevolucion.cantidad), 0.0))
        .where(MESDevolucion.estado == 'PENDIENTE'))
    return {'por_modulo_y_motivo': filas,
            'cantidad_total': round(float(total or 0), 3),
            'cantidad_pendiente': round(float(pendiente or 0), 3)}


@router.post('/devoluciones', response_model=DevolucionResponse, status_code=201)
async def create_devolucion(data: DevolucionCreate,
                            db: AsyncSession = Depends(get_db)):
    if data.cantidad <= 0:
        raise HTTPException(422, 'La cantidad devuelta debe ser mayor que cero')
    if not data.motivo.strip():
        raise HTTPException(422, 'Diga qué avería tiene: es el dato que sirve después')
    if data.celda_origen_id == data.celda_destino_id:
        raise HTTPException(
            422, 'Un módulo no se devuelve material a sí mismo. Si la avería la '
                 'causó el mismo módulo, corrija su producción o registre scrap.')

    orden = await db.get(MESOrdenProduccion, data.orden_id)
    if not orden:
        raise HTTPException(404, 'Orden no encontrada')
    if orden.estado not in (EstadoOrdenProduccionEnum.LIBERADA,
                            EstadoOrdenProduccionEnum.EN_EJECUCION):
        raise HTTPException(
            409, f'La orden está {orden.estado.value}: solo se devuelve material '
                 f'de una orden liberada o en ejecución.')
    origen = await db.get(MESCeldaTrabajo, data.celda_origen_id)
    if not origen:
        raise HTTPException(404, 'Módulo que devuelve no encontrado')
    destino = await db.get(MESCeldaTrabajo, data.celda_destino_id)
    if not destino:
        raise HTTPException(404, 'Módulo que debe rehacerlo no encontrado')
    if not await db.get(MESProducto, data.producto_id):
        raise HTTPException(404, 'Producto no encontrado')
    if data.operario_id and not await db.get(MESOperario, data.operario_id):
        raise HTTPException(404, 'Operario no encontrado')

    # No se devuelve lo que no se tiene: el saldo del módulo que devuelve manda.
    saldo = await _saldo_modulo(db, data.celda_origen_id, data.producto_id)
    if data.cantidad > saldo + 1e-6:
        raise HTTPException(
            409,
            f'El módulo {origen.nombre} tiene {saldo:g} de este producto y se '
            f'quieren devolver {data.cantidad:g}. Registre primero la entrada '
            f'del material que recibió.')

    campos = data.model_dump()
    campos['motivo'] = data.motivo.strip()
    obj = MESDevolucion(**campos, estado='PENDIENTE', fecha=_ahora())
    db.add(obj)
    await db.flush()

    # El traslado que mueve el material de verdad, amarrado a la devolución.
    db.add(MESWIP(
        orden_id=data.orden_id, celda_id=data.celda_origen_id,
        celda_destino_id=data.celda_destino_id, producto_id=data.producto_id,
        lote_id=data.lote_id, tipo_mov=TipoMovimientoWIPEnum.TRANSFERENCIA,
        cantidad=data.cantidad, unidad_medida=data.unidad_medida,
        fecha_mov=_ahora(), devolucion_id=obj.id,
        observaciones=f'Devolución por avería: {campos["motivo"]}'))

    await db.commit()
    await db.refresh(obj)
    return obj


@router.put('/devoluciones/{did}/reprocesar', response_model=DevolucionResponse)
async def reprocesar_devolucion(did: int, data: ReprocesoIn,
                                db: AsyncSession = Depends(get_db)):
    """El módulo responsable rehizo el material y lo devuelve al flujo."""
    obj = await db.get(MESDevolucion, did)
    if not obj:
        raise HTTPException(404, 'Esa devolución no existe')
    if obj.estado == 'REPROCESADA':
        cuando = (f' el {obj.fecha_reproceso:%Y-%m-%d}'
                  if obj.fecha_reproceso else '')
        raise HTTPException(409, f'Esa devolución ya se reprocesó{cuando}')

    # El material vuelve a quien lo reclamó. Se comprueba que el módulo
    # responsable todavía lo tenga: si ya lo movió a otra parte, reprocesar
    # dejaría su saldo en negativo.
    saldo = await _saldo_modulo(db, obj.celda_destino_id, obj.producto_id)
    if obj.cantidad > saldo + 1e-6:
        destino = await db.get(MESCeldaTrabajo, obj.celda_destino_id)
        raise HTTPException(
            409,
            f'El módulo {destino.nombre if destino else obj.celda_destino_id} '
            f'tiene {saldo:g} de este producto y la devolución es de '
            f'{obj.cantidad:g}: el material ya se movió a otra parte.')

    db.add(MESWIP(
        orden_id=obj.orden_id, celda_id=obj.celda_destino_id,
        celda_destino_id=obj.celda_origen_id, producto_id=obj.producto_id,
        lote_id=obj.lote_id, tipo_mov=TipoMovimientoWIPEnum.TRANSFERENCIA,
        cantidad=obj.cantidad, unidad_medida=obj.unidad_medida,
        fecha_mov=_ahora(), devolucion_id=obj.id,
        observaciones=f'Reproceso terminado: {obj.motivo}'))

    obj.estado = 'REPROCESADA'
    obj.fecha_reproceso = _ahora()
    if data.observaciones:
        obj.observaciones_reproceso = data.observaciones
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete('/devoluciones/{did}', status_code=204)
async def eliminar_devolucion(did: int, db: AsyncSession = Depends(get_db)):
    """Anula una devolución mal registrada y deshace sus movimientos.

    Solo mientras esté PENDIENTE: una vez reprocesada, el material ya volvió al
    flujo y borrarla dejaría el saldo de los dos módulos mintiendo.
    """
    obj = await db.get(MESDevolucion, did)
    if not obj:
        raise HTTPException(404, 'Esa devolución no existe')
    if obj.estado == 'REPROCESADA':
        raise HTTPException(
            409, 'Ya se reprocesó: el material volvió al flujo y sus movimientos '
                 'no se pueden deshacer. Registre un ajuste si hay que corregir.')
    r = await db.execute(select(MESWIP).where(MESWIP.devolucion_id == did))
    for w in r.scalars().all():
        await db.delete(w)
    await db.delete(obj)
    await db.commit()


# ─── Consumos de material ────────────────────────────────────────────────────

class ConsumoCreate(BaseModel):
    orden_id: int
    producto_id: int
    lote_id: Optional[int] = None
    cantidad_plan: float
    cantidad_real: float = 0.0
    unidad_medida: str = 'UN'
    operario_id: Optional[int] = None

class ConsumoResponse(ConsumoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha_consumo: Optional[datetime] = None

@router.get('/consumos', response_model=List[ConsumoResponse])
async def list_consumos(orden_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESConsumoMaterial)
    if orden_id:
        q = q.where(MESConsumoMaterial.orden_id == orden_id)
    result = await db.execute(q.order_by(MESConsumoMaterial.created_at.desc()))
    return result.scalars().all()

@router.post('/consumos', response_model=ConsumoResponse, status_code=201)
async def create_consumo(data: ConsumoCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(MESOrdenProduccion, data.orden_id):
        raise HTTPException(404, 'Orden no encontrada')
    obj = MESConsumoMaterial(**data.model_dump(), fecha_consumo=datetime.utcnow())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Recetas ─────────────────────────────────────────────────────────────────

@router.get('/recetas', response_model=List[RecetaResponse])
async def list_recetas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESReceta).where(MESReceta.vigente == True))
    return result.scalars().all()

@router.post('/recetas', response_model=RecetaResponse, status_code=201)
async def create_receta(data: RecetaCreate, db: AsyncSession = Depends(get_db)):
    obj = MESReceta(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Órdenes de Producción ───────────────────────────────────────────────────

# Máquina de estados (ISO 9001 §8.5.1 — control de producción): solo se admiten
# las transiciones del flujo controlado; todo lo demás responde 409.
TRANSICIONES_ORDEN: dict = {
    'PLANEADA':     {'LIBERADA', 'CANCELADA'},
    'LIBERADA':     {'EN_EJECUCION', 'PLANEADA', 'CANCELADA'},
    'EN_EJECUCION': {'SUSPENDIDA', 'CERRADA', 'CANCELADA'},
    'SUSPENDIDA':   {'EN_EJECUCION', 'CANCELADA'},
    'CERRADA':      set(),
    'CANCELADA':    set(),
}

async def _siguiente_numero_orden(db: AsyncSession) -> str:
    """Numeración controlada de órdenes: OP-YYYYMMDD-#### (consecutivo del día)."""
    hoy = datetime.utcnow().strftime('%Y%m%d')
    prefijo = f'OP-{hoy}-'
    r = await db.execute(
        select(func.count(MESOrdenProduccion.id)).where(MESOrdenProduccion.numero.like(f'{prefijo}%'))
    )
    return f'{prefijo}{(r.scalar() or 0) + 1:04d}'

@router.get('/ordenes/siguiente-numero')
async def get_siguiente_numero(db: AsyncSession = Depends(get_db)):
    return {'numero': await _siguiente_numero_orden(db)}

@router.get('/ordenes', response_model=List[OrdenResponse])
async def list_ordenes(estado: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESOrdenProduccion)
    if estado:
        q = q.where(MESOrdenProduccion.estado == estado)
    result = await db.execute(q.order_by(MESOrdenProduccion.created_at.desc()))
    return result.scalars().all()

@router.post('/ordenes', response_model=OrdenResponse, status_code=201)
async def create_orden(data: OrdenCreate, db: AsyncSession = Depends(get_db)):
    d = data.model_dump()
    if not d.get('numero'):
        d['numero'] = await _siguiente_numero_orden(db)
    if d['cantidad_planificada'] is None or d['cantidad_planificada'] <= 0:
        raise HTTPException(422, 'La cantidad planificada debe ser mayor que cero')
    producto = await db.get(MESProducto, d['producto_id'])
    if not producto:
        raise HTTPException(404, 'Producto no encontrado')
    obj = MESOrdenProduccion(**d)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.get('/ordenes/{orden_id}', response_model=OrdenResponse)
async def get_orden(orden_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(MESOrdenProduccion, orden_id)
    if not obj:
        raise HTTPException(404, 'Orden no encontrada')
    return obj

class OrdenReplan(BaseModel):
    linea_id: Optional[int] = None
    prioridad: Optional[str] = None
    fecha_inicio_plan: Optional[datetime] = None
    fecha_fin_plan: Optional[datetime] = None
    observaciones: Optional[str] = None

@router.put('/ordenes/{orden_id}', response_model=OrdenResponse)
async def replanificar_orden(orden_id: int, data: OrdenReplan, db: AsyncSession = Depends(get_db)):
    """Replanificación controlada: solo órdenes PLANEADA o LIBERADA admiten
    cambios de línea/fechas/prioridad (cambio controlado — ISO 9001 §8.5.6)."""
    obj = await db.get(MESOrdenProduccion, orden_id)
    if not obj:
        raise HTTPException(404, 'Orden no encontrada')
    if obj.estado not in (EstadoOrdenProduccionEnum.PLANEADA, EstadoOrdenProduccionEnum.LIBERADA):
        raise HTTPException(409, f'La orden está {obj.estado.value}: solo se replanifica en PLANEADA o LIBERADA')
    if data.prioridad is not None:
        if data.prioridad not in PrioridadOrdenMESEnum.__members__:
            raise HTTPException(422, f'Prioridad inválida: {data.prioridad}')
        obj.prioridad = PrioridadOrdenMESEnum[data.prioridad]
    if data.linea_id is not None:
        if not await db.get(MESLinea, data.linea_id):
            raise HTTPException(404, 'Línea no encontrada')
        obj.linea_id = data.linea_id
    if data.fecha_inicio_plan is not None:
        obj.fecha_inicio_plan = data.fecha_inicio_plan
    if data.fecha_fin_plan is not None:
        obj.fecha_fin_plan = data.fecha_fin_plan
    if data.observaciones:
        obj.observaciones = data.observaciones
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put('/ordenes/{orden_id}/estado')
async def update_orden_estado(orden_id: int, estado: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(MESOrdenProduccion, orden_id)
    if not obj:
        raise HTTPException(404, 'Orden no encontrada')
    if estado not in EstadoOrdenProduccionEnum.__members__:
        raise HTTPException(422, f'Estado inválido: {estado}')
    actual = obj.estado.value if obj.estado else 'PLANEADA'
    if estado not in TRANSICIONES_ORDEN.get(actual, set()):
        raise HTTPException(409, f'Transición no permitida: {actual} → {estado}')
    # Cierre controlado: no se puede cerrar con ejecuciones abiertas
    if estado == 'CERRADA':
        abiertas = await db.scalar(
            select(func.count(MESEjecucion.id)).where(
                MESEjecucion.orden_id == orden_id,
                MESEjecucion.estado.in_([EstadoEjecucionMESEnum.PENDIENTE, EstadoEjecucionMESEnum.EN_PROGRESO, EstadoEjecucionMESEnum.PAUSADA]),
            )
        )
        if abiertas:
            raise HTTPException(409, f'No se puede cerrar: hay {abiertas} ejecución(es) abierta(s)')
    obj.estado = EstadoOrdenProduccionEnum[estado]
    if estado == 'EN_EJECUCION' and not obj.fecha_inicio_real:
        obj.fecha_inicio_real = datetime.utcnow()
    if estado in ('CERRADA', 'CANCELADA') and not obj.fecha_fin_real:
        obj.fecha_fin_real = datetime.utcnow()
    await db.commit()
    return {'ok': True, 'estado': estado}


# ─── Lotes ───────────────────────────────────────────────────────────────────

@router.get('/lotes', response_model=List[LoteResponse])
async def list_lotes(producto_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESLote)
    if producto_id:
        q = q.where(MESLote.producto_id == producto_id)
    result = await db.execute(q.order_by(MESLote.created_at.desc()))
    return result.scalars().all()

@router.post('/lotes', response_model=LoteResponse, status_code=201)
async def create_lote(data: LoteCreate, db: AsyncSession = Depends(get_db)):
    obj = MESLote(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


class LoteEstado(BaseModel):
    estado: str                              # LIBERADO / BLOQUEADO / RECHAZADO / VENCIDO
    responsable_liberacion: Optional[str] = None
    observaciones: Optional[str] = None

@router.put('/lotes/{lote_id}/estado', response_model=LoteResponse)
async def cambiar_estado_lote(lote_id: int, data: LoteEstado, db: AsyncSession = Depends(get_db)):
    """Disposición del lote. LIBERADO exige responsable (ISO 9001 §8.6:
    la liberación requiere trazabilidad a la persona que autoriza)."""
    obj = await db.get(MESLote, lote_id)
    if not obj:
        raise HTTPException(404, 'Lote no encontrado')
    if data.estado not in EstadoLoteMESEnum.__members__:
        raise HTTPException(422, f'Estado inválido: {data.estado}')
    if obj.estado == EstadoLoteMESEnum.CONSUMIDO:
        raise HTTPException(409, 'El lote ya fue consumido')
    if data.estado == 'LIBERADO':
        if not data.responsable_liberacion:
            raise HTTPException(422, 'La liberación exige indicar el responsable que autoriza')
        # No se libera un lote con inspecciones rechazadas o pendientes de dictamen
        r = await db.execute(select(MESInspeccion).where(MESInspeccion.lote_id == lote_id))
        insps = r.scalars().all()
        if any(i.resultado == ResultadoInspeccionMESEnum.RECHAZADO for i in insps):
            raise HTTPException(409, 'El lote tiene inspecciones RECHAZADAS: no se puede liberar')
        if any(i.resultado == ResultadoInspeccionMESEnum.PENDIENTE for i in insps):
            raise HTTPException(409, 'El lote tiene inspecciones sin dictaminar: no se puede liberar')
        obj.fecha_liberacion = datetime.utcnow()
        obj.responsable_liberacion = data.responsable_liberacion
    obj.estado = EstadoLoteMESEnum[data.estado]
    if data.observaciones:
        obj.observaciones = data.observaciones
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Trazabilidad (expediente de lote — ISO 9001 §8.5.2) ─────────────────────

@router.get('/trazabilidad/lote/{lote_id}')
async def trazabilidad_lote(lote_id: int, db: AsyncSession = Depends(get_db)):
    """Expediente completo del lote: orden, ejecuciones, paradas, inspecciones
    (con defectos), scrap y consumos de material asociados."""
    lote = await db.get(MESLote, lote_id)
    if not lote:
        raise HTTPException(404, 'Lote no encontrado')
    out: dict = {
        'lote': {
            'id': lote.id, 'numero_lote': lote.numero_lote, 'estado': lote.estado.value,
            'cantidad': lote.cantidad, 'unidad_medida': lote.unidad_medida,
            'producto_id': lote.producto_id,
            'fecha_fabricacion': lote.fecha_fabricacion,
            'fecha_vencimiento': lote.fecha_vencimiento,
            'fecha_liberacion': lote.fecha_liberacion,
            'responsable_liberacion': lote.responsable_liberacion,
        },
        'orden': None, 'ejecuciones': [], 'paradas': [], 'inspecciones': [],
        'scrap': [], 'consumos': [],
        # Por dónde pasó la orden, estación por estación. Es lo que convierte el
        # expediente en trazabilidad de verdad: sin esto dice cuánto se produjo,
        # pero no en qué máquina ni quién la operó, que es justo lo que pregunta
        # un auditor y lo que hace falta cuando hay que recoger un lote.
        'recorrido': [],
    }
    producto = await db.get(MESProducto, lote.producto_id)
    if producto:
        out['lote']['producto'] = {'codigo': producto.codigo, 'nombre': producto.nombre}
    if lote.orden_id:
        orden = await db.get(MESOrdenProduccion, lote.orden_id)
        if orden:
            out['orden'] = {
                'id': orden.id, 'numero': orden.numero, 'estado': orden.estado.value,
                'cantidad_planificada': orden.cantidad_planificada,
                'cantidad_producida': orden.cantidad_producida,
                'cantidad_scrap': orden.cantidad_scrap,
                'fecha_inicio_real': orden.fecha_inicio_real, 'fecha_fin_real': orden.fecha_fin_real,
                'linea_id': orden.linea_id,
            }
            # El recorrido por las estaciones de la línea.
            from app.api.v1.endpoints.mes_planta import (
                ordenar_estaciones as _ordenar)
            from app.infrastructure.models.mes import (
                MESAvanceEstacion as _Avance, MESFlujoConexion as _Conexion,
                MESFlujoNodo as _Nodo)
            if orden.linea_id:
                nodos = list((await db.execute(select(_Nodo).where(
                    _Nodo.linea_id == orden.linea_id))).scalars().all())
                conexiones = list((await db.execute(select(_Conexion).where(
                    _Conexion.linea_id == orden.linea_id))).scalars().all())
                avances = {a.nodo_id: a for a in (await db.execute(select(_Avance)
                    .where(_Avance.orden_id == orden.id))).scalars().all()}
                equipos_nombre = {e.id: e.nombre for e in (await db.execute(
                    select(MESEquipo))).scalars().all()}
                for posicion, nodo in enumerate(_ordenar(nodos, conexiones), start=1):
                    a = avances.get(nodo.id)
                    if a is None:
                        continue
                    out['recorrido'].append({
                        'posicion': posicion,
                        'estacion': (nodo.nombre or equipos_nombre.get(nodo.equipo_id)
                                     or f'Estación {posicion}'),
                        'tipo': nodo.tipo.value if hasattr(nodo.tipo, 'value') else nodo.tipo,
                        'operario_id': a.operario_id,
                        'turno': a.turno.value if hasattr(a.turno, 'value') else a.turno,
                        'estado': a.estado.value if hasattr(a.estado, 'value') else a.estado,
                        'cantidad_producida': a.cantidad_producida,
                        'cantidad_scrap': a.cantidad_scrap,
                        'fecha_inicio': a.fecha_inicio, 'fecha_fin': a.fecha_fin,
                        'observaciones': a.observaciones,
                    })

            r = await db.execute(select(MESEjecucion).where(MESEjecucion.orden_id == orden.id))
            ejecuciones = r.scalars().all()
            out['ejecuciones'] = [{
                'id': e.id, 'estado': e.estado.value, 'turno': e.turno.value,
                'operario_id': e.operario_id, 'equipo_id': e.equipo_id,
                'fecha_inicio': e.fecha_inicio, 'fecha_fin': e.fecha_fin,
                'cantidad_producida': e.cantidad_producida, 'cantidad_scrap': e.cantidad_scrap,
            } for e in ejecuciones]
            ids_ej = [e.id for e in ejecuciones]
            if ids_ej:
                r = await db.execute(select(MESParada).where(MESParada.ejecucion_id.in_(ids_ej)))
                out['paradas'] = [{
                    'id': p.id, 'ejecucion_id': p.ejecucion_id, 'tipo': p.tipo.value, 'causa': p.causa,
                    'fecha_inicio': p.fecha_inicio, 'fecha_fin': p.fecha_fin, 'duracion_min': p.duracion_min,
                } for p in r.scalars().all()]
            r = await db.execute(select(MESScrap).where(MESScrap.orden_id == orden.id))
            out['scrap'] = [{
                'id': s.id, 'tipo': s.tipo.value, 'causa': s.causa, 'cantidad': s.cantidad,
                'costo_total': s.costo_total, 'es_reprocesable': s.es_reprocesable,
                'fecha_registro': s.fecha_registro,
            } for s in r.scalars().all()]
            r = await db.execute(select(MESConsumoMaterial).where(MESConsumoMaterial.orden_id == orden.id))
            out['consumos'] = [{
                'id': c.id, 'producto_id': c.producto_id, 'lote_id': c.lote_id,
                'cantidad_plan': c.cantidad_plan, 'cantidad_real': c.cantidad_real,
                'fecha_consumo': c.fecha_consumo,
            } for c in r.scalars().all()]
    # Inspecciones directas del lote (incluye las de la orden si aplican al lote)
    r = await db.execute(select(MESInspeccion).where(
        (MESInspeccion.lote_id == lote_id) | (MESInspeccion.orden_id == (lote.orden_id or -1))
    ))
    insps = r.scalars().all()
    insp_out = []
    for i in insps:
        rd = await db.execute(select(MESDefecto).where(MESDefecto.inspeccion_id == i.id))
        insp_out.append({
            'id': i.id, 'tipo': i.tipo.value, 'resultado': i.resultado.value,
            'operario_id': i.operario_id, 'fecha_inspeccion': i.fecha_inspeccion,
            'muestra_tam': i.muestra_tam, 'muestra_defectos': i.muestra_defectos,
            'observaciones': i.observaciones,
            'defectos': [{
                'codigo_defecto': d.codigo_defecto, 'descripcion': d.descripcion,
                'cantidad': d.cantidad, 'causa_raiz': d.causa_raiz,
            } for d in rd.scalars().all()],
        })
    out['inspecciones'] = insp_out
    return out


# ─── Ejecucion ───────────────────────────────────────────────────────────────

@router.get('/ejecuciones', response_model=List[EjecucionResponse])
async def list_ejecuciones(orden_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESEjecucion)
    if orden_id:
        q = q.where(MESEjecucion.orden_id == orden_id)
    result = await db.execute(q.order_by(MESEjecucion.created_at.desc()))
    return result.scalars().all()

@router.post('/ejecuciones', response_model=EjecucionResponse, status_code=201)
async def create_ejecucion(data: EjecucionCreate, db: AsyncSession = Depends(get_db)):
    orden = await db.get(MESOrdenProduccion, data.orden_id)
    if not orden:
        raise HTTPException(404, 'Orden no encontrada')
    if orden.estado not in (EstadoOrdenProduccionEnum.LIBERADA, EstadoOrdenProduccionEnum.EN_EJECUCION):
        raise HTTPException(409, f'La orden está {orden.estado.value}: debe estar LIBERADA o EN_EJECUCION para registrar ejecuciones')
    obj = MESEjecucion(**data.model_dump(), fecha_inicio=datetime.utcnow(), estado='EN_PROGRESO')
    # Iniciar la primera ejecución pone la orden EN_EJECUCION automáticamente
    if orden.estado == EstadoOrdenProduccionEnum.LIBERADA:
        orden.estado = EstadoOrdenProduccionEnum.EN_EJECUCION
        if not orden.fecha_inicio_real:
            orden.fecha_inicio_real = datetime.utcnow()
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


class EjecucionCierre(BaseModel):
    cantidad_producida: float
    cantidad_scrap: float = 0.0
    observaciones: Optional[str] = None

@router.put('/ejecuciones/{ejecucion_id}/cerrar', response_model=EjecucionResponse)
async def cerrar_ejecucion(ejecucion_id: int, data: EjecucionCierre, db: AsyncSession = Depends(get_db)):
    """Cierra la ejecución con las cantidades reportadas y las acumula en la orden
    (registro de producción trazable — ISO 9001 §8.5.2)."""
    obj = await db.get(MESEjecucion, ejecucion_id)
    if not obj:
        raise HTTPException(404, 'Ejecución no encontrada')
    if obj.estado in (EstadoEjecucionMESEnum.COMPLETADA, EstadoEjecucionMESEnum.CANCELADA):
        raise HTTPException(409, f'La ejecución ya está {obj.estado.value}')
    if data.cantidad_producida < 0 or data.cantidad_scrap < 0:
        raise HTTPException(422, 'Las cantidades no pueden ser negativas')
    # Paradas abiertas se cierran junto con la ejecución
    r = await db.execute(select(MESParada).where(MESParada.ejecucion_id == ejecucion_id, MESParada.fecha_fin.is_(None)))
    ahora = datetime.utcnow()
    for p in r.scalars().all():
        p.fecha_fin = ahora
        if p.fecha_inicio:
            p.duracion_min = round((ahora - p.fecha_inicio.replace(tzinfo=None)).total_seconds() / 60, 1)
    obj.cantidad_producida = data.cantidad_producida
    obj.cantidad_scrap = data.cantidad_scrap
    obj.observaciones = data.observaciones or obj.observaciones
    obj.fecha_fin = ahora
    obj.estado = EstadoEjecucionMESEnum.COMPLETADA

    orden = await db.get(MESOrdenProduccion, obj.orden_id)
    if orden:
        # La pérdida va al libro de scrap, que es de donde sale la cifra que se
        # mira. Antes se acumulaba directo en la orden con `+=` mientras el
        # terminal de planta REEMPLAZABA ese mismo campo con la suma de las
        # estaciones: el que escribía último ganaba, y la tasa de scrap del
        # tablero era el resultado de esa carrera.
        if data.cantidad_scrap > 0:
            registrar_scrap(
                db, orden_id=orden.id, producto_id=orden.producto_id,
                cantidad=data.cantidad_scrap,
                causa='Reportado al cerrar la ejecución',
                operario_id=obj.operario_id,
                observaciones=data.observaciones)
        await db.flush()
        # Los totales se recalculan desde sus fuentes; no los acumula nadie.
        await recalcular_totales_orden(db, orden)

    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Paradas ─────────────────────────────────────────────────────────────────

class ParadaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # La ejecución es opcional: las paradas que se registran desde una
    # estación del flujo no tienen ejecución, y exigirla hacía fallar la lista
    # entera. El tipo llega como enum y se entrega como texto.
    id: int; ejecucion_id: Optional[int] = None; tipo: str; causa: str
    equipo_id: Optional[int] = None

    @field_validator('tipo', mode='before')
    @classmethod
    def _tipo_texto(cls, v):
        return v.value if hasattr(v, 'value') else v
    descripcion: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    duracion_min: Optional[float] = None

@router.get('/paradas', response_model=List[ParadaResponse])
async def list_paradas(
    ejecucion_id: Optional[int] = None,
    abiertas: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(MESParada)
    if ejecucion_id:
        q = q.where(MESParada.ejecucion_id == ejecucion_id)
    if abiertas:
        q = q.where(MESParada.fecha_fin.is_(None))
    result = await db.execute(q.order_by(MESParada.fecha_inicio.desc()))
    return result.scalars().all()

@router.post('/paradas', response_model=ParadaResponse, status_code=201)
async def create_parada(data: ParadaCreate, db: AsyncSession = Depends(get_db)):
    ej = await db.get(MESEjecucion, data.ejecucion_id)
    if not ej:
        raise HTTPException(404, 'Ejecución no encontrada')
    if ej.estado in (EstadoEjecucionMESEnum.COMPLETADA, EstadoEjecucionMESEnum.CANCELADA):
        raise HTTPException(409, 'No se pueden registrar paradas en una ejecución cerrada')
    obj = MESParada(**data.model_dump(), fecha_inicio=datetime.utcnow())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put('/paradas/{parada_id}/cerrar', response_model=ParadaResponse)
async def cerrar_parada(parada_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(MESParada, parada_id)
    if not obj:
        raise HTTPException(404, 'Parada no encontrada')
    if obj.fecha_fin:
        raise HTTPException(409, 'La parada ya está cerrada')
    obj.fecha_fin = datetime.utcnow()
    if obj.fecha_inicio:
        obj.duracion_min = round((obj.fecha_fin - obj.fecha_inicio.replace(tzinfo=None)).total_seconds() / 60, 1)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Inspecciones ────────────────────────────────────────────────────────────

@router.get('/inspecciones', response_model=List[InspeccionResponse])
async def list_inspecciones(orden_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESInspeccion)
    if orden_id:
        q = q.where(MESInspeccion.orden_id == orden_id)
    result = await db.execute(q.order_by(MESInspeccion.created_at.desc()))
    return result.scalars().all()

@router.post('/inspecciones', response_model=InspeccionResponse, status_code=201)
async def create_inspeccion(data: InspeccionCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(MESOrdenProduccion, data.orden_id):
        raise HTTPException(404, 'Orden no encontrada')
    if not await db.get(MESOperario, data.operario_id):
        raise HTTPException(404, 'Operario (inspector) no encontrado')
    obj = MESInspeccion(**data.model_dump(), fecha_inspeccion=datetime.utcnow())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


class InspeccionResultado(BaseModel):
    resultado: str                      # APROBADO / RECHAZADO / CONDICIONAL
    muestra_defectos: Optional[int] = None
    observaciones: Optional[str] = None

@router.put('/inspecciones/{insp_id}/resultado', response_model=InspeccionResponse)
async def registrar_resultado_inspeccion(insp_id: int, data: InspeccionResultado, db: AsyncSession = Depends(get_db)):
    """Dictamina la inspección (registro de calidad — ISO 9001 §8.6 liberación)."""
    obj = await db.get(MESInspeccion, insp_id)
    if not obj:
        raise HTTPException(404, 'Inspección no encontrada')
    if data.resultado not in ResultadoInspeccionMESEnum.__members__ or data.resultado == 'PENDIENTE':
        raise HTTPException(422, f'Resultado inválido: {data.resultado}')
    if obj.resultado != ResultadoInspeccionMESEnum.PENDIENTE:
        raise HTTPException(409, f'La inspección ya fue dictaminada: {obj.resultado.value}')
    obj.resultado = ResultadoInspeccionMESEnum[data.resultado]
    if data.muestra_defectos is not None:
        obj.muestra_defectos = data.muestra_defectos
    if data.observaciones:
        obj.observaciones = data.observaciones
    # Una inspección RECHAZADA sobre un lote lo bloquea automáticamente
    if data.resultado == 'RECHAZADO' and obj.lote_id:
        lote = await db.get(MESLote, obj.lote_id)
        if lote and lote.estado not in (EstadoLoteMESEnum.CONSUMIDO,):
            lote.estado = EstadoLoteMESEnum.BLOQUEADO
    await db.commit()
    await db.refresh(obj)
    return obj


class DefectoCreate(BaseModel):
    codigo_defecto: str
    descripcion: str
    cantidad: int = 1
    ubicacion: Optional[str] = None
    causa_raiz: Optional[str] = None

class DefectoResponse(DefectoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    inspeccion_id: int

@router.get('/inspecciones/{insp_id}/defectos', response_model=List[DefectoResponse])
async def list_defectos(insp_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(MESDefecto).where(MESDefecto.inspeccion_id == insp_id))
    return r.scalars().all()

@router.post('/inspecciones/{insp_id}/defectos', response_model=DefectoResponse, status_code=201)
async def create_defecto(insp_id: int, data: DefectoCreate, db: AsyncSession = Depends(get_db)):
    insp = await db.get(MESInspeccion, insp_id)
    if not insp:
        raise HTTPException(404, 'Inspección no encontrada')
    obj = MESDefecto(inspeccion_id=insp_id, **data.model_dump())
    insp.muestra_defectos = (insp.muestra_defectos or 0) + data.cantidad
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Scrap ───────────────────────────────────────────────────────────────────

@router.get('/scrap', response_model=List[ScrapResponse])
async def list_scrap(orden_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESScrap)
    if orden_id:
        q = q.where(MESScrap.orden_id == orden_id)
    result = await db.execute(q.order_by(MESScrap.created_at.desc()))
    return result.scalars().all()

@router.post('/scrap', response_model=ScrapResponse, status_code=201)
async def create_scrap(data: ScrapCreate, db: AsyncSession = Depends(get_db)):
    if data.cantidad <= 0:
        raise HTTPException(422, 'La cantidad de scrap debe ser mayor que cero')
    if not data.causa.strip():
        raise HTTPException(422, 'La causa del scrap es obligatoria: sin ella el '
                                 'registro no sirve para corregir nada')
    orden = await db.get(MESOrdenProduccion, data.orden_id)
    if not orden:
        raise HTTPException(404, 'Orden no encontrada')
    if not await db.get(MESProducto, data.producto_id):
        raise HTTPException(404, 'Producto no encontrado')

    d = data.model_dump()
    d['causa'] = data.causa.strip()
    if d.get('costo_unitario') and d.get('cantidad'):
        d['costo_total'] = d['costo_unitario'] * d['cantidad']
    d['fecha_registro'] = _ahora()
    obj = MESScrap(**d)
    db.add(obj)
    # El scrap de la orden es la suma de su libro: al agregar una pérdida hay
    # que volver a totalizar, o el tablero se queda con la cifra anterior.
    await db.flush()
    await recalcular_totales_orden(db, orden)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── OEE ─────────────────────────────────────────────────────────────────────

@router.get('/oee', response_model=List[OEEResponse])
async def list_oee(linea_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(MESOEERegistro)
    if linea_id:
        q = q.where(MESOEERegistro.linea_id == linea_id)
    result = await db.execute(q.order_by(MESOEERegistro.created_at.desc()))
    return result.scalars().all()

@router.post('/oee', response_model=OEEResponse, status_code=201)
async def create_oee(data: OEECreate, db: AsyncSession = Depends(get_db)):
    d = data.model_dump()
    tp = d['tiempo_planificado_min']
    to = d['tiempo_operativo_min']
    pn = d['produccion_nominal']
    pr = d['produccion_real']
    pb = d['produccion_buena']
    disp = (to / tp * 100) if tp > 0 else 0
    rend = (pr / pn * 100) if pn > 0 else 0
    cal  = (pb / pr * 100) if pr > 0 else 0
    oee  = (disp * rend * cal / 10000)
    d.update({'disponibilidad': round(disp, 2), 'rendimiento': round(rend, 2),
              'calidad': round(cal, 2), 'oee': round(oee, 2),
              'fecha': datetime.utcnow()})
    obj = MESOEERegistro(**d)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── Checklists ──────────────────────────────────────────────────────────────

@router.get('/checklists/plantillas')
async def list_checklist_plantillas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESChecklistPlantilla).where(MESChecklistPlantilla.activo == True))
    return result.scalars().all()

@router.post('/checklists/plantillas', status_code=201)
async def create_checklist_plantilla(nombre: str, aplica_a: str = 'ORDEN', db: AsyncSession = Depends(get_db)):
    obj = MESChecklistPlantilla(nombre=nombre, aplica_a=aplica_a)
    db.add(obj)
    await db.commit()
    return {'ok': True, 'id': obj.id}

@router.post('/checklists/ejecuciones', status_code=201)
async def create_checklist_ejecucion(
    orden_id: int, plantilla_id: int, operario_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    obj = MESChecklistEjecucion(
        orden_id=orden_id, plantilla_id=plantilla_id,
        operario_id=operario_id, fecha=datetime.utcnow()
    )
    db.add(obj)
    await db.commit()
    return {'ok': True, 'id': obj.id}


# ─── KPIs ────────────────────────────────────────────────────────────────────

@router.get('/kpis/diarios')
async def get_kpis_diarios(limit: int = 30, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MESKPIDiario).order_by(MESKPIDiario.fecha.desc()).limit(limit))
    return result.scalars().all()


# ══════════════════════════════════════════════════════════════════════════════
# EDITAR Y DAR DE BAJA LA CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════
#
# Hasta acá el módulo solo sabía listar y crear. Una planta se configura una vez
# y se corrige muchas: cambia el nombre de una línea, se reubica una máquina, se
# retira un equipo. Sin editar, el único camino era crear otro registro y dejar
# el anterior estorbando, que es como se llena un catálogo de duplicados.
#
# La baja desactiva en vez de borrar. Una máquina retirada sigue apareciendo en
# las órdenes, las paradas y el OEE del año pasado: borrarla dejaría ese
# histórico sin a qué referirse.

async def _actualizar(db: AsyncSession, modelo, oid: int, data: BaseModel, que: str):
    obj = await db.get(modelo, oid)
    if not obj:
        raise HTTPException(404, f'{que} no encontrado')
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(obj, campo, valor.strip() if isinstance(valor, str) else valor)
    await db.commit()
    await db.refresh(obj)
    return obj


async def _desactivar(db: AsyncSession, modelo, oid: int, que: str):
    obj = await db.get(modelo, oid)
    if not obj:
        raise HTTPException(404, f'{que} no encontrado')
    obj.activo = False
    await db.commit()


@router.put('/plantas/{pid}', response_model=PlantaResponse)
async def update_planta(pid: int, data: PlantaCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESPlanta, pid, data, 'Planta')


@router.delete('/plantas/{pid}', status_code=204)
async def delete_planta(pid: int, db: AsyncSession = Depends(get_db)):
    # Una planta con líneas activas no se retira sola: primero hay que decidir
    # qué pasa con ellas, y hacerlo en silencio dejaría líneas huérfanas
    # apuntando a una planta que ya no aparece en ninguna lista.
    r = await db.execute(select(func.count()).select_from(MESLinea).where(and_(
        MESLinea.planta_id == pid, MESLinea.activo == True)))
    if (r.scalar() or 0) > 0:
        raise HTTPException(409, 'Esa planta todavía tiene líneas activas. '
                                 'Retire o mueva sus líneas antes de darla de baja.')
    await _desactivar(db, MESPlanta, pid, 'Planta')


@router.put('/lineas/{lid}', response_model=LineaResponse)
async def update_linea(lid: int, data: LineaCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESLinea, lid, data, 'Línea')


@router.delete('/lineas/{lid}', status_code=204)
async def delete_linea(lid: int, db: AsyncSession = Depends(get_db)):
    await _desactivar(db, MESLinea, lid, 'Línea')


@router.put('/celdas/{cid}', response_model=CeldaResponse)
async def update_celda(cid: int, data: CeldaCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESCeldaTrabajo, cid, data, 'Celda')


@router.delete('/celdas/{cid}', status_code=204)
async def delete_celda(cid: int, db: AsyncSession = Depends(get_db)):
    # Las máquinas de la celda quedan sin celda, no de baja: la máquina sigue
    # existiendo y se puede reasignar. Retirarla junto con la celda sería
    # perder un equipo por reorganizar el taller.
    r = await db.execute(select(MESEquipo).where(MESEquipo.celda_id == cid))
    for equipo in r.scalars().all():
        equipo.celda_id = None
    await _desactivar(db, MESCeldaTrabajo, cid, 'Celda')


@router.put('/equipos/{eid}', response_model=EquipoResponse)
async def update_equipo(eid: int, data: EquipoCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESEquipo, eid, data, 'Equipo')


@router.delete('/equipos/{eid}', status_code=204)
async def delete_equipo(eid: int, db: AsyncSession = Depends(get_db)):
    await _desactivar(db, MESEquipo, eid, 'Equipo')


@router.put('/operarios/{oid}', response_model=OperarioResponse)
async def update_operario(oid: int, data: OperarioCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESOperario, oid, data, 'Operario')


@router.delete('/operarios/{oid}', status_code=204)
async def delete_operario(oid: int, db: AsyncSession = Depends(get_db)):
    await _desactivar(db, MESOperario, oid, 'Operario')


@router.put('/turnos/{tid}', response_model=TurnoResponse)
async def update_turno(tid: int, data: TurnoCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESTurno, tid, data, 'Turno')


@router.delete('/turnos/{tid}', status_code=204)
async def delete_turno(tid: int, db: AsyncSession = Depends(get_db)):
    await _desactivar(db, MESTurno, tid, 'Turno')


@router.put('/productos/{pid}', response_model=ProductoResponse)
async def update_producto(pid: int, data: ProductoCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESProducto, pid, data, 'Material')


@router.delete('/productos/{pid}', status_code=204)
async def delete_producto(pid: int, db: AsyncSession = Depends(get_db)):
    await _desactivar(db, MESProducto, pid, 'Material')


# ══════════════════════════════════════════════════════════════════════════════
# OPERACIONES
# ══════════════════════════════════════════════════════════════════════════════
#
# La operación es QUÉ se hace en una etapa —troquelar, sellar, envasar— y la
# máquina es CON QUÉ. Van separadas porque la misma operación se hace en
# máquinas distintas según la línea, y la misma máquina hace operaciones
# distintas según el producto. La tabla existía desde el principio pero no
# tenía por dónde entrar; sin ella el esquema solo puede decir qué máquina hay
# en cada punto, no qué ocurre ahí.

class OperacionCreate(BaseModel):
    celda_id: Optional[int] = None
    codigo: str
    nombre: str
    # Del catálogo MES/TIPO_OPERACION. Clasifica la operación para poder
    # compararla entre plantas que le dan nombres distintos a lo mismo.
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    tiempo_std_min: Optional[float] = None
    requiere_inspeccion: bool = False


class OperacionResponse(OperacionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool


@router.get('/operaciones', response_model=List[OperacionResponse])
async def list_operaciones(celda_id: Optional[int] = None,
                           db: AsyncSession = Depends(get_db)):
    q = select(MESOperacion).where(MESOperacion.activo == True)
    if celda_id:
        q = q.where(MESOperacion.celda_id == celda_id)
    result = await db.execute(q.order_by(MESOperacion.codigo))
    return result.scalars().all()


@router.post('/operaciones', response_model=OperacionResponse, status_code=201)
async def create_operacion(data: OperacionCreate, db: AsyncSession = Depends(get_db)):
    codigo = (data.codigo or '').strip()
    if not codigo:
        raise HTTPException(400, 'El código de la operación es obligatorio')
    r = await db.execute(select(MESOperacion).where(
        func.lower(MESOperacion.codigo) == codigo.lower()))
    if r.scalar_one_or_none():
        raise HTTPException(409, f'Ya existe una operación con el código {codigo}')
    obj = MESOperacion(**{**data.model_dump(), 'codigo': codigo})
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put('/operaciones/{oid}', response_model=OperacionResponse)
async def update_operacion(oid: int, data: OperacionCreate, db: AsyncSession = Depends(get_db)):
    return await _actualizar(db, MESOperacion, oid, data, 'Operación')


@router.delete('/operaciones/{oid}', status_code=204)
async def delete_operacion(oid: int, db: AsyncSession = Depends(get_db)):
    await _desactivar(db, MESOperacion, oid, 'Operación')
