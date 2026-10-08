"""
Métricas de confiabilidad del CMMS.

Vive en `core` porque las usan el tablero, el módulo de confiabilidad y los
informes. Tres copias de la misma fórmula terminan dando tres cifras distintas
del mismo equipo, y la conversación deja de ser sobre el equipo y pasa a ser
sobre cuál pantalla tiene la razón.

QUÉ SE CALCULA Y CON QUÉ DATO

  MTTR   promedio de (fecha_fin − fecha_inicio) de las órdenes marcadas como
         falla y ya cerradas. Es tiempo de reparación real, no estimado.

  MTBF   por activo, el tiempo entre fallas consecutivas:
         (última − primera) ÷ (número de fallas − 1)
         Se promedia entre los activos con al menos dos fallas: con una sola no
         hay «entre».

  Disponibilidad   tiempo del periodo menos el tiempo fuera de servicio, sobre
         el tiempo del periodo. Solo cuentan las órdenes que declaran
         `afecta_disponibilidad`: cambiar un filtro con el equipo andando no
         resta disponibilidad.

TODO SE DEVUELVE CON SU MUESTRA
Un MTBF sacado de tres órdenes no significa lo mismo que uno de trescientas.
Cuando no hay datos suficientes se devuelve `None`, nunca cero: un cero se lee
como «se daña todo el tiempo» y sería exactamente lo contrario de la verdad.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.eam import EAMActivo, EAMOrdenTrabajo

ESTADOS_ABIERTA = ("PENDIENTE", "ASIGNADA", "EN_EJECUCION", "EN_ESPERA_REPUESTOS")


def horas_entre(inicio: Optional[datetime], fin: Optional[datetime]) -> Optional[float]:
    if not inicio or not fin or fin < inicio:
        return None
    return (fin - inicio).total_seconds() / 3600


async def ordenes_del_periodo(db: AsyncSession, desde: datetime,
                              tipo_activo: Optional[str] = None,
                              marca: Optional[str] = None,
                              activo_id: Optional[int] = None
                              ) -> List[Tuple[EAMOrdenTrabajo, EAMActivo]]:
    """Órdenes cerradas en el periodo, con su activo. Una sola consulta.

    Se traen juntas y se agregan en Python en vez de hacer una consulta por
    métrica: son los mismos registros para MTBF, MTTR, costo y disponibilidad, y
    seis recorridos de la misma tabla no dan una cifra mejor.
    """
    q = (select(EAMOrdenTrabajo, EAMActivo)
         .join(EAMActivo, EAMActivo.id == EAMOrdenTrabajo.activo_id)
         .where(and_(EAMOrdenTrabajo.fecha_fin.isnot(None),
                     EAMOrdenTrabajo.fecha_fin >= desde)))
    if tipo_activo:
        q = q.where(EAMActivo.tipo_activo == tipo_activo)
    if marca:
        q = q.where(EAMActivo.marca == marca)
    if activo_id:
        q = q.where(EAMOrdenTrabajo.activo_id == activo_id)
    return list((await db.execute(q)).all())


def mttr(ordenes: List[Tuple[EAMOrdenTrabajo, EAMActivo]]) -> Tuple[Optional[float], int]:
    """Tiempo medio de reparación, y sobre cuántas órdenes se calculó."""
    duraciones = [h for h in (horas_entre(o.fecha_inicio, o.fecha_fin)
                              for o, _ in ordenes if o.es_falla) if h is not None]
    if not duraciones:
        return None, 0
    return round(sum(duraciones) / len(duraciones), 1), len(duraciones)


def mtbf(ordenes: List[Tuple[EAMOrdenTrabajo, EAMActivo]]) -> Tuple[Optional[float], int]:
    """Tiempo medio entre fallas, y sobre cuántos activos.

    Se agrupa por activo antes de promediar: mezclar las fechas de toda la flota
    en una sola serie daría un intervalo pequeño solo porque hay muchos equipos.
    """
    por_activo: Dict[int, List[datetime]] = defaultdict(list)
    for o, _ in ordenes:
        if o.es_falla and o.fecha_inicio:
            por_activo[o.activo_id].append(o.fecha_inicio)

    intervalos = []
    for fechas in por_activo.values():
        if len(fechas) < 2:
            continue
        fechas.sort()
        intervalos.append((fechas[-1] - fechas[0]).total_seconds() / 3600 / (len(fechas) - 1))
    if not intervalos:
        return None, 0
    return round(sum(intervalos) / len(intervalos), 1), len(intervalos)


HORAS_MES_CONTINUO = 720.0


def horas_programadas(activos, dias: int) -> float:
    """Horas que los activos debían estar disponibles en el periodo.

    Cada activo aporta sus horas programadas por mes (Configuración →
    Disponibilidad); sin dato, se supone operación continua (720 h/mes). Una
    montacargas de un turno no debe contarse como si trabajara 24 horas: su
    disponibilidad saldría inflada.
    """
    if isinstance(activos, int):
        return activos * dias * 24
    return sum((getattr(a, "horas_programadas_mes", None) or HORAS_MES_CONTINUO) / 30 * dias for a in activos)


def disponibilidad(ordenes: List[Tuple[EAMOrdenTrabajo, EAMActivo]],
                   activos, dias: int) -> Optional[float]:
    """Porcentaje del tiempo programado en que la flota estuvo disponible.

    `activos` es la lista de activos (o, por compatibilidad, cuántos son).
    Solo restan las órdenes que declaran afectar la disponibilidad: un cambio de
    aceite con el equipo operando no es tiempo perdido, y contarlo haría que la
    cifra castigue el mantenimiento preventivo, que es justo lo contrario de lo
    que se quiere incentivar.
    """
    if not activos or not dias:
        return None
    horas_totales = horas_programadas(activos, dias)
    if horas_totales <= 0:
        return None
    fuera = sum(h for h in (horas_entre(o.fecha_inicio, o.fecha_fin)
                            for o, _ in ordenes if o.afecta_disponibilidad)
                if h is not None)
    return round(max(0.0, (horas_totales - fuera) / horas_totales) * 100, 2)


def agrupar(ordenes: List[Tuple[EAMOrdenTrabajo, EAMActivo]],
            clave, dias: int) -> List[Dict[str, Any]]:
    """Indicadores por marca, línea, tipo o activo, según la clave que se pase.

    Cada grupo trae su propio MTBF y MTTR calculados sobre sus órdenes, no un
    prorrateo del total: el promedio de la flota no dice nada de un equipo en
    particular, que es lo que se quiere encontrar acá.
    """
    grupos: Dict[str, List[Tuple[EAMOrdenTrabajo, EAMActivo]]] = defaultdict(list)
    activos_por_grupo: Dict[str, dict] = defaultdict(dict)
    for o, a in ordenes:
        etiqueta = clave(a)
        if not etiqueta:
            continue
        grupos[etiqueta].append((o, a))
        activos_por_grupo[etiqueta][a.id] = a

    salida = []
    for etiqueta, filas in grupos.items():
        valor_mttr, casos_mttr = mttr(filas)
        valor_mtbf, activos_mtbf = mtbf(filas)
        fallas = sum(1 for o, _ in filas if o.es_falla)
        costo = sum(o.costo_total or 0 for o, _ in filas)
        fuera = sum(h for h in (horas_entre(o.fecha_inicio, o.fecha_fin)
                                for o, _ in filas if o.afecta_disponibilidad)
                    if h is not None)
        salida.append({
            "etiqueta": etiqueta,
            "activos": len(activos_por_grupo[etiqueta]),
            "ordenes": len(filas), "fallas": fallas,
            "costo": round(costo, 2),
            "costo_fallas": round(sum(o.costo_total or 0 for o, _ in filas if o.es_falla), 2),
            "mttr_horas": valor_mttr, "mttr_casos": casos_mttr,
            "mtbf_horas": valor_mtbf, "mtbf_activos": activos_mtbf,
            "horas_fuera": round(fuera, 1),
            "disponibilidad": disponibilidad(filas, list(activos_por_grupo[etiqueta].values()), dias),
        })
    return sorted(salida, key=lambda x: -x["fallas"])
