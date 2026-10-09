/**
 * WFM · Mi turno (la pantalla de cada persona, pensada para celular o terminal).
 *
 * 1. Marca la entrada: su estación sale de la programación del día (o de su
 *    estación habitual); si no tiene, elige estación o qué va a hacer.
 * 2. Ve sus tareas: la que tiene en sus manos, cuántas esperan en la cola de
 *    su estación, sus alistamientos (picking) asignados.
 * 3. «Tomar siguiente»: el sistema le entrega la tarea que le toca; escanea el
 *    origen y el destino. Al terminar recibe la siguiente.
 * Pausas y salida miden su tiempo. Los lectores escriben como teclado + Enter.
 */
import { useEffect, useRef, useState } from 'react'
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  LinearProgress, Menu, MenuItem, Paper, Stack, Switch, Typography, alpha,
} from '@mui/material'
import {
  PlayArrow, Pause, Logout, QrCodeScanner, Inventory2, Place, ArrowDownward, ReportProblem, CheckCircle, Badge, Coffee,
  Hub, ShoppingCart, OpenInNew,
} from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms, num } from '@/api/wmsTrazable'
import { bodega, minutos, MOTIVOS_PAUSA, TIPO_TAREA, type TareaOp } from '@/api/tareasBodega'
import { personal, FUNCIONES } from '@/api/personal'
import { aFecha } from '@/utils/fechas'

const COLOR = '#0D9488'

function Reloj({ desde }: { desde: string }) {
  const [, set] = useState(0)
  useEffect(() => { const t = setInterval(() => set(x => x + 1), 30_000); return () => clearInterval(t) }, [])
  return <>{minutos((Date.now() - aFecha(desde).getTime()) / 60000)}</>
}

function Escaner({ etiqueta, onLeer, deshabilitado }: { etiqueta: string; onLeer: (v: string) => void; deshabilitado?: boolean }) {
  const [v, setV] = useState('')
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { setTimeout(() => ref.current?.focus(), 150) }, [etiqueta])
  return (
    <TextField inputRef={ref} fullWidth label={etiqueta} value={v} disabled={deshabilitado} autoComplete="off"
      onChange={e => setV(e.target.value)}
      onKeyDown={e => { if (e.key === 'Enter' && v.trim()) { onLeer(v.trim()); setV('') } }}
      InputProps={{ startAdornment: <QrCodeScanner sx={{ mr: 1, color: 'text.secondary' }} />, sx: { fontFamily: 'Consolas, monospace', fontSize: 20 } }} />
  )
}

