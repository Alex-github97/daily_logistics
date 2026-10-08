/**
 * POS · Vender
 *
 * La pantalla de mostrador. Se busca por nombre o SKU, o se escanea: un lector
 * de código de barras escribe el código y un Enter, y con eso el producto entra
 * al carrito. Solo aparecen productos con precio en la lista de la caja y con
 * existencia en las zonas vendibles de su almacén. El servidor vuelve a tomar
 * los precios y a verificar existencias al cobrar: lo que se ve aquí es la
 * vista previa, no lo que manda.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Box, Paper, Typography, Button, IconButton, Divider, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, Alert, Chip, InputAdornment, Tooltip,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { PointOfSale, Search, Add, Remove, Delete, Print, Person, Payments } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { pos, pesos, type ProductoCatalogo, type Venta } from '@/api/pos'
import { errorApi } from '@/components/comun/Registro'
import { COLOR_MODULO } from '@/config/marca'
import { Ticket, imprimirTicket } from '@/components/pos/Ticket'
import { useLectorGlobal } from '@/components/comun/LectorGlobal'

const COLOR = COLOR_MODULO

interface Item { p: ProductoCatalogo; cantidad: number; descuento: number }

const liquidar = (i: Item) => {
  const bruto = i.p.precio * i.cantidad
  const total = Math.round((bruto - bruto * i.descuento / 100) * 100) / 100
  const base = i.p.tarifa_iva > 0 ? Math.round(total / (1 + i.p.tarifa_iva / 100) * 100) / 100 : total
  return { total, base, iva: total - base }
}

function AbrirTurno({ onAbierto }: { onAbierto: () => void }) {
  const cajas = useQuery({ queryKey: ['pos', 'cajas'], queryFn: pos.cajas })
  const [caja, setCaja] = useState<number | ''>('')
  const [base, setBase] = useState('0')
  const libres = (cajas.data ?? []).filter(c => c.activa && !c.turno_abierto)
  const abrir = async () => {
    try { await pos.abrirTurno(Number(caja), Number(base)); toast.success('Turno abierto'); onAbierto() }
    catch (e) { toast.error(errorApi(e)) }
  }
  return (
    <Paper variant="outlined" sx={{ p: 4, borderRadius: 3, maxWidth: 480, mx: 'auto', mt: 6 }}>
      <Typography sx={{ fontWeight: 800, fontSize: 20, mb: 0.5 }}>Abrir turno de caja</Typography>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 2 }}>
        Elija la caja y cuente el efectivo con que empieza. Al cerrar, el sistema le dirá cuánto debe haber.
      </Typography>
      {cajas.data && libres.length === 0 && <Alert severity="info" sx={{ mb: 2 }}>No hay cajas libres. Créelas en POS · Configuración o espere a que se cierre un turno.</Alert>}
      <TextField select fullWidth size="small" label="Caja" value={caja} onChange={e => setCaja(Number(e.target.value))} sx={{ mb: 2 }}>
        {libres.map(c => <MenuItem key={c.id} value={c.id}>{c.codigo} · {c.nombre} ({c.almacen_nombre})</MenuItem>)}
      </TextField>
      <TextField fullWidth size="small" type="number" label="Base inicial en efectivo" value={base} onChange={e => setBase(e.target.value)}
        InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }} sx={{ mb: 2 }} />
      <Button fullWidth variant="contained" disabled={!caja} onClick={abrir} sx={{ bgcolor: COLOR }}>Abrir turno</Button>
    </Paper>
  )
}

export default function POSVenta() {
  const qc = useQueryClient()
  const turno = useQuery({ queryKey: ['pos', 'turno'], queryFn: pos.turnoActual })
  const medios = useQuery({ queryKey: ['pos', 'medios'], queryFn: pos.medios, staleTime: Infinity })
  const cajas = useQuery({ queryKey: ['pos', 'cajas'], queryFn: pos.cajas })
  const t = turno.data
  const caja = (cajas.data ?? []).find(c => c.id === t?.caja_id)
  const [q, setQ] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const catalogo = useQuery({ queryKey: ['pos', 'catalogo', t?.caja_id, busqueda], enabled: !!t,
    queryFn: () => pos.catalogo(t!.caja_id, busqueda || undefined) })
  const [carrito, setCarrito] = useState<Item[]>([])
  const [cliente, setCliente] = useState({ nombre: '', documento: '', email: '' })
  const [cobrar, setCobrar] = useState(false)
  const [pagos, setPagos] = useState<{ medio: string; monto: string; referencia: string }[]>([])
  const [ticket, setTicket] = useState<Venta | null>(null)
  const [enviando, setEnviando] = useState(false)
  const buscador = useRef<HTMLInputElement>(null)

  useEffect(() => { const h = setTimeout(() => setBusqueda(q.trim()), 250); return () => clearTimeout(h) }, [q])

  const totales = useMemo(() => carrito.reduce((s, i) => {
    const l = liquidar(i); return { total: s.total + l.total, base: s.base + l.base, iva: s.iva + l.iva, n: s.n + i.cantidad }
  }, { total: 0, base: 0, iva: 0, n: 0 }), [carrito])

  const agregar = (p: ProductoCatalogo) => {
    setCarrito(c => {
      const ya = c.find(i => i.p.producto_id === p.producto_id)
      const nueva = (ya?.cantidad ?? 0) + 1
      if (nueva > p.disponible) { toast.error(`Solo hay ${p.disponible} de ${p.nombre}`); return c }
      return ya ? c.map(i => i === ya ? { ...i, cantidad: nueva } : i) : [...c, { p, cantidad: 1, descuento: 0 }]
    })
  }
  // Un lector de códigos escribe el código y un Enter: si coincide exacto, entra solo.
  const alEnter = async (leido?: string) => {
    const codigo = (leido ?? q).trim()
    if (!codigo || !t) return
    const res = await pos.catalogo(t.caja_id, codigo)
    const exacto = res.find(p => p.codigo_barras === codigo || p.sku.toLowerCase() === codigo.toLowerCase())
    if (exacto) { agregar(exacto); setQ('') }
    else if (res.length === 1) { agregar(res[0]); setQ('') }
    else if (!res.length) toast.error('Sin coincidencias en la lista de esta caja')
  }
  // El lector también entra aunque el cursor no esté en el buscador.
  useLectorGlobal(c => { alEnter(c) }, !!t)
  const cambiar = (i: Item, campo: 'cantidad' | 'descuento', v: number) =>
    setCarrito(c => c.map(x => x === i ? { ...x, [campo]: v } : x))

  const abrirCobro = () => {
    setPagos([{ medio: 'EFECTIVO', monto: String(Math.round(totales.total)), referencia: '' }])
    setCobrar(true)
  }
  const pagado = pagos.reduce((s, p) => s + (Number(p.monto) || 0), 0)
  const noEfectivo = pagos.filter(p => p.medio !== 'EFECTIVO').reduce((s, p) => s + (Number(p.monto) || 0), 0)
  const cambio = Math.max(0, pagado - totales.total)
  const errorPago = pagado < totales.total - 0.005 ? `Faltan ${pesos(totales.total - pagado)}`
    : noEfectivo > totales.total + 0.005 ? 'El cambio solo se da en efectivo' : null

  const confirmar = async () => {
    setEnviando(true)
    try {
      const v = await pos.vender({
        caja_id: t!.caja_id,
        lineas: carrito.map(i => ({ producto_id: i.p.producto_id, cantidad: i.cantidad, descuento_pct: i.descuento })),
        pagos: pagos.filter(p => Number(p.monto) > 0).map(p => ({ medio: p.medio, monto: Number(p.monto), referencia: p.referencia || undefined })),
        cliente: { nombre: cliente.nombre || undefined, documento: cliente.documento || undefined, email: cliente.email || undefined },
      })
      setCobrar(false); setCarrito([]); setCliente({ nombre: '', documento: '', email: '' }); setTicket(v)
      qc.invalidateQueries({ queryKey: ['pos'] })
      toast.success(`Venta ${v.numero} registrada`)
    } catch (e) { toast.error(errorApi(e, 'No se pudo registrar la venta')) }
    finally { setEnviando(false) }
  }

  if (turno.isLoading) return <Layout><Box sx={{ p: 3 }} /></Layout>
  if (!t) return <Layout><Box sx={{ p: 3 }}><AbrirTurno onAbierto={() => qc.invalidateQueries({ queryKey: ['pos'] })} /></Box></Layout>

  return (
    <Layout>
      <Box sx={{ p: 2.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2, flexWrap: 'wrap' }}>
          <PointOfSale sx={{ color: COLOR }} />
          <Typography sx={{ fontWeight: 800, fontSize: 20 }}>{t.caja_nombre}</Typography>
          <Chip size="small" label={`Turno de ${t.cajero}`} />
          <Chip size="small" label={`${t.resumen.ventas} ventas · ${pesos(t.resumen.total_ventas)}`} />
          {caja && caja.descuento_maximo > 0 && <Chip size="small" label={`Descuento hasta ${caja.descuento_maximo}%`} />}
        </Box>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 7 }}>
            <TextField inputRef={buscador} autoFocus fullWidth size="small" placeholder="Buscar o escanear (nombre, SKU o código de barras)"
              value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Tab') { if (e.key === 'Tab' && !q.trim()) return; e.preventDefault(); alEnter() } }}
              InputProps={{ startAdornment: <InputAdornment position="start"><Search /></InputAdornment> }} sx={{ mb: 1.5 }} />
            <Grid container spacing={1}>
              {(catalogo.data ?? []).map(p => (
                <Grid key={p.producto_id} size={{ xs: 6, sm: 4, lg: 3 }}>
                  <Paper variant="outlined" role="button" aria-label={`Agregar ${p.nombre}`} onClick={() => p.disponible > 0 && agregar(p)}
                    sx={{ p: 1.25, borderRadius: 2, cursor: p.disponible > 0 ? 'pointer' : 'not-allowed', opacity: p.disponible > 0 ? 1 : 0.5,
                          '&:hover': { borderColor: COLOR }, height: '100%' }}>
                    <Typography sx={{ fontSize: 12.5, fontWeight: 700, lineHeight: 1.25 }}>{p.nombre}</Typography>
                    <Typography sx={{ fontSize: 10.5, color: 'text.secondary' }}>{p.sku}</Typography>
                    <Typography sx={{ fontSize: 15, fontWeight: 800, color: COLOR, mt: 0.5 }}>{pesos(p.precio)}</Typography>
                    <Typography sx={{ fontSize: 10.5, color: p.disponible > 0 ? 'text.secondary' : '#DC2626' }}>
                      {p.disponible > 0 ? `${p.disponible} ${p.unidad.toLowerCase()} disponibles` : 'Agotado'}
                    </Typography>
                  </Paper>
                </Grid>
              ))}
              {catalogo.data && catalogo.data.length === 0 && (
                <Typography sx={{ p: 2, color: 'text.secondary', fontSize: 13 }}>
                  {busqueda ? 'Sin coincidencias.' : 'La lista de precios de esta caja no tiene productos todavía.'}
                </Typography>
              )}
            </Grid>
          </Grid>
          <Grid size={{ xs: 12, md: 5 }}>
            <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, position: 'sticky', top: 12 }}>
              <Typography sx={{ fontWeight: 800, mb: 1 }}>Venta ({totales.n} unidades)</Typography>
              {carrito.length === 0 && <Typography sx={{ fontSize: 13, color: 'text.secondary', py: 3, textAlign: 'center' }}>Escanee o toque un producto.</Typography>}
              {carrito.map(i => {
                const l = liquidar(i)
                return (
                  <Box key={i.p.producto_id} sx={{ py: 1, borderBottom: '1px solid #F1F5F9' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                      <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{i.p.nombre}</Typography>
                      <Typography sx={{ fontSize: 13, fontWeight: 700 }}>{pesos(l.total)}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                      <IconButton size="small" aria-label="Quitar uno" onClick={() => i.cantidad > 1 ? cambiar(i, 'cantidad', i.cantidad - 1) : setCarrito(c => c.filter(x => x !== i))}><Remove fontSize="small" /></IconButton>
                      <TextField size="small" value={i.cantidad} sx={{ width: 64 }} inputProps={{ 'aria-label': 'Cantidad', style: { textAlign: 'center' } }}
                        onChange={e => { const v = Number(e.target.value); if (v > 0 && v <= i.p.disponible) cambiar(i, 'cantidad', v) }} />
                      <IconButton size="small" aria-label="Agregar uno" onClick={() => agregar(i.p)}><Add fontSize="small" /></IconButton>
                      <Typography sx={{ fontSize: 11.5, color: 'text.secondary', mx: 1 }}>× {pesos(i.p.precio)}</Typography>
                      {caja && caja.descuento_maximo > 0 && (
                        <TextField size="small" label="Dto %" value={i.descuento} sx={{ width: 76 }}
                          onChange={e => { const v = Number(e.target.value); if (v >= 0 && v <= caja.descuento_maximo) cambiar(i, 'descuento', v) }} />
                      )}
                      <Box sx={{ flex: 1 }} />
                      <IconButton size="small" aria-label={`Quitar ${i.p.nombre}`} onClick={() => setCarrito(c => c.filter(x => x !== i))}><Delete fontSize="small" /></IconButton>
                    </Box>
                  </Box>
                )
              })}
              <Divider sx={{ my: 1.5 }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>Base</span><span>{pesos(totales.base)}</span></Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>IVA incluido</span><span>{pesos(totales.iva)}</span></Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', fontSize: 22, fontWeight: 800, mt: 1 }}><span>Total</span><span>{pesos(totales.total)}</span></Box>
              <Divider sx={{ my: 1.5 }} />
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}><Person fontSize="small" sx={{ color: 'text.secondary' }} /><Typography sx={{ fontSize: 12.5, fontWeight: 700 }}>Cliente (vacío = consumidor final)</Typography></Box>
              <Grid container spacing={1}>
                <Grid size={6}><TextField size="small" fullWidth label="Cédula / NIT" value={cliente.documento} onChange={e => setCliente({ ...cliente, documento: e.target.value })} /></Grid>
                <Grid size={6}><TextField size="small" fullWidth label="Nombre" value={cliente.nombre} onChange={e => setCliente({ ...cliente, nombre: e.target.value })} /></Grid>
                <Grid size={12}><TextField size="small" fullWidth label="Correo para la factura" value={cliente.email} onChange={e => setCliente({ ...cliente, email: e.target.value })} /></Grid>
              </Grid>
              <Button fullWidth size="large" variant="contained" startIcon={<Payments />} disabled={!carrito.length || (!!cliente.documento && !cliente.nombre)}
                onClick={abrirCobro} sx={{ mt: 2, bgcolor: COLOR, py: 1.3, fontSize: 16, fontWeight: 800 }}>Cobrar {pesos(totales.total)}</Button>
              {!!cliente.documento && !cliente.nombre && <Typography sx={{ fontSize: 11.5, color: '#DC2626', mt: 0.5 }}>Con documento, escriba también el nombre.</Typography>}
            </Paper>
          </Grid>
        </Grid>

        <Dialog open={cobrar} onClose={() => setCobrar(false)} maxWidth="sm" fullWidth>
          <DialogTitle sx={{ fontWeight: 800 }}>Cobrar {pesos(totales.total)}</DialogTitle>
          <DialogContent>
            {pagos.map((p, k) => (
              <Box key={k} sx={{ display: 'flex', gap: 1, mt: 1.5 }}>
                <TextField select size="small" label="Medio" value={p.medio} sx={{ width: 170 }}
                  onChange={e => setPagos(ps => ps.map((x, j) => j === k ? { ...x, medio: e.target.value } : x))}>
                  {(medios.data ?? []).map(m => <MenuItem key={m.valor} value={m.valor}>{m.nombre}</MenuItem>)}
                </TextField>
                <TextField size="small" type="number" label={p.medio === 'EFECTIVO' ? 'Recibido' : 'Monto'} value={p.monto} sx={{ flex: 1 }}
                  onChange={e => setPagos(ps => ps.map((x, j) => j === k ? { ...x, monto: e.target.value } : x))} />
                {p.medio !== 'EFECTIVO' && <TextField size="small" label="Aprobación / ref." value={p.referencia} sx={{ width: 150 }}
                  onChange={e => setPagos(ps => ps.map((x, j) => j === k ? { ...x, referencia: e.target.value } : x))} />}
                {pagos.length > 1 && <IconButton aria-label="Quitar pago" onClick={() => setPagos(ps => ps.filter((_, j) => j !== k))}><Delete fontSize="small" /></IconButton>}
              </Box>
            ))}
            <Button size="small" startIcon={<Add />} sx={{ mt: 1 }}
              onClick={() => setPagos(ps => [...ps, { medio: 'TARJETA_DEBITO', monto: String(Math.max(0, Math.round(totales.total - pagado))), referencia: '' }])}>Pago mixto: agregar otro medio</Button>
            <Box sx={{ mt: 2, p: 1.5, borderRadius: 2, bgcolor: '#F8FAFC' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}><span>Pagado</span><b>{pesos(pagado)}</b></Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', fontSize: 20, fontWeight: 800, color: '#15803D' }}><span>Cambio</span><span>{pesos(cambio)}</span></Box>
            </Box>
            {errorPago && <Alert severity="warning" sx={{ mt: 1.5 }}>{errorPago}</Alert>}
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button color="inherit" onClick={() => setCobrar(false)}>Volver</Button>
            <Button variant="contained" disabled={!!errorPago || enviando} onClick={confirmar} sx={{ bgcolor: COLOR }}>
              {enviando ? 'Registrando…' : 'Confirmar venta'}
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog open={!!ticket} onClose={() => { setTicket(null); setTimeout(() => buscador.current?.focus(), 50) }} maxWidth="xs" fullWidth>
          <DialogContent>{ticket && <Ticket venta={ticket} />}</DialogContent>
          <DialogActions>
            <Tooltip title="Imprimir en la impresora de tickets"><Button startIcon={<Print />} onClick={() => ticket && imprimirTicket(ticket)}>Imprimir</Button></Tooltip>
            <Button variant="contained" onClick={() => { setTicket(null); setTimeout(() => buscador.current?.focus(), 50) }} sx={{ bgcolor: COLOR }}>Nueva venta</Button>
          </DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
