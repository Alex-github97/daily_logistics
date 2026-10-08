"""
Mesa de ayuda: lo que ve y hace el cliente, y lo que ve y hace soporte.

Los dos lados comparten las mismas tablas pero NO las mismas reglas, y esa es
la parte delicada de este módulo:

  · El cliente solo ve los tickets de SU empresa, no puede cambiar el estado ni
    la criticidad, y no ve las notas internas del equipo.
  · Soporte ve la cola de todas las empresas y es quien clasifica.

Cada endpoint decide a qué lado pertenece; ninguno se apoya en que la pantalla
oculte algo, porque una URL escrita a mano se salta cualquier pantalla.
"""
import hashlib
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_plataforma
from app.core.security import decode_token
from app.infrastructure.models.plataforma import PlataformaCliente
from app.infrastructure.models.soporte import (
    SoporteTicket, SoporteMensaje, SoporteAdjunto,
    ESTADOS, CRITICIDADES, IMPACTOS,
)
from app.core.permisos_consola import exigir

router = APIRouter(prefix="/soporte", tags=["Soporte"])

ALMACEN = Path(settings.UPLOAD_DIR) / "soporte"

# Lo que se puede adjuntar. Se valida por extensión y por tipo declarado: la
# lista existe para no convertir la mesa de ayuda en un depósito de ejecutables.
EXTENSIONES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".xlsx", ".xls", ".csv", ".json", ".xml", ".txt", ".log",
    ".docx", ".doc", ".pptx", ".ppt", ".zip", ".rar", ".7z",
    ".eml", ".msg", ".mp4", ".webm",
}
MAX_BYTES = 15 * 1024 * 1024   # 15 MB por archivo


# ─── Quién está pidiendo ──────────────────────────────────────────────────────

class Solicitante(BaseModel):
    usuario: str
    empresa: str


def _quien(request: Request) -> Solicitante:
    """El usuario y la empresa que vienen firmados en el token.

    Se leen del token y nunca del cuerpo de la petición: si la empresa llegara
    como un campo más, cualquiera podría leer los tickets de otra escribiéndola.
    """
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Sesión no válida")
    try:
        datos = decode_token(auth[7:])
    except Exception:
        raise HTTPException(401, "Sesión no válida")
    if datos.get("type") != "access":   # el de refresco no abre la API
        raise HTTPException(401, "Sesión no válida")
    # `usr` es el nombre de usuario; `sub` el id. Los mensajes se firman con el
    # nombre: con el id salían atribuidos a un número.
    usuario, empresa = datos.get("usr") or datos.get("sub"), datos.get("cli")
    if not usuario or not empresa:
        raise HTTPException(403, "La sesión no indica usuario o empresa")
    return Solicitante(usuario=str(usuario), empresa=str(empresa))


async def _cliente_de(db: AsyncSession, codigo: str) -> PlataformaCliente:
    r = await db.execute(select(PlataformaCliente).where(PlataformaCliente.codigo == codigo))
    cliente = r.scalar_one_or_none()
    if not cliente:
        raise HTTPException(404, "La empresa de la sesión no está registrada")
    return cliente


async def _siguiente_numero(db: AsyncSession) -> str:
    """Consecutivo del año. Toma el mayor sufijo y no la cantidad de filas:
    contando, al borrar un ticket el siguiente repetiría un número ya usado."""
    anio = datetime.utcnow().year
    marca = f"SOP-{anio}-"
    r = await db.execute(
        select(func.max(SoporteTicket.numero)).where(SoporteTicket.numero.like(f"{marca}%")))
    ultimo = r.scalar()
    siguiente = 1
    if ultimo:
        try:
            siguiente = int(str(ultimo).rsplit("-", 1)[-1]) + 1
        except ValueError:
            siguiente = 1
    return f"{marca}{siguiente:04d}"


# La criticidad de partida sale del impacto declarado, pero soporte la cambia:
# es una propuesta, no la última palabra.
CRITICIDAD_SUGERIDA = {
    "CONSULTA": "BAJA",
    "MOLESTIA": "MEDIA",
    "BLOQUEA_TAREA": "ALTA",
    "OPERACION_DETENIDA": "CRITICA",
}


# ─── Lo que se manda y se devuelve ────────────────────────────────────────────

class AdjuntoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo_mime: Optional[str] = None
    tamano: Optional[int] = None
    creado_en: datetime
    mensaje_id: Optional[int] = None


class MensajeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    autor: str
    autor_nombre: Optional[str] = None
    es_soporte: bool
    cuerpo: str
    interno: bool
    creado_en: datetime
    adjuntos: List[AdjuntoResponse] = []


class TicketResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero: str
    asunto: str
    estado: str
    criticidad: str
    categoria: Optional[str] = None
    modulo: Optional[str] = None
    impacto: Optional[str] = None
    autor: str
    autor_nombre: Optional[str] = None
    cliente_codigo: str
    asignado_a: Optional[str] = None
    created_at: Optional[datetime] = None
    ultima_actividad: Optional[datetime] = None
    primera_respuesta_en: Optional[datetime] = None
    mensajes: int = 0


class TicketDetalle(TicketResumen):
    conversacion: List[MensajeResponse] = []


class TicketNuevo(BaseModel):
    asunto: str
    descripcion: str
    categoria: Optional[str] = None
    modulo: Optional[str] = None
    impacto: str = "MOLESTIA"


class MensajeNuevo(BaseModel):
    cuerpo: str
    # Solo soporte puede marcarlo; para el cliente se ignora.
    interno: bool = False


class CambioTicket(BaseModel):
    """Lo que solo soporte puede tocar."""
    estado: Optional[str] = None
    criticidad: Optional[str] = None
    asignado_a: Optional[str] = None
    categoria: Optional[str] = None


async def _armar_detalle(
    db: AsyncSession, ticket: SoporteTicket, incluir_internos: bool,
) -> TicketDetalle:
    q = select(SoporteMensaje).where(SoporteMensaje.ticket_id == ticket.id)
    if not incluir_internos:
        q = q.where(SoporteMensaje.interno == False)  # noqa: E712
    mensajes = list((await db.execute(q.order_by(SoporteMensaje.creado_en))).scalars().all())

    adjuntos = list((await db.execute(
        select(SoporteAdjunto).where(SoporteAdjunto.ticket_id == ticket.id))).scalars().all())
    por_mensaje: dict = {}
    for a in adjuntos:
        por_mensaje.setdefault(a.mensaje_id, []).append(AdjuntoResponse.model_validate(a))

    detalle = TicketDetalle.model_validate(ticket)
    detalle.mensajes = len(mensajes)
    detalle.conversacion = []
    for m in mensajes:
        ficha = MensajeResponse.model_validate(m)
        ficha.adjuntos = por_mensaje.get(m.id, [])
        detalle.conversacion.append(ficha)
    return detalle


# ═══ Lado del cliente ═════════════════════════════════════════════════════════

@router.get("/mis-tickets", response_model=List[TicketResumen])
async def mis_tickets(
    request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
):
    """Los tickets de la empresa de quien consulta. De ninguna otra."""
    quien = _quien(request)
    r = await db.execute(
        select(SoporteTicket)
        .where(SoporteTicket.cliente_codigo == quien.empresa)
        .order_by(SoporteTicket.ultima_actividad.desc().nullslast(),
                  SoporteTicket.id.desc()))
    tickets = list(r.scalars().all())
    if not tickets:
        return []
    conteos = dict((await db.execute(
        select(SoporteMensaje.ticket_id, func.count())
        .where(SoporteMensaje.ticket_id.in_([t.id for t in tickets]),
               SoporteMensaje.interno == False)  # noqa: E712
        .group_by(SoporteMensaje.ticket_id))).all())
    salida = []
    for t in tickets:
        ficha = TicketResumen.model_validate(t)
        ficha.mensajes = conteos.get(t.id, 0)
        salida.append(ficha)
    return salida


@router.post("/tickets", response_model=TicketDetalle, status_code=201)
async def crear_ticket(
    data: TicketNuevo, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
):
    quien = _quien(request)
    cliente = await _cliente_de(db, quien.empresa)

    asunto = (data.asunto or "").strip()
    cuerpo = (data.descripcion or "").strip()
    if not asunto:
        raise HTTPException(400, "Escriba un asunto: es lo que soporte ve primero en la cola.")
    if not cuerpo:
        raise HTTPException(400, "Describa qué pasó; sin eso soporte no puede empezar.")
    if data.impacto not in IMPACTOS:
        raise HTTPException(400, f"Impacto inválido. Use uno de: {', '.join(IMPACTOS)}.")

    ahora = datetime.utcnow()
    ticket = SoporteTicket(
        numero=await _siguiente_numero(db),
        cliente_id=cliente.id, cliente_codigo=cliente.codigo,
        autor=quien.usuario, autor_nombre=None,
        asunto=asunto, categoria=data.categoria, modulo=data.modulo,
        impacto=data.impacto,
        estado="NUEVO",
        # Propuesta a partir del impacto; soporte la ajusta al clasificar.
        criticidad=CRITICIDAD_SUGERIDA.get(data.impacto, "MEDIA"),
        ultima_actividad=ahora,
    )
    db.add(ticket)
    await db.flush()

    db.add(SoporteMensaje(
        ticket_id=ticket.id, autor=quien.usuario, es_soporte=False,
        cuerpo=cuerpo, interno=False, creado_en=ahora))
    await db.commit(); await db.refresh(ticket)
    return await _armar_detalle(db, ticket, incluir_internos=False)


