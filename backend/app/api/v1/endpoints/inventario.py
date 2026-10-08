"""
Inventario del CMMS — bodegas, existencias, kárdex, ajustes y rotación.

El motor que mueve saldos y deja kárdex vive en `core/inventario_kardex.py`,
porque lo comparten esta pantalla y las órdenes de trabajo.

LO QUE ESTE MÓDULO RESPONDE
  Existencias   cuánto hay de cada repuesto y en qué bodega
  Kárdex        de dónde salió cada unidad y a qué costo
  Rotación      qué se mueve, qué está dormido y cuántos meses de stock hay
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_, or_, desc, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.inventario_kardex import (
    mover, recalcular_existencias, bodega_por_defecto,
    TIPOS_ENTRADA, TIPOS_SALIDA,
)
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.catalogo import CatalogoMaestro
from app.infrastructure.models.eam import EAMRepuesto, EAMOrdenTrabajo
from app.infrastructure.models.inventario import (
    InvBodega, InvExistencia, InvMotivo, InvMovimiento,
)

router = APIRouter(prefix="/eam/inventario", tags=["CMMS/EAM · Inventario"])

ETIQUETA_TIPO = {
    "ENTRADA": "Entrada", "SALIDA": "Salida",
    "AJUSTE_ENTRADA": "Ajuste (+)", "AJUSTE_SALIDA": "Ajuste (−)",
    "TRASLADO_ENTRADA": "Traslado recibido", "TRASLADO_SALIDA": "Traslado enviado",
    "DEVOLUCION": "Devolución",
}


def _quien(u: Usuario) -> str:
    return getattr(u, "username", None) or getattr(u, "nombre", None) or "—"


# ══════════════════════════════════════════════════════════════════════════════
# BODEGAS
# ══════════════════════════════════════════════════════════════════════════════

class BodegaIn(BaseModel):
    codigo: str
    nombre: str
    pais_id: Optional[int] = None
    ciudad_id: Optional[int] = None
    direccion: Optional[str] = None
    responsable: Optional[str] = None
    telefono: Optional[str] = None
    por_defecto: bool = False
    observaciones: Optional[str] = None
    activo: bool = True


class BodegaOut(BodegaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    referencias: Optional[int] = None
    valor: Optional[float] = None


async def _geografia(db: AsyncSession, ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Nombre de cada nodo del catálogo y el de sus padres.

    La ciudad cuelga del departamento y éste del país, así que con subir por
    `padre_id` se arma la ruta completa sin guardarla repetida en la bodega.
    """
    if not ids:
        return {}
    r = await db.execute(select(CatalogoMaestro))
    todos = {c.id: c for c in r.scalars().all()}
    salida: Dict[int, Dict[str, Any]] = {}
    for nodo_id in ids:
        nodo = todos.get(nodo_id)
        if not nodo:
            continue
        ruta = {"nombre": nodo.nombre, "tipo": nodo.tipo}
        padre = todos.get(nodo.padre_id) if nodo.padre_id else None
        cadena = []
        while padre:
            cadena.append((padre.tipo, padre.nombre))
            padre = todos.get(padre.padre_id) if padre.padre_id else None
        ruta["cadena"] = dict(cadena)
        salida[nodo_id] = ruta
    return salida


@router.get("/bodegas", response_model=List[BodegaOut])
async def listar_bodegas(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(InvBodega).where(InvBodega.activo.is_(True))
                         .order_by(InvBodega.codigo))
    bodegas = list(r.scalars().all())

    geo = await _geografia(db, [b.ciudad_id for b in bodegas if b.ciudad_id]
                           + [b.pais_id for b in bodegas if b.pais_id])

    r = await db.execute(
        select(InvExistencia.bodega_id, func.count(InvExistencia.id),
               func.coalesce(func.sum(InvExistencia.cantidad
                                      * InvExistencia.costo_promedio), 0))
        .group_by(InvExistencia.bodega_id))
    resumen = {bid: (n, float(v or 0)) for bid, n, v in r.all()}

    salida = []
    for b in bodegas:
        d = BodegaOut.model_validate(b).model_dump()
        ciudad = geo.get(b.ciudad_id) if b.ciudad_id else None
        pais = geo.get(b.pais_id) if b.pais_id else None
        d["ciudad"] = ciudad["nombre"] if ciudad else None
        d["departamento"] = (ciudad or {}).get("cadena", {}).get("DEPARTAMENTO")
        # Si la ciudad ya trae su país en la cadena, se prefiere ése: es el que
        # de verdad corresponde, aunque alguien haya escogido otro a mano.
        d["pais"] = ((ciudad or {}).get("cadena", {}).get("PAIS")
                     or (pais["nombre"] if pais else None))
        n, valor = resumen.get(b.id, (0, 0.0))
        d["referencias"], d["valor"] = n, round(valor, 2)
        salida.append(d)
    return salida


