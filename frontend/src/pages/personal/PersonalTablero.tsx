/**
 * WFM · Tablero del supervisor (en vivo).
 *
 * Cada estación con quién está programado hoy, quién está trabajando (libre,
 * con tarea o en pausa) y cuántas tareas esperan en su cola. Las personas se
 * mueven de estación con un clic; abajo, quién está en jornada sin estación y
 * quién estaba programado y no ha llegado.
 */
import { useState } from 'react'
import {
  Alert, Avatar, Box, Button, Chip, IconButton, LinearProgress, Menu, MenuItem, Paper, Stack, Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import { Groups, SwapHoriz, Logout, Hub, EventNote, Badge, PersonOff, Inventory2 } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, Cifra, errorApi } from '@/components/comun/Registro'
import { wms } from '@/api/wmsTrazable'
import { minutos, MOTIVOS_PAUSA, TIPO_TAREA } from '@/api/tareasBodega'
import { personal, TIPOS_ESTACION, type Jornada } from '@/api/personal'

const COLOR = '#0D9488'
const iniciales = (n?: string | null) => (n ?? '?').split(' ').filter(Boolean).slice(0, 2).map(x => x[0]).join('').toUpperCase()

export default function PersonalTablero() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  const tablero = useQuery({ queryKey: ['wfm-tablero', almacen], refetchInterval: 15_000, queryFn: () => personal.tablero(almacen || undefined) })
  const [mover, setMover] = useState<{ ancla: HTMLElement; j: Jornada } | null>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['wfm-tablero'] })
  const hacer = async (f: () => Promise<unknown>, ok: string) => { try { await f(); toast.success(ok); refrescar() } catch (e) { toast.error(errorApi(e)) } }
  const d = tablero.data

  const Persona = ({ j }: { j: Jornada }) => {
    const c = j.estado === 'PAUSADA' ? '#F59E0B' : j.tarea ? '#2563EB' : '#10B981'
    return (
      <Stack direction="row" alignItems="center" gap={1} sx={{ py: 0.75, px: 1, borderRadius: 2, '&:hover': { bgcolor: '#F8FAFC' } }}>
        <Avatar sx={{ width: 32, height: 32, fontSize: 12.5, fontWeight: 700, bgcolor: alpha(c, 0.15), color: c }}>{iniciales(j.persona)}</Avatar>
        <Box flex={1} minWidth={0}>
          <Typography fontSize={13} fontWeight={700} noWrap>{j.persona}</Typography>
          <Typography fontSize={11.5} color="text.secondary" noWrap>
            {j.estado === 'PAUSADA' ? `Pausa · ${MOTIVOS_PAUSA[j.pausa_actual?.motivo ?? 'OTRO']}`
              : j.tarea ? `${TIPO_TAREA[j.tarea.tipo] ?? j.tarea.tipo} #${j.tarea.id} · ${j.tarea.sku}` : 'Libre'} · {minutos(j.minutos)} en jornada</Typography>
        </Box>
        <Chip size="small" label={j.estado === 'PAUSADA' ? 'Pausa' : j.tarea ? 'Con tarea' : 'Libre'} sx={{ height: 20, fontSize: 10.5, bgcolor: alpha(c, 0.12), color: c, fontWeight: 700 }} />
        <Tooltip title="Mover de estación"><IconButton size="small" onClick={e => setMover({ ancla: e.currentTarget, j })}><SwapHoriz fontSize="small" /></IconButton></Tooltip>
        <Tooltip title="Cerrar su jornada"><IconButton size="small" onClick={() => hacer(() => personal.cerrarDe(j.id), `Jornada de ${j.persona} cerrada`)}><Logout fontSize="small" /></IconButton></Tooltip>
      </Stack>
    )
  }

  return (
    <Layout title="Personal — Tablero">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Groups sx={{ fontSize: 28 }} />} titulo="Personal en operación" color={COLOR}
          subtitulo="Quién está trabajando, en qué estación y en qué tarea; quién falta" />
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap" alignItems="center">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 220 }}>
            <MenuItem value="">Todos</MenuItem>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <Box flex={1} />
          <Button startIcon={<EventNote />} onClick={() => navigate('/personal/programacion')}>Programación</Button>
          <Button startIcon={<Badge />} onClick={() => navigate('/personal/kiosco')}>Kiosco de marcación</Button>
          <Button variant="contained" startIcon={<Hub />} onClick={() => navigate('/personal/estaciones')} sx={{ bgcolor: COLOR, '&:hover': { bgcolor: '#0F766E' } }}>Estaciones</Button>
        </Stack>
        {tablero.isLoading || !d ? <LinearProgress /> : <>
          <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
            {([['Programados hoy', d.resumen.programados, '#6366F1'], ['Presentes', d.resumen.presentes, COLOR], ['Con tarea', d.resumen.con_tarea, '#2563EB'],
              ['En pausa', d.resumen.en_pausa, '#F59E0B'], ['No han llegado', d.resumen.ausentes, '#DC2626'], ['Tareas en cola', d.resumen.en_cola, '#7C3AED']] as const).map(([t, v, c]) =>
              <Grid key={t} size={{ xs: 6, md: 2 }}><Cifra etiqueta={t} valor={v} color={c} /></Grid>)}
          </Grid>

          {!d.estaciones.length && <Alert severity="info" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={() => navigate('/personal/estaciones')}>Crear</Button>}>
            Aún no hay estaciones de trabajo: créelas para programar a las personas y dirigir las tareas.</Alert>}
          <Grid container spacing={1.5}>
            {d.estaciones.map(e => {
              const n = e.trabajando.length, lleno = n >= e.capacidad
              const color = e.color ?? COLOR
              return (
                <Grid key={e.id} size={{ xs: 12, md: 6, lg: 4 }}>
                  <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden', height: '100%', borderTop: `4px solid ${color}` }}>
                    <Box sx={{ px: 2, py: 1.25, display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box flex={1} minWidth={0}>
                        <Stack direction="row" gap={0.75} alignItems="center">
                          <Typography fontWeight={800} noWrap>{e.nombre}</Typography>
                          {e.requiere_montacargas && <Chip size="small" label="Montacargas" sx={{ height: 18, fontSize: 10 }} />}
                        </Stack>
                        <Typography fontSize={11.5} color="text.secondary" fontFamily="Consolas, monospace">{e.codigo} · {TIPOS_ESTACION[e.tipo] ?? e.tipo}</Typography>
                      </Box>
                      <Tooltip title={`${n} trabajando · capacidad ${e.capacidad}`}>
                        <Chip size="small" label={`${n}/${e.capacidad}`} sx={{ fontWeight: 800, bgcolor: alpha(lleno ? '#10B981' : n ? '#F59E0B' : '#94A3B8', 0.15) }} />
                      </Tooltip>
                      {e.en_cola > 0 && <Tooltip title="Tareas esperando en la cola de esta estación"><Chip size="small" icon={<Inventory2 sx={{ fontSize: 14 }} />} label={e.en_cola}
                        sx={{ bgcolor: alpha('#7C3AED', 0.12), color: '#7C3AED', fontWeight: 700 }} /></Tooltip>}
                    </Box>
                    <Box sx={{ px: 1, pb: 1 }}>
                      {e.trabajando.map(j => <Persona key={j.id} j={j} />)}
                      {e.programados.filter(p => !p.presente).map(p => (
                        <Stack key={p.programacion_id} direction="row" alignItems="center" gap={1} sx={{ py: 0.75, px: 1, opacity: 0.6 }}>
                          <Avatar sx={{ width: 32, height: 32, fontSize: 12.5, bgcolor: '#F1F5F9', color: '#94A3B8' }}><PersonOff sx={{ fontSize: 18 }} /></Avatar>
                          <Box flex={1}><Typography fontSize={13} fontWeight={600}>{p.persona}</Typography>
                            <Typography fontSize={11.5} color="text.secondary">Programado{p.hora_inicio ? ` ${p.hora_inicio}` : ''} · no ha marcado entrada</Typography></Box>
                        </Stack>))}
                      {!e.trabajando.length && !e.programados.length && <Typography fontSize={12.5} color="text.disabled" sx={{ px: 1, py: 1 }}>Nadie programado hoy.</Typography>}
                    </Box>
                  </Paper>
                </Grid>
              )
            })}
          </Grid>

          {d.sin_estacion.length > 0 && <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mt: 2 }}>
            <Typography fontWeight={800} mb={0.5}>En jornada sin estación</Typography>
            <Typography fontSize={12.5} color="text.secondary" mb={1}>Trabajan con lo que eligieron al entrar. Asígneles una estación para dirigir sus tareas.</Typography>
            {d.sin_estacion.map(j => <Persona key={j.id} j={j} />)}
          </Paper>}
          {d.ausentes.length > 0 && <Alert severity="warning" sx={{ mt: 2 }}>
            <b>Programados que no han marcado entrada:</b> {d.ausentes.map(a => `${a.persona}${a.hora_inicio ? ` (${a.hora_inicio})` : ''}`).join(', ')}</Alert>}
        </>}

        <Menu anchorEl={mover?.ancla} open={!!mover} onClose={() => setMover(null)}>
          <MenuItem disabled sx={{ fontSize: 12.5, opacity: '1 !important', fontWeight: 700 }}>Mover a {mover?.j.persona} a…</MenuItem>
          {(d?.estaciones ?? []).filter(e => e.id !== mover?.j.estacion_id).map(e =>
            <MenuItem key={e.id} onClick={() => { const j = mover!.j; setMover(null); hacer(() => personal.moverEstacion(j.id, e.id), `${j.persona} pasa a ${e.nombre}`) }}>{e.codigo} · {e.nombre}</MenuItem>)}
          {mover?.j.estacion_id && <MenuItem onClick={() => { const j = mover!.j; setMover(null); hacer(() => personal.moverEstacion(j.id, null), `${j.persona} queda sin estación`) }}>Sin estación</MenuItem>}
        </Menu>
      </Box>
    </Layout>
  )
}
