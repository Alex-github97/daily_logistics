"""
Siembra de volumen para la gestión documental (DMS).

QUÉ GENERA
Un año de vida de un archivo documental: carpetas, tipos de documento con sus
campos, documentos que nacen en borrador y van pasando por revisión, firma y
publicación, sus versiones, los expedientes de personal y de vehículos, y las
políticas de retención con sus vencimientos.

TRES REGLAS QUE HACEN QUE ESTOS DATOS SIRVAN

1. **El estado del documento y sus firmas cuentan la misma historia.** Un
   documento publicado tiene sus firmas firmadas; uno en revisión las tiene
   pendientes. Sembrarlos por separado produce el caso imposible —publicado sin
   firmar— que hace que nadie vuelva a confiar en el semáforo de la pantalla.

2. **La completitud de un expediente se calcula.** Sale de cuántos de sus
   documentos obligatorios están de verdad cargados, no de un porcentaje
   sorteado. Es lo único que permite que la pantalla diga «a este conductor le
   falta la licencia» y que se pueda ir a comprobarlo.

3. **La vigencia manda sobre el estado.** Un documento cuya fecha de
   vencimiento ya pasó queda OBSOLETO, no publicado. Un archivo documental
   cuyo valor es justamente saber qué está vigente no puede tener vencidos
   marcados como vigentes.

DETERMINISTA
Semilla fija: dos corridas producen exactamente los mismos datos.
"""
import hashlib
import random
import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.dms import (
    DMSAuditoria, DMSCampoMetadato, DMSCarpeta, DMSCategoria, DMSDocumento,
    DMSExpediente, DMSExpedienteDocumento, DMSFirma, DMSInstancia,
    DMSInstanciaPaso, DMSKPIDiario, DMSMetadatoValor, DMSNotificacion,
    DMSRetencion, DMSTipoDocumento, DMSVersion, DMSWorkflow, DMSWorkflowPaso,
    AccionAuditoriaDMSEnum, EstadoDocumentoDMSEnum, EstadoFirmaDMSEnum,
    EstadoInstanciaDMSEnum, TipoExpedienteDMSEnum, TipoFirmaDMSEnum,
)

SEMILLA = 20260912

# (nombre, código, icono, color)
_CATEGORIAS = [
    ("Calidad",            "CAL", "verified",        "#0EA5E9"),
    ("Talento humano",     "THU", "badge",           "#7C3AED"),
    ("Operaciones",        "OPE", "local_shipping",  "#059669"),
    ("Legal y contratos",  "LEG", "gavel",           "#B91C1C"),
    ("Financiero",         "FIN", "payments",        "#F59E0B"),
    ("Seguridad y salud",  "SST", "health_and_safety", "#EF4444"),
]

# (nombre, categoría, extensiones, exige firma, exige aprobación, días de vigencia)
_TIPOS = [
    ("Procedimiento",              "Calidad",           "pdf,docx", True,  True,  None),
    ("Instructivo de trabajo",     "Calidad",           "pdf,docx", False, True,  None),
    ("Formato",                    "Calidad",           "xlsx,pdf", False, False, None),
    ("Contrato laboral",           "Talento humano",    "pdf",      True,  True,  None),
    ("Hoja de vida",               "Talento humano",    "pdf",      False, False, None),
    ("Certificado médico",         "Talento humano",    "pdf,jpg",  False, False, 365),
    ("Licencia de conducción",     "Operaciones",       "pdf,jpg",  False, False, 1825),
    ("Tarjeta de propiedad",       "Operaciones",       "pdf,jpg",  False, False, None),
    ("SOAT",                       "Operaciones",       "pdf",      False, False, 365),
    ("Revisión técnico-mecánica",  "Operaciones",       "pdf",      False, False, 365),
    ("Contrato con cliente",       "Legal y contratos", "pdf,docx", True,  True,  None),
    ("Póliza de seguro",           "Legal y contratos", "pdf",      False, True,  365),
    ("Estado financiero",          "Financiero",        "pdf,xlsx", False, True,  None),
    ("Matriz de riesgos",          "Seguridad y salud", "xlsx,pdf", False, True,  365),
    ("Examen ocupacional",         "Seguridad y salud", "pdf",      False, False, 365),
]

