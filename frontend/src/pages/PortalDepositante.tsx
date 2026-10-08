/**
 * Portal del cliente del 3PL (depositante): su inventario, sus movimientos de
 * entrada y salida, sus órdenes y recepciones, y sus facturas del servicio.
 * Es una pantalla aparte, sin el menú de la plataforma: el usuario del portal
 * no tiene acceso a nada más (lo impide la API, no solo esta pantalla).
 */
import { useState } from 'react'
import { Box, Typography, Tabs, Tab, TextField, Button, Chip, Stack, Paper, LinearProgress } from '@mui/material'
import Grid from '@mui/material/Grid2'
import { Logout, FileDownload, Warehouse } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import * as XLSX from 'xlsx'
import { apiClient as api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { TablaRegistros, Cifra } from '@/components/comun/Registro'
import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

const COLOR = COLOR_MODULO
const num = (v?: number | null) => v == null ? '—' : v.toLocaleString('es-CO', { maximumFractionDigits: 3 })
const pesos = (v?: number | null) => v == null ? '—' : v.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })
const fecha = (s?: string | null) => s ? aFecha(s).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: s.length > 10 ? 'short' : undefined }) : '—'
const traer = (ruta: string, params?: Record<string, unknown>) => api.get(ruta, { params }).then(r => r.data)

function exportar(nombre: string, filas: Record<string, unknown>[]) {
  const libro = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(filas), 'Hoja1')
  XLSX.writeFile(libro, `${nombre}.xlsx`)
}

