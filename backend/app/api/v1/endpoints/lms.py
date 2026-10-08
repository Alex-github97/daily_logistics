from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime, date, timedelta
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from app.core.database import get_db
from app.infrastructure.models.lms import (
    LMSFacultad, LMSEscuela, LMSPrograma, LMSInstructor,
    LMSCurso, LMSModulo, LMSContenido,
    LMSCompetencia, LMSCursoCompetencia, LMSMatrizCompetencia,
    LMSRutaAprendizaje, LMSRutaCurso, LMSProgramaCurso,
    LMSInscripcion, LMSProgreso,
    LMSEvaluacion, LMSPregunta, LMSOpcionRespuesta,
    LMSEvaluacionPregunta, LMSIntentoEvaluacion, LMSRespuesta,
    LMSCertificacion, LMSCertificadoUsuario,
    LMSInsignia, LMSInsigniaUsuario,
    LMSForo, LMSHiloForo, LMSComentario,
    LMSKPIDiario,
    ModalidadCursoEnum, NivelCursoEnum, EstadoCursoEnum,
    TipoProgramaEnum, EstadoInscripcionEnum, TipoEvaluacionEnum,
    TipoPreguntaEnum, NivelCompetenciaEnum, EstadoCertificacionEnum,
    TipoContenidoEnum, TipoInstructorEnum,
)

router = APIRouter(prefix="/lms", tags=["LMS"])

# ─── Schemas ────────────────────────────────────────────────────────────────

class FacultadCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    color: Optional[str] = "#D97706"
    icono: Optional[str] = "School"

class EscuelaCreate(BaseModel):
    facultad_id: int
    nombre: str
    descripcion: Optional[str] = None

class ProgramaCreate(BaseModel):
    escuela_id: int
    nombre: str
    descripcion: Optional[str] = None
    tipo: TipoProgramaEnum
    duracion_horas: int = 0

class InstructorCreate(BaseModel):
    nombre: str
    email: Optional[str] = None
    especialidad: Optional[str] = None
    tipo: TipoInstructorEnum = TipoInstructorEnum.INTERNO

class CursoCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    instructor_id: Optional[int] = None
    modalidad: ModalidadCursoEnum
    nivel: NivelCursoEnum
    duracion_horas: float = 0
    categoria: Optional[str] = None
    es_obligatorio: bool = False
    puntaje_aprobacion: int = 70

class CompetenciaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None

class MatrizCompetenciaCreate(BaseModel):
    cargo: str
    area: Optional[str] = None
    competencia_id: int
    nivel_requerido: NivelCompetenciaEnum
    nivel_actual: Optional[NivelCompetenciaEnum] = None

class RutaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    cargo_objetivo: Optional[str] = None
    area_objetivo: Optional[str] = None

class InscripcionCreate(BaseModel):
    usuario_id: int
    curso_id: Optional[int] = None
    ruta_id: Optional[int] = None

class EvaluacionCreate(BaseModel):
    curso_id: Optional[int] = None
    nombre: str
    tipo: TipoEvaluacionEnum
    descripcion: Optional[str] = None
    tiempo_limite_min: Optional[int] = None
    intentos_maximos: int = 3
    puntaje_aprobacion: int = 70

class PreguntaCreate(BaseModel):
    tipo: TipoPreguntaEnum
    enunciado: str
    nivel_dificultad: str = "MEDIO"
    categoria: Optional[str] = None
    puntaje: int = 1

class OpcionCreate(BaseModel):
    pregunta_id: int
    texto: str
    es_correcta: bool = False
    orden: int = 0

class CertificacionCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    curso_id: Optional[int] = None
    programa_id: Optional[int] = None
    vigencia_meses: int = 12
    entidad_emisora: Optional[str] = None

class CertificadoCreate(BaseModel):
    certificacion_id: int
    usuario_id: int
    fecha_emision: datetime
    fecha_vencimiento: Optional[datetime] = None

class InsigniaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    tipo: Optional[str] = None
    criterio: Optional[str] = None
    puntos_otorgados: int = 0

class ForoCreate(BaseModel):
    curso_id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = None

class HiloCreate(BaseModel):
    foro_id: int
    usuario_id: int
    titulo: str
    contenido: str

class ComentarioCreate(BaseModel):
    hilo_id: int
    usuario_id: int
    contenido: str

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _next_code(prefix: str, year: int, seq: int) -> str:
    return f"{prefix}-{year}-{seq:03d}"

