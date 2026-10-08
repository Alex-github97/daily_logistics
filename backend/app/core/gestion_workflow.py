"""
El motor de transiciones.

Los estados y las transiciones son datos: cambiar cómo trabaja un equipo es
configurar, no desplegar. Lo que no puede ser un dato es el **código** que
decide, así que una transición no guarda una expresión ni un fragmento de script
sino una lista de claves:

    [{"clave": "rol_consola", "config": {"roles": ["SOPORTE"]}}]

Cada clave resuelve una función registrada acá. Agregar una regla nueva es
registrar una función; usarla es configurar. Guardar código en la base sería
darle a quien configura un flujo la capacidad de ejecutar lo que quiera dentro
del proceso del servidor, que es exactamente el agujero que el módulo existe para
no abrir.

Tres clases de regla, que corren en este orden:

  1. **Condiciones** — ¿esta persona puede hacer este movimiento? Si no se
     cumplen, la transición ni siquiera se ofrece en la pantalla.
  2. **Validaciones** — ¿la incidencia está lista para moverse? Sí se ofrece, y
     falla explicando qué falta. La diferencia importa: una transición que
     desaparece sin decir por qué se lee como un error de la herramienta.
  3. **Acciones** — qué pasa después.

El límite de trabajo en curso NO es una condición configurable: vive en el estado
y se comprueba siempre. Si fuera opcional, alguien lo dejaría sin marcar y el
límite volvería a ser decorativo.
"""
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permisos_consola import Miembro
from app.infrastructure.models.gestion import (
    GPEstado, GPIncidencia, GPTransicion, GPProyectoMiembro,
)


class Contexto:
    """Todo lo que una regla puede necesitar para decidir."""

    def __init__(self, db: AsyncSession, incidencia: GPIncidencia,
                 quien: Miembro, destino: GPEstado):
        self.db = db
        self.incidencia = incidencia
        self.quien = quien
        self.destino = destino


# ─── Condiciones ──────────────────────────────────────────────────────────────
#
# Devuelven None si se cumplen, o el motivo si no. El motivo se le muestra a
# quien lo intenta, así que dice qué le falta y no solo que no puede.

async def _rol_consola(ctx: Contexto, config: dict) -> Optional[str]:
    permitidos = {str(r).upper() for r in (config.get("roles") or [])}
    if not permitidos or ctx.quien.rol.upper() in permitidos:
        return None
    return f"solo pueden hacerlo: {', '.join(sorted(permitidos))}"


async def _es_asignado(ctx: Contexto, _config: dict) -> Optional[str]:
    if ctx.incidencia.asignado == ctx.quien.usuario:
        return None
    if not ctx.incidencia.asignado:
        return "primero hay que asignarla"
    return f"solo puede hacerlo quien la tiene asignada ({ctx.incidencia.asignado})"


async def _miembro_proyecto(ctx: Contexto, _config: dict) -> Optional[str]:
    fila = (await ctx.db.execute(select(GPProyectoMiembro.id).where(
        GPProyectoMiembro.proyecto_id == ctx.incidencia.proyecto_id,
        GPProyectoMiembro.usuario == ctx.quien.usuario))).first()
    return None if fila else "hay que ser miembro del proyecto"


CONDICIONES: Dict[str, Callable] = {
    "rol_consola": _rol_consola,
    "es_asignado": _es_asignado,
    "miembro_proyecto": _miembro_proyecto,
}


# ─── Validaciones ─────────────────────────────────────────────────────────────

async def _exige_asignado(ctx: Contexto, _config: dict) -> Optional[str]:
    if ctx.incidencia.asignado:
        return None
    return "hay que asignarla a alguien antes de moverla ahí"


async def _exige_estimacion(ctx: Contexto, _config: dict) -> Optional[str]:
    # Vacío es distinto de cero: cero es una estimación válida —algo que ya
    # estaba hecho— y vacío es que nadie la miró.
    if ctx.incidencia.puntos is not None:
        return None
    return "hay que estimarla en puntos antes de moverla ahí"


