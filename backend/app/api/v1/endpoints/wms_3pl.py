"""
WMS · Facturación del servicio logístico (3PL): tarifas por depositante,
liquidación de un periodo (almacenamiento día a día del kárdex, movimientos y
maquila) y su factura de venta en el ERP. Prefijo: /wms/3pl
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import erp_motor, facturacion_dian as dian
from app.core import wms_3pl as tpl
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_supervisor
from app.infrastructure.models.erp import (
    ERPEmpresa, ERPFacturaCliente, ERPLineaFacturaCliente, EstadoFactura, TipoComprobante,
)
from app.infrastructure.models.erp_facturacion import ERPResolucionFacturacion
from app.infrastructure.models.erp_nucleo import ERPTercero
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import WMSDepositante, WMSLiquidacion3PL, WMSTarifa3PL

router = APIRouter(prefix="/wms/3pl", tags=["wms-3pl"])
Concepto = Literal["ALM_M3_DIA", "ALM_POSICION_DIA", "ALM_ESTIBA_DIA", "REC_UNIDAD", "REC_DOCUMENTO",
                   "DESP_UNIDAD", "DESP_LINEA", "DESP_ORDEN", "MINIMO_MES"]


@router.get("/conceptos")
async def conceptos(_=Depends(get_current_user)):
    return [{"concepto": k, "nombre": v[0], "unidad": v[1]} for k, v in tpl.CONCEPTOS.items()]


# ── Tarifas ──────────────────────────────────────────────────────────────────

class TarifaIn(BaseModel):
    concepto: Concepto
    valor: Optional[float] = Field(default=None, ge=0)   # vacío = quitar la tarifa
    iva_pct: float = Field(default=19, ge=0, le=100)


@router.get("/tarifas")
async def ver_tarifas(depositante_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Las tarifas del depositante (o las generales) y, por cada concepto, la que se aplica."""
    propias = {t.concepto: t for t in (await db.execute(select(WMSTarifa3PL).where(
        WMSTarifa3PL.depositante_id.is_(None) if depositante_id is None else WMSTarifa3PL.depositante_id == depositante_id
    ))).scalars()}
    efectivas = await tpl.tarifas_efectivas(db, depositante_id) if depositante_id else propias
    return [{"concepto": c, "nombre": n, "unidad": u,
             "valor": propias[c].valor if c in propias else None, "iva_pct": propias[c].iva_pct if c in propias else 19,
             "aplica": efectivas[c].valor if c in efectivas else None,
             "origen": None if c not in efectivas else ("propia" if efectivas[c].depositante_id else "general")}
            for c, (n, u) in tpl.CONCEPTOS.items()]


@router.put("/tarifas")
async def guardar_tarifas(data: List[TarifaIn], depositante_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
                          _: Usuario = Depends(require_supervisor)):
    if depositante_id and await db.get(WMSDepositante, depositante_id) is None:
        raise HTTPException(404, "Depositante no encontrado.")
    actuales = {t.concepto: t for t in (await db.execute(select(WMSTarifa3PL).where(
        WMSTarifa3PL.depositante_id.is_(None) if depositante_id is None else WMSTarifa3PL.depositante_id == depositante_id
    ))).scalars()}
    for d in data:
        t = actuales.get(d.concepto)
        if d.valor is None:
            if t:
                await db.delete(t)
            continue
        if t is None:
            t = WMSTarifa3PL(depositante_id=depositante_id, concepto=d.concepto, valor=d.valor)
            db.add(t)
        t.valor, t.iva_pct, t.activo = d.valor, d.iva_pct, True
    await db.flush()
    return await ver_tarifas(depositante_id, db)


# ── Liquidaciones ────────────────────────────────────────────────────────────

class PeriodoIn(BaseModel):
    depositante_id: int
    desde: date
    hasta: date


def _validar_periodo(p: PeriodoIn):
    if p.desde > p.hasta:
        raise HTTPException(422, "La fecha inicial es posterior a la final.")
    if (p.hasta - p.desde).days > 92:
        raise HTTPException(422, "Liquide como máximo tres meses a la vez.")
    hoy = (datetime.now(timezone.utc) - timedelta(hours=5)).date()
    if p.hasta >= hoy:
        raise HTTPException(422, "Solo se liquidan días cerrados: el periodo tiene que terminar a más tardar ayer.")


