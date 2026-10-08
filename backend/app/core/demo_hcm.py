"""
Siembra de volumen para Gestión Humana (HCM).

QUÉ ES Y QUÉ NO ES
Genera la planta de una empresa de transporte —estructura, contratos,
conductores con licencia, nómina mes a mes, novedades, incapacidades,
vacaciones, capacitación, evaluaciones, SST y vacantes— para un año.

La regla que hace utilizables estos datos: **la nómina se liquida, no se
inventa**. Salud y pensión son el 4% cada una sobre el devengado sujeto, el
fondo de solidaridad aplica desde 4 salarios mínimos, y el auxilio de transporte
solo se paga hasta 2 salarios mínimos. El neto es devengado menos deducido, y el
total del período es la suma de sus detalles. Un sembrador que escribiera
importes al azar produce una nómina que no cuadra con nada, y el primer contador
que la mire lo ve en un minuto.

Los conductores importan más allá de este módulo: el TMS los necesita para
asignar viajes, así que acá se crean con licencia, categoría y vencimiento
—incluidas algunas por vencer, que es lo que le da algo que mostrar al tablero
de alertas.

DETERMINISTA
Semilla fija: dos corridas producen exactamente los mismos datos.
"""
import random
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.hcm import (
    EstadoCapacitacionEnum, EstadoLaboralEnum, EstadoNominaEnum,
    EstadoVacanteEnum, GeneroEnum, HCMArea, HCMCapacitacion, HCMCargo,
    HCMCentroCosto, HCMColaborador, HCMColaboradorCapacitacion, HCMConductor,
    HCMContrato, HCMEmpresa, HCMEvaluacion, HCMIncapacidad, HCMKPIDiario,
    HCMNominaDetalle, HCMNominaPeriodo, HCMNovedad, HCMSede, HCMSSTIncidente,
    HCMSSTInspeccion, HCMSSTRiesgo, HCMVacacion, HCMVacante, TipoContratoEnum,
    TipoDocumentoEnum, TipoEvaluacionEnum, TipoIncapacidadEnum,
    TipoLicenciaEnum, TipoNovedadEnum, TipoSSTEnum,
)

SEMILLA = 20260904

# Salario mínimo y auxilio de transporte de 2026. Van acá y no repartidos por el
# código porque de estos dos números cuelga toda la liquidación.
SMLV = 1_623_500.0
AUXILIO_TRANSPORTE = 200_000.0

# Los topes de la ley: el auxilio se paga hasta 2 salarios mínimos, y el fondo de
# solidaridad pensional arranca en 4.
TOPE_AUXILIO = 2 * SMLV
TOPE_SOLIDARIDAD = 4 * SMLV


# ─── Vocabulario ──────────────────────────────────────────────────────────────

_NOMBRES_M = ["Andrés", "Carlos", "Diego", "Édinson", "Fabián", "Gustavo",
              "Héctor", "Iván", "Jairo", "Kevin", "Luis", "Mauricio", "Nelson",
              "Óscar", "Pedro", "Ramiro", "Sebastián", "Tomás", "Uriel",
              "Wilson", "Yeison", "Álvaro", "Jhon", "Duván", "Fredy"]
_NOMBRES_F = ["Adriana", "Beatriz", "Carolina", "Diana", "Elena", "Fernanda",
              "Gloria", "Helena", "Isabel", "Juliana", "Katherine", "Lorena",
              "Marcela", "Natalia", "Olga", "Paola", "Rocío", "Sandra",
              "Tatiana", "Viviana", "Yesenia", "Ángela", "Claudia"]
_APELLIDOS = ["Ramírez", "González", "Rodríguez", "Martínez", "Cárdenas",
              "Ospina", "Quintero", "Valencia", "Betancur", "Mejía", "Salazar",
              "Rincón", "Peláez", "Zapata", "Arango", "Cifuentes", "Bedoya",
              "Restrepo", "Guzmán", "Sánchez", "Torres", "Moreno", "Vargas",
              "Castaño", "Herrera", "Jiménez", "Nieto", "Pineda", "Rojas",
              "Suárez", "Camacho", "Duarte", "Escobar", "Forero", "Galvis"]

_SEDES = [
    ("Sede Principal Funza", "Funza", "Cundinamarca",
     "Km 2 Vía Siberia–Funza, Parque Industrial"),
    ("CEDI Medellín", "Medellín", "Antioquia", "Calle 10 Sur #50-120, Guayabal"),
    ("Punto Barranquilla", "Barranquilla", "Atlántico", "Vía 40 #73-290"),
]

