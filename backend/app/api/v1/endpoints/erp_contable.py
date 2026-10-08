"""
El núcleo contable expuesto: terceros, períodos, reglas, libros y estados.

Va aparte de `erp.py` —que ya pasa de 1.500 líneas y cubre los documentos— pero
cuelga del MISMO prefijo `/erp`, así que desde fuera es el mismo módulo.

Lo que hay acá es lo que convierte los documentos en contabilidad:

  · el maestro de terceros, sin el cual no hay exógena ni cartera por NIT;
  · los períodos, que son lo que permite cerrar un mes y que se quede cerrado;
  · las reglas contables y tributarias, que sacan las cuentas y las tarifas de
    dentro del código;
  · los libros y los estados financieros, calculados SIEMPRE desde los
    movimientos y nunca desde un saldo guardado aparte.

Ese último punto es el que hace que las cifras se puedan defender: un saldo
almacenado se desincroniza del movimiento que lo produjo y nadie sabe cuál de los
dos miente.
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import erp_impuestos, erp_motor, erp_semilla
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core import erp_permisos
from app.infrastructure.models.erp import (
    EstadoComprobante, TipoCuenta,
    ERPAuditoria, ERPComprobante, ERPComprobanteLinea, ERPEmpresa, ERPPlanCuenta,
)
from app.infrastructure.models.erp_nucleo import (
    ERPEventoContable, ERPParametroFiscal, ERPPeriodo,
    ERPReglaContable, ERPReglaImpuesto, ERPTercero,
)
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/erp", tags=["ERP"])


def _quien(u: Usuario) -> str:
    return getattr(u, "nombre", None) or getattr(u, "username", "?")


def _ip(request: Request) -> Optional[str]:
    """La IP de quien pide, si el proxy la pasa.

    No se inventa: `request.client.host` detrás de nginx es la del propio proxy,
    y guardar esa como si fuera la del usuario es peor que no guardar nada.
    """
    reenviada = request.headers.get("x-forwarded-for")
    return reenviada.split(",")[0].strip() if reenviada else None


# ═══ TERCEROS ═════════════════════════════════════════════════════════════════

class TerceroEntrada(BaseModel):
    empresa_id: int
    tipo_identificacion: str = "NIT"
    numero_identificacion: str = Field(min_length=1, max_length=30)
    razon_social: str = Field(min_length=1, max_length=300)
    nombre_comercial: Optional[str] = None
    es_persona_natural: bool = False
    primer_nombre: Optional[str] = None
    primer_apellido: Optional[str] = None
    segundo_apellido: Optional[str] = None
    otros_nombres: Optional[str] = None

    es_cliente: bool = False
    es_proveedor: bool = False
    es_empleado: bool = False
    es_socio: bool = False

    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    codigo_municipio: Optional[str] = None
    departamento: Optional[str] = None
    pais: str = "Colombia"
    telefono: Optional[str] = None
    email: Optional[str] = None

    responsabilidades: List[str] = []
    regimen: Optional[str] = None
    codigo_ciiu: Optional[str] = None
    autorretenedor: bool = False
    gran_contribuyente: bool = False
    agente_retencion: bool = False
    exento_retencion: bool = False

    dias_credito: int = 0
    cupo_credito: float = 0
    banco_nombre: Optional[str] = None
    banco_tipo_cuenta: Optional[str] = None
    banco_numero_cuenta: Optional[str] = None
    notas: Optional[str] = None


class TerceroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    tipo_identificacion: str
    numero_identificacion: str
    digito_verificacion: Optional[str] = None
    razon_social: str
    nombre_comercial: Optional[str] = None
    es_persona_natural: bool
    es_cliente: bool
    es_proveedor: bool
    es_empleado: bool
    es_socio: bool
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    codigo_municipio: Optional[str] = None
    departamento: Optional[str] = None
    pais: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    responsabilidades: List[str] = []
    regimen: Optional[str] = None
    codigo_ciiu: Optional[str] = None
    autorretenedor: bool
    gran_contribuyente: bool
    agente_retencion: bool
    exento_retencion: bool
    dias_credito: int
    cupo_credito: Optional[float] = None
    banco_nombre: Optional[str] = None
    banco_numero_cuenta: Optional[str] = None
    activo: bool


@router.get("/terceros", response_model=List[TerceroResponse])
async def listar_terceros(
    empresa_id: Optional[int] = None,
    buscar: Optional[str] = None,
    tipo: Optional[str] = Query(None, description="cliente, proveedor, empleado"),
    limite: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_terceros),
):
    consulta = select(ERPTercero).where(ERPTercero.activo.is_(True))
    if empresa_id:
        consulta = consulta.where(ERPTercero.empresa_id == empresa_id)
    if buscar:
        aguja = f"%{buscar.strip()}%"
        consulta = consulta.where(or_(
            ERPTercero.razon_social.ilike(aguja),
            ERPTercero.nombre_comercial.ilike(aguja),
            ERPTercero.numero_identificacion.ilike(aguja)))
    if tipo:
        campo = {"cliente": ERPTercero.es_cliente,
                 "proveedor": ERPTercero.es_proveedor,
                 "empleado": ERPTercero.es_empleado}.get(tipo.lower())
        if campo is not None:
            consulta = consulta.where(campo.is_(True))

    r = await db.execute(consulta.order_by(ERPTercero.razon_social).limit(limite))
    return list(r.scalars().all())


@router.post("/terceros", response_model=TerceroResponse, status_code=201)
async def crear_tercero(
    data: TerceroEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.editar_terceros),
):
    """Da de alta un tercero, calculando su dígito de verificación.

    El DV se calcula y no se pide: pedirlo invita a que alguien lo escriba mal, y
    un DV equivocado hace rechazar la información exógena entera.
    """
    numero = "".join(c for c in data.numero_identificacion if c.isalnum())
    ya = (await db.execute(select(ERPTercero).where(
        ERPTercero.empresa_id == data.empresa_id,
        ERPTercero.numero_identificacion == numero))).scalar_one_or_none()
    if ya is not None:
        raise HTTPException(
            409,
            f"Ya existe «{ya.razon_social}» con la identificación {numero}. "
            f"Edítelo en vez de crear otro: dos veces el mismo tercero parte su "
            f"cartera y su exógena en dos.")

    dv = (erp_motor.digito_verificacion(numero)
          if data.tipo_identificacion == "NIT" else None)

    tercero = ERPTercero(
        **data.model_dump(exclude={"numero_identificacion"}),
        numero_identificacion=numero, digito_verificacion=dv, activo=True)
    db.add(tercero)
    await db.flush()

    await erp_motor.auditar(
        db, empresa_id=data.empresa_id, entidad="tercero", entidad_id=tercero.id,
        accion="CREAR", usuario=_quien(usuario), ip=_ip(request),
        despues={"nit": numero, "razon_social": data.razon_social})
    await db.commit()
    await db.refresh(tercero)
    return tercero


@router.put("/terceros/{tercero_id}", response_model=TerceroResponse)
async def editar_tercero(
    tercero_id: int, data: TerceroEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.editar_terceros),
):
    tercero = await db.get(ERPTercero, tercero_id)
    if tercero is None:
        raise HTTPException(404, "Ese tercero no existe.")

    antes = {"razon_social": tercero.razon_social,
             "numero_identificacion": tercero.numero_identificacion,
             "regimen": tercero.regimen}

    numero = "".join(c for c in data.numero_identificacion if c.isalnum())
    for campo, valor in data.model_dump(exclude={"numero_identificacion",
                                                 "empresa_id"}).items():
        setattr(tercero, campo, valor)
    tercero.numero_identificacion = numero
    if data.tipo_identificacion == "NIT":
        tercero.digito_verificacion = erp_motor.digito_verificacion(numero)

    await erp_motor.auditar(
        db, empresa_id=tercero.empresa_id, entidad="tercero",
        entidad_id=tercero.id, accion="EDITAR", usuario=_quien(usuario),
        ip=_ip(request), antes=antes,
        despues={"razon_social": data.razon_social,
                 "numero_identificacion": numero, "regimen": data.regimen})
    await db.commit()
    await db.refresh(tercero)
    return tercero


@router.get("/terceros/dv/{nit}")
async def calcular_dv(nit: str, usuario: Usuario = Depends(get_current_user)):
    """El dígito de verificación de un NIT, para mostrarlo mientras se escribe."""
    return {"nit": nit, "dv": erp_motor.digito_verificacion(nit)}


# ═══ PERÍODOS ═════════════════════════════════════════════════════════════════

class PeriodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    anio: int
    mes: int
    estado: str
    cerrado_por: Optional[str] = None
    cerrado_en: Optional[datetime] = None
    motivo_reapertura: Optional[str] = None
    # Se calculan
    comprobantes: int = 0
    debitos: float = 0
    creditos: float = 0


@router.get("/contabilidad/periodos", response_model=List[PeriodoResponse])
async def listar_periodos(
    empresa_id: int, anio: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_contabilidad),
):
    consulta = select(ERPPeriodo).where(ERPPeriodo.empresa_id == empresa_id)
    if anio:
        consulta = consulta.where(ERPPeriodo.anio == anio)
    periodos = list((await db.execute(
        consulta.order_by(ERPPeriodo.anio.desc(), ERPPeriodo.mes.desc()))).scalars().all())

    # El movimiento de cada período, en una sola consulta agrupada. Una por
    # período convierte doce meses en doce viajes a la base.
    r = await db.execute(
        select(ERPComprobante.periodo, func.count(),
               func.coalesce(func.sum(ERPComprobante.total_debito), 0),
               func.coalesce(func.sum(ERPComprobante.total_credito), 0))
        .where(ERPComprobante.empresa_id == empresa_id,
               ERPComprobante.estado == EstadoComprobante.CONTABILIZADO)
        .group_by(ERPComprobante.periodo))
    movimiento = {p: (c, float(d), float(cr)) for p, c, d, cr in r.all()}

    salida = []
    for p in periodos:
        ficha = PeriodoResponse.model_validate(p)
        c, d, cr = movimiento.get(f"{p.anio}-{p.mes:02d}", (0, 0.0, 0.0))
        ficha.comprobantes, ficha.debitos, ficha.creditos = c, d, cr
        salida.append(ficha)
    return salida


class CierreEntrada(BaseModel):
    empresa_id: int
    anio: int
    mes: int
    motivo: Optional[str] = None


@router.post("/contabilidad/periodos/cerrar", response_model=PeriodoResponse)
async def cerrar_periodo(
    data: CierreEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.manejar_periodos),
):
    """Cierra un mes. Después de esto no entra ni sale nada de él.

    Antes de cerrar se comprueba que no queden comprobantes en borrador: cerrar
    con borradores dentro los deja inservibles —no se pueden contabilizar ni
    borrar— y quien los escribió no se entera.
    """
    periodo = await erp_motor.periodo_de(
        db, data.empresa_id, date(data.anio, data.mes, 1))
    if periodo.estado != "ABIERTO":
        raise HTTPException(409, f"Ese período ya está {periodo.estado.lower()}.")

    borradores = (await db.execute(
        select(func.count()).select_from(ERPComprobante).where(
            ERPComprobante.empresa_id == data.empresa_id,
            ERPComprobante.periodo == f"{data.anio}-{data.mes:02d}",
            ERPComprobante.estado == EstadoComprobante.BORRADOR))).scalar() or 0
    if borradores:
        raise HTTPException(
            409,
            f"Quedan {borradores} comprobante(s) en borrador en ese período. "
            f"Contabilícelos o anúlelos antes de cerrar: al cerrar quedarían "
            f"inservibles y quien los escribió no se enteraría.")

    pendientes = (await db.execute(
        select(func.count()).select_from(ERPEventoContable).where(
            ERPEventoContable.empresa_id == data.empresa_id,
            ERPEventoContable.estado.in_(("PENDIENTE", "FALLIDO")),
            func.extract("year", ERPEventoContable.fecha) == data.anio,
            func.extract("month", ERPEventoContable.fecha) == data.mes))).scalar() or 0
    if pendientes:
        raise HTTPException(
            409,
            f"Hay {pendientes} hecho(s) económico(s) de ese mes sin contabilizar. "
            f"Revíselos en Contabilidad → Eventos: cerrar ahora dejaría el mes "
            f"incompleto.")

    periodo.estado = "CERRADO"
    periodo.cerrado_por = _quien(usuario)
    periodo.cerrado_en = datetime.now(timezone.utc)

    await erp_motor.auditar(
        db, empresa_id=data.empresa_id, entidad="periodo", entidad_id=periodo.id,
        accion="CERRAR", usuario=_quien(usuario), ip=_ip(request),
        motivo=data.motivo,
        despues={"periodo": f"{data.anio}-{data.mes:02d}", "estado": "CERRADO"})
    await db.commit()
    await db.refresh(periodo)
    return PeriodoResponse.model_validate(periodo)


@router.post("/contabilidad/periodos/reabrir", response_model=PeriodoResponse)
async def reabrir_periodo(
    data: CierreEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.manejar_periodos),
):
    """Reabre un mes cerrado, dejando constancia de quién y por qué.

    El motivo es obligatorio. Reabrir sin justificar es lo mismo que no haber
    cerrado, y la declaración que se presentó con esas cifras queda sin respaldo.
    """
    if not data.motivo or not data.motivo.strip():
        raise HTTPException(
            422,
            "Diga por qué se reabre. Un período que se reabre sin motivo deja sin "
            "respaldo la declaración que se presentó con esas cifras.")

    periodo = (await db.execute(select(ERPPeriodo).where(
        ERPPeriodo.empresa_id == data.empresa_id,
        ERPPeriodo.anio == data.anio,
        ERPPeriodo.mes == data.mes))).scalar_one_or_none()
    if periodo is None:
        raise HTTPException(404, "Ese período no existe.")
    if periodo.estado == "BLOQUEADO":
        raise HTTPException(
            409,
            "Ese período está bloqueado definitivamente. Corrija con un asiento "
            "en el período abierto en vez de reabrirlo.")
    if periodo.estado == "ABIERTO":
        raise HTTPException(409, "Ese período ya está abierto.")

    periodo.estado = "ABIERTO"
    periodo.motivo_reapertura = data.motivo.strip()
    periodo.reabierto_por = _quien(usuario)
    periodo.reabierto_en = datetime.now(timezone.utc)

    await erp_motor.auditar(
        db, empresa_id=data.empresa_id, entidad="periodo", entidad_id=periodo.id,
        accion="REABRIR", usuario=_quien(usuario), ip=_ip(request),
        motivo=data.motivo.strip(),
        antes={"estado": "CERRADO"}, despues={"estado": "ABIERTO"})
    await db.commit()
    await db.refresh(periodo)
    return PeriodoResponse.model_validate(periodo)


# ═══ REGLAS ═══════════════════════════════════════════════════════════════════

@router.get("/contabilidad/reglas")
async def listar_reglas(
    empresa_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_contabilidad),
):
    """Qué cuenta cumple cada papel en cada evento.

    Es la parametrización que saca los códigos de cuenta de dentro del código.
    """
    reglas = list((await db.execute(select(ERPReglaContable).where(
        ERPReglaContable.empresa_id == empresa_id
    ).order_by(ERPReglaContable.evento, ERPReglaContable.papel))).scalars().all())
    if not reglas:
        return {"eventos": [], "gramatica": list(erp_motor.NATURALEZA_POR_EVENTO)}

    cuentas = {
        c.id: c for c in (await db.execute(select(ERPPlanCuenta).where(
            ERPPlanCuenta.id.in_([r.cuenta_id for r in reglas])))).scalars().all()
    }

    por_evento: Dict[str, List[dict]] = {}
    for r in reglas:
        cuenta = cuentas.get(r.cuenta_id)
        por_evento.setdefault(r.evento, []).append({
            "id": r.id, "papel": r.papel, "condicion": r.condicion,
            "cuenta_id": r.cuenta_id,
            "cuenta_codigo": cuenta.codigo if cuenta else None,
            "cuenta_nombre": cuenta.nombre if cuenta else None,
            "naturaleza": r.naturaleza, "activa": r.activa,
        })

    return {
        "eventos": [{"evento": e, "reglas": rs} for e, rs in sorted(por_evento.items())],
        # Los papeles que el motor entiende para cada evento. Sale del servidor
        # para que la pantalla no ofrezca un papel que el motor no sabe asentar.
        "gramatica": {
            evento: list(papeles)
            for evento, (_tipo, papeles) in erp_motor.NATURALEZA_POR_EVENTO.items()
        },
    }


class ReglaEntrada(BaseModel):
    empresa_id: int
    evento: str
    papel: str
    condicion: str = ""
    cuenta_id: int
    naturaleza: str
    descripcion: Optional[str] = None


@router.post("/contabilidad/reglas", status_code=201)
async def guardar_regla(
    data: ReglaEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.parametrizar),
):
    """Crea o actualiza la regla de un papel. Comprueba que el papel exista."""
    gramatica = erp_motor.NATURALEZA_POR_EVENTO.get(data.evento)
    if gramatica is None:
        raise HTTPException(
            422, f"El evento «{data.evento}» no está en la gramática del motor.")
    if data.papel not in gramatica[1]:
        raise HTTPException(
            422,
            f"El papel «{data.papel}» no aplica a «{data.evento}». Los que aplican "
            f"son: {', '.join(sorted(gramatica[1]))}.")

    cuenta = await db.get(ERPPlanCuenta, data.cuenta_id)
    if cuenta is None:
        raise HTTPException(404, "Esa cuenta no existe.")
    if not cuenta.acepta_movimientos:
        raise HTTPException(
            422,
            f"La cuenta {cuenta.codigo} es agrupadora y no acepta movimiento. "
            f"Escoja una subcuenta: si no, el balance no cuadraría consigo mismo.")

    regla = (await db.execute(select(ERPReglaContable).where(
        ERPReglaContable.empresa_id == data.empresa_id,
        ERPReglaContable.evento == data.evento,
        ERPReglaContable.papel == data.papel,
        ERPReglaContable.condicion == data.condicion))).scalar_one_or_none()

    if regla is None:
        regla = ERPReglaContable(**data.model_dump(), activa=True)
        db.add(regla)
    else:
        regla.cuenta_id = data.cuenta_id
        regla.naturaleza = data.naturaleza
        regla.descripcion = data.descripcion
        regla.activa = True

    await db.flush()
    await erp_motor.auditar(
        db, empresa_id=data.empresa_id, entidad="regla_contable",
        entidad_id=regla.id, accion="CONFIGURAR", usuario=_quien(usuario),
        ip=_ip(request),
        despues={"evento": data.evento, "papel": data.papel,
                 "cuenta": cuenta.codigo})
    await db.commit()
    return {"id": regla.id, "evento": regla.evento, "papel": regla.papel}


@router.get("/tributacion/reglas")
async def listar_reglas_impuesto(
    empresa_id: int, vigentes: bool = True,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_impuestos),
):
    consulta = select(ERPReglaImpuesto).where(
        ERPReglaImpuesto.empresa_id == empresa_id)
    if vigentes:
        hoy = date.today()
        consulta = consulta.where(
            ERPReglaImpuesto.activa.is_(True),
            ERPReglaImpuesto.vigente_desde <= hoy,
            or_(ERPReglaImpuesto.vigente_hasta.is_(None),
                ERPReglaImpuesto.vigente_hasta >= hoy))
    r = await db.execute(consulta.order_by(
        ERPReglaImpuesto.impuesto, ERPReglaImpuesto.concepto,
        ERPReglaImpuesto.vigente_desde.desc()))
    return [
        {"id": x.id, "impuesto": x.impuesto, "concepto": x.concepto,
         "tarifa": float(x.tarifa), "base_minima_uvt": float(x.base_minima_uvt or 0),
         "vigente_desde": x.vigente_desde, "vigente_hasta": x.vigente_hasta,
         "codigo_municipio": x.codigo_municipio, "papel": x.papel,
         "excluye_autorretenedor": x.excluye_autorretenedor, "activa": x.activa}
        for x in r.scalars().all()
    ]


class ReglaImpuestoEntrada(BaseModel):
    empresa_id: int
    impuesto: str
    concepto: str
    tarifa: float
    base_minima_uvt: float = 0
    vigente_desde: date
    codigo_municipio: Optional[str] = None
    papel: Optional[str] = None
    cuenta_id: Optional[int] = None
    excluye_autorretenedor: bool = True
    descripcion: Optional[str] = None


@router.post("/tributacion/reglas", status_code=201)
async def crear_regla_impuesto(
    data: ReglaImpuestoEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.parametrizar),
):
    """Crea una regla tributaria y CIERRA la anterior del mismo concepto.

    No se edita la vieja: se le pone fecha de fin y se crea una nueva. Editar la
    anterior reescribiría cómo se calculó lo que ya se declaró, y entonces
    recalcular una factura de marzo daría una cifra distinta de la presentada.
    """
    anteriores = list((await db.execute(select(ERPReglaImpuesto).where(
        ERPReglaImpuesto.empresa_id == data.empresa_id,
        ERPReglaImpuesto.impuesto == data.impuesto,
        ERPReglaImpuesto.concepto == data.concepto,
        ERPReglaImpuesto.activa.is_(True),
        ERPReglaImpuesto.vigente_hasta.is_(None)))).scalars().all())
    for vieja in anteriores:
        if vieja.vigente_desde >= data.vigente_desde:
            raise HTTPException(
                409,
                f"Ya hay una regla de {data.impuesto}/{data.concepto} vigente desde "
                f"{vieja.vigente_desde}. La nueva tiene que empezar después.")
        vieja.vigente_hasta = data.vigente_desde

    regla = ERPReglaImpuesto(**data.model_dump(), activa=True)
    db.add(regla)
    await db.flush()

    await erp_motor.auditar(
        db, empresa_id=data.empresa_id, entidad="regla_impuesto",
        entidad_id=regla.id, accion="CONFIGURAR", usuario=_quien(usuario),
        ip=_ip(request),
        despues={"impuesto": data.impuesto, "concepto": data.concepto,
                 "tarifa": data.tarifa, "desde": str(data.vigente_desde)},
        motivo=f"Cierra {len(anteriores)} regla(s) anterior(es)")
    await db.commit()
    return {"id": regla.id, "cerradas": len(anteriores)}


@router.post("/tributacion/simular")
async def simular_impuestos(
    empresa_id: int, base: float, concepto: str,
    fecha: Optional[date] = None, tercero_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_impuestos),
):
    """Qué impuestos aplicarían a una base, y por qué.

    Devuelve el detalle con el motivo de cada exclusión. Es lo que permite
    explicar por qué no se retuvo, que en una revisión vale tanto como el número.
    """
    tercero = await db.get(ERPTercero, tercero_id) if tercero_id else None
    # Sin `estricto`: el simulador debe MOSTRAR la regla que no se puede liquidar
    # y por qué, no negarse a responder. Detenerse es lo correcto al emitir un
    # documento, y eso lo sigue haciendo `crear_factura_*`.
    return await erp_impuestos.liquidar_documento(
        db, empresa_id=empresa_id, fecha=fecha or date.today(),
        base_gravada=base, concepto=concepto, tercero=tercero, estricto=False)


@router.get("/tributacion/parametros")
async def listar_parametros(
    anio: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_impuestos),
):
    consulta = select(ERPParametroFiscal)
    if anio:
        consulta = consulta.where(ERPParametroFiscal.anio == anio)
    r = await db.execute(consulta.order_by(
        ERPParametroFiscal.anio.desc(), ERPParametroFiscal.clave))
    return [
        {"id": p.id, "anio": p.anio, "clave": p.clave, "valor": float(p.valor),
         "descripcion": p.descripcion, "fuente": p.fuente}
        for p in r.scalars().all()
    ]


class ParametroEntrada(BaseModel):
    anio: int
    clave: str
    valor: float
    descripcion: Optional[str] = None
    fuente: Optional[str] = None


@router.post("/tributacion/parametros", status_code=201)
async def guardar_parametro(
    data: ParametroEntrada,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.parametrizar),
):
    """La UVT, el salario mínimo y demás valores que cambian cada año."""
    p = (await db.execute(select(ERPParametroFiscal).where(
        ERPParametroFiscal.anio == data.anio,
        ERPParametroFiscal.clave == data.clave.upper()))).scalar_one_or_none()
    if p is None:
        p = ERPParametroFiscal(**{**data.model_dump(), "clave": data.clave.upper()})
        db.add(p)
    else:
        p.valor = data.valor
        p.descripcion = data.descripcion
        p.fuente = data.fuente
    await db.commit()
    return {"anio": p.anio, "clave": p.clave, "valor": float(p.valor)}


# ═══ LIBROS Y ESTADOS FINANCIEROS ═════════════════════════════════════════════
#
# Todo se calcula desde `erp_comprobante_lineas`. Nunca desde un saldo guardado
# aparte: un saldo almacenado se desincroniza del movimiento que lo produjo, y
# entonces nadie sabe cuál de los dos miente.


async def _saldos(db: AsyncSession, empresa_id: int, hasta: date,
                  desde: Optional[date] = None,
                  centro_costo_id: Optional[int] = None) -> Dict[int, Dict[str, Decimal]]:
    """Débitos y créditos por cuenta en un rango, de una sola consulta."""
    condiciones = [
        ERPComprobante.empresa_id == empresa_id,
        ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
        ERPComprobante.fecha <= hasta,
    ]
    if desde:
        condiciones.append(ERPComprobante.fecha >= desde)
    if centro_costo_id:
        condiciones.append(ERPComprobanteLinea.centro_costo_id == centro_costo_id)

    r = await db.execute(
        select(ERPComprobanteLinea.cuenta_id,
               func.coalesce(func.sum(ERPComprobanteLinea.debito), 0),
               func.coalesce(func.sum(ERPComprobanteLinea.credito), 0))
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .where(and_(*condiciones))
        .group_by(ERPComprobanteLinea.cuenta_id))
    return {
        cid: {"debito": Decimal(str(d)), "credito": Decimal(str(c))}
        for cid, d, c in r.all()
    }


@router.get("/contabilidad/balance-comprobacion")
async def balance_comprobacion(
    empresa_id: int, hasta: date,
    desde: Optional[date] = None,
    centro_costo_id: Optional[int] = None,
    solo_con_movimiento: bool = True,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Saldo inicial, movimiento del período y saldo final, por cuenta.

    Es el reporte que permite detectar un descuadre: si la suma de débitos no
    iguala la de créditos, hay un asiento mal escrito, y desde acá se puede bajar
    hasta el documento que lo produjo.
    """
    inicio_periodo = desde or date(hasta.year, 1, 1)
    # El saldo inicial es todo lo anterior al rango. Sin él, el balance de un mes
    # no explica de dónde viene el saldo con el que arranca.
    anteriores = await _saldos(
        db, empresa_id, inicio_periodo - __import__("datetime").timedelta(days=1),
        centro_costo_id=centro_costo_id)
    movimiento = await _saldos(db, empresa_id, hasta, inicio_periodo, centro_costo_id)

    cuentas = {
        c.id: c for c in (await db.execute(select(ERPPlanCuenta).where(
            ERPPlanCuenta.empresa_id == empresa_id
        ).order_by(ERPPlanCuenta.codigo))).scalars().all()
    }

    filas = []
    total = {"inicial_d": Decimal(0), "inicial_c": Decimal(0),
             "mov_d": Decimal(0), "mov_c": Decimal(0),
             "final_d": Decimal(0), "final_c": Decimal(0)}

    for cuenta in cuentas.values():
        ini = anteriores.get(cuenta.id, {"debito": Decimal(0), "credito": Decimal(0)})
        mov = movimiento.get(cuenta.id, {"debito": Decimal(0), "credito": Decimal(0)})
        if solo_con_movimiento and not (ini["debito"] or ini["credito"]
                                        or mov["debito"] or mov["credito"]):
            continue

        saldo_ini = ini["debito"] - ini["credito"]
        saldo_fin = saldo_ini + mov["debito"] - mov["credito"]

        filas.append({
            "cuenta_id": cuenta.id, "codigo": cuenta.codigo, "nombre": cuenta.nombre,
            "naturaleza": cuenta.naturaleza.value if hasattr(cuenta.naturaleza, "value")
                          else str(cuenta.naturaleza),
            "acepta_movimientos": cuenta.acepta_movimientos,
            "saldo_inicial_debito": float(max(saldo_ini, 0)),
            "saldo_inicial_credito": float(max(-saldo_ini, 0)),
            "debitos": float(mov["debito"]), "creditos": float(mov["credito"]),
            "saldo_final_debito": float(max(saldo_fin, 0)),
            "saldo_final_credito": float(max(-saldo_fin, 0)),
        })
        total["inicial_d"] += max(saldo_ini, Decimal(0))
        total["inicial_c"] += max(-saldo_ini, Decimal(0))
        total["mov_d"] += mov["debito"]
        total["mov_c"] += mov["credito"]
        total["final_d"] += max(saldo_fin, Decimal(0))
        total["final_c"] += max(-saldo_fin, Decimal(0))

    return {
        "desde": inicio_periodo, "hasta": hasta,
        "filas": filas,
        "totales": {k: float(v) for k, v in total.items()},
        # Que cuadre o no es la información más importante del reporte, así que
        # va explícita y no se deja al ojo de quien suma dos columnas largas.
        "cuadra": abs(total["mov_d"] - total["mov_c"]) < Decimal("0.01"),
    }


