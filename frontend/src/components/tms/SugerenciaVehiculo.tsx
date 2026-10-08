/**
 * Peso y volumen de lo que se va a mover y el vehículo que conviene.
 *
 * Se usa en el WMS (despacho, traslados, pedidos en línea) y en el TMS. Si se
 * pasa `onElegir`, los vehículos disponibles se pueden seleccionar; los que no
 * tienen capacidad para la carga no aparecen (el servidor tampoco los acepta).
 */
import { Alert, Box, Chip, CircularProgress, LinearProgress, Paper, Radio, Stack, Tooltip, Typography, alpha } from '@mui/material'
import { LocalShipping } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { ESTADO, PALETA, ACENTO } from '@/config/marca'

export interface FuenteCarga {
  orden_ids?: number[]
  despacho_id?: number
  traslado_id?: number
  lineas?: { producto_id: number; cantidad: number }[]
}
interface TipoSug { tipo: string; nombre: string; capacidad_kg: number | null; volumen_m3: number | null; cabe: boolean; uso_kg_pct: number | null; uso_m3_pct: number | null }
interface VehSug { id: number; placa: string; tipo: string; tipo_nombre: string; capacidad_kg: number | null; capacidad_m3: number | null; uso_kg_pct: number | null; uso_m3_pct: number | null }
export interface Estimacion {
  peso_kg: number; volumen_m3: number; sin_peso: string[]; sin_volumen: string[]
  detalle: { sku: string; nombre: string; unidades: number; como: string; peso_kg: number; volumen_m3: number }[]
  sugerencia: { recomendado: TipoSug | null; tipos: TipoSug[]; vehiculos: VehSug[]; tolerancia_pct: number }
}

const n = (x: number | null | undefined, d = 0) => x == null ? '—' : x.toLocaleString('es-CO', { maximumFractionDigits: d })
const color = (p: number) => p > 100 ? ESTADO.peligro : p > 85 ? ESTADO.alerta : ESTADO.exito

function Uso({ etiqueta, pct }: { etiqueta: string; pct: number | null }) {
  if (pct == null) return null
  return (
    <Box sx={{ minWidth: 90 }}>
      <Typography sx={{ fontSize: 10.5, color: PALETA.grafito }}>{etiqueta} {pct}%</Typography>
      <LinearProgress variant="determinate" value={Math.min(100, pct)}
        sx={{ height: 6, borderRadius: 3, bgcolor: PALETA.niebla, '& .MuiLinearProgress-bar': { bgcolor: color(pct) } }} />
    </Box>
  )
}

export default function SugerenciaVehiculo({ fuente, seleccionado, onElegir, titulo = 'Carga y vehículo sugerido' }: {
  fuente: FuenteCarga | null; seleccionado?: number | ''; onElegir?: (id: number | '') => void; titulo?: string
}) {
  const activa = !!fuente && !!((fuente.orden_ids?.length) || fuente.despacho_id || fuente.traslado_id || fuente.lineas?.length)
  const q = useQuery<Estimacion>({
    queryKey: ['carga-estimar', fuente], enabled: activa,
    queryFn: () => apiClient.post('/wms/carga/estimar', fuente).then(r => r.data),
  })
  if (!activa) return null
  if (q.isLoading) return <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}><CircularProgress size={18} /></Paper>
  if (!q.data) return null
  const e = q.data, s = e.sugerencia, rec = s.recomendado
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: alpha(ACENTO.base, 0.35), bgcolor: alpha(ACENTO.base, 0.03) }}>
      <Stack direction="row" alignItems="center" gap={1} mb={1}>
        <LocalShipping sx={{ color: ACENTO.base }} />
        <Typography sx={{ fontWeight: 800, fontSize: 14, flex: 1 }}>{titulo}</Typography>
        <Chip size="small" label={`${n(e.peso_kg, 1)} kg`} sx={{ fontWeight: 700 }} />
        <Chip size="small" label={`${n(e.volumen_m3, 3)} m³`} sx={{ fontWeight: 700 }} />
      </Stack>
      {(e.sin_peso.length > 0 || e.sin_volumen.length > 0) && (
        <Alert severity="warning" sx={{ mb: 1, py: 0, fontSize: 12 }}>
          Estimación incompleta: {e.sin_peso.length ? `sin peso ${e.sin_peso.join(', ')}` : ''}{e.sin_peso.length && e.sin_volumen.length ? ' · ' : ''}
          {e.sin_volumen.length ? `sin medidas ${e.sin_volumen.join(', ')}` : ''}. Complete el maestro o el cubicaje.
        </Alert>
      )}
      {rec ? (
        <Typography sx={{ fontSize: 13, mb: 1 }}>
          Vehículo sugerido: <b style={{ color: ACENTO.profundo }}>{rec.nombre}</b> (hasta {n(rec.capacidad_kg)} kg y {n(rec.volumen_m3, 1)} m³ ·
          uso {rec.uso_kg_pct ?? '—'}% del peso y {rec.uso_m3_pct ?? '—'}% del volumen)
        </Typography>
      ) : (
        <Alert severity="error" sx={{ mb: 1, py: 0, fontSize: 12 }}>Ningún tipo de vehículo configurado puede llevar esta carga completa: divídala en varios viajes.</Alert>
      )}
      <Stack direction="row" gap={0.5} flexWrap="wrap" mb={onElegir ? 1.5 : 0}>
        {s.tipos.map(t => (
          <Tooltip key={t.tipo} title={`${n(t.capacidad_kg)} kg · ${n(t.volumen_m3, 1)} m³`}>
            <Chip size="small" label={t.nombre} variant={rec?.tipo === t.tipo ? 'filled' : 'outlined'}
              sx={{ fontSize: 11, opacity: t.cabe ? 1 : 0.45, textDecoration: t.cabe ? 'none' : 'line-through',
                ...(rec?.tipo === t.tipo ? { bgcolor: ACENTO.base, color: '#fff' } : {}) }} />
          </Tooltip>
        ))}
      </Stack>
      {onElegir && (
        <>
          <Typography sx={{ fontSize: 12, fontWeight: 700, color: PALETA.grafito, mb: 0.5 }}>
            Vehículos disponibles que pueden llevarla ({s.vehiculos.length})
          </Typography>
          {!s.vehiculos.length && <Typography sx={{ fontSize: 12, color: PALETA.grafito }}>Ningún vehículo disponible tiene capacidad libre suficiente.</Typography>}
          <Stack gap={0.5}>
            {s.vehiculos.map(v => (
              <Stack key={v.id} direction="row" alignItems="center" gap={1.5} onClick={() => onElegir(seleccionado === v.id ? '' : v.id)}
                sx={{ px: 1, py: 0.5, borderRadius: 1.5, cursor: 'pointer', border: `1px solid ${seleccionado === v.id ? ACENTO.base : PALETA.niebla}`,
                  bgcolor: seleccionado === v.id ? alpha(ACENTO.base, 0.06) : '#fff' }}>
                <Radio size="small" checked={seleccionado === v.id} sx={{ p: 0.25 }} />
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 800, minWidth: 80 }}>{v.placa}</Typography>
                <Typography sx={{ fontSize: 12, flex: 1 }}>{v.tipo_nombre}{rec?.tipo === v.tipo ? ' · sugerido' : ''}</Typography>
                <Uso etiqueta="Peso" pct={v.uso_kg_pct} /><Uso etiqueta="Volumen" pct={v.uso_m3_pct} />
              </Stack>
            ))}
          </Stack>
        </>
      )}
    </Paper>
  )
}
