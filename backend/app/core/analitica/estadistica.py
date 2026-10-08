"""
Control estadístico de procesos y comparación de grupos.

CARTAS DE CONTROL
Una carta no dice si el proceso es bueno: dice si cambió. Los límites salen
del propio proceso, no de una meta, y un punto fuera de ellos significa «aquí
pasó algo que no es la variación de siempre», que es lo que vale la pena
investigar.

  I-MR     una medida por punto (el OEE de un turno). Límites con el rango
           móvil medio: x̄ ± 2,66·MR̄.
  p' Laney proporción con tamaños distintos (desperdicio por corrida). La
           carta p clásica asume que las unidades son independientes; con
           miles de unidades por corrida los límites quedan tan estrechos que
           TODO sale fuera de control. Laney corrige por la variación real
           entre corridas (sobredispersión), y con datos binomiales de verdad
           da lo mismo que la p clásica.

Los límites se calculan con un periodo base —los primeros puntos— y los
siguientes se juzgan contra él. Si se calcularan con todos, un cambio
sostenido movería los límites y se escondería a sí mismo.

REGLAS DE NELSON que se aplican (las más usadas y con menos falsas alarmas)
  1  un punto más allá de 3σ
  2  nueve seguidos del mismo lado de la media
  3  seis seguidos subiendo o bajando
  5  dos de tres más allá de 2σ del mismo lado

COMPARAR GRUPOS
Para preguntar «¿este operario desperdicia más?» la unidad es la CORRIDA, no
la pieza: las piezas de una misma corrida comparten material, máquina y
ajuste, y contarlas como independientes haría significativa cualquier
diferencia. Se usa Mann-Whitney (no supone normalidad) y Benjamini-Hochberg
para corregir por hacer muchas comparaciones a la vez.
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

MIN_PUNTOS_CARTA = 12
MIN_CORRIDAS_GRUPO = 8


def _base(n: int) -> int:
    """Cuántos puntos forman el periodo base: la mitad, entre 12 y 30."""
    return int(min(30, max(MIN_PUNTOS_CARTA, n // 2)))


def reglas_nelson(z: Sequence[float]) -> Dict[int, List[str]]:
    """Qué reglas rompe cada punto, con `z` en unidades de sigma respecto a la
    línea central (puede ser un sigma distinto por punto)."""
    alertas: Dict[int, List[str]] = {}
    marca = lambda i, t: alertas.setdefault(i, []).append(t)
    n = len(z)
    for i, v in enumerate(z):
        if abs(v) > 3:
            marca(i, "Fuera de los límites de control")
    for i in range(8, n):
        ventana = z[i - 8:i + 1]
        if all(v > 0 for v in ventana) or all(v < 0 for v in ventana):
            marca(i, "Nueve seguidos del mismo lado: el nivel cambió")
    for i in range(5, n):
        d = np.diff(z[i - 5:i + 1])
        if all(d > 0) or all(d < 0):
            marca(i, "Seis seguidos en la misma dirección: hay una tendencia")
    for i in range(2, n):
        ventana = z[i - 2:i + 1]
        if sum(v > 2 for v in ventana) >= 2 or sum(v < -2 for v in ventana) >= 2:
            marca(i, "Dos de tres cerca del límite")
    return alertas


def carta_imr(valores: Sequence[float], etiquetas: Sequence[str]) -> Dict:
    x = np.asarray(valores, dtype=float)
    n = len(x)
    if n < MIN_PUNTOS_CARTA:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_CARTA}
    b = _base(n)
    centro = float(x[:b].mean())
    mr = float(np.abs(np.diff(x[:b])).mean())
    sigma = mr / 1.128
    if sigma <= 0:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_CARTA, "motivo": "Sin variación"}
    z = (x - centro) / sigma
    alertas = reglas_nelson(z)
    return {
        "suficiente": True, "tipo": "I-MR", "puntos_base": b,
        "centro": round(centro, 3), "lcs": round(centro + 3 * sigma, 3), "lci": round(centro - 3 * sigma, 3),
        "serie": [{"etiqueta": e, "valor": round(float(v), 3), "alertas": alertas.get(i, [])}
                  for i, (e, v) in enumerate(zip(etiquetas, x))],
    }


def carta_p_laney(defectuosos: Sequence[float], tamanos: Sequence[float], etiquetas: Sequence[str]) -> Dict:
    d = np.asarray(defectuosos, dtype=float)
    m = np.asarray(tamanos, dtype=float)
    ok = m > 0
    d, m = d[ok], m[ok]
    etiquetas = [e for e, k in zip(etiquetas, ok) if k]
    n = len(d)
    if n < MIN_PUNTOS_CARTA:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_CARTA}
    b = _base(n)
    pbar = float(d[:b].sum() / m[:b].sum())
    if pbar <= 0 or pbar >= 1:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_CARTA, "motivo": "Sin variación"}
    p = d / m
    sp = np.sqrt(pbar * (1 - pbar) / m)
    zb = (p[:b] - pbar) / sp[:b]
    sigma_z = float(np.abs(np.diff(zb)).mean() / 1.128) or 1.0
    s = sp * sigma_z
    z = (p - pbar) / s
    alertas = reglas_nelson(z)
    return {
        "suficiente": True, "tipo": "p' de Laney", "puntos_base": b,
        "centro": round(pbar * 100, 3), "sobredispersion": round(sigma_z, 2),
        "serie": [{"etiqueta": e, "valor": round(float(pi) * 100, 3),
                   "lcs": round(min(1.0, pbar + 3 * float(si)) * 100, 3),
                   "lci": round(max(0.0, pbar - 3 * float(si)) * 100, 3),
                   "tamano": float(mi), "alertas": alertas.get(i, [])}
                  for i, (e, pi, si, mi) in enumerate(zip(etiquetas, p, s, m))],
    }


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float]:
    """Prueba U con aproximación normal y corrección por empates. Devuelve
    (p bilateral, probabilidad de que un valor de `a` supere a uno de `b`)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    n1, n2 = len(a), len(b)
    todos = np.concatenate([a, b])
    orden = todos.argsort(kind="mergesort")
    rangos = np.empty(len(todos))
    vals = todos[orden]
    i = 0
    empates = 0.0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        rangos[orden[i:j + 1]] = (i + j) / 2 + 1
        t = j - i + 1
        empates += t ** 3 - t
        i = j + 1
    u1 = rangos[:n1].sum() - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    N = n1 + n2
    var = n1 * n2 / 12 * ((N + 1) - empates / (N * (N - 1)))
    if var <= 0:
        return 1.0, 0.5
    z = (u1 - mu - math.copysign(0.5, u1 - mu)) / math.sqrt(var)
    return math.erfc(abs(z) / math.sqrt(2)), float(u1 / (n1 * n2))


