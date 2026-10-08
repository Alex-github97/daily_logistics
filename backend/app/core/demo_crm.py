"""
Siembra de volumen para el módulo comercial (CRM).

QUÉ GENERA
Un año de vida comercial: prospectos que entran por una campaña, se califican,
se vuelven oportunidad, pasan por cotización y terminan en contrato —o se
pierden—, y después el cliente firmado abre tickets, recibe encuestas y acumula
un puntaje de salud.

TRES REGLAS QUE HACEN QUE ESTOS DATOS SIRVAN

1. **El embudo es un embudo de verdad.** Cada oportunidad sale de un prospecto
   que existe, cada cotización de una oportunidad, y cada contrato de una
   cotización aprobada. Sembrar las cuatro listas por separado da un tablero que
   se ve bien y que se cae en cuanto alguien pincha una cifra para ver de dónde
   viene.

2. **El puntaje de salud se calcula, no se sortea.** Sale de los tickets que ese
   cliente abrió, de sus encuestas y de si tiene contrato vigente. Así, cuando
   el módulo dice que un cliente está en riesgo, se puede ir a mirar qué se lo
   hizo. Un puntaje aleatorio convierte la pantalla de retención en adivinación.

3. **Los KPI diarios se resumen de lo sembrado.** No se inventan aparte, porque
   entonces el tablero y las listas dirían dos cosas distintas del mismo mes y
   quien lo note deja de creerle a los dos.

DETERMINISTA
Semilla fija: dos corridas producen exactamente los mismos datos.
"""
import random
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.crm import (
    CRMActividad, CRMCampana, CRMCampanaCliente, CRMCliente, CRMContacto,
    CRMContrato, CRMContratoSLA, CRMCotizacion, CRMCotizacionItem,
    CRMCuentaClave, CRMEjecutivoComercial, CRMEncuesta, CRMInteraccion,
    CRMKPIDiario, CRMLead, CRMObjetivoComercial, CRMOportunidad,
    CRMRiesgoCliente, CRMSaludCliente, CRMTicket,
    EstadoClienteEnum, EstadoContratoEnum, EstadoCotizacionEnum,
    EstadoLeadEnum, EstadoOportunidadEnum, EstadoTicketEnum,
    NivelRiesgoClienteEnum, SegmentoClienteEnum, TipoCampanaEnum,
    TipoClienteEnum, TipoEncuestaEnum, TipoInteraccionEnum, TipoTicketEnum,
)

SEMILLA = 20260910

# El comercial colombiano tiene su calendario: enero se pierde entre vacaciones
# y presupuestos sin aprobar, y el cuarto trimestre concentra los cierres porque
# nadie quiere entrar al año siguiente con la meta sin cumplir.
_ESTACIONALIDAD = {
    1: 0.55, 2: 0.85, 3: 1.05, 4: 0.95, 5: 1.08, 6: 1.00,
    7: 0.92, 8: 1.06, 9: 1.12, 10: 1.24, 11: 1.30, 12: 0.78,
}

_EJECUTIVOS = [
    ("Laura Soto Ramírez",      "Bogotá",       1_800_000_000),
    ("Carlos Vega Ospina",      "Bogotá",       1_500_000_000),
    ("Ana Ruiz Cardona",        "Antioquia",    1_350_000_000),
    ("Pedro Díaz Mejía",        "Valle",        1_200_000_000),
    ("Mónica Peña Álvarez",     "Costa Caribe",   950_000_000),
]

# (razón social, industria, ciudad, segmento, potencial anual en pesos)
_EMPRESAS = [
    ("Distribuidora del Norte S.A.S.",      "Distribución", "Barranquilla", "MEDIANA",      480_000_000),
    ("Alimentos del Valle S.A.",            "Alimentos",    "Cali",         "CORPORATIVO",1_900_000_000),
    ("Textiles Andinos Ltda.",              "Manufactura",  "Medellín",     "MEDIANA",      620_000_000),
    ("Ferretería Industrial Cundinamarca",  "Ferretería",   "Bogotá",       "PEQUENA",      180_000_000),
    ("Lácteos La Sabana S.A.S.",            "Alimentos",    "Zipaquirá",    "MEDIANA",      540_000_000),
    ("Químicos Tecnológicos de Colombia",   "Químicos",     "Bogotá",       "ESTRATEGICO",2_400_000_000),
    ("Constructora Cordillera S.A.",        "Construcción", "Bogotá",       "CORPORATIVO",1_600_000_000),
    ("Agroindustrias del Tolima",           "Agro",         "Ibagué",       "MEDIANA",      430_000_000),
    ("Plásticos del Caribe S.A.S.",         "Manufactura",  "Cartagena",    "MEDIANA",      510_000_000),
    ("Farmacéutica Nacional Ltda.",         "Farmacéutico", "Bogotá",       "ESTRATEGICO",2_100_000_000),
    ("Autopartes del Eje Cafetero",         "Automotriz",   "Pereira",      "PEQUENA",      210_000_000),
    ("Comercializadora Santander S.A.",     "Retail",       "Bucaramanga",  "MEDIANA",      670_000_000),
    ("Bebidas Premium de Colombia",         "Bebidas",      "Medellín",     "CORPORATIVO",1_450_000_000),
    ("Papelera del Oriente Ltda.",          "Papel",        "Cúcuta",       "PEQUENA",      160_000_000),
    ("Metalmecánica Antioqueña S.A.S.",     "Metalmecánica","Itagüí",       "MEDIANA",      590_000_000),
    ("Cosméticos Naturales de Colombia",    "Cosméticos",   "Bogotá",       "MEDIANA",      380_000_000),
    ("Refrigerados del Pacífico S.A.",      "Alimentos",    "Buenaventura", "CORPORATIVO",1_250_000_000),
    ("Insumos Agrícolas del Meta",          "Agro",         "Villavicencio","PEQUENA",      240_000_000),
    ("Electrodomésticos Andina S.A.S.",     "Retail",       "Bogotá",       "MEDIANA",      720_000_000),
    ("Cementos del Magdalena",              "Construcción", "Santa Marta",  "ESTRATEGICO",1_950_000_000),
    ("Vidrios Técnicos Colombianos",        "Manufactura",  "Bogotá",       "PEQUENA",      195_000_000),
    ("Distribuidora Farmacéutica Sur",      "Farmacéutico", "Neiva",        "MEDIANA",      445_000_000),
    ("Muebles y Diseño del Quindío",        "Muebles",      "Armenia",      "PEQUENA",      150_000_000),
    ("Cárnicos del Llano S.A.",             "Alimentos",    "Villavicencio","MEDIANA",      580_000_000),
    ("Empaques Flexibles de Colombia",      "Empaques",     "Medellín",     "CORPORATIVO",1_380_000_000),
    ("Herramientas Profesionales Ltda.",    "Ferretería",   "Cali",         "PEQUENA",      175_000_000),
    ("Semillas y Fertilizantes del Huila",  "Agro",         "Neiva",        "MEDIANA",      395_000_000),
    ("Confecciones Modernas S.A.S.",        "Textil",       "Medellín",     "MEDIANA",      465_000_000),
    ("Lubricantes Industriales Nacionales", "Químicos",     "Bogotá",       "MEDIANA",      520_000_000),
    ("Comercial Aduanera del Caribe",       "Comercio",     "Cartagena",    "CORPORATIVO",1_120_000_000),
]