async def _get_next_seq(db: AsyncSession, model, prefix_field, prefix: str) -> str:
    year = datetime.utcnow().year
    result = await db.execute(
        select(func.count()).where(
            and_(
                getattr(model, prefix_field).like(f"{prefix}-{year}-%"),
            )
        )
    )
    count = result.scalar() or 0
    return _next_code(prefix, year, count + 1)

# ─── Dashboard ───────────────────────────────────────────────────────────────

@router.get("/dashboard/kpis")
async def lms_kpis(db: AsyncSession = Depends(get_db)):
    cursos_q       = await db.execute(select(func.count()).where(LMSCurso.estado == EstadoCursoEnum.PUBLICADO))
    insc_q         = await db.execute(select(func.count()).where(LMSInscripcion.estado == EstadoInscripcionEnum.EN_PROGRESO))
    completados_q  = await db.execute(select(func.count()).where(LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO))
    total_insc_q   = await db.execute(select(func.count()).select_from(LMSInscripcion))
    certs_vigentes = await db.execute(select(func.count()).where(LMSCertificadoUsuario.estado == EstadoCertificacionEnum.VIGENTE))
    certs_venc_q   = await db.execute(select(func.count()).where(LMSCertificadoUsuario.estado == EstadoCertificacionEnum.VENCIDA))
    por_vencer_q   = await db.execute(select(func.count()).where(LMSCertificadoUsuario.estado == EstadoCertificacionEnum.POR_VENCER))
    brechas_q      = await db.execute(select(func.count()).where(LMSMatrizCompetencia.brecha > 0))
    instructores_q = await db.execute(select(func.count()).where(LMSInstructor.activo == True))
    preguntas_q    = await db.execute(select(func.count()).where(LMSPregunta.activo == True))

    total_insc  = total_insc_q.scalar() or 1
    completados = completados_q.scalar() or 0
    tasa        = round((completados / total_insc) * 100, 1)

    return {
        "cursos_publicados":      cursos_q.scalar() or 0,
        "inscripciones_activas":  insc_q.scalar() or 0,
        "completados":            completados,
        "tasa_finalizacion":      tasa,
        "certificados_vigentes":  certs_vigentes.scalar() or 0,
        "certificados_vencidos":  certs_venc_q.scalar() or 0,
        "certificados_por_vencer": por_vencer_q.scalar() or 0,
        "brechas_competencias":   brechas_q.scalar() or 0,
        "instructores_activos":   instructores_q.scalar() or 0,
        "banco_preguntas":        preguntas_q.scalar() or 0,
    }

@router.get("/dashboard/actividad-reciente")
async def lms_actividad_reciente(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LMSInscripcion).order_by(LMSInscripcion.created_at.desc()).limit(10)
    )
    items = result.scalars().all()
    return [
        {
            "id": i.id,
            "usuario_id": i.usuario_id,
            "curso_id": i.curso_id,
            "estado": i.estado,
            "progreso_pct": float(i.progreso_pct or 0),
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ]

# ─── Facultades ──────────────────────────────────────────────────────────────

@router.get("/facultades")
async def list_facultades(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSFacultad).where(LMSFacultad.activo == True).order_by(LMSFacultad.nombre))
    facs = result.scalars().all()
    data = []
    for f in facs:
        esc_q = await db.execute(select(func.count()).where(LMSEscuela.facultad_id == f.id))
        data.append({
            "id": f.id, "nombre": f.nombre, "descripcion": f.descripcion,
            "color": f.color, "icono": f.icono,
            "total_escuelas": esc_q.scalar() or 0,
        })
    return data

@router.post("/facultades")
async def create_facultad(body: FacultadCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSFacultad(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "nombre": obj.nombre}

# ─── Escuelas ────────────────────────────────────────────────────────────────

@router.get("/escuelas")
async def list_escuelas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSEscuela).where(LMSEscuela.activo == True).order_by(LMSEscuela.nombre))
    items = result.scalars().all()
    data = []
    for e in items:
        fac = await db.get(LMSFacultad, e.facultad_id)
        prog_q = await db.execute(select(func.count()).where(LMSPrograma.escuela_id == e.id))
        data.append({
            "id": e.id, "nombre": e.nombre, "descripcion": e.descripcion,
            "facultad_id": e.facultad_id,
            "facultad_nombre": fac.nombre if fac else None,
            "total_programas": prog_q.scalar() or 0,
        })
    return data

