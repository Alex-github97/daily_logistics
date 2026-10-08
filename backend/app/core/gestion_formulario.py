"""
El motor del formulario: una sola configuración gobierna qué se pide y qué vale.

El problema que resuelve: sin esto, la pantalla de alta tiene la mitad de sus
controles cableados —título, responsable, prioridad— y la otra mitad dinámica, y
además cada tipo de incidencia necesita su propio `if`. Con veinte tipos eso son
veinte ramas repartidas por tres componentes, y agregar un campo obliga a
desplegar.

La idea es que **los campos nativos y los configurables vivan en el mismo
registro**. Un campo declara dónde se guarda su valor:

  · `COLUMNA` → en una columna de `gp_incidencia`. Solo los del sistema, que
    existían antes que este registro.
  · `JSONB`   → en `gp_incidencia.campos`. Todo lo que cree un administrador.

Desde fuera son iguales: los dos se describen, se validan y se dibujan igual, y
el administrador puede poner un campo suyo por encima del título si quiere. Esa
uniformidad es lo que permite que el formulario se arme entero desde la base.

Y declara de dónde salen sus opciones:

  · `PROPIO`  → de `gp_campo_opcion`, la lista que alguien escribió.
  · `ENTIDAD` → de una tabla: usuarios, sprints, épicas, versiones, componentes.

Lo segundo es lo que evita el error clásico de tener un catálogo «Sprint»
paralelo a la tabla de sprints, que se desincroniza el primer día. Las opciones
se consultan en el momento y se filtran por el proyecto en curso, así que un
sprint nuevo aparece en el formulario sin que nadie configure nada.

**La validación es la del servidor.** La misma definición alimenta el formulario,
así que la pantalla y el servidor no pueden discrepar; pero quien arme la
petición a mano se topa con lo mismo.
"""
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import gestion_campos
from app.infrastructure.models.gestion import (
    SECCIONES, TIPOS_DE_ENTIDAD, TIPOS_MULTIPLES,
    GPCampo, GPCampoOpcion, GPComponente, GPEsquemaCampo, GPEstado,
    GPIncidencia, GPPrioridad, GPProyecto, GPSprint, GPTipoIncidencia,
    GPVersion,
)
from app.infrastructure.models.plataforma import PlataformaMiembro


class CampoDelFormulario:
    """Un campo tal como aplica a un proyecto y un tipo concretos."""

    __slots__ = ("campo", "obligatorio", "solo_lectura", "visible", "orden", "opciones")

    def __init__(self, campo: GPCampo, obligatorio: bool, solo_lectura: bool,
                 visible: bool, orden: int):
        self.campo = campo
        self.obligatorio = obligatorio
        self.solo_lectura = solo_lectura
        self.visible = visible
        self.orden = orden
        self.opciones: List[dict] = []


# ─── Qué campos aplican ───────────────────────────────────────────────────────

async def campos_del(db: AsyncSession, proyecto_id: Optional[int],
                     tipo_id: Optional[int]) -> List[CampoDelFormulario]:
    """Los campos que aplican, resolviendo de lo general a lo específico.

    Se recogen las cuatro combinaciones —global, por proyecto, por tipo, y por
    los dos— y para cada campo se queda la más específica. Sin esta precedencia
    habría que repetir la configuración común en cada proyecto, y la primera vez
    que alguien la cambiara quedaría desincronizada en los demás.
    """
    # `IN (:proyecto, NULL)` NO sirve: en SQL nada casa con NULL, así que las
    # reglas globales quedarían fuera y ningún campo aplicaría a nada.
    ambito = (
        GPEsquemaCampo.proyecto_id.is_(None) if proyecto_id is None
        else or_(GPEsquemaCampo.proyecto_id == proyecto_id,
                 GPEsquemaCampo.proyecto_id.is_(None))
    )
    reglas = [
        e for e in (await db.execute(select(GPEsquemaCampo).where(ambito))).scalars().all()
        if e.tipo_id is None or e.tipo_id == tipo_id
    ]
    if not reglas:
        return []

    def peso(e: GPEsquemaCampo) -> int:
        return (1 if e.proyecto_id is not None else 0) + \
               (2 if e.tipo_id is not None else 0)

    mejor: Dict[int, GPEsquemaCampo] = {}
    for regla in reglas:
        actual = mejor.get(regla.campo_id)
        if actual is None or peso(regla) > peso(actual):
            mejor[regla.campo_id] = regla

    campos = {
        c.id: c for c in (await db.execute(select(GPCampo).where(
            GPCampo.id.in_(list(mejor)), GPCampo.archivado.is_(False)
        ))).scalars().all()
    }
    if not campos:
        return []

    salida = [
        CampoDelFormulario(
            campos[cid], regla.obligatorio, regla.solo_lectura,
            regla.visible, regla.orden)
        for cid, regla in mejor.items() if cid in campos
    ]
    # Primero por sección —en el orden en que se muestran— y dentro de ella por
    # el orden que diga la regla.
    posicion = {clave: i for i, (clave, _) in enumerate(SECCIONES)}
    salida.sort(key=lambda c: (
        posicion.get(c.campo.seccion, 99), c.orden, c.campo.orden, c.campo.nombre))
    return salida


