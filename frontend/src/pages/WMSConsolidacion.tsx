/**
 * WMS · Consolidación y despacho
 *
 * Lo alistado espera en el staging de salida. Cada orden tiene un DESTINO
 * (obligatorio): solo se consolidan juntas las del mismo destino. Se consolida
 * por lotes (varias órdenes en un consolidado) o individual, se cierra con sus
 * bultos (etiqueta con código de barras), se asigna el modo de despacho —en
 * lote o uno a uno— y «Solicitar transporte» lo envía al TMS, donde se carga
 * en los vehículos.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Box, Button, Checkbox, Chip, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, LinearProgress,
  MenuItem, Paper, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  CallMerge, Place, EditLocationAlt, LockOutlined, LockOpen, Print, LocalShipping, Category, DeleteOutline, ExpandMore,
  ExpandLess, Send, Close, CallSplit,
} from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, Cifra, errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms, fechaHora, num } from '@/api/wmsTrazable'
import { consolidacion as cx, MODOS, ESTADO_CONS, type Consolidado, type OrdenPorConsolidar } from '@/api/consolidacion'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const kg = (v?: number | null) => v == null ? '—' : `${v.toLocaleString('es-CO', { maximumFractionDigits: 1 })} kg`
const m3 = (v?: number | null) => v == null ? '—' : `${v.toLocaleString('es-CO', { maximumFractionDigits: 3 })} m³`
const ModoChip = ({ m }: { m?: string | null }) => m ? <Chip size="small" label={MODOS[m]?.corto ?? m}
  sx={{ height: 20, fontSize: 11, fontWeight: 700, bgcolor: alpha(MODOS[m]?.color ?? '#64748B', 0.12), color: MODOS[m]?.color }} />
  : <Typography fontSize={12} color="text.disabled">Sin modo</Typography>

export default function WMSConsolidacion() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const [tab, setTab] = useState(0)
  const a = almacen || undefined
  const porCons = useQuery({ queryKey: ['cons-por', almacen], enabled: !!almacen, refetchInterval: 20_000, queryFn: () => cx.porConsolidar(a) })
  const consolidados = useQuery({ queryKey: ['cons-lista', almacen], enabled: !!almacen, refetchInterval: 20_000,
    queryFn: () => cx.consolidados({ almacen_id: a, estado: 'ABIERTO,CERRADO,SOLICITADO,EN_CARGUE' }) })
  const historial = useQuery({ queryKey: ['cons-hist', almacen], enabled: !!almacen && tab === 2,
    queryFn: () => cx.consolidados({ almacen_id: a, estado: 'DESPACHADO,ENTREGADO' }) })
  const solicitudes = useQuery({ queryKey: ['cons-sol', almacen], enabled: !!almacen && tab === 3, queryFn: () => cx.solicitudes({ almacen_id: a }) })
  const trans = useQuery({ queryKey: ['wms-transportadoras'], queryFn: () => api.get('/wms/transportadoras/').then(r => r.data as any[]) })

  const [marcadasO, setMarcadasO] = useState<Set<number>>(new Set())
  const [marcadosC, setMarcadosC] = useState<Set<number>>(new Set())
  const [abierto, setAbierto] = useState<number | null>(null)
  const [destino, setDestino] = useState<OrdenPorConsolidar | null>(null)
  const [fd, setFd] = useState({ destino: '', ciudad: '', direccion: '', contacto: '', telefono: '' })
  const [cerrar, setCerrar] = useState<Consolidado | null>(null)
  const [bultos, setBultos] = useState('1')
  const [modo, setModo] = useState<{ ids: number[]; modo: string; transportadora_id: number | ''; guia: string } | null>(null)
  const refrescar = () => ['cons-por', 'cons-lista', 'cons-hist', 'cons-sol'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
  const hacer = async (f: () => Promise<unknown>, ok: string) => { try { await f(); toast.success(ok); refrescar() } catch (e) { toast.error(errorApi(e)) } }

  const grupos = useMemo(() => {
    const m = new Map<string, OrdenPorConsolidar[]>()
    for (const o of porCons.data ?? []) m.set(o.destino ?? '', [...(m.get(o.destino ?? '') ?? []), o])
    return [...m.entries()].sort((x, y) => (x[0] === '' ? -1 : y[0] === '' ? 1 : x[0].localeCompare(y[0])))
  }, [porCons.data])
  const abiertos = (consolidados.data ?? []).filter(c => c.estado === 'ABIERTO')
  const lista = consolidados.data ?? []
  const listosParaSolicitar = lista.filter(c => marcadosC.has(c.id) && c.estado === 'CERRADO' && c.modo_despacho)
  const kpi = {
    ordenes: porCons.data?.length ?? 0, sinDestino: (porCons.data ?? []).filter(o => !o.destino).length,
    abiertos: abiertos.length, cerrados: lista.filter(c => c.estado === 'CERRADO').length,
    sinModo: lista.filter(c => ['ABIERTO', 'CERRADO'].includes(c.estado) && !c.modo_despacho).length,
    solicitados: lista.filter(c => ['SOLICITADO', 'EN_CARGUE'].includes(c.estado)).length,
  }

  const consolidarGrupo = async (ids: number[], individual: boolean) => {
    try { const r = await cx.consolidar(ids, individual)
      toast.success(individual ? `${r.length} consolidados individuales` : `Consolidado ${r[0].codigo} creado`)
      setMarcadasO(new Set()); refrescar(); setTab(1) } catch (e) { toast.error(errorApi(e)) }
  }

  return (
    <Layout title="WMS — Consolidación y despacho">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<CallMerge sx={{ fontSize: 28 }} />} titulo="Consolidación y despacho" color={COLOR}
          subtitulo="Lo alistado se consolida por destino, se le asigna el modo de despacho y se solicita el transporte al TMS" />
        <Stack direction="row" gap={1.5} mb={2} alignItems="center" flexWrap="wrap">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => { setAlmacen(Number(e.target.value)); setMarcadasO(new Set()); setMarcadosC(new Set()) }} sx={{ minWidth: 240 }}>
            {(almacenes.data ?? []).map(x => <MenuItem key={x.id} value={x.id}>{x.nombre}</MenuItem>)}
          </TextField>
          <Box flex={1} />
          <Button startIcon={<LocalShipping />} onClick={() => navigate('/tms/asignacion-carga')}>Asignación de carga (TMS)</Button>
        </Stack>
        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          {([['Órdenes por consolidar', kpi.ordenes, '#D97706', kpi.sinDestino ? `${kpi.sinDestino} sin destino` : undefined],
            ['Consolidando', kpi.abiertos, '#F59E0B', undefined], ['Cerrados', kpi.cerrados, '#2563EB', undefined],
            ['Sin modo de despacho', kpi.sinModo, '#DC2626', undefined], ['Transporte solicitado', kpi.solicitados, '#7C3AED', 'en el TMS']] as const).map(([t, v, c, s]) =>
            <Grid key={t} size={{ xs: 6, md: 2.4 }}><Cifra etiqueta={t} valor={v} color={c} sub={s} /></Grid>)}
        </Grid>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label={`Por consolidar (${kpi.ordenes})`} /><Tab label={`Consolidados (${lista.length})`} /><Tab label="Despachados" /><Tab label="Solicitudes de transporte" />
        </Tabs>

        {/* ── Por consolidar: agrupado por destino ── */}
        {tab === 0 && (porCons.isLoading ? <LinearProgress /> : !grupos.length ? <Alert severity="info">No hay órdenes alistadas esperando consolidación.</Alert> :
          <Stack gap={1.5}>
            {grupos.map(([dest, ords]) => {
              const sel = ords.filter(o => marcadasO.has(o.id))
              const abiertosDest = abiertos.filter(c => c.destino === dest)
              const sinDest = dest === ''
              return (
                <Paper key={dest || 'sin'} variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden', borderLeft: `4px solid ${sinDest ? '#DC2626' : COLOR}` }}>
                  <Stack direction="row" alignItems="center" gap={1.25} sx={{ px: 2, py: 1.25, bgcolor: sinDest ? alpha('#DC2626', 0.05) : alpha(COLOR, 0.04), flexWrap: 'wrap' }}>
                    <Place sx={{ color: sinDest ? '#DC2626' : COLOR }} />
                    <Box flex={1} minWidth={200}>
                      <Typography fontWeight={800} fontSize={16}>{sinDest ? 'Sin destino' : dest}</Typography>
                      <Typography fontSize={12} color="text.secondary">{sinDest ? 'Asigne el destino a cada orden: sin destino no se puede consolidar'
                        : `${ords.length} orden(es) · ${kg(ords.reduce((s, o) => s + (o.peso_kg ?? 0), 0))} · ${m3(ords.reduce((s, o) => s + (o.volumen_m3 ?? 0), 0))}`}</Typography>
                    </Box>
                    {!sinDest && <>
                      <Button size="small" variant="contained" startIcon={<CallMerge />} disabled={!sel.length} onClick={() => consolidarGrupo(sel.map(o => o.id), false)}
                        sx={{ bgcolor: COLOR }}>Consolidar en lote{sel.length ? ` (${sel.length})` : ''}</Button>
                      <Button size="small" startIcon={<CallSplit />} disabled={!sel.length} onClick={() => consolidarGrupo(sel.map(o => o.id), true)}>Individual</Button>
                      {abiertosDest.length > 0 && <TextField select size="small" label="Agregar a…" value="" disabled={!sel.length} sx={{ minWidth: 170 }}
                        onChange={e => hacer(async () => { await cx.agregar(Number(e.target.value), sel.map(o => o.id)); setMarcadasO(new Set()) }, 'Órdenes agregadas al consolidado')}>
                        {abiertosDest.map(c => <MenuItem key={c.id} value={c.id}>{c.codigo} ({c.ordenes.length})</MenuItem>)}
                      </TextField>}
                    </>}
                  </Stack>
                  <Table size="small">
                    <TableHead><TableRow>
                      <TableCell padding="checkbox">{!sinDest && <Checkbox size="small" checked={sel.length === ords.length} indeterminate={sel.length > 0 && sel.length < ords.length}
                        onChange={e => setMarcadasO(s => { const n = new Set(s); ords.forEach(o => e.target.checked ? n.add(o.id) : n.delete(o.id)); return n })} />}</TableCell>
                      {['Orden', 'Pedido / cliente', 'Entrega en', 'Unidades', 'Peso', 'Volumen', ''].map(h => <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12 }}>{h}</TableCell>)}
                    </TableRow></TableHead>
                    <TableBody>{ords.map(o => (
                      <TableRow key={o.id} hover selected={marcadasO.has(o.id)}>
                        <TableCell padding="checkbox">{!sinDest && <Checkbox size="small" checked={marcadasO.has(o.id)}
                          onChange={() => setMarcadasO(s => { const n = new Set(s); n.has(o.id) ? n.delete(o.id) : n.add(o.id); return n })} />}</TableCell>
                        <TableCell sx={{ fontFamily: 'Consolas, monospace', fontWeight: 700 }}>{o.numero}</TableCell>
                        <TableCell><Typography fontSize={13} fontWeight={600}>{o.pedido ?? o.cliente}</Typography>
                          <Typography fontSize={11} color="text.secondary">{o.plataforma ?? o.canal ?? o.cliente}</Typography></TableCell>
                        <TableCell sx={{ fontSize: 12.5, maxWidth: 280 }}>{o.destino_direccion ?? '—'}{o.destino_ciudad ? ` · ${o.destino_ciudad}` : ''}
                          {o.destino_contacto && <Typography fontSize={11} color="text.secondary">{o.destino_contacto}{o.destino_telefono ? ` · ${o.destino_telefono}` : ''}</Typography>}</TableCell>
                        <TableCell>{num(o.unidades)}</TableCell><TableCell>{kg(o.peso_kg)}</TableCell><TableCell>{m3(o.volumen_m3)}</TableCell>
                        <TableCell align="right"><Tooltip title="Destino de la orden"><Button size="small" color={sinDest ? 'error' : 'primary'} startIcon={<EditLocationAlt />}
                          onClick={() => { setDestino(o); setFd({ destino: o.destino ?? o.destino_ciudad ?? '', ciudad: o.destino_ciudad ?? '', direccion: o.destino_direccion ?? '',
                            contacto: o.destino_contacto ?? '', telefono: o.destino_telefono ?? '' }) }}>{sinDest ? 'Asignar destino' : 'Destino'}</Button></Tooltip></TableCell>
                      </TableRow>))}</TableBody>
                  </Table>
                </Paper>
              )
            })}
          </Stack>)}

        {/* ── Consolidados ── */}
        {tab === 1 && (consolidados.isLoading ? <LinearProgress /> : !lista.length ? <Alert severity="info">No hay consolidados en curso.</Alert> : <>
          <Stack direction="row" gap={1} mb={1.25} alignItems="center" flexWrap="wrap">
            <Button variant="outlined" startIcon={<Category />} disabled={!lista.some(c => marcadosC.has(c.id) && ['ABIERTO', 'CERRADO'].includes(c.estado))}
              onClick={() => setModo({ ids: lista.filter(c => marcadosC.has(c.id) && ['ABIERTO', 'CERRADO'].includes(c.estado)).map(c => c.id), modo: 'PAQUETEO_URBANO_PROPIO', transportadora_id: '', guia: '' })}>
              Asignar modo de despacho{marcadosC.size ? ` (${marcadosC.size})` : ''}</Button>
            <Button variant="contained" startIcon={<Send />} disabled={!listosParaSolicitar.length} sx={{ bgcolor: COLOR }}
              onClick={() => hacer(async () => { const r = await cx.solicitar(listosParaSolicitar.map(c => c.id))
                toast.success(r.solicitudes.map(s => `${s.codigo}: ${s.consolidados} · ${s.modo}`).join(' — ')); setMarcadosC(new Set()) }, 'Transporte solicitado al TMS')}>
              Solicitar transporte{listosParaSolicitar.length ? ` (${listosParaSolicitar.length})` : ''}</Button>
            <Typography fontSize={12.5} color="text.secondary">Se solicita lo cerrado y con modo; el TMS lo asigna a los vehículos.</Typography>
          </Stack>
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell padding="checkbox" sx={{ bgcolor: '#F8FAFC' }} />
                {['Consolidado', 'Destino', 'Estado', 'Pedidos', 'Bultos', 'Peso', 'Volumen', 'Modo de despacho', 'Solicitud', ''].map(h =>
                  <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC', whiteSpace: 'nowrap' }}>{h}</TableCell>)}
              </TableRow></TableHead>
              <TableBody>{lista.map(c => {
                const e = ESTADO_CONS[c.estado] ?? { t: c.estado, c: '#64748B' }
                const editable = ['ABIERTO', 'CERRADO'].includes(c.estado)
                return [
                  <TableRow key={c.id} hover selected={marcadosC.has(c.id)}>
                    <TableCell padding="checkbox"><Checkbox size="small" disabled={!editable} checked={marcadosC.has(c.id)}
                      onChange={() => setMarcadosC(s => { const n = new Set(s); n.has(c.id) ? n.delete(c.id) : n.add(c.id); return n })} /></TableCell>
                    <TableCell><Stack direction="row" alignItems="center" gap={0.5}>
                      <IconButton size="small" onClick={() => setAbierto(abierto === c.id ? null : c.id)}>{abierto === c.id ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}</IconButton>
                      <Typography fontFamily="Consolas, monospace" fontWeight={800} fontSize={13}>{c.codigo}</Typography>
                      {c.individual && <Chip size="small" label="Individual" sx={{ height: 18, fontSize: 10 }} />}</Stack></TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>{c.destino}</TableCell>
                    <TableCell><Chip size="small" label={e.t} sx={{ bgcolor: alpha(e.c, 0.12), color: e.c, fontWeight: 700, height: 22 }} /></TableCell>
                    <TableCell>{c.ordenes.length}</TableCell><TableCell>{c.bultos}</TableCell><TableCell>{kg(c.peso_kg)}</TableCell><TableCell>{m3(c.volumen_m3)}</TableCell>
                    <TableCell><ModoChip m={c.modo_despacho} />{c.transportadora && <Typography fontSize={11} color="text.secondary">{c.transportadora}{c.guia ? ` · guía ${c.guia}` : ''}</Typography>}</TableCell>
                    <TableCell sx={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>{c.solicitud ?? '—'}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                      {c.estado === 'ABIERTO' && <Tooltip title="Cerrar (bultos)"><IconButton size="small" color="primary" onClick={() => { setCerrar(c); setBultos(String(c.ordenes.length)) }}><LockOutlined fontSize="small" /></IconButton></Tooltip>}
                      {c.estado === 'CERRADO' && <Tooltip title="Reabrir"><IconButton size="small" onClick={() => hacer(() => cx.reabrir(c.id), 'Reabierto')}><LockOpen fontSize="small" /></IconButton></Tooltip>}
                      {editable && <Tooltip title="Modo de despacho"><IconButton size="small" onClick={() => setModo({ ids: [c.id], modo: c.modo_despacho ?? 'PAQUETEO_URBANO_PROPIO', transportadora_id: c.transportadora_id ?? '', guia: c.guia ?? '' })}><Category fontSize="small" /></IconButton></Tooltip>}
                      <Tooltip title="Etiqueta"><IconButton size="small" onClick={() => cx.etiqueta(c.id).catch(x => toast.error(errorApi(x)))}><Print fontSize="small" /></IconButton></Tooltip>
                      {editable && <Tooltip title="Deshacer consolidado"><IconButton size="small" onClick={() => hacer(() => cx.anular(c.id), 'Consolidado deshecho: sus órdenes vuelven a «por consolidar»')}><DeleteOutline fontSize="small" /></IconButton></Tooltip>}
                    </TableCell>
                  </TableRow>,
                  <TableRow key={`d${c.id}`}><TableCell colSpan={11} sx={{ p: 0, border: abierto === c.id ? undefined : 0 }}>
                    <Collapse in={abierto === c.id}><Box sx={{ px: 6, py: 1.25, bgcolor: '#FAFAFB' }}>
                      {c.ordenes.map(o => <Stack key={o.orden_id} direction="row" alignItems="center" gap={1.5} sx={{ py: 0.4 }}>
                        <Typography fontFamily="Consolas, monospace" fontSize={12.5} fontWeight={700} width={110}>{o.numero}</Typography>
                        <Typography fontSize={12.5} width={130}>{o.pedido ?? ''}</Typography>
                        <Typography fontSize={12.5} flex={1}>{o.direccion ?? ''}{o.contacto ? ` · ${o.contacto}` : ''}</Typography>
                        <Typography fontSize={12} color="text.secondary">{kg(o.peso_kg)}</Typography>
                        {c.estado === 'ABIERTO' && <IconButton size="small" onClick={() => hacer(() => cx.quitarOrden(c.id, o.orden_id), 'Orden devuelta a «por consolidar»')}><Close fontSize="small" /></IconButton>}
                      </Stack>)}
                      {c.notas && <Typography fontSize={12} color="text.secondary" mt={0.5}>{c.notas}</Typography>}
                    </Box></Collapse>
                  </TableCell></TableRow>,
                ]
              })}</TableBody>
            </Table>
          </Paper>
        </>)}

        {/* ── Despachados ── */}
        {tab === 2 && (historial.isLoading ? <LinearProgress /> : !historial.data?.length ? <Alert severity="info">Aún no hay consolidados despachados.</Alert> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['Consolidado', 'Destino', 'Estado', 'Pedidos', 'Bultos', 'Modo', 'Creado'].map(h => <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC' }}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{historial.data.map(c => { const e = ESTADO_CONS[c.estado] ?? { t: c.estado, c: '#64748B' }; return (
                <TableRow key={c.id} hover><TableCell sx={{ fontFamily: 'Consolas, monospace', fontWeight: 700 }}>{c.codigo}</TableCell><TableCell>{c.destino}</TableCell>
                  <TableCell><Chip size="small" label={e.t} sx={{ bgcolor: alpha(e.c, 0.12), color: e.c, fontWeight: 700, height: 22 }} /></TableCell>
                  <TableCell>{c.ordenes.length}</TableCell><TableCell>{c.bultos}</TableCell><TableCell><ModoChip m={c.modo_despacho} /></TableCell><TableCell sx={{ fontSize: 12 }}>{fechaHora(c.creado)}</TableCell></TableRow>) })}</TableBody>
            </Table>
          </Paper>)}

        {/* ── Solicitudes ── */}
        {tab === 3 && (solicitudes.isLoading ? <LinearProgress /> : !solicitudes.data?.length ? <Alert severity="info">Aún no se ha solicitado transporte.</Alert> :
          <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>{['Solicitud', 'Modo', 'Transportadora', 'Estado', 'Consolidados', 'Pendientes', 'En cargue', 'Despachados', 'Bultos', 'Peso', 'Creada'].map(h =>
                <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC', whiteSpace: 'nowrap' }}>{h}</TableCell>)}</TableRow></TableHead>
              <TableBody>{solicitudes.data.map(s => (
                <TableRow key={s.id} hover><TableCell sx={{ fontFamily: 'Consolas, monospace', fontWeight: 700 }}>{s.codigo}</TableCell><TableCell><ModoChip m={s.modo_despacho} /></TableCell>
                  <TableCell sx={{ fontSize: 12.5 }}>{s.transportadora ?? '—'}</TableCell><TableCell><Chip size="small" label={s.estado.toLowerCase().replace('_', ' ')} sx={{ height: 20, textTransform: 'capitalize' }} /></TableCell>
                  <TableCell>{s.consolidados}</TableCell><TableCell>{s.pendientes}</TableCell><TableCell>{s.en_cargue}</TableCell><TableCell>{s.despachados}</TableCell>
                  <TableCell>{s.bultos}</TableCell><TableCell>{kg(s.peso_kg)}</TableCell><TableCell sx={{ fontSize: 12 }}>{fechaHora(s.creada)}</TableCell></TableRow>))}</TableBody>
            </Table>
          </Paper>)}

        {/* ── Diálogos ── */}
        <Dialog open={!!destino} onClose={() => setDestino(null)} maxWidth="sm" fullWidth>
          <DialogTitle fontWeight={800}>Destino de la orden {destino?.numero}</DialogTitle>
          <DialogContent sx={{ pt: '8px !important' }}><Stack gap={2}>
            <TextField label="Destino de consolidación" value={fd.destino} onChange={e => setFd({ ...fd, destino: e.target.value })}
              helperText="Solo se consolidan juntas las órdenes con el mismo destino (p. ej. BOGOTA, MEDELLIN, BOGOTA NORTE)" />
            <Stack direction="row" gap={1.5}>
              <TextField label="Ciudad" value={fd.ciudad} onChange={e => setFd({ ...fd, ciudad: e.target.value })} sx={{ flex: 1 }} />
              <TextField label="Teléfono" value={fd.telefono} onChange={e => setFd({ ...fd, telefono: e.target.value })} sx={{ flex: 1 }} />
            </Stack>
            <TextField label="Dirección de entrega" value={fd.direccion} onChange={e => setFd({ ...fd, direccion: e.target.value })} />
            <TextField label="Recibe" value={fd.contacto} onChange={e => setFd({ ...fd, contacto: e.target.value })} />
          </Stack></DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setDestino(null)}>Cancelar</Button>
            <Button variant="contained" disabled={fd.destino.trim().length < 2} sx={{ bgcolor: COLOR }}
              onClick={() => { const o = destino!; setDestino(null); hacer(() => cx.destino(o.id, { destino: fd.destino, ciudad: fd.ciudad || null, direccion: fd.direccion || null,
                contacto: fd.contacto || null, telefono: fd.telefono || null }), 'Destino guardado') }}>Guardar</Button></DialogActions>
        </Dialog>
        <Dialog open={!!cerrar} onClose={() => setCerrar(null)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={800}>Cerrar {cerrar?.codigo}</DialogTitle>
          <DialogContent><Typography fontSize={13} color="text.secondary" mb={2}>{cerrar?.ordenes.length} pedido(s) para {cerrar?.destino}. Indique cuántos bultos quedaron: se imprime una etiqueta por bulto.</Typography>
            <TextField autoFocus fullWidth type="number" label="Bultos" value={bultos} onChange={e => setBultos(e.target.value)} /></DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setCerrar(null)}>Volver</Button>
            <Button variant="contained" disabled={!(Number(bultos) >= 1)} sx={{ bgcolor: COLOR }} onClick={() => { const c = cerrar!; setCerrar(null)
              hacer(async () => { await cx.cerrar(c.id, Number(bultos)); await cx.etiqueta(c.id) }, `${c.codigo} cerrado`) }}>Cerrar e imprimir etiquetas</Button></DialogActions>
        </Dialog>
        <Dialog open={!!modo} onClose={() => setModo(null)} maxWidth="sm" fullWidth>
          <DialogTitle fontWeight={800}>Modo de despacho {modo && modo.ids.length > 1 ? `· ${modo.ids.length} consolidados (lote)` : ''}</DialogTitle>
          {modo && <DialogContent sx={{ pt: '8px !important' }}><Stack gap={2}>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
              {Object.entries(MODOS).map(([k, v]) => (
                <Paper key={k} variant="outlined" onClick={() => setModo({ ...modo, modo: k })} sx={{ p: 1.5, borderRadius: 2, cursor: 'pointer',
                  borderColor: modo.modo === k ? v.color : undefined, bgcolor: modo.modo === k ? alpha(v.color, 0.06) : undefined, borderWidth: modo.modo === k ? 2 : 1 }}>
                  <Typography fontWeight={800} fontSize={13.5} sx={{ color: modo.modo === k ? v.color : undefined }}>{v.nombre}</Typography>
                  <Typography fontSize={11.5} color="text.secondary">{v.tercerizado ? 'Lo recoge una transportadora' : 'Vehículos propios'}</Typography>
                </Paper>))}
            </Box>
            {MODOS[modo.modo]?.tercerizado && <>
              <TextField select label="Transportadora" value={modo.transportadora_id} onChange={e => setModo({ ...modo, transportadora_id: Number(e.target.value) })}>
                {(trans.data ?? []).filter(t => t.activo !== false).map(t => <MenuItem key={t.id} value={t.id}>{t.nombre}</MenuItem>)}
              </TextField>
              {modo.ids.length === 1 && <TextField label="Guía de la transportadora (opcional)" value={modo.guia} onChange={e => setModo({ ...modo, guia: e.target.value })} />}
            </>}
          </Stack></DialogContent>}
          <DialogActions><Button color="inherit" onClick={() => setModo(null)}>Cancelar</Button>
            <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!modo || (MODOS[modo.modo]?.tercerizado && !modo.transportadora_id)}
              onClick={() => { const m = modo!; setModo(null); hacer(async () => { await cx.modo(m.ids, m.modo, m.transportadora_id || null, m.guia || null); setMarcadosC(new Set()) }, 'Modo de despacho asignado') }}>Asignar</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
