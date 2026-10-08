/**
 * POS · Ventas y devoluciones
 *
 * Consulta de ventas con su ticket (reimpresión) y devolución total o parcial:
 * se elige qué y cuánto vuelve, en qué estado (lo bueno regresa a la zona
 * vendible de donde salió, lo dañado a cuarentena) y cómo se reembolsa. El
 * servidor emite la nota crédito y el asiento inverso.
 */
import { useState } from 'react'
import {
  Box, Button, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, Typography, Tabs, Tab,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { ReceiptLong, Print, Undo } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { pos, pesos, type Venta } from '@/api/pos'
import { Encabezado, TablaRegistros, Etiqueta, errorApi } from '@/components/comun/Registro'
import { Ticket, imprimirTicket } from '@/components/pos/Ticket'
import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

const COLOR = COLOR_MODULO
const hoy = () => new Date().toLocaleDateString('en-CA')
const ESTADO_COLOR: Record<string, string> = { PAGADA: '#15803D', DEVUELTA_PARCIAL: '#D97706', DEVUELTA: '#DC2626' }

export default function POSVentas() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [desde, setDesde] = useState(hoy())
  const [hasta, setHasta] = useState(hoy())
  const [q, setQ] = useState('')
  const ventas = useQuery({ queryKey: ['pos', 'ventas', desde, hasta, q], queryFn: () => pos.ventas({ desde, hasta, q: q || undefined }) })
  const devs = useQuery({ queryKey: ['pos', 'devoluciones', desde, hasta], queryFn: () => pos.devoluciones({ desde, hasta }), enabled: tab === 1 })
  const medios = useQuery({ queryKey: ['pos', 'medios'], queryFn: pos.medios, staleTime: Infinity })
  const [ver, setVer] = useState<Venta | null>(null)
  const [dev, setDev] = useState<Venta | null>(null)
  const [cant, setCant] = useState<Record<number, string>>({})
  const [estado, setEstado] = useState<Record<number, string>>({})
  const [motivo, setMotivo] = useState('')
  const [medio, setMedio] = useState('EFECTIVO')

  const abrir = async (id: number, modo: 'ver' | 'dev') => {
    const v = await pos.venta(id)
    if (modo === 'ver') setVer(v)
    else { setDev(v); setCant({}); setEstado({}); setMotivo(''); setMedio(v.pagos?.[0]?.medio ?? 'EFECTIVO') }
  }
  const lineasDev = (dev?.lineas ?? []).filter(l => Number(cant[l.id]) > 0)
  const totalDev = lineasDev.reduce((s, l) => s + l.total / l.cantidad * Number(cant[l.id]), 0)
  const devolver = async () => {
    try {
      await pos.devolver({ venta_id: dev!.id, motivo, medio_reembolso: medio,
        lineas: lineasDev.map(l => ({ linea_id: l.id, cantidad: Number(cant[l.id]), estado: estado[l.id] ?? 'BUENO' })) })
      toast.success('Devolución registrada con su nota crédito'); setDev(null); qc.invalidateQueries({ queryKey: ['pos'] })
    } catch (e) { toast.error(errorApi(e)) }
  }

  return (
    <Layout>
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<ReceiptLong sx={{ fontSize: 28 }} />} titulo="Ventas y devoluciones" subtitulo="POS · Consulta, reimpresión y devoluciones con nota crédito" color={COLOR} />
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap' }}>
          <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" label="Número, cliente o documento" value={q} onChange={e => setQ(e.target.value)} sx={{ minWidth: 260 }} />
        </Box>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Ventas" /><Tab label="Devoluciones" /></Tabs>
        {tab === 0 && (
          <TablaRegistros filas={ventas.data ?? []} cargando={ventas.isLoading} vacio="Sin ventas en el periodo" etiqueta={(v: Venta) => v.numero}
            onFila={(v: Venta) => abrir(v.id, 'ver')}
            extra={(v: Venta) => <>
              <Button size="small" startIcon={<Print />} onClick={async () => imprimirTicket(await pos.venta(v.id))}>Ticket</Button>
              {v.estado !== 'DEVUELTA' && <Button size="small" color="warning" startIcon={<Undo />} onClick={() => abrir(v.id, 'dev')}>Devolver</Button>}
            </>}
            columnas={[
              { titulo: 'Número', valor: (v: Venta) => <Box sx={{ fontFamily: 'monospace' }}>{v.numero}</Box> },
              { titulo: 'Fecha', valor: (v: Venta) => aFecha(v.fecha).toLocaleString('es-CO') },
              { titulo: 'Caja', valor: (v: Venta) => v.caja_nombre },
              { titulo: 'Cajero', valor: (v: Venta) => v.cajero },
              { titulo: 'Cliente', valor: (v: Venta) => v.cliente_nombre },
              { titulo: 'Total', valor: (v: Venta) => pesos(v.total), alinear: 'right' },
              { titulo: 'Estado', valor: (v: Venta) => <Etiqueta texto={v.estado.replace('_', ' ').toLowerCase()} color={ESTADO_COLOR[v.estado] ?? '#64748B'} /> },
            ]} />
        )}
        {tab === 1 && (
          <TablaRegistros filas={devs.data ?? []} cargando={devs.isLoading} vacio="Sin devoluciones" etiqueta={(d: any) => `devolución ${d.id}`}
            columnas={[
              { titulo: 'Fecha', valor: (d: any) => aFecha(d.fecha).toLocaleString('es-CO') },
              { titulo: 'Venta', valor: (d: any) => d.venta_numero },
              { titulo: 'Cliente', valor: (d: any) => d.cliente },
              { titulo: 'Motivo', valor: (d: any) => d.motivo },
              { titulo: 'Reembolso', valor: (d: any) => d.medio_reembolso },
              { titulo: 'Total', valor: (d: any) => pesos(d.total), alinear: 'right' },
              { titulo: 'Cajero', valor: (d: any) => d.cajero },
            ]} />
        )}

        <Dialog open={!!ver} onClose={() => setVer(null)} maxWidth="xs" fullWidth>
          <DialogContent>{ver && <Ticket venta={ver} />}</DialogContent>
          <DialogActions><Button startIcon={<Print />} onClick={() => ver && imprimirTicket(ver)}>Imprimir</Button><Button onClick={() => setVer(null)}>Cerrar</Button></DialogActions>
        </Dialog>

        <Dialog open={!!dev} onClose={() => setDev(null)} maxWidth="md" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Devolución de {dev?.numero}</DialogTitle>
          <DialogContent>
            {(dev?.lineas ?? []).map(l => {
              const max = l.cantidad - l.cantidad_devuelta
              return (
                <Box key={l.id} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1, borderBottom: '1px solid #F1F5F9' }}>
                  <Box sx={{ flex: 1 }}>
                    <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{l.descripcion}</Typography>
                    <Typography sx={{ fontSize: 11.5, color: 'text.secondary' }}>Vendidas {l.cantidad} · ya devueltas {l.cantidad_devuelta} · {pesos(l.total / l.cantidad)} c/u</Typography>
                  </Box>
                  <TextField size="small" type="number" label={`Devolver (máx. ${max})`} value={cant[l.id] ?? ''} disabled={max <= 0} sx={{ width: 150 }}
                    onChange={e => { const v = Number(e.target.value); if (e.target.value === '' || (v >= 0 && v <= max)) setCant({ ...cant, [l.id]: e.target.value }) }} />
                  <TextField select size="small" label="Estado" value={estado[l.id] ?? 'BUENO'} sx={{ width: 170 }}
                    onChange={e => setEstado({ ...estado, [l.id]: e.target.value })}>
                    <MenuItem value="BUENO">Buen estado (vuelve a la venta)</MenuItem><MenuItem value="DANADO">Dañado (a cuarentena)</MenuItem>
                  </TextField>
                </Box>
              )
            })}
            <Box sx={{ display: 'flex', gap: 1.5, mt: 2 }}>
              <TextField size="small" label="Motivo" value={motivo} onChange={e => setMotivo(e.target.value)} sx={{ flex: 1 }} />
              <TextField select size="small" label="Reembolso por" value={medio} onChange={e => setMedio(e.target.value)} sx={{ width: 200 }}>
                {(medios.data ?? []).map(m => <MenuItem key={m.valor} value={m.valor}>{m.nombre}</MenuItem>)}
              </TextField>
            </Box>
            <Typography sx={{ fontSize: 18, fontWeight: 800, mt: 2 }}>A reembolsar: {pesos(totalDev)}</Typography>
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setDev(null)}>Cancelar</Button>
            <Button variant="contained" color="warning" disabled={!lineasDev.length || motivo.trim().length < 3} onClick={devolver}>Registrar devolución</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
