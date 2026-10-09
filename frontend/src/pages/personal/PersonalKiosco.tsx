/**
 * WFM · Kiosco de marcación: un equipo a la entrada de la bodega (con sesión de
 * supervisor) con un lector. La persona escanea su carné: si no tiene jornada
 * abierta, marca la entrada (en su estación programada); si la tiene, la salida.
 */
import { useEffect, useRef, useState } from 'react'
import { Box, Paper, Stack, Typography, alpha } from '@mui/material'
import { Badge, Login, Logout, ErrorOutline } from '@mui/icons-material'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { errorApi } from '@/components/comun/Registro'
import { minutos } from '@/api/tareasBodega'
import { personal } from '@/api/personal'

const COLOR = '#0D9488'
type Resultado = { ok: true; accion: 'ENTRADA' | 'SALIDA'; persona: string; estacion: string | null; minutos?: number; hora: string } | { ok: false; error: string; hora: string }

export default function PersonalKiosco() {
  const [carne, setCarne] = useState('')
  const [res, setRes] = useState<Resultado | null>(null)
  const [hora, setHora] = useState(new Date())
  const campo = useRef<HTMLInputElement>(null)
  useEffect(() => { const t = setInterval(() => setHora(new Date()), 1000); return () => clearInterval(t) }, [])
  useEffect(() => { campo.current?.focus() })
  useEffect(() => { if (!res) return; const t = setTimeout(() => setRes(null), 6000); return () => clearTimeout(t) }, [res])

  const marcar = async (c: string) => {
    const h = new Date().toLocaleTimeString('es-CO', { timeStyle: 'short' })
    try {
      const r = await personal.marcar(c)
      setRes({ ok: true, accion: r.accion, persona: r.persona, estacion: r.estacion, minutos: r.accion === 'SALIDA' ? r.jornada.minutos : undefined, hora: h })
    } catch (e) { setRes({ ok: false, error: errorApi(e, 'No se pudo marcar'), hora: h }) }
    setCarne('')
  }

  const c = !res ? COLOR : !res.ok ? '#DC2626' : res.accion === 'ENTRADA' ? '#10B981' : '#2563EB'
  return (
    <Layout title="Personal — Kiosco">
      <Box sx={{ p: 3, maxWidth: 760, mx: 'auto' }} onClick={() => campo.current?.focus()}>
        <Paper variant="outlined" sx={{ p: 4, borderRadius: 4, textAlign: 'center' }}>
          <Typography sx={{ fontSize: 56, fontWeight: 800, fontFamily: 'Consolas, monospace', lineHeight: 1 }}>
            {hora.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}</Typography>
          <Typography color="text.secondary" sx={{ textTransform: 'capitalize', mb: 3 }}>{hora.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' })}</Typography>
          <Box sx={{ p: 3, borderRadius: 3, bgcolor: alpha(c, 0.08), border: `2px solid ${alpha(c, 0.4)}`, minHeight: 170, display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all .2s' }}>
            {!res ? <Stack alignItems="center" gap={1}><Badge sx={{ fontSize: 56, color: COLOR }} />
              <Typography fontSize={22} fontWeight={800}>Escanee su carné</Typography>
              <Typography color="text.secondary">Para marcar la entrada o la salida</Typography></Stack>
              : !res.ok ? <Stack alignItems="center" gap={1}><ErrorOutline sx={{ fontSize: 56, color: c }} />
                <Typography fontSize={22} fontWeight={800} color={c}>{res.error}</Typography></Stack>
              : <Stack alignItems="center" gap={0.5}>
                {res.accion === 'ENTRADA' ? <Login sx={{ fontSize: 56, color: c }} /> : <Logout sx={{ fontSize: 56, color: c }} />}
                <Typography fontSize={15} fontWeight={800} color={c} letterSpacing="0.1em">{res.accion === 'ENTRADA' ? 'ENTRADA' : 'SALIDA'} · {res.hora}</Typography>
                <Typography fontSize={30} fontWeight={800}>{res.accion === 'ENTRADA' ? '¡Bienvenido, ' : 'Hasta luego, '}{res.persona.split(' ')[0]}!</Typography>
                <Typography fontSize={16} color="text.secondary">{res.accion === 'ENTRADA' ? (res.estacion ? `Estación: ${res.estacion}` : 'Sin estación asignada: avise a su supervisor')
                  : `Jornada de ${minutos(res.minutos)}`}</Typography>
              </Stack>}
          </Box>
          <TextField inputRef={campo} fullWidth autoComplete="off" label="Carné" value={carne} onChange={e => setCarne(e.target.value)} sx={{ mt: 3 }}
            onKeyDown={e => { if (e.key === 'Enter' && carne.trim()) marcar(carne.trim()) }}
            inputProps={{ style: { fontFamily: 'Consolas, monospace', fontSize: 22, textAlign: 'center' } }} />
        </Paper>
      </Box>
    </Layout>
  )
}
