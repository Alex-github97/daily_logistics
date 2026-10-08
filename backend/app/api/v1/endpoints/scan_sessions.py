"""
Sesiones de escaneo — permiten vincular un celular como escáner remoto.
No requieren autenticación: el UUID de sesión actúa como token de seguridad.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_plataforma
from pydantic import BaseModel
import uuid
import socket

router = APIRouter(prefix="/scan-sessions", tags=["Scan Sessions"])


@router.get("/server-ip")
async def get_server_ip():
    """Devuelve la IP LAN del PC host (necesaria para generar el QR que abre el celular)."""
    ip = ""
    # Docker Desktop for Windows expone la IP del host via host.docker.internal
    try:
        ip = socket.gethostbyname("host.docker.internal")
    except Exception:
        pass
    if not ip:
        # Fallback: conectar a DNS externo para descubrir la interfaz de salida
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
    return {"ip": ip}

# Las sesiones viven en Postgres (public.scan_sesion), no en un diccionario del
# proceso: en producción hay varios workers y el celular y el PC casi nunca
# caen en el mismo. Una hora de vida, como antes.
_TTL = 3600
_VIGENTE = "creada > now() - make_interval(secs => :ttl)"


class CodePayload(BaseModel):
    code: str


@router.post("/", status_code=201)
async def create_session(db: AsyncSession = Depends(get_db_plataforma)):
    await db.execute(text(
        "DELETE FROM public.scan_sesion WHERE creada <= now() - make_interval(secs => :ttl)"),
        {"ttl": _TTL})
    session_id = str(uuid.uuid4())
    await db.execute(text("INSERT INTO public.scan_sesion (id) VALUES (:id)"), {"id": session_id})
    return {"id": session_id}


@router.post("/{session_id}/code")
async def push_code(session_id: str, payload: CodePayload,
                    db: AsyncSession = Depends(get_db_plataforma)):
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=422, detail="El código no puede estar vacío")
    # Se agrega en la misma sentencia: dos lecturas seguidas del celular no se
    # pisan aunque lleguen a procesos distintos.
    total = (await db.execute(text(
        "UPDATE public.scan_sesion SET codigos = codigos || jsonb_build_array(CAST(:c AS text)) "
        f"WHERE id = :id AND {_VIGENTE} RETURNING jsonb_array_length(codigos)"),
        {"c": code, "id": session_id, "ttl": _TTL})).scalar()
    if total is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
    return {"ok": True, "total": total}


@router.get("/{session_id}/codes")
async def get_codes(session_id: str, since: int = 0,
                    db: AsyncSession = Depends(get_db_plataforma)):
    codigos = (await db.execute(text(
        f"SELECT codigos FROM public.scan_sesion WHERE id = :id AND {_VIGENTE}"),
        {"id": session_id, "ttl": _TTL})).scalar()
    if codigos is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
    return {"codes": codigos[since:], "total": len(codigos)}


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db_plataforma)):
    await db.execute(text("DELETE FROM public.scan_sesion WHERE id = :id"), {"id": session_id})
