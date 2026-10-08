/**
 * WMS · Estibas (LPN)
 *
 * Cada estiba, caja o canasta tiene su etiqueta (License Plate Number). Lo que
 * va adentro viaja con ella: moverla mueve todo su contenido y deja cada línea
 * en el kárdex. Aquí se crean, se arman con mercancía suelta de su ubicación,
 * se mueven escaneando el destino, se cierran y se imprime su etiqueta.
 */
import { useState } from 'react'
import {
  Box, Typography, MenuItem, Button, Chip, Dialog, DialogTitle, DialogContent, DialogActions, Stack, Alert, Autocomplete, Tabs, Tab,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { ViewInAr, Add, Print, OpenWith, Lock, Search } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import QRCode from 'qrcode'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, errorApi } from '@/components/comun/Registro'
import { wms, TIPO_MOV, fechaHora, num, type Contenedor } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const ESTADO_COLOR: Record<string, string> = { ABIERTO: '#2563EB', CERRADO: '#15803D', VACIO: '#94A3B8', DESPACHADO: '#7C3AED', ANULADO: '#64748B' }
const esc = (x: unknown) => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))

async function imprimirEtiqueta(c: Contenedor) {
  const qr = await QRCode.toDataURL(c.codigo, { margin: 0, width: 360 })
  const lineas = (c.contenido ?? []).slice(0, 6).map(l =>
    `<tr><td>${esc(l.sku)}</td><td>${esc(l.producto)}</td><td>${esc(l.lote ?? '')}</td><td style="text-align:right">${num(l.disponible + l.reservado + l.bloqueado)}</td></tr>`).join('')
  const w = window.open('', '_blank', 'width=480,height=720')
  if (!w) return
  w.document.write(`<html><head><title>${esc(c.codigo)}</title><style>
    @page{size:100mm 150mm;margin:4mm} body{font-family:Arial,sans-serif;margin:0;width:92mm}
    .c{text-align:center} .cod{font:700 30px monospace;letter-spacing:2px;margin:4px 0}
    table{width:100%;border-collapse:collapse;font-size:10px} td{border-top:1px solid #000;padding:2px}
    .m{font-size:11px}</style></head><body>
    <div class="c"><img src="${qr}" style="width:62mm;height:62mm"/><div class="cod">${esc(c.codigo)}</div></div>
    <div class="m"><b>${esc(c.tipo)}</b> · ${esc(c.almacen)} · ${esc(c.depositante ?? '')}</div>
    <div class="m">Ubicación: <b>${esc(c.ubicacion ?? 'sin ubicar')}</b> · ${num(c.unidades)} und</div>
    <table>${lineas}</table></body></html>`)
  w.document.close(); w.focus(); setTimeout(() => w.print(), 300)
}

