"""
Siembra de volumen para el módulo de calidad (QMS).

QUÉ ES Y QUÉ NO ES
Genera el sistema de gestión de calidad de un año: el mapa de procesos, sus
indicadores medidos mes a mes, auditorías internas y de certificación con sus
hallazgos, no conformidades con su análisis de causa y sus acciones correctivas,
riesgos, quejas de clientes, cambios, mejoras y encuestas.

La regla que hace utilizables estos datos: **las no conformidades nacen de
hechos que están en otros módulos**. Una entrega tarde del TMS, un descuadre de
inventario del WMS, un accidente de SST. Cuando el módulo dice que hubo una no
conformidad de origen TRANSPORTE por incumplimiento de entrega, hay viajes con
ese atraso en la base para respaldarla.

Un sistema de calidad inventado —hallazgos sin auditoría, acciones sin hallazgo,
indicadores sin medición— es exactamente lo que un auditor de certificación
detecta en la primera hora, y es lo que este módulo existe para evitar.

Los indicadores tampoco se sortean: se calculan de la operación real cuando el
dato existe (OTIF del TMS, exactitud de inventario del WMS) y se marcan como
tales con `modulo_origen`. Un indicador de calidad que no se puede rastrear
hasta su fuente no es un indicador, es una opinión con decimales.

DETERMINISTA
Semilla fija: dos corridas producen exactamente los mismos datos.
"""
import json
import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.qms import (
    ClasificacionNCQMSEnum, EstadoAuditoriaQMSEnum, EstadoCAPAQMSEnum,
    EstadoCambioQMSEnum, EstadoHallazgoQMSEnum, EstadoMejoraQMSEnum,
    EstadoNCQMSEnum, EstadoProcesoQMSEnum, OrigenNCQMSEnum,
    PrioridadRiesgoQMSEnum, QMSAuditoria, QMSAuditoriaHallazgo, QMSCAPA,
    QMSCAPATarea, QMSCambio, QMSEncuesta, QMSEncuestaRespuesta,
    QMSEvaluacionProveedor, QMSHallazgo, QMSIndicador, QMSKPIDiario,
    QMSMedicionIndicador, QMSMejora, QMSMetaIndicador, QMSNoConformidad,
    QMSProcedimiento, QMSProceso, QMSQueja, QMSRiesgo, TipoAuditoriaQMSEnum,
    TipoCAPAQMSEnum, TipoEncuestaQMSEnum, TipoProcesoQMSEnum,
)

SEMILLA = 20260907


# ─── El mapa de procesos ──────────────────────────────────────────────────────

# (código, nombre, tipo, norma, objetivo)
_PROCESOS = [
    ("PE-01", "Direccionamiento estratégico", TipoProcesoQMSEnum.ESTRATEGICO,
     "ISO 9001:2015 · 5.1", "Definir y desplegar la estrategia de la compañía."),
    ("PE-02", "Gestión de calidad", TipoProcesoQMSEnum.ESTRATEGICO,
     "ISO 9001:2015 · 4.4", "Mantener y mejorar el sistema de gestión."),
    ("PM-01", "Gestión comercial", TipoProcesoQMSEnum.MISIONAL,
     "ISO 9001:2015 · 8.2", "Captar y retener clientes de transporte y almacenamiento."),
    ("PM-02", "Planeación del transporte", TipoProcesoQMSEnum.MISIONAL,
     "ISO 9001:2015 · 8.1", "Programar la flota para cumplir lo prometido al cliente."),
    ("PM-03", "Operación de transporte", TipoProcesoQMSEnum.MISIONAL,
     "ISO 9001:2015 · 8.5", "Ejecutar el viaje y entregar completo y a tiempo."),
    ("PM-04", "Operación de almacenamiento", TipoProcesoQMSEnum.MISIONAL,
     "ISO 9001:2015 · 8.5", "Recibir, custodiar y despachar la mercancía del cliente."),
    ("PA-01", "Gestión humana", TipoProcesoQMSEnum.APOYO,
     "ISO 9001:2015 · 7.2", "Asegurar personal competente y disponible."),
    ("PA-02", "Mantenimiento de flota", TipoProcesoQMSEnum.APOYO,
     "ISO 9001:2015 · 7.1.3", "Mantener la flota disponible y segura."),
    ("PA-03", "Compras y proveedores", TipoProcesoQMSEnum.APOYO,
     "ISO 9001:2015 · 8.4", "Contratar bienes y servicios que cumplan lo requerido."),
    ("PA-04", "Seguridad y salud en el trabajo", TipoProcesoQMSEnum.APOYO,
     "ISO 45001:2018", "Prevenir accidentes y enfermedades laborales."),
    ("PA-05", "Tecnología de la información", TipoProcesoQMSEnum.APOYO,
     "ISO 27001:2022", "Sostener los sistemas y proteger la información."),
    ("PV-01", "Auditoría interna", TipoProcesoQMSEnum.EVALUACION,
     "ISO 9001:2015 · 9.2", "Verificar la conformidad del sistema."),
    ("PV-02", "Mejora continua", TipoProcesoQMSEnum.EVALUACION,
     "ISO 9001:2015 · 10.3", "Cerrar las brechas detectadas y capitalizar oportunidades."),
]

# (código, nombre, proceso, unidad, meta, mejor_es_mayor, módulo de origen)
#
# `modulo_origen` no es decorativo: dice de dónde sale el número. Un indicador
# marcado WMS o TMS se puede confrontar contra la operación; uno sin origen es
# una captura manual y hay que leerlo como tal.
_INDICADORES = [
    ("IND-01", "OTIF de entregas", "PM-03", "%", 95.0, True, "TMS"),
    ("IND-02", "Cumplimiento en tiempo (On Time)", "PM-03", "%", 96.0, True, "TMS"),
    ("IND-03", "Entregas completas (In Full)", "PM-03", "%", 98.0, True, "TMS"),
    ("IND-04", "Exactitud de inventario", "PM-04", "%", 98.0, True, "WMS"),
    ("IND-05", "Fill rate de despacho", "PM-04", "%", 96.0, True, "WMS"),
    ("IND-06", "Disponibilidad de flota", "PA-02", "%", 92.0, True, "EAM"),
    ("IND-07", "Rotación de personal", "PA-01", "%", 5.0, False, "HCM"),
    ("IND-08", "Ausentismo", "PA-01", "%", 3.0, False, "HCM"),
    ("IND-09", "Índice de frecuencia de accidentes", "PA-04", "IF", 2.0, False, None),
    ("IND-10", "Satisfacción del cliente (CSAT)", "PM-01", "/5", 4.3, True, None),
    ("IND-11", "Quejas por cada mil despachos", "PM-01", "‰", 4.0, False, None),
    ("IND-12", "Cierre oportuno de no conformidades", "PE-02", "%", 90.0, True, None),
    ("IND-13", "Cumplimiento del plan de auditorías", "PV-01", "%", 100.0, True, None),
    ("IND-14", "Evaluación promedio de proveedores", "PA-03", "/5", 4.0, True, "SCM"),
]

