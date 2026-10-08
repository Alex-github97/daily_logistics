"""AGS - Agenda de Servicios.

Agenda, catalogo de servicios con precio preconfigurado e ingresos por cliente
para negocios de servicio con cita previa (salones, barberias, plomeros,
albaniles, tecnicos a domicilio).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, and_, or_
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from app.core.database import get_db
from app.infrastructure.models.ags import (
    AGSConfig, AGSCategoriaServicio, AGSServicio,
    AGSProfesional, AGSProfesionalServicio, AGSHorarioProfesional, AGSAusencia,
    AGSCliente, AGSCita, AGSCitaServicio, AGSCitaMaterial, AGSPagoCita,
    EstadoCitaEnum, LugarServicioEnum, OrigenCitaEnum, MedioPagoEnum, TipoPagoEnum,
)

router = APIRouter(prefix="/ags", tags=["ags"])


# Estados que ocupan un espacio real en la agenda: una cita cancelada o con
# inasistencia libera el horario y no debe bloquear a nadie mas.
ESTADOS_ACTIVOS = [
    EstadoCitaEnum.AGENDADA.value,
    EstadoCitaEnum.CONFIRMADA.value,
    EstadoCitaEnum.EN_CURSO.value,
    EstadoCitaEnum.COMPLETADA.value,
]

# Estados que ya generaron ingreso
ESTADOS_FACTURABLES = [EstadoCitaEnum.COMPLETADA.value]


# ──────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────

# El servidor corre en UTC, pero un negocio de servicios vive en su hora local:
# la agenda del dia, el cierre de caja y el "no agendar en el pasado" tienen que
# medirse contra la hora del local, no contra UTC. Sin esto un pago recibido a
# las 8pm en Colombia caeria en la caja del dia siguiente.
ZONA_LOCAL = ZoneInfo("America/Bogota")


def _ahora() -> datetime:
    """Hora local del negocio, sin tzinfo para comparar con las fechas guardadas."""
    return datetime.now(ZONA_LOCAL).replace(tzinfo=None)


def _hoy() -> date:
    return _ahora().date()


async def _get_config(db: AsyncSession) -> AGSConfig:
    r = await db.execute(select(AGSConfig).limit(1))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        cfg = AGSConfig(
            nombre_negocio="Mi negocio",
            dias_laborales=[1, 2, 3, 4, 5, 6],
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def _siguiente_codigo(db: AsyncSession, modelo, prefijo: str, ancho: int = 4) -> str:
    """Codigo consecutivo tipo CITA-0001 tomando el maximo existente."""
    r = await db.execute(select(func.count()).select_from(modelo))
    base = (r.scalar() or 0) + 1
    for _ in range(200):  # salta huecos si borraron filas
        codigo = "%s-%0*d" % (prefijo, ancho, base)
        rc = await db.execute(select(modelo.id).where(modelo.codigo == codigo))
        if rc.scalar_one_or_none() is None:
            return codigo
        base += 1
    return "%s-%d" % (prefijo, int(_ahora().timestamp()))


def _hhmm_a_min(txt: Optional[str]) -> Optional[int]:
    if not txt:
        return None
    try:
        partes = str(txt).split(":")
        return int(partes[0]) * 60 + int(partes[1])
    except (ValueError, IndexError):
        return None


def _min_a_hhmm(minutos: int) -> str:
    return "%02d:%02d" % (minutos // 60, minutos % 60)


def _dia_semana(f: date) -> int:
    """1=lunes ... 7=domingo (igual que ISO)."""
    return f.isoweekday()


def _sin_tz(d: Optional[datetime]) -> Optional[datetime]:
    """Quita el tzinfo para poder comparar contra fechas construidas localmente."""
    if d is None:
        return None
    return d.replace(tzinfo=None) if d.tzinfo is not None else d


def _recalcular_totales(cita: AGSCita, servicios: List[AGSCitaServicio],
                        materiales: List[AGSCitaMaterial],
                        comision_profesional_pct: float, iva_pct: float = 0) -> None:
    """Recalcula el dinero de la cita a partir de sus lineas.

    subtotal servicios + materiales - descuento + propina = total
    La comision se calcula solo sobre la mano de obra (servicios), nunca sobre
    materiales ni propina: el material lo pone el negocio y la propina es del
    profesional completa.
    """
    subtotal = 0.0
    comision = 0.0
    duracion = 0
    for s in servicios:
        linea = float(s.subtotal or 0)
        subtotal += linea
        duracion += int(s.duracion_min or 0)
        pct = s.comision_pct if s.comision_pct is not None else comision_profesional_pct
        comision += linea * float(pct or 0) / 100.0

    materiales_total = sum(float(m.subtotal or 0) for m in materiales)

    cita.subtotal = round(subtotal, 2)
    cita.total_materiales = round(materiales_total, 2)
    cita.comision_profesional = round(comision, 2)
    cita.total = round(
        subtotal + materiales_total - float(cita.descuento or 0) + float(cita.propina or 0), 2
    )
    # IVA de la configuración: los precios ya lo traen, así que se discrimina
    # la parte que es impuesto (base = precio / (1 + tasa)). La propina no es
    # venta del negocio y no lleva IVA. Antes la tasa se guardaba y no se usaba.
    gravado = subtotal + materiales_total - float(cita.descuento or 0)
    tasa = float(iva_pct or 0)
    cita.iva_incluido = round(gravado * tasa / (100 + tasa), 2) if tasa > 0 and gravado > 0 else 0.0
    if duracion > 0:
        cita.duracion_min = duracion
        cita.fecha_fin = _sin_tz(cita.fecha_inicio) + timedelta(minutes=duracion)


async def _validar_disponibilidad(
    db: AsyncSession, profesional_id: int, inicio: datetime, fin: datetime,
    excluir_cita_id: Optional[int] = None, permite_sobrecupo: bool = False,
) -> None:
    """Rechaza el agendamiento si el profesional ya esta ocupado o ausente.

    Es la regla de negocio que evita el problema clasico de estos negocios:
    dos clientes citados a la misma hora con la misma persona.
    """
    inicio = _sin_tz(inicio)
    fin = _sin_tz(fin)

    # Ausencias (del profesional o cierre general del negocio)
    ra = await db.execute(select(AGSAusencia).where(
        or_(AGSAusencia.profesional_id == profesional_id,
            AGSAusencia.profesional_id.is_(None)),
    ))
    for a in ra.scalars().all():
        a_ini, a_fin = _sin_tz(a.fecha_inicio), _sin_tz(a.fecha_fin)
        if a_ini < fin and a_fin > inicio:
            quien = "el negocio" if a.profesional_id is None else "el profesional"
            raise HTTPException(
                status_code=409,
                detail="No se puede agendar: %s tiene registrada una ausencia (%s) "
                       "del %s al %s." % (
                           quien, a.motivo or a.tipo or "sin motivo",
                           a_ini.strftime("%d/%m/%Y %H:%M"), a_fin.strftime("%d/%m/%Y %H:%M")),
            )

    if permite_sobrecupo:
        return

    # Cruce con otra cita activa del mismo profesional
    q = select(AGSCita).where(
        AGSCita.profesional_id == profesional_id,
        AGSCita.estado.in_(ESTADOS_ACTIVOS),
        AGSCita.fecha_inicio < fin,
        AGSCita.fecha_fin > inicio,
    )
    if excluir_cita_id is not None:
        q = q.where(AGSCita.id != excluir_cita_id)
    r = await db.execute(q.limit(1))
    choque = r.scalar_one_or_none()
    if choque is not None:
        cli = await db.get(AGSCliente, choque.cliente_id)
        raise HTTPException(
            status_code=409,
            detail="Horario ocupado: %s ya tiene la cita %s con %s de %s a %s." % (
                "el profesional", choque.codigo,
                cli.nombre if cli else "otro cliente",
                _sin_tz(choque.fecha_inicio).strftime("%H:%M"),
                _sin_tz(choque.fecha_fin).strftime("%H:%M")),
        )


# ──────────────────────────────────────────
# CONFIGURACION
# ──────────────────────────────────────────

class ConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_negocio: str
    tipo_negocio: Optional[str] = None
    nit: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    hora_apertura: Optional[str] = None
    hora_cierre: Optional[str] = None
    dias_laborales: Optional[List[int]] = None
    intervalo_agenda_min: Optional[int] = None
    moneda: Optional[str] = None
    iva_pct: Optional[float] = None
    comision_defecto_pct: Optional[float] = None
    permite_sobrecupo: Optional[bool] = None
    anticipacion_minima_min: Optional[int] = None
    tolerancia_no_show_min: Optional[int] = None
    mensaje_recordatorio: Optional[str] = None
    reserva_online_activa: Optional[bool] = None
    slug: Optional[str] = None
    mensaje_bienvenida: Optional[str] = None
    dias_max_anticipacion: Optional[int] = None
    max_citas_pendientes_cliente: Optional[int] = None
    permite_cancelar_online: Optional[bool] = None
    horas_min_cancelacion: Optional[int] = None
    requiere_confirmacion_online: Optional[bool] = None


class ConfigUpdate(BaseModel):
    nombre_negocio: Optional[str] = None
    tipo_negocio: Optional[str] = None
    nit: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    hora_apertura: Optional[str] = None
    hora_cierre: Optional[str] = None
    dias_laborales: Optional[List[int]] = None
    intervalo_agenda_min: Optional[int] = None
    moneda: Optional[str] = None
    iva_pct: Optional[float] = None
    comision_defecto_pct: Optional[float] = None
    permite_sobrecupo: Optional[bool] = None
    anticipacion_minima_min: Optional[int] = None
    tolerancia_no_show_min: Optional[int] = None
    mensaje_recordatorio: Optional[str] = None
    reserva_online_activa: Optional[bool] = None
    slug: Optional[str] = None
    mensaje_bienvenida: Optional[str] = None
    dias_max_anticipacion: Optional[int] = None
    max_citas_pendientes_cliente: Optional[int] = None
    permite_cancelar_online: Optional[bool] = None
    horas_min_cancelacion: Optional[int] = None
    requiere_confirmacion_online: Optional[bool] = None


@router.get("/config", response_model=ConfigResponse)
async def obtener_config(db: AsyncSession = Depends(get_db)):
    return await _get_config(db)


@router.put("/config", response_model=ConfigResponse)
async def actualizar_config(data: ConfigUpdate, db: AsyncSession = Depends(get_db)):
    cfg = await _get_config(db)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)
    await db.commit()
    await db.refresh(cfg)
    return cfg


# ──────────────────────────────────────────
# CATEGORIAS DE SERVICIO
# ──────────────────────────────────────────

class CategoriaBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    color: Optional[str] = "#A21CAF"
    orden: Optional[int] = 0
    activo: Optional[bool] = True


class CategoriaResponse(CategoriaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total_servicios: int = 0


@router.get("/categorias", response_model=List[CategoriaResponse])
async def listar_categorias(solo_activas: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(AGSCategoriaServicio)
    if solo_activas:
        q = q.where(AGSCategoriaServicio.activo == True)
    r = await db.execute(q.order_by(AGSCategoriaServicio.orden, AGSCategoriaServicio.nombre))
    cats = r.scalars().all()

    rc = await db.execute(
        select(AGSServicio.categoria_id, func.count()).group_by(AGSServicio.categoria_id)
    )
    conteo = {cid: n for cid, n in rc.all()}

    salida = []
    for c in cats:
        item = CategoriaResponse.model_validate(c)
        item.total_servicios = conteo.get(c.id, 0)
        salida.append(item)
    return salida


@router.post("/categorias", response_model=CategoriaResponse, status_code=201)
async def crear_categoria(data: CategoriaBase, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(AGSCategoriaServicio).where(
        func.lower(AGSCategoriaServicio.nombre) == data.nombre.strip().lower()))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "Ya existe una categoria llamada '%s'." % data.nombre)
    obj = AGSCategoriaServicio(**data.model_dump())
    obj.nombre = obj.nombre.strip()
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return CategoriaResponse.model_validate(obj)


@router.put("/categorias/{cid}", response_model=CategoriaResponse)
async def actualizar_categoria(cid: int, data: CategoriaBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSCategoriaServicio, cid)
    if obj is None:
        raise HTTPException(404, "Categoria no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return CategoriaResponse.model_validate(obj)


@router.delete("/categorias/{cid}", status_code=204)
async def eliminar_categoria(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSCategoriaServicio, cid)
    if obj is None:
        raise HTTPException(404, "Categoria no encontrada")
    r = await db.execute(select(func.count()).select_from(AGSServicio).where(
        AGSServicio.categoria_id == cid))
    if (r.scalar() or 0) > 0:
        raise HTTPException(409, "La categoria tiene servicios asociados. "
                                 "Muevalos a otra categoria o desactivela.")
    await db.delete(obj)
    await db.commit()


# ──────────────────────────────────────────
# SERVICIOS (catalogo con precio preconfigurado)
# ──────────────────────────────────────────

class ServicioBase(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    categoria_id: Optional[int] = None
    descripcion: Optional[str] = None
    duracion_min: int = 30
    precio: float = 0
    costo_insumos: Optional[float] = 0
    comision_pct: Optional[float] = None
    permite_domicilio: Optional[bool] = False
    cobra_materiales: Optional[bool] = False
    requiere_anticipo: Optional[bool] = False
    color: Optional[str] = None
    activo: Optional[bool] = True


class ServicioResponse(ServicioBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    categoria_nombre: Optional[str] = None
    categoria_color: Optional[str] = None
    margen: Optional[float] = None
    margen_pct: Optional[float] = None
    veces_vendido: int = 0


@router.get("/servicios", response_model=List[ServicioResponse])
async def listar_servicios(
    categoria_id: Optional[int] = None,
    solo_activos: bool = False,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    cons = select(AGSServicio)
    if categoria_id is not None:
        cons = cons.where(AGSServicio.categoria_id == categoria_id)
    if solo_activos:
        cons = cons.where(AGSServicio.activo == True)
    if q:
        patron = "%%%s%%" % q.strip().lower()
        cons = cons.where(or_(func.lower(AGSServicio.nombre).like(patron),
                              func.lower(AGSServicio.codigo).like(patron)))
    r = await db.execute(cons.order_by(AGSServicio.nombre))
    servicios = r.scalars().all()

    rc = await db.execute(select(AGSCategoriaServicio))
    cats = {c.id: c for c in rc.scalars().all()}

    rv = await db.execute(
        select(AGSCitaServicio.servicio_id, func.count())
        .group_by(AGSCitaServicio.servicio_id)
    )
    vendidos = {sid: n for sid, n in rv.all()}

    salida = []
    for s in servicios:
        item = ServicioResponse.model_validate(s)
        cat = cats.get(s.categoria_id)
        item.categoria_nombre = cat.nombre if cat else None
        item.categoria_color = cat.color if cat else None
        precio = float(s.precio or 0)
        costo = float(s.costo_insumos or 0)
        item.margen = round(precio - costo, 2)
        item.margen_pct = round((precio - costo) / precio * 100, 1) if precio > 0 else None
        item.veces_vendido = vendidos.get(s.id, 0)
        salida.append(item)
    return salida


@router.post("/servicios", response_model=ServicioResponse, status_code=201)
async def crear_servicio(data: ServicioBase, db: AsyncSession = Depends(get_db)):
    if data.duracion_min <= 0:
        raise HTTPException(400, "La duracion del servicio debe ser mayor a cero: "
                                 "es lo que permite calcular la hora de fin en la agenda.")
    valores = data.model_dump()
    codigo = (valores.pop("codigo", None) or "").strip()
    if not codigo:
        codigo = await _siguiente_codigo(db, AGSServicio, "SRV")
    else:
        rc = await db.execute(select(AGSServicio).where(AGSServicio.codigo == codigo))
        if rc.scalar_one_or_none() is not None:
            raise HTTPException(400, "El codigo '%s' ya esta registrado." % codigo)
    obj = AGSServicio(codigo=codigo, **valores)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ServicioResponse.model_validate(obj)


@router.put("/servicios/{sid}", response_model=ServicioResponse)
async def actualizar_servicio(sid: int, data: ServicioBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSServicio, sid)
    if obj is None:
        raise HTTPException(404, "Servicio no encontrado")
    valores = data.model_dump(exclude_unset=True)
    valores.pop("codigo", None)
    if valores.get("duracion_min") is not None and valores["duracion_min"] <= 0:
        raise HTTPException(400, "La duracion del servicio debe ser mayor a cero.")
    for k, v in valores.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return ServicioResponse.model_validate(obj)


@router.delete("/servicios/{sid}", status_code=204)
async def eliminar_servicio(sid: int, db: AsyncSession = Depends(get_db)):
    """Desactiva el servicio en lugar de borrarlo: las citas historicas lo
    referencian y sus ingresos deben seguir cuadrando."""
    obj = await db.get(AGSServicio, sid)
    if obj is None:
        raise HTTPException(404, "Servicio no encontrado")
    r = await db.execute(select(func.count()).select_from(AGSCitaServicio).where(
        AGSCitaServicio.servicio_id == sid))
    if (r.scalar() or 0) > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj)
    await db.commit()


# ──────────────────────────────────────────
# PROFESIONALES
# ──────────────────────────────────────────

class HorarioBase(BaseModel):
    dia_semana: int
    hora_inicio: str
    hora_fin: str
    activo: Optional[bool] = True


class HorarioResponse(HorarioBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    profesional_id: int


class ProfesionalBase(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    documento: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    especialidad: Optional[str] = None
    color: Optional[str] = "#A21CAF"
    comision_pct: Optional[float] = 0
    salario_base: Optional[float] = 0
    fecha_ingreso: Optional[date] = None
    acepta_domicilio: Optional[bool] = False
    notas: Optional[str] = None
    activo: Optional[bool] = True


class ProfesionalResponse(ProfesionalBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    horarios: List[HorarioResponse] = []
    servicios_ids: List[int] = []
    citas_mes: int = 0
    ingresos_mes: float = 0


@router.get("/profesionales", response_model=List[ProfesionalResponse])
async def listar_profesionales(solo_activos: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(AGSProfesional)
    if solo_activos:
        q = q.where(AGSProfesional.activo == True)
    r = await db.execute(q.order_by(AGSProfesional.nombre))
    profesionales = r.scalars().all()
    if not profesionales:
        return []

    ids = [p.id for p in profesionales]

    rh = await db.execute(select(AGSHorarioProfesional).where(
        AGSHorarioProfesional.profesional_id.in_(ids)
    ).order_by(AGSHorarioProfesional.dia_semana, AGSHorarioProfesional.hora_inicio))
    horarios: Dict[int, List[HorarioResponse]] = {}
    for h in rh.scalars().all():
        horarios.setdefault(h.profesional_id, []).append(HorarioResponse.model_validate(h))

    rs = await db.execute(select(AGSProfesionalServicio).where(
        AGSProfesionalServicio.profesional_id.in_(ids)))
    servicios: Dict[int, List[int]] = {}
    for ps in rs.scalars().all():
        servicios.setdefault(ps.profesional_id, []).append(ps.servicio_id)

    # Produccion del mes en curso
    hoy = _hoy()
    inicio_mes = datetime(hoy.year, hoy.month, 1)
    rm = await db.execute(
        select(AGSCita.profesional_id, func.count(), func.coalesce(func.sum(AGSCita.total), 0))
        .where(AGSCita.profesional_id.in_(ids),
               AGSCita.estado.in_(ESTADOS_FACTURABLES),
               AGSCita.fecha_inicio >= inicio_mes)
        .group_by(AGSCita.profesional_id)
    )
    mes = {pid: (n, float(t or 0)) for pid, n, t in rm.all()}

    salida = []
    for p in profesionales:
        item = ProfesionalResponse.model_validate(p)
        item.horarios = horarios.get(p.id, [])
        item.servicios_ids = servicios.get(p.id, [])
        n, total = mes.get(p.id, (0, 0.0))
        item.citas_mes = n
        item.ingresos_mes = round(total, 2)
        salida.append(item)
    return salida


@router.post("/profesionales", response_model=ProfesionalResponse, status_code=201)
async def crear_profesional(data: ProfesionalBase, db: AsyncSession = Depends(get_db)):
    valores = data.model_dump()
    codigo = (valores.pop("codigo", None) or "").strip()
    if not codigo:
        codigo = await _siguiente_codigo(db, AGSProfesional, "PRO", 3)
    else:
        rc = await db.execute(select(AGSProfesional).where(AGSProfesional.codigo == codigo))
        if rc.scalar_one_or_none() is not None:
            raise HTTPException(400, "El codigo '%s' ya esta registrado." % codigo)
    obj = AGSProfesional(codigo=codigo, **valores)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ProfesionalResponse.model_validate(obj)


@router.put("/profesionales/{pid}", response_model=ProfesionalResponse)
async def actualizar_profesional(pid: int, data: ProfesionalBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSProfesional, pid)
    if obj is None:
        raise HTTPException(404, "Profesional no encontrado")
    valores = data.model_dump(exclude_unset=True)
    valores.pop("codigo", None)
    for k, v in valores.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return ProfesionalResponse.model_validate(obj)


@router.delete("/profesionales/{pid}", status_code=204)
async def eliminar_profesional(pid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSProfesional, pid)
    if obj is None:
        raise HTTPException(404, "Profesional no encontrado")
    r = await db.execute(select(func.count()).select_from(AGSCita).where(
        AGSCita.profesional_id == pid,
        AGSCita.estado.in_([EstadoCitaEnum.AGENDADA.value,
                            EstadoCitaEnum.CONFIRMADA.value,
                            EstadoCitaEnum.EN_CURSO.value]),
    ))
    pendientes = r.scalar() or 0
    if pendientes > 0:
        raise HTTPException(409, "No se puede desactivar: tiene %d cita(s) pendiente(s). "
                                 "Reasignelas o cancelelas primero." % pendientes)
    obj.activo = False
    await db.commit()


class ServiciosProfesionalUpdate(BaseModel):
    servicios_ids: List[int]


@router.put("/profesionales/{pid}/servicios", response_model=ProfesionalResponse)
async def asignar_servicios_profesional(
    pid: int, data: ServiciosProfesionalUpdate, db: AsyncSession = Depends(get_db)
):
    """Define que servicios sabe prestar. Sirve para que la agenda solo ofrezca
    a las personas capacitadas para el servicio pedido."""
    obj = await db.get(AGSProfesional, pid)
    if obj is None:
        raise HTTPException(404, "Profesional no encontrado")
    await db.execute(delete(AGSProfesionalServicio).where(
        AGSProfesionalServicio.profesional_id == pid))
    for sid in set(data.servicios_ids):
        db.add(AGSProfesionalServicio(profesional_id=pid, servicio_id=sid))
    await db.commit()
    await db.refresh(obj)
    item = ProfesionalResponse.model_validate(obj)
    item.servicios_ids = list(set(data.servicios_ids))
    return item


@router.put("/profesionales/{pid}/horarios", response_model=List[HorarioResponse])
async def definir_horarios(
    pid: int, horarios: List[HorarioBase], db: AsyncSession = Depends(get_db)
):
    """Reemplaza la jornada completa del profesional."""
    obj = await db.get(AGSProfesional, pid)
    if obj is None:
        raise HTTPException(404, "Profesional no encontrado")

    for h in horarios:
        ini, fin = _hhmm_a_min(h.hora_inicio), _hhmm_a_min(h.hora_fin)
        if ini is None or fin is None:
            raise HTTPException(400, "Hora invalida '%s - %s'. Use el formato HH:MM."
                                     % (h.hora_inicio, h.hora_fin))
        if fin <= ini:
            raise HTTPException(400, "La hora de fin (%s) debe ser posterior a la de inicio (%s)."
                                     % (h.hora_fin, h.hora_inicio))
        if h.dia_semana < 1 or h.dia_semana > 7:
            raise HTTPException(400, "Dia de la semana invalido: %s (1=lunes ... 7=domingo)."
                                     % h.dia_semana)

    await db.execute(delete(AGSHorarioProfesional).where(
        AGSHorarioProfesional.profesional_id == pid))
    nuevos = []
    for h in horarios:
        obj_h = AGSHorarioProfesional(profesional_id=pid, **h.model_dump())
        db.add(obj_h)
        nuevos.append(obj_h)
    await db.commit()
    for n in nuevos:
        await db.refresh(n)
    return [HorarioResponse.model_validate(n) for n in nuevos]


# ──────────────────────────────────────────
# AUSENCIAS
# ──────────────────────────────────────────

class AusenciaBase(BaseModel):
    profesional_id: Optional[int] = None
    fecha_inicio: datetime
    fecha_fin: datetime
    motivo: Optional[str] = None
    tipo: Optional[str] = "PERMISO"


class AusenciaResponse(AusenciaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    profesional_nombre: Optional[str] = None


@router.get("/ausencias", response_model=List[AusenciaResponse])
async def listar_ausencias(
    desde: Optional[datetime] = None, hasta: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(AGSAusencia)
    if desde is not None:
        q = q.where(AGSAusencia.fecha_fin >= desde)
    if hasta is not None:
        q = q.where(AGSAusencia.fecha_inicio <= hasta)
    r = await db.execute(q.order_by(AGSAusencia.fecha_inicio.desc()))
    ausencias = r.scalars().all()

    rp = await db.execute(select(AGSProfesional))
    nombres = {p.id: p.nombre for p in rp.scalars().all()}

    salida = []
    for a in ausencias:
        item = AusenciaResponse.model_validate(a)
        item.profesional_nombre = nombres.get(a.profesional_id) if a.profesional_id else "Todo el negocio"
        salida.append(item)
    return salida


@router.post("/ausencias", response_model=AusenciaResponse, status_code=201)
async def crear_ausencia(data: AusenciaBase, db: AsyncSession = Depends(get_db)):
    if data.fecha_fin <= data.fecha_inicio:
        raise HTTPException(400, "La fecha de fin debe ser posterior a la de inicio.")

    # Avisar si el bloqueo pisa citas ya agendadas
    q = select(func.count()).select_from(AGSCita).where(
        AGSCita.estado.in_([EstadoCitaEnum.AGENDADA.value, EstadoCitaEnum.CONFIRMADA.value]),
        AGSCita.fecha_inicio < data.fecha_fin,
        AGSCita.fecha_fin > data.fecha_inicio,
    )
    if data.profesional_id is not None:
        q = q.where(AGSCita.profesional_id == data.profesional_id)
    r = await db.execute(q)
    afectadas = r.scalar() or 0
    if afectadas > 0:
        raise HTTPException(409, "Hay %d cita(s) agendada(s) en ese rango. "
                                 "Reprogramelas o cancelelas antes de bloquear la agenda."
                                 % afectadas)

    obj = AGSAusencia(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return AusenciaResponse.model_validate(obj)


@router.delete("/ausencias/{aid}", status_code=204)
async def eliminar_ausencia(aid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSAusencia, aid)
    if obj is None:
        raise HTTPException(404, "Ausencia no encontrada")
    await db.delete(obj)
    await db.commit()


# ──────────────────────────────────────────
# CLIENTES
# ──────────────────────────────────────────

class ClienteBase(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    documento: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    barrio: Optional[str] = None
    ciudad: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    como_nos_conocio: Optional[str] = None
    acepta_recordatorios: Optional[bool] = True
    notas: Optional[str] = None
    activo: Optional[bool] = True


class ClienteResponse(ClienteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    total_citas: int = 0
    citas_completadas: int = 0
    citas_no_asistio: int = 0
    total_gastado: float = 0
    ticket_promedio: float = 0
    ultima_visita: Optional[datetime] = None
    proxima_cita: Optional[datetime] = None
    saldo_pendiente: float = 0


@router.get("/clientes", response_model=List[ClienteResponse])
async def listar_clientes(
    q: Optional[str] = None, solo_activos: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Clientes con sus metricas de valor: cuanto ha dejado cada uno, cada
    cuanto vuelve y si quedo debiendo."""
    cons = select(AGSCliente)
    if solo_activos:
        cons = cons.where(AGSCliente.activo == True)
    if q:
        patron = "%%%s%%" % q.strip().lower()
        cons = cons.where(or_(
            func.lower(AGSCliente.nombre).like(patron),
            func.lower(AGSCliente.telefono).like(patron),
            func.lower(AGSCliente.documento).like(patron),
            func.lower(AGSCliente.codigo).like(patron),
        ))
    r = await db.execute(cons.order_by(AGSCliente.nombre))
    clientes = r.scalars().all()
    if not clientes:
        return []

    ids = [c.id for c in clientes]
    rc = await db.execute(select(AGSCita).where(AGSCita.cliente_id.in_(ids)))
    citas = rc.scalars().all()

    ahora = _ahora()
    agregado: Dict[int, Dict[str, Any]] = {}
    for c in citas:
        d = agregado.setdefault(c.cliente_id, {
            "total": 0, "completadas": 0, "no_asistio": 0, "gastado": 0.0,
            "ultima": None, "proxima": None, "saldo": 0.0,
        })
        d["total"] += 1
        inicio = _sin_tz(c.fecha_inicio)
        if c.estado == EstadoCitaEnum.COMPLETADA.value:
            d["completadas"] += 1
            d["gastado"] += float(c.total or 0)
            d["saldo"] += float(c.total or 0) - float(c.total_pagado or 0)
            if d["ultima"] is None or inicio > d["ultima"]:
                d["ultima"] = inicio
        elif c.estado == EstadoCitaEnum.NO_ASISTIO.value:
            d["no_asistio"] += 1
        if c.estado in (EstadoCitaEnum.AGENDADA.value, EstadoCitaEnum.CONFIRMADA.value) \
                and inicio >= ahora:
            if d["proxima"] is None or inicio < d["proxima"]:
                d["proxima"] = inicio

    salida = []
    for c in clientes:
        item = ClienteResponse.model_validate(c)
        d = agregado.get(c.id)
        if d:
            item.total_citas = d["total"]
            item.citas_completadas = d["completadas"]
            item.citas_no_asistio = d["no_asistio"]
            item.total_gastado = round(d["gastado"], 2)
            item.ticket_promedio = round(d["gastado"] / d["completadas"], 2) if d["completadas"] else 0
            item.ultima_visita = d["ultima"]
            item.proxima_cita = d["proxima"]
            item.saldo_pendiente = round(max(d["saldo"], 0), 2)
        salida.append(item)
    return salida


