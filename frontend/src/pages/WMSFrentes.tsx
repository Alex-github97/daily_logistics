/**
 * WMS · Frentes de picking y reabastecimiento.
 *
 * Cada frente es la ubicación de la que se alista (o se vende, en la sala POS)
 * un producto, con mínimo y máximo en unidades o empaques. Bajo el mínimo nace
 * un reabastecimiento desde la reserva (por aprobar del supervisor, si así se
 * configura). Los frentes alternos (prioridad 2, 3…) se habilitan cuando hace
 * falta. Arriba, las reglas del almacén.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Autocomplete, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton,
  LinearProgress, MenuItem, Paper, Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography, alpha,
} from '@mui/material'
import { Add, Edit, DeleteOutline, Bolt, Storefront, Tune, Search } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, errorApi } from '@/components/comun/Registro'
import { wms, num } from '@/api/wmsTrazable'
import { apiClient as api } from '@/api/client'
import { bodega, type ConfigTareas, type Frente, type FrenteIn } from '@/api/tareasBodega'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const EST: Record<string, { t: string; c: string }> = {
  OK: { t: 'En rango', c: '#10B981' }, BAJO: { t: 'Bajo el mínimo', c: '#F59E0B' }, AGOTADO: { t: 'Agotado', c: '#EF4444' },
  SOBRE: { t: 'Sobre el máximo', c: '#6366F1' }, SIN_EMPAQUE: { t: 'Sin empaque', c: '#64748B' },
}
const UNIDADES: Record<string, string> = { UNIDAD: 'Unidades', CAJA: 'Cajas', MASTER: 'Cajas máster', ESTIBA: 'Estibas' }

const REGLAS: [keyof ConfigTareas, string, string][] = [
  ['reabastecimiento_activo', 'Reabastecimiento automático', 'Bajo el mínimo se crea la tarea desde la reserva'],
  ['requiere_aprobacion', 'Requiere aprobación del supervisor', 'Las tareas nacen «por aprobar»'],
  ['picking_solo_frentes', 'El picking sale solo de frentes', 'Para los productos que tienen frente'],
  ['picking_reserva_si_falta', 'Si los frentes no alcanzan, tomar de la reserva', 'Si no, se pide un reabastecimiento urgente'],
  ['picking_excluir_pos', 'No alistar de la sala de ventas (POS)', 'La sala se reabastece, no se alista'],
  ['exigir_escaneo_origen', 'Exigir escanear el origen', 'Evita tomar de la ubicación equivocada'],
]

export default function WMSFrentes() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const cfg = useQuery({ queryKey: ['config-tareas', almacen], enabled: !!almacen, queryFn: () => bodega.config(Number(almacen)) })
  const frentes = useQuery({ queryKey: ['frentes', almacen], enabled: !!almacen, refetchInterval: 30_000, queryFn: () => bodega.frentes(Number(almacen)) })
  const productos = useQuery({ queryKey: ['wms-productos-lista'], queryFn: wms.productos })
  const ubicaciones = useQuery({ queryKey: ['wms-ubicaciones-lista'], queryFn: wms.ubicaciones })
  const zonas = useQuery({ queryKey: ['wms-zonas'], queryFn: () => api.get('/wms/zonas/').then(r => r.data as any[]) })
  const [form, setForm] = useState<(FrenteIn & { id?: number }) | null>(null)
  const [buscar, setBuscar] = useState('')
  const [filtro, setFiltro] = useState<'todos' | 'alerta' | 'pos'>('todos')
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['frentes'] }); qc.invalidateQueries({ queryKey: ['config-tareas'] }) }

  const guardarCfg = async (parche: Partial<ConfigTareas>) => {
    try { await bodega.guardarConfig(Number(almacen), { ...cfg.data!, ...parche }); refrescar(); toast.success('Regla guardada') }
    catch (e) { toast.error(errorApi(e)) }
  }
  const guardar = async () => {
    if (!form) return
    try {
      const { id, ...d } = form
      if (id) await bodega.editarFrente(id, d); else await bodega.crearFrente(d)
      toast.success(id ? 'Frente actualizado' : 'Frente creado'); setForm(null); refrescar()
    } catch (e) { toast.error(errorApi(e)) }
  }
  const alternar = async (f: Frente) => {
    try { await bodega.editarFrente(f.id, { almacen_id: f.almacen_id, producto_id: f.producto_id, ubicacion_id: f.ubicacion_id, unidad: f.unidad,
      minimo: f.minimo, maximo: f.maximo, prioridad: f.prioridad, activo: !f.activo }); refrescar() } catch (e) { toast.error(errorApi(e)) }
  }
  const evaluar = async () => {
    try { const r = await bodega.evaluar(Number(almacen))
      toast.success(r.creadas.length ? `${r.creadas.length} reabastecimientos creados${cfg.data?.requiere_aprobacion ? ' (por aprobar en Tareas)' : ''}` : 'Todos los frentes están cubiertos')
      if (r.sin_reserva.length) toast.error(`${r.sin_reserva.length} frente(s) bajo mínimo sin reserva en la bodega`)
      refrescar(); qc.invalidateQueries({ queryKey: ['tareas-op'] })
    } catch (e) { toast.error(errorApi(e)) }
  }

  const lista = useMemo(() => (frentes.data ?? []).filter(f =>
    (!buscar || `${f.sku} ${f.producto} ${f.ubicacion}`.toLowerCase().includes(buscar.toLowerCase())) &&
    (filtro === 'todos' || (filtro === 'pos' ? f.sala_pos : ['BAJO', 'AGOTADO', 'SIN_EMPAQUE'].includes(f.estado)))), [frentes.data, buscar, filtro])
  const resumen = useMemo(() => {
    const fs = frentes.data ?? []
    return { total: fs.length, alerta: fs.filter(f => ['BAJO', 'AGOTADO'].includes(f.estado)).length,
      agotados: fs.filter(f => f.estado === 'AGOTADO').length, camino: fs.filter(f => f.tareas_abiertas > 0).length, pos: fs.filter(f => f.sala_pos).length }
  }, [frentes.data])
  // Ubicaciones que pueden ser frente: del almacén, fuera de recepción, cuarentena, despacho y tránsito.
  const zonasValidas = new Map((zonas.data ?? []).filter(z => z.almacen_id === almacen && !['RECEPCION', 'CUARENTENA', 'DESPACHO', 'TRANSITO'].includes(z.tipo)).map(z => [z.id, z]))
  const ubicAlmacen = (ubicaciones.data ?? []).filter((u: any) => u.activo !== false && zonasValidas.has(u.zona_id))

  return (
    <Layout title="WMS — Frentes de picking">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Storefront sx={{ fontSize: 28 }} />} titulo="Frentes de picking y reabastecimiento" color={COLOR}
          subtitulo="De dónde se alista cada producto, con su mínimo y máximo; bajo el mínimo se reabastece desde la reserva" />
        <Stack direction="row" gap={1.5} mb={2} alignItems="center" flexWrap="wrap">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(Number(e.target.value))} sx={{ minWidth: 240 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <Box flex={1} />
          <Button startIcon={<Bolt />} onClick={evaluar} disabled={!almacen}>Evaluar ahora</Button>
          <Button variant="contained" startIcon={<Add />} sx={{ bgcolor: COLOR }} disabled={!almacen}
            onClick={() => setForm({ almacen_id: Number(almacen), producto_id: 0, ubicacion_id: 0, unidad: 'UNIDAD', minimo: 0, maximo: 0, prioridad: 1, activo: true })}>Nuevo frente</Button>
        </Stack>

        {/* reglas */}
        {cfg.data && <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
          <Stack direction="row" alignItems="center" gap={1} mb={1}><Tune sx={{ color: COLOR }} /><Typography fontWeight={800}>Reglas del almacén</Typography></Stack>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' }, columnGap: 2 }}>
            {REGLAS.map(([k, t, d]) => (
              <FormControlLabel key={k} sx={{ alignItems: 'flex-start', m: 0, py: 0.5 }}
                control={<Switch size="small" checked={!!cfg.data![k]} onChange={e => guardarCfg({ [k]: e.target.checked })} />}
                label={<Box sx={{ pl: 0.5 }}><Typography fontSize={13.5} fontWeight={600}>{t}</Typography><Typography fontSize={11.5} color="text.secondary">{d}</Typography></Box>} />
            ))}
          </Box>
          <Stack direction="row" gap={1.5} mt={1.5} flexWrap="wrap">
            {([['liberar_asignada_min', 'Liberar asignadas sin empezar (min)'], ['alerta_en_curso_min', 'Alertar tareas en curso (min)'], ['nivel_montacargas', 'Montacargas desde el nivel']] as const).map(([k, t]) => (
              <TextField key={`${almacen}-${k}`} size="small" type="number" label={t} defaultValue={cfg.data![k]} sx={{ width: 250 }}
                onBlur={e => Number(e.target.value) > 0 && Number(e.target.value) !== cfg.data![k] && guardarCfg({ [k]: Number(e.target.value) })} />
            ))}
          </Stack>
        </Paper>}

        {/* resumen */}
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap">
          {[['Frentes', resumen.total, COLOR], ['Bajo mínimo / agotados', resumen.alerta, '#F59E0B'], ['Agotados', resumen.agotados, '#EF4444'],
            ['Con reabastecimiento en camino', resumen.camino, '#0891B2'], ['En la sala POS', resumen.pos, '#8B5CF6']].map(([t, v, c]) => (
            <Paper key={t as string} variant="outlined" sx={{ px: 2, py: 1.25, borderRadius: 2.5, minWidth: 150, borderTop: `3px solid ${c}` }}>
              <Typography fontSize={22} fontWeight={800} sx={{ color: c as string }}>{v as number}</Typography>
              <Typography fontSize={12} color="text.secondary">{t as string}</Typography>
            </Paper>))}
        </Stack>

        <Stack direction="row" gap={1.5} mb={1.5} alignItems="center" flexWrap="wrap">
          <TextField size="small" placeholder="Buscar producto o ubicación" value={buscar} onChange={e => setBuscar(e.target.value)}
            InputProps={{ startAdornment: <Search fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} /> }} sx={{ width: 300 }} />
          {([['todos', 'Todos'], ['alerta', 'Necesitan reabastecer'], ['pos', 'Sala POS']] as const).map(([k, t]) =>
            <Chip key={k} label={t} clickable color={filtro === k ? 'primary' : 'default'} variant={filtro === k ? 'filled' : 'outlined'} onClick={() => setFiltro(k)} />)}
        </Stack>

        {frentes.isLoading ? <LinearProgress /> : !lista.length ? <Alert severity="info">
          {frentes.data?.length ? 'Ningún frente coincide.' : 'Aún no hay frentes: cree uno por producto (la ubicación de la que se alista o se vende) con su mínimo y máximo.'}</Alert> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['Producto', 'Frente', 'Mín. – Máx.', 'Nivel actual', 'Estado', 'En camino', 'Habilitado', ''].map(h =>
                <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC', whiteSpace: 'nowrap' }}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{lista.map(f => {
                const e = EST[f.estado] ?? EST.OK
                const pct = f.maximo_u ? Math.min(100, (f.actual / f.maximo_u) * 100) : 0
                const pmin = f.maximo_u ? Math.min(100, (f.minimo_u / f.maximo_u) * 100) : 0
                return (
                  <TableRow key={f.id} hover sx={{ opacity: f.activo ? 1 : 0.55 }}>
                    <TableCell><Typography fontSize={13} fontWeight={700}>{f.producto}</Typography>
                      <Typography fontSize={11.5} color="text.secondary" fontFamily="Consolas, monospace">{f.sku}</Typography></TableCell>
                    <TableCell><Stack direction="row" gap={0.75} alignItems="center">
                      <Typography fontFamily="Consolas, monospace" fontWeight={700} fontSize={13}>{f.ubicacion}</Typography>
                      {f.sala_pos && <Chip size="small" label="POS" sx={{ height: 18, fontSize: 10, bgcolor: alpha('#8B5CF6', 0.12), color: '#7C3AED' }} />}
                      {f.prioridad > 1 && <Chip size="small" label={`Alterno ${f.prioridad}`} sx={{ height: 18, fontSize: 10 }} />}
                    </Stack><Typography fontSize={11} color="text.secondary">{f.zona}</Typography></TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}><Typography fontSize={13}>{num(f.minimo)} – {num(f.maximo)} {UNIDADES[f.unidad]?.toLowerCase()}</Typography>
                      {f.unidad !== 'UNIDAD' && <Typography fontSize={11} color="text.secondary">{num(f.minimo_u)} – {num(f.maximo_u)} und</Typography>}</TableCell>
                    <TableCell sx={{ minWidth: 170 }}>
                      <Box sx={{ position: 'relative', height: 8, borderRadius: 4, bgcolor: '#F1F5F9', overflow: 'hidden' }}>
                        <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: e.c, borderRadius: 4 }} />
                        <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: `${pmin}%`, width: 2, bgcolor: '#0F172A', opacity: 0.5 }} />
                      </Box>
                      <Typography fontSize={11.5} mt={0.4}>{num(f.actual)} und{f.factor && f.factor > 1 ? ` (${num(Math.round(f.actual / f.factor * 10) / 10)} ${UNIDADES[f.unidad]?.toLowerCase()})` : ''}</Typography>
                    </TableCell>
                    <TableCell><Chip size="small" label={e.t} sx={{ bgcolor: alpha(e.c, 0.12), color: e.c, fontWeight: 700 }} /></TableCell>
                    <TableCell><Typography fontSize={12.5}>{f.en_camino ? `${num(f.en_camino)} und` : '—'}</Typography>
                      {f.tareas_abiertas > 0 && <Typography fontSize={11} color="text.secondary">{f.tareas_abiertas} tarea(s)</Typography>}</TableCell>
                    <TableCell><Switch size="small" checked={f.activo} onChange={() => alternar(f)} /></TableCell>
                    <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                      <Tooltip title="Editar"><IconButton size="small" onClick={() => setForm({ id: f.id, almacen_id: f.almacen_id, producto_id: f.producto_id, ubicacion_id: f.ubicacion_id,
                        unidad: f.unidad, minimo: f.minimo, maximo: f.maximo, prioridad: f.prioridad, activo: f.activo })}><Edit fontSize="small" /></IconButton></Tooltip>
                      <Tooltip title="Quitar"><IconButton size="small" onClick={async () => { try { await bodega.borrarFrente(f.id); refrescar(); toast.success('Frente quitado') } catch (e) { toast.error(errorApi(e)) } }}>
                        <DeleteOutline fontSize="small" /></IconButton></Tooltip>
                    </TableCell>
                  </TableRow>
                )
              })}</TableBody>
            </Table>
          </Paper>}

        <Dialog open={!!form} onClose={() => setForm(null)} maxWidth="sm" fullWidth>
          <DialogTitle fontWeight={800}>{form?.id ? 'Editar frente' : 'Nuevo frente de picking'}</DialogTitle>
          {form && <DialogContent sx={{ pt: '8px !important' }}>
            <Stack gap={2}>
              <Autocomplete options={productos.data ?? []} value={(productos.data ?? []).find((p: any) => p.id === form.producto_id) ?? null}
                getOptionLabel={(p: any) => `${p.sku} · ${p.nombre}`} onChange={(_, p: any) => setForm({ ...form, producto_id: p?.id ?? 0 })}
                renderInput={p => <TextField {...p} label="Producto" />} />
              <Autocomplete options={ubicAlmacen} value={ubicAlmacen.find((u: any) => u.id === form.ubicacion_id) ?? null}
                getOptionLabel={(u: any) => `${u.codigo}${zonasValidas.get(u.zona_id)?.vendible_pos ? ' · sala POS' : ''}`} onChange={(_, u: any) => setForm({ ...form, ubicacion_id: u?.id ?? 0 })}
                renderInput={p => <TextField {...p} label="Ubicación del frente" helperText="La de alistar (p. ej. nivel 1) o una góndola de la sala POS" />} />
              <Stack direction="row" gap={1.5}>
                <TextField select label="Se mide en" value={form.unidad} onChange={e => setForm({ ...form, unidad: e.target.value })} sx={{ flex: 1 }}>
                  {Object.entries(UNIDADES).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
                </TextField>
                <TextField label="Mínimo" type="number" value={form.minimo} onChange={e => setForm({ ...form, minimo: Number(e.target.value) })} sx={{ width: 120 }} />
                <TextField label="Máximo" type="number" value={form.maximo} onChange={e => setForm({ ...form, maximo: Number(e.target.value) })} sx={{ width: 120 }} />
              </Stack>
              <Stack direction="row" gap={1.5} alignItems="center">
                <TextField select label="Tipo de frente" value={form.prioridad} onChange={e => setForm({ ...form, prioridad: Number(e.target.value) })} sx={{ flex: 1 }}>
                  <MenuItem value={1}>Principal</MenuItem>{[2, 3, 4].map(p => <MenuItem key={p} value={p}>Alterno {p}</MenuItem>)}
                </TextField>
                <FormControlLabel control={<Switch checked={form.activo} onChange={e => setForm({ ...form, activo: e.target.checked })} />} label="Habilitado" />
              </Stack>
              <Alert severity="info" icon={false} sx={{ fontSize: 12.5 }}>
                Cuando lo que hay (más lo que viene en camino) quede bajo el mínimo, se crea un reabastecimiento desde la reserva hasta el máximo,
                redondeado al empaque. Un alterno deshabilitado no se usa ni se reabastece hasta habilitarlo.</Alert>
            </Stack>
          </DialogContent>}
          <DialogActions><Button color="inherit" onClick={() => setForm(null)}>Cancelar</Button>
            <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!form?.producto_id || !form?.ubicacion_id || !(form?.maximo > 0)} onClick={guardar}>Guardar</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
