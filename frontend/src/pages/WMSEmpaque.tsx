/**
 * WMS · Empaque
 *
 * Para cada orden alistada, el sistema propone en qué cajas va (la más pequeña
 * que alcanza, respetando peso), con su peso real y el volumétrico que cobra la
 * transportadora. El empacador ajusta, pesa, confirma e imprime la etiqueta de
 * cada bulto. Peso y volumen pasan solos al despacho.
 */
import { useEffect, useState } from 'react'
import {
  Box, Paper, Typography, MenuItem, Button, Chip, Stack, Alert, Tabs, Tab, IconButton,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Inventory, Print, Delete, AutoFixHigh } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import QRCode from 'qrcode'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, FormularioRegistro, Cifra, errorApi, type Campo } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { sug, type Bulto } from '@/api/wmsSugerencias'
import { wms, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const esc = (x: unknown) => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))

async function etiquetas(orden: any, bultos: Bulto[]) {
  const total = bultos.length
  const paginas = await Promise.all(bultos.map(async (b, i) => {
    const qr = await QRCode.toDataURL(`${orden.numero_orden}/${i + 1}`, { margin: 0, width: 260 })
    return `<div class="e"><div class="c"><b>${esc(orden.cliente?.nombre)}</b></div>
      <div class="n">${esc(orden.numero_orden)}</div><div class="b">Bulto ${i + 1} de ${total}</div>
      <img src="${qr}"/><div>${num(b.peso_kg)} kg · ${b.largo_cm}×${b.ancho_cm}×${b.alto_cm} cm</div>
      <div class="m">${b.contenido.map(c => `${esc(c.sku ?? c.producto_id)} × ${num(c.cantidad)}`).join(' · ')}</div></div>`
  }))
  const w = window.open('', '_blank', 'width=480,height=720')
  if (!w) return
  w.document.write(`<html><head><title>${esc(orden.numero_orden)}</title><style>
    @page{size:100mm 150mm;margin:4mm} body{font-family:Arial,sans-serif;margin:0}
    .e{width:92mm;height:140mm;page-break-after:always;text-align:center} .n{font:700 26px monospace;margin:6px 0}
    .b{font-size:20px;font-weight:700;margin-bottom:6px} img{width:55mm;height:55mm} .m{font-size:10px;margin-top:6px}
    .c{font-size:14px}</style></head><body>${paginas.join('')}</body></html>`)
  w.document.close(); w.focus(); setTimeout(() => w.print(), 300)
}

