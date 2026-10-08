"""
Roles y permisos de la consola del operador.

Hasta ahora, entrar a la consola era todo o nada: cualquier administrador de la
empresa operadora podía dar de alta empresas, ver la cartera de todos los
clientes, restablecer contraseñas y atender soporte. Eso está bien con una
persona y deja de estarlo con tres: quien atiende soporte no necesita ver
cuánto factura cada cliente, y quien lleva la cartera no necesita poder entrar a
la cuenta de nadie.

Los permisos se declaran acá y no en cada endpoint para que la respuesta a
«¿quién puede hacer qué?» esté en un solo archivo y se pueda leer de corrido.
"""
from typing import Dict, List, NamedTuple


class Permiso(NamedTuple):
    clave: str
    descripcion: str


# El catálogo completo. Agregar un permiso es una línea acá y su uso en el
# endpoint correspondiente.
PERMISOS: List[Permiso] = [
    Permiso("empresas.ver",        "Ver las empresas y sus usuarios"),
    Permiso("empresas.crear",      "Dar de alta empresas nuevas"),
    Permiso("empresas.editar",     "Editar datos y suspender empresas"),
    Permiso("empresas.modulos",    "Cambiar qué módulos tiene contratados una empresa"),
    Permiso("usuarios.crear",      "Crear usuarios dentro de una empresa"),
    Permiso("usuarios.editar",     "Activar, desactivar y editar usuarios de una empresa"),
    Permiso("usuarios.clave",      "Restablecer la contraseña de un usuario"),
    Permiso("comercial.ver",       "Ver contratos, contactos y documentos"),
    Permiso("comercial.editar",    "Editar contratos, contactos y documentos"),
    Permiso("contabilidad.ver",    "Ver facturas, pagos y la contabilidad consolidada"),
    Permiso("contabilidad.editar", "Emitir facturas, notas crédito y registrar pagos"),
    Permiso("soporte.ver",         "Ver la cola de soporte y el tablero"),
    Permiso("soporte.atender",     "Responder, clasificar y mover solicitudes"),
    Permiso("gestion.ver",         "Ver los proyectos y sus incidencias"),
    Permiso("gestion.trabajar",    "Crear, editar, comentar y mover incidencias"),
    # Separado de «trabajar» a propósito: cambiar un workflow o un campo afecta a
    # todo el mundo y a las incidencias que ya existen, mientras que mover una
    # tarjeta solo afecta a esa. Quien trabaja a diario no necesita lo primero.
    Permiso("gestion.configurar",  "Definir proyectos, workflows, tipos y campos"),
    Permiso("equipo.gestionar",    "Administrar el equipo de la consola y sus roles"),
    Permiso("bitacora.ver",        "Ver la bitácora de acciones"),
    Permiso("landing.editar",      "Editar el contenido de la página pública"),
]

TODOS = tuple(p.clave for p in PERMISOS)


class Rol(NamedTuple):
    clave: str
    nombre: str
    descripcion: str
    permisos: tuple


ROLES: List[Rol] = [
    Rol("PROPIETARIO", "Propietario",
        "Todo, incluido administrar el equipo de la consola.",
        TODOS),
    Rol("ADMINISTRADOR", "Administrador",
        "Todo sobre empresas, comercial y soporte. No administra el equipo.",
        tuple(p for p in TODOS if p != "equipo.gestionar")),
    Rol("COMERCIAL", "Comercial",
        "Contratos, facturación y cartera. No entra a las cuentas de los clientes "
        "ni restablece contraseñas.",
        ("empresas.ver", "empresas.crear", "empresas.editar", "empresas.modulos",
         "comercial.ver", "comercial.editar",
         "contabilidad.ver", "contabilidad.editar", "bitacora.ver",
         # Comercial edita la pagina publica: es quien conoce el discurso de venta.
         "landing.editar")),
    Rol("SOPORTE", "Soporte técnico",
        "Atiende la mesa de ayuda y el tablero. Ve las empresas para dar contexto, "
        "pero no su información comercial.",
        # Trabaja las incidencias porque es quien recibe lo que llega por el
        # chat, pero no configura: un workflow mal cambiado en medio de una
        # atención deja tickets atascados sin transición de salida.
        ("empresas.ver", "usuarios.clave",
         "soporte.ver", "soporte.atender",
         "gestion.ver", "gestion.trabajar", "bitacora.ver")),
    Rol("CONSULTA", "Solo consulta",
        "Ve todo pero no cambia nada. Útil para dirección y auditoría.",
        ("empresas.ver", "comercial.ver", "contabilidad.ver",
         "soporte.ver", "gestion.ver", "bitacora.ver")),
]

POR_CLAVE: Dict[str, Rol] = {r.clave: r for r in ROLES}


def permisos_de(rol: str) -> tuple:
    """Los permisos de un rol. Un rol desconocido no da ninguno.

    Se falla cerrado a propósito: si mañana se borra un rol y queda alguien
    apuntando a él, es preferible que no pueda hacer nada a que pueda hacerlo
    todo.
    """
    definicion = POR_CLAVE.get((rol or "").upper())
    return definicion.permisos if definicion else ()
