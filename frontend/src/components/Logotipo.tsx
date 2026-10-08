/**
 * Logotipo de Daily Logistics: un distintivo (ruta con dos paradas) y el nombre.
 *
 * Se dibuja en SVG + texto para que escale sin perder nitidez y se adapte al
 * fondo sobre el que va.
 */
import { Box, Typography } from '@mui/material'
import { ACENTO, DESTELLO, MARCA, PALETA } from '@/config/marca'

export function Distintivo({ tamano = 32, claro = false }: { tamano?: number; claro?: boolean }) {
  return (
    <Box
      component="svg"
      viewBox="0 0 40 40"
      sx={{ width: tamano, height: tamano, flexShrink: 0, display: 'block' }}
    >
      <defs>
        <linearGradient id="dl-distintivo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4F46E5" />
          <stop offset="0.55" stopColor="#7C3AED" />
          <stop offset="1" stopColor="#06B6D4" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="40" height="40" rx="11" fill="url(#dl-distintivo)" />
      <path
        d="M10 28 C 10 18, 30 22, 30 12"
        fill="none" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round"
        strokeDasharray="0.1 6"
      />
      <circle cx="10" cy="28" r="4" fill="#FFFFFF" />
      <circle cx="30" cy="12" r="4.5" fill={DESTELLO.base} />
    </Box>
  )
}

export function Logotipo({
  tamano = 22, conLema = false, claro = false, soloTexto = false,
}: {
  /** Altura de las letras, en píxeles. */
  tamano?: number
  conLema?: boolean
  /** Para fondos oscuros. */
  claro?: boolean
  soloTexto?: boolean
}) {
  const color = claro ? '#FFFFFF' : PALETA.tinta
  const [uno, dos] = MARCA.logotipo.split(' ')

  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: tamano * 0.45 + 'px' }}>
      {!soloTexto && <Distintivo tamano={tamano * 1.6} claro={claro} />}
      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
        <Typography
          component="span"
          sx={{
            fontFamily: '"Plus Jakarta Sans", sans-serif',
            fontWeight: 800,
            fontSize: tamano,
            letterSpacing: '-0.03em',
            lineHeight: 1,
            color,
            whiteSpace: 'nowrap',
          }}
        >
          {uno}
          <Box component="span" sx={{ fontWeight: 400, color: claro ? ACENTO.claro : ACENTO.base }}>
            {dos}
          </Box>
          <Box component="span" sx={{ color: DESTELLO.base }}>.</Box>
        </Typography>
        {conLema && (
          <Typography
            component="span"
            sx={{
              mt: 0.6, fontSize: Math.max(9, tamano * 0.42), fontWeight: 600,
              letterSpacing: '0.12em', textTransform: 'uppercase',
              color: claro ? 'rgba(255,255,255,0.6)' : PALETA.acero, whiteSpace: 'nowrap',
            }}
          >
            {MARCA.lema}
          </Typography>
        )}
      </Box>
    </Box>
  )
}
