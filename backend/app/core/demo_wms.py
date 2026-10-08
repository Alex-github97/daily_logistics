"""
Siembra de volumen para el módulo de almacenes (WMS).

QUÉ ES Y QUÉ NO ES
Genera un año de operación de dos bodegas: compras a proveedores, recepciones,
ubicación de la mercancía, órdenes de salida, alistamiento, despachos, conteos
cíclicos y devoluciones. No es un relleno de tablas.

La diferencia está en una sola regla, y es la que hace que estos datos sirvan
para algo: **la existencia de cada producto en cada ubicación es exactamente la
suma de los movimientos que la tocaron**. El sembrador lleva el saldo en memoria
mientras avanza por los días, no despacha lo que no hay, y al final escribe el
inventario desde ese saldo. Un sembrador que escribiera existencias por un lado y
movimientos por otro produce una bodega que se ve llena y miente: el tablero
mostraría una exactitud de inventario inventada, que es justo el número que un
jefe de bodega mira primero.

Por lo mismo, los indicadores diarios (OTIF, fill rate, exactitud) se calculan de
las órdenes de ese día, no se sortean. Si un día salió mal, el tablero lo dice.

LOS DATOS SON VEROSÍMILES, NO ALEATORIOS
Hay estacionalidad —diciembre y julio pesan más—, unos pocos clientes que
concentran el despacho, proveedores que entregan tarde, y un porcentaje de
órdenes que se despachan incompletas. Sin eso el OTIF sale en 100% todos los días
y no se puede mostrar nada.

DETERMINISTA
Semilla fija: dos corridas producen exactamente los mismos datos.
"""
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.wms import (
    WMSAlmacen, WMSCategoriaProducto, WMSCiudad, WMSCliente, WMSConteoDetalle,
    WMSConteoInventario, WMSDespacho, WMSDespachoDetalle, WMSDevolucion,
    WMSDevolucionDetalle, WMSEventoTrazabilidad, WMSFamiliaProducto, WMSInventarioUbicacion, WMSLote,
    WMSKPIDiario, WMSMotivoMovimiento, WMSMovimientoInventario, WMSOrdenCompra,
    WMSOrdenCompraDetalle, WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSPais,
    WMSPickingDetalle, WMSPickingTarea, WMSProducto, WMSProveedor,
    WMSRecepcion, WMSRecepcionDetalle, WMSTarea, WMSTipoUbicacion, WMSTipoZona,
    WMSTransportadora, WMSUbicacion, WMSUnidadMedida, WMSZona,
)

SEMILLA = 20260903

# Diciembre y julio mueven más carga; enero y febrero son los meses flojos. Es el
# patrón de una operación logística en Colombia, y sin él la serie sale plana.
_ESTACIONALIDAD = {
    1: 0.78, 2: 0.85, 3: 1.00, 4: 0.97, 5: 1.05, 6: 1.02,
    7: 1.18, 8: 1.06, 9: 1.03, 10: 1.10, 11: 1.22, 12: 1.35,
}


# ─── Vocabulario ──────────────────────────────────────────────────────────────

_ALMACENES = [
    ("BOD-FUNZA", "Bodega Central Funza", "Km 2 Vía Siberia–Funza, Parque Industrial",
     "Funza"),
    ("CEDI-MED", "CEDI Medellín", "Calle 10 Sur #50-120, Guayabal", "Medellín"),
]

# Un catálogo de una empresa de transporte y logística: lo que de verdad se
# guarda en su bodega.
_CATEGORIAS: Dict[str, List[str]] = {
    "Repuestos": ["Motor", "Frenos", "Suspensión", "Transmisión", "Eléctrico"],
    "Lubricantes": ["Aceite motor", "Aceite transmisión", "Grasas", "Refrigerantes"],
    "Llantas": ["Dirección", "Tracción", "Remolque"],
    "Consumibles": ["Filtros", "Correas", "Mangueras", "Fijaciones"],
    "EPP": ["Protección cabeza", "Protección manos", "Alta visibilidad"],
    "Empaque": ["Estibas", "Zunchos", "Vinipel", "Cajas"],
}

_PIEZAS: Dict[str, List[Tuple[str, float, float]]] = {
    # (nombre, peso kg, precio de referencia)
    "Motor": [("Kit de empaques culata", 2.4, 385_000), ("Turbocompresor", 18.0, 4_250_000),
              ("Bomba de agua", 3.6, 620_000), ("Inyector common rail", 1.1, 890_000),
              ("Termostato", 0.4, 95_000)],
    "Frenos": [("Pastilla de freno delantera", 4.2, 310_000), ("Campana de freno", 32.0, 1_180_000),
               ("Pulmón de freno tipo 30", 6.5, 420_000), ("Válvula relay", 2.1, 560_000)],
    "Suspensión": [("Bolsa de aire suspensión", 8.4, 780_000), ("Amortiguador cabina", 3.2, 340_000),
                   ("Buje de muelle", 1.6, 88_000)],
    "Transmisión": [("Cruceta cardán", 5.8, 470_000), ("Disco de embrague 15\"", 12.4, 1_640_000),
                    ("Rodamiento de salida", 2.2, 295_000)],
    "Eléctrico": [("Alternador 24V 110A", 9.6, 1_320_000), ("Batería 150Ah", 41.0, 890_000),
                  ("Motor de arranque", 11.2, 1_450_000), ("Faro delantero LED", 2.8, 380_000)],
    "Aceite motor": [("Aceite 15W40 CI-4 balde 5gl", 18.5, 520_000),
                     ("Aceite 15W40 CI-4 tambor 55gl", 208.0, 5_400_000),
                     ("Aceite sintético 10W30 balde 5gl", 18.2, 690_000)],
    "Aceite transmisión": [("Aceite 80W90 balde 5gl", 18.8, 480_000),
                           ("ATF Dexron III galón", 3.8, 118_000)],
    "Grasas": [("Grasa litio EP-2 cuñete 35lb", 16.0, 340_000),
               ("Grasa de disulfuro cartucho", 0.4, 22_000)],
    "Refrigerantes": [("Refrigerante 50/50 galón", 3.9, 76_000),
                      ("Refrigerante concentrado tambor", 205.0, 3_200_000)],
    "Dirección": [("Llanta 295/80R22.5 dirección", 62.0, 1_780_000),
                  ("Llanta 315/80R22.5 dirección", 68.0, 1_950_000)],
    "Tracción": [("Llanta 295/80R22.5 tracción", 65.0, 1_820_000),
                 ("Llanta 11R22.5 tracción", 58.0, 1_540_000)],
    "Remolque": [("Llanta 385/65R22.5 remolque", 72.0, 2_100_000)],
    "Filtros": [("Filtro de aceite", 1.4, 68_000), ("Filtro de aire primario", 2.2, 145_000),
                ("Filtro separador de agua", 0.9, 92_000), ("Filtro de combustible", 0.8, 74_000),
                ("Filtro de cabina", 0.5, 46_000)],
    "Correas": [("Correa multi-V 8PK", 0.6, 118_000), ("Correa de ventilador", 0.4, 62_000)],
    "Mangueras": [("Manguera de radiador superior", 1.2, 135_000),
                  ("Manguera de aire 3/8\" metro", 0.2, 12_000)],
    "Fijaciones": [("Tuerca de rin M22", 0.3, 9_500), ("Perno de muelle", 0.5, 14_000),
                   ("Abrazadera 4\"", 0.2, 7_800)],
    "Protección cabeza": [("Casco dieléctrico", 0.4, 42_000), ("Gafas de seguridad", 0.1, 18_000)],
    "Protección manos": [("Guante de nitrilo par", 0.1, 9_000),
                         ("Guante de carnaza par", 0.2, 16_000)],
    "Alta visibilidad": [("Chaleco reflectivo", 0.2, 28_000), ("Botas dieléctricas par", 1.6, 185_000)],
    "Estibas": [("Estiba plástica 1.2x1.0", 16.0, 145_000), ("Estiba de madera 1.2x1.0", 22.0, 48_000)],
    "Zunchos": [("Zuncho poliéster rollo 500m", 14.0, 210_000), ("Grapa metálica caja x1000", 6.0, 58_000)],
    "Vinipel": [("Vinipel stretch rollo 20\"", 3.2, 38_000)],
    "Cajas": [("Caja corrugada 40x30x30", 0.5, 4_200), ("Caja corrugada 60x40x40", 0.9, 7_600)],
}

