"""
Lubricación — la flota como eje del análisis.

QUÉ RESUELVE ESTE ARCHIVO
Todo lo anterior respondía «qué le pasa a esta muestra». Acá la pregunta es
«qué le pasa a este segmento de la flota»: los Cascadia con motor DD15, los
tractocamiones de una línea, una placa concreta. Es la pregunta con la que se
decide un intervalo de cambio o un cambio de proveedor de aceite, y no se
puede responder muestra por muestra.

EL EJE ES EL KILOMETRAJE, NO LA FECHA
Un vehículo parado tres meses no envejece su aceite. Dos muestras con la misma
fecha y con 8.000 km de diferencia no son comparables, y un informe que grafique
contra el calendario mezcla las dos. Por eso todas las series de acá van contra
`medidor_equipo` —la lectura del odómetro al tomar la muestra— y no contra
`fecha_toma`. Es la misma razón por la que ASTM D7669 pide normalizar la
tendencia por unidad de vida del aceite.

LA CORRELACIÓN ES DE PEARSON, Y SE DICE
Se calcula con `normas_lubricacion.pearson`, que devuelve `None` cuando no hay
con qué —menos de cuatro puntos, o una serie constante— en vez de un cero que
se leería como «no hay relación». Cada coeficiente viaja con su `n`: un 0,99
sobre cuatro puntos no dice nada, y sin la cantidad de muestras eso no se ve.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.normas_lubricacion import (
    BANDA_SAE_100C, CONSTANTES, Criterio, DESVIO_VISCOSIDAD, FUENTES,
    GRUPO_DESGASTE, LIMITES_HIDRAULICO, LIMITES_MOTOR, MINIMO_POBLACION_D7720,
    NATURALEZA, PERCENTIL_CONDENA, PERCENTIL_PRECAUCION, REGLAS,
    limites_estadisticos, pearson, regresion,
)
from app.infrastructure.models.eam import EAMActivo
from app.infrastructure.models.lubricacion import (
    LubeAjusteNorma, LubeCarga, LubeCompartimento, LubeDiagnostico,
    LubeMotivoDrenaje, LubeMuestra, LubeParametro, LubeRelleno, LubeResultado,
    LubeTipoCompartimento,
)

router = APIRouter(prefix="/eam/lube/interpretacion",
                   tags=["CMMS/EAM · Lubricación · Interpretación"])


# ══════════════════════════════════════════════════════════════════════════════
# El filtro de flota
#
# Marca, línea, modelo, tipo y motor son TEXTO en `eam_activo`, no llaves
# foráneas. Es la convención que ya usan el tablero de causa raíz y la
# analítica de lubricación, y hay que respetarla: si este informe filtrara por
# otro camino, sus cifras no se podrían comparar con las de aquellos y habría
# dos verdades para la misma pregunta.
# ══════════════════════════════════════════════════════════════════════════════

class FiltroFlota:
    """Los criterios de segmentación, como dependencia de FastAPI.

    Va como clase y no como seis parámetros repetidos en cada endpoint porque
    son seis, aparecen en cinco endpoints, y cada vez que se agregara uno
    habría que acordarse de los cinco sitios.
    """

    def __init__(
        self,
        marca: Optional[str] = Query(None, description="Marca del vehículo"),
        linea: Optional[str] = Query(None, description="Línea del vehículo"),
        modelo: Optional[str] = Query(None, description="Modelo del vehículo"),
        tipo: Optional[str] = Query(None, description="Tipo de activo"),
        motor: Optional[str] = Query(None, description="Motor: «marca · línea»"),
        placa: Optional[str] = Query(None, description="Código o placa del activo"),
        compartimento: Optional[str] = Query(
            None, description="Código del tipo de compartimento: MOT, HID…"),
    ):
        self.marca = marca or None
        self.linea = linea or None
        self.modelo = modelo or None
        self.tipo = tipo or None
        self.motor = motor or None
        self.placa = placa or None
        self.compartimento = compartimento or None

    @property
    def activo(self) -> bool:
        """¿Hay algún criterio puesto? Sirve para rotular la pantalla."""
        return any([self.marca, self.linea, self.modelo, self.tipo,
                    self.motor, self.placa, self.compartimento])

    def aplicar(self, q: Select) -> Select:
        """Añade los criterios a una consulta que ya tenga `EAMActivo` unido."""
        if self.marca:
            q = q.where(EAMActivo.marca == self.marca)
        if self.linea:
            q = q.where(EAMActivo.linea == self.linea)
        if self.modelo:
            q = q.where(EAMActivo.modelo == self.modelo)
        if self.tipo:
            q = q.where(EAMActivo.tipo_activo == self.tipo)
        if self.placa:
            # El activo se identifica por código, y la placa es un campo
            # aparte que puede estar vacío. Se acepta cualquiera de los dos
            # porque quien escribe en el filtro no sabe cuál guardó el sistema.
            q = q.where((EAMActivo.codigo == self.placa)
                        | (EAMActivo.placa == self.placa))
        if self.motor:
            # El motor se identifica por «marca · línea» en un solo valor:
            # separarlo en dos selectores obligaría a escoger la marca del
            # motor antes de ver las opciones, y nadie recuerda que el DD15 es
            # Detroit.
            marca, _, linea = self.motor.partition(" · ")
            q = q.where(EAMActivo.motor_marca == marca.strip())
            if linea.strip():
                q = q.where(EAMActivo.motor_linea == linea.strip())
        if self.compartimento:
            q = q.where(LubeTipoCompartimento.codigo == self.compartimento)
        return q

    def como_dict(self) -> Dict[str, Optional[str]]:
        return {"marca": self.marca, "linea": self.linea, "modelo": self.modelo,
                "tipo": self.tipo, "motor": self.motor, "placa": self.placa,
                "compartimento": self.compartimento}


def _base_muestras(f: FiltroFlota, desde: Optional[datetime] = None) -> Select:
    """Las muestras válidas del segmento, con la jerarquía del activo unida.

    `LubeTipoCompartimento` entra siempre en el JOIN aunque no se filtre por
    él: el filtro por familia de compartimento lo necesita, y montar dos
    consultas distintas según el filtro es la manera de que una de las dos se
    quede sin arreglar.
    """
    q = (select(LubeMuestra, LubeCompartimento, EAMActivo, LubeTipoCompartimento)
         .join(LubeCompartimento,
               LubeCompartimento.id == LubeMuestra.compartimento_id)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .join(LubeTipoCompartimento,
               LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
         .where(LubeMuestra.estado != "ANULADA"))
    if desde is not None:
        q = q.where(LubeMuestra.fecha_toma >= desde)
    return f.aplicar(q)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Las opciones de los filtros
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/filtros")
async def filtros(db: AsyncSession = Depends(get_db)):
    """Qué se puede escoger, y solo lo que tiene muestras.

    POR QUÉ SOLO LO QUE TIENE MUESTRAS
    Un selector que ofrece treinta marcas de las cuales cuatro tienen análisis
    hace que el usuario escoja una de las veintiséis vacías y concluya que la
    pantalla está rota. Se listan las opciones con su conteo de muestras, y las
    que no tienen no aparecen.

    Cada opción viaja con su padre —la línea sabe de qué marca es— para que el
    frontend pueda encadenar los selectores sin volver a preguntar.
    """
    filas = (await db.execute(
        select(EAMActivo.tipo_activo, EAMActivo.marca, EAMActivo.linea,
               EAMActivo.modelo, EAMActivo.motor_marca, EAMActivo.motor_linea,
               EAMActivo.codigo, EAMActivo.placa, EAMActivo.nombre,
               func.count(LubeMuestra.id))
        .join(LubeCompartimento, LubeCompartimento.activo_id == EAMActivo.id)
        .join(LubeMuestra, LubeMuestra.compartimento_id == LubeCompartimento.id)
        .where(LubeMuestra.estado != "ANULADA")
        .group_by(EAMActivo.tipo_activo, EAMActivo.marca, EAMActivo.linea,
                  EAMActivo.modelo, EAMActivo.motor_marca,
                  EAMActivo.motor_linea, EAMActivo.codigo, EAMActivo.placa,
                  EAMActivo.nombre)
    )).all()

    tipos: Dict[str, int] = defaultdict(int)
    marcas: Dict[str, int] = defaultdict(int)
    lineas: Dict[tuple, int] = defaultdict(int)
    modelos: Dict[tuple, int] = defaultdict(int)
    motores: Dict[tuple, int] = defaultdict(int)
    placas: List[Dict[str, Any]] = []

    for (tipo, marca, linea, modelo, mot_marca, mot_linea,
         codigo, placa, nombre, n) in filas:
        if tipo:
            tipos[tipo] += n
        if marca:
            marcas[marca] += n
            if linea:
                lineas[(linea, marca)] += n
                if modelo:
                    modelos[(modelo, linea)] += n
        if mot_marca:
            etiqueta = f"{mot_marca} · {mot_linea}" if mot_linea else mot_marca
            motores[(etiqueta, marca or "")] += n
        placas.append({"valor": codigo, "etiqueta": codigo,
                       "detalle": f"{nombre}"[:60],
                       "placa": placa, "marca": marca, "linea": linea,
                       "modelo": modelo, "muestras": n})

    def _lista(d: Dict[Any, int], con_padre: bool = False):
        salida = []
        for clave, n in d.items():
            if con_padre:
                valor, padre = clave
                salida.append({"valor": valor, "etiqueta": valor,
                               "padre": padre or None, "muestras": n})
            else:
                salida.append({"valor": clave, "etiqueta": clave,
                               "padre": None, "muestras": n})
        salida.sort(key=lambda x: (-x["muestras"], x["etiqueta"]))
        return salida

    comps = (await db.execute(
        select(LubeTipoCompartimento.codigo, LubeTipoCompartimento.nombre,
               func.count(LubeMuestra.id))
        .join(LubeCompartimento,
              LubeCompartimento.tipo_compartimento_id == LubeTipoCompartimento.id)
        .join(LubeMuestra, LubeMuestra.compartimento_id == LubeCompartimento.id)
        .where(LubeMuestra.estado != "ANULADA")
        .group_by(LubeTipoCompartimento.codigo, LubeTipoCompartimento.nombre)
    )).all()

    placas.sort(key=lambda x: x["etiqueta"])
    return {
        "tipos": _lista(tipos),
        "marcas": _lista(marcas),
        "lineas": _lista(lineas, con_padre=True),
        "modelos": _lista(modelos, con_padre=True),
        "motores": _lista(motores, con_padre=True),
        "compartimentos": [{"valor": c, "etiqueta": n, "padre": None,
                            "muestras": k} for c, n, k in comps
                           if c and c != "GRA"],
        "placas": placas,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. El tablero del programa
#
# Mudado desde la pantalla de operación de lubricación. Allá estaba fuera de
# lugar: aquella pantalla es para registrar cargas y muestras, y un tablero
# entre las pestañas de registro obliga a irse del trabajo para consultar y a
# volver. Acá vive con el resto del análisis y hereda el filtro de flota, que
# es lo que le faltaba: «parámetros que más disparan» sin poder acotar a una
# familia de motores no permite actuar sobre nada.
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/programa")
async def programa(
    dias: int = Query(365, ge=30, le=3650),
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Cómo va el programa en el segmento filtrado.

    SIN TOPE EN LA LISTA DE PARÁMETROS
    La versión anterior mostraba los doce que más disparan. Doce es suficiente
    para la foto general y es exactamente lo que estorba cuando se busca un
    parámetro concreto: el que se quiere revisar es, casi siempre, uno que no
    está entre los doce primeros. Acá va la lista completa de todo lo que se
    disparó alguna vez, y la pantalla la muestra en un cuadro del mismo tamaño
    con desplazamiento.
    """
    desde = datetime.utcnow() - timedelta(days=dias)

    filas = (await db.execute(_base_muestras(f, desde))).all()
    ids = [m.id for m, _, _, _ in filas]
    total = len(filas)

    por_severidad: Dict[str, int] = defaultdict(int)
    for m, _c, _a, _t in filas:
        por_severidad[m.severidad or "PENDIENTE"] += 1

    # ── Parámetros que disparan, completos y con su código ───────────────────
    # El código viaja porque la pantalla lo necesita para pedir la correlación
    # de ese parámetro al hacer clic. Sin él habría que adivinarlo del nombre.
    parametros: List[Dict[str, Any]] = []
    if ids:
        r = await db.execute(
            select(LubeParametro.codigo, LubeParametro.nombre,
                   LubeParametro.grupo, LubeParametro.unidad,
                   LubeParametro.origen_probable,
                   func.count(LubeResultado.id),
                   func.sum(case((LubeResultado.estado == "CRITICO", 1), else_=0)),
                   func.count(func.distinct(LubeMuestra.compartimento_id)))
            .join(LubeResultado, LubeResultado.parametro_id == LubeParametro.id)
            .join(LubeMuestra, LubeMuestra.id == LubeResultado.muestra_id)
            .where(and_(LubeResultado.estado.in_(("MARGINAL", "CRITICO")),
                        LubeResultado.muestra_id.in_(ids)))
            .group_by(LubeParametro.codigo, LubeParametro.nombre,
                      LubeParametro.grupo, LubeParametro.unidad,
                      LubeParametro.origen_probable)
            .order_by(func.count(LubeResultado.id).desc()))
        parametros = [{
            "codigo": cod, "etiqueta": nom, "grupo": gr, "unidad": un,
            "origen": org, "cantidad": c, "criticas": int(k or 0),
            "equipos": eq,
        } for cod, nom, gr, un, org, c, k, eq in r.all()]

    # ── Motivos de drenaje del segmento ──────────────────────────────────────
    q = (select(LubeMotivoDrenaje.nombre, LubeMotivoDrenaje.categoria,
                LubeMotivoDrenaje.evitable, func.count(LubeCarga.id),
                func.avg(LubeCarga.vida_lograda))
         .join(LubeCarga, LubeCarga.motivo_drenaje_id == LubeMotivoDrenaje.id)
         .join(LubeCompartimento,
               LubeCompartimento.id == LubeCarga.compartimento_id)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .join(LubeTipoCompartimento,
               LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
         .where(and_(LubeCarga.estado == "DRENADA",
                     LubeCarga.fecha_drenaje >= desde))
         .group_by(LubeMotivoDrenaje.nombre, LubeMotivoDrenaje.categoria,
                   LubeMotivoDrenaje.evitable)
         .order_by(func.count(LubeCarga.id).desc()))
    drenajes = [{"etiqueta": n, "categoria": cat, "evitable": bool(ev),
                 "cantidad": c, "vida_promedio": round(float(v), 1) if v else None}
                for n, cat, ev, c, v in (await db.execute(f.aplicar(q))).all()]

    # ── Costo por unidad de vida ─────────────────────────────────────────────
    # El aceite de reposición entra en la cuenta: en un equipo con fuga puede
    # ser el grueso del gasto, y dejarlo fuera daría un costo por hora más bajo
    # que el de la ficha de cada carga.
    rellenos = (select(LubeRelleno.carga_id.label("carga_id"),
                       func.sum(func.coalesce(LubeRelleno.costo, 0)).label("costo"))
                .group_by(LubeRelleno.carga_id).subquery())
    q = (select(LubeTipoCompartimento.nombre, LubeTipoCompartimento.unidad_vida,
                func.count(LubeCarga.id),
                func.sum(func.coalesce(LubeCarga.costo_aceite, 0)
                         + func.coalesce(LubeCarga.costo_filtro, 0)
                         + func.coalesce(LubeCarga.costo_mano_obra, 0)
                         + func.coalesce(rellenos.c.costo, 0)),
                func.sum(LubeCarga.vida_lograda))
         .join(LubeCompartimento,
               LubeCompartimento.tipo_compartimento_id == LubeTipoCompartimento.id)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .join(LubeCarga, LubeCarga.compartimento_id == LubeCompartimento.id)
         .outerjoin(rellenos, rellenos.c.carga_id == LubeCarga.id)
         .where(and_(LubeCarga.estado == "DRENADA",
                     LubeCarga.fecha_drenaje >= desde))
         .group_by(LubeTipoCompartimento.nombre,
                   LubeTipoCompartimento.unidad_vida))
    costos = []
    for nombre, unidad, n, costo, vida in (await db.execute(f.aplicar(q))).all():
        costo, vida = float(costo or 0), float(vida or 0)
        costos.append({"etiqueta": nombre, "unidad": unidad, "cargas": n,
                       "costo_total": round(costo, 2), "vida_total": round(vida, 1),
                       "costo_por_unidad": round(costo / vida, 2) if vida else None})

    # ── Por marca y por línea dentro del segmento ────────────────────────────
    async def _por(campo):
        """Muestras y críticas agrupadas por un atributo del activo.

        Devuelve también los equipos distintos: «45 muestras» no dice si son
        quince camiones con tres muestras cada uno o tres con quince, y esa
        diferencia decide si la cifra representa a la flota o a tres equipos.

        LOS QUE NO TIENEN EL DATO SE CUENTAN APARTE, NO SE ESCONDEN
        Un activo sin motor registrado no pertenece a ningún grupo de motor,
        pero sus muestras existen. Si se descartaran en silencio, la suma de
        los grupos no cuadraría con el total del tablero y nadie sabría por
        qué. Y una fila con la etiqueta en blanco —que es lo que salía— no
        sirve para nada: no se puede filtrar por ella ni se entiende qué es.
        """
        # `concat` de PostgreSQL ignora los NULL, así que un motor sin marca no
        # produce NULL sino cadena vacía y `isnot(None)` no lo atrapa. Hay que
        # descartar las dos cosas.
        vacio = or_(campo.is_(None), campo == "")
        base = (select(campo, func.count(LubeMuestra.id),
                       func.sum(case((LubeMuestra.severidad.in_(
                           ("CRITICO", "ACCION_INMEDIATA")), 1), else_=0)),
                       func.count(func.distinct(EAMActivo.id)))
                .join(LubeCompartimento,
                      LubeCompartimento.activo_id == EAMActivo.id)
                .join(LubeTipoCompartimento,
                      LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
                .join(LubeMuestra,
                      LubeMuestra.compartimento_id == LubeCompartimento.id)
                .where(and_(LubeMuestra.fecha_toma >= desde,
                            LubeMuestra.estado != "ANULADA")))

        grupos = [{"etiqueta": n, "cantidad": c, "criticas": int(k or 0),
                   "equipos": eq}
                  for n, c, k, eq in (await db.execute(f.aplicar(
                      base.where(~vacio).group_by(campo)
                      .order_by(func.count(LubeMuestra.id).desc())))).all()]

        sin_dato = (await db.execute(f.aplicar(
            base.where(vacio).group_by(campo)))).all()
        return {
            "grupos": grupos,
            "sin_dato": {"muestras": sum(x[1] for x in sin_dato),
                         "equipos": sum(x[3] for x in sin_dato)},
        }

    por_marca = await _por(EAMActivo.marca)
    por_linea = await _por(EAMActivo.linea)

    # El motor se agrupa por «marca · línea» en un solo valor, con el mismo
    # separador que usa el filtro. Es lo que permite que al hacer clic en
    # «Detroit · DD15» se pueda acotar el análisis a ese motor sin traducir
    # nada: la etiqueta que se ve ES el valor que entiende el filtro.
    _motor = func.concat(EAMActivo.motor_marca,
                         func.coalesce(" · " + EAMActivo.motor_linea, ""))
    por_motor = await _por(_motor)

    # ── Acierto del diagnóstico, solo del segmento ───────────────────────────
    # La versión anterior contaba los diagnósticos de toda la empresa y los
    # presentaba junto a cifras filtradas. Con un filtro puesto eso produce un
    # tablero donde una parte de los números habla de la flota entera: la
    # inconsistencia no se nota y desacredita el resto.
    verificacion: Dict[str, int] = {}
    if ids:
        verificacion = {v: c for v, c in (await db.execute(
            select(LubeDiagnostico.verificacion, func.count(LubeDiagnostico.id))
            .where(LubeDiagnostico.muestra_id.in_(ids))
            .group_by(LubeDiagnostico.verificacion))).all()}
    confirmados = verificacion.get("CONFIRMADO", 0)
    desmentidos = verificacion.get("DESMENTIDO", 0)
    acierto = (round(confirmados / (confirmados + desmentidos) * 100, 1)
               if (confirmados + desmentidos) else None)

    # ── Calidad del dato: compartimentos sin puerto de muestreo ──────────────
    q = (select(func.count(func.distinct(LubeCompartimento.id)))
         .select_from(LubeCompartimento)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .join(LubeTipoCompartimento,
               LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
         .where(and_(LubeCompartimento.activo.is_(True),
                     LubeTipoCompartimento.codigo != "GRA")))
    comps_total = (await db.execute(f.aplicar(q))).scalar() or 0
    sin_puerto = (await db.execute(f.aplicar(
        q.where(LubeCompartimento.tiene_puerto_muestreo.is_(False))))).scalar() or 0

    return {
        "filtro": f.como_dict(),
        "dias": dias,
        "total_muestras": total,
        "por_severidad": dict(por_severidad),
        "criticas": (por_severidad.get("CRITICO", 0)
                     + por_severidad.get("ACCION_INMEDIATA", 0)),
        "parametros": parametros,
        "drenajes": drenajes,
        "costos": costos,
        "por_marca": por_marca,
        "por_linea": por_linea,
        "por_motor": por_motor,
        "diagnostico": {"confirmados": confirmados, "desmentidos": desmentidos,
                        "pendientes": verificacion.get("PENDIENTE", 0),
                        "acierto_pct": acierto},
        "compartimentos": comps_total,
        "sin_puerto_muestreo": sin_puerto,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. La correlación de UN parámetro contra todos los demás
#
# Es lo que se abre al hacer clic en un parámetro del tablero. La matriz
# completa —que sigue existiendo en la pestaña de correlación— responde «qué se
# mueve con qué en general»; esto responde «este que me está disparando, con
# qué viene acompañado», que es la pregunta que se hace cuando ya se detectó
# algo y hay que decidir qué revisar.
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/correlacion-de/{codigo}")
async def correlacion_de(
    codigo: str,
    dias: int = Query(1460, ge=90, le=3650),
    minimo: int = Query(6, ge=4, le=200),
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Pearson de un parámetro contra el resto, ordenado por fuerza.

    Solo se emparejan muestras donde AMBOS parámetros están medidos. Rellenar
    el faltante con cero produciría correlaciones altísimas entre parámetros
    que simplemente se piden juntos en el mismo paquete de laboratorio.
    """
    catalogo = {p.codigo: p for p in (await db.execute(
        select(LubeParametro))).scalars().all()}
    objetivo = catalogo.get(codigo)
    if not objetivo:
        raise HTTPException(404, f"No existe el parámetro «{codigo}».")
    if objetivo.es_texto:
        raise HTTPException(
            400, f"«{objetivo.nombre}» no es numérico: el código ISO 4406 son "
                 f"tres números que solo tienen sentido juntos y no se "
                 f"correlaciona.")

    desde = datetime.utcnow() - timedelta(days=dias)
    q = (select(LubeResultado.muestra_id, LubeParametro.codigo,
                LubeResultado.valor)
         .join(LubeParametro, LubeParametro.id == LubeResultado.parametro_id)
         .join(LubeMuestra, LubeMuestra.id == LubeResultado.muestra_id)
         .join(LubeCompartimento,
               LubeCompartimento.id == LubeMuestra.compartimento_id)
         .join(EAMActivo, EAMActivo.id == LubeCompartimento.activo_id)
         .join(LubeTipoCompartimento,
               LubeTipoCompartimento.id == LubeCompartimento.tipo_compartimento_id)
         .where(and_(LubeMuestra.fecha_toma >= desde,
                     LubeMuestra.estado != "ANULADA",
                     LubeResultado.valor.isnot(None),
                     LubeParametro.es_texto.is_(False))))

    por_muestra: Dict[int, Dict[str, float]] = defaultdict(dict)
    for muestra_id, cod, valor in (await db.execute(f.aplicar(q))).all():
        por_muestra[muestra_id][cod] = float(valor)

    contra: List[Dict[str, Any]] = []
    for otro, p in catalogo.items():
        if otro == codigo or p.es_texto:
            continue
        xs, ys = [], []
        for valores in por_muestra.values():
            if codigo in valores and otro in valores:
                xs.append(valores[codigo])
                ys.append(valores[otro])
        if len(xs) < minimo:
            continue
        r = pearson(xs, ys)
        contra.append({
            "codigo": otro, "nombre": p.nombre, "grupo": p.grupo,
            "unidad": p.unidad, "origen_probable": p.origen_probable,
            "r": r, "n": len(xs),
        })

    # Por fuerza de la relación, sin importar el signo: una correlación
    # negativa fuerte —viscosidad contra combustible— es tan informativa como
    # una positiva, y ordenar por valor con signo la manda al final.
    contra.sort(key=lambda x: -abs(x["r"]) if x["r"] is not None else 1)

    return {
        "codigo": codigo,
        "nombre": objetivo.nombre,
        "unidad": objetivo.unidad,
        "grupo": objetivo.grupo,
        "origen_probable": objetivo.origen_probable,
        "filtro": f.como_dict(),
        "muestras": len(por_muestra),
        "metodo": "Coeficiente de correlación de Pearson sobre las muestras "
                  "donde ambos parámetros están medidos.",
        "contra": contra,
        "nota": "Que dos parámetros suban juntos no prueba que uno cause el "
                "otro: pueden tener los dos una tercera causa, o coincidir. "
                "El coeficiente sirve para orientar qué revisar, no para "
                "concluir.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. Evolución contra el kilometraje
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/evolucion")
async def evolucion(
    dias: int = Query(1460, ge=90, le=3650),
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Cómo se comporta cada muestra a lo largo del recorrido del vehículo.

    Una serie por placa, con el kilometraje en el eje y la severidad de cada
    muestra como color. Responde «cómo viene esta flota con el recorrido», que
    es distinto de «cómo viene con el tiempo»: un vehículo parado no envejece
    su aceite.

    Las muestras sin lectura de odómetro quedan fuera y se informa cuántas
    son. Ponerlas en cero las apilaría todas al comienzo del eje e inventaría
    una tendencia inicial que no existe.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    filas = (await db.execute(_base_muestras(f, desde)
                              .order_by(LubeMuestra.fecha_toma))).all()
    if not filas:
        return {"filtro": f.como_dict(), "placas": [], "muestras": 0,
                "sin_medidor": 0, "resumen": {}}

    ids = [m.id for m, _, _, _ in filas]
    # Cuántos parámetros fuera de rango tiene cada muestra: es el indicador
    # que hace legible la serie. Graficar treinta parámetros por placa produce
    # un plato de espagueti; graficar «cuántos hallazgos» produce una línea que
    # se entiende.
    hallazgos: Dict[int, Dict[str, int]] = defaultdict(
        lambda: {"marginal": 0, "critico": 0})
    for muestra_id, estado, n in (await db.execute(
        select(LubeResultado.muestra_id, LubeResultado.estado, func.count())
        .where(and_(LubeResultado.muestra_id.in_(ids),
                    LubeResultado.estado.in_(("MARGINAL", "CRITICO"))))
        .group_by(LubeResultado.muestra_id, LubeResultado.estado)
    )).all():
        hallazgos[muestra_id][str(estado).lower()] = n

    por_placa: Dict[str, Dict[str, Any]] = {}
    sin_medidor = 0
    resumen: Dict[str, int] = defaultdict(int)

    for muestra, comp, activo, tipo in filas:
        resumen[muestra.severidad or "PENDIENTE"] += 1
        if muestra.medidor_equipo is None:
            sin_medidor += 1
            continue
        clave = activo.codigo
        p = por_placa.setdefault(clave, {
            "placa": activo.codigo, "activo": activo.nombre,
            "marca": activo.marca, "linea": activo.linea,
            "modelo": activo.modelo,
            "motor": (f"{activo.motor_marca} · {activo.motor_linea}"
                      if activo.motor_marca and activo.motor_linea
                      else activo.motor_marca),
            "puntos": [],
        })
        h = hallazgos.get(muestra.id, {"marginal": 0, "critico": 0})
        p["puntos"].append({
            "km": round(float(muestra.medidor_equipo), 1),
            "fecha": muestra.fecha_toma,
            "numero": muestra.numero,
            "compartimento": comp.nombre,
            "tipo_compartimento": tipo.codigo,
            "severidad": muestra.severidad,
            "horas_aceite": muestra.horas_aceite,
            "hallazgos": h["marginal"] + h["critico"],
            "criticos": h["critico"],
            "muestra_id": muestra.id,
            "compartimento_id": comp.id,
        })

    placas = []
    for p in por_placa.values():
        p["puntos"].sort(key=lambda x: x["km"])
        kms = [x["km"] for x in p["puntos"]]
        malos = [float(x["hallazgos"]) for x in p["puntos"]]
        p["muestras"] = len(p["puntos"])
        p["km_min"], p["km_max"] = (min(kms), max(kms)) if kms else (None, None)
        # La pendiente de «hallazgos contra kilometraje» dice si el equipo se
        # está deteriorando con el recorrido o si se mantiene.
        p["tendencia"] = regresion(kms, malos)
        placas.append(p)
    placas.sort(key=lambda x: -x["muestras"])

    return {
        "filtro": f.como_dict(),
        "placas": placas,
        "muestras": len(filas),
        "sin_medidor": sin_medidor,
        "resumen": dict(resumen),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. Dispersión: cada parámetro contra el kilometraje
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/dispersion")
async def dispersion(
    dias: int = Query(1460, ge=90, le=3650),
    minimo: int = Query(6, ge=4, le=500),
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Un diagrama de dispersión por parámetro: valor contra kilometraje.

    PARA QUÉ SIRVE ESTA PANTALLA
    Para ver de un golpe qué le pasa al aceite con el recorrido en todas sus
    categorías a la vez. Los metales de desgaste deberían subir con el
    kilometraje —eso es normal—; el TBN debería bajar. Lo que interesa son los
    que NO se comportan así: un silicio que sube con el kilometraje delata una
    entrada de polvo que se abre con el uso, y un hierro plano en un motor con
    mucho recorrido suele significar que las muestras no se están tomando
    igual.

    Cada panel trae su recta de mínimos cuadrados, su r de Pearson y su
    pendiente por cada 1.000 km. La pendiente es la cifra con la que se decide
    un intervalo; el r dice si esa pendiente significa algo.
    """
    desde = datetime.utcnow() - timedelta(days=dias)
    filas = (await db.execute(_base_muestras(f, desde))).all()
    if not filas:
        return {"filtro": f.como_dict(), "parametros": [], "muestras": 0,
                "sin_medidor": 0}

    # El kilometraje de cada muestra. Sin él la muestra no entra: es el eje.
    km_de: Dict[int, float] = {}
    placa_de: Dict[int, str] = {}
    sin_medidor = 0
    for muestra, _comp, activo, _tipo in filas:
        if muestra.medidor_equipo is None:
            sin_medidor += 1
            continue
        km_de[muestra.id] = float(muestra.medidor_equipo)
        placa_de[muestra.id] = activo.codigo

    if not km_de:
        return {"filtro": f.como_dict(), "parametros": [],
                "muestras": len(filas), "sin_medidor": sin_medidor,
                "motivo": "Ninguna muestra del segmento tiene lectura de "
                          "odómetro. Sin ella no se puede graficar contra el "
                          "kilometraje."}

    catalogo = {p.id: p for p in (await db.execute(
        select(LubeParametro))).scalars().all()}

    puntos_de: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in (await db.execute(
        select(LubeResultado)
        .where(and_(LubeResultado.muestra_id.in_(list(km_de.keys())),
                    LubeResultado.valor.isnot(None)))
    )).scalars().all():
        p = catalogo.get(r.parametro_id)
        if not p or p.es_texto:
            continue
        puntos_de[r.parametro_id].append({
            "km": round(km_de[r.muestra_id], 1),
            "valor": float(r.valor),
            "estado": r.estado or "NORMAL",
            "placa": placa_de.get(r.muestra_id),
            "muestra_id": r.muestra_id,
        })

    # El orden de presentación: el grupo primero —desgaste, contaminación,
    # aditivo, propiedad— porque así se lee un boletín, y dentro de cada grupo
    # el que más se dispara. Alfabético pondría el aluminio antes del hierro y
    # nadie busca así.
    ORDEN_GRUPO = {"DESGASTE": 0, "CONTAMINACION": 1, "PROPIEDAD": 2,
                   "ADITIVO": 3}

    salida = []
    for pid, puntos in puntos_de.items():
        if len(puntos) < minimo:
            continue
        p = catalogo[pid]
        xs = [x["km"] for x in puntos]
        ys = [x["valor"] for x in puntos]
        fuera = sum(1 for x in puntos if x["estado"] in ("MARGINAL", "CRITICO"))
        salida.append({
            "codigo": p.codigo, "nombre": p.nombre, "unidad": p.unidad,
            "grupo": p.grupo, "origen_probable": p.origen_probable,
            "bidireccional": bool(p.bidireccional),
            "es_desgaste": p.codigo in GRUPO_DESGASTE,
            "puntos": sorted(puntos, key=lambda x: x["km"]),
            "fuera_de_rango": fuera,
            "regresion": regresion(xs, ys),
            "minimo": round(min(ys), 3), "maximo": round(max(ys), 3),
            "promedio": round(sum(ys) / len(ys), 3),
        })
    salida.sort(key=lambda x: (ORDEN_GRUPO.get(x["grupo"], 9),
                              -x["fuera_de_rango"]))

    return {
        "filtro": f.como_dict(),
        "parametros": salida,
        "muestras": len(km_de),
        "sin_medidor": sin_medidor,
        "nota": "La pendiente va por cada 1.000 km. Que un metal de desgaste "
                "suba con el recorrido es normal; lo que hay que mirar son "
                "los que no se comportan como deberían.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# `/normas` se fusionó con `/criterios`
#
# Servía los límites de referencia; `/criterios` sirve los VIGENTES, que son los
# de referencia con los ajustes de la empresa encima. Mantener los dos habría
# dejado un endpoint que dice lo que manda la norma y otro que dice lo que
# aplica el evaluador, y la pantalla acabaría leyendo el que no era.
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# 7. El criterio: consultarlo y ajustarlo
#
# Lo que la empresa cambia se guarda como DIFERENCIA contra lo publicado, no
# como una copia entera de la tabla de límites. Así un parámetro sin fila usa el
# valor de referencia, borrar la fila lo devuelve exactamente a como estaba, y
# cuando la referencia se actualice —porque salga una revisión de la norma— el
# cambio llega solo a lo que nadie tocó.
# ══════════════════════════════════════════════════════════════════════════════

AMBITOS = {"LIMITE", "MOTOR", "REGLA"}
SEVERIDADES = {"NORMAL", "MARGINAL", "CRITICO", "ACCION_INMEDIATA"}


async def _criterio(db: AsyncSession) -> Criterio:
    """El criterio vigente de esta empresa: referencia más sus ajustes."""
    # No hay filtro por «activo»: un ajuste que se retira se borra, no se
    # apaga. Una fila apagada con un motivo de hace dos años no informa nada y
    # obliga a filtrarla en todas las consultas.
    filas = (await db.execute(select(LubeAjusteNorma))).scalars().all()
    return Criterio([{
        "ambito": a.ambito, "clave": a.clave,
        "precaucion": a.precaucion, "condena": a.condena, "valor": a.valor,
        "activa": a.activa, "severidad": a.severidad, "urgencia": a.urgencia,
        "orden": a.orden, "lectura": a.lectura, "accion": a.accion,
        "motivo": a.motivo, "ajustado_por": a.ajustado_por,
    } for a in filas])


class AjusteLimite(BaseModel):
    """Un umbral de un parámetro en una familia de compartimento."""
    precaucion: Optional[float] = None
    condena: Optional[float] = None
    motivo: str = Field(min_length=8, max_length=2000)


class AjusteConstante(BaseModel):
    valor: float
    motivo: str = Field(min_length=8, max_length=2000)


class AjusteRegla(BaseModel):
    activa: Optional[bool] = None
    severidad: Optional[str] = None
    urgencia: Optional[int] = Field(default=None, ge=0, le=100)
    orden: Optional[int] = Field(default=None, ge=0, le=99)
    lectura: Optional[str] = Field(default=None, max_length=2000)
    accion: Optional[str] = Field(default=None, max_length=2000)
    motivo: str = Field(min_length=8, max_length=2000)


async def _guardar(db: AsyncSession, ambito: str, clave: str,
                   campos: Dict[str, Any], motivo: str,
                   quien: Optional[str]) -> LubeAjusteNorma:
    """Crea o actualiza el ajuste. Uno por (ámbito, clave)."""
    fila = (await db.execute(
        select(LubeAjusteNorma).where(and_(LubeAjusteNorma.ambito == ambito,
                                           LubeAjusteNorma.clave == clave))
    )).scalar_one_or_none()
    if fila is None:
        fila = LubeAjusteNorma(ambito=ambito, clave=clave, motivo=motivo)
        db.add(fila)
    for campo, valor in campos.items():
        setattr(fila, campo, valor)
    fila.motivo = motivo
    fila.ajustado_por = quien
    await db.commit()
    await db.refresh(fila)
    return fila


@router.get("/criterios")
async def criterios(
    dias: int = Query(1460, ge=90, le=3650),
    f: FiltroFlota = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """El criterio vigente completo, marcando qué está ajustado y qué no.

    Es la misma información que aplica el evaluador. Se sirve de un solo sitio a
    propósito: una pantalla de configuración que leyera de otro lado podría
    mostrar un criterio y el informe aplicar otro, y eso no se nota hasta que
    alguien discute una conclusión.
    """
    criterio = await _criterio(db)
    catalogo = {p.codigo: p for p in (await db.execute(
        select(LubeParametro))).scalars().all()}

    # Las familias de compartimento que esta empresa tiene de verdad. Ofrecer
    # las nueve del catálogo cuando solo se usan dos llena la pantalla de
    # criterios para equipos que no existen.
    # Ordenadas por cuántos compartimentos tiene cada una: la pantalla abre en
    # la primera, y abrir en la familia con cuatro equipos cuando la flota son
    # ciento treinta motores manda a corregir el criterio equivocado.
    familias = [{"codigo": c, "nombre": n, "compartimentos": k}
                for c, n, k in (await db.execute(
        select(LubeTipoCompartimento.codigo, LubeTipoCompartimento.nombre,
               func.count(LubeCompartimento.id))
        .join(LubeCompartimento,
              LubeCompartimento.tipo_compartimento_id == LubeTipoCompartimento.id)
        .where(LubeTipoCompartimento.codigo != "GRA")
        .group_by(LubeTipoCompartimento.codigo, LubeTipoCompartimento.nombre)
        .order_by(func.count(LubeCompartimento.id).desc())
    )).all() if c]
    if not familias:
        familias = [{"codigo": "MOT", "nombre": "Motor diésel",
                     "compartimentos": 0}]

    def _limites_de(familia: str):
        salida = []
        for codigo, l in criterio.limites(familia).items():
            p = catalogo.get(codigo)
            salida.append({
                **l, "codigo": codigo,
                "nombre": p.nombre if p else codigo,
                "unidad": p.unidad if p else None,
                "grupo": p.grupo if p else None,
            })
        return salida

    # ── Los límites estadísticos, que no se editan pero sí se explican ───────
    desde = datetime.utcnow() - timedelta(days=dias)
    filas = (await db.execute(_base_muestras(f, desde))).all()
    tipo_de_muestra = {m.id: (t.codigo or "SIN_TIPO") for m, _c, _a, t in filas}
    nombre_tipo = {(t.codigo or "SIN_TIPO"): t.nombre for _m, _c, _a, t in filas}
    catalogo_id = {p.id: p for p in (await db.execute(
        select(LubeParametro))).scalars().all()}

    poblaciones: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list))
    if tipo_de_muestra:
        for mid, pid, valor in (await db.execute(
            select(LubeResultado.muestra_id, LubeResultado.parametro_id,
                   LubeResultado.valor)
            .where(and_(LubeResultado.muestra_id.in_(list(tipo_de_muestra)),
                        LubeResultado.valor.isnot(None)))
        )).all():
            p = catalogo_id.get(pid)
            if p and p.codigo in GRUPO_DESGASTE:
                poblaciones[tipo_de_muestra[mid]][p.codigo].append(float(valor))

    minimo = int(criterio.constante("minimo_poblacion"))
    por_familia = []
    for tipo, pob in poblaciones.items():
        estadisticos = limites_estadisticos(pob, criterio)
        por_familia.append({
            "tipo": tipo, "nombre": nombre_tipo.get(tipo, tipo),
            "muestras": sum(1 for t in tipo_de_muestra.values() if t == tipo),
            "estadisticos": estadisticos,
            "insuficientes": [{"codigo": c, "n": len(v),
                               "faltan": minimo - len(v)}
                              for c, v in pob.items() if c not in estadisticos],
        })
    por_familia.sort(key=lambda x: -x["muestras"])

    return {
        "filtro": f.como_dict(),
        "fuentes": FUENTES,
        "naturaleza": NATURALEZA,
        "severidades": sorted(SEVERIDADES),
        "familias": familias,
        "limites": {fa["codigo"]: _limites_de(fa["codigo"]) for fa in familias},
        "constantes": criterio.constantes_vigentes(),
        "reglas": criterio.reglas_vigentes(),
        "por_familia": por_familia,
        "minimo_poblacion": minimo,
        "percentiles": {"precaucion": criterio.constante("percentil_precaucion"),
                        "condena": criterio.constante("percentil_condena")},
        "banda_sae": BANDA_SAE_100C,
        "hay_ajustes": criterio.hay_ajustes,
        "resumen_ajustes": criterio.resumen_ajustes(),
        "advertencia": "Las normas ASTM e ISO definen CÓMO SE MIDE, no cuándo "
                       "es malo. Cada límite lleva por separado el método del "
                       "ensayo y el origen del umbral, porque citar una norma "
                       "de ensayo como si fuera la fuente de un límite es una "
                       "cita falsa. Un umbral que esta empresa ajuste deja de "
                       "presentarse como referencia y pasa a decir que es de "
                       "la casa, con su motivo al lado.",
    }


@router.put("/criterios/limite/{familia}/{codigo}")
async def ajustar_limite(
    familia: str, codigo: str, datos: AjusteLimite,
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
):
    """Cambia el umbral de un parámetro para una familia de compartimento."""
    base = Criterio().limites(familia)
    if codigo not in base:
        raise HTTPException(
            404, f"«{codigo}» no tiene criterio de referencia en la familia "
                 f"«{familia}», así que no hay nada que ajustar.")
    if datos.precaucion is None and datos.condena is None:
        raise HTTPException(
            400, "No se indicó ningún umbral. Para volver al valor de "
                 "referencia hay que borrar el ajuste, no guardarlo vacío.")

    # La dirección del parámetro decide qué orden tiene sentido: en el TBN el
    # peligro es que BAJE, así que la condena va por debajo de la precaución.
    direccion = base[codigo].get("direccion", "ALTO")
    p, c = datos.precaucion, datos.condena
    if p is not None and c is not None:
        if direccion == "BAJO" and c > p:
            raise HTTPException(
                400, f"En «{codigo}» el peligro es que el valor BAJE: la "
                     f"condena ({c}) tiene que ser menor o igual que la "
                     f"precaución ({p}).")
        if direccion != "BAJO" and c < p:
            raise HTTPException(
                400, f"La condena ({c}) no puede ser menor que la precaución "
                     f"({p}): quedaría un umbral de alarma más exigente que el "
                     f"de condena y ninguna muestra caería en precaución.")

    fila = await _guardar(db, "LIMITE", f"{familia.upper()}:{codigo}",
                          {"precaucion": p, "condena": c},
                          datos.motivo, getattr(usuario, "username", None))
    return {"guardado": True, "ambito": "LIMITE", "clave": fila.clave,
            "referencia": {"precaucion": base[codigo].get("precaucion"),
                           "condena": base[codigo].get("condena")}}


@router.put("/criterios/constante/{clave}")
async def ajustar_constante(
    clave: str, datos: AjusteConstante,
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
):
    """Cambia una constante del motor de cálculo."""
    meta = CONSTANTES.get(clave)
    if not meta:
        raise HTTPException(404, f"No existe la constante «{clave}».")
    if not (meta["minimo"] <= datos.valor <= meta["maximo"]):
        raise HTTPException(
            400, f"«{meta['nombre']}» tiene que estar entre {meta['minimo']:g} "
                 f"y {meta['maximo']:g} {meta['unidad']}. Se recibió "
                 f"{datos.valor:g}.")

    # Los pares precaución/condena tienen que conservar su orden, o el escalón
    # entre «vigilar» y «actuar» desaparece sin que nadie lo note.
    criterio = await _criterio(db)
    PARES = [("percentil_precaucion", "percentil_condena"),
             ("salto_precaucion", "salto_condena"),
             ("desvio_viscosidad_precaucion", "desvio_viscosidad_condena")]
    for menor, mayor in PARES:
        if clave == menor and datos.valor >= criterio.constante(mayor):
            raise HTTPException(
                400, f"«{meta['nombre']}» ({datos.valor:g}) tiene que quedar "
                     f"por debajo de «{CONSTANTES[mayor]['nombre']}» "
                     f"({criterio.constante(mayor):g}).")
        if clave == mayor and datos.valor <= criterio.constante(menor):
            raise HTTPException(
                400, f"«{meta['nombre']}» ({datos.valor:g}) tiene que quedar "
                     f"por encima de «{CONSTANTES[menor]['nombre']}» "
                     f"({criterio.constante(menor):g}).")

    await _guardar(db, "MOTOR", clave, {"valor": datos.valor},
                   datos.motivo, getattr(usuario, "username", None))
    return {"guardado": True, "ambito": "MOTOR", "clave": clave,
            "referencia": meta["valor"]}


@router.put("/criterios/regla/{codigo}")
async def ajustar_regla(
    codigo: str, datos: AjusteRegla,
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
):
    """Apaga, reordena o reescribe una regla de diagnóstico.

    No se pueden crear reglas nuevas desde acá, y es a propósito: una regla no
    es solo un texto, es una condición sobre combinaciones de parámetros
    —«cobre fuera pero plomo y estaño dentro»— que hay que escribir en código
    para que el evaluador la entienda. Lo que sí se puede es apagar la que no
    aplique, cambiar su prioridad, y reescribir con las palabras de la casa qué
    significa y qué hacer.
    """
    base = {r["codigo"]: r for r in Criterio().reglas_vigentes()}
    if codigo not in base:
        raise HTTPException(404, f"No existe la regla «{codigo}».")
    if datos.severidad is not None and datos.severidad not in SEVERIDADES:
        raise HTTPException(
            400, f"Severidad «{datos.severidad}» desconocida. Las válidas son: "
                 f"{', '.join(sorted(SEVERIDADES))}.")

    campos = {c: getattr(datos, c) for c in
              ("activa", "severidad", "urgencia", "orden", "lectura", "accion")}
    if all(v is None for v in campos.values()):
        raise HTTPException(
            400, "No se indicó ningún cambio. Para volver a la regla de "
                 "referencia hay que borrar el ajuste.")

    await _guardar(db, "REGLA", codigo, campos, datos.motivo,
                   getattr(usuario, "username", None))
    return {"guardado": True, "ambito": "REGLA", "clave": codigo,
            "referencia": base[codigo]["referencia"]}


@router.delete("/criterios/{ambito}/{clave:path}")
async def restaurar_criterio(
    ambito: str, clave: str,
    db: AsyncSession = Depends(get_db),
):
    """Borra el ajuste y devuelve el criterio de referencia.

    Se borra la fila y no se marca inactiva: el registro de qué se cambió y por
    qué solo tiene valor mientras el cambio esté vigente. Una fila apagada con
    un motivo de hace dos años no informa, estorba.
    """
    ambito = ambito.upper()
    if ambito not in AMBITOS:
        raise HTTPException(404, f"Ámbito «{ambito}» desconocido.")
    fila = (await db.execute(
        select(LubeAjusteNorma).where(and_(LubeAjusteNorma.ambito == ambito,
                                           LubeAjusteNorma.clave == clave))
    )).scalar_one_or_none()
    if fila is None:
        raise HTTPException(
            404, "Ese criterio no está ajustado: ya está en su valor de "
                 "referencia.")
    await db.delete(fila)
    await db.commit()
    return {"restaurado": True, "ambito": ambito, "clave": clave}


@router.get("/criterios/ajustes")
async def ajustes_vigentes(db: AsyncSession = Depends(get_db)):
    """Todo lo que esta empresa cambió, junto y con su motivo.

    Es la vista de auditoría: la lista corta de en qué se aparta esta empresa
    del criterio publicado, sin tener que recorrer las tres pestañas buscando
    insignias.
    """
    filas = (await db.execute(
        select(LubeAjusteNorma).order_by(LubeAjusteNorma.ambito,
                                         LubeAjusteNorma.clave)
    )).scalars().all()
    return [{
        "ambito": a.ambito, "clave": a.clave,
        "precaucion": a.precaucion, "condena": a.condena, "valor": a.valor,
        "activa": a.activa, "severidad": a.severidad, "urgencia": a.urgencia,
        "orden": a.orden, "lectura": a.lectura, "accion": a.accion,
        "motivo": a.motivo, "ajustado_por": a.ajustado_por,
        "cuando": a.updated_at or a.created_at,
    } for a in filas]
