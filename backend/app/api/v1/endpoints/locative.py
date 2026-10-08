"""
API endpoints — Mantenimiento Locativo
Prefijo: /locativa
Normas: ISO 55001 · ISO 41001 · ISO 31000 · ISO 14224 · ISO 50001 · IAS 16/36
"""
from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, extract
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.locative import (
    LocativaSede, LocativaEspacio, LocativaCategoria, LocativaModoFalla,
    LocativaProveedor, LocativaActivo, LocativaActivoDocumento,
    LocativaCatalogoTarea, LocativaOrdenTrabajo, LocativaOTChecklist, LocativaOTMaterial,
    LocativaRegistroFalla, LocativaRiesgo, LocativaRiesgoTratamiento,
    LocativaMedidor, LocativaLecturaEnergia,
)
from app.application.schemas.locative import (
    LocativaSedeCreate, LocativaSedeUpdate, LocativaSedeResponse,
    LocativaEspacioCreate, LocativaEspacioUpdate, LocativaEspacioResponse,
    LocativaCategoriaCreate, LocativaCategoriaUpdate, LocativaCategoriaResponse,
    LocativaModoFallaCreate, LocativaModoFallaResponse,
    LocativaProveedorCreate, LocativaProveedorUpdate, LocativaProveedorResponse,
    LocativaActivoCreate, LocativaActivoUpdate, LocativaActivoResponse, LocativaActivoBaja,
    LocativaActivoDocumentoCreate, LocativaActivoDocumentoResponse,
    LocativaCatalogoTareaCreate, LocativaCatalogoTareaUpdate, LocativaCatalogoTareaResponse,
    LocativaOTCreate, LocativaOTUpdate, LocativaOTEstadoUpdate, LocativaOTResponse,
    LocativaFallaCreate, LocativaFallaResponse,
    LocativaRiesgoCreate, LocativaRiesgoUpdate, LocativaRiesgoResponse,
    LocativaRiesgoTratamientoCreate, LocativaRiesgoTratamientoUpdate, LocativaRiesgoTratamientoResponse,
    LocativaMedidorCreate, LocativaMedidorUpdate, LocativaMedidorResponse,
    LocativaLecturaCreate, LocativaLecturaResponse,
    LocativaKPIs,
)

