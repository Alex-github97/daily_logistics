from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.models.usuario import RolUsuario
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.proveedor import Proveedor
from app.infrastructure.models.scm import (
    ScmSolicitudCompra, ScmSolicitudItem, ScmOrdenCompra, ScmOrdenItem,
    ScmEvaluacionProveedor, EstadoSolicitudSCM, EstadoOrdenSCM,
    CategoriaSCM, PrioridadSCM, ClasificacionProveedor, RecomendacionProveedor,
    ScmParametro,
)

router = APIRouter(prefix="/scm", tags=["SCM"])


# ── Helpers ────────────────────────────────────────────────────────────────

async def _parametros(db: AsyncSession) -> ScmParametro:
    p = await db.get(ScmParametro, 1)
    if p is None:
        p = ScmParametro(id=1, monto_doble_aprobacion=50_000_000, solicitud_exige_items=True,
                         dias_oc_sin_confirmar=3, dias_evaluacion_proveedor=180)
        db.add(p)
        await db.flush()
    return p


class ParametrosIn(BaseModel):
    monto_doble_aprobacion: Optional[float] = None
    solicitud_exige_items: bool = True
    dias_oc_sin_confirmar: int = 3
    dias_evaluacion_proveedor: int = 180


def _parametros_dict(p: ScmParametro) -> dict:
    return {"monto_doble_aprobacion": p.monto_doble_aprobacion,
            "solicitud_exige_items": p.solicitud_exige_items,
            "dias_oc_sin_confirmar": p.dias_oc_sin_confirmar,
            "dias_evaluacion_proveedor": p.dias_evaluacion_proveedor}


@router.get("/parametros")
async def leer_parametros(db: AsyncSession = Depends(get_db),
                          current_user: Usuario = Depends(get_current_user)):
    return _parametros_dict(await _parametros(db))


@router.put("/parametros")
async def guardar_parametros(data: ParametrosIn, db: AsyncSession = Depends(get_db),
                             current_user: Usuario = Depends(require_admin)):
    if data.monto_doble_aprobacion is not None and data.monto_doble_aprobacion <= 0:
        raise HTTPException(422, "El tope de doble aprobación debe ser mayor que cero, o vacío para no exigirla.")
    if data.dias_oc_sin_confirmar < 1 or data.dias_evaluacion_proveedor < 1:
        raise HTTPException(422, "Los plazos deben ser de al menos un día.")
    p = await _parametros(db)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    return _parametros_dict(p)


async def _gen_numero_solicitud(db: AsyncSession) -> str:
    year = date.today().year
    res = await db.execute(select(func.count(ScmSolicitudCompra.id)))
    seq = (res.scalar_one() or 0) + 1
    return f"SCM-SOL-{year}-{seq:05d}"


async def _gen_numero_orden(db: AsyncSession) -> str:
    year = date.today().year
    res = await db.execute(select(func.count(ScmOrdenCompra.id)))
    seq = (res.scalar_one() or 0) + 1
    return f"SCM-OC-{year}-{seq:05d}"


def _solicitud_to_dict(s: ScmSolicitudCompra, include_items: bool = False) -> dict:
    d = {
        "id": s.id,
        "numero": s.numero,
        "titulo": s.titulo,
        "descripcion": s.descripcion,
        "categoria": s.categoria.value if s.categoria else None,
        "prioridad": s.prioridad.value if s.prioridad else None,
        "estado": s.estado.value if s.estado else None,
        "fecha_requerida": s.fecha_requerida.isoformat() if s.fecha_requerida else None,
        "presupuesto_estimado": s.presupuesto_estimado,
        "moneda": s.moneda,
        "justificacion": s.justificacion,
        "observaciones": s.observaciones,
        "fecha_aprobacion": s.fecha_aprobacion.isoformat() if s.fecha_aprobacion else None,
        "motivo_rechazo": s.motivo_rechazo,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "solicitante_id": s.solicitante_id,
        "aprobador_id": s.aprobador_id,
        "proveedor_id": s.proveedor_id,
    }
    if include_items and s.items:
        d["items"] = [
            {
                "id": i.id,
                "descripcion": i.descripcion,
                "unidad": i.unidad,
                "cantidad": i.cantidad,
                "precio_estimado": i.precio_estimado,
                "total_estimado": i.total_estimado,
                "especificaciones": i.especificaciones,
            }
            for i in s.items
        ]
    return d


