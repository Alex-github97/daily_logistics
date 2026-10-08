"""
Migración del WMS a la operación trazable (idempotente; corre dentro del candado
de migración, después de `create_all`).

1. Columnas nuevas en tablas que ya existían (`create_all` no las agrega).
2. Existencias: las filas repetidas del mismo producto, ubicación y lote se
   fusionan en una. Existían porque el UNIQUE viejo no veía los lotes NULL; se
   reemplaza por un índice único con COALESCE que además incluye la estiba.
3. Todo producto tiene dueño: si hay productos sin depositante se crea el
   depositante «propio» (la empresa) y se les asigna. Desde ahí el inventario,
   los indicadores y la facturación de almacenamiento se cortan por dueño.
4. El kárdex viejo recibe almacén y depositante, para poder filtrarlo igual que
   el nuevo.
"""
import logging

from sqlalchemy import text

log = logging.getLogger(__name__)

COLUMNAS = [
    ("wms_almacenes", "flujo_recepcion", "VARCHAR(12) DEFAULT 'DIRECTO' NOT NULL"),
    ("wms_productos", "depositante_id", "INTEGER REFERENCES wms_depositantes(id)"),
    ("wms_ordenes_compra", "depositante_id", "INTEGER REFERENCES wms_depositantes(id)"),
    ("wms_recepciones", "depositante_id", "INTEGER REFERENCES wms_depositantes(id)"),
    ("wms_recepciones", "muelle", "VARCHAR(30)"),
    ("wms_recepciones", "fecha_llegada", "TIMESTAMPTZ"),
    ("wms_recepciones", "inicio_descargue", "TIMESTAMPTZ"),
    ("wms_recepciones", "fin_descargue", "TIMESTAMPTZ"),
    ("wms_recepciones", "completada_en", "TIMESTAMPTZ"),
    ("wms_recepciones_detalle", "contenedor_id", "INTEGER REFERENCES wms_contenedores(id)"),
    ("wms_inventario_ubicacion", "contenedor_id", "INTEGER REFERENCES wms_contenedores(id)"),
    ("wms_movimientos_inventario", "contenedor_id", "INTEGER REFERENCES wms_contenedores(id)"),
    ("wms_movimientos_inventario", "contenedor_destino_id", "INTEGER REFERENCES wms_contenedores(id)"),
    ("wms_movimientos_inventario", "depositante_id", "INTEGER REFERENCES wms_depositantes(id)"),
    ("wms_movimientos_inventario", "almacen_id", "INTEGER REFERENCES wms_almacenes(id)"),
    ("wms_movimientos_inventario", "documento_tipo", "VARCHAR(30)"),
    ("wms_movimientos_inventario", "documento_id", "INTEGER"),
    ("wms_movimientos_inventario", "tarea_id", "INTEGER REFERENCES wms_tareas(id)"),
    ("wms_movimientos_inventario", "estado_origen", "VARCHAR(12)"),
    ("wms_movimientos_inventario", "estado_destino", "VARCHAR(12)"),
    ("wms_movimientos_inventario", "saldo_origen", "DOUBLE PRECISION"),
    ("wms_movimientos_inventario", "saldo_destino", "DOUBLE PRECISION"),
    ("wms_conteos_detalle", "contenedor_id", "INTEGER REFERENCES wms_contenedores(id)"),
    ("wms_ordenes_salida", "depositante_id", "INTEGER REFERENCES wms_depositantes(id)"),
    ("wms_picking_detalles", "cantidad_despachada", "DOUBLE PRECISION DEFAULT 0 NOT NULL"),
    ("wms_picking_detalles", "contenedor_id", "INTEGER REFERENCES wms_contenedores(id)"),
    ("wms_despachos", "muelle", "VARCHAR(30)"),
    ("wms_despachos", "inicio_cargue", "TIMESTAMPTZ"),
    ("wms_despachos", "fin_cargue", "TIMESTAMPTZ"),
    ("wms_despachos_detalle", "contenedor_id", "INTEGER REFERENCES wms_contenedores(id)"),
    ("wms_ubicaciones", "largo_cm", "DOUBLE PRECISION"),
    ("wms_ubicaciones", "ancho_cm", "DOUBLE PRECISION"),
    ("wms_ubicaciones", "alto_cm", "DOUBLE PRECISION"),
    ("wms_ubicaciones", "orden_recorrido", "INTEGER"),
    ("wms_picking_tareas", "ola_id", "INTEGER REFERENCES wms_olas(id)"),
    ("wms_movimientos_inventario", "comprobante_id", "INTEGER"),
    ("wms_recepciones", "factura_proveedor_id", "INTEGER"),
    ("wms_despachos", "factura_id", "INTEGER"),
    ("wms_despachos", "aviso_factura", "VARCHAR(300)"),
    ("wms_devoluciones", "nota_credito_id", "INTEGER"),
]

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_wms_mov_producto_fecha ON wms_movimientos_inventario (producto_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_wms_mov_lote ON wms_movimientos_inventario (lote_id)",
    "CREATE INDEX IF NOT EXISTS ix_wms_mov_contenedor ON wms_movimientos_inventario (contenedor_id)",
    "CREATE INDEX IF NOT EXISTS ix_wms_mov_contenedor_dest ON wms_movimientos_inventario (contenedor_destino_id)",
    "CREATE INDEX IF NOT EXISTS ix_wms_mov_documento ON wms_movimientos_inventario (documento_tipo, documento_id)",
    "CREATE INDEX IF NOT EXISTS ix_wms_mov_origen ON wms_movimientos_inventario (ubicacion_origen_id)",
    "CREATE INDEX IF NOT EXISTS ix_wms_mov_destino ON wms_movimientos_inventario (ubicacion_destino_id)",
]