# ─── De dónde salen las opciones ──────────────────────────────────────────────
#
# Cada entrada resuelve una entidad a una lista de `{valor, etiqueta, pista}`.
# Es una lista CERRADA: un campo no puede nombrar una tabla cualquiera, igual que
# el motor de filtros no puede nombrar una columna cualquiera.

async def _usuarios(db: AsyncSession, _p: Optional[int], usuario: str) -> List[dict]:
    """A quién se le puede asignar trabajo: el equipo de la consola.

    Quien consulta entra siempre, aunque no esté en la tabla. Mientras el equipo
    no se haya formalizado esa tabla está vacía, y devolver una lista vacía deja
    el selector de responsable sin una sola opción —ni siquiera uno mismo—, que
    es exactamente como se ve un campo roto.
    """
    r = await db.execute(select(PlataformaMiembro).where(
        PlataformaMiembro.activo.is_(True)
    ).order_by(PlataformaMiembro.nombre, PlataformaMiembro.usuario))
    equipo = [
        {"valor": m.usuario, "etiqueta": m.nombre or m.usuario, "pista": m.rol}
        for m in r.scalars().all()
    ]
    if usuario and not any(m["valor"] == usuario for m in equipo):
        equipo.insert(0, {"valor": usuario, "etiqueta": usuario, "pista": "usted"})
    return equipo


async def _proyectos(db: AsyncSession, _p: Optional[int], _usuario: str) -> List[dict]:
    r = await db.execute(select(GPProyecto).where(
        GPProyecto.archivado.is_(False)).order_by(GPProyecto.nombre))
    return [{"valor": str(x.id), "etiqueta": x.nombre, "pista": x.clave}
            for x in r.scalars().all()]


async def _tipos(db: AsyncSession, proyecto_id: Optional[int], _usuario: str) -> List[dict]:
    ambito = (
        GPTipoIncidencia.proyecto_id.is_(None) if proyecto_id is None
        else or_(GPTipoIncidencia.proyecto_id == proyecto_id,
                 GPTipoIncidencia.proyecto_id.is_(None))
    )
    r = await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.archivado.is_(False), ambito
    ).order_by(GPTipoIncidencia.orden))
    return [{"valor": str(x.id), "etiqueta": x.nombre, "pista": x.icono or x.nivel}
            for x in r.scalars().all()]


async def _prioridades(db: AsyncSession, _p: Optional[int], _usuario: str) -> List[dict]:
    r = await db.execute(select(GPPrioridad).order_by(GPPrioridad.orden))
    return [{"valor": str(x.id), "etiqueta": x.nombre, "color": x.color}
            for x in r.scalars().all()]


async def _estados(db: AsyncSession, proyecto_id: Optional[int], _usuario: str) -> List[dict]:
    consulta = select(GPEstado).order_by(GPEstado.orden)
    if proyecto_id is not None:
        wf = (await db.execute(select(GPProyecto.workflow_id).where(
            GPProyecto.id == proyecto_id))).scalar()
        if wf:
            consulta = consulta.where(GPEstado.workflow_id == wf)
    r = await db.execute(consulta)
    return [{"valor": str(x.id), "etiqueta": x.nombre, "pista": x.categoria,
             "color": x.color} for x in r.scalars().all()]


