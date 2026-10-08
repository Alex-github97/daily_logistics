"""
Cargue masivo de muestras de aceite desde Excel.

Va aparte de `eam_importar.py` —el cargue de catálogos— porque una muestra no es
una fila de catálogo: cuelga de un compartimento que hay que resolver por el
código del activo, trae una columna por cada parámetro del laboratorio (y esos
los define cada empresa, no el código) y al guardarse se evalúa contra los
límites. Nada de eso cabe en un importador genérico de una sola tabla.

Se hereda el criterio del otro, que es el que hace usable un cargue:
**no se detiene en el primer error** —un archivo de doscientas muestras con dos
malas carga las 198 y dice qué pasó con las otras dos— y es **idempotente**: la
muestra que ya existe se omite en vez de duplicarse, así que corregir el archivo
y volverlo a subir es seguro.

EL ORDEN IMPORTA, Y POR ESO VA EN DOS FASES
Primero se insertan todas las muestras del archivo y solo después se evalúan.
La evaluación compara contra la muestra anterior de la misma carga para sacar la
tasa de cambio; si se insertara y evaluara de una en una, una muestra que va
antes en el archivo pero después en el tiempo se evaluaría sin su predecesora
—la que venía más abajo en el Excel— y su tasa de cambio saldría vacía. Con las
dos fases, el orden de las filas deja de importar.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.eam import EAMActivo
from app.infrastructure.models.lubricacion import (
    LubeCarga, LubeCompartimento, LubeLaboratorio, LubeMetodoMuestreo,
    LubeMuestra, LubeParametro, LubeResultado,
)
from app.api.v1.endpoints.lubricacion_operacion import evaluar_muestra, _quien

router = APIRouter(prefix="/eam/lube/importar", tags=["CMMS/EAM · Lubricación"])

# Tope por archivo, y bastante más bajo que el de los catálogos: cada muestra se
# evalúa contra sus límites y contra su muestra anterior, y eso son varias
# consultas por fila. Mil muestras son un año de historia de una flota mediana;
# más que eso casi siempre es un error de pegado.
MAX_FILAS = 1000

# El prefijo de las columnas de parámetros. Sin él, un laboratorio que llame
# «numero» a un parámetro pisaría la columna del número de muestra.
PREFIJO_PARAMETRO = "p_"


class ColumnaPlantilla(BaseModel):
    clave: str
    titulo: str
    requerida: bool = False
    ayuda: Optional[str] = None
    ejemplo: Optional[str] = None


class DefinicionImportacion(BaseModel):
    ruta: str
    titulo: str
    columnas: List[ColumnaPlantilla]


class FilaConError(BaseModel):
    # Número de fila tal como lo ve quien abre el Excel: la 1 es el encabezado.
    fila: int
    motivo: str


class ResultadoImportacion(BaseModel):
    creados: int = 0
    omitidos: int = 0
    errores: List[FilaConError] = []
    total: int = 0


class Cargue(BaseModel):
    filas: List[Dict[str, Any]]


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSIONES
# ══════════════════════════════════════════════════════════════════════════════

# Origen del calendario de Excel. No es 1900-01-01: Excel arrastra desde Lotus
# el error de creer que 1900 fue bisiesto, y el desfase se corrige contando
# desde el 30 de diciembre de 1899.
ORIGEN_EXCEL = datetime(1899, 12, 30)

FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y")

# Hora por omisión cuando la celda trae solo la fecha, y es la misma que pone el
# formulario de una muestra suelta. No es cosmético: la muestra anterior se
# busca ordenando por `fecha_toma`, así que dos muestras del mismo día —una
# escrita a mano y otra importada— se ordenarían por la hora que cada vía
# inventó, y la tasa de cambio se calcularía contra la muestra equivocada.
HORA_POR_OMISION = 8


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _numero(valor: Any) -> float:
    """Un número escrito como lo escribe la gente.

    Se acepta la coma decimal y el punto de miles porque en un Excel llenado en
    Colombia «1.234,5» y «1234.5» son el mismo dato, y rechazar el primero
    obligaría a reformatear el archivo a mano.
    """
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    t = _texto(valor).replace(" ", "")
    if not t:
        raise ValueError("vacío")
    if "," in t and "." in t:
        # El separador decimal es el último que aparece; el otro es de miles.
        t = t.replace(".", "") if t.rindex(",") > t.rindex(".") else t.replace(",", "")
    t = t.replace(",", ".")
    return float(t)


def _fecha(valor: Any) -> datetime:
    """La fecha de la celda, venga como venga.

    El navegador lee la hoja sin convertir fechas, así que una celda con formato
    de fecha llega como el número de serie de Excel —45900, no «2026-08-30»—.
    Hay que aceptar las dos formas, o el cargue falla justo con los archivos
    bien hechos.
    """
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        d = ORIGEN_EXCEL + timedelta(days=float(valor))
        # Serie entera: la celda tenía fecha y no hora.
        return d if float(valor) % 1 else d.replace(hour=HORA_POR_OMISION)
    t = _texto(valor)
    if not t:
        raise ValueError("vacío")
    # Con hora explícita, tal como la manda el formulario de una muestra suelta.
    try:
        d = datetime.fromisoformat(t.replace("Z", ""))
        return d if len(t) > 10 else d.replace(hour=HORA_POR_OMISION)
    except ValueError:
        pass
    for f in FORMATOS_FECHA:
        try:
            return datetime.strptime(t[:10], f).replace(hour=HORA_POR_OMISION)
        except ValueError:
            continue
    raise ValueError(f"«{t}» no es una fecha")


def _clave(texto: Any) -> str:
    """Para comparar nombres escritos a mano: sin mayúsculas ni espacios de más."""
    return _texto(texto).lower()


# ══════════════════════════════════════════════════════════════════════════════
# LA PLANTILLA
# ══════════════════════════════════════════════════════════════════════════════

def _columnas_fijas() -> List[ColumnaPlantilla]:
    return [
        ColumnaPlantilla(
            clave="activo", titulo="Activo", requerida=True, ejemplo="MTC-001",
            ayuda="Código del activo, tal como aparece en Activos. No el nombre.",
        ),
        ColumnaPlantilla(
            clave="compartimento", titulo="Compartimento", requerida=True, ejemplo="HID",
            ayuda="Código del compartimento (MOT, HID, DIF-POST) o su nombre completo. "
                  "Tiene que ser uno de los compartimentos de ese activo.",
        ),
        ColumnaPlantilla(
            clave="numero", titulo="N.º de muestra", requerida=True, ejemplo="L-2026-0455",
            ayuda="El número del boletín del laboratorio. Es único: si ya está cargado, "
                  "la fila se omite en vez de duplicarse.",
        ),
        ColumnaPlantilla(
            clave="fecha_toma", titulo="Fecha de toma", requerida=True, ejemplo="2026-08-30",
            ayuda="Cuándo se tomó la muestra, no cuándo llegó el resultado. Sirve una "
                  "celda con formato de fecha o el texto AAAA-MM-DD.",
        ),
        ColumnaPlantilla(
            clave="medidor", titulo="Lectura del equipo", ejemplo="4820",
            ayuda="Horómetro u odómetro al momento de la toma. De acá sale la vida del "
                  "aceite; sin este dato la muestra queda sin horas.",
        ),
        ColumnaPlantilla(
            clave="laboratorio", titulo="Laboratorio",
            ayuda="Nombre del laboratorio, como está en la configuración de lubricación.",
        ),
        ColumnaPlantilla(
            clave="metodo", titulo="Método de toma",
            ayuda="Nombre del método, como está en la configuración de lubricación. "
                  "Importa: un método no recomendado cambia cómo se lee el resultado. "
                  "Si se deja vacío, queda el del compartimento.",
        ),
        ColumnaPlantilla(
            clave="observaciones", titulo="Observaciones",
            ayuda="Lo que no cabe en ninguna columna.",
        ),
    ]


@router.get("/muestras/plantilla", response_model=DefinicionImportacion)
async def plantilla_muestras(db: AsyncSession = Depends(get_db)):
    """Las columnas del cargue, para que el navegador arme el Excel.

    Las de parámetros salen de la base y no de una lista fija: qué mide el
    laboratorio lo define cada empresa en la configuración, y una plantilla con
    columnas que nadie llena —o sin la que sí se mide— es peor que no tenerla.
    """
    r = await db.execute(
        select(LubeParametro).where(LubeParametro.activo.is_(True))
        .order_by(LubeParametro.orden, LubeParametro.nombre))

    columnas = _columnas_fijas()
    for p in r.scalars().all():
        titulo = f"{p.nombre} ({p.unidad})" if p.unidad else p.nombre
        ayuda = p.origen_probable or ""
        if p.es_texto:
            ayuda = (ayuda + " · Va como texto, no como número.").strip(" ·")
        columnas.append(ColumnaPlantilla(
            clave=f"{PREFIJO_PARAMETRO}{p.codigo}", titulo=titulo, ayuda=ayuda or None))

    return DefinicionImportacion(
        ruta="muestras", titulo="Muestras de aceite", columnas=columnas)


# ══════════════════════════════════════════════════════════════════════════════
# LA IMPORTACIÓN
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/muestras", response_model=ResultadoImportacion)
async def importar_muestras(cargue: Cargue, db: AsyncSession = Depends(get_db),
                            usuario: Usuario = Depends(get_current_user)):
    if not cargue.filas:
        raise HTTPException(400, "El archivo no trae ninguna fila con datos")
    if len(cargue.filas) > MAX_FILAS:
        raise HTTPException(
            400,
            f"El archivo trae {len(cargue.filas)} filas y el máximo son {MAX_FILAS}. "
            "Divídalo en varios archivos.",
        )

    # Todo lo que hay que resolver, en unas pocas consultas y no en varias por
    # fila: con mil filas, resolver activo y compartimento fila por fila son
    # dos mil viajes a la base para un dato que no cambia durante el cargue.
    r = await db.execute(select(EAMActivo.id, EAMActivo.codigo))
    activos = {_clave(cod): aid for aid, cod in r.all() if cod}

    r = await db.execute(select(LubeCompartimento))
    compartimentos = list(r.scalars().all())
    # Por activo, y aceptando código o nombre: quien llena el Excel escribe el
    # que tiene a mano. El código gana si los dos coinciden.
    por_activo: Dict[int, Dict[str, LubeCompartimento]] = {}
    for c in compartimentos:
        d = por_activo.setdefault(c.activo_id, {})
        d.setdefault(_clave(c.nombre), c)
        d[_clave(c.codigo)] = c

    r = await db.execute(select(LubeLaboratorio.id, LubeLaboratorio.nombre))
    laboratorios = {_clave(n): i for i, n in r.all() if n}

    r = await db.execute(select(LubeMetodoMuestreo.id, LubeMetodoMuestreo.nombre))
    metodos = {_clave(n): i for i, n in r.all() if n}

    r = await db.execute(select(LubeParametro).where(LubeParametro.activo.is_(True)))
    parametros = {_clave(p.codigo): p for p in r.scalars().all()}

    # La carga viva de cada compartimento: a ella se cuelga la muestra, y de su
    # medidor de arranque salen las horas del aceite.
    r = await db.execute(select(LubeCarga).where(LubeCarga.estado == "ACTIVA"))
    carga_viva = {c.compartimento_id: c for c in r.scalars().all()}

    r = await db.execute(select(func.lower(LubeMuestra.numero)))
    existentes = {n for (n,) in r.all() if n}

    resultado = ResultadoImportacion(total=len(cargue.filas))
    # (muestra, resultados) de cada fila válida. Se insertan todas antes de
    # evaluar ninguna; el motivo está en el encabezado del módulo.
    pendientes: List[Tuple[LubeMuestra, List[Dict[str, Any]]]] = []

    for i, cruda in enumerate(cargue.filas):
        # +2: la fila 1 del Excel es el encabezado y el índice empieza en 0.
        numero_fila = i + 2

        def error(motivo: str, fila: int = numero_fila) -> None:
            resultado.errores.append(FilaConError(fila=fila, motivo=motivo))

        numero = _texto(cruda.get("numero"))
        if not numero:
            error("Falta el N.º de muestra")
            continue
        # Idempotencia: el número ya cargado —o repetido dentro del archivo— se
        # omite en vez de duplicarse.
        if _clave(numero) in existentes:
            resultado.omitidos += 1
            continue

        codigo_activo = _texto(cruda.get("activo"))
        if not codigo_activo:
            error("Falta el Activo")
            continue
        activo_id = activos.get(_clave(codigo_activo))
        if activo_id is None:
            error(f"No hay ningún activo con el código «{codigo_activo}»")
            continue

        nombre_comp = _texto(cruda.get("compartimento"))
        if not nombre_comp:
            error("Falta el Compartimento")
            continue
        comp = por_activo.get(activo_id, {}).get(_clave(nombre_comp))
        if comp is None:
            disponibles = ", ".join(sorted({
                c.codigo for c in compartimentos if c.activo_id == activo_id})) or "ninguno"
            error(f"El activo {codigo_activo} no tiene el compartimento «{nombre_comp}». "
                  f"Tiene: {disponibles}")
            continue

        try:
            fecha_toma = _fecha(cruda.get("fecha_toma"))
        except ValueError as e:
            error("Falta la Fecha de toma" if str(e) == "vacío" else f"Fecha de toma: {e}")
            continue

        medidor = None
        crudo_medidor = _texto(cruda.get("medidor"))
        if crudo_medidor:
            try:
                medidor = _numero(crudo_medidor)
            except ValueError:
                error(f"«{crudo_medidor}» no es un número válido en Lectura del equipo")
                continue

        laboratorio_id = None
        crudo_lab = _texto(cruda.get("laboratorio"))
        if crudo_lab:
            laboratorio_id = laboratorios.get(_clave(crudo_lab))
            if laboratorio_id is None:
                error(f"No hay un laboratorio llamado «{crudo_lab}». Créelo en la "
                      "configuración de lubricación o deje la celda vacía.")
                continue

        # Si no dicen el método, queda el que tiene definido el compartimento:
        # es el que se usa siempre en ese punto de muestreo.
        metodo_id = comp.metodo_muestreo_id
        crudo_metodo = _texto(cruda.get("metodo"))
        if crudo_metodo:
            metodo_id = metodos.get(_clave(crudo_metodo))
            if metodo_id is None:
                error(f"No hay un método de toma llamado «{crudo_metodo}». Créelo en la "
                      "configuración de lubricación o deje la celda vacía.")
                continue

        # Los resultados del laboratorio: una columna por parámetro.
        filas_resultado: List[Dict[str, Any]] = []
        problema = None
        for columna, valor in cruda.items():
            if not columna.startswith(PREFIJO_PARAMETRO):
                continue
            if not _texto(valor):
                continue
            p = parametros.get(_clave(columna[len(PREFIJO_PARAMETRO):]))
            # Un parámetro que ya no está en el catálogo se ignora en silencio:
            # es una columna sobrante de una plantilla vieja, no un error de
            # quien llenó el archivo.
            if p is None:
                continue
            if p.es_texto:
                filas_resultado.append(
                    {"parametro_id": p.id, "valor": None, "valor_texto": _texto(valor)})
                continue
            try:
                filas_resultado.append(
                    {"parametro_id": p.id, "valor": _numero(valor), "valor_texto": None})
            except ValueError:
                unidad = f" ({p.unidad})" if p.unidad else ""
                problema = f"«{_texto(valor)}» no es un número válido en {p.nombre}{unidad}"
                break
        if problema:
            error(problema)
            continue

        carga = carga_viva.get(comp.id)
        horas = None
        if carga and carga.medidor_inicio is not None and medidor is not None:
            horas = round(medidor - carga.medidor_inicio, 2)

        existentes.add(_clave(numero))
        pendientes.append((
            LubeMuestra(
                numero=numero, compartimento_id=comp.id,
                carga_id=carga.id if carga else None,
                fecha_toma=fecha_toma, medidor_equipo=medidor, horas_aceite=horas,
                laboratorio_id=laboratorio_id, metodo_id=metodo_id,
                observaciones=_texto(cruda.get("observaciones")) or None,
                registrado_por=_quien(usuario),
                estado="CON_RESULTADO" if filas_resultado else "TOMADA",
            ),
            filas_resultado,
        ))

    if not pendientes:
        return resultado

    # ── Fase 1: todas las muestras del archivo, y sus resultados ──────────────
    db.add_all([m for m, _ in pendientes])
    await db.commit()

    for muestra, filas_resultado in pendientes:
        await db.refresh(muestra)
        for fila in filas_resultado:
            db.add(LubeResultado(muestra_id=muestra.id, **fila))
    await db.commit()

    # ── Fase 2: la evaluación, con todo el archivo ya en la base ──────────────
    # Una muestra sin resultados queda en TOMADA y no se evalúa: no hay contra
    # qué, y evaluarla la dejaría marcada NORMAL sin haber medido nada.
    for muestra, filas_resultado in pendientes:
        if filas_resultado:
            await evaluar_muestra(db, muestra)

    resultado.creados = len(pendientes)
    return resultado
