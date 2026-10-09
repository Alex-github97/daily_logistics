/**
 * WFM · Estaciones de trabajo: los puestos a los que se programa a las personas
 * («Recepción muelle 1», «Montacargas pasillo A», «Picking frentes», «Caja 1»).
 * Cada estación dice qué tareas del WMS recibe quien está en ella, en qué zonas,
 * si exige montacargas y cuántas personas caben.
 */
import { useState } from 'react'
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, LinearProgress,
  MenuItem, Paper, Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography, alpha,
} from '@mui/material'
import { Add, Edit, DeleteOutline, Hub } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms } from '@/api/wmsTrazable'
import { personal, FUNCIONES, TIPOS_ESTACION, type Estacion, type EstacionIn } from '@/api/personal'

const COLOR = '#0D9488'
const FUNC_TIPO: Record<string, string[]> = {
  RECEPCION: ['UBICACION'], UBICACION: ['UBICACION', 'MOVIMIENTO'], REABASTECIMIENTO: ['REABASTECIMIENTO'], PICKING: ['REABASTECIMIENTO'],
  GENERAL: ['UBICACION', 'REABASTECIMIENTO', 'MOVIMIENTO'],
}
const COLORES = ['#0D9488', '#2563EB', '#7C3AED', '#DB2777', '#EA580C', '#CA8A04', '#16A34A', '#475569']
const vacia = (): EstacionIn => ({ codigo: '', nombre: '', tipo: 'GENERAL', almacen_id: null, funciones: FUNC_TIPO.GENERAL, zonas: [],
  requiere_montacargas: false, capacidad: 1, color: COLORES[0], activo: true, notas: null })

