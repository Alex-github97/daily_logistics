import { useState } from 'react'
import {
  Box, Typography, Table, TableHead, TableBody, TableRow, TableCell, Paper, Chip, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, Stack, ToggleButton, ToggleButtonGroup, Tooltip, InputAdornment, Alert,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Add as AddIcon, DirectionsCar, Search as SearchIcon, Download, Link as LinkIcon, Edit as EditIcon } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient as api } from '@/api/client'
import { exportarPDF, exportarExcel } from '@/utils/exportar'
import { EsquemaLlantasPreview } from '@/components/EsquemaLlantasPreview'

export interface VehiculoCombinado {
  origen: string; flota: string; id: number; activo_id?: number | null
  codigo?: string | null; nombre?: string | null; placa?: string; tipo?: string
  marca?: string; modelo?: string; anio?: number; numero_ejes?: number
  layout_llantas?: number[] | null; tiene_repuesto?: boolean | null
  capacidad_kg?: number; estado?: string; motor_marca?: string
  motor_linea?: string; motor_cc?: number; propietario?: string
}

interface TipoActivo { id: number; codigo: string; nombre: string; usa_llantas: boolean }
interface EsquemaVehiculo { id: number; nombre: string; tipo_activo?: string | null; numero_ejes: number; layout?: number[] | null; tiene_repuesto: boolean; cantidad_repuestos: number }

const EMPTY = {
  codigo: '', nombre: '', placa: '', tipo_activo: 'VEHICULO', marca: '', modelo: '',
  anio: '', esquema_id: '', motor_marca: '', motor_linea: '',
  motor_cc: '', responsable: '', sede: '',
}

/**
 * Tabla unificada de vehículos: flota PROPIA (activos del CMMS/EAM) + flota EXTERNA (TMS).
 * `color` adapta el acento al módulo host. Si `permitirCrear`, muestra el alta de flota propia (CMMS).
 */
