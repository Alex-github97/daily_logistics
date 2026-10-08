"""
Siembra de volumen para el módulo de abastecimiento (SCM).

QUÉ ES Y QUÉ NO ES
Genera el ciclo completo de compras de un año: solicitudes internas que se
aprueban o se rechazan, órdenes de compra que salen de esas solicitudes,
recepciones parciales y totales, y la evaluación trimestral de cada proveedor.

Dos reglas hacen que estos datos sirvan:

1. **El total de una orden es la suma de sus renglones, con su descuento y su
   IVA.** No hay un «total» escrito aparte. Un módulo de compras cuyo total no
   se puede rehacer renglón por renglón no le sirve a nadie para negociar.

2. **La calificación de un proveedor sale de sus entregas, no de un sorteo.**
   El puntaje de cumplimiento en tiempo se calcula de las órdenes que ese
   proveedor entregó tarde de verdad, y la clasificación A/B/C/D sale del
   puntaje. Así, cuando el módulo dice que hay que reemplazar a un proveedor,
   se puede ir a mirar cuáles entregas lo justifican.

DETERMINISTA
Semilla fija: dos corridas producen exactamente los mismos datos.
"""
import random
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.proveedor import Proveedor
from app.infrastructure.models.scm import (
    CategoriaSCM, ClasificacionProveedor, EstadoOrdenSCM, EstadoSolicitudSCM,
    PrioridadSCM, RecomendacionProveedor, ScmEvaluacionProveedor,
    ScmOrdenCompra, ScmOrdenItem, ScmSolicitudCompra, ScmSolicitudItem,
)

SEMILLA = 20260906

_ESTACIONALIDAD = {
    1: 0.72, 2: 0.88, 3: 1.05, 4: 0.98, 5: 1.06, 6: 1.02,
    7: 1.10, 8: 1.04, 9: 1.06, 10: 1.14, 11: 1.28, 12: 0.90,
}

# El IVA general en Colombia. Los servicios de transporte de carga están
# excluidos, pero lo que se compra acá —repuestos, equipos, papelería— sí lo
# lleva, y por eso el módulo lo aplica a todo salvo lo que se marque exento.
IVA = 0.19

# (razón social, tipo de lo que vende, categoría, ciudad)
_PROVEEDORES = [
    ("Distribuidora Andina de Repuestos SAS", CategoriaSCM.REPUESTOS, "Bogotá D.C."),
    ("Lubricantes del Norte SA", CategoriaSCM.INSUMOS, "Barranquilla"),
    ("Llantas y Rines Nacional SAS", CategoriaSCM.REPUESTOS, "Bogotá D.C."),
    ("Filtros Técnicos de Colombia", CategoriaSCM.REPUESTOS, "Medellín"),
    ("Suministros Industriales Sabana", CategoriaSCM.MATERIALES, "Funza"),
    ("Autopartes Magdalena SAS", CategoriaSCM.REPUESTOS, "Barranquilla"),
    ("Comercial Diesel Caribe", CategoriaSCM.REPUESTOS, "Cartagena"),
    ("Grupo Ferretero Occidente", CategoriaSCM.MATERIALES, "Cali"),
    ("Dotaciones y EPP Seguros SAS", CategoriaSCM.INSUMOS, "Bogotá D.C."),
    ("Empaques del Valle", CategoriaSCM.MATERIALES, "Cali"),
    ("Importadora Pacífico Motors", CategoriaSCM.EQUIPOS, "Buenaventura"),
    ("Frenos y Ejes Cordillera", CategoriaSCM.REPUESTOS, "Medellín"),
    ("Baterías y Energía Orinoquía", CategoriaSCM.REPUESTOS, "Villavicencio"),
    ("Rodamientos Técnicos SAS", CategoriaSCM.REPUESTOS, "Bogotá D.C."),
    ("Aceites Premium Colombia", CategoriaSCM.INSUMOS, "Bogotá D.C."),
    ("Sistemas y Redes Altiplano", CategoriaSCM.IT, "Bogotá D.C."),
    ("Soluciones Cloud Andinas", CategoriaSCM.IT, "Medellín"),
    ("Papelería Corporativa Nacional", CategoriaSCM.PAPELERIA, "Bogotá D.C."),
    ("Servicios de Báscula y Pesaje", CategoriaSCM.SERVICIOS, "Funza"),
    ("Vigilancia y Escolta Segura SAS", CategoriaSCM.SERVICIOS, "Bogotá D.C."),
    ("Mantenimiento Locativo Integral", CategoriaSCM.SERVICIOS, "Funza"),
    ("Montacargas y Equipos del Centro", CategoriaSCM.EQUIPOS, "Bogotá D.C."),
    ("Transportes Aliados de Carga", CategoriaSCM.LOGISTICA, "Medellín"),
    ("Operador Portuario del Caribe", CategoriaSCM.LOGISTICA, "Cartagena"),
    ("Combustibles y Estaciones Sabana", CategoriaSCM.INSUMOS, "Funza"),
]

