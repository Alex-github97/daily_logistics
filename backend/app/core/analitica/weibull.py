"""
Confiabilidad estadística: Weibull con censura y Crow-AMSAA.

DOS PREGUNTAS DISTINTAS, DOS MODELOS
  Weibull     ¿cuánto dura un COMPONENTE? Cada falla de un modo (el alternador,
              la bomba) se repara cambiando la pieza, así que después de la
              falla la pieza vuelve a empezar. Los intervalos entre fallas del
              mismo modo son vidas de piezas distintas y se pueden juntar.
  Crow-AMSAA  ¿el EQUIPO se está deteriorando? Un camión no se cambia cuando
              falla: se repara y sigue envejeciendo. Sus fallas no son vidas
              independientes, son un proceso en el tiempo, y lo que interesa
              es si se aceleran.

LA CENSURA NO ES UN DETALLE
Un equipo que lleva 80.000 km sin fallar dice algo: que la pieza dura MÁS de
80.000 km. Si solo se ajustan las fallas observadas, la vida sale más corta de
lo que es, y tanto más corta cuanto mejor funcione la flota. Por eso cada
intervalo abierto entra como censurado («vivió al menos esto»).

El intervalo antes de la primera falla observada también entra como censurado:
no se sabe qué edad tenía la pieza cuando empezó el registro, solo que llegó al
menos hasta ahí. Es una cota conservadora; subestima un poco la vida, nunca la
exagera.
"""
import math
from typing import Dict, List, Optional, Sequence

import numpy as np

MIN_FALLAS_WEIBULL = 5
MIN_FALLAS_CROW = 4


def _loglik(beta: float, eta: float, t: np.ndarray, d: np.ndarray) -> float:
    z = t / eta
    return float(np.sum(d * (math.log(beta) - math.log(eta) + (beta - 1) * np.log(z)))
                 - np.sum(z ** beta))


def ajustar_weibull(tiempos: Sequence[float], fallo: Sequence[bool]) -> Dict:
    """Máxima verosimilitud de Weibull de dos parámetros con censura por la derecha.

    `tiempos` son las vidas observadas y `fallo` dice si terminó en falla
    (True) o si seguía viva al cortar (False). Devuelve forma β, escala η,
    intervalos de confianza del 90 % y la prueba contra el modelo exponencial.
    """
    t = np.asarray(tiempos, dtype=float)
    d = np.asarray(fallo, dtype=float)
    mask = t > 0
    t, d = t[mask], d[mask]
    r = int(d.sum())
    base = {"fallas": r, "censurados": int(len(t) - r), "suficiente": r >= MIN_FALLAS_WEIBULL,
            "minimo": MIN_FALLAS_WEIBULL}
    if r < MIN_FALLAS_WEIBULL:
        return base

    # Se escala por la vida mayor: con kilómetros, t^β se desborda enseguida.
    escala = float(t.max())
    ts = t / escala
    ln_t = np.log(ts)
    media_ln_fallas = float(np.sum(d * ln_t) / r)

    def g(b: float) -> float:
        tb = ts ** b
        return float(np.sum(tb * ln_t) / np.sum(tb)) - 1.0 / b - media_ln_fallas

    # g es creciente en β: bisección, que no se pierde como Newton cuando
    # hay pocos datos.
    lo, hi = 0.02, 30.0
    if g(lo) > 0 or g(hi) < 0:
        return {**base, "suficiente": False, "motivo": "Los datos no permiten un ajuste estable"}
    for _ in range(200):
        mid = (lo + hi) / 2
        if g(mid) > 0:
            hi = mid
        else:
            lo = mid
    beta = (lo + hi) / 2
    eta = escala * float((np.sum(ts ** beta) / r) ** (1 / beta))

    # Intervalo de confianza por la matriz de información observada, en
    # escala logarítmica para que el intervalo no cruce el cero.
    def ll(lb: float, le: float) -> float:
        return _loglik(math.exp(lb), math.exp(le), t, d)
    lb0, le0, h = math.log(beta), math.log(eta), 1e-4
    f0 = ll(lb0, le0)
    hbb = (ll(lb0 + h, le0) - 2 * f0 + ll(lb0 - h, le0)) / h ** 2
    hee = (ll(lb0, le0 + h) - 2 * f0 + ll(lb0, le0 - h)) / h ** 2
    hbe = (ll(lb0 + h, le0 + h) - ll(lb0 + h, le0 - h) - ll(lb0 - h, le0 + h) + ll(lb0 - h, le0 - h)) / (4 * h ** 2)
    info = -np.array([[hbb, hbe], [hbe, hee]])
    ic_beta = ic_eta = None
    try:
        cov = np.linalg.inv(info)
        z90 = 1.645
        sb, se = math.sqrt(max(cov[0, 0], 0)), math.sqrt(max(cov[1, 1], 0))
        ic_beta = [round(beta * math.exp(-z90 * sb), 3), round(beta * math.exp(z90 * sb), 3)]
        ic_eta = [round(eta * math.exp(-z90 * se), 1), round(eta * math.exp(z90 * se), 1)]
    except np.linalg.LinAlgError:
        pass

    # ¿Hace falta Weibull, o basta con una tasa constante? Razón de
    # verosimilitudes contra el exponencial (β = 1), chi-cuadrado con 1 grado.
    eta_exp = float(t.sum() / r)
    lr = max(0.0, 2 * (f0 - _loglik(1.0, eta_exp, t, d)))
    p_exponencial = math.erfc(math.sqrt(lr / 2))

    return {
        **base,
        "beta": round(beta, 3), "eta": round(eta, 1),
        "ic90_beta": ic_beta, "ic90_eta": ic_eta,
        "vida_media": round(eta * math.gamma(1 + 1 / beta), 1),
        "b10": round(vida_b(beta, eta, 0.10), 1),
        "p_valor_vs_exponencial": round(p_exponencial, 4),
        "patron": patron(beta, ic_beta),
    }


