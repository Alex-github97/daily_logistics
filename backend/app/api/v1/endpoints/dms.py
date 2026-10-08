from datetime import date, datetime
from typing import List, Optional
from pathlib import Path
import hashlib
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.tenant import esquema_actual
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.dms import (
    DMSCarpeta, DMSCategoria, DMSTipoDocumento, DMSCampoMetadato,
    DMSDocumento, DMSVersion, DMSMetadatoValor, DMSFirma,
    DMSWorkflow, DMSWorkflowPaso, DMSInstancia, DMSInstanciaPaso,
    DMSExpediente, DMSExpedienteDocumento, DMSRetencion,
    DMSAuditoria, DMSNotificacion, DMSKPIDiario,
    EstadoDocumentoDMSEnum, TipoFirmaDMSEnum, EstadoFirmaDMSEnum,
    EstadoInstanciaDMSEnum, TipoExpedienteDMSEnum, AccionAuditoriaDMSEnum,
)
from app.application.schemas.dms import (
    DMSCarpetaCreate, DMSCarpetaUpdate, DMSCarpetaResponse,
    DMSCategoriaCreate, DMSCategoriaUpdate, DMSCategoriaResponse,
    DMSTipoDocumentoCreate, DMSTipoDocumentoUpdate, DMSTipoDocumentoResponse,
    DMSCampoMetadatoCreate, DMSCampoMetadatoUpdate, DMSCampoMetadatoResponse,
    DMSDocumentoCreate, DMSDocumentoUpdate, DMSDocumentoResponse, DMSDocumentoListResponse,
    DMSVersionCreate, DMSVersionResponse,
    DMSMetadatoValorCreate, DMSMetadatoValorResponse,
    DMSFirmaCreate, DMSFirmaUpdate, DMSFirmaResponse,
    DMSWorkflowCreate, DMSWorkflowUpdate, DMSWorkflowResponse,
    DMSWorkflowPasoCreate, DMSWorkflowPasoUpdate, DMSWorkflowPasoResponse,
    DMSInstanciaCreate, DMSInstanciaResponse,
    DMSInstanciaPasoUpdate, DMSInstanciaPasoResponse,
    DMSExpedienteCreate, DMSExpedienteUpdate, DMSExpedienteResponse,
    DMSExpedienteDocumentoCreate, DMSExpedienteDocumentoResponse,
    DMSRetencionCreate, DMSRetencionUpdate, DMSRetencionResponse,
    DMSAuditoriaResponse,
    DMSNotificacionCreate, DMSNotificacionResponse,
    DMSDashboardKPIs,
)

router = APIRouter(prefix="/dms", tags=["dms"])

# Almacenamiento de archivos del DMS. Va bajo UPLOAD_DIR, que en producción es
# un volumen: antes vivía en /app/data, que en desarrollo está montado pero en
# producción es la capa del contenedor, y cada reconstrucción de la imagen
# borraba los documentos. Una carpeta por empresa: los id se repiten entre
# esquemas.
DMS_STORAGE = Path(settings.UPLOAD_DIR).resolve() / "dms"
_DMS_ANTERIOR = Path(__file__).resolve().parents[4] / "data" / "dms_files"


def _carpeta_dms() -> Path:
    return DMS_STORAGE / (esquema_actual() or "public")


def _archivo(ruta: Optional[str]) -> Optional[Path]:
    """La ruta guardada, o el mismo archivo si se trasladó a la carpeta nueva."""
    if not ruta:
        return None
    p = Path(ruta)
    if p.exists():
        return p
    for alterna in (_carpeta_dms() / p.name, DMS_STORAGE / p.name, _DMS_ANTERIOR / p.name):
        if alterna.exists():
            return alterna
    return None


def _extraer_texto(contenido: bytes, mime: Optional[str], filename: Optional[str]) -> Optional[str]:
    """Extrae texto para búsqueda de contenido (PDF via pdfplumber, texto plano)."""
    fn = (filename or "").lower()
    try:
        if (mime and "pdf" in mime) or fn.endswith(".pdf"):
            import pdfplumber
            partes = []
            with pdfplumber.open(io.BytesIO(contenido)) as pdf:
                for page in pdf.pages[:30]:
                    partes.append(page.extract_text() or "")
            return ("\n".join(partes)).strip()[:20000] or None
        if (mime and mime.startswith("text")) or fn.endswith((".txt", ".csv", ".md")):
            return contenido.decode("utf-8", "ignore")[:20000] or None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Helper interno para registrar auditoría
# ---------------------------------------------------------------------------

async def _registrar_auditoria(
    db: AsyncSession,
    documento_id: int,
    accion: AccionAuditoriaDMSEnum,
    usuario_id: Optional[int] = None,
    descripcion: Optional[str] = None,
    datos_anteriores: Optional[dict] = None,
    datos_nuevos: Optional[dict] = None,
    ip: Optional[str] = None,
    version_id: Optional[int] = None,
) -> DMSAuditoria:
    # El modelo DMSAuditoria expone 'detalle' e 'ip_origen' (no descripcion/datos/ip).
    # Consolidamos la descripción y los cambios (antes/después) en 'detalle'.
    import json as _json
    detalle = (descripcion or "").strip()
    extra: dict = {}
    if datos_anteriores:
        extra["antes"] = datos_anteriores
    if datos_nuevos:
        extra["despues"] = datos_nuevos
    if extra:
        detalle = (detalle + " " + _json.dumps(extra, ensure_ascii=False, default=str)).strip()
    entrada = DMSAuditoria(
        documento_id=documento_id,
        version_id=version_id,
        accion=accion,
        usuario_id=usuario_id,
        detalle=detalle or None,
        ip_origen=ip or "0.0.0.0",
    )
    db.add(entrada)
    await db.flush()
    return entrada


# ===========================================================================
# 1. DASHBOARD
# ===========================================================================

