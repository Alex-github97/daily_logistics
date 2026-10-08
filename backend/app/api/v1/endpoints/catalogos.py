"""Catálogo maestro: un solo CRUD para los catálogos de todos los módulos.

Reemplaza la necesidad de escribir una tabla, un CRUD y una pantalla por cada
lista controlada. Los módulos que ya tienen catálogos con atributos propios
(neumáticos, vehículos del CMMS) se quedan como están: ahí cada valor carga
datos del negocio que una tabla genérica no puede guardar.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

from app.core.database import get_db
from app.infrastructure.models.catalogo import (
    CatalogoMaestro, CATALOGOS_REGISTRO, MODULO_GLOBAL,
    catalogos_de, buscar_registro, MODULOS_CON_CATALOGO,
)

router = APIRouter(prefix="/catalogos", tags=["catalogos"])


# ──────────────────────────────────────────
# SCHEMAS
# ──────────────────────────────────────────

class RegistroCatalogo(BaseModel):
    modulo: str
    tipo: str
    label: str
    descripcion: str
    padre: Optional[str] = None
    total: int = 0


class ValorCatalogoBase(BaseModel):
    modulo: str
    tipo: str
    nombre: str
    codigo: Optional[str] = None
    padre_id: Optional[int] = None
    orden: Optional[int] = 0
    color: Optional[str] = None
    metadatos: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = True


class ValorCatalogoResponse(ValorCatalogoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    padre_nombre: Optional[str] = None
    total_hijos: int = 0


class ValorCatalogoUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    padre_id: Optional[int] = None
    orden: Optional[int] = None
    color: Optional[str] = None
    metadatos: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = None


# ──────────────────────────────────────────
# METADATOS DEL REGISTRO
# ──────────────────────────────────────────

@router.get("/registro", response_model=List[RegistroCatalogo])
async def listar_registro(
    modulo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Qué catálogos existen, cómo se llaman y de quién dependen.

    La interfaz se arma desde acá: agregar un catálogo nuevo a un módulo es una
    línea en el registro y no una pantalla nueva.
    """
    entradas = catalogos_de(modulo.upper()) if modulo else list(CATALOGOS_REGISTRO)

    r = await db.execute(
        select(CatalogoMaestro.modulo, CatalogoMaestro.tipo, func.count())
        .group_by(CatalogoMaestro.modulo, CatalogoMaestro.tipo)
    )
    conteo = {(m, t): n for m, t, n in r.all()}

    return [RegistroCatalogo(
        modulo=c["modulo"], tipo=c["tipo"], label=c["label"],
        descripcion=c["descripcion"], padre=c["padre"],
        total=conteo.get((c["modulo"], c["tipo"]), 0),
    ) for c in entradas]


@router.get("/modulos", response_model=List[str])
async def listar_modulos():
    return MODULOS_CON_CATALOGO


# ──────────────────────────────────────────
# VALORES
# ──────────────────────────────────────────