# (título de la solicitud, categoría, renglones típicos con unidad y precio)
_COMPRAS: Dict[CategoriaSCM, List[tuple]] = {
    CategoriaSCM.REPUESTOS: [
        ("Kit de frenos para flota pesada", [
            ("Pastilla de freno delantera", "JUEGO", 310_000),
            ("Campana de freno", "UN", 1_180_000),
            ("Pulmón de freno tipo 30", "UN", 420_000)]),
        ("Reposición de llantas de dirección", [
            ("Llanta 295/80R22.5 dirección", "UN", 1_780_000),
            ("Válvula de rin", "UN", 12_000)]),
        ("Repuestos de motor para overhaul", [
            ("Kit de empaques culata", "JUEGO", 385_000),
            ("Bomba de agua", "UN", 620_000),
            ("Inyector common rail", "UN", 890_000)]),
        ("Sistema eléctrico de cabina", [
            ("Alternador 24V 110A", "UN", 1_320_000),
            ("Batería 150Ah", "UN", 890_000)]),
    ],
    CategoriaSCM.INSUMOS: [
        ("Aceite de motor para el trimestre", [
            ("Aceite 15W40 CI-4 tambor 55gl", "TMB", 5_400_000),
            ("Filtro de aceite", "UN", 68_000)]),
        ("Dotación semestral de personal operativo", [
            ("Camisa de dotación", "UN", 58_000),
            ("Pantalón de dotación", "UN", 72_000),
            ("Botas dieléctricas", "PAR", 185_000)]),
        ("Elementos de protección personal", [
            ("Casco dieléctrico", "UN", 42_000),
            ("Gafas de seguridad", "UN", 18_000),
            ("Guante de carnaza", "PAR", 16_000),
            ("Chaleco reflectivo", "UN", 28_000)]),
    ],
    CategoriaSCM.MATERIALES: [
        ("Material de empaque para despachos", [
            ("Vinipel stretch rollo 20\"", "RL", 38_000),
            ("Zuncho poliéster rollo 500m", "RL", 210_000),
            ("Caja corrugada 60x40x40", "UN", 7_600)]),
        ("Estibas de reposición", [
            ("Estiba plástica 1.2x1.0", "UN", 145_000),
            ("Estiba de madera 1.2x1.0", "UN", 48_000)]),
    ],
    CategoriaSCM.EQUIPOS: [
        ("Montacargas eléctrico para el CEDI", [
            ("Montacargas eléctrico 2.5 t", "UN", 118_000_000),
            ("Cargador de batería industrial", "UN", 14_500_000)]),
        ("Herramienta de taller", [
            ("Gato hidráulico 20 t", "UN", 2_400_000),
            ("Torquímetro 1/2\"", "UN", 890_000),
            ("Compresor de 100 galones", "UN", 6_800_000)]),
    ],
    CategoriaSCM.IT: [
        ("Renovación de equipos de cómputo", [
            ("Portátil corporativo 16 GB", "UN", 4_200_000),
            ("Monitor 24 pulgadas", "UN", 780_000)]),
        ("Terminales de radiofrecuencia para bodega", [
            ("Terminal RF con lector 2D", "UN", 3_900_000),
            ("Base de carga múltiple", "UN", 1_100_000)]),
        ("Licenciamiento anual de ofimática", [
            ("Licencia de ofimática por usuario", "UN", 720_000)]),
    ],
    CategoriaSCM.SERVICIOS: [
        ("Servicio de vigilancia para la sede", [
            ("Puesto de vigilancia 24 horas / mes", "MES", 8_900_000)]),
        ("Calibración anual de básculas", [
            ("Calibración de báscula camionera", "UN", 2_300_000)]),
        ("Mantenimiento locativo de bodega", [
            ("Pintura de demarcación por m²", "M2", 46_000),
            ("Reparación de portón de muelle", "UN", 3_200_000)]),
    ],
    CategoriaSCM.LOGISTICA: [
        ("Contratación de transporte aliado", [
            ("Flete Bogotá–Barranquilla tractocamión", "VJE", 5_800_000),
            ("Flete Bogotá–Medellín tractocamión", "VJE", 2_900_000)]),
        ("Operación portuaria de importación", [
            ("Manejo de contenedor 40 pies", "UN", 1_650_000)]),
    ],
    CategoriaSCM.PAPELERIA: [
        ("Papelería y aseo del trimestre", [
            ("Resma de papel carta", "UN", 18_500),
            ("Tóner de impresora", "UN", 320_000),
            ("Insumos de aseo surtidos", "GLB", 1_400_000)]),
    ],
}

