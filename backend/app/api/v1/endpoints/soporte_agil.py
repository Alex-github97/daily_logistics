"""
Gestión ágil de las solicitudes: tablero, backlog, sprints y métricas.

Todo esto es solo para el equipo, así que va entero detrás de los permisos
de soporte.
El cliente sigue viendo su conversación y su estado; no ve puntos, ni sprints,
ni en qué columna está su solicitud.

Tres decisiones que sostienen el resto:

  · El límite de trabajo en curso se hace cumplir en el servidor. Un límite que
    se puede exceder en silencio no limita nada, y el problema que resuelve
    —empezar diez cosas y no terminar ninguna— es justo el que aparece cuando
    nadie lo hace cumplir.
  · Al cerrar un sprint, lo no terminado vuelve al backlog. Arrastrarlo al
    siguiente escondería que no cupo, y la velocidad dejaría de significar algo.
  · La velocidad se congela al cerrar. Si se recalculara, reestimar una
    solicitud vieja cambiaría la historia.
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_plataforma
from app.core.security import decode_token
from app.infrastructure.models.soporte import (
    SoporteTicket, SoporteSprint, SoporteEpica, SoporteEvento, SoporteColumna,
    ESTADOS, TIPOS_TRABAJO, PUNTOS, ESTADOS_SPRINT,
)
from app.core.permisos_consola import exigir

router = APIRouter(prefix="/soporte", tags=["Soporte"])


# Columnas por defecto. Se siembran la primera vez que se pide el tablero, para
# que exista uno usable sin obligar a configurarlo antes de empezar.
COLUMNAS_INICIALES = [
    ("NUEVO", "Por hacer", 0, None),
    ("EN_PROGRESO", "En curso", 1, 5),
    ("ESPERANDO_CLIENTE", "Esperando al cliente", 2, None),
    ("RESUELTO", "Listo", 3, None),
    ("CERRADO", "Cerrado", 4, None),
]

# Las columnas donde el trabajo está realmente en manos del equipo. Solo ahí
# tiene sentido un límite: lo que espera al cliente no lo bloquea el equipo.
COLUMNAS_ACTIVAS = {"EN_PROGRESO"}


def _sin_zona(momento: Optional[datetime]) -> Optional[datetime]:
    """Quita la zona horaria para poder comparar.

    `created_at` viene del mixin y lleva zona; las columnas de soporte se
    declararon sin ella. Restar una de otra revienta con "can't compare
    offset-naive and offset-aware datetimes", y como los dos valores están en
    UTC, quitar la zona no mueve ningún instante.
    """
    if momento is None:
        return None
    return momento.replace(tzinfo=None) if momento.tzinfo else momento


def _autor(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return "?"
    try:
        datos = decode_token(auth[7:])
        return str(datos.get("usr") or datos.get("sub") or "?")
    except Exception:
        return "?"


def _anotar(db: AsyncSession, ticket_id: int, campo: str,
            anterior, nuevo, autor: str) -> None:
    db.add(SoporteEvento(
        ticket_id=ticket_id, campo=campo,
        anterior=None if anterior is None else str(anterior)[:120],
        nuevo=None if nuevo is None else str(nuevo)[:120],
        autor=autor, fecha=datetime.utcnow()))


async def _columnas(db: AsyncSession) -> List[SoporteColumna]:
    r = await db.execute(select(SoporteColumna).order_by(SoporteColumna.orden))
    columnas = list(r.scalars().all())
    if not columnas:
        for estado, titulo, orden, wip in COLUMNAS_INICIALES:
            db.add(SoporteColumna(estado=estado, titulo=titulo, orden=orden, limite_wip=wip))
        await db.commit()
        r = await db.execute(select(SoporteColumna).order_by(SoporteColumna.orden))
        columnas = list(r.scalars().all())
    return columnas


# ─── Lo que se devuelve ───────────────────────────────────────────────────────

class TarjetaTicket(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero: str
    asunto: str
    estado: str
    criticidad: str
    tipo_trabajo: Optional[str] = None
    puntos: Optional[int] = None
    sprint_id: Optional[int] = None
    epica_id: Optional[int] = None
    orden: Optional[float] = None
    etiquetas: Optional[List[str]] = None
    asignado_a: Optional[str] = None
    cliente_codigo: str
    autor: str
    modulo: Optional[str] = None
    created_at: Optional[datetime] = None
    ultima_actividad: Optional[datetime] = None
    iniciado_en: Optional[datetime] = None
    resuelto_en: Optional[datetime] = None


class ColumnaTablero(BaseModel):
    estado: str
    titulo: str
    orden: int
    limite_wip: Optional[int] = None
    # Cuántas hay ahora. Con el límite al lado, dice si se puede meter otra.
    cantidad: int = 0
    puntos: int = 0
    tarjetas: List[TarjetaTicket] = []


class Tablero(BaseModel):
    sprint: Optional[dict] = None
    columnas: List[ColumnaTablero] = []


class Sprint(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    nombre: str
    objetivo: Optional[str] = None
    inicio: Optional[date] = None
    fin: Optional[date] = None
    estado: str = "PLANEADO"
    puntos_comprometidos: Optional[int] = None
    puntos_completados: Optional[int] = None
    cerrado_en: Optional[datetime] = None
    # Calculados sobre lo que hay ahora, para el sprint en curso.
    total_solicitudes: int = 0
    puntos_en_curso: int = 0
    puntos_hechos: int = 0


class Epica(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = None
    color: Optional[str] = None
    archivada: bool = False
    solicitudes: int = 0
    puntos: int = 0


# ─── Tablero ──────────────────────────────────────────────────────────────────

@router.get("/agil/tablero", response_model=Tablero)
async def tablero(
    sprint_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    """El tablero del sprint activo, o del que se pida.

    Sin ningún sprint activo muestra lo que está en curso fuera de sprint: si
    no, el equipo que trabaja sin iteraciones vería un tablero vacío.
    """
    columnas = await _columnas(db)

    sprint = None
    if sprint_id:
        sprint = await db.get(SoporteSprint, sprint_id)
    else:
        r = await db.execute(select(SoporteSprint).where(SoporteSprint.estado == "ACTIVO"))
        sprint = r.scalar_one_or_none()

    q = select(SoporteTicket)
    if sprint:
        q = q.where(SoporteTicket.sprint_id == sprint.id)
    else:
        q = q.where(SoporteTicket.sprint_id.is_(None),
                    SoporteTicket.estado != "CERRADO")
    tickets = list((await db.execute(
        q.order_by(SoporteTicket.orden, SoporteTicket.id))).scalars().all())

    por_estado: Dict[str, List[SoporteTicket]] = {}
    for t in tickets:
        por_estado.setdefault(t.estado, []).append(t)

    salida = Tablero()
    if sprint:
        salida.sprint = {
            "id": sprint.id, "nombre": sprint.nombre, "objetivo": sprint.objetivo,
            "inicio": str(sprint.inicio) if sprint.inicio else None,
            "fin": str(sprint.fin) if sprint.fin else None,
            "estado": sprint.estado,
        }
    for c in columnas:
        del_estado = por_estado.get(c.estado, [])
        salida.columnas.append(ColumnaTablero(
            estado=c.estado, titulo=c.titulo, orden=c.orden or 0,
            limite_wip=c.limite_wip,
            cantidad=len(del_estado),
            puntos=sum(t.puntos or 0 for t in del_estado),
            tarjetas=[TarjetaTicket.model_validate(t) for t in del_estado],
        ))
    return salida


class Movimiento(BaseModel):
    estado: str
    # Entre qué dos tarjetas queda. Vacío = al final de la columna.
    orden_anterior: Optional[float] = None
    orden_siguiente: Optional[float] = None


@router.put("/agil/tickets/{ticket_id}/mover", response_model=TarjetaTicket)
async def mover(
    ticket_id: int, data: Movimiento, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    """Mueve una solicitud de columna, respetando el límite de trabajo en curso."""
    ticket = await db.get(SoporteTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Esa solicitud no existe")
    nuevo = (data.estado or "").upper()
    if nuevo not in ESTADOS:
        raise HTTPException(400, f"Estado inválido. Use uno de: {', '.join(ESTADOS)}.")

    if nuevo != ticket.estado and nuevo in COLUMNAS_ACTIVAS:
        columna = (await db.execute(
            select(SoporteColumna).where(SoporteColumna.estado == nuevo))).scalar_one_or_none()
        if columna and columna.limite_wip:
            q = select(func.count()).select_from(SoporteTicket).where(
                SoporteTicket.estado == nuevo)
            if ticket.sprint_id:
                q = q.where(SoporteTicket.sprint_id == ticket.sprint_id)
            actuales = (await db.execute(q)).scalar() or 0
            if actuales >= columna.limite_wip:
                raise HTTPException(
                    409,
                    f"«{columna.titulo}» ya tiene {actuales} solicitudes y su límite es "
                    f"{columna.limite_wip}. Termine algo antes de empezar otra cosa, o "
                    f"suba el límite si el equipo creció.",
                )

    autor = _autor(request)
    ahora = datetime.utcnow()
    if nuevo != ticket.estado:
        _anotar(db, ticket.id, "estado", ticket.estado, nuevo, autor)
        # La primera vez que entra a trabajo activo arranca el tiempo de ciclo.
        if nuevo in COLUMNAS_ACTIVAS and not ticket.iniciado_en:
            ticket.iniciado_en = ahora
        if nuevo == "RESUELTO" and not ticket.resuelto_en:
            ticket.resuelto_en = ahora
        if nuevo == "CERRADO":
            ticket.cerrado_en = ahora
        elif nuevo in ("NUEVO", "EN_PROGRESO"):
            ticket.resuelto_en = None
            ticket.cerrado_en = None
        ticket.estado = nuevo

    # Punto medio entre sus vecinas: así insertar no obliga a renumerar la
    # columna entera en cada arrastre.
    ant, sig = data.orden_anterior, data.orden_siguiente
    if ant is not None and sig is not None:
        ticket.orden = (ant + sig) / 2
    elif ant is not None:
        ticket.orden = ant + 1
    elif sig is not None:
        ticket.orden = sig - 1

    ticket.ultima_actividad = ahora
    await db.commit(); await db.refresh(ticket)
    return TarjetaTicket.model_validate(ticket)


class CambioAgil(BaseModel):
    tipo_trabajo: Optional[str] = None
    puntos: Optional[int] = None
    sprint_id: Optional[int] = None
    epica_id: Optional[int] = None
    etiquetas: Optional[List[str]] = None


@router.put("/agil/tickets/{ticket_id}", response_model=TarjetaTicket)
async def actualizar(
    ticket_id: int, data: CambioAgil, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    """Tipo, estimación, sprint, épica y etiquetas."""
    ticket = await db.get(SoporteTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Esa solicitud no existe")
    cambios = data.model_dump(exclude_unset=True)
    autor = _autor(request)

    if "tipo_trabajo" in cambios and cambios["tipo_trabajo"]:
        valor = cambios["tipo_trabajo"].upper()
        if valor not in TIPOS_TRABAJO:
            raise HTTPException(400, f"Tipo inválido. Use uno de: {', '.join(TIPOS_TRABAJO)}.")
        cambios["tipo_trabajo"] = valor

    if "puntos" in cambios and cambios["puntos"] is not None:
        if cambios["puntos"] not in PUNTOS:
            raise HTTPException(
                400,
                f"La estimación usa la escala {', '.join(str(p) for p in PUNTOS)}. "
                "Es imprecisa a propósito: obliga a comparar tamaños en vez de "
                "fingir que se puede estimar en horas.",
            )

    if cambios.get("sprint_id"):
        sprint = await db.get(SoporteSprint, cambios["sprint_id"])
        if not sprint:
            raise HTTPException(404, "Ese sprint no existe")
        if sprint.estado == "CERRADO":
            raise HTTPException(
                409, "Ese sprint ya está cerrado: no se le puede agregar trabajo.")

    for campo, valor in cambios.items():
        anterior = getattr(ticket, campo)
        if anterior != valor:
            _anotar(db, ticket.id, campo, anterior, valor, autor)
        setattr(ticket, campo, valor)

    ticket.ultima_actividad = datetime.utcnow()
    await db.commit(); await db.refresh(ticket)
    return TarjetaTicket.model_validate(ticket)


# ─── Backlog ──────────────────────────────────────────────────────────────────

@router.get("/agil/backlog", response_model=List[TarjetaTicket])
async def backlog(
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    """Lo que no está en ningún sprint y sigue abierto, en orden de prioridad."""
    r = await db.execute(
        select(SoporteTicket)
        .where(SoporteTicket.sprint_id.is_(None),
               SoporteTicket.estado.notin_(("RESUELTO", "CERRADO")))
        .order_by(SoporteTicket.orden, SoporteTicket.id.desc()))
    return [TarjetaTicket.model_validate(t) for t in r.scalars().all()]


class Reordenar(BaseModel):
    """Los ids en el orden en que quedan. Se manda la lista completa y no
    posiciones sueltas: así el servidor no tiene que adivinar el resultado."""
    ids: List[int]


@router.put("/agil/backlog/orden", response_model=List[TarjetaTicket])
async def reordenar(
    data: Reordenar,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    r = await db.execute(select(SoporteTicket).where(SoporteTicket.id.in_(data.ids)))
    por_id = {t.id: t for t in r.scalars().all()}
    for posicion, tid in enumerate(data.ids):
        if tid in por_id:
            por_id[tid].orden = float(posicion)
    await db.commit()
    return await backlog(db, None)  # type: ignore[arg-type]


# ─── Sprints ──────────────────────────────────────────────────────────────────

async def _con_calculos(db: AsyncSession, sprint: SoporteSprint) -> Sprint:
    ficha = Sprint.model_validate(sprint)
    r = await db.execute(select(SoporteTicket).where(SoporteTicket.sprint_id == sprint.id))
    tickets = list(r.scalars().all())
    ficha.total_solicitudes = len(tickets)
    ficha.puntos_en_curso = sum(t.puntos or 0 for t in tickets)
    ficha.puntos_hechos = sum(
        t.puntos or 0 for t in tickets if t.estado in ("RESUELTO", "CERRADO"))
    return ficha


@router.get("/agil/sprints", response_model=List[Sprint])
async def listar_sprints(
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    r = await db.execute(select(SoporteSprint).order_by(SoporteSprint.id.desc()))
    return [await _con_calculos(db, s) for s in r.scalars().all()]


@router.post("/agil/sprints", response_model=Sprint, status_code=201)
async def crear_sprint(
    data: Sprint,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    if not (data.nombre or "").strip():
        raise HTTPException(400, "El sprint necesita un nombre")
    if data.inicio and data.fin and data.fin < data.inicio:
        raise HTTPException(400, "El sprint termina antes de empezar: revise las fechas.")
    sprint = SoporteSprint(
        nombre=data.nombre.strip(), objetivo=data.objetivo,
        inicio=data.inicio, fin=data.fin, estado="PLANEADO")
    db.add(sprint); await db.commit(); await db.refresh(sprint)
    return await _con_calculos(db, sprint)


@router.post("/agil/sprints/{sprint_id}/activar", response_model=Sprint)
async def activar(
    sprint_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    """Arranca la iteración y congela lo comprometido."""
    sprint = await db.get(SoporteSprint, sprint_id)
    if not sprint:
        raise HTTPException(404, "Ese sprint no existe")
    if sprint.estado == "CERRADO":
        raise HTTPException(409, "Ese sprint ya se cerró")

    otro = (await db.execute(select(SoporteSprint).where(
        SoporteSprint.estado == "ACTIVO",
        SoporteSprint.id != sprint_id))).scalar_one_or_none()
    if otro:
        raise HTTPException(
            409,
            f"«{otro.nombre}» sigue activo. Ciérrelo primero: con dos iteraciones a la "
            "vez, «en qué estamos trabajando» deja de tener una respuesta.",
        )

    tickets = list((await db.execute(
        select(SoporteTicket).where(SoporteTicket.sprint_id == sprint_id))).scalars().all())
    if not tickets:
        raise HTTPException(
            409, "El sprint está vacío. Arrástrele solicitudes del backlog antes de activarlo.")
    sin_estimar = [t.numero for t in tickets if t.puntos is None]
    if sin_estimar:
        raise HTTPException(
            409,
            f"Hay {len(sin_estimar)} solicitudes sin estimar ({', '.join(sin_estimar[:5])}"
            f"{'…' if len(sin_estimar) > 5 else ''}). Sin estimación no hay compromiso "
            "que medir ni velocidad que comparar.",
        )

    sprint.estado = "ACTIVO"
    # Se congela acá: si se recalculara al cerrar, agregar trabajo a mitad de
    # sprint haría parecer que siempre estuvo comprometido.
    sprint.puntos_comprometidos = sum(t.puntos or 0 for t in tickets)
    await db.commit(); await db.refresh(sprint)
    return await _con_calculos(db, sprint)


@router.post("/agil/sprints/{sprint_id}/cerrar", response_model=Sprint)
async def cerrar(
    sprint_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    """Cierra la iteración: lo terminado queda, lo demás vuelve al backlog.

    Arrastrar lo no terminado al siguiente sprint escondería que no cupo, y la
    velocidad dejaría de significar algo.
    """
    sprint = await db.get(SoporteSprint, sprint_id)
    if not sprint:
        raise HTTPException(404, "Ese sprint no existe")
    if sprint.estado == "CERRADO":
        raise HTTPException(409, "Ese sprint ya está cerrado")

    autor = _autor(request)
    tickets = list((await db.execute(
        select(SoporteTicket).where(SoporteTicket.sprint_id == sprint_id))).scalars().all())

    completados = [t for t in tickets if t.estado in ("RESUELTO", "CERRADO")]
    sprint.puntos_completados = sum(t.puntos or 0 for t in completados)
    for t in tickets:
        if t not in completados:
            _anotar(db, t.id, "sprint_id", sprint_id, None, autor)
            t.sprint_id = None
    sprint.estado = "CERRADO"
    sprint.cerrado_en = datetime.utcnow()
    await db.commit(); await db.refresh(sprint)
    return await _con_calculos(db, sprint)


# ─── Épicas ───────────────────────────────────────────────────────────────────

@router.get("/agil/epicas", response_model=List[Epica])
async def listar_epicas(
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    epicas = list((await db.execute(
        select(SoporteEpica).order_by(SoporteEpica.nombre))).scalars().all())
    if not epicas:
        return []
    conteos = dict((await db.execute(
        select(SoporteTicket.epica_id, func.count())
        .where(SoporteTicket.epica_id.in_([e.id for e in epicas]))
        .group_by(SoporteTicket.epica_id))).all())
    puntos = dict((await db.execute(
        select(SoporteTicket.epica_id, func.sum(SoporteTicket.puntos))
        .where(SoporteTicket.epica_id.in_([e.id for e in epicas]))
        .group_by(SoporteTicket.epica_id))).all())
    salida = []
    for e in epicas:
        ficha = Epica.model_validate(e)
        ficha.solicitudes = conteos.get(e.id, 0)
        ficha.puntos = int(puntos.get(e.id) or 0)
        salida.append(ficha)
    return salida


@router.post("/agil/epicas", response_model=Epica, status_code=201)
async def crear_epica(
    data: Epica,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    if not (data.nombre or "").strip():
        raise HTTPException(400, "La épica necesita un nombre")
    epica = SoporteEpica(
        nombre=data.nombre.strip(), descripcion=data.descripcion, color=data.color)
    db.add(epica); await db.commit(); await db.refresh(epica)
    return Epica.model_validate(epica)


# ─── Columnas del tablero ─────────────────────────────────────────────────────

class CambioColumna(BaseModel):
    titulo: Optional[str] = None
    limite_wip: Optional[int] = None


@router.put("/agil/columnas/{estado}", response_model=ColumnaTablero)
async def configurar_columna(
    estado: str, data: CambioColumna,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    await _columnas(db)
    columna = (await db.execute(select(SoporteColumna).where(
        SoporteColumna.estado == estado.upper()))).scalar_one_or_none()
    if not columna:
        raise HTTPException(404, "Esa columna no existe")
    cambios = data.model_dump(exclude_unset=True)
    if cambios.get("limite_wip") is not None and cambios["limite_wip"] < 1:
        raise HTTPException(
            400, "El límite debe ser al menos 1. Para quitarlo, déjelo vacío.")
    for campo, valor in cambios.items():
        setattr(columna, campo, valor)
    await db.commit(); await db.refresh(columna)
    return ColumnaTablero(
        estado=columna.estado, titulo=columna.titulo, orden=columna.orden or 0,
        limite_wip=columna.limite_wip)


# ─── Métricas ─────────────────────────────────────────────────────────────────

class PuntoBurndown(BaseModel):
    fecha: date
    ideal: float
    real: Optional[float] = None


class Velocidad(BaseModel):
    sprint: str
    comprometidos: int
    completados: int


class Metricas(BaseModel):
    burndown: List[PuntoBurndown] = []
    velocidad: List[Velocidad] = []
    # En días. El de ciclo es lo que el equipo puede mejorar; el de entrega
    # incluye la espera en el backlog, que depende de la priorización.
    tiempo_ciclo_promedio: Optional[float] = None
    tiempo_entrega_promedio: Optional[float] = None
    por_tipo: Dict[str, int] = {}


@router.get("/agil/metricas", response_model=Metricas)
async def metricas(
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    m = Metricas()

    cerrados = list((await db.execute(
        select(SoporteSprint).where(SoporteSprint.estado == "CERRADO")
        .order_by(SoporteSprint.cerrado_en).limit(12))).scalars().all())
    m.velocidad = [
        Velocidad(sprint=s.nombre,
                  comprometidos=s.puntos_comprometidos or 0,
                  completados=s.puntos_completados or 0)
        for s in cerrados
    ]

    activo = (await db.execute(
        select(SoporteSprint).where(SoporteSprint.estado == "ACTIVO"))).scalar_one_or_none()
    if activo and activo.inicio and activo.fin:
        tickets = list((await db.execute(
            select(SoporteTicket).where(SoporteTicket.sprint_id == activo.id))).scalars().all())
        total = sum(t.puntos or 0 for t in tickets)
        dias = (activo.fin - activo.inicio).days or 1

        # Cuándo se terminó cada solicitud, para restar en el día correcto.
        # Se lee de los eventos y no del estado actual: sobre el estado, el
        # gráfico mostraría el pasado como si siempre hubiera sido así.
        eventos = list((await db.execute(
            select(SoporteEvento).where(
                SoporteEvento.ticket_id.in_([t.id for t in tickets] or [0]),
                SoporteEvento.campo == "estado",
                SoporteEvento.nuevo.in_(("RESUELTO", "CERRADO")))
            .order_by(SoporteEvento.fecha))).scalars().all())
        completado_en: Dict[int, date] = {}
        for e in eventos:
            completado_en.setdefault(e.ticket_id, e.fecha.date())
        puntos_por_ticket = {t.id: (t.puntos or 0) for t in tickets}

        hoy = date.today()
        for i in range(dias + 1):
            dia = activo.inicio + timedelta(days=i)
            ideal = total - (total / dias) * i
            punto = PuntoBurndown(fecha=dia, ideal=round(max(ideal, 0), 1))
            # La línea real solo se dibuja hasta hoy: prolongarla al futuro
            # sugeriría que ya sabemos qué va a pasar.
            if dia <= hoy:
                hechos = sum(p for tid, p in puntos_por_ticket.items()
                             if tid in completado_en and completado_en[tid] <= dia)
                punto.real = float(total - hechos)
            m.burndown.append(punto)

    # Tiempos, sobre lo resuelto en los últimos 90 días.
    desde = datetime.utcnow() - timedelta(days=90)
    resueltos = list((await db.execute(
        select(SoporteTicket).where(SoporteTicket.resuelto_en.isnot(None),
                                    SoporteTicket.resuelto_en >= desde))).scalars().all())
    ciclos, entregas = [], []
    for t in resueltos:
        fin = _sin_zona(t.resuelto_en)
        inicio = _sin_zona(t.iniciado_en)
        creado = _sin_zona(t.created_at)
        if fin and inicio and fin > inicio:
            ciclos.append((fin - inicio).total_seconds() / 86400)
        if fin and creado and fin > creado:
            entregas.append((fin - creado).total_seconds() / 86400)
    if ciclos:
        m.tiempo_ciclo_promedio = round(sum(ciclos) / len(ciclos), 1)
    if entregas:
        m.tiempo_entrega_promedio = round(sum(entregas) / len(entregas), 1)

    abiertos = list((await db.execute(
        select(SoporteTicket).where(SoporteTicket.estado != "CERRADO"))).scalars().all())
    for t in abiertos:
        clave = t.tipo_trabajo or "SIN_CLASIFICAR"
        m.por_tipo[clave] = m.por_tipo.get(clave, 0) + 1
    return m
