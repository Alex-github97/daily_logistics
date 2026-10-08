"""
Proceso de fondo de los canales de venta y anotación de cambios de stock.

- Cada movimiento de inventario anota el producto en `mkp_cola_stock` dentro de
  la misma transacción (si el movimiento se deshace, la anotación también).
- Cada 20 segundos, por cada empresa: consulta pedidos de los conectores que
  toca, envía los estados pendientes y publica el stock de lo que cambió.

Con varios procesos del servidor, un candado de PostgreSQL por empresa evita
que dos hagan la misma vuelta a la vez.
"""
import asyncio
import logging
import zlib

from sqlalchemy import event, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import AsyncSessionLocal, engine
from app.core.marketplace import servicio
from app.infrastructure.models.marketplace import MKPColaStock
from app.infrastructure.models.wms import WMSMovimientoInventario

log = logging.getLogger("uvicorn.error")
INTERVALO = 20


@event.listens_for(Session, "after_flush")
def _anotar_cambios_de_stock(session, _contexto) -> None:
    ids = {o.producto_id for o in session.new if isinstance(o, WMSMovimientoInventario) and o.producto_id}
    if ids:
        session.connection().execute(
            pg_insert(MKPColaStock).values([{"producto_id": i} for i in ids]).on_conflict_do_nothing())


async def _esquemas() -> list:
    async with engine.connect() as c:
        hay = (await c.execute(text("SELECT to_regclass('public.plataforma_cliente')"))).scalar()
        if not hay:
            return ["public"]
        filas = (await c.execute(text("SELECT esquema FROM public.plataforma_cliente WHERE activo = true"))).all()
    return list(dict.fromkeys(["public", *[f[0] for f in filas if f[0]]]))


async def _vuelta(esquema: str) -> None:
    clave = zlib.crc32(f"mkp:{esquema}".encode())
    async with engine.connect() as candado:
        tomado = (await candado.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": clave})).scalar()
        if not tomado:
            return
        try:
            async with AsyncSessionLocal(info={"esquema": esquema}) as db:
                await servicio.tick(db)
        finally:
            await candado.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": clave})


async def ciclo() -> None:
    while True:
        await asyncio.sleep(INTERVALO)
        try:
            for esq in await _esquemas():
                try:
                    await _vuelta(esq)
                except Exception as e:  # noqa: BLE001 — una empresa con error no frena a las demás
                    log.warning("Canales de venta (%s): %s", esq, e)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Canales de venta: %s", e)