def patron(beta: float, ic: Optional[List[float]] = None) -> str:
    """La lectura del β. Si el intervalo cruza el 1 no se puede afirmar
    desgaste ni mortalidad infantil: se dice que es aleatoria."""
    if ic and ic[0] <= 1 <= ic[1]:
        return "ALEATORIA"
    if beta < 1:
        return "INFANTIL"
    if beta <= 1.1:
        return "ALEATORIA"
    return "DESGASTE"


def confiabilidad(t: float, beta: float, eta: float) -> float:
    return math.exp(-((max(t, 0) / eta) ** beta))


def vida_b(beta: float, eta: float, p: float) -> float:
    """Vida a la que ha fallado la fracción p de la población (B10 con p=0.1)."""
    return eta * (-math.log(1 - p)) ** (1 / beta)


def prob_falla_condicional(edad: float, horizonte: float, beta: float, eta: float) -> float:
    """Probabilidad de fallar en los próximos `horizonte`, dado que ya llegó a
    `edad` sin fallar. Es la cifra útil para un equipo concreto: la de la
    población entera no dice nada de uno que ya lleva media vida."""
    if horizonte <= 0:
        return 0.0
    return 1 - math.exp(-(((edad + horizonte) / eta) ** beta - (max(edad, 0) / eta) ** beta))


def reemplazo_optimo(beta: float, eta: float, costo_preventivo: float, costo_falla: float) -> Optional[Dict]:
    """Edad de reemplazo preventivo que minimiza el costo por unidad de vida.

    Modelo clásico de reemplazo por edad: cambiar a la edad T cuesta Cp si la
    pieza llegó viva y Cf si falló antes. Solo tiene sentido con desgaste
    (β > 1) y cuando fallar sale más caro que prevenir; si no, lo óptimo es
    usar la pieza hasta que falle, y así se dice.
    """
    if beta <= 1 or costo_falla <= costo_preventivo or costo_preventivo <= 0:
        return None
    T = np.linspace(eta * 0.02, eta * 3, 1500)
    R = np.exp(-((T / eta) ** beta))
    # ∫0^T R(u) du por trapecios acumulados
    integ = np.concatenate([[T[0]], T[0] + np.cumsum((R[1:] + R[:-1]) / 2 * np.diff(T))])
    costo = (costo_preventivo * R + costo_falla * (1 - R)) / integ
    i = int(np.argmin(costo))
    correctivo = costo_falla / (eta * math.gamma(1 + 1 / beta))
    # Un mínimo en el borde de la búsqueda es «nunca cambiarla» disfrazado:
    # a 3η ya falló casi todo y el costo iguala al correctivo salvo decimales.
    # Por debajo de 1 % de ahorro tampoco vale la pena la regla.
    if i >= len(T) - 1 or costo[i] >= correctivo * 0.99:
        return None
    return {
        "edad": round(float(T[i]), 1),
        "costo_por_unidad": round(float(costo[i]), 4),
        "costo_por_unidad_correctivo": round(correctivo, 4),
        "ahorro_pct": round((1 - float(costo[i]) / correctivo) * 100, 1),
        "prob_fallar_antes": round(float(1 - R[i]) * 100, 1),
    }


def _chi2_cdf_par(x: float, gl_mitad: int) -> float:
    """CDF de chi-cuadrado con 2k grados de libertad, que tiene forma cerrada."""
    s, termino = 0.0, 1.0
    for k in range(gl_mitad):
        if k:
            termino *= (x / 2) / k
        s += termino
    return 1 - math.exp(-x / 2) * s


def crow_amsaa(tiempos_falla: Sequence[float], tiempo_total: float) -> Dict:
    """Proceso de Poisson de ley de potencias (Crow-AMSAA, MIL-HDBK-189),
    truncado en el tiempo total observado.

    β < 1: las fallas se espacian (el equipo mejora). β > 1: se aceleran (se
    deteriora). La prueba de tendencia compara contra β = 1, tasa constante.
    """
    t = sorted(x for x in tiempos_falla if x > 0)
    n = len(t)
    if n < MIN_FALLAS_CROW or tiempo_total <= 0:
        return {"fallas": n, "suficiente": False, "minimo": MIN_FALLAS_CROW}
    T = max(tiempo_total, t[-1])
    suma = sum(math.log(T / x) for x in t)
    if suma <= 0:
        return {"fallas": n, "suficiente": False, "minimo": MIN_FALLAS_CROW}
    beta = n / suma
    lam = n / T ** beta
    estad = 2 * suma                       # chi² con 2n grados si β = 1
    cdf = _chi2_cdf_par(estad, n)
    p = 2 * min(cdf, 1 - cdf)
    intensidad = lam * beta * T ** (beta - 1)
    if p >= 0.10:
        tendencia = "ESTABLE"
    else:
        tendencia = "DETERIORO" if beta > 1 else "MEJORA"
    return {
        "fallas": n, "suficiente": True,
        "beta": round(beta, 3), "lambda": lam,
        "p_valor_tendencia": round(p, 4), "tendencia": tendencia,
        "mtbf_actual": round(1 / intensidad, 1) if intensidad > 0 else None,
        "mtbf_promedio": round(T / n, 1),
    }


def fallas_esperadas(ca: Dict, tiempo_total: float, horizonte: float) -> Optional[float]:
    if not ca.get("suficiente"):
        return None
    b, lam = ca["beta"], ca["lambda"]
    return round(lam * ((tiempo_total + horizonte) ** b - tiempo_total ** b), 2)