export default function PersonalEstaciones() {
  const qc = useQueryClient()
  const estaciones = useQuery({ queryKey: ['wfm-estaciones'], queryFn: () => personal.estaciones() })
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const zonas = useQuery({ queryKey: ['wms-zonas'], queryFn: () => api.get('/wms/zonas/').then(r => r.data as any[]) })
  const [form, setForm] = useState<(EstacionIn & { id?: number }) | null>(null)
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['wfm-estaciones'] }); qc.invalidateQueries({ queryKey: ['wfm-tablero'] }) }
  const guardar = async () => {
    if (!form) return
    try { const { id, ...d } = form; if (id) await personal.editarEstacion(id, d); else await personal.crearEstacion(d)
      toast.success('Estación guardada'); setForm(null); refrescar() } catch (e) { toast.error(errorApi(e)) }
  }
  const nombreAlm = (id: number | null) => id ? almacenes.data?.find(a => a.id === id)?.nombre : 'Cualquiera'

  return (
    <Layout title="Personal — Estaciones">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Hub sx={{ fontSize: 28 }} />} titulo="Estaciones de trabajo" color={COLOR}
          subtitulo="Los puestos a los que se asigna a las personas: qué tareas reciben, en qué zonas y cuántos caben" />
        <Stack direction="row" mb={2}><Box flex={1} />
          <Button variant="contained" startIcon={<Add />} onClick={() => setForm(vacia())} sx={{ bgcolor: COLOR, '&:hover': { bgcolor: '#0F766E' } }}>Nueva estación</Button></Stack>
        {estaciones.isLoading ? <LinearProgress /> : !estaciones.data?.length ? <Alert severity="info">Cree la primera estación: por ejemplo «Recepción muelle 1» o «Montacargas pasillo A».</Alert> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['Estación', 'Tipo', 'Almacén', 'Recibe', 'Zonas', 'Capacidad', 'Estado', ''].map(h =>
                <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC' }}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{estaciones.data.map(e => (
                <TableRow key={e.id} hover sx={{ opacity: e.activo ? 1 : 0.5 }}>
                  <TableCell><Stack direction="row" gap={1} alignItems="center"><Box sx={{ width: 10, height: 28, borderRadius: 1, bgcolor: e.color ?? COLOR }} />
                    <Box><Typography fontWeight={700} fontSize={13.5}>{e.nombre}</Typography>
                      <Typography fontSize={11.5} color="text.secondary" fontFamily="Consolas, monospace">{e.codigo}</Typography></Box></Stack></TableCell>
                  <TableCell sx={{ fontSize: 13 }}>{TIPOS_ESTACION[e.tipo] ?? e.tipo}{e.requiere_montacargas && <Chip size="small" label="Montacargas" sx={{ ml: 0.75, height: 18, fontSize: 10 }} />}</TableCell>
                  <TableCell sx={{ fontSize: 13 }}>{nombreAlm(e.almacen_id)}</TableCell>
                  <TableCell>{e.funciones.length ? e.funciones.map(f => <Chip key={f} size="small" label={FUNCIONES[f] ?? f} sx={{ mr: 0.5, mb: 0.25, height: 20, fontSize: 11 }} />)
                    : <Typography fontSize={12} color="text.secondary">— (sin tareas del WMS)</Typography>}</TableCell>
                  <TableCell sx={{ fontSize: 12.5 }}>{e.zonas.length ? e.zonas.map(z => zonas.data?.find(x => x.id === z)?.codigo ?? z).join(', ') : 'Todas'}</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>{e.capacidad}</TableCell>
                  <TableCell><Chip size="small" label={e.activo ? 'Activa' : 'Inactiva'} sx={{ bgcolor: alpha(e.activo ? '#10B981' : '#94A3B8', 0.12), color: e.activo ? '#047857' : '#64748B', fontWeight: 700 }} /></TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                    <Tooltip title="Editar"><IconButton size="small" onClick={() => setForm({ ...e })}><Edit fontSize="small" /></IconButton></Tooltip>
                    <Tooltip title="Quitar (si tiene historia, se desactiva)"><IconButton size="small" onClick={async () => {
                      try { await personal.borrarEstacion(e.id); refrescar(); toast.success('Estación quitada') } catch (x) { toast.error(errorApi(x)) } }}><DeleteOutline fontSize="small" /></IconButton></Tooltip>
                  </TableCell>
                </TableRow>))}</TableBody>
            </Table>
          </Paper>}

        <Dialog open={!!form} onClose={() => setForm(null)} maxWidth="sm" fullWidth>
          <DialogTitle fontWeight={800}>{form?.id ? 'Editar estación' : 'Nueva estación de trabajo'}</DialogTitle>
          {form && <DialogContent sx={{ pt: '8px !important' }}>
            <Stack gap={2}>
              <Stack direction="row" gap={1.5}>
                <TextField label="Código" value={form.codigo} onChange={e => setForm({ ...form, codigo: e.target.value.toUpperCase() })} sx={{ width: 150 }} />
                <TextField label="Nombre" value={form.nombre} onChange={e => setForm({ ...form, nombre: e.target.value })} sx={{ flex: 1 }} placeholder="Montacargas pasillo A" />
              </Stack>
              <Stack direction="row" gap={1.5}>
                <TextField select label="Tipo" value={form.tipo} sx={{ flex: 1 }}
                  onChange={e => setForm({ ...form, tipo: e.target.value, funciones: FUNC_TIPO[e.target.value] ?? [], requiere_montacargas: e.target.value === 'UBICACION' ? true : form.requiere_montacargas })}>
                  {Object.entries(TIPOS_ESTACION).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
                </TextField>
                <TextField select label="Almacén" value={form.almacen_id ?? ''} sx={{ flex: 1 }} onChange={e => setForm({ ...form, almacen_id: e.target.value === '' ? null : Number(e.target.value), zonas: [] })}>
                  <MenuItem value="">Cualquiera</MenuItem>
                  {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
                </TextField>
              </Stack>
              <Box>
                <Typography fontSize={13} fontWeight={700} mb={0.75}>Tareas del WMS que recibe</Typography>
                <Stack direction="row" gap={1} flexWrap="wrap">
                  {Object.entries(FUNCIONES).map(([k, v]) => { const on = form.funciones.includes(k)
                    return <Chip key={k} label={v} clickable color={on ? 'primary' : 'default'} variant={on ? 'filled' : 'outlined'}
                      onClick={() => setForm({ ...form, funciones: on ? form.funciones.filter(x => x !== k) : [...form.funciones, k] })} /> })}
                </Stack>
                <Typography fontSize={11.5} color="text.secondary" mt={0.5}>Sin ninguna: la estación no recibe tareas del WMS (p. ej. una caja POS o conducción).</Typography>
              </Box>
              <TextField select label="Zonas (vacío = todas)" SelectProps={{ multiple: true }} value={form.zonas} disabled={!form.almacen_id}
                helperText={form.almacen_id ? 'Solo tareas que salen o llegan a estas zonas' : 'Elija el almacén para limitar zonas'}
                onChange={e => setForm({ ...form, zonas: e.target.value as unknown as number[] })}>
                {(zonas.data ?? []).filter(z => z.almacen_id === form.almacen_id).map(z => <MenuItem key={z.id} value={z.id}>{z.codigo} · {z.nombre}</MenuItem>)}
              </TextField>
              <Stack direction="row" gap={1.5} alignItems="center">
                <TextField label="Capacidad (personas)" type="number" value={form.capacidad} onChange={e => setForm({ ...form, capacidad: Math.max(1, Number(e.target.value)) })} sx={{ width: 180 }} />
                <FormControlLabel control={<Switch checked={form.requiere_montacargas} onChange={e => setForm({ ...form, requiere_montacargas: e.target.checked })} />} label="Exige montacargas" />
                <FormControlLabel control={<Switch checked={form.activo} onChange={e => setForm({ ...form, activo: e.target.checked })} />} label="Activa" />
              </Stack>
              <Stack direction="row" gap={0.75} alignItems="center"><Typography fontSize={13} mr={1}>Color</Typography>
                {COLORES.map(c => <Box key={c} onClick={() => setForm({ ...form, color: c })} sx={{ width: 24, height: 24, borderRadius: 1, bgcolor: c, cursor: 'pointer',
                  outline: form.color === c ? `2px solid ${c}` : 'none', outlineOffset: 2 }} />)}</Stack>
            </Stack>
          </DialogContent>}
          <DialogActions><Button color="inherit" onClick={() => setForm(null)}>Cancelar</Button>
            <Button variant="contained" disabled={!form?.codigo.trim() || !form?.nombre.trim()} onClick={guardar} sx={{ bgcolor: COLOR }}>Guardar</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
