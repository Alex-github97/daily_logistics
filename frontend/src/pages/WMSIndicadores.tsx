/**
 * WMS · Indicadores
 *
 * El tablero de los indicadores del WMS por categoría, cada uno contra su meta
 * y contra el periodo anterior. Cada tarjeta abre su ficha: qué mide, la
 * fórmula, de dónde sale cada dato, cómo se calcula paso a paso, qué quedó por
 * fuera (calidad de datos), cómo ha evolucionado y los registros detrás del
 * número. La meta se ajusta por almacén.
 */
import { useMemo, useState } from 'react'
import {
  Box, Paper, Typography, MenuItem, Chip, Stack, Dialog, DialogTitle, DialogContent, DialogActions, Button, Tabs, Tab, Alert, Tooltip, LinearProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Insights, TrendingUp, TrendingDown, TrendingFlat, WarningAmber, FileDownload } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip as RTooltip, ReferenceLine, ResponsiveContainer, CartesianGrid } from 'recharts'
import * as XLSX from 'xlsx'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const SEM: Record<string, string> = { verde: '#15803D', amarillo: '#D97706', rojo: '#DC2626' }
const CATEGORIAS = ['Recepción', 'Almacenamiento', 'Inventario', 'Espacio', 'Alistamiento', 'Despacho', 'Servicio al cliente', 'Productividad']

interface Ind {
  clave: string; nombre: string; categoria: string; unidad: string; sentido: 'mayor' | 'menor'; especializado: boolean
  instantaneo: boolean; valor: number | null; numerador?: number | null; denominador?: number | null; muestras: number
  avisos: string[]; meta: number; semaforo: string | null; anterior?: number | null
}

const hoy = () => new Date().toLocaleDateString('en-CA')
const fmt = (v: number | null | undefined, u: string) => v == null ? '—' : `${num(Math.round(v * 100) / 100)}${u === '%' ? '%' : ` ${u}`}`

function rango(p: string): [string, string] {
  const d = new Date(); const iso = (x: Date) => x.toLocaleDateString('en-CA')
  if (p === 'mes') return [iso(new Date(d.getFullYear(), d.getMonth(), 1)), iso(d)]
  if (p === 'mes_anterior') return [iso(new Date(d.getFullYear(), d.getMonth() - 1, 1)), iso(new Date(d.getFullYear(), d.getMonth(), 0))]
  if (p === 'trimestre') return [iso(new Date(d.getTime() - 89 * 864e5)), iso(d)]
  if (p === 'anio') return [iso(new Date(d.getFullYear(), 0, 1)), iso(d)]
  return [iso(new Date(d.getTime() - 29 * 864e5)), iso(d)]
}

function Tendencia({ i }: { i: Ind }) {
  if (i.valor == null || i.anterior == null || i.instantaneo) return null
  const dif = i.valor - i.anterior
  if (Math.abs(dif) < 1e-9) return <TrendingFlat fontSize="small" sx={{ color: 'text.secondary' }} />
  const mejora = i.sentido === 'mayor' ? dif > 0 : dif < 0
  const Icono = dif > 0 ? TrendingUp : TrendingDown
  return <Tooltip title={`Periodo anterior: ${fmt(i.anterior, i.unidad)}`}><Icono fontSize="small" sx={{ color: mejora ? '#15803D' : '#DC2626' }} /></Tooltip>
}

