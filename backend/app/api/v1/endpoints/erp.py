"""
ERP — Enterprise Resource Planning
Núcleo financiero, administrativo, tributario y contable corporativo.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import logging

from app.core import erp_motor
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.erp import (
    ERPEmpresa, ERPPlanCuenta, ERPCentroCosto, ERPComprobante, ERPComprobanteLinea,
    ERPBanco, ERPCuentaBancaria, ERPMovimientoBancario, ERPTipoImpuesto,
    ERPFacturaCliente, ERPLineaFacturaCliente, ERPFacturaProveedor,
    ERPPago, ERPPresupuesto, ERPLineaPresupuesto, ERPActivoFijo, ERPDepreciacionActivo,
    ERPRequisicion, ERPLineaRequisicion, ERPOrdenCompra, ERPLineaOrdenCompra,
    ERPProyecto, ERPGastoProyecto, ERPTasaCambio, ERPAuditoria, ERPConfigGeneral,
    TipoCuenta, NaturalezaCuenta, EstadoComprobante, TipoComprobante,
    TipoCuentaBancaria, EstadoFactura, TipoImpuestoEnum, TipoPresupuesto,
    EstadoPresupuesto, MetodoDepreciacion, EstadoActivoFijo, EstadoOC,
    EstadoRequisicion, EstadoPago, TipoPago, EstadoProyecto, TipoMovimientoBancario,
    TipoCentroCosto,
)

router = APIRouter(prefix="/erp", tags=["ERP"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class EmpresaCreate(BaseModel):
    nit: str
    razon_social: str
    nombre_comercial: Optional[str] = None
    pais: str = "Colombia"
    ciudad: Optional[str] = None
    moneda_base: str = "COP"
    sector: Optional[str] = None
    regimen_fiscal: Optional[str] = None
    norma_contable: str = "IFRS"
    es_holding: bool = False
    holding_id: Optional[int] = None

class EmpresaResponse(EmpresaCreate):
    id: int
    activo: bool
    model_config = {"from_attributes": True}


class PlanCuentaCreate(BaseModel):
    codigo: str
    nombre: str
    tipo: TipoCuenta
    naturaleza: NaturalezaCuenta
    nivel: int = 1
    cuenta_padre_id: Optional[int] = None
    es_auxiliar: bool = False
    acepta_movimientos: bool = True
    empresa_id: Optional[int] = None

class PlanCuentaResponse(PlanCuentaCreate):
    id: int
    activo: bool
    model_config = {"from_attributes": True}


class CentroCostoCreate(BaseModel):
    codigo: str
    nombre: str
    tipo: TipoCentroCosto = TipoCentroCosto.OPERATIVO
    responsable: Optional[str] = None
    presupuesto_anual: Optional[float] = None
    padre_id: Optional[int] = None
    empresa_id: Optional[int] = None

class CentroCostoResponse(CentroCostoCreate):
    id: int
    activo: bool
    model_config = {"from_attributes": True}


class ComprobanteLineaCreate(BaseModel):
    cuenta_id: int
    centro_costo_id: Optional[int] = None
    debito: float = 0
    credito: float = 0
    concepto: Optional[str] = None
    tercero: Optional[str] = None

class ComprobanteCreate(BaseModel):
    numero: str
    tipo: TipoComprobante
    fecha: date
    concepto: str
    empresa_id: Optional[int] = None
    referencia: Optional[str] = None
    lineas: List[ComprobanteLineaCreate] = []

class ComprobanteResponse(BaseModel):
    id: int
    numero: str
    tipo: TipoComprobante
    fecha: date
    concepto: str
    estado: EstadoComprobante
    total_debito: float
    total_credito: float
    periodo: Optional[str]
    model_config = {"from_attributes": True}


class BancoCreate(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    swift: Optional[str] = None
    pais: str = "Colombia"

class BancoResponse(BancoCreate):
    id: int
    activo: bool
    model_config = {"from_attributes": True}


class CuentaBancariaCreate(BaseModel):
    banco_id: int
    numero: str
    tipo: TipoCuentaBancaria
    moneda: str = "COP"
    descripcion: Optional[str] = None
    empresa_id: Optional[int] = None

class CuentaBancariaResponse(CuentaBancariaCreate):
    id: int
    saldo_contable: float
    saldo_disponible: float
    activo: bool
    model_config = {"from_attributes": True}


class MovimientoBancarioCreate(BaseModel):
    cuenta_id: int
    fecha: date
    tipo: TipoMovimientoBancario
    monto: float
    concepto: str
    referencia: Optional[str] = None

class MovimientoBancarioResponse(MovimientoBancarioCreate):
    id: int
    conciliado: bool
    model_config = {"from_attributes": True}


class TipoImpuestoCreate(BaseModel):
    nombre: str
    codigo: str
    tipo: TipoImpuestoEnum
    porcentaje: float = 0
    pais: str = "Colombia"
    descripcion: Optional[str] = None

class TipoImpuestoResponse(TipoImpuestoCreate):
    id: int
    activo: bool
    model_config = {"from_attributes": True}


class LineaFacturaCreate(BaseModel):
    descripcion: str
    cantidad: float = 1
    precio_unitario: float = 0
    descuento_pct: float = 0
    impuesto_id: Optional[int] = None
    cuenta_id: Optional[int] = None
    centro_costo_id: Optional[int] = None

class FacturaClienteCreate(BaseModel):
    numero: str
    cliente_nombre: str
    cliente_nit: Optional[str] = None
    cliente_email: Optional[str] = None
    fecha: date
    # Vacío: fecha + días de crédito de la configuración (CxC).
    fecha_vencimiento: Optional[date] = None
    moneda: str = "COP"
    centro_costo_id: Optional[int] = None
    proyecto_id: Optional[int] = None
    concepto: Optional[str] = None
    empresa_id: Optional[int] = None
    lineas: List[LineaFacturaCreate] = []

class FacturaClienteResponse(BaseModel):
    id: int
    numero: str
    cliente_nombre: str
    cliente_nit: Optional[str]
    fecha: date
    fecha_vencimiento: date
    subtotal: float
    total_impuestos: float
    total: float
    saldo: float
    estado: EstadoFactura
    moneda: str
    cufe: Optional[str] = None
    numero_electronico: Optional[str] = None
    model_config = {"from_attributes": True}


class FacturaProveedorCreate(BaseModel):
    numero_proveedor: str
    proveedor_nombre: str
    proveedor_nit: Optional[str] = None
    fecha: date
    # Vacío: fecha + días de crédito de la configuración (CxP).
    fecha_vencimiento: Optional[date] = None
    subtotal: float = 0
    total_impuestos: float = 0
    retenciones: float = 0
    total: float = 0
    moneda: str = "COP"
    orden_compra_id: Optional[int] = None
    centro_costo_id: Optional[int] = None
    concepto: Optional[str] = None
    empresa_id: Optional[int] = None
    # La recepción del WMS que esta factura cubre: en vez de cargar a gasto,
    # salda la «mercancía recibida por facturar» que dejó esa recepción.
    recepcion_wms_id: Optional[int] = None

class FacturaProveedorResponse(FacturaProveedorCreate):
    id: int
    neto_pagar: float
    saldo: float
    estado: EstadoFactura
    model_config = {"from_attributes": True}


class PagoCreate(BaseModel):
    tipo: TipoPago
    numero: str
    fecha: date
    factura_cliente_id: Optional[int] = None
    factura_proveedor_id: Optional[int] = None
    cuenta_bancaria_id: Optional[int] = None
    monto: float
    moneda: str = "COP"
    metodo_pago: Optional[str] = None
    referencia: Optional[str] = None
    concepto: Optional[str] = None
    empresa_id: Optional[int] = None

class PagoResponse(PagoCreate):
    id: int
    estado: EstadoPago
    model_config = {"from_attributes": True}


class PresupuestoCreate(BaseModel):
    nombre: str
    tipo: TipoPresupuesto
    anio: int
    moneda: str = "COP"
    responsable: Optional[str] = None
    descripcion: Optional[str] = None
    empresa_id: Optional[int] = None

class PresupuestoResponse(PresupuestoCreate):
    id: int
    estado: EstadoPresupuesto
    total_presupuestado: float
    total_ejecutado: float
    activo: bool
    model_config = {"from_attributes": True}


class ActivoFijoCreate(BaseModel):
    codigo: str
    nombre: str
    categoria: str
    subcategoria: Optional[str] = None
    fecha_adquisicion: date
    valor_adquisicion: float
    valor_residual: float = 0
    vida_util_meses: int = 60
    metodo_depreciacion: MetodoDepreciacion = MetodoDepreciacion.LINEA_RECTA
    ubicacion: Optional[str] = None
    responsable: Optional[str] = None
    centro_costo_id: Optional[int] = None
    empresa_id: Optional[int] = None
    serie: Optional[str] = None
    proveedor: Optional[str] = None

class ActivoFijoResponse(ActivoFijoCreate):
    id: int
    depreciacion_acumulada: float
    valor_libro: float
    estado: EstadoActivoFijo
    activo: bool
    model_config = {"from_attributes": True}


class RequisicionCreate(BaseModel):
    numero: str
    solicitante: str
    fecha: date
    fecha_requerida: date
    urgente: bool = False
    centro_costo_id: Optional[int] = None
    justificacion: Optional[str] = None
    empresa_id: Optional[int] = None

class RequisicionResponse(RequisicionCreate):
    id: int
    estado: EstadoRequisicion
    activo: bool
    model_config = {"from_attributes": True}


class LineaOCCreate(BaseModel):
    descripcion: str
    unidad: Optional[str] = None
    cantidad: float = 1
    precio_unitario: float = 0
    descuento_pct: float = 0
    impuesto_id: Optional[int] = None
    cuenta_id: Optional[int] = None

class OrdenCompraCreate(BaseModel):
    numero: str
    proveedor_nombre: str
    proveedor_nit: Optional[str] = None
    fecha: date
    fecha_entrega: Optional[date] = None
    condiciones_pago: Optional[str] = None
    lugar_entrega: Optional[str] = None
    centro_costo_id: Optional[int] = None
    requisicion_id: Optional[int] = None
    moneda: str = "COP"
    empresa_id: Optional[int] = None
    observaciones: Optional[str] = None
    lineas: List[LineaOCCreate] = []

class OrdenCompraResponse(BaseModel):
    id: int
    numero: str
    proveedor_nombre: str
    proveedor_nit: Optional[str]
    fecha: date
    estado: EstadoOC
    subtotal: float
    total_impuestos: float
    total: float
    moneda: str
    activo: bool
    model_config = {"from_attributes": True}


class ProyectoCreate(BaseModel):
    codigo: str
    nombre: str
    tipo: Optional[str] = None
    cliente: Optional[str] = None
    responsable: Optional[str] = None
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    presupuesto_total: float = 0
    centro_costo_id: Optional[int] = None
    descripcion: Optional[str] = None
    empresa_id: Optional[int] = None

class ProyectoResponse(ProyectoCreate):
    id: int
    ejecutado_total: float
    ingresos_total: float
    estado: EstadoProyecto
    activo: bool
    model_config = {"from_attributes": True}


# ── DASHBOARD KPIs ────────────────────────────────────────────────────────────

# ─── Listas acotadas ──────────────────────────────────────────────────────────

TOPE_LISTA = 200        # por omisión
TOPE_MAXIMO = 2000      # lo más que se puede pedir de una vez


async def _pagina(db, consulta, respuesta: Response,
                  limite: int, desplazamiento: int, columna_id):
    """Devuelve un TROZO de la consulta y dice cuántos hay en total.

    POR QUÉ EXISTE
    Estas listas se devolvían enteras. Con la operación de tres años de una
    empresa mediana, `/contabilidad/comprobantes` respondía 7,5 MB y la pantalla
    intentaba pintar treinta mil filas: la pestaña del navegador se congelaba y
    se cerraba sola. No era un error de programación visible en ninguna parte —
    el endpoint funcionaba— y por eso nadie lo vio hasta que hubo datos.

    El total va en la cabecera `X-Total-Count` y no dentro del cuerpo a
    propósito: así las pantallas que ya consumen estas rutas como un arreglo
    siguen funcionando —y dejan de morirse— sin cambiar nada, y las que quieran
    paginar leen la cabecera.
    """
    total = (await db.execute(
        select(func.count()).select_from(consulta.subquery()))).scalar() or 0
    respuesta.headers["X-Total-Count"] = str(total)
    respuesta.headers["X-Limite"] = str(limite)
    respuesta.headers["X-Desplazamiento"] = str(desplazamiento)
    # Sin esto el navegador no deja leer las cabeceras desde otro origen y la
    # pantalla no puede decir «200 de 31.314».
    respuesta.headers["Access-Control-Expose-Headers"] = (
        "X-Total-Count, X-Limite, X-Desplazamiento")

    r = await db.execute(consulta.offset(desplazamiento).limit(limite))
    return list(r.scalars().all())


@router.get("/dashboard/kpis")
async def get_erp_kpis(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    hoy = date.today()

    # Facturas cliente
    r_fc = await db.execute(
        select(
            func.count(ERPFacturaCliente.id).label("total_facturas"),
            func.coalesce(func.sum(ERPFacturaCliente.total), 0).label("total_facturado"),
            func.coalesce(func.sum(ERPFacturaCliente.saldo), 0).label("cartera_total"),
        ).where(ERPFacturaCliente.activo == True)
    )
    kpi_fc = r_fc.one()

    # Cartera vencida
    r_vencida = await db.execute(
        select(func.coalesce(func.sum(ERPFacturaCliente.saldo), 0)).where(
            and_(ERPFacturaCliente.activo == True, ERPFacturaCliente.fecha_vencimiento < hoy,
                 ERPFacturaCliente.estado == EstadoFactura.VENCIDA)
        )
    )
    cartera_vencida = float(r_vencida.scalar() or 0)

    # Cuentas por pagar
    r_fp = await db.execute(
        select(
            func.count(ERPFacturaProveedor.id).label("total"),
            func.coalesce(func.sum(ERPFacturaProveedor.saldo), 0).label("total_por_pagar"),
        ).where(ERPFacturaProveedor.activo == True)
    )
    kpi_fp = r_fp.one()

    # Activos fijos
    r_af = await db.execute(
        select(
            func.count(ERPActivoFijo.id).label("total"),
            func.coalesce(func.sum(ERPActivoFijo.valor_adquisicion), 0).label("valor_total"),
            func.coalesce(func.sum(ERPActivoFijo.valor_libro), 0).label("valor_libro_total"),
        ).where(ERPActivoFijo.activo == True)
    )
    kpi_af = r_af.one()

    # Presupuesto año actual
    r_pres = await db.execute(
        select(
            func.coalesce(func.sum(ERPPresupuesto.total_presupuestado), 0).label("presupuestado"),
            func.coalesce(func.sum(ERPPresupuesto.total_ejecutado), 0).label("ejecutado"),
        ).where(and_(ERPPresupuesto.activo == True, ERPPresupuesto.anio == hoy.year,
                     ERPPresupuesto.estado == EstadoPresupuesto.APROBADO))
    )
    kpi_pres = r_pres.one()

    # Saldo bancario
    r_banco = await db.execute(
        select(func.coalesce(func.sum(ERPCuentaBancaria.saldo_disponible), 0)).where(
            ERPCuentaBancaria.activo == True
        )
    )
    saldo_bancario = float(r_banco.scalar() or 0)

    # Órdenes de compra pendientes
    r_oc = await db.execute(
        select(
            func.count(ERPOrdenCompra.id),
            func.coalesce(func.sum(ERPOrdenCompra.total), 0),
        ).where(and_(ERPOrdenCompra.activo == True,
                     ERPOrdenCompra.estado.in_([EstadoOC.APROBADA, EstadoOC.BORRADOR])))
    )
    kpi_oc = r_oc.one()

    return {
        "facturacion": {
            "total_facturas": int(kpi_fc.total_facturas),
            "total_facturado": float(kpi_fc.total_facturado),
            "cartera_total": float(kpi_fc.cartera_total),
            "cartera_vencida": cartera_vencida,
        },
        "cuentas_pagar": {
            "total_facturas": int(kpi_fp.total),
            "total_por_pagar": float(kpi_fp.total_por_pagar),
        },
        "activos_fijos": {
            "total_activos": int(kpi_af.total),
            "valor_adquisicion": float(kpi_af.valor_total),
            "valor_libro": float(kpi_af.valor_libro_total),
        },
        "presupuesto": {
            "presupuestado": float(kpi_pres.presupuestado),
            "ejecutado": float(kpi_pres.ejecutado),
            "ejecucion_pct": (float(kpi_pres.ejecutado) / float(kpi_pres.presupuestado) * 100)
                             if float(kpi_pres.presupuestado) > 0 else 0,
        },
        "tesoreria": {
            "saldo_bancario": saldo_bancario,
        },
        "compras": {
            "oc_pendientes": int(kpi_oc[0]),
            "valor_oc_pendiente": float(kpi_oc[1]),
        },
    }


# ── EMPRESAS ──────────────────────────────────────────────────────────────────

@router.get("/empresas", response_model=List[EmpresaResponse])
async def listar_empresas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    r = await db.execute(select(ERPEmpresa).where(ERPEmpresa.activo == True).order_by(ERPEmpresa.razon_social))
    return list(r.scalars().all())

@router.post("/empresas", response_model=EmpresaResponse, status_code=201)
async def crear_empresa(data: EmpresaCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    emp = ERPEmpresa(**data.model_dump())
    db.add(emp)
    await db.flush()

    # El plan de cuentas y las reglas se siembran ACÁ y no solo al arrancar:
    # una empresa recién creada sin cuentas no puede facturar, y su primera
    # factura falla con «no hay regla contable para cartera». Esperar al
    # siguiente reinicio del servidor para que sirva no es una respuesta.
    #
    # Si la siembra falla, la empresa igual se crea: se puede completar después
    # desde Configuración, y no poder crear la empresa sería peor.
    try:
        from app.core import erp_semilla
        await erp_semilla.sembrar_parametros(db)
        await erp_semilla.sembrar_empresa(db, emp.id)
    except Exception as e:   # noqa: BLE001
        logging.getLogger("uvicorn.error").warning(
            "La empresa %s se creó pero no se pudo sembrar su contabilidad: %s",
            emp.id, e)

    await db.commit()
    await db.refresh(emp)
    return emp

@router.put("/empresas/{empresa_id}", response_model=EmpresaResponse)
async def actualizar_empresa(empresa_id: int, data: EmpresaCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    emp = await db.get(ERPEmpresa, empresa_id)
    if not emp:
        raise HTTPException(404, "Empresa no encontrada")
    for k, v in data.model_dump().items():
        setattr(emp, k, v)
    await db.commit()
    await db.refresh(emp)
    return emp


# ── PLAN DE CUENTAS ───────────────────────────────────────────────────────────

@router.get("/contabilidad/cuentas", response_model=List[PlanCuentaResponse])
async def listar_cuentas(
    tipo: Optional[TipoCuenta] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPPlanCuenta).where(ERPPlanCuenta.activo == True)
    if tipo:
        q = q.where(ERPPlanCuenta.tipo == tipo)
    if search:
        q = q.where(ERPPlanCuenta.nombre.ilike(f"%{search}%") | ERPPlanCuenta.codigo.ilike(f"%{search}%"))
    r = await db.execute(q.order_by(ERPPlanCuenta.codigo))
    return list(r.scalars().all())

@router.post("/contabilidad/cuentas", response_model=PlanCuentaResponse, status_code=201)
async def crear_cuenta(data: PlanCuentaCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    existing = await db.execute(select(ERPPlanCuenta).where(ERPPlanCuenta.codigo == data.codigo))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Ya existe la cuenta con código {data.codigo}")
    cuenta = ERPPlanCuenta(**data.model_dump())
    db.add(cuenta)
    await db.commit()
    await db.refresh(cuenta)
    return cuenta

@router.delete("/contabilidad/cuentas/{cuenta_id}", status_code=204)
async def eliminar_cuenta(cuenta_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    c = await db.get(ERPPlanCuenta, cuenta_id)
    if not c:
        raise HTTPException(404, "Cuenta no encontrada")
    c.activo = False
    await db.commit()


# ── CENTROS DE COSTO ──────────────────────────────────────────────────────────

@router.get("/contabilidad/centros-costo", response_model=List[CentroCostoResponse])
async def listar_centros_costo(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    r = await db.execute(select(ERPCentroCosto).where(ERPCentroCosto.activo == True).order_by(ERPCentroCosto.codigo))
    return list(r.scalars().all())

@router.post("/contabilidad/centros-costo", response_model=CentroCostoResponse, status_code=201)
async def crear_centro_costo(data: CentroCostoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    cc = ERPCentroCosto(**data.model_dump())
    db.add(cc)
    await db.commit()
    await db.refresh(cc)
    return cc

@router.delete("/contabilidad/centros-costo/{cc_id}", status_code=204)
async def eliminar_centro_costo(cc_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    cc = await db.get(ERPCentroCosto, cc_id)
    if not cc:
        raise HTTPException(404, "Centro de costo no encontrado")
    cc.activo = False
    await db.commit()


# ── COMPROBANTES ──────────────────────────────────────────────────────────────

@router.get("/contabilidad/comprobantes", response_model=List[ComprobanteResponse])
async def listar_comprobantes(
    respuesta: Response,
    tipo: Optional[TipoComprobante] = Query(None),
    estado: Optional[EstadoComprobante] = Query(None),
    periodo: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    limite: int = Query(TOPE_LISTA, ge=1, le=TOPE_MAXIMO),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPComprobante)
    if tipo:
        q = q.where(ERPComprobante.tipo == tipo)
    if estado:
        q = q.where(ERPComprobante.estado == estado)
    if periodo:
        q = q.where(ERPComprobante.periodo == periodo)
    # Un rango de fechas evita tener que paginar hasta el año pasado para llegar
    # a un comprobante viejo.
    if desde:
        q = q.where(ERPComprobante.fecha >= desde)
    if hasta:
        q = q.where(ERPComprobante.fecha <= hasta)
    # Del más nuevo al más viejo: la primera página es la que se mira.
    q = q.order_by(ERPComprobante.fecha.desc(), ERPComprobante.id.desc())
    return await _pagina(db, q, respuesta, limite, desplazamiento, ERPComprobante.id)

@router.post("/contabilidad/comprobantes", response_model=ComprobanteResponse, status_code=201)
async def crear_comprobante(data: ComprobanteCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    total_d = sum(l.debito for l in data.lineas)
    total_c = sum(l.credito for l in data.lineas)
    if abs(total_d - total_c) > 0.01:
        raise HTTPException(400, "El comprobante no cuadra: débitos ≠ créditos")
    periodo = data.fecha.strftime("%Y-%m")
    comp = ERPComprobante(
        **{k: v for k, v in data.model_dump(exclude={"lineas"}).items()},
        total_debito=total_d, total_credito=total_c, periodo=periodo,
        creado_por=current_user.nombre,
    )
    db.add(comp)
    await db.flush()
    for ldata in data.lineas:
        linea = ERPComprobanteLinea(comprobante_id=comp.id, **ldata.model_dump())
        db.add(linea)
    await db.commit()
    await db.refresh(comp)
    return comp

@router.post("/contabilidad/comprobantes/{comp_id}/contabilizar", response_model=ComprobanteResponse)
async def contabilizar_comprobante(comp_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    comp = await db.get(ERPComprobante, comp_id)
    if not comp:
        raise HTTPException(404, "Comprobante no encontrado")
    if comp.estado != EstadoComprobante.BORRADOR:
        raise HTTPException(400, "Solo se pueden contabilizar comprobantes en estado BORRADOR")
    comp.estado = EstadoComprobante.CONTABILIZADO
    comp.contabilizado_por = current_user.nombre
    comp.contabilizado_en = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(comp)
    return comp


# ── BANCOS ────────────────────────────────────────────────────────────────────

@router.get("/tesoreria/bancos", response_model=List[BancoResponse])
async def listar_bancos(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    r = await db.execute(select(ERPBanco).where(ERPBanco.activo == True).order_by(ERPBanco.nombre))
    return list(r.scalars().all())

@router.post("/tesoreria/bancos", response_model=BancoResponse, status_code=201)
async def crear_banco(data: BancoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    b = ERPBanco(**data.model_dump())
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


# ── CUENTAS BANCARIAS ──────────────────────────────────────────────────────────

@router.get("/tesoreria/cuentas", response_model=List[CuentaBancariaResponse])
async def listar_cuentas_bancarias(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    r = await db.execute(select(ERPCuentaBancaria).where(ERPCuentaBancaria.activo == True).order_by(ERPCuentaBancaria.numero))
    return list(r.scalars().all())

@router.post("/tesoreria/cuentas", response_model=CuentaBancariaResponse, status_code=201)
async def crear_cuenta_bancaria(data: CuentaBancariaCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    cb = ERPCuentaBancaria(**data.model_dump())
    db.add(cb)
    await db.commit()
    await db.refresh(cb)
    return cb


# ── MOVIMIENTOS BANCARIOS ─────────────────────────────────────────────────────

@router.get("/tesoreria/movimientos", response_model=List[MovimientoBancarioResponse])
async def listar_movimientos(
    cuenta_id: Optional[int] = Query(None),
    conciliado: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPMovimientoBancario)
    if cuenta_id:
        q = q.where(ERPMovimientoBancario.cuenta_id == cuenta_id)
    if conciliado is not None:
        q = q.where(ERPMovimientoBancario.conciliado == conciliado)
    r = await db.execute(q.order_by(ERPMovimientoBancario.fecha.desc()))
    return list(r.scalars().all())

@router.post("/tesoreria/movimientos", response_model=MovimientoBancarioResponse, status_code=201)
async def registrar_movimiento(data: MovimientoBancarioCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    mv = ERPMovimientoBancario(**data.model_dump())
    db.add(mv)
    # Actualizar saldo cuenta
    cb = await db.get(ERPCuentaBancaria, data.cuenta_id)
    if cb:
        if data.tipo == TipoMovimientoBancario.CREDITO:
            cb.saldo_contable = float(cb.saldo_contable) + data.monto
            cb.saldo_disponible = float(cb.saldo_disponible) + data.monto
        else:
            cb.saldo_contable = float(cb.saldo_contable) - data.monto
            cb.saldo_disponible = float(cb.saldo_disponible) - data.monto
    await db.commit()
    await db.refresh(mv)
    return mv


# ── IMPUESTOS ─────────────────────────────────────────────────────────────────

@router.get("/tributacion/impuestos", response_model=List[TipoImpuestoResponse])
async def listar_impuestos(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    r = await db.execute(select(ERPTipoImpuesto).where(ERPTipoImpuesto.activo == True).order_by(ERPTipoImpuesto.nombre))
    return list(r.scalars().all())

@router.post("/tributacion/impuestos", response_model=TipoImpuestoResponse, status_code=201)
async def crear_impuesto(data: TipoImpuestoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    existing = await db.execute(select(ERPTipoImpuesto).where(ERPTipoImpuesto.codigo == data.codigo))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Ya existe impuesto con código {data.codigo}")
    imp = ERPTipoImpuesto(**data.model_dump())
    db.add(imp)
    await db.commit()
    await db.refresh(imp)
    return imp

@router.delete("/tributacion/impuestos/{imp_id}", status_code=204)
async def eliminar_impuesto(imp_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    imp = await db.get(ERPTipoImpuesto, imp_id)
    if not imp:
        raise HTTPException(404, "Impuesto no encontrado")
    imp.activo = False
    await db.commit()


# ── CUENTAS POR COBRAR ────────────────────────────────────────────────────────

@router.get("/cxc/facturas", response_model=List[FacturaClienteResponse])
async def listar_facturas_cliente(
    respuesta: Response,
    estado: Optional[EstadoFactura] = Query(None),
    search: Optional[str] = Query(None),
    solo_con_saldo: bool = Query(False),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    limite: int = Query(TOPE_LISTA, ge=1, le=TOPE_MAXIMO),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPFacturaCliente).where(ERPFacturaCliente.activo == True)
    if estado:
        q = q.where(ERPFacturaCliente.estado == estado)
    if solo_con_saldo:
        q = q.where(ERPFacturaCliente.saldo > 0)
    if desde:
        q = q.where(ERPFacturaCliente.fecha >= desde)
    if hasta:
        q = q.where(ERPFacturaCliente.fecha <= hasta)
    if search:
        q = q.where(ERPFacturaCliente.cliente_nombre.ilike(f"%{search}%")
                    | ERPFacturaCliente.numero.ilike(f"%{search}%"))
    q = q.order_by(ERPFacturaCliente.fecha.desc(), ERPFacturaCliente.id.desc())
    return await _pagina(db, q, respuesta, limite, desplazamiento,
                         ERPFacturaCliente.id)


@router.get("/cxc/resumen")
async def resumen_cartera(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Los totales de la cartera, sumados en la BASE.

    La pantalla los calculaba recorriendo la lista completa de facturas, así que
    dependía de traérselas todas —lo que la congelaba— y, en cuanto la lista se
    acotó, los totales habrían quedado mal sin que nada avisara. Sumar en SQL es
    correcto con cualquier volumen y no trae una sola fila de más.
    """
    hoy = date.today()
    fila = (await db.execute(select(
        func.count(),
        func.coalesce(func.sum(ERPFacturaCliente.total), 0),
        func.coalesce(func.sum(ERPFacturaCliente.saldo), 0),
        func.count().filter(ERPFacturaCliente.saldo > 0),
        func.coalesce(func.sum(ERPFacturaCliente.saldo).filter(
            ERPFacturaCliente.saldo > 0,
            ERPFacturaCliente.fecha_vencimiento < hoy), 0),
        func.count().filter(ERPFacturaCliente.saldo > 0,
                            ERPFacturaCliente.fecha_vencimiento < hoy),
    ).where(ERPFacturaCliente.activo == True))).first()

    return {
        "facturas": fila[0], "facturado": float(fila[1]),
        "cartera": float(fila[2]), "con_saldo": fila[3],
        "vencido": float(fila[4]), "facturas_vencidas": fila[5],
    }

