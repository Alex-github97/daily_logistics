import React, { useMemo, useState } from 'react'
import {
  Box, Typography, Stack, Paper, Table, TableBody, TableCell, TableHead, TableRow, TableContainer, Chip, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, InputLabel, IconButton, Tooltip, Stepper, Step, StepLabel, Tabs, Tab, alpha, CircularProgress,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Add,
  Search,
  Visibility,
  Cancel as CancelIcon,
  CheckCircle,
  Close,
  LocalShipping,
  Person,
  Route,
  Inventory,
  AttachMoney,
  Description,
  Timeline,
  Close as CloseIcon,
} from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { ViajeDetalleDialog } from '@/components/tms/ViajeDetalle'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO

// ─── Types ────────────────────────────────────────────────────────────────────

type EstadoViaje = 'PROGRAMADO' | 'ASIGNADO' | 'EN_TRANSITO' | 'ENTREGADO' | 'CERRADO' | 'CANCELADO'

interface ViajeApi {
  id: number
  codigo: string
  tipo_servicio: string
  estado: EstadoViaje
  vehiculo_id?: number | null
  vehiculo_placa?: string | null
  conductor_hcm_id?: number | null
  conductor_nombre?: string | null
  origen_ciudad?: string | null
  destino_ciudad?: string | null
  fecha_programada_cargue?: string | null
  fecha_programada_entrega?: string | null
  distancia_km?: number | null
  peso_kg?: number | null
  num_entregas?: number | null
  valor_flete?: number | null
  otif_on_time?: boolean | null
  otif_in_full?: boolean | null
  notas?: string | null
}

interface NuevoViajeForm {
  tipoServicio: string
  descripcionCarga: string
  pesoKg: string
  volumenM3: string
  nEntregas: string
  valorFlete: string
  origenCiudad: string
  origenDireccion: string
  destinoCiudad: string
  destinoDireccion: string
  distanciaKm: string
  fechaCargue: string
  fechaEntrega: string
  vehiculoId: string
  conductorId: string
  notas: string
}

const TIPO_SERVICIO_OPTS: { value: string; label: string }[] = [
  { value: 'TERRESTRE_URBANO', label: 'Terrestre urbano' },
  { value: 'TERRESTRE_REGIONAL', label: 'Terrestre regional' },
  { value: 'TERRESTRE_NACIONAL', label: 'Terrestre nacional' },
  { value: 'INTERNACIONAL', label: 'Internacional' },
  { value: 'DISTRIBUCION', label: 'Distribución' },
  { value: 'ULTIMA_MILLA', label: 'Última milla' },
  { value: 'PRIMERA_MILLA', label: 'Primera milla' },
  { value: 'CROSS_DOCKING', label: 'Cross Docking' },
  { value: 'DEDICADO', label: 'Dedicado' },
]
const tipoServicioLabel = (v?: string | null) => TIPO_SERVICIO_OPTS.find((o) => o.value === v)?.label || v || '—'

const ESTADOS_ALL: EstadoViaje[] = ['PROGRAMADO', 'ASIGNADO', 'EN_TRANSITO', 'ENTREGADO', 'CERRADO', 'CANCELADO']

const estadoStyle: Record<EstadoViaje, { label: string; color: string; bg: string }> = {
  PROGRAMADO: { label: 'Programado', color: '#1D4ED8', bg: '#DBEAFE' },
  ASIGNADO: { label: 'Asignado', color: '#4338CA', bg: '#E0E7FF' },
  EN_TRANSITO: { label: 'En Tránsito', color: '#B45309', bg: '#FEF3C7' },
  ENTREGADO: { label: 'Entregado', color: '#15803D', bg: '#DCFCE7' },
  CERRADO: { label: 'Cerrado', color: '#4B5563', bg: '#F3F4F6' },
  CANCELADO: { label: 'Cancelado', color: '#DC2626', bg: '#FEE2E2' },
}

