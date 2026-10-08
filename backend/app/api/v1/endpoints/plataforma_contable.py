"""
Facturación, notas crédito y la contabilidad consolidada de la plataforma.

AVISO: esto es **control contable interno**, no facturación electrónica ante la
DIAN. No genera CUFE, no valida rangos de numeración autorizados y no reemplaza
al proveedor de facturación electrónica. La factura legal se emite allá y su
número se guarda acá en `numero_externo` para poder cruzar las dos cosas.

La cadena es factura → nota crédito → pago, y el saldo de un cliente sale de
las tres: lo facturado, menos lo acreditado, menos lo pagado. Una factura
emitida no se corrige editándola —eso dejaría lo ya reportado sin cuadrar— sino
emitiendo una nota crédito que la disminuye.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_plataforma
from app.infrastructure.models.plataforma import (
    PlataformaCliente, PlataformaContrato, PlataformaFactura,
    PlataformaNotaCredito, PlataformaPago,
)
from app.core.permisos_consola import exigir
from app.api.v1.endpoints.plataforma import _anotar, _empresa

router = APIRouter(prefix="/plataforma", tags=["Consola del operador"])

CERO = Decimal("0.00")


def _pesos(v) -> Decimal:
    """A dos decimales, tratando el vacío como cero."""
    return (Decimal(v) if v is not None else CERO).quantize(Decimal("0.01"))


async def _siguiente_numero(db: AsyncSession, modelo, prefijo: str) -> str:
    """El siguiente consecutivo del año, sin repetir.

    Se toma el mayor sufijo existente y no la cantidad de filas: contando, al
    anular o borrar una, el siguiente número repetiría uno ya usado.
    """
    anio = date.today().year
    marca = f"{prefijo}-{anio}-"
    r = await db.execute(
        select(func.max(modelo.numero)).where(modelo.numero.like(f"{marca}%")))
    ultimo = r.scalar()
    siguiente = 1
    if ultimo:
        try:
            siguiente = int(str(ultimo).rsplit("-", 1)[-1]) + 1
        except ValueError:
            siguiente = 1
    return f"{marca}{siguiente:04d}"


# ─── Facturas ─────────────────────────────────────────────────────────────────

class Factura(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    numero: Optional[str] = None
    numero_externo: Optional[str] = None
    fecha: date
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    subtotal: Decimal = CERO
    iva_pct: Decimal = Decimal(19)
    iva_valor: Decimal = CERO
    total: Decimal = CERO
    moneda: str = "COP"
    anulada: bool = False
    concepto: Optional[str] = None
    notas: Optional[str] = None
    # Calculados: cuánto se le acreditó y cuánto se ha pagado.
    acreditado: Decimal = CERO
    pagado: Decimal = CERO
    saldo: Decimal = CERO


class FacturaNueva(BaseModel):
    fecha: Optional[date] = None
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    # Si no se manda, se toma la tarifa del contrato.
    subtotal: Optional[Decimal] = None
    iva_pct: Optional[Decimal] = None
    concepto: Optional[str] = None
    numero_externo: Optional[str] = None


async def _saldos(db: AsyncSession, facturas: List[PlataformaFactura]) -> Dict[int, Dict[str, Decimal]]:
    """Lo acreditado y lo pagado de cada factura, en dos consultas."""
    ids = [f.id for f in facturas]
    if not ids:
        return {}
    rn = await db.execute(
        select(PlataformaNotaCredito.factura_id, func.sum(PlataformaNotaCredito.valor))
        .where(PlataformaNotaCredito.factura_id.in_(ids))
        .group_by(PlataformaNotaCredito.factura_id))
    notas = {fid: _pesos(v) for fid, v in rn.all()}
    rp = await db.execute(
        select(PlataformaPago.factura_id, func.sum(PlataformaPago.monto))
        .where(PlataformaPago.factura_id.in_(ids))
        .group_by(PlataformaPago.factura_id))
    pagos = {fid: _pesos(v) for fid, v in rp.all()}
    return {
        fid: {"acreditado": notas.get(fid, CERO), "pagado": pagos.get(fid, CERO)}
        for fid in ids
    }


def _con_saldo(f: PlataformaFactura, s: Dict[str, Decimal]) -> Factura:
    ficha = Factura.model_validate(f)
    ficha.acreditado = s.get("acreditado", CERO)
    ficha.pagado = s.get("pagado", CERO)
    # Una factura anulada no debe nada: queda solo como constancia de que el
    # número se usó.
    base = CERO if f.anulada else _pesos(f.total)
    ficha.saldo = max(CERO, base - ficha.acreditado - ficha.pagado)
    return ficha


@router.get("/empresas/{cliente_id}/facturas", response_model=List[Factura])
async def ver_facturas(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.ver")),
):
    r = await db.execute(
        select(PlataformaFactura)
        .where(PlataformaFactura.cliente_id == cliente_id)
        .order_by(PlataformaFactura.fecha.desc(), PlataformaFactura.id.desc()))
    facturas = list(r.scalars().all())
    saldos = await _saldos(db, facturas)
    return [_con_saldo(f, saldos.get(f.id, {})) for f in facturas]


@router.post("/empresas/{cliente_id}/facturas", response_model=Factura, status_code=201)
async def emitir_factura(
    cliente_id: int, data: FacturaNueva, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.editar")),
):
    """Emite la factura de un periodo.

    Los valores se congelan al emitirla en vez de recalcularse desde el
    contrato: si la tarifa sube el mes que viene, lo ya facturado no puede
    cambiar solo.
    """
    empresa = await _empresa(db, cliente_id)
    rc = await db.execute(
        select(PlataformaContrato).where(PlataformaContrato.cliente_id == cliente_id))
    contrato = rc.scalar_one_or_none()

    subtotal = _pesos(data.subtotal if data.subtotal is not None
                      else (contrato.tarifa_mensual if contrato else CERO))
    if subtotal <= CERO:
        raise HTTPException(
            400,
            "La factura quedaría en cero. Defina la tarifa mensual en la pestaña "
            "Comercial, o escriba un valor para esta factura.",
        )
    iva_pct = _pesos(data.iva_pct if data.iva_pct is not None
                     else (contrato.iva_pct if contrato and contrato.iva_pct is not None
                           else Decimal(19)))

    hoy = date.today()
    desde = data.periodo_desde or hoy.replace(day=1)
    hasta = data.periodo_hasta or desde.replace(day=monthrange(desde.year, desde.month)[1])
    if hasta < desde:
        raise HTTPException(400, "El periodo termina antes de empezar: revise las dos fechas.")

    # Dos facturas para el mismo periodo casi siempre es un doble clic, no una
    # intención. Se avisa en vez de duplicar el cobro en silencio.
    ya = await db.execute(
        select(func.count()).select_from(PlataformaFactura).where(
            (PlataformaFactura.cliente_id == cliente_id) &
            (PlataformaFactura.periodo_desde == desde) &
            (PlataformaFactura.periodo_hasta == hasta) &
            (PlataformaFactura.anulada == False)))  # noqa: E712
    if ya.scalar():
        raise HTTPException(
            409,
            f"Ya hay una factura vigente de esta empresa para el periodo "
            f"{desde} – {hasta}. Anule la anterior si va a reemplazarla.",
        )

    iva_valor = (subtotal * iva_pct / Decimal(100)).quantize(Decimal("0.01"))
    factura = PlataformaFactura(
        cliente_id=cliente_id,
        numero=await _siguiente_numero(db, PlataformaFactura, "FA"),
        numero_externo=data.numero_externo,
        fecha=data.fecha or hoy,
        periodo_desde=desde, periodo_hasta=hasta,
        subtotal=subtotal, iva_pct=iva_pct, iva_valor=iva_valor,
        total=subtotal + iva_valor,
        moneda=(contrato.moneda if contrato else "COP") or "COP",
        concepto=data.concepto or f"Servicio de plataforma {desde:%Y-%m}",
    )
    db.add(factura)
    await db.flush()
    await _anotar(db, request, "factura.emision", empresa.codigo,
                  f"{factura.numero} por {factura.total}")
    await db.commit(); await db.refresh(factura)
    return _con_saldo(factura, {})


@router.post("/empresas/{cliente_id}/facturas/{factura_id}/anular", response_model=Factura)
async def anular_factura(
    cliente_id: int, factura_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.editar")),
):
    """Deja la factura sin efecto contable, conservando el número.

    No se borra: una factura emitida que desaparece deja un hueco en el
    consecutivo que después nadie sabe explicar.
    """
    empresa = await _empresa(db, cliente_id)
    r = await db.execute(select(PlataformaFactura).where(
        (PlataformaFactura.id == factura_id) &
        (PlataformaFactura.cliente_id == cliente_id)))
    f = r.scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Esa factura no existe en esta empresa")
    if f.anulada:
        raise HTTPException(409, "Esa factura ya está anulada")

    pagado = (await db.execute(
        select(func.sum(PlataformaPago.monto)).where(PlataformaPago.factura_id == factura_id)
    )).scalar()
    if pagado:
        raise HTTPException(
            409,
            f"Esa factura tiene {_pesos(pagado)} en pagos aplicados. Anular una factura "
            "ya pagada dejaría el dinero sin respaldo: emita una nota crédito, "
            "o desligue primero los pagos.",
        )

    f.anulada = True
    await _anotar(db, request, "factura.anulacion", empresa.codigo, f.numero)
    await db.commit(); await db.refresh(f)
    return _con_saldo(f, {})


# ─── Notas crédito ────────────────────────────────────────────────────────────

class NotaCredito(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    factura_id: int
    numero: Optional[str] = None
    numero_externo: Optional[str] = None
    fecha: Optional[date] = None
    valor: Decimal
    moneda: str = "COP"
    motivo: str
    notas: Optional[str] = None


@router.get("/empresas/{cliente_id}/notas-credito", response_model=List[NotaCredito])
async def ver_notas(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.ver")),
):
    r = await db.execute(
        select(PlataformaNotaCredito)
        .where(PlataformaNotaCredito.cliente_id == cliente_id)
        .order_by(PlataformaNotaCredito.fecha.desc(), PlataformaNotaCredito.id.desc()))
    return [NotaCredito.model_validate(n) for n in r.scalars().all()]


@router.post("/empresas/{cliente_id}/notas-credito", response_model=NotaCredito, status_code=201)
async def emitir_nota(
    cliente_id: int, data: NotaCredito, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.editar")),
):
    """Emite una nota crédito contra una factura.

    El valor no puede pasar de lo que la factura todavía sostiene: acreditar más
    de lo facturado dejaría un saldo a favor que no salió de ninguna parte.
    """
    empresa = await _empresa(db, cliente_id)
    if data.valor is None or data.valor <= 0:
        raise HTTPException(400, "El valor de la nota crédito debe ser mayor que cero")
    if not (data.motivo or "").strip():
        raise HTTPException(
            400, "Escriba el motivo: es lo primero que se pregunta al revisar la cuenta.")

    rf = await db.execute(select(PlataformaFactura).where(
        (PlataformaFactura.id == data.factura_id) &
        (PlataformaFactura.cliente_id == cliente_id)))
    factura = rf.scalar_one_or_none()
    if not factura:
        raise HTTPException(404, "Esa factura no existe en esta empresa")
    if factura.anulada:
        raise HTTPException(
            409, "Esa factura está anulada: no queda nada que acreditar sobre ella.")

    acreditado = _pesos((await db.execute(
        select(func.sum(PlataformaNotaCredito.valor))
        .where(PlataformaNotaCredito.factura_id == factura.id))).scalar())
    disponible = _pesos(factura.total) - acreditado
    valor = _pesos(data.valor)
    if valor > disponible:
        raise HTTPException(
            400,
            f"La factura {factura.numero} es de {_pesos(factura.total)} y ya tiene "
            f"{acreditado} en notas crédito: solo quedan {disponible} por acreditar.",
        )

    nota = PlataformaNotaCredito(
        cliente_id=cliente_id, factura_id=factura.id,
        numero=await _siguiente_numero(db, PlataformaNotaCredito, "NC"),
        numero_externo=data.numero_externo,
        fecha=data.fecha or date.today(),
        valor=valor, moneda=factura.moneda or "COP",
        motivo=data.motivo.strip(), notas=data.notas,
    )
    db.add(nota)
    await db.flush()
    await _anotar(db, request, "nota_credito.emision", empresa.codigo,
                  f"{nota.numero} por {valor} sobre {factura.numero}")
    await db.commit(); await db.refresh(nota)
    return NotaCredito.model_validate(nota)


# ─── Contabilidad consolidada ─────────────────────────────────────────────────

class FilaCliente(BaseModel):
    cliente_id: int
    codigo: str
    nombre: str
    activo: bool
    tarifa_mensual: Decimal = CERO
    facturado: Decimal = CERO
    acreditado: Decimal = CERO
    recaudado: Decimal = CERO
    saldo: Decimal = CERO
    facturas: int = 0
    # Días desde la factura vencida más antigua sin saldar.
    dias_mora: int = 0


class FilaMes(BaseModel):
    mes: str            # AAAA-MM
    facturado: Decimal = CERO
    acreditado: Decimal = CERO
    recaudado: Decimal = CERO


class Contabilidad(BaseModel):
    """Todo junto, para no tener que entrar cliente por cliente."""
    facturado: Decimal = CERO
    acreditado: Decimal = CERO
    recaudado: Decimal = CERO
    por_cobrar: Decimal = CERO
    # Suma de las tarifas de las empresas activas: el ingreso recurrente mensual.
    ingreso_recurrente: Decimal = CERO
    empresas_activas: int = 0
    empresas_en_mora: int = 0
    clientes: List[FilaCliente] = []
    meses: List[FilaMes] = []


@router.get("/contabilidad", response_model=Contabilidad)
async def contabilidad(
    desde: Optional[date] = None, hasta: Optional[date] = None,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.ver")),
):
    """La cuenta de toda la plataforma, por cliente y por mes.

    Se arma con cuatro consultas agregadas y no recorriendo cliente por cliente:
    con veinte empresas la diferencia no se nota, con doscientas sí.
    """
    empresas = list((await db.execute(
        select(PlataformaCliente).order_by(PlataformaCliente.nombre))).scalars().all())
    por_id = {e.id: e for e in empresas}

    contratos = {c.cliente_id: c for c in (await db.execute(
        select(PlataformaContrato))).scalars().all()}

    # Solo las facturas vigentes cuentan: una anulada conserva el número pero
    # no representa un cobro.
    qf = select(PlataformaFactura).where(PlataformaFactura.anulada == False)  # noqa: E712
    if desde:
        qf = qf.where(PlataformaFactura.fecha >= desde)
    if hasta:
        qf = qf.where(PlataformaFactura.fecha <= hasta)
    facturas = list((await db.execute(qf)).scalars().all())

    qn = select(PlataformaNotaCredito)
    if desde:
        qn = qn.where(PlataformaNotaCredito.fecha >= desde)
    if hasta:
        qn = qn.where(PlataformaNotaCredito.fecha <= hasta)
    notas = list((await db.execute(qn)).scalars().all())

    qp = select(PlataformaPago)
    if desde:
        qp = qp.where(PlataformaPago.fecha >= desde)
    if hasta:
        qp = qp.where(PlataformaPago.fecha <= hasta)
    pagos = list((await db.execute(qp)).scalars().all())

    # Por cliente
    filas: Dict[int, FilaCliente] = {}
    for e in empresas:
        c = contratos.get(e.id)
        filas[e.id] = FilaCliente(
            cliente_id=e.id, codigo=e.codigo, nombre=e.nombre, activo=bool(e.activo),
            tarifa_mensual=_pesos(c.tarifa_mensual if c else CERO),
        )
    for f in facturas:
        fila = filas.get(f.cliente_id)
        if fila:
            fila.facturado += _pesos(f.total)
            fila.facturas += 1
    for n in notas:
        fila = filas.get(n.cliente_id)
        if fila:
            fila.acreditado += _pesos(n.valor)
    for p in pagos:
        fila = filas.get(p.cliente_id)
        if fila:
            fila.recaudado += _pesos(p.monto)

    # La mora se mide desde la factura vigente más antigua que aún tiene saldo.
    acreditado_por_factura: Dict[int, Decimal] = {}
    for n in notas:
        acreditado_por_factura[n.factura_id] = \
            acreditado_por_factura.get(n.factura_id, CERO) + _pesos(n.valor)
    pagado_por_factura: Dict[int, Decimal] = {}
    for p in pagos:
        if p.factura_id:
            pagado_por_factura[p.factura_id] = \
                pagado_por_factura.get(p.factura_id, CERO) + _pesos(p.monto)

    hoy = date.today()
    for f in facturas:
        saldo = (_pesos(f.total)
                 - acreditado_por_factura.get(f.id, CERO)
                 - pagado_por_factura.get(f.id, CERO))
        if saldo > CERO and f.fecha and f.fecha < hoy:
            fila = filas.get(f.cliente_id)
            if fila:
                fila.dias_mora = max(fila.dias_mora, (hoy - f.fecha).days)

    for fila in filas.values():
        fila.saldo = max(CERO, fila.facturado - fila.acreditado - fila.recaudado)

    # Por mes
    meses: Dict[str, FilaMes] = {}

    def mes_de(d: Optional[date]) -> Optional[str]:
        return f"{d.year:04d}-{d.month:02d}" if d else None

    for f in facturas:
        k = mes_de(f.fecha)
        if k:
            meses.setdefault(k, FilaMes(mes=k)).facturado += _pesos(f.total)
    for n in notas:
        k = mes_de(n.fecha)
        if k:
            meses.setdefault(k, FilaMes(mes=k)).acreditado += _pesos(n.valor)
    for p in pagos:
        k = mes_de(p.fecha)
        if k:
            meses.setdefault(k, FilaMes(mes=k)).recaudado += _pesos(p.monto)

    lista = sorted(filas.values(), key=lambda x: (-x.saldo, x.nombre))
    total_facturado = sum((x.facturado for x in lista), CERO)
    total_acreditado = sum((x.acreditado for x in lista), CERO)
    total_recaudado = sum((x.recaudado for x in lista), CERO)

    return Contabilidad(
        facturado=total_facturado,
        acreditado=total_acreditado,
        recaudado=total_recaudado,
        por_cobrar=max(CERO, total_facturado - total_acreditado - total_recaudado),
        ingreso_recurrente=sum(
            (x.tarifa_mensual for x in lista if x.activo), CERO),
        empresas_activas=sum(1 for x in lista if x.activo),
        empresas_en_mora=sum(1 for x in lista if x.dias_mora > 0),
        clientes=lista,
        meses=[meses[k] for k in sorted(meses)],
    )
