"""
Canales de venta en línea: marketplaces y tiendas (Daily Logistics).

Un CONECTOR es una cuenta de una plataforma (MercadoLibre, Shopify,
WooCommerce, VTEX, Rappi) o una fuente sin API (importación de archivo,
webhook genérico). De cada conector entran PEDIDOS, que se convierten en
órdenes de salida del WMS; y hacia cada conector sale el STOCK publicable de
los productos mapeados en PUBLICACIONES.

Las colas (`mkp_cola_stock`, `mkp_cola_estado`) desacoplan el trabajo con las
APIs externas de las transacciones del WMS: un movimiento de inventario solo
anota «este producto cambió», y un proceso en segundo plano publica el stock.
Si la API externa está caída, el WMS sigue funcionando y la cola se reintenta.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func,
)

from app.core.tenant import ESQUEMA_PLATAFORMA
from app.infrastructure.models.base import Base, TimestampMixin

# Plataformas soportadas.
TIPOS_CONECTOR = ("MERCADOLIBRE", "SHOPIFY", "WOOCOMMERCE", "VTEX", "RAPPI", "ARCHIVO", "WEBHOOK")


class MKPConector(Base, TimestampMixin):
    __tablename__ = "mkp_conectores"
    id                = Column(Integer, primary_key=True, index=True)
    tipo              = Column(String(20), nullable=False, index=True)
    nombre            = Column(String(120), nullable=False)
    activo            = Column(Boolean, nullable=False, default=True)
    # Desde dónde se despachan sus pedidos y a nombre de qué cliente WMS quedan.
    almacen_id        = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False)
    cliente_id        = Column(Integer, ForeignKey("wms_clientes.id"), nullable=True)
    # Credenciales y parámetros de la plataforma (tokens, dominio, claves…).
    credenciales      = Column(JSON, nullable=False, default=dict)
    config            = Column(JSON, nullable=False, default=dict)
    # Unidades que se restan al publicar, para no vender lo que no hay.
    colchon_stock     = Column(Integer, nullable=False, default=0)
    sincronizar_stock = Column(Boolean, nullable=False, default=True)
    importar_pedidos  = Column(Boolean, nullable=False, default=True)
    # Token secreto de la URL pública de avisos (webhooks) de este conector.
    token_webhook     = Column(String(64), nullable=False, unique=True)
    estado_conexion   = Column(String(20), nullable=False, default="SIN_PROBAR")  # OK / ERROR / SIN_PROBAR
    ultimo_error      = Column(Text, nullable=True)
    ultima_sync_pedidos = Column(DateTime(timezone=True), nullable=True)
    ultima_sync_stock   = Column(DateTime(timezone=True), nullable=True)


class MKPPublicacion(Base, TimestampMixin):
    """Un producto del WMS publicado en un conector (lo que se vende allá)."""
    __tablename__ = "mkp_publicaciones"
    __table_args__ = (UniqueConstraint("conector_id", "ref_externa", "ref_variante", name="uq_mkp_publicacion"),)
    id            = Column(Integer, primary_key=True, index=True)
    conector_id   = Column(Integer, ForeignKey("mkp_conectores.id", ondelete="CASCADE"), nullable=False, index=True)
    producto_id   = Column(Integer, ForeignKey("wms_productos.id"), nullable=True, index=True)
    # Identificador de la publicación en la plataforma (item de MercadoLibre,
    # producto/variante de Shopify o WooCommerce, SKU de VTEX…).
    ref_externa   = Column(String(120), nullable=False)
    ref_variante  = Column(String(120), nullable=False, default="")
    # Para el inventario de Shopify (inventory_item_id).
    ref_inventario = Column(String(120), nullable=True)
    sku_externo   = Column(String(120), nullable=True, index=True)
    titulo        = Column(String(300), nullable=True)
    # Cuántas unidades del producto vende una publicación (un «pack x6» = 6).
    unidades      = Column(Float, nullable=False, default=1)
    activo        = Column(Boolean, nullable=False, default=True)
    ultimo_stock_enviado = Column(Integer, nullable=True)
    ultimo_envio  = Column(DateTime(timezone=True), nullable=True)
    ultimo_error  = Column(Text, nullable=True)


class MKPPedido(Base, TimestampMixin):
    """Un pedido de un canal. Se registra una sola vez aunque llegue repetido."""
    __tablename__ = "mkp_pedidos"
    __table_args__ = (UniqueConstraint("conector_id", "pedido_externo", name="uq_mkp_pedido"),)
    id              = Column(Integer, primary_key=True, index=True)
    conector_id     = Column(Integer, ForeignKey("mkp_conectores.id"), nullable=False, index=True)
    pedido_externo  = Column(String(120), nullable=False)
    envio_externo   = Column(String(120), nullable=True)      # p. ej. shipment de MercadoLibre
    estado_externo  = Column(String(40), nullable=True)
    # RECIBIDO → COMPROMETIDO → EN_STAGING → DESPACHADO → ENTREGADO; o CON_NOVEDAD / CANCELADO.
    estado          = Column(String(20), nullable=False, default="RECIBIDO", index=True)
    novedad         = Column(Text, nullable=True)
    fecha_pedido    = Column(DateTime(timezone=True), nullable=True)
    comprador       = Column(String(200), nullable=True)
    documento       = Column(String(40), nullable=True)
    telefono        = Column(String(40), nullable=True)
    email           = Column(String(200), nullable=True)
    direccion       = Column(String(400), nullable=True)
    ciudad          = Column(String(120), nullable=True)
    total           = Column(Numeric(18, 2), nullable=True)
    orden_salida_id = Column(Integer, ForeignKey("wms_ordenes_salida.id"), nullable=True, index=True)
    despacho_id     = Column(Integer, ForeignKey("wms_despachos.id"), nullable=True)
    tracking        = Column(String(120), nullable=True)
    crudo           = Column(JSON, nullable=True)            # lo que mandó la plataforma, tal cual


class MKPPedidoLinea(Base):
    __tablename__ = "mkp_pedido_lineas"
    id           = Column(Integer, primary_key=True)
    pedido_id    = Column(Integer, ForeignKey("mkp_pedidos.id", ondelete="CASCADE"), nullable=False, index=True)
    ref_externa  = Column(String(120), nullable=True)
    ref_variante = Column(String(120), nullable=True)
    sku_externo  = Column(String(120), nullable=True)
    titulo       = Column(String(300), nullable=True)
    cantidad     = Column(Float, nullable=False)
    precio       = Column(Numeric(18, 2), nullable=True)
    producto_id  = Column(Integer, ForeignKey("wms_productos.id"), nullable=True)
    unidades     = Column(Float, nullable=True)              # cantidad × unidades de la publicación


class MKPColaStock(Base):
    """«Este producto cambió de stock»: el proceso de fondo publica su cantidad."""
    __tablename__ = "mkp_cola_stock"
    producto_id = Column(Integer, primary_key=True)
    anotado     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MKPColaEstado(Base):
    """Avisos pendientes hacia la plataforma: ENVIADO (con guía) o ENTREGADO."""
    __tablename__ = "mkp_cola_estado"
    id         = Column(Integer, primary_key=True)
    pedido_id  = Column(Integer, ForeignKey("mkp_pedidos.id", ondelete="CASCADE"), nullable=False)
    evento     = Column(String(20), nullable=False)
    intentos   = Column(Integer, nullable=False, default=0)
    ultimo_error = Column(Text, nullable=True)
    creado     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MKPBitacora(Base):
    """Lo que pasó con cada conector: pedidos recibidos, stock enviado, errores."""
    __tablename__ = "mkp_bitacora"
    id          = Column(Integer, primary_key=True)
    conector_id = Column(Integer, ForeignKey("mkp_conectores.id", ondelete="CASCADE"), nullable=True, index=True)
    fecha       = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    tipo        = Column(String(30), nullable=False)      # PEDIDO / STOCK / ESTADO / CONEXION / WEBHOOK / IMPORTACION
    ok          = Column(Boolean, nullable=False, default=True)
    mensaje     = Column(Text, nullable=False)


class MKPRegistroPublico(Base):
    """Token de webhook → empresa. Vive en `public` porque el aviso de un
    marketplace llega sin sesión: con el token se sabe a qué esquema va."""
    __tablename__ = "mkp_registro_publico"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}
    token       = Column(String(64), primary_key=True)
    esquema     = Column(String(60), nullable=False)
    conector_id = Column(Integer, nullable=False)
    tipo        = Column(String(20), nullable=False)