@router.post("/escuelas")
async def create_escuela(body: EscuelaCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSEscuela(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "nombre": obj.nombre}

# ─── Programas ───────────────────────────────────────────────────────────────

@router.get("/programas")
async def list_programas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSPrograma).where(LMSPrograma.activo == True).order_by(LMSPrograma.nombre))
    items = result.scalars().all()
    data = []
    for p in items:
        esc = await db.get(LMSEscuela, p.escuela_id)
        c_q = await db.execute(select(func.count()).where(LMSProgramaCurso.programa_id == p.id))
        data.append({
            "id": p.id, "codigo": p.codigo, "nombre": p.nombre,
            "descripcion": p.descripcion, "tipo": p.tipo,
            "duracion_horas": p.duracion_horas,
            "escuela_id": p.escuela_id, "escuela_nombre": esc.nombre if esc else None,
            "total_cursos": c_q.scalar() or 0,
        })
    return data

@router.post("/programas")
async def create_programa(body: ProgramaCreate, db: AsyncSession = Depends(get_db)):
    year = datetime.utcnow().year
    seq_q = await db.execute(select(func.count()).select_from(LMSPrograma))
    seq = (seq_q.scalar() or 0) + 1
    obj = LMSPrograma(**body.model_dump(), codigo=f"PRG-{year}-{seq:03d}")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "codigo": obj.codigo, "nombre": obj.nombre}

# ─── Instructores ────────────────────────────────────────────────────────────

@router.get("/instructores")
async def list_instructores(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSInstructor).where(LMSInstructor.activo == True).order_by(LMSInstructor.nombre))
    items = result.scalars().all()
    data = []
    for i in items:
        c_q = await db.execute(select(func.count()).where(LMSCurso.instructor_id == i.id))
        data.append({
            "id": i.id, "nombre": i.nombre, "email": i.email,
            "especialidad": i.especialidad, "tipo": i.tipo,
            "total_cursos": c_q.scalar() or 0,
        })
    return data

@router.post("/instructores")
async def create_instructor(body: InstructorCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSInstructor(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "nombre": obj.nombre}

# ─── Cursos ──────────────────────────────────────────────────────────────────

@router.get("/cursos")
async def list_cursos(
    modalidad: Optional[str] = None,
    nivel: Optional[str] = None,
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(LMSCurso)
    filters = []
    if modalidad:
        filters.append(LMSCurso.modalidad == modalidad)
    if nivel:
        filters.append(LMSCurso.nivel == nivel)
    if estado:
        filters.append(LMSCurso.estado == estado)
    if categoria:
        filters.append(LMSCurso.categoria == categoria)
    if filters:
        q = q.where(and_(*filters))
    q = q.order_by(LMSCurso.nombre)
    result = await db.execute(q)
    items = result.scalars().all()
    data = []
    for c in items:
        instr = await db.get(LMSInstructor, c.instructor_id) if c.instructor_id else None
        insc_q = await db.execute(select(func.count()).where(LMSInscripcion.curso_id == c.id))
        data.append({
            "id": c.id, "codigo": c.codigo, "nombre": c.nombre,
            "descripcion": c.descripcion, "modalidad": c.modalidad,
            "nivel": c.nivel, "estado": c.estado,
            "duracion_horas": float(c.duracion_horas or 0),
            "categoria": c.categoria, "es_obligatorio": c.es_obligatorio,
            "puntaje_aprobacion": c.puntaje_aprobacion,
            "instructor": instr.nombre if instr else None,
            "total_inscritos": insc_q.scalar() or 0,
        })
    return data

@router.post("/cursos")
async def create_curso(body: CursoCreate, db: AsyncSession = Depends(get_db)):
    year = datetime.utcnow().year
    seq_q = await db.execute(select(func.count()).select_from(LMSCurso))
    seq = (seq_q.scalar() or 0) + 1
    obj = LMSCurso(**body.model_dump(), codigo=f"CRS-{year}-{seq:03d}", estado=EstadoCursoEnum.BORRADOR)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "codigo": obj.codigo, "nombre": obj.nombre}

@router.put("/cursos/{curso_id}/publicar")
async def publicar_curso(curso_id: int, db: AsyncSession = Depends(get_db)):
    curso = await db.get(LMSCurso, curso_id)
    if not curso:
        raise HTTPException(404, "Curso no encontrado")
    curso.estado = EstadoCursoEnum.PUBLICADO
    await db.commit()
    return {"ok": True}

# ─── Competencias ────────────────────────────────────────────────────────────

@router.get("/competencias")
async def list_competencias(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSCompetencia).where(LMSCompetencia.activo == True).order_by(LMSCompetencia.nombre))
    items = result.scalars().all()
    return [
        {"id": c.id, "codigo": c.codigo, "nombre": c.nombre,
         "descripcion": c.descripcion, "categoria": c.categoria}
        for c in items
    ]

