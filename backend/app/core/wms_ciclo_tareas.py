"""
Ciclo de fondo de las tareas de bodega (cada minuto, en cada cliente):

- evalúa los frentes de picking y crea los reabastecimientos que falten
  (incluida la sala de ventas del POS, cuyas ventas no pasan por el picking);
- devuelve a la cola las tareas asignadas que nadie empezó a tiempo;
- cierra las jornadas que quedaron abiertas más de 14 horas.

Cada cliente se procesa con su propio candado: con varios workers solo uno lo
hace, y un cliente con error no frena a los demás.
"""
from __future__ import annotations

import asyncio
import logging
import zlib

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine

log = logging.getLogger(__name__)
INTERVALO = 60


async def _esquemas() -> list:
    async with engine.connect() as c:
        hay = (await c.execute(text("SELECT to_regclass('public.plataforma_cliente')"))).scalar()
        if not hay:
            return ["public"]
        filas = (await c.execute(text("SELECT esquema FROM public.plataforma_cliente WHERE activo = true"))).all()
    return list(dict.fromkeys(["public", *[f[0] for f in filas if f[0]]]))


async def vuelta(esquema: str) -> None:
    from app.core import personal as per
    from app.core import wms_tareas_dirigidas as wtd
    from app.core import wms_reabastecimiento as reab
    clave = zlib.crc32(f"wms-tareas:{esquema}".encode())
    async with engine.connect() as candado:
        if not (await candado.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": clave})).scalar():
            return
        try:
            async with AsyncSessionLocal(info={"esquema": esquema}) as db:
                existe = (await db.execute(text("SELECT to_regclass('wms_frentes_picking')"))).scalar()
                if not existe:
                    return
                await reab.evaluar(db)
                await wtd.liberar_vencidas(db)
                await per.cerrar_olvidadas(db)
                await db.commit()
        finally:
            await candado.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": clave})


async def ciclo() -> None:
    while True:
        await asyncio.sleep(INTERVALO)
        try:
            for esq in await _esquemas():
                try:
                    await vuelta(esq)
                except Exception as e:  # noqa: BLE001 — un cliente con error no frena a los demás
                    log.warning("Tareas de bodega (%s): %s", esq, e)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Tareas de bodega: %s", e)
