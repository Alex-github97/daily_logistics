/**
 * WMS · Trazabilidad
 *
 * - Kárdex: cada movimiento con su efecto y el saldo acumulado, para un
 *   producto, lote, ubicación, estiba, depositante o almacén. Al final compara
 *   el saldo contra la existencia actual: si no cuadran, hubo un movimiento sin
 *   rastro.
 * - Recorrido de lote: de qué proveedor llegó, a quién se entregó (con
 *   contacto), y dónde queda. Desde ahí se retiene el lote si hay que retirarlo.
 * - Bitácora: los eventos (quién hizo qué) por producto, lote o ubicación.
 */
import { useMemo, useState } from 'react'
import {
  Box, Paper, Typography, Tabs, Tab, MenuItem, Autocomplete, FormControlLabel, Checkbox, Button, Chip, Alert, Dialog, DialogTitle, DialogContent, DialogActions, LinearProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Timeline, FileDownload, Block } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import * as XLSX from 'xlsx'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, Cifra, errorApi } from '@/components/comun/Registro'
import { wms, TIPO_MOV, fechaHora, num, type Movimiento } from '@/api/wmsTrazable'
import BitacoraEventos from '@/components/wms/BitacoraEventos'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
type Alcance = 'producto_id' | 'lote_id' | 'ubicacion_id' | 'contenedor_id' | 'depositante_id' | 'almacen_id'
const ALCANCES: [Alcance, string][] = [['producto_id', 'Producto'], ['lote_id', 'Lote'], ['ubicacion_id', 'Ubicación'],
  ['contenedor_id', 'Estiba (LPN)'], ['depositante_id', 'Depositante'], ['almacen_id', 'Almacén']]
interface Opcion { id: number; etiqueta: string }

function useOpciones(alcance: Alcance) {
  return useQuery<Opcion[]>({
    queryKey: ['wms-opciones', alcance], staleTime: 60_000,
    queryFn: async () => {
      if (alcance === 'producto_id') return (await wms.productos()).map(p => ({ id: p.id, etiqueta: `${p.sku} · ${p.nombre}` }))
      if (alcance === 'lote_id') {
        const [lotes, prods] = await Promise.all([wms.lotes(), wms.productos()])
        const n = Object.fromEntries(prods.map(p => [p.id, p.nombre]))
        return lotes.map(l => ({ id: l.id, etiqueta: `${l.numero_lote} · ${n[l.producto_id] ?? ''}` }))
      }
      if (alcance === 'ubicacion_id') return (await wms.ubicaciones()).map(u => ({ id: u.id, etiqueta: u.codigo }))
      if (alcance === 'contenedor_id') return (await wms.contenedores({ estado: 'ABIERTO,CERRADO,VACIO,DESPACHADO', limite: 1000 })).map(c => ({ id: c.id, etiqueta: `${c.codigo} · ${c.ubicacion ?? 'sin ubicar'}` }))
      if (alcance === 'depositante_id') return (await wms.depositantes()).map(d => ({ id: d.id, etiqueta: d.nombre }))
      return (await wms.almacenes()).map(a => ({ id: a.id, etiqueta: a.nombre }))
    },
  })
}

function exportar(nombre: string, filas: Record<string, unknown>[]) {
  const libro = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(filas), 'Hoja1')
  XLSX.writeFile(libro, `${nombre}.xlsx`)
}

const ruta = (m: Movimiento) => {
  const o = m.origen ? `${m.origen}${m.contenedor && m.origen ? ` [${m.contenedor}]` : ''}` : '—'
  const d = m.destino ? `${m.destino}${m.contenedor_destino ? ` [${m.contenedor_destino}]` : ''}` : '—'
  return `${o} → ${d}`
}

