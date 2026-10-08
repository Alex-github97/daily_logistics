"""
Numeración con resolución DIAN y códigos únicos (CUFE / CUDE).

NUMERACIÓN. El número sale de la resolución vigente con un solo
`UPDATE … RETURNING`: es atómico (dos cajas no reciben el mismo número), no
pasa del rango autorizado y no sirve fuera de la vigencia. Si la resolución
se agotó o venció se dice exactamente eso, porque facturar fuera de ella no
es válido ante la DIAN.

CUFE / CUDE. Fórmula del anexo técnico de facturación electrónica (SHA-384):

    NumFac + FecFac + HorFac + ValFac + 01 + ValIVA + 04 + ValINC + 03 + ValICA
    + ValTot + NitOFE + NumAdq + ClaveTécnica + TipoAmbiente

El CUDE (documento POS, nota crédito) es la misma cadena con el PIN del
software en lugar de la clave técnica. Comprobado contra el ejemplo del anexo
en `tests/unit/test_facturacion_dian.py`.

Lo que NO hace todavía: generar el XML UBL, firmarlo y transmitirlo. Eso lo
hace el proveedor tecnológico que la empresa contrate; el documento queda en
estado POR_TRANSMITIR con su código calculado.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.erp_facturacion import ERPResolucionFacturacion

CONSUMIDOR_FINAL = "222222222222"


class ResolucionInvalida(Exception):
    pass


def _v(x) -> str:
    return str(Decimal(str(x or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def codigo_unico(numero: str, fecha: date, hora: str, valor_bruto, iva, inc, ica, valor_total,
                 nit_emisor: str, documento_adquiriente: Optional[str], clave: str, ambiente: str) -> str:
    """CUFE (con clave técnica) o CUDE (con PIN del software)."""
    cadena = (f"{numero}{fecha.isoformat()}{hora}{_v(valor_bruto)}01{_v(iva)}04{_v(inc)}03{_v(ica)}"
              f"{_v(valor_total)}{nit_emisor}{documento_adquiriente or CONSUMIDOR_FINAL}{clave or ''}{ambiente}")
    return hashlib.sha384(cadena.encode("utf-8")).hexdigest()


def hora_colombia(momento: datetime) -> str:
    from zoneinfo import ZoneInfo
    return momento.astimezone(ZoneInfo("America/Bogota")).strftime("%H:%M:%S-05:00")


async def tomar_numero(db: AsyncSession, resolucion_id: int) -> Tuple[str, ERPResolucionFacturacion]:
    """El siguiente número de la resolución, o la razón exacta por la que no hay."""
    fila = (await db.execute(text("""
        UPDATE erp_resolucion_facturacion
           SET actual = GREATEST(actual, desde - 1) + 1, updated_at = now()
         WHERE id = :i AND activa
           AND current_date BETWEEN vigencia_desde AND vigencia_hasta
           AND GREATEST(actual, desde - 1) + 1 <= hasta
        RETURNING actual
    """), {"i": resolucion_id})).first()
    res = await db.get(ERPResolucionFacturacion, resolucion_id)
    if res is None:
        raise ResolucionInvalida("La caja no tiene resolución de facturación asignada.")
    if fila is None:
        hoy = date.today()
        if not res.activa:
            raise ResolucionInvalida(f"La resolución {res.numero_resolucion} está inactiva.")
        if hoy > res.vigencia_hasta:
            raise ResolucionInvalida(f"La resolución {res.numero_resolucion} venció el {res.vigencia_hasta}. "
                                     "Registre la nueva en Finanzas → Resoluciones de facturación.")
        if hoy < res.vigencia_desde:
            raise ResolucionInvalida(f"La resolución {res.numero_resolucion} rige desde el {res.vigencia_desde}.")
        raise ResolucionInvalida(f"Se agotó el rango de la resolución {res.numero_resolucion} "
                                 f"({res.prefijo}{res.desde}–{res.prefijo}{res.hasta}).")
    await db.refresh(res)
    return f"{res.prefijo}{fila[0]}", res


def restantes(res: ERPResolucionFacturacion) -> int:
    return int(res.hasta - max(res.actual or 0, res.desde - 1))
