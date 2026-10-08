"""
WMS · Maestro de productos, códigos de barras y escaneo (propio de Daily Logistics).

Un producto se crea una vez aquí y de aquí lo toman el WMS y el POS. Al crearlo:

  - Se genera su SKU automático: prefijo de la categoría + consecutivo
    (BEB-000012). Si no tiene categoría, PRD-000012.
  - Se crean sus niveles de empaque con jerarquía: la UNIDAD siempre (1
    unidad), y opcionalmente CAJA, MASTER y ESTIBA, cada uno con cuántas
    unidades base contiene.
  - Cada nivel tiene su propio código (= su SKU de nivel) y su código de barras:
    la unidad usa el SKU (o el EAN del fabricante, si se da) y los demás niveles
    el SKU con un sufijo: BEB-000012-CJ, -MS, -ES.

Al escanear (recepción, traslado, orden de salida) el código se resuelve a su
producto y nivel: una caja de 12 suma 12 unidades; una unidad suma 1.

Los niveles se guardan en `wms_producto_empaques` —la misma tabla del
cubicaje—, así que medidas, cubicaje y códigos son una sola fuente.
"""
import re
import unicodedata
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wms_inventario
from app.core import wms_operacion as op
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.wms import (
    WMSInventarioUbicacion, WMSLote, WMSProducto, WMSProductoEmpaque, WMSUbicacion,
)

router = APIRouter(prefix="/wms", tags=["WMS · Maestro de productos y códigos"])

NIVELES = ("UNIDAD", "CAJA", "MASTER", "ESTIBA")
SUFIJO = {"CAJA": "CJ", "MASTER": "MS", "ESTIBA": "ES"}
NOMBRE_NIVEL = {"UNIDAD": "Unidad", "CAJA": "Caja", "MASTER": "Caja máster", "ESTIBA": "Estiba"}


# ─── Esquemas ─────────────────────────────────────────────────────────────────

class NivelIn(BaseModel):
    nivel: Literal["CAJA", "MASTER", "ESTIBA"]
    # Unidades base que contiene este nivel (una caja de 12 → 12).
    unidades: float = Field(gt=1)
    # Código del fabricante (opcional). Si no viene, se genera desde el SKU.
    codigo_barras: Optional[str] = Field(default=None, max_length=60)


class ProductoMaestroIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    sku: Optional[str] = Field(default=None, max_length=80)   # vacío = automático
    descripcion: Optional[str] = None
    categoria: Optional[str] = Field(default=None, max_length=100)
    familia: Optional[str] = Field(default=None, max_length=100)
    unidad_medida: str = Field(default="UNIDAD", max_length=30)
    peso_kg: Optional[float] = Field(default=None, ge=0)
    requiere_lote: bool = False
    requiere_serial: bool = False
    requiere_refrigeracion: bool = False
    vida_util_dias: Optional[int] = Field(default=None, ge=0)
    tarifa_iva: float = Field(default=19, ge=0, le=100)
    depositante_id: Optional[int] = None
    # EAN/GTIN del fabricante para la unidad (opcional). Si no viene, el SKU.
    codigo_barras: Optional[str] = Field(default=None, max_length=60)
    niveles: List[NivelIn] = []
    activo: bool = True


class NivelOut(BaseModel):
    nivel: str
    nombre: str
    unidades: float
    codigo: str          # lo que lleva el código de barras
    contiene: Optional[str] = None   # "12 unidades", "4 cajas (48 unidades)"


class ProductoMaestroOut(BaseModel):
    id: int
    sku: str
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    familia: Optional[str] = None
    unidad_medida: str
    peso_kg: Optional[float] = None
    requiere_lote: bool
    requiere_serial: bool
    requiere_refrigeracion: bool
    vida_util_dias: Optional[int] = None
    tarifa_iva: float
    depositante_id: Optional[int] = None
    codigo_barras: Optional[str] = None
    activo: bool
    existencia: float = 0
    niveles: List[NivelOut] = []


class CodigoResuelto(BaseModel):
    codigo: str
    producto_id: int
    sku: str
    nombre: str
    nivel: str
    nivel_nombre: str
    unidades: float
    requiere_lote: bool
    unidad_medida: str


class LineaAsignar(BaseModel):
    producto_id: int
    cantidad: float = Field(gt=0)
    # Unidades por empaque (12 si se envían cajas de 12). Se toman empaques
    # completos de cada ubicación antes de completar con unidades sueltas.
    multiplo: float = Field(default=1, gt=0)