function Empacar() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const ordenes = useQuery({ queryKey: ['emp-ordenes', almacen], enabled: !!almacen,
    queryFn: () => api.get('/wms/ordenes-salida/', { params: { almacen_id: almacen, estado: 'EN_PICKING,EMPACANDO', limite: 200 } }).then(r => r.data) })
  const cajas = useQuery({ queryKey: ['emp-cajas'], queryFn: sug.cajas })
  const [orden, setOrden] = useState<any | null>(null)
  const [bultos, setBultos] = useState<Bulto[]>([])
  const [info, setInfo] = useState<any>(null)
  const sugerir = async (o: any) => {
    setOrden(o); setBultos([]); setInfo(null)
    try {
      const actual = await sug.empaque(o.id)
      if (actual.bultos.length) { setBultos(actual.bultos); setInfo({ guardado: true }); return }
      const r = await sug.sugerirEmpaque(o.id)
      setBultos(r.bultos); setInfo(r)
    } catch (e) { toast.error(errorApi(e)) }
  }
  const cambiarCaja = (i: number, id: number) => {
    const c = (cajas.data ?? []).find(x => x.id === id)
    setBultos(bs => bs.map((b, j) => j === i ? { ...b, caja_id: id, caja: c?.codigo, largo_cm: c?.largo_cm, ancho_cm: c?.ancho_cm, alto_cm: c?.alto_cm } : b))
  }
  const confirmar = async () => {
    try {
      const r = await sug.confirmarEmpaque(orden.id, bultos.map(b => ({ caja_id: b.caja_id, largo_cm: b.largo_cm, ancho_cm: b.ancho_cm,
        alto_cm: b.alto_cm, peso_kg: b.peso_kg, contenido: b.contenido })))
      toast.success(`${r.bultos.length} bultos registrados: ${num(r.peso_total_kg)} kg, ${num(r.volumen_total_m3)} m³`)
      setInfo({ guardado: true }); qc.invalidateQueries({ queryKey: ['emp-ordenes'] })
    } catch (e) { toast.error(errorApi(e)) }
  }
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 4 }}>
        <TextField select fullWidth size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(Number(e.target.value))} sx={{ mb: 1.5 }}>
          {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
        </TextField>
        <TablaRegistros filas={ordenes.data ?? []} cargando={ordenes.isLoading} vacio="Sin órdenes en alistamiento o empaque" etiqueta={(o: any) => o.numero_orden}
          onFila={sugerir} columnas={[
            { titulo: 'Orden', valor: (o: any) => <Typography fontFamily="monospace" fontSize={13} fontWeight={700}>{o.numero_orden}</Typography> },
            { titulo: 'Cliente', valor: (o: any) => o.cliente?.nombre },
            { titulo: 'Estado', valor: (o: any) => <Chip size="small" label={o.estado.toLowerCase()} /> },
          ]} />
      </Grid>
      <Grid size={{ xs: 12, md: 8 }}>
        {!orden && <Alert severity="info">Elija una orden para proponer su empaque.</Alert>}
        {orden && <>
          <Stack direction="row" alignItems="center" gap={1} mb={1.5}>
            <Typography fontWeight={800} fontSize={18} fontFamily="monospace">{orden.numero_orden}</Typography>
            <Typography color="text.secondary">{orden.cliente?.nombre}</Typography>
            <Box flex={1} />
            {info?.guardado && <Button size="small" startIcon={<AutoFixHigh />} onClick={async () => { const r = await sug.sugerirEmpaque(orden.id); setBultos(r.bultos); setInfo(r) }}>Volver a sugerir</Button>}
          </Stack>
          {info?.avisos?.map((a: string) => <Alert key={a} severity="warning" sx={{ mb: 1 }}>{a}</Alert>)}
          {info?.sin_medidas?.length > 0 && <Alert severity="info" sx={{ mb: 1 }}>Sin medidas: {info.sin_medidas.map((s: any) => `${s.sku} × ${num(s.cantidad)}`).join(', ')}. Agréguelos a un bulto a mano o cubíquelos.</Alert>}
          {info?.peso_facturable_kg != null && <Grid container spacing={1.5} mb={1.5}>
            <Grid size={{ xs: 4 }}><Cifra etiqueta="Bultos" valor={bultos.length} color={COLOR} /></Grid>
            <Grid size={{ xs: 4 }}><Cifra etiqueta="Peso real" valor={`${num(info.peso_total_kg)} kg`} color="#0369A1" /></Grid>
            <Grid size={{ xs: 4 }}><Cifra etiqueta="Peso facturable" valor={`${num(info.peso_facturable_kg)} kg`} color="#7C3AED" sub="El mayor entre real y volumétrico" /></Grid>
          </Grid>}
          <Stack gap={1}>
            {bultos.map((b, i) => (
              <Paper key={i} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                <Stack direction="row" gap={1.5} alignItems="center" flexWrap="wrap">
                  <Typography fontWeight={800}>Bulto {i + 1}</Typography>
                  <TextField select size="small" label="Caja" value={b.caja_id ?? ''} onChange={e => cambiarCaja(i, Number(e.target.value))} sx={{ minWidth: 200 }}>
                    {(cajas.data ?? []).filter(c => c.activo).map(c => <MenuItem key={c.id} value={c.id}>{c.codigo} · {c.largo_cm}×{c.ancho_cm}×{c.alto_cm}</MenuItem>)}
                  </TextField>
                  <TextField size="small" type="number" label="Peso real (kg)" value={b.peso_kg ?? ''} sx={{ width: 140 }}
                    onChange={e => setBultos(bs => bs.map((x, j) => j === i ? { ...x, peso_kg: e.target.value === '' ? null : Number(e.target.value) } : x))} />
                  {b.llenado_pct != null && <Chip size="small" label={`llenado ${b.llenado_pct}%`} />}
                  <Box flex={1} />
                  <IconButton size="small" aria-label={`Quitar bulto ${i + 1}`} onClick={() => setBultos(bs => bs.filter((_, j) => j !== i))}><Delete fontSize="small" /></IconButton>
                </Stack>
                <Typography fontSize={12.5} color="text.secondary" mt={0.75}>{b.contenido.map(c => `${c.sku ?? c.producto_id} × ${num(c.cantidad)}`).join(' · ')}</Typography>
              </Paper>
            ))}
          </Stack>
          {!!bultos.length && <Stack direction="row" gap={1} mt={2} justifyContent="flex-end">
            <Button startIcon={<Print />} onClick={() => etiquetas(orden, bultos)}>Etiquetas</Button>
            <Button variant="contained" onClick={confirmar} sx={{ bgcolor: COLOR }}>{info?.guardado ? 'Guardar cambios' : 'Confirmar empaque'}</Button>
          </Stack>}
        </>}
      </Grid>
    </Grid>
  )
}