@router.post("/clientes", response_model=ClienteResponse, status_code=201)
async def crear_cliente(data: ClienteBase, db: AsyncSession = Depends(get_db)):
    valores = data.model_dump()
    codigo = (valores.pop("codigo", None) or "").strip()
    if not codigo:
        codigo = await _siguiente_codigo(db, AGSCliente, "CLI", 5)
    else:
        rc = await db.execute(select(AGSCliente).where(AGSCliente.codigo == codigo))
        if rc.scalar_one_or_none() is not None:
            raise HTTPException(400, "El codigo '%s' ya esta registrado." % codigo)

    # Aviso temprano de duplicado por telefono: es el identificador real que
    # usa el mostrador para buscar a un cliente.
    if valores.get("telefono"):
        rt = await db.execute(select(AGSCliente).where(
            AGSCliente.telefono == valores["telefono"].strip()))
        dup = rt.scalar_one_or_none()
        if dup is not None:
            raise HTTPException(400, "El telefono %s ya esta registrado a nombre de %s (%s)."
                                     % (valores["telefono"], dup.nombre, dup.codigo))

    obj = AGSCliente(codigo=codigo, **valores)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ClienteResponse.model_validate(obj)


@router.put("/clientes/{cid}", response_model=ClienteResponse)
async def actualizar_cliente(cid: int, data: ClienteBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSCliente, cid)
    if obj is None:
        raise HTTPException(404, "Cliente no encontrado")
    valores = data.model_dump(exclude_unset=True)
    valores.pop("codigo", None)
    for k, v in valores.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return ClienteResponse.model_validate(obj)


