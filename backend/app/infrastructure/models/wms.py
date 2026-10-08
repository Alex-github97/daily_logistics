"""
Módulo WMS (Warehouse Management System) — Modelos de base de datos
Prefijo de tabla: wms_
"""
from datetime import datetime, timezone as _tz
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, ForeignKey, Text,
    Date, DateTime, JSON, UniqueConstraint, Numeric, Index, func
)
from sqlalchemy.orm import relationship
from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ─── Catálogos ─────────────────────────────────────────────────────────────────

class WMSTipoZona(Base, TimestampMixin):
    __tablename__ = "wms_tipos_zona"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(60), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)
    activo      = Column(Boolean, default=True)


class WMSTipoUbicacion(Base, TimestampMixin):
    __tablename__ = "wms_tipos_ubicacion"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(60), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)
    activo      = Column(Boolean, default=True)


class WMSUnidadMedida(Base, TimestampMixin):
    __tablename__ = "wms_unidades_medida"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(60), nullable=False, unique=True)
    abreviatura = Column(String(15), nullable=True)
    activo      = Column(Boolean, default=True)


class WMSMotivoMovimiento(Base, TimestampMixin):
    """Motivos configurables para reservas y bloqueos de inventario."""
    __tablename__ = "wms_motivos_movimiento"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False)
    tipo   = Column(String(20), nullable=False, default="RESERVA")  # RESERVA / BLOQUEO
    activo = Column(Boolean, default=True)


class WMSCategoriaProducto(Base, TimestampMixin):
    __tablename__ = "wms_categorias_producto"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    activo = Column(Boolean, default=True)

    familias = relationship("WMSFamiliaProducto", back_populates="categoria")


class WMSFamiliaProducto(Base, TimestampMixin):
    __tablename__ = "wms_familias_producto"
    id           = Column(Integer, primary_key=True, index=True)
    nombre       = Column(String(100), nullable=False)
    categoria_id = Column(Integer, ForeignKey("wms_categorias_producto.id"), nullable=False)
    activo       = Column(Boolean, default=True)

    categoria = relationship("WMSCategoriaProducto", back_populates="familias")


class WMSPais(Base, TimestampMixin):
    __tablename__ = "wms_paises"
    id         = Column(Integer, primary_key=True, index=True)
    nombre     = Column(String(100), nullable=False, unique=True)
    codigo_iso = Column(String(5), nullable=True)
    activo     = Column(Boolean, default=True)

    ciudades = relationship("WMSCiudad", back_populates="pais")


class WMSCiudad(Base, TimestampMixin):
    __tablename__ = "wms_ciudades"
    id      = Column(Integer, primary_key=True, index=True)
    nombre  = Column(String(100), nullable=False)
    pais_id = Column(Integer, ForeignKey("wms_paises.id"), nullable=False)
    activo  = Column(Boolean, default=True)

    pais = relationship("WMSPais", back_populates="ciudades")


class WMSAlmacen(Base, TimestampMixin):
    __tablename__ = "wms_almacenes"
    id        = Column(Integer, primary_key=True, index=True)
    codigo    = Column(String(30), nullable=False, unique=True, index=True)
    nombre    = Column(String(150), nullable=False)
    direccion = Column(String(255), nullable=True)
    ciudad    = Column(String(100), nullable=True)
    pais      = Column(String(80), nullable=True)
    # DIRECTO: la recepción deja la mercancía en su ubicación final.
    # DIRIGIDO: la deja en la zona de recepción, en una estiba (LPN) por línea,
    # y crea una tarea de ubicación por estiba con la ubicación sugerida. Es lo
    # que permite medir de muelle a estantería y saber quién ubicó qué.
    flujo_recepcion = Column(String(12), nullable=False, default="DIRECTO", server_default="DIRECTO")
    activo    = Column(Boolean, default=True)

    zonas            = relationship("WMSZona", back_populates="almacen")
    ordenes_compra   = relationship("WMSOrdenCompra", back_populates="almacen")
    recepciones      = relationship("WMSRecepcion", back_populates="almacen")
    ordenes_salida   = relationship("WMSOrdenSalida", back_populates="almacen")
    conteos          = relationship("WMSConteoInventario", back_populates="almacen")
    devoluciones     = relationship("WMSDevolucion", back_populates="almacen")
    kpis_diarios     = relationship("WMSKPIDiario", back_populates="almacen")


class WMSZona(Base, TimestampMixin):
    __tablename__ = "wms_zonas"
    id                    = Column(Integer, primary_key=True, index=True)
    almacen_id            = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False)
    codigo                = Column(String(30), nullable=False, unique=True, index=True)
    nombre                = Column(String(150), nullable=False)
    # RECEPCION/ALMACENAMIENTO/DESPACHO/CUARENTENA/CROSS_DOCKING
    tipo                  = Column(String(30), nullable=False, default="ALMACENAMIENTO")
    temperatura_controlada = Column(Boolean, default=False)
    # Lo que hay en una zona vendible lo puede vender el POS del almacén.
    # Recepción, cuarentena y despacho nunca se marcan.
    vendible_pos          = Column(Boolean, nullable=False, default=False)
    activo                = Column(Boolean, default=True)

    almacen    = relationship("WMSAlmacen", back_populates="zonas")
    ubicaciones = relationship("WMSUbicacion", back_populates="zona")


class WMSUbicacion(Base, TimestampMixin):
    __tablename__ = "wms_ubicaciones"
    id            = Column(Integer, primary_key=True, index=True)
    zona_id       = Column(Integer, ForeignKey("wms_zonas.id"), nullable=False)
    codigo        = Column(String(30), nullable=False, unique=True, index=True)
    pasillo       = Column(String(20), nullable=True)
    estanteria    = Column(String(20), nullable=True)
    nivel         = Column(String(20), nullable=True)
    posicion      = Column(String(20), nullable=True)
    # ESTANDAR/PALLET/SUELO/CAMARA_FRIO/RESTRINGIDA/CUARENTENA
    tipo          = Column(String(30), nullable=False, default="ESTANDAR")
    capacidad_kg  = Column(Float, nullable=True)
    capacidad_m3  = Column(Float, nullable=True)
    # Medidas internas útiles (frente × fondo × alto libre). Con ellas la
    # capacidad en m³ se calcula, y se sabe cuántas cajas caben y en qué posición.
    largo_cm      = Column(Float, nullable=True)
    ancho_cm      = Column(Float, nullable=True)
    alto_cm       = Column(Float, nullable=True)
    # Lugar de la ubicación en el recorrido de alistamiento (1 = la primera
    # desde el muelle). Vacío: se deduce de pasillo y posición en serpentina.
    orden_recorrido = Column(Integer, nullable=True)
    activo        = Column(Boolean, default=True)

    zona              = relationship("WMSZona", back_populates="ubicaciones")
    inventarios       = relationship("WMSInventarioUbicacion", back_populates="ubicacion")
    movimientos_origen  = relationship("WMSMovimientoInventario", foreign_keys="WMSMovimientoInventario.ubicacion_origen_id", back_populates="ubicacion_origen")
    movimientos_destino = relationship("WMSMovimientoInventario", foreign_keys="WMSMovimientoInventario.ubicacion_destino_id", back_populates="ubicacion_destino")
    recepciones_detalle = relationship("WMSRecepcionDetalle", back_populates="ubicacion")
    picking_detalles    = relationship("WMSPickingDetalle", back_populates="ubicacion")
    conteos_detalle     = relationship("WMSConteoDetalle", back_populates="ubicacion")
    eventos_trazabilidad = relationship("WMSEventoTrazabilidad", back_populates="ubicacion")