function Cajas() {
  const qc = useQueryClient()
  const cajas = useQuery({ queryKey: ['emp-cajas'], queryFn: sug.cajas })
  const [dlg, setDlg] = useState<{ abierto: boolean; r: any }>({ abierto: false, r: null })
  const campos: Campo[] = [
    { clave: 'codigo', etiqueta: 'Código', obligatorio: true, ancho: 4 }, { clave: 'nombre', etiqueta: 'Nombre', obligatorio: true, ancho: 8 },
    { clave: 'largo_cm', etiqueta: 'Largo interno (cm)', tipo: 'numero', obligatorio: true, min: 1, ancho: 4 },
    { clave: 'ancho_cm', etiqueta: 'Ancho interno (cm)', tipo: 'numero', obligatorio: true, min: 1, ancho: 4 },
    { clave: 'alto_cm', etiqueta: 'Alto interno (cm)', tipo: 'numero', obligatorio: true, min: 1, ancho: 4 },
    { clave: 'peso_max_kg', etiqueta: 'Peso máximo (kg)', tipo: 'numero', min: 0.1, ancho: 4 },
    { clave: 'tara_kg', etiqueta: 'Peso de la caja vacía (kg)', tipo: 'numero', min: 0, ancho: 4 },
    { clave: 'costo', etiqueta: 'Costo', tipo: 'numero', min: 0, ancho: 4 }, { clave: 'activo', etiqueta: 'Activa', tipo: 'interruptor' },
  ]
  return <>
    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}><Button variant="contained" sx={{ bgcolor: COLOR }} onClick={() => setDlg({ abierto: true, r: null })}>Nueva caja</Button></Box>
    <TablaRegistros filas={cajas.data ?? []} cargando={cajas.isLoading} vacio="Sin cajas: cree las que usa para despachar" etiqueta={c => c.codigo} onEditar={c => setDlg({ abierto: true, r: c })}
      columnas={[
        { titulo: 'Código', valor: c => c.codigo }, { titulo: 'Nombre', valor: c => c.nombre },
        { titulo: 'Interno', valor: c => `${c.largo_cm} × ${c.ancho_cm} × ${c.alto_cm} cm` },
        { titulo: 'Volumen', valor: c => `${num(c.volumen_m3)} m³`, alinear: 'right' }, { titulo: 'Máx.', valor: c => `${num(c.peso_max_kg)} kg`, alinear: 'right' },
        { titulo: 'Tara', valor: c => `${num(c.tara_kg)} kg`, alinear: 'right' }, { titulo: 'Estado', valor: c => c.activo ? 'Activa' : 'Inactiva' },
      ]} />
    <FormularioRegistro abierto={dlg.abierto} titulo={dlg.r ? 'Editar caja' : 'Nueva caja de despacho'} campos={campos} registro={dlg.r}
      valoresIniciales={{ activo: true, peso_max_kg: 25, tara_kg: 0 }} onCerrar={() => setDlg({ abierto: false, r: null })}
      onGuardar={async c => { if (dlg.r) await sug.editarCaja(dlg.r.id, c); else await sug.crearCaja(c); toast.success('Caja guardada'); qc.invalidateQueries({ queryKey: ['emp-cajas'] }) }} />
  </>
}

export default function WMSEmpaque() {
  const [tab, setTab] = useState(0)
  return (
    <Layout title="WMS — Empaque">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Inventory sx={{ fontSize: 28 }} />} titulo="Empaque" color={COLOR} subtitulo="La caja justa para cada orden, con su peso y su etiqueta" />
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Empacar" /><Tab label="Cajas de despacho" /></Tabs>
        {tab === 0 && <Empacar />}
        {tab === 1 && <Cajas />}
      </Box>
    </Layout>
  )
}