class AsignarIn(BaseModel):
    almacen_id: int
    lineas: List[LineaAsignar] = Field(min_length=1)


# ─── Ayudas ───────────────────────────────────────────────────────────────────

def _prefijo(categoria: Optional[str]) -> str:
    if not categoria:
        return "PRD"
    limpio = unicodedata.normalize("NFKD", categoria).encode("ascii", "ignore").decode().upper()
    letras = re.sub(r"[^A-Z]", "", limpio)
    return (letras[:3] or "PRD").ljust(3, "X")


async def _sku_nuevo(db: AsyncSession, categoria: Optional[str]) -> str:
    pre = _prefijo(categoria)
    patron = re.compile(rf"^{pre}-(\d+)$")
    existentes = (await db.execute(select(WMSProducto.sku).where(WMSProducto.sku.like(f"{pre}-%")))).scalars().all()
    mayor = max((int(m.group(1)) for s in existentes if (m := patron.match(s))), default=0)
    return f"{pre}-{mayor + 1:06d}"


def _limpio(codigo: Optional[str]) -> Optional[str]:
    c = (codigo or "").strip().upper()
    return c or None


async def _codigo_libre(db: AsyncSession, codigo: str, producto_id: Optional[int] = None) -> None:
    """Un código identifica una sola cosa: no puede repetirse entre productos ni niveles."""
    q1 = select(WMSProducto.id).where(or_(func.upper(WMSProducto.sku) == codigo,
                                          func.upper(WMSProducto.codigo_barras) == codigo))
    q2 = select(WMSProductoEmpaque.producto_id).where(func.upper(WMSProductoEmpaque.codigo_barras) == codigo)
    if producto_id:
        q1 = q1.where(WMSProducto.id != producto_id)
        q2 = q2.where(WMSProductoEmpaque.producto_id != producto_id)
    if (await db.execute(q1)).first() or (await db.execute(q2)).first():
        raise HTTPException(409, f"El código «{codigo}» ya está asignado a otro producto.")


def _contiene(nivel: str, unidades: float, por_nivel: Dict[str, float]) -> Optional[str]:
    if nivel == "UNIDAD":
        return None
    u = f"{unidades:g} unidades"
    anterior = {"MASTER": "CAJA", "ESTIBA": "MASTER"}.get(nivel)
    # Si el nivel anterior existe y divide exacto, se dice en esos términos.
    while anterior and anterior not in por_nivel:
        anterior = {"MASTER": "CAJA", "ESTIBA": "MASTER"}.get(anterior)
    if anterior and por_nivel.get(anterior) and unidades % por_nivel[anterior] == 0:
        n = unidades / por_nivel[anterior]
        nombre = {"CAJA": "cajas", "MASTER": "cajas máster"}[anterior]
        return f"{n:g} {nombre} ({u})"
    return u


async def _salida(db: AsyncSession, p: WMSProducto, existencia: Optional[float] = None) -> ProductoMaestroOut:
    emps = (await db.execute(select(WMSProductoEmpaque).where(WMSProductoEmpaque.producto_id == p.id))).scalars().all()
    por_nivel = {e.nivel: float(e.unidades) for e in emps}
    niveles = [NivelOut(nivel="UNIDAD", nombre="Unidad", unidades=1, codigo=p.codigo_barras or p.sku)]
    for e in sorted(emps, key=lambda e: NIVELES.index(e.nivel) if e.nivel in NIVELES else 9):
        if e.nivel == "UNIDAD":
            continue
        niveles.append(NivelOut(
            nivel=e.nivel, nombre=NOMBRE_NIVEL.get(e.nivel, e.nivel), unidades=float(e.unidades),
            codigo=e.codigo_barras or f"{p.sku}-{SUFIJO.get(e.nivel, e.nivel[:2])}",
            contiene=_contiene(e.nivel, float(e.unidades), por_nivel),
        ))
    if existencia is None:
        existencia = float(await wms_inventario.existencia_total(db, p.id))
    return ProductoMaestroOut(
        id=p.id, sku=p.sku, nombre=p.nombre, descripcion=p.descripcion, categoria=p.categoria, familia=p.familia,
        unidad_medida=p.unidad_medida, peso_kg=p.peso_kg, requiere_lote=bool(p.requiere_lote),
        requiere_serial=bool(p.requiere_serial), requiere_refrigeracion=bool(p.requiere_refrigeracion),
        vida_util_dias=p.vida_util_dias, tarifa_iva=float(p.tarifa_iva or 0), depositante_id=p.depositante_id,
        codigo_barras=p.codigo_barras, activo=bool(p.activo), existencia=existencia, niveles=niveles,
    )


