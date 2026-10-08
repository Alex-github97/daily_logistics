"""
Estados configurables de la orden de compra (Daily Logistics).

Cada empresa decide cómo se llaman sus estados, su color y su orden, y puede
crear estados propios. Lo que el sistema cambia solo se apoya en el ROL del
estado, no en su nombre:

  INICIAL           la OC recién creada.
  EN_RECEPCION      al registrar una recepción contra la OC.
  RECIBIDA_PARCIAL  al completar una recepción que no cubre todo lo pedido.
  RECIBIDA          al completar la recepción que cubre todo lo pedido.
  CERRADA           cierre manual (ya no admite recepciones).
  ANULADA           anulación manual (ya no admite recepciones).

Los códigos por defecto son los que ya usaba el módulo (PENDIENTE, PARCIAL,
COMPLETA, CANCELADA): las órdenes que existían siguen siendo válidas.
"""
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.wms import WMSEstadoOC

ROLES: Dict[str, str] = {
    "INICIAL": "Al crear la orden",
    "EN_RECEPCION": "Al registrar una recepción contra la orden",
    "RECIBIDA_PARCIAL": "Al completar una recepción que no cubre todo lo pedido",
    "RECIBIDA": "Al completar la recepción que cubre todo lo pedido",
    "CERRADA": "Cierre manual: ya no admite recepciones",
    "ANULADA": "Anulación manual: ya no admite recepciones",
}
# Sin estos el sistema no sabría a qué estado mover la orden.
ROLES_OBLIGATORIOS = ("INICIAL", "RECIBIDA_PARCIAL", "RECIBIDA")
# En estos estados la orden ya no admite recepciones.
ROLES_SIN_RECEPCION = ("RECIBIDA", "CERRADA", "ANULADA")

POR_DEFECTO = [
    {"codigo": "PENDIENTE", "nombre": "Emitida", "color": "#4F46E5", "orden": 10, "rol": "INICIAL"},
    {"codigo": "EN_RECEPCION", "nombre": "En recepción", "color": "#0891B2", "orden": 20, "rol": "EN_RECEPCION"},
    {"codigo": "PARCIAL", "nombre": "Recibida parcial", "color": "#D97706", "orden": 30, "rol": "RECIBIDA_PARCIAL"},
    {"codigo": "COMPLETA", "nombre": "Recibida", "color": "#16A34A", "orden": 40, "rol": "RECIBIDA"},
    {"codigo": "CERRADA", "nombre": "Cerrada", "color": "#475569", "orden": 50, "rol": "CERRADA"},
    {"codigo": "CANCELADA", "nombre": "Anulada", "color": "#DC2626", "orden": 60, "rol": "ANULADA"},
]


async def asegurar(db: AsyncSession) -> None:
    """Siembra los estados por defecto la primera vez que la empresa los necesita."""
    if (await db.execute(select(WMSEstadoOC.id).limit(1))).first():
        return
    for e in POR_DEFECTO:
        db.add(WMSEstadoOC(**e, activo=True))
    await db.flush()


async def listar(db: AsyncSession) -> List[WMSEstadoOC]:
    await asegurar(db)
    return list((await db.execute(select(WMSEstadoOC).order_by(WMSEstadoOC.orden, WMSEstadoOC.id))).scalars())


async def codigo_de(db: AsyncSession, rol: str) -> Optional[str]:
    """El código del estado que tiene ese rol (None si la empresa no lo usa)."""
    await asegurar(db)
    return (await db.execute(select(WMSEstadoOC.codigo).where(
        WMSEstadoOC.rol == rol, WMSEstadoOC.activo.is_(True)))).scalar()


async def rol_de(db: AsyncSession, codigo: Optional[str]) -> Optional[str]:
    if not codigo:
        return None
    await asegurar(db)
    return (await db.execute(select(WMSEstadoOC.rol).where(WMSEstadoOC.codigo == codigo))).scalar()


async def codigos_con_rol(db: AsyncSession, roles: Iterable[str]) -> List[str]:
    await asegurar(db)
    return list((await db.execute(select(WMSEstadoOC.codigo).where(WMSEstadoOC.rol.in_(list(roles))))).scalars())


async def existe(db: AsyncSession, codigo: str) -> bool:
    await asegurar(db)
    return (await db.execute(select(WMSEstadoOC.id).where(
        WMSEstadoOC.codigo == codigo, WMSEstadoOC.activo.is_(True)))).first() is not None
