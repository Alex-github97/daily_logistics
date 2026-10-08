"""
Lubricación — la interpretación según la norma, no según la costumbre.

POR QUÉ ESTE ARCHIVO EXISTE
La primera versión del informe reproducía la lectura del comité técnico de la
empresa. Servía, pero no se podía defender ante un auditor ni ante el
fabricante del motor: «lo interpretamos así» no es un criterio. Acá el
criterio queda escrito, con la fuente al lado de cada número, y la pantalla lo
muestra. Si alguien discute una conclusión, la discusión es contra una norma
publicada y no contra una opinión.

LA DISTINCIÓN QUE NO SE PUEDE BORRAR
Las normas ASTM e ISO de análisis de aceite dicen CÓMO SE MIDE, casi nunca
CUÁNDO ES MALO. ASTM D445 define el ensayo de viscosidad cinemática; no dice
que un 20 % de desviación condene la carga. Confundir las dos cosas —citar
«ASTM D445» como si fuera el origen de un umbral— es una cita falsa, y es un
error muy común en los informes de laboratorio.

Por eso cada límite lleva DOS campos separados:

  metodo    la norma del ensayo. Es lo que da trazabilidad al número medido.
  criterio  de dónde sale el umbral. Y hay solo tres orígenes legítimos:

     1. EL FABRICANTE. Los límites de condena del OEM del motor. Mandan sobre
        todo lo demás, pero son específicos de cada familia y no están en una
        norma pública.
     2. LA PROPIA FLOTA — ASTM D7720. La norma que sí trata de límites: los
        deriva estadísticamente de la población medida. Es lo que corresponde
        para los metales de desgaste, donde un valor absoluto universal no
        existe: 50 ppm de hierro es rutina en un motor grande y es alarma en
        una caja de engranajes.
     3. LA LITERATURA DE REFERENCIA. Tormos para motor diésel, y el cuerpo de
        práctica de ICML/Noria. Se cita como lo que es: práctica publicada, no
        norma obligatoria.

Y LO QUE MANDA POR ENCIMA DE LOS UMBRALES: LA TENDENCIA
ASTM D7669 —guía de análisis de tendencia de datos de condición— y ASTM D4378
y D6224 construyen el diagnóstico sobre la VARIACIÓN, no sobre el valor
suelto. Es la diferencia entre un motor con 60 ppm de hierro estable desde
hace dos años —que es su nivel— y uno que pasó de 12 a 55 en una muestra. El
segundo está fallando y el primero no, y un informe que solo compare contra un
tope los reporta igual.

FUENTES
  ASTM D5185   metales, aditivos y contaminantes por ICP-AES
  ASTM D2896   TBN por titulación con ácido perclórico
  ASTM D4739   TBN por titulación con ácido clorhídrico (da más bajo que D2896)
  ASTM D664    TAN por titulación potenciométrica
  ASTM D445    viscosidad cinemática
  ASTM D6304   agua por Karl Fischer coulométrico
  ASTM D2982   detección de anticongelante a base de glicol (cualitativa)
  ASTM D7844   hollín por FTIR
  ASTM E2412   monitoreo de condición por FTIR: oxidación, nitración, sulfatación
  ASTM D7593   dilución por combustible por cromatografía de gases
  ASTM D7720   fijación estadística de límites de alarma sobre la propia población
  ASTM D7669   análisis de tendencia de datos de condición del lubricante
  ASTM D4378   monitoreo en servicio (turbina; su método de desviación relativa
               es el que se usa de forma general para viscosidad y TAN)
  ASTM D6224   monitoreo en servicio de equipo auxiliar de planta
  ASTM D8184   índice de partículas ferrosas
  ISO 4406     código de limpieza por conteo de partículas
  SAE J300     clasificación de viscosidad de aceites de motor
  Tormos, B.   «Análisis de aceite usado en motores diésel» (UPV / Reverté)
  ICML / Noria cuerpo de práctica de análisis de lubricantes en servicio
"""
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple

# ══════════════════════════════════════════════════════════════════════════════
# El registro de fuentes
#
# Aparte, y con el título completo, para que la pantalla pueda mostrar de qué
# habla cada sigla. «ASTM D7720» no le dice nada a nadie que no la conozca.
# ══════════════════════════════════════════════════════════════════════════════

FUENTES: Dict[str, Dict[str, str]] = {
    "ASTM D5185": {
        "titulo": "Determinación multielemental por ICP-AES en aceites usados y "
                  "aceites base",
        "define": "Cómo se miden los metales de desgaste, los aditivos y los "
                  "contaminantes metálicos. No fija límites.",
    },
    "ASTM D2896": {
        "titulo": "Número base (TBN) por titulación potenciométrica con ácido "
                  "perclórico",
        "define": "La reserva alcalina del aceite. Da valores más altos que "
                  "D4739 sobre la misma muestra: los dos métodos no son "
                  "intercambiables en una tendencia.",
    },
    "ASTM D4739": {
        "titulo": "Número base por titulación potenciométrica con ácido "
                  "clorhídrico",
        "define": "Reserva alcalina efectiva. Es el método que la literatura "
                  "de motor recomienda para aceite en servicio.",
    },
    "ASTM D664": {
        "titulo": "Número ácido (TAN) por titulación potenciométrica",
        "define": "La acidez acumulada por oxidación y por azufre del "
                  "combustible.",
    },
    "ASTM D445": {
        "titulo": "Viscosidad cinemática de líquidos transparentes y opacos",
        "define": "El ensayo de viscosidad. El umbral no sale de acá.",
    },
    "ASTM D6304": {
        "titulo": "Agua por titulación culombimétrica Karl Fischer",
        "define": "Agua total, en ppm o en porcentaje.",
    },
    "ASTM D2982": {
        "titulo": "Detección de anticongelantes a base de glicol en aceite usado",
        "define": "Ensayo cualitativo: da positivo o negativo. Un positivo no "
                  "admite matices.",
    },
    "ASTM D7844": {
        "titulo": "Hollín en aceite de motor diésel usado por FTIR",
        "define": "El hollín en porcentaje de masa.",
    },
    "ASTM E2412": {
        "titulo": "Monitoreo de condición de fluidos por espectrometría FTIR "
                  "con análisis de tendencia",
        "define": "Oxidación, nitración y sulfatación. La norma es "
                  "explícitamente de TENDENCIA: los valores absolutos "
                  "dependen del equipo y de la línea base del aceite nuevo.",
    },
    "ASTM D7593": {
        "titulo": "Dilución por combustible en aceite de motor diésel por "
                  "cromatografía de gases",
        "define": "El combustible en porcentaje de volumen.",
    },
    "ASTM D7720": {
        "titulo": "Guía para evaluar estadísticamente datos de análisis de "
                  "aceite usado con el fin de fijar límites de alarma",
        "define": "La norma que sí trata de LÍMITES. Los deriva de la "
                  "distribución de la propia población: percentiles sobre "
                  "equipos comparables. Es el criterio correcto para los "
                  "metales de desgaste, donde no existe un tope universal.",
    },
    "ASTM D7669": {
        "titulo": "Guía para el análisis práctico de tendencia de datos de "
                  "condición del lubricante",
        "define": "Cómo se lee una tendencia: la tasa de cambio por unidad de "
                  "vida del aceite, y no el último número.",
    },
    "ASTM D4378": {
        "titulo": "Práctica de monitoreo en servicio de aceites minerales para "
                  "turbina",
        "define": "El método de desviación relativa contra el aceite nuevo "
                  "—viscosidad, TAN— que se aplica de forma general.",
    },
    "ASTM D6224": {
        "titulo": "Práctica de monitoreo en servicio de aceite lubricante de "
                  "equipo auxiliar de planta",
        "define": "El programa de monitoreo: frecuencia, parámetros, y la "
                  "distinción entre límite de precaución y límite de condena.",
    },
    "ASTM D8184": {
        "titulo": "Índice de partículas ferrosas en fluidos en servicio",
        "define": "Las partículas ferrosas grandes que la ICP no ve: por "
                  "encima de unas 5 µm el plasma no las disocia y no las "
                  "cuenta.",
    },
    "ISO 4406": {
        "titulo": "Código de contaminación por partículas sólidas de fluidos "
                  "hidráulicos",
        "define": "Tres números —≥4 µm, ≥6 µm, ≥14 µm— que solo tienen "
                  "sentido juntos. Cada código es un factor de dos en la "
                  "cantidad de partículas.",
    },
    "SAE J300": {
        "titulo": "Clasificación de viscosidad de aceites de motor",
        "define": "La banda de viscosidad a 100 °C de cada grado. Permite "
                  "derivar el valor de referencia del aceite nuevo a partir "
                  "del grado cargado, sin tener que medirlo.",
    },
    "Tormos": {
        "titulo": "Tormos, B. — «Análisis de aceite usado en motores diésel», "
                  "Universitat Politècnica de València / Reverté",
        "define": "Referencia de motor diésel: criterios de contaminación por "
                  "agua y combustible, agotamiento de la reserva alcalina, y "
                  "el peso de la tasa de desgaste sobre el valor absoluto.",
    },
    "ICML": {
        "titulo": "International Council for Machinery Lubrication — cuerpo de "
                  "conocimiento MLA/MLT",
        "define": "Práctica de campo: interpretación combinada de elementos, "
                  "relación Si:Al para confirmar polvo, lavado de cobre en "
                  "enfriadores nuevos, calidad de la toma de muestra.",
    },
}

# Qué naturaleza tiene cada umbral. Se muestra en pantalla junto al hallazgo,
# porque un límite del fabricante y un percentil de la propia flota no tienen
# la misma autoridad y quien decide tiene derecho a saber cuál está mirando.
NATURALEZA = {
    "NORMA": "Umbral tomado de una norma o de una banda normalizada.",
    "REFERENCIA": "Umbral de literatura de referencia publicada; no es norma "
                  "obligatoria.",
    "FLOTA": "Umbral derivado estadísticamente de esta misma flota, según "
             "ASTM D7720.",
    "OEM": "Límite de condena del fabricante, cargado en la configuración.",
    "TENDENCIA": "No es un tope: es una variación por unidad de vida del "
                 "aceite, según ASTM D7669.",
}


