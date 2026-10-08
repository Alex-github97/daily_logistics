"""
El lenguaje de filtros: de un texto a SQL parametrizado.

    proyecto = "ERP" Y prioridad EN ("ALTA", "CRITICA") Y asignado = yo()
    estado NO EN ("Hecho", "Descartada") Y actualizado > hace(7, dias)
    modulo = "EAM" Y etiquetas CONTIENE "regresion" ORDENAR POR vence ASC

La cadena es siempre la misma y no hay atajos:

    texto → léxico → sintaxis → árbol → **validación** → SQLAlchemy → SQL

El eslabón que sostiene todo es la validación. Ahí se rechaza lo que no está
permitido: un campo que no existe o no es filtrable, un operador que no aplica a
ese tipo, un literal que no convierte, una consulta desmedida. Un camino que no
pase por ahí es un agujero, así que **el constructor visual genera este mismo
texto** en vez de tener su propia ruta.

Lo que hace que sea seguro, y por qué cada cosa:

  · **Los identificadores salen de una lista blanca.** No hay forma de nombrar
    una columna o una tabla: si no está en el registro, no existe.
  · **Las uniones son un juego cerrado.** El constructor sabe resolver proyecto,
    tipo, estado, prioridad y sprint por subconsulta, y nada más.
  · **Los literales son siempre parámetros.** Nunca texto interpolado. Es esto lo
    que vuelve irrelevante lo que el usuario escriba: puede escribir comillas,
    punto y coma o `DROP TABLE` y llegan como el contenido de un parámetro.
  · **La complejidad está acotada.** Un límite de condiciones y de profundidad
    impide una consulta que tumbe la base sin que nadie tuviera mala intención.
  · **Los permisos entran en el árbol**, no se aplican después de consultar.

Nunca se guarda ni se ejecuta SQL escrito por el usuario. Un filtro guardado
guarda su texto, y el SQL se vuelve a generar cada vez desde el árbol validado.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, cast, func, not_, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Numeric, TIMESTAMP

from app.infrastructure.models.gestion import (
    GPCampo, GPEstado, GPIncidencia, GPPrioridad, GPProyecto, GPSprint,
    GPTipoIncidencia,
)

# ─── Topes ────────────────────────────────────────────────────────────────────
#
# No son preferencias. Sin ellos, una expresión con doscientos paréntesis
# anidados o una lista de cien mil elementos deja al planificador dando vueltas y
# el proceso se cae; y eso no necesita mala intención, basta con un pegado
# desafortunado.
MAX_LARGO = 4000
MAX_CONDICIONES = 40
MAX_PROFUNDIDAD = 8
MAX_EN = 200


class ErrorDeConsulta(HTTPException):
    """Un problema del filtro, señalando dónde.

    La posición no es un lujo: sin ella, «error de sintaxis» en una expresión de
    tres líneas obliga a borrarla entera y volver a empezar.
    """

    def __init__(self, mensaje: str, posicion: Optional[int] = None):
        super().__init__(400, {"consulta": mensaje, "posicion": posicion})
        self.mensaje = mensaje
        self.posicion = posicion


# ─── Análisis léxico ──────────────────────────────────────────────────────────

PALABRAS = {
    "Y", "O", "NO", "EN", "ES", "VACIO", "VACÍO", "CONTIENE", "EMPIEZA",
    "TERMINA", "ORDENAR", "POR", "ASC", "DESC", "CON",
}

SIMBOLOS = ("!=", ">=", "<=", "=", ">", "<", "(", ")", ",")


class Token:
    __slots__ = ("tipo", "valor", "pos")

    def __init__(self, tipo: str, valor: Any, pos: int):
        self.tipo = tipo          # PALABRA · IDENT · TEXTO · NUMERO · SIMBOLO · FIN
        self.valor = valor
        self.pos = pos

    def __repr__(self) -> str:
        return f"{self.tipo}({self.valor!r})"


def analizar_lexico(texto: str) -> List[Token]:
    if len(texto) > MAX_LARGO:
        raise ErrorDeConsulta(
            f"El filtro es demasiado largo ({len(texto)} caracteres, el máximo "
            f"son {MAX_LARGO}).")

    tokens: List[Token] = []
    i, n = 0, len(texto)

    while i < n:
        c = texto[i]

        if c.isspace():
            i += 1
            continue

        # Cadena entre comillas. Se admiten las dos porque la gente escribe con
        # las que tenga a mano, y la barra invertida escapa la comilla de cierre.
        if c in ('"', "'"):
            cierre, j, partes = c, i + 1, []
            while j < n:
                if texto[j] == "\\" and j + 1 < n:
                    partes.append(texto[j + 1])
                    j += 2
                    continue
                if texto[j] == cierre:
                    break
                partes.append(texto[j])
                j += 1
            if j >= n:
                raise ErrorDeConsulta(
                    "Falta la comilla de cierre.", i)
            tokens.append(Token("TEXTO", "".join(partes), i))
            i = j + 1
            continue

        if c.isdigit() or (c == "-" and i + 1 < n and texto[i + 1].isdigit()):
            j = i + 1
            while j < n and (texto[j].isdigit() or texto[j] in ".-:"):
                j += 1
            crudo = texto[i:j]
            # Una fecha es un literal más, pero se distingue acá para no tener
            # que adivinar después si «2026-09-01» era una resta.
            if "-" in crudo[1:] or ":" in crudo:
                tokens.append(Token("TEXTO", crudo, i))
            else:
                try:
                    tokens.append(Token(
                        "NUMERO", float(crudo) if "." in crudo else int(crudo), i))
                except ValueError:
                    raise ErrorDeConsulta(f"«{crudo}» no es un número.", i)
            i = j
            continue

        if c.isalpha() or c == "_":
            j = i
            while j < n and (texto[j].isalnum() or texto[j] in "_."):
                j += 1
            palabra = texto[i:j]
            arriba = palabra.upper()
            if arriba in PALABRAS:
                tokens.append(Token("PALABRA", arriba, i))
            else:
                tokens.append(Token("IDENT", palabra, i))
            i = j
            continue

        for simbolo in SIMBOLOS:
            if texto.startswith(simbolo, i):
                tokens.append(Token("SIMBOLO", simbolo, i))
                i += len(simbolo)
                break
        else:
            raise ErrorDeConsulta(f"No entiendo el carácter «{c}».", i)

    tokens.append(Token("FIN", None, n))
    return tokens


# ─── El árbol ─────────────────────────────────────────────────────────────────

class Nodo:
    pass


class Y(Nodo):
    def __init__(self, partes: List[Nodo]):
        self.partes = partes


class O(Nodo):
    def __init__(self, partes: List[Nodo]):
        self.partes = partes


class No(Nodo):
    def __init__(self, parte: Nodo):
        self.parte = parte


class Comparacion(Nodo):
    def __init__(self, campo: str, operador: str, valor: Any, pos: int):
        self.campo = campo
        self.operador = operador
        self.valor = valor
        self.pos = pos


class Llamada:
    """Una función del lenguaje: yo(), hoy(), hace(7, dias)…"""

    def __init__(self, nombre: str, argumentos: List[Any], pos: int):
        self.nombre = nombre
        self.argumentos = argumentos
        self.pos = pos


class Orden:
    def __init__(self, campo: str, ascendente: bool, pos: int):
        self.campo = campo
        self.ascendente = ascendente
        self.pos = pos


# ─── Análisis sintáctico ──────────────────────────────────────────────────────
#
# Descendente recursivo, con la precedencia escrita en la forma de las
# funciones: `O` llama a `Y`, que llama a `NO`, que llama a la comparación. Así
# `a Y b O c` se agrupa como `(a Y b) O c` sin tabla de precedencias que
# mantener aparte.

OPERADORES_SIMBOLO = {"=", "!=", ">", ">=", "<", "<="}


class Analizador:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.i = 0
        self.condiciones = 0

    # ── utilidades ──
    def actual(self) -> Token:
        return self.tokens[self.i]

    def siguiente(self, salto: int = 1) -> Token:
        j = self.i + salto
        return self.tokens[j] if j < len(self.tokens) else self.tokens[-1]

    def comer(self) -> Token:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def es_palabra(self, *cuales: str) -> bool:
        t = self.actual()
        return t.tipo == "PALABRA" and t.valor in cuales

    def es_simbolo(self, *cuales: str) -> bool:
        t = self.actual()
        return t.tipo == "SIMBOLO" and t.valor in cuales

    def exigir_simbolo(self, cual: str) -> None:
        if not self.es_simbolo(cual):
            raise ErrorDeConsulta(
                f"Esperaba «{cual}» y encontré «{self.actual().valor}».",
                self.actual().pos)
        self.comer()

    # ── gramática ──
    def analizar(self) -> Tuple[Optional[Nodo], Optional[Orden]]:
        if self.actual().tipo == "FIN":
            return None, None

        raiz = None
        if not self.es_palabra("ORDENAR"):
            raiz = self.expresion(1)

        orden = None
        if self.es_palabra("ORDENAR"):
            orden = self.ordenar()

        if self.actual().tipo != "FIN":
            raise ErrorDeConsulta(
                f"Sobra «{self.actual().valor}» al final del filtro.",
                self.actual().pos)
        return raiz, orden

    def expresion(self, profundidad: int) -> Nodo:
        if profundidad > MAX_PROFUNDIDAD:
            raise ErrorDeConsulta(
                f"El filtro tiene demasiados paréntesis anidados (el máximo son "
                f"{MAX_PROFUNDIDAD} niveles).", self.actual().pos)

        partes = [self.conjuncion(profundidad)]
        while self.es_palabra("O"):
            self.comer()
            partes.append(self.conjuncion(profundidad))
        return partes[0] if len(partes) == 1 else O(partes)

    def conjuncion(self, profundidad: int) -> Nodo:
        partes = [self.negacion(profundidad)]
        while self.es_palabra("Y"):
            self.comer()
            partes.append(self.negacion(profundidad))
        return partes[0] if len(partes) == 1 else Y(partes)

    def negacion(self, profundidad: int) -> Nodo:
        # `NO` seguido de paréntesis o de otro `NO` niega un bloque; delante de un
        # campo forma parte del operador («NO EN», «NO CONTIENE»), así que ahí no
        # se consume.
        if self.es_palabra("NO") and (
                self.siguiente().tipo == "SIMBOLO" and self.siguiente().valor == "("
                or self.siguiente().tipo == "PALABRA" and self.siguiente().valor == "NO"):
            self.comer()
            return No(self.negacion(profundidad))
        return self.atomo(profundidad)

    def atomo(self, profundidad: int) -> Nodo:
        if self.es_simbolo("("):
            self.comer()
            dentro = self.expresion(profundidad + 1)
            self.exigir_simbolo(")")
            return dentro
        return self.comparacion()

    def comparacion(self) -> Comparacion:
        self.condiciones += 1
        if self.condiciones > MAX_CONDICIONES:
            raise ErrorDeConsulta(
                f"El filtro tiene demasiadas condiciones (el máximo son "
                f"{MAX_CONDICIONES}).", self.actual().pos)

        t = self.comer()
        if t.tipo != "IDENT":
            raise ErrorDeConsulta(
                f"Esperaba el nombre de un campo y encontré «{t.valor}».", t.pos)
        campo, pos = t.valor, t.pos

        operador = self.operador()

        if operador in ("ES VACIO", "NO ES VACIO"):
            return Comparacion(campo, operador, None, pos)

        return Comparacion(campo, operador, self.valor(operador), pos)

    def operador(self) -> str:
        t = self.actual()

        if t.tipo == "SIMBOLO" and t.valor in OPERADORES_SIMBOLO:
            self.comer()
            return t.valor

        if t.tipo != "PALABRA":
            raise ErrorDeConsulta(
                f"«{t.valor}» no es un operador. Los que hay son: =, !=, >, >=, "
                f"<, <=, EN, NO EN, CONTIENE, NO CONTIENE, EMPIEZA, TERMINA, "
                f"ES VACÍO y NO ES VACÍO.", t.pos)

        if t.valor == "NO":
            self.comer()
            siguiente = self.comer()
            if siguiente.tipo != "PALABRA":
                raise ErrorDeConsulta(
                    f"Después de NO esperaba EN, CONTIENE o ES VACÍO.", siguiente.pos)
            if siguiente.valor == "EN":
                return "NO EN"
            if siguiente.valor == "CONTIENE":
                return "NO CONTIENE"
            if siguiente.valor == "ES":
                vacio = self.comer()
                if vacio.tipo == "PALABRA" and vacio.valor in ("VACIO", "VACÍO"):
                    return "NO ES VACIO"
                raise ErrorDeConsulta("Esperaba VACÍO después de NO ES.", vacio.pos)
            raise ErrorDeConsulta(
                f"«NO {siguiente.valor}» no es un operador.", siguiente.pos)

        if t.valor == "ES":
            self.comer()
            vacio = self.comer()
            if vacio.tipo == "PALABRA" and vacio.valor in ("VACIO", "VACÍO"):
                return "ES VACIO"
            raise ErrorDeConsulta("Esperaba VACÍO después de ES.", vacio.pos)

        if t.valor in ("EN", "CONTIENE", "EMPIEZA", "TERMINA"):
            self.comer()
            # «EMPIEZA CON» y «TERMINA CON» se leen mejor; el CON es opcional.
            if t.valor in ("EMPIEZA", "TERMINA") and self.es_palabra("CON"):
                self.comer()
            return t.valor

        raise ErrorDeConsulta(f"«{t.valor}» no es un operador.", t.pos)

    def valor(self, operador: str) -> Any:
        if operador in ("EN", "NO EN"):
            self.exigir_simbolo("(")
            elementos = [self.literal()]
            while self.es_simbolo(","):
                self.comer()
                elementos.append(self.literal())
                if len(elementos) > MAX_EN:
                    raise ErrorDeConsulta(
                        f"La lista tiene demasiados elementos (el máximo son "
                        f"{MAX_EN}).", self.actual().pos)
            self.exigir_simbolo(")")
            return elementos
        return self.literal()

    def literal(self) -> Any:
        t = self.comer()

        if t.tipo in ("TEXTO", "NUMERO"):
            return t.valor

        if t.tipo == "IDENT":
            # ¿Es una llamada a función?
            if self.es_simbolo("("):
                self.comer()
                argumentos = []
                if not self.es_simbolo(")"):
                    argumentos.append(self.literal())
                    while self.es_simbolo(","):
                        self.comer()
                        argumentos.append(self.literal())
                self.exigir_simbolo(")")
                return Llamada(t.valor, argumentos, t.pos)
            # Una palabra suelta vale como texto: obligar a comillas para
            # escribir `estado = Hecho` es fricción sin ninguna ganancia.
            return t.valor

        raise ErrorDeConsulta(f"Esperaba un valor y encontré «{t.valor}».", t.pos)

    def ordenar(self) -> Orden:
        self.comer()   # ORDENAR
        if not self.es_palabra("POR"):
            raise ErrorDeConsulta("Esperaba POR después de ORDENAR.",
                                  self.actual().pos)
        self.comer()
        t = self.comer()
        if t.tipo != "IDENT":
            raise ErrorDeConsulta(
                f"Esperaba el nombre de un campo y encontré «{t.valor}».", t.pos)
        ascendente = False
        if self.es_palabra("ASC"):
            self.comer()
            ascendente = True
        elif self.es_palabra("DESC"):
            self.comer()
        return Orden(t.valor, ascendente, t.pos)


# ─── Funciones del lenguaje ───────────────────────────────────────────────────
#
# Se resuelven a un valor en Python y de ahí entran como parámetro. Nada de esto
# llega al SQL como texto.

UNIDADES = {
    "dia": 1, "dias": 1, "día": 1, "días": 1,
    "semana": 7, "semanas": 7,
    "mes": 30, "meses": 30,
    "ano": 365, "anos": 365, "año": 365, "años": 365,
}


def resolver_llamada(llamada: Llamada, usuario: str) -> Any:
    nombre = llamada.nombre.lower()
    ahora = datetime.now(timezone.utc)

    if nombre == "yo":
        return usuario
    if nombre == "ahora":
        return ahora
    if nombre == "hoy":
        return datetime.combine(ahora.date(), datetime.min.time(), timezone.utc)
    if nombre == "iniciodesemana":
        inicio = ahora.date() - timedelta(days=ahora.weekday())
        return datetime.combine(inicio, datetime.min.time(), timezone.utc)
    if nombre == "iniciodemes":
        return datetime.combine(ahora.date().replace(day=1),
                                datetime.min.time(), timezone.utc)
    if nombre == "hace":
        if len(llamada.argumentos) != 2:
            raise ErrorDeConsulta(
                "hace() lleva dos argumentos: cuántos y de qué. "
                "Por ejemplo hace(7, dias).", llamada.pos)
        cuantos, unidad = llamada.argumentos
        if not isinstance(cuantos, (int, float)):
            raise ErrorDeConsulta("El primer argumento de hace() es un número.",
                                  llamada.pos)
        dias = UNIDADES.get(str(unidad).lower())
        if dias is None:
            raise ErrorDeConsulta(
                f"«{unidad}» no es una unidad de tiempo. Use días, semanas, "
                f"meses o años.", llamada.pos)
        return ahora - timedelta(days=float(cuantos) * dias)

    raise ErrorDeConsulta(
        f"«{llamada.nombre}()» no es una función. Las que hay son: yo(), hoy(), "
        f"ahora(), hace(n, dias), inicioDeSemana(), inicioDeMes().", llamada.pos)


# ─── El registro de campos ────────────────────────────────────────────────────

class Referencia:
    """Un campo que apunta a otra tabla y se resuelve por subconsulta.

    Subconsulta y no unión: una unión por cada campo del filtro es justo lo que
    hace lenta una consulta de cinco condiciones, y además cambiaría la cardinalidad
    del resultado si alguna relación no fuera uno a uno.
    """

    def __init__(self, columna, modelo, buscar_por: Sequence, mostrar):
        self.columna = columna
        self.modelo = modelo
        self.buscar_por = buscar_por
        self.mostrar = mostrar


class Campo:
    def __init__(self, clave: str, etiqueta: str, tipo: str, *,
                 columna=None, referencia: Optional[Referencia] = None,
                 personalizado: Optional[str] = None, ordenable: bool = True,
                 especial: Optional[str] = None):
        self.clave = clave
        self.etiqueta = etiqueta
        self.tipo = tipo
        self.columna = columna
        self.referencia = referencia
        self.personalizado = personalizado   # la clave dentro del jsonb
        self.ordenable = ordenable
        self.especial = especial


# Qué operadores admite cada tipo. Se comprueba en la validación: `puntos
# CONTIENE "3"` es un error de quien escribe, no algo que haya que interpretar.
OPERADORES = {
    "TEXTO":          {"=", "!=", "CONTIENE", "NO CONTIENE", "EMPIEZA", "TERMINA",
                       "EN", "NO EN", "ES VACIO", "NO ES VACIO"},
    "TEXTO_LARGO":    {"=", "!=", "CONTIENE", "NO CONTIENE", "EMPIEZA", "TERMINA",
                       "ES VACIO", "NO ES VACIO"},
    "NUMERO":         {"=", "!=", ">", ">=", "<", "<=", "EN", "NO EN",
                       "ES VACIO", "NO ES VACIO"},
    "DECIMAL":        {"=", "!=", ">", ">=", "<", "<=", "EN", "NO EN",
                       "ES VACIO", "NO ES VACIO"},
    "FECHA":          {"=", "!=", ">", ">=", "<", "<=", "ES VACIO", "NO ES VACIO"},
    "FECHA_HORA":     {"=", "!=", ">", ">=", "<", "<=", "ES VACIO", "NO ES VACIO"},
    "BOOLEANO":       {"=", "!="},
    "LISTA":          {"=", "!=", "EN", "NO EN", "ES VACIO", "NO ES VACIO"},
    "LISTA_MULTIPLE": {"CONTIENE", "NO CONTIENE", "ES VACIO", "NO ES VACIO"},
    "USUARIO":        {"=", "!=", "EN", "NO EN", "ES VACIO", "NO ES VACIO"},
    "URL":            {"=", "!=", "CONTIENE", "NO CONTIENE", "ES VACIO", "NO ES VACIO"},
    "ETIQUETAS":      {"CONTIENE", "NO CONTIENE", "ES VACIO", "NO ES VACIO"},
    "REFERENCIA":     {"=", "!=", "EN", "NO EN", "ES VACIO", "NO ES VACIO"},
    "BUSQUEDA":       {"CONTIENE", "="},
}


def _campos_nativos() -> Dict[str, Campo]:
    return {c.clave: c for c in [
        Campo("clave", "Clave", "NUMERO", columna=GPIncidencia.numero),
        Campo("numero", "Número", "NUMERO", columna=GPIncidencia.numero),
        Campo("resumen", "Título", "TEXTO", columna=GPIncidencia.resumen),
        Campo("descripcion", "Descripción", "TEXTO_LARGO",
              columna=GPIncidencia.descripcion, ordenable=False),
        # Busca por el índice de texto completo, sobre título y descripción.
        Campo("texto", "Texto", "BUSQUEDA", especial="busqueda", ordenable=False),
        Campo("asignado", "Responsable", "USUARIO", columna=GPIncidencia.asignado),
        Campo("reporta", "Reportó", "USUARIO", columna=GPIncidencia.reporta),
        Campo("puntos", "Puntos", "NUMERO", columna=GPIncidencia.puntos),
        Campo("etiquetas", "Etiquetas", "ETIQUETAS",
              columna=GPIncidencia.etiquetas, ordenable=False),
        Campo("padre", "Padre", "NUMERO", columna=GPIncidencia.padre_id),
        Campo("ticket", "Solicitud de soporte", "NUMERO",
              columna=GPIncidencia.ticket_id),
        Campo("creado", "Creación", "FECHA_HORA", columna=GPIncidencia.created_at),
        Campo("actualizado", "Última actualización", "FECHA_HORA",
              columna=GPIncidencia.actualizado),
        Campo("vence", "Vencimiento", "FECHA_HORA", columna=GPIncidencia.vence),
        Campo("iniciado", "Inicio", "FECHA_HORA", columna=GPIncidencia.iniciado),
        Campo("resuelto", "Resolución", "FECHA_HORA", columna=GPIncidencia.resuelto),

        Campo("proyecto", "Proyecto", "REFERENCIA", referencia=Referencia(
            GPIncidencia.proyecto_id, GPProyecto,
            (GPProyecto.clave, GPProyecto.nombre), GPProyecto.nombre)),
        Campo("tipo", "Tipo", "REFERENCIA", referencia=Referencia(
            GPIncidencia.tipo_id, GPTipoIncidencia,
            (GPTipoIncidencia.clave, GPTipoIncidencia.nombre),
            GPTipoIncidencia.nombre)),
        Campo("estado", "Estado", "REFERENCIA", referencia=Referencia(
            GPIncidencia.estado_id, GPEstado,
            (GPEstado.clave, GPEstado.nombre), GPEstado.nombre)),
        Campo("categoria", "Categoría del estado", "REFERENCIA",
              referencia=Referencia(
                  GPIncidencia.estado_id, GPEstado,
                  (GPEstado.categoria,), GPEstado.categoria)),
        Campo("prioridad", "Prioridad", "REFERENCIA", referencia=Referencia(
            GPIncidencia.prioridad_id, GPPrioridad,
            (GPPrioridad.clave, GPPrioridad.nombre), GPPrioridad.nombre)),
        Campo("sprint", "Sprint", "REFERENCIA", referencia=Referencia(
            GPIncidencia.sprint_id, GPSprint,
            (GPSprint.nombre,), GPSprint.nombre)),
    ]}


async def registro(db: AsyncSession) -> Dict[str, Campo]:
    """Los campos que se pueden nombrar en un filtro.

    Los nativos son fijos; los configurables entran solo si están marcados como
    filtrables, que es lo mismo que decide si el servidor les creó su índice. Un
    campo filtrable sin índice convierte cada consulta en un recorrido completo.
    """
    campos = _campos_nativos()

    r = await db.execute(select(GPCampo).where(
        GPCampo.filtrable.is_(True), GPCampo.archivado.is_(False)))
    for c in r.scalars().all():
        if c.clave in campos:
            # Un campo configurable no puede tapar a uno nativo: `estado` tiene
            # que seguir significando el estado del flujo.
            continue
        campos[c.clave] = Campo(c.clave, c.nombre, c.tipo,
                                personalizado=c.clave, ordenable=c.ordenable)
    return campos


# ─── Construcción ─────────────────────────────────────────────────────────────

def _expresion_personalizada(campo: Campo):
    """La expresión que saca el valor de un campo configurable del jsonb.

    Se castea según el tipo declarado y se protege con `jsonb_typeof`: un valor
    viejo de otro tipo haría fallar el cast y tumbaría la consulta entera en vez
    de simplemente no coincidir.
    """
    crudo = GPIncidencia.campos[campo.personalizado].astext

    if campo.tipo in ("NUMERO", "DECIMAL"):
        return cast(crudo, Numeric), func.jsonb_typeof(
            GPIncidencia.campos[campo.personalizado]) == "number"
    if campo.tipo in ("FECHA", "FECHA_HORA"):
        return cast(crudo, TIMESTAMP(timezone=True)), func.jsonb_typeof(
            GPIncidencia.campos[campo.personalizado]) == "string"
    if campo.tipo == "BOOLEANO":
        return crudo, None
    return crudo, None


def _como(texto: str) -> str:
    """Escapa los comodines de LIKE.

    Sin esto, buscar «100%» devuelve todo lo que empiece por 100, y quien busca
    concluye que la herramienta no funciona.
    """
    return texto.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _comparar(izquierda, operador: str, valor):
    if operador == "=":
        return izquierda == valor
    if operador == "!=":
        # `!=` tiene que traer también las que no tienen valor: quien filtra
        # «estado != Hecho» espera ver las que aún no tienen estado, no perderlas.
        return or_(izquierda != valor, izquierda.is_(None))
    if operador == ">":
        return izquierda > valor
    if operador == ">=":
        return izquierda >= valor
    if operador == "<":
        return izquierda < valor
    if operador == "<=":
        return izquierda <= valor
    raise ErrorDeConsulta(f"Operador no soportado: {operador}.")


def _construir_comparacion(c: Comparacion, campos: Dict[str, Campo], usuario: str):
    campo = campos.get(c.campo)
    if campo is None:
        parecidos = [k for k in campos if k.startswith(c.campo[:3].lower())][:4]
        pista = f" ¿Quiso decir {', '.join(parecidos)}?" if parecidos else ""
        raise ErrorDeConsulta(
            f"«{c.campo}» no es un campo que se pueda filtrar.{pista}", c.pos)

    permitidos = OPERADORES.get(campo.tipo, set())
    if c.operador not in permitidos:
        raise ErrorDeConsulta(
            f"«{c.operador}» no aplica a {campo.etiqueta}. Ahí puede usar: "
            f"{', '.join(sorted(permitidos))}.", c.pos)

    # Las funciones se resuelven a un valor y de ahí entran como parámetro.
    valor = c.valor
    if isinstance(valor, Llamada):
        valor = resolver_llamada(valor, usuario)
    elif isinstance(valor, list):
        valor = [resolver_llamada(v, usuario) if isinstance(v, Llamada) else v
                 for v in valor]

    # ── búsqueda de texto completo ──
    if campo.especial == "busqueda":
        return GPIncidencia.busqueda.op("@@")(
            func.plainto_tsquery("spanish", str(valor)))

    # ── referencias a otra tabla ──
    if campo.referencia is not None:
        ref = campo.referencia
        if c.operador == "ES VACIO":
            return ref.columna.is_(None)
        if c.operador == "NO ES VACIO":
            return ref.columna.isnot(None)

        buscados = valor if isinstance(valor, list) else [valor]
        textos = [str(v).strip().upper() for v in buscados]
        coincide = or_(*[func.upper(col).in_(textos) for col in ref.buscar_por])
        dentro = ref.columna.in_(select(ref.modelo.id).where(coincide))

        if c.operador in ("=", "EN"):
            return dentro
        # Negado: también las que no apuntan a nada.
        return or_(not_(dentro), ref.columna.is_(None))

    # ── columna directa o campo configurable ──
    if campo.personalizado:
        izquierda, guarda = _expresion_personalizada(campo)
        existe = GPIncidencia.campos.has_key(campo.personalizado)
    else:
        izquierda, guarda = campo.columna, None
        existe = campo.columna.isnot(None)

    if c.operador == "ES VACIO":
        return not_(existe)
    if c.operador == "NO ES VACIO":
        return existe

    if campo.tipo in ("ETIQUETAS", "LISTA_MULTIPLE"):
        columna = (GPIncidencia.campos[campo.personalizado]
                   if campo.personalizado else GPIncidencia.etiquetas)
        contiene = columna.op("@>")(func.to_jsonb(cast([str(valor)], JSONB)))
        return contiene if c.operador == "CONTIENE" else not_(contiene)

    if c.operador in ("CONTIENE", "NO CONTIENE", "EMPIEZA", "TERMINA"):
        aguja = _como(str(valor))
        patron = {"CONTIENE": f"%{aguja}%", "NO CONTIENE": f"%{aguja}%",
                  "EMPIEZA": f"{aguja}%", "TERMINA": f"%{aguja}"}[c.operador]
        parecido = izquierda.ilike(patron, escape="\\")
        condicion = parecido if c.operador != "NO CONTIENE" else or_(
            not_(parecido), izquierda.is_(None))
        return and_(guarda, condicion) if guarda is not None else condicion

    if c.operador in ("EN", "NO EN"):
        lista = [_convertir(v, campo, c.pos) for v in valor]
        dentro = izquierda.in_(lista)
        condicion = dentro if c.operador == "EN" else or_(
            not_(dentro), izquierda.is_(None))
        return and_(guarda, condicion) if guarda is not None else condicion

    condicion = _comparar(izquierda, c.operador, _convertir(valor, campo, c.pos))
    return and_(guarda, condicion) if guarda is not None else condicion


def _convertir(valor: Any, campo: Campo, pos: int):
    """Lleva el literal al tipo del campo, o dice por qué no se puede."""
    if isinstance(valor, datetime):
        return valor

    if campo.tipo in ("NUMERO", "DECIMAL"):
        if isinstance(valor, (int, float)):
            return valor
        try:
            texto = str(valor).strip().replace(",", ".")
            return float(texto) if "." in texto else int(texto)
        except ValueError:
            raise ErrorDeConsulta(
                f"{campo.etiqueta} es numérico y «{valor}» no es un número.", pos)

    if campo.tipo in ("FECHA", "FECHA_HORA"):
        texto = str(valor).strip().replace("Z", "+00:00")
        try:
            momento = datetime.fromisoformat(texto)
        except ValueError:
            try:
                momento = datetime.combine(date.fromisoformat(texto[:10]),
                                           datetime.min.time())
            except ValueError:
                raise ErrorDeConsulta(
                    f"{campo.etiqueta} es una fecha y «{valor}» no lo es. Use "
                    f"AAAA-MM-DD o una función como hace(7, dias).", pos)
        return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)

    if campo.tipo == "BOOLEANO":
        s = str(valor).strip().lower()
        if s in ("true", "si", "sí", "1"):
            return "true"
        if s in ("false", "no", "0"):
            return "false"
        raise ErrorDeConsulta(f"{campo.etiqueta} es sí o no, y «{valor}» no lo es.", pos)

    return str(valor)


def construir(nodo: Optional[Nodo], campos: Dict[str, Campo], usuario: str):
    """Del árbol validado a una condición de SQLAlchemy."""
    if nodo is None:
        return None
    if isinstance(nodo, Y):
        return and_(*[construir(p, campos, usuario) for p in nodo.partes])
    if isinstance(nodo, O):
        return or_(*[construir(p, campos, usuario) for p in nodo.partes])
    if isinstance(nodo, No):
        return not_(construir(nodo.parte, campos, usuario))
    if isinstance(nodo, Comparacion):
        return _construir_comparacion(nodo, campos, usuario)
    raise ErrorDeConsulta("El filtro tiene una forma que no entiendo.")


def expresion_de_orden(orden: Optional[Orden], campos: Dict[str, Campo]):
    """La columna por la que ordenar, comprobando que se pueda."""
    if orden is None:
        return None, GPIncidencia.actualizado, False

    campo = campos.get(orden.campo)
    if campo is None:
        raise ErrorDeConsulta(
            f"No se puede ordenar por «{orden.campo}»: no es un campo conocido.",
            orden.pos)
    if not campo.ordenable:
        raise ErrorDeConsulta(
            f"{campo.etiqueta} no se puede usar para ordenar.", orden.pos)

    if campo.referencia is not None:
        # Por el id de la referencia: para prioridad y estado eso respeta el
        # orden configurado, que es lo que la gente espera, y no el alfabético.
        return campo, campo.referencia.columna, orden.ascendente
    if campo.personalizado:
        izquierda, _ = _expresion_personalizada(campo)
        return campo, izquierda, orden.ascendente
    return campo, campo.columna, orden.ascendente


class Consulta:
    """Un filtro ya analizado, validado y traducido.

    Se devuelve todo junto —y no solo la condición— para que sea imposible
    ejecutar la parte del filtro sin haber validado la del orden. Cuando eran dos
    pasos, guardar un filtro validaba sus condiciones pero no su «ORDENAR POR»:
    el filtro se guardaba, se compartía, y reventaba después en la cara de otra
    persona, que no sabía qué había escrito quien lo creó.
    """

    __slots__ = ("condicion", "orden", "campo_orden", "expresion_orden", "ascendente")

    def __init__(self, condicion, orden, campo_orden, expresion_orden, ascendente):
        self.condicion = condicion
        self.orden = orden
        self.campo_orden = campo_orden
        self.expresion_orden = expresion_orden
        self.ascendente = ascendente


def compilar(texto: str, campos: Dict[str, Campo], usuario: str) -> Consulta:
    """El camino completo, de una vez. Es la única puerta de entrada."""
    raiz, orden = Analizador(analizar_lexico(texto or "")).analizar()
    condicion = construir(raiz, campos, usuario)
    campo_orden, expresion_orden, ascendente = expresion_de_orden(orden, campos)
    return Consulta(condicion, orden, campo_orden, expresion_orden, ascendente)


def catalogo(campos: Dict[str, Campo]) -> List[dict]:
    """Lo que el constructor visual puede ofrecer.

    Sale del mismo registro que valida: si la pantalla tuviera su propia lista,
    acabaría ofreciendo un campo que el servidor rechaza, y quien lo use
    concluiría que el filtro está roto.
    """
    return [
        {"clave": c.clave, "etiqueta": c.etiqueta, "tipo": c.tipo,
         "ordenable": c.ordenable, "personalizado": bool(c.personalizado),
         "operadores": sorted(OPERADORES.get(c.tipo, set()))}
        for c in sorted(campos.values(), key=lambda x: x.etiqueta)
    ]


FUNCIONES = [
    {"nombre": "yo()", "descripcion": "Quien está consultando"},
    {"nombre": "hoy()", "descripcion": "Hoy a las 00:00"},
    {"nombre": "ahora()", "descripcion": "Este instante"},
    {"nombre": "hace(7, dias)", "descripcion": "Hace tantos días, semanas, meses o años"},
    {"nombre": "inicioDeSemana()", "descripcion": "El lunes de esta semana"},
    {"nombre": "inicioDeMes()", "descripcion": "El día 1 de este mes"},
]
