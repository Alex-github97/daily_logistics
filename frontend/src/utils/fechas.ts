/**
 * Fechas sin hora («2026-10-15») como día local.
 *
 * `new Date('2026-10-15')` es medianoche UTC: en Colombia (UTC−5) eso es el 14
 * a las 7 p. m., y las pantallas mostraban un día menos en fechas de emisión,
 * vencimientos, entregas… Con hora («2026-10-15T14:30:00Z») se comporta igual
 * que `new Date`.
 */
export function aFecha(v: string | number | Date | null | undefined): Date {
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)) {
    const [a, m, d] = v.split('-').map(Number)
    return new Date(a, m - 1, d)
  }
  return new Date(v as string)
}
