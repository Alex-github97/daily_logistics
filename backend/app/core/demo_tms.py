"""
Siembra de volumen para el módulo de transporte (TMS).

QUÉ ES Y QUÉ NO ES
Genera un año de operación de una flota: vehículos, rutas nacionales, viajes con
sus paradas y su rastro de eventos, documentos, prueba de entrega, costos,
liquidación al conductor, OTIF y alertas.

Dos reglas sostienen que estos datos sirvan para decidir:

1. **El costo de un viaje es la suma de sus componentes.** Combustible, peajes,
   viáticos, horas extras, mantenimiento e indirectos se calculan de la
   distancia y del tipo de vehículo; el total es su suma, el costo por kilómetro
   es total/distancia y el margen es flete menos costo. Un sembrador que
   escribiera un «costo total» suelto produce un tablero de rentabilidad que no
   se puede auditar: nadie podría explicar de dónde sale el número.

2. **El OTIF se deriva de las fechas, no se sortea.** `on_time` es que la
   entrega real no pase de la programada, y `in_full` es que se hayan entregado
   todas las paradas. Si el tablero dice 87%, ese 87% se puede recontar viaje
   por viaje.

Las distancias entre ciudades son las reales de la malla vial colombiana. Es lo
que hace que el costo por kilómetro caiga en el rango que un jefe de transporte
reconoce; con distancias inventadas, el indicador estrella del módulo queda
fuera de escala y el lector deja de creer todo lo demás.

DETERMINISTA
Semilla fija: dos corridas producen exactamente los mismos datos.
"""
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.hcm import HCMColaborador, HCMConductor, HCMEmpresa
from app.infrastructure.models.tms import (
    EstadoDocumentoTMSEnum, EstadoLiquidacionTMSEnum, EstadoParadaTMSEnum,
    EstadoVehiculoTMSEnum, EstadoViajeTMSEnum, NivelAlertaTMSEnum,
    TipoAlertaTMSEnum, TipoCarroceriaTMSEnum, TipoDocumentoTMSEnum,
    TipoEventoTMSEnum, TipoParadaTMSEnum, TipoServicioTMSEnum,
    TipoVehiculoTMSEnum, TMSAlerta, TMSCostoViaje, TMSDocumento, TMSEvento,
    TMSKPIDiario, TMSLiquidacion, TMSOTIFRegistro, TMSParada, TMSPOD,
    TMSPuntoRuta, TMSRuta, TMSTipoServicio, TMSVehiculo, TMSViaje, TMSZona,
)

SEMILLA = 20260905

_ESTACIONALIDAD = {
    1: 0.80, 2: 0.86, 3: 1.00, 4: 0.96, 5: 1.04, 6: 1.01,
    7: 1.16, 8: 1.05, 9: 1.02, 10: 1.09, 11: 1.20, 12: 1.32,
}

# Precio del galón de ACPM y rendimiento típico de un tractocamión cargado. De
# estos dos números sale el costo de combustible, que es más de la mitad del
# costo de un viaje: ponerlos acá y no dispersos es lo que permite corregir el
# modelo entero cambiando una línea.
PRECIO_GALON_ACPM = 10_500.0
KM_POR_GALON = {
    TipoVehiculoTMSEnum.TRACTOCAMION: 6.5,
    TipoVehiculoTMSEnum.DOBLE_TROQUE: 9.0,
    TipoVehiculoTMSEnum.CAMION_SENCILLO: 12.0,
    TipoVehiculoTMSEnum.CARROTANQUE: 6.0,
    TipoVehiculoTMSEnum.REFRIGERADO: 7.0,
    TipoVehiculoTMSEnum.PLATAFORMA: 7.5,
    TipoVehiculoTMSEnum.VAN: 16.0,
    TipoVehiculoTMSEnum.CAMIONETA: 18.0,
}

# Peaje promedio por kilómetro en vía nacional, por número de ejes. Es la otra
# mitad del costo variable y varía mucho con la configuración del vehículo.
PEAJE_POR_KM = {2: 62.0, 3: 96.0, 4: 128.0, 5: 168.0, 6: 196.0}


# ─── Geografía ────────────────────────────────────────────────────────────────

# (ciudad, departamento, lat, lng)
_CIUDADES = {
    "Bogotá D.C.":    ("Cundinamarca", 4.7110, -74.0721),
    "Funza":          ("Cundinamarca", 4.7167, -74.2119),
    "Medellín":       ("Antioquia", 6.2442, -75.5812),
    "Cali":           ("Valle del Cauca", 3.4516, -76.5320),
    "Barranquilla":   ("Atlántico", 10.9639, -74.7964),
    "Cartagena":      ("Bolívar", 10.3910, -75.4794),
    "Bucaramanga":    ("Santander", 7.1193, -73.1227),
    "Pereira":        ("Risaralda", 4.8133, -75.6961),
    "Manizales":      ("Caldas", 5.0703, -75.5138),
    "Ibagué":         ("Tolima", 4.4389, -75.2322),
    "Villavicencio":  ("Meta", 4.1420, -73.6266),
    "Neiva":          ("Huila", 2.9273, -75.2819),
    "Santa Marta":    ("Magdalena", 11.2408, -74.1990),
    "Cúcuta":         ("Norte de Santander", 7.8939, -72.5078),
    "Montería":       ("Córdoba", 8.7479, -75.8814),
    "Buenaventura":   ("Valle del Cauca", 3.8801, -77.0312),
}