# (área, cargos con su rango salarial en salarios mínimos y su peso en la planta)
_ESTRUCTURA = {
    "Operaciones": [
        ("Conductor de tractocamión", 2.2, 3.4, 34),
        ("Conductor de camión sencillo", 1.8, 2.6, 14),
        ("Auxiliar de patio", 1.0, 1.4, 6),
        ("Coordinador de operaciones", 3.4, 5.0, 3),
        ("Jefe de operaciones", 6.0, 8.5, 1),
    ],
    "Almacén": [
        ("Auxiliar de bodega", 1.0, 1.5, 12),
        ("Operario de montacargas", 1.3, 1.9, 5),
        ("Coordinador de almacén", 3.0, 4.5, 2),
    ],
    "Mantenimiento": [
        ("Técnico mecánico", 1.6, 2.6, 7),
        ("Técnico eléctrico automotriz", 1.7, 2.7, 3),
        ("Jefe de mantenimiento", 5.5, 8.0, 1),
    ],
    "Administración": [
        ("Auxiliar administrativo", 1.1, 1.7, 5),
        ("Analista de nómina", 2.4, 3.6, 2),
        ("Contador", 4.5, 7.0, 1),
        ("Gerente administrativo", 9.0, 14.0, 1),
    ],
    "Comercial": [
        ("Ejecutivo comercial", 2.2, 3.8, 4),
        ("Gerente comercial", 8.0, 13.0, 1),
    ],
    "Seguridad y Salud": [
        ("Analista SST", 2.6, 3.8, 2),
        ("Coordinador SST", 4.0, 5.5, 1),
    ],
}

_CENTROS_COSTO = [
    ("CC-100", "Transporte terrestre"), ("CC-200", "Almacenamiento"),
    ("CC-300", "Mantenimiento de flota"), ("CC-400", "Administración"),
    ("CC-500", "Comercial"),
]

_CAPACITACIONES = [
    ("Manejo defensivo", "TECNICA", 16, True, True),
    ("Mercancías peligrosas", "NORMATIVA", 24, True, True),
    ("Trabajo en alturas", "SST", 40, True, False),
    ("Manipulación de montacargas", "TECNICA", 20, True, False),
    ("Inducción y reinducción", "INDUCCION", 8, True, False),
    ("Primeros auxilios", "SST", 12, False, False),
    ("Atención al cliente", "BLANDA", 8, False, False),
    ("Seguridad vial y fatiga", "SST", 10, True, True),
]

_RIESGOS_SST = [
    ("Vía pública", "Accidente de tránsito en ruta nacional", 4, 5),
    ("Zona de cargue", "Atrapamiento entre vehículo y muelle", 3, 5),
    ("Bodega", "Caída de mercancía almacenada en altura", 3, 4),
    ("Taller", "Contacto con sustancias químicas (aceites, solventes)", 3, 3),
    ("Taller", "Quemadura por superficie caliente del motor", 2, 3),
    ("Montacargas", "Volcamiento del equipo por sobrecarga", 2, 5),
    ("Oficinas", "Trastorno musculoesquelético por postura", 4, 2),
    ("Vía pública", "Atraco o piratería terrestre", 3, 5),
    ("Bodega", "Ruido continuo por operación de equipos", 3, 2),
    ("Zona de cargue", "Sobreesfuerzo por manipulación manual de carga", 4, 3),
]

_INCIDENTES_SST = [
    (TipoSSTEnum.CASI_ACCIDENTE, "Vehículo invade el carril durante adelantamiento en la vía Bogotá–Girardot", 0),
    (TipoSSTEnum.INCIDENTE, "Derrame de aceite en el foso del taller sin lesionados", 0),
    (TipoSSTEnum.ACCIDENTE, "Golpe en la mano al cerrar la compuerta del furgón", 3),
    (TipoSSTEnum.ACCIDENTE, "Caída a nivel en zona de cargue por piso húmedo", 5),
    (TipoSSTEnum.CASI_ACCIDENTE, "Montacargas frena a destiempo cerca de personal en pasillo", 0),
    (TipoSSTEnum.INCIDENTE, "Estiba se desprende al retirarla del rack, sin personas cerca", 0),
    (TipoSSTEnum.ACCIDENTE, "Lumbalgia por levantamiento manual de bulto de 40 kg", 8),
    (TipoSSTEnum.ACCIDENTE, "Colisión leve por alcance en el peaje de Chusacá", 2),
]

# El contenedor corre con la configuración regional C, así que `%B` devuelve
# «september». Los meses van escritos porque una nómina que dice «Nómina
# september 2026» delata que nadie miró la pantalla.
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_DIAGNOSTICOS = [
    "Lumbalgia mecánica", "Síndrome gripal", "Gastroenteritis aguda",
    "Esguince de tobillo grado I", "Cefalea tensional",
    "Contusión en mano derecha", "Faringitis aguda", "Dolor cervical",
]


def _habil(d: date) -> bool:
    return d.weekday() < 5


def _cedula(az: random.Random) -> str:
    return str(az.randrange(8_000_000, 1_099_999_999))


def _redondear(v: float) -> float:
    """A pesos completos. La nómina no lleva centavos."""
    return float(round(v))


