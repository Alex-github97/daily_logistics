"""
Umbrales de aviso del CMMS, en un solo lugar.

Antes cada pantalla tenía su número escrito en el código —garantías avisaba
a 90 días y el tablero a 30, calibración a 30, preventivos a 15— y la pantalla
de «Umbrales & Alertas» guardaba siete valores en la memoria del navegador que
ningún cálculo leía. Aquí están solo los que algo usa, y quién los usa.
"""
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PARAMETROS_EAM: Dict[str, dict] = {
    "garantia_dias_aviso": {"defecto": 90, "min": 1, "max": 365,
                            "descripcion": "Días antes del vencimiento para avisar que una garantía vence",
                            "lo_usan": "Garantías (por vencer) y el tablero del CMMS"},
    "calibracion_dias_aviso": {"defecto": 30, "min": 1, "max": 365,
                               "descripcion": "Días antes del vencimiento para marcar una calibración «por vencer»",
                               "lo_usan": "Confiabilidad → Calibraciones"},
    "pm_dias_aviso": {"defecto": 15, "min": 1, "max": 120,
                      "descripcion": "Días antes de la fecha para marcar un preventivo como «próximo»",
                      "lo_usan": "Reportes del CMMS (cumplimiento de planes)"},
}


async def leer_parametros_eam(db: AsyncSession) -> Dict[str, float]:
    from app.infrastructure.models.eam import EAMParametro
    guardados = {p.clave: p.valor for p in (await db.execute(select(EAMParametro))).scalars().all()}
    return {k: float(guardados.get(k, d["defecto"])) for k, d in PARAMETROS_EAM.items()}
