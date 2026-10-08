"""
Clasificador predictivo con validación hacia adelante en el tiempo.

CÓMO SE SABE SI EL MODELO SIRVE
Se entrena con el pasado y se califica con lo que pasó DESPUÉS, nunca con una
partición al azar: en datos de mantenimiento, mezclar meses deja que el modelo
«vea» el futuro del mismo equipo y la cifra sale inflada. El corte es por fecha.

Y siempre se compara contra lo más simple que existe: decir a todos la tasa
histórica de falla. Si el modelo no le gana a eso (índice de habilidad de
Brier ≤ 0), la pantalla lo dice y no muestra sus probabilidades como si fueran
conocimiento. Un modelo que no supera al promedio es ruido con decimales.

POR QUÉ DOS MODELOS
Con pocos cientos de filas, una regresión logística suele ganarle al gradient
boosting; con miles y relaciones no lineales, al revés. Se entrenan los dos y
se queda el que mejor califica en el periodo de prueba, no el más sofisticado.

MEMORIA
scikit-learn se importa aquí adentro y no al arrancar: en producción corren
cuatro procesos y cargarlo en todos, aunque nadie abra la pantalla, es memoria
que el servidor no tiene de sobra.
"""
from typing import Dict, List, Optional, Sequence

import numpy as np

MIN_POSITIVOS_ENTRENAR = 15
MIN_POSITIVOS_PRUEBA = 5
MIN_FILAS_PRUEBA = 30


