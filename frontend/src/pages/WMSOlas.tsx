/**
 * WMS · Olas de alistamiento
 *
 * Varias órdenes se alistan en un solo recorrido: el sistema consolida lo que
 * hay que sacar de cada ubicación, ordena las paradas en serpentina y, en cada
 * parada, dice a qué orden va cada parte (las urgentes primero). Muestra cuánto
 * recorrido se ahorra frente a ir orden por orden.
 */
import { useEffect, useRef, useState } from 'react'
import {
  Box, Paper, Typography, MenuItem, Button, Chip, Stack, Alert, Dialog, DialogTitle, DialogContent, DialogActions, LinearProgress, Autocomplete,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Waves, CheckCircle, PlaylistAdd } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, Cifra, errorApi } from '@/components/comun/Registro'
import { sug, type Parada } from '@/api/wmsSugerencias'
import { wms, fechaHora, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO

export default function WMSOlas() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const olas = useQuery({ queryKey: ['olas', almacen], enabled: !!almacen, queryFn: () => sug.olas({ almacen_id: almacen }) })
  const [ver, setVer] = useState<number | null>(null)
  const ola = useQuery({ queryKey: ['ola', ver], enabled: !!ver, queryFn: () => sug.ola(ver!) })
  const [nueva, setNueva] = useState(false)
  const [filtro, setFiltro] = useState({ hasta: '', prioridades: [] as string[], max: '30' })
  const [parada, setParada] = useState<Parada | null>(null)
  const [scan, setScan] = useState({ ubicacion: '', producto: '', cantidad: '' })
  const campo = useRef<HTMLInputElement>(null)
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['olas'] }); qc.invalidateQueries({ queryKey: ['ola'] }) }

  const crear = async () => {
    try {
      const o = await sug.crearOla({ almacen_id: almacen, hasta_fecha_requerida: filtro.hasta || undefined,
        prioridades: filtro.prioridades.length ? filtro.prioridades : undefined, max_ordenes: Number(filtro.max) || 30 })
      toast.success(`Ola ${o.codigo} con ${o.ordenes.length} órdenes`); setNueva(false); refrescar(); setVer(o.id)
    } catch (e) { toast.error(errorApi(e)) }
  }
  const abrirParada = (p: Parada) => { setParada(p); setScan({ ubicacion: '', producto: '', cantidad: String(p.cantidad) }); setTimeout(() => campo.current?.focus(), 100) }
  const confirmar = async () => {
    try {
      await sug.parada(ver!, { ubicacion_id: parada!.ubicacion_id, producto_id: parada!.producto_id, lote_id: parada!.lote_id,
        contenedor_id: parada!.contenedor_id, cantidad: Number(scan.cantidad), ubicacion_codigo: scan.ubicacion || undefined,
        producto_codigo: scan.producto || undefined })
      toast.success('Parada confirmada'); setParada(null); refrescar()
    } catch (e) { toast.error(errorApi(e)) }
  }
  const d = ola.data
  return (
    <Layout title="WMS — Olas de alistamiento">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Waves sx={{ fontSize: 28 }} />} titulo="Olas de alistamiento" color={COLOR}
          subtitulo="Varias órdenes, un solo recorrido: paradas en serpentina y reparto por orden" />
        <Stack direction="row" gap={1.5} mb={2} alignItems="center">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => { setAlmacen(Number(e.target.value)); setVer(null) }} sx={{ minWidth: 240 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <Box flex={1} />
          <Button variant="contained" startIcon={<PlaylistAdd />} onClick={() => setNueva(true)} sx={{ bgcolor: COLOR }}>Nueva ola</Button>
        </Stack>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 4 }}>
            <TablaRegistros filas={olas.data ?? []} cargando={olas.isLoading} vacio="Sin olas" etiqueta={o => o.codigo} onFila={o => setVer(o.id)}
              columnas={[
                { titulo: 'Ola', valor: o => <Typography fontFamily="monospace" fontWeight={700} fontSize={13}>{o.codigo}</Typography> },
                { titulo: 'Órdenes', valor: o => o.ordenes.length, alinear: 'right' },
                { titulo: 'Estado', valor: o => <Chip size="small" label={o.estado.toLowerCase()} color={o.estado === 'COMPLETADA' ? 'success' : o.estado === 'EN_CURSO' ? 'info' : 'default'} /> },
              ]} />
          </Grid>
          <Grid size={{ xs: 12, md: 8 }}>
            {!ver && <Alert severity="info">Elija una ola o cree una con las órdenes pendientes.</Alert>}
            {ola.isFetching && !d && <LinearProgress />}
            {d && <>
              <Stack direction="row" gap={1} alignItems="center" mb={1.5} flexWrap="wrap">
                <Typography fontWeight={800} fontSize={18} fontFamily="monospace">{d.codigo}</Typography>
                <Chip size="small" label={d.estado.toLowerCase()} />
                <Typography fontSize={12} color="text.secondary">{d.criterio} · {fechaHora(d.creada)}</Typography>
              </Stack>
              <Grid container spacing={1.5} mb={2}>
                <Grid size={{ xs: 4 }}><Cifra etiqueta="Paradas" valor={d.visitas_ola ?? 0} color={COLOR} sub={`${d.visitas_orden_por_orden} orden por orden`} /></Grid>
                <Grid size={{ xs: 4 }}><Cifra etiqueta="Recorrido (posiciones)" valor={d.recorrido_ola ?? 0} color="#0369A1" sub={`${d.recorrido_orden_por_orden} orden por orden`} /></Grid>
                <Grid size={{ xs: 4 }}><Cifra etiqueta="Recorrido ahorrado" valor={d.ahorro_recorrido_pct == null ? '—' : `${d.ahorro_recorrido_pct}%`} color="#15803D" /></Grid>
              </Grid>
              {d.ordenes.some(o => o.sin_existencia) && <Alert severity="warning" sx={{ mb: 1.5 }}>
                Sin existencia para alistar: {d.ordenes.filter(o => o.sin_existencia).map(o => o.numero).join(', ')}.</Alert>}
              <Stack gap={1}>
                {(d.paradas ?? []).map((p, i) => (
                  <Paper key={`${p.ubicacion_id}-${p.producto_id}-${p.lote_id}-${p.contenedor_id}`} variant="outlined"
                    sx={{ p: 1.5, borderRadius: 2, opacity: p.hecha ? 0.6 : 1, borderLeft: `4px solid ${p.hecha ? '#15803D' : COLOR}` }}>
                    <Stack direction="row" alignItems="center" gap={1.5} flexWrap="wrap">
                      <Typography fontWeight={800} sx={{ width: 28 }}>{i + 1}</Typography>
                      <Typography fontFamily="monospace" fontWeight={700} sx={{ minWidth: 110 }}>{p.ubicacion}</Typography>
                      <Box flex={1}>
                        <Typography fontSize={13} fontWeight={600}>{p.sku} · {p.producto}{p.lote ? ` · lote ${p.lote}` : ''}{p.contenedor ? ` · ${p.contenedor}` : ''}</Typography>
                        <Typography fontSize={11.5} color="text.secondary">
                          {p.reparto.map(r => `${r.orden}: ${r.alistado != null ? `${num(r.alistado)}/${num(r.cantidad)}` : num(r.cantidad)}`).join(' · ')}
                        </Typography>
                      </Box>
                      <Typography fontWeight={800} fontSize={18}>{p.hecha ? `${num(p.alistado)} ✓` : num(p.cantidad)}</Typography>
                      {p.hecha ? <CheckCircle sx={{ color: '#15803D' }} /> :
                        <Button size="small" variant="contained" sx={{ bgcolor: COLOR }} onClick={() => abrirParada(p)}>Alistar</Button>}
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            </>}
          </Grid>
        </Grid>

        <Dialog open={nueva} onClose={() => setNueva(false)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Nueva ola</DialogTitle>
          <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
            <Typography fontSize={13} color="text.secondary">Toma las órdenes pendientes del almacén, las urgentes y las de fecha más próxima primero.</Typography>
            <TextField size="small" type="date" label="Requeridas hasta" value={filtro.hasta} onChange={e => setFiltro({ ...filtro, hasta: e.target.value })} InputLabelProps={{ shrink: true }} />
            <Autocomplete multiple size="small" options={['URGENTE', 'ALTA', 'NORMAL', 'BAJA']} value={filtro.prioridades}
              onChange={(_, v) => setFiltro({ ...filtro, prioridades: v })} renderInput={p => <TextField {...p} label="Prioridades (vacío = todas)" />} />
            <TextField size="small" type="number" label="Máximo de órdenes" value={filtro.max} onChange={e => setFiltro({ ...filtro, max: e.target.value })} />
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setNueva(false)}>Cancelar</Button>
            <Button variant="contained" onClick={crear} sx={{ bgcolor: COLOR }}>Crear ola</Button></DialogActions>
        </Dialog>

        <Dialog open={!!parada} onClose={() => setParada(null)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Parada en {parada?.ubicacion}</DialogTitle>
          <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
            <Typography fontSize={13}>{parada?.sku} · {parada?.producto}: saque <b>{num(parada?.cantidad)}</b></Typography>
            <TextField inputRef={campo} size="small" label="Escanee la ubicación" value={scan.ubicacion} onChange={e => setScan({ ...scan, ubicacion: e.target.value })} />
            <TextField size="small" label="Escanee el producto" value={scan.producto} onChange={e => setScan({ ...scan, producto: e.target.value })} />
            <TextField size="small" type="number" label="Cantidad sacada" value={scan.cantidad} onChange={e => setScan({ ...scan, cantidad: e.target.value })}
              helperText="Si sacó menos, el faltante le queda a las órdenes de menor prioridad" />
            <Typography fontSize={12} color="text.secondary">Reparto: {parada?.reparto.map(r => `${r.orden} ${num(r.cantidad)}`).join(' · ')}</Typography>
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setParada(null)}>Volver</Button>
            <Button variant="contained" disabled={scan.cantidad === '' || Number(scan.cantidad) < 0} onClick={confirmar} sx={{ bgcolor: COLOR }}>Confirmar</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
