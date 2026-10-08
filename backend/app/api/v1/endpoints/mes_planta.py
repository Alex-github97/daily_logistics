"""
La terminal de planta: donde el operario mueve la orden estación por estación.

QUÉ RESUELVE
Una orden liberada no pasa de «en ejecución» a «cerrada» de un salto. La recorre
la línea: entra material, la toca una máquina, luego otra, se inspecciona y sale
producto. Sin registrar ese recorrido, el sistema solo sabe el total producido y
no sabe responder la única pregunta que hace quien está esperando la orden:
**dónde va**.

Este módulo expone lo que necesita una pantalla puesta en el piso de la planta,
al lado de la máquina:

  * las estaciones de la línea, en el orden en que el material las recorre;
  * cuánto puede tomar cada estación ahora mismo;
  * el registro del avance, firmado por el operario que lo hizo.

LA REGLA QUE LO SOSTIENE
**Una estación no puede producir más de lo que le entregó la anterior.** Es la
restricción que hace que el recorrido signifique algo: sin ella, la suma de los
avances puede superar lo que entró a la línea y el tablero mostraría un
cumplimiento imposible. Se valida al registrar y no al consultar, porque un dato
imposible no debe llegar a guardarse.

La primera estación —la entrada de material— está limitada por lo planificado en
la orden. Las demás, por lo que produjo la estación de la que reciben.

CÓMO SE IDENTIFICA EL OPERARIO
Con su código de operario, que es lo que lleva en el carné y lo que sabe de
memoria. No es una segunda contraseña: la sesión de la empresa ya está abierta en
la terminal, y esto solo dice **quién** está reportando, que es lo que la
trazabilidad necesita. Pedirle al operario de planta una contraseña larga en un
teclado con guantes es la forma más segura de que tres operarios compartan la
misma sesión y el registro deje de servir para nada.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.mes import (
    EstadoEjecucionMESEnum, EstadoOrdenProduccionEnum, MESAvanceEstacion,
    MESEquipo, MESFlujoConexion, MESFlujoNodo, MESLinea, MESOperacion,
    MESOperario, MESOrdenProduccion, MESParada, MESProducto,
    TipoNodoFlujoEnum, TipoParadaMESEnum, TurnoMESEnum,
)
from app.infrastructure.models.usuario import Usuario
# El recorrido de la linea y los totales de la orden viven en un solo sitio: los
# comparte con `mes.py`, que cierra ejecuciones y registra scrap sobre la misma
# orden. Tenerlos por duplicado fue lo que dejo los totales con dos duenos.
from app.core.mes_totales import (
    ahora as _ahora,
    ordenar_estaciones,
    predecesores,
    recalcular_totales_orden,
    registrar_scrap,
    valor as _valor,
)

router = APIRouter(prefix="/mes/planta", tags=["mes-planta"])


# ─── Esquemas ─────────────────────────────────────────────────────────────────

class Identificacion(BaseModel):
    codigo: str = Field(..., description="Código de operario, usuario o cédula")
    pin: Optional[str] = Field(None, description="El PIN de terminal, si lo tiene")


class AperturaParada(BaseModel):
    orden_id: int
    nodo_id: int
    operario_id: int
    tipo: str = Field("NO_PLANEADA",
                      description="PLANEADA, NO_PLANEADA, CALIDAD, "
                                  "MANTENIMIENTO, SETUP o MATERIAL")
    causa: str = Field(..., min_length=3)
    descripcion: Optional[str] = None


class CierreParada(BaseModel):
    descripcion: Optional[str] = None


class RegistroAvance(BaseModel):
    orden_id: int
    nodo_id: int
    operario_id: int
    cantidad_producida: float = Field(0, ge=0)
    cantidad_scrap: float = Field(0, ge=0)
    turno: str = "MANANA"
    observaciones: Optional[str] = None
    # Cerrar la estación dice «por acá ya no pasa más de esta orden». Se pide
    # explícito y no se deduce de haber alcanzado la cantidad, porque una orden
    # puede cerrarse corta a propósito.
    cerrar: bool = False


# ─── Quién reporta ────────────────────────────────────────────────────────────

@router.post("/identificar")
async def identificar(
    datos: Identificacion,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Dice qué operario está frente a la terminal.

    Acepta el código de operario, el usuario de la plataforma o la cédula: en el
    piso cada quien recuerda uno distinto, y rechazar a alguien porque escribió
    su cédula en vez de su código es la forma más rápida de que dejen de usar la
    terminal y todos reporten con la cuenta del supervisor.

    Cuando el operario tiene PIN, se exige. El PIN no reemplaza la contraseña de
    su cuenta —la sesión de la empresa ya está abierta en la terminal— pero es lo
    que impide que uno firme el avance a nombre de otro, que es de lo que depende
    poder medir la productividad de cada quien.
    """
    texto = datos.codigo.strip()
    if not texto:
        raise HTTPException(400, "Escriba su código de operario.")

    operario = (await db.execute(
        select(MESOperario)
        .outerjoin(Usuario, Usuario.id == MESOperario.usuario_id)
        .where(or_(
            func.upper(MESOperario.codigo) == texto.upper(),
            MESOperario.cedula == texto,
            func.lower(Usuario.username) == texto.lower(),
        ))
    )).scalars().first()

    if operario is None:
        raise HTTPException(
            404, f"No hay ningún operario que coincida con «{texto}». "
                 f"Puede escribir su código, su usuario o su cédula.")
    if not operario.activo:
        raise HTTPException(
            403, f"{operario.nombre} está inactivo y no puede reportar producción.")
    if operario.pin:
        entregado = (datos.pin or "").strip()
        if not entregado:
            # Pedir el PIN no es un error: es el segundo paso de la conversación.
            # Se responde 200 y sin identidad, para que la pantalla muestre el
            # campo. Devolver 401 haría que el interceptor de la aplicación
            # cerrara la sesión y sacara al operario al login por el solo hecho
            # de no haber escrito todavía su PIN.
            return {"requiere_pin": True, "nombre": operario.nombre}
        if entregado != operario.pin:
            # 403 y no 401: la sesión de la empresa es válida, lo que falla es la
            # verificación de quién está frente a la terminal.
            raise HTTPException(403, "El PIN no coincide.")

    usuario = (await db.get(Usuario, operario.usuario_id)
               if operario.usuario_id else None)
    return {
        "id": operario.id, "codigo": operario.codigo, "nombre": operario.nombre,
        "cargo": operario.cargo, "planta_id": operario.planta_id,
        "usuario": usuario.username if usuario else None,
        # La pantalla lo usa para pedir el PIN antes de dejar reportar.
        "requiere_pin": bool(operario.pin),
    }


