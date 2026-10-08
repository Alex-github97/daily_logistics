/**
 * WMS · Facturación del servicio logístico (3PL)
 *
 * Tarifas por depositante (o generales), liquidación de un periodo con el
 * almacenamiento día a día reconstruido del kárdex, y su factura de venta en
 * el ERP. No se puede liquidar dos veces el mismo día del mismo depositante.
 */
import { useEffect, useState } from 'react'
import {
  Box, Paper, Typography, MenuItem, Button, Chip, Stack, Alert, Tabs, Tab, LinearProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { RequestQuote } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, Cifra, errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const pesos = (v?: number | null) => v == null ? '—' : v.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })
const iso = (d: Date) => d.toLocaleDateString('en-CA')

function Liquidar() {
  const qc = useQueryClient()
  const deps = useQuery({ queryKey: ['wms-depositantes'], queryFn: wms.depositantes })
  const hoy = new Date()
  const [dep, setDep] = useState<number | ''>('')
  const [desde, setDesde] = useState(iso(new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1)))
  const [hasta, setHasta] = useState(iso(new Date(hoy.getFullYear(), hoy.getMonth(), 0)))
  const [previa, setPrevia] = useState<any>(null)
  const [cargando, setCargando] = useState(false)
  useEffect(() => setPrevia(null), [dep, desde, hasta])
  const calcular = async () => {
    setCargando(true)
    try { setPrevia(await api.post('/wms/3pl/liquidaciones/previa', { depositante_id: dep, desde, hasta }).then(r => r.data)) }
    catch (e) { toast.error(errorApi(e)) } finally { setCargando(false) }
  }
  const guardar = async () => {
    try { const l = await api.post('/wms/3pl/liquidaciones', { depositante_id: dep, desde, hasta }).then(r => r.data)
      toast.success(`Liquidación ${l.numero} guardada en borrador`); setPrevia(null); qc.invalidateQueries({ queryKey: ['3pl-liq'] }) }
    catch (e) { toast.error(errorApi(e)) }
  }
  return <>
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
      <Stack direction="row" gap={1.5} flexWrap="wrap" alignItems="center">
        <TextField select size="small" label="Depositante" value={dep} onChange={e => setDep(Number(e.target.value))} sx={{ minWidth: 260 }}>
          {(deps.data ?? []).filter(d => !d.propio).map(d => <MenuItem key={d.id} value={d.id}>{d.nombre}</MenuItem>)}
        </TextField>
        <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
        <Button variant="outlined" disabled={!dep || cargando} onClick={calcular}>Calcular</Button>
      </Stack>
      <Typography fontSize={12} color="text.secondary" mt={1}>Solo días cerrados (hasta ayer). El almacenamiento se toma de la existencia al cierre de cada día.</Typography>
    </Paper>
    {cargando && <LinearProgress />}
    {previa && <>
      {previa.avisos.map((a: string) => <Alert key={a} severity="warning" sx={{ mb: 1 }}>{a}</Alert>)}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="m³ promedio" valor={num(previa.promedios.m3)} color={COLOR} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Posiciones promedio" valor={num(previa.promedios.posiciones)} color="#0369A1" /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Estibas promedio" valor={num(previa.promedios.estibas)} color="#7C3AED" /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Total con IVA" valor={pesos(previa.total)} color="#15803D" sub={`Subtotal ${pesos(previa.subtotal)}`} /></Grid>
      </Grid>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2, height: 220 }}>
        <ResponsiveContainer>
          <BarChart data={previa.diario.map((x: any) => ({ ...x, dia: x.fecha.slice(5) }))}>
            <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="dia" fontSize={10} /><YAxis fontSize={10} />
            <RTooltip /><Bar dataKey="m3" name="m³" fill={COLOR} /><Bar dataKey="posiciones" name="Posiciones" fill="#0EA5E9" />
          </BarChart>
        </ResponsiveContainer>
      </Paper>
      <TablaRegistros filas={previa.lineas.map((l: any, i: number) => ({ ...l, id: i + 1 }))} vacio="Nada que cobrar" etiqueta={(l: any) => l.descripcion}
        columnas={[
          { titulo: 'Concepto', valor: (l: any) => <>{l.descripcion} {l.propia && <Chip size="small" label="tarifa propia" sx={{ height: 18, fontSize: 10 }} />}</> },
          { titulo: 'Cantidad', valor: (l: any) => `${num(l.cantidad)} ${l.unidad}`, alinear: 'right' },
          { titulo: 'Tarifa', valor: (l: any) => pesos(l.tarifa), alinear: 'right' },
          { titulo: 'Subtotal', valor: (l: any) => pesos(l.subtotal), alinear: 'right' },
          { titulo: 'IVA', valor: (l: any) => `${pesos(l.iva)} (${l.iva_pct}%)`, alinear: 'right' },
        ]} />
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
        <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!previa.lineas.length} onClick={guardar}>Guardar liquidación</Button>
      </Box>
    </>}
  </>
}