@router.post("/liquidaciones/previa")
async def previa(data: PeriodoIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    _validar_periodo(data)
    return await tpl.liquidar(db, data.depositante_id, data.desde, data.hasta)


def _liq_dict(l: WMSLiquidacion3PL, dep: Optional[WMSDepositante] = None, factura: Optional[ERPFacturaCliente] = None) -> dict:
    return {"id": l.id, "numero": l.numero, "depositante_id": l.depositante_id, "depositante": dep.nombre if dep else None,
            "desde": l.desde.isoformat(), "hasta": l.hasta.isoformat(), "estado": l.estado, "lineas": l.lineas,
            "diario": l.diario, "subtotal": l.subtotal, "iva": l.iva, "total": l.total, "factura_id": l.factura_id,
            "factura": factura.numero if factura else None, "cufe": factura.cufe if factura else None,
            "facturada_en": l.facturada_en.isoformat() if l.facturada_en else None,
            "creada": l.created_at.isoformat() if l.created_at else None}


@router.post("/liquidaciones", status_code=201)
async def crear(data: PeriodoIn, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(get_current_user)):
    """Guarda la liquidación en borrador. No se permite liquidar dos veces los
    mismos días del mismo depositante (cobro doble)."""
    _validar_periodo(data)
    dep = await db.get(WMSDepositante, data.depositante_id)
    if dep is None:
        raise HTTPException(404, "Depositante no encontrado.")
    choque = (await db.execute(select(WMSLiquidacion3PL).where(
        WMSLiquidacion3PL.depositante_id == data.depositante_id, WMSLiquidacion3PL.estado != "ANULADA",
        WMSLiquidacion3PL.desde <= data.hasta, WMSLiquidacion3PL.hasta >= data.desde).with_for_update())).scalars().first()
    if choque:
        raise HTTPException(409, f"Esos días ya están en la liquidación {choque.numero} ({choque.desde} a {choque.hasta}).")
    r = await tpl.liquidar(db, data.depositante_id, data.desde, data.hasta)
    if not r["lineas"]:
        raise HTTPException(422, "No hay nada que cobrar en el periodo (sin actividad o sin tarifas).")
    n = (await db.execute(select(func.count()).select_from(WMSLiquidacion3PL))).scalar() + 1
    numero = f"LIQ-{data.hasta.strftime('%Y%m')}-{n:04d}"
    while (await db.execute(select(WMSLiquidacion3PL.id).where(WMSLiquidacion3PL.numero == numero))).first():
        n += 1
        numero = f"LIQ-{data.hasta.strftime('%Y%m')}-{n:04d}"
    l = WMSLiquidacion3PL(numero=numero, depositante_id=data.depositante_id, desde=data.desde, hasta=data.hasta,
                          estado="BORRADOR", lineas=r["lineas"], diario=r["diario"], subtotal=r["subtotal"], iva=r["iva"],
                          total=r["total"], creada_por_id=yo.id)
    db.add(l)
    await db.flush()
    return {**_liq_dict(l, dep), "avisos": r["avisos"]}


@router.get("/liquidaciones")
async def listar(depositante_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(WMSLiquidacion3PL)
    if depositante_id:
        q = q.where(WMSLiquidacion3PL.depositante_id == depositante_id)
    filas = (await db.execute(q.order_by(WMSLiquidacion3PL.id.desc()).limit(300))).scalars().all()
    deps = {d.id: d for d in (await db.execute(select(WMSDepositante))).scalars()}
    facts = {f.id: f for f in (await db.execute(select(ERPFacturaCliente).where(
        ERPFacturaCliente.id.in_([l.factura_id for l in filas if l.factura_id] or [0])))).scalars()}
    return [_liq_dict(l, deps.get(l.depositante_id), facts.get(l.factura_id)) for l in filas]


async def _liq(db, lid) -> WMSLiquidacion3PL:
    l = (await db.execute(select(WMSLiquidacion3PL).where(WMSLiquidacion3PL.id == lid).with_for_update())).scalar_one_or_none()
    if l is None:
        raise HTTPException(404, "Liquidación no encontrada.")
    return l


@router.post("/liquidaciones/{lid}/anular")
async def anular(lid: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(require_supervisor)):
    l = await _liq(db, lid)
    if l.estado != "BORRADOR":
        raise HTTPException(409, "Solo se anula una liquidación en borrador; la facturada se corrige con nota crédito en el ERP.")
    l.estado = "ANULADA"
    return _liq_dict(l)


async def _tercero(db, empresa_id: int, dep: WMSDepositante) -> ERPTercero:
    if dep.tercero_id:
        t = await db.get(ERPTercero, dep.tercero_id)
        if t:
            return t
    if not dep.nit:
        raise HTTPException(422, f"El depositante {dep.nombre} no tiene NIT ni tercero del ERP: no se le puede facturar.")
    t = (await db.execute(select(ERPTercero).where(ERPTercero.empresa_id == empresa_id,
                                                  ERPTercero.numero_identificacion == dep.nit))).scalar_one_or_none()
    if t is None:
        t = ERPTercero(empresa_id=empresa_id, tipo_identificacion="NIT", numero_identificacion=dep.nit, razon_social=dep.nombre,
                       email=dep.email, es_persona_natural=False, es_cliente=True, origen="WMS")
        db.add(t)
        await db.flush()
    elif not t.es_cliente:
        t.es_cliente = True
    dep.tercero_id = t.id
    return t


@router.post("/liquidaciones/{lid}/facturar")
async def facturar(lid: int, db: AsyncSession = Depends(get_db), yo: Usuario = Depends(require_supervisor)):
    """Convierte la liquidación en factura de venta del ERP: número de la
    resolución de factura electrónica vigente, CUFE, cartera por cobrar y su asiento."""
    l = await _liq(db, lid)
    if l.estado != "BORRADOR":
        raise HTTPException(409, f"La liquidación está {l.estado.lower()}.")
    dep = await db.get(WMSDepositante, l.depositante_id)
    empresa = (await db.execute(select(ERPEmpresa).order_by(ERPEmpresa.id).limit(1))).scalar()
    if empresa is None:
        raise HTTPException(422, "Cree primero la empresa en Finanzas: la factura necesita emisor.")
    hoy = (datetime.now(timezone.utc) - timedelta(hours=5)).date()
    res = (await db.execute(select(ERPResolucionFacturacion).where(
        ERPResolucionFacturacion.empresa_id == empresa.id, ERPResolucionFacturacion.tipo_documento == "FACTURA_VENTA",
        ERPResolucionFacturacion.activa.is_(True), ERPResolucionFacturacion.vigencia_desde <= hoy,
        ERPResolucionFacturacion.vigencia_hasta >= hoy).order_by(ERPResolucionFacturacion.id))).scalars().first()
    if res is None:
        raise HTTPException(422, "No hay una resolución de factura electrónica de venta vigente (POS · Configuración → Resoluciones DIAN).")
    tercero = await _tercero(db, empresa.id, dep)
    try:
        numero, res = await dian.tomar_numero(db, res.id)
    except dian.ResolucionInvalida as e:
        raise HTTPException(409, str(e))
    momento = datetime.now(timezone.utc)
    cufe = dian.codigo_unico(numero, hoy, dian.hora_colombia(momento), l.subtotal, l.iva, 0, 0, l.total, empresa.nit,
                             tercero.numero_identificacion, res.clave_tecnica, res.ambiente)
    fac = ERPFacturaCliente(empresa_id=empresa.id, numero=numero, cliente_nombre=tercero.razon_social or dep.nombre,
                            cliente_nit=tercero.numero_identificacion, cliente_email=dep.email, fecha=hoy,
                            fecha_vencimiento=hoy + timedelta(days=30), subtotal=l.subtotal, total_impuestos=l.iva,
                            total=l.total, saldo=l.total, estado=EstadoFactura.EMITIDA, moneda="COP",
                            concepto=f"Servicios logísticos {l.desde} a {l.hasta} ({l.numero})", cufe=cufe,
                            numero_electronico=numero, resolucion_id=res.id, origen="WMS_3PL", estado_dian="POR_TRANSMITIR")
    db.add(fac)
    await db.flush()
    for ln in l.lineas:
        db.add(ERPLineaFacturaCliente(factura_id=fac.id, descripcion=f"{ln['descripcion']} ({ln['cantidad']:g} {ln['unidad']})"[:500],
                                      cantidad=ln["cantidad"], precio_unitario=round(ln["subtotal"] / ln["cantidad"], 2) if ln["cantidad"] else ln["subtotal"],
                                      descuento_pct=0, subtotal=ln["subtotal"], total_impuesto=ln["iva"],
                                      total=round(ln["subtotal"] + ln["iva"], 2)))
    asiento = [erp_motor.Linea("cartera", debito=l.total, tercero_id=tercero.id),
               erp_motor.Linea("ingreso", credito=l.subtotal, tercero_id=tercero.id)]
    if l.iva:
        asiento.append(erp_motor.Linea("iva_generado", credito=l.iva, tercero_id=tercero.id))
    try:
        await erp_motor.asentar(db, empresa_id=empresa.id, evento="VENTA_FACTURA", tipo=TipoComprobante.DIARIO, fecha=hoy,
                                concepto=f"Factura de servicios logísticos {numero} - {dep.nombre}", lineas=asiento,
                                usuario=yo.username, documento_tipo="factura_cliente", documento_id=fac.id,
                                documento_numero=numero)
    except erp_motor.ErrorContable as e:
        raise HTTPException(422, f"No se pudo contabilizar la factura: {e}")
    l.estado, l.factura_id, l.facturada_en = "FACTURADA", fac.id, momento
    return _liq_dict(l, dep, fac)