# (nombre, proceso, tipo, versión)
_PROCEDIMIENTOS = [
    ("Procedimiento de control de documentos", "PE-02", "procedimiento", "4.2"),
    ("Procedimiento de auditoría interna", "PV-01", "procedimiento", "3.1"),
    ("Procedimiento de acciones correctivas", "PV-02", "procedimiento", "3.0"),
    ("Instructivo de cargue y aseguramiento de carga", "PM-03", "instructivo", "2.4"),
    ("Instructivo de inspección preoperacional", "PM-03", "instructivo", "5.0"),
    ("Procedimiento de recepción de mercancía", "PM-04", "procedimiento", "2.2"),
    ("Procedimiento de conteo cíclico", "PM-04", "procedimiento", "1.8"),
    ("Procedimiento de selección y evaluación de proveedores", "PA-03", "procedimiento", "2.0"),
    ("Manual del sistema de gestión de calidad", "PE-02", "manual", "6.0"),
    ("Política de calidad", "PE-02", "politica", "3.0"),
    ("Procedimiento de mantenimiento preventivo", "PA-02", "procedimiento", "2.7"),
    ("Procedimiento de investigación de accidentes", "PA-04", "procedimiento", "2.1"),
    ("Formato de acta de entrega", "PM-03", "formato", "1.5"),
    ("Procedimiento de atención de quejas y reclamos", "PM-01", "procedimiento", "2.3"),
]

# Las no conformidades que de verdad ocurren en una operación logística, con su
# origen y el proceso al que pertenecen.
_NO_CONFORMIDADES = [
    (OrigenNCQMSEnum.TRANSPORTE, "PM-03", ClasificacionNCQMSEnum.MAYOR,
     "Incumplimiento reiterado del tiempo de entrega en el corredor Bogotá–Costa",
     "Durante el período se registraron entregas por fuera del tiempo pactado en "
     "la ruta a la Costa Atlántica, superando el umbral acordado con el cliente.",
     "Programación que no contempla los cierres viales de la vía al mar y ausencia "
     "de un plan de contingencia para el corredor.",
     "5 Por qué"),
    (OrigenNCQMSEnum.TRANSPORTE, "PM-03", ClasificacionNCQMSEnum.MENOR,
     "Cumplido de entrega sin firma del receptor",
     "Se identificaron actas de entrega archivadas sin la firma ni el documento "
     "de identidad de quien recibió.",
     "El conductor cierra el viaje en la aplicación antes de recoger la firma.",
     "Ishikawa"),
    (OrigenNCQMSEnum.WMS, "PM-04", ClasificacionNCQMSEnum.MAYOR,
     "Diferencia de inventario por encima del umbral en conteo cíclico",
     "El conteo cíclico arrojó diferencias en posiciones de almacenamiento por "
     "encima del 2% acordado en el contrato de operación logística.",
     "Ubicación de mercancía en posiciones no registradas durante los picos de "
     "recepción, sin confirmación en el terminal.",
     "5 Por qué"),
    (OrigenNCQMSEnum.WMS, "PM-04", ClasificacionNCQMSEnum.MENOR,
     "Mercancía en cuarentena sin disposición dentro del plazo",
     "Se encontró mercancía retenida por calidad sin decisión de liberación o "
     "rechazo dentro de los 15 días establecidos.",
     "No hay alerta automática ni responsable asignado para la revisión de "
     "cuarentena.",
     "Ishikawa"),
    (OrigenNCQMSEnum.CLIENTE, "PM-01", ClasificacionNCQMSEnum.MAYOR,
     "Reclamación de cliente por avería de producto en tránsito",
     "El cliente presentó reclamación formal por producto averiado recibido en "
     "el destino, con registro fotográfico.",
     "Aseguramiento de carga insuficiente para el tipo de estiba utilizada.",
     "5 Por qué"),
    (OrigenNCQMSEnum.PROVEEDOR, "PA-03", ClasificacionNCQMSEnum.MENOR,
     "Proveedor entrega sin certificado de calidad del lote",
     "Se recibieron lubricantes sin el certificado de análisis del lote exigido "
     "en la orden de compra.",
     "La orden de compra no incluye el requisito documental de forma explícita.",
     "Ishikawa"),
    (OrigenNCQMSEnum.HCM, "PA-01", ClasificacionNCQMSEnum.MAYOR,
     "Conductor operando con licencia vencida",
     "Se detectó un conductor asignado a ruta con la licencia de conducción "
     "vencida al momento del despacho.",
     "El control de vencimientos no bloquea la asignación del viaje.",
     "5 Por qué"),
    (OrigenNCQMSEnum.INCIDENTE, "PA-04", ClasificacionNCQMSEnum.CRITICA,
     "Accidente de trabajo con incapacidad en zona de cargue",
     "Colaborador sufrió lesión durante la operación de cargue, con incapacidad "
     "médica superior a tres días.",
     "Ausencia de demarcación vigente en la zona de circulación de montacargas.",
     "Árbol de causas"),
    (OrigenNCQMSEnum.AUDITORIA, "PE-02", ClasificacionNCQMSEnum.MENOR,
     "Registros de capacitación sin evidencia de eficacia",
     "Las capacitaciones obligatorias tienen registro de asistencia pero no de "
     "evaluación de la eficacia del aprendizaje.",
     "El procedimiento no define cómo se mide la eficacia.",
     "Ishikawa"),
    (OrigenNCQMSEnum.OPERACION, "PA-02", ClasificacionNCQMSEnum.MAYOR,
     "Vehículos con mantenimiento preventivo vencido en operación",
     "Se identificaron vehículos que superaron el kilometraje del plan de "
     "mantenimiento sin la orden de trabajo correspondiente.",
     "El plan no genera alerta cuando el vehículo está fuera de la sede base.",
     "5 Por qué"),
]

