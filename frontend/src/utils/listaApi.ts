/**
 * Saca la lista de una respuesta que puede venir de dos formas.
 *
 * Algunos endpoints devuelven un arreglo y otros lo envuelven en
 * `{items, total, page, per_page}` porque paginan. Las pantallas hacían
 * `.map()` sobre lo que llegara, así que las que consumían un endpoint
 * paginado reventaban enteras con «x.map is not a function» — la de nómina
 * llevaba así hasta que se intentó fotografiarla.
 *
 * No se arregla haciendo que todos devuelvan arreglos: paginar la nómina de una
 * empresa grande es correcto, y quitarle la paginación traería de vuelta el
 * problema de traerse diez mil filas para llenar un desplegable.
 */
export function listaDe<T = unknown>(datos: unknown): T[] {
  if (Array.isArray(datos)) return datos as T[]
  if (datos && typeof datos === 'object') {
    const envoltorio = datos as Record<string, unknown>
    // `items` es la forma de este backend; `results` y `data` se aceptan porque
    // cuestan una línea y evitan el mismo fallo si algún endpoint cambia.
    for (const clave of ['items', 'results', 'data'] as const) {
      if (Array.isArray(envoltorio[clave])) return envoltorio[clave] as T[]
    }
  }
  // Ni arreglo ni envoltorio conocido: una lista vacía deja la pantalla en pie.
  // Es preferible un desplegable sin opciones a una pantalla en blanco con un
  // error de JavaScript.
  return []
}

/** Cuántos hay en total, cuando la respuesta lo dice. */
export function totalDe(datos: unknown, respaldo = 0): number {
  if (datos && typeof datos === 'object' && !Array.isArray(datos)) {
    const t = (datos as Record<string, unknown>).total
    if (typeof t === 'number') return t
  }
  if (Array.isArray(datos)) return datos.length
  return respaldo
}