function KardexTab() {
  const [alcance, setAlcance] = useState<Alcance>('producto_id')
  const [valor, setValor] = useState<Opcion | null>(null)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [estados, setEstados] = useState(false)
  const opciones = useOpciones(alcance)
  const k = useQuery({
    queryKey: ['wms-kardex', alcance, valor?.id, desde, hasta, estados], enabled: !!valor,
    queryFn: () => wms.kardex({ [alcance]: valor!.id, desde: desde || undefined, hasta: hasta || undefined, incluir_estados: estados }),
  })
  const d = k.data
  const filas = useMemo(() => (d?.movimientos ?? []).slice().reverse(), [d])
  return (
    <>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
        <Grid container spacing={1.5} alignItems="center">
          <Grid size={{ xs: 12, md: 2 }}>
            <TextField select fullWidth size="small" label="Kárdex de" value={alcance} onChange={e => { setAlcance(e.target.value as Alcance); setValor(null) }}>
              {ALCANCES.map(([v, t]) => <MenuItem key={v} value={v}>{t}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <Autocomplete size="small" options={opciones.data ?? []} value={valor} onChange={(_, v) => setValor(v)}
              getOptionLabel={o => o.etiqueta} isOptionEqualToValue={(a, b) => a.id === b.id} loading={opciones.isLoading}
              renderInput={p => <TextField {...p} label="Buscar" />} />
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}><TextField fullWidth size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} /></Grid>
          <Grid size={{ xs: 6, md: 2 }}><TextField fullWidth size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} /></Grid>
          <Grid size={{ xs: 12, md: 2 }}>
            <FormControlLabel control={<Checkbox size="small" checked={estados} onChange={e => setEstados(e.target.checked)} />}
              label={<Typography fontSize={12}>Ver reservas y bloqueos</Typography>} />
          </Grid>
        </Grid>
      </Paper>
      {!valor && <Alert severity="info">Elija qué quiere rastrear. El saldo es físico: disponible + reservado + bloqueado.</Alert>}
      {k.isFetching && <LinearProgress />}
      {d && <>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Saldo inicial" valor={num(d.saldo_inicial)} color="#64748B" /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Saldo final del kárdex" valor={num(d.saldo_final)} color={COLOR} sub={`${d.total_movimientos} movimientos`} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Existencia actual" valor={num(d.existencia_actual)} color="#0369A1" /></Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Cifra etiqueta="Conciliación" color={d.diferencia == null ? '#64748B' : Math.abs(d.diferencia) < 1e-6 ? '#15803D' : '#DC2626'}
              valor={d.diferencia == null ? 'No aplica' : Math.abs(d.diferencia) < 1e-6 ? 'Cuadra' : `Descuadre ${num(d.diferencia)}`}
              sub={d.diferencia == null ? 'Solo sin fecha inicial y hasta hoy' : Math.abs(d.diferencia) < 1e-6 ? 'Todo movimiento tiene rastro' : 'Existencias que cambiaron sin movimiento'} />
          </Grid>
        </Grid>
        {!d.completo && <Alert severity="warning" sx={{ mb: 1 }}>Se muestran los primeros movimientos del periodo; acote las fechas para ver el resto.</Alert>}
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
          <Button size="small" startIcon={<FileDownload />} onClick={() => exportar(`kardex-${valor?.etiqueta ?? ''}`, d.movimientos.map(m => ({
            Fecha: fechaHora(m.fecha), Tipo: TIPO_MOV[m.tipo] ?? m.tipo, SKU: m.sku, Producto: m.producto, Lote: m.lote ?? '',
            Cantidad: m.cantidad, Efecto: m.efecto, Saldo: m.saldo, Origen: m.origen ?? '', Destino: m.destino ?? '',
            'Estiba origen': m.contenedor ?? '', 'Estiba destino': m.contenedor_destino ?? '',
            Documento: `${m.documento_tipo ?? ''} ${m.referencia ?? ''}`.trim(), Usuario: m.usuario ?? '', Notas: m.notas ?? '' })))}>
            Exportar a Excel</Button>
        </Box>
        <TablaRegistros filas={filas} vacio="Sin movimientos en el periodo" etiqueta={m => `movimiento ${m.id}`}
          columnas={[
            { titulo: 'Fecha', valor: m => fechaHora(m.fecha) },
            { titulo: 'Tipo', valor: m => <Chip size="small" label={TIPO_MOV[m.tipo] ?? m.tipo} sx={{ fontSize: 11, height: 20 }} /> },
            { titulo: 'Producto', valor: m => <Box><b>{m.sku}</b> {m.lote && <Typography component="span" fontSize={11} color="text.secondary">· {m.lote}</Typography>}</Box> },
            { titulo: 'Ruta', valor: m => <Typography fontSize={12} fontFamily="monospace">{ruta(m)}</Typography> },
            { titulo: 'Estado', valor: m => m.estado_origen && m.estado_destino && m.estado_origen !== m.estado_destino ? `${m.estado_origen.toLowerCase()} → ${m.estado_destino.toLowerCase()}` : '' },
            { titulo: 'Efecto', alinear: 'right', valor: m => <Box sx={{ color: (m.efecto ?? 0) > 0 ? '#15803D' : (m.efecto ?? 0) < 0 ? '#DC2626' : 'text.secondary', fontWeight: 700 }}>{(m.efecto ?? 0) > 0 ? '+' : ''}{num(m.efecto ?? 0)}</Box> },
            { titulo: 'Saldo', alinear: 'right', valor: m => <b>{num(m.saldo)}</b> },
            { titulo: 'Documento', valor: m => <Typography fontSize={12}>{m.referencia ?? (m.documento_tipo ? `${m.documento_tipo} ${m.documento_id ?? ''}` : '')}{m.tarea_id ? ` · tarea ${m.tarea_id}` : ''}</Typography> },
            { titulo: 'Quién', valor: m => m.usuario ?? '' },
            { titulo: 'Notas', valor: m => <Typography fontSize={11.5} color="text.secondary">{m.notas ?? ''}</Typography> },
          ]} />
      </>}
    </>
  )
}