async def _fijar_niveles(db: AsyncSession, p: WMSProducto, unidad_codigo: Optional[str], niveles: List[NivelIn]) -> None:
    claves = [n.nivel for n in niveles]
    if len(set(claves)) != len(claves):
        raise HTTPException(422, "Cada nivel de empaque va una sola vez.")
    orden = sorted(niveles, key=lambda n: NIVELES.index(n.nivel))
    previo = 1.0
    for n in orden:
        if n.unidades <= previo:
            raise HTTPException(422, f"{NOMBRE_NIVEL[n.nivel]}: debe contener más unidades que el nivel anterior.")
        previo = n.unidades

    # Unidad: el código del fabricante o el SKU. Es el que escanea el POS.
    codigo_unidad = _limpio(unidad_codigo) or p.sku
    if codigo_unidad != p.sku:
        await _codigo_libre(db, codigo_unidad, p.id)
    p.codigo_barras = codigo_unidad

    actuales = {e.nivel: e for e in (await db.execute(select(WMSProductoEmpaque).where(
        WMSProductoEmpaque.producto_id == p.id))).scalars()}
    deseados = {"UNIDAD": (1.0, codigo_unidad)}
    for n in orden:
        codigo = _limpio(n.codigo_barras) or f"{p.sku}-{SUFIJO[n.nivel]}"
        await _codigo_libre(db, codigo, p.id)
        deseados[n.nivel] = (float(n.unidades), codigo)
    codigos = [c for _, c in deseados.values()]
    if len(set(codigos)) != len(codigos):
        raise HTTPException(422, "Dos niveles del producto no pueden tener el mismo código.")

    for nivel, e in actuales.items():
        if nivel not in deseados:
            await db.delete(e)
    for nivel, (unidades, codigo) in deseados.items():
        e = actuales.get(nivel)
        if e is None:
            # Las medidas, si se toman después (cubicaje), conservan este registro.
            db.add(WMSProductoEmpaque(producto_id=p.id, nivel=nivel, unidades=unidades, codigo_barras=codigo))
        else:
            e.unidades, e.codigo_barras = unidades, codigo


# ─── Maestro de productos ─────────────────────────────────────────────────────