_SERVICIOS = [
    ("Operación logística integral",       "3PL",          38_000_000),
    ("Transporte de carga nacional",       "TRANSPORTE",   24_000_000),
    ("Almacenamiento y distribución",      "WMS",          19_000_000),
    ("Última milla urbana",                "ULTIMA_MILLA", 15_000_000),
    ("Cross-docking regional",             "CROSSDOCK",    11_000_000),
    ("Gestión de inventarios en sitio",    "INHOUSE",      27_000_000),
]

_MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_FUENTES = ["Sitio web", "Referido", "Feria comercial", "LinkedIn",
            "Llamada en frío", "Campaña de correo", "Cliente actual"]

_NOMBRES = ["Andrés", "Carolina", "Javier", "Diana", "Ricardo", "Paola",
            "Óscar", "Natalia", "Fernando", "Claudia", "Mauricio", "Luz"]
_APELLIDOS = ["Gómez", "Rodríguez", "Martínez", "Herrera", "Castaño", "Molina",
              "Restrepo", "Cárdenas", "Villamil", "Quintero", "Salazar", "Pardo"]
_CARGOS = ["Gerente de Logística", "Director de Compras", "Jefe de Operaciones",
           "Coordinador de Abastecimiento", "Gerente General",
           "Director Financiero", "Analista de Compras"]

_ASUNTOS_TICKET = [
    ("Retraso en la entrega de la ruta norte",        "INCIDENTE", "ALTA"),
    ("Diferencia en la cantidad recibida",            "RECLAMO",   "ALTA"),
    ("Solicitud de certificado de cumplimiento",      "SOLICITUD", "BAJA"),
    ("Consulta sobre la tarifa del corredor Cali",    "CONSULTA",  "BAJA"),
    ("Avería en el empaque de dos estibas",           "RECLAMO",   "MEDIA"),
    ("Cambio de la ventana horaria de entrega",       "SOLICITUD", "MEDIA"),
    ("Falta la factura del mes anterior",             "PQRS",      "MEDIA"),
    ("Unidad no se presentó al cargue",               "INCIDENTE", "CRITICA"),
    ("Solicitud de informe de indicadores",           "SOLICITUD", "BAJA"),
    ("Producto entregado en dirección equivocada",    "RECLAMO",   "ALTA"),
]


def _sin_tildes(t: str) -> str:
    """Para armar correos. Las tildes en un dominio no son direcciones válidas."""
    return "".join(c for c in unicodedata.normalize("NFKD", t)
                   if not unicodedata.combining(c))


def _dominio(razon: str) -> str:
    base = _sin_tildes(razon).lower()
    for ruido in (" s.a.s.", " s.a.", " ltda.", " s.a.s", " ltda"):
        base = base.replace(ruido, "")
    palabras = [p for p in base.replace(".", "").split() if len(p) > 3][:2]
    return ("".join(palabras) or "empresa") + ".com.co"


def _habil(d: date) -> bool:
    return d.weekday() < 5


def _nit(az: random.Random) -> str:
    cuerpo = az.randrange(800_000_000, 901_000_000)
    return f"{cuerpo}-{az.randrange(0, 10)}"


# El territorio va con la cuota: a quien le piden mil ochocientos millones le
# dan mas prospectos que a quien le piden novecientos. Repartir parejo hace que
# el de la cuota chica cierre el 270% y el de la grande el 60%, y entonces la
# pantalla de desempeno mide el tamano de la meta, no el trabajo.
_PESOS_EJECUTIVO = [meta for _, _, meta in _EJECUTIVOS]


