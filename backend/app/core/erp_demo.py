"""
Siembra de volumen para la cuenta de demostración.

QUÉ ES Y QUÉ NO ES
Esto genera la operación de varios años de una empresa de transporte y logística
—terceros, facturación, compras, recaudos, pagos, nómina, activos y su
depreciación— y la contabiliza **con el motor de verdad**. No inserta asientos a
mano: cada comprobante pasa por `erp_motor.asentar`, con sus reglas, su período y
su cuadre. Un sembrador que escribiera directamente en `erp_comprobante_lineas`
produciría una base que se ve llena y miente, porque contendría combinaciones que
el sistema real nunca crearía; y entonces medir el desempeño sobre ella no diría
nada del desempeño real.

La contrapartida es que sembrar cuesta tiempo. Es el precio de que las cifras
sean ciertas: al terminar, el balance de comprobación cuadra, y eso es
comprobable.

LOS DATOS SON VEROSÍMILES, NO ALEATORIOS
Una empresa real no factura lo mismo todos los días. Acá hay estacionalidad
—diciembre y julio pesan más—, crecimiento año a año, clientes grandes que
concentran facturación, facturas que se pagan tarde y algunas que no se pagan.
Sin eso, la cartera por edades sale plana y no sirve para ver nada.

DETERMINISTA
Se siembra con una semilla fija, así que dos corridas producen exactamente los
mismos datos. Un problema de desempeño que aparece una vez se puede volver a
reproducir; con datos al azar, no.
"""
import random
import time
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import erp_motor, erp_semilla
from app.core.erp_motor import Linea
from app.infrastructure.models.erp import (
    EstadoFactura, ERPActivoFijo, ERPBanco, ERPCentroCosto, ERPCuentaBancaria,
    ERPEmpresa, ERPFacturaCliente, ERPFacturaProveedor, ERPLineaFacturaCliente,
    ERPPago, ERPPlanCuenta, ERPProyecto, TipoComprobante,
)
from app.infrastructure.models.erp import (
    ERPLineaPresupuesto, ERPMovimientoBancario, ERPPresupuesto,
)
from app.infrastructure.models.erp_gestion import ERPInductor
from app.infrastructure.models.erp_nucleo import ERPTercero

SEMILLA = 20260902
CENTAVO = Decimal("0.01")


# ─── Vocabulario ──────────────────────────────────────────────────────────────

_RAICES = [
    "Andina", "Caribe", "Pacífico", "Cordillera", "Magdalena", "Sabana",
    "Altiplano", "Orinoquía", "Amazonía", "Guajira", "Tolima", "Antioqueña",
    "Vallecaucana", "Santandereana", "Boyacense", "Nariñense", "Chocoana",
    "Cafetera", "Llanera", "Costeña",
]
_GIROS = [
    "Logística", "Transportes", "Distribuciones", "Comercializadora",
    "Almacenes", "Suministros", "Industrias", "Alimentos", "Ferretería",
    "Textiles", "Agroindustria", "Manufacturas", "Importaciones",
    "Representaciones", "Servicios", "Ingeniería", "Construcciones",
]
_FORMAS = ["SAS", "SAS", "SAS", "LTDA", "SA", "SAS"]

_NOMBRES = [
    "Carolina", "Andrés", "Diana", "Julián", "Paola", "Camilo", "Natalia",
    "Sebastián", "Ángela", "Mauricio", "Liliana", "Óscar", "Sandra", "Iván",
    "Claudia", "Fernando", "Marcela", "Ricardo", "Adriana", "Germán",
]
_APELLIDOS = [
    "Gómez", "Rodríguez", "Martínez", "Ramírez", "Cárdenas", "Ospina",
    "Restrepo", "Villegas", "Quintero", "Bustamante", "Zapata", "Naranjo",
    "Betancur", "Escobar", "Arango", "Peláez", "Mejía", "Salazar",
]

# (ciudad, código DANE). El municipio decide la tarifa de ICA, así que va de
# verdad y no inventado.
_CIUDADES = [
    ("Bogotá D.C.", "11001"), ("Medellín", "05001"), ("Cali", "76001"),
    ("Barranquilla", "08001"), ("Cartagena", "13001"), ("Bucaramanga", "68001"),
    ("Pereira", "66001"), ("Manizales", "17001"), ("Cúcuta", "54001"),
    ("Ibagué", "73001"), ("Villavicencio", "50001"), ("Santa Marta", "47001"),
    ("Neiva", "41001"), ("Armenia", "63001"), ("Popayán", "19001"),
    ("Montería", "23001"), ("Buenaventura", "76109"), ("Yopal", "85001"),
]

_SERVICIOS = [
    ("Flete nacional Bogotá–Medellín", 2_850_000),
    ("Flete nacional Bogotá–Barranquilla", 4_200_000),
    ("Flete nacional Medellín–Cali", 2_400_000),
    ("Flete urbano de distribución", 480_000),
    ("Almacenamiento en bodega (mes)", 3_600_000),
    ("Cross-docking por posición", 190_000),
    ("Alquiler de estibas (mes)", 850_000),
    ("Cargue y descargue", 320_000),
    ("Transporte refrigerado", 5_100_000),
    ("Carga extradimensionada", 8_700_000),
    ("Gestión aduanera", 1_450_000),
    ("Última milla — paquete", 22_000),
]

