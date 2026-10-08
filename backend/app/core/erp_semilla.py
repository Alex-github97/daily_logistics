"""
El arranque en frío de la contabilidad: PUC, reglas y parámetros.

Sin esto, una empresa nueva no puede facturar: el motor contable pide la cuenta
de cartera y no hay ninguna, así que la primera factura falla con «no hay regla
contable para cartera». Sembrar un mínimo usable es lo que evita que la primera
experiencia del módulo sea un error.

Todo lo que se siembra es **editable**. El PUC colombiano tiene cientos de
cuentas y acá van las que hacen falta para operar; el resto se agrega desde la
pantalla. Las tarifas van con su vigencia, así que cuando cambien se agrega una
regla nueva en vez de editar la vieja —editar la vieja reescribiría cómo se
calculó lo que ya se declaró—.

Las cifras de 2026 —UVT, salario mínimo— se dejan en cero a propósito cuando no
se conocen con certeza: un valor inventado desplaza todas las retenciones que
dependen de él, y es peor que no tener valor, porque nadie revisa lo que ya
aparece lleno.
"""
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.erp import (
    NaturalezaCuenta, TipoCuenta, ERPEmpresa, ERPPlanCuenta,
)
from app.infrastructure.models.erp_nucleo import (
    ERPParametroFiscal, ERPReglaContable, ERPReglaImpuesto,
)


# ─── Plan Único de Cuentas ────────────────────────────────────────────────────
#
# (código, nombre, tipo, naturaleza, acepta movimientos)
#
# La estructura del PUC colombiano: clase (1) → grupo (2) → cuenta (4) →
# subcuenta (6). Solo las subcuentas aceptan movimiento; las de arriba son
# agrupadoras y su saldo es la suma de las de abajo. Permitir movimiento en una
# cuenta agrupadora es lo que hace que un balance no cuadre consigo mismo.