async def _exige_campos(ctx: Contexto, config: dict) -> Optional[str]:
    faltan = [
        c for c in (config.get("claves") or [])
        if not (ctx.incidencia.campos or {}).get(c)
    ]
    if not faltan:
        return None
    return f"faltan por llenar: {', '.join(faltan)}"


async def _exige_resolucion(ctx: Contexto, _config: dict) -> Optional[str]:
    if (ctx.incidencia.campos or {}).get("resolucion"):
        return None
    return "hay que indicar cómo se resolvió"


VALIDACIONES: Dict[str, Callable] = {
    "exige_asignado": _exige_asignado,
    "exige_estimacion": _exige_estimacion,
    "exige_campos": _exige_campos,
    "exige_resolucion": _exige_resolucion,
}


# ─── Acciones ─────────────────────────────────────────────────────────────────
#
# Modifican la incidencia y devuelven qué cambiaron, para que quede en el
# historial. Una acción que cambia algo sin dejar rastro convierte el historial
# en una media verdad.

async def _sellar_iniciado(ctx: Contexto, _config: dict) -> List[Tuple[str, object, object]]:
    if ctx.incidencia.iniciado:
        # No se vuelve a sellar: si al devolver y reempezar se pisara la marca,
        # el tiempo de ciclo mediría solo la última vuelta y escondería las
        # anteriores, que son justo las que interesan.
        return []
    antes = ctx.incidencia.iniciado
    ctx.incidencia.iniciado = datetime.now(timezone.utc)
    return [("iniciado", antes, ctx.incidencia.iniciado)]


async def _sellar_resuelto(ctx: Contexto, _config: dict) -> List[Tuple[str, object, object]]:
    antes = ctx.incidencia.resuelto
    ctx.incidencia.resuelto = datetime.now(timezone.utc)
    return [("resuelto", antes, ctx.incidencia.resuelto)]


async def _limpiar_resuelto(ctx: Contexto, _config: dict) -> List[Tuple[str, object, object]]:
    if ctx.incidencia.resuelto is None:
        return []
    antes = ctx.incidencia.resuelto
    ctx.incidencia.resuelto = None
    return [("resuelto", antes, None)]


async def _asignar_a_quien_mueve(ctx: Contexto, _config: dict) -> List[Tuple[str, object, object]]:
    if ctx.incidencia.asignado == ctx.quien.usuario:
        return []
    antes = ctx.incidencia.asignado
    ctx.incidencia.asignado = ctx.quien.usuario
    return [("asignado", antes, ctx.quien.usuario)]


async def _quitar_asignado(ctx: Contexto, _config: dict) -> List[Tuple[str, object, object]]:
    if not ctx.incidencia.asignado:
        return []
    antes = ctx.incidencia.asignado
    ctx.incidencia.asignado = None
    return [("asignado", antes, None)]


async def _sacar_del_sprint(ctx: Contexto, _config: dict) -> List[Tuple[str, object, object]]:
    if ctx.incidencia.sprint_id is None:
        return []
    antes = ctx.incidencia.sprint_id
    ctx.incidencia.sprint_id = None
    return [("sprint", antes, None)]


ACCIONES: Dict[str, Callable] = {
    "sellar_iniciado": _sellar_iniciado,
    "sellar_resuelto": _sellar_resuelto,
    "limpiar_resuelto": _limpiar_resuelto,
    "asignar_a_quien_mueve": _asignar_a_quien_mueve,
    "quitar_asignado": _quitar_asignado,
    "sacar_del_sprint": _sacar_del_sprint,
}


# ─── El motor ─────────────────────────────────────────────────────────────────

async def transiciones_de(db: AsyncSession, workflow_id: int,
                          estado_id: int) -> List[GPTransicion]:
    """Las transiciones declaradas desde ese estado, más las de cualquier origen.

    Las de origen vacío existen para no tener que declarar un «Cancelar» por cada
    estado del flujo.
    """
    r = await db.execute(
        select(GPTransicion).where(
            GPTransicion.workflow_id == workflow_id,
            (GPTransicion.origen_id == estado_id) | (GPTransicion.origen_id.is_(None)),
        ).order_by(GPTransicion.orden))
    return list(r.scalars().all())