async def migrar_wms(conn) -> None:
    if not (await conn.execute(text("SELECT to_regclass('wms_inventario_ubicacion')"))).scalar():
        return
    for tabla, columna, tipo in COLUMNAS:
        await conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}"))

    # 2. Fusionar filas repetidas y cambiar la llave.
    repetidas = (await conn.execute(text("""
        SELECT producto_id, ubicacion_id, COALESCE(lote_id, 0) AS l, COALESCE(contenedor_id, 0) AS c,
               min(id) AS queda, sum(cantidad_disponible) AS d, sum(cantidad_reservada) AS r,
               sum(cantidad_bloqueada) AS b, count(*) AS n
        FROM wms_inventario_ubicacion
        GROUP BY 1, 2, 3, 4 HAVING count(*) > 1"""))).all()
    for f in repetidas:
        await conn.execute(text("""
            DELETE FROM wms_inventario_ubicacion
            WHERE producto_id = :p AND ubicacion_id = :u AND COALESCE(lote_id, 0) = :l
              AND COALESCE(contenedor_id, 0) = :c AND id <> :q"""),
            {"p": f.producto_id, "u": f.ubicacion_id, "l": f.l, "c": f.c, "q": f.queda})
        await conn.execute(text("""
            UPDATE wms_inventario_ubicacion SET cantidad_disponible = :d, cantidad_reservada = :r,
                   cantidad_bloqueada = :b WHERE id = :q"""),
            {"d": f.d, "r": f.r, "b": f.b, "q": f.queda})
    if repetidas:
        log.warning("WMS: se fusionaron %d grupos de existencias repetidas (lote NULL).", len(repetidas))
    await conn.execute(text(
        "ALTER TABLE wms_inventario_ubicacion DROP CONSTRAINT IF EXISTS uq_inv_prod_ubic_lote"))
    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_clave ON wms_inventario_ubicacion
            (producto_id, ubicacion_id, COALESCE(lote_id, 0), COALESCE(contenedor_id, 0))"""))
    for sql in INDICES:
        await conn.execute(text(sql))

    # 3. Todo producto con dueño.
    sin_dueno = (await conn.execute(text(
        "SELECT count(*) FROM wms_productos WHERE depositante_id IS NULL"))).scalar()
    if sin_dueno:
        propio = (await conn.execute(text(
            "SELECT id FROM wms_depositantes WHERE propio ORDER BY id LIMIT 1"))).scalar()
        if propio is None:
            propio = (await conn.execute(text("""
                INSERT INTO wms_depositantes (codigo, nombre, propio, activo, created_at, updated_at)
                VALUES ('PROPIO', 'Mercancía propia', true, true, now(), now())
                ON CONFLICT (codigo) DO UPDATE SET propio = true
                RETURNING id"""))).scalar()
        await conn.execute(text("UPDATE wms_productos SET depositante_id = :d WHERE depositante_id IS NULL"),
                           {"d": propio})
        for tabla in ("wms_ordenes_compra", "wms_recepciones", "wms_ordenes_salida"):
            # El documento viejo toma el dueño de sus productos (todos eran del propio).
            await conn.execute(text(f"UPDATE {tabla} SET depositante_id = :d WHERE depositante_id IS NULL"),
                               {"d": propio})

    # 4. Kárdex viejo con almacén y depositante.
    await conn.execute(text("""
        UPDATE wms_movimientos_inventario m SET almacen_id = z.almacen_id
        FROM wms_ubicaciones u JOIN wms_zonas z ON z.id = u.zona_id
        WHERE m.almacen_id IS NULL AND u.id = COALESCE(m.ubicacion_origen_id, m.ubicacion_destino_id)"""))
    await conn.execute(text("""
        UPDATE wms_movimientos_inventario m SET depositante_id = p.depositante_id
        FROM wms_productos p WHERE m.depositante_id IS NULL AND p.id = m.producto_id"""))
