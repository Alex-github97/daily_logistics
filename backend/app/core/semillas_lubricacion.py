"""
Configuración de arranque de lubricación.

Un módulo de análisis con los catálogos vacíos no se puede usar: no hay contra
qué evaluar una muestra, así que la primera carga de datos no diría nada. Estas
semillas dejan el módulo operable desde el primer día, y todo lo sembrado es
editable —el objetivo es no arrancar en blanco, no imponer criterios.

LOS CÓDIGOS DE PARÁMETRO NO SON ARBITRARIOS
Coinciden exactamente con los que ya reconoce el lector de boletines
(`lubricacion.py`). Gracias a eso, lo que el OCR extrae de un PDF entra directo
como resultados sin tabla de traducción en el medio.

SOBRE LOS LÍMITES SEMBRADOS
Son valores de arranque de uso común para motor diésel, no la especificación de
ningún fabricante. Sirven para que el semáforo funcione desde el principio y
hay que reemplazarlos por los del OEM o los del laboratorio de cada empresa: la
fuente queda marcada como «NORMA» justamente para que se note cuáles todavía no
se han ajustado.
"""
from typing import Any, Dict, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.lubricacion import (
    LubeTipoCompartimento, LubeParametro, LubeLimite,
    LubeMetodoMuestreo, LubeMotivoDrenaje, LubeModoFalla,
)

# ── Parámetros ───────────────────────────────────────────────────────────────
# (código, nombre, unidad, grupo, origen probable, texto?, bidireccional?)
PARAMETROS: List[tuple] = [
    # Metales de desgaste: cada uno delata una pieza distinta, y esa traducción
    # es la que convierte un número en un diagnóstico.
    ("fe", "Hierro (Fe)", "ppm", "DESGASTE", "Camisas, anillos, engranajes, árbol de levas", False, False),
    ("cr", "Cromo (Cr)", "ppm", "DESGASTE", "Anillos cromados, rodamientos", False, False),
    ("pb", "Plomo (Pb)", "ppm", "DESGASTE", "Cojinetes de biela y bancada", False, False),
    ("cu", "Cobre (Cu)", "ppm", "DESGASTE", "Cojinetes, bujes, enfriador de aceite", False, False),
    ("sn", "Estaño (Sn)", "ppm", "DESGASTE", "Recubrimiento de cojinetes", False, False),
    ("al", "Aluminio (Al)", "ppm", "DESGASTE", "Pistones, bombas, carcasas", False, False),
    ("ni", "Níquel (Ni)", "ppm", "DESGASTE", "Aleaciones de válvulas y ejes", False, False),
    ("mo", "Molibdeno (Mo)", "ppm", "DESGASTE", "Anillos, o aditivo antifricción", False, False),
    # Contaminantes: de dónde entra la suciedad.
    ("si", "Silicio (Si)", "ppm", "CONTAMINACION", "Polvo y tierra: filtro de aire o sellos", False, False),
    ("na", "Sodio (Na)", "ppm", "CONTAMINACION", "Refrigerante o agua salina", False, False),
    ("k", "Potasio (K)", "ppm", "CONTAMINACION", "Refrigerante", False, False),
    ("agua", "Agua", "%", "CONTAMINACION", "Condensación, refrigerante, lavado", False, False),
    ("combustible", "Dilución por combustible", "%", "CONTAMINACION", "Inyección deficiente, ralentí excesivo", False, False),
    ("hollin", "Hollín", "%", "CONTAMINACION", "Combustión incompleta, filtro de aire", False, False),
    ("glicol", "Glicol", "ppm", "CONTAMINACION", "Fuga de refrigerante: empaques o culata", False, False),
    ("iso4406", "Código ISO 4406", "cód.", "CONTAMINACION", "Limpieza del aceite: partículas por mililitro", True, False),
    ("pq", "Índice PQ", "—", "CONTAMINACION", "Partículas ferrosas grandes que la espectrometría no ve", False, False),
    # Aditivos: si caen, el aceite perdió su protección.
    ("ca", "Calcio (Ca)", "ppm", "ADITIVO", "Detergente", False, False),
    ("mg", "Magnesio (Mg)", "ppm", "ADITIVO", "Detergente", False, False),
    ("zn", "Zinc (Zn)", "ppm", "ADITIVO", "Antidesgaste (ZDDP)", False, False),
    ("p", "Fósforo (P)", "ppm", "ADITIVO", "Antidesgaste", False, False),
    ("b", "Boro (B)", "ppm", "ADITIVO", "Dispersante, o refrigerante", False, False),
    ("ba", "Bario (Ba)", "ppm", "ADITIVO", "Detergente", False, False),
    # Propiedades del fluido.
    ("viscosidad", "Viscosidad 40 °C", "cSt", "PROPIEDAD", "Alejarse en cualquier dirección es problema", False, True),
    ("visc100", "Viscosidad 100 °C", "cSt", "PROPIEDAD", "Dilución si baja, oxidación si sube", False, True),
    ("indice_viscosidad", "Índice de viscosidad", "—", "PROPIEDAD", None, False, True),
    ("tbn", "TBN", "mgKOH/g", "PROPIEDAD", "Reserva alcalina: peligroso cuando BAJA", False, False),
    ("tan", "TAN", "mgKOH/g", "PROPIEDAD", "Acidez: peligroso cuando sube", False, False),
    ("oxidacion", "Oxidación", "Abs/cm", "PROPIEDAD", "Envejecimiento por temperatura", False, False),
    ("nitracion", "Nitración", "Abs/cm", "PROPIEDAD", "Gases de combustión (más en gas natural)", False, False),
    ("sulfatacion", "Sulfatación", "Abs/cm", "PROPIEDAD", "Azufre del combustible", False, False),
]