@router.get("/contabilidad/libro-mayor")
async def libro_mayor(
    empresa_id: int, cuenta_id: int, desde: date, hasta: date,
    limite: int = Query(500, ge=1, le=5000),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """El movimiento de una cuenta, con su saldo corriente, por páginas.

    Cada línea trae el comprobante que la produjo, que es el eslabón que permite
    ir de una cifra del balance al documento que la originó.

    POR QUÉ VA PAGINADO
    Sin límite, el mayor de la cuenta de clientes de un año devolvía veinticinco
    mil líneas en una sola respuesta: segundo y medio de servidor, varios megas
    por el cable y una tabla que nadie puede leer. Se devuelve el total además de
    la página, para que la pantalla pueda decir «500 de 25.812» en vez de dar a
    entender que eso es todo lo que hay.

    EL SALDO CORRIENTE SIGUE SIENDO CORRECTO
    Paginar un saldo acumulado es donde esto suele salir mal: si cada página
    empieza a acumular desde cero, la columna de saldo miente en todas menos en
    la primera. Acá el arrastre de la página se calcula con una suma agregada de
    lo anterior —una consulta, no traer las filas—, así que la última línea de la
    página 6 muestra el mismo saldo que mostraría sin paginar.
    """
    import datetime as _dt
    previos = await _saldos(db, empresa_id, desde - _dt.timedelta(days=1))
    p = previos.get(cuenta_id, {"debito": Decimal(0), "credito": Decimal(0)})
    saldo_inicial = p["debito"] - p["credito"]

    filtro = [ERPComprobanteLinea.cuenta_id == cuenta_id,
              ERPComprobante.empresa_id == empresa_id,
              ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
              ERPComprobante.fecha >= desde, ERPComprobante.fecha <= hasta]

    total = (await db.execute(
        select(func.count())
        .select_from(ERPComprobanteLinea)
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .where(*filtro))).scalar() or 0

    # El arrastre: lo que suman las líneas que quedaron antes de esta página.
    arrastre = Decimal(0)
    if desplazamiento:
        anteriores = (
            select(ERPComprobanteLinea.debito, ERPComprobanteLinea.credito)
            .join(ERPComprobante,
                  ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
            .where(*filtro)
            .order_by(ERPComprobante.fecha, ERPComprobante.id)
            .limit(desplazamiento).subquery()
        )
        fila = (await db.execute(select(
            func.coalesce(func.sum(anteriores.c.debito), 0),
            func.coalesce(func.sum(anteriores.c.credito), 0)))).first()
        arrastre = Decimal(str(fila[0])) - Decimal(str(fila[1]))

    saldo = saldo_inicial + arrastre

    r = await db.execute(
        select(ERPComprobanteLinea, ERPComprobante)
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .where(*filtro)
        .order_by(ERPComprobante.fecha, ERPComprobante.id)
        .offset(desplazamiento).limit(limite))

    cuenta = await db.get(ERPPlanCuenta, cuenta_id)
    lineas = []
    for linea, comp in r.all():
        saldo += Decimal(str(linea.debito)) - Decimal(str(linea.credito))
        lineas.append({
            "fecha": comp.fecha, "comprobante_id": comp.id,
            "comprobante": comp.numero, "tipo": comp.tipo.value
            if hasattr(comp.tipo, "value") else str(comp.tipo),
            "concepto": linea.concepto or comp.concepto,
            "tercero": linea.tercero, "referencia": comp.referencia,
            "debito": float(linea.debito), "credito": float(linea.credito),
            "saldo": float(saldo),
        })

    # El saldo final es el de TODO el rango, no el de la página: es la cifra que
    # tiene que coincidir con el balance, y darla por página sería un error.
    cierre = await _saldos(db, empresa_id, hasta)
    c = cierre.get(cuenta_id, {"debito": Decimal(0), "credito": Decimal(0)})

    return {
        "cuenta": {"id": cuenta_id,
                   "codigo": cuenta.codigo if cuenta else None,
                   "nombre": cuenta.nombre if cuenta else None},
        "desde": desde, "hasta": hasta,
        "saldo_inicial": float(saldo_inicial),
        "saldo_final": float(c["debito"] - c["credito"]),
        "total_lineas": total,
        "desplazamiento": desplazamiento,
        "limite": limite,
        "lineas": lineas,
    }


@router.get("/contabilidad/libro-diario")
async def libro_diario(
    empresa_id: int, desde: date, hasta: date,
    limite: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Los comprobantes del período, en orden cronológico, con sus líneas."""
    comps = list((await db.execute(select(ERPComprobante).where(
        ERPComprobante.empresa_id == empresa_id,
        ERPComprobante.fecha >= desde, ERPComprobante.fecha <= hasta,
        ERPComprobante.estado == EstadoComprobante.CONTABILIZADO
    ).order_by(ERPComprobante.fecha, ERPComprobante.id).limit(limite))).scalars().all())

    # Cuántos hay en realidad. Cortar en 500 sin decirlo hace creer que el mes
    # tuvo 500 comprobantes, y ese es un error que no se nota nunca.
    total = (await db.execute(select(func.count()).select_from(ERPComprobante).where(
        ERPComprobante.empresa_id == empresa_id,
        ERPComprobante.fecha >= desde, ERPComprobante.fecha <= hasta,
        ERPComprobante.estado == EstadoComprobante.CONTABILIZADO))).scalar() or 0

    if not comps:
        return {"desde": desde, "hasta": hasta, "comprobantes": [],
                "total_comprobantes": total, "limite": limite}

    r = await db.execute(select(ERPComprobanteLinea).where(
        ERPComprobanteLinea.comprobante_id.in_([c.id for c in comps])))
    por_comp: Dict[int, List[ERPComprobanteLinea]] = {}
    for ln in r.scalars().all():
        por_comp.setdefault(ln.comprobante_id, []).append(ln)

    ids = {ln.cuenta_id for lns in por_comp.values() for ln in lns}
    cuentas = {
        c.id: c for c in (await db.execute(select(ERPPlanCuenta).where(
            ERPPlanCuenta.id.in_(ids)))).scalars().all()
    } if ids else {}

    return {
        "desde": desde, "hasta": hasta,
        "total_comprobantes": total, "limite": limite,
        "comprobantes": [
            {
                "id": c.id, "numero": c.numero, "fecha": c.fecha,
                "tipo": c.tipo.value if hasattr(c.tipo, "value") else str(c.tipo),
                "concepto": c.concepto, "referencia": c.referencia,
                "total_debito": float(c.total_debito),
                "total_credito": float(c.total_credito),
                "lineas": [
                    {"cuenta_id": ln.cuenta_id,
                     "codigo": cuentas[ln.cuenta_id].codigo if ln.cuenta_id in cuentas else None,
                     "nombre": cuentas[ln.cuenta_id].nombre if ln.cuenta_id in cuentas else None,
                     "concepto": ln.concepto, "tercero": ln.tercero,
                     "debito": float(ln.debito), "credito": float(ln.credito)}
                    for ln in por_comp.get(c.id, [])
                ],
            }
            for c in comps
        ],
    }


@router.get("/contabilidad/estado-situacion")
async def estado_situacion_financiera(
    empresa_id: int, hasta: date,
    comparar_con: Optional[date] = None,
    centro_costo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """El balance, calculado desde los movimientos.

    Incluye el resultado del ejercicio dentro del patrimonio aunque todavía no se
    haya hecho el asiento de cierre: sin eso, el balance de cualquier mes que no
    sea diciembre no cuadra, y parece un error del sistema cuando es lo normal.
    """
    async def armar(corte: date) -> dict:
        saldos = await _saldos(db, empresa_id, corte, centro_costo_id=centro_costo_id)
        cuentas = {
            c.id: c for c in (await db.execute(select(ERPPlanCuenta).where(
                ERPPlanCuenta.empresa_id == empresa_id))).scalars().all()
        }
        grupos: Dict[str, List[dict]] = {"ACTIVO": [], "PASIVO": [], "PATRIMONIO": []}
        totales = {"ACTIVO": Decimal(0), "PASIVO": Decimal(0), "PATRIMONIO": Decimal(0)}
        resultado = Decimal(0)

        for cid, mov in saldos.items():
            cuenta = cuentas.get(cid)
            if cuenta is None:
                continue
            tipo = cuenta.tipo.value if hasattr(cuenta.tipo, "value") else str(cuenta.tipo)
            saldo = mov["debito"] - mov["credito"]

            if tipo == "INGRESO":
                resultado += -saldo
                continue
            if tipo == "EGRESO":
                # El enum del ERP usa EGRESO para gastos y costos por igual.
                resultado -= saldo
                continue
            if tipo not in grupos:
                continue

            # Pasivo y patrimonio se muestran en positivo aunque su saldo sea
            # crédito: un pasivo en negativo se lee como un error.
            valor = saldo if tipo == "ACTIVO" else -saldo
            grupos[tipo].append({
                "cuenta_id": cid, "codigo": cuenta.codigo, "nombre": cuenta.nombre,
                "valor": float(valor)})
            totales[tipo] += valor

        for g in grupos.values():
            g.sort(key=lambda x: x["codigo"])

        patrimonio_total = totales["PATRIMONIO"] + resultado
        return {
            "corte": corte,
            "activo": grupos["ACTIVO"], "total_activo": float(totales["ACTIVO"]),
            "pasivo": grupos["PASIVO"], "total_pasivo": float(totales["PASIVO"]),
            "patrimonio": grupos["PATRIMONIO"],
            "resultado_ejercicio": float(resultado),
            "total_patrimonio": float(patrimonio_total),
            "cuadra": abs(totales["ACTIVO"] - totales["PASIVO"] - patrimonio_total)
                      < Decimal("0.01"),
            "diferencia": float(totales["ACTIVO"] - totales["PASIVO"] - patrimonio_total),
        }

    actual = await armar(hasta)
    return {"actual": actual,
            "comparativo": await armar(comparar_con) if comparar_con else None}


@router.get("/contabilidad/estado-resultados")
async def estado_resultados(
    empresa_id: int, desde: date, hasta: date,
    centro_costo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Ingresos, costos, gastos y utilidad del período, desde los movimientos."""
    saldos = await _saldos(db, empresa_id, hasta, desde, centro_costo_id)
    cuentas = {
        c.id: c for c in (await db.execute(select(ERPPlanCuenta).where(
            ERPPlanCuenta.empresa_id == empresa_id))).scalars().all()
    }

    grupos: Dict[str, List[dict]] = {"INGRESO": [], "COSTO": [], "GASTO": []}
    totales = {"INGRESO": Decimal(0), "COSTO": Decimal(0), "GASTO": Decimal(0)}

    for cid, mov in saldos.items():
        cuenta = cuentas.get(cid)
        if cuenta is None:
            continue
        tipo = cuenta.tipo.value if hasattr(cuenta.tipo, "value") else str(cuenta.tipo)
        if tipo == "INGRESO":
            grupo = "INGRESO"
        elif tipo == "EGRESO":
            # El enum del ERP no distingue gasto de costo: los dos son EGRESO.
            # La separacion sale de la clase del PUC —6 es costo de ventas, 5 es
            # gasto—, que es la convencion colombiana. Sin separarlos no hay
            # margen bruto, que es la cifra que mas se mira de este reporte.
            grupo = "COSTO" if cuenta.codigo.startswith("6") else "GASTO"
        else:
            continue
        saldo = mov["debito"] - mov["credito"]
        valor = -saldo if grupo == "INGRESO" else saldo
        grupos[grupo].append({"cuenta_id": cid, "codigo": cuenta.codigo,
                              "nombre": cuenta.nombre, "valor": float(valor)})
        totales[grupo] += valor

    for g in grupos.values():
        g.sort(key=lambda x: x["codigo"])

    bruta = totales["INGRESO"] - totales["COSTO"]
    operacional = bruta - totales["GASTO"]

    return {
        "desde": desde, "hasta": hasta,
        "ingresos": grupos["INGRESO"], "total_ingresos": float(totales["INGRESO"]),
        "costos": grupos["COSTO"], "total_costos": float(totales["COSTO"]),
        "utilidad_bruta": float(bruta),
        "gastos": grupos["GASTO"], "total_gastos": float(totales["GASTO"]),
        "utilidad_operacional": float(operacional),
        "margen_bruto": float(bruta / totales["INGRESO"] * 100)
                        if totales["INGRESO"] else 0.0,
        "margen_operacional": float(operacional / totales["INGRESO"] * 100)
                              if totales["INGRESO"] else 0.0,
    }


# ═══ EVENTOS Y AUDITORÍA ══════════════════════════════════════════════════════

@router.get("/contabilidad/eventos")
async def listar_eventos(
    empresa_id: int, estado: Optional[str] = None,
    limite: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_contabilidad),
):
    """Los hechos económicos venidos de otros módulos y su contabilización.

    Los FALLIDOS son los que hay que mirar: cada uno trae el motivo, que casi
    siempre es una regla contable sin configurar.
    """
    consulta = select(ERPEventoContable).where(
        ERPEventoContable.empresa_id == empresa_id)
    if estado:
        consulta = consulta.where(ERPEventoContable.estado == estado.upper())
    r = await db.execute(consulta.order_by(
        ERPEventoContable.fecha.desc(), ERPEventoContable.id.desc()).limit(limite))
    return [
        {"id": e.id, "modulo": e.modulo, "evento": e.evento,
         "documento_tipo": e.documento_tipo, "documento_id": e.documento_id,
         "documento_numero": e.documento_numero, "fecha": e.fecha,
         "importes": e.importes, "estado": e.estado,
         "comprobante_id": e.comprobante_id, "error": e.error,
         "intentos": e.intentos}
        for e in r.scalars().all()
    ]


@router.post("/contabilidad/eventos/{evento_id}/contabilizar")
async def contabilizar_evento(
    evento_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.contabilizar),
):
    """Vuelve a intentar contabilizar un evento que falló."""
    comp = await erp_motor.contabilizar_evento(db, evento_id, _quien(usuario))
    ev = await db.get(ERPEventoContable, evento_id)
    await db.commit()
    if comp is None:
        raise HTTPException(422, {"contabilidad": ev.error if ev else "No se pudo."})
    return {"comprobante_id": comp.id, "numero": comp.numero}


class AnulacionEntrada(BaseModel):
    motivo: str = Field(min_length=3)


@router.post("/contabilidad/comprobantes/{comprobante_id}/anular")
async def anular_comprobante(
    comprobante_id: int, data: AnulacionEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.anular),
):
    """Anula un comprobante creando su contrario.

    No se borra ni se edita: borrarlo dejaría un hueco en el consecutivo y haría
    imposible explicar por qué el libro de un mes cambió.
    """
    reverso = await erp_motor.reversar(db, comprobante_id, _quien(usuario),
                                        data.motivo)
    await db.commit()
    return {"anulado": comprobante_id, "reverso_id": reverso.id,
            "reverso_numero": reverso.numero}


