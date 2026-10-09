/**
 * WFM · Productividad: por persona y periodo — horas en jornada, pausas, tiempo
 * en tareas, tiempo sin tarea, utilización y tareas por hora —, horas por
 * estación y el detalle de cada jornada (pausas y estaciones por las que pasó).
 */
import { useMemo, useState } from 'react'
import {
  Alert, Box, Chip, LinearProgress, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import { Insights } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, Cifra } from '@/components/comun/Registro'
import { wms } from '@/api/wmsTrazable'
import { minutos, MOTIVOS_PAUSA, TIPO_TAREA } from '@/api/tareasBodega'
import { personal } from '@/api/personal'
import { aFecha } from '@/utils/fechas'

const COLOR = '#0D9488'
const hoyISO = (d = 0) => { const x = new Date(); x.setDate(x.getDate() + d); return x.toLocaleDateString('en-CA') }

function Barra({ productivo, pausa, total }: { productivo: number; pausa: number; total: number }) {
  const t = Math.max(1, total)
  return (
    <Tooltip title={`En tareas ${minutos(productivo)} · pausas ${minutos(pausa)} · sin tarea ${minutos(Math.max(0, total - productivo - pausa))}`}>
      <Box sx={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', bgcolor: '#E2E8F0', minWidth: 140 }}>
        <Box sx={{ width: `${(productivo / t) * 100}%`, bgcolor: '#10B981' }} />
        <Box sx={{ width: `${(pausa / t) * 100}%`, bgcolor: '#F59E0B' }} />
      </Box>
    </Tooltip>
  )
}
const th = { fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC', whiteSpace: 'nowrap' as const }

export default function PersonalProductividad() {
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  const [desde, setDesde] = useState(hoyISO(-7))
  const [hasta, setHasta] = useState(hoyISO())
  const p = { almacen_id: almacen || undefined, desde, hasta }
  const prod = useQuery({ queryKey: ['wfm-productividad', p], queryFn: () => personal.productividad(p) })
  const jornadas = useQuery({ queryKey: ['wfm-jornadas', p], queryFn: () => personal.jornadas(p) })
  const tot = useMemo(() => {
    const r = prod.data?.personas ?? []
    const min = r.reduce((s, x) => s + x.minutos, 0), pausa = r.reduce((s, x) => s + x.pausa_min, 0), productivo = r.reduce((s, x) => s + x.productivo_min, 0)
    const tareas = r.reduce((s, x) => s + x.tareas, 0)
    return { horas: min / 60, pausa, productivo, tareas, util: min - pausa > 0 ? productivo / (min - pausa) * 100 : null, th: min - pausa >= 1 ? tareas / ((min - pausa) / 60) : null }
  }, [prod.data])

  return (
    <Layout title="Personal — Productividad">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Insights sx={{ fontSize: 28 }} />} titulo="Productividad del personal" color={COLOR}
          subtitulo="Jornadas, pausas, tiempo en tareas, utilización y horas por estación" />
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 220 }}>
            <MenuItem value="">Todos</MenuItem>{(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
        </Stack>
        <Grid container spacing={1.5} mb={2}>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Horas en jornada" valor={tot.horas.toLocaleString('es-CO', { maximumFractionDigits: 1 })} color={COLOR} /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Tiempo en tareas" valor={minutos(tot.productivo)} color="#10B981" /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="En pausas" valor={minutos(tot.pausa)} color="#F59E0B" /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Utilización" valor={tot.util == null ? '—' : `${Math.round(tot.util)}%`} color="#2563EB" sub="en tareas ÷ (jornada − pausas)" /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Tareas por hora" valor={tot.th == null ? '—' : tot.th.toLocaleString('es-CO', { maximumFractionDigits: 1 })} color="#7C3AED" sub={`${tot.tareas} tareas`} /></Grid>
        </Grid>

        <Grid container spacing={2} mb={3}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Typography fontWeight={800} mb={1}>Por persona</Typography>
            {prod.isLoading ? <LinearProgress /> : !prod.data?.personas.length ? <Alert severity="info">Sin jornadas en el periodo.</Alert> :
              <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
                <Table size="small">
                  <TableHead><TableRow>{['Persona', 'Jornadas', 'Horas', 'Distribución', 'Utilización', 'Tareas', 'Tareas/h', 'Por tipo'].map(h => <TableCell key={h} sx={th}>{h}</TableCell>)}</TableRow></TableHead>
                  <TableBody>{prod.data.personas.map(r => (
                    <TableRow key={r.usuario_id} hover>
                      <TableCell sx={{ fontWeight: 700 }}>{r.persona}</TableCell><TableCell>{r.jornadas}</TableCell>
                      <TableCell>{r.horas.toLocaleString('es-CO', { maximumFractionDigits: 1 })}</TableCell>
                      <TableCell><Barra productivo={r.productivo_min} pausa={r.pausa_min} total={r.minutos} /></TableCell>
                      <TableCell>{r.utilizacion_pct == null ? '—' : `${Math.round(r.utilizacion_pct)}%`}</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>{r.tareas}</TableCell><TableCell>{r.tareas_hora ?? '—'}</TableCell>
                      <TableCell>{Object.entries(r.por_tipo).map(([k, v]) => <Chip key={k} size="small" label={`${TIPO_TAREA[k] ?? k} ${v}`} sx={{ mr: 0.5, height: 20, fontSize: 11 }} />)}</TableCell>
                    </TableRow>))}</TableBody>
                </Table>
              </Paper>}
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Typography fontWeight={800} mb={1}>Por estación</Typography>
            {!prod.data?.estaciones.length ? <Alert severity="info">Sin datos.</Alert> :
              <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
                <Table size="small">
                  <TableHead><TableRow>{['Estación', 'Horas', 'Personas'].map(h => <TableCell key={h} sx={th}>{h}</TableCell>)}</TableRow></TableHead>
                  <TableBody>{prod.data.estaciones.map(e => (
                    <TableRow key={e.estacion_id ?? 0} hover><TableCell sx={{ fontWeight: 600 }}>{e.estacion}</TableCell>
                      <TableCell>{e.horas.toLocaleString('es-CO', { maximumFractionDigits: 1 })}</TableCell><TableCell>{e.personas}</TableCell></TableRow>))}</TableBody>
                </Table>
              </Paper>}
          </Grid>
        </Grid>

        <Typography fontWeight={800} mb={1}>Jornadas</Typography>
        {jornadas.isLoading ? <LinearProgress /> : !jornadas.data?.length ? <Alert severity="info">Sin jornadas en el periodo.</Alert> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['Persona', 'Estado', 'Inicio', 'Fin', 'Duración', 'Distribución', 'Estaciones', 'Pausas', 'Tareas', 'Utilización', 'Marcó'].map(h => <TableCell key={h} sx={th}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{jornadas.data.map(j => {
                const c = j.estado === 'CERRADA' ? '#64748B' : j.estado === 'ACTIVA' ? '#10B981' : '#F59E0B'
                return (
                  <TableRow key={j.id} hover>
                    <TableCell sx={{ fontWeight: 700 }}>{j.persona}</TableCell>
                    <TableCell><Chip size="small" label={j.estado === 'CERRADA' && j.cierre_auto ? 'Cerrada sola' : j.estado.toLowerCase()} sx={{ bgcolor: alpha(c, 0.12), color: c, fontWeight: 700, height: 20, textTransform: 'capitalize' }} /></TableCell>
                    <TableCell sx={{ fontSize: 12.5, whiteSpace: 'nowrap' }}>{aFecha(j.inicio).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{j.fin ? aFecha(j.fin).toLocaleTimeString('es-CO', { timeStyle: 'short' }) : '—'}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{minutos(j.minutos)}</TableCell>
                    <TableCell><Barra productivo={j.productivo_min} pausa={j.pausa_min} total={j.minutos} /></TableCell>
                    <TableCell sx={{ fontSize: 12 }}>{j.tramos.length ? j.tramos.map((t, i) => <div key={i}>{t.estacion ?? 'Sin estación'} · {minutos(t.min)}</div>) : (j.estacion ?? '—')}</TableCell>
                    <TableCell sx={{ fontSize: 12 }}>{j.pausas.length ? j.pausas.map((p, i) => <div key={i}>{MOTIVOS_PAUSA[p.motivo] ?? p.motivo} · {minutos(p.min)}</div>) : '—'}</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>{j.tareas}</TableCell>
                    <TableCell>{j.utilizacion_pct == null ? '—' : `${Math.round(j.utilizacion_pct)}%`}</TableCell>
                    <TableCell sx={{ fontSize: 12 }}>{j.origen === 'KIOSCO' ? 'Kiosco' : j.origen === 'APP' ? 'Su equipo' : '—'}</TableCell>
                  </TableRow>
                )
              })}</TableBody>
            </Table>
          </Paper>}
      </Box>
    </Layout>
  )
}