# ── Tipos de compartimento ───────────────────────────────────────────────────
# (código, nombre, unidad de vida, descripción)
TIPOS_COMPARTIMENTO: List[tuple] = [
    ("MOT", "Motor diésel", "HORAS", "Cárter del motor de combustión"),
    ("HID", "Sistema hidráulico", "HORAS", "Depósito y circuito hidráulico"),
    ("TRA", "Transmisión", "HORAS", "Caja manual o automática"),
    ("DIF", "Diferencial", "KM", "Puente y corona"),
    ("MFI", "Mando final", "HORAS", "Reductores de rueda o de oruga"),
    ("COM", "Compresor", "HORAS", "Compresor de aire o de refrigeración"),
    ("GEN", "Generador", "HORAS", "Grupo electrógeno"),
    ("ENG", "Caja de engranajes", "HORAS", "Reductores industriales"),
    ("GRA", "Puntos de grasa", "DIAS", "Engrase por calendario, sin análisis"),
]

# ── Métodos de muestreo ──────────────────────────────────────────────────────
# La calidad no es un adorno: define si el dato es comparable con el histórico.
METODOS: List[tuple] = [
    ("Puerto de muestreo dedicado", "RECOMENDADO",
     "Válvula instalada en la línea presurizada, antes del filtro. Es el único que "
     "toma aceite en circulación y da resultados repetibles."),
    ("Sonda por tubo de varilla", "ACEPTABLE",
     "Con tubo nuevo por muestra y a media profundidad. Repetible si se respeta "
     "siempre la misma profundidad."),
    ("Por el tapón de drenaje", "NO_RECOMENDADO",
     "Arrastra el sedimento del fondo y da lecturas altas que no representan el "
     "aceite en circulación. Sirve solo si no hay otra opción, y hay que saber que "
     "sus valores no son comparables con los demás."),
    ("Muestra del aceite drenado", "NO_RECOMENDADO",
     "Tomada del recipiente después del cambio. Solo indica una tendencia gruesa."),
]

# ── Motivos de drenaje ───────────────────────────────────────────────────────
# (código, nombre, categoría, evitable, descripción)
MOTIVOS_DRENAJE: List[tuple] = [
    ("CAL", "Cumplió el intervalo programado", "CALENDARIO", False,
     "Cambio por plan, sin evidencia de que el aceite estuviera agotado."),
    ("CON", "Aceite agotado por condición", "CONDICION", False,
     "El análisis mostró que el aceite llegó al final de su vida útil."),
    ("CTM", "Contaminación", "CONTAMINACION", True,
     "Agua, refrigerante, combustible o suciedad por encima del límite."),
    ("FAL", "Falla del equipo", "FALLA", True,
     "Se drenó a causa de una falla mecánica."),
    ("INT", "Intervención mayor", "INTERVENCION", False,
     "Se drenó por una reparación, no porque el aceite lo pidiera."),
    ("ERR", "Producto equivocado", "CONTAMINACION", True,
     "Se cargó un lubricante distinto al especificado y hubo que sacarlo."),
]