# (concepto, papel, condición contable, valor típico). La condición es lo que
# hace que cada compra caiga en su cuenta: sin ella todo termina en «gastos
# diversos» y el plan de cuentas parece de tres renglones.
_COMPRAS = [
    ("Combustible ACPM", "gasto", "COMBUSTIBLE", 6_800_000),
    ("Peajes", "gasto", "PEAJES", 2_300_000),
    ("Llantas", "inventario", "", 4_900_000),
    ("Repuestos y mantenimiento", "inventario", "", 1_750_000),
    ("Arrendamiento de bodega", "gasto", "ARRENDAMIENTO", 12_000_000),
    ("Servicios públicos", "gasto", "SERVICIOS_PUBLICOS", 1_900_000),
    ("Honorarios contables", "gasto", "HONORARIOS", 2_800_000),
    ("Vigilancia y aseo", "gasto", "VIGILANCIA", 3_400_000),
    ("Pólizas de seguro", "gasto", "SEGUROS", 7_200_000),
    ("Papelería y aseo", "gasto", "", 380_000),
]

_ACTIVOS = [
    ("Tractocamión", 320_000_000, 120), ("Remolque", 95_000_000, 120),
    ("Montacargas", 78_000_000, 96), ("Camión sencillo", 145_000_000, 120),
    ("Camioneta de reparto", 89_000_000, 96),
    ("Equipo de cómputo", 4_200_000, 36), ("Servidor", 22_000_000, 60),
    ("Estantería de bodega", 18_000_000, 120),
    ("Báscula camionera", 41_000_000, 120),
]

_CENTROS = [
    ("CC-01", "Transporte de carga", "OPERATIVO"),
    ("CC-02", "Almacenamiento", "OPERATIVO"),
    ("CC-03", "Distribución urbana", "OPERATIVO"),
    ("CC-04", "Administración", "ADMINISTRATIVO"),
    ("CC-05", "Comercial", "COMERCIAL"),
    ("CC-06", "Mantenimiento de flota", "OPERATIVO"),
]

# Diciembre y julio mueven más carga; enero y febrero son flojos. Sin esta curva
# la serie mensual sale plana y ningún reporte de tendencia dice nada.
_ESTACIONALIDAD = [0.62, 0.71, 0.94, 0.97, 1.03, 1.08,
                   1.21, 1.05, 1.02, 1.09, 1.18, 1.42]


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def _nit(az: random.Random) -> str:
    """Un NIT con la pinta de los de verdad: 8xx o 9xx y nueve dígitos."""
    return f"{az.choice([8, 9])}{az.randint(0, 99):02d}{az.randint(0, 999999):06d}"


# ─── El progreso ──────────────────────────────────────────────────────────────

class Progreso:
    """Cuenta lo hecho y el tiempo, para poder decir cuánto costó cada parte."""

    def __init__(self, avisar=None):
        self.inicio = time.monotonic()
        self.marcas: List[Tuple[str, float, int]] = []
        self._ultimo = self.inicio
        self._avisar = avisar or (lambda t: None)

    def paso(self, nombre: str, cantidad: int) -> None:
        ahora = time.monotonic()
        self.marcas.append((nombre, ahora - self._ultimo, cantidad))
        self._ultimo = ahora
        self._avisar(f"  {nombre}: {cantidad} en {self.marcas[-1][1]:.1f}s")

    def resumen(self) -> dict:
        return {
            "segundos": round(time.monotonic() - self.inicio, 1),
            "pasos": [{"paso": n, "segundos": round(s, 1), "cantidad": c}
                      for n, s, c in self.marcas],
        }


# ─── La siembra ───────────────────────────────────────────────────────────────

