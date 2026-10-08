"""
Documentos de las órdenes de trabajo: cotizaciones, facturas, órdenes de compra
e informes técnicos.

Van en el esquema del cliente porque son datos suyos, no una conversación con
quien opera la plataforma. Eso trae una consecuencia que hay que atender: dos
empresas pueden tener la OT número 5, así que la ruta en disco lleva el esquema
adentro. Sin eso, la segunda sobrescribiría el archivo de la primera.

La descarga pasa por acá y no por una carpeta pública: una factura de
mantenimiento tiene precios de proveedor, y una URL adivinable los expondría.
"""
import hashlib
import mimetypes
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.core.tenant import esquema_actual, ESQUEMA_POR_DEFECTO
from app.infrastructure.models.eam import EAMAdjuntoOT, EAMOrdenTrabajo

router = APIRouter(prefix="/eam", tags=["CMMS/EAM"])

# Los tipos que se ofrecen como botón. `OTRO` existe para lo que no encaja, que
# siempre aparece.
TIPOS = {
    "COTIZACION": "Cotización",
    "ORDEN_COMPRA": "Orden de compra",
    "FACTURA": "Factura",
    "INFORME_TECNICO": "Informe técnico",
    "REMISION": "Remisión",
    "GARANTIA": "Garantía",
    "FOTO": "Fotografía",
    "OTRO": "Otro documento",
}

EXTENSIONES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic",
    ".xlsx", ".xls", ".csv", ".doc", ".docx", ".txt", ".json", ".xml",
    ".zip", ".rar", ".7z", ".eml", ".msg", ".dwg",
}
MAX_BYTES = 25 * 1024 * 1024   # 25 MB: los planos y los escaneos pesan


def _usuario(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return "?"
    try:
        datos = decode_token(auth[7:])
        return str(datos.get("usr") or datos.get("sub") or "?")
    except Exception:
        return "?"


def _carpeta() -> str:
    """La subcarpeta del cliente en curso.

    Es lo que impide que la OT 5 de una empresa pise la OT 5 de otra.
    """
    esquema = esquema_actual() or ESQUEMA_POR_DEFECTO
    limpio = re.sub(r"[^A-Za-z0-9_]", "_", esquema)
    return f"eam_ot/{limpio}"


def _nombre_seguro(nombre: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.basename(nombre or "archivo"))
    return limpio[:120] or "archivo"


class AdjuntoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ot_id: int
    ot_numero: Optional[str] = None
    tipo: str
    tipo_label: Optional[str] = None
    nombre: str
    tipo_mime: Optional[str] = None
    tamano: Optional[int] = None
    numero_documento: Optional[str] = None
    fecha_documento: Optional[date] = None
    valor: Optional[float] = None
    proveedor: Optional[str] = None
    notas: Optional[str] = None
    subido_por: Optional[str] = None
    created_at: Optional[datetime] = None


class TipoDisponible(BaseModel):
    clave: str
    label: str


def _con_label(a: EAMAdjuntoOT) -> AdjuntoResponse:
    ficha = AdjuntoResponse.model_validate(a)
    ficha.tipo_label = TIPOS.get(a.tipo, a.tipo)
    return ficha


@router.get("/ot-adjuntos/tipos", response_model=List[TipoDisponible])
async def tipos():
    return [TipoDisponible(clave=k, label=v) for k, v in TIPOS.items()]


@router.get("/ots/{ot_id}/adjuntos", response_model=List[AdjuntoResponse])
async def listar(ot_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMAdjuntoOT)
        .where(EAMAdjuntoOT.ot_id == ot_id)
        .order_by(EAMAdjuntoOT.tipo, EAMAdjuntoOT.id.desc()))
    return [_con_label(a) for a in r.scalars().all()]


@router.post("/ots/{ot_id}/adjuntos", response_model=List[AdjuntoResponse],
             status_code=201)
