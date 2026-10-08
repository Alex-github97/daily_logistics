"""
Seed de datos coherentes para el módulo WMS.
Puebla catálogos, almacenes, zonas, ubicaciones, productos, lotes, inventario,
órdenes de compra, una recepción en borrador, órdenes de salida, un conteo
programado y algunos movimientos de historial.

Idempotente: si detecta el almacén 'ALM-BOG' ya creado, no vuelve a sembrar.

Ejecutar:  docker exec ci_backend python scripts/seed_wms.py
"""
import asyncio
from datetime import date, timedelta, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
# Importa TODOS los modelos para que el registro de mappers de SQLAlchemy
# resuelva las relaciones cruzadas (evita 'name not defined' al configurar).
from app.infrastructure.models import *  # noqa: F401,F403
from app.infrastructure.models import mantenimiento  # noqa: F401  (registra MantenimientoEstiba)
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.wms import (
    WMSTipoZona, WMSTipoUbicacion, WMSUnidadMedida, WMSMotivoMovimiento,
    WMSCategoriaProducto, WMSFamiliaProducto,
    WMSPais, WMSCiudad,
    WMSAlmacen, WMSZona, WMSUbicacion,
    WMSProducto, WMSLote,
    WMSProveedor, WMSCliente, WMSTransportadora,
    WMSOrdenCompra, WMSOrdenCompraDetalle,
    WMSRecepcion, WMSRecepcionDetalle,
    WMSInventarioUbicacion, WMSMovimientoInventario,
    WMSConteoInventario, WMSConteoDetalle,
    WMSOrdenSalida, WMSOrdenSalidaDetalle,
)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

HOY = date.today()


