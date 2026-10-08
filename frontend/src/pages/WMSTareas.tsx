/**
 * WMS · Tareas de bodega
 *
 * Lo que el personal tiene que mover: ubicar lo recibido (con la ubicación
 * sugerida y su razón). El operario la toma (queda su nombre y la hora),
 * escanea la ubicación donde la deja y, si no es la sugerida, dice por qué.
 * Cada paso queda con hora: de ahí salen los tiempos de muelle a estantería y
 * la productividad por persona.
 */
import { useMemo, useRef, useState } from 'react'
import {
  Box, Paper, Typography, MenuItem, Button, Chip, Dialog, DialogTitle, DialogContent, DialogActions, Alert, Stack, ToggleButtonGroup, ToggleButton,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { AssignmentTurnedIn, PlayArrow, PlaceOutlined, Refresh, Close } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, Cifra, errorApi } from '@/components/comun/Registro'
import { wms, fechaHora, num, type Tarea } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

const COLOR = COLOR_MODULO
const ESTADO: Record<string, { t: string; c: string }> = {
  PENDIENTE: { t: 'Pendiente', c: '#D97706' }, EN_CURSO: { t: 'En curso', c: '#2563EB' },
  COMPLETADA: { t: 'Completada', c: '#15803D' }, CANCELADA: { t: 'Cancelada', c: '#64748B' },
}
const TIPO: Record<string, string> = { UBICACION: 'Ubicar', REABASTECIMIENTO: 'Reabastecer', MOVIMIENTO: 'Mover' }

