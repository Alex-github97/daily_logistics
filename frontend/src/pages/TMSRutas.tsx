import React, { useState, useMemo } from 'react'
import {
  Box, Card, CardContent, Typography, Stack, Chip, Button, InputAdornment, MenuItem, InputLabel, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Tabs, Tab, Paper, Grid2 as Grid, Divider, alpha, Tooltip, Alert, CircularProgress,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import {
  Search,
  Add,
  Edit,
  Close,
  Route,
  DirectionsCar,
  Speed,
  AttachMoney,
  Timeline,
  Delete,
  CheckCircle,
  Block,
  MapOutlined,
  TrendingUp,
  TrendingDown,
  AccessTime,
  LocalGasStation,
  Toll,
} from '@mui/icons-material'
import { Layout } from '@/components/layout/Layout'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import toast from 'react-hot-toast'

import { COLOR_MODULO } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'
const TMS_COLOR = COLOR_MODULO

// ─── Interfaces (alineadas con backend /tms/rutas) ────────────────────────────

type TipoParadaRuta = 'ORIGEN' | 'PARADA_INTERMEDIA' | 'DESTINO' | 'CROSS_DOCK'

interface PuntoRuta {
  id?: number
  secuencia: number
  ciudad: string
  tipo: TipoParadaRuta
}

type TipoServicioRuta =
  | 'TERRESTRE_URBANO' | 'TERRESTRE_REGIONAL' | 'TERRESTRE_NACIONAL' | 'INTERNACIONAL'
  | 'DISTRIBUCION' | 'ULTIMA_MILLA' | 'PRIMERA_MILLA' | 'CROSS_DOCKING' | 'DEDICADO' | 'TERCERIZADO'

interface Ruta {
  id: number
  nombre: string
  codigo: string | null
  origen: string
  destino: string
  distanciaKm: number
  tiempoEstimadoMin: number
  tipoServicio: TipoServicioRuta
  costoReferencia: number
  estado: 'ACTIVA' | 'INACTIVA'
  puntosRuta: PuntoRuta[]
}

const TIPO_SERVICIO_OPTS: { value: TipoServicioRuta; label: string }[] = [
  { value: 'TERRESTRE_URBANO', label: 'Terrestre urbano' },
  { value: 'TERRESTRE_REGIONAL', label: 'Terrestre regional' },
  { value: 'TERRESTRE_NACIONAL', label: 'Terrestre nacional' },
  { value: 'INTERNACIONAL', label: 'Internacional' },
  { value: 'DISTRIBUCION', label: 'Distribución' },
  { value: 'ULTIMA_MILLA', label: 'Última milla' },
  { value: 'PRIMERA_MILLA', label: 'Primera milla' },
  { value: 'CROSS_DOCKING', label: 'Cross Docking' },
  { value: 'DEDICADO', label: 'Dedicado' },
  { value: 'TERCERIZADO', label: 'Tercerizado' },
]
const tipoServicioLabel = (v: TipoServicioRuta) => TIPO_SERVICIO_OPTS.find((o) => o.value === v)?.label || v

function rutaFromApi(r: any): Ruta {
  return {
    id: r.id,
    nombre: r.nombre,
    codigo: r.codigo,
    origen: r.origen,
    destino: r.destino,
    distanciaKm: r.distancia_km ?? 0,
    tiempoEstimadoMin: r.tiempo_estimado_min ?? 0,
    tipoServicio: (r.tipo_servicio ?? 'TERRESTRE_NACIONAL') as TipoServicioRuta,
    costoReferencia: r.costo_referencia ?? 0,
    estado: r.activo ? 'ACTIVA' : 'INACTIVA',
    puntosRuta: [],
  }
}

function puntoFromApi(p: any): PuntoRuta {
  return { id: p.id, secuencia: p.secuencia, ciudad: p.ciudad, tipo: p.tipo ?? 'PARADA_INTERMEDIA' }
}

interface AlternativaRuta {
  nombre: string
  distanciaKm: number
  tiempoMin: number
  costoTotal: number
  descripcion: string
}

interface ResultadoOptimizacion {
  distanciaTotal: number
  tiempoEstimadoMin: number
  costoCombustible: number
  peajes: number
  costoTotal: number
  alternativas: AlternativaRuta[]
}

interface RutaAnalisis {
  ruta: string
  nViajes: number
  otifRate: number
  costoPromKm: number
  tiempoPromMin: number
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatMinutes(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  return m === 0 ? `${h}h` : `${h}h ${m}m`
}

function formatCOP(value: number): string {
  return `$${value.toLocaleString('es-CO')}`
}

const TIPO_SERVICIO_COLOR: Record<TipoServicioRuta, string> = {
  TERRESTRE_URBANO: '#1565C0',
  TERRESTRE_REGIONAL: '#1565C0',
  TERRESTRE_NACIONAL: '#1565C0',
  INTERNACIONAL: '#4A148C',
  DISTRIBUCION: '#006064',
  ULTIMA_MILLA: '#E65100',
  PRIMERA_MILLA: '#E65100',
  CROSS_DOCKING: '#00695C',
  DEDICADO: '#B71C1C',
  TERCERIZADO: '#6B7280',
}

function getTipoServicioChip(tipo: Ruta['tipoServicio']) {
  const color = TIPO_SERVICIO_COLOR[tipo] ?? '#64748B'
  return (
    <Chip
      label={tipoServicioLabel(tipo)}
      size="small"
      sx={{ fontWeight: 600, fontSize: 11, color, bgcolor: alpha(color, 0.1), border: 'none' }}
    />
  )
}

function getEstadoChip(estado: Ruta['estado']) {
  return estado === 'ACTIVA' ? (
    <Chip
      label="Activa"
      size="small"
      sx={{ fontWeight: 600, fontSize: 11, color: '#166534', bgcolor: alpha('#22C55E', 0.12) }}
    />
  ) : (
    <Chip
      label="Inactiva"
      size="small"
      sx={{ fontWeight: 600, fontSize: 11, color: '#6B7280', bgcolor: alpha('#9CA3AF', 0.15) }}
    />
  )
}

// ─── Dialog Nueva/Editar Ruta ─────────────────────────────────────────────────

interface RutaDialogProps {
  open: boolean
  ruta: Ruta | null
  onClose: () => void
  onSave: (ruta: Ruta) => void
  saving?: boolean
}

function RutaDialog({ open, ruta, onClose, onSave, saving }: RutaDialogProps) {
  const isEdit = ruta !== null

  const emptyForm = {
    nombre: '',
    codigo: '',
    origen: '',
    destino: '',
    distanciaKm: '' as string | number,
    tiempoEstimadoMin: '' as string | number,
    tipoServicio: 'CARGA_GENERAL' as Ruta['tipoServicio'],
    costoReferencia: '' as string | number,
  }

  const [form, setForm] = useState(
    ruta
      ? {
          nombre: ruta.nombre,
          codigo: ruta.codigo,
          origen: ruta.origen,
          destino: ruta.destino,
          distanciaKm: ruta.distanciaKm,
          tiempoEstimadoMin: ruta.tiempoEstimadoMin,
          tipoServicio: ruta.tipoServicio,
          costoReferencia: ruta.costoReferencia,
        }
      : emptyForm,
  )

  const [puntos, setPuntos] = useState<PuntoRuta[]>(
    ruta ? [...ruta.puntosRuta] : [],
  )

  React.useEffect(() => {
    if (open) {
      setForm(
        ruta
          ? {
              nombre: ruta.nombre,
              codigo: ruta.codigo,
              origen: ruta.origen,
              destino: ruta.destino,
              distanciaKm: ruta.distanciaKm,
              tiempoEstimadoMin: ruta.tiempoEstimadoMin,
              tipoServicio: ruta.tipoServicio,
              costoReferencia: ruta.costoReferencia,
            }
          : emptyForm,
      )
      setPuntos(ruta ? [...ruta.puntosRuta] : [])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, ruta])

  const handleChange = (field: string, value: string | number) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  const handleAddPunto = () => {
    setPuntos(prev => [
      ...prev,
      { secuencia: prev.length + 1, ciudad: '', tipo: 'PARADA_INTERMEDIA' },
    ])
  }

  const handleDeletePunto = (idx: number) => {
    setPuntos(prev => {
      const updated = prev.filter((_, i) => i !== idx)
      return updated.map((p, i) => ({ ...p, secuencia: i + 1 }))
    })
  }

  const handlePuntoChange = (idx: number, field: keyof PuntoRuta, value: string | number) => {
    setPuntos(prev =>
      prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p)),
    )
  }

  const handleSave = () => {
    if (!form.nombre || !form.codigo || !form.origen || !form.destino) {
      toast.error('Complete los campos obligatorios')
      return
    }
    const saved: Ruta = {
      id: ruta?.id ?? Date.now(),
      nombre: form.nombre,
      codigo: form.codigo,
      origen: form.origen,
      destino: form.destino,
      distanciaKm: Number(form.distanciaKm) || 0,
      tiempoEstimadoMin: Number(form.tiempoEstimadoMin) || 0,
      tipoServicio: form.tipoServicio,
      costoReferencia: Number(form.costoReferencia) || 0,
      estado: ruta?.estado ?? 'ACTIVA',
      puntosRuta: puntos,
    }
    onSave(saved)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Typography variant="h6" fontWeight={700}>
          {isEdit ? 'Editar Ruta' : 'Nueva Ruta'}
        </Typography>
        <IconButton onClick={onClose} size="small">
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers sx={{ pt: 2 }}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              label="Nombre *"
              fullWidth
              size="small"
              value={form.nombre}
              onChange={e => handleChange('nombre', e.target.value)}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              label="Código *"
              fullWidth
              size="small"
              value={form.codigo}
              onChange={e => handleChange('codigo', e.target.value)}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              label="Origen *"
              fullWidth
              size="small"
              value={form.origen}
              onChange={e => handleChange('origen', e.target.value)}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              label="Destino *"
              fullWidth
              size="small"
              value={form.destino}
              onChange={e => handleChange('destino', e.target.value)}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              label="Distancia (km) *"
              fullWidth
              size="small"
              type="number"
              value={form.distanciaKm}
              onChange={e => handleChange('distanciaKm', e.target.value)}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              label="Tiempo Estimado (min) *"
              fullWidth
              size="small"
              type="number"
              value={form.tiempoEstimadoMin}
              onChange={e => handleChange('tiempoEstimadoMin', e.target.value)}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Tipo Servicio *</InputLabel>
              <Select
                label="Tipo Servicio *"
                value={form.tipoServicio}
                onChange={e => handleChange('tipoServicio', e.target.value)}
              >
                {TIPO_SERVICIO_OPTS.map(o => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              label="Costo Referencia (COP) *"
              fullWidth
              size="small"
              type="number"
              value={form.costoReferencia}
              onChange={e => handleChange('costoReferencia', e.target.value)}
            />
          </Grid>
        </Grid>

        <Divider sx={{ my: 3 }} />

        <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2}>
          <Typography variant="subtitle1" fontWeight={700}>
            Puntos de Ruta
          </Typography>
          <Button
            startIcon={<Add />}
            size="small"
            variant="outlined"
            onClick={handleAddPunto}
            sx={{ borderColor: TMS_COLOR, color: TMS_COLOR }}
          >
            Agregar Punto
          </Button>
        </Stack>

        {puntos.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
            Sin puntos de ruta definidos
          </Typography>
        ) : (
          <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: alpha(TMS_COLOR, 0.06) }}>
                  <TableCell sx={{ fontWeight: 700, width: 50 }}>#</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Ciudad</TableCell>
                  <TableCell sx={{ fontWeight: 700, width: 160 }}>Tipo</TableCell>
                  <TableCell sx={{ fontWeight: 700, width: 60 }}>Eliminar</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {puntos.map((punto, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{punto.secuencia}</TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        value={punto.ciudad}
                        onChange={e => handlePuntoChange(idx, 'ciudad', e.target.value)}
                        placeholder="Nombre ciudad"
                        sx={{ '& .MuiInputBase-input': { py: 0.5 } }}
                      />
                    </TableCell>
                    <TableCell>
                      <FormControl fullWidth size="small">
                        <Select
                          value={punto.tipo}
                          onChange={e => handlePuntoChange(idx, 'tipo', e.target.value)}
                          sx={{ '& .MuiSelect-select': { py: 0.5 } }}
                        >
                          <MenuItem value="ORIGEN">Origen</MenuItem>
                          <MenuItem value="PARADA">Parada</MenuItem>
                          <MenuItem value="DESTINO">Destino</MenuItem>
                        </Select>
                      </FormControl>
                    </TableCell>
                    <TableCell>
                      <IconButton size="small" color="error" onClick={() => handleDeletePunto(idx)}>
                        <Delete fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} color="inherit" disabled={saving}>
          Cancelar
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving}
          sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#025E91' } }}
        >
          {saving ? 'Guardando...' : isEdit ? 'Guardar Cambios' : 'Crear Ruta'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Tab 1: Rutas Registradas ─────────────────────────────────────────────────

interface Tab1Props {
  rutas: Ruta[]
  onEdit: (ruta: Ruta) => void
  onToggleEstado: (id: number) => void
  onNew: () => void
  onVerDetalle: (ruta: Ruta) => void
}

function TabRutasRegistradas({ rutas, onEdit, onToggleEstado, onNew, onVerDetalle }: Tab1Props) {
  const [search, setSearch] = useState('')
  const [estadoFilter, setEstadoFilter] = useState<'TODAS' | 'ACTIVA' | 'INACTIVA'>('TODAS')

  const filtered = useMemo(() => {
    return rutas.filter(r => {
      const matchSearch =
        search === '' ||
        r.nombre.toLowerCase().includes(search.toLowerCase()) ||
        r.origen.toLowerCase().includes(search.toLowerCase()) ||
        r.destino.toLowerCase().includes(search.toLowerCase()) ||
        (r.codigo ?? '').toLowerCase().includes(search.toLowerCase())
      const matchEstado = estadoFilter === 'TODAS' || r.estado === estadoFilter
      return matchSearch && matchEstado
    })
  }, [rutas, search, estadoFilter])

  return (
    <Box>
      {/* Toolbar */}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} mb={3} flexWrap="wrap">
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={onNew}
          sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#025E91' }, fontWeight: 700, whiteSpace: 'nowrap' }}
        >
          + Nueva Ruta
        </Button>
        <TextField
          size="small"
          placeholder="Buscar por nombre, origen o destino..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 220 }}
        />
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Estado</InputLabel>
          <Select
            label="Estado"
            value={estadoFilter}
            onChange={e => setEstadoFilter(e.target.value as typeof estadoFilter)}
          >
            <MenuItem value="TODAS">Todas</MenuItem>
            <MenuItem value="ACTIVA">Activa</MenuItem>
            <MenuItem value="INACTIVA">Inactiva</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
          {filtered.length} resultado{filtered.length !== 1 ? 's' : ''}
        </Typography>
      </Stack>

      <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: alpha(TMS_COLOR, 0.07) }}>
              <TableCell sx={{ fontWeight: 700 }}>Nombre</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Código</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Origen → Destino</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">Distancia</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Tiempo Est.</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Tipo Servicio</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">Costo Ref.</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Estado</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="center">Acciones</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  No se encontraron rutas
                </TableCell>
              </TableRow>
            ) : (
              filtered.map(ruta => (
                <TableRow key={ruta.id} hover onClick={() => onVerDetalle(ruta)} sx={{ cursor: 'pointer' }}>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>
                      {ruta.nombre}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', color: TMS_COLOR, fontWeight: 600 }}>
                      {ruta.codigo}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" alignItems="center" spacing={0.5}>
                      <Typography variant="body2">{ruta.origen}</Typography>
                      <Typography variant="body2" color="text.secondary">→</Typography>
                      <Typography variant="body2">{ruta.destino}</Typography>
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2">{ruta.distanciaKm.toLocaleString('es-CO')} km</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{formatMinutes(ruta.tiempoEstimadoMin)}</Typography>
                  </TableCell>
                  <TableCell>{getTipoServicioChip(ruta.tipoServicio)}</TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" fontWeight={600}>
                      {formatCOP(ruta.costoReferencia)}
                    </Typography>
                  </TableCell>
                  <TableCell>{getEstadoChip(ruta.estado)}</TableCell>
                  <TableCell align="center">
                    <Stack direction="row" spacing={0.5} justifyContent="center">
                      <Tooltip title="Editar">
                        <IconButton size="small" onClick={() => onEdit(ruta)} sx={{ color: TMS_COLOR }}>
                          <Edit fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={ruta.estado === 'ACTIVA' ? 'Desactivar' : 'Activar'}>
                        <IconButton
                          size="small"
                          onClick={() => onToggleEstado(ruta.id)}
                          sx={{ color: ruta.estado === 'ACTIVA' ? '#EF4444' : '#22C55E' }}
                        >
                          {ruta.estado === 'ACTIVA' ? (
                            <Block fontSize="small" />
                          ) : (
                            <CheckCircle fontSize="small" />
                          )}
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}

// ─── Tab 2: Estimador de ruta ────────────────────────────────────────────────
// Antes «optimizaba» con una distancia al azar entre 400 y 1.100 km y tres
// alternativas fijas: cada clic daba otro resultado. Ahora reúne lo que la
// empresa ya sabe de ese corredor —rutas del catálogo y viajes hechos— y si
// no sabe nada lo dice. No traza el recorrido: eso requiere un motor de mapas.

interface EstimacionRuta {
  origen: string; destino: string
  rutas: { id: number; nombre: string; codigo?: string | null; origen: string; destino: string
    distancia_km?: number | null; tiempo_estimado_min?: number | null; costo_referencia?: number | null }[]
  historico: { viajes: number; distancia_km: number | null; horas_reales: number | null; viajes_con_tiempo: number
    costo_por_km: number | null; viajes_con_costo: number }
  costo_por_km_flota: number | null
}

function TabOptimizador() {
  const [origen, setOrigen] = useState('')
  const [destino, setDestino] = useState('')
  const [consulta, setConsulta] = useState<{ origen: string; destino: string } | null>(null)
  const { data: est, isFetching } = useQuery<EstimacionRuta>({
    queryKey: ['tms-rutas-estimar', consulta],
    queryFn: () => apiClient.get('/tms/rutas-estimar', { params: consulta }).then(r => r.data),
    enabled: !!consulta,
  })

  const estimar = () => {
    if (origen.trim().length < 2 || destino.trim().length < 2) { toast.error('Ingrese origen y destino'); return }
    setConsulta({ origen: origen.trim(), destino: destino.trim() })
  }
  // El costo por km que se usa: el del corredor si hay viajes con costos; si
  // no, el de toda la flota. Se dice cuál se usó.
  const costoKm = est?.historico.costo_por_km ?? est?.costo_por_km_flota ?? null
  const fuenteCosto = est?.historico.costo_por_km != null
    ? `promedio de ${est.historico.viajes_con_costo} viaje(s) en este corredor`
    : est?.costo_por_km_flota != null ? 'promedio de toda la flota (este corredor no tiene viajes con costos)' : null
  const distancia = est?.historico.distancia_km ?? est?.rutas.find(r => r.distancia_km)?.distancia_km ?? null
  const sinDatos = est && !est.rutas.length && !est.historico.viajes

  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 5 }}>
        <Paper variant="outlined" sx={{ borderRadius: 2, p: 3 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} mb={3}>
            <Box sx={{ p: 1, bgcolor: alpha(TMS_COLOR, 0.1), borderRadius: 1.5, display: 'flex' }}>
              <MapOutlined sx={{ color: TMS_COLOR, fontSize: 22 }} />
            </Box>
            <Typography variant="h6" fontWeight={700}>Estimador de ruta</Typography>
          </Stack>
          <Stack spacing={2.5}>
            <TextField label="Ciudad de origen" size="small" fullWidth value={origen} onChange={e => setOrigen(e.target.value)} />
            <TextField label="Ciudad de destino" size="small" fullWidth value={destino} onChange={e => setDestino(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') estimar() }} />
            <Button variant="contained" onClick={estimar} disabled={isFetching} sx={{ bgcolor: TMS_COLOR }}>
              {isFetching ? 'Consultando…' : 'Estimar'}
            </Button>
            <Typography fontSize={12} color="text.secondary">
              Se estima con las rutas del catálogo y los viajes ya hechos entre esas ciudades.
            </Typography>
          </Stack>
        </Paper>
      </Grid>

      <Grid size={{ xs: 12, md: 7 }}>
        {!est ? (
          <Paper variant="outlined" sx={{ borderRadius: 2, p: 4, textAlign: 'center' }}>
            <Typography color="text.secondary">Escribe origen y destino para ver lo que se sabe de ese corredor.</Typography>
          </Paper>
        ) : sinDatos ? (
          <Alert severity="info">
            No hay rutas en el catálogo ni viajes registrados entre «{est.origen}» y «{est.destino}».
            Registra la ruta en la pestaña «Rutas registradas» con su distancia y tiempo, o espera a que se hagan viajes en ese corredor.
          </Alert>
        ) : (
          <Stack spacing={2}>
            <Grid container spacing={2}>
              {[
                ['Distancia', distancia != null ? `${distancia.toLocaleString('es-CO')} km` : '—',
                  est.historico.distancia_km != null ? `promedio de ${est.historico.viajes} viaje(s)` : distancia != null ? 'según el catálogo' : 'sin dato'],
                ['Duración real', est.historico.horas_reales != null ? formatMinutes(Math.round(est.historico.horas_reales * 60)) : '—',
                  est.historico.viajes_con_tiempo ? `cargue a entrega, ${est.historico.viajes_con_tiempo} viaje(s)` : 'sin viajes con tiempos'],
                ['Costo estimado', costoKm != null && distancia != null ? formatCOP(costoKm * distancia) : '—',
                  costoKm != null ? `${formatCOP(costoKm)}/km · ${fuenteCosto}` : 'sin viajes con costos'],
              ].map(([t, v, s]) => (
                <Grid key={t} size={{ xs: 12, sm: 4 }}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: '100%' }}>
                    <Typography fontSize={12} color="text.secondary">{t}</Typography>
                    <Typography variant="h6" fontWeight={800} color={TMS_COLOR}>{v}</Typography>
                    <Typography fontSize={11} color="text.secondary">{s}</Typography>
                  </Paper>
                </Grid>
              ))}
            </Grid>
            <Paper variant="outlined" sx={{ borderRadius: 2 }}>
              <Typography fontWeight={700} sx={{ p: 2, pb: 1 }}>Rutas del catálogo para este corredor ({est.rutas.length})</Typography>
              {est.rutas.length === 0 ? (
                <Typography fontSize={13} color="text.secondary" sx={{ px: 2, pb: 2 }}>Ninguna ruta registrada coincide con estas ciudades.</Typography>
              ) : (
                <Table size="small">
                  <TableHead><TableRow><TableCell><b>Ruta</b></TableCell><TableCell align="right"><b>Distancia</b></TableCell>
                    <TableCell align="right"><b>Tiempo</b></TableCell><TableCell align="right"><b>Costo estimado</b></TableCell></TableRow></TableHead>
                  <TableBody>
                    {est.rutas.map((r, i) => (
                      <TableRow key={r.id} sx={i === 0 ? { bgcolor: alpha(TMS_COLOR, 0.05) } : undefined}>
                        <TableCell><Typography fontSize={13} fontWeight={i === 0 ? 700 : 400}>{r.codigo ? `${r.codigo} · ` : ''}{r.nombre}</Typography>
                          {i === 0 && r.distancia_km != null && <Typography fontSize={11} color="text.secondary">La más corta del catálogo</Typography>}</TableCell>
                        <TableCell align="right">{r.distancia_km != null ? `${r.distancia_km} km` : '—'}</TableCell>
                        <TableCell align="right">{r.tiempo_estimado_min != null ? formatMinutes(r.tiempo_estimado_min) : '—'}</TableCell>
                        <TableCell align="right">{r.costo_referencia != null ? formatCOP(r.costo_referencia)
                          : costoKm != null && r.distancia_km != null ? formatCOP(costoKm * r.distancia_km) : '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Paper>
          </Stack>
        )}
      </Grid>
    </Grid>
  )
}

// ─── Tab 3: Análisis ──────────────────────────────────────────────────────────
// Antes: ocho rutas con OTIF, costo y tiempo escritos a mano. Ahora: cada
// corredor con viajes entregados, calculado por el servidor.

interface CorredorAnalisis {
  origen: string; destino: string; viajes: number
  on_time_rate: number | null; otif_rate: number | null
  costo_por_km: number | null; horas_promedio: number | null
}

function TabAnalisis({ totalActivas, totalRutas }: { totalActivas: number; totalRutas: number }) {
  const { data: corredores = [], isLoading } = useQuery<CorredorAnalisis[]>({
    queryKey: ['tms-rutas-analisis'],
    queryFn: () => apiClient.get('/tms/rutas-analisis').then(r => r.data),
  })
  const conOtif = corredores.filter(c => c.otif_rate != null)
  const orden = [...conOtif].sort((a, b) => b.otif_rate! - a.otif_rate!)
  const totalViajes = corredores.reduce((s, c) => s + c.viajes, 0)
  // OTIF global ponderado por viajes, no promedio simple de corredores.
  const otifGlobal = conOtif.length
    ? conOtif.reduce((s, c) => s + c.otif_rate! * c.viajes, 0) / conOtif.reduce((s, c) => s + c.viajes, 0)
    : null
  const nombre = (c: CorredorAnalisis) => `${c.origen} → ${c.destino}`

  const Tabla = ({ data, color }: { data: CorredorAnalisis[]; color: string }) => (
    <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
      <Table size="small">
        <TableHead>
          <TableRow sx={{ bgcolor: alpha(color, 0.12) }}>
            <TableCell sx={{ fontWeight: 700 }}>Corredor</TableCell>
            <TableCell sx={{ fontWeight: 700 }} align="right">Viajes</TableCell>
            <TableCell sx={{ fontWeight: 700 }} align="right">OTIF</TableCell>
            <TableCell sx={{ fontWeight: 700 }} align="right">A tiempo</TableCell>
            <TableCell sx={{ fontWeight: 700 }} align="right">Costo/km</TableCell>
            <TableCell sx={{ fontWeight: 700 }} align="right">Duración prom.</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.length === 0 && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 2, color: 'text.secondary' }}>Sin datos</TableCell></TableRow>}
          {data.map(c => (
            <TableRow key={nombre(c)}>
              <TableCell>{nombre(c)}</TableCell>
              <TableCell align="right">{c.viajes}</TableCell>
              <TableCell align="right"><b>{c.otif_rate != null ? `${c.otif_rate.toFixed(1)}%` : '—'}</b></TableCell>
              <TableCell align="right">{c.on_time_rate != null ? `${c.on_time_rate.toFixed(1)}%` : '—'}</TableCell>
              <TableCell align="right">{c.costo_por_km != null ? formatCOP(c.costo_por_km) : '—'}</TableCell>
              <TableCell align="right">{c.horas_promedio != null ? formatMinutes(Math.round(c.horas_promedio * 60)) : '—'}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )

  return (
    <Stack spacing={3}>
      <Grid container spacing={2}>
        {[
          ['Rutas activas en catálogo', `${totalActivas} de ${totalRutas}`],
          ['Corredores con viajes', String(corredores.length)],
          ['Viajes entregados', String(totalViajes)],
          ['OTIF global', otifGlobal != null ? `${otifGlobal.toFixed(1)}%` : '—'],
        ].map(([t, v]) => (
          <Grid key={t} size={{ xs: 6, md: 3 }}>
            <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
              <Typography fontSize={12} color="text.secondary">{t}</Typography>
              <Typography variant="h6" fontWeight={800} color={TMS_COLOR}>{v}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>
      {isLoading ? <Box textAlign="center" py={3}><CircularProgress size={24} /></Box> : corredores.length === 0 ? (
        <Alert severity="info">El análisis aparece cuando hay viajes entregados con origen y destino.</Alert>
      ) : (<>
        {conOtif.length > 0 && (
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}><Typography fontWeight={700} mb={1}>Mejor OTIF</Typography><Tabla data={orden.slice(0, 3)} color="#22C55E" /></Grid>
            <Grid size={{ xs: 12, md: 6 }}><Typography fontWeight={700} mb={1}>OTIF más bajo</Typography><Tabla data={[...orden].reverse().slice(0, 3)} color="#F97316" /></Grid>
          </Grid>
        )}
        <Box><Typography fontWeight={700} mb={1}>Todos los corredores</Typography><Tabla data={corredores} color={TMS_COLOR} /></Box>
      </>)}
    </Stack>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function TMSRutas() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingRuta, setEditingRuta] = useState<Ruta | null>(null)
  const [verRuta, setVerRuta] = useState<Ruta | null>(null)
  const [saving, setSaving] = useState(false)

  const { data: rutasApi = [], isLoading } = useQuery<any[]>({
    queryKey: ['tms-rutas'],
    queryFn: () => apiClient.get('/tms/rutas').then(r => r.data),
  })
  const rutas = useMemo(() => rutasApi.map(rutaFromApi), [rutasApi])

  const { data: puntosVer = [] } = useQuery<PuntoRuta[]>({
    queryKey: ['tms-ruta-puntos', verRuta?.id],
    queryFn: () => apiClient.get(`/tms/rutas/${verRuta!.id}/puntos`).then(r => r.data.map(puntoFromApi)),
    enabled: !!verRuta,
  })

  const toggleEstadoMutation = useMutation({
    mutationFn: ({ id, activo }: { id: number; activo: boolean }) =>
      apiClient.put(`/tms/rutas/${id}`, { activo }),
    onSuccess: () => {
      toast.success('Estado de la ruta actualizado')
      qc.invalidateQueries({ queryKey: ['tms-rutas'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al actualizar el estado de la ruta')),
  })

  const handleNew = () => {
    setEditingRuta(null)
    setDialogOpen(true)
  }

  const handleEdit = (ruta: Ruta) => {
    setEditingRuta(ruta)
    setDialogOpen(true)
  }

  const handleToggleEstado = (id: number) => {
    const ruta = rutas.find(r => r.id === id)
    if (!ruta) return
    toggleEstadoMutation.mutate({ id, activo: ruta.estado !== 'ACTIVA' })
  }

  const persistirPuntos = async (rutaId: number, puntos: PuntoRuta[]) => {
    await apiClient.delete(`/tms/rutas/${rutaId}/puntos`)
    for (const p of puntos) {
      await apiClient.post(`/tms/rutas/${rutaId}/puntos`, {
        ruta_id: rutaId,
        secuencia: p.secuencia,
        ciudad: p.ciudad,
        tipo: p.tipo,
      })
    }
  }

  const handleSave = async (saved: Ruta) => {
    setSaving(true)
    try {
      const payload = {
        nombre: saved.nombre,
        codigo: saved.codigo || undefined,
        origen: saved.origen,
        destino: saved.destino,
        distancia_km: saved.distanciaKm,
        tiempo_estimado_min: saved.tiempoEstimadoMin,
        tipo_servicio: saved.tipoServicio,
        costo_referencia: saved.costoReferencia,
      }
      let rutaId = editingRuta?.id
      if (editingRuta) {
        await apiClient.put(`/tms/rutas/${editingRuta.id}`, payload)
        toast.success(`Ruta ${saved.codigo ?? ''} actualizada`)
      } else {
        const resp = await apiClient.post('/tms/rutas', payload)
        rutaId = resp.data.id
        toast.success(`Ruta ${resp.data.codigo ?? ''} creada exitosamente`)
      }
      if (rutaId) await persistirPuntos(rutaId, saved.puntosRuta)
      qc.invalidateQueries({ queryKey: ['tms-rutas'] })
      qc.invalidateQueries({ queryKey: ['tms-ruta-puntos', rutaId] })
      setDialogOpen(false)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Error al guardar la ruta')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Layout>
      <Box sx={{ p: 3 }}>
        {/* Page Header */}
        <Stack direction="row" alignItems="center" spacing={2} mb={3}>
          <Box
            sx={{
              p: 1.5,
              bgcolor: alpha(TMS_COLOR, 0.1),
              borderRadius: 2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Route sx={{ color: TMS_COLOR, fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h5" fontWeight={800} color="text.primary">
              Gestión de Rutas
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Administración y optimización de rutas de transporte
            </Typography>
          </Box>
        </Stack>

        {/* KPI Cards */}
        <Grid container spacing={2} mb={3}>
          {[
            {
              label: 'Rutas Activas',
              value: rutas.filter(r => r.estado === 'ACTIVA').length,
              suffix: '',
              icon: <CheckCircle sx={{ fontSize: 24, color: '#16A34A' }} />,
              bg: alpha('#22C55E', 0.08),
              borderColor: alpha('#22C55E', 0.2),
            },
            {
              label: 'Total Rutas',
              value: rutas.length,
              suffix: '',
              icon: <Route sx={{ fontSize: 24, color: TMS_COLOR }} />,
              bg: alpha(TMS_COLOR, 0.08),
              borderColor: alpha(TMS_COLOR, 0.2),
            },
            {
              label: 'Km Promedio',
              value: rutas.length ? Math.round(rutas.reduce((s, r) => s + r.distanciaKm, 0) / rutas.length) : 0,
              suffix: ' km',
              icon: <Speed sx={{ fontSize: 24, color: '#7C3AED' }} />,
              bg: alpha('#7C3AED', 0.08),
              borderColor: alpha('#7C3AED', 0.2),
            },
            {
              label: 'Costo Prom. Referencia',
              value: rutas.length ? Math.round(rutas.reduce((s, r) => s + r.costoReferencia, 0) / rutas.length) : 0,
              suffix: '',
              prefix: '$',
              icon: <AttachMoney sx={{ fontSize: 24, color: '#D97706' }} />,
              bg: alpha('#D97706', 0.08),
              borderColor: alpha('#D97706', 0.2),
            },
          ].map(kpi => (
            <Grid key={kpi.label} size={{ xs: 6, md: 3 }}>
              <Paper
                variant="outlined"
                sx={{
                  borderRadius: 2,
                  p: 2,
                  bgcolor: kpi.bg,
                  borderColor: kpi.borderColor,
                }}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {kpi.label}
                    </Typography>
                    <Typography variant="h5" fontWeight={800} mt={0.5}>
                      {kpi.prefix ?? ''}{typeof kpi.value === 'number' && kpi.prefix === '$'
                        ? kpi.value.toLocaleString('es-CO')
                        : kpi.value}{kpi.suffix}
                    </Typography>
                  </Box>
                  <Box sx={{ p: 1, bgcolor: 'white', borderRadius: 1.5, boxShadow: 1 }}>
                    {kpi.icon}
                  </Box>
                </Stack>
              </Paper>
            </Grid>
          ))}
        </Grid>

        {/* Tabs */}
        <Paper variant="outlined" sx={{ borderRadius: 2 }}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{
              borderBottom: '1px solid',
              borderColor: 'divider',
              px: 2,
              '& .MuiTab-root': { fontWeight: 600, textTransform: 'none', fontSize: 14 },
              '& .Mui-selected': { color: TMS_COLOR },
              '& .MuiTabs-indicator': { bgcolor: TMS_COLOR },
            }}
          >
            <Tab label="Rutas Registradas" icon={<Route />} iconPosition="start" />
            <Tab label="Estimador" icon={<MapOutlined />} iconPosition="start" />
            <Tab label="Análisis" icon={<Timeline />} iconPosition="start" />
          </Tabs>

          <Box sx={{ p: 3 }}>
            {tab === 0 && (
              <TabRutasRegistradas
                rutas={rutas}
                onEdit={handleEdit}
                onToggleEstado={handleToggleEstado}
                onNew={handleNew}
                onVerDetalle={setVerRuta}
              />
            )}
            {tab === 1 && <TabOptimizador />}
            {tab === 2 && (
              <TabAnalisis
                totalActivas={rutas.filter(r => r.estado === 'ACTIVA').length}
                totalRutas={rutas.length}
              />
            )}
          </Box>
        </Paper>
      </Box>

      <RutaDialog
        open={dialogOpen}
        ruta={editingRuta}
        onClose={() => setDialogOpen(false)}
        onSave={handleSave}
        saving={saving}
      />

      <VerRutaDialog
        ruta={verRuta}
        puntos={puntosVer}
        open={!!verRuta}
        onClose={() => setVerRuta(null)}
        onEditar={() => { if (verRuta) { handleEdit(verRuta); setVerRuta(null) } }}
      />
    </Layout>
  )
}

// ─── Dialog: Ver Detalle de Ruta ───────────────────────────────────────────────

function VerRutaDialog({
  ruta,
  puntos,
  open,
  onClose,
  onEditar,
}: {
  ruta: Ruta | null
  puntos: PuntoRuta[]
  open: boolean
  onClose: () => void
  onEditar: () => void
}) {
  if (!ruta) return null

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Box>
          <Typography variant="h6" fontWeight={700}>{ruta.nombre}</Typography>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', color: TMS_COLOR, fontWeight: 600 }}>
            {ruta.codigo ?? 'Sin código'}
          </Typography>
        </Box>
        <IconButton onClick={onClose} size="small"><Close fontSize="small" /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction="row" spacing={1} mb={2.5}>
          {getEstadoChip(ruta.estado)}
          {getTipoServicioChip(ruta.tipoServicio)}
        </Stack>

        <Grid container spacing={2} mb={2.5}>
          {[
            { label: 'Origen', value: ruta.origen },
            { label: 'Destino', value: ruta.destino },
            { label: 'Distancia', value: `${ruta.distanciaKm.toLocaleString('es-CO')} km` },
            { label: 'Tiempo estimado', value: formatMinutes(ruta.tiempoEstimadoMin) },
            { label: 'Costo referencia', value: formatCOP(ruta.costoReferencia) },
          ].map((f) => (
            <Grid key={f.label} size={{ xs: 6 }}>
              <Typography variant="caption" sx={{ color: '#64748B', display: 'block' }}>{f.label}</Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{f.value}</Typography>
            </Grid>
          ))}
        </Grid>

        <Divider sx={{ my: 1.5 }} />
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Puntos de ruta</Typography>
        {puntos.length === 0 ? (
          <Typography variant="body2" sx={{ color: '#94A3B8', py: 1 }}>Sin puntos intermedios definidos</Typography>
        ) : (
          <Stack spacing={0.75}>
            {puntos.map((p, idx) => (
              <Stack key={p.id ?? idx} direction="row" alignItems="center" spacing={1}>
                <Chip label={p.secuencia} size="small" sx={{ minWidth: 28, fontWeight: 700 }} />
                <Typography variant="body2" sx={{ flex: 1 }}>{p.ciudad}</Typography>
                <Chip label={p.tipo.replace(/_/g, ' ')} size="small" variant="outlined" sx={{ fontSize: 10 }} />
              </Stack>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose}>Cerrar</Button>
        <Button variant="contained" startIcon={<Edit />} onClick={onEditar} sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#025E91' } }}>
          Editar Ruta
        </Button>
      </DialogActions>
    </Dialog>
  )
}