class WMSProducto(Base, TimestampMixin):
    __tablename__ = "wms_productos"
    id                    = Column(Integer, primary_key=True, index=True)
    sku                   = Column(String(80), nullable=False, unique=True, index=True)
    nombre                = Column(String(200), nullable=False)
    descripcion           = Column(Text, nullable=True)
    categoria             = Column(String(100), nullable=True)
    familia               = Column(String(100), nullable=True)
    unidad_medida         = Column(String(30), nullable=False, default="UNIDAD")
    peso_kg               = Column(Float, nullable=True)
    volumen_m3            = Column(Float, nullable=True)
    requiere_refrigeracion = Column(Boolean, default=False)
    requiere_serial       = Column(Boolean, default=False)
    requiere_lote         = Column(Boolean, default=False)
    vida_util_dias        = Column(Integer, nullable=True)
    imagen_url            = Column(String(500), nullable=True)
    # Para vender: código de barras (EAN/GTIN), tarifa de IVA y costo promedio
    # ponderado, que se recalcula en cada entrada valorizada (recepción).
    codigo_barras         = Column(String(60), nullable=True, index=True)
    tarifa_iva            = Column(Numeric(5, 2), nullable=False, default=19)
    costo_promedio        = Column(Numeric(18, 4), nullable=False, default=0)
    # Dueño de la mercancía (operación 3PL). Cada referencia es de un solo
    # depositante: así el inventario de un cliente nunca se mezcla con el de otro.
    depositante_id        = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True, index=True)
    activo                = Column(Boolean, default=True)

    lotes               = relationship("WMSLote", back_populates="producto")
    series              = relationship("WMSSerie", back_populates="producto")
    inventarios         = relationship("WMSInventarioUbicacion", back_populates="producto")
    movimientos         = relationship("WMSMovimientoInventario", back_populates="producto")
    recepciones_detalle = relationship("WMSRecepcionDetalle", back_populates="producto")
    oc_detalles         = relationship("WMSOrdenCompraDetalle", back_populates="producto")
    salida_detalles     = relationship("WMSOrdenSalidaDetalle", back_populates="producto")
    picking_detalles    = relationship("WMSPickingDetalle", back_populates="producto")
    despacho_detalles   = relationship("WMSDespachoDetalle", back_populates="producto")
    conteos_detalle     = relationship("WMSConteoDetalle", back_populates="producto")
    devolucion_detalles = relationship("WMSDevolucionDetalle", back_populates="producto")
    eventos_trazabilidad = relationship("WMSEventoTrazabilidad", back_populates="producto")


class WMSLote(Base, TimestampMixin):
    __tablename__ = "wms_lotes"
    id             = Column(Integer, primary_key=True, index=True)
    producto_id    = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    numero_lote    = Column(String(100), nullable=False)
    fecha_fabricacion = Column(Date, nullable=True)
    fecha_vencimiento = Column(Date, nullable=True)
    proveedor_lote = Column(String(150), nullable=True)
    activo         = Column(Boolean, default=True)

    producto            = relationship("WMSProducto", back_populates="lotes")
    series              = relationship("WMSSerie", back_populates="lote")
    inventarios         = relationship("WMSInventarioUbicacion", back_populates="lote")
    movimientos         = relationship("WMSMovimientoInventario", back_populates="lote")
    recepciones_detalle = relationship("WMSRecepcionDetalle", back_populates="lote")
    salida_detalles     = relationship("WMSOrdenSalidaDetalle", back_populates="lote")
    picking_detalles    = relationship("WMSPickingDetalle", back_populates="lote")
    despacho_detalles   = relationship("WMSDespachoDetalle", back_populates="lote")
    conteos_detalle     = relationship("WMSConteoDetalle", back_populates="lote")
    devolucion_detalles = relationship("WMSDevolucionDetalle", back_populates="lote")
    eventos_trazabilidad = relationship("WMSEventoTrazabilidad", back_populates="lote")


class WMSSerie(Base, TimestampMixin):
    __tablename__ = "wms_series"
    id           = Column(Integer, primary_key=True, index=True)
    producto_id  = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    lote_id      = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    numero_serie = Column(String(150), nullable=False, unique=True, index=True)
    # DISPONIBLE/ASIGNADO/DESPACHADO/DEVUELTO/DADO_DE_BAJA
    estado       = Column(String(30), nullable=False, default="DISPONIBLE")
    activo       = Column(Boolean, default=True)

    producto    = relationship("WMSProducto", back_populates="series")
    lote        = relationship("WMSLote", back_populates="series")
    movimientos = relationship("WMSMovimientoInventario", back_populates="serie")


class WMSProveedor(Base, TimestampMixin):
    __tablename__ = "wms_proveedores"
    id       = Column(Integer, primary_key=True, index=True)
    codigo   = Column(String(30), nullable=False, unique=True, index=True)
    nombre   = Column(String(150), nullable=False)
    nit      = Column(String(30), nullable=True)
    contacto = Column(String(100), nullable=True)
    email    = Column(String(120), nullable=True)
    telefono = Column(String(30), nullable=True)
    ciudad   = Column(String(100), nullable=True)
    pais     = Column(String(80), nullable=True)
    activo   = Column(Boolean, default=True)

    ordenes_compra = relationship("WMSOrdenCompra", back_populates="proveedor")
    devoluciones   = relationship("WMSDevolucion", back_populates="proveedor")


class WMSCliente(Base, TimestampMixin):
    __tablename__ = "wms_clientes"
    id       = Column(Integer, primary_key=True, index=True)
    codigo   = Column(String(30), nullable=False, unique=True, index=True)
    nombre   = Column(String(150), nullable=False)
    nit      = Column(String(30), nullable=True)
    contacto = Column(String(100), nullable=True)
    email    = Column(String(120), nullable=True)
    telefono = Column(String(30), nullable=True)
    ciudad   = Column(String(100), nullable=True)
    pais     = Column(String(80), nullable=True)
    segmento = Column(String(60), nullable=True)
    activo   = Column(Boolean, default=True)

    ordenes_salida = relationship("WMSOrdenSalida", back_populates="cliente")
    devoluciones   = relationship("WMSDevolucion", back_populates="cliente")


class WMSTransportadora(Base, TimestampMixin):
    __tablename__ = "wms_transportadoras"
    id       = Column(Integer, primary_key=True, index=True)
    codigo   = Column(String(30), nullable=False, unique=True, index=True)
    nombre   = Column(String(150), nullable=False)
    nit      = Column(String(30), nullable=True)
    contacto = Column(String(100), nullable=True)
    telefono = Column(String(30), nullable=True)
    activo   = Column(Boolean, default=True)

    despachos = relationship("WMSDespacho", back_populates="transportadora")


# ─── Inbound ───────────────────────────────────────────────────────────────────

class WMSOrdenCompra(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "wms_ordenes_compra"
    id             = Column(Integer, primary_key=True, index=True)
    numero_oc      = Column(String(60), nullable=False, unique=True, index=True)
    proveedor_id   = Column(Integer, ForeignKey("wms_proveedores.id"), nullable=False)
    almacen_id     = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False)
    depositante_id = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True, index=True)
    fecha_emision  = Column(Date, nullable=False)
    fecha_esperada = Column(Date, nullable=True)
    # PENDIENTE/PARCIAL/COMPLETA/CANCELADA
    estado         = Column(String(20), nullable=False, default="PENDIENTE")
    notas          = Column(Text, nullable=True)

    proveedor  = relationship("WMSProveedor", back_populates="ordenes_compra")
    almacen    = relationship("WMSAlmacen", back_populates="ordenes_compra")
    detalles   = relationship("WMSOrdenCompraDetalle", back_populates="orden", cascade="all, delete-orphan")
    recepciones = relationship("WMSRecepcion", back_populates="orden_compra")


class WMSOrdenCompraDetalle(Base, TimestampMixin):
    __tablename__ = "wms_ordenes_compra_detalle"
    id                  = Column(Integer, primary_key=True, index=True)
    orden_id            = Column(Integer, ForeignKey("wms_ordenes_compra.id"), nullable=False)
    producto_id         = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    cantidad_solicitada = Column(Float, nullable=False)
    cantidad_recibida   = Column(Float, nullable=False, default=0)
    precio_unitario     = Column(Float, nullable=True)
    unidad_medida       = Column(String(30), nullable=True)

    orden   = relationship("WMSOrdenCompra", back_populates="detalles")
    producto = relationship("WMSProducto", back_populates="oc_detalles")