@router.post("/bodegas", response_model=BodegaOut, status_code=201)
async def crear_bodega(data: BodegaIn, db: AsyncSession = Depends(get_db)):
    codigo = (data.codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(400, "El código es obligatorio")
    r = await db.execute(select(func.count()).select_from(InvBodega)
                         .where(func.upper(InvBodega.codigo) == codigo))
    if r.scalar():
        raise HTTPException(409, f"Ya existe una bodega con el código «{codigo}»")

    # Si la ciudad y el país no concuerdan, el informe por región mentiría.
    if data.ciudad_id and data.pais_id:
        geo = await _geografia(db, [data.ciudad_id])
        pais_real = geo.get(data.ciudad_id, {}).get("cadena", {}).get("PAIS")
        pais = await db.get(CatalogoMaestro, data.pais_id)
        if pais_real and pais and pais_real != pais.nombre:
            raise HTTPException(
                400, f"Esa ciudad pertenece a {pais_real}, no a {pais.nombre}.")

    obj = InvBodega(**{**data.model_dump(), "codigo": codigo})
    if data.por_defecto:
        await _quitar_defecto(db)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return BodegaOut.model_validate(obj)


async def _quitar_defecto(db: AsyncSession) -> None:
    """Solo una bodega puede ser la de por defecto."""
    r = await db.execute(select(InvBodega).where(InvBodega.por_defecto.is_(True)))
    for b in r.scalars().all():
        b.por_defecto = False


@router.put("/bodegas/{bid}", response_model=BodegaOut)
async def editar_bodega(bid: int, data: BodegaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(InvBodega, bid)
    if not obj:
        raise HTTPException(404, "Esa bodega no existe")
    if data.por_defecto and not obj.por_defecto:
        await _quitar_defecto(db)
    for k, v in data.model_dump().items():
        setattr(obj, k, v.strip().upper() if k == "codigo" and isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return BodegaOut.model_validate(obj)


@router.delete("/bodegas/{bid}", status_code=204)
async def borrar_bodega(bid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(InvBodega, bid)
    if not obj:
        raise HTTPException(404, "Esa bodega no existe")
    r = await db.execute(select(func.count()).select_from(InvExistencia).where(and_(
        InvExistencia.bodega_id == bid, InvExistencia.cantidad != 0)))
    if r.scalar():
        raise HTTPException(
            409, "No se puede desactivar: todavía tiene existencias. Trasládelas o ajústelas "
                 "a cero primero.")
    obj.activo = False
    await db.commit()


@router.get("/geografia", response_model=Dict[str, List[Dict[str, Any]]])
async def geografia(db: AsyncSession = Depends(get_db)):
    """Países y ciudades del catálogo maestro, para armar la jerarquía."""
    r = await db.execute(select(CatalogoMaestro).where(and_(
        CatalogoMaestro.tipo.in_(("PAIS", "DEPARTAMENTO", "CIUDAD")),
        CatalogoMaestro.activo.is_(True))).order_by(CatalogoMaestro.nombre))
    nodos = list(r.scalars().all())
    por_id = {n.id: n for n in nodos}

    def _pais_de(nodo):
        actual = nodo
        while actual and actual.tipo != "PAIS":
            actual = por_id.get(actual.padre_id) if actual.padre_id else None
        return actual

    return {
        "paises": [{"id": n.id, "nombre": n.nombre}
                   for n in nodos if n.tipo == "PAIS"],
        "ciudades": [{"id": n.id, "nombre": n.nombre,
                      "departamento": (por_id.get(n.padre_id).nombre
                                       if n.padre_id and por_id.get(n.padre_id) else None),
                      "pais_id": (_pais_de(n).id if _pais_de(n) else None),
                      "pais": (_pais_de(n).nombre if _pais_de(n) else None)}
                     for n in nodos if n.tipo == "CIUDAD"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# MOTIVOS DE AJUSTE
# ══════════════════════════════════════════════════════════════════════════════

class MotivoIn(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    sentido: str = "AMBOS"
    descripcion: Optional[str] = None
    activo: bool = True


class MotivoOut(MotivoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.get("/motivos", response_model=List[MotivoOut])
async def listar_motivos(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(InvMotivo).where(InvMotivo.activo.is_(True))
                         .order_by(InvMotivo.nombre))
    return list(r.scalars().all())


@router.post("/motivos", response_model=MotivoOut, status_code=201)
async def crear_motivo(data: MotivoIn, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio")
    r = await db.execute(select(func.count()).select_from(InvMotivo)
                         .where(func.lower(InvMotivo.nombre) == nombre.lower()))
    if r.scalar():
        raise HTTPException(409, f"Ya existe el motivo «{nombre}»")
    obj = InvMotivo(**{**data.model_dump(), "nombre": nombre})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/motivos/{mid}", status_code=204)
async def borrar_motivo(mid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(InvMotivo, mid)
    if not obj:
        raise HTTPException(404, "Ese motivo no existe")
    obj.activo = False
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# EXISTENCIAS
# ══════════════════════════════════════════════════════════════════════════════

class ExistenciaOut(BaseModel):
    repuesto_id: int
    codigo: str
    nombre: str
    categoria: Optional[str] = None
    unidad: Optional[str] = None
    bodega_id: int
    bodega: str
    cantidad: float
    costo_promedio: float
    valor: float
    stock_minimo: Optional[float] = None
    stock_maximo: Optional[float] = None
    ubicacion: Optional[str] = None
    ultimo_movimiento: Optional[datetime] = None
    bajo_minimo: bool = False
    negativo: bool = False


@router.get("/existencias", response_model=List[ExistenciaOut])
async def existencias(bodega_id: Optional[int] = None, buscar: Optional[str] = None,
                      solo_alertas: bool = False,
                      db: AsyncSession = Depends(get_db)):
    q = (select(InvExistencia, EAMRepuesto, InvBodega)
         .join(EAMRepuesto, EAMRepuesto.id == InvExistencia.repuesto_id)
         .join(InvBodega, InvBodega.id == InvExistencia.bodega_id)
         .order_by(EAMRepuesto.nombre))
    if bodega_id:
        q = q.where(InvExistencia.bodega_id == bodega_id)
    if buscar:
        q = q.where(or_(EAMRepuesto.nombre.ilike(f"%{buscar}%"),
                        EAMRepuesto.codigo.ilike(f"%{buscar}%")))

    salida = []
    for e, rep, bod in (await db.execute(q)).all():
        minimo = e.stock_minimo if e.stock_minimo is not None else rep.stock_minimo
        bajo = minimo is not None and (e.cantidad or 0) < minimo
        negativo = (e.cantidad or 0) < 0
        if solo_alertas and not (bajo or negativo):
            continue
        salida.append(ExistenciaOut(
            repuesto_id=rep.id, codigo=rep.codigo, nombre=rep.nombre,
            categoria=rep.categoria, unidad=rep.unidad_medida,
            bodega_id=bod.id, bodega=bod.nombre,
            cantidad=round(e.cantidad or 0, 2),
            costo_promedio=round(e.costo_promedio or 0, 2),
            valor=round((e.cantidad or 0) * (e.costo_promedio or 0), 2),
            stock_minimo=minimo, stock_maximo=e.stock_maximo,
            ubicacion=e.ubicacion, ultimo_movimiento=e.ultimo_movimiento,
            bajo_minimo=bajo, negativo=negativo))
    return salida


class ParametrosExistencia(BaseModel):
    stock_minimo: Optional[float] = None
    stock_maximo: Optional[float] = None
    ubicacion: Optional[str] = None


@router.put("/existencias/{repuesto_id}/{bodega_id}", response_model=Dict[str, Any])
async def parametros(repuesto_id: int, bodega_id: int, data: ParametrosExistencia,
                     db: AsyncSession = Depends(get_db)):
    """Mínimos, máximos y ubicación. No toca cantidades: eso solo por kárdex."""
    r = await db.execute(select(InvExistencia).where(and_(
        InvExistencia.repuesto_id == repuesto_id,
        InvExistencia.bodega_id == bodega_id)))
    fila = r.scalar_one_or_none()
    if not fila:
        fila = InvExistencia(repuesto_id=repuesto_id, bodega_id=bodega_id,
                             cantidad=0, costo_promedio=0)
        db.add(fila)
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(fila, k, v)
    await db.commit()
    return {"repuesto_id": repuesto_id, "bodega_id": bodega_id}


# ══════════════════════════════════════════════════════════════════════════════
# MOVIMIENTOS
# ══════════════════════════════════════════════════════════════════════════════

class MovimientoIn(BaseModel):
    repuesto_id: int
    bodega_id: int
    tipo: str
    cantidad: float
    costo_unitario: Optional[float] = None
    fecha: Optional[datetime] = None
    motivo_id: Optional[int] = None
    documento: Optional[str] = None
    proveedor: Optional[str] = None
    observaciones: Optional[str] = None


class TrasladoIn(BaseModel):
    repuesto_id: int
    bodega_origen_id: int
    bodega_destino_id: int
    cantidad: float
    fecha: Optional[datetime] = None
    observaciones: Optional[str] = None


class MovimientoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha: datetime
    repuesto_id: int
    bodega_id: int
    tipo: str
    cantidad: float
    costo_unitario: float
    costo_total: float
    saldo_cantidad: Optional[float] = None
    ot_id: Optional[int] = None
    motivo_id: Optional[int] = None
    documento: Optional[str] = None
    proveedor: Optional[str] = None
    observaciones: Optional[str] = None
    registrado_por: Optional[str] = None
    codigo: Optional[str] = None
    repuesto: Optional[str] = None
    bodega: Optional[str] = None
    motivo: Optional[str] = None
    ot_numero: Optional[str] = None
    tipo_label: Optional[str] = None
    signo: Optional[int] = None


@router.get("/movimientos", response_model=List[MovimientoOut])
async def kardex(repuesto_id: Optional[int] = None, bodega_id: Optional[int] = None,
                 tipo: Optional[str] = None, desde: Optional[datetime] = None,
                 hasta: Optional[datetime] = None,
                 limite: int = Query(500, le=5000),
                 db: AsyncSession = Depends(get_db)):
    q = (select(InvMovimiento, EAMRepuesto, InvBodega, InvMotivo, EAMOrdenTrabajo)
         .join(EAMRepuesto, EAMRepuesto.id == InvMovimiento.repuesto_id)
         .join(InvBodega, InvBodega.id == InvMovimiento.bodega_id)
         .outerjoin(InvMotivo, InvMotivo.id == InvMovimiento.motivo_id)
         .outerjoin(EAMOrdenTrabajo, EAMOrdenTrabajo.id == InvMovimiento.ot_id)
         .order_by(desc(InvMovimiento.fecha), desc(InvMovimiento.id)).limit(limite))
    if repuesto_id:
        q = q.where(InvMovimiento.repuesto_id == repuesto_id)
    if bodega_id:
        q = q.where(InvMovimiento.bodega_id == bodega_id)
    if tipo:
        q = q.where(InvMovimiento.tipo == tipo)
    if desde:
        q = q.where(InvMovimiento.fecha >= desde)
    if hasta:
        q = q.where(InvMovimiento.fecha <= hasta)

    salida = []
    for mov, rep, bod, mot, ot in (await db.execute(q)).all():
        d = MovimientoOut.model_validate(mov).model_dump()
        d.update(codigo=rep.codigo, repuesto=rep.nombre, bodega=bod.nombre,
                 motivo=mot.nombre if mot else None,
                 ot_numero=ot.numero if ot else None,
                 tipo_label=ETIQUETA_TIPO.get(mov.tipo, mov.tipo),
                 signo=1 if mov.tipo in TIPOS_ENTRADA else -1)
        salida.append(d)
    return salida


@router.post("/movimientos", response_model=Dict[str, Any], status_code=201)
async def crear_movimiento(data: MovimientoIn, db: AsyncSession = Depends(get_db),
                           usuario: Usuario = Depends(get_current_user)):
    if data.tipo not in ("ENTRADA", "AJUSTE_ENTRADA", "AJUSTE_SALIDA", "SALIDA"):
        raise HTTPException(
            400, "Desde acá solo se registran entradas, salidas y ajustes. Los traslados "
                 "tienen su propia operación y las salidas por orden las genera la orden.")
    if not await db.get(EAMRepuesto, data.repuesto_id):
        raise HTTPException(400, "Ese repuesto no existe")
    if not await db.get(InvBodega, data.bodega_id):
        raise HTTPException(400, "Esa bodega no existe")
    if data.tipo.startswith("AJUSTE") and not data.motivo_id:
        raise HTTPException(
            400, "Un ajuste necesita motivo: sin él, tres meses después nadie puede explicar "
                 "el descuadre.")
    try:
        mov = await mover(db, repuesto_id=data.repuesto_id, bodega_id=data.bodega_id,
                          tipo=data.tipo, cantidad=data.cantidad,
                          costo_unitario=data.costo_unitario, fecha=data.fecha,
                          motivo_id=data.motivo_id, documento=data.documento,
                          proveedor=data.proveedor, observaciones=data.observaciones,
                          usuario=_quien(usuario))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    return {"id": mov.id, "saldo": mov.saldo_cantidad,
            "costo_promedio": mov.saldo_costo_promedio,
            "negativo": (mov.saldo_cantidad or 0) < 0}


@router.post("/traslados", response_model=Dict[str, Any], status_code=201)
async def trasladar(data: TrasladoIn, db: AsyncSession = Depends(get_db),
                    usuario: Usuario = Depends(get_current_user)):
    """Mueve material entre bodegas: dos movimientos ligados entre sí.

    El costo viaja con el material: la entrada en destino usa el promedio de
    origen, no el suyo. Si no, trasladar cambiaría el valor del inventario sin
    que haya pasado nada económico.
    """
    if data.bodega_origen_id == data.bodega_destino_id:
        raise HTTPException(400, "El origen y el destino son la misma bodega")
    r = await db.execute(select(InvExistencia).where(and_(
        InvExistencia.repuesto_id == data.repuesto_id,
        InvExistencia.bodega_id == data.bodega_origen_id)))
    origen = r.scalar_one_or_none()
    costo = origen.costo_promedio if origen else 0

    salida = await mover(db, repuesto_id=data.repuesto_id,
                         bodega_id=data.bodega_origen_id, tipo="TRASLADO_SALIDA",
                         cantidad=data.cantidad, costo_unitario=costo,
                         fecha=data.fecha, observaciones=data.observaciones,
                         usuario=_quien(usuario))
    entrada = await mover(db, repuesto_id=data.repuesto_id,
                          bodega_id=data.bodega_destino_id, tipo="TRASLADO_ENTRADA",
                          cantidad=data.cantidad, costo_unitario=costo,
                          fecha=data.fecha, traslado_id=salida.id,
                          observaciones=data.observaciones, usuario=_quien(usuario))
    salida.traslado_id = entrada.id
    await db.commit()
    return {"salida_id": salida.id, "entrada_id": entrada.id,
            "costo_unitario": costo,
            "saldo_origen": salida.saldo_cantidad,
            "saldo_destino": entrada.saldo_cantidad}


@router.post("/recalcular", response_model=Dict[str, int])
async def recalcular(db: AsyncSession = Depends(get_db)):
    """Reconstruye las existencias desde el kárdex. Si corrige algo, había un
    problema: el kárdex es la verdad y la existencia es solo un saldo guardado."""
    return await recalcular_existencias(db)


# ══════════════════════════════════════════════════════════════════════════════
# INFORMES
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/resumen", response_model=Dict[str, Any])
async def resumen(dias: int = Query(90, ge=7, le=1095),
                  db: AsyncSession = Depends(get_db)):
    desde = datetime.utcnow() - timedelta(days=dias)

    r = await db.execute(select(
        func.count(InvExistencia.id),
        func.coalesce(func.sum(InvExistencia.cantidad * InvExistencia.costo_promedio), 0),
        func.sum(case((InvExistencia.cantidad < 0, 1), else_=0))))
    referencias, valor, negativas = r.one()

    r = await db.execute(
        select(InvMovimiento.tipo, func.count(InvMovimiento.id),
               func.coalesce(func.sum(InvMovimiento.costo_total), 0))
        .where(InvMovimiento.fecha >= desde).group_by(InvMovimiento.tipo))
    por_tipo = [{"tipo": t, "etiqueta": ETIQUETA_TIPO.get(t, t), "cantidad": c,
                 "valor": round(float(v or 0), 2),
                 "signo": 1 if t in TIPOS_ENTRADA else -1} for t, c, v in r.all()]

    entradas = sum(x["valor"] for x in por_tipo if x["signo"] > 0)
    salidas = sum(x["valor"] for x in por_tipo if x["signo"] < 0)

    # Bajo mínimo: se compara contra el mínimo de la bodega y, si no tiene, el
    # del repuesto.
    r = await db.execute(
        select(InvExistencia, EAMRepuesto)
        .join(EAMRepuesto, EAMRepuesto.id == InvExistencia.repuesto_id))
    bajo_minimo = 0
    for e, rep in r.all():
        minimo = e.stock_minimo if e.stock_minimo is not None else rep.stock_minimo
        if minimo is not None and (e.cantidad or 0) < minimo:
            bajo_minimo += 1

    return {
        "periodo_dias": dias,
        "referencias": referencias or 0,
        "valor_inventario": round(float(valor or 0), 2),
        "existencias_negativas": int(negativas or 0),
        "bajo_minimo": bajo_minimo,
        "entradas_valor": round(entradas, 2),
        "salidas_valor": round(salidas, 2),
        "por_tipo": por_tipo,
    }


@router.get("/rotacion", response_model=Dict[str, Any])
async def rotacion(dias: int = Query(180, ge=30, le=1095),
                   bodega_id: Optional[int] = None,
                   db: AsyncSession = Depends(get_db)):
    """Rotación por repuesto.

    CÓMO SE CALCULA
        rotación = valor de las salidas del periodo ÷ valor del inventario actual
        meses de stock = existencia ÷ consumo mensual promedio

    Se usa el inventario actual y no el promedio del periodo porque el kárdex no
    guarda una foto diaria: reconstruir el saldo día por día para toda la flota
    sería costoso y el resultado no cambiaría las decisiones. Queda dicho para
    que nadie lo lea como una rotación contable exacta.

    Lo que de verdad se busca acá es la cola: el material dormido, que es plata
    quieta en un estante.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    meses = dias / 30.0

    q = (select(InvMovimiento.repuesto_id,
                func.sum(case((InvMovimiento.tipo.in_(tuple(TIPOS_SALIDA)),
                               InvMovimiento.cantidad), else_=0)),
                func.sum(case((InvMovimiento.tipo.in_(tuple(TIPOS_SALIDA)),
                               InvMovimiento.costo_total), else_=0)),
                func.count(InvMovimiento.id))
         .where(InvMovimiento.fecha >= desde)
         .group_by(InvMovimiento.repuesto_id))
    if bodega_id:
        q = q.where(InvMovimiento.bodega_id == bodega_id)
    consumo = {rid: (float(c or 0), float(v or 0), n) for rid, c, v, n in (await db.execute(q)).all()}

    qe = (select(InvExistencia.repuesto_id,
                 func.sum(InvExistencia.cantidad),
                 func.max(InvExistencia.ultimo_movimiento),
                 func.sum(InvExistencia.cantidad * InvExistencia.costo_promedio))
          .group_by(InvExistencia.repuesto_id))
    if bodega_id:
        qe = qe.where(InvExistencia.bodega_id == bodega_id)
    existencias = {rid: (float(c or 0), ult, float(v or 0))
                   for rid, c, ult, v in (await db.execute(qe)).all()}

    r = await db.execute(select(EAMRepuesto))
    repuestos = {x.id: x for x in r.scalars().all()}

    ahora = datetime.utcnow()
    filas = []
    for rid in set(consumo) | set(existencias):
        rep = repuestos.get(rid)
        if not rep:
            continue
        cant_salida, valor_salida, movimientos = consumo.get(rid, (0.0, 0.0, 0))
        cantidad, ultimo, valor = existencias.get(rid, (0.0, None, 0.0))
        consumo_mensual = cant_salida / meses if meses else 0
        filas.append({
            "repuesto_id": rid, "codigo": rep.codigo, "nombre": rep.nombre,
            "categoria": rep.categoria,
            "existencia": round(cantidad, 2), "valor": round(valor, 2),
            "salidas": round(cant_salida, 2), "valor_salidas": round(valor_salida, 2),
            "movimientos": movimientos,
            "consumo_mensual": round(consumo_mensual, 2),
            "rotacion": round(valor_salida / valor, 2) if valor > 0 else None,
            "meses_stock": (round(cantidad / consumo_mensual, 1)
                            if consumo_mensual > 0 else None),
            "dias_sin_movimiento": ((ahora - ultimo).days if ultimo else None),
            # Sin salidas en el periodo y con existencia: plata quieta.
            "dormido": cant_salida == 0 and cantidad > 0,
        })

    filas.sort(key=lambda x: -(x["valor_salidas"] or 0))
    dormidos = [f for f in filas if f["dormido"]]
    return {
        "periodo_dias": dias,
        "filas": filas,
        "dormidos": len(dormidos),
        "valor_dormido": round(sum(f["valor"] for f in dormidos), 2),
        "valor_movido": round(sum(f["valor_salidas"] for f in filas), 2),
    }
