"""
LMS · lo que faltaba para que la plataforma de aprendizaje funcione.

Las quince pantallas del módulo eran maqueta, y el servidor (`lms.py`) sabía
listar y crear catálogos pero no permitía lo esencial de un LMS: TOMAR un
curso. Aquí está ese recorrido y lo que le faltaba al resto:

  1. Aprender: inscribirse, avanzar por los contenidos, presentar la
     evaluación —la califica el servidor, con intentos y tiempo límite— y, al
     terminar, recibir el certificado si el curso lo tiene.
  2. Administrar: editar y retirar lo que antes solo se creaba; módulos y
     contenidos de cada curso; preguntas con sus opciones en un solo paso.
  3. Medir: tablero, reportes, onboarding, ranking y recomendaciones
     calculados con los registros.

TRES DATOS QUE SE CALCULAN Y NO SE GUARDAN
  - El estado de un certificado (vigente, por vencer, vencido) sale de su
    fecha de vencimiento. Guardado, `lms.py` lo dejaba VIGENTE para siempre.
  - La brecha de una competencia es el nivel requerido menos el actual.
  - El avance de una inscripción son los contenidos completados sobre el
    total del curso.

LO QUE SE QUITÓ
Las «recomendaciones de IA» de `lms.py` daban 95 puntos a todo curso
obligatorio y 78 al resto, y la «predicción» del mes era lo completado más
doce. Las recomendaciones de aquí dicen por qué recomiendan cada curso
(obligatorio sin empezar, desarrolla una competencia con brecha para tu cargo)
y no inventan un puntaje.
"""
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Integer, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.lms import (
    LMSFacultad, LMSEscuela, LMSPrograma, LMSInstructor, LMSCompetencia, LMSCurso, LMSModulo,
    LMSContenido, LMSCursoCompetencia, LMSMatrizCompetencia, LMSRutaAprendizaje, LMSRutaCurso,
    LMSInscripcion, LMSProgreso, LMSEvaluacion, LMSPregunta, LMSOpcionRespuesta,
    LMSEvaluacionPregunta, LMSIntentoEvaluacion, LMSRespuesta, LMSCertificacion,
    LMSCertificadoUsuario, LMSInsignia, LMSInsigniaUsuario,
    ModalidadCursoEnum, NivelCursoEnum, EstadoCursoEnum, TipoProgramaEnum, EstadoInscripcionEnum,
    TipoEvaluacionEnum, TipoPreguntaEnum, NivelCompetenciaEnum, EstadoCertificacionEnum,
    TipoContenidoEnum, TipoInstructorEnum,
)

router = APIRouter(prefix="/lms", tags=["LMS"])

NIVELES = ["INICIAL", "BASICO", "INTERMEDIO", "AVANZADO", "EXPERTO"]
DIAS_POR_VENCER = 30
CALIFICABLES = (TipoPreguntaEnum.MULTIPLE, TipoPreguntaEnum.VERDADERO_FALSO)


def _v(x):
    return x.value if hasattr(x, "value") else x


def _ahora() -> datetime:
    # Las columnas de fecha de LMS son sin zona: se guarda la hora UTC sin zona.
    return datetime.utcnow()


async def _obtener(db: AsyncSession, model, id: int, nombre: str):
    obj = await db.get(model, id)
    if not obj:
        raise HTTPException(404, f"{nombre} no encontrado")
    return obj


async def _nombres(db: AsyncSession, ids) -> Dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    r = await db.execute(select(Usuario.id, Usuario.nombre, Usuario.apellido, Usuario.cargo).where(Usuario.id.in_(ids)))
    return {i: f"{n} {a}".strip() for i, n, a, _c in r.all()}


def _estado_certificado(c: LMSCertificadoUsuario) -> str:
    if _v(c.estado) == "CANCELADA":
        return "CANCELADA"
    if c.fecha_vencimiento is None:
        return "VIGENTE"
    ahora = _ahora()
    if c.fecha_vencimiento < ahora:
        return "VENCIDA"
    return "POR_VENCER" if c.fecha_vencimiento <= ahora + timedelta(days=DIAS_POR_VENCER) else "VIGENTE"


def _brecha(requerido, actual) -> int:
    r = NIVELES.index(_v(requerido)) if requerido else 0
    a = NIVELES.index(_v(actual)) if actual else 0
    return max(0, r - a)


async def _siguiente_codigo(db: AsyncSession, model, prefijo: str) -> str:
    """Consecutivo por el mayor sufijo usado, no por conteo: contar choca con
    el UNIQUE del código apenas se borra una fila."""
    anio = _ahora().year
    patron = f"{prefijo}-{anio}-"
    r = await db.execute(select(model.codigo).where(model.codigo.like(f"{patron}%")))
    maximo = max([int(c[len(patron):]) for (c,) in r.all() if c and c[len(patron):].isdigit()] or [0])
    return f"{patron}{maximo + 1:03d}"


# ═════════════════════════════════════════════════════════════════════════════
# 1. CURSOS: detalle, edición, módulos y contenidos
# ═════════════════════════════════════════════════════════════════════════════

class CursoIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    instructor_id: Optional[int] = None
    modalidad: ModalidadCursoEnum
    nivel: NivelCursoEnum
    duracion_horas: float = 0
    categoria: Optional[str] = None
    es_obligatorio: bool = False
    puntaje_aprobacion: int = 70
    estado: Optional[EstadoCursoEnum] = None


class ModuloIn(BaseModel):
    nombre: str
    orden: int = 0
    duracion_horas: float = 0


class ContenidoIn(BaseModel):
    modulo_id: int
    tipo: TipoContenidoEnum
    titulo: str
    descripcion: Optional[str] = None
    url: Optional[str] = None
    duracion_minutos: int = 0
    orden: int = 0


def _curso_base(c: LMSCurso) -> dict:
    return {
        "id": c.id, "codigo": c.codigo, "nombre": c.nombre, "descripcion": c.descripcion,
        "instructor_id": c.instructor_id, "modalidad": _v(c.modalidad), "nivel": _v(c.nivel),
        "estado": _v(c.estado), "duracion_horas": float(c.duracion_horas or 0), "categoria": c.categoria,
        "es_obligatorio": bool(c.es_obligatorio), "puntaje_aprobacion": c.puntaje_aprobacion,
    }


def _validar_curso(d: CursoIn):
    if not d.nombre.strip():
        raise HTTPException(422, "Falta el nombre del curso")
    if not 0 <= d.puntaje_aprobacion <= 100:
        raise HTTPException(422, "El puntaje de aprobación va de 0 a 100")
    if d.duracion_horas < 0:
        raise HTTPException(422, "La duración no puede ser negativa")


