"""
Vectorización de planos y fotos de estanterías (módulo Mapa de bodega).

Cuando se carga un plano o se calibra la foto de una estantería, la imagen se
convierte en un SVG de líneas para la vista «gemelo digital»:

- Plano: se binariza (umbral de Otsu) y se extraen los trazos horizontales y
  verticales largos —muros, racks, recuadros, cotas— como segmentos con su
  grosor real. Lo diagonal corto (rayados) y el texto quedan fuera: el texto se
  muestra aparte, tenue, desde la imagen original.
- Estantería: con las 4 esquinas calibradas se endereza la cara (homografía) a
  una vista frontal; luego se detectan bordes (Sobel) y se extraen los
  horizontales (largueros, cajas) y verticales (postes) como un wireframe.

Solo numpy y Pillow: sin dependencias nuevas en el servidor.
"""
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

Seg = Tuple[float, float, float, float, float]   # x0, y0, x1, y1, grosor


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _otsu(g: np.ndarray) -> float:
    hist, _ = np.histogram(g, bins=256, range=(0, 256))
    total = g.size
    suma = np.dot(np.arange(256), hist)
    sb = wb = 0.0
    mejor, umbral = 0.0, 128
    for t in range(256):
        wb += hist[t]
        if wb == 0:
            continue
        wf = total - wb
        if wf == 0:
            break
        sb += t * hist[t]
        mb, mf = sb / wb, (suma - sb) / wf
        var = wb * wf * (mb - mf) ** 2
        if var > mejor:
            mejor, umbral = var, t
    return umbral


def _corridas(fila: np.ndarray, minimo: int):
    """Inicio y fin (exclusivo) de las corridas de True con largo >= minimo."""
    p = np.concatenate(([0], fila.astype(np.int8), [0]))
    d = np.diff(p)
    ini, fin = np.where(d == 1)[0], np.where(d == -1)[0]
    largo = fin - ini
    m = largo >= minimo
    return ini[m], fin[m]