_PROVEEDORES = [
    "Distribuidora Andina de Repuestos", "Lubricantes del Norte", "Llantas y Rines Nacional",
    "Filtros Técnicos de Colombia", "Suministros Industriales Sabana", "Autopartes Magdalena",
    "Comercial Diesel Caribe", "Grupo Ferretero Occidente", "Dotaciones y EPP Seguros",
    "Empaques del Valle", "Importadora Pacífico Motors", "Frenos y Ejes Cordillera",
    "Baterías y Energía Orinoquía", "Rodamientos Técnicos SAS", "Aceites Premium Colombia",
    "Herramientas Altiplano", "Repuestos Pesados Antioquia", "Neumáticos del Tolima",
    "Insumos Logísticos Guajira", "Comercializadora Amazonía",
]

_CLIENTES = [
    ("Cervecería Nacional Andina", "Consumo masivo"), ("Alimentos Sabana SAS", "Consumo masivo"),
    ("Retail Express Colombia", "Retail"), ("Farmacéutica Caribe", "Farma"),
    ("Cementos Cordillera", "Industrial"), ("Agroindustrias Magdalena", "Agro"),
    ("Textiles Antioquia", "Manufactura"), ("Electrodomésticos Pacífico", "Retail"),
    ("Bebidas Orinoquía", "Consumo masivo"), ("Química Industrial Altiplano", "Industrial"),
    ("Papelera del Tolima", "Manufactura"), ("Lácteos Guajira", "Alimentos"),
    ("Ferretería Mayorista Nacional", "Retail"), ("Distribuidora Amazonía", "Consumo masivo"),
    ("Plásticos del Valle", "Manufactura"), ("Congelados del Caribe", "Alimentos"),
    ("Metalmecánica Sabana", "Industrial"), ("Cosméticos Bogotá SAS", "Consumo masivo"),
    ("Autopartes Retail Andina", "Retail"), ("Agrícola Llanos Orientales", "Agro"),
    ("Molinos del Huila", "Alimentos"), ("Vidrios Técnicos Colombia", "Industrial"),
    ("Confecciones Medellín", "Manufactura"), ("Bebidas Funcionales SAS", "Consumo masivo"),
    ("Hospital Universitario Central", "Salud"), ("Cadena de Supermercados Sur", "Retail"),
    ("Insumos Mineros Pacífico", "Minería"), ("Editorial Nacional", "Manufactura"),
    ("Refrigerados Andinos", "Alimentos"), ("Constructora Sabana Norte", "Construcción"),
]

_TRANSPORTADORAS = [
    ("TRA-001", "Coordinadora Mercantil"), ("TRA-002", "Envía Colvanes"),
    ("TRA-003", "TCC Logística"), ("TRA-004", "Servientrega Carga"),
    ("TRA-005", "Transportes Botero Soto"), ("TRA-006", "Flota Propia Demo"),
]

_NOMBRES = ["Andrés", "Carolina", "Diego", "Fernanda", "Gustavo", "Helena", "Iván",
            "Juliana", "Kevin", "Lorena", "Mauricio", "Natalia", "Óscar", "Paola",
            "Ricardo", "Sandra", "Tomás", "Valentina", "Wilson", "Yesenia"]
_APELLIDOS = ["Ramírez", "González", "Rodríguez", "Martínez", "Cárdenas", "Ospina",
              "Quintero", "Valencia", "Betancur", "Mejía", "Salazar", "Rincón",
              "Peláez", "Zapata", "Arango", "Cifuentes", "Bedoya", "Restrepo"]


def _persona(az: random.Random) -> str:
    return f"{az.choice(_NOMBRES)} {az.choice(_APELLIDOS)}"


def _nit(az: random.Random) -> str:
    cuerpo = az.randrange(800_000_000, 901_999_999)
    return f"{cuerpo}-{az.randrange(0, 10)}"


def _habil(d: date) -> bool:
    return d.weekday() < 5


class Progreso:
    """Va contando y avisando. Sembrar en silencio durante minutos es peor que
    lento: parece colgado."""

    def __init__(self, avisar):
        self.avisar = avisar or (lambda t: None)
        self.conteo: Dict[str, int] = {}

    def mas(self, clave: str, n: int = 1) -> None:
        self.conteo[clave] = self.conteo.get(clave, 0) + n

    def hito(self, texto: str) -> None:
        self.avisar(texto)


# ─── Siembra ──────────────────────────────────────────────────────────────────