export function VehiculosCombinados({
  color = '#1A1A1A', colorDark = '#1A1A1A', permitirCrear = false,
}: { color?: string; colorDark?: string; permitirCrear?: boolean }) {
  const qc = useQueryClient()
  const [flota, setFlota] = useState<'TODAS' | 'PROPIA' | 'EXTERNA'>('TODAS')
  const [search, setSearch] = useState('')
  const [nuevoOpen, setNuevoOpen] = useState(false)
  const [form, setForm] = useState({ ...EMPTY })
  const [layoutVeh, setLayoutVeh] = useState<VehiculoCombinado | null>(null)
  const [layoutEsquemaId, setLayoutEsquemaId] = useState('')

  const { data: vehiculos = [], isLoading } = useQuery<VehiculoCombinado[]>({
    queryKey: ['vehiculos-combinados'],
    queryFn: () => api.get('/eam/vehiculos-combinados').then(r => r.data),
  })
  const { data: tiposActivo = [] } = useQuery<TipoActivo[]>({
    queryKey: ['eam-tipos-activo'],
    queryFn: () => api.get('/eam/tipos-activo').then(r => r.data),
  })
  // Esquemas (categorías) de ejes/llantas — se pre-configuran una sola vez aquí
  // y luego cada vehículo simplemente se le asigna una; no se digitan números
  // vehículo por vehículo.
  const { data: esquemas = [] } = useQuery<EsquemaVehiculo[]>({
    queryKey: ['eam-esquemas'],
    queryFn: () => api.get('/eam/neumaticos/esquemas').then(r => r.data),
  })

  const mutAsignarEsquema = useMutation({
    mutationFn: ({ activo_id, esquema_id }: { activo_id: number; esquema_id: number }) =>
      api.post('/eam/neumaticos/esquemas/asignar', { activo_id, esquema_id, fecha_vigencia: new Date().toISOString().slice(0, 10) }),
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo asignar la categoría de ejes/llantas'),
  })

  const mutCrear = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post('/eam/activos', payload).then(r => r.data),
    onSuccess: async (activo) => {
      if (form.esquema_id) await mutAsignarEsquema.mutateAsync({ activo_id: activo.id, esquema_id: Number(form.esquema_id) })
      toast.success('Vehículo de flota propia registrado')
      qc.invalidateQueries({ queryKey: ['vehiculos-combinados'] })
      setNuevoOpen(false); setForm({ ...EMPTY })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo registrar'),
  })

  // Vincula un vehículo EXTERNO (TMS/Flota) al CMMS, o si ya está vinculado
  // simplemente abre el diálogo para asignarle una categoría de ejes/llantas.
  const mutVincular = useMutation({
    mutationFn: (v: VehiculoCombinado) => api.post('/eam/activos/vincular-externo', { origen: v.origen, origen_id: v.id }).then(r => r.data),
    onSuccess: (activo) => {
      qc.invalidateQueries({ queryKey: ['vehiculos-combinados'] })
      setLayoutVeh(prev => prev ? { ...prev, activo_id: activo.id } : prev)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo vincular al CMMS'),
  })

  const abrirLayout = (v: VehiculoCombinado) => {
    setLayoutVeh(v)
    setLayoutEsquemaId('')
  }

  const guardarLayout = () => {
    if (!layoutVeh?.activo_id || !layoutEsquemaId) return
    mutAsignarEsquema.mutate({ activo_id: layoutVeh.activo_id, esquema_id: Number(layoutEsquemaId) }, {
      onSuccess: () => {
        toast.success('Categoría de ejes/llantas asignada')
        qc.invalidateQueries({ queryKey: ['vehiculos-combinados'] })
        setLayoutVeh(null)
      },
    })
  }

  const filtered = vehiculos.filter(v => {
    if (flota !== 'TODAS' && v.flota !== flota) return false
    if (search.trim()) {
      const q = search.toLowerCase()
      return [v.placa, v.marca, v.modelo, v.tipo, v.propietario].some(x => (x ?? '').toLowerCase().includes(q))
    }
    return true
  })

  const columnas = [
    { key: 'flota', header: 'Flota' }, { key: 'placa', header: 'Placa' },
    { key: 'tipo', header: 'Tipo' }, { key: 'marca', header: 'Marca' },
    { key: 'modelo', header: 'Modelo' }, { key: 'anio', header: 'Año' },
    { key: 'numero_ejes', header: 'Ejes' }, { key: 'motor_marca', header: 'Motor' },
    { key: 'motor_cc', header: 'CC' }, { key: 'propietario', header: 'Responsable/Propietario' },
    { key: 'cmms', header: 'Config. llantas (CMMS)' },
  ]

  const exportar = (tipo: 'pdf' | 'excel') => {
    const opts = {
      archivo: 'flota-vehiculos', titulo: 'Flota de vehículos (propia + externa)',
      columnas, filas: filtered, color,
    }
    tipo === 'pdf' ? exportarPDF(opts) : exportarExcel(opts)
  }

  const propias = vehiculos.filter(v => v.flota === 'PROPIA').length
  const externas = vehiculos.filter(v => v.flota === 'EXTERNA').length

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} mb={2} alignItems={{ md: 'center' }} flexWrap="wrap" useFlexGap>
        <ToggleButtonGroup size="small" exclusive value={flota} onChange={(_, v) => v && setFlota(v)}>
          <ToggleButton value="TODAS" sx={{ textTransform: 'none' }}>Todas ({vehiculos.length})</ToggleButton>
          <ToggleButton value="PROPIA" sx={{ textTransform: 'none' }}>Propia ({propias})</ToggleButton>
          <ToggleButton value="EXTERNA" sx={{ textTransform: 'none' }}>Externa ({externas})</ToggleButton>
        </ToggleButtonGroup>
        <TextField
          size="small" placeholder="Buscar placa, marca, modelo…" value={search}
          onChange={e => setSearch(e.target.value)} sx={{ minWidth: 240, flex: 1 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 18, color: '#94A3B8' }} /></InputAdornment> }}
        />
        <Button size="small" variant="outlined" startIcon={<Download />} onClick={() => exportar('pdf')} sx={{ textTransform: 'none' }}>PDF</Button>
        <Button size="small" variant="outlined" startIcon={<Download />} onClick={() => exportar('excel')} sx={{ textTransform: 'none' }}>Excel</Button>
        {permitirCrear && (
          <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={() => setNuevoOpen(true)}
            sx={{ bgcolor: color, '&:hover': { bgcolor: colorDark }, textTransform: 'none', fontWeight: 700 }}>
            Nuevo vehículo (flota propia)
          </Button>
        )}
      </Stack>

      <Typography fontSize={12} color="#94A3B8" mb={1}>
        Flota propia = registrada en el CMMS · Flota externa = vehículos del TMS/Flota · a cada vehículo se le
        asigna una categoría de ejes/llantas ya creada (las categorías se pre-configuran en EAM → Configuración → Catálogos → Esquemas de vehículo).
      </Typography>

      <Paper elevation={0} sx={{ bgcolor: '#FFFFFF', border: `1px solid ${color}40`, borderRadius: '14px', overflowX: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              {columnas.map(c => <TableCell key={c.key} sx={{ fontWeight: 700, fontSize: 11, color: '#64748B', whiteSpace: 'nowrap' }}>{c.header}</TableCell>)}
            </TableRow>
          </TableHead>
          <TableBody>
            {filtered.map(v => (
              <TableRow key={`${v.origen}-${v.id}`} hover>
                <TableCell>
                  <Chip size="small" label={v.flota === 'PROPIA' ? 'Propia' : 'Externa'}
                    sx={{ fontWeight: 700, fontSize: 10, bgcolor: v.flota === 'PROPIA' ? `${color}22` : '#3B82F622', color: v.flota === 'PROPIA' ? colorDark : '#2563EB' }} />
                </TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{v.placa ?? '—'}</TableCell>
                <TableCell>{v.tipo ?? '—'}</TableCell>
                <TableCell>{v.marca ?? '—'}</TableCell>
                <TableCell>{v.modelo ?? '—'}</TableCell>
                <TableCell>{v.anio ?? '—'}</TableCell>
                <TableCell>{v.numero_ejes ?? '—'}</TableCell>
                <TableCell>{v.motor_marca ? `${v.motor_marca}${v.motor_linea ? ` ${v.motor_linea}` : ''}` : '—'}</TableCell>
                <TableCell>{v.motor_cc ? `${v.motor_cc.toLocaleString()} cc` : '—'}</TableCell>
                <TableCell>{v.propietario ?? '—'}</TableCell>
                <TableCell>
                  {v.activo_id ? (
                    <Button size="small" startIcon={<EditIcon sx={{ fontSize: 15 }} />} onClick={() => abrirLayout(v)} sx={{ textTransform: 'none', fontSize: 11.5 }}>
                      {v.numero_ejes != null ? `${v.numero_ejes} eje(s)` : 'Configurar'}
                    </Button>
                  ) : (
                    <Tooltip title="Vincula este vehículo al CMMS para poder configurar ejes/llantas y usarlo en Neumáticos">
                      <Button size="small" variant="outlined" startIcon={<LinkIcon sx={{ fontSize: 15 }} />}
                        onClick={() => { setLayoutVeh(v); mutVincular.mutate(v) }} disabled={mutVincular.isPending}
                        sx={{ textTransform: 'none', fontSize: 11.5, color, borderColor: `${color}66` }}>
                        Vincular al CMMS
                      </Button>
                    </Tooltip>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow><TableCell colSpan={columnas.length} align="center">
                <Typography color="text.secondary" py={3}>{isLoading ? 'Cargando…' : 'Sin vehículos registrados'}</Typography>
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      {/* Alta de vehículo de flota propia (CMMS) */}
      <Dialog open={nuevoOpen} onClose={() => setNuevoOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 16, display: 'flex', alignItems: 'center', gap: 1 }}>
          <DirectionsCar sx={{ color }} /> Nuevo vehículo · Flota propia
        </DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ pt: 0.5 }}>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Código *" size="small" fullWidth value={form.codigo} onChange={e => setForm(f => ({ ...f, codigo: e.target.value }))} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Placa" size="small" fullWidth value={form.placa} onChange={e => setForm(f => ({ ...f, placa: e.target.value.toUpperCase() }))} /></Grid>
            <Grid size={{ xs: 12 }}><TextField label="Nombre / descripción *" size="small" fullWidth value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Tipo" size="small" fullWidth value={form.tipo_activo} onChange={e => setForm(f => ({ ...f, tipo_activo: e.target.value }))}>
                {(tiposActivo.length ? tiposActivo : [{ codigo: 'VEHICULO', nombre: 'Vehículo' }]).map(t => <MenuItem key={t.codigo} value={t.codigo}>{t.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}><TextField label="Marca" size="small" fullWidth value={form.marca} onChange={e => setForm(f => ({ ...f, marca: e.target.value }))} /></Grid>
            <Grid size={{ xs: 6, sm: 3 }}><TextField label="Modelo" size="small" fullWidth value={form.modelo} onChange={e => setForm(f => ({ ...f, modelo: e.target.value }))} /></Grid>
            <Grid size={{ xs: 6, sm: 3 }}><TextField label="Año" type="number" size="small" fullWidth value={form.anio} onChange={e => setForm(f => ({ ...f, anio: e.target.value }))} /></Grid>
            {(tiposActivo.find(t => t.codigo === form.tipo_activo)?.usa_llantas ?? form.tipo_activo === 'VEHICULO') && <>
              <Grid size={{ xs: 12 }}><Typography fontSize={12} fontWeight={700} color="#94A3B8" mt={1}>EJES Y LLANTAS</Typography></Grid>
              <Grid size={{ xs: 12 }}>
                <TextField select label="Categoría de ejes/llantas" size="small" fullWidth value={form.esquema_id} onChange={e => setForm(f => ({ ...f, esquema_id: e.target.value }))}>
                  <MenuItem value="">Sin asignar (configurar después)</MenuItem>
                  {esquemas.map(es => (
                    <MenuItem key={es.id} value={String(es.id)}>
                      <Tooltip
                        placement="right" arrow
                        title={<EsquemaLlantasPreview
                          layout={es.layout} numeroEjes={es.numero_ejes}
                          tieneRepuesto={es.tiene_repuesto} cantidadRepuestos={es.cantidad_repuestos}
                          nombre={es.nombre}
                        />}
                        componentsProps={{ tooltip: { sx: { bgcolor: '#0F172A', maxWidth: 'none' } }, arrow: { sx: { color: '#0F172A' } } }}
                      >
                        <Box sx={{ width: '100%' }}>
                          {es.nombre} · {es.numero_ejes} eje(s){es.tiene_repuesto ? ` + repuesto` : ''}
                        </Box>
                      </Tooltip>
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              {esquemas.length === 0 && <Grid size={{ xs: 12 }}><Alert severity="info" sx={{ py: 0.5 }}>Aún no hay categorías creadas. Pre-configúralas en <b>EAM → Configuración → Catálogos → Esquemas de vehículo</b> y luego solo se asignan aquí.</Alert></Grid>}
            </>}
            <Grid size={{ xs: 12 }}><Typography fontSize={12} fontWeight={700} color="#94A3B8" mt={1}>MOTOR</Typography></Grid>
            <Grid size={{ xs: 12, sm: 5 }}><TextField label="Marca del motor" size="small" fullWidth value={form.motor_marca} onChange={e => setForm(f => ({ ...f, motor_marca: e.target.value }))} /></Grid>
            <Grid size={{ xs: 12, sm: 4 }}><TextField label="Línea del motor" size="small" fullWidth value={form.motor_linea} onChange={e => setForm(f => ({ ...f, motor_linea: e.target.value }))} /></Grid>
            <Grid size={{ xs: 12, sm: 3 }}><TextField label="Cilindraje (cc)" type="number" size="small" fullWidth value={form.motor_cc} onChange={e => setForm(f => ({ ...f, motor_cc: e.target.value }))} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Responsable" size="small" fullWidth value={form.responsable} onChange={e => setForm(f => ({ ...f, responsable: e.target.value }))} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Sede" size="small" fullWidth value={form.sede} onChange={e => setForm(f => ({ ...f, sede: e.target.value }))} /></Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setNuevoOpen(false)}>Cancelar</Button>
          <Button variant="contained" disabled={!form.codigo || !form.nombre || mutCrear.isPending}
            onClick={() => mutCrear.mutate({
              codigo: form.codigo, nombre: form.nombre, tipo_activo: form.tipo_activo,
              placa: form.placa || undefined, marca: form.marca || undefined, modelo: form.modelo || undefined,
              anio: form.anio ? Number(form.anio) : undefined,
              motor_marca: form.motor_marca || undefined, motor_linea: form.motor_linea || undefined,
              motor_cc: form.motor_cc ? Number(form.motor_cc) : undefined,
              responsable: form.responsable || undefined, sede: form.sede || undefined,
            })}
            sx={{ bgcolor: color, '&:hover': { bgcolor: colorDark } }}>Registrar</Button>
        </DialogActions>
      </Dialog>

      {/* Asignar categoría de ejes/llantas (pre-configurada) a un vehículo ya vinculado al CMMS */}
      <Dialog open={!!layoutVeh} onClose={() => setLayoutVeh(null)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 16 }}>Ejes y llantas
          <Typography variant="caption" color="text.secondary" display="block">{layoutVeh?.placa} — usado por el módulo de Neumáticos</Typography>
        </DialogTitle>
        <DialogContent dividers>
          {!layoutVeh?.activo_id ? (
            <Alert severity="info">Vinculando al CMMS…</Alert>
          ) : (
            <Stack spacing={2} pt={0.5}>
              <TextField select label="Categoría de ejes/llantas" size="small" fullWidth value={layoutEsquemaId} onChange={e => setLayoutEsquemaId(e.target.value)}>
                <MenuItem value="">Seleccionar…</MenuItem>
                {esquemas.map(es => (
                    <MenuItem key={es.id} value={String(es.id)}>
                      <Tooltip
                        placement="right" arrow
                        title={<EsquemaLlantasPreview
                          layout={es.layout} numeroEjes={es.numero_ejes}
                          tieneRepuesto={es.tiene_repuesto} cantidadRepuestos={es.cantidad_repuestos}
                          nombre={es.nombre}
                        />}
                        componentsProps={{ tooltip: { sx: { bgcolor: '#0F172A', maxWidth: 'none' } }, arrow: { sx: { color: '#0F172A' } } }}
                      >
                        <Box sx={{ width: '100%' }}>
                          {es.nombre} · {es.numero_ejes} eje(s){es.tiene_repuesto ? ` + repuesto` : ''}
                        </Box>
                      </Tooltip>
                    </MenuItem>
                  ))}
              </TextField>
              {esquemas.length === 0 && <Alert severity="info" sx={{ py: 0.5 }}>Aún no hay categorías creadas. Pre-configúralas en <b>EAM → Configuración → Catálogos → Esquemas de vehículo</b> y luego solo se asignan aquí.</Alert>}
            </Stack>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setLayoutVeh(null)}>Cerrar</Button>
          <Button
            variant="contained" disabled={!layoutVeh?.activo_id || !layoutEsquemaId || mutAsignarEsquema.isPending}
            onClick={guardarLayout}
            sx={{ bgcolor: color, '&:hover': { bgcolor: colorDark } }}>Guardar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
