/**
 * TMS · Motor de costos
 *
 * Era una maqueta: quince viajes con costos escritos a mano, un «Mayor costo»
 * fijo y un «Guardar» que solo mostraba el aviso. Ahora cada viaje trae su
 * desglose real y se registra o corrige desde aquí.
 *
 * Total, margen y costo por kilómetro los calcula el servidor con la distancia
 * actual del viaje. Las vistas por ruta, por conductor y por componente se
 * agrupan aquí a partir de esos viajes: no se guardan en ningún lado.
 */
import React, { useMemo, useState } from 'react'
import {
  Box, Paper, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, IconButton, Stack, Tabs, Tab, Chip, Tooltip, LinearProgress, Alert,
  Table, TableBody, TableCell, TableHead, TableRow, TableContainer, alpha, Divider,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  AttachMoney, TrendingUp, TrendingDown, BarChart, Edit, Add,
  LocalGasStation, Toll, HotelOutlined, WorkOutline, Build, AccountBalance, ArrowForward,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { tmsApi, type ViajeCosto, type ComponentesCosto } from '@/api/tms'

import { COLOR_MODULO } from '@/config/marca'
const TMS_COLOR = COLOR_MODULO
const fmt = (n: number) => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(n)
const fmtPct = (n: number | null | undefined) => (n == null ? '—' : `${n.toFixed(1)}%`)
const margenColor = (pct: number | null | undefined) =>
  pct == null ? 'text.secondary' : pct >= 20 ? 'success.main' : pct >= 10 ? 'warning.main' : 'error.main'

type Clave = keyof Omit<ComponentesCosto, 'notas' | 'valor_flete_cobrado'>
const COMPONENTES: { key: Clave; label: string; icon: React.ReactNode }[] = [
  { key: 'combustible', label: 'Combustible', icon: <LocalGasStation fontSize="small" /> },
  { key: 'peajes', label: 'Peajes', icon: <Toll fontSize="small" /> },
  { key: 'viaticos', label: 'Viáticos', icon: <HotelOutlined fontSize="small" /> },
  { key: 'horas_extras', label: 'Horas extras', icon: <WorkOutline fontSize="small" /> },
  { key: 'mantenimiento', label: 'Mantenimiento', icon: <Build fontSize="small" /> },
  { key: 'costos_indirectos', label: 'Costos indirectos', icon: <AccountBalance fontSize="small" /> },
]

function KPICard({ label, value, sub, icon, color }: { label: string; value: string; sub?: string; icon: React.ReactNode; color: string }) {
  return (
    <Paper elevation={0} sx={{ p: 2.5, border: '1px solid #E2E8F0', borderRadius: 2, height: '100%' }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Box sx={{ minWidth: 0 }}>
          <Typography fontSize={12} color="text.secondary" mb={0.5}>{label}</Typography>
          <Typography variant="h6" fontWeight={700} noWrap>{value}</Typography>
          {sub && <Typography fontSize={11} color="text.secondary" mt={0.3} noWrap>{sub}</Typography>}
        </Box>
        <Box sx={{ bgcolor: alpha(color, 0.1), p: 1, borderRadius: 1.5, color }}>{icon}</Box>
      </Stack>
    </Paper>
  )
}

const primerDiaMes = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10) }
const hoyISO = () => new Date().toISOString().slice(0, 10)
const VACIO: Record<string, string> = { combustible: '', peajes: '', viaticos: '', horas_extras: '', mantenimiento: '', costos_indirectos: '', valor_flete_cobrado: '', notas: '' }

