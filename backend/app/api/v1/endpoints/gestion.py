"""
Proyectos y configuración del módulo de gestión.

Todo va detrás de los permisos de la consola, y encima de eso el proyecto se
comprueba objeto por objeto: tener `gestion.ver` no alcanza para entrar a un
proyecto restringido del que no se es miembro.

`gestion.configurar` está separado de `gestion.trabajar` a propósito. Cambiar un
workflow afecta a las incidencias que ya existen —una transición que desaparece
deja tarjetas sin salida— y eso no es lo mismo que mover una tarjeta.
"""
import re
import unicodedata
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import gestion_campos, gestion_workflow
from app.core.database import get_db_plataforma
from app.core.gestion_permisos import (
    exigir_proyecto, limitar, proyectos_visibles, roles_en,
)
from app.core.permisos_consola import Miembro, exigir
from app.infrastructure.models.plataforma import PlataformaMiembro
from app.infrastructure.models.gestion import (
    GPCampo, GPCampoOpcion, GPEstado, GPIncidencia, GPPrioridad, GPProyecto,
    GPProyectoMiembro, GPTipoIncidencia, GPTransicion, GPWorkflow,
    NIVELES, ROLES_PROYECTO, TIPOS_CAMPO, CATEGORIAS_ESTADO,
)

router = APIRouter(prefix="/gestion", tags=["Gestión"])


# ─── Lo que se devuelve ───────────────────────────────────────────────────────

class ProyectoResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clave: str
    nombre: str
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    lider: Optional[str] = None
    workflow_id: Optional[int] = None
    restringido: bool = False
    incidencia_automatica: bool = True
    archivado: bool = False
    # Se calculan; no salen de la tabla.
    abiertas: int = 0
    total: int = 0
    mi_rol: Optional[str] = None


class MiembroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usuario: str
    rol: str


class ProyectoEntrada(BaseModel):
    # La clave se puede omitir: se deduce del nombre. Escribirla a mano es un
    # trámite que solo existía porque alguien tenía que garantizar que fuera
    # única, y eso lo hace mejor el servidor.
    clave: Optional[str] = Field(default=None, max_length=12)
    nombre: str = Field(min_length=2, max_length=160)
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    lider: Optional[str] = None
    workflow_id: Optional[int] = None
    restringido: bool = False
    incidencia_automatica: bool = True


class ProyectoCambio(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    lider: Optional[str] = None
    workflow_id: Optional[int] = None
    restringido: Optional[bool] = None
    incidencia_automatica: Optional[bool] = None
    archivado: Optional[bool] = None


class MiembroEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=80)
    rol: str = "MIEMBRO"


# ─── Proyectos ────────────────────────────────────────────────────────────────

