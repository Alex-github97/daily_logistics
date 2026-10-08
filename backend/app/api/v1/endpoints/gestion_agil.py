"""
Sprints, backlog, Gantt y métricas.

Tres reglas que sostienen que las cifras signifiquen algo:

  · **Al cerrar un sprint, lo no terminado vuelve al backlog.** Arrastrarlo al
    siguiente escondería que no cupo, y la velocidad dejaría de medir nada.
  · **La velocidad se congela al cerrar.** Si se recalculara, reestimar algo
    viejo cambiaría la historia.
  · **Solo un sprint activo por proyecto.** Dos a la vez hacen que «en qué
    estamos trabajando» deje de tener una respuesta.

El Gantt dibuja el plan (`inicio_plan` → `vence`) y encima lo real
(`iniciado` → `resuelto`). Con una sola barra no se puede ver si el plan se está
cumpliendo, que es lo único que un Gantt sirve para responder.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.gestion_incidencias import Tarjeta, _tarjetas
from app.core import gestion_incidencias
from app.core.database import get_db_plataforma
from app.core.gestion_permisos import exigir_proyecto
from app.core.permisos_consola import Miembro, exigir
from app.infrastructure.models.gestion import (
    GPEstado, GPHistorial, GPIncidencia, GPSprint, GPTipoIncidencia, GPVinculo,
)

router = APIRouter(prefix="/gestion", tags=["Gestión"])


# ─── Formas ───────────────────────────────────────────────────────────────────

class SprintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    proyecto_id: int
    nombre: str
    objetivo: Optional[str] = None
    inicio: Optional[date] = None
    fin: Optional[date] = None
    estado: str
    puntos_comprometidos: Optional[int] = None
    puntos_completados: Optional[int] = None
    cerrado_en: Optional[datetime] = None
    # Se calculan
    total: int = 0
    puntos_totales: int = 0
    puntos_hechos: int = 0
    sin_estimar: int = 0


class SprintEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    objetivo: Optional[str] = None
    inicio: Optional[date] = None
    fin: Optional[date] = None


class BarraGantt(BaseModel):
    id: int
    clave: str
    resumen: str
    tipo: Optional[str] = None
    icono: Optional[str] = None
    estado: Optional[str] = None
    categoria: Optional[str] = None
    color: Optional[str] = None
    asignado: Optional[str] = None
    puntos: Optional[int] = None
    nivel: str = 'NORMAL'
    padre_id: Optional[int] = None
    # El plan
    inicio_plan: Optional[datetime] = None
    vence: Optional[datetime] = None
    # Lo que de verdad pasó
    iniciado: Optional[datetime] = None
    resuelto: Optional[datetime] = None
    # A quién bloquea, y de quién depende. Son las flechas del diagrama.
    #
    # Se devuelven los dos sentidos aunque el vínculo se guarde una sola vez: la
    # pantalla necesita responder «¿qué me está frenando?», y calcular eso
    # invirtiendo el mapa en el navegador obliga a tener cargadas TODAS las
    # barras, cosa que deja de ser cierta en cuanto se filtra por sprint.
    bloquea_a: List[int] = []
    depende_de: List[int] = []
    # Cuánto de esto está hecho, de 0 a 1. En una tarea con hijas es la fracción
    # de hijas terminadas; en una hoja, 1 si está terminada y 0 si no. No se
    # inventa un punto medio para lo que está en curso: un porcentaje que nadie
    # midió es peor que no tener porcentaje.
    avance: float = 0.0
    # Cuántas hijas tiene. La pantalla lo usa para saber si dibujar el desplegable
    # sin tener que recorrer la lista entera por cada fila.
    hijas: int = 0


class Gantt(BaseModel):
    desde: Optional[date] = None
    hasta: Optional[date] = None
    barras: List[BarraGantt]
    # Las que no tienen ninguna fecha: se listan aparte en vez de esconderlas,
    # porque «no aparece en el Gantt» se lee como que se perdió.
    sin_fechas: List[Tarjeta] = []


# ─── Sprints ──────────────────────────────────────────────────────────────────

def _con_zona(momento: Optional[datetime]) -> Optional[datetime]:
    """Una fecha siempre con zona, asumiendo UTC si no la trae.

    Las columnas son `timestamptz`. Una fecha ingenua la interpreta PostgreSQL
    con la zona de la sesion —que no es la misma en todas las conexiones— y
    ademas rompe cualquier comparacion posterior con las que si la traen.
    """
    if momento is None:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


async def _resumir(db: AsyncSession, sprints: List[GPSprint]) -> List[SprintResponse]:
    """Agrega las cifras de todos los sprints en una consulta, no en una por uno."""
    if not sprints:
        return []
    ids = [s.id for s in sprints]

    r = await db.execute(
        select(GPIncidencia.sprint_id, GPEstado.categoria,
               func.count(), func.coalesce(func.sum(GPIncidencia.puntos), 0),
               func.count().filter(GPIncidencia.puntos.is_(None)))
        .join(GPEstado, GPEstado.id == GPIncidencia.estado_id)
        .where(GPIncidencia.sprint_id.in_(ids))
        .group_by(GPIncidencia.sprint_id, GPEstado.categoria))

    total: Dict[int, int] = {}
    puntos: Dict[int, int] = {}
    hechos: Dict[int, int] = {}
    sin_estimar: Dict[int, int] = {}
    for sid, categoria, cuantas, pts, sin in r.all():
        total[sid] = total.get(sid, 0) + cuantas
        puntos[sid] = puntos.get(sid, 0) + int(pts or 0)
        sin_estimar[sid] = sin_estimar.get(sid, 0) + cuantas if sin else sin_estimar.get(sid, 0)
        if categoria == "TERMINADO":
            hechos[sid] = hechos.get(sid, 0) + int(pts or 0)

    salida = []
    for s in sprints:
        ficha = SprintResponse.model_validate(s)
        ficha.total = total.get(s.id, 0)
        ficha.puntos_totales = puntos.get(s.id, 0)
        ficha.puntos_hechos = hechos.get(s.id, 0)
        ficha.sin_estimar = sin_estimar.get(s.id, 0)
        salida.append(ficha)
    return salida


@router.get("/proyectos/{proyecto_id}/sprints", response_model=List[SprintResponse])
async def listar_sprints(
    proyecto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    await exigir_proyecto(db, quien, proyecto_id)
    r = await db.execute(select(GPSprint).where(
        GPSprint.proyecto_id == proyecto_id
    ).order_by(GPSprint.inicio.desc().nullslast(), GPSprint.id.desc()))
    return await _resumir(db, list(r.scalars().all()))


@router.post("/proyectos/{proyecto_id}/sprints", response_model=SprintResponse,
             status_code=201)
async def crear_sprint(
    proyecto_id: int, data: SprintEntrada,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    await exigir_proyecto(db, quien, proyecto_id, escritura=True)
    if data.inicio and data.fin and data.fin < data.inicio:
        raise HTTPException(422, "La fecha de fin no puede ser anterior a la de inicio.")

    sprint = GPSprint(
        proyecto_id=proyecto_id, nombre=data.nombre.strip(), objetivo=data.objetivo,
        inicio=data.inicio, fin=data.fin, estado="PLANEADO")
    db.add(sprint)
    await db.commit()
    await db.refresh(sprint)
    return (await _resumir(db, [sprint]))[0]


@router.post("/sprints/{sprint_id}/activar", response_model=SprintResponse)
async def activar_sprint(
    sprint_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    sprint = await _sprint_editable(db, quien, sprint_id)
    if sprint.estado == "CERRADO":
        raise HTTPException(409, "Un sprint cerrado no se puede reabrir.")

    otro = (await db.execute(select(GPSprint).where(
        GPSprint.proyecto_id == sprint.proyecto_id,
        GPSprint.estado == "ACTIVO", GPSprint.id != sprint_id))).scalar_one_or_none()
    if otro is not None:
        raise HTTPException(
            409,
            f"«{otro.nombre}» sigue activo. Ciérrelo primero: con dos sprints a la "
            f"vez, «en qué estamos trabajando» deja de tener una respuesta.")

    # El compromiso se sella al arrancar, no al cerrar: si se calculara al final
    # incluiría lo que se metió a mitad de camino y el sprint siempre parecería
    # bien planeado.
    comprometidos = (await db.execute(
        select(func.coalesce(func.sum(GPIncidencia.puntos), 0)).where(
            GPIncidencia.sprint_id == sprint_id))).scalar() or 0

    sprint.estado = "ACTIVO"
    sprint.puntos_comprometidos = int(comprometidos)
    if not sprint.inicio:
        sprint.inicio = datetime.now(timezone.utc).date()
    await db.commit()
    await db.refresh(sprint)
    return (await _resumir(db, [sprint]))[0]


@router.post("/sprints/{sprint_id}/cerrar", response_model=SprintResponse)
async def cerrar_sprint(
    sprint_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Cierra el sprint y devuelve al backlog lo que no se terminó."""
    sprint = await _sprint_editable(db, quien, sprint_id)
    if sprint.estado == "CERRADO":
        raise HTTPException(409, "Ese sprint ya estaba cerrado.")

    completados = (await db.execute(
        select(func.coalesce(func.sum(GPIncidencia.puntos), 0))
        .join(GPEstado, GPEstado.id == GPIncidencia.estado_id)
        .where(GPIncidencia.sprint_id == sprint_id,
               GPEstado.categoria == "TERMINADO"))).scalar() or 0

    pendientes = list((await db.execute(
        select(GPIncidencia)
        .join(GPEstado, GPEstado.id == GPIncidencia.estado_id)
        .where(GPIncidencia.sprint_id == sprint_id,
               GPEstado.categoria != "TERMINADO"))).scalars().all())
    for inc in pendientes:
        inc.sprint_id = None
        gestion_incidencias.anotar(
            db, inc.id, "sprint", sprint.nombre, None, quien.usuario)

    sprint.estado = "CERRADO"
    sprint.puntos_completados = int(completados)
    sprint.cerrado_en = datetime.now(timezone.utc)
    if not sprint.fin:
        sprint.fin = datetime.now(timezone.utc).date()

    await db.commit()
    await db.refresh(sprint)
    return (await _resumir(db, [sprint]))[0]