def liquidar(
    salario_base: float, *,
    dias: int = 30,
    horas_extras: float = 0.0,
    recargo_nocturno: float = 0.0,
    dominicales: float = 0.0,
    festivos: float = 0.0,
    bonificaciones: float = 0.0,
    comisiones: float = 0.0,
    viaticos: float = 0.0,
    embargo: float = 0.0,
    otros_descuentos: float = 0.0,
) -> Dict[str, float]:
    """Liquida un detalle de nómina con las reglas colombianas.

    Está fuera del sembrador a propósito: es la parte que tiene que ser correcta
    aunque los nombres y las fechas sean inventados. Lo que devuelve cuadra —el
    neto es el devengado menos el deducido, siempre— y por eso los totales del
    período se pueden sumar y comparar contra la contabilidad.

    Lo que no es obvio y suele salir mal:

    - El auxilio de transporte NO es salario: entra al devengado pero no a la
      base de salud y pensión. Meterlo en la base infla los aportes de toda la
      planta operativa, que es justo la que lo recibe.
    - Los viáticos ocasionales tampoco son base de aportes.
    - El fondo de solidaridad solo aplica desde 4 salarios mínimos, y es del
      trabajador. Aplicarlo a todos es un error caro y silencioso.
    """
    proporcional = salario_base * dias / 30.0
    auxilio = (AUXILIO_TRANSPORTE * dias / 30.0
               if salario_base <= TOPE_AUXILIO else 0.0)

    # Base de aportes: lo salarial. Ni auxilio de transporte ni viáticos.
    base_aportes = (proporcional + horas_extras + recargo_nocturno
                    + dominicales + festivos + comisiones)
    devengado = base_aportes + bonificaciones + viaticos + auxilio

    salud = base_aportes * 0.04
    pension = base_aportes * 0.04
    solidaridad = base_aportes * 0.01 if base_aportes >= TOPE_SOLIDARIDAD else 0.0

    # Retención de la fuente: solo por encima de un umbral alto. Se aproxima con
    # una tasa marginal suave; no pretende reemplazar la depuración completa, y
    # por eso no se presenta como una cifra fiscal sino operativa.
    retencion = 0.0
    if base_aportes > 4_500_000:
        retencion = (base_aportes - 4_500_000) * 0.10

    deducido = salud + pension + solidaridad + retencion + embargo + otros_descuentos
    return {
        "salario_base": _redondear(proporcional),
        "horas_extras": _redondear(horas_extras),
        "recargo_nocturno": _redondear(recargo_nocturno),
        "dominicales": _redondear(dominicales),
        "festivos": _redondear(festivos),
        "bonificaciones": _redondear(bonificaciones),
        "comisiones": _redondear(comisiones),
        "viaticos": _redondear(viaticos),
        "auxilio_transporte": _redondear(auxilio),
        "otros_devengados": 0.0,
        "total_devengado": _redondear(devengado),
        "salud": _redondear(salud),
        "pension": _redondear(pension),
        "fondo_solidaridad": _redondear(solidaridad),
        "retencion_fuente": _redondear(retencion),
        "embargo": _redondear(embargo),
        "otros_descuentos": _redondear(otros_descuentos),
        "total_deducido": _redondear(deducido),
        "neto_pagado": _redondear(devengado - deducido),
    }