# Corredores reales, con la distancia por carretera —no en línea recta— y las
# horas que de verdad toma con las restricciones de la vía.
_CORREDORES: List[Tuple[str, str, float, int]] = [
    ("Funza", "Medellín", 415, 600),
    ("Funza", "Cali", 460, 660),
    ("Funza", "Barranquilla", 1000, 1140),
    ("Funza", "Cartagena", 1050, 1200),
    ("Funza", "Bucaramanga", 395, 540),
    ("Funza", "Pereira", 320, 480),
    ("Funza", "Manizales", 290, 450),
    ("Funza", "Ibagué", 200, 300),
    ("Funza", "Villavicencio", 120, 210),
    ("Funza", "Neiva", 300, 420),
    ("Funza", "Cúcuta", 560, 780),
    ("Medellín", "Cali", 420, 570),
    ("Medellín", "Barranquilla", 700, 840),
    ("Medellín", "Cartagena", 640, 780),
    ("Medellín", "Montería", 320, 450),
    ("Medellín", "Pereira", 210, 300),
    ("Cali", "Buenaventura", 125, 180),
    ("Cali", "Pereira", 220, 300),
    ("Barranquilla", "Santa Marta", 95, 120),
    ("Barranquilla", "Cartagena", 130, 150),
    ("Bucaramanga", "Cúcuta", 200, 300),
    ("Funza", "Santa Marta", 950, 1080),
]

_ZONAS = [
    ("Centro", "Cundinamarca, Boyacá y Tolima",
     "Bogotá D.C.|Funza|Ibagué|Villavicencio"),
    ("Antioquia y Eje Cafetero", "Antioquia, Caldas, Risaralda y Quindío",
     "Medellín|Pereira|Manizales"),
    ("Costa Caribe", "Atlántico, Bolívar, Magdalena y Córdoba",
     "Barranquilla|Cartagena|Santa Marta|Montería"),
    ("Suroccidente", "Valle del Cauca, Cauca y Nariño",
     "Cali|Buenaventura"),
    ("Nororiente", "Santander y Norte de Santander",
     "Bucaramanga|Cúcuta"),
    ("Sur", "Huila y Caquetá", "Neiva"),
]

_TIPOS_SERVICIO = [
    ("TN", "Terrestre nacional", TipoServicioTMSEnum.TERRESTRE_NACIONAL),
    ("TR", "Terrestre regional", TipoServicioTMSEnum.TERRESTRE_REGIONAL),
    ("TU", "Terrestre urbano", TipoServicioTMSEnum.TERRESTRE_URBANO),
    ("DI", "Distribución", TipoServicioTMSEnum.DISTRIBUCION),
    ("UM", "Última milla", TipoServicioTMSEnum.ULTIMA_MILLA),
    ("DE", "Dedicado", TipoServicioTMSEnum.DEDICADO),
    ("TE", "Tercerizado", TipoServicioTMSEnum.TERCERIZADO),
]

# (tipo, carrocería, marca, línea, ejes, capacidad kg, cuántos)
_FLOTA = [
    (TipoVehiculoTMSEnum.TRACTOCAMION, TipoCarroceriaTMSEnum.PLANCHA,
     "Kenworth", "T800", 6, 34_000, 8),
    (TipoVehiculoTMSEnum.TRACTOCAMION, TipoCarroceriaTMSEnum.CONTENEDOR,
     "International", "9200i", 6, 34_000, 6),
    (TipoVehiculoTMSEnum.TRACTOCAMION, TipoCarroceriaTMSEnum.FURGON,
     "Freightliner", "Columbia", 6, 32_000, 5),
    (TipoVehiculoTMSEnum.DOBLE_TROQUE, TipoCarroceriaTMSEnum.ESTACAS,
     "Chevrolet", "Kodiak", 3, 17_000, 6),
    (TipoVehiculoTMSEnum.DOBLE_TROQUE, TipoCarroceriaTMSEnum.FURGON,
     "Hino", "FM 2635", 3, 16_000, 4),
    (TipoVehiculoTMSEnum.CAMION_SENCILLO, TipoCarroceriaTMSEnum.FURGON,
     "Chevrolet", "NPR", 2, 5_500, 7),
    (TipoVehiculoTMSEnum.CAMION_SENCILLO, TipoCarroceriaTMSEnum.ESTACAS,
     "Hino", "Dutro", 2, 4_800, 4),
    (TipoVehiculoTMSEnum.REFRIGERADO, TipoCarroceriaTMSEnum.REFRIGERADO_CAR,
     "Isuzu", "FVR", 3, 12_000, 3),
    (TipoVehiculoTMSEnum.CARROTANQUE, TipoCarroceriaTMSEnum.CISTERNA,
     "Kenworth", "T370", 4, 26_000, 2),
    (TipoVehiculoTMSEnum.VAN, TipoCarroceriaTMSEnum.FURGON,
     "Renault", "Master", 2, 1_600, 5),
]

_CLIENTES = [
    "Cervecería Nacional Andina", "Alimentos Sabana SAS", "Retail Express Colombia",
    "Farmacéutica Caribe", "Cementos Cordillera", "Agroindustrias Magdalena",
    "Textiles Antioquia", "Electrodomésticos Pacífico", "Bebidas Orinoquía",
    "Química Industrial Altiplano", "Papelera del Tolima", "Lácteos Guajira",
    "Ferretería Mayorista Nacional", "Distribuidora Amazonía", "Plásticos del Valle",
    "Congelados del Caribe", "Metalmecánica Sabana", "Cosméticos Bogotá SAS",
]