@router.get("/auditoria")
async def listar_auditoria(
    empresa_id: int,
    entidad: Optional[str] = None, entidad_id: Optional[int] = None,
    limite: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_contabilidad),
):
    """Quién hizo qué. Responde las cinco preguntas de una revisión."""
    consulta = select(ERPAuditoria).where(ERPAuditoria.empresa_id == empresa_id)
    if entidad:
        consulta = consulta.where(ERPAuditoria.entidad == entidad)
    if entidad_id:
        consulta = consulta.where(ERPAuditoria.entidad_id == entidad_id)
    r = await db.execute(consulta.order_by(ERPAuditoria.created_at.desc()).limit(limite))

    def _leer(texto):
        """El detalle vuelve a ser un objeto. La columna es de texto porque ya
        existía así; convertir la tabla a jsonb obligaría a reescribir lo que ya
        está guardado, y el histórico de auditoría es justo lo que no se toca."""
        if not texto:
            return None
        try:
            return json.loads(texto)
        except (TypeError, ValueError):
            return {"texto": texto}

    return [
        {"id": a.id, "entidad": a.entidad, "entidad_id": a.entidad_id,
         "accion": a.accion, "usuario": a.usuario, "creado": a.created_at,
         "antes": _leer(a.datos_antes), "despues": _leer(a.datos_despues),
         "motivo": a.observaciones, "ip": a.ip,
         "documento_origen": a.documento_origen}
        for a in r.scalars().all()
    ]


# ═══ PARAMETRIZACIÓN INICIAL ══════════════════════════════════════════════════

@router.post("/contabilidad/sembrar")
async def sembrar(
    empresa_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.parametrizar),
):
    """Deja una empresa lista para contabilizar: PUC, reglas y tarifas.

    Es idempotente: sobre una empresa que ya tiene cuentas completa lo que falte
    sin pisar lo que alguien haya cambiado.
    """
    empresa = await db.get(ERPEmpresa, empresa_id)
    if empresa is None:
        raise HTTPException(404, "Esa empresa no existe.")

    resultado = await erp_semilla.sembrar_empresa(db, empresa_id)
    resultado["parametros"] = await erp_semilla.sembrar_parametros(db)

    await erp_motor.auditar(
        db, empresa_id=empresa_id, entidad="empresa", entidad_id=empresa_id,
        accion="SEMBRAR", usuario=_quien(usuario), despues=resultado)
    await db.commit()
    return resultado