export default function WMSEstibas() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const ubicaciones = useQuery({ queryKey: ['wms-ubicaciones-lista'], queryFn: wms.ubicaciones })
  const productos = useQuery({ queryKey: ['wms-productos-lista'], queryFn: wms.productos })
  const [almacen, setAlmacen] = useState<number | ''>('')
  const [estado, setEstado] = useState('ABIERTO,CERRADO')
  const [q, setQ] = useState('')
  const lista = useQuery({ queryKey: ['wms-estibas', almacen, estado, q], queryFn: () => wms.contenedores({ almacen_id: almacen || undefined, estado, q: q || undefined }) })
  const [ver, setVer] = useState<number | null>(null)
  const ficha = useQuery({ queryKey: ['wms-estiba', ver], enabled: !!ver, queryFn: () => wms.contenedor(ver!) })
  const [tabFicha, setTabFicha] = useState(0)
  const [nueva, setNueva] = useState(false)
  const [n, setN] = useState({ almacen_id: '' as number | '', ubicacion_codigo: '', tipo: 'ESTIBA' })
  const [mover, setMover] = useState('')
  const [agregar, setAgregar] = useState<{ producto: any | null; lote_id: string; cantidad: string }>({ producto: null, lote_id: '', cantidad: '' })
  const [escaneo, setEscaneo] = useState('')
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['wms-estibas'] }); qc.invalidateQueries({ queryKey: ['wms-estiba'] }) }
  const c = ficha.data

  const accion = async (f: () => Promise<unknown>, ok: string) => {
    try { await f(); toast.success(ok); refrescar() } catch (e) { toast.error(errorApi(e)) }
  }
  const buscarCodigo = async () => {
    if (!escaneo.trim()) return
    try { const r = await wms.contenedorPorCodigo(escaneo.trim()); setVer(r.id); setTabFicha(0); setEscaneo('') }
    catch (e) { toast.error(errorApi(e)) }
  }

  return (
    <Layout title="WMS — Estibas">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<ViewInAr sx={{ fontSize: 28 }} />} titulo="Estibas y contenedores (LPN)" color={COLOR}
          subtitulo="Unidades de manejo con etiqueta propia: lo que llevan adentro viaja con ellas" />
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap" alignItems="center">
          <TextField size="small" label="Escanear etiqueta" value={escaneo} onChange={e => setEscaneo(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') buscarCodigo() }} InputProps={{ endAdornment: <Search fontSize="small" /> }} sx={{ width: 200 }} />
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 200 }}>
            <MenuItem value="">Todos</MenuItem>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Estado" value={estado} onChange={e => setEstado(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="ABIERTO,CERRADO">En bodega</MenuItem><MenuItem value="VACIO">Vacías</MenuItem>
            <MenuItem value="DESPACHADO">Despachadas</MenuItem>
          </TextField>
          <TextField size="small" label="Código" value={q} onChange={e => setQ(e.target.value)} />
          <Box flex={1} />
          <Button variant="contained" startIcon={<Add />} onClick={() => setNueva(true)} sx={{ bgcolor: COLOR }}>Nueva estiba</Button>
        </Stack>
        <TablaRegistros filas={lista.data ?? []} cargando={lista.isLoading} vacio="Sin estibas" etiqueta={x => x.codigo}
          onFila={x => { setVer(x.id); setTabFicha(0) }}
          columnas={[
            { titulo: 'Código', valor: x => <Typography fontFamily="monospace" fontWeight={700}>{x.codigo}</Typography> },
            { titulo: 'Tipo', valor: x => x.tipo.toLowerCase() },
            { titulo: 'Estado', valor: x => <Chip size="small" label={x.estado.toLowerCase()} sx={{ bgcolor: ESTADO_COLOR[x.estado], color: '#fff', height: 20 }} /> },
            { titulo: 'Ubicación', valor: x => x.ubicacion ?? 'sin ubicar' },
            { titulo: 'Depositante', valor: x => x.depositante ?? '' },
            { titulo: 'Líneas', valor: x => x.lineas, alinear: 'right' },
            { titulo: 'Unidades', valor: x => num(x.unidades), alinear: 'right' },
            { titulo: 'Origen', valor: x => x.documento_tipo ? `${x.documento_tipo.toLowerCase()} ${x.documento_id}` : 'manual' },
            { titulo: 'Creada', valor: x => fechaHora(x.creado) },
          ]} />

        <Dialog open={!!ver} onClose={() => setVer(null)} maxWidth="md" fullWidth>
          <DialogTitle sx={{ fontWeight: 800 }}>
            <Typography component="span" fontFamily="monospace" fontWeight={800} fontSize={20}>{c?.codigo}</Typography>
            {c && <Chip size="small" label={c.estado.toLowerCase()} sx={{ ml: 1, bgcolor: ESTADO_COLOR[c.estado], color: '#fff' }} />}
            <Typography fontSize={13} color="text.secondary">{c?.almacen} · {c?.ubicacion ?? 'sin ubicar'} · {c?.depositante ?? ''} · {num(c?.unidades)} und</Typography>
          </DialogTitle>
          <DialogContent>
            <Tabs value={tabFicha} onChange={(_, v) => setTabFicha(v)} sx={{ mb: 2 }}>
              <Tab label="Contenido" /><Tab label="Historia" /><Tab label="Mover / armar" />
            </Tabs>
            {tabFicha === 0 && <TablaRegistros filas={(c?.contenido ?? []).map((l, i) => ({ ...l, id: i + 1 }))} vacio="Vacía" etiqueta={l => l.sku ?? ''}
              columnas={[{ titulo: 'SKU', valor: l => l.sku }, { titulo: 'Producto', valor: l => l.producto }, { titulo: 'Lote', valor: l => l.lote ?? '' },
                { titulo: 'Disponible', valor: l => num(l.disponible), alinear: 'right' }, { titulo: 'Reservado', valor: l => num(l.reservado), alinear: 'right' },
                { titulo: 'Bloqueado', valor: l => num(l.bloqueado), alinear: 'right' }]} />}
            {tabFicha === 1 && <TablaRegistros filas={(c?.historia ?? []).slice().reverse()} vacio="Sin movimientos" etiqueta={m => `movimiento ${m.id}`}
              columnas={[{ titulo: 'Fecha', valor: m => fechaHora(m.fecha) }, { titulo: 'Tipo', valor: m => TIPO_MOV[m.tipo] ?? m.tipo },
                { titulo: 'Producto', valor: m => m.sku }, { titulo: 'Cantidad', valor: m => num(m.cantidad), alinear: 'right' },
                { titulo: 'Ruta', valor: m => `${m.origen ?? '—'} → ${m.destino ?? '—'}` }, { titulo: 'Quién', valor: m => m.usuario ?? '' }]} />}
            {tabFicha === 2 && c && (
              <Stack gap={2}>
                {['ABIERTO', 'CERRADO'].includes(c.estado) ? <>
                  <Stack direction="row" gap={1}>
                    <TextField size="small" label="Escanee la ubicación destino" value={mover} onChange={e => setMover(e.target.value)} sx={{ flex: 1 }}
                      onKeyDown={e => { if (e.key === 'Enter' && mover.trim()) accion(() => wms.moverContenedor(c.id, mover.trim()), 'Estiba movida').then(() => setMover('')) }} />
                    <Button startIcon={<OpenWith />} disabled={!mover.trim()} onClick={() => accion(() => wms.moverContenedor(c.id, mover.trim()), 'Estiba movida').then(() => setMover(''))}>Mover entera</Button>
                  </Stack>
                  {c.estado === 'ABIERTO' && c.ubicacion && <>
                    <Typography fontSize={13} fontWeight={700}>Armar: agregar mercancía suelta de {c.ubicacion}</Typography>
                    <Stack direction="row" gap={1}>
                      <Autocomplete size="small" sx={{ flex: 2 }} options={productos.data ?? []} value={agregar.producto}
                        getOptionLabel={(p: any) => `${p.sku} · ${p.nombre}`} onChange={(_, v) => setAgregar({ ...agregar, producto: v })}
                        renderInput={p => <TextField {...p} label="Producto" />} />
                      <TextField size="small" label="Lote (id)" value={agregar.lote_id} onChange={e => setAgregar({ ...agregar, lote_id: e.target.value })} sx={{ width: 110 }} />
                      <TextField size="small" type="number" label="Cantidad" value={agregar.cantidad} onChange={e => setAgregar({ ...agregar, cantidad: e.target.value })} sx={{ width: 120 }} />
                      <Button disabled={!agregar.producto || !(Number(agregar.cantidad) > 0)} onClick={() => accion(() => wms.agregarAContenedor(c.id, {
                        producto_id: agregar.producto.id, lote_id: agregar.lote_id ? Number(agregar.lote_id) : null, cantidad: Number(agregar.cantidad) }), 'Agregado a la estiba')
                        .then(() => setAgregar({ producto: null, lote_id: '', cantidad: '' }))}>Agregar</Button>
                    </Stack>
                  </>}
                </> : <Alert severity="info">Una estiba {c.estado.toLowerCase()} no se mueve ni se arma.</Alert>}
              </Stack>
            )}
          </DialogContent>
          <DialogActions>
            {c && c.estado === 'ABIERTO' && <Button startIcon={<Lock />} onClick={() => accion(() => wms.cerrarContenedor(c.id), 'Estiba cerrada')}>Cerrar estiba</Button>}
            {c && <Button startIcon={<Print />} onClick={() => imprimirEtiqueta(c)}>Imprimir etiqueta</Button>}
            <Button onClick={() => setVer(null)}>Salir</Button>
          </DialogActions>
        </Dialog>

        <Dialog open={nueva} onClose={() => setNueva(false)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Nueva estiba</DialogTitle>
          <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
            <TextField select size="small" label="Almacén" value={n.almacen_id} onChange={e => setN({ ...n, almacen_id: Number(e.target.value) })}>
              {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
            </TextField>
            <Autocomplete size="small" options={(ubicaciones.data ?? []).map(u => u.codigo as string)} value={n.ubicacion_codigo || null}
              onChange={(_, v) => setN({ ...n, ubicacion_codigo: v ?? '' })} renderInput={p => <TextField {...p} label="Ubicación (opcional)" />} />
            <TextField select size="small" label="Tipo" value={n.tipo} onChange={e => setN({ ...n, tipo: e.target.value })}>
              {['ESTIBA', 'CAJA', 'CANASTA', 'CONTENEDOR'].map(t => <MenuItem key={t} value={t}>{t.toLowerCase()}</MenuItem>)}
            </TextField>
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setNueva(false)}>Cancelar</Button>
            <Button variant="contained" disabled={!n.almacen_id} sx={{ bgcolor: COLOR }} onClick={async () => {
              try {
                const r = await wms.crearContenedor({ almacen_id: n.almacen_id, ubicacion_codigo: n.ubicacion_codigo || undefined, tipo: n.tipo })
                toast.success(`Estiba ${r.codigo} creada`); setNueva(false); refrescar(); setVer(r.id); setTabFicha(2)
              } catch (e) { toast.error(errorApi(e)) }
            }}>Crear</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