# ─── INTEGRACIÓN CONTABLE (subledger -> libro mayor) ──────────────────────────
# Cada operación —factura, pago, depreciación— genera su asiento contabilizado,
# de modo que el mayor y los estados financieros reflejan la operación sin
# captura manual.
#
# El PUC de once cuentas que vivía acá se eliminó: el plan completo lo siembra
# `erp_semilla` por empresa y las cuentas concretas las eligen las reglas
# contables, que se editan desde la pantalla. Tener una lista paralela en el
# código era la razón por la que cambiar una cuenta exigía un despliegue.


# La contabilización de los documentos la hace `erp_motor.asentar`, no este
# módulo. Lo que había acá tenía cuatro problemas que ya costaban plata:
#
#   · `_get_or_create_cuenta` buscaba la cuenta por código SIN filtrar por
#     empresa, así que en multiempresa devolvía la cuenta de otra compañía y el
#     asiento quedaba en los libros del vecino;
#   · si no encontraba el código, lo INVENTABA: un tipeo creaba una cuenta nueva
#     que nadie había definido y que no aparecía en ningún reporte;
#   · toleraba un descuadre de hasta un peso por documento;
#   · cuando algo salía mal devolvía `None` en silencio y el documento quedaba
#     guardado SIN asiento, que no se nota hasta el cierre.
#
# Los códigos de cuenta salen ahora de las reglas contables, que se editan desde
# la pantalla. Acá solo se dice qué PAPEL cumple cada línea.