async def hay_cupo(db: AsyncSession, destino: GPEstado, proyecto_id: int,
                   incidencia_id: Optional[int] = None) -> Optional[str]:
    """El límite de trabajo en curso del estado de destino.

    Se cuenta dentro del proyecto y no en toda la base: el límite es del equipo
    que trabaja ese proyecto. Se excluye la propia incidencia porque mover algo
    que ya está en la columna —reordenarlo— no debería chocar contra el límite.
    """
    if not destino.limite_wip:
        return None
    consulta = select(func.count()).select_from(GPIncidencia).where(
        GPIncidencia.estado_id == destino.id,
        GPIncidencia.proyecto_id == proyecto_id)
    if incidencia_id is not None:
        consulta = consulta.where(GPIncidencia.id != incidencia_id)
    cuantas = (await db.execute(consulta)).scalar() or 0
    if cuantas < destino.limite_wip:
        return None
    return (f"«{destino.nombre}» ya tiene {cuantas} y su límite es "
            f"{destino.limite_wip}. Termine algo antes de empezar otra cosa.")


async def evaluar(reglas: List[dict], registro: Dict[str, Callable],
                  ctx: Contexto) -> List[str]:
    """Corre un juego de reglas y devuelve los motivos por los que no pasa.

    Una regla cuya clave no esté registrada **bloquea**. Ignorarla sería peor:
    una condición mal escrita —un cambio de nombre, un error de tipeo— dejaría la
    transición abierta a todo el mundo justo cuando alguien creía haberla
    restringido.
    """
    motivos: List[str] = []
    for regla in reglas or []:
        clave = (regla or {}).get("clave")
        funcion = registro.get(clave)
        if funcion is None:
            motivos.append(
                f"la regla «{clave}» no existe en el servidor; revísela en la "
                f"configuración del flujo")
            continue
        motivo = await funcion(ctx, (regla or {}).get("config") or {})
        if motivo:
            motivos.append(motivo)
    return motivos


async def disponibles(db: AsyncSession, incidencia: GPIncidencia,
                      workflow_id: int, quien: Miembro) -> List[dict]:
    """Las transiciones que esta persona puede usar ahora mismo.

    Las que no pasan las condiciones no se devuelven; las que fallan una
    validación sí, marcadas con lo que falta. Esconder una transición porque
    falta llenar un campo deja a la gente buscando un botón que nadie quitó.
    """
    candidatas = await transiciones_de(db, workflow_id, incidencia.estado_id)
    if not candidatas:
        return []

    destinos = {
        e.id: e for e in (await db.execute(select(GPEstado).where(
            GPEstado.id.in_([t.destino_id for t in candidatas])))).scalars().all()
    }

    salida: List[dict] = []
    for t in candidatas:
        destino = destinos.get(t.destino_id)
        if destino is None or destino.id == incidencia.estado_id:
            continue
        ctx = Contexto(db, incidencia, quien, destino)

        if await evaluar(t.condiciones or [], CONDICIONES, ctx):
            continue

        impedimentos = await evaluar(t.validaciones or [], VALIDACIONES, ctx)
        tope = await hay_cupo(db, destino, incidencia.proyecto_id, incidencia.id)
        if tope:
            impedimentos.append(tope)

        salida.append({
            "id": t.id,
            "nombre": t.nombre,
            "destino_id": destino.id,
            "destino": destino.nombre,
            "categoria": destino.categoria,
            "color": destino.color,
            "lista": not impedimentos,
            "impedimentos": impedimentos,
        })
    return salida


