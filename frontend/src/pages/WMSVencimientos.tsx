import { useState } from 'react'
import {
  Box, Typography, Chip, Paper, Table, TableHead, TableBody, TableRow, TableCell, MenuItem, Button, Stack, InputAdornment, alpha, LinearProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { EventBusy, Search as SearchIcon, Download } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { apiClient as api } from '@/api/client'
import { exportarPDF, exportarExcel } from '@/utils/exportar'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const WMS_COLOR = COLOR_MODULO
const WMS_DARK = COLOR_MODULO

interface ItemVenc {
  inventario_id: number
  producto: { id: number; sku: string; nombre: string }
  lote: string
  ubicacion: string
  fecha_vencimiento: string
  dias_restantes: number
  cantidad_disponible: number
  estado: string
}
interface RespVenc {
  resumen: { vencidos: number; criticos: number; por_vencer: number; bloqueados: number }
  items: ItemVenc[]
}

const ESTADO_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  VENCIDO:    { color: '#DC2626', bg: '#FEF2F2', label: 'Vencido' },
  CRITICO:    { color: '#EA580C', bg: '#FFF7ED', label: 'Crítico (≤7d)' },
  POR_VENCER: { color: '#D97706', bg: '#FFFBEB', label: 'Por vencer' },
  BLOQUEADO:  { color: '#64748B', bg: '#F1F5F9', label: 'Bloqueado' },
}