function Ficha({ clave, params, onCerrar }: { clave: string; params: Record<string, unknown>; onCerrar: () => void }) {
  const qc = useQueryClient()
  const f = useQuery({ queryKey: ['wms-ind-ficha', clave, params], queryFn: () => api.get(`/wms/indicadores/${clave}`, { params }).then(r => r.data) })
  const [tab, setTab] = useState(0)
  const [meta, setMeta] = useState('')
  const d = f.data
  const columnas = useMemo(() => d?.detalle?.length ? Object.keys(d.detalle[0]) : [], [d])
  const guardarMeta = async (general: boolean) => {
    try {
      await api.put(`/wms/indicadores/${clave}/meta`, { meta: Number(meta), almacen_id: general ? null : params.almacen_id ?? null })
      toast.success('Meta guardada'); setMeta(''); qc.invalidateQueries({ queryKey: ['wms-ind'] }); qc.invalidateQueries({ queryKey: ['wms-ind-ficha'] })
    } catch (e) { toast.error(errorApi(e)) }
  }
  const fi = d?.ficha
  return (
    <Dialog open onClose={onCerrar} maxWidth="md" fullWidth>
      {!d ? <LinearProgress /> : <>
        <DialogTitle sx={{ fontWeight: 800 }}>
          {fi.nombre}
          <Typography fontSize={13} color="text.secondary">{fi.categoria}{fi.especializado ? ' · especializado' : ''}{fi.instantaneo ? ' · se mide sobre el estado actual' : ''}</Typography>
        </DialogTitle>
        <DialogContent>
          <Stack direction="row" gap={3} alignItems="baseline" mb={2} flexWrap="wrap">
            <Typography fontSize={34} fontWeight={800} sx={{ color: d.semaforo ? SEM[d.semaforo] : 'text.secondary' }}>{fmt(d.valor, fi.unidad)}</Typography>
            <Typography color="text.secondary">Meta: {fi.sentido === 'mayor' ? '≥' : '≤'} {fmt(fi.meta, fi.unidad)}</Typography>
            {d.denominador != null && <Typography color="text.secondary" fontSize={13}>{num(d.numerador)} / {num(d.denominador)}{d.muestras ? ` · ${d.muestras} registros` : ''}</Typography>}
          </Stack>
          {d.avisos?.map((a: string) => <Alert key={a} severity="warning" sx={{ mb: 1 }}>{a}</Alert>)}
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
            <Tab label="Cómo se mide" /><Tab label="Evolución" disabled={fi.instantaneo} /><Tab label={`Detalle (${d.detalle_total})`} /><Tab label="Meta" />
          </Tabs>
          {tab === 0 && <Stack gap={1.5}>
            <Typography>{fi.definicion}</Typography>
            <Paper variant="outlined" sx={{ p: 1.5, fontFamily: 'monospace', fontSize: 13, bgcolor: '#F8FAFC' }}>{fi.formula}</Paper>
            <Typography fontSize={13}><b>Datos:</b> {fi.fuente}</Typography>
            <Box component="ol" sx={{ m: 0, pl: 2.5, fontSize: 13 }}>{fi.como.map((p: string) => <li key={p}>{p}</li>)}</Box>
            <Typography fontSize={13}><b>Sentido:</b> {fi.sentido === 'mayor' ? 'entre más alto, mejor' : 'entre más bajo, mejor'}. <b>Meta sugerida:</b> {fmt(fi.meta_sugerida, fi.unidad)}.</Typography>
            {fi.referencia && <Typography fontSize={13} color="text.secondary">{fi.referencia}</Typography>}
            <Typography fontSize={12} color="text.secondary">Semáforo: verde cumple la meta; amarillo está a menos del 10 % de cumplirla; rojo, más lejos.</Typography>
          </Stack>}
          {tab === 1 && (d.serie?.length ? <Box sx={{ height: 280 }}><ResponsiveContainer>
            <LineChart data={d.serie.map((x: any) => ({ ...x, corte: x.desde.slice(5) }))}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="corte" fontSize={11} /><YAxis fontSize={11} />
              <RTooltip formatter={(v: any) => fmt(v, fi.unidad)} labelFormatter={(l: any) => `Desde ${l}`} />
              <ReferenceLine y={fi.meta} stroke="#D97706" strokeDasharray="4 4" label={{ value: 'meta', fontSize: 11 }} />
              <Line type="monotone" dataKey="valor" stroke={COLOR} strokeWidth={2} connectNulls dot />
            </LineChart></ResponsiveContainer></Box> : <Alert severity="info">Sin datos por cortes en el periodo.</Alert>)}
          {tab === 2 && <>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
              <Button size="small" startIcon={<FileDownload />} disabled={!d.detalle.length} onClick={() => {
                const libro = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(d.detalle), 'Detalle')
                XLSX.writeFile(libro, `${clave}-${d.desde}-${d.hasta}.xlsx`)
              }}>Exportar</Button>
            </Box>
            <TablaRegistros filas={d.detalle.map((x: any, i: number) => ({ ...x, id: i + 1 }))} vacio="Nada que mostrar: todos los registros cumplen o no hay datos" etiqueta={() => 'registro'}
              columnas={columnas.map(c => ({ titulo: c.replace(/_/g, ' '), valor: (x: any) => typeof x[c] === 'boolean' ? (x[c] ? 'sí' : 'no') : String(x[c] ?? '') }))} />
            {d.detalle_total > d.detalle.length && <Typography fontSize={12} color="text.secondary" mt={1}>Se muestran {d.detalle.length} de {d.detalle_total}.</Typography>}
          </>}
          {tab === 3 && <Stack gap={1.5}>
            <Typography fontSize={13}>Meta vigente: <b>{fmt(fi.meta, fi.unidad)}</b> (sugerida {fmt(fi.meta_sugerida, fi.unidad)}). Solo supervisores pueden cambiarla.</Typography>
            <Stack direction="row" gap={1}>
              <TextField size="small" type="number" label={`Nueva meta (${fi.unidad})`} value={meta} onChange={e => setMeta(e.target.value)} />
              {!!params.almacen_id && <Button disabled={meta === ''} onClick={() => guardarMeta(false)}>Para este almacén</Button>}
              <Button disabled={meta === ''} onClick={() => guardarMeta(true)}>Para todos los almacenes</Button>
            </Stack>
          </Stack>}
        </DialogContent>
        <DialogActions><Button onClick={onCerrar}>Cerrar</Button></DialogActions>
      </>}
    </Dialog>
  )
}