async def aplicar(db: AsyncSession, incidencia: GPIncidencia, transicion_id: int,
                  workflow_id: int, quien: Miembro) -> List[Tuple[str, object, object]]:
    """Ejecuta una transición y devuelve todo lo que cambió.

    Devolver los cambios en vez de escribir el historial acá deja al motor sin
    saber nada del historial, y permite que quien llama registre en una sola
    tanda lo de la transición y lo que él mismo haya cambiado.
    """
    transicion = (await db.execute(select(GPTransicion).where(
        GPTransicion.id == transicion_id,
        GPTransicion.workflow_id == workflow_id))).scalar_one_or_none()
    if transicion is None:
        raise HTTPException(404, "Esa transición no existe en este flujo.")

    if transicion.origen_id is not None and transicion.origen_id != incidencia.estado_id:
        raise HTTPException(
            409,
            "La incidencia ya no está en el estado desde el que sale esa "
            "transición. Vuelva a cargarla: alguien más la movió.")

    destino = (await db.execute(select(GPEstado).where(
        GPEstado.id == transicion.destino_id))).scalar_one_or_none()
    if destino is None:
        raise HTTPException(409, "La transición apunta a un estado que ya no existe.")

    ctx = Contexto(db, incidencia, quien, destino)

    motivos = await evaluar(transicion.condiciones or [], CONDICIONES, ctx)
    if motivos:
        raise HTTPException(403, f"No puede mover esta incidencia: {'; '.join(motivos)}.")

    motivos = await evaluar(transicion.validaciones or [], VALIDACIONES, ctx)
    tope = await hay_cupo(db, destino, incidencia.proyecto_id, incidencia.id)
    if tope:
        motivos.append(tope)
    if motivos:
        raise HTTPException(409, f"Todavía no puede pasar a «{destino.nombre}»: "
                                 f"{'; '.join(motivos)}.")

    cambios: List[Tuple[str, object, object]] = []
    anterior = (await db.execute(select(GPEstado).where(
        GPEstado.id == incidencia.estado_id))).scalar_one_or_none()
    incidencia.estado_id = destino.id
    cambios.append(("estado", anterior.nombre if anterior else None, destino.nombre))

    for accion in transicion.acciones or []:
        clave = (accion or {}).get("clave")
        funcion = ACCIONES.get(clave)
        if funcion is None:
            # A diferencia de las condiciones, una acción desconocida no bloquea:
            # el movimiento ya fue autorizado y negarlo por un efecto secundario
            # mal configurado dejaría la incidencia atascada sin salida.
            cambios.append(("aviso", None, f"la acción «{clave}» no existe en el servidor"))
            continue
        cambios.extend(await funcion(ctx, (accion or {}).get("config") or {}))

    return cambios


def catalogo() -> dict:
    """Lo que la pantalla de configuración puede ofrecer al armar un flujo.

    Sale del mismo registro que ejecuta el motor: una lista escrita a mano en el
    frontend acabaría ofreciendo reglas que el servidor no conoce, y esas
    bloquean la transición.
    """
    return {
        "condiciones": [
            {"clave": "rol_consola", "nombre": "Solo ciertos roles",
             "config": {"roles": []}},
            {"clave": "es_asignado", "nombre": "Solo quien la tiene asignada",
             "config": {}},
            {"clave": "miembro_proyecto", "nombre": "Solo miembros del proyecto",
             "config": {}},
        ],
        "validaciones": [
            {"clave": "exige_asignado", "nombre": "Exigir responsable", "config": {}},
            {"clave": "exige_estimacion", "nombre": "Exigir estimación", "config": {}},
            {"clave": "exige_campos", "nombre": "Exigir ciertos campos",
             "config": {"claves": []}},
            {"clave": "exige_resolucion", "nombre": "Exigir cómo se resolvió",
             "config": {}},
        ],
        "acciones": [
            {"clave": "sellar_iniciado", "nombre": "Marcar cuándo empezó", "config": {}},
            {"clave": "sellar_resuelto", "nombre": "Marcar cuándo se resolvió", "config": {}},
            {"clave": "limpiar_resuelto", "nombre": "Borrar la marca de resuelta", "config": {}},
            {"clave": "asignar_a_quien_mueve", "nombre": "Asignar a quien la mueve", "config": {}},
            {"clave": "quitar_asignado", "nombre": "Quitar el responsable", "config": {}},
            {"clave": "sacar_del_sprint", "nombre": "Sacarla del sprint", "config": {}},
        ],
    }
