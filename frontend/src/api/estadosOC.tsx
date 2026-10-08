/**
 * Estados configurables de la orden de compra (WMS › Configuración › Estados de OC).
 */
import { Chip, alpha } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'

export interface EstadoOC {
  id: number; codigo: string; nombre: string; color: string; orden: number
  rol: string | null; rol_descripcion: string | null; obligatorio: boolean; activo: boolean; usos: number
}
export interface RolOC { rol: string; descripcion: string; obligatorio: boolean }

/** En estos roles la orden ya no admite recepciones. */
export const ROLES_SIN_RECEPCION = ['RECIBIDA', 'CERRADA', 'ANULADA']

export function useEstadosOC() {
  const q = useQuery<{ estados: EstadoOC[]; roles: RolOC[] }>({
    queryKey: ['wms-estados-oc'],
    queryFn: () => apiClient.get('/wms/estados-oc').then(r => r.data),
    staleTime: 60_000,
  })
  const estados = q.data?.estados ?? []
  const porCodigo = new Map(estados.map(e => [e.codigo, e]))
  return {
    ...q, estados, roles: q.data?.roles ?? [], porCodigo,
    /** Si una OC en ese estado admite recepciones. */
    admiteRecepcion: (codigo: string) => !ROLES_SIN_RECEPCION.includes(porCodigo.get(codigo)?.rol ?? ''),
  }
}

export function ChipEstadoOC({ codigo, estados }: { codigo: string; estados: Map<string, EstadoOC> }) {
  const e = estados.get(codigo)
  const color = e?.color ?? '#64748B'
  return (
    <Chip size="small" label={e?.nombre ?? codigo}
      sx={{ fontSize: 11, fontWeight: 700, bgcolor: alpha(color, 0.12), color, border: `1px solid ${alpha(color, 0.35)}` }} />
  )
}