# (nombre de la carpeta, categoría a la que pertenece su contenido)
_CARPETAS = [
    ("Sistema de gestión",   "Calidad"),
    ("Nómina y contratos",   "Talento humano"),
    ("Flota",                "Operaciones"),
    ("Conductores",          "Operaciones"),
    ("Clientes",             "Legal y contratos"),
    ("Contabilidad",         "Financiero"),
    ("Seguridad y salud",    "Seguridad y salud"),
]

_NOMBRES = ["Andrés", "Carolina", "Javier", "Diana", "Ricardo", "Paola",
            "Óscar", "Natalia", "Fernando", "Claudia", "Mauricio", "Luz",
            "Camilo", "Sandra", "Julián", "Marcela"]
_APELLIDOS = ["Gómez", "Rodríguez", "Martínez", "Herrera", "Castaño", "Molina",
              "Restrepo", "Cárdenas", "Villamil", "Quintero", "Salazar", "Pardo",
              "Ocampo", "Bedoya", "Naranjo", "Arango"]

# Las políticas de retención más comunes en Colombia, con su norma.
_RETENCIONES = [
    ("Contratos laborales",   "Contrato laboral",   730,  7300,
     "ARCHIVAR", "Ley 594 de 2000 · retención de 20 años"),
    ("Documentos contables",  "Estado financiero",  1825, 3650,
     "ARCHIVAR", "Código de Comercio art. 28 · 10 años"),
    ("Exámenes ocupacionales", "Examen ocupacional", 365, 7300,
     "ARCHIVAR", "Resolución 2346 de 2007 · 20 años tras el retiro"),
    ("Documentos de vehículo", "SOAT",               365,  1825,
     "ELIMINAR", "Vigencia legal más 5 años de respaldo"),
    ("Procedimientos vigentes", "Procedimiento",     1095, 3650,
     "ARCHIVAR", "ISO 9001 · versión obsoleta identificada y conservada"),
]


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t)
                   if not unicodedata.combining(c))


def _archivo(nombre: str, extension: str) -> str:
    base = _sin_tildes(nombre).lower().replace(" ", "_")
    base = "".join(c for c in base if c.isalnum() or c == "_")
    return f"{base[:60]}.{extension}"


def _hash(texto: str) -> str:
    return hashlib.md5(texto.encode("utf-8")).hexdigest()


def _habil(d: date) -> bool:
    return d.weekday() < 5


