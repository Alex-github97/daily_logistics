"""
El motor del inventario: mover existencias y dejar kárdex.

Vive en `core` y no en un endpoint porque lo usan dos sitios: la pantalla de
inventario y, sobre todo, las órdenes de trabajo. Si la lógica estuviera en el
endpoint, la orden tendría que llamarse a sí misma por HTTP o duplicar el
cálculo, y dos copias del costeo terminan dando cifras distintas.

COSTEO PROMEDIO PONDERADO
  entrada  costo_promedio = (saldo × promedio + cantidad × costo) / (saldo + cantidad)
  salida   sale al promedio vigente y el promedio no cambia

SALIDAS SIN EXISTENCIA
Se permiten y quedan marcadas. Negar el registro no devuelve el repuesto al
estante: la pieza ya se montó, y lo único que se lograría es que la salida no
quede escrita y el descuadre aparezca más tarde sin quién lo explique. La
existencia queda en negativo, que es una señal visible de que hay algo que
conciliar, y los informes la muestran en rojo.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.eam import EAMRepuesto, EAMOTMaterial
from app.infrastructure.models.inventario import (
    InvBodega, InvExistencia, InvMovimiento,
)

# Los que suman al saldo. El resto resta.
TIPOS_ENTRADA = {"ENTRADA", "AJUSTE_ENTRADA", "TRASLADO_ENTRADA", "DEVOLUCION"}
TIPOS_SALIDA = {"SALIDA", "AJUSTE_SALIDA", "TRASLADO_SALIDA"}


async def bodega_por_defecto(db: AsyncSession) -> Optional[InvBodega]:
    """La bodega marcada por defecto, o la única que exista.

    Con una sola bodega no tiene sentido obligar a escogerla en cada línea de
    cada orden: se asume, y el usuario solo decide cuando de verdad hay opción.
    """
    r = await db.execute(select(InvBodega).where(and_(
        InvBodega.activo.is_(True), InvBodega.por_defecto.is_(True))))
    bodega = r.scalar_one_or_none()
    if bodega:
        return bodega
    r = await db.execute(select(InvBodega).where(InvBodega.activo.is_(True)).limit(2))
    bodegas = list(r.scalars().all())
    return bodegas[0] if len(bodegas) == 1 else None


async def _existencia(db: AsyncSession, repuesto_id: int,
                      bodega_id: int) -> InvExistencia:
    r = await db.execute(select(InvExistencia).where(and_(
        InvExistencia.repuesto_id == repuesto_id,
        InvExistencia.bodega_id == bodega_id)))
    fila = r.scalar_one_or_none()
    if not fila:
        fila = InvExistencia(repuesto_id=repuesto_id, bodega_id=bodega_id,
                             cantidad=0, costo_promedio=0)
        db.add(fila)
        await db.flush()
    return fila


async def _sincronizar_stock_global(db: AsyncSession, repuesto_id: int) -> None:
    """Deja `eam_repuesto.stock_actual` como la suma de todas las bodegas.

    Ese campo ya existía y se sigue usando en pantallas viejas. Mantenerlo al
    día evita que dos sitios muestren cifras distintas del mismo repuesto; la
    verdad por bodega vive en `eam_inv_existencia`.
    """
    r = await db.execute(select(func.coalesce(func.sum(InvExistencia.cantidad), 0))
                         .where(InvExistencia.repuesto_id == repuesto_id))
    total = float(r.scalar() or 0)
    repuesto = await db.get(EAMRepuesto, repuesto_id)
    if repuesto:
        repuesto.stock_actual = int(total) if total == int(total) else total


async def mover(db: AsyncSession, *, repuesto_id: int, bodega_id: int, tipo: str,
                cantidad: float, costo_unitario: Optional[float] = None,
                fecha: Optional[datetime] = None,
                ot_id: Optional[int] = None, ot_material_id: Optional[int] = None,
                motivo_id: Optional[int] = None, traslado_id: Optional[int] = None,
                documento: Optional[str] = None, proveedor: Optional[str] = None,
                observaciones: Optional[str] = None,
                usuario: Optional[str] = None) -> InvMovimiento:
    """Registra un movimiento y actualiza la existencia. Es el único camino.

    Nada debería tocar `eam_inv_existencia` por fuera de acá: el saldo y el
    kárdex tienen que moverse juntos o dejan de poder auditarse.
    """
    if cantidad <= 0:
        raise ValueError("La cantidad de un movimiento debe ser mayor que cero")
    if tipo not in TIPOS_ENTRADA | TIPOS_SALIDA:
        raise ValueError(f"Tipo de movimiento desconocido: {tipo}")

    fila = await _existencia(db, repuesto_id, bodega_id)
    saldo = fila.cantidad or 0
    promedio = fila.costo_promedio or 0

    if tipo in TIPOS_ENTRADA:
        costo = costo_unitario if costo_unitario is not None else promedio
        nuevo_saldo = saldo + cantidad
        # Con saldo negativo el promedio anterior no significa nada: se toma el
        # costo de esta entrada, que es el único dato real que hay.
        if saldo <= 0:
            promedio = costo
        elif nuevo_saldo > 0:
            promedio = (saldo * promedio + cantidad * costo) / nuevo_saldo
    else:
        # La salida sale al promedio vigente; el promedio no se mueve.
        costo = costo_unitario if costo_unitario is not None else promedio
        nuevo_saldo = saldo - cantidad

    fila.cantidad = round(nuevo_saldo, 4)
    fila.costo_promedio = round(promedio, 4)
    fila.ultimo_movimiento = fecha or datetime.utcnow()

    movimiento = InvMovimiento(
        fecha=fecha or datetime.utcnow(), repuesto_id=repuesto_id,
        bodega_id=bodega_id, tipo=tipo, cantidad=cantidad,
        costo_unitario=round(costo or 0, 4),
        costo_total=round((costo or 0) * cantidad, 2),
        saldo_cantidad=fila.cantidad, saldo_costo_promedio=fila.costo_promedio,
        ot_id=ot_id, ot_material_id=ot_material_id, motivo_id=motivo_id,
        traslado_id=traslado_id, documento=documento, proveedor=proveedor,
        observaciones=observaciones, registrado_por=usuario)
    db.add(movimiento)
    await db.flush()
    await _sincronizar_stock_global(db, repuesto_id)
    return movimiento


async def sincronizar_orden(db: AsyncSession, ot, usuario: Optional[str] = None
                            ) -> Dict[str, Any]:
    """Deja el inventario acorde con los repuestos que la orden declara hoy.

    POR QUÉ RECONCILIA EN VEZ DE DESCONTAR
    Al guardar una orden, sus líneas se borran y se reconstruyen enteras. Si acá
    se descontara sin más, editar dos veces la misma orden descontaría dos
    veces. Entonces se compara lo que la orden pide ahora contra lo que ya se
    despachó para ella, y se mueve solo la diferencia:

        falta   → sale de la bodega
        sobra   → vuelve como devolución

    Así guardar la orden veinte veces sin tocar los repuestos no mueve nada, y
    bajar una cantidad devuelve al estante lo que ya no se usó.
    """
    if not getattr(ot, "id", None):
        return {"movimientos": 0, "sin_existencia": []}

    defecto = await bodega_por_defecto(db)

    # Las líneas se leen de la tabla y no de `ot.repuestos`. Leerlas por la
    # relación funcionaba mientras la orden traía material, pero una orden sin
    # repuestos —una revisión, un diagnóstico, una orden recién abierta— dejaba
    # la colección sin cargar y el acceso intentaba una consulta perezosa en
    # pleno contexto asíncrono: `MissingGreenlet`, y la orden no se creaba.
    # Después del flush la tabla ya tiene lo mismo que la relación, así que
    # preguntarle a ella es igual de correcto y no depende de si SQLAlchemy
    # alcanzó a cargarla.
    r = await db.execute(select(EAMOTMaterial).where(EAMOTMaterial.ot_id == ot.id))
    lineas = list(r.scalars().all())

    # Lo que la orden pide hoy, por repuesto y bodega.
    requerido: Dict[Tuple[int, int], float] = {}
    for linea in lineas:
        if not linea.repuesto_id:
            continue   # material suelto, sin catálogo: no toca inventario
        bodega_id = getattr(linea, "bodega_id", None) or (defecto.id if defecto else None)
        if not bodega_id:
            continue   # sin bodega no hay de dónde descontar
        clave = (linea.repuesto_id, bodega_id)
        requerido[clave] = requerido.get(clave, 0) + (linea.cantidad or 0)

    # Lo ya despachado para esta orden.
    r = await db.execute(select(InvMovimiento)
                         .where(InvMovimiento.ot_id == ot.id))
    despachado: Dict[Tuple[int, int], float] = {}
    for m in r.scalars().all():
        clave = (m.repuesto_id, m.bodega_id)
        signo = 1 if m.tipo in TIPOS_SALIDA else -1
        despachado[clave] = despachado.get(clave, 0) + signo * m.cantidad

    # El material sale el día del trabajo, no el día en que se digitó la orden.
    # Con la fecha de hoy, una orden registrada con atraso mandaba su consumo al
    # mes equivocado y el kárdex dejaba de cuadrar con el costo del periodo.
    fecha_salida = getattr(ot, "fecha_fin", None) or getattr(ot, "fecha_inicio", None)

    movimientos = 0
    sin_existencia: List[Dict[str, Any]] = []
    for clave in set(requerido) | set(despachado):
        repuesto_id, bodega_id = clave
        delta = round(requerido.get(clave, 0) - despachado.get(clave, 0), 4)
        if abs(delta) < 0.0001:
            continue

        if delta > 0:
            fila = await _existencia(db, repuesto_id, bodega_id)
            if (fila.cantidad or 0) < delta:
                repuesto = await db.get(EAMRepuesto, repuesto_id)
                bodega = await db.get(InvBodega, bodega_id)
                sin_existencia.append({
                    "repuesto": repuesto.nombre if repuesto else repuesto_id,
                    "codigo": repuesto.codigo if repuesto else None,
                    "bodega": bodega.nombre if bodega else bodega_id,
                    "disponible": fila.cantidad or 0, "requerido": delta,
                })
            await mover(db, repuesto_id=repuesto_id, bodega_id=bodega_id,
                        tipo="SALIDA", cantidad=delta, ot_id=ot.id,
                        fecha=fecha_salida,
                        observaciones=f"Orden de trabajo {ot.numero}",
                        usuario=usuario)
        else:
            await mover(db, repuesto_id=repuesto_id, bodega_id=bodega_id,
                        tipo="DEVOLUCION", cantidad=-delta, ot_id=ot.id,
                        fecha=fecha_salida,
                        observaciones=f"Devolución por ajuste de la orden {ot.numero}",
                        usuario=usuario)
        movimientos += 1

    return {"movimientos": movimientos, "sin_existencia": sin_existencia}


async def revertir_orden(db: AsyncSession, ot_id: int,
                         usuario: Optional[str] = None) -> int:
    """Devuelve a la bodega todo lo despachado para una orden.

    Se usa al anular o borrar una orden: si el material no se consumió, dejarlo
    descontado convertiría el inventario en un faltante permanente que nadie
    puede explicar.
    """
    r = await db.execute(select(InvMovimiento).where(InvMovimiento.ot_id == ot_id))
    pendiente: Dict[Tuple[int, int], float] = {}
    for m in r.scalars().all():
        clave = (m.repuesto_id, m.bodega_id)
        signo = 1 if m.tipo in TIPOS_SALIDA else -1
        pendiente[clave] = pendiente.get(clave, 0) + signo * m.cantidad

    hechos = 0
    for (repuesto_id, bodega_id), neto in pendiente.items():
        if abs(neto) < 0.0001:
            continue
        await mover(db, repuesto_id=repuesto_id, bodega_id=bodega_id,
                    tipo="DEVOLUCION" if neto > 0 else "SALIDA",
                    cantidad=abs(neto), ot_id=ot_id,
                    observaciones="Reverso por anulación de la orden",
                    usuario=usuario)
        hechos += 1
    return hechos


async def recalcular_existencias(db: AsyncSession) -> Dict[str, int]:
    """Reconstruye las existencias desde el kárdex.

    El kárdex es la verdad; la existencia es un saldo guardado por rapidez. Esto
    corrige cualquier desincronización y es la forma de comprobar que no la hay:
    si al correrlo cambia algo, había un problema.
    """
    r = await db.execute(select(InvMovimiento).order_by(InvMovimiento.fecha,
                                                        InvMovimiento.id))
    saldos: Dict[Tuple[int, int], Tuple[float, float]] = {}
    for m in r.scalars().all():
        clave = (m.repuesto_id, m.bodega_id)
        cantidad, promedio = saldos.get(clave, (0.0, 0.0))
        if m.tipo in TIPOS_ENTRADA:
            nuevo = cantidad + m.cantidad
            if cantidad <= 0:
                promedio = m.costo_unitario or 0
            elif nuevo > 0:
                promedio = (cantidad * promedio + m.cantidad * (m.costo_unitario or 0)) / nuevo
            cantidad = nuevo
        else:
            cantidad -= m.cantidad
        saldos[clave] = (cantidad, promedio)

    corregidas = 0
    for (repuesto_id, bodega_id), (cantidad, promedio) in saldos.items():
        fila = await _existencia(db, repuesto_id, bodega_id)
        if (round(fila.cantidad or 0, 4) != round(cantidad, 4)
                or round(fila.costo_promedio or 0, 4) != round(promedio, 4)):
            corregidas += 1
        fila.cantidad = round(cantidad, 4)
        fila.costo_promedio = round(promedio, 4)

    for repuesto_id in {k[0] for k in saldos}:
        await _sincronizar_stock_global(db, repuesto_id)

    await db.commit()
    return {"existencias": len(saldos), "corregidas": corregidas}
