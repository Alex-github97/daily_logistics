"""
El contenido editable de la landing.

Se guarda como un solo documento JSON y no como veinte columnas: los textos de
una página cambian de forma cada vez que se rediseña, y una tabla con una
columna por párrafo obliga a migrar la base cada vez que alguien mueve una
sección.

La lectura es **pública**: la landing la ve cualquiera, y exigir sesión para
mostrar un título dejaría la página en blanco a los visitantes. La escritura
exige el permiso de la consola.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_plataforma
from app.core.permisos_consola import Miembro, exigir
from app.core.security import decode_token
from app.infrastructure.models.plataforma import PlataformaLanding

router = APIRouter(prefix="/landing", tags=["Landing"])

# Lo que la página trae escrito adentro. Existe acá también para poder
# devolverlo la primera vez, antes de que nadie haya editado nada.
CONTENIDO_INICIAL: Dict[str, Any] = {
    "marca_logo": "TITTANWARE",
    "marca_nombre": "TittanWare",
    "marca_legal": "Todos los derechos reservados",
    "url_portal": "https://tittanware.tech",
    "correo": "contacto@tittanware.com",
    "color_acento": "#2F6FEB",
    "hero_lema": "Tecnología que fortalece · Soluciones que trascienden",
    "hero_titulo": "Toda la operación en <em>una sola plataforma</em>",
    "hero_bajada": (
        "Mantenimiento, almacenes, transporte, calidad, talento y finanzas dejan de "
        "vivir en archivos sueltos y empiezan a hablar entre sí. La dirección deja de "
        "pedir informes y empieza a mirarlos: el costo, el avance y el riesgo, mientras "
        "están pasando."
    ),
    "hero_boton1": "Solicitar una demostración",
    "hero_boton2": "Ver los módulos",
    "problema_titulo": "El dato existe. Está en otro lado.",
    "problema_texto": (
        "La orden de trabajo está en un cuaderno, el inventario en una hoja de cálculo "
        "y el costo real aparece dos meses después en contabilidad. No falta "
        "información: falta que esté junta y que signifique lo mismo en todas partes."
    ),
    "negocio_titulo": "Lo que cambia para quien responde por los números",
    "negocio_texto": (
        "La operación gana orden, y eso ya se nota. Pero la razón para hacerlo está en "
        "el piso de arriba: costos que se pueden explicar, decisiones que no esperan al "
        "cierre del mes y crecimiento que no se paga contratando más gente para digitar."
    ),
    "modulos_titulo": "Se activa lo que se usa",
    "modulos_texto": (
        "No hay que comprarlo todo. Cada empresa contrata los módulos que necesita y "
        "el resto sencillamente no aparece: ni en el menú, ni en el precio."
    ),
    "detalle_titulo": "Mantenimiento, de la orden a la causa",
    "detalle_texto": (
        "El módulo más profundo de la plataforma, construido con la lógica de quien "
        "vive la operación y no con la de un formulario genérico."
    ),
    "seguridad_titulo": "Construida para aguantar la operación real",
    "seguridad_texto": (
        "No es una hoja de cálculo con botones. Es la ingeniería que se le exige a "
        "un sistema del que la operación depende todos los días, y del que nadie se "
        "quiere acordar porque simplemente funciona."
    ),
    "cierre_titulo": "Cuéntenos cómo opera hoy",
    "cierre_texto": (
        "La primera conversación es para entender su operación, no para mostrar "
        "pantallas. A partir de ahí definimos qué módulos tienen sentido y en qué orden."
    ),
    "negocio": [
        {"clave": "01", "titulo": "Costos con nombre y apellido",
         "texto": "Cada peso de mantenimiento, inventario o transporte queda amarrado a "
                  "la orden, el activo y el centro de costo que lo originó. El cierre "
                  "del mes deja de ser una reconstrucción y pasa a ser una consulta."},
        {"clave": "02", "titulo": "Decisiones con los datos de hoy",
         "texto": "Los tableros se alimentan de lo que la operación registra mientras "
                  "trabaja. Nadie tiene que consolidar un archivo para que la dirección "
                  "pueda mirar el avance, el costo y el riesgo."},
        {"clave": "03", "titulo": "Crecer sin engordar la administración",
         "texto": "Sumar una sede, una flota o una empresa entera no obliga a sumar "
                  "personas digitando lo mismo en otro formato. La estructura ya está "
                  "hecha y se replica."},
        {"clave": "04", "titulo": "Auditorías que se responden, no que se preparan",
         "texto": "Certificaciones, revisorías y clientes piden evidencia. Queda "
                  "registrada sola, con autor y fecha, mientras se opera; no hay que "
                  "fabricarla la semana anterior."},
    ],
    "pilares": [
        {"clave": "01", "titulo": "Un catálogo, no veinte listas",
         "texto": "Ciudades, cargos, centros de costo y categorías se definen una vez y "
                  "se usan en todos los módulos. «Bodega Norte» deja de ser tres valores "
                  "distintos y los informes por fin cuadran."},
        {"clave": "02", "titulo": "Se define una vez y cubre toda la flota",
         "texto": "Tipo de activo → marca → línea → modelo. Un plan de mantenimiento se "
                  "define una vez sobre la jerarquía y cubre todos los equipos que le "
                  "corresponden."},
        {"clave": "03", "titulo": "Trazabilidad hasta el origen",
         "texto": "De un costo del mes se puede llegar a la orden que lo generó, al "
                  "activo, a la falla y al análisis de por qué ocurrió, con sus "
                  "evidencias y su responsable."},
    ],
    # Cada línea es «Nombre | ruta del folleto». Sin la ruta la ficha se pinta
    # pero no lleva a ninguna parte, que es lo correcto para un módulo que
    # todavía no tiene folleto escrito.
    #
    # No están «Gestión de Flotas» —se unificó dentro del CMMS— ni
    # «Mantenimiento Locativo», que no tiene ninguna ruta en el servidor.
    "modulos": [
        "CMMS / EAM · Mantenimiento | /modulos/cmms.html",
        "WMS · Almacenes | /modulos/wms.html",
        "TMS · Transporte | /modulos/tms.html",
        "Control de Estibas | /modulos/estibas.html",
        "ERP · Financiero | /modulos/erp.html",
        "Gestión Humana | /modulos/gh.html",
        "SST · Seguridad y Salud | /modulos/sst.html",
        "LMS · Formación | /modulos/lms.html",
        "QMS · Calidad | /modulos/qms.html",
        "GRC · Riesgo y Cumplimiento | /modulos/grc.html",
        "DMS · Gestión Documental | /modulos/dms.html",
        "CRM · Comercial | /modulos/crm.html",
        "TarifaX · Motor de Tarifas | /modulos/tarifax.html",
        "SCM · Proveedores | /modulos/scm.html",
        "MES · Producción | /modulos/mes.html",
        "APS · Planeación | /modulos/aps.html",
        "AGS · Agenda de Servicios | /modulos/ags.html",
    ],
    "detalles": [
        {"clave": "OT", "titulo": "Órdenes de trabajo",
         "texto": "Trabajos y repuestos desde el catálogo, proveedor por línea, y los "
                  "soportes —cotización, orden de compra, factura— adjuntos y "
                  "consultables por número."},
        {"clave": "RC", "titulo": "Análisis de causa raíz",
         "texto": "Cinco porqués, acciones con responsable y fecha, evidencias "
                  "fotográficas e informe exportable en PDF. Y las causas alimentan el "
                  "tablero."},
        {"clave": "PM", "titulo": "Planes por jerarquía",
         "texto": "Rutinas por kilometraje, horómetro o calendario, definidas sobre "
                  "tipo, marca y línea. El último odómetro registrado programa la "
                  "siguiente."},
        {"clave": "LL", "titulo": "Gestión de llantas",
         "texto": "Montaje y rotación arrastrando a la posición, con inspección, "
                  "kilometraje y fecha obligatorios, y el historial completo de cada "
                  "llanta."},
        {"clave": "CB", "titulo": "Control de combustible",
         "texto": "Tanqueos con su costo e IVA, y rendimiento en kilómetros por "
                  "galón medido tanque a tanque. Metas por marca, línea y motor, "
                  "con alerta cuando un vehículo se queda por debajo."},
        {"clave": "LB", "titulo": "Análisis de lubricación",
         "texto": "Muestras de aceite por compartimento, con límites propios por "
                  "familia de equipo: el valor absoluto, la velocidad a la que sube "
                  "y la referencia de la flota. Detecta el desgaste antes de que el "
                  "límite se cruce."},
        {"clave": "CH", "titulo": "Inspecciones preoperativas",
         "texto": "Checklists configurables por sistema del equipo, con evidencia "
                  "fotográfica y firma. Un hallazgo crítico reprueba la inspección y "
                  "abre la orden de trabajo sola."},
        {"clave": "IN", "titulo": "Inventario de repuestos",
         "texto": "Existencias por bodega con kárdex y costo promedio. Las órdenes "
                  "de trabajo descuentan solas, y el informe de rotación muestra qué "
                  "está dormido en el estante."},
    ],
    "garantias": [
        {"clave": "01", "titulo": "No se arrastra con la operación encima",
         "texto": "Varios procesos atienden en paralelo y las consultas no se bloquean "
                  "entre sí. Que haya mucha gente trabajando al mismo tiempo no es lo "
                  "que hace lenta a la plataforma."},
        {"clave": "02", "titulo": "Se respalda sola, todas las madrugadas",
         "texto": "La base completa se respalda cada noche sin que nadie tenga que "
                  "acordarse, y además una copia por empresa: se puede restaurar a una "
                  "sola sin tocar a las demás."},
        {"clave": "03", "titulo": "Cifrada de punta a punta",
         "texto": "Todo el tráfico va por HTTPS con certificado que se renueva solo. Las "
                  "contraseñas se guardan de forma irreversible: ni siquiera nosotros "
                  "podemos leerlas."},
        {"clave": "04", "titulo": "Todo deja rastro",
         "texto": "Movimientos, cambios de estado y accesos quedan registrados con autor "
                  "y fecha. Cuando toca explicar qué pasó, la respuesta está en el "
                  "sistema y no en la memoria de alguien."},
        {"clave": "05", "titulo": "Los permisos se verifican en el servidor",
         "texto": "No se aplican ocultando botones: se comprueban en cada petición. Quien "
                  "no tiene acceso a algo no lo consigue escribiendo la dirección a mano."},
        {"clave": "06", "titulo": "Siempre la última versión",
         "texto": "Es web: no hay nada que instalar ni actualizaciones que coordinar con "
                  "cada equipo. Todos entran a la misma versión, desde cualquier "
                  "computador y desde cualquier parte."},
    ],
}

# Tope por documento. Una landing con más de esto no es una landing, y sin
# límite una petición podría meter megas de texto en la base.
MAX_CARACTERES = 120_000


class Publicacion(BaseModel):
    contenido: Dict[str, Any]


class EstadoLanding(BaseModel):
    contenido: Dict[str, Any]
    actualizado_en: Optional[datetime] = None
    actualizado_por: Optional[str] = None


async def _fila(db: AsyncSession) -> Optional[PlataformaLanding]:
    r = await db.execute(select(PlataformaLanding).order_by(PlataformaLanding.id).limit(1))
    return r.scalar_one_or_none()


@router.get("/contenido")
async def contenido(db: AsyncSession = Depends(get_db_plataforma)):
    """Lo que la landing muestra. Público a propósito.

    Si nadie ha editado nada devuelve el contenido inicial, para que la página
    tenga qué mostrar desde el primer día.
    """
    fila = await _fila(db)
    return (fila.contenido or CONTENIDO_INICIAL) if fila else CONTENIDO_INICIAL


@router.get("/estado", response_model=EstadoLanding)
async def estado(
    db: AsyncSession = Depends(get_db_plataforma),
    _: Miembro = Depends(exigir("landing.editar")),
):
    """Lo mismo, más quién lo tocó por última vez. Para el editor."""
    fila = await _fila(db)
    if not fila:
        return EstadoLanding(contenido=CONTENIDO_INICIAL)
    return EstadoLanding(
        contenido=fila.contenido or CONTENIDO_INICIAL,
        actualizado_en=fila.updated_at, actualizado_por=fila.actualizado_por)


@router.get("/inicial")
async def inicial(_: Miembro = Depends(exigir("landing.editar"))):
    """El contenido de fábrica, para poder volver atrás sin perder la página."""
    return CONTENIDO_INICIAL


@router.put("/contenido", response_model=EstadoLanding)
async def publicar(
    data: Publicacion, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("landing.editar")),
):
    import json
    crudo = json.dumps(data.contenido, ensure_ascii=False)
    if len(crudo) > MAX_CARACTERES:
        raise HTTPException(
            400,
            f"El contenido pesa {len(crudo)} caracteres y el máximo son "
            f"{MAX_CARACTERES}. Acorte los textos o quite secciones.",
        )
    # Sin correo, el botón principal de la página no lleva a ninguna parte.
    if not (data.contenido.get("correo") or "").strip():
        raise HTTPException(
            400, "Falta el correo de contacto: es a donde lleva el botón principal.")

    fila = await _fila(db)
    if not fila:
        fila = PlataformaLanding()
        db.add(fila)
    fila.contenido = data.contenido
    fila.actualizado_por = quien.usuario
    await db.commit(); await db.refresh(fila)
    return EstadoLanding(contenido=fila.contenido,
                         actualizado_en=fila.updated_at,
                         actualizado_por=fila.actualizado_por)
