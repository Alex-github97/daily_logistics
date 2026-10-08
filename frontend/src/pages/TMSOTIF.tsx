/**
 * TMS · OTIF (a tiempo y completo)
 *
 * Era una maqueta: treinta viajes, cinco conductores y siete motivos de falla
 * escritos a mano. Ahora sale de los viajes entregados.
 *
 * La puntualidad la calcula el servidor con las fechas. La completitud la
 * confirma una persona —es lo único del indicador que no se deduce— y antes
 * no había dónde hacerlo: por eso el OTIF del tablero salía en cero. Un viaje
 * sin confirmar no cuenta como incompleto; se muestra aparte como pendiente.
 */
import React, { useMemo, useState } from 'react'
import {
  Box, Paper, Typography, Stack, Tabs, Tab, Chip, Button, TextField, Dialog, DialogTitle,
  DialogContent, DialogActions, Table, TableBody, TableCell, TableHead, TableRow, TableContainer,
  alpha, LinearProgress, Alert, ToggleButton, ToggleButtonGroup,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import { CheckCircle, Cancel, HelpOutline, EmojiEvents, Speed, AccessTime, Inventory2 } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { tmsApi, type ViajeOTIF } from '@/api/tms'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO
const fmtPct = (n: number | null) => (n == null ? '—' : `${n.toFixed(1)}%`)
const fmtFecha = (s?: string | null) => (s ? aFecha(s).toLocaleString('es-CO', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—')
const primerDiaMes = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10) }
const hoyISO = () => new Date().toISOString().slice(0, 10)

function nivelServicio(otif: number | null) {
  if (otif == null) return <Chip label="SIN DATOS" size="small" />
  if (otif >= 95) return <Chip label="EXCELENTE" color="success" size="small" />
  if (otif >= 85) return <Chip label="BUENO" color="primary" size="small" />
  if (otif >= 70) return <Chip label="REGULAR" color="warning" size="small" />
  return <Chip label="CRÍTICO" color="error" size="small" />
}
const Estado = ({ v }: { v: boolean | null }) => v == null
  ? <HelpOutline sx={{ fontSize: 18, color: 'text.disabled' }} />
  : v ? <CheckCircle sx={{ fontSize: 18, color: 'success.main' }} /> : <Cancel sx={{ fontSize: 18, color: 'error.main' }} />

/** Tasa sobre los viajes donde el dato se conoce. */
const tasa = (xs: ViajeOTIF[], k: 'on_time' | 'in_full' | 'otif') => {
  const conocidos = xs.filter(x => x[k] != null)
  return conocidos.length ? (conocidos.filter(x => x[k]).length / conocidos.length) * 100 : null
}

export default function TMSOTIF() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [desde, setDesde] = useState(primerDiaMes())
  const [hasta, setHasta] = useState(hoyISO())
  const [confirmando, setConfirmando] = useState<ViajeOTIF | null>(null)
  const [completo, setCompleto] = useState<boolean | null>(true)
  const [motivo, setMotivo] = useState('')

  const filtro = { fecha_desde: desde || undefined, fecha_hasta: hasta || undefined }
  const { data: viajes = [], isLoading } = useQuery({ queryKey: ['tms-otif', desde, hasta], queryFn: () => tmsApi.otif(filtro) })

  const sinConfirmar = viajes.filter(v => v.in_full == null)
  const agrupar = (clave: (v: ViajeOTIF) => string) => {
    const m = new Map<string, ViajeOTIF[]>()
    viajes.forEach(v => { const k = clave(v); m.set(k, [...(m.get(k) ?? []), v]) })
    return [...m.entries()].map(([nombre, vs]) => {
      const retrasos = vs.map(v => v.horas_retraso).filter((h): h is number => h != null)
      return {
        nombre, n: vs.length, ot: tasa(vs, 'on_time'), if_: tasa(vs, 'in_full'), otif: tasa(vs, 'otif'),
        retrasoProm: retrasos.length ? retrasos.reduce((s, h) => s + h, 0) / retrasos.length : null,
        fallas: vs.filter(v => v.otif === false).length,
      }
    }).sort((a, b) => b.n - a.n)
  }
  const porCliente = agrupar(v => v.cliente || 'Sin cliente')
  const porRuta = agrupar(v => `${v.origen || '¿?'} → ${v.destino || '¿?'}`)
  const porConductor = agrupar(v => v.conductor || 'Sin conductor')
  const motivos = useMemo(() => {
    const m = new Map<string, number>()
    viajes.filter(v => v.in_full === false && v.motivo).forEach(v => m.set(v.motivo!, (m.get(v.motivo!) ?? 0) + 1))
    return [...m.entries()].map(([motivo, n]) => ({ motivo, n })).sort((a, b) => b.n - a.n)
  }, [viajes])
  const tarde = viajes.filter(v => v.on_time === false)

  const confirmar = useMutation({
    mutationFn: () => tmsApi.confirmarInFull(confirmando!.viaje_id, completo, completo === false ? motivo.trim() : null),
    onSuccess: () => {
      toast.success('Entrega confirmada')
      qc.invalidateQueries({ queryKey: ['tms-otif'] })
      qc.invalidateQueries({ queryKey: ['tms-dashboard'] })
      setConfirmando(null)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo guardar'),
  })
  const abrir = (v: ViajeOTIF) => { setConfirmando(v); setCompleto(v.in_full ?? true); setMotivo(v.motivo ?? '') }

  const Tarjeta = ({ label, valor, icon, color, sub }: { label: string; valor: string; icon: React.ReactNode; color: string; sub?: string }) => (
    <Paper elevation={0} sx={{ p: 2.5, border: '1px solid #E2E8F0', borderRadius: 2, height: '100%' }}>
      <Stack direction="row" justifyContent="space-between">
        <Box><Typography fontSize={12} color="text.secondary">{label}</Typography><Typography variant="h5" fontWeight={800} color={color}>{valor}</Typography>
          {sub && <Typography fontSize={11} color="text.secondary">{sub}</Typography>}</Box>
        <Box sx={{ color, opacity: 0.8 }}>{icon}</Box>
      </Stack>
    </Paper>
  )
  const TablaGrupo = ({ filas, titulo }: { filas: ReturnType<typeof agrupar>; titulo: string }) => (
    <TableContainer>
      <Table size="small">
        <TableHead sx={{ bgcolor: '#F8FAFC' }}>
          <TableRow><TableCell><b>{titulo}</b></TableCell><TableCell align="center"><b>Viajes</b></TableCell><TableCell align="right"><b>A tiempo</b></TableCell>
            <TableCell align="right"><b>Completo</b></TableCell><TableCell align="right"><b>OTIF</b></TableCell><TableCell align="right"><b>Retraso prom.</b></TableCell><TableCell><b>Nivel</b></TableCell></TableRow>
        </TableHead>
        <TableBody>
          {filas.length === 0 && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>Sin viajes entregados en el período</TableCell></TableRow>}
          {filas.map(r => (
            <TableRow key={r.nombre} hover>
              <TableCell>{r.nombre}</TableCell><TableCell align="center">{r.n}</TableCell>
              <TableCell align="right">{fmtPct(r.ot)}</TableCell><TableCell align="right">{fmtPct(r.if_)}</TableCell>
              <TableCell align="right"><b>{fmtPct(r.otif)}</b></TableCell>
              <TableCell align="right">{r.retrasoProm == null ? '—' : `${r.retrasoProm > 0 ? '+' : ''}${r.retrasoProm.toFixed(1)} h`}</TableCell>
              <TableCell>{nivelServicio(r.otif)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )

  const otif = tasa(viajes, 'otif')
  return (
    <Layout>
      <Box sx={{ p: 3 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} gap={2} mb={3}>
          <Box>
            <Typography variant="h5" fontWeight={700}>OTIF · Nivel de servicio</Typography>
            <Typography variant="body2" color="text.secondary">Entregas a tiempo y completas, sobre los viajes entregados</Typography>
          </Box>
          <Stack direction="row" gap={1}>
            <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
            <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
          </Stack>
        </Stack>

        <Grid container spacing={2} mb={3}>
          <Grid size={{ xs: 6, md: 3 }}><Tarjeta label="OTIF" valor={fmtPct(otif)} icon={<EmojiEvents />} color={TMS_COLOR} sub={`${viajes.length} viajes entregados`} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Tarjeta label="A tiempo" valor={fmtPct(tasa(viajes, 'on_time'))} icon={<AccessTime />} color="#0369A1" sub={`${tarde.length} tarde`} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Tarjeta label="Completo" valor={fmtPct(tasa(viajes, 'in_full'))} icon={<Inventory2 />} color="#7C3AED" sub={`${sinConfirmar.length} sin confirmar`} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Paper elevation={0} sx={{ p: 2.5, border: '1px solid #E2E8F0', borderRadius: 2, height: '100%' }}>
            <Typography fontSize={12} color="text.secondary" mb={1}>Nivel de servicio</Typography>{nivelServicio(otif)}
            <Stack direction="row" alignItems="center" gap={0.5} mt={1}><Speed sx={{ fontSize: 16, color: 'text.secondary' }} /><Typography fontSize={11} color="text.secondary">Meta de referencia: 95 %</Typography></Stack>
          </Paper></Grid>
        </Grid>

        {sinConfirmar.length > 0 && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {sinConfirmar.length} entrega(s) sin confirmar si llegaron completas. No cuentan en el indicador hasta que alguien las confirme en la pestaña «Viajes».
          </Alert>
        )}

        <Paper elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ borderBottom: '1px solid #E2E8F0', px: 2 }}>
            <Tab label={`Viajes (${viajes.length})`} /><Tab label="Por cliente" /><Tab label="Por ruta" /><Tab label="Por conductor" /><Tab label="Causas de falla" />
          </Tabs>
          {isLoading && <LinearProgress />}
          <Box sx={{ p: 2 }}>
            {tab === 0 && (
              <TableContainer>
                <Table size="small">
                  <TableHead sx={{ bgcolor: '#F8FAFC' }}>
                    <TableRow><TableCell><b>Viaje</b></TableCell><TableCell><b>Cliente</b></TableCell><TableCell><b>Ruta</b></TableCell>
                      <TableCell><b>Programada</b></TableCell><TableCell><b>Real</b></TableCell><TableCell align="center"><b>A tiempo</b></TableCell>
                      <TableCell align="center"><b>Completo</b></TableCell><TableCell><b>Motivo</b></TableCell><TableCell /></TableRow>
                  </TableHead>
                  <TableBody>
                    {!isLoading && viajes.length === 0 && <TableRow><TableCell colSpan={9} align="center" sx={{ py: 3, color: 'text.secondary' }}>No hay viajes entregados en el período</TableCell></TableRow>}
                    {viajes.map(v => (
                      <TableRow key={v.viaje_id} hover>
                        <TableCell><b>{v.codigo}</b></TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{v.cliente || '—'}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{v.origen} → {v.destino}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{fmtFecha(v.fecha_programada)}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{fmtFecha(v.fecha_real)}
                          {v.horas_retraso != null && v.horas_retraso > 0 && <Typography fontSize={10.5} color="error.main">+{v.horas_retraso.toFixed(1)} h</Typography>}</TableCell>
                        <TableCell align="center"><Estado v={v.on_time} /></TableCell>
                        <TableCell align="center"><Estado v={v.in_full} /></TableCell>
                        <TableCell sx={{ fontSize: 12, maxWidth: 200 }}>{v.motivo || '—'}</TableCell>
                        <TableCell>
                          <Button size="small" variant={v.in_full == null ? 'contained' : 'text'} onClick={() => abrir(v)}
                            sx={v.in_full == null ? { bgcolor: TMS_COLOR } : { color: TMS_COLOR }}>
                            {v.in_full == null ? 'Confirmar' : 'Cambiar'}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            {tab === 1 && <TablaGrupo filas={porCliente} titulo="Cliente" />}
            {tab === 2 && <TablaGrupo filas={porRuta} titulo="Ruta" />}
            {tab === 3 && <TablaGrupo filas={porConductor} titulo="Conductor" />}
            {tab === 4 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography fontWeight={700} mb={1.5}>Qué faltó en las entregas incompletas</Typography>
                  {motivos.length === 0 ? <Typography fontSize={13} color="text.secondary">Ninguna entrega registrada como incompleta.</Typography> : (
                    <Stack gap={1}>{motivos.map(m => (
                      <Box key={m.motivo}>
                        <Stack direction="row" justifyContent="space-between"><Typography fontSize={13}>{m.motivo}</Typography><Typography fontSize={13} fontWeight={700}>{m.n}</Typography></Stack>
                        <Box sx={{ height: 6, borderRadius: 3, bgcolor: '#E5E7EB' }}><Box sx={{ height: 6, borderRadius: 3, bgcolor: '#DC2626', width: `${(m.n / motivos[0].n) * 100}%` }} /></Box>
                      </Box>
                    ))}</Stack>
                  )}
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography fontWeight={700} mb={1.5}>Entregas tarde ({tarde.length})</Typography>
                  {tarde.length === 0 ? <Typography fontSize={13} color="text.secondary">Todas las entregas del período llegaron a tiempo.</Typography> : (
                    <Stack gap={0.75}>{[...tarde].sort((a, b) => (b.horas_retraso ?? 0) - (a.horas_retraso ?? 0)).slice(0, 10).map(v => (
                      <Stack key={v.viaje_id} direction="row" justifyContent="space-between" sx={{ py: 0.5, borderBottom: '1px solid #F1F5F9' }}>
                        <Typography fontSize={13}>{v.codigo} · {v.destino}</Typography>
                        <Typography fontSize={13} fontWeight={700} color="error.main">+{(v.horas_retraso ?? 0).toFixed(1)} h</Typography>
                      </Stack>
                    ))}</Stack>
                  )}
                  <Typography fontSize={11} color="text.secondary" mt={1}>Las causas de un retraso se registran como novedades en el tracking del viaje.</Typography>
                </Grid>
              </Grid>
            )}
          </Box>
        </Paper>

        <Dialog open={!!confirmando} onClose={() => setConfirmando(null)} maxWidth="xs" fullWidth>
          <DialogTitle>¿La entrega llegó completa? — {confirmando?.codigo}</DialogTitle>
          <DialogContent>
            <ToggleButtonGroup exclusive fullWidth size="small" value={completo} onChange={(_, v) => v !== undefined && setCompleto(v)} sx={{ my: 1 }}>
              <ToggleButton value={true} color="success">Completa</ToggleButton>
              <ToggleButton value={false} color="error">Incompleta</ToggleButton>
            </ToggleButtonGroup>
            {completo === false && (
              <TextField label="Qué faltó" required fullWidth size="small" multiline minRows={2} sx={{ mt: 1 }} value={motivo} onChange={e => setMotivo(e.target.value)}
                helperText="Por ejemplo: faltante en picking, avería de 3 cajas, pedido parcial" />
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmando(null)}>Cancelar</Button>
            <Button variant="contained" disabled={completo == null || (completo === false && !motivo.trim()) || confirmar.isPending}
              onClick={() => confirmar.mutate()} sx={{ bgcolor: TMS_COLOR }}>Confirmar</Button>
          </DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