@router.get("/dashboard/kpis", response_model=DMSDashboardKPIs)
async def get_dashboard_kpis(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    today = date.today()
    now = datetime.utcnow()
    now_plus_30 = datetime(now.year, now.month, now.day) if True else now
    from datetime import timedelta
    now_dt = datetime.utcnow()
    now_plus_30_dt = now_dt + timedelta(days=30)
    now_plus_90_dt = now_dt + timedelta(days=90)

    # total_documentos
    r = await db.execute(
        select(func.count(DMSDocumento.id)).where(DMSDocumento.deleted_at.is_(None))
    )
    total_documentos = r.scalar() or 0

    # documentos_activos
    r = await db.execute(
        select(func.count(DMSDocumento.id)).where(
            and_(
                DMSDocumento.deleted_at.is_(None),
                DMSDocumento.estado.in_([
                    EstadoDocumentoDMSEnum.APROBADO,
                    EstadoDocumentoDMSEnum.PUBLICADO,
                ]),
            )
        )
    )
    documentos_activos = r.scalar() or 0

    # documentos_vencidos
    r = await db.execute(
        select(func.count(DMSDocumento.id)).where(
            and_(
                DMSDocumento.fecha_vigencia_fin < now_dt,
                DMSDocumento.estado.notin_([
                    EstadoDocumentoDMSEnum.ARCHIVADO,
                    EstadoDocumentoDMSEnum.OBSOLETO,
                ]),
            )
        )
    )
    documentos_vencidos = r.scalar() or 0

    # documentos_proximos_vencer
    r = await db.execute(
        select(func.count(DMSDocumento.id)).where(
            and_(
                DMSDocumento.fecha_vigencia_fin >= now_dt,
                DMSDocumento.fecha_vigencia_fin <= now_plus_30_dt,
            )
        )
    )
    documentos_proximos_vencer = r.scalar() or 0

    # firmas_pendientes
    r = await db.execute(
        select(func.count(DMSFirma.id)).where(
            DMSFirma.estado == EstadoFirmaDMSEnum.PENDIENTE
        )
    )
    firmas_pendientes = r.scalar() or 0

    # workflows_activos
    r = await db.execute(
        select(func.count(DMSInstancia.id)).where(
            DMSInstancia.estado == EstadoInstanciaDMSEnum.EN_CURSO
        )
    )
    workflows_activos = r.scalar() or 0

    # expedientes_activos
    r = await db.execute(
        select(func.count(DMSExpediente.id)).where(
            and_(
                DMSExpediente.estado == "activo",
                DMSExpediente.deleted_at.is_(None),
            )
        )
    )
    expedientes_activos = r.scalar() or 0

    # cumplimiento_pct
    cumplimiento_pct = round((documentos_activos / max(total_documentos, 1)) * 100, 2)

    # categorias_total
    r = await db.execute(
        select(func.count(DMSCategoria.id)).where(DMSCategoria.activo == True)
    )
    categorias_total = r.scalar() or 0

    # versiones_hoy
    r = await db.execute(
        select(func.count(DMSVersion.id)).where(
            func.date(DMSVersion.created_at) == today
        )
    )
    versiones_hoy = r.scalar() or 0

    # tamanio_total_mb
    r = await db.execute(
        select(func.coalesce(func.sum(DMSVersion.tamanio_bytes), 0))
    )
    tamanio_total_mb = round((r.scalar() or 0) / 1048576, 4)

    # alertas_criticas
    r = await db.execute(
        select(func.count(DMSNotificacion.id)).where(DMSNotificacion.leida == False)
    )
    alertas_criticas = r.scalar() or 0

    # documentos_creados_hoy
    r = await db.execute(
        select(func.count(DMSDocumento.id)).where(
            and_(
                DMSDocumento.deleted_at.is_(None),
                func.date(DMSDocumento.created_at) == today,
            )
        )
    )
    documentos_creados_hoy = r.scalar() or 0

    # aprobaciones_pendientes
    r = await db.execute(
        select(func.count(DMSInstanciaPaso.id)).where(
            DMSInstanciaPaso.estado == "pendiente"
        )
    )
    aprobaciones_pendientes = r.scalar() or 0

    return DMSDashboardKPIs(
        total_documentos=total_documentos,
        documentos_activos=documentos_activos,
        documentos_vencidos=documentos_vencidos,
        documentos_proximos_vencer=documentos_proximos_vencer,
        firmas_pendientes=firmas_pendientes,
        workflows_activos=workflows_activos,
        expedientes_activos=expedientes_activos,
        cumplimiento_pct=cumplimiento_pct,
        categorias_total=categorias_total,
        versiones_hoy=versiones_hoy,
        tamanio_total_mb=tamanio_total_mb,
        alertas_criticas=alertas_criticas,
        documentos_creados_hoy=documentos_creados_hoy,
        aprobaciones_pendientes=aprobaciones_pendientes,
    )


@router.get("/notificaciones", response_model=List[DMSNotificacionResponse])
async def listar_notificaciones(
    leida: Optional[bool] = None,
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSNotificacion)
    if leida is not None:
        q = q.where(DMSNotificacion.leida == leida)
    q = q.order_by(DMSNotificacion.created_at.desc()).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/notificaciones", response_model=DMSNotificacionResponse, status_code=201)
async def crear_notificacion(
    data: DMSNotificacionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSNotificacion(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/notificaciones/{n_id}/leer")
async def marcar_notificacion_leida(
    n_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSNotificacion, n_id)
    if not item:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    item.leida = True
    await db.commit()
    return {"mensaje": "Notificación leída"}


# ===========================================================================
# 2. CARPETAS
# ===========================================================================

@router.get("/carpetas", response_model=List[DMSCarpetaResponse])
async def listar_carpetas(
    padre_id: Optional[int] = None,
    es_publica: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSCarpeta).where(DMSCarpeta.deleted_at.is_(None))
    if padre_id is None:
        q = q.where(DMSCarpeta.padre_id.is_(None))
    else:
        q = q.where(DMSCarpeta.padre_id == padre_id)
    if es_publica is not None:
        q = q.where(DMSCarpeta.es_publica == es_publica)
    r = await db.execute(q.order_by(DMSCarpeta.nombre))
    return r.scalars().all()


@router.post("/carpetas", response_model=DMSCarpetaResponse, status_code=201)
async def crear_carpeta(
    data: DMSCarpetaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSCarpeta(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/carpetas/{carpeta_id}", response_model=DMSCarpetaResponse)
async def actualizar_carpeta(
    carpeta_id: int,
    data: DMSCarpetaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSCarpeta, carpeta_id)
    if not item:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/carpetas/{carpeta_id}", status_code=204)
async def eliminar_carpeta(
    carpeta_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSCarpeta, carpeta_id)
    if not item:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    item.deleted_at = datetime.utcnow()
    await db.commit()


# ===========================================================================
# 3. CATEGORÍAS
# ===========================================================================

@router.get("/categorias", response_model=List[DMSCategoriaResponse])
async def listar_categorias(
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSCategoria)
    if activo is not None:
        q = q.where(DMSCategoria.activo == activo)
    r = await db.execute(q.order_by(DMSCategoria.nombre))
    return r.scalars().all()


@router.post("/categorias", response_model=DMSCategoriaResponse, status_code=201)
async def crear_categoria(
    data: DMSCategoriaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSCategoria(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/categorias/{cat_id}", response_model=DMSCategoriaResponse)
async def actualizar_categoria(
    cat_id: int,
    data: DMSCategoriaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSCategoria, cat_id)
    if not item:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/categorias/{cat_id}", status_code=204)
async def eliminar_categoria(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSCategoria, cat_id)
    if not item:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    await db.delete(item)
    await db.commit()


# ===========================================================================
# 4. TIPOS DE DOCUMENTO Y CAMPOS DE METADATO
# ===========================================================================

@router.get("/tipos-documento", response_model=List[DMSTipoDocumentoResponse])
async def listar_tipos_documento(
    categoria_id: Optional[int] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSTipoDocumento)
    if categoria_id is not None:
        q = q.where(DMSTipoDocumento.categoria_id == categoria_id)
    if activo is not None:
        q = q.where(DMSTipoDocumento.activo == activo)
    r = await db.execute(q.order_by(DMSTipoDocumento.nombre))
    return r.scalars().all()


@router.post("/tipos-documento", response_model=DMSTipoDocumentoResponse, status_code=201)
async def crear_tipo_documento(
    data: DMSTipoDocumentoCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSTipoDocumento(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/tipos-documento/{tipo_id}", response_model=DMSTipoDocumentoResponse)
async def actualizar_tipo_documento(
    tipo_id: int,
    data: DMSTipoDocumentoUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSTipoDocumento, tipo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Tipo de documento no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/tipos-documento/{tipo_id}/campos", response_model=List[DMSCampoMetadatoResponse])
async def listar_campos_por_tipo(
    tipo_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSCampoMetadato).where(
        DMSCampoMetadato.tipo_documento_id == tipo_id
    ).order_by(DMSCampoMetadato.orden)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/campos-metadato", response_model=DMSCampoMetadatoResponse, status_code=201)
async def crear_campo_metadato(
    data: DMSCampoMetadatoCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSCampoMetadato(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/campos-metadato/{campo_id}", response_model=DMSCampoMetadatoResponse)
async def actualizar_campo_metadato(
    campo_id: int,
    data: DMSCampoMetadatoUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSCampoMetadato, campo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Campo de metadato no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/campos-metadato/{campo_id}", status_code=204)
async def eliminar_campo_metadato(
    campo_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSCampoMetadato, campo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Campo de metadato no encontrado")
    await db.delete(item)
    await db.commit()


# ===========================================================================
# 5. DOCUMENTOS (CORE)
# ===========================================================================

# Quién puede ver y bajar un documento. Antes «Confidencial» y «Se puede
# descargar» se guardaban y ninguna ruta los consultaba: cualquiera con sesión
# listaba y descargaba todo. Ahora:
#   · confidencial: solo lo ven (en la lista, la ficha, las versiones y la
#     descarga) su propietario y los administradores;
#   · sin descarga: se ve en la lista, pero el archivo solo lo baja su
#     propietario o un administrador.
def _es_admin(u: Usuario) -> bool:
    return getattr(u.rol, "value", u.rol) == "ADMINISTRADOR"


def _es_duenio(doc: DMSDocumento, u: Usuario) -> bool:
    return _es_admin(u) or (doc.propietario_id is not None and doc.propietario_id == u.id)


def _puede_ver(doc: DMSDocumento, u: Usuario) -> bool:
    return not doc.es_confidencial or _es_duenio(doc, u)


def _puede_descargar(doc: DMSDocumento, u: Usuario) -> bool:
    return _es_duenio(doc, u) or (not doc.es_confidencial and doc.permite_descarga is not False)


async def _documento_visible(db: AsyncSession, doc_id: int, u: Usuario) -> DMSDocumento:
    doc = await db.get(DMSDocumento, doc_id)
    # Un confidencial ajeno responde igual que uno inexistente: decir «existe
    # pero no puedes verlo» ya es revelar algo.
    if not doc or doc.deleted_at is not None or not _puede_ver(doc, u):
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return doc


async def _exigir_descarga(db: AsyncSession, doc_id: int, u: Usuario) -> None:
    doc = await _documento_visible(db, doc_id, u)
    if not _puede_descargar(doc, u):
        raise HTTPException(status_code=403,
                            detail="Este documento no permite descarga; solo su propietario o un administrador.")

@router.get("/documentos", response_model=List[DMSDocumentoListResponse])
async def listar_documentos(
    q: Optional[str] = None,
    estado: Optional[str] = None,
    tipo_documento_id: Optional[int] = None,
    carpeta_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    stmt = (
        select(
            DMSDocumento,
            DMSTipoDocumento.nombre.label("tipo_nombre"),
            Usuario.nombre.label("propietario_nombre"),
        )
        .outerjoin(DMSTipoDocumento, DMSDocumento.tipo_documento_id == DMSTipoDocumento.id)
        .outerjoin(Usuario, DMSDocumento.propietario_id == Usuario.id)
        .where(DMSDocumento.deleted_at.is_(None))
    )

    if q:
        stmt = stmt.where(
            or_(
                DMSDocumento.nombre.ilike(f"%{q}%"),
                DMSDocumento.codigo.ilike(f"%{q}%"),
            )
        )
    if estado:
        stmt = stmt.where(DMSDocumento.estado == estado)
    if tipo_documento_id is not None:
        stmt = stmt.where(DMSDocumento.tipo_documento_id == tipo_documento_id)
    if carpeta_id is not None:
        stmt = stmt.where(DMSDocumento.carpeta_id == carpeta_id)
    if not _es_admin(current_user):
        stmt = stmt.where(or_(DMSDocumento.es_confidencial.isnot(True),
                              DMSDocumento.propietario_id == current_user.id))

    offset = (page - 1) * per_page
    stmt = stmt.order_by(DMSDocumento.nombre).offset(offset).limit(per_page)

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for row in rows:
        doc = row[0]
        tipo_nombre = row[1]
        propietario_nombre = row[2]
        items.append(
            DMSDocumentoListResponse(
                id=doc.id,
                codigo=doc.codigo,
                nombre=doc.nombre,
                estado=doc.estado,
                tipo_documento_id=doc.tipo_documento_id,
                tipo_nombre=tipo_nombre,
                propietario_id=doc.propietario_id,
                propietario_nombre=propietario_nombre,
                version_actual=doc.version_actual,
                fecha_vigencia_fin=doc.fecha_vigencia_fin,
                created_at=doc.created_at,
                es_confidencial=bool(doc.es_confidencial),
                permite_descarga=doc.permite_descarga is not False,
                permite_impresion=doc.permite_impresion is not False,
                descripcion=doc.descripcion,
                carpeta_id=doc.carpeta_id,
                tags=doc.tags,
                fecha_vigencia_inicio=doc.fecha_vigencia_inicio,
                puede_descargar=_puede_descargar(doc, current_user),
            )
        )
    return items


@router.post("/documentos", response_model=DMSDocumentoResponse, status_code=201)
async def crear_documento(
    data: DMSDocumentoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Generar código automático DOC-YYYY-NNNNNN
    year = datetime.utcnow().year
    r = await db.execute(select(func.count(DMSDocumento.id)))
    count = (r.scalar() or 0) + 1
    codigo = f"DOC-{year}-{count:06d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    # Sin propietario, un documento confidencial no lo podría ver nadie más
    # que un administrador, ni siquiera quien lo subió.
    payload["propietario_id"] = payload.get("propietario_id") or current_user.id
    item = DMSDocumento(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/documentos/{doc_id}", response_model=DMSDocumentoResponse)
async def obtener_documento(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return await _documento_visible(db, doc_id, current_user)


@router.put("/documentos/{doc_id}", response_model=DMSDocumentoResponse)
async def actualizar_documento(
    doc_id: int,
    data: DMSDocumentoUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSDocumento, doc_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/documentos/{doc_id}", status_code=204)
async def eliminar_documento(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSDocumento, doc_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    item.deleted_at = datetime.utcnow()
    await db.commit()


_TRANSICIONES_VALIDAS = {
    EstadoDocumentoDMSEnum.BORRADOR: [EstadoDocumentoDMSEnum.EN_REVISION],
    EstadoDocumentoDMSEnum.EN_REVISION: [
        EstadoDocumentoDMSEnum.APROBADO,
        EstadoDocumentoDMSEnum.BORRADOR,
    ],
    EstadoDocumentoDMSEnum.APROBADO: [
        EstadoDocumentoDMSEnum.PUBLICADO,
        EstadoDocumentoDMSEnum.OBSOLETO,
    ],
    EstadoDocumentoDMSEnum.PUBLICADO: [
        EstadoDocumentoDMSEnum.OBSOLETO,
        EstadoDocumentoDMSEnum.ARCHIVADO,
    ],
}


@router.put("/documentos/{doc_id}/estado")
async def cambiar_estado_documento(
    doc_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    item = await _documento_visible(db, doc_id, current_user)

    nuevo_estado_str = body.get("estado")
    comentario = body.get("comentario")

    try:
        nuevo_estado = EstadoDocumentoDMSEnum(nuevo_estado_str)
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail=f"Estado inválido: {nuevo_estado_str}")

    # Validar transición (ARCHIVADO siempre permitido)
    estado_actual = item.estado
    permitidos = _TRANSICIONES_VALIDAS.get(estado_actual, [])
    if nuevo_estado != EstadoDocumentoDMSEnum.ARCHIVADO and nuevo_estado not in permitidos:
        raise HTTPException(
            status_code=400,
            detail=f"Transición no permitida: {estado_actual} → {nuevo_estado}",
        )

    if nuevo_estado in (EstadoDocumentoDMSEnum.APROBADO, EstadoDocumentoDMSEnum.PUBLICADO):
        faltan = _faltantes(await _ficha(db, item))
        if faltan:
            raise HTTPException(
                status_code=409,
                detail="Faltan metadatos obligatorios: " + ", ".join(faltan)
                       + ". Complételos en la ficha del documento.")

    estado_anterior = item.estado
    item.estado = nuevo_estado
    await db.flush()

    # Valores legibles (evita "EstadoDocumentoDMSEnum.X" en el detalle de auditoría)
    _ant = getattr(estado_anterior, "value", estado_anterior)
    _nue = getattr(nuevo_estado, "value", nuevo_estado)

    # Registrar auditoría
    await _registrar_auditoria(
        db=db,
        documento_id=doc_id,
        accion=AccionAuditoriaDMSEnum.MODIFICACION,
        usuario_id=getattr(current_user, "id", None),
        descripcion=comentario or f"Cambio de estado: {_ant} → {_nue}",
        datos_anteriores={"estado": _ant},
        datos_nuevos={"estado": _nue},
    )

    await db.commit()
    return {"mensaje": "Estado actualizado", "estado": _nue}


# ===========================================================================
# 6. VERSIONES
# ===========================================================================

@router.get("/documentos/{doc_id}/versiones", response_model=List[DMSVersionResponse])
async def listar_versiones(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    await _documento_visible(db, doc_id, current_user)
    q = (
        select(DMSVersion)
        .where(DMSVersion.documento_id == doc_id)
        .order_by(DMSVersion.version_numero.desc())
    )
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/versiones", response_model=DMSVersionResponse, status_code=201)
async def crear_version(
    data: DMSVersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    doc = await db.get(DMSDocumento, data.documento_id)
    if not doc or doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    item = DMSVersion(**data.model_dump())
    db.add(item)
    await db.flush()

    # Actualizar versión en el documento
    doc.version_actual = data.version_numero
    if hasattr(doc, "version_numero"):
        doc.version_numero = data.version_numero

    # Registrar auditoría
    await _registrar_auditoria(
        db=db,
        documento_id=data.documento_id,
        accion=AccionAuditoriaDMSEnum.VERSION_NUEVA,
        usuario_id=getattr(current_user, "id", None),
        descripcion=f"Nueva versión {data.version_numero} creada",
        datos_nuevos={"version_numero": data.version_numero},
    )

    await db.commit()
    await db.refresh(item)
    return item


@router.post("/documentos/{documento_id}/upload", response_model=DMSVersionResponse)
async def subir_archivo_version(
    documento_id: int,
    request: Request,
    file: UploadFile = File(...),
    comentario: Optional[str] = Form(None),
    es_mayor: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Carga REAL de un archivo: lo almacena en disco, calcula hash/tamaño, extrae
    texto (PDF/plano) para búsqueda de contenido y crea una nueva versión."""
    doc = await _documento_visible(db, documento_id, current_user)
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    md5 = hashlib.md5(contenido).hexdigest()
    nuevo_num = (doc.version_numero or 0) + 1
    numero_str = f"{nuevo_num}.0"
    _carpeta_dms().mkdir(parents=True, exist_ok=True)
    safe = (file.filename or "archivo").replace("/", "_").replace("\\", "_")
    ruta = _carpeta_dms() / f"doc{documento_id}_v{nuevo_num}_{md5[:8]}_{safe}"
    ruta.write_bytes(contenido)
    ocr = _extraer_texto(contenido, file.content_type, file.filename)
    ver = DMSVersion(
        documento_id=documento_id, numero_version=numero_str, version_numero=nuevo_num,
        es_mayor=es_mayor, nombre_archivo=file.filename or safe, ruta_archivo=str(ruta),
        tamanio_bytes=len(contenido), tipo_mime=file.content_type, hash_md5=md5,
        comentario=comentario, ocr_texto=ocr, creado_por_id=getattr(current_user, "id", None),
    )
    db.add(ver)
    await db.flush()
    doc.version_actual = numero_str
    doc.version_numero = nuevo_num
    await _registrar_auditoria(
        db=db, documento_id=documento_id, accion=AccionAuditoriaDMSEnum.VERSION_NUEVA,
        usuario_id=getattr(current_user, "id", None),
        descripcion=f"Archivo '{file.filename}' cargado (v{numero_str}, {len(contenido)} bytes)",
        version_id=ver.id, ip=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(ver)
    return ver


@router.get("/versiones/{version_id}/download")
async def descargar_version(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    ver = await db.get(DMSVersion, version_id)
    archivo = _archivo(ver.ruta_archivo) if ver else None
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    await _exigir_descarga(db, ver.documento_id, current_user)
    return FileResponse(archivo, filename=ver.nombre_archivo,
                        media_type=ver.tipo_mime or "application/octet-stream")


@router.get("/documentos/{documento_id}/download")
async def descargar_documento(
    documento_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Descarga la última versión con archivo del documento."""
    await _exigir_descarga(db, documento_id, current_user)
    r = await db.execute(
        select(DMSVersion).where(
            DMSVersion.documento_id == documento_id,
            DMSVersion.ruta_archivo.isnot(None),
        ).order_by(DMSVersion.version_numero.desc())
    )
    ver = r.scalars().first()
    archivo = _archivo(ver.ruta_archivo) if ver else None
    if not archivo:
        raise HTTPException(status_code=404, detail="El documento no tiene archivo")
    return FileResponse(archivo, filename=ver.nombre_archivo,
                        media_type=ver.tipo_mime or "application/octet-stream")


@router.get("/versiones/{version_id}", response_model=DMSVersionResponse)
async def obtener_version(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSVersion, version_id)
    if not item:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    return item


# ===========================================================================
# 7. METADATOS
# ===========================================================================

@router.get("/documentos/{doc_id}/metadatos", response_model=List[DMSMetadatoValorResponse])
async def listar_metadatos(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSMetadatoValor).where(DMSMetadatoValor.documento_id == doc_id)
    r = await db.execute(q)
    return r.scalars().all()


# ── La ficha de metadatos de un documento ───────────────────────────────────
# Los campos se configuran por tipo de documento (Configuración DMS). Antes
# nadie los llenaba: no había pantalla que los pidiera y «Obligatorio» no lo
# hacía cumplir nadie. Ahora la ficha junta los campos del tipo con los valores
# del documento, se guarda completa, y un documento no se aprueba ni se
# publica mientras le falte un obligatorio.

def _opciones(c: DMSCampoMetadato) -> List[str]:
    import json
    if not c.opciones:
        return []
    try:
        v = json.loads(c.opciones)
        if isinstance(v, list):
            return [str(x) for x in v]
    except ValueError:
        pass
    return [x.strip() for x in c.opciones.split(",") if x.strip()]


def _valor_de(c: DMSCampoMetadato, v: Optional[DMSMetadatoValor]):
    if v is None:
        return None
    if c.tipo_dato == "numero":
        return float(v.valor_numero) if v.valor_numero is not None else None
    if c.tipo_dato == "fecha":
        return v.valor_fecha.date().isoformat() if v.valor_fecha else None
    if c.tipo_dato == "booleano":
        return v.valor_booleano
    return v.valor_texto


async def _ficha(db: AsyncSession, doc: DMSDocumento) -> list:
    if not doc.tipo_documento_id:
        return []
    campos = (await db.execute(select(DMSCampoMetadato).where(
        DMSCampoMetadato.tipo_documento_id == doc.tipo_documento_id)
        .order_by(DMSCampoMetadato.orden, DMSCampoMetadato.id))).scalars().all()
    valores = {v.campo_id: v for v in (await db.execute(select(DMSMetadatoValor).where(
        DMSMetadatoValor.documento_id == doc.id))).scalars().all()}
    return [{"campo_id": c.id, "nombre": c.nombre, "etiqueta": c.etiqueta,
             "tipo_dato": c.tipo_dato, "requerido": bool(c.requerido),
             "opciones": _opciones(c), "valor": _valor_de(c, valores.get(c.id))}
            for c in campos]


def _faltantes(ficha: list) -> List[str]:
    return [f["etiqueta"] for f in ficha
            if f["requerido"] and (f["valor"] is None or f["valor"] == "")]


@router.get("/documentos/{doc_id}/ficha-metadatos")
async def ficha_metadatos(doc_id: int, db: AsyncSession = Depends(get_db),
                          current_user: Usuario = Depends(get_current_user)):
    doc = await _documento_visible(db, doc_id, current_user)
    ficha = await _ficha(db, doc)
    return {"campos": ficha, "faltantes": _faltantes(ficha)}


@router.put("/documentos/{doc_id}/ficha-metadatos")
async def guardar_ficha_metadatos(doc_id: int, body: dict, db: AsyncSession = Depends(get_db),
                                  current_user: Usuario = Depends(get_current_user)):
    """Guarda todos los valores de una vez: {"valores": {campo_id: valor}}."""
    doc = await _documento_visible(db, doc_id, current_user)
    entrada = {int(k): v for k, v in (body.get("valores") or {}).items()}
    campos = {c.id: c for c in (await db.execute(select(DMSCampoMetadato).where(
        DMSCampoMetadato.tipo_documento_id == doc.tipo_documento_id))).scalars().all()} \
        if doc.tipo_documento_id else {}
    existentes = {v.campo_id: v for v in (await db.execute(select(DMSMetadatoValor).where(
        DMSMetadatoValor.documento_id == doc.id))).scalars().all()}
    for cid, valor in entrada.items():
        c = campos.get(cid)
        if c is None:
            raise HTTPException(422, "Ese campo no pertenece al tipo de este documento.")
        v = existentes.get(cid) or DMSMetadatoValor(documento_id=doc.id, campo_id=cid)
        v.valor_texto = v.valor_numero = v.valor_fecha = v.valor_booleano = None
        vacio = valor is None or valor == ""
        try:
            if vacio:
                pass
            elif c.tipo_dato == "numero":
                v.valor_numero = float(valor)
            elif c.tipo_dato == "fecha":
                v.valor_fecha = datetime.fromisoformat(str(valor)[:10])
            elif c.tipo_dato == "booleano":
                v.valor_booleano = bool(valor)
            else:
                texto = str(valor).strip()
                if c.tipo_dato == "lista" and _opciones(c) and texto not in _opciones(c):
                    raise HTTPException(422, f"«{c.etiqueta}»: elija una de las opciones.")
                v.valor_texto = texto
        except (TypeError, ValueError):
            raise HTTPException(422, f"«{c.etiqueta}»: el valor no es válido.")
        if cid not in existentes:
            db.add(v)
    await db.flush()
    ficha = await _ficha(db, doc)
    return {"campos": ficha, "faltantes": _faltantes(ficha)}


@router.post("/metadatos", response_model=DMSMetadatoValorResponse, status_code=201)
async def crear_metadato(
    data: DMSMetadatoValorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Verificar duplicado (documento_id, campo_id)
    existing = await db.execute(
        select(DMSMetadatoValor).where(
            and_(
                DMSMetadatoValor.documento_id == data.documento_id,
                DMSMetadatoValor.campo_id == data.campo_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Ya existe un metadato para este campo en el documento",
        )
    item = DMSMetadatoValor(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/metadatos/{meta_id}", response_model=DMSMetadatoValorResponse)
async def actualizar_metadato(
    meta_id: int,
    data: DMSMetadatoValorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSMetadatoValor, meta_id)
    if not item:
        raise HTTPException(status_code=404, detail="Metadato no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/metadatos/{meta_id}", status_code=204)
async def eliminar_metadato(
    meta_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSMetadatoValor, meta_id)
    if not item:
        raise HTTPException(status_code=404, detail="Metadato no encontrado")
    await db.delete(item)
    await db.commit()


# ===========================================================================
# 8. FIRMAS
# ===========================================================================

@router.get("/firmas", response_model=List[DMSFirmaResponse])
async def listar_firmas(
    estado: Optional[str] = None,
    documento_id: Optional[int] = None,
    firmante_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSFirma)
    if estado:
        q = q.where(DMSFirma.estado == estado)
    if documento_id is not None:
        q = q.where(DMSFirma.documento_id == documento_id)
    if firmante_id is not None:
        q = q.where(DMSFirma.firmante_id == firmante_id)
    q = q.order_by(DMSFirma.orden, DMSFirma.created_at)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/firmas", response_model=DMSFirmaResponse, status_code=201)
async def crear_firma(
    data: DMSFirmaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Verificar duplicado pendiente
    existing = await db.execute(
        select(DMSFirma).where(
            and_(
                DMSFirma.documento_id == data.documento_id,
                DMSFirma.firmante_id == data.firmante_id,
                DMSFirma.estado == EstadoFirmaDMSEnum.PENDIENTE,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Ya existe una firma pendiente para este firmante en el documento",
        )
    item = DMSFirma(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/firmas/{firma_id}/firmar", response_model=DMSFirmaResponse)
async def firmar_documento(
    firma_id: int,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    item = await db.get(DMSFirma, firma_id)
    if not item:
        raise HTTPException(status_code=404, detail="Firma no encontrada")
    if item.estado != EstadoFirmaDMSEnum.PENDIENTE:
        raise HTTPException(status_code=400, detail="La firma no está en estado PENDIENTE")

    item.estado = EstadoFirmaDMSEnum.FIRMADO
    item.fecha_firma = datetime.utcnow()
    ip = request.client.host if request.client else "0.0.0.0"
    item.ip_firma = ip
    if body.get("observaciones"):
        item.observaciones = body["observaciones"]

    await db.flush()

    await _registrar_auditoria(
        db=db,
        documento_id=item.documento_id,
        accion=AccionAuditoriaDMSEnum.FIRMA,
        usuario_id=getattr(current_user, "id", None),
        descripcion=f"Documento firmado por usuario {getattr(current_user, 'id', None)}",
        datos_nuevos={"firma_id": firma_id, "estado": "FIRMADO"},
        ip=ip,
    )

    await db.commit()
    await db.refresh(item)
    return item


@router.put("/firmas/{firma_id}/rechazar", response_model=DMSFirmaResponse)
async def rechazar_firma(
    firma_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSFirma, firma_id)
    if not item:
        raise HTTPException(status_code=404, detail="Firma no encontrada")
    if item.estado != EstadoFirmaDMSEnum.PENDIENTE:
        raise HTTPException(status_code=400, detail="La firma no está en estado PENDIENTE")

    item.estado = EstadoFirmaDMSEnum.RECHAZADO
    if body.get("observaciones"):
        item.observaciones = body["observaciones"]

    await db.commit()
    await db.refresh(item)
    return item


# ===========================================================================
# 9. WORKFLOWS
# ===========================================================================

@router.get("/workflows", response_model=List[DMSWorkflowResponse])
async def listar_workflows(
    activo: Optional[bool] = None,
    tipo_documento_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSWorkflow)
    if activo is not None:
        q = q.where(DMSWorkflow.activo == activo)
    if tipo_documento_id is not None:
        q = q.where(DMSWorkflow.tipo_documento_id == tipo_documento_id)
    r = await db.execute(q.order_by(DMSWorkflow.nombre))
    return r.scalars().all()


@router.post("/workflows", response_model=DMSWorkflowResponse, status_code=201)
async def crear_workflow(
    data: DMSWorkflowCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSWorkflow(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/workflows/{wf_id}", response_model=DMSWorkflowResponse)
async def actualizar_workflow(
    wf_id: int,
    data: DMSWorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSWorkflow, wf_id)
    if not item:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/workflows/{wf_id}/pasos", response_model=List[DMSWorkflowPasoResponse])
async def listar_pasos_workflow(
    wf_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(DMSWorkflowPaso)
        .where(DMSWorkflowPaso.workflow_id == wf_id)
        .order_by(DMSWorkflowPaso.orden)
    )
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/workflows/pasos", response_model=DMSWorkflowPasoResponse, status_code=201)
async def crear_paso_workflow(
    data: DMSWorkflowPasoCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSWorkflowPaso(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/workflows/pasos/{paso_id}", response_model=DMSWorkflowPasoResponse)
async def actualizar_paso_workflow(
    paso_id: int,
    data: DMSWorkflowPasoUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSWorkflowPaso, paso_id)
    if not item:
        raise HTTPException(status_code=404, detail="Paso de workflow no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/workflows/pasos/{paso_id}", status_code=204)
async def eliminar_paso_workflow(
    paso_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSWorkflowPaso, paso_id)
    if not item:
        raise HTTPException(status_code=404, detail="Paso de workflow no encontrado")
    await db.delete(item)
    await db.commit()


@router.get("/instancias", response_model=List[DMSInstanciaResponse])
async def listar_instancias(
    estado: Optional[str] = None,
    documento_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSInstancia)
    if estado:
        q = q.where(DMSInstancia.estado == estado)
    if documento_id is not None:
        q = q.where(DMSInstancia.documento_id == documento_id)
    r = await db.execute(q.order_by(DMSInstancia.created_at.desc()))
    return r.scalars().all()


@router.post("/instancias", response_model=DMSInstanciaResponse, status_code=201)
async def crear_instancia(
    data: DMSInstanciaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Obtener pasos del workflow
    pasos_r = await db.execute(
        select(DMSWorkflowPaso)
        .where(DMSWorkflowPaso.workflow_id == data.workflow_id)
        .order_by(DMSWorkflowPaso.orden)
    )
    pasos = pasos_r.scalars().all()

    instancia = DMSInstancia(**data.model_dump())
    instancia.estado = EstadoInstanciaDMSEnum.EN_CURSO
    instancia.paso_actual = 1 if pasos else 0
    db.add(instancia)
    await db.flush()

    # Crear pasos de instancia (el orden se deriva del DMSWorkflowPaso via paso_id)
    for paso in pasos:
        ip = DMSInstanciaPaso(
            instancia_id=instancia.id,
            paso_id=paso.id,
            estado="pendiente",
        )
        db.add(ip)

    await db.commit()
    await db.refresh(instancia)
    return instancia


@router.put("/instancias/{inst_id}/avanzar", response_model=DMSInstanciaResponse)
async def avanzar_instancia(
    inst_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    instancia = await db.get(DMSInstancia, inst_id)
    if not instancia:
        raise HTTPException(status_code=404, detail="Instancia no encontrada")
    if instancia.estado != EstadoInstanciaDMSEnum.EN_CURSO:
        raise HTTPException(status_code=400, detail="La instancia no está en curso")

    # Marcar paso actual como completado (orden vive en DMSWorkflowPaso via paso_id)
    paso_actual_r = await db.execute(
        select(DMSInstanciaPaso)
        .join(DMSWorkflowPaso, DMSInstanciaPaso.paso_id == DMSWorkflowPaso.id)
        .where(
            and_(
                DMSInstanciaPaso.instancia_id == inst_id,
                DMSWorkflowPaso.orden == instancia.paso_actual,
            )
        )
    )
    paso_actual_obj = paso_actual_r.scalar_one_or_none()
    if paso_actual_obj:
        paso_actual_obj.estado = "completado"
        paso_actual_obj.accion = body.get("accion", "aprobado")
        paso_actual_obj.comentario = body.get("comentario")
        paso_actual_obj.fecha_respuesta = datetime.utcnow()

    # Buscar siguiente paso (por orden del DMSWorkflowPaso)
    siguiente_paso_r = await db.execute(
        select(DMSWorkflowPaso.orden)
        .join(DMSInstanciaPaso, DMSInstanciaPaso.paso_id == DMSWorkflowPaso.id)
        .where(
            and_(
                DMSInstanciaPaso.instancia_id == inst_id,
                DMSWorkflowPaso.orden > instancia.paso_actual,
                DMSInstanciaPaso.estado == "pendiente",
            )
        ).order_by(DMSWorkflowPaso.orden).limit(1)
    )
    siguiente_orden = siguiente_paso_r.scalar_one_or_none()

    if siguiente_orden is not None:
        instancia.paso_actual = siguiente_orden
    else:
        instancia.estado = EstadoInstanciaDMSEnum.COMPLETADO
        instancia.fecha_fin = datetime.utcnow()

    await db.commit()
    await db.refresh(instancia)
    return instancia


@router.put("/instancias/{inst_id}/cancelar", response_model=DMSInstanciaResponse)
async def cancelar_instancia(
    inst_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    instancia = await db.get(DMSInstancia, inst_id)
    if not instancia:
        raise HTTPException(status_code=404, detail="Instancia no encontrada")

    instancia.estado = EstadoInstanciaDMSEnum.CANCELADO
    instancia.comentario_cierre = body.get("comentario")
    instancia.fecha_fin = datetime.utcnow()

    await db.commit()
    await db.refresh(instancia)
    return instancia


# ===========================================================================
# 10. EXPEDIENTES
# ===========================================================================

@router.get("/expedientes", response_model=List[DMSExpedienteResponse])
async def listar_expedientes(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSExpediente).where(DMSExpediente.deleted_at.is_(None))
    if tipo:
        q = q.where(DMSExpediente.tipo == tipo)
    if estado:
        q = q.where(DMSExpediente.estado == estado)
    r = await db.execute(q.order_by(DMSExpediente.nombre))
    return r.scalars().all()


@router.post("/expedientes", response_model=DMSExpedienteResponse, status_code=201)
async def crear_expediente(
    data: DMSExpedienteCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Generar código EXP-{TIPO[0:3]}-{NNNNNN}
    tipo_str = str(data.tipo).upper()[:3] if data.tipo else "GEN"
    r = await db.execute(select(func.count(DMSExpediente.id)))
    count = (r.scalar() or 0) + 1
    codigo = f"EXP-{tipo_str}-{count:06d}"

    payload = data.model_dump()
    payload["codigo"] = codigo
    item = DMSExpediente(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/expedientes/{exp_id}", response_model=DMSExpedienteResponse)
async def obtener_expediente(
    exp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSExpediente, exp_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return item


@router.put("/expedientes/{exp_id}", response_model=DMSExpedienteResponse)
async def actualizar_expediente(
    exp_id: int,
    data: DMSExpedienteUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSExpediente, exp_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/expedientes/{exp_id}", status_code=204)
async def eliminar_expediente(
    exp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSExpediente, exp_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    item.deleted_at = datetime.utcnow()
    await db.commit()


@router.get("/expedientes/{exp_id}/documentos", response_model=List[DMSExpedienteDocumentoResponse])
async def listar_documentos_expediente(
    exp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSExpedienteDocumento).where(
        DMSExpedienteDocumento.expediente_id == exp_id
    )
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/expedientes/documentos", response_model=DMSExpedienteDocumentoResponse, status_code=201)
async def agregar_documento_expediente(
    data: DMSExpedienteDocumentoCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Verificar duplicado
    existing = await db.execute(
        select(DMSExpedienteDocumento).where(
            and_(
                DMSExpedienteDocumento.expediente_id == data.expediente_id,
                DMSExpedienteDocumento.documento_id == data.documento_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="El documento ya está asociado a este expediente",
        )
    item = DMSExpedienteDocumento(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/expedientes/documentos/{ed_id}", status_code=204)
async def eliminar_documento_expediente(
    ed_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSExpedienteDocumento, ed_id)
    if not item:
        raise HTTPException(status_code=404, detail="Relación expediente-documento no encontrada")
    await db.delete(item)
    await db.commit()


# ===========================================================================
# 11. RETENCIÓN
# ===========================================================================

@router.get("/retencion", response_model=List[DMSRetencionResponse])
async def listar_retencion(
    activo: Optional[bool] = None,
    tipo_documento_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSRetencion)
    if activo is not None:
        q = q.where(DMSRetencion.activo == activo)
    if tipo_documento_id is not None:
        q = q.where(DMSRetencion.tipo_documento_id == tipo_documento_id)
    r = await db.execute(q.order_by(DMSRetencion.id))
    return r.scalars().all()


@router.post("/retencion", response_model=DMSRetencionResponse, status_code=201)
async def crear_retencion(
    data: DMSRetencionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = DMSRetencion(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/retencion/{ret_id}", response_model=DMSRetencionResponse)
async def actualizar_retencion(
    ret_id: int,
    data: DMSRetencionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    item = await db.get(DMSRetencion, ret_id)
    if not item:
        raise HTTPException(status_code=404, detail="Política de retención no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/retencion/vencimientos")
async def vencimientos_documentos(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from datetime import timedelta

    now_dt = datetime.utcnow()
    now_plus_30 = now_dt + timedelta(days=30)
    now_plus_90 = now_dt + timedelta(days=90)

    def _build_doc_dict(doc: DMSDocumento, now: datetime) -> dict:
        dias = None
        if doc.fecha_vigencia_fin:
            delta = doc.fecha_vigencia_fin - now
            dias = delta.days
        return {
            "id": doc.id,
            "nombre": doc.nombre,
            "codigo": doc.codigo,
            "estado": doc.estado,
            "fecha_vigencia_fin": doc.fecha_vigencia_fin,
            "dias_restantes": dias,
        }

    # Vencidos
    r = await db.execute(
        select(DMSDocumento).where(
            and_(
                DMSDocumento.deleted_at.is_(None),
                DMSDocumento.fecha_vigencia_fin < now_dt,
            )
        )
    )
    vencidos = [_build_doc_dict(d, now_dt) for d in r.scalars().all() if _puede_ver(d, current_user)]

    # Próximos 30 días
    r = await db.execute(
        select(DMSDocumento).where(
            and_(
                DMSDocumento.deleted_at.is_(None),
                DMSDocumento.fecha_vigencia_fin >= now_dt,
                DMSDocumento.fecha_vigencia_fin <= now_plus_30,
            )
        )
    )
    proximos_30 = [_build_doc_dict(d, now_dt) for d in r.scalars().all() if _puede_ver(d, current_user)]

    # Próximos 90 días (excluyendo los de 30)
    r = await db.execute(
        select(DMSDocumento).where(
            and_(
                DMSDocumento.deleted_at.is_(None),
                DMSDocumento.fecha_vigencia_fin > now_plus_30,
                DMSDocumento.fecha_vigencia_fin <= now_plus_90,
            )
        )
    )
    proximos_90 = [_build_doc_dict(d, now_dt) for d in r.scalars().all() if _puede_ver(d, current_user)]

    return {
        "vencidos": vencidos,
        "proximos_30": proximos_30,
        "proximos_90": proximos_90,
    }


# ===========================================================================
# 12. AUDITORÍA
# ===========================================================================

@router.get("/auditoria", response_model=List[DMSAuditoriaResponse])
async def listar_auditoria(
    documento_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    accion: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(DMSAuditoria)
    if documento_id is not None:
        q = q.where(DMSAuditoria.documento_id == documento_id)
    if usuario_id is not None:
        q = q.where(DMSAuditoria.usuario_id == usuario_id)
    if accion:
        q = q.where(DMSAuditoria.accion == accion)
    if fecha_desde:
        q = q.where(func.date(DMSAuditoria.created_at) >= fecha_desde)
    if fecha_hasta:
        q = q.where(func.date(DMSAuditoria.created_at) <= fecha_hasta)
    q = q.order_by(DMSAuditoria.created_at.desc()).limit(limit)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("/auditoria/registrar", response_model=DMSAuditoriaResponse, status_code=201)
async def registrar_auditoria_endpoint(
    data: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Endpoint interno para registrar entradas de auditoría."""
    item = DMSAuditoria(**data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
