"""
Agrupar registros por lo que dicen: problemas que se repiten con otras palabras.

Siete no conformidades pueden titularse distinto —«remisión sin firma»,
«falta firma del cliente en guía», «documento de entrega incompleto»— y ser el
mismo problema. Contarlas por categoría no lo muestra; leerlas todas, nadie lo
hace. Aquí se representan con TF-IDF (qué palabras distinguen a cada texto) y
se agrupan por similitud de coseno con un umbral fijo: dos textos quedan juntos
solo si comparten vocabulario de verdad, no porque el algoritmo tenga que
repartir en un número de grupos pedido de antemano.

Lo que no hace: entender sinónimos que no comparten raíz. «Tardanza» y
«retraso» quedan separados. Por eso cada grupo muestra sus textos: la
agrupación propone, la persona confirma.
"""
import re
import unicodedata
from typing import Dict, List, Sequence

import numpy as np

# Palabras vacías del español y del vocabulario de calidad que aparece en todo
# (no distingue un problema de otro).
VACIAS = set("""
a al algo algun alguna algunas alguno algunos ante antes asi aun aunque bajo bien cada casi como con contra cual
cuales cuando de del desde donde dos durante e el ella ellas ellos en entre era eran es esa esas ese eso esos esta
estaba estan estar este esto estos fue fueron ha hace hacia han hasta hay la las le les lo los mas me mientras mismo
muy nada ni no nos o otra otras otro otros para pero poco por porque que quien se segun ser si sin sobre solo son su
sus tambien tan tanto te tiene tienen todo todos tras tu un una uno unos y ya se sea fueron sido
no conformidad nc hallazgo evidencia detecta detecto detectado detectada registra registro se evidencio presenta
presento caso casos proceso procesos area realizar realizo debido falta
""".split())


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def _tokens(t: str) -> List[str]:
    # Raíz rudimentaria: se quitan plurales para que «firma» y «firmas» cuenten igual.
    salida = []
    for p in _normalizar(t).split():
        if len(p) < 3 or p in VACIAS or p.isdigit():
            continue
        if len(p) > 4 and p.endswith("es"):
            p = p[:-2]
        elif len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        salida.append(p)
    return salida


def agrupar(textos: Sequence[str], umbral: float = 0.72, minimo: int = 3) -> Dict:
    """Grupos de textos parecidos. `umbral` es la distancia de coseno máxima
    promedio para unir dos grupos (0 = idénticos, 1 = nada en común).

    Devuelve los grupos de al menos `minimo` textos, con los índices de sus
    textos y las palabras que los definen.
    """
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.feature_extraction.text import TfidfVectorizer

    docs = [" ".join(_tokens(t or "")) for t in textos]
    utiles = [i for i, d in enumerate(docs) if d.strip()]
    if len(utiles) < minimo:
        return {"suficiente": False, "textos": len(utiles), "grupos": []}
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    try:
        X = vec.fit_transform([docs[i] for i in utiles])
    except ValueError:
        return {"suficiente": False, "textos": len(utiles), "grupos": []}
    # Un texto cuyas palabras no aparecen en ningún otro queda en cero: no se
    # parece a nada, así que no puede formar grupo y se aparta.
    con_vocabulario = np.asarray(X.getnnz(axis=1) > 0).ravel()
    X = X[con_vocabulario]
    utiles = [i for i, ok in zip(utiles, con_vocabulario) if ok]
    if X.shape[1] == 0 or X.shape[0] < minimo:
        return {"suficiente": False, "textos": len(utiles), "grupos": []}
    etiquetas = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                        distance_threshold=umbral).fit_predict(X.toarray())
    vocab = np.array(vec.get_feature_names_out())
    grupos = []
    for g in set(etiquetas):
        idx = [utiles[i] for i in np.where(etiquetas == g)[0]]
        if len(idx) < minimo:
            continue
        centro = np.asarray(X[np.where(etiquetas == g)[0]].mean(axis=0)).ravel()
        terminos = [t for t in vocab[np.argsort(-centro)][:6] if centro[vec.vocabulary_[t]] > 0]
        grupos.append({"indices": idx, "terminos": terminos})
    grupos.sort(key=lambda g: -len(g["indices"]))
    return {"suficiente": True, "textos": len(utiles), "grupos": grupos}