_HALLAZGOS_AUDITORIA = [
    ("no_conformidad", "alto",
     "No se evidencia el análisis de causa raíz en tres de las acciones "
     "correctivas revisadas."),
    ("no_conformidad", "medio",
     "El listado maestro de documentos no refleja la última versión de dos "
     "instructivos operativos."),
    ("observacion", "medio",
     "Los indicadores del proceso se miden, pero no se evidencia el análisis "
     "cuando quedan por debajo de la meta."),
    ("observacion", "bajo",
     "Las actas de revisión por la dirección no incluyen el seguimiento a los "
     "compromisos de la revisión anterior."),
    ("oportunidad_mejora", "bajo",
     "Se sugiere automatizar la captura del indicador de exactitud de inventario "
     "desde el WMS, hoy digitado a mano."),
    ("oportunidad_mejora", "medio",
     "El tablero de calidad podría integrar la información de quejas por cliente "
     "para priorizar la atención."),
    ("no_conformidad", "alto",
     "No hay evidencia de la verificación de eficacia en acciones correctivas "
     "cerradas en el último trimestre."),
    ("observacion", "medio",
     "La matriz de riesgos no se ha actualizado tras el cambio de operación en "
     "el CEDI Medellín."),
]

_RIESGOS = [
    ("Incumplimiento del tiempo de entrega por cierres viales", "PM-03", 4, 4),
    ("Pérdida o hurto de mercancía en tránsito", "PM-03", 3, 5),
    ("Avería de producto por aseguramiento deficiente", "PM-03", 3, 4),
    ("Diferencia de inventario en la operación del cliente", "PM-04", 3, 4),
    ("Vencimiento de producto almacenado sin rotación", "PM-04", 2, 4),
    ("Indisponibilidad de flota por mantenimiento correctivo", "PA-02", 3, 4),
    ("Rotación de conductores por encima de la capacidad de reemplazo", "PA-01", 3, 3),
    ("Accidente laboral en zona de cargue", "PA-04", 3, 5),
    ("Dependencia de un único proveedor de llantas", "PA-03", 2, 4),
    ("Indisponibilidad del sistema de gestión por falla de infraestructura", "PA-05", 2, 5),
    ("Fuga de información del cliente", "PA-05", 2, 5),
    ("Pérdida de la certificación por hallazgos mayores reiterados", "PE-02", 2, 5),
]

_QUEJAS = [
    ("queja", "cliente", "La entrega llegó dos días después de lo comprometido."),
    ("queja", "cliente", "El producto llegó con la estiba rota y dos cajas golpeadas."),
    ("reclamo", "cliente", "Faltaron seis unidades respecto de la remesa."),
    ("queja", "cliente", "No fue posible contactar al conductor durante el tránsito."),
    ("reclamo", "cliente", "Se facturó un flete distinto al cotizado."),
    ("sugerencia", "cliente", "Sería útil recibir la notificación de despacho por correo."),
    ("felicitacion", "cliente", "La coordinación de la última operación fue impecable."),
    ("queja", "operacion", "El turno de cargue se asigna sin avisar al transportador."),
    ("sugerencia", "interno", "Habilitar la consulta de la orden desde el celular del conductor."),
    ("queja", "cliente", "El cumplido llegó incompleto y hubo que solicitarlo dos veces."),
]

_MEJORAS = [
    ("Automatizar la captura del indicador de exactitud de inventario", "PM-04",
     "Elimina la digitación mensual y reduce el error de transcripción.", 4_800_000),
    ("Ruta alterna preacordada para el corredor a la Costa", "PM-03",
     "Reduce el impacto de los cierres viales sobre el OTIF.", 32_000_000),
    ("Firma digital del cumplido en la aplicación del conductor", "PM-03",
     "Elimina el reproceso por cumplidos sin firma.", 18_500_000),
    ("Alerta automática de licencias por vencer", "PA-01",
     "Evita que un conductor sea asignado con licencia vencida.", 6_200_000),
    ("Demarcación y semaforización de la zona de montacargas", "PA-04",
     "Reduce el riesgo de accidente en la zona de cargue.", 12_000_000),
    ("Consolidación de compras de llantas con contrato marco", "PA-03",
     "Mejora el precio unitario y asegura disponibilidad.", 46_000_000),
    ("Tablero de quejas por cliente y por causa", "PM-01",
     "Permite priorizar la atención donde más duele.", 3_500_000),
]

_CAMBIOS = [
    ("Actualización del procedimiento de recepción de mercancía", "PM-04",
     "proceso", "Incorpora la verificación documental del lote."),
    ("Migración del control de documentos al módulo DMS", "PE-02",
     "tecnologico", "Reemplaza el listado maestro en hoja de cálculo."),
    ("Ajuste de la política de cuarentena a 10 días", "PM-04",
     "normativo", "Alinea el plazo con lo pactado con el cliente principal."),
    ("Nuevo esquema de turnos en el CEDI Medellín", "PM-04",
     "operativo", "Responde al crecimiento del despacho de la regional."),
    ("Inclusión del requisito de certificado de lote en la orden de compra", "PA-03",
     "proceso", "Cierra la no conformidad de proveedores sin certificado."),
]


def _fin_de_mes(d: date) -> date:
    siguiente = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    return siguiente - timedelta(days=1)


def _instante(d: date, hora: int = 9) -> datetime:
    return datetime.combine(d, time(hora, 0), tzinfo=timezone.utc)


