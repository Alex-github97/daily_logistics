"""
Cargue masivo de los catálogos propios del CMMS.

El Excel se lee en el navegador y aquí llegan filas ya estructuradas: así no hay
que subir archivos ni manejar temporales, y este lado se dedica a lo que
importa, que es validar.

Criterio de la importación: **no se detiene en el primer error**. Un archivo de
trescientas filas con dos malas debe cargar las 298 buenas y decir exactamente
qué pasó con las otras dos; abortar todo obligaría a corregir a ciegas.

Y es **idempotente**: lo que ya existe se omite en vez de duplicarse, para que
volver a subir el mismo archivo corregido no deje el catálogo con todo repetido.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.infrastructure.models.eam import (
    EAMActividad, EAMRepuesto, EAMFallaCatalogo, EAMCausaCatalogo,
    EAMSolucionCatalogo, EAMTipoActivo, EAMMarcaActivo, EAMLineaActivo,
    EAMModeloActivo, EAMMotorActivo, EAMTipoCombustible, EAMTipoTrabajo,
    EAMCentroCosto,
)

router = APIRouter(prefix="/eam", tags=["CMMS/EAM"])

# Tope por archivo. Un Excel de más de esto casi siempre es un error de pegado,
# y una petición con cien mil filas tumba la memoria del proceso.
MAX_FILAS = 5000


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


def _col(clave, titulo, requerida=False, ayuda=None, ejemplo=None):
    return ColumnaPlantilla(clave=clave, titulo=titulo, requerida=requerida,
                            ayuda=ayuda, ejemplo=ejemplo)


# Qué columnas admite cada catálogo, de dónde salen la plantilla y la validación.
# `clave_unica` es el campo por el que se decide si una fila ya existe.
CATALOGOS: Dict[str, Dict[str, Any]] = {
    "actividades": {
        "modelo": EAMActividad, "titulo": "Actividades", "clave_unica": "nombre",
        "columnas": [
            _col("nombre", "Nombre", True, "El trabajo tal como aparecerá en la OT",
                 "Cambio de aceite de motor"),
            _col("descripcion", "Descripción", False, ejemplo="Incluye filtro y revisión de fugas"),
        ],
    },
    "repuestos": {
        "modelo": EAMRepuesto, "titulo": "Repuestos", "clave_unica": "codigo",
        "columnas": [
            _col("codigo", "Código", True, "Identificador único del repuesto", "REP-0001"),
            _col("nombre", "Nombre", True, ejemplo="Filtro de aceite"),
            _col("descripcion", "Descripción"),
            _col("categoria", "Categoría", ejemplo="Filtros"),
            _col("unidad_medida", "Unidad de medida", ejemplo="UNIDAD"),
            _col("costo_unitario", "Costo unitario",
                 ayuda="Escriba el número sin separadores de miles: 45000, no 45.000",
                 ejemplo="45000"),
            _col("stock_minimo", "Stock mínimo", ejemplo="5"),
            _col("stock_actual", "Stock actual", ejemplo="20"),
            _col("proveedor_ppal", "Proveedor principal", ejemplo="Distribuidora XYZ"),
        ],
    },
    "fallas": {
        "modelo": EAMFallaCatalogo, "titulo": "Fallas", "clave_unica": "descripcion",
        "columnas": [
            _col("descripcion", "Descripción", True, "Qué se dañó", "Fuga de aceite por retén"),
            _col("codigo", "Código", ejemplo="F-001"),
            _col("tipo_activo", "Tipo de activo", ayuda="A qué tipo de activo aplica",
                 ejemplo="VEHICULO"),
        ],
    },
    "causas": {
        "modelo": EAMCausaCatalogo, "titulo": "Causas", "clave_unica": "descripcion",
        "columnas": [
            _col("descripcion", "Descripción", True, "Por qué se dañó",
                 "Desgaste normal por uso"),
        ],
    },
    "soluciones": {
        "modelo": EAMSolucionCatalogo, "titulo": "Soluciones", "clave_unica": "descripcion",
        "columnas": [
            _col("descripcion", "Descripción", True, "Qué se hizo", "Cambio de retén y sellos"),
        ],
    },
    "tipos-trabajo": {
        "modelo": EAMTipoTrabajo, "titulo": "Tipos de trabajo", "clave_unica": "nombre",
        "columnas": [
            _col("nombre", "Nombre", True, ejemplo="Mantenimiento Preventivo"),
            _col("categoria", "Categoría", False,
                 "PREVENTIVO, CORRECTIVO, PREDICTIVO, INSPECCION o EMERGENCIA",
                 "PREVENTIVO"),
            _col("duracion", "Duración", False,
                 "Texto libre: admite «Variable» además de horas", "4h"),
            _col("requiere_taller", "Requiere taller", False, "Sí o No", "No"),
            _col("requiere_materiales", "Requiere repuestos", False, "Sí o No", "Sí"),
            _col("sistema", "Sistema", ejemplo="Motor"),
            _col("subsistema", "Subsistema", ejemplo="Lubricación"),
        ],
    },
    "centros-costo": {
        "modelo": EAMCentroCosto, "titulo": "Centros de costo", "clave_unica": "codigo",
        "columnas": [
            _col("codigo", "Código", True, ejemplo="CC-001"),
            _col("nombre", "Nombre", True, ejemplo="Flota Bogotá"),
            _col("ciudad", "Ciudad", ejemplo="Bogotá"),
            _col("plataforma", "Plataforma", ejemplo="Plataforma Central"),
        ],
    },
    "tipos-activo": {
        "modelo": EAMTipoActivo, "titulo": "Tipos de activo", "clave_unica": "codigo",
        "columnas": [
            _col("codigo", "Código", True, "Se usa internamente; sin espacios", "VEHICULO"),
            _col("nombre", "Nombre", True, ejemplo="Vehículo"),
            _col("usa_llantas", "Usa llantas", False,
                 "Sí solo si a ese tipo se le montan llantas", "Sí"),
        ],
    },
    "motores": {
        "modelo": EAMMotorActivo, "titulo": "Motores", "clave_unica": "nombre",
        "columnas": [
            _col("nombre", "Motor", True, ejemplo="Cummins ISL9"),
            _col("marca", "Marca", ejemplo="Cummins"),
            _col("cilindraje_cc", "Cilindraje (cc)",
                 ayuda="Sin separadores de miles: 8900, no 8.900", ejemplo="8900"),
            _col("potencia_hp", "Potencia (HP)", ejemplo="380"),
        ],
    },
    "combustibles": {
        "modelo": EAMTipoCombustible, "titulo": "Combustibles", "clave_unica": "nombre",
        "columnas": [_col("nombre", "Nombre", True, ejemplo="Diésel")],
    },
    "marcas": {
        "modelo": EAMMarcaActivo, "titulo": "Marcas", "clave_unica": "nombre",
        "columnas": [
            _col("nombre", "Marca", True, ejemplo="Freightliner"),
            _col("tipo_activo", "Tipo de activo", True,
                 "Debe existir ya en Tipos de activo. Escriba su código o su nombre.",
                 "VEHICULO"),
        ],
        "resolver": "marca",
    },
    "lineas": {
        "modelo": EAMLineaActivo, "titulo": "Líneas", "clave_unica": "nombre",
        "columnas": [
            _col("nombre", "Línea", True, ejemplo="Cascadia"),
            _col("marca", "Marca", True,
                 "Debe existir ya en Marcas. Cárguelas primero.", "Freightliner"),
        ],
        "resolver": "linea",
    },
    "modelos": {
        "modelo": EAMModeloActivo, "titulo": "Modelos", "clave_unica": "nombre",
        "columnas": [
            _col("nombre", "Modelo", True, ejemplo="Cascadia 126"),
            _col("marca", "Marca", True, "Sirve para saber a qué línea pertenece",
                 "Freightliner"),
            _col("linea", "Línea", True, "Debe existir ya en Líneas de esa marca",
                 "Cascadia"),
            _col("anio_desde", "Año desde", ejemplo="2018"),
        ],
        "resolver": "modelo",
    },
}

NUMERICAS = {
    "costo_unitario": float, "stock_minimo": int, "stock_actual": int,
    "cilindraje_cc": float, "potencia_hp": float, "anio_desde": int,
}

# Los campos de sí/no: quien llena un Excel escribe de todo.
BOOLEANAS = {"usa_llantas", "requiere_taller", "requiere_materiales"}
AFIRMATIVOS = {"si", "sí", "s", "true", "verdadero", "x", "1", "yes"}


def _numero(valor: Any) -> float:
    """Interpreta un número escrito a la colombiana: punto de miles, coma decimal.

    Si la celda ya viene como número —lo normal cuando Excel la tiene
    formateada— se usa tal cual. El problema son las celdas de texto: "45.000"
    son cuarenta y cinco mil, no cuarenta y cinco, y "12500,50" son doce mil
    quinientos con cincuenta, no un millón doscientos cincuenta mil.

    Queda un caso genuinamente ambiguo: un punto seguido de exactamente tres
    dígitos y sin coma. "45.000" puede ser 45000 (miles) o 45.0 (decimal). Se
    resuelve como miles porque es la convención local, y por eso la plantilla
    pide escribir los números sin separadores.
    """
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)

    texto = str(valor).strip()
    for basura in ("$", " ", " ", "COP", "cop"):
        texto = texto.replace(basura, "")
    if not texto:
        raise ValueError("vacío")

    tiene_punto, tiene_coma = "." in texto, "," in texto
    if tiene_punto and tiene_coma:
        # El separador decimal es el último que aparece; el otro es de miles.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif tiene_coma:
        # Una sola coma con uno o dos dígitos detrás es decimal; si no, miles.
        entero, _, resto = texto.rpartition(",")
        if texto.count(",") == 1 and 1 <= len(resto) <= 2:
            texto = entero + "." + resto
        else:
            texto = texto.replace(",", "")
    elif tiene_punto:
        entero, _, resto = texto.rpartition(".")
        # Tres dígitos detrás del punto: separador de miles, no decimal.
        if texto.count(".") > 1 or len(resto) == 3:
            texto = texto.replace(".", "")
    return float(texto)


async def _mapa_padres(db: AsyncSession, resolver: str) -> Dict[str, Any]:
    """Índices para resolver por nombre lo que en la tabla es un id.

    Se arma antes del bucle y no dentro: consultando por fila, un archivo de
    trescientas líneas dispararía trescientas consultas.
    """
    if resolver == "marca":
        # La marca guarda el CÓDIGO del tipo, no su id. Se admite escribir
        # cualquiera de los dos, porque en pantalla se ve el nombre.
        r = await db.execute(select(EAMTipoActivo))
        indice: Dict[str, Any] = {}
        for tipo in r.scalars().all():
            indice[str(tipo.codigo).strip().lower()] = tipo.codigo
            indice[str(tipo.nombre).strip().lower()] = tipo.codigo
        return indice

    if resolver == "linea":
        r = await db.execute(select(EAMMarcaActivo))
        return {m.nombre.strip().lower(): m.id for m in r.scalars().all()}

    if resolver == "modelo":
        # La línea se busca por (marca, línea): el mismo nombre de línea puede
        # existir en dos marcas distintas.
        r = await db.execute(
            select(EAMLineaActivo, EAMMarcaActivo)
            .join(EAMMarcaActivo, EAMMarcaActivo.id == EAMLineaActivo.marca_id))
        return {
            (marca.nombre.strip().lower(), linea.nombre.strip().lower()): linea.id
            for linea, marca in r.all()
        }
    return {}


def _resolver_fila(resolver: str, fila: Dict[str, Any], padres: Dict[str, Any]):
    """Devuelve (campos_extra, error). El error ya viene redactado para el usuario."""
    if resolver == "marca":
        escrito = str(fila.get("tipo_activo") or "").strip()
        if not escrito:
            return None, "Falta el tipo de activo"
        codigo = padres.get(escrito.lower())
        if codigo is None:
            return None, f"No existe «{escrito}» en Tipos de activo. Cárguelo primero."
        return {"tipo_activo": codigo}, None

    if resolver == "linea":
        escrito = str(fila.get("marca") or "").strip()
        if not escrito:
            return None, "Falta la marca"
        marca_id = padres.get(escrito.lower())
        if marca_id is None:
            return None, f"No existe la marca «{escrito}». Cárguela primero."
        return {"marca_id": marca_id}, None

    if resolver == "modelo":
        marca = str(fila.get("marca") or "").strip()
        linea = str(fila.get("linea") or "").strip()
        if not marca or not linea:
            return None, "Faltan la marca o la línea"
        linea_id = padres.get((marca.lower(), linea.lower()))
        if linea_id is None:
            return None, f"No existe la línea «{linea}» en la marca «{marca}». Cárguela primero."
        return {"linea_id": linea_id}, None

    return {}, None


def _booleano(valor: Any) -> bool:
    """Sí/No escrito de las mil formas en que la gente lo escribe."""
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in AFIRMATIVOS


class FilaConError(BaseModel):
    # Número de fila del Excel tal como lo ve el usuario: la 1 es el encabezado.
    fila: int
    motivo: str


class ResultadoImportacion(BaseModel):
    creados: int = 0
    omitidos: int = 0
    errores: List[FilaConError] = []
    total: int = 0


class Cargue(BaseModel):
    filas: List[Dict[str, Any]]


@router.get("/catalogos/{ruta}/plantilla", response_model=DefinicionImportacion)
async def definicion_plantilla(ruta: str):
    """Las columnas del catálogo, para que el navegador arme la plantilla."""
    if ruta not in CATALOGOS:
        raise HTTPException(404, f"No hay un catálogo «{ruta}» que se pueda importar")
    d = CATALOGOS[ruta]
    return DefinicionImportacion(ruta=ruta, titulo=d["titulo"], columnas=d["columnas"])


@router.post("/catalogos/{ruta}/importar", response_model=ResultadoImportacion)
async def importar(ruta: str, cargue: Cargue, db: AsyncSession = Depends(get_db)):
    if ruta not in CATALOGOS:
        raise HTTPException(404, f"No hay un catálogo «{ruta}» que se pueda importar")
    if len(cargue.filas) > MAX_FILAS:
        raise HTTPException(
            400,
            f"El archivo trae {len(cargue.filas)} filas y el máximo son {MAX_FILAS}. "
            "Divídalo en varios archivos.",
        )

    d = CATALOGOS[ruta]
    modelo, clave = d["modelo"], d["clave_unica"]
    resolver = d.get("resolver")
    padres = await _mapa_padres(db, resolver) if resolver else {}
    # Las columnas que solo sirven para encontrar el padre no son campos del
    # modelo: se usan y se descartan.
    auxiliares = {"marca", "linea"} if resolver in ("linea", "modelo") else set()
    requeridas = [c.clave for c in d["columnas"] if c.requerida]
    admitidas = {c.clave for c in d["columnas"]}

    # Lo que ya está, para no duplicarlo. Se compara sin distinguir mayúsculas
    # ni espacios sobrantes: "Filtro de aceite" y "filtro de aceite " son lo
    # mismo para quien llena un Excel.
    #
    # En los jerárquicos la unicidad es POR PADRE y no global: "Cascadia" puede
    # ser una línea de Freightliner y también de otra marca, y compararlo contra
    # todo el catálogo rechazaría filas legítimas.
    campo_padre = {"marca": "tipo_activo", "linea": "marca_id",
                   "modelo": "linea_id"}.get(resolver)
    existentes = set()
    if campo_padre:
        r = await db.execute(select(getattr(modelo, clave), getattr(modelo, campo_padre)))
        for valor, padre in r.all():
            if valor is not None:
                existentes.add((padre, str(valor).strip().lower()))
    else:
        r = await db.execute(select(getattr(modelo, clave)))
        for (valor,) in r.all():
            if valor is not None:
                existentes.add(str(valor).strip().lower())

    resultado = ResultadoImportacion(total=len(cargue.filas))
    nuevos = []

    for i, cruda in enumerate(cargue.filas):
        # +2: la fila 1 del Excel es el encabezado y el índice empieza en 0.
        numero = i + 2
        fila = {k: v for k, v in cruda.items() if k in admitidas}

        faltantes = [
            c for c in requeridas
            if fila.get(c) is None or str(fila.get(c)).strip() == ""
        ]
        if faltantes:
            titulos = ", ".join(
                next(c.titulo for c in d["columnas"] if c.clave == f) for f in faltantes)
            resultado.errores.append(FilaConError(fila=numero, motivo=f"Falta {titulos}"))
            continue

        extra: Dict[str, Any] = {}
        if resolver:
            extra, error = _resolver_fila(resolver, fila, padres)
            if error:
                resultado.errores.append(FilaConError(fila=numero, motivo=error))
                continue

        nombre_fila = str(fila.get(clave, "")).strip().lower()
        valor_clave = (extra.get(campo_padre), nombre_fila) if campo_padre else nombre_fila
        if valor_clave in existentes:
            resultado.omitidos += 1
            continue

        limpio: Dict[str, Any] = {}
        problema = None
        for k, v in fila.items():
            if v is None or str(v).strip() == "":
                continue
            if k in auxiliares:
                continue
            if k in BOOLEANAS:
                limpio[k] = _booleano(v)
            elif k in NUMERICAS:
                try:
                    limpio[k] = NUMERICAS[k](_numero(v))
                except (TypeError, ValueError):
                    titulo = next(c.titulo for c in d["columnas"] if c.clave == k)
                    problema = f"«{v}» no es un número válido en {titulo}"
                    break
            else:
                limpio[k] = str(v).strip()
        if problema:
            resultado.errores.append(FilaConError(fila=numero, motivo=problema))
            continue

        limpio.update(extra)

        # Dos filas iguales dentro del mismo archivo: la segunda se omite.
        existentes.add(valor_clave)
        nuevos.append(modelo(**limpio))

    if nuevos:
        db.add_all(nuevos)
        await db.commit()
        resultado.creados = len(nuevos)

    return resultado
