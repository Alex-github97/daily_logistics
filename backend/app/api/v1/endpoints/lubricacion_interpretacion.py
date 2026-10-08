"""
Lubricación — la interpretación de las muestras, no solo su medición.

QUÉ AÑADE SOBRE LA ANALÍTICA QUE YA EXISTE
`lubricacion_analitica` responde cómo va el PROGRAMA: cuánta vida se logra,
cuánto cuesta, si se muestrea a tiempo. Esto responde otra cosa: qué le está
pasando a CADA MOTOR y por qué. Son dos preguntas distintas y por eso viven
separadas.

DE DÓNDE SALE EL CRITERIO
De la literatura y de las normas, no de la costumbre de la casa. Los límites,
las reglas de diagnóstico y su procedencia viven en `core/normas_lubricacion`,
con la fuente al lado de cada número: ASTM D5185 para los elementos, D6304 para
el agua, D2982 para el glicol, E2412 para la degradación por FTIR, D7720 para
los límites estadísticos de desgaste, D7669 para la tendencia, SAE J300 para la
banda de viscosidad, y las referencias de Tormos e ICML para lo que es práctica
publicada y no norma.

Ese archivo explica por qué esa separación importa: las normas ASTM e ISO
dicen CÓMO SE MIDE, casi nunca CUÁNDO ES MALO. Citar «ASTM D445» como origen
de un umbral de viscosidad es una cita falsa, y acá cada límite lleva el método
y el criterio en campos distintos justamente para no cometerla.

LO QUE ESTA PANTALLA RESPONDE, EN ORDEN
  1. Quién no se ha muestreado. Sin cobertura, todo lo demás mide una parte de
     la flota y se presenta como si midiera toda.
  2. Qué le pasa a cada placa, con la tendencia entre las dos últimas muestras.
     Un valor alto sostenido y un valor que se disparó no son el mismo problema.
  3. Por qué le pasa: la cadena causa-efecto de la literatura, y la correlación
     real de los datos para comprobar si se está cumpliendo en esta flota.
  4. Qué hacer: la acción sale de la regla que encaja con el patrón completo,
     no del peor valor suelto.
  5. Si se puede estirar el intervalo de cambio, y qué lo impide.

POR QUÉ EL PATRÓN Y NO EL VALOR MÁS ALTO
Porque el diagnóstico está en la combinación. Silicio con aluminio es polvo;
silicio sin aluminio probablemente no lo es. Cobre con plomo y estaño es el
casquete; cobre solo suele ser lavado del enfriador de aceite. Mirar el peor
número de la lista y no el conjunto produce la recomendación genérica que nadie
aplica —y, en el caso del cobre, manda a desarmar motores sanos.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.lubricacion_flota import (
    FiltroFlota, _base_muestras, _criterio,
)
from app.core.database import get_db
from app.core.normas_lubricacion import (
    CATEGORIAS_REPARACION, FUENTES, GRUPO_DESGASTE, Criterio,
    diagnosticar, evaluar_muestra, limites_estadisticos, pearson,
)
from app.infrastructure.models.eam import EAMActivo
from app.infrastructure.models.lubricacion import (
    LubeCarga, LubeCompartimento, LubeDiagnostico, LubeMotivoDrenaje,
    LubeMuestra, LubeParametro, LubeProducto, LubeResultado,
    LubeTipoCompartimento,
)

router = APIRouter(prefix="/eam/lube/interpretacion",
                   tags=["CMMS/EAM · Lubricación · Interpretación"])


# ══════════════════════════════════════════════════════════════════════════════
# La notación del comité
#
# En el informe cada muestra se resume con las siglas de lo que está fuera:
# «Fe-Al-Cu-Si-Na», «Cu», «<Visc». Es notación de taller y hay que respetarla:
# quien lee el informe la reconoce de un vistazo, y traducirla a nombres largos
# convierte una tabla legible en un muro de texto.
# ══════════════════════════════════════════════════════════════════════════════

SIGLA: Dict[str, str] = {
    "fe": "Fe", "cr": "Cr", "pb": "Pb", "cu": "Cu", "sn": "Sn", "al": "Al",
    "ni": "Ni", "mo": "Mo", "si": "Si", "na": "Na", "k": "K", "b": "B",
    "ca": "Ca", "mg": "Mg", "zn": "Zn", "p": "P", "ba": "Ba",
    "agua": "Agua", "combustible": "Comb", "hollin": "Hollín", "glicol": "Glicol",
    "tbn": "TBN", "tan": "TAN", "oxidacion": "Oxid", "nitracion": "Nitr",
    "sulfatacion": "Sulf", "pq": "PQ", "iso4406": "ISO",
}

# La viscosidad se anota con la dirección, porque bajar y subir son averías
# distintas: bajar es dilución por combustible, subir es oxidación.
VISCOSIDADES = {"viscosidad", "visc100"}

# El orden en que se listan las siglas. No es alfabético: primero los metales de
# desgaste —que es lo que rompe el motor—, después los contaminantes que los
# causan, y de últimas las propiedades del aceite.
ORDEN_SIGLAS = ["fe", "cr", "pb", "cu", "sn", "al", "ni", "mo",
                "si", "na", "k", "agua", "glicol", "combustible", "hollin",
                "b", "ca", "mg", "zn", "p", "ba",
                "viscosidad", "visc100", "tbn", "tan",
                "oxidacion", "nitracion", "sulfatacion", "pq", "iso4406"]


# ══════════════════════════════════════════════════════════════════════════════
# La cadena causa-efecto
#
# Los mecanismos de degradación y desgaste descritos en la literatura de
# análisis de aceite en motor diésel, cada uno con su fuente. La pantalla los
# contrasta con la correlación medida en esta flota: al lado de «esto es lo que
# dice la literatura» va «esto es lo que dicen los datos de aquí».
#
# QUÉ SE CORRIGIÓ FRENTE A LA VERSIÓN ANTERIOR
# La cadena que había venía de la lectura interna del comité y tenía dos
# mecanismos mal explicados. El más importante: decía que la sulfatación
# desgasta porque «las partículas de azufre actúan como abrasivo». No es así.
# La sulfatación que mide el FTIR no son partículas: es la formación de
# compuestos sulfurados en el aceite a partir del azufre del combustible. Lo
# que produce es ACIDEZ, y la acidez ataca químicamente los metales blandos
# —plomo, cobre, estaño—. Es desgaste corrosivo, no abrasivo, y la distinción
# no es académica: contra un abrasivo se revisa la filtración y la admisión,
# y contra la acidez se revisa el azufre del combustible y el TBN del aceite.
# Diagnosticar uno y actuar sobre el otro no arregla nada.
#
# Se declara aquí, a la vista, y no dentro de un cálculo: cuando el próximo
# análisis la corrija —y lo hará— hay que poder cambiarla en un sitio y que se
# note en toda la pantalla.
# ══════════════════════════════════════════════════════════════════════════════

CADENA_CAUSAL: List[Dict[str, Any]] = [
    {
        "causa": ["agua"],
        "efecto": ["b", "na", "k"],
        "fuentes": ["ASTM D5185", "ASTM D2982", "ICML"],
        "porque": "Los refrigerantes llevan inhibidores de corrosión a base de "
                  "boratos, nitritos y silicatos de sodio y potasio. Si entra "
                  "refrigerante, entran con él esos tres elementos y sube el "
                  "agua, sin que el aceite haya perdido su propio aditivo.",
        "accion": "Confirmar con ensayo de glicol (ASTM D2982) y revisar el "
                  "paso al cárter: empaque de culata, enfriador de aceite, "
                  "camisas.",
    },
    {
        "causa": ["agua", "glicol"],
        "efecto": ["oxidacion", "tan"],
        "fuentes": ["ASTM E2412", "ASTM D664", "Tormos"],
        "porque": "El agua y el glicol hidrolizan los aditivos y catalizan la "
                  "oxidación del aceite base. El producto de esa oxidación son "
                  "ácidos orgánicos, que es lo que mide el TAN.",
        "accion": "Cerrar la entrada de refrigerante antes de cambiar la "
                  "carga: el aceite nuevo se degrada igual si la fuga sigue "
                  "abierta.",
    },
    {
        "causa": ["sulfatacion"],
        "efecto": ["tan"],
        "efecto_inverso": ["tbn"],
        "fuentes": ["ASTM E2412", "ASTM D664", "ASTM D4739"],
        "porque": "El azufre del combustible forma compuestos sulfurados que "
                  "acidifican el aceite. Cada punto de acidez consume reserva "
                  "alcalina: la sulfatación sube, el TAN sube y el TBN baja, "
                  "los tres a la vez.",
        "accion": "Verificar el azufre del combustible. Con azufre alto hay que "
                  "acortar el intervalo o subir el TBN del aceite.",
    },
    {
        "causa": ["tan"],
        "efecto": ["pb", "cu", "sn"],
        "fuentes": ["ASTM D664", "Tormos", "ICML"],
        "porque": "Cuando la acidez supera lo que la reserva alcalina puede "
                  "neutralizar, ataca químicamente los metales blandos del "
                  "cojinete —plomo, cobre y estaño— por corrosión. No es "
                  "abrasión: es un ataque químico, y por eso afecta justo a "
                  "esos tres y no al hierro de las camisas.",
        "accion": "Cambiar la carga. Si se repite en la familia, el problema "
                  "es el combustible o el intervalo, no el motor.",
    },
    {
        "causa": ["si"],
        "efecto": ["fe", "cr", "al"],
        "fuentes": ["ASTM D5185", "Tormos", "ICML"],
        "porque": "La sílice del polvo tiene la dureza justa para rayar las "
                  "superficies de trabajo. Ataca camisas, anillos y árbol de "
                  "levas —hierro y cromo— y los pistones —aluminio—. Es el "
                  "contaminante más destructivo del motor, y el aceite nuevo "
                  "no lo resuelve porque la entrada sigue abierta.",
        "accion": "Revisar todo el lado de admisión: filtro, sello del filtro, "
                  "abrazaderas, mangueras.",
    },
    {
        "causa": ["combustible"],
        "efecto_inverso": ["viscosidad", "visc100"],
        "efecto": ["fe", "cu", "pb"],
        "fuentes": ["ASTM D7593", "ASTM D445", "Tormos"],
        "porque": "El combustible baja la viscosidad y con ella el espesor de "
                  "película. En los cojinetes el régimen pasa de "
                  "hidrodinámico a mixto, y ahí es donde aparece el contacto "
                  "metal-metal. La correlación con la viscosidad tiene que ser "
                  "NEGATIVA: si sale positiva, hay que dudar del ensayo.",
        "accion": "Revisar inyección, y descartar ralentí prolongado y "
                  "regeneraciones incompletas del filtro de partículas.",
    },
    {
        "causa": ["hollin"],
        "efecto": ["viscosidad", "fe"],
        "fuentes": ["ASTM D7844", "ICML"],
        "porque": "El hollín suspendido no desgasta. Cuando el dispersante se "
                  "agota, aglomera: sube la viscosidad, tapa el filtro y las "
                  "aglomeraciones sí desgastan el tren de válvulas.",
        "accion": "Revisar filtro de aire, inyección y tiempos.",
    },
    {
        "causa": ["fe"],
        "efecto": ["al"],
        "fuentes": ["ICML"],
        "porque": "Las partículas de hierro desprendidas son más duras que el "
                  "aluminio y producen desgaste abrasivo de tres cuerpos sobre "
                  "pistones y carcasas. Es un efecto secundario: el aluminio "
                  "es consecuencia y no causa.",
        "accion": "Atender primero el origen del hierro.",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# Las reglas de diagnóstico viven en `core/normas_lubricacion`
#
# Antes estaban acá, escritas a partir de los casos que el comité de la empresa
# había resuelto. Se movieron porque cambiaron de naturaleza: ahora salen de la
# literatura y de las normas, cada una con su fuente, y ese cuerpo de criterio
# lo usan tanto esta pantalla como el evaluador de muestras. Dejarlo en un
# endpoint lo habría vuelto inaccesible para el resto del módulo.
#
# `normas_lubricacion.REGLAS` mantiene la misma mecánica de antes —se evalúan en
# orden y gana la primera que encaje— porque combinar todas las que aplican
# produce una recomendación que dice seis cosas y no manda hacer ninguna.
# ══════════════════════════════════════════════════════════════════════════════


async def _viene_de_reparacion(db: AsyncSession, muestra: LubeMuestra,
                               comp_id: int, criterio: Criterio) -> bool:
    """¿La carga actual entró después de una reparación, y hace poco?

    QUÉ CUENTA COMO «RECIÉN REPARADO»
    Que la carga ANTERIOR se haya drenado por una intervención mayor o por una
    falla del equipo. No basta con que el aceite sea nuevo: un cambio por
    calendario no explica nada, y tomarlo como reparación daría por normal el
    desgaste de cualquier motor recién servido.
    """
    if not muestra.carga_id:
        return False
    carga = await db.get(LubeCarga, muestra.carga_id)
    if not carga or not carga.fecha_llenado:
        return False
    dias = (muestra.fecha_toma - carga.fecha_llenado).days
    if not 0 <= dias <= criterio.constante("dias_asentamiento"):
        return False

    # La carga que se drenó justo antes de esta, en el mismo compartimento.
    anterior = (await db.execute(
        select(LubeCarga)
        .where(and_(LubeCarga.compartimento_id == comp_id,
                    LubeCarga.id != carga.id,
                    LubeCarga.fecha_llenado < carga.fecha_llenado))
        .order_by(LubeCarga.fecha_llenado.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not anterior or not anterior.motivo_drenaje_id:
        return False
    motivo = await db.get(LubeMotivoDrenaje, anterior.motivo_drenaje_id)
    return bool(motivo and motivo.categoria in CATEGORIAS_REPARACION)


async def _catalogo(db: AsyncSession) -> Dict[int, LubeParametro]:
    r = await db.execute(select(LubeParametro))
    return {p.id: p for p in r.scalars().all()}


def _sigla(p: LubeParametro, valor: Optional[float],
           limites_bajos: bool = False) -> str:
    """La sigla con que el comité anota un parámetro fuera de rango."""
    base = SIGLA.get(p.codigo, p.codigo[:4].capitalize())
    if p.codigo in VISCOSIDADES:
        return ("<Visc" if limites_bajos else ">Visc")
    if p.codigo == "tbn":
        return "<TBN"
    return base


def _ordenar_siglas(codigos: List[str]) -> List[str]:
    posicion = {c: i for i, c in enumerate(ORDEN_SIGLAS)}
    return sorted(codigos, key=lambda c: posicion.get(c, 999))


# ══════════════════════════════════════════════════════════════════════════════
# 1. Cobertura de muestreo
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/cobertura")
async def cobertura(
    anio: Optional[int] = None,
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Quién no se ha muestreado, y quién no se ha muestreado nunca.

    ES LO PRIMERO QUE SE MIRA, Y POR UNA RAZÓN
    Todo lo demás —tendencias, correlaciones, ahorros— se calcula sobre los
    equipos que sí tienen muestra. Presentarlo sin decir a cuántos equipos deja
    fuera es presentar una parte de la flota como si fuera toda. Un motor sin
    muestra no es un motor sano: es un motor del que no se sabe nada.

    Se distinguen dos casos porque piden acciones distintas: al que tiene
    histórico y se le venció el turno hay que programarlo; al que nunca se ha
    muestreado hay que instalarle primero el punto de toma.
    """
    anio = anio or date.today().year
    inicio = datetime(anio, 1, 1)

    # Todos los compartimentos que se analizan. Los puntos de grasa se excluyen:
    # no se les toma muestra, y contarlos como «sin muestrear» inflaría la
    # brecha con equipos a los que nunca les correspondió.
    filas = (await db.execute(f.aplicar(
        select(LubeCompartimento, EAMActivo, LubeTipoCompartimento)
        .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
        .join(LubeTipoCompartimento,
              LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
        .where(LubeTipoCompartimento.codigo != "GRA")
    ))).all()

    ultima_por_comp: Dict[int, datetime] = {}
    en_anio: set = set()
    for comp_id, fecha in (await db.execute(
        select(LubeMuestra.compartimento_id, func.max(LubeMuestra.fecha_toma))
        .where(LubeMuestra.estado != "ANULADA")
        .group_by(LubeMuestra.compartimento_id)
    )).all():
        ultima_por_comp[comp_id] = fecha
    for (comp_id,) in (await db.execute(
        select(LubeMuestra.compartimento_id).distinct()
        .where(and_(LubeMuestra.estado != "ANULADA",
                    LubeMuestra.fecha_toma >= inicio))
    )).all():
        en_anio.add(comp_id)

    sin_muestra_anio: List[Dict[str, Any]] = []
    sin_historico: List[Dict[str, Any]] = []
    for comp, activo, tipo in filas:
        if comp.id in en_anio:
            continue
        ultima = ultima_por_comp.get(comp.id)
        fila = {
            "compartimento_id": comp.id,
            "compartimento": comp.nombre,
            "tipo": tipo.nombre,
            "placa": activo.codigo,
            "activo": activo.nombre,
            "familia_motor": activo.linea or activo.marca or "Sin clasificar",
            "marca": activo.marca,
            "ultima_muestra": ultima,
        }
        (sin_historico if ultima is None else sin_muestra_anio).append(fila)

    # Los que llevan más tiempo sin muestra van primero: son los que más riesgo
    # acumulan y los que menos se notan en una lista alfabética.
    sin_muestra_anio.sort(key=lambda x: x["ultima_muestra"] or datetime.min)

    # La cobertura se mide sobre los compartimentos DEL SEGMENTO. Con un filtro
    # puesto, `en_anio` trae los de toda la empresa, y contarlos daría más
    # cubiertos que analizables —una cobertura del 300 %—.
    del_segmento = {comp.id for comp, _a, _t in filas}
    total = len(filas)
    cubiertos = len(en_anio & del_segmento)
    return {
        "anio": anio,
        "filtro": f.como_dict(),
        "compartimentos_analizables": total,
        "con_muestra_en_el_anio": cubiertos,
        "cobertura_pct": round(100 * cubiertos / total, 1) if total else 0.0,
        "sin_muestra_en_el_anio": sin_muestra_anio,
        "sin_historico": sin_historico,
    }


@router.get("/compartimentos")
async def compartimentos(f: FiltroFlota = Depends(),
                         db: AsyncSession = Depends(get_db)):
    """Los compartimentos que se analizan, para escoger uno.

    Trae cuántas muestras tiene cada uno y la severidad de la última: quien
    abre el selector normalmente busca el que está peor, no el primero por
    orden alfabético.
    """
    filas = (await db.execute(f.aplicar(
        select(LubeCompartimento, EAMActivo, LubeTipoCompartimento)
        .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
        .join(LubeTipoCompartimento,
              LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
        .where(LubeTipoCompartimento.codigo != "GRA")
        .order_by(EAMActivo.codigo)
    ))).all()

    conteo: Dict[int, int] = {}
    for comp_id, n in (await db.execute(
        select(LubeMuestra.compartimento_id, func.count())
        .where(LubeMuestra.estado != "ANULADA")
        .group_by(LubeMuestra.compartimento_id)
    )).all():
        conteo[comp_id] = n

    # La severidad de la última muestra de cada compartimento.
    ultima: Dict[int, Tuple[datetime, Optional[str]]] = {}
    for comp_id, cuando, sev in (await db.execute(
        select(LubeMuestra.compartimento_id, LubeMuestra.fecha_toma,
               LubeMuestra.severidad)
        .where(LubeMuestra.estado != "ANULADA")
        .order_by(LubeMuestra.fecha_toma)
    )).all():
        ultima[comp_id] = (cuando, sev)

    peso = {"ACCION_INMEDIATA": 0, "CRITICO": 1, "MARGINAL": 2, "NORMAL": 3}
    salida = [{
        "compartimento_id": comp.id,
        "compartimento": comp.nombre,
        "tipo": tipo.nombre,
        "placa": activo.codigo,
        "activo": activo.nombre,
        "familia_motor": activo.linea or activo.marca or "Sin clasificar",
        "muestras": conteo.get(comp.id, 0),
        "ultima_muestra": ultima.get(comp.id, (None, None))[0],
        "severidad_ultima": ultima.get(comp.id, (None, None))[1],
    } for comp, activo, tipo in filas]
    salida.sort(key=lambda x: (peso.get(x["severidad_ultima"] or "", 4), x["placa"]))
    return salida


# ══════════════════════════════════════════════════════════════════════════════
# 2. El tablero de conclusiones
#
# Una fila por muestra: qué salió fuera, contra qué límite, de dónde sale ese
# límite, qué significa el conjunto y qué hacer. Es la vista con la que se abre
# la reunión.
#
# CÓMO SE FORMA CADA FILA
#   1. Se recogen los valores medidos de la muestra y los de la muestra
#      anterior del mismo compartimento —la tendencia necesita las dos—.
#   2. Se evalúan contra los límites de norma y contra el límite estadístico de
#      la propia flota para los metales de desgaste (ASTM D7720).
#   3. La regla que encaja con el patrón completo da la lectura y la acción.
#   4. Un diagnóstico escrito por una persona manda sobre el automático.
#
# POR QUÉ SE RECALCULA Y NO SE LEE `LubeResultado.estado`
# Porque aquel estado lo puso el evaluador contra los límites CONFIGURADOS en
# la empresa, que pueden estar sin cargar, mal cargados o desactualizados. Esta
# pantalla afirma que juzga según norma, y para poder afirmarlo tiene que
# aplicar la norma ella misma. Los dos números conviven a la vista: la columna
# de severidad del sistema sigue ahí, y cuando difieren la diferencia es
# información —normalmente, que los límites de la configuración no coinciden
# con el criterio de referencia—.
# ══════════════════════════════════════════════════════════════════════════════

async def _poblacion_desgaste(db: AsyncSession, tipo_de_muestra: Dict[int, str],
                              catalogo: Dict[int, LubeParametro],
                              criterio: Criterio,
                              ) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Los límites estadísticos de ASTM D7720, POR FAMILIA DE COMPARTIMENTO.

    Devuelve `{código de tipo: {parámetro: límite}}`. La separación por familia
    es la mitad de la norma: un percentil de hierro sacado de los motores y los
    hidráulicos juntos no describe a ninguno de los dos, porque sus rangos
    normales no se parecen.

    Se calculan una vez para todo el tablero y no muestra por muestra: son un
    percentil de la población, así que recalcularlos por fila daría el mismo
    número treinta veces y treinta consultas.
    """
    if not tipo_de_muestra:
        return {}
    poblaciones: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list))
    for mid, pid, valor in (await db.execute(
        select(LubeResultado.muestra_id, LubeResultado.parametro_id,
               LubeResultado.valor)
        .where(and_(LubeResultado.muestra_id.in_(list(tipo_de_muestra.keys())),
                    LubeResultado.valor.isnot(None)))
    )).all():
        p = catalogo.get(pid)
        if p and p.codigo in GRUPO_DESGASTE:
            poblaciones[tipo_de_muestra[mid]][p.codigo].append(float(valor))
    return {tipo: limites_estadisticos(pob, criterio)
            for tipo, pob in poblaciones.items()}


async def _anteriores(db: AsyncSession, muestras: List[LubeMuestra],
                      catalogo: Dict[int, LubeParametro],
                      ) -> Dict[int, Dict[str, float]]:
    """Los valores de la muestra ANTERIOR de cada compartimento.

    La tendencia es la mitad del diagnóstico —ASTM D7669— y sin la muestra
    previa no se puede calcular. Se resuelve en dos consultas para toda la
    tabla: una por muestra serían cientos.
    """
    if not muestras:
        return {}
    comp_ids = {m.compartimento_id for m in muestras}
    # Todas las muestras de esos compartimentos, ordenadas: con eso se sabe
    # cuál precede a cuál sin una consulta por fila.
    orden: Dict[int, List[Tuple[datetime, int]]] = defaultdict(list)
    for comp_id, fecha, mid in (await db.execute(
        select(LubeMuestra.compartimento_id, LubeMuestra.fecha_toma,
               LubeMuestra.id)
        .where(and_(LubeMuestra.compartimento_id.in_(comp_ids),
                    LubeMuestra.estado != "ANULADA"))
        .order_by(LubeMuestra.compartimento_id, LubeMuestra.fecha_toma)
    )).all():
        orden[comp_id].append((fecha, mid))

    previa_de: Dict[int, int] = {}
    for comp_id, lista in orden.items():
        for i in range(1, len(lista)):
            previa_de[lista[i][1]] = lista[i - 1][1]

    necesarias = {previa_de[m.id] for m in muestras if m.id in previa_de}
    if not necesarias:
        return {}
    valores: Dict[int, Dict[str, float]] = defaultdict(dict)
    for mid, pid, valor in (await db.execute(
        select(LubeResultado.muestra_id, LubeResultado.parametro_id,
               LubeResultado.valor)
        .where(and_(LubeResultado.muestra_id.in_(necesarias),
                    LubeResultado.valor.isnot(None)))
    )).all():
        p = catalogo.get(pid)
        if p:
            valores[mid][p.codigo] = float(valor)

    return {m.id: valores.get(previa_de.get(m.id, -1), {}) for m in muestras}


# Qué severidades mandan a actuar y cuáles no. La discrepancia que importa es
# la que cruza esta línea.
_ACCIONABLES = {"CRITICO", "ACCION_INMEDIATA"}


def _cambia_la_decision(sistema: Optional[str], norma: str) -> bool:
    """¿El criterio de norma y el del sistema mandan cosas distintas?"""
    if not sistema or sistema == "PENDIENTE":
        return False
    return (sistema in _ACCIONABLES) != (norma in _ACCIONABLES)


@router.get("/tablero")
async def tablero(
    dias: int = Query(180, ge=30, le=1825),
    solo_con_hallazgo: bool = True,
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """La tabla de conclusiones: placa, qué salió, contra qué norma, y qué hacer.

    La notación abreviada de la columna «Tipo» —«Fe-Al-Cu-Si-Na»— es notación
    de taller y hay que respetarla: quien lee el informe la reconoce de un
    vistazo, y traducirla a nombres largos convierte una tabla legible en un
    muro de texto.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    criterio = await _criterio(db)
    catalogo = await _catalogo(db)
    por_codigo = {p.codigo: p for p in catalogo.values()}

    muestras = (await db.execute(
        _base_muestras(f, desde).order_by(LubeMuestra.fecha_toma.desc())
    )).all()
    if not muestras:
        return {"desde": desde, "filas": [], "resumen": {},
                "limites_flota": {}, "fuentes": FUENTES}

    ids = [m.id for m, _, _, _ in muestras]
    lista_muestras = [m for m, _, _, _ in muestras]

    por_muestra: Dict[int, List[LubeResultado]] = defaultdict(list)
    for r in (await db.execute(
        select(LubeResultado).where(LubeResultado.muestra_id.in_(ids))
    )).scalars().all():
        por_muestra[r.muestra_id].append(r)

    tipo_de_muestra = {m.id: (t.codigo or "SIN_TIPO")
                       for m, _c, _a, t in muestras}
    estadisticos = await _poblacion_desgaste(db, tipo_de_muestra, catalogo,
                                             criterio)
    valores_previos = await _anteriores(db, lista_muestras, catalogo)

    # El grado SAE del aceite realmente cargado. Es la referencia contra la que
    # SAE J300 permite juzgar la viscosidad, y sin él ese juicio no se hace en
    # vez de hacerse contra un promedio inventado.
    grados: Dict[int, Optional[str]] = {}
    cargas_necesarias = {m.carga_id for m in lista_muestras if m.carga_id}
    if cargas_necesarias:
        for carga_id, grado in (await db.execute(
            select(LubeCarga.id, LubeProducto.grado_sae)
            .join(LubeProducto, LubeProducto.id == LubeCarga.producto_id)
            .where(LubeCarga.id.in_(cargas_necesarias))
        )).all():
            grados[carga_id] = grado

    # Los diagnósticos ya escritos por una persona mandan sobre el automático:
    # quien miró el motor sabe cosas que la muestra no dice.
    manuales: Dict[int, LubeDiagnostico] = {}
    for d in (await db.execute(
        select(LubeDiagnostico).where(LubeDiagnostico.muestra_id.in_(ids))
    )).scalars().all():
        if not d.automatico:
            manuales[d.muestra_id] = d

    filas: List[Dict[str, Any]] = []
    resumen: Dict[str, int] = defaultdict(int)

    for muestra, comp, activo, tipo in muestras:
        resultados = por_muestra.get(muestra.id, [])
        valores: Dict[str, float] = {}
        unidades: Dict[str, Optional[str]] = {}
        iso_medido: Optional[str] = None
        estados_sistema: Dict[str, str] = {}
        for r in resultados:
            p = catalogo.get(r.parametro_id)
            if not p:
                continue
            unidades[p.codigo] = p.unidad
            estados_sistema[p.codigo] = r.estado or "NORMAL"
            if p.codigo == "iso4406":
                iso_medido = r.valor_texto
            elif r.valor is not None:
                valores[p.codigo] = float(r.valor)

        evaluacion = evaluar_muestra(
            valores=valores, unidades=unidades,
            anteriores=valores_previos.get(muestra.id, {}),
            tipo_compartimento=tipo.codigo,
            estadisticos=estadisticos.get(tipo.codigo or "SIN_TIPO", {}),
            grado_sae=grados.get(muestra.carga_id or -1),
            meta_iso=comp.meta_iso4406,
            iso_medido=iso_medido,
            criterio=criterio,
        )
        hallazgos = evaluacion["hallazgos"]
        fuera = [c for c, h in hallazgos.items() if h.get("estado")]

        if solo_con_hallazgo and not hallazgos:
            continue

        post_reparacion = await _viene_de_reparacion(db, muestra, comp.id,
                                                     criterio)
        regla = diagnosticar(evaluacion, post_reparacion, criterio)

        # El estado de la fila sale de la severidad de la regla, que ya
        # incorpora si algún parámetro llegó a condena.
        estado = {"ACCION_INMEDIATA": "CRITICO", "CRITICO": "CRITICO",
                  "MARGINAL": "ALERTA", "NORMAL": "NORMAL"}.get(
                      regla["severidad"], "ALERTA")

        detalle = []
        for codigo in _ordenar_siglas(list(hallazgos.keys())):
            h = hallazgos[codigo]
            p = por_codigo.get(codigo)
            if not p:
                continue
            bajo = p.codigo in VISCOSIDADES or p.codigo == "tbn"
            detalle.append({
                "codigo": codigo, "nombre": p.nombre,
                "sigla": _sigla(p, h.get("valor"), bajo),
                "valor": h.get("valor"), "texto": h.get("texto"),
                "unidad": h.get("unidad"),
                # NORMAL no aparece acá: si un parámetro está en `hallazgos` es
                # porque cruzó un límite o porque se movió. Un tercer estado
                # vacío obligaría a la pantalla a distinguir «sin estado» de
                # «normal», que no es la misma cosa.
                "estado": h.get("estado") or "TENDENCIA",
                "limite": h.get("limite"),
                "tendencia": h.get("tendencia"),
                "origen_probable": p.origen_probable,
                "estado_sistema": estados_sistema.get(codigo),
            })

        ordenados = _ordenar_siglas(fuera)
        mapa_sigla = {d["codigo"]: d["sigla"] for d in detalle}
        manual = manuales.get(muestra.id)
        filas.append({
            "muestra_id": muestra.id,
            "numero": muestra.numero,
            "familia_motor": activo.linea or activo.marca or "Sin clasificar",
            "marca": activo.marca,
            "linea": activo.linea,
            "modelo": activo.modelo,
            "motor": (f"{activo.motor_marca} · {activo.motor_linea}"
                      if activo.motor_marca and activo.motor_linea
                      else activo.motor_marca),
            "placa": activo.codigo,
            "activo": activo.nombre,
            "compartimento": comp.nombre,
            "compartimento_id": comp.id,
            "tipo_compartimento": tipo.codigo,
            "km": muestra.medidor_equipo,
            "horas_aceite": muestra.horas_aceite,
            # La vida del aceite se mide en horas en un motor y en
            # kilómetros en un diferencial. Sin la unidad, «500» no dice
            # nada: la trae el tipo de compartimento y viaja con el dato.
            "unidad_vida": tipo.unidad_vida,
            "fecha_toma": muestra.fecha_toma,
            "tipo": "-".join(mapa_sigla[c] for c in ordenados if c in mapa_sigla) or "—",
            "patron": regla["nombre"],
            "regla": regla["codigo"],
            "lectura": regla["lectura"],
            "criterio": regla["criterio"],
            "fuentes": regla.get("fuentes", []),
            "accion_sugerida": manual.recomendacion if manual else regla["accion"],
            "accion_de_persona": bool(manual),
            "estado": estado,
            "severidad_norma": regla["severidad"],
            # Lo que la regla declara para su modo de falla, que puede ser
            # peor que lo alcanzado por esta muestra. Permite decir «este
            # modo de falla es crítico, pero esta muestra todavía no».
            "severidad_del_modo": regla.get("severidad_declarada",
                                            regla["severidad"]),
            "urgencia": regla["urgencia"],
            "severidad_sistema": muestra.severidad,
            # SOLO SE MARCA LA DISCREPANCIA QUE CAMBIA LA DECISIÓN.
            # Marcar cualquier diferencia entre el criterio de norma y el que
            # el sistema calculó con los límites configurados llenó de avisos
            # 138 de 149 filas en la primera prueba, y un aviso que sale en el
            # 93 % de las filas no avisa de nada. Lo que importa es el salto
            # entre «no pasa nada» y «hay que actuar»: que una muestra sea
            # marginal para uno y crítica para el otro no cambia lo que se hace
            # con ella.
            "discrepa": _cambia_la_decision(muestra.severidad,
                                            regla["severidad"]),
            "cruce_tbn_tan": evaluacion["cruce_tbn_tan"],
            "relacion_si_al": evaluacion["relacion_si_al"],
            "desvio_viscosidad": evaluacion["desvio_viscosidad"],
            "detalle": detalle,
        })
        resumen[estado] += 1

    # Lo urgente primero, y a igual urgencia lo más reciente: es el orden en
    # que se revisa en la reunión.
    filas.sort(key=lambda x: (-x["urgencia"], x["fecha_toma"]), reverse=False)
    filas.sort(key=lambda x: x["urgencia"], reverse=True)

    return {
        "desde": desde,
        "filtro": f.como_dict(),
        "filas": filas,
        "resumen": dict(resumen),
        # Los límites estadísticos con que se juzgó, por familia de
        # compartimento, para que la pantalla pueda decir contra qué se comparó
        # y sobre cuántas mediciones. Cada fila ya trae su propio límite en el
        # detalle; esto es el resumen.
        "limites_flota": estadisticos,
        "fuentes": FUENTES,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. Análisis por placa, con tendencia
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/placa/{compartimento_id}")
async def por_placa(
    compartimento_id: int,
    muestras: int = Query(8, ge=2, le=40),
    db: AsyncSession = Depends(get_db),
):
    """El seguimiento de un compartimento: qué se movió entre las dos últimas.

    POR QUÉ LA COMPARACIÓN ENTRE LAS DOS ÚLTIMAS Y NO SOLO EL VALOR
    Porque un valor alto y estable y un valor que se disparó no son el mismo
    problema. El primero suele ser el nivel normal de ese motor; el segundo es
    algo que empezó a pasar. Es el fundamento de ASTM D7669 —análisis de
    tendencia— y por eso la tabla presenta siempre las dos lecturas juntas,
    penúltima y última, en vez del último número solo.

    Cada punto de la serie trae el kilometraje además de la fecha: dos muestras
    del mismo mes con 8.000 km de diferencia no son comparables, y el
    kilometraje es el eje que las ordena de verdad.
    """
    comp = await db.get(LubeCompartimento, compartimento_id)
    if not comp:
        raise HTTPException(404, "Ese compartimento no existe.")
    activo = await db.get(EAMActivo, comp.activo_id)
    catalogo = await _catalogo(db)

    historia = list((await db.execute(
        select(LubeMuestra)
        .where(and_(LubeMuestra.compartimento_id == compartimento_id,
                    LubeMuestra.estado != "ANULADA"))
        .order_by(LubeMuestra.fecha_toma.desc())
        .limit(muestras)
    )).scalars().all())
    if not historia:
        return {"compartimento": comp.nombre,
                "placa": activo.codigo if activo else None,
                "series": [], "cambios": [], "muestras": []}

    historia.reverse()   # de la más antigua a la más reciente, para graficar
    ids = [m.id for m in historia]
    por_muestra: Dict[int, Dict[int, LubeResultado]] = defaultdict(dict)
    for r in (await db.execute(
        select(LubeResultado).where(LubeResultado.muestra_id.in_(ids))
    )).scalars().all():
        por_muestra[r.muestra_id][r.parametro_id] = r

    # Una serie por parámetro que tenga al menos un valor. Los que nunca se
    # midieron no se listan: una línea plana en cero se lee como «está en cero»,
    # que es distinto de «no se midió».
    series: List[Dict[str, Any]] = []
    for pid, p in catalogo.items():
        puntos = []
        for m in historia:
            r = por_muestra.get(m.id, {}).get(pid)
            if r is None or r.valor is None:
                continue
            puntos.append({"fecha": m.fecha_toma, "numero": m.numero,
                           "km": m.medidor_equipo,
                           "valor": r.valor, "estado": r.estado,
                           "horas_aceite": m.horas_aceite})
        if not puntos:
            continue
        series.append({
            "codigo": p.codigo, "nombre": p.nombre, "sigla": SIGLA.get(p.codigo, p.codigo),
            "unidad": p.unidad, "grupo": p.grupo,
            "origen_probable": p.origen_probable,
            "puntos": puntos,
        })

    # Lo que se movió entre la penúltima y la última.
    cambios: List[Dict[str, Any]] = []
    if len(historia) >= 2:
        ultima, penultima = historia[-1], historia[-2]
        for pid, p in catalogo.items():
            a = por_muestra.get(penultima.id, {}).get(pid)
            b = por_muestra.get(ultima.id, {}).get(pid)
            if a is None or b is None or a.valor is None or b.valor is None:
                continue
            if a.valor == 0 and b.valor == 0:
                continue
            delta = b.valor - a.valor
            # Un cambio menor al 15% es ruido de laboratorio, no una tendencia.
            # Marcarlo llenaría la lista de movimientos que no significan nada.
            base = abs(a.valor) or 1.0
            pct = delta / base * 100
            if abs(pct) < 15 and b.estado == "NORMAL":
                continue
            cambios.append({
                "codigo": p.codigo, "nombre": p.nombre,
                "sigla": SIGLA.get(p.codigo, p.codigo), "unidad": p.unidad,
                "grupo": p.grupo, "origen_probable": p.origen_probable,
                "penultima": a.valor, "ultima": b.valor,
                "delta": round(delta, 3), "variacion_pct": round(pct, 1),
                "estado": b.estado, "tasa_cambio": b.tasa_cambio,
            })
        # Lo que empeoró primero, y dentro de eso lo que más se movió.
        peso = {"CRITICO": 0, "MARGINAL": 1, "NORMAL": 2}
        cambios.sort(key=lambda c: (peso.get(c["estado"], 3), -abs(c["variacion_pct"])))

    return {
        "compartimento_id": comp.id,
        "compartimento": comp.nombre,
        "placa": activo.codigo if activo else None,
        "activo": activo.nombre if activo else None,
        "familia_motor": (activo.linea or activo.marca) if activo else None,
        "muestras": [{"id": m.id, "numero": m.numero, "fecha": m.fecha_toma,
                      "severidad": m.severidad, "horas_aceite": m.horas_aceite}
                     for m in historia],
        "series": series,
        "cambios": cambios,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. Correlación entre parámetros
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/correlacion")
async def correlacion(
    familia: Optional[str] = None,
    dias: int = Query(1460, ge=90, le=3650),
    minimo_muestras: int = Query(8, ge=4, le=200),
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Qué parámetros se mueven juntos en esta flota. Pearson.

    PARA QUÉ SIRVE Y PARA QUÉ NO
    Sirve para comprobar si los mecanismos que describe la literatura se están
    cumpliendo con los datos de aquí. No sirve para descubrir la causa: dos
    cosas pueden subir juntas porque una causa la otra, porque las dos tienen
    una tercera causa, o por casualidad. Por eso la respuesta trae los
    eslabones de la cadena y su correlación medida, uno al lado del otro, y no
    una lista de coeficientes sueltos que cada quien interpreta.

    `n` viaja con cada coeficiente. Una correlación de 0,99 sobre cuatro puntos
    no dice nada, y sin la cantidad de muestras eso no se puede ver.

    EL SIGNO ESPERADO ES PARTE DE LA COMPROBACIÓN
    Algunos eslabones predicen una relación INVERSA: el combustible diluye y la
    viscosidad baja, la sulfatación sube y el TBN baja. En esos casos una
    correlación positiva fuerte no confirma el mecanismo: lo contradice. Un
    contraste que solo mirara la magnitud daría por bueno justo el resultado
    que debería encender una alarma sobre el laboratorio o sobre los datos.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    criterio = await _criterio(db)
    umbral = criterio.constante("umbral_confirmacion")
    catalogo = await _catalogo(db)

    q = (select(LubeResultado.muestra_id, LubeResultado.parametro_id,
                LubeResultado.valor)
         .join(LubeMuestra, LubeMuestra.id == LubeResultado.muestra_id)
         .join(LubeCompartimento,
               LubeCompartimento.id == LubeMuestra.compartimento_id)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .join(LubeTipoCompartimento,
               LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
         .where(and_(LubeMuestra.fecha_toma >= desde,
                     LubeMuestra.estado != "ANULADA",
                     LubeResultado.valor.isnot(None))))
    q = f.aplicar(q)
    # `familia` es el parámetro con el que llamaba la versión anterior de la
    # pantalla. Se conserva y equivale a filtrar por línea: quitarlo rompería
    # cualquier enlace guardado.
    if familia:
        q = q.where(EAMActivo.linea == familia)

    por_muestra: Dict[int, Dict[int, float]] = defaultdict(dict)
    for muestra_id, pid, valor in (await db.execute(q)).all():
        por_muestra[muestra_id][pid] = float(valor)

    if len(por_muestra) < minimo_muestras:
        return {"familia": familia, "muestras": len(por_muestra),
                "suficiente": False,
                "motivo": f"Hacen falta al menos {minimo_muestras} muestras para "
                          f"que una correlación signifique algo; hay "
                          f"{len(por_muestra)}.",
                "parametros": [], "matriz": [], "cadena": []}

    # Solo los parámetros numéricos con presencia suficiente: uno medido en tres
    # muestras produce coeficientes altísimos por casualidad.
    presencia: Dict[int, int] = defaultdict(int)
    for valores in por_muestra.values():
        for pid in valores:
            presencia[pid] += 1
    utiles = [pid for pid, n in presencia.items()
              if n >= minimo_muestras and pid in catalogo
              and not catalogo[pid].es_texto]
    utiles.sort(key=lambda pid: ORDEN_SIGLAS.index(catalogo[pid].codigo)
                if catalogo[pid].codigo in ORDEN_SIGLAS else 999)

    matriz: List[List[Optional[float]]] = []
    conteos: List[List[int]] = []
    for a in utiles:
        fila_r, fila_n = [], []
        for b in utiles:
            xs, ys = [], []
            for valores in por_muestra.values():
                if a in valores and b in valores:
                    xs.append(valores[a])
                    ys.append(valores[b])
            fila_r.append(1.0 if a == b else pearson(xs, ys))
            fila_n.append(len(xs))
        matriz.append(fila_r)
        conteos.append(fila_n)

    indice = {catalogo[pid].codigo: i for i, pid in enumerate(utiles)}

    # La cadena declarada, contrastada con lo medido. Es la parte que convierte
    # la matriz en una conclusión: «esto es lo que dice la literatura, y esto es
    # lo que dicen los datos de esta flota».
    #
    # CADA MEDIDA LLEVA EL SIGNO QUE SE ESPERABA
    # Un eslabón con `efecto_inverso` predice correlación negativa. Se guarda
    # `esperado` en la medida y `concuerda` dice si el signo salió como debía:
    # sin eso, una viscosidad que sube con el combustible —físicamente
    # imposible— se contaría como confirmación del mecanismo.
    cadena: List[Dict[str, Any]] = []
    for eslabon in CADENA_CAUSAL:
        medidas = []
        for causa in eslabon["causa"]:
            for efecto, esperado in ([(e, 1) for e in eslabon.get("efecto", [])]
                                     + [(e, -1) for e in
                                        eslabon.get("efecto_inverso", [])]):
                if efecto.startswith("__"):
                    continue
                i, j = indice.get(causa), indice.get(efecto)
                if i is None or j is None:
                    continue
                r = matriz[i][j]
                medidas.append({
                    "causa": causa, "efecto": efecto,
                    "r": r, "n": conteos[i][j],
                    "esperado": "POSITIVO" if esperado > 0 else "NEGATIVO",
                    "concuerda": (None if r is None
                                  else (r * esperado) >= umbral),
                })
        # Se promedia la correlación ORIENTADA —multiplicada por el signo
        # esperado— y no la cruda. Así un eslabón mixto no se autocancela: un
        # +0,8 esperado positivo y un −0,8 esperado negativo son dos
        # confirmaciones, y promediarlos en crudo daría cero.
        orientadas = [m["r"] * (1 if m["esperado"] == "POSITIVO" else -1)
                      for m in medidas if m["r"] is not None]
        media = round(sum(orientadas) / len(orientadas), 3) if orientadas else None
        cadena.append({
            **eslabon,
            "medidas": medidas,
            "correlacion_media": media,
            # `correlacion_cruda` es la media sin orientar. Se manda para que
            # la pantalla pueda mostrar el número que se vería en una matriz
            # normal y no parezca que se cambió el dato.
            "correlacion_cruda": (round(sum(m["r"] for m in medidas
                                            if m["r"] is not None)
                                        / len(orientadas), 3)
                                  if orientadas else None),
            "se_confirma": media is not None and media >= umbral,
            "contradice": media is not None and media <= -umbral,
        })

    return {
        "familia": familia,
        "filtro": f.como_dict(),
        "muestras": len(por_muestra),
        "suficiente": True,
        "metodo": "Coeficiente de correlación de Pearson. Solo se emparejan "
                  "muestras donde ambos parámetros están medidos.",
        "umbral_confirmacion": umbral,
        "parametros": [{"codigo": catalogo[pid].codigo,
                        "nombre": catalogo[pid].nombre,
                        "sigla": SIGLA.get(catalogo[pid].codigo, catalogo[pid].codigo),
                        "grupo": catalogo[pid].grupo,
                        "unidad": catalogo[pid].unidad}
                       for pid in utiles],
        "matriz": matriz,
        "conteos": conteos,
        "cadena": cadena,
        "fuentes": FUENTES,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. Extensión de vida del aceite
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/extension")
async def extension(
    dias: int = Query(1460, ge=180, le=3650),
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Si se puede estirar el intervalo de cambio, y qué lo impide.

    LA REGLA QUE GOBIERNA ESTA PANTALLA
    Se puede extender cuando el aceite llega al cambio con reserva —TBN sano,
    viscosidad en rango, sin contaminación— y NO se puede cuando algo lo está
    degradando antes de tiempo. Por eso la respuesta separa las familias en dos
    listas y dice, para las que no, cuál es el impedimento concreto.

    Extender sobre un motor que entra glicol no ahorra: adelanta una reparación.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    catalogo = await _catalogo(db)
    por_codigo = {p.codigo: p.id for p in catalogo.values()}

    filas = (await db.execute(_base_muestras(f, desde))).all()
    if not filas:
        return {"filtro": f.como_dict(), "familias": [], "muestras": 0}

    ids = [m.id for m, _, _, _ in filas]
    valores: Dict[int, Dict[int, float]] = defaultdict(dict)
    estados: Dict[int, Dict[int, str]] = defaultdict(dict)
    for r in (await db.execute(
        select(LubeResultado).where(LubeResultado.muestra_id.in_(ids))
    )).scalars().all():
        if r.valor is not None:
            valores[r.muestra_id][r.parametro_id] = float(r.valor)
        estados[r.muestra_id][r.parametro_id] = r.estado or "NORMAL"

    IMPEDIMENTOS = [
        ("glicol", "Entrada de glicol", "Hay refrigerante llegando al aceite. "
         "Extender sobre esto adelanta una reparación de motor."),
        ("agua", "Agua en el aceite", "El agua degrada la carga y arrastra los "
         "aditivos; el intervalo actual ya le queda largo."),
        ("si", "Entrada de polvo", "El silicio abrasivo desgasta más rápido "
         "cuanto más tiempo circule."),
        ("combustible", "Dilución por combustible", "El aceite diluido protege "
         "menos aunque el resto de la muestra salga bien."),
        ("nitracion", "Nitración alta", "El aceite se está envejeciendo antes de "
         "tiempo por gases de combustión."),
        ("oxidacion", "Oxidación alta", "El aceite ya perdió capacidad "
         "dispersante."),
    ]

    por_familia: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"muestras": 0, "tbn": [], "viscosidad": [], "vida": [],
                 "impedimentos": defaultdict(int), "compartimentos": set()})

    for muestra, comp, activo, _tipo in filas:
        familia = activo.linea or activo.marca or "Sin clasificar"
        acum = por_familia[familia]
        acum["muestras"] += 1
        acum["compartimentos"].add(comp.id)
        v = valores.get(muestra.id, {})
        e = estados.get(muestra.id, {})

        for clave, lista in (("tbn", "tbn"), ("viscosidad", "viscosidad")):
            pid = por_codigo.get(clave)
            if pid and pid in v:
                acum[lista].append(v[pid])
        if muestra.horas_aceite:
            acum["vida"].append(float(muestra.horas_aceite))

        for codigo, etiqueta, _ in IMPEDIMENTOS:
            pid = por_codigo.get(codigo)
            if pid and e.get(pid) in ("MARGINAL", "CRITICO"):
                acum["impedimentos"][etiqueta] += 1

    salida = []
    for familia, acum in por_familia.items():
        tbn = acum["tbn"]
        visc = acum["viscosidad"]
        # El TBN al final del intervalo es lo que dice si sobró reserva. Se toma
        # el promedio de los más bajos —el cuartil inferior— y no la media de
        # todos: extender con base en el promedio deja fuera justo a los motores
        # que ya llegaban justos.
        tbn_ordenado = sorted(tbn)
        n = max(1, len(tbn_ordenado) // 4)
        tbn_bajo = sum(tbn_ordenado[:n]) / n if tbn_ordenado else None

        impedimentos = [
            {"impedimento": etiqueta, "muestras": veces,
             "pct": round(100 * veces / acum["muestras"], 1),
             "porque": next(p for c, e_, p in IMPEDIMENTOS if e_ == etiqueta)}
            for etiqueta, veces in sorted(acum["impedimentos"].items(),
                                          key=lambda x: -x[1])
            # Un caso aislado no bloquea a la familia entera: bloquea a ese
            # motor. Se exige que afecte al menos a uno de cada diez.
            if veces / acum["muestras"] >= 0.10
        ]

        salida.append({
            "familia": familia,
            "muestras": acum["muestras"],
            "equipos": len(acum["compartimentos"]),
            "tbn_promedio": round(sum(tbn) / len(tbn), 2) if tbn else None,
            "tbn_cuartil_bajo": round(tbn_bajo, 2) if tbn_bajo else None,
            "viscosidad_promedio": round(sum(visc) / len(visc), 2) if visc else None,
            "vida_promedio": round(sum(acum["vida"]) / len(acum["vida"]), 0) if acum["vida"] else None,
            "impedimentos": impedimentos,
            # Se puede evaluar la extensión cuando no hay impedimento extendido y
            # el TBN de los peores casos todavía guarda reserva. El umbral de 4
            # es la práctica común para diésel: por debajo, el aceite ya no
            # neutraliza los ácidos de la combustión.
            "puede_evaluarse": (not impedimentos and tbn_bajo is not None
                                and tbn_bajo >= 4.0),
            # NO MEDIDO NO ES LO MISMO QUE BAJO.
            # Decir «TBN por debajo de 4» cuando el TBN nunca se midió es
            # inventar un resultado. Lo que corresponde es pedir la medición:
            # sin ella la pregunta de extender no se puede ni plantear.
            "motivo": (
                f"{len(impedimentos)} condición(es) están degradando la carga "
                f"antes de tiempo." if impedimentos
                else "No se está midiendo el TBN en esta familia. Sin la reserva "
                     "alcalina al final del intervalo no hay con qué decidir si "
                     "se puede extender." if tbn_bajo is None
                else "Sin impedimentos y con reserva alcalina al final del "
                     "intervalo." if tbn_bajo >= 4.0
                else f"El TBN de los peores casos llega a {round(tbn_bajo, 2)} al "
                     f"final del intervalo. Por debajo de 4 el aceite ya no "
                     f"neutraliza los ácidos de la combustión: no hay reserva "
                     f"que estirar."),
        })

    salida.sort(key=lambda x: (not x["puede_evaluarse"], -x["muestras"]))
    return {"filtro": f.como_dict(), "familias": salida,
            "muestras": len(filas)}


# ══════════════════════════════════════════════════════════════════════════════
# 6. La cadena, para consultarla sin datos
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/cadena-causal")
async def cadena_causal(db: AsyncSession = Depends(get_db)):
    """La cadena causa-efecto y las reglas, tal cual, sin cruzarlas con datos.

    Está aparte para poder consultarlas al leer una muestra concreta —«¿por qué
    subiría el boro?»— sin tener que cargar la matriz de correlación entera.
    """
    criterio = await _criterio(db)
    return {
        "eslabones": CADENA_CAUSAL,
        # Las reglas VIGENTES, con los ajustes de la empresa: si acá se
        # listaran las de referencia, la consulta diría una cosa y el
        # evaluador aplicaría otra.
        "reglas": [{k: v for k, v in r.items()
                    if k not in ("exige", "tambien", "prohibe")}
                   for r in criterio.reglas()],
        "fuentes": FUENTES,
        "nota": "Los mecanismos vienen de la literatura de análisis de aceite "
                "en motor diésel, no de la observación de una flota concreta. "
                "Que la correlación medida los confirme o no en esta flota es "
                "una comprobación, no la fuente: un mecanismo físico no deja "
                "de existir porque unos datos no lo muestren, y una "
                "correlación alta no lo crea.",
    }
