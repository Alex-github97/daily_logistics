/**
 * WFM · Personas: el perfil operativo de cada usuario — carné (para marcar en el
 * kiosco), cargo, habilidades (montacargas, picking, caja…), almacén y estación
 * habitual. Las estaciones que exigen una habilidad solo admiten a quien la tiene.
 */
import { useMemo, useState } from 'react'
import {
  Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, LinearProgress, MenuItem,
  Paper, Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography, alpha,
} from '@mui/material'
import { Badge, Edit, QrCode2, Search } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, errorApi } from '@/components/comun/Registro'
import { wms } from '@/api/wmsTrazable'
import { personal, HABILIDADES, type Persona } from '@/api/personal'

const COLOR = '#0D9488'

export default function PersonalPersonas() {
  const qc = useQueryClient()
  const personas = useQuery({ queryKey: ['wfm-personas'], queryFn: personal.personas })
  const estaciones = useQuery({ queryKey: ['wfm-estaciones'], queryFn: () => personal.estaciones() })
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [form, setForm] = useState<Persona | null>(null)
  const [buscar, setBuscar] = useState('')
  const refrescar = () => qc.invalidateQueries({ queryKey: ['wfm-personas'] })
  const lista = useMemo(() => (personas.data ?? []).filter(p => !buscar || `${p.nombre} ${p.username} ${p.carne ?? ''}`.toLowerCase().includes(buscar.toLowerCase())), [personas.data, buscar])
  const guardar = async () => {
    if (!form) return
    try { await personal.guardarPersona(form.usuario_id, { carne: form.carne, cargo: form.cargo, habilidades: form.habilidades,
      almacen_id: form.almacen_id, estacion_id: form.estacion_id, activo: form.activo }); toast.success('Persona guardada'); setForm(null); refrescar() }
    catch (e) { toast.error(errorApi(e)) }
  }

  return (
    <Layout title="Personal — Personas">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Badge sx={{ fontSize: 28 }} />} titulo="Personas" color={COLOR}
          subtitulo="Carné para marcar, habilidades y estación habitual de cada persona que opera" />
        <TextField size="small" placeholder="Buscar persona o carné" value={buscar} onChange={e => setBuscar(e.target.value)} sx={{ width: 320, mb: 2 }}
          InputProps={{ startAdornment: <Search fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} /> }} />
        {personas.isLoading ? <LinearProgress /> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['Persona', 'Carné', 'Cargo', 'Habilidades', 'Estación habitual', 'Ahora', ''].map(h =>
                <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC' }}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{lista.map(p => (
                <TableRow key={p.usuario_id} hover sx={{ opacity: p.activo ? 1 : 0.5 }}>
                  <TableCell><Typography fontWeight={700} fontSize={13.5}>{p.nombre}</Typography>
                    <Typography fontSize={11.5} color="text.secondary">{p.username} · {p.rol.replace(/_/g, ' ').toLowerCase()}</Typography></TableCell>
                  <TableCell>{p.carne ? <Chip size="small" icon={<QrCode2 sx={{ fontSize: 15 }} />} label={p.carne} sx={{ fontFamily: 'Consolas, monospace' }} />
                    : <Button size="small" onClick={async () => { try { await personal.generarCarne(p.usuario_id); refrescar(); toast.success('Carné generado') } catch (e) { toast.error(errorApi(e)) } }}>Generar carné</Button>}</TableCell>
                  <TableCell sx={{ fontSize: 13 }}>{p.cargo ?? '—'}</TableCell>
                  <TableCell>{p.habilidades.map(h => <Chip key={h} size="small" label={HABILIDADES[h] ?? h} sx={{ mr: 0.5, mb: 0.25, height: 20, fontSize: 11,
                    ...(h === 'MONTACARGAS' ? { bgcolor: alpha('#EA580C', 0.12), color: '#C2410C' } : {}) }} />)}</TableCell>
                  <TableCell sx={{ fontSize: 13 }}>{estaciones.data?.find(e => e.id === p.estacion_id)?.nombre ?? '—'}</TableCell>
                  <TableCell>{p.jornada ? <Chip size="small" label={p.jornada.estado === 'PAUSADA' ? 'En pausa' : 'Trabajando'}
                    sx={{ bgcolor: alpha(p.jornada.estado === 'PAUSADA' ? '#F59E0B' : '#10B981', 0.12), color: p.jornada.estado === 'PAUSADA' ? '#B45309' : '#047857', fontWeight: 700 }} />
                    : <Typography fontSize={12} color="text.disabled">—</Typography>}</TableCell>
                  <TableCell align="right"><Tooltip title="Editar"><IconButton size="small" onClick={() => setForm({ ...p })}><Edit fontSize="small" /></IconButton></Tooltip></TableCell>
                </TableRow>))}</TableBody>
            </Table>
          </Paper>}

        <Dialog open={!!form} onClose={() => setForm(null)} maxWidth="sm" fullWidth>
          <DialogTitle fontWeight={800}>{form?.nombre}</DialogTitle>
          {form && <DialogContent sx={{ pt: '8px !important' }}>
            <Stack gap={2}>
              <Stack direction="row" gap={1.5}>
                <TextField label="Carné" value={form.carne ?? ''} onChange={e => setForm({ ...form, carne: e.target.value.toUpperCase() || null })} sx={{ flex: 1 }}
                  helperText="El código que se escanea en el kiosco" inputProps={{ style: { fontFamily: 'Consolas, monospace' } }} />
                <TextField label="Cargo" value={form.cargo ?? ''} onChange={e => setForm({ ...form, cargo: e.target.value || null })} sx={{ flex: 1 }} />
              </Stack>
              <Box>
                <Typography fontSize={13} fontWeight={700} mb={0.75}>Habilidades</Typography>
                <Stack direction="row" gap={0.75} flexWrap="wrap">
                  {Object.entries(HABILIDADES).map(([k, v]) => { const on = form.habilidades.includes(k)
                    return <Chip key={k} label={v} clickable color={on ? 'primary' : 'default'} variant={on ? 'filled' : 'outlined'}
                      onClick={() => setForm({ ...form, habilidades: on ? form.habilidades.filter(x => x !== k) : [...form.habilidades, k] })} /> })}
                </Stack>
              </Box>
              <Stack direction="row" gap={1.5}>
                <TextField select label="Almacén habitual" value={form.almacen_id ?? ''} sx={{ flex: 1 }} onChange={e => setForm({ ...form, almacen_id: e.target.value === '' ? null : Number(e.target.value) })}>
                  <MenuItem value="">—</MenuItem>{(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
                </TextField>
                <TextField select label="Estación habitual" value={form.estacion_id ?? ''} sx={{ flex: 1 }} onChange={e => setForm({ ...form, estacion_id: e.target.value === '' ? null : Number(e.target.value) })}
                  helperText="Si no está programado, entra aquí">
                  <MenuItem value="">—</MenuItem>{(estaciones.data ?? []).filter(e => e.activo).map(e => <MenuItem key={e.id} value={e.id}>{e.codigo} · {e.nombre}</MenuItem>)}
                </TextField>
              </Stack>
              <FormControlLabel control={<Switch checked={form.activo} onChange={e => setForm({ ...form, activo: e.target.checked })} />} label="Activa en Personal (puede marcar y recibir tareas)" />
            </Stack>
          </DialogContent>}
          <DialogActions><Button color="inherit" onClick={() => setForm(null)}>Cancelar</Button>
            <Button variant="contained" onClick={guardar} sx={{ bgcolor: COLOR }}>Guardar</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
