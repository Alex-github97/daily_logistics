"""
Pronóstico de demanda mensual con selección del método por desempeño fuera
de muestra.

LOS MÉTODOS
  Ingenuo         el mes siguiente es igual al último. No es un buen método:
                  es la vara. Un método que no le gana no aporta nada.
  Promedio móvil  promedio de los últimos 3 meses.
  Suavización     exponencial simple: nivel que se actualiza con cada mes.
  Holt            nivel y tendencia (amortiguada, para no proyectar al
                  infinito una racha).
  Holt-Winters    nivel, tendencia y estacionalidad de 12 meses. Solo con al
                  menos 24 meses: con menos no hay dos ciclos para aprender
                  la estación, y un «patrón» visto una sola vez es azar.
  Croston         para demanda intermitente (muchos meses en cero): pronostica
                  por separado el tamaño del pedido y el intervalo entre
                  pedidos. Los demás métodos, con ceros, dan un promedio que no
                  corresponde a ningún mes real.

CÓMO SE ELIGE
Origen rodante: se ajusta cada método con la historia hasta el mes t y se
pronostica t+1, para los últimos meses disponibles. Gana el de menor error
cuadrático (RMSE) en esos meses que no vio. No el error absoluto: el MAE
premia pronosticar la mediana, y con demanda intermitente la mediana es cero;
para planear inventario hace falta la demanda esperada, que es la media. El error de validación también
da el tamaño del intervalo y del stock de seguridad: se usa el error real del
pronóstico, no la variación de la demanda, que sobrestima el riesgo cuando la
demanda tiene tendencia o estación que el modelo sí captura.
"""
import math
from itertools import product
from statistics import NormalDist
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

MIN_MESES = 6          # por debajo: promedio simple y aviso de pocos datos
MIN_ESTACIONAL = 24

NOMBRES = {
    "INGENUO": "Ingenuo (último mes)", "PROMEDIO_MOVIL": "Promedio móvil 3 meses",
    "SUAVIZACION": "Suavización exponencial", "HOLT": "Holt (tendencia amortiguada)",
    "HOLT_WINTERS": "Holt-Winters (estacional)", "CROSTON": "Croston (intermitente)",
    "PROMEDIO": "Promedio simple (pocos datos)",
}


# ─── Métodos: cada uno devuelve el pronóstico de los próximos h meses ─────────

def _ingenuo(y, h, _p=None):
    return np.full(h, y[-1])


def _promedio_movil(y, h, _p=None):
    return np.full(h, y[-3:].mean())


def _ses(y, h, p):
    a = p[0]
    nivel = y[0]
    for v in y[1:]:
        nivel = a * v + (1 - a) * nivel
    return np.full(h, nivel)


def _holt(y, h, p):
    a, b, phi = p
    nivel, tend = y[0], (y[min(3, len(y) - 1)] - y[0]) / max(min(3, len(y) - 1), 1)
    for v in y[1:]:
        prev = nivel
        nivel = a * v + (1 - a) * (nivel + phi * tend)
        tend = b * (nivel - prev) + (1 - b) * phi * tend
    return np.array([nivel + sum(phi ** k for k in range(1, i + 1)) * tend for i in range(1, h + 1)])


def _holt_winters(y, h, p):
    a, b, g = p
    m = 12
    nivel = y[:m].mean()
    tend = (y[m:2 * m].mean() - y[:m].mean()) / m
    estacion = list(y[:m] - nivel)
    for t in range(m, len(y)):
        s = estacion[t - m]
        prev = nivel
        nivel = a * (y[t] - s) + (1 - a) * (nivel + tend)
        tend = b * (nivel - prev) + (1 - b) * tend
        estacion.append(g * (y[t] - nivel) + (1 - g) * s)
    n = len(y)
    return np.array([nivel + i * tend + estacion[n - m + (i - 1) % m] for i in range(1, h + 1)])