async def _sprints(db: AsyncSession, proyecto_id: Optional[int], _usuario: str) -> List[dict]:
    if proyecto_id is None:
        return []
    r = await db.execute(select(GPSprint).where(
        GPSprint.proyecto_id == proyecto_id, GPSprint.estado != "CERRADO"
    ).order_by(GPSprint.inicio.desc().nullslast()))
    return [{"valor": str(x.id), "etiqueta": x.nombre,
             "pista": "en curso" if x.estado == "ACTIVO" else "planeado"}
            for x in r.scalars().all()]


async def _epicas(db: AsyncSession, proyecto_id: Optional[int], _usuario: str) -> List[dict]:
    """Las épicas son incidencias, no un catálogo aparte.

    Es la diferencia con tener una tabla «épica»: una épica se comenta, se
    asigna, tiene estado y se cierra igual que cualquier otra cosa. Duplicarla
    como catálogo obligaría a mantener las dos.
    """
    if proyecto_id is None:
        return []
    tipos = select(GPTipoIncidencia.id).where(GPTipoIncidencia.nivel == "EPICA")
    proyecto = (await db.execute(select(GPProyecto).where(
        GPProyecto.id == proyecto_id))).scalar_one_or_none()
    r = await db.execute(
        select(GPIncidencia).where(
            GPIncidencia.proyecto_id == proyecto_id,
            GPIncidencia.tipo_id.in_(tipos)
        ).order_by(GPIncidencia.numero.desc()).limit(200))
    return [
        {"valor": str(x.id), "etiqueta": x.resumen,
         "pista": f"{proyecto.clave}-{x.numero}" if proyecto else str(x.numero)}
        for x in r.scalars().all()
    ]


async def _incidencias(db: AsyncSession, proyecto_id: Optional[int], _usuario: str) -> List[dict]:
    if proyecto_id is None:
        return []
    proyecto = (await db.execute(select(GPProyecto).where(
        GPProyecto.id == proyecto_id))).scalar_one_or_none()
    r = await db.execute(select(GPIncidencia).where(
        GPIncidencia.proyecto_id == proyecto_id
    ).order_by(GPIncidencia.numero.desc()).limit(200))
    return [
        {"valor": str(x.id), "etiqueta": x.resumen,
         "pista": f"{proyecto.clave}-{x.numero}" if proyecto else str(x.numero)}
        for x in r.scalars().all()
    ]


async def _versiones(db: AsyncSession, proyecto_id: Optional[int], _usuario: str) -> List[dict]:
    if proyecto_id is None:
        return []
    r = await db.execute(select(GPVersion).where(
        GPVersion.proyecto_id == proyecto_id, GPVersion.archivada.is_(False)
    ).order_by(GPVersion.orden, GPVersion.nombre))
    return [{"valor": str(x.id), "etiqueta": x.nombre,
             "pista": "liberada" if x.liberada else None}
            for x in r.scalars().all()]


async def _componentes(db: AsyncSession, proyecto_id: Optional[int], _usuario: str) -> List[dict]:
    if proyecto_id is None:
        return []
    r = await db.execute(select(GPComponente).where(
        GPComponente.proyecto_id == proyecto_id, GPComponente.archivado.is_(False)
    ).order_by(GPComponente.orden, GPComponente.nombre))
    return [{"valor": str(x.id), "etiqueta": x.nombre, "pista": x.responsable,
             "color": x.color} for x in r.scalars().all()]


ENTIDADES: Dict[str, Callable] = {
    "usuario": _usuarios,
    "proyecto": _proyectos,
    "tipo_incidencia": _tipos,
    "prioridad": _prioridades,
    "estado": _estados,
    "sprint": _sprints,
    "epica": _epicas,
    "incidencia": _incidencias,
    "version": _versiones,
    "componente": _componentes,
}