def _orden_to_dict(o: ScmOrdenCompra, include_items: bool = False) -> dict:
    d = {
        "id": o.id,
        "numero": o.numero,
        "solicitud_id": o.solicitud_id,
        "proveedor_id": o.proveedor_id,
        "creado_por_id": o.creado_por_id,
        "estado": o.estado.value if o.estado else None,
        "categoria": o.categoria.value if o.categoria else None,
        "prioridad": o.prioridad.value if o.prioridad else None,
        "fecha_emision": o.fecha_emision.isoformat() if o.fecha_emision else None,
        "fecha_entrega_esperada": o.fecha_entrega_esperada.isoformat() if o.fecha_entrega_esperada else None,
        "fecha_entrega_real": o.fecha_entrega_real.isoformat() if o.fecha_entrega_real else None,
        "subtotal": o.subtotal,
        "impuestos": o.impuestos,
        "total": o.total,
        "moneda": o.moneda,
        "condiciones_pago": o.condiciones_pago,
        "lugar_entrega": o.lugar_entrega,
        "notas": o.notas,
        "codigo_sap": o.codigo_sap,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
    if include_items and o.items:
        d["items"] = [
            {
                "id": i.id,
                "descripcion": i.descripcion,
                "codigo_producto": i.codigo_producto,
                "unidad": i.unidad,
                "cantidad": i.cantidad,
                "cantidad_recibida": i.cantidad_recibida,
                "precio_unitario": i.precio_unitario,
                "descuento_pct": i.descuento_pct,
                "total": i.total,
                "especificaciones": i.especificaciones,
            }
            for i in o.items
        ]
    return d


# ── Dashboard ──────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def scm_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    total_sol = await db.execute(select(func.count(ScmSolicitudCompra.id)))
    sol_pendientes = await db.execute(
        select(func.count(ScmSolicitudCompra.id)).where(
            ScmSolicitudCompra.estado == EstadoSolicitudSCM.PENDIENTE
        )
    )
    oc_abiertas = await db.execute(
        select(func.count(ScmOrdenCompra.id)).where(
            ScmOrdenCompra.estado.in_([
                EstadoOrdenSCM.ENVIADA, EstadoOrdenSCM.CONFIRMADA, EstadoOrdenSCM.EN_TRANSITO,
                EstadoOrdenSCM.RECIBIDA_PARCIAL,
            ])
        )
    )
    valor_oc = await db.execute(
        select(func.coalesce(func.sum(ScmOrdenCompra.total), 0)).where(
            ScmOrdenCompra.estado.in_([
                EstadoOrdenSCM.ENVIADA, EstadoOrdenSCM.CONFIRMADA, EstadoOrdenSCM.EN_TRANSITO,
                EstadoOrdenSCM.RECIBIDA_PARCIAL,
            ])
        )
    )
    proveedores_activos = await db.execute(
        select(func.count(Proveedor.id)).where(Proveedor.activo == True)
    )
    oc_por_estado = await db.execute(
        select(ScmOrdenCompra.estado, func.count(ScmOrdenCompra.id).label("cnt"))
        .group_by(ScmOrdenCompra.estado)
    )
    sol_por_estado = await db.execute(
        select(ScmSolicitudCompra.estado, func.count(ScmSolicitudCompra.id).label("cnt"))
        .group_by(ScmSolicitudCompra.estado)
    )
    par = await _parametros(db)
    hoy = date.today()
    sin_confirmar = (await db.execute(
        select(ScmOrdenCompra.id, ScmOrdenCompra.numero, ScmOrdenCompra.fecha_emision, Proveedor.razon_social)
        .join(Proveedor, Proveedor.id == ScmOrdenCompra.proveedor_id)
        .where(ScmOrdenCompra.estado == EstadoOrdenSCM.ENVIADA,
               ScmOrdenCompra.fecha_emision <= hoy - timedelta(days=par.dias_oc_sin_confirmar))
        .order_by(ScmOrdenCompra.fecha_emision))).all()
    # Proveedores a los que se les compró en el último año y cuya última
    # evaluación es más vieja que el plazo (o no existe).
    ultima_eval = (select(ScmEvaluacionProveedor.proveedor_id,
                          func.max(ScmEvaluacionProveedor.created_at).label("ultima"))
                   .group_by(ScmEvaluacionProveedor.proveedor_id).subquery())
    por_evaluar = (await db.execute(
        select(Proveedor.id, Proveedor.razon_social, ultima_eval.c.ultima)
        .join(ScmOrdenCompra, ScmOrdenCompra.proveedor_id == Proveedor.id)
        .outerjoin(ultima_eval, ultima_eval.c.proveedor_id == Proveedor.id)
        .where(ScmOrdenCompra.fecha_emision >= hoy - timedelta(days=365),
               Proveedor.activo == True)  # noqa: E712
        .group_by(Proveedor.id, Proveedor.razon_social, ultima_eval.c.ultima))).all()
    limite_eval = hoy - timedelta(days=par.dias_evaluacion_proveedor)
    por_evaluar = [r for r in por_evaluar if r.ultima is None or r.ultima.date() < limite_eval]

    alertas = [
        {"tipo": "OC_SIN_CONFIRMAR", "id": r.id,
         "texto": f"{r.numero} · {r.razon_social}",
         "detalle": f"Enviada hace {(hoy - r.fecha_emision).days} días y sin confirmar"}
        for r in sin_confirmar
    ] + [
        {"tipo": "PROVEEDOR_SIN_EVALUAR", "id": r.id, "texto": r.razon_social,
         "detalle": ("Nunca evaluado" if r.ultima is None
                     else f"Última evaluación hace {(hoy - r.ultima.date()).days} días")}
        for r in por_evaluar
    ]

    return {
        "alertas": alertas,
        "parametros": _parametros_dict(par),
        "kpis": {
            "total_solicitudes": total_sol.scalar_one(),
            "solicitudes_pendientes": sol_pendientes.scalar_one(),
            "oc_abiertas": oc_abiertas.scalar_one(),
            "valor_oc_en_proceso": valor_oc.scalar_one(),
            "proveedores_activos": proveedores_activos.scalar_one(),
        },
        "oc_por_estado": {row.estado.value: row.cnt for row in oc_por_estado.all()},
        "sol_por_estado": {row.estado.value: row.cnt for row in sol_por_estado.all()},
    }


# ── Solicitudes de Compra ──────────────────────────────────────────────────

class SolicitudItemIn(BaseModel):
    descripcion: str
    unidad: Optional[str] = None
    cantidad: float = 1
    precio_estimado: Optional[float] = None
    especificaciones: Optional[str] = None


class SolicitudCreate(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    categoria: CategoriaSCM = CategoriaSCM.OTROS
    prioridad: PrioridadSCM = PrioridadSCM.MEDIA
    fecha_requerida: Optional[date] = None
    presupuesto_estimado: Optional[float] = None
    moneda: str = "COP"
    justificacion: Optional[str] = None
    proveedor_id: Optional[int] = None
    items: List[SolicitudItemIn] = []


class AprobarRechazarIn(BaseModel):
    motivo: Optional[str] = None


@router.get("/solicitudes")
async def listar_solicitudes(
    estado: Optional[str] = Query(None),
    prioridad: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    conds = [ScmSolicitudCompra.activo == True]
    if estado:
        conds.append(ScmSolicitudCompra.estado == EstadoSolicitudSCM(estado))
    if prioridad:
        conds.append(ScmSolicitudCompra.prioridad == PrioridadSCM(prioridad))
    where = and_(*conds)

    total_res = await db.execute(select(func.count(ScmSolicitudCompra.id)).where(where))
    total = total_res.scalar_one()

    result = await db.execute(
        select(ScmSolicitudCompra).where(where)
        .options(selectinload(ScmSolicitudCompra.items))
        .order_by(ScmSolicitudCompra.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = list(result.scalars().all())
    return {
        "items": [_solicitud_to_dict(s, include_items=True) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/solicitudes", status_code=201)
async def crear_solicitud(
    data: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if not data.items and (await _parametros(db)).solicitud_exige_items:
        raise HTTPException(422, "La solicitud necesita al menos un ítem (Configuración de SCM).")
    numero = await _gen_numero_solicitud(db)
    presupuesto = data.presupuesto_estimado
    if not presupuesto and data.items:
        presupuesto = sum(
            (i.cantidad * (i.precio_estimado or 0)) for i in data.items
        )

    sol = ScmSolicitudCompra(
        numero=numero,
        solicitante_id=current_user.id,
        titulo=data.titulo,
        descripcion=data.descripcion,
        categoria=data.categoria,
        prioridad=data.prioridad,
        estado=EstadoSolicitudSCM.BORRADOR,
        fecha_requerida=data.fecha_requerida,
        presupuesto_estimado=presupuesto,
        moneda=data.moneda,
        justificacion=data.justificacion,
        proveedor_id=data.proveedor_id,
    )
    db.add(sol)
    await db.flush()

    for item_data in data.items:
        total_est = item_data.cantidad * (item_data.precio_estimado or 0)
        item = ScmSolicitudItem(
            solicitud_id=sol.id,
            descripcion=item_data.descripcion,
            unidad=item_data.unidad,
            cantidad=item_data.cantidad,
            precio_estimado=item_data.precio_estimado,
            total_estimado=total_est or None,
            especificaciones=item_data.especificaciones,
        )
        db.add(item)

    await db.commit()
    await db.refresh(sol)
    return _solicitud_to_dict(sol)


@router.put("/solicitudes/{solicitud_id}/enviar")
async def enviar_solicitud(
    solicitud_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    sol = await db.get(ScmSolicitudCompra, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if sol.estado != EstadoSolicitudSCM.BORRADOR:
        raise HTTPException(status_code=400, detail="Solo se pueden enviar solicitudes en borrador")
    sol.estado = EstadoSolicitudSCM.PENDIENTE
    await db.commit()
    return _solicitud_to_dict(sol)


@router.put("/solicitudes/{solicitud_id}/aprobar")
async def aprobar_solicitud(
    solicitud_id: int,
    body: AprobarRechazarIn = AprobarRechazarIn(),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    sol = await db.get(ScmSolicitudCompra, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    sol.estado = EstadoSolicitudSCM.APROBADA
    sol.aprobador_id = current_user.id
    sol.fecha_aprobacion = date.today()
    await db.commit()
    return _solicitud_to_dict(sol)


@router.put("/solicitudes/{solicitud_id}/rechazar")
async def rechazar_solicitud(
    solicitud_id: int,
    body: AprobarRechazarIn,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    sol = await db.get(ScmSolicitudCompra, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    sol.estado = EstadoSolicitudSCM.RECHAZADA
    sol.aprobador_id = current_user.id
    sol.motivo_rechazo = body.motivo
    await db.commit()
    return _solicitud_to_dict(sol)


# ── Órdenes de Compra ─────────────────────────────────────────────────────

class OrdenItemIn(BaseModel):
    descripcion: str
    codigo_producto: Optional[str] = None
    unidad: Optional[str] = None
    cantidad: float = 1
    precio_unitario: float = 0
    descuento_pct: Optional[float] = 0
    especificaciones: Optional[str] = None


class OrdenCreate(BaseModel):
    proveedor_id: int
    solicitud_id: Optional[int] = None
    categoria: CategoriaSCM = CategoriaSCM.OTROS
    prioridad: PrioridadSCM = PrioridadSCM.MEDIA
    fecha_entrega_esperada: Optional[date] = None
    moneda: str = "COP"
    condiciones_pago: Optional[str] = None
    lugar_entrega: Optional[str] = None
    notas: Optional[str] = None
    impuestos_pct: float = 19.0
    items: List[OrdenItemIn] = []


class EstadoUpdate(BaseModel):
    estado: EstadoOrdenSCM
    fecha_entrega_real: Optional[date] = None
    notas: Optional[str] = None


@router.get("/ordenes-compra")
async def listar_ordenes(
    estado: Optional[str] = Query(None),
    proveedor_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    conds = [ScmOrdenCompra.activo == True]
    if estado:
        conds.append(ScmOrdenCompra.estado == EstadoOrdenSCM(estado))
    if proveedor_id:
        conds.append(ScmOrdenCompra.proveedor_id == proveedor_id)
    where = and_(*conds)

    total_res = await db.execute(select(func.count(ScmOrdenCompra.id)).where(where))
    total = total_res.scalar_one()

    result = await db.execute(
        select(ScmOrdenCompra).where(where)
        .options(selectinload(ScmOrdenCompra.items))
        .order_by(ScmOrdenCompra.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = list(result.scalars().all())
    # El cliente declaraba `proveedor_nombre` y el servidor nunca lo mandaba:
    # la lista de órdenes mostraba solo el número del proveedor.
    nombres = await _nombres_proveedores(db, [o.proveedor_id for o in items])
    return {
        "items": [{**_orden_to_dict(o, include_items=True), "proveedor_nombre": nombres.get(o.proveedor_id)}
                  for o in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/ordenes-compra", status_code=201)
async def crear_orden(
    data: OrdenCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    proveedor = await db.get(Proveedor, data.proveedor_id)
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    numero = await _gen_numero_orden(db)

    subtotal = sum(
        item.cantidad * item.precio_unitario * (1 - (item.descuento_pct or 0) / 100)
        for item in data.items
    )
    impuestos = subtotal * data.impuestos_pct / 100
    total = subtotal + impuestos

    orden = ScmOrdenCompra(
        numero=numero,
        solicitud_id=data.solicitud_id,
        proveedor_id=data.proveedor_id,
        creado_por_id=current_user.id,
        estado=EstadoOrdenSCM.BORRADOR,
        categoria=data.categoria,
        prioridad=data.prioridad,
        fecha_emision=date.today(),
        fecha_entrega_esperada=data.fecha_entrega_esperada,
        moneda=data.moneda,
        condiciones_pago=data.condiciones_pago,
        lugar_entrega=data.lugar_entrega,
        notas=data.notas,
        subtotal=round(subtotal, 2),
        impuestos=round(impuestos, 2),
        total=round(total, 2),
    )
    db.add(orden)
    await db.flush()

    for item_data in data.items:
        item_total = (
            item_data.cantidad
            * item_data.precio_unitario
            * (1 - (item_data.descuento_pct or 0) / 100)
        )
        item = ScmOrdenItem(
            orden_id=orden.id,
            descripcion=item_data.descripcion,
            codigo_producto=item_data.codigo_producto,
            unidad=item_data.unidad,
            cantidad=item_data.cantidad,
            precio_unitario=item_data.precio_unitario,
            descuento_pct=item_data.descuento_pct,
            total=round(item_total, 2),
            especificaciones=item_data.especificaciones,
        )
        db.add(item)

    await db.commit()
    await db.refresh(orden)
    return _orden_to_dict(orden)


@router.get("/ordenes-compra/{orden_id}")
async def detalle_orden(
    orden_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(ScmOrdenCompra).where(ScmOrdenCompra.id == orden_id)
        .options(selectinload(ScmOrdenCompra.items))
    )
    orden = result.scalar_one_or_none()
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return _orden_to_dict(orden, include_items=True)


@router.put("/ordenes-compra/{orden_id}/estado")
async def actualizar_estado_orden(
    orden_id: int,
    body: EstadoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    orden = await db.get(ScmOrdenCompra, orden_id)
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    # Doble aprobación: una OC grande no sale del borrador con una sola firma.
    # La envía un administrador distinto de quien la creó, y queda registrado.
    tope = (await _parametros(db)).monto_doble_aprobacion
    if (orden.estado == EstadoOrdenSCM.BORRADOR and body.estado != EstadoOrdenSCM.CANCELADA
            and body.estado != EstadoOrdenSCM.BORRADOR and tope and (orden.total or 0) > tope):
        rol = getattr(current_user.rol, "value", current_user.rol)
        if rol != RolUsuario.ADMINISTRADOR.value or current_user.id == orden.creado_por_id:
            raise HTTPException(403, (
                f"Esta orden supera ${tope:,.0f}: la debe aprobar un administrador distinto "
                "de quien la creó.").replace(",", "."))
        orden.aprobado_por_id = current_user.id
    orden.estado = body.estado
    if body.fecha_entrega_real:
        orden.fecha_entrega_real = body.fecha_entrega_real
    if body.notas:
        orden.notas = body.notas
    await db.commit()
    return _orden_to_dict(orden)


# ── Evaluaciones de Proveedor ──────────────────────────────────────────────

class EvaluacionCreate(BaseModel):
    proveedor_id: int
    periodo: str
    calidad: Optional[float] = None
    tiempo_entrega: Optional[float] = None
    precio: Optional[float] = None
    servicio: Optional[float] = None
    documentacion: Optional[float] = None
    comentarios: Optional[str] = None
    recomendacion: Optional[RecomendacionProveedor] = None


@router.get("/evaluaciones/proveedor/{proveedor_id}")
async def evaluaciones_proveedor(
    proveedor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(ScmEvaluacionProveedor)
        .where(ScmEvaluacionProveedor.proveedor_id == proveedor_id)
        .order_by(ScmEvaluacionProveedor.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": e.id,
            "periodo": e.periodo,
            "calidad": e.calidad,
            "tiempo_entrega": e.tiempo_entrega,
            "precio": e.precio,
            "servicio": e.servicio,
            "documentacion": e.documentacion,
            "puntaje_total": e.puntaje_total,
            "clasificacion": e.clasificacion.value if e.clasificacion else None,
            "comentarios": e.comentarios,
            "recomendacion": e.recomendacion.value if e.recomendacion else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


@router.post("/evaluaciones", status_code=201)
async def crear_evaluacion(
    data: EvaluacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    scores = [v for v in [data.calidad, data.tiempo_entrega, data.precio, data.servicio, data.documentacion] if v is not None]
    puntaje = round(sum(scores) / len(scores), 2) if scores else None

    clasificacion = None
    if puntaje is not None:
        if puntaje >= 8.5:
            clasificacion = ClasificacionProveedor.A
        elif puntaje >= 7.0:
            clasificacion = ClasificacionProveedor.B
        elif puntaje >= 5.5:
            clasificacion = ClasificacionProveedor.C
        else:
            clasificacion = ClasificacionProveedor.D

    ev = ScmEvaluacionProveedor(
        proveedor_id=data.proveedor_id,
        evaluador_id=current_user.id,
        periodo=data.periodo,
        calidad=data.calidad,
        tiempo_entrega=data.tiempo_entrega,
        precio=data.precio,
        servicio=data.servicio,
        documentacion=data.documentacion,
        puntaje_total=puntaje,
        clasificacion=clasificacion,
        comentarios=data.comentarios,
        recomendacion=data.recomendacion,
    )
    db.add(ev)
    await db.commit()
    return {"id": ev.id, "puntaje_total": puntaje, "clasificacion": clasificacion.value if clasificacion else None}


# ── Proveedores SCM ────────────────────────────────────────────────────────

@router.get("/proveedores")
async def proveedores_scm(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    conds = [Proveedor.activo == True]
    if q:
        conds.append(Proveedor.razon_social.ilike(f"%{q}%"))
    where = and_(*conds)

    total_res = await db.execute(select(func.count(Proveedor.id)).where(where))
    total = total_res.scalar_one()

    result = await db.execute(
        select(Proveedor).where(where)
        .order_by(Proveedor.razon_social)
        .offset((page - 1) * page_size).limit(page_size)
    )
    proveedores = result.scalars().all()

    prov_ids = [p.id for p in proveedores]
    oc_counts: dict = {}
    if prov_ids:
        oc_res = await db.execute(
            select(ScmOrdenCompra.proveedor_id, func.count(ScmOrdenCompra.id).label("cnt"))
            .where(ScmOrdenCompra.proveedor_id.in_(prov_ids))
            .group_by(ScmOrdenCompra.proveedor_id)
        )
        oc_counts = {row.proveedor_id: row.cnt for row in oc_res.all()}

    eval_res = await db.execute(
        select(
            ScmEvaluacionProveedor.proveedor_id,
            func.avg(ScmEvaluacionProveedor.puntaje_total).label("prom"),
            func.max(ScmEvaluacionProveedor.clasificacion).label("cls"),
        )
        .where(ScmEvaluacionProveedor.proveedor_id.in_(prov_ids))
        .group_by(ScmEvaluacionProveedor.proveedor_id)
    )
    eval_map: dict = {row.proveedor_id: {"prom": row.prom, "cls": row.cls} for row in eval_res.all()}

    items = []
    for p in proveedores:
        ev = eval_map.get(p.id, {})
        items.append({
            "id": p.id,
            "nit": p.nit,
            "razon_social": p.razon_social,
            "nombre_comercial": p.nombre_comercial,
            "tipo": p.tipo,
            "contacto_nombre": p.contacto_nombre,
            "contacto_email": p.contacto_email,
            "ciudad": p.ciudad,
            "total_ordenes": oc_counts.get(p.id, 0),
            "puntaje_promedio": round(ev.get("prom") or 0, 1) if ev.get("prom") else None,
            "clasificacion": ev.get("cls").value if ev.get("cls") else None,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ═════════════════════════════════════════════════════════════════════════════
# INVENTARIO, ENTRANTES, REPOSICIÓN, DEVOLUCIONES Y RIESGOS
#
# Las cinco pantallas eran maqueta: bodegas con «$ 3.8 B», embarques desde
# Shanghái, un «accuracy forecast 82 %» y planes con presupuesto inventado.
# Nada de eso existía. Lo que sí existe se cruza aquí:
#   - el inventario real (existencias por bodega del módulo de inventario),
#   - las órdenes de compra abiertas, que dicen qué viene en camino,
#   - las salidas de inventario, que dicen cuánto se consume.
# Las devoluciones y los riesgos no tenían tabla; ahora la tienen.
# ═════════════════════════════════════════════════════════════════════════════

from datetime import datetime, timedelta, timezone
from app.infrastructure.models.scm import ScmDevolucion, ScmRiesgo
from app.infrastructure.models.inventario import InvBodega, InvExistencia, InvMovimiento
from app.infrastructure.models.eam import EAMRepuesto

# Estados en que una orden todavía no ha llegado del todo.
_OC_EN_CAMINO = [EstadoOrdenSCM.ENVIADA, EstadoOrdenSCM.CONFIRMADA,
                 EstadoOrdenSCM.EN_TRANSITO, EstadoOrdenSCM.RECIBIDA_PARCIAL]


def _v(x):
    return x.value if hasattr(x, "value") else x


async def _nombres_proveedores(db: AsyncSession, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    r = await db.execute(select(Proveedor.id, Proveedor.razon_social).where(Proveedor.id.in_(ids)))
    return dict(r.all())


async def _en_camino_por_codigo(db: AsyncSession) -> dict:
    """Unidades pedidas y aún no recibidas, por código de producto."""
    r = await db.execute(
        select(ScmOrdenItem.codigo_producto,
               func.sum(ScmOrdenItem.cantidad - func.coalesce(ScmOrdenItem.cantidad_recibida, 0)))
        .join(ScmOrdenCompra, ScmOrdenCompra.id == ScmOrdenItem.orden_id)
        .where(ScmOrdenCompra.deleted_at.is_(None), ScmOrdenCompra.estado.in_(_OC_EN_CAMINO),
               ScmOrdenItem.codigo_producto.isnot(None))
        .group_by(ScmOrdenItem.codigo_producto))
    return {c: float(q or 0) for c, q in r.all() if (q or 0) > 0}


# ─── Inventario ──────────────────────────────────────────────────────────────

@router.get("/inventario")
async def inventario_scm(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Bodegas con su valor y referencias, y lo que está bajo el mínimo."""
    filas = (await db.execute(
        select(InvExistencia, EAMRepuesto, InvBodega)
        .join(EAMRepuesto, EAMRepuesto.id == InvExistencia.repuesto_id)
        .join(InvBodega, InvBodega.id == InvExistencia.bodega_id)
        .where(InvBodega.activo.is_(True)))).all()
    en_camino = await _en_camino_por_codigo(db)

    bodegas: dict = {}
    alertas = []
    for e, rep, b in filas:
        g = bodegas.setdefault(b.id, {"id": b.id, "nombre": b.nombre, "codigo": b.codigo,
                                      "referencias": 0, "unidades": 0.0, "valor": 0.0, "bajo_minimo": 0})
        cant = e.cantidad or 0
        if cant != 0:
            g["referencias"] += 1
        g["unidades"] += cant
        g["valor"] += cant * (e.costo_promedio or 0)
        minimo = e.stock_minimo if e.stock_minimo is not None else rep.stock_minimo
        if minimo and cant < minimo:
            g["bajo_minimo"] += 1
            alertas.append({
                "repuesto_id": rep.id, "codigo": rep.codigo, "nombre": rep.nombre,
                "bodega": b.nombre, "cantidad": cant, "minimo": minimo,
                "en_camino": en_camino.get(rep.codigo, 0.0),
                # Crítico: sin existencias o por debajo de la mitad del mínimo.
                "nivel": "CRITICO" if cant <= 0 or cant < minimo / 2 else "BAJO",
            })
    for g in bodegas.values():
        g["valor"] = round(g["valor"], 2)
    # Un repuesto con mínimo que nunca ha entrado a ninguna bodega no tiene
    # fila de existencias, y sin esto no saldría en las alertas: es justo el
    # caso más grave, porque no hay ni una unidad.
    con_fila = {rep.id for _e, rep, _b in filas}
    for rep in (await db.execute(select(EAMRepuesto).where(EAMRepuesto.stock_minimo > 0))).scalars().all():
        if rep.id not in con_fila:
            alertas.append({"repuesto_id": rep.id, "codigo": rep.codigo, "nombre": rep.nombre,
                            "bodega": None, "cantidad": 0.0, "minimo": float(rep.stock_minimo),
                            "en_camino": en_camino.get(rep.codigo, 0.0), "nivel": "CRITICO"})
    alertas.sort(key=lambda a: (a["nivel"] != "CRITICO", a["cantidad"] / a["minimo"]))
    return {
        "bodegas": sorted(bodegas.values(), key=lambda g: -g["valor"]),
        "alertas": alertas,
        "valor_total": round(sum(g["valor"] for g in bodegas.values()), 2),
    }


# ─── Entrantes (logística de abastecimiento) ─────────────────────────────────

@router.get("/entrantes")
async def entrantes(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Órdenes de compra en camino y el cumplimiento de las ya recibidas.

    La puntualidad se mide contra la fecha esperada de la propia orden: una
    orden sin fecha esperada no cuenta ni a favor ni en contra.
    """
    hoy = date.today()
    abiertas = (await db.execute(
        select(ScmOrdenCompra).options(selectinload(ScmOrdenCompra.items))
        .where(ScmOrdenCompra.deleted_at.is_(None), ScmOrdenCompra.estado.in_(_OC_EN_CAMINO))
        .order_by(ScmOrdenCompra.fecha_entrega_esperada.asc().nullslast()))).scalars().all()
    inicio_mes = hoy.replace(day=1)
    recibidas = (await db.execute(
        select(ScmOrdenCompra).where(
            ScmOrdenCompra.deleted_at.is_(None),
            ScmOrdenCompra.estado.in_([EstadoOrdenSCM.RECIBIDA, EstadoOrdenSCM.CERRADA]),
            ScmOrdenCompra.fecha_entrega_real >= hoy - timedelta(days=90)))).scalars().all()
    prov = await _nombres_proveedores(db, [o.proveedor_id for o in list(abiertas) + list(recibidas)])

    medibles = [o for o in recibidas if o.fecha_entrega_esperada and o.fecha_entrega_real]
    a_tiempo = [o for o in medibles if o.fecha_entrega_real <= o.fecha_entrega_esperada]
    return {
        "en_camino": [{
            "id": o.id, "numero": o.numero, "estado": _v(o.estado), "proveedor": prov.get(o.proveedor_id),
            "categoria": _v(o.categoria), "total": o.total, "lugar_entrega": o.lugar_entrega,
            "fecha_emision": o.fecha_emision.isoformat() if o.fecha_emision else None,
            "fecha_esperada": o.fecha_entrega_esperada.isoformat() if o.fecha_entrega_esperada else None,
            "dias_atraso": (hoy - o.fecha_entrega_esperada).days
                           if o.fecha_entrega_esperada and o.fecha_entrega_esperada < hoy else 0,
            "unidades_pedidas": sum(i.cantidad or 0 for i in o.items),
            "unidades_recibidas": sum(i.cantidad_recibida or 0 for i in o.items),
        } for o in abiertas],
        "recibidas_90d": len(recibidas),
        "recibidas_mes": sum(1 for o in recibidas if o.fecha_entrega_real >= inicio_mes),
        "a_tiempo_pct": round(len(a_tiempo) * 100 / len(medibles), 1) if medibles else None,
        "medibles": len(medibles),
    }


# ─── Reposición (planificación) ──────────────────────────────────────────────

@router.get("/reposicion")
async def reposicion(dias: int = Query(90, ge=30, le=365), db: AsyncSession = Depends(get_db),
                     _: Usuario = Depends(get_current_user)):
    """Qué hay que pedir, con el consumo real y lo que ya viene en camino.

    Por referencia (sumando todas las bodegas): existencias, mínimo y máximo,
    consumo diario de los últimos `dias` (solo SALIDAS: un traslado entre
    bodegas no es consumo), días de cobertura y cantidad sugerida hasta el
    máximo —o dos veces el mínimo si no hay máximo— descontando lo pedido.
    """
    desde = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=dias)
    consumo = dict((await db.execute(
        select(InvMovimiento.repuesto_id, func.sum(func.abs(InvMovimiento.cantidad)))
        .where(InvMovimiento.tipo == "SALIDA", InvMovimiento.fecha >= desde)
        .group_by(InvMovimiento.repuesto_id))).all())
    filas = (await db.execute(
        select(EAMRepuesto, func.coalesce(func.sum(InvExistencia.cantidad), 0),
               func.sum(InvExistencia.stock_minimo), func.sum(InvExistencia.stock_maximo))
        .outerjoin(InvExistencia, InvExistencia.repuesto_id == EAMRepuesto.id)
        .group_by(EAMRepuesto.id))).all()
    en_camino = await _en_camino_por_codigo(db)

    salida = []
    for rep, cant, min_b, max_b in filas:
        minimo = float(min_b) if min_b is not None else (float(rep.stock_minimo) if rep.stock_minimo else None)
        if not minimo:
            continue
        cant = float(cant or 0)
        diario = float(consumo.get(rep.id, 0)) / dias
        camino = en_camino.get(rep.codigo, 0.0)
        objetivo = float(max_b) if max_b else minimo * 2
        sugerido = max(0.0, objetivo - cant - camino)
        if cant + camino >= minimo and not (diario and cant / diario < 15):
            continue
        salida.append({
            "repuesto_id": rep.id, "codigo": rep.codigo, "nombre": rep.nombre,
            "categoria": rep.categoria, "unidad": rep.unidad_medida,
            "existencias": cant, "minimo": minimo, "maximo": float(max_b) if max_b else None,
            "en_camino": camino, "consumo_diario": round(diario, 3),
            "dias_cobertura": round(cant / diario, 1) if diario else None,
            "sugerido": round(sugerido, 2),
        })
    salida.sort(key=lambda x: (x["dias_cobertura"] if x["dias_cobertura"] is not None else 9999))
    return {"dias_consumo": dias, "items": salida}


@router.get("/demanda")
async def demanda_por_categoria(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Valor comprado por categoría: últimos 90 días contra los 90 anteriores.

    Es la variación medida, no un pronóstico: la maqueta decía «forecast +28 %»
    sin que el sistema pronosticara nada.
    """
    hoy = date.today()
    corte, inicio = hoy - timedelta(days=90), hoy - timedelta(days=180)
    r = await db.execute(
        select(ScmOrdenCompra.categoria, ScmOrdenCompra.fecha_emision, ScmOrdenCompra.total)
        .where(ScmOrdenCompra.deleted_at.is_(None), ScmOrdenCompra.estado != EstadoOrdenSCM.CANCELADA,
               ScmOrdenCompra.fecha_emision >= inicio))
    g: dict = {}
    for cat, f, total in r.all():
        x = g.setdefault(_v(cat), {"categoria": _v(cat), "actual": 0.0, "anterior": 0.0})
        x["actual" if f >= corte else "anterior"] += total or 0
    for x in g.values():
        x["variacion_pct"] = round((x["actual"] - x["anterior"]) * 100 / x["anterior"], 1) if x["anterior"] else None
    return sorted(g.values(), key=lambda x: -x["actual"])


# ─── Devoluciones a proveedor ────────────────────────────────────────────────

MOTIVOS_DEV = ("DEFECTO_CALIDAD", "CANTIDAD_INCORRECTA", "PRODUCTO_EQUIVOCADO",
               "DANOS_TRANSPORTE", "VENCIMIENTO", "OTRO")
ESTADOS_DEV = ("PENDIENTE", "EN_PROCESO", "APROBADA", "RECHAZADA", "CERRADA")


class DevolucionIn(BaseModel):
    orden_id: int
    motivo: str
    fecha: date
    unidades: Optional[float] = None
    valor: Optional[float] = None
    descripcion: Optional[str] = None


class DevolucionEstadoIn(BaseModel):
    estado: str
    resolucion: Optional[str] = None
    valor_recuperado: Optional[float] = None


async def _dev_dict(db: AsyncSession, d: ScmDevolucion, oc: Optional[ScmOrdenCompra] = None, prov: Optional[dict] = None) -> dict:
    oc = oc or await db.get(ScmOrdenCompra, d.orden_id)
    prov = prov if prov is not None else await _nombres_proveedores(db, [oc.proveedor_id] if oc else [])
    return {
        "id": d.id, "numero": d.numero, "orden_id": d.orden_id, "orden_numero": oc.numero if oc else None,
        "proveedor_id": oc.proveedor_id if oc else None, "proveedor": prov.get(oc.proveedor_id) if oc else None,
        "motivo": d.motivo, "estado": d.estado, "fecha": d.fecha.isoformat(),
        "unidades": d.unidades, "valor": d.valor, "descripcion": d.descripcion,
        "resolucion": d.resolucion, "valor_recuperado": d.valor_recuperado,
        "fecha_cierre": d.fecha_cierre.isoformat() if d.fecha_cierre else None,
    }


async def _validar_dev(db: AsyncSession, data: DevolucionIn) -> ScmOrdenCompra:
    if data.motivo not in MOTIVOS_DEV:
        raise HTTPException(422, f"Motivo: uno de {MOTIVOS_DEV}")
    if data.fecha > date.today():
        raise HTTPException(422, "La fecha no puede ser futura")
    if (data.unidades is not None and data.unidades <= 0) or (data.valor is not None and data.valor < 0):
        raise HTTPException(422, "Unidades mayores que cero y valor no negativo")
    oc = await db.get(ScmOrdenCompra, data.orden_id)
    if not oc or oc.deleted_at is not None:
        raise HTTPException(404, "Orden de compra no encontrada")
    if data.valor and oc.total and data.valor > oc.total:
        raise HTTPException(422, "La devolución no puede valer más que la orden")
    return oc


@router.get("/devoluciones")
async def listar_devoluciones(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    filas = (await db.execute(
        select(ScmDevolucion, ScmOrdenCompra).join(ScmOrdenCompra, ScmOrdenCompra.id == ScmDevolucion.orden_id)
        .where(ScmDevolucion.deleted_at.is_(None)).order_by(ScmDevolucion.fecha.desc(), ScmDevolucion.id.desc()))).all()
    prov = await _nombres_proveedores(db, [oc.proveedor_id for _d, oc in filas])
    return [await _dev_dict(db, d, oc, prov) for d, oc in filas]


@router.post("/devoluciones", status_code=201)
async def crear_devolucion(data: DevolucionIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    oc = await _validar_dev(db, data)
    n = (await db.execute(select(func.count(ScmDevolucion.id)))).scalar_one() + 1
    d = ScmDevolucion(numero=f"SCM-DEV-{date.today().year}-{n:05d}", estado="PENDIENTE", **data.model_dump())
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return await _dev_dict(db, d, oc)


@router.put("/devoluciones/{did}")
async def editar_devolucion(did: int, data: DevolucionIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    d = await db.get(ScmDevolucion, did)
    if not d or d.deleted_at is not None:
        raise HTTPException(404, "Devolución no encontrada")
    if d.estado in ("CERRADA", "RECHAZADA"):
        raise HTTPException(400, "Una devolución cerrada o rechazada ya no se edita")
    oc = await _validar_dev(db, data)
    for k, v in data.model_dump().items():
        setattr(d, k, v)
    await db.commit()
    return await _dev_dict(db, d, oc)


@router.put("/devoluciones/{did}/estado")
async def estado_devolucion(did: int, data: DevolucionEstadoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    d = await db.get(ScmDevolucion, did)
    if not d or d.deleted_at is not None:
        raise HTTPException(404, "Devolución no encontrada")
    if data.estado not in ESTADOS_DEV:
        raise HTTPException(422, f"Estado: uno de {ESTADOS_DEV}")
    if data.estado in ("APROBADA", "RECHAZADA", "CERRADA") and not (data.resolucion or d.resolucion):
        raise HTTPException(422, "Registra la respuesta del proveedor")
    if data.valor_recuperado is not None and (data.valor_recuperado < 0 or (d.valor and data.valor_recuperado > d.valor)):
        raise HTTPException(422, "Lo recuperado no puede ser negativo ni mayor que el valor devuelto")
    d.estado = data.estado
    if data.resolucion is not None:
        d.resolucion = data.resolucion.strip() or None
    if data.valor_recuperado is not None:
        d.valor_recuperado = data.valor_recuperado
    d.fecha_cierre = date.today() if data.estado in ("CERRADA", "RECHAZADA") else None
    await db.commit()
    return await _dev_dict(db, d)


@router.delete("/devoluciones/{did}", status_code=204)
async def borrar_devolucion(did: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    d = await db.get(ScmDevolucion, did)
    if not d or d.deleted_at is not None:
        raise HTTPException(404, "Devolución no encontrada")
    d.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ─── Riesgos de suministro ───────────────────────────────────────────────────

CATEGORIAS_RIESGO = ("PROVEEDOR", "REGULATORIO", "OPERATIVO", "FINANCIERO", "TECNOLOGICO", "LOGISTICO", "OTRO")
ESTADOS_RIESGO = ("IDENTIFICADO", "EN_MITIGACION", "MITIGADO", "MATERIALIZADO")


class RiesgoIn(BaseModel):
    titulo: str
    categoria: str
    proveedor_id: Optional[int] = None
    impacto: int
    probabilidad: int
    estado: str = "IDENTIFICADO"
    responsable: Optional[str] = None
    descripcion: Optional[str] = None
    plan_mitigacion: Optional[str] = None
    fecha_revision: Optional[date] = None


def _nivel(impacto: int, prob: int) -> str:
    """Impacto (1-4) × probabilidad (1-3): hasta 12."""
    p = impacto * prob
    return "CRITICO" if p >= 9 else "ALTO" if p >= 6 else "MEDIO" if p >= 3 else "BAJO"


def _riesgo_dict(r: ScmRiesgo, prov: dict) -> dict:
    return {
        "id": r.id, "titulo": r.titulo, "categoria": r.categoria,
        "proveedor_id": r.proveedor_id, "proveedor": prov.get(r.proveedor_id),
        "impacto": r.impacto, "probabilidad": r.probabilidad,
        "puntaje": r.impacto * r.probabilidad, "nivel": _nivel(r.impacto, r.probabilidad),
        "estado": r.estado, "responsable": r.responsable, "descripcion": r.descripcion,
        "plan_mitigacion": r.plan_mitigacion,
        "fecha_revision": r.fecha_revision.isoformat() if r.fecha_revision else None,
    }


def _validar_riesgo(d: RiesgoIn):
    if not d.titulo.strip():
        raise HTTPException(422, "Falta el título")
    if d.categoria not in CATEGORIAS_RIESGO:
        raise HTTPException(422, f"Categoría: una de {CATEGORIAS_RIESGO}")
    if d.estado not in ESTADOS_RIESGO:
        raise HTTPException(422, f"Estado: uno de {ESTADOS_RIESGO}")
    if not 1 <= d.impacto <= 4 or not 1 <= d.probabilidad <= 3:
        raise HTTPException(422, "Impacto de 1 a 4 y probabilidad de 1 a 3")
    if d.estado == "EN_MITIGACION" and not (d.plan_mitigacion or "").strip():
        raise HTTPException(422, "Un riesgo en mitigación necesita su plan")


@router.get("/riesgos")
async def listar_riesgos(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    rs = (await db.execute(select(ScmRiesgo).where(ScmRiesgo.deleted_at.is_(None)))).scalars().all()
    prov = await _nombres_proveedores(db, [r.proveedor_id for r in rs])
    return sorted([_riesgo_dict(r, prov) for r in rs], key=lambda x: -x["puntaje"])


@router.post("/riesgos", status_code=201)
async def crear_riesgo(data: RiesgoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_riesgo(data)
    r = ScmRiesgo(**data.model_dump())
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return _riesgo_dict(r, await _nombres_proveedores(db, [r.proveedor_id]))


@router.put("/riesgos/{rid}")
async def editar_riesgo(rid: int, data: RiesgoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_riesgo(data)
    r = await db.get(ScmRiesgo, rid)
    if not r or r.deleted_at is not None:
        raise HTTPException(404, "Riesgo no encontrado")
    for k, v in data.model_dump().items():
        setattr(r, k, v)
    await db.commit()
    return _riesgo_dict(r, await _nombres_proveedores(db, [r.proveedor_id]))


@router.delete("/riesgos/{rid}", status_code=204)
async def borrar_riesgo(rid: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    r = await db.get(ScmRiesgo, rid)
    if not r or r.deleted_at is not None:
        raise HTTPException(404, "Riesgo no encontrado")
    r.deleted_at = datetime.now(timezone.utc)
    await db.commit()