@router.post("/competencias")
async def create_competencia(body: CompetenciaCreate, db: AsyncSession = Depends(get_db)):
    year = datetime.utcnow().year
    seq_q = await db.execute(select(func.count()).select_from(LMSCompetencia))
    seq = (seq_q.scalar() or 0) + 1
    obj = LMSCompetencia(**body.model_dump(), codigo=f"COMP-{year}-{seq:03d}")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "codigo": obj.codigo, "nombre": obj.nombre}

# ─── Matriz de Competencias ──────────────────────────────────────────────────

@router.get("/matriz-competencias")
async def list_matriz(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSMatrizCompetencia).order_by(LMSMatrizCompetencia.cargo))
    items = result.scalars().all()
    data = []
    for m in items:
        comp = await db.get(LMSCompetencia, m.competencia_id)
        data.append({
            "id": m.id, "cargo": m.cargo, "area": m.area,
            "competencia": comp.nombre if comp else None,
            "nivel_requerido": m.nivel_requerido,
            "nivel_actual": m.nivel_actual,
            "brecha": m.brecha,
        })
    return data

@router.post("/matriz-competencias")
async def create_matriz(body: MatrizCompetenciaCreate, db: AsyncSession = Depends(get_db)):
    niveles = {"INICIAL": 1, "BASICO": 2, "INTERMEDIO": 3, "AVANZADO": 4, "EXPERTO": 5}
    req = niveles.get(body.nivel_requerido, 3)
    act = niveles.get(body.nivel_actual, 0) if body.nivel_actual else 0
    brecha = max(0, req - act)
    obj = LMSMatrizCompetencia(**body.model_dump(), brecha=brecha)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "brecha": obj.brecha}

# ─── Rutas de Aprendizaje ────────────────────────────────────────────────────

@router.get("/rutas")
async def list_rutas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSRutaAprendizaje).where(LMSRutaAprendizaje.activo == True).order_by(LMSRutaAprendizaje.nombre))
    items = result.scalars().all()
    data = []
    for r in items:
        c_q = await db.execute(select(func.count()).where(LMSRutaCurso.ruta_id == r.id))
        insc_q = await db.execute(select(func.count()).where(LMSInscripcion.ruta_id == r.id))
        data.append({
            "id": r.id, "codigo": r.codigo, "nombre": r.nombre,
            "descripcion": r.descripcion,
            "cargo_objetivo": r.cargo_objetivo,
            "area_objetivo": r.area_objetivo,
            "duracion_total_horas": float(r.duracion_total_horas or 0),
            "total_cursos": c_q.scalar() or 0,
            "total_inscritos": insc_q.scalar() or 0,
        })
    return data

@router.post("/rutas")
async def create_ruta(body: RutaCreate, db: AsyncSession = Depends(get_db)):
    year = datetime.utcnow().year
    seq_q = await db.execute(select(func.count()).select_from(LMSRutaAprendizaje))
    seq = (seq_q.scalar() or 0) + 1
    obj = LMSRutaAprendizaje(**body.model_dump(), codigo=f"RUT-{year}-{seq:03d}")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "codigo": obj.codigo, "nombre": obj.nombre}

# ─── Inscripciones ───────────────────────────────────────────────────────────