def _croston(y, h, p):
    a = p[0]
    nz = np.nonzero(y)[0]
    if len(nz) == 0:
        return np.zeros(h)
    z, x = y[nz[0]], 1.0
    q = 1
    for t in range(nz[0] + 1, len(y)):
        if y[t] > 0:
            z = a * y[t] + (1 - a) * z
            x = a * q + (1 - a) * x
            q = 1
        else:
            q += 1
    # Corrección de Syntetos-Boylan: el Croston original sobreestima.
    return np.full(h, (1 - a / 2) * z / x)


ALFAS = (0.1, 0.2, 0.3, 0.5, 0.7)
METODOS = {
    "INGENUO": (_ingenuo, [None]),
    "PROMEDIO_MOVIL": (_promedio_movil, [None]),
    "SUAVIZACION": (_ses, [(a,) for a in ALFAS]),
    "HOLT": (_holt, list(product((0.2, 0.4, 0.6), (0.05, 0.15), (0.9, 0.98)))),
    "HOLT_WINTERS": (_holt_winters, list(product((0.1, 0.3, 0.5), (0.02, 0.1), (0.1, 0.3)))),
    "CROSTON": (_croston, [(a,) for a in (0.1, 0.2, 0.3)]),
}


def clasificar_demanda(y: Sequence[float]) -> Dict:
    """Clasificación de Syntetos y Boylan: intervalo medio entre demandas
    (ADI) y variabilidad del tamaño (CV²). Dice qué tan pronosticable es."""
    y = np.asarray(y, float)
    nz = y[y > 0]
    if len(nz) < 2:
        return {"tipo": "SIN_DATOS", "adi": None, "cv2": None}
    adi = len(y) / len(nz)
    cv2 = float((nz.std() / nz.mean()) ** 2) if nz.mean() else 0.0
    tipo = ("SUAVE" if adi < 1.32 and cv2 < 0.49 else "ERRATICA" if adi < 1.32 else
            "INTERMITENTE" if cv2 < 0.49 else "IRREGULAR")
    return {"tipo": tipo, "adi": round(adi, 2), "cv2": round(cv2, 2)}


def _candidatos(y: np.ndarray, intermitente: bool) -> List[str]:
    # Con demanda intermitente, el ingenuo, Holt y Holt-Winters no aplican:
    # una racha de ceros o un pedido suelto no son tendencia ni estación, y en
    # una ventana corta el ingenuo «acierta» los ceros por pura repetición.
    if intermitente:
        return ["PROMEDIO_MOVIL", "SUAVIZACION", "CROSTON"]
    c = ["INGENUO", "PROMEDIO_MOVIL", "SUAVIZACION", "HOLT"]
    if len(y) >= MIN_ESTACIONAL:
        c.append("HOLT_WINTERS")
    return c


# Con demanda intermitente el α se limita a valores bajos: uno alto confunde
# un pedido suelto con un cambio de nivel.
ALFAS_INTERMITENTE = (0.05, 0.1, 0.2, 0.3)


def _mejor_parametro(metodo: str, y: np.ndarray, ventana: int = 6,
                     intermitente: bool = False) -> Optional[tuple]:
    """Parámetro que mejor pronostica un mes adelante dentro de la muestra de
    ajuste. Se busca en una rejilla pequeña: con series mensuales cortas,
    afinar más es ajustar ruido."""
    f, rejilla = METODOS[metodo]
    if rejilla == [None]:
        return None
    if intermitente and metodo in ("SUAVIZACION", "CROSTON"):
        rejilla = [(a,) for a in ALFAS_INTERMITENTE]
    minimo = 13 if metodo == "HOLT_WINTERS" else 3
    mejor, err_mejor = rejilla[0], math.inf
    for p in rejilla:
        errs = [(f(y[:t], 1, p)[0] - y[t]) ** 2 for t in range(max(minimo, len(y) - ventana), len(y))]
        e = float(np.mean(errs)) if errs else math.inf
        if e < err_mejor:
            mejor, err_mejor = p, e
    return mejor