@router.get("/catalogo")
async def catalogo(db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    """Los cursos con instructor, inscritos, contenidos y si el usuario actual
    ya está inscrito. Todo en pocas consultas, no una por curso."""
    cursos = (await db.execute(select(LMSCurso).where(LMSCurso.estado != EstadoCursoEnum.ARCHIVADO)
                               .order_by(LMSCurso.nombre))).scalars().all()
    instr = dict((await db.execute(select(LMSInstructor.id, LMSInstructor.nombre))).all())
    inscritos = dict((await db.execute(select(LMSInscripcion.curso_id, func.count())
                                       .where(LMSInscripcion.curso_id.isnot(None)).group_by(LMSInscripcion.curso_id))).all())
    completados = dict((await db.execute(select(LMSInscripcion.curso_id, func.count())
                                         .where(LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO)
                                         .group_by(LMSInscripcion.curso_id))).all())
    contenidos = dict((await db.execute(select(LMSModulo.curso_id, func.count(LMSContenido.id))
                                        .join(LMSContenido, LMSContenido.modulo_id == LMSModulo.id)
                                        .group_by(LMSModulo.curso_id))).all())
    mias = dict((await db.execute(select(LMSInscripcion.curso_id, LMSInscripcion.estado)
                                  .where(LMSInscripcion.usuario_id == usuario.id))).all())
    return [{
        **_curso_base(c), "instructor": instr.get(c.instructor_id),
        "total_inscritos": inscritos.get(c.id, 0), "total_completados": completados.get(c.id, 0),
        "total_contenidos": contenidos.get(c.id, 0),
        "mi_estado": _v(mias[c.id]) if c.id in mias else None,
    } for c in cursos]


@router.get("/cursos/{curso_id}/detalle")
async def detalle_curso(curso_id: int, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    c = await _obtener(db, LMSCurso, curso_id, "Curso")
    modulos = (await db.execute(select(LMSModulo).where(LMSModulo.curso_id == c.id)
                                .order_by(LMSModulo.orden, LMSModulo.id))).scalars().all()
    conts = (await db.execute(select(LMSContenido).where(LMSContenido.modulo_id.in_([m.id for m in modulos] or [0]))
                              .order_by(LMSContenido.orden, LMSContenido.id))).scalars().all()
    insc = (await db.execute(select(LMSInscripcion).where(LMSInscripcion.usuario_id == usuario.id,
                                                          LMSInscripcion.curso_id == c.id))).scalars().first()
    hechos = set()
    if insc:
        hechos = set((await db.execute(select(LMSProgreso.contenido_id).where(
            LMSProgreso.inscripcion_id == insc.id, LMSProgreso.completado.is_(True)))).scalars().all())
    evals = (await db.execute(select(LMSEvaluacion).where(LMSEvaluacion.curso_id == c.id,
                                                          LMSEvaluacion.activo.is_(True)))).scalars().all()
    instr = await db.get(LMSInstructor, c.instructor_id) if c.instructor_id else None
    return {
        **_curso_base(c), "instructor": instr.nombre if instr else None,
        "modulos": [{
            "id": m.id, "nombre": m.nombre, "orden": m.orden, "duracion_horas": float(m.duracion_horas or 0),
            "contenidos": [{
                "id": x.id, "modulo_id": m.id, "tipo": _v(x.tipo), "titulo": x.titulo, "descripcion": x.descripcion,
                "url": x.url, "duracion_minutos": x.duracion_minutos, "orden": x.orden, "completado": x.id in hechos,
            } for x in conts if x.modulo_id == m.id],
        } for m in modulos],
        "evaluaciones": [{"id": e.id, "codigo": e.codigo, "nombre": e.nombre, "tipo": _v(e.tipo),
                          "intentos_maximos": e.intentos_maximos, "puntaje_aprobacion": e.puntaje_aprobacion,
                          "tiempo_limite_min": e.tiempo_limite_min} for e in evals],
        "inscripcion": _insc_dict(insc) if insc else None,
    }


@router.post("/cursos/nuevo", status_code=201)
async def crear_curso(d: CursoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_curso(d)
    if d.estado == EstadoCursoEnum.PUBLICADO:
        # Un curso recién creado no tiene contenidos todavía.
        raise HTTPException(400, "Un curso sin contenidos no se puede publicar")
    datos = d.model_dump(exclude={"estado"})
    c = LMSCurso(**datos, codigo=await _siguiente_codigo(db, LMSCurso, "CRS"), estado=d.estado or EstadoCursoEnum.BORRADOR)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _curso_base(c)


@router.put("/cursos/{curso_id}")
async def editar_curso(curso_id: int, d: CursoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_curso(d)
    c = await _obtener(db, LMSCurso, curso_id, "Curso")
    for k, v in d.model_dump().items():
        if k == "estado" and v is None:
            continue
        setattr(c, k, v)
    if _v(c.estado) == "PUBLICADO":
        await _exigir_contenido(db, c)
    await db.commit()
    return _curso_base(c)


async def _exigir_contenido(db: AsyncSession, c: LMSCurso):
    n = (await db.execute(select(func.count(LMSContenido.id)).join(LMSModulo, LMSModulo.id == LMSContenido.modulo_id)
                          .where(LMSModulo.curso_id == c.id))).scalar_one()
    if not n:
        raise HTTPException(400, "Un curso sin contenidos no se puede publicar")


@router.delete("/cursos/{curso_id}", status_code=204)
async def archivar_curso(curso_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Se archiva, no se borra: sus inscripciones y certificados siguen siendo historia."""
    c = await _obtener(db, LMSCurso, curso_id, "Curso")
    c.estado = EstadoCursoEnum.ARCHIVADO
    await db.commit()


@router.post("/cursos/{curso_id}/modulos", status_code=201)
async def crear_modulo(curso_id: int, d: ModuloIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    await _obtener(db, LMSCurso, curso_id, "Curso")
    if not d.nombre.strip():
        raise HTTPException(422, "Falta el nombre del módulo")
    m = LMSModulo(curso_id=curso_id, **d.model_dump())
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return {"id": m.id, "nombre": m.nombre, "orden": m.orden}


@router.put("/modulos/{modulo_id}")
async def editar_modulo(modulo_id: int, d: ModuloIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    m = await _obtener(db, LMSModulo, modulo_id, "Módulo")
    for k, v in d.model_dump().items():
        setattr(m, k, v)
    await db.commit()
    return {"id": m.id, "nombre": m.nombre, "orden": m.orden}


@router.delete("/modulos/{modulo_id}", status_code=204)
async def borrar_modulo(modulo_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    m = await _obtener(db, LMSModulo, modulo_id, "Módulo")
    ids = (await db.execute(select(LMSContenido.id).where(LMSContenido.modulo_id == m.id))).scalars().all()
    if ids and (await db.execute(select(func.count(LMSProgreso.id)).where(LMSProgreso.contenido_id.in_(ids)))).scalar_one():
        raise HTTPException(400, "El módulo tiene avance registrado de participantes; no se puede borrar")
    for i in ids:
        await db.delete(await db.get(LMSContenido, i))
    await db.delete(m)
    await db.commit()


def _validar_contenido(d: ContenidoIn):
    if not d.titulo.strip():
        raise HTTPException(422, "Falta el título")
    if d.duracion_minutos < 0:
        raise HTTPException(422, "La duración no puede ser negativa")
    if _v(d.tipo) in ("VIDEO", "DOCUMENTO", "PRESENTACION", "ENLACE", "SCORM") and not (d.url or "").strip():
        raise HTTPException(422, "Este tipo de contenido necesita el enlace al material")


@router.post("/contenidos", status_code=201)
async def crear_contenido(d: ContenidoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_contenido(d)
    await _obtener(db, LMSModulo, d.modulo_id, "Módulo")
    x = LMSContenido(**d.model_dump())
    db.add(x)
    await db.commit()
    await db.refresh(x)
    return {"id": x.id, "titulo": x.titulo}


@router.put("/contenidos/{contenido_id}")
async def editar_contenido(contenido_id: int, d: ContenidoIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_contenido(d)
    x = await _obtener(db, LMSContenido, contenido_id, "Contenido")
    for k, v in d.model_dump().items():
        setattr(x, k, v)
    await db.commit()
    return {"id": x.id, "titulo": x.titulo}


@router.delete("/contenidos/{contenido_id}", status_code=204)
async def borrar_contenido(contenido_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    x = await _obtener(db, LMSContenido, contenido_id, "Contenido")
    if (await db.execute(select(func.count(LMSProgreso.id)).where(LMSProgreso.contenido_id == x.id))).scalar_one():
        raise HTTPException(400, "El contenido tiene avance registrado; no se puede borrar")
    await db.delete(x)
    await db.commit()


# ═════════════════════════════════════════════════════════════════════════════
# 2. APRENDER: inscripción, avance, evaluación y certificado
# ═════════════════════════════════════════════════════════════════════════════

def _insc_dict(i: LMSInscripcion) -> dict:
    return {"id": i.id, "usuario_id": i.usuario_id, "curso_id": i.curso_id, "estado": _v(i.estado),
            "progreso_pct": float(i.progreso_pct or 0), "nota_final": float(i.nota_final) if i.nota_final is not None else None,
            "fecha_inicio": i.fecha_inicio.isoformat() if i.fecha_inicio else None,
            "fecha_fin": i.fecha_fin.isoformat() if i.fecha_fin else None}


async def _recalcular_inscripcion(db: AsyncSession, insc: LMSInscripcion) -> Optional[dict]:
    """Avance = contenidos completados / total. El curso se completa con todo
    el contenido visto y, si tiene evaluaciones activas, con todas aprobadas.
    Al completarse emite el certificado del curso, si lo tiene. Devuelve el
    certificado emitido, o None."""
    total = (await db.execute(select(func.count(LMSContenido.id)).join(LMSModulo, LMSModulo.id == LMSContenido.modulo_id)
                              .where(LMSModulo.curso_id == insc.curso_id))).scalar_one()
    hechos = (await db.execute(select(func.count(LMSProgreso.id)).where(
        LMSProgreso.inscripcion_id == insc.id, LMSProgreso.completado.is_(True)))).scalar_one()
    insc.progreso_pct = round(hechos * 100 / total, 2) if total else 0
    evals = (await db.execute(select(LMSEvaluacion.id).where(LMSEvaluacion.curso_id == insc.curso_id,
                                                             LMSEvaluacion.activo.is_(True)))).scalars().all()
    aprobadas = set((await db.execute(select(LMSIntentoEvaluacion.evaluacion_id).where(
        LMSIntentoEvaluacion.usuario_id == insc.usuario_id, LMSIntentoEvaluacion.aprobado.is_(True),
        LMSIntentoEvaluacion.evaluacion_id.in_(evals or [0])))).scalars().all())
    if evals:
        notas = (await db.execute(select(func.max(LMSIntentoEvaluacion.puntaje_obtenido)).where(
            LMSIntentoEvaluacion.usuario_id == insc.usuario_id, LMSIntentoEvaluacion.evaluacion_id.in_(evals))
            .group_by(LMSIntentoEvaluacion.evaluacion_id))).scalars().all()
        insc.nota_final = round(sum(float(n or 0) for n in notas) / len(evals), 2) if notas else None
    completo = total > 0 and hechos >= total and set(evals) <= aprobadas
    emitido = None
    if completo and _v(insc.estado) != "COMPLETADO":
        insc.estado = EstadoInscripcionEnum.COMPLETADO
        insc.fecha_fin = _ahora()
        emitido = await _emitir_si_corresponde(db, insc)
    elif not completo and _v(insc.estado) in ("INSCRITO", "PENDIENTE") and (hechos or aprobadas):
        insc.estado = EstadoInscripcionEnum.EN_PROGRESO
    return emitido


async def _emitir_si_corresponde(db: AsyncSession, insc: LMSInscripcion) -> Optional[dict]:
    cert = (await db.execute(select(LMSCertificacion).where(LMSCertificacion.curso_id == insc.curso_id,
                                                            LMSCertificacion.activo.is_(True)))).scalars().first()
    if not cert:
        return None
    previos = (await db.execute(select(LMSCertificadoUsuario).where(
        LMSCertificadoUsuario.certificacion_id == cert.id, LMSCertificadoUsuario.usuario_id == insc.usuario_id))).scalars().all()
    if any(_estado_certificado(p) in ("VIGENTE", "POR_VENCER") for p in previos):
        return None
    ahora = _ahora()
    n = (await db.execute(select(func.count(LMSCertificadoUsuario.id)))).scalar_one() + 1
    obj = LMSCertificadoUsuario(certificacion_id=cert.id, usuario_id=insc.usuario_id,
                                numero_certificado=f"CERT-{ahora.year}-{n:06d}", fecha_emision=ahora,
                                fecha_vencimiento=ahora + timedelta(days=30 * (cert.vigencia_meses or 12)),
                                estado=EstadoCertificacionEnum.VIGENTE)
    db.add(obj)
    await db.flush()
    return {"numero": obj.numero_certificado, "certificacion": cert.nombre,
            "vence": obj.fecha_vencimiento.date().isoformat()}


@router.post("/cursos/{curso_id}/inscribirme", status_code=201)
async def inscribirme(curso_id: int, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    c = await _obtener(db, LMSCurso, curso_id, "Curso")
    if _v(c.estado) != "PUBLICADO":
        raise HTTPException(400, "Solo se puede inscribir en cursos publicados")
    ya = (await db.execute(select(LMSInscripcion).where(LMSInscripcion.usuario_id == usuario.id,
                                                        LMSInscripcion.curso_id == c.id))).scalars().first()
    if ya:
        if _v(ya.estado) == "ABANDONADO":
            ya.estado = EstadoInscripcionEnum.EN_PROGRESO
            await db.commit()
        return _insc_dict(ya)
    i = LMSInscripcion(usuario_id=usuario.id, curso_id=c.id, estado=EstadoInscripcionEnum.INSCRITO,
                       fecha_inicio=_ahora(), progreso_pct=0)
    db.add(i)
    await db.commit()
    await db.refresh(i)
    return _insc_dict(i)


class InscripcionMasivaIn(BaseModel):
    curso_id: int
    usuario_ids: List[int]


@router.post("/inscripciones/masiva")
async def inscribir_varios(d: InscripcionMasivaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Inscribe a varias personas (por ejemplo, a un cargo en un obligatorio).
    Las que ya estaban inscritas se omiten."""
    c = await _obtener(db, LMSCurso, d.curso_id, "Curso")
    if _v(c.estado) != "PUBLICADO":
        raise HTTPException(400, "Solo se puede inscribir en cursos publicados")
    ya = set((await db.execute(select(LMSInscripcion.usuario_id).where(LMSInscripcion.curso_id == c.id))).scalars().all())
    nuevos = [u for u in dict.fromkeys(d.usuario_ids) if u not in ya]
    for u in nuevos:
        db.add(LMSInscripcion(usuario_id=u, curso_id=c.id, estado=EstadoInscripcionEnum.INSCRITO,
                              fecha_inicio=_ahora(), progreso_pct=0))
    await db.commit()
    return {"inscritos": len(nuevos), "ya_estaban": len(d.usuario_ids) - len(nuevos)}


@router.post("/contenidos/{contenido_id}/completar")
async def completar_contenido(contenido_id: int, minutos: int = Query(0, ge=0),
                              db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    x = await _obtener(db, LMSContenido, contenido_id, "Contenido")
    m = await db.get(LMSModulo, x.modulo_id)
    insc = (await db.execute(select(LMSInscripcion).where(LMSInscripcion.usuario_id == usuario.id,
                                                          LMSInscripcion.curso_id == m.curso_id))).scalars().first()
    if not insc:
        raise HTTPException(400, "Inscríbete en el curso para registrar tu avance")
    p = (await db.execute(select(LMSProgreso).where(LMSProgreso.inscripcion_id == insc.id,
                                                    LMSProgreso.contenido_id == x.id))).scalars().first()
    if not p:
        p = LMSProgreso(inscripcion_id=insc.id, contenido_id=x.id, tiempo_minutos=0)
        db.add(p)
    p.completado = True
    p.fecha_completado = p.fecha_completado or _ahora()
    p.tiempo_minutos = (p.tiempo_minutos or 0) + minutos
    await db.flush()
    emitido = await _recalcular_inscripcion(db, insc)
    await db.commit()
    return {"inscripcion": _insc_dict(insc), "certificado_emitido": emitido}


# ── Evaluaciones: iniciar un intento y entregarlo ──

@router.post("/evaluaciones/{evaluacion_id}/iniciar")
async def iniciar_evaluacion(evaluacion_id: int, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    """Abre un intento y devuelve las preguntas SIN la respuesta correcta.

    Solo entran las preguntas que se califican solas (opción múltiple y
    verdadero/falso): una respuesta abierta necesita a una persona, y
    calificarla en cero cambiaría la nota sin decir por qué.
    """
    e = await _obtener(db, LMSEvaluacion, evaluacion_id, "Evaluación")
    if not e.activo:
        raise HTTPException(400, "La evaluación no está activa")
    previos = (await db.execute(select(LMSIntentoEvaluacion).where(
        LMSIntentoEvaluacion.evaluacion_id == e.id, LMSIntentoEvaluacion.usuario_id == usuario.id))).scalars().all()
    if any(p.aprobado for p in previos):
        raise HTTPException(400, "Ya aprobaste esta evaluación")
    abierto = next((p for p in previos if p.fecha_fin is None), None)
    entregados = [p for p in previos if p.fecha_fin is not None]
    if not abierto and len(entregados) >= (e.intentos_maximos or 1):
        raise HTTPException(400, f"Agotaste los {e.intentos_maximos} intentos de esta evaluación")
    pregs = (await db.execute(select(LMSPregunta).join(LMSEvaluacionPregunta, LMSEvaluacionPregunta.pregunta_id == LMSPregunta.id)
                              .where(LMSEvaluacionPregunta.evaluacion_id == e.id, LMSPregunta.activo.is_(True),
                                     LMSPregunta.tipo.in_(CALIFICABLES))
                              .order_by(LMSEvaluacionPregunta.orden))).scalars().all()
    if not pregs:
        raise HTTPException(400, "La evaluación no tiene preguntas calificables asignadas")
    if not abierto:
        abierto = LMSIntentoEvaluacion(evaluacion_id=e.id, usuario_id=usuario.id,
                                       numero_intento=len(entregados) + 1, fecha_inicio=_ahora())
        db.add(abierto)
        await db.commit()
        await db.refresh(abierto)
    opciones = (await db.execute(select(LMSOpcionRespuesta).where(
        LMSOpcionRespuesta.pregunta_id.in_([p.id for p in pregs])).order_by(LMSOpcionRespuesta.orden))).scalars().all()
    pregs = list(pregs)
    if e.aleatorizar_preguntas:
        random.Random(abierto.id).shuffle(pregs)
    return {
        "intento_id": abierto.id, "numero_intento": abierto.numero_intento,
        "intentos_maximos": e.intentos_maximos, "tiempo_limite_min": e.tiempo_limite_min,
        "inicio": abierto.fecha_inicio.isoformat() + "Z", "puntaje_aprobacion": e.puntaje_aprobacion,
        "nombre": e.nombre,
        "preguntas": [{"id": p.id, "tipo": _v(p.tipo), "enunciado": p.enunciado, "puntaje": p.puntaje,
                       "opciones": [{"id": o.id, "texto": o.texto} for o in opciones if o.pregunta_id == p.id]}
                      for p in pregs],
    }


class RespuestaIn(BaseModel):
    pregunta_id: int
    opcion_id: Optional[int] = None


class EntregaIn(BaseModel):
    respuestas: List[RespuestaIn]


@router.post("/intentos/{intento_id}/entregar")
async def entregar_intento(intento_id: int, d: EntregaIn, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    """Califica en el servidor. La pantalla nunca recibe cuál es la correcta
    antes de entregar, así que la nota no se puede fabricar desde el navegador."""
    it = await _obtener(db, LMSIntentoEvaluacion, intento_id, "Intento")
    if it.usuario_id != usuario.id:
        raise HTTPException(403, "Este intento no es tuyo")
    if it.fecha_fin is not None:
        raise HTTPException(400, "Este intento ya fue entregado")
    e = await db.get(LMSEvaluacion, it.evaluacion_id)
    ahora = _ahora()
    minutos = (ahora - it.fecha_inicio).total_seconds() / 60 if it.fecha_inicio else 0
    # Un minuto de gracia por la latencia de la red.
    fuera_de_tiempo = bool(e.tiempo_limite_min and minutos > e.tiempo_limite_min + 1)
    pregs = (await db.execute(select(LMSPregunta).join(LMSEvaluacionPregunta, LMSEvaluacionPregunta.pregunta_id == LMSPregunta.id)
                              .where(LMSEvaluacionPregunta.evaluacion_id == e.id, LMSPregunta.activo.is_(True),
                                     LMSPregunta.tipo.in_(CALIFICABLES)))).scalars().all()
    correctas = dict((await db.execute(select(LMSOpcionRespuesta.id, LMSOpcionRespuesta.pregunta_id).where(
        LMSOpcionRespuesta.pregunta_id.in_([p.id for p in pregs] or [0]), LMSOpcionRespuesta.es_correcta.is_(True)))).all())
    dadas = {r.pregunta_id: r.opcion_id for r in d.respuestas}
    total = sum(p.puntaje or 1 for p in pregs)
    obtenido = 0
    detalle = []
    for p in pregs:
        op = dadas.get(p.id)
        bien = bool(op and correctas.get(op) == p.id) and not fuera_de_tiempo
        pts = (p.puntaje or 1) if bien else 0
        obtenido += pts
        db.add(LMSRespuesta(intento_id=it.id, pregunta_id=p.id, opcion_id=op, es_correcta=bien, puntaje_obtenido=pts))
        detalle.append({"pregunta_id": p.id, "correcta": bien})
    puntaje = round(obtenido * 100 / total, 2) if total else 0
    it.puntaje_obtenido = puntaje
    it.aprobado = puntaje >= (e.puntaje_aprobacion or 70)
    it.fecha_fin = ahora
    it.tiempo_utilizado_min = int(round(minutos))
    await db.flush()
    emitido = None
    if e.curso_id:
        insc = (await db.execute(select(LMSInscripcion).where(LMSInscripcion.usuario_id == usuario.id,
                                                              LMSInscripcion.curso_id == e.curso_id))).scalars().first()
        if insc:
            emitido = await _recalcular_inscripcion(db, insc)
    await db.commit()
    usados = (await db.execute(select(func.count(LMSIntentoEvaluacion.id)).where(
        LMSIntentoEvaluacion.evaluacion_id == e.id, LMSIntentoEvaluacion.usuario_id == usuario.id,
        LMSIntentoEvaluacion.fecha_fin.isnot(None)))).scalar_one()
    return {"puntaje": puntaje, "aprobado": it.aprobado, "puntaje_aprobacion": e.puntaje_aprobacion,
            "fuera_de_tiempo": fuera_de_tiempo, "intentos_restantes": max(0, (e.intentos_maximos or 1) - usados),
            "detalle": detalle, "certificado_emitido": emitido}


@router.get("/mi-aprendizaje")
async def mi_aprendizaje(db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    inscs = (await db.execute(select(LMSInscripcion, LMSCurso).join(LMSCurso, LMSCurso.id == LMSInscripcion.curso_id)
                              .where(LMSInscripcion.usuario_id == usuario.id)
                              .order_by(LMSInscripcion.updated_at.desc()))).all()
    certs = (await db.execute(select(LMSCertificadoUsuario, LMSCertificacion).join(
        LMSCertificacion, LMSCertificacion.id == LMSCertificadoUsuario.certificacion_id)
        .where(LMSCertificadoUsuario.usuario_id == usuario.id))).all()
    ins = (await db.execute(select(LMSInsignia, LMSInsigniaUsuario.fecha_obtenida).join(
        LMSInsigniaUsuario, LMSInsigniaUsuario.insignia_id == LMSInsignia.id)
        .where(LMSInsigniaUsuario.usuario_id == usuario.id))).all()
    horas = sum(float(c.duracion_horas or 0) for i, c in inscs if _v(i.estado) == "COMPLETADO")
    return {
        "usuario": {"id": usuario.id, "nombre": f"{usuario.nombre} {usuario.apellido}".strip(), "cargo": usuario.cargo},
        "cursos": [{**_insc_dict(i), "curso": c.nombre, "codigo": c.codigo, "modalidad": _v(c.modalidad),
                    "duracion_horas": float(c.duracion_horas or 0), "es_obligatorio": bool(c.es_obligatorio)} for i, c in inscs],
        "certificados": [{"id": cu.id, "numero": cu.numero_certificado, "certificacion": ce.nombre,
                          "emision": cu.fecha_emision.date().isoformat(),
                          "vence": cu.fecha_vencimiento.date().isoformat() if cu.fecha_vencimiento else None,
                          "estado": _estado_certificado(cu)} for cu, ce in certs],
        "insignias": [{"nombre": x.nombre, "icono": x.icono, "color": x.color, "puntos": x.puntos_otorgados,
                       "fecha": f.date().isoformat() if f else None} for x, f in ins],
        "puntos": sum(x.puntos_otorgados or 0 for x, _f in ins),
        "horas_completadas": round(horas, 2),
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3. CATÁLOGOS: editar y retirar lo que antes solo se creaba
# ═════════════════════════════════════════════════════════════════════════════

class FacultadIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    color: Optional[str] = None


class EscuelaIn(BaseModel):
    facultad_id: int
    nombre: str
    descripcion: Optional[str] = None


class ProgramaIn(BaseModel):
    escuela_id: int
    nombre: str
    descripcion: Optional[str] = None
    tipo: TipoProgramaEnum
    duracion_horas: int = 0


class InstructorIn(BaseModel):
    nombre: str
    email: Optional[str] = None
    especialidad: Optional[str] = None
    tipo: TipoInstructorEnum = TipoInstructorEnum.INTERNO


class CompetenciaIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None


class MatrizIn(BaseModel):
    cargo: str
    area: Optional[str] = None
    competencia_id: int
    nivel_requerido: NivelCompetenciaEnum
    nivel_actual: Optional[NivelCompetenciaEnum] = None


class RutaIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    cargo_objetivo: Optional[str] = None
    area_objetivo: Optional[str] = None
    curso_ids: List[int] = []


class EvaluacionIn(BaseModel):
    curso_id: Optional[int] = None
    nombre: str
    tipo: TipoEvaluacionEnum
    descripcion: Optional[str] = None
    tiempo_limite_min: Optional[int] = None
    intentos_maximos: int = 3
    puntaje_aprobacion: int = 70
    aleatorizar_preguntas: bool = True
    activo: bool = True
    pregunta_ids: List[int] = []


class OpcionIn(BaseModel):
    texto: str
    es_correcta: bool = False


class PreguntaIn(BaseModel):
    tipo: TipoPreguntaEnum
    enunciado: str
    nivel_dificultad: str = "MEDIO"
    categoria: Optional[str] = None
    puntaje: int = 1
    opciones: List[OpcionIn] = []


class CertificacionIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    curso_id: Optional[int] = None
    programa_id: Optional[int] = None
    vigencia_meses: int = 12
    entidad_emisora: Optional[str] = None


class InsigniaIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    tipo: Optional[str] = None
    criterio: Optional[str] = None
    puntos_otorgados: int = 0


def _simple(ruta: str, model, esquema, nombre: str, prefijo: Optional[str] = None, validar=None, activo=True):
    """GET lista, POST, PUT y DELETE (desactiva si el modelo tiene `activo`)."""
    async def crear(d: esquema, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):  # type: ignore
        if validar:
            validar(d)
        obj = model(**d.model_dump())
        if prefijo:
            obj.codigo = await _siguiente_codigo(db, model, prefijo)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return {c.name: _v(getattr(obj, c.name)) for c in model.__table__.columns}

    async def editar(id: int, d: esquema, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):  # type: ignore
        if validar:
            validar(d)
        obj = await _obtener(db, model, id, nombre)
        for k, v in d.model_dump().items():
            setattr(obj, k, v)
        await db.commit()
        await db.refresh(obj)
        return {c.name: _v(getattr(obj, c.name)) for c in model.__table__.columns}

    async def retirar(id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
        obj = await _obtener(db, model, id, nombre)
        if activo and hasattr(obj, "activo"):
            obj.activo = False
        else:
            await db.delete(obj)
        await db.commit()

    router.add_api_route(f"/admin/{ruta}", crear, methods=["POST"], status_code=201, name=f"crear_{ruta}")
    router.add_api_route(f"/admin/{ruta}/{{id}}", editar, methods=["PUT"], name=f"editar_{ruta}")
    router.add_api_route(f"/admin/{ruta}/{{id}}", retirar, methods=["DELETE"], status_code=204, name=f"retirar_{ruta}")


def _no_vacio(campo: str):
    def v(d):
        if not str(getattr(d, campo) or "").strip():
            raise HTTPException(422, f"Falta el campo {campo}")
    return v


_simple("facultades", LMSFacultad, FacultadIn, "Facultad", validar=_no_vacio("nombre"))
_simple("escuelas", LMSEscuela, EscuelaIn, "Escuela", validar=_no_vacio("nombre"))
_simple("programas", LMSPrograma, ProgramaIn, "Programa", prefijo="PRG", validar=_no_vacio("nombre"))
_simple("instructores", LMSInstructor, InstructorIn, "Instructor", validar=_no_vacio("nombre"))
_simple("competencias", LMSCompetencia, CompetenciaIn, "Competencia", prefijo="CMP", validar=_no_vacio("nombre"))


def _validar_cert(d: CertificacionIn):
    if not d.nombre.strip():
        raise HTTPException(422, "Falta el nombre")
    if d.vigencia_meses <= 0:
        raise HTTPException(422, "La vigencia debe ser de al menos un mes")


_simple("certificaciones", LMSCertificacion, CertificacionIn, "Certificación", prefijo="CRT", validar=_validar_cert)
_simple("insignias", LMSInsignia, InsigniaIn, "Insignia", validar=_no_vacio("nombre"))


# ── Matriz de competencias: la brecha se calcula ──

def _matriz_dict(m: LMSMatrizCompetencia, comp: Optional[str]) -> dict:
    return {"id": m.id, "cargo": m.cargo, "area": m.area, "competencia_id": m.competencia_id, "competencia": comp,
            "nivel_requerido": _v(m.nivel_requerido), "nivel_actual": _v(m.nivel_actual),
            "brecha": _brecha(m.nivel_requerido, m.nivel_actual)}


@router.get("/admin/matriz")
async def matriz(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    comps = dict((await db.execute(select(LMSCompetencia.id, LMSCompetencia.nombre))).all())
    filas = (await db.execute(select(LMSMatrizCompetencia).order_by(LMSMatrizCompetencia.cargo))).scalars().all()
    return [_matriz_dict(m, comps.get(m.competencia_id)) for m in filas]


async def _guardar_matriz(db: AsyncSession, m: LMSMatrizCompetencia, d: MatrizIn):
    if not d.cargo.strip():
        raise HTTPException(422, "Falta el cargo")
    await _obtener(db, LMSCompetencia, d.competencia_id, "Competencia")
    for k, v in d.model_dump().items():
        setattr(m, k, v)
    # Se guarda también porque el tablero de `lms.py` la cuenta en SQL; se
    # reescribe en cada guardado desde los dos niveles.
    m.brecha = _brecha(d.nivel_requerido, d.nivel_actual)


@router.post("/admin/matriz", status_code=201)
async def crear_matriz(d: MatrizIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    m = LMSMatrizCompetencia()
    await _guardar_matriz(db, m, d)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _matriz_dict(m, (await db.get(LMSCompetencia, m.competencia_id)).nombre)


@router.put("/admin/matriz/{id}")
async def editar_matriz(id: int, d: MatrizIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    m = await _obtener(db, LMSMatrizCompetencia, id, "Fila de la matriz")
    await _guardar_matriz(db, m, d)
    await db.commit()
    return _matriz_dict(m, (await db.get(LMSCompetencia, m.competencia_id)).nombre)


@router.delete("/admin/matriz/{id}", status_code=204)
async def borrar_matriz(id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    await db.delete(await _obtener(db, LMSMatrizCompetencia, id, "Fila de la matriz"))
    await db.commit()


# ── Competencias que desarrolla cada curso ──

class CursoCompetenciasIn(BaseModel):
    competencia_ids: List[int]


@router.put("/cursos/{curso_id}/competencias")
async def competencias_curso(curso_id: int, d: CursoCompetenciasIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    await _obtener(db, LMSCurso, curso_id, "Curso")
    for x in (await db.execute(select(LMSCursoCompetencia).where(LMSCursoCompetencia.curso_id == curso_id))).scalars().all():
        await db.delete(x)
    for cid in dict.fromkeys(d.competencia_ids):
        db.add(LMSCursoCompetencia(curso_id=curso_id, competencia_id=cid))
    await db.commit()
    return {"curso_id": curso_id, "competencia_ids": list(dict.fromkeys(d.competencia_ids))}


@router.get("/cursos/{curso_id}/competencias")
async def leer_competencias_curso(curso_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return (await db.execute(select(LMSCursoCompetencia.competencia_id).where(
        LMSCursoCompetencia.curso_id == curso_id))).scalars().all()


# ── Rutas con sus cursos en orden ──

async def _ruta_dict(db: AsyncSession, r: LMSRutaAprendizaje) -> dict:
    cursos = (await db.execute(select(LMSCurso, LMSRutaCurso.orden).join(LMSRutaCurso, LMSRutaCurso.curso_id == LMSCurso.id)
                               .where(LMSRutaCurso.ruta_id == r.id).order_by(LMSRutaCurso.orden))).all()
    return {"id": r.id, "codigo": r.codigo, "nombre": r.nombre, "descripcion": r.descripcion,
            "cargo_objetivo": r.cargo_objetivo, "area_objetivo": r.area_objetivo, "activo": r.activo,
            # La duración de la ruta es la suma de sus cursos: se calcula.
            "duracion_total_horas": round(sum(float(c.duracion_horas or 0) for c, _o in cursos), 2),
            "cursos": [{"id": c.id, "codigo": c.codigo, "nombre": c.nombre, "duracion_horas": float(c.duracion_horas or 0),
                        "estado": _v(c.estado)} for c, _o in cursos]}


@router.get("/admin/rutas")
async def rutas(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    rs = (await db.execute(select(LMSRutaAprendizaje).where(LMSRutaAprendizaje.activo.is_(True))
                           .order_by(LMSRutaAprendizaje.nombre))).scalars().all()
    return [await _ruta_dict(db, r) for r in rs]


async def _guardar_ruta(db: AsyncSession, r: LMSRutaAprendizaje, d: RutaIn):
    if not d.nombre.strip():
        raise HTTPException(422, "Falta el nombre")
    for k, v in d.model_dump(exclude={"curso_ids"}).items():
        setattr(r, k, v)
    await db.flush()
    for x in (await db.execute(select(LMSRutaCurso).where(LMSRutaCurso.ruta_id == r.id))).scalars().all():
        await db.delete(x)
    for orden, cid in enumerate(dict.fromkeys(d.curso_ids)):
        await _obtener(db, LMSCurso, cid, "Curso")
        db.add(LMSRutaCurso(ruta_id=r.id, curso_id=cid, orden=orden))
    cursos = (await db.execute(select(LMSCurso.duracion_horas).where(LMSCurso.id.in_(d.curso_ids or [0])))).scalars().all()
    r.duracion_total_horas = sum(float(h or 0) for h in cursos)


@router.post("/admin/rutas", status_code=201)
async def crear_ruta(d: RutaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    r = LMSRutaAprendizaje(codigo=await _siguiente_codigo(db, LMSRutaAprendizaje, "RUT"), activo=True)
    db.add(r)
    await _guardar_ruta(db, r, d)
    await db.commit()
    return await _ruta_dict(db, r)


@router.put("/admin/rutas/{id}")
async def editar_ruta(id: int, d: RutaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    r = await _obtener(db, LMSRutaAprendizaje, id, "Ruta")
    await _guardar_ruta(db, r, d)
    await db.commit()
    return await _ruta_dict(db, r)


@router.delete("/admin/rutas/{id}", status_code=204)
async def retirar_ruta(id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    r = await _obtener(db, LMSRutaAprendizaje, id, "Ruta")
    r.activo = False
    await db.commit()


# ── Banco de preguntas: la pregunta con sus opciones en un solo paso ──

def _validar_pregunta(d: PreguntaIn):
    if not d.enunciado.strip():
        raise HTTPException(422, "Falta el enunciado")
    if d.puntaje < 1:
        raise HTTPException(422, "El puntaje debe ser al menos 1")
    if d.tipo in CALIFICABLES:
        ops = [o for o in d.opciones if o.texto.strip()]
        if len(ops) < 2:
            raise HTTPException(422, "Una pregunta cerrada necesita al menos dos opciones")
        if sum(1 for o in ops if o.es_correcta) != 1:
            raise HTTPException(422, "Marca exactamente una opción correcta")


async def _pregunta_dict(db: AsyncSession, p: LMSPregunta) -> dict:
    ops = (await db.execute(select(LMSOpcionRespuesta).where(LMSOpcionRespuesta.pregunta_id == p.id)
                            .order_by(LMSOpcionRespuesta.orden))).scalars().all()
    usos = (await db.execute(select(func.count(LMSEvaluacionPregunta.id)).where(LMSEvaluacionPregunta.pregunta_id == p.id))).scalar_one()
    return {"id": p.id, "codigo": p.codigo, "tipo": _v(p.tipo), "enunciado": p.enunciado,
            "nivel_dificultad": p.nivel_dificultad, "categoria": p.categoria, "puntaje": p.puntaje, "activo": p.activo,
            "opciones": [{"id": o.id, "texto": o.texto, "es_correcta": o.es_correcta} for o in ops], "en_evaluaciones": usos}


@router.get("/admin/preguntas")
async def preguntas(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    ps = (await db.execute(select(LMSPregunta).where(LMSPregunta.activo.is_(True)).order_by(LMSPregunta.id.desc()))).scalars().all()
    return [await _pregunta_dict(db, p) for p in ps]


async def _guardar_opciones(db: AsyncSession, p: LMSPregunta, d: PreguntaIn):
    usadas = (await db.execute(select(func.count(LMSRespuesta.id)).where(LMSRespuesta.pregunta_id == p.id))).scalar_one()
    actuales = (await db.execute(select(LMSOpcionRespuesta).where(LMSOpcionRespuesta.pregunta_id == p.id))).scalars().all()
    if usadas and actuales:
        # Con respuestas registradas no se reemplazan las opciones: las
        # respuestas viejas quedarían apuntando a opciones que ya no existen.
        return
    for o in actuales:
        await db.delete(o)
    if d.tipo in CALIFICABLES:
        for i, o in enumerate([o for o in d.opciones if o.texto.strip()]):
            db.add(LMSOpcionRespuesta(pregunta_id=p.id, texto=o.texto.strip(), es_correcta=o.es_correcta, orden=i))


@router.post("/admin/preguntas", status_code=201)
async def crear_pregunta(d: PreguntaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_pregunta(d)
    p = LMSPregunta(**d.model_dump(exclude={"opciones"}), codigo=await _siguiente_codigo(db, LMSPregunta, "PRE"), activo=True)
    db.add(p)
    await db.flush()
    await _guardar_opciones(db, p, d)
    await db.commit()
    return await _pregunta_dict(db, p)


@router.put("/admin/preguntas/{id}")
async def editar_pregunta(id: int, d: PreguntaIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _validar_pregunta(d)
    p = await _obtener(db, LMSPregunta, id, "Pregunta")
    for k, v in d.model_dump(exclude={"opciones"}).items():
        setattr(p, k, v)
    await _guardar_opciones(db, p, d)
    await db.commit()
    return await _pregunta_dict(db, p)


@router.delete("/admin/preguntas/{id}", status_code=204)
async def retirar_pregunta(id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    p = await _obtener(db, LMSPregunta, id, "Pregunta")
    p.activo = False
    await db.commit()


# ── Evaluaciones con sus preguntas ──

async def _eval_dict(db: AsyncSession, e: LMSEvaluacion) -> dict:
    pids = (await db.execute(select(LMSEvaluacionPregunta.pregunta_id).where(LMSEvaluacionPregunta.evaluacion_id == e.id)
                             .order_by(LMSEvaluacionPregunta.orden))).scalars().all()
    ints = (await db.execute(select(func.count(LMSIntentoEvaluacion.id), func.avg(LMSIntentoEvaluacion.puntaje_obtenido),
                                    func.sum(func.cast(LMSIntentoEvaluacion.aprobado, Integer)))
                             .where(LMSIntentoEvaluacion.evaluacion_id == e.id, LMSIntentoEvaluacion.fecha_fin.isnot(None)))).one()
    curso = await db.get(LMSCurso, e.curso_id) if e.curso_id else None
    return {"id": e.id, "codigo": e.codigo, "curso_id": e.curso_id, "curso": curso.nombre if curso else None,
            "nombre": e.nombre, "tipo": _v(e.tipo), "descripcion": e.descripcion, "tiempo_limite_min": e.tiempo_limite_min,
            "intentos_maximos": e.intentos_maximos, "puntaje_aprobacion": e.puntaje_aprobacion,
            "aleatorizar_preguntas": e.aleatorizar_preguntas, "activo": e.activo, "pregunta_ids": pids,
            "intentos": ints[0] or 0, "promedio": round(float(ints[1]), 1) if ints[1] is not None else None,
            "aprobados": int(ints[2] or 0)}


@router.get("/admin/evaluaciones")
async def evaluaciones(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    es = (await db.execute(select(LMSEvaluacion).order_by(LMSEvaluacion.id.desc()))).scalars().all()
    return [await _eval_dict(db, e) for e in es]


async def _guardar_eval(db: AsyncSession, e: LMSEvaluacion, d: EvaluacionIn):
    if not d.nombre.strip():
        raise HTTPException(422, "Falta el nombre")
    if not 0 <= d.puntaje_aprobacion <= 100 or d.intentos_maximos < 1:
        raise HTTPException(422, "Aprobación de 0 a 100 y al menos un intento")
    if d.tiempo_limite_min is not None and d.tiempo_limite_min <= 0:
        raise HTTPException(422, "El tiempo límite debe ser mayor que cero")
    for k, v in d.model_dump(exclude={"pregunta_ids"}).items():
        setattr(e, k, v)
    await db.flush()
    for x in (await db.execute(select(LMSEvaluacionPregunta).where(LMSEvaluacionPregunta.evaluacion_id == e.id))).scalars().all():
        await db.delete(x)
    for orden, pid in enumerate(dict.fromkeys(d.pregunta_ids)):
        db.add(LMSEvaluacionPregunta(evaluacion_id=e.id, pregunta_id=pid, orden=orden))


@router.post("/admin/evaluaciones", status_code=201)
async def crear_eval(d: EvaluacionIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    e = LMSEvaluacion(codigo=await _siguiente_codigo(db, LMSEvaluacion, "EVA"))
    db.add(e)
    await _guardar_eval(db, e, d)
    await db.commit()
    return await _eval_dict(db, e)


@router.put("/admin/evaluaciones/{id}")
async def editar_eval(id: int, d: EvaluacionIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    e = await _obtener(db, LMSEvaluacion, id, "Evaluación")
    await _guardar_eval(db, e, d)
    await db.commit()
    return await _eval_dict(db, e)


@router.delete("/admin/evaluaciones/{id}", status_code=204)
async def retirar_eval(id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    e = await _obtener(db, LMSEvaluacion, id, "Evaluación")
    e.activo = False
    await db.commit()


# ── Certificados emitidos e insignias otorgadas ──

@router.get("/admin/certificados")
async def certificados(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    filas = (await db.execute(select(LMSCertificadoUsuario, LMSCertificacion).join(
        LMSCertificacion, LMSCertificacion.id == LMSCertificadoUsuario.certificacion_id)
        .order_by(LMSCertificadoUsuario.fecha_vencimiento))).all()
    nombres = await _nombres(db, [cu.usuario_id for cu, _c in filas])
    ahora = _ahora()
    return [{"id": cu.id, "numero": cu.numero_certificado, "certificacion_id": ce.id, "certificacion": ce.nombre,
             "usuario_id": cu.usuario_id, "usuario": nombres.get(cu.usuario_id, f"Usuario {cu.usuario_id}"),
             "emision": cu.fecha_emision.date().isoformat(),
             "vence": cu.fecha_vencimiento.date().isoformat() if cu.fecha_vencimiento else None,
             "dias_restantes": (cu.fecha_vencimiento - ahora).days if cu.fecha_vencimiento else None,
             "estado": _estado_certificado(cu)} for cu, ce in filas]


class OtorgarIn(BaseModel):
    usuario_id: int
    curso_id: Optional[int] = None


@router.post("/admin/insignias/{id}/otorgar", status_code=201)
async def otorgar(id: int, d: OtorgarIn, db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    ins = await _obtener(db, LMSInsignia, id, "Insignia")
    if (await db.execute(select(func.count(LMSInsigniaUsuario.id)).where(
            LMSInsigniaUsuario.insignia_id == ins.id, LMSInsigniaUsuario.usuario_id == d.usuario_id))).scalar_one():
        raise HTTPException(400, "Esa persona ya tiene esta insignia")
    await _obtener(db, Usuario, d.usuario_id, "Usuario")
    db.add(LMSInsigniaUsuario(insignia_id=ins.id, usuario_id=d.usuario_id, curso_id=d.curso_id, fecha_obtenida=_ahora()))
    await db.commit()
    return {"insignia": ins.nombre, "usuario_id": d.usuario_id}


# ═════════════════════════════════════════════════════════════════════════════
# 4. MEDIR: tablero, reportes, onboarding, ranking, biblioteca, recomendaciones
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/tablero")
async def tablero(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    inscs = (await db.execute(select(LMSInscripcion.estado, func.count()).group_by(LMSInscripcion.estado))).all()
    por = {_v(e): n for e, n in inscs}
    total = sum(por.values())
    certs = (await db.execute(select(LMSCertificadoUsuario))).scalars().all()
    est = [_estado_certificado(c) for c in certs]
    matriz_ = (await db.execute(select(LMSMatrizCompetencia))).scalars().all()
    horas = (await db.execute(select(func.coalesce(func.sum(LMSCurso.duracion_horas), 0)).join(
        LMSInscripcion, LMSInscripcion.curso_id == LMSCurso.id).where(LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO))).scalar_one()
    return {
        "cursos_publicados": (await db.execute(select(func.count(LMSCurso.id)).where(LMSCurso.estado == EstadoCursoEnum.PUBLICADO))).scalar_one(),
        "inscripciones": total,
        "en_progreso": por.get("EN_PROGRESO", 0) + por.get("INSCRITO", 0),
        "completados": por.get("COMPLETADO", 0),
        # Sobre las inscripciones que ya terminaron de algún modo o siguen: no
        # se infla con el 1 artificial que usaba `lms.py` cuando no había datos.
        "tasa_finalizacion": round(por.get("COMPLETADO", 0) * 100 / total, 1) if total else None,
        "certificados_vigentes": est.count("VIGENTE"),
        "certificados_por_vencer": est.count("POR_VENCER"),
        "certificados_vencidos": est.count("VENCIDA"),
        "brechas": sum(1 for m in matriz_ if _brecha(m.nivel_requerido, m.nivel_actual) > 0),
        "horas_completadas": round(float(horas or 0), 1),
        "banco_preguntas": (await db.execute(select(func.count(LMSPregunta.id)).where(LMSPregunta.activo.is_(True)))).scalar_one(),
    }


@router.get("/reportes/resumen")
async def reportes(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Top de cursos, horas por mes y cumplimiento de obligatorios por cargo."""
    cursos = (await db.execute(select(LMSCurso).where(LMSCurso.estado != EstadoCursoEnum.ARCHIVADO))).scalars().all()
    inscs = (await db.execute(select(LMSInscripcion).where(LMSInscripcion.curso_id.isnot(None)))).scalars().all()
    por_curso: Dict[int, list] = {}
    for i in inscs:
        por_curso.setdefault(i.curso_id, []).append(i)
    top = sorted([{
        "curso": c.nombre, "codigo": c.codigo, "inscritos": len(por_curso.get(c.id, [])),
        "completados": sum(1 for i in por_curso.get(c.id, []) if _v(i.estado) == "COMPLETADO"),
        "nota_promedio": (lambda ns: round(sum(ns) / len(ns), 1) if ns else None)(
            [float(i.nota_final) for i in por_curso.get(c.id, []) if i.nota_final is not None]),
    } for c in cursos], key=lambda x: -x["inscritos"])[:10]
    for t in top:
        t["tasa"] = round(t["completados"] * 100 / t["inscritos"], 1) if t["inscritos"] else None

    duracion = {c.id: float(c.duracion_horas or 0) for c in cursos}
    horas_mes: Dict[str, float] = {}
    for i in inscs:
        if _v(i.estado) == "COMPLETADO" and i.fecha_fin:
            k = i.fecha_fin.strftime("%Y-%m")
            horas_mes[k] = horas_mes.get(k, 0) + duracion.get(i.curso_id, 0)

    # Obligatorios por cargo: de las personas de cada cargo, cuántas
    # completaron cada curso obligatorio.
    obligatorios = [c for c in cursos if c.es_obligatorio and _v(c.estado) == "PUBLICADO"]
    usuarios = (await db.execute(select(Usuario.id, Usuario.cargo).where(Usuario.activo.is_(True)))).all()
    por_cargo: Dict[str, List[int]] = {}
    for uid, cargo in usuarios:
        por_cargo.setdefault((cargo or "Sin cargo").strip() or "Sin cargo", []).append(uid)
    hecho = {(i.usuario_id, i.curso_id) for i in inscs if _v(i.estado) == "COMPLETADO"}
    cumplimiento = [{
        "cargo": cargo, "personas": len(uids),
        "cursos": [{"curso": c.nombre, "completaron": sum(1 for u in uids if (u, c.id) in hecho)} for c in obligatorios],
    } for cargo, uids in sorted(por_cargo.items())]
    return {"top_cursos": top, "horas_por_mes": [{"mes": k, "horas": round(v, 1)} for k, v in sorted(horas_mes.items())],
            "obligatorios": [c.nombre for c in obligatorios], "cumplimiento_por_cargo": cumplimiento}


@router.get("/onboarding/avance")
async def onboarding(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Cada persona frente a los cursos obligatorios: cuáles completó, cuáles
    lleva y cuáles no ha empezado."""
    obligatorios = (await db.execute(select(LMSCurso).where(LMSCurso.es_obligatorio.is_(True),
                                                            LMSCurso.estado == EstadoCursoEnum.PUBLICADO))).scalars().all()
    ids = [c.id for c in obligatorios]
    inscs = (await db.execute(select(LMSInscripcion).where(LMSInscripcion.curso_id.in_(ids or [0])))).scalars().all()
    usuarios = (await db.execute(select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.created_at.desc()))).scalars().all()
    salida = []
    for u in usuarios:
        mias = {i.curso_id: i for i in inscs if i.usuario_id == u.id}
        comp = sum(1 for c in ids if c in mias and _v(mias[c].estado) == "COMPLETADO")
        salida.append({
            "usuario_id": u.id, "nombre": f"{u.nombre} {u.apellido}".strip(), "cargo": u.cargo,
            "ingreso": u.created_at.date().isoformat() if u.created_at else None,
            "completados": comp, "total": len(ids),
            "avance_pct": round(comp * 100 / len(ids), 1) if ids else None,
            "cursos": [{"curso_id": c.id, "curso": c.nombre,
                        "estado": _v(mias[c.id].estado) if c.id in mias else "SIN_INSCRIBIR",
                        "progreso_pct": float(mias[c.id].progreso_pct or 0) if c.id in mias else 0} for c in obligatorios],
        })
    return {"obligatorios": [{"id": c.id, "nombre": c.nombre, "duracion_horas": float(c.duracion_horas or 0)} for c in obligatorios],
            "personas": salida}


@router.get("/ranking")
async def ranking(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Puntos de las insignias, con los cursos completados como desempate."""
    pts = dict((await db.execute(select(LMSInsigniaUsuario.usuario_id, func.sum(LMSInsignia.puntos_otorgados))
                                 .join(LMSInsignia, LMSInsignia.id == LMSInsigniaUsuario.insignia_id)
                                 .group_by(LMSInsigniaUsuario.usuario_id))).all())
    nins = dict((await db.execute(select(LMSInsigniaUsuario.usuario_id, func.count())
                                  .group_by(LMSInsigniaUsuario.usuario_id))).all())
    comp = dict((await db.execute(select(LMSInscripcion.usuario_id, func.count()).where(
        LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO).group_by(LMSInscripcion.usuario_id))).all())
    ids = set(pts) | set(comp)
    nombres = await _nombres(db, ids)
    filas = sorted([{"usuario_id": u, "nombre": nombres.get(u, f"Usuario {u}"), "puntos": int(pts.get(u) or 0),
                     "insignias": int(nins.get(u) or 0), "cursos_completados": int(comp.get(u) or 0)} for u in ids],
                   key=lambda x: (-x["puntos"], -x["cursos_completados"]))
    for i, f in enumerate(filas):
        f["posicion"] = i + 1
    return filas


@router.get("/biblioteca")
async def biblioteca(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Todos los contenidos de los cursos publicados, para buscarlos sin
    entrar curso por curso."""
    filas = (await db.execute(select(LMSContenido, LMSModulo, LMSCurso)
                              .join(LMSModulo, LMSModulo.id == LMSContenido.modulo_id)
                              .join(LMSCurso, LMSCurso.id == LMSModulo.curso_id)
                              .where(LMSCurso.estado == EstadoCursoEnum.PUBLICADO)
                              .order_by(LMSCurso.nombre, LMSModulo.orden, LMSContenido.orden))).all()
    return [{"id": x.id, "tipo": _v(x.tipo), "titulo": x.titulo, "descripcion": x.descripcion, "url": x.url,
             "duracion_minutos": x.duracion_minutos, "modulo": m.nombre, "curso_id": c.id, "curso": c.nombre,
             "categoria": c.categoria} for x, m, c in filas]


@router.get("/recomendaciones")
async def recomendaciones(usuario_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
                          usuario: Usuario = Depends(get_current_user)):
    """Qué cursos le convienen a una persona y POR QUÉ, con reglas explícitas:

      1. Obligatorios que no ha completado.
      2. Cursos que desarrollan una competencia en la que su cargo tiene
         brecha en la matriz.
      3. Cursos de las rutas pensadas para su cargo.
    """
    u = await _obtener(db, Usuario, usuario_id, "Usuario") if usuario_id else usuario
    cursos = {c.id: c for c in (await db.execute(select(LMSCurso).where(LMSCurso.estado == EstadoCursoEnum.PUBLICADO))).scalars().all()}
    hechos = set((await db.execute(select(LMSInscripcion.curso_id).where(
        LMSInscripcion.usuario_id == u.id, LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO))).scalars().all())
    razones: Dict[int, List[str]] = {}
    for c in cursos.values():
        if c.es_obligatorio and c.id not in hechos:
            razones.setdefault(c.id, []).append("Obligatorio y aún no lo completas")
    if u.cargo:
        brechas = (await db.execute(select(LMSMatrizCompetencia, LMSCompetencia.nombre)
                                    .join(LMSCompetencia, LMSCompetencia.id == LMSMatrizCompetencia.competencia_id)
                                    .where(func.lower(LMSMatrizCompetencia.cargo) == u.cargo.strip().lower()))).all()
        con_brecha = {m.competencia_id: n for m, n in brechas if _brecha(m.nivel_requerido, m.nivel_actual) > 0}
        for cc in (await db.execute(select(LMSCursoCompetencia).where(
                LMSCursoCompetencia.competencia_id.in_(list(con_brecha) or [0])))).scalars().all():
            if cc.curso_id in cursos and cc.curso_id not in hechos:
                razones.setdefault(cc.curso_id, []).append(f"Desarrolla «{con_brecha[cc.competencia_id]}», con brecha en tu cargo")
        rutas_ = (await db.execute(select(LMSRutaCurso.curso_id, LMSRutaAprendizaje.nombre)
                                   .join(LMSRutaAprendizaje, LMSRutaAprendizaje.id == LMSRutaCurso.ruta_id)
                                   .where(LMSRutaAprendizaje.activo.is_(True),
                                          func.lower(LMSRutaAprendizaje.cargo_objetivo) == u.cargo.strip().lower()))).all()
        for cid, nombre in rutas_:
            if cid in cursos and cid not in hechos:
                razones.setdefault(cid, []).append(f"Parte de la ruta «{nombre}» para tu cargo")
    return {"usuario": {"id": u.id, "nombre": f"{u.nombre} {u.apellido}".strip(), "cargo": u.cargo},
            "cursos": sorted([{**_curso_base(cursos[cid]), "razones": rz} for cid, rz in razones.items()],
                             key=lambda x: (-len(x["razones"]), not x["es_obligatorio"]))}


@router.get("/usuarios")
async def usuarios_lms(db: AsyncSession = Depends(get_db), _: Usuario = Depends(get_current_user)):
    """Personas para inscribir u otorgar insignias, con su cargo."""
    us = (await db.execute(select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre))).scalars().all()
    return [{"id": u.id, "nombre": f"{u.nombre} {u.apellido}".strip(), "cargo": u.cargo} for u in us]
