"""
La configuración: flujos, estados, transiciones, tipos, prioridades y campos.

Es la mitad que convierte el módulo en configurable de verdad. Sin estas rutas,
cambiar cómo trabaja un equipo exige entrar a la base a mano, y eso significa que
en la práctica nadie lo cambia.

Todo va detrás de `gestion.configurar`, separado de `gestion.trabajar`: cambiar
un workflow afecta a las incidencias que ya existen —una transición que
desaparece deja tarjetas sin salida— y eso no es lo mismo que mover una tarjeta.

Dos cuidados que se repiten en todo el archivo:

  · **Nada que esté en uso se borra.** Se archiva. Borrar un estado al que
    apuntan incidencias las dejaría señalando a una fila que ya no existe.
  · **Las claves de los campos se restringen a minúsculas, dígitos y guion
    bajo.** No es estética: la clave termina dentro de una expresión de índice y
    dentro del lenguaje de filtros, y ahí no puede entrar texto arbitrario.
"""
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import gestion_workflow
from app.core.database import get_db_plataforma
from app.core.permisos_consola import Miembro, exigir
from app.infrastructure.models.gestion import (
    CATEGORIAS_ESTADO, NIVELES, TIPOS_CAMPO,
    GPCampo, GPCampoOpcion, GPEsquemaCampo, GPEstado, GPIncidencia, GPPrioridad,
    GPTipoIncidencia, GPTransicion, GPWorkflow,
)

router = APIRouter(prefix="/gestion/config", tags=["Gestión"])

CLAVE_VALIDA = re.compile(r"^[a-z][a-z0-9_]{1,59}$")


# ─── Flujos ───────────────────────────────────────────────────────────────────

class WorkflowEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: Optional[str] = None
    por_defecto: bool = False


class EstadoEntrada(BaseModel):
    clave: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=60)
    categoria: str = "POR_HACER"
    color: Optional[str] = None
    orden: int = 0
    inicial: bool = False
    limite_wip: Optional[int] = None


class TransicionEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    origen_id: Optional[int] = None
    destino_id: int
    condiciones: List[Dict[str, Any]] = []
    validaciones: List[Dict[str, Any]] = []
    acciones: List[Dict[str, Any]] = []
    orden: int = 0


