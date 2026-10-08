"""
Inventario del CMMS — bodegas, existencias y kárdex.

QUÉ PROBLEMA RESUELVE
`eam_repuesto` ya tenía un `stock_actual`: un número suelto, sin bodega y sin
historia. No se podía responder «cuánto hay en Bogotá», ni «de dónde salió esa
diferencia», que son las dos preguntas que se le hacen a un inventario.

LAS TRES TABLAS Y POR QUÉ SON TRES

  eam_inv_bodega       dónde está el material
  eam_inv_existencia   cuánto hay de cada repuesto en cada bodega
  eam_inv_movimiento   por qué llegó a ser esa cantidad

La existencia es un saldo calculado que se guarda por rapidez; el kárdex es la
verdad. Si algún día no cuadran, el kárdex manda y la existencia se recalcula —
por eso cada movimiento guarda el saldo que dejó, y no solo la cantidad.

EL COSTEO ES PROMEDIO PONDERADO
Cada entrada recalcula el costo promedio de esa existencia y cada salida sale a
ese promedio. Es el método que la contabilidad colombiana acepta sin discusión y
el único que se puede explicar sin rastrear lote por lote. PEPS obligaría a
llevar capas por lote, que es otro modelo entero y nadie pidió.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint, Index,
)
from app.infrastructure.models.base import Base, TimestampMixin


class InvBodega(Base, TimestampMixin):
    """Bodega de repuestos, ubicada en la jerarquía geográfica del catálogo
    maestro: País → Departamento → Ciudad.

    Se apunta al catálogo maestro y no se guardan los nombres como texto porque
    esa jerarquía ya existe y la comparten todos los módulos. Escribir «Bogotá»
    a mano acá crearía una tercera versión de la misma ciudad y los informes por
    región dejarían de cuadrar.
    """
    __tablename__ = "eam_inv_bodega"
    __table_args__ = (UniqueConstraint("codigo", name="uq_eam_inv_bodega_codigo"),)
    id     = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(40), nullable=False)
    nombre = Column(String(150), nullable=False)

    # Ambos apuntan a `catalogo_maestro`. La ciudad ya cuelga de su país por
    # `padre_id`, pero se guarda el país aparte para poder registrar una bodega
    # de la que solo se sabe el país todavía.
    pais_id   = Column(Integer, ForeignKey("catalogo_maestro.id"), nullable=True)
    ciudad_id = Column(Integer, ForeignKey("catalogo_maestro.id"), nullable=True)

    direccion   = Column(String(250), nullable=True)
    responsable = Column(String(120), nullable=True)
    telefono    = Column(String(50), nullable=True)
    # La bodega por defecto es a la que van las salidas de una OT cuando nadie
    # dice de dónde sacar el repuesto. Solo una puede serlo.
    por_defecto = Column(Boolean, default=False, nullable=False)
    observaciones = Column(Text, nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)


class InvExistencia(Base, TimestampMixin):
    """Cuánto hay de un repuesto en una bodega, y a qué costo promedio."""
    __tablename__ = "eam_inv_existencia"
    __table_args__ = (
        UniqueConstraint("repuesto_id", "bodega_id", name="uq_eam_inv_existencia"),
        Index("ix_eam_inv_existencia_bodega", "bodega_id"),
    )
    id          = Column(Integer, primary_key=True, index=True)
    repuesto_id = Column(Integer, ForeignKey("eam_repuesto.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    bodega_id   = Column(Integer, ForeignKey("eam_inv_bodega.id", ondelete="CASCADE"),
                         nullable=False)

    cantidad       = Column(Float, default=0, nullable=False)
    costo_promedio = Column(Float, default=0, nullable=False)

    # Mínimos y máximos por bodega, no globales: la bodega de una sede pequeña
    # no necesita el mismo colchón que la central.
    stock_minimo = Column(Float, nullable=True)
    stock_maximo = Column(Float, nullable=True)
    ubicacion    = Column(String(80), nullable=True)   # estante, nivel, gaveta

    # Última fecha con movimiento. Es lo que permite detectar el material
    # dormido sin recorrer todo el kárdex.
    ultimo_movimiento = Column(DateTime, nullable=True)


class InvMotivo(Base, TimestampMixin):
    """Motivos de ajuste, tipificados.

    Un ajuste sin motivo es un descuadre que nadie puede explicar tres meses
    después. Tipificarlos permite además ver si los faltantes vienen de conteos,
    de daños o de material que se prestó y no volvió.
    """
    __tablename__ = "eam_inv_motivo"
    __table_args__ = (UniqueConstraint("nombre", name="uq_eam_inv_motivo_nombre"),)
    id     = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(30), nullable=True)
    nombre = Column(String(150), nullable=False)
    # ENTRADA | SALIDA | AMBOS — para qué lado del ajuste sirve.
    sentido     = Column(String(10), default="AMBOS", nullable=False)
    descripcion = Column(String(300), nullable=True)
    activo      = Column(Boolean, default=True, nullable=False)


class InvMovimiento(Base, TimestampMixin):
    """El kárdex. Cada línea dice qué pasó, cuánto costó y con qué saldo quedó.

    `cantidad` siempre es positiva; el signo lo pone `tipo`. Guardar cantidades
    negativas obliga a recordar la convención en cada consulta y tarde o
    temprano alguien la suma mal.
    """
    __tablename__ = "eam_inv_movimiento"
    __table_args__ = (
        Index("ix_eam_inv_mov_repuesto_fecha", "repuesto_id", "fecha"),
        Index("ix_eam_inv_mov_bodega_fecha", "bodega_id", "fecha"),
        Index("ix_eam_inv_mov_ot", "ot_id"),
    )
    id          = Column(Integer, primary_key=True, index=True)
    fecha       = Column(DateTime, nullable=False, index=True)
    repuesto_id = Column(Integer, ForeignKey("eam_repuesto.id"), nullable=False)
    bodega_id   = Column(Integer, ForeignKey("eam_inv_bodega.id"), nullable=False)

    # ENTRADA | SALIDA | AJUSTE_ENTRADA | AJUSTE_SALIDA | TRASLADO_ENTRADA |
    # TRASLADO_SALIDA | DEVOLUCION
    tipo = Column(String(20), nullable=False, index=True)

    cantidad        = Column(Float, nullable=False)
    costo_unitario  = Column(Float, default=0, nullable=False)
    costo_total     = Column(Float, default=0, nullable=False)

    # Saldo que dejó el movimiento. Se guarda para poder auditar el kárdex sin
    # recomputarlo entero, y para detectar si la existencia se desincronizó.
    saldo_cantidad = Column(Float, nullable=True)
    saldo_costo_promedio = Column(Float, nullable=True)

    # De dónde viene. `ot_material_id` es lo que permite reconciliar: al editar
    # una orden se compara lo ya despachado contra lo que la línea dice ahora y
    # se mueve solo la diferencia, en vez de descontar de nuevo.
    ot_id          = Column(Integer, ForeignKey("eam_orden_trabajo.id", ondelete="SET NULL"),
                            nullable=True)
    ot_material_id = Column(Integer, nullable=True)
    motivo_id      = Column(Integer, ForeignKey("eam_inv_motivo.id"), nullable=True)
    # La contraparte de un traslado, para poder verlos en pareja.
    traslado_id    = Column(Integer, nullable=True)

    documento   = Column(String(80), nullable=True)   # factura, remisión, conteo
    proveedor   = Column(String(150), nullable=True)
    observaciones = Column(Text, nullable=True)
    registrado_por = Column(String(120), nullable=True)