async def subir(
    ot_id: int, request: Request,
    archivos: List[UploadFile] = File(...),
    tipo: str = Form("OTRO"),
    numero_documento: Optional[str] = Form(None),
    fecha_documento: Optional[str] = Form(None),
    valor: Optional[str] = Form(None),
    proveedor: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    ot = await db.get(EAMOrdenTrabajo, ot_id)
    if not ot:
        raise HTTPException(404, "Esa orden de trabajo no existe")
    clave = (tipo or "OTRO").upper()
    if clave not in TIPOS:
        raise HTTPException(
            400, f"Tipo inválido. Use uno de: {', '.join(TIPOS)}.")

    fecha = None
    if fecha_documento:
        try:
            fecha = date.fromisoformat(fecha_documento[:10])
        except ValueError:
            raise HTTPException(400, f"«{fecha_documento}» no es una fecha válida (AAAA-MM-DD)")

    monto = None
    if valor not in (None, ""):
        try:
            # Se admite lo que la gente pega desde una factura: "$ 1.250.000".
            texto = str(valor).replace("$", "").replace(" ", "").replace(".", "")
            monto = float(texto.replace(",", "."))
        except ValueError:
            raise HTTPException(400, f"«{valor}» no es un valor numérico válido")

    carpeta = _carpeta()
    destino = Path(settings.UPLOAD_DIR) / carpeta
    destino.mkdir(parents=True, exist_ok=True)

    guardados = []
    for archivo in archivos:
        contenido = await archivo.read()
        nombre = _nombre_seguro(archivo.filename or "archivo")
        if not contenido:
            raise HTTPException(400, f"«{nombre}» está vacío")
        if len(contenido) > MAX_BYTES:
            raise HTTPException(
                400,
                f"«{nombre}» pesa {len(contenido) // (1024 * 1024)} MB y el máximo son "
                f"{MAX_BYTES // (1024 * 1024)} MB.",
            )
        extension = os.path.splitext(nombre)[1].lower()
        if extension not in EXTENSIONES:
            raise HTTPException(
                400,
                f"No se admiten archivos «{extension or 'sin extensión'}». Se aceptan: "
                f"{', '.join(sorted(e.lstrip('.') for e in EXTENSIONES))}.",
            )

        firma = hashlib.md5(contenido).hexdigest()[:10]
        relativa = f"{carpeta}/ot{ot_id}_{clave.lower()}_{firma}_{nombre}"
        (Path(settings.UPLOAD_DIR) / relativa).write_bytes(contenido)

        adjunto = EAMAdjuntoOT(
            ot_id=ot_id, ot_numero=ot.numero, tipo=clave, nombre=nombre,
            ruta=relativa,
            tipo_mime=archivo.content_type or mimetypes.guess_type(nombre)[0],
            tamano=len(contenido),
            numero_documento=(numero_documento or None), fecha_documento=fecha,
            valor=monto, proveedor=(proveedor or None), notas=(notas or None),
            subido_por=_usuario(request),
        )
        db.add(adjunto)
        guardados.append(adjunto)

    await db.commit()
    for a in guardados:
        await db.refresh(a)
    return [_con_label(a) for a in guardados]


@router.get("/ot-adjuntos/buscar", response_model=List[AdjuntoResponse])
async def buscar(
    numero: Optional[str] = None, tipo: Optional[str] = None,
    documento: Optional[str] = None, proveedor: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Busca documentos por número de OT, por tipo, por número de documento o
    por proveedor.

    Es la forma en que la gente los pide: «páseme la factura de la OT-2026-0042»
    o «todas las cotizaciones de ese taller».
    """
    q = select(EAMAdjuntoOT)
    if numero:
        q = q.where(EAMAdjuntoOT.ot_numero.ilike(f"%{numero.strip()}%"))
    if tipo:
        q = q.where(EAMAdjuntoOT.tipo == tipo.upper())
    if documento:
        q = q.where(EAMAdjuntoOT.numero_documento.ilike(f"%{documento.strip()}%"))
    if proveedor:
        q = q.where(EAMAdjuntoOT.proveedor.ilike(f"%{proveedor.strip()}%"))
    if not any([numero, tipo, documento, proveedor]):
        # Sin filtros se devuelven los últimos: una consulta sin criterio no
        # debería traer diez mil filas.
        q = q.order_by(EAMAdjuntoOT.id.desc()).limit(100)
    else:
        q = q.order_by(EAMAdjuntoOT.ot_numero.desc(), EAMAdjuntoOT.id.desc()).limit(500)
    r = await db.execute(q)
    return [_con_label(a) for a in r.scalars().all()]


@router.get("/ot-adjuntos/{adjunto_id}/descargar")
async def descargar(adjunto_id: int, db: AsyncSession = Depends(get_db)):
    """Entrega el archivo.

    La consulta va contra el esquema de quien pide, así que un id de otra
    empresa sencillamente no existe acá. Aun así se comprueba que la ruta no se
    salga del almacén.
    """
    adjunto = await db.get(EAMAdjuntoOT, adjunto_id)
    if not adjunto:
        raise HTTPException(404, "Ese documento no existe")

    ruta = Path(settings.UPLOAD_DIR) / adjunto.ruta
    try:
        ruta.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(404, "Ese documento no existe")
    if not ruta.exists():
        raise HTTPException(410, "El archivo ya no está en el servidor")

    return FileResponse(
        ruta, filename=adjunto.nombre,
        media_type=adjunto.tipo_mime or "application/octet-stream")


@router.delete("/ot-adjuntos/{adjunto_id}", status_code=204)
async def borrar(adjunto_id: int, db: AsyncSession = Depends(get_db)):
    adjunto = await db.get(EAMAdjuntoOT, adjunto_id)
    if not adjunto:
        raise HTTPException(404, "Ese documento no existe")
    ruta = Path(settings.UPLOAD_DIR) / adjunto.ruta
    await db.delete(adjunto)
    await db.commit()
    # El archivo se borra después de la base: si se borrara antes y la
    # transacción fallara, quedaría una fila apuntando a un archivo inexistente.
    try:
        if ruta.exists():
            ruta.unlink()
    except OSError:
        # Un archivo que no se deja borrar no debe hacer fallar la operación:
        # la fila ya no está y el archivo queda huérfano, que es lo menos malo.
        pass