@router.post("/workflows", status_code=201)
async def crear_workflow(
    data: WorkflowEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Un flujo nuevo, con el juego mínimo de estados para que sirva.

    Nace con estados y no vacío a propósito: un flujo sin estado inicial no deja
    crear ni una incidencia, y quien lo estrena se encuentra con un error en vez
    de con algo que funciona.
    """
    if data.por_defecto:
        await db.execute(text(
            "UPDATE public.gp_workflow SET por_defecto = false WHERE por_defecto = true"))

    wf = GPWorkflow(nombre=data.nombre.strip(), descripcion=data.descripcion,
                    por_defecto=data.por_defecto, archivado=False)
    db.add(wf)
    await db.flush()

    for clave, nombre, categoria, color, orden, inicial in (
        ("POR_HACER", "Por hacer", "POR_HACER", "#4D4D4D", 0, True),
        ("EN_CURSO", "En curso", "EN_CURSO", "#2F6FEB", 1, False),
        ("HECHO", "Hecho", "TERMINADO", "#16A34A", 2, False),
    ):
        db.add(GPEstado(workflow_id=wf.id, clave=clave, nombre=nombre,
                        categoria=categoria, color=color, orden=orden,
                        inicial=inicial))
    await db.flush()

    estados = {
        e.clave: e.id for e in (await db.execute(select(GPEstado).where(
            GPEstado.workflow_id == wf.id))).scalars().all()
    }
    for nombre, origen, destino, acciones, orden in (
        ("Empezar", estados["POR_HACER"], estados["EN_CURSO"],
         [{"clave": "sellar_iniciado"}], 0),
        ("Terminar", estados["EN_CURSO"], estados["HECHO"],
         [{"clave": "sellar_resuelto"}], 1),
        ("Devolver", estados["EN_CURSO"], estados["POR_HACER"], [], 2),
    ):
        db.add(GPTransicion(
            workflow_id=wf.id, nombre=nombre, origen_id=origen, destino_id=destino,
            condiciones=[], validaciones=[], acciones=acciones, orden=orden))

    await db.commit()
    await db.refresh(wf)
    return {"id": wf.id, "nombre": wf.nombre}


@router.post("/workflows/{workflow_id}/estados", status_code=201)
async def crear_estado(
    workflow_id: int, data: EstadoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    if data.categoria not in CATEGORIAS_ESTADO:
        raise HTTPException(
            422, f"Categoría no válida. Son: {', '.join(CATEGORIAS_ESTADO)}. "
                 f"De ella depende si el estado cuenta como trabajo en curso o "
                 f"como terminado en las métricas.")

    wf = (await db.execute(select(GPWorkflow).where(
        GPWorkflow.id == workflow_id))).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, "Ese flujo no existe.")

    ya = (await db.execute(select(GPEstado.id).where(
        GPEstado.workflow_id == workflow_id,
        func.upper(GPEstado.clave) == data.clave.strip().upper()))).first()
    if ya:
        raise HTTPException(409, f"Ese flujo ya tiene un estado «{data.clave}».")

    if data.inicial:
        await db.execute(text(
            "UPDATE public.gp_estado SET inicial = false WHERE workflow_id = :w"),
            {"w": workflow_id})

    estado = GPEstado(
        workflow_id=workflow_id, clave=data.clave.strip().upper(),
        nombre=data.nombre.strip(), categoria=data.categoria, color=data.color,
        orden=data.orden, inicial=data.inicial, limite_wip=data.limite_wip)
    db.add(estado)
    await db.commit()
    await db.refresh(estado)
    return {"id": estado.id, "nombre": estado.nombre}


@router.put("/estados/{estado_id}")
async def editar_estado(
    estado_id: int, data: EstadoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    estado = (await db.execute(select(GPEstado).where(
        GPEstado.id == estado_id))).scalar_one_or_none()
    if estado is None:
        raise HTTPException(404, "Ese estado no existe.")
    if data.categoria not in CATEGORIAS_ESTADO:
        raise HTTPException(422, f"Categoría no válida. Son: {', '.join(CATEGORIAS_ESTADO)}.")

    if data.inicial and not estado.inicial:
        await db.execute(text(
            "UPDATE public.gp_estado SET inicial = false WHERE workflow_id = :w"),
            {"w": estado.workflow_id})

    estado.nombre = data.nombre.strip()
    estado.categoria = data.categoria
    estado.color = data.color
    estado.orden = data.orden
    estado.inicial = data.inicial
    estado.limite_wip = data.limite_wip
    await db.commit()
    return {"id": estado.id, "nombre": estado.nombre}


@router.delete("/estados/{estado_id}", status_code=204)
async def borrar_estado(
    estado_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Solo si no hay nada apuntándole. Un estado huérfano rompe la lista."""
    estado = (await db.execute(select(GPEstado).where(
        GPEstado.id == estado_id))).scalar_one_or_none()
    if estado is None:
        raise HTTPException(404, "Ese estado no existe.")

    cuantas = (await db.execute(select(func.count()).select_from(GPIncidencia)
                                .where(GPIncidencia.estado_id == estado_id))).scalar() or 0
    if cuantas:
        raise HTTPException(
            409,
            f"Hay {cuantas} incidencia(s) en «{estado.nombre}». Muévalas a otro "
            f"estado antes de borrarlo.")

    # Las transiciones que lo mencionan se van primero, y con un `flush` de por
    # medio: sin él, SQLAlchemy ordena la tanda a su manera y emite el DELETE del
    # estado antes que el de las transiciones, con lo que la llave foránea lo
    # rechaza. El error se ve como si la comprobación de arriba no sirviera.
    for t in (await db.execute(select(GPTransicion).where(or_(
            GPTransicion.origen_id == estado_id,
            GPTransicion.destino_id == estado_id)))).scalars().all():
        await db.delete(t)
    await db.flush()

    await db.delete(estado)
    await db.commit()


@router.post("/workflows/{workflow_id}/transiciones", status_code=201)
async def crear_transicion(
    workflow_id: int, data: TransicionEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Una transición, con sus reglas comprobadas contra el registro del servidor.

    Una regla cuya clave el motor no conozca BLOQUEA la transición al usarla, así
    que se rechaza acá: es mucho mejor no dejarla guardar que descubrirlo el día
    que alguien no pueda mover una tarjeta.
    """
    registro = gestion_workflow.catalogo()
    validas = {
        "condiciones": {r["clave"] for r in registro["condiciones"]},
        "validaciones": {r["clave"] for r in registro["validaciones"]},
        "acciones": {r["clave"] for r in registro["acciones"]},
    }
    for grupo, reglas in (("condiciones", data.condiciones),
                          ("validaciones", data.validaciones),
                          ("acciones", data.acciones)):
        for regla in reglas:
            clave = (regla or {}).get("clave")
            if clave not in validas[grupo]:
                raise HTTPException(
                    422,
                    f"«{clave}» no es una regla que el servidor conozca. En "
                    f"{grupo} puede usar: {', '.join(sorted(validas[grupo]))}.")

    for campo, ident in (("origen", data.origen_id), ("destino", data.destino_id)):
        if ident is None:
            continue
        hay = (await db.execute(select(GPEstado.id).where(
            GPEstado.id == ident, GPEstado.workflow_id == workflow_id))).first()
        if not hay:
            raise HTTPException(400, f"El estado de {campo} no es de este flujo.")

    t = GPTransicion(
        workflow_id=workflow_id, nombre=data.nombre.strip(),
        origen_id=data.origen_id, destino_id=data.destino_id,
        condiciones=data.condiciones, validaciones=data.validaciones,
        acciones=data.acciones, orden=data.orden)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return {"id": t.id, "nombre": t.nombre}


@router.delete("/transiciones/{transicion_id}", status_code=204)
async def borrar_transicion(
    transicion_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    t = (await db.execute(select(GPTransicion).where(
        GPTransicion.id == transicion_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Esa transición no existe.")
    await db.delete(t)
    await db.commit()


# ─── Tipos y prioridades ──────────────────────────────────────────────────────

class TipoEntrada(BaseModel):
    clave: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=60)
    icono: Optional[str] = None
    color: Optional[str] = None
    nivel: str = "NORMAL"
    workflow_id: Optional[int] = None
    proyecto_id: Optional[int] = None
    orden: int = 0


@router.post("/tipos", status_code=201)
async def crear_tipo(
    data: TipoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    if data.nivel not in NIVELES:
        raise HTTPException(422, f"Nivel no válido. Son: {', '.join(NIVELES)}.")

    tipo = GPTipoIncidencia(
        proyecto_id=data.proyecto_id, clave=data.clave.strip().upper(),
        nombre=data.nombre.strip(), icono=data.icono, color=data.color,
        nivel=data.nivel, workflow_id=data.workflow_id, orden=data.orden,
        archivado=False)
    db.add(tipo)
    await db.commit()
    await db.refresh(tipo)
    return {"id": tipo.id, "nombre": tipo.nombre}


@router.put("/tipos/{tipo_id}")
async def editar_tipo(
    tipo_id: int, data: TipoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == tipo_id))).scalar_one_or_none()
    if tipo is None:
        raise HTTPException(404, "Ese tipo no existe.")
    if data.nivel not in NIVELES:
        raise HTTPException(422, f"Nivel no válido. Son: {', '.join(NIVELES)}.")

    cuantas = (await db.execute(select(func.count()).select_from(GPIncidencia)
                                .where(GPIncidencia.tipo_id == tipo_id))).scalar() or 0
    if cuantas and data.nivel != tipo.nivel:
        raise HTTPException(
            409,
            f"«{tipo.nombre}» ya tiene {cuantas} incidencia(s). Cambiarle el nivel "
            f"dejaría jerarquías imposibles —una subtarea colgando de otra—. Cree "
            f"un tipo nuevo y mueva las que corresponda.")

    tipo.nombre = data.nombre.strip()
    tipo.icono = data.icono
    tipo.color = data.color
    tipo.nivel = data.nivel
    tipo.workflow_id = data.workflow_id
    tipo.orden = data.orden
    await db.commit()
    return {"id": tipo.id, "nombre": tipo.nombre}


@router.delete("/tipos/{tipo_id}", status_code=204)
async def archivar_tipo(
    tipo_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Se archiva, no se borra: hay incidencias que lo referencian."""
    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == tipo_id))).scalar_one_or_none()
    if tipo is None:
        raise HTTPException(404, "Ese tipo no existe.")
    tipo.archivado = True
    await db.commit()


