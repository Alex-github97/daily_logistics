/**
 * Geometría del constructor de bodega (en metros): contornos y polilíneas con
 * tramos rectos o curvos. Un tramo va de un punto al siguiente y su curva es la
 * «flecha» `s`: cuánto se separa del centro de la cuerda el punto medio del
 * arco (0 = recto; positiva hacia la izquierda del sentido de avance, tal como
 * se ve en pantalla con el eje Y hacia abajo… es decir, hacia (-dy, dx)).
 * El constructor y la bodega 3D muestrean las curvas con estas mismas funciones.
 */
export interface Pt { x: number; y: number; s?: number }
export type XY = [number, number]

const TAU = Math.PI * 2

/** Datos del arco de un tramo, o null si es recto. */
export function arco(a: XY, b: XY, s: number) {
  const dx = b[0] - a[0], dy = b[1] - a[1], c = Math.hypot(dx, dy)
  if (Math.abs(s) < 1e-6 || c < 1e-9) return null
  const n: XY = [-dy / c, dx / c]
  const mc: XY = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const r = (c * c / 4 + s * s) / (2 * Math.abs(s))
  const k = s - Math.sign(s) * r
  const centro: XY = [mc[0] + n[0] * k, mc[1] + n[1] * k]
  const medio: XY = [mc[0] + n[0] * s, mc[1] + n[1] * s]
  const a0 = Math.atan2(a[1] - centro[1], a[0] - centro[0])
  const a1 = Math.atan2(b[1] - centro[1], b[0] - centro[0])
  const am = Math.atan2(medio[1] - centro[1], medio[0] - centro[0])
  const ccw = ((a1 - a0) % TAU + TAU) % TAU
  const hastaMedio = ((am - a0) % TAU + TAU) % TAU
  const barrido = hastaMedio < ccw ? ccw : ccw - TAU
  return { centro, r, a0, barrido, medio }
}

/** Punto medio visible de un tramo (en la curva si es curvo). */
export function medioTramo(a: XY, b: XY, s: number): XY {
  const ar = arco(a, b, s)
  return ar ? ar.medio : [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
}

/** Puntos del tramo de a hacia b (incluye a, excluye b). */
export function muestrearTramo(a: XY, b: XY, s: number): XY[] {
  const ar = arco(a, b, s)
  if (!ar) return [a]
  const n = Math.max(6, Math.ceil(Math.abs(ar.barrido) / (Math.PI / 36)))
  const out: XY[] = []
  for (let i = 0; i < n; i++) {
    const t = ar.a0 + ar.barrido * (i / n)
    out.push([ar.centro[0] + ar.r * Math.cos(t), ar.centro[1] + ar.r * Math.sin(t)])
  }
  return out
}

/** Toda la forma muestreada (cerrada: sin repetir el primer punto al final). */
export function muestrear(pts: Pt[], cerrado: boolean): XY[] {
  if (!pts.length) return []
  const out: XY[] = []
  const n = pts.length
  const tramos = cerrado ? n : n - 1
  for (let i = 0; i < tramos; i++) {
    const a = pts[i], b = pts[(i + 1) % n]
    out.push(...muestrearTramo([a.x, a.y], [b.x, b.y], a.s ?? 0))
  }
  if (!cerrado) out.push([pts[n - 1].x, pts[n - 1].y])
  return out
}

export function largoTramo(a: XY, b: XY, s: number): number {
  const ar = arco(a, b, s)
  return ar ? Math.abs(ar.barrido) * ar.r : Math.hypot(b[0] - a[0], b[1] - a[1])
}

export function perimetro(pts: Pt[], cerrado: boolean): number {
  let t = 0
  const n = pts.length, tramos = cerrado ? n : n - 1
  for (let i = 0; i < tramos; i++) { const a = pts[i], b = pts[(i + 1) % n]; t += largoTramo([a.x, a.y], [b.x, b.y], a.s ?? 0) }
  return t
}

export function area(pol: XY[]): number {
  let s = 0
  for (let i = 0; i < pol.length; i++) { const [x0, y0] = pol[i], [x1, y1] = pol[(i + 1) % pol.length]; s += x0 * y1 - x1 * y0 }
  return Math.abs(s) / 2
}

export function dentro(pol: XY[], x: number, y: number): boolean {
  let c = false
  for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) {
    const [xi, yi] = pol[i], [xj, yj] = pol[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c
  }
  return c
}

export function distSegmento(x: number, y: number, a: XY, b: XY): number {
  const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy
  const t = l2 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)) : 0
  return Math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))
}

export function distPolilinea(linea: XY[], x: number, y: number, cerrado = false): number {
  let d = Infinity
  const n = linea.length, tramos = cerrado ? n : n - 1
  for (let i = 0; i < tramos; i++) d = Math.min(d, distSegmento(x, y, linea[i], linea[(i + 1) % n]))
  return d
}

export function cajaDe(pts: XY[]) {
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1])
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) }
}

export function cruzan(a: XY, b: XY, c: XY, d: XY): boolean {
  const o = (p: XY, q: XY, r: XY) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]))
  return o(a, b, c) !== o(a, b, d) && o(c, d, a) !== o(c, d, b)
}

/** ¿Algún segmento de A cruza alguno de B? (A y B, polilíneas muestreadas) */
export function seCruzan(A: XY[], cerradoA: boolean, B: XY[], cerradoB: boolean): boolean {
  const ta = cerradoA ? A.length : A.length - 1, tb = cerradoB ? B.length : B.length - 1
  for (let i = 0; i < ta; i++) for (let j = 0; j < tb; j++) {
    if (cruzan(A[i], A[(i + 1) % A.length], B[j], B[(j + 1) % B.length])) return true
  }
  return false
}

export function pathSvg(pts: XY[], cerrado: boolean): string {
  if (!pts.length) return ''
  return pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(3)} ${p[1].toFixed(3)}`).join(' ') + (cerrado ? ' Z' : '')
}

/** Partir un tramo curvo en su punto medio sin cambiar la forma: las dos
 *  mitades conservan el mismo arco. Devuelve [s de la primera, punto medio, s de la segunda]. */
export function partirTramo(a: XY, b: XY, s: number): [number, XY, number] {
  const ar = arco(a, b, s)
  if (!ar) return [0, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], 0]
  const c2 = Math.hypot(ar.medio[0] - a[0], ar.medio[1] - a[1])
  const s2 = Math.sign(s) * (ar.r - Math.sqrt(Math.max(0, ar.r * ar.r - (c2 / 2) ** 2)))
  return [s2, ar.medio, s2]
}

/** Flecha que hace pasar el arco por el punto p (proyección sobre la normal de la cuerda). */
export function flechaPor(a: XY, b: XY, p: XY): number {
  const dx = b[0] - a[0], dy = b[1] - a[1], c = Math.hypot(dx, dy)
  if (c < 1e-9) return 0
  const n: XY = [-dy / c, dx / c]
  return (p[0] - (a[0] + b[0]) / 2) * n[0] + (p[1] - (a[1] + b[1]) / 2) * n[1]
}