@router.get("/inscripciones")
async def list_inscripciones(
    usuario_id: Optional[int] = None,
    estado: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(LMSInscripcion)
    filters = []
    if usuario_id:
        filters.append(LMSInscripcion.usuario_id == usuario_id)
    if estado:
        filters.append(LMSInscripcion.estado == estado)
    if filters:
        q = q.where(and_(*filters))
    q = q.order_by(LMSInscripcion.created_at.desc())
    result = await db.execute(q)
    items = result.scalars().all()
    data = []
    for i in items:
        curso = await db.get(LMSCurso, i.curso_id) if i.curso_id else None
        data.append({
            "id": i.id, "usuario_id": i.usuario_id,
            "curso_id": i.curso_id,
            "curso_nombre": curso.nombre if curso else None,
            "ruta_id": i.ruta_id,
            "estado": i.estado,
            "progreso_pct": float(i.progreso_pct or 0),
            "nota_final": float(i.nota_final) if i.nota_final else None,
            "fecha_inicio": i.fecha_inicio.isoformat() if i.fecha_inicio else None,
            "fecha_fin": i.fecha_fin.isoformat() if i.fecha_fin else None,
        })
    return data

@router.post("/inscripciones")
async def create_inscripcion(body: InscripcionCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSInscripcion(
        **body.model_dump(),
        estado=EstadoInscripcionEnum.INSCRITO,
        fecha_inicio=datetime.utcnow(),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "estado": obj.estado}

# ─── Evaluaciones ────────────────────────────────────────────────────────────

@router.get("/evaluaciones")
async def list_evaluaciones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSEvaluacion).where(LMSEvaluacion.activo == True).order_by(LMSEvaluacion.nombre))
    items = result.scalars().all()
    data = []
    for e in items:
        curso = await db.get(LMSCurso, e.curso_id) if e.curso_id else None
        p_q = await db.execute(select(func.count()).where(LMSEvaluacionPregunta.evaluacion_id == e.id))
        i_q = await db.execute(select(func.count()).where(LMSIntentoEvaluacion.evaluacion_id == e.id))
        apro_q = await db.execute(
            select(func.count()).where(and_(
                LMSIntentoEvaluacion.evaluacion_id == e.id,
                LMSIntentoEvaluacion.aprobado == True,
            ))
        )
        intentos = i_q.scalar() or 0   # un resultado se lee una sola vez
        total_int = intentos or 1
        apro = apro_q.scalar() or 0
        data.append({
            "id": e.id, "codigo": e.codigo, "nombre": e.nombre,
            "tipo": e.tipo,
            "curso_nombre": curso.nombre if curso else None,
            "tiempo_limite_min": e.tiempo_limite_min,
            "intentos_maximos": e.intentos_maximos,
            "puntaje_aprobacion": e.puntaje_aprobacion,
            "total_preguntas": p_q.scalar() or 0,
            "total_intentos": intentos,
            "tasa_aprobacion": round((apro / total_int) * 100, 1),
        })
    return data

@router.post("/evaluaciones")
async def create_evaluacion(body: EvaluacionCreate, db: AsyncSession = Depends(get_db)):
    year = datetime.utcnow().year
    seq_q = await db.execute(select(func.count()).select_from(LMSEvaluacion))
    seq = (seq_q.scalar() or 0) + 1
    obj = LMSEvaluacion(**body.model_dump(), codigo=f"EVL-{year}-{seq:03d}")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "codigo": obj.codigo, "nombre": obj.nombre}

# ─── Banco de Preguntas ──────────────────────────────────────────────────────

@router.get("/preguntas")
async def list_preguntas(
    tipo: Optional[str] = None,
    nivel: Optional[str] = None,
    categoria: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(LMSPregunta).where(LMSPregunta.activo == True)
    if tipo:
        q = q.where(LMSPregunta.tipo == tipo)
    if nivel:
        q = q.where(LMSPregunta.nivel_dificultad == nivel)
    if categoria:
        q = q.where(LMSPregunta.categoria == categoria)
    q = q.order_by(LMSPregunta.created_at.desc())
    result = await db.execute(q)
    items = result.scalars().all()
    return [
        {
            "id": p.id, "codigo": p.codigo, "tipo": p.tipo,
            "enunciado": p.enunciado[:120] + ("..." if len(p.enunciado) > 120 else ""),
            "nivel_dificultad": p.nivel_dificultad,
            "categoria": p.categoria, "puntaje": p.puntaje,
        }
        for p in items
    ]

@router.post("/preguntas")
async def create_pregunta(body: PreguntaCreate, db: AsyncSession = Depends(get_db)):
    year = datetime.utcnow().year
    seq_q = await db.execute(select(func.count()).select_from(LMSPregunta))
    seq = (seq_q.scalar() or 0) + 1
    obj = LMSPregunta(**body.model_dump(), codigo=f"PRG-{year}-{seq:04d}")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "codigo": obj.codigo}