async def sembrar_dms(
    db: AsyncSession, *,
    desde: date,
    hasta: date,
    documentos_por_semana: int = 12,
    esquema: Optional[str] = None,
    avisar=None,
) -> dict:
    """Genera el archivo documental entre dos fechas."""
    avisar = avisar or (lambda t: None)
    az = random.Random(SEMILLA)

    async def confirmar() -> None:
        # El `search_path` vive en la CONEXIÓN: tras cada commit hay que
        # reponerlo o las inserciones siguientes caen en `public`.
        await db.commit()
        if esquema:
            await db.execute(text(f'SET search_path TO "{esquema}"'))

    usuarios = [f[0] for f in (await db.execute(
        text("SELECT id FROM usuarios ORDER BY id LIMIT 12"))).all()] or [1]

    def alguien() -> int:
        return az.choice(usuarios)

    # ── Categorías ────────────────────────────────────────────────────────────
    categorias: Dict[str, DMSCategoria] = {}
    for nombre, codigo, icono, color in _CATEGORIAS:
        c = DMSCategoria(nombre=nombre, codigo=codigo, icono=icono, color=color,
                         descripcion=f"Documentos de {nombre.lower()}.",
                         activo=True)
        db.add(c)
        categorias[nombre] = c
    await confirmar()

    # ── Carpetas ──────────────────────────────────────────────────────────────
    carpetas: Dict[str, DMSCarpeta] = {}
    raiz = DMSCarpeta(nombre="Documentos", ruta="/Documentos", icono="folder",
                      color="#64748B", es_publica=True, creado_por_id=usuarios[0],
                      descripcion="Raíz del archivo documental.")
    db.add(raiz)
    await db.flush()
    for nombre, categoria in _CARPETAS:
        f = DMSCarpeta(
            nombre=nombre, padre_id=raiz.id, ruta=f"/Documentos/{nombre}",
            icono="folder", color=categorias[categoria].color,
            es_publica=categoria not in ("Talento humano", "Financiero"),
            creado_por_id=usuarios[0],
            descripcion=f"{nombre} · {categoria}.")
        db.add(f)
        carpetas[nombre] = f
    await confirmar()
    avisar(f"  {len(categorias)} categorías y {len(carpetas) + 1} carpetas")

    # ── Tipos de documento y sus campos ───────────────────────────────────────
    tipos: Dict[str, DMSTipoDocumento] = {}
    for i, (nombre, categoria, ext, firma, aprueba, vigencia) in enumerate(_TIPOS, 1):
        t = DMSTipoDocumento(
            nombre=nombre, categoria_id=categorias[categoria].id,
            codigo=f"TD-{i:03d}", extensiones_permitidas=ext,
            requiere_firma=firma, requiere_aprobacion=aprueba,
            dias_vigencia=vigencia, activo=True,
            descripcion=f"{nombre} bajo la categoría {categoria.lower()}.")
        db.add(t)
        tipos[nombre] = t
    await confirmar()

    # Los campos que se le piden a cada tipo al cargarlo. Sin ellos, buscar un
    # documento por su número de póliza o por la placa del vehículo obliga a
    # abrirlos uno por uno.
    _CAMPOS = {
        "Contrato laboral": [("cedula", "Cédula", "texto", True),
                             ("cargo", "Cargo", "texto", True),
                             ("fecha_ingreso", "Fecha de ingreso", "fecha", True)],
        "SOAT": [("placa", "Placa", "texto", True),
                 ("aseguradora", "Aseguradora", "texto", True),
                 ("numero_poliza", "Número de póliza", "texto", True)],
        "Licencia de conducción": [("cedula", "Cédula", "texto", True),
                                   ("categoria", "Categoría", "texto", True)],
        "Póliza de seguro": [("numero_poliza", "Número de póliza", "texto", True),
                             ("valor_asegurado", "Valor asegurado", "numero", False)],
        "Contrato con cliente": [("nit_cliente", "NIT del cliente", "texto", True),
                                 ("valor_mensual", "Valor mensual", "numero", False)],
        "Procedimiento": [("proceso", "Proceso", "texto", True),
                          ("norma", "Norma de referencia", "texto", False)],
    }
    campos_por_tipo: Dict[str, List[DMSCampoMetadato]] = {}
    for tipo_nombre, campos in _CAMPOS.items():
        campos_por_tipo[tipo_nombre] = []
        for orden, (clave, etiqueta, dato, requerido) in enumerate(campos, 1):
            c = DMSCampoMetadato(
                tipo_documento_id=tipos[tipo_nombre].id, nombre=clave,
                etiqueta=etiqueta, tipo_dato=dato, requerido=requerido,
                orden=orden)
            db.add(c)
            campos_por_tipo[tipo_nombre].append(c)
    await confirmar()
    avisar(f"  {len(tipos)} tipos de documento")

    # ── Flujos de aprobación ──────────────────────────────────────────────────
    flujos: Dict[str, DMSWorkflow] = {}
    pasos_por_flujo: Dict[int, List[DMSWorkflowPaso]] = {}
    for tipo_nombre in ("Procedimiento", "Contrato laboral",
                        "Contrato con cliente", "Estado financiero"):
        w = DMSWorkflow(
            nombre=f"Aprobación de {tipo_nombre.lower()}",
            descripcion=f"Ruta de revisión y aprobación para {tipo_nombre.lower()}.",
            tipo_documento_id=tipos[tipo_nombre].id, activo=True, dias_limite=10)
        db.add(w)
        await db.flush()
        flujos[tipo_nombre] = w
        pasos = []
        for orden, (nombre, clase, rol, dias) in enumerate([
            ("Revisión técnica", "REVISION", "Líder del proceso", 3),
            ("Aprobación", "APROBACION", "Jefe de área", 4),
            ("Publicación", "PUBLICACION", "Gestión documental", 3),
        ], 1):
            p = DMSWorkflowPaso(
                workflow_id=w.id, nombre=nombre, tipo=clase, orden=orden,
                responsable_rol=rol, dias_limite=dias, es_obligatorio=True)
            db.add(p)
            pasos.append(p)
        pasos_por_flujo[w.id] = pasos
    await confirmar()

    # ── Documentos, semana a semana ───────────────────────────────────────────
    documentos: List[DMSDocumento] = []
    versiones: List[DMSVersion] = []
    n_doc = 0
    dia = desde
    while dia <= hasta:
        if dia.weekday() != 0:
            dia += timedelta(days=1)
            continue

        for _ in range(documentos_por_semana):
            n_doc += 1
            tipo_nombre, categoria, ext, exige_firma, exige_aprob, vigencia = az.choice(_TIPOS)
            tipo = tipos[tipo_nombre]
            carpeta = carpetas[next(c for c, cat in _CARPETAS if cat == categoria)]
            nacido = dia + timedelta(days=az.randrange(0, 5))
            if nacido > hasta:
                nacido = hasta

            # La vigencia se cuenta desde que nace, no desde hoy.
            inicio_vig = nacido
            fin_vig = (nacido + timedelta(days=vigencia)) if vigencia else None

            # EL ESTADO Y LA VIGENCIA CUENTAN LA MISMA HISTORIA.
            #
            # Lo vencido queda obsoleto aunque se hubiera publicado. Un archivo
            # documental cuyo valor es saber qué está vigente no puede tener
            # vencidos marcados como vigentes: eso es exactamente el error que
            # deja salir un camión con el SOAT caído.
            reciente = (hasta - nacido).days < 20
            if fin_vig and fin_vig < hasta:
                estado = EstadoDocumentoDMSEnum.OBSOLETO
            elif reciente and az.random() < 0.55:
                estado = az.choice([EstadoDocumentoDMSEnum.BORRADOR,
                                    EstadoDocumentoDMSEnum.EN_REVISION])
            elif az.random() < 0.08:
                estado = EstadoDocumentoDMSEnum.ARCHIVADO
            else:
                estado = EstadoDocumentoDMSEnum.PUBLICADO

            nombre_doc = f"{tipo_nombre} · {az.choice(_NOMBRES)} {az.choice(_APELLIDOS)}" \
                if categoria in ("Talento humano", "Seguridad y salud") \
                else f"{tipo_nombre} {nacido.year}-{n_doc:04d}"

            versiones_mayores = az.randrange(1, 4)
            d = DMSDocumento(
                codigo=f"DOC-{nacido.year}-{n_doc:04d}",
                nombre=nombre_doc,
                descripcion=f"{tipo_nombre} archivado en {carpeta.nombre.lower()}.",
                tipo_documento_id=tipo.id, carpeta_id=carpeta.id,
                estado=estado, version_numero=versiones_mayores,
                version_actual=f"{versiones_mayores}.0",
                tags=",".join(az.sample(
                    ["vigente", "auditoría", "iso9001", "legal", "operación",
                     "personal", "flota", "confidencial"], k=az.randrange(1, 4))),
                es_confidencial=categoria in ("Talento humano", "Financiero"),
                permite_descarga=categoria not in ("Talento humano",),
                permite_impresion=True,
                fecha_vigencia_inicio=datetime.combine(inicio_vig, time(8)),
                fecha_vigencia_fin=datetime.combine(fin_vig, time(23, 59)) if fin_vig else None,
                propietario_id=alguien(), modulo_origen="DMS")
            d.created_at = datetime.combine(nacido, time(az.randrange(8, 18)))
            db.add(d)
            await db.flush()
            documentos.append(d)

            # Sus versiones. Cada una con su archivo, su tamaño y su huella: sin
            # el hash no hay forma de demostrar que el PDF que se descarga hoy es
            # el mismo que se aprobó, que es la mitad del sentido de un DMS.
            for v in range(1, versiones_mayores + 1):
                extension = ext.split(",")[0]
                tam = az.randrange(80_000, 4_500_000)
                fecha_v = nacido + timedelta(days=(v - 1) * az.randrange(20, 90))
                if fecha_v > hasta:
                    fecha_v = hasta
                ver = DMSVersion(
                    documento_id=d.id, numero_version=f"{v}.0", version_numero=v,
                    es_mayor=True, nombre_archivo=_archivo(nombre_doc, extension),
                    ruta_archivo=f"dms/{nacido.year}/{d.codigo}/v{v}.{extension}",
                    tamanio_bytes=tam,
                    tipo_mime={"pdf": "application/pdf",
                               "docx": "application/vnd.openxmlformats-officedocument"
                                       ".wordprocessingml.document",
                               "xlsx": "application/vnd.openxmlformats-officedocument"
                                       ".spreadsheetml.sheet",
                               "jpg": "image/jpeg"}.get(extension, "application/octet-stream"),
                    hash_md5=_hash(f"{d.codigo}-v{v}"),
                    comentario="Versión inicial." if v == 1
                               else f"Actualización {v}: se corrigieron los anexos.",
                    creado_por_id=d.propietario_id)
                ver.created_at = datetime.combine(fecha_v, time(10))
                db.add(ver)
                versiones.append(ver)

            # Los valores de sus campos.
            for campo in campos_por_tipo.get(tipo_nombre, []):
                valor = DMSMetadatoValor(documento_id=d.id, campo_id=campo.id)
                if campo.tipo_dato == "numero":
                    valor.valor_numero = az.randrange(5, 900) * 1_000_000
                elif campo.tipo_dato == "fecha":
                    valor.valor_fecha = datetime.combine(
                        nacido - timedelta(days=az.randrange(30, 900)), time(0))
                elif campo.nombre == "placa":
                    valor.valor_texto = (f"{az.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"
                                         f"{az.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"
                                         f"{az.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"
                                         f"{az.randrange(100, 999)}")
                elif campo.nombre == "cedula":
                    valor.valor_texto = str(az.randrange(10_000_000, 1_200_000_000))
                elif campo.nombre == "numero_poliza":
                    valor.valor_texto = f"POL-{az.randrange(100000, 999999)}"
                else:
                    valor.valor_texto = az.choice(
                        ["Seguros Bolívar", "Sura", "Previsora", "Mapfre",
                         "Operaciones", "Calidad", "ISO 9001:2015", "C2", "C3"])
                db.add(valor)
        await confirmar()
        dia += timedelta(days=7)
    avisar(f"  {len(documentos)} documentos con {len(versiones)} versiones")

    # ── Firmas ────────────────────────────────────────────────────────────────
    #
    # Solo de los tipos que las exigen, y CONSISTENTES CON EL ESTADO: un
    # documento publicado tiene sus firmas firmadas. El caso imposible
    # —publicado sin firmar— es lo que hace que nadie crea en el semáforo.
    firmas: List[DMSFirma] = []
    ultima_version = {}
    for v in versiones:
        anterior = ultima_version.get(v.documento_id)
        if anterior is None or v.version_numero > anterior.version_numero:
            ultima_version[v.documento_id] = v

    for d in documentos:
        tipo = next(t for t in tipos.values() if t.id == d.tipo_documento_id)
        if not tipo.requiere_firma:
            continue
        version = ultima_version.get(d.id)
        publicado = d.estado in (EstadoDocumentoDMSEnum.PUBLICADO,
                                 EstadoDocumentoDMSEnum.OBSOLETO,
                                 EstadoDocumentoDMSEnum.ARCHIVADO)
        for orden in range(1, az.randrange(2, 4)):
            if publicado:
                estado_f = EstadoFirmaDMSEnum.FIRMADO
            elif d.estado == EstadoDocumentoDMSEnum.EN_REVISION:
                estado_f = EstadoFirmaDMSEnum.PENDIENTE
            else:
                estado_f = EstadoFirmaDMSEnum.PENDIENTE
            firmado_el = ((d.created_at or datetime.combine(desde, time(9)))
                          + timedelta(days=az.randrange(1, 12)))
            f = DMSFirma(
                documento_id=d.id, version_id=version.id if version else None,
                firmante_id=alguien(),
                tipo_firma=az.choice(list(TipoFirmaDMSEnum)),
                estado=estado_f,
                fecha_firma=firmado_el if estado_f == EstadoFirmaDMSEnum.FIRMADO else None,
                ip_firma=f"190.{az.randrange(0,255)}.{az.randrange(0,255)}.{az.randrange(1,254)}"
                         if estado_f == EstadoFirmaDMSEnum.FIRMADO else None,
                dispositivo=az.choice(["Windows · Chrome", "Android · Chrome",
                                       "macOS · Safari", "iOS · Safari"])
                            if estado_f == EstadoFirmaDMSEnum.FIRMADO else None,
                orden=orden)
            db.add(f)
            firmas.append(f)
    await confirmar()
    avisar(f"  {len(firmas)} firmas")

    # ── Instancias de flujo ───────────────────────────────────────────────────
    instancias = 0
    for d in documentos:
        tipo = next(t for t in tipos.values() if t.id == d.tipo_documento_id)
        flujo = flujos.get(tipo.nombre)
        if flujo is None or az.random() > 0.7:
            continue
        instancias += 1
        pasos = pasos_por_flujo[flujo.id]
        inicio = (d.created_at or datetime.combine(desde, time(9)))
        if d.estado in (EstadoDocumentoDMSEnum.BORRADOR,
                        EstadoDocumentoDMSEnum.EN_REVISION):
            estado_i = EstadoInstanciaDMSEnum.EN_CURSO
            paso_actual = az.randrange(1, len(pasos) + 1)
            fin = None
        else:
            estado_i = EstadoInstanciaDMSEnum.COMPLETADO
            paso_actual = len(pasos)
            fin = inicio + timedelta(days=az.randrange(2, 14))
        inst = DMSInstancia(
            workflow_id=flujo.id, documento_id=d.id, estado=estado_i,
            iniciado_por_id=d.propietario_id, paso_actual=paso_actual,
            fecha_inicio=inicio,
            fecha_limite=inicio + timedelta(days=flujo.dias_limite or 10),
            fecha_fin=fin,
            comentario_cierre="Aprobado sin observaciones." if fin else None)
        db.add(inst)
        await db.flush()
        for p in pasos:
            if p.orden < paso_actual or estado_i == EstadoInstanciaDMSEnum.COMPLETADO:
                estado_p, accion = "COMPLETADO", "APROBAR"
                respuesta = inicio + timedelta(days=p.orden * 2)
            elif p.orden == paso_actual:
                estado_p, accion, respuesta = "PENDIENTE", None, None
            else:
                estado_p, accion, respuesta = "PENDIENTE", None, None
            db.add(DMSInstanciaPaso(
                instancia_id=inst.id, paso_id=p.id, estado=estado_p,
                asignado_a_id=alguien(), fecha_asignacion=inicio,
                fecha_respuesta=respuesta, accion=accion,
                comentario="Revisado y conforme." if accion else None))
    await confirmar()
    avisar(f"  {instancias} flujos de aprobación en marcha")

    # ── Expedientes ───────────────────────────────────────────────────────────
    #
    # La completitud NO se sortea: se cuenta cuántos de los documentos
    # obligatorios están de verdad enlazados. Es lo único que permite que la
    # pantalla diga «a este conductor le falta la licencia» y que alguien pueda
    # ir a comprobarlo.
    OBLIGATORIOS = {
        TipoExpedienteDMSEnum.CONDUCTOR: [
            "Licencia de conducción", "Hoja de vida", "Certificado médico",
            "Examen ocupacional", "Contrato laboral"],
        TipoExpedienteDMSEnum.VEHICULO: [
            "Tarjeta de propiedad", "SOAT", "Revisión técnico-mecánica",
            "Póliza de seguro"],
        TipoExpedienteDMSEnum.EMPLEADO: [
            "Contrato laboral", "Hoja de vida", "Examen ocupacional"],
        TipoExpedienteDMSEnum.CLIENTE: [
            "Contrato con cliente", "Póliza de seguro"],
    }
    por_tipo_doc: Dict[int, List[DMSDocumento]] = {}
    for d in documentos:
        por_tipo_doc.setdefault(d.tipo_documento_id, []).append(d)

    expedientes = 0
    n_exp = 0
    for clase, requeridos in OBLIGATORIOS.items():
        for _ in range(az.randrange(6, 13)):
            n_exp += 1
            expedientes += 1
            titular = (f"{az.choice(_NOMBRES)} {az.choice(_APELLIDOS)}"
                       if clase in (TipoExpedienteDMSEnum.CONDUCTOR,
                                    TipoExpedienteDMSEnum.EMPLEADO)
                       else f"{az.choice(['Vehículo', 'Cuenta'])} "
                            f"{az.choice('ABCDEFGHJK')}{az.randrange(100, 999)}")
            exp = DMSExpediente(
                codigo=f"EXP-{clase.value[:3]}-{n_exp:04d}",
                nombre=f"Expediente de {titular}",
                tipo=clase, estado="ACTIVO",
                descripcion=f"Documentación obligatoria de {titular}.",
                propietario_id=alguien(), completitud_pct=0)
            db.add(exp)
            await db.flush()

            # SOLO SE ENLAZA LO QUE EXISTE.
            #
            # `dms_expediente_documento.documento_id` es obligatorio, así que un
            # requisito pendiente no se puede representar como una fila vacía:
            # lo que falta es la ausencia de fila. La completitud se calcula
            # contra la lista de requisitos, no contra las filas insertadas —si
            # se calculara así siempre daría 100% y la pantalla no serviría para
            # encontrar lo que falta, que es para lo único que se mira.
            cargados = 0
            for tipo_nombre in requeridos:
                tipo = tipos[tipo_nombre]
                candidatos = por_tipo_doc.get(tipo.id, [])
                if not candidatos or az.random() >= 0.72:
                    continue
                db.add(DMSExpedienteDocumento(
                    expediente_id=exp.id,
                    documento_id=az.choice(candidatos).id,
                    tipo_requerido=tipo_nombre, es_obligatorio=True))
                cargados += 1
            exp.completitud_pct = round(100 * cargados / max(1, len(requeridos)))
    await confirmar()
    avisar(f"  {expedientes} expedientes")

    # ── Políticas de retención ────────────────────────────────────────────────
    for nombre, tipo_nombre, activo_dias, total_dias, accion, norma in _RETENCIONES:
        db.add(DMSRetencion(
            nombre=nombre, tipo_documento_id=tipos[tipo_nombre].id,
            dias_retencion_activo=activo_dias, dias_retencion_total=total_dias,
            accion_vencimiento=accion, normativa=norma, activo=True))
    await confirmar()

    # ── Rastro de auditoría ───────────────────────────────────────────────────
    #
    # Quién vio qué y cuándo. Es lo que convierte un repositorio de archivos en
    # un archivo documental: sin esto no se puede responder a un auditor quién
    # descargó el contrato antes de que se filtrara.
    acciones = 0
    for d in az.sample(documentos, min(len(documentos), 320)):
        for _ in range(az.randrange(1, 6)):
            base = d.created_at or datetime.combine(desde, time(9))
            cuando = base + timedelta(days=az.randrange(0, 200),
                                      hours=az.randrange(0, 10))
            if cuando > datetime.combine(hasta, time(23)):
                cuando = datetime.combine(hasta, time(az.randrange(8, 18)))
            accion = az.choice(list(AccionAuditoriaDMSEnum))
            reg = DMSAuditoria(
                documento_id=d.id, usuario_id=alguien(), accion=accion,
                detalle=f"{accion.value.capitalize()} de «{d.nombre[:60]}».",
                ip_origen=f"190.{az.randrange(0,255)}.{az.randrange(0,255)}.{az.randrange(1,254)}",
                user_agent=az.choice([
                    "Mozilla/5.0 (Windows NT 10.0) Chrome/128",
                    "Mozilla/5.0 (Macintosh) Safari/17",
                    "Mozilla/5.0 (Linux; Android 14) Chrome/128"]))
            reg.created_at = cuando
            db.add(reg)
            acciones += 1
        if acciones % 400 == 0:
            await confirmar()
    await confirmar()
    avisar(f"  {acciones} registros de auditoría")

    # ── Avisos ────────────────────────────────────────────────────────────────
    #
    # A quien tiene una firma pendiente y a quien se le vence un documento.
    avisos = 0
    for f in firmas:
        if f.estado != EstadoFirmaDMSEnum.PENDIENTE:
            continue
        d = next(x for x in documentos if x.id == f.documento_id)
        db.add(DMSNotificacion(
            usuario_id=f.firmante_id, documento_id=d.id, tipo="FIRMA_PENDIENTE",
            titulo="Tiene un documento por firmar",
            mensaje=f"«{d.nombre[:70]}» espera su firma.",
            leida=az.random() < 0.4, accion_url=f"/dms/documentos/{d.id}"))
        avisos += 1

    limite = hasta + timedelta(days=45)
    for d in documentos:
        if not d.fecha_vigencia_fin:
            continue
        vence = d.fecha_vigencia_fin.date()
        if not (hasta <= vence <= limite):
            continue
        dias = (vence - hasta).days
        db.add(DMSNotificacion(
            usuario_id=d.propietario_id, documento_id=d.id, tipo="POR_VENCER",
            titulo=f"Un documento vence en {dias} día(s)",
            mensaje=f"«{d.nombre[:70]}» pierde vigencia el {vence:%d/%m/%Y}.",
            leida=False, accion_url=f"/dms/documentos/{d.id}"))
        avisos += 1
    await confirmar()

    # ── Indicadores diarios ───────────────────────────────────────────────────
    #
    # Se resumen de lo sembrado. Inventarlos aparte haría que el tablero y las
    # listas dijeran cosas distintas del mismo día.
    n_kpi = 0
    dia = desde
    while dia <= hasta:
        if not _habil(dia):
            dia += timedelta(days=1)
            continue
        hasta_hoy = [d for d in documentos
                     if (d.created_at.date() if d.created_at else desde) <= dia]
        creados_hoy = [d for d in documentos
                       if d.created_at and d.created_at.date() == dia]
        vencidos = [d for d in hasta_hoy
                    if d.fecha_vigencia_fin and d.fecha_vigencia_fin.date() < dia]
        aprobados = [d for d in hasta_hoy
                     if d.estado == EstadoDocumentoDMSEnum.PUBLICADO]
        firmas_pend = [f for f in firmas if f.estado == EstadoFirmaDMSEnum.PENDIENTE]
        firmas_ok = [f for f in firmas
                     if f.fecha_firma and f.fecha_firma.date() <= dia]
        bytes_hoy = sum(
            (v.tamanio_bytes or 0) for v in versiones
            if (v.created_at.date() if v.created_at else desde) <= dia)

        db.add(DMSKPIDiario(
            fecha=dia,
            total_documentos=len(hasta_hoy),
            documentos_creados=len(creados_hoy),
            documentos_aprobados=len(aprobados),
            documentos_vencidos=len(vencidos),
            firmas_pendientes=len(firmas_pend),
            firmas_completadas=len(firmas_ok),
            workflows_activos=instancias,
            tamanio_total_mb=round(bytes_hoy / 1_048_576, 2)))
        n_kpi += 1
        if n_kpi % 40 == 0:
            await confirmar()
        dia += timedelta(days=1)
    await confirmar()
    avisar(f"  {n_kpi} días de indicadores")

    return {
        "categorias": len(categorias), "carpetas": len(carpetas) + 1,
        "tipos_documento": len(tipos), "documentos": len(documentos),
        "versiones": len(versiones), "firmas": len(firmas),
        "flujos": len(flujos), "instancias": instancias,
        "expedientes": expedientes, "auditoria": acciones,
        "notificaciones": avisos, "kpis": n_kpi,
    }