async def cargar_opciones(db: AsyncSession, campos: List[CampoDelFormulario],
                          proyecto_id: Optional[int], usuario: str = "") -> None:
    """Llena las opciones de cada campo de selección.

    Las de catálogo propio se traen todas de una vez; las de entidad se consultan
    una vez por entidad y no una por campo, que es la diferencia entre una
    consulta y quince cuando el formulario tiene varios campos de usuario.
    """
    propios = [c for c in campos if c.campo.origen == "PROPIO"]
    if propios:
        r = await db.execute(select(GPCampoOpcion).where(
            GPCampoOpcion.campo_id.in_([c.campo.id for c in propios]),
            GPCampoOpcion.archivada.is_(False)).order_by(GPCampoOpcion.orden))
        por_campo: Dict[int, List[dict]] = {}
        for o in r.scalars().all():
            por_campo.setdefault(o.campo_id, []).append(
                {"valor": o.valor, "etiqueta": o.etiqueta, "color": o.color})
        for c in propios:
            c.opciones = por_campo.get(c.campo.id, [])

    de_entidad = [c for c in campos if c.campo.origen == "ENTIDAD"]
    cache: Dict[str, List[dict]] = {}
    for c in de_entidad:
        entidad = c.campo.entidad or TIPOS_DE_ENTIDAD.get(c.campo.tipo)
        if not entidad:
            continue
        if entidad not in cache:
            resolver = ENTIDADES.get(entidad)
            cache[entidad] = await resolver(db, proyecto_id, usuario) if resolver else []
        c.opciones = cache[entidad]


# ─── El esquema que consume la pantalla ───────────────────────────────────────

async def esquema(db: AsyncSession, proyecto_id: Optional[int],
                  tipo_id: Optional[int], usuario: str,
                  incidencia: Optional[GPIncidencia] = None) -> dict:
    """Todo lo que el formulario necesita para dibujarse, en una sola petición.

    Devuelve las secciones con sus campos, sus opciones ya resueltas y el valor
    actual cuando se está editando. La pantalla no decide nada: recorre esto y
    dibuja. Es lo que hace que agregar un campo no toque el frontend.
    """
    campos = await campos_del(db, proyecto_id, tipo_id)
    visibles = [c for c in campos if c.visible]
    await cargar_opciones(db, visibles, proyecto_id, usuario)

    valores = await valores_de(incidencia, visibles) if incidencia else {}
    defectos = await _defectos(db, visibles, proyecto_id, usuario)

    por_seccion: Dict[str, List[dict]] = {}
    for c in visibles:
        por_seccion.setdefault(c.campo.seccion, []).append({
            "clave": c.campo.clave,
            "nombre": c.campo.nombre,
            "descripcion": c.campo.descripcion,
            "ayuda": c.campo.ayuda,
            "tipo": c.campo.tipo,
            "multiple": c.campo.tipo in TIPOS_MULTIPLES,
            "obligatorio": c.obligatorio,
            "solo_lectura": c.solo_lectura,
            "del_sistema": c.campo.del_sistema,
            "validacion": c.campo.validacion or {},
            "opciones": c.opciones,
            # De qué depende. La pantalla usa esto para volver a pedir el esquema
            # cuando cambie el proyecto o el tipo, en vez de llevar la regla
            # escrita: si mañana un campo depende de otra cosa, se declara acá.
            "depende_de": _dependencia(c.campo),
            "valor": valores.get(c.campo.clave),
            "defecto": defectos.get(c.campo.clave),
        })

    return {
        "proyecto_id": proyecto_id,
        "tipo_id": tipo_id,
        "secciones": [
            {"clave": clave, "titulo": titulo, "campos": por_seccion[clave]}
            for clave, titulo in SECCIONES if por_seccion.get(clave)
        ],
    }


def _dependencia(campo: GPCampo) -> Optional[str]:
    """De qué otra cosa dependen las opciones de este campo."""
    entidad = campo.entidad or TIPOS_DE_ENTIDAD.get(campo.tipo)
    if entidad in ("sprint", "epica", "version", "componente", "incidencia", "estado"):
        return "proyecto"
    return None


async def _defectos(db: AsyncSession, campos: List[CampoDelFormulario],
                    proyecto_id: Optional[int], usuario: str) -> Dict[str, Any]:
    """Resuelve los valores por defecto, incluidas las señales del servidor.

    `@yo`, `@hoy` y `@sprint_activo` se resuelven acá y no en la pantalla: el
    navegador no sabe cuál es el sprint activo, y la fecha del navegador es la
    del equipo de quien mira, que no siempre coincide con la del servidor.
    """
    salida: Dict[str, Any] = {}
    sprint_activo: Optional[int] = None

    for c in campos:
        crudo = c.campo.valor_defecto
        if crudo is None:
            continue
        if crudo == "@yo":
            salida[c.campo.clave] = usuario
        elif crudo == "@hoy":
            salida[c.campo.clave] = datetime.now(timezone.utc).date().isoformat()
        elif crudo == "@ahora":
            salida[c.campo.clave] = datetime.now(timezone.utc).isoformat()
        elif crudo == "@sprint_activo":
            if sprint_activo is None and proyecto_id is not None:
                sprint_activo = (await db.execute(select(GPSprint.id).where(
                    GPSprint.proyecto_id == proyecto_id,
                    GPSprint.estado == "ACTIVO"))).scalar()
            if sprint_activo:
                salida[c.campo.clave] = str(sprint_activo)
        else:
            salida[c.campo.clave] = crudo
    return salida