export default function TMSCostos() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [desde, setDesde] = useState(primerDiaMes())
  const [hasta, setHasta] = useState(hoyISO())
  const [editando, setEditando] = useState<ViajeCosto | null>(null)
  const [f, setF] = useState<Record<string, string>>({ ...VACIO })

  const { data: viajes = [], isLoading } = useQuery({
    queryKey: ['tms-costos-lista', desde, hasta],
    queryFn: () => tmsApi.costos({ fecha_desde: desde || undefined, fecha_hasta: hasta || undefined }),
  })
  const conCosto = viajes.filter(v => v.costo)
  const sinCosto = viajes.filter(v => !v.costo && ['ENTREGADO', 'CERRADO', 'EN_TRANSITO'].includes(v.estado))

  const kpi = useMemo(() => {
    const total = conCosto.reduce((s, v) => s + v.costo!.costo_total, 0)
    const km = conCosto.reduce((s, v) => s + (v.distancia_km || 0), 0)
    const flete = conCosto.reduce((s, v) => s + v.costo!.valor_flete_cobrado, 0)
    const mayor = [...conCosto].sort((a, b) => b.costo!.costo_total - a.costo!.costo_total)[0]
    return {
      total, promViaje: conCosto.length ? total / conCosto.length : 0,
      // Por km solo sobre los viajes que tienen distancia: sumar costos de
      // viajes sin distancia inflaría la cifra.
      porKm: km ? conCosto.filter(v => v.distancia_km).reduce((s, v) => s + v.costo!.costo_total, 0) / km : null,
      // Margen ponderado por flete, no promedio de porcentajes: un viaje
      // pequeño con margen alto no debe pesar lo mismo que uno grande.
      margen: flete ? ((flete - total) / flete) * 100 : null,
      mayor,
    }
  }, [conCosto])

  const agrupar = (clave: (v: ViajeCosto) => string) => {
    const m = new Map<string, ViajeCosto[]>()
    conCosto.forEach(v => { const k = clave(v); m.set(k, [...(m.get(k) ?? []), v]) })
    return [...m.entries()].map(([nombre, vs]) => {
      const total = vs.reduce((s, v) => s + v.costo!.costo_total, 0)
      const flete = vs.reduce((s, v) => s + v.costo!.valor_flete_cobrado, 0)
      const km = vs.reduce((s, v) => s + (v.distancia_km || 0), 0)
      return {
        nombre, n: vs.length, total, prom: total / vs.length,
        porKm: km ? vs.filter(v => v.distancia_km).reduce((s, v) => s + v.costo!.costo_total, 0) / km : null,
        margen: flete ? ((flete - total) / flete) * 100 : null,
      }
    }).sort((a, b) => b.total - a.total)
  }
  const rutas = agrupar(v => `${v.origen || '¿?'} → ${v.destino || '¿?'}`)
  const conductores = agrupar(v => v.conductor || 'Sin conductor')
  const porMargen = rutas.filter(r => r.margen != null).sort((a, b) => b.margen! - a.margen!)
  const maxAbs = Math.max(1, ...porMargen.map(r => Math.abs(r.margen!)))
  const totComp = (k: Clave) => conCosto.reduce((s, v) => s + (v.costo![k] || 0), 0)

  const abrir = (v: ViajeCosto) => {
    const c = v.costo
    setF(c ? {
      combustible: String(c.combustible), peajes: String(c.peajes), viaticos: String(c.viaticos),
      horas_extras: String(c.horas_extras), mantenimiento: String(c.mantenimiento),
      costos_indirectos: String(c.costos_indirectos), valor_flete_cobrado: String(c.valor_flete_cobrado),
      notas: c.notas ?? '',
    } : { ...VACIO, valor_flete_cobrado: v.valor_flete != null ? String(v.valor_flete) : '' })
    setEditando(v)
  }
  const n = (k: string) => { const x = Number(f[k]); return Number.isFinite(x) ? x : 0 }
  const negativos = [...COMPONENTES.map(c => c.key), 'valor_flete_cobrado'].some(k => f[k] !== '' && Number(f[k]) < 0)
  const totalForm = COMPONENTES.reduce((s, c) => s + n(c.key), 0)
  const fleteForm = n('valor_flete_cobrado')

  const guardar = useMutation({
    mutationFn: () => {
      const d: ComponentesCosto = {
        combustible: n('combustible'), peajes: n('peajes'), viaticos: n('viaticos'),
        horas_extras: n('horas_extras'), mantenimiento: n('mantenimiento'),
        costos_indirectos: n('costos_indirectos'), valor_flete_cobrado: n('valor_flete_cobrado'),
        notas: f.notas.trim() || null,
      }
      return editando!.costo ? tmsApi.editarCostos(editando!.costo.id, d) : tmsApi.crearCostos(editando!.viaje_id, d)
    },
    onSuccess: () => {
      toast.success(editando?.costo ? 'Costos actualizados' : 'Costos registrados')
      qc.invalidateQueries({ queryKey: ['tms-costos-lista'] })
      setEditando(null)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo guardar'),
  })

  const cab = { bgcolor: '#F8FAFC' }
  return (
    <Layout>
      <Box sx={{ p: 3, minHeight: '100vh' }}>
        <Stack direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'center' }} justifyContent="space-between" gap={2} mb={3}>
          <Stack direction="row" alignItems="center" gap={1.5}>
            <Box sx={{ bgcolor: alpha(TMS_COLOR, 0.1), borderRadius: 2, p: 1, display: 'flex' }}>
              <AttachMoney sx={{ color: TMS_COLOR, fontSize: 28 }} />
            </Box>
            <Box>
              <Typography variant="h5" fontWeight={700}>Motor de Costos TMS</Typography>
              <Typography variant="body2" color="text.secondary">Rentabilidad y análisis de costos por viaje y ruta</Typography>
            </Box>
          </Stack>
          <Stack direction="row" gap={1}>
            <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
            <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
          </Stack>
        </Stack>

        <Grid container spacing={2} mb={3}>
          <Grid size={{ xs: 12, sm: 6, lg: 2.4 }}><KPICard label="Costo total del período" value={fmt(kpi.total)} sub={`${conCosto.length} viajes con costos`} icon={<AttachMoney />} color={TMS_COLOR} /></Grid>
          <Grid size={{ xs: 12, sm: 6, lg: 2.4 }}><KPICard label="Costo promedio / viaje" value={fmt(kpi.promViaje)} icon={<BarChart />} color="#7C3AED" /></Grid>
          <Grid size={{ xs: 12, sm: 6, lg: 2.4 }}><KPICard label="Costo promedio / km" value={kpi.porKm == null ? '—' : fmt(kpi.porKm)} sub="Viajes con distancia" icon={<TrendingUp />} color="#059669" /></Grid>
          <Grid size={{ xs: 12, sm: 6, lg: 2.4 }}><KPICard label="Margen del período" value={fmtPct(kpi.margen)} sub="Sobre el flete cobrado" icon={<TrendingUp />} color={kpi.margen == null ? '#6B7280' : kpi.margen >= 20 ? '#059669' : kpi.margen >= 10 ? '#D97706' : '#DC2626'} /></Grid>
          <Grid size={{ xs: 12, sm: 6, lg: 2.4 }}><KPICard label="Mayor costo" value={kpi.mayor?.codigo ?? '—'} sub={kpi.mayor ? `${kpi.mayor.origen} → ${kpi.mayor.destino}` : undefined} icon={<TrendingDown />} color="#DC2626" /></Grid>
        </Grid>

        {sinCosto.length > 0 && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {sinCosto.length} viaje(s) en tránsito o entregados todavía no tienen costos registrados: sin ellos el margen del período no está completo.
          </Alert>
        )}

        <Paper elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: '1px solid #E2E8F0', px: 2 }}>
            <Tab label={`Por viaje (${viajes.length})`} />
            <Tab label="Por ruta" />
            <Tab label="Análisis de rentabilidad" />
          </Tabs>
          {isLoading && <LinearProgress />}

          {tab === 0 && (
            <Box sx={{ p: 2 }}>
              <TableContainer>
                <Table size="small">
                  <TableHead sx={cab}>
                    <TableRow>
                      <TableCell><b>Código</b></TableCell><TableCell><b>Ruta</b></TableCell><TableCell><b>Conductor</b></TableCell>
                      <TableCell align="right"><b>Flete cobrado</b></TableCell><TableCell align="right"><b>Costo total</b></TableCell>
                      <TableCell align="right"><b>Margen $</b></TableCell><TableCell align="right"><b>Margen %</b></TableCell><TableCell />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {!isLoading && viajes.length === 0 && (
                      <TableRow><TableCell colSpan={8} align="center" sx={{ py: 3, color: 'text.secondary' }}>No hay viajes en el período</TableCell></TableRow>
                    )}
                    {viajes.map(v => (
                      <TableRow key={v.viaje_id} hover>
                        <TableCell><b>{v.codigo}</b><Typography fontSize={10.5} color="text.secondary">{v.estado}</Typography></TableCell>
                        <TableCell>
                          <Stack direction="row" alignItems="center" gap={0.5}>
                            <Typography fontSize={12}>{v.origen || '—'}</Typography>
                            <ArrowForward sx={{ fontSize: 12, color: TMS_COLOR }} />
                            <Typography fontSize={12}>{v.destino || '—'}</Typography>
                          </Stack>
                        </TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{v.conductor || '—'}</TableCell>
                        {v.costo ? (<>
                          <TableCell align="right" sx={{ fontSize: 12 }}>{fmt(v.costo.valor_flete_cobrado)}</TableCell>
                          <TableCell align="right" sx={{ fontSize: 12 }}>{fmt(v.costo.costo_total)}</TableCell>
                          <TableCell align="right" sx={{ fontSize: 12, color: v.costo.margen >= 0 ? 'success.main' : 'error.main' }}>{fmt(v.costo.margen)}</TableCell>
                          <TableCell align="right"><Typography fontSize={12} fontWeight={700} color={margenColor(v.costo.margen_pct)}>{fmtPct(v.costo.margen_pct)}</Typography></TableCell>
                        </>) : (
                          <TableCell colSpan={4} align="center"><Chip size="small" label="Sin costos registrados" /></TableCell>
                        )}
                        <TableCell>
                          <Tooltip title={v.costo ? 'Editar costos' : 'Registrar costos'}>
                            <IconButton size="small" aria-label={`${v.costo ? 'Editar' : 'Registrar'} costos de ${v.codigo}`} onClick={() => abrir(v)}>
                              {v.costo ? <Edit fontSize="small" /> : <Add fontSize="small" />}
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {tab === 1 && (
            <Box sx={{ p: 2 }}>
              <TableContainer>
                <Table size="small">
                  <TableHead sx={cab}>
                    <TableRow>
                      <TableCell><b>Ruta</b></TableCell><TableCell align="center"><b>N.º viajes</b></TableCell>
                      <TableCell align="right"><b>Costo total</b></TableCell><TableCell align="right"><b>Prom./viaje</b></TableCell>
                      <TableCell align="right"><b>Prom./km</b></TableCell><TableCell align="right"><b>Margen %</b></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rutas.length === 0 && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>Sin viajes con costos en el período</TableCell></TableRow>}
                    {rutas.map(r => (
                      <TableRow key={r.nombre} hover>
                        <TableCell><b>{r.nombre}</b></TableCell>
                        <TableCell align="center">{r.n}</TableCell>
                        <TableCell align="right" sx={{ fontSize: 12 }}>{fmt(r.total)}</TableCell>
                        <TableCell align="right" sx={{ fontSize: 12 }}>{fmt(r.prom)}</TableCell>
                        <TableCell align="right" sx={{ fontSize: 12 }}>{r.porKm == null ? '—' : fmt(r.porKm)}</TableCell>
                        <TableCell align="right"><Typography fontSize={12} fontWeight={700} color={margenColor(r.margen)}>{fmtPct(r.margen)}</Typography></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {tab === 2 && (
            <Box sx={{ p: 3 }}>
              {conCosto.length === 0 ? (
                <Typography color="text.secondary">El análisis aparece cuando hay viajes con costos registrados en el período.</Typography>
              ) : (
                <Grid container spacing={3}>
                  {[['Rutas más rentables', porMargen.slice(0, 5), 'success.main'], ['Rutas menos rentables', [...porMargen].reverse().slice(0, 5), 'error.main']].map(([titulo, lista, color]) => (
                    <Grid key={titulo as string} size={{ xs: 12, md: 6 }}>
                      <Typography fontWeight={700} mb={2} color={color as string}>{titulo as string}</Typography>
                      <Stack gap={1}>
                        {(lista as typeof porMargen).map(r => (
                          <Box key={r.nombre}>
                            <Stack direction="row" justifyContent="space-between" mb={0.3}>
                              <Typography fontSize={12}>{r.nombre}</Typography>
                              <Typography fontSize={12} fontWeight={700} color={margenColor(r.margen)}>{fmtPct(r.margen)}</Typography>
                            </Stack>
                            <Box sx={{ bgcolor: '#E5E7EB', borderRadius: 1, height: 8 }}>
                              <Box sx={{ bgcolor: (r.margen ?? 0) >= 0 ? 'success.main' : 'error.main', height: 8, borderRadius: 1, width: `${(Math.abs(r.margen ?? 0) / maxAbs) * 100}%` }} />
                            </Box>
                          </Box>
                        ))}
                      </Stack>
                    </Grid>
                  ))}

                  <Grid size={{ xs: 12 }}>
                    <Divider sx={{ my: 1 }} />
                    <Typography fontWeight={700} mb={2}>Análisis por conductor</Typography>
                    <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2 }}>
                      <Table size="small">
                        <TableHead sx={cab}>
                          <TableRow><TableCell><b>Conductor</b></TableCell><TableCell align="center"><b>N.º viajes</b></TableCell><TableCell align="right"><b>Costo prom./viaje</b></TableCell><TableCell align="right"><b>Margen %</b></TableCell></TableRow>
                        </TableHead>
                        <TableBody>
                          {conductores.map(c => (
                            <TableRow key={c.nombre} hover>
                              <TableCell>{c.nombre}</TableCell><TableCell align="center">{c.n}</TableCell>
                              <TableCell align="right" sx={{ fontSize: 12 }}>{fmt(c.prom)}</TableCell>
                              <TableCell align="right"><Typography fontSize={12} fontWeight={700} color={margenColor(c.margen)}>{fmtPct(c.margen)}</Typography></TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Grid>

                  <Grid size={{ xs: 12 }}>
                    <Typography fontWeight={700} mb={2}>Resumen por componente de costo</Typography>
                    <Grid container spacing={2}>
                      {COMPONENTES.map(cl => (
                        <Grid key={cl.key} size={{ xs: 12, sm: 6, md: 4 }}>
                          <Paper elevation={0} sx={{ p: 2, border: '1px solid #E2E8F0', borderRadius: 2 }}>
                            <Stack direction="row" alignItems="center" gap={1} mb={0.5}>
                              <Box sx={{ color: TMS_COLOR }}>{cl.icon}</Box>
                              <Typography fontSize={13}>{cl.label}</Typography>
                            </Stack>
                            <Typography fontWeight={700} fontSize={16}>{fmt(totComp(cl.key))}</Typography>
                            <Typography fontSize={11} color="text.secondary">{kpi.total ? fmtPct((totComp(cl.key) / kpi.total) * 100) : '—'} del total</Typography>
                          </Paper>
                        </Grid>
                      ))}
                    </Grid>
                  </Grid>
                </Grid>
              )}
            </Box>
          )}
        </Paper>

        <Dialog open={!!editando} onClose={() => setEditando(null)} maxWidth="sm" fullWidth>
          {editando && (<>
            <DialogTitle>{editando.costo ? 'Editar costos' : 'Registrar costos'} — {editando.codigo}</DialogTitle>
            <DialogContent>
              <Typography fontSize={13} color="text.secondary" mb={2}>
                {editando.origen} → {editando.destino}{editando.conductor ? ` · ${editando.conductor}` : ''}
                {editando.distancia_km ? ` · ${editando.distancia_km} km` : ' · sin distancia registrada'}
              </Typography>
              <Grid container spacing={2}>
                {COMPONENTES.map(cl => (
                  <Grid key={cl.key} size={{ xs: 12, sm: 6 }}>
                    <TextField label={cl.label} type="number" fullWidth size="small" value={f[cl.key]}
                      error={f[cl.key] !== '' && Number(f[cl.key]) < 0}
                      onChange={e => setF({ ...f, [cl.key]: e.target.value })}
                      InputProps={{ startAdornment: <Box sx={{ mr: 0.5, color: TMS_COLOR, display: 'flex' }}>{cl.icon}</Box> }} />
                  </Grid>
                ))}
                <Grid size={{ xs: 12 }}>
                  <TextField label="Flete cobrado al cliente" type="number" fullWidth size="small" value={f.valor_flete_cobrado}
                    error={f.valor_flete_cobrado !== '' && Number(f.valor_flete_cobrado) < 0}
                    onChange={e => setF({ ...f, valor_flete_cobrado: e.target.value })} />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField label="Notas" fullWidth size="small" multiline minRows={2} value={f.notas} onChange={e => setF({ ...f, notas: e.target.value })} />
                </Grid>
              </Grid>
              <Divider sx={{ my: 2 }} />
              <Stack direction="row" justifyContent="space-between"><Typography fontWeight={700}>Costo total</Typography><Typography fontWeight={700} color={TMS_COLOR}>{fmt(totalForm)}</Typography></Stack>
              <Stack direction="row" justifyContent="space-between">
                <Typography>Margen</Typography>
                <Typography fontWeight={600} color={fleteForm - totalForm >= 0 ? 'success.main' : 'error.main'}>
                  {fmt(fleteForm - totalForm)}{fleteForm ? ` (${fmtPct(((fleteForm - totalForm) / fleteForm) * 100)})` : ''}
                </Typography>
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setEditando(null)}>Cancelar</Button>
              <Button variant="contained" disabled={negativos || guardar.isPending} onClick={() => guardar.mutate()} sx={{ bgcolor: TMS_COLOR }}>Guardar</Button>
            </DialogActions>
          </>)}
        </Dialog>
      </Box>
    </Layout>
  )
}