_CARGAS = [
    "Bebidas en estiba", "Alimento procesado refrigerado", "Mercancía general paletizada",
    "Medicamentos con cadena de frío", "Cemento en sacos", "Producto agrícola a granel",
    "Textiles en cajas", "Electrodomésticos", "Insumos químicos clase 8",
    "Papel y cartón", "Lácteos refrigerados", "Ferretería surtida",
    "Envases plásticos", "Congelados", "Estructura metálica", "Cosméticos",
]

_INCIDENTES = [
    ("Retén de policía en la vía", 25), ("Trancón por obra en la vía", 55),
    ("Derrumbe con paso a un carril", 120), ("Falla mecánica menor", 90),
    ("Llanta pinchada", 70), ("Cierre vial programado", 150),
    ("Demora en el turno de cargue", 80), ("Demora en el descargue del cliente", 95),
    ("Manifestación con bloqueo parcial", 180),
]


def _habil(d: date) -> bool:
    return d.weekday() < 5


def _placa(az: random.Random, usadas: set) -> str:
    while True:
        p = (f"{az.choice('STUVWXYZ')}{az.choice('ABCDEFGHJK')}"
             f"{az.choice('ABCDEFGHJK')}{az.randrange(100, 999)}")
        if p not in usadas:
            usadas.add(p)
            return p


def costear(distancia_km: float, *, ejes: int, tipo: TipoVehiculoTMSEnum,
            horas: float, az: random.Random) -> Dict[str, float]:
    """Calcula el costo de un viaje a partir de su distancia y su vehículo.

    Está fuera del generador porque es la parte que tiene que ser defendible: el
    costo por kilómetro es el número por el que un jefe de transporte abre este
    módulo, y tiene que poder rehacerse componente por componente.

    El combustible sale del rendimiento real del tipo de vehículo y del precio
    del galón; el peaje, de los ejes. Los dos juntos son cerca del 70% del costo
    de un viaje nacional, y por eso son los únicos que no se sortean.
    """
    rendimiento = KM_POR_GALON.get(tipo, 8.0)
    combustible = distancia_km / rendimiento * PRECIO_GALON_ACPM
    peajes = distancia_km * PEAJE_POR_KM.get(ejes, 100.0)
    # Los viáticos se pagan por día de ruta, no por kilómetro.
    dias_ruta = max(1, round(horas / 14.0))
    viaticos = dias_ruta * 78_000
    horas_extras = max(0.0, horas - 8.0) * 14_500
    # El mantenimiento se provisiona por kilómetro recorrido: es lo que después
    # permite comparar contra lo que de verdad costó el taller.
    mantenimiento = distancia_km * az.uniform(240, 420)
    indirectos = distancia_km * az.uniform(95, 165)
    total = (combustible + peajes + viaticos + horas_extras
             + mantenimiento + indirectos)
    return {
        "combustible": round(combustible, 2),
        "peajes": round(peajes, 2),
        "viaticos": round(viaticos, 2),
        "horas_extras": round(horas_extras, 2),
        "mantenimiento": round(mantenimiento, 2),
        "costos_indirectos": round(indirectos, 2),
        "costo_total": round(total, 2),
    }


