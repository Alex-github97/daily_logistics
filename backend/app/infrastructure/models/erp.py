"""
ERP — Enterprise Resource Planning
Núcleo financiero, administrativo, tributario y contable corporativo.
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Date, DateTime,
    Text, ForeignKey, Enum, Numeric, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


# ── Enums ─────────────────────────────────────────────────────────────────────

class TipoCuenta(str, enum.Enum):
    ACTIVO = "ACTIVO"
    PASIVO = "PASIVO"
    PATRIMONIO = "PATRIMONIO"
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
    ORDEN = "ORDEN"

class NaturalezaCuenta(str, enum.Enum):
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"

class EstadoComprobante(str, enum.Enum):
    BORRADOR = "BORRADOR"
    CONTABILIZADO = "CONTABILIZADO"
    ANULADO = "ANULADO"

class TipoComprobante(str, enum.Enum):
    DIARIO = "DIARIO"
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
    AJUSTE = "AJUSTE"
    APERTURA = "APERTURA"
    CIERRE = "CIERRE"
    TRASLADO = "TRASLADO"

class TipoCuentaBancaria(str, enum.Enum):
    CORRIENTE = "CORRIENTE"
    AHORROS = "AHORROS"
    FIDUCIA = "FIDUCIA"
    CDT = "CDT"

class EstadoFactura(str, enum.Enum):
    BORRADOR = "BORRADOR"
    EMITIDA = "EMITIDA"
    PARCIALMENTE_PAGADA = "PARCIALMENTE_PAGADA"
    PAGADA = "PAGADA"
    VENCIDA = "VENCIDA"
    ANULADA = "ANULADA"

class TipoImpuestoEnum(str, enum.Enum):
    IVA = "IVA"
    RETENCION_FUENTE = "RETENCION_FUENTE"
    RETENCION_IVA = "RETENCION_IVA"
    RETENCION_ICA = "RETENCION_ICA"
    INDUSTRIA_COMERCIO = "INDUSTRIA_COMERCIO"
    TIMBRE = "TIMBRE"
    OTRO = "OTRO"

class TipoPresupuesto(str, enum.Enum):
    OPERATIVO = "OPERATIVO"
    FINANCIERO = "FINANCIERO"
    COMERCIAL = "COMERCIAL"
    INVERSION = "INVERSION"
    CAPITAL = "CAPITAL"

class EstadoPresupuesto(str, enum.Enum):
    BORRADOR = "BORRADOR"
    EN_REVISION = "EN_REVISION"
    APROBADO = "APROBADO"
    CERRADO = "CERRADO"

class MetodoDepreciacion(str, enum.Enum):
    LINEA_RECTA = "LINEA_RECTA"
    SALDO_DECRECIENTE = "SALDO_DECRECIENTE"
    UNIDADES_PRODUCCION = "UNIDADES_PRODUCCION"
    SUM_DIGITOS = "SUM_DIGITOS"

class EstadoActivoFijo(str, enum.Enum):
    EN_USO = "EN_USO"
    EN_MANTENIMIENTO = "EN_MANTENIMIENTO"
    DADO_BAJA = "DADO_BAJA"
    VENDIDO = "VENDIDO"
    REVALORIZADO = "REVALORIZADO"

class EstadoOC(str, enum.Enum):
    BORRADOR = "BORRADOR"
    APROBADA = "APROBADA"
    PARCIALMENTE_RECIBIDA = "PARCIALMENTE_RECIBIDA"
    RECIBIDA = "RECIBIDA"
    ANULADA = "ANULADA"

class EstadoRequisicion(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    EN_COTIZACION = "EN_COTIZACION"
    CON_OC = "CON_OC"
    RECHAZADA = "RECHAZADA"

class EstadoPago(str, enum.Enum):
    PROGRAMADO = "PROGRAMADO"
    PROCESADO = "PROCESADO"
    FALLIDO = "FALLIDO"
    ANULADO = "ANULADO"

class TipoPago(str, enum.Enum):
    COBRO = "COBRO"
    PAGO = "PAGO"

class EstadoProyecto(str, enum.Enum):
    PLANEACION = "PLANEACION"
    EN_EJECUCION = "EN_EJECUCION"
    PAUSADO = "PAUSADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"

class TipoMovimientoBancario(str, enum.Enum):
    CREDITO = "CREDITO"
    DEBITO = "DEBITO"

class TipoCentroCosto(str, enum.Enum):
    OPERATIVO = "OPERATIVO"
    ADMINISTRATIVO = "ADMINISTRATIVO"
    COMERCIAL = "COMERCIAL"
    FINANCIERO = "FINANCIERO"
    PROYECTO = "PROYECTO"


# ── 1. CONSOLIDACIÓN MULTIEMPRESA ─────────────────────────────────────────────

class ERPEmpresa(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_empresas"

    id              = Column(Integer, primary_key=True, index=True)
    nit             = Column(String(30), unique=True, nullable=False, index=True)
    razon_social    = Column(String(300), nullable=False)
    nombre_comercial= Column(String(300), nullable=True)
    pais            = Column(String(100), nullable=False, default="Colombia")
    ciudad          = Column(String(100), nullable=True)
    direccion       = Column(String(300), nullable=True)
    telefono        = Column(String(50), nullable=True)
    email           = Column(String(200), nullable=True)
    moneda_base     = Column(String(10), nullable=False, default="COP")
    sector          = Column(String(100), nullable=True)
    regimen_fiscal  = Column(String(100), nullable=True)
    es_holding      = Column(Boolean, default=False)
    holding_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    norma_contable  = Column(String(50), default="IFRS")
    logo_url        = Column(String(500), nullable=True)
    observaciones   = Column(Text, nullable=True)

    filiales = relationship("ERPEmpresa", foreign_keys=[holding_id])


# ── 2. PLAN DE CUENTAS ────────────────────────────────────────────────────────

class ERPPlanCuenta(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_plan_cuentas"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    codigo          = Column(String(20), nullable=False, index=True)
    nombre          = Column(String(300), nullable=False)
    tipo            = Column(Enum(TipoCuenta), nullable=False)
    naturaleza      = Column(Enum(NaturalezaCuenta), nullable=False)
    nivel           = Column(Integer, nullable=False, default=1)
    cuenta_padre_id = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    es_auxiliar     = Column(Boolean, default=False)
    acepta_movimientos = Column(Boolean, default=True)
    norma           = Column(String(50), default="IFRS")
    descripcion     = Column(Text, nullable=True)

    cuenta_padre    = relationship("ERPPlanCuenta", remote_side=[id])
    lineas          = relationship("ERPComprobanteLinea", back_populates="cuenta")

    __table_args__ = (UniqueConstraint("codigo", "empresa_id", name="uq_cuenta_empresa"),)


# ── 3. CENTROS DE COSTO / BENEFICIO ───────────────────────────────────────────

class ERPCentroCosto(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_centros_costo"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    codigo          = Column(String(20), nullable=False, unique=True, index=True)
    nombre          = Column(String(200), nullable=False)
    tipo            = Column(Enum(TipoCentroCosto), nullable=False, default=TipoCentroCosto.OPERATIVO)
    responsable     = Column(String(200), nullable=True)
    presupuesto_anual = Column(Numeric(18, 2), nullable=True)
    padre_id        = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    descripcion     = Column(Text, nullable=True)

    padre           = relationship("ERPCentroCosto", remote_side=[id])


# ── 4. COMPROBANTES CONTABLES ─────────────────────────────────────────────────

class ERPComprobante(Base, TimestampMixin):
    __tablename__ = "erp_comprobantes"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    numero          = Column(String(50), nullable=False, index=True)
    tipo            = Column(Enum(TipoComprobante), nullable=False)
    fecha           = Column(Date, nullable=False)
    concepto        = Column(String(500), nullable=False)
    estado          = Column(Enum(EstadoComprobante), nullable=False, default=EstadoComprobante.BORRADOR)
    total_debito    = Column(Numeric(18, 2), nullable=False, default=0)
    total_credito   = Column(Numeric(18, 2), nullable=False, default=0)
    referencia      = Column(String(200), nullable=True)
    periodo         = Column(String(7), nullable=True)  # YYYY-MM
    creado_por      = Column(String(200), nullable=True)
    contabilizado_por = Column(String(200), nullable=True)
    # Con zona, como `created_at` de esta misma tabla. Sin zona convivían dos
    # significados en la misma columna —un sitio escribía hora local y otro
    # UTC— y no había forma de saber cuál era cuál mirando el dato.
    contabilizado_en  = Column(DateTime(timezone=True), nullable=True)
    observaciones   = Column(Text, nullable=True)

    lineas          = relationship("ERPComprobanteLinea", back_populates="comprobante", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("numero", "empresa_id", "tipo", name="uq_comprobante"),)


class ERPComprobanteLinea(Base):
    __tablename__ = "erp_comprobante_lineas"

    id              = Column(Integer, primary_key=True, index=True)
    comprobante_id  = Column(Integer, ForeignKey("erp_comprobantes.id"), nullable=False)
    cuenta_id       = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=False)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    debito          = Column(Numeric(18, 2), nullable=False, default=0)
    credito         = Column(Numeric(18, 2), nullable=False, default=0)
    concepto        = Column(String(300), nullable=True)
    tercero         = Column(String(300), nullable=True)
    referencia      = Column(String(200), nullable=True)

    comprobante     = relationship("ERPComprobante", back_populates="lineas")
    cuenta          = relationship("ERPPlanCuenta", back_populates="lineas")


# ── 5. BANCOS Y TESORERÍA ─────────────────────────────────────────────────────

class ERPBanco(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_bancos"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(200), nullable=False)
    codigo          = Column(String(20), nullable=True)
    swift           = Column(String(20), nullable=True)
    pais            = Column(String(100), default="Colombia")
    activo          = Column(Boolean, default=True)

    cuentas         = relationship("ERPCuentaBancaria", back_populates="banco")


class ERPCuentaBancaria(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_cuentas_bancarias"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    banco_id        = Column(Integer, ForeignKey("erp_bancos.id"), nullable=False)
    numero          = Column(String(50), nullable=False, index=True)
    tipo            = Column(Enum(TipoCuentaBancaria), nullable=False)
    moneda          = Column(String(10), default="COP")
    saldo_contable  = Column(Numeric(18, 2), nullable=False, default=0)
    saldo_disponible= Column(Numeric(18, 2), nullable=False, default=0)
    saldo_banco     = Column(Numeric(18, 2), nullable=True)
    cuenta_contable_id = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    descripcion     = Column(String(300), nullable=True)
    activo          = Column(Boolean, default=True)

    banco           = relationship("ERPBanco", back_populates="cuentas")
    movimientos     = relationship("ERPMovimientoBancario", back_populates="cuenta")


class ERPMovimientoBancario(Base, TimestampMixin):
    __tablename__ = "erp_movimientos_bancarios"

    id              = Column(Integer, primary_key=True, index=True)
    cuenta_id       = Column(Integer, ForeignKey("erp_cuentas_bancarias.id"), nullable=False)
    fecha           = Column(Date, nullable=False)
    tipo            = Column(Enum(TipoMovimientoBancario), nullable=False)
    monto           = Column(Numeric(18, 2), nullable=False)
    concepto        = Column(String(500), nullable=False)
    referencia      = Column(String(200), nullable=True)
    conciliado      = Column(Boolean, default=False)
    comprobante_id  = Column(Integer, ForeignKey("erp_comprobantes.id"), nullable=True)
    saldo_acumulado = Column(Numeric(18, 2), nullable=True)

    cuenta          = relationship("ERPCuentaBancaria", back_populates="movimientos")


# ── 6. IMPUESTOS ──────────────────────────────────────────────────────────────

class ERPTipoImpuesto(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_tipos_impuesto"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(200), nullable=False)
    codigo          = Column(String(20), nullable=False, unique=True)
    tipo            = Column(Enum(TipoImpuestoEnum), nullable=False)
    porcentaje      = Column(Numeric(8, 4), nullable=False, default=0)
    pais            = Column(String(100), default="Colombia")
    cuenta_debito_id  = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    cuenta_credito_id = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    descripcion     = Column(Text, nullable=True)
    activo          = Column(Boolean, default=True)


# ── 7. CUENTAS POR COBRAR ─────────────────────────────────────────────────────

class ERPFacturaCliente(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_facturas_cliente"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    numero          = Column(String(50), nullable=False, unique=True, index=True)
    numero_electronico = Column(String(100), nullable=True)
    cliente_nombre  = Column(String(300), nullable=False)
    cliente_nit     = Column(String(50), nullable=True)
    cliente_email   = Column(String(200), nullable=True)
    fecha           = Column(Date, nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    subtotal        = Column(Numeric(18, 2), nullable=False, default=0)
    descuento       = Column(Numeric(18, 2), nullable=False, default=0)
    total_impuestos = Column(Numeric(18, 2), nullable=False, default=0)
    total           = Column(Numeric(18, 2), nullable=False, default=0)
    saldo           = Column(Numeric(18, 2), nullable=False, default=0)
    moneda          = Column(String(10), default="COP")
    tasa_cambio     = Column(Numeric(12, 4), default=1)
    estado          = Column(Enum(EstadoFactura), nullable=False, default=EstadoFactura.BORRADOR)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    proyecto_id     = Column(Integer, ForeignKey("erp_proyectos.id"), nullable=True)
    concepto        = Column(String(500), nullable=True)
    observaciones   = Column(Text, nullable=True)
    cufe            = Column(String(200), nullable=True)  # DIAN code
    resolucion_id   = Column(Integer, ForeignKey("erp_resolucion_facturacion.id"), nullable=True)
    origen          = Column(String(20), nullable=True)        # POS, ERP…
    estado_dian     = Column(String(20), nullable=True)        # POR_TRANSMITIR, ACEPTADA, RECHAZADA

    lineas          = relationship("ERPLineaFacturaCliente", back_populates="factura", cascade="all, delete-orphan")
    pagos           = relationship("ERPPago", back_populates="factura_cliente")


class ERPLineaFacturaCliente(Base):
    __tablename__ = "erp_lineas_factura_cliente"

    id              = Column(Integer, primary_key=True, index=True)
    factura_id      = Column(Integer, ForeignKey("erp_facturas_cliente.id"), nullable=False)
    descripcion     = Column(String(500), nullable=False)
    cantidad        = Column(Numeric(12, 4), nullable=False, default=1)
    precio_unitario = Column(Numeric(18, 2), nullable=False, default=0)
    descuento_pct   = Column(Numeric(5, 2), default=0)
    impuesto_id     = Column(Integer, ForeignKey("erp_tipos_impuesto.id"), nullable=True)
    subtotal        = Column(Numeric(18, 2), nullable=False, default=0)
    total_impuesto  = Column(Numeric(18, 2), nullable=False, default=0)
    total           = Column(Numeric(18, 2), nullable=False, default=0)
    cuenta_id       = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)

    factura         = relationship("ERPFacturaCliente", back_populates="lineas")


# ── 8. CUENTAS POR PAGAR ──────────────────────────────────────────────────────

class ERPFacturaProveedor(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_facturas_proveedor"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    numero_proveedor= Column(String(100), nullable=False)
    proveedor_nombre= Column(String(300), nullable=False)
    proveedor_nit   = Column(String(50), nullable=True)
    fecha           = Column(Date, nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    fecha_registro  = Column(Date, nullable=True)
    subtotal        = Column(Numeric(18, 2), nullable=False, default=0)
    total_impuestos = Column(Numeric(18, 2), nullable=False, default=0)
    retenciones     = Column(Numeric(18, 2), nullable=False, default=0)
    total           = Column(Numeric(18, 2), nullable=False, default=0)
    neto_pagar      = Column(Numeric(18, 2), nullable=False, default=0)
    saldo           = Column(Numeric(18, 2), nullable=False, default=0)
    moneda          = Column(String(10), default="COP")
    estado          = Column(Enum(EstadoFactura), nullable=False, default=EstadoFactura.BORRADOR)
    orden_compra_id = Column(Integer, ForeignKey("erp_ordenes_compra.id"), nullable=True)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    concepto        = Column(String(500), nullable=True)
    observaciones   = Column(Text, nullable=True)

    pagos           = relationship("ERPPago", back_populates="factura_proveedor")


# ── 9. PAGOS ──────────────────────────────────────────────────────────────────

class ERPPago(Base, TimestampMixin):
    __tablename__ = "erp_pagos"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    tipo            = Column(Enum(TipoPago), nullable=False)
    numero          = Column(String(50), nullable=False, index=True)
    fecha           = Column(Date, nullable=False)
    factura_cliente_id  = Column(Integer, ForeignKey("erp_facturas_cliente.id"), nullable=True)
    factura_proveedor_id= Column(Integer, ForeignKey("erp_facturas_proveedor.id"), nullable=True)
    cuenta_bancaria_id  = Column(Integer, ForeignKey("erp_cuentas_bancarias.id"), nullable=True)
    monto           = Column(Numeric(18, 2), nullable=False)
    moneda          = Column(String(10), default="COP")
    metodo_pago     = Column(String(100), nullable=True)  # transferencia, cheque, efectivo
    referencia      = Column(String(200), nullable=True)
    estado          = Column(Enum(EstadoPago), nullable=False, default=EstadoPago.PROGRAMADO)
    comprobante_id  = Column(Integer, ForeignKey("erp_comprobantes.id"), nullable=True)
    concepto        = Column(String(300), nullable=True)

    factura_cliente   = relationship("ERPFacturaCliente", back_populates="pagos")
    factura_proveedor = relationship("ERPFacturaProveedor", back_populates="pagos")


# ── 10. PRESUPUESTOS ──────────────────────────────────────────────────────────

class ERPPresupuesto(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_presupuestos"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    nombre          = Column(String(300), nullable=False)
    tipo            = Column(Enum(TipoPresupuesto), nullable=False)
    anio            = Column(Integer, nullable=False)
    moneda          = Column(String(10), default="COP")
    estado          = Column(Enum(EstadoPresupuesto), nullable=False, default=EstadoPresupuesto.BORRADOR)
    total_presupuestado = Column(Numeric(18, 2), nullable=False, default=0)
    total_ejecutado     = Column(Numeric(18, 2), nullable=False, default=0)
    responsable     = Column(String(200), nullable=True)
    descripcion     = Column(Text, nullable=True)

    lineas          = relationship("ERPLineaPresupuesto", back_populates="presupuesto", cascade="all, delete-orphan")


class ERPLineaPresupuesto(Base):
    __tablename__ = "erp_lineas_presupuesto"

    id              = Column(Integer, primary_key=True, index=True)
    presupuesto_id  = Column(Integer, ForeignKey("erp_presupuestos.id"), nullable=False)
    cuenta_id       = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    descripcion     = Column(String(300), nullable=False)
    mes             = Column(Integer, nullable=False)  # 1-12
    monto_presupuestado = Column(Numeric(18, 2), nullable=False, default=0)
    monto_ejecutado     = Column(Numeric(18, 2), nullable=False, default=0)
    monto_comprometido  = Column(Numeric(18, 2), nullable=False, default=0)

    presupuesto     = relationship("ERPPresupuesto", back_populates="lineas")


# ── 11. ACTIVOS FIJOS ─────────────────────────────────────────────────────────

class ERPActivoFijo(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_activos_fijos"

    id                  = Column(Integer, primary_key=True, index=True)
    empresa_id          = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    codigo              = Column(String(50), nullable=False, unique=True, index=True)
    nombre              = Column(String(300), nullable=False)
    descripcion         = Column(Text, nullable=True)
    categoria           = Column(String(100), nullable=False)
    subcategoria        = Column(String(100), nullable=True)
    fecha_adquisicion   = Column(Date, nullable=False)
    valor_adquisicion   = Column(Numeric(18, 2), nullable=False)
    valor_residual      = Column(Numeric(18, 2), nullable=False, default=0)
    vida_util_meses     = Column(Integer, nullable=False, default=60)
    metodo_depreciacion = Column(Enum(MetodoDepreciacion), nullable=False, default=MetodoDepreciacion.LINEA_RECTA)
    depreciacion_acumulada = Column(Numeric(18, 2), nullable=False, default=0)
    valor_libro         = Column(Numeric(18, 2), nullable=False, default=0)
    estado              = Column(Enum(EstadoActivoFijo), nullable=False, default=EstadoActivoFijo.EN_USO)
    ubicacion           = Column(String(200), nullable=True)
    responsable         = Column(String(200), nullable=True)
    centro_costo_id     = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    cuenta_activo_id    = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    cuenta_dep_id       = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    serie               = Column(String(100), nullable=True)
    proveedor           = Column(String(300), nullable=True)
    garantia_meses      = Column(Integer, nullable=True)
    documento_compra    = Column(String(200), nullable=True)

    depreciaciones      = relationship("ERPDepreciacionActivo", back_populates="activo", cascade="all, delete-orphan")


class ERPDepreciacionActivo(Base, TimestampMixin):
    __tablename__ = "erp_depreciaciones_activo"

    id                  = Column(Integer, primary_key=True, index=True)
    activo_id           = Column(Integer, ForeignKey("erp_activos_fijos.id"), nullable=False)
    periodo             = Column(String(7), nullable=False)  # YYYY-MM
    fecha               = Column(Date, nullable=False)
    valor_depreciacion  = Column(Numeric(18, 2), nullable=False)
    depreciacion_acumulada = Column(Numeric(18, 2), nullable=False)
    valor_libro         = Column(Numeric(18, 2), nullable=False)
    comprobante_id      = Column(Integer, ForeignKey("erp_comprobantes.id"), nullable=True)

    activo              = relationship("ERPActivoFijo", back_populates="depreciaciones")


# ── 12. COMPRAS CORPORATIVAS ──────────────────────────────────────────────────

class ERPRequisicion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_requisiciones"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    numero          = Column(String(50), nullable=False, unique=True, index=True)
    solicitante     = Column(String(200), nullable=False)
    fecha           = Column(Date, nullable=False)
    fecha_requerida = Column(Date, nullable=False)
    estado          = Column(Enum(EstadoRequisicion), nullable=False, default=EstadoRequisicion.PENDIENTE)
    urgente         = Column(Boolean, default=False)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    justificacion   = Column(Text, nullable=True)
    aprobado_por    = Column(String(200), nullable=True)
    fecha_aprobacion= Column(Date, nullable=True)

    lineas          = relationship("ERPLineaRequisicion", back_populates="requisicion", cascade="all, delete-orphan")


class ERPLineaRequisicion(Base):
    __tablename__ = "erp_lineas_requisicion"

    id              = Column(Integer, primary_key=True, index=True)
    requisicion_id  = Column(Integer, ForeignKey("erp_requisiciones.id"), nullable=False)
    descripcion     = Column(String(500), nullable=False)
    unidad          = Column(String(50), nullable=True)
    cantidad        = Column(Numeric(12, 4), nullable=False, default=1)
    precio_estimado = Column(Numeric(18, 2), nullable=True)
    total_estimado  = Column(Numeric(18, 2), nullable=True)
    especificaciones= Column(Text, nullable=True)

    requisicion     = relationship("ERPRequisicion", back_populates="lineas")


class ERPOrdenCompra(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_ordenes_compra"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    numero          = Column(String(50), nullable=False, unique=True, index=True)
    proveedor_nombre= Column(String(300), nullable=False)
    proveedor_nit   = Column(String(50), nullable=True)
    fecha           = Column(Date, nullable=False)
    fecha_entrega   = Column(Date, nullable=True)
    estado          = Column(Enum(EstadoOC), nullable=False, default=EstadoOC.BORRADOR)
    subtotal        = Column(Numeric(18, 2), nullable=False, default=0)
    total_impuestos = Column(Numeric(18, 2), nullable=False, default=0)
    total           = Column(Numeric(18, 2), nullable=False, default=0)
    moneda          = Column(String(10), default="COP")
    condiciones_pago= Column(String(200), nullable=True)
    lugar_entrega   = Column(String(300), nullable=True)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    requisicion_id  = Column(Integer, ForeignKey("erp_requisiciones.id"), nullable=True)
    aprobado_por    = Column(String(200), nullable=True)
    fecha_aprobacion= Column(Date, nullable=True)
    observaciones   = Column(Text, nullable=True)

    lineas          = relationship("ERPLineaOrdenCompra", back_populates="orden", cascade="all, delete-orphan")
    facturas        = relationship("ERPFacturaProveedor", back_populates=None)


class ERPLineaOrdenCompra(Base):
    __tablename__ = "erp_lineas_oc"

    id              = Column(Integer, primary_key=True, index=True)
    orden_id        = Column(Integer, ForeignKey("erp_ordenes_compra.id"), nullable=False)
    descripcion     = Column(String(500), nullable=False)
    unidad          = Column(String(50), nullable=True)
    cantidad        = Column(Numeric(12, 4), nullable=False, default=1)
    precio_unitario = Column(Numeric(18, 2), nullable=False, default=0)
    descuento_pct   = Column(Numeric(5, 2), default=0)
    impuesto_id     = Column(Integer, ForeignKey("erp_tipos_impuesto.id"), nullable=True)
    subtotal        = Column(Numeric(18, 2), nullable=False, default=0)
    total_impuesto  = Column(Numeric(18, 2), nullable=False, default=0)
    total           = Column(Numeric(18, 2), nullable=False, default=0)
    cantidad_recibida = Column(Numeric(12, 4), nullable=False, default=0)
    cuenta_id       = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)

    orden           = relationship("ERPOrdenCompra", back_populates="lineas")


# ── 13. PROYECTOS FINANCIEROS ─────────────────────────────────────────────────

class ERPProyecto(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "erp_proyectos"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("erp_empresas.id"), nullable=True)
    codigo          = Column(String(50), nullable=False, unique=True, index=True)
    nombre          = Column(String(300), nullable=False)
    tipo            = Column(String(100), nullable=True)
    cliente         = Column(String(300), nullable=True)
    responsable     = Column(String(200), nullable=True)
    fecha_inicio    = Column(Date, nullable=False)
    fecha_fin       = Column(Date, nullable=True)
    presupuesto_total = Column(Numeric(18, 2), nullable=False, default=0)
    ejecutado_total   = Column(Numeric(18, 2), nullable=False, default=0)
    ingresos_total    = Column(Numeric(18, 2), nullable=False, default=0)
    estado          = Column(Enum(EstadoProyecto), nullable=False, default=EstadoProyecto.PLANEACION)
    centro_costo_id = Column(Integer, ForeignKey("erp_centros_costo.id"), nullable=True)
    descripcion     = Column(Text, nullable=True)

    gastos          = relationship("ERPGastoProyecto", back_populates="proyecto")
    facturas        = relationship("ERPFacturaCliente", back_populates=None)


class ERPGastoProyecto(Base, TimestampMixin):
    __tablename__ = "erp_gastos_proyecto"

    id              = Column(Integer, primary_key=True, index=True)
    proyecto_id     = Column(Integer, ForeignKey("erp_proyectos.id"), nullable=False)
    fecha           = Column(Date, nullable=False)
    descripcion     = Column(String(500), nullable=False)
    categoria       = Column(String(100), nullable=True)
    monto           = Column(Numeric(18, 2), nullable=False)
    proveedor       = Column(String(300), nullable=True)
    cuenta_id       = Column(Integer, ForeignKey("erp_plan_cuentas.id"), nullable=True)
    comprobante_id  = Column(Integer, ForeignKey("erp_comprobantes.id"), nullable=True)

    proyecto        = relationship("ERPProyecto", back_populates="gastos")


# ── 14. TASAS DE CAMBIO ───────────────────────────────────────────────────────

class ERPTasaCambio(Base, TimestampMixin):
    __tablename__ = "erp_tasas_cambio"

    id              = Column(Integer, primary_key=True, index=True)
    moneda_origen   = Column(String(10), nullable=False)
    moneda_destino  = Column(String(10), nullable=False)
    fecha           = Column(Date, nullable=False)
    tasa            = Column(Numeric(16, 6), nullable=False)
    fuente          = Column(String(100), nullable=True)

    __table_args__ = (UniqueConstraint("moneda_origen", "moneda_destino", "fecha", name="uq_tasa_cambio"),)


# ── 15. AUDITORÍA ERP ─────────────────────────────────────────────────────────

class ERPAuditoria(Base, TimestampMixin):
    __tablename__ = "erp_auditoria"

    id              = Column(Integer, primary_key=True, index=True)
    modulo          = Column(String(100), nullable=False)
    entidad         = Column(String(100), nullable=False)
    entidad_id      = Column(Integer, nullable=True)
    accion          = Column(String(50), nullable=False)
    usuario         = Column(String(200), nullable=False)
    ip              = Column(String(50), nullable=True)
    datos_antes     = Column(Text, nullable=True)
    datos_despues   = Column(Text, nullable=True)
    observaciones   = Column(Text, nullable=True)
    # Tres columnas que le faltaban para servir de auditoria financiera: sin
    # empresa no se puede separar el rastro de cada una, y sin saber de que
    # documento salio un asiento la trazabilidad se corta justo donde importa.
    empresa_id      = Column(Integer, nullable=True, index=True)
    documento_origen = Column(String(120), nullable=True)

    __table_args__ = (Index("ix_erp_auditoria_modulo_fecha", "modulo", "created_at"),)


class ERPConfigGeneral(Base, TimestampMixin):
    """Parámetros generales del ERP (fila única id=1)."""
    __tablename__ = "erp_config_general"

    id                     = Column(Integer, primary_key=True, index=True)
    moneda_base            = Column(String(10), nullable=False, default="COP")
    norma_contable         = Column(String(50), nullable=False, default="NIIF")
    metodo_inventario      = Column(String(50), nullable=False, default="PROMEDIO_PONDERADO")
    periodo_fiscal_inicio  = Column(String(10), nullable=False, default="01-01")
    dias_vencimiento_cxc   = Column(Integer, nullable=False, default=30)
    dias_vencimiento_cxp   = Column(Integer, nullable=False, default=30)
    aprobacion_compras     = Column(Boolean, nullable=False, default=True)
    aprobacion_presupuesto = Column(Boolean, nullable=False, default=True)