async def seed():
    async with Session() as db:  # type: AsyncSession
        # ── Motivos de reserva/bloqueo por defecto (idempotente aparte) ────────
        mot_count = await db.execute(select(WMSMotivoMovimiento))
        if not mot_count.scalars().first():
            db.add_all([
                WMSMotivoMovimiento(nombre="Pedido en preparación", tipo="RESERVA"),
                WMSMotivoMovimiento(nombre="Apartado para cliente", tipo="RESERVA"),
                WMSMotivoMovimiento(nombre="Reserva promocional", tipo="RESERVA"),
                WMSMotivoMovimiento(nombre="Transferencia pendiente", tipo="RESERVA"),
                WMSMotivoMovimiento(nombre="Producto averiado", tipo="BLOQUEO"),
                WMSMotivoMovimiento(nombre="En inspección de calidad", tipo="BLOQUEO"),
                WMSMotivoMovimiento(nombre="Vencido / próximo a vencer", tipo="BLOQUEO"),
                WMSMotivoMovimiento(nombre="Cuarentena", tipo="BLOQUEO"),
                WMSMotivoMovimiento(nombre="Retención por auditoría", tipo="BLOQUEO"),
            ])
            await db.commit()
            print("Motivos de reserva/bloqueo por defecto creados.")

        # ── Idempotencia ──────────────────────────────────────────────────────
        ya = await db.execute(select(WMSAlmacen).where(WMSAlmacen.codigo == "ALM-BOG"))
        if ya.scalar_one_or_none():
            print("WMS ya tiene datos base (ALM-BOG existe). Solo se verificaron motivos.")
            return

        # Usuario operario (si existe alguno)
        u = await db.execute(select(Usuario).order_by(Usuario.id).limit(1))
        operario = u.scalar_one_or_none()
        operario_id = operario.id if operario else None

        # ── Catálogos base ────────────────────────────────────────────────────
        db.add_all([
            WMSTipoZona(nombre="Recepción", descripcion="Zona de recibo de mercancía"),
            WMSTipoZona(nombre="Almacenamiento", descripcion="Zona de almacenaje"),
            WMSTipoZona(nombre="Despacho", descripcion="Zona de alistamiento y salida"),
            WMSTipoZona(nombre="Cuarentena", descripcion="Producto en inspección"),
        ])
        db.add_all([
            WMSTipoUbicacion(nombre="Estándar"),
            WMSTipoUbicacion(nombre="Pallet"),
            WMSTipoUbicacion(nombre="Cámara Fría"),
            WMSTipoUbicacion(nombre="Piso"),
        ])
        db.add_all([
            WMSUnidadMedida(nombre="Unidad", abreviatura="UND"),
            WMSUnidadMedida(nombre="Caja", abreviatura="CAJ"),
            WMSUnidadMedida(nombre="Kilogramo", abreviatura="KG"),
            WMSUnidadMedida(nombre="Litro", abreviatura="LT"),
            WMSUnidadMedida(nombre="Pallet", abreviatura="PAL"),
        ])

        cat_alim = WMSCategoriaProducto(nombre="Alimentos")
        cat_beb = WMSCategoriaProducto(nombre="Bebidas")
        cat_aseo = WMSCategoriaProducto(nombre="Aseo")
        db.add_all([cat_alim, cat_beb, cat_aseo])
        await db.flush()
        db.add_all([
            WMSFamiliaProducto(nombre="Granos", categoria_id=cat_alim.id),
            WMSFamiliaProducto(nombre="Enlatados", categoria_id=cat_alim.id),
            WMSFamiliaProducto(nombre="Gaseosas", categoria_id=cat_beb.id),
            WMSFamiliaProducto(nombre="Detergentes", categoria_id=cat_aseo.id),
        ])

        # ── Geografía ─────────────────────────────────────────────────────────
        col = WMSPais(nombre="Colombia", codigo_iso="CO")
        db.add(col)
        await db.flush()
        db.add_all([
            WMSCiudad(nombre="Bogotá", pais_id=col.id),
            WMSCiudad(nombre="Medellín", pais_id=col.id),
            WMSCiudad(nombre="Cali", pais_id=col.id),
        ])

        # ── Almacenes ─────────────────────────────────────────────────────────
        alm_bog = WMSAlmacen(codigo="ALM-BOG", nombre="Centro Distribución Bogotá",
                             direccion="Calle 13 # 100-20", ciudad="Bogotá", pais="Colombia")
        alm_med = WMSAlmacen(codigo="ALM-MED", nombre="Bodega Medellín",
                             direccion="Cra 50 # 20-30", ciudad="Medellín", pais="Colombia")
        db.add_all([alm_bog, alm_med])
        await db.flush()

        # ── Zonas + Ubicaciones (por almacén) ───────────────────────────────────
        # devuelve dict de ubicaciones por código para referenciar luego
        ubic = {}

        def crear_zonas_ubic(alm, pref):
            zr = WMSZona(almacen_id=alm.id, codigo=f"{pref}-ZR", nombre="Recepción", tipo="RECEPCION")
            za = WMSZona(almacen_id=alm.id, codigo=f"{pref}-ZA", nombre="Almacenamiento", tipo="ALMACENAMIENTO")
            zd = WMSZona(almacen_id=alm.id, codigo=f"{pref}-ZD", nombre="Despacho", tipo="DESPACHO")
            return zr, za, zd

        zbr, zba, zbd = crear_zonas_ubic(alm_bog, "BOG")
        zmr, zma, zmd = crear_zonas_ubic(alm_med, "MED")
        db.add_all([zbr, zba, zbd, zmr, zma, zmd])
        await db.flush()

        def add_ubic(zona, codigo, pasillo, estanteria, nivel, tipo="ESTANDAR"):
            o = WMSUbicacion(zona_id=zona.id, codigo=codigo, pasillo=pasillo,
                             estanteria=estanteria, nivel=nivel, posicion="01",
                             tipo=tipo, capacidad_kg=1000, capacidad_m3=2.5)
            db.add(o)
            ubic[codigo] = o
            return o

        # Bogotá
        add_ubic(zbr, "BOG-REC-01", "R", "01", "00", "PISO")
        add_ubic(zba, "BOG-A-01-01", "A", "01", "01")
        add_ubic(zba, "BOG-A-01-02", "A", "01", "02")
        add_ubic(zba, "BOG-A-02-01", "A", "02", "01")
        add_ubic(zbd, "BOG-DES-01", "D", "01", "00", "PISO")
        # Medellín
        add_ubic(zmr, "MED-REC-01", "R", "01", "00", "PISO")
        add_ubic(zma, "MED-A-01-01", "A", "01", "01")
        add_ubic(zmd, "MED-DES-01", "D", "01", "00", "PISO")
        await db.flush()

        # ── Productos ───────────────────────────────────────────────────────────
        prods = {}

        def add_prod(sku, nombre, categoria, familia, um, peso, vol, lote=False, refrig=False, vida=None):
            p = WMSProducto(sku=sku, nombre=nombre, categoria=categoria, familia=familia,
                            unidad_medida=um, peso_kg=peso, volumen_m3=vol,
                            requiere_lote=lote, requiere_refrigeracion=refrig, vida_util_dias=vida)
            db.add(p)
            prods[sku] = p
            return p

        add_prod("ARR-001", "Arroz Blanco 500g", "Alimentos", "Granos", "CAJA", 12, 0.03, lote=True, vida=365)
        add_prod("FRJ-001", "Fríjol Rojo 500g", "Alimentos", "Granos", "CAJA", 12, 0.03, lote=True, vida=365)
        add_prod("ATN-001", "Atún Lomitos 170g", "Alimentos", "Enlatados", "CAJA", 8, 0.02, lote=True, vida=730)
        add_prod("GAS-001", "Gaseosa Cola 1.5L", "Bebidas", "Gaseosas", "CAJA", 9, 0.02, lote=True, refrig=True, vida=180)
        add_prod("AGU-001", "Agua Botella 600ml", "Bebidas", "Gaseosas", "CAJA", 6, 0.02, lote=True, vida=365)
        add_prod("DET-001", "Detergente Polvo 1kg", "Aseo", "Detergentes", "UNIDAD", 1, 0.002)
        add_prod("JAB-001", "Jabón Barra x3", "Aseo", "Detergentes", "UNIDAD", 0.5, 0.001)
        add_prod("CLO-001", "Blanqueador 1L", "Aseo", "Detergentes", "UNIDAD", 1.1, 0.001)
        await db.flush()

        # ── Lotes (algunos próximos a vencer para disparar alertas) ─────────────
        lotes = {}

        def add_lote(sku, numero, dias_venc):
            lt = WMSLote(producto_id=prods[sku].id, numero_lote=numero,
                         fecha_fabricacion=HOY - timedelta(days=30),
                         fecha_vencimiento=HOY + timedelta(days=dias_venc),
                         proveedor_lote="Proveedor Genérico")
            db.add(lt)
            lotes[numero] = lt
            return lt

        add_lote("ARR-001", "LARR-2601", 300)
        add_lote("FRJ-001", "LFRJ-2601", 320)
        add_lote("ATN-001", "LATN-2601", 700)
        add_lote("GAS-001", "LGAS-2601", 20)   # vence en 20 días → alerta
        add_lote("AGU-001", "LAGU-2601", 15)   # vence en 15 días → alerta
        await db.flush()

        # ── Terceros ─────────────────────────────────────────────────────────
        prov1 = WMSProveedor(codigo="PRV-001", nombre="Distribuidora Nacional S.A.S.", nit="900111222-3",
                             contacto="Carlos Ruiz", email="ventas@disnal.co", telefono="6014567890",
                             ciudad="Bogotá", pais="Colombia")
        prov2 = WMSProveedor(codigo="PRV-002", nombre="Alimentos del Valle Ltda.", nit="800333444-5",
                             contacto="María Gómez", ciudad="Cali", pais="Colombia")
        prov3 = WMSProveedor(codigo="PRV-003", nombre="Aseo Total S.A.", nit="901555666-7",
                             ciudad="Medellín", pais="Colombia")
        db.add_all([prov1, prov2, prov3])

        cli1 = WMSCliente(codigo="CLI-001", nombre="Supermercados La Economía", nit="830111000-1",
                          contacto="Ana Torres", email="compras@laeconomia.co", ciudad="Bogotá",
                          pais="Colombia", segmento="RETAIL")
        cli2 = WMSCliente(codigo="CLI-002", nombre="Tiendas D1", nit="900222000-2",
                          ciudad="Medellín", pais="Colombia", segmento="RETAIL")
        cli3 = WMSCliente(codigo="CLI-003", nombre="Hotel Estelar", nit="860333000-3",
                          ciudad="Bogotá", pais="Colombia", segmento="B2B")
        cli4 = WMSCliente(codigo="CLI-004", nombre="Comprador Online", ciudad="Cali",
                          pais="Colombia", segmento="ECOMMERCE")
        db.add_all([cli1, cli2, cli3, cli4])

        trans1 = WMSTransportadora(codigo="TRA-001", nombre="TransCarga Express", nit="900777888-9",
                                   contacto="Pedro Díaz", telefono="3101234567")
        trans2 = WMSTransportadora(codigo="TRA-002", nombre="Logística Andina", nit="901999000-1")
        db.add_all([trans1, trans2])
        await db.flush()

        # ── Inventario inicial (stock disponible en almacenamiento Bogotá) ──────
        def add_inv(sku, codigo_ubic, cant, lote_num=None):
            inv = WMSInventarioUbicacion(
                producto_id=prods[sku].id,
                ubicacion_id=ubic[codigo_ubic].id,
                lote_id=lotes[lote_num].id if lote_num else None,
                cantidad_disponible=cant, cantidad_reservada=0, cantidad_bloqueada=0,
            )
            db.add(inv)
            return inv

        add_inv("ARR-001", "BOG-A-01-01", 500, "LARR-2601")
        add_inv("FRJ-001", "BOG-A-01-02", 300, "LFRJ-2601")
        add_inv("ATN-001", "BOG-A-02-01", 800, "LATN-2601")
        add_inv("GAS-001", "BOG-A-01-01", 240, "LGAS-2601")
        add_inv("AGU-001", "BOG-A-01-02", 600, "LAGU-2601")
        add_inv("DET-001", "BOG-A-02-01", 150)
        add_inv("JAB-001", "BOG-A-02-01", 400)
        # Medellín
        add_inv("DET-001", "MED-A-01-01", 90)
        add_inv("CLO-001", "MED-A-01-01", 120)
        await db.flush()

        # ── Órdenes de compra ───────────────────────────────────────────────────
        oc1 = WMSOrdenCompra(numero_oc="OC-2601-0001", proveedor_id=prov1.id, almacen_id=alm_bog.id,
                             fecha_emision=HOY - timedelta(days=5), fecha_esperada=HOY + timedelta(days=2),
                             estado="PENDIENTE", notas="Reposición de granos")
        oc2 = WMSOrdenCompra(numero_oc="OC-2601-0002", proveedor_id=prov3.id, almacen_id=alm_med.id,
                             fecha_emision=HOY - timedelta(days=2), fecha_esperada=HOY + timedelta(days=4),
                             estado="PENDIENTE", notas="Línea de aseo")
        db.add_all([oc1, oc2])
        await db.flush()
        db.add_all([
            WMSOrdenCompraDetalle(orden_id=oc1.id, producto_id=prods["ARR-001"].id,
                                  cantidad_solicitada=200, precio_unitario=18000, unidad_medida="CAJA"),
            WMSOrdenCompraDetalle(orden_id=oc1.id, producto_id=prods["FRJ-001"].id,
                                  cantidad_solicitada=150, precio_unitario=22000, unidad_medida="CAJA"),
            WMSOrdenCompraDetalle(orden_id=oc2.id, producto_id=prods["DET-001"].id,
                                  cantidad_solicitada=300, precio_unitario=6500, unidad_medida="UNIDAD"),
            WMSOrdenCompraDetalle(orden_id=oc2.id, producto_id=prods["CLO-001"].id,
                                  cantidad_solicitada=200, precio_unitario=4800, unidad_medida="UNIDAD"),
        ])

        # ── Recepción en BORRADOR contra OC-1 (para 'Completar' desde la UI) ────
        rec = WMSRecepcion(numero_recepcion="REC-2601-0001", tipo="CONTRA_OC",
                           orden_compra_id=oc1.id, almacen_id=alm_bog.id,
                           fecha_recepcion=HOY, estado="BORRADOR", operario_id=operario_id,
                           notas="Recibo parcial pendiente de put-away")
        db.add(rec)
        await db.flush()
        db.add_all([
            WMSRecepcionDetalle(recepcion_id=rec.id, producto_id=prods["ARR-001"].id,
                                lote_id=lotes["LARR-2601"].id, cantidad_esperada=200,
                                cantidad_recibida=200, ubicacion_id=ubic["BOG-A-01-01"].id,
                                estado_calidad="APROBADO"),
            WMSRecepcionDetalle(recepcion_id=rec.id, producto_id=prods["FRJ-001"].id,
                                lote_id=lotes["LFRJ-2601"].id, cantidad_esperada=150,
                                cantidad_recibida=150, ubicacion_id=ubic["BOG-A-01-02"].id,
                                estado_calidad="APROBADO"),
        ])

        # ── Órdenes de salida (para Generar Picking / Despachar desde la UI) ────
        os1 = WMSOrdenSalida(numero_orden="OS-2601-0001", cliente_id=cli1.id, almacen_id=alm_bog.id,
                             fecha_emision=HOY, fecha_requerida=HOY + timedelta(days=1),
                             estado="PENDIENTE", prioridad="ALTA", canal="RETAIL")
        os2 = WMSOrdenSalida(numero_orden="OS-2601-0002", cliente_id=cli3.id, almacen_id=alm_bog.id,
                             fecha_emision=HOY, fecha_requerida=HOY - timedelta(days=1),  # vencida → alerta
                             estado="PENDIENTE", prioridad="URGENTE", canal="B2B")
        db.add_all([os1, os2])
        await db.flush()
        db.add_all([
            WMSOrdenSalidaDetalle(orden_id=os1.id, producto_id=prods["ARR-001"].id,
                                  lote_id=lotes["LARR-2601"].id, cantidad_solicitada=50, precio_unitario=21000),
            WMSOrdenSalidaDetalle(orden_id=os1.id, producto_id=prods["ATN-001"].id,
                                  lote_id=lotes["LATN-2601"].id, cantidad_solicitada=80, precio_unitario=9500),
            WMSOrdenSalidaDetalle(orden_id=os2.id, producto_id=prods["GAS-001"].id,
                                  lote_id=lotes["LGAS-2601"].id, cantidad_solicitada=60, precio_unitario=7800),
        ])

        # ── Conteo cíclico PROGRAMADO con detalles (para capturar físico) ───────
        conteo = WMSConteoInventario(almacen_id=alm_bog.id, tipo="CICLICO", estado="PROGRAMADO",
                                     fecha_programada=HOY, operario_id=operario_id,
                                     notas="Conteo cíclico pasillo A")
        db.add(conteo)
        await db.flush()
        db.add_all([
            WMSConteoDetalle(conteo_id=conteo.id, producto_id=prods["ARR-001"].id,
                             ubicacion_id=ubic["BOG-A-01-01"].id, lote_id=lotes["LARR-2601"].id,
                             cantidad_sistema=500),
            WMSConteoDetalle(conteo_id=conteo.id, producto_id=prods["ATN-001"].id,
                             ubicacion_id=ubic["BOG-A-02-01"].id, lote_id=lotes["LATN-2601"].id,
                             cantidad_sistema=800),
        ])

        # ── Movimientos de historial (ajuste + transferencia) ───────────────────
        db.add_all([
            WMSMovimientoInventario(tipo="AJUSTE", producto_id=prods["DET-001"].id,
                                    ubicacion_destino_id=ubic["BOG-A-02-01"].id, cantidad=10,
                                    referencia_documento="AJUSTE_MANUAL", usuario_id=operario_id,
                                    notas="Ajuste por reconteo inicial"),
            WMSMovimientoInventario(tipo="TRANSFERENCIA", producto_id=prods["JAB-001"].id,
                                    ubicacion_origen_id=ubic["BOG-A-01-01"].id,
                                    ubicacion_destino_id=ubic["BOG-A-02-01"].id, cantidad=25,
                                    referencia_documento="TRANSFERENCIA", usuario_id=operario_id,
                                    notas="Reubicación de jabón"),
        ])

        await db.commit()
        print("WMS sembrado: 2 almacenes, 8 ubicaciones, 8 productos, 5 lotes, "
              "9 registros de inventario, 2 OC, 1 recepción (BORRADOR), 2 órdenes de salida, "
              "1 conteo (PROGRAMADO), 2 movimientos.")


if __name__ == "__main__":
    asyncio.run(seed())
