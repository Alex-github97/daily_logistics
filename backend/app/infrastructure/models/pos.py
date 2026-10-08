"""
POS · Punto de venta.

Vende en mostrador desde el inventario del WMS habilitado para ello (las zonas
marcadas como vendibles del almacén de cada caja) y factura en el ERP. Una venta
confirmada es UNA transacción: descuenta existencias (con bloqueo de fila y sin
saldos negativos), emite la factura con numeración de la resolución DIAN y deja
el asiento contable (caja o banco contra ingreso e IVA, y costo de ventas contra
inventario). Una devolución hace lo contrario con nota crédito.

Los precios salen de listas (cada caja usa una), con IVA incluido como se cobra
al público. El dinero se controla por turnos: apertura con base, entradas y
salidas de efectivo, y cierre con arqueo por medio de pago.
"""
import enum

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


class MedioPagoPOS(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    TARJETA_DEBITO = "TARJETA_DEBITO"
    TARJETA_CREDITO = "TARJETA_CREDITO"
    NEQUI = "NEQUI"
    DAVIPLATA = "DAVIPLATA"
    TRANSFERENCIA = "TRANSFERENCIA"
    QR = "QR"


class POSListaPrecio(Base, TimestampMixin):
    __tablename__ = "pos_lista_precio"
    id = sa.Column(sa.Integer, primary_key=True)
    nombre = sa.Column(sa.String(120), nullable=False, unique=True)
    descripcion = sa.Column(sa.Text)
    activa = sa.Column(sa.Boolean, nullable=False, default=True)

    precios = relationship("POSPrecio", back_populates="lista", cascade="all, delete-orphan")


class POSPrecio(Base, TimestampMixin):
    __tablename__ = "pos_precio"
    __table_args__ = (sa.UniqueConstraint("lista_id", "producto_id", name="uq_pos_precio"),)
    id = sa.Column(sa.Integer, primary_key=True)
    lista_id = sa.Column(sa.Integer, sa.ForeignKey("pos_lista_precio.id", ondelete="CASCADE"), nullable=False, index=True)
    producto_id = sa.Column(sa.Integer, sa.ForeignKey("wms_productos.id"), nullable=False, index=True)
    # Precio al público, IVA incluido.
    precio = sa.Column(sa.Numeric(18, 2), nullable=False)
    lista = relationship("POSListaPrecio", back_populates="precios")


class POSCaja(Base, TimestampMixin):
    __tablename__ = "pos_caja"
    id = sa.Column(sa.Integer, primary_key=True)
    codigo = sa.Column(sa.String(20), nullable=False, unique=True)
    nombre = sa.Column(sa.String(120), nullable=False)
    almacen_id = sa.Column(sa.Integer, sa.ForeignKey("wms_almacenes.id"), nullable=False)
    lista_id = sa.Column(sa.Integer, sa.ForeignKey("pos_lista_precio.id"), nullable=False)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"))
    resolucion_id = sa.Column(sa.Integer, sa.ForeignKey("erp_resolucion_facturacion.id"))
    # Descuento máximo que el cajero puede dar sin autorización (%).
    descuento_maximo = sa.Column(sa.Numeric(5, 2), nullable=False, default=0)
    activa = sa.Column(sa.Boolean, nullable=False, default=True)


class POSTurno(Base, TimestampMixin):
    __tablename__ = "pos_turno"
    id = sa.Column(sa.Integer, primary_key=True)
    caja_id = sa.Column(sa.Integer, sa.ForeignKey("pos_caja.id"), nullable=False, index=True)
    cajero_id = sa.Column(sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False)
    apertura = sa.Column(sa.DateTime(timezone=True), nullable=False)
    base_inicial = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    cierre = sa.Column(sa.DateTime(timezone=True))
    estado = sa.Column(sa.String(10), nullable=False, default="ABIERTO")   # ABIERTO | CERRADO
    # Al cierre: lo que el sistema esperaba y lo que el cajero contó, por medio.
    esperado = sa.Column(sa.JSON)
    contado = sa.Column(sa.JSON)
    diferencia = sa.Column(sa.Numeric(18, 2))
    observaciones = sa.Column(sa.Text)


class POSMovimientoCaja(Base, TimestampMixin):
    """Entrada o salida de efectivo que no es una venta (cambio, pago menor…)."""
    __tablename__ = "pos_movimiento_caja"
    id = sa.Column(sa.Integer, primary_key=True)
    turno_id = sa.Column(sa.Integer, sa.ForeignKey("pos_turno.id"), nullable=False, index=True)
    tipo = sa.Column(sa.String(10), nullable=False)          # INGRESO | RETIRO
    monto = sa.Column(sa.Numeric(18, 2), nullable=False)
    motivo = sa.Column(sa.String(300), nullable=False)
    usuario_id = sa.Column(sa.Integer, sa.ForeignKey("usuarios.id"))


class POSVenta(Base, TimestampMixin):
    __tablename__ = "pos_venta"
    id = sa.Column(sa.Integer, primary_key=True)
    numero = sa.Column(sa.String(40), nullable=False, unique=True)
    turno_id = sa.Column(sa.Integer, sa.ForeignKey("pos_turno.id"), nullable=False, index=True)
    caja_id = sa.Column(sa.Integer, sa.ForeignKey("pos_caja.id"), nullable=False, index=True)
    cajero_id = sa.Column(sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False)
    fecha = sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    tercero_id = sa.Column(sa.Integer, sa.ForeignKey("erp_terceros.id"))
    cliente_nombre = sa.Column(sa.String(300), nullable=False, default="Consumidor final")
    cliente_documento = sa.Column(sa.String(30))
    cliente_email = sa.Column(sa.String(200))
    subtotal = sa.Column(sa.Numeric(18, 2), nullable=False)     # base gravable + exenta
    descuento = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    impuestos = sa.Column(sa.Numeric(18, 2), nullable=False)
    total = sa.Column(sa.Numeric(18, 2), nullable=False)
    costo_total = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    recibido = sa.Column(sa.Numeric(18, 2))                   # efectivo entregado
    cambio = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    estado = sa.Column(sa.String(20), nullable=False, default="PAGADA")   # PAGADA | DEVUELTA_PARCIAL | DEVUELTA
    factura_id = sa.Column(sa.Integer, sa.ForeignKey("erp_facturas_cliente.id"))
    comprobante_id = sa.Column(sa.Integer, sa.ForeignKey("erp_comprobantes.id"))
    cufe = sa.Column(sa.String(200))

    lineas = relationship("POSVentaLinea", back_populates="venta", cascade="all, delete-orphan")
    pagos = relationship("POSPago", back_populates="venta", cascade="all, delete-orphan")


class POSVentaLinea(Base):
    __tablename__ = "pos_venta_linea"
    id = sa.Column(sa.Integer, primary_key=True)
    venta_id = sa.Column(sa.Integer, sa.ForeignKey("pos_venta.id", ondelete="CASCADE"), nullable=False, index=True)
    producto_id = sa.Column(sa.Integer, sa.ForeignKey("wms_productos.id"), nullable=False)
    descripcion = sa.Column(sa.String(300), nullable=False)
    cantidad = sa.Column(sa.Numeric(18, 4), nullable=False)
    precio_unitario = sa.Column(sa.Numeric(18, 2), nullable=False)   # IVA incluido
    descuento_pct = sa.Column(sa.Numeric(5, 2), nullable=False, default=0)
    tarifa_iva = sa.Column(sa.Numeric(5, 2), nullable=False, default=0)
    base = sa.Column(sa.Numeric(18, 2), nullable=False)
    iva = sa.Column(sa.Numeric(18, 2), nullable=False)
    total = sa.Column(sa.Numeric(18, 2), nullable=False)
    costo_unitario = sa.Column(sa.Numeric(18, 4), nullable=False, default=0)
    # De qué ubicación y lote salió cada parte: [{ubicacion_id, lote_id, cantidad}]
    salidas = sa.Column(sa.JSON, nullable=False, default=list)
    cantidad_devuelta = sa.Column(sa.Numeric(18, 4), nullable=False, default=0)

    venta = relationship("POSVenta", back_populates="lineas")


class POSPago(Base):
    __tablename__ = "pos_pago"
    id = sa.Column(sa.Integer, primary_key=True)
    venta_id = sa.Column(sa.Integer, sa.ForeignKey("pos_venta.id", ondelete="CASCADE"), nullable=False, index=True)
    medio = sa.Column(sa.String(20), nullable=False)
    monto = sa.Column(sa.Numeric(18, 2), nullable=False)
    referencia = sa.Column(sa.String(80))                  # aprobación del datáfono, comprobante Nequi…
    venta = relationship("POSVenta", back_populates="pagos")


class POSDevolucion(Base, TimestampMixin):
    __tablename__ = "pos_devolucion"
    id = sa.Column(sa.Integer, primary_key=True)
    venta_id = sa.Column(sa.Integer, sa.ForeignKey("pos_venta.id"), nullable=False, index=True)
    turno_id = sa.Column(sa.Integer, sa.ForeignKey("pos_turno.id"), nullable=False, index=True)
    cajero_id = sa.Column(sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False)
    fecha = sa.Column(sa.DateTime(timezone=True), nullable=False)
    motivo = sa.Column(sa.Text, nullable=False)
    medio_reembolso = sa.Column(sa.String(20), nullable=False)
    subtotal = sa.Column(sa.Numeric(18, 2), nullable=False)
    impuestos = sa.Column(sa.Numeric(18, 2), nullable=False)
    total = sa.Column(sa.Numeric(18, 2), nullable=False)
    costo_total = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    nota_credito_id = sa.Column(sa.Integer, sa.ForeignKey("erp_nota_credito_cliente.id"))
    comprobante_id = sa.Column(sa.Integer, sa.ForeignKey("erp_comprobantes.id"))
    # [{linea_id, cantidad, estado: BUENO|DANADO, ubicacion_id}]
    lineas = sa.Column(sa.JSON, nullable=False, default=list)