def _segmentos(b: np.ndarray, minimo: int, paso: int = 3) -> List[Seg]:
    """Trazos horizontales: une corridas casi iguales de filas seguidas en un
    rectángulo y lo devuelve como segmento con su grosor."""
    activos = {}          # (x0, x1) redondeados → [y_ini, y_fin, x0, x1]
    salida: List[Seg] = []
    for y in range(b.shape[0]):
        ini, fin = _corridas(b[y], minimo)
        vistos = set()
        for x0, x1 in zip(ini, fin):
            k = (int(x0) // paso, int(x1) // paso)
            r = activos.get(k) or activos.get((k[0] - 1, k[1])) or activos.get((k[0], k[1] + 1)) \
                or activos.get((k[0] + 1, k[1])) or activos.get((k[0], k[1] - 1))
            if r is not None and r[1] == y - 1:
                r[1] = y
                vistos.add(id(r))
            else:
                r = [y, y, int(x0), int(x1)]
                activos[k] = r
                vistos.add(id(r))
        for k in [k for k, r in activos.items() if r[1] < y - 1]:
            r = activos.pop(k)
            salida.append((r[2], (r[0] + r[1] + 1) / 2, r[3], (r[0] + r[1] + 1) / 2, r[1] - r[0] + 1))
    for r in activos.values():
        salida.append((r[2], (r[0] + r[1] + 1) / 2, r[3], (r[0] + r[1] + 1) / 2, r[1] - r[0] + 1))
    return salida


def _horizontales_y_verticales(b_h: np.ndarray, b_v: np.ndarray, min_h: int, min_v: int) -> List[Seg]:
    h = _segmentos(b_h, min_h)
    v = [(y0, x0, y1, x1, g) for (x0, y0, x1, y1, g) in _segmentos(b_v.T, min_v)]
    # Un «segmento» más grueso que largo es en realidad una mancha: fuera.
    return [s for s in h + v if max(abs(s[2] - s[0]), abs(s[3] - s[1])) >= s[4] * 1.5]


def _svg(segs: Sequence[Seg], w: int, h: int, estilo: str) -> str:
    """SVG autónomo de trazos grises, sin fondo (la pantalla pone el fondo claro)."""
    gruesos = [s for s in segs if s[4] >= 6]
    finos = [s for s in segs if s[4] < 6]

    def lineas(lista, color, factor, minimo, opacidad):
        return "".join(
            f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{color}" '
            f'stroke-width="{max(minimo, g * factor):.1f}" stroke-opacity="{opacidad}"/>'
            for x0, y0, x1, y1, g in lista)

    if estilo == "plano":
        cuerpo = (f'<g stroke-linecap="square">{lineas(gruesos, "#334155", 0.7, 3, 0.95)}</g>'
                  f'<g stroke-linecap="round">{lineas(finos, "#64748B", 0.9, 1.4, 0.85)}</g>')
    else:
        cuerpo = (f'<g stroke-linecap="round">{lineas(gruesos, "#334155", 0.5, 2.2, 0.9)}'
                  f'{lineas(finos, "#64748B", 0.8, 1.1, 0.6)}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'{cuerpo}</svg>')


# ─── Plano ───────────────────────────────────────────────────────────────────

def vectorizar_plano(img: Image.Image) -> Tuple[str, int]:
    """SVG de líneas del plano y cuántos trazos tiene."""
    g = img.convert("L")
    ancho = 1600
    if g.width != ancho:
        g = g.resize((ancho, max(1, round(g.height * ancho / g.width))), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float32)
    oscuro = a < min(_otsu(a), 170)
    minimo = max(16, round(ancho * 0.011))
    segs = _horizontales_y_verticales(oscuro, oscuro, minimo, minimo)
    return _svg(segs, g.width, g.height, "plano"), len(segs)


# ─── Estanterías ─────────────────────────────────────────────────────────────

def _homografia(src, dst) -> List[float]:
    A, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    return list(np.linalg.solve(np.array(A, float), np.array(b, float)))


def rectificar(img: Image.Image, esquinas: Sequence[Sequence[float]]) -> Image.Image:
    """La cara de la estantería vista de frente (corrige la perspectiva)."""
    w, h = img.size
    q = [(x * w, y * h) for x, y in esquinas]       # arriba-izq, arriba-der, abajo-der, abajo-izq
    ancho = (np.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]) + np.hypot(q[2][0] - q[3][0], q[2][1] - q[3][1])) / 2
    alto = (np.hypot(q[3][0] - q[0][0], q[3][1] - q[0][1]) + np.hypot(q[2][0] - q[1][0], q[2][1] - q[1][1])) / 2
    escala = 1400 / max(ancho, 1)
    W, H = 1400, max(200, int(alto * escala))
    salida = [(0, 0), (W, 0), (W, H), (0, H)]
    coef = _homografia(salida, q)                    # PIL pide: salida → entrada
    return img.convert("L").transform((W, H), Image.PERSPECTIVE, coef, Image.BICUBIC)


def vectorizar_estanteria(rect: Image.Image) -> Tuple[str, int]:
    a = np.asarray(rect.convert("L"), dtype=np.float32)
    gx = np.zeros_like(a); gy = np.zeros_like(a)
    gx[:, 1:-1] = a[:, 2:] - a[:, :-2]
    gy[1:-1, :] = a[2:, :] - a[:-2, :]
    gx, gy = np.abs(gx), np.abs(gy)
    # Umbral alto: quedan postes, largueros, estibas y cajas; la textura del
    # fondo (ladrillo, sombras) es de bajo contraste y se va.
    umbral = max(24.0, float(np.percentile(np.maximum(gx, gy), 94)))
    W, H = rect.size
    segs = _horizontales_y_verticales(gy > umbral, gx > umbral, max(24, W // 30), max(24, H // 22))
    return _svg(segs, W, H, "estanteria"), len(segs)