def pronosticar(historia: Sequence[float], horizonte: int = 6) -> Dict:
    """Pronóstico de `horizonte` meses con el método que mejor predijo los
    últimos meses que no vio. Devuelve también la comparación de métodos."""
    y = np.asarray(historia, float)
    y = np.clip(y, 0, None)
    n = len(y)
    clase = clasificar_demanda(y)
    if n == 0:
        return {"metodo": None, "suficiente": False, "pronostico": [0.0] * horizonte, "meses": 0, "clase": clase}
    if n < MIN_MESES:
        media = float(y.mean())
        rmse = float(y.std()) if n > 1 else media
        return {"metodo": "PROMEDIO", "nombre": NOMBRES["PROMEDIO"], "suficiente": False, "meses": n,
                "pronostico": [round(media, 2)] * horizonte, "rmse": round(rmse, 2),
                "inferior": [round(max(0.0, media - 1.28 * rmse), 2)] * horizonte,
                "superior": [round(media + 1.28 * rmse, 2)] * horizonte,
                "comparacion": [], "clase": clase}

    intermitente = clase["tipo"] in ("INTERMITENTE", "IRREGULAR")
    candidatos = _candidatos(y, intermitente)
    # Validación: los últimos k meses, cada uno pronosticado con lo anterior.
    # Con demanda intermitente la ventana es la mitad de la historia: seis
    # meses pueden ser todos ceros y no dicen nada del tamaño de un pedido.
    k = max(6, n // 2) if intermitente else min(6, max(3, n // 4))
    inicio = n - k
    resultados = []
    for metodo in candidatos:
        f, _ = METODOS[metodo]
        minimo = MIN_ESTACIONAL if metodo == "HOLT_WINTERS" else 3
        if inicio < minimo:
            continue
        # El parámetro se elige con la historia anterior a la validación y
        # queda fijo: elegirlo en cada mes también le dejaría ver el futuro.
        p = _mejor_parametro(metodo, y[:inicio], k, intermitente)
        errores = [float(f(y[:t], 1, p)[0]) - y[t] for t in range(inicio, n)]
        e = np.array(errores)
        real = y[inicio:]
        resultados.append({
            "metodo": metodo, "nombre": NOMBRES[metodo],
            "mae": round(float(np.abs(e).mean()), 2),
            "rmse": round(float(np.sqrt((e ** 2).mean())), 2),
            "wape": round(float(np.abs(e).sum() / real.sum() * 100), 1) if real.sum() > 0 else None,
            "sesgo": round(float(e.sum() / real.sum() * 100), 1) if real.sum() > 0 else None,
        })
    resultados.sort(key=lambda r: r["rmse"])
    ganador = resultados[0]
    ingenuo = next((r for r in resultados if r["metodo"] == "INGENUO"), None)
    f, _ = METODOS[ganador["metodo"]]
    p = _mejor_parametro(ganador["metodo"], y, k, intermitente)
    pron = np.clip(f(y, horizonte, p), 0, None)
    # El intervalo crece con la distancia: el error a h meses es mayor que a uno.
    rmse = ganador["rmse"]
    z80 = 1.2816
    ancho = [z80 * rmse * math.sqrt(i) for i in range(1, horizonte + 1)]
    return {
        "metodo": ganador["metodo"], "nombre": ganador["nombre"], "suficiente": True, "meses": n,
        "meses_validacion": k, "clase": clase,
        "pronostico": [round(float(v), 2) for v in pron],
        "inferior": [round(max(0.0, float(v) - a), 2) for v, a in zip(pron, ancho)],
        "superior": [round(float(v) + a, 2) for v, a in zip(pron, ancho)],
        "rmse": rmse, "mae": ganador["mae"], "wape": ganador["wape"], "sesgo": ganador["sesgo"],
        # Valor agregado del pronóstico: cuánto error le quita al ingenuo.
        "fva_pct": round((1 - ganador["rmse"] / ingenuo["rmse"]) * 100, 1) if ingenuo and ingenuo["rmse"] > 0 else None,
        "comparacion": resultados,
    }


def z_servicio(nivel_pct: float) -> float:
    nivel = min(max(nivel_pct, 50.0), 99.9) / 100
    return NormalDist().inv_cdf(nivel)
