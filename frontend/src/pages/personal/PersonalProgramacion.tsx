/**
 * WFM · Programación: quién va a qué estación cada día (y en qué horario).
 * Al marcar la entrada, la persona queda en la estación programada. Se puede
 * copiar el día anterior y avisa si una estación pasa de su capacidad o si
 * alguien no tiene la habilidad que la estación exige.
 */
import { useMemo, useState } from 'react'
import {
  Alert, Avatar, Box, Button, Chip, IconButton, LinearProgress, MenuItem, Paper, Stack, Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import { EventNote, ChevronLeft, ChevronRight, ContentCopy, Close, PersonAdd } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, errorApi } from '@/components/comun/Registro'
import { wms } from '@/api/wmsTrazable'
import { personal, TIPOS_ESTACION, TURNOS } from '@/api/personal'

const COLOR = '#0D9488'
const iso = (d: Date) => d.toLocaleDateString('en-CA')
const mover = (f: string, dias: number) => { const d = new Date(`${f}T12:00:00`); d.setDate(d.getDate() + dias); return iso(d) }
const iniciales = (n?: string | null) => (n ?? '?').split(' ').filter(Boolean).slice(0, 2).map(x => x[0]).join('').toUpperCase()

export default function PersonalProgramacion() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  const [fecha, setFecha] = useState(iso(new Date()))
  const estaciones = useQuery({ queryKey: ['wfm-estaciones', almacen], queryFn: () => personal.estaciones(almacen || undefined) })
  const personas = useQuery({ queryKey: ['wfm-personas'], queryFn: personal.personas })
  const prog = useQuery({ queryKey: ['wfm-programacion', fecha, almacen], queryFn: () => personal.programacion(fecha, almacen || undefined) })
  const [nuevo, setNuevo] = useState<Record<number, { usuario_id: number | ''; turno: string; hora_inicio: string; hora_fin: string }>>({})
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['wfm-programacion'] }); qc.invalidateQueries({ queryKey: ['wfm-tablero'] }) }
  const programados = useMemo(() => new Set((prog.data ?? []).map(p => p.usuario_id)), [prog.data])
  const activas = (estaciones.data ?? []).filter(e => e.activo)
  const libres = (personas.data ?? []).filter(p => p.activo && !programados.has(p.usuario_id))
  const dia = new Date(`${fecha}T12:00:00`).toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' })

  const agregar = async (estacion_id: number) => {
    const n = nuevo[estacion_id]
    if (!n?.usuario_id) return
    try {
      const r = await personal.programar({ fecha, estacion_id, usuario_id: Number(n.usuario_id), turno: n.turno, hora_inicio: n.hora_inicio || null, hora_fin: n.hora_fin || null })
      if (r.aviso) toast(r.aviso, { icon: '⚠️' }); else toast.success('Programado')
      setNuevo(s => ({ ...s, [estacion_id]: { ...n, usuario_id: '' } })); refrescar()
    } catch (e) { toast.error(errorApi(e)) }
  }

  return (
    <Layout title="Personal — Programación">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<EventNote sx={{ fontSize: 28 }} />} titulo="Programación de estaciones" color={COLOR}
          subtitulo="Quién trabaja en qué estación cada día; al marcar entrada, cada persona queda en la suya" />
        <Stack direction="row" gap={1.5} mb={2} alignItems="center" flexWrap="wrap">
          <IconButton onClick={() => setFecha(mover(fecha, -1))}><ChevronLeft /></IconButton>
          <TextField size="small" type="date" label="Día" value={fecha} onChange={e => e.target.value && setFecha(e.target.value)} InputLabelProps={{ shrink: true }} />
          <IconButton onClick={() => setFecha(mover(fecha, 1))}><ChevronRight /></IconButton>
          <Typography fontWeight={700} sx={{ textTransform: 'capitalize' }}>{dia}</Typography>
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 200 }}>
            <MenuItem value="">Todos</MenuItem>{(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <Box flex={1} />
          <Button startIcon={<ContentCopy />} onClick={async () => {
            try { const r = await personal.copiar(mover(fecha, -1), fecha); toast.success(r.copiadas ? `${r.copiadas} programaciones copiadas del día anterior` : 'No había nada nuevo que copiar'); refrescar() }
            catch (e) { toast.error(errorApi(e)) } }}>Copiar el día anterior</Button>
        </Stack>
        {(prog.isLoading || estaciones.isLoading) ? <LinearProgress /> : !activas.length ? <Alert severity="info">Primero cree las estaciones de trabajo.</Alert> : <>
          {libres.length > 0 && <Alert severity="info" icon={false} sx={{ mb: 2, fontSize: 13 }}>
            <b>Sin programar este día ({libres.length}):</b> {libres.slice(0, 12).map(p => p.nombre).join(', ')}{libres.length > 12 ? '…' : ''}</Alert>}
          <Grid container spacing={1.5}>
            {activas.map(e => {
              const filas = (prog.data ?? []).filter(p => p.estacion_id === e.id)
              const n = nuevo[e.id] ?? { usuario_id: '', turno: 'DIA', hora_inicio: '', hora_fin: '' }
              const sobre = filas.length > e.capacidad
              return (
                <Grid key={e.id} size={{ xs: 12, md: 6, lg: 4 }}>
                  <Paper variant="outlined" sx={{ borderRadius: 3, p: 1.5, height: '100%', borderTop: `4px solid ${e.color ?? COLOR}` }}>
                    <Stack direction="row" alignItems="center" gap={1} mb={1}>
                      <Box flex={1}><Typography fontWeight={800}>{e.nombre}</Typography>
                        <Typography fontSize={11.5} color="text.secondary">{e.codigo} · {TIPOS_ESTACION[e.tipo] ?? e.tipo}{e.requiere_montacargas ? ' · montacargas' : ''}</Typography></Box>
                      <Chip size="small" label={`${filas.length}/${e.capacidad}`} sx={{ fontWeight: 800, bgcolor: alpha(sobre ? '#DC2626' : filas.length ? COLOR : '#94A3B8', 0.14), color: sobre ? '#DC2626' : undefined }} />
                    </Stack>
                    {filas.map(p => (
                      <Stack key={p.id} direction="row" alignItems="center" gap={1} sx={{ py: 0.5 }}>
                        <Avatar sx={{ width: 28, height: 28, fontSize: 11.5, bgcolor: alpha(e.color ?? COLOR, 0.15), color: e.color ?? COLOR, fontWeight: 700 }}>{iniciales(p.persona)}</Avatar>
                        <Box flex={1}><Typography fontSize={13} fontWeight={600}>{p.persona}</Typography>
                          <Typography fontSize={11} color="text.secondary">{TURNOS[p.turno] ?? p.turno}{p.hora_inicio ? ` · ${p.hora_inicio}–${p.hora_fin ?? ''}` : ''}</Typography></Box>
                        <Tooltip title="Quitar"><IconButton size="small" onClick={async () => { try { await personal.desprogramar(p.id); refrescar() } catch (x) { toast.error(errorApi(x)) } }}><Close fontSize="small" /></IconButton></Tooltip>
                      </Stack>))}
                    <Box sx={{ mt: 1, pt: 1, borderTop: '1px dashed #E2E8F0' }}>
                      <TextField select size="small" fullWidth label="Agregar persona" value={n.usuario_id}
                        onChange={x => setNuevo(s => ({ ...s, [e.id]: { ...n, usuario_id: Number(x.target.value) } }))}>
                        {libres.map(p => <MenuItem key={p.usuario_id} value={p.usuario_id} disabled={e.requiere_montacargas && !p.habilidades.includes('MONTACARGAS')}>
                          {p.nombre}{e.requiere_montacargas && !p.habilidades.includes('MONTACARGAS') ? ' (sin montacargas)' : ''}</MenuItem>)}
                      </TextField>
                      {!!n.usuario_id && <Stack direction="row" gap={1} mt={1} alignItems="center">
                        <TextField select size="small" label="Turno" value={n.turno} onChange={x => setNuevo(s => ({ ...s, [e.id]: { ...n, turno: x.target.value } }))} sx={{ width: 130 }}>
                          {Object.entries(TURNOS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
                        </TextField>
                        <TextField size="small" type="time" label="Desde" value={n.hora_inicio} onChange={x => setNuevo(s => ({ ...s, [e.id]: { ...n, hora_inicio: x.target.value } }))} InputLabelProps={{ shrink: true }} sx={{ width: 110 }} />
                        <TextField size="small" type="time" label="Hasta" value={n.hora_fin} onChange={x => setNuevo(s => ({ ...s, [e.id]: { ...n, hora_fin: x.target.value } }))} InputLabelProps={{ shrink: true }} sx={{ width: 110 }} />
                        <IconButton color="primary" onClick={() => agregar(e.id)}><PersonAdd /></IconButton>
                      </Stack>}
                    </Box>
                  </Paper>
                </Grid>
              )
            })}
          </Grid>
        </>}
      </Box>
    </Layout>
  )
}
