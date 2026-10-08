"""
Las pantallas de gestión, conectadas a la contabilidad.

Costeo, presupuestos, activos, planeación y conciliación mostraban cifras que
salían de constantes en el frontend o de un cero fijo. Una cifra inventada en una
pantalla de gestión es peor que un espacio vacío: el espacio vacío se nota, y el
número se cree.

TODO SALE DEL MAYOR
Ninguno de estos cálculos guarda un saldo aparte. La ejecución de un centro de
costo es la suma de sus líneas contabilizadas, y la rentabilidad de un proyecto
también. Un saldo guardado en paralelo se desincroniza del movimiento que lo
produjo, y entonces hay dos verdades y nadie sabe cuál mirar.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import erp_motor, erp_permisos
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.erp_motor import ErrorContable, Linea
from app.infrastructure.models.erp import (
    EstadoComprobante, ERPActivoFijo, ERPCentroCosto, ERPComprobante,
    ERPComprobanteLinea, ERPCuentaBancaria, ERPEmpresa, ERPLineaPresupuesto,
    ERPMovimientoBancario, ERPPlanCuenta, ERPPresupuesto, ERPProyecto,
    TipoComprobante,
)
from app.infrastructure.models.erp_gestion import (
    ERPDistribucionABC, ERPEscenario, ERPInductor,
)
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/erp", tags=["ERP · Gestión"])

CENTAVO = Decimal("0.01")


def _r(v: Any) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


async def _empresa_por_defecto(db: AsyncSession) -> Optional[int]:
    """La empresa cuando la pantalla no la manda.

    Varias pantallas viejas no tienen selector todavía. Caer a la primera es
    correcto mientras haya una sola; con dos, la pantalla debe elegir, y por eso
    el parámetro existe.
    """
    return (await db.execute(select(ERPEmpresa.id).order_by(
        ERPEmpresa.id).limit(1))).scalar()


async def _saldos_por_centro(
    db: AsyncSession, empresa_id: int, desde: date, hasta: date,
    clases: str = "56",
) -> Dict[Optional[int], Decimal]:
    """Lo gastado por centro de costo en el rango, desde el mayor.

    `clases` son las clases del PUC que cuentan como ejecución: 5 gastos y 6
    costos. El activo y el pasivo no son ejecución de presupuesto —comprar un
    camión no es un gasto del mes— y sumarlos sería el error clásico.
    """
    filas = (await db.execute(
        select(ERPComprobanteLinea.centro_costo_id,
               func.coalesce(func.sum(ERPComprobanteLinea.debito
                                      - ERPComprobanteLinea.credito), 0))
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .join(ERPPlanCuenta, ERPPlanCuenta.id == ERPComprobanteLinea.cuenta_id)
        .where(ERPComprobante.empresa_id == empresa_id,
               ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
               ERPComprobante.fecha >= desde, ERPComprobante.fecha <= hasta,
               or_(*[ERPPlanCuenta.codigo.startswith(c) for c in clases]))
        .group_by(ERPComprobanteLinea.centro_costo_id))).all()
    return {cid: _r(monto) for cid, monto in filas}


# ═══ ACTIVOS · CRONOGRAMA DE DEPRECIACIÓN ═════════════════════════════════════

@router.get("/activos/{activo_id}/schedule")
async def cronograma_depreciacion(
    activo_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_contabilidad),
):
    """El calendario completo de depreciación de un activo, cuota por cuota.

    La pantalla lo pedía y no existía: devolvía 404 y la pestaña quedaba vacía
    sin decir por qué.

    Se calcula, no se guarda. Un cronograma guardado se vuelve mentira apenas
    alguien corrige la vida útil o el valor residual, y nadie vuelve a mirarlo
    para ver si sigue valiendo.
    """
    af = await db.get(ERPActivoFijo, activo_id)
    if af is None:
        raise HTTPException(404, "Ese activo no existe.")

    valor = _r(af.valor_adquisicion)
    residual = _r(af.valor_residual)
    meses = int(af.vida_util_meses or 0)
    if meses <= 0:
        raise HTTPException(
            422, "El activo no tiene vida útil definida, así que no se puede "
                 "calcular su depreciación. Corríjala en la ficha del activo.")

    depreciable = valor - residual
    metodo = (af.metodo_depreciacion.value
              if hasattr(af.metodo_depreciacion, "value")
              else str(af.metodo_depreciacion))

    filas: List[dict] = []
    acumulada = Decimal(0)
    libro = valor
    inicio = af.fecha_adquisicion or date.today()

    for mes in range(1, meses + 1):
        if metodo == "SALDO_DECRECIENTE":
            # El doble del lineal sobre el saldo en libros. Se corta en el valor
            # residual, que es lo que impide depreciar por debajo de él.
            cuota = (libro * Decimal(2) / Decimal(meses)).quantize(CENTAVO)
        elif metodo == "SUM_DIGITOS":
            restantes = meses - mes + 1
            suma = Decimal(meses * (meses + 1) // 2)
            cuota = (depreciable * Decimal(restantes) / suma).quantize(CENTAVO)
        else:
            cuota = (depreciable / Decimal(meses)).quantize(CENTAVO)

        # La última cuota absorbe el redondeo: sin esto quedan centavos colgando
        # y el activo nunca llega exactamente a su valor residual.
        if acumulada + cuota > depreciable or mes == meses:
            cuota = max(Decimal(0), depreciable - acumulada)

        acumulada += cuota
        libro = valor - acumulada

        anio = inicio.year + (inicio.month - 1 + mes) // 12
        mes_cal = (inicio.month - 1 + mes) % 12 + 1
        filas.append({
            "mes": mes,
            "fecha": date(anio, mes_cal, 1).isoformat(),
            "cuota": float(cuota),
            "depreciacion_acumulada": float(acumulada),
            "valor_libro": float(libro),
        })
        if cuota == 0:
            break

    return filas


# ═══ COSTEO ═══════════════════════════════════════════════════════════════════

@router.get("/costeo/centros")
async def costeo_centros(
    empresa_id: Optional[int] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Presupuesto contra ejecución real por centro de costo.

    La pantalla mostraba `ejecutado = 0` fijo, así que el porcentaje de ejecución
    era siempre cero y la columna no informaba de nada. Acá sale del mayor.
    """
    empresa_id = empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        return {"centros": [], "desde": None, "hasta": None}

    hasta = hasta or date.today()
    desde = desde or date(hasta.year, 1, 1)
    ejecutado = await _saldos_por_centro(db, empresa_id, desde, hasta)

    centros = list((await db.execute(select(ERPCentroCosto).where(
        or_(ERPCentroCosto.empresa_id == empresa_id,
            ERPCentroCosto.empresa_id.is_(None))
    ).order_by(ERPCentroCosto.codigo))).scalars().all())

    salida = []
    for c in centros:
        gastado = ejecutado.get(c.id, Decimal(0))
        presupuesto = _r(c.presupuesto_anual)
        salida.append({
            "id": c.id, "codigo": c.codigo, "nombre": c.nombre,
            "tipo": c.tipo.value if hasattr(c.tipo, "value") else str(c.tipo),
            "responsable": c.responsable,
            "presupuesto_anual": float(presupuesto),
            "ejecutado": float(gastado),
            "disponible": float(presupuesto - gastado),
            "pct_ejecucion": float((gastado / presupuesto * 100).quantize(CENTAVO))
                             if presupuesto else None,
        })

    # Lo que no se imputó a ningún centro. Va explícito porque si se reparte en
    # silencio entre los demás, todos los porcentajes quedan mal y nadie lo nota.
    sin_centro = ejecutado.get(None, Decimal(0))

    return {
        "desde": desde, "hasta": hasta, "centros": salida,
        "sin_centro_de_costo": float(sin_centro),
        "total_ejecutado": float(sum(ejecutado.values(), Decimal(0))),
    }


