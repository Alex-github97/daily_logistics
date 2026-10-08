"""
Los campos configurables: qué aplica, qué es válido y qué se guarda.

El valor vive en `gp_incidencia.campos`, una columna `jsonb`. Esta es la capa que
impide que eso se convierta en un basurero: nada entra sin estar declarado en
`gp_campo` y sin pasar la validación de su tipo.

Dos reglas que no se negocian:

  · **Una clave que nadie declaró se rechaza**, no se guarda «por si acaso».
    Guardar lo que llegue significa que un error de tipeo en el navegador crea un
    campo fantasma que ninguna pantalla muestra y ningún filtro encuentra, y que
    nadie descubre hasta que audita el jsonb a mano.
  · **La validación es la del servidor.** La misma definición alimenta el
    formulario, así que la pantalla y el servidor no pueden discrepar; pero quien
    arme la petición a mano se topa igual con esto.

La lista de campos aplicables sale de `gp_esquema_campo`, que puede ser global
(sin proyecto ni tipo) o cada vez más específica. Gana la regla más específica:
así se define una vez lo común y se ajusta solo donde hace falta.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.gestion import (
    GPCampo, GPCampoOpcion, GPEsquemaCampo,
)


class CampoAplicable:
    """Un campo tal como aplica a un proyecto y un tipo concretos."""

    def __init__(self, campo: GPCampo, obligatorio: bool, solo_lectura: bool,
                 orden: int, opciones: List[GPCampoOpcion]):
        self.campo = campo
        self.obligatorio = obligatorio
        self.solo_lectura = solo_lectura
        self.orden = orden
        self.opciones = opciones


async def campos_aplicables(db: AsyncSession, proyecto_id: Optional[int],
                            tipo_id: Optional[int]) -> List[CampoAplicable]:
    """Los campos que aplican, resolviendo de lo general a lo específico.

    Se recogen las cuatro combinaciones —global, por proyecto, por tipo, y por
    los dos— y para cada campo se queda la más específica. Sin esta precedencia
    habría que repetir la configuración común en cada proyecto, y la primera vez
    que alguien la cambiara quedaría desincronizada en los demás.
    """
    # `IN (:proyecto, NULL)` NO sirve acá: en SQL, comparar NULL con cualquier
    # cosa da NULL, así que las reglas globales —las que tienen proyecto_id
    # vacío— nunca entrarían y ningún campo aplicaría a nada. Va con OR e
    # `IS NULL` explícito.
    ambito = (
        GPEsquemaCampo.proyecto_id.is_(None) if proyecto_id is None
        else or_(GPEsquemaCampo.proyecto_id == proyecto_id,
                 GPEsquemaCampo.proyecto_id.is_(None))
    )
    r = await db.execute(select(GPEsquemaCampo).where(ambito))
    reglas = [
        e for e in r.scalars().all()
        if e.tipo_id is None or e.tipo_id == tipo_id
    ]
    if not reglas:
        return []

    # Cuanto más concreta, más manda.
    def peso(e: GPEsquemaCampo) -> int:
        return (1 if e.proyecto_id is not None else 0) + \
               (2 if e.tipo_id is not None else 0)

    mejor: Dict[int, GPEsquemaCampo] = {}
    for regla in reglas:
        actual = mejor.get(regla.campo_id)
        if actual is None or peso(regla) > peso(actual):
            mejor[regla.campo_id] = regla
    if not mejor:
        return []

    r = await db.execute(
        select(GPCampo).where(
            GPCampo.id.in_(list(mejor)), GPCampo.archivado.is_(False)))
    campos = {c.id: c for c in r.scalars().all()}
    if not campos:
        return []

    r = await db.execute(
        select(GPCampoOpcion).where(
            GPCampoOpcion.campo_id.in_(list(campos)),
            GPCampoOpcion.archivada.is_(False),
        ).order_by(GPCampoOpcion.orden))
    opciones: Dict[int, List[GPCampoOpcion]] = {}
    for o in r.scalars().all():
        opciones.setdefault(o.campo_id, []).append(o)

    salida = [
        CampoAplicable(campos[cid], regla.obligatorio, regla.solo_lectura,
                       regla.orden, opciones.get(cid, []))
        for cid, regla in mejor.items() if cid in campos
    ]
    salida.sort(key=lambda c: (c.orden, c.campo.nombre))
    return salida


# ─── Validación por tipo ──────────────────────────────────────────────────────
#
# Cada validador devuelve el valor ya normalizado, o levanta ValueError con un
# mensaje que dice qué está mal. El mensaje llega tal cual a quien está llenando
# el formulario, así que se escribe para esa persona y no para el registro.

def _texto(valor: Any, reglas: dict, _opciones) -> str:
    s = str(valor).strip()
    maximo = reglas.get("max")
    if maximo and len(s) > int(maximo):
        raise ValueError(f"no puede pasar de {maximo} caracteres (tiene {len(s)})")
    minimo = reglas.get("min")
    if minimo and len(s) < int(minimo):
        raise ValueError(f"necesita al menos {minimo} caracteres")
    patron = reglas.get("patron")
    if patron:
        import re
        if not re.fullmatch(patron, s):
            raise ValueError(reglas.get("mensaje") or "no tiene el formato esperado")
    return s


def _numero(valor: Any, reglas: dict, _opciones) -> int:
    try:
        # `int(float(...))` no: convertiría 2.7 en 2 sin avisar.
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError("tiene que ser un número entero")
    return _rango(n, reglas)


def _decimal(valor: Any, reglas: dict, _opciones) -> float:
    try:
        n = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("tiene que ser un número")
    decimales = reglas.get("decimales")
    if decimales is not None:
        n = round(n, int(decimales))
    return _rango(n, reglas)


def _rango(n, reglas: dict):
    if reglas.get("min") is not None and n < reglas["min"]:
        raise ValueError(f"no puede ser menor que {reglas['min']}")
    if reglas.get("max") is not None and n > reglas["max"]:
        raise ValueError(f"no puede ser mayor que {reglas['max']}")
    return n


def _booleano(valor: Any, _reglas, _opciones) -> bool:
    if isinstance(valor, bool):
        return valor
    s = str(valor).strip().lower()
    if s in ("true", "1", "si", "sí"):
        return True
    if s in ("false", "0", "no"):
        return False
    raise ValueError("tiene que ser sí o no")


def _fecha(valor: Any, _reglas, _opciones) -> str:
    s = str(valor).strip()
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        raise ValueError("tiene que ser una fecha (AAAA-MM-DD)")


def _fecha_hora(valor: Any, _reglas, _opciones) -> str:
    s = str(valor).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).isoformat()
    except ValueError:
        raise ValueError("tiene que ser una fecha con hora")


def _lista(valor: Any, _reglas, opciones: List[GPCampoOpcion]) -> str:
    s = str(valor).strip()
    validas = {o.valor for o in opciones}
    if s not in validas:
        raise ValueError(
            "no es una de las opciones" +
            (f" ({', '.join(sorted(validas))})" if len(validas) <= 12 else ""))
    return s


def _lista_multiple(valor: Any, _reglas, opciones: List[GPCampoOpcion]) -> List[str]:
    if not isinstance(valor, (list, tuple)):
        raise ValueError("tiene que ser una lista de opciones")
    validas = {o.valor for o in opciones}
    fuera = [str(v) for v in valor if str(v).strip() not in validas]
    if fuera:
        raise ValueError(f"estas no son opciones válidas: {', '.join(fuera)}")
    # Sin repetidos y en orden estable, para que dos guardados iguales produzcan
    # el mismo jsonb y no aparezcan cambios donde no los hubo.
    return sorted({str(v).strip() for v in valor})


def _usuario(valor: Any, _reglas, _opciones) -> str:
    s = str(valor).strip()
    if not s:
        raise ValueError("no puede quedar vacío")
    return s[:80]


def _url(valor: Any, _reglas, _opciones) -> str:
    s = str(valor).strip()
    if not (s.startswith("http://") or s.startswith("https://")):
        raise ValueError("tiene que empezar por http:// o https://")
    return s


def _etiquetas(valor: Any, _reglas, _opciones) -> List[str]:
    if isinstance(valor, str):
        valor = [t for t in valor.split(",")]
    if not isinstance(valor, (list, tuple)):
        raise ValueError("tiene que ser una lista de etiquetas")
    return sorted({str(t).strip() for t in valor if str(t).strip()})


def _correo(valor: Any, _reglas, _opciones) -> str:
    """Una comprobación deliberadamente laxa.

    Validar correos «bien» es un pozo sin fondo —hay direcciones legales que
    ninguna expresión regular razonable acepta—, y una regla estricta rechaza
    direcciones que sí existen. Se comprueba lo que de verdad delata una errata:
    que haya algo, una arroba y un punto después.
    """
    s = str(valor).strip()
    if s.count("@") != 1:
        raise ValueError("tiene que ser una dirección de correo")
    antes, despues = s.split("@")
    if not antes or "." not in despues or despues.startswith(".") or despues.endswith("."):
        raise ValueError("tiene que ser una dirección de correo")
    return s


def _adjunto(valor: Any, _reglas, _opciones) -> str:
    """La referencia a un archivo ya subido.

    El archivo no viaja por acá: se sube por su propio endpoint, que comprueba
    tamaño, extensión y permisos. Acá solo queda constancia de a cuál apunta.
    """
    s = str(valor).strip()
    if not s:
        raise ValueError("no apunta a ningún archivo")
    return s[:200]


VALIDADORES = {
    "TEXTO": _texto,
    "TEXTO_LARGO": _texto,
    "TEXTO_RICO": _texto,
    "CORREO": _correo,
    "ADJUNTO": _adjunto,
    "NUMERO": _numero,
    "DECIMAL": _decimal,
    "FECHA": _fecha,
    "FECHA_HORA": _fecha_hora,
    "BOOLEANO": _booleano,
    "LISTA": _lista,
    "LISTA_MULTIPLE": _lista_multiple,
    "USUARIO": _usuario,
    "URL": _url,
    "ETIQUETAS": _etiquetas,
}


def validar(aplicables: List[CampoAplicable], entrantes: Dict[str, Any],
            previos: Optional[Dict[str, Any]] = None,
            exigir_obligatorios: bool = True) -> Dict[str, Any]:
    """Deja el jsonb de campos listo para guardar, o explica qué está mal.

    `previos` son los valores que ya tenía la incidencia: al editar solo se manda
    lo que cambia, y lo que no venga se conserva. `exigir_obligatorios` se apaga
    en los borradores, donde falta información a propósito.

    Todos los errores se juntan y se devuelven de una vez. Devolverlos de a uno
    obliga a quien llena el formulario a corregir, reenviar, descubrir el
    siguiente, y así.
    """
    por_clave = {c.campo.clave: c for c in aplicables}
    resultado: Dict[str, Any] = dict(previos or {})
    problemas: List[str] = []

    for clave, valor in (entrantes or {}).items():
        aplicable = por_clave.get(clave)
        if aplicable is None:
            problemas.append(
                f"«{clave}» no es un campo de este tipo de incidencia. "
                f"Si hace falta, créelo en la configuración.")
            continue
        if aplicable.solo_lectura:
            problemas.append(f"«{aplicable.campo.nombre}» no se puede editar a mano.")
            continue

        # Vacío borra el valor. Es distinto de no mandar la clave, que lo deja
        # como estaba, y hay que poder hacer las dos cosas.
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            resultado.pop(clave, None)
            continue

        validador = VALIDADORES.get(aplicable.campo.tipo)
        if validador is None:
            problemas.append(
                f"«{aplicable.campo.nombre}» es de un tipo que el servidor no "
                f"sabe validar ({aplicable.campo.tipo}).")
            continue
        try:
            resultado[clave] = validador(
                valor, aplicable.campo.validacion or {}, aplicable.opciones)
        except ValueError as e:
            problemas.append(f"«{aplicable.campo.nombre}» {e}.")

    if exigir_obligatorios:
        for aplicable in aplicables:
            if not aplicable.obligatorio:
                continue
            v = resultado.get(aplicable.campo.clave)
            if v is None or v == "" or v == []:
                problemas.append(f"«{aplicable.campo.nombre}» es obligatorio.")

    if problemas:
        raise HTTPException(422, {"campos": problemas})
    return resultado


def descripcion_de(aplicables: List[CampoAplicable]) -> List[dict]:
    """La definición que necesita la pantalla para dibujar el formulario.

    Sale de la misma fuente que la validación a propósito: si la pantalla
    construyera su propia idea de los campos, tarde o temprano aceptaría algo que
    el servidor descarta y el usuario perdería lo escrito sin entender por qué.
    """
    return [
        {
            "clave": a.campo.clave,
            "nombre": a.campo.nombre,
            "descripcion": a.campo.descripcion,
            "ayuda": a.campo.ayuda,
            "tipo": a.campo.tipo,
            "obligatorio": a.obligatorio,
            "solo_lectura": a.solo_lectura,
            "validacion": a.campo.validacion or {},
            "valor_defecto": a.campo.valor_defecto,
            "filtrable": a.campo.filtrable,
            "orden": a.orden,
            "opciones": [
                {"valor": o.valor, "etiqueta": o.etiqueta, "color": o.color}
                for o in a.opciones
            ],
        }
        for a in aplicables
    ]