PUC: List[Tuple[str, str, TipoCuenta, NaturalezaCuenta, bool]] = [
    # ── 1. ACTIVO ──
    ("1", "ACTIVO", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("11", "DISPONIBLE", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("1105", "CAJA", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("110505", "Caja general", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("110510", "Caja menor", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1110", "BANCOS", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("111005", "Bancos nacionales", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("111010", "Bancos del exterior", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),

    ("13", "DEUDORES", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("1305", "CLIENTES", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("130505", "Clientes nacionales", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1330", "ANTICIPOS Y AVANCES", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("133005", "Anticipos a proveedores", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1355", "ANTICIPO DE IMPUESTOS", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("135515", "Retención en la fuente soportada", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("135517", "Retención de IVA soportada", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("135518", "Retención de ICA soportada", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1399", "PROVISIONES", TipoCuenta.ACTIVO, NaturalezaCuenta.CREDITO, False),
    ("139905", "Deterioro de cartera", TipoCuenta.ACTIVO, NaturalezaCuenta.CREDITO, True),

    ("14", "INVENTARIOS", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("1435", "MERCANCÍAS NO FABRICADAS POR LA EMPRESA", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("143505", "Mercancías para la venta", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1455", "MATERIALES, REPUESTOS Y ACCESORIOS", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("145505", "Repuestos y accesorios", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),

    ("15", "PROPIEDADES, PLANTA Y EQUIPO", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("1540", "FLOTA Y EQUIPO DE TRANSPORTE", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("154005", "Vehículos", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1524", "EQUIPO DE OFICINA", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("152405", "Muebles y enseres", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1528", "EQUIPO DE CÓMPUTO Y COMUNICACIÓN", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, False),
    ("152805", "Equipo de cómputo", TipoCuenta.ACTIVO, NaturalezaCuenta.DEBITO, True),
    ("1592", "DEPRECIACIÓN ACUMULADA", TipoCuenta.ACTIVO, NaturalezaCuenta.CREDITO, False),
    ("159205", "Depreciación acumulada", TipoCuenta.ACTIVO, NaturalezaCuenta.CREDITO, True),

    # ── 2. PASIVO ──
    ("2", "PASIVO", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("22", "PROVEEDORES", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("2205", "NACIONALES", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("220505", "Proveedores nacionales", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    # La mercancía que entró a la bodega y cuya factura no ha llegado: la deja
    # la recepción del WMS y la salda la factura del proveedor.
    ("220510", "Mercancía recibida por facturar", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("23", "CUENTAS POR PAGAR", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("2335", "COSTOS Y GASTOS POR PAGAR", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("233595", "Otros costos y gastos por pagar", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("2365", "RETENCIÓN EN LA FUENTE", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("236540", "Compras", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("236525", "Honorarios", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("236530", "Servicios", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("2367", "IMPUESTO A LAS VENTAS RETENIDO", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("236701", "IVA retenido", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("2368", "IMPUESTO DE INDUSTRIA Y COMERCIO RETENIDO", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("236801", "ICA retenido", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("2370", "RETENCIONES Y APORTES DE NÓMINA", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("237005", "Aportes a EPS", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("237006", "Aportes a fondo de pensiones", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("2380", "ACREEDORES VARIOS", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("238095", "Otros acreedores", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("24", "IMPUESTOS, GRAVÁMENES Y TASAS", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("2408", "IMPUESTO SOBRE LAS VENTAS POR PAGAR", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("240805", "IVA generado", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("240810", "IVA descontable", TipoCuenta.PASIVO, NaturalezaCuenta.DEBITO, True),
    ("2412", "DE INDUSTRIA Y COMERCIO", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("241205", "Impuesto de industria y comercio", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("25", "OBLIGACIONES LABORALES", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("2505", "SALARIOS POR PAGAR", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("250505", "Salarios por pagar", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),
    ("2510", "CESANTÍAS CONSOLIDADAS", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, False),
    ("251005", "Cesantías consolidadas", TipoCuenta.PASIVO, NaturalezaCuenta.CREDITO, True),

    # ── 3. PATRIMONIO ──
    ("3", "PATRIMONIO", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, False),
    ("31", "CAPITAL SOCIAL", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, False),
    ("3105", "CAPITAL SUSCRITO Y PAGADO", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, False),
    ("310505", "Capital autorizado", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, True),
    ("36", "RESULTADOS DEL EJERCICIO", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, False),
    ("3605", "UTILIDAD DEL EJERCICIO", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, False),
    ("360505", "Utilidad del ejercicio", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, True),
    ("37", "RESULTADOS DE EJERCICIOS ANTERIORES", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, False),
    ("370505", "Utilidades acumuladas", TipoCuenta.PATRIMONIO, NaturalezaCuenta.CREDITO, True),

    # ── 4. INGRESOS ──
    ("4", "INGRESOS", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, False),
    ("41", "OPERACIONALES", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, False),
    ("4135", "COMERCIO AL POR MAYOR Y AL POR MENOR", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, False),
    ("413500", "Venta de mercancías", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, True),
    ("4155", "ACTIVIDADES DE SERVICIO", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, False),
    ("415500", "Servicios prestados", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, True),
    ("4175", "TRANSPORTE, ALMACENAMIENTO Y COMUNICACIONES", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, False),
    ("417505", "Servicio de transporte", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, True),
    ("417510", "Almacenamiento y bodegaje", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, True),
    ("4210", "FINANCIEROS", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, False),
    ("421005", "Intereses", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, True),
    ("4275", "DEVOLUCIONES EN VENTAS", TipoCuenta.INGRESO, NaturalezaCuenta.DEBITO, False),
    ("427500", "Devoluciones en ventas", TipoCuenta.INGRESO, NaturalezaCuenta.DEBITO, True),
    ("4295", "DIVERSOS", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, False),
    ("429595", "Sobrantes de inventario", TipoCuenta.INGRESO, NaturalezaCuenta.CREDITO, True),

    # ── 5. GASTOS ──
    ("5", "GASTOS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("51", "OPERACIONALES DE ADMINISTRACIÓN", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("5105", "GASTOS DE PERSONAL", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("510506", "Sueldos", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("510527", "Aportes a EPS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("510530", "Aportes a fondo de pensiones", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5110", "HONORARIOS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("511010", "Revisoría fiscal", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("511095", "Otros honorarios", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5120", "ARRENDAMIENTOS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("512010", "Construcciones y edificaciones", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5130", "SEGUROS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("513025", "Cumplimiento", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5135", "SERVICIOS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("513525", "Acueducto y alcantarillado", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("513530", "Energía eléctrica", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("513535", "Teléfono e internet", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("513595", "Otros servicios", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5160", "DEPRECIACIONES", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("516005", "Gasto por depreciación", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5305", "FINANCIEROS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("530505", "Gastos bancarios", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("530520", "Intereses", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5399", "OTROS GASTOS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("539995", "Gastos diversos", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("5315", "GASTOS EXTRAORDINARIOS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("531595", "Faltantes y bajas de inventario", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),

    # ── 6. COSTOS ──
    ("6", "COSTOS DE VENTAS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("61", "COSTO DE VENTAS Y DE PRESTACIÓN DE SERVICIOS", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("6135", "COMERCIO AL POR MAYOR Y AL POR MENOR", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("613500", "Costo de mercancía vendida", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("6175", "TRANSPORTE, ALMACENAMIENTO Y COMUNICACIONES", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, False),
    ("617505", "Costo del servicio de transporte", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("617510", "Combustibles y lubricantes", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
    ("617515", "Peajes", TipoCuenta.EGRESO, NaturalezaCuenta.DEBITO, True),
]


# ─── Qué cuenta cumple cada papel ─────────────────────────────────────────────
#
# (evento, papel, código de cuenta, naturaleza[, condición])
#
# Esto es lo que saca los códigos de dentro del código. Cada línea dice: «cuando
# pase ESTO, el papel de cartera lo cumple la cuenta 130505, al débito».

REGLAS: List[tuple] = [
    ("VENTA_FACTURA", "cartera", "130505", "DEBITO"),
    ("VENTA_FACTURA", "ingreso", "413500", "CREDITO"),
    ("VENTA_FACTURA", "iva_generado", "240805", "CREDITO"),
    ("VENTA_FACTURA", "retefuente", "135515", "DEBITO"),
    ("VENTA_FACTURA", "reteica", "135518", "DEBITO"),
    ("VENTA_FACTURA", "reteiva", "135517", "DEBITO"),

    ("VENTA_NOTA_CREDITO", "cartera", "130505", "CREDITO"),
    ("VENTA_NOTA_CREDITO", "ingreso", "427500", "DEBITO"),
    ("VENTA_NOTA_CREDITO", "iva_generado", "240805", "DEBITO"),

    ("COMPRA_FACTURA", "proveedor", "220505", "CREDITO"),
    ("COMPRA_FACTURA", "gasto", "539995", "DEBITO"),
    ("COMPRA_FACTURA", "inventario", "143505", "DEBITO"),
    # Cada concepto de compra a su cuenta. La regla específica de la condición
    # manda sobre la general de arriba, así que agregar un concepto nuevo es
    # agregar una línea acá y no tocar el código que factura.
    ("COMPRA_FACTURA", "gasto", "617510", "DEBITO", "COMBUSTIBLE"),
    ("COMPRA_FACTURA", "gasto", "617515", "DEBITO", "PEAJES"),
    ("COMPRA_FACTURA", "gasto", "512010", "DEBITO", "ARRENDAMIENTO"),
    ("COMPRA_FACTURA", "gasto", "513025", "DEBITO", "SEGUROS"),
    ("COMPRA_FACTURA", "gasto", "513530", "DEBITO", "SERVICIOS_PUBLICOS"),
    ("COMPRA_FACTURA", "gasto", "511095", "DEBITO", "HONORARIOS"),
    ("COMPRA_FACTURA", "gasto", "513595", "DEBITO", "VIGILANCIA"),

    ("COMPRA_FACTURA", "iva_descontable", "240810", "DEBITO"),
    ("COMPRA_FACTURA", "retefuente", "236540", "CREDITO"),
    ("COMPRA_FACTURA", "reteica", "236801", "CREDITO"),
    ("COMPRA_FACTURA", "reteiva", "236701", "CREDITO"),

    ("RECAUDO_CLIENTE", "banco", "111005", "DEBITO"),
    ("RECAUDO_CLIENTE", "caja", "110505", "DEBITO"),
    ("RECAUDO_CLIENTE", "cartera", "130505", "CREDITO"),
    ("RECAUDO_CLIENTE", "retefuente", "135515", "DEBITO"),
    ("RECAUDO_CLIENTE", "descuento", "539995", "DEBITO"),

    ("PAGO_PROVEEDOR", "proveedor", "220505", "DEBITO"),
    ("PAGO_PROVEEDOR", "banco", "111005", "CREDITO"),
    ("PAGO_PROVEEDOR", "caja", "110505", "CREDITO"),
    ("PAGO_PROVEEDOR", "descuento", "421005", "CREDITO"),

    ("INVENTARIO_SALIDA", "costo_venta", "613500", "DEBITO"),
    ("INVENTARIO_SALIDA", "inventario", "143505", "CREDITO"),
    ("INVENTARIO_ENTRADA", "inventario", "143505", "DEBITO"),
    ("INVENTARIO_ENTRADA", "proveedor", "220505", "CREDITO"),
    ("INVENTARIO_ENTRADA", "gasto", "539995", "CREDITO"),
    # Cruce de tres vías: la recepción acredita «por facturar» y la factura del
    # proveedor ligada a esa recepción lo debita, en vez de cargar a gasto.
    ("INVENTARIO_ENTRADA", "por_facturar", "220510", "CREDITO"),
    ("COMPRA_FACTURA", "por_facturar", "220510", "DEBITO"),
    ("INVENTARIO_DEVOLUCION", "inventario", "143505", "DEBITO"),
    ("INVENTARIO_DEVOLUCION", "costo_venta", "613500", "CREDITO"),
    ("INVENTARIO_MERMA", "merma", "531595", "DEBITO"),
    ("INVENTARIO_MERMA", "inventario", "143505", "CREDITO"),
    ("INVENTARIO_SOBRANTE", "inventario", "143505", "DEBITO"),
    ("INVENTARIO_SOBRANTE", "sobrante", "429595", "CREDITO"),

    ("NOMINA_LIQUIDACION", "gasto_nomina", "510506", "DEBITO"),
    ("NOMINA_LIQUIDACION", "salud", "237005", "CREDITO"),
    ("NOMINA_LIQUIDACION", "pension", "237006", "CREDITO"),
    ("NOMINA_LIQUIDACION", "retefuente", "236540", "CREDITO"),
    ("NOMINA_LIQUIDACION", "neto_pagar", "250505", "CREDITO"),
    ("NOMINA_LIQUIDACION", "prestaciones", "251005", "CREDITO"),
    ("NOMINA_LIQUIDACION", "parafiscales", "238095", "CREDITO"),

    ("ACTIVO_DEPRECIACION", "gasto_depreciacion", "516005", "DEBITO"),
    ("ACTIVO_DEPRECIACION", "depreciacion_acumulada", "159205", "CREDITO"),

    # El transporte es la operación de esta plataforma, así que lleva sus propias
    # cuentas de ingreso y costo en vez de mezclarse con el comercio.
    ("SERVICIO_EJECUTADO", "cartera", "130505", "DEBITO"),
    ("SERVICIO_EJECUTADO", "ingreso", "417505", "CREDITO"),
    ("SERVICIO_EJECUTADO", "iva_generado", "240805", "CREDITO"),
    ("SERVICIO_EJECUTADO", "costo", "617505", "DEBITO"),
    # El costo del servicio se acumula contra cuentas por pagar: la factura del
    # combustible o del conductor llega después de prestarlo, y el gasto es del
    # mes en que se prestó, no del mes en que llega el papel.
    ("SERVICIO_EJECUTADO", "costo_por_pagar", "233595", "CREDITO"),

    ("POS_VENTA", "caja", "110505", "DEBITO"),
    ("POS_VENTA", "banco", "111005", "DEBITO"),
    ("POS_VENTA", "ingreso", "413500", "CREDITO"),
    ("POS_VENTA", "iva_generado", "240805", "CREDITO"),
    ("POS_VENTA", "costo_venta", "613500", "DEBITO"),
    ("POS_VENTA", "inventario", "143505", "CREDITO"),
    ("POS_DEVOLUCION", "caja", "110505", "CREDITO"),
    ("POS_DEVOLUCION", "banco", "111005", "CREDITO"),
    ("POS_DEVOLUCION", "devolucion", "427500", "DEBITO"),
    ("POS_DEVOLUCION", "iva_generado", "240805", "DEBITO"),
    ("POS_DEVOLUCION", "costo_venta", "613500", "CREDITO"),
    ("POS_DEVOLUCION", "inventario", "143505", "DEBITO"),
]


# ─── Reglas tributarias ───────────────────────────────────────────────────────
#
# (impuesto, concepto, tarifa, base mínima en UVT, papel, cuenta,
#  excluye autorretenedor)
#
# Las tarifas son las de uso corriente en Colombia y son EDITABLES: cuando
# cambien se agrega una regla nueva con su vigencia, no se edita esta. La base
# mínima va en UVT porque así la fija la norma; el motor la convierte a pesos con
# la UVT del año del documento.

IMPUESTOS: List[Tuple[str, str, str, str, str, str, bool]] = [
    ("IVA", "General 19%", "19.0", "0", "iva_generado", "240805", False),
    ("IVA", "Reducida 5%", "5.0", "0", "iva_generado", "240805", False),
    ("IVA", "Excluido", "0.0", "0", "iva_generado", "240805", False),

    ("RETEFUENTE", "Compras generales", "2.5", "27", "retefuente", "236540", True),
    ("RETEFUENTE", "Servicios generales", "4.0", "4", "retefuente", "236530", True),
    ("RETEFUENTE", "Honorarios", "11.0", "0", "retefuente", "236525", True),
    ("RETEFUENTE", "Arrendamientos", "3.5", "27", "retefuente", "236540", True),
    ("RETEFUENTE", "Transporte de carga", "1.0", "4", "retefuente", "236530", True),

    ("RETEIVA", "General", "15.0", "0", "reteiva", "236701", True),
    ("RETEICA", "General", "0.414", "0", "reteica", "236801", True),
]


# ─── La siembra ───────────────────────────────────────────────────────────────

async def sembrar_empresa(db: AsyncSession, empresa_id: int) -> Dict[str, int]:
    """Deja una empresa lista para contabilizar.

    Es idempotente: se puede llamar sobre una empresa que ya tiene cuentas y no
    duplica ni pisa lo que alguien haya cambiado. Eso importa porque se llama al
    arrancar y porque el administrador puede querer completar el plan de una
    empresa vieja sin perder sus ajustes.
    """
    cuentas: Dict[str, ERPPlanCuenta] = {
        c.codigo: c for c in (await db.execute(select(ERPPlanCuenta).where(
            ERPPlanCuenta.empresa_id == empresa_id))).scalars().all()
    }

    nuevas = 0
    for codigo, nombre, tipo, naturaleza, mueve in PUC:
        if codigo in cuentas:
            continue
        # El padre es el código sin los dos últimos dígitos. La jerarquía sale de
        # la propia codificación del PUC, así que no hay que declararla aparte ni
        # puede quedar inconsistente con los códigos.
        padre = None
        for largo in (len(codigo) - 2, len(codigo) - 1):
            if largo > 0 and codigo[:largo] in cuentas:
                padre = cuentas[codigo[:largo]]
                break

        cuenta = ERPPlanCuenta(
            empresa_id=empresa_id, codigo=codigo, nombre=nombre, tipo=tipo,
            naturaleza=naturaleza, nivel=len(codigo),
            cuenta_padre_id=padre.id if padre else None,
            es_auxiliar=mueve, acepta_movimientos=mueve, norma="NIIF")
        db.add(cuenta)
        await db.flush()
        cuentas[codigo] = cuenta
        nuevas += 1

    # ── Reglas contables ──
    existentes = {
        (r.evento, r.papel, r.condicion)
        for r in (await db.execute(select(ERPReglaContable).where(
            ERPReglaContable.empresa_id == empresa_id))).scalars().all()
    }
    reglas = 0
    for fila in REGLAS:
        evento, papel, codigo, naturaleza = fila[:4]
        # La quinta posición, si viene, es la condición: la regla específica
        # manda sobre la general del mismo papel.
        condicion = fila[4] if len(fila) > 4 else ""
        if (evento, papel, condicion) in existentes:
            continue
        cuenta = cuentas.get(codigo)
        if cuenta is None:
            continue
        db.add(ERPReglaContable(
            empresa_id=empresa_id, evento=evento, papel=papel,
            condicion=condicion, cuenta_id=cuenta.id, naturaleza=naturaleza,
            descripcion=f"{papel} de {evento}"
                        + (f" · {condicion}" if condicion else ""),
            activa=True))
        reglas += 1

    # ── Reglas tributarias ──
    hay_impuestos = (await db.execute(select(ERPReglaImpuesto.id).where(
        ERPReglaImpuesto.empresa_id == empresa_id).limit(1))).first()
    impuestos = 0
    if not hay_impuestos:
        # Desde el 1 de enero del año en curso: fechar la vigencia más atrás
        # afirmaría que estas tarifas ya regían entonces, y eso no lo sabemos.
        desde = date(date.today().year, 1, 1)
        for imp, concepto, tarifa, uvt, papel, codigo, excluye in IMPUESTOS:
            cuenta = cuentas.get(codigo)
            db.add(ERPReglaImpuesto(
                empresa_id=empresa_id, impuesto=imp, concepto=concepto,
                tarifa=tarifa, base_minima_uvt=uvt, base_minima_pesos=0,
                vigente_desde=desde, vigente_hasta=None,
                papel=papel, cuenta_id=cuenta.id if cuenta else None,
                excluye_autorretenedor=excluye, activa=True,
                descripcion=f"{imp} · {concepto}"))
            impuestos += 1

    return {"cuentas": nuevas, "reglas": reglas, "impuestos": impuestos}


async def sembrar_parametros(db: AsyncSession) -> int:
    """Los valores fiscales que se conocen con certeza.

    Solo se siembra lo que se sabe. Un año sin UVT cargada hace que las bases
    mínimas en UVT no filtren —lo cual se nota y se corrige—; una UVT inventada
    desplaza en silencio todas las retenciones que dependen de ella, y nadie
    revisa un campo que ya aparece lleno.
    """
    conocidos: List[Tuple[int, str, str, str]] = [
        (2024, "UVT", "47065", "DIAN · Resolución 187 de 2023"),
        (2025, "UVT", "49799", "DIAN · Resolución 193 de 2024"),
        (2024, "SMMLV", "1300000", "Decreto 2292 de 2023"),
        (2025, "SMMLV", "1423500", "Decreto 1572 de 2024"),
    ]
    puestos = 0
    for anio, clave, valor, fuente in conocidos:
        ya = (await db.execute(select(ERPParametroFiscal.id).where(
            ERPParametroFiscal.anio == anio,
            ERPParametroFiscal.clave == clave))).first()
        if ya:
            continue
        db.add(ERPParametroFiscal(anio=anio, clave=clave, valor=valor,
                                  fuente=fuente,
                                  descripcion=f"{clave} {anio}"))
        puestos += 1
    return puestos