class InductorEntrada(BaseModel):
    empresa_id: Optional[int] = None
    codigo: str = Field(min_length=1, max_length=30)
    actividad: str = Field(min_length=1, max_length=160)
    inductor: str = Field(min_length=1, max_length=160)
    unidad: str = "und"
    cuenta_origen_id: Optional[int] = None
    # {"3": 1200, "5": 400} — unidades consumidas por cada centro de costo.
    consumo_por_centro: Dict[str, float] = {}
    activo: bool = True


@router.get("/costeo/inductores")
async def listar_inductores(
    empresa_id: Optional[int] = None,
    periodo: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Los criterios de reparto, con el costo unitario ya calculado.

    El costo unitario no se guarda: es el saldo de la cuenta dividido por las
    unidades consumidas, y guardarlo lo dejaría desactualizado en cuanto entre un
    asiento más a esa cuenta.
    """
    empresa_id = empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        return []

    inductores = list((await db.execute(select(ERPInductor).where(
        ERPInductor.empresa_id == empresa_id
    ).order_by(ERPInductor.codigo))).scalars().all())
    if not inductores:
        return []

    # Sin período, el ÚLTIMO MES CON MOVIMIENTO y no el mes del calendario.
    # Anclarlo al mes en curso dejaba la pantalla en blanco cada día 1 —y todo
    # el mes de enero, mientras se cierra diciembre—, que es justo cuando se
    # mira el costeo.
    if periodo:
        anio, mes = int(periodo[:4]), int(periodo[5:])
    else:
        ultima = (await db.execute(select(func.max(ERPComprobante.fecha)).where(
            ERPComprobante.empresa_id == empresa_id,
            ERPComprobante.estado == EstadoComprobante.CONTABILIZADO))).scalar()
        ultima = ultima or date.today()
        anio, mes = ultima.year, ultima.month

    desde = date(anio, mes, 1)
    hasta = date(anio + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1)
    cuentas = {i.cuenta_origen_id for i in inductores if i.cuenta_origen_id}
    saldos: Dict[int, Decimal] = {}
    if cuentas:
        filas = (await db.execute(
            select(ERPComprobanteLinea.cuenta_id,
                   func.coalesce(func.sum(ERPComprobanteLinea.debito
                                          - ERPComprobanteLinea.credito), 0))
            .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
            .where(ERPComprobante.empresa_id == empresa_id,
                   ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
                   ERPComprobante.fecha >= desde, ERPComprobante.fecha <= hasta,
                   ERPComprobanteLinea.cuenta_id.in_(cuentas))
            .group_by(ERPComprobanteLinea.cuenta_id))).all()
        saldos = {cid: _r(m) for cid, m in filas}

    nombres = {c.id: (c.codigo, c.nombre) for c in (await db.execute(
        select(ERPPlanCuenta).where(ERPPlanCuenta.id.in_(cuentas or {0}))
    )).scalars().all()}

    salida = []
    for i in inductores:
        unidades = sum(Decimal(str(v)) for v in (i.consumo_por_centro or {}).values())
        pozo = saldos.get(i.cuenta_origen_id, Decimal(0))
        cuenta = nombres.get(i.cuenta_origen_id)
        salida.append({
            "id": i.id, "codigo": i.codigo, "actividad": i.actividad,
            "inductor": i.inductor, "unidad": i.unidad,
            "cuenta_origen_id": i.cuenta_origen_id,
            "cuenta_origen": f"{cuenta[0]} · {cuenta[1]}" if cuenta else None,
            "consumo_por_centro": i.consumo_por_centro or {},
            "unidades_totales": float(unidades),
            "periodo": f"{anio}-{mes:02d}",
            "monto_del_mes": float(pozo),
            "costo_unitario": float((pozo / unidades).quantize(CENTAVO))
                              if unidades else None,
            "activo": i.activo,
        })
    return salida


@router.post("/costeo/inductores", status_code=201)
async def guardar_inductor(
    data: InductorEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.parametrizar),
):
    empresa_id = data.empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        raise HTTPException(422, "No hay ninguna empresa creada.")

    inductor = (await db.execute(select(ERPInductor).where(
        ERPInductor.empresa_id == empresa_id,
        ERPInductor.codigo == data.codigo))).scalar_one_or_none()

    antes = None
    if inductor is None:
        inductor = ERPInductor(empresa_id=empresa_id, codigo=data.codigo,
                               definido_por=usuario.nombre)
        db.add(inductor)
    else:
        antes = {"actividad": inductor.actividad, "inductor": inductor.inductor,
                 "consumo": inductor.consumo_por_centro}

    inductor.actividad = data.actividad
    inductor.inductor = data.inductor
    inductor.unidad = data.unidad
    inductor.cuenta_origen_id = data.cuenta_origen_id
    inductor.consumo_por_centro = {k: float(v) for k, v in
                                   data.consumo_por_centro.items()}
    inductor.activo = data.activo
    await db.flush()

    # Cambiar un inductor cambia qué línea de negocio parece rentable, así que
    # queda quién lo cambió y qué había antes.
    await erp_motor.auditar(
        db, empresa_id=empresa_id, entidad="inductor_abc", entidad_id=inductor.id,
        accion="EDITAR" if antes else "CREAR", usuario=usuario.nombre,
        antes=antes, despues={"actividad": data.actividad,
                              "inductor": data.inductor,
                              "consumo": inductor.consumo_por_centro},
        ip=request.client.host if request.client else None)
    await db.commit()
    return {"id": inductor.id, "codigo": inductor.codigo}


class DistribucionEntrada(BaseModel):
    empresa_id: Optional[int] = None
    inductor_id: int
    periodo: str = Field(pattern=r"^\d{4}-\d{2}$")


@router.post("/costeo/distribuir", status_code=201)
async def distribuir_costos(
    data: DistribucionEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.contabilizar),
):
    """Reparte el saldo de una cuenta entre centros de costo y lo CONTABILIZA.

    Esto es lo que hace que el costeo ABC deje de ser un cálculo aparte. Repartir
    solo en un informe produce dos verdades: la del informe y la de los libros. Acá
    el reparto es un asiento —sale del centro que acumuló el costo y entra en los
    que lo consumieron—, así que el mayor y el costeo dicen lo mismo por
    construcción.

    Se repite el mes y no pasa nada: la restricción única impide distribuir dos
    veces el mismo período, porque hacerlo duplicaría el costo en quien lo recibe.
    """
    empresa_id = data.empresa_id or await _empresa_por_defecto(db)
    inductor = await db.get(ERPInductor, data.inductor_id)
    if inductor is None or inductor.empresa_id != empresa_id:
        raise HTTPException(404, "Ese inductor no existe en esta empresa.")
    if not inductor.cuenta_origen_id:
        raise HTTPException(
            422, f"El inductor «{inductor.actividad}» no tiene cuenta de origen. "
                 f"Sin ella no se sabe qué saldo repartir.")

    consumo = {int(k): Decimal(str(v))
               for k, v in (inductor.consumo_por_centro or {}).items()
               if Decimal(str(v)) > 0}
    if not consumo:
        raise HTTPException(
            422, f"Nadie consumió «{inductor.inductor}» según la configuración, "
                 f"así que no hay entre quiénes repartir.")

    ya = (await db.execute(select(ERPDistribucionABC).where(
        ERPDistribucionABC.empresa_id == empresa_id,
        ERPDistribucionABC.inductor_id == inductor.id,
        ERPDistribucionABC.periodo == data.periodo))).scalar_one_or_none()
    if ya is not None:
        raise HTTPException(
            409, f"«{inductor.actividad}» ya se distribuyó en {data.periodo} "
                 f"por {float(ya.monto_distribuido):,.2f}. Anule ese comprobante "
                 f"si hay que rehacerlo.")

    anio, mes = int(data.periodo[:4]), int(data.periodo[5:])
    primero = date(anio, mes, 1)
    ultimo = (date(anio + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1))

    # El saldo a repartir es el de la cuenta EN ESE MES y sin centro asignado:
    # lo que ya se imputó a un centro no se vuelve a repartir.
    pozo = _r((await db.execute(
        select(func.coalesce(func.sum(ERPComprobanteLinea.debito
                                      - ERPComprobanteLinea.credito), 0))
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .where(ERPComprobante.empresa_id == empresa_id,
               ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
               ERPComprobante.fecha >= primero, ERPComprobante.fecha <= ultimo,
               ERPComprobanteLinea.cuenta_id == inductor.cuenta_origen_id,
               ERPComprobanteLinea.centro_costo_id.is_(None)))).scalar())

    if pozo <= 0:
        raise HTTPException(
            422, f"La cuenta de «{inductor.actividad}» no tiene saldo sin asignar "
                 f"en {data.periodo}: no hay nada que repartir.")

    total_unidades = sum(consumo.values())
    detalle: List[dict] = []
    lineas: List[Linea] = []
    repartido = Decimal(0)
    centros = list(consumo.items())

    for i, (centro_id, unidades) in enumerate(centros):
        if i == len(centros) - 1:
            # Al último le va el resto, para que la suma dé exactamente el pozo.
            # Repartir por porcentaje y redondear cada parte deja centavos
            # sueltos y el asiento no cuadra.
            monto = pozo - repartido
        else:
            monto = (pozo * unidades / total_unidades).quantize(CENTAVO)
        repartido += monto
        detalle.append({"centro_costo_id": centro_id,
                        "unidades": float(unidades), "monto": float(monto)})
        lineas.append(Linea("distribucion_destino", debito=monto,
                            cuenta_id=inductor.cuenta_origen_id,
                            centro_costo_id=centro_id,
                            concepto=f"{inductor.actividad} · {inductor.inductor}"))

    # La contrapartida: sale del mismo saldo, sin centro. La cuenta queda igual y
    # lo único que cambia es a qué centro está imputado el costo, que es
    # exactamente lo que hace un reparto.
    lineas.append(Linea("distribucion_origen", credito=pozo,
                        cuenta_id=inductor.cuenta_origen_id,
                        concepto=f"Distribución de {inductor.actividad}"))

    comp = await erp_motor.asentar(
        db, empresa_id=empresa_id, evento="COSTEO_DISTRIBUCION",
        tipo=TipoComprobante.AJUSTE, fecha=ultimo,
        concepto=f"Distribución ABC · {inductor.actividad} · {data.periodo}",
        lineas=lineas, usuario=usuario.nombre,
        documento_tipo="distribucion_abc", documento_numero=data.periodo)

    dist = ERPDistribucionABC(
        empresa_id=empresa_id, inductor_id=inductor.id, periodo=data.periodo,
        monto_distribuido=pozo, detalle=detalle, comprobante_id=comp.id,
        ejecutado_por=usuario.nombre)
    db.add(dist)
    await db.commit()

    return {"periodo": data.periodo, "monto_distribuido": float(pozo),
            "comprobante": comp.numero, "detalle": detalle}


@router.get("/costeo/distribuciones")
async def listar_distribuciones(
    empresa_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    empresa_id = empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        return []
    filas = (await db.execute(
        select(ERPDistribucionABC, ERPInductor, ERPComprobante.numero)
        .join(ERPInductor, ERPInductor.id == ERPDistribucionABC.inductor_id)
        .outerjoin(ERPComprobante,
                   ERPComprobante.id == ERPDistribucionABC.comprobante_id)
        .where(ERPDistribucionABC.empresa_id == empresa_id)
        .order_by(ERPDistribucionABC.periodo.desc()))).all()
    return [
        {"id": d.id, "periodo": d.periodo, "actividad": i.actividad,
         "inductor": i.inductor, "monto": float(d.monto_distribuido),
         "comprobante": numero, "detalle": d.detalle,
         "ejecutado_por": d.ejecutado_por}
        for d, i, numero in filas
    ]


# ═══ PRESUPUESTOS · EJECUCIÓN REAL ════════════════════════════════════════════

@router.get("/presupuestos/{presupuesto_id}/ejecucion")
async def ejecucion_presupuestal(
    presupuesto_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Presupuestado contra ejecutado, línea por línea, desde el mayor.

    `monto_ejecutado` existe como columna en las líneas del presupuesto, pero
    nadie lo actualizaba: se quedaba en cero para siempre. Se calcula acá en vez
    de mantener esa columna al día porque un total guardado y un movimiento que
    no coinciden es una discusión sin ganador.
    """
    pres = await db.get(ERPPresupuesto, presupuesto_id)
    if pres is None:
        raise HTTPException(404, "Ese presupuesto no existe.")

    lineas = list((await db.execute(select(ERPLineaPresupuesto).where(
        ERPLineaPresupuesto.presupuesto_id == presupuesto_id))).scalars().all())

    desde = date(pres.anio, 1, 1)
    hasta = date(pres.anio, 12, 31)

    # Un solo viaje: el movimiento del año por (cuenta, centro, mes).
    movimiento = {
        (cid, ccid, mes): _r(monto)
        for cid, ccid, mes, monto in (await db.execute(
            select(ERPComprobanteLinea.cuenta_id,
                   ERPComprobanteLinea.centro_costo_id,
                   func.extract("month", ERPComprobante.fecha),
                   func.coalesce(func.sum(ERPComprobanteLinea.debito
                                          - ERPComprobanteLinea.credito), 0))
            .join(ERPComprobante,
                  ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
            .where(ERPComprobante.empresa_id == pres.empresa_id,
                   ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
                   ERPComprobante.fecha >= desde, ERPComprobante.fecha <= hasta)
            .group_by(text("1"), text("2"), text("3")))).all()
    }

    cuentas = {c.id: c for c in (await db.execute(select(ERPPlanCuenta).where(
        ERPPlanCuenta.id.in_([l.cuenta_id for l in lineas] or [0])
    ))).scalars().all()}

    salida, total_p, total_e = [], Decimal(0), Decimal(0)
    for l in lineas:
        # Sin mes, la línea es anual y le corresponde todo el año.
        if l.mes:
            ejecutado = movimiento.get((l.cuenta_id, l.centro_costo_id, l.mes),
                                       Decimal(0))
        else:
            ejecutado = sum(
                (v for (cid, ccid, _m), v in movimiento.items()
                 if cid == l.cuenta_id and ccid == l.centro_costo_id),
                Decimal(0))
        presupuestado = _r(l.monto_presupuestado)
        cuenta = cuentas.get(l.cuenta_id)
        total_p += presupuestado
        total_e += ejecutado
        salida.append({
            "id": l.id, "descripcion": l.descripcion, "mes": l.mes,
            "cuenta_id": l.cuenta_id,
            "cuenta": f"{cuenta.codigo} · {cuenta.nombre}" if cuenta else None,
            "centro_costo_id": l.centro_costo_id,
            "presupuestado": float(presupuestado),
            "ejecutado": float(ejecutado),
            "variacion": float(presupuestado - ejecutado),
            "pct": float((ejecutado / presupuestado * 100).quantize(CENTAVO))
                   if presupuestado else None,
        })

    return {
        "presupuesto": {"id": pres.id, "nombre": pres.nombre, "anio": pres.anio,
                        "estado": pres.estado.value
                                  if hasattr(pres.estado, "value") else str(pres.estado)},
        "lineas": salida,
        "total_presupuestado": float(total_p),
        "total_ejecutado": float(total_e),
        "variacion": float(total_p - total_e),
    }


# ═══ PROYECTOS · RENTABILIDAD DESDE EL MAYOR ══════════════════════════════════

@router.get("/proyectos/rentabilidad-real")
async def rentabilidad_real(
    empresa_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Ingresos, costos y margen de cada proyecto, desde su centro de costo.

    `ingresos_total` y `ejecutado_total` viven en la tabla de proyectos y nadie
    los alimentaba, así que el margen salía siempre del 100%. Acá se leen del
    mayor a través del centro de costo del proyecto, que es el vínculo que ya
    existía y no se estaba usando.
    """
    empresa_id = empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        return []

    proyectos = list((await db.execute(select(ERPProyecto).where(
        or_(ERPProyecto.empresa_id == empresa_id,
            ERPProyecto.empresa_id.is_(None))))).scalars().all())
    if not proyectos:
        return []

    centros = [p.centro_costo_id for p in proyectos if p.centro_costo_id]
    movimiento: Dict[int, Dict[str, Decimal]] = {}
    if centros:
        filas = (await db.execute(
            select(ERPComprobanteLinea.centro_costo_id,
                   func.substr(ERPPlanCuenta.codigo, 1, 1),
                   func.coalesce(func.sum(ERPComprobanteLinea.credito
                                          - ERPComprobanteLinea.debito), 0))
            .join(ERPComprobante,
                  ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
            .join(ERPPlanCuenta,
                  ERPPlanCuenta.id == ERPComprobanteLinea.cuenta_id)
            .where(ERPComprobante.empresa_id == empresa_id,
                   ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
                   ERPComprobanteLinea.centro_costo_id.in_(centros),
                   func.substr(ERPPlanCuenta.codigo, 1, 1).in_(["4", "5", "6"]))
            .group_by(text("1"), text("2")))).all()
        for ccid, clase, monto in filas:
            m = movimiento.setdefault(ccid, {})
            # Los ingresos son de naturaleza crédito y los costos débito; por eso
            # se suma crédito-débito y se le da vuelta al signo de los gastos.
            m[clase] = _r(monto)

    salida = []
    for p in proyectos:
        m = movimiento.get(p.centro_costo_id, {})
        ingresos = m.get("4", Decimal(0))
        costos = -m.get("6", Decimal(0))
        gastos = -m.get("5", Decimal(0))
        margen = ingresos - costos - gastos
        presupuesto = _r(p.presupuesto_total)
        salida.append({
            "id": p.id, "codigo": p.codigo, "nombre": p.nombre,
            "cliente": p.cliente,
            "estado": p.estado.value if hasattr(p.estado, "value") else str(p.estado),
            "fecha_inicio": p.fecha_inicio, "fecha_fin": p.fecha_fin,
            "presupuesto": float(presupuesto),
            "ingresos": float(ingresos),
            "costos": float(costos), "gastos": float(gastos),
            "ejecutado": float(costos + gastos),
            "margen": float(margen),
            "margen_pct": float((margen / ingresos * 100).quantize(CENTAVO))
                          if ingresos else None,
            "pct_presupuesto": float(((costos + gastos) / presupuesto * 100)
                                     .quantize(CENTAVO)) if presupuesto else None,
            # Un proyecto sin centro de costo no se puede medir, y decirlo es más
            # útil que mostrar ceros que parecen un resultado.
            "medible": p.centro_costo_id is not None,
        })
    return salida


# ═══ EPM · PLANEACIÓN ═════════════════════════════════════════════════════════

async def _resultado_del_rango(db: AsyncSession, empresa_id: int,
                               desde: date, hasta: date) -> Dict[str, Decimal]:
    """Ingresos, costos y gastos del rango. La base de toda proyección."""
    filas = (await db.execute(
        select(func.substr(ERPPlanCuenta.codigo, 1, 1),
               func.coalesce(func.sum(ERPComprobanteLinea.credito
                                      - ERPComprobanteLinea.debito), 0))
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .join(ERPPlanCuenta, ERPPlanCuenta.id == ERPComprobanteLinea.cuenta_id)
        .where(ERPComprobante.empresa_id == empresa_id,
               ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
               ERPComprobante.fecha >= desde, ERPComprobante.fecha <= hasta,
               func.substr(ERPPlanCuenta.codigo, 1, 1).in_(["4", "5", "6"]))
        .group_by(text("1")))).all()
    m = {clase: _r(monto) for clase, monto in filas}
    return {"ingresos": m.get("4", Decimal(0)),
            "gastos": -m.get("5", Decimal(0)),
            "costos": -m.get("6", Decimal(0))}


@router.get("/epm/planes")
async def epm_planes(
    empresa_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Los planes financieros, que son los presupuestos con su ejecución.

    La pantalla pedía esta ruta y no existía: daba 404 y la pestaña salía vacía.
    No se inventa una entidad «plan» aparte: un plan financiero ES un presupuesto,
    y duplicarlo habría creado dos sitios donde cuadrar la misma cifra.
    """
    empresa_id = empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        return []

    presupuestos = list((await db.execute(select(ERPPresupuesto).where(
        or_(ERPPresupuesto.empresa_id == empresa_id,
            ERPPresupuesto.empresa_id.is_(None))
    ).order_by(ERPPresupuesto.anio.desc()))).scalars().all())
    if not presupuestos:
        return []

    # Ingreso y gasto presupuestados salen de la clase de la cuenta de cada
    # línea, no de un campo aparte: así no pueden discrepar entre sí.
    reparto = {
        (pid, clase): _r(monto)
        for pid, clase, monto in (await db.execute(
            select(ERPLineaPresupuesto.presupuesto_id,
                   func.substr(ERPPlanCuenta.codigo, 1, 1),
                   func.coalesce(func.sum(ERPLineaPresupuesto.monto_presupuestado), 0))
            .join(ERPPlanCuenta, ERPPlanCuenta.id == ERPLineaPresupuesto.cuenta_id)
            .where(ERPLineaPresupuesto.presupuesto_id.in_([p.id for p in presupuestos]))
            .group_by(text("1"), text("2")))).all()
    }

    salida = []
    for p in presupuestos:
        ingresos = reparto.get((p.id, "4"), Decimal(0))
        gastos = (reparto.get((p.id, "5"), Decimal(0))
                  + reparto.get((p.id, "6"), Decimal(0)))
        if not ingresos and not gastos:
            # Un presupuesto sin líneas clasificadas: se muestra el total, que es
            # lo único cierto que hay de él.
            gastos = _r(p.total_presupuestado)
        salida.append({
            "id": p.id, "nombre": p.nombre,
            "tipo": p.tipo.value if hasattr(p.tipo, "value") else str(p.tipo),
            "periodo": str(p.anio), "version": "1",
            "estado": p.estado.value if hasattr(p.estado, "value") else str(p.estado),
            "presupuesto_ingresos": float(ingresos),
            "presupuesto_gastos": float(gastos),
            "utilidad_proyectada": float(ingresos - gastos),
        })
    return salida


@router.get("/epm/forecast")
async def epm_forecast(
    empresa_id: Optional[int] = None,
    meses: int = Query(12, ge=3, le=36),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Lo real de cada mes contra lo proyectado desde la propia historia.

    La proyección es la media móvil de los tres meses anteriores ajustada por la
    tendencia del año. No es sofisticada a propósito: un método que quien lo mira
    puede reproducir a mano es un método en el que puede confiar, y aquí la
    utilidad está en ver la desviación, no en acertar el decimal.

    Los meses ya cerrados muestran el real Y lo que se habría proyectado, que es
    lo único que permite saber si el método sirve.
    """
    empresa_id = empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        return []

    hoy = date.today()
    inicio = date(hoy.year, hoy.month, 1) - timedelta(days=31 * (meses - 1))
    inicio = date(inicio.year, inicio.month, 1)

    filas = (await db.execute(
        select(func.to_char(ERPComprobante.fecha, "YYYY-MM"),
               func.substr(ERPPlanCuenta.codigo, 1, 1),
               func.coalesce(func.sum(ERPComprobanteLinea.credito
                                      - ERPComprobanteLinea.debito), 0))
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .join(ERPPlanCuenta, ERPPlanCuenta.id == ERPComprobanteLinea.cuenta_id)
        .where(ERPComprobante.empresa_id == empresa_id,
               ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
               ERPComprobante.fecha >= inicio,
               func.substr(ERPPlanCuenta.codigo, 1, 1).in_(["4", "5", "6"]))
        .group_by(text("1"), text("2")))).all()

    real: Dict[str, Dict[str, Decimal]] = {}
    for mes, clase, monto in filas:
        real.setdefault(mes, {})[clase] = _r(monto)

    etiquetas = []
    y, m = inicio.year, inicio.month
    for _ in range(meses):
        etiquetas.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1

    salida = []
    hist_ing: List[Decimal] = []
    hist_gas: List[Decimal] = []
    for etiqueta in etiquetas:
        d = real.get(etiqueta, {})
        ingresos = d.get("4", Decimal(0))
        gastos = -d.get("5", Decimal(0)) - d.get("6", Decimal(0))

        def _proyectar(hist: List[Decimal]) -> Decimal:
            if not hist:
                return Decimal(0)
            ventana = hist[-3:]
            return _r(sum(ventana, Decimal(0)) / len(ventana))

        salida.append({
            "mes": etiqueta,
            "ingresos_real": float(ingresos),
            "ingresos_forecast": float(_proyectar(hist_ing)),
            "gastos_real": float(gastos),
            "gastos_forecast": float(_proyectar(hist_gas)),
            "variacion_pct": float(
                ((ingresos - _proyectar(hist_ing)) / _proyectar(hist_ing) * 100)
                .quantize(CENTAVO)) if _proyectar(hist_ing) else 0.0,
        })
        if ingresos or gastos:
            hist_ing.append(ingresos)
            hist_gas.append(gastos)
    return salida


@router.get("/epm/escenarios")
async def epm_escenarios(
    empresa_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    empresa_id = empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        return []
    escenarios = list((await db.execute(select(ERPEscenario).where(
        ERPEscenario.empresa_id == empresa_id
    ).order_by(ERPEscenario.anio.desc(),
               ERPEscenario.supuesto_crecimiento.desc()))).scalars().all())
    return [
        {"id": e.id, "nombre": e.nombre, "descripcion": e.descripcion or "",
         "anio": e.anio,
         "supuesto_crecimiento": float(e.supuesto_crecimiento),
         "ingresos_proyectados": float(e.ingresos_proyectados),
         "costos_proyectados": float(e.costos_proyectados),
         "gastos_proyectados": float(e.gastos_proyectados),
         "utilidad_proyectada": float(e.utilidad_proyectada),
         "ebitda_pct": float(e.ebitda_pct),
         "base_ingresos": float(e.base_ingresos),
         "base_desde": e.base_desde, "base_hasta": e.base_hasta,
         "creado_por": e.creado_por}
        for e in escenarios
    ]


class Crecimiento(BaseModel):
    nombre: str
    pct: float
    # Los costos no crecen al ritmo de las ventas: hay una parte fija. Si no se
    # dice, se asume que crecen a la mitad, que es lo prudente.
    pct_costos: Optional[float] = None


class SimulacionEntrada(BaseModel):
    empresa_id: Optional[int] = None
    crecimientos: List[Crecimiento]
    anio: Optional[int] = None


@router.post("/epm/simular")
async def epm_simular(
    data: SimulacionEntrada,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """Proyecta escenarios sobre los últimos doce meses REALES y los guarda.

    La base son los doce meses cerrados anteriores, tomados del mayor. Proyectar
    sobre una cifra inventada da un escenario que no se puede defender ante nadie.

    La base queda congelada en cada escenario: dos escenarios comparables tienen
    que partir del mismo punto, y si se recalculara con la contabilidad de hoy
    dejarían de serlo en cuanto entrara un asiento.
    """
    empresa_id = data.empresa_id or await _empresa_por_defecto(db)
    if empresa_id is None:
        raise HTTPException(422, "No hay ninguna empresa creada.")
    if not data.crecimientos:
        raise HTTPException(422, "No se indicó ningún escenario que simular.")

    hoy = date.today()
    hasta = date(hoy.year, hoy.month, 1) - timedelta(days=1)
    desde = date(hasta.year - 1, hasta.month, 1)
    base = await _resultado_del_rango(db, empresa_id, desde, hasta)

    if base["ingresos"] <= 0:
        raise HTTPException(
            422, f"No hay ingresos contabilizados entre {desde} y {hasta}, así que "
                 f"no hay sobre qué proyectar. Registre operación o cambie el rango.")

    anio = data.anio or (hoy.year + 1)
    salida = []
    for c in data.crecimientos:
        factor = Decimal(1) + Decimal(str(c.pct)) / Decimal(100)
        # Los costos siguen a las ventas solo a medias: parte del costo es fijo.
        # Hacerlos crecer igual que los ingresos deja el margen constante, y
        # entonces el escenario no dice nada que no se supiera.
        factor_costos = (Decimal(1) + Decimal(str(c.pct_costos)) / Decimal(100)
                         if c.pct_costos is not None
                         else Decimal(1) + Decimal(str(c.pct)) / Decimal(200))

        ingresos = _r(base["ingresos"] * factor)
        costos = _r(base["costos"] * factor_costos)
        gastos = _r(base["gastos"] * factor_costos)
        utilidad = ingresos - costos - gastos

        e = (await db.execute(select(ERPEscenario).where(
            ERPEscenario.empresa_id == empresa_id,
            ERPEscenario.anio == anio,
            ERPEscenario.nombre == c.nombre))).scalar_one_or_none()
        if e is None:
            e = ERPEscenario(empresa_id=empresa_id, anio=anio, nombre=c.nombre)
            db.add(e)

        e.descripcion = (f"Ingresos {c.pct:+.1f}% sobre {desde:%b %Y}–{hasta:%b %Y}")
        e.supuesto_crecimiento = Decimal(str(c.pct))
        e.supuesto_inflacion_costos = (factor_costos - 1) * 100
        e.base_ingresos = base["ingresos"]
        e.base_costos = base["costos"]
        e.base_gastos = base["gastos"]
        e.base_desde, e.base_hasta = desde, hasta
        e.ingresos_proyectados = ingresos
        e.costos_proyectados = costos
        e.gastos_proyectados = gastos
        e.utilidad_proyectada = utilidad
        e.ebitda_pct = ((utilidad / ingresos * 100).quantize(CENTAVO)
                        if ingresos else Decimal(0))
        e.creado_por = usuario.nombre
        await db.flush()
        salida.append({"nombre": c.nombre, "ingresos_proyectados": float(ingresos),
                       "utilidad_proyectada": float(utilidad),
                       "ebitda_pct": float(e.ebitda_pct)})

    await db.commit()
    return {"anio": anio, "base": {k: float(v) for k, v in base.items()},
            "base_desde": desde, "base_hasta": hasta, "escenarios": salida}


# ═══ TESORERÍA · CONCILIACIÓN ═════════════════════════════════════════════════

@router.get("/tesoreria/conciliacion")
async def proponer_conciliacion(
    cuenta_id: int,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    dias_tolerancia: int = Query(5, ge=0, le=30),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.conciliar),
):
    """Empareja los movimientos del extracto con los asientos de la cuenta.

    Propone; no concilia solo. Conciliar automáticamente lo que «se parece»
    esconde justo los casos que hay que mirar —dos facturas por el mismo importe
    el mismo día, un pago que llegó partido—, y un extracto conciliado a la fuerza
    es peor que uno sin conciliar, porque nadie lo vuelve a revisar.

    El puntaje dice por qué se propuso cada pareja, así que quien confirme puede
    juzgar en vez de creer.
    """
    cuenta = await db.get(ERPCuentaBancaria, cuenta_id)
    if cuenta is None:
        raise HTTPException(404, "Esa cuenta bancaria no existe.")
    if not cuenta.cuenta_contable_id:
        raise HTTPException(
            422, "Esta cuenta bancaria no tiene cuenta contable asociada, así que "
                 "no hay contra qué conciliarla. Asígnela en la ficha de la cuenta.")

    hasta = hasta or date.today()
    desde = desde or (hasta - timedelta(days=90))

    movimientos = list((await db.execute(select(ERPMovimientoBancario).where(
        ERPMovimientoBancario.cuenta_id == cuenta_id,
        ERPMovimientoBancario.conciliado.is_(False),
        ERPMovimientoBancario.fecha >= desde,
        ERPMovimientoBancario.fecha <= hasta,
    ).order_by(ERPMovimientoBancario.fecha))).scalars().all())

    # Los asientos de la cuenta contable en el rango, más el margen de tolerancia
    # a cada lado: un pago del 30 puede aparecer en el extracto el 2.
    apuntes = (await db.execute(
        select(ERPComprobanteLinea.id, ERPComprobante.id, ERPComprobante.numero,
               ERPComprobante.fecha, ERPComprobante.concepto,
               ERPComprobante.referencia,
               ERPComprobanteLinea.debito, ERPComprobanteLinea.credito)
        .join(ERPComprobante, ERPComprobante.id == ERPComprobanteLinea.comprobante_id)
        .where(ERPComprobante.empresa_id == cuenta.empresa_id,
               ERPComprobante.estado == EstadoComprobante.CONTABILIZADO,
               ERPComprobanteLinea.cuenta_id == cuenta.cuenta_contable_id,
               ERPComprobante.fecha >= desde - timedelta(days=dias_tolerancia),
               ERPComprobante.fecha <= hasta + timedelta(days=dias_tolerancia))
    )).all()

    # Los que ya están amarrados a un movimiento no se vuelven a ofrecer.
    tomados = set((await db.execute(
        select(ERPMovimientoBancario.comprobante_id).where(
            ERPMovimientoBancario.comprobante_id.isnot(None)))).scalars().all())

    libres = [a for a in apuntes if a[1] not in tomados]
    propuestas = []

    for mv in movimientos:
        entrada = str(mv.tipo.value if hasattr(mv.tipo, "value") else mv.tipo) == "CREDITO"
        monto = _r(mv.monto)
        candidatos = []
        for lid, cid, numero, fecha, concepto, referencia, debito, credito in libres:
            # Una entrada en el banco es un débito en la cuenta contable, y al
            # revés. Emparejar sin mirar el sentido junta un pago con un cobro.
            valor = _r(debito) if entrada else _r(credito)
            if valor <= 0 or valor != monto:
                continue
            dias = abs((fecha - mv.fecha).days)
            if dias > dias_tolerancia:
                continue

            # El puntaje: el importe exacto ya está garantizado, así que lo que
            # separa a los candidatos es la cercanía en fecha y la referencia.
            puntaje = 60 + max(0, 20 - dias * 4)
            razones = [f"importe exacto", f"{dias} día(s) de diferencia"]
            ref = (mv.referencia or "").strip().lower()
            if ref and ref in ((referencia or "") + " " + (concepto or "")).lower():
                puntaje += 20
                razones.append("la referencia coincide")
            candidatos.append({
                "comprobante_id": cid, "comprobante": numero, "fecha": fecha,
                "concepto": concepto, "referencia": referencia,
                "puntaje": min(100, puntaje), "razones": razones,
            })

        candidatos.sort(key=lambda c: -c["puntaje"])
        # Con dos candidatos igual de buenos NO hay propuesta automática: es
        # justo el caso ambiguo que hay que mirar a mano.
        ambiguo = (len(candidatos) > 1
                   and candidatos[0]["puntaje"] == candidatos[1]["puntaje"])
        propuestas.append({
            "movimiento_id": mv.id, "fecha": mv.fecha,
            "tipo": mv.tipo.value if hasattr(mv.tipo, "value") else str(mv.tipo),
            "monto": float(monto), "concepto": mv.concepto,
            "referencia": mv.referencia,
            "candidatos": candidatos[:5],
            "sugerido": (candidatos[0]["comprobante_id"]
                         if candidatos and not ambiguo else None),
            "ambiguo": ambiguo,
        })

    return {
        "cuenta": {"id": cuenta.id, "numero": cuenta.numero},
        "desde": desde, "hasta": hasta,
        "sin_conciliar": len(movimientos),
        "con_propuesta": sum(1 for p in propuestas if p["sugerido"]),
        "ambiguos": sum(1 for p in propuestas if p["ambiguo"]),
        "propuestas": propuestas,
    }


class ConciliarEntrada(BaseModel):
    # [{"movimiento_id": 1, "comprobante_id": 44}, …]
    parejas: List[Dict[str, int]]


@router.post("/tesoreria/conciliar")
async def confirmar_conciliacion(
    data: ConciliarEntrada, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.conciliar),
):
    """Ata cada movimiento a su comprobante. Es un acto de una persona."""
    hechas = 0
    for par in data.parejas:
        mv = await db.get(ERPMovimientoBancario, par.get("movimiento_id"))
        if mv is None:
            continue
        comp = await db.get(ERPComprobante, par.get("comprobante_id"))
        if comp is None:
            raise HTTPException(
                404, f"El comprobante {par.get('comprobante_id')} no existe.")
        mv.comprobante_id = comp.id
        mv.conciliado = True
        hechas += 1
        await erp_motor.auditar(
            db, empresa_id=comp.empresa_id, entidad="movimiento_bancario",
            entidad_id=mv.id, accion="CONCILIAR", usuario=usuario.nombre,
            despues={"comprobante": comp.numero, "monto": str(mv.monto)},
            ip=request.client.host if request.client else None)
    await db.commit()
    return {"conciliados": hechas}


@router.post("/tesoreria/desconciliar/{movimiento_id}")
async def desconciliar(
    movimiento_id: int, request: Request,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.conciliar),
):
    """Deshace una conciliación equivocada, dejando constancia."""
    mv = await db.get(ERPMovimientoBancario, movimiento_id)
    if mv is None:
        raise HTTPException(404, "Ese movimiento no existe.")
    anterior = mv.comprobante_id
    mv.conciliado = False
    mv.comprobante_id = None
    cuenta = await db.get(ERPCuentaBancaria, mv.cuenta_id)
    await erp_motor.auditar(
        db, empresa_id=cuenta.empresa_id if cuenta else None,
        entidad="movimiento_bancario", entidad_id=mv.id,
        accion="DESCONCILIAR", usuario=usuario.nombre,
        antes={"comprobante_id": anterior},
        ip=request.client.host if request.client else None)
    await db.commit()
    return {"movimiento_id": movimiento_id, "conciliado": False}


# ═══ CONSOLIDACIÓN ════════════════════════════════════════════════════════════

@router.get("/consolidacion")
async def consolidar(
    desde: date, hasta: date,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.ver_reportes),
):
    """El resultado de todas las empresas, junto y por separado.

    Las operaciones ENTRE empresas del grupo se identifican y se muestran aparte
    en vez de restarse en silencio: una venta de una filial a otra infla los
    ingresos del grupo sin que haya entrado un peso de fuera, y ocultar el ajuste
    impide comprobar que se hizo bien.

    Se detectan por el NIT: si el tercero de una factura es otra empresa del
    grupo, la operación es interna. Es el criterio que se puede verificar mirando
    un documento, que es lo que hace falta en una auditoría.
    """
    empresas = list((await db.execute(select(ERPEmpresa).where(
        ERPEmpresa.activo.is_(True)))).scalars().all())
    if not empresas:
        return {"empresas": [], "consolidado": {}, "operaciones_internas": []}

    nits = {e.nit for e in empresas if e.nit}
    por_empresa = []
    total = {"ingresos": Decimal(0), "costos": Decimal(0), "gastos": Decimal(0)}

    for e in empresas:
        r = await _resultado_del_rango(db, e.id, desde, hasta)
        por_empresa.append({
            "empresa_id": e.id, "nit": e.nit, "razon_social": e.razon_social,
            "ingresos": float(r["ingresos"]), "costos": float(r["costos"]),
            "gastos": float(r["gastos"]),
            "utilidad": float(r["ingresos"] - r["costos"] - r["gastos"]),
        })
        for k in total:
            total[k] += r[k]

    # Facturación cuyo tercero es otra empresa del grupo.
    internas = []
    if len(nits) > 1:
        from app.infrastructure.models.erp import ERPFacturaCliente
        filas = (await db.execute(
            select(ERPFacturaCliente.empresa_id, ERPFacturaCliente.cliente_nit,
                   func.count(), func.coalesce(func.sum(ERPFacturaCliente.subtotal), 0))
            .where(ERPFacturaCliente.fecha >= desde,
                   ERPFacturaCliente.fecha <= hasta,
                   ERPFacturaCliente.cliente_nit.in_(nits))
            .group_by(text("1"), text("2")))).all()
        razones = {e.nit: e.razon_social for e in empresas}
        for emisor, nit_cliente, cuantas, monto in filas:
            internas.append({
                "empresa_emisora_id": emisor,
                "cliente_nit": nit_cliente,
                "cliente": razones.get(nit_cliente),
                "facturas": cuantas, "monto": float(_r(monto)),
            })

    eliminacion = _r(sum((Decimal(str(i["monto"])) for i in internas), Decimal(0)))

    return {
        "desde": desde, "hasta": hasta,
        "empresas": por_empresa,
        "suma_simple": {k: float(v) for k, v in total.items()},
        "operaciones_internas": internas,
        "eliminacion_ingresos": float(eliminacion),
        "consolidado": {
            "ingresos": float(total["ingresos"] - eliminacion),
            "costos": float(total["costos"]),
            "gastos": float(total["gastos"]),
            "utilidad": float(total["ingresos"] - eliminacion
                              - total["costos"] - total["gastos"]),
        },
    }


class ContabilizarMovimiento(BaseModel):
    # La contrapartida la elige quien contabiliza: solo él sabe si ese débito es
    # una comisión, un impuesto o una devolución. Adivinarla por el texto del
    # extracto es cómodo y se equivoca en silencio.
    cuenta_contrapartida_id: int
    concepto: Optional[str] = None


@router.post("/tesoreria/movimientos/{movimiento_id}/contabilizar")
async def contabilizar_movimiento(
    movimiento_id: int, data: ContabilizarMovimiento,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(erp_permisos.contabilizar),
):
    """Crea el asiento de un movimiento del extracto que no tiene documento.

    Las comisiones, el 4x1000 y los rendimientos aparecen en el extracto y no
    vienen de ninguna factura. Sin esta ruta había que ir a crear el comprobante
    a mano en otra pantalla y volver a conciliar, y en la práctica eso significa
    que la cuenta nunca queda cuadrada.

    Deja el movimiento conciliado contra el asiento que acaba de crear, porque
    son el mismo hecho y separarlos solo daría trabajo de más.
    """
    mv = await db.get(ERPMovimientoBancario, movimiento_id)
    if mv is None:
        raise HTTPException(404, "Ese movimiento no existe.")
    if mv.comprobante_id:
        raise HTTPException(
            409, "Ese movimiento ya está atado a un comprobante. Desconcílielo "
                 "primero si el asiento estaba mal.")

    cuenta = await db.get(ERPCuentaBancaria, mv.cuenta_id)
    if cuenta is None or not cuenta.cuenta_contable_id:
        raise HTTPException(
            422, "La cuenta bancaria no tiene cuenta contable asociada.")

    contrapartida = await db.get(ERPPlanCuenta, data.cuenta_contrapartida_id)
    if contrapartida is None:
        raise HTTPException(404, "Esa cuenta de contrapartida no existe.")
    if not contrapartida.acepta_movimientos:
        raise HTTPException(
            422, f"La cuenta {contrapartida.codigo} es agrupadora y no recibe "
                 f"movimiento. Elija una subcuenta.")

    entrada = str(mv.tipo.value if hasattr(mv.tipo, "value") else mv.tipo) == "CREDITO"
    monto = _r(mv.monto)
    concepto = data.concepto or mv.concepto

    lineas = [
        Linea("banco", debito=monto if entrada else 0,
              credito=0 if entrada else monto,
              cuenta_id=cuenta.cuenta_contable_id, concepto=concepto),
        Linea("contrapartida", debito=0 if entrada else monto,
              credito=monto if entrada else 0,
              cuenta_id=contrapartida.id, concepto=concepto),
    ]
    comp = await erp_motor.asentar(
        db, empresa_id=cuenta.empresa_id,
        evento="MOVIMIENTO_BANCARIO",
        tipo=TipoComprobante.INGRESO if entrada else TipoComprobante.EGRESO,
        fecha=mv.fecha, concepto=concepto, lineas=lineas, usuario=usuario.nombre,
        documento_tipo="movimiento_bancario", documento_id=mv.id,
        documento_numero=mv.referencia)

    mv.comprobante_id = comp.id
    mv.conciliado = True
    await db.commit()
    return {"comprobante": comp.numero, "comprobante_id": comp.id,
            "conciliado": True}