async def _empresa_de(db, empresa_id: Optional[int]) -> int:
    """La empresa del documento, o la primera si la pantalla no la manda.

    Las pantallas de cartera no tienen selector de empresa, y sin empresa el
    motor contable no puede abrir el período: la factura fallaba con un 500
    cada vez. Con una sola empresa, que es el caso normal, la primera es la
    correcta.
    """
    if empresa_id:
        return empresa_id
    eid = (await db.execute(select(ERPEmpresa.id).order_by(ERPEmpresa.id).limit(1))).scalar()
    if eid is None:
        raise HTTPException(422, "Primero hay que crear la empresa en Finanzas → Empresas.")
    return eid


async def _asiento(db, *, empresa_id, evento, tipo, fecha, concepto, referencia,
                   lineas, usuario, documento_tipo=None, documento_id=None):
    """Puente hacia el motor contable, conservando la firma cómoda de acá.

    `lineas` es una lista de (papel, débito, crédito, tercero). Si algo impide
    contabilizar —período cerrado, regla sin configurar, descuadre— levanta
    `ErrorContable`, que es un 422 y tumba la transacción: el documento tampoco
    se guarda. Es deliberado, y es lo contrario de lo que hacía antes.
    """
    empresa_id = await _empresa_de(db, empresa_id)
    return await erp_motor.asentar(
        db, empresa_id=empresa_id, evento=evento, tipo=tipo, fecha=fecha,
        concepto=concepto,
        lineas=[erp_motor.Linea(papel, debito=deb, credito=cred, concepto=tercero)
                for papel, deb, cred, tercero in lineas if (deb or cred)],
        usuario=usuario, documento_tipo=documento_tipo, documento_id=documento_id,
        documento_numero=referencia)


