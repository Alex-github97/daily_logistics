/**
 * Empaques de los productos: para registrar en cajas/másters/estibas y mostrar
 * la equivalencia. El inventario siempre se lleva en unidades; esto solo
 * convierte lo que el usuario escribe o ve.
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'

export interface NivelMaestro { nivel: string; nombre: string; unidades: number }
export type Contar = 'UNIDAD' | 'CAJA' | 'MASTER' | 'ESTIBA'

export const NOMBRE_CONTAR: Record<Contar, [string, string]> = {
  UNIDAD: ['unidad', 'unidades'], CAJA: ['caja', 'cajas'], MASTER: ['máster', 'másters'], ESTIBA: ['estiba', 'estibas'],
}
const ORDEN: Contar[] = ['ESTIBA', 'MASTER', 'CAJA']

const num = (n: number) => n.toLocaleString('es-CO', { maximumFractionDigits: 2 })
export const plural = (n: number, c: Contar) => `${num(n)} ${NOMBRE_CONTAR[c][n === 1 ? 0 : 1]}`

/** Los niveles de empaque de cada producto (producto_id → niveles). */
export function useNiveles() {
  const q = useQuery<{ id: number; niveles: NivelMaestro[] }[]>({
    queryKey: ['wms-maestro', true],
    queryFn: () => api.get('/wms/maestro/productos', { params: { activo: true } }).then(r => r.data),
    staleTime: 60_000,
  })
  return useMemo(() => new Map((q.data ?? []).map(p => [p.id, p.niveles])), [q.data])
}

/** Unidades que trae un nivel del producto; 0 si el producto no tiene ese empaque. */
export function factor(niveles: NivelMaestro[] | undefined, c: Contar): number {
  if (c === 'UNIDAD') return 1
  return niveles?.find(n => n.nivel === c)?.unidades ?? 0
}

/** «27 und = 2 cajas + 3 und». Vacío si no hay empaques que aplicar. */
export function equivalencia(cantidad: number, niveles: NivelMaestro[] | undefined): string {
  let resto = cantidad
  const partes: string[] = []
  for (const c of ORDEN) {
    const f = factor(niveles, c)
    if (f > 1 && resto >= f) {
      const n = Math.floor(resto / f)
      partes.push(plural(n, c))
      resto -= n * f
    }
  }
  if (!partes.length) return ''
  if (resto > 0) partes.push(`${num(resto)} und`)
  return partes.join(' + ')
}