const fmt = (n?: number | null) => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n || 0)
const fmtFecha = (s?: string | null): string => {
  if (!s) return '—'
  const d = aFecha(s)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const STEPS = ['Servicio y Carga', 'Ruta y Tiempos', 'Recursos']

const FORM_INIT: NuevoViajeForm = {
  tipoServicio: '', descripcionCarga: '', pesoKg: '', volumenM3: '', nEntregas: '1', valorFlete: '',
  origenCiudad: '', origenDireccion: '', destinoCiudad: '', destinoDireccion: '', distanciaKm: '', fechaCargue: '', fechaEntrega: '',
  vehiculoId: '', conductorId: '', notas: '',
}

// ─── Dialog Nuevo Viaje (real) ─────────────────────────────────────────────────

function NuevoViajeDialog({ open, onClose, onCreado, vehiculos, conductores }: { open: boolean; onClose: () => void; onCreado: () => void; vehiculos: any[]; conductores: any[] }) {
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<NuevoViajeForm>(FORM_INIT)
  const [saving, setSaving] = useState(false)

  const set = (k: keyof NuevoViajeForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((p) => ({ ...p, [k]: e.target.value }))
  const handleClose = () => { setStep(0); setForm(FORM_INIT); onClose() }

  const crear = async () => {
    if (!form.tipoServicio) { toast.error('Selecciona el tipo de servicio'); setStep(0); return }
    setSaving(true)
    try {
      const payload: any = {
        tipo_servicio: form.tipoServicio,
        origen_ciudad: form.origenCiudad || undefined,
        origen_direccion: form.origenDireccion || undefined,
        destino_ciudad: form.destinoCiudad || undefined,
        destino_direccion: form.destinoDireccion || undefined,
        distancia_km: form.distanciaKm ? Number(form.distanciaKm) : undefined,
        peso_kg: form.pesoKg ? Number(form.pesoKg) : undefined,
        volumen_m3: form.volumenM3 ? Number(form.volumenM3) : undefined,
        num_entregas: form.nEntregas ? Number(form.nEntregas) : 1,
        valor_flete: form.valorFlete ? Number(form.valorFlete) : undefined,
        fecha_programada_cargue: form.fechaCargue || undefined,
        fecha_programada_entrega: form.fechaEntrega || undefined,
        vehiculo_id: form.vehiculoId ? Number(form.vehiculoId) : undefined,
        conductor_hcm_id: form.conductorId ? Number(form.conductorId) : undefined,
        notas: form.notas || undefined,
      }
      await apiClient.post('/tms/viajes', payload)
      toast.success('Viaje creado')
      handleClose(); onCreado()
    } catch (err: any) { toast.error(err.response?.data?.detail || 'No se pudo crear el viaje') }
    finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography fontWeight={700}>Nuevo Viaje</Typography>
          <IconButton size="small" onClick={handleClose}><CloseIcon /></IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stepper activeStep={step} sx={{ mb: 3 }}>{STEPS.map((s) => <Step key={s}><StepLabel>{s}</StepLabel></Step>)}</Stepper>

        {step === 0 && (
          <Stack spacing={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Tipo Servicio</InputLabel>
              <Select value={form.tipoServicio} label="Tipo Servicio" onChange={(e) => setForm((p) => ({ ...p, tipoServicio: String(e.target.value) }))}>
                {TIPO_SERVICIO_OPTS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
              </Select>
            </FormControl>
            <TextField label="Descripción Carga" size="small" fullWidth value={form.descripcionCarga} onChange={set('descripcionCarga')} />
            <Grid container spacing={2}>
              <Grid size={{ xs: 6 }}><TextField label="Peso (kg)" size="small" fullWidth type="number" value={form.pesoKg} onChange={set('pesoKg')} /></Grid>
              <Grid size={{ xs: 6 }}><TextField label="Volumen (m³)" size="small" fullWidth type="number" value={form.volumenM3} onChange={set('volumenM3')} /></Grid>
              <Grid size={{ xs: 6 }}><TextField label="N° Entregas" size="small" fullWidth type="number" value={form.nEntregas} onChange={set('nEntregas')} /></Grid>
              <Grid size={{ xs: 6 }}><TextField label="Valor Flete (COP)" size="small" fullWidth type="number" value={form.valorFlete} onChange={set('valorFlete')} /></Grid>
            </Grid>
          </Stack>
        )}

        {step === 1 && (
          <Grid container spacing={2}>
            <Grid size={{ xs: 6 }}><TextField label="Ciudad Origen" size="small" fullWidth value={form.origenCiudad} onChange={set('origenCiudad')} /></Grid>
            <Grid size={{ xs: 6 }}><TextField label="Ciudad Destino" size="small" fullWidth value={form.destinoCiudad} onChange={set('destinoCiudad')} /></Grid>
            <Grid size={{ xs: 6 }}><TextField label="Dirección Origen" size="small" fullWidth value={form.origenDireccion} onChange={set('origenDireccion')} /></Grid>
            <Grid size={{ xs: 6 }}><TextField label="Dirección Destino" size="small" fullWidth value={form.destinoDireccion} onChange={set('destinoDireccion')} /></Grid>
            <Grid size={{ xs: 12 }}><TextField label="Distancia (km)" size="small" fullWidth type="number" value={form.distanciaKm} onChange={set('distanciaKm')} /></Grid>
            <Grid size={{ xs: 6 }}><TextField label="Fecha/Hora Cargue" size="small" fullWidth type="datetime-local" InputLabelProps={{ shrink: true }} value={form.fechaCargue} onChange={set('fechaCargue')} /></Grid>
            <Grid size={{ xs: 6 }}><TextField label="Fecha/Hora Entrega" size="small" fullWidth type="datetime-local" InputLabelProps={{ shrink: true }} value={form.fechaEntrega} onChange={set('fechaEntrega')} /></Grid>
          </Grid>
        )}

        {step === 2 && (
          <Stack spacing={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Vehículo</InputLabel>
              <Select value={form.vehiculoId} label="Vehículo" onChange={(e) => setForm((p) => ({ ...p, vehiculoId: String(e.target.value) }))}>
                <MenuItem value="">— Sin asignar —</MenuItem>
                {vehiculos.map((v) => <MenuItem key={v.id} value={String(v.id)}>{v.placa} — {v.tipo_vehiculo}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Conductor</InputLabel>
              <Select value={form.conductorId} label="Conductor" onChange={(e) => setForm((p) => ({ ...p, conductorId: String(e.target.value) }))}>
                <MenuItem value="">— Sin asignar —</MenuItem>
                {conductores.map((c) => <MenuItem key={c.id} value={String(c.id)}>{c.colaborador_nombre || `Conductor #${c.id}`} — Lic. {c.num_licencia}</MenuItem>)}
              </Select>
            </FormControl>
            <TextField label="Notas adicionales" size="small" fullWidth multiline rows={3} value={form.notas} onChange={set('notas')} />
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        {step > 0 && <Button onClick={() => setStep((s) => s - 1)} disabled={saving}>Atrás</Button>}
        <Box flex={1} />
        {step < 2 ? (
          <Button variant="contained" sx={{ bgcolor: TMS_COLOR }} onClick={() => setStep((s) => s + 1)}>Siguiente</Button>
        ) : (
          <Button variant="contained" sx={{ bgcolor: TMS_COLOR }} onClick={crear} disabled={saving}>{saving ? 'Creando…' : 'Crear Viaje'}</Button>
        )}
      </DialogActions>
    </Dialog>
  )
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

export default function TMSViajes() {
  const qc = useQueryClient()
  const [estadoFiltro, setEstadoFiltro] = useState<EstadoViaje | 'TODOS'>('TODOS')
  // La búsqueda puede llegar en la dirección: es lo que permite que una alerta
  // del tablero abra esta pantalla ya filtrada por su viaje, en vez de dejar al
  // usuario buscándolo a mano entre miles.
  const [busqueda, setBusqueda] = useState(
    () => new URLSearchParams(window.location.search).get('q') ?? '')
  const [dialogNuevo, setDialogNuevo] = useState(false)
  const [viajeVer, setViajeVer] = useState<ViajeApi | null>(null)

  const { data, isLoading } = useQuery<{ items: ViajeApi[]; total: number }>({
    queryKey: ['tms-viajes'],
    queryFn: () => apiClient.get('/tms/viajes', { params: { per_page: 100 } }).then((r) => r.data),
  })
  const viajes = data?.items ?? []

  const { data: vehiculos = [] } = useQuery<any[]>({ queryKey: ['tms-vehiculos'], queryFn: () => apiClient.get('/tms/vehiculos').then((r) => r.data) })
  const { data: conductores = [] } = useQuery<any[]>({ queryKey: ['hcm-conductores'], queryFn: () => apiClient.get('/hcm/conductores').then((r) => r.data) })

  const filtered = useMemo(() => viajes.filter((v) => {
    if (estadoFiltro !== 'TODOS' && v.estado !== estadoFiltro) return false
    if (busqueda && !`${v.codigo} ${v.origen_ciudad ?? ''} ${v.destino_ciudad ?? ''} ${v.conductor_nombre ?? ''}`.toLowerCase().includes(busqueda.toLowerCase())) return false
    return true
  }), [viajes, estadoFiltro, busqueda])

  const handleAccion = async (estado: string, id: number) => {
    try {
      await apiClient.put(`/tms/viajes/${id}/estado`, null, { params: { estado } })
      toast.success('Estado actualizado')
      qc.invalidateQueries({ queryKey: ['tms-viajes'] })
    } catch (err: any) { toast.error(err.response?.data?.detail || 'No se pudo cambiar el estado') }
  }

  const ESTADOS_BTN: Array<EstadoViaje | 'TODOS'> = ['TODOS', ...ESTADOS_ALL]

  return (
    <Layout>
      <Box sx={{ p: 3, maxWidth: 1600, mx: 'auto' }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
          <Box>
            <Typography variant="h5" fontWeight={800} color={TMS_COLOR}>Gestión de Viajes</Typography>
            <Typography variant="body2" color="text.secondary">{data?.total ?? viajes.length} viajes registrados</Typography>
          </Box>
          <Button variant="contained" startIcon={<Add />} sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#0284C7' } }} onClick={() => setDialogNuevo(true)}>Nuevo Viaje</Button>
        </Stack>

        {/* Toolbar */}
        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '12px', p: 2, mb: 2 }}>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" gap={1}>
            <TextField size="small" placeholder="Buscar por código, ciudad, conductor..." value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
              InputProps={{ startAdornment: <Search sx={{ fontSize: 18, color: 'text.secondary', mr: 1 }} /> }} sx={{ width: 320 }} />
            <Stack direction="row" spacing={0.5} flexWrap="wrap" gap={0.5}>
              {ESTADOS_BTN.map((es) => {
                const active = estadoFiltro === es
                const s = es === 'TODOS' ? null : estadoStyle[es as EstadoViaje]
                return (
                  <Chip key={es} size="small"
                    label={es === 'TODOS' ? `Todos (${viajes.length})` : `${s!.label} (${viajes.filter((v) => v.estado === es).length})`}
                    onClick={() => setEstadoFiltro(es)}
                    sx={{ cursor: 'pointer', fontWeight: active ? 700 : 500, bgcolor: active ? (s ? s.bg : alpha(TMS_COLOR, 0.1)) : 'transparent', color: active ? (s ? s.color : TMS_COLOR) : 'text.secondary', border: `1px solid ${active ? (s ? s.color : TMS_COLOR) : '#E5E7EB'}` }} />
                )
              })}
            </Stack>
          </Stack>
        </Paper>

        {/* Tabla */}
        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', overflow: 'hidden' }}>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                  {['Código', 'Tipo', 'Ruta', 'Conductor / Placa', 'Prog. Cargue', 'Prog. Entrega', 'Valor Flete', 'Estado', 'OTIF', 'Acciones'].map((h) => (
                    <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12 }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {isLoading ? (
                  <TableRow><TableCell colSpan={10} align="center" sx={{ py: 5 }}><CircularProgress size={26} /></TableCell></TableRow>
                ) : filtered.map((v) => {
                  const e = estadoStyle[v.estado]
                  return (
                    <TableRow key={v.id} hover sx={{ cursor: 'pointer' }} onClick={() => setViajeVer(v)}>
                      <TableCell><Typography fontSize={12} fontWeight={700} color={TMS_COLOR}>{v.codigo}</Typography></TableCell>
                      <TableCell><Chip label={tipoServicioLabel(v.tipo_servicio)} size="small" sx={{ fontSize: 10, fontWeight: 600, bgcolor: alpha(TMS_COLOR, 0.08), color: TMS_COLOR }} /></TableCell>
                      <TableCell>
                        <Typography fontSize={12}>{v.origen_ciudad || '—'}</Typography>
                        <Typography fontSize={11} color="text.secondary">→ {v.destino_ciudad || '—'}</Typography>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <Person sx={{ fontSize: 13, color: 'text.secondary' }} />
                          <Box>
                            <Typography fontSize={12}>{v.conductor_nombre || '—'}</Typography>
                            <Typography fontSize={11} color="text.secondary">{v.vehiculo_placa || '—'}</Typography>
                          </Box>
                        </Stack>
                      </TableCell>
                      <TableCell><Typography fontSize={11}>{fmtFecha(v.fecha_programada_cargue)}</Typography></TableCell>
                      <TableCell><Typography fontSize={11}>{fmtFecha(v.fecha_programada_entrega)}</Typography></TableCell>
                      <TableCell><Typography fontSize={12} fontWeight={600}>{fmt(v.valor_flete)}</Typography></TableCell>
                      <TableCell><Chip label={e.label} size="small" sx={{ bgcolor: e.bg, color: e.color, fontWeight: 700, fontSize: 11 }} /></TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={0.5}>
                          <Tooltip title="On Time"><Box>{v.otif_on_time === true ? <CheckCircle sx={{ fontSize: 16, color: '#16A34A' }} /> : v.otif_on_time === false ? <CancelIcon sx={{ fontSize: 16, color: '#DC2626' }} /> : <Typography fontSize={11} color="text.disabled">—</Typography>}</Box></Tooltip>
                          <Tooltip title="In Full"><Box>{v.otif_in_full === true ? <CheckCircle sx={{ fontSize: 16, color: '#16A34A' }} /> : v.otif_in_full === false ? <CancelIcon sx={{ fontSize: 16, color: '#DC2626' }} /> : <Typography fontSize={11} color="text.disabled">—</Typography>}</Box></Tooltip>
                        </Stack>
                      </TableCell>
                      <TableCell onClick={(ev) => ev.stopPropagation()}>
                        <Stack direction="row" spacing={0.25}>
                          <Tooltip title="Ver detalle"><IconButton size="small" onClick={() => setViajeVer(v)} sx={{ color: TMS_COLOR }}><Visibility sx={{ fontSize: 16 }} /></IconButton></Tooltip>
                          {['PROGRAMADO', 'ASIGNADO'].includes(v.estado) && (
                            <Tooltip title="Cancelar"><IconButton size="small" sx={{ color: '#DC2626' }} onClick={() => handleAccion('CANCELADO', v.id)}><CancelIcon sx={{ fontSize: 16 }} /></IconButton></Tooltip>
                          )}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {!isLoading && filtered.length === 0 && (
                  <TableRow><TableCell colSpan={10} align="center" sx={{ py: 4, color: 'text.secondary', fontSize: 13 }}>
                    {viajes.length === 0 ? 'Aún no hay viajes. Crea el primero con “Nuevo Viaje”.' : 'No se encontraron viajes con los filtros aplicados'}
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        <NuevoViajeDialog open={dialogNuevo} onClose={() => setDialogNuevo(false)} onCreado={() => qc.invalidateQueries({ queryKey: ['tms-viajes'] })} vehiculos={vehiculos} conductores={conductores} />
        {/* La llave por viaje reinicia la pestaña al abrir otro. */}
        <ViajeDetalleDialog key={viajeVer?.id ?? 'ninguno'} viaje={viajeVer} open={!!viajeVer} onClose={() => setViajeVer(null)} onAccion={handleAccion}
          estadoChip={(es) => { const st = estadoStyle[es as EstadoViaje]; return st ? <Chip label={st.label} size="small" sx={{ bgcolor: st.bg, color: st.color, fontWeight: 700 }} /> : null }}
          onCambioViaje={async () => {
            // Registrar la llegada a destino entrega el viaje en el servidor:
            // se trae de nuevo para que el detalle y la lista muestren el estado real.
            qc.invalidateQueries({ queryKey: ['tms-viajes'] })
            if (viajeVer) setViajeVer((await apiClient.get(`/tms/viajes/${viajeVer.id}`)).data)
          }} />
      </Box>
    </Layout>
  )
}