def benjamini_hochberg(pvalores: Sequence[float]) -> List[float]:
    """p-valores ajustados por tasa de falsos descubrimientos."""
    p = np.asarray(pvalores, float)
    n = len(p)
    if not n:
        return []
    orden = np.argsort(p)
    ajust = np.empty(n)
    acumulado = 1.0
    for k in range(n - 1, -1, -1):
        i = orden[k]
        acumulado = min(acumulado, p[i] * n / (k + 1))
        ajust[i] = acumulado
    return [float(x) for x in ajust]


def comparar_grupos(corridas: List[Dict], factores: Dict[str, str], valor: str = "tasa",
                    alfa: float = 0.05) -> List[Dict]:
    """Cada nivel de cada factor contra el resto de las corridas.

    `corridas` son diccionarios con los factores y el valor; `factores` mapea
    la clave del factor a su nombre en pantalla. Solo se prueban niveles con
    al menos 8 corridas propias y 8 del resto.
    """
    def probar(excluir):
        salida = []
        for clave, nombre in factores.items():
            niveles = {c.get(clave) for c in corridas if c.get(clave) is not None}
            if len(niveles) < 2:
                continue
            for nivel in niveles:
                fuera = excluir.get(clave, set()) - {nivel}
                a = [c[valor] for c in corridas if c.get(clave) == nivel]
                b = [c[valor] for c in corridas
                     if c.get(clave) is not None and c.get(clave) != nivel and c.get(clave) not in fuera]
                if len(a) < MIN_CORRIDAS_GRUPO or len(b) < MIN_CORRIDAS_GRUPO:
                    continue
                p, prob_mayor = mann_whitney(a, b)
                salida.append({"factor": nombre, "clave": clave, "nivel": nivel, "corridas": len(a),
                               "corridas_resto": len(b),
                               "mediana": round(float(np.median(a)), 3), "mediana_resto": round(float(np.median(b)), 3),
                               "media": round(float(np.mean(a)), 3), "media_resto": round(float(np.mean(b)), 3),
                               "prob_mayor": round(prob_mayor, 3), "p": p})
        return salida

    # Efecto espejo: si un operario desperdicia mucho, «el resto» de cada uno
    # de los demás lo incluye y todos parecen mejores de lo normal. Primero se
    # encuentran los peores; después se vuelve a comparar a los demás contra
    # el resto SIN ellos.
    primera = probar({})
    ajust = benjamini_hochberg([x["p"] for x in primera])
    peores: Dict[str, set] = {}
    for x, pa in zip(primera, ajust):
        if pa < alfa and x["media"] > x["media_resto"]:
            peores.setdefault(x["clave"], set()).add(x["nivel"])
    pruebas = probar(peores) if peores else primera
    for x in pruebas:
        x.pop("clave", None)
    for prueba, pa in zip(pruebas, benjamini_hochberg([x["p"] for x in pruebas])):
        prueba["p_ajustado"] = round(pa, 4)
        prueba["p"] = round(prueba["p"], 4)
        prueba["significativo"] = pa < alfa
    return sorted(pruebas, key=lambda x: (not x["significativo"], x["p_ajustado"]))