def entrenar(filas: List[Dict], objetivo: Sequence[int], fechas: Sequence,
             categoricas: Sequence[str], etiquetas: Dict[str, str],
             fraccion_prueba: float = 0.25) -> Dict:
    """Entrena, valida hacia adelante y devuelve el modelo con su calificación.

    `filas` son diccionarios de variables por observación, `objetivo` 0/1,
    `fechas` el corte de cada observación. `etiquetas` traduce cada variable
    a lo que se muestra en pantalla.
    """
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

    X = pd.DataFrame(filas)
    y = np.asarray(objetivo, dtype=int)
    f = pd.to_datetime(pd.Series(list(fechas)))
    cats = [c for c in categoricas if c in X.columns]
    nums = [c for c in X.columns if c not in cats]
    for c in cats:
        X[c] = X[c].fillna("—").astype(str)

    base = {"filas": int(len(y)), "positivos": int(y.sum()), "suficiente": False}
    if len(y) == 0:
        return {**base, "motivo": "No hay historia para entrenar"}

    corte = f.quantile(1 - fraccion_prueba)
    ent, pru = (f < corte).to_numpy(), (f >= corte).to_numpy()
    pos_ent, pos_pru = int(y[ent].sum()), int(y[pru].sum())
    base.update({"positivos_entrenamiento": pos_ent, "positivos_prueba": pos_pru,
                 "filas_prueba": int(pru.sum()),
                 "corte_validacion": corte.date().isoformat()})
    if pos_ent < MIN_POSITIVOS_ENTRENAR or pos_pru < MIN_POSITIVOS_PRUEBA or pru.sum() < MIN_FILAS_PRUEBA:
        return {**base, "motivo": (
            f"Hacen falta al menos {MIN_POSITIVOS_ENTRENAR} fallas para entrenar y "
            f"{MIN_POSITIVOS_PRUEBA} en el periodo de prueba; hay {pos_ent} y {pos_pru}.")}
    if len(set(y[ent])) < 2 or len(set(y[pru])) < 2:
        return {**base, "motivo": "Todas las observaciones tienen el mismo resultado"}

    def logistica():
        pre = ColumnTransformer([
            ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), nums),
            ("cat", OneHotEncoder(handle_unknown="ignore"), cats),
        ])
        return make_pipeline(pre, LogisticRegression(C=0.5, max_iter=2000))

    def boosting():
        pre = ColumnTransformer([
            ("num", "passthrough", nums),
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), cats),
        ])
        n_cat = len(cats)
        mascara = [False] * len(nums) + [True] * n_cat
        return make_pipeline(pre, HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=20,
            l2_regularization=1.0, categorical_features=mascara if n_cat else None,
            random_state=0))

    tasa = float(y[ent].mean())
    brier_base = float(np.mean((y[pru] - tasa) ** 2))
    candidatos = {}
    for nombre, fabrica in (("Regresión logística", logistica), ("Gradient boosting", boosting)):
        m = fabrica().fit(X[ent], y[ent])
        p = m.predict_proba(X[pru])[:, 1]
        brier = float(brier_score_loss(y[pru], p))
        candidatos[nombre] = {"modelo": m, "p": p, "brier": brier,
                              "auc": float(roc_auc_score(y[pru], p)),
                              "habilidad": 1 - brier / brier_base if brier_base > 0 else 0.0}
    elegido = min(candidatos, key=lambda k: candidatos[k]["brier"])
    c = candidatos[elegido]

    # Calibración: en cada tramo de probabilidad, ¿cuántas fallas hubo de verdad?
    calibracion = []
    bordes = np.quantile(c["p"], [0, 0.5, 0.8, 0.95, 1.0])
    for lo, hi in zip(bordes[:-1], bordes[1:]):
        sel = (c["p"] >= lo) & (c["p"] <= hi)
        if sel.sum():
            calibracion.append({"desde": round(float(lo) * 100, 1), "hasta": round(float(hi) * 100, 1),
                                "observaciones": int(sel.sum()),
                                "predicho": round(float(c["p"][sel].mean()) * 100, 1),
                                "real": round(float(y[pru][sel].mean()) * 100, 1)})

    imp = permutation_importance(c["modelo"], X[pru], y[pru], scoring="neg_brier_score",
                                 n_repeats=8, random_state=0)
    importancia = sorted(
        ({"variable": col, "etiqueta": etiquetas.get(col, col),
          "aporte": round(float(v), 5)} for col, v in zip(X.columns, imp.importances_mean)),
        key=lambda x: -x["aporte"])

    util = c["habilidad"] > 0.02 and c["auc"] > 0.6
    # Lo que el modelo conoce: el rango de cada variable en la historia. Un
    # árbol que nunca vio 1.300 horas sin parada no «extrapola», repite la hoja
    # más cercana con toda su seguridad; hay que avisarlo.
    rangos = {col: (float(X[col].quantile(0.005)), float(X[col].quantile(0.995)))
              for col in nums if X[col].notna().any()}
    conocidas = {col: set(X[col].unique()) for col in cats}
    # El modelo final se reentrena con TODA la historia: la validación ya dijo
    # cuánto confiar en él; tirar los últimos meses sería perder lo más reciente.
    final = (logistica if elegido == "Regresión logística" else boosting)().fit(X, y)
    return {
        **base, "suficiente": True, "util": util,
        "modelo": elegido,
        "auc": round(c["auc"], 3), "brier": round(c["brier"], 4),
        "brier_referencia": round(brier_base, 4),
        "habilidad": round(c["habilidad"], 3),
        "tasa_historica": round(tasa * 100, 1),
        "comparacion": {k: {"auc": round(v["auc"], 3), "habilidad": round(v["habilidad"], 3)}
                        for k, v in candidatos.items()},
        "calibracion": calibracion,
        "importancia": [i for i in importancia if i["aporte"] > 0][:8],
        "_modelo": final, "_columnas": list(X.columns), "_categoricas": cats,
        "_rangos": rangos, "_conocidas": conocidas,
    }


def fuera_de_experiencia(resultado: Dict, fila: Dict, etiquetas: Dict[str, str]) -> List[str]:
    """Las variables de esta observación que caen fuera de lo que el modelo
    vio al entrenar. Si hay alguna, su probabilidad no está respaldada."""
    avisos = []
    for col, (lo, hi) in resultado.get("_rangos", {}).items():
        v = fila.get(col)
        if v is not None and not (lo <= v <= hi):
            avisos.append(etiquetas.get(col, col))
    for col, vistos in resultado.get("_conocidas", {}).items():
        v = fila.get(col)
        if v is not None and str(v) not in vistos:
            avisos.append(etiquetas.get(col, col))
    return avisos


def predecir(resultado: Dict, filas: List[Dict]) -> Optional[np.ndarray]:
    if not resultado.get("suficiente") or not filas:
        return None
    import pandas as pd
    X = pd.DataFrame(filas)[resultado["_columnas"]]
    for c in resultado["_categoricas"]:
        X[c] = X[c].fillna("—").astype(str)
    return resultado["_modelo"].predict_proba(X)[:, 1]


def publico(resultado: Dict) -> Dict:
    """Lo que se puede serializar: sin el objeto del modelo."""
    return {k: v for k, v in resultado.items() if not k.startswith("_")}