@router.post("/preguntas/opciones")
async def create_opcion(body: OpcionCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSOpcionRespuesta(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id}

# ─── Certificaciones ─────────────────────────────────────────────────────────

@router.get("/certificaciones")
async def list_certificaciones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSCertificacion).where(LMSCertificacion.activo == True).order_by(LMSCertificacion.nombre))
    items = result.scalars().all()
    data = []
    for c in items:
        cert_q = await db.execute(select(func.count()).where(LMSCertificadoUsuario.certificacion_id == c.id))
        vig_q  = await db.execute(select(func.count()).where(and_(
            LMSCertificadoUsuario.certificacion_id == c.id,
            LMSCertificadoUsuario.estado == EstadoCertificacionEnum.VIGENTE,
        )))
        data.append({
            "id": c.id, "codigo": c.codigo, "nombre": c.nombre,
            "descripcion": c.descripcion, "vigencia_meses": c.vigencia_meses,
            "curso_id": c.curso_id, "programa_id": c.programa_id, "entidad_emisora": c.entidad_emisora,
            "total_emitidos": cert_q.scalar() or 0,
            "vigentes": vig_q.scalar() or 0,
        })
    return data

@router.post("/certificaciones")
async def create_certificacion(body: CertificacionCreate, db: AsyncSession = Depends(get_db)):
    year = datetime.utcnow().year
    seq_q = await db.execute(select(func.count()).select_from(LMSCertificacion))
    seq = (seq_q.scalar() or 0) + 1
    obj = LMSCertificacion(**body.model_dump(), codigo=f"CERT-{year}-{seq:03d}")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "codigo": obj.codigo, "nombre": obj.nombre}

@router.get("/certificados")
async def list_certificados(
    estado: Optional[str] = None,
    usuario_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(LMSCertificadoUsuario)
    if estado:
        q = q.where(LMSCertificadoUsuario.estado == estado)
    if usuario_id:
        q = q.where(LMSCertificadoUsuario.usuario_id == usuario_id)
    q = q.order_by(LMSCertificadoUsuario.fecha_vencimiento)
    result = await db.execute(q)
    items = result.scalars().all()
    data = []
    for c in items:
        cert = await db.get(LMSCertificacion, c.certificacion_id)
        data.append({
            "id": c.id,
            "certificacion": cert.nombre if cert else None,
            "usuario_id": c.usuario_id,
            "numero_certificado": c.numero_certificado,
            "fecha_emision": c.fecha_emision.isoformat() if c.fecha_emision else None,
            "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
            "estado": c.estado,
        })
    return data

@router.post("/certificados")
async def emitir_certificado(body: CertificadoCreate, db: AsyncSession = Depends(get_db)):
    cert = await db.get(LMSCertificacion, body.certificacion_id)
    if not cert:
        raise HTTPException(404, "Certificación no encontrada")
    year = body.fecha_emision.year
    seq_q = await db.execute(select(func.count()).select_from(LMSCertificadoUsuario))
    seq = (seq_q.scalar() or 0) + 1
    num = f"CERT-{year}-{seq:06d}"
    fv = body.fecha_vencimiento or (body.fecha_emision + timedelta(days=cert.vigencia_meses * 30))
    obj = LMSCertificadoUsuario(
        certificacion_id=body.certificacion_id,
        usuario_id=body.usuario_id,
        numero_certificado=num,
        fecha_emision=body.fecha_emision,
        fecha_vencimiento=fv,
        estado=EstadoCertificacionEnum.VIGENTE,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "numero_certificado": obj.numero_certificado}

@router.get("/certificados/por-vencer")
async def certificados_por_vencer(dias: int = 30, db: AsyncSession = Depends(get_db)):
    limite = datetime.utcnow() + timedelta(days=dias)
    result = await db.execute(
        select(LMSCertificadoUsuario).where(
            and_(
                LMSCertificadoUsuario.estado == EstadoCertificacionEnum.VIGENTE,
                LMSCertificadoUsuario.fecha_vencimiento <= limite,
            )
        ).order_by(LMSCertificadoUsuario.fecha_vencimiento)
    )
    items = result.scalars().all()
    data = []
    for c in items:
        cert = await db.get(LMSCertificacion, c.certificacion_id)
        data.append({
            "id": c.id,
            "certificacion": cert.nombre if cert else None,
            "usuario_id": c.usuario_id,
            "numero_certificado": c.numero_certificado,
            "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
            "dias_restantes": (c.fecha_vencimiento - datetime.utcnow()).days if c.fecha_vencimiento else None,
        })
    return data

# ─── Insignias ───────────────────────────────────────────────────────────────

@router.get("/insignias")
async def list_insignias(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSInsignia).where(LMSInsignia.activo == True).order_by(LMSInsignia.nombre))
    items = result.scalars().all()
    data = []
    for i in items:
        u_q = await db.execute(select(func.count()).where(LMSInsigniaUsuario.insignia_id == i.id))
        data.append({
            "id": i.id, "nombre": i.nombre, "descripcion": i.descripcion,
            "icono": i.icono, "color": i.color, "tipo": i.tipo,
            "puntos_otorgados": i.puntos_otorgados,
            "total_otorgadas": u_q.scalar() or 0,
        })
    return data

