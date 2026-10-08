"""
Lo que comparten todas las rutas de GRC: quién puede ser asignado, cómo se
valida una clasificación, cómo se deja rastro y los cálculos que el módulo no
deja escribir a mano (residual, prioridad, efectividad, vencimientos).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.catalogos import resolver_valor_catalogo
from app.infrastructure.models.catalogo import CatalogoMaestro
from app.infrastructure.models.grc import (
    EfectividadControlGRCEnum, GRCBandaRiesgo, GRCControl, GRCHistorial, GRCParametro,
    GRCPruebaControl, GRCRiesgo, GRCRiesgoControl, PrioridadRiesgoGRCEnum, TipoControlGRCEnum,
)

AHORA = lambda: datetime.now(timezone.utc)   # noqa: E731


# ── Personas ─────────────────────────────────────────────────────────────────

SQL_PERSONAS = """
    SELECT u.id, u.nombre, u.apellido, u.email, u.cargo
    FROM usuarios u LEFT JOIN roles r ON r.id = u.rol_id
    WHERE u.activo
      AND (upper(coalesce(u.rol, '')) = 'ADMINISTRADOR'
           OR upper(coalesce(r.nombre, '')) = 'ADMINISTRADOR'
           OR lower(coalesce(r.permisos::jsonb ->> 'grc', 'false')) = 'true')
    ORDER BY u.nombre, u.apellido