# ─── Tendencias y conteos ─────────────────────────────────────────────────────

MIN_PUNTOS_TENDENCIA = 8


def carta_c(conteos: Sequence[float], etiquetas: Sequence[str]) -> Dict:
    """Carta c para conteos por periodo (NC por mes): c̄ ± 3√c̄."""
    x = np.asarray(conteos, dtype=float)
    n = len(x)
    if n < MIN_PUNTOS_CARTA:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_CARTA}
    b = _base(n)
    c = float(x[:b].mean())
    if c <= 0:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_CARTA, "motivo": "Sin eventos en el periodo base"}
    s = math.sqrt(c)
    alertas = reglas_nelson((x - c) / s)
    return {"suficiente": True, "tipo": "c", "puntos_base": b, "centro": round(c, 2),
            "lcs": round(c + 3 * s, 2), "lci": round(max(0.0, c - 3 * s), 2),
            "serie": [{"etiqueta": e, "valor": float(v), "alertas": alertas.get(i, [])}
                      for i, (e, v) in enumerate(zip(etiquetas, x))]}


def mann_kendall(valores: Sequence[float]) -> Dict:
    """Prueba de tendencia de Mann-Kendall con pendiente de Sen.

    No supone normalidad ni linealidad: pregunta si los valores tienden a
    subir (o bajar) con el tiempo más de lo que el azar explica. La pendiente
    de Sen es la mediana de todas las pendientes entre pares, así que un mes
    atípico no la arrastra.
    """
    x = np.asarray(valores, dtype=float)
    n = len(x)
    if n < MIN_PUNTOS_TENDENCIA:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_TENDENCIA}
    s = 0
    pendientes: List[float] = []
    for i in range(n - 1):
        d = x[i + 1:] - x[i]
        s += int(np.sign(d).sum())
        pendientes.extend(d / np.arange(1, n - i))
    _, cuentas = np.unique(x, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(int(t) * (int(t) - 1) * (2 * int(t) + 5) for t in cuentas)) / 18
    if var <= 0:
        return {"suficiente": False, "puntos": n, "minimo": MIN_PUNTOS_TENDENCIA, "motivo": "Sin variación"}
    z = (s - np.sign(s)) / math.sqrt(var) if s else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    sen = float(np.median(pendientes))
    return {"suficiente": True, "puntos": n, "p": round(p, 4), "pendiente": round(sen, 4),
            "tendencia": ("SUBE" if s > 0 else "BAJA") if p < 0.10 else "ESTABLE"}


# Cuantiles t de Student al 95 % (intervalo del 90 %) para pocos grados de libertad.
_T95 = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833,
        10: 1.812, 12: 1.782, 15: 1.753, 20: 1.725, 25: 1.708, 30: 1.697}


def _t95(gl: int) -> float:
    if gl >= 30:
        return 1.645 + 1.6 / gl
    return _T95[max(k for k in _T95 if k <= gl)]


