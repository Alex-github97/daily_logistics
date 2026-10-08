/**
 * Número de documento automático (OC-2026-00042) en los formularios de creación.
 *
 * Muestra el próximo número como vista previa; el número definitivo lo asigna
 * el servidor al guardar (si otro usuario guarda antes, este avanza uno).
 */
import { InputAdornment, TextField } from '@mui/material'
import { Lock } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'

export function NumeroAutomatico({ tipo, etiqueta }: { tipo: 'OC' | 'REC' | 'OS' | 'DESP' | 'TRL'; etiqueta: string }) {
  const q = useQuery<{ siguiente: string }>({
    queryKey: ['consecutivo', tipo],
    queryFn: () => api.get(`/wms/consecutivos/${tipo}/siguiente`).then(r => r.data),
    staleTime: 0,
    refetchOnMount: 'always',
  })
  return (
    <TextField
      label={etiqueta}
      fullWidth
      size="small"
      value={q.data?.siguiente ?? 'Se asigna al guardar'}
      disabled
      helperText="Automático y único: se confirma al guardar"
      InputProps={{
        startAdornment: <InputAdornment position="start"><Lock sx={{ fontSize: 16 }} /></InputAdornment>,
        sx: { fontFamily: 'ui-monospace, monospace', fontWeight: 700 },
      }}
    />
  )
}