"""


async def personas_grc(db: AsyncSession) -> List[dict]:
    """Usuarios activos con acceso al módulo GRC: los únicos asignables."""
    filas = (await db.execute(text(SQL_PERSONAS))).all()
    return [{"id": f.id, "nombre": f"{f.nombre} {f.apellido}".strip(), "email": f.email,
             "cargo": f.cargo} for f in filas]


async def mapa_usuarios(db: AsyncSession) -> Dict[int, str]:
    """Nombre de cualquier usuario, también de los que ya no tienen acceso:
    el historial tiene que poder decir quién era."""
    filas = (await db.execute(text("SELECT id, nombre, apellido FROM usuarios"))).all()
    return {f.id: f"{f.nombre} {f.apellido}".strip() for f in filas}


async def validar_personas(db: AsyncSession, cambios: Dict[str, Any], actuales: Dict[str, Any]) -> None:
    """Toda persona NUEVA en el registro debe tener acceso a GRC. Una que ya
    estaba y perdió el acceso no bloquea la edición del resto del registro."""
    validas = None
    for campo, valor in cambios.items():
        ids = valor if isinstance(valor, list) else [valor]
        previos = actuales.get(campo)
        previos = set(previos if isinstance(previos, list) else [previos])
        nuevos = [i for i in ids if i is not None and i not in previos]
        if not nuevos:
            continue
        if validas is None:
            validas = {p["id"] for p in await personas_grc(db)}
        malos = [i for i in nuevos if i not in validas]
        if malos:
            raise HTTPException(422, f"El usuario {malos[0]} no tiene acceso al módulo GRC "
                                     f"(campo «{campo.replace('_id', '').replace('_', ' ')}»).")


# ── Catálogos ────────────────────────────────────────────────────────────────

async def validar_catalogos(db: AsyncSession, datos: Dict[str, Any],
                            catalogos: Dict[str, tuple]) -> None:
    """Normaliza cada clasificación a la grafía del catálogo o rechaza el valor."""
    for campo, (modulo, tipo, etiqueta) in catalogos.items():
        if campo not in datos:
            continue
        valor = datos[campo]
        try:
            if isinstance(valor, list):
                datos[campo] = [await resolver_valor_catalogo(db, modulo, tipo, v, True, etiqueta)
                                for v in valor if (v or "").strip()]
            else:
                datos[campo] = await resolver_valor_catalogo(db, modulo, tipo, valor, False, etiqueta)
        except ValueError as e:
            raise HTTPException(422, str(e))


async def metadatos_catalogo(db: AsyncSession, modulo: str, tipo: str) -> Dict[str, dict]:
    filas = (await db.execute(select(CatalogoMaestro.nombre, CatalogoMaestro.metadatos).where(
        CatalogoMaestro.modulo == modulo, CatalogoMaestro.tipo == tipo))).all()
    salida = {}
    for nombre, meta in filas:
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = {}
        salida[nombre] = meta or {}
    return salida


async def dias_de(db: AsyncSession, periodicidad: Optional[str]) -> Optional[int]:
    if not periodicidad:
        return None
    meta = (await metadatos_catalogo(db, "GRC", "PERIODICIDAD")).get(periodicidad) or {}
    try:
        return int(meta.get("dias")) if meta.get("dias") else None
    except (TypeError, ValueError):
        return None


# ── Parámetros ───────────────────────────────────────────────────────────────

async def parametro(db: AsyncSession, clave: str, defecto: int) -> int:
    v = (await db.execute(select(GRCParametro.valor).where(GRCParametro.clave == clave))).scalar()
    try:
        return int(v) if v is not None else defecto
    except ValueError:
        return defecto


# ── Historial ────────────────────────────────────────────────────────────────

def _texto(v) -> Optional[str]:
    if v is None:
        return None
    if hasattr(v, "value"):
        v = v.value
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)[:2000]


async def registrar(db: AsyncSession, entidad: str, entidad_id: int, accion: str,
                    usuario_id: Optional[int], campo: Optional[str] = None,
                    anterior=None, nuevo=None) -> None:
    db.add(GRCHistorial(entidad=entidad, entidad_id=entidad_id, accion=accion, campo=campo,
                        anterior=_texto(anterior), nuevo=_texto(nuevo),
                        usuario_id=usuario_id, fecha=AHORA()))


# ── Serialización ────────────────────────────────────────────────────────────

def valor_json(v):
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


LISTAS_DE_PERSONAS = ("equipo", "participantes", "asistentes")


def como_dict(obj, usuarios: Dict[int, str], personas: Iterable[str] = (),
              listas_personas: Iterable[str] = ()) -> dict:
    d = {c.name: valor_json(getattr(obj, c.name)) for c in obj.__table__.columns}
    # Sin lista explícita: toda columna con llave a usuarios es una persona.
    if not personas:
        personas = [c.name for c in obj.__table__.columns
                    if any(fk.column.table.name == "usuarios" for fk in c.foreign_keys)]
    if not listas_personas:
        listas_personas = [c for c in LISTAS_DE_PERSONAS if c in d]
    for campo in personas:
        d[campo.removesuffix("_id") + "_nombre"] = usuarios.get(d.get(campo)) if d.get(campo) else None
    for campo in listas_personas:
        d[campo + "_nombres"] = [usuarios.get(i, f"#{i}") for i in (d.get(campo) or [])]
    return d


# ── Riesgo: niveles, residual y prioridad ────────────────────────────────────

REDUCCION = {EfectividadControlGRCEnum.EFECTIVO: 2, EfectividadControlGRCEnum.PARCIALMENTE_EFECTIVO: 1}


async def bandas(db: AsyncSession) -> List[GRCBandaRiesgo]:
    return list((await db.execute(select(GRCBandaRiesgo).order_by(GRCBandaRiesgo.minimo.desc()))).scalars())


async def prioridad_de(db: AsyncSession, nivel: Optional[int], cache=None) -> Optional[PrioridadRiesgoGRCEnum]:
    if not nivel:
        return None
    lista = cache if cache is not None else await bandas(db)
    for b in lista:            # de la más alta a la más baja
        if nivel >= b.minimo:
            return b.prioridad
    return PrioridadRiesgoGRCEnum.BAJA


async def recalcular_riesgo(db: AsyncSession, riesgo: GRCRiesgo) -> None:
    """Nivel inherente = probabilidad × impacto. El residual sale de los
    controles vinculados y su efectividad PROBADA:

    - preventivo: reduce la probabilidad (2 niveles si es efectivo, 1 si es
      parcialmente efectivo);
    - detectivo y correctivo: reducen el impacto, con la misma regla;
    - compensatorio: reduce los dos, un nivel menos que los anteriores.

    En cada eje cuenta el MEJOR control, no la suma: tres controles mediocres
    no hacen uno excelente. Un control no probado no reduce nada; esa es la
    diferencia entre un control que existe en un papel y uno que funciona.
    """
    p, i = riesgo.probabilidad_inherente, riesgo.impacto_inherente
    riesgo.nivel_inherente = p * i if p and i else None
    if not (p and i):
        riesgo.probabilidad_residual = riesgo.impacto_residual = riesgo.nivel_residual = None
        riesgo.prioridad = None
        return
    controles = (await db.execute(
        select(GRCControl.tipo, GRCControl.efectividad)
        .join(GRCRiesgoControl, GRCRiesgoControl.control_id == GRCControl.id)
        .where(GRCRiesgoControl.riesgo_id == riesgo.id, GRCControl.deleted_at.is_(None)))).all() if riesgo.id else []
    red_p = red_i = 0
    for tipo, efect in controles:
        r = REDUCCION.get(efect, 0)
        if tipo == TipoControlGRCEnum.PREVENTIVO:
            red_p = max(red_p, r)
        elif tipo in (TipoControlGRCEnum.DETECTIVO, TipoControlGRCEnum.CORRECTIVO):
            red_i = max(red_i, r)
        elif tipo == TipoControlGRCEnum.COMPENSATORIO:
            red_p, red_i = max(red_p, r - 1), max(red_i, r - 1)
    riesgo.probabilidad_residual = max(1, p - red_p)
    riesgo.impacto_residual = max(1, i - red_i)
    riesgo.nivel_residual = riesgo.probabilidad_residual * riesgo.impacto_residual
    riesgo.prioridad = await prioridad_de(db, riesgo.nivel_residual)


async def recalcular_riesgos_de_control(db: AsyncSession, control_id: int) -> None:
    ids = (await db.execute(select(GRCRiesgoControl.riesgo_id).where(
        GRCRiesgoControl.control_id == control_id))).scalars().all()
    for rid in ids:
        r = await db.get(GRCRiesgo, rid)
        if r is not None and r.deleted_at is None:
            await recalcular_riesgo(db, r)


# ── Control: la efectividad sale de la última prueba ─────────────────────────

async def recalcular_control(db: AsyncSession, control: GRCControl) -> None:
    ultima = (await db.execute(
        select(GRCPruebaControl).where(GRCPruebaControl.control_id == control.id,
                                       GRCPruebaControl.deleted_at.is_(None))
        .order_by(GRCPruebaControl.fecha.desc(), GRCPruebaControl.id.desc()).limit(1))).scalar()
    if ultima is None:
        control.efectividad = EfectividadControlGRCEnum.NO_PROBADO
        control.ultima_evaluacion = None
    else:
        control.efectividad = ultima.resultado
        control.ultima_evaluacion = ultima.fecha
    dias = await dias_de(db, control.periodicidad_prueba)
    base = control.ultima_evaluacion or (control.created_at.date() if control.created_at else date.today())
    control.proxima_evaluacion = base + timedelta(days=dias) if dias else None
    await db.flush()
    await recalcular_riesgos_de_control(db, control.id)


# ── Terceros ─────────────────────────────────────────────────────────────────

def clasificar_tercero(puntaje: Optional[float]):
    """Puntaje de la evaluación (más es mejor) → clasificación y nivel de riesgo."""
    if puntaje is None:
        return None, None
    if puntaje >= 90:
        return "excelente", "bajo"
    if puntaje >= 75:
        return "bueno", "medio"
    if puntaje >= 60:
        return "regular", "alto"
    return "deficiente", "critico"


# ── KRI ──────────────────────────────────────────────────────────────────────

def estado_kri(valor, direccion: str, alerta, critico) -> str:
    if valor is None:
        return "sin_medicion"
    v, a, c = float(valor), float(alerta), float(critico)
    if direccion == "baja":
        return "critico" if v <= c else "alerta" if v <= a else "normal"
    return "critico" if v >= c else "alerta" if v >= a else "normal"