export default function WMSVencimientos() {
  const [dias, setDias] = useState(30)
  const [busca, setBusca] = useState('')
  const [filtroEstado, setFiltroEstado] = useState('')

  const { data, isLoading } = useQuery<RespVenc>({
    queryKey: ['wms-vencimientos', dias],
    queryFn: () => api.get(`/wms/inventario/vencimientos?dias=${dias}`).then(r => r.data),
  })

  const resumen = data?.resumen ?? { vencidos: 0, criticos: 0, por_vencer: 0, bloqueados: 0 }
  const items = (data?.items ?? []).filter(it => {
    if (filtroEstado && it.estado !== filtroEstado) return false
    if (busca.trim()) {
      const q = busca.toLowerCase()
      return [it.producto.sku, it.producto.nombre, it.lote, it.ubicacion].some(x => (x ?? '').toLowerCase().includes(q))
    }
    return true
  })

  const columnas = [
    { key: 'sku', header: 'SKU' }, { key: 'producto', header: 'Producto' }, { key: 'lote', header: 'Lote' },
    { key: 'ubicacion', header: 'Ubicación' }, { key: 'fecha_vencimiento', header: 'Vencimiento' },
    { key: 'dias_restantes', header: 'Días' }, { key: 'cantidad', header: 'Disponible' }, { key: 'estado', header: 'Estado' },
  ]
  const filasExport = items.map(it => ({
    sku: it.producto.sku, producto: it.producto.nombre, lote: it.lote, ubicacion: it.ubicacion,
    fecha_vencimiento: it.fecha_vencimiento, dias_restantes: it.dias_restantes,
    cantidad: it.cantidad_disponible, estado: ESTADO_STYLE[it.estado]?.label ?? it.estado,
  }))
  const exportar = (tipo: 'pdf' | 'excel') => {
    const opts = { archivo: 'wms-control-vencimientos', titulo: 'WMS — Control de vencimientos (FEFO)', color: WMS_COLOR, columnas, filas: filasExport }
    tipo === 'pdf' ? exportarPDF(opts) : exportarExcel(opts)
  }

  const cards = [
    { l: 'Vencidos', v: resumen.vencidos, c: '#DC2626', e: 'VENCIDO' },
    { l: 'Críticos (≤7d)', v: resumen.criticos, c: '#EA580C', e: 'CRITICO' },
    { l: 'Por vencer', v: resumen.por_vencer, c: '#D97706', e: 'POR_VENCER' },
    { l: 'Bloqueados', v: resumen.bloqueados, c: '#64748B', e: 'BLOQUEADO' },
  ]

  return (
    <Layout title="WMS · Control de Vencimientos">
      <Box sx={{ p: 3, bgcolor: '#F0F2F5', minHeight: '100vh' }}>
        {/* Header */}
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3} flexWrap="wrap" gap={2}>
          <Stack direction="row" alignItems="center" gap={1.5}>
            <EventBusy sx={{ color: WMS_COLOR, fontSize: 34 }} />
            <Box>
              <Typography variant="h5" fontWeight={800} color={WMS_DARK}>Control de Vencimientos</Typography>
              <Typography fontSize={12} color="text.secondary">
                Inventario perecedero por vida útil · base del FEFO — el picking no despacha vencidos ni bloqueados (ISO 9001 §8.5.4)
              </Typography>
            </Box>
          </Stack>
          <Stack direction="row" gap={1}>
            <Button size="small" variant="outlined" startIcon={<Download />} onClick={() => exportar('pdf')} sx={{ textTransform: 'none' }}>PDF</Button>
            <Button size="small" variant="outlined" startIcon={<Download />} onClick={() => exportar('excel')} sx={{ textTransform: 'none' }}>Excel</Button>
          </Stack>
        </Stack>

        {/* Resumen */}
        <Grid container spacing={1.5} mb={2.5} className="anim-stagger">
          {cards.map(k => (
            <Grid key={k.l} size={{ xs: 6, md: 3 }}>
              <Paper elevation={0} className="hover-lift" onClick={() => setFiltroEstado(filtroEstado === k.e ? '' : k.e)}
                sx={{ p: 2, borderRadius: '14px', cursor: 'pointer', border: `1px solid ${filtroEstado === k.e ? k.c : '#E5E7EB'}`, bgcolor: filtroEstado === k.e ? alpha(k.c, 0.06) : '#FFFFFF' }}>
                <Typography className="text-gradient" fontSize={28} fontWeight={800} color={k.c} sx={{ fontVariantNumeric: 'tabular-nums' }}>{k.v}</Typography>
                <Typography fontSize={12} fontWeight={600} color="text.secondary">{k.l}</Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>

        {/* Filtros */}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} mb={2} alignItems={{ sm: 'center' }}>
          <TextField size="small" placeholder="Buscar SKU, producto, lote o ubicación…" value={busca} onChange={e => setBusca(e.target.value)}
            sx={{ minWidth: 280, flex: 1 }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 18, color: '#94A3B8' }} /></InputAdornment> }} />
          <TextField select size="small" label="Ventana de días" value={String(dias)} onChange={e => setDias(Number(e.target.value))} sx={{ minWidth: 160 }}>
            {[7, 15, 30, 60, 90, 180, 365].map(d => <MenuItem key={d} value={String(d)}>Próximos {d} días</MenuItem>)}
          </TextField>
          {filtroEstado && <Button size="small" onClick={() => setFiltroEstado('')} sx={{ textTransform: 'none' }}>Quitar filtro</Button>}
        </Stack>

        {isLoading && <LinearProgress sx={{ mb: 2 }} />}

        {/* Tabla */}
        <Paper elevation={0} sx={{ bgcolor: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: '14px', overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>{['SKU', 'Producto', 'Lote', 'Ubicación', 'Vencimiento', 'Días restantes', 'Disponible', 'Estado'].map(h => <TableCell key={h} sx={{ whiteSpace: 'nowrap' }}>{h}</TableCell>)}</TableRow>
            </TableHead>
            <TableBody>
              {items.map(it => {
                const st = ESTADO_STYLE[it.estado] ?? ESTADO_STYLE.POR_VENCER
                return (
                  <TableRow key={it.inventario_id} hover>
                    <TableCell sx={{ fontWeight: 700, color: WMS_DARK }}>{it.producto.sku}</TableCell>
                    <TableCell>{it.producto.nombre}</TableCell>
                    <TableCell>{it.lote}</TableCell>
                    <TableCell>{it.ubicacion}</TableCell>
                    <TableCell sx={{ fontVariantNumeric: 'tabular-nums' }}>{aFecha(it.fecha_vencimiento).toLocaleDateString('es-CO')}</TableCell>
                    <TableCell sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: st.color }}>
                      {it.dias_restantes < 0 ? `vencido hace ${Math.abs(it.dias_restantes)}d` : `${it.dias_restantes} d`}
                    </TableCell>
                    <TableCell sx={{ fontVariantNumeric: 'tabular-nums' }}>{it.cantidad_disponible.toLocaleString('es-CO')}</TableCell>
                    <TableCell><Chip size="small" label={st.label} sx={{ fontWeight: 700, fontSize: 10, color: st.color, bgcolor: st.bg }} /></TableCell>
                  </TableRow>
                )
              })}
              {items.length === 0 && (
                <TableRow><TableCell colSpan={8} align="center">
                  <Typography color="text.secondary" py={3}>{isLoading ? 'Cargando…' : 'Sin inventario perecedero en la ventana seleccionada'}</Typography>
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      </Box>
    </Layout>
  )
}