async def valores_de(incidencia: GPIncidencia,
                     campos: List[CampoDelFormulario]) -> Dict[str, Any]:
    """El valor actual de cada campo, venga de una columna o del jsonb."""
    valores: Dict[str, Any] = {}
    guardados = incidencia.campos or {}
    for c in campos:
        if c.campo.almacenamiento == "COLUMNA" and c.campo.columna:
            v = getattr(incidencia, c.campo.columna, None)
            if isinstance(v, (datetime, date)):
                v = v.isoformat()
            elif v is not None and c.campo.tipo in TIPOS_DE_ENTIDAD and not isinstance(v, list):
                # Las referencias viajan como texto para que el selector no tenga
                # que distinguir entre un id numérico y un nombre de usuario.
                v = str(v)
            valores[c.campo.clave] = v
        else:
            valores[c.campo.clave] = guardados.get(c.campo.clave)
    return valores


# ─── Validación y escritura ───────────────────────────────────────────────────

def _entero(valor: Any) -> Optional[int]:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


async def _existe(db: AsyncSession, entidad: str, valor: Any,
                  proyecto_id: Optional[int]) -> bool:
    """Comprueba que la referencia apunte a algo real y del proyecto correcto.

    No se confía en que la pantalla mande un id de la lista que se le dio: quien
    arme la petición a mano puede poner el sprint de otro proyecto, y eso dejaría
    incidencias contadas en un sprint al que no pertenecen.
    """
    if entidad == "usuario":
        # No se comprueba contra la tabla del equipo a propósito. Mientras el
        # equipo no se haya formalizado esa tabla está vacía, y rechazar toda
        # asignación por eso sería peor que el problema que evita: nadie podría
        # asignarse nada, ni siquiera a sí mismo.
        return bool(str(valor).strip())

    ident = _entero(valor)
    if ident is None:
        return False

    modelo = {
        "proyecto": GPProyecto, "tipo_incidencia": GPTipoIncidencia,
        "prioridad": GPPrioridad, "estado": GPEstado, "sprint": GPSprint,
        "version": GPVersion, "componente": GPComponente,
        "epica": GPIncidencia, "incidencia": GPIncidencia,
    }.get(entidad)
    if modelo is None:
        return False

    consulta = select(modelo.id).where(modelo.id == ident)
    # Lo que es del proyecto tiene que ser de ESTE proyecto.
    if proyecto_id is not None and entidad in (
            "sprint", "version", "componente", "epica", "incidencia"):
        consulta = consulta.where(modelo.proyecto_id == proyecto_id)
    return (await db.execute(consulta)).first() is not None


