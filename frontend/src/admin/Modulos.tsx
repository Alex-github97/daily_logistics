/**
 * Qué módulos tiene contratados la empresa.
 *
 * Esta lista no es informativa: el servidor la hace cumplir en cada petición,
 * así que quitar un módulo acá se lo quita de verdad, aunque el usuario escriba
 * la URL a mano. Por eso el aviso al guardar es explícito.
 */
import { useState } from 'react'
import {
  Box, Card, Typography, Stack, Button, Checkbox, FormControlLabel, Alert,
  Skeleton, Chip, Divider,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, COLOR_MODULO } from '@/config/marca'
import { consolaApi, mensajeDeError, type Empresa } from './api'

export default function Modulos({ empresa }: { empresa: Empresa }) {
  const qc = useQueryClient()
  const [elegidos, setElegidos] = useState<Set<string> | null>(null)

  const { data: modulos = [], isLoading } = useQuery({
    queryKey: ['modulos', empresa.id],
    queryFn: () => consolaApi.modulos(empresa.id),
  })

  // La selección se siembra con lo que hay guardado la primera vez que llega.
  const actual = elegidos ?? new Set(modulos.filter(m => m.activo).map(m => m.clave))
  const cambiado = elegidos !== null &&
    JSON.stringify([...actual].sort()) !==
    JSON.stringify(modulos.filter(m => m.activo).map(m => m.clave).sort())

  const guardar = useMutation({
    mutationFn: () => consolaApi.guardarModulos(empresa.id, [...actual]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['modulos', empresa.id] })
      setElegidos(null)
      toast.success('Módulos actualizados')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const alternar = (clave: string) => {
    const nuevo = new Set(actual)
    if (nuevo.has(clave)) nuevo.delete(clave)
    else nuevo.add(clave)
    setElegidos(nuevo)
  }

  if (isLoading) return <Skeleton variant="rectangular" height={320} sx={{ borderRadius: 3 }} />

  const opcionales = modulos.filter(m => !m.esencial)
  const esenciales = modulos.filter(m => m.esencial)

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 2 }}>
        Lo que se desmarque aquí deja de funcionar para esta empresa de inmediato,
        también si alguien escribe la dirección a mano.
      </Alert>

      <Card sx={{ borderRadius: 3, p: 2.5 }}>
        <Stack direction="row" alignItems="center" mb={1.5}>
          <Typography variant="subtitle2" fontWeight={800} sx={{ flex: 1 }}>
            Módulos contratados
          </Typography>
          <Chip
            label={`${opcionales.filter(m => actual.has(m.clave)).length} de ${opcionales.length}`}
            size="small"
            sx={{ fontWeight: 700, bgcolor: `${COLOR_MODULO}14`, color: COLOR_MODULO }}
          />
        </Stack>

        <Box sx={{
          display: 'grid', gap: 0.25,
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr' },
        }}>
          {opcionales.map(m => (
            <FormControlLabel
              key={m.clave}
              control={
                <Checkbox
                  size="small" checked={actual.has(m.clave)}
                  onChange={() => alternar(m.clave)}
                />
              }
              label={<Typography variant="body2">{m.nombre}</Typography>}
            />
          ))}
        </Box>

        <Divider sx={{ my: 2 }} />
        <Typography variant="caption" color="text.secondary" display="block" mb={1}>
          Siempre incluidos — sin ellos nadie podría entrar ni administrar su propia empresa:
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={0.75}>
          {esenciales.map(m => (
            <Chip key={m.clave} label={m.nombre} size="small" variant="outlined"
              sx={{ fontSize: 11, color: PALETA.grafito }} />
          ))}
        </Stack>

        <Stack direction="row" spacing={1.5} mt={2.5}>
          <Button
            variant="contained" disabled={!cambiado || guardar.isPending}
            onClick={() => guardar.mutate()}
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            {guardar.isPending ? 'Guardando…' : 'Guardar módulos'}
          </Button>
          {cambiado && (
            <Button onClick={() => setElegidos(null)} sx={{ textTransform: 'none' }}>
              Descartar cambios
            </Button>
          )}
        </Stack>
      </Card>
    </Box>
  )
}
