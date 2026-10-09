/**
 * TMS · Asignación de carga a vehículos
 *
 * El WMS solicita transporte para consolidados (con destino y modo de
 * despacho). Aquí se arma cada cargue: se elige el vehículo (o la
 * transportadora y su placa, si es tercerizado) y se le suben consolidados con
 * un clic o escaneando su etiqueta —radiofrecuencia o lector de código de
 * barras—, viendo el peso y el volumen contra la capacidad. Al confirmar nacen
 * los despachos y el viaje con sus paradas; de ahí sigue el flujo normal
 * (conductor, salida, entrega). El cargue queda guardado: otra terminal puede
 * abrirlo y seguir escaneando.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, LinearProgress, MenuItem, Paper, Stack,
  Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  LocalShipping, QrCodeScanner, Add, Close, CheckCircle, Inventory2, Place, Search, OpenInNew, Undo, PlaylistAdd,
} from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { Encabezado, errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms } from '@/api/wmsTrazable'
import { consolidacion as cx, MODOS, type Cargue, type CargueIn, type Consolidado } from '@/api/consolidacion'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const kg = (v?: number | null) => v == null ? '—' : `${v.toLocaleString('es-CO', { maximumFractionDigits: 1 })} kg`
const m3 = (v?: number | null) => v == null ? '—' : `${v.toLocaleString('es-CO', { maximumFractionDigits: 3 })} m³`

function Barra({ etiqueta, pct, valor }: { etiqueta: string; pct: number | null | undefined; valor: string }) {
  const p = Math.min(100, pct ?? 0), c = (pct ?? 0) > 100 ? '#DC2626' : (pct ?? 0) > 85 ? '#F59E0B' : '#10B981'
  return (
    <Box flex={1}>
      <Stack direction="row" justifyContent="space-between"><Typography fontSize={12} fontWeight={700}>{etiqueta}</Typography>
        <Typography fontSize={12} color="text.secondary">{valor}{pct != null ? ` · ${Math.round(pct)}%` : ''}</Typography></Stack>
      <Box sx={{ height: 10, borderRadius: 5, bgcolor: '#E2E8F0', overflow: 'hidden', mt: 0.5 }}><Box sx={{ width: `${p}%`, height: '100%', bgcolor: c, transition: 'width .3s' }} /></Box>
    </Box>
  )
}

export default function TMSAsignacionCarga() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const cargues = useQuery({ queryKey: ['tms-cargues'], refetchInterval: 8_000, queryFn: () => cx.cargues('ARMANDO') })
  const [activo, setActivo] = useState<number | null>(null)
  const cargue: Cargue | undefined = (cargues.data ?? []).find(k => k.id === activo)
  const pendiente = useQuery({ queryKey: ['tms-carga-pendiente', almacen, cargue?.modo_despacho], enabled: !!almacen, refetchInterval: 8_000,
    queryFn: () => cx.cargaPendiente({ almacen_id: almacen || undefined, modo: cargue?.modo_despacho }) })
  const solicitudes = useQuery({ queryKey: ['tms-solicitudes', almacen], enabled: !!almacen, refetchInterval: 15_000,
    queryFn: () => cx.solicitudes({ almacen_id: almacen || undefined, estado: 'PENDIENTE,EN_CARGUE' }) })
  const vehiculos = useQuery({ queryKey: ['tms-vehiculos-lista'], queryFn: () => api.get('/tms/vehiculos').then(r => (Array.isArray(r.data) ? r.data : r.data.items) as any[]) })
  const trans = useQuery({ queryKey: ['wms-transportadoras'], queryFn: () => api.get('/wms/transportadoras/').then(r => r.data as any[]) })
  const [nuevo, setNuevo] = useState<CargueIn | null>(null)
  const [buscar, setBuscar] = useState('')
  const [codigo, setCodigo] = useState('')
  const [ultimo, setUltimo] = useState<{ ok: boolean; texto: string } | null>(null)
  const [confirmar, setConfirmar] = useState(false)
  const [listo, setListo] = useState<{ viaje_id: number; viaje: string; despachos: number; paradas: number } | null>(null)
  const scan = useRef<HTMLInputElement>(null)
  useEffect(() => { if (!activo && cargues.data?.length) setActivo(cargues.data[0].id) }, [cargues.data, activo])
  useEffect(() => { if (cargue) setTimeout(() => scan.current?.focus(), 100) }, [cargue?.id])
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['tms-cargues'] }); qc.invalidateQueries({ queryKey: ['tms-carga-pendiente'] }); qc.invalidateQueries({ queryKey: ['tms-solicitudes'] }) }

  const asignar = async (d: { codigo?: string; consolidado_id?: number }) => {
    if (!cargue) { toast.error('Abra o cree un cargue primero'); return }
    try { const k = await cx.asignar(cargue.id, d); const c = k.consolidados.find(x => d.consolidado_id ? x.id === d.consolidado_id : x.codigo === d.codigo?.toUpperCase())
      setUltimo({ ok: true, texto: `${c?.codigo ?? d.codigo} cargado · ${c?.destino ?? ''}` }); refrescar() }
    catch (e) { setUltimo({ ok: false, texto: errorApi(e) }); toast.error(errorApi(e)) }
  }
  const crear = async () => {
    if (!nuevo) return
    try { const k = await cx.crearCargue(nuevo); setNuevo(null); setActivo(k.id); toast.success(`Cargue ${k.codigo} abierto`); refrescar() } catch (e) { toast.error(errorApi(e)) }
  }

  const visibles = useMemo(() => (pendiente.data ?? []).filter(c => !buscar || `${c.codigo} ${c.destino} ${c.ordenes.map(o => o.pedido).join(' ')}`.toLowerCase().includes(buscar.toLowerCase())), [pendiente.data, buscar])
  const porDestino = useMemo(() => {
    const m = new Map<string, Consolidado[]>()
    for (const c of visibles) m.set(c.destino, [...(m.get(c.destino) ?? []), c])
    return [...m.entries()]
  }, [visibles])
  const cap = cargue?.capacidad

  return (
    <Layout title="TMS — Asignación de carga">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<LocalShipping sx={{ fontSize: 28 }} />} titulo="Asignación de carga a vehículos" color={COLOR}
          subtitulo="Los consolidados que pidió el WMS se suben a cada vehículo con clic, radiofrecuencia o escáner; al confirmar nace el viaje" />
        <Stack direction="row" gap={1.5} mb={2} alignItems="center" flexWrap="wrap">
          <TextField select size="small" label="Almacén de salida" value={almacen} onChange={e => setAlmacen(Number(e.target.value))} sx={{ minWidth: 220 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          {(solicitudes.data ?? []).length > 0 && <Chip label={`${solicitudes.data!.length} solicitud(es) abiertas · ${solicitudes.data!.reduce((s, x) => s + x.pendientes, 0)} consolidados por cargar`}
            sx={{ bgcolor: alpha('#7C3AED', 0.1), color: '#7C3AED', fontWeight: 700 }} />}
          <Box flex={1} />
          <Button variant="contained" startIcon={<Add />} disabled={!almacen} sx={{ bgcolor: COLOR }}
            onClick={() => setNuevo({ almacen_id: Number(almacen), modo_despacho: 'PAQUETEO_URBANO_PROPIO', vehiculo_id: null, transportadora_id: null, placa_tercero: '' })}>Nuevo cargue</Button>
        </Stack>

        {/* cargues en armado */}
        {(cargues.data ?? []).length > 0 && <Stack direction="row" gap={1} mb={2} flexWrap="wrap">
          {cargues.data!.map(k => <Chip key={k.id} clickable onClick={() => setActivo(k.id)} icon={<LocalShipping sx={{ fontSize: 16 }} />}
            label={`${k.codigo} · ${k.vehiculo ?? k.transportadora ?? 'sin vehículo'} · ${k.totales.consolidados}`}
            sx={{ fontWeight: 700, bgcolor: k.id === activo ? alpha(COLOR, 0.15) : undefined, border: k.id === activo ? `1px solid ${COLOR}` : undefined }} />)}
        </Stack>}

        <Grid container spacing={2}>
          {/* ── Carga pendiente ── */}
          <Grid size={{ xs: 12, md: 5 }}>
            <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
              <Box sx={{ px: 2, py: 1.25, borderBottom: '1px solid', borderColor: 'divider', bgcolor: '#FCFCFD' }}>
                <Typography fontWeight={800}>Carga por asignar</Typography>
                <Typography fontSize={12} color="text.secondary">{cargue ? `Solo lo de ${MODOS[cargue.modo_despacho]?.nombre.toLowerCase()}` : 'Todos los modos'} · clic en + para subirlo al cargue</Typography>
                <TextField size="small" fullWidth placeholder="Buscar destino, consolidado o pedido" value={buscar} onChange={e => setBuscar(e.target.value)} sx={{ mt: 1 }}
                  InputProps={{ startAdornment: <Search fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} /> }} />
              </Box>
              <Box sx={{ maxHeight: 620, overflowY: 'auto' }}>
                {pendiente.isLoading ? <LinearProgress /> : !visibles.length ? <Typography sx={{ p: 2 }} color="text.secondary" fontSize={13}>No hay carga pendiente{cargue ? ' de este modo' : ''}.</Typography> :
                  porDestino.map(([dest, cs]) => (
                    <Box key={dest}>
                      <Stack direction="row" alignItems="center" gap={1} sx={{ px: 2, py: 0.75, bgcolor: '#F8FAFC', borderBottom: '1px solid #EEF2F7' }}>
                        <Place sx={{ fontSize: 17, color: COLOR }} /><Typography fontWeight={800} fontSize={13}>{dest}</Typography>
                        <Typography fontSize={11.5} color="text.secondary">{cs.length} consolidado(s) · {kg(cs.reduce((s, c) => s + (c.peso_kg ?? 0), 0))}</Typography>
                        <Box flex={1} />
                        {cargue && cs.length > 1 && <Tooltip title="Subir todo el destino"><IconButton size="small" onClick={async () => { for (const c of cs) await asignar({ consolidado_id: c.id }) }}><PlaylistAdd fontSize="small" /></IconButton></Tooltip>}
                      </Stack>
                      {cs.map(c => (
                        <Stack key={c.id} direction="row" alignItems="center" gap={1} sx={{ px: 2, py: 1, borderBottom: '1px solid #F1F5F9', '&:hover': { bgcolor: '#FAFAFB' } }}>
                          <Inventory2 sx={{ color: MODOS[c.modo_despacho ?? '']?.color ?? '#94A3B8', fontSize: 20 }} />
                          <Box flex={1} minWidth={0}>
                            <Typography fontFamily="Consolas, monospace" fontWeight={800} fontSize={13}>{c.codigo}</Typography>
                            <Typography fontSize={11.5} color="text.secondary" noWrap>{c.ordenes.length} pedido(s) · {c.bultos} bulto(s) · {kg(c.peso_kg)} · {m3(c.volumen_m3)}
                              {!cargue && ` · ${MODOS[c.modo_despacho ?? '']?.corto ?? ''}`}{c.transportadora ? ` · ${c.transportadora}` : ''}</Typography>
                          </Box>
                          <Tooltip title="Devolver al WMS"><IconButton size="small" onClick={async () => { const m = window.prompt(`¿Por qué se devuelve ${c.codigo} al WMS?`); if (!m) return
                            try { await cx.devolver(c.id, m); toast.success('Devuelto al WMS'); refrescar() } catch (e) { toast.error(errorApi(e)) } }}><Undo fontSize="small" /></IconButton></Tooltip>
                          <Tooltip title={cargue ? `Subir a ${cargue.codigo}` : 'Abra un cargue'}><span><IconButton size="small" color="primary" disabled={!cargue} onClick={() => asignar({ consolidado_id: c.id })}><Add /></IconButton></span></Tooltip>
                        </Stack>))}
                    </Box>))}
              </Box>
            </Paper>
          </Grid>

          {/* ── Cargue activo ── */}
          <Grid size={{ xs: 12, md: 7 }}>
            {!cargue ? <Paper variant="outlined" sx={{ p: 4, borderRadius: 3, textAlign: 'center' }}>
              <LocalShipping sx={{ fontSize: 48, color: '#CBD5E1' }} />
              <Typography fontWeight={800} fontSize={18} mt={1}>Abra un cargue</Typography>
              <Typography color="text.secondary" fontSize={13.5} mb={2}>Elija el modo de despacho y el vehículo (o la transportadora) y empiece a subir los consolidados.</Typography>
              <Button variant="contained" startIcon={<Add />} disabled={!almacen} sx={{ bgcolor: COLOR }}
                onClick={() => setNuevo({ almacen_id: Number(almacen), modo_despacho: 'PAQUETEO_URBANO_PROPIO', vehiculo_id: null, transportadora_id: null, placa_tercero: '' })}>Nuevo cargue</Button>
            </Paper> : <Paper variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden', borderColor: alpha(COLOR, 0.4) }}>
              <Stack direction="row" alignItems="center" gap={1.5} sx={{ px: 2, py: 1.5, bgcolor: alpha(COLOR, 0.05), flexWrap: 'wrap' }}>
                <LocalShipping sx={{ color: COLOR }} />
                <Box flex={1} minWidth={200}>
                  <Typography fontWeight={800} fontSize={17}>{cargue.codigo} · {cargue.vehiculo ?? (cargue.transportadora ? `${cargue.transportadora}${cargue.placa_tercero ? ` · ${cargue.placa_tercero}` : ''}` : 'sin vehículo')}</Typography>
                  <Chip size="small" label={MODOS[cargue.modo_despacho]?.nombre} sx={{ height: 20, fontSize: 11, fontWeight: 700, bgcolor: alpha(MODOS[cargue.modo_despacho]?.color ?? '#64748B', 0.12), color: MODOS[cargue.modo_despacho]?.color }} />
                </Box>
                {!cargue.tercerizado && <TextField select size="small" label="Vehículo" value={cargue.vehiculo_id ?? ''} sx={{ minWidth: 180 }}
                  onChange={async e => { try { await cx.editarCargue(cargue.id, { almacen_id: cargue.almacen_id, modo_despacho: cargue.modo_despacho, vehiculo_id: Number(e.target.value) }); refrescar() } catch (x) { toast.error(errorApi(x)) } }}>
                  {(vehiculos.data ?? []).map(v => <MenuItem key={v.id} value={v.id}>{v.placa} · {v.tipo_vehiculo ?? v.tipo ?? ''}</MenuItem>)}
                </TextField>}
                <Button color="inherit" size="small" onClick={async () => { try { await cx.cancelarCargue(cargue.id); setActivo(null); toast.success('Cargue cancelado: la carga vuelve a pendiente'); refrescar() } catch (e) { toast.error(errorApi(e)) } }}>Cancelar cargue</Button>
              </Stack>
              <Box sx={{ p: 2 }}>
                {/* escáner */}
                <TextField inputRef={scan} fullWidth autoComplete="off" label="Escanee la etiqueta del consolidado (lector o radiofrecuencia)" value={codigo}
                  onChange={e => setCodigo(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && codigo.trim()) { asignar({ codigo: codigo.trim() }); setCodigo('') } }}
                  InputProps={{ startAdornment: <QrCodeScanner sx={{ mr: 1, color: 'text.secondary' }} />, sx: { fontFamily: 'Consolas, monospace', fontSize: 18 } }} />
                {ultimo && <Alert severity={ultimo.ok ? 'success' : 'error'} sx={{ mt: 1, py: 0 }} onClose={() => setUltimo(null)}>{ultimo.texto}</Alert>}

                {/* capacidad */}
                <Stack direction="row" gap={2} mt={2}>
                  {cap ? <>
                    <Barra etiqueta="Peso" pct={cap.uso_kg_pct} valor={`${kg(cargue.totales.peso_kg)} de ${kg(cap.capacidad_kg)}`} />
                    <Barra etiqueta="Volumen" pct={cap.uso_m3_pct} valor={`${m3(cargue.totales.volumen_m3)} de ${m3(cap.capacidad_m3)}`} />
                  </> : <Typography fontSize={13} color="text.secondary">{cargue.tercerizado ? 'Tercerizado: la capacidad la controla la transportadora.' : 'Elija el vehículo para ver la capacidad.'}
                    {' '}Carga: {kg(cargue.totales.peso_kg)} · {m3(cargue.totales.volumen_m3)}</Typography>}
                </Stack>
                {cap && cap.avisos.length > 0 && <Typography fontSize={11.5} color="text.secondary" mt={0.5}>{cap.avisos.join(' · ')}</Typography>}
                <Stack direction="row" gap={1} mt={1.5} flexWrap="wrap">
                  {[['Consolidados', cargue.totales.consolidados], ['Pedidos', cargue.totales.pedidos], ['Bultos', cargue.totales.bultos], ['Destinos', cargue.destinos.length]].map(([t, v]) =>
                    <Box key={t as string} sx={{ px: 1.5, py: 0.75, borderRadius: 2, bgcolor: '#F8FAFC', minWidth: 90 }}>
                      <Typography fontWeight={800} fontSize={18}>{v as number}</Typography><Typography fontSize={11} color="text.secondary">{t as string}</Typography></Box>)}
                </Stack>

                {/* lo cargado, por destino (= paradas) */}
                <Typography fontWeight={800} mt={2} mb={0.75}>En el vehículo</Typography>
                {!cargue.consolidados.length ? <Typography fontSize={13} color="text.secondary">Aún vacío: escanee etiquetas o use + en la lista.</Typography> :
                  cargue.destinos.map(d => (
                    <Box key={d.destino} sx={{ mb: 1, border: '1px solid #EEF2F7', borderRadius: 2 }}>
                      <Stack direction="row" alignItems="center" gap={1} sx={{ px: 1.5, py: 0.75, bgcolor: '#FAFAFB' }}>
                        <Place sx={{ fontSize: 16, color: COLOR }} /><Typography fontWeight={800} fontSize={13}>{d.destino}</Typography>
                        <Typography fontSize={11.5} color="text.secondary">{d.pedidos} pedido(s) · {d.bultos} bulto(s)</Typography></Stack>
                      {cargue.consolidados.filter(c => c.destino === d.destino).map(c => (
                        <Stack key={c.id} direction="row" alignItems="center" gap={1} sx={{ px: 1.5, py: 0.6, borderTop: '1px solid #F1F5F9' }}>
                          <CheckCircle sx={{ fontSize: 17, color: '#10B981' }} />
                          <Typography fontFamily="Consolas, monospace" fontWeight={700} fontSize={12.5}>{c.codigo}</Typography>
                          <Typography fontSize={12} color="text.secondary" flex={1} noWrap>{c.ordenes.map(o => o.pedido ?? o.numero).join(', ')}</Typography>
                          <Typography fontSize={12} color="text.secondary">{kg(c.peso_kg)}</Typography>
                          <IconButton size="small" onClick={async () => { try { await cx.quitar(cargue.id, c.id); refrescar() } catch (e) { toast.error(errorApi(e)) } }}><Close fontSize="small" /></IconButton>
                        </Stack>))}
                    </Box>))}
                <Button fullWidth size="large" variant="contained" startIcon={<CheckCircle />} disabled={!cargue.consolidados.length || (cap ? !cap.ok : false) || (!cargue.tercerizado && !cargue.vehiculo_id)}
                  onClick={() => setConfirmar(true)} sx={{ mt: 2, py: 1.25, bgcolor: '#10B981', '&:hover': { bgcolor: '#059669' } }}>Confirmar cargue y crear el viaje</Button>
              </Box>
            </Paper>}
          </Grid>
        </Grid>

        {/* nuevo cargue */}
        <Dialog open={!!nuevo} onClose={() => setNuevo(null)} maxWidth="sm" fullWidth>
          <DialogTitle fontWeight={800}>Nuevo cargue</DialogTitle>
          {nuevo && <DialogContent sx={{ pt: '8px !important' }}><Stack gap={2}>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
              {Object.entries(MODOS).map(([k, v]) => (
                <Paper key={k} variant="outlined" onClick={() => setNuevo({ ...nuevo, modo_despacho: k })} sx={{ p: 1.25, borderRadius: 2, cursor: 'pointer',
                  borderColor: nuevo.modo_despacho === k ? v.color : undefined, borderWidth: nuevo.modo_despacho === k ? 2 : 1, bgcolor: nuevo.modo_despacho === k ? alpha(v.color, 0.06) : undefined }}>
                  <Typography fontWeight={800} fontSize={13} sx={{ color: nuevo.modo_despacho === k ? v.color : undefined }}>{v.nombre}</Typography>
                  <Typography fontSize={11.5} color="text.secondary">{(pendiente.data ?? []).filter(c => c.modo_despacho === k).length} consolidados esperando</Typography>
                </Paper>))}
            </Box>
            {MODOS[nuevo.modo_despacho]?.tercerizado ? <Stack direction="row" gap={1.5}>
              <TextField select label="Transportadora" value={nuevo.transportadora_id ?? ''} onChange={e => setNuevo({ ...nuevo, transportadora_id: Number(e.target.value) })} sx={{ flex: 2 }}>
                {(trans.data ?? []).map(t => <MenuItem key={t.id} value={t.id}>{t.nombre}</MenuItem>)}
              </TextField>
              <TextField label="Placa que recoge" value={nuevo.placa_tercero ?? ''} onChange={e => setNuevo({ ...nuevo, placa_tercero: e.target.value.toUpperCase() })} sx={{ flex: 1 }} />
            </Stack> : <TextField select label="Vehículo" value={nuevo.vehiculo_id ?? ''} onChange={e => setNuevo({ ...nuevo, vehiculo_id: Number(e.target.value) })}
              helperText="Se verifica el peso y el volumen de lo que se cargue contra su capacidad">
              {(vehiculos.data ?? []).map(v => <MenuItem key={v.id} value={v.id}>{v.placa} · {v.tipo_vehiculo ?? v.tipo ?? ''}{v.capacidad_kg ? ` · ${v.capacidad_kg} kg` : ''}</MenuItem>)}
            </TextField>}
          </Stack></DialogContent>}
          <DialogActions><Button color="inherit" onClick={() => setNuevo(null)}>Cancelar</Button>
            <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!nuevo || (MODOS[nuevo.modo_despacho]?.tercerizado ? !nuevo.transportadora_id : !nuevo.vehiculo_id)} onClick={crear}>Abrir cargue</Button></DialogActions>
        </Dialog>

        {/* confirmar */}
        <Dialog open={confirmar} onClose={() => setConfirmar(false)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={800}>Confirmar {cargue?.codigo}</DialogTitle>
          <DialogContent><Typography fontSize={14}>
            Se despachan <b>{cargue?.totales.pedidos}</b> pedidos en <b>{cargue?.totales.consolidados}</b> consolidados ({cargue?.totales.bultos} bultos) y se crea el viaje
            con {cargue?.destinos.length} destino(s). La mercancía sale del staging del WMS y los pedidos de los canales reciben su guía.</Typography></DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setConfirmar(false)}>Volver</Button>
            <Button variant="contained" sx={{ bgcolor: '#10B981' }} onClick={async () => {
              setConfirmar(false)
              try { const r = await cx.confirmar(cargue!.id, {}); setListo(r); setActivo(null); refrescar() } catch (e) { toast.error(errorApi(e)) }
            }}>Confirmar y crear viaje</Button></DialogActions>
        </Dialog>
        <Dialog open={!!listo} onClose={() => setListo(null)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={800} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><CheckCircle sx={{ color: '#10B981' }} />Viaje {listo?.viaje} creado</DialogTitle>
          <DialogContent><Typography fontSize={14}>{listo?.despachos} despachos · {listo?.paradas} parada(s). Siga con el flujo normal: asigne el conductor y despache el viaje.</Typography></DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setListo(null)}>Seguir cargando</Button>
            <Button variant="contained" endIcon={<OpenInNew />} sx={{ bgcolor: COLOR }} onClick={() => navigate('/tms/viajes')}>Ir al viaje</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