# ══════════════════════════════════════════════════════════════════════════════
# Límites de contaminación y de condición del aceite
#
# Estos sí tienen valores de referencia publicados, porque no dependen del
# tamaño ni de la metalurgia del motor: 0,2 % de agua es 0,2 % de agua en
# cualquier cárter. Los metales de desgaste NO están acá —van por percentil de
# la flota, más abajo— justamente porque para ellos un tope universal no
# existe.
#
# Estructura: código → (precaución, condena, dirección, método, criterio,
#                       naturaleza, porqué)
# dirección: ALTO   sube y es malo
#            BAJO   baja y es malo
#            DESVIO se compara contra una referencia en las dos direcciones
# ══════════════════════════════════════════════════════════════════════════════

LIMITES_MOTOR: Dict[str, Dict[str, Any]] = {
    "glicol": {
        "precaucion": 0.0, "condena": 0.0, "direccion": "ALTO",
        "metodo": "ASTM D2982", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "El ensayo es cualitativo: cualquier detección positiva "
                  "significa que hay refrigerante entrando. El glicol ataca "
                  "los cojinetes y forma depósitos que tapan conductos; no "
                  "hay un nivel «tolerable» que esperar a la próxima muestra.",
        "accion": "Parar y buscar la fuga: empaque de culata, enfriador de "
                  "aceite, camisas. Cambiar la carga después de cerrarla.",
    },
    "agua": {
        "precaucion": 0.1, "condena": 0.2, "direccion": "ALTO",
        "metodo": "ASTM D6304", "criterio": "Tormos", "naturaleza": "REFERENCIA",
        "porque": "Por encima de 0,1 % el agua ya hidroliza los aditivos y "
                  "arrastra los detergentes; por encima de 0,2 % desplaza la "
                  "película lubricante y produce corrosión y desgaste "
                  "adhesivo. El agua libre es mucho peor que la emulsionada.",
        "accion": "Determinar el origen —condensación por operación fría, "
                  "refrigerante, o lavado— antes de cambiar la carga: si es "
                  "refrigerante, cambiar el aceite no resuelve nada.",
    },
    "combustible": {
        "precaucion": 2.5, "condena": 5.0, "direccion": "ALTO",
        "metodo": "ASTM D7593", "criterio": "Tormos", "naturaleza": "REFERENCIA",
        "porque": "El combustible baja la viscosidad y con ella el espesor de "
                  "película. Cerca del 5 % la caída de viscosidad ya es "
                  "suficiente para que el régimen pase de hidrodinámico a "
                  "mixto en los cojinetes. Es el límite de condena que usan "
                  "los fabricantes de motor.",
        "accion": "Revisar inyección, y descartar ralentí prolongado y "
                  "regeneraciones incompletas del filtro de partículas. "
                  "Confirmar con la viscosidad: si el combustible sube y la "
                  "viscosidad no baja, sospechar del ensayo.",
    },
    "hollin": {
        "precaucion": 3.0, "condena": 5.0, "direccion": "ALTO",
        "metodo": "ASTM D7844", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "El hollín en sí no es abrasivo mientras el dispersante lo "
                  "mantenga en suspensión. El problema aparece cuando "
                  "aglomera: sube la viscosidad, tapa el filtro y el hollín "
                  "aglomerado sí desgasta el tren de válvulas. Un motor con "
                  "EGR tolera más hollín que uno sin recirculación.",
        "accion": "Revisar filtro de aire, inyección y tiempos. Si el aceite "
                  "es de bajo SAPS y el hollín es alto, verificar que el "
                  "producto cargado corresponde al motor.",
    },
    "tbn": {
        "precaucion": None, "condena": 2.0, "direccion": "BAJO",
        "metodo": "ASTM D4739", "criterio": "Tormos", "naturaleza": "REFERENCIA",
        "porque": "La reserva alcalina es lo que neutraliza los ácidos de la "
                  "combustión. El criterio de precaución no es un número "
                  "fijo sino la mitad del TBN del aceite nuevo; el de "
                  "condena, 2,0 mgKOH/g, es donde el aceite deja de "
                  "neutralizar. Si se mide por D2896 en vez de D4739 el valor "
                  "sale más alto y el umbral no es comparable.",
        "accion": "Acortar el intervalo. Si se repite en toda una familia, "
                  "revisar el azufre del combustible y el grado del aceite: "
                  "un TBN que se agota antes de tiempo suele ser combustible, "
                  "no motor.",
    },
    "tan": {
        "precaucion": None, "condena": None, "direccion": "ALTO",
        "metodo": "ASTM D664", "criterio": "ASTM D4378", "naturaleza": "NORMA",
        "porque": "No se juzga por el valor absoluto sino por el incremento "
                  "sobre el aceite nuevo —la desviación relativa de "
                  "D4378—, y por el cruce con el TBN: cuando el TAN alcanza "
                  "al TBN el aceite ya no tiene con qué neutralizar y empieza "
                  "la corrosión de los metales blandos.",
        "accion": "Cambiar la carga. Si el TAN sube sin que suba la "
                  "oxidación, sospechar contaminación con un ácido externo.",
    },
    "oxidacion": {
        "precaucion": 20.0, "condena": 30.0, "direccion": "ALTO",
        "metodo": "ASTM E2412", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "E2412 es una norma de tendencia: el número solo tiene "
                  "sentido contra la línea base del aceite nuevo y del mismo "
                  "equipo. Los valores de 20 y 30 Abs/cm son la práctica "
                  "corriente de los laboratorios para aceite de motor, no un "
                  "límite normalizado.",
        "accion": "Revisar temperatura de operación y el intervalo. La "
                  "oxidación alta anticipa subida de viscosidad y de TAN.",
    },
    "nitracion": {
        "precaucion": 20.0, "condena": 30.0, "direccion": "ALTO",
        "metodo": "ASTM E2412", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "La nitración viene del paso de gases de combustión al "
                  "cárter. Es la señal de blow-by por anillos o de exceso de "
                  "ralentí, y en motores a gas es el parámetro dominante.",
        "accion": "Prueba de blow-by. Revisar el sistema de ventilación del "
                  "cárter antes de culpar al aceite.",
    },
    "sulfatacion": {
        "precaucion": 25.0, "condena": 35.0, "direccion": "ALTO",
        "metodo": "ASTM E2412", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "Sale del azufre del combustible. Consume reserva alcalina, "
                  "así que sube junto con la caída del TBN y anticipa "
                  "corrosión.",
        "accion": "Verificar la calidad del combustible. Con azufre alto, el "
                  "intervalo tiene que ser más corto o el aceite de TBN más "
                  "alto.",
    },
    "si": {
        "precaucion": 20.0, "condena": 30.0, "direccion": "ALTO",
        "metodo": "ASTM D5185", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "El silicio es sílice: polvo. Es el contaminante más "
                  "destructivo del motor porque su dureza está justo en el "
                  "rango que raya camisas y anillos. Pero el silicio también "
                  "puede venir de un antiespumante o de un sellador reciente, "
                  "y eso no es polvo: la relación con el aluminio lo "
                  "distingue.",
        "accion": "Revisar todo el lado de admisión: filtro, abrazaderas, "
                  "mangueras, sello del filtro. Es un ingreso, no un "
                  "desgaste: el aceite nuevo no lo resuelve.",
    },
    "na": {
        "precaucion": 20.0, "condena": 40.0, "direccion": "ALTO",
        "metodo": "ASTM D5185", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "El sodio es el trazador del refrigerante, pero también es "
                  "aditivo de algunos aceites y viene del ambiente marino. "
                  "Solo confirma refrigerante cuando lo acompaña el potasio, "
                  "el boro o el glicol.",
        "accion": "Buscar la fuente antes de intervenir el motor.",
    },
    "k": {
        "precaucion": 20.0, "condena": 40.0, "direccion": "ALTO",
        "metodo": "ASTM D5185", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "El potasio casi no tiene otro origen que el refrigerante. "
                  "Es el trazador más específico de los tres.",
        "accion": "Revisar empaque de culata y enfriador de aceite.",
    },
    "pq": {
        "precaucion": 50.0, "condena": 100.0, "direccion": "ALTO",
        "metodo": "ASTM D8184", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "La ICP no ve las partículas grandes: por encima de unas "
                  "5 µm el plasma no las disocia. El índice ferroso las "
                  "cuenta. Un PQ alto con el hierro por ICP normal es la "
                  "firma del desgaste severo —descamación, fatiga— y es "
                  "justamente el caso que un informe de solo espectrometría "
                  "declara sano.",
        "accion": "Ferrografía analítica para ver la morfología de la "
                  "partícula. No esperar la próxima muestra.",
    },
}

# Los mismos criterios, ajustados para lo que no es motor. Lo que cambia de
# verdad es la sensibilidad al agua y a las partículas: un sistema hidráulico
# se arruina con contaminación que un cárter tolera sin enterarse.
LIMITES_HIDRAULICO: Dict[str, Dict[str, Any]] = {
    "agua": {
        "precaucion": 0.02, "condena": 0.05, "direccion": "ALTO",
        "metodo": "ASTM D6304", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "Un hidráulico trabaja con holguras de micras y presiones "
                  "altas: el agua que un motor tolera acá causa cavitación, "
                  "corrosión y bloqueo de servoválvulas. El criterio corriente "
                  "es mantenerse por debajo de 200 ppm.",
        "accion": "Revisar respiraderos y sellos. Deshidratar antes de "
                  "reponer aceite.",
    },
    "si": {
        "precaucion": 15.0, "condena": 25.0, "direccion": "ALTO",
        "metodo": "ASTM D5185", "criterio": "ICML", "naturaleza": "REFERENCIA",
        "porque": "En hidráulica el polvo no solo desgasta: erosiona los "
                  "asientos de las válvulas y se lleva la precisión del "
                  "sistema.",
        "accion": "Revisar respiraderos, sellos de vástago y el "
                  "procedimiento de llenado.",
    },
}


