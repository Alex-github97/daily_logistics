/**
 * Cuánto usa la empresa la plataforma, contado dentro de su propio esquema.
 *
 * Sirve para lo que un operador necesita ver antes de que se lo digan: que un
 * cliente lleva semanas sin entrar, o que uno pequeño está creciendo. Son
 * conteos, no contenido — la consola no muestra los datos del cliente.
 */
import {
  Box, Card, Typography, Stack, Skeleton, Alert, Chip, Divider,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { consolaApi, type Empresa } from './api'
import { aFecha } from '@/utils/fechas'

const cuando = (iso?: string | null) => {
  if (!iso) return { texto: 'Nunca ha entrado nadie', dias: null as number | null }
  const d = aFecha(iso)
  if (isNaN(d.getTime())) return { texto: iso, dias: null }
  const dias = Math.floor((Date.now() - d.getTime()) / 86400000)
  const fecha = d.toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' })
  if (dias === 0) return { texto: `Hoy · ${fecha}`, dias }
  if (dias === 1) return { texto: `Ayer · ${fecha}`, dias }
  return { texto: `Hace ${dias} días · ${fecha}`, dias }
}

function Dato({ etiqueta, valor, pie, color }: {
  etiqueta: string; valor: string | number; pie?: string; color?: string
}) {
  return (
    <Box sx={{ flex: 1, minWidth: 140 }}>
      <Typography variant="caption" color="text.secondary">{etiqueta}</Typography>
      <Typography variant="h6" fontWeight={800} sx={{
        fontVariantNumeric: 'tabular-nums', color: color ?? PALETA.tinta,
      }}>
        {valor}
      </Typography>
      {pie && <Typography variant="caption" color="text.secondary">{pie}</Typography>}
    </Box>
  )
}

export default function Uso({ empresa }: { empresa: Empresa }) {
  const { data: uso, isLoading } = useQuery({
    queryKey: ['uso', empresa.id], queryFn: () => consolaApi.uso(empresa.id),
  })

  if (isLoading || !uso) {
    return <Skeleton variant="rectangular" height={300} sx={{ borderRadius: 3 }} />
  }

  const ingreso = cuando(uso.ultimo_ingreso)
  // Un mes sin que entre nadie es la señal temprana de que el cliente se está
  // yendo; conviene verla antes de que llegue la carta.
  const abandonando = ingreso.dias !== null && ingreso.dias > 30
  const sinDatos = Object.values(uso.conteos).every(v => v === 0)

  return (
    <Box>
      {abandonando && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Nadie de esta empresa ha entrado en {ingreso.dias} días.
        </Alert>
      )}
      {!uso.ultimo_ingreso && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Nadie ha entrado nunca a esta empresa. Puede que no le hayan entregado
          las credenciales.
        </Alert>
      )}

      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
        <Typography variant="subtitle2" fontWeight={800} mb={2}>Actividad</Typography>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <Dato etiqueta="Usuarios" valor={`${uso.usuarios_activos} de ${uso.usuarios}`}
            pie="activos del total" />
          <Divider orientation="vertical" flexItem />
          <Dato
            etiqueta="Entraron en 30 días" valor={uso.activos_30d}
            pie={`de ${uso.usuarios_activos} activos`}
            color={uso.activos_30d === 0 ? ESTADO.peligro : undefined}
          />
          <Divider orientation="vertical" flexItem />
          <Box sx={{ flex: 2, minWidth: 220 }}>
            <Typography variant="caption" color="text.secondary">Último ingreso</Typography>
            <Typography variant="body2" fontWeight={700} sx={{ mt: 0.5 }}>
              {ingreso.texto}
            </Typography>
          </Box>
        </Stack>
      </Card>

      <Card sx={{ borderRadius: 3, p: 2.5 }}>
        <Stack direction="row" alignItems="center" mb={2}>
          <Typography variant="subtitle2" fontWeight={800} sx={{ flex: 1 }}>
            Volumen de información
          </Typography>
          <Chip label="Solo conteos" size="small" variant="outlined"
            sx={{ fontSize: 10, color: PALETA.grafito }} />
        </Stack>

        {sinDatos && (
          <Alert severity="info" sx={{ mb: 2 }}>
            La empresa todavía no ha cargado nada. Si lleva tiempo dada de alta,
            puede que necesite acompañamiento para arrancar.
          </Alert>
        )}

        <Box sx={{
          display: 'grid', gap: 1.5,
          gridTemplateColumns: { xs: '1fr 1fr', sm: 'repeat(4, 1fr)' },
        }}>
          {Object.entries(uso.conteos).map(([etiqueta, n]) => (
            <Box key={etiqueta} sx={{
              p: 1.5, borderRadius: 2, bgcolor: PALETA.bruma,
              border: `1px solid ${PALETA.niebla}`,
            }}>
              <Typography variant="h6" fontWeight={800} sx={{
                fontVariantNumeric: 'tabular-nums',
                color: n > 0 ? COLOR_MODULO : PALETA.acero,
              }}>
                {n.toLocaleString('es-CO')}
              </Typography>
              <Typography variant="caption" color="text.secondary">{etiqueta}</Typography>
            </Box>
          ))}
        </Box>
      </Card>
    </Box>
  )
}
