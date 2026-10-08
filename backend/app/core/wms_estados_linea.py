"""
Estado de cada línea de una orden de salida, derivado de sus cantidades.

La columna `wms_ordenes_salida_detalle.estado` se creaba en PENDIENTE y nada
la volvía a tocar: una orden entregada mostraba todas sus líneas «pendientes».
En vez de actualizarla en cada pantalla (picking, despacho, TMS, cancelación…),
se recalcula aquí después de cualquier escritura que toque la orden, sus líneas
o su picking, en la misma transacción.

    PENDIENTE → RESERVADO → EN_PREPARACION → PREPARADO → DESPACHO_PARCIAL → DESPACHADO → ENTREGADO
    (ENTREGA_PARCIAL si la orden se entregó sin todo; CANCELADO si la orden se anuló)

«Preparado» es lo confirmado en el picking, no lo reservado: `cantidad_preparada`
se llena al reservar y por sí sola diría «preparado» antes de que nadie alistara.
"""
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.infrastructure.models.wms import WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSPickingDetalle

ALISTADO = """(SELECT COALESCE(SUM(pd.cantidad_pickeada), 0) FROM wms_picking_detalles pd
               JOIN wms_picking_tareas t ON t.id = pd.tarea_id
              WHERE t.orden_id = d.orden_id AND pd.producto_id = d.producto_id AND pd.confirmado)"""

CASO = f"""CASE
  WHEN o.estado = 'CANCELADO' THEN 'CANCELADO'
  WHEN o.estado = 'ENTREGADO' AND d.cantidad_despachada >= d.cantidad_solicitada THEN 'ENTREGADO'
  WHEN o.estado = 'ENTREGADO' AND d.cantidad_despachada > 0 THEN 'ENTREGA_PARCIAL'
  WHEN d.cantidad_despachada >= d.cantidad_solicitada THEN 'DESPACHADO'
  WHEN d.cantidad_despachada > 0 THEN 'DESPACHO_PARCIAL'
  WHEN {ALISTADO} >= d.cantidad_solicitada THEN 'PREPARADO'
  WHEN {ALISTADO} > 0 THEN 'EN_PREPARACION'
  WHEN d.cantidad_preparada > 0 THEN 'RESERVADO'
  ELSE 'PENDIENTE' END"""

SQL = text(f"""UPDATE wms_ordenes_salida_detalle d SET estado = {CASO}
  FROM wms_ordenes_salida o
 WHERE o.id = d.orden_id AND d.orden_id = ANY(:ids) AND d.estado IS DISTINCT FROM ({CASO})""")
TAREAS = text("SELECT DISTINCT orden_id FROM wms_picking_tareas WHERE id = ANY(:ids) AND orden_id IS NOT NULL")


@event.listens_for(Session, "after_flush")
def _recalcular_lineas(session, _contexto) -> None:
    ids, tareas = set(), set()
    for o in list(session.new) + list(session.dirty):
        if isinstance(o, WMSOrdenSalida) and o.id:
            ids.add(o.id)
        elif isinstance(o, WMSOrdenSalidaDetalle) and o.orden_id:
            ids.add(o.orden_id)
        elif isinstance(o, WMSPickingDetalle) and o.tarea_id:
            tareas.add(o.tarea_id)
    if tareas:
        ids |= set(session.connection().execute(TAREAS, {"ids": list(tareas)}).scalars())
    if ids:
        session.connection().execute(SQL, {"ids": list(ids)})


def sincronizar_todo_sql() -> str:
    """Para corregir los datos existentes (se ejecuta una vez por esquema)."""
    return f"UPDATE wms_ordenes_salida_detalle d SET estado = {CASO} FROM wms_ordenes_salida o WHERE o.id = d.orden_id"