def regresion_lineal(x: Sequence[float], y: Sequence[float]) -> Dict:
    """Pendiente por mínimos cuadrados con su intervalo del 90 %."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 6:
        return {"suficiente": False, "puntos": n, "minimo": 6}
    xm, ym = x.mean(), y.mean()
    sxx = float(((x - xm) ** 2).sum())
    if sxx == 0:
        return {"suficiente": False, "puntos": n, "minimo": 6}
    b = float(((x - xm) * (y - ym)).sum() / sxx)
    a = float(ym - b * xm)
    res = y - (a + b * x)
    se = math.sqrt(float((res ** 2).sum()) / (n - 2) / sxx)
    t = _t95(n - 2)
    return {"suficiente": True, "puntos": n, "pendiente": round(b, 4), "intercepto": round(a, 4),
            "ic90": [round(b - t * se, 4), round(b + t * se, 4)],
            "significativa": (b - t * se) > 0 or (b + t * se) < 0}


# ─── Tiempo hasta un evento ───────────────────────────────────────────────────

MIN_EVENTOS_KM = 5


def kaplan_meier(tiempos: Sequence[float], ocurrio: Sequence[bool]) -> Dict:
    """Curva de Kaplan-Meier: probabilidad de que el evento NO haya ocurrido
    todavía a cada tiempo, contando los casos abiertos como censurados.

    Para «¿cuánto tarda en cerrarse un incidente?»: promediar solo los
    cerrados deja fuera a los que llevan meses abiertos, y el tiempo sale más
    corto de lo que es, justo en el caso que más preocupa.
    """
    t = np.asarray(tiempos, float)
    e = np.asarray(ocurrio, bool)
    if int(e.sum()) < MIN_EVENTOS_KM:
        return {"suficiente": False, "eventos": int(e.sum()), "abiertos": int((~e).sum()), "minimo": MIN_EVENTOS_KM}
    orden = np.argsort(t)
    t, e = t[orden], e[orden]
    n = len(t)
    s, curva = 1.0, [(0.0, 1.0)]
    i = 0
    while i < n:
        j = i
        while j < n and t[j] == t[i]:
            j += 1
        d = int(e[i:j].sum())
        if d:
            s *= 1 - d / (n - i)
            curva.append((float(t[i]), s))
        i = j
    mediana = next((x for x, v in curva if v <= 0.5), None)
    p90 = next((x for x, v in curva if v <= 0.1), None)
    return {"suficiente": True, "eventos": int(e.sum()), "abiertos": int((~e).sum()),
            "mediana": round(mediana, 1) if mediana is not None else None,
            "p90": round(p90, 1) if p90 is not None else None,
            "curva": [[round(x, 1), round(v, 4)] for x, v in curva]}


def supervivencia_en(curva: List[List[float]], t: float) -> float:
    """S(t) de una curva de Kaplan-Meier (escalonada)."""
    s = 1.0
    for x, v in curva:
        if x <= t:
            s = v
        else:
            break
    return s


def spearman(x: Sequence[float], y: Sequence[float]) -> Dict:
    """Correlación de rangos de Spearman con su p aproximado (t con n−2)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 5:
        return {"suficiente": False, "puntos": n, "minimo": 5}

    def rangos(v):
        orden = v.argsort(kind="mergesort")
        r = np.empty(n)
        vals = v[orden]
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[j + 1] == vals[i]:
                j += 1
            r[orden[i:j + 1]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = rangos(x), rangos(y)
    if rx.std() == 0 or ry.std() == 0:
        return {"suficiente": False, "puntos": n, "minimo": 5, "motivo": "Sin variación"}
    rho = float(np.corrcoef(rx, ry)[0, 1])
    if abs(rho) >= 1:
        return {"suficiente": True, "puntos": n, "rho": round(rho, 3), "p": 0.0}
    tt = rho * math.sqrt((n - 2) / (1 - rho ** 2))
    # Aproximación normal de la t: suficiente para decir «hay o no hay relación».
    p = math.erfc(abs(tt) / math.sqrt(2) * (1 - 1 / (4 * max(n - 2, 1))))
    return {"suficiente": True, "puntos": n, "rho": round(rho, 3), "p": round(p, 4)}