export default function WMSTareas() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  const [vista, setVista] = useState<'abiertas' | 'hechas'>('abiertas')
  const tareas = useQuery({
    queryKey: ['wms-tareas-bodega', almacen, vista], refetchInterval: 20_000,
    queryFn: () => wms.tareas({ almacen_id: almacen || undefined, estado: vista === 'abiertas' ? 'PENDIENTE,EN_CURSO' : 'COMPLETADA,CANCELADA', limite: 300 }),
  })
  const hechas = useQuery({ queryKey: ['wms-tareas-bodega-hechas', almacen], queryFn: () => wms.tareas({ almacen_id: almacen || undefined, estado: 'COMPLETADA', limite: 500 }) })
  const [ubicar, setUbicar] = useState<Tarea | null>(null)
  const [codigo, setCodigo] = useState('')
  const [motivo, setMotivo] = useState('')
  const [cancelar, setCancelar] = useState<Tarea | null>(null)
  const campo = useRef<HTMLInputElement>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['wms-tareas-bodega'] }).then(() => qc.invalidateQueries({ queryKey: ['wms-tareas-bodega-hechas'] }))

  const indicadores = useMemo(() => {
    const t = hechas.data ?? []
    const hoy = new Date().toDateString()
    const deHoy = t.filter(x => x.terminada && aFecha(x.terminada).toDateString() === hoy)
    const ejec = t.map(x => x.ejecucion_min).filter((v): v is number => v != null)
    const conSugerida = t.filter(x => x.sugerida)
    return {
      hoy: deHoy.length,
      ejecucion: ejec.length ? ejec.reduce((a, b) => a + b, 0) / ejec.length : null,
      desvio: conSugerida.length ? conSugerida.filter(x => x.motivo_desvio).length / conSugerida.length * 100 : null,
    }
  }, [hechas.data])
  const abiertas = (tareas.data ?? []).filter(t => t.estado === 'PENDIENTE' || t.estado === 'EN_CURSO')

  const iniciar = async (t: Tarea) => {
    try { await wms.iniciarTarea(t.id); toast.success('Tarea tomada'); refrescar() } catch (e) { toast.error(errorApi(e)) }
  }
  const abrirUbicar = (t: Tarea) => { setUbicar(t); setCodigo(''); setMotivo(''); setTimeout(() => campo.current?.focus(), 100) }
  const distinta = !!ubicar?.sugerida && !!codigo && codigo.trim().toUpperCase() !== ubicar.sugerida.toUpperCase()
  const confirmar = async () => {
    try {
      await wms.completarTarea(ubicar!.id, { ubicacion_codigo: codigo.trim(), motivo_desvio: distinta ? motivo : undefined })
      toast.success(`Ubicado en ${codigo.trim().toUpperCase()}`); setUbicar(null); refrescar()
    } catch (e) { toast.error(errorApi(e)) }
  }
  const resugerir = async (t: Tarea) => {
    try { const r = await wms.resugerir(t.id); toast.success(r.sugerida ? `Nueva sugerencia: ${r.sugerida}` : 'No hay ubicación libre que sugerir'); refrescar() }
    catch (e) { toast.error(errorApi(e)) }
  }

  return (
    <Layout title="WMS — Tareas">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<AssignmentTurnedIn sx={{ fontSize: 28 }} />} titulo="Tareas de bodega" color={COLOR}
          subtitulo="Ubicación dirigida: qué mover, a dónde y quién lo hizo" />
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Pendientes" valor={abiertas.filter(t => t.estado === 'PENDIENTE').length} color="#D97706" /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Completadas hoy" valor={indicadores.hoy} color="#15803D" /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Tiempo medio de ejecución" valor={indicadores.ejecucion == null ? '—' : `${num(Math.round(indicadores.ejecucion * 10) / 10)} min`} color={COLOR} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="No fue a la sugerida" valor={indicadores.desvio == null ? '—' : `${Math.round(indicadores.desvio)}%`} color="#7C3AED" sub="Base para mejorar las reglas de ubicación" /></Grid>
        </Grid>
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap" alignItems="center">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 220 }}>
            <MenuItem value="">Todos</MenuItem>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <ToggleButtonGroup size="small" exclusive value={vista} onChange={(_, v) => v && setVista(v)}>
            <ToggleButton value="abiertas">Por hacer</ToggleButton><ToggleButton value="hechas">Historial</ToggleButton>
          </ToggleButtonGroup>
        </Stack>

        {tareas.data && tareas.data.length === 0 && <Alert severity="info">{vista === 'abiertas' ? 'No hay tareas por hacer.' : 'Sin tareas terminadas.'}</Alert>}
        <Grid container spacing={1.5}>
          {(tareas.data ?? []).map(t => {
            const e = ESTADO[t.estado] ?? { t: t.estado, c: '#64748B' }
            return (
              <Grid key={t.id} size={{ xs: 12, md: 6, lg: 4 }}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, borderLeft: `4px solid ${e.c}`, height: '100%' }}>
                  <Stack direction="row" alignItems="center" gap={1} mb={0.5}>
                    <Typography fontWeight={800}>{TIPO[t.tipo] ?? t.tipo} #{t.id}</Typography>
                    <Chip size="small" label={e.t} sx={{ bgcolor: e.c, color: '#fff', height: 20, fontSize: 11 }} />
                    <Box flex={1} />
                    <Typography fontSize={11} color="text.secondary">{fechaHora(t.creada)}</Typography>
                  </Stack>
                  <Typography fontSize={14} fontWeight={600}>{t.sku} · {t.producto}</Typography>
                  <Typography fontSize={12.5} color="text.secondary">
                    {num(t.cantidad)} und{t.lote ? ` · lote ${t.lote}` : ''}{t.contenedor ? ` · estiba ${t.contenedor}` : ''}
                    {t.documento_tipo ? ` · ${t.documento_tipo.toLowerCase()} ${t.documento_id}` : ''}
                  </Typography>
                  <Box sx={{ my: 1.25, p: 1.25, bgcolor: '#F8FAFC', borderRadius: 2, fontFamily: 'monospace', fontSize: 13 }}>
                    {t.origen ?? '—'} → <b>{t.destino ?? t.sugerida ?? 'sin sugerencia'}</b>
                    {t.razon_sugerencia && !t.destino && <Typography fontSize={11.5} color="text.secondary" fontFamily="inherit">{t.razon_sugerencia}</Typography>}
                    {t.motivo_desvio && <Typography fontSize={11.5} color="#7C3AED" fontFamily="inherit">Sugerida {t.sugerida}: {t.motivo_desvio}</Typography>}
                  </Box>
                  {t.operario && <Typography fontSize={12} color="text.secondary">
                    {t.operario}{t.espera_min != null ? ` · esperó ${num(t.espera_min)} min` : ''}{t.ejecucion_min != null ? ` · la hizo en ${num(t.ejecucion_min)} min` : ''}
                  </Typography>}
                  {(t.estado === 'PENDIENTE' || t.estado === 'EN_CURSO') && (
                    <Stack direction="row" gap={1} mt={1.5} flexWrap="wrap">
                      {t.estado === 'PENDIENTE' && <Button size="small" startIcon={<PlayArrow />} onClick={() => iniciar(t)}>Tomar</Button>}
                      <Button size="small" variant="contained" startIcon={<PlaceOutlined />} onClick={() => abrirUbicar(t)} sx={{ bgcolor: COLOR }}>Ubicar</Button>
                      <Button size="small" startIcon={<Refresh />} onClick={() => resugerir(t)}>Otra sugerencia</Button>
                      <Button size="small" color="inherit" startIcon={<Close />} onClick={() => { setCancelar(t); setMotivo('') }}>Cancelar</Button>
                    </Stack>
                  )}
                </Paper>
              </Grid>
            )
          })}
        </Grid>

        <Dialog open={!!ubicar} onClose={() => setUbicar(null)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Ubicar {ubicar?.contenedor ?? ubicar?.sku}</DialogTitle>
          <DialogContent>
            {ubicar?.sugerida && <Alert severity="info" sx={{ mb: 2 }}>Sugerida: <b>{ubicar.sugerida}</b>{ubicar.razon_sugerencia ? ` — ${ubicar.razon_sugerencia}` : ''}</Alert>}
            <TextField inputRef={campo} fullWidth label="Escanee la ubicación donde la deja" value={codigo} onChange={e => setCodigo(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && codigo.trim() && (!distinta || motivo.trim())) confirmar() }}
              inputProps={{ style: { fontFamily: 'monospace', fontSize: 18 } }} />
            {distinta && <TextField fullWidth sx={{ mt: 2 }} label="¿Por qué no en la sugerida?" value={motivo} onChange={e => setMotivo(e.target.value)}
              helperText="Ej.: ubicación ocupada, no cabe, estiba dañada" />}
          </DialogContent>
          <DialogActions>
            <Button color="inherit" onClick={() => setUbicar(null)}>Volver</Button>
            {ubicar?.sugerida && !codigo && <Button onClick={() => setCodigo(ubicar.sugerida!)}>Usar la sugerida</Button>}
            <Button variant="contained" disabled={!codigo.trim() || (distinta && !motivo.trim())} onClick={confirmar} sx={{ bgcolor: COLOR }}>Confirmar</Button>
          </DialogActions>
        </Dialog>

        <Dialog open={!!cancelar} onClose={() => setCancelar(null)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Cancelar la tarea #{cancelar?.id}</DialogTitle>
          <DialogContent>
            <Typography fontSize={13} color="text.secondary" mb={1.5}>La mercancía se queda donde está. Solo un supervisor puede cancelar.</Typography>
            <TextField fullWidth label="Motivo" value={motivo} onChange={e => setMotivo(e.target.value)} />
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setCancelar(null)}>Volver</Button>
            <Button color="error" variant="contained" disabled={motivo.trim().length < 3} onClick={async () => {
              try { await wms.cancelarTarea(cancelar!.id, motivo); toast.success('Tarea cancelada'); setCancelar(null); refrescar() }
              catch (e) { toast.error(errorApi(e)) }
            }}>Cancelar tarea</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