# ── Modos de falla del lubricante ────────────────────────────────────────────
# (código, nombre, categoría, severidad, acción sugerida)
MODOS_FALLA: List[tuple] = [
    ("DESG-ABR", "Desgaste abrasivo", "DESGASTE", "GRAVE",
     "Revisar filtro y ductos de aire, sellos y respiraderos. Silicio alto con hierro alto."),
    ("DESG-ADH", "Desgaste adhesivo", "DESGASTE", "GRAVE",
     "Verificar presión de aceite, holguras y temperatura de operación."),
    ("DESG-COJ", "Desgaste de cojinetes", "DESGASTE", "GRAVE",
     "Plomo, estaño o cobre en alza. Revisar presión de aceite y filtración."),
    ("CONT-AGU", "Contaminación por agua", "CONTAMINACION", "GRAVE",
     "Buscar condensación, fuga de refrigerante o entrada por lavado."),
    ("CONT-REF", "Entrada de refrigerante", "REFRIGERANTE", "GRAVE",
     "Sodio, potasio o glicol presentes. Revisar empaques, culata y enfriador."),
    ("CONT-SUC", "Ingreso de suciedad", "CONTAMINACION", "MODERADO",
     "Silicio alto. Revisar filtro de aire, sellos y procedimiento de llenado."),
    ("DIL-COMB", "Dilución por combustible", "DILUCION", "GRAVE",
     "Viscosidad a la baja. Revisar inyectores, anillos y exceso de ralentí."),
    ("DEG-OXI", "Oxidación del aceite", "DEGRADACION", "MODERADO",
     "Temperatura de operación alta o intervalo excedido."),
    ("DEG-TBN", "Agotamiento de la reserva alcalina", "DEGRADACION", "MODERADO",
     "TBN bajo. Acortar el intervalo o revisar el azufre del combustible."),
    ("ADI-AGO", "Agotamiento de aditivos", "ADITIVOS", "MODERADO",
     "Zinc y fósforo a la baja: el aceite perdió su protección antidesgaste."),
    ("PROD-ERR", "Producto incorrecto o mezcla", "DEGRADACION", "GRAVE",
     "El perfil de aditivos no corresponde al producto declarado."),
]

# ── Límites de arranque para motor diésel ────────────────────────────────────
# (código de parámetro, tipo, marginal_min, marginal_max, crítico_min, crítico_max)
LIMITES_MOTOR: List[tuple] = [
    ("fe", "ABSOLUTO", None, 100, None, 150),
    ("cu", "ABSOLUTO", None, 30, None, 50),
    ("pb", "ABSOLUTO", None, 30, None, 50),
    ("cr", "ABSOLUTO", None, 15, None, 25),
    ("al", "ABSOLUTO", None, 20, None, 35),
    ("si", "ABSOLUTO", None, 20, None, 30),
    ("na", "ABSOLUTO", None, 30, None, 60),
    ("k", "ABSOLUTO", None, 20, None, 40),
    ("agua", "ABSOLUTO", None, 0.2, None, 0.5),
    ("combustible", "ABSOLUTO", None, 3.0, None, 5.0),
    ("hollin", "ABSOLUTO", None, 2.0, None, 3.0),
    ("glicol", "ABSOLUTO", None, 1, None, 50),
    # El TBN es al revés: el peligro es que caiga.
    ("tbn", "ABSOLUTO", 4.0, None, 2.5, None),
    ("tan", "ABSOLUTO", None, 2.5, None, 4.0),
    # La viscosidad se vigila en las dos direcciones.
    ("viscosidad", "ABSOLUTO", 90, 125, 80, 140),
    # Tasa de cambio: por cada 100 horas de aceite. Es la señal temprana, y por
    # eso vale la pena sembrarla aunque los absolutos ya existan.
    ("fe", "TASA_CAMBIO", None, 8, None, 15),
    ("cu", "TASA_CAMBIO", None, 3, None, 6),
    ("si", "TASA_CAMBIO", None, 3, None, 6),
]