@router.get("", response_model=List[ValorCatalogoResponse])
async def listar_valores(
    modulo: str,
    tipo: str,
    padre_id: Optional[int] = None,
    solo_activos: bool = False,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Valores de un catálogo. `padre_id` acota al nivel de arriba: las ciudades
    de un departamento, las áreas de una sede."""
    modulo, tipo = modulo.upper(), tipo.upper()
    if buscar_registro(modulo, tipo) is None:
        raise HTTPException(404, "El catálogo %s/%s no está declarado en el registro."
                                 % (modulo, tipo))

    cons = select(CatalogoMaestro).where(
        CatalogoMaestro.modulo == modulo, CatalogoMaestro.tipo == tipo)
    if padre_id is not None:
        cons = cons.where(CatalogoMaestro.padre_id == padre_id)
    if solo_activos:
        cons = cons.where(CatalogoMaestro.activo == True)
    if q:
        patron = "%%%s%%" % q.strip().lower()
        cons = cons.where(or_(func.lower(CatalogoMaestro.nombre).like(patron),
                              func.lower(CatalogoMaestro.codigo).like(patron)))
    r = await db.execute(cons.order_by(CatalogoMaestro.orden, CatalogoMaestro.nombre))
    valores = r.scalars().all()
    if not valores:
        return []

    # Nombre del padre y cuántos hijos tiene cada valor, en dos consultas
    padres_ids = {v.padre_id for v in valores if v.padre_id}
    padres = {}
    if padres_ids:
        rp = await db.execute(select(CatalogoMaestro).where(CatalogoMaestro.id.in_(padres_ids)))
        padres = {p.id: p.nombre for p in rp.scalars().all()}

    rh = await db.execute(
        select(CatalogoMaestro.padre_id, func.count())
        .where(CatalogoMaestro.padre_id.in_([v.id for v in valores]))
        .group_by(CatalogoMaestro.padre_id)
    )
    hijos = {pid: n for pid, n in rh.all()}

    salida = []
    for v in valores:
        item = ValorCatalogoResponse.model_validate(v)
        item.padre_nombre = padres.get(v.padre_id) if v.padre_id else None
        item.total_hijos = hijos.get(v.id, 0)
        salida.append(item)
    return salida


@router.post("", response_model=ValorCatalogoResponse, status_code=201)
async def crear_valor(data: ValorCatalogoBase, db: AsyncSession = Depends(get_db)):
    modulo, tipo = data.modulo.upper(), data.tipo.upper()
    registro = buscar_registro(modulo, tipo)
    if registro is None:
        raise HTTPException(404, "El catálogo %s/%s no está declarado en el registro."
                                 % (modulo, tipo))
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio.")

    # Coherencia de la jerarquía: si el catálogo declara padre, el padre es
    # obligatorio y tiene que ser del tipo correcto. Sin esto se podría colgar
    # una ciudad de un cargo.
    if registro["padre"]:
        if data.padre_id is None:
            raise HTTPException(400, "Este catálogo depende de %s: indique el valor padre."
                                     % registro["padre"])
        padre = await db.get(CatalogoMaestro, data.padre_id)
        if padre is None:
            raise HTTPException(404, "El valor padre indicado no existe.")
        if padre.tipo != registro["padre"]:
            raise HTTPException(400, "El padre debe ser de tipo %s, no %s."
                                     % (registro["padre"], padre.tipo))
    elif data.padre_id is not None:
        raise HTTPException(400, "Este catálogo es plano y no admite valor padre.")

    r = await db.execute(select(CatalogoMaestro).where(
        CatalogoMaestro.modulo == modulo,
        CatalogoMaestro.tipo == tipo,
        func.lower(CatalogoMaestro.nombre) == nombre.lower(),
        CatalogoMaestro.padre_id == data.padre_id,
    ))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "'%s' ya existe en ese catálogo." % nombre)

    obj = CatalogoMaestro(
        modulo=modulo, tipo=tipo, nombre=nombre, codigo=data.codigo or None,
        padre_id=data.padre_id, orden=data.orden or 0, color=data.color,
        metadatos=data.metadatos,
        activo=data.activo if data.activo is not None else True,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ValorCatalogoResponse.model_validate(obj)


@router.put("/{vid}", response_model=ValorCatalogoResponse)
async def actualizar_valor(vid: int, data: ValorCatalogoUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(CatalogoMaestro, vid)
    if obj is None:
        raise HTTPException(404, "Valor no encontrado")
    valores = data.model_dump(exclude_unset=True)

    if "padre_id" in valores and valores["padre_id"] is not None:
        if valores["padre_id"] == vid:
            raise HTTPException(400, "Un valor no puede ser su propio padre.")
        padre = await db.get(CatalogoMaestro, valores["padre_id"])
        if padre is None:
            raise HTTPException(404, "El valor padre indicado no existe.")
        # Evitar ciclos: subir por la cadena del nuevo padre buscándose a sí mismo
        cursor, saltos = padre, 0
        while cursor is not None and saltos < 20:
            if cursor.id == vid:
                raise HTTPException(400, "Ese padre haría un ciclo en la jerarquía.")
            cursor = await db.get(CatalogoMaestro, cursor.padre_id) if cursor.padre_id else None
            saltos += 1

    for k, v in valores.items():
        setattr(obj, k, v.strip() if isinstance(v, str) else v)
    await db.commit()
    await db.refresh(obj)
    return ValorCatalogoResponse.model_validate(obj)


@router.delete("/{vid}", status_code=204)
async def eliminar_valor(vid: int, db: AsyncSession = Depends(get_db)):
    """Borra el valor. Si tiene hijos se desactiva: borrarlo se llevaría por
    cascada toda la rama, que casi nunca es lo que se quiere."""
    obj = await db.get(CatalogoMaestro, vid)
    if obj is None:
        raise HTTPException(404, "Valor no encontrado")
    r = await db.execute(select(func.count()).select_from(CatalogoMaestro).where(
        CatalogoMaestro.padre_id == vid))
    if (r.scalar() or 0) > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj)
    await db.commit()


class ArbolNodo(BaseModel):
    id: int
    nombre: str
    codigo: Optional[str] = None
    tipo: str
    activo: bool = True
    hijos: List["ArbolNodo"] = []


@router.get("/arbol", response_model=List[ArbolNodo])
async def arbol_catalogo(
    modulo: str, tipo: str, solo_activos: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Devuelve la rama completa a partir de un tipo raíz, ya anidada.

    Sirve para pintar la jerarquía de un golpe (país → departamento → ciudad)
    sin que la interfaz tenga que pedir un nivel por vez.
    """
    modulo, tipo = modulo.upper(), tipo.upper()
    if buscar_registro(modulo, tipo) is None:
        raise HTTPException(404, "El catálogo %s/%s no está declarado." % (modulo, tipo))

    cons = select(CatalogoMaestro).where(CatalogoMaestro.modulo == modulo)
    if solo_activos:
        cons = cons.where(CatalogoMaestro.activo == True)
    r = await db.execute(cons.order_by(CatalogoMaestro.orden, CatalogoMaestro.nombre))
    todos = r.scalars().all()

    por_padre: Dict[Optional[int], List[CatalogoMaestro]] = {}
    for v in todos:
        por_padre.setdefault(v.padre_id, []).append(v)

    def armar(v: CatalogoMaestro) -> ArbolNodo:
        return ArbolNodo(
            id=v.id, nombre=v.nombre, codigo=v.codigo, tipo=v.tipo,
            activo=bool(v.activo),
            hijos=[armar(h) for h in por_padre.get(v.id, [])],
        )

    return [armar(v) for v in todos if v.tipo == tipo]


# ──────────────────────────────────────────
# VALIDACIÓN REUTILIZABLE POR LOS MÓDULOS
# ──────────────────────────────────────────

async def resolver_valor_catalogo(
    db: AsyncSession, modulo: str, tipo: str, nombre: Optional[str],
    obligatorio: bool = False, etiqueta: Optional[str] = None,
) -> Optional[str]:
    """Valida que un texto exista en el catálogo y lo devuelve normalizado.

    Es la pieza que hace que la estandarización sea real y no solo visual: que
    la pantalla muestre una lista no impide que por API llegue texto libre.
    Cualquier endpoint de cualquier módulo la puede llamar antes de guardar.

    Devuelve el nombre con la grafía del catálogo, o None si venía vacío y no
    es obligatorio. Lanza ValueError con un mensaje entendible si no existe.
    """
    campo = etiqueta or tipo.replace("_", " ").lower()
    texto = (nombre or "").strip()
    if not texto:
        if obligatorio:
            raise ValueError("El campo %s es obligatorio." % campo)
        return None

    r = await db.execute(select(CatalogoMaestro).where(
        CatalogoMaestro.modulo == modulo.upper(),
        CatalogoMaestro.tipo == tipo.upper(),
        func.lower(CatalogoMaestro.nombre) == texto.lower(),
    ))
    valor = r.scalar_one_or_none()
    if valor is None:
        raise ValueError("'%s' no está en el catálogo de %s. Agréguelo en la "
                         "configuración antes de usarlo." % (texto, campo))
    if not valor.activo:
        raise ValueError("'%s' está desactivado en el catálogo de %s." % (texto, campo))
    return valor.nombre


# ── Cargue masivo desde Excel ─────────────────────────────────────────────────
#
# El archivo se lee en el navegador y acá llegan filas ya estructuradas: así no
# hay que subir archivos ni manejar temporales, y este lado se dedica a validar.
#
# No se detiene en el primer error: un archivo de trescientas filas con dos
# malas carga las 298 buenas y dice qué pasó con las otras dos. Y es idempotente
# —lo repetido se omite— para que volver a subir el archivo corregido no deje el
# catálogo duplicado.

MAX_FILAS_IMPORTACION = 5000


class FilaConError(BaseModel):
    # Número de fila tal como lo ve el usuario en Excel: la 1 es el encabezado.
    fila: int
    motivo: str


class ResultadoImportacion(BaseModel):
    creados: int = 0
    omitidos: int = 0
    errores: List[FilaConError] = []
    total: int = 0


class CargueCatalogo(BaseModel):
    modulo: str
    tipo: str
    filas: List[dict]


@router.post("/importar", response_model=ResultadoImportacion)
async def importar_valores(cargue: CargueCatalogo, db: AsyncSession = Depends(get_db)):
    """Carga valores de un catálogo desde una lista de filas.

    En los catálogos con jerarquía el padre viene por **nombre** y no por id:
    quien llena un Excel escribe "Antioquia", no el número 4173.
    """
    modulo, tipo = cargue.modulo.upper(), cargue.tipo.upper()
    registro = buscar_registro(modulo, tipo)
    if registro is None:
        raise HTTPException(404, "El catálogo %s/%s no está declarado en el registro."
                                 % (modulo, tipo))
    if len(cargue.filas) > MAX_FILAS_IMPORTACION:
        raise HTTPException(
            400,
            "El archivo trae %d filas y el máximo son %d. Divídalo en varios archivos."
            % (len(cargue.filas), MAX_FILAS_IMPORTACION),
        )

    tipo_padre = registro["padre"]

    # Los posibles padres, indexados por nombre en minúsculas. Se resuelven de
    # una vez y no fila por fila, que serían cientos de consultas.
    padres: dict = {}
    if tipo_padre:
        r = await db.execute(select(CatalogoMaestro).where(
            CatalogoMaestro.modulo.in_([modulo, MODULO_GLOBAL]),
            CatalogoMaestro.tipo == tipo_padre,
        ))
        for p in r.scalars().all():
            padres[p.nombre.strip().lower()] = p.id

    # Lo que ya existe, por (padre, nombre): el mismo nombre puede repetirse
    # bajo padres distintos —"Norte" en dos sedes— y eso es válido.
    r = await db.execute(select(CatalogoMaestro).where(
        CatalogoMaestro.modulo == modulo, CatalogoMaestro.tipo == tipo))
    existentes = {(v.padre_id, v.nombre.strip().lower()) for v in r.scalars().all()}

    resultado = ResultadoImportacion(total=len(cargue.filas))
    nuevos = []

    for i, fila in enumerate(cargue.filas):
        numero = i + 2
        nombre = str(fila.get("nombre") or "").strip()
        if not nombre:
            resultado.errores.append(FilaConError(fila=numero, motivo="Falta el nombre"))
            continue

        padre_id = None
        if tipo_padre:
            nombre_padre = str(fila.get("padre") or "").strip()
            if not nombre_padre:
                resultado.errores.append(FilaConError(
                    fila=numero,
                    motivo="Falta el padre: este catálogo depende de %s" % tipo_padre))
                continue
            padre_id = padres.get(nombre_padre.lower())
            if padre_id is None:
                resultado.errores.append(FilaConError(
                    fila=numero,
                    motivo="No existe «%s» en %s. Cárguelo primero." % (nombre_padre, tipo_padre)))
                continue

        if (padre_id, nombre.lower()) in existentes:
            resultado.omitidos += 1
            continue

        codigo = str(fila.get("codigo") or "").strip() or None
        # Dos filas iguales en el mismo archivo: la segunda se omite.
        existentes.add((padre_id, nombre.lower()))
        nuevos.append(CatalogoMaestro(
            modulo=modulo, tipo=tipo, nombre=nombre, codigo=codigo,
            padre_id=padre_id, orden=0, activo=True))

    if nuevos:
        db.add_all(nuevos)
        await db.commit()
        resultado.creados = len(nuevos)

    return resultado