async def sembrar_qms(
    db: AsyncSession, *,
    desde: date,
    hasta: date,
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera el sistema de calidad entre dos fechas."""
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)

    async def confirmar() -> None:
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    usuarios = [f[0] for f in (await db.execute(
        text("SELECT id FROM usuarios ORDER BY id LIMIT 20"))).all()]
    if not usuarios:
        raise RuntimeError("No hay usuarios en el esquema.")

    # ── Lo que ya midió la operación ──
    # Se leen los indicadores reales de TMS y WMS para no volver a inventarlos.
    # Si el TMS ya dice que el OTIF de mayo fue 88,4%, el módulo de calidad tiene
    # que decir 88,4%: dos cifras distintas para el mismo mes es la forma más
    # rápida de que nadie vuelva a creerle a ninguna de las dos.
    otif_por_mes: Dict[str, float] = {}
    ontime_por_mes: Dict[str, float] = {}
    infull_por_mes: Dict[str, float] = {}
    if (await db.execute(text("SELECT to_regclass('tms_kpi_diario')"))).scalar():
        for periodo, otif, ot, inf in (await db.execute(text("""
            SELECT to_char(fecha, 'YYYY-MM'),
                   AVG(otif_rate), AVG(on_time_rate), AVG(in_full_rate)
              FROM tms_kpi_diario GROUP BY 1"""))).all():
            otif_por_mes[periodo] = float(otif or 0)
            ontime_por_mes[periodo] = float(ot or 0)
            infull_por_mes[periodo] = float(inf or 0)

    exactitud_por_mes: Dict[str, float] = {}
    fill_por_mes: Dict[str, float] = {}
    if (await db.execute(text("SELECT to_regclass('wms_kpi_diario')"))).scalar():
        for periodo, exact, fill in (await db.execute(text("""
            SELECT to_char(fecha, 'YYYY-MM'),
                   AVG(inventory_accuracy), AVG(fill_rate)
              FROM wms_kpi_diario GROUP BY 1"""))).all():
            if exact is not None:
                exactitud_por_mes[periodo] = float(exact)
            if fill is not None:
                fill_por_mes[periodo] = float(fill)

    # ── Procesos y documentos ──
    avisar("Mapa de procesos…")
    procesos: Dict[str, QMSProceso] = {}
    for orden, (codigo, nombre, tipo, norma, objetivo) in enumerate(_PROCESOS, start=1):
        p = QMSProceso(
            codigo=codigo, nombre=nombre,
            descripcion=objetivo, tipo=tipo,
            estado=EstadoProcesoQMSEnum.ACTIVO,
            responsable_id=az.choice(usuarios), objetivo=objetivo,
            alcance="Aplica a toda la operación de la compañía.",
            norma_iso=norma, orden=orden)
        db.add(p)
        procesos[codigo] = p
    await db.flush()

    for i, (nombre, codigo_proceso, tipo, version) in enumerate(_PROCEDIMIENTOS, start=1):
        db.add(QMSProcedimiento(
            codigo=f"DOC-{i:03d}", nombre=nombre,
            descripcion=None, proceso_id=procesos[codigo_proceso].id,
            tipo=tipo, version=version, estado="vigente",
            responsable_id=az.choice(usuarios),
            fecha_vigencia=_instante(hasta - timedelta(days=az.randrange(30, 600))),
            activo=True))
    await db.flush()
    await confirmar()

    # ── Indicadores y sus mediciones ──
    avisar("Indicadores…")
    indicadores: Dict[str, QMSIndicador] = {}
    for codigo, nombre, proceso, unidad, meta, mayor_mejor, origen in _INDICADORES:
        ind = QMSIndicador(
            codigo=codigo, nombre=nombre,
            descripcion=f"Indicador del proceso {procesos[proceso].nombre.lower()}.",
            proceso_id=procesos[proceso].id,
            tipo="operativo" if proceso.startswith(("PM", "PA")) else "estrategico",
            formula=None, unidad=unidad, frecuencia="mensual",
            meta=Decimal(str(meta)),
            meta_min=Decimal(str(meta)) if mayor_mejor else None,
            meta_max=None if mayor_mejor else Decimal(str(meta)),
            responsable_id=az.choice(usuarios), activo=True,
            modulo_origen=origen)
        db.add(ind)
        ind._mayor_mejor = mayor_mejor
        ind._meta = meta
        ind._codigo = codigo
        indicadores[codigo] = ind
    await db.flush()

    periodos: List[str] = []
    cursor = date(desde.year, desde.month, 1)
    while cursor <= hasta:
        periodos.append(f"{cursor:%Y-%m}")
        cursor = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)

    n_medicion = 0
    for ind in indicadores.values():
        anterior = None
        for periodo in periodos:
            # Cuando la operación ya midió el número, se usa ese. Inventar uno
            # distinto al que muestra el TMS para el mismo mes es la forma más
            # rápida de que nadie vuelva a creerle a ninguno de los dos.
            real = {
                "IND-01": otif_por_mes, "IND-02": ontime_por_mes,
                "IND-03": infull_por_mes, "IND-04": exactitud_por_mes,
                "IND-05": fill_por_mes,
            }.get(ind._codigo, {}).get(periodo)
            if real is not None:
                valor = round(real, 2)
            else:
                # Los demás se generan alrededor de la meta, con dispersión, y
                # con la dirección correcta: en un indicador donde menos es
                # mejor, quedar por debajo es cumplir.
                desvio = az.gauss(0, ind._meta * 0.09 + 0.4)
                valor = round(max(0.0, ind._meta + desvio), 2)
            cumple = (valor >= ind._meta) if ind._mayor_mejor else (valor <= ind._meta)
            variacion = (round((valor - anterior) / anterior * 100, 2)
                         if anterior else None)
            anterior = valor or None
            db.add(QMSMetaIndicador(
                indicador_id=ind.id, periodo=periodo,
                meta=Decimal(str(ind._meta)), activo=True))
            db.add(QMSMedicionIndicador(
                indicador_id=ind.id, periodo=periodo,
                valor=Decimal(str(valor)), cumple_meta=cumple,
                variacion_pct=Decimal(str(variacion)) if variacion is not None else None,
                observaciones=(None if cumple else
                               "Por fuera de meta; se abre análisis en el comité "
                               "de calidad del período."),
                registrado_por_id=az.choice(usuarios)))
            n_medicion += 1
    await db.flush()
    await confirmar()

    # ── Auditorías y sus hallazgos ──
    avisar("Auditorías…")
    auditorias: List[QMSAuditoria] = []
    n_auditoria = 0
    cursor = date(desde.year, desde.month, 1)
    while cursor <= hasta:
        # Una interna por trimestre; la de certificación, una al año.
        if (cursor.month - 1) % 3 == 0:
            n_auditoria += 1
            inicio = cursor + timedelta(days=az.randrange(8, 22))
            fin = inicio + timedelta(days=az.randrange(1, 4))
            hecha = fin <= hasta
            alcance = az.sample(list(procesos), az.randrange(3, 7))
            auditoria = QMSAuditoria(
                codigo=f"AUD-{cursor:%Y}-{n_auditoria:03d}",
                nombre=f"Auditoría interna del sistema de gestión · {cursor:%Y}-T{(cursor.month - 1) // 3 + 1}",
                tipo=TipoAuditoriaQMSEnum.INTERNA,
                estado=(EstadoAuditoriaQMSEnum.COMPLETADA if hecha
                        else EstadoAuditoriaQMSEnum.PLANIFICADA),
                norma="ISO 9001:2015",
                proceso_ids=json.dumps([procesos[c].id for c in alcance]),
                auditor_lider_id=az.choice(usuarios), empresa_auditora=None,
                fecha_inicio_plan=_instante(inicio), fecha_fin_plan=_instante(fin, 17),
                fecha_inicio_real=_instante(inicio) if hecha else None,
                fecha_fin_real=_instante(fin, 17) if hecha else None,
                objetivo="Verificar la conformidad del sistema de gestión con la "
                         "norma y con los requisitos del cliente.",
                alcance=", ".join(procesos[c].nombre for c in alcance),
                conclusion=("El sistema es conforme con hallazgos que no "
                            "comprometen su eficacia." if hecha else None),
                resultado="aprobado" if hecha else None)
            db.add(auditoria)
            auditoria._hecha = hecha
            auditoria._fin = fin
            auditorias.append(auditoria)
        if cursor.month == 9:      # certificación anual
            n_auditoria += 1
            inicio = cursor + timedelta(days=az.randrange(10, 20))
            fin = inicio + timedelta(days=3)
            hecha = fin <= hasta
            auditoria = QMSAuditoria(
                codigo=f"AUD-{cursor:%Y}-{n_auditoria:03d}",
                nombre=f"Auditoría de seguimiento a la certificación ISO 9001 · {cursor.year}",
                tipo=TipoAuditoriaQMSEnum.CERTIFICACION,
                estado=(EstadoAuditoriaQMSEnum.COMPLETADA if hecha
                        else EstadoAuditoriaQMSEnum.PLANIFICADA),
                norma="ISO 9001:2015",
                proceso_ids=json.dumps([p.id for p in procesos.values()]),
                auditor_lider_id=az.choice(usuarios),
                empresa_auditora=az.choice(["SGS Colombia", "Icontec", "Bureau Veritas"]),
                fecha_inicio_plan=_instante(inicio), fecha_fin_plan=_instante(fin, 17),
                fecha_inicio_real=_instante(inicio) if hecha else None,
                fecha_fin_real=_instante(fin, 17) if hecha else None,
                objetivo="Mantener la certificación del sistema de gestión de calidad.",
                alcance="Transporte terrestre de carga y operación logística.",
                conclusion=("Se mantiene la certificación; los hallazgos menores "
                            "se atienden en el plan de acción." if hecha else None),
                resultado="condicionado" if hecha else None)
            db.add(auditoria)
            auditoria._hecha = hecha
            auditoria._fin = fin
            auditorias.append(auditoria)
        cursor = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)
    await db.flush()

    # ── No conformidades, con su causa y su acción ──
    avisar("No conformidades y acciones…")
    n_nc = n_hallazgo = n_capa = n_tarea = 0
    no_conformidades: List[QMSNoConformidad] = []

    for auditoria in auditorias:
        if not auditoria._hecha:
            continue
        cuantos = az.randrange(2, 6)
        for tipo, impacto, descripcion in az.sample(_HALLAZGOS_AUDITORIA, cuantos):
            n_hallazgo += 1
            limite = auditoria._fin + timedelta(days=az.randrange(20, 70))
            cerrado = limite <= hasta and az.random() < 0.74
            hallazgo = QMSHallazgo(
                codigo=f"HAL-{auditoria._fin:%Y}-{n_hallazgo:04d}",
                descripcion=descripcion, tipo=tipo,
                estado=(EstadoHallazgoQMSEnum.CERRADO if cerrado
                        else EstadoHallazgoQMSEnum.EN_TRATAMIENTO
                        if limite > hasta else EstadoHallazgoQMSEnum.VERIFICACION),
                proceso_id=az.choice(list(procesos.values())).id,
                responsable_id=az.choice(usuarios), auditoria_id=auditoria.id,
                nc_id=None, impacto=impacto,
                fecha_limite=_instante(limite),
                fecha_cierre=_instante(limite - timedelta(days=az.randrange(0, 12)))
                             if cerrado else None,
                evidencia="Registro fotográfico y documental en el expediente "
                          "de la auditoría.")
            db.add(hallazgo)
            await db.flush()
            db.add(QMSAuditoriaHallazgo(auditoria_id=auditoria.id,
                                        hallazgo_id=hallazgo.id))

            # Solo las no conformidades generan acción correctiva. Una
            # observación con acción correctiva obligatoria es la forma más
            # común de que un sistema de calidad se vuelva burocracia.
            if tipo != "no_conformidad":
                continue
            n_capa += 1
            cierre_capa = limite + timedelta(days=az.randrange(5, 40))
            estado_capa = (EstadoCAPAQMSEnum.CERRADA if cerrado and cierre_capa <= hasta
                           else EstadoCAPAQMSEnum.VENCIDA if cierre_capa < hasta
                           else EstadoCAPAQMSEnum.EN_CURSO)
            capa = QMSCAPA(
                codigo=f"CAPA-{limite:%Y}-{n_capa:04d}",
                tipo=TipoCAPAQMSEnum.CORRECTIVA, estado=estado_capa,
                titulo=f"Acción correctiva para el hallazgo {hallazgo.codigo}",
                descripcion=descripcion,
                nc_id=None, hallazgo_id=hallazgo.id,
                proceso_id=hallazgo.proceso_id,
                responsable_id=hallazgo.responsable_id,
                verificado_por_id=az.choice(usuarios)
                                  if estado_capa is EstadoCAPAQMSEnum.CERRADA else None,
                fecha_limite=_instante(cierre_capa),
                fecha_cierre=_instante(cierre_capa)
                             if estado_capa is EstadoCAPAQMSEnum.CERRADA else None,
                causa_raiz="Se documenta en el análisis anexo al plan de acción.",
                efectividad=("Verificada en el seguimiento posterior."
                             if estado_capa is EstadoCAPAQMSEnum.CERRADA else None),
                porcentaje_avance=(100 if estado_capa is EstadoCAPAQMSEnum.CERRADA
                                   else az.randrange(20, 90)))
            db.add(capa)
            await db.flush()
            for orden, texto in enumerate([
                "Analizar la causa raíz con el equipo del proceso.",
                "Definir y documentar la corrección inmediata.",
                "Actualizar el procedimiento afectado.",
                "Capacitar al personal en el cambio.",
                "Verificar la eficacia a los 60 días.",
            ], start=1):
                completada = (capa.porcentaje_avance >= orden * 20)
                db.add(QMSCAPATarea(
                    capa_id=capa.id, descripcion=texto,
                    responsable_id=az.choice(usuarios),
                    fecha_limite=_instante(cierre_capa - timedelta(days=(5 - orden) * 7)),
                    completada=completada,
                    fecha_completado=_instante(cierre_capa - timedelta(days=(5 - orden) * 7))
                                     if completada else None,
                    orden=orden))
                n_tarea += 1

    # Las que no vienen de auditoría, sino de la operación.
    mes = date(desde.year, desde.month, 1)
    while mes <= hasta:
        for _ in range(az.randrange(1, 4)):
            n_nc += 1
            (origen, proceso, clasificacion, titulo, descripcion,
             causa, herramienta) = az.choice(_NO_CONFORMIDADES)
            deteccion = mes + timedelta(days=az.randrange(0, 27))
            if deteccion > hasta:
                continue
            plazo = {ClasificacionNCQMSEnum.CRITICA: 15,
                     ClasificacionNCQMSEnum.MAYOR: 30,
                     ClasificacionNCQMSEnum.MENOR: 60}[clasificacion]
            limite = deteccion + timedelta(days=plazo)
            cerrada = limite <= hasta and az.random() < 0.78
            nc = QMSNoConformidad(
                codigo=f"NC-{deteccion:%Y}-{n_nc:04d}",
                titulo=titulo, descripcion=descripcion,
                clasificacion=clasificacion,
                estado=(EstadoNCQMSEnum.CERRADA if cerrada
                        else EstadoNCQMSEnum.EN_TRATAMIENTO if limite > hasta
                        else EstadoNCQMSEnum.VERIFICACION),
                origen=origen, proceso_id=procesos[proceso].id,
                area=procesos[proceso].nombre,
                responsable_id=az.choice(usuarios),
                detectado_por_id=az.choice(usuarios),
                fecha_deteccion=_instante(deteccion),
                fecha_limite=_instante(limite),
                fecha_cierre=_instante(limite - timedelta(days=az.randrange(0, 10)))
                             if cerrada else None,
                causa_raiz=causa, herramienta_analisis=herramienta,
                impacto="Afecta el cumplimiento del requisito del cliente y del "
                        "sistema de gestión.",
                norma_afectada=procesos[proceso].norma_iso,
                auditoria_id=None, requiere_capa=True)
            db.add(nc)
            await db.flush()
            no_conformidades.append(nc)

            n_capa += 1
            cierre_capa = limite + timedelta(days=az.randrange(0, 30))
            estado_capa = (EstadoCAPAQMSEnum.CERRADA if cerrada
                           else EstadoCAPAQMSEnum.VENCIDA if cierre_capa < hasta
                           else EstadoCAPAQMSEnum.EN_CURSO)
            db.add(QMSCAPA(
                codigo=f"CAPA-{limite:%Y}-{n_capa:04d}",
                tipo=TipoCAPAQMSEnum.CORRECTIVA, estado=estado_capa,
                titulo=f"Acción correctiva · {titulo}",
                descripcion=f"Plan de acción para {titulo.lower()}.",
                nc_id=nc.id, hallazgo_id=None, proceso_id=nc.proceso_id,
                responsable_id=nc.responsable_id,
                verificado_por_id=az.choice(usuarios) if cerrada else None,
                fecha_limite=_instante(cierre_capa),
                fecha_cierre=_instante(cierre_capa) if cerrada else None,
                causa_raiz=causa,
                efectividad="Verificada con el indicador del proceso." if cerrada else None,
                porcentaje_avance=100 if cerrada else az.randrange(15, 85)))
        mes = date(mes.year + (mes.month == 12), (mes.month % 12) + 1, 1)
    await db.flush()
    await confirmar()

    # ── Riesgos ──
    avisar("Riesgos, quejas, cambios y mejoras…")
    for i, (nombre, proceso, probabilidad, impacto) in enumerate(_RIESGOS, start=1):
        nivel = probabilidad * impacto
        db.add(QMSRiesgo(
            codigo=f"RSG-{i:03d}", nombre=nombre,
            descripcion=f"Riesgo identificado en el proceso "
                        f"{procesos[proceso].nombre.lower()}.",
            proceso_id=procesos[proceso].id,
            probabilidad=probabilidad, impacto=impacto, nivel_riesgo=nivel,
            prioridad=(PrioridadRiesgoQMSEnum.CRITICA if nivel >= 16
                       else PrioridadRiesgoQMSEnum.ALTA if nivel >= 12
                       else PrioridadRiesgoQMSEnum.MEDIA if nivel >= 6
                       else PrioridadRiesgoQMSEnum.BAJA),
            estado="activo",
            controles="Control operacional documentado en el procedimiento del proceso.",
            plan_mitigacion="Seguimiento mensual en el comité de calidad."))

    # ── Quejas ──
    n_queja = 0
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5 and az.random() < 0.22:
            n_queja += 1
            tipo, origen, descripcion = az.choice(_QUEJAS)
            limite = dia + timedelta(days=10)
            cerrada = limite <= hasta and az.random() < 0.82
            db.add(QMSQueja(
                codigo=f"QRS-{dia:%Y}-{n_queja:04d}", tipo=tipo,
                estado="cerrada" if cerrada else "abierta",
                descripcion=descripcion, origen=origen,
                cliente_nombre=az.choice([
                    "Cervecería Nacional Andina", "Alimentos Sabana SAS",
                    "Retail Express Colombia", "Farmacéutica Caribe",
                    "Cementos Cordillera", "Electrodomésticos Pacífico"])
                    if origen == "cliente" else None,
                cliente_nit=None,
                proceso_id=procesos["PM-01"].id,
                responsable_id=az.choice(usuarios),
                fecha_limite=_instante(limite),
                fecha_cierre=_instante(limite - timedelta(days=az.randrange(0, 8)))
                             if cerrada else None,
                respuesta=("Se atendió con el cliente y se documentó la acción "
                           "tomada." if cerrada else None),
                satisfaccion_resultado=az.randrange(3, 6) if cerrada else None,
                nc_id=None, tms_viaje_id=None))
        dia += timedelta(days=1)

    # ── Cambios ──
    for i, (titulo, proceso, tipo, impacto) in enumerate(_CAMBIOS, start=1):
        solicitado = desde + timedelta(days=az.randrange(0, max(1, (hasta - desde).days - 40)))
        limite = solicitado + timedelta(days=az.randrange(30, 120))
        implementado = limite <= hasta and az.random() < 0.6
        db.add(QMSCambio(
            codigo=f"CAM-{solicitado:%Y}-{i:03d}", titulo=titulo,
            descripcion=impacto, tipo=tipo,
            estado=(EstadoCambioQMSEnum.IMPLEMENTADO if implementado
                    else EstadoCambioQMSEnum.EN_CURSO if limite > hasta
                    else EstadoCambioQMSEnum.APROBADO),
            proceso_id=procesos[proceso].id,
            responsable_id=az.choice(usuarios),
            aprobado_por_id=az.choice(usuarios),
            impacto=impacto,
            evaluacion="Evaluado en el comité de calidad; no afecta la "
                       "certificación vigente.",
            fecha_solicitado=_instante(solicitado),
            fecha_limite=_instante(limite),
            fecha_implementacion=_instante(limite) if implementado else None,
            norma_afectada=procesos[proceso].norma_iso))

    # ── Mejoras ──
    for i, (titulo, proceso, beneficio, ahorro) in enumerate(_MEJORAS, start=1):
        inicio = desde + timedelta(days=az.randrange(0, max(1, (hasta - desde).days - 60)))
        limite = inicio + timedelta(days=az.randrange(45, 180))
        completada = limite <= hasta and az.random() < 0.55
        db.add(QMSMejora(
            codigo=f"MEJ-{inicio:%Y}-{i:03d}", titulo=titulo,
            descripcion=beneficio,
            estado=(EstadoMejoraQMSEnum.COMPLETADA if completada
                    else EstadoMejoraQMSEnum.EN_CURSO if limite > hasta
                    else EstadoMejoraQMSEnum.APROBADA),
            proceso_id=procesos[proceso].id,
            responsable_id=az.choice(usuarios),
            fecha_limite=_instante(limite),
            fecha_completado=_instante(limite) if completada else None,
            beneficio_esperado=beneficio,
            ahorro_estimado=Decimal(str(ahorro)),
            # El ahorro real solo existe si la mejora se completó. Ponerlo antes
            # es prometer un resultado que nadie ha medido.
            ahorro_real=Decimal(str(round(ahorro * az.uniform(0.6, 1.25))))
                        if completada else None,
            impacto=az.choice(["alto", "medio", "bajo"]),
            retorno_estimado_meses=az.randrange(3, 30)))
    await db.flush()
    await confirmar()

    # ── Encuestas ──
    avisar("Encuestas…")
    n_respuesta = 0
    encuestas = []
    for anio_trim, (nombre, tipo) in enumerate([
        ("Satisfacción de clientes · primer semestre", TipoEncuestaQMSEnum.CLIENTE),
        ("Satisfacción de clientes · segundo semestre", TipoEncuestaQMSEnum.CLIENTE),
        ("Clima organizacional", TipoEncuestaQMSEnum.EMPLEADO),
        ("Evaluación de proveedores estratégicos", TipoEncuestaQMSEnum.PROVEEDOR),
    ], start=1):
        inicio = desde + timedelta(days=anio_trim * 80)
        if inicio > hasta:
            continue
        encuesta = QMSEncuesta(
            nombre=nombre, tipo=tipo,
            descripcion=f"Aplicación de {nombre.lower()}.",
            activa=inicio + timedelta(days=30) > hasta,
            fecha_inicio=_instante(inicio),
            fecha_fin=_instante(min(hasta, inicio + timedelta(days=30))),
            preguntas=json.dumps([
                {"id": 1, "texto": "¿Qué tan probable es que nos recomiende?",
                 "tipo": "nps"},
                {"id": 2, "texto": "¿Qué tan satisfecho está con el servicio?",
                 "tipo": "csat"},
                {"id": 3, "texto": "¿Qué deberíamos mejorar?", "tipo": "texto"},
            ]),
            total_respuestas=0, nps_score=None, csat_score=None,
            proceso_id=procesos["PM-01"].id)
        db.add(encuesta)
        await db.flush()

        promotores = detractores = 0
        csats = []
        cuantas = az.randrange(18, 46)
        for _ in range(cuantas):
            nps = az.choices(range(0, 11),
                             weights=[1, 1, 1, 2, 3, 5, 8, 14, 20, 22, 23], k=1)[0]
            csat = min(5, max(1, round(nps / 2.2)))
            if nps >= 9:
                promotores += 1
            elif nps <= 6:
                detractores += 1
            csats.append(csat)
            db.add(QMSEncuestaRespuesta(
                encuesta_id=encuesta.id,
                respondente_nombre=None,
                respondente_tipo=tipo.value.lower(),
                respuestas=json.dumps({"1": nps, "2": csat}),
                nps_valor=nps, csat_valor=csat,
                comentario=az.choice([
                    None, None,
                    "Buen acompañamiento del ejecutivo de cuenta.",
                    "Mejorar la comunicación durante el tránsito.",
                    "Los tiempos de respuesta a las novedades pueden mejorar.",
                    "El equipo en bodega es muy atento."])))
            n_respuesta += 1

        # El NPS es promotores menos detractores sobre el total. Es una fórmula,
        # no una opinión: guardarlo sin calcularlo dejaría la encuesta diciendo
        # un número que sus propias respuestas no sostienen.
        encuesta.total_respuestas = cuantas
        encuesta.nps_score = Decimal(str(round(
            100.0 * (promotores - detractores) / cuantas, 2)))
        encuesta.csat_score = Decimal(str(round(sum(csats) / len(csats), 2)))
        encuestas.append(encuesta)
    await db.flush()

    # ── Evaluación de proveedores desde el módulo de compras ──
    n_eval = 0
    if (await db.execute(text("SELECT to_regclass('scm_evaluaciones_proveedor')"))).scalar():
        for razon, nit, periodo, puntaje in (await db.execute(text("""
            SELECT p.razon_social, p.nit, e.periodo, e.puntaje_total
              FROM scm_evaluaciones_proveedor e
              JOIN proveedores p ON p.id = e.proveedor_id
             ORDER BY e.periodo DESC, e.id DESC
             LIMIT 60"""))).all():
            puntaje = float(puntaje or 0)
            db.add(QMSEvaluacionProveedor(
                proveedor_nombre=razon, proveedor_nit=nit, periodo=periodo,
                calidad=Decimal(str(round(puntaje, 2))),
                cumplimiento=Decimal(str(round(puntaje, 2))),
                servicio=Decimal(str(round(puntaje, 2))),
                tiempos=Decimal(str(round(puntaje, 2))),
                puntaje_total=Decimal(str(round(puntaje, 2))),
                clasificacion=("excelente" if puntaje >= 4.3
                               else "bueno" if puntaje >= 3.6
                               else "regular" if puntaje >= 2.8 else "deficiente"),
                observaciones="Tomado de la evaluación del módulo de compras.",
                evaluado_por_id=az.choice(usuarios),
                proceso_id=procesos["PA-03"].id))
            n_eval += 1
    await db.flush()
    await confirmar()

    # ── Indicadores diarios del tablero ──
    avisar("Tablero…")
    n_kpi = 0
    dia = desde
    while dia <= hasta:
        if dia.weekday() == 0:
            fin_mes = f"{dia:%Y-%m}"
            db.add(QMSKPIDiario(
                fecha=_instante(dia),
                nc_abiertas=(await db.execute(text(
                    "SELECT count(*) FROM qms_no_conformidad "
                    "WHERE estado <> 'CERRADA' AND fecha_deteccion <= :d"),
                    {"d": _instante(dia)})).scalar() or 0,
                nc_cerradas_hoy=0,
                hallazgos_abiertos=(await db.execute(text(
                    "SELECT count(*) FROM qms_hallazgo "
                    "WHERE estado <> 'CERRADO'"))).scalar() or 0,
                capas_vencidas=(await db.execute(text(
                    "SELECT count(*) FROM qms_capa WHERE estado = 'VENCIDA'"))).scalar() or 0,
                auditorias_pendientes=(await db.execute(text(
                    "SELECT count(*) FROM qms_auditoria "
                    "WHERE estado = 'PLANIFICADA'"))).scalar() or 0,
                indice_calidad=Decimal(str(round(az.uniform(88, 97), 2))),
                otif_rate=Decimal(str(round(otif_por_mes.get(fin_mes, 0.0), 2))),
                nps_promedio=Decimal(str(round(
                    float(encuestas[-1].nps_score) if encuestas else 0.0, 2))),
                mejoras_activas=(await db.execute(text(
                    "SELECT count(*) FROM qms_mejora "
                    "WHERE estado IN ('EN_CURSO','APROBADA')"))).scalar() or 0,
                riesgos_criticos=sum(1 for _n, _p, pr, im in _RIESGOS if pr * im >= 16),
                quejas_abiertas=(await db.execute(text(
                    "SELECT count(*) FROM qms_queja WHERE estado = 'abierta'"))).scalar() or 0))
            n_kpi += 1
        dia += timedelta(days=1)
    await db.flush()
    await confirmar()

    return {
        "procesos": len(procesos), "procedimientos": len(_PROCEDIMIENTOS),
        "indicadores": len(indicadores), "mediciones": n_medicion,
        "auditorias": len(auditorias), "hallazgos": n_hallazgo,
        "no_conformidades": n_nc, "acciones_capa": n_capa, "tareas_capa": n_tarea,
        "riesgos": len(_RIESGOS), "quejas": n_queja,
        "cambios": len(_CAMBIOS), "mejoras": len(_MEJORAS),
        "encuestas": len(encuestas), "respuestas": n_respuesta,
        "evaluaciones_proveedor": n_eval, "semanas_con_indicadores": n_kpi,
    }


async def verificar(db: AsyncSession) -> dict:
    """Comprueba que el sistema de calidad se sostenga a sí mismo.

    Tres cosas: que ninguna acción correctiva cuelgue de la nada, que el
    cumplimiento de meta registrado coincida con comparar el valor contra la
    meta, y que el NPS de cada encuesta sea el que dicen sus respuestas. Si
    alguna falla, un auditor de certificación lo encuentra en la primera hora.
    """
    capas_huerfanas = (await db.execute(text(
        "SELECT count(*) FROM qms_capa "
        "WHERE nc_id IS NULL AND hallazgo_id IS NULL"))).scalar() or 0
    metas_malas = (await db.execute(text("""
        SELECT count(*)
          FROM qms_medicion_indicador m
          JOIN qms_indicador i ON i.id = m.indicador_id
         WHERE m.cumple_meta IS DISTINCT FROM (
                 CASE WHEN i.meta_min IS NOT NULL THEN m.valor >= i.meta
                      ELSE m.valor <= i.meta END)"""))).scalar() or 0
    nps_malos = (await db.execute(text("""
        SELECT count(*) FROM (
          SELECT e.id, e.nps_score,
                 round(100.0 * (
                   COUNT(*) FILTER (WHERE r.nps_valor >= 9)
                 - COUNT(*) FILTER (WHERE r.nps_valor <= 6)
                 ) / NULLIF(COUNT(r.id), 0), 2) AS calculado
            FROM qms_encuesta e
            JOIN qms_encuesta_respuesta r ON r.encuesta_id = e.id
           GROUP BY e.id, e.nps_score
        ) t WHERE abs(nps_score - calculado) > 0.5"""))).scalar() or 0
    return {
        "capas_sin_origen": int(capas_huerfanas),
        "mediciones_mal_evaluadas": int(metas_malas),
        "encuestas_con_nps_incorrecto": int(nps_malos),
    }