function Liquidaciones() {
  const qc = useQueryClient()
  const liq = useQuery({ queryKey: ['3pl-liq'], queryFn: () => api.get('/wms/3pl/liquidaciones').then(r => r.data) })
  const accion = async (ruta: string, ok: string) => {
    try { await api.post(ruta); toast.success(ok); qc.invalidateQueries({ queryKey: ['3pl-liq'] }) } catch (e) { toast.error(errorApi(e)) }
  }
  return <TablaRegistros filas={liq.data ?? []} cargando={liq.isLoading} vacio="Sin liquidaciones" etiqueta={(l: any) => l.numero}
    extra={(l: any) => l.estado === 'BORRADOR' ? <>
      <Button size="small" variant="contained" sx={{ bgcolor: COLOR }} onClick={() => accion(`/wms/3pl/liquidaciones/${l.id}/facturar`, 'Factura emitida en el ERP')}>Facturar</Button>
      <Button size="small" color="inherit" onClick={() => accion(`/wms/3pl/liquidaciones/${l.id}/anular`, 'Liquidación anulada')}>Anular</Button>
    </> : null}
    columnas={[
      { titulo: 'Liquidación', valor: (l: any) => <Typography fontFamily="monospace" fontWeight={700} fontSize={13}>{l.numero}</Typography> },
      { titulo: 'Depositante', valor: (l: any) => l.depositante },
      { titulo: 'Periodo', valor: (l: any) => `${l.desde} a ${l.hasta}` },
      { titulo: 'Total', valor: (l: any) => pesos(l.total), alinear: 'right' },
      { titulo: 'Estado', valor: (l: any) => <Chip size="small" label={l.estado.toLowerCase()} color={l.estado === 'FACTURADA' ? 'success' : l.estado === 'ANULADA' ? 'default' : 'warning'} /> },
      { titulo: 'Factura', valor: (l: any) => l.factura ?? '' },
    ]} />
}

function Tarifas() {
  const qc = useQueryClient()
  const deps = useQuery({ queryKey: ['wms-depositantes'], queryFn: wms.depositantes })
  const [dep, setDep] = useState<number | ''>('')
  const tarifas = useQuery({ queryKey: ['3pl-tarifas', dep], queryFn: () => api.get('/wms/3pl/tarifas', { params: { depositante_id: dep || undefined } }).then(r => r.data) })
  const [edicion, setEdicion] = useState<Record<string, { valor: string; iva_pct: string }>>({})
  useEffect(() => setEdicion({}), [dep])
  const valor = (t: any, k: 'valor' | 'iva_pct') => edicion[t.concepto]?.[k] ?? (t[k] == null ? '' : String(t[k]))
  const poner = (t: any, k: 'valor' | 'iva_pct', v: string) =>
    setEdicion(e => ({ ...e, [t.concepto]: { ...(e[t.concepto] ?? { valor: valor(t, 'valor'), iva_pct: valor(t, 'iva_pct') }), [k]: v } }))
  const guardar = async () => {
    try {
      await api.put('/wms/3pl/tarifas', Object.entries(edicion).map(([concepto, x]) => ({ concepto, valor: x.valor === '' ? null : Number(x.valor), iva_pct: Number(x.iva_pct || 19) })),
        { params: { depositante_id: dep || undefined } })
      toast.success('Tarifas guardadas'); setEdicion({}); qc.invalidateQueries({ queryKey: ['3pl-tarifas'] })
    } catch (e) { toast.error(errorApi(e)) }
  }
  return <>
    <Stack direction="row" gap={1.5} mb={2} alignItems="center">
      <TextField select size="small" label="Tarifas de" value={dep} onChange={e => setDep(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 280 }}>
        <MenuItem value="">Generales (aplican si el depositante no tiene propias)</MenuItem>
        {(deps.data ?? []).filter(d => !d.propio).map(d => <MenuItem key={d.id} value={d.id}>{d.nombre}</MenuItem>)}
      </TextField>
      <Box flex={1} />
      <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!Object.keys(edicion).length} onClick={guardar}>Guardar</Button>
    </Stack>
    <TablaRegistros filas={(tarifas.data ?? []).map((t: any, i: number) => ({ ...t, id: i + 1 }))} cargando={tarifas.isLoading} vacio="" etiqueta={(t: any) => t.nombre}
      columnas={[
        { titulo: 'Concepto', valor: (t: any) => t.nombre }, { titulo: 'Unidad', valor: (t: any) => t.unidad },
        { titulo: dep ? 'Tarifa propia' : 'Tarifa general', valor: (t: any) => <TextField size="small" type="number" value={valor(t, 'valor')} sx={{ width: 140 }}
          inputProps={{ 'aria-label': `Tarifa ${t.nombre}` }} onChange={e => poner(t, 'valor', e.target.value)} placeholder="sin tarifa" /> },
        { titulo: 'IVA %', valor: (t: any) => <TextField size="small" type="number" value={valor(t, 'iva_pct')} sx={{ width: 80 }} onChange={e => poner(t, 'iva_pct', e.target.value)} /> },
        ...(dep ? [{ titulo: 'Se aplica', valor: (t: any) => t.aplica == null ? '—' : <>{pesos(t.aplica)} <Chip size="small" label={t.origen} sx={{ height: 18, fontSize: 10 }} /></> }] : []),
      ]} />
  </>
}

export default function WMSFacturacion3PL() {
  const [tab, setTab] = useState(0)
  return (
    <Layout title="WMS — Facturación 3PL">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<RequestQuote sx={{ fontSize: 28 }} />} titulo="Facturación del servicio logístico" color={COLOR}
          subtitulo="Almacenamiento día a día, movimientos y maquila de cada depositante, facturados en el ERP" />
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Liquidar" /><Tab label="Liquidaciones" /><Tab label="Tarifas" /></Tabs>
        {tab === 0 && <Liquidar />}
        {tab === 1 && <Liquidaciones />}
        {tab === 2 && <Tarifas />}
      </Box>
    </Layout>
  )
}