async def sembrar_hcm(
    db: AsyncSession, *,
    desde: date,
    hasta: date,
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera la planta y su historia entre dos fechas."""
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)

    async def confirmar() -> None:
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    # ── Empresa y estructura ──
    avisar("Estructura de la empresa…")
    empresa = HCMEmpresa(
        nombre="Transportes Demo SAS", nit="901456789", pais="Colombia",
        ciudad="Funza", telefono="6018765432",
        email="gestionhumana@demo-tittanware.com", activo=True)
    db.add(empresa)
    await db.flush()

    sedes: List[HCMSede] = []
    for nombre, ciudad, departamento, direccion in _SEDES:
        sede = HCMSede(empresa_id=empresa.id, nombre=nombre, ciudad=ciudad,
                       departamento=departamento, pais="Colombia",
                       direccion=direccion,
                       telefono=f"60{az.randrange(1, 9)}{az.randrange(1000000, 9999999)}",
                       activo=True)
        db.add(sede)
        sedes.append(sede)

    centros: List[HCMCentroCosto] = []
    for codigo, nombre in _CENTROS_COSTO:
        cc = HCMCentroCosto(empresa_id=empresa.id, codigo=codigo, nombre=nombre,
                            activo=True)
        db.add(cc)
        centros.append(cc)
    await db.flush()

    areas: Dict[str, HCMArea] = {}
    cargos: List[HCMCargo] = []
    for nombre_area, lista in _ESTRUCTURA.items():
        area = HCMArea(empresa_id=empresa.id, nombre=nombre_area,
                       descripcion=f"Área de {nombre_area.lower()}", activo=True)
        db.add(area)
        await db.flush()
        areas[nombre_area] = area
        for nombre_cargo, minimo, maximo, cuantos in lista:
            cargo = HCMCargo(
                empresa_id=empresa.id, area_id=area.id, nombre=nombre_cargo,
                nivel=("DIRECTIVO" if minimo >= 6 else
                       "COORDINACION" if minimo >= 3 else "OPERATIVO"),
                descripcion=None,
                salario_minimo=_redondear(minimo * SMLV),
                salario_maximo=_redondear(maximo * SMLV), activo=True)
            db.add(cargo)
            cargo._cuantos = cuantos
            cargo._area = nombre_area
            cargo._rango = (minimo, maximo)
            cargos.append(cargo)
    await db.flush()

    # ── La planta ──
    avisar("Colaboradores y contratos…")
    colaboradores: List[HCMColaborador] = []
    consecutivo = 0
    usados: set = set()
    jefes_por_area: Dict[str, HCMColaborador] = {}

    for cargo in cargos:
        for _ in range(cargo._cuantos):
            consecutivo += 1
            masculino = az.random() < (0.86 if "Conductor" in cargo.nombre else 0.52)
            nombres = az.choice(_NOMBRES_M if masculino else _NOMBRES_F)
            apellidos = f"{az.choice(_APELLIDOS)} {az.choice(_APELLIDOS)}"

            cedula = _cedula(az)
            while cedula in usados:
                cedula = _cedula(az)
            usados.add(cedula)

            # La antigüedad se reparte: hay gente de hace años y gente que entró
            # el mes pasado. Sin eso la rotación sale en cero y el indicador de
            # nuevos ingresos es una línea plana.
            antiguedad = az.choices([az.randrange(1, 12), az.randrange(12, 48),
                                     az.randrange(48, 150)],
                                    weights=[34, 44, 22], k=1)[0]
            ingreso = hasta - timedelta(days=int(antiguedad * 30.4))
            salario = _redondear(az.uniform(*cargo._rango) * SMLV)

            # Un 7% ya se retiró. Sin retirados no hay rotación que calcular.
            # Se exige antigüedad suficiente: nadie se retira antes de entrar, y
            # el retiro tiene que caber entre el ingreso y hoy.
            dias_antiguedad = int(antiguedad * 30.4)
            retirado = az.random() < 0.07 and dias_antiguedad > 150
            fecha_retiro = None
            if retirado:
                fecha_retiro = ingreso + timedelta(
                    days=az.randrange(120, dias_antiguedad))
                if fecha_retiro > hasta:
                    retirado, fecha_retiro = False, None

            estado = (EstadoLaboralEnum.RETIRADO if retirado
                      else az.choices([EstadoLaboralEnum.ACTIVO,
                                       EstadoLaboralEnum.VACACIONES,
                                       EstadoLaboralEnum.INCAPACIDAD],
                                      weights=[93, 5, 2], k=1)[0])

            tipo_contrato = az.choices(
                [TipoContratoEnum.INDEFINIDO, TipoContratoEnum.FIJO,
                 TipoContratoEnum.OBRA_LABOR, TipoContratoEnum.PRESTACION_SERVICIOS],
                weights=[62, 22, 10, 6], k=1)[0]

            colaborador = HCMColaborador(
                tipo_documento=TipoDocumentoEnum.CC, numero_documento=cedula,
                nombres=nombres, apellidos=apellidos,
                fecha_nacimiento=date(az.randrange(1968, 2004),
                                      az.randrange(1, 13), az.randrange(1, 29)),
                genero=GeneroEnum.MASCULINO if masculino else GeneroEnum.FEMENINO,
                nacionalidad="Colombiana",
                estado_civil=az.choice(["Soltero(a)", "Casado(a)",
                                        "Unión libre", "Divorciado(a)"]),
                direccion=f"Calle {az.randrange(1, 180)} #{az.randrange(1, 99)}-{az.randrange(1, 99)}",
                ciudad=az.choice([s.ciudad for s in sedes]),
                departamento="Cundinamarca", pais="Colombia",
                telefono=f"3{az.randrange(10, 25)}{az.randrange(1000000, 9999999)}",
                email=f"{nombres.split()[0].lower()}.{apellidos.split()[0].lower()}"
                      f"{consecutivo}@demo-tittanware.com",
                codigo_empleado=f"EMP-{consecutivo:04d}",
                empresa_id=empresa.id, sede_id=az.choice(sedes).id,
                area_id=areas[cargo._area].id, cargo_id=cargo.id,
                centro_costo_id=az.choice(centros).id,
                tipo_contrato=tipo_contrato, fecha_ingreso=ingreso,
                fecha_retiro=fecha_retiro,
                estado_laboral=estado, salario_base=salario,
                tipo_salario="ORDINARIO",
                auxilio_transporte=(AUXILIO_TRANSPORTE if salario <= TOPE_AUXILIO else 0.0),
                bonificaciones_fijas=0.0)
            db.add(colaborador)
            colaborador._cargo = cargo
            colaboradores.append(colaborador)
    await db.flush()

    # Jefes: quien tiene el cargo directivo del área manda sobre los demás.
    for cargo in cargos:
        if cargo.nivel != "DIRECTIVO":
            continue
        for c in colaboradores:
            if c.cargo_id == cargo.id:
                jefes_por_area[cargo._area] = c
                break
    for c in colaboradores:
        jefe = jefes_por_area.get(c._cargo._area)
        if jefe is not None and jefe.id != c.id:
            c.jefe_id = jefe.id

    for c in colaboradores:
        db.add(HCMContrato(
            colaborador_id=c.id, tipo_contrato=c.tipo_contrato,
            fecha_inicio=c.fecha_ingreso,
            fecha_fin=(c.fecha_ingreso + timedelta(days=365)
                       if c.tipo_contrato == TipoContratoEnum.FIJO else None),
            salario=c.salario_base,
            estado="TERMINADO" if c.fecha_retiro else "ACTIVO",
            notas=None))
    await db.flush()
    await confirmar()

    # ── Conductores ──
    avisar("Conductores y licencias…")
    conductores: List[HCMConductor] = []
    licencias = set()
    for c in colaboradores:
        if "Conductor" not in c._cargo.nombre:
            continue
        num = str(az.randrange(10_000_000, 99_999_999))
        while num in licencias:
            num = str(az.randrange(10_000_000, 99_999_999))
        licencias.add(num)
        expedicion = c.fecha_ingreso - timedelta(days=az.randrange(200, 2500))
        # Los vencimientos se reparten alrededor de hoy: unas pocas vencidas y
        # varias por vencer. Con todas vigentes el tablero de alertas nace vacío
        # y no se puede mostrar para qué sirve.
        vencimiento = hasta + timedelta(days=az.choices(
            [az.randrange(-120, 0), az.randrange(0, 60), az.randrange(60, 900)],
            weights=[6, 16, 78], k=1)[0])
        conductor = HCMConductor(
            colaborador_id=c.id, num_licencia=num,
            tipo_licencia=(TipoLicenciaEnum.C3 if "tractocamión" in c._cargo.nombre
                           else TipoLicenciaEnum.C2),
            fecha_expedicion_licencia=expedicion,
            fecha_vencimiento_licencia=vencimiento,
            restricciones=az.choice([None, None, None, "Uso de lentes correctivos"]),
            anos_experiencia=az.randrange(2, 26),
            certificaciones="Manejo defensivo · Mercancías peligrosas"
                            if az.random() < 0.55 else "Manejo defensivo",
            activo_conduccion=(c.estado_laboral != EstadoLaboralEnum.RETIRADO))
        db.add(conductor)
        conductor._colaborador = c
        conductores.append(conductor)
    await db.flush()
    await confirmar()

    # ── Nómina, mes a mes ──
    avisar("Nómina…")
    activos = [c for c in colaboradores if c.fecha_retiro is None]
    periodos = 0
    detalles = 0
    novedades = 0
    mes = date(desde.year, desde.month, 1)
    while mes <= hasta:
        siguiente = date(mes.year + (mes.month == 12), (mes.month % 12) + 1, 1)
        fin = siguiente - timedelta(days=1)
        if fin > hasta:
            fin = hasta

        periodo = HCMNominaPeriodo(
            empresa_id=empresa.id,
            nombre=f"Nómina {_MESES[mes.month - 1]} {mes.year}",
            fecha_inicio=mes, fecha_fin=fin,
            # El mes en curso todavía está abierto: una nómina donde todo está
            # pagado hasta el último día no existe en ninguna empresa.
            estado=(EstadoNominaEnum.EN_PROCESO if fin >= hasta - timedelta(days=25)
                    else EstadoNominaEnum.PAGADA),
            total_devengado=0, total_deducido=0, total_neto=0, empleados_count=0)
        db.add(periodo)
        await db.flush()
        periodos += 1

        suma_dev = suma_ded = suma_neto = 0.0
        cuantos = 0
        for c in colaboradores:
            if c.fecha_ingreso > fin:
                continue
            if c.fecha_retiro and c.fecha_retiro < mes:
                continue
            conduce = "Conductor" in c._cargo.nombre
            dias = 30
            if c.fecha_ingreso > mes:
                dias = max(1, 30 - c.fecha_ingreso.day + 1)

            # A los conductores les pesan las extras y los viáticos; a comercial,
            # las comisiones. Una nómina donde todos ganan igual no permite ver
            # nada en un informe por área.
            extras = (c.salario_base / 235 * 1.25 * az.randrange(0, 34)
                      if conduce or c._cargo._area in ("Almacén", "Mantenimiento")
                      else c.salario_base / 235 * 1.25 * az.randrange(0, 9))
            nocturno = (c.salario_base / 235 * 0.35 * az.randrange(0, 26)
                        if conduce else 0.0)
            dominical = (c.salario_base / 30 * 1.75 * az.randrange(0, 3)
                         if conduce else 0.0)
            viaticos = az.randrange(0, 14) * 62_000 if conduce else 0.0
            comisiones = (c.salario_base * az.uniform(0.05, 0.35)
                          if "comercial" in c._cargo.nombre.lower() else 0.0)
            bonificacion = (az.randrange(120, 460) * 1_000
                            if az.random() < 0.22 else 0.0)
            embargo = c.salario_base * 0.20 if az.random() < 0.03 else 0.0
            otros = az.randrange(20, 180) * 1_000 if az.random() < 0.18 else 0.0

            valores = liquidar(
                c.salario_base, dias=dias, horas_extras=extras,
                recargo_nocturno=nocturno, dominicales=dominical, festivos=0.0,
                bonificaciones=bonificacion, comisiones=comisiones,
                viaticos=viaticos, embargo=embargo, otros_descuentos=otros)
            db.add(HCMNominaDetalle(periodo_id=periodo.id, colaborador_id=c.id,
                                    **valores))
            detalles += 1
            cuantos += 1
            suma_dev += valores["total_devengado"]
            suma_ded += valores["total_deducido"]
            suma_neto += valores["neto_pagado"]

            # Las novedades del mes quedan registradas aparte: son el respaldo de
            # lo que se liquidó, y sin ellas la pantalla de novedades sale vacía
            # aunque la nómina tenga extras y descuentos.
            for tipo, valor, texto in (
                (TipoNovedadEnum.HORA_EXTRA, valores["horas_extras"],
                 "Horas extras del período"),
                (TipoNovedadEnum.VIATICO, valores["viaticos"],
                 "Viáticos de ruta"),
                (TipoNovedadEnum.COMISION, valores["comisiones"],
                 "Comisión por ventas"),
                (TipoNovedadEnum.BONIFICACION, valores["bonificaciones"],
                 "Bonificación no salarial"),
                (TipoNovedadEnum.EMBARGO, valores["embargo"],
                 "Embargo judicial"),
            ):
                if valor <= 0:
                    continue
                db.add(HCMNovedad(
                    colaborador_id=c.id, periodo_id=periodo.id,
                    tipo_novedad=tipo, descripcion=texto, valor=valor,
                    fecha=fin, aprobado_por="Analista de nómina", notas=None))
                novedades += 1

        periodo.total_devengado = _redondear(suma_dev)
        periodo.total_deducido = _redondear(suma_ded)
        periodo.total_neto = _redondear(suma_neto)
        periodo.empleados_count = cuantos
        await db.flush()
        await confirmar()
        mes = siguiente

    # ── Ausentismo ──
    avisar("Incapacidades y vacaciones…")
    incapacidades = vacaciones = 0
    for c in colaboradores:
        for _ in range(az.choices([0, 1, 2], weights=[62, 30, 8], k=1)[0]):
            inicio = desde + timedelta(days=az.randrange(0, max(1, (hasta - desde).days)))
            if inicio < c.fecha_ingreso:
                continue
            dias = az.choices([1, 2, 3, 5, 8, 15, 30], weights=[26, 22, 18, 16, 10, 6, 2], k=1)[0]
            tipo = az.choices(
                [TipoIncapacidadEnum.ENFERMEDAD_COMUN,
                 TipoIncapacidadEnum.ACCIDENTE_LABORAL,
                 TipoIncapacidadEnum.ENFERMEDAD_LABORAL,
                 TipoIncapacidadEnum.MATERNIDAD],
                weights=[76, 14, 6, 4], k=1)[0]
            # Los dos primeros días los paga la empresa; de ahí en adelante la
            # EPS. Repartirlo al azar borra el único dato por el que alguien
            # abre esta pantalla: cuánto le cuesta el ausentismo a la empresa.
            dia_salario = c.salario_base / 30.0
            propios = min(dias, 2)
            db.add(HCMIncapacidad(
                colaborador_id=c.id, tipo_incapacidad=tipo,
                diagnostico=az.choice(_DIAGNOSTICOS),
                entidad_emisora=az.choice(["Sura EPS", "Sanitas", "Nueva EPS",
                                           "Compensar", "Salud Total"]),
                fecha_inicio=inicio, fecha_fin=inicio + timedelta(days=dias - 1),
                dias=dias,
                costo_empresa=_redondear(propios * dia_salario),
                costo_eps=_redondear(max(0, dias - propios) * dia_salario * 0.6667),
                estado="CERRADA" if inicio + timedelta(days=dias) < hasta else "ACTIVA",
                notas=None))
            incapacidades += 1

        if (hasta - c.fecha_ingreso).days > 365 and az.random() < 0.62:
            inicio = hasta - timedelta(days=az.randrange(10, 320))
            dias = az.choice([5, 7, 10, 15])
            db.add(HCMVacacion(
                colaborador_id=c.id, fecha_inicio=inicio,
                fecha_fin=inicio + timedelta(days=dias - 1),
                dias_disfrutados=dias, tipo="DISFRUTE",
                estado=az.choices(["APROBADA", "PENDIENTE", "DISFRUTADA"],
                                  weights=[24, 12, 64], k=1)[0],
                aprobado_por="Jefe inmediato", notas=None))
            vacaciones += 1
    await db.flush()
    await confirmar()

    # ── Capacitación ──
    avisar("Capacitación y evaluaciones…")
    capacitaciones: List[HCMCapacitacion] = []
    for nombre, tipo, horas, obligatoria, conductores_only in _CAPACITACIONES:
        inicio = desde + timedelta(days=az.randrange(0, max(1, (hasta - desde).days - 30)))
        cap = HCMCapacitacion(
            empresa_id=empresa.id, nombre=nombre,
            descripcion=f"Programa de {nombre.lower()}", tipo=tipo,
            duracion_horas=horas,
            instructor=f"{az.choice(_NOMBRES_M + _NOMBRES_F)} {az.choice(_APELLIDOS)}",
            modalidad=az.choice(["PRESENCIAL", "VIRTUAL", "MIXTA"]),
            fecha_inicio=inicio, fecha_fin=inicio + timedelta(days=az.randrange(1, 20)),
            obligatoria=obligatoria, aplica_conductores=conductores_only,
            activo=True)
        db.add(cap)
        cap._solo_conductores = conductores_only
        capacitaciones.append(cap)
    await db.flush()

    inscripciones = 0
    for cap in capacitaciones:
        publico = ([c for c in colaboradores if "Conductor" in c._cargo.nombre]
                   if cap._solo_conductores else colaboradores)
        for c in publico:
            if not cap.obligatoria and az.random() > 0.35:
                continue
            estado = az.choices(
                [EstadoCapacitacionEnum.COMPLETADO, EstadoCapacitacionEnum.EN_CURSO,
                 EstadoCapacitacionEnum.PENDIENTE, EstadoCapacitacionEnum.VENCIDO],
                weights=[68, 12, 14, 6], k=1)[0]
            completado = (cap.fecha_fin if estado == EstadoCapacitacionEnum.COMPLETADO
                          else None)
            db.add(HCMColaboradorCapacitacion(
                colaborador_id=c.id, capacitacion_id=cap.id, estado=estado,
                fecha_completado=completado,
                calificacion=round(az.uniform(3.2, 5.0), 1) if completado else None,
                fecha_vencimiento=(completado + timedelta(days=730)
                                   if completado else None),
                notas=None))
            inscripciones += 1
    await db.flush()
    await confirmar()

    # ── Evaluaciones ──
    evaluaciones = 0
    for c in colaboradores:
        if c.fecha_retiro or (hasta - c.fecha_ingreso).days < 180:
            continue
        if az.random() > 0.72:
            continue
        jefe = jefes_por_area.get(c._cargo._area)
        db.add(HCMEvaluacion(
            colaborador_id=c.id, periodo=f"{hasta.year}-S1",
            tipo_evaluacion=az.choices(
                [TipoEvaluacionEnum.NOVENTA, TipoEvaluacionEnum.CIENTO_OCHENTA,
                 TipoEvaluacionEnum.TRESCIENTOS_SESENTA],
                weights=[54, 30, 16], k=1)[0],
            evaluador_id=jefe.id if jefe and jefe.id != c.id else None,
            fecha=hasta - timedelta(days=az.randrange(20, 200)),
            calificacion_total=round(az.gauss(4.1, 0.5), 2),
            estado=az.choices(["COMPLETADA", "PENDIENTE"], weights=[82, 18], k=1)[0],
            notas=None))
        evaluaciones += 1
    await db.flush()

    # ── SST ──
    avisar("Seguridad y salud en el trabajo…")
    for fuente, descripcion, probabilidad, impacto in _RIESGOS_SST:
        db.add(HCMSSTRiesgo(
            empresa_id=empresa.id, area_id=az.choice(list(areas.values())).id,
            fuente=fuente, descripcion=descripcion, probabilidad=probabilidad,
            impacto=impacto, nivel_riesgo=probabilidad * impacto,
            control="Control operacional documentado y verificado en inspección",
            responsable_id=az.choice(colaboradores).id,
            fecha_revision=hasta - timedelta(days=az.randrange(10, 180)),
            estado="ACTIVO"))

    incidentes = 0
    for _ in range(az.randrange(14, 24)):
        tipo, descripcion, dias_inc = az.choice(_INCIDENTES_SST)
        fecha = desde + timedelta(days=az.randrange(0, max(1, (hasta - desde).days)))
        db.add(HCMSSTIncidente(
            empresa_id=empresa.id, sede_id=az.choice(sedes).id,
            colaborador_id=az.choice(colaboradores).id, fecha=fecha,
            tipo_sst=tipo, descripcion=descripcion,
            causa=az.choice(["Acto inseguro", "Condición insegura",
                             "Falla de procedimiento", "Factor externo"]),
            consecuencias="Sin lesión" if dias_inc == 0 else f"Incapacidad de {dias_inc} días",
            dias_incapacidad=dias_inc,
            investigado=az.random() < 0.78,
            medidas_correctivas="Refuerzo de capacitación y ajuste del procedimiento",
            estado=az.choices(["CERRADO", "ABIERTO", "EN_INVESTIGACION"],
                              weights=[64, 18, 18], k=1)[0]))
        incidentes += 1

    inspecciones = 0
    dia = desde
    while dia <= hasta:
        if dia.day in (5, 20) and _habil(dia):
            db.add(HCMSSTInspeccion(
                empresa_id=empresa.id, sede_id=az.choice(sedes).id, fecha=dia,
                tipo=az.choice(["Inspección de vehículos", "Inspección locativa",
                                "Inspección de EPP", "Inspección de extintores",
                                "Inspección de botiquines"]),
                inspector_id=az.choice(colaboradores).id,
                hallazgos=az.choice([
                    "Sin hallazgos", "Extintor con presión baja en zona de cargue",
                    "Señalización de pasillo desgastada",
                    "Dos operarios sin gafas de seguridad",
                    "Botiquín incompleto en el taller"]),
                acciones="Se asigna responsable y fecha de cierre",
                estado=az.choices(["CERRADA", "PENDIENTE"], weights=[76, 24], k=1)[0]))
            inspecciones += 1
        dia += timedelta(days=1)
    await db.flush()
    await confirmar()

    # ── Vacantes ──
    vacantes = 0
    for cargo in az.sample(cargos, 6):
        apertura = hasta - timedelta(days=az.randrange(5, 120))
        db.add(HCMVacante(
            empresa_id=empresa.id, cargo_id=cargo.id, titulo=cargo.nombre,
            num_vacantes=az.randrange(1, 4),
            descripcion=f"Se requiere {cargo.nombre.lower()} para la operación.",
            requisitos="Experiencia mínima de 2 años en cargos similares.",
            salario_min=cargo.salario_minimo, salario_max=cargo.salario_maximo,
            fecha_apertura=apertura,
            fecha_cierre=apertura + timedelta(days=45),
            estado=az.choices([EstadoVacanteEnum.ABIERTA, EstadoVacanteEnum.CERRADA],
                              weights=[62, 38], k=1)[0],
            tipo_contrato=TipoContratoEnum.INDEFINIDO,
            modalidad=az.choice(["PRESENCIAL", "HIBRIDO"])))
        vacantes += 1
    await db.flush()

    # ── Indicadores diarios, calculados de la planta ──
    avisar("Indicadores…")
    kpis = 0
    dia = desde
    costo_mes = 0.0
    while dia <= hasta:
        if dia.weekday() == 0:      # uno por semana: diario no aporta nada
            plantilla = [c for c in colaboradores if c.fecha_ingreso <= dia]
            act = [c for c in plantilla
                   if c.fecha_retiro is None or c.fecha_retiro > dia]
            ret = [c for c in plantilla
                   if c.fecha_retiro is not None and c.fecha_retiro <= dia]
            nuevos = [c for c in plantilla
                      if (dia - c.fecha_ingreso).days < 30]
            cond = [c for c in conductores
                    if c._colaborador in act]
            por_vencer = [c for c in cond
                          if 0 <= (c.fecha_vencimiento_licencia - dia).days <= 60]
            costo_mes = sum(c.salario_base for c in act) * 1.52   # con prestaciones
            db.add(HCMKPIDiario(
                empresa_id=empresa.id, fecha=dia,
                headcount_total=len(plantilla), headcount_activo=len(act),
                headcount_retirado=len(ret), nuevos_ingresos=len(nuevos),
                rotacion_mensual=round(100.0 * len(ret) / len(plantilla), 2)
                                 if plantilla else 0.0,
                conductores_activos=len(cond),
                conductores_licencias_por_vencer=len(por_vencer),
                ausentismo_rate=round(az.uniform(1.4, 4.2), 2),
                costo_nomina_mes=_redondear(costo_mes)))
            kpis += 1
        dia += timedelta(days=1)
    await db.flush()
    await confirmar()

    return {
        "empresa": 1, "sedes": len(sedes), "areas": len(areas),
        "cargos": len(cargos), "centros_costo": len(centros),
        "colaboradores": len(colaboradores), "activos": len(activos),
        "conductores": len(conductores), "periodos_nomina": periodos,
        "detalles_nomina": detalles, "novedades": novedades,
        "incapacidades": incapacidades, "vacaciones": vacaciones,
        "capacitaciones": len(capacitaciones), "inscripciones": inscripciones,
        "evaluaciones": evaluaciones, "riesgos_sst": len(_RIESGOS_SST),
        "incidentes_sst": incidentes, "inspecciones_sst": inspecciones,
        "vacantes": vacantes, "semanas_con_indicadores": kpis,
    }


async def verificar(db: AsyncSession) -> dict:
    """Comprueba que la nómina cuadre.

    Dos cosas: que el neto de cada detalle sea su devengado menos su deducido, y
    que el total de cada período sea la suma de sus detalles. Si alguna falla,
    los importes son decorativos y no sirven para mostrarle nada a un contador.
    """
    descuadres = (await db.execute(text(
        "SELECT count(*) FROM hcm_nomina_detalle "
        "WHERE abs(neto_pagado - (total_devengado - total_deducido)) > 1"))).scalar() or 0
    periodos_malos = (await db.execute(text("""
        SELECT count(*) FROM (
          SELECT p.id, p.total_neto,
                 COALESCE(SUM(d.neto_pagado), 0) AS suma
            FROM hcm_nomina_periodo p
            LEFT JOIN hcm_nomina_detalle d ON d.periodo_id = p.id
           GROUP BY p.id, p.total_neto
        ) t WHERE abs(total_neto - suma) > 1"""))).scalar() or 0
    total = (await db.execute(text(
        "SELECT COALESCE(SUM(neto_pagado), 0) FROM hcm_nomina_detalle"))).scalar() or 0
    return {
        "detalles_descuadrados": int(descuadres),
        "periodos_descuadrados": int(periodos_malos),
        "nomina_neta_total": round(float(total), 2),
    }