export default function WMSIndicadores() {
  const [periodo, setPeriodo] = useState('30')
  const [[desde, hasta], setRango] = useState<[string, string]>(rango('30'))
  const [almacen, setAlmacen] = useState<number | ''>('')
  const [depositante, setDepositante] = useState<number | ''>('')
  const [vista, setVista] = useState(0)
  const [ficha, setFicha] = useState<string | null>(null)
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const depositantes = useQuery({ queryKey: ['wms-depositantes'], queryFn: wms.depositantes })
  const params = { desde, hasta, almacen_id: almacen || undefined, depositante_id: depositante || undefined }
  const t = useQuery({ queryKey: ['wms-ind', params], queryFn: () => api.get('/wms/indicadores', { params }).then(r => r.data) })
  const ops = useQuery({ queryKey: ['wms-ind-ops', params], enabled: vista === 1, queryFn: () => api.get('/wms/indicadores/operarios', { params }).then(r => r.data) })
  const inds: Ind[] = t.data?.indicadores ?? []
  const resumen = useMemo(() => ({ verde: inds.filter(i => i.semaforo === 'verde').length, amarillo: inds.filter(i => i.semaforo === 'amarillo').length,
    rojo: inds.filter(i => i.semaforo === 'rojo').length, sin: inds.filter(i => i.valor == null).length }), [inds])
  const exportarFichas = async () => {
    const cat = await api.get('/wms/indicadores/catalogo', { params: { almacen_id: almacen || undefined } }).then(r => r.data)
    const libro = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(cat.map((f: any) => ({
      Indicador: f.nombre, Categoría: f.categoria, Unidad: f.unidad, Sentido: f.sentido === 'mayor' ? 'Más es mejor' : 'Menos es mejor',
      Meta: f.meta, Definición: f.definicion, Fórmula: f.formula, Datos: f.fuente, 'Cómo se mide': f.como.join(' → '), Referencia: f.referencia }))), 'Fichas')
    XLSX.writeFile(libro, 'fichas-indicadores-wms.xlsx')
  }
  return (
    <Layout title="WMS — Indicadores">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Insights sx={{ fontSize: 28 }} />} titulo="Indicadores de la bodega" color={COLOR}
          subtitulo="Estándar y especializados, cada uno con su ficha: qué mide, cómo se calcula y qué datos usa" />
        <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
          <Grid container spacing={1.5} alignItems="center">
            <Grid size={{ xs: 12, md: 2.5 }}>
              <TextField select fullWidth size="small" label="Periodo" value={periodo} onChange={e => { setPeriodo(e.target.value); if (e.target.value !== 'otro') setRango(rango(e.target.value)) }}>
                <MenuItem value="30">Últimos 30 días</MenuItem><MenuItem value="mes">Este mes</MenuItem><MenuItem value="mes_anterior">Mes anterior</MenuItem>
                <MenuItem value="trimestre">Últimos 90 días</MenuItem><MenuItem value="anio">Este año</MenuItem><MenuItem value="otro">Otro…</MenuItem>
              </TextField>
            </Grid>
            {periodo === 'otro' && <>
              <Grid size={{ xs: 6, md: 1.75 }}><TextField fullWidth size="small" type="date" label="Desde" value={desde} onChange={e => setRango([e.target.value, hasta])} InputLabelProps={{ shrink: true }} /></Grid>
              <Grid size={{ xs: 6, md: 1.75 }}><TextField fullWidth size="small" type="date" label="Hasta" value={hasta} onChange={e => setRango([desde, e.target.value || hoy()])} InputLabelProps={{ shrink: true }} /></Grid>
            </>}
            <Grid size={{ xs: 12, md: 2.5 }}>
              <TextField select fullWidth size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(e.target.value === '' ? '' : Number(e.target.value))}>
                <MenuItem value="">Todos</MenuItem>{(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, md: 2.5 }}>
              <TextField select fullWidth size="small" label="Depositante" value={depositante} onChange={e => setDepositante(e.target.value === '' ? '' : Number(e.target.value))}>
                <MenuItem value="">Todos</MenuItem>{(depositantes.data ?? []).map(d => <MenuItem key={d.id} value={d.id}>{d.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, md: 'grow' }} sx={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button size="small" startIcon={<FileDownload />} onClick={exportarFichas}>Fichas de los indicadores</Button>
            </Grid>
          </Grid>
          {t.data && <Stack direction="row" gap={1} mt={1.5} flexWrap="wrap">
            <Chip size="small" sx={{ bgcolor: SEM.verde, color: '#fff' }} label={`${resumen.verde} en meta`} />
            <Chip size="small" sx={{ bgcolor: SEM.amarillo, color: '#fff' }} label={`${resumen.amarillo} cerca`} />
            <Chip size="small" sx={{ bgcolor: SEM.rojo, color: '#fff' }} label={`${resumen.rojo} lejos de la meta`} />
            <Chip size="small" label={`${resumen.sin} sin datos`} />
            <Typography fontSize={12} color="text.secondary">{t.data.desde} a {t.data.hasta}; la flecha compara con el periodo anterior de igual duración.</Typography>
          </Stack>}
        </Paper>
        <Tabs value={vista} onChange={(_, v) => setVista(v)} sx={{ mb: 2 }}><Tab label="Indicadores" /><Tab label="Productividad por persona" /></Tabs>
        {t.isLoading && <LinearProgress />}
        {vista === 0 && CATEGORIAS.map(cat => {
          const lista = inds.filter(i => i.categoria === cat)
          if (!lista.length) return null
          return (
            <Box key={cat} mb={3}>
              <Typography fontWeight={800} mb={1}>{cat}</Typography>
              <Grid container spacing={1.5}>
                {lista.map(i => (
                  <Grid key={i.clave} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                    <Paper variant="outlined" role="button" aria-label={`Ficha ${i.nombre}`} onClick={() => setFicha(i.clave)}
                      sx={{ p: 1.75, borderRadius: 3, cursor: 'pointer', height: '100%', borderTop: `4px solid ${i.semaforo ? SEM[i.semaforo] : '#CBD5E1'}`, '&:hover': { boxShadow: 2 } }}>
                      <Stack direction="row" alignItems="flex-start" gap={0.5}>
                        <Typography fontSize={13} fontWeight={700} flex={1} lineHeight={1.25}>{i.nombre}</Typography>
                        {i.avisos.length > 0 && <Tooltip title={i.avisos.join(' ')}><WarningAmber fontSize="small" sx={{ color: '#D97706' }} /></Tooltip>}
                      </Stack>
                      <Stack direction="row" alignItems="center" gap={1} mt={1}>
                        <Typography fontSize={26} fontWeight={800} sx={{ color: i.semaforo ? SEM[i.semaforo] : 'text.secondary' }}>{fmt(i.valor, i.unidad)}</Typography>
                        <Tendencia i={i} />
                      </Stack>
                      <Typography fontSize={11.5} color="text.secondary">
                        Meta {i.sentido === 'mayor' ? '≥' : '≤'} {fmt(i.meta, i.unidad)}{i.muestras ? ` · ${i.muestras} registros` : ''}
                      </Typography>
                      <Stack direction="row" gap={0.5} mt={0.75}>
                        {i.especializado && <Chip size="small" label="Especializado" sx={{ height: 18, fontSize: 10 }} />}
                        {i.instantaneo && <Chip size="small" label="Estado actual" sx={{ height: 18, fontSize: 10 }} />}
                      </Stack>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </Box>
          )
        })}
        {vista === 1 && <TablaRegistros filas={(ops.data ?? []).map((o: any) => ({ ...o, id: o.usuario_id }))} cargando={ops.isLoading} vacio="Sin tareas terminadas en el periodo" etiqueta={(o: any) => o.nombre}
          columnas={[
            { titulo: 'Persona', valor: (o: any) => o.nombre },
            { titulo: 'Estibas ubicadas', valor: (o: any) => o.tareas, alinear: 'right' },
            { titulo: 'Tareas/h', valor: (o: any) => o.tareas_por_hora ?? '—', alinear: 'right' },
            { titulo: 'Fuera de la sugerida', valor: (o: any) => o.desvio_pct == null ? '—' : `${o.desvio_pct}%`, alinear: 'right' },
            { titulo: 'Tareas de alistamiento', valor: (o: any) => o.tareas_alistamiento, alinear: 'right' },
            { titulo: 'Líneas alistadas', valor: (o: any) => o.lineas, alinear: 'right' },
            { titulo: 'Líneas/h', valor: (o: any) => o.lineas_por_hora ?? '—', alinear: 'right' },
          ]} />}
        {ficha && <Ficha clave={ficha} params={params} onCerrar={() => setFicha(null)} />}
      </Box>
    </Layout>
  )
}