class WMSRecepcion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "wms_recepciones"
    id               = Column(Integer, primary_key=True, index=True)
    numero_recepcion = Column(String(60), nullable=False, unique=True, index=True)
    # CONTRA_OC/ASN/CIEGA/PARCIAL/CONSOLIDADA
    tipo             = Column(String(30), nullable=False, default="CONTRA_OC")
    orden_compra_id  = Column(Integer, ForeignKey("wms_ordenes_compra.id"), nullable=True)
    almacen_id       = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False)
    fecha_recepcion  = Column(Date, nullable=False)
    # BORRADOR/EN_PROCESO/COMPLETA/RECHAZADA
    estado           = Column(String(20), nullable=False, default="BORRADOR")
    operario_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    depositante_id   = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True, index=True)
    # Tiempos del muelle: llegada del vehículo, inicio y fin del descargue. Con
    # el fin de la ubicación (tarea o cierre) dan el «dock to stock».
    muelle           = Column(String(30), nullable=True)
    fecha_llegada    = Column(DateTime(timezone=True), nullable=True)
    inicio_descargue = Column(DateTime(timezone=True), nullable=True)
    fin_descargue    = Column(DateTime(timezone=True), nullable=True)
    completada_en    = Column(DateTime(timezone=True), nullable=True)
    # La factura del proveedor que la cubre: al registrarla en el ERP salda la
    # «mercancía recibida por facturar» que dejó esta recepción.
    factura_proveedor_id = Column(Integer, nullable=True, index=True)
    notas            = Column(Text, nullable=True)

    orden_compra = relationship("WMSOrdenCompra", back_populates="recepciones")
    almacen      = relationship("WMSAlmacen", back_populates="recepciones")
    detalles     = relationship("WMSRecepcionDetalle", back_populates="recepcion", cascade="all, delete-orphan")


class WMSRecepcionDetalle(Base, TimestampMixin):
    __tablename__ = "wms_recepciones_detalle"
    id                = Column(Integer, primary_key=True, index=True)
    recepcion_id      = Column(Integer, ForeignKey("wms_recepciones.id"), nullable=False)
    producto_id       = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    lote_id           = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    cantidad_esperada = Column(Float, nullable=True)
    cantidad_recibida = Column(Float, nullable=False, default=0)
    ubicacion_id      = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    contenedor_id     = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True)
    # APROBADO/RECHAZADO/CUARENTENA/INSPECCION
    estado_calidad    = Column(String(20), nullable=False, default="APROBADO")
    notas             = Column(Text, nullable=True)
    # FALTANTE / SOBRANTE / NO_SOLICITADO / DANADO / VENCIDO / PRODUCTO_EQUIVOCADO / NO_RECIBIDO / OTRO
    novedad           = Column(String(30), nullable=True)

    recepcion = relationship("WMSRecepcion", back_populates="detalles")
    producto  = relationship("WMSProducto", back_populates="recepciones_detalle")
    lote      = relationship("WMSLote", back_populates="recepciones_detalle")
    ubicacion = relationship("WMSUbicacion", back_populates="recepciones_detalle")


# ─── Inventario ────────────────────────────────────────────────────────────────

class WMSInventarioUbicacion(Base, TimestampMixin):
    __tablename__ = "wms_inventario_ubicacion"
    id                  = Column(Integer, primary_key=True, index=True)
    producto_id         = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    ubicacion_id        = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=False)
    lote_id             = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    contenedor_id       = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True, index=True)
    cantidad_disponible = Column(Float, nullable=False, default=0)
    cantidad_reservada  = Column(Float, nullable=False, default=0)
    cantidad_bloqueada  = Column(Float, nullable=False, default=0)
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    producto  = relationship("WMSProducto", back_populates="inventarios")
    ubicacion = relationship("WMSUbicacion", back_populates="inventarios")
    lote      = relationship("WMSLote", back_populates="inventarios")


# Una fila por producto, ubicación, lote y estiba. El índice usa COALESCE: un
# UNIQUE normal no ve los NULL y dejaba dos filas «sin lote» del mismo producto
# en la misma ubicación.
Index("uq_inv_clave", WMSInventarioUbicacion.producto_id, WMSInventarioUbicacion.ubicacion_id,
      func.coalesce(WMSInventarioUbicacion.lote_id, 0), func.coalesce(WMSInventarioUbicacion.contenedor_id, 0),
      unique=True)


class WMSMovimientoInventario(Base, TimestampMixin):
    __tablename__ = "wms_movimientos_inventario"
    id                   = Column(Integer, primary_key=True, index=True)
    # RECEPCION/DESPACHO/AJUSTE/TRANSFERENCIA/DEVOLUCION/CONTEO/CROSS_DOCKING
    tipo                 = Column(String(30), nullable=False)
    producto_id          = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    ubicacion_origen_id  = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    ubicacion_destino_id = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    lote_id              = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    serie_id             = Column(Integer, ForeignKey("wms_series.id"), nullable=True)
    cantidad             = Column(Float, nullable=False)
    costo_unitario       = Column(Numeric(18, 4), nullable=True)
    referencia_documento = Column(String(100), nullable=True)
    usuario_id           = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    notas                = Column(Text, nullable=True)
    # Trazabilidad completa: de qué estiba, de quién, en qué almacén, por qué
    # documento y tarea, entre qué estados (disponible/reservado/bloqueado) y
    # cómo quedaron las dos filas tocadas. Lo escribe solo `wms_inventario.mover`.
    # Estiba de la que sale (o a la que entra, si no hay origen) y estiba a la
    # que llega: armar o desarmar una estiba es un movimiento entre las dos.
    contenedor_id        = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True, index=True)
    contenedor_destino_id = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True, index=True)
    depositante_id       = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True, index=True)
    almacen_id           = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=True, index=True)
    documento_tipo       = Column(String(30), nullable=True)
    documento_id         = Column(Integer, nullable=True)
    tarea_id             = Column(Integer, ForeignKey("wms_tareas.id"), nullable=True)
    estado_origen        = Column(String(12), nullable=True)
    estado_destino       = Column(String(12), nullable=True)
    saldo_origen         = Column(Float, nullable=True)
    saldo_destino        = Column(Float, nullable=True)
    # El comprobante del ERP que contabilizó este movimiento (solo mercancía
    # propia: la de un depositante 3PL no es de la empresa y no se contabiliza).
    comprobante_id       = Column(Integer, nullable=True, index=True)

    producto          = relationship("WMSProducto", back_populates="movimientos")
    ubicacion_origen  = relationship("WMSUbicacion", foreign_keys=[ubicacion_origen_id], back_populates="movimientos_origen")
    ubicacion_destino = relationship("WMSUbicacion", foreign_keys=[ubicacion_destino_id], back_populates="movimientos_destino")
    lote              = relationship("WMSLote", back_populates="movimientos")
    serie             = relationship("WMSSerie", back_populates="movimientos")


class WMSConteoInventario(Base, TimestampMixin):
    __tablename__ = "wms_conteos_inventario"
    id              = Column(Integer, primary_key=True, index=True)
    almacen_id      = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False)
    # CICLICO/GENERAL/DIRIGIDO
    tipo            = Column(String(20), nullable=False, default="CICLICO")
    # PROGRAMADO/EN_PROCESO/COMPLETO/CANCELADO
    estado          = Column(String(20), nullable=False, default="PROGRAMADO")
    fecha_programada = Column(Date, nullable=False)
    fecha_inicio    = Column(DateTime(timezone=True), nullable=True)
    fecha_fin       = Column(DateTime(timezone=True), nullable=True)
    operario_id     = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    notas           = Column(Text, nullable=True)

    almacen  = relationship("WMSAlmacen", back_populates="conteos")
    detalles = relationship("WMSConteoDetalle", back_populates="conteo", cascade="all, delete-orphan")


class WMSConteoDetalle(Base, TimestampMixin):
    __tablename__ = "wms_conteos_detalle"
    id               = Column(Integer, primary_key=True, index=True)
    conteo_id        = Column(Integer, ForeignKey("wms_conteos_inventario.id"), nullable=False)
    producto_id      = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    ubicacion_id     = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=False)
    lote_id          = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    contenedor_id    = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True)
    cantidad_sistema = Column(Float, nullable=False, default=0)
    cantidad_fisica  = Column(Float, nullable=True)
    diferencia       = Column(Float, nullable=True)   # computed: fisica - sistema
    ajustado         = Column(Boolean, default=False)

    conteo   = relationship("WMSConteoInventario", back_populates="detalles")
    producto  = relationship("WMSProducto", back_populates="conteos_detalle")
    ubicacion = relationship("WMSUbicacion", back_populates="conteos_detalle")
    lote      = relationship("WMSLote", back_populates="conteos_detalle")