router = APIRouter(prefix="/locativa", tags=["locativa"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _calcular_valor_libros(a: LocativaActivo) -> Optional[float]:
    if a.costo_adquisicion is None:
        return None
    return max(0.0, a.costo_adquisicion - (a.depreciacion_acumulada or 0) - (a.deterioro_acumulado or 0))


def _calcular_depreciacion_anual(a: LocativaActivo) -> Optional[float]:
    if not a.costo_adquisicion or not a.vida_util_anos or a.vida_util_anos <= 0:
        return None
    if a.metodo_depreciacion == "LINEA_RECTA":
        return (a.costo_adquisicion - (a.valor_residual or 0)) / a.vida_util_anos
    if a.metodo_depreciacion == "SALDOS_DECRECIENTES":
        vl = _calcular_valor_libros(a) or 0
        return vl * (2 / a.vida_util_anos)
    return None


def _semaforo_doc(fecha_venc: Optional[date]) -> Optional[str]:
    if not fecha_venc:
        return None
    dias = (fecha_venc - date.today()).days
    if dias < 0:
        return "VENCIDO"
    if dias <= 30:
        return "POR_VENCER"
    return "VIGENTE"


def _build_activo_response(a: LocativaActivo) -> dict:
    d = {c.name: getattr(a, c.name) for c in a.__table__.columns}
    d["valor_libros"] = _calcular_valor_libros(a)
    d["depreciacion_anual"] = _calcular_depreciacion_anual(a)
    return d


async def _generar_numero_ot(db: AsyncSession) -> str:
    r = await db.execute(select(func.count(LocativaOrdenTrabajo.id)))
    n = (r.scalar() or 0) + 1
    return f"OT-ML-{n:05d}"


async def _generar_codigo_riesgo(db: AsyncSession) -> str:
    r = await db.execute(select(func.count(LocativaRiesgo.id)))
    n = (r.scalar() or 0) + 1
    return f"RSK-{n:04d}"


# ─── Dashboard KPIs ────────────────────────────────────────────────────────────

@router.get("/dashboard/kpis", response_model=LocativaKPIs)
async def kpis_dashboard(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    hoy = date.today()
    mes_actual = hoy.month
    ano_actual = hoy.year

    # Activos
    r_activos = await db.execute(select(LocativaActivo).where(LocativaActivo.activo == True))
    activos = r_activos.scalars().all()
    total = len(activos)
    operativos = sum(1 for a in activos if a.estado == "OPERATIVO")
    en_mant = sum(1 for a in activos if a.estado == "EN_MANTENIMIENTO")
    fuera = sum(1 for a in activos if a.estado == "FUERA_SERVICIO")
    valor_libros = sum(_calcular_valor_libros(a) or 0 for a in activos)

    # OTs
    r_ots = await db.execute(select(LocativaOrdenTrabajo))
    ots = r_ots.scalars().all()
    ots_abiertas = sum(1 for o in ots if o.estado in ("ABIERTA", "ASIGNADA"))
    ots_prog = sum(1 for o in ots if o.estado == "EN_PROGRESO")
    ots_vencidas = sum(1 for o in ots if o.fecha_programada and o.fecha_programada < hoy and o.estado not in ("CERRADA", "CANCELADA", "VERIFICADA"))
    ots_cerradas_mes = sum(1 for o in ots if o.fecha_cierre and o.fecha_cierre.month == mes_actual and o.fecha_cierre.year == ano_actual)
    ots_prev_programadas = sum(1 for o in ots if o.tipo == "PREVENTIVO" and o.fecha_programada and o.fecha_programada.month == mes_actual and o.fecha_programada.year == ano_actual)
    ots_prev_cerradas = sum(1 for o in ots if o.tipo == "PREVENTIVO" and o.estado in ("CERRADA", "VERIFICADA") and o.fecha_cierre and o.fecha_cierre.month == mes_actual and o.fecha_cierre.year == ano_actual)
    cumplimiento = (ots_prev_cerradas / ots_prev_programadas * 100) if ots_prev_programadas > 0 else 0
    costo_mes = sum((o.costo_mano_obra or 0) + (o.costo_materiales or 0) + (o.costo_externo or 0) for o in ots if o.fecha_cierre and o.fecha_cierre.month == mes_actual and o.fecha_cierre.year == ano_actual)

    # Fallas
    r_fallas = await db.execute(select(LocativaRegistroFalla).where(
        extract("month", LocativaRegistroFalla.fecha_deteccion) == mes_actual,
        extract("year", LocativaRegistroFalla.fecha_deteccion) == ano_actual,
    ))
    fallas_mes = r_fallas.scalars().all()
    total_fallas = len(fallas_mes)
    mttr_vals = [f.tiempo_reparacion_hrs for f in fallas_mes if f.tiempo_reparacion_hrs]
    mttr = sum(mttr_vals) / len(mttr_vals) if mttr_vals else 0
    disponibilidad = max(0, 100 - (sum(f.horas_indisponibilidad or 0 for f in fallas_mes) / (total or 1) / 720 * 100))

    # Riesgos
    r_riesgos = await db.execute(select(LocativaRiesgo).where(LocativaRiesgo.estado != "CERRADO"))
    riesgos = r_riesgos.scalars().all()
    r_inacept = sum(1 for r in riesgos if r.aceptabilidad == "INACEPTABLE")
    r_toler = sum(1 for r in riesgos if r.aceptabilidad == "TOLERABLE")

    # Energía — mes actual
    r_lecturas = await db.execute(select(LocativaLecturaEnergia).where(
        extract("month", LocativaLecturaEnergia.fecha) == mes_actual,
        extract("year", LocativaLecturaEnergia.fecha) == ano_actual,
    ))
    lecturas = r_lecturas.scalars().all()
    consumo_mes = sum(l.consumo_periodo or 0 for l in lecturas)
    costo_energia = sum(l.costo_periodo or 0 for l in lecturas)

    # Documentos por vencer (< 30 días)
    r_docs = await db.execute(select(LocativaActivoDocumento).where(LocativaActivoDocumento.fecha_vencimiento != None))
    docs = r_docs.scalars().all()
    docs_por_vencer = sum(1 for d in docs if d.fecha_vencimiento and 0 <= (d.fecha_vencimiento - hoy).days <= 30)

    # Contratos por vencer
    r_provs = await db.execute(select(LocativaProveedor).where(LocativaProveedor.activo == True, LocativaProveedor.fecha_contrato_vencimiento != None))
    provs = r_provs.scalars().all()
    contratos_pv = sum(1 for p in provs if p.fecha_contrato_vencimiento and 0 <= (p.fecha_contrato_vencimiento - hoy).days <= 30)

    return LocativaKPIs(
        total_activos=total, activos_operativos=operativos,
        activos_mantenimiento=en_mant, activos_fuera_servicio=fuera,
        valor_libros_total=round(valor_libros, 2),
        ots_abiertas=ots_abiertas, ots_en_progreso=ots_prog,
        ots_vencidas=ots_vencidas, ots_cerradas_mes=ots_cerradas_mes,
        cumplimiento_preventivo=round(cumplimiento, 1),
        costo_mantenimiento_mes=round(costo_mes, 2),
        total_fallas_mes=total_fallas, mttr_promedio=round(mttr, 2),
        disponibilidad_promedio=round(disponibilidad, 1),
        riesgos_inaceptables=r_inacept, riesgos_tolerables=r_toler,
        riesgos_total=len(riesgos),
        consumo_energia_mes=round(consumo_mes, 2),
        costo_energia_mes=round(costo_energia, 2),
        documentos_por_vencer=docs_por_vencer,
        contratos_por_vencer=contratos_pv,
    )


# ─── Sedes ────────────────────────────────────────────────────────────────────

@router.get("/sedes/", response_model=List[LocativaSedeResponse])
async def listar_sedes(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(LocativaSede).order_by(LocativaSede.nombre))
    return r.scalars().all()

@router.post("/sedes/", response_model=LocativaSedeResponse, status_code=201)
async def crear_sede(data: LocativaSedeCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaSede(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/sedes/{sede_id}", response_model=LocativaSedeResponse)
async def actualizar_sede(sede_id: int, data: LocativaSedeUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaSede, sede_id)
    if not obj: raise HTTPException(404, "Sede no encontrada")
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/sedes/{sede_id}", status_code=204)
async def eliminar_sede(sede_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaSede, sede_id)
    if not obj: raise HTTPException(404, "Sede no encontrada")
    await db.delete(obj); await db.commit()


# ─── Espacios ─────────────────────────────────────────────────────────────────

@router.get("/espacios/", response_model=List[LocativaEspacioResponse])
async def listar_espacios(sede_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(LocativaEspacio).order_by(LocativaEspacio.nombre)
    if sede_id: q = q.where(LocativaEspacio.sede_id == sede_id)
    r = await db.execute(q); return r.scalars().all()

@router.post("/espacios/", response_model=LocativaEspacioResponse, status_code=201)
async def crear_espacio(data: LocativaEspacioCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaEspacio(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/espacios/{espacio_id}", response_model=LocativaEspacioResponse)
async def actualizar_espacio(espacio_id: int, data: LocativaEspacioUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaEspacio, espacio_id)
    if not obj: raise HTTPException(404, "Espacio no encontrado")
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/espacios/{espacio_id}", status_code=204)
async def eliminar_espacio(espacio_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaEspacio, espacio_id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ─── Categorías ────────────────────────────────────────────────────────────────

@router.get("/categorias/", response_model=List[LocativaCategoriaResponse])
async def listar_categorias(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(LocativaCategoria).order_by(LocativaCategoria.nombre))
    return r.scalars().all()

@router.post("/categorias/", response_model=LocativaCategoriaResponse, status_code=201)
async def crear_categoria(data: LocativaCategoriaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaCategoria(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/categorias/{cat_id}", response_model=LocativaCategoriaResponse)
async def actualizar_categoria(cat_id: int, data: LocativaCategoriaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaCategoria, cat_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/categorias/{cat_id}", status_code=204)
async def eliminar_categoria(cat_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaCategoria, cat_id)
    if not obj: raise HTTPException(404)
    obj.activo = False; await db.commit()


# ─── Modos de Falla ────────────────────────────────────────────────────────────

@router.get("/modos-falla/", response_model=List[LocativaModoFallaResponse])
async def listar_modos_falla(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(LocativaModoFalla).where(LocativaModoFalla.activo == True).order_by(LocativaModoFalla.nombre))
    return r.scalars().all()

@router.post("/modos-falla/", response_model=LocativaModoFallaResponse, status_code=201)
async def crear_modo_falla(data: LocativaModoFallaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaModoFalla(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj


# ─── Proveedores ───────────────────────────────────────────────────────────────

@router.get("/proveedores/", response_model=List[LocativaProveedorResponse])
async def listar_proveedores(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(LocativaProveedor).where(LocativaProveedor.activo == True).order_by(LocativaProveedor.nombre))
    return r.scalars().all()

@router.post("/proveedores/", response_model=LocativaProveedorResponse, status_code=201)
async def crear_proveedor(data: LocativaProveedorCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaProveedor(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/proveedores/{prov_id}", response_model=LocativaProveedorResponse)
async def actualizar_proveedor(prov_id: int, data: LocativaProveedorUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaProveedor, prov_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/proveedores/{prov_id}", status_code=204)
async def eliminar_proveedor(prov_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaProveedor, prov_id)
    if not obj: raise HTTPException(404)
    obj.activo = False; await db.commit()


# ─── Activos ───────────────────────────────────────────────────────────────────

@router.get("/activos/", response_model=List[LocativaActivoResponse])
async def listar_activos(
    estado: Optional[str] = None,
    criticidad: Optional[str] = None,
    sede_id: Optional[int] = None,
    categoria_id: Optional[int] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(LocativaActivo).where(LocativaActivo.activo == True).order_by(LocativaActivo.nombre)
    if estado: stmt = stmt.where(LocativaActivo.estado == estado)
    if criticidad: stmt = stmt.where(LocativaActivo.criticidad == criticidad)
    if sede_id: stmt = stmt.where(LocativaActivo.sede_id == sede_id)
    if categoria_id: stmt = stmt.where(LocativaActivo.categoria_id == categoria_id)
    r = await db.execute(stmt)
    activos = r.scalars().all()
    return [_build_activo_response(a) for a in activos]

@router.get("/activos/{activo_id}", response_model=LocativaActivoResponse)
async def obtener_activo(activo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaActivo, activo_id)
    if not obj or not obj.activo: raise HTTPException(404, "Activo no encontrado")
    return _build_activo_response(obj)

@router.post("/activos/", response_model=LocativaActivoResponse, status_code=201)
async def crear_activo(data: LocativaActivoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaActivo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return _build_activo_response(obj)

@router.put("/activos/{activo_id}", response_model=LocativaActivoResponse)
async def actualizar_activo(activo_id: int, data: LocativaActivoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaActivo, activo_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return _build_activo_response(obj)

@router.patch("/activos/{activo_id}/baja", response_model=LocativaActivoResponse)
async def dar_baja_activo(activo_id: int, data: LocativaActivoBaja, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaActivo, activo_id)
    if not obj: raise HTTPException(404)
    obj.estado = "BAJA"; obj.activo = False
    obj.fecha_baja = data.fecha_baja; obj.motivo_baja = data.motivo_baja
    obj.valor_rescate = data.valor_rescate
    obj.depreciacion_acumulada = _calcular_valor_libros(obj) or 0
    await db.commit(); await db.refresh(obj)
    return _build_activo_response(obj)

@router.delete("/activos/{activo_id}", status_code=204)
async def eliminar_activo(activo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaActivo, activo_id)
    if not obj: raise HTTPException(404)
    obj.activo = False; await db.commit()


# ─── Documentos de Activo ──────────────────────────────────────────────────────

@router.get("/activos/{activo_id}/documentos", response_model=List[LocativaActivoDocumentoResponse])
async def listar_documentos_activo(activo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(LocativaActivoDocumento).where(LocativaActivoDocumento.activo_id == activo_id))
    docs = r.scalars().all()
    result = []
    for d in docs:
        rd = {c.name: getattr(d, c.name) for c in d.__table__.columns}
        rd["estado_semaforo"] = _semaforo_doc(d.fecha_vencimiento)
        result.append(rd)
    return result

@router.post("/activos/{activo_id}/documentos", response_model=LocativaActivoDocumentoResponse, status_code=201)
async def crear_documento_activo(activo_id: int, data: LocativaActivoDocumentoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    data_dict = data.model_dump(); data_dict["activo_id"] = activo_id
    obj = LocativaActivoDocumento(**data_dict)
    db.add(obj); await db.commit(); await db.refresh(obj)
    rd = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    rd["estado_semaforo"] = _semaforo_doc(obj.fecha_vencimiento)
    return rd

@router.get("/activos/documentos/alertas", response_model=List[LocativaActivoDocumentoResponse])
async def alertas_documentos(
    estado: str = Query("POR_VENCER", description="VENCIDO, POR_VENCER o VIGENTE"),
    dias: int = Query(30, ge=1, le=365,
                      description="Cuántos días adelante cuentan como «por vencer»"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los documentos de activos vencidos o por vencer.

    El tablero de Locativa lo pedía desde el primer día y no existía: la llamada
    caía en el DELETE de documentos y respondía 405. La pantalla lo envolvía en
    un `.catch(() => [])`, así que mostraba cero vencidos para siempre y nadie
    veía ningún error —que es peor que la pantalla rota, porque un cero se lee
    como «no hay nada pendiente».
    """
    hoy = date.today()
    q = select(LocativaActivoDocumento).where(
        LocativaActivoDocumento.fecha_vencimiento.isnot(None))
    if estado == "VENCIDO":
        q = q.where(LocativaActivoDocumento.fecha_vencimiento < hoy)
    elif estado == "POR_VENCER":
        q = q.where(LocativaActivoDocumento.fecha_vencimiento >= hoy,
                    LocativaActivoDocumento.fecha_vencimiento
                    <= hoy + timedelta(days=dias))
    elif estado == "VIGENTE":
        q = q.where(LocativaActivoDocumento.fecha_vencimiento
                    > hoy + timedelta(days=dias))

    docs = (await db.execute(
        q.order_by(LocativaActivoDocumento.fecha_vencimiento.asc()).limit(200)
    )).scalars().all()
    salida = []
    for d in docs:
        fila = {c.name: getattr(d, c.name) for c in d.__table__.columns}
        fila["estado_semaforo"] = _semaforo_doc(d.fecha_vencimiento)
        salida.append(fila)
    return salida


@router.delete("/activos/documentos/{doc_id}", status_code=204)
async def eliminar_documento(doc_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaActivoDocumento, doc_id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ─── Catálogo de Tareas ────────────────────────────────────────────────────────

@router.get("/catalogo-tareas/", response_model=List[LocativaCatalogoTareaResponse])
async def listar_catalogo_tareas(tipo: Optional[str] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(LocativaCatalogoTarea).where(LocativaCatalogoTarea.activo == True).order_by(LocativaCatalogoTarea.nombre)
    if tipo: q = q.where(LocativaCatalogoTarea.tipo == tipo)
    r = await db.execute(q); return r.scalars().all()

@router.post("/catalogo-tareas/", response_model=LocativaCatalogoTareaResponse, status_code=201)
async def crear_tarea_catalogo(data: LocativaCatalogoTareaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaCatalogoTarea(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/catalogo-tareas/{tarea_id}", response_model=LocativaCatalogoTareaResponse)
async def actualizar_tarea_catalogo(tarea_id: int, data: LocativaCatalogoTareaUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaCatalogoTarea, tarea_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/catalogo-tareas/{tarea_id}", status_code=204)
async def eliminar_tarea_catalogo(tarea_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaCatalogoTarea, tarea_id)
    if not obj: raise HTTPException(404)
    obj.activo = False; await db.commit()


# ─── Órdenes de Trabajo ────────────────────────────────────────────────────────

@router.get("/ordenes/", response_model=List[LocativaOTResponse])
async def listar_ordenes(
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    activo_id: Optional[int] = None,
    sede_id: Optional[int] = None,
    prioridad: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = (
        select(LocativaOrdenTrabajo)
        .options(selectinload(LocativaOrdenTrabajo.checklist), selectinload(LocativaOrdenTrabajo.materiales))
        .order_by(LocativaOrdenTrabajo.fecha_apertura.desc())
    )
    if estado: stmt = stmt.where(LocativaOrdenTrabajo.estado == estado)
    if tipo: stmt = stmt.where(LocativaOrdenTrabajo.tipo == tipo)
    if activo_id: stmt = stmt.where(LocativaOrdenTrabajo.activo_id == activo_id)
    if sede_id: stmt = stmt.where(LocativaOrdenTrabajo.sede_id == sede_id)
    if prioridad: stmt = stmt.where(LocativaOrdenTrabajo.prioridad == prioridad)
    r = await db.execute(stmt)
    ots = r.scalars().all()
    result = []
    for o in ots:
        d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
        d["checklist"] = [{"id": c.id, "paso": c.paso, "descripcion": c.descripcion, "completado": c.completado, "observacion": c.observacion} for c in o.checklist]
        d["materiales"] = [{"id": m.id, "descripcion": m.descripcion, "cantidad": m.cantidad, "unidad": m.unidad, "costo_unitario": m.costo_unitario, "costo_total": m.costo_total} for m in o.materiales]
        d["costo_total"] = (o.costo_mano_obra or 0) + (o.costo_materiales or 0) + (o.costo_externo or 0)
        result.append(d)
    return result

@router.get("/ordenes/{ot_id}", response_model=LocativaOTResponse)
async def obtener_orden(ot_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    stmt = select(LocativaOrdenTrabajo).where(LocativaOrdenTrabajo.id == ot_id).options(
        selectinload(LocativaOrdenTrabajo.checklist), selectinload(LocativaOrdenTrabajo.materiales)
    )
    r = await db.execute(stmt); o = r.scalar_one_or_none()
    if not o: raise HTTPException(404, "Orden no encontrada")
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    d["checklist"] = [{"id": c.id, "paso": c.paso, "descripcion": c.descripcion, "completado": c.completado, "observacion": c.observacion} for c in o.checklist]
    d["materiales"] = [{"id": m.id, "descripcion": m.descripcion, "cantidad": m.cantidad, "unidad": m.unidad, "costo_unitario": m.costo_unitario, "costo_total": m.costo_total} for m in o.materiales]
    d["costo_total"] = (o.costo_mano_obra or 0) + (o.costo_materiales or 0) + (o.costo_externo or 0)
    return d

@router.post("/ordenes/", response_model=LocativaOTResponse, status_code=201)
async def crear_orden(data: LocativaOTCreate, db: AsyncSession = Depends(get_db), user: Usuario = Depends(get_current_user)):
    checklist_data = data.checklist; materiales_data = data.materiales
    ot_data = data.model_dump(exclude={"checklist", "materiales"})
    ot_data["numero"] = await _generar_numero_ot(db)
    ot_data["creado_por_id"] = user.id
    ot = LocativaOrdenTrabajo(**ot_data)
    db.add(ot); await db.flush()
    for i, item in enumerate(checklist_data):
        db.add(LocativaOTChecklist(orden_id=ot.id, paso=item.paso or i + 1, descripcion=item.descripcion))
    for mat in materiales_data:
        costo_total = (mat.cantidad * mat.costo_unitario) if mat.costo_unitario else None
        db.add(LocativaOTMaterial(orden_id=ot.id, descripcion=mat.descripcion, cantidad=mat.cantidad, unidad=mat.unidad, costo_unitario=mat.costo_unitario, costo_total=costo_total))
    await db.commit()
    stmt = select(LocativaOrdenTrabajo).where(LocativaOrdenTrabajo.id == ot.id).options(
        selectinload(LocativaOrdenTrabajo.checklist), selectinload(LocativaOrdenTrabajo.materiales)
    )
    r = await db.execute(stmt); o = r.scalar_one()
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    d["checklist"] = [{"id": c.id, "paso": c.paso, "descripcion": c.descripcion, "completado": c.completado, "observacion": c.observacion} for c in o.checklist]
    d["materiales"] = [{"id": m.id, "descripcion": m.descripcion, "cantidad": m.cantidad, "unidad": m.unidad, "costo_unitario": m.costo_unitario, "costo_total": m.costo_total} for m in o.materiales]
    d["costo_total"] = (o.costo_mano_obra or 0) + (o.costo_materiales or 0) + (o.costo_externo or 0)
    return d

@router.put("/ordenes/{ot_id}", response_model=LocativaOTResponse)
async def actualizar_orden(ot_id: int, data: LocativaOTUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    o = await db.get(LocativaOrdenTrabajo, ot_id)
    if not o: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(o, k, v)
    await db.commit()
    stmt = select(LocativaOrdenTrabajo).where(LocativaOrdenTrabajo.id == ot_id).options(
        selectinload(LocativaOrdenTrabajo.checklist), selectinload(LocativaOrdenTrabajo.materiales)
    )
    r = await db.execute(stmt); o = r.scalar_one()
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    d["checklist"] = [{"id": c.id, "paso": c.paso, "descripcion": c.descripcion, "completado": c.completado, "observacion": c.observacion} for c in o.checklist]
    d["materiales"] = [{"id": m.id, "descripcion": m.descripcion, "cantidad": m.cantidad, "unidad": m.unidad, "costo_unitario": m.costo_unitario, "costo_total": m.costo_total} for m in o.materiales]
    d["costo_total"] = (o.costo_mano_obra or 0) + (o.costo_materiales or 0) + (o.costo_externo or 0)
    return d

@router.patch("/ordenes/{ot_id}/estado", response_model=LocativaOTResponse)
async def cambiar_estado_orden(ot_id: int, data: LocativaOTEstadoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    o = await db.get(LocativaOrdenTrabajo, ot_id)
    if not o: raise HTTPException(404)
    o.estado = data.estado
    if data.observaciones: o.observaciones = data.observaciones
    if data.fecha_cierre: o.fecha_cierre = data.fecha_cierre
    if data.estado in ("CERRADA", "VERIFICADA") and not o.fecha_cierre:
        o.fecha_cierre = date.today()
    if data.tiempo_real_hrs: o.tiempo_real_hrs = data.tiempo_real_hrs
    if data.trabajo_realizado: o.trabajo_realizado = data.trabajo_realizado
    if data.causa_raiz: o.causa_raiz = data.causa_raiz
    if data.estado_post_intervencion: o.estado_post_intervencion = data.estado_post_intervencion
    if data.estado == "EN_PROGRESO" and not o.fecha_inicio_real:
        o.fecha_inicio_real = date.today()
    await db.commit()
    stmt = select(LocativaOrdenTrabajo).where(LocativaOrdenTrabajo.id == ot_id).options(
        selectinload(LocativaOrdenTrabajo.checklist), selectinload(LocativaOrdenTrabajo.materiales)
    )
    r = await db.execute(stmt); o = r.scalar_one()
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    d["checklist"] = [{"id": c.id, "paso": c.paso, "descripcion": c.descripcion, "completado": c.completado, "observacion": c.observacion} for c in o.checklist]
    d["materiales"] = [{"id": m.id, "descripcion": m.descripcion, "cantidad": m.cantidad, "unidad": m.unidad, "costo_unitario": m.costo_unitario, "costo_total": m.costo_total} for m in o.materiales]
    d["costo_total"] = (o.costo_mano_obra or 0) + (o.costo_materiales or 0) + (o.costo_externo or 0)
    return d


# ─── Registro de Fallas ────────────────────────────────────────────────────────

@router.get("/fallas/", response_model=List[LocativaFallaResponse])
async def listar_fallas(activo_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(LocativaRegistroFalla).order_by(LocativaRegistroFalla.fecha_deteccion.desc())
    if activo_id: q = q.where(LocativaRegistroFalla.activo_id == activo_id)
    r = await db.execute(q); return r.scalars().all()

@router.post("/fallas/", response_model=LocativaFallaResponse, status_code=201)
async def crear_falla(data: LocativaFallaCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaRegistroFalla(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.delete("/fallas/{falla_id}", status_code=204)
async def eliminar_falla(falla_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaRegistroFalla, falla_id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()


# ─── Riesgos (ISO 31000) ──────────────────────────────────────────────────────

@router.get("/riesgos/", response_model=List[LocativaRiesgoResponse])
async def listar_riesgos(
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    aceptabilidad: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(LocativaRiesgo).options(selectinload(LocativaRiesgo.tratamientos)).order_by(LocativaRiesgo.id.desc())
    if estado: q = q.where(LocativaRiesgo.estado == estado)
    if categoria: q = q.where(LocativaRiesgo.categoria == categoria)
    if aceptabilidad: q = q.where(LocativaRiesgo.aceptabilidad == aceptabilidad)
    r = await db.execute(q); return r.scalars().all()

@router.get("/riesgos/{riesgo_id}", response_model=LocativaRiesgoResponse)
async def obtener_riesgo(riesgo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    stmt = select(LocativaRiesgo).where(LocativaRiesgo.id == riesgo_id).options(selectinload(LocativaRiesgo.tratamientos))
    r = await db.execute(stmt); obj = r.scalar_one_or_none()
    if not obj: raise HTTPException(404)
    return obj

@router.post("/riesgos/", response_model=LocativaRiesgoResponse, status_code=201)
async def crear_riesgo(data: LocativaRiesgoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    d = data.model_dump()
    if not d.get("codigo"):
        d["codigo"] = await _generar_codigo_riesgo(db)
    obj = LocativaRiesgo(**d)
    # Auto-calcular nivel inherente
    impactos = [x for x in [obj.impacto_personas, obj.impacto_operacional, obj.impacto_financiero, obj.impacto_ambiental] if x]
    if obj.probabilidad and impactos:
        obj.nivel_inherente = obj.probabilidad * max(impactos)
        ni = obj.nivel_inherente
        obj.aceptabilidad = "INACEPTABLE" if ni >= 15 else ("TOLERABLE" if ni >= 6 else "ACEPTABLE")
    db.add(obj); await db.commit()
    stmt = select(LocativaRiesgo).where(LocativaRiesgo.id == obj.id).options(selectinload(LocativaRiesgo.tratamientos))
    r = await db.execute(stmt); return r.scalar_one()

@router.put("/riesgos/{riesgo_id}", response_model=LocativaRiesgoResponse)
async def actualizar_riesgo(riesgo_id: int, data: LocativaRiesgoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaRiesgo, riesgo_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    impactos = [x for x in [obj.impacto_personas, obj.impacto_operacional, obj.impacto_financiero, obj.impacto_ambiental] if x]
    if obj.probabilidad and impactos:
        obj.nivel_inherente = obj.probabilidad * max(impactos)
        ni = obj.nivel_inherente
        obj.aceptabilidad = "INACEPTABLE" if ni >= 15 else ("TOLERABLE" if ni >= 6 else "ACEPTABLE")
    await db.commit()
    stmt = select(LocativaRiesgo).where(LocativaRiesgo.id == riesgo_id).options(selectinload(LocativaRiesgo.tratamientos))
    r = await db.execute(stmt); return r.scalar_one()

@router.delete("/riesgos/{riesgo_id}", status_code=204)
async def eliminar_riesgo(riesgo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaRiesgo, riesgo_id)
    if not obj: raise HTTPException(404)
    obj.estado = "CERRADO"; await db.commit()

@router.post("/riesgos/{riesgo_id}/tratamientos", response_model=LocativaRiesgoTratamientoResponse, status_code=201)
async def crear_tratamiento(riesgo_id: int, data: LocativaRiesgoTratamientoCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    d = data.model_dump(); d["riesgo_id"] = riesgo_id
    obj = LocativaRiesgoTratamiento(**d)
    db.add(obj); await db.commit(); await db.refresh(obj)
    r = await db.get(LocativaRiesgo, riesgo_id)
    if r: r.estado = "EN_TRATAMIENTO"; await db.commit()
    return obj

@router.put("/tratamientos/{trat_id}", response_model=LocativaRiesgoTratamientoResponse)
async def actualizar_tratamiento(trat_id: int, data: LocativaRiesgoTratamientoUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaRiesgoTratamiento, trat_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj


# ─── Medidores de Energía ──────────────────────────────────────────────────────

@router.get("/medidores/", response_model=List[LocativaMedidorResponse])
async def listar_medidores(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    r = await db.execute(select(LocativaMedidor).where(LocativaMedidor.activo == True).order_by(LocativaMedidor.nombre))
    return r.scalars().all()

@router.post("/medidores/", response_model=LocativaMedidorResponse, status_code=201)
async def crear_medidor(data: LocativaMedidorCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = LocativaMedidor(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.put("/medidores/{med_id}", response_model=LocativaMedidorResponse)
async def actualizar_medidor(med_id: int, data: LocativaMedidorUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaMedidor, med_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/medidores/{med_id}", status_code=204)
async def eliminar_medidor(med_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaMedidor, med_id)
    if not obj: raise HTTPException(404)
    obj.activo = False; await db.commit()


# ─── Lecturas de Energía ───────────────────────────────────────────────────────

@router.get("/lecturas-energia/", response_model=List[LocativaLecturaResponse])
async def listar_lecturas(medidor_id: Optional[int] = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    q = select(LocativaLecturaEnergia).order_by(LocativaLecturaEnergia.fecha.desc())
    if medidor_id: q = q.where(LocativaLecturaEnergia.medidor_id == medidor_id)
    r = await db.execute(q); return r.scalars().all()

@router.post("/lecturas-energia/", response_model=LocativaLecturaResponse, status_code=201)
async def crear_lectura(data: LocativaLecturaCreate, user: Usuario = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Calcular consumo del período respecto a la última lectura
    r = await db.execute(
        select(LocativaLecturaEnergia)
        .where(LocativaLecturaEnergia.medidor_id == data.medidor_id)
        .order_by(LocativaLecturaEnergia.fecha.desc())
        .limit(1)
    )
    ultima = r.scalar_one_or_none()
    consumo = data.valor_lectura - ultima.valor_lectura if ultima else None
    medidor = await db.get(LocativaMedidor, data.medidor_id)
    costo = consumo * (medidor.tarifa_unidad or 0) if consumo and medidor else None
    # Detectar anomalía si el consumo es > 150% de la línea base
    anomalo = False
    if consumo and medidor and medidor.linea_base_mensual:
        anomalo = consumo > medidor.linea_base_mensual * 1.5
    obj = LocativaLecturaEnergia(
        medidor_id=data.medidor_id, fecha=data.fecha,
        valor_lectura=data.valor_lectura, consumo_periodo=consumo,
        costo_periodo=costo, anomalo=anomalo,
        observaciones=data.observaciones, registrado_por_id=user.id,
    )
    db.add(obj); await db.commit(); await db.refresh(obj); return obj

@router.delete("/lecturas-energia/{lectura_id}", status_code=204)
async def eliminar_lectura(lectura_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    obj = await db.get(LocativaLecturaEnergia, lectura_id)
    if not obj: raise HTTPException(404)
    await db.delete(obj); await db.commit()