async def verificar(db: AsyncSession) -> dict:
    """Comprueba lo que haría inservible el archivo si estuviera mal.

    Tres cosas, y las tres tienen que dar cero.
    """
    # Un documento publicado con firmas sin firmar es el caso que hace que nadie
    # crea en el estado que muestra la pantalla.
    publicados_sin_firmar = (await db.execute(text("""
        SELECT count(DISTINCT d.id) FROM dms_documento d
          JOIN dms_firma f ON f.documento_id = d.id
         WHERE d.estado = 'PUBLICADO' AND f.estado = 'PENDIENTE'"""))).scalar() or 0

    # Un documento vencido que sigue figurando como publicado es lo que deja
    # salir un camión con el SOAT caído.
    vencidos_publicados = (await db.execute(text("""
        SELECT count(*) FROM dms_documento
         WHERE estado = 'PUBLICADO'
           AND fecha_vigencia_fin IS NOT NULL
           AND fecha_vigencia_fin < now()"""))).scalar() or 0

    # Un enlace que apunta a un documento inexistente deja el expediente
    # diciendo que tiene algo que no se puede abrir.
    enlaces_rotos = (await db.execute(text("""
        SELECT count(*) FROM dms_expediente_documento ed
         WHERE NOT EXISTS (SELECT 1 FROM dms_documento d WHERE d.id = ed.documento_id)
      """))).scalar() or 0

    # Y la completitud nunca puede superar el 100% ni bajar de cero: si eso
    # pasa, el cálculo está contando mal y el resto de la pantalla también.
    completitud_imposible = (await db.execute(text("""
        SELECT count(*) FROM dms_expediente
         WHERE completitud_pct < 0 OR completitud_pct > 100"""))).scalar() or 0

    total_mb = (await db.execute(text(
        "SELECT COALESCE(SUM(tamanio_bytes), 0) / 1048576.0 FROM dms_version"))).scalar() or 0

    return {
        "publicados_con_firma_pendiente": int(publicados_sin_firmar),
        "vencidos_aun_publicados": int(vencidos_publicados),
        "expedientes_con_enlaces_rotos": int(enlaces_rotos),
        "completitud_fuera_de_rango": int(completitud_imposible),
        "tamanio_total_mb": round(float(total_mb), 2),
    }