async def _sprint_editable(db: AsyncSession, quien: Miembro, sprint_id: int) -> GPSprint:
    sprint = (await db.execute(select(GPSprint).where(
        GPSprint.id == sprint_id))).scalar_one_or_none()
    if sprint is None:
        raise HTTPException(404, "Ese sprint no existe.")
    await exigir_proyecto(db, quien, sprint.proyecto_id, escritura=True)
    return sprint


# ─── Backlog ──────────────────────────────────────────────────────────────────

class MoverAlSprint(BaseModel):
    ids: List[int]
    sprint_id: Optional[int] = None


@router.get("/proyectos/{proyecto_id}/backlog")
async def backlog(
    proyecto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Lo que está fuera de todo sprint, más lo del sprint activo.

    Se devuelven juntos porque planear es mover cosas entre las dos listas, y
    tenerlas en dos pantallas obliga a recordar de memoria qué había en la otra.
    """
    await exigir_proyecto(db, quien, proyecto_id)

    activo = (await db.execute(select(GPSprint).where(
        GPSprint.proyecto_id == proyecto_id,
        GPSprint.estado == "ACTIVO"))).scalar_one_or_none()

    # Fuera del backlog lo terminado: un backlog que arrastra lo hecho deja de
    # ser una lista de trabajo pendiente.
    terminados = select(GPEstado.id).where(GPEstado.categoria == "TERMINADO")

    sueltas = list((await db.execute(
        select(GPIncidencia).where(
            GPIncidencia.proyecto_id == proyecto_id,
            GPIncidencia.sprint_id.is_(None),
            GPIncidencia.estado_id.notin_(terminados),
        ).order_by(GPIncidencia.orden))).scalars().all())

    del_sprint = []
    if activo is not None:
        del_sprint = list((await db.execute(
            select(GPIncidencia).where(
                GPIncidencia.sprint_id == activo.id
            ).order_by(GPIncidencia.orden))).scalars().all())

    return {
        "sprint": (await _resumir(db, [activo]))[0] if activo else None,
        "en_sprint": await _tarjetas(db, del_sprint),
        "backlog": await _tarjetas(db, sueltas),
    }


@router.put("/backlog/sprint")
async def mover_al_sprint(
    data: MoverAlSprint,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Mete o saca incidencias de un sprint."""
    if not data.ids:
        return {"movidas": 0}

    incidencias = list((await db.execute(select(GPIncidencia).where(
        GPIncidencia.id.in_(data.ids)))).scalars().all())
    if not incidencias:
        raise HTTPException(404, "Ninguna de esas incidencias existe.")

    sprint = None
    if data.sprint_id is not None:
        sprint = await _sprint_editable(db, quien, data.sprint_id)
        if sprint.estado == "CERRADO":
            raise HTTPException(409, "No se puede agregar trabajo a un sprint cerrado.")

    for inc in incidencias:
        await exigir_proyecto(db, quien, inc.proyecto_id, escritura=True)
        if sprint is not None and inc.proyecto_id != sprint.proyecto_id:
            raise HTTPException(
                400, "Una incidencia solo puede entrar a un sprint de su propio proyecto.")
        anterior = inc.sprint_id
        if anterior == data.sprint_id:
            continue
        inc.sprint_id = data.sprint_id
        gestion_incidencias.anotar(
            db, inc.id, "sprint",
            None if anterior is None else str(anterior),
            sprint.nombre if sprint else None, quien.usuario)

    await db.commit()
    return {"movidas": len(incidencias)}


class Reordenar(BaseModel):
    ids: List[int]


@router.put("/backlog/orden")
async def reordenar(
    data: Reordenar,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Fija el orden del backlog según la lista que llega.

    Se reescriben las posiciones de todo lo que se manda, espaciadas de mil en
    mil. El hueco entre una y otra es lo que permite insertar después sin volver
    a numerar la lista entera en cada arrastre.
    """
    incidencias = {
        i.id: i for i in (await db.execute(select(GPIncidencia).where(
            GPIncidencia.id.in_(data.ids)))).scalars().all()
    }
    for posicion, ident in enumerate(data.ids):
        inc = incidencias.get(ident)
        if inc is not None:
            inc.orden = float(posicion + 1) * 1000.0
    await db.commit()
    return {"ordenadas": len(incidencias)}


# ─── Gantt ────────────────────────────────────────────────────────────────────

@router.get("/proyectos/{proyecto_id}/gantt", response_model=Gantt)
async def gantt(
    proyecto_id: int,
    sprint_id: Optional[int] = None,
    incluir_terminadas: bool = True,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Las barras del diagrama, con el plan y lo real.

    Una incidencia entra si tiene alguna fecha —planeada o real—. Las que no
    tienen ninguna se devuelven aparte en vez de descartarse: desaparecer de la
    pantalla se lee como que se perdieron, y lo que hace falta es justo lo
    contrario, que se vean para poder ponerles fecha.
    """
    await exigir_proyecto(db, quien, proyecto_id)

    consulta = select(GPIncidencia).where(GPIncidencia.proyecto_id == proyecto_id)
    if sprint_id is not None:
        consulta = consulta.where(GPIncidencia.sprint_id == sprint_id)
    if not incluir_terminadas:
        consulta = consulta.where(GPIncidencia.estado_id.notin_(
            select(GPEstado.id).where(GPEstado.categoria == "TERMINADO")))

    incidencias = list((await db.execute(consulta)).scalars().all())
    if not incidencias:
        return Gantt(barras=[], sin_fechas=[])

    ids = [i.id for i in incidencias]
    estados = {
        e.id: e for e in (await db.execute(select(GPEstado).where(
            GPEstado.id.in_({i.estado_id for i in incidencias})))).scalars().all()
    }
    tipos = {
        t.id: t for t in (await db.execute(select(GPTipoIncidencia).where(
            GPTipoIncidencia.id.in_({i.tipo_id for i in incidencias})))).scalars().all()
    }

    # Las flechas del diagrama, en los dos sentidos y de una sola consulta: una
    # por barra es el patrón que convierte cien tareas en doscientas consultas.
    #
    # Solo los vínculos que expresan precedencia. «Se relaciona con» o «duplica
    # a» no dicen que una vaya antes que otra, y dibujarlos como flecha haría
    # leer un orden que nadie declaró.
    PRECEDENCIA = ("BLOQUEA", "DEPENDE", "CAUSA")
    r = await db.execute(select(GPVinculo).where(
        GPVinculo.tipo.in_(PRECEDENCIA),
        or_(GPVinculo.origen_id.in_(ids), GPVinculo.destino_id.in_(ids))))
    bloqueos: Dict[int, List[int]] = {}
    dependencias: Dict[int, List[int]] = {}
    for v in r.scalars().all():
        # «A depende de B» se guarda como origen=A, destino=B; los otros dos van
        # al revés —A bloquea a B, A causa B—, así que la flecha apunta distinto.
        if v.tipo == "DEPENDE":
            antes, despues = v.destino_id, v.origen_id
        else:
            antes, despues = v.origen_id, v.destino_id
        bloqueos.setdefault(antes, []).append(despues)
        dependencias.setdefault(despues, []).append(antes)

    # Cuántas hijas tiene cada una y cuántas están terminadas, para el avance y
    # para saber si dibujar el desplegable.
    terminados = select(GPEstado.id).where(GPEstado.categoria == "TERMINADO")
    r = await db.execute(
        select(GPIncidencia.padre_id, func.count(),
               func.count().filter(GPIncidencia.estado_id.in_(terminados)))
        .where(GPIncidencia.padre_id.in_(ids))
        .group_by(GPIncidencia.padre_id))
    conteo_hijas: Dict[int, tuple] = {p: (t, h) for p, t, h in r.all()}

    barras: List[BarraGantt] = []
    huerfanas: List[GPIncidencia] = []
    momentos: List[datetime] = []

    for i in incidencias:
        # Se normalizan al leer, no solo al escribir: puede haber filas de antes
        # de que la escritura pusiera la zona, y una sola tumba la comparacion.
        fechas = [_con_zona(f) for f in
                  (i.inicio_plan, i.vence, i.iniciado, i.resuelto) if f]
        if not fechas:
            huerfanas.append(i)
            continue
        momentos.extend(fechas)
        estado = estados.get(i.estado_id)
        tipo = tipos.get(i.tipo_id)

        # El avance: en una tarea con hijas, la fracción terminada; en una hoja,
        # todo o nada. No se inventa un punto medio para lo que está en curso —un
        # porcentaje que nadie midió es peor que no tener porcentaje—.
        total_hijas, hechas = conteo_hijas.get(i.id, (0, 0))
        if total_hijas:
            avance = hechas / total_hijas
        else:
            avance = 1.0 if (estado and estado.categoria == "TERMINADO") else 0.0

        barras.append(BarraGantt(
            id=i.id,
            clave=f"{proyecto_id}-{i.numero}",   # se reemplaza abajo
            resumen=i.resumen,
            tipo=tipo.nombre if tipo else None,
            icono=tipo.icono if tipo else None,
            nivel=tipo.nivel if tipo else "NORMAL",
            estado=estado.nombre if estado else None,
            categoria=estado.categoria if estado else None,
            color=estado.color if estado else None,
            asignado=i.asignado, puntos=i.puntos, padre_id=i.padre_id,
            inicio_plan=i.inicio_plan, vence=i.vence,
            iniciado=i.iniciado, resuelto=i.resuelto,
            bloquea_a=bloqueos.get(i.id, []),
            depende_de=dependencias.get(i.id, []),
            avance=round(avance, 3),
            hijas=total_hijas,
        ))

    # La clave visible lleva el prefijo del proyecto.
    fichas = {t.id: t.clave for t in await _tarjetas(db, incidencias)}
    for b in barras:
        b.clave = fichas.get(b.id, b.clave)

    return Gantt(
        desde=min(momentos).date() if momentos else None,
        hasta=max(momentos).date() if momentos else None,
        barras=sorted(barras, key=lambda b: (
            b.inicio_plan or b.iniciado or b.vence or b.resuelto)),
        sin_fechas=await _tarjetas(db, huerfanas),
    )


class FechasPlan(BaseModel):
    inicio_plan: Optional[datetime] = None
    vence: Optional[datetime] = None


@router.put("/incidencias/{incidencia_id}/plan")
async def fijar_plan(
    incidencia_id: int, data: FechasPlan,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.trabajar")),
):
    """Las fechas planeadas, que son las que dibujan la barra del Gantt."""
    inc = (await db.execute(select(GPIncidencia).where(
        GPIncidencia.id == incidencia_id))).scalar_one_or_none()
    if inc is None:
        raise HTTPException(404, "Esa incidencia no existe.")
    await exigir_proyecto(db, quien, inc.proyecto_id, escritura=True)

    # Con zona horaria siempre. Una fecha ingenua en una columna `timestamptz` la
    # interpreta PostgreSQL con la zona de la sesión —que no es la misma en todas
    # las conexiones— y además rompe cualquier comparación posterior con las que
    # sí la traen: «can't compare offset-naive and offset-aware datetimes».
    inicio = _con_zona(data.inicio_plan)
    vence = _con_zona(data.vence)

    if inicio and vence and vence < inicio:
        raise HTTPException(422, "La fecha de fin no puede ser anterior a la de inicio.")

    for campo, nuevo in (("inicio_plan", inicio), ("vence", vence)):
        anterior = getattr(inc, campo)
        if anterior != nuevo:
            setattr(inc, campo, nuevo)
            gestion_incidencias.anotar(db, inc.id, campo, anterior, nuevo, quien.usuario)

    inc.actualizado = datetime.now(timezone.utc)
    await db.commit()
    return {"inicio_plan": inc.inicio_plan, "vence": inc.vence}


# ─── Métricas ─────────────────────────────────────────────────────────────────

@router.get("/proyectos/{proyecto_id}/metricas")
async def metricas(
    proyecto_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("gestion.ver")),
):
    """Velocidad, burndown del sprint activo y tiempo de ciclo.

    El burndown se calcula sobre el HISTORIAL y no sobre el estado de hoy: sobre
    el estado actual mostraría el pasado como si siempre hubiera sido así, y una
    curva que se redibuja sola cada vez que alguien mueve algo viejo no sirve
    para decidir nada.
    """
    await exigir_proyecto(db, quien, proyecto_id)

    cerrados = list((await db.execute(select(GPSprint).where(
        GPSprint.proyecto_id == proyecto_id, GPSprint.estado == "CERRADO"
    ).order_by(GPSprint.cerrado_en).limit(12))).scalars().all())

    velocidad = [
        {"sprint": s.nombre,
         "comprometidos": s.puntos_comprometidos or 0,
         "completados": s.puntos_completados or 0}
        for s in cerrados
    ]

    activo = (await db.execute(select(GPSprint).where(
        GPSprint.proyecto_id == proyecto_id,
        GPSprint.estado == "ACTIVO"))).scalar_one_or_none()

    burndown: List[dict] = []
    # Por qué no hay curva, cuando no la hay. Devolver una lista vacía sin más
    # deja a la pantalla con un recuadro en blanco, y en blanco se lee como que
    # la herramienta falló y no como que falta un dato que alguien puede poner.
    burndown_nota: Optional[str] = None
    if activo is None:
        burndown_nota = "No hay ningún sprint activo."
    elif not (activo.inicio and activo.fin):
        burndown_nota = (
            f"«{activo.nombre}» no tiene fecha de fin. Sin horizonte no hay contra "
            f"qué comparar el avance.")

    if activo and activo.inicio and activo.fin:
        total = (await db.execute(
            select(func.coalesce(func.sum(GPIncidencia.puntos), 0)).where(
                GPIncidencia.sprint_id == activo.id))).scalar() or 0

        # Cuándo pasó cada incidencia a un estado terminado, según el historial.
        terminados = {
            e.nombre for e in (await db.execute(select(GPEstado).where(
                GPEstado.categoria == "TERMINADO"))).scalars().all()
        }
        puntos_por_inc = {
            i.id: (i.puntos or 0) for i in (await db.execute(select(GPIncidencia).where(
                GPIncidencia.sprint_id == activo.id))).scalars().all()
        }
        r = await db.execute(select(GPHistorial).where(
            GPHistorial.incidencia_id.in_(list(puntos_por_inc) or [-1]),
            GPHistorial.campo == "estado").order_by(GPHistorial.creado))
        quemado_en: Dict[date, int] = {}
        ya = set()
        for h in r.scalars().all():
            if h.nuevo in terminados and h.incidencia_id not in ya:
                ya.add(h.incidencia_id)
                dia = h.creado.date()
                quemado_en[dia] = quemado_en.get(dia, 0) + puntos_por_inc.get(h.incidencia_id, 0)

        dias = (activo.fin - activo.inicio).days + 1
        hoy = datetime.now(timezone.utc).date()
        restante = float(total)
        for n in range(max(dias, 1)):
            dia = activo.inicio + timedelta(days=n)
            restante -= quemado_en.get(dia, 0)
            burndown.append({
                "fecha": dia.isoformat(),
                "ideal": round(total - (total * n / max(dias - 1, 1)), 1),
                # Sin datos del futuro: la línea real se corta hoy. Prolongarla
                # en plano hace creer que el trabajo se detuvo.
                "real": round(restante, 1) if dia <= hoy else None,
            })

    # Tiempo de ciclo: de que empezó a que se resolvió. Medir desde que se creó
    # incluye la espera en el backlog, que depende de otra cosa.
    ciclo = (await db.execute(
        select(func.avg(
            func.extract("epoch", GPIncidencia.resuelto - GPIncidencia.iniciado) / 86400.0
        )).where(
            GPIncidencia.proyecto_id == proyecto_id,
            GPIncidencia.iniciado.isnot(None),
            GPIncidencia.resuelto.isnot(None)))).scalar()

    r = await db.execute(
        select(GPTipoIncidencia.nombre, func.count())
        .join(GPIncidencia, GPIncidencia.tipo_id == GPTipoIncidencia.id)
        .where(GPIncidencia.proyecto_id == proyecto_id)
        .group_by(GPTipoIncidencia.nombre))
    por_tipo = {nombre: cuantas for nombre, cuantas in r.all()}

    r = await db.execute(
        select(GPEstado.categoria, func.count())
        .join(GPIncidencia, GPIncidencia.estado_id == GPEstado.id)
        .where(GPIncidencia.proyecto_id == proyecto_id)
        .group_by(GPEstado.categoria))
    por_categoria = {categoria: cuantas for categoria, cuantas in r.all()}

    r = await db.execute(
        select(GPIncidencia.asignado, func.count(),
               func.coalesce(func.sum(GPIncidencia.puntos), 0))
        .join(GPEstado, GPEstado.id == GPIncidencia.estado_id)
        .where(GPIncidencia.proyecto_id == proyecto_id,
               GPEstado.categoria.in_(("POR_HACER", "EN_CURSO")))
        .group_by(GPIncidencia.asignado))
    carga = [
        {"usuario": usuario or "sin asignar", "abiertas": cuantas, "puntos": int(pts or 0)}
        for usuario, cuantas, pts in r.all()
    ]

    return {
        "velocidad": velocidad,
        "burndown": burndown,
        "burndown_nota": burndown_nota,
        "sprint_activo": (await _resumir(db, [activo]))[0] if activo else None,
        "tiempo_ciclo_dias": round(float(ciclo), 1) if ciclo is not None else None,
        "por_tipo": por_tipo,
        "por_categoria": por_categoria,
        "carga": sorted(carga, key=lambda c: -c["abiertas"]),
    }