async def sembrar_crm(
    db: AsyncSession, *,
    desde: date,
    hasta: date,
    leads_por_semana: int = 6,
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera un año de actividad comercial entre dos fechas."""
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)

    async def confirmar() -> None:
        # El `search_path` vive en la CONEXIÓN, no en la sesión: después de cada
        # commit hay que reponerlo o las inserciones siguientes caen en `public`.
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    # ── Ejecutivos ────────────────────────────────────────────────────────────
    ejecutivos: List[CRMEjecutivoComercial] = []
    for i, (nombre, region, meta) in enumerate(_EJECUTIVOS, start=1):
        e = CRMEjecutivoComercial(
            codigo=f"EJC-{i:03d}", nombre=nombre, region=region,
            email=f"{_sin_tildes(nombre).lower().split()[0]}."
                  f"{_sin_tildes(nombre).lower().split()[1]}@tittanware.com",
            telefono=f"3{az.randrange(0, 3)}{az.randrange(10_000_000, 99_999_999)}",
            meta_anual=Decimal(meta), activo=True)
        db.add(e)
        ejecutivos.append(e)
    await confirmar()
    avisar(f"  {len(ejecutivos)} ejecutivos comerciales")

    # ── Campañas ──────────────────────────────────────────────────────────────
    campanas: List[CRMCampana] = []
    tipos_campana = list(TipoCampanaEnum)
    mes = date(desde.year, desde.month, 1)
    n = 0
    while mes <= hasta:
        if mes.month % 2 == 1:          # una campaña cada dos meses
            n += 1
            fin = min(mes + timedelta(days=55), hasta)
            c = CRMCampana(
                codigo=f"CAM-{mes.year}-{n:02d}",
                nombre=f"Captación {_MESES[mes.month]} {mes.year}",
                tipo=tipos_campana[n % len(tipos_campana)],
                descripcion="Generación de prospectos en el sector industrial.",
                fecha_inicio=mes, fecha_fin=fin,
                presupuesto=Decimal(az.randrange(8, 30) * 1_000_000),
                activa=fin >= hasta)
            db.add(c)
            campanas.append(c)
        mes = date(mes.year + (mes.month // 12), (mes.month % 12) + 1, 1)
    await confirmar()

    # ── Clientes y prospectos ─────────────────────────────────────────────────
    #
    # Todos entran como PROSPECTO. Lo que los convierte en cliente es haber
    # ganado una oportunidad más adelante: si se marcaran activos aquí, el
    # embudo mostraría clientes que nunca compraron nada.
    clientes: List[CRMCliente] = []
    for i, (razon, industria, ciudad, segmento, potencial) in enumerate(_EMPRESAS, start=1):
        ejec = ejecutivos[i % len(ejecutivos)]
        c = CRMCliente(
            codigo=f"CLI-{desde.year}-{i:03d}", razon_social=razon,
            nit=_nit(az), tipo=TipoClienteEnum.EMPRESA,
            segmento=SegmentoClienteEnum(segmento),
            estado=EstadoClienteEnum.PROSPECTO,
            industria=industria, pais="Colombia", ciudad=ciudad,
            direccion=f"Calle {az.randrange(1, 180)} # {az.randrange(1, 90)}-{az.randrange(1, 99)}",
            telefono=f"60{az.randrange(1, 9)}{az.randrange(1_000_000, 9_999_999)}",
            email=f"contacto@{_dominio(razon)}",
            sitio_web=f"https://www.{_dominio(razon)}",
            ejecutivo_id=ejec.id, potencial_anual=Decimal(potencial),
            ingresos_ytd=Decimal(0), health_score=50, lead_score=0, activo=True)
        db.add(c)
        clientes.append(c)
    await confirmar()

    # ── Contactos ─────────────────────────────────────────────────────────────
    for c in clientes:
        for j in range(az.randrange(1, 4)):
            nombre = f"{az.choice(_NOMBRES)} {az.choice(_APELLIDOS)}"
            db.add(CRMContacto(
                cliente_id=c.id, nombre=nombre, cargo=az.choice(_CARGOS),
                email=f"{_sin_tildes(nombre).lower().replace(' ', '.')}@{_dominio(c.razon_social)}",
                telefono=f"3{az.randrange(0, 3)}{az.randrange(10_000_000, 99_999_999)}",
                es_decisor=(j == 0), es_principal=(j == 0), activo=True))
    await confirmar()
    avisar(f"  {len(clientes)} cuentas con sus contactos")

    # Una de cada cuatro cuentas se atiende mal. Se decide aqui, antes de
    # generar sus tickets, para que TODO lo suyo sea coherente: se le responde
    # tarde, califica peor, entrega peor y paga peor. Son las cuentas que la
    # pantalla de retencion existe para encontrar.
    problematicas = set(az.sample([c.id for c in clientes],
                                  k=max(1, len(clientes) // 4)))

    contactos_por_cliente: Dict[int, List[int]] = {}
    for cid, ctid in (await db.execute(
            select(CRMContacto.cliente_id, CRMContacto.id))).all():
        contactos_por_cliente.setdefault(cid, []).append(ctid)

    # ── El embudo, semana a semana ────────────────────────────────────────────
    leads: List[CRMLead] = []
    oportunidades: List[CRMOportunidad] = []
    cotizaciones: List[CRMCotizacion] = []
    contratos: List[CRMContrato] = []
    n_lead = n_opo = n_cot = n_con = 0

    dia = desde
    while dia <= hasta:
        if dia.weekday() != 0:          # el embudo se mueve los lunes
            dia += timedelta(days=1)
            continue

        cuantos = max(1, round(leads_por_semana * _ESTACIONALIDAD[dia.month]))
        for _ in range(cuantos):
            n_lead += 1
            cliente = az.choice(clientes)
            ejec = az.choices(ejecutivos, weights=_PESOS_EJECUTIVO, k=1)[0]
            # El puntaje decide el estado, no al revés: un prospecto «caliente»
            # con puntaje 12 es exactamente el dato que hace desconfiar de un CRM.
            score = az.randrange(5, 100)
            estado = (EstadoLeadEnum.CALIENTE if score >= 70
                      else EstadoLeadEnum.TIBIO if score >= 40
                      else EstadoLeadEnum.FRIO)
            lead = CRMLead(
                codigo=f"LEAD-{dia.year}-{n_lead:04d}",
                cliente_id=cliente.id, ejecutivo_id=ejec.id,
                empresa=cliente.razon_social,
                contacto=f"{az.choice(_NOMBRES)} {az.choice(_APELLIDOS)}",
                email=f"nuevo@{_dominio(cliente.razon_social)}",
                telefono=f"3{az.randrange(0, 3)}{az.randrange(10_000_000, 99_999_999)}",
                fuente=az.choice(_FUENTES), industria=cliente.industria,
                estado=estado, score=score,
                potencial=Decimal(az.randrange(40, 900) * 1_000_000),
                convertido=False)
            lead.created_at = datetime.combine(dia, time(az.randrange(8, 18)))
            db.add(lead)
            leads.append(lead)
        dia += timedelta(days=7)
    await confirmar()
    avisar(f"  {len(leads)} prospectos")

    # Solo los prospectos con puntaje alto pasan a oportunidad, y no todos: eso
    # es lo que da una tasa de conversión creíble en vez de un 100%.
    for lead in leads:
        if lead.score < 55 or az.random() > 0.62:
            continue
        n_opo += 1
        nacido = (lead.created_at or datetime.combine(desde, time(9))).date()
        esperada = nacido + timedelta(days=az.randrange(25, 110))
        servicio, clave, mensual = az.choice(_SERVICIOS)
        valor = Decimal(mensual * az.randrange(10, 26))     # a 10–26 meses

        # El desenlace depende de cuánto tiempo pasó: lo que se abrió el mes
        # pasado todavía está en curso. Cerrar todo daría un embudo vacío, que
        # es justo lo que no se ve nunca en una operación real.
        madura = esperada <= hasta
        if not madura:
            estado = az.choice([EstadoOportunidadEnum.IDENTIFICACION,
                                EstadoOportunidadEnum.CALIFICACION,
                                EstadoOportunidadEnum.PROPUESTA,
                                EstadoOportunidadEnum.NEGOCIACION])
            probabilidad = {"IDENTIFICACION": 15, "CALIFICACION": 35,
                            "PROPUESTA": 60, "NEGOCIACION": 80}[estado.value]
            cierre = None
            contratado = None
            motivo = None
        elif az.random() < 0.22:
            estado = EstadoOportunidadEnum.CIERRE_GANADO
            probabilidad, cierre = 100, esperada
            contratado = valor * Decimal(az.randrange(88, 103)) / Decimal(100)
            motivo = None
        else:
            estado = EstadoOportunidadEnum.CIERRE_PERDIDO
            probabilidad, cierre, contratado = 0, esperada, None
            motivo = az.choice([
                "Precio por encima del competidor",
                "El cliente aplazó la decisión al próximo año",
                "No se cumplió el requisito de cobertura nacional",
                "Se adjudicó al proveedor actual",
            ])

        o = CRMOportunidad(
            codigo=f"OPO-{nacido.year}-{n_opo:04d}",
            cliente_id=lead.cliente_id, lead_id=lead.id,
            ejecutivo_id=lead.ejecutivo_id,
            nombre=f"{servicio} — {lead.empresa}",
            descripcion=f"Propuesta de {servicio.lower()} originada en «{lead.fuente}».",
            estado=estado, probabilidad=probabilidad,
            valor_estimado=valor.quantize(Decimal("1")),
            valor_contratado=contratado.quantize(Decimal("1")) if contratado else None,
            servicio=clave, fecha_esperada=esperada, fecha_cierre=cierre,
            motivo_perdida=motivo)
        o.created_at = datetime.combine(nacido, time(10))
        db.add(o)
        oportunidades.append(o)
        lead.convertido = True
        lead.estado = EstadoLeadEnum.CONVERTIDO
    await confirmar()
    avisar(f"  {len(oportunidades)} oportunidades")

    # ── Cotizaciones: una por cada oportunidad que llegó a propuesta ──────────
    IVA = Decimal("0.19")
    for o in oportunidades:
        if o.estado in (EstadoOportunidadEnum.IDENTIFICACION,
                        EstadoOportunidadEnum.CALIFICACION):
            continue
        n_cot += 1
        nacida = (o.created_at.date() if o.created_at else desde) + timedelta(
            days=az.randrange(5, 25))
        estado_cot = (EstadoCotizacionEnum.APROBADA
                      if o.estado == EstadoOportunidadEnum.CIERRE_GANADO
                      else EstadoCotizacionEnum.RECHAZADA
                      if o.estado == EstadoOportunidadEnum.CIERRE_PERDIDO
                      else EstadoCotizacionEnum.ENVIADA)
        cot = CRMCotizacion(
            codigo=f"COT-{nacida.year}-{n_cot:04d}",
            version=1, oportunidad_id=o.id, cliente_id=o.cliente_id,
            ejecutivo_id=o.ejecutivo_id, estado=estado_cot,
            subtotal=Decimal(0), iva=Decimal(0), total=Decimal(0),
            validez_dias=30, fecha_envio=nacida,
            fecha_vencimiento=nacida + timedelta(days=30),
            notas="Tarifas sujetas a volumen mensual comprometido.")
        cot.created_at = datetime.combine(nacida, time(11))
        db.add(cot)
        await db.flush()

        # El total sale de los renglones. Escribirlo aparte deja una cotización
        # cuyo total no se puede rehacer, y eso no sirve para negociar.
        subtotal = Decimal(0)
        for _ in range(az.randrange(2, 5)):
            servicio, clave, mensual = az.choice(_SERVICIOS)
            cantidad = Decimal(az.randrange(1, 13))
            precio = Decimal(mensual)
            dcto = Decimal(az.choice([0, 0, 0, 5, 8, 10]))
            total_linea = (cantidad * precio * (Decimal(100) - dcto)
                           / Decimal(100)).quantize(Decimal("1"))
            db.add(CRMCotizacionItem(
                cotizacion_id=cot.id, descripcion=servicio, unidad="mes",
                cantidad=cantidad, precio_unitario=precio,
                descuento_pct=dcto, total=total_linea))
            subtotal += total_linea
        cot.subtotal = subtotal
        cot.iva = (subtotal * IVA).quantize(Decimal("1"))
        cot.total = cot.subtotal + cot.iva
        cotizaciones.append(cot)
    await confirmar()
    avisar(f"  {len(cotizaciones)} cotizaciones")

    # ── Contratos: solo de cotización aprobada ────────────────────────────────
    por_oportunidad = {c.oportunidad_id: c for c in cotizaciones}
    for o in oportunidades:
        if o.estado != EstadoOportunidadEnum.CIERRE_GANADO:
            continue
        cot = por_oportunidad.get(o.id)
        if cot is None:
            continue
        n_con += 1
        inicio = o.fecha_cierre or hasta
        meses = az.choice([12, 12, 18, 24, 36])
        fin = inicio + timedelta(days=meses * 30)
        vigente = fin >= hasta
        mensual = (cot.total / Decimal(meses)).quantize(Decimal("1"))
        con = CRMContrato(
            codigo=f"CON-{inicio.year}-{n_con:03d}",
            cliente_id=o.cliente_id, oportunidad_id=o.id,
            ejecutivo_id=o.ejecutivo_id,
            nombre=o.nombre,
            estado=EstadoContratoEnum.ACTIVO if vigente else EstadoContratoEnum.VENCIDO,
            tipo_servicio=o.servicio, valor_mensual=mensual,
            valor_total=cot.total, fecha_inicio=inicio, fecha_fin=fin,
            duracion_meses=meses, auto_renovacion=az.random() < 0.4,
            notas="Renovación sujeta a cumplimiento de los indicadores pactados.")
        con.created_at = datetime.combine(inicio, time(15))
        db.add(con)
        contratos.append(con)
        await db.flush()

        # Los acuerdos de nivel de servicio. El valor actual se mueve alrededor
        # del objetivo —a veces por debajo— porque un contrato donde todos los
        # indicadores se cumplen siempre no le sirve a nadie para gestionar.
        # Quien incumple sus indicadores es quien ya se identificó como cuenta
        # mal atendida. Sortear el desvío para todos por igual dejaba a casi
        # todos los contratos incumpliendo algo, y un tablero donde suenan
        # dieciséis alarmas de treinta y nueve indicadores no distingue lo grave
        # de lo normal: se aprende a cerrarlo sin leerlo.
        #
        # El signo depende de la unidad: en las horas se falla pasándose, y en
        # los porcentajes quedándose corto.
        mal_servida = con.cliente_id in problematicas
        for indicador, objetivo, unidad in (
                ("Cumplimiento de entregas a tiempo (OTIF)", 95, "%"),
                ("Tiempo de respuesta a reclamos", 24, "horas"),
                ("Exactitud del inventario", 99, "%")):
            magnitud = (az.uniform(2, 8) if mal_servida
                        else az.uniform(-3, 0.6))
            hacia_arriba_es_peor = unidad == "horas"
            desvio = magnitud if hacia_arriba_es_peor else -magnitud
            db.add(CRMContratoSLA(
                contrato_id=con.id, indicador=indicador,
                objetivo=Decimal(objetivo), unidad=unidad,
                valor_actual=Decimal(round(objetivo + desvio, 2)),
                penalizacion="Nota de crédito del 2% del valor mensual.",
                frecuencia_medicion="Mensual", activo=True))

        cliente = next(c for c in clientes if c.id == o.cliente_id)
        cliente.estado = EstadoClienteEnum.CLIENTE_ACTIVO
        cliente.ingresos_ytd = (cliente.ingresos_ytd or Decimal(0)) + mensual * 12
    await confirmar()
    avisar(f"  {len(contratos)} contratos")

    # ── Tickets, interacciones y encuestas de los clientes firmados ───────────
    activos = [c for c in clientes if c.estado == EstadoClienteEnum.CLIENTE_ACTIVO]
    contrato_de = {}
    for con in contratos:
        contrato_de.setdefault(con.cliente_id, con.id)

    tickets: List[CRMTicket] = []
    n_tk = 0
    for cliente in activos:
        for _ in range(az.randrange(2, 9)):
            n_tk += 1
            abierto = desde + timedelta(days=az.randrange(0, max(1, (hasta - desde).days)))
            if not _habil(abierto):
                abierto += timedelta(days=2)
            asunto, tipo, prioridad = az.choice(_ASUNTOS_TICKET)
            horas_limite = {"CRITICA": 4, "ALTA": 8, "MEDIA": 24, "BAJA": 72}[prioridad]
            momento = datetime.combine(abierto, time(az.randrange(7, 18)))

            # Los tickets viejos ya se cerraron; los de las últimas semanas no.
            # Con todo cerrado, la pantalla de servicio se ve perfecta y no
            # sirve para nada.
            reciente = (hasta - abierto).days < 21
            umbral_abierto = 0.80 if cliente.id in problematicas else 0.45
            if reciente and az.random() < umbral_abierto:
                estado = az.choice([EstadoTicketEnum.ABIERTO,
                                    EstadoTicketEnum.EN_PROCESO,
                                    EstadoTicketEnum.ESCALADO])
                resolucion = respuesta = solucion = satisfaccion = None
            else:
                estado = az.choice([EstadoTicketEnum.RESUELTO,
                                    EstadoTicketEnum.RESUELTO,
                                    EstadoTicketEnum.CERRADO])
                # En la cuenta descuidada se responde tarde. Es lo que despues
                # explica su nota baja y su puntaje de salud.
                mal_atendida = cliente.id in problematicas
                factor = 3.2 if mal_atendida else 1.0
                horas_resp = round(az.uniform(0.3, horas_limite * 1.4 * factor), 2)
                horas_sol = round(horas_resp
                                  + az.uniform(1, horas_limite * 3 * factor), 2)
                resolucion = momento + timedelta(hours=horas_sol)
                respuesta = Decimal(str(horas_resp))
                solucion = Decimal(str(horas_sol))
                # Si se resolvió dentro del plazo, la nota es mejor. Sortearla
                # sin relación con el tiempo rompería el vínculo entre servicio
                # y satisfacción, que es lo único que la pantalla quiere mostrar.
                a_tiempo = horas_sol <= horas_limite * 2
                satisfaccion = az.randrange(4, 6) if a_tiempo else az.randrange(1, 4)

            t = CRMTicket(
                codigo=f"TKT-{abierto.year}-{n_tk:04d}",
                cliente_id=cliente.id, contrato_id=contrato_de.get(cliente.id),
                contacto_id=(contactos_por_cliente.get(cliente.id) or [None])[0],
                ejecutivo_id=cliente.ejecutivo_id,
                tipo=TipoTicketEnum(tipo), estado=estado, prioridad=prioridad,
                asunto=asunto,
                descripcion="Reportado por el cliente a través del canal de servicio.",
                canal=az.choice(["Correo", "Teléfono", "Portal", "WhatsApp"]),
                fecha_limite=momento + timedelta(hours=horas_limite),
                fecha_resolucion=resolucion,
                tiempo_respuesta_hrs=respuesta, tiempo_solucion_hrs=solucion,
                satisfaccion=satisfaccion)
            t.created_at = momento
            db.add(t)
            tickets.append(t)
    await confirmar()
    avisar(f"  {len(tickets)} tickets de servicio")

    # Interacciones: las de los tickets, más el seguimiento comercial.
    tipos_int = list(TipoInteraccionEnum)
    for t in tickets:
        if az.random() < 0.7:
            db.add(CRMInteraccion(
                cliente_id=t.cliente_id, contacto_id=t.contacto_id,
                ticket_id=t.id, ejecutivo_id=t.ejecutivo_id,
                tipo=az.choice(tipos_int),
                asunto=f"Seguimiento a «{t.asunto[:60]}»",
                descripcion="Se contactó al cliente para informar el avance.",
                duracion_min=az.randrange(5, 45),
                resultado="Cliente informado",
                fecha_interaccion=(t.created_at or datetime.combine(desde, time(9)))
                                  + timedelta(hours=az.randrange(1, 30))))
    for o in oportunidades:
        for _ in range(az.randrange(1, 4)):
            base = o.created_at or datetime.combine(desde, time(9))
            db.add(CRMInteraccion(
                cliente_id=o.cliente_id, oportunidad_id=o.id,
                ejecutivo_id=o.ejecutivo_id, tipo=az.choice(tipos_int),
                asunto=f"Avance comercial — {o.nombre[:60]}",
                descripcion="Reunión de seguimiento sobre la propuesta.",
                duracion_min=az.randrange(15, 90),
                resultado=az.choice(["Interés confirmado", "Pidieron ajustar el alcance",
                                     "Solicitaron referencias", "Quedó de responder"]),
                proximo_paso=az.choice(["Enviar propuesta ajustada",
                                        "Agendar visita a la operación",
                                        "Esperar respuesta del comité"]),
                fecha_interaccion=base + timedelta(days=az.randrange(1, 40))))
    await confirmar()

    # Encuestas: solo a quien tuvo un ticket cerrado. Encuestar a alguien que
    # nunca pidió nada es lo que hace que un NPS no signifique nada.
    n_enc = 0
    for t in tickets:
        if t.estado not in (EstadoTicketEnum.RESUELTO, EstadoTicketEnum.CERRADO):
            continue
        if az.random() > 0.45:
            continue
        n_enc += 1
        enviada = (t.fecha_resolucion or datetime.combine(hasta, time(9))).date()
        respondida = az.random() < 0.68
        tipo_enc = az.choice(list(TipoEncuestaEnum))
        # El NPS va de 0 a 10; CSAT y CES, de 1 a 5. Meterlos en la misma escala
        # daría un promedio que no significa nada.
        if not respondida:
            puntaje = None
        elif tipo_enc == TipoEncuestaEnum.NPS:
            puntaje = min(10, max(0, (t.satisfaccion or 3) * 2 + az.randrange(-2, 2)))
        else:
            puntaje = t.satisfaccion or az.randrange(3, 6)
        db.add(CRMEncuesta(
            codigo=f"ENC-{enviada.year}-{n_enc:04d}",
            cliente_id=t.cliente_id, ticket_id=t.id, tipo=tipo_enc,
            puntaje=puntaje,
            comentario=("Buen acompañamiento del ejecutivo." if (puntaje or 0) >= 4
                        else "La respuesta tardó más de lo esperado."
                        if respondida else None),
            respondida=respondida, fecha_envio=enviada,
            fecha_respuesta=enviada + timedelta(days=az.randrange(1, 6))
                            if respondida else None))
    await confirmar()

    # ── Puntaje de salud: se calcula de lo anterior ───────────────────────────
    #
    # Cinco componentes, cada uno de 0 a 100, y el resultado es su promedio
    # ponderado. Lo que importa es que se pueda explicar: si un cliente aparece
    # en rojo, la fila de `crm_salud_cliente` dice exactamente por qué.
    por_cliente_tk: Dict[int, List[CRMTicket]] = {}
    for t in tickets:
        por_cliente_tk.setdefault(t.cliente_id, []).append(t)

    for cliente in clientes:
        tiene_contrato = cliente.id in contrato_de

        # AL PROSPECTO NO SE LE MIDE LA SALUD.
        #
        # El puntaje de salud responde «¿este cliente se me va a ir?», y a quien
        # todavia no ha comprado nada esa pregunta no se le puede hacer: no tiene
        # entregas, ni tickets, ni cartera. Ponerle un numero igual daba a los
        # trece prospectos exactamente 62 —el resultado de promediar valores por
        # defecto—, y ese 62 se veia en la pantalla como si fuera una medicion.
        # A ellos les corresponde el `lead_score`, que si mide lo suyo: que tan
        # cerca estan de comprar.
        if not tiene_contrato:
            cliente.health_score = 0
            cliente.lead_score = min(100, max(
                (l.score for l in leads if l.cliente_id == cliente.id), default=20))
            continue

        suyos = por_cliente_tk.get(cliente.id, [])
        abiertos = sum(1 for t in suyos
                       if t.estado in (EstadoTicketEnum.ABIERTO,
                                       EstadoTicketEnum.EN_PROCESO,
                                       EstadoTicketEnum.ESCALADO))
        notas = [t.satisfaccion for t in suyos if t.satisfaccion]

        score_tickets = max(0, 100 - abiertos * 18)
        score_nps = int((sum(notas) / len(notas)) * 20) if notas else 60
        score_contratos = 90
        # El mismo conjunto que ya definio como se le atendio. No se vuelve a
        # sortear: un cliente con OTIF malo y tickets impecables no existe, y
        # sembrarlo asi haria que el desglose del puntaje se contradiga solo.
        floja = cliente.id in problematicas
        score_otif = az.randrange(38, 68) if floja else az.randrange(78, 99)
        score_pagos = az.randrange(30, 62) if floja else az.randrange(72, 100)
        health = round((score_tickets * 0.25 + score_nps * 0.25 +
                        score_contratos * 0.20 + score_otif * 0.20 +
                        score_pagos * 0.10))

        cliente.health_score = health
        cliente.lead_score = min(100, health + az.randrange(-10, 11))
        db.add(CRMSaludCliente(
            cliente_id=cliente.id, fecha_calculo=hasta, health_score=health,
            score_otif=score_otif, score_tickets=score_tickets,
            score_pagos=score_pagos, score_nps=score_nps,
            score_contratos=score_contratos,
            riesgo_churn=Decimal(max(0, 100 - health)) / Decimal(2),
            prediccion_ia=("Cuenta estable; se puede proponer ampliación de alcance."
                           if health >= 75 else
                           "Riesgo moderado: hay tickets sin cerrar y la nota de "
                           "servicio viene cayendo." if health >= 50 else
                           "Riesgo alto de pérdida. Conviene una visita del "
                           "gerente antes de la renovación.")))

        # Por debajo de 70 se abre un riesgo. No es un numero redondo por
        # gusto: con 60 no entraba nadie y la pantalla de retencion quedaba
        # vacia, que es peor que una alarma temprana de mas.
        if health < 70:
            db.add(CRMRiesgoCliente(
                cliente_id=cliente.id,
                tipo_riesgo="Deterioro del nivel de servicio",
                nivel=(NivelRiesgoClienteEnum.CRITICO if health < 50
                       else NivelRiesgoClienteEnum.ALTO if health < 62
                       else NivelRiesgoClienteEnum.MEDIO),
                descripcion=f"Puntaje de salud en {health} con {abiertos} "
                            f"ticket(s) sin cerrar.",
                plan_mitigacion="Reunión de recuperación con el gerente de cuenta "
                                "y plan de acción a 30 días.",
                activo=True))
    await confirmar()

    # ── Cuentas clave y objetivos ─────────────────────────────────────────────
    #
    # Clave es quien tiene contrato y potencial alto. Marcar a todo el mundo
    # como cuenta clave es lo mismo que no marcar a nadie.
    for cliente in activos:
        if (cliente.potencial_anual or 0) < 500_000_000:
            continue
        db.add(CRMCuentaClave(
            cliente_id=cliente.id, ejecutivo_id=cliente.ejecutivo_id,
            objetivo_anual=cliente.potencial_anual,
            ingreso_actual=cliente.ingresos_ytd,
            estrategia="Ampliar el alcance a las regionales aún no cubiertas y "
                       "asegurar la renovación con doce meses de anticipación.",
            proxima_reunion=hasta + timedelta(days=az.randrange(5, 40)),
            nivel_riesgo=(NivelRiesgoClienteEnum.ALTO if cliente.health_score < 55
                          else NivelRiesgoClienteEnum.MEDIO if cliente.health_score < 75
                          else NivelRiesgoClienteEnum.BAJO)))

    # Lo logrado es el valor del PRIMER AÑO de cada contrato ganado, no el del
    # contrato completo. Contar entero un contrato a 24 meses contra una meta
    # anual da cumplimientos del 250%, y una pantalla donde todo el mundo pasa
    # del 200% no sirve para decidir nada.
    ganado_por_ejec: Dict[int, Decimal] = {}
    contrato_por_opo = {c.oportunidad_id: c for c in contratos}
    for o in oportunidades:
        if o.estado != EstadoOportunidadEnum.CIERRE_GANADO or not o.ejecutivo_id:
            continue
        con = contrato_por_opo.get(o.id)
        primer_ano = ((con.valor_mensual or Decimal(0)) * Decimal(12)
                      if con else (o.valor_contratado or Decimal(0)))
        ganado_por_ejec[o.ejecutivo_id] = (
            ganado_por_ejec.get(o.ejecutivo_id, Decimal(0)) + primer_ano)
    for e in ejecutivos:
        logrado = ganado_por_ejec.get(e.id, Decimal(0))
        meta = e.meta_anual or Decimal(1)
        db.add(CRMObjetivoComercial(
            ejecutivo_id=e.id, periodo=str(hasta.year),
            tipo_objetivo="Ventas nuevas", meta=meta, logrado=logrado,
            porcentaje=(logrado / meta * 100).quantize(Decimal("0.01"))))
    await confirmar()

    # ── Actividades pendientes ────────────────────────────────────────────────
    for o in oportunidades:
        if o.estado in (EstadoOportunidadEnum.CIERRE_GANADO,
                        EstadoOportunidadEnum.CIERRE_PERDIDO):
            continue
        db.add(CRMActividad(
            cliente_id=o.cliente_id, oportunidad_id=o.id,
            ejecutivo_id=o.ejecutivo_id, tipo=az.choice(["LLAMADA", "REUNION", "CORREO"]),
            asunto=az.choice(["Confirmar el alcance con operaciones",
                              "Enviar la propuesta ajustada",
                              "Agendar visita a la bodega del cliente",
                              "Pedir los volúmenes reales del último trimestre"]),
            descripcion=f"Relacionada con {o.codigo}.",
            fecha_vencimiento=datetime.combine(
                hasta + timedelta(days=az.randrange(1, 25)), time(10)),
            completada=False,
            prioridad=("ALTA" if o.probabilidad >= 60 else "MEDIA")))
    await confirmar()

    # ── Campañas: a quién se le envió y qué pasó ──────────────────────────────
    for cam in campanas:
        alcanzados = az.sample(clientes, min(len(clientes), az.randrange(8, 21)))
        generados = convertidos = 0
        ingresos = Decimal(0)
        for c in alcanzados:
            abierto = az.random() < 0.55
            respondido = abierto and az.random() < 0.35
            convertido = respondido and az.random() < 0.30
            db.add(CRMCampanaCliente(
                campana_id=cam.id, cliente_id=c.id, enviado=True,
                abierto=abierto, respondido=respondido, convertido=convertido))
            if respondido:
                generados += 1
            if convertido:
                convertidos += 1
                ingresos += (c.ingresos_ytd or Decimal(0)) / Decimal(4)
        cam.leads_generados = generados
        cam.conversiones = convertidos
        cam.ingresos_generados = ingresos.quantize(Decimal("1"))
    await confirmar()

    # ── KPI diarios: resumen de lo sembrado ───────────────────────────────────
    #
    # Se calculan sobre los mismos objetos que ya están en memoria. Si se
    # inventaran aparte, el tablero y las listas dirían cosas distintas del
    # mismo mes, y quien lo note deja de creerle a los dos.
    dia = desde
    n_kpi = 0
    while dia <= hasta:
        if not _habil(dia):
            dia += timedelta(days=1)
            continue
        hasta_hoy = lambda x: (x.created_at.date() if x.created_at else desde) <= dia

        cli_hoy = [c for c in clientes if hasta_hoy(c)] or clientes
        leads_hoy = [l for l in leads if hasta_hoy(l)]
        opo_hoy = [o for o in oportunidades if hasta_hoy(o)]
        opo_vivas = [o for o in opo_hoy if o.fecha_cierre is None or o.fecha_cierre > dia]
        cerradas = [o for o in opo_hoy if o.fecha_cierre and o.fecha_cierre <= dia]
        ganadas = [o for o in cerradas if o.estado == EstadoOportunidadEnum.CIERRE_GANADO]
        tk_hoy = [t for t in tickets if hasta_hoy(t)]
        tk_abiertos = [t for t in tk_hoy
                       if t.fecha_resolucion is None or t.fecha_resolucion.date() > dia]
        con_hoy = [c for c in contratos
                   if c.fecha_inicio and c.fecha_inicio <= dia]
        con_vivos = [c for c in con_hoy if c.fecha_fin and c.fecha_fin >= dia]
        por_vencer = [c for c in con_vivos
                      if c.fecha_fin and (c.fecha_fin - dia).days <= 90]
        notas = [t.satisfaccion for t in tk_hoy if t.satisfaccion]

        pipeline = sum((o.valor_estimado or Decimal(0)) for o in opo_vivas)
        activos_hoy = [c for c in cli_hoy
                       if c.estado == EstadoClienteEnum.CLIENTE_ACTIVO]

        db.add(CRMKPIDiario(
            fecha=dia,
            total_clientes=len(cli_hoy), clientes_activos=len(activos_hoy),
            total_leads=len(leads_hoy),
            leads_calientes=sum(1 for l in leads_hoy if l.score >= 70),
            pipeline_valor=Decimal(pipeline).quantize(Decimal("1")),
            oportunidades_activas=len(opo_vivas),
            tasa_conversion=(Decimal(len(opo_hoy)) / Decimal(len(leads_hoy)) * 100
                             ).quantize(Decimal("0.01")) if leads_hoy else Decimal(0),
            win_rate=(Decimal(len(ganadas)) / Decimal(len(cerradas)) * 100
                      ).quantize(Decimal("0.01")) if cerradas else Decimal(0),
            tickets_abiertos=len(tk_abiertos),
            tickets_escalados=sum(1 for t in tk_abiertos
                                  if t.estado == EstadoTicketEnum.ESCALADO),
            nps_promedio=(Decimal(sum(notas)) / Decimal(len(notas)) * 20
                          ).quantize(Decimal("0.01")) if notas else Decimal(0),
            csat_promedio=(Decimal(sum(notas)) / Decimal(len(notas))
                           ).quantize(Decimal("0.01")) if notas else Decimal(0),
            contratos_activos=len(con_vivos), contratos_por_vencer=len(por_vencer),
            ingresos_mes=sum((c.valor_mensual or Decimal(0)) for c in con_vivos),
            churn_rate=(Decimal(len(con_hoy) - len(con_vivos))
                        / Decimal(len(con_hoy)) * 100).quantize(Decimal("0.01"))
                       if con_hoy else Decimal(0)))
        n_kpi += 1
        if n_kpi % 40 == 0:
            await confirmar()
        dia += timedelta(days=1)
    await confirmar()
    avisar(f"  {n_kpi} días de indicadores")

    return {
        "ejecutivos": len(ejecutivos), "clientes": len(clientes),
        "leads": len(leads), "oportunidades": len(oportunidades),
        "cotizaciones": len(cotizaciones), "contratos": len(contratos),
        "tickets": len(tickets), "campanas": len(campanas), "kpis": n_kpi,
    }


async def verificar(db: AsyncSession) -> dict:
    """Comprueba que el embudo sea un embudo y que las cifras se puedan rehacer.

    Tres cosas, y las tres tienen que dar cero. Si una falla, el módulo enseña
    un tablero que no se sostiene al pinchar una cifra, que es peor que no
    enseñar nada.
    """
    cot_descuadradas = (await db.execute(text("""
        SELECT count(*) FROM (
          SELECT c.id, c.subtotal, c.iva, c.total,
                 COALESCE(SUM(i.total), 0) AS suma
            FROM crm_cotizacion c
            LEFT JOIN crm_cotizacion_item i ON i.cotizacion_id = c.id
           GROUP BY c.id, c.subtotal, c.iva, c.total
        ) t
        WHERE abs(subtotal - suma) > 1
           OR abs(total - (subtotal + iva)) > 1"""))).scalar() or 0

    # Un contrato sin oportunidad ganada detrás es un contrato que apareció de
    # la nada: rompe la trazabilidad de todo el embudo.
    con_sin_origen = (await db.execute(text("""
        SELECT count(*) FROM crm_contrato c
         WHERE c.oportunidad_id IS NULL
            OR NOT EXISTS (SELECT 1 FROM crm_oportunidad o
                            WHERE o.id = c.oportunidad_id
                              AND o.estado = 'CIERRE_GANADO')"""))).scalar() or 0

    # Un cliente activo sin contrato tampoco puede ser: es lo que lo hizo cliente.
    activos_sin_contrato = (await db.execute(text("""
        SELECT count(*) FROM crm_cliente c
         WHERE c.estado = 'CLIENTE_ACTIVO'
           AND NOT EXISTS (SELECT 1 FROM crm_contrato k
                            WHERE k.cliente_id = c.id)"""))).scalar() or 0

    pipeline = (await db.execute(text("""
        SELECT COALESCE(SUM(valor_estimado), 0) FROM crm_oportunidad
         WHERE estado NOT IN ('CIERRE_GANADO', 'CIERRE_PERDIDO')"""))).scalar() or 0
    contratado = (await db.execute(text(
        "SELECT COALESCE(SUM(valor_total), 0) FROM crm_contrato"))).scalar() or 0

    return {
        "cotizaciones_descuadradas": int(cot_descuadradas),
        "contratos_sin_oportunidad_ganada": int(con_sin_origen),
        "clientes_activos_sin_contrato": int(activos_sin_contrato),
        "pipeline_abierto": round(float(pipeline), 2),
        "total_contratado": round(float(contratado), 2),
    }