async def validar(db: AsyncSession, campos: List[CampoDelFormulario],
                  entrantes: Dict[str, Any], proyecto_id: Optional[int],
                  previos: Optional[Dict[str, Any]] = None,
                  exigir_obligatorios: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Valida lo que llega y lo reparte entre columnas y jsonb.

    Devuelve `(por_columna, por_jsonb)`. Todos los problemas se juntan y se
    devuelven de una vez: de a uno obliga a corregir, reenviar, descubrir el
    siguiente, y así.
    """
    por_clave = {c.campo.clave: c for c in campos}
    columnas: Dict[str, Any] = {}
    jsonb: Dict[str, Any] = dict(previos or {})
    problemas: List[str] = []

    for clave, valor in (entrantes or {}).items():
        aplicable = por_clave.get(clave)
        if aplicable is None:
            problemas.append(
                f"«{clave}» no es un campo de este tipo de incidencia. "
                f"Si hace falta, créelo en la configuración.")
            continue
        if aplicable.solo_lectura:
            problemas.append(f"«{aplicable.campo.nombre}» no se puede editar a mano.")
            continue
        if not aplicable.visible:
            problemas.append(f"«{aplicable.campo.nombre}» no aplica acá.")
            continue

        campo = aplicable.campo
        vacio = valor is None or valor == "" or valor == []

        # ── Referencias a entidades ──
        entidad = campo.entidad or TIPOS_DE_ENTIDAD.get(campo.tipo)
        if entidad:
            if vacio:
                _guardar(campo, columnas, jsonb, None)
                continue
            multiples = campo.tipo in TIPOS_MULTIPLES
            lista = valor if isinstance(valor, (list, tuple)) else [valor]
            malos = []
            for v in lista:
                if not await _existe(db, entidad, v, proyecto_id):
                    malos.append(str(v))
            if malos:
                problemas.append(
                    f"«{campo.nombre}»: {', '.join(malos)} no existe o no es de "
                    f"este proyecto.")
                continue
            if multiples:
                _guardar(campo, columnas, jsonb, [str(v) for v in lista])
            else:
                limpio = lista[0]
                # A columna van tal como la columna los espera: los ids como
                # entero, el usuario como texto.
                if campo.almacenamiento == "COLUMNA" and entidad != "usuario":
                    limpio = _entero(limpio)
                _guardar(campo, columnas, jsonb, limpio)
            continue

        # ── Datos ──
        if vacio:
            _guardar(campo, columnas, jsonb, None)
            continue

        validador = gestion_campos.VALIDADORES.get(_equivalente(campo.tipo))
        if validador is None:
            problemas.append(
                f"«{campo.nombre}» es de un tipo que el servidor no sabe validar "
                f"({campo.tipo}).")
            continue
        try:
            opciones = [
                type("O", (), {"valor": o["valor"]})() for o in aplicable.opciones
            ]
            limpio = validador(valor, campo.validacion or {}, opciones)
            _guardar(campo, columnas, jsonb, limpio)
        except ValueError as e:
            problemas.append(f"«{campo.nombre}» {e}.")

    if exigir_obligatorios:
        for aplicable in campos:
            if not aplicable.obligatorio or not aplicable.visible:
                continue
            campo = aplicable.campo
            v = (columnas.get(campo.columna) if campo.almacenamiento == "COLUMNA"
                 else jsonb.get(campo.clave))
            if v is None or v == "" or v == []:
                problemas.append(f"«{campo.nombre}» es obligatorio.")

    if problemas:
        raise HTTPException(422, {"campos": problemas})
    return columnas, jsonb


def _guardar(campo: GPCampo, columnas: Dict[str, Any], jsonb: Dict[str, Any],
             valor: Any) -> None:
    if campo.almacenamiento == "COLUMNA" and campo.columna:
        columnas[campo.columna] = _para_columna(campo, valor)
    elif valor is None:
        jsonb.pop(campo.clave, None)
    else:
        jsonb[campo.clave] = valor


def _para_columna(campo: GPCampo, valor: Any) -> Any:
    """Lleva el valor al tipo que espera la columna.

    Los validadores devuelven la fecha como texto ISO, que es lo correcto para el
    jsonb —ahí todo es JSON—. Una columna `timestamptz` no lo acepta: asyncpg es
    estricto y falla con «expected a datetime.date or datetime.datetime
    instance», que llega al navegador como un 500 sin explicación.

    Es la costura entre los dos almacenamientos, y hay que cruzarla acá: dejarlo
    para el modelo significaría que cada sitio que escriba una fecha tenga que
    acordarse.
    """
    if valor is None:
        return None
    if campo.tipo in ("FECHA", "FECHA_HORA") and isinstance(valor, str):
        texto = valor.strip().replace("Z", "+00:00")
        try:
            momento = datetime.fromisoformat(texto)
        except ValueError:
            try:
                momento = datetime.combine(date.fromisoformat(texto[:10]),
                                           datetime.min.time())
            except ValueError:
                raise HTTPException(
                    422, {"campos": [f"«{campo.nombre}» no es una fecha válida."]})
        # Sin zona se asume UTC: la columna la lleva, y dejarla ingenua hace que
        # PostgreSQL la interprete con la zona de la sesión, que no es la misma
        # en todas las conexiones.
        return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)
    return valor


def _equivalente(tipo: str) -> str:
    """El validador que usa cada tipo.

    `TEXTO_RICO` reutiliza el de texto largo: lo que cambia es el control de la
    pantalla, no lo que se acepta. `CORREO` y `ADJUNTO` tienen el suyo.
    """
    return {"TEXTO_RICO": "TEXTO_LARGO"}.get(tipo, tipo)