@router.get("/proyectos", response_model=List[ProyectoResumen])
async def listar_proyectos(
    incluir_archivados: bool = False,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Los proyectos que esta persona puede ver, con cuánto tienen abierto.

    Las cuentas salen de una sola consulta agrupada y no de una por proyecto: con
    muchos proyectos, la segunda forma es la que convierte una pantalla de inicio
    en una espera.
    """
    visibles = await proyectos_visibles(db, quien)

    consulta = select(GPProyecto)
    if not incluir_archivados:
        consulta = consulta.where(GPProyecto.archivado.is_(False))
    consulta = limitar(consulta, visibles, GPProyecto.id)
    proyectos = list((await db.execute(
        consulta.order_by(GPProyecto.archivado, GPProyecto.nombre))).scalars().all())
    if not proyectos:
        return []

    ids = [p.id for p in proyectos]
    r = await db.execute(
        select(GPIncidencia.proyecto_id, GPEstado.categoria, func.count())
        .join(GPEstado, GPEstado.id == GPIncidencia.estado_id)
        .where(GPIncidencia.proyecto_id.in_(ids))
        .group_by(GPIncidencia.proyecto_id, GPEstado.categoria))
    abiertas: Dict[int, int] = {}
    totales: Dict[int, int] = {}
    for pid, categoria, cuantas in r.all():
        totales[pid] = totales.get(pid, 0) + cuantas
        if categoria != "TERMINADO":
            abiertas[pid] = abiertas.get(pid, 0) + cuantas

    mis_roles = await roles_en(db, quien.usuario, ids)

    salida = []
    for p in proyectos:
        ficha = ProyectoResumen.model_validate(p)
        ficha.abiertas = abiertas.get(p.id, 0)
        ficha.total = totales.get(p.id, 0)
        ficha.mi_rol = mis_roles.get(p.id)
        salida.append(ficha)
    return salida


async def _clave_sugerida(db: AsyncSession, nombre: str) -> str:
    """Propone una clave a partir del nombre, y se asegura de que sea única.

    «Desarrollos» → DES. «Soporte y mantenimiento» → SYM, tomando la inicial de
    cada palabra cuando hay varias: es lo que una persona escribiría.

    Si ya existe, agrega un número: DES, DES2, DES3… No se usa un aleatorio
    porque la clave se lee todo el día en los códigos de las incidencias, y
    «DES-14» se recuerda y se dicta por teléfono; «X7K-14» no.
    """
    # Primero se quitan las tildes, DESPUÉS lo que no es letra. Al revés, la
    # normalización separa «ó» en «o» + tilde, la tilde se cambia por un espacio
    # y «Migración» queda partida en «Migracio» y «n»: la clave salía MNC en vez
    # de MC.
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", nombre)
        if not unicodedata.combining(c))
    limpio = re.sub(r"[^A-Za-z0-9 ]", " ", sin_tildes)
    palabras = [p for p in limpio.split() if p]

    if not palabras:
        base = "PRY"
    elif len(palabras) == 1:
        base = palabras[0][:3].upper()
    else:
        # La inicial de cada palabra, hasta cuatro. Las palabras de enlace se
        # descartan: «Soporte y mantenimiento» da SM, no SYM.
        enlaces = {"y", "de", "del", "la", "el", "los", "las", "para", "en", "a"}
        utiles = [p for p in palabras if p.lower() not in enlaces] or palabras
        base = "".join(p[0] for p in utiles[:4]).upper()

    base = (base or "PRY")[:8]
    usadas = {c for (c,) in (await db.execute(select(GPProyecto.clave))).all()}
    if base not in usadas:
        return base
    for n in range(2, 100):
        candidata = f"{base}{n}"
        if candidata not in usadas:
            return candidata
    return f"PRY{len(usadas) + 1}"


@router.get("/proyectos/clave-sugerida")
async def clave_sugerida(
    nombre: str,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """La clave que se usaría para ese nombre.

    La pantalla la muestra mientras se escribe el nombre, para que quien crea el
    proyecto vea cómo van a quedar los códigos de sus incidencias antes de
    confirmar. Sigue pudiendo cambiarla.
    """
    return {"clave": await _clave_sugerida(db, nombre)}


@router.post("/proyectos", response_model=ProyectoResumen, status_code=201)
async def crear_proyecto(
    data: ProyectoEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    clave = (data.clave or "").strip().upper()
    if not clave:
        clave = await _clave_sugerida(db, data.nombre)
    if not clave.isalnum():
        raise HTTPException(
            422,
            "La clave del proyecto solo admite letras y números: es el prefijo "
            "de las claves visibles (ERP-123).")

    existe = (await db.execute(select(GPProyecto.id).where(
        GPProyecto.clave == clave))).first()
    if existe:
        raise HTTPException(409, f"Ya hay un proyecto con la clave «{clave}».")

    if data.workflow_id is not None:
        hay = (await db.execute(select(GPWorkflow.id).where(
            GPWorkflow.id == data.workflow_id))).first()
        if not hay:
            raise HTTPException(404, "Ese flujo no existe.")

    proyecto = GPProyecto(
        clave=clave, nombre=data.nombre.strip(), descripcion=data.descripcion,
        icono=data.icono, color=data.color, lider=data.lider or quien.usuario,
        workflow_id=data.workflow_id, contador=0,
        restringido=data.restringido,
        incidencia_automatica=data.incidencia_automatica,
        archivado=False,
    )
    db.add(proyecto)
    await db.flush()

    # Quien lo crea queda de líder dentro del proyecto. Sin esto, un proyecto
    # restringido nacería sin nadie que pueda entrar, ni siquiera su autor.
    db.add(GPProyectoMiembro(
        proyecto_id=proyecto.id, usuario=proyecto.lider or quien.usuario,
        rol="LIDER"))
    await db.commit()
    await db.refresh(proyecto)
    return ProyectoResumen.model_validate(proyecto)


@router.get("/proyectos/{proyecto_id}", response_model=ProyectoResumen)
async def ver_proyecto(
    proyecto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    proyecto = await exigir_proyecto(db, quien, proyecto_id)
    ficha = ProyectoResumen.model_validate(proyecto)
    ficha.total = (await db.execute(select(func.count()).select_from(GPIncidencia)
                                    .where(GPIncidencia.proyecto_id == proyecto_id))).scalar() or 0
    ficha.abiertas = (await db.execute(
        select(func.count()).select_from(GPIncidencia)
        .join(GPEstado, GPEstado.id == GPIncidencia.estado_id)
        .where(GPIncidencia.proyecto_id == proyecto_id,
               GPEstado.categoria != "TERMINADO"))).scalar() or 0
    ficha.mi_rol = (await roles_en(db, quien.usuario, [proyecto_id])).get(proyecto_id)
    return ficha


@router.put("/proyectos/{proyecto_id}", response_model=ProyectoResumen)
async def editar_proyecto(
    proyecto_id: int, data: ProyectoCambio,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    proyecto = await exigir_proyecto(db, quien, proyecto_id)
    cambios = data.model_dump(exclude_unset=True)

    if cambios.get("restringido") and not cambios.get("archivado"):
        # Al restringir, quien queda fuera pierde el acceso de inmediato. Se
        # comprueba que haya al menos un miembro o el proyecto queda inalcanzable
        # para todos, incluido quien lo restringió.
        hay = (await db.execute(select(func.count()).select_from(GPProyectoMiembro)
                                .where(GPProyectoMiembro.proyecto_id == proyecto_id))).scalar() or 0
        if hay == 0:
            raise HTTPException(
                409,
                "Antes de restringirlo, agregue al menos un miembro: si no, "
                "nadie podría volver a entrar.")

    for campo, valor in cambios.items():
        setattr(proyecto, campo, valor)
    await db.commit()
    await db.refresh(proyecto)
    return ProyectoResumen.model_validate(proyecto)


@router.get("/proyectos/{proyecto_id}/miembros", response_model=List[MiembroResponse])
async def listar_miembros(
    proyecto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    await exigir_proyecto(db, quien, proyecto_id)
    r = await db.execute(select(GPProyectoMiembro).where(
        GPProyectoMiembro.proyecto_id == proyecto_id
    ).order_by(GPProyectoMiembro.rol, GPProyectoMiembro.usuario))
    return list(r.scalars().all())


@router.delete("/proyectos/{proyecto_id}", status_code=204)
async def eliminar_proyecto(
    proyecto_id: int,
    forzar: bool = Query(
        False, description="Elimina aunque tenga incidencias. Se pierden."),
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    """Elimina un proyecto.

    Un proyecto vacío se borra sin más: normalmente es uno recién creado con un
    nombre equivocado, y obligar a archivarlo deja basura en el selector para
    siempre.

    Uno CON incidencias no se borra por accidente: hay que pedirlo
    explícitamente con `forzar`. La razón es que las incidencias son el registro
    del trabajo —comentarios, adjuntos, historial— y eso no se recupera. La
    alternativa para conservar el historial es archivarlo, y el mensaje lo dice.
    """
    proyecto = (await db.execute(select(GPProyecto).where(
        GPProyecto.id == proyecto_id))).scalar_one_or_none()
    if proyecto is None:
        raise HTTPException(404, "Ese proyecto no existe.")

    cuantas = (await db.execute(
        select(func.count()).select_from(GPIncidencia)
        .where(GPIncidencia.proyecto_id == proyecto_id))).scalar() or 0

    if cuantas and not forzar:
        raise HTTPException(
            409,
            f"«{proyecto.nombre}» tiene {cuantas} incidencia(s) con su "
            f"historial y sus adjuntos. Si de verdad quiere perderlas, "
            f"confirme la eliminación; si solo quiere quitarlo de la vista, "
            f"archívelo y se conserva todo.")

    # Las incidencias se borran en cascada por la relación; los miembros se
    # quitan a mano porque cuelgan del proyecto y no de la incidencia.
    await db.execute(sa_delete(GPProyectoMiembro).where(
        GPProyectoMiembro.proyecto_id == proyecto_id))
    await db.delete(proyecto)
    await db.commit()


@router.post("/proyectos/{proyecto_id}/miembros", response_model=MiembroResponse,
             status_code=201)
async def agregar_miembro(
    proyecto_id: int, data: MiembroEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    await exigir_proyecto(db, quien, proyecto_id)
    rol = (data.rol or "MIEMBRO").upper()
    if rol not in ROLES_PROYECTO:
        raise HTTPException(422, f"Rol no válido. Son: {', '.join(ROLES_PROYECTO)}.")

    usuario = data.usuario.strip()
    ya = (await db.execute(select(GPProyectoMiembro).where(
        GPProyectoMiembro.proyecto_id == proyecto_id,
        GPProyectoMiembro.usuario == usuario))).scalar_one_or_none()
    if ya is not None:
        ya.rol = rol
        await db.commit()
        await db.refresh(ya)
        return ya

    miembro = GPProyectoMiembro(proyecto_id=proyecto_id, usuario=usuario, rol=rol)
    db.add(miembro)
    await db.commit()
    await db.refresh(miembro)
    return miembro


@router.delete("/proyectos/{proyecto_id}/miembros/{miembro_id}", status_code=204)
async def quitar_miembro(
    proyecto_id: int, miembro_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.configurar")),
):
    proyecto = await exigir_proyecto(db, quien, proyecto_id)
    miembro = (await db.execute(select(GPProyectoMiembro).where(
        GPProyectoMiembro.id == miembro_id,
        GPProyectoMiembro.proyecto_id == proyecto_id))).scalar_one_or_none()
    if miembro is None:
        raise HTTPException(404, "Esa persona no figura en el proyecto.")

    if proyecto.restringido:
        quedan = (await db.execute(select(func.count()).select_from(GPProyectoMiembro)
                                   .where(GPProyectoMiembro.proyecto_id == proyecto_id))).scalar() or 0
        if quedan <= 1:
            raise HTTPException(
                409,
                "Es la única persona del proyecto y el proyecto está "
                "restringido: quitarla lo dejaría inalcanzable.")

    await db.delete(miembro)
    await db.commit()


# ─── Configuración ────────────────────────────────────────────────────────────

@router.get("/configuracion")
async def configuracion(
    proyecto_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Todo lo que una pantalla necesita para dibujarse, en una sola petición.

    Tipos, prioridades, estados y campos se piden juntos porque se necesitan
    juntos: pedirlos por separado obliga a la pantalla a encadenar cuatro
    llamadas antes de mostrar la primera fila.
    """
    if proyecto_id is not None:
        await exigir_proyecto(db, quien, proyecto_id)

    # OR explícito: `IN (:proyecto, NULL)` deja fuera las filas cuyo proyecto es
    # NULL —los tipos globales— porque en SQL nada casa con NULL.
    ambito = (
        GPTipoIncidencia.proyecto_id.is_(None) if proyecto_id is None
        else or_(GPTipoIncidencia.proyecto_id == proyecto_id,
                 GPTipoIncidencia.proyecto_id.is_(None))
    )
    tipos = list((await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.archivado.is_(False), ambito,
    ).order_by(GPTipoIncidencia.orden))).scalars().all())

    prioridades = list((await db.execute(
        select(GPPrioridad).order_by(GPPrioridad.orden))).scalars().all())

    workflows = list((await db.execute(select(GPWorkflow).where(
        GPWorkflow.archivado.is_(False)).order_by(GPWorkflow.nombre))).scalars().all())

    estados = list((await db.execute(select(GPEstado).order_by(
        GPEstado.workflow_id, GPEstado.orden))).scalars().all())

    campos = gestion_campos.descripcion_de(
        await gestion_campos.campos_aplicables(db, proyecto_id, None))

    return {
        "tipos": [
            {"id": t.id, "clave": t.clave, "nombre": t.nombre, "icono": t.icono,
             "color": t.color, "nivel": t.nivel, "workflow_id": t.workflow_id,
             "proyecto_id": t.proyecto_id}
            for t in tipos
        ],
        "prioridades": [
            {"id": p.id, "clave": p.clave, "nombre": p.nombre, "color": p.color,
             "orden": p.orden, "por_defecto": p.por_defecto}
            for p in prioridades
        ],
        "workflows": [
            {"id": w.id, "nombre": w.nombre, "descripcion": w.descripcion,
             "por_defecto": w.por_defecto,
             "estados": [
                 {"id": e.id, "clave": e.clave, "nombre": e.nombre,
                  "categoria": e.categoria, "color": e.color, "orden": e.orden,
                  "inicial": e.inicial, "limite_wip": e.limite_wip}
                 for e in estados if e.workflow_id == w.id
             ]}
            for w in workflows
        ],
        "campos": campos,
        "vocabulario": {
            "categorias_estado": list(CATEGORIAS_ESTADO),
            "niveles": list(NIVELES),
            "tipos_campo": list(TIPOS_CAMPO),
            "roles_proyecto": list(ROLES_PROYECTO),
        },
        # Lo que se puede colgar de una transición sale del registro del
        # servidor, no de una lista escrita en la pantalla: una regla que el
        # servidor no conozca bloquea la transición.
        "reglas": gestion_workflow.catalogo(),
    }