async def _ticket_del_cliente(
    db: AsyncSession, ticket_id: int, quien: Solicitante,
) -> SoporteTicket:
    r = await db.execute(select(SoporteTicket).where(
        (SoporteTicket.id == ticket_id) &
        (SoporteTicket.cliente_codigo == quien.empresa)))
    ticket = r.scalar_one_or_none()
    # Mismo mensaje exista o no en otra empresa: decir "existe pero no es suyo"
    # ya revelaría que otra empresa tiene ese ticket.
    if not ticket:
        raise HTTPException(404, "Ese requerimiento no existe")
    return ticket


@router.get("/tickets/{ticket_id}", response_model=TicketDetalle)
async def ver_ticket(
    ticket_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
):
    quien = _quien(request)
    ticket = await _ticket_del_cliente(db, ticket_id, quien)
    return await _armar_detalle(db, ticket, incluir_internos=False)


@router.post("/tickets/{ticket_id}/mensajes", response_model=TicketDetalle)
async def responder_cliente(
    ticket_id: int, data: MensajeNuevo, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
):
    quien = _quien(request)
    ticket = await _ticket_del_cliente(db, ticket_id, quien)
    cuerpo = (data.cuerpo or "").strip()
    if not cuerpo:
        raise HTTPException(400, "El mensaje está vacío")

    ahora = datetime.utcnow()
    db.add(SoporteMensaje(
        ticket_id=ticket.id, autor=quien.usuario, es_soporte=False,
        cuerpo=cuerpo, interno=False, creado_en=ahora))
    ticket.ultima_actividad = ahora
    # Que el cliente escriba reabre lo cerrado: si vuelve a hablar es que el
    # asunto no estaba resuelto, y un ticket cerrado no lo ve nadie en la cola.
    if ticket.estado in ("RESUELTO", "CERRADO", "ESPERANDO_CLIENTE"):
        ticket.estado = "EN_PROGRESO"
        ticket.cerrado_en = None
    await db.commit(); await db.refresh(ticket)
    return await _armar_detalle(db, ticket, incluir_internos=False)


# ═══ Lado de soporte ══════════════════════════════════════════════════════════