@router.post("/insignias")
async def create_insignia(body: InsigniaCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSInsignia(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "nombre": obj.nombre}

# ─── Gamificación / Ranking ──────────────────────────────────────────────────

@router.get("/gamificacion/ranking")
async def gamificacion_ranking(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            LMSInsigniaUsuario.usuario_id,
            func.sum(LMSInsignia.puntos_otorgados).label("puntos"),
            func.count(LMSInsigniaUsuario.id).label("insignias"),
        )
        .join(LMSInsignia, LMSInsigniaUsuario.insignia_id == LMSInsignia.id)
        .group_by(LMSInsigniaUsuario.usuario_id)
        .order_by(func.sum(LMSInsignia.puntos_otorgados).desc())
        .limit(20)
    )
    rows = result.all()
    return [
        {"posicion": idx + 1, "usuario_id": r.usuario_id, "puntos": int(r.puntos or 0), "insignias": int(r.insignias or 0)}
        for idx, r in enumerate(rows)
    ]

@router.get("/gamificacion/usuario/{usuario_id}")
async def gamificacion_usuario(usuario_id: int, db: AsyncSession = Depends(get_db)):
    ins_result = await db.execute(
        select(LMSInsigniaUsuario).where(LMSInsigniaUsuario.usuario_id == usuario_id)
    )
    insignias = ins_result.scalars().all()
    puntos = 0
    insignias_data = []
    for iu in insignias:
        ins = await db.get(LMSInsignia, iu.insignia_id)
        if ins:
            puntos += ins.puntos_otorgados or 0
            insignias_data.append({"nombre": ins.nombre, "icono": ins.icono, "color": ins.color, "puntos": ins.puntos_otorgados})

    comp_result = await db.execute(
        select(LMSInscripcion).where(and_(
            LMSInscripcion.usuario_id == usuario_id,
            LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO,
        ))
    )
    completados = len(comp_result.scalars().all())

    return {
        "usuario_id": usuario_id,
        "puntos_totales": puntos,
        "total_insignias": len(insignias_data),
        "cursos_completados": completados,
        "insignias": insignias_data,
    }

# ─── Foros ───────────────────────────────────────────────────────────────────

@router.get("/foros")
async def list_foros(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LMSForo).where(LMSForo.activo == True).order_by(LMSForo.nombre))
    items = result.scalars().all()
    data = []
    for f in items:
        h_q = await db.execute(select(func.count()).where(LMSHiloForo.foro_id == f.id))
        data.append({
            "id": f.id, "nombre": f.nombre, "descripcion": f.descripcion,
            "curso_id": f.curso_id, "total_hilos": h_q.scalar() or 0,
        })
    return data

@router.post("/foros")
async def create_foro(body: ForoCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSForo(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "nombre": obj.nombre}

@router.get("/foros/{foro_id}/hilos")
async def list_hilos(foro_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LMSHiloForo).where(LMSHiloForo.foro_id == foro_id).order_by(LMSHiloForo.fijado.desc(), LMSHiloForo.created_at.desc())
    )
    items = result.scalars().all()
    data = []
    for h in items:
        c_q = await db.execute(select(func.count()).where(LMSComentario.hilo_id == h.id))
        data.append({
            "id": h.id, "titulo": h.titulo, "contenido": h.contenido[:200],
            "usuario_id": h.usuario_id, "fijado": h.fijado,
            "total_comentarios": c_q.scalar() or 0,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        })
    return data

@router.post("/foros/hilos")
async def create_hilo(body: HiloCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSHiloForo(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id}

@router.post("/foros/hilos/comentarios")
async def create_comentario(body: ComentarioCreate, db: AsyncSession = Depends(get_db)):
    obj = LMSComentario(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id}

# ─── Reportes / KPIs ─────────────────────────────────────────────────────────

@router.get("/reportes/kpis-area")
async def reportes_kpis_area(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            LMSMatrizCompetencia.area,
            func.count(LMSMatrizCompetencia.id).label("total"),
            func.sum(LMSMatrizCompetencia.brecha).label("brechas"),
            func.avg(LMSMatrizCompetencia.brecha).label("brecha_avg"),
        )
        .where(LMSMatrizCompetencia.area.isnot(None))
        .group_by(LMSMatrizCompetencia.area)
        .order_by(func.sum(LMSMatrizCompetencia.brecha).desc())
    )
    rows = result.all()
    return [
        {
            "area": r.area,
            "total_competencias": int(r.total),
            "total_brechas": int(r.brechas or 0),
            "brecha_promedio": round(float(r.brecha_avg or 0), 2),
        }
        for r in rows
    ]

