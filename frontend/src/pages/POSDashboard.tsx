/**
 * POS · Tablero
 *
 * Lo vendido en el periodo con su margen real (base sin IVA contra el costo
 * promedio con que salió del inventario), devoluciones, mezcla de medios de
 * pago, ventas por caja y los productos que más venden.
 */
import { useState } from 'react'
import { Box, Paper, Typography, TextField, LinearProgress } from '@mui/material'
import Grid from '@mui/material/Grid2'
import { PointOfSale } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { pos, pesos } from '@/api/pos'
import { Encabezado, TablaRegistros, Cifra } from '@/components/comun/Registro'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const hoy = () => new Date().toLocaleDateString('en-CA')

function Barras({ titulo, filas }: { titulo: string; filas: { nombre: string; valor: number; sub?: string }[] }) {
  const max = Math.max(1, ...filas.map(f => f.valor))
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, height: '100%' }}>
      <Typography sx={{ fontWeight: 700, mb: 1.5 }}>{titulo}</Typography>
      {!filas.length && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>Sin ventas en el periodo</Typography>}
      {filas.map(f => (
        <Box key={f.nombre} sx={{ mb: 1.25 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
            <span>{f.nombre}{f.sub ? <Typography component="span" sx={{ fontSize: 11.5, color: 'text.secondary' }}> · {f.sub}</Typography> : null}</span>
            <b>{pesos(f.valor)}</b>
          </Box>
          <LinearProgress variant="determinate" value={f.valor / max * 100} sx={{ height: 6, borderRadius: 3, '& .MuiLinearProgress-bar': { bgcolor: COLOR } }} />
        </Box>
      ))}
    </Paper>
  )
}

export default function POSDashboard() {
  const [desde, setDesde] = useState(hoy())
  const [hasta, setHasta] = useState(hoy())
  const t = useQuery({ queryKey: ['pos', 'tablero', desde, hasta], queryFn: () => pos.tablero({ desde, hasta }) })
  const d = t.data
  return (
    <Layout>
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<PointOfSale sx={{ fontSize: 28 }} />} titulo="Tablero del punto de venta" subtitulo="Ventas, margen, devoluciones y medios de pago" color={COLOR} />
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
          <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
        </Box>
        {t.isLoading && <LinearProgress />}
        {d && <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 6, md: 2 }}><Cifra etiqueta="Ventas" valor={d.ventas} color={COLOR} sub={`${d.turnos_abiertos} turno(s) abierto(s)`} /></Grid>
            <Grid size={{ xs: 6, md: 2 }}><Cifra etiqueta="Vendido" valor={pesos(d.total)} color="#15803D" sub={`IVA ${pesos(d.iva)}`} /></Grid>
            <Grid size={{ xs: 6, md: 2 }}><Cifra etiqueta="Ticket promedio" valor={pesos(d.ticket_promedio)} color="#0369A1" /></Grid>
            <Grid size={{ xs: 6, md: 2 }}><Cifra etiqueta="Costo de lo vendido" valor={pesos(d.costo)} color="#64748B" /></Grid>
            <Grid size={{ xs: 6, md: 2 }}><Cifra etiqueta="Margen bruto" valor={pesos(d.margen)} color="#7C3AED" sub={d.margen_pct == null ? undefined : `${d.margen_pct}% sobre la base`} /></Grid>
            <Grid size={{ xs: 6, md: 2 }}><Cifra etiqueta="Devoluciones" valor={pesos(d.devoluciones)} color="#DC2626" /></Grid>
          </Grid>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, md: 6 }}><Barras titulo="Por medio de pago" filas={d.por_medio.map((m: any) => ({ nombre: m.medio, valor: m.total }))} /></Grid>
            <Grid size={{ xs: 12, md: 6 }}><Barras titulo="Por caja" filas={d.por_caja.map((c: any) => ({ nombre: c.caja, valor: c.total, sub: `${c.ventas} ventas` }))} /></Grid>
          </Grid>
          <Typography sx={{ fontWeight: 700, mb: 1 }}>Productos más vendidos</Typography>
          <TablaRegistros filas={d.top_productos.map((p: any, i: number) => ({ ...p, id: i + 1 }))} vacio="Sin ventas en el periodo" etiqueta={(p: any) => p.producto}
            columnas={[
              { titulo: 'Producto', valor: (p: any) => p.producto },
              { titulo: 'Cantidad', valor: (p: any) => p.cantidad.toLocaleString('es-CO'), alinear: 'right' },
              { titulo: 'Vendido', valor: (p: any) => pesos(p.total), alinear: 'right' },
              { titulo: 'Margen', valor: (p: any) => pesos(p.margen), alinear: 'right' },
            ]} />
        </>}
      </Box>
    </Layout>
  )
}