@router.get("/cola", response_model=List[TicketResumen])
async def cola(
    estado: Optional[str] = None, criticidad: Optional[str] = None,
    empresa: Optional[str] = None, buscar: Optional[str] = None,
    incluir_cerrados: bool = False,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    """La cola de todas las empresas."""
    q = select(SoporteTicket)
    if estado:
        q = q.where(SoporteTicket.estado == estado.upper())
    elif not incluir_cerrados:
        # Por defecto no se muestran los cerrados: la cola sirve para trabajar,
        # no para consultar el histórico.
        q = q.where(SoporteTicket.estado != "CERRADO")
    if criticidad:
        q = q.where(SoporteTicket.criticidad == criticidad.upper())
    if empresa:
        q = q.where(SoporteTicket.cliente_codigo == empresa)
    if buscar:
        patron = f"%{buscar.strip()}%"
        q = q.where(or_(SoporteTicket.asunto.ilike(patron),
                        SoporteTicket.numero.ilike(patron)))

    tickets = list((await db.execute(
        q.order_by(SoporteTicket.ultima_actividad.desc().nullslast(),
                   SoporteTicket.id.desc()).limit(500))).scalars().all())
    if not tickets:
        return []
    conteos = dict((await db.execute(
        select(SoporteMensaje.ticket_id, func.count())
        .where(SoporteMensaje.ticket_id.in_([t.id for t in tickets]))
        .group_by(SoporteMensaje.ticket_id))).all())
    salida = []
    for t in tickets:
        ficha = TicketResumen.model_validate(t)
        ficha.mensajes = conteos.get(t.id, 0)
        salida.append(ficha)
    return salida


@router.get("/cola/{ticket_id}", response_model=TicketDetalle)
async def ver_como_soporte(
    ticket_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    ticket = await db.get(SoporteTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ese requerimiento no existe")
    return await _armar_detalle(db, ticket, incluir_internos=True)


@router.put("/cola/{ticket_id}", response_model=TicketDetalle)
async def clasificar(
    ticket_id: int, data: CambioTicket, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    """Estado, criticidad y responsable. Solo soporte."""
    ticket = await db.get(SoporteTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ese requerimiento no existe")

    cambios = data.model_dump(exclude_unset=True)
    if cambios.get("estado"):
        nuevo = cambios["estado"].upper()
        if nuevo not in ESTADOS:
            raise HTTPException(400, f"Estado inválido. Use uno de: {', '.join(ESTADOS)}.")
        cambios["estado"] = nuevo
        ahora = datetime.utcnow()
        if nuevo == "RESUELTO" and not ticket.resuelto_en:
            ticket.resuelto_en = ahora
        if nuevo == "CERRADO":
            ticket.cerrado_en = ahora
        elif nuevo != "RESUELTO":
            # Reabrir borra las marcas de fin, o las métricas quedarían mintiendo.
            ticket.cerrado_en = None
            if nuevo in ("NUEVO", "EN_PROGRESO"):
                ticket.resuelto_en = None
    if cambios.get("criticidad"):
        nueva = cambios["criticidad"].upper()
        if nueva not in CRITICIDADES:
            raise HTTPException(
                400, f"Criticidad inválida. Use una de: {', '.join(CRITICIDADES)}.")
        cambios["criticidad"] = nueva

    for campo, valor in cambios.items():
        setattr(ticket, campo, valor)
    ticket.ultima_actividad = datetime.utcnow()
    await db.commit(); await db.refresh(ticket)
    return await _armar_detalle(db, ticket, incluir_internos=True)


@router.post("/cola/{ticket_id}/mensajes", response_model=TicketDetalle)
async def responder_soporte(
    ticket_id: int, data: MensajeNuevo, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.atender")),
):
    quien = _quien(request)
    ticket = await db.get(SoporteTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ese requerimiento no existe")
    cuerpo = (data.cuerpo or "").strip()
    if not cuerpo:
        raise HTTPException(400, "El mensaje está vacío")

    ahora = datetime.utcnow()
    db.add(SoporteMensaje(
        ticket_id=ticket.id, autor=quien.usuario, es_soporte=True,
        cuerpo=cuerpo, interno=bool(data.interno), creado_en=ahora))
    ticket.ultima_actividad = ahora
    # Una nota interna no es atender al cliente: no cuenta como respuesta ni
    # mueve el estado, o la métrica premiaría hablar entre nosotros.
    if not data.interno:
        if not ticket.primera_respuesta_en:
            ticket.primera_respuesta_en = ahora
        if ticket.estado == "NUEVO":
            ticket.estado = "EN_PROGRESO"
    await db.commit(); await db.refresh(ticket)
    return await _armar_detalle(db, ticket, incluir_internos=True)


# ═══ Adjuntos ═════════════════════════════════════════════════════════════════

def _validar_archivo(nombre: str, contenido: bytes) -> str:
    if not contenido:
        raise HTTPException(400, "El archivo está vacío")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(
            400,
            f"«{nombre}» pesa {len(contenido) // (1024 * 1024)} MB y el máximo son "
            f"{MAX_BYTES // (1024 * 1024)} MB. Comprímalo o divídalo.",
        )
    extension = os.path.splitext(nombre or "")[1].lower()
    if extension not in EXTENSIONES:
        raise HTTPException(
            400,
            f"No se admiten archivos «{extension or 'sin extensión'}». "
            f"Se aceptan: {', '.join(sorted(e.lstrip('.') for e in EXTENSIONES))}.",
        )
    return extension


def _nombre_seguro(nombre: str) -> str:
    """Sin rutas ni caracteres raros: el nombre lo escribe quien sube el archivo."""
    limpio = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.basename(nombre or "archivo"))
    return limpio[:120] or "archivo"


async def _guardar_adjuntos(
    db: AsyncSession, ticket: SoporteTicket, mensaje_id: Optional[int],
    usuario: str, archivos: List[UploadFile],
) -> List[SoporteAdjunto]:
    guardados = []
    ALMACEN.mkdir(parents=True, exist_ok=True)
    for archivo in archivos:
        contenido = await archivo.read()
        nombre = _nombre_seguro(archivo.filename or "archivo")
        _validar_archivo(nombre, contenido)
        firma = hashlib.md5(contenido).hexdigest()[:10]
        relativa = f"soporte/t{ticket.id}_{firma}_{nombre}"
        (Path(settings.UPLOAD_DIR) / relativa).write_bytes(contenido)
        adjunto = SoporteAdjunto(
            ticket_id=ticket.id, mensaje_id=mensaje_id, nombre=nombre,
            tipo_mime=archivo.content_type or mimetypes.guess_type(nombre)[0],
            tamano=len(contenido), ruta=relativa, subido_por=usuario,
            creado_en=datetime.utcnow(),
        )
        db.add(adjunto)
        guardados.append(adjunto)
    return guardados


@router.post("/tickets/{ticket_id}/adjuntos", response_model=TicketDetalle)
async def adjuntar(
    ticket_id: int, request: Request,
    archivos: List[UploadFile] = File(...),
    cuerpo: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_plataforma),
):
    """Adjunta archivos al ticket, opcionalmente con un mensaje.

    Sirve para los dos lados: si quien sube es de la empresa dueña del ticket,
    entra por ahí; si es soporte, el mensaje queda marcado como suyo.
    """
    quien = _quien(request)
    cliente = await _cliente_de(db, quien.empresa)

    ticket = await db.get(SoporteTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ese requerimiento no existe")
    es_soporte = bool(cliente.es_operador)
    if not es_soporte and ticket.cliente_codigo != quien.empresa:
        raise HTTPException(404, "Ese requerimiento no existe")

    ahora = datetime.utcnow()
    mensaje_id = None
    texto = (cuerpo or "").strip()
    if texto:
        mensaje = SoporteMensaje(
            ticket_id=ticket.id, autor=quien.usuario, es_soporte=es_soporte,
            cuerpo=texto, interno=False, creado_en=ahora)
        db.add(mensaje)
        await db.flush()
        mensaje_id = mensaje.id
        if es_soporte and not ticket.primera_respuesta_en:
            ticket.primera_respuesta_en = ahora

    await _guardar_adjuntos(db, ticket, mensaje_id, quien.usuario, archivos)
    ticket.ultima_actividad = ahora
    await db.commit(); await db.refresh(ticket)
    return await _armar_detalle(db, ticket, incluir_internos=es_soporte)


@router.get("/adjuntos/{adjunto_id}")
async def descargar(
    adjunto_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
):
    """Descarga con permisos.

    No se sirve por carpeta pública a propósito: un pantallazo adjunto a un
    ticket puede traer datos de otra empresa, y una URL adivinable los expondría.
    """
    quien = _quien(request)
    adjunto = await db.get(SoporteAdjunto, adjunto_id)
    if not adjunto:
        raise HTTPException(404, "Ese archivo no existe")
    ticket = await db.get(SoporteTicket, adjunto.ticket_id)
    if not ticket:
        raise HTTPException(404, "Ese archivo no existe")

    cliente = await _cliente_de(db, quien.empresa)
    if not cliente.es_operador and ticket.cliente_codigo != quien.empresa:
        raise HTTPException(404, "Ese archivo no existe")

    ruta = Path(settings.UPLOAD_DIR) / adjunto.ruta
    # La ruta se recompone desde la base, pero se comprueba igual que no salga
    # del almacén: un `..` guardado por error no debe poder leer otra cosa.
    try:
        ruta.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(404, "Ese archivo no existe")
    if not ruta.exists():
        raise HTTPException(410, "El archivo ya no está en el servidor")

    return FileResponse(
        ruta, filename=adjunto.nombre,
        media_type=adjunto.tipo_mime or "application/octet-stream")


# ─── Resumen para la consola ──────────────────────────────────────────────────

class ResumenSoporte(BaseModel):
    abiertos: int = 0
    sin_responder: int = 0
    criticos: int = 0
    por_estado: dict = {}
    por_criticidad: dict = {}


@router.get("/resumen", response_model=ResumenSoporte)
async def resumen(
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("soporte.ver")),
):
    tickets = list((await db.execute(select(SoporteTicket))).scalars().all())
    abiertos = [t for t in tickets if t.estado != "CERRADO"]
    r = ResumenSoporte(
        abiertos=len(abiertos),
        sin_responder=sum(1 for t in abiertos if not t.primera_respuesta_en),
        criticos=sum(1 for t in abiertos if t.criticidad == "CRITICA"),
    )
    for t in abiertos:
        r.por_estado[t.estado] = r.por_estado.get(t.estado, 0) + 1
        r.por_criticidad[t.criticidad] = r.por_criticidad.get(t.criticidad, 0) + 1
    return r