# ─── Outbound ──────────────────────────────────────────────────────────────────

class WMSOrdenSalida(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "wms_ordenes_salida"
    id             = Column(Integer, primary_key=True, index=True)
    numero_orden   = Column(String(60), nullable=False, unique=True, index=True)
    cliente_id     = Column(Integer, ForeignKey("wms_clientes.id"), nullable=False)
    almacen_id     = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False)
    depositante_id = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True, index=True)
    fecha_emision  = Column(Date, nullable=False)
    fecha_requerida = Column(Date, nullable=True)
    # PENDIENTE/EN_PICKING/EMPACANDO/DESPACHADO/ENTREGADO/CANCELADO
    estado         = Column(String(20), nullable=False, default="PENDIENTE")
    # BAJA/NORMAL/ALTA/URGENTE
    prioridad      = Column(String(20), nullable=False, default="NORMAL")
    # ECOMMERCE/B2B/RETAIL/TRANSFERENCIA
    canal          = Column(String(30), nullable=True)

    cliente   = relationship("WMSCliente", back_populates="ordenes_salida")
    almacen   = relationship("WMSAlmacen", back_populates="ordenes_salida")
    detalles  = relationship("WMSOrdenSalidaDetalle", back_populates="orden", cascade="all, delete-orphan")
    tareas_picking = relationship("WMSPickingTarea", back_populates="orden")
    despachos = relationship("WMSDespacho", back_populates="orden")
    devoluciones = relationship("WMSDevolucion", back_populates="orden_referencia")


class WMSOrdenSalidaDetalle(Base, TimestampMixin):
    __tablename__ = "wms_ordenes_salida_detalle"
    id                  = Column(Integer, primary_key=True, index=True)
    orden_id            = Column(Integer, ForeignKey("wms_ordenes_salida.id"), nullable=False)
    producto_id         = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    lote_id             = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    cantidad_solicitada = Column(Float, nullable=False)
    cantidad_preparada  = Column(Float, nullable=False, default=0)
    cantidad_despachada = Column(Float, nullable=False, default=0)
    precio_unitario     = Column(Float, nullable=True)
    # PENDIENTE/PARCIAL/COMPLETO
    estado              = Column(String(20), nullable=False, default="PENDIENTE")

    orden   = relationship("WMSOrdenSalida", back_populates="detalles")
    producto = relationship("WMSProducto", back_populates="salida_detalles")
    lote     = relationship("WMSLote", back_populates="salida_detalles")


class WMSPickingTarea(Base, TimestampMixin):
    __tablename__ = "wms_picking_tareas"
    id                   = Column(Integer, primary_key=True, index=True)
    orden_id             = Column(Integer, ForeignKey("wms_ordenes_salida.id"), nullable=False)
    ola_id               = Column(Integer, ForeignKey("wms_olas.id"), nullable=True, index=True)
    operario_id          = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    # SINGLE/BATCH/ZONE/CLUSTER/WAVE
    tipo                 = Column(String(20), nullable=False, default="SINGLE")
    # PENDIENTE/EN_PROGRESO/COMPLETADA/CANCELADA
    estado               = Column(String(20), nullable=False, default="PENDIENTE")
    fecha_asignacion     = Column(DateTime(timezone=True), nullable=True)
    fecha_inicio         = Column(DateTime(timezone=True), nullable=True)
    fecha_fin            = Column(DateTime(timezone=True), nullable=True)
    ubicaciones_visitadas = Column(Integer, nullable=False, default=0)
    items_pickeados      = Column(Integer, nullable=False, default=0)

    orden   = relationship("WMSOrdenSalida", back_populates="tareas_picking")
    detalles = relationship("WMSPickingDetalle", back_populates="tarea", cascade="all, delete-orphan")


class WMSPickingDetalle(Base, TimestampMixin):
    __tablename__ = "wms_picking_detalles"
    id                    = Column(Integer, primary_key=True, index=True)
    tarea_id              = Column(Integer, ForeignKey("wms_picking_tareas.id"), nullable=False)
    producto_id           = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    ubicacion_id          = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=False)
    lote_id               = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    cantidad_solicitada   = Column(Float, nullable=False)
    cantidad_pickeada     = Column(Float, nullable=False, default=0)
    # Lo que de este alistamiento ya salió en un despacho: el despacho consume
    # exactamente lo que se reservó y alistó para su orden, no lo de otra.
    cantidad_despachada   = Column(Float, nullable=False, default=0, server_default="0")
    contenedor_id         = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True)
    # De dónde se sacó. Al confirmar, la mercancía pasa al staging de salida y
    # `ubicacion_id` queda apuntando allá (es de donde la saca el despacho).
    ubicacion_alistada_id = Column(Integer, nullable=True)  # sin FK: la relación «ubicacion» usa ubicacion_id
    confirmado            = Column(Boolean, default=False)
    timestamp_confirmacion = Column(DateTime(timezone=True), nullable=True)

    tarea    = relationship("WMSPickingTarea", back_populates="detalles")
    producto  = relationship("WMSProducto", back_populates="picking_detalles")
    ubicacion = relationship("WMSUbicacion", back_populates="picking_detalles")
    lote      = relationship("WMSLote", back_populates="picking_detalles")


class WMSDespacho(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "wms_despachos"
    id                    = Column(Integer, primary_key=True, index=True)
    numero_despacho       = Column(String(60), nullable=False, unique=True, index=True)
    orden_id              = Column(Integer, ForeignKey("wms_ordenes_salida.id"), nullable=False)
    transportadora_id     = Column(Integer, ForeignKey("wms_transportadoras.id"), nullable=True)
    vehiculo_placa        = Column(String(20), nullable=True)
    conductor_nombre      = Column(String(150), nullable=True)
    fecha_despacho        = Column(Date, nullable=False)
    fecha_entrega_estimada = Column(Date, nullable=True)
    fecha_entrega_real    = Column(Date, nullable=True)
    # PREPARANDO/LISTO/EN_TRANSITO/ENTREGADO/INCIDENCIA
    estado                = Column(String(20), nullable=False, default="PREPARANDO")
    peso_total_kg         = Column(Float, nullable=True)
    volumen_total_m3      = Column(Float, nullable=True)
    muelle                = Column(String(30), nullable=True)
    inicio_cargue         = Column(DateTime(timezone=True), nullable=True)
    fin_cargue            = Column(DateTime(timezone=True), nullable=True)
    # Factura de venta del ERP. Vacía cuando no se pudo facturar al despachar
    # (orden sin precios, sin resolución vigente): `aviso_factura` dice por qué.
    factura_id            = Column(Integer, nullable=True, index=True)
    aviso_factura         = Column(String(300), nullable=True)
    notas                 = Column(Text, nullable=True)

    orden          = relationship("WMSOrdenSalida", back_populates="despachos")
    transportadora = relationship("WMSTransportadora", back_populates="despachos")
    detalles       = relationship("WMSDespachoDetalle", back_populates="despacho", cascade="all, delete-orphan")


class WMSDespachoDetalle(Base, TimestampMixin):
    __tablename__ = "wms_despachos_detalle"
    id               = Column(Integer, primary_key=True, index=True)
    despacho_id      = Column(Integer, ForeignKey("wms_despachos.id"), nullable=False)
    producto_id      = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    lote_id          = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    cantidad         = Column(Float, nullable=False)
    numero_tracking  = Column(String(100), nullable=True)
    contenedor_id    = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True)

    despacho = relationship("WMSDespacho", back_populates="detalles")
    producto  = relationship("WMSProducto", back_populates="despacho_detalles")
    lote      = relationship("WMSLote", back_populates="despacho_detalles")


# ─── Historial de estado WMS ───────────────────────────────────────────────────