class PrioridadEntrada(BaseModel):
    clave: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=60)
    color: Optional[str] = None
    orden: int = 0
    por_defecto: bool = False


@router.post("/prioridades", status_code=201)
async def crear_prioridad(
    data: PrioridadEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    if data.por_defecto:
        await db.execute(text(
            "UPDATE public.gp_prioridad SET por_defecto = false WHERE por_defecto = true"))
    p = GPPrioridad(clave=data.clave.strip().upper(), nombre=data.nombre.strip(),
                    color=data.color, orden=data.orden, por_defecto=data.por_defecto)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": p.id, "nombre": p.nombre}


# ─── Campos configurables ─────────────────────────────────────────────────────

class OpcionEntrada(BaseModel):
    valor: str = Field(min_length=1, max_length=120)
    etiqueta: str = Field(min_length=1, max_length=160)
    color: Optional[str] = None


class CampoEntrada(BaseModel):
    clave: str = Field(min_length=2, max_length=60)
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: Optional[str] = None
    ayuda: Optional[str] = None
    tipo: str
    validacion: Dict[str, Any] = {}
    filtrable: bool = False
    ordenable: bool = False
    opciones: List[OpcionEntrada] = []
    # A qué aplica. Vacíos = a todo.
    proyecto_id: Optional[int] = None
    tipo_id: Optional[int] = None
    obligatorio: bool = False


async def _indice_de(db: AsyncSession, clave: str, tipo: str, crear: bool) -> None:
    """Crea o borra el índice por expresión del campo, según se marque filtrable.

    Esto es lo que permite que el administrador decida qué se indexa sin escribir
    SQL, y que no paguemos un índice por cada campo que nadie filtra. El nombre y
    la clave se interpolan porque un índice no admite parámetros — por eso la
    clave se valida antes contra una expresión regular estricta.
    """
    if not CLAVE_VALIDA.match(clave):
        raise HTTPException(422, "La clave del campo no es válida.")

    nombre = f"ix_gp_inc_campo_{clave}"
    if not crear:
        await db.execute(text(f'DROP INDEX IF EXISTS public."{nombre}"'))
        return

    if tipo in ("NUMERO", "DECIMAL"):
        expresion = f"((campos ->> '{clave}')::numeric)"
    elif tipo in ("FECHA", "FECHA_HORA"):
        expresion = f"((campos ->> '{clave}')::timestamptz)"
    else:
        expresion = f"((campos ->> '{clave}'))"

    # CONCURRENTLY no: exige estar fuera de una transacción, y acá se está dentro
    # de la del endpoint. Con una tabla pequeña el bloqueo es instantáneo; el día
    # que no lo sea, esto se mueve a una tarea en segundo plano.
    await db.execute(text(
        f'CREATE INDEX IF NOT EXISTS "{nombre}" ON public.gp_incidencia {expresion}'))


@router.post("/campos", status_code=201)
async def crear_campo(
    data: CampoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Un campo nuevo, con su índice si se marca filtrable y su regla de uso.

    Se crea el `gp_esquema_campo` en el mismo paso: un campo sin fila de esquema
    existe pero no aplica a nada —sale en la configuración y en ningún
    formulario—, que es de los fallos que nadie detecta hasta que alguien
    pregunta por qué no puede llenarlo.
    """
    clave = data.clave.strip().lower()
    if not CLAVE_VALIDA.match(clave):
        raise HTTPException(
            422,
            "La clave solo admite minúsculas, dígitos y guion bajo, y empieza por "
            "letra. Es con lo que se nombra el campo en un filtro.")
    if data.tipo not in TIPOS_CAMPO:
        raise HTTPException(422, f"Tipo no válido. Son: {', '.join(TIPOS_CAMPO)}.")

    ya = (await db.execute(select(GPCampo.id).where(GPCampo.clave == clave))).first()
    if ya:
        raise HTTPException(409, f"Ya hay un campo con la clave «{clave}».")

    if data.tipo in ("LISTA", "LISTA_MULTIPLE") and not data.opciones:
        raise HTTPException(
            422, "Un campo de lista necesita al menos una opción.")

    campo = GPCampo(
        clave=clave, nombre=data.nombre.strip(), descripcion=data.descripcion,
        ayuda=data.ayuda, tipo=data.tipo, validacion=data.validacion,
        filtrable=data.filtrable, ordenable=data.ordenable,
        del_sistema=False, archivado=False)
    db.add(campo)
    await db.flush()

    for orden, o in enumerate(data.opciones):
        db.add(GPCampoOpcion(campo_id=campo.id, valor=o.valor.strip(),
                             etiqueta=o.etiqueta.strip(), color=o.color,
                             orden=orden, archivada=False))

    db.add(GPEsquemaCampo(
        proyecto_id=data.proyecto_id, tipo_id=data.tipo_id, campo_id=campo.id,
        obligatorio=data.obligatorio, solo_lectura=False, orden=0))

    if data.filtrable or data.ordenable:
        await _indice_de(db, clave, data.tipo, True)

    await db.commit()
    await db.refresh(campo)
    return {"id": campo.id, "clave": campo.clave, "nombre": campo.nombre}


class CampoCambio(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    ayuda: Optional[str] = None
    validacion: Optional[Dict[str, Any]] = None
    filtrable: Optional[bool] = None
    ordenable: Optional[bool] = None


@router.put("/campos/{campo_id}")
async def editar_campo(
    campo_id: int, data: CampoCambio,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Edita el campo. La clave y el tipo no se tocan.

    Cambiar la clave rompería los filtros guardados que la nombran y dejaría
    huérfanos los valores ya escritos en el jsonb; cambiar el tipo dejaría datos
    que ya no validan. Las dos cosas se hacen creando un campo nuevo.
    """
    campo = (await db.execute(select(GPCampo).where(
        GPCampo.id == campo_id))).scalar_one_or_none()
    if campo is None:
        raise HTTPException(404, "Ese campo no existe.")

    cambios = data.model_dump(exclude_unset=True)
    filtrable_antes = campo.filtrable or campo.ordenable

    for k, v in cambios.items():
        setattr(campo, k, v)

    filtrable_ahora = campo.filtrable or campo.ordenable
    if filtrable_ahora != filtrable_antes:
        await _indice_de(db, campo.clave, campo.tipo, filtrable_ahora)

    await db.commit()
    return {"id": campo.id, "nombre": campo.nombre, "filtrable": campo.filtrable}


@router.delete("/campos/{campo_id}", status_code=204)
async def archivar_campo(
    campo_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Se archiva y se le quita el índice; los valores escritos se quedan.

    Borrarlo de verdad implicaría reescribir el jsonb de todas las incidencias, y
    un campo archivado que se recupera trae sus datos consigo.
    """
    campo = (await db.execute(select(GPCampo).where(
        GPCampo.id == campo_id))).scalar_one_or_none()
    if campo is None:
        raise HTTPException(404, "Ese campo no existe.")
    if campo.del_sistema:
        raise HTTPException(409, "Los campos del sistema no se pueden archivar.")

    campo.archivado = True
    campo.filtrable = False
    campo.ordenable = False
    await _indice_de(db, campo.clave, campo.tipo, False)
    await db.commit()


class EsquemaEntrada(BaseModel):
    campo_id: int
    proyecto_id: Optional[int] = None
    tipo_id: Optional[int] = None
    obligatorio: bool = False
    solo_lectura: bool = False
    orden: int = 0


@router.post("/esquemas", status_code=201)
async def aplicar_campo(
    data: EsquemaEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Hace que un campo aplique a un proyecto, a un tipo, o a los dos."""
    hay = (await db.execute(select(GPCampo.id).where(
        GPCampo.id == data.campo_id))).first()
    if not hay:
        raise HTTPException(404, "Ese campo no existe.")

    ya = (await db.execute(select(GPEsquemaCampo).where(
        GPEsquemaCampo.campo_id == data.campo_id,
        GPEsquemaCampo.proyecto_id.is_(data.proyecto_id) if data.proyecto_id is None
        else GPEsquemaCampo.proyecto_id == data.proyecto_id,
        GPEsquemaCampo.tipo_id.is_(data.tipo_id) if data.tipo_id is None
        else GPEsquemaCampo.tipo_id == data.tipo_id))).scalar_one_or_none()
    if ya is not None:
        ya.obligatorio = data.obligatorio
        ya.solo_lectura = data.solo_lectura
        ya.orden = data.orden
        await db.commit()
        return {"id": ya.id}

    esquema = GPEsquemaCampo(**data.model_dump())
    db.add(esquema)
    await db.commit()
    await db.refresh(esquema)
    return {"id": esquema.id}


@router.delete("/esquemas/{esquema_id}", status_code=204)
async def quitar_campo(
    esquema_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    esquema = (await db.execute(select(GPEsquemaCampo).where(
        GPEsquemaCampo.id == esquema_id))).scalar_one_or_none()
    if esquema is None:
        raise HTTPException(404, "Esa regla no existe.")
    await db.delete(esquema)
    await db.commit()


@router.get("/esquemas")
async def listar_esquemas(
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Dónde aplica cada campo, para la pantalla de configuración."""
    r = await db.execute(select(GPEsquemaCampo).order_by(GPEsquemaCampo.orden))
    return [
        {"id": e.id, "campo_id": e.campo_id, "proyecto_id": e.proyecto_id,
         "tipo_id": e.tipo_id, "obligatorio": e.obligatorio,
         "solo_lectura": e.solo_lectura, "orden": e.orden}
        for e in r.scalars().all()
    ]
