"""
El servicio de incidencias: crear, registrar y convertir una solicitud en trabajo.

Acá vive lo que no puede quedar en un endpoint porque tiene que pasar igual
venga de donde venga: la numeración, el historial y el ascenso desde la mesa de
ayuda. Un endpoint que arme una incidencia por su cuenta se saltaría alguna de
las tres, y el fallo no se ve hasta mucho después.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import gestion_campos
from app.core.permisos_consola import Miembro
from app.infrastructure.models.gestion import (
    GPEstado, GPHistorial, GPIncidencia, GPPrioridad, GPProyecto,
    GPTipoIncidencia, GPWorkflow,
)
from app.infrastructure.models.soporte import SoporteTicket, SoporteMensaje


def clave_de(proyecto: GPProyecto, incidencia: GPIncidencia) -> str:
    """La clave visible: SOP-123.

    Se arma al mostrar y no se guarda. Guardarla obligaría a reescribir todas las
    incidencias de un proyecto el día que alguien lo renombre.
    """
    return f"{proyecto.clave}-{incidencia.numero}"


def anotar(db: AsyncSession, incidencia_id: int, campo: str,
           anterior: Any, nuevo: Any, autor: str) -> None:
    """Registra un cambio. Se recorta porque esto es para leer, no para restaurar."""
    db.add(GPHistorial(
        incidencia_id=incidencia_id,
        campo=campo,
        anterior=None if anterior is None else str(anterior)[:500],
        nuevo=None if nuevo is None else str(nuevo)[:500],
        autor=autor,
        creado=datetime.now(timezone.utc),
    ))


def anotar_varios(db: AsyncSession, incidencia_id: int,
                  cambios: Sequence[Tuple[str, Any, Any]], autor: str) -> None:
    for campo, antes, despues in cambios:
        anotar(db, incidencia_id, campo, antes, despues, autor)


async def siguiente_numero(db: AsyncSession, proyecto_id: int) -> int:
    """El consecutivo del proyecto, reservado de forma segura.

    `UPDATE ... RETURNING` toma el bloqueo de la fila del proyecto, así que dos
    altas simultáneas en el mismo proyecto se serializan y en proyectos distintos
    no se estorban. `SELECT max(numero) + 1` sería una carrera: las dos leen el
    mismo máximo y producen la misma clave.
    """
    numero = (await db.execute(text(
        "UPDATE public.gp_proyecto SET contador = contador + 1 "
        "WHERE id = :p RETURNING contador"), {"p": proyecto_id})).scalar()
    if numero is None:
        raise HTTPException(404, "Ese proyecto no existe.")
    return int(numero)


async def workflow_de(db: AsyncSession, proyecto: GPProyecto,
                      tipo: GPTipoIncidencia) -> int:
    """Qué flujo gobierna a esta incidencia.

    Manda el del tipo, y si no tiene, el del proyecto. Así se define uno por
    proyecto y se hace la excepción solo donde de verdad hace falta —una épica
    rara vez recorre los mismos estados que un error—.
    """
    wf = tipo.workflow_id or proyecto.workflow_id
    if wf:
        return wf
    porDefecto = (await db.execute(select(GPWorkflow.id).where(
        GPWorkflow.por_defecto.is_(True), GPWorkflow.archivado.is_(False)
    ).limit(1))).scalar()
    if porDefecto is None:
        raise HTTPException(
            409,
            f"«{proyecto.nombre}» no tiene flujo asignado y no hay ninguno por "
            f"defecto. Asígnele uno en la configuración del proyecto.")
    return porDefecto


async def estado_inicial(db: AsyncSession, workflow_id: int) -> GPEstado:
    estado = (await db.execute(select(GPEstado).where(
        GPEstado.workflow_id == workflow_id, GPEstado.inicial.is_(True)
    ).order_by(GPEstado.orden).limit(1))).scalar_one_or_none()
    if estado is None:
        # Sin inicial marcado se toma el primero: es preferible a no dejar crear
        # nada. Un flujo mal configurado no debería bloquear el trabajo.
        estado = (await db.execute(select(GPEstado).where(
            GPEstado.workflow_id == workflow_id
        ).order_by(GPEstado.orden).limit(1))).scalar_one_or_none()
    if estado is None:
        raise HTTPException(
            409, "El flujo de este proyecto no tiene ningún estado definido.")
    return estado


async def prioridad_por_defecto(db: AsyncSession) -> Optional[int]:
    return (await db.execute(select(GPPrioridad.id).where(
        GPPrioridad.por_defecto.is_(True)).limit(1))).scalar()


async def tipo_valido(db: AsyncSession, tipo_id: int,
                      proyecto_id: int) -> GPTipoIncidencia:
    """El tipo, si sirve para este proyecto.

    Un tipo es del proyecto o es global. Aceptar el de otro proyecto dejaría a la
    incidencia recorriendo un flujo que su equipo no configuró.
    """
    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == tipo_id))).scalar_one_or_none()
    if tipo is None or tipo.archivado:
        raise HTTPException(404, "Ese tipo de incidencia no existe o está archivado.")
    if tipo.proyecto_id is not None and tipo.proyecto_id != proyecto_id:
        raise HTTPException(400, "Ese tipo de incidencia es de otro proyecto.")
    return tipo


async def validar_padre(db: AsyncSession, padre_id: int, proyecto_id: int,
                        tipo: GPTipoIncidencia,
                        hijo_id: Optional[int] = None) -> GPIncidencia:
    """Comprueba que colgar de ese padre tenga sentido.

    La jerarquía sale del nivel del tipo y no de una tabla de parentesco: una
    subtarea cuelga de algo normal, y algo normal cuelga de una épica. Además se
    impide que una incidencia sea su propio ancestro, que es lo que convierte
    cualquier recorrido del árbol en un bucle infinito.
    """
    padre = (await db.execute(select(GPIncidencia).where(
        GPIncidencia.id == padre_id))).scalar_one_or_none()
    if padre is None:
        raise HTTPException(404, "La incidencia que indicó como padre no existe.")
    if padre.proyecto_id != proyecto_id:
        raise HTTPException(400, "El padre tiene que estar en el mismo proyecto.")
    if hijo_id is not None and padre.id == hijo_id:
        raise HTTPException(400, "Una incidencia no puede colgar de sí misma.")

    tipo_padre = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.id == padre.tipo_id))).scalar_one_or_none()
    nivel_padre = tipo_padre.nivel if tipo_padre else "NORMAL"

    esperado = {"SUBTAREA": "NORMAL", "NORMAL": "EPICA"}.get(tipo.nivel)
    if esperado is None:
        raise HTTPException(400, "Una épica no puede colgar de nada.")
    if nivel_padre != esperado:
        raise HTTPException(
            400,
            f"Una incidencia de nivel {tipo.nivel} cuelga de una de nivel "
            f"{esperado}, no de una {nivel_padre}.")

    if hijo_id is not None:
        # Solo hay dos saltos posibles, así que basta con mirar hacia arriba
        # mientras haya padre; no hace falta un recorrido general.
        actual = padre
        vistos = {hijo_id}
        while actual is not None and actual.padre_id is not None:
            if actual.padre_id in vistos:
                raise HTTPException(400, "Eso crearía un ciclo en la jerarquía.")
            vistos.add(actual.id)
            actual = (await db.execute(select(GPIncidencia).where(
                GPIncidencia.id == actual.padre_id))).scalar_one_or_none()

    return padre


async def crear(db: AsyncSession, proyecto: GPProyecto, *, tipo_id: int,
                resumen: str, descripcion: Optional[str], autor: str,
                asignado: Optional[str] = None,
                prioridad_id: Optional[int] = None,
                padre_id: Optional[int] = None,
                puntos: Optional[int] = None,
                etiquetas: Optional[List[str]] = None,
                campos: Optional[Dict[str, Any]] = None,
                vence: Optional[datetime] = None,
                inicio_plan: Optional[datetime] = None,
                sprint_id: Optional[int] = None,
                reporta: Optional[str] = None,
                ticket_id: Optional[int] = None,
                estado_id: Optional[int] = None,
                columnas: Optional[Dict[str, Any]] = None) -> GPIncidencia:
    """Da de alta una incidencia con todo lo que eso implica.

    `estado_id` solo lo usa el ascenso desde soporte, que necesita dejarla en el
    estado sin clasificar aunque el flujo empiece en otro sitio.

    `reporta` se puede indicar distinto de quien la crea: alguien de soporte
    registra a nombre de quien reportó. Si no se indica, es quien la crea.
    """
    tipo = await tipo_valido(db, tipo_id, proyecto.id)
    workflow_id = await workflow_de(db, proyecto, tipo)

    if estado_id is None:
        estado_id = (await estado_inicial(db, workflow_id)).id

    # Los campos ya vienen validados cuando el alta pasa por el motor del
    # formulario. Cuando llegan por otra vía —el ascenso desde soporte— se
    # validan acá, por el MISMO motor.
    #
    # Antes se usaba el validador viejo, que no sabe de almacenamiento: desde que
    # los campos nativos entraron al registro, veía «Título» entre los aplicables,
    # no lo encontraba en el jsonb —vive en una columna— y lo daba por vacío. El
    # ascenso desde soporte fallaba con «Título es obligatorio» aunque el título
    # venía puesto, en su argumento.
    #
    # Los obligatorios no se exigen por esta vía: quien llama trae el título y la
    # descripción en sus argumentos, y los demás campos los llena el equipo al
    # clasificar. Exigirlos impediría clasificar una solicitud que llegó a medias,
    # que es justo lo que hay que poder hacer.
    if columnas is None:
        from app.core import gestion_formulario   # acá para no cerrar un ciclo

        aplicables = await gestion_formulario.campos_del(db, proyecto.id, tipo.id)
        await gestion_formulario.cargar_opciones(db, aplicables, proyecto.id, autor)
        de_columna, valores = await gestion_formulario.validar(
            db, aplicables, campos or {}, proyecto.id, exigir_obligatorios=False)
        columnas = de_columna
    else:
        valores = dict(campos or {})

    # Lo que va a cada columna: primero los argumentos sueltos —los que usa el
    # ascenso desde soporte— y encima lo que el motor del formulario validó.
    #
    # Va por nombre y no con una cadena de `elif` a propósito: con la cadena, un
    # campo nativo nuevo se guardaba en silencio en ninguna parte, porque nadie
    # se acordaba de agregarle su rama. Acá, lo que el motor produzca llega solo.
    datos: Dict[str, Any] = {
        "resumen": resumen, "descripcion": descripcion,
        "asignado": asignado, "reporta": reporta or autor,
        "prioridad_id": prioridad_id, "padre_id": padre_id,
        "sprint_id": sprint_id, "puntos": puntos,
        "vence": vence, "inicio_plan": inicio_plan,
        "etiquetas": etiquetas,
    }
    for columna, valor in (columnas or {}).items():
        if columna in datos:
            datos[columna] = valor
        else:
            # Una columna que el motor conoce y esta función no: si se ignorara,
            # el campo se guardaría en ninguna parte sin que nadie se entere.
            raise HTTPException(
                500,
                f"El campo «{columna}» apunta a una columna que el alta no sabe "
                f"llenar. Revise su configuración.")

    resumen = (datos["resumen"] or "").strip()
    if not resumen:
        raise HTTPException(422, "La incidencia necesita un título.")

    padre_id = datos["padre_id"]
    if padre_id is not None:
        await validar_padre(db, padre_id, proyecto.id, tipo)

    numero = await siguiente_numero(db, proyecto.id)

    # Al final del backlog. Se deja hueco entre una y otra para poder insertar
    # después sin reordenar la lista entera en cada arrastre.
    ultimo = (await db.execute(select(func.max(GPIncidencia.orden)).where(
        GPIncidencia.proyecto_id == proyecto.id))).scalar() or 0.0

    incidencia = GPIncidencia(
        proyecto_id=proyecto.id,
        numero=numero,
        tipo_id=tipo.id,
        estado_id=estado_id,
        prioridad_id=datos["prioridad_id"] or await prioridad_por_defecto(db),
        resumen=resumen[:300],
        descripcion=datos["descripcion"],
        reporta=datos["reporta"] or autor,
        asignado=datos["asignado"],
        padre_id=padre_id,
        puntos=datos["puntos"],
        orden=float(ultimo) + 1000.0,
        etiquetas=sorted({str(e).strip()
                          for e in (datos["etiquetas"] or []) if str(e).strip()}),
        campos=valores,
        vence=datos["vence"],
        inicio_plan=datos["inicio_plan"],
        sprint_id=datos["sprint_id"],
        ticket_id=ticket_id,
        actualizado=datetime.now(timezone.utc),
    )
    db.add(incidencia)
    await db.flush()

    anotar(db, incidencia.id, "creada", None, resumen[:500], autor)
    return incidencia


async def promover_ticket(db: AsyncSession, ticket: SoporteTicket,
                          autor: str) -> Optional[GPIncidencia]:
    """Convierte una solicitud de soporte en trabajo interno.

    El asunto del cliente se **copia**, no se mueve: `soporte_ticket.asunto` se
    queda intacto porque es lo que el cliente ve en su conversación y la
    evidencia de qué fue lo que pidió. Desde acá el equipo reescribe el título
    cuantas veces haga falta, y cada reescritura queda en el historial.

    Devuelve None si el proyecto no tiene el automático encendido o si el ticket
    ya tenía su incidencia. Llamarla dos veces no crea dos.
    """
    ya = (await db.execute(select(GPIncidencia).where(
        GPIncidencia.ticket_id == ticket.id))).scalar_one_or_none()
    if ya is not None:
        return ya

    proyecto = (await db.execute(select(GPProyecto).where(
        GPProyecto.incidencia_automatica.is_(True),
        GPProyecto.archivado.is_(False),
    ).order_by(GPProyecto.id).limit(1))).scalar_one_or_none()
    if proyecto is None:
        return None

    workflow_id = await workflow_de(db, proyecto, await _tipo_para(db, ticket, proyecto))
    # Entra sin clasificar: es lo que mantiene fuera del backlog y de las
    # métricas de entrega las consultas que se resuelven en el chat en dos
    # minutos, sin que por eso se pierda ninguna.
    sin_clasificar = (await db.execute(select(GPEstado).where(
        GPEstado.workflow_id == workflow_id,
        GPEstado.categoria == "SIN_CLASIFICAR",
    ).order_by(GPEstado.orden).limit(1))).scalar_one_or_none()

    tipo = await _tipo_para(db, ticket, proyecto)

    # El primer mensaje del cliente es la descripción: es donde está el detalle,
    # y obligar a abrir la conversación para saber de qué se trata convierte cada
    # clasificación en dos pantallas.
    primero = (await db.execute(select(SoporteMensaje).where(
        SoporteMensaje.ticket_id == ticket.id,
        SoporteMensaje.interno.is_(False),
    ).order_by(SoporteMensaje.id).limit(1))).scalar_one_or_none()

    detalle = primero.cuerpo if primero else None
    contexto = [f"Solicitud {ticket.numero} de {ticket.cliente_codigo}."]
    if ticket.modulo:
        contexto.append(f"Módulo: {ticket.modulo}.")
    if ticket.impacto:
        contexto.append(f"Impacto declarado: {ticket.impacto}.")
    descripcion = "\n\n".join(filter(None, [detalle, " ".join(contexto)]))

    incidencia = await crear(
        db, proyecto,
        tipo_id=tipo.id,
        resumen=ticket.asunto,
        descripcion=descripcion,
        autor=autor,
        campos=await _campos_del_ticket(db, proyecto, tipo, ticket),
        ticket_id=ticket.id,
        estado_id=sin_clasificar.id if sin_clasificar else None,
    )
    anotar(db, incidencia.id, "origen", None,
           f"solicitud de soporte {ticket.numero}", autor)
    return incidencia


async def _tipo_para(db: AsyncSession, ticket: SoporteTicket,
                     proyecto: GPProyecto) -> GPTipoIncidencia:
    """El tipo que corresponde al trabajo declarado en el ticket.

    Se propone desde `tipo_trabajo`, que el equipo ya corrige en la cola —quien
    reporta llama «error» a casi todo—. Si no hay equivalencia, cae en TAREA.
    """
    equivalencias = {"ERROR": "ERROR", "MEJORA": "MEJORA",
                     "TAREA": "TAREA", "CONSULTA": "CONSULTA"}
    clave = equivalencias.get((ticket.tipo_trabajo or "").upper(), "TAREA")

    for candidata in (clave, "TAREA"):
        tipo = (await db.execute(select(GPTipoIncidencia).where(
            GPTipoIncidencia.clave == candidata,
            GPTipoIncidencia.archivado.is_(False),
            # OR explícito y no `IN (id, NULL)`: en SQL nada casa con NULL, así
            # que un IN con NULL dentro deja fuera justo los tipos globales.
            or_(GPTipoIncidencia.proyecto_id == proyecto.id,
                GPTipoIncidencia.proyecto_id.is_(None)),
        # El del proyecto manda sobre el global cuando existen los dos.
        ).order_by(GPTipoIncidencia.proyecto_id.desc().nullslast()
                   ).limit(1))).scalar_one_or_none()
        if tipo is not None:
            return tipo

    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.archivado.is_(False),
        GPTipoIncidencia.nivel == "NORMAL",
    ).order_by(GPTipoIncidencia.orden).limit(1))).scalar_one_or_none()
    if tipo is None:
        raise HTTPException(
            409, "No hay ningún tipo de incidencia configurado.")
    return tipo


async def _campos_del_ticket(db: AsyncSession, proyecto: GPProyecto,
                             tipo: GPTipoIncidencia,
                             ticket: SoporteTicket) -> Dict[str, Any]:
    """Traslada lo que el ticket ya sabe a los campos que existan.

    Se comprueba contra los campos aplicables en vez de asumirlos: son
    configurables y el operador pudo haberlos borrado, y un ascenso no debería
    fallar por eso.
    """
    aplicables = await gestion_campos.campos_aplicables(db, proyecto.id, tipo.id)
    por_clave = {a.campo.clave: a for a in aplicables}
    valores: Dict[str, Any] = {}

    if "modulo" in por_clave and ticket.modulo:
        validas = {o.valor for o in por_clave["modulo"].opciones}
        if ticket.modulo.upper() in validas:
            valores["modulo"] = ticket.modulo.upper()
        elif "OTRO" in validas:
            valores["modulo"] = "OTRO"

    if "empresa_afectada" in por_clave and ticket.cliente_codigo:
        valores["empresa_afectada"] = ticket.cliente_codigo

    return valores