class WMSHistorialEstado(Base):
    """Registro inmutable de cada cambio de estado en entidades WMS (Despacho, OrdenSalida)."""
    __tablename__ = "wms_historial_estado"

    id              = Column(Integer, primary_key=True, index=True)
    # DESPACHO / ORDEN_SALIDA
    entidad_tipo    = Column(String(30), nullable=False, index=True)
    entidad_id      = Column(Integer, nullable=False, index=True)
    estado_anterior = Column(String(30), nullable=True)
    estado_nuevo    = Column(String(30), nullable=False)
    # AVANCE / CORRECCION
    tipo_cambio     = Column(String(20), nullable=False, default="AVANCE")
    observacion     = Column(Text, nullable=True)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha           = Column(DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(_tz.utc))

    usuario = relationship("Usuario")


# ─── Devoluciones ──────────────────────────────────────────────────────────────

class WMSDevolucion(Base, TimestampMixin):
    __tablename__ = "wms_devoluciones"
    id                 = Column(Integer, primary_key=True, index=True)
    numero_devolucion  = Column(String(60), nullable=False, unique=True, index=True)
    # CLIENTE/PROVEEDOR
    tipo               = Column(String(20), nullable=False)
    orden_referencia_id = Column(Integer, ForeignKey("wms_ordenes_salida.id"), nullable=True)
    cliente_id         = Column(Integer, ForeignKey("wms_clientes.id"), nullable=True)
    proveedor_id       = Column(Integer, ForeignKey("wms_proveedores.id"), nullable=True)
    almacen_id         = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False)
    fecha_recepcion    = Column(Date, nullable=False)
    # RECIBIDA/INSPECCION/APROBADA/RECHAZADA/REINGRESADA
    estado             = Column(String(20), nullable=False, default="RECIBIDA")
    motivo             = Column(String(255), nullable=True)
    nota_credito_id    = Column(Integer, nullable=True)
    notas              = Column(Text, nullable=True)

    orden_referencia = relationship("WMSOrdenSalida", back_populates="devoluciones")
    cliente          = relationship("WMSCliente", back_populates="devoluciones")
    proveedor        = relationship("WMSProveedor", back_populates="devoluciones")
    almacen          = relationship("WMSAlmacen", back_populates="devoluciones")
    detalles         = relationship("WMSDevolucionDetalle", back_populates="devolucion", cascade="all, delete-orphan")


class WMSDevolucionDetalle(Base, TimestampMixin):
    __tablename__ = "wms_devoluciones_detalle"
    id             = Column(Integer, primary_key=True, index=True)
    devolucion_id  = Column(Integer, ForeignKey("wms_devoluciones.id"), nullable=False)
    producto_id    = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    lote_id        = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    cantidad       = Column(Float, nullable=False)
    # BUENO/DANO_MENOR/DANO_MAYOR/DESTRUIR
    estado_calidad = Column(String(20), nullable=False, default="BUENO")
    # REINGRESAR/CUARENTENA/DESTRUIR/DEVOLVER_PROVEEDOR
    accion         = Column(String(30), nullable=False, default="REINGRESAR")
    reingresado    = Column(Boolean, default=False)

    devolucion = relationship("WMSDevolucion", back_populates="detalles")
    producto   = relationship("WMSProducto", back_populates="devolucion_detalles")
    lote       = relationship("WMSLote", back_populates="devolucion_detalles")


# ─── Trazabilidad ──────────────────────────────────────────────────────────────

class WMSEventoTrazabilidad(Base, TimestampMixin):
    __tablename__ = "wms_eventos_trazabilidad"
    id               = Column(Integer, primary_key=True, index=True)
    tipo_evento      = Column(String(60), nullable=False)
    entidad_tipo     = Column(String(60), nullable=True)
    entidad_id       = Column(Integer, nullable=True)
    descripcion      = Column(Text, nullable=True)
    datos_adicionales = Column(JSON, nullable=True)
    usuario_id       = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    ubicacion_id     = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    producto_id      = Column(Integer, ForeignKey("wms_productos.id"), nullable=True)
    lote_id          = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)

    ubicacion = relationship("WMSUbicacion", back_populates="eventos_trazabilidad")
    producto  = relationship("WMSProducto", back_populates="eventos_trazabilidad")
    lote      = relationship("WMSLote", back_populates="eventos_trazabilidad")


# ─── KPI Diario ────────────────────────────────────────────────────────────────

class WMSKPIDiario(Base, TimestampMixin):
    __tablename__ = "wms_kpi_diario"
    id                     = Column(Integer, primary_key=True, index=True)
    fecha                  = Column(Date, nullable=False, unique=True, index=True)
    almacen_id             = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=True)
    ordenes_total          = Column(Integer, nullable=False, default=0)
    ordenes_on_time        = Column(Integer, nullable=False, default=0)
    ordenes_in_full        = Column(Integer, nullable=False, default=0)
    ordenes_otif           = Column(Integer, nullable=False, default=0)
    ordenes_perfect        = Column(Integer, nullable=False, default=0)
    fill_rate              = Column(Float, nullable=True)
    inventory_accuracy     = Column(Float, nullable=True)
    cost_per_order         = Column(Float, nullable=True)
    dock_to_stock_minutes  = Column(Float, nullable=True)
    picking_accuracy       = Column(Float, nullable=True)
    shipping_accuracy      = Column(Float, nullable=True)

    almacen = relationship("WMSAlmacen", back_populates="kpis_diarios")


# ─── Operación 3PL: depositantes ───────────────────────────────────────────────

class WMSDepositante(Base, TimestampMixin):
    """Dueño de la mercancía almacenada. La empresa misma es un depositante más
    (marcado `propio`), así todo el inventario tiene dueño y los reportes,
    indicadores y la facturación de almacenamiento se cortan igual."""
    __tablename__ = "wms_depositantes"
    id        = Column(Integer, primary_key=True, index=True)
    codigo    = Column(String(30), nullable=False, unique=True, index=True)
    nombre    = Column(String(150), nullable=False)
    nit       = Column(String(30), nullable=True)
    contacto  = Column(String(100), nullable=True)
    email     = Column(String(120), nullable=True)
    telefono  = Column(String(30), nullable=True)
    propio    = Column(Boolean, nullable=False, default=False)
    # Tercero del ERP al que se le factura el servicio logístico.
    tercero_id = Column(Integer, ForeignKey("erp_terceros.id"), nullable=True)
    notas     = Column(Text, nullable=True)
    activo    = Column(Boolean, default=True)


# ─── Estibas / contenedores (LPN) ──────────────────────────────────────────────

class WMSContenedor(Base, TimestampMixin):
    """Unidad de manejo con etiqueta propia (License Plate Number): estiba,
    caja, canasta. Lo que tiene adentro son filas de existencia con su
    `contenedor_id`; moverla mueve todo su contenido de una sola vez."""
    __tablename__ = "wms_contenedores"
    id             = Column(Integer, primary_key=True, index=True)
    codigo         = Column(String(30), nullable=False, unique=True, index=True)
    # ESTIBA/CAJA/CANASTA/CONTENEDOR
    tipo           = Column(String(20), nullable=False, default="ESTIBA")
    # ABIERTO (se le puede agregar) / CERRADO / DESPACHADO / VACIO / ANULADO
    estado         = Column(String(15), nullable=False, default="ABIERTO")
    almacen_id     = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    ubicacion_id   = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True, index=True)
    depositante_id = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True, index=True)
    padre_id       = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True)
    documento_tipo = Column(String(30), nullable=True)
    documento_id   = Column(Integer, nullable=True)
    largo_cm       = Column(Float, nullable=True)
    ancho_cm       = Column(Float, nullable=True)
    alto_cm        = Column(Float, nullable=True)
    peso_kg        = Column(Float, nullable=True)
    creado_por_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    notas          = Column(Text, nullable=True)


# ─── Tareas de bodega ──────────────────────────────────────────────────────────