function RecorridoTab() {
  const qc = useQueryClient()
  const lotes = useOpciones('lote_id')
  const [lote, setLote] = useState<Opcion | null>(null)
  const r = useQuery({ queryKey: ['wms-recorrido', lote?.id], enabled: !!lote, queryFn: () => wms.recorrido(lote!.id) })
  const [retener, setRetener] = useState(false)
  const [motivo, setMotivo] = useState('')
  const d = r.data
  const confirmarRetencion = async () => {
    try {
      const x = await wms.retenerLote(lote!.id, motivo)
      toast.success(`Lote retenido: ${num(x.bloqueado)} und bloqueadas${x.reservado_en_ordenes ? `; ${num(x.reservado_en_ordenes)} siguen reservadas en órdenes` : ''}`)
      setRetener(false); setMotivo(''); qc.invalidateQueries({ queryKey: ['wms-recorrido'] })
    } catch (e) { toast.error(errorApi(e)) }
  }
  return (
    <>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
        <Autocomplete size="small" options={lotes.data ?? []} value={lote} onChange={(_, v) => setLote(v)} loading={lotes.isLoading}
          getOptionLabel={o => o.etiqueta} isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={p => <TextField {...p} label="Lote a rastrear" placeholder="Número de lote o producto" />} />
      </Paper>
      {r.isFetching && <LinearProgress />}
      {d && <>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 2 }}>
          <Typography fontWeight={800} fontSize={18}>Lote {d.lote.numero}</Typography>
          <Typography color="text.secondary">{d.producto?.sku} · {d.producto?.nombre}{d.depositante ? ` · de ${d.depositante}` : ''}</Typography>
          {d.lote.vence && <Chip size="small" label={`Vence ${d.lote.vence}`} />}
          <Chip size="small" color={d.lote.activo ? 'success' : 'error'} label={d.lote.activo ? 'Activo' : 'Retenido / inactivo'} />
          <Box sx={{ flex: 1 }} />
          <Button size="small" startIcon={<FileDownload />} onClick={() => exportar(`recorrido-${d.lote.numero}`, d.destino.map(x => ({
            Fecha: fechaHora(x.fecha), 'Entregado a': x.a_quien, Contacto: x.contacto ?? '', Documento: x.documento ?? '', Cantidad: x.cantidad })))}>
            Exportar entregas</Button>
          {d.lote.activo && <Button size="small" color="error" variant="outlined" startIcon={<Block />} onClick={() => setRetener(true)}>Retener lote</Button>}
        </Box>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 4 }}><Cifra etiqueta="Recibido" valor={num(d.recibido)} color="#15803D" /></Grid>
          <Grid size={{ xs: 4 }}><Cifra etiqueta="Salió de la bodega" valor={num(d.salido)} color="#DC2626" sub={`${d.clientes.length} destinatario(s)`} /></Grid>
          <Grid size={{ xs: 4 }}><Cifra etiqueta="Queda en bodega" valor={num(d.en_bodega)} color={COLOR} /></Grid>
        </Grid>
        <Typography fontWeight={700} mb={1}>De dónde vino</Typography>
        <TablaRegistros filas={d.origen.map((o, i) => ({ ...o, id: i + 1 }))} vacio="Sin recepciones registradas para este lote" etiqueta={o => o.recepcion}
          columnas={[
            { titulo: 'Fecha', valor: o => o.fecha }, { titulo: 'Recepción', valor: o => o.recepcion },
            { titulo: 'Orden de compra', valor: o => o.orden_compra ?? '' }, { titulo: 'Proveedor', valor: o => o.proveedor ?? '' },
            { titulo: 'Calidad', valor: o => o.calidad.toLowerCase() }, { titulo: 'Cantidad', valor: o => num(o.cantidad), alinear: 'right' },
          ]} />
        <Typography fontWeight={700} mt={3} mb={1}>A quién se le entregó</Typography>
        <TablaRegistros filas={d.clientes.map((c, i) => ({ ...c, id: i + 1 }))} vacio="El lote no ha salido de la bodega" etiqueta={c => c.a_quien}
          columnas={[
            { titulo: 'Destinatario', valor: c => <b>{c.a_quien}</b> }, { titulo: 'Contacto', valor: c => c.contacto ?? '' },
            { titulo: 'Documentos', valor: c => c.documentos.join(', ') }, { titulo: 'Última entrega', valor: c => fechaHora(c.ultima) },
            { titulo: 'Cantidad', valor: c => num(c.cantidad), alinear: 'right' },
          ]} />
        <Typography fontWeight={700} mt={3} mb={1}>Dónde queda</Typography>
        <TablaRegistros filas={d.queda.map((q, i) => ({ ...q, id: i + 1 }))} vacio="No queda nada en bodega" etiqueta={q => q.ubicacion}
          columnas={[
            { titulo: 'Ubicación', valor: q => q.ubicacion }, { titulo: 'Estiba', valor: q => q.contenedor ?? '' },
            { titulo: 'Disponible', valor: q => num(q.disponible), alinear: 'right' }, { titulo: 'Reservado', valor: q => num(q.reservado), alinear: 'right' },
            { titulo: 'Bloqueado', valor: q => num(q.bloqueado), alinear: 'right' },
          ]} />
      </>}
      <Dialog open={retener} onClose={() => setRetener(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Retener el lote {d?.lote.numero}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            El lote deja de alistarse y venderse, y todo lo disponible en bodega pasa a bloqueado. Lo que ya está reservado en órdenes
            se informa para que lo saque de ellas.
          </Alert>
          <TextField fullWidth multiline minRows={2} label="Motivo (queda en la trazabilidad)" value={motivo} onChange={e => setMotivo(e.target.value)} />
        </DialogContent>
        <DialogActions><Button color="inherit" onClick={() => setRetener(false)}>Cancelar</Button>
          <Button color="error" variant="contained" disabled={motivo.trim().length < 5} onClick={confirmarRetencion}>Retener</Button></DialogActions>
      </Dialog>
    </>
  )
}

export default function WMSTrazabilidad() {
  const [tab, setTab] = useState(0)
  return (
    <Layout title="WMS — Trazabilidad">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Timeline sx={{ fontSize: 28 }} />} titulo="Trazabilidad" color={COLOR}
          subtitulo="Kárdex con saldo y conciliación, recorrido de lotes de punta a punta y bitácora de eventos" />
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="Kárdex" /><Tab label="Recorrido de lote" /><Tab label="Bitácora de eventos" />
        </Tabs>
        {tab === 0 && <KardexTab />}
        {tab === 1 && <RecorridoTab />}
        {tab === 2 && <BitacoraEventos />}
      </Box>
    </Layout>
  )
}
