"""
Análisis de causa raíz de las órdenes de trabajo.

Es un informe **estructurado**, no un archivo adjunto. La diferencia es la razón
de ser del módulo: de un PDF adjunto no se puede sacar «cuál es la falla que más
nos cuesta en los Freightliner»; de campos con estructura, sí. El PDF exportable
se genera a partir de estos datos, no al revés.

Las evidencias van aparte de los adjuntos de la OT: aquellos son los soportes
comerciales —cotización, factura, orden de compra— y estas son la evidencia
técnica que se embebe en el informe.
"""
import hashlib
import mimetypes
import os
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.core.tenant import esquema_actual, ESQUEMA_POR_DEFECTO
from app.api.v1.endpoints import eam_causa_raiz_pdf
from app.infrastructure.models.eam import (
    EAMCausaRaiz, EAMCausaRaizAccion, EAMCausaRaizEvidencia,
    EAMOrdenTrabajo, EAMActivo, METODOLOGIAS_RCA, ESTADOS_RCA,
)
from app.infrastructure.models.catalogo import CatalogoMaestro

router = APIRouter(prefix="/eam", tags=["CMMS/EAM"])

# Solo imágenes y PDF: la evidencia se embebe en el informe, y un .zip dentro de
# un PDF no prueba nada.
EXTENSIONES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".heic", ".pdf"}
IMAGENES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
MAX_BYTES = 20 * 1024 * 1024


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
    esquema = esquema_actual() or ESQUEMA_POR_DEFECTO
    return f"eam_rca/{re.sub(r'[^A-Za-z0-9_]', '_', esquema)}"


def _nombre_seguro(nombre: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.basename(nombre or "archivo"))
    return limpio[:120] or "archivo"


# ─── Esquemas ─────────────────────────────────────────────────────────────────