class WMSTarea(Base, TimestampMixin):
    """Un movimiento que alguien tiene que hacer: ubicar lo recibido, reabastecer
    el frente de picking, mover una estiba. Cada una guarda cuándo se creó, se
    asignó, empezó y terminó, quién la hizo, a dónde se sugirió llevar y a dónde
    se llevó de verdad. Es la base de los indicadores de productividad."""
    __tablename__ = "wms_tareas"
    id                    = Column(Integer, primary_key=True, index=True)
    # UBICACION / REABASTECIMIENTO / MOVIMIENTO
    tipo                  = Column(String(20), nullable=False, index=True)
    # PENDIENTE / EN_CURSO / COMPLETADA / CANCELADA
    estado                = Column(String(12), nullable=False, default="PENDIENTE", index=True)
    prioridad             = Column(Integer, nullable=False, default=5)
    almacen_id            = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    depositante_id        = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True)
    producto_id           = Column(Integer, ForeignKey("wms_productos.id"), nullable=True)
    lote_id               = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    contenedor_id         = Column(Integer, ForeignKey("wms_contenedores.id"), nullable=True)
    cantidad              = Column(Float, nullable=True)
    ubicacion_origen_id   = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    ubicacion_sugerida_id = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    ubicacion_destino_id  = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    # Por qué la estiba no fue a donde se sugirió (dato para mejorar el slotting).
    motivo_desvio         = Column(String(200), nullable=True)
    razon_sugerencia      = Column(String(200), nullable=True)
    documento_tipo        = Column(String(30), nullable=True)
    documento_id          = Column(Integer, nullable=True)
    operario_id           = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    asignada_en           = Column(DateTime(timezone=True), nullable=True)
    iniciada_en           = Column(DateTime(timezone=True), nullable=True)
    terminada_en          = Column(DateTime(timezone=True), nullable=True)
    notas                 = Column(Text, nullable=True)


# ─── Cubicaje ──────────────────────────────────────────────────────────────────

class WMSProductoEmpaque(Base, TimestampMixin):
    """Un nivel de empaque del producto: la unidad, la caja, la caja máster, la
    estiba. Cada nivel tiene sus medidas, su peso, cuántas unidades base lleva y
    su propio código de barras. Es lo que permite cubicar, armar estibas y
    elegir la caja de despacho."""
    __tablename__ = "wms_producto_empaques"
    __table_args__ = (UniqueConstraint("producto_id", "nivel", name="uq_empaque_nivel"),)
    id             = Column(Integer, primary_key=True, index=True)
    producto_id    = Column(Integer, ForeignKey("wms_productos.id"), nullable=False, index=True)
    # UNIDAD / CAJA / MASTER / ESTIBA
    nivel          = Column(String(10), nullable=False)
    unidades       = Column(Float, nullable=False, default=1)
    largo_cm       = Column(Float, nullable=True)
    ancho_cm       = Column(Float, nullable=True)
    alto_cm        = Column(Float, nullable=True)
    peso_kg        = Column(Float, nullable=True)
    codigo_barras  = Column(String(60), nullable=True, index=True)
    # Solo ESTIBA: cajas por cama (Ti) y camas (Hi).
    cajas_por_cama = Column(Integer, nullable=True)
    camas          = Column(Integer, nullable=True)
    apilable       = Column(Boolean, nullable=False, default=True)
    max_apilado    = Column(Integer, nullable=True)
    # MANUAL / CUBICADOR
    fuente         = Column(String(10), nullable=False, default="MANUAL")
    medicion_id    = Column(Integer, ForeignKey("wms_mediciones.id"), nullable=True)
    medido_en      = Column(DateTime(timezone=True), nullable=True)
    medido_por_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)


class WMSCubicador(Base, TimestampMixin):
    """Estación de cubicaje: un ESP32 con tres láseres (largo, ancho, alto) y
    una celda de carga. Manda lecturas crudas; el servidor aplica la
    calibración. Se autentica con su propio token, que se puede revocar."""
    __tablename__ = "wms_cubicadores"
    id               = Column(Integer, primary_key=True, index=True)
    codigo           = Column(String(30), nullable=False, unique=True)
    nombre           = Column(String(120), nullable=False)
    almacen_id       = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=True)
    activo           = Column(Boolean, nullable=False, default=True)
    # Huella del token vigente (se guarda la huella, nunca el token).
    token_huella     = Column(String(64), nullable=True)
    token_emitido_en = Column(DateTime(timezone=True), nullable=True)
    ultima_conexion  = Column(DateTime(timezone=True), nullable=True)
    firmware         = Column(String(30), nullable=True)
    # Calibración por eje: medida = escala × (base − lectura). La base es la
    # distancia del láser a la pared de referencia opuesta, en mm.
    base_x_mm        = Column(Float, nullable=True)
    base_y_mm        = Column(Float, nullable=True)
    base_z_mm        = Column(Float, nullable=True)
    escala_x         = Column(Float, nullable=False, default=1.0)
    escala_y         = Column(Float, nullable=False, default=1.0)
    escala_z         = Column(Float, nullable=False, default=1.0)
    # Celda de carga: gramos = (crudo − tara) × escala.
    tara_crudo       = Column(Float, nullable=True)
    escala_peso      = Column(Float, nullable=True)
    # Muestras de calibración con bloques de medida conocida.
    calibracion      = Column(JSON, nullable=True)
    tolerancia_mm    = Column(Float, nullable=False, default=2.0)
    notas            = Column(Text, nullable=True)


class WMSMedicion(Base, TimestampMixin):
    """Una medición del cubicador: las lecturas crudas, las medidas que
    resultan y qué tan estables fueron. Queda pendiente hasta que alguien la
    asigna a un producto y nivel de empaque (o la usa para calibrar)."""
    __tablename__ = "wms_mediciones"
    id             = Column(Integer, primary_key=True, index=True)
    cubicador_id   = Column(Integer, ForeignKey("wms_cubicadores.id"), nullable=False, index=True)
    lecturas       = Column(JSON, nullable=False)
    largo_cm       = Column(Float, nullable=True)
    ancho_cm       = Column(Float, nullable=True)
    alto_cm        = Column(Float, nullable=True)
    peso_kg        = Column(Float, nullable=True)
    dispersion_mm  = Column(Float, nullable=True)
    estable        = Column(Boolean, nullable=False, default=True)
    # PENDIENTE / ASIGNADA / DESCARTADA / CALIBRACION
    estado         = Column(String(12), nullable=False, default="PENDIENTE", index=True)
    producto_id    = Column(Integer, ForeignKey("wms_productos.id"), nullable=True)
    nivel          = Column(String(10), nullable=True)
    asignada_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    asignada_en    = Column(DateTime(timezone=True), nullable=True)


class WMSKPIMeta(Base, TimestampMixin):
    """Meta de un indicador, general (almacen_id vacío) o de un almacén."""
    __tablename__ = "wms_kpi_metas"
    id         = Column(Integer, primary_key=True, index=True)
    clave      = Column(String(40), nullable=False, index=True)
    almacen_id = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=True)
    meta       = Column(Float, nullable=False)
    fijada_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)


Index("uq_kpi_meta", WMSKPIMeta.clave, func.coalesce(WMSKPIMeta.almacen_id, 0), unique=True)


class WMSOla(Base, TimestampMixin):
    """Ola de alistamiento: varias órdenes que se alistan juntas en un solo
    recorrido. Cada orden conserva su tarea; la ola agrupa y ordena las paradas."""
    __tablename__ = "wms_olas"
    id            = Column(Integer, primary_key=True, index=True)
    codigo        = Column(String(40), nullable=False, unique=True)
    almacen_id    = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    # ABIERTA / EN_CURSO / COMPLETADA / CANCELADA
    estado        = Column(String(12), nullable=False, default="ABIERTA")
    criterio      = Column(String(200), nullable=True)
    creada_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    completada_en = Column(DateTime(timezone=True), nullable=True)


class WMSCajaEmpaque(Base, TimestampMixin):
    """Caja de despacho del catálogo: medidas internas, peso máximo, tara y costo."""
    __tablename__ = "wms_cajas_empaque"
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String(30), nullable=False, unique=True)
    nombre      = Column(String(120), nullable=False)
    largo_cm    = Column(Float, nullable=False)
    ancho_cm    = Column(Float, nullable=False)
    alto_cm     = Column(Float, nullable=False)
    peso_max_kg = Column(Float, nullable=False, default=25)
    tara_kg     = Column(Float, nullable=False, default=0)
    costo       = Column(Float, nullable=True)
    activo      = Column(Boolean, nullable=False, default=True)


