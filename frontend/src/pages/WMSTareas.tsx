/**
 * WMS · Tareas de bodega (tablero del supervisor)
 *
 * - Por aprobar: los reabastecimientos que nacen de los frentes bajo el
 *   mínimo; se aprueban (en lote) o se rechazan con motivo.
 * - En operación: la cola, lo asignado y lo que está en curso, con quién y
 *   desde cuándo; alerta si una tarea lleva demasiado. Se reasigna o cancela.
 * - Operarios: quién está en jornada, en pausa o sin tarea.
 * - Historial: lo terminado, cancelado o rechazado.
 * Las personas trabajan desde Personal › Mi turno (módulo WFM): el sistema les
 * asigna la tarea según su estación.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, LinearProgress, MenuItem,
  Paper, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import { AssignmentTurnedIn, Check, Close, SwapHoriz, Refresh, WarningAmber, Bolt, Storefront, PhoneAndroid } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, Cifra, errorApi } from '@/components/comun/Registro'
import { wms, fechaHora, num } from '@/api/wmsTrazable'
import { bodega, minutos, ESTADO_TAREA, MOTIVOS_PAUSA, TIPO_TAREA, type TareaOp } from '@/api/tareasBodega'
import { personal } from '@/api/personal'
import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

const COLOR = COLOR_MODULO

function Ruta({ t }: { t: TareaOp }) {
  return (
    <Box sx={{ fontFamily: 'Consolas, monospace', fontSize: 12.5 }}>
      {t.origen ?? '—'} → <b>{t.destino ?? t.sugerida ?? 'sin sugerencia'}</b>
      {t.motivo_desvio && <Typography fontSize={11} color="#7C3AED">Sugerida {t.sugerida}: {t.motivo_desvio}</Typography>}
    </Box>
  )
}

export default function WMSTareas() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const [tab, setTab] = useState(0)
  const p = { almacen_id: almacen || undefined }
  const porAprobar = useQuery({ queryKey: ['tareas-op', 'aprobar', almacen], enabled: !!almacen, refetchInterval: 15_000,
    queryFn: () => bodega.tareas({ ...p, estado: 'POR_APROBAR', limite: 500 }) })
  const abiertas = useQuery({ queryKey: ['tareas-op', 'abiertas', almacen], enabled: !!almacen, refetchInterval: 15_000,
    queryFn: () => bodega.tareas({ ...p, estado: 'PENDIENTE,ASIGNADA,EN_CURSO', limite: 500 }) })
  const historial = useQuery({ queryKey: ['tareas-op', 'historial', almacen], enabled: !!almacen, refetchInterval: 60_000,
    queryFn: () => bodega.tareas({ ...p, estado: 'COMPLETADA,CANCELADA,RECHAZADA', limite: 300 }) })
  const jornadas = useQuery({ queryKey: ['jornadas-abiertas', almacen], enabled: !!almacen, refetchInterval: 15_000,
    queryFn: () => personal.jornadas({ ...p, abiertas: true }) })
  const cfg = useQuery({ queryKey: ['config-tareas', almacen], enabled: !!almacen, queryFn: () => bodega.config(Number(almacen)) })
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set())
  const [rechazar, setRechazar] = useState<TareaOp | null>(null)
  const [cancelar, setCancelar] = useState<TareaOp | null>(null)
  const [reasignar, setReasignar] = useState<TareaOp | null>(null)
  const [motivo, setMotivo] = useState('')
  const [operario, setOperario] = useState<number | ''>('')
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['tareas-op'] }); qc.invalidateQueries({ queryKey: ['jornadas-abiertas'] }); qc.invalidateQueries({ queryKey: ['frentes'] }) }
  const hacer = async (f: () => Promise<unknown>, ok: string) => { try { await f(); toast.success(ok); refrescar() } catch (e) { toast.error(errorApi(e)) } }

  const alerta = cfg.data?.alerta_en_curso_min ?? 30
  const kpi = useMemo(() => {
    const h = historial.data ?? [], hoy = new Date().toDateString()
    const hechasHoy = h.filter(t => t.estado === 'COMPLETADA' && t.terminada && aFecha(t.terminada).toDateString() === hoy)
    const ejec = h.map(t => t.ejecucion_min).filter((v): v is number => v != null)
    const conSug = h.filter(t => t.estado === 'COMPLETADA' && t.sugerida)
    const ab = abiertas.data ?? []
    return {
      cola: ab.filter(t => t.estado === 'PENDIENTE').length, curso: ab.filter(t => t.estado !== 'PENDIENTE').length,
      lentas: ab.filter(t => (t.en_curso_min ?? 0) > alerta).length, hoy: hechasHoy.length,
      ejec: ejec.length ? ejec.reduce((a, b) => a + b, 0) / ejec.length : null,
      desvio: conSug.length ? conSug.filter(t => t.motivo_desvio).length / conSug.length * 100 : null,
    }
  }, [historial.data, abiertas.data, alerta])
  const enJornada = (jornadas.data ?? []).filter(j => j.estado === 'ACTIVA')

  const aprobarMarcadas = () => hacer(async () => { await bodega.aprobar([...marcadas]); setMarcadas(new Set()) }, `${marcadas.size} aprobada(s): pasan a la cola`)

  return (
    <Layout title="WMS — Tareas">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<AssignmentTurnedIn sx={{ fontSize: 28 }} />} titulo="Tareas de bodega" color={COLOR}
          subtitulo="Reabastecimiento, ubicación y reubicación dirigidos: el sistema asigna, el operario escanea, aquí se supervisa" />
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap" alignItems="center">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => { setAlmacen(Number(e.target.value)); setMarcadas(new Set()) }} sx={{ minWidth: 240 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <Box flex={1} />
          <Button startIcon={<Bolt />} onClick={async () => {
            try { const r = await bodega.evaluar(Number(almacen)); toast.success(r.creadas.length ? `${r.creadas.length} reabastecimiento(s) creados` : 'Todos los frentes están cubiertos'); refrescar() }
            catch (e) { toast.error(errorApi(e)) }
          }}>Evaluar frentes</Button>
          <Button startIcon={<Storefront />} onClick={() => navigate('/wms/frentes')}>Frentes de picking</Button>
          <Button variant="contained" startIcon={<PhoneAndroid />} onClick={() => navigate('/personal')} sx={{ bgcolor: COLOR }}>Personal en operación</Button>
        </Stack>
        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          <Grid size={{ xs: 6, md: 12 / 7 }}><Cifra etiqueta="Por aprobar" valor={porAprobar.data?.length ?? 0} color="#9333EA" /></Grid>
          <Grid size={{ xs: 6, md: 12 / 7 }}><Cifra etiqueta="En cola" valor={kpi.cola} color="#D97706" /></Grid>
          <Grid size={{ xs: 6, md: 12 / 7 }}><Cifra etiqueta="Asignadas / en curso" valor={kpi.curso} color="#2563EB" sub={kpi.lentas ? `${kpi.lentas} pasan de ${alerta} min` : undefined} /></Grid>
          <Grid size={{ xs: 6, md: 12 / 7 }}><Cifra etiqueta="Completadas hoy" valor={kpi.hoy} color="#15803D" /></Grid>
          <Grid size={{ xs: 6, md: 12 / 7 }}><Cifra etiqueta="Operarios trabajando" valor={`${enJornada.length} / ${jornadas.data?.length ?? 0}`} color="#0891B2" sub="activos / en jornada" /></Grid>
          <Grid size={{ xs: 6, md: 12 / 7 }}><Cifra etiqueta="Tiempo medio" valor={kpi.ejec == null ? '—' : minutos(kpi.ejec)} color={COLOR} /></Grid>
          <Grid size={{ xs: 6, md: 12 / 7 }}><Cifra etiqueta="No fue a la sugerida" valor={kpi.desvio == null ? '—' : `${Math.round(kpi.desvio)}%`} color="#7C3AED" /></Grid>
        </Grid>

        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label={`Por aprobar (${porAprobar.data?.length ?? 0})`} />
          <Tab label={`En operación (${abiertas.data?.length ?? 0})`} />
          <Tab label={`Operarios (${jornadas.data?.length ?? 0})`} />
          <Tab label="Historial" />
        </Tabs>

        {/* ── Por aprobar ── */}
        {tab === 0 && (porAprobar.isLoading ? <LinearProgress /> : !porAprobar.data?.length
          ? <Alert severity="success">No hay reabastecimientos por aprobar.</Alert> : <>
            <Stack direction="row" gap={1} mb={1} alignItems="center">
              <Button variant="contained" startIcon={<Check />} disabled={!marcadas.size} onClick={aprobarMarcadas} sx={{ bgcolor: '#15803D' }}>Aprobar {marcadas.size || ''}</Button>
              <Typography fontSize={12.5} color="text.secondary">Al aprobar pasan a la cola y el sistema las asigna a los operarios en jornada.</Typography>
            </Stack>
            <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
              <Table size="small">
                <TableHead><TableRow>
                  <TableCell padding="checkbox" sx={{ bgcolor: '#F8FAFC' }}><Checkbox size="small" checked={marcadas.size === porAprobar.data.length}
                    indeterminate={marcadas.size > 0 && marcadas.size < porAprobar.data.length}
                    onChange={e => setMarcadas(e.target.checked ? new Set(porAprobar.data!.map(t => t.id)) : new Set())} /></TableCell>
                  {['#', 'Producto', 'Cantidad', 'Desde → hasta', 'Por qué', 'Creada', ''].map(h => <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC' }}>{h}</TableCell>)}
                </TableRow></TableHead>
                <TableBody>{porAprobar.data.map(t => (
                  <TableRow key={t.id} hover selected={marcadas.has(t.id)}>
                    <TableCell padding="checkbox"><Checkbox size="small" checked={marcadas.has(t.id)} onChange={() => setMarcadas(s => { const n = new Set(s); n.has(t.id) ? n.delete(t.id) : n.add(t.id); return n })} /></TableCell>
                    <TableCell><Stack direction="row" gap={0.5} alignItems="center"><Typography fontSize={12.5} fontWeight={700}>{t.id}</Typography>
                      {t.prioridad <= 1 && <Chip size="small" color="error" label="Urgente" sx={{ height: 18, fontSize: 10 }} />}</Stack></TableCell>
                    <TableCell><Typography fontSize={13} fontWeight={600}>{t.producto}</Typography><Typography fontSize={11} color="text.secondary" fontFamily="Consolas, monospace">{t.sku}{t.lote ? ` · lote ${t.lote}` : ''}</Typography></TableCell>
                    <TableCell sx={{ fontFamily: 'Consolas, monospace', fontWeight: 700 }}>{num(t.cantidad)}</TableCell>
                    <TableCell><Ruta t={t} /></TableCell>
                    <TableCell sx={{ maxWidth: 320 }}><Typography fontSize={12}>{t.razon_sugerencia}</Typography>
                      {t.notas && <Typography fontSize={11.5} color="#B45309">{t.notas}</Typography>}</TableCell>
                    <TableCell sx={{ fontSize: 12, whiteSpace: 'nowrap' }}>{fechaHora(t.creada)}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                      <Tooltip title="Aprobar"><IconButton size="small" color="success" onClick={() => hacer(() => bodega.aprobar([t.id]), 'Aprobada')}><Check fontSize="small" /></IconButton></Tooltip>
                      <Tooltip title="Rechazar"><IconButton size="small" color="error" onClick={() => { setRechazar(t); setMotivo('') }}><Close fontSize="small" /></IconButton></Tooltip>
                    </TableCell>
                  </TableRow>))}</TableBody>
              </Table>
            </Paper>
          </>)}

        {/* ── En operación ── */}
        {tab === 1 && (abiertas.isLoading ? <LinearProgress /> : !abiertas.data?.length ? <Alert severity="info">No hay tareas en operación.</Alert> :
          <Grid container spacing={1.5}>
            {abiertas.data.map(t => {
              const e = ESTADO_TAREA[t.estado] ?? { t: t.estado, c: '#64748B' }
              const lenta = (t.en_curso_min ?? 0) > alerta
              return (
                <Grid key={t.id} size={{ xs: 12, md: 6, lg: 4 }}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, borderLeft: `4px solid ${lenta ? '#DC2626' : e.c}`, height: '100%' }}>
                    <Stack direction="row" alignItems="center" gap={1} mb={0.5}>
                      <Typography fontWeight={800}>{TIPO_TAREA[t.tipo] ?? t.tipo} #{t.id}</Typography>
                      <Chip size="small" label={e.t} sx={{ bgcolor: e.c, color: '#fff', height: 20, fontSize: 11 }} />
                      {t.prioridad <= 1 && <Chip size="small" color="error" label="Urgente" sx={{ height: 20, fontSize: 11 }} />}
                      <Box flex={1} />
                      {lenta && <Tooltip title={`Lleva ${minutos(t.en_curso_min)} en curso`}><WarningAmber sx={{ color: '#DC2626' }} /></Tooltip>}
                    </Stack>
                    <Typography fontSize={14} fontWeight={600}>{t.sku} · {t.producto}</Typography>
                    <Typography fontSize={12.5} color="text.secondary">{num(t.cantidad)} und{t.lote ? ` · lote ${t.lote}` : ''}{t.contenedor ? ` · estiba ${t.contenedor}` : ''}</Typography>
                    <Box sx={{ my: 1.25, p: 1.25, bgcolor: '#F8FAFC', borderRadius: 2 }}><Ruta t={t} />
                      {t.razon_sugerencia && <Typography fontSize={11.5} color="text.secondary">{t.razon_sugerencia}</Typography>}</Box>
                    <Typography fontSize={12} color="text.secondary">
                      {t.operario ? <><b>{t.operario}</b> · {t.estado === 'EN_CURSO' ? `en curso hace ${minutos(t.en_curso_min)}${t.origen_confirmado ? ' · origen escaneado' : ''}` : `asignada ${fechaHora(t.asignada)}`}</>
                        : `En cola desde ${fechaHora(t.creada)}${t.aprobada_por ? ` · aprobó ${t.aprobada_por}` : ''}`}
                    </Typography>
                    {t.notas && <Typography fontSize={11.5} color="#B45309" mt={0.5}>{t.notas}</Typography>}
                    <Stack direction="row" gap={0.5} mt={1.25} flexWrap="wrap">
                      <Button size="small" startIcon={<SwapHoriz />} onClick={() => { setReasignar(t); setOperario('') }}>Reasignar</Button>
                      {t.tipo !== 'REABASTECIMIENTO' && <Button size="small" startIcon={<Refresh />} onClick={() => hacer(async () => { await wms.resugerir(t.id) }, 'Sugerencia recalculada')}>Otra sugerencia</Button>}
                      <Button size="small" color="inherit" startIcon={<Close />} onClick={() => { setCancelar(t); setMotivo('') }}>Cancelar</Button>
                    </Stack>
                  </Paper>
                </Grid>
              )
            })}
          </Grid>)}

        {/* ── Operarios ── */}
        {tab === 2 && (!jornadas.data?.length ? <Alert severity="info">Nadie tiene la jornada abierta en este almacén. Cada persona marca su entrada en Personal › Mi turno (o con su carné en el kiosco).</Alert> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['Operario', 'Estado', 'Desde', 'Hace', 'Tarea actual', 'Tareas', 'Productivo', 'Pausas', 'Utilización', ''].map(h =>
                <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC' }}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{jornadas.data.map(j => {
                const c = j.estado === 'ACTIVA' ? (j.tarea ? '#2563EB' : '#10B981') : '#F59E0B'
                return (
                  <TableRow key={j.id} hover>
                    <TableCell><Typography fontSize={13} fontWeight={700}>{j.persona}</Typography>
                      <Typography fontSize={11} color="text.secondary">{j.estacion ?? j.funciones.map(f => TIPO_TAREA[f] ?? f).join(' · ')}</Typography></TableCell>
                    <TableCell><Chip size="small" label={j.estado === 'PAUSADA' ? `Pausa · ${MOTIVOS_PAUSA[j.pausa_actual?.motivo ?? 'OTRO']}` : j.tarea ? 'Con tarea' : 'Libre'}
                      sx={{ bgcolor: alpha(c, 0.12), color: c, fontWeight: 700 }} /></TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{aFecha(j.inicio).toLocaleTimeString('es-CO', { timeStyle: 'short' })}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{minutos(j.minutos)}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{j.tarea ? `${TIPO_TAREA[j.tarea.tipo]} #${j.tarea.id} · ${j.tarea.sku}` : '—'}</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>{j.tareas}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{minutos(j.productivo_min)}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{minutos(j.pausa_min)}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{j.utilizacion_pct == null ? '—' : `${Math.round(j.utilizacion_pct)}%`}</TableCell>
                    <TableCell align="right"><Button size="small" color="inherit" onClick={() => hacer(() => personal.cerrarDe(j.id), 'Jornada cerrada')}>Cerrar jornada</Button></TableCell>
                  </TableRow>
                )
              })}</TableBody>
            </Table>
          </Paper>)}

        {/* ── Historial ── */}
        {tab === 3 && (historial.isLoading ? <LinearProgress /> : !historial.data?.length ? <Alert severity="info">Sin tareas terminadas.</Alert> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['#', 'Tipo', 'Estado', 'Producto', 'Cant.', 'Ruta', 'Operario', 'Esperó', 'La hizo en', 'Terminó'].map(h =>
                <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC' }}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{historial.data.map(t => {
                const e = ESTADO_TAREA[t.estado] ?? { t: t.estado, c: '#64748B' }
                return (
                  <TableRow key={t.id} hover>
                    <TableCell sx={{ fontWeight: 700 }}>{t.id}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{TIPO_TAREA[t.tipo] ?? t.tipo}</TableCell>
                    <TableCell><Chip size="small" label={e.t} sx={{ bgcolor: alpha(e.c, 0.12), color: e.c, fontWeight: 700, height: 20 }} /></TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{t.sku} · {t.producto}{t.notas && t.estado !== 'COMPLETADA' ? <Typography fontSize={11} color="text.secondary">{t.notas}</Typography> : null}</TableCell>
                    <TableCell sx={{ fontFamily: 'Consolas, monospace' }}>{num(t.cantidad)}</TableCell>
                    <TableCell><Ruta t={t} /></TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{t.operario ?? t.aprobada_por ?? '—'}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{minutos(t.espera_min)}</TableCell>
                    <TableCell sx={{ fontSize: 12.5 }}>{minutos(t.ejecucion_min)}</TableCell>
                    <TableCell sx={{ fontSize: 12, whiteSpace: 'nowrap' }}>{fechaHora(t.terminada)}</TableCell>
                  </TableRow>
                )
              })}</TableBody>
            </Table>
          </Paper>)}

        {/* diálogos */}
        <Dialog open={!!rechazar} onClose={() => setRechazar(null)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={800}>Rechazar el reabastecimiento #{rechazar?.id}</DialogTitle>
          <DialogContent><TextField fullWidth autoFocus label="Motivo" value={motivo} onChange={e => setMotivo(e.target.value)} sx={{ mt: 1 }}
            helperText="Ej.: el frente se surte manualmente hoy, la reserva está comprometida" /></DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setRechazar(null)}>Volver</Button>
            <Button color="error" variant="contained" disabled={motivo.trim().length < 3} onClick={() => { const t = rechazar!; setRechazar(null); hacer(() => bodega.rechazar(t.id, motivo), 'Rechazada') }}>Rechazar</Button></DialogActions>
        </Dialog>
        <Dialog open={!!cancelar} onClose={() => setCancelar(null)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={800}>Cancelar la tarea #{cancelar?.id}</DialogTitle>
          <DialogContent><Typography fontSize={13} color="text.secondary" mb={1.5}>La mercancía se queda donde está.</Typography>
            <TextField fullWidth autoFocus label="Motivo" value={motivo} onChange={e => setMotivo(e.target.value)} /></DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setCancelar(null)}>Volver</Button>
            <Button color="error" variant="contained" disabled={motivo.trim().length < 3} onClick={() => { const t = cancelar!; setCancelar(null); hacer(() => bodega.cancelar(t.id, motivo), 'Tarea cancelada') }}>Cancelar tarea</Button></DialogActions>
        </Dialog>
        <Dialog open={!!reasignar} onClose={() => setReasignar(null)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={800}>Reasignar la tarea #{reasignar?.id}</DialogTitle>
          <DialogContent>
            <TextField select fullWidth label="Operario" value={operario} onChange={e => setOperario(e.target.value === '' ? '' : Number(e.target.value))} sx={{ mt: 1 }}
              helperText="Solo operarios con la jornada activa y sin tarea en sus manos">
              <MenuItem value="">Devolver a la cola (que el sistema la asigne)</MenuItem>
              {enJornada.filter(j => !j.tarea).map(j => <MenuItem key={j.usuario_id} value={j.usuario_id}>{j.persona}</MenuItem>)}
            </TextField>
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setReasignar(null)}>Volver</Button>
            <Button variant="contained" sx={{ bgcolor: COLOR }} onClick={() => { const t = reasignar!; setReasignar(null); hacer(() => bodega.reasignar(t.id, operario === '' ? null : operario), operario === '' ? 'Devuelta a la cola' : 'Reasignada') }}>Reasignar</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
