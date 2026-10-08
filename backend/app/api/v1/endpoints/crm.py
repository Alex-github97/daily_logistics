from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.core.database import get_db
from app.infrastructure.models.crm import (
    CRMEjecutivoComercial, CRMCliente, CRMContacto, CRMLead,
    CRMOportunidad, CRMCotizacion, CRMCotizacionItem, CRMContrato,
    CRMContratoSLA, CRMTicket, CRMInteraccion, CRMCampana, CRMCampanaCliente,
    CRMEncuesta, CRMCuentaClave, CRMObjetivoComercial, CRMActividad,
    CRMRiesgoCliente, CRMSaludCliente, CRMKPIDiario, CRMParametro,
    EstadoClienteEnum, TipoClienteEnum, SegmentoClienteEnum,
    EstadoLeadEnum, EstadoOportunidadEnum, EstadoCotizacionEnum,
    EstadoContratoEnum, EstadoTicketEnum, TipoTicketEnum,
    TipoInteraccionEnum, TipoCampanaEnum, TipoEncuestaEnum, NivelRiesgoClienteEnum,
)

router = APIRouter(prefix="/crm", tags=["CRM"])


# ──────────────────────────────────────────
# SCHEMAS
# ──────────────────────────────────────────

class EjecutivoCreate(BaseModel):
    codigo: str
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    region: Optional[str] = None
    meta_anual: Optional[Decimal] = None

