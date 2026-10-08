import React, { useState, useMemo } from 'react'
import {
  Box, Card, CardContent, Typography, Stack, Chip, Button, InputAdornment, MenuItem, InputLabel, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Paper, Divider, alpha, Alert, Avatar, CircularProgress,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Search,
  PersonOutline,
  DirectionsCar,
  Close,
  Warning,
  CalendarToday,
  Phone,
  LocationOn,
  Assignment,
  CheckCircle,
  ErrorOutline,
  Badge,
  Add,
  Edit,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'
import { ConductorFormDialog } from '@/components/tms/ConductorForm'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO

// ─── Types (reales, desde /tms/conductores y /tms/viajes) ─────────────────────

interface ConductorApi {
  id: number
  colaborador_id: number
  colaborador_nombre?: string | null
  colaborador_documento?: string | null
  colaborador_codigo?: string | null
  colaborador_telefono?: string | null
  colaborador_ciudad?: string | null
  tipo_documento?: string | null
  nombres?: string | null
  apellidos?: string | null
  email?: string | null
  fecha_expedicion_licencia?: string | null
  num_licencia: string
  tipo_licencia: string
  fecha_vencimiento_licencia: string
  restricciones?: string | null
  anos_experiencia: number
  activo_conduccion: boolean
  vehiculos_tipos: string[]
  coberturas: string[]
  documentos_count: number
  dias_hasta_vencimiento: number
}

interface ViajeApi {
  id: number
  codigo: string
  estado: string
  conductor_hcm_id?: number | null
  vehiculo_placa?: string | null
  origen_ciudad?: string | null
  destino_ciudad?: string | null
  fecha_programada_cargue?: string | null
}

type EstadoLaboral = 'EN_RUTA' | 'DISPONIBLE' | 'INACTIVO'

const ESTADOS_ACTIVOS_VIAJE = new Set(['ASIGNADO', 'EN_TRANSITO'])

// ─── Helpers ──────────────────────────────────────────────────────────────────

function diasHastaVencimiento(isoDate: string): number {
  const target = aFecha(isoDate)
  const hoy = new Date()
  hoy.setHours(0, 0, 0, 0)
  const diff = target.getTime() - hoy.getTime()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function getInitials(nombre: string): string {
  return nombre
    .split(' ')
    .slice(0, 2)
    .map((n) => n[0])
    .join('')
    .toUpperCase()
}

function estadoLaboralConfig(estado: EstadoLaboral) {
  switch (estado) {
    case 'DISPONIBLE':
      return { label: 'Disponible', color: '#16a34a', bg: alpha('#16a34a', 0.12) }
    case 'EN_RUTA':
      return { label: 'En Ruta', color: TMS_COLOR, bg: alpha(TMS_COLOR, 0.12) }
    case 'INACTIVO':
      return { label: 'Inactivo', color: '#9ca3af', bg: alpha('#9ca3af', 0.15) }
  }
}

function licenciaExpiryBadge(isoDate: string): { label: string; color: string; bg: string } | null {
  const dias = diasHastaVencimiento(isoDate)
  if (dias < 0) return { label: 'Vencida', color: '#dc2626', bg: alpha('#dc2626', 0.15) }
  if (dias < 30) return { label: 'Vence pronto', color: '#dc2626', bg: alpha('#dc2626', 0.12) }
  if (dias < 60) return { label: 'Por vencer', color: '#d97706', bg: alpha('#d97706', 0.12) }
  return null
}

function diasRestsChipColor(dias: number): { color: string; bg: string } {
  if (dias < 0) return { color: '#dc2626', bg: alpha('#dc2626', 0.12) }
  if (dias < 7) return { color: '#dc2626', bg: alpha('#dc2626', 0.12) }
  if (dias < 30) return { color: '#d97706', bg: alpha('#d97706', 0.12) }
  return { color: '#ca8a04', bg: alpha('#ca8a04', 0.12) }
}

function fmtFecha(s?: string | null): string {
  if (!s) return '—'
  const d = aFecha(s)
  return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KPICard({
  label,
  value,
  color,
  icon,
}: {
  label: string
  value: number
  color: string
  icon: React.ReactNode
}) {
  return (
    <Card
      sx={{
        flex: 1,
        minWidth: 150,
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: alpha(color, 0.25),
        borderRadius: 2,
      }}
    >
      <CardContent sx={{ p: '14px 18px !important' }}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Box
            sx={{
              width: 42,
              height: 42,
              borderRadius: 2,
              bgcolor: alpha(color, 0.15),
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color,
            }}
          >
            {icon}
          </Box>
          <Box>
            <Typography variant="h5" sx={{ color, fontWeight: 800, lineHeight: 1.1 }}>
              {value}
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
              {label}
            </Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}

// ─── Dialog: Asignar a Viaje ──────────────────────────────────────────────────

function AsignarViajeDialog({
  conductor,
  viajesDisponibles,
  open,
  onClose,
  onConfirm,
  saving,
}: {
  conductor: ConductorApi | null
  viajesDisponibles: ViajeApi[]
  open: boolean
  onClose: () => void
  onConfirm: (viajeId: number) => void
  saving: boolean
}) {
  const [viajeSeleccionado, setViajeSeleccionado] = useState<string>('')

  React.useEffect(() => {
    if (open) setViajeSeleccionado('')
  }, [open])

  if (!conductor) return null

  function handleConfirm() {
    if (!viajeSeleccionado) {
      toast.error('Seleccione un viaje disponible')
      return
    }
    onConfirm(Number(viajeSeleccionado))
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: '#E5E7EB', borderRadius: 3 } }}
    >
      <DialogTitle sx={{ color: '#1E293B', pb: 1 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Box
              sx={{
                width: 38, height: 38, borderRadius: 2, bgcolor: alpha(TMS_COLOR, 0.2),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Assignment sx={{ color: TMS_COLOR, fontSize: 20 }} />
            </Box>
            <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700 }}>
              Asignar a Viaje
            </Typography>
          </Stack>
          <IconButton onClick={onClose} sx={{ color: '#64748B' }}>
            <Close />
          </IconButton>
        </Stack>
      </DialogTitle>

      <DialogContent sx={{ px: 3 }}>
        <Box sx={{ bgcolor: '#F8FAFC', border: '1px solid', borderColor: '#E5E7EB', borderRadius: 2, p: 2, mb: 3 }}>
          <Stack direction="row" alignItems="center" spacing={2}>
            <Avatar sx={{ width: 48, height: 48, bgcolor: TMS_COLOR, color: '#fff', fontWeight: 700, fontSize: 16 }}>
              {getInitials(conductor.colaborador_nombre || '—')}
            </Avatar>
            <Box sx={{ flex: 1 }}>
              <Typography variant="body1" sx={{ color: '#1E293B', fontWeight: 700 }}>
                {conductor.colaborador_nombre}
              </Typography>
              <Chip
                label={`Cat. ${conductor.tipo_licencia}`}
                size="small"
                variant="outlined"
                sx={{ fontSize: 10, color: '#64748B', borderColor: '#E5E7EB', height: 20, mt: 0.4 }}
              />
            </Box>
          </Stack>
        </Box>

        {viajesDisponibles.length === 0 ? (
          <Alert severity="info">No hay viajes programados sin conductor asignado por ahora.</Alert>
        ) : (
          <FormControl fullWidth size="small">
            <InputLabel>Seleccionar Viaje Disponible</InputLabel>
            <Select
              value={viajeSeleccionado}
              label="Seleccionar Viaje Disponible"
              onChange={(e) => setViajeSeleccionado(e.target.value)}
            >
              {viajesDisponibles.map((v) => (
                <MenuItem key={v.id} value={String(v.id)} sx={{ fontSize: 13, py: 1.2 }}>
                  <Stack>
                    <Typography variant="body2" sx={{ fontWeight: 700, color: TMS_COLOR, fontSize: 13 }}>
                      {v.codigo}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
                      {v.origen_ciudad ?? '—'} → {v.destino_ciudad ?? '—'} · Cargue: {fmtFecha(v.fecha_programada_cargue)}
                    </Typography>
                  </Stack>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
        <Button onClick={onClose} variant="outlined" size="small" sx={{ color: '#64748B', borderColor: '#E5E7EB' }}>
          Cancelar
        </Button>
        <Button
          variant="contained"
          size="small"
          onClick={handleConfirm}
          disabled={saving || viajesDisponibles.length === 0}
          sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#0284c7' }, fontWeight: 700 }}
        >
          {saving ? 'Asignando...' : 'Confirmar Asignación'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Dialog: Detalle Conductor ─────────────────────────────────────────────────

function DetalleConductorDialog({
  conductor,
  estado,
  viajeActual,
  historial,
  open,
  onClose,
}: {
  conductor: ConductorApi | null
  estado: EstadoLaboral
  viajeActual: ViajeApi | null
  historial: ViajeApi[]
  open: boolean
  onClose: () => void
}) {
  if (!conductor) return null
  const estadoConfig = estadoLaboralConfig(estado)
  const expBadge = licenciaExpiryBadge(conductor.fecha_vencimiento_licencia)

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Avatar sx={{ width: 44, height: 44, bgcolor: TMS_COLOR, color: '#fff', fontWeight: 800 }}>
              {getInitials(conductor.colaborador_nombre || '—')}
            </Avatar>
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>{conductor.colaborador_nombre}</Typography>
              <Typography variant="caption" sx={{ color: '#64748B' }}>
                {conductor.colaborador_codigo ?? '—'} · CC {conductor.colaborador_documento ?? '—'}
              </Typography>
            </Box>
          </Stack>
          <IconButton onClick={onClose} size="small"><Close fontSize="small" /></IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction="row" spacing={1} mb={2.5} flexWrap="wrap" useFlexGap>
          <Chip label={estadoConfig.label} size="small" sx={{ bgcolor: estadoConfig.bg, color: estadoConfig.color, fontWeight: 700 }} />
          <Chip label={`Licencia Cat. ${conductor.tipo_licencia}`} size="small" variant="outlined" />
          {expBadge && <Chip label={expBadge.label} size="small" sx={{ bgcolor: expBadge.bg, color: expBadge.color, fontWeight: 700 }} />}
          {!conductor.activo_conduccion && <Chip label="Conducción inactiva" size="small" color="default" />}
        </Stack>

        <Grid container spacing={2} mb={2.5}>
          {[
            { label: 'N° Licencia', value: conductor.num_licencia },
            { label: 'Vence', value: fmtFecha(conductor.fecha_vencimiento_licencia) },
            { label: 'Años experiencia', value: String(conductor.anos_experiencia) },
            { label: 'Ciudad', value: conductor.colaborador_ciudad ?? '—' },
            { label: 'Teléfono', value: conductor.colaborador_telefono ?? '—' },
            { label: 'Documentos registrados', value: String(conductor.documentos_count) },
          ].map((f) => (
            <Grid key={f.label} size={{ xs: 6 }}>
              <Typography variant="caption" sx={{ color: '#64748B', display: 'block' }}>{f.label}</Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{f.value}</Typography>
            </Grid>
          ))}
        </Grid>

        {conductor.vehiculos_tipos.length > 0 && (
          <Box mb={2}>
            <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mb: 0.5 }}>Habilitado para conducir</Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {conductor.vehiculos_tipos.map((t) => <Chip key={t} label={t.replace(/_/g, ' ')} size="small" variant="outlined" />)}
            </Stack>
          </Box>
        )}

        {viajeActual && (
          <Box sx={{ bgcolor: alpha(TMS_COLOR, 0.06), border: '1px solid', borderColor: alpha(TMS_COLOR, 0.2), borderRadius: 2, p: 1.5, mb: 2 }}>
            <Typography variant="caption" sx={{ color: TMS_COLOR, fontWeight: 700, display: 'block', mb: 0.3 }}>Viaje en curso</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>{viajeActual.codigo}</Typography>
            <Typography variant="caption" sx={{ color: '#64748B' }}>
              {viajeActual.origen_ciudad ?? '—'} → {viajeActual.destino_ciudad ?? '—'} · {viajeActual.vehiculo_placa ?? '—'}
            </Typography>
          </Box>
        )}

        <Divider sx={{ my: 1.5 }} />
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Últimos viajes</Typography>
        {historial.length === 0 ? (
          <Typography variant="body2" sx={{ color: '#94A3B8', py: 1 }}>Sin viajes registrados aún</Typography>
        ) : (
          <Stack spacing={0.75}>
            {historial.slice(0, 5).map((v) => (
              <Stack key={v.id} direction="row" justifyContent="space-between" alignItems="center" sx={{ fontSize: 12 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, color: TMS_COLOR, fontSize: 12 }}>{v.codigo}</Typography>
                <Typography variant="caption" sx={{ color: '#64748B' }}>
                  {v.origen_ciudad ?? '—'} → {v.destino_ciudad ?? '—'}
                </Typography>
                <Chip label={v.estado.replace(/_/g, ' ')} size="small" sx={{ fontSize: 10, height: 20 }} />
              </Stack>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Driver Card ──────────────────────────────────────────────────────────────

function ConductorCard({
  conductor,
  estado,
  viajeActual,
  onAsignar,
  onVerDetalle,
  onEditar,
}: {
  conductor: ConductorApi
  estado: EstadoLaboral
  viajeActual: ViajeApi | null
  onAsignar: (c: ConductorApi) => void
  onVerDetalle: (c: ConductorApi) => void
  onEditar: (c: ConductorApi) => void
}) {
  const estadoConfig = estadoLaboralConfig(estado)
  const expBadge = licenciaExpiryBadge(conductor.fecha_vencimiento_licencia)

  return (
    <Card
      onClick={() => onVerDetalle(conductor)}
      sx={{
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: '#E5E7EB',
        borderRadius: 2.5,
        height: '100%',
        cursor: 'pointer',
        transition: 'border-color 0.2s',
        '&:hover': { borderColor: alpha(TMS_COLOR, 0.35) },
      }}
    >
      <CardContent sx={{ p: '20px !important' }}>
        <Stack direction="row" alignItems="flex-start" spacing={1.5} mb={2}>
          <Avatar sx={{ width: 56, height: 56, bgcolor: TMS_COLOR, color: '#fff', fontWeight: 800, fontSize: 18, flexShrink: 0 }}>
            {getInitials(conductor.colaborador_nombre || '—')}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body1" sx={{ color: '#1E293B', fontWeight: 700, fontSize: 14, lineHeight: 1.3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {conductor.colaborador_nombre ?? `Conductor #${conductor.id}`}
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
              {conductor.colaborador_codigo ?? '—'} · CC {conductor.colaborador_documento ?? '—'}
            </Typography>
            <Stack direction="row" alignItems="center" spacing={0.8} mt={0.8} flexWrap="wrap" useFlexGap>
              <Chip label={`Cat. ${conductor.tipo_licencia}`} size="small" variant="outlined" sx={{ fontSize: 10, height: 20, color: TMS_COLOR, borderColor: alpha(TMS_COLOR, 0.4) }} />
              <Chip label={estadoConfig.label} size="small" sx={{ bgcolor: estadoConfig.bg, color: estadoConfig.color, fontWeight: 700, fontSize: 10, height: 20 }} />
            </Stack>
          </Box>
          <IconButton size="small" aria-label="Editar conductor" onClick={(e) => { e.stopPropagation(); onEditar(conductor) }}
            sx={{ color: '#64748B', '&:hover': { color: TMS_COLOR, bgcolor: alpha(TMS_COLOR, 0.08) } }}>
            <Edit sx={{ fontSize: 18 }} />
          </IconButton>
        </Stack>

        <Divider sx={{ borderColor: '#E5E7EB', mb: 1.5 }} />

        <Stack spacing={1} mb={1.5}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <DirectionsCar sx={{ fontSize: 14, color: '#6b7280', flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
              {conductor.anos_experiencia} años de experiencia
            </Typography>
          </Stack>

          <Stack direction="row" alignItems="center" spacing={1}>
            <LocationOn sx={{ fontSize: 14, color: '#6b7280', flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
              {conductor.colaborador_ciudad ?? '—'}
            </Typography>
          </Stack>

          <Stack direction="row" alignItems="center" spacing={1}>
            <Phone sx={{ fontSize: 14, color: '#6b7280', flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
              {conductor.colaborador_telefono ?? '—'}
            </Typography>
          </Stack>

          <Stack direction="row" alignItems="center" spacing={1}>
            <CalendarToday sx={{ fontSize: 14, color: '#6b7280', flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
              Licencia vence: {fmtFecha(conductor.fecha_vencimiento_licencia)}
            </Typography>
            {expBadge && (
              <Chip label={expBadge.label} size="small" sx={{ bgcolor: expBadge.bg, color: expBadge.color, fontWeight: 700, fontSize: 9, height: 18, ml: 0.5 }} />
            )}
          </Stack>

          {viajeActual && (
            <Box sx={{ bgcolor: alpha(TMS_COLOR, 0.08), border: '1px solid', borderColor: alpha(TMS_COLOR, 0.2), borderRadius: 1.5, px: 1.2, py: 0.6 }}>
              <Typography variant="caption" sx={{ color: TMS_COLOR, fontWeight: 700, fontSize: 11 }}>
                En viaje: {viajeActual.codigo}
              </Typography>
            </Box>
          )}
        </Stack>

        <Stack direction="row" spacing={1} mt={2} onClick={(e) => e.stopPropagation()}>
          <Button
            variant="contained"
            size="small"
            fullWidth
            disabled={estado !== 'DISPONIBLE'}
            onClick={() => onAsignar(conductor)}
            sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#0284c7' }, '&.Mui-disabled': { bgcolor: '#E5E7EB', color: '#94A3B8' }, fontWeight: 700, fontSize: 11 }}
          >
            Asignar a Viaje
          </Button>
          <Button
            variant="outlined"
            size="small"
            fullWidth
            endIcon={<Badge sx={{ fontSize: 12 }} />}
            onClick={() => onVerDetalle(conductor)}
            sx={{ color: '#64748B', borderColor: '#E5E7EB', '&:hover': { borderColor: '#64748B', bgcolor: '#F8FAFC' }, fontSize: 11 }}
          >
            Ver Detalle
          </Button>
        </Stack>
      </CardContent>
    </Card>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function TMSConductores() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [filterEstado, setFilterEstado] = useState<EstadoLaboral | ''>('')

  const [asignarOpen, setAsignarOpen] = useState(false)
  const [detalleOpen, setDetalleOpen] = useState(false)
  const [conductorSeleccionado, setConductorSeleccionado] = useState<ConductorApi | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [conductorEditar, setConductorEditar] = useState<ConductorApi | null>(null)

  const { data: conductores = [], isLoading } = useQuery<ConductorApi[]>({
    // Todos, activos e inactivos: desde aquí también se reactivan.
    queryKey: ['tms-conductores'],
    queryFn: () => apiClient.get('/tms/conductores').then((r) => r.data),
  })

  const { data: viajesResp } = useQuery<{ items: ViajeApi[] }>({
    queryKey: ['tms-viajes-conductores'],
    queryFn: () => apiClient.get('/tms/viajes', { params: { per_page: 100 } }).then((r) => r.data),
  })
  const viajes = viajesResp?.items ?? []

  // Viaje activo por conductor (ASIGNADO / EN_TRANSITO)
  const viajeActivoPorConductor = useMemo(() => {
    const map = new Map<number, ViajeApi>()
    for (const v of viajes) {
      if (v.conductor_hcm_id && ESTADOS_ACTIVOS_VIAJE.has(v.estado)) {
        map.set(v.conductor_hcm_id, v)
      }
    }
    return map
  }, [viajes])

  // Historial de viajes por conductor (todos, orden ya viene desc por id)
  const historialPorConductor = useMemo(() => {
    const map = new Map<number, ViajeApi[]>()
    for (const v of viajes) {
      if (!v.conductor_hcm_id) continue
      const arr = map.get(v.conductor_hcm_id) ?? []
      arr.push(v)
      map.set(v.conductor_hcm_id, arr)
    }
    return map
  }, [viajes])

  // Viajes programados sin conductor asignado, disponibles para asignar
  const viajesDisponibles = useMemo(
    () => viajes.filter((v) => v.estado === 'PROGRAMADO' && !v.conductor_hcm_id),
    [viajes],
  )

  function estadoDe(c: ConductorApi): EstadoLaboral {
    if (viajeActivoPorConductor.has(c.id)) return 'EN_RUTA'
    return c.activo_conduccion ? 'DISPONIBLE' : 'INACTIVO'
  }

  const filtered = useMemo(() => {
    return conductores.filter((c) => {
      const q = search.toLowerCase()
      const matchSearch =
        !q ||
        (c.colaborador_nombre ?? '').toLowerCase().includes(q) ||
        (c.colaborador_documento ?? '').includes(q)
      const matchEstado = !filterEstado || estadoDe(c) === filterEstado
      return matchSearch && matchEstado
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conductores, search, filterEstado, viajeActivoPorConductor])

  const kpis = useMemo(
    () => ({
      total: conductores.filter((c) => c.activo_conduccion).length,
      enRuta: conductores.filter((c) => estadoDe(c) === 'EN_RUTA').length,
      disponibles: conductores.filter((c) => estadoDe(c) === 'DISPONIBLE').length,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [conductores, viajeActivoPorConductor],
  )

  const alertasDocumentos = useMemo(() => {
    return conductores
      .map((c) => ({ conductor: c, dias: diasHastaVencimiento(c.fecha_vencimiento_licencia) }))
      .filter(({ dias }) => dias < 60)
      .sort((a, b) => a.dias - b.dias)
  }, [conductores])

  const asignarMutation = useMutation({
    mutationFn: ({ viajeId, conductorId }: { viajeId: number; conductorId: number }) =>
      apiClient.put(`/tms/viajes/${viajeId}`, { conductor_hcm_id: conductorId }),
    onSuccess: (_data, vars) => {
      toast.success('Conductor asignado al viaje exitosamente')
      qc.invalidateQueries({ queryKey: ['tms-viajes-conductores'] })
      qc.invalidateQueries({ queryKey: ['tms-viajes'] })
      setAsignarOpen(false)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Error al asignar el viaje'),
  })

  function handleAsignar(conductor: ConductorApi) {
    setConductorSeleccionado(conductor)
    setAsignarOpen(true)
  }

  function abrirNuevo() {
    setConductorEditar(null)
    setFormOpen(true)
  }

  function abrirEditar(conductor: ConductorApi) {
    setConductorEditar(conductor)
    setFormOpen(true)
  }

  function handleVerDetalle(conductor: ConductorApi) {
    setConductorSeleccionado(conductor)
    setDetalleOpen(true)
  }

  function handleConfirmarAsignacion(viajeId: number) {
    if (!conductorSeleccionado) return
    asignarMutation.mutate({ viajeId, conductorId: conductorSeleccionado.id })
  }

  return (
    <Layout>
      <Box sx={{ minHeight: '100%', bgcolor: '#F0F2F5', p: 3 }}>
        {/* Header */}
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" mb={3}>
          <Box>
            <Stack direction="row" alignItems="center" spacing={1.5} mb={0.3}>
              <Box sx={{ width: 36, height: 36, borderRadius: 2, bgcolor: alpha(TMS_COLOR, 0.2), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <PersonOutline sx={{ color: TMS_COLOR, fontSize: 20 }} />
              </Box>
              <Box>
                <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700, lineHeight: 1.2 }}>
                  Conductores TMS
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
                  TMS — Registro de conductores y asignación a viajes
                </Typography>
              </Box>
            </Stack>
          </Box>
          <Button variant="contained" startIcon={<Add />} onClick={abrirNuevo}
            sx={{ textTransform: 'none', fontWeight: 700, borderRadius: 2 }}>
            Nuevo conductor
          </Button>
        </Stack>

        <Alert
          severity="info"
          sx={{ mb: 3, bgcolor: alpha('#0ea5e9', 0.08), border: '1px solid', borderColor: alpha('#0ea5e9', 0.25), color: '#0369A1', '& .MuiAlert-icon': { color: '#0284c7' }, fontSize: 13 }}
        >
          Registre aquí a sus conductores con su licencia y los vehículos que puede manejar. Los conductores
          <strong> activos</strong> con licencia vigente quedan disponibles en la <strong>planeación de viajes</strong>.
        </Alert>

        <Stack direction="row" spacing={1.5} mb={3} flexWrap="wrap" useFlexGap>
          <KPICard label="Conductores Activos" value={kpis.total} color={TMS_COLOR} icon={<PersonOutline sx={{ fontSize: 20 }} />} />
          <KPICard label="En Ruta" value={kpis.enRuta} color="#2563eb" icon={<DirectionsCar sx={{ fontSize: 20 }} />} />
          <KPICard label="Disponibles" value={kpis.disponibles} color="#16a34a" icon={<CheckCircle sx={{ fontSize: 20 }} />} />
        </Stack>

        <Stack direction="row" spacing={1.5} mb={2.5} flexWrap="wrap" useFlexGap alignItems="center">
          <TextField
            size="small"
            placeholder="Buscar por nombre o cédula..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ flex: 1, minWidth: 220 }}
            InputProps={{ startAdornment: <InputAdornment position="start"><Search sx={{ fontSize: 16, color: '#64748B' }} /></InputAdornment> }}
          />
          <FormControl size="small" sx={{ minWidth: 190 }}>
            <InputLabel>Estado Laboral</InputLabel>
            <Select value={filterEstado} label="Estado Laboral" onChange={(e) => setFilterEstado(e.target.value as EstadoLaboral | '')}>
              <MenuItem value="" sx={{ fontSize: 13 }}>Todos los estados</MenuItem>
              <MenuItem value="DISPONIBLE" sx={{ fontSize: 13 }}>Disponible</MenuItem>
              <MenuItem value="EN_RUTA" sx={{ fontSize: 13 }}>En Ruta</MenuItem>
              <MenuItem value="INACTIVO" sx={{ fontSize: 13 }}>Inactivo</MenuItem>
            </Select>
          </FormControl>
          <Typography variant="caption" sx={{ color: '#64748B', fontSize: 12, whiteSpace: 'nowrap' }}>
            {filtered.length} de {conductores.length} conductores
          </Typography>
        </Stack>

        {isLoading ? (
          <Box sx={{ textAlign: 'center', py: 8 }}><CircularProgress size={28} /></Box>
        ) : filtered.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="body2" sx={{ color: '#64748B' }}>
              {conductores.length === 0 ? 'Aún no hay conductores. Use «Nuevo conductor» para registrar el primero.' : 'No se encontraron conductores con los filtros aplicados'}
            </Typography>
          </Box>
        ) : (
          <Grid container spacing={2} mb={4}>
            {filtered.map((conductor) => (
              <Grid key={conductor.id} size={{ xs: 12, sm: 6, md: 4 }}>
                <ConductorCard
                  conductor={conductor}
                  estado={estadoDe(conductor)}
                  viajeActual={viajeActivoPorConductor.get(conductor.id) ?? null}
                  onAsignar={handleAsignar}
                  onVerDetalle={handleVerDetalle}
                  onEditar={abrirEditar}
                />
              </Grid>
            ))}
          </Grid>
        )}

        {/* Alertas de Documentos Section */}
        <Box mt={2}>
          <Stack direction="row" alignItems="center" spacing={1} mb={2}>
            <Box sx={{ width: 32, height: 32, borderRadius: 1.5, bgcolor: alpha('#d97706', 0.15), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Warning sx={{ color: '#d97706', fontSize: 18 }} />
            </Box>
            <Box>
              <Typography variant="subtitle1" sx={{ color: '#1E293B', fontWeight: 700, lineHeight: 1.2 }}>
                Alertas de Documentos
              </Typography>
              <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
                Conductores con licencia próxima a vencer (menos de 60 días)
              </Typography>
            </Box>
          </Stack>

          {alertasDocumentos.length === 0 ? (
            <Box sx={{ bgcolor: alpha('#16a34a', 0.06), border: '1px solid', borderColor: alpha('#16a34a', 0.2), borderRadius: 2, p: 2.5, textAlign: 'center' }}>
              <Stack direction="row" alignItems="center" justifyContent="center" spacing={1}>
                <CheckCircle sx={{ color: '#16a34a', fontSize: 20 }} />
                <Typography variant="body2" sx={{ color: '#16a34a', fontWeight: 600 }}>
                  Todos los documentos están en regla
                </Typography>
              </Stack>
            </Box>
          ) : (
            <Paper sx={{ bgcolor: 'background.paper', border: '1px solid', borderColor: '#E5E7EB', borderRadius: 2, overflow: 'hidden' }}>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#F8FAFC' }}>
                      {['Conductor', 'Documento', 'Fecha Vencimiento', 'Días Restantes', 'Estado'].map((h) => (
                        <TableCell key={h} sx={{ color: '#64748B', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, borderBottom: '1px solid #E5E7EB', py: 1.2, px: 2, whiteSpace: 'nowrap' }}>
                          {h}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {alertasDocumentos.map(({ conductor, dias }) => {
                      const chipColors = diasRestsChipColor(dias)
                      const estadoLabel = dias < 0 ? 'Vencida' : dias < 7 ? 'Crítico' : dias < 30 ? 'Urgente' : 'Por Vencer'

                      return (
                        <TableRow
                          key={conductor.id}
                          onClick={() => handleVerDetalle(conductor)}
                          sx={{ cursor: 'pointer', '&:hover': { bgcolor: '#F8FAFC' }, '&:last-child td': { borderBottom: 'none' } }}
                        >
                          <TableCell sx={{ borderBottom: '1px solid #E5E7EB', px: 2, py: 1.2 }}>
                            <Stack direction="row" alignItems="center" spacing={1.2}>
                              <Avatar sx={{ width: 28, height: 28, bgcolor: alpha(TMS_COLOR, 0.25), color: TMS_COLOR, fontSize: 10, fontWeight: 700 }}>
                                {getInitials(conductor.colaborador_nombre || '—')}
                              </Avatar>
                              <Box>
                                <Typography variant="body2" sx={{ color: '#1E293B', fontWeight: 600, fontSize: 12 }}>
                                  {conductor.colaborador_nombre}
                                </Typography>
                                <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>
                                  {conductor.colaborador_codigo ?? '—'}
                                </Typography>
                              </Box>
                            </Stack>
                          </TableCell>
                          <TableCell sx={{ color: '#334155', fontSize: 12, borderBottom: '1px solid #E5E7EB', px: 2, py: 1.2 }}>
                            <Stack direction="row" alignItems="center" spacing={0.5}>
                              <DirectionsCar sx={{ fontSize: 13, color: '#6b7280' }} />
                              <span>Licencia de Conducción Cat. {conductor.tipo_licencia}</span>
                            </Stack>
                          </TableCell>
                          <TableCell sx={{ color: '#64748B', fontSize: 12, borderBottom: '1px solid #E5E7EB', px: 2, py: 1.2 }}>
                            <Stack direction="row" alignItems="center" spacing={0.5}>
                              <CalendarToday sx={{ fontSize: 12, color: '#6b7280' }} />
                              <span>{fmtFecha(conductor.fecha_vencimiento_licencia)}</span>
                            </Stack>
                          </TableCell>
                          <TableCell sx={{ borderBottom: '1px solid #E5E7EB', px: 2, py: 1.2 }}>
                            <Stack direction="row" alignItems="center" spacing={0.5}>
                              {dias < 0 ? <ErrorOutline sx={{ fontSize: 14, color: '#dc2626' }} /> : <Warning sx={{ fontSize: 14, color: chipColors.color }} />}
                              <Typography variant="body2" sx={{ color: chipColors.color, fontWeight: 700, fontSize: 12 }}>
                                {dias < 0 ? `Vencida hace ${Math.abs(dias)}d` : `${dias} días`}
                              </Typography>
                            </Stack>
                          </TableCell>
                          <TableCell sx={{ borderBottom: '1px solid #E5E7EB', px: 2, py: 1.2 }}>
                            <Chip label={estadoLabel} size="small" sx={{ bgcolor: chipColors.bg, color: chipColors.color, fontWeight: 700, fontSize: 10, height: 22 }} />
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          )}
        </Box>

        <AsignarViajeDialog
          conductor={conductorSeleccionado}
          viajesDisponibles={viajesDisponibles}
          open={asignarOpen}
          onClose={() => setAsignarOpen(false)}
          onConfirm={handleConfirmarAsignacion}
          saving={asignarMutation.isPending}
        />

        <ConductorFormDialog
          open={formOpen}
          conductor={conductorEditar}
          onClose={() => setFormOpen(false)}
        />

        <DetalleConductorDialog
          conductor={conductorSeleccionado}
          estado={conductorSeleccionado ? estadoDe(conductorSeleccionado) : 'DISPONIBLE'}
          viajeActual={conductorSeleccionado ? viajeActivoPorConductor.get(conductorSeleccionado.id) ?? null : null}
          historial={conductorSeleccionado ? historialPorConductor.get(conductorSeleccionado.id) ?? [] : []}
          open={detalleOpen}
          onClose={() => setDetalleOpen(false)}
        />
      </Box>
    </Layout>
  )
}
