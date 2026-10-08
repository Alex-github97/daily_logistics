"""
Lo que la pantalla de garantías necesitaba y no tenía: catálogos que sirvan a
cualquier perfil y documentos de verdad.

LOS DESPLEGABLES NO FUNCIONABAN POR TRES CAUSAS DISTINTAS
  - Proveedores salía de `/proveedores/`, el maestro general, vacío en el CMMS:
    los proveedores del mantenimiento son los contratistas.
  - Responsables salía de `/usuarios/`, que solo puede listar un administrador:
    para cualquier otro perfil la lista llegaba vacía.
  - Activos era un select sin búsqueda; con una flota real es inmanejable.

Este catálogo junta cada fuente y entrega solo nombres, que es lo que el
formulario necesita. No expone correos ni permisos, así que no hace falta
ser administrador para pedirlo.
"""
import hashlib
import mimetypes
import os
import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.eam_adjuntos import EXTENSIONES, MAX_BYTES, _nombre_seguro, _usuario
from app.core.config import settings
from app.core.database import get_db
from app.core.tenant import ESQUEMA_POR_DEFECTO, esquema_actual
from app.infrastructure.models.eam import EAMActivo, EAMAdjuntoGarantia, EAMContratista, EAMGarantia
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/eam", tags=["CMMS/EAM · Garantías"])


@router.get("/garantias-catalogos")
async def catalogos(db: AsyncSession = Depends(get_db)):
    activos = (await db.execute(select(EAMActivo).where(EAMActivo.activo.is_(True))
                                .order_by(EAMActivo.codigo))).scalars().all()
    usados = (await db.execute(select(EAMGarantia.proveedor, EAMGarantia.responsable))).all()

    proveedores = {c.nombre.strip() for c in (await db.execute(
        select(EAMContratista).where(EAMContratista.activo.is_(True)))).scalars().all() if c.nombre}
    try:
        from app.infrastructure.models.proveedor import Proveedor  # maestro general, si existe
        for p in (await db.execute(select(Proveedor))).scalars().all():
            nombre = getattr(p, "nombre_comercial", None) or getattr(p, "razon_social", None)
            if nombre:
                proveedores.add(nombre.strip())
    except Exception:
        pass
    proveedores |= {p.strip() for p, _ in usados if p and p.strip()}

    responsables = {f"{u.nombre or ''} {u.apellido or ''}".strip() for u in (await db.execute(
        select(Usuario).where(Usuario.activo.is_(True)))).scalars().all()}
    responsables |= {r.strip() for _, r in usados if r and r.strip()}
    responsables.discard("")

    contratistas = {c.nombre.strip(): {"contacto": c.contacto, "telefono": c.telefono}
                    for c in (await db.execute(select(EAMContratista).where(EAMContratista.activo.is_(True)))).scalars().all()
                    if c.nombre}
    return {
        "activos": [{"id": a.id, "codigo": a.codigo, "nombre": a.nombre, "placa": a.placa, "marca": a.marca}
                    for a in activos],
        "proveedores": sorted(proveedores, key=str.lower),
        "responsables": sorted(responsables, key=str.lower),
        # Contacto y teléfono de los contratistas: al escoger uno, el formulario
        # los llena en vez de pedir que se digiten otra vez.
        "contactos": contratistas,
    }


def _carpeta() -> str:
    esquema = esquema_actual() or ESQUEMA_POR_DEFECTO
    return f"eam_garantia/{re.sub(r'[^A-Za-z0-9_]', '_', esquema)}"


def _ficha(a: EAMAdjuntoGarantia) -> dict:
    return {"id": a.id, "garantia_id": a.garantia_id, "nombre": a.nombre, "tipo_mime": a.tipo_mime,
            "tamano": a.tamano, "subido_por": a.subido_por,
            "created_at": a.created_at.isoformat() if a.created_at else None}


@router.get("/garantias/{gid}/adjuntos")
async def listar_adjuntos(gid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMAdjuntoGarantia).where(EAMAdjuntoGarantia.garantia_id == gid)
                         .order_by(EAMAdjuntoGarantia.id.desc()))
    return [_ficha(a) for a in r.scalars().all()]


@router.post("/garantias/{gid}/adjuntos", status_code=201)
async def subir_adjuntos(gid: int, request: Request, archivos: List[UploadFile] = File(...),
                         db: AsyncSession = Depends(get_db)):
    g = await db.get(EAMGarantia, gid)
    if not g:
        raise HTTPException(404, "Esa garantía no existe")
    destino = Path(settings.UPLOAD_DIR) / _carpeta()
    destino.mkdir(parents=True, exist_ok=True)
    guardados = []
    for archivo in archivos:
        contenido = await archivo.read()
        nombre = _nombre_seguro(archivo.filename or "archivo")
        if not contenido:
            raise HTTPException(400, f"«{nombre}» está vacío")
        if len(contenido) > MAX_BYTES:
            raise HTTPException(400, f"«{nombre}» pesa más de {MAX_BYTES // (1024 * 1024)} MB")
        extension = os.path.splitext(nombre)[1].lower()
        if extension not in EXTENSIONES:
            raise HTTPException(400, f"No se admiten archivos «{extension or 'sin extensión'}»")
        relativa = f"{_carpeta()}/g{gid}_{hashlib.md5(contenido).hexdigest()[:10]}_{nombre}"
        (Path(settings.UPLOAD_DIR) / relativa).write_bytes(contenido)
        a = EAMAdjuntoGarantia(garantia_id=gid, nombre=nombre, ruta=relativa, tamano=len(contenido),
                               tipo_mime=archivo.content_type or mimetypes.guess_type(nombre)[0],
                               subido_por=_usuario(request))
        db.add(a)
        guardados.append(a)
    # El campo «documento» de la garantía conserva el nombre del contrato para
    # los listados y el reporte: si estaba vacío, se toma el primer archivo.
    if not (g.documento or "").strip() and guardados:
        g.documento = guardados[0].nombre
    await db.commit()
    for a in guardados:
        await db.refresh(a)
    return [_ficha(a) for a in guardados]


@router.get("/garantias-adjuntos/{aid}/descargar")
async def descargar_adjunto(aid: int, db: AsyncSession = Depends(get_db)):
    a = await db.get(EAMAdjuntoGarantia, aid)
    if not a:
        raise HTTPException(404, "Ese documento no existe")
    ruta = Path(settings.UPLOAD_DIR) / a.ruta
    try:
        ruta.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(404, "Ese documento no existe")
    if not ruta.exists():
        raise HTTPException(410, "El archivo ya no está en el servidor")
    return FileResponse(ruta, filename=a.nombre, media_type=a.tipo_mime or "application/octet-stream")


@router.delete("/garantias-adjuntos/{aid}", status_code=204)
async def borrar_adjunto(aid: int, db: AsyncSession = Depends(get_db)):
    a = await db.get(EAMAdjuntoGarantia, aid)
    if not a:
        raise HTTPException(404, "Ese documento no existe")
    ruta = Path(settings.UPLOAD_DIR) / a.ruta
    await db.delete(a)
    await db.commit()
    try:
        if ruta.exists():
            ruta.unlink()
    except OSError:
        pass