@router.get("/workflows/{workflow_id}")
async def ver_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """El flujo con sus estados y transiciones, tal como lo ejecuta el motor."""
    wf = (await db.execute(select(GPWorkflow).where(
        GPWorkflow.id == workflow_id))).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, "Ese flujo no existe.")

    estados = list((await db.execute(select(GPEstado).where(
        GPEstado.workflow_id == workflow_id).order_by(GPEstado.orden))).scalars().all())
    transiciones = list((await db.execute(select(GPTransicion).where(
        GPTransicion.workflow_id == workflow_id
    ).order_by(GPTransicion.orden))).scalars().all())

    return {
        "id": wf.id, "nombre": wf.nombre, "descripcion": wf.descripcion,
        "por_defecto": wf.por_defecto, "archivado": wf.archivado,
        "estados": [
            {"id": e.id, "clave": e.clave, "nombre": e.nombre,
             "categoria": e.categoria, "color": e.color, "orden": e.orden,
             "inicial": e.inicial, "limite_wip": e.limite_wip}
            for e in estados
        ],
        "transiciones": [
            {"id": t.id, "nombre": t.nombre, "origen_id": t.origen_id,
             "destino_id": t.destino_id, "condiciones": t.condiciones,
             "validaciones": t.validaciones, "acciones": t.acciones,
             "orden": t.orden}
            for t in transiciones
        ],
    }