# ─── El tablero de la línea ───────────────────────────────────────────────────

@router.get("/tablero")
async def tablero(
    linea_id: int,
    orden_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Las estaciones de una línea y el avance de una orden en cada una.

    Devuelve, por estación, cuánto lleva producido y **cuánto puede tomar
    todavía**. Ese último número es el que evita que el operario tenga que
    calcular de cabeza si le alcanza el material, y es el mismo que valida el
    servidor al registrar: si la pantalla ofrece un tope distinto al que el
    servidor aplica, el operario recibe un rechazo que no entiende.
    """
    linea = await db.get(MESLinea, linea_id)
    if linea is None:
        raise HTTPException(404, "La línea no existe.")

    nodos = list((await db.execute(
        select(MESFlujoNodo).where(MESFlujoNodo.linea_id == linea_id,
                                   MESFlujoNodo.activo.is_(True)))).scalars().all())
    conexiones = list((await db.execute(
        select(MESFlujoConexion).where(
            MESFlujoConexion.linea_id == linea_id))).scalars().all())

    if not nodos:
        return {
            "linea": {"id": linea.id, "codigo": linea.codigo, "nombre": linea.nombre},
            "orden": None, "estaciones": [],
            "aviso": "Esta línea todavía no tiene esquema. Dibújelo en "
                     "«Plantas & Líneas» para poder reportar por estación.",
        }

    ordenadas = ordenar_estaciones(nodos, conexiones)

    orden = None
    avances: Dict[int, MESAvanceEstacion] = {}
    if orden_id:
        orden = await db.get(MESOrdenProduccion, orden_id)
        if orden is None:
            raise HTTPException(404, "La orden no existe.")
        avances = {a.nodo_id: a for a in (await db.execute(
            select(MESAvanceEstacion).where(
                MESAvanceEstacion.orden_id == orden_id))).scalars().all()}

    # Nombres para mostrar: la máquina, el producto o la operación del nodo.
    equipos = {e.id: e.nombre for e in (await db.execute(
        select(MESEquipo))).scalars().all()}
    productos = {p.id: p.nombre for p in (await db.execute(
        select(MESProducto))).scalars().all()}
    operaciones = {o.id: o.nombre for o in (await db.execute(
        select(MESOperacion))).scalars().all()}

    producido_por_nodo = {nid: (a.cantidad_producida or 0.0)
                          for nid, a in avances.items()}
    plan = float(orden.cantidad_planificada) if orden else 0.0

    # Las paradas abiertas, por estación. Van en el tablero y no en una consulta
    # aparte porque una máquina detenida es lo primero que hay que ver al mirar
    # la línea: separarlo obliga a abrir otra pantalla para enterarse.
    paradas_abiertas: Dict[int, Any] = {}
    if avances:
        for parada, nodo_id in (await db.execute(
            select(MESParada, MESAvanceEstacion.nodo_id)
            .join(MESAvanceEstacion, MESParada.avance_id == MESAvanceEstacion.id)
            .where(MESAvanceEstacion.orden_id == orden_id,
                   MESParada.fecha_fin.is_(None))
        )).all():
            paradas_abiertas[nodo_id] = parada

    estaciones = []
    for posicion, nodo in enumerate(ordenadas, start=1):
        previos = predecesores(nodo.id, conexiones)
        # Lo que esta estación puede tomar: lo que le entregaron los anteriores
        # —o lo planificado, si es la primera— menos lo que ya procesó.
        if previos:
            entrante = sum(producido_por_nodo.get(p, 0.0) for p in previos)
        else:
            entrante = plan
        avance = avances.get(nodo.id)
        procesado = ((avance.cantidad_producida or 0.0)
                     + (avance.cantidad_scrap or 0.0)) if avance else 0.0
        disponible = max(0.0, round(entrante - procesado, 4))

        parada = paradas_abiertas.get(nodo.id)
        estaciones.append({
            "posicion": posicion,
            "nodo_id": nodo.id,
            "tipo": _valor(nodo.tipo),
            # Las coordenadas del esquema, para poder dibujar la línea tal como
            # está configurada en la planta y no como una fila de tarjetas.
            "pos_x": nodo.pos_x,
            "pos_y": nodo.pos_y,
            "parada_abierta": None if parada is None else {
                "id": parada.id, "tipo": _valor(parada.tipo),
                "causa": parada.causa, "fecha_inicio": parada.fecha_inicio,
            },
            "nombre": (nodo.nombre
                       or equipos.get(nodo.equipo_id)
                       or productos.get(nodo.producto_id)
                       or operaciones.get(nodo.operacion_id)
                       or f"Estación {posicion}"),
            "operacion": operaciones.get(nodo.operacion_id),
            "equipo": equipos.get(nodo.equipo_id),
            "es_cuello_botella": bool(nodo.es_cuello_botella),
            "tiempo_ciclo_seg": nodo.tiempo_ciclo_seg,
            "cantidad_entrante": round(entrante, 4),
            "cantidad_producida": round(avance.cantidad_producida, 4) if avance else 0.0,
            "cantidad_scrap": round(avance.cantidad_scrap, 4) if avance else 0.0,
            "cantidad_disponible": disponible,
            "estado": _valor(avance.estado) if avance else "PENDIENTE",
            "operario_id": avance.operario_id if avance else None,
            "fecha_inicio": avance.fecha_inicio if avance else None,
            "fecha_fin": avance.fecha_fin if avance else None,
            "observaciones": avance.observaciones if avance else None,
            # Se puede reportar si hay algo que procesar y la estación no está
            # cerrada. La pantalla usa esto para habilitar el botón, y el
            # servidor aplica la misma regla al guardar.
            "puede_reportar": bool(
                orden
                and _valor(orden.estado) in ("LIBERADA", "EN_EJECUCION")
                and disponible > 0
                and parada is None
                and (not avance or _valor(avance.estado) != "COMPLETADA")),
        })

    return {
        "linea": {"id": linea.id, "codigo": linea.codigo, "nombre": linea.nombre},
        # Por dónde pasa el material de una estación a otra. Con esto la pantalla
        # dibuja la línea tal como está configurada —con sus bifurcaciones y sus
        # reprocesos— en vez de suponer una fila india.
        "conexiones": [{"origen_id": c.origen_id, "destino_id": c.destino_id,
                        "tipo": _valor(c.tipo), "etiqueta": c.etiqueta}
                       for c in conexiones],
        "orden": None if not orden else {
            "id": orden.id, "numero": orden.numero,
            "estado": _valor(orden.estado),
            "cantidad_planificada": orden.cantidad_planificada,
            "cantidad_producida": orden.cantidad_producida,
            "cantidad_scrap": orden.cantidad_scrap,
            "unidad_medida": orden.unidad_medida,
        },
        "estaciones": estaciones,
    }


@router.get("/ordenes")
async def ordenes_en_piso(
    linea_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Las órdenes que se pueden trabajar ahora: liberadas o en ejecución.

    Una orden planeada todavía no baja a la planta, y una cerrada ya no se toca.
    Mostrarlas todas obligaría al operario a buscar la suya entre cientos.
    """
    q = select(MESOrdenProduccion).where(
        MESOrdenProduccion.estado.in_([EstadoOrdenProduccionEnum.LIBERADA,
                                       EstadoOrdenProduccionEnum.EN_EJECUCION]))
    if linea_id:
        q = q.where(MESOrdenProduccion.linea_id == linea_id)
    ordenes = (await db.execute(
        q.order_by(MESOrdenProduccion.id.desc()).limit(100))).scalars().all()
    productos = {p.id: p for p in (await db.execute(
        select(MESProducto))).scalars().all()}
    return [{
        "id": o.id, "numero": o.numero, "estado": _valor(o.estado),
        "linea_id": o.linea_id,
        "producto": (f"{productos[o.producto_id].codigo} — "
                     f"{productos[o.producto_id].nombre}")
                    if o.producto_id in productos else None,
        "cantidad_planificada": o.cantidad_planificada,
        "cantidad_producida": o.cantidad_producida,
        "unidad_medida": o.unidad_medida,
    } for o in ordenes]


# ─── Registrar el avance ──────────────────────────────────────────────────────

@router.post("/avance")
async def registrar_avance(
    datos: RegistroAvance,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Suma lo que esta estación hizo con esta orden.

    Suma, no reemplaza: el operario reporta varias veces durante el turno y cada
    reporte se agrega al acumulado de la estación. Reemplazar obligaría a que
    escriba el total corregido cada vez, que es donde se equivoca.
    """
    if datos.cantidad_producida <= 0 and datos.cantidad_scrap <= 0 and not datos.cerrar:
        raise HTTPException(400, "No hay nada que registrar: indique cuánto "
                                 "produjo, cuánto se perdió, o cierre la estación.")

    orden = await db.get(MESOrdenProduccion, datos.orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe.")
    if _valor(orden.estado) not in ("LIBERADA", "EN_EJECUCION"):
        raise HTTPException(
            409, f"La orden {orden.numero} está {_valor(orden.estado).lower()} "
                 f"y no admite reportes de producción.")

    nodo = await db.get(MESFlujoNodo, datos.nodo_id)
    if nodo is None:
        raise HTTPException(404, "La estación no existe.")
    if orden.linea_id and nodo.linea_id != orden.linea_id:
        raise HTTPException(
            409, "Esa estación no pertenece a la línea de la orden.")

    operario = await db.get(MESOperario, datos.operario_id)
    if operario is None or not operario.activo:
        raise HTTPException(403, "El operario no existe o está inactivo.")

    conexiones = list((await db.execute(
        select(MESFlujoConexion).where(
            MESFlujoConexion.linea_id == nodo.linea_id))).scalars().all())
    previos = predecesores(nodo.id, conexiones)

    avances = {a.nodo_id: a for a in (await db.execute(
        select(MESAvanceEstacion).where(
            MESAvanceEstacion.orden_id == orden.id))).scalars().all()}

    if previos:
        entrante = sum((avances[p].cantidad_producida or 0.0)
                       for p in previos if p in avances)
    else:
        entrante = float(orden.cantidad_planificada)

    avance = avances.get(nodo.id)
    procesado = ((avance.cantidad_producida or 0.0)
                 + (avance.cantidad_scrap or 0.0)) if avance else 0.0
    disponible = round(entrante - procesado, 4)
    pedido = datos.cantidad_producida + datos.cantidad_scrap

    if pedido > disponible + 1e-6:
        # El mensaje dice el número, no solo que no se puede: el operario tiene
        # que poder corregir sin llamar a nadie.
        origen = ("lo planificado en la orden" if not previos
                  else "lo que entregó la estación anterior")
        raise HTTPException(
            409,
            f"No se puede registrar {pedido:g}: en esta estación solo hay "
            f"{disponible:g} disponible según {origen}.")

    if avance is None:
        avance = MESAvanceEstacion(
            orden_id=orden.id, nodo_id=nodo.id, operario_id=operario.id,
            turno=TurnoMESEnum(datos.turno) if datos.turno in
                  TurnoMESEnum.__members__ else TurnoMESEnum.MANANA,
            estado=EstadoEjecucionMESEnum.EN_PROGRESO,
            cantidad_producida=0.0, cantidad_scrap=0.0,
            fecha_inicio=_ahora())
        db.add(avance)
        await db.flush()

    avance.cantidad_producida = round(
        (avance.cantidad_producida or 0.0) + datos.cantidad_producida, 4)
    avance.cantidad_scrap = round(
        (avance.cantidad_scrap or 0.0) + datos.cantidad_scrap, 4)
    avance.operario_id = operario.id
    if datos.observaciones:
        avance.observaciones = datos.observaciones
    if datos.cerrar:
        avance.estado = EstadoEjecucionMESEnum.COMPLETADA
        avance.fecha_fin = _ahora()
    else:
        avance.estado = EstadoEjecucionMESEnum.EN_PROGRESO

    # La pérdida que reporta la estación va al LIBRO de scrap, no solo a su
    # contador. Antes se quedaba en `avance.cantidad_scrap` y la pantalla de
    # Scrap no se enteraba: la línea decía haber perdido material y el módulo
    # que existe para medirlo mostraba cero.
    if datos.cantidad_scrap > 0:
        registrar_scrap(
            db, orden_id=orden.id, producto_id=orden.producto_id,
            cantidad=datos.cantidad_scrap,
            causa=f"Reportado en {nodo.nombre or 'estación'}",
            operario_id=operario.id,
            observaciones=datos.observaciones)

    # Los totales de la orden se recalculan desde sus fuentes; no los acumula
    # nadie. El por qué está en `app/core/mes_totales.py`.
    await db.flush()
    await recalcular_totales_orden(db, orden)

    if _valor(orden.estado) == "LIBERADA":
        orden.estado = EstadoOrdenProduccionEnum.EN_EJECUCION
        if not orden.fecha_inicio_real:
            orden.fecha_inicio_real = _ahora()

    await db.commit()
    await db.refresh(avance)

    return {
        "avance": {
            "id": avance.id, "nodo_id": avance.nodo_id,
            "cantidad_producida": avance.cantidad_producida,
            "cantidad_scrap": avance.cantidad_scrap,
            "estado": _valor(avance.estado),
        },
        "orden": {
            "id": orden.id, "numero": orden.numero,
            "estado": _valor(orden.estado),
            "cantidad_producida": orden.cantidad_producida,
            "cantidad_scrap": orden.cantidad_scrap,
        },
        "mensaje": (f"{operario.nombre} registró {datos.cantidad_producida:g} "
                    f"en {nodo.nombre or 'la estación'}."),
    }


@router.get("/recorrido/{orden_id}")
async def recorrido(
    orden_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Por dónde ha pasado una orden, en orden y con quién la trabajó.

    Es lo que consume la trazabilidad: la lista de estaciones que tocaron la
    orden, con la cantidad, el operario y la hora. Sin esto, el expediente del
    lote dice cuánto se produjo pero no dónde ni quién.
    """
    orden = await db.get(MESOrdenProduccion, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe.")
    if not orden.linea_id:
        return {"orden_id": orden_id, "estaciones": []}

    nodos = list((await db.execute(
        select(MESFlujoNodo).where(
            MESFlujoNodo.linea_id == orden.linea_id))).scalars().all())
    conexiones = list((await db.execute(
        select(MESFlujoConexion).where(
            MESFlujoConexion.linea_id == orden.linea_id))).scalars().all())
    avances = {a.nodo_id: a for a in (await db.execute(
        select(MESAvanceEstacion).where(
            MESAvanceEstacion.orden_id == orden_id))).scalars().all()}
    operarios = {o.id: o.nombre for o in (await db.execute(
        select(MESOperario))).scalars().all()}
    equipos = {e.id: e.nombre for e in (await db.execute(
        select(MESEquipo))).scalars().all()}

    salida = []
    for posicion, nodo in enumerate(ordenar_estaciones(nodos, conexiones), start=1):
        a = avances.get(nodo.id)
        if a is None:
            continue
        salida.append({
            "posicion": posicion, "nodo_id": nodo.id,
            "estacion": nodo.nombre or equipos.get(nodo.equipo_id)
                        or f"Estación {posicion}",
            "tipo": _valor(nodo.tipo),
            "operario": operarios.get(a.operario_id),
            "turno": _valor(a.turno),
            "cantidad_producida": a.cantidad_producida,
            "cantidad_scrap": a.cantidad_scrap,
            "estado": _valor(a.estado),
            "fecha_inicio": a.fecha_inicio, "fecha_fin": a.fecha_fin,
            "observaciones": a.observaciones,
        })
    return {"orden_id": orden_id, "estaciones": salida}


# ─── Averías y paradas ────────────────────────────────────────────────────────

@router.post("/parada")
async def abrir_parada(
    datos: AperturaParada,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Registra que una estación se detuvo, y desde cuándo.

    El reloj lo lleva el servidor: la parada se abre ahora y se cierra cuando
    alguien diga. Pedirle al operario que escriba la hora de inicio garantiza que
    la escriba redondeada —o mal—, y la duración es justo el dato por el que se
    registra una parada.

    No se permiten dos paradas abiertas a la vez en la misma estación para la
    misma orden: si la máquina ya está parada, lo que corresponde es cerrar la
    anterior, no acumular dos relojes sobre el mismo tiempo.
    """
    if datos.tipo not in TipoParadaMESEnum.__members__:
        raise HTTPException(
            400, f"Tipo de parada no válido: {datos.tipo}. "
                 f"Use uno de {', '.join(TipoParadaMESEnum.__members__)}.")

    avance = (await db.execute(
        select(MESAvanceEstacion).where(
            MESAvanceEstacion.orden_id == datos.orden_id,
            MESAvanceEstacion.nodo_id == datos.nodo_id))).scalar_one_or_none()

    # Una máquina puede pararse antes de producir nada: si la estación todavía no
    # tiene registro, se crea. Exigir que primero reporte producción dejaría sin
    # registrar justamente la avería que impidió producir.
    if avance is None:
        operario = await db.get(MESOperario, datos.operario_id)
        if operario is None or not operario.activo:
            raise HTTPException(403, "El operario no existe o está inactivo.")
        avance = MESAvanceEstacion(
            orden_id=datos.orden_id, nodo_id=datos.nodo_id,
            operario_id=datos.operario_id,
            estado=EstadoEjecucionMESEnum.EN_PROGRESO,
            cantidad_producida=0.0, cantidad_scrap=0.0, fecha_inicio=_ahora())
        db.add(avance)
        await db.flush()

    abierta = (await db.execute(
        select(MESParada).where(MESParada.avance_id == avance.id,
                                MESParada.fecha_fin.is_(None)))).scalars().first()
    if abierta is not None:
        raise HTTPException(
            409, f"Esa estación ya tiene una parada abierta desde las "
                 f"{abierta.fecha_inicio:%H:%M} por «{abierta.causa}». "
                 f"Ciérrela antes de abrir otra.")

    parada = MESParada(
        ejecucion_id=None, avance_id=avance.id,
        operario_id=datos.operario_id, equipo_id=None,
        tipo=TipoParadaMESEnum[datos.tipo],
        causa=datos.causa.strip(), descripcion=datos.descripcion,
        fecha_inicio=_ahora())
    db.add(parada)

    # Mientras la máquina está parada, la estación no está produciendo.
    avance.estado = EstadoEjecucionMESEnum.PAUSADA
    await db.commit()
    await db.refresh(parada)
    return {
        "id": parada.id, "avance_id": avance.id,
        "tipo": _valor(parada.tipo), "causa": parada.causa,
        "fecha_inicio": parada.fecha_inicio,
        "mensaje": f"Parada abierta por «{parada.causa}».",
    }


@router.put("/parada/{parada_id}/cerrar")
async def cerrar_parada(
    parada_id: int,
    datos: CierreParada,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Cierra una parada y calcula cuánto duró."""
    parada = await db.get(MESParada, parada_id)
    if parada is None:
        raise HTTPException(404, "La parada no existe.")
    if parada.fecha_fin is not None:
        raise HTTPException(409, "Esa parada ya está cerrada.")

    parada.fecha_fin = _ahora()
    # La duración se guarda calculada y no se deja para el momento de consultar:
    # así los informes de OEE no dependen de que quien los escriba se acuerde de
    # restar las fechas, ni de en qué zona horaria lo haga.
    parada.duracion_min = round(
        (parada.fecha_fin - parada.fecha_inicio).total_seconds() / 60.0, 2)
    if datos.descripcion:
        parada.descripcion = ((parada.descripcion or "") + "\n"
                              + datos.descripcion).strip()

    if parada.avance_id:
        avance = await db.get(MESAvanceEstacion, parada.avance_id)
        # Vuelve a producción solo si no queda otra parada abierta.
        if avance is not None and avance.estado == EstadoEjecucionMESEnum.PAUSADA:
            otra = (await db.execute(
                select(MESParada).where(
                    MESParada.avance_id == avance.id,
                    MESParada.id != parada.id,
                    MESParada.fecha_fin.is_(None)))).scalars().first()
            if otra is None:
                avance.estado = EstadoEjecucionMESEnum.EN_PROGRESO

    await db.commit()
    return {
        "id": parada.id, "duracion_min": parada.duracion_min,
        "mensaje": f"Parada cerrada tras {parada.duracion_min:g} minutos.",
    }


@router.get("/paradas")
async def paradas_de_orden(
    orden_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Las paradas de una orden, con su estación y quién las reportó."""
    filas = (await db.execute(
        select(MESParada, MESFlujoNodo, MESOperario)
        .join(MESAvanceEstacion, MESParada.avance_id == MESAvanceEstacion.id)
        .join(MESFlujoNodo, MESFlujoNodo.id == MESAvanceEstacion.nodo_id)
        .outerjoin(MESOperario, MESOperario.id == MESParada.operario_id)
        .where(MESAvanceEstacion.orden_id == orden_id)
        .order_by(MESParada.fecha_inicio.desc()))).all()
    return [{
        "id": p.id, "nodo_id": n.id,
        "estacion": n.nombre or f"Estación {n.id}",
        "tipo": _valor(p.tipo), "causa": p.causa, "descripcion": p.descripcion,
        "operario": o.nombre if o else None,
        "fecha_inicio": p.fecha_inicio, "fecha_fin": p.fecha_fin,
        "duracion_min": p.duracion_min,
        "abierta": p.fecha_fin is None,
    } for p, n, o in filas]


# ─── Productividad por operario ───────────────────────────────────────────────

@router.get("/productividad")
async def productividad(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Qué produjo cada operario, con cuánto desperdicio y cuánto tiempo parado.

    Es la razón de que cada operario tenga su propia cuenta: con un código
    compartido en la terminal, estas tres cifras no existirían.

    El desperdicio se da en porcentaje sobre lo que esa persona procesó, no en
    valor absoluto: comparar a quien hizo 50 unidades con quien hizo 5.000 por
    las unidades desperdiciadas solo dice quién trabajó más horas.
    """
    filtros = []
    if desde:
        filtros.append(MESAvanceEstacion.fecha_inicio >= desde)
    if hasta:
        filtros.append(MESAvanceEstacion.fecha_inicio <= hasta)

    filas = (await db.execute(
        select(MESOperario.id, MESOperario.codigo, MESOperario.nombre,
               MESOperario.cargo,
               func.count(MESAvanceEstacion.id),
               func.coalesce(func.sum(MESAvanceEstacion.cantidad_producida), 0),
               func.coalesce(func.sum(MESAvanceEstacion.cantidad_scrap), 0))
        .join(MESAvanceEstacion, MESAvanceEstacion.operario_id == MESOperario.id)
        .where(*filtros)
        .group_by(MESOperario.id, MESOperario.codigo, MESOperario.nombre,
                  MESOperario.cargo))).all()

    # El tiempo parado va en consulta aparte. Unirlo a la anterior multiplicaría
    # las filas de avance por las de parada y las cantidades saldrían infladas:
    # es el error clásico de sumar sobre dos uniones a la vez.
    detenido = dict((await db.execute(
        select(MESParada.operario_id,
               func.coalesce(func.sum(MESParada.duracion_min), 0))
        .where(MESParada.operario_id.isnot(None))
        .group_by(MESParada.operario_id))).all())

    salida = []
    for oid, codigo, nombre, cargo, estaciones, producido, scrap in filas:
        producido = float(producido or 0)
        scrap = float(scrap or 0)
        procesado = producido + scrap
        salida.append({
            "operario_id": oid, "codigo": codigo, "nombre": nombre,
            "cargo": cargo,
            "estaciones_trabajadas": int(estaciones),
            "cantidad_producida": round(producido, 2),
            "cantidad_scrap": round(scrap, 2),
            "scrap_pct": round(scrap / procesado * 100, 2) if procesado else 0.0,
            "minutos_parada": round(float(detenido.get(oid, 0) or 0), 1),
        })
    salida.sort(key=lambda x: -x["cantidad_producida"])
    return salida
