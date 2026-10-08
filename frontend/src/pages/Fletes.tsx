import React, { useState } from 'react'
import {
  Box, Paper, Tabs, Tab, Typography, Button, Chip, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, IconButton, Tooltip, CircularProgress, Alert, Divider, Stack, alpha,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Add as AddIcon,
  LocalShipping as TruckIcon,
  Assignment as AsignacionIcon,
  QueuePlayNext as EnturnarIcon,
  Edit as EditIcon,
  PersonAdd as PersonAddIcon,
  CheckCircle as CheckIcon,
  Cancel as CancelIcon,
  SwapHoriz as RouteIcon,
  Delete as DeleteIcon,
  Inventory as CargoIcon,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'

import { mensajeDeError } from '@/utils/errorApi'
import { aFecha } from '@/utils/fechas'
// ── Tipos ────────────────────────────────────────────────────────────────────

const TIPOS_VEHICULO = [
  { value: 'TRACTOCAMION',   label: 'Tractocamión' },
  { value: 'CAMION_SENCILLO', label: 'Camión Sencillo' },
  { value: 'DOBLETROQUE',    label: 'Dobletroque' },
  { value: 'PATINETA',       label: 'Patineta' },
  { value: 'TURBO',          label: 'Turbo' },
]

const TIPOS_CARROCERIA = [
  { value: 'ESTACAS',     label: 'Estacas' },
  { value: 'PLANCHA',     label: 'Plancha' },
  { value: 'CONTENEDOR',  label: 'Contenedor' },
  { value: 'FURGON',      label: 'Furgón' },
  { value: 'CISTERNA',    label: 'Cisterna' },
  { value: 'REFRIGERADO', label: 'Refrigerado' },
  { value: 'PLATAFORMA',  label: 'Plataforma' },
]

const ESTADO_COLORS: Record<string, string> = {
  PENDIENTE: '#F59E0B',
  ASIGNADO:  '#3B82F6',
  EN_CURSO:  '#8B5CF6',
  COMPLETADO: '#1A1A1A',
  CANCELADO:  '#EF4444',
}

const ESTADO_LABELS: Record<string, string> = {
  PENDIENTE:  'Pendiente',
  ASIGNADO:   'Asignado',
  EN_CURSO:   'En Curso',
  COMPLETADO: 'Completado',
  CANCELADO:  'Cancelado',
}

interface Flete {
  id: number
  ciudad_origen: string
  ciudad_destino: string
  tipo_vehiculo: string
  tipo_carroceria?: string
  generador_id?: number
  generador_nombre?: string
  descripcion_carga?: string
  peso_kg?: number
  num_entregas?: number
  distancia_km?: number
  fecha_hora_cargue: string
  fecha_hora_entrega?: string
  valor_flete?: number
  es_negociable: boolean
  estado: string
  conductor_id?: number
  conductor_nombre?: string
  vehiculo_flete_id?: number
  vehiculo_placa?: string
  notas?: string
  created_at: string
}

interface Conductor { id: number; nombre: string; apellido: string; cedula?: string; telefono?: string }
interface VehiculoFlete { id: number; conductor_id: number; placa: string; tipo_vehiculo: string; tipo_carroceria?: string; marca?: string; modelo?: string }
interface GeneradorCarga { id: number; nombre: string; nit?: string; ciudad?: string }
interface Enturnamiento {
  id: number; conductor_id: number; conductor_nombre?: string; conductor_cedula?: string
  ciudad_disponible: string; fecha_hora_disponible: string; tipo_vehiculo?: string
  tipo_carroceria?: string; estado: string; flete_asignado_id?: number; notas?: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const tipoLabel = (val: string) => TIPOS_VEHICULO.find(t => t.value === val)?.label ?? val
const carroceriaLabel = (val?: string) => val ? (TIPOS_CARROCERIA.find(t => t.value === val)?.label ?? val) : ''
const formatDateTime = (dt?: string) => dt ? aFecha(dt).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' }) : '—'
const formatCurrency = (n?: number) => n != null ? `$${n.toLocaleString('es-CO')}` : null

// ── Componente EstadoChip ─────────────────────────────────────────────────────

function EstadoChip({ estado }: { estado: string }) {
  return (
    <Chip
      label={ESTADO_LABELS[estado] ?? estado}
      size="small"
      sx={{
        bgcolor: alpha(ESTADO_COLORS[estado] ?? '#6B7280', 0.15),
        color: ESTADO_COLORS[estado] ?? '#6B7280',
        fontWeight: 600,
        fontSize: 11,
        height: 22,
        border: `1px solid ${alpha(ESTADO_COLORS[estado] ?? '#6B7280', 0.35)}`,
      }}
    />
  )
}

// ── Tarjeta de Flete ──────────────────────────────────────────────────────────

function FletaCard({
  flete, onAsignar, onEstado, onDelete, readonly,
}: {
  flete: Flete
  onAsignar?: (f: Flete) => void
  onEstado?: (f: Flete, estado: string) => void
  onDelete?: (id: number) => void
  readonly?: boolean
}) {
  return (
    <Paper
      elevation={0}
      sx={{
        border: '1px solid',
        borderColor: alpha(ESTADO_COLORS[flete.estado] ?? '#E5E7EB', 0.3),
        borderRadius: '14px',
        p: 2.5,
        transition: 'all 0.15s ease',
        '&:hover': { boxShadow: '0 4px 20px rgba(0,0,0,0.08)' },
      }}
    >
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" mb={1.5}>
        <Box>
          <Stack direction="row" alignItems="center" gap={1} mb={0.5}>
            <RouteIcon sx={{ fontSize: 16, color: '#6B7280' }} />
            <Typography fontWeight={700} fontSize={15}>
              {flete.ciudad_origen} → {flete.ciudad_destino}
            </Typography>
          </Stack>
          <Stack direction="row" gap={0.75} flexWrap="wrap">
            <Chip label={tipoLabel(flete.tipo_vehiculo)} size="small" sx={{ fontSize: 11, height: 20 }} />
            {flete.tipo_carroceria && (
              <Chip label={carroceriaLabel(flete.tipo_carroceria)} size="small" variant="outlined" sx={{ fontSize: 11, height: 20 }} />
            )}
            <EstadoChip estado={flete.estado} />
          </Stack>
        </Box>
        <Box textAlign="right">
          {flete.es_negociable ? (
            <Typography fontSize={12} color="warning.main" fontWeight={600}>Negociable</Typography>
          ) : flete.valor_flete ? (
            <Typography fontWeight={700} fontSize={14} color="success.main">
              {formatCurrency(flete.valor_flete)}
            </Typography>
          ) : null}
          <Typography fontSize={11} color="text.secondary">#{flete.id}</Typography>
        </Box>
      </Stack>

      <Grid container spacing={1.5} sx={{ mb: 1.5 }}>
        {flete.generador_nombre && (
          <Grid size={6}>
            <Typography fontSize={11} color="text.secondary">Cliente</Typography>
            <Typography fontSize={13} fontWeight={500}>{flete.generador_nombre}</Typography>
          </Grid>
        )}
        {flete.descripcion_carga && (
          <Grid size={6}>
            <Typography fontSize={11} color="text.secondary">Carga</Typography>
            <Typography fontSize={13} fontWeight={500}>{flete.descripcion_carga}</Typography>
          </Grid>
        )}
        {flete.peso_kg && (
          <Grid size={4}>
            <Typography fontSize={11} color="text.secondary">Peso</Typography>
            <Typography fontSize={13} fontWeight={500}>{flete.peso_kg.toLocaleString()} kg</Typography>
          </Grid>
        )}
        {flete.num_entregas && flete.num_entregas > 1 && (
          <Grid size={4}>
            <Typography fontSize={11} color="text.secondary">Entregas</Typography>
            <Typography fontSize={13} fontWeight={500}>{flete.num_entregas}</Typography>
          </Grid>
        )}
        <Grid size={6}>
          <Typography fontSize={11} color="text.secondary">Cargue</Typography>
          <Typography fontSize={13} fontWeight={500}>{formatDateTime(flete.fecha_hora_cargue)}</Typography>
        </Grid>
        {flete.fecha_hora_entrega && (
          <Grid size={6}>
            <Typography fontSize={11} color="text.secondary">Entrega</Typography>
            <Typography fontSize={13} fontWeight={500}>{formatDateTime(flete.fecha_hora_entrega)}</Typography>
          </Grid>
        )}
        {flete.conductor_nombre && (
          <Grid size={6}>
            <Typography fontSize={11} color="text.secondary">Conductor</Typography>
            <Typography fontSize={13} fontWeight={600} color="primary.main">{flete.conductor_nombre}</Typography>
          </Grid>
        )}
        {flete.vehiculo_placa && (
          <Grid size={6}>
            <Typography fontSize={11} color="text.secondary">Vehículo</Typography>
            <Typography fontSize={13} fontWeight={500}>{flete.vehiculo_placa}</Typography>
          </Grid>
        )}
      </Grid>

      {!readonly && (
        <Stack direction="row" gap={1} justifyContent="flex-end">
          {flete.estado === 'PENDIENTE' && onAsignar && (
            <Button
              size="small"
              variant="contained"
              startIcon={<PersonAddIcon />}
              onClick={() => onAsignar(flete)}
              sx={{ borderRadius: '8px', fontSize: 12, textTransform: 'none', bgcolor: '#1A1A1A', '&:hover': { bgcolor: '#1A1A1A' } }}
            >
              Asignar Conductor
            </Button>
          )}
          {flete.estado === 'ASIGNADO' && onEstado && (
            <Button
              size="small"
              variant="outlined"
              color="primary"
              onClick={() => onEstado(flete, 'EN_CURSO')}
              sx={{ borderRadius: '8px', fontSize: 12, textTransform: 'none' }}
            >
              Iniciar Viaje
            </Button>
          )}
          {flete.estado === 'EN_CURSO' && onEstado && (
            <Button
              size="small"
              variant="outlined"
              color="success"
              startIcon={<CheckIcon />}
              onClick={() => onEstado(flete, 'COMPLETADO')}
              sx={{ borderRadius: '8px', fontSize: 12, textTransform: 'none' }}
            >
              Completar
            </Button>
          )}
          {['PENDIENTE', 'ASIGNADO'].includes(flete.estado) && onEstado && (
            <Button
              size="small"
              variant="outlined"
              color="error"
              startIcon={<CancelIcon />}
              onClick={() => onEstado(flete, 'CANCELADO')}
              sx={{ borderRadius: '8px', fontSize: 12, textTransform: 'none' }}
            >
              Cancelar
            </Button>
          )}
          {['PENDIENTE', 'CANCELADO'].includes(flete.estado) && onDelete && (
            <Tooltip title="Eliminar flete">
              <IconButton size="small" color="error" onClick={() => onDelete(flete.id)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
      )}
    </Paper>
  )
}

// ── Tab 1: Registrar Flete ────────────────────────────────────────────────────

function TabRegistrar({ generadores, conductores, onSuccess }: {
  generadores: GeneradorCarga[]
  conductores: Conductor[]
  onSuccess: () => void
}) {
  const [form, setForm] = useState({
    ciudad_origen: '', ciudad_destino: '', tipo_vehiculo: '',
    tipo_carroceria: '', generador_id: '', descripcion_carga: '',
    peso_kg: '', num_entregas: '1', distancia_km: '',
    fecha_hora_cargue: '', fecha_hora_entrega: '',
    valor_flete: '', es_negociable: false, notas: '',
  })
  const [showGenDialog, setShowGenDialog] = useState(false)
  const [newGen, setNewGen] = useState({ nombre: '', nit: '', ciudad: '', telefono: '', contacto: '' })
  const qc = useQueryClient()

  const createMut = useMutation({
    mutationFn: (data: object) => api.post('/fletes/', data).then(r => r.data),
    onSuccess: () => {
      toast.success('Flete registrado exitosamente')
      setForm({
        ciudad_origen: '', ciudad_destino: '', tipo_vehiculo: '',
        tipo_carroceria: '', generador_id: '', descripcion_carga: '',
        peso_kg: '', num_entregas: '1', distancia_km: '',
        fecha_hora_cargue: '', fecha_hora_entrega: '',
        valor_flete: '', es_negociable: false, notas: '',
      })
      qc.invalidateQueries({ queryKey: ['fletes'] })
      onSuccess()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al registrar el flete')),
  })

  const createGenMut = useMutation({
    mutationFn: (data: object) => api.post('/fletes/generadores/', data).then(r => r.data),
    onSuccess: (data) => {
      toast.success('Generador creado')
      setForm(f => ({ ...f, generador_id: String(data.id) }))
      qc.invalidateQueries({ queryKey: ['fletes-generadores'] })
      setShowGenDialog(false)
      setNewGen({ nombre: '', nit: '', ciudad: '', telefono: '', contacto: '' })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al crear el generador')),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.ciudad_origen || !form.ciudad_destino || !form.tipo_vehiculo || !form.fecha_hora_cargue) {
      toast.error('Completa los campos obligatorios: origen, destino, tipo de vehículo y fecha de cargue')
      return
    }
    const payload: Record<string, unknown> = {
      ciudad_origen: form.ciudad_origen,
      ciudad_destino: form.ciudad_destino,
      tipo_vehiculo: form.tipo_vehiculo,
      fecha_hora_cargue: form.fecha_hora_cargue,
      es_negociable: form.es_negociable,
    }
    if (form.tipo_carroceria) payload.tipo_carroceria = form.tipo_carroceria
    if (form.generador_id) payload.generador_id = Number(form.generador_id)
    if (form.descripcion_carga) payload.descripcion_carga = form.descripcion_carga
    if (form.peso_kg) payload.peso_kg = Number(form.peso_kg)
    if (form.num_entregas) payload.num_entregas = Number(form.num_entregas)
    if (form.distancia_km) payload.distancia_km = Number(form.distancia_km)
    if (form.fecha_hora_entrega) payload.fecha_hora_entrega = form.fecha_hora_entrega
    if (form.valor_flete && !form.es_negociable) payload.valor_flete = Number(form.valor_flete)
    if (form.notas) payload.notas = form.notas
    createMut.mutate(payload)
  }

  const f = (name: string) => form[name as keyof typeof form]
  const set = (name: string, value: unknown) => setForm(prev => ({ ...prev, [name]: value }))

  return (
    <Box component="form" onSubmit={handleSubmit}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography fontSize={15} fontWeight={600} color="text.primary">Datos del Flete</Typography>
        <Button
          type="submit"
          variant="contained"
          startIcon={createMut.isPending ? <CircularProgress size={16} color="inherit" /> : <AddIcon />}
          disabled={createMut.isPending}
          sx={{ borderRadius: '10px', textTransform: 'none', bgcolor: '#1A1A1A', '&:hover': { bgcolor: '#1A1A1A' } }}
        >
          Registrar Flete
        </Button>
      </Stack>

      <Grid container spacing={2.5}>
        <Grid size={6}>
          <TextField
            label="Ciudad de Origen *" fullWidth size="small"
            value={form.ciudad_origen} onChange={e => set('ciudad_origen', e.target.value)}
          />
        </Grid>
        <Grid size={6}>
          <TextField
            label="Ciudad de Destino *" fullWidth size="small"
            value={form.ciudad_destino} onChange={e => set('ciudad_destino', e.target.value)}
          />
        </Grid>
        <Grid size={6}>
          <TextField
            select label="Tipo de Vehículo *" fullWidth size="small"
            value={form.tipo_vehiculo} onChange={e => set('tipo_vehiculo', e.target.value)}
          >
            {TIPOS_VEHICULO.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
          </TextField>
        </Grid>
        <Grid size={6}>
          <TextField
            select label="Tipo de Carrocería" fullWidth size="small"
            value={form.tipo_carroceria} onChange={e => set('tipo_carroceria', e.target.value)}
          >
            <MenuItem value=""><em>Sin especificar</em></MenuItem>
            {TIPOS_CARROCERIA.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
          </TextField>
        </Grid>
        <Grid size={12}>
          <Stack direction="row" gap={1} alignItems="flex-start">
            <TextField
              select label="Cliente Generador de Carga" fullWidth size="small"
              value={form.generador_id} onChange={e => set('generador_id', e.target.value)}
            >
              <MenuItem value=""><em>Sin especificar</em></MenuItem>
              {generadores.map(g => (
                <MenuItem key={g.id} value={String(g.id)}>
                  {g.nombre}{g.ciudad ? ` — ${g.ciudad}` : ''}
                </MenuItem>
              ))}
            </TextField>
            <Tooltip title="Crear nuevo generador">
              <IconButton
                onClick={() => setShowGenDialog(true)}
                sx={{ border: '1px solid', borderColor: 'divider', borderRadius: '8px', flexShrink: 0 }}
              >
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Grid>
        <Grid size={8}>
          <TextField
            label="Descripción de Carga" fullWidth size="small"
            value={form.descripcion_carga} onChange={e => set('descripcion_carga', e.target.value)}
          />
        </Grid>
        <Grid size={4}>
          <TextField
            label="Número de Entregas" type="number" fullWidth size="small"
            inputProps={{ min: 1 }}
            value={form.num_entregas} onChange={e => set('num_entregas', e.target.value)}
          />
        </Grid>
        <Grid size={4}>
          <TextField
            label="Peso (kg)" type="number" fullWidth size="small"
            inputProps={{ min: 0 }}
            value={form.peso_kg} onChange={e => set('peso_kg', e.target.value)}
          />
        </Grid>
        <Grid size={4}>
          <TextField
            label="Distancia (km)" type="number" fullWidth size="small"
            inputProps={{ min: 0 }}
            value={form.distancia_km} onChange={e => set('distancia_km', e.target.value)}
            helperText="Próximamente calculado automáticamente"
          />
        </Grid>
        <Grid size={4}>
          <TextField
            label="Valor del Flete ($)" type="number" fullWidth size="small"
            inputProps={{ min: 0 }}
            value={form.valor_flete} onChange={e => set('valor_flete', e.target.value)}
            disabled={form.es_negociable as boolean}
          />
        </Grid>
        <Grid size={6}>
          <TextField
            label="Fecha y Hora de Cargue *" type="datetime-local" fullWidth size="small"
            InputLabelProps={{ shrink: true }}
            value={form.fecha_hora_cargue} onChange={e => set('fecha_hora_cargue', e.target.value)}
          />
        </Grid>
        <Grid size={6}>
          <TextField
            label="Fecha y Hora de Entrega" type="datetime-local" fullWidth size="small"
            InputLabelProps={{ shrink: true }}
            value={form.fecha_hora_entrega} onChange={e => set('fecha_hora_entrega', e.target.value)}
          />
        </Grid>
        <Grid size={12}>
          <Stack direction="row" alignItems="center" gap={2}>
            <Box
              component="label"
              sx={{ display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer', userSelect: 'none' }}
            >
              <Box
                component="input"
                type="checkbox"
                checked={form.es_negociable as boolean}
                onChange={e => set('es_negociable', e.target.checked)}
                sx={{ width: 16, height: 16, cursor: 'pointer' }}
              />
              <Typography fontSize={14} color="text.secondary">Flete Negociable (sin valor fijo)</Typography>
            </Box>
          </Stack>
        </Grid>
        <Grid size={12}>
          <TextField
            label="Notas adicionales" fullWidth size="small" multiline rows={2}
            value={form.notas} onChange={e => set('notas', e.target.value)}
          />
        </Grid>
      </Grid>

      {/* Dialog nuevo generador */}
      <Dialog open={showGenDialog} onClose={() => setShowGenDialog(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>Nuevo Generador de Carga</DialogTitle>
        <DialogContent>
          <Stack gap={2} pt={1}>
            <TextField label="Nombre *" size="small" fullWidth value={newGen.nombre} onChange={e => setNewGen(g => ({ ...g, nombre: e.target.value }))} />
            <TextField label="NIT" size="small" fullWidth value={newGen.nit} onChange={e => setNewGen(g => ({ ...g, nit: e.target.value }))} />
            <TextField label="Ciudad" size="small" fullWidth value={newGen.ciudad} onChange={e => setNewGen(g => ({ ...g, ciudad: e.target.value }))} />
            <TextField label="Teléfono" size="small" fullWidth value={newGen.telefono} onChange={e => setNewGen(g => ({ ...g, telefono: e.target.value }))} />
            <TextField label="Contacto" size="small" fullWidth value={newGen.contacto} onChange={e => setNewGen(g => ({ ...g, contacto: e.target.value }))} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          <Button size="small" onClick={() => setShowGenDialog(false)} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button
            size="small" variant="contained"
            disabled={!newGen.nombre || createGenMut.isPending}
            onClick={() => createGenMut.mutate(newGen)}
            sx={{ textTransform: 'none', bgcolor: '#1A1A1A', '&:hover': { bgcolor: '#1A1A1A' } }}
          >
            Crear
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ── Tab 2: Asignación de Viajes ───────────────────────────────────────────────

function TabAsignacion({ fletes, conductores, onAsignar, onEstado, onDelete }: {
  fletes: Flete[]
  conductores: Conductor[]
  onAsignar: (flete: Flete, conductorId: number, vehiculoId: number) => void
  onEstado: (fleteId: number, estado: string) => void
  onDelete: (fleteId: number) => void
}) {
  const [selectedFlete, setSelectedFlete] = useState<Flete | null>(null)
  const [conductorId, setConductorId] = useState('')
  const [vehiculoId, setVehiculoId] = useState('')
  const [filtroEstado, setFiltroEstado] = useState('TODOS')

  const { data: vehiculosConductor = [] } = useQuery<VehiculoFlete[]>({
    queryKey: ['vehiculos-conductor', conductorId],
    queryFn: () => conductorId
      ? api.get(`/fletes/conductores/${conductorId}/vehiculos`).then(r => r.data)
      : Promise.resolve([]),
    enabled: !!conductorId,
  })

  const fltroOptions = ['TODOS', 'PENDIENTE', 'ASIGNADO', 'EN_CURSO', 'COMPLETADO', 'CANCELADO']
  const filtrados = filtroEstado === 'TODOS' ? fletes : fletes.filter(f => f.estado === filtroEstado)

  return (
    <Box>
      <Stack direction="row" gap={1} mb={3} flexWrap="wrap">
        {fltroOptions.map(e => (
          <Chip
            key={e}
            label={e === 'TODOS' ? `Todos (${fletes.length})` : `${ESTADO_LABELS[e] ?? e} (${fletes.filter(f => f.estado === e).length})`}
            onClick={() => setFiltroEstado(e)}
            sx={{
              cursor: 'pointer',
              fontWeight: filtroEstado === e ? 700 : 400,
              bgcolor: filtroEstado === e ? alpha(ESTADO_COLORS[e] ?? '#1A1A1A', 0.15) : 'transparent',
              border: `1px solid ${filtroEstado === e ? (ESTADO_COLORS[e] ?? '#1A1A1A') : '#E5E7EB'}`,
              color: filtroEstado === e ? (ESTADO_COLORS[e] ?? '#1A1A1A') : 'text.secondary',
            }}
          />
        ))}
      </Stack>

      {filtrados.length === 0 ? (
        <Box textAlign="center" py={8}>
          <TruckIcon sx={{ fontSize: 48, color: '#D1D5DB', mb: 2 }} />
          <Typography color="text.secondary">No hay fletes con ese filtro</Typography>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {filtrados.map(flete => (
            <Grid key={flete.id} size={{ xs: 12, md: 6, lg: 4 }}>
              <FletaCard
                flete={flete}
                onAsignar={(f) => { setSelectedFlete(f); setConductorId(''); setVehiculoId('') }}
                onEstado={(f, estado) => onEstado(f.id, estado)}
                onDelete={onDelete}
              />
            </Grid>
          ))}
        </Grid>
      )}

      {/* Dialog de asignación */}
      <Dialog open={!!selectedFlete} onClose={() => setSelectedFlete(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>
          Asignar Conductor al Flete #{selectedFlete?.id}
        </DialogTitle>
        <DialogContent>
          <Stack gap={2} pt={1}>
            {selectedFlete && (
              <Alert severity="info" sx={{ fontSize: 12 }}>
                <strong>{selectedFlete.ciudad_origen} → {selectedFlete.ciudad_destino}</strong><br />
                Requiere: {tipoLabel(selectedFlete.tipo_vehiculo)}
                {selectedFlete.tipo_carroceria ? ` · ${carroceriaLabel(selectedFlete.tipo_carroceria)}` : ''}
              </Alert>
            )}
            <TextField
              select label="Conductor" size="small" fullWidth
              value={conductorId} onChange={e => { setConductorId(e.target.value); setVehiculoId('') }}
            >
              <MenuItem value=""><em>Seleccionar conductor</em></MenuItem>
              {conductores.map(c => (
                <MenuItem key={c.id} value={String(c.id)}>
                  {c.nombre} {c.apellido}{c.cedula ? ` — CC ${c.cedula}` : ''}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select label="Vehículo" size="small" fullWidth
              value={vehiculoId} onChange={e => setVehiculoId(e.target.value)}
              disabled={!conductorId || vehiculosConductor.length === 0}
              helperText={conductorId && vehiculosConductor.length === 0 ? 'El conductor no tiene vehículos registrados' : ''}
            >
              <MenuItem value=""><em>Seleccionar vehículo</em></MenuItem>
              {vehiculosConductor.map(v => (
                <MenuItem key={v.id} value={String(v.id)}>
                  {v.placa} — {tipoLabel(v.tipo_vehiculo)}{v.tipo_carroceria ? ` · ${carroceriaLabel(v.tipo_carroceria)}` : ''}
                  {v.marca ? ` (${v.marca})` : ''}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          <Button size="small" onClick={() => setSelectedFlete(null)} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button
            size="small" variant="contained"
            disabled={!conductorId || !vehiculoId}
            onClick={() => {
              if (selectedFlete) {
                onAsignar(selectedFlete, Number(conductorId), Number(vehiculoId))
                setSelectedFlete(null)
              }
            }}
            sx={{ textTransform: 'none', bgcolor: '#1A1A1A', '&:hover': { bgcolor: '#1A1A1A' } }}
          >
            Asignar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ── Tab 3: Enturnamiento ──────────────────────────────────────────────────────

function TabEnturnamiento({ conductores, fletesPendientes }: {
  conductores: Conductor[]
  fletesPendientes: Flete[]
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    conductor_id: '', ciudad_disponible: '', fecha_hora_disponible: '',
    tipo_vehiculo: '', tipo_carroceria: '', notas: '',
  })
  const [asignarDialog, setAsignarDialog] = useState<Enturnamiento | null>(null)
  const [fleteSeleccionado, setFleteSeleccionado] = useState('')

  const { data: enturnados = [], isLoading } = useQuery<Enturnamiento[]>({
    queryKey: ['enturnamiento'],
    queryFn: () => api.get('/fletes/enturnamiento/?estado=ACTIVO').then(r => r.data),
  })

  const crearMut = useMutation({
    mutationFn: (data: object) => api.post('/fletes/enturnamiento/', data).then(r => r.data),
    onSuccess: () => {
      toast.success('Conductor enturnado exitosamente')
      setForm({ conductor_id: '', ciudad_disponible: '', fecha_hora_disponible: '', tipo_vehiculo: '', tipo_carroceria: '', notas: '' })
      qc.invalidateQueries({ queryKey: ['enturnamiento'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg ?? 'Error al enturnar conductor')
    },
  })

  const inactivarMut = useMutation({
    mutationFn: (id: number) => api.patch(`/fletes/enturnamiento/${id}/inactivar`).then(r => r.data),
    onSuccess: () => { toast.success('Enturnamiento inactivado'); qc.invalidateQueries({ queryKey: ['enturnamiento'] }) },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al inactivar')),
  })

  const asignarMut = useMutation({
    mutationFn: ({ id, fleteId }: { id: number; fleteId: number }) =>
      api.patch(`/fletes/enturnamiento/${id}/asignar-flete`, { flete_id: fleteId }).then(r => r.data),
    onSuccess: () => {
      toast.success('Conductor asignado al flete')
      setAsignarDialog(null)
      setFleteSeleccionado('')
      qc.invalidateQueries({ queryKey: ['enturnamiento'] })
      qc.invalidateQueries({ queryKey: ['fletes'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg ?? 'Error al asignar')
    },
  })

  const handleSubmitEnturnar = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.conductor_id || !form.ciudad_disponible || !form.fecha_hora_disponible) {
      toast.error('Completa conductor, ciudad y fecha/hora de disponibilidad')
      return
    }
    const payload: Record<string, unknown> = {
      conductor_id: Number(form.conductor_id),
      ciudad_disponible: form.ciudad_disponible,
      fecha_hora_disponible: form.fecha_hora_disponible,
    }
    if (form.tipo_vehiculo) payload.tipo_vehiculo = form.tipo_vehiculo
    if (form.tipo_carroceria) payload.tipo_carroceria = form.tipo_carroceria
    if (form.notas) payload.notas = form.notas
    crearMut.mutate(payload)
  }

  return (
    <Grid container spacing={3}>
      {/* Formulario de enturnamiento */}
      <Grid size={{ xs: 12, md: 4 }}>
        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 2.5 }}>
          <Typography fontSize={14} fontWeight={700} mb={2.5} color="text.primary">
            Registrar Disponibilidad
          </Typography>
          <Box component="form" onSubmit={handleSubmitEnturnar}>
            <Stack gap={2}>
              <TextField
                select label="Conductor *" size="small" fullWidth
                value={form.conductor_id} onChange={e => setForm(f => ({ ...f, conductor_id: e.target.value }))}
              >
                <MenuItem value=""><em>Seleccionar</em></MenuItem>
                {conductores.map(c => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.nombre} {c.apellido}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Ciudad Disponible *" size="small" fullWidth
                value={form.ciudad_disponible} onChange={e => setForm(f => ({ ...f, ciudad_disponible: e.target.value }))}
              />
              <TextField
                label="Disponible desde *" type="datetime-local" size="small" fullWidth
                InputLabelProps={{ shrink: true }}
                value={form.fecha_hora_disponible} onChange={e => setForm(f => ({ ...f, fecha_hora_disponible: e.target.value }))}
              />
              <TextField
                select label="Tipo de Vehículo" size="small" fullWidth
                value={form.tipo_vehiculo} onChange={e => setForm(f => ({ ...f, tipo_vehiculo: e.target.value }))}
              >
                <MenuItem value=""><em>Cualquiera</em></MenuItem>
                {TIPOS_VEHICULO.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
              </TextField>
              <TextField
                select label="Tipo de Carrocería" size="small" fullWidth
                value={form.tipo_carroceria} onChange={e => setForm(f => ({ ...f, tipo_carroceria: e.target.value }))}
              >
                <MenuItem value=""><em>Cualquiera</em></MenuItem>
                {TIPOS_CARROCERIA.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
              </TextField>
              <TextField
                label="Notas" size="small" fullWidth multiline rows={2}
                value={form.notas} onChange={e => setForm(f => ({ ...f, notas: e.target.value }))}
              />
              <Button
                type="submit" variant="contained" fullWidth
                disabled={crearMut.isPending}
                startIcon={crearMut.isPending ? <CircularProgress size={16} color="inherit" /> : <EnturnarIcon />}
                sx={{ borderRadius: '10px', textTransform: 'none', bgcolor: '#1A1A1A', '&:hover': { bgcolor: '#1A1A1A' } }}
              >
                Enturnar Conductor
              </Button>
            </Stack>
          </Box>
        </Paper>
      </Grid>

      {/* Lista de conductores enturnados */}
      <Grid size={{ xs: 12, md: 8 }}>
        <Typography fontSize={14} fontWeight={700} mb={2} color="text.primary">
          Conductores en Turno ({enturnados.length})
        </Typography>
        {isLoading ? (
          <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
        ) : enturnados.length === 0 ? (
          <Box textAlign="center" py={8}>
            <EnturnarIcon sx={{ fontSize: 48, color: '#D1D5DB', mb: 2 }} />
            <Typography color="text.secondary">No hay conductores en turno actualmente</Typography>
          </Box>
        ) : (
          <Stack gap={1.5}>
            {enturnados.map(e => (
              <Paper
                key={e.id}
                elevation={0}
                sx={{ border: '1px solid #E5E7EB', borderRadius: '12px', p: 2, display: 'flex', alignItems: 'center', gap: 2 }}
              >
                <Box
                  sx={{
                    width: 40, height: 40, borderRadius: '10px',
                    bgcolor: alpha('#1A1A1A', 0.12),
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}
                >
                  <TruckIcon sx={{ fontSize: 20, color: '#1A1A1A' }} />
                </Box>
                <Box flex={1} minWidth={0}>
                  <Typography fontWeight={700} fontSize={13}>
                    {e.conductor_nombre ?? `Conductor #${e.conductor_id}`}
                    {e.conductor_cedula ? <Typography component="span" fontSize={11} color="text.secondary"> — CC {e.conductor_cedula}</Typography> : null}
                  </Typography>
                  <Stack direction="row" gap={1.5} flexWrap="wrap" mt={0.25}>
                    <Typography fontSize={12} color="text.secondary">
                      📍 {e.ciudad_disponible}
                    </Typography>
                    <Typography fontSize={12} color="text.secondary">
                      🕐 {formatDateTime(e.fecha_hora_disponible)}
                    </Typography>
                    {e.tipo_vehiculo && (
                      <Chip label={tipoLabel(e.tipo_vehiculo)} size="small" sx={{ height: 18, fontSize: 10 }} />
                    )}
                    {e.tipo_carroceria && (
                      <Chip label={carroceriaLabel(e.tipo_carroceria)} size="small" variant="outlined" sx={{ height: 18, fontSize: 10 }} />
                    )}
                  </Stack>
                </Box>
                <Stack direction="row" gap={1}>
                  <Button
                    size="small"
                    variant="outlined"
                    color="primary"
                    startIcon={<AsignacionIcon />}
                    onClick={() => { setAsignarDialog(e); setFleteSeleccionado('') }}
                    sx={{ borderRadius: '8px', fontSize: 11, textTransform: 'none', whiteSpace: 'nowrap' }}
                  >
                    Asignar Flete
                  </Button>
                  <Tooltip title="Inactivar enturnamiento">
                    <IconButton
                      size="small" color="error"
                      onClick={() => inactivarMut.mutate(e.id)}
                      disabled={inactivarMut.isPending}
                    >
                      <CancelIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </Paper>
            ))}
          </Stack>
        )}
      </Grid>

      {/* Dialog asignar flete a enturnado */}
      <Dialog open={!!asignarDialog} onClose={() => setAsignarDialog(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>
          Asignar Flete a {asignarDialog?.conductor_nombre}
        </DialogTitle>
        <DialogContent>
          <Stack gap={2} pt={1}>
            {fletesPendientes.length === 0 ? (
              <Alert severity="warning">No hay fletes pendientes de asignación</Alert>
            ) : (
              <TextField
                select label="Flete Pendiente" size="small" fullWidth
                value={fleteSeleccionado} onChange={e => setFleteSeleccionado(e.target.value)}
              >
                <MenuItem value=""><em>Seleccionar flete</em></MenuItem>
                {fletesPendientes.map(f => (
                  <MenuItem key={f.id} value={String(f.id)}>
                    #{f.id} — {f.ciudad_origen} → {f.ciudad_destino} ({tipoLabel(f.tipo_vehiculo)})
                  </MenuItem>
                ))}
              </TextField>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          <Button size="small" onClick={() => setAsignarDialog(null)} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button
            size="small" variant="contained"
            disabled={!fleteSeleccionado || fletesPendientes.length === 0 || asignarMut.isPending}
            onClick={() => {
              if (asignarDialog && fleteSeleccionado) {
                asignarMut.mutate({ id: asignarDialog.id, fleteId: Number(fleteSeleccionado) })
              }
            }}
            sx={{ textTransform: 'none', bgcolor: '#1A1A1A', '&:hover': { bgcolor: '#1A1A1A' } }}
          >
            Asignar
          </Button>
        </DialogActions>
      </Dialog>
    </Grid>
  )
}

// ── Página Principal ──────────────────────────────────────────────────────────

export default function Fletes() {
  const [tab, setTab] = useState(0)
  const qc = useQueryClient()

  const { data: fletes = [], isLoading: loadingFletes } = useQuery<Flete[]>({
    queryKey: ['fletes'],
    queryFn: () => api.get('/fletes/').then(r => r.data),
  })

  const { data: generadores = [] } = useQuery<GeneradorCarga[]>({
    queryKey: ['fletes-generadores'],
    queryFn: () => api.get('/fletes/generadores/').then(r => r.data),
  })

  const { data: conductores = [] } = useQuery<Conductor[]>({
    queryKey: ['conductores'],
    queryFn: () => api.get('/fletes/conductores/').then(r => r.data),
  })

  const asignarMut = useMutation({
    mutationFn: ({ fleteId, conductorId, vehiculoId }: { fleteId: number; conductorId: number; vehiculoId: number }) =>
      api.patch(`/fletes/${fleteId}/asignar`, { conductor_id: conductorId, vehiculo_flete_id: vehiculoId }).then(r => r.data),
    onSuccess: () => { toast.success('Conductor asignado al flete'); qc.invalidateQueries({ queryKey: ['fletes'] }) },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg ?? 'Error al asignar conductor')
    },
  })

  const estadoMut = useMutation({
    mutationFn: ({ fleteId, estado }: { fleteId: number; estado: string }) =>
      api.patch(`/fletes/${fleteId}/estado?estado=${estado}`).then(r => r.data),
    onSuccess: (_, vars) => {
      toast.success(`Flete marcado como ${ESTADO_LABELS[vars.estado] ?? vars.estado}`)
      qc.invalidateQueries({ queryKey: ['fletes'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al cambiar estado')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/fletes/${id}`),
    onSuccess: () => { toast.success('Flete eliminado'); qc.invalidateQueries({ queryKey: ['fletes'] }) },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al eliminar flete')),
  })

  const fletesPendientes = fletes.filter(f => f.estado === 'PENDIENTE')

  // KPIs rápidos
  const kpis = [
    { label: 'Total',      count: fletes.length,                                     color: '#6366F1' },
    { label: 'Pendientes', count: fletes.filter(f => f.estado === 'PENDIENTE').length, color: '#F59E0B' },
    { label: 'Asignados',  count: fletes.filter(f => f.estado === 'ASIGNADO').length,  color: '#3B82F6' },
    { label: 'En Curso',   count: fletes.filter(f => f.estado === 'EN_CURSO').length,  color: '#8B5CF6' },
    { label: 'Completados', count: fletes.filter(f => f.estado === 'COMPLETADO').length, color: '#1A1A1A' },
  ]

  return (
    <Layout title="Módulo de Fletes">
      {/* KPIs */}
      <Grid container spacing={2} mb={3}>
        {kpis.map(kpi => (
          <Grid key={kpi.label} size={{ xs: 6, sm: 4, md: 2.4 }}>
            <Paper
              elevation={0}
              sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 2, textAlign: 'center' }}
            >
              <Typography fontSize={26} fontWeight={800} color={kpi.color} lineHeight={1}>
                {kpi.count}
              </Typography>
              <Typography fontSize={12} color="text.secondary" mt={0.5}>{kpi.label}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      {/* Tabs */}
      <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '16px', overflow: 'hidden' }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{
            borderBottom: '1px solid #E5E7EB',
            '& .MuiTab-root': { textTransform: 'none', fontSize: 13.5, fontWeight: 500, minHeight: 52 },
            '& .Mui-selected': { fontWeight: 700, color: '#1A1A1A' },
            '& .MuiTabs-indicator': { bgcolor: '#1A1A1A' },
          }}
        >
          <Tab icon={<AddIcon sx={{ fontSize: 18 }} />} iconPosition="start" label="Registrar Flete" />
          <Tab
            icon={<TruckIcon sx={{ fontSize: 18 }} />}
            iconPosition="start"
            label={`Asignación de Viajes${fletes.length ? ` (${fletes.length})` : ''}`}
          />
          <Tab icon={<EnturnarIcon sx={{ fontSize: 18 }} />} iconPosition="start" label="Enturnamiento" />
        </Tabs>

        <Box p={3}>
          {tab === 0 && (
            <TabRegistrar
              generadores={generadores}
              conductores={conductores}
              onSuccess={() => setTab(1)}
            />
          )}
          {tab === 1 && (
            loadingFletes ? (
              <Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box>
            ) : (
              <TabAsignacion
                fletes={fletes}
                conductores={conductores}
                onAsignar={(flete, conductorId, vehiculoId) =>
                  asignarMut.mutate({ fleteId: flete.id, conductorId, vehiculoId })
                }
                onEstado={(fleteId, estado) => estadoMut.mutate({ fleteId, estado })}
                onDelete={(id) => deleteMut.mutate(id)}
              />
            )
          )}
          {tab === 2 && (
            <TabEnturnamiento
              conductores={conductores}
              fletesPendientes={fletesPendientes}
            />
          )}
        </Box>
      </Paper>
    </Layout>
  )
}
