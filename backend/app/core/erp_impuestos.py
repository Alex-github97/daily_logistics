"""
El motor tributario: qué impuestos y retenciones aplican, y por cuánto.

Antes un impuesto era un porcentaje plano en `erp_tipos_impuesto`. Eso alcanza
para el IVA de una factura sencilla y para nada más:

  · Sin **vigencia**, cambiar una tarifa reescribe cómo se calculó lo que ya se
    declaró.
  · Sin **base mínima**, la retención en la fuente se practica sobre compras que
    la norma excluye.
  · Sin **concepto**, no hay forma de saber si algo es honorarios (11 %) o
    compras generales (2,5 %).
  · Sin **municipio**, el ICA no se puede calcular: cada uno tiene su tarifa.
  · Sin las marcas del **tercero**, se le retiene a un autorretenedor.

Todo eso es configuración, no código. Acá va solo el mecanismo: cómo se escoge
la regla vigente y cómo se calcula. Las tarifas viven en `erp_reglas_impuesto` y
se cambian sin desplegar.

Lo que este motor NO hace: decidir si algo es honorarios o compras. Eso lo dice
quien factura, escogiendo el concepto. Adivinarlo desde la descripción sería
adivinar la retención, y equivocarse ahí tiene consecuencias con la DIAN.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.erp_nucleo import (
    ERPParametroFiscal, ERPReglaImpuesto, ERPTercero,
)

CENTAVO = Decimal("0.01")


def _r(valor: Any) -> Decimal:
    if valor is None:
        return Decimal("0")
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class ImpuestoCalculado:
    """El resultado de aplicar una regla: cuánto, sobre qué y por qué."""

    __slots__ = ("impuesto", "concepto", "papel", "base", "tarifa", "valor",
                 "cuenta_id", "regla_id", "motivo", "bloqueado")

    def __init__(self, impuesto: str, concepto: str, papel: Optional[str],
                 base: Decimal, tarifa: Decimal, valor: Decimal,
                 cuenta_id: Optional[int], regla_id: Optional[int],
                 motivo: Optional[str] = None, bloqueado: bool = False):
        self.impuesto = impuesto
        self.concepto = concepto
        self.papel = papel
        self.base = base
        self.tarifa = tarifa
        self.valor = valor
        self.cuenta_id = cuenta_id
        self.regla_id = regla_id
        # Por qué NO se aplicó, cuando el valor es cero. Sin esto, «no se retuvo»
        # es indistinguible de «se olvidó retener».
        self.motivo = motivo
        # Cierto cuando el cero NO es una respuesta sino una falla de
        # configuración: quien liquide debe detenerse, no seguir con cero.
        self.bloqueado = bloqueado

    def como_dict(self) -> dict:
        return {
            "impuesto": self.impuesto, "concepto": self.concepto,
            "papel": self.papel, "base": str(self.base),
            "tarifa": str(self.tarifa), "valor": str(self.valor),
            "cuenta_id": self.cuenta_id, "regla_id": self.regla_id,
            "motivo": self.motivo, "bloqueado": self.bloqueado,
        }


async def uvt_de(db: AsyncSession, anio: int) -> Decimal:
    """El valor de la UVT de ese año.

    Va en tabla porque cambia cada enero. Sin valor cargado se devuelve cero, y
    entonces las bases mínimas en UVT no filtran nada: es preferible a inventar
    una cifra, porque una UVT equivocada desplaza todas las retenciones.
    """
    valor = (await db.execute(select(ERPParametroFiscal.valor).where(
        ERPParametroFiscal.anio == anio,
        ERPParametroFiscal.clave == "UVT"))).scalar()
    return _r(valor) if valor is not None else Decimal("0")


async def reglas_vigentes(db: AsyncSession, empresa_id: int, impuesto: str,
                          concepto: str, fecha: date) -> List[ERPReglaImpuesto]:
    """Las reglas de ese impuesto y concepto que estaban vigentes en esa fecha.

    Vigente EN LA FECHA DEL DOCUMENTO, no hoy: recontabilizar una factura de
    marzo con la tarifa de agosto produce una cifra que no coincide con la que se
    declaró.
    """
    return list((await db.execute(select(ERPReglaImpuesto).where(
        ERPReglaImpuesto.empresa_id == empresa_id,
        ERPReglaImpuesto.impuesto == impuesto,
        ERPReglaImpuesto.concepto == concepto,
        ERPReglaImpuesto.activa.is_(True),
        ERPReglaImpuesto.vigente_desde <= fecha,
        or_(ERPReglaImpuesto.vigente_hasta.is_(None),
            ERPReglaImpuesto.vigente_hasta >= fecha),
    ).order_by(ERPReglaImpuesto.vigente_desde.desc()))).scalars().all())


async def calcular(
    db: AsyncSession, *, empresa_id: int, impuesto: str, concepto: str,
    base: Any, fecha: date, tercero: Optional[ERPTercero] = None,
    codigo_municipio: Optional[str] = None,
) -> ImpuestoCalculado:
    """Cuánto de este impuesto aplica sobre esta base.

    Devuelve siempre un resultado, aunque sea cero: cuando no se aplica, el
    motivo dice por qué. «No se retuvo» y «se olvidó retener» se ven igual en un
    total, y solo el motivo los distingue en una revisión.
    """
    base = _r(base)
    reglas = await reglas_vigentes(db, empresa_id, impuesto, concepto, fecha)

    if not reglas:
        return ImpuestoCalculado(
            impuesto, concepto, None, base, Decimal("0"), Decimal("0"), None, None,
            motivo=f"No hay regla vigente de {impuesto} para «{concepto}» "
                   f"al {fecha.isoformat()}.")

    # La más específica primero: la que nombra el municipio gana sobre la
    # general. El ICA de Bogotá no es el de Medellín.
    def especificidad(r: ERPReglaImpuesto) -> int:
        return ((1 if r.codigo_municipio else 0)
                + (1 if r.codigo_ciiu else 0)
                + (1 if r.aplica_regimen else 0))

    candidatas = [
        r for r in reglas
        if (not r.codigo_municipio or r.codigo_municipio == codigo_municipio)
        and (not r.codigo_ciiu or (tercero and r.codigo_ciiu == tercero.codigo_ciiu))
        and (not r.aplica_regimen or (tercero and r.aplica_regimen == tercero.regimen))
    ]
    if not candidatas:
        return ImpuestoCalculado(
            impuesto, concepto, None, base, Decimal("0"), Decimal("0"), None, None,
            motivo=f"Hay reglas de {impuesto}/{concepto} pero ninguna aplica a este "
                   f"tercero o municipio.")

    regla = sorted(candidatas, key=especificidad, reverse=True)[0]

    # ── Exclusiones por el tercero ──
    if tercero is not None:
        if tercero.exento_retencion and impuesto.startswith("RETE"):
            return ImpuestoCalculado(
                impuesto, concepto, regla.papel, base, Decimal("0"), Decimal("0"),
                regla.cuenta_id, regla.id,
                motivo=f"{tercero.razon_social} está marcado como exento de retención.")
        if regla.excluye_autorretenedor and tercero.autorretenedor:
            return ImpuestoCalculado(
                impuesto, concepto, regla.papel, base, Decimal("0"), Decimal("0"),
                regla.cuenta_id, regla.id,
                motivo=f"{tercero.razon_social} es autorretenedor: se autorretiene él.")
        if regla.excluye_gran_contribuyente and tercero.gran_contribuyente:
            return ImpuestoCalculado(
                impuesto, concepto, regla.papel, base, Decimal("0"), Decimal("0"),
                regla.cuenta_id, regla.id,
                motivo=f"{tercero.razon_social} es gran contribuyente.")

    # ── Base mínima ──
    minimo = _r(regla.base_minima_pesos)
    if regla.base_minima_uvt and float(regla.base_minima_uvt) > 0:
        uvt = await uvt_de(db, fecha.year)
        if uvt <= 0:
            # Sin UVT del año, el mínimo es DESCONOCIDO, no cero. Tratarlo como
            # cero hace retener sobre una compra de diez mil pesos: la regla deja
            # de filtrar y nadie lo nota, porque el documento sale bien formado.
            # Se detiene y se dice qué cargar; es un solo campo.
            return ImpuestoCalculado(
                impuesto, concepto, regla.papel, base, _r(regla.tarifa),
                Decimal("0"), regla.cuenta_id, regla.id,
                motivo=f"No se puede liquidar {impuesto}/{concepto}: la regla "
                       f"exige una base mínima de {regla.base_minima_uvt} UVT y "
                       f"no hay UVT cargada para {fecha.year}. Cárguela en "
                       f"Configuración → Parámetros fiscales.",
                bloqueado=True)
        # Manda la que resulte mayor: la norma fija el mínimo en UVT y el
        # valor en pesos es solo una comodidad para no recalcular.
        minimo = max(minimo, _r(Decimal(str(regla.base_minima_uvt)) * uvt))

    if minimo > 0 and base < minimo:
        return ImpuestoCalculado(
            impuesto, concepto, regla.papel, base, _r(regla.tarifa), Decimal("0"),
            regla.cuenta_id, regla.id,
            motivo=f"La base ({base}) no alcanza el mínimo de {minimo}.")

    tarifa = _r(regla.tarifa)
    valor = _r(base * tarifa / Decimal("100"))
    return ImpuestoCalculado(impuesto, concepto, regla.papel, base, tarifa, valor,
                             regla.cuenta_id, regla.id)


async def liquidar_documento(
    db: AsyncSession, *, empresa_id: int, fecha: date,
    base_gravada: Any, concepto: str,
    tercero: Optional[ERPTercero] = None,
    impuestos: Optional[List[str]] = None,
    base_exenta: Any = 0,
    estricto: bool = True,
) -> Dict[str, Any]:
    """Liquida todos los impuestos de un documento de una vez.

    Devuelve el detalle además del total. El detalle es lo que permite explicarle
    a alguien —o a la DIAN— por qué se retuvo lo que se retuvo, y es también lo
    que alimenta los papeles de trabajo.

    Las retenciones se calculan sobre la base GRAVADA, no sobre el total: retener
    sobre el total incluiría el IVA en la base, que es un error clásico y caro.

    `estricto` distingue emitir de explicar. Al emitir un documento hay que
    detenerse si una regla no se puede liquidar, porque saldría con una retención
    que no es la que la norma pide. Al simular pasa lo contrario: quien pregunta
    «¿qué se retendría?» necesita ver el renglón bloqueado con su motivo, y
    negarse a responder le esconde justamente la respuesta que buscaba.
    """
    impuestos = impuestos or ["IVA", "RETEFUENTE", "RETEICA", "RETEIVA"]
    base_gravada = _r(base_gravada)

    resultados: List[ImpuestoCalculado] = []
    iva = Decimal("0")

    for nombre in impuestos:
        if nombre == "RETEIVA":
            # ReteIVA se calcula sobre el IVA, no sobre la base. Hay que tener el
            # IVA ya liquidado, así que va después.
            continue
        r = await calcular(
            db, empresa_id=empresa_id, impuesto=nombre, concepto=concepto,
            base=base_gravada, fecha=fecha, tercero=tercero,
            codigo_municipio=tercero.codigo_municipio if tercero else None)
        resultados.append(r)
        if nombre == "IVA":
            iva = r.valor

    if "RETEIVA" in impuestos and iva > 0:
        resultados.append(await calcular(
            db, empresa_id=empresa_id, impuesto="RETEIVA", concepto=concepto,
            base=iva, fecha=fecha, tercero=tercero,
            codigo_municipio=tercero.codigo_municipio if tercero else None))

    # Un impuesto bloqueado no se puede resolver poniendo cero: eso emitiría el
    # documento con una retención que no es la que la norma pide. Se detiene acá,
    # con el motivo puesto, para que se corrija la configuración y se reintente.
    bloqueados = [r for r in resultados if r.bloqueado]
    if bloqueados and estricto:
        from app.core.erp_motor import ErrorContable
        raise ErrorContable(
            " ".join(r.motivo for r in bloqueados if r.motivo),
            {"impuestos_bloqueados": [r.como_dict() for r in bloqueados]})

    # Los papeles del asiento, listos para el motor contable.
    papeles: Dict[str, Decimal] = {}
    for r in resultados:
        if r.valor and r.papel:
            papeles[r.papel] = papeles.get(r.papel, Decimal("0")) + r.valor

    total_impuestos = sum((r.valor for r in resultados
                           if not r.impuesto.startswith("RETE")), Decimal("0"))
    total_retenciones = sum((r.valor for r in resultados
                             if r.impuesto.startswith("RETE")), Decimal("0"))

    return {
        "base_gravada": str(base_gravada),
        "base_exenta": str(_r(base_exenta)),
        "total_impuestos": str(total_impuestos),
        "total_retenciones": str(total_retenciones),
        "total_documento": str(base_gravada + _r(base_exenta) + total_impuestos),
        "neto_a_pagar": str(base_gravada + _r(base_exenta) + total_impuestos
                            - total_retenciones),
        "papeles": {k: str(v) for k, v in papeles.items()},
        "detalle": [r.como_dict() for r in resultados],
        # Con qué reglas NO se pudo. En modo estricto no se llega acá; al simular
        # es la parte más útil de la respuesta.
        "bloqueados": [r.como_dict() for r in bloqueados],
    }
