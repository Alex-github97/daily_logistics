"""
Los módulos que se pueden contratar, y a qué rutas corresponde cada uno.

Esta tabla es la que convierte «el cliente contrató EAM» en algo que el
servidor puede hacer cumplir: sin el mapa de prefijos, la lista de módulos
contratados sería decorativa y cualquiera podría entrar a un módulo que no paga
escribiendo la URL a mano.
"""
from typing import Dict, List, NamedTuple, Optional


class Modulo(NamedTuple):
    clave: str
    nombre: str
    # Prefijos de la API que pertenecen a este módulo.
    prefijos: tuple
    # Los que no se pueden quitar: sin ellos no se puede ni entrar ni
    # administrar la propia empresa, así que no tiene sentido venderlos aparte.
    esencial: bool = False


MODULOS: List[Modulo] = [
    # Daily Logistics solo comercializa estos tres módulos. Las rutas de apoyo
    # que consumen (conductores de /hcm, vehículos de /eam, resoluciones DIAN
    # de /erp) no se venden aparte: quedan fuera del catálogo y por eso no se
    # cortan por contrato.
    Modulo("wms",     "WMS · Almacenes", ("/wms",)),
    Modulo("pos",     "POS · Punto de Venta", ("/pos",)),
    Modulo("tms",     "TMS · Transporte", ("/tms", "/fletes")),
    # Jornadas, estaciones de trabajo y productividad de las personas que operan.
    Modulo("wfm",     "WFM · Personal operativo", ("/personal",)),
    # Sin esto nadie entra ni administra su empresa: no se vende aparte.
    Modulo("base", "Acceso y administración",
           ("/auth", "/usuarios", "/roles", "/alertas", "/proveedores", "/catalogos",
            "/plataforma", "/configuracion"),
           esencial=True),
]

POR_CLAVE: Dict[str, Modulo] = {m.clave: m for m in MODULOS}

# Los que toda empresa tiene desde el primer día, sin negociarlos.
ESENCIALES = tuple(m.clave for m in MODULOS if m.esencial)

# Lo que se activa por defecto al dar de alta una empresa. Se deja en lo mínimo
# a propósito: es más fácil habilitar lo que se vendió que descubrir tarde que
# un cliente lleva meses usando algo que nunca contrató.
POR_DEFECTO = ESENCIALES + ("wms", "pos", "tms", "wfm")


def modulo_de_ruta(ruta: str) -> Optional[str]:
    """A qué módulo pertenece una ruta de la API, o None si a ninguno.

    Se compara sobre lo que sigue a `/api/v1`. El prefijo más largo gana, para
    que `/eam` no le robe una ruta a un módulo con un prefijo más específico.
    """
    resto = ruta.split("/api/v1", 1)[-1] if "/api/v1" in ruta else ruta
    mejor: Optional[str] = None
    largo = -1
    for m in MODULOS:
        for p in m.prefijos:
            if (resto == p or resto.startswith(p + "/") or resto.startswith(p + "?")) and len(p) > largo:
                mejor, largo = m.clave, len(p)
    return mejor