@router.get("/reportes/horas-capacitacion")
async def reportes_horas(db: AsyncSession = Depends(get_db)):
    completados = await db.execute(
        select(LMSInscripcion).where(LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO)
    )
    items = completados.scalars().all()
    total_horas = 0.0
    for i in items:
        if i.curso_id:
            c = await db.get(LMSCurso, i.curso_id)
            if c:
                total_horas += float(c.duracion_horas or 0)
    return {
        "total_horas_completadas": round(total_horas, 2),
        "total_completados": len(items),
        "promedio_horas_por_colaborador": round(total_horas / max(len(items), 1), 2),
    }

# ─── IA / Recomendaciones ────────────────────────────────────────────────────

@router.get("/ia/recomendaciones/{usuario_id}")
async def ia_recomendaciones(usuario_id: int, db: AsyncSession = Depends(get_db)):
    insc_result = await db.execute(
        select(LMSInscripcion.curso_id).where(LMSInscripcion.usuario_id == usuario_id)
    )
    inscritos = {r[0] for r in insc_result.all() if r[0]}
    result = await db.execute(
        select(LMSCurso).where(
            and_(
                LMSCurso.estado == EstadoCursoEnum.PUBLICADO,
                LMSCurso.id.notin_(inscritos) if inscritos else True,
            )
        ).order_by(LMSCurso.es_obligatorio.desc(), LMSCurso.nombre).limit(6)
    )
    cursos = result.scalars().all()
    return [
        {
            "id": c.id, "codigo": c.codigo, "nombre": c.nombre,
            "modalidad": c.modalidad, "nivel": c.nivel,
            "duracion_horas": float(c.duracion_horas or 0),
            "es_obligatorio": c.es_obligatorio,
            "razon": "Obligatorio para tu cargo" if c.es_obligatorio else "Recomendado por IA según tu perfil",
            "score_ia": 95 if c.es_obligatorio else 78,
        }
        for c in cursos
    ]

@router.get("/ia/predicciones")
async def ia_predicciones(db: AsyncSession = Depends(get_db)):
    total_q = await db.execute(select(func.count()).select_from(LMSInscripcion))
    comp_q  = await db.execute(select(func.count()).where(LMSInscripcion.estado == EstadoInscripcionEnum.COMPLETADO))
    abandon_q = await db.execute(select(func.count()).where(LMSInscripcion.estado == EstadoInscripcionEnum.ABANDONADO))
    total     = total_q.scalar() or 1
    completados = comp_q.scalar() or 0
    abandonos   = abandon_q.scalar() or 0
    brechas_q = await db.execute(select(func.count()).where(LMSMatrizCompetencia.brecha > 2))
    brechas_criticas = brechas_q.scalar() or 0
    return {
        "riesgo_incumplimiento_pct": round((abandonos / total) * 100, 1),
        "tasa_finalizacion_pct": round((completados / total) * 100, 1),
        "brechas_criticas": brechas_criticas,
        "prediccion_completados_mes": completados + 12,
        "alertas": [
            f"{brechas_criticas} brechas de competencia nivel crítico detectadas" if brechas_criticas > 0 else None,
            f"Tasa de abandono: {round((abandonos / total) * 100, 1)}%" if abandonos > 0 else None,
        ],
    }

# ─── Onboarding ──────────────────────────────────────────────────────────────

@router.get("/onboarding/cursos-obligatorios")
async def onboarding_cursos_obligatorios(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LMSCurso).where(
            and_(LMSCurso.es_obligatorio == True, LMSCurso.estado == EstadoCursoEnum.PUBLICADO)
        ).order_by(LMSCurso.nombre)
    )
    cursos = result.scalars().all()
    return [
        {
            "id": c.id, "codigo": c.codigo, "nombre": c.nombre,
            "modalidad": c.modalidad, "nivel": c.nivel,
            "duracion_horas": float(c.duracion_horas or 0),
            "categoria": c.categoria,
        }
        for c in cursos
    ]