async def sembrar_lubricacion(db: AsyncSession) -> Dict[str, int]:
    """Siembra lo que falte. Es idempotente: se puede correr en cada arranque.

    No toca nada que ya exista —si alguien ajustó un límite, se respeta— porque
    esto corre en cada arranque del servidor y pisar la configuración de la
    empresa en cada despliegue sería inaceptable.
    """
    creados = {"parametros": 0, "tipos": 0, "metodos": 0, "motivos": 0,
               "modos": 0, "limites": 0}

    # Parámetros.
    r = await db.execute(select(LubeParametro.codigo))
    existentes = {c for (c,) in r.all()}
    for orden, (codigo, nombre, unidad, grupo, origen, texto, bidir) in enumerate(PARAMETROS):
        if codigo in existentes:
            continue
        db.add(LubeParametro(codigo=codigo, nombre=nombre, unidad=unidad, grupo=grupo,
                             origen_probable=origen, es_texto=texto,
                             bidireccional=bidir, orden=orden * 10))
        creados["parametros"] += 1

    # Tipos de compartimento.
    r = await db.execute(select(LubeTipoCompartimento.nombre))
    existentes = {n for (n,) in r.all()}
    for codigo, nombre, unidad, desc in TIPOS_COMPARTIMENTO:
        if nombre in existentes:
            continue
        db.add(LubeTipoCompartimento(codigo=codigo, nombre=nombre,
                                     unidad_vida=unidad, descripcion=desc))
        creados["tipos"] += 1

    # Métodos de muestreo.
    r = await db.execute(select(LubeMetodoMuestreo.nombre))
    existentes = {n for (n,) in r.all()}
    for nombre, calidad, desc in METODOS:
        if nombre in existentes:
            continue
        db.add(LubeMetodoMuestreo(nombre=nombre, calidad=calidad, descripcion=desc))
        creados["metodos"] += 1

    # Motivos de drenaje.
    r = await db.execute(select(LubeMotivoDrenaje.nombre))
    existentes = {n for (n,) in r.all()}
    for codigo, nombre, categoria, evitable, desc in MOTIVOS_DRENAJE:
        if nombre in existentes:
            continue
        db.add(LubeMotivoDrenaje(codigo=codigo, nombre=nombre, categoria=categoria,
                                 evitable=evitable, descripcion=desc))
        creados["motivos"] += 1

    # Modos de falla.
    r = await db.execute(select(LubeModoFalla.codigo))
    existentes = {c for (c,) in r.all()}
    for codigo, nombre, categoria, severidad, accion in MODOS_FALLA:
        if codigo in existentes:
            continue
        db.add(LubeModoFalla(codigo=codigo, nombre=nombre, categoria=categoria,
                             severidad=severidad, accion_sugerida=accion))
        creados["modos"] += 1

    await db.commit()

    # Límites del motor: necesitan que los parámetros y el tipo ya tengan id.
    r = await db.execute(select(LubeTipoCompartimento).where(
        LubeTipoCompartimento.nombre == "Motor diésel"))
    motor = r.scalar_one_or_none()
    if motor:
        r = await db.execute(select(LubeParametro))
        por_codigo = {p.codigo: p.id for p in r.scalars().all()}
        r = await db.execute(select(LubeLimite.parametro_id, LubeLimite.tipo)
                             .where(LubeLimite.tipo_compartimento_id == motor.id))
        ya = {(pid, tipo) for pid, tipo in r.all()}
        for codigo, tipo, mar_min, mar_max, cri_min, cri_max in LIMITES_MOTOR:
            pid = por_codigo.get(codigo)
            if not pid or (pid, tipo) in ya:
                continue
            db.add(LubeLimite(
                parametro_id=pid, tipo_compartimento_id=motor.id, tipo=tipo,
                marginal_min=mar_min, marginal_max=mar_max,
                critico_min=cri_min, critico_max=cri_max,
                fuente="NORMA",
                nota="Valor de arranque de uso común. Reemplazar por el del "
                     "fabricante o el del laboratorio."))
            creados["limites"] += 1
        await db.commit()

    return creados