class WMSEmpaqueOrden(Base, TimestampMixin):
    """Un bulto de una orden: en qué caja va y qué lleva. Sus pesos y volúmenes
    alimentan el despacho y la etiqueta del bulto."""
    __tablename__ = "wms_empaques_orden"
    id           = Column(Integer, primary_key=True, index=True)
    orden_id     = Column(Integer, ForeignKey("wms_ordenes_salida.id"), nullable=False, index=True)
    numero       = Column(Integer, nullable=False)
    caja_id      = Column(Integer, ForeignKey("wms_cajas_empaque.id"), nullable=True)
    largo_cm     = Column(Float, nullable=True)
    ancho_cm     = Column(Float, nullable=True)
    alto_cm      = Column(Float, nullable=True)
    peso_kg      = Column(Float, nullable=True)
    contenido    = Column(JSON, nullable=False)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)


# ─── Maquila (servicios de valor agregado) ─────────────────────────────────────

class WMSMaquilaReceta(Base, TimestampMixin):
    """Cómo se arma (o desarma) un producto: sus componentes por unidad, el
    tiempo estándar y el costo de mano de obra por unidad."""
    __tablename__ = "wms_maquila_recetas"
    id                    = Column(Integer, primary_key=True, index=True)
    codigo                = Column(String(30), nullable=False, unique=True)
    nombre                = Column(String(150), nullable=False)
    # KIT / REEMPAQUE / ETIQUETADO / DESARME
    tipo                  = Column(String(12), nullable=False, default="KIT")
    producto_resultado_id = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    minutos_por_unidad    = Column(Float, nullable=False, default=0)
    costo_mano_obra_unidad = Column(Float, nullable=False, default=0)
    instrucciones         = Column(Text, nullable=True)
    activo                = Column(Boolean, nullable=False, default=True)


class WMSMaquilaComponente(Base, TimestampMixin):
    __tablename__ = "wms_maquila_componentes"
    __table_args__ = (UniqueConstraint("receta_id", "producto_id", name="uq_maquila_componente"),)
    id          = Column(Integer, primary_key=True, index=True)
    receta_id   = Column(Integer, ForeignKey("wms_maquila_recetas.id", ondelete="CASCADE"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    cantidad    = Column(Float, nullable=False)


class WMSMaquilaOrden(Base, TimestampMixin):
    """Una corrida de maquila. Al iniciar reserva lo que va a consumir; al
    terminar consume lo usado, libera lo que sobró y produce el resultado con
    su costo (componentes + mano de obra)."""
    __tablename__ = "wms_maquila_ordenes"
    id                   = Column(Integer, primary_key=True, index=True)
    numero               = Column(String(40), nullable=False, unique=True)
    receta_id            = Column(Integer, ForeignKey("wms_maquila_recetas.id"), nullable=False)
    almacen_id           = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    depositante_id       = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True)
    cantidad_plan        = Column(Float, nullable=False)
    cantidad_hecha       = Column(Float, nullable=True)
    # PLANEADA / EN_PROCESO / TERMINADA / CANCELADA
    estado               = Column(String(12), nullable=False, default="PLANEADA", index=True)
    reservas             = Column(JSON, nullable=True)
    ubicacion_destino_id = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    costo_unitario       = Column(Float, nullable=True)
    minutos_reales       = Column(Float, nullable=True)
    operario_id          = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    iniciada_en          = Column(DateTime(timezone=True), nullable=True)
    terminada_en         = Column(DateTime(timezone=True), nullable=True)
    notas                = Column(Text, nullable=True)


# ─── Mapa visual: fotos de las estanterías y plano ─────────────────────────────

class WMSMapaFoto(Base, TimestampMixin):
    """Foto frontal de una estantería, guardada en blanco y negro. Las cuatro
    esquinas (normalizadas 0-1) y las filas × columnas definen la cuadrícula
    de celdas sobre la foto; cada celda es una ubicación."""
    __tablename__ = "wms_mapa_fotos"
    id          = Column(Integer, primary_key=True, index=True)
    almacen_id  = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    nombre      = Column(String(150), nullable=False)
    archivo     = Column(String(300), nullable=False)
    ancho       = Column(Integer, nullable=False)
    alto        = Column(Integer, nullable=False)
    # [[x, y] arriba-izquierda, arriba-derecha, abajo-derecha, abajo-izquierda]
    esquinas    = Column(JSON, nullable=True)
    filas       = Column(Integer, nullable=True)
    columnas    = Column(Integer, nullable=True)
    pasillo     = Column(String(20), nullable=True)
    estanteria  = Column(String(20), nullable=True)
    notas       = Column(Text, nullable=True)


class WMSMapaCelda(Base, TimestampMixin):
    __tablename__ = "wms_mapa_celdas"
    __table_args__ = (UniqueConstraint("foto_id", "fila", "columna", name="uq_mapa_celda"),)
    id           = Column(Integer, primary_key=True, index=True)
    foto_id      = Column(Integer, ForeignKey("wms_mapa_fotos.id", ondelete="CASCADE"), nullable=False, index=True)
    fila         = Column(Integer, nullable=False)       # 0 = la de arriba
    columna      = Column(Integer, nullable=False)       # 0 = la de la izquierda
    ubicacion_id = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)


class WMSPlano(Base, TimestampMixin):
    """Plano (o foto cenital) de la bodega, con las estanterías marcadas."""
    __tablename__ = "wms_planos"
    id         = Column(Integer, primary_key=True, index=True)
    almacen_id = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, unique=True)
    archivo    = Column(String(300), nullable=False)
    ancho      = Column(Integer, nullable=False)
    alto       = Column(Integer, nullable=False)
    # [{"x","y","w","h" (0-1), "etiqueta", "foto_id"}]
    marcas     = Column(JSON, nullable=True)


# ─── Constructor de bodega (layout en metros) ──────────────────────────────────

class WMSLayout(Base, TimestampMixin):
    """Configuración del layout de un almacén: tamaño del piso, escala del
    plano de fondo y cómo se codifican las ubicaciones que genera."""
    __tablename__ = "wms_layouts"
    id             = Column(Integer, primary_key=True, index=True)
    almacen_id     = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, unique=True)
    ancho_m        = Column(Float, nullable=False, default=40)
    largo_m        = Column(Float, nullable=False, default=30)
    # Metros por píxel del plano de fondo y dónde queda su esquina superior izquierda.
    escala_m_px    = Column(Float, nullable=True)
    plano_x_m      = Column(Float, nullable=False, default=0)
    plano_y_m      = Column(Float, nullable=False, default=0)
    # Tokens: {almacen} {zona} {pasillo} {estanteria} {posicion} {nivel} (admite formato: {nivel:02d})
    patron_codigo  = Column(String(80), nullable=False, default="{pasillo}-{estanteria}-{posicion}-{nivel}")


class WMSLayoutElemento(Base, TimestampMixin):
    """Una estructura del layout: estantería (selectiva, góndola, cantiléver),
    almacenamiento en piso, o un área / muro / columna. (x, y) es el centro en
    metros desde la esquina superior izquierda del piso; la rotación, en grados
    en sentido horario. El largo de una estantería sale de módulos × frente."""
    __tablename__ = "wms_layout_elementos"
    id            = Column(Integer, primary_key=True, index=True)
    almacen_id    = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    # SELECTIVO / GONDOLA / CANTILEVER / PISO / ZONA / MURO / COLUMNA
    tipo          = Column(String(20), nullable=False)
    nombre        = Column(String(60), nullable=True)
    pasillo       = Column(String(20), nullable=True)
    estanteria    = Column(String(20), nullable=True)
    zona_id       = Column(Integer, ForeignKey("wms_zonas.id"), nullable=True)
    # Área ligada a una ubicación existente (p. ej. la de recepción), para ver su ocupación.
    ubicacion_id  = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    foto_id       = Column(Integer, ForeignKey("wms_mapa_fotos.id", ondelete="SET NULL"), nullable=True)
    categoria     = Column(String(30), nullable=True)        # tipo de área: RECEPCION, DESPACHO…
    color         = Column(String(9), nullable=True)
    x_m           = Column(Float, nullable=False, default=0)
    y_m           = Column(Float, nullable=False, default=0)
    rotacion      = Column(Float, nullable=False, default=0)
    modulos       = Column(Integer, nullable=False, default=1)
    por_modulo    = Column(Integer, nullable=False, default=1)  # posiciones por módulo (vano)
    niveles       = Column(Integer, nullable=False, default=1)
    frente_cm     = Column(Float, nullable=False, default=270)  # ancho de un módulo
    fondo_cm      = Column(Float, nullable=False, default=100)
    alto_nivel_cm = Column(Float, nullable=False, default=150)
    capacidad_kg  = Column(Float, nullable=True)                # por posición
    largo_m       = Column(Float, nullable=True)                # áreas, muros y columnas
    ancho_m       = Column(Float, nullable=True)
    orden         = Column(Integer, nullable=False, default=0)