class Accion(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    tipo: str = "CORRECTIVA"
    descripcion: str
    responsable: Optional[str] = None
    fecha_compromiso: Optional[date] = None
    estado: str = "PENDIENTE"
    fecha_cierre: Optional[date] = None
    orden: int = 0


class Evidencia(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo_mime: Optional[str] = None
    tamano: Optional[int] = None
    descripcion: Optional[str] = None
    orden: int = 0


class Porque(BaseModel):
    pregunta: str = ""
    respuesta: str = ""


class CausaRaiz(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    ot_id: Optional[int] = None
    ot_numero: Optional[str] = None
    activo_id: Optional[int] = None

    fecha_analisis: Optional[date] = None
    analista: Optional[str] = None
    participantes: Optional[str] = None
    metodologia: str = "CINCO_PORQUES"
    estado: str = "BORRADOR"

    descripcion_evento: Optional[str] = None
    deteccion: Optional[str] = None
    modo_falla: Optional[str] = None
    categoria_causa: Optional[str] = None

    porques: Optional[List[Porque]] = None
    causa_inmediata: Optional[str] = None
    causa_raiz: Optional[str] = None
    factores_contribuyentes: Optional[str] = None

    horas_parada: Optional[float] = None
    costo_estimado: Optional[float] = None
    hubo_lesion: bool = False
    hubo_ambiental: bool = False

    conclusiones: Optional[str] = None
    verificacion_eficacia: Optional[str] = None
    fecha_verificacion: Optional[date] = None
    eficaz: Optional[bool] = None

    elaborado_por: Optional[str] = None
    acciones: List[Accion] = []
    evidencias: List[Evidencia] = []


async def _armar(db: AsyncSession, rca: EAMCausaRaiz) -> CausaRaiz:
    ficha = CausaRaiz.model_validate(rca)
    acciones = (await db.execute(
        select(EAMCausaRaizAccion)
        .where(EAMCausaRaizAccion.causa_raiz_id == rca.id)
        .order_by(EAMCausaRaizAccion.orden, EAMCausaRaizAccion.id))).scalars().all()
    ficha.acciones = [Accion.model_validate(a) for a in acciones]
    evidencias = (await db.execute(
        select(EAMCausaRaizEvidencia)
        .where(EAMCausaRaizEvidencia.causa_raiz_id == rca.id)
        .order_by(EAMCausaRaizEvidencia.orden, EAMCausaRaizEvidencia.id))).scalars().all()
    ficha.evidencias = [Evidencia.model_validate(e) for e in evidencias]
    return ficha


# ─── El informe ───────────────────────────────────────────────────────────────

@router.get("/ots/{ot_id}/causa-raiz", response_model=Optional[CausaRaiz])
async def ver(ot_id: int, db: AsyncSession = Depends(get_db)):
    """El análisis de esa OT, o vacío si todavía no tiene."""
    r = await db.execute(select(EAMCausaRaiz).where(EAMCausaRaiz.ot_id == ot_id))
    rca = r.scalar_one_or_none()
    return await _armar(db, rca) if rca else None


# La clasificación del análisis sale de estos catálogos del maestro. La pantalla
# ya los ofrece como listas, pero un valor puede llegar por importación o venir
# de un análisis escrito antes de que las listas existieran.
CATALOGOS_CLASIFICACION = {
    "deteccion": "METODO_DETECCION",
    "modo_falla": "MODO_FALLA",
    "categoria_causa": "CATEGORIA_CAUSA",
}


async def _normalizar_clasificacion(db: AsyncSession, campos: Dict[str, Any]) -> None:
    """Deja la clasificación escrita como está en el catálogo. Modifica en sitio.

    No rechaza lo que no reconoce, y es a propósito: un análisis se guarda en
    borrador varias veces y bloquear el guardado por una palabra que todavía no
    está en la lista sería peor que el problema. Lo que sí hace es que «fuga de
    aceite» y «FUGA DE ACEITE» dejen de contar como dos causas distintas, que es
    lo único que impide que el tablero las sume.
    """
    pendientes = {c: (campos.get(c) or "").strip()
                  for c in CATALOGOS_CLASIFICACION if campos.get(c)}
    if not pendientes:
        return
    r = await db.execute(select(CatalogoMaestro).where(
        CatalogoMaestro.modulo == "EAM",
        CatalogoMaestro.tipo.in_(set(CATALOGOS_CLASIFICACION.values())),
        CatalogoMaestro.activo.is_(True)))
    por_tipo: Dict[str, Dict[str, str]] = {}
    for valor in r.scalars().all():
        por_tipo.setdefault(valor.tipo, {})[valor.nombre.strip().lower()] = valor.nombre
    for campo, texto in pendientes.items():
        oficial = por_tipo.get(CATALOGOS_CLASIFICACION[campo], {}).get(texto.lower())
        campos[campo] = oficial or texto


@router.put("/ots/{ot_id}/causa-raiz", response_model=CausaRaiz)
async def guardar(
    ot_id: int, data: CausaRaiz, request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Crea o actualiza el análisis. Las acciones se reemplazan completas.

    Se manda la lista entera de acciones y no diferencias sueltas: es lo que la
    pantalla tiene en la mano, y evita que un borrado se pierda por el camino.
    """
    ot = await db.get(EAMOrdenTrabajo, ot_id)
    if not ot:
        raise HTTPException(404, "Esa orden de trabajo no existe")
    if data.metodologia and data.metodologia not in METODOLOGIAS_RCA:
        raise HTTPException(
            400, f"Metodología inválida. Use una de: {', '.join(METODOLOGIAS_RCA)}.")
    if data.estado and data.estado not in ESTADOS_RCA:
        raise HTTPException(400, f"Estado inválido. Use uno de: {', '.join(ESTADOS_RCA)}.")

    # Cerrar el análisis exige lo mínimo que lo vuelve útil: sin causa raíz ni
    # acciones, un informe cerrado es un formulario lleno que no cambia nada.
    if data.estado == "CERRADO":
        if not (data.causa_raiz or "").strip():
            raise HTTPException(
                409, "No se puede cerrar sin escribir la causa raíz.")
        if not data.acciones:
            raise HTTPException(
                409,
                "No se puede cerrar sin al menos una acción. Un análisis sin acciones "
                "no evita que vuelva a pasar.",
            )

    r = await db.execute(select(EAMCausaRaiz).where(EAMCausaRaiz.ot_id == ot_id))
    rca = r.scalar_one_or_none()
    if not rca:
        rca = EAMCausaRaiz(ot_id=ot_id, elaborado_por=_usuario(request))
        db.add(rca)

    campos = data.model_dump(exclude={"id", "ot_id", "acciones", "evidencias",
                                      "ot_numero", "activo_id", "porques"},
                             exclude_unset=True)
    await _normalizar_clasificacion(db, campos)
    for campo, valor in campos.items():
        setattr(rca, campo, valor)
    if data.porques is not None:
        rca.porques = [p.model_dump() for p in data.porques]
    # Se copian de la OT: el histórico no debe depender de que la OT siga viva.
    rca.ot_numero = ot.numero
    rca.activo_id = ot.activo_id
    await db.flush()

    if data.acciones is not None:
        await db.execute(
            EAMCausaRaizAccion.__table__.delete().where(
                EAMCausaRaizAccion.causa_raiz_id == rca.id))
        for i, a in enumerate(data.acciones):
            if not (a.descripcion or "").strip():
                continue
            db.add(EAMCausaRaizAccion(
                causa_raiz_id=rca.id, tipo=a.tipo, descripcion=a.descripcion.strip(),
                responsable=a.responsable, fecha_compromiso=a.fecha_compromiso,
                estado=a.estado, fecha_cierre=a.fecha_cierre, orden=i))

    await db.commit(); await db.refresh(rca)
    return await _armar(db, rca)


@router.delete("/causa-raiz/{rca_id}", status_code=204)
async def borrar(rca_id: int, db: AsyncSession = Depends(get_db)):
    rca = await db.get(EAMCausaRaiz, rca_id)
    if not rca:
        raise HTTPException(404, "Ese análisis no existe")
    await db.delete(rca)
    await db.commit()


# ─── Evidencias ───────────────────────────────────────────────────────────────

@router.post("/causa-raiz/{rca_id}/evidencias", response_model=List[Evidencia],
             status_code=201)
async def subir_evidencia(
    rca_id: int, request: Request,
    archivos: List[UploadFile] = File(...),
    descripcion: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    rca = await db.get(EAMCausaRaiz, rca_id)
    if not rca:
        raise HTTPException(404, "Ese análisis no existe")

    carpeta = _carpeta()
    (Path(settings.UPLOAD_DIR) / carpeta).mkdir(parents=True, exist_ok=True)
    siguiente = (await db.execute(
        select(func.coalesce(func.max(EAMCausaRaizEvidencia.orden), -1))
        .where(EAMCausaRaizEvidencia.causa_raiz_id == rca_id))).scalar() + 1

    guardadas = []
    for archivo in archivos:
        contenido = await archivo.read()
        nombre = _nombre_seguro(archivo.filename or "evidencia")
        if not contenido:
            raise HTTPException(400, f"«{nombre}» está vacío")
        if len(contenido) > MAX_BYTES:
            raise HTTPException(
                400, f"«{nombre}» supera los {MAX_BYTES // (1024 * 1024)} MB")
        extension = os.path.splitext(nombre)[1].lower()
        if extension not in EXTENSIONES:
            raise HTTPException(
                400,
                f"Como evidencia solo se admiten imágenes y PDF, no «{extension}». "
                "Los soportes comerciales van en la sección Documentos de la orden.",
            )
        firma = hashlib.md5(contenido).hexdigest()[:10]
        relativa = f"{carpeta}/rca{rca_id}_{firma}_{nombre}"
        (Path(settings.UPLOAD_DIR) / relativa).write_bytes(contenido)
        evidencia = EAMCausaRaizEvidencia(
            causa_raiz_id=rca_id, nombre=nombre, ruta=relativa,
            tipo_mime=archivo.content_type or mimetypes.guess_type(nombre)[0],
            tamano=len(contenido), descripcion=descripcion, orden=siguiente,
            subido_por=_usuario(request))
        siguiente += 1
        db.add(evidencia)
        guardadas.append(evidencia)

    await db.commit()
    for e in guardadas:
        await db.refresh(e)
    return [Evidencia.model_validate(e) for e in guardadas]


@router.put("/causa-raiz/evidencias/{evidencia_id}", response_model=Evidencia)
async def describir_evidencia(
    evidencia_id: int, descripcion: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """El pie de foto. Una evidencia sin explicación no prueba nada."""
    e = await db.get(EAMCausaRaizEvidencia, evidencia_id)
    if not e:
        raise HTTPException(404, "Esa evidencia no existe")
    e.descripcion = descripcion
    await db.commit(); await db.refresh(e)
    return Evidencia.model_validate(e)


@router.get("/causa-raiz/evidencias/{evidencia_id}/descargar")
async def descargar_evidencia(evidencia_id: int, db: AsyncSession = Depends(get_db)):
    e = await db.get(EAMCausaRaizEvidencia, evidencia_id)
    if not e:
        raise HTTPException(404, "Esa evidencia no existe")
    ruta = Path(settings.UPLOAD_DIR) / e.ruta
    try:
        ruta.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(404, "Esa evidencia no existe")
    if not ruta.exists():
        raise HTTPException(410, "El archivo ya no está en el servidor")
    return FileResponse(ruta, filename=e.nombre,
                        media_type=e.tipo_mime or "application/octet-stream")


@router.delete("/causa-raiz/evidencias/{evidencia_id}", status_code=204)
async def borrar_evidencia(evidencia_id: int, db: AsyncSession = Depends(get_db)):
    e = await db.get(EAMCausaRaizEvidencia, evidencia_id)
    if not e:
        raise HTTPException(404, "Esa evidencia no existe")
    ruta = Path(settings.UPLOAD_DIR) / e.ruta
    await db.delete(e)
    await db.commit()
    try:
        if ruta.exists():
            ruta.unlink()
    except OSError:
        pass


@router.get("/causa-raiz/{rca_id}/pdf")
async def exportar_pdf(rca_id: int, db: AsyncSession = Depends(get_db)):
    """El informe completo en PDF, con las evidencias embebidas."""
    rca = await db.get(EAMCausaRaiz, rca_id)
    if not rca:
        raise HTTPException(404, "Ese analisis no existe")

    activo = await db.get(EAMActivo, rca.activo_id) if rca.activo_id else None
    acciones = list((await db.execute(
        select(EAMCausaRaizAccion)
        .where(EAMCausaRaizAccion.causa_raiz_id == rca_id)
        .order_by(EAMCausaRaizAccion.orden))).scalars().all())
    evidencias = list((await db.execute(
        select(EAMCausaRaizEvidencia)
        .where(EAMCausaRaizEvidencia.causa_raiz_id == rca_id)
        .order_by(EAMCausaRaizEvidencia.orden))).scalars().all())

    salida = eam_causa_raiz_pdf.construir(rca, activo, acciones, evidencias)
    nombre = f"causa-raiz-{rca.ot_numero or rca_id}.pdf".replace("/", "-")
    return StreamingResponse(
        salida, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# ─── Analitica para el dashboard de mantenimiento ─────────────────────────────
#
# Esta es la razon de que el informe sea estructurado y no un archivo: se puede
# contar. Todo se agrupa cruzando el analisis con la OT y su activo, que es
# donde viven la marca y la linea.

class FilaConteo(BaseModel):
    etiqueta: str
    cantidad: int = 0
    costo: float = 0
    horas: float = 0


class AnaliticaCausas(BaseModel):
    total: int = 0
    cerrados: int = 0
    costo_total: float = 0
    horas_total: float = 0
    # Acciones comprometidas que ya pasaron su fecha: es el sintoma de que los
    # analisis se hacen pero no se cierran.
    acciones_vencidas: int = 0
    por_causa: List[FilaConteo] = []
    por_modo_falla: List[FilaConteo] = []
    por_marca: List[FilaConteo] = []
    por_linea: List[FilaConteo] = []
    por_tipo_activo: List[FilaConteo] = []
    por_activo: List[FilaConteo] = []


def _acumular(destino: Dict[str, FilaConteo], clave: Optional[str],
              costo: Optional[float], horas: Optional[float]) -> None:
    etiqueta = (clave or "").strip() or "Sin clasificar"
    fila = destino.setdefault(etiqueta, FilaConteo(etiqueta=etiqueta))
    fila.cantidad += 1
    fila.costo += float(costo or 0)
    fila.horas += float(horas or 0)


def _ordenar(destino: Dict[str, FilaConteo], tope: int = 15) -> List[FilaConteo]:
    return sorted(destino.values(), key=lambda f: (-f.cantidad, -f.costo))[:tope]


@router.get("/causa-raiz/analitica", response_model=AnaliticaCausas)
async def analitica(
    desde: Optional[date] = None, hasta: Optional[date] = None,
    marca: Optional[str] = None, linea: Optional[str] = None,
    tipo_activo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Las causas de falla agregadas por causa, modo, marca, linea y activo.

    Los filtros se encadenan: elegir una marca y luego una linea permite bajar
    de "que nos falla" a "que nos falla en esta flota", que es donde la
    respuesta sirve para decidir algo.
    """
    q = (select(EAMCausaRaiz, EAMActivo)
         .join(EAMActivo, EAMActivo.id == EAMCausaRaiz.activo_id, isouter=True))
    if desde:
        q = q.where(EAMCausaRaiz.fecha_analisis >= desde)
    if hasta:
        q = q.where(EAMCausaRaiz.fecha_analisis <= hasta)
    if marca:
        q = q.where(EAMActivo.marca == marca)
    if linea:
        q = q.where(EAMActivo.linea == linea)
    if tipo_activo:
        q = q.where(EAMActivo.tipo_activo == tipo_activo)

    filas = (await db.execute(q)).all()

    salida = AnaliticaCausas(total=len(filas))
    causas: Dict[str, FilaConteo] = {}
    modos: Dict[str, FilaConteo] = {}
    marcas: Dict[str, FilaConteo] = {}
    lineas: Dict[str, FilaConteo] = {}
    tipos: Dict[str, FilaConteo] = {}
    activos: Dict[str, FilaConteo] = {}

    for rca, activo in filas:
        costo, horas = rca.costo_estimado, rca.horas_parada
        salida.costo_total += float(costo or 0)
        salida.horas_total += float(horas or 0)
        if rca.estado == "CERRADO":
            salida.cerrados += 1
        _acumular(causas, rca.categoria_causa, costo, horas)
        _acumular(modos, rca.modo_falla, costo, horas)
        if activo:
            _acumular(marcas, activo.marca, costo, horas)
            # La linea se etiqueta con su marca: "Cascadia" sin mas no dice de
            # quien es, y dos marcas pueden tener lineas homonimas.
            etiqueta_linea = " ".join(
                x for x in [activo.marca, activo.linea] if x) or None
            _acumular(lineas, etiqueta_linea, costo, horas)
            _acumular(tipos, activo.tipo_activo, costo, horas)
            _acumular(activos, f"{activo.codigo} {activo.nombre}".strip(), costo, horas)

    salida.por_causa = _ordenar(causas)
    salida.por_modo_falla = _ordenar(modos)
    salida.por_marca = _ordenar(marcas)
    salida.por_linea = _ordenar(lineas)
    salida.por_tipo_activo = _ordenar(tipos)
    salida.por_activo = _ordenar(activos, 10)

    vencidas = await db.execute(
        select(func.count()).select_from(EAMCausaRaizAccion).where(
            EAMCausaRaizAccion.estado != "HECHA",
            EAMCausaRaizAccion.fecha_compromiso.isnot(None),
            EAMCausaRaizAccion.fecha_compromiso < date.today()))
    salida.acciones_vencidas = vencidas.scalar() or 0
    return salida


class ResumenRCA(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ot_id: int
    ot_numero: Optional[str] = None
    fecha_analisis: Optional[date] = None
    estado: str
    modo_falla: Optional[str] = None
    categoria_causa: Optional[str] = None
    causa_raiz: Optional[str] = None
    costo_estimado: Optional[float] = None
    horas_parada: Optional[float] = None
    activo: Optional[str] = None
    marca: Optional[str] = None
    linea: Optional[str] = None


@router.get("/causa-raiz", response_model=List[ResumenRCA])
async def listar(
    marca: Optional[str] = None, linea: Optional[str] = None,
    causa: Optional[str] = None, estado: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """El listado de analisis, para poder ir del grafico al caso concreto."""
    q = (select(EAMCausaRaiz, EAMActivo)
         .join(EAMActivo, EAMActivo.id == EAMCausaRaiz.activo_id, isouter=True)
         .order_by(EAMCausaRaiz.fecha_analisis.desc().nullslast(),
                   EAMCausaRaiz.id.desc()))
    if marca:
        q = q.where(EAMActivo.marca == marca)
    if linea:
        q = q.where(EAMActivo.linea == linea)
    if causa:
        q = q.where(EAMCausaRaiz.categoria_causa == causa)
    if estado:
        q = q.where(EAMCausaRaiz.estado == estado.upper())

    salida = []
    for rca, activo in (await db.execute(q.limit(500))).all():
        ficha = ResumenRCA.model_validate(rca)
        if activo:
            ficha.activo = f"{activo.codigo} — {activo.nombre}"
            ficha.marca, ficha.linea = activo.marca, activo.linea
        salida.append(ficha)
    return salida