async def sembrar_volumen(
    db: AsyncSession, *,
    empresa_id: Optional[int] = None,
    desde: date,
    hasta: date,
    terceros: int = 300,
    facturas_por_dia_habil: int = 14,
    usuario: str = "sembrador",
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera y contabiliza la operación de una empresa entre dos fechas.

    Devuelve el recuento de lo creado y el tiempo de cada parte, que es lo que
    permite decir dónde está el costo.
    """
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)
    p = Progreso(avisar)

    async def confirmar() -> None:
        """Consolida y REPONE el esquema.

        El `search_path` vive en la conexión, no en la sesión: al consolidar, la
        conexión vuelve al pool y la siguiente puede ser otra, sin esquema. Es la
        misma trampa que ya costó dos fallos en producción, y acá aparece porque
        se consolida muchas veces durante la siembra.
        """
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    # ── La empresa ──
    if empresa_id is None:
        empresa = (await db.execute(select(ERPEmpresa).limit(1))).scalar_one_or_none()
        if empresa is None:
            empresa = ERPEmpresa(
                nit="901456789", razon_social="Transportes Demo SAS",
                nombre_comercial="Demo Flota", pais="Colombia",
                ciudad="Bogotá D.C.", moneda_base="COP",
                regimen_fiscal="Responsable de IVA", sector="Transporte de carga")
            db.add(empresa)
            await db.flush()
        empresa_id = empresa.id

    await erp_semilla.sembrar_parametros(db)
    await erp_semilla.sembrar_empresa(db, empresa_id)
    await db.flush()

    # La UVT de los años sembrados tiene que existir, o las retenciones con base
    # mínima se bloquean —que es lo correcto— y no se podría facturar.
    for anio in range(desde.year, hasta.year + 1):
        ya = (await db.execute(text(
            "SELECT 1 FROM erp_parametros_fiscales WHERE anio=:a AND clave='UVT'"),
            {"a": anio})).first()
        if not ya:
            # Se proyecta desde 2025 con el 5% anual, y se DICE que es estimada.
            # Una cifra estimada rotulada como tal es utilizable; una estimada que
            # se presenta como oficial es una trampa para el que la lea después.
            base, desde_anio = Decimal("49799"), 2025
            valor = base * (Decimal("1.05") ** (anio - desde_anio))
            await db.execute(text(
                "INSERT INTO erp_parametros_fiscales "
                "(anio, clave, valor, fuente, descripcion, created_at, updated_at) "
                "VALUES (:a, 'UVT', :v, :f, :d, now(), now())"),
                {"a": anio, "v": int(valor), "d": f"UVT {anio}",
                 "f": "ESTIMADA para la cuenta de demostración — no es oficial"})
    await db.flush()

    cuentas: Dict[str, ERPPlanCuenta] = {
        c.codigo: c for c in (await db.execute(select(ERPPlanCuenta).where(
            ERPPlanCuenta.empresa_id == empresa_id))).scalars().all()
    }

    # ── Centros de costo ──
    centros: List[ERPCentroCosto] = list((await db.execute(select(ERPCentroCosto))).scalars().all())
    if not centros:
        for codigo, nombre, tipo in _CENTROS:
            cc = ERPCentroCosto(codigo=codigo, nombre=nombre, tipo=tipo,
                                empresa_id=empresa_id,
                                responsable=f"{az.choice(_NOMBRES)} {az.choice(_APELLIDOS)}",
                                presupuesto_anual=az.randint(200, 1800) * 1_000_000)
            db.add(cc)
            centros.append(cc)
        await db.flush()
    p.paso("centros de costo", len(centros))

    # ── Bancos y cuentas ──
    banco = (await db.execute(select(ERPBanco).limit(1))).scalar_one_or_none()
    if banco is None:
        banco = ERPBanco(nombre="Bancolombia", codigo="007", pais="Colombia")
        db.add(banco)
        await db.flush()
    cuenta_banco = (await db.execute(select(ERPCuentaBancaria).limit(1))).scalar_one_or_none()
    if cuenta_banco is None:
        cuenta_banco = ERPCuentaBancaria(
            empresa_id=empresa_id, banco_id=banco.id, numero="1234567890",
            tipo="CORRIENTE", moneda="COP",
            saldo_banco=0, saldo_contable=0, saldo_disponible=0,
            cuenta_contable_id=cuentas["111005"].id if "111005" in cuentas else None)
        db.add(cuenta_banco)
        await db.flush()

    # ── Terceros ──
    ya_terceros = list((await db.execute(select(ERPTercero).where(
        ERPTercero.empresa_id == empresa_id))).scalars().all())
    nits_usados = {t.numero_identificacion for t in ya_terceros}
    nuevos: List[ERPTercero] = []
    while len(ya_terceros) + len(nuevos) < terceros:
        nit = _nit(az)
        if nit in nits_usados:
            continue
        nits_usados.add(nit)
        natural = az.random() < 0.18
        ciudad, dane = az.choice(_CIUDADES)
        if natural:
            nombre = az.choice(_NOMBRES)
            ap1, ap2 = az.choice(_APELLIDOS), az.choice(_APELLIDOS)
            razon = f"{nombre} {ap1} {ap2}"
        else:
            razon = (f"{az.choice(_GIROS)} {az.choice(_RAICES)} "
                     f"{az.choice(_FORMAS)}")
        # Papeles solapados a propósito: una misma empresa suele ser cliente y
        # proveedor, y es justo el caso que los maestros separados rompen.
        cliente = az.random() < 0.72
        proveedor = az.random() < 0.38
        if not cliente and not proveedor:
            cliente = True
        t = ERPTercero(
            empresa_id=empresa_id,
            tipo_identificacion="CC" if natural else "NIT",
            numero_identificacion=nit,
            digito_verificacion=(None if natural
                                 else erp_motor.digito_verificacion(nit)),
            razon_social=razon, es_persona_natural=natural,
            es_cliente=cliente, es_proveedor=proveedor,
            ciudad=ciudad, codigo_municipio=dane, pais="Colombia",
            departamento=ciudad,
            telefono=f"3{az.randint(0, 99):02d}{az.randint(0, 9999999):07d}",
            email=f"contacto@{_sin_tildes(razon.split()[0]).lower()}{az.randint(1, 99)}.com.co",
            # Las condiciones tributarias en proporciones realistas: los grandes
            # contribuyentes y autorretenedores son pocos, pero existen, y son
            # los que hacen que una retención no se practique.
            autorretenedor=az.random() < 0.09,
            gran_contribuyente=az.random() < 0.05,
            agente_retencion=az.random() < 0.12,
            exento_retencion=az.random() < 0.03,
            regimen="COMUN" if not natural else "SIMPLIFICADO",
            dias_credito=az.choice([0, 15, 30, 30, 45, 60, 90]),
            cupo_credito=az.choice([0, 20, 50, 100, 200, 500]) * 1_000_000,
            responsabilidades=[],
        )
        nuevos.append(t)
        db.add(t)
    await db.flush()
    ya_terceros += nuevos
    clientes = [t for t in ya_terceros if t.es_cliente]
    proveedores = [t for t in ya_terceros if t.es_proveedor] or clientes
    p.paso("terceros", len(ya_terceros))

    # Unos pocos clientes concentran la facturación, como en la vida real. Con
    # todos igual de probables, la cartera sale uniforme y no se parece a nada.
    grandes = az.sample(clientes, max(1, len(clientes) // 12))
    def _un_cliente():
        return az.choice(grandes) if az.random() < 0.42 else az.choice(clientes)

    # ── Activos fijos ──
    activos: List[ERPActivoFijo] = []
    n_activos = 0
    if not (await db.execute(select(ERPActivoFijo.id).limit(1))).first():
        for i in range(1, 121):
            nombre, valor, vida = az.choice(_ACTIVOS)
            compra = desde - timedelta(days=az.randint(0, 1500))
            af = ERPActivoFijo(
                empresa_id=empresa_id, codigo=f"AF-{i:04d}",
                nombre=f"{nombre} {i:03d}", categoria=nombre,
                fecha_adquisicion=compra,
                valor_adquisicion=valor * az.uniform(0.85, 1.15),
                valor_residual=valor * 0.1,
                vida_util_meses=vida, metodo_depreciacion="LINEA_RECTA",
                depreciacion_acumulada=0, valor_libro=valor,
                centro_costo_id=az.choice(centros).id,
                ubicacion=az.choice(_CIUDADES)[0], estado="EN_USO")
            db.add(af)
            activos.append(af)
        await db.flush()
        n_activos = len(activos)
    p.paso("activos fijos", n_activos)

    # ── Proyectos ──
    proyectos: List[ERPProyecto] = list((await db.execute(select(ERPProyecto))).scalars().all())
    if not proyectos:
        for i in range(1, 25):
            cli = _un_cliente()
            # El margen se acota al rango: sembrar un solo mes es válido —se usa
            # para probar el propio sembrador— y no puede reventar por eso.
            margen = max(0, (hasta - desde).days - 90)
            inicio = desde + timedelta(days=az.randint(0, margen))
            pr = ERPProyecto(
                empresa_id=empresa_id, codigo=f"PRY-{i:03d}",
                nombre=f"Operación logística {cli.razon_social[:40]}",
                cliente=cli.razon_social, fecha_inicio=inicio,
                # Sin centro de costo un proyecto no se puede medir: sus
                # ingresos y costos no se pueden separar de los del resto.
                centro_costo_id=az.choice(centros).id,
                fecha_fin=inicio + timedelta(days=az.randint(120, 540)),
                presupuesto_total=az.randint(80, 900) * 1_000_000,
                ejecutado_total=0, ingresos_total=0,
                estado=az.choice(["EN_EJECUCION", "EN_EJECUCION",
                                  "EN_EJECUCION", "COMPLETADO"]))
            db.add(pr)
            proyectos.append(pr)
        await db.flush()
    p.paso("proyectos", len(proyectos))

    # ── La operación día a día ──
    #
    # Se recorre el calendario y no un contador de facturas: así la distribución
    # por mes, la estacionalidad y la antigüedad de la cartera salen solas y son
    # coherentes entre sí.
    conteo = {"facturas_cliente": 0, "facturas_proveedor": 0, "pagos": 0,
              "comprobantes": 0, "nomina": 0, "depreciacion": 0,
              "presupuestos": 0, "lineas_presupuesto": 0, "inductores": 0,
              "movimientos_banco": 0}
    pendientes: List[Tuple[ERPFacturaCliente, date]] = []
    por_pagar: List[Tuple[ERPFacturaProveedor, date]] = []
    consecutivo_fc = consecutivo_fp = consecutivo_pago = 0
    crecimiento_anual = 1.18

    dia = desde
    mes_actual = (desde.year, desde.month)
    while dia <= hasta:
        # El cierre del mes anterior se dispara al cambiar de mes, no en un día
        # concreto: atarlo al día 31 lo hacía fallar cuando ese día caía en fin
        # de semana —el bucle los salta— y el mes se quedaba sin nómina ni
        # depreciación sin que nada avisara.
        if (dia.year, dia.month) != mes_actual:
            ultimo = dia - timedelta(days=1)
            await _cierre_de_mes(db, empresa_id, ultimo, az, centros, activos,
                                 usuario, conteo, crecimiento_anual, desde)
            mes_actual = (dia.year, dia.month)
            await confirmar()

        if dia.weekday() >= 5:
            dia += timedelta(days=1)
            continue

        anios = (dia.year - desde.year)
        factor = (_ESTACIONALIDAD[dia.month - 1] * (crecimiento_anual ** anios))
        del_dia = max(1, int(az.gauss(facturas_por_dia_habil * factor,
                                      facturas_por_dia_habil * 0.25)))

        # ── Facturas de venta ──
        for _ in range(del_dia):
            cli = _un_cliente()
            consecutivo_fc += 1
            n_lineas = az.choices([1, 2, 3, 4], weights=[52, 28, 14, 6])[0]
            subtotal = Decimal(0)
            detalle = []
            for _ in range(n_lineas):
                desc, precio = az.choice(_SERVICIOS)
                cant = az.choices([1, 1, 2, 3, 5, 10], weights=[45, 20, 15, 10, 6, 4])[0]
                unit = Decimal(int(precio * az.uniform(0.9, 1.25)))
                base = unit * cant
                subtotal += base
                detalle.append((desc, cant, unit, base))

            iva = (subtotal * Decimal("0.19")).quantize(Decimal("0.01"))
            total = subtotal + iva
            vence = dia + timedelta(days=cli.dias_credito or 30)

            fc = ERPFacturaCliente(
                empresa_id=empresa_id, numero=f"FV-{dia.year}-{consecutivo_fc:06d}",
                cliente_nombre=cli.razon_social, cliente_nit=cli.numero_identificacion,
                fecha=dia, fecha_vencimiento=vence,
                subtotal=subtotal, total_impuestos=iva, total=total, saldo=total,
                estado=EstadoFactura.EMITIDA,
                centro_costo_id=az.choice(centros).id,
                observaciones=None)
            db.add(fc)
            await db.flush()
            for desc, cant, unit, base in detalle:
                db.add(ERPLineaFacturaCliente(
                    factura_id=fc.id, descripcion=desc, cantidad=cant,
                    precio_unitario=unit, descuento_pct=0,
                    subtotal=base, total_impuesto=(base * Decimal("0.19")).quantize(Decimal("0.01")),
                    total=base + (base * Decimal("0.19")).quantize(Decimal("0.01"))))

            await erp_motor.asentar(
                db, empresa_id=empresa_id, evento="VENTA_FACTURA",
                tipo=TipoComprobante.DIARIO, fecha=dia,
                concepto=f"Factura de venta {fc.numero} · {cli.razon_social}",
                lineas=[Linea("cartera", debito=total, tercero_id=cli.id),
                        Linea("ingreso", credito=subtotal, tercero_id=cli.id),
                        Linea("iva_generado", credito=iva, tercero_id=cli.id)],
                usuario=usuario, documento_tipo="factura_cliente",
                documento_id=fc.id, documento_numero=fc.numero,
                centro_costo_id=fc.centro_costo_id)
            conteo["facturas_cliente"] += 1
            conteo["comprobantes"] += 1

            # El 88% se cobra; de esas, la mitad tarde. El 12% restante es la
            # cartera vencida que hace que el reporte de edades sirva de algo.
            if az.random() < 0.88:
                atraso = az.choices([0, 5, 15, 35, 70], weights=[38, 26, 18, 12, 6])[0]
                pendientes.append((fc, vence + timedelta(days=atraso)))

        # ── Compras: menos frecuentes que las ventas ──
        for _ in range(az.randint(2, 6)):
            if True:
                prov = az.choice(proveedores)
                desc, papel, condicion, precio = az.choice(_COMPRAS)
                consecutivo_fp += 1
                subtotal = Decimal(int(precio * az.uniform(0.8, 1.35)))
                iva = (subtotal * Decimal("0.19")).quantize(Decimal("0.01"))

                # La retención depende del tercero, y por eso se pregunta en vez
                # de aplicarse a ciegas: un autorretenedor no lleva retefuente.
                retencion = Decimal(0)
                if not prov.autorretenedor and not prov.exento_retencion:
                    retencion = (subtotal * Decimal("0.025")).quantize(Decimal("0.01"))

                neto = subtotal + iva - retencion
                vence = dia + timedelta(days=az.choice([15, 30, 30, 45, 60]))
                fp = ERPFacturaProveedor(
                    empresa_id=empresa_id,
                    numero_proveedor=f"FC-{dia.year}-{consecutivo_fp:06d}",
                    proveedor_nombre=prov.razon_social,
                    proveedor_nit=prov.numero_identificacion,
                    fecha=dia, fecha_vencimiento=vence,
                    subtotal=subtotal, total_impuestos=iva, retenciones=retencion,
                    total=subtotal + iva, neto_pagar=neto, saldo=neto,
                    estado=EstadoFactura.EMITIDA,
                    centro_costo_id=az.choice(centros).id)
                db.add(fp)
                await db.flush()

                lineas = [Linea(papel, debito=subtotal, tercero_id=prov.id,
                                condicion=condicion),
                          Linea("iva_descontable", debito=iva, tercero_id=prov.id),
                          Linea("proveedor", credito=neto, tercero_id=prov.id)]
                if retencion:
                    lineas.append(Linea("retefuente", credito=retencion,
                                        tercero_id=prov.id))
                await erp_motor.asentar(
                    db, empresa_id=empresa_id, evento="COMPRA_FACTURA",
                    tipo=TipoComprobante.DIARIO, fecha=dia,
                    concepto=f"Factura de compra {fp.numero_proveedor} · {desc}",
                    lineas=lineas, usuario=usuario,
                    documento_tipo="factura_proveedor", documento_id=fp.id,
                    documento_numero=fp.numero_proveedor,
                    centro_costo_id=fp.centro_costo_id)
                conteo["facturas_proveedor"] += 1
                conteo["comprobantes"] += 1

                if az.random() < 0.94:
                    por_pagar.append((fp, vence + timedelta(days=az.randint(0, 20))))

        # ── Recaudos y pagos que vencen hoy ──
        cobrar_hoy = [x for x in pendientes if x[1] <= dia]
        for fc, _ in cobrar_hoy:
            pendientes.remove((fc, _))
            consecutivo_pago += 1
            monto = Decimal(str(fc.saldo))
            if monto <= 0:
                continue
            pago = ERPPago(
                empresa_id=empresa_id, numero=f"RC-{dia.year}-{consecutivo_pago:06d}",
                tipo="COBRO", fecha=dia, monto=monto, moneda="COP",
                metodo_pago=az.choice(["TRANSFERENCIA", "TRANSFERENCIA",
                                       "CHEQUE", "EFECTIVO"]),
                estado="PROCESADO", factura_cliente_id=fc.id,
                cuenta_bancaria_id=cuenta_banco.id,
                referencia=fc.numero)
            db.add(pago)
            await db.flush()
            fc.saldo = 0
            fc.estado = EstadoFactura.PAGADA
            await erp_motor.asentar(
                db, empresa_id=empresa_id, evento="RECAUDO_CLIENTE",
                tipo=TipoComprobante.INGRESO, fecha=dia,
                concepto=f"Recaudo de {fc.numero} · {fc.cliente_nombre}",
                lineas=[Linea("banco", debito=monto),
                        Linea("cartera", credito=monto)],
                usuario=usuario, documento_tipo="pago", documento_id=pago.id,
                documento_numero=pago.numero)
            conteo["pagos"] += 1
            conteo["comprobantes"] += 1

        pagar_hoy = [x for x in por_pagar if x[1] <= dia]
        for fp, _ in pagar_hoy:
            por_pagar.remove((fp, _))
            consecutivo_pago += 1
            monto = Decimal(str(fp.saldo))
            if monto <= 0:
                continue
            pago = ERPPago(
                empresa_id=empresa_id, numero=f"CE-{dia.year}-{consecutivo_pago:06d}",
                tipo="PAGO", fecha=dia, monto=monto, moneda="COP",
                metodo_pago="TRANSFERENCIA", estado="PROCESADO",
                factura_proveedor_id=fp.id, cuenta_bancaria_id=cuenta_banco.id,
                referencia=fp.numero_proveedor)
            db.add(pago)
            await db.flush()
            fp.saldo = 0
            fp.estado = EstadoFactura.PAGADA
            await erp_motor.asentar(
                db, empresa_id=empresa_id, evento="PAGO_PROVEEDOR",
                tipo=TipoComprobante.EGRESO, fecha=dia,
                concepto=f"Pago de {fp.numero_proveedor} · {fp.proveedor_nombre}",
                lineas=[Linea("proveedor", debito=monto),
                        Linea("banco", credito=monto)],
                usuario=usuario, documento_tipo="pago", documento_id=pago.id,
                documento_numero=pago.numero)
            conteo["pagos"] += 1
            conteo["comprobantes"] += 1

        dia += timedelta(days=1)

    await _cierre_de_mes(db, empresa_id, hasta, az, centros, activos,
                         usuario, conteo, crecimiento_anual, desde)
    await confirmar()
    p.paso("operación contabilizada", conteo["comprobantes"])

    # ── Presupuestos, inductores y extracto ──
    #
    # Van DESPUÉS de la operación y no antes: el presupuesto se arma sobre lo que
    # de verdad se gastó el año anterior más un margen, que es como se hace, y el
    # extracto se genera a partir de los movimientos de banco ya contabilizados,
    # que es de donde saldría en la realidad.
    await _presupuestos(db, empresa_id, az, cuentas, centros, desde, hasta, conteo)
    await _inductores(db, empresa_id, az, cuentas, centros, conteo)
    await _extracto(db, empresa_id, az, cuenta_banco, cuentas, conteo)
    await confirmar()
    p.paso("presupuestos, inductores y extracto",
           conteo["lineas_presupuesto"] + conteo["movimientos_banco"])

    # ── La comprobación que vale ──
    #
    # Sembrar sin comprobar deja una base que se ve llena y puede estar mal.
    cuadre = (await db.execute(text(
        "SELECT coalesce(sum(l.debito),0), coalesce(sum(l.credito),0) "
        "FROM erp_comprobante_lineas l "
        "JOIN erp_comprobantes c ON c.id = l.comprobante_id "
        "WHERE c.empresa_id = :e"), {"e": empresa_id})).first()
    conteo["debitos"] = float(cuadre[0])
    conteo["creditos"] = float(cuadre[1])
    conteo["cuadra"] = abs(float(cuadre[0]) - float(cuadre[1])) < 0.01

    lineas = (await db.execute(text(
        "SELECT count(*) FROM erp_comprobante_lineas l "
        "JOIN erp_comprobantes c ON c.id = l.comprobante_id "
        "WHERE c.empresa_id = :e"), {"e": empresa_id})).scalar()
    conteo["lineas_contables"] = lineas

    # Sin estadísticas frescas el planificador de PostgreSQL sigue creyendo que
    # las tablas están vacías y elige recorrerlas enteras. Medir el desempeño
    # antes de esto mide otra cosa.
    await db.execute(text("ANALYZE"))
    await confirmar()

    return {"empresa_id": empresa_id, "conteo": conteo, "tiempos": p.resumen()}


async def _cierre_de_mes(db, empresa_id, dia, az, centros, activos, usuario,
                         conteo, crecimiento, desde) -> None:
    """Nómina y depreciación del mes, que es lo que da cuerpo a los gastos.

    Sin ellas el estado de resultados solo tiene costo de ventas y la utilidad
    sale irreal, así que ningún reporte de rentabilidad significa nada.
    """
    anios = dia.year - desde.year
    base = Decimal(int(52_000_000 * (crecimiento ** anios) * az.uniform(0.97, 1.03)))
    salud = (base * Decimal("0.085")).quantize(Decimal("0.01"))
    pension = (base * Decimal("0.12")).quantize(Decimal("0.01"))
    retefuente = (base * Decimal("0.02")).quantize(Decimal("0.01"))
    prestaciones = (base * Decimal("0.2183")).quantize(Decimal("0.01"))
    parafiscales = (base * Decimal("0.09")).quantize(Decimal("0.01"))
    neto = base - salud - pension - retefuente

    await erp_motor.asentar(
        db, empresa_id=empresa_id, evento="NOMINA_LIQUIDACION",
        tipo=TipoComprobante.DIARIO, fecha=dia,
        concepto=f"Nómina de {dia.year}-{dia.month:02d}",
        lineas=[
            Linea("gasto_nomina", debito=base + prestaciones + parafiscales),
            Linea("salud", credito=salud),
            Linea("pension", credito=pension),
            Linea("retefuente", credito=retefuente),
            Linea("prestaciones", credito=prestaciones),
            Linea("parafiscales", credito=parafiscales),
            Linea("neto_pagar", credito=neto),
        ],
        usuario=usuario, documento_tipo="nomina", documento_id=0,
        documento_numero=f"NOM-{dia.year}{dia.month:02d}")
    conteo["nomina"] += 1
    conteo["comprobantes"] += 1

    # ── Costo directo de la operación ──
    #
    # Combustible, conductores y peajes del mes, en proporción a lo facturado.
    # Sin esto la empresa sembrada muestra un margen del 89%, que no existe en
    # transporte de carga —lo normal está entre el 8% y el 15%— y haría que todo
    # reporte de rentabilidad se viera bien sin significar nada.
    #
    # Va como acumulación de fin de mes contra proveedores, que es como se lleva
    # cuando la factura del combustible llega después del servicio prestado.
    facturado = (await db.execute(text("""
        SELECT coalesce(sum(l.credito - l.debito), 0)
        FROM erp_comprobante_lineas l
        JOIN erp_comprobantes c ON c.id = l.comprobante_id
        JOIN erp_plan_cuentas pc ON pc.id = l.cuenta_id
        WHERE c.empresa_id = :e AND c.estado = 'CONTABILIZADO'
          AND left(pc.codigo, 1) = '4'
          AND date_trunc('month', c.fecha) = date_trunc('month', CAST(:f AS date))
    """), {"e": empresa_id, "f": dia})).scalar()

    directo = (Decimal(str(facturado or 0)) * Decimal(str(az.uniform(0.58, 0.68)))
               ).quantize(Decimal("0.01"))
    if directo > 0:
        await erp_motor.asentar(
            db, empresa_id=empresa_id, evento="SERVICIO_EJECUTADO",
            tipo=TipoComprobante.DIARIO, fecha=dia,
            concepto=f"Costo de operación de {dia.year}-{dia.month:02d}",
            lineas=[Linea("costo", debito=directo,
                          centro_costo_id=az.choice(centros).id),
                    Linea("costo_por_pagar", credito=directo)],
            usuario=usuario, documento_tipo="costo_operacion", documento_id=0,
            documento_numero=f"COP-{dia.year}{dia.month:02d}")
        conteo["comprobantes"] += 1

    # La depreciación va en UN comprobante mensual con el total, no uno por
    # activo: así es como se lleva de verdad, y ciento veinte comprobantes al mes
    # solo servirían para inflar la base sin parecerse a nada.
    if activos:
        total = Decimal(0)
        for af in activos:
            if af.fecha_adquisicion > dia:
                continue
            mensual = ((Decimal(str(af.valor_adquisicion))
                        - Decimal(str(af.valor_residual)))
                       / Decimal(af.vida_util_meses))
            acumulada = Decimal(str(af.depreciacion_acumulada)) + mensual
            tope = Decimal(str(af.valor_adquisicion)) - Decimal(str(af.valor_residual))
            if acumulada > tope:
                mensual = max(Decimal(0), tope - Decimal(str(af.depreciacion_acumulada)))
                acumulada = tope
            if mensual <= 0:
                continue
            af.depreciacion_acumulada = acumulada
            af.valor_libro = Decimal(str(af.valor_adquisicion)) - acumulada
            total += mensual

        if total > 0:
            await erp_motor.asentar(
                db, empresa_id=empresa_id, evento="ACTIVO_DEPRECIACION",
                tipo=TipoComprobante.DIARIO, fecha=dia,
                concepto=f"Depreciación de {dia.year}-{dia.month:02d}",
                lineas=[Linea("gasto_depreciacion", debito=total),
                        Linea("depreciacion_acumulada", credito=total)],
                usuario=usuario, documento_tipo="depreciacion", documento_id=0,
                documento_numero=f"DEP-{dia.year}{dia.month:02d}")
            conteo["depreciacion"] += 1
            conteo["comprobantes"] += 1


# ─── Presupuesto, costeo y extracto ───────────────────────────────────────────

async def _presupuestos(db, empresa_id, az, cuentas, centros, desde, hasta,
                        conteo) -> None:
    """Un presupuesto por año, armado sobre lo que de verdad se movió.

    Se construye a partir del gasto real del año anterior más un margen, que es
    como se presupuesta. Números redondos inventados darían una ejecución del
    30% o del 400% y la pantalla de variaciones no significaría nada.
    """
    ya = (await db.execute(select(ERPPresupuesto.id).limit(1))).first()
    if ya:
        return

    presupuestables = [c for c in cuentas.values()
                       if c.acepta_movimientos and c.codigo[0] in "56"]
    if not presupuestables:
        return

    for anio in range(desde.year, hasta.year + 1):
        real = {
            (cid, ccid): Decimal(str(monto))
            for cid, ccid, monto in (await db.execute(text("""
                SELECT l.cuenta_id, l.centro_costo_id,
                       coalesce(sum(l.debito - l.credito), 0)
                FROM erp_comprobante_lineas l
                JOIN erp_comprobantes c ON c.id = l.comprobante_id
                JOIN erp_plan_cuentas pc ON pc.id = l.cuenta_id
                WHERE c.empresa_id = :e AND c.estado = 'CONTABILIZADO'
                  AND extract(year from c.fecha) = :a
                  AND left(pc.codigo, 1) IN ('5', '6')
                GROUP BY 1, 2
            """), {"e": empresa_id, "a": anio - 1})).all()
        }

        pres = ERPPresupuesto(
            empresa_id=empresa_id, nombre=f"Presupuesto operativo {anio}",
            tipo="OPERATIVO", anio=anio, moneda="COP",
            estado="APROBADO" if anio < hasta.year else "EN_REVISION",
            responsable=f"{az.choice(_NOMBRES)} {az.choice(_APELLIDOS)}",
            descripcion=f"Construido sobre la ejecución de {anio - 1} más margen.",
            total_presupuestado=0, total_ejecutado=0)
        db.add(pres)
        await db.flush()

        total = Decimal(0)
        # El primer año no tiene historia: se parte de una cifra por centro para
        # que el presupuesto exista, y la descripción dice que es así.
        base = real or {
            (az.choice(presupuestables).id, c.id):
                Decimal(az.randint(20, 180) * 1_000_000)
            for c in centros
        }
        peso_anual = Decimal(str(sum(_ESTACIONALIDAD)))
        for (cuenta_id, centro_id), monto in base.items():
            if monto <= 0 or cuenta_id is None:
                continue
            anual = (monto * Decimal(str(az.uniform(1.05, 1.35)))).quantize(CENTAVO)
            # Repartido por meses: un presupuesto anual sin desglose no permite
            # ver en qué mes se desvió, que es para lo que se mira.
            for mes in range(1, 13):
                cuota = (anual * Decimal(str(_ESTACIONALIDAD[mes - 1]))
                         / peso_anual).quantize(CENTAVO)
                db.add(ERPLineaPresupuesto(
                    presupuesto_id=pres.id, cuenta_id=cuenta_id,
                    centro_costo_id=centro_id, mes=mes,
                    descripcion=f"{anio}-{mes:02d}",
                    monto_presupuestado=cuota, monto_ejecutado=0,
                    monto_comprometido=0))
                total += cuota
                conteo["lineas_presupuesto"] += 1

        pres.total_presupuestado = total
        conteo["presupuestos"] += 1
    await db.flush()


async def _inductores(db, empresa_id, az, cuentas, centros, conteo) -> None:
    """Los criterios de reparto del costeo ABC.

    Las unidades consumidas por centro son las que hacen que el reparto no sea
    uniforme: si todos consumieran lo mismo, repartir por inductor daría igual
    que repartir por partes iguales y el método no probaría nada.
    """
    ya = (await db.execute(select(ERPInductor.id).limit(1))).first()
    if ya:
        return

    definiciones = [
        ("ABC-01", "Almacenamiento", "m² ocupado", "m²", "512010"),
        ("ABC-02", "Transporte", "km recorrido", "km", "617510"),
        ("ABC-03", "Administración", "horas hombre", "h", "511095"),
        ("ABC-04", "Aseguramiento", "valor asegurado", "$", "513025"),
    ]
    for codigo, actividad, inductor, unidad, cuenta in definiciones:
        c = cuentas.get(cuenta)
        db.add(ERPInductor(
            empresa_id=empresa_id, codigo=codigo, actividad=actividad,
            inductor=inductor, unidad=unidad,
            cuenta_origen_id=c.id if c else None,
            consumo_por_centro={str(cc.id): az.randint(80, 2400)
                                for cc in centros},
            activo=True, definido_por="sembrador"))
        conteo["inductores"] += 1
    await db.flush()


async def _extracto(db, empresa_id, az, cuenta_banco, cuentas, conteo) -> None:
    """El extracto bancario, generado desde los asientos de banco.

    Es lo que hace que la conciliación tenga algo que conciliar. Se generan tres
    clases de línea a propósito:

      · las que calcan un asiento —se emparejan solas—;
      · las que llegan con unos días de desfase, que es el caso corriente y el
        que prueba que la tolerancia de fechas sirve;
      · comisiones y rendimientos que NO tienen asiento, porque son justo los
        que obligan a contabilizar desde la pantalla de tesorería.

    Sin las dos últimas, la conciliación se vería perfecta y no probaría nada.
    """
    ya = (await db.execute(select(ERPMovimientoBancario.id).limit(1))).first()
    if ya or cuenta_banco is None or "111005" not in cuentas:
        return

    apuntes = (await db.execute(text("""
        SELECT c.fecha, c.numero, c.concepto, l.debito, l.credito
        FROM erp_comprobante_lineas l
        JOIN erp_comprobantes c ON c.id = l.comprobante_id
        WHERE c.empresa_id = :e AND l.cuenta_id = :cta
          AND c.estado = 'CONTABILIZADO'
        ORDER BY c.fecha DESC
        LIMIT 400
    """), {"e": empresa_id, "cta": cuentas["111005"].id})).all()

    for fecha, numero, concepto, debito, credito in apuntes:
        entra = Decimal(str(debito or 0)) > 0
        monto = Decimal(str(debito if entra else credito))
        if monto <= 0:
            continue
        desfase = az.choices([0, 1, 2, 3], weights=[80, 10, 6, 4])[0]
        db.add(ERPMovimientoBancario(
            cuenta_id=cuenta_banco.id, fecha=fecha + timedelta(days=desfase),
            tipo="CREDITO" if entra else "DEBITO", monto=monto,
            concepto=(concepto or "")[:500], referencia=numero, conciliado=False))
        conteo["movimientos_banco"] += 1

    if apuntes:
        ultima = max(a[0] for a in apuntes)
        for i in range(24):
            cual = az.choice(["Comisión por manejo", "GMF 4x1000",
                              "Rendimientos financieros", "Cuota de manejo"])
            entra = cual.startswith("Rendimientos")
            db.add(ERPMovimientoBancario(
                cuenta_id=cuenta_banco.id, fecha=ultima - timedelta(days=i * 7),
                tipo="CREDITO" if entra else "DEBITO",
                monto=Decimal(az.randint(12, 900) * 1000),
                concepto=cual, referencia=None, conciliado=False))
            conteo["movimientos_banco"] += 1
    await db.flush()