export default function PersonalMiTurno() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const mia = useQuery({ queryKey: ['wfm-mi-jornada'], queryFn: personal.miJornada, refetchInterval: 15_000 })
  const tareas = useQuery({ queryKey: ['wfm-mis-tareas'], queryFn: personal.misTareas, refetchInterval: 15_000, enabled: !!mia.data?.jornada })
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const estaciones = useQuery({ queryKey: ['wfm-estaciones'], queryFn: () => personal.estaciones() })
  const zonas = useQuery({ queryKey: ['wms-zonas'], queryFn: () => api.get('/wms/zonas/').then(r => r.data as any[]) })
  const [form, setForm] = useState<{ estacion_id: number | ''; almacen_id: number | ''; funciones: string[]; zonas: number[]; montacargas: boolean }>(
    { estacion_id: '', almacen_id: '', funciones: Object.keys(FUNCIONES), zonas: [], montacargas: false })
  const [ocupado, setOcupado] = useState(false)
  const [sinTareas, setSinTareas] = useState(false)
  const [menuPausa, setMenuPausa] = useState<HTMLElement | null>(null)
  const [menuNovedad, setMenuNovedad] = useState<HTMLElement | null>(null)
  const [cerrar, setCerrar] = useState(false)
  const [destino, setDestino] = useState<string | null>(null)
  const [motivo, setMotivo] = useState('')
  const [cantidad, setCantidad] = useState('')

  const d = mia.data
  const j = d?.jornada ?? null
  const t: TareaOp | null = tareas.data?.actual ?? null
  useEffect(() => {
    if (!d || j) return
    setForm(f => ({ ...f, estacion_id: f.estacion_id || d.programado?.estacion_id || d.perfil?.estacion_id || '',
      almacen_id: f.almacen_id || d.perfil?.almacen_id || almacenes.data?.[0]?.id || '' }))
  }, [d, j, almacenes.data])
  useEffect(() => { setDestino(null); setMotivo(''); setCantidad(t?.cantidad != null ? String(t.cantidad) : '') }, [t?.id])
  const refrescar = () => Promise.all([qc.invalidateQueries({ queryKey: ['wfm-mi-jornada'] }), qc.invalidateQueries({ queryKey: ['wfm-mis-tareas'] })])
  const accion = async (f: () => Promise<unknown>, ok?: string) => {
    setOcupado(true)
    try { await f(); if (ok) toast.success(ok); await refrescar() } catch (e) { toast.error(errorApi(e)) } finally { setOcupado(false) }
  }
  const siguiente = async () => {
    setOcupado(true)
    try { const r = await bodega.siguiente(); setSinTareas(!r.tarea); await refrescar() }
    catch (e) { toast.error(errorApi(e)) } finally { setOcupado(false) }
  }
  useEffect(() => {
    if (!sinTareas || t || j?.estado !== 'ACTIVA') return
    const x = setInterval(siguiente, 20_000)
    return () => clearInterval(x)
  }, [sinTareas, t, j?.estado]) // eslint-disable-line react-hooks/exhaustive-deps

  const completar = async () => {
    if (!t || !destino) return
    const desvio = !!t.sugerida && destino.toUpperCase() !== t.sugerida.toUpperCase()
    setOcupado(true)
    try {
      await bodega.completar(t.id, { ubicacion_codigo: destino, motivo_desvio: desvio ? motivo : undefined,
        cantidad: t.tipo === 'REABASTECIMIENTO' && cantidad ? Number(cantidad) : undefined })
      toast.success(`Listo: ${t.sku} en ${destino.toUpperCase()}`)
      await refrescar(); await siguiente()
    } catch (e) { toast.error(errorApi(e)) } finally { setOcupado(false) }
  }

  if (mia.isLoading) return <Layout title="Personal — Mi turno"><LinearProgress /></Layout>
  const estSel = (estaciones.data ?? []).find(e => e.id === form.estacion_id)

  return (
    <Layout title="Personal — Mi turno">
      <Box sx={{ p: { xs: 1.5, md: 3 }, maxWidth: 720, mx: 'auto' }}>
        {/* ── Marcar entrada ── */}
        {!j && <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, borderRadius: 3 }}>
          <Stack direction="row" gap={1.5} alignItems="center" mb={2}>
            <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: alpha(COLOR, 0.1), display: 'flex' }}><Badge sx={{ color: COLOR }} /></Box>
            <Box><Typography fontWeight={800} fontSize={20}>Marcar entrada</Typography>
              <Typography fontSize={13} color="text.secondary">Desde aquí recibe sus tareas y se mide su tiempo de trabajo.</Typography></Box>
          </Stack>
          {d?.programado && <Alert severity="info" icon={<Hub />} sx={{ mb: 2 }}>
            Hoy está programado en <b>{d.programado.estacion}</b>{d.programado.hora_inicio ? ` · ${d.programado.hora_inicio}–${d.programado.hora_fin ?? ''}` : ''}.</Alert>}
          <Stack gap={2}>
            <TextField select label="Estación de trabajo" value={form.estacion_id} onChange={e => setForm({ ...form, estacion_id: e.target.value === '' ? '' : Number(e.target.value) })}
              helperText="La estación define qué tareas recibe y en qué zonas">
              <MenuItem value="">Sin estación (elegir qué voy a hacer)</MenuItem>
              {(estaciones.data ?? []).filter(e => e.activo).map(e => <MenuItem key={e.id} value={e.id}>{e.codigo} · {e.nombre}</MenuItem>)}
            </TextField>
            {!estSel && <>
              <TextField select label="Almacén" value={form.almacen_id} onChange={e => setForm({ ...form, almacen_id: Number(e.target.value), zonas: [] })}>
                {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
              </TextField>
              <Box>
                <Typography fontSize={13} fontWeight={700} mb={0.75}>¿Qué va a hacer hoy?</Typography>
                <Stack direction="row" gap={1} flexWrap="wrap">
                  {Object.entries(FUNCIONES).map(([k, txt]) => {
                    const on = form.funciones.includes(k)
                    return <Chip key={k} label={txt} clickable color={on ? 'primary' : 'default'} variant={on ? 'filled' : 'outlined'}
                      onClick={() => setForm({ ...form, funciones: on ? form.funciones.filter(x => x !== k) : [...form.funciones, k] })} />
                  })}
                </Stack>
              </Box>
              <TextField select label="Zonas (vacío = todas)" SelectProps={{ multiple: true }} value={form.zonas}
                onChange={e => setForm({ ...form, zonas: (e.target.value as unknown as number[]) })}>
                {(zonas.data ?? []).filter(z => z.almacen_id === form.almacen_id).map(z => <MenuItem key={z.id} value={z.id}>{z.codigo} · {z.nombre}</MenuItem>)}
              </TextField>
              <FormControlLabel control={<Switch checked={form.montacargas} onChange={e => setForm({ ...form, montacargas: e.target.checked })} />}
                label="Manejo montacargas hoy" />
            </>}
            <Button size="large" variant="contained" startIcon={<PlayArrow />} disabled={ocupado || (!estSel && (!form.almacen_id || !form.funciones.length))}
              onClick={() => accion(() => personal.iniciar({ estacion_id: form.estacion_id || null, almacen_id: form.almacen_id || undefined,
                funciones: estSel ? [] : form.funciones, zonas: estSel ? [] : form.zonas, montacargas: form.montacargas }), 'Entrada registrada')}
              sx={{ py: 1.5, fontSize: 17, borderRadius: 2.5, bgcolor: COLOR, '&:hover': { bgcolor: '#0F766E' } }}>Marcar entrada</Button>
          </Stack>
        </Paper>}

        {/* ── Jornada abierta ── */}
        {j && <>
          <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
            <Stack direction="row" alignItems="center" gap={1.25}>
              <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: j.estado === 'ACTIVA' ? '#10B981' : '#F59E0B',
                boxShadow: `0 0 0 4px ${alpha(j.estado === 'ACTIVA' ? '#10B981' : '#F59E0B', 0.2)}` }} />
              <Box flex={1} minWidth={0}>
                <Typography fontWeight={800} noWrap>{j.persona}</Typography>
                <Typography fontSize={12.5} color="text.secondary">Desde {aFecha(j.inicio).toLocaleTimeString('es-CO', { timeStyle: 'short' })} · <Reloj desde={j.inicio} /></Typography>
              </Box>
              {j.estado === 'ACTIVA'
                ? <Button size="small" startIcon={<Pause />} onClick={e => setMenuPausa(e.currentTarget)} disabled={t?.estado === 'EN_CURSO'}>Pausa</Button>
                : <Button size="small" variant="contained" startIcon={<PlayArrow />} onClick={() => accion(personal.reanudar, 'Jornada reanudada')}>Reanudar</Button>}
              <Button size="small" color="inherit" startIcon={<Logout />} onClick={() => setCerrar(true)} disabled={t?.estado === 'EN_CURSO'}>Salida</Button>
            </Stack>
            <Stack direction="row" alignItems="center" gap={1} mt={1.25} sx={{ p: 1, borderRadius: 2, bgcolor: alpha(COLOR, 0.06) }}>
              <Hub sx={{ color: COLOR, fontSize: 20 }} />
              <Typography fontSize={13.5}>{j.estacion ? <>Estación <b>{j.estacion}</b></> : <>Sin estación · {j.funciones.map(f => FUNCIONES[f] ?? f).join(', ')}</>}</Typography>
            </Stack>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1, mt: 1.25 }}>
              {[['Tareas hoy', String(tareas.data?.hechas_hoy ?? j.tareas)], ['Productivo', minutos(j.productivo_min)], ['En pausa', minutos(j.pausa_min)],
                ['En cola', String(tareas.data?.en_cola ?? '—')]].map(([k, v]) => (
                <Box key={k} sx={{ p: 1, borderRadius: 2, bgcolor: '#F8FAFC', textAlign: 'center' }}>
                  <Typography fontWeight={800} fontSize={16}>{v}</Typography>
                  <Typography fontSize={11} color="text.secondary">{k}</Typography>
                </Box>))}
            </Box>
          </Paper>

          {j.estado === 'PAUSADA' && <Paper variant="outlined" sx={{ p: 3, borderRadius: 3, textAlign: 'center', borderColor: '#F59E0B', bgcolor: alpha('#F59E0B', 0.05) }}>
            <Coffee sx={{ fontSize: 44, color: '#F59E0B' }} />
            <Typography fontWeight={800} fontSize={20} mt={1}>En pausa · {MOTIVOS_PAUSA[j.pausa_actual?.motivo ?? 'OTRO']}</Typography>
            {j.pausa_actual && <Typography color="text.secondary">Desde hace <Reloj desde={j.pausa_actual.inicio} /></Typography>}
            <Button size="large" variant="contained" startIcon={<PlayArrow />} sx={{ mt: 2, bgcolor: COLOR }} onClick={() => accion(personal.reanudar, 'Jornada reanudada')}>Volver al trabajo</Button>
          </Paper>}

          {/* alistamientos asignados (se hacen en Picking) */}
          {j.estado === 'ACTIVA' && !!tareas.data?.picking.length && <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
            <Stack direction="row" alignItems="center" gap={1} mb={1}><ShoppingCart sx={{ color: COLOR }} /><Typography fontWeight={800}>Mis alistamientos</Typography></Stack>
            {tareas.data.picking.map(p => (
              <Stack key={p.id} direction="row" alignItems="center" gap={1} sx={{ py: 0.75, borderTop: '1px solid #F1F5F9' }}>
                <Typography fontSize={13.5} flex={1}>Picking #{p.id} · orden {p.orden_id} · {p.estado === 'EN_PROGRESO' ? 'en progreso' : 'pendiente'}</Typography>
                <Button size="small" endIcon={<OpenInNew />} onClick={() => navigate('/wms/picking')}>Abrir</Button>
              </Stack>))}
          </Paper>}

          {j.estado === 'ACTIVA' && !t && <Paper variant="outlined" sx={{ p: 3, borderRadius: 3, textAlign: 'center' }}>
            {sinTareas ? <>
              <CheckCircle sx={{ fontSize: 44, color: '#10B981' }} />
              <Typography fontWeight={800} fontSize={19} mt={1}>No hay tareas para su estación ahora</Typography>
              <Typography color="text.secondary" fontSize={13.5}>Se revisa sola cada 20 segundos.</Typography>
            </> : <Typography color="text.secondary" mb={1}>{tareas.data?.en_cola ? `${tareas.data.en_cola} tarea(s) esperan en la cola.` : 'Pida su próxima tarea.'} El sistema le asigna la que le toca.</Typography>}
            <Button size="large" variant="contained" startIcon={ocupado ? <CircularProgress size={18} color="inherit" /> : <ArrowDownward />} disabled={ocupado}
              onClick={siguiente} sx={{ mt: 2, py: 1.5, px: 4, fontSize: 17, borderRadius: 2.5, bgcolor: COLOR, '&:hover': { bgcolor: '#0F766E' } }}>Tomar siguiente tarea</Button>
          </Paper>}

          {/* ── Tarea en sus manos ── */}
          {j.estado === 'ACTIVA' && t && (() => {
            const paso = t.origen && !t.origen_confirmado ? 1 : 2
            const desvio = !!destino && !!t.sugerida && destino.toUpperCase() !== t.sugerida.toUpperCase()
            return (
              <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden', borderColor: alpha(COLOR, 0.4) }}>
                <Box sx={{ px: 2, py: 1.5, bgcolor: alpha(COLOR, 0.06), display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip size="small" label={TIPO_TAREA[t.tipo] ?? t.tipo} sx={{ bgcolor: COLOR, color: '#fff', fontWeight: 700 }} />
                  {t.prioridad <= 1 && <Chip size="small" color="error" label="Urgente" />}
                  <Typography fontWeight={800}>#{t.id}</Typography>
                  <Box flex={1} />
                  <Button size="small" color="warning" startIcon={<ReportProblem />} onClick={e => setMenuNovedad(e.currentTarget)}>Novedad</Button>
                </Box>
                <Box sx={{ p: 2 }}>
                  <Stack direction="row" gap={1.25} alignItems="center" mb={2}>
                    <Inventory2 sx={{ color: 'text.secondary' }} />
                    <Box><Typography fontWeight={800} fontSize={17}>{t.producto}</Typography>
                      <Typography fontSize={13} color="text.secondary" fontFamily="Consolas, monospace">
                        {t.sku} · {num(t.cantidad)} und{t.lote ? ` · lote ${t.lote}` : ''}{t.contenedor ? ` · estiba ${t.contenedor}` : ''}{t.contenedor_origen ? ` · de la estiba ${t.contenedor_origen}` : ''}</Typography></Box>
                  </Stack>
                  <Box sx={{ p: 1.5, borderRadius: 2, border: '2px solid', borderColor: paso === 1 ? COLOR : '#E2E8F0', bgcolor: paso === 1 ? alpha(COLOR, 0.04) : '#fff', mb: 1.5 }}>
                    <Stack direction="row" alignItems="center" gap={1}>
                      {paso > 1 ? <CheckCircle sx={{ color: '#10B981' }} /> : <Place sx={{ color: COLOR }} />}
                      <Typography fontSize={12.5} color="text.secondary" fontWeight={700}>1 · TOMAR EN</Typography>
                    </Stack>
                    <Typography sx={{ fontFamily: 'Consolas, monospace', fontWeight: 800, fontSize: 30, my: 0.5 }}>{t.origen ?? '—'}</Typography>
                    {paso === 1 && <Escaner etiqueta="Escanee la ubicación (o la estiba) de origen" deshabilitado={ocupado}
                      onLeer={v => accion(() => bodega.confirmarOrigen(t.id, v), 'Origen confirmado')} />}
                  </Box>
                  <Box sx={{ p: 1.5, borderRadius: 2, border: '2px solid', borderColor: paso === 2 ? COLOR : '#E2E8F0', bgcolor: paso === 2 ? alpha(COLOR, 0.04) : '#fff', opacity: paso === 2 ? 1 : 0.6 }}>
                    <Stack direction="row" alignItems="center" gap={1}><Place sx={{ color: paso === 2 ? COLOR : 'text.disabled' }} />
                      <Typography fontSize={12.5} color="text.secondary" fontWeight={700}>2 · DEJAR EN</Typography></Stack>
                    <Typography sx={{ fontFamily: 'Consolas, monospace', fontWeight: 800, fontSize: 30, my: 0.5 }}>{t.sugerida ?? 'Donde haya espacio'}</Typography>
                    {t.razon_sugerencia && <Typography fontSize={12.5} color="text.secondary" mb={1}>{t.razon_sugerencia}</Typography>}
                    {paso === 2 && <Stack gap={1.5}>
                      {!destino ? <Escaner etiqueta="Escanee la ubicación donde la deja" deshabilitado={ocupado} onLeer={v => setDestino(v.toUpperCase())} />
                        : <Alert severity={desvio ? 'warning' : 'success'} action={<Button color="inherit" size="small" onClick={() => setDestino(null)}>Cambiar</Button>}>
                          Destino: <b>{destino}</b>{desvio ? ' — no es la sugerida' : ''}</Alert>}
                      {t.tipo === 'REABASTECIMIENTO' && destino && <TextField label="Unidades que llevó" type="number" value={cantidad} onChange={e => setCantidad(e.target.value)}
                        helperText={`Aprobadas: ${num(t.cantidad)}. Si llevó menos, corrija.`} />}
                      {desvio && <TextField label="¿Por qué no en la sugerida?" value={motivo} onChange={e => setMotivo(e.target.value)} helperText="Ej.: ocupada, no cabe, bloqueada" />}
                      {destino && <Button size="large" variant="contained" startIcon={ocupado ? <CircularProgress size={18} color="inherit" /> : <CheckCircle />}
                        disabled={ocupado || (desvio && motivo.trim().length < 3)} onClick={completar}
                        sx={{ py: 1.4, fontSize: 17, borderRadius: 2.5, bgcolor: '#10B981', '&:hover': { bgcolor: '#059669' } }}>Confirmar y seguir</Button>}
                    </Stack>}
                  </Box>
                </Box>
              </Paper>
            )
          })()}
        </>}

        <Menu anchorEl={menuPausa} open={!!menuPausa} onClose={() => setMenuPausa(null)}>
          {Object.entries(MOTIVOS_PAUSA).map(([k, v]) => <MenuItem key={k} onClick={() => { setMenuPausa(null); accion(() => personal.pausar(k), `En pausa: ${v.toLowerCase()}`) }}>{v}</MenuItem>)}
        </Menu>
        <Menu anchorEl={menuNovedad} open={!!menuNovedad} onClose={() => setMenuNovedad(null)}>
          {[['FALTANTE', 'No está la mercancía (faltante)'], ['DANADO', 'Mercancía dañada'], ['UBICACION_BLOQUEADA', 'Ubicación bloqueada u ocupada'], ['OTRO', 'No puedo hacerla (otro)']].map(([k, v]) =>
            <MenuItem key={k} onClick={() => { setMenuNovedad(null); if (t) accion(() => bodega.novedad(t.id, k), 'Novedad reportada: la tarea vuelve al supervisor') }}>{v}</MenuItem>)}
        </Menu>
        <Dialog open={cerrar} onClose={() => setCerrar(false)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={800}>Marcar la salida</DialogTitle>
          <DialogContent><Typography fontSize={14}>Hoy: {j?.tareas ?? 0} tareas · {minutos(j?.productivo_min)} productivo · {minutos(j?.pausa_min)} en pausa.
            {t ? ' La tarea asignada vuelve a la cola.' : ''}</Typography></DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setCerrar(false)}>Volver</Button>
            <Button variant="contained" color="error" onClick={() => { setCerrar(false); accion(personal.cerrar, 'Salida registrada') }}>Marcar salida</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