@router.get("/personas")
async def personas(
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """A quién se le puede asignar trabajo: el equipo de la consola.

    Sale de `plataforma_miembro` y no de un campo de texto libre. Con texto
    libre, «juan», «Juan» y «juan.perez» son tres responsables distintos, la
    carga por persona se reparte en tres, y filtrar por asignado no encuentra la
    mitad de lo que debería.
    """
    r = await db.execute(select(PlataformaMiembro).where(
        PlataformaMiembro.activo.is_(True)
    ).order_by(PlataformaMiembro.nombre, PlataformaMiembro.usuario))
    equipo = list(r.scalars().all())

    # Quien consulta va primero aunque el equipo no esté formalizado todavía:
    # si no, la persona que está creando la incidencia no se encuentra a sí
    # misma en el selector.
    if not any(m.usuario == quien.usuario for m in equipo):
        return [{"usuario": quien.usuario, "nombre": quien.usuario,
                 "rol": quien.rol, "soy_yo": True}] + [
            {"usuario": m.usuario, "nombre": m.nombre or m.usuario,
             "rol": m.rol, "soy_yo": False} for m in equipo]

    return [
        {"usuario": m.usuario, "nombre": m.nombre or m.usuario, "rol": m.rol,
         "soy_yo": m.usuario == quien.usuario}
        for m in equipo
    ]


@router.get("/proyectos/{proyecto_id}/padres")
async def padres_posibles(
    proyecto_id: int,
    nivel: str = "NORMAL",
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """De qué puede colgar una incidencia de ese nivel, dentro del proyecto.

    Se calcula acá y no en la pantalla porque la regla de jerarquía es del
    servidor: una lista armada en el navegador acabaría ofreciendo padres que el
    servidor rechaza al guardar.
    """
    await exigir_proyecto(db, quien, proyecto_id)

    esperado = {"SUBTAREA": "NORMAL", "NORMAL": "EPICA"}.get((nivel or "").upper())
    if esperado is None:
        return []

    tipos = select(GPTipoIncidencia.id).where(GPTipoIncidencia.nivel == esperado)
    r = await db.execute(
        select(GPIncidencia.id, GPIncidencia.numero, GPIncidencia.resumen)
        .where(GPIncidencia.proyecto_id == proyecto_id,
               GPIncidencia.tipo_id.in_(tipos))
        .order_by(GPIncidencia.numero.desc()).limit(200))

    proyecto = (await db.execute(select(GPProyecto).where(
        GPProyecto.id == proyecto_id))).scalar_one()
    return [
        {"id": i, "clave": f"{proyecto.clave}-{n}", "resumen": s}
        for i, n, s in r.all()
    ]


@router.get("/etiquetas")
async def etiquetas_usadas(
    proyecto_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Las etiquetas que ya se están usando, para proponerlas al escribir.

    Sin esto, cada quien inventa la suya —«regresion», «regresión», «regr»— y
    las etiquetas dejan de agrupar nada.
    """
    consulta = select(func.jsonb_array_elements_text(GPIncidencia.etiquetas))
    consulta = limitar(consulta, await proyectos_visibles(db, quien),
                       GPIncidencia.proyecto_id)
    if proyecto_id is not None:
        consulta = consulta.where(GPIncidencia.proyecto_id == proyecto_id)

    sub = consulta.subquery()
    r = await db.execute(
        select(sub.c[0], func.count()).select_from(sub)
        .group_by(sub.c[0]).order_by(func.count().desc()).limit(60))
    return [{"etiqueta": e, "usos": c} for e, c in r.all()]


@router.get("/campos")
async def listar_campos(
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """El catálogo completo de campos, para la pantalla de configuración."""
    campos = list((await db.execute(select(GPCampo).where(
        GPCampo.archivado.is_(False)).order_by(GPCampo.nombre))).scalars().all())
    if not campos:
        return []

    r = await db.execute(select(GPCampoOpcion).where(
        GPCampoOpcion.campo_id.in_([c.id for c in campos]),
        GPCampoOpcion.archivada.is_(False)).order_by(GPCampoOpcion.orden))
    opciones: Dict[int, list] = {}
    for o in r.scalars().all():
        opciones.setdefault(o.campo_id, []).append(
            {"id": o.id, "valor": o.valor, "etiqueta": o.etiqueta, "color": o.color})

    return [
        {"id": c.id, "clave": c.clave, "nombre": c.nombre,
         "descripcion": c.descripcion, "ayuda": c.ayuda, "tipo": c.tipo,
         "validacion": c.validacion, "valor_defecto": c.valor_defecto,
         "filtrable": c.filtrable, "ordenable": c.ordenable,
         "del_sistema": c.del_sistema, "opciones": opciones.get(c.id, [])}
        for c in campos
    ]
