"""
El catálogo de permisos que puede tener un perfil dentro de una empresa.

Es distinto de `modulos.py`, y conviene no confundirlos: aquel dice qué
**contrató** la empresa y este dice qué puede hacer **cada persona** dentro de
lo contratado. Los dos tienen que pasar para que alguien entre a una pantalla:
si el módulo no está contratado da igual el perfil, y si el perfil no lo
permite da igual que esté contratado.

POR QUÉ EN UN SOLO SITIO
La lista estaba repartida en tres lugares que se desincronizaron: el esquema
del rol en el servidor, el mapa de rutas del portal y las casillas de la
pantalla. El resultado fue que ERP, SCM y SST se podían marcar en la pantalla,
el portal los exigía para dejar entrar, y el servidor los descartaba en
silencio al guardar: un perfil con esos módulos no funcionaba y no había forma
de saber por qué. Acá quedan una vez y los tres los leen de acá.
"""
from typing import Dict, List, NamedTuple


class Permiso(NamedTuple):
    clave: str
    nombre: str
    # Para agrupar las casillas en la pantalla; un perfil de veinte casillas
    # sueltas no se puede revisar de un vistazo.
    grupo: str


PERMISOS_PERFIL: List[Permiso] = [
    # ── Control de estibas ────────────────────────────────────────────────
    Permiso("dashboard",    "Tablero",                 "Control de estibas"),
    Permiso("estibas",      "Estibas",                 "Control de estibas"),
    Permiso("movimientos",  "Movimientos",             "Control de estibas"),
    Permiso("manifiestos",  "Manifiestos",             "Control de estibas"),
    Permiso("ubicaciones",  "Ubicaciones",             "Control de estibas"),
    Permiso("danos",        "Daños",                   "Control de estibas"),
    Permiso("trazabilidad", "Trazabilidad",            "Control de estibas"),
    Permiso("consultas",    "Consultas",               "Control de estibas"),
    Permiso("costos",       "Costos",                  "Control de estibas"),

    # ── Operación ─────────────────────────────────────────────────────────
    Permiso("vehiculos",    "Vehículos",               "Operación"),
    Permiso("proveedores",  "Proveedores",             "Operación"),
    Permiso("alertas",      "Alertas",                 "Operación"),
    Permiso("mantenimiento", "Mantenimiento",          "Operación"),

    # ── Módulos ───────────────────────────────────────────────────────────
    Permiso("tx",   "TarifaX · Motor de tarifas",      "Módulos"),
    Permiso("ft",   "Fletes",                          "Módulos"),
    Permiso("gf",   "Gestión de flotas",               "Módulos"),
    Permiso("ml",   "Mantenimiento locativo",          "Módulos"),
    Permiso("wms",  "WMS · Almacenes",                 "Módulos"),
    Permiso("gh",   "Gestión humana",                  "Módulos"),
    Permiso("tms",  "TMS · Transporte",                "Módulos"),
    Permiso("dms",  "DMS · Gestión documental",        "Módulos"),
    Permiso("qms",  "QMS · Calidad",                   "Módulos"),
    Permiso("grc",  "GRC · Riesgo y cumplimiento",     "Módulos"),
    Permiso("lms",  "LMS · Formación",                 "Módulos"),
    Permiso("crm",  "CRM · Comercial",                 "Módulos"),
    Permiso("eam",  "CMMS / EAM · Mantenimiento",      "Módulos"),
    Permiso("mes",  "MES · Producción",                "Módulos"),
    Permiso("aps",  "APS · Planeación",                "Módulos"),
    # Los tres que faltaban: el portal los exigía y el servidor los descartaba.
    Permiso("erp",  "ERP · Financiero",                "Módulos"),
    Permiso("scm",  "SCM · Cadena de suministro",      "Módulos"),
    Permiso("sst",  "SST · Seguridad y salud",         "Módulos"),
    Permiso("ags",  "AGS · Agenda de servicios",       "Módulos"),
    Permiso("pos",  "POS · Punto de venta",            "Módulos"),

    # ── Finanzas ──────────────────────────────────────────────────────────
    #
    # El ERP financiero necesita permisos más finos que «ve el módulo o no».
    # Quien registra una factura no debería poder cerrar un período, y quien
    # consulta la cartera no tiene por qué poder anular un asiento.
    #
    # `erp` sigue siendo la llave del módulo: sin él no se entra. Estos afinan
    # qué se puede hacer una vez dentro.
    Permiso("fin_contabilidad",  "Ver contabilidad y libros",   "Finanzas"),
    Permiso("fin_comprobantes",  "Crear y editar comprobantes", "Finanzas"),
    # Contabilizar es lo que vuelve un borrador irreversible, y anular es lo que
    # toca un asiento ya en firme. Van aparte de crear por eso.
    Permiso("fin_contabilizar",  "Contabilizar comprobantes",   "Finanzas"),
    Permiso("fin_anular",        "Anular comprobantes",         "Finanzas"),
    Permiso("fin_cartera",       "Ver cartera y CxC",           "Finanzas"),
    Permiso("fin_pagos",         "Registrar pagos y recaudos",  "Finanzas"),
    Permiso("fin_tesoreria",     "Bancos y tesorería",          "Finanzas"),
    Permiso("fin_conciliar",     "Conciliación bancaria",       "Finanzas"),
    Permiso("fin_impuestos",     "Impuestos y retenciones",     "Finanzas"),
    # Cerrar y reabrir son la frontera entre lo declarado y lo modificable. Es
    # el permiso más delicado del módulo y por eso va solo.
    Permiso("fin_periodos",      "Cerrar y reabrir períodos",   "Finanzas"),
    Permiso("fin_reportes",      "Estados financieros",         "Finanzas"),
    Permiso("fin_exportar",      "Exportar información",        "Finanzas"),
    # Cambiar una regla contable cambia cómo se contabiliza TODO lo que venga
    # después. Es configuración, no operación.
    Permiso("fin_parametrizar",  "Plan de cuentas y reglas",    "Finanzas"),
    Permiso("fin_terceros",      "Maestro de terceros",         "Finanzas"),

    # ── Administración ────────────────────────────────────────────────────
    # Quien lo tenga puede crear usuarios y perfiles de su propia empresa, así
    # que se separa del resto: es el único que reparte poder.
    Permiso("usuarios", "Usuarios y perfiles",         "Administración"),
]

CLAVES: tuple = tuple(p.clave for p in PERMISOS_PERFIL)
POR_CLAVE: Dict[str, Permiso] = {p.clave: p for p in PERMISOS_PERFIL}


def normalizar(permisos: Dict[str, object] | None) -> Dict[str, bool]:
    """Deja el mapa de permisos con todas las claves conocidas y solo esas.

    Lo que llegue de más se descarta —una clave inventada no la mira nadie— y
    lo que falte queda en «no». Guardar el mapa completo y no solo lo marcado
    hace que revisar un perfil no dependa de saber qué claves existían el día
    que se creó.
    """
    dado = permisos or {}
    return {c: bool(dado.get(c)) for c in CLAVES}