@router.get("/maestro/productos", response_model=List[ProductoMaestroOut])
async def listar_maestro(
    q: Optional[str] = Query(None, description="SKU, nombre o código de barras"),
    categoria: Optional[str] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(WMSProducto)
    if q:
        t = f"%{q.strip()}%"
        sub = select(WMSProductoEmpaque.producto_id).where(WMSProductoEmpaque.codigo_barras.ilike(t))
        stmt = stmt.where(or_(WMSProducto.sku.ilike(t), WMSProducto.nombre.ilike(t),
                              WMSProducto.codigo_barras.ilike(t), WMSProducto.id.in_(sub)))
    if categoria:
        stmt = stmt.where(WMSProducto.categoria == categoria)
    if activo is not None:
        stmt = stmt.where(WMSProducto.activo == activo)
    productos = (await db.execute(stmt.order_by(WMSProducto.nombre))).scalars().all()
    # Existencias en una sola consulta, no una por producto.
    totales = dict((await db.execute(
        select(WMSInventarioUbicacion.producto_id,
               func.sum(WMSInventarioUbicacion.cantidad_disponible + WMSInventarioUbicacion.cantidad_reservada
                        + WMSInventarioUbicacion.cantidad_bloqueada))
        .group_by(WMSInventarioUbicacion.producto_id))).all())
    return [await _salida(db, p, float(totales.get(p.id) or 0)) for p in productos]


@router.get("/maestro/productos/{producto_id}", response_model=ProductoMaestroOut)
async def ver_maestro(producto_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    p = await db.get(WMSProducto, producto_id)
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    return await _salida(db, p)


async def _clasificacion(db: AsyncSession, categoria: Optional[str], familia: Optional[str]):
    """Categoría y familia salen de los catálogos (Configuración del WMS ›
    Categorías / Familias): texto libre producía «Bebidas», «bebidas» y
    «BEBIDAS» como tres categorías. Devuelve los nombres tal como están en el
    catálogo."""
    from app.infrastructure.models.wms import WMSCategoriaProducto, WMSFamiliaProducto
    categoria, familia = (categoria or "").strip() or None, (familia or "").strip() or None
    if not categoria:
        if familia:
            raise HTTPException(422, "Elija primero la categoría de la familia.")
        return None, None
    cat = (await db.execute(select(WMSCategoriaProducto).where(
        func.lower(WMSCategoriaProducto.nombre) == categoria.lower(), WMSCategoriaProducto.activo.isnot(False)))).scalar()
    if not cat:
        raise HTTPException(422, f"La categoría «{categoria}» no existe. Créela en Configuración del WMS › Categorías.")
    if not familia:
        return cat.nombre, None
    fam = (await db.execute(select(WMSFamiliaProducto).where(
        func.lower(WMSFamiliaProducto.nombre) == familia.lower(), WMSFamiliaProducto.categoria_id == cat.id,
        WMSFamiliaProducto.activo.isnot(False)))).scalar()
    if not fam:
        raise HTTPException(422, f"La familia «{familia}» no existe en la categoría {cat.nombre}. Créela en Configuración del WMS › Familias.")
    return cat.nombre, fam.nombre


@router.post("/maestro/productos", response_model=ProductoMaestroOut, status_code=201)
async def crear_maestro(data: ProductoMaestroIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    data.categoria, data.familia = await _clasificacion(db, data.categoria, data.familia)
    sku = _limpio(data.sku) or await _sku_nuevo(db, data.categoria)
    await _codigo_libre(db, sku)
    p = WMSProducto(
        sku=sku, nombre=data.nombre.strip(), descripcion=data.descripcion, categoria=data.categoria,
        familia=data.familia, unidad_medida=data.unidad_medida, peso_kg=data.peso_kg,
        requiere_lote=data.requiere_lote, requiere_serial=data.requiere_serial,
        requiere_refrigeracion=data.requiere_refrigeracion, vida_util_dias=data.vida_util_dias,
        tarifa_iva=data.tarifa_iva, activo=data.activo,
        depositante_id=data.depositante_id or await op.depositante_propio(db),
    )
    db.add(p)
    await db.flush()
    await _fijar_niveles(db, p, data.codigo_barras, data.niveles)
    await db.commit()
    await db.refresh(p)
    return await _salida(db, p, 0)


@router.put("/maestro/productos/{producto_id}", response_model=ProductoMaestroOut)
async def actualizar_maestro(producto_id: int, data: ProductoMaestroIn, db: AsyncSession = Depends(get_db),
                             _=Depends(get_current_user)):
    p = await db.get(WMSProducto, producto_id)
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    # El SKU no se cambia: está impreso en etiquetas y en el historial.
    if data.depositante_id and data.depositante_id != p.depositante_id:
        if await wms_inventario.existencia_total(db, p.id) > 0:
            raise HTTPException(409, "El producto tiene existencias: no se le puede cambiar el depositante.")
        p.depositante_id = data.depositante_id
    # Solo se valida si cambió: un producto antiguo con una categoría fuera del
    # catálogo se puede seguir editando en lo demás.
    if (data.categoria or None, data.familia or None) != (p.categoria, p.familia):
        data.categoria, data.familia = await _clasificacion(db, data.categoria, data.familia)
    for campo in ("descripcion", "categoria", "familia", "unidad_medida", "peso_kg", "requiere_lote",
                  "requiere_serial", "requiere_refrigeracion", "vida_util_dias", "tarifa_iva", "activo"):
        setattr(p, campo, getattr(data, campo))
    p.nombre = data.nombre.strip()
    await _fijar_niveles(db, p, data.codigo_barras, data.niveles)
    await db.commit()
    await db.refresh(p)
    return await _salida(db, p)


# ─── Escaneo ──────────────────────────────────────────────────────────────────

async def _resolver(db: AsyncSession, codigo: str):
    """(producto, nivel, unidades) de un código, o None si no es de ningún producto."""
    c = (codigo or "").strip().upper()
    if not c:
        return None
    r = await _resolver_exacto(db, c)
    if r is None:
        # Lector configurado con teclado en inglés sobre Windows en español: el
        # guion llega como apóstrofo y el guion bajo como «?». Se prueba la
        # lectura corregida antes de darla por desconocida.
        alterno = c.replace("'", "-").replace("?", "_").replace("´", "-")
        if alterno != c:
            r = await _resolver_exacto(db, alterno)
    return r


async def _resolver_exacto(db: AsyncSession, c: str):
    e = (await db.execute(select(WMSProductoEmpaque).where(
        func.upper(WMSProductoEmpaque.codigo_barras) == c).limit(1))).scalar()
    if e:
        return await db.get(WMSProducto, e.producto_id), e.nivel, float(e.unidades)
    p = (await db.execute(select(WMSProducto).where(or_(
        func.upper(WMSProducto.codigo_barras) == c, func.upper(WMSProducto.sku) == c)).limit(1))).scalar()
    return (p, "UNIDAD", 1.0) if p else None


def _resuelto(codigo: str, p: WMSProducto, nivel: str, unidades: float) -> CodigoResuelto:
    return CodigoResuelto(codigo=codigo.strip().upper(), producto_id=p.id, sku=p.sku, nombre=p.nombre, nivel=nivel,
                          nivel_nombre=NOMBRE_NIVEL.get(nivel, nivel), unidades=unidades,
                          requiere_lote=bool(p.requiere_lote), unidad_medida=p.unidad_medida)


class AsignarCodigoIn(BaseModel):
    producto_id: int
    nivel: Literal["UNIDAD", "CAJA", "MASTER", "ESTIBA"] = "UNIDAD"


@router.post("/codigos/{codigo}/asignar", response_model=CodigoResuelto)
async def asignar_codigo(codigo: str, data: AsignarCodigoIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Registra un código leído que no existía (p. ej. el EAN del fabricante)
    como el código de un nivel de empaque de un producto existente."""
    c = _limpio(codigo)
    if not c:
        raise HTTPException(422, "Código vacío")
    p = await db.get(WMSProducto, data.producto_id)
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    await _codigo_libre(db, c, p.id)
    e = (await db.execute(select(WMSProductoEmpaque).where(
        WMSProductoEmpaque.producto_id == p.id, WMSProductoEmpaque.nivel == data.nivel))).scalar()
    if not e:
        raise HTTPException(422, f"{p.nombre} no tiene el nivel {NOMBRE_NIVEL.get(data.nivel, data.nivel)}: agréguelo en el maestro.")
    e.codigo_barras = c
    if data.nivel == "UNIDAD":
        p.codigo_barras = c
    await db.commit()
    return _resuelto(c, p, data.nivel, float(e.unidades))


@router.get("/codigos/{codigo}", response_model=CodigoResuelto)
async def resolver_codigo(codigo: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Qué es un código escaneado: producto, nivel y cuántas unidades representa."""
    r = await _resolver(db, codigo)
    if not r:
        raise HTTPException(404, f"El código «{codigo}» no corresponde a ningún producto.")
    p, nivel, unidades = r
    if not p.activo:
        raise HTTPException(409, f"{p.nombre} está inactivo.")
    return _resuelto(codigo, p, nivel, unidades)


# ─── RFID ─────────────────────────────────────────────────────────────────────
#
# Una etiqueta RFID de producto lleva normalmente un EPC SGTIN-96 (GS1): el GTIN
# del producto (o de su caja) más un serial único por etiqueta. El serial es lo
# que permite contar sin repetir: el lector lee la misma etiqueta muchas veces
# por segundo, y cada etiqueta debe sumar una sola vez.

# partición → (bits del prefijo de empresa, dígitos, bits de la referencia, dígitos)
_PARTICION = {0: (40, 12, 4, 1), 1: (37, 11, 7, 2), 2: (34, 10, 10, 3), 3: (30, 9, 14, 4),
              4: (27, 8, 17, 5), 5: (24, 7, 20, 6), 6: (20, 6, 24, 7)}


def _digito_control(trece: str) -> str:
    suma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(trece)))
    return str((10 - suma % 10) % 10)


def sgtin96_a_gtin(epc: str) -> Optional[str]:
    """GTIN-14 de un EPC SGTIN-96 en hexadecimal (24 caracteres), o None si no lo es."""
    h = epc.strip().upper()
    if len(h) != 24 or not re.fullmatch(r"[0-9A-F]{24}", h) or not h.startswith("30"):
        return None
    bits = bin(int(h, 16))[2:].zfill(96)
    particion = int(bits[11:14], 2)
    if particion not in _PARTICION:
        return None
    cb, cd, rb, rd = _PARTICION[particion]
    empresa = str(int(bits[14:14 + cb], 2)).zfill(cd)
    referencia = str(int(bits[14 + cb:14 + cb + rb], 2)).zfill(rd)
    trece = referencia[0] + empresa + referencia[1:]
    return trece + _digito_control(trece)


class LecturasRFID(BaseModel):
    lecturas: List[str] = Field(min_length=1, max_length=5000)


@router.post("/rfid/resolver")
async def resolver_rfid(data: LecturasRFID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Convierte lecturas RFID en productos. Cada EPC distinto cuenta una vez.

    Acepta EPC SGTIN-96 (se busca el producto por su GTIN/EAN) y etiquetas grabadas
    con el código del producto o de su empaque (SKU, BEB-000012-CJ, EAN…)."""
    resueltos, desconocidos, vistos = [], [], set()
    for crudo in data.lecturas:
        epc = re.sub(r"\s+", "", crudo or "").upper()
        if not epc or epc in vistos:
            continue
        vistos.add(epc)
        codigo = epc
        r = await _resolver(db, epc)
        if not r and (gtin := sgtin96_a_gtin(epc)):
            # El GTIN-14 de una unidad es su EAN-13 con un 0 adelante.
            for candidato in (gtin, gtin[1:] if gtin.startswith("0") else None, gtin.lstrip("0")):
                if candidato and (r := await _resolver(db, candidato)):
                    codigo = candidato
                    break
        if r and r[0].activo:
            p, nivel, unidades = r
            # `codigo` es el del producto o su empaque (lo que valida el picking);
            # `epc` es la etiqueta leída.
            resueltos.append({"epc": epc, **_resuelto(codigo, p, nivel, unidades).model_dump()})
        else:
            desconocidos.append(epc)
    return {"resueltos": resueltos, "desconocidos": desconocidos}


async def _repartir(db: AsyncSession, producto_id: int, almacen_id: int, cantidad: float, multiplo: float):
    """Empaques completos primero (ver `wms_inventario.asignar_por_empaque`)."""
    return await wms_inventario.asignar_por_empaque(db, producto_id, almacen_id, cantidad, multiplo=multiplo or 1)


@router.post("/escaneo/asignar-origen")
async def asignar_origen(data: AsignarIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """De dónde sale lo escaneado para un traslado: reparte cada producto entre las
    ubicaciones con existencias del almacén, primero lo que vence primero (FEFO).
    No reserva nada: solo sugiere. Lo que no alcanza se informa como faltante."""
    lineas, faltantes = [], []
    for ln in data.lineas:
        asignado = 0.0
        for a in await _repartir(db, ln.producto_id, data.almacen_id, ln.cantidad, ln.multiplo):
            ub = await db.get(WMSUbicacion, a.ubicacion_id)
            lote = await db.get(WMSLote, a.lote_id) if a.lote_id else None
            inv = (await db.execute(select(WMSInventarioUbicacion.id).where(
                WMSInventarioUbicacion.producto_id == ln.producto_id,
                WMSInventarioUbicacion.ubicacion_id == a.ubicacion_id,
                WMSInventarioUbicacion.lote_id.is_(None) if a.lote_id is None else WMSInventarioUbicacion.lote_id == a.lote_id,
                WMSInventarioUbicacion.contenedor_id.is_(None) if a.contenedor_id is None
                else WMSInventarioUbicacion.contenedor_id == a.contenedor_id,
            ).limit(1))).scalar()
            lineas.append({
                "inventario_id": inv, "producto_id": ln.producto_id, "ubicacion_id": a.ubicacion_id,
                "ubicacion": ub.codigo if ub else None, "lote_id": a.lote_id,
                "lote": lote.numero_lote if lote else None, "contenedor_id": a.contenedor_id,
                "cantidad": float(a.cantidad),
            })
            asignado += float(a.cantidad)
        if asignado + 1e-9 < ln.cantidad:
            p = await db.get(WMSProducto, ln.producto_id)
            faltantes.append({"producto_id": ln.producto_id, "sku": p.sku if p else None,
                              "nombre": p.nombre if p else None, "solicitado": ln.cantidad, "disponible": asignado})
    # Solo se consultó: se sueltan los bloqueos de lectura de la asignación.
    await db.rollback()
    return {"lineas": lineas, "faltantes": faltantes}
