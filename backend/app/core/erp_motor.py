"""
El motor contable: de un hecho económico a un asiento que cuadra.

Reemplaza a `_generar_asiento`, que tenía tres defectos que hacían la
contabilidad poco confiable:

  1. **Fallaba en silencio.** `if no cuadra: return None`. La factura se
     guardaba, el asiento no se creaba, y nadie se enteraba hasta que el balance
     no cuadraba meses después. Acá un asiento que no cuadra levanta una
     excepción y tumba la transacción entera: mejor que la factura no se guarde
     a que se guarde sin contabilizar.

  2. **Toleraba un descuadre de un peso.** `abs(d - c) > 1.0`. Un peso por
     documento, mil documentos al mes, y el balance se va sin que nadie sepa por
     qué. La tolerancia ahora es de medio centavo, que es solo el error de
     redondeo del `round(x, 2)`.

  3. **Numeraba con `count(*) + 1`.** Dos comprobantes simultáneos reciben el
     mismo número. Ahora sale de un contador con bloqueo de fila, por empresa y
     por tipo.

Y añade lo que faltaba: comprueba que el período esté abierto, resuelve las
cuentas por REGLA en vez de tenerlas escritas en el código, y deja constancia en
la auditoría.
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.erp import (
    EstadoComprobante, TipoComprobante,
    ERPAuditoria, ERPComprobante, ERPComprobanteLinea, ERPPlanCuenta,
)
from app.infrastructure.models.erp_nucleo import (
    ERPEventoContable, ERPPeriodo, ERPReglaContable, ERPTercero,
)

# Medio centavo. Es el error que puede dejar `round(x, 2)` sobre unas pocas
# líneas, y nada más. Cualquier diferencia mayor es un error de cálculo, no de
# redondeo, y tiene que doler.
TOLERANCIA = Decimal("0.005")

CENTAVO = Decimal("0.01")


def _redondear(valor: Any) -> Decimal:
    """A dos decimales, con redondeo bancario al alza en el medio.

    Se hace en Decimal y no en float: `0.1 + 0.2` en float no es `0.3`, y esa
    diferencia acumulada sobre cien líneas es exactamente el descuadre que nadie
    logra explicar.
    """
    if valor is None:
        return Decimal("0")
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class Linea:
    """Una línea del asiento, antes de saber en qué cuenta cae.

    Se nombra por su PAPEL —«cartera», «ingreso», «iva_generado»— y no por un
    número de cuenta. Quien llama al motor no sabe de cuentas; la regla contable
    decide cuál cumple cada papel.
    """

    __slots__ = ("papel", "debito", "credito", "tercero_id", "centro_costo_id",
                 "concepto", "condicion", "base", "cuenta_id")

    def __init__(self, papel: str, debito: Any = 0, credito: Any = 0, *,
                 tercero_id: Optional[int] = None,
                 centro_costo_id: Optional[int] = None,
                 concepto: Optional[str] = None,
                 condicion: str = "",
                 base: Any = None,
                 cuenta_id: Optional[int] = None):
        self.papel = papel
        self.debito = _redondear(debito)
        self.credito = _redondear(credito)
        self.tercero_id = tercero_id
        self.centro_costo_id = centro_costo_id
        self.concepto = concepto
        self.condicion = condicion
        self.base = _redondear(base) if base is not None else None
        # Cuando quien llama ya sabe la cuenta —un pago que sale de una cuenta
        # bancaria concreta— se pasa directa y no se busca regla.
        self.cuenta_id = cuenta_id


class ErrorContable(HTTPException):
    """Un problema que impide contabilizar, con el motivo puesto.

    Es una excepción y no un `return None` a propósito: lo segundo deja el
    documento guardado sin asiento, que es la forma más cara de fallar porque no
    se nota hasta el cierre.
    """

    def __init__(self, mensaje: str, detalle: Optional[dict] = None):
        super().__init__(422, {"contabilidad": mensaje, **(detalle or {})})
        self.mensaje = mensaje


# ─── Períodos ─────────────────────────────────────────────────────────────────

async def periodo_de(db: AsyncSession, empresa_id: int, fecha: date) -> ERPPeriodo:
    """El período de esa fecha, creándolo abierto si es el primero.

    Se crea al vuelo en vez de exigir que alguien abra cada mes a mano: obligar a
    abrir el período antes de poder facturar el día 1 es fricción que no protege
    de nada. Lo que sí protege es que no se pueda contabilizar en uno CERRADO, y
    eso es una decisión explícita de alguien.
    """
    def _buscar():
        return db.execute(select(ERPPeriodo).where(
            ERPPeriodo.empresa_id == empresa_id,
            ERPPeriodo.anio == fecha.year,
            ERPPeriodo.mes == fecha.month))

    periodo = (await _buscar()).scalar_one_or_none()
    if periodo is not None:
        return periodo

    # Leer-y-si-no-crear es una carrera: dos peticiones simultáneas no encuentran
    # el período, las dos lo insertan, y la segunda choca contra `uq_erp_periodo`.
    # Pasa de verdad —el día 1 de cada mes, con cuatro workers— y el usuario ve un
    # 500 al facturar. `ON CONFLICT DO NOTHING` deja que gane cualquiera de las
    # dos sin que la otra falle.
    await db.execute(text(
        "INSERT INTO erp_periodos (empresa_id, anio, mes, estado, created_at, updated_at) "
        "VALUES (:e, :a, :m, 'ABIERTO', now(), now()) "
        "ON CONFLICT (empresa_id, anio, mes) DO NOTHING"),
        {"e": empresa_id, "a": fecha.year, "m": fecha.month})

    # Se relee en vez de confiar en lo insertado: si ganó la otra transacción, el
    # período existente es el que manda —y podría estar CERRADO—.
    periodo = (await _buscar()).scalar_one_or_none()
    if periodo is None:
        raise ErrorContable(
            f"No se pudo abrir el período {fecha.year}-{fecha.month:02d}.")
    return periodo


async def exigir_periodo_abierto(db: AsyncSession, empresa_id: int,
                                 fecha: date) -> ERPPeriodo:
    periodo = await periodo_de(db, empresa_id, fecha)
    if periodo.estado != "ABIERTO":
        raise ErrorContable(
            f"El período {fecha.year}-{fecha.month:02d} está "
            f"{periodo.estado.lower()}. Reábralo si de verdad hay que registrar "
            f"algo ahí; quedará constancia de quién lo hizo y por qué.")
    return periodo


# ─── Consecutivos ─────────────────────────────────────────────────────────────

PREFIJOS = {
    TipoComprobante.INGRESO: "RC",
    TipoComprobante.EGRESO: "CE",
    TipoComprobante.DIARIO: "CD",
}


async def siguiente_numero(db: AsyncSession, empresa_id: int,
                           tipo: TipoComprobante, anio: int) -> str:
    """El consecutivo del comprobante, sin carreras y en tiempo constante.

    El número lleva el año porque los consecutivos contables se reinician cada
    ejercicio.

    POR QUÉ UNA TABLA DE CONSECUTIVOS
    Antes se calculaba con `max(substring(numero from '[0-9]+$')::int)` sobre las
    filas del talonario. Ningún índice sirve para eso, así que cada comprobante
    nuevo releía TODOS los del año: con mil comprobantes se nota, con cien mil el
    sistema se arrastra, y el costo crece con el uso. Es el peor tipo de lentitud
    porque aparece cuando el cliente ya depende del sistema.

    `UPDATE ... RETURNING` sobre una fila resuelve las dos cosas a la vez: es
    O(1) y el propio bloqueo de fila serializa a quienes numeran el mismo
    talonario, sin cerrojo aparte y sin estorbar a los demás.
    """
    prefijo = PREFIJOS.get(tipo, "CD")

    # `ON CONFLICT DO NOTHING` para el primer comprobante del talonario; dos
    # peticiones simultáneas ahí no chocan, y la de después toma el bloqueo.
    await db.execute(text(
        "INSERT INTO erp_consecutivos (empresa_id, prefijo, anio, ultimo) "
        "VALUES (:e, :p, :a, 0) ON CONFLICT (empresa_id, prefijo, anio) DO NOTHING"),
        {"e": empresa_id, "p": prefijo, "a": anio})

    siguiente = (await db.execute(text(
        "UPDATE erp_consecutivos SET ultimo = ultimo + 1 "
        "WHERE empresa_id = :e AND prefijo = :p AND anio = :a "
        "RETURNING ultimo"),
        {"e": empresa_id, "p": prefijo, "a": anio})).scalar()

    return f"{prefijo}-{anio}-{siguiente:06d}"


# ─── Reglas contables ─────────────────────────────────────────────────────────

async def cuenta_para(db: AsyncSession, empresa_id: int, evento: str,
                      papel: str, condicion: str = "") -> ERPReglaContable:
    """Qué cuenta cumple ese papel en ese evento.

    Busca primero la regla específica de la condición y cae a la general. Si no
    hay ninguna, **falla con un mensaje que dice qué configurar**: antes esto
    creaba la cuenta al vuelo con `_get_or_create_cuenta`, y así un error de
    tipeo en un código producía una cuenta nueva que nadie había definido.
    """
    # Una memoria por sesión. Un asiento corriente pide tres o cuatro papeles y
    # un proceso de cierre contabiliza cientos de documentos seguidos: sin esto,
    # cada línea de cada uno vuelve a preguntar por la misma regla. Dentro de una
    # transacción la configuración no cambia, así que releerla no aporta nada.
    memoria = db.info.setdefault("erp_reglas", {})
    clave = (empresa_id, evento, papel, condicion)
    if clave in memoria:
        return memoria[clave]

    reglas = (await db.execute(select(ERPReglaContable).where(
        ERPReglaContable.empresa_id == empresa_id,
        ERPReglaContable.evento == evento,
        ERPReglaContable.papel == papel,
        ERPReglaContable.activa.is_(True),
        or_(ERPReglaContable.condicion == condicion,
            ERPReglaContable.condicion == "")))).scalars().all()

    # La específica manda sobre la general.
    especifica = next((r for r in reglas if r.condicion == condicion and condicion), None)
    regla = especifica or next((r for r in reglas if r.condicion == ""), None)

    if regla is None:
        raise ErrorContable(
            f"No hay regla contable para «{papel}» en el evento «{evento}». "
            f"Defínala en Configuración → Reglas contables, indicando qué cuenta "
            f"del plan cumple ese papel.",
            {"evento": evento, "papel": papel})

    # Solo se memoriza el acierto: si falta la regla y alguien la crea, el
    # siguiente intento debe encontrarla en vez de repetir el error.
    memoria[clave] = regla
    return regla


# ─── El asiento ───────────────────────────────────────────────────────────────

async def asentar(
    db: AsyncSession, *,
    empresa_id: int,
    evento: str,
    tipo: TipoComprobante,
    fecha: date,
    concepto: str,
    lineas: Sequence[Linea],
    usuario: str,
    documento_tipo: Optional[str] = None,
    documento_id: Optional[int] = None,
    documento_numero: Optional[str] = None,
    centro_costo_id: Optional[int] = None,
    moneda: str = "COP",
    tasa_cambio: Any = 1,
    contabilizar: bool = True,
) -> ERPComprobante:
    """Convierte un hecho económico en un comprobante contable.

    Comprueba, en este orden y antes de escribir nada:
      1. que haya líneas con importe;
      2. que el período esté abierto;
      3. que cada papel tenga su cuenta configurada;
      4. que débitos y créditos cuadren.

    Cualquier fallo levanta `ErrorContable` y tumba la transacción de quien
    llama. Eso es lo que impide que quede un documento sin su asiento.
    """
    vivas = [ln for ln in lineas if ln.debito or ln.credito]
    if not vivas:
        raise ErrorContable(
            f"El asiento de «{concepto}» no tiene ninguna línea con importe. "
            f"Un documento en cero no produce contabilidad.")

    await exigir_periodo_abierto(db, empresa_id, fecha)

    # Se resuelven TODAS las cuentas antes de escribir. Si falta una regla, se
    # falla sin haber dejado medio comprobante.
    resueltas: List[tuple] = []
    for ln in vivas:
        if ln.cuenta_id is not None:
            cuenta_id = ln.cuenta_id
        else:
            regla = await cuenta_para(db, empresa_id, evento, ln.papel, ln.condicion)
            cuenta_id = regla.cuenta_id
        resueltas.append((ln, cuenta_id))

    total_debito = sum((ln.debito for ln in vivas), Decimal("0"))
    total_credito = sum((ln.credito for ln in vivas), Decimal("0"))
    diferencia = abs(total_debito - total_credito)

    if diferencia > TOLERANCIA:
        # El detalle va en el error: sin ver las líneas, «no cuadra» obliga a
        # reproducir el cálculo a mano para encontrar cuál sobra.
        raise ErrorContable(
            f"El asiento no cuadra: débitos {total_debito} contra créditos "
            f"{total_credito}, diferencia de {diferencia}.",
            {"lineas": [
                {"papel": ln.papel, "debito": str(ln.debito),
                 "credito": str(ln.credito)} for ln in vivas
            ]})

    numero = await siguiente_numero(db, empresa_id, tipo, fecha.year)
    ahora = datetime.now(timezone.utc)

    comp = ERPComprobante(
        empresa_id=empresa_id,
        numero=numero,
        tipo=tipo,
        fecha=fecha,
        concepto=concepto,
        referencia=documento_numero,
        estado=(EstadoComprobante.CONTABILIZADO if contabilizar
                else EstadoComprobante.BORRADOR),
        total_debito=total_debito,
        total_credito=total_credito,
        periodo=f"{fecha.year}-{fecha.month:02d}",
        creado_por=usuario,
        contabilizado_por=usuario if contabilizar else None,
        contabilizado_en=ahora if contabilizar else None,
    )
    db.add(comp)
    await db.flush()

    for ln, cuenta_id in resueltas:
        db.add(ERPComprobanteLinea(
            comprobante_id=comp.id,
            cuenta_id=cuenta_id,
            debito=ln.debito,
            credito=ln.credito,
            concepto=ln.concepto or concepto,
            tercero=str(ln.tercero_id) if ln.tercero_id else None,
            centro_costo_id=ln.centro_costo_id or centro_costo_id,
        ))

    await auditar(db, empresa_id=empresa_id, entidad="comprobante",
                  entidad_id=comp.id, accion="CONTABILIZAR" if contabilizar else "CREAR",
                  usuario=usuario,
                  documento_origen=f"{documento_tipo}:{documento_numero}"
                  if documento_tipo else None,
                  despues={"numero": numero, "total": str(total_debito),
                           "evento": evento})
    return comp


async def reversar(db: AsyncSession, comprobante_id: int, usuario: str,
                   motivo: str) -> ERPComprobante:
    """Anula un comprobante creando su contrario, no borrándolo.

    Un asiento contabilizado no se modifica ni se borra: se reversa. Borrarlo
    dejaría un hueco en el consecutivo y haría imposible explicar por qué el
    libro de un mes cerrado cambió. El contrario entra en la fecha de HOY y no en
    la del original, porque revertir en un período ya cerrado volvería a
    invalidar una declaración presentada.
    """
    original = await db.get(ERPComprobante, comprobante_id)
    if original is None:
        raise ErrorContable("Ese comprobante no existe.")
    if original.estado == EstadoComprobante.ANULADO:
        raise ErrorContable("Ese comprobante ya está anulado.")
    if not motivo or not motivo.strip():
        raise ErrorContable(
            "Una anulación sin motivo no se puede auditar. Diga por qué se anula.")

    lineas = list((await db.execute(select(ERPComprobanteLinea).where(
        ERPComprobanteLinea.comprobante_id == comprobante_id))).scalars().all())
    if not lineas:
        raise ErrorContable("Ese comprobante no tiene líneas que reversar.")

    hoy = datetime.now(timezone.utc).date()
    await exigir_periodo_abierto(db, original.empresa_id, hoy)

    contrarias = [
        Linea("reversion", debito=ln.credito, credito=ln.debito,
              cuenta_id=ln.cuenta_id, centro_costo_id=ln.centro_costo_id,
              concepto=f"Reversión de {original.numero}")
        for ln in lineas
    ]

    reverso = await asentar(
        db, empresa_id=original.empresa_id, evento="REVERSION",
        tipo=original.tipo, fecha=hoy,
        concepto=f"Reversión de {original.numero}: {motivo.strip()}",
        lineas=contrarias, usuario=usuario,
        documento_tipo="comprobante", documento_id=original.id,
        documento_numero=original.numero)

    original.estado = EstadoComprobante.ANULADO

    await auditar(db, empresa_id=original.empresa_id, entidad="comprobante",
                  entidad_id=original.id, accion="ANULAR", usuario=usuario,
                  motivo=motivo.strip(),
                  antes={"estado": "CONTABILIZADO"},
                  despues={"estado": "ANULADO", "reversado_por": reverso.numero})
    return reverso


# ─── Auditoría ────────────────────────────────────────────────────────────────

async def auditar(db: AsyncSession, *, empresa_id: int, entidad: str,
                  entidad_id: int, accion: str, usuario: str,
                  antes: Optional[dict] = None, despues: Optional[dict] = None,
                  motivo: Optional[str] = None, ip: Optional[str] = None,
                  documento_origen: Optional[str] = None) -> None:
    """Deja constancia. No hace commit: va dentro de la transacción de quien llama.

    Es deliberado: una auditoría que se guarda aunque la operación falle
    registraría cosas que no pasaron, y una que se guarda por su cuenta podría
    perderse si la operación se revierte.
    """
    # Se reutiliza la tabla que ya existía, con sus nombres: `datos_antes` y
    # `datos_despues` son texto, así que el detalle va serializado. Crear una
    # segunda tabla de auditoría para el mismo módulo habría dejado dos versiones
    # de la verdad, y nadie sabría cuál mirar.
    db.add(ERPAuditoria(
        empresa_id=empresa_id, modulo="FINANZAS", entidad=entidad,
        entidad_id=entidad_id, accion=accion, usuario=usuario, ip=ip,
        datos_antes=json.dumps(antes, default=str) if antes else None,
        datos_despues=json.dumps(despues, default=str) if despues else None,
        observaciones=motivo, documento_origen=documento_origen))


# ─── La cola de eventos ───────────────────────────────────────────────────────

async def registrar_evento(
    db: AsyncSession, *, empresa_id: int, modulo: str, evento: str,
    documento_tipo: str, documento_id: int, fecha: date,
    importes: Dict[str, Any],
    documento_numero: Optional[str] = None,
    tercero_id: Optional[int] = None,
    centro_costo_id: Optional[int] = None,
    moneda: str = "COP", tasa_cambio: Any = 1,
) -> ERPEventoContable:
    """Anota un hecho económico venido de otro módulo.

    El módulo de origen no sabe de cuentas: dice cuánto va en cada PAPEL
    —`{"ingreso": 1000000, "iva_generado": 190000}`— y el motor decide en qué
    cuenta cae. Eso es lo que permite cambiar el plan de cuentas sin tocar
    ventas, inventarios ni nómina.

    El evento se guarda aunque su contabilización falle. Perder el hecho porque
    faltaba configurar una regla sería perder información real por un problema de
    parametrización.
    """
    # El mismo documento no se anota dos veces: reintentar una operación no debe
    # duplicar el asiento.
    ya = (await db.execute(select(ERPEventoContable).where(
        ERPEventoContable.modulo == modulo,
        ERPEventoContable.evento == evento,
        ERPEventoContable.documento_tipo == documento_tipo,
        ERPEventoContable.documento_id == documento_id))).scalar_one_or_none()
    if ya is not None:
        return ya

    ev = ERPEventoContable(
        empresa_id=empresa_id, modulo=modulo, evento=evento,
        documento_tipo=documento_tipo, documento_id=documento_id,
        documento_numero=documento_numero, fecha=fecha,
        tercero_id=tercero_id, centro_costo_id=centro_costo_id,
        importes={k: str(_redondear(v)) for k, v in importes.items()},
        moneda=moneda, tasa_cambio=tasa_cambio, estado="PENDIENTE")
    db.add(ev)
    await db.flush()
    return ev


# Qué naturaleza tiene cada papel y con qué tipo de comprobante se contabiliza.
# Vive acá y no en la base porque es la gramática del motor —qué significa cada
# papel—, no configuración del negocio: la CUENTA sí se configura, el hecho de
# que la cartera se debite al facturar, no.
NATURALEZA_POR_EVENTO: Dict[str, tuple] = {
    "VENTA_FACTURA": (TipoComprobante.DIARIO, {
        "cartera": "D", "ingreso": "C", "iva_generado": "C",
        "retefuente": "D", "reteica": "D", "reteiva": "D",
        "descuento": "D", "anticipo_aplicado": "D",
    }),
    "VENTA_NOTA_CREDITO": (TipoComprobante.DIARIO, {
        "cartera": "C", "ingreso": "D", "iva_generado": "D",
    }),
    "COMPRA_FACTURA": (TipoComprobante.DIARIO, {
        "gasto": "D", "inventario": "D", "iva_descontable": "D",
        "proveedor": "C", "retefuente": "C", "reteica": "C", "reteiva": "C",
        "por_facturar": "D",
    }),
    "RECAUDO_CLIENTE": (TipoComprobante.INGRESO, {
        "banco": "D", "caja": "D", "cartera": "C",
        "descuento": "D", "retefuente": "D",
    }),
    "PAGO_PROVEEDOR": (TipoComprobante.EGRESO, {
        "proveedor": "D", "banco": "C", "caja": "C", "descuento": "C",
    }),
    "INVENTARIO_SALIDA": (TipoComprobante.DIARIO, {
        "costo_venta": "D", "inventario": "C",
    }),
    "INVENTARIO_ENTRADA": (TipoComprobante.DIARIO, {
        "inventario": "D", "proveedor": "C", "gasto": "C", "por_facturar": "C",
    }),
    # La mercancía vendida que el cliente devuelve y vuelve a la bodega.
    "INVENTARIO_DEVOLUCION": (TipoComprobante.DIARIO, {
        "inventario": "D", "costo_venta": "C",
    }),
    # Lo que el conteo o un ajuste encuentra de menos (o da de baja) y de más.
    "INVENTARIO_MERMA": (TipoComprobante.DIARIO, {
        "merma": "D", "inventario": "C",
    }),
    "INVENTARIO_SOBRANTE": (TipoComprobante.DIARIO, {
        "inventario": "D", "sobrante": "C",
    }),
    "NOMINA_LIQUIDACION": (TipoComprobante.DIARIO, {
        "gasto_nomina": "D", "salud": "C", "pension": "C", "retefuente": "C",
        "neto_pagar": "C", "prestaciones": "C", "parafiscales": "C",
    }),
    "ACTIVO_DEPRECIACION": (TipoComprobante.DIARIO, {
        "gasto_depreciacion": "D", "depreciacion_acumulada": "C",
    }),
    "SERVICIO_EJECUTADO": (TipoComprobante.DIARIO, {
        "cartera": "D", "ingreso": "C", "iva_generado": "C", "costo": "D",
    }),
    # Venta de contado en mostrador: un solo comprobante con el cobro (caja o
    # banco según el medio), el ingreso, el IVA y el costo de lo que salió.
    "POS_VENTA": (TipoComprobante.INGRESO, {
        "caja": "D", "banco": "D", "ingreso": "C", "iva_generado": "C",
        "costo_venta": "D", "inventario": "C",
    }),
    # Su inverso: se devuelve el dinero y la mercancía vuelve al inventario.
    "POS_DEVOLUCION": (TipoComprobante.EGRESO, {
        "caja": "C", "banco": "C", "devolucion": "D", "iva_generado": "D",
        "costo_venta": "C", "inventario": "D",
    }),
}


async def contabilizar_evento(db: AsyncSession, evento_id: int,
                              usuario: str) -> Optional[ERPComprobante]:
    """Convierte un evento pendiente en su asiento.

    Si falla, el evento queda marcado con el motivo en vez de desaparecer: así se
    puede ver qué falta configurar y volver a intentarlo, en lugar de descubrir
    meses después que un mes entero no se contabilizó.
    """
    ev = await db.get(ERPEventoContable, evento_id)
    if ev is None:
        raise ErrorContable("Ese evento no existe.")
    if ev.estado == "CONTABILIZADO":
        return await db.get(ERPComprobante, ev.comprobante_id) if ev.comprobante_id else None

    gramatica = NATURALEZA_POR_EVENTO.get(ev.evento)
    if gramatica is None:
        ev.estado = "FALLIDO"
        ev.error = (f"El evento «{ev.evento}» no está en la gramática del motor. "
                    f"Hay que declarar qué naturaleza tiene cada papel.")
        ev.intentos = (ev.intentos or 0) + 1
        return None

    tipo, naturalezas = gramatica
    lineas: List[Linea] = []
    for papel, importe in (ev.importes or {}).items():
        valor = _redondear(importe)
        if not valor:
            continue
        naturaleza = naturalezas.get(papel)
        if naturaleza is None:
            ev.estado = "FALLIDO"
            ev.error = (f"El papel «{papel}» no está declarado para el evento "
                        f"«{ev.evento}».")
            ev.intentos = (ev.intentos or 0) + 1
            return None
        lineas.append(Linea(
            papel,
            debito=valor if naturaleza == "D" else 0,
            credito=valor if naturaleza == "C" else 0,
            tercero_id=ev.tercero_id, centro_costo_id=ev.centro_costo_id))

    try:
        comp = await asentar(
            db, empresa_id=ev.empresa_id, evento=ev.evento, tipo=tipo,
            fecha=ev.fecha,
            concepto=f"{ev.documento_tipo} {ev.documento_numero or ev.documento_id}",
            lineas=lineas, usuario=usuario,
            documento_tipo=ev.documento_tipo, documento_id=ev.documento_id,
            documento_numero=ev.documento_numero,
            centro_costo_id=ev.centro_costo_id,
            moneda=ev.moneda, tasa_cambio=ev.tasa_cambio)
    except HTTPException as e:
        ev.estado = "FALLIDO"
        d = e.detail
        ev.error = str(d.get("contabilidad") if isinstance(d, dict) else d)[:2000]
        ev.intentos = (ev.intentos or 0) + 1
        return None

    ev.estado = "CONTABILIZADO"
    ev.comprobante_id = comp.id
    ev.error = None
    ev.procesado = datetime.now(timezone.utc)
    return comp


# ─── Dígito de verificación ───────────────────────────────────────────────────

# Los pesos del algoritmo de la DIAN. Van en orden desde el dígito menos
# significativo hacia el más significativo.
_PESOS_DV = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def digito_verificacion(nit: str) -> Optional[str]:
    """El DV de un NIT, calculado.

    Se calcula y no se pide: pedirlo invita a que alguien lo escriba mal, y un DV
    equivocado hace rechazar la información exógena entera. El algoritmo es el de
    la DIAN —suma ponderada módulo 11— y no cambia.
    """
    limpio = "".join(c for c in str(nit or "") if c.isdigit())
    if not limpio or len(limpio) > len(_PESOS_DV):
        return None
    suma = sum(int(d) * _PESOS_DV[i]
               for i, d in enumerate(reversed(limpio)))
    resto = suma % 11
    return str(resto if resto < 2 else 11 - resto)