export default function PortalDepositante() {
  const { user, portal, logout } = useAuthStore()
  const [tab, setTab] = useState(0)
  const [q, setQ] = useState('')
  const hoy = new Date().toLocaleDateString('en-CA')
  const [desde, setDesde] = useState(new Date(Date.now() - 30 * 864e5).toLocaleDateString('en-CA'))
  const [hasta, setHasta] = useState(hoy)
  const resumen = useQuery({ queryKey: ['portal-resumen'], queryFn: () => traer('/wms/portal/resumen') })
  const inv = useQuery({ queryKey: ['portal-inv', q], enabled: tab === 0, queryFn: () => traer('/wms/portal/inventario', { q: q || undefined }) })
  const mov = useQuery({ queryKey: ['portal-mov', desde, hasta], enabled: tab === 1, queryFn: () => traer('/wms/portal/movimientos', { desde, hasta }) })
  const ord = useQuery({ queryKey: ['portal-ord'], enabled: tab === 2, queryFn: () => traer('/wms/portal/ordenes') })
  const rec = useQuery({ queryKey: ['portal-rec'], enabled: tab === 3, queryFn: () => traer('/wms/portal/recepciones') })
  const fac = useQuery({ queryKey: ['portal-fac'], enabled: tab === 4, queryFn: () => traer('/wms/portal/facturacion') })
  const r = resumen.data
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: '#F8FAFC' }}>
      <Box sx={{ bgcolor: '#0F172A', color: '#fff', px: 3, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Warehouse />
        <Box flex={1}>
          <Typography fontWeight={800}>{portal?.nombre ?? r?.depositante?.nombre}</Typography>
          <Typography fontSize={12} sx={{ opacity: 0.75 }}>Portal de clientes · {user?.nombre} {user?.apellido}</Typography>
        </Box>
        <Button color="inherit" startIcon={<Logout />} onClick={() => { logout(); window.location.href = '/login' }}>Salir</Button>
      </Box>
      <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
        {resumen.isLoading && <LinearProgress />}
        {r && <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Referencias en bodega" valor={r.referencias} color={COLOR} /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Unidades" valor={num(r.unidades)} color="#0369A1" /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Disponibles" valor={num(r.disponibles)} color="#15803D" /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Cifra etiqueta="Bloqueadas" valor={num(r.bloqueadas)} color="#A855F7" sub="Cuarentena o retenidas" /></Grid>
          <Grid size={{ xs: 12, md: 2.4 }}><Cifra etiqueta="Órdenes en curso" valor={r.ordenes_en_curso} color="#D97706" sub={`${num(r.m3)} m³ ocupados`} /></Grid>
        </Grid>}
        <Paper variant="outlined" sx={{ borderRadius: 3, p: 2 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
            <Tab label="Inventario" /><Tab label="Movimientos" /><Tab label="Órdenes" /><Tab label="Recepciones" /><Tab label="Facturación" />
          </Tabs>
          {tab === 0 && <>
            <Stack direction="row" gap={1.5} mb={1.5}>
              <TextField size="small" label="Buscar producto" value={q} onChange={e => setQ(e.target.value)} />
              <Box flex={1} />
              <Button size="small" startIcon={<FileDownload />} disabled={!inv.data?.length} onClick={() => exportar('inventario', inv.data)}>Exportar</Button>
            </Stack>
            <TablaRegistros filas={(inv.data ?? []).map((x: any, i: number) => ({ ...x, id: i + 1 }))} cargando={inv.isLoading} vacio="Sin mercancía en bodega" etiqueta={(x: any) => x.sku}
              columnas={[
                { titulo: 'SKU', valor: (x: any) => x.sku }, { titulo: 'Producto', valor: (x: any) => x.nombre },
                { titulo: 'Lote', valor: (x: any) => x.lote ?? '' }, { titulo: 'Vence', valor: (x: any) => x.vence ?? '' },
                { titulo: 'Disponible', valor: (x: any) => num(x.disponible), alinear: 'right' },
                { titulo: 'En alistamiento', valor: (x: any) => num(x.reservado), alinear: 'right' },
                { titulo: 'Bloqueado', valor: (x: any) => num(x.bloqueado), alinear: 'right' },
                { titulo: 'Total', valor: (x: any) => <b>{num(x.total)}</b>, alinear: 'right' },
              ]} />
          </>}
          {tab === 1 && <>
            <Stack direction="row" gap={1.5} mb={1.5}>
              <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
              <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
              <Box flex={1} />
              <Button size="small" startIcon={<FileDownload />} disabled={!mov.data?.length} onClick={() => exportar('movimientos', mov.data)}>Exportar</Button>
            </Stack>
            <TablaRegistros filas={(mov.data ?? []).map((x: any, i: number) => ({ ...x, id: i + 1 }))} cargando={mov.isLoading} vacio="Sin movimientos en el periodo" etiqueta={(x: any) => x.sku}
              columnas={[
                { titulo: 'Fecha', valor: (x: any) => fecha(x.fecha) }, { titulo: 'Movimiento', valor: (x: any) => x.tipo },
                { titulo: 'SKU', valor: (x: any) => x.sku }, { titulo: 'Lote', valor: (x: any) => x.lote ?? '' },
                { titulo: 'Entrada', valor: (x: any) => x.entrada ? <Box sx={{ color: '#15803D', fontWeight: 700 }}>+{num(x.entrada)}</Box> : '', alinear: 'right' },
                { titulo: 'Salida', valor: (x: any) => x.salida ? <Box sx={{ color: '#DC2626', fontWeight: 700 }}>−{num(x.salida)}</Box> : '', alinear: 'right' },
                { titulo: 'Documento', valor: (x: any) => x.documento ?? '' }, { titulo: 'Nota', valor: (x: any) => x.notas ?? '' },
              ]} />
          </>}
          {tab === 2 && <TablaRegistros filas={(ord.data ?? []).map((x: any, i: number) => ({ ...x, id: i + 1 }))} cargando={ord.isLoading} vacio="Sin órdenes" etiqueta={(x: any) => x.numero}
            columnas={[
              { titulo: 'Orden', valor: (x: any) => x.numero }, { titulo: 'Destinatario', valor: (x: any) => x.destinatario },
              { titulo: 'Emitida', valor: (x: any) => x.emitida }, { titulo: 'Requerida', valor: (x: any) => x.requerida ?? '' },
              { titulo: 'Estado', valor: (x: any) => <Chip size="small" label={x.estado.toLowerCase()} /> },
              { titulo: 'Pedido / despachado', valor: (x: any) => `${num(x.pedido)} / ${num(x.despachado)}`, alinear: 'right' },
              { titulo: 'Despachos', valor: (x: any) => x.despachos.map((d: any) => `${d.numero} (${d.estado.toLowerCase()}${d.entregado ? `, entregado ${d.entregado}` : ''})`).join(' · ') },
            ]} />}
          {tab === 3 && <TablaRegistros filas={(rec.data ?? []).map((x: any, i: number) => ({ ...x, id: i + 1 }))} cargando={rec.isLoading} vacio="Sin recepciones" etiqueta={(x: any) => x.numero}
            columnas={[
              { titulo: 'Recepción', valor: (x: any) => x.numero }, { titulo: 'Fecha', valor: (x: any) => x.fecha },
              { titulo: 'Estado', valor: (x: any) => <Chip size="small" label={x.estado.toLowerCase()} /> },
              { titulo: 'Unidades', valor: (x: any) => num(x.unidades), alinear: 'right' },
            ]} />}
          {tab === 4 && <TablaRegistros filas={(fac.data ?? []).map((x: any, i: number) => ({ ...x, id: i + 1 }))} cargando={fac.isLoading} vacio="Sin facturas todavía" etiqueta={(x: any) => x.liquidacion}
            columnas={[
              { titulo: 'Factura', valor: (x: any) => x.factura ?? '' }, { titulo: 'Periodo', valor: (x: any) => `${x.desde} a ${x.hasta}` },
              { titulo: 'Detalle', valor: (x: any) => x.lineas.map((l: any) => `${l.descripcion}: ${pesos(l.subtotal)}`).join(' · ') },
              { titulo: 'Total', valor: (x: any) => pesos(x.total), alinear: 'right' },
              { titulo: 'Saldo', valor: (x: any) => pesos(x.saldo), alinear: 'right' }, { titulo: 'Vence', valor: (x: any) => x.vence ?? '' },
            ]} />}
        </Paper>
      </Box>
    </Box>
  )
}