@router.post("/cxc/facturas", response_model=FacturaClienteResponse, status_code=201)
async def crear_factura_cliente(data: FacturaClienteCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    existing = await db.execute(select(ERPFacturaCliente).where(ERPFacturaCliente.numero == data.numero))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Ya existe factura con número {data.numero}")
    subtotal = 0.0
    total_imp = 0.0
    for l in data.lineas:
        base = l.cantidad * l.precio_unitario * (1 - l.descuento_pct / 100)
        imp = 0.0
        if l.impuesto_id:
            t = await db.get(ERPTipoImpuesto, l.impuesto_id)
            if t:
                imp = base * float(t.porcentaje) / 100
        subtotal += base
        total_imp += imp
    total = subtotal + total_imp
    if data.fecha_vencimiento is None:
        data.fecha_vencimiento = data.fecha + timedelta(days=(await _get_config(db)).dias_vencimiento_cxc)
    fc = ERPFacturaCliente(
        **{k: v for k, v in data.model_dump(exclude={"lineas"}).items()},
        subtotal=subtotal, total_impuestos=total_imp, total=total, saldo=total,
    )
    fc.empresa_id = await _empresa_de(db, fc.empresa_id)
    db.add(fc)
    await db.flush()
    for ldata in data.lineas:
        base = ldata.cantidad * ldata.precio_unitario * (1 - ldata.descuento_pct / 100)
        imp = 0.0
        if ldata.impuesto_id:
            t = await db.get(ERPTipoImpuesto, ldata.impuesto_id)
            if t:
                imp = base * float(t.porcentaje) / 100
        linea = ERPLineaFacturaCliente(
            factura_id=fc.id, **{k: v for k, v in ldata.model_dump().items()},
            subtotal=base, total_impuesto=imp, total=base + imp,
        )
        db.add(linea)
    await _asiento(
        db, empresa_id=fc.empresa_id, evento="VENTA_FACTURA",
        tipo=TipoComprobante.DIARIO, fecha=fc.fecha,
        concepto=f"Factura de venta {fc.numero} - {fc.cliente_nombre}",
        referencia=fc.numero, documento_tipo="factura_cliente", documento_id=fc.id,
        lineas=[("cartera", total, 0, fc.cliente_nombre),
                ("ingreso", 0, subtotal, fc.cliente_nombre),
                ("iva_generado", 0, total_imp, fc.cliente_nombre)],
        usuario=current_user.nombre,
    )
    await db.commit()
    await db.refresh(fc)
    return fc

@router.get("/cxc/aging")
async def aging_cuentas_cobrar(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    hoy = date.today()
    r = await db.execute(
        select(ERPFacturaCliente).where(
            and_(ERPFacturaCliente.activo == True, ERPFacturaCliente.saldo > 0)
        )
    )
    facturas = r.scalars().all()
    buckets = {"corriente": 0, "1_30": 0, "31_60": 0, "61_90": 0, "mas_90": 0}
    for f in facturas:
        dias = (hoy - f.fecha_vencimiento).days
        saldo = float(f.saldo)
        if dias <= 0:
            buckets["corriente"] += saldo
        elif dias <= 30:
            buckets["1_30"] += saldo
        elif dias <= 60:
            buckets["31_60"] += saldo
        elif dias <= 90:
            buckets["61_90"] += saldo
        else:
            buckets["mas_90"] += saldo
    return buckets


# ── CUENTAS POR PAGAR ─────────────────────────────────────────────────────────

@router.get("/cxp/facturas", response_model=List[FacturaProveedorResponse])
async def listar_facturas_proveedor(
    respuesta: Response,
    estado: Optional[EstadoFactura] = Query(None),
    search: Optional[str] = Query(None),
    solo_con_saldo: bool = Query(False),
    limite: int = Query(TOPE_LISTA, ge=1, le=TOPE_MAXIMO),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPFacturaProveedor).where(ERPFacturaProveedor.activo == True)
    if estado:
        q = q.where(ERPFacturaProveedor.estado == estado)
    if solo_con_saldo:
        q = q.where(ERPFacturaProveedor.saldo > 0)
    if search:
        q = q.where(ERPFacturaProveedor.proveedor_nombre.ilike(f"%{search}%"))
    # Por vencimiento: lo primero que hay que pagar va arriba.
    q = q.order_by(ERPFacturaProveedor.fecha_vencimiento.asc(),
                   ERPFacturaProveedor.id.asc())
    return await _pagina(db, q, respuesta, limite, desplazamiento,
                         ERPFacturaProveedor.id)


@router.get("/cxp/resumen")
async def resumen_por_pagar(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Los totales por pagar, sumados en la base. Mismo motivo que en cartera."""
    hoy = date.today()
    en_ocho = hoy + timedelta(days=8)
    fila = (await db.execute(select(
        func.count(),
        func.coalesce(func.sum(ERPFacturaProveedor.saldo), 0),
        func.count().filter(ERPFacturaProveedor.saldo > 0),
        func.coalesce(func.sum(ERPFacturaProveedor.saldo).filter(
            ERPFacturaProveedor.saldo > 0,
            ERPFacturaProveedor.fecha_vencimiento < hoy), 0),
        func.count().filter(ERPFacturaProveedor.saldo > 0,
                            ERPFacturaProveedor.fecha_vencimiento < hoy),
        func.count().filter(ERPFacturaProveedor.saldo > 0,
                            ERPFacturaProveedor.fecha_vencimiento >= hoy,
                            ERPFacturaProveedor.fecha_vencimiento <= en_ocho),
    ).where(ERPFacturaProveedor.activo == True))).first()

    return {
        "facturas": fila[0], "por_pagar": float(fila[1]),
        "con_saldo": fila[2], "vencido": float(fila[3]),
        "facturas_vencidas": fila[4], "vencen_en_ocho_dias": fila[5],
    }

@router.post("/cxp/facturas", response_model=FacturaProveedorResponse, status_code=201)
async def crear_factura_proveedor(data: FacturaProveedorCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    neto = data.total - data.retenciones
    if data.fecha_vencimiento is None:
        data.fecha_vencimiento = data.fecha + timedelta(days=(await _get_config(db)).dias_vencimiento_cxp)
    rec = None
    if data.recepcion_wms_id:
        from app.infrastructure.models.wms import WMSRecepcion
        rec = (await db.execute(select(WMSRecepcion).where(WMSRecepcion.id == data.recepcion_wms_id)
                                .with_for_update())).scalar_one_or_none()
        if rec is None or rec.estado != "COMPLETA":
            raise HTTPException(422, "La recepción no existe o no está completa.")
        if rec.factura_proveedor_id:
            raise HTTPException(409, f"La recepción {rec.numero_recepcion} ya tiene su factura de proveedor.")
    fp = ERPFacturaProveedor(**data.model_dump(exclude={"recepcion_wms_id"}), neto_pagar=neto, saldo=neto)
    fp.empresa_id = await _empresa_de(db, fp.empresa_id)
    db.add(fp)
    await db.flush()
    # Asiento automático: Db Gasto+IVA / Cr Proveedores (neto) + Retenciones
    subt = float(fp.subtotal or (float(fp.total) - float(fp.total_impuestos or 0)))
    iva = float(fp.total_impuestos or 0)
    # Mercancía recibida en la bodega: la factura salda lo que la recepción dejó
    # por facturar, y solo la diferencia de precio (si la hay) va a gasto.
    por_facturar = 0.0
    if rec is not None:
        from app.core import wms_contable
        por_facturar = float(await wms_contable.valor_por_facturar(db, rec))
        rec.factura_proveedor_id = fp.id
    gasto = round(subt - por_facturar, 2)
    await _asiento(
        db, empresa_id=fp.empresa_id, evento="COMPRA_FACTURA",
        tipo=TipoComprobante.DIARIO, fecha=fp.fecha,
        concepto=f"Factura de compra {fp.numero_proveedor} - {fp.proveedor_nombre}",
        referencia=fp.numero_proveedor, documento_tipo="factura_proveedor",
        documento_id=fp.id,
        # El IVA de una compra va al DÉBITO como descontable: es un derecho
        # contra la DIAN, no un ingreso. La cuenta la pone la regla.
        lineas=[("por_facturar", por_facturar, 0, fp.proveedor_nombre),
                ("gasto", max(gasto, 0), max(-gasto, 0), fp.proveedor_nombre),
                ("iva_descontable", iva, 0, fp.proveedor_nombre),
                ("retefuente", 0, float(fp.retenciones or 0), fp.proveedor_nombre),
                ("proveedor", 0, neto, fp.proveedor_nombre)],
        usuario=current_user.nombre,
    )
    await db.commit()
    await db.refresh(fp)
    fp.recepcion_wms_id = rec.id if rec else None
    return fp


@router.get("/cxp/recepciones-por-facturar")
async def recepciones_por_facturar(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Las recepciones del WMS que dejaron mercancía por facturar y todavía no
    tienen la factura del proveedor: lo que el ERP debe al proveedor sin papel."""
    from app.core import wms_contable
    from app.infrastructure.models.wms import WMSOrdenCompra, WMSProveedor, WMSRecepcion, WMSMovimientoInventario as M
    ids = [r for (r,) in (await db.execute(select(M.documento_id).where(
        M.documento_tipo == "RECEPCION", M.comprobante_id.isnot(None)).distinct())).all()]
    if not ids:
        return []
    filas = (await db.execute(select(WMSRecepcion, WMSOrdenCompra, WMSProveedor)
                              .outerjoin(WMSOrdenCompra, WMSOrdenCompra.id == WMSRecepcion.orden_compra_id)
                              .outerjoin(WMSProveedor, WMSProveedor.id == WMSOrdenCompra.proveedor_id)
                              .where(WMSRecepcion.id.in_(ids), WMSRecepcion.factura_proveedor_id.is_(None))
                              .order_by(WMSRecepcion.completada_en.desc()))).all()
    return [{"id": r.id, "numero": r.numero_recepcion, "fecha": r.fecha_recepcion.isoformat(),
             "orden_compra": oc.numero_oc if oc else None, "proveedor": p.nombre if p else None,
             "proveedor_nit": p.nit if p else None,
             "valor": float(await wms_contable.valor_por_facturar(db, r))} for r, oc, p in filas]


# ── PAGOS ─────────────────────────────────────────────────────────────────────

@router.get("/pagos", response_model=List[PagoResponse])
async def listar_pagos(
    respuesta: Response,
    tipo: Optional[TipoPago] = Query(None),
    estado: Optional[EstadoPago] = Query(None),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    limite: int = Query(TOPE_LISTA, ge=1, le=TOPE_MAXIMO),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPPago)
    if tipo:
        q = q.where(ERPPago.tipo == tipo)
    if estado:
        q = q.where(ERPPago.estado == estado)
    if desde:
        q = q.where(ERPPago.fecha >= desde)
    if hasta:
        q = q.where(ERPPago.fecha <= hasta)
    q = q.order_by(ERPPago.fecha.desc(), ERPPago.id.desc())
    return await _pagina(db, q, respuesta, limite, desplazamiento, ERPPago.id)

@router.post("/pagos", response_model=PagoResponse, status_code=201)
async def registrar_pago(data: PagoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    pago = ERPPago(**data.model_dump(), estado=EstadoPago.PROCESADO)
    # La empresa del pago es la de la factura que paga.
    factura = (await db.get(ERPFacturaCliente, data.factura_cliente_id) if data.factura_cliente_id
               else await db.get(ERPFacturaProveedor, data.factura_proveedor_id) if data.factura_proveedor_id
               else None)
    pago.empresa_id = await _empresa_de(db, pago.empresa_id or (factura.empresa_id if factura else None))
    db.add(pago)
    # Se vacía ya: el asiento referencia `pago.id`, y sin esto es None.
    await db.flush()
    # Actualizar saldo factura
    if data.factura_cliente_id:
        fc = await db.get(ERPFacturaCliente, data.factura_cliente_id)
        if fc:
            nuevo_saldo = max(0, float(fc.saldo) - data.monto)
            fc.saldo = nuevo_saldo
            fc.estado = EstadoFactura.PAGADA if nuevo_saldo == 0 else EstadoFactura.PARCIALMENTE_PAGADA
    if data.factura_proveedor_id:
        fp = await db.get(ERPFacturaProveedor, data.factura_proveedor_id)
        if fp:
            nuevo_saldo = max(0, float(fp.saldo) - data.monto)
            fp.saldo = nuevo_saldo
            fp.estado = EstadoFactura.PAGADA if nuevo_saldo == 0 else EstadoFactura.PARCIALMENTE_PAGADA
    # Asiento automático del pago
    if data.factura_cliente_id:
        # Recaudo: Db Bancos / Cr Clientes
        await _asiento(db, empresa_id=pago.empresa_id, evento="RECAUDO_CLIENTE",
            tipo=TipoComprobante.INGRESO, fecha=pago.fecha,
            concepto="Recaudo pago cliente",
            referencia=getattr(pago, "referencia", None) or "",
            documento_tipo="pago", documento_id=pago.id,
            lineas=[("banco", data.monto, 0, None), ("cartera", 0, data.monto, None)],
            usuario=current_user.nombre)
    elif data.factura_proveedor_id:
        # Egreso: Db Proveedores / Cr Bancos
        await _asiento(db, empresa_id=pago.empresa_id, evento="PAGO_PROVEEDOR",
            tipo=TipoComprobante.EGRESO, fecha=pago.fecha,
            concepto="Pago a proveedor",
            referencia=getattr(pago, "referencia", None) or "",
            documento_tipo="pago", documento_id=pago.id,
            lineas=[("proveedor", data.monto, 0, None), ("banco", 0, data.monto, None)],
            usuario=current_user.nombre)
    await db.commit()
    await db.refresh(pago)
    return pago


# ── PRESUPUESTOS ──────────────────────────────────────────────────────────────

@router.get("/presupuestos", response_model=List[PresupuestoResponse])
async def listar_presupuestos(
    anio: Optional[int] = Query(None),
    tipo: Optional[TipoPresupuesto] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPPresupuesto).where(ERPPresupuesto.activo == True)
    if anio:
        q = q.where(ERPPresupuesto.anio == anio)
    if tipo:
        q = q.where(ERPPresupuesto.tipo == tipo)
    r = await db.execute(q.order_by(ERPPresupuesto.anio.desc(), ERPPresupuesto.nombre))
    presupuestos = list(r.scalars().all())

    # `total_ejecutado` es una columna que nadie actualizaba: se quedaba en cero
    # para siempre y la pantalla mostraba 0% de ejecución en todos. Se calcula
    # desde el mayor —gasto y costo del año, clases 5 y 6— en vez de mantener la
    # columna al día, porque un total guardado que no coincide con el movimiento
    # que lo produjo es una discusión sin ganador.
    if presupuestos:
        anios = {p.anio for p in presupuestos}
        empresas = {p.empresa_id for p in presupuestos if p.empresa_id}
        ejecutado = {
            (eid, int(anio)): float(monto)
            for eid, anio, monto in (await db.execute(text("""
                SELECT c.empresa_id, extract(year from c.fecha) AS anio,
                       coalesce(sum(l.debito - l.credito), 0)
                FROM erp_comprobante_lineas l
                JOIN erp_comprobantes c ON c.id = l.comprobante_id
                JOIN erp_plan_cuentas pc ON pc.id = l.cuenta_id
                WHERE c.estado = 'CONTABILIZADO'
                  AND left(pc.codigo, 1) IN ('5', '6')
                  AND extract(year from c.fecha) = ANY(:anios)
                GROUP BY 1, 2
            """), {"anios": list(anios)})).all()
        }
        for pres in presupuestos:
            pres.total_ejecutado = ejecutado.get((pres.empresa_id, pres.anio), 0.0)

    return presupuestos

@router.post("/presupuestos", response_model=PresupuestoResponse, status_code=201)
async def crear_presupuesto(data: PresupuestoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    p = ERPPresupuesto(**data.model_dump())
    if not (await _get_config(db)).aprobacion_presupuesto:
        p.estado = EstadoPresupuesto.APROBADO
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p

@router.post("/presupuestos/{pres_id}/aprobar", response_model=PresupuestoResponse)
async def aprobar_presupuesto(pres_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    p = await db.get(ERPPresupuesto, pres_id)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    p.estado = EstadoPresupuesto.APROBADO
    await db.commit()
    await db.refresh(p)
    return p


# ── ACTIVOS FIJOS ─────────────────────────────────────────────────────────────

@router.get("/activos", response_model=List[ActivoFijoResponse])
async def listar_activos(
    categoria: Optional[str] = Query(None),
    estado: Optional[EstadoActivoFijo] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPActivoFijo).where(ERPActivoFijo.activo == True)
    if categoria:
        q = q.where(ERPActivoFijo.categoria == categoria)
    if estado:
        q = q.where(ERPActivoFijo.estado == estado)
    r = await db.execute(q.order_by(ERPActivoFijo.codigo))
    return list(r.scalars().all())

@router.post("/activos", response_model=ActivoFijoResponse, status_code=201)
async def crear_activo(data: ActivoFijoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    existing = await db.execute(select(ERPActivoFijo).where(ERPActivoFijo.codigo == data.codigo))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Ya existe activo con código {data.codigo}")
    af = ERPActivoFijo(**data.model_dump(), valor_libro=data.valor_adquisicion)
    db.add(af)
    await db.commit()
    await db.refresh(af)
    return af

@router.post("/activos/{activo_id}/depreciar")
async def calcular_depreciacion(activo_id: int, fecha: date = Query(...), db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    af = await db.get(ERPActivoFijo, activo_id)
    if not af:
        raise HTTPException(404, "Activo no encontrado")
    if af.metodo_depreciacion == MetodoDepreciacion.LINEA_RECTA:
        dep_mensual = (float(af.valor_adquisicion) - float(af.valor_residual)) / af.vida_util_meses
    else:
        dep_mensual = (float(af.valor_libro) * 2) / af.vida_util_meses
    nueva_acum = float(af.depreciacion_acumulada) + dep_mensual
    nuevo_libro = max(float(af.valor_residual), float(af.valor_adquisicion) - nueva_acum)
    dep = ERPDepreciacionActivo(
        activo_id=activo_id, periodo=fecha.strftime("%Y-%m"), fecha=fecha,
        valor_depreciacion=dep_mensual, depreciacion_acumulada=nueva_acum, valor_libro=nuevo_libro,
    )
    af.depreciacion_acumulada = nueva_acum
    af.valor_libro = nuevo_libro
    db.add(dep)
    # Asiento automático: Db Gasto depreciación / Cr Depreciación acumulada
    await _asiento(db, empresa_id=af.empresa_id, evento="ACTIVO_DEPRECIACION",
        tipo=TipoComprobante.DIARIO, fecha=fecha,
        concepto=f"Depreciación {af.codigo} - {af.nombre}", referencia=af.codigo,
        documento_tipo="activo_fijo", documento_id=af.id,
        lineas=[("gasto_depreciacion", dep_mensual, 0, None),
                ("depreciacion_acumulada", 0, dep_mensual, None)],
        usuario=current_user.nombre)
    await db.commit()
    return {"depreciacion": dep_mensual, "acumulada": nueva_acum, "valor_libro": nuevo_libro}


# ── COMPRAS ───────────────────────────────────────────────────────────────────

@router.get("/compras/requisiciones", response_model=List[RequisicionResponse])
async def listar_requisiciones(
    estado: Optional[EstadoRequisicion] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPRequisicion).where(ERPRequisicion.activo == True)
    if estado:
        q = q.where(ERPRequisicion.estado == estado)
    r = await db.execute(q.order_by(ERPRequisicion.fecha.desc()))
    return list(r.scalars().all())

@router.post("/compras/requisiciones", response_model=RequisicionResponse, status_code=201)
async def crear_requisicion(data: RequisicionCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    req = ERPRequisicion(**data.model_dump())
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req

@router.post("/compras/requisiciones/{req_id}/aprobar", response_model=RequisicionResponse)
async def aprobar_requisicion(req_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    req = await db.get(ERPRequisicion, req_id)
    if not req:
        raise HTTPException(404, "Requisición no encontrada")
    req.estado = EstadoRequisicion.APROBADA
    req.aprobado_por = current_user.nombre
    req.fecha_aprobacion = date.today()
    await db.commit()
    await db.refresh(req)
    return req

@router.get("/compras/ordenes", response_model=List[OrdenCompraResponse])
async def listar_ordenes_compra(
    estado: Optional[EstadoOC] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPOrdenCompra).where(ERPOrdenCompra.activo == True)
    if estado:
        q = q.where(ERPOrdenCompra.estado == estado)
    r = await db.execute(q.order_by(ERPOrdenCompra.fecha.desc()))
    return list(r.scalars().all())

@router.post("/compras/ordenes", response_model=OrdenCompraResponse, status_code=201)
async def crear_orden_compra(data: OrdenCompraCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if (await db.execute(select(ERPOrdenCompra.id).where(ERPOrdenCompra.numero == data.numero))).first():
        raise HTTPException(409, f"Ya existe una orden de compra con número {data.numero}")
    subtotal = sum(l.cantidad * l.precio_unitario * (1 - l.descuento_pct / 100) for l in data.lineas)
    total_imp = 0.0
    for l in data.lineas:
        if l.impuesto_id:
            t = await db.get(ERPTipoImpuesto, l.impuesto_id)
            if t:
                base = l.cantidad * l.precio_unitario * (1 - l.descuento_pct / 100)
                total_imp += base * float(t.porcentaje) / 100
    total = subtotal + total_imp
    oc = ERPOrdenCompra(
        **{k: v for k, v in data.model_dump(exclude={"lineas"}).items()},
        subtotal=subtotal, total_impuestos=total_imp, total=total,
    )
    if not (await _get_config(db)).aprobacion_compras:
        oc.estado = EstadoOC.APROBADA
        oc.aprobado_por = "Sin aprobación (configuración)"
        oc.fecha_aprobacion = date.today()
    db.add(oc)
    await db.flush()
    for ldata in data.lineas:
        base = ldata.cantidad * ldata.precio_unitario * (1 - ldata.descuento_pct / 100)
        imp = 0.0
        if ldata.impuesto_id:
            t = await db.get(ERPTipoImpuesto, ldata.impuesto_id)
            if t:
                imp = base * float(t.porcentaje) / 100
        linea = ERPLineaOrdenCompra(
            orden_id=oc.id, **{k: v for k, v in ldata.model_dump().items()},
            subtotal=base, total_impuesto=imp, total=base + imp,
        )
        db.add(linea)
    await db.commit()
    await db.refresh(oc)
    return oc

@router.post("/compras/ordenes/{oc_id}/aprobar", response_model=OrdenCompraResponse)
async def aprobar_orden_compra(oc_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    oc = await db.get(ERPOrdenCompra, oc_id)
    if not oc:
        raise HTTPException(404, "Orden de compra no encontrada")
    oc.estado = EstadoOC.APROBADA
    oc.aprobado_por = current_user.nombre
    oc.fecha_aprobacion = date.today()
    await db.commit()
    await db.refresh(oc)
    return oc


# ── PROYECTOS ─────────────────────────────────────────────────────────────────

@router.get("/proyectos", response_model=List[ProyectoResponse])
async def listar_proyectos(
    estado: Optional[EstadoProyecto] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = select(ERPProyecto).where(ERPProyecto.activo == True)
    if estado:
        q = q.where(ERPProyecto.estado == estado)
    r = await db.execute(q.order_by(ERPProyecto.fecha_inicio.desc()))
    return list(r.scalars().all())

@router.post("/proyectos", response_model=ProyectoResponse, status_code=201)
async def crear_proyecto(data: ProyectoCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    existing = await db.execute(select(ERPProyecto).where(ERPProyecto.codigo == data.codigo))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Ya existe proyecto con código {data.codigo}")
    proy = ERPProyecto(**data.model_dump())
    db.add(proy)
    await db.commit()
    await db.refresh(proy)
    return proy

@router.get("/proyectos/rentabilidad")
async def rentabilidad_proyectos(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Rentabilidad de todos los proyectos (ingresos vs costos ejecutados)."""
    r = await db.execute(select(ERPProyecto).where(ERPProyecto.deleted_at.is_(None)))
    out = []
    for p in r.scalars().all():
        ingresos = float(p.ingresos_total or 0)
        costos = float(p.ejecutado_total or 0)
        margen = ingresos - costos
        out.append({
            "proyecto_id": p.id, "nombre": p.nombre,
            "ingresos": ingresos, "costos": costos, "margen_bruto": margen,
            "margen_pct": round(margen / ingresos * 100, 2) if ingresos > 0 else 0.0,
            "roi": round(margen / costos * 100, 2) if costos > 0 else 0.0,
        })
    out.sort(key=lambda x: x["margen_bruto"], reverse=True)
    return out


@router.get("/proyectos/{proy_id}/rentabilidad")
async def rentabilidad_proyecto(proy_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    proy = await db.get(ERPProyecto, proy_id)
    if not proy:
        raise HTTPException(404, "Proyecto no encontrado")
    r_gastos = await db.execute(
        select(func.coalesce(func.sum(ERPGastoProyecto.monto), 0)).where(ERPGastoProyecto.proyecto_id == proy_id)
    )
    total_gastos = float(r_gastos.scalar() or 0)
    utilidad = float(proy.ingresos_total) - total_gastos
    margen = (utilidad / float(proy.ingresos_total) * 100) if float(proy.ingresos_total) > 0 else 0
    return {
        "proyecto": proy.nombre,
        "ingresos": float(proy.ingresos_total),
        "gastos": total_gastos,
        "utilidad": utilidad,
        "margen_pct": round(margen, 2),
        "presupuesto": float(proy.presupuesto_total),
        "ejecucion_pct": (total_gastos / float(proy.presupuesto_total) * 100) if float(proy.presupuesto_total) > 0 else 0,
    }


# ── TASAS DE CAMBIO ───────────────────────────────────────────────────────────

@router.get("/tasas-cambio")
async def listar_tasas(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    r = await db.execute(select(ERPTasaCambio).order_by(ERPTasaCambio.fecha.desc()).limit(50))
    items = r.scalars().all()
    return [{"id": t.id, "moneda_origen": t.moneda_origen, "moneda_destino": t.moneda_destino, "fecha": t.fecha, "tasa": float(t.tasa)} for t in items]

@router.post("/tasas-cambio", status_code=201)
async def crear_tasa(moneda_origen: str, moneda_destino: str, fecha: date, tasa: float, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    t = ERPTasaCambio(moneda_origen=moneda_origen, moneda_destino=moneda_destino, fecha=fecha, tasa=tasa)
    db.add(t)
    await db.commit()
    return {"ok": True}


# ── FACTURACIÓN ELECTRÓNICA (emisión / DIAN) ──────────────────────────────────
class FacturaClientePatch(BaseModel):
    estado: Optional[EstadoFactura] = None


@router.patch("/cxc/facturas/{factura_id}", response_model=FacturaClienteResponse)
async def actualizar_factura_cliente(factura_id: int, data: FacturaClientePatch, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Actualiza el estado de la factura. Al EMITIR genera el CUFE (código único
    de la factura electrónica). Nota: la firma/transmisión real a la DIAN requiere
    certificado digital y el proveedor tecnológico; aquí se genera el CUFE funcional."""
    fc = await db.get(ERPFacturaCliente, factura_id)
    if not fc:
        raise HTTPException(404, "Factura no encontrada")
    if data.estado is not None:
        if data.estado == EstadoFactura.EMITIDA and not fc.cufe:
            base = f"{fc.numero}|{fc.cliente_nit or ''}|{float(fc.total):.2f}|{fc.fecha}|{fc.total_impuestos}"
            fc.cufe = hashlib.sha384(base.encode()).hexdigest()
            fc.numero_electronico = f"FE-{fc.numero}"
        fc.estado = data.estado
    await db.commit()
    await db.refresh(fc)
    return fc


# ── CONFIGURACIÓN GENERAL DEL ERP ─────────────────────────────────────────────
async def _get_config(db) -> ERPConfigGeneral:
    cfg = await db.get(ERPConfigGeneral, 1)
    if not cfg:
        cfg = ERPConfigGeneral(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


class ConfigGeneralUpdate(BaseModel):
    moneda_base: Optional[str] = None
    norma_contable: Optional[str] = None
    metodo_inventario: Optional[str] = None
    periodo_fiscal_inicio: Optional[str] = None
    dias_vencimiento_cxc: Optional[int] = None
    dias_vencimiento_cxp: Optional[int] = None
    aprobacion_compras: Optional[bool] = None
    aprobacion_presupuesto: Optional[bool] = None


@router.get("/config/general")
async def get_config_general(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    cfg = await _get_config(db)
    return {c.name: getattr(cfg, c.name) for c in ERPConfigGeneral.__table__.columns if c.name not in ("created_at", "updated_at")}


@router.put("/config/general")
async def put_config_general(data: ConfigGeneralUpdate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    cfg = await _get_config(db)
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(cfg, k, v)
    await db.commit()
    await db.refresh(cfg)
    return {"ok": True}


@router.get("/config/tasas-cambio")
async def config_tasas_cambio(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    r = await db.execute(select(ERPTasaCambio).order_by(ERPTasaCambio.fecha.desc()).limit(50))
    return [{"id": t.id, "moneda_origen": t.moneda_origen, "moneda_destino": t.moneda_destino,
             "tasa": float(t.tasa), "fecha_vigencia": t.fecha.isoformat() if t.fecha else None, "activo": True}
            for t in r.scalars().all()]


class TasaCambioBody(BaseModel):
    moneda_origen: str = "USD"
    moneda_destino: str = "COP"
    tasa: float
    fecha_vigencia: date


@router.post("/config/tasas-cambio", status_code=201)
async def config_crear_tasa(data: TasaCambioBody, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    t = ERPTasaCambio(moneda_origen=data.moneda_origen, moneda_destino=data.moneda_destino,
                      fecha=data.fecha_vigencia, tasa=data.tasa)
    db.add(t)
    await db.commit()
    return {"ok": True}


@router.get("/config/integraciones")
async def config_integraciones(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Qué módulos le mandan hechos económicos a Contabilidad y cómo le va a cada uno.

    Sale de la cola de eventos contables, no de una lista de interruptores:
    antes había cuatro filas fijas con un interruptor que no guardaba nada y
    que ningún cálculo consultaba. Un módulo aparece cuando ha mandado algo.
    """
    filas = (await db.execute(text("""
        SELECT modulo,
               count(*)                                          AS eventos,
               count(*) FILTER (WHERE estado = 'CONTABILIZADO')  AS contabilizados,
               count(*) FILTER (WHERE estado = 'PENDIENTE')      AS pendientes,
               count(*) FILTER (WHERE estado = 'FALLIDO')        AS fallidos,
               max(creado)                                       AS ultimo
        FROM erp_eventos_contables GROUP BY modulo ORDER BY max(creado) DESC
    """))).mappings().all()
    return [{**dict(f), "ultimo": f["ultimo"].isoformat() if f["ultimo"] else None} for f in filas]


@router.get("/config/numeraciones")
async def config_numeraciones(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Los talonarios de comprobantes con su último número usado (erp_consecutivos)."""
    nombres = {"CD": "Comprobante de diario", "RC": "Recibo de caja", "CE": "Comprobante de egreso"}
    filas = (await db.execute(text("""
        SELECT c.prefijo, c.anio, c.ultimo, e.razon_social AS empresa
        FROM erp_consecutivos c LEFT JOIN erp_empresas e ON e.id = c.empresa_id
        ORDER BY c.anio DESC, e.razon_social, c.prefijo
    """))).mappings().all()
    return [{**dict(f), "tipo_documento": nombres.get(f["prefijo"], f["prefijo"])} for f in filas]


# ── REPORTES ──────────────────────────────────────────────────────────────────

async def _sum_lineas(db, anio, *, tipo=None, cod_like=None, signo=1, acumulado=False):
    """Suma de líneas de comprobantes CONTABILIZADOS (libro mayor).
    signo +1 => débito-crédito (cuentas de naturaleza débito: activo/gasto);
    signo -1 => crédito-débito (pasivo/patrimonio/ingreso)."""
    expr = (func.sum(ERPComprobanteLinea.debito - ERPComprobanteLinea.credito) if signo > 0
            else func.sum(ERPComprobanteLinea.credito - ERPComprobanteLinea.debito))
    q = select(func.coalesce(expr, 0)).join(ERPComprobante).join(ERPPlanCuenta).where(
        ERPComprobante.estado == EstadoComprobante.CONTABILIZADO
    )
    if acumulado:
        q = q.where(func.substr(ERPComprobante.periodo, 1, 4) <= str(anio))
    else:
        q = q.where(func.substr(ERPComprobante.periodo, 1, 4) == str(anio))
    if tipo is not None:
        q = q.where(ERPPlanCuenta.tipo == tipo)
    if cod_like:
        q = q.where(ERPPlanCuenta.codigo.like(cod_like))
    return float((await db.execute(q)).scalar() or 0)


@router.get("/reportes/estado-resultados")
async def estado_resultados(
    anio: Optional[int] = Query(None),
    mes: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    anio = anio or date.today().year
    ingresos_op = await _sum_lineas(db, anio, tipo=TipoCuenta.INGRESO, cod_like="41%", signo=-1)
    ingresos_tot = await _sum_lineas(db, anio, tipo=TipoCuenta.INGRESO, signo=-1)
    if ingresos_op == 0:
        ingresos_op = ingresos_tot
    otros_ingresos = ingresos_tot - ingresos_op

    costo_ventas = await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, cod_like="6%", signo=1)
    gastos_admin = await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, cod_like="51%", signo=1)
    gastos_ventas = await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, cod_like="52%", signo=1)
    gastos_fin = await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, cod_like="53%", signo=1)
    depreciacion = (await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, cod_like="5160%", signo=1)
                    + await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, cod_like="5260%", signo=1))
    egresos_tot = await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, signo=1)
    # Egresos no clasificados por código -> a gastos de administración
    clasificados = costo_ventas + gastos_admin + gastos_ventas + gastos_fin
    if egresos_tot > clasificados:
        gastos_admin += egresos_tot - clasificados

    ingresos_base = ingresos_op + otros_ingresos
    utilidad_bruta = ingresos_base - costo_ventas
    ebit = utilidad_bruta - gastos_admin - gastos_ventas - depreciacion
    ebitda = ebit + depreciacion
    uai = ebit - gastos_fin
    impuestos = round(max(uai, 0) * 0.35)
    utilidad_neta = uai - impuestos

    def m(x):
        return round(x / ingresos_base * 100, 2) if ingresos_base > 0 else 0.0

    return {
        "anio": anio,
        "ingresos_operacionales": ingresos_op, "costo_ventas": costo_ventas,
        "utilidad_bruta": utilidad_bruta, "gastos_admin": gastos_admin,
        "gastos_ventas": gastos_ventas, "ebitda": ebitda, "depreciacion": depreciacion,
        "ebit": ebit, "gastos_financieros": gastos_fin,
        "utilidad_antes_impuestos": uai, "impuestos": impuestos, "utilidad_neta": utilidad_neta,
        "margen_bruto_pct": m(utilidad_bruta), "margen_ebitda_pct": m(ebitda), "margen_neto_pct": m(utilidad_neta),
    }


@router.get("/reportes/balance-general")
async def balance_general(
    anio: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    anio = anio or date.today().year
    total_activos = await _sum_lineas(db, anio, tipo=TipoCuenta.ACTIVO, signo=1, acumulado=True)
    activos_fijos = await _sum_lineas(db, anio, tipo=TipoCuenta.ACTIVO, cod_like="15%", signo=1, acumulado=True)
    activos_corr = sum([await _sum_lineas(db, anio, tipo=TipoCuenta.ACTIVO, cod_like=f"{p}%", signo=1, acumulado=True)
                        for p in ("11", "12", "13", "14")])
    otros_activos = total_activos - activos_fijos - activos_corr

    total_pasivos = await _sum_lineas(db, anio, tipo=TipoCuenta.PASIVO, signo=-1, acumulado=True)
    pasivos_corr = sum([await _sum_lineas(db, anio, tipo=TipoCuenta.PASIVO, cod_like=f"{p}%", signo=-1, acumulado=True)
                        for p in ("21", "22", "23", "24", "25")])
    pasivos_lp = total_pasivos - pasivos_corr

    patrimonio_ctas = await _sum_lineas(db, anio, tipo=TipoCuenta.PATRIMONIO, signo=-1, acumulado=True)
    ingresos_acum = await _sum_lineas(db, anio, tipo=TipoCuenta.INGRESO, signo=-1, acumulado=True)
    egresos_acum = await _sum_lineas(db, anio, tipo=TipoCuenta.EGRESO, signo=1, acumulado=True)
    utilidad_acum = ingresos_acum - egresos_acum
    patrimonio = patrimonio_ctas + utilidad_acum

    return {
        "anio": anio,
        "activos_corrientes": activos_corr, "activos_fijos": activos_fijos,
        "otros_activos": otros_activos, "total_activos": total_activos,
        "pasivos_corrientes": pasivos_corr, "pasivos_largo_plazo": pasivos_lp,
        "total_pasivos": total_pasivos, "patrimonio": patrimonio,
        "total_pasivos_patrimonio": total_pasivos + patrimonio,
    }


@router.get("/reportes/flujo-caja")
async def flujo_caja(
    anio: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    anio = anio or date.today().year
    r = await db.execute(
        select(
            func.extract("month", ERPMovimientoBancario.fecha).label("mes"),
            ERPMovimientoBancario.tipo,
            func.coalesce(func.sum(ERPMovimientoBancario.monto), 0),
        ).where(func.extract("year", ERPMovimientoBancario.fecha) == anio)
        .group_by("mes", ERPMovimientoBancario.tipo)
    )
    ingresos = {i: 0.0 for i in range(1, 13)}
    egresos = {i: 0.0 for i in range(1, 13)}
    for mes, tipo, total in r.all():
        mi = int(mes)
        if tipo == TipoMovimientoBancario.CREDITO:
            ingresos[mi] += float(total)
        else:
            egresos[mi] += float(total)

    nombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    out = []
    saldo = 0.0
    for i in range(1, 13):
        operacional = ingresos[i] - egresos[i]
        saldo_inicial = saldo
        saldo += operacional
        out.append({
            "mes": nombres[i - 1], "operacional": round(operacional), "inversion": 0,
            "financiacion": 0, "flujo_neto": round(operacional),
            "saldo_inicial": round(saldo_inicial), "saldo_final": round(saldo),
        })
    return out


@router.get("/reportes/kpis")
async def reportes_kpis(
    anio: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    anio = anio or date.today().year
    bg = await balance_general(anio, db, current_user)  # type: ignore
    er = await estado_resultados(anio, None, db, current_user)  # type: ignore
    act_c = bg["activos_corrientes"] or 0
    pas_c = bg["pasivos_corrientes"] or 1
    total_act = bg["total_activos"] or 1
    patrim = bg["patrimonio"] or 1
    ingresos = er["ingresos_operacionales"] or 1
    return [
        {"nombre": "Liquidez corriente", "valor": round(act_c / pas_c, 2), "unidad": "veces",
         "variacion": 0, "benchmark": ">1.5"},
        {"nombre": "Endeudamiento", "valor": round(bg["total_pasivos"] / total_act * 100, 1), "unidad": "%",
         "variacion": 0, "benchmark": "<60%"},
        {"nombre": "Margen neto", "valor": er["margen_neto_pct"], "unidad": "%",
         "variacion": 0, "benchmark": ">5%"},
        {"nombre": "Margen EBITDA", "valor": er["margen_ebitda_pct"], "unidad": "%",
         "variacion": 0, "benchmark": ">15%"},
        {"nombre": "ROE", "valor": round(er["utilidad_neta"] / patrim * 100, 1), "unidad": "%",
         "variacion": 0, "benchmark": ">15%"},
        {"nombre": "Utilidad neta", "valor": round(er["utilidad_neta"]), "unidad": "COP",
         "variacion": 0, "benchmark": ""},
    ]
