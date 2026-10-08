/**
 * Ocupación de la bodega (WMS › Inventario › Ocupación de bodega).
 *
 * Antes vivía en Cubicaje › Ubicaciones. Muestra el piso en m² (huella de cada
 * estantería, contada una vez aunque tenga varios niveles), el uso cúbico en
 * m³ y las posiciones ocupadas, por zona y por ubicación.
 */
import { useMemo, useState } from 'react'
import {
  Alert, Box, Chip, LinearProgress, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Typography,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import { useQuery } from '@tanstack/react-query'
import { TextField } from '@/components/comun/Desplegables'
import { TablaRegistros, Cifra } from '@/components/comun/Registro'
import { cubicaje, dims } from '@/api/wmsCubicaje'
import { wms, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

interface ZonaArea {
  zona: string; tipo: string; area_m2: number; ocupada_m2: number; libre_m2: number
  ocupacion_pct: number | null; huellas: number; huellas_sin_medidas: number
}

const colorPct = (p: number) => (p > 95 ? '#DC2626' : p > 80 ? '#D97706' : '#15803D')

function Barra({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <>—</>
  return (
    <Box sx={{ minWidth: 120 }}>
      <LinearProgress variant="determinate" value={Math.min(100, pct)}
        sx={{ height: 8, borderRadius: 4, mb: 0.25, '& .MuiLinearProgress-bar': { bgcolor: colorPct(pct) } }} />
      <Typography fontSize={11}>{pct}%</Typography>
    </Box>
  )
}

export default function OcupacionBodega() {
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  const res = useQuery({ queryKey: ['cub-resumen', almacen], queryFn: () => cubicaje.resumen(almacen || undefined) })
  const ocu = useQuery({ queryKey: ['cub-ocupacion', almacen], queryFn: () => cubicaje.ocupacion(almacen || undefined) })
  const d = res.data
  const filas = useMemo(() => (ocu.data ?? []).slice().sort((a, b) => (b.ocupacion_pct ?? -1) - (a.ocupacion_pct ?? -1)), [ocu.data])
  const zonas: ZonaArea[] = d?.area_por_zona ?? []

  return (
    <>
      <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 240, mb: 2 }}>
        <MenuItem value="">Todos</MenuItem>{(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
      </TextField>
      {d && <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Área ocupada" valor={d.ocupacion_area_pct == null ? '—' : `${d.ocupacion_area_pct}%`} color={COLOR_MODULO}
          sub={`${num(d.area_ocupada_m2)} de ${num(d.area_m2)} m² · libres ${num(d.area_libre_m2)} m²`} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Utilización cúbica" valor={d.utilizacion_cubica_pct == null ? '—' : `${d.utilizacion_cubica_pct}%`} color="#7C3AED" sub={`${num(d.ocupado_m3)} de ${num(d.capacidad_m3)} m³`} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Posiciones ocupadas" valor={d.ocupacion_posiciones_pct == null ? '—' : `${d.ocupacion_posiciones_pct}%`} color="#0369A1" sub={`${d.ubicaciones_ocupadas} de ${d.ubicaciones}`} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Unidades sin volumen" valor={num(d.unidades_sin_volumen)} color="#D97706" sub={`${d.ubicaciones_sin_medidas} ubicaciones sin medidas`} /></Grid>
      </Grid>}
      {d && (d.ubicaciones_sin_medidas > 0 || d.unidades_sin_volumen > 0 || d.huellas_sin_medidas > 0) && <Alert severity="warning" sx={{ mb: 2 }}>
        Los números son tan buenos como los datos: faltan medidas (frente y fondo) en ubicaciones o volumen en productos.
        Complételas en Configuración del WMS › Ubicaciones y en Cubicaje para que los m² y m³ sean reales.</Alert>}

      <Typography fontWeight={700} mb={1}>Metros cuadrados por zona</Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3, mb: 3 }}>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Zona</TableCell><TableCell>Tipo</TableCell><TableCell align="right">Área (m²)</TableCell>
            <TableCell align="right">Ocupada (m²)</TableCell><TableCell align="right">Libre (m²)</TableCell><TableCell>Ocupación</TableCell>
            <TableCell align="right">Huellas sin medidas</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {zonas.map(z => (
              <TableRow key={z.zona} hover>
                <TableCell sx={{ fontWeight: 600 }}>{z.zona}</TableCell>
                <TableCell><Chip size="small" label={z.tipo} variant="outlined" sx={{ fontSize: 11 }} /></TableCell>
                <TableCell align="right">{num(z.area_m2)}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{num(z.ocupada_m2)}</TableCell>
                <TableCell align="right">{num(z.libre_m2)}</TableCell>
                <TableCell><Barra pct={z.ocupacion_pct} /></TableCell>
                <TableCell align="right">{z.huellas_sin_medidas ? <Chip size="small" color="warning" label={z.huellas_sin_medidas} /> : ''}</TableCell>
              </TableRow>
            ))}
            {!zonas.length && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>Sin zonas</TableCell></TableRow>}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography fontWeight={700} mb={1}>Detalle por ubicación</Typography>
      <TablaRegistros filas={filas} cargando={ocu.isLoading} vacio="Sin ubicaciones" etiqueta={u => u.codigo}
        columnas={[
          { titulo: 'Ubicación', valor: u => <Typography fontFamily="monospace" fontWeight={700}>{u.codigo}</Typography> },
          { titulo: 'Zona', valor: u => u.zona }, { titulo: 'Medidas', valor: u => dims(u.largo_cm, u.ancho_cm, u.alto_cm) },
          { titulo: 'Piso', valor: u => (u as any).area_m2 ? `${num((u as any).area_m2)} m²` : '—', alinear: 'right' },
          { titulo: 'Capacidad', valor: u => u.capacidad_m3 ? `${num(u.capacidad_m3)} m³` : 'sin medidas', alinear: 'right' },
          { titulo: 'Ocupado', valor: u => `${num(u.ocupado_m3)} m³`, alinear: 'right' },
          { titulo: 'Ocupación', valor: u => <Barra pct={u.ocupacion_pct} /> },
          { titulo: 'SKU', valor: u => u.skus, alinear: 'right' },
          { titulo: 'Sin volumen', valor: u => u.unidades_sin_volumen ? <Chip size="small" color="warning" label={num(u.unidades_sin_volumen)} /> : '', alinear: 'right' },
        ]} />
    </>
  )
}