_JUSTIFICACIONES = [
    "Reposición de existencias por consumo del período.",
    "Requerimiento del plan de mantenimiento preventivo.",
    "Solicitud de la jefatura de operaciones para atender el crecimiento del despacho.",
    "Reemplazo de elementos dados de baja en la última inspección.",
    "Cumplimiento del programa anual de seguridad y salud en el trabajo.",
    "Contrato vigente que requiere renovación antes del vencimiento.",
]

_RECHAZOS = [
    "El presupuesto del centro de costo ya está comprometido para el período.",
    "Se solicita cotizar con al menos dos proveedores adicionales.",
    "La necesidad se cubre con existencias disponibles en bodega.",
    "Se aplaza para el siguiente trimestre por prioridad de otras compras.",
]


def _habil(d: date) -> bool:
    return d.weekday() < 5


def _nit(az: random.Random) -> str:
    return f"{az.randrange(800_000_000, 901_999_999)}-{az.randrange(0, 10)}"


async def sembrar_scm(
    db: AsyncSession, *,
    desde: date,
    hasta: date,
    solicitudes_por_semana: int = 7,
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera el ciclo de compras entre dos fechas."""
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)

    async def confirmar() -> None:
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    usuarios = [f[0] for f in (await db.execute(
        text("SELECT id FROM usuarios ORDER BY id LIMIT 20"))).all()]
    if not usuarios:
        raise RuntimeError("No hay usuarios en el esquema: el módulo de compras "
                           "necesita un solicitante y un aprobador.")

    # ── Proveedores ──
    avisar("Proveedores…")
    proveedores: List[Proveedor] = []
    for i, (razon, categoria, ciudad) in enumerate(_PROVEEDORES, start=1):
        p = Proveedor(
            nit=_nit(az), razon_social=razon,
            nombre_comercial=razon.replace(" SAS", "").replace(" SA", ""),
            tipo="COMPRA",
            contacto_nombre=None,
            contacto_email=f"ventas{i}@proveedor-demo.com",
            contacto_telefono=f"60{az.randrange(1, 9)}{az.randrange(1000000, 9999999)}",
            direccion=f"Calle {az.randrange(1, 180)} #{az.randrange(1, 99)}-{az.randrange(1, 99)}",
            ciudad=ciudad, codigo_sap=f"SAP-{i:05d}",
            observaciones=None)
        p._categoria = categoria
        db.add(p)
        proveedores.append(p)
    await db.flush()
    await confirmar()

    # Cada proveedor tiene su propio nivel de cumplimiento, y no cambia día a
    # día. Es lo que hace que la evaluación trimestral distinga a unos de otros:
    # con todos igual de buenos, la clasificación A/B/C/D sale toda en A y el
    # módulo no sirve para lo único que se le pide.
    puntualidad = {p.id: min(0.99, max(0.55, az.gauss(0.87, 0.12)))
                   for p in proveedores}
    por_categoria: Dict[CategoriaSCM, List[Proveedor]] = {}
    for p in proveedores:
        por_categoria.setdefault(p._categoria, []).append(p)

    # ── El ciclo de compras ──
    avisar("Solicitudes y órdenes…")
    n_sol = n_ord = 0
    items_sol = items_ord = 0
    # Entregas por proveedor, para calificar después con datos y no con un dado.
    entregas: Dict[int, List[bool]] = {p.id: [] for p in proveedores}

    dia = desde
    ultimo_mes = None
    while dia <= hasta:
        if dia.weekday() != 0:      # las solicitudes se radican los lunes
            dia += timedelta(days=1)
            continue
        if dia.month != ultimo_mes:
            ultimo_mes = dia.month
            avisar(f"  {dia:%Y-%m}…")
            await confirmar()

        estacion = _ESTACIONALIDAD[dia.month]
        cuantas = max(1, int(round(solicitudes_por_semana * estacion
                                   * az.uniform(0.7, 1.3))))
        for _ in range(cuantas):
            n_sol += 1
            categoria = az.choices(
                list(_COMPRAS), weights=[26, 20, 14, 8, 10, 12, 6, 4], k=1)[0]
            titulo, renglones = az.choice(_COMPRAS[categoria])
            solicitante = az.choice(usuarios)
            aprobador = az.choice([u for u in usuarios if u != solicitante] or usuarios)

            lineas = []
            estimado = 0.0
            for descripcion, unidad, precio in renglones:
                # La cantidad tiene que ser creíble para lo que se compra.
                # Nadie pide cinco montacargas de golpe: con la misma regla para
                # todo, un solo renglón de equipos se lleva el presupuesto anual
                # y el gasto por categoría deja de significar nada.
                cantidad = float(
                    1 if precio > 50_000_000
                    else az.randrange(1, 3) if precio > 3_000_000
                    else az.randrange(3, 26))
                total = round(cantidad * precio, 2)
                estimado += total
                lineas.append((descripcion, unidad, cantidad, precio, total))

            # El camino de la solicitud. Un 14% se rechaza y un 8% se queda sin
            # decidir: una bandeja de aprobaciones vacía no existe en ninguna
            # empresa, y es justo la pantalla que abre un jefe de compras.
            suerte = az.random()
            sin_decidir = (hasta - dia).days < 25 and suerte < 0.28
            rechazada = not sin_decidir and suerte > 0.86
            fecha_aprobacion = None if (sin_decidir or rechazada) else \
                dia + timedelta(days=az.randrange(1, 9))

            estado_sol = (EstadoSolicitudSCM.PENDIENTE if sin_decidir
                          else EstadoSolicitudSCM.RECHAZADA if rechazada
                          else EstadoSolicitudSCM.APROBADA)

            solicitud = ScmSolicitudCompra(
                numero=f"SOL-{dia:%Y}-{n_sol:05d}",
                solicitante_id=solicitante,
                aprobador_id=None if sin_decidir else aprobador,
                proveedor_id=None, titulo=titulo,
                descripcion=f"{titulo}. {az.choice(_JUSTIFICACIONES)}",
                categoria=categoria,
                prioridad=az.choices(
                    [PrioridadSCM.BAJA, PrioridadSCM.MEDIA,
                     PrioridadSCM.ALTA, PrioridadSCM.URGENTE],
                    weights=[14, 54, 26, 6], k=1)[0],
                estado=estado_sol,
                fecha_requerida=dia + timedelta(days=az.randrange(12, 60)),
                presupuesto_estimado=round(estimado, 2), moneda="COP",
                justificacion=az.choice(_JUSTIFICACIONES),
                observaciones=None,
                fecha_aprobacion=fecha_aprobacion,
                motivo_rechazo=az.choice(_RECHAZOS) if rechazada else None,
                created_at=None)
            db.add(solicitud)
            await db.flush()

            for descripcion, unidad, cantidad, precio, total in lineas:
                db.add(ScmSolicitudItem(
                    solicitud_id=solicitud.id, descripcion=descripcion,
                    unidad=unidad, cantidad=cantidad, precio_estimado=precio,
                    total_estimado=total, especificaciones=None))
                items_sol += 1

            if estado_sol is not EstadoSolicitudSCM.APROBADA:
                continue

            # ── La orden de compra que sale de la solicitud ──
            n_ord += 1
            candidatos = por_categoria.get(categoria) or proveedores
            proveedor = az.choice(candidatos)
            emision = fecha_aprobacion + timedelta(days=az.randrange(0, 6))
            plazo = az.randrange(8, 40)
            esperada = emision + timedelta(days=plazo)

            # ¿Entregó a tiempo? Sale del nivel de cumplimiento de ESE proveedor,
            # que es lo que después justifica su calificación.
            a_tiempo = az.random() < puntualidad[proveedor.id]
            real = esperada + (timedelta(days=0) if a_tiempo
                               else timedelta(days=az.randrange(2, 22)))
            entregada = real <= hasta
            if entregada:
                entregas[proveedor.id].append(a_tiempo)

            # Un 9% de lo entregado llega incompleto.
            parcial = entregada and az.random() < 0.09

            orden = ScmOrdenCompra(
                numero=f"OC-{emision:%Y}-{n_ord:05d}",
                solicitud_id=solicitud.id, proveedor_id=proveedor.id,
                creado_por_id=solicitante, aprobado_por_id=aprobador,
                estado=(EstadoOrdenSCM.RECIBIDA_PARCIAL if parcial
                        else EstadoOrdenSCM.CERRADA if entregada
                        else EstadoOrdenSCM.EN_TRANSITO
                        if emision <= hasta else EstadoOrdenSCM.ENVIADA),
                categoria=categoria, prioridad=solicitud.prioridad,
                fecha_emision=emision, fecha_entrega_esperada=esperada,
                fecha_entrega_real=real if entregada else None,
                subtotal=0, impuestos=0, total=0, moneda="COP",
                condiciones_pago=az.choice(
                    ["Contado", "30 días", "45 días", "60 días", "50% anticipo"]),
                lugar_entrega=az.choice(
                    ["Bodega Central Funza", "CEDI Medellín", "Punto Barranquilla"]),
                notas=None, codigo_sap=None)
            db.add(orden)
            await db.flush()

            # El total se arma renglón por renglón. No se escribe aparte: un
            # total que no se puede rehacer no sirve para negociar con nadie.
            subtotal = 0.0
            for descripcion, unidad, cantidad, precio, _t in lineas:
                descuento = az.choice([0.0, 0.0, 0.0, 3.0, 5.0, 8.0])
                bruto = cantidad * precio
                total_linea = round(bruto * (1 - descuento / 100.0), 2)
                subtotal += total_linea
                recibida = (cantidad if entregada and not parcial
                            else round(cantidad * az.uniform(0.4, 0.9))
                            if parcial else 0.0)
                db.add(ScmOrdenItem(
                    orden_id=orden.id, descripcion=descripcion,
                    codigo_producto=None, unidad=unidad, cantidad=cantidad,
                    cantidad_recibida=recibida, precio_unitario=precio,
                    descuento_pct=descuento, total=total_linea,
                    especificaciones=None))
                items_ord += 1

            # Los servicios de transporte de carga están excluidos de IVA; el
            # resto lo lleva. Aplicárselo a todo por comodidad falsearía el
            # gasto de un rubro entero.
            impuestos = 0.0 if categoria is CategoriaSCM.LOGISTICA \
                else round(subtotal * IVA, 2)
            orden.subtotal = round(subtotal, 2)
            orden.impuestos = impuestos
            orden.total = round(subtotal + impuestos, 2)

            solicitud.estado = (EstadoSolicitudSCM.COMPLETADA if entregada
                                else EstadoSolicitudSCM.EN_PROCESO)
            solicitud.proveedor_id = proveedor.id

        dia += timedelta(days=1)

    await db.flush()
    await confirmar()

    # ── Evaluación trimestral, calculada de las entregas ──
    avisar("Evaluación de proveedores…")
    n_eval = 0
    trimestres = []
    cursor = date(desde.year, ((desde.month - 1) // 3) * 3 + 1, 1)
    while cursor <= hasta:
        trimestres.append(f"{cursor.year}-T{(cursor.month - 1) // 3 + 1}")
        mes = cursor.month + 3
        cursor = date(cursor.year + (mes > 12), (mes - 1) % 12 + 1, 1)

    for proveedor in proveedores:
        historial = entregas[proveedor.id]
        if not historial:
            continue
        # El cumplimiento en tiempo es un hecho, no una opinión: sale de las
        # entregas de ese proveedor. Las demás notas se mueven alrededor de él,
        # porque un proveedor que incumple rara vez brilla en lo demás.
        cumplimiento = 100.0 * sum(historial) / len(historial)
        for periodo in trimestres[-4:]:
            base = cumplimiento / 20.0        # de 0 a 5
            calidad = min(5.0, max(1.0, az.gauss(base + 0.3, 0.5)))
            tiempo = min(5.0, max(1.0, base))
            precio = min(5.0, max(1.0, az.gauss(3.8, 0.7)))
            servicio = min(5.0, max(1.0, az.gauss(base + 0.2, 0.6)))
            documentacion = min(5.0, max(1.0, az.gauss(base + 0.4, 0.6)))
            puntaje = round(
                (calidad * 0.30 + tiempo * 0.30 + precio * 0.15
                 + servicio * 0.15 + documentacion * 0.10), 2)
            clasificacion = (ClasificacionProveedor.A if puntaje >= 4.3
                             else ClasificacionProveedor.B if puntaje >= 3.6
                             else ClasificacionProveedor.C if puntaje >= 2.8
                             else ClasificacionProveedor.D)
            recomendacion = (RecomendacionProveedor.MANTENER if puntaje >= 4.0
                             else RecomendacionProveedor.MEJORAR if puntaje >= 3.0
                             else RecomendacionProveedor.REEMPLAZAR if puntaje >= 2.2
                             else RecomendacionProveedor.SUSPENDER)
            db.add(ScmEvaluacionProveedor(
                proveedor_id=proveedor.id, evaluador_id=az.choice(usuarios),
                periodo=periodo,
                calidad=round(calidad, 2), tiempo_entrega=round(tiempo, 2),
                precio=round(precio, 2), servicio=round(servicio, 2),
                documentacion=round(documentacion, 2),
                puntaje_total=puntaje, clasificacion=clasificacion,
                comentarios=(
                    f"Cumplimiento en tiempo del {cumplimiento:.0f}% sobre "
                    f"{len(historial)} entregas del período evaluado."),
                recomendacion=recomendacion))
            n_eval += 1
    await db.flush()
    await confirmar()

    return {
        "proveedores": len(proveedores),
        "solicitudes": n_sol, "renglones_solicitud": items_sol,
        "ordenes_compra": n_ord, "renglones_orden": items_ord,
        "evaluaciones": n_eval,
    }


async def verificar(db: AsyncSession) -> dict:
    """Comprueba que el total de cada orden sea la suma de sus renglones.

    Con su descuento y su IVA. Si no cuadra, las cifras de compras son
    decorativas y no se pueden confrontar con la contabilidad.
    """
    descuadres = (await db.execute(text("""
        SELECT count(*) FROM (
          SELECT o.id, o.subtotal, o.impuestos, o.total,
                 COALESCE(SUM(i.total), 0) AS suma
            FROM scm_ordenes_compra o
            LEFT JOIN scm_orden_items i ON i.orden_id = o.id
           GROUP BY o.id, o.subtotal, o.impuestos, o.total
        ) t
        WHERE abs(subtotal - suma) > 1
           OR abs(total - (subtotal + impuestos)) > 1"""))).scalar() or 0
    huerfanas = (await db.execute(text("""
        SELECT count(*) FROM scm_ordenes_compra o
         WHERE o.solicitud_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM scm_solicitudes_compra s
                            WHERE s.id = o.solicitud_id
                              AND s.estado IN ('APROBADA', 'EN_PROCESO',
                                               'COMPLETADA'))"""))).scalar() or 0
    comprado = (await db.execute(text(
        "SELECT COALESCE(SUM(total), 0) FROM scm_ordenes_compra"))).scalar() or 0
    return {
        "ordenes_descuadradas": int(descuadres),
        "ordenes_sin_solicitud_aprobada": int(huerfanas),
        "total_comprado": round(float(comprado), 2),
    }
