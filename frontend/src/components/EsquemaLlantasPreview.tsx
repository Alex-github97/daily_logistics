import { Box, Stack, Typography } from '@mui/material'

import { COLOR_MODULO } from '@/config/marca'
const COLOR_FRENTE = COLOR_MODULO

/**
 * Vista previa del esquema de ejes/llantas de un vehículo.
 * Se dibuja a partir del `layout` (cantidad de llantas por cada eje), así que
 * sirve para cualquier esquema del catálogo y para los que se creen después,
 * sin depender de imágenes fijas. Si el esquema no tiene layout se cae al
 * patrón clásico (eje 1 direccional = 2 llantas, ejes siguientes duales = 4),
 * que es el mismo criterio que usa el backend al generar las posiciones.
 */
export function EsquemaLlantasPreview({
  layout, numeroEjes = 0, tieneRepuesto = false, cantidadRepuestos = 0, nombre,
}: {
  layout?: number[] | null
  numeroEjes?: number
  tieneRepuesto?: boolean
  cantidadRepuestos?: number
  nombre?: string
}) {
  const ejes = layout?.length
    ? layout
    : Array.from({ length: numeroEjes }, (_, i) => (i === 0 ? 2 : 4))
  const totalLlantas = ejes.reduce((a, b) => a + b, 0)
  const repuestos = tieneRepuesto ? Math.max(1, cantidadRepuestos) : 0
  const maxPorLado = Math.max(1, ...ejes.map(n => Math.ceil(n / 2)))

  const Rueda = () => (
    <Box sx={{
      width: 9, height: 15, borderRadius: '3px',
      bgcolor: '#1F2937', border: '1px solid #0F172A', flexShrink: 0,
    }} />
  )

  return (
    <Box sx={{ p: 0.5, minWidth: 190 }}>
      {nombre && (
        <Typography fontSize={11.5} fontWeight={700} sx={{ mb: 0.75, color: '#fff' }}>{nombre}</Typography>
      )}

      <Box sx={{ bgcolor: '#FFFFFF', borderRadius: '8px', p: 1, border: '1px solid #E5E7EB' }}>
        {/* Frente / cabina */}
        <Box sx={{
          mx: 'auto', mb: 0.5, width: 62, height: 14, borderRadius: '7px 7px 3px 3px',
          bgcolor: 'rgba(79, 70, 229, 0.14)', border: `1px solid ${COLOR_FRENTE}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Typography fontSize={6.5} fontWeight={800} color={COLOR_FRENTE} letterSpacing="0.05em">FRENTE</Typography>
        </Box>

        {/* Ejes */}
        <Box sx={{ position: 'relative' }}>
          {/* Chasis */}
          <Box sx={{
            position: 'absolute', left: '50%', top: 2, bottom: 2, width: 6,
            transform: 'translateX(-50%)', bgcolor: '#94A3B8', borderRadius: 1, zIndex: 0,
          }} />
          <Stack spacing={0.6} sx={{ position: 'relative', zIndex: 1, py: 0.25 }}>
            {ejes.map((cantidad, i) => {
              const izq = Math.ceil(cantidad / 2)
              const der = cantidad - izq
              return (
                <Stack key={i} direction="row" alignItems="center" justifyContent="center" spacing={0.4}>
                  <Typography fontSize={6.5} fontWeight={700} color="#64748B" sx={{ width: 26, textAlign: 'right' }}>
                    E{i + 1}
                  </Typography>
                  <Stack direction="row" gap={0.3} sx={{ width: maxPorLado * 11, justifyContent: 'flex-end' }}>
                    {Array.from({ length: izq }, (_, k) => <Rueda key={k} />)}
                  </Stack>
                  <Box sx={{ width: 34, height: 3.5, bgcolor: '#64748B', borderRadius: 1 }} />
                  <Stack direction="row" gap={0.3} sx={{ width: maxPorLado * 11 }}>
                    {Array.from({ length: der }, (_, k) => <Rueda key={k} />)}
                  </Stack>
                  <Box sx={{ width: 26 }} />
                </Stack>
              )
            })}
          </Stack>
        </Box>

        {/* Repuestos */}
        {repuestos > 0 && (
          <Stack direction="row" alignItems="center" justifyContent="center" spacing={0.5}
            sx={{ mt: 0.75, pt: 0.6, borderTop: '1px dashed #CBD5E1' }}>
            <Typography fontSize={6.5} fontWeight={700} color="#64748B">REP.</Typography>
            <Stack direction="row" gap={0.3}>
              {Array.from({ length: repuestos }, (_, k) => <Rueda key={k} />)}
            </Stack>
          </Stack>
        )}
      </Box>

      <Typography fontSize={10} sx={{ mt: 0.6, color: '#E2E8F0' }}>
        {ejes.length} eje(s) · {totalLlantas} llantas{repuestos > 0 ? ` + ${repuestos} repuesto(s)` : ''}
      </Typography>
      <Typography fontSize={9} sx={{ color: '#94A3B8' }}>
        Por eje: {ejes.join(' · ')}
      </Typography>
    </Box>
  )
}