async def sembrar_tms(
    db: AsyncSession, *,
    desde: date,
    hasta: date,
    viajes_por_dia_habil: int = 9,
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera la operación de transporte entre dos fechas."""
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)

    async def confirmar() -> None:
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    usuarios = [f[0] for f in (await db.execute(
        text("SELECT id FROM usuarios ORDER BY id LIMIT 20"))).all()] or [None]

    empresa = (await db.execute(select(HCMEmpresa).limit(1))).scalar_one_or_none()
    if empresa is None:
        raise RuntimeError(
            "No hay empresa en Gestión Humana. Siembre primero el módulo «hcm»: "
            "el TMS asigna sus viajes a conductores, y los conductores viven allá.")
    empresa_id = empresa.id

    conductores = (await db.execute(
        select(HCMConductor, HCMColaborador)
        .join(HCMColaborador, HCMConductor.colaborador_id == HCMColaborador.id)
        .where(HCMConductor.activo_conduccion.is_(True))
    )).all()
    if not conductores:
        raise RuntimeError(
            "No hay conductores activos. Siembre primero el módulo «hcm».")

    # ── Catálogos ──
    avisar("Zonas y tipos de servicio…")
    for nombre, descripcion, ciudades in _ZONAS:
        db.add(TMSZona(nombre=nombre, descripcion=descripcion,
                       ciudades=ciudades, activo=True))
    for codigo, nombre, _ in _TIPOS_SERVICIO:
        db.add(TMSTipoServicio(nombre=nombre, codigo=codigo,
                               descripcion=f"Servicio {nombre.lower()}",
                               activo=True))
    await db.flush()

    # ── Flota ──
    avisar("Flota…")
    vehiculos: List[TMSVehiculo] = []
    placas: set = set()
    for tipo, carroceria, marca, linea, ejes, capacidad, cuantos in _FLOTA:
        for _ in range(cuantos):
            v = TMSVehiculo(
                placa=_placa(az, placas), tipo_vehiculo=tipo,
                tipo_carroceria=carroceria, marca=marca, modelo=linea,
                anio=az.randrange(2013, 2026),
                configuracion=f"{ejes} ejes",
                capacidad_kg=capacidad,
                volumen_m3=round(capacidad * 0.0022, 1),
                num_ejes=ejes,
                peso_bruto_kg=capacidad * 1.55,
                # Una flota real nunca está toda disponible: siempre hay algo en
                # el taller. Con todo disponible, el indicador de utilización no
                # significa nada.
                estado_operativo=az.choices(
                    [EstadoVehiculoTMSEnum.DISPONIBLE,
                     EstadoVehiculoTMSEnum.EN_VIAJE,
                     EstadoVehiculoTMSEnum.EN_MANTENIMIENTO,
                     EstadoVehiculoTMSEnum.FUERA_SERVICIO],
                    weights=[46, 34, 15, 5], k=1)[0],
                empresa_id=empresa_id,
                propietario=az.choices(
                    ["Transportes Demo SAS", None], weights=[72, 28], k=1)[0])
            v._ejes = ejes
            v._capacidad = capacidad
            v._tipo = tipo
            db.add(v)
            vehiculos.append(v)
    await db.flush()

    # ── Rutas ──
    avisar("Rutas…")
    rutas: List[TMSRuta] = []
    for i, (origen, destino, km, minutos) in enumerate(_CORREDORES, start=1):
        servicio = (TipoServicioTMSEnum.TERRESTRE_NACIONAL if km > 250
                    else TipoServicioTMSEnum.TERRESTRE_REGIONAL)
        ruta = TMSRuta(
            nombre=f"{origen} — {destino}", codigo=f"RT-{i:03d}",
            origen=origen, destino=destino, distancia_km=km,
            tiempo_estimado_min=minutos, tipo_servicio=servicio,
            # El costo de referencia se calcula con el mismo modelo que después
            # costea cada viaje. Si fuera un número aparte, la comparación entre
            # lo presupuestado y lo real mediría el error del sembrador.
            costo_referencia=round(costear(
                km, ejes=6, tipo=TipoVehiculoTMSEnum.TRACTOCAMION,
                horas=minutos / 60.0, az=az)["costo_total"], 2),
            activo=True)
        db.add(ruta)
        await db.flush()
        rutas.append(ruta)

        lat_o, lng_o = _CIUDADES[origen][1], _CIUDADES[origen][2]
        lat_d, lng_d = _CIUDADES[destino][1], _CIUDADES[destino][2]
        db.add(TMSPuntoRuta(ruta_id=ruta.id, secuencia=1, ciudad=origen,
                            lat=lat_o, lng=lng_o, tipo=TipoParadaTMSEnum.ORIGEN,
                            tiempo_estimado_minutos=0))
        db.add(TMSPuntoRuta(ruta_id=ruta.id, secuencia=2, ciudad=destino,
                            lat=lat_d, lng=lng_d, tipo=TipoParadaTMSEnum.DESTINO,
                            tiempo_estimado_minutos=minutos))
    await db.flush()
    await confirmar()

    # ── Viajes ──
    avisar("Viajes…")
    n_viaje = n_parada = n_evento = n_doc = n_pod = n_liq = n_alerta = 0
    kpis: List[TMSKPIDiario] = []
    # Unos pocos clientes concentran la carga, como en cualquier transportadora.
    pesos_cliente = [max(0.4, az.gauss(1.0, 0.7)) for _ in _CLIENTES]
    for i in range(3):
        pesos_cliente[i] *= 3.5

    dia = desde
    ultimo_mes = None
    while dia <= hasta:
        if not _habil(dia) and az.random() > 0.35:
            dia += timedelta(days=1)
            continue
        if dia.month != ultimo_mes:
            ultimo_mes = dia.month
            avisar(f"  {dia:%Y-%m}…")
            await confirmar()

        estacion = _ESTACIONALIDAD[dia.month]
        cuantos = max(1, int(round(viajes_por_dia_habil * estacion
                                   * az.uniform(0.75, 1.25))))
        del_dia: List[Tuple[TMSViaje, bool, bool, float]] = []

        for _ in range(cuantos):
            n_viaje += 1
            ruta = az.choice(rutas)
            # El vehículo tiene que caber en el servicio: un furgón de 5 toneladas
            # no hace Funza–Barranquilla con carga completa.
            candidatos = [v for v in vehiculos
                          if (v._capacidad >= 12_000 if ruta.distancia_km > 400
                              else True)]
            vehiculo = az.choice(candidatos or vehiculos)
            conductor, colaborador = az.choice(conductores)
            cliente = az.choices(_CLIENTES, weights=pesos_cliente, k=1)[0]

            horas = ruta.tiempo_estimado_min / 60.0
            salida = datetime.combine(
                dia, time(az.randrange(4, 12), az.choice([0, 15, 30, 45])),
                tzinfo=timezone.utc)
            entrega_programada = salida + timedelta(hours=horas + 3)

            # Un 13% llega tarde. Ese número es el que sostiene el OTIF, y por
            # eso se declara acá y no se esconde en una fórmula.
            atraso_horas = 0.0
            if az.random() < 0.13:
                atraso_horas = az.uniform(1.5, 26.0)
            entrega_real = entrega_programada + timedelta(hours=atraso_horas)

            # Y un 5% no entrega todo: faltó una parada o parte de la carga.
            completo = az.random() > 0.05
            en_curso = entrega_real.date() > hasta

            peso = round(vehiculo._capacidad * az.uniform(0.55, 0.98), 1)
            costos = costear(ruta.distancia_km, ejes=vehiculo._ejes,
                             tipo=vehiculo._tipo, horas=horas, az=az)
            # El flete se cobra con un margen sobre el costo, con dispersión: hay
            # rutas que se pierden. Un módulo de rentabilidad donde todo gana lo
            # mismo no le sirve a nadie para decidir qué ruta dejar de hacer.
            margen_objetivo = az.gauss(0.19, 0.11)
            flete = round(costos["costo_total"] * (1 + margen_objetivo), 2)

            origen_dep, origen_lat, origen_lng = _CIUDADES[ruta.origen]
            destino_dep, destino_lat, destino_lng = _CIUDADES[ruta.destino]

            viaje = TMSViaje(
                codigo=f"VJ-{dia:%Y}-{n_viaje:06d}",
                tipo_servicio=ruta.tipo_servicio,
                # Lo entregado hace poco todavía no se ha cerrado: cerrar es
                # un trámite que toma días. Con todo CERRADO no habría ningún
                # viaje pendiente de liquidar, y esa bandeja nunca está vacía.
                estado=(EstadoViajeTMSEnum.EN_TRANSITO if en_curso
                        else EstadoViajeTMSEnum.ENTREGADO
                        if (hasta - entrega_real.date()).days <= 18
                        else EstadoViajeTMSEnum.CERRADO),
                vehiculo_id=vehiculo.id, conductor_hcm_id=conductor.id,
                empresa_id=empresa_id,
                origen_ciudad=ruta.origen,
                origen_direccion=f"Centro logístico {ruta.origen}",
                origen_lat=origen_lat, origen_lng=origen_lng,
                destino_ciudad=ruta.destino,
                destino_direccion=f"Bodega de {cliente} · {ruta.destino}",
                destino_lat=destino_lat, destino_lng=destino_lng,
                fecha_programada_cargue=salida - timedelta(hours=2),
                fecha_real_cargue=salida,
                fecha_programada_entrega=entrega_programada,
                fecha_real_entrega=None if en_curso else entrega_real,
                distancia_km=ruta.distancia_km, peso_kg=peso,
                volumen_m3=round(peso * 0.0022, 2),
                num_entregas=az.choices([1, 2, 3], weights=[72, 20, 8], k=1)[0],
                descripcion_carga=f"{az.choice(_CARGAS)} para {cliente}",
                valor_flete=flete,
                otif_on_time=None if en_curso else (atraso_horas <= 0),
                otif_in_full=None if en_curso else completo,
                notas=None, creado_por_id=az.choice(usuarios),
                created_at=salida)
            db.add(viaje)
            await db.flush()

            # ── Paradas ──
            db.add(TMSParada(
                viaje_id=viaje.id, secuencia=1, tipo=TipoParadaTMSEnum.ORIGEN,
                ciudad=ruta.origen, direccion=f"Centro logístico {ruta.origen}",
                lat=origen_lat, lng=origen_lng,
                estado=EstadoParadaTMSEnum.COMPLETADA,
                tiempo_estimado_llegada=salida - timedelta(hours=2),
                tiempo_real_llegada=salida - timedelta(hours=az.uniform(0.5, 2.5)),
                tiempo_estimado_salida=salida, tiempo_real_salida=salida,
                contacto="Coordinación de patio", telefono_contacto="6018765432"))
            n_parada += 1

            intermedias = viaje.num_entregas - 1
            for k in range(intermedias):
                fraccion = (k + 1) / (intermedias + 1)
                momento = salida + timedelta(hours=horas * fraccion)
                ciudad_int = az.choice([c for c in _CIUDADES
                                        if c not in (ruta.origen, ruta.destino)])
                dep_i, lat_i, lng_i = _CIUDADES[ciudad_int]
                db.add(TMSParada(
                    viaje_id=viaje.id, secuencia=k + 2,
                    tipo=TipoParadaTMSEnum.PARADA_INTERMEDIA, ciudad=ciudad_int,
                    direccion=f"Punto de entrega · {ciudad_int}",
                    lat=lat_i, lng=lng_i,
                    estado=(EstadoParadaTMSEnum.PENDIENTE if en_curso
                            else EstadoParadaTMSEnum.COMPLETADA
                            if completo else EstadoParadaTMSEnum.SALTADA),
                    tiempo_estimado_llegada=momento,
                    tiempo_real_llegada=None if en_curso else momento,
                    tiempo_estimado_salida=momento + timedelta(minutes=45),
                    tiempo_real_salida=None if en_curso
                                       else momento + timedelta(minutes=45),
                    contacto=f"Recepción {ciudad_int}",
                    telefono_contacto=f"60{az.randrange(1000000, 9999999)}"))
                n_parada += 1

            db.add(TMSParada(
                viaje_id=viaje.id, secuencia=viaje.num_entregas + 1,
                tipo=TipoParadaTMSEnum.DESTINO, ciudad=ruta.destino,
                direccion=f"Bodega de {cliente} · {ruta.destino}",
                lat=destino_lat, lng=destino_lng,
                estado=(EstadoParadaTMSEnum.EN_CURSO if en_curso
                        else EstadoParadaTMSEnum.COMPLETADA),
                tiempo_estimado_llegada=entrega_programada,
                tiempo_real_llegada=None if en_curso else entrega_real,
                tiempo_estimado_salida=entrega_programada + timedelta(hours=1),
                tiempo_real_salida=None if en_curso
                                   else entrega_real + timedelta(hours=1),
                contacto=f"Almacén {cliente}",
                telefono_contacto=f"60{az.randrange(1000000, 9999999)}"))
            n_parada += 1

            # ── Rastro del viaje ──
            # Los puntos de GPS se interpolan sobre la recta origen–destino. No
            # es la ruta real por carretera, y por eso el mapa muestra el avance
            # y no promete un trazado que no se calculó.
            db.add(TMSEvento(
                viaje_id=viaje.id, tipo_evento=TipoEventoTMSEnum.SALIDA_ORIGEN,
                descripcion=f"Salida de {ruta.origen} con {peso:,.0f} kg",
                lat=origen_lat, lng=origen_lng, velocidad_kmh=0,
                timestamp=salida, registrado_por_id=az.choice(usuarios)))
            n_evento += 1

            puntos = 6 if ruta.distancia_km > 400 else 3
            for k in range(1, puntos + 1):
                f = k / (puntos + 1)
                momento = salida + timedelta(hours=horas * f)
                if momento.date() > hasta:
                    break
                db.add(TMSEvento(
                    viaje_id=viaje.id,
                    tipo_evento=TipoEventoTMSEnum.ACTUALIZACION_GPS,
                    descripcion=None,
                    lat=round(origen_lat + (destino_lat - origen_lat) * f, 5),
                    lng=round(origen_lng + (destino_lng - origen_lng) * f, 5),
                    velocidad_kmh=round(az.uniform(38, 82), 1),
                    timestamp=momento, registrado_por_id=None))
                n_evento += 1

            if atraso_horas > 0:
                motivo, minutos_perdidos = az.choice(_INCIDENTES)
                db.add(TMSEvento(
                    viaje_id=viaje.id, tipo_evento=TipoEventoTMSEnum.RETRASO,
                    descripcion=f"{motivo} · {minutos_perdidos} min de demora",
                    lat=round((origen_lat + destino_lat) / 2, 5),
                    lng=round((origen_lng + destino_lng) / 2, 5),
                    velocidad_kmh=0,
                    timestamp=salida + timedelta(hours=horas * 0.6),
                    registrado_por_id=az.choice(usuarios)))
                n_evento += 1
                db.add(TMSAlerta(
                    tipo=TipoAlertaTMSEnum.RETRASO_VIAJE,
                    nivel=(NivelAlertaTMSEnum.CRITICA if atraso_horas > 12
                           else NivelAlertaTMSEnum.ALTA if atraso_horas > 5
                           else NivelAlertaTMSEnum.MEDIA),
                    mensaje=f"{viaje.codigo} llega con {atraso_horas:.1f} h de "
                            f"atraso a {ruta.destino}: {motivo.lower()}",
                    viaje_id=viaje.id, vehiculo_id=vehiculo.id,
                    conductor_id=conductor.id,
                    leida=(True if (hasta - dia).days > 20
                           else az.random() < 0.45),
                    fecha_alerta=salida + timedelta(hours=horas * 0.6)))
                n_alerta += 1

            if not en_curso:
                db.add(TMSEvento(
                    viaje_id=viaje.id,
                    tipo_evento=TipoEventoTMSEnum.LLEGADA_DESTINO,
                    descripcion=f"Llegada a {ruta.destino}",
                    lat=destino_lat, lng=destino_lng, velocidad_kmh=0,
                    timestamp=entrega_real, registrado_por_id=az.choice(usuarios)))
                n_evento += 1

            # ── Documentos ──
            for tipo_doc, prefijo in ((TipoDocumentoTMSEnum.REMESA, "REM"),
                                      (TipoDocumentoTMSEnum.MANIFIESTO, "MAN")):
                db.add(TMSDocumento(
                    viaje_id=viaje.id, tipo_documento=tipo_doc,
                    numero=f"{prefijo}-{dia:%Y}-{n_viaje:06d}",
                    fecha_emision=dia,
                    estado=EstadoDocumentoTMSEnum.FIRMADO,
                    observaciones=None))
                n_doc += 1
            if not en_curso:
                db.add(TMSDocumento(
                    viaje_id=viaje.id,
                    tipo_documento=TipoDocumentoTMSEnum.CUMPLIDO,
                    numero=f"CUM-{dia:%Y}-{n_viaje:06d}",
                    fecha_emision=entrega_real.date(),
                    estado=(EstadoDocumentoTMSEnum.FIRMADO if completo
                            else EstadoDocumentoTMSEnum.PENDIENTE),
                    observaciones=None if completo
                                  else "Falta cumplido de una de las entregas"))
                n_doc += 1

                # ── Prueba de entrega ──
                db.add(TMSPOD(
                    viaje_id=viaje.id,
                    receptor_nombre=f"Almacén {cliente}",
                    receptor_documento=str(az.randrange(10_000_000, 1_099_999_999)),
                    lat=destino_lat, lng=destino_lng,
                    fecha_hora=entrega_real,
                    observaciones=None if completo
                                  else "Se recibe parcial; pendiente una entrega",
                    registrado_por_id=az.choice(usuarios)))
                n_pod += 1

            # ── Costos ──
            db.add(TMSCostoViaje(
                viaje_id=viaje.id, **costos,
                valor_flete_cobrado=flete,
                costo_por_km=round(costos["costo_total"] / ruta.distancia_km, 2),
                costo_por_entrega=round(costos["costo_total"] / viaje.num_entregas, 2),
                margen=round(flete - costos["costo_total"], 2),
                notas=None))

            # ── Liquidación al conductor ──
            if not en_curso:
                # El conductor gana un porcentaje del flete, más bonificación por
                # entrega a tiempo y menos los anticipos que ya recibió en ruta.
                base = round(flete * az.uniform(0.10, 0.16), 2)
                bonificacion = round(base * 0.08, 2) if atraso_horas <= 0 else 0.0
                anticipos = round(costos["viaticos"], 2)
                descuentos = round(base * 0.05, 2) if az.random() < 0.12 else 0.0
                db.add(TMSLiquidacion(
                    viaje_id=viaje.id, conductor_hcm_id=conductor.id,
                    periodo=f"{entrega_real:%Y-%m}",
                    valor_flete=base, bonificaciones=bonificacion,
                    descuentos=descuentos, anticipos=anticipos,
                    total_a_pagar=round(base + bonificacion - descuentos - anticipos, 2),
                    estado=az.choices(
                        [EstadoLiquidacionTMSEnum.PAGADA,
                         EstadoLiquidacionTMSEnum.APROBADA,
                         EstadoLiquidacionTMSEnum.PENDIENTE,
                         EstadoLiquidacionTMSEnum.BORRADOR],
                        weights=[68, 16, 11, 5], k=1)[0],
                    pagado_en=entrega_real + timedelta(days=az.randrange(3, 20)),
                    aprobado_por_id=az.choice(usuarios), notas=None))
                n_liq += 1

                # ── Registro OTIF ──
                db.add(TMSOTIFRegistro(
                    viaje_id=viaje.id, fecha=entrega_real.date(),
                    on_time=(atraso_horas <= 0), in_full=completo,
                    otif=(atraso_horas <= 0 and completo),
                    cliente=cliente, ruta=ruta.nombre,
                    observaciones=None if atraso_horas <= 0
                                  else f"Atraso de {atraso_horas:.1f} h"))

            del_dia.append((viaje, atraso_horas <= 0, completo,
                            ruta.distancia_km))

        # ── Indicadores del día, calculados de los viajes ──
        cerrados = [(v, t, f, km) for v, t, f, km in del_dia
                    if v.estado in (EstadoViajeTMSEnum.CERRADO,
                                    EstadoViajeTMSEnum.ENTREGADO)]
        if del_dia:
            total = len(cerrados) or 1
            on_time = sum(1 for _, t, _, _ in cerrados if t)
            in_full = sum(1 for _, _, f, _ in cerrados if f)
            otif = sum(1 for _, t, f, _ in cerrados if t and f)
            km_total = sum(km for _, _, _, km in del_dia)
            costo_km = sum(v.valor_flete or 0 for v, _, _, _ in del_dia) / max(1, km_total)
            kpis.append(TMSKPIDiario(
                empresa_id=empresa_id, fecha=dia,
                viajes_programados=len(del_dia),
                viajes_completados=len(cerrados), viajes_cancelados=0,
                on_time_rate=round(100.0 * on_time / total, 2),
                in_full_rate=round(100.0 * in_full / total, 2),
                otif_rate=round(100.0 * otif / total, 2),
                costo_promedio_km=round(costo_km, 2),
                km_recorridos=round(km_total, 1),
                # Los kilómetros vacíos son el retorno sin carga. Es el
                # desperdicio que este módulo existe para reducir, así que tiene
                # que estar y no puede ser cero.
                km_vacios=round(km_total * az.uniform(0.14, 0.31), 1),
                utilizacion_flota=round(
                    100.0 * min(len(del_dia), len(vehiculos)) / len(vehiculos), 2),
                conductores_activos=len({v.conductor_hcm_id for v, _, _, _ in del_dia})))
        dia += timedelta(days=1)

    db.add_all(kpis)
    await db.flush()
    await confirmar()

    # ── La programación de los próximos días ──
    # Una transportadora sabe hoy lo que sale mañana. Sin estos viajes el tablero
    # dice «0 viajes programados», que se lee como que la operación se detuvo.
    avisar("Programación…")
    n_programados = 0
    for adelanto in range(1, 5):
        futuro = hasta + timedelta(days=adelanto)
        if not _habil(futuro):
            continue
        for _ in range(az.randrange(5, 11)):
            n_viaje += 1
            n_programados += 1
            ruta = az.choice(rutas)
            vehiculo = az.choice([v for v in vehiculos
                                  if v.estado_operativo != EstadoVehiculoTMSEnum.FUERA_SERVICIO]
                                 or vehiculos)
            conductor, _colab = az.choice(conductores)
            cliente = az.choices(_CLIENTES, weights=pesos_cliente, k=1)[0]
            horas = ruta.tiempo_estimado_min / 60.0
            cargue = datetime.combine(
                futuro, time(az.randrange(4, 12), az.choice([0, 30])),
                tzinfo=timezone.utc)
            peso = round(vehiculo._capacidad * az.uniform(0.55, 0.98), 1)
            costos = costear(ruta.distancia_km, ejes=vehiculo._ejes,
                             tipo=vehiculo._tipo, horas=horas, az=az)
            flete = round(costos["costo_total"] * (1 + az.gauss(0.19, 0.11)), 2)
            _dep_o, lat_o, lng_o = _CIUDADES[ruta.origen]
            _dep_d, lat_d, lng_d = _CIUDADES[ruta.destino]
            viaje = TMSViaje(
                codigo=f"VJ-{futuro:%Y}-{n_viaje:06d}",
                tipo_servicio=ruta.tipo_servicio,
                # ASIGNADO cuando ya tiene vehículo y conductor; PROGRAMADO
                # cuando todavía está por asignar. Los dos estados existen y el
                # tablero de planeación distingue entre ellos.
                estado=az.choices([EstadoViajeTMSEnum.PROGRAMADO,
                                   EstadoViajeTMSEnum.ASIGNADO],
                                  weights=[42, 58], k=1)[0],
                vehiculo_id=vehiculo.id, conductor_hcm_id=conductor.id,
                empresa_id=empresa_id,
                origen_ciudad=ruta.origen,
                origen_direccion=f"Centro logístico {ruta.origen}",
                origen_lat=lat_o, origen_lng=lng_o,
                destino_ciudad=ruta.destino,
                destino_direccion=f"Bodega de {cliente} · {ruta.destino}",
                destino_lat=lat_d, destino_lng=lng_d,
                fecha_programada_cargue=cargue,
                fecha_programada_entrega=cargue + timedelta(hours=horas + 3),
                distancia_km=ruta.distancia_km, peso_kg=peso,
                volumen_m3=round(peso * 0.0022, 2),
                num_entregas=az.choices([1, 2], weights=[80, 20], k=1)[0],
                descripcion_carga=f"{az.choice(_CARGAS)} para {cliente}",
                valor_flete=flete, creado_por_id=az.choice(usuarios),
                created_at=datetime.combine(hasta, time(16, 0), tzinfo=timezone.utc))
            db.add(viaje)
            await db.flush()
            db.add(TMSParada(
                viaje_id=viaje.id, secuencia=1, tipo=TipoParadaTMSEnum.ORIGEN,
                ciudad=ruta.origen, direccion=f"Centro logístico {ruta.origen}",
                lat=lat_o, lng=lng_o, estado=EstadoParadaTMSEnum.PENDIENTE,
                tiempo_estimado_llegada=cargue - timedelta(hours=2),
                tiempo_estimado_salida=cargue,
                contacto="Coordinación de patio", telefono_contacto="6018765432"))
            db.add(TMSParada(
                viaje_id=viaje.id, secuencia=2, tipo=TipoParadaTMSEnum.DESTINO,
                ciudad=ruta.destino,
                direccion=f"Bodega de {cliente} · {ruta.destino}",
                lat=lat_d, lng=lng_d, estado=EstadoParadaTMSEnum.PENDIENTE,
                tiempo_estimado_llegada=cargue + timedelta(hours=horas + 3),
                tiempo_estimado_salida=cargue + timedelta(hours=horas + 4),
                contacto=f"Almacén {cliente}",
                telefono_contacto=f"60{az.randrange(1000000, 9999999)}"))
            n_parada += 2
            db.add(TMSCostoViaje(
                viaje_id=viaje.id, **costos, valor_flete_cobrado=flete,
                costo_por_km=round(costos["costo_total"] / ruta.distancia_km, 2),
                costo_por_entrega=round(costos["costo_total"] / viaje.num_entregas, 2),
                margen=round(flete - costos["costo_total"], 2),
                notas="Costo presupuestado; el viaje no ha salido"))
    await db.flush()
    await confirmar()

    # ── Alertas que no vienen de un viaje ──
    avisar("Alertas de flota…")
    for v in vehiculos:
        if v.estado_operativo == EstadoVehiculoTMSEnum.FUERA_SERVICIO:
            db.add(TMSAlerta(
                tipo=TipoAlertaTMSEnum.VEHICULO_FUERA_SERVICIO,
                nivel=NivelAlertaTMSEnum.ALTA,
                mensaje=f"{v.placa} está fuera de servicio y no puede programarse",
                vehiculo_id=v.id, leida=False,
                fecha_alerta=datetime.combine(hasta, time(6, 0), tzinfo=timezone.utc)))
            n_alerta += 1
    for conductor, colaborador in conductores:
        dias = (conductor.fecha_vencimiento_licencia - hasta).days
        if dias > 60:
            continue
        db.add(TMSAlerta(
            tipo=TipoAlertaTMSEnum.VENCIMIENTO_DOCUMENTO,
            nivel=(NivelAlertaTMSEnum.CRITICA if dias < 0
                   else NivelAlertaTMSEnum.ALTA if dias <= 15
                   else NivelAlertaTMSEnum.MEDIA),
            mensaje=(f"Licencia de {colaborador.nombres} {colaborador.apellidos} "
                     + (f"vencida hace {abs(dias)} días" if dias < 0
                        else f"vence en {dias} días")),
            conductor_id=conductor.id, leida=False,
            fecha_alerta=datetime.combine(hasta, time(6, 30), tzinfo=timezone.utc)))
        n_alerta += 1
    await db.flush()
    await confirmar()

    return {
        "vehiculos": len(vehiculos), "rutas": len(rutas), "zonas": len(_ZONAS),
        "viajes": n_viaje, "paradas": n_parada, "eventos": n_evento,
        "documentos": n_doc, "pruebas_entrega": n_pod,
        "programados": n_programados,
        "liquidaciones": n_liq, "alertas": n_alerta,
        "dias_con_indicadores": len(kpis),
    }


async def verificar(db: AsyncSession) -> dict:
    """Comprueba las dos reglas del módulo.

    Que el costo total de cada viaje sea la suma de sus componentes, y que el
    OTIF registrado coincida con lo que dicen las fechas. Si alguna falla, el
    tablero de rentabilidad y el de cumplimiento son decorativos.
    """
    costos_malos = (await db.execute(text("""
        SELECT count(*) FROM tms_costo_viaje
         WHERE abs(costo_total - (combustible + peajes + viaticos
               + horas_extras + mantenimiento + costos_indirectos)) > 1"""))).scalar() or 0
    otif_malos = (await db.execute(text("""
        SELECT count(*)
          FROM tms_otif_registro o
          JOIN tms_viaje v ON v.id = o.viaje_id
         WHERE o.on_time <> (v.fecha_real_entrega <= v.fecha_programada_entrega)
            OR o.otif <> (o.on_time AND o.in_full)"""))).scalar() or 0
    km_malos = (await db.execute(text(
        "SELECT count(*) FROM tms_kpi_diario WHERE km_vacios > km_recorridos"))).scalar() or 0
    margen = (await db.execute(text(
        "SELECT COALESCE(SUM(margen), 0) FROM tms_costo_viaje"))).scalar() or 0
    facturado = (await db.execute(text(
        "SELECT COALESCE(SUM(valor_flete_cobrado), 0) FROM tms_costo_viaje"))).scalar() or 0
    return {
        "costos_descuadrados": int(costos_malos),
        "otif_descuadrados": int(otif_malos),
        "kpis_descuadrados": int(km_malos),
        "flete_facturado": round(float(facturado), 2),
        "margen_total": round(float(margen), 2),
    }
