"""
Multicliente por esquema de PostgreSQL.

Cada cliente vive en su propio esquema con el juego completo de tablas. El
inquilino se resuelve una vez por petición y se fija en la conexión con
`search_path`, así que las consultas de los módulos no llevan filtro alguno:
una consulta mal escrita no puede ver datos de otro cliente porque no los
alcanza desde su conexión.

La alternativa —una columna `tenant_id` en las 414 tablas— dejaría la
separación en manos de que nadie olvide un `WHERE` en ninguna de las 1.236
rutas, hoy ni nunca. Acá el olvido no es posible.

El registro de clientes vive en `public`, fuera de los esquemas, porque hay que
poder consultarlo antes de saber a qué cliente se entra.
"""
from contextvars import ContextVar
from typing import Optional

# Esquema del cliente en curso. Se llena por petición y se limpia al terminar.
_esquema_actual: ContextVar[Optional[str]] = ContextVar("esquema_actual", default=None)

# Donde viven el registro de clientes y todo lo que es común a la plataforma.
ESQUEMA_PLATAFORMA = "public"

# Nombre del esquema de quien ya estaba antes de que esto fuera multicliente.
# Sus datos se quedan donde están y ese cliente pasa a ser uno más.
ESQUEMA_POR_DEFECTO = "public"


def fijar_esquema(esquema: Optional[str]) -> None:
    _esquema_actual.set(esquema)


def esquema_actual() -> Optional[str]:
    return _esquema_actual.get()


def codigo_valido(codigo: str) -> bool:
    """El código del cliente termina siendo un nombre de esquema.

    Se restringe a minúsculas, dígitos y guion bajo para que no haya forma de
    inyectar SQL por el nombre: `search_path` no admite parámetros y hay que
    interpolarlo.
    """
    if not codigo or len(codigo) > 40:
        return False
    if not codigo[0].isalpha():
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in codigo)


def nombre_esquema(codigo: str) -> str:
    """El esquema de un cliente, a partir de su código."""
    return codigo if codigo == ESQUEMA_POR_DEFECTO else f"cli_{codigo}"


# ─── Los dos niveles de administración ────────────────────────────────────────
#
# Administrar la propia empresa —usuarios, catálogos, configuración— y
# administrar la plataforma —dar de alta o suspender empresas— son cosas
# distintas. El rol ADMINISTRADOR lo tiene el administrador de cada cliente
# dentro de su esquema, así que usarlo para lo segundo dejaba que el
# administrador de una empresa listara y suspendiera a las demás.
#
# Quién opera la plataforma se marca en el registro de clientes, que vive fuera
# de los esquemas: si la marca estuviera dentro del esquema de un cliente, ese
# cliente podría dársela a sí mismo.
