"""
La relación comercial con cada empresa: qué contrató, qué paga, quién es.

Va aparte de `plataforma.py` porque son dos cosas distintas: aquel administra
el **acceso** —quién entra y con qué credenciales— y este el **negocio**. Los
dos cuelgan del mismo prefijo y de la misma guardia de operador.

Todo esto vive en el esquema `public`: es información del operador sobre el
cliente, no del cliente, y guardarla dentro de su esquema la dejaría a la vista
de la propia empresa.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import acceso_modulos
from app.core.database import get_db_plataforma
from app.core.modulos import MODULOS, ESENCIALES
from app.infrastructure.models.plataforma import (
    PlataformaContrato, PlataformaModuloCliente, PlataformaContacto,
    PlataformaDocumento, PlataformaPago,
)
from app.core.permisos_consola import exigir
from app.api.v1.endpoints.plataforma import _anotar, _empresa, _sesion_de

router = APIRouter(prefix="/plataforma", tags=["Consola del operador"])


# ─── Contrato ─────────────────────────────────────────────────────────────────

class Contrato(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tarifa_mensual: Decimal = Decimal(0)
    moneda: str = "COP"
    iva_pct: Decimal = Decimal(19)
    dia_corte: int = 1
    inicio: Optional[date] = None
    fin: Optional[date] = None
    notas: Optional[str] = None


async def _contrato_de(db: AsyncSession, cliente_id: int) -> PlataformaContrato:
    """El contrato de la empresa; se crea vacío la primera vez que se consulta.

    Así la consola nunca tiene que distinguir entre «no tiene contrato» y
    «tiene uno en ceros», que para el operador son lo mismo.
    """
    r = await db.execute(
        select(PlataformaContrato).where(PlataformaContrato.cliente_id == cliente_id))
    c = r.scalar_one_or_none()
    if not c:
        c = PlataformaContrato(cliente_id=cliente_id)
        db.add(c)
        await db.flush()
    return c


@router.get("/empresas/{cliente_id}/contrato", response_model=Contrato)
async def ver_contrato(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.ver")),
):
    await _empresa(db, cliente_id)
    c = await _contrato_de(db, cliente_id)
    await db.commit()
    return Contrato.model_validate(c)


@router.put("/empresas/{cliente_id}/contrato", response_model=Contrato)
async def guardar_contrato(
    cliente_id: int, data: Contrato, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.editar")),
):
    empresa = await _empresa(db, cliente_id)
    c = await _contrato_de(db, cliente_id)
    if data.dia_corte is not None and not (1 <= data.dia_corte <= 28):
        raise HTTPException(
            400,
            "El día de corte debe estar entre 1 y 28: febrero no tiene 30 ni 31, "
            "y un corte el 31 se saltaría meses.",
        )
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(c, campo, valor)
    await _anotar(db, request, "contrato.edicion", empresa.codigo,
                  f"tarifa {c.tarifa_mensual} {c.moneda}")
    await db.commit(); await db.refresh(c)
    return Contrato.model_validate(c)


# ─── Módulos contratados ──────────────────────────────────────────────────────

class ModuloContratado(BaseModel):
    clave: str
    nombre: str
    activo: bool
    esencial: bool


async def _modulos(db: AsyncSession, cliente_id: int) -> List[ModuloContratado]:
    r = await db.execute(select(PlataformaModuloCliente).where(
        PlataformaModuloCliente.cliente_id == cliente_id))
    filas = {m.modulo: m for m in r.scalars().all()}
    # Sin ninguna fila, la empresa es anterior a esta función y lo tiene todo.
    # Es lo mismo que asume el middleware; las dos lecturas deben coincidir o
    # la consola mostraría una cosa y el servidor haría otra.
    virgen = not filas
    return [
        ModuloContratado(
            clave=m.clave, nombre=m.nombre, esencial=m.esencial,
            activo=bool(m.esencial or virgen or (m.clave in filas and filas[m.clave].activo)),
        )
        for m in MODULOS
    ]


@router.get("/empresas/{cliente_id}/modulos", response_model=List[ModuloContratado])
async def ver_modulos(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.ver")),
):
    await _empresa(db, cliente_id)
    return await _modulos(db, cliente_id)


class ModulosElegidos(BaseModel):
    claves: List[str]


@router.put("/empresas/{cliente_id}/modulos", response_model=List[ModuloContratado])
async def guardar_modulos(
    cliente_id: int, data: ModulosElegidos, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.modulos")),
):
    empresa = await _empresa(db, cliente_id)
    elegidos = set(data.claves) | set(ESENCIALES)

    r = await db.execute(select(PlataformaModuloCliente).where(
        PlataformaModuloCliente.cliente_id == cliente_id))
    existentes = {m.modulo: m for m in r.scalars().all()}

    for m in MODULOS:
        activo = m.clave in elegidos
        fila = existentes.get(m.clave)
        if fila:
            if fila.activo != activo:
                fila.activo = activo
                if activo and not fila.desde:
                    fila.desde = date.today()
        else:
            db.add(PlataformaModuloCliente(
                cliente_id=cliente_id, modulo=m.clave, activo=activo,
                desde=date.today() if activo else None))

    await _anotar(db, request, "modulos.edicion", empresa.codigo,
                  ", ".join(sorted(elegidos - set(ESENCIALES))) or "ninguno")
    await db.commit()
    # El middleware recuerda esto unos segundos; sin descartarlo, el cambio
    # tardaría en verse y parecería que no se guardó.
    acceso_modulos.olvidar(empresa.codigo)
    return await _modulos(db, cliente_id)


# ─── Contactos ────────────────────────────────────────────────────────────────

class Contacto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    nombre: str
    cargo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    principal: bool = False
    notas: Optional[str] = None


@router.get("/empresas/{cliente_id}/contactos", response_model=List[Contacto])
async def ver_contactos(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.ver")),
):
    r = await db.execute(
        select(PlataformaContacto)
        .where(PlataformaContacto.cliente_id == cliente_id)
        .order_by(PlataformaContacto.principal.desc(), PlataformaContacto.nombre))
    return [Contacto.model_validate(c) for c in r.scalars().all()]


@router.post("/empresas/{cliente_id}/contactos", response_model=Contacto, status_code=201)
async def crear_contacto(
    cliente_id: int, data: Contacto, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.editar")),
):
    empresa = await _empresa(db, cliente_id)
    if data.principal:
        # Solo puede haber un principal: si no, «a quién se le escribe» vuelve
        # a ser una pregunta abierta.
        await db.execute(
            text("UPDATE plataforma_contacto SET principal = false WHERE cliente_id = :c"),
            {"c": cliente_id})
    c = PlataformaContacto(cliente_id=cliente_id, **data.model_dump(exclude={"id"}))
    db.add(c)
    await _anotar(db, request, "contacto.alta", empresa.codigo, data.nombre)
    await db.commit(); await db.refresh(c)
    return Contacto.model_validate(c)


@router.put("/empresas/{cliente_id}/contactos/{contacto_id}", response_model=Contacto)
async def editar_contacto(
    cliente_id: int, contacto_id: int, data: Contacto, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.editar")),
):
    empresa = await _empresa(db, cliente_id)
    r = await db.execute(select(PlataformaContacto).where(
        (PlataformaContacto.id == contacto_id) &
        (PlataformaContacto.cliente_id == cliente_id)))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Ese contacto no existe en esta empresa")
    if data.principal:
        await db.execute(
            text("UPDATE plataforma_contacto SET principal = false WHERE cliente_id = :c"),
            {"c": cliente_id})
    for campo, valor in data.model_dump(exclude={"id"}, exclude_unset=True).items():
        setattr(c, campo, valor)
    await _anotar(db, request, "contacto.edicion", empresa.codigo, c.nombre)
    await db.commit(); await db.refresh(c)
    return Contacto.model_validate(c)


@router.delete("/empresas/{cliente_id}/contactos/{contacto_id}", status_code=204)
async def borrar_contacto(
    cliente_id: int, contacto_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.editar")),
):
    empresa = await _empresa(db, cliente_id)
    r = await db.execute(select(PlataformaContacto).where(
        (PlataformaContacto.id == contacto_id) &
        (PlataformaContacto.cliente_id == cliente_id)))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Ese contacto no existe en esta empresa")
    nombre = c.nombre
    await db.delete(c)
    await _anotar(db, request, "contacto.baja", empresa.codigo, nombre)
    await db.commit()


# ─── Documentos ───────────────────────────────────────────────────────────────

class Documento(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    tipo: Optional[str] = None
    nombre: str
    archivo: Optional[str] = None
    vence: Optional[date] = None
    notas: Optional[str] = None


@router.get("/empresas/{cliente_id}/documentos", response_model=List[Documento])
async def ver_documentos(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.ver")),
):
    r = await db.execute(
        select(PlataformaDocumento)
        .where(PlataformaDocumento.cliente_id == cliente_id)
        .order_by(PlataformaDocumento.id.desc()))
    return [Documento.model_validate(d) for d in r.scalars().all()]


@router.post("/empresas/{cliente_id}/documentos", response_model=Documento, status_code=201)
async def crear_documento(
    cliente_id: int, data: Documento, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.editar")),
):
    empresa = await _empresa(db, cliente_id)
    d = PlataformaDocumento(cliente_id=cliente_id, **data.model_dump(exclude={"id"}))
    db.add(d)
    await _anotar(db, request, "documento.alta", empresa.codigo, data.nombre)
    await db.commit(); await db.refresh(d)
    return Documento.model_validate(d)


@router.delete("/empresas/{cliente_id}/documentos/{documento_id}", status_code=204)
async def borrar_documento(
    cliente_id: int, documento_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("comercial.editar")),
):
    empresa = await _empresa(db, cliente_id)
    r = await db.execute(select(PlataformaDocumento).where(
        (PlataformaDocumento.id == documento_id) &
        (PlataformaDocumento.cliente_id == cliente_id)))
    d = r.scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Ese documento no existe en esta empresa")
    nombre = d.nombre
    await db.delete(d)
    await _anotar(db, request, "documento.baja", empresa.codigo, nombre)
    await db.commit()


# ─── Pagos y cartera ──────────────────────────────────────────────────────────

class Pago(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    # A qué factura se aplica. Sin este campo el valor llegaba y Pydantic lo
    # descartaba en silencio: el pago quedaba suelto y la factura seguía
    # apareciendo sin abonar.
    factura_id: Optional[int] = None
    fecha: date
    monto: Decimal
    moneda: str = "COP"
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    metodo: Optional[str] = None
    referencia: Optional[str] = None
    notas: Optional[str] = None


class Cartera(BaseModel):
    """El estado de cuenta, resumido.

    `cubierto_hasta` sale del periodo que cubren los pagos y no de la fecha en
    que se pagaron: un cliente puede pagar tarde tres meses juntos y quedar al
    día, y otro puede pagar puntual un solo mes y estar descubierto.
    """
    tarifa_mensual: Decimal
    moneda: str
    iva_pct: Decimal
    total_con_iva: Decimal
    pagado_total: Decimal
    cubierto_hasta: Optional[date] = None
    dias_en_mora: int = 0
    al_dia: bool = True
    # Sin ningún pago con periodo no se puede afirmar ni que está al día ni que
    # está en mora; la consola lo muestra como «sin datos» en vez de inventar.
    hay_datos: bool = False


@router.get("/empresas/{cliente_id}/pagos", response_model=List[Pago])
async def ver_pagos(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.ver")),
):
    r = await db.execute(
        select(PlataformaPago)
        .where(PlataformaPago.cliente_id == cliente_id)
        .order_by(PlataformaPago.fecha.desc(), PlataformaPago.id.desc()))
    return [Pago.model_validate(p) for p in r.scalars().all()]


@router.post("/empresas/{cliente_id}/pagos", response_model=Pago, status_code=201)
async def registrar_pago(
    cliente_id: int, data: Pago, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.editar")),
):
    empresa = await _empresa(db, cliente_id)
    if data.monto is None or data.monto <= 0:
        raise HTTPException(400, "El monto del pago debe ser mayor que cero")
    if data.periodo_desde and data.periodo_hasta and data.periodo_hasta < data.periodo_desde:
        raise HTTPException(
            400, "El periodo termina antes de empezar: revise las dos fechas.")
    p = PlataformaPago(cliente_id=cliente_id, **data.model_dump(exclude={"id"}))
    db.add(p)
    detalle = f"{data.monto} {data.moneda}"
    if data.periodo_hasta:
        detalle += f" hasta {data.periodo_hasta}"
    await _anotar(db, request, "pago.registro", empresa.codigo, detalle)
    await db.commit(); await db.refresh(p)
    return Pago.model_validate(p)


@router.delete("/empresas/{cliente_id}/pagos/{pago_id}", status_code=204)
async def borrar_pago(
    cliente_id: int, pago_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.editar")),
):
    empresa = await _empresa(db, cliente_id)
    r = await db.execute(select(PlataformaPago).where(
        (PlataformaPago.id == pago_id) & (PlataformaPago.cliente_id == cliente_id)))
    p = r.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Ese pago no existe en esta empresa")
    detalle = f"{p.monto} del {p.fecha}"
    await db.delete(p)
    await _anotar(db, request, "pago.anulacion", empresa.codigo, detalle)
    await db.commit()


@router.get("/empresas/{cliente_id}/cartera", response_model=Cartera)
async def ver_cartera(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("contabilidad.ver")),
):
    await _empresa(db, cliente_id)
    c = await _contrato_de(db, cliente_id)
    await db.commit()

    r = await db.execute(select(PlataformaPago).where(PlataformaPago.cliente_id == cliente_id))
    pagos = list(r.scalars().all())
    total = sum((p.monto or Decimal(0)) for p in pagos) if pagos else Decimal(0)
    hasta = max((p.periodo_hasta for p in pagos if p.periodo_hasta), default=None)

    tarifa = c.tarifa_mensual or Decimal(0)
    iva = c.iva_pct if c.iva_pct is not None else Decimal(19)
    hoy = date.today()
    mora = (hoy - hasta).days if hasta and hasta < hoy else 0

    return Cartera(
        tarifa_mensual=tarifa,
        moneda=c.moneda or "COP",
        iva_pct=iva,
        total_con_iva=(tarifa * (Decimal(100) + iva) / Decimal(100)).quantize(Decimal("0.01")),
        pagado_total=Decimal(total),
        cubierto_hasta=hasta,
        dias_en_mora=mora,
        al_dia=mora == 0,
        hay_datos=hasta is not None,
    )


# ─── Uso real de la plataforma ────────────────────────────────────────────────

class Uso(BaseModel):
    """Cuánto se usa de verdad, contando dentro del esquema del cliente.

    Sirve para dos cosas que un operador necesita: notar que un cliente está
    abandonando la herramienta antes de que lo diga, y sustentar la tarifa con
    algo distinto de una impresión.
    """
    usuarios: int = 0
    usuarios_activos: int = 0
    ultimo_ingreso: Optional[datetime] = None
    # Cuántos usuarios entraron en los últimos 30 días.
    activos_30d: int = 0
    conteos: Dict[str, int] = {}


# Se cuenta un puñado de tablas representativas y no las 416: recorrerlas todas
# en cada consulta sería lento y no diría gran cosa.
_TABLAS_DE_USO = {
    "Estibas": "estibas",
    "Movimientos": "movimientos",
    "Manifiestos": "manifiestos",
    "Activos (EAM)": "eam_activo",
    "Órdenes de trabajo": "eam_orden_trabajo",
    "Llantas": "eam_neumatico",
    "Vehículos": "vehiculos",
    "Documentos (DMS)": "dms_documento",
}


@router.get("/empresas/{cliente_id}/uso", response_model=Uso)
async def ver_uso(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.ver")),
):
    empresa = await _empresa(db, cliente_id)
    uso = Uso()
    async with _sesion_de(empresa.esquema) as s:
        uso.usuarios = (await s.execute(text("SELECT count(*) FROM usuarios"))).scalar() or 0
        uso.usuarios_activos = (await s.execute(
            text("SELECT count(*) FROM usuarios WHERE activo"))).scalar() or 0
        uso.ultimo_ingreso = (await s.execute(
            text("SELECT max(ultimo_login) FROM usuarios"))).scalar()
        uso.activos_30d = (await s.execute(
            text("SELECT count(*) FROM usuarios WHERE ultimo_login > :d"),
            {"d": datetime.utcnow() - timedelta(days=30)})).scalar() or 0

        conteos: Dict[str, int] = {}
        for etiqueta, tabla in _TABLAS_DE_USO.items():
            try:
                conteos[etiqueta] = (await s.execute(
                    text(f"SELECT count(*) FROM {tabla}"))).scalar() or 0
            except Exception:
                # Una tabla que no exista en ese esquema no debe tumbar el resto
                # del informe. La consulta fallida aborta la transacción, así que
                # hay que deshacerla antes de seguir contando.
                await s.rollback()
        uso.conteos = conteos
    return uso