def limites_de(tipo_codigo: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Los límites que aplican a una familia de compartimento."""
    if (tipo_codigo or "").upper() in ("HID",):
        return {**LIMITES_MOTOR, **LIMITES_HIDRAULICO}
    return LIMITES_MOTOR


# ══════════════════════════════════════════════════════════════════════════════
# Viscosidad: la banda del grado SAE
#
# Acá sí hay una banda normalizada de verdad. SAE J300 define el rango de
# viscosidad cinemática a 100 °C de cada grado, así que el valor de referencia
# del aceite nuevo se deduce del grado cargado sin necesidad de medirlo. Es la
# única forma honesta de juzgar una viscosidad: contra el aceite que le
# corresponde, no contra un promedio de la flota.
# ══════════════════════════════════════════════════════════════════════════════

BANDA_SAE_100C: Dict[str, Tuple[float, float]] = {
    "20": (5.6, 9.3), "30": (9.3, 12.5), "40": (12.5, 16.3),
    "50": (16.3, 21.9), "60": (21.9, 26.1),
}

# Desviación relativa contra el aceite nuevo, el método de ASTM D4378. Los
# porcentajes son la práctica corriente para motor.
DESVIO_VISCOSIDAD = {"precaucion": 0.20, "condena": 0.30}


def grado_posterior(grado_sae: Optional[str]) -> Optional[str]:
    """El número que va después de la W: de «15W-40» saca «40».

    Es el que manda la viscosidad en caliente, que es la que lubrica. El
    número de antes de la W es un requisito de bombeo en frío y no dice nada
    sobre la película a temperatura de operación.
    """
    if not grado_sae:
        return None
    texto = grado_sae.upper().replace(" ", "")
    if "W-" in texto:
        cola = texto.split("W-", 1)[1]
    elif "W" in texto:
        cola = texto.split("W", 1)[1]
    else:
        cola = texto
    cola = "".join(c for c in cola if c.isdigit())
    return cola if cola in BANDA_SAE_100C else None


def referencia_viscosidad_100c(grado_sae: Optional[str]) -> Optional[float]:
    """El centro de la banda SAE J300 del grado, como valor del aceite nuevo."""
    g = grado_posterior(grado_sae)
    if not g:
        return None
    bajo, alto = BANDA_SAE_100C[g]
    return round((bajo + alto) / 2, 2)


# ══════════════════════════════════════════════════════════════════════════════
# Límites estadísticos — ASTM D7720
#
# Para los metales de desgaste no existe un tope universal, y por eso la norma
# que trata de límites los deriva de la población: se toma el conjunto de
# equipos comparables y se fija la alarma en un percentil alto de su propia
# distribución.
#
# POR QUÉ PERCENTIL Y NO MEDIA MÁS DOS SIGMAS
# Porque las distribuciones de metales de desgaste no son normales: tienen cola
# derecha larga. Con media+2σ, unos pocos equipos en falla arrastran la media y
# el límite queda por encima de casi todo, así que no alarma nunca. D7720
# contempla el enfoque no paramétrico justamente por esto.
#
# EL MÍNIMO DE MUESTRAS NO ES NEGOCIABLE
# Un percentil 97,5 sobre doce puntos es el punto más alto de doce, y llamarlo
# «límite de la flota» le da una autoridad que no tiene. Sin población
# suficiente esta capa se apaga y el diagnóstico se apoya solo en la tendencia.
#
# «EQUIPOS COMPARABLES» ES LA MITAD DE LA NORMA
# El percentil solo significa algo si la población es homogénea. Juntar los
# motores diésel con los sistemas hidráulicos y sacar un percentil de hierro de
# los dos produce un número que no describe a ninguno: los rangos normales son
# distintos por metalurgia y por volumen de aceite. Por eso los límites se
# calculan POR FAMILIA DE COMPARTIMENTO y cada muestra se juzga contra la suya.
# ══════════════════════════════════════════════════════════════════════════════

# A partir de qué correlación se da por cumplido en esta flota un eslabón de la
# cadena causal. No es un valor de significancia estadística: es el punto donde
# la relación es lo bastante fuerte como para actuar sobre ella.
UMBRAL_CONFIRMACION = 0.4

MINIMO_POBLACION_D7720 = 30
PERCENTIL_PRECAUCION = 90.0
PERCENTIL_CONDENA = 97.5

GRUPO_DESGASTE = {"fe", "cr", "pb", "cu", "sn", "al", "ni", "mo"}


def percentil(valores: List[float], p: float) -> Optional[float]:
    """Percentil por interpolación lineal. `None` si no hay datos."""
    if not valores:
        return None
    xs = sorted(valores)
    if len(xs) == 1:
        return xs[0]
    pos = (p / 100) * (len(xs) - 1)
    bajo = int(pos)
    alto = min(bajo + 1, len(xs) - 1)
    peso = pos - bajo
    return xs[bajo] * (1 - peso) + xs[alto] * peso


def limites_estadisticos(poblacion: Dict[str, List[float]],
                         criterio: Optional["Criterio"] = None,
                         ) -> Dict[str, Dict[str, Any]]:
    """Los límites de alarma derivados de la propia flota, según ASTM D7720.

    Recibe, por código de parámetro, todos los valores medidos en equipos
    comparables. Devuelve solo los parámetros con población suficiente: es
    preferible no tener límite estadístico que tener uno inventado.

    Los percentiles y la población mínima salen del criterio vigente, que puede
    traer los ajustes de la empresa.
    """
    criterio = criterio or CRITERIO_BASE
    minimo = int(criterio.constante("minimo_poblacion"))
    p_prec = criterio.constante("percentil_precaucion")
    p_cond = criterio.constante("percentil_condena")

    salida: Dict[str, Dict[str, Any]] = {}
    for codigo, valores in poblacion.items():
        limpios = [v for v in valores if v is not None]
        if len(limpios) < minimo:
            continue
        p90 = percentil(limpios, p_prec)
        p975 = percentil(limpios, p_cond)
        if p90 is None or p975 is None or p975 <= 0:
            continue
        salida[codigo] = {
            "precaucion": round(p90, 2), "condena": round(p975, 2),
            "direccion": "ALTO", "metodo": "ASTM D5185",
            "criterio": "ASTM D7720", "naturaleza": "FLOTA",
            "n": len(limpios),
            "mediana": round(percentil(limpios, 50) or 0, 2),
            "porque": f"Percentil {p_prec:g} y "
                      f"{p_cond:g} de las {len(limpios)} "
                      f"mediciones de esta familia de compartimento. Para los "
                      f"metales de desgaste no hay tope universal: 50 ppm de "
                      f"hierro es rutina en un motor grande y alarma en una "
                      f"caja de engranajes, así que la referencia correcta es "
                      f"la propia población de equipos comparables.",
            "accion": "Contrastar con la tasa de cambio antes de intervenir: "
                      "un valor alto y estable es el nivel de ese equipo.",
        }
    return salida


# ══════════════════════════════════════════════════════════════════════════════
# Tendencia — ASTM D7669
#
# El valor que de verdad diagnostica. Se expresa por unidad de vida del aceite
# —cada 100 horas o cada 1.000 km— para que dos muestras tomadas a distinta
# altura del intervalo se puedan comparar.
#
# EL DENOMINADOR IMPORTA
# Comparar 20 ppm de hierro a las 50 horas con 20 ppm a las 500 es comparar una
# tasa diez veces mayor con una normal. Es el error que hace que un informe
# ordenado por valor absoluto ponga primero a los motores sanos con intervalo
# largo.
# ══════════════════════════════════════════════════════════════════════════════

# Cuánto se considera un salto. Es relativo, no absoluto: duplicar es una
# señal en cualquier escala, y así el criterio no depende de la unidad.
SALTO_PRECAUCION = 0.60    # +60 % sobre la muestra anterior
SALTO_CONDENA = 1.50       # +150 %: se triplicó o más

# Por debajo de este valor la variación relativa no significa nada: pasar de
# 0,4 a 1,2 ppm es «se triplicó» y es ruido del ensayo. Cada familia de
# parámetros tiene su propio suelo de significancia.
SUELO_SIGNIFICANCIA = {
    "ppm": 5.0, "%": 0.05, "mgKOH/g": 0.3, "Abs/cm": 3.0, "cSt": 1.0,
}


def significativo(valor: float, unidad: Optional[str],
                  criterio: Optional["Criterio"] = None) -> bool:
    """¿El valor está por encima del ruido del ensayo para su unidad?"""
    return abs(valor) >= (criterio or CRITERIO_BASE).suelo(unidad)


def evaluar_tendencia(anterior: Optional[float], actual: Optional[float],
                      unidad: Optional[str],
                      criterio: Optional["Criterio"] = None,
                      ) -> Optional[Dict[str, Any]]:
    """Clasifica el salto entre dos muestras consecutivas.

    Devuelve `None` cuando no hay con qué: sin muestra anterior no hay
    tendencia, y decir «estable» sería una afirmación sin respaldo.
    """
    criterio = criterio or CRITERIO_BASE
    if anterior is None or actual is None:
        return None
    if not significativo(actual, unidad, criterio):
        return None
    suelo = criterio.suelo(unidad)
    base = abs(anterior)
    if base < (suelo or 1e-9):
        # De casi cero a un valor significativo: apareció algo que no estaba.
        return {"variacion": None, "estado": "PRECAUCION",
                "lectura": "Apareció donde antes no se medía nada apreciable."}
    variacion = (actual - anterior) / base
    # Las constantes se guardan en porcentaje porque así se escriben en el
    # formulario; acá se vuelven fracción para comparar.
    if variacion >= criterio.constante("salto_condena") / 100:
        estado = "CONDENA"
    elif variacion >= criterio.constante("salto_precaucion") / 100:
        estado = "PRECAUCION"
    else:
        return None
    return {
        "variacion": round(variacion * 100, 1), "estado": estado,
        "lectura": f"Subió {round(variacion * 100)} % respecto de la muestra "
                   f"anterior.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Las reglas de diagnóstico
#
# Cada una dice qué combinación la dispara, qué significa físicamente, qué
# hacer, y de dónde sale el criterio. Se evalúan EN ORDEN y gana la primera que
# encaje: las específicas arriba, las genéricas abajo. Evaluarlas todas y
# juntarlas produce una recomendación que dice seis cosas y no manda hacer
# ninguna.
#
# EL ORDEN ES «CUÁNTOS PARÁMETROS MIRA», NO «QUÉ TAN GRAVE ES»
# Primero las reglas de combinación —dos o más parámetros a la vez— y después
# las de un solo parámetro. La razón la enseñó la primera prueba con datos
# reales: con la regla del agua en tercer lugar y `exige: ["agua"]`, 111 de 149
# conclusiones salieron «Agua por encima del límite» y «Desgaste generalizado»
# no disparó ni una vez. El agua estaba fuera de verdad, pero como conclusión
# no sirve: que el agua esté alta ya se ve en la tabla de hallazgos, y lo que
# el informe tiene que nombrar es el patrón que dice qué revisar.
#
# Las dos excepciones son deliberadas y van arriba del todo: el glicol, porque
# un ensayo cualitativo positivo no admite matices, y el índice ferroso,
# porque es un modo de falla que ninguna otra regla recoge.
#
# LA DIFERENCIA CON LA VERSIÓN ANTERIOR
# Antes las reglas salían de los casos que el comité de la empresa había
# resuelto. Ahora salen de la literatura, y eso cambió conclusiones concretas:
#
#   · Cobre alto solo ya no es «desgaste de casquetes». La práctica de campo
#     documenta que un enfriador de aceite nuevo lava cobre durante las
#     primeras horas y da lecturas de decenas de ppm sin que haya desgaste.
#     Mandar a desarmar un motor por eso es un error caro y frecuente.
#   · El silicio ya no se lee solo. La relación con el aluminio distingue el
#     polvo de carretera —que lleva los dos— del silicio de un antiespumante o
#     de un sellador, que no es abrasivo.
#   · El TAN se juzga por el cruce con el TBN y no por un tope suelto.
#   · Un PQ alto con hierro normal es ahora un hallazgo propio y grave, en vez
#     de pasar desapercibido.
# ══════════════════════════════════════════════════════════════════════════════

REGLAS: List[Dict[str, Any]] = [
    {
        "codigo": "REFRIGERANTE",
        "nombre": "Refrigerante en el aceite",
        "exige": ["glicol"],
        "severidad": "ACCION_INMEDIATA",
        "urgencia": 100,
        "fuentes": ["ASTM D2982", "ICML"],
        "criterio": "Glicol detectado por ASTM D2982. El ensayo es "
                    "cualitativo: no hay nivel tolerable.",
        "lectura": "Hay refrigerante llegando al aceite. El glicol ataca los "
                   "cojinetes de metal blando y forma depósitos gelatinosos "
                   "que tapan conductos y filtro.",
        "accion": "Sacar el equipo de servicio. Buscar el paso: empaque de "
                  "culata, enfriador de aceite, camisas. Cambiar la carga "
                  "solo después de cerrar la fuga.",
    },
    {
        "codigo": "REFRIGERANTE_TRAZADORES",
        "nombre": "Refrigerante probable por trazadores",
        "exige": ["na"],
        "tambien": ["k", "b", "agua"],
        "minimo_tambien": 1,
        "severidad": "CRITICO",
        "urgencia": 92,
        "fuentes": ["ASTM D5185", "ICML"],
        "criterio": "Sodio acompañado de potasio, boro o agua, medidos por "
                    "ASTM D5185. Ninguno de los tres es concluyente solo.",
        "lectura": "El patrón es el del refrigerante: los inhibidores de "
                   "corrosión llevan boratos y silicatos de sodio y potasio, "
                   "así que suben juntos. El sodio solo también puede ser "
                   "aditivo del aceite o ambiente marino, y por eso hace "
                   "falta el acompañamiento.",
        "accion": "Pedir ensayo de glicol por ASTM D2982 para confirmar, y "
                  "revisar enfriador de aceite y empaque de culata.",
    },
    {
        "codigo": "DESGASTE_SEVERO_PQ",
        "nombre": "Desgaste severo con partícula grande",
        "exige": ["pq"],
        "severidad": "ACCION_INMEDIATA",
        "urgencia": 96,
        "fuentes": ["ASTM D8184", "ASTM D5185", "ICML"],
        "criterio": "Índice ferroso alto por ASTM D8184. Se reporta aparte "
                    "del hierro por ICP porque miden cosas distintas.",
        "lectura": "Hay partículas ferrosas grandes circulando. La ICP no "
                   "las ve —por encima de unas 5 µm el plasma no las "
                   "disocia—, así que un informe de solo espectrometría "
                   "declara sano justamente el caso más grave: descamación "
                   "por fatiga, que es la firma de una falla en curso.",
        "accion": "Ferrografía analítica para ver la morfología. No esperar "
                  "la próxima muestra: este modo de falla progresa rápido.",
    },
    {
        "codigo": "POLVO_CON_DESGASTE",
        "nombre": "Ingreso de polvo con desgaste activo",
        "exige": ["si"],
        "tambien": ["fe", "cr", "al"],
        "minimo_tambien": 1,
        "severidad": "CRITICO",
        "urgencia": 90,
        "fuentes": ["ASTM D5185", "ICML", "Tormos"],
        "criterio": "Silicio alto por ASTM D5185 junto con metales de "
                    "desgaste sobre el límite estadístico de la flota "
                    "(ASTM D7720).",
        "lectura": "El polvo ya no solo está entrando: está desgastando. La "
                   "sílice tiene la dureza justa para rayar camisas y "
                   "anillos, y el desgaste que produce no se detiene al "
                   "cambiar el aceite porque la entrada sigue abierta.",
        "accion": "Revisar todo el lado de admisión —filtro, sello del "
                  "filtro, abrazaderas, mangueras— y acortar el intervalo "
                  "hasta cerrarla. Cambiar la carga sin cerrar la entrada es "
                  "gasto perdido.",
    },
    {
        "codigo": "COJINETES",
        "nombre": "Desgaste de cojinetes",
        "exige": ["cu"],
        "tambien": ["pb", "sn"],
        "minimo_tambien": 1,
        "severidad": "CRITICO",
        "urgencia": 89,
        "fuentes": ["ASTM D5185", "Tormos"],
        "criterio": "Cobre con plomo o estaño, todos sobre el percentil de "
                    "la flota. Es la composición del casquete.",
        "lectura": "El casquete es una aleación de cobre, plomo y estaño: "
                   "que suban juntos es la firma del material del cojinete, "
                   "no una coincidencia. Suele venir de falta de presión, de "
                   "filtración deficiente o de acidez alta.",
        "accion": "Prueba de blow-by y verificación de presión de aceite. "
                  "Contramuestra antes de desarmar.",
    },
    {
        "codigo": "CRUCE_TBN_TAN",
        "nombre": "Cruce TBN/TAN: reserva alcalina agotada",
        "exige": [],
        "requiere_cruce_tbn_tan": True,
        "severidad": "CRITICO",
        "urgencia": 84,
        "fuentes": ["ASTM D4739", "ASTM D664", "ASTM D4378"],
        "criterio": "El TAN alcanzó o superó al TBN. Es el criterio de "
                    "condena clásico, y el más robusto de los dos porque no "
                    "depende del valor del aceite nuevo.",
        "lectura": "El aceite ya no tiene con qué neutralizar los ácidos que "
                   "genera la combustión. A partir de acá empieza la "
                   "corrosión de los metales blandos —plomo, cobre, estaño— "
                   "y la formación de barnices.",
        "accion": "Cambiar la carga. Si pasa en toda una familia antes del "
                  "intervalo, el problema es el azufre del combustible o el "
                  "grado del aceite, no el motor.",
    },
    {
        "codigo": "DESGASTE_GENERALIZADO",
        "nombre": "Desgaste generalizado",
        "exige": [],
        "minimo_desgaste": 3,
        "severidad": "CRITICO",
        "urgencia": 94,
        "fuentes": ["ASTM D7720", "ASTM D7669", "Tormos"],
        "criterio": "Tres o más metales de desgaste por encima del percentil "
                    "de la flota (ASTM D7720) en la misma muestra.",
        "lectura": "Que suban a la vez metales de piezas distintas rara vez "
                   "es una pieza. Apunta a algo que ataca todas las "
                   "superficies: un abrasivo circulando, el aceite agotado, "
                   "o falta de presión. También lo produce una muestra "
                   "tomada por el tapón de drenaje, que arrastra sedimento.",
        "accion": "Verificar cómo se tomó la muestra y repetirla con método "
                  "controlado. Si se confirma, revisar filtración y presión "
                  "de aceite antes de desarmar.",
    },
    {
        "codigo": "DILUCION",
        "nombre": "Dilución por combustible",
        "exige": ["combustible"],
        "severidad": "CRITICO",
        "urgencia": 86,
        "fuentes": ["ASTM D7593", "ASTM D445", "Tormos"],
        "criterio": "Combustible por ASTM D7593 sobre 5 %, o sobre 2,5 % con "
                    "la viscosidad cayendo más del 20 % respecto del grado "
                    "SAE cargado.",
        "lectura": "La viscosidad cae y con ella el espesor de película. En "
                   "los cojinetes el régimen pasa de hidrodinámico a mixto, "
                   "que es donde aparece el desgaste. El resto de la muestra "
                   "puede salir perfecta y el aceite igual no está "
                   "protegiendo.",
        "accion": "Revisar inyección, y descartar ralentí prolongado y "
                  "regeneraciones incompletas del filtro de partículas.",
    },
    {
        "codigo": "AGUA",
        "nombre": "Agua por encima del límite",
        "exige": ["agua"],
        "severidad": "CRITICO",
        "urgencia": 88,
        "fuentes": ["ASTM D6304", "Tormos"],
        "criterio": "Agua por ASTM D6304 sobre 0,2 % en motor. En hidráulica "
                    "el criterio es veinte veces más exigente.",
        "lectura": "El agua desplaza la película lubricante, hidroliza los "
                   "aditivos y corroe. En un motor que opera frío suele ser "
                   "condensación; si viene con sodio o potasio, es "
                   "refrigerante y el problema es otro.",
        "accion": "Determinar el origen antes de cambiar la carga: "
                  "condensación por operación fría, refrigerante, o entrada "
                  "por lavado.",
    },
    {
        "codigo": "POLVO_CONFIRMADO",
        "nombre": "Ingreso de polvo",
        "exige": ["si"],
        "requiere_relacion_si_al": True,
        "severidad": "MARGINAL",
        "urgencia": 62,
        "fuentes": ["ASTM D5185", "ICML"],
        "criterio": "Silicio alto con aluminio subiendo en proporción. El "
                    "polvo de carretera es aluminosilicato: lleva los dos.",
        "lectura": "Está entrando polvo, pero los metales de desgaste "
                   "todavía están en el nivel de la flota. Se puede actuar "
                   "sobre la causa antes de que haya daño.",
        "accion": "Revisar el lado de admisión y el procedimiento de "
                  "llenado. Confirmar en la próxima muestra.",
    },
    {
        "codigo": "SILICIO_SIN_ALUMINIO",
        "nombre": "Silicio alto que probablemente no es polvo",
        "exige": ["si"],
        "severidad": "MARGINAL",
        "urgencia": 35,
        "fuentes": ["ASTM D5185", "ICML"],
        "criterio": "Silicio alto SIN aluminio acompañante. El polvo de "
                    "carretera es aluminosilicato; el silicio solo apunta a "
                    "otra fuente.",
        "lectura": "El silicio sube pero el aluminio no. Eso no encaja con "
                   "polvo: encaja con antiespumante del aceite nuevo, con "
                   "sellador de silicona de un armado reciente, o con "
                   "residuo de un aditivo. Tratarlo como polvo manda a "
                   "revisar una admisión que está bien.",
        "accion": "Verificar si hubo intervención reciente con sellador de "
                  "silicona y comparar contra el silicio del aceite nuevo. "
                  "Confirmar en la próxima muestra antes de intervenir.",
    },
    {
        "codigo": "COBRE_SOLO",
        "nombre": "Cobre alto sin otro metal acompañante",
        "exige": ["cu"],
        "prohibe": ["pb", "sn", "fe"],
        "severidad": "MARGINAL",
        "urgencia": 45,
        "fuentes": ["ASTM D5185", "ICML"],
        "criterio": "Cobre sobre el percentil de la flota, con plomo, estaño "
                    "y hierro dentro del nivel normal.",
        "lectura": "Cobre solo, sin los metales que lo acompañarían si "
                   "fueran cojinetes, suele ser lavado del enfriador de "
                   "aceite: un enfriador nuevo entrega cobre durante las "
                   "primeras horas y da decenas de ppm sin que haya "
                   "desgaste. El cobre de un cojinete viene con plomo o con "
                   "estaño, porque el casquete es una aleación.",
        "accion": "Verificar si el enfriador de aceite se cambió hace poco. "
                  "Confirmar en la próxima muestra antes de intervenir: "
                  "desarmar un motor por cobre solo es un error caro y "
                  "frecuente.",
    },
    {
        "codigo": "DEGRADACION",
        "nombre": "Aceite degradado",
        "exige": [],
        "tambien": ["oxidacion", "nitracion", "sulfatacion", "tan"],
        "minimo_tambien": 2,
        "severidad": "MARGINAL",
        "urgencia": 72,
        "fuentes": ["ASTM E2412", "ASTM D664", "ASTM D6224"],
        "criterio": "Dos o más indicadores de degradación por FTIR "
                    "(ASTM E2412) sobre el umbral de referencia.",
        "lectura": "El aceite perdió propiedades. Mientras dure la "
                   "condición, los metales de desgaste van a subir aunque el "
                   "motor esté sano: el diagnóstico de desgaste no es "
                   "confiable hasta cambiar la carga.",
        "accion": "Cambiar la carga y averiguar por qué se degradó antes de "
                  "tiempo: temperatura de operación, intervalo, azufre del "
                  "combustible o producto equivocado.",
    },
    {
        "codigo": "TBN_AGOTADO",
        "nombre": "Reserva alcalina por debajo del límite",
        "exige": ["tbn"],
        "severidad": "MARGINAL",
        "urgencia": 70,
        "fuentes": ["ASTM D4739", "Tormos"],
        "criterio": "TBN por ASTM D4739 por debajo de 2,0 mgKOH/g, o por "
                    "debajo de la mitad del valor del aceite nuevo.",
        "lectura": "Al aceite le queda poca capacidad de neutralizar. "
                   "Todavía protege, pero el margen hasta el cruce con el "
                   "TAN es corto.",
        "accion": "Acortar el intervalo en esta familia y revisar el azufre "
                  "del combustible.",
    },
    {
        "codigo": "NITRACION",
        "nombre": "Nitración alta: paso de gases al cárter",
        "exige": ["nitracion"],
        "severidad": "MARGINAL",
        "urgencia": 60,
        "fuentes": ["ASTM E2412", "ICML"],
        "criterio": "Nitración por FTIR (ASTM E2412) sobre el umbral de "
                    "referencia.",
        "lectura": "La nitración viene de gases de combustión que pasan al "
                   "cárter. Es señal de blow-by por anillos, de ventilación "
                   "del cárter obstruida, o de ralentí excesivo.",
        "accion": "Prueba de blow-by y revisión del sistema de ventilación "
                  "del cárter antes de culpar al aceite.",
    },
    {
        "codigo": "HOLLIN",
        "nombre": "Hollín alto",
        "exige": ["hollin"],
        "severidad": "MARGINAL",
        "urgencia": 55,
        "fuentes": ["ASTM D7844", "ICML"],
        "criterio": "Hollín por FTIR (ASTM D7844) sobre 3 %; sobre 5 % es "
                    "condena.",
        "lectura": "El hollín no es abrasivo mientras el dispersante lo "
                   "mantenga suspendido. El daño viene cuando aglomera: sube "
                   "la viscosidad, tapa el filtro y desgasta el tren de "
                   "válvulas.",
        "accion": "Revisar filtro de aire, inyección y tiempos. Verificar "
                  "que el aceite cargado corresponde al motor.",
    },
    {
        "codigo": "VISCOSIDAD",
        "nombre": "Viscosidad fuera de la banda del grado",
        "exige": [],
        "requiere_desvio_viscosidad": True,
        "severidad": "MARGINAL",
        "urgencia": 58,
        "fuentes": ["ASTM D445", "SAE J300", "ASTM D4378"],
        "criterio": "Desviación de más del 20 % respecto del centro de la "
                    "banda SAE J300 del grado cargado; más del 30 % es "
                    "condena. Es el método de desviación relativa de "
                    "ASTM D4378.",
        "lectura": "Bajar es dilución —combustible o un aceite más ligero—. "
                   "Subir es oxidación, hollín aglomerado o un grado "
                   "equivocado. Son averías distintas y la dirección las "
                   "separa.",
        "accion": "Confirmar el producto realmente cargado y contrastar con "
                  "el combustible y la oxidación.",
    },
    {
        "codigo": "LIMPIEZA_ISO",
        "nombre": "Limpieza por encima de la meta ISO 4406",
        "exige": ["iso4406"],
        "severidad": "MARGINAL",
        "urgencia": 50,
        "fuentes": ["ISO 4406", "ICML"],
        "criterio": "Código ISO 4406 por encima de la meta del "
                    "compartimento. Cada código es el doble de partículas.",
        "lectura": "El fluido está más sucio que su meta. En hidráulica y en "
                   "engranajes de precisión la limpieza es el parámetro que "
                   "gobierna la vida del componente.",
        "accion": "Revisar filtración, respiraderos y el procedimiento de "
                  "llenado.",
    },
    {
        "codigo": "TENDENCIA",
        "nombre": "Tendencia al alza sin cruzar el límite",
        "exige": [],
        "solo_tendencia": True,
        "severidad": "MARGINAL",
        "urgencia": 48,
        "fuentes": ["ASTM D7669", "ASTM D4378"],
        "criterio": "Salto respecto de la muestra anterior por encima del "
                    "60 %, con el valor todavía dentro de los límites. "
                    "ASTM D7669 construye el diagnóstico sobre la variación "
                    "y no sobre el valor suelto.",
        "lectura": "Ningún parámetro cruzó su límite, pero algo se está "
                   "moviendo rápido. Es la señal temprana: esperar a que "
                   "cruce el tope es esperar a que el daño ya esté hecho.",
        "accion": "Adelantar la próxima muestra y vigilar los parámetros "
                  "que se movieron.",
    },
    {
        "codigo": "DESGASTE_PUNTUAL",
        "nombre": "Desgaste puntual",
        "exige": [],
        "minimo_desgaste": 1,
        "severidad": "MARGINAL",
        "urgencia": 40,
        "fuentes": ["ASTM D7720", "ASTM D7669"],
        "criterio": "Un metal de desgaste sobre el percentil de la flota, "
                    "sin patrón que lo acompañe.",
        "lectura": "Un solo metal fuera y sin acompañamiento. Puede ser el "
                   "comienzo de algo, o puede ser la toma de muestra: una "
                   "muestra tomada por el tapón de drenaje produce "
                   "exactamente esta señal.",
        "accion": "Contramuestra con método controlado antes de decidir "
                  "nada.",
    },
]

# El motor recién intervenido cambia la lectura, no el dato. Las primeras horas
# después de un armado liberan partículas del rodaje, y el silicio del armado
# en un patio con polvo no viene de la admisión. Es una excepción reconocida en
# la práctica de campo, y sin ella el programa manda a desarmar motores que
# están asentándose con normalidad.
DIAS_ASENTAMIENTO = 90
CATEGORIAS_REPARACION = {"INTERVENCION", "FALLA"}

REGLA_ASENTAMIENTO = {
    "codigo": "ASENTAMIENTO",
    "nombre": "Motor en asentamiento",
    "severidad": "NORMAL",
    "urgencia": 25,
    "fuentes": ["ICML", "ASTM D7669"],
    "criterio": "Carga instalada hace menos de 90 días después de una "
                "intervención mayor o de una falla. La línea base todavía no "
                "es la del equipo en régimen.",
    "lectura": "El desgaste de las primeras muestras después de un armado "
               "corresponde al rodaje, y el silicio suele venir del montaje y "
               "no de la admisión. Leer estos valores contra el límite de la "
               "flota en régimen produce una alarma falsa.",
    "accion": "Continuar el monitoreo con frecuencia más corta y confirmar la "
              "normalización en la siguiente muestra. No intervenir por estos "
              "valores.",
}

REGLA_SIN_HALLAZGO = {
    "codigo": "SIN_HALLAZGO",
    "nombre": "Sin hallazgos",
    "severidad": "NORMAL",
    "urgencia": 0,
    "fuentes": ["ASTM D6224"],
    "criterio": "Todos los parámetros medidos dentro de sus límites y sin "
                "tendencia significativa.",
    "lectura": "Nada que reportar en esta muestra.",
    "accion": "Continuar el programa de muestreo.",
}


# ══════════════════════════════════════════════════════════════════════════════
# El evaluador
# ══════════════════════════════════════════════════════════════════════════════

# Relación silicio–aluminio del polvo de carretera. El aluminosilicato lleva
# los dos elementos, y su proporción es el criterio de campo para distinguir
# polvo real de silicio de otra fuente.
RELACION_SI_AL_MINIMA = 0.15   # Al/Si por debajo de esto, probablemente no es polvo


def _estado_contra(valor: float, limite: Dict[str, Any]) -> Optional[str]:
    """Compara un valor con un límite y devuelve el estado, o `None`."""
    direccion = limite.get("direccion", "ALTO")
    prec, cond = limite.get("precaucion"), limite.get("condena")
    if direccion == "BAJO":
        if cond is not None and valor <= cond:
            return "CONDENA"
        if prec is not None and valor <= prec:
            return "PRECAUCION"
        return None
    # Los ensayos cualitativos —glicol— tienen los dos umbrales en cero: se
    # dispara con cualquier valor por encima de cero, no con «mayor o igual».
    if prec == 0 and cond == 0:
        return "CONDENA" if valor > 0 else None
    if cond is not None and valor >= cond:
        return "CONDENA"
    if prec is not None and valor >= prec:
        return "PRECAUCION"
    return None


def evaluar_muestra(
    valores: Dict[str, float],
    unidades: Dict[str, Optional[str]],
    anteriores: Optional[Dict[str, float]] = None,
    tipo_compartimento: Optional[str] = None,
    estadisticos: Optional[Dict[str, Dict[str, Any]]] = None,
    grado_sae: Optional[str] = None,
    meta_iso: Optional[str] = None,
    iso_medido: Optional[str] = None,
    criterio: Optional["Criterio"] = None,
) -> Dict[str, Any]:
    """Evalúa una muestra contra los límites de norma y su propia tendencia.

    Devuelve, por parámetro, el estado y el límite que lo disparó —con su
    fuente—, más la evaluación de tendencia. No decide el diagnóstico: eso lo
    hace `diagnosticar` sobre esta salida, y están separados a propósito para
    poder mostrar en pantalla el hallazgo por parámetro y la conclusión como
    dos cosas distintas.
    """
    criterio = criterio or CRITERIO_BASE
    base = criterio.limites(tipo_compartimento)
    estadisticos = estadisticos or {}
    anteriores = anteriores or {}
    hallazgos: Dict[str, Dict[str, Any]] = {}

    for codigo, valor in valores.items():
        if valor is None:
            continue
        unidad = unidades.get(codigo)
        limite = base.get(codigo)
        # Para los metales de desgaste el límite correcto es el de la propia
        # flota. Si no hay población suficiente no se inventa uno: el
        # parámetro queda solo con su tendencia.
        if codigo in GRUPO_DESGASTE:
            limite = estadisticos.get(codigo)

        estado = _estado_contra(valor, limite) if limite else None
        tendencia = evaluar_tendencia(anteriores.get(codigo), valor,
                                      unidad, criterio)

        if estado is None and tendencia is None:
            continue
        hallazgos[codigo] = {
            "valor": valor,
            "unidad": unidad,
            "estado": estado,
            # El límite viaja aunque el parámetro NO lo haya cruzado. Un hierro
            # de 50 ppm que subió 103 % se lee distinto sabiendo que el límite
            # de su familia está en 76: dice que va rápido y todavía hay
            # margen. Sin el número al lado, la fila solo dice «subió mucho» y
            # el lector no puede juzgar cuánto queda.
            "limite": ({"precaucion": limite.get("precaucion"),
                        "condena": limite.get("condena"),
                        "direccion": limite.get("direccion"),
                        "metodo": limite.get("metodo"),
                        "criterio": limite.get("criterio"),
                        "naturaleza": limite.get("naturaleza"),
                        "porque": limite.get("porque"),
                        "n": limite.get("n")} if limite else None),
            "tendencia": tendencia,
        }

    # ── Viscosidad contra la banda SAE J300 del grado cargado ────────────────
    # Aparte porque no se juzga contra un tope sino contra el aceite que le
    # corresponde, y esa referencia sale del grado y no de la flota.
    desvio_visc = None
    referencia = referencia_viscosidad_100c(grado_sae)
    medido = valores.get("visc100")
    if referencia and medido is not None:
        rel = (medido - referencia) / referencia
        d_prec = criterio.constante("desvio_viscosidad_precaucion") / 100
        d_cond = criterio.constante("desvio_viscosidad_condena") / 100
        estado = ("CONDENA" if abs(rel) >= d_cond
                  else "PRECAUCION" if abs(rel) >= d_prec
                  else None)
        desvio_visc = {
            "medido": medido, "referencia": referencia,
            "grado": grado_sae, "desvio_pct": round(rel * 100, 1),
            "direccion": "ALTA" if rel > 0 else "BAJA",
            "estado": estado,
            "metodo": "ASTM D445", "criterio": "SAE J300 + ASTM D4378",
            "naturaleza": "NORMA",
        }
        if estado:
            hallazgos.setdefault("visc100", {
                "valor": medido, "unidad": unidades.get("visc100"),
                "estado": estado, "tendencia": None,
                "limite": {
                    "precaucion": round(referencia * (1 + d_prec), 2),
                    "condena": round(referencia * (1 + d_cond), 2),
                    "direccion": "DESVIO", "metodo": "ASTM D445",
                    "criterio": "SAE J300 + ASTM D4378", "naturaleza": "NORMA",
                    "porque": f"El grado {grado_sae} tiene su banda de "
                              f"viscosidad a 100 °C definida en SAE J300; su "
                              f"centro es {referencia} cSt. La desviación "
                              f"medida es del {round(rel * 100, 1)} %.",
                },
            })

    # ── Cruce TBN/TAN ────────────────────────────────────────────────────────
    tbn, tan = valores.get("tbn"), valores.get("tan")
    cruce = bool(tbn is not None and tan is not None and tan >= tbn and tbn > 0)

    # ── Relación silicio–aluminio ────────────────────────────────────────────
    si, al = valores.get("si"), valores.get("al")
    relacion_si_al = None
    if si and si > 0 and al is not None:
        relacion_si_al = round(al / si, 3)

    # ── Limpieza contra la meta ISO 4406 ─────────────────────────────────────
    if meta_iso and iso_medido:
        exceso = _exceso_iso(iso_medido, meta_iso)
        if exceso is not None and exceso > 0:
            hallazgos["iso4406"] = {
                "valor": None, "unidad": "cód.",
                "estado": "CONDENA" if exceso >= 2 else "PRECAUCION",
                "tendencia": None,
                "limite": {
                    "precaucion": None, "condena": None, "direccion": "ALTO",
                    "metodo": "ISO 4406", "criterio": "Meta del compartimento",
                    "naturaleza": "NORMA",
                    "porque": f"Medido {iso_medido} contra la meta "
                              f"{meta_iso}: {exceso} código(s) por encima. "
                              f"Cada código duplica la cantidad de "
                              f"partículas.",
                },
                "texto": iso_medido,
            }

    return {
        "hallazgos": hallazgos,
        "desvio_viscosidad": desvio_visc,
        "cruce_tbn_tan": cruce,
        "relacion_si_al": relacion_si_al,
    }


def _exceso_iso(medido: str, meta: str) -> Optional[int]:
    """Cuántos códigos ISO 4406 por encima de la meta está el fluido.

    Se compara código por código y se devuelve el peor de los tres: un fluido
    que cumple en las partículas finas y falla en las de 14 µm no está limpio,
    y promediar los tres números lo daría por bueno.
    """
    try:
        a = [int(x) for x in medido.replace(" ", "").split("/")]
        b = [int(x) for x in meta.replace(" ", "").split("/")]
    except (ValueError, AttributeError):
        return None
    if len(a) != len(b) or not a:
        return None
    return max(x - y for x, y in zip(a, b))


def diagnosticar(evaluacion: Dict[str, Any],
                 post_reparacion: bool = False,
                 criterio: Optional["Criterio"] = None) -> Dict[str, Any]:
    """Escoge la regla que explica la muestra.

    Gana la PRIMERA que encaje, no la que más parámetros toque. Las reglas
    están ordenadas de específica a genérica justamente para esto: combinar
    todas las que encajan produce una recomendación que dice seis cosas y no
    manda hacer ninguna.
    """
    criterio = criterio or CRITERIO_BASE
    relacion_minima = criterio.constante("relacion_si_al_minima")
    hallazgos = evaluacion["hallazgos"]
    # «Fuera» es haber cruzado un límite. Una tendencia sola no cuenta como
    # fuera: es lo que dispara la regla de tendencia, que va aparte.
    fuera = {c for c, h in hallazgos.items() if h.get("estado")}
    condenados = {c for c, h in hallazgos.items() if h.get("estado") == "CONDENA"}
    con_tendencia = {c for c, h in hallazgos.items() if h.get("tendencia")}
    n_desgaste = len(fuera & GRUPO_DESGASTE)
    relacion = evaluacion.get("relacion_si_al")

    for regla in criterio.reglas():
        exige = set(regla.get("exige", []))
        if exige and not exige <= fuera:
            continue
        prohibe = set(regla.get("prohibe", []))
        if prohibe & fuera:
            continue
        tambien = set(regla.get("tambien", []))
        minimo = regla.get("minimo_tambien", 0)
        if minimo and len(tambien & fuera) < minimo:
            continue
        if n_desgaste < regla.get("minimo_desgaste", 0):
            continue
        if regla.get("requiere_cruce_tbn_tan") and not evaluacion.get("cruce_tbn_tan"):
            continue
        if regla.get("requiere_desvio_viscosidad"):
            d = evaluacion.get("desvio_viscosidad")
            if not d or not d.get("estado"):
                continue
        # Las dos reglas de silicio se separan por la relación con el aluminio.
        # Sin aluminio medido no se puede decidir, y entonces no aplica
        # ninguna de las dos: se cae a una regla más genérica antes que
        # afirmar algo que el dato no sostiene.
        if regla.get("requiere_relacion_si_al"):
            if relacion is None or relacion < relacion_minima:
                continue
        if regla["codigo"] == "SILICIO_SIN_ALUMINIO":
            if relacion is None or relacion >= relacion_minima:
                continue
        if regla.get("solo_tendencia"):
            if fuera or not con_tendencia:
                continue
        # Una regla sin exigencias y sin ningún otro criterio encajaría con
        # todo. No se permite: sería un diagnóstico por defecto disfrazado.
        if (not exige and not regla.get("minimo_desgaste")
                and not regla.get("minimo_tambien")
                and not regla.get("requiere_cruce_tbn_tan")
                and not regla.get("requiere_desvio_viscosidad")
                and not regla.get("solo_tendencia")):
            continue

        if post_reparacion and (n_desgaste or "si" in fuera):
            return dict(REGLA_ASENTAMIENTO)

        # LA REGLA DICE QUÉ PASA; EL DATO, CUÁNTO HA AVANZADO.
        # La severidad se ajusta en las dos direcciones, y la de bajada es la
        # que más importa: la regla del agua está declarada CRÍTICA porque el
        # agua en el cárter lo es, pero una muestra que apenas rozó el umbral de
        # precaución —0,1 %, no los 0,2 % de condena— no es una emergencia.
        # Sin la bajada, cualquier parámetro que asome por encima del primer
        # umbral salía como crítico, y en la primera prueba con datos reales eso
        # dejó 125 de 149 muestras en rojo. Un tablero donde casi todo está en
        # rojo no prioriza nada.
        severidad = regla["severidad"]
        if condenados:
            if severidad == "MARGINAL":
                severidad = "CRITICO"
        elif severidad in ("CRITICO", "ACCION_INMEDIATA"):
            severidad = "MARGINAL"
        return {**regla, "severidad": severidad,
                # Se conserva lo que la regla declara para poder mostrar en
                # pantalla «este modo de falla es crítico, pero esta muestra
                # todavía no llegó ahí».
                "severidad_declarada": regla["severidad"]}

    return dict(REGLA_SIN_HALLAZGO)


# ══════════════════════════════════════════════════════════════════════════════
# Regresión sobre el kilometraje
#
# Para responder cómo se comporta cada parámetro contra el recorrido. Es la
# lectura de tendencia de ASTM D7669 llevada a la flota entera en vez de a un
# equipo: la pendiente dice cuánto sube el parámetro por cada 1.000 km, que es
# la cifra con la que se decide un intervalo.
# ══════════════════════════════════════════════════════════════════════════════

def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    """Coeficiente de correlación de Pearson, o `None` si no se puede calcular.

    Devuelve `None` —y no cero— cuando faltan datos o una de las series es
    constante. Un cero afirma «no hay relación»; presentarlo cuando en
    realidad no se pudo calcular es la manera más silenciosa de mentir en una
    matriz de correlación.
    """
    n = len(xs)
    if n < 4:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return round(sxy / sqrt(sxx * syy), 4)


def regresion(xs: List[float], ys: List[float]) -> Optional[Dict[str, Any]]:
    """Recta de mínimos cuadrados con su r de Pearson y su r².

    La pendiente viene también expresada por cada 1.000 unidades de x, que es
    como se lee un kilometraje: «sube 4,2 ppm cada 1.000 km» se entiende y
    «0,0042» no.
    """
    n = len(xs)
    if n < 4:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    pendiente = sxy / sxx
    r = pearson(xs, ys)
    return {
        "n": n,
        "pendiente": round(pendiente, 6),
        "por_mil": round(pendiente * 1000, 3),
        # Los odómetros de flota van en cientos de miles de kilómetros, así que
        # hay series donde «por cada 1.000 km» sale en centésimas y no se lee.
        # Se manda también la escala de diez mil para que la pantalla escoja la
        # que produce un número legible sin tener que multiplicar por su cuenta
        # y arriesgarse a que la etiqueta y el número se desincronicen.
        "por_diez_mil": round(pendiente * 10000, 3),
        "intercepto": round(my - pendiente * mx, 4),
        "r": r,
        "r2": round(r * r, 4) if r is not None else None,
        "x_min": round(min(xs), 2), "x_max": round(max(xs), 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# EL CRITERIO VIGENTE: la referencia con los ajustes de la empresa encima
#
# Todo lo de arriba es lo publicado. Nada de eso se toca desde la aplicación:
# vive en el código, versionado y con su fuente. Lo que la empresa cambia se
# guarda aparte, en `eam_lube_ajuste_norma`, y se resuelve acá.
#
# POR QUÉ LA CONFIGURACIÓN NO PUEDE BORRAR LA PROCEDENCIA
# Todo el módulo se rehízo para poder decir de dónde sale cada número. Si al
# cambiar un límite la pantalla siguiera diciendo «Tormos», la configurabilidad
# habría deshecho justamente eso: un valor de la casa presentado como norma
# internacional es peor que no citar nada, porque es una cita falsa.
#
# Por eso un límite ajustado cambia de naturaleza a EMPRESA y viaja con el
# valor de referencia y el motivo del cambio al lado. Ajustar es legítimo —el
# fabricante del motor manda sobre la literatura, y un laboratorio con otro
# método tiene otros umbrales—; disimularlo no.
# ══════════════════════════════════════════════════════════════════════════════

NATURALEZA["EMPRESA"] = ("Umbral ajustado por esta empresa. Reemplaza al de "
                         "referencia, que se conserva a la vista para poder "
                         "compararlos.")

# Las constantes del motor de cálculo, con lo que hacen y qué se gana o se
# pierde al moverlas. Los valores van en la unidad en que se leen —un
# porcentaje es 60 y no 0,60— porque el formulario los muestra tal cual, y
# pedirle a alguien que escriba 0,60 para decir «60 %» produce ceros de más.
CONSTANTES: Dict[str, Dict[str, Any]] = {
    "percentil_precaucion": {
        "valor": PERCENTIL_PRECAUCION, "minimo": 50.0, "maximo": 99.0,
        "unidad": "percentil",
        "grupo": "Límites de la propia flota (ASTM D7720)",
        "nombre": "Percentil de precaución",
        "fuentes": ["ASTM D7720"],
        "que_hace": "Por encima de este percentil de la población, un metal de "
                    "desgaste entra en precaución.",
        "efecto": "Bajarlo alarma antes y produce más avisos; subirlo deja "
                  "pasar desgastes incipientes. El 90 es el punto donde una de "
                  "cada diez muestras de equipos comparables queda marcada.",
    },
    "percentil_condena": {
        "valor": PERCENTIL_CONDENA, "minimo": 80.0, "maximo": 99.9,
        "unidad": "percentil",
        "grupo": "Límites de la propia flota (ASTM D7720)",
        "nombre": "Percentil de condena",
        "fuentes": ["ASTM D7720"],
        "que_hace": "Por encima de este percentil, el metal de desgaste se "
                    "considera condenatorio.",
        "efecto": "Tiene que quedar por encima del de precaución. Acercarlos "
                  "borra el escalón entre «vigilar» y «actuar».",
    },
    "minimo_poblacion": {
        "valor": float(MINIMO_POBLACION_D7720), "minimo": 10.0, "maximo": 500.0,
        "unidad": "mediciones",
        "grupo": "Límites de la propia flota (ASTM D7720)",
        "nombre": "Población mínima para calcular un límite",
        "fuentes": ["ASTM D7720"],
        "que_hace": "Con menos mediciones de las que diga acá, el parámetro se "
                    "queda sin límite estadístico y solo se juzga por tendencia.",
        "efecto": "Bajarlo da límites en flotas pequeñas, pero un percentil "
                  "97,5 sobre doce puntos es el punto más alto de doce, y "
                  "llamarlo «límite» le da una autoridad que no tiene.",
    },
    "salto_precaucion": {
        "valor": SALTO_PRECAUCION * 100, "minimo": 10.0, "maximo": 500.0,
        "unidad": "%",
        "grupo": "Tendencia (ASTM D7669)",
        "nombre": "Salto que enciende precaución",
        "fuentes": ["ASTM D7669"],
        "que_hace": "Subida respecto de la muestra anterior a partir de la "
                    "cual se marca la tendencia, aunque el valor siga dentro "
                    "de los límites.",
        "efecto": "Es la señal temprana. Subirlo mucho equivale a esperar a "
                  "que el parámetro cruce el tope, que es esperar a que el "
                  "daño ya esté hecho.",
    },
    "salto_condena": {
        "valor": SALTO_CONDENA * 100, "minimo": 50.0, "maximo": 2000.0,
        "unidad": "%",
        "grupo": "Tendencia (ASTM D7669)",
        "nombre": "Salto que enciende condena",
        "fuentes": ["ASTM D7669"],
        "que_hace": "Subida respecto de la muestra anterior que se considera "
                    "grave por sí sola.",
        "efecto": "150 % es «se multiplicó por dos y medio». Con intervalos de "
                  "muestreo largos conviene subirlo; con intervalos cortos, "
                  "bajarlo.",
    },
    "desvio_viscosidad_precaucion": {
        "valor": DESVIO_VISCOSIDAD["precaucion"] * 100, "minimo": 5.0,
        "maximo": 60.0, "unidad": "%",
        "grupo": "Viscosidad (SAE J300 + ASTM D4378)",
        "nombre": "Desviación de precaución",
        "fuentes": ["SAE J300", "ASTM D4378"],
        "que_hace": "Cuánto puede alejarse la viscosidad a 100 °C del centro "
                    "de la banda del grado cargado antes de marcarse.",
        "efecto": "Los fabricantes de motor suelen usar ±20 %. Con aceites "
                  "multigrado de alto índice de viscosidad puede apretarse.",
    },
    "desvio_viscosidad_condena": {
        "valor": DESVIO_VISCOSIDAD["condena"] * 100, "minimo": 10.0,
        "maximo": 80.0, "unidad": "%",
        "grupo": "Viscosidad (SAE J300 + ASTM D4378)",
        "nombre": "Desviación de condena",
        "fuentes": ["SAE J300", "ASTM D4378"],
        "que_hace": "Desviación a partir de la cual el aceite se considera "
                    "fuera del grado que le corresponde.",
        "efecto": "Una desviación del 30 % ya suele significar que la película "
                  "no es la que el motor espera.",
    },
    "relacion_si_al_minima": {
        "valor": RELACION_SI_AL_MINIMA, "minimo": 0.01, "maximo": 1.0,
        "unidad": "Al/Si",
        "grupo": "Lectura combinada de elementos",
        "nombre": "Relación aluminio/silicio que confirma polvo",
        "fuentes": ["ICML"],
        "que_hace": "Con el silicio alto, si el aluminio acompaña por encima "
                    "de esta proporción se diagnostica polvo; por debajo, se "
                    "sospecha de otra fuente de silicio.",
        "efecto": "Depende del polvo de la zona. Subirlo exige más aluminio "
                  "para dar el polvo por confirmado y manda más muestras a "
                  "«silicio que probablemente no es polvo».",
    },
    "dias_asentamiento": {
        "valor": float(DIAS_ASENTAMIENTO), "minimo": 0.0, "maximo": 365.0,
        "unidad": "días",
        "grupo": "Lectura combinada de elementos",
        "nombre": "Ventana de asentamiento tras una intervención",
        "fuentes": ["ICML", "ASTM D7669"],
        "que_hace": "Durante estos días después de una reparación mayor, el "
                    "desgaste alto se lee como rodaje y no como avería.",
        "efecto": "Ponerlo en cero apaga la excepción y manda a desarmar "
                  "motores que se están asentando con normalidad. Estirarlo "
                  "de más esconde una falla real detrás del rodaje.",
    },
    "umbral_confirmacion": {
        "valor": UMBRAL_CONFIRMACION, "minimo": 0.1, "maximo": 0.95,
        "unidad": "r",
        "grupo": "Correlación",
        "nombre": "Correlación que confirma un mecanismo",
        "fuentes": [],
        "que_hace": "A partir de este coeficiente de Pearson se da por "
                    "cumplido en esta flota un eslabón de la cadena causal.",
        "efecto": "No es un valor de significancia estadística: es el punto "
                  "donde la relación es lo bastante fuerte como para que valga "
                  "la pena actuar sobre ella.",
    },
    "suelo_ppm": {
        "valor": SUELO_SIGNIFICANCIA["ppm"], "minimo": 0.0, "maximo": 100.0,
        "unidad": "ppm",
        "grupo": "Ruido del laboratorio",
        "nombre": "Suelo de significancia en ppm",
        "fuentes": [],
        "que_hace": "Por debajo de este valor no se evalúa la tendencia: pasar "
                    "de 0,4 a 1,2 ppm es «se triplicó» y es ruido del ensayo.",
        "efecto": "Depende de la repetibilidad del laboratorio. Bajarlo llena "
                  "el informe de tendencias que no significan nada.",
    },
    "suelo_pct": {
        "valor": SUELO_SIGNIFICANCIA["%"], "minimo": 0.0, "maximo": 5.0,
        "unidad": "%",
        "grupo": "Ruido del laboratorio",
        "nombre": "Suelo de significancia en porcentaje",
        "fuentes": [],
        "que_hace": "El mismo suelo, para agua, combustible y hollín.",
        "efecto": "Ver el suelo en ppm.",
    },
    "suelo_mgkoh": {
        "valor": SUELO_SIGNIFICANCIA["mgKOH/g"], "minimo": 0.0, "maximo": 5.0,
        "unidad": "mgKOH/g",
        "grupo": "Ruido del laboratorio",
        "nombre": "Suelo de significancia en mgKOH/g",
        "fuentes": [],
        "que_hace": "El mismo suelo, para TBN y TAN.",
        "efecto": "Ver el suelo en ppm.",
    },
    "suelo_abs": {
        "valor": SUELO_SIGNIFICANCIA["Abs/cm"], "minimo": 0.0, "maximo": 30.0,
        "unidad": "Abs/cm",
        "grupo": "Ruido del laboratorio",
        "nombre": "Suelo de significancia en Abs/cm",
        "fuentes": ["ASTM E2412"],
        "que_hace": "El mismo suelo, para oxidación, nitración y sulfatación.",
        "efecto": "Ver el suelo en ppm.",
    },
    "suelo_cst": {
        "valor": SUELO_SIGNIFICANCIA["cSt"], "minimo": 0.0, "maximo": 20.0,
        "unidad": "cSt",
        "grupo": "Ruido del laboratorio",
        "nombre": "Suelo de significancia en cSt",
        "fuentes": ["ASTM D445"],
        "que_hace": "El mismo suelo, para la viscosidad.",
        "efecto": "Ver el suelo en ppm.",
    },
}

# Qué familia de compartimento usa qué tablas de referencia. Se declara acá para
# que la pantalla de configuración ofrezca las mismas opciones que aplica el
# evaluador, y no una lista escrita a mano que se desincronice.
TABLAS_POR_FAMILIA: Dict[str, Tuple[Dict[str, Any], ...]] = {
    "HID": (LIMITES_MOTOR, LIMITES_HIDRAULICO),
}
FAMILIA_POR_DEFECTO: Tuple[Dict[str, Any], ...] = (LIMITES_MOTOR,)

# Con qué constante se compara el suelo de significancia de cada unidad.
_SUELO_DE_UNIDAD = {"ppm": "suelo_ppm", "%": "suelo_pct",
                    "mgKOH/g": "suelo_mgkoh", "Abs/cm": "suelo_abs",
                    "cSt": "suelo_cst"}


class Criterio:
    """El criterio con el que se juzga: referencia + ajustes de la empresa.

    Se construye una vez por consulta y se pasa a los evaluadores. Antes esos
    leían las constantes del módulo directamente, que estaba bien mientras el
    criterio fuera uno solo para todos; con ajustes por empresa habría hecho
    falta estado global por petición, y en un servidor con varios trabajadores
    eso es una carrera esperando a pasar.
    """

    def __init__(self, ajustes: Optional[List[Dict[str, Any]]] = None):
        self._por_ambito: Dict[str, Dict[str, Dict[str, Any]]] = {
            "LIMITE": {}, "MOTOR": {}, "REGLA": {}}
        for a in (ajustes or []):
            ambito = a.get("ambito")
            if ambito in self._por_ambito:
                self._por_ambito[ambito][a.get("clave", "")] = a

    # ── Constantes ───────────────────────────────────────────────────────────

    def constante(self, nombre: str) -> float:
        """El valor vigente de una constante, en su unidad de presentación."""
        meta = CONSTANTES[nombre]
        ajuste = self._por_ambito["MOTOR"].get(nombre)
        if ajuste and ajuste.get("valor") is not None:
            return float(ajuste["valor"])
        return float(meta["valor"])

    def constantes_vigentes(self) -> List[Dict[str, Any]]:
        """Todas, con su valor de referencia al lado y si están ajustadas."""
        salida = []
        for nombre, meta in CONSTANTES.items():
            ajuste = self._por_ambito["MOTOR"].get(nombre)
            salida.append({
                **meta,
                "clave": nombre,
                "valor": self.constante(nombre),
                "valor_referencia": meta["valor"],
                "ajustado": bool(ajuste and ajuste.get("valor") is not None),
                "motivo": ajuste.get("motivo") if ajuste else None,
                "ajustado_por": ajuste.get("ajustado_por") if ajuste else None,
            })
        return salida

    def suelo(self, unidad: Optional[str]) -> float:
        clave = _SUELO_DE_UNIDAD.get(unidad or "")
        return self.constante(clave) if clave else 0.0

    # ── Límites ──────────────────────────────────────────────────────────────

    def limites(self, tipo_codigo: Optional[str]) -> Dict[str, Dict[str, Any]]:
        """Los límites vigentes para una familia de compartimento.

        Un límite ajustado cambia de naturaleza a EMPRESA y conserva el valor
        publicado en `referencia`, para que la pantalla pueda mostrar los dos.
        """
        tablas = TABLAS_POR_FAMILIA.get((tipo_codigo or "").upper(),
                                        FAMILIA_POR_DEFECTO)
        base: Dict[str, Dict[str, Any]] = {}
        for tabla in tablas:
            base.update(tabla)

        salida: Dict[str, Dict[str, Any]] = {}
        for codigo, limite in base.items():
            ajuste = self.ajuste_de_limite(tipo_codigo, codigo)
            if not ajuste:
                salida[codigo] = limite
                continue
            # Un ajuste puede tocar solo uno de los dos umbrales; el otro sigue
            # siendo el de referencia.
            nuevo = dict(limite)
            for campo in ("precaucion", "condena"):
                if ajuste.get(campo) is not None:
                    nuevo[campo] = float(ajuste[campo])
            nuevo["naturaleza"] = "EMPRESA"
            nuevo["criterio"] = "Ajuste de la empresa"
            nuevo["referencia"] = {"precaucion": limite.get("precaucion"),
                                   "condena": limite.get("condena"),
                                   "criterio": limite.get("criterio"),
                                   "naturaleza": limite.get("naturaleza")}
            nuevo["motivo_ajuste"] = ajuste.get("motivo")
            nuevo["ajustado_por"] = ajuste.get("ajustado_por")
            salida[codigo] = nuevo
        return salida

    def ajuste_de_limite(self, tipo_codigo: Optional[str], codigo: str
                         ) -> Optional[Dict[str, Any]]:
        return self._por_ambito["LIMITE"].get(
            f"{(tipo_codigo or '*').upper()}:{codigo}")

    # ── Reglas ───────────────────────────────────────────────────────────────

    def reglas(self) -> List[Dict[str, Any]]:
        """Las reglas ACTIVAS, en el orden vigente. Es lo que evalúa el motor.

        El orden importa más que cualquier otro ajuste: es lo que decide qué
        regla gana cuando encajan varias. A igual orden manda el de referencia,
        así reordenar una sola no baraja las demás.
        """
        return [r for r in self.reglas_vigentes() if r["activa"]]

    def reglas_vigentes(self) -> List[Dict[str, Any]]:
        """Todas, incluidas las apagadas, para poder listarlas y reactivarlas."""
        salida = []
        for i, regla in enumerate(REGLAS):
            ajuste = self._por_ambito["REGLA"].get(regla["codigo"])
            r = dict(regla)
            r["orden_referencia"] = i
            r["orden_explicito"] = bool(ajuste and ajuste.get("orden") is not None)
            r["orden"] = (int(ajuste["orden"])
                          if r["orden_explicito"] else i)
            r["activa"] = not (ajuste and ajuste.get("activa") is False)
            r["ajustado"] = bool(ajuste)
            r["referencia"] = {"severidad": regla["severidad"],
                               "urgencia": regla["urgencia"],
                               "lectura": regla["lectura"],
                               "accion": regla["accion"],
                               "orden": i}
            if ajuste:
                for campo in ("severidad", "urgencia", "lectura", "accion"):
                    if ajuste.get(campo) not in (None, ""):
                        r[campo] = ajuste[campo]
                r["motivo_ajuste"] = ajuste.get("motivo")
                r["ajustado_por"] = ajuste.get("ajustado_por")
            salida.append(r)
        # A igual número de orden gana la que se ordenó a propósito. Sin ese
        # desempate, poner una regla en la posición 0 no la subiría: perdería
        # contra la que ya estaba ahí por referencia, y reordenar —que es el
        # ajuste que más cambia el diagnóstico— no haría nada.
        salida.sort(key=lambda r: (r["orden"],
                                   0 if r["orden_explicito"] else 1,
                                   r["orden_referencia"]))
        return salida

    # ── Estado general ───────────────────────────────────────────────────────

    @property
    def hay_ajustes(self) -> bool:
        return any(self._por_ambito.values())

    def resumen_ajustes(self) -> Dict[str, int]:
        return {a: len(v) for a, v in self._por_ambito.items()}


# El criterio sin ajustes. Sirve de valor por defecto para poder seguir llamando
# a los evaluadores sin pasar nada —en una prueba, por ejemplo— y para no
# construir un objeto en cada llamada cuando la empresa no ha tocado nada.
CRITERIO_BASE = Criterio()