class EjecutivoResponse(EjecutivoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool


class ClienteCreate(BaseModel):
    codigo: str
    razon_social: str
    nit: Optional[str] = None
    tipo: TipoClienteEnum = TipoClienteEnum.EMPRESA
    segmento: Optional[SegmentoClienteEnum] = None
    estado: EstadoClienteEnum = EstadoClienteEnum.PROSPECTO
    industria: Optional[str] = None
    pais: str = "Colombia"
    ciudad: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    sitio_web: Optional[str] = None
    ejecutivo_id: Optional[int] = None
    potencial_anual: Optional[Decimal] = None
    notas: Optional[str] = None

class ClienteResponse(ClienteCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ingresos_ytd: Decimal
    health_score: int
    lead_score: int
    activo: bool


class ContactoCreate(BaseModel):
    cliente_id: int
    nombre: str
    cargo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    whatsapp: Optional[str] = None
    linkedin: Optional[str] = None
    es_decisor: bool = False
    es_principal: bool = False

class ContactoResponse(ContactoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool


class LeadCreate(BaseModel):
    codigo: str
    cliente_id: Optional[int] = None
    ejecutivo_id: Optional[int] = None
    empresa: str
    contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    fuente: Optional[str] = None
    industria: Optional[str] = None
    estado: EstadoLeadEnum = EstadoLeadEnum.FRIO
    score: int = 0
    potencial: Optional[Decimal] = None
    notas: Optional[str] = None

class LeadResponse(LeadCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    convertido: bool


class OportunidadCreate(BaseModel):
    codigo: str
    cliente_id: int
    lead_id: Optional[int] = None
    ejecutivo_id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = None
    estado: EstadoOportunidadEnum = EstadoOportunidadEnum.IDENTIFICACION
    probabilidad: int = 10
    valor_estimado: Optional[Decimal] = None
    servicio: Optional[str] = None
    fecha_esperada: Optional[date] = None

class OportunidadResponse(OportunidadCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    valor_contratado: Optional[Decimal]
    fecha_cierre: Optional[date]
    motivo_perdida: Optional[str]


class CotizacionCreate(BaseModel):
    codigo: str
    oportunidad_id: Optional[int] = None
    cliente_id: int
    ejecutivo_id: Optional[int] = None
    estado: EstadoCotizacionEnum = EstadoCotizacionEnum.BORRADOR
    validez_dias: int = 30
    notas: Optional[str] = None

class CotizacionResponse(CotizacionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int
    subtotal: Decimal
    iva: Decimal
    total: Decimal
    fecha_envio: Optional[date]
    fecha_vencimiento: Optional[date]


class ContratoCreate(BaseModel):
    codigo: str
    cliente_id: int
    oportunidad_id: Optional[int] = None
    ejecutivo_id: Optional[int] = None
    nombre: str
    estado: EstadoContratoEnum = EstadoContratoEnum.BORRADOR
    tipo_servicio: Optional[str] = None
    valor_mensual: Optional[Decimal] = None
    valor_total: Optional[Decimal] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    duracion_meses: Optional[int] = None
    auto_renovacion: bool = False
    notas: Optional[str] = None

class ContratoResponse(ContratoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TicketCreate(BaseModel):
    codigo: str
    cliente_id: int
    contrato_id: Optional[int] = None
    contacto_id: Optional[int] = None
    ejecutivo_id: Optional[int] = None
    tipo: TipoTicketEnum = TipoTicketEnum.SOLICITUD
    estado: EstadoTicketEnum = EstadoTicketEnum.ABIERTO
    prioridad: str = "MEDIA"
    asunto: str
    descripcion: Optional[str] = None
    canal: Optional[str] = None

class TicketResponse(TicketCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha_limite: Optional[datetime]
    fecha_resolucion: Optional[datetime]
    tiempo_respuesta_hrs: Optional[Decimal]
    tiempo_solucion_hrs: Optional[Decimal]
    satisfaccion: Optional[int]


class InteraccionCreate(BaseModel):
    cliente_id: int
    contacto_id: Optional[int] = None
    ticket_id: Optional[int] = None
    oportunidad_id: Optional[int] = None
    ejecutivo_id: Optional[int] = None
    tipo: TipoInteraccionEnum
    asunto: Optional[str] = None
    descripcion: Optional[str] = None
    duracion_min: Optional[int] = None
    resultado: Optional[str] = None
    proximo_paso: Optional[str] = None
    fecha_interaccion: Optional[datetime] = None

class InteraccionResponse(InteraccionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class EncuestaCreate(BaseModel):
    codigo: str
    cliente_id: int
    ticket_id: Optional[int] = None
    tipo: TipoEncuestaEnum
    puntaje: Optional[int] = None
    comentario: Optional[str] = None

class EncuestaResponse(EncuestaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    respondida: bool
    fecha_envio: Optional[date]
    fecha_respuesta: Optional[date]


class KPIDiarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha: date
    total_clientes: int
    clientes_activos: int
    total_leads: int
    leads_calientes: int
    pipeline_valor: Decimal
    oportunidades_activas: int
    tasa_conversion: Decimal
    win_rate: Decimal
    tickets_abiertos: int
    tickets_escalados: int
    nps_promedio: Decimal
    csat_promedio: Decimal
    contratos_activos: int
    contratos_por_vencer: int
    ingresos_mes: Decimal
    churn_rate: Decimal


# ──────────────────────────────────────────
# ENDPOINTS — EJECUTIVOS
# ──────────────────────────────────────────

@router.get("/ejecutivos", response_model=List[EjecutivoResponse])
async def listar_ejecutivos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CRMEjecutivoComercial).where(CRMEjecutivoComercial.activo == True))
    return result.scalars().all()

@router.post("/ejecutivos", response_model=EjecutivoResponse)
async def crear_ejecutivo(data: EjecutivoCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMEjecutivoComercial(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.get("/ejecutivos/{id}", response_model=EjecutivoResponse)
async def obtener_ejecutivo(id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(CRMEjecutivoComercial, id)
    if not obj:
        raise HTTPException(404, "Ejecutivo no encontrado")
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — CLIENTES
# ──────────────────────────────────────────

@router.get("/clientes", response_model=List[ClienteResponse])
async def listar_clientes(
    estado: Optional[str] = None,
    segmento: Optional[str] = None,
    ejecutivo_id: Optional[int] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMCliente).where(CRMCliente.activo == True)
    if estado:
        stmt = stmt.where(CRMCliente.estado == estado)
    if segmento:
        stmt = stmt.where(CRMCliente.segmento == segmento)
    if ejecutivo_id:
        stmt = stmt.where(CRMCliente.ejecutivo_id == ejecutivo_id)
    if q:
        stmt = stmt.where(CRMCliente.razon_social.ilike(f"%{q}%"))
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/clientes", response_model=ClienteResponse, status_code=201)
async def crear_cliente(data: ClienteCreate, db: AsyncSession = Depends(get_db)):
    """Da de alta un cliente o prospecto.

    El código se comprueba antes de insertar. Dejar que reviente el índice único
    de la base devuelve un 500, y quien lo ve no tiene forma de saber que lo
    único que pasa es que ese código ya está usado.
    """
    repetido = (await db.execute(select(CRMCliente).where(
        CRMCliente.codigo == data.codigo))).scalar_one_or_none()
    if repetido is not None:
        raise HTTPException(
            409, f"El código {data.codigo} ya lo usa «{repetido.razon_social}».")
    obj = CRMCliente(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.get("/clientes/{id}", response_model=ClienteResponse)
async def obtener_cliente(id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(CRMCliente, id)
    if not obj:
        raise HTTPException(404, "Cliente no encontrado")
    return obj

class ClienteEdicion(BaseModel):
    """Todo opcional: se manda solo lo que cambió.

    Con el modelo de creación aquí, cambiar la ciudad exigía reenviar el código
    y la razón social, y cualquier campo que la pantalla no incluyera se perdía.
    """
    codigo: Optional[str] = None
    razon_social: Optional[str] = None
    nit: Optional[str] = None
    tipo: Optional[TipoClienteEnum] = None
    segmento: Optional[SegmentoClienteEnum] = None
    estado: Optional[EstadoClienteEnum] = None
    industria: Optional[str] = None
    pais: Optional[str] = None
    ciudad: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    sitio_web: Optional[str] = None
    ejecutivo_id: Optional[int] = None
    potencial_anual: Optional[Decimal] = None
    notas: Optional[str] = None
    activo: Optional[bool] = None


@router.put("/clientes/{id}", response_model=ClienteResponse)
async def actualizar_cliente(id: int, data: ClienteEdicion, db: AsyncSession = Depends(get_db)):
    obj = await db.get(CRMCliente, id)
    if not obj:
        raise HTTPException(404, "Cliente no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — CONTACTOS
# ──────────────────────────────────────────

@router.get("/contactos", response_model=List[ContactoResponse])
async def listar_contactos(cliente_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(CRMContacto).where(CRMContacto.activo == True)
    if cliente_id:
        stmt = stmt.where(CRMContacto.cliente_id == cliente_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/contactos", response_model=ContactoResponse)
async def crear_contacto(data: ContactoCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMContacto(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — LEADS
# ──────────────────────────────────────────

@router.get("/leads", response_model=List[LeadResponse])
async def listar_leads(
    estado: Optional[str] = None,
    ejecutivo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMLead)
    if estado:
        stmt = stmt.where(CRMLead.estado == estado)
    if ejecutivo_id:
        stmt = stmt.where(CRMLead.ejecutivo_id == ejecutivo_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/leads", response_model=LeadResponse)
async def crear_lead(data: LeadCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMLead(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put("/leads/{id}", response_model=LeadResponse)
async def actualizar_lead(id: int, data: LeadCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(CRMLead, id)
    if not obj:
        raise HTTPException(404, "Lead no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — OPORTUNIDADES
# ──────────────────────────────────────────

@router.get("/oportunidades", response_model=List[OportunidadResponse])
async def listar_oportunidades(
    estado: Optional[str] = None,
    cliente_id: Optional[int] = None,
    ejecutivo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMOportunidad)
    if estado:
        stmt = stmt.where(CRMOportunidad.estado == estado)
    if cliente_id:
        stmt = stmt.where(CRMOportunidad.cliente_id == cliente_id)
    if ejecutivo_id:
        stmt = stmt.where(CRMOportunidad.ejecutivo_id == ejecutivo_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/oportunidades", response_model=OportunidadResponse)
async def crear_oportunidad(data: OportunidadCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMOportunidad(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

# La probabilidad que corresponde a cada etapa. Va aquí y no en la pantalla: si
# cada sitio la decidiera, el mismo negocio saldría con un pronóstico distinto en
# el tablero y en la ficha, y el pronóstico ponderado dejaría de significar nada.
_PROBABILIDAD_POR_ETAPA = {
    "IDENTIFICACION": 10, "CALIFICACION": 30, "PROPUESTA": 55,
    "NEGOCIACION": 80, "CIERRE_GANADO": 100, "CIERRE_PERDIDO": 0,
}


class MoverOportunidad(BaseModel):
    estado: EstadoOportunidadEnum
    valor_contratado: Optional[Decimal] = None
    motivo_perdida: Optional[str] = None


@router.put("/oportunidades/{id}/estado")
async def actualizar_estado_oportunidad(
    id: int, datos: MoverOportunidad, db: AsyncSession = Depends(get_db),
):
    """Mueve una oportunidad de etapa, con lo que eso arrastra.

    Mover de etapa no es solo cambiar una palabra:

    · **La probabilidad sigue a la etapa.** Dejarla como estaba produce una
      oportunidad en negociación con el 10% de probabilidad, y el pronóstico
      ponderado —que es para lo que existe la probabilidad— queda mal.

    · **Cerrar sella la fecha, y reabrir la borra.** Sin fecha de cierre, una
      oportunidad ganada no aparece en el trimestre de nadie; con una fecha vieja
      después de reabrirla, aparece en un trimestre en el que ya no está.

    · **Perder exige decir por qué.** El motivo es el único dato que hace útil el
      historial de perdidas: sin él solo queda saber cuántas, que no ayuda a
      perder menos la próxima vez.
    """
    obj = await db.get(CRMOportunidad, id)
    if not obj:
        raise HTTPException(404, "Esa oportunidad no existe.")

    destino = datos.estado.value
    if destino == "CIERRE_PERDIDO" and not (datos.motivo_perdida or "").strip():
        raise HTTPException(422, "Diga por qué se perdió: sin el motivo, el "
                                 "historial de pérdidas no sirve para nada.")

    obj.estado = datos.estado
    obj.probabilidad = _PROBABILIDAD_POR_ETAPA.get(destino, obj.probabilidad)

    if destino == "CIERRE_GANADO":
        obj.fecha_cierre = date.today()
        obj.valor_contratado = datos.valor_contratado or obj.valor_estimado
        obj.motivo_perdida = None
    elif destino == "CIERRE_PERDIDO":
        obj.fecha_cierre = date.today()
        obj.motivo_perdida = datos.motivo_perdida.strip()[:200]
        obj.valor_contratado = None
    else:
        # Vuelve a estar abierta: no puede conservar su fecha de cierre.
        obj.fecha_cierre = None
        obj.motivo_perdida = None

    await db.commit()
    await db.refresh(obj)
    return OportunidadResponse.model_validate(obj)


# ──────────────────────────────────────────
# ENDPOINTS — COTIZACIONES
# ──────────────────────────────────────────

@router.get("/cotizaciones", response_model=List[CotizacionResponse])
async def listar_cotizaciones(
    estado: Optional[str] = None,
    cliente_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMCotizacion)
    if estado:
        stmt = stmt.where(CRMCotizacion.estado == estado)
    if cliente_id:
        stmt = stmt.where(CRMCotizacion.cliente_id == cliente_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/cotizaciones", response_model=CotizacionResponse)
async def crear_cotizacion(data: CotizacionCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMCotizacion(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — CONTRATOS
# ──────────────────────────────────────────

@router.get("/contratos", response_model=List[ContratoResponse])
async def listar_contratos(
    estado: Optional[str] = None,
    cliente_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMContrato)
    if estado:
        stmt = stmt.where(CRMContrato.estado == estado)
    if cliente_id:
        stmt = stmt.where(CRMContrato.cliente_id == cliente_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/contratos", response_model=ContratoResponse)
async def crear_contrato(data: ContratoCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMContrato(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put("/contratos/{id}", response_model=ContratoResponse)
async def actualizar_contrato(id: int, data: ContratoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(CRMContrato, id)
    if not obj:
        raise HTTPException(404, "Contrato no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — TICKETS
# ──────────────────────────────────────────

@router.get("/tickets", response_model=List[TicketResponse])
async def listar_tickets(
    estado: Optional[str] = None,
    cliente_id: Optional[int] = None,
    tipo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMTicket)
    if estado:
        stmt = stmt.where(CRMTicket.estado == estado)
    if cliente_id:
        stmt = stmt.where(CRMTicket.cliente_id == cliente_id)
    if tipo:
        stmt = stmt.where(CRMTicket.tipo == tipo)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/tickets", response_model=TicketResponse)
async def crear_ticket(data: TicketCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMTicket(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

class MoverTicket(BaseModel):
    estado: EstadoTicketEnum
    satisfaccion: Optional[int] = None


@router.put("/tickets/{id}/estado", response_model=TicketResponse)
async def actualizar_estado_ticket(
    id: int, datos: MoverTicket, db: AsyncSession = Depends(get_db),
):
    """Cambia el estado de un ticket y calcula lo que eso implica.

    Cerrar sella la fecha de resolución y, con ella, las horas que tomó. Ese par
    de números es de donde salen el cumplimiento del plazo y el informe de
    servicio: si el estado cambiara sin sellarlos, el ticket figuraría resuelto y
    no contaría en ninguna medición.

    Reabrir los borra. Un ticket que se reabre y conserva su tiempo de solución
    dice que se resolvió en cuatro horas algo que sigue abierto.
    """
    obj = await db.get(CRMTicket, id)
    if not obj:
        raise HTTPException(404, "Ese ticket no existe.")

    if datos.satisfaccion is not None and not 1 <= datos.satisfaccion <= 5:
        raise HTTPException(422, "La satisfacción va de 1 a 5.")

    cerrado = datos.estado in (EstadoTicketEnum.RESUELTO, EstadoTicketEnum.CERRADO)
    obj.estado = datos.estado

    if cerrado and obj.fecha_resolucion is None:
        ahora = datetime.now(timezone.utc)
        obj.fecha_resolucion = ahora
        creado = obj.created_at or ahora
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        horas = max(0.0, (ahora - creado).total_seconds() / 3600)
        obj.tiempo_solucion_hrs = Decimal(str(round(horas, 2)))
        if obj.tiempo_respuesta_hrs is None:
            obj.tiempo_respuesta_hrs = obj.tiempo_solucion_hrs
    elif not cerrado:
        obj.fecha_resolucion = None
        obj.tiempo_solucion_hrs = None

    if datos.satisfaccion is not None:
        obj.satisfaccion = datos.satisfaccion

    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — INTERACCIONES
# ──────────────────────────────────────────

@router.get("/interacciones", response_model=List[InteraccionResponse])
async def listar_interacciones(
    cliente_id: Optional[int] = None,
    tipo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMInteraccion).order_by(CRMInteraccion.created_at.desc())
    if cliente_id:
        stmt = stmt.where(CRMInteraccion.cliente_id == cliente_id)
    if tipo:
        stmt = stmt.where(CRMInteraccion.tipo == tipo)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/interacciones", response_model=InteraccionResponse)
async def crear_interaccion(data: InteraccionCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMInteraccion(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — ENCUESTAS
# ──────────────────────────────────────────

@router.get("/encuestas", response_model=List[EncuestaResponse])
async def listar_encuestas(
    cliente_id: Optional[int] = None,
    tipo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CRMEncuesta)
    if cliente_id:
        stmt = stmt.where(CRMEncuesta.cliente_id == cliente_id)
    if tipo:
        stmt = stmt.where(CRMEncuesta.tipo == tipo)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/encuestas", response_model=EncuestaResponse)
async def crear_encuesta(data: EncuestaCreate, db: AsyncSession = Depends(get_db)):
    obj = CRMEncuesta(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ──────────────────────────────────────────
# ENDPOINTS — KPIs
# ──────────────────────────────────────────

@router.get("/kpis/dashboard")
async def kpis_dashboard(db: AsyncSession = Depends(get_db)):
    total_clientes = (await db.execute(select(func.count()).select_from(CRMCliente).where(CRMCliente.activo == True))).scalar_one()
    clientes_activos = (await db.execute(select(func.count()).select_from(CRMCliente).where(CRMCliente.estado == 'CLIENTE_ACTIVO'))).scalar_one()
    total_leads = (await db.execute(select(func.count()).select_from(CRMLead))).scalar_one()
    leads_calientes = (await db.execute(select(func.count()).select_from(CRMLead).where(CRMLead.estado == 'CALIENTE'))).scalar_one()
    oportunidades_activas = (await db.execute(select(func.count()).select_from(CRMOportunidad).where(CRMOportunidad.estado.not_in(['CIERRE_GANADO', 'CIERRE_PERDIDO'])))).scalar_one()
    tickets_abiertos = (await db.execute(select(func.count()).select_from(CRMTicket).where(CRMTicket.estado == 'ABIERTO'))).scalar_one()
    tickets_escalados = (await db.execute(select(func.count()).select_from(CRMTicket).where(CRMTicket.estado == 'ESCALADO'))).scalar_one()
    contratos_activos = (await db.execute(select(func.count()).select_from(CRMContrato).where(CRMContrato.estado == 'ACTIVO'))).scalar_one()
    return {
        "total_clientes": total_clientes,
        "clientes_activos": clientes_activos,
        "total_leads": total_leads,
        "leads_calientes": leads_calientes,
        "oportunidades_activas": oportunidades_activas,
        "tickets_abiertos": tickets_abiertos,
        "tickets_escalados": tickets_escalados,
        "contratos_activos": contratos_activos,
    }

@router.get("/kpis/diarios", response_model=List[KPIDiarioResponse])
async def kpis_diarios(
    limit: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CRMKPIDiario).order_by(CRMKPIDiario.fecha.desc()).limit(limit)
    )
    return result.scalars().all()


# ══════════════════════════════════════════════════════════════════════════════
# Lo que faltaba para que las pantallas dejaran de inventarse los datos
#
# Las quince pantallas del módulo se construyeron como maqueta, con las listas
# escritas dentro del propio archivo. Al conectarlas apareció que seis de ellas
# pedían cosas que el servidor guardaba pero no publicaba: los renglones de una
# cotización, los acuerdos de nivel de servicio de un contrato, las campañas,
# las cuentas clave, los objetivos de cada ejecutivo y el desglose del puntaje
# de salud.
#
# Son consultas de lectura sobre tablas que ya existían. No hay tabla nueva.
# ══════════════════════════════════════════════════════════════════════════════

class CotizacionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    descripcion: str
    unidad: Optional[str]
    cantidad: Decimal
    precio_unitario: Decimal
    descuento_pct: Decimal
    total: Decimal


@router.get("/cotizaciones/{cotizacion_id}")
async def detalle_cotizacion(cotizacion_id: int, db: AsyncSession = Depends(get_db)):
    """La cotización con sus renglones.

    Van juntos y no en dos rutas: una cotización sin sus renglones es un total
    que nadie puede rehacer, y quien la abre siempre quiere ver de qué se
    compone. Pedirlos aparte obliga a dos viajes para una sola pregunta.
    """
    cot = (await db.execute(select(CRMCotizacion).where(
        CRMCotizacion.id == cotizacion_id))).scalar_one_or_none()
    if cot is None:
        raise HTTPException(404, "Esa cotización no existe.")
    items = (await db.execute(select(CRMCotizacionItem).where(
        CRMCotizacionItem.cotizacion_id == cotizacion_id
    ).order_by(CRMCotizacionItem.id))).scalars().all()
    return {
        "cotizacion": CotizacionResponse.model_validate(cot),
        "items": [CotizacionItemResponse.model_validate(i) for i in items],
    }


class SLAResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    contrato_id: int
    indicador: str
    objetivo: Decimal
    unidad: Optional[str]
    valor_actual: Optional[Decimal]
    penalizacion: Optional[str]
    frecuencia_medicion: Optional[str]
    activo: bool


@router.get("/contratos/{contrato_id}/sla", response_model=List[SLAResponse])
async def sla_de_contrato(contrato_id: int, db: AsyncSession = Depends(get_db)):
    """Los acuerdos de nivel de servicio pactados en un contrato."""
    return (await db.execute(select(CRMContratoSLA).where(
        CRMContratoSLA.contrato_id == contrato_id,
    ).order_by(CRMContratoSLA.id))).scalars().all()


class CampanaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    tipo: TipoCampanaEnum
    descripcion: Optional[str]
    fecha_inicio: Optional[date]
    fecha_fin: Optional[date]
    presupuesto: Optional[Decimal]
    leads_generados: int
    conversiones: int
    ingresos_generados: Decimal
    activa: bool
    # Del detalle de envíos. Se calcula acá y no en la pantalla: si cada
    # pantalla lo dedujera a su manera, dos sitios darían dos tasas de apertura
    # distintas para la misma campaña.
    enviados: int = 0
    abiertos: int = 0
    respondidos: int = 0


@router.get("/campanas", response_model=List[CampanaResponse])
async def listar_campanas(
    activa: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """Las campañas comerciales, con el resultado de sus envíos."""
    q = select(CRMCampana)
    if activa is not None:
        q = q.where(CRMCampana.activa == activa)
    campanas = (await db.execute(
        q.order_by(CRMCampana.fecha_inicio.desc().nullslast()))).scalars().all()

    conteos = {
        cid: (env, ab, resp)
        for cid, env, ab, resp in (await db.execute(
            select(
                CRMCampanaCliente.campana_id,
                func.count().filter(CRMCampanaCliente.enviado.is_(True)),
                func.count().filter(CRMCampanaCliente.abierto.is_(True)),
                func.count().filter(CRMCampanaCliente.respondido.is_(True)),
            ).group_by(CRMCampanaCliente.campana_id))).all()
    }

    salida = []
    for c in campanas:
        env, ab, resp = conteos.get(c.id, (0, 0, 0))
        fila = CampanaResponse.model_validate(c)
        fila.enviados, fila.abiertos, fila.respondidos = env, ab, resp
        salida.append(fila)
    return salida


class CuentaClaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cliente_id: int
    ejecutivo_id: Optional[int]
    objetivo_anual: Optional[Decimal]
    ingreso_actual: Optional[Decimal]
    estrategia: Optional[str]
    proxima_reunion: Optional[date]
    nivel_riesgo: NivelRiesgoClienteEnum
    # Del cliente. Se adjunta para que la pantalla no tenga que cruzar dos
    # listas a mano solo para poder escribir el nombre en una fila.
    cliente: Optional[str] = None
    health_score: Optional[int] = None
    segmento: Optional[str] = None


@router.get("/cuentas-clave", response_model=List[CuentaClaveResponse])
async def listar_cuentas_clave(db: AsyncSession = Depends(get_db)):
    """Las cuentas que se gestionan con plan propio."""
    filas = (await db.execute(
        select(CRMCuentaClave, CRMCliente)
        .join(CRMCliente, CRMCliente.id == CRMCuentaClave.cliente_id)
        .order_by(CRMCuentaClave.objetivo_anual.desc().nullslast()))).all()
    salida = []
    for cuenta, cliente in filas:
        fila = CuentaClaveResponse.model_validate(cuenta)
        fila.cliente = cliente.razon_social
        fila.health_score = cliente.health_score
        fila.segmento = cliente.segmento.value if cliente.segmento else None
        salida.append(fila)
    return salida


class ObjetivoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ejecutivo_id: int
    periodo: str
    tipo_objetivo: str
    meta: Decimal
    logrado: Decimal
    porcentaje: Decimal
    ejecutivo: Optional[str] = None
    region: Optional[str] = None


@router.get("/objetivos", response_model=List[ObjetivoResponse])
async def listar_objetivos(
    periodo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """La meta de cada ejecutivo y cuánto lleva."""
    q = (select(CRMObjetivoComercial, CRMEjecutivoComercial)
         .join(CRMEjecutivoComercial,
               CRMEjecutivoComercial.id == CRMObjetivoComercial.ejecutivo_id))
    if periodo:
        q = q.where(CRMObjetivoComercial.periodo == periodo)
    salida = []
    for obj, ejec in (await db.execute(
            q.order_by(CRMObjetivoComercial.porcentaje.desc()))).all():
        fila = ObjetivoResponse.model_validate(obj)
        fila.ejecutivo = ejec.nombre
        fila.region = ejec.region
        salida.append(fila)
    return salida


class SaludResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cliente_id: int
    fecha_calculo: date
    health_score: int
    score_otif: Optional[int]
    score_tickets: Optional[int]
    score_pagos: Optional[int]
    score_nps: Optional[int]
    score_contratos: Optional[int]
    riesgo_churn: Optional[Decimal]
    prediccion_ia: Optional[str]
    cliente: Optional[str] = None
    ingresos_ytd: Optional[Decimal] = None


@router.get("/salud", response_model=List[SaludResponse])
async def listar_salud(
    en_riesgo: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """El puntaje de salud de cada cliente, con su desglose.

    El desglose es lo que hace útil al puntaje: un número solo dice que el
    cliente está mal, y el desglose dice por dónde —servicio, cobro, entregas—
    que es lo que permite hacer algo al respecto.
    """
    q = (select(CRMSaludCliente, CRMCliente)
         .join(CRMCliente, CRMCliente.id == CRMSaludCliente.cliente_id))
    if en_riesgo:
        q = q.where(CRMSaludCliente.health_score < 60)
    salida = []
    for salud, cliente in (await db.execute(
            q.order_by(CRMSaludCliente.health_score))).all():
        fila = SaludResponse.model_validate(salud)
        fila.cliente = cliente.razon_social
        fila.ingresos_ytd = cliente.ingresos_ytd
        salida.append(fila)
    return salida


class RiesgoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cliente_id: int
    tipo_riesgo: str
    nivel: NivelRiesgoClienteEnum
    descripcion: Optional[str]
    plan_mitigacion: Optional[str]
    activo: bool
    cliente: Optional[str] = None


@router.get("/riesgos", response_model=List[RiesgoResponse])
async def listar_riesgos(db: AsyncSession = Depends(get_db)):
    """Los riesgos abiertos sobre cuentas, con su plan de mitigación."""
    filas = (await db.execute(
        select(CRMRiesgoCliente, CRMCliente)
        .join(CRMCliente, CRMCliente.id == CRMRiesgoCliente.cliente_id)
        .where(CRMRiesgoCliente.activo.is_(True))
        .order_by(CRMRiesgoCliente.nivel.desc()))).all()
    salida = []
    for riesgo, cliente in filas:
        fila = RiesgoResponse.model_validate(riesgo)
        fila.cliente = cliente.razon_social
        salida.append(fila)
    return salida


class ActividadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cliente_id: Optional[int]
    oportunidad_id: Optional[int]
    ticket_id: Optional[int]
    ejecutivo_id: Optional[int]
    tipo: str
    asunto: str
    descripcion: Optional[str]
    fecha_vencimiento: Optional[datetime]
    completada: bool
    prioridad: str
    cliente: Optional[str] = None


@router.get("/actividades", response_model=List[ActividadResponse])
async def listar_actividades(
    pendientes: bool = True,
    ejecutivo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Lo que cada ejecutivo tiene por hacer."""
    q = (select(CRMActividad, CRMCliente)
         .outerjoin(CRMCliente, CRMCliente.id == CRMActividad.cliente_id))
    if pendientes:
        q = q.where(CRMActividad.completada.is_(False))
    if ejecutivo_id:
        q = q.where(CRMActividad.ejecutivo_id == ejecutivo_id)
    salida = []
    for act, cliente in (await db.execute(
            q.order_by(CRMActividad.fecha_vencimiento.asc().nullslast()))).all():
        fila = ActividadResponse.model_validate(act)
        fila.cliente = cliente.razon_social if cliente else None
        salida.append(fila)
    return salida


@router.put("/actividades/{actividad_id}/completar")
async def completar_actividad(actividad_id: int, db: AsyncSession = Depends(get_db)):
    """Marca una tarea como hecha."""
    act = (await db.execute(select(CRMActividad).where(
        CRMActividad.id == actividad_id))).scalar_one_or_none()
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    act.completada = True
    await db.commit()
    return {"id": act.id, "completada": True}


class AlertaComercial(BaseModel):
    nivel: str          # CRITICO | ALTO | MEDIO
    tipo: str
    texto: str
    referencia: Optional[str] = None
    cliente_id: Optional[int] = None


@router.get("/alertas", response_model=List[AlertaComercial])
async def alertas_comerciales(db: AsyncSession = Depends(get_db)):
    """Lo que hay que mirar hoy, con su motivo y su referencia.

    POR QUÉ ESTÁ EN EL SERVIDOR
    Porque si cada pantalla dedujera sus alertas, el tablero y la ficha del
    cliente dirían cosas distintas del mismo contrato. Acá se calculan una vez y
    todas las pantallas ven lo mismo.

    Cada alerta lleva la referencia del documento que la origina. Una alerta que
    dice «hay contratos por vencer» sin decir cuáles obliga a buscarlos a mano,
    y entonces nadie la usa.
    """
    hoy = date.today()
    ahora = datetime.now(timezone.utc)
    cfg = await parametros(db)
    alertas: List[AlertaComercial] = []

    # Contratos por vencer. El plazo lo pone cada empresa: quien negocia con
    # comités trimestrales necesita más aviso que quien renueva por correo.
    limite = hoy + timedelta(days=int(cfg["aviso_renovacion_dias"]))
    for contrato, cliente in (await db.execute(
        select(CRMContrato, CRMCliente)
        .join(CRMCliente, CRMCliente.id == CRMContrato.cliente_id)
        .where(CRMContrato.estado == EstadoContratoEnum.ACTIVO,
               CRMContrato.fecha_fin.isnot(None),
               CRMContrato.fecha_fin <= limite,
               CRMContrato.fecha_fin >= hoy)
        .order_by(CRMContrato.fecha_fin))).all():
        dias = (contrato.fecha_fin - hoy).days
        alertas.append(AlertaComercial(
            nivel="CRITICO" if dias <= cfg["renovacion_critica_dias"] else "ALTO",
            tipo="CONTRATO_POR_VENCER",
            texto=f"El contrato de {cliente.razon_social} vence en {dias} día(s)"
                  f"{' y no tiene renovación automática' if not contrato.auto_renovacion else ''}.",
            referencia=contrato.codigo, cliente_id=cliente.id))

    # Tickets que ya pasaron su fecha límite y siguen sin resolverse.
    for ticket, cliente in (await db.execute(
        select(CRMTicket, CRMCliente)
        .join(CRMCliente, CRMCliente.id == CRMTicket.cliente_id)
        .where(CRMTicket.estado.in_([EstadoTicketEnum.ABIERTO,
                                     EstadoTicketEnum.EN_PROCESO,
                                     EstadoTicketEnum.ESCALADO]),
               CRMTicket.fecha_limite.isnot(None),
               CRMTicket.fecha_limite < ahora)
        .order_by(CRMTicket.fecha_limite))).all():
        horas = int((ahora - ticket.fecha_limite).total_seconds() // 3600)
        alertas.append(AlertaComercial(
            nivel="CRITICO" if ticket.estado == EstadoTicketEnum.ESCALADO else "ALTO",
            tipo="TICKET_VENCIDO",
            texto=f"«{ticket.asunto}» de {cliente.razon_social} lleva {horas} h "
                  f"pasado su plazo de respuesta.",
            referencia=ticket.codigo, cliente_id=cliente.id))

    # Cuentas cuya salud se deterioró. Se toma el cálculo más reciente de cada
    # cliente: mirar todos los históricos repetiría la misma cuenta cada mes.
    ultima = (select(CRMSaludCliente.cliente_id,
                     func.max(CRMSaludCliente.fecha_calculo).label("f"))
              .group_by(CRMSaludCliente.cliente_id).subquery())
    for salud, cliente in (await db.execute(
        select(CRMSaludCliente, CRMCliente)
        .join(ultima, (ultima.c.cliente_id == CRMSaludCliente.cliente_id) &
                      (ultima.c.f == CRMSaludCliente.fecha_calculo))
        .join(CRMCliente, CRMCliente.id == CRMSaludCliente.cliente_id)
        .where(CRMSaludCliente.health_score < cfg["salud_alerta"])
        .order_by(CRMSaludCliente.health_score))).all():
        # El motivo sale del componente más bajo. Decir «salud 62» sin decir por
        # qué deja a quien lo lee sin nada que hacer al respecto.
        componentes = {
            "el servicio": salud.score_tickets,
            "la satisfacción": salud.score_nps,
            "las entregas a tiempo": salud.score_otif,
            "el pago": salud.score_pagos,
        }
        peor = min((v, k) for k, v in componentes.items() if v is not None)
        # Entre crítico y el umbral de alerta queda la franja «alto». Se saca a
        # medio camino en vez de con otro parámetro: dos umbrales ya son
        # bastante que explicarle a quien configura.
        _franja_alta = (cfg["salud_critica"] + cfg["salud_alerta"]) / 2
        alertas.append(AlertaComercial(
            nivel="CRITICO" if salud.health_score < cfg["salud_critica"]
                  else "ALTO" if salud.health_score < _franja_alta else "MEDIO",
            tipo="SALUD_BAJA",
            texto=f"{cliente.razon_social} está en {salud.health_score} de salud; "
                  f"lo peor es {peor[1]} ({peor[0]}).",
            referencia=cliente.codigo, cliente_id=cliente.id))

    # Indicadores pactados que no se están cumpliendo.
    #
    # NO TODOS SE INCUMPLEN HACIA ABAJO. En «OTIF 95%» quedarse corto es la
    # falla; en «responder en 24 horas» la falla es pasarse. Comparar los dos
    # igual marcaba como incumplida una respuesta en 18 horas contra un pacto de
    # 24 —o sea, avisaba de un acuerdo que se estaba cumpliendo de sobra—, y esa
    # clase de aviso es la que enseña a la gente a ignorar el tablero.
    # El sentido se decide por la UNIDAD, no por el nombre del indicador. Buscar
    # palabras en el nombre parece más listo y es más frágil: «Cumplimiento de
    # entregas a tiempo (OTIF)» contiene «tiempo» y quedaba invertido, con lo
    # que un OTIF del 96,7% contra un pacto del 95% se reportaba como
    # incumplido. La unidad no se presta a eso: lo que se mide en horas o en
    # días se cumple quedándose por debajo, y lo que se mide en porcentaje o en
    # unidades se cumple llegando.
    def menor_es_mejor(sla_) -> bool:
        unidad = (sla_.unidad or "").strip().lower()
        return any(unidad.startswith(u) for u in
                   ("hora", "hr", "h", "día", "dia", "d", "minuto", "min",
                    "segundo", "seg", "semana"))

    for sla, contrato, cliente in (await db.execute(
        select(CRMContratoSLA, CRMContrato, CRMCliente)
        .join(CRMContrato, CRMContrato.id == CRMContratoSLA.contrato_id)
        .join(CRMCliente, CRMCliente.id == CRMContrato.cliente_id)
        .where(CRMContratoSLA.activo.is_(True),
               CRMContrato.estado == EstadoContratoEnum.ACTIVO,
               CRMContratoSLA.valor_actual.isnot(None)))).all():
        objetivo, actual = float(sla.objetivo), float(sla.valor_actual)
        brecha = (actual - objetivo) if menor_es_mejor(sla) else (objetivo - actual)
        # Una décima de diferencia no es un incumplimiento: es ruido de medición.
        if brecha < cfg["sla_tolerancia"]:
            continue
        unidad = f" {sla.unidad}" if sla.unidad and sla.unidad != "%" else (sla.unidad or "")
        alertas.append(AlertaComercial(
            nivel="ALTO" if brecha >= cfg["sla_desvio_grave"] else "MEDIO",
            tipo="SLA_INCUMPLIDO",
            texto=f"{sla.indicador} de {cliente.razon_social} está en "
                  f"{actual:g}{unidad} contra {objetivo:g}{unidad} pactado.",
            referencia=contrato.codigo, cliente_id=cliente.id))

    orden = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2}
    alertas.sort(key=lambda a: (orden.get(a.nivel, 3), a.tipo))
    return alertas[:40]


class Recomendacion(BaseModel):
    tipo: str           # AMPLIAR | RENOVAR | RECUPERAR | REACTIVAR | CONVERTIR
    cliente_id: int
    cliente: str
    titulo: str
    razon: str
    potencial: Optional[Decimal] = None
    urgencia: int = 0   # 0 a 100; ordena la lista


@router.get("/recomendaciones", response_model=List[Recomendacion])
async def recomendaciones(db: AsyncSession = Depends(get_db)):
    """Qué conviene hacer con cada cuenta, y por qué.

    NO ES UN MODELO PREDICTIVO. Son reglas explícitas sobre datos que ya están:
    quién factura muy por debajo de su potencial, a quién se le vence el contrato
    sin renovación automática, quién viene con la salud caída, quién quedó sin
    contrato vigente, y qué prospecto lleva tiempo caliente sin que nadie lo
    convierta.

    Se llama así —y no «predicción»— a propósito. Cada línea dice de qué dato
    sale, para que quien la lea pueda discutirla; una recomendación que no se
    puede rebatir no se aplica, se ignora.
    """
    hoy = date.today()
    cfg = await parametros(db)
    salida: List[Recomendacion] = []

    clientes = {c.id: c for c in (await db.execute(
        select(CRMCliente))).scalars().all()}

    contratos = (await db.execute(select(CRMContrato))).scalars().all()
    vigentes: Dict[int, List[CRMContrato]] = {}
    for k in contratos:
        if k.estado == EstadoContratoEnum.ACTIVO:
            vigentes.setdefault(k.cliente_id, []).append(k)

    # ── Ampliar: factura muy por debajo de lo que esa cuenta podría dar ────────
    for cid, ks in vigentes.items():
        cli = clientes.get(cid)
        if cli is None or not cli.potencial_anual:
            continue
        anual = sum((k.valor_mensual or Decimal(0)) for k in ks) * Decimal(12)
        potencial = Decimal(cli.potencial_anual)
        if anual >= potencial * Decimal(str(cfg["ampliar_bajo_potencial"] / 100)):
            continue
        brecha = potencial - anual
        salida.append(Recomendacion(
            tipo="AMPLIAR", cliente_id=cid, cliente=cli.razon_social,
            titulo="Ampliar el alcance del servicio",
            razon=f"Factura {int(anual / 1_000_000)} M al año contra un potencial "
                  f"estimado de {int(potencial / 1_000_000)} M. La diferencia son "
                  f"servicios que hoy contrata en otra parte o no contrata.",
            potencial=brecha.quantize(Decimal("1")),
            urgencia=min(90, int((brecha / potencial) * 100))))

    # ── Renovar: vence pronto y no se renueva solo ────────────────────────────
    for k in contratos:
        if k.estado != EstadoContratoEnum.ACTIVO or not k.fecha_fin:
            continue
        # Se avisa con el doble del plazo configurado: una renovación sin
        # renovación automática hay que empezarla antes que una que se renueva
        # sola y solo se está confirmando.
        dias = (k.fecha_fin - hoy).days
        if not 0 <= dias <= cfg["aviso_renovacion_dias"] * 2 or k.auto_renovacion:
            continue
        cli = clientes.get(k.cliente_id)
        if cli is None:
            continue
        salida.append(Recomendacion(
            tipo="RENOVAR", cliente_id=k.cliente_id, cliente=cli.razon_social,
            titulo=f"Iniciar la renovación de {k.codigo}",
            razon=f"Vence en {dias} día(s) y no tiene renovación automática. "
                  f"Una renovación pasa por el comité del cliente: empezar a "
                  f"treinta días suele ser tarde.",
            potencial=(k.valor_mensual or Decimal(0)) * Decimal(12),
            urgencia=max(50, 100 - dias)))

    # ── Recuperar: la salud viene caída ───────────────────────────────────────
    ultima = (select(CRMSaludCliente.cliente_id,
                     func.max(CRMSaludCliente.fecha_calculo).label("f"))
              .group_by(CRMSaludCliente.cliente_id).subquery())
    for salud in (await db.execute(
        select(CRMSaludCliente)
        .join(ultima, (ultima.c.cliente_id == CRMSaludCliente.cliente_id) &
                      (ultima.c.f == CRMSaludCliente.fecha_calculo))
        .where(CRMSaludCliente.health_score < cfg["salud_alerta"]))).scalars().all():
        cli = clientes.get(salud.cliente_id)
        if cli is None:
            continue
        componentes = {
            "el servicio": salud.score_tickets,
            "la satisfacción": salud.score_nps,
            "las entregas a tiempo": salud.score_otif,
            "el pago": salud.score_pagos,
        }
        peor = min((v, k) for k, v in componentes.items() if v is not None)
        anual = sum((k.valor_mensual or Decimal(0))
                    for k in vigentes.get(salud.cliente_id, [])) * Decimal(12)
        salida.append(Recomendacion(
            tipo="RECUPERAR", cliente_id=salud.cliente_id, cliente=cli.razon_social,
            titulo="Plan de recuperación antes de la renovación",
            razon=f"Salud en {salud.health_score}; lo más bajo es {peor[1]} "
                  f"({peor[0]}). Es lo que hay que arreglar primero, y hay que "
                  f"hacerlo antes de sentarse a renovar.",
            potencial=anual.quantize(Decimal("1")),
            urgencia=min(95, 100 - salud.health_score)))

    # ── Reactivar: fue cliente y ya no tiene contrato vigente ─────────────────
    for cid, cli in clientes.items():
        if cid in vigentes:
            continue
        suyos = [k for k in contratos if k.cliente_id == cid]
        if not suyos:
            continue
        ultimo = max(suyos, key=lambda k: k.fecha_fin or date.min)
        if not ultimo.fecha_fin:
            continue
        dias = (hoy - ultimo.fecha_fin).days
        if dias < 0 or dias > cfg["reactivar_dias_max"]:
            continue
        salida.append(Recomendacion(
            tipo="REACTIVAR", cliente_id=cid, cliente=cli.razon_social,
            titulo="Volver a tocar la puerta",
            razon=f"Fue cliente y su último contrato terminó hace {dias} día(s). "
                  f"Conoce la operación y no hay que empezar de cero.",
            potencial=(ultimo.valor_mensual or Decimal(0)) * Decimal(12),
            urgencia=max(25, 60 - dias // 10)))

    # ── Convertir: prospecto caliente que nadie ha movido ─────────────────────
    for lead in (await db.execute(
        select(CRMLead).where(CRMLead.estado == EstadoLeadEnum.CALIENTE,
                              CRMLead.convertido.is_(False)))).scalars().all():
        if lead.cliente_id is None:
            continue
        cli = clientes.get(lead.cliente_id)
        if cli is None:
            continue
        salida.append(Recomendacion(
            tipo="CONVERTIR", cliente_id=lead.cliente_id, cliente=cli.razon_social,
            titulo=f"Abrir oportunidad desde {lead.codigo}",
            razon=f"Prospecto con puntaje {lead.score} que entró por «"
                  f"{lead.fuente or 'canal sin registrar'}» y sigue sin "
                  f"convertirse en oportunidad.",
            potencial=lead.potencial, urgencia=min(85, lead.score)))

    salida.sort(key=lambda r: -r.urgencia)
    return salida[:60]


# ══════════════════════════════════════════════════════════════════════════════
# Los umbrales configurables
#
# Cada uno tiene un valor por defecto razonable y una explicación de qué cambia
# al moverlo. La explicación no es adorno: un umbral que nadie entiende no se
# toca, y entonces da lo mismo que sea configurable.
# ══════════════════════════════════════════════════════════════════════════════

PARAMETROS_CRM = [
    {
        "clave": "aviso_renovacion_dias",
        "nombre": "Avisar de una renovación con",
        "unidad": "días",
        "defecto": 45,
        "minimo": 7, "maximo": 180,
        "explica": "A cuántos días del vencimiento aparece la alerta de "
                   "renovación. Si su cliente decide en comité trimestral, "
                   "cuarenta y cinco días es lo mínimo; si renueva por correo, "
                   "quince alcanzan.",
    },
    {
        "clave": "renovacion_critica_dias",
        "nombre": "Marcar la renovación como crítica a",
        "unidad": "días",
        "defecto": 15,
        "minimo": 3, "maximo": 60,
        "explica": "Por debajo de este plazo la alerta pasa de alta a crítica. "
                   "Debe ser menor que el aviso de renovación.",
    },
    {
        "clave": "salud_alerta",
        "nombre": "Encender alerta de cuenta cuando la salud baje de",
        "unidad": "puntos",
        "defecto": 70,
        "minimo": 30, "maximo": 90,
        "explica": "Umbral a partir del cual una cuenta con contrato aparece en "
                   "las alertas y en las recomendaciones de recuperación. Subirlo "
                   "avisa antes y con más ruido; bajarlo avisa tarde.",
    },
    {
        "clave": "salud_critica",
        "nombre": "Considerar la cuenta crítica por debajo de",
        "unidad": "puntos",
        "defecto": 50,
        "minimo": 10, "maximo": 70,
        "explica": "Por debajo de este puntaje la alerta de la cuenta pasa a "
                   "crítica. Debe ser menor que el umbral de alerta.",
    },
    {
        "clave": "sla_tolerancia",
        "nombre": "Ignorar desvíos de indicador menores a",
        "unidad": "puntos",
        "defecto": 1,
        "minimo": 0, "maximo": 10,
        "explica": "Diferencia que se considera ruido de medición y no "
                   "incumplimiento. Ponerlo en cero hace sonar la alarma por una "
                   "décima, y eso entrena a la gente a cerrar el tablero sin leerlo.",
    },
    {
        "clave": "sla_desvio_grave",
        "nombre": "Tratar el incumplimiento como grave desde",
        "unidad": "puntos",
        "defecto": 5,
        "minimo": 1, "maximo": 30,
        "explica": "Desde esta diferencia contra lo pactado, la alerta del "
                   "indicador pasa de media a alta.",
    },
    {
        "clave": "ampliar_bajo_potencial",
        "nombre": "Sugerir ampliar cuando el cliente facture menos del",
        "unidad": "%",
        "defecto": 65,
        "minimo": 20, "maximo": 95,
        "explica": "Porcentaje de su potencial estimado por debajo del cual la "
                   "cuenta aparece como oportunidad de ampliación.",
    },
    {
        "clave": "reactivar_dias_max",
        "nombre": "Dejar de sugerir reactivar después de",
        "unidad": "días",
        "defecto": 540,
        "minimo": 90, "maximo": 1460,
        "explica": "Cuánto tiempo después de terminar un contrato sigue teniendo "
                   "sentido volver a tocar la puerta. Pasado ese plazo el cliente "
                   "ya rehízo su operación y no es una reactivación, es una venta "
                   "nueva.",
    },
]

_POR_CLAVE = {p["clave"]: p for p in PARAMETROS_CRM}


async def parametros(db: AsyncSession) -> Dict[str, float]:
    """Los umbrales en uso: lo guardado, y el valor por defecto para el resto.

    Devuelve siempre las ocho claves. Que el módulo tenga que preguntarse si un
    umbral existe es lo que produce los `None` que revientan una comparación tres
    funciones más abajo.
    """
    guardados = {
        p.clave: float(p.valor)
        for p in (await db.execute(select(CRMParametro))).scalars().all()
    }
    return {p["clave"]: guardados.get(p["clave"], float(p["defecto"]))
            for p in PARAMETROS_CRM}


class ParametroResponse(BaseModel):
    clave: str
    nombre: str
    unidad: str
    valor: float
    defecto: float
    minimo: float
    maximo: float
    explica: str
    personalizado: bool


@router.get("/parametros", response_model=List[ParametroResponse])
async def listar_parametros(db: AsyncSession = Depends(get_db)):
    """Los umbrales con los que trabaja el módulo, y qué cambia cada uno."""
    guardados = {
        p.clave: float(p.valor)
        for p in (await db.execute(select(CRMParametro))).scalars().all()
    }
    return [
        ParametroResponse(
            clave=p["clave"], nombre=p["nombre"], unidad=p["unidad"],
            valor=guardados.get(p["clave"], float(p["defecto"])),
            defecto=float(p["defecto"]),
            minimo=float(p["minimo"]), maximo=float(p["maximo"]),
            explica=p["explica"],
            personalizado=p["clave"] in guardados,
        )
        for p in PARAMETROS_CRM
    ]


class GuardarParametro(BaseModel):
    valor: float


@router.put("/parametros/{clave}", response_model=ParametroResponse)
async def guardar_parametro(
    clave: str, datos: GuardarParametro, db: AsyncSession = Depends(get_db),
):
    """Cambia un umbral. Empieza a aplicarse en la siguiente consulta.

    Se valida contra el rango declarado. Un umbral de salud en 300 no rompe nada
    visible: simplemente deja de avisar de todo, y nadie relaciona el silencio
    con el número que alguien tecleó hace un mes.
    """
    definicion = _POR_CLAVE.get(clave)
    if definicion is None:
        raise HTTPException(404, "Ese parámetro no existe.")
    if not definicion["minimo"] <= datos.valor <= definicion["maximo"]:
        raise HTTPException(
            422, f"«{definicion['nombre']}» tiene que estar entre "
                 f"{definicion['minimo']} y {definicion['maximo']} "
                 f"{definicion['unidad']}.")

    fila = (await db.execute(select(CRMParametro).where(
        CRMParametro.clave == clave))).scalar_one_or_none()
    if fila is None:
        fila = CRMParametro(clave=clave, valor=Decimal(str(datos.valor)))
        db.add(fila)
    else:
        fila.valor = Decimal(str(datos.valor))
    await db.commit()

    return ParametroResponse(
        clave=clave, nombre=definicion["nombre"], unidad=definicion["unidad"],
        valor=datos.valor, defecto=float(definicion["defecto"]),
        minimo=float(definicion["minimo"]), maximo=float(definicion["maximo"]),
        explica=definicion["explica"], personalizado=True)


@router.delete("/parametros/{clave}", response_model=ParametroResponse)
async def restaurar_parametro(clave: str, db: AsyncSession = Depends(get_db)):
    """Vuelve el umbral a su valor por defecto."""
    definicion = _POR_CLAVE.get(clave)
    if definicion is None:
        raise HTTPException(404, "Ese parámetro no existe.")
    fila = (await db.execute(select(CRMParametro).where(
        CRMParametro.clave == clave))).scalar_one_or_none()
    if fila is not None:
        await db.delete(fila)
        await db.commit()
    return ParametroResponse(
        clave=clave, nombre=definicion["nombre"], unidad=definicion["unidad"],
        valor=float(definicion["defecto"]), defecto=float(definicion["defecto"]),
        minimo=float(definicion["minimo"]), maximo=float(definicion["maximo"]),
        explica=definicion["explica"], personalizado=False)


# ══════════════════════════════════════════════════════════════════════════════
# Editar y eliminar
#
# El módulo nació pudiendo crear y consultar, pero no corregir ni deshacer, y un
# módulo donde un error de digitación es permanente no se usa: la gente monta su
# hoja de cálculo al lado.
#
# BORRAR NO ARRASTRA. Ningún borrado se lleva por delante lo que cuelga de él.
# Si un cliente tiene contratos, el borrado se niega y dice cuántos: perder un
# año de historia comercial por un clic es exactamente lo que no puede pasar.
# Para el cliente que ya no opera está «desactivar», que lo saca de las listas y
# conserva lo suyo.
# ══════════════════════════════════════════════════════════════════════════════

async def _obtener(db: AsyncSession, modelo, id_: int, que: str):
    obj = await db.get(modelo, id_)
    if obj is None:
        raise HTTPException(404, f"{que} no existe o ya fue eliminado.")
    return obj


async def _aplicar(db: AsyncSession, obj, datos: BaseModel):
    """Escribe solo lo que vino en el cuerpo.

    `exclude_unset` es lo que hace que la pantalla pueda mandar un campo suelto
    sin pisar los demás con nulos. Sin eso, editar el teléfono de un cliente le
    borraría la dirección.
    """
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(obj, campo, valor)
    await db.commit()
    await db.refresh(obj)
    return obj


async def _cuantos(db: AsyncSession, modelo, **filtros) -> int:
    q = select(func.count()).select_from(modelo)
    for campo, valor in filtros.items():
        q = q.where(getattr(modelo, campo) == valor)
    return (await db.execute(q)).scalar_one()


# El singular de cada cosa que puede impedir un borrado. Quitarle la ese al
# plural produce «1 oportunidade», y un mensaje mal escrito le resta credibilidad
# justo cuando está explicando por qué no dejó hacer algo.
_SINGULAR = {
    "clientes asignados": "cliente asignado",
    "oportunidades": "una oportunidad",
    "contratos": "un contrato",
    "cotizaciones": "una cotización",
    "tickets": "un ticket",
    "tickets asociados": "un ticket asociado",
}


async def _impedir_si_tiene(db: AsyncSession, dependientes: list) -> None:
    """Niega el borrado nombrando qué lo impide, y cuánto.

    Decir «no se puede eliminar» sin decir por qué deja a quien lo intenta sin
    nada que hacer salvo volver a intentarlo.
    """
    trabas = []
    for modelo, campo, valor, nombre in dependientes:
        n = await _cuantos(db, modelo, **{campo: valor})
        if n:
            trabas.append(f"{n} {nombre}" if n > 1
                          else _SINGULAR.get(nombre, f"1 {nombre}"))
    if trabas:
        raise HTTPException(
            409, "No se puede eliminar porque tiene " + ", ".join(trabas) +
                 ". Elimine eso primero, o desactívelo para sacarlo de las "
                 "listas conservando su historia.")


# ── Ejecutivos ────────────────────────────────────────────────────────────────

class EjecutivoEdicion(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    region: Optional[str] = None
    meta_anual: Optional[Decimal] = None
    activo: Optional[bool] = None


@router.put("/ejecutivos/{id}", response_model=EjecutivoResponse)
async def editar_ejecutivo(id: int, datos: EjecutivoEdicion,
                           db: AsyncSession = Depends(get_db)):
    return await _aplicar(db, await _obtener(db, CRMEjecutivoComercial, id,
                                             "Ese ejecutivo"), datos)


@router.delete("/ejecutivos/{id}", status_code=204)
async def eliminar_ejecutivo(id: int, db: AsyncSession = Depends(get_db)):
    """Se niega si tiene cartera: quedaría gente sin responsable y sin aviso."""
    ejec = await _obtener(db, CRMEjecutivoComercial, id, "Ese ejecutivo")
    await _impedir_si_tiene(db, [
        (CRMCliente, "ejecutivo_id", id, "clientes asignados"),
        (CRMOportunidad, "ejecutivo_id", id, "oportunidades"),
        (CRMContrato, "ejecutivo_id", id, "contratos"),
    ])
    await db.delete(ejec)
    await db.commit()


# ── Clientes ──────────────────────────────────────────────────────────────────

@router.delete("/clientes/{id}", status_code=204)
async def eliminar_cliente(id: int, db: AsyncSession = Depends(get_db)):
    cliente = await _obtener(db, CRMCliente, id, "Ese cliente")
    await _impedir_si_tiene(db, [
        (CRMContrato, "cliente_id", id, "contratos"),
        (CRMTicket, "cliente_id", id, "tickets"),
        (CRMOportunidad, "cliente_id", id, "oportunidades"),
        (CRMCotizacion, "cliente_id", id, "cotizaciones"),
    ])
    # Lo que sí se lleva son sus propios anexos, que fuera de él no significan
    # nada: un contacto sin cliente, una interacción sin cuenta.
    for modelo in (CRMContacto, CRMInteraccion, CRMEncuesta,
                   CRMRiesgoCliente, CRMSaludCliente, CRMCuentaClave,
                   CRMActividad, CRMCampanaCliente, CRMLead):
        for fila in (await db.execute(select(modelo).where(
                modelo.cliente_id == id))).scalars().all():
            await db.delete(fila)
    await db.delete(cliente)
    await db.commit()


# ── Contactos ─────────────────────────────────────────────────────────────────

class ContactoEdicion(BaseModel):
    nombre: Optional[str] = None
    cargo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    whatsapp: Optional[str] = None
    linkedin: Optional[str] = None
    es_decisor: Optional[bool] = None
    es_principal: Optional[bool] = None
    activo: Optional[bool] = None


@router.put("/contactos/{id}", response_model=ContactoResponse)
async def editar_contacto(id: int, datos: ContactoEdicion,
                          db: AsyncSession = Depends(get_db)):
    return await _aplicar(db, await _obtener(db, CRMContacto, id,
                                             "Ese contacto"), datos)


@router.delete("/contactos/{id}", status_code=204)
async def eliminar_contacto(id: int, db: AsyncSession = Depends(get_db)):
    await db.delete(await _obtener(db, CRMContacto, id, "Ese contacto"))
    await db.commit()


# ── Prospectos ────────────────────────────────────────────────────────────────

@router.delete("/leads/{id}", status_code=204)
async def eliminar_lead(id: int, db: AsyncSession = Depends(get_db)):
    lead = await _obtener(db, CRMLead, id, "Ese prospecto")
    await _impedir_si_tiene(db, [
        (CRMOportunidad, "lead_id", id, "oportunidades"),
    ])
    await db.delete(lead)
    await db.commit()


# ── Oportunidades ─────────────────────────────────────────────────────────────

class OportunidadEdicion(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    ejecutivo_id: Optional[int] = None
    valor_estimado: Optional[Decimal] = None
    servicio: Optional[str] = None
    fecha_esperada: Optional[date] = None
    probabilidad: Optional[int] = None


@router.put("/oportunidades/{id}", response_model=OportunidadResponse)
async def editar_oportunidad(id: int, datos: OportunidadEdicion,
                             db: AsyncSession = Depends(get_db)):
    return await _aplicar(db, await _obtener(db, CRMOportunidad, id,
                                             "Esa oportunidad"), datos)


@router.delete("/oportunidades/{id}", status_code=204)
async def eliminar_oportunidad(id: int, db: AsyncSession = Depends(get_db)):
    opo = await _obtener(db, CRMOportunidad, id, "Esa oportunidad")
    await _impedir_si_tiene(db, [
        (CRMContrato, "oportunidad_id", id, "contratos"),
        (CRMCotizacion, "oportunidad_id", id, "cotizaciones"),
    ])
    await db.delete(opo)
    await db.commit()


# ── Cotizaciones ──────────────────────────────────────────────────────────────

class CotizacionEdicion(BaseModel):
    estado: Optional[EstadoCotizacionEnum] = None
    validez_dias: Optional[int] = None
    notas: Optional[str] = None
    fecha_envio: Optional[date] = None
    fecha_vencimiento: Optional[date] = None


@router.put("/cotizaciones/{id}", response_model=CotizacionResponse)
async def editar_cotizacion(id: int, datos: CotizacionEdicion,
                            db: AsyncSession = Depends(get_db)):
    return await _aplicar(db, await _obtener(db, CRMCotizacion, id,
                                             "Esa cotización"), datos)


@router.delete("/cotizaciones/{id}", status_code=204)
async def eliminar_cotizacion(id: int, db: AsyncSession = Depends(get_db)):
    cot = await _obtener(db, CRMCotizacion, id, "Esa cotización")
    await _impedir_si_tiene(db, [
        (CRMContrato, "oportunidad_id", cot.oportunidad_id or -1, "contratos"),
    ])
    for item in (await db.execute(select(CRMCotizacionItem).where(
            CRMCotizacionItem.cotizacion_id == id))).scalars().all():
        await db.delete(item)
    await db.delete(cot)
    await db.commit()


# ── Contratos ─────────────────────────────────────────────────────────────────

@router.delete("/contratos/{id}", status_code=204)
async def eliminar_contrato(id: int, db: AsyncSession = Depends(get_db)):
    contrato = await _obtener(db, CRMContrato, id, "Ese contrato")
    await _impedir_si_tiene(db, [
        (CRMTicket, "contrato_id", id, "tickets asociados"),
    ])
    for sla in (await db.execute(select(CRMContratoSLA).where(
            CRMContratoSLA.contrato_id == id))).scalars().all():
        await db.delete(sla)
    await db.delete(contrato)
    await db.commit()


class SLAEntrada(BaseModel):
    indicador: str
    objetivo: Decimal
    unidad: Optional[str] = None
    valor_actual: Optional[Decimal] = None
    penalizacion: Optional[str] = None
    frecuencia_medicion: Optional[str] = None


@router.post("/contratos/{id}/sla", response_model=SLAResponse, status_code=201)
async def crear_sla(id: int, datos: SLAEntrada,
                    db: AsyncSession = Depends(get_db)):
    """Pacta un indicador nuevo en un contrato."""
    await _obtener(db, CRMContrato, id, "Ese contrato")
    sla = CRMContratoSLA(contrato_id=id, activo=True, **datos.model_dump())
    db.add(sla)
    await db.commit()
    await db.refresh(sla)
    return sla


class SLAEdicion(BaseModel):
    indicador: Optional[str] = None
    objetivo: Optional[Decimal] = None
    unidad: Optional[str] = None
    valor_actual: Optional[Decimal] = None
    penalizacion: Optional[str] = None
    frecuencia_medicion: Optional[str] = None
    activo: Optional[bool] = None


@router.put("/sla/{id}", response_model=SLAResponse)
async def editar_sla(id: int, datos: SLAEdicion,
                     db: AsyncSession = Depends(get_db)):
    return await _aplicar(db, await _obtener(db, CRMContratoSLA, id,
                                             "Ese indicador"), datos)


@router.delete("/sla/{id}", status_code=204)
async def eliminar_sla(id: int, db: AsyncSession = Depends(get_db)):
    await db.delete(await _obtener(db, CRMContratoSLA, id, "Ese indicador"))
    await db.commit()


# ── Tickets ───────────────────────────────────────────────────────────────────

class TicketEdicion(BaseModel):
    asunto: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[TipoTicketEnum] = None
    prioridad: Optional[str] = None
    canal: Optional[str] = None
    ejecutivo_id: Optional[int] = None
    contrato_id: Optional[int] = None
    fecha_limite: Optional[datetime] = None
    satisfaccion: Optional[int] = None


@router.put("/tickets/{id}", response_model=TicketResponse)
async def editar_ticket(id: int, datos: TicketEdicion,
                        db: AsyncSession = Depends(get_db)):
    if datos.satisfaccion is not None and not 1 <= datos.satisfaccion <= 5:
        raise HTTPException(422, "La satisfacción va de 1 a 5.")
    return await _aplicar(db, await _obtener(db, CRMTicket, id,
                                             "Ese ticket"), datos)


@router.delete("/tickets/{id}", status_code=204)
async def eliminar_ticket(id: int, db: AsyncSession = Depends(get_db)):
    ticket = await _obtener(db, CRMTicket, id, "Ese ticket")
    # Las interacciones y la encuesta de un ticket no significan nada sin él.
    for modelo in (CRMInteraccion, CRMEncuesta):
        for fila in (await db.execute(select(modelo).where(
                modelo.ticket_id == id))).scalars().all():
            await db.delete(fila)
    await db.delete(ticket)
    await db.commit()


# ── Interacciones ─────────────────────────────────────────────────────────────

class InteraccionEdicion(BaseModel):
    tipo: Optional[TipoInteraccionEnum] = None
    asunto: Optional[str] = None
    descripcion: Optional[str] = None
    duracion_min: Optional[int] = None
    resultado: Optional[str] = None
    proximo_paso: Optional[str] = None
    fecha_interaccion: Optional[datetime] = None


@router.put("/interacciones/{id}", response_model=InteraccionResponse)
async def editar_interaccion(id: int, datos: InteraccionEdicion,
                             db: AsyncSession = Depends(get_db)):
    return await _aplicar(db, await _obtener(db, CRMInteraccion, id,
                                             "Ese contacto"), datos)


@router.delete("/interacciones/{id}", status_code=204)
async def eliminar_interaccion(id: int, db: AsyncSession = Depends(get_db)):
    await db.delete(await _obtener(db, CRMInteraccion, id, "Ese contacto"))
    await db.commit()


# ── Encuestas ─────────────────────────────────────────────────────────────────

class EncuestaEdicion(BaseModel):
    puntaje: Optional[int] = None
    comentario: Optional[str] = None
    respondida: Optional[bool] = None
    fecha_respuesta: Optional[date] = None


@router.put("/encuestas/{id}", response_model=EncuestaResponse)
async def editar_encuesta(id: int, datos: EncuestaEdicion,
                          db: AsyncSession = Depends(get_db)):
    """Registra la respuesta de una encuesta.

    El máximo depende de la escala: el NPS llega a diez y el CSAT a cinco.
    Aceptar un ocho en un CSAT metería en el promedio un valor imposible y
    nadie volvería a poder explicar la cifra.
    """
    enc = await _obtener(db, CRMEncuesta, id, "Esa encuesta")
    if datos.puntaje is not None:
        tope = 10 if enc.tipo == TipoEncuestaEnum.NPS else 5
        if not 0 <= datos.puntaje <= tope:
            raise HTTPException(
                422, f"En una encuesta {enc.tipo.value} el puntaje va de 0 a {tope}.")
        # Registrar un puntaje es responderla: dejarla como «sin responder» con
        # nota puesta la deja fuera del NPS, que solo cuenta las respondidas.
        if datos.respondida is None:
            enc.respondida = True
        if datos.fecha_respuesta is None and enc.fecha_respuesta is None:
            enc.fecha_respuesta = date.today()
    return await _aplicar(db, enc, datos)


@router.delete("/encuestas/{id}", status_code=204)
async def eliminar_encuesta(id: int, db: AsyncSession = Depends(get_db)):
    await db.delete(await _obtener(db, CRMEncuesta, id, "Esa encuesta"))
    await db.commit()


# ── Campañas ──────────────────────────────────────────────────────────────────

class CampanaEntrada(BaseModel):
    codigo: str
    nombre: str
    tipo: TipoCampanaEnum
    descripcion: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    presupuesto: Optional[Decimal] = None
    activa: bool = True


@router.post("/campanas", response_model=CampanaResponse, status_code=201)
async def crear_campana(datos: CampanaEntrada, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(CRMCampana).where(
            CRMCampana.codigo == datos.codigo))).scalar_one_or_none():
        raise HTTPException(409, f"Ya existe una campaña con el código {datos.codigo}.")
    campana = CRMCampana(**datos.model_dump())
    db.add(campana)
    await db.commit()
    await db.refresh(campana)
    return CampanaResponse.model_validate(campana)


class CampanaEdicion(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[TipoCampanaEnum] = None
    descripcion: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    presupuesto: Optional[Decimal] = None
    activa: Optional[bool] = None


@router.put("/campanas/{id}", response_model=CampanaResponse)
async def editar_campana(id: int, datos: CampanaEdicion,
                         db: AsyncSession = Depends(get_db)):
    campana = await _aplicar(db, await _obtener(db, CRMCampana, id,
                                                "Esa campaña"), datos)
    return CampanaResponse.model_validate(campana)


@router.delete("/campanas/{id}", status_code=204)
async def eliminar_campana(id: int, db: AsyncSession = Depends(get_db)):
    campana = await _obtener(db, CRMCampana, id, "Esa campaña")
    for fila in (await db.execute(select(CRMCampanaCliente).where(
            CRMCampanaCliente.campana_id == id))).scalars().all():
        await db.delete(fila)
    await db.delete(campana)
    await db.commit()


# ── Cuentas clave ─────────────────────────────────────────────────────────────

class CuentaClaveEntrada(BaseModel):
    cliente_id: int
    ejecutivo_id: Optional[int] = None
    objetivo_anual: Optional[Decimal] = None
    ingreso_actual: Optional[Decimal] = None
    estrategia: Optional[str] = None
    proxima_reunion: Optional[date] = None
    nivel_riesgo: NivelRiesgoClienteEnum = NivelRiesgoClienteEnum.BAJO


@router.post("/cuentas-clave", response_model=CuentaClaveResponse, status_code=201)
async def crear_cuenta_clave(datos: CuentaClaveEntrada,
                             db: AsyncSession = Depends(get_db)):
    cliente = await _obtener(db, CRMCliente, datos.cliente_id, "Ese cliente")
    if (await db.execute(select(CRMCuentaClave).where(
            CRMCuentaClave.cliente_id == datos.cliente_id))).scalar_one_or_none():
        raise HTTPException(
            409, f"{cliente.razon_social} ya está declarada como cuenta clave.")
    cuenta = CRMCuentaClave(**datos.model_dump())
    db.add(cuenta)
    await db.commit()
    await db.refresh(cuenta)
    fila = CuentaClaveResponse.model_validate(cuenta)
    fila.cliente = cliente.razon_social
    fila.health_score = cliente.health_score
    return fila


class CuentaClaveEdicion(BaseModel):
    ejecutivo_id: Optional[int] = None
    objetivo_anual: Optional[Decimal] = None
    ingreso_actual: Optional[Decimal] = None
    estrategia: Optional[str] = None
    proxima_reunion: Optional[date] = None
    nivel_riesgo: Optional[NivelRiesgoClienteEnum] = None


@router.put("/cuentas-clave/{id}", response_model=CuentaClaveResponse)
async def editar_cuenta_clave(id: int, datos: CuentaClaveEdicion,
                              db: AsyncSession = Depends(get_db)):
    cuenta = await _aplicar(db, await _obtener(db, CRMCuentaClave, id,
                                               "Esa cuenta clave"), datos)
    cliente = await db.get(CRMCliente, cuenta.cliente_id)
    fila = CuentaClaveResponse.model_validate(cuenta)
    if cliente:
        fila.cliente = cliente.razon_social
        fila.health_score = cliente.health_score
    return fila


@router.delete("/cuentas-clave/{id}", status_code=204)
async def eliminar_cuenta_clave(id: int, db: AsyncSession = Depends(get_db)):
    """Deja de gestionarla con plan propio. El cliente sigue igual."""
    await db.delete(await _obtener(db, CRMCuentaClave, id, "Esa cuenta clave"))
    await db.commit()


# ── Riesgos de cuenta ─────────────────────────────────────────────────────────

class RiesgoEntrada(BaseModel):
    cliente_id: int
    tipo_riesgo: str
    nivel: NivelRiesgoClienteEnum = NivelRiesgoClienteEnum.MEDIO
    descripcion: Optional[str] = None
    plan_mitigacion: Optional[str] = None


@router.post("/riesgos", response_model=RiesgoResponse, status_code=201)
async def crear_riesgo(datos: RiesgoEntrada, db: AsyncSession = Depends(get_db)):
    cliente = await _obtener(db, CRMCliente, datos.cliente_id, "Ese cliente")
    riesgo = CRMRiesgoCliente(activo=True, **datos.model_dump())
    db.add(riesgo)
    await db.commit()
    await db.refresh(riesgo)
    fila = RiesgoResponse.model_validate(riesgo)
    fila.cliente = cliente.razon_social
    return fila


class RiesgoEdicion(BaseModel):
    tipo_riesgo: Optional[str] = None
    nivel: Optional[NivelRiesgoClienteEnum] = None
    descripcion: Optional[str] = None
    plan_mitigacion: Optional[str] = None
    activo: Optional[bool] = None


@router.put("/riesgos/{id}", response_model=RiesgoResponse)
async def editar_riesgo(id: int, datos: RiesgoEdicion,
                        db: AsyncSession = Depends(get_db)):
    riesgo = await _aplicar(db, await _obtener(db, CRMRiesgoCliente, id,
                                               "Ese riesgo"), datos)
    cliente = await db.get(CRMCliente, riesgo.cliente_id)
    fila = RiesgoResponse.model_validate(riesgo)
    if cliente:
        fila.cliente = cliente.razon_social
    return fila


@router.delete("/riesgos/{id}", status_code=204)
async def eliminar_riesgo(id: int, db: AsyncSession = Depends(get_db)):
    await db.delete(await _obtener(db, CRMRiesgoCliente, id, "Ese riesgo"))
    await db.commit()


# ── Actividades ───────────────────────────────────────────────────────────────

class ActividadEntrada(BaseModel):
    asunto: str
    tipo: str = "LLAMADA"
    cliente_id: Optional[int] = None
    oportunidad_id: Optional[int] = None
    ejecutivo_id: Optional[int] = None
    descripcion: Optional[str] = None
    fecha_vencimiento: Optional[datetime] = None
    prioridad: str = "MEDIA"


@router.post("/actividades", response_model=ActividadResponse, status_code=201)
async def crear_actividad(datos: ActividadEntrada,
                          db: AsyncSession = Depends(get_db)):
    act = CRMActividad(completada=False, **datos.model_dump())
    db.add(act)
    await db.commit()
    await db.refresh(act)
    fila = ActividadResponse.model_validate(act)
    if act.cliente_id:
        cliente = await db.get(CRMCliente, act.cliente_id)
        fila.cliente = cliente.razon_social if cliente else None
    return fila


@router.delete("/actividades/{id}", status_code=204)
async def eliminar_actividad(id: int, db: AsyncSession = Depends(get_db)):
    await db.delete(await _obtener(db, CRMActividad, id, "Esa tarea"))
    await db.commit()