async def sembrar_wms(
    db: AsyncSession, *,
    desde: date,
    hasta: date,
    salidas_por_dia_habil: int = 12,
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera la operación de dos bodegas entre dos fechas.

    Devuelve el recuento de lo creado, que es lo que permite comprobar después
    que el inventario cuadra con los movimientos.
    """
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)
    p = Progreso(avisar)

    async def confirmar() -> None:
        """Consolida y REPONE el esquema.

        El `search_path` vive en la conexión, no en la sesión: al consolidar, la
        conexión vuelve al pool y la siguiente puede ser otra, sin esquema. Es la
        misma trampa que ya costó dos fallos en producción.
        """
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    usuarios = [f[0] for f in (await db.execute(
        text("SELECT id FROM usuarios ORDER BY id LIMIT 20"))).all()] or [None]

    # ── Catálogos ──
    p.hito("Catálogos…")
    for nombre, desc in [("Recepción", "Zona de descargue y verificación"),
                         ("Almacenamiento", "Racks y estanterías"),
                         ("Despacho", "Zona de alistamiento y cargue"),
                         ("Cuarentena", "Mercancía retenida por calidad"),
                         ("Cross-docking", "Tránsito sin almacenamiento")]:
        db.add(WMSTipoZona(nombre=nombre, descripcion=desc, activo=True))
    for nombre, desc in [("Estándar", "Estantería convencional"),
                         ("Pallet", "Posición de estiba completa"),
                         ("Suelo", "Almacenamiento en piso"),
                         ("Cámara fría", "Temperatura controlada"),
                         ("Restringida", "Acceso controlado")]:
        db.add(WMSTipoUbicacion(nombre=nombre, descripcion=desc, activo=True))
    for nombre, abrev in [("Unidad", "UN"), ("Caja", "CJ"), ("Galón", "GL"),
                          ("Litro", "L"), ("Kilogramo", "KG"), ("Rollo", "RL"),
                          ("Par", "PAR"), ("Balde", "BLD"), ("Tambor", "TMB")]:
        db.add(WMSUnidadMedida(nombre=nombre, abreviatura=abrev, activo=True))
    for nombre, tipo in [("Reserva por orden de salida", "RESERVA"),
                         ("Reserva por traslado", "RESERVA"),
                         ("Bloqueo por calidad", "BLOQUEO"),
                         ("Bloqueo por vencimiento", "BLOQUEO"),
                         ("Bloqueo por conteo", "BLOQUEO")]:
        db.add(WMSMotivoMovimiento(nombre=nombre, tipo=tipo, activo=True))

    colombia = WMSPais(nombre="Colombia", codigo_iso="CO", activo=True)
    db.add(colombia)
    await db.flush()
    for ciudad in ["Bogotá D.C.", "Medellín", "Cali", "Barranquilla", "Cartagena",
                   "Bucaramanga", "Funza", "Pereira", "Ibagué", "Villavicencio"]:
        db.add(WMSCiudad(nombre=ciudad, pais_id=colombia.id, activo=True))

    categorias: Dict[str, WMSCategoriaProducto] = {}
    for nombre in _CATEGORIAS:
        cat = WMSCategoriaProducto(nombre=nombre, activo=True)
        db.add(cat)
        categorias[nombre] = cat
    await db.flush()
    for nombre, familias in _CATEGORIAS.items():
        for familia in familias:
            db.add(WMSFamiliaProducto(nombre=familia,
                                      categoria_id=categorias[nombre].id, activo=True))
    await db.flush()

    # ── Bodegas, zonas y ubicaciones ──
    p.hito("Bodegas y ubicaciones…")
    almacenes: List[WMSAlmacen] = []
    for codigo, nombre, direccion, ciudad in _ALMACENES:
        alm = WMSAlmacen(codigo=codigo, nombre=nombre, direccion=direccion,
                         ciudad=ciudad, pais="Colombia", activo=True)
        db.add(alm)
        almacenes.append(alm)
    await db.flush()

    # Las ubicaciones de almacenamiento son las únicas que reciben existencia.
    # Recepción y despacho son de paso: si les quedara saldo, el inventario del
    # tablero incluiría mercancía que en realidad está en el muelle.
    ubic_por_almacen: Dict[int, List[WMSUbicacion]] = {}
    for alm in almacenes:
        prefijo = alm.codigo.split("-")[-1][:3].upper()
        for tipo, nombre, sufijo in [("RECEPCION", "Recepción", "REC"),
                                     ("DESPACHO", "Despacho", "DES"),
                                     ("CUARENTENA", "Cuarentena", "CUA")]:
            zona = WMSZona(almacen_id=alm.id, codigo=f"{prefijo}-{sufijo}",
                           nombre=f"{nombre} {alm.nombre}", tipo=tipo, activo=True)
            db.add(zona)
            await db.flush()
            ub = WMSUbicacion(zona_id=zona.id, codigo=f"{prefijo}-{sufijo}-01",
                              tipo="SUELO", capacidad_kg=20_000, activo=True)
            db.add(ub)
            await db.flush()

        ubic_por_almacen[alm.id] = []
        for n_zona, letra in enumerate("ABC", start=1):
            zona = WMSZona(
                almacen_id=alm.id, codigo=f"{prefijo}-ALM{letra}",
                nombre=f"Almacenamiento {letra} · {alm.nombre}",
                tipo="ALMACENAMIENTO",
                temperatura_controlada=(letra == "C"), activo=True)
            db.add(zona)
            await db.flush()
            for pasillo in range(1, 5):
                for estanteria in range(1, 7):
                    for nivel in range(1, 4):
                        codigo = (f"{prefijo}-{letra}{pasillo:02d}"
                                  f"-{estanteria:02d}-{nivel}")
                        ub = WMSUbicacion(
                            zona_id=zona.id, codigo=codigo,
                            pasillo=f"{letra}{pasillo:02d}",
                            estanteria=f"{estanteria:02d}", nivel=str(nivel),
                            posicion="01",
                            tipo="PALLET" if nivel == 1 else "ESTANDAR",
                            capacidad_kg=1500 if nivel == 1 else 600,
                            capacidad_m3=2.4 if nivel == 1 else 1.1, activo=True)
                        db.add(ub)
                        ubic_por_almacen[alm.id].append(ub)
        await db.flush()
    p.mas("ubicaciones", sum(len(v) for v in ubic_por_almacen.values()) + len(almacenes) * 3)

    # ── Productos ──
    p.hito("Productos…")
    productos: List[WMSProducto] = []
    consecutivo = 0
    # Todo producto tiene dueño (operación 3PL): la empresa de demostración guarda mercancía propia.
    from app.core.wms_operacion import depositante_propio
    propio = await depositante_propio(db)
    for categoria, familias in _CATEGORIAS.items():
        for familia in familias:
            for nombre, peso, precio in _PIEZAS.get(familia, []):
                consecutivo += 1
                perecedero = categoria in ("Lubricantes",)
                producto = WMSProducto(
                    sku=f"SKU-{consecutivo:05d}", nombre=nombre,
                    descripcion=f"{nombre} · {familia} · {categoria}",
                    categoria=categoria, familia=familia,
                    unidad_medida="UNIDAD" if peso < 15 else "UNIDAD",
                    # Unos 450 kg/m³, la densidad de repuestos en su empaque: con
                    # 3,5 litros por kilo más 20 de base, un filtro de 1 kg ocupaba
                    # 23 litros y la bodega salía llena al 476%.
                    peso_kg=peso, volumen_m3=round(peso * 0.0022 + 0.001, 4),
                    costo_promedio=precio,
                    requiere_refrigeracion=False,
                    requiere_serial=(categoria == "Llantas"),
                    requiere_lote=perecedero,
                    vida_util_dias=730 if perecedero else None,
                    depositante_id=propio,
                    activo=True)
                producto._precio = precio          # solo para la siembra
                db.add(producto)
                productos.append(producto)
    await db.flush()
    p.mas("productos", len(productos))
    por_id: Dict[int, WMSProducto] = {x.id: x for x in productos}

    # Un lote por producto que lo exige, con vencimiento repartido.
    lotes: Dict[int, List[WMSLote]] = {}
    for producto in productos:
        if not producto.requiere_lote:
            continue
        lotes[producto.id] = []
        for n in range(1, 4):
            fabricacion = desde - timedelta(days=az.randrange(30, 200))
            lote = WMSLote(
                producto_id=producto.id,
                numero_lote=f"L{fabricacion:%y%m}-{producto.id:04d}-{n}",
                fecha_fabricacion=fabricacion,
                fecha_vencimiento=fabricacion + timedelta(days=producto.vida_util_dias or 730),
                proveedor_lote=az.choice(_PROVEEDORES), activo=True)
            db.add(lote)
            lotes[producto.id].append(lote)
    await db.flush()
    p.mas("lotes", sum(len(v) for v in lotes.values()))

    # ── Terceros ──
    p.hito("Proveedores, clientes y transportadoras…")
    proveedores: List[WMSProveedor] = []
    for i, nombre in enumerate(_PROVEEDORES, start=1):
        prov = WMSProveedor(
            codigo=f"PRV-{i:03d}", nombre=nombre, nit=_nit(az),
            contacto=_persona(az),
            email=f"compras{i}@proveedor-demo.com",
            telefono=f"60{az.randrange(1, 9)}{az.randrange(1000000, 9999999)}",
            ciudad=az.choice(["Bogotá D.C.", "Medellín", "Cali", "Barranquilla"]),
            pais="Colombia", activo=True)
        db.add(prov)
        proveedores.append(prov)

    clientes: List[WMSCliente] = []
    for i, (nombre, segmento) in enumerate(_CLIENTES, start=1):
        cli = WMSCliente(
            codigo=f"CLI-{i:03d}", nombre=nombre, nit=_nit(az),
            contacto=_persona(az),
            email=f"logistica{i}@cliente-demo.com",
            telefono=f"60{az.randrange(1, 9)}{az.randrange(1000000, 9999999)}",
            ciudad=az.choice(["Bogotá D.C.", "Medellín", "Cali", "Barranquilla",
                              "Bucaramanga", "Pereira"]),
            pais="Colombia", segmento=segmento, activo=True)
        db.add(cli)
        clientes.append(cli)

    transportadoras: List[WMSTransportadora] = []
    for codigo, nombre in _TRANSPORTADORAS:
        tra = WMSTransportadora(codigo=codigo, nombre=nombre, nit=_nit(az),
                                contacto=_persona(az),
                                telefono=f"60{az.randrange(1000000, 9999999)}",
                                activo=True)
        db.add(tra)
        transportadoras.append(tra)
    await db.flush()
    await confirmar()

    # Unos pocos clientes concentran el despacho. Sin esa concentración, un
    # informe de «clientes principales» sale con todos empatados y no dice nada.
    pesos_cliente = [max(0.4, az.gauss(1.0, 0.7)) for _ in clientes]
    for i in range(4):
        pesos_cliente[i] *= 4.0

    # ── El saldo, que es la columna vertebral de todo esto ──
    # (producto_id, ubicacion_id, lote_id) -> cantidad
    saldo: Dict[Tuple[int, int, Optional[int]], float] = {}
    # Dónde vive habitualmente cada producto en cada bodega.
    casa: Dict[Tuple[int, int], WMSUbicacion] = {}
    for alm in almacenes:
        disponibles = list(ubic_por_almacen[alm.id])
        az.shuffle(disponibles)
        for i, producto in enumerate(productos):
            casa[(producto.id, alm.id)] = disponibles[i % len(disponibles)]

    def ubicacion_de(producto: WMSProducto, alm: WMSAlmacen) -> WMSUbicacion:
        return casa[(producto.id, alm.id)]

    almacen_de: Dict[int, int] = {}
    for alm in almacenes:
        for u in ubic_por_almacen[alm.id]:
            almacen_de[u.id] = alm.id

    # Existencia por (producto, bodega). Se mantiene al mover en vez de
    # recalcularse: es lo que permite decidir qué reponer sin recorrer todo el
    # saldo en cada compra.
    existencia: Dict[Tuple[int, int], float] = {}

    def hay(producto_id: int, ubicacion_id: int, lote_id: Optional[int]) -> float:
        return saldo.get((producto_id, ubicacion_id, lote_id), 0.0)

    def mover(producto_id: int, ubicacion_id: int, lote_id: Optional[int],
              delta: float) -> None:
        clave = (producto_id, ubicacion_id, lote_id)
        saldo[clave] = round(saldo.get(clave, 0.0) + delta, 3)
        alm_id = almacen_de.get(ubicacion_id)
        if alm_id is not None:
            k = (producto_id, alm_id)
            existencia[k] = round(existencia.get(k, 0.0) + delta, 3)

    # ── Existencia inicial ──
    # La bodega no nace vacía el primer día: se le da un inventario de arranque y
    # se registra como un movimiento de ajuste, para que el saldo siga siendo la
    # suma de los movimientos y no una excepción escondida.
    p.hito("Inventario de arranque…")

    # Demanda esperada de un producto en una bodega, por día hábil: las salidas
    # del día se reparten entre bodegas, cada orden lleva 3 líneas en promedio
    # sobre todo el catálogo, y la cantidad por línea depende del precio (ver
    # las salidas más abajo). Con esto se dimensionan el arranque y las compras.
    def demanda_dia(producto: WMSProducto) -> float:
        por_linea = 12.5 if producto._precio < 500_000 else 3.0
        return max(0.05, salidas_por_dia_habil / len(almacenes) * 3 / len(productos) * por_linea)

    movimientos: List[WMSMovimientoInventario] = []
    for alm in almacenes:
        for producto in productos:
            if az.random() > 0.95:
                continue
            ub = ubicacion_de(producto, alm)
            lote = az.choice(lotes[producto.id]) if producto.requiere_lote else None
            cantidad = float(max(3, round(demanda_dia(producto) * az.uniform(25, 50))))
            mover(producto.id, ub.id, lote.id if lote else None, cantidad)
            movimientos.append(WMSMovimientoInventario(
                tipo="AJUSTE", producto_id=producto.id, ubicacion_destino_id=ub.id,
                lote_id=lote.id if lote else None, cantidad=cantidad,
                referencia_documento="INVENTARIO-INICIAL",
                usuario_id=az.choice(usuarios),
                notas="Saldo de apertura de la cuenta de demostración",
                created_at=datetime.combine(desde, time(7, 0), tzinfo=timezone.utc)))
    db.add_all(movimientos)
    await db.flush()
    p.mas("movimientos", len(movimientos))
    await confirmar()

    # ── El año, día por día ──
    p.hito("Operación diaria…")
    n_oc = n_rec = n_salida = n_desp = n_conteo = n_dev = 0
    n_mov = len(movimientos)
    kpis: List[WMSKPIDiario] = []
    ordenes_abiertas: List[Tuple[WMSOrdenSalida, List[WMSOrdenSalidaDetalle]]] = []

    dia = desde
    ultimo_mes = None
    while dia <= hasta:
        if not _habil(dia):
            dia += timedelta(days=1)
            continue
        estacion = _ESTACIONALIDAD[dia.month]

        if dia.month != ultimo_mes:
            ultimo_mes = dia.month
            p.hito(f"  {dia:%Y-%m}…")
            await confirmar()

        # ── Compras: dos o tres a la semana ──
        if dia.weekday() in (0, 2) or (dia.weekday() == 4 and az.random() < 0.5):
            for alm in almacenes:
                # Se compra lo que está bajo, no cualquier cosa, y hasta cubrir
                # mes y medio de demanda (el proveedor tarda hasta tres semanas).
                #
                # Con compras al azar, la bodega termina llena de lo que nadie
                # pide y vacía de lo que sí: el fill rate se quedaba en 66% y el
                # in-full en 28%. Y con cantidades fijas (90 a 260 por línea)
                # sin mirar cuánto se vende, el inventario solo crecía: 449 días
                # de cobertura y estanterías al 252% de su volumen.
                bajos = sorted(
                    (x for x in productos
                     if existencia.get((x.id, alm.id), 0.0) < demanda_dia(x) * 26),
                    key=lambda x: existencia.get((x.id, alm.id), 0.0) / demanda_dia(x)
                )[:az.randrange(5, 12)]
                if not bajos:
                    continue
                n_oc += 1
                prov = az.choice(proveedores)
                emision = dia
                esperada = dia + timedelta(days=az.randrange(3, 12))
                oc = WMSOrdenCompra(
                    numero_oc=f"OC-{dia:%Y}-{n_oc:05d}", proveedor_id=prov.id,
                    almacen_id=alm.id, fecha_emision=emision,
                    fecha_esperada=esperada, estado="PENDIENTE",
                    notas=None,
                    created_at=datetime.combine(emision, time(9, 0), tzinfo=timezone.utc))
                db.add(oc)
                await db.flush()

                detalles_oc: List[WMSOrdenCompraDetalle] = []
                for producto in bajos:
                    cantidad = float(max(1, round(demanda_dia(producto) * az.uniform(40, 55)
                                                  - existencia.get((producto.id, alm.id), 0.0))))
                    det = WMSOrdenCompraDetalle(
                        orden_id=oc.id, producto_id=producto.id,
                        cantidad_solicitada=cantidad, cantidad_recibida=0,
                        precio_unitario=producto._precio,
                        unidad_medida=producto.unidad_medida)
                    db.add(det)
                    detalles_oc.append(det)
                await db.flush()

                # La recepción llega cuando llega. Un 18% de los proveedores
                # entrega tarde, que es lo que hace que el indicador de
                # cumplimiento de proveedor tenga algo que mostrar.
                tarde = az.random() < 0.18
                llegada = esperada + timedelta(days=az.randrange(1, 9) if tarde else 0)
                if llegada > hasta:
                    continue
                # Cerca del corte, parte de la mercancía está todavía en el
                # muelle sin ubicar. Sin esto la bodega aparece con cero
                # recepciones pendientes, que es un estado que ninguna bodega
                # tiene: siempre hay algo descargándose.
                en_curso = (hasta - llegada).days <= 9 and az.random() < 0.45
                n_rec += 1
                # Los tiempos del muelle: el vehículo llega, espera turno,
                # descarga, y la mercancía queda ubicada horas después. Son los
                # que alimentan dock-to-stock y el tiempo de descargue.
                llega_vehiculo = datetime.combine(llegada, time(8, 30), tzinfo=timezone.utc)
                inicio_desc = llega_vehiculo + timedelta(minutes=az.randrange(5, 41))
                fin_desc = inicio_desc + timedelta(minutes=az.randrange(25, 91))
                ubicada = fin_desc + timedelta(minutes=az.randrange(40, 300))
                oc.depositante_id = propio
                rec = WMSRecepcion(
                    numero_recepcion=f"REC-{llegada:%Y}-{n_rec:05d}",
                    tipo="CONTRA_OC", orden_compra_id=oc.id, almacen_id=alm.id,
                    depositante_id=propio,
                    fecha_recepcion=llegada,
                    estado="EN_PROCESO" if en_curso else "COMPLETA",
                    operario_id=az.choice(usuarios),
                    notas="Entrega con retraso del proveedor" if tarde else None,
                    muelle=f"MUELLE-{az.randrange(1, 4)}",
                    fecha_llegada=llega_vehiculo,
                    inicio_descargue=inicio_desc,
                    fin_descargue=None if en_curso else fin_desc,
                    completada_en=None if en_curso else ubicada,
                    created_at=llega_vehiculo)
                db.add(rec)
                await db.flush()

                if en_curso:
                    continue

                completa = True
                for det in detalles_oc:
                    producto = por_id[det.producto_id]
                    # Un 12% llega incompleto y un 4% con problema de calidad.
                    faltante = az.random() < 0.12
                    recibida = (det.cantidad_solicitada if not faltante
                                else round(det.cantidad_solicitada * az.uniform(0.5, 0.9)))
                    if faltante:
                        completa = False
                    calidad = "CUARENTENA" if az.random() < 0.04 else "APROBADO"
                    lote = az.choice(lotes[producto.id]) if producto.requiere_lote else None
                    ub = ubicacion_de(producto, alm)
                    db.add(WMSRecepcionDetalle(
                        recepcion_id=rec.id, producto_id=producto.id,
                        lote_id=lote.id if lote else None,
                        cantidad_esperada=det.cantidad_solicitada,
                        cantidad_recibida=recibida, ubicacion_id=ub.id,
                        estado_calidad=calidad,
                        notas="Retenido para inspección" if calidad == "CUARENTENA" else None))
                    det.cantidad_recibida = recibida
                    # Lo que queda en cuarentena NO entra al disponible. Sumarlo
                    # seria mentirle al que mira el inventario.
                    if calidad == "APROBADO":
                        mover(producto.id, ub.id, lote.id if lote else None, recibida)
                        # La recepción no tiene origen: la mercancía entra de
                        # fuera de la bodega. Ponerle el muelle como origen se
                        # leería mejor, pero dejaría el muelle en negativo y
                        # entonces «inventario = suma de movimientos» dejaría de
                        # cumplirse, que es la única regla que sostiene esto.
                        db.add(WMSMovimientoInventario(
                            tipo="RECEPCION", producto_id=producto.id,
                            ubicacion_destino_id=ub.id,
                            lote_id=lote.id if lote else None, cantidad=recibida,
                            referencia_documento=rec.numero_recepcion,
                            documento_tipo="RECEPCION", documento_id=rec.id,
                            usuario_id=rec.operario_id,
                            created_at=ubicada))
                        n_mov += 1
                        # La ubicación de cada línea es una tarea con su
                        # sugerencia; un 7% se guarda en otro sitio, que es lo
                        # que mide el cumplimiento de la ubicación sugerida.
                        desvio = az.random() < 0.07
                        creada = fin_desc + timedelta(minutes=az.randrange(1, 10))
                        iniciada = creada + timedelta(minutes=az.randrange(2, 35))
                        db.add(WMSTarea(
                            tipo="UBICACION", estado="COMPLETADA", almacen_id=alm.id,
                            depositante_id=propio, producto_id=producto.id,
                            lote_id=lote.id if lote else None, cantidad=recibida,
                            ubicacion_sugerida_id=(az.choice(ubic_por_almacen[alm.id]).id
                                                   if desvio else ub.id),
                            ubicacion_destino_id=ub.id,
                            motivo_desvio="Ubicación sugerida ocupada; se guardó en el pasillo vecino" if desvio else None,
                            razon_sugerencia="Ubicación habitual del producto",
                            documento_tipo="RECEPCION", documento_id=rec.id,
                            operario_id=az.choice(usuarios), asignada_en=creada,
                            iniciada_en=iniciada,
                            terminada_en=min(ubicada, iniciada + timedelta(minutes=az.randrange(3, 11))),
                            created_at=creada))
                oc.estado = "COMPLETA" if completa else "PARCIAL"

        # ── Salidas del día ──
        cuantas = max(1, int(round(salidas_por_dia_habil * estacion * az.uniform(0.75, 1.25))))
        del_dia: List[Tuple[WMSOrdenSalida, List[WMSOrdenSalidaDetalle], bool, bool]] = []
        for _ in range(cuantas):
            n_salida += 1
            alm = az.choice(almacenes)
            cliente = az.choices(clientes, weights=pesos_cliente, k=1)[0]
            requerida = dia + timedelta(days=az.randrange(1, 5))
            orden = WMSOrdenSalida(
                numero_orden=f"OS-{dia:%Y}-{n_salida:06d}", cliente_id=cliente.id,
                almacen_id=alm.id, fecha_emision=dia, fecha_requerida=requerida,
                estado="PENDIENTE",
                prioridad=az.choices(["BAJA", "NORMAL", "ALTA", "URGENTE"],
                                     weights=[10, 62, 22, 6], k=1)[0],
                canal=az.choices(["B2B", "RETAIL", "ECOMMERCE", "TRANSFERENCIA"],
                                 weights=[52, 26, 16, 6], k=1)[0],
                created_at=datetime.combine(dia, time(az.randrange(7, 16),
                                                      az.randrange(0, 60)),
                                            tzinfo=timezone.utc))
            db.add(orden)
            await db.flush()

            detalles: List[WMSOrdenSalidaDetalle] = []
            for producto in az.sample(productos, az.randrange(1, 6)):
                ub = ubicacion_de(producto, alm)
                # El cliente no elige lote: se le asigna por FEFO el primero que
                # vence entre los que hay. Con un lote al azar, la línea quedaba
                # sin servir teniendo existencia de otro lote al lado.
                lote = None
                if producto.requiere_lote:
                    con_saldo = [x for x in lotes[producto.id] if hay(producto.id, ub.id, x.id) > 0]
                    lote = min(con_saldo or lotes[producto.id], key=lambda x: x.fecha_vencimiento)
                lote_id = lote.id if lote else None
                pedida =float(az.randrange(1, 25) if producto._precio < 500_000
                               else az.randrange(1, 6))
                det = WMSOrdenSalidaDetalle(
                    orden_id=orden.id, producto_id=producto.id, lote_id=lote_id,
                    cantidad_solicitada=pedida, cantidad_preparada=0,
                    cantidad_despachada=0, precio_unitario=producto._precio * 1.28,
                    estado="PENDIENTE")
                det._ubicacion = ub
                db.add(det)
                detalles.append(det)
            await db.flush()
            del_dia.append((orden, detalles, False, False))

        # ── Alistamiento y despacho ──
        # Se despacha lo del día y lo que quedó pendiente de días anteriores: una
        # bodega real arrastra cola, y el tablero de pendientes tiene que mostrarla.
        cola = ordenes_abiertas + [(o, d) for o, d, _, _ in del_dia]
        ordenes_abiertas = []
        completadas_hoy: List[Tuple[WMSOrdenSalida, bool, bool]] = []

        for orden, detalles in cola:
            # Un 8% se queda esperando: falta de mercancía, cliente que aplaza.
            # Y en los últimos días antes del corte se retiene bastante más,
            # porque una bodega tiene siempre trabajo del día sin cerrar: con
            # todo despachado, el tablero se lee como una operación detenida.
            cerca_del_corte = (hasta - dia).days <= 3
            umbral = 0.55 if cerca_del_corte else 0.08
            if az.random() < umbral and orden.fecha_emision >= dia - timedelta(days=6):
                ordenes_abiertas.append((orden, detalles))
                continue

            # El alistamiento dura lo que sus líneas (2 a 5 minutos cada una,
            # más el arranque), no el día entero: con inicio fijo a las 8:10 la
            # productividad salía en una línea por hora.
            orden.depositante_id = propio
            fin_picking = datetime.combine(dia, time(az.randrange(9, 16), az.randrange(0, 60)),
                                           tzinfo=timezone.utc)
            inicio_picking = fin_picking - timedelta(
                minutes=3 + sum(az.randrange(2, 6) for _ in detalles))
            tarea = WMSPickingTarea(
                orden_id=orden.id, operario_id=az.choice(usuarios),
                tipo=az.choices(["SINGLE", "BATCH", "ZONE", "WAVE"],
                                weights=[58, 22, 14, 6], k=1)[0],
                estado="COMPLETADA",
                fecha_asignacion=inicio_picking - timedelta(minutes=az.randrange(5, 60)),
                fecha_inicio=inicio_picking,
                fecha_fin=fin_picking,
                ubicaciones_visitadas=len(detalles), items_pickeados=0)
            db.add(tarea)
            await db.flush()

            in_full = True
            pickeados = 0
            salidas: List[WMSMovimientoInventario] = []
            for det in detalles:
                ub = det._ubicacion
                disponible = hay(det.producto_id, ub.id, det.lote_id)
                sacado = min(det.cantidad_solicitada, disponible)
                if sacado < det.cantidad_solicitada:
                    in_full = False
                if sacado > 0:
                    mover(det.producto_id, ub.id, det.lote_id, -sacado)
                    salida = WMSMovimientoInventario(
                        tipo="DESPACHO", producto_id=det.producto_id,
                        ubicacion_origen_id=ub.id, lote_id=det.lote_id,
                        cantidad=sacado, referencia_documento=orden.numero_orden,
                        usuario_id=tarea.operario_id,
                        created_at=tarea.fecha_fin)
                    db.add(salida)
                    salidas.append(salida)
                    n_mov += 1
                db.add(WMSPickingDetalle(
                    tarea_id=tarea.id, producto_id=det.producto_id,
                    ubicacion_id=ub.id, lote_id=det.lote_id,
                    cantidad_solicitada=det.cantidad_solicitada,
                    cantidad_pickeada=sacado, cantidad_despachada=sacado,
                    confirmado=True, timestamp_confirmacion=tarea.fecha_fin))
                # Cada confirmación queda en la bitácora; un 82% se verifica
                # con lector (código de la ubicación y del producto).
                db.add(WMSEventoTrazabilidad(
                    tipo_evento="PICKING_CONFIRMADO", entidad_tipo="PICKING_TAREA",
                    entidad_id=tarea.id, producto_id=det.producto_id,
                    ubicacion_id=ub.id, lote_id=det.lote_id,
                    usuario_id=tarea.operario_id,
                    descripcion=f"Alistadas {sacado:g} de {det.cantidad_solicitada:g}",
                    datos_adicionales={"verificado": az.random() < 0.82,
                                       "cantidad": sacado},
                    created_at=tarea.fecha_fin))
                det.cantidad_preparada = sacado
                det.cantidad_despachada = sacado
                det.estado = ("COMPLETO" if sacado >= det.cantidad_solicitada
                              else "PARCIAL" if sacado > 0 else "PENDIENTE")
                pickeados += 1
            tarea.items_pickeados = pickeados

            n_desp += 1
            transportadora = az.choice(transportadoras)
            entrega_estimada = orden.fecha_requerida or (dia + timedelta(days=2))
            # Un 11% entrega tarde. Ese número es el que sostiene el OTIF.
            atraso = az.randrange(1, 5) if az.random() < 0.11 else 0
            entrega_real = entrega_estimada + timedelta(days=atraso)
            on_time = atraso == 0
            # El cargue empieza cuando el alistamiento termina y el vehículo
            # está en el muelle; antes del cierre de las 17:00.
            inicio_cargue = max(tarea.fecha_fin, datetime.combine(dia, time(15, 0), tzinfo=timezone.utc)) \
                + timedelta(minutes=az.randrange(10, 41))
            peso =sum((por_id[d.producto_id].peso_kg or 0) * d.cantidad_despachada
                       for d in detalles)
            despacho = WMSDespacho(
                numero_despacho=f"DSP-{dia:%Y}-{n_desp:06d}", orden_id=orden.id,
                transportadora_id=transportadora.id,
                vehiculo_placa=f"{az.choice('STUVWXYZ')}{az.choice('ABCDEFGH')}"
                               f"{az.choice('ABCDEFGH')}{az.randrange(100, 999)}",
                conductor_nombre=_persona(az), fecha_despacho=dia,
                fecha_entrega_estimada=entrega_estimada,
                fecha_entrega_real=entrega_real if entrega_real <= hasta else None,
                estado=("ENTREGADO" if entrega_real <= hasta else "EN_TRANSITO"),
                peso_total_kg=round(peso, 2),
                volumen_total_m3=round(peso * 0.0035, 3),
                notas=f"Entrega con {atraso} día(s) de atraso" if atraso else None,
                muelle=f"MUELLE-{az.randrange(4, 7)}",
                inicio_cargue=inicio_cargue,
                fin_cargue=inicio_cargue + timedelta(minutes=az.randrange(20, 71)),
                created_at=datetime.combine(dia, time(17, 0), tzinfo=timezone.utc))
            db.add(despacho)
            await db.flush()
            for salida in salidas:
                salida.documento_tipo = "DESPACHO"
                salida.documento_id = despacho.id
            for det in detalles:
                if det.cantidad_despachada <= 0:
                    continue
                db.add(WMSDespachoDetalle(
                    despacho_id=despacho.id, producto_id=det.producto_id,
                    lote_id=det.lote_id, cantidad=det.cantidad_despachada,
                    numero_tracking=f"{transportadora.codigo}-{despacho.id:07d}"))
            orden.estado = "ENTREGADO" if despacho.estado == "ENTREGADO" else "DESPACHADO"
            completadas_hoy.append((orden, on_time, in_full))

            # Devoluciones: un 3% del despacho vuelve.
            if az.random() < 0.03 and detalles:
                n_dev += 1
                fecha_dev = min(hasta, entrega_real + timedelta(days=az.randrange(2, 12)))
                dev = WMSDevolucion(
                    numero_devolucion=f"DEV-{fecha_dev:%Y}-{n_dev:05d}",
                    tipo="CLIENTE", orden_referencia_id=orden.id,
                    cliente_id=orden.cliente_id, almacen_id=orden.almacen_id,
                    fecha_recepcion=fecha_dev, estado="APROBADA",
                    motivo=az.choice(["Producto averiado en tránsito",
                                      "Referencia equivocada",
                                      "Cliente rechazó la entrega",
                                      "Cantidad excedida"]),
                    created_at=datetime.combine(fecha_dev, time(10, 0),
                                                tzinfo=timezone.utc))
                db.add(dev)
                await db.flush()
                det = az.choice(detalles)
                if det.cantidad_despachada > 0:
                    vuelve = max(1.0, round(det.cantidad_despachada * az.uniform(0.2, 1.0)))
                    calidad = az.choices(["BUENO", "DANO_MENOR", "DANO_MAYOR"],
                                         weights=[64, 24, 12], k=1)[0]
                    accion = "REINGRESAR" if calidad == "BUENO" else "CUARENTENA"
                    db.add(WMSDevolucionDetalle(
                        devolucion_id=dev.id, producto_id=det.producto_id,
                        lote_id=det.lote_id, cantidad=vuelve,
                        estado_calidad=calidad, accion=accion,
                        reingresado=(accion == "REINGRESAR")))
                    # Solo lo que vuelve bueno regresa al disponible.
                    if accion == "REINGRESAR":
                        ub = det._ubicacion
                        mover(det.producto_id, ub.id, det.lote_id, vuelve)
                        db.add(WMSMovimientoInventario(
                            tipo="DEVOLUCION", producto_id=det.producto_id,
                            ubicacion_destino_id=ub.id, lote_id=det.lote_id,
                            cantidad=vuelve,
                            referencia_documento=dev.numero_devolucion,
                            usuario_id=az.choice(usuarios),
                            created_at=datetime.combine(fecha_dev, time(11, 0),
                                                        tzinfo=timezone.utc)))
                        n_mov += 1

        # ── Conteo cíclico: dos veces por semana ──
        exactitud = None
        if dia.weekday() in (1, 3):
            n_conteo += 1
            alm = almacenes[n_conteo % len(almacenes)]
            conteo = WMSConteoInventario(
                almacen_id=alm.id, tipo="CICLICO", estado="COMPLETO",
                fecha_programada=dia,
                fecha_inicio=datetime.combine(dia, time(6, 30), tzinfo=timezone.utc),
                fecha_fin=datetime.combine(dia, time(8, 0), tzinfo=timezone.utc),
                operario_id=az.choice(usuarios),
                created_at=datetime.combine(dia, time(6, 0), tzinfo=timezone.utc))
            db.add(conteo)
            await db.flush()

            candidatos = [(k, v) for k, v in saldo.items() if v > 0
                          and any(u.id == k[1] for u in ubic_por_almacen[alm.id])]
            az.shuffle(candidatos)
            revisados = candidatos[:20]
            exactos = 0
            for (producto_id, ubicacion_id, lote_id), cantidad in revisados:
                # Un 6% de las posiciones tiene diferencia. Ese es el número real
                # de una bodega bien llevada, y es el que produce la exactitud.
                if az.random() < 0.06:
                    fisica = max(0.0, cantidad + az.choice([-3, -2, -1, 1, 2]))
                else:
                    fisica = cantidad
                    exactos += 1
                diferencia = round(fisica - cantidad, 3)
                db.add(WMSConteoDetalle(
                    conteo_id=conteo.id, producto_id=producto_id,
                    ubicacion_id=ubicacion_id, lote_id=lote_id,
                    cantidad_sistema=cantidad, cantidad_fisica=fisica,
                    diferencia=diferencia, ajustado=bool(diferencia)))
                # La diferencia se ajusta de verdad: si no, el conteo del mes
                # siguiente encontraría el mismo descuadre y el sistema se vería
                # como si nadie corrigiera nada.
                if diferencia:
                    mover(producto_id, ubicacion_id, lote_id, diferencia)
                    db.add(WMSMovimientoInventario(
                        tipo="CONTEO", producto_id=producto_id,
                        ubicacion_destino_id=ubicacion_id if diferencia > 0 else None,
                        ubicacion_origen_id=ubicacion_id if diferencia < 0 else None,
                        lote_id=lote_id, cantidad=abs(diferencia),
                        referencia_documento=f"CONTEO-{conteo.id:05d}",
                        usuario_id=conteo.operario_id,
                        notas="Ajuste por conteo cíclico",
                        created_at=conteo.fecha_fin))
                    n_mov += 1
            exactitud = round(100.0 * exactos / len(revisados), 2) if revisados else None

        # ── Traslados internos ──
        if az.random() < 0.4:
            con_saldo = [(k, v) for k, v in saldo.items() if v > 3]
            if con_saldo:
                (producto_id, origen_id, lote_id), cantidad = az.choice(con_saldo)
                alm = next(a for a in almacenes
                           if any(u.id == origen_id for u in ubic_por_almacen[a.id]))
                destino = az.choice(ubic_por_almacen[alm.id])
                if destino.id != origen_id:
                    cuanto = float(az.randrange(1, max(2, int(cantidad // 2))))
                    mover(producto_id, origen_id, lote_id, -cuanto)
                    mover(producto_id, destino.id, lote_id, cuanto)
                    db.add(WMSMovimientoInventario(
                        tipo="TRANSFERENCIA", producto_id=producto_id,
                        ubicacion_origen_id=origen_id, ubicacion_destino_id=destino.id,
                        lote_id=lote_id, cantidad=cuanto,
                        referencia_documento=f"TRF-{dia:%Y%m%d}",
                        usuario_id=az.choice(usuarios),
                        notas="Reubicación por optimización de picking",
                        created_at=datetime.combine(dia, time(15, 0), tzinfo=timezone.utc)))
                    n_mov += 1

        # ── Los indicadores del día, calculados de lo que pasó ──
        if completadas_hoy:
            total = len(completadas_hoy)
            on_time = sum(1 for _, t, _ in completadas_hoy if t)
            in_full = sum(1 for _, _, f in completadas_hoy if f)
            otif = sum(1 for _, t, f in completadas_hoy if t and f)
            kpis.append(WMSKPIDiario(
                fecha=dia, almacen_id=almacenes[0].id,
                ordenes_total=total, ordenes_on_time=on_time,
                ordenes_in_full=in_full, ordenes_otif=otif,
                ordenes_perfect=otif,
                fill_rate=round(100.0 * in_full / total, 2),
                inventory_accuracy=exactitud,
                cost_per_order=round(az.uniform(8_500, 14_800), 2),
                dock_to_stock_minutes=round(az.uniform(38, 145), 1),
                picking_accuracy=round(az.uniform(97.2, 99.9), 2),
                shipping_accuracy=round(az.uniform(98.0, 99.9), 2)))

        p.mas("salidas", len(del_dia))
        dia += timedelta(days=1)

    # Lo que quedó sin despachar al final se queda pendiente, que es lo correcto:
    # una bodega nunca está en cero pendientes.
    for orden, detalles in ordenes_abiertas:
        orden.estado = az.choices(["PENDIENTE", "EN_PICKING", "EMPACANDO"],
                                  weights=[52, 33, 15], k=1)[0]
        # Una orden en alistamiento tiene una tarea abierta. Poner solo el
        # estado deja el tablero diciendo «0 tareas de picking activas» al lado
        # de «15 órdenes pendientes», que es una contradicción que cualquier
        # jefe de bodega ve en dos segundos.
        if orden.estado in ("EN_PICKING", "EMPACANDO"):
            tarea = WMSPickingTarea(
                orden_id=orden.id, operario_id=az.choice(usuarios),
                tipo=az.choice(["SINGLE", "BATCH", "ZONE"]),
                estado="EN_PROGRESO",
                fecha_asignacion=datetime.combine(hasta, time(7, 30),
                                                  tzinfo=timezone.utc),
                fecha_inicio=datetime.combine(hasta, time(7, 45),
                                              tzinfo=timezone.utc),
                ubicaciones_visitadas=az.randrange(0, max(1, len(detalles))),
                items_pickeados=az.randrange(0, max(1, len(detalles))))
            db.add(tarea)
            await db.flush()
            for det in detalles:
                db.add(WMSPickingDetalle(
                    tarea_id=tarea.id, producto_id=det.producto_id,
                    ubicacion_id=det._ubicacion.id, lote_id=det.lote_id,
                    cantidad_solicitada=det.cantidad_solicitada,
                    cantidad_pickeada=0, confirmado=False))

    db.add_all(kpis)
    await db.flush()
    await confirmar()

    # ── El inventario, escrito desde el saldo ──
    p.hito("Consolidando el inventario…")
    filas = 0
    for (producto_id, ubicacion_id, lote_id), cantidad in saldo.items():
        if cantidad <= 0:
            continue
        # Una parte del stock está comprometida o retenida. Se marca acá y no
        # durante el recorrido porque es una foto del cierre, no un movimiento.
        # En unidades enteras: estos productos no se parten. «783,81 kits de
        # empaques» delata al instante que la cifra la calculó alguien y no la
        # contó nadie.
        reservada = float(int(cantidad * az.uniform(0.0, 0.18))) if az.random() < 0.25 else 0.0
        bloqueada = float(int(cantidad * az.uniform(0.0, 0.10))) if az.random() < 0.08 else 0.0
        db.add(WMSInventarioUbicacion(
            producto_id=producto_id, ubicacion_id=ubicacion_id, lote_id=lote_id,
            cantidad_disponible=round(cantidad - reservada - bloqueada, 3),
            cantidad_reservada=reservada, cantidad_bloqueada=bloqueada))
        filas += 1
    await db.flush()
    # El kárdex lleva dueño y almacén en cada línea: de ahí salen la facturación
    # 3PL (ocupación diaria reconstruida hacia atrás), el portal del cliente y
    # los filtros por almacén. Se completa al final, en una sola sentencia, en
    # vez de repetirlo en cada uno de los sitios que registran movimientos.
    await db.execute(text("""
        UPDATE wms_movimientos_inventario m
           SET depositante_id = COALESCE(m.depositante_id, p.depositante_id),
               almacen_id = COALESCE(m.almacen_id, z.almacen_id)
          FROM wms_productos p, wms_ubicaciones u, wms_zonas z
         WHERE p.id = m.producto_id
           AND u.id = COALESCE(m.ubicacion_destino_id, m.ubicacion_origen_id)
           AND z.id = u.zona_id"""))
    await confirmar()

    resumen = {
        "almacenes": len(almacenes),
        "ubicaciones": p.conteo.get("ubicaciones", 0),
        "productos": len(productos),
        "lotes": p.conteo.get("lotes", 0),
        "proveedores": len(proveedores),
        "clientes": len(clientes),
        "ordenes_compra": n_oc,
        "recepciones": n_rec,
        "ordenes_salida": n_salida,
        "despachos": n_desp,
        "conteos": n_conteo,
        "devoluciones": n_dev,
        "movimientos": n_mov,
        "posiciones_con_saldo": filas,
        "dias_con_indicadores": len(kpis),
    }
    p.hito("WMS sembrado.")
    return resumen


async def verificar(db: AsyncSession) -> dict:
    """Comprueba la única regla que importa: el inventario es la suma de los
    movimientos.

    Se corre después de sembrar. Si esto no cuadra, los datos no sirven para
    medir nada y es mejor saberlo acá que descubrirlo en una demostración.
    """
    movido = (await db.execute(text("""
        SELECT COALESCE(SUM(delta), 0) FROM (
            SELECT cantidad AS delta FROM wms_movimientos_inventario
             WHERE ubicacion_destino_id IS NOT NULL
            UNION ALL
            SELECT -cantidad FROM wms_movimientos_inventario
             WHERE ubicacion_origen_id IS NOT NULL
        ) t"""))).scalar() or 0
    en_stock = (await db.execute(text(
        "SELECT COALESCE(SUM(cantidad_disponible + cantidad_reservada "
        "+ cantidad_bloqueada), 0) FROM wms_inventario_ubicacion"))).scalar() or 0
    negativos = (await db.execute(text(
        "SELECT count(*) FROM wms_inventario_ubicacion "
        "WHERE cantidad_disponible < 0"))).scalar() or 0
    return {
        "movimientos_netos": round(float(movido), 2),
        "inventario_total": round(float(en_stock), 2),
        "diferencia": round(float(movido) - float(en_stock), 2),
        "posiciones_negativas": int(negativos),
    }