class WMSLayoutPosicion(Base, TimestampMixin):
    """Qué ubicación del WMS es cada posición (nivel, posición) de una estructura."""
    __tablename__ = "wms_layout_posiciones"
    __table_args__ = (UniqueConstraint("elemento_id", "nivel", "posicion", name="uq_layout_posicion"),)
    id           = Column(Integer, primary_key=True, index=True)
    elemento_id  = Column(Integer, ForeignKey("wms_layout_elementos.id", ondelete="CASCADE"), nullable=False, index=True)
    nivel        = Column(Integer, nullable=False)
    posicion     = Column(Integer, nullable=False)
    ubicacion_id = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=False, index=True)


# ─── Facturación del servicio 3PL ──────────────────────────────────────────────

class WMSTarifa3PL(Base, TimestampMixin):
    """Lo que se cobra por concepto. Sin depositante es la tarifa general; la
    del depositante, si existe, la reemplaza."""
    __tablename__ = "wms_tarifas_3pl"
    id             = Column(Integer, primary_key=True, index=True)
    depositante_id = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=True, index=True)
    # ALM_M3_DIA / ALM_POSICION_DIA / ALM_ESTIBA_DIA / REC_UNIDAD / REC_DOCUMENTO /
    # DESP_UNIDAD / DESP_LINEA / DESP_ORDEN / MINIMO_MES
    concepto       = Column(String(20), nullable=False)
    valor          = Column(Float, nullable=False)
    iva_pct        = Column(Float, nullable=False, default=19)
    activo         = Column(Boolean, nullable=False, default=True)


Index("uq_tarifa_3pl", WMSTarifa3PL.concepto, func.coalesce(WMSTarifa3PL.depositante_id, 0), unique=True)


class WMSLiquidacion3PL(Base, TimestampMixin):
    """El cobro de un periodo a un depositante: almacenamiento día a día (del
    kárdex), movimientos y maquila, a sus tarifas. Al facturarla se vuelve una
    factura de venta del ERP."""
    __tablename__ = "wms_liquidaciones_3pl"
    id             = Column(Integer, primary_key=True, index=True)
    numero         = Column(String(40), nullable=False, unique=True)
    depositante_id = Column(Integer, ForeignKey("wms_depositantes.id"), nullable=False, index=True)
    desde          = Column(Date, nullable=False)
    hasta          = Column(Date, nullable=False)
    # BORRADOR / FACTURADA / ANULADA
    estado         = Column(String(10), nullable=False, default="BORRADOR")
    lineas         = Column(JSON, nullable=False)
    diario         = Column(JSON, nullable=True)
    subtotal       = Column(Float, nullable=False, default=0)
    iva            = Column(Float, nullable=False, default=0)
    total          = Column(Float, nullable=False, default=0)
    factura_id     = Column(Integer, ForeignKey("erp_facturas_cliente.id"), nullable=True)
    creada_por_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    facturada_en   = Column(DateTime(timezone=True), nullable=True)


class WMSDepositanteUsuario(Base, TimestampMixin):
    """Usuario del portal: una persona del cliente que solo ve la mercancía de
    su depositante. Al entrar, su token lleva el depositante firmado y la API
    no le abre nada más."""
    __tablename__ = "wms_depositante_usuarios"
    id             = Column(Integer, primary_key=True, index=True)
    usuario_id     = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, unique=True)
    depositante_id = Column(Integer, ForeignKey("wms_depositantes.id", ondelete="CASCADE"), nullable=False, index=True)


class WMSTraslado(Base, TimestampMixin):
    """Traslado entre almacenes. La mercancía sale del origen hacia la
    ubicación de TRÁNSITO del destino y queda ahí, sin poderse vender ni alistar,
    hasta que el destino la recibe: así el inventario no aparece en Medellín
    mientras el camión todavía va por la vía."""
    __tablename__ = "wms_traslados"
    id                    = Column(Integer, primary_key=True, index=True)
    numero                = Column(String(40), nullable=False, unique=True)
    almacen_origen_id     = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    almacen_destino_id    = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    ubicacion_transito_id = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=False)
    # EN_TRANSITO / RECIBIDO
    estado                = Column(String(12), nullable=False, default="EN_TRANSITO")
    tms_viaje_id          = Column(Integer, nullable=True)
    tms_codigo            = Column(String(40), nullable=True)
    despachado_en         = Column(DateTime(timezone=True), nullable=True)
    recibido_en           = Column(DateTime(timezone=True), nullable=True)
    usuario_id            = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    recibido_por_id       = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    notas                 = Column(Text, nullable=True)

    detalles = relationship("WMSTrasladoDetalle", back_populates="traslado", cascade="all, delete-orphan",
                            order_by="WMSTrasladoDetalle.id")


class WMSTrasladoDetalle(Base, TimestampMixin):
    __tablename__ = "wms_traslados_detalle"
    id                   = Column(Integer, primary_key=True, index=True)
    traslado_id          = Column(Integer, ForeignKey("wms_traslados.id", ondelete="CASCADE"), nullable=False, index=True)
    producto_id          = Column(Integer, ForeignKey("wms_productos.id"), nullable=False)
    lote_id              = Column(Integer, ForeignKey("wms_lotes.id"), nullable=True)
    cantidad             = Column(Float, nullable=False)
    ubicacion_origen_id  = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=False)
    ubicacion_destino_id = Column(Integer, ForeignKey("wms_ubicaciones.id"), nullable=True)
    cantidad_recibida    = Column(Float, nullable=True)

    traslado = relationship("WMSTraslado", back_populates="detalles")


class WMSEstadoOC(Base, TimestampMixin):
    """Estados de la orden de compra, configurables por cada empresa (Daily Logistics).

    El nombre, el color y el orden los decide la empresa, y puede agregar
    estados propios (p. ej. «Aprobada», «En tránsito») que se cambian a mano.
    Lo que el sistema hace solo —pasar la OC a «en recepción» al registrar una
    recepción, a «recibida parcial» o «recibida» al completarla— se apoya en el
    `rol`: cada rol lo tiene a lo sumo un estado. `codigo` es lo que se guarda en
    `wms_ordenes_compra.estado`, por eso no se cambia una vez creado.
    """
    __tablename__ = "wms_estados_oc"
    id     = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), nullable=False, unique=True)
    nombre = Column(String(60), nullable=False)
    color  = Column(String(20), nullable=False, default="#64748B")
    orden  = Column(Integer, nullable=False, default=0)
    # INICIAL / EN_RECEPCION / RECIBIDA_PARCIAL / RECIBIDA / CERRADA / ANULADA, o nada (estado manual).
    rol    = Column(String(20), nullable=True, unique=True)
    activo = Column(Boolean, nullable=False, default=True)


class DocConsecutivo(Base):
    """Consecutivo de documentos por tipo y año (Daily Logistics).

    De aquí salen los números estilo ERP (4500000042, 5000000007…): se incrementa
    con una sola sentencia atómica dentro de la transacción del documento, así
    que dos usuarios guardando a la vez nunca reciben el mismo número y, si el
    guardado falla, el número no se consume.
    """
    __tablename__ = "doc_consecutivos"
    __table_args__ = (UniqueConstraint("clave", "anio", name="uq_doc_consecutivo"),)
    id     = Column(Integer, primary_key=True)
    clave  = Column(String(80), nullable=False)    # tabla:prefijo, p. ej. wms_ordenes_compra:OC
    anio   = Column(Integer, nullable=False)          # 0 = serie continua (no reinicia por año)
    ultimo = Column(Integer, nullable=False, default=0)