@router.delete("/clientes/{cid}", status_code=204)
async def eliminar_cliente(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(AGSCliente, cid)
    if obj is None:
        raise HTTPException(404, "Cliente no encontrado")
    r = await db.execute(select(func.count()).select_from(AGSCita).where(
        AGSCita.cliente_id == cid,
        AGSCita.estado.in_([EstadoCitaEnum.AGENDADA.value,
                            EstadoCitaEnum.CONFIRMADA.value,
                            EstadoCitaEnum.EN_CURSO.value]),
    ))
    if (r.scalar() or 0) > 0:
        raise HTTPException(409, "El cliente tiene citas pendientes. Cancelelas primero.")
    obj.activo = False
    await db.commit()


class HistorialCitaCliente(BaseModel):
    id: int
    codigo: str
    fecha_inicio: datetime
    estado: str
    profesional: Optional[str] = None
    servicios: str = ""
    total: float = 0
    total_pagado: float = 0
    medio_pago: Optional[str] = None


class HistorialClienteResponse(BaseModel):
    cliente_id: int
    nombre: str
    total_citas: int
    total_gastado: float
    ticket_promedio: float
    saldo_pendiente: float
    dias_desde_ultima: Optional[int] = None
    servicio_favorito: Optional[str] = None
    citas: List[HistorialCitaCliente] = []


@router.get("/clientes/{cid}/historial", response_model=HistorialClienteResponse)
async def historial_cliente(cid: int, db: AsyncSession = Depends(get_db)):
    """Ficha del cliente: todo lo que ha consumido y cuanto ha dejado."""
    cli = await db.get(AGSCliente, cid)
    if cli is None:
        raise HTTPException(404, "Cliente no encontrado")

    rc = await db.execute(select(AGSCita).where(AGSCita.cliente_id == cid)
                          .order_by(AGSCita.fecha_inicio.desc()))
    citas = rc.scalars().all()

    rp = await db.execute(select(AGSProfesional))
    profs = {p.id: p.nombre for p in rp.scalars().all()}

    lineas: Dict[int, List[str]] = {}
    conteo_servicio: Dict[str, int] = {}
    if citas:
        rs = await db.execute(select(AGSCitaServicio).where(
            AGSCitaServicio.cita_id.in_([c.id for c in citas])))
        for s in rs.scalars().all():
            lineas.setdefault(s.cita_id, []).append(s.nombre_servicio)
            conteo_servicio[s.nombre_servicio] = conteo_servicio.get(s.nombre_servicio, 0) + 1

    gastado = sum(float(c.total or 0) for c in citas
                  if c.estado == EstadoCitaEnum.COMPLETADA.value)
    completadas = [c for c in citas if c.estado == EstadoCitaEnum.COMPLETADA.value]
    saldo = sum(float(c.total or 0) - float(c.total_pagado or 0) for c in completadas)
    ultima = max((_sin_tz(c.fecha_inicio) for c in completadas), default=None)

    favorito = None
    if conteo_servicio:
        favorito = max(conteo_servicio.items(), key=lambda kv: kv[1])[0]

    return HistorialClienteResponse(
        cliente_id=cli.id, nombre=cli.nombre,
        total_citas=len(citas), total_gastado=round(gastado, 2),
        ticket_promedio=round(gastado / len(completadas), 2) if completadas else 0,
        saldo_pendiente=round(max(saldo, 0), 2),
        dias_desde_ultima=(_ahora() - ultima).days if ultima else None,
        servicio_favorito=favorito,
        citas=[HistorialCitaCliente(
            id=c.id, codigo=c.codigo, fecha_inicio=c.fecha_inicio, estado=c.estado,
            profesional=profs.get(c.profesional_id),
            servicios=", ".join(lineas.get(c.id, [])),
            total=float(c.total or 0), total_pagado=float(c.total_pagado or 0),
            medio_pago=c.medio_pago,
        ) for c in citas],
    )

# ──────────────────────────────────────────
# AGENDA / DISPONIBILIDAD
# ──────────────────────────────────────────

class SlotDisponible(BaseModel):
    hora_inicio: str
    hora_fin: str
    inicio: datetime
    fin: datetime


class DisponibilidadProfesional(BaseModel):
    profesional_id: int
    profesional: str
    color: Optional[str] = None
    trabaja: bool = True
    motivo_no_disponible: Optional[str] = None
    jornada: List[str] = []
    slots: List[SlotDisponible] = []
    minutos_disponibles: int = 0
    minutos_ocupados: int = 0
    ocupacion_pct: float = 0


def _fusionar(intervalos: List[tuple]) -> List[tuple]:
    """Une intervalos (inicio_min, fin_min) que se solapan."""
    if not intervalos:
        return []
    ordenados = sorted(intervalos)
    salida = [ordenados[0]]
    for ini, fin in ordenados[1:]:
        ult_ini, ult_fin = salida[-1]
        if ini <= ult_fin:
            salida[-1] = (ult_ini, max(ult_fin, fin))
        else:
            salida.append((ini, fin))
    return salida


@router.get("/agenda/disponibilidad", response_model=List[DisponibilidadProfesional])
async def disponibilidad(
    fecha: date,
    duracion_min: int = 30,
    profesional_id: Optional[int] = None,
    servicio_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Horas realmente libres para agendar en una fecha.

    Parte de la jornada de cada profesional, le resta las citas ya tomadas y
    las ausencias, y devuelve solo los espacios donde cabe completo un servicio
    de la duracion pedida. Es lo que permite ofrecer horarios sin sobrevender.
    """
    cfg = await _get_config(db)
    if servicio_id is not None:
        srv = await db.get(AGSServicio, servicio_id)
        if srv is None:
            raise HTTPException(404, "Servicio no encontrado")
        duracion_min = int(srv.duracion_min or duracion_min)
    if duracion_min <= 0:
        raise HTTPException(400, "La duracion debe ser mayor a cero.")

    paso = max(int(cfg.intervalo_agenda_min or 30), 5)
    dia = _dia_semana(fecha)

    # Profesionales candidatos: activos y, si se pidio un servicio concreto,
    # solo los que lo saben prestar (si alguien lo tiene asignado).
    q = select(AGSProfesional).where(AGSProfesional.activo == True)
    if profesional_id is not None:
        q = q.where(AGSProfesional.id == profesional_id)
    r = await db.execute(q.order_by(AGSProfesional.nombre))
    profesionales = r.scalars().all()

    if servicio_id is not None and profesionales:
        rs = await db.execute(select(AGSProfesionalServicio.profesional_id).where(
            AGSProfesionalServicio.servicio_id == servicio_id))
        capacitados = {pid for (pid,) in rs.all()}
        # Si nadie tiene el servicio asignado, se asume que todos pueden prestarlo
        if capacitados:
            profesionales = [p for p in profesionales if p.id in capacitados]

    if not profesionales:
        return []

    ids = [p.id for p in profesionales]

    # Jornada del dia
    rh = await db.execute(select(AGSHorarioProfesional).where(
        AGSHorarioProfesional.profesional_id.in_(ids),
        AGSHorarioProfesional.dia_semana == dia,
        AGSHorarioProfesional.activo == True,
    ).order_by(AGSHorarioProfesional.hora_inicio))
    franjas: Dict[int, List[tuple]] = {}
    etiquetas: Dict[int, List[str]] = {}
    for h in rh.scalars().all():
        ini, fin = _hhmm_a_min(h.hora_inicio), _hhmm_a_min(h.hora_fin)
        if ini is None or fin is None or fin <= ini:
            continue
        franjas.setdefault(h.profesional_id, []).append((ini, fin))
        etiquetas.setdefault(h.profesional_id, []).append("%s - %s" % (h.hora_inicio, h.hora_fin))

    dia_inicio = datetime(fecha.year, fecha.month, fecha.day)
    dia_fin = dia_inicio + timedelta(days=1)

    # Citas del dia que ocupan agenda
    rc = await db.execute(select(AGSCita).where(
        AGSCita.profesional_id.in_(ids),
        AGSCita.estado.in_(ESTADOS_ACTIVOS),
        AGSCita.fecha_inicio < dia_fin,
        AGSCita.fecha_fin > dia_inicio,
    ))
    ocupado: Dict[int, List[tuple]] = {}
    for c in rc.scalars().all():
        ini = _sin_tz(c.fecha_inicio)
        fin = _sin_tz(c.fecha_fin)
        ini_min = max(0, int((ini - dia_inicio).total_seconds() // 60))
        fin_min = min(1440, int((fin - dia_inicio).total_seconds() // 60))
        if fin_min > ini_min:
            ocupado.setdefault(c.profesional_id, []).append((ini_min, fin_min))

    # Ausencias del dia (propias o cierre general)
    ra = await db.execute(select(AGSAusencia).where(
        AGSAusencia.fecha_inicio < dia_fin, AGSAusencia.fecha_fin > dia_inicio,
    ))
    ausencias_dia = ra.scalars().all()
    cierre_general: List[tuple] = []
    for a in ausencias_dia:
        ini = max(_sin_tz(a.fecha_inicio), dia_inicio)
        fin = min(_sin_tz(a.fecha_fin), dia_fin)
        rango = (int((ini - dia_inicio).total_seconds() // 60),
                 int((fin - dia_inicio).total_seconds() // 60))
        if rango[1] <= rango[0]:
            continue
        if a.profesional_id is None:
            cierre_general.append(rango)
        else:
            ocupado.setdefault(a.profesional_id, []).append(rango)

    # El negocio puede no atender ese dia de la semana
    dias_habiles = cfg.dias_laborales or [1, 2, 3, 4, 5, 6]
    negocio_cerrado = dia not in dias_habiles

    # No ofrecer horas ya pasadas (ni dentro de la anticipacion minima)
    ahora = _ahora()
    piso_min = 0
    if fecha == ahora.date():
        piso_min = ahora.hour * 60 + ahora.minute + int(cfg.anticipacion_minima_min or 0)

    salida: List[DisponibilidadProfesional] = []
    for p in profesionales:
        item = DisponibilidadProfesional(
            profesional_id=p.id, profesional=p.nombre, color=p.color,
            jornada=etiquetas.get(p.id, []),
        )
        mis_franjas = franjas.get(p.id, [])
        if negocio_cerrado:
            item.trabaja = False
            item.motivo_no_disponible = "El negocio no atiende este dia"
        elif not mis_franjas:
            item.trabaja = False
            item.motivo_no_disponible = "Sin jornada configurada para este dia"

        ocupados_p = _fusionar(ocupado.get(p.id, []) + cierre_general)
        item.minutos_ocupados = sum(f - i for i, f in ocupados_p)

        if item.trabaja:
            for f_ini, f_fin in _fusionar(mis_franjas):
                t = f_ini
                # alinear al paso de la agenda
                if t % paso:
                    t += paso - (t % paso)
                while t + duracion_min <= f_fin:
                    if t >= piso_min and not any(
                        t < o_fin and (t + duracion_min) > o_ini for o_ini, o_fin in ocupados_p
                    ):
                        item.slots.append(SlotDisponible(
                            hora_inicio=_min_a_hhmm(t),
                            hora_fin=_min_a_hhmm(t + duracion_min),
                            inicio=dia_inicio + timedelta(minutes=t),
                            fin=dia_inicio + timedelta(minutes=t + duracion_min),
                        ))
                    t += paso

        minutos_jornada = sum(f - i for i, f in _fusionar(mis_franjas))
        item.minutos_disponibles = len(item.slots) * duracion_min
        item.ocupacion_pct = round(item.minutos_ocupados / minutos_jornada * 100, 1) \
            if minutos_jornada > 0 else 0
        salida.append(item)
    return salida


# ──────────────────────────────────────────
# CITAS
# ──────────────────────────────────────────

class LineaServicioIn(BaseModel):
    servicio_id: Optional[int] = None
    nombre_servicio: Optional[str] = None
    cantidad: float = 1
    precio_unitario: Optional[float] = None
    duracion_min: Optional[int] = None


class LineaServicioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    servicio_id: Optional[int] = None
    nombre_servicio: str
    cantidad: float
    precio_unitario: float
    subtotal: float
    duracion_min: int


class LineaMaterialIn(BaseModel):
    descripcion: str
    cantidad: float = 1
    precio_unitario: float = 0


class LineaMaterialResponse(LineaMaterialIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subtotal: float


class PagoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha: datetime
    monto: float
    medio_pago: Optional[str] = None
    tipo: Optional[str] = None
    referencia: Optional[str] = None
    notas: Optional[str] = None


class CitaCreate(BaseModel):
    cliente_id: int
    profesional_id: int
    fecha_inicio: datetime
    servicios: List[LineaServicioIn]
    lugar: Optional[str] = LugarServicioEnum.LOCAL.value
    direccion_servicio: Optional[str] = None
    origen: Optional[str] = OrigenCitaEnum.MOSTRADOR.value
    descuento: Optional[float] = 0
    descuento_motivo: Optional[str] = None
    notas: Optional[str] = None
    creado_por: Optional[str] = None
    estado: Optional[str] = None


class CitaUpdate(BaseModel):
    cliente_id: Optional[int] = None
    profesional_id: Optional[int] = None
    fecha_inicio: Optional[datetime] = None
    servicios: Optional[List[LineaServicioIn]] = None
    materiales: Optional[List[LineaMaterialIn]] = None
    lugar: Optional[str] = None
    direccion_servicio: Optional[str] = None
    descuento: Optional[float] = None
    descuento_motivo: Optional[str] = None
    propina: Optional[float] = None
    notas: Optional[str] = None


class CitaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    cliente_id: int
    cliente: Optional[str] = None
    cliente_telefono: Optional[str] = None
    profesional_id: int
    profesional: Optional[str] = None
    profesional_color: Optional[str] = None
    fecha_inicio: datetime
    fecha_fin: datetime
    duracion_min: int
    lugar: Optional[str] = None
    direccion_servicio: Optional[str] = None
    estado: str
    origen: Optional[str] = None
    subtotal: float = 0
    descuento: float = 0
    descuento_motivo: Optional[str] = None
    total_materiales: float = 0
    propina: float = 0
    total: float = 0
    pagado: bool = False
    total_pagado: float = 0
    saldo: float = 0
    medio_pago: Optional[str] = None
    fecha_pago: Optional[datetime] = None
    comision_profesional: float = 0
    iva_incluido: float = 0
    notas: Optional[str] = None
    motivo_cancelacion: Optional[str] = None
    recordatorio_enviado: bool = False
    servicios_texto: str = ""
    servicios: List[LineaServicioResponse] = []
    materiales: List[LineaMaterialResponse] = []
    pagos: List[PagoResponse] = []


async def _armar_respuesta(db: AsyncSession, cita: AGSCita, detalle: bool = True) -> CitaResponse:
    item = CitaResponse.model_validate(cita)
    cli = await db.get(AGSCliente, cita.cliente_id)
    pro = await db.get(AGSProfesional, cita.profesional_id)
    item.cliente = cli.nombre if cli else None
    item.cliente_telefono = cli.telefono if cli else None
    item.profesional = pro.nombre if pro else None
    item.profesional_color = pro.color if pro else None
    item.saldo = round(float(cita.total or 0) - float(cita.total_pagado or 0), 2)

    rs = await db.execute(select(AGSCitaServicio).where(AGSCitaServicio.cita_id == cita.id))
    lineas = rs.scalars().all()
    item.servicios_texto = ", ".join(l.nombre_servicio for l in lineas)
    if detalle:
        item.servicios = [LineaServicioResponse.model_validate(l) for l in lineas]
        rm = await db.execute(select(AGSCitaMaterial).where(AGSCitaMaterial.cita_id == cita.id))
        item.materiales = [LineaMaterialResponse.model_validate(m) for m in rm.scalars().all()]
        rp = await db.execute(select(AGSPagoCita).where(AGSPagoCita.cita_id == cita.id)
                              .order_by(AGSPagoCita.fecha))
        item.pagos = [PagoResponse.model_validate(p) for p in rp.scalars().all()]
    return item


async def _construir_lineas(db: AsyncSession, cita_id: int,
                            servicios: List[LineaServicioIn]) -> List[AGSCitaServicio]:
    """Crea las lineas de servicio tomando precio y duracion del catalogo.

    El precio se puede sobreescribir por linea (un descuento puntual o un
    trabajo cotizado aparte), pero por defecto manda lo preconfigurado.
    """
    if not servicios:
        raise HTTPException(400, "La cita debe incluir al menos un servicio.")
    lineas = []
    for entrada in servicios:
        nombre = (entrada.nombre_servicio or "").strip()
        precio = entrada.precio_unitario
        duracion = entrada.duracion_min
        comision_pct = None

        if entrada.servicio_id is not None:
            srv = await db.get(AGSServicio, entrada.servicio_id)
            if srv is None:
                raise HTTPException(404, "El servicio %s no existe." % entrada.servicio_id)
            if not srv.activo:
                raise HTTPException(400, "El servicio '%s' esta desactivado." % srv.nombre)
            nombre = nombre or srv.nombre
            precio = precio if precio is not None else float(srv.precio or 0)
            duracion = duracion if duracion is not None else int(srv.duracion_min or 0)
            comision_pct = srv.comision_pct
        if not nombre:
            raise HTTPException(400, "Cada linea necesita un servicio del catalogo o un nombre.")
        if precio is None:
            precio = 0.0
        if duracion is None:
            duracion = 0

        cantidad = float(entrada.cantidad or 1)
        lineas.append(AGSCitaServicio(
            cita_id=cita_id, servicio_id=entrada.servicio_id, nombre_servicio=nombre,
            cantidad=cantidad, precio_unitario=float(precio),
            subtotal=round(float(precio) * cantidad, 2),
            duracion_min=int(duracion * cantidad), comision_pct=comision_pct,
        ))
    return lineas


@router.get("/citas", response_model=List[CitaResponse])
async def listar_citas(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    profesional_id: Optional[int] = None,
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    solo_pendientes_pago: bool = False,
    limite: int = 2000,
    db: AsyncSession = Depends(get_db),
):
    q = select(AGSCita)
    if desde is not None:
        q = q.where(AGSCita.fecha_fin >= desde)
    if hasta is not None:
        q = q.where(AGSCita.fecha_inicio <= hasta)
    if profesional_id is not None:
        q = q.where(AGSCita.profesional_id == profesional_id)
    if cliente_id is not None:
        q = q.where(AGSCita.cliente_id == cliente_id)
    if estado:
        q = q.where(AGSCita.estado == estado)
    if solo_pendientes_pago:
        q = q.where(AGSCita.estado == EstadoCitaEnum.COMPLETADA.value,
                    AGSCita.pagado == False)
    r = await db.execute(q.order_by(AGSCita.fecha_inicio.desc()).limit(limite))
    citas = r.scalars().all()
    if not citas:
        return []

    # Enriquecer en lote para no disparar una consulta por cita
    rc = await db.execute(select(AGSCliente))
    clientes = {c.id: c for c in rc.scalars().all()}
    rp = await db.execute(select(AGSProfesional))
    profs = {p.id: p for p in rp.scalars().all()}
    rs = await db.execute(select(AGSCitaServicio).where(
        AGSCitaServicio.cita_id.in_([c.id for c in citas])))
    lineas: Dict[int, List[str]] = {}
    for l in rs.scalars().all():
        lineas.setdefault(l.cita_id, []).append(l.nombre_servicio)

    salida = []
    for c in citas:
        item = CitaResponse.model_validate(c)
        cli = clientes.get(c.cliente_id)
        pro = profs.get(c.profesional_id)
        item.cliente = cli.nombre if cli else None
        item.cliente_telefono = cli.telefono if cli else None
        item.profesional = pro.nombre if pro else None
        item.profesional_color = pro.color if pro else None
        item.saldo = round(float(c.total or 0) - float(c.total_pagado or 0), 2)
        item.servicios_texto = ", ".join(lineas.get(c.id, []))
        salida.append(item)
    return salida


@router.get("/citas/{cid}", response_model=CitaResponse)
async def obtener_cita(cid: int, db: AsyncSession = Depends(get_db)):
    cita = await db.get(AGSCita, cid)
    if cita is None:
        raise HTTPException(404, "Cita no encontrada")
    return await _armar_respuesta(db, cita)


@router.post("/citas", response_model=CitaResponse, status_code=201)
async def crear_cita(data: CitaCreate, db: AsyncSession = Depends(get_db)):
    """Agenda una cita validando que el horario este realmente libre."""
    cfg = await _get_config(db)

    cli = await db.get(AGSCliente, data.cliente_id)
    if cli is None:
        raise HTTPException(404, "Cliente no encontrado")
    pro = await db.get(AGSProfesional, data.profesional_id)
    if pro is None:
        raise HTTPException(404, "Profesional no encontrado")
    if not pro.activo:
        raise HTTPException(400, "El profesional '%s' esta inactivo." % pro.nombre)

    inicio = _sin_tz(data.fecha_inicio)
    if data.lugar == LugarServicioEnum.DOMICILIO.value and not (
        data.direccion_servicio or cli.direccion
    ):
        raise HTTPException(400, "Un servicio a domicilio necesita direccion: "
                                 "indiquela en la cita o en la ficha del cliente.")

    cita = AGSCita(
        codigo=await _siguiente_codigo(db, AGSCita, "CITA", 5),
        cliente_id=data.cliente_id, profesional_id=data.profesional_id,
        fecha_inicio=inicio, fecha_fin=inicio + timedelta(minutes=30), duracion_min=30,
        lugar=data.lugar or LugarServicioEnum.LOCAL.value,
        direccion_servicio=data.direccion_servicio or (
            cli.direccion if data.lugar == LugarServicioEnum.DOMICILIO.value else None),
        estado=data.estado or EstadoCitaEnum.AGENDADA.value,
        origen=data.origen or OrigenCitaEnum.MOSTRADOR.value,
        descuento=float(data.descuento or 0), descuento_motivo=data.descuento_motivo,
        notas=data.notas, creado_por=data.creado_por,
    )
    db.add(cita)
    await db.flush()

    lineas = await _construir_lineas(db, cita.id, data.servicios)
    for l in lineas:
        db.add(l)
    _recalcular_totales(cita, lineas, [], float(pro.comision_pct or cfg.comision_defecto_pct or 0),
                        float(cfg.iva_pct or 0))

    # Se excluye a si misma: el flush anterior ya la dejo visible en la
    # transaccion y sin esto la cita choca contra su propio registro.
    await _validar_disponibilidad(
        db, data.profesional_id, cita.fecha_inicio, cita.fecha_fin,
        excluir_cita_id=cita.id, permite_sobrecupo=bool(cfg.permite_sobrecupo),
    )

    await db.commit()
    await db.refresh(cita)
    return await _armar_respuesta(db, cita)


@router.put("/citas/{cid}", response_model=CitaResponse)
async def actualizar_cita(cid: int, data: CitaUpdate, db: AsyncSession = Depends(get_db)):
    """Reprograma o reajusta la cita. Vuelve a validar el cruce de horarios."""
    cita = await db.get(AGSCita, cid)
    if cita is None:
        raise HTTPException(404, "Cita no encontrada")
    if cita.estado in (EstadoCitaEnum.CANCELADA.value, EstadoCitaEnum.NO_ASISTIO.value):
        raise HTTPException(409, "La cita esta %s: no se puede modificar." % cita.estado.lower())
    if cita.pagado:
        raise HTTPException(409, "La cita ya esta pagada. Anule el pago antes de modificarla.")

    cfg = await _get_config(db)
    valores = data.model_dump(exclude_unset=True)
    servicios_in = valores.pop("servicios", None)
    materiales_in = valores.pop("materiales", None)

    if "fecha_inicio" in valores and valores["fecha_inicio"] is not None:
        valores["fecha_inicio"] = _sin_tz(valores["fecha_inicio"])
    for k, v in valores.items():
        setattr(cita, k, v)

    pro = await db.get(AGSProfesional, cita.profesional_id)
    if pro is None:
        raise HTTPException(404, "Profesional no encontrado")

    if servicios_in is not None:
        await db.execute(delete(AGSCitaServicio).where(AGSCitaServicio.cita_id == cid))
        lineas = await _construir_lineas(db, cid, [LineaServicioIn(**s) for s in servicios_in])
        for l in lineas:
            db.add(l)
    else:
        rs = await db.execute(select(AGSCitaServicio).where(AGSCitaServicio.cita_id == cid))
        lineas = list(rs.scalars().all())

    if materiales_in is not None:
        await db.execute(delete(AGSCitaMaterial).where(AGSCitaMaterial.cita_id == cid))
        materiales = []
        for m in materiales_in:
            entrada = LineaMaterialIn(**m)
            obj = AGSCitaMaterial(
                cita_id=cid, descripcion=entrada.descripcion,
                cantidad=float(entrada.cantidad or 1),
                precio_unitario=float(entrada.precio_unitario or 0),
                subtotal=round(float(entrada.precio_unitario or 0) * float(entrada.cantidad or 1), 2),
            )
            db.add(obj)
            materiales.append(obj)
    else:
        rm = await db.execute(select(AGSCitaMaterial).where(AGSCitaMaterial.cita_id == cid))
        materiales = list(rm.scalars().all())

    _recalcular_totales(cita, lineas, materiales,
                        float(pro.comision_pct or cfg.comision_defecto_pct or 0),
                        float(cfg.iva_pct or 0))

    await _validar_disponibilidad(
        db, cita.profesional_id, cita.fecha_inicio, cita.fecha_fin,
        excluir_cita_id=cid, permite_sobrecupo=bool(cfg.permite_sobrecupo),
    )

    await db.commit()
    await db.refresh(cita)
    return await _armar_respuesta(db, cita)


# Transiciones validas del ciclo de vida de la cita
TRANSICIONES = {
    EstadoCitaEnum.AGENDADA.value:   [EstadoCitaEnum.CONFIRMADA.value, EstadoCitaEnum.EN_CURSO.value,
                                      EstadoCitaEnum.CANCELADA.value, EstadoCitaEnum.NO_ASISTIO.value],
    EstadoCitaEnum.CONFIRMADA.value: [EstadoCitaEnum.EN_CURSO.value, EstadoCitaEnum.CANCELADA.value,
                                      EstadoCitaEnum.NO_ASISTIO.value],
    EstadoCitaEnum.EN_CURSO.value:   [EstadoCitaEnum.COMPLETADA.value, EstadoCitaEnum.CANCELADA.value],
    EstadoCitaEnum.COMPLETADA.value: [],
    EstadoCitaEnum.CANCELADA.value:  [],
    EstadoCitaEnum.NO_ASISTIO.value: [],
}


class CambioEstadoCita(BaseModel):
    estado: str
    motivo: Optional[str] = None


@router.post("/citas/{cid}/estado", response_model=CitaResponse)
async def cambiar_estado_cita(cid: int, data: CambioEstadoCita, db: AsyncSession = Depends(get_db)):
    """Avanza la cita por su ciclo de vida respetando las transiciones validas.

    Completar exige que la cita este cobrada: es el punto donde el trabajo se
    convierte en ingreso, y dejarlo pasar sin pago descuadra la caja.
    """
    cita = await db.get(AGSCita, cid)
    if cita is None:
        raise HTTPException(404, "Cita no encontrada")

    destino = (data.estado or "").upper()
    if destino not in TRANSICIONES:
        raise HTTPException(400, "Estado '%s' no valido." % data.estado)
    permitidos = TRANSICIONES.get(cita.estado, [])
    if destino not in permitidos:
        if not permitidos:
            raise HTTPException(409, "La cita esta %s: es un estado final." % cita.estado.lower())
        raise HTTPException(409, "No se puede pasar de %s a %s. Estados posibles: %s."
                                 % (cita.estado, destino, ", ".join(permitidos)))

    ahora = _ahora()
    if destino == EstadoCitaEnum.NO_ASISTIO.value:
        # La tolerancia de espera de la configuración: antes de que pase, el
        # cliente todavía puede llegar y marcarlo ausente sería un error que
        # además le cuenta como inasistencia en su historial.
        cfg = await _get_config(db)
        limite = _sin_tz(cita.fecha_inicio) + timedelta(minutes=int(cfg.tolerancia_no_show_min or 0))
        if ahora < limite:
            raise HTTPException(409, "Aún está dentro de la tolerancia de espera (%d min): "
                                     "se puede marcar la inasistencia desde las %s."
                                     % (cfg.tolerancia_no_show_min or 0, limite.strftime("%H:%M")))
    if destino == EstadoCitaEnum.EN_CURSO.value:
        cita.hora_llegada = cita.hora_llegada or ahora
        cita.hora_inicio_real = ahora
    elif destino == EstadoCitaEnum.COMPLETADA.value:
        if not cita.pagado:
            raise HTTPException(409, "Registre el cobro antes de completar la cita: "
                                     "use la accion Cobrar.")
        cita.hora_fin_real = ahora
    elif destino in (EstadoCitaEnum.CANCELADA.value, EstadoCitaEnum.NO_ASISTIO.value):
        cita.motivo_cancelacion = data.motivo

    cita.estado = destino
    await db.commit()
    await db.refresh(cita)
    return await _armar_respuesta(db, cita)


class CobroCita(BaseModel):
    medio_pago: str = MedioPagoEnum.EFECTIVO.value
    monto: Optional[float] = None          # por defecto el saldo completo
    propina: Optional[float] = None
    descuento: Optional[float] = None
    descuento_motivo: Optional[str] = None
    materiales: Optional[List[LineaMaterialIn]] = None
    referencia: Optional[str] = None
    notas: Optional[str] = None
    registrado_por: Optional[str] = None
    completar: bool = True


@router.post("/citas/{cid}/cobrar", response_model=CitaResponse)
async def cobrar_cita(cid: int, data: CobroCita, db: AsyncSession = Depends(get_db)):
    """Cobra la cita: registra el pago, liquida la comision y la completa.

    Permite ajustar en el mismo paso la propina, el descuento y los materiales
    consumidos, porque en la practica esos tres se conocen solo al terminar
    de atender.
    """
    cita = await db.get(AGSCita, cid)
    if cita is None:
        raise HTTPException(404, "Cita no encontrada")
    if cita.estado in (EstadoCitaEnum.CANCELADA.value, EstadoCitaEnum.NO_ASISTIO.value):
        raise HTTPException(409, "La cita esta %s: no se puede cobrar." % cita.estado.lower())

    cfg = await _get_config(db)
    pro = await db.get(AGSProfesional, cita.profesional_id)

    if data.propina is not None:
        cita.propina = float(data.propina)
    if data.descuento is not None:
        cita.descuento = float(data.descuento)
        cita.descuento_motivo = data.descuento_motivo

    if data.materiales is not None:
        await db.execute(delete(AGSCitaMaterial).where(AGSCitaMaterial.cita_id == cid))
        materiales = []
        for entrada in data.materiales:
            obj = AGSCitaMaterial(
                cita_id=cid, descripcion=entrada.descripcion,
                cantidad=float(entrada.cantidad or 1),
                precio_unitario=float(entrada.precio_unitario or 0),
                subtotal=round(float(entrada.precio_unitario or 0) * float(entrada.cantidad or 1), 2),
            )
            db.add(obj)
            materiales.append(obj)
    else:
        rm = await db.execute(select(AGSCitaMaterial).where(AGSCitaMaterial.cita_id == cid))
        materiales = list(rm.scalars().all())

    rs = await db.execute(select(AGSCitaServicio).where(AGSCitaServicio.cita_id == cid))
    lineas = list(rs.scalars().all())
    _recalcular_totales(cita, lineas, materiales,
                        float((pro.comision_pct if pro else 0) or cfg.comision_defecto_pct or 0),
                        float(cfg.iva_pct or 0))

    if float(cita.descuento or 0) > float(cita.subtotal or 0) + float(cita.total_materiales or 0):
        raise HTTPException(400, "El descuento no puede superar el valor del servicio.")

    ya_pagado = float(cita.total_pagado or 0)
    saldo = round(float(cita.total or 0) - ya_pagado, 2)
    monto = float(data.monto) if data.monto is not None else saldo
    if monto <= 0:
        raise HTTPException(400, "El monto a cobrar debe ser mayor a cero. "
                                 "Saldo actual: %.2f" % saldo)
    if monto > saldo + 0.01:
        raise HTTPException(400, "El monto (%.2f) supera el saldo pendiente (%.2f)."
                                 % (monto, saldo))

    ahora = _ahora()
    db.add(AGSPagoCita(
        cita_id=cid, fecha=ahora, monto=round(monto, 2),
        medio_pago=data.medio_pago, tipo=TipoPagoEnum.PAGO.value,
        referencia=data.referencia, notas=data.notas, registrado_por=data.registrado_por,
    ))

    cita.total_pagado = round(ya_pagado + monto, 2)
    cita.medio_pago = data.medio_pago
    cita.pagado = cita.total_pagado >= round(float(cita.total or 0), 2) - 0.01
    if cita.pagado:
        cita.fecha_pago = ahora
        if data.completar and cita.estado != EstadoCitaEnum.COMPLETADA.value:
            cita.estado = EstadoCitaEnum.COMPLETADA.value
            cita.hora_fin_real = ahora

    await db.commit()
    await db.refresh(cita)
    return await _armar_respuesta(db, cita)


class AbonoCita(BaseModel):
    monto: float
    medio_pago: str = MedioPagoEnum.EFECTIVO.value
    referencia: Optional[str] = None
    notas: Optional[str] = None
    registrado_por: Optional[str] = None


@router.post("/citas/{cid}/abonos", response_model=CitaResponse)
async def registrar_abono(cid: int, data: AbonoCita, db: AsyncSession = Depends(get_db)):
    """Anticipo antes de terminar el trabajo (obras, tratamientos largos)."""
    cita = await db.get(AGSCita, cid)
    if cita is None:
        raise HTTPException(404, "Cita no encontrada")
    if data.monto <= 0:
        raise HTTPException(400, "El abono debe ser mayor a cero.")
    saldo = round(float(cita.total or 0) - float(cita.total_pagado or 0), 2)
    if data.monto > saldo + 0.01:
        raise HTTPException(400, "El abono (%.2f) supera el saldo pendiente (%.2f)."
                                 % (data.monto, saldo))

    db.add(AGSPagoCita(
        cita_id=cid, fecha=_ahora(), monto=round(float(data.monto), 2),
        medio_pago=data.medio_pago, tipo=TipoPagoEnum.ANTICIPO.value,
        referencia=data.referencia, notas=data.notas, registrado_por=data.registrado_por,
    ))
    cita.total_pagado = round(float(cita.total_pagado or 0) + float(data.monto), 2)
    cita.pagado = cita.total_pagado >= round(float(cita.total or 0), 2) - 0.01
    await db.commit()
    await db.refresh(cita)
    return await _armar_respuesta(db, cita)


@router.delete("/citas/{cid}", status_code=204)
async def eliminar_cita(cid: int, db: AsyncSession = Depends(get_db)):
    """Borra la cita. Solo si no movio dinero: lo cobrado no se borra, se cancela."""
    cita = await db.get(AGSCita, cid)
    if cita is None:
        raise HTTPException(404, "Cita no encontrada")
    if float(cita.total_pagado or 0) > 0:
        raise HTTPException(409, "La cita tiene pagos registrados. "
                                 "Cancelela en lugar de borrarla para no perder el rastro.")
    await db.delete(cita)
    await db.commit()


class RecordatorioResponse(BaseModel):
    cita_id: int
    cliente: str
    telefono: Optional[str] = None
    mensaje: str
    enlace_whatsapp: Optional[str] = None


@router.post("/citas/{cid}/recordatorio", response_model=RecordatorioResponse)
async def generar_recordatorio(cid: int, db: AsyncSession = Depends(get_db)):
    """Arma el mensaje de recordatorio y el enlace de WhatsApp para enviarlo.

    No envia nada por si mismo: entrega el enlace wa.me listo para abrir, que
    es como estos negocios confirman citas en la practica.
    """
    cita = await db.get(AGSCita, cid)
    if cita is None:
        raise HTTPException(404, "Cita no encontrada")
    cfg = await _get_config(db)
    cli = await db.get(AGSCliente, cita.cliente_id)
    if cli is None:
        raise HTTPException(404, "Cliente no encontrado")

    rs = await db.execute(select(AGSCitaServicio).where(AGSCitaServicio.cita_id == cid))
    servicios = ", ".join(l.nombre_servicio for l in rs.scalars().all())
    inicio = _sin_tz(cita.fecha_inicio)

    plantilla = cfg.mensaje_recordatorio or "Hola {cliente}, le recordamos su cita."
    mensaje = (plantilla
               .replace("{cliente}", cli.nombre)
               .replace("{negocio}", cfg.nombre_negocio or "")
               .replace("{fecha}", inicio.strftime("%d/%m/%Y"))
               .replace("{hora}", inicio.strftime("%I:%M %p").lstrip("0"))
               .replace("{servicio}", servicios or "su servicio")
               .replace("{codigo}", cita.codigo)
               .replace("{total}", "{:,.0f}".format(float(cita.total or 0))))

    enlace = None
    if cli.telefono:
        from urllib.parse import quote
        solo_digitos = "".join(ch for ch in cli.telefono if ch.isdigit())
        if solo_digitos:
            # Colombia: si viene sin indicativo se le agrega el 57
            if len(solo_digitos) == 10:
                solo_digitos = "57" + solo_digitos
            enlace = "https://wa.me/%s?text=%s" % (solo_digitos, quote(mensaje))

    cita.recordatorio_enviado = True
    await db.commit()

    return RecordatorioResponse(
        cita_id=cid, cliente=cli.nombre, telefono=cli.telefono,
        mensaje=mensaje, enlace_whatsapp=enlace,
    )

# ──────────────────────────────────────────
# REPORTES DE INGRESOS
# ──────────────────────────────────────────

class PuntoIngreso(BaseModel):
    periodo: str
    fecha: date
    citas: int = 0
    servicios: float = 0
    materiales: float = 0
    descuentos: float = 0
    propinas: float = 0
    total: float = 0
    comisiones: float = 0
    utilidad: float = 0


class ResumenIngresos(BaseModel):
    desde: date
    hasta: date
    agrupar: str
    citas_completadas: int = 0
    citas_canceladas: int = 0
    citas_no_asistio: int = 0
    total_servicios: float = 0
    total_materiales: float = 0
    total_descuentos: float = 0
    total_propinas: float = 0
    total_ingresos: float = 0
    total_iva: float = 0
    total_comisiones: float = 0
    utilidad_bruta: float = 0
    ticket_promedio: float = 0
    por_cobrar: float = 0
    tasa_no_show_pct: float = 0
    serie: List[PuntoIngreso] = []


def _clave_periodo(f: date, agrupar: str) -> tuple:
    """Devuelve (etiqueta, fecha_representativa) del periodo que contiene f."""
    if agrupar == "mes":
        return ("%04d-%02d" % (f.year, f.month), date(f.year, f.month, 1))
    if agrupar == "semana":
        lunes = f - timedelta(days=f.weekday())
        return (lunes.strftime("Sem %d/%m"), lunes)
    return (f.strftime("%d/%m"), f)


@router.get("/reportes/ingresos", response_model=ResumenIngresos)
async def reporte_ingresos(
    desde: date, hasta: date,
    agrupar: str = "dia",
    profesional_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Ingresos del periodo con su serie de tiempo.

    Solo cuenta las citas completadas: agendar no es facturar. Las canceladas
    y las inasistencias se reportan aparte porque miden otra cosa (la fuga de
    agenda), no el ingreso.
    """
    if agrupar not in ("dia", "semana", "mes"):
        raise HTTPException(400, "El agrupamiento debe ser dia, semana o mes.")
    if hasta < desde:
        raise HTTPException(400, "La fecha final no puede ser anterior a la inicial.")

    ini = datetime(desde.year, desde.month, desde.day)
    fin = datetime(hasta.year, hasta.month, hasta.day) + timedelta(days=1)

    q = select(AGSCita).where(AGSCita.fecha_inicio >= ini, AGSCita.fecha_inicio < fin)
    if profesional_id is not None:
        q = q.where(AGSCita.profesional_id == profesional_id)
    r = await db.execute(q)
    citas = r.scalars().all()

    # Costo de insumos del catalogo para estimar la utilidad real
    rs = await db.execute(select(AGSServicio))
    costo_srv = {x.id: float(x.costo_insumos or 0) for x in rs.scalars().all()}
    lineas_por_cita: Dict[int, List[AGSCitaServicio]] = {}
    if citas:
        rl = await db.execute(select(AGSCitaServicio).where(
            AGSCitaServicio.cita_id.in_([c.id for c in citas])))
        for l in rl.scalars().all():
            lineas_por_cita.setdefault(l.cita_id, []).append(l)

    resumen = ResumenIngresos(desde=desde, hasta=hasta, agrupar=agrupar)
    buckets: Dict[str, PuntoIngreso] = {}

    for c in citas:
        if c.estado == EstadoCitaEnum.CANCELADA.value:
            resumen.citas_canceladas += 1
            continue
        if c.estado == EstadoCitaEnum.NO_ASISTIO.value:
            resumen.citas_no_asistio += 1
            continue
        if c.estado not in ESTADOS_FACTURABLES:
            continue

        resumen.citas_completadas += 1
        etiqueta, fecha_rep = _clave_periodo(_sin_tz(c.fecha_inicio).date(), agrupar)
        p = buckets.get(etiqueta)
        if p is None:
            p = PuntoIngreso(periodo=etiqueta, fecha=fecha_rep)
            buckets[etiqueta] = p

        servicios = float(c.subtotal or 0)
        materiales = float(c.total_materiales or 0)
        descuento = float(c.descuento or 0)
        propina = float(c.propina or 0)
        total = float(c.total or 0)
        comision = float(c.comision_profesional or 0)
        iva = float(c.iva_incluido or 0)
        insumos = sum(costo_srv.get(l.servicio_id, 0) * float(l.cantidad or 1)
                      for l in lineas_por_cita.get(c.id, []))

        p.citas += 1
        p.servicios += servicios
        p.materiales += materiales
        p.descuentos += descuento
        p.propinas += propina
        p.total += total
        p.comisiones += comision
        # La propina no es del negocio ni el IVA tampoco: se descuentan de la utilidad
        p.utilidad += total - comision - insumos - propina - iva

        resumen.total_servicios += servicios
        resumen.total_materiales += materiales
        resumen.total_descuentos += descuento
        resumen.total_propinas += propina
        resumen.total_ingresos += total
        resumen.total_comisiones += comision
        resumen.total_iva += iva
        resumen.utilidad_bruta += total - comision - insumos - propina - iva
        resumen.por_cobrar += total - float(c.total_pagado or 0)

    for p in buckets.values():
        for campo in ("servicios", "materiales", "descuentos", "propinas",
                      "total", "comisiones", "utilidad"):
            setattr(p, campo, round(getattr(p, campo), 2))
    for campo in ("total_servicios", "total_materiales", "total_descuentos",
                  "total_propinas", "total_ingresos", "total_iva", "total_comisiones",
                  "utilidad_bruta", "por_cobrar"):
        setattr(resumen, campo, round(getattr(resumen, campo), 2))

    resumen.por_cobrar = round(max(resumen.por_cobrar, 0), 2)
    if resumen.citas_completadas:
        resumen.ticket_promedio = round(resumen.total_ingresos / resumen.citas_completadas, 2)
    agendadas = resumen.citas_completadas + resumen.citas_no_asistio + resumen.citas_canceladas
    if agendadas:
        resumen.tasa_no_show_pct = round(resumen.citas_no_asistio / agendadas * 100, 1)

    resumen.serie = sorted(buckets.values(), key=lambda x: x.fecha)
    return resumen


class ProduccionProfesional(BaseModel):
    profesional_id: int
    profesional: str
    color: Optional[str] = None
    citas: int = 0
    servicios: float = 0
    ingresos: float = 0
    comision: float = 0
    propinas: float = 0
    ticket_promedio: float = 0
    minutos_trabajados: int = 0
    minutos_disponibles: int = 0
    ocupacion_pct: float = 0
    no_show: int = 0


@router.get("/reportes/por-profesional", response_model=List[ProduccionProfesional])
async def reporte_por_profesional(
    desde: date, hasta: date, db: AsyncSession = Depends(get_db)
):
    """Produccion y comision a pagar de cada persona del equipo.

    La ocupacion compara los minutos vendidos contra los minutos de jornada
    configurada en el periodo: es el indicador que dice si sobra o falta gente.
    """
    ini = datetime(desde.year, desde.month, desde.day)
    fin = datetime(hasta.year, hasta.month, hasta.day) + timedelta(days=1)

    rp = await db.execute(select(AGSProfesional).order_by(AGSProfesional.nombre))
    profesionales = rp.scalars().all()
    if not profesionales:
        return []

    rh = await db.execute(select(AGSHorarioProfesional).where(
        AGSHorarioProfesional.activo == True))
    jornada: Dict[int, Dict[int, int]] = {}
    for h in rh.scalars().all():
        h_ini, h_fin = _hhmm_a_min(h.hora_inicio), _hhmm_a_min(h.hora_fin)
        if h_ini is None or h_fin is None or h_fin <= h_ini:
            continue
        jornada.setdefault(h.profesional_id, {})
        jornada[h.profesional_id][h.dia_semana] = \
            jornada[h.profesional_id].get(h.dia_semana, 0) + (h_fin - h_ini)

    # Minutos de jornada disponibles en el rango de fechas
    dias_rango: Dict[int, int] = {}
    cursor = desde
    while cursor <= hasta:
        d = _dia_semana(cursor)
        dias_rango[d] = dias_rango.get(d, 0) + 1
        cursor += timedelta(days=1)

    rc = await db.execute(select(AGSCita).where(
        AGSCita.fecha_inicio >= ini, AGSCita.fecha_inicio < fin))
    citas = rc.scalars().all()

    por_prof: Dict[int, Dict[str, Any]] = {}
    for c in citas:
        d = por_prof.setdefault(c.profesional_id, {
            "citas": 0, "servicios": 0.0, "ingresos": 0.0, "comision": 0.0,
            "propinas": 0.0, "minutos": 0, "no_show": 0,
        })
        if c.estado == EstadoCitaEnum.NO_ASISTIO.value:
            d["no_show"] += 1
            continue
        if c.estado not in ESTADOS_FACTURABLES:
            continue
        d["citas"] += 1
        d["servicios"] += float(c.subtotal or 0)
        d["ingresos"] += float(c.total or 0)
        d["comision"] += float(c.comision_profesional or 0)
        d["propinas"] += float(c.propina or 0)
        d["minutos"] += int(c.duracion_min or 0)

    salida = []
    for p in profesionales:
        d = por_prof.get(p.id, {})
        disponibles = sum(minutos * dias_rango.get(dia, 0)
                          for dia, minutos in jornada.get(p.id, {}).items())
        trabajados = int(d.get("minutos", 0))
        item = ProduccionProfesional(
            profesional_id=p.id, profesional=p.nombre, color=p.color,
            citas=d.get("citas", 0),
            servicios=round(d.get("servicios", 0.0), 2),
            ingresos=round(d.get("ingresos", 0.0), 2),
            comision=round(d.get("comision", 0.0), 2),
            propinas=round(d.get("propinas", 0.0), 2),
            minutos_trabajados=trabajados,
            minutos_disponibles=disponibles,
            no_show=d.get("no_show", 0),
        )
        if item.citas:
            item.ticket_promedio = round(item.ingresos / item.citas, 2)
        if disponibles > 0:
            item.ocupacion_pct = round(trabajados / disponibles * 100, 1)
        salida.append(item)
    return sorted(salida, key=lambda x: -x.ingresos)


class VentaServicio(BaseModel):
    servicio_id: Optional[int] = None
    servicio: str
    categoria: Optional[str] = None
    veces: int = 0
    cantidad: float = 0
    ingresos: float = 0
    participacion_pct: float = 0
    minutos: int = 0
    ingreso_por_hora: float = 0


@router.get("/reportes/por-servicio", response_model=List[VentaServicio])
async def reporte_por_servicio(
    desde: date, hasta: date, db: AsyncSession = Depends(get_db)
):
    """Que servicios sostienen el negocio.

    Ademas del ingreso total muestra el ingreso por hora: un servicio caro que
    ocupa tres horas puede rendir menos que uno barato de veinte minutos.
    """
    ini = datetime(desde.year, desde.month, desde.day)
    fin = datetime(hasta.year, hasta.month, hasta.day) + timedelta(days=1)

    rc = await db.execute(select(AGSCita.id).where(
        AGSCita.fecha_inicio >= ini, AGSCita.fecha_inicio < fin,
        AGSCita.estado.in_(ESTADOS_FACTURABLES),
    ))
    ids = [i for (i,) in rc.all()]
    if not ids:
        return []

    rl = await db.execute(select(AGSCitaServicio).where(AGSCitaServicio.cita_id.in_(ids)))
    lineas = rl.scalars().all()

    rs = await db.execute(select(AGSServicio))
    servicios = {x.id: x for x in rs.scalars().all()}
    rcat = await db.execute(select(AGSCategoriaServicio))
    cats = {c.id: c.nombre for c in rcat.scalars().all()}

    agrupado: Dict[str, VentaServicio] = {}
    total_general = 0.0
    for l in lineas:
        clave = str(l.servicio_id) if l.servicio_id else "libre:%s" % l.nombre_servicio
        item = agrupado.get(clave)
        if item is None:
            srv = servicios.get(l.servicio_id) if l.servicio_id else None
            item = VentaServicio(
                servicio_id=l.servicio_id, servicio=l.nombre_servicio,
                categoria=cats.get(srv.categoria_id) if srv else None,
            )
            agrupado[clave] = item
        item.veces += 1
        item.cantidad += float(l.cantidad or 1)
        item.ingresos += float(l.subtotal or 0)
        item.minutos += int(l.duracion_min or 0)
        total_general += float(l.subtotal or 0)

    for item in agrupado.values():
        item.ingresos = round(item.ingresos, 2)
        item.participacion_pct = round(item.ingresos / total_general * 100, 1) \
            if total_general > 0 else 0
        item.ingreso_por_hora = round(item.ingresos / (item.minutos / 60.0), 2) \
            if item.minutos > 0 else 0
    return sorted(agrupado.values(), key=lambda x: -x.ingresos)


class ClienteRanking(BaseModel):
    cliente_id: int
    cliente: str
    telefono: Optional[str] = None
    citas: int = 0
    ingresos: float = 0
    ticket_promedio: float = 0
    ultima_visita: Optional[datetime] = None
    dias_sin_venir: Optional[int] = None
    saldo_pendiente: float = 0
    no_show: int = 0


@router.get("/reportes/por-cliente", response_model=List[ClienteRanking])
async def reporte_por_cliente(
    desde: date, hasta: date, limite: int = 100, db: AsyncSession = Depends(get_db)
):
    """Ingresos por cliente en el periodo, de mayor a menor."""
    ini = datetime(desde.year, desde.month, desde.day)
    fin = datetime(hasta.year, hasta.month, hasta.day) + timedelta(days=1)

    rc = await db.execute(select(AGSCita).where(
        AGSCita.fecha_inicio >= ini, AGSCita.fecha_inicio < fin))
    citas = rc.scalars().all()
    if not citas:
        return []

    rcl = await db.execute(select(AGSCliente))
    clientes = {c.id: c for c in rcl.scalars().all()}

    agrupado: Dict[int, ClienteRanking] = {}
    ahora = _ahora()
    for c in citas:
        cli = clientes.get(c.cliente_id)
        item = agrupado.get(c.cliente_id)
        if item is None:
            item = ClienteRanking(
                cliente_id=c.cliente_id,
                cliente=cli.nombre if cli else "(cliente eliminado)",
                telefono=cli.telefono if cli else None,
            )
            agrupado[c.cliente_id] = item
        if c.estado == EstadoCitaEnum.NO_ASISTIO.value:
            item.no_show += 1
            continue
        if c.estado not in ESTADOS_FACTURABLES:
            continue
        item.citas += 1
        item.ingresos += float(c.total or 0)
        item.saldo_pendiente += float(c.total or 0) - float(c.total_pagado or 0)
        inicio = _sin_tz(c.fecha_inicio)
        if item.ultima_visita is None or inicio > _sin_tz(item.ultima_visita):
            item.ultima_visita = inicio

    for item in agrupado.values():
        item.ingresos = round(item.ingresos, 2)
        item.saldo_pendiente = round(max(item.saldo_pendiente, 0), 2)
        if item.citas:
            item.ticket_promedio = round(item.ingresos / item.citas, 2)
        if item.ultima_visita:
            item.dias_sin_venir = (ahora - _sin_tz(item.ultima_visita)).days
    return sorted(agrupado.values(), key=lambda x: -x.ingresos)[:limite]


class LineaCaja(BaseModel):
    medio_pago: str
    movimientos: int = 0
    total: float = 0


class CierreCaja(BaseModel):
    fecha: date
    total_recaudado: float = 0
    movimientos: int = 0
    efectivo: float = 0
    digital: float = 0
    por_medio: List[LineaCaja] = []
    citas_atendidas: int = 0
    citas_pendientes_pago: int = 0
    saldo_por_cobrar: float = 0
    comisiones_generadas: float = 0


@router.get("/reportes/caja", response_model=CierreCaja)
async def cierre_caja(fecha: Optional[date] = None, db: AsyncSession = Depends(get_db)):
    """Cuadre de caja del dia: cuanto entro y por que medio.

    Se calcula sobre los pagos registrados ese dia (no sobre las citas), que es
    lo que realmente debe estar en el cajon o en la cuenta al cerrar.
    """
    dia = fecha or _hoy()
    ini = datetime(dia.year, dia.month, dia.day)
    fin = ini + timedelta(days=1)

    rp = await db.execute(select(AGSPagoCita).where(
        AGSPagoCita.fecha >= ini, AGSPagoCita.fecha < fin))
    pagos = rp.scalars().all()

    resultado = CierreCaja(fecha=dia)
    por_medio: Dict[str, LineaCaja] = {}
    for p in pagos:
        medio = p.medio_pago or "SIN_MEDIO"
        linea = por_medio.get(medio)
        if linea is None:
            linea = LineaCaja(medio_pago=medio)
            por_medio[medio] = linea
        linea.movimientos += 1
        linea.total += float(p.monto or 0)
        resultado.total_recaudado += float(p.monto or 0)
        resultado.movimientos += 1
        if medio == MedioPagoEnum.EFECTIVO.value:
            resultado.efectivo += float(p.monto or 0)
        else:
            resultado.digital += float(p.monto or 0)

    for linea in por_medio.values():
        linea.total = round(linea.total, 2)
    resultado.por_medio = sorted(por_medio.values(), key=lambda x: -x.total)
    resultado.total_recaudado = round(resultado.total_recaudado, 2)
    resultado.efectivo = round(resultado.efectivo, 2)
    resultado.digital = round(resultado.digital, 2)

    rc = await db.execute(select(AGSCita).where(
        AGSCita.fecha_inicio >= ini, AGSCita.fecha_inicio < fin))
    for c in rc.scalars().all():
        if c.estado in ESTADOS_FACTURABLES:
            resultado.citas_atendidas += 1
            resultado.comisiones_generadas += float(c.comision_profesional or 0)
            saldo = float(c.total or 0) - float(c.total_pagado or 0)
            if saldo > 0.01:
                resultado.citas_pendientes_pago += 1
                resultado.saldo_por_cobrar += saldo
    resultado.saldo_por_cobrar = round(resultado.saldo_por_cobrar, 2)
    resultado.comisiones_generadas = round(resultado.comisiones_generadas, 2)
    return resultado


# ──────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────

class CitaResumen(BaseModel):
    id: int
    codigo: str
    hora: str
    fecha_inicio: datetime
    cliente: str
    telefono: Optional[str] = None
    profesional: Optional[str] = None
    profesional_color: Optional[str] = None
    servicios: str = ""
    estado: str
    total: float = 0
    lugar: Optional[str] = None


class DashboardResponse(BaseModel):
    fecha: date
    negocio: Optional[str] = None
    # Hoy
    citas_hoy: int = 0
    atendidas_hoy: int = 0
    pendientes_hoy: int = 0
    ingresos_hoy: float = 0
    recaudado_hoy: float = 0
    ocupacion_hoy_pct: float = 0
    # Mes
    citas_mes: int = 0
    ingresos_mes: float = 0
    ticket_promedio_mes: float = 0
    comisiones_mes: float = 0
    ingresos_mes_anterior: float = 0
    variacion_pct: Optional[float] = None
    # Cartera y alertas
    por_cobrar: float = 0
    citas_por_cobrar: int = 0
    no_show_mes: int = 0
    tasa_no_show_pct: float = 0
    clientes_nuevos_mes: int = 0
    clientes_activos: int = 0
    sin_recordatorio: int = 0
    # Listas
    agenda_hoy: List[CitaResumen] = []
    proximas: List[CitaResumen] = []
    top_servicios: List[VentaServicio] = []


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(db: AsyncSession = Depends(get_db)):
    """Tablero de arranque: como va el dia, como va el mes y que esta pendiente."""
    cfg = await _get_config(db)
    hoy = _hoy()
    ini_hoy = datetime(hoy.year, hoy.month, hoy.day)
    fin_hoy = ini_hoy + timedelta(days=1)
    ini_mes = datetime(hoy.year, hoy.month, 1)
    if hoy.month == 1:
        ini_mes_ant = datetime(hoy.year - 1, 12, 1)
    else:
        ini_mes_ant = datetime(hoy.year, hoy.month - 1, 1)

    res = DashboardResponse(fecha=hoy, negocio=cfg.nombre_negocio)

    rcl = await db.execute(select(AGSCliente))
    clientes = {c.id: c for c in rcl.scalars().all()}
    rp = await db.execute(select(AGSProfesional))
    profs = {p.id: p for p in rp.scalars().all()}

    # Citas desde el mes anterior en adelante: cubre todos los KPIs de un tiro
    rc = await db.execute(select(AGSCita).where(AGSCita.fecha_inicio >= ini_mes_ant)
                          .order_by(AGSCita.fecha_inicio))
    citas = rc.scalars().all()

    lineas: Dict[int, List[str]] = {}
    if citas:
        rl = await db.execute(select(AGSCitaServicio).where(
            AGSCitaServicio.cita_id.in_([c.id for c in citas])))
        for l in rl.scalars().all():
            lineas.setdefault(l.cita_id, []).append(l.nombre_servicio)

    def resumir(c: AGSCita) -> CitaResumen:
        cli = clientes.get(c.cliente_id)
        pro = profs.get(c.profesional_id)
        inicio = _sin_tz(c.fecha_inicio)
        return CitaResumen(
            id=c.id, codigo=c.codigo, hora=inicio.strftime("%H:%M"),
            fecha_inicio=inicio,
            cliente=cli.nombre if cli else "(sin cliente)",
            telefono=cli.telefono if cli else None,
            profesional=pro.nombre if pro else None,
            profesional_color=pro.color if pro else None,
            servicios=", ".join(lineas.get(c.id, [])),
            estado=c.estado, total=float(c.total or 0), lugar=c.lugar,
        )

    ahora = _ahora()
    minutos_vendidos_hoy = 0
    agendadas_mes = 0

    for c in citas:
        inicio = _sin_tz(c.fecha_inicio)
        es_hoy = ini_hoy <= inicio < fin_hoy
        es_mes = inicio >= ini_mes
        es_mes_ant = ini_mes_ant <= inicio < ini_mes

        if es_hoy and c.estado not in (EstadoCitaEnum.CANCELADA.value,):
            res.citas_hoy += 1
            res.agenda_hoy.append(resumir(c))
            if c.estado in ESTADOS_FACTURABLES:
                res.atendidas_hoy += 1
                res.ingresos_hoy += float(c.total or 0)
                res.recaudado_hoy += float(c.total_pagado or 0)
                minutos_vendidos_hoy += int(c.duracion_min or 0)
            elif c.estado in (EstadoCitaEnum.AGENDADA.value, EstadoCitaEnum.CONFIRMADA.value,
                              EstadoCitaEnum.EN_CURSO.value):
                res.pendientes_hoy += 1
                minutos_vendidos_hoy += int(c.duracion_min or 0)
                if not c.recordatorio_enviado:
                    res.sin_recordatorio += 1

        if es_mes:
            if c.estado in ESTADOS_FACTURABLES:
                res.citas_mes += 1
                res.ingresos_mes += float(c.total or 0)
                res.comisiones_mes += float(c.comision_profesional or 0)
                saldo = float(c.total or 0) - float(c.total_pagado or 0)
                if saldo > 0.01:
                    res.por_cobrar += saldo
                    res.citas_por_cobrar += 1
                agendadas_mes += 1
            elif c.estado == EstadoCitaEnum.NO_ASISTIO.value:
                res.no_show_mes += 1
                agendadas_mes += 1
            elif c.estado == EstadoCitaEnum.CANCELADA.value:
                agendadas_mes += 1
        elif es_mes_ant and c.estado in ESTADOS_FACTURABLES:
            res.ingresos_mes_anterior += float(c.total or 0)

        # Proximas citas (siguientes 7 dias)
        if inicio >= ahora and inicio < ahora + timedelta(days=7) and c.estado in (
            EstadoCitaEnum.AGENDADA.value, EstadoCitaEnum.CONFIRMADA.value
        ):
            res.proximas.append(resumir(c))

    res.agenda_hoy.sort(key=lambda x: x.fecha_inicio)
    res.proximas.sort(key=lambda x: x.fecha_inicio)
    res.proximas = res.proximas[:15]

    for campo in ("ingresos_hoy", "recaudado_hoy", "ingresos_mes",
                  "comisiones_mes", "ingresos_mes_anterior", "por_cobrar"):
        setattr(res, campo, round(getattr(res, campo), 2))

    if res.citas_mes:
        res.ticket_promedio_mes = round(res.ingresos_mes / res.citas_mes, 2)
    if agendadas_mes:
        res.tasa_no_show_pct = round(res.no_show_mes / agendadas_mes * 100, 1)
    if res.ingresos_mes_anterior > 0:
        res.variacion_pct = round(
            (res.ingresos_mes - res.ingresos_mes_anterior) / res.ingresos_mes_anterior * 100, 1)

    # Ocupacion de hoy: minutos vendidos contra la jornada del equipo activo
    dia = _dia_semana(hoy)
    rh = await db.execute(select(AGSHorarioProfesional).where(
        AGSHorarioProfesional.dia_semana == dia, AGSHorarioProfesional.activo == True))
    activos = {p.id for p in profs.values() if p.activo}
    capacidad = 0
    for h in rh.scalars().all():
        if h.profesional_id not in activos:
            continue
        h_ini, h_fin = _hhmm_a_min(h.hora_inicio), _hhmm_a_min(h.hora_fin)
        if h_ini is not None and h_fin is not None and h_fin > h_ini:
            capacidad += h_fin - h_ini
    if capacidad > 0:
        res.ocupacion_hoy_pct = round(minutos_vendidos_hoy / capacidad * 100, 1)

    # Clientes
    res.clientes_activos = sum(1 for c in clientes.values() if c.activo)
    res.clientes_nuevos_mes = sum(
        1 for c in clientes.values()
        if c.created_at is not None and _sin_tz(c.created_at) >= ini_mes
    )

    # Top servicios del mes
    try:
        res.top_servicios = (await reporte_por_servicio(
            desde=ini_mes.date(), hasta=hoy, db=db))[:5]
    except HTTPException:
        res.top_servicios = []

    return res

# ──────────────────────────────────────────
# RESERVA ONLINE (publico, sin login)
# ──────────────────────────────────────────
#
# Todo lo que esta debajo lo consume la pagina publica /reservar/{slug}, que no
# pide login. Por eso expone deliberadamente el minimo: el catalogo activo, los
# nombres del equipo y las horas libres. Nunca ingresos, ni comisiones, ni el
# listado de clientes, ni datos de otras citas.


async def _config_publica(db: AsyncSession, slug: str) -> AGSConfig:
    """Busca el negocio por su slug y exige que la reserva online este abierta."""
    limpio = (slug or "").strip().lower()
    r = await db.execute(select(AGSConfig).where(func.lower(AGSConfig.slug) == limpio))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(404, "No encontramos este negocio.")
    if not cfg.reserva_online_activa:
        raise HTTPException(
            403, "Este negocio no esta recibiendo reservas por internet en este momento.")
    return cfg


class NegocioPublico(BaseModel):
    nombre: str
    tipo_negocio: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    hora_apertura: Optional[str] = None
    hora_cierre: Optional[str] = None
    dias_laborales: Optional[List[int]] = None
    mensaje_bienvenida: Optional[str] = None
    dias_max_anticipacion: int = 30
    permite_cancelar_online: bool = True
    horas_min_cancelacion: int = 4
    requiere_confirmacion: bool = True


@router.get("/publico/{slug}", response_model=NegocioPublico)
async def negocio_publico(slug: str, db: AsyncSession = Depends(get_db)):
    """Datos de presentacion del negocio para la pagina de reservas."""
    cfg = await _config_publica(db, slug)
    return NegocioPublico(
        nombre=cfg.nombre_negocio, tipo_negocio=cfg.tipo_negocio,
        telefono=cfg.telefono, direccion=cfg.direccion, ciudad=cfg.ciudad,
        hora_apertura=cfg.hora_apertura, hora_cierre=cfg.hora_cierre,
        dias_laborales=cfg.dias_laborales or [1, 2, 3, 4, 5, 6],
        mensaje_bienvenida=cfg.mensaje_bienvenida,
        dias_max_anticipacion=int(cfg.dias_max_anticipacion or 30),
        permite_cancelar_online=bool(cfg.permite_cancelar_online),
        horas_min_cancelacion=int(cfg.horas_min_cancelacion or 0),
        requiere_confirmacion=bool(cfg.requiere_confirmacion_online),
    )


class ServicioPublico(BaseModel):
    """Version reducida del servicio: sin costo de insumos ni margen."""
    id: int
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    categoria_color: Optional[str] = None
    duracion_min: int
    precio: float
    permite_domicilio: bool = False


@router.get("/publico/{slug}/servicios", response_model=List[ServicioPublico])
async def servicios_publicos(slug: str, db: AsyncSession = Depends(get_db)):
    await _config_publica(db, slug)
    r = await db.execute(select(AGSServicio).where(AGSServicio.activo == True)
                         .order_by(AGSServicio.nombre))
    servicios = r.scalars().all()
    rc = await db.execute(select(AGSCategoriaServicio))
    cats = {c.id: c for c in rc.scalars().all()}
    salida = []
    for x in servicios:
        cat = cats.get(x.categoria_id)
        if cat is not None and cat.activo is False:
            continue
        salida.append(ServicioPublico(
            id=x.id, nombre=x.nombre, descripcion=x.descripcion,
            categoria=cat.nombre if cat else None,
            categoria_color=cat.color if cat else None,
            duracion_min=int(x.duracion_min or 0), precio=float(x.precio or 0),
            permite_domicilio=bool(x.permite_domicilio),
        ))
    return salida


class ProfesionalPublico(BaseModel):
    id: int
    nombre: str
    especialidad: Optional[str] = None
    color: Optional[str] = None


@router.get("/publico/{slug}/profesionales", response_model=List[ProfesionalPublico])
async def profesionales_publicos(
    slug: str, servicio_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
):
    """Quien puede atender. Si se pasa un servicio, solo quienes lo prestan."""
    await _config_publica(db, slug)
    r = await db.execute(select(AGSProfesional).where(AGSProfesional.activo == True)
                         .order_by(AGSProfesional.nombre))
    profesionales = r.scalars().all()

    if servicio_id is not None and profesionales:
        rs = await db.execute(select(AGSProfesionalServicio.profesional_id).where(
            AGSProfesionalServicio.servicio_id == servicio_id))
        capacitados = {pid for (pid,) in rs.all()}
        if capacitados:
            profesionales = [p for p in profesionales if p.id in capacitados]

    return [ProfesionalPublico(
        id=p.id, nombre=p.nombre, especialidad=p.especialidad, color=p.color,
    ) for p in profesionales]


class SlotPublico(BaseModel):
    hora_inicio: str
    hora_fin: str
    inicio: datetime
    profesional_id: int
    profesional: str


@router.get("/publico/{slug}/disponibilidad", response_model=List[SlotPublico])
async def disponibilidad_publica(
    slug: str, fecha: date, servicio_id: int,
    profesional_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Horas libres de la fecha, ya aplanadas en una sola lista.

    Cuando el cliente no elige profesional se devuelven las horas de todo el
    equipo y se deja una sola entrada por hora (la del primero disponible):
    a quien reserva le interesa la hora, no quien lo atiende.
    """
    cfg = await _config_publica(db, slug)

    hoy = _hoy()
    if fecha < hoy:
        raise HTTPException(400, "Esa fecha ya paso.")
    limite = hoy + timedelta(days=int(cfg.dias_max_anticipacion or 30))
    if fecha > limite:
        raise HTTPException(
            400, "Solo se pueden reservar citas hasta el %s." % limite.strftime("%d/%m/%Y"))

    disponibilidad = await disponibilidad_publica_interna(
        db, fecha, servicio_id, profesional_id)

    salida: List[SlotPublico] = []
    vistas = set()
    for d in disponibilidad:
        for s in d.slots:
            if profesional_id is None and s.hora_inicio in vistas:
                continue
            vistas.add(s.hora_inicio)
            salida.append(SlotPublico(
                hora_inicio=s.hora_inicio, hora_fin=s.hora_fin, inicio=s.inicio,
                profesional_id=d.profesional_id, profesional=d.profesional,
            ))
    return sorted(salida, key=lambda x: x.hora_inicio)


async def disponibilidad_publica_interna(
    db: AsyncSession, fecha: date, servicio_id: int, profesional_id: Optional[int],
) -> List[DisponibilidadProfesional]:
    """Reusa el calculo de disponibilidad del panel interno."""
    return await disponibilidad(
        fecha=fecha, duracion_min=30, profesional_id=profesional_id,
        servicio_id=servicio_id, db=db,
    )


class ReservaPublicaIn(BaseModel):
    nombre: str
    telefono: str
    servicio_id: int
    fecha_inicio: datetime
    profesional_id: Optional[int] = None
    email: Optional[str] = None
    notas: Optional[str] = None
    lugar: Optional[str] = None
    direccion_servicio: Optional[str] = None


class ReservaPublicaOut(BaseModel):
    codigo: str
    estado: str
    fecha_inicio: datetime
    fecha_fin: datetime
    servicio: str
    profesional: str
    total: float
    requiere_confirmacion: bool
    mensaje: str


@router.post("/publico/{slug}/reservar", response_model=ReservaPublicaOut, status_code=201)
async def reservar_publico(
    slug: str, data: ReservaPublicaIn, db: AsyncSession = Depends(get_db),
):
    """Crea la cita desde la pagina publica.

    El cliente se identifica por telefono: si ya existe se reutiliza su ficha
    (y con ella su historial), si no se crea. Asi el mostrador no termina con
    tres registros de la misma persona.
    """
    cfg = await _config_publica(db, slug)

    telefono = "".join(ch for ch in (data.telefono or "") if ch.isdigit())
    if len(telefono) < 7:
        raise HTTPException(400, "El telefono no parece valido. Revise el numero.")
    nombre = (data.nombre or "").strip()
    if len(nombre) < 3:
        raise HTTPException(400, "Escriba su nombre completo.")

    srv = await db.get(AGSServicio, data.servicio_id)
    if srv is None or not srv.activo:
        raise HTTPException(404, "Ese servicio ya no esta disponible.")

    inicio = _sin_tz(data.fecha_inicio)
    ahora = _ahora()
    if inicio <= ahora:
        raise HTTPException(400, "Esa hora ya paso. Elija otra.")
    minimo = ahora + timedelta(minutes=int(cfg.anticipacion_minima_min or 0))
    if inicio < minimo:
        raise HTTPException(
            400, "Las reservas se toman con al menos %d minutos de anticipacion."
                 % int(cfg.anticipacion_minima_min or 0))
    limite = ahora + timedelta(days=int(cfg.dias_max_anticipacion or 30))
    if inicio > limite:
        raise HTTPException(
            400, "Solo se pueden reservar citas hasta el %s." % limite.strftime("%d/%m/%Y"))

    # Cliente: buscar por telefono o crear
    rc = await db.execute(select(AGSCliente).where(AGSCliente.telefono == telefono))
    cliente = rc.scalar_one_or_none()
    if cliente is None:
        cliente = AGSCliente(
            codigo=await _siguiente_codigo(db, AGSCliente, "CLI", 5),
            nombre=nombre, telefono=telefono, email=data.email or None,
            direccion=data.direccion_servicio or None,
            como_nos_conocio="Reserva online", acepta_recordatorios=True,
        )
        db.add(cliente)
        await db.flush()
    else:
        if not cliente.activo:
            raise HTTPException(
                403, "No podemos tomar la reserva. Comuniquese con el negocio.")
        if data.email and not cliente.email:
            cliente.email = data.email

    # Tope de citas pendientes: freno simple contra reservas en masa
    tope = int(cfg.max_citas_pendientes_cliente or 0)
    if tope > 0:
        rp = await db.execute(select(func.count()).select_from(AGSCita).where(
            AGSCita.cliente_id == cliente.id,
            AGSCita.estado.in_([EstadoCitaEnum.AGENDADA.value,
                                EstadoCitaEnum.CONFIRMADA.value]),
            AGSCita.fecha_inicio >= ahora,
        ))
        if (rp.scalar() or 0) >= tope:
            raise HTTPException(
                409, "Ya tiene %d cita(s) pendiente(s). Para agendar otra, "
                     "comuniquese con el negocio." % tope)

    # Profesional: el elegido, o el primero libre a esa hora
    profesional_id = data.profesional_id
    if profesional_id is None:
        libres = await disponibilidad_publica_interna(db, inicio.date(), srv.id, None)
        hhmm = inicio.strftime("%H:%M")
        for d in libres:
            if any(x.hora_inicio == hhmm for x in d.slots):
                profesional_id = d.profesional_id
                break
        if profesional_id is None:
            raise HTTPException(409, "Esa hora acaba de ocuparse. Elija otra, por favor.")

    pro = await db.get(AGSProfesional, profesional_id)
    if pro is None or not pro.activo:
        raise HTTPException(404, "Ese profesional no esta disponible.")

    lugar = data.lugar or LugarServicioEnum.LOCAL.value
    if lugar == LugarServicioEnum.DOMICILIO.value:
        if not srv.permite_domicilio:
            raise HTTPException(400, "Ese servicio no se presta a domicilio.")
        if not (data.direccion_servicio or cliente.direccion):
            raise HTTPException(400, "Indique la direccion para el servicio a domicilio.")

    cita = AGSCita(
        codigo=await _siguiente_codigo(db, AGSCita, "CITA", 5),
        cliente_id=cliente.id, profesional_id=profesional_id,
        fecha_inicio=inicio, fecha_fin=inicio + timedelta(minutes=30), duracion_min=30,
        lugar=lugar,
        direccion_servicio=data.direccion_servicio or (
            cliente.direccion if lugar == LugarServicioEnum.DOMICILIO.value else None),
        estado=(EstadoCitaEnum.AGENDADA.value if cfg.requiere_confirmacion_online
                else EstadoCitaEnum.CONFIRMADA.value),
        origen=OrigenCitaEnum.ONLINE.value,
        notas=data.notas, creado_por="Reserva online",
    )
    db.add(cita)
    await db.flush()

    lineas = await _construir_lineas(db, cita.id, [LineaServicioIn(servicio_id=srv.id)])
    for l in lineas:
        db.add(l)
    _recalcular_totales(cita, lineas, [],
                        float(pro.comision_pct or cfg.comision_defecto_pct or 0),
                        float(cfg.iva_pct or 0))

    await _validar_disponibilidad(
        db, profesional_id, cita.fecha_inicio, cita.fecha_fin,
        excluir_cita_id=cita.id, permite_sobrecupo=bool(cfg.permite_sobrecupo),
    )

    await db.commit()
    await db.refresh(cita)

    requiere = bool(cfg.requiere_confirmacion_online)
    return ReservaPublicaOut(
        codigo=cita.codigo, estado=cita.estado,
        fecha_inicio=cita.fecha_inicio, fecha_fin=cita.fecha_fin,
        servicio=srv.nombre, profesional=pro.nombre, total=float(cita.total or 0),
        requiere_confirmacion=requiere,
        mensaje=("Su reserva quedo registrada. El negocio la confirmara pronto."
                 if requiere else "Su cita quedo confirmada. Lo esperamos."),
    )


class CitaPublica(BaseModel):
    codigo: str
    estado: str
    fecha_inicio: datetime
    fecha_fin: datetime
    servicios: str
    profesional: str
    total: float
    lugar: Optional[str] = None
    direccion_servicio: Optional[str] = None
    puede_cancelar: bool = False
    motivo_no_cancelable: Optional[str] = None


@router.get("/publico/{slug}/cita", response_model=CitaPublica)
async def consultar_cita_publica(
    slug: str, codigo: str, telefono: str, db: AsyncSession = Depends(get_db),
):
    """Consulta una cita con su codigo mas el telefono con el que se reservo.

    Pedir las dos cosas evita que con solo adivinar un codigo consecutivo se
    pueda ver la cita de otra persona.
    """
    cfg = await _config_publica(db, slug)

    solo_digitos = "".join(ch for ch in (telefono or "") if ch.isdigit())
    r = await db.execute(select(AGSCita).where(
        func.upper(AGSCita.codigo) == (codigo or "").strip().upper()))
    cita = r.scalar_one_or_none()
    if cita is None:
        raise HTTPException(404, "No encontramos esa cita.")

    cliente = await db.get(AGSCliente, cita.cliente_id)
    tel_cliente = "".join(ch for ch in (cliente.telefono or "") if ch.isdigit()) if cliente else ""
    if not solo_digitos or not tel_cliente or not tel_cliente.endswith(solo_digitos[-7:]):
        raise HTTPException(404, "No encontramos esa cita con ese telefono.")

    pro = await db.get(AGSProfesional, cita.profesional_id)
    rs = await db.execute(select(AGSCitaServicio).where(AGSCitaServicio.cita_id == cita.id))
    servicios = ", ".join(l.nombre_servicio for l in rs.scalars().all())

    puede, motivo = _puede_cancelar_online(cfg, cita)
    return CitaPublica(
        codigo=cita.codigo, estado=cita.estado,
        fecha_inicio=cita.fecha_inicio, fecha_fin=cita.fecha_fin,
        servicios=servicios, profesional=pro.nombre if pro else "",
        total=float(cita.total or 0), lugar=cita.lugar,
        direccion_servicio=cita.direccion_servicio,
        puede_cancelar=puede, motivo_no_cancelable=motivo,
    )


def _puede_cancelar_online(cfg: AGSConfig, cita: AGSCita):
    """Reglas de cancelacion desde la pagina publica."""
    if not cfg.permite_cancelar_online:
        return False, "Este negocio no permite cancelar por internet. Comuniquese con el."
    if cita.estado not in (EstadoCitaEnum.AGENDADA.value, EstadoCitaEnum.CONFIRMADA.value):
        return False, "Esta cita ya no se puede cancelar."
    if float(cita.total_pagado or 0) > 0:
        return False, "Esta cita tiene pagos registrados. Comuniquese con el negocio."
    horas = int(cfg.horas_min_cancelacion or 0)
    if horas > 0:
        limite = _sin_tz(cita.fecha_inicio) - timedelta(hours=horas)
        if _ahora() > limite:
            return False, ("Ya paso el plazo para cancelar por internet "
                           "(%d horas antes). Comuniquese con el negocio." % horas)
    return True, None


class CancelarPublicoIn(BaseModel):
    codigo: str
    telefono: str
    motivo: Optional[str] = None


@router.post("/publico/{slug}/cancelar", response_model=CitaPublica)
async def cancelar_cita_publica(
    slug: str, data: CancelarPublicoIn, db: AsyncSession = Depends(get_db),
):
    cfg = await _config_publica(db, slug)

    solo_digitos = "".join(ch for ch in (data.telefono or "") if ch.isdigit())
    r = await db.execute(select(AGSCita).where(
        func.upper(AGSCita.codigo) == (data.codigo or "").strip().upper()))
    cita = r.scalar_one_or_none()
    if cita is None:
        raise HTTPException(404, "No encontramos esa cita.")

    cliente = await db.get(AGSCliente, cita.cliente_id)
    tel_cliente = "".join(ch for ch in (cliente.telefono or "") if ch.isdigit()) if cliente else ""
    if not solo_digitos or not tel_cliente or not tel_cliente.endswith(solo_digitos[-7:]):
        raise HTTPException(404, "No encontramos esa cita con ese telefono.")

    puede, motivo = _puede_cancelar_online(cfg, cita)
    if not puede:
        raise HTTPException(409, motivo or "Esta cita no se puede cancelar.")

    cita.estado = EstadoCitaEnum.CANCELADA.value
    cita.motivo_cancelacion = (data.motivo or "Cancelada por el cliente desde la web")[:200]
    await db.commit()
    await db.refresh(cita)

    pro = await db.get(AGSProfesional, cita.profesional_id)
    rs = await db.execute(select(AGSCitaServicio).where(AGSCitaServicio.cita_id == cita.id))
    servicios = ", ".join(l.nombre_servicio for l in rs.scalars().all())
    return CitaPublica(
        codigo=cita.codigo, estado=cita.estado,
        fecha_inicio=cita.fecha_inicio, fecha_fin=cita.fecha_fin,
        servicios=servicios, profesional=pro.nombre if pro else "",
        total=float(cita.total or 0), lugar=cita.lugar,
        direccion_servicio=cita.direccion_servicio,
        puede_cancelar=False, motivo_no_cancelable="La cita esta cancelada.",
    )

