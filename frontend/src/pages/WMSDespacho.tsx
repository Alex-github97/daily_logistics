import React, { useState } from 'react'
import {
  Box, Paper, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, IconButton, Stack, Chip, Tooltip, CircularProgress, alpha, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Collapse, Divider, Alert,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Add as AddIcon,
  LocalShipping as TruckIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Assignment as AssignmentIcon,
  AssignmentReturn as ReturnIcon,
  Close as CloseIcon,
  ArrowForward as ArrowIcon,
  History as HistoryIcon,
  Undo as UndoIcon,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'
import SugerenciaVehiculo from '@/components/tms/SugerenciaVehiculo'
import { BotonPDF } from '@/components/comun/BotonPDF'
import { Layout } from '@/components/layout/Layout'
import { useAuthStore } from '@/store/authStore'
import toast from 'react-hot-toast'

import { COLOR_MODULO } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'
import { aFecha } from '@/utils/fechas'
const WMS_COLOR = COLOR_MODULO

// ─── Types ─────────────────────────────────────────────────────────────────────
interface Orden {
  id: number
  numero_orden: string
  estado: string
  cliente?: { nombre: string }
  almacen?: { nombre: string }
  detalles?: unknown[]
}
interface Transportadora { id: number; nombre: string; codigo?: string }
interface DespachoItem {
  id: number
  producto_id: number
  producto?: { sku: string; nombre: string; unidad_medida: string }
  lote_id?: number
  cantidad: number
  numero_tracking?: string
}
interface Despacho {
  id: number
  numero_despacho: string
  orden_id: number
  orden_numero?: string
  transportadora_id?: number
  transportadora_nombre?: string
  vehiculo_placa?: string
  conductor_nombre?: string
  fecha_despacho?: string
  fecha_entrega_estimada?: string
  fecha_entrega_real?: string
  estado: 'PREPARANDO' | 'LISTO' | 'EN_TRANSITO' | 'ENTREGADO' | 'INCIDENCIA'
  peso_total_kg?: number
  volumen_total_m3?: number
  notas?: string
  // Factura de venta del ERP; vacía con `aviso_factura` cuando no se pudo facturar al despachar.
  factura_id?: number | null
  factura_numero?: string | null
  aviso_factura?: string | null
  detalles?: DespachoItem[]
}
interface HistorialEntry {
  id: number
  estado_anterior: string | null
  estado_nuevo: string
  tipo_cambio: 'AVANCE' | 'CORRECCION'
  observacion: string | null
  usuario: string
  fecha: string
}
interface DevolucionItem {
  id?: number
  producto?: { sku: string; nombre: string }
  lote_id?: number
  cantidad?: number
  estado_calidad?: string
  accion?: string
  reingresado?: boolean
}
interface Devolucion {
  id: number
  numero_devolucion: string
  tipo: 'CLIENTE' | 'PROVEEDOR'
  estado: string
  motivo?: string
  fecha_recepcion?: string
  nota_credito_id?: number | null
  orden_referencia_id?: number
  cliente_id?: number
  proveedor_id?: number
  almacen_id?: number
  notas?: string
  detalles?: DevolucionItem[]
}
interface Almacen { id: number; nombre: string }
interface Cliente { id: number; nombre: string }
interface Proveedor { id: number; nombre: string }

// ─── State machine constants ────────────────────────────────────────────────────
const TRANS_NEXT: Record<string, Array<{ estado: string; label: string; color: string; outlined?: boolean }>> = {
  PREPARANDO:  [{ estado: 'LISTO', label: 'Listo para despachar', color: '#D97706' }],
  LISTO:       [{ estado: 'EN_TRANSITO', label: 'Iniciar tránsito', color: '#EA580C' }],
  EN_TRANSITO: [
    { estado: 'ENTREGADO',  label: 'Confirmar entrega',    color: '#059669' },
    { estado: 'INCIDENCIA', label: 'Registrar incidencia', color: '#DC2626', outlined: true },
  ],
  INCIDENCIA:  [{ estado: 'EN_TRANSITO', label: 'Resolver incidencia', color: '#7C3AED' }],
  ENTREGADO:   [],
}

const REVERT_MAP: Record<string, { estado: string; label: string }> = {
  LISTO:       { estado: 'PREPARANDO',   label: 'Volver a PREPARANDO (cancelar alistamiento)' },
  EN_TRANSITO: { estado: 'LISTO',        label: 'Volver a LISTO (cancelar salida en tránsito)' },
  ENTREGADO:   { estado: 'EN_TRANSITO',  label: 'Volver a EN TRÁNSITO (anular entrega registrada)' },
  INCIDENCIA:  { estado: 'EN_TRANSITO',  label: 'Volver a EN TRÁNSITO (corregir incidencia)' },
}

const ROLES_SUPERVISION = new Set(['ADMINISTRADOR', 'SUPERVISOR_LOGISTICO'])

// Estados de orden de salida elegibles para generar un despacho
const ORDEN_ESTADOS_DESPACHABLES = ['EMPACANDO', 'EN_PICKING']

// Extrae un mensaje legible del error de axios (incluye arrays de detalle 422)

// ─── Estado chip ───────────────────────────────────────────────────────────────
const ESTADO_CFG = {
  PREPARANDO:  { label: 'Preparando',   color: '#1E40AF', bg: '#DBEAFE' },
  LISTO:       { label: 'Listo',        color: '#92400E', bg: '#FEF3C7' },
  EN_TRANSITO: { label: 'En tránsito',  color: '#9A3412', bg: '#FFEDD5' },
  ENTREGADO:   { label: 'Entregado',    color: '#065F46', bg: '#D1FAE5' },
  INCIDENCIA:  { label: 'Incidencia',   color: '#991B1B', bg: '#FEE2E2' },
} as const

function EstadoChip({ estado }: { estado: Despacho['estado'] }) {
  const cfg = ESTADO_CFG[estado] ?? { label: estado, color: '#374151', bg: '#F3F4F6' }
  return (
    <Chip
      label={cfg.label}
      size="small"
      sx={{ bgcolor: cfg.bg, color: cfg.color, fontWeight: 700, fontSize: 11, height: 22 }}
    />
  )
}

// ─── Estado action button (table row) ─────────────────────────────────────────
function EstadoButton({ despacho, onTransition }: { despacho: Despacho; onTransition: (id: number, estado: string) => void }) {
  const nexts = TRANS_NEXT[despacho.estado] ?? []
  if (nexts.length === 0) {
    if (despacho.estado === 'ENTREGADO') return <CheckIcon sx={{ color: '#059669', fontSize: 18 }} />
    if (despacho.estado === 'INCIDENCIA') return <WarningIcon sx={{ color: '#DC2626', fontSize: 18 }} />
    return null
  }
  const first = nexts[0]
  return (
    <Button size="small" variant="outlined"
      sx={{ textTransform: 'none', fontSize: 11, borderColor: first.outlined ? first.color : alpha(first.color, 0.6), color: first.color }}
      onClick={e => { e.stopPropagation(); onTransition(despacho.id, first.estado) }}>
      {first.estado === 'EN_TRANSITO' && <TruckIcon sx={{ fontSize: 13, mr: 0.5 }} />}
      {first.estado === 'ENTREGADO' && <CheckIcon sx={{ fontSize: 13, mr: 0.5 }} />}
      {first.label}
    </Button>
  )
}

// ─── Summary cards ─────────────────────────────────────────────────────────────
function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <Paper elevation={0} sx={{ border: `1px solid ${alpha(color, 0.25)}`, borderRadius: '12px', p: 2, flex: 1, minWidth: 120 }}>
      <Typography fontSize={26} fontWeight={800} color={color} lineHeight={1}>{value}</Typography>
      <Typography fontSize={12} color="text.secondary" mt={0.5}>{label}</Typography>
    </Paper>
  )
}

// ─── Nuevo Despacho dialog form ────────────────────────────────────────────────
function NuevoDespachoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    orden_id: '', transportadora_id: '', vehiculo_placa: '', conductor_nombre: '',
    fecha_despacho: '', fecha_entrega_estimada: '', notas: '', gestion_transporte: 'NINGUNA',
  })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))
  // Vehículo del TMS sugerido por la carga de la orden (opcional).
  const [vehiculoTms, setVehiculoTms] = useState<number | ''>('')

  // El filtro va al servidor. Filtrando aquí se bajaba el año entero de órdenes
  // —3.258, con sus casi diez mil líneas— para quedarse con las que están en
  // alistamiento, que son unas decenas.
  const { data: ordenes = [], isError: ordenesError } = useQuery<Orden[]>({
    queryKey: ['wms-ordenes-despacho'],
    queryFn: () => api.get('/wms/ordenes-salida/', {
      params: { estado: ORDEN_ESTADOS_DESPACHABLES.join(','), limite: 200 },
    }).then(r => r.data),
    enabled: open,
  })
  const { data: transportadoras = [] } = useQuery<Transportadora[]>({
    queryKey: ['wms-transportadoras'],
    queryFn: () => api.get('/wms/transportadoras/').then(r => r.data),
    enabled: open,
  })

  const createMut = useMutation({
    mutationFn: (d: object) => api.post('/wms/despachos/', d).then(r => r.data),
    onSuccess: (desp: any) => {
      const n: string = desp?.notas || ''
      const m = n.match(/TMS \(([^)]+)\)/)
      toast.success(m ? `Despacho creado — viaje TMS ${m[1]} generado` : 'Despacho creado')
      if (desp?.factura_numero) toast.success(`Factura electrónica ${desp.factura_numero} emitida`)
      else if (desp?.aviso_factura) toast(`Sin factura todavía: ${desp.aviso_factura}`, { icon: '⚠️', duration: 8000 })
      qc.invalidateQueries({ queryKey: ['wms-despachos'] })
      onClose()
    },
    onError: (err: any) => toast.error(mensajeDeError(err, 'Error al crear despacho')),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.orden_id) { toast.error('Seleccione una orden'); return }
    const payload: Record<string, unknown> = {
      orden_id: Number(form.orden_id),
      transportadora_id: form.transportadora_id ? Number(form.transportadora_id) : undefined,
      vehiculo_placa: form.vehiculo_placa || undefined,
      conductor_nombre: form.conductor_nombre || undefined,
      fecha_despacho: form.fecha_despacho || undefined,
      fecha_entrega_estimada: form.fecha_entrega_estimada || undefined,
      notas: form.notas || undefined,
      gestion_transporte: form.gestion_transporte,
      tms_vehiculo_id: vehiculoTms || undefined,
    }
    createMut.mutate(payload)
  }

  const handleClose = () => {
    setForm({ orden_id: '', transportadora_id: '', vehiculo_placa: '', conductor_nombre: '', fecha_despacho: '', fecha_entrega_estimada: '', notas: '', gestion_transporte: 'NINGUNA' })
    setVehiculoTms('')
    onClose()
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
        Nuevo Despacho
        <Typography variant="caption" color="text.secondary" display="block">
          Genera un despacho a partir de una orden de salida en picking
        </Typography>
      </DialogTitle>
      <Box component="form" onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ pt: 0.5 }}>
            <Grid size={{ xs: 12 }}>
              <TextField select label="Orden *" fullWidth size="small" value={form.orden_id} onChange={e => { set('orden_id', e.target.value); setVehiculoTms('') }}
                error={ordenesError}
                helperText={ordenesError ? 'No se pudieron cargar las órdenes de salida' : 'Las líneas se derivan del picking confirmado'}>
                <MenuItem value="">Seleccione una orden</MenuItem>
                {ordenes.map(o => (
                  <MenuItem key={o.id} value={o.id.toString()}>
                    {o.numero_orden} — {o.estado}{o.cliente?.nombre ? ` · ${o.cliente.nombre}` : ''}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField select label="Transportadora" fullWidth size="small" value={form.transportadora_id} onChange={e => set('transportadora_id', e.target.value)}>
                <MenuItem value="">Sin transportadora</MenuItem>
                {transportadoras.map(t => <MenuItem key={t.id} value={t.id.toString()}>{t.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            {form.orden_id && (
              <Grid size={{ xs: 12 }}>
                <SugerenciaVehiculo fuente={{ orden_ids: [Number(form.orden_id)] }} seleccionado={vehiculoTms} onElegir={setVehiculoTms}
                  titulo="Carga de la orden y vehículo sugerido (elija uno de la flota o escriba una placa externa)" />
              </Grid>
            )}
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField label={vehiculoTms ? 'Placa (del vehículo elegido)' : 'Placa vehículo externo'} fullWidth size="small"
                value={vehiculoTms ? '' : form.vehiculo_placa} disabled={!!vehiculoTms} onChange={e => set('vehiculo_placa', e.target.value)}
                helperText={vehiculoTms ? 'Se toma del vehículo de la flota seleccionado' : undefined} />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField label="Conductor" fullWidth size="small" value={form.conductor_nombre} onChange={e => set('conductor_nombre', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField label="Fecha despacho" fullWidth size="small" type="date" value={form.fecha_despacho} onChange={e => set('fecha_despacho', e.target.value)} InputLabelProps={{ shrink: true }} />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField label="Entrega estimada" fullWidth size="small" type="date" value={form.fecha_entrega_estimada} onChange={e => set('fecha_entrega_estimada', e.target.value)} InputLabelProps={{ shrink: true }} />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField label="Notas" fullWidth size="small" multiline rows={2} value={form.notas} onChange={e => set('notas', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField select label="Gestión de transporte" fullWidth size="small" value={form.gestion_transporte} onChange={e => set('gestion_transporte', e.target.value)}>
                <MenuItem value="NINGUNA">No gestionar en la plataforma</MenuItem>
                <MenuItem value="TMS">Gestionar por TMS (crea viaje)</MenuItem>
              </TextField>
            </Grid>
            {form.gestion_transporte === 'TMS' && (
              <Grid size={{ xs: 12 }}>
                <Alert severity="info" sx={{ py: 0 }}>
                  Se creará un <b>viaje en TMS</b> vinculado a este despacho (origen: almacén de la orden; destino: ciudad del cliente).
                </Alert>
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button size="small" onClick={handleClose} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button type="submit" size="small" variant="contained" disabled={createMut.isPending}
            startIcon={createMut.isPending ? <CircularProgress size={12} color="inherit" /> : undefined}
            sx={{ textTransform: 'none', bgcolor: WMS_COLOR, '&:hover': { bgcolor: alpha(WMS_COLOR, 0.85) } }}>
            Crear
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  )
}

// ─── Nueva Devolución dialog ───────────────────────────────────────────────────
function NuevoDevolucionDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    tipo: 'CLIENTE', orden_referencia_id: '', cliente_id: '', proveedor_id: '',
    almacen_id: '', fecha_recepcion: '', motivo: '',
  })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const { data: almacenes = [] } = useQuery<Almacen[]>({ queryKey: ['wms-almacenes'], queryFn: () => api.get('/wms/almacenes/').then(r => r.data), enabled: open })
  const { data: clientes = [] } = useQuery<Cliente[]>({ queryKey: ['wms-clientes'], queryFn: () => api.get('/wms/clientes/').then(r => r.data), enabled: open })
  const { data: proveedores = [] } = useQuery<Proveedor[]>({ queryKey: ['wms-proveedores'], queryFn: () => api.get('/wms/proveedores/').then(r => r.data), enabled: open })
  const { data: ordenes = [], isError: ordenesError } = useQuery<Orden[]>({ queryKey: ['wms-ordenes-dev'], queryFn: () => api.get('/wms/ordenes-salida/', { params: { limite: 200 } }).then(r => r.data), enabled: open })

  const createMut = useMutation({
    mutationFn: (d: object) => api.post('/wms/devoluciones/', d).then(r => r.data),
    onSuccess: () => { toast.success('Devolución registrada'); qc.invalidateQueries({ queryKey: ['wms-devoluciones'] }); onClose() },
    onError: (err: any) => toast.error(mensajeDeError(err, 'Error al registrar devolución')),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.motivo.trim()) { toast.error('El motivo es obligatorio'); return }
    const payload: Record<string, unknown> = {
      tipo: form.tipo,
      motivo: form.motivo,
      almacen_id: form.almacen_id ? Number(form.almacen_id) : undefined,
      fecha_recepcion: form.fecha_recepcion || undefined,
      orden_referencia_id: form.orden_referencia_id ? Number(form.orden_referencia_id) : undefined,
      cliente_id: form.tipo === 'CLIENTE' && form.cliente_id ? Number(form.cliente_id) : undefined,
      proveedor_id: form.tipo === 'PROVEEDOR' && form.proveedor_id ? Number(form.proveedor_id) : undefined,
    }
    createMut.mutate(payload)
  }

  const handleClose = () => {
    setForm({ tipo: 'CLIENTE', orden_referencia_id: '', cliente_id: '', proveedor_id: '', almacen_id: '', fecha_recepcion: '', motivo: '' })
    onClose()
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
        Nueva Devolución
        <Typography variant="caption" color="text.secondary" display="block">
          Registra la recepción de una devolución de cliente o proveedor
        </Typography>
      </DialogTitle>
      <Box component="form" onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ pt: 0.5 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Tipo *" fullWidth size="small" value={form.tipo} onChange={e => set('tipo', e.target.value)}>
                <MenuItem value="CLIENTE">Cliente</MenuItem>
                <MenuItem value="PROVEEDOR">Proveedor</MenuItem>
              </TextField>
            </Grid>
            {form.tipo === 'CLIENTE' && (
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField select label="Cliente" fullWidth size="small" value={form.cliente_id} onChange={e => set('cliente_id', e.target.value)}>
                  <MenuItem value="">Sin cliente específico</MenuItem>
                  {clientes.map(c => <MenuItem key={c.id} value={c.id.toString()}>{c.nombre}</MenuItem>)}
                </TextField>
              </Grid>
            )}
            {form.tipo === 'PROVEEDOR' && (
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField select label="Proveedor" fullWidth size="small" value={form.proveedor_id} onChange={e => set('proveedor_id', e.target.value)}>
                  <MenuItem value="">Sin proveedor específico</MenuItem>
                  {proveedores.map(p => <MenuItem key={p.id} value={p.id.toString()}>{p.nombre}</MenuItem>)}
                </TextField>
              </Grid>
            )}
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Orden de referencia" fullWidth size="small" value={form.orden_referencia_id} onChange={e => set('orden_referencia_id', e.target.value)}
                error={ordenesError} helperText={ordenesError ? 'No se pudieron cargar las órdenes de salida' : undefined}>
                <MenuItem value="">Sin orden de referencia</MenuItem>
                {ordenes.map(o => <MenuItem key={o.id} value={o.id.toString()}>{o.numero_orden}{o.cliente?.nombre ? ` · ${o.cliente.nombre}` : ''}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Almacén destino" fullWidth size="small" value={form.almacen_id} onChange={e => set('almacen_id', e.target.value)}>
                <MenuItem value="">Sin almacén asignado</MenuItem>
                {almacenes.map(a => <MenuItem key={a.id} value={a.id.toString()}>{a.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField label="Fecha de recepción" fullWidth size="small" type="date" value={form.fecha_recepcion} onChange={e => set('fecha_recepcion', e.target.value)} InputLabelProps={{ shrink: true }} />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField label="Motivo *" fullWidth size="small" multiline rows={2} value={form.motivo} onChange={e => set('motivo', e.target.value)} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button size="small" onClick={handleClose} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button type="submit" size="small" variant="contained" disabled={createMut.isPending}
            startIcon={createMut.isPending ? <CircularProgress size={12} color="inherit" /> : undefined}
            sx={{ textTransform: 'none', bgcolor: WMS_COLOR, '&:hover': { bgcolor: alpha(WMS_COLOR, 0.85) } }}>
            Registrar
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  )
}

// ─── Detalle dialog ─────────────────────────────────────────────────────────────
function DetalleDialog({
  despacho,
  onClose,
  onTransition,
}: {
  despacho: Despacho | null
  onClose: () => void
  onTransition: (id: number, estado: string) => void
}) {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const esSupervisor = ROLES_SUPERVISION.has(user?.rol ?? '')
  const [showRevertir, setShowRevertir] = useState(false)
  const [motivo, setMotivo] = useState('')

  const { data: historial = [], isFetching: loadHist } = useQuery<HistorialEntry[]>({
    queryKey: ['wms-despacho-historial', despacho?.id],
    queryFn: () => api.get(`/wms/despachos/${despacho!.id}/historial`).then(r => r.data),
    enabled: !!despacho,
  })

  const revertirMut = useMutation({
    mutationFn: ({ id, observacion }: { id: number; observacion: string }) =>
      api.post(`/wms/despachos/${id}/estado/revertir`, { observacion }).then(r => r.data),
    onSuccess: (res) => {
      toast.success(`Estado revertido a ${res.estado}`)
      qc.invalidateQueries({ queryKey: ['wms-despachos'] })
      qc.invalidateQueries({ queryKey: ['wms-despacho-historial', despacho?.id] })
      setShowRevertir(false)
      setMotivo('')
      onClose()
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Error al revertir estado'),
  })

  const handleTransicion = (id: number, estado: string) => {
    onTransition(id, estado)
    qc.invalidateQueries({ queryKey: ['wms-despacho-historial', id] })
  }

  if (!despacho) return null

  const nexts = TRANS_NEXT[despacho.estado] ?? []
  const revert = REVERT_MAP[despacho.estado]
  const items = despacho.detalles ?? []

  const estadoColor = (ESTADO_CFG as any)[despacho.estado]?.color ?? '#374151'
  const estadoBg = (ESTADO_CFG as any)[despacho.estado]?.bg ?? '#F3F4F6'

  return (
    <Dialog open={!!despacho} onClose={onClose} maxWidth="md" fullWidth
      PaperProps={{ sx: { borderRadius: 3, maxHeight: '90vh' } }}>
      <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography fontSize={16} fontWeight={700} letterSpacing="-0.02em">
              Despacho {despacho.numero_despacho}
            </Typography>
            <Chip label={(ESTADO_CFG as any)[despacho.estado]?.label ?? despacho.estado} size="small"
              sx={{ mt: 0.5, bgcolor: estadoBg, color: estadoColor, fontWeight: 700, fontSize: 11 }} />
          </Box>
          <Stack direction="row" gap={1} alignItems="center">
            <BotonPDF tipo="despacho" id={despacho.id} etiqueta="Remisión PDF" />
            <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
          </Stack>
        </Stack>
      </DialogTitle>

      <DialogContent dividers sx={{ p: 0 }}>
        {/* Información general */}
        <Box sx={{ px: 3, py: 2, bgcolor: '#FAFAFA', borderBottom: '1px solid #E5E7EB' }}>
          <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary', mb: 1.5 }}>
            Información del despacho
          </Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
            {[
              ['Orden', `#${despacho.orden_id}`],
              ['Transportadora', despacho.transportadora_nombre ?? '—'],
              ['Placa', despacho.vehiculo_placa ?? '—'],
              ['Conductor', despacho.conductor_nombre ?? '—'],
              ['F. Despacho', despacho.fecha_despacho ?? '—'],
              ['F. Entrega Est.', despacho.fecha_entrega_estimada ?? '—'],
              ['F. Entrega Real', despacho.fecha_entrega_real ?? '—'],
              ['Peso (kg)', despacho.peso_total_kg != null ? `${despacho.peso_total_kg} kg` : '—'],
              ['Notas', despacho.notas ?? '—'],
            ].map(([label, value]) => (
              <Box key={label}>
                <Typography fontSize={11} color="text.secondary">{label}</Typography>
                <Typography fontSize={12} fontWeight={600}>{value}</Typography>
              </Box>
            ))}
          </Box>
        </Box>

        {/* Botones de transición */}
        {nexts.length > 0 && (
          <Box sx={{ px: 3, py: 1.75, borderBottom: '1px solid #E5E7EB', bgcolor: '#FFFFFF' }}>
            <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary', mb: 1 }}>
              Avanzar estado
            </Typography>
            <Stack direction="row" gap={1} flexWrap="wrap">
              {nexts.map(t => (
                <Button key={t.estado} size="small"
                  variant={t.outlined ? 'outlined' : 'contained'}
                  sx={{
                    textTransform: 'none', fontSize: 12, borderRadius: '8px',
                    bgcolor: t.outlined ? undefined : t.color,
                    borderColor: t.color, color: t.outlined ? t.color : '#fff',
                    '&:hover': { bgcolor: t.outlined ? alpha(t.color, 0.08) : t.color },
                  }}
                  onClick={() => handleTransicion(despacho.id, t.estado)}>
                  {t.estado === 'ENTREGADO' && <CheckIcon sx={{ fontSize: 14, mr: 0.5 }} />}
                  {t.estado === 'EN_TRANSITO' && <TruckIcon sx={{ fontSize: 14, mr: 0.5 }} />}
                  {t.label}
                </Button>
              ))}
            </Stack>
          </Box>
        )}

        {/* Ítems */}
        <Box sx={{ px: 3, py: 2, borderBottom: '1px solid #E5E7EB' }}>
          <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary', mb: 1.5 }}>
            Ítems del despacho ({items.length})
          </Typography>
          {items.length === 0 ? (
            <Typography fontSize={12} color="text.secondary">Sin ítems registrados</Typography>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '10px' }}>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                    {['SKU', 'Producto', 'Cantidad', 'Tracking'].map(h => (
                      <TableCell key={h} sx={{ fontSize: 11, fontWeight: 700, color: '#6B7280', py: 1 }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map(item => (
                    <TableRow key={item.id} sx={{ '&:last-child td': { border: 0 } }}>
                      <TableCell sx={{ fontSize: 11, fontFamily: 'monospace', color: WMS_COLOR, fontWeight: 600 }}>{item.producto?.sku ?? `P-${item.producto_id}`}</TableCell>
                      <TableCell sx={{ fontSize: 12 }}>{item.producto?.nombre ?? '—'}</TableCell>
                      <TableCell sx={{ fontSize: 12 }}>{item.cantidad} {item.producto?.unidad_medida ?? ''}</TableCell>
                      <TableCell sx={{ fontSize: 11, fontFamily: 'monospace' }}>{item.numero_tracking ?? '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>

        {/* Historial de estado */}
        <Box sx={{ px: 3, py: 2, borderBottom: esSupervisor && revert ? '1px solid #E5E7EB' : undefined }}>
          <Stack direction="row" alignItems="center" gap={1} mb={1.5}>
            <HistoryIcon sx={{ fontSize: 15, color: '#9CA3AF' }} />
            <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary' }}>
              Historial de estado
            </Typography>
            {loadHist && <CircularProgress size={12} sx={{ color: WMS_COLOR }} />}
          </Stack>

          {historial.length === 0 && !loadHist ? (
            <Typography fontSize={12} color="text.secondary">Sin registros de historial</Typography>
          ) : (
            <Stack gap={0}>
              {historial.map((h, i) => {
                const isCorreccion = h.tipo_cambio === 'CORRECCION'
                const dotColor = isCorreccion ? '#D97706' : WMS_COLOR
                return (
                  <Box key={h.id} sx={{ display: 'flex', gap: 1.5 }}>
                    {/* Timeline spine */}
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20, flexShrink: 0 }}>
                      <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: dotColor, flexShrink: 0, mt: 0.5, border: `2px solid ${isCorreccion ? '#FDE68A' : alpha(WMS_COLOR, 0.2)}` }} />
                      {i < historial.length - 1 && <Box sx={{ width: 1.5, flex: 1, bgcolor: '#E5E7EB', my: 0.5 }} />}
                    </Box>
                    {/* Content */}
                    <Box pb={i < historial.length - 1 ? 1.5 : 0}>
                      <Stack direction="row" gap={0.75} alignItems="center" flexWrap="wrap">
                        {h.estado_anterior && (
                          <>
                            <Chip label={h.estado_anterior} size="small"
                              sx={{ fontSize: 10, height: 18, bgcolor: '#F3F4F6', color: '#6B7280' }} />
                            <ArrowIcon sx={{ fontSize: 12, color: '#9CA3AF' }} />
                          </>
                        )}
                        <Chip label={h.estado_nuevo} size="small"
                          sx={{ fontSize: 10, height: 18, bgcolor: alpha(dotColor, 0.12), color: dotColor, fontWeight: 700 }} />
                        {isCorreccion && (
                          <Chip label="Corrección" size="small"
                            sx={{ fontSize: 9, height: 16, bgcolor: '#FEF3C7', color: '#92400E', fontWeight: 700 }} />
                        )}
                      </Stack>
                      <Typography fontSize={11} color="text.secondary" mt={0.25}>
                        {h.usuario} · {aFecha(h.fecha).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}
                      </Typography>
                      {h.observacion && (
                        <Typography fontSize={11} color="#92400E" fontStyle="italic" mt={0.25}>
                          {h.observacion}
                        </Typography>
                      )}
                    </Box>
                  </Box>
                )
              })}
            </Stack>
          )}
        </Box>

        {/* Revertir estado (supervisor) */}
        {esSupervisor && revert && (
          <Box sx={{ px: 3, py: 2 }}>
            <Button
              size="small"
              startIcon={<UndoIcon sx={{ fontSize: 14 }} />}
              onClick={() => setShowRevertir(v => !v)}
              sx={{ textTransform: 'none', fontSize: 12, color: '#92400E', border: '1px solid #FDE68A', borderRadius: '8px', bgcolor: '#FFFBEB', '&:hover': { bgcolor: '#FEF3C7' } }}>
              Revertir estado
            </Button>

            {showRevertir && (
              <Box mt={2} p={2} sx={{ bgcolor: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: '10px' }}>
                <Typography fontSize={12} fontWeight={600} color="#92400E" mb={0.5}>
                  {revert.label}
                </Typography>
                <Typography fontSize={11} color="#78350F" mb={1.5}>
                  Esta acción quedará registrada en el historial con su nombre y la observación indicada.
                </Typography>
                <TextField
                  label="Observación (obligatoria)"
                  fullWidth size="small" multiline rows={2}
                  value={motivo}
                  onChange={e => setMotivo(e.target.value)}
                  sx={{ mb: 1.5, '& .MuiOutlinedInput-root': { fontSize: 12 } }}
                />
                <Stack direction="row" justifyContent="flex-end" gap={1}>
                  <Button size="small" onClick={() => { setShowRevertir(false); setMotivo('') }}
                    sx={{ textTransform: 'none', fontSize: 12 }}>Cancelar</Button>
                  <Button size="small" variant="contained" disabled={!motivo.trim() || revertirMut.isPending}
                    startIcon={revertirMut.isPending ? <CircularProgress size={12} color="inherit" /> : <UndoIcon sx={{ fontSize: 14 }} />}
                    sx={{ textTransform: 'none', fontSize: 12, bgcolor: '#D97706', '&:hover': { bgcolor: '#B45309' } }}
                    onClick={() => revertirMut.mutate({ id: despacho.id, observacion: motivo })}>
                    Revertir estado
                  </Button>
                </Stack>
              </Box>
            )}
          </Box>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ─── Devoluciones section ──────────────────────────────────────────────────────
// Acciones seleccionables al procesar una devolución. REINGRESADA reingresa stock.
const DEV_ACCIONES = ['APROBADA', 'RECHAZADA', 'REINGRESADA'] as const
// Estados finales de una devolución: ya no admiten procesamiento
const DEV_ESTADOS_FINALES = new Set(['REINGRESADA', 'RECHAZADA'])

// Configuración de chip por tipo de devolución (compartida entre tabla y detalle)
const DEV_TIPO_CFG = {
  CLIENTE:   { label: 'Cliente',   color: '#1E40AF', bg: '#DBEAFE' },
  PROVEEDOR: { label: 'Proveedor', color: '#4338CA', bg: '#E0E7FF' },
} as const

// Encabezado uniforme de sección (mismo estilo que el detalle de despacho)
const DEV_SECTION_LABEL = {
  fontSize: 12, fontWeight: 700, letterSpacing: 0.4,
  textTransform: 'uppercase' as const, color: 'text.secondary',
}

// ─── Detalle devolución dialog ──────────────────────────────────────────────────
function DetalleDevolucionDialog({ devolucion, onClose }: { devolucion: Devolucion | null; onClose: () => void }) {
  if (!devolucion) return null

  const tipoCfg = DEV_TIPO_CFG[devolucion.tipo] ?? { label: devolucion.tipo, color: '#374151', bg: '#F3F4F6' }
  const items = devolucion.detalles ?? []

  const info: Array<[string, string]> = [
    ['Tipo', tipoCfg.label],
    ['Estado', devolucion.estado],
    ['Fecha de recepción', devolucion.fecha_recepcion ?? '—'],
    ['Orden de referencia', devolucion.orden_referencia_id != null ? `#${devolucion.orden_referencia_id}` : '—'],
    [devolucion.tipo === 'PROVEEDOR' ? 'Proveedor' : 'Cliente',
      devolucion.tipo === 'PROVEEDOR'
        ? (devolucion.proveedor_id != null ? `#${devolucion.proveedor_id}` : '—')
        : (devolucion.cliente_id != null ? `#${devolucion.cliente_id}` : '—')],
    ['Almacén', devolucion.almacen_id != null ? `#${devolucion.almacen_id}` : '—'],
    ['Motivo', devolucion.motivo ?? '—'],
    ['Notas', devolucion.notas ?? '—'],
  ]

  return (
    <Dialog open={!!devolucion} onClose={onClose} maxWidth="md" fullWidth
      PaperProps={{ sx: { borderRadius: 3, maxHeight: '90vh' } }}>
      <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography fontSize={16} fontWeight={700} letterSpacing="-0.02em">
              Devolución {devolucion.numero_devolucion}
            </Typography>
            <Stack direction="row" gap={0.75} mt={0.5} flexWrap="wrap">
              <Chip label={devolucion.estado} size="small"
                sx={{ bgcolor: '#F3F4F6', color: '#374151', fontWeight: 700, fontSize: 11, height: 22 }} />
              <Chip label={tipoCfg.label} size="small"
                sx={{ bgcolor: tipoCfg.bg, color: tipoCfg.color, fontWeight: 700, fontSize: 11, height: 22 }} />
            </Stack>
          </Box>
          <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
        </Stack>
      </DialogTitle>

      <DialogContent dividers>
        {/* Información */}
        <Box sx={{ mb: 3 }}>
          <Typography sx={{ ...DEV_SECTION_LABEL, mb: 1.5 }}>Información</Typography>
          <Grid container spacing={2}>
            {info.map(([label, value]) => (
              <Grid key={label} size={{ xs: 6, sm: 4 }}>
                <Typography fontSize={11} color="text.secondary">{label}</Typography>
                <Typography fontSize={12} fontWeight={600} sx={{ wordBreak: 'break-word' }}>{value}</Typography>
              </Grid>
            ))}
          </Grid>
        </Box>

        {/* Ítems */}
        <Box>
          <Typography sx={{ ...DEV_SECTION_LABEL, mb: 1.5 }}>Ítems ({items.length})</Typography>
          {items.length === 0 ? (
            <Typography fontSize={12} color="text.secondary">Sin ítems registrados</Typography>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '10px' }}>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                    {['Producto', 'Cantidad', 'Estado calidad', 'Acción', 'Reingresado'].map(h => (
                      <TableCell key={h} sx={{ fontSize: 11, fontWeight: 700, color: '#6B7280', py: 1 }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((item, idx) => (
                    <TableRow key={item.id ?? idx} sx={{ '&:last-child td': { border: 0 } }}>
                      <TableCell sx={{ fontSize: 12 }}>
                        {item.producto
                          ? <><Box component="span" sx={{ fontFamily: 'monospace', color: WMS_COLOR, fontWeight: 600 }}>{item.producto.sku}</Box>{` — ${item.producto.nombre}`}</>
                          : `Lote #${item.lote_id ?? '—'}`}
                      </TableCell>
                      <TableCell sx={{ fontSize: 12 }}>{item.cantidad ?? '—'}</TableCell>
                      <TableCell>
                        {item.estado_calidad
                          ? <Chip label={item.estado_calidad} size="small" sx={{ bgcolor: '#F3F4F6', color: '#374151', fontSize: 10, height: 20 }} />
                          : <Typography fontSize={12} color="text.secondary">—</Typography>}
                      </TableCell>
                      <TableCell sx={{ fontSize: 12 }}>{item.accion ?? '—'}</TableCell>
                      <TableCell>
                        <Chip label={item.reingresado ? 'Sí' : 'No'} size="small"
                          sx={{ fontSize: 10, height: 20, fontWeight: 700,
                            bgcolor: item.reingresado ? '#D1FAE5' : '#F3F4F6',
                            color: item.reingresado ? '#065F46' : '#6B7280' }} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button size="small" onClick={onClose} sx={{ textTransform: 'none' }}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  )
}

function DevolucionesSection() {
  const qc = useQueryClient()
  const [openNew, setOpenNew] = useState(false)
  const [accion, setAccion] = useState<Record<number, string>>({})
  const [detalleDev, setDetalleDev] = useState<Devolucion | null>(null)

  const { data: devoluciones = [], isLoading } = useQuery<Devolucion[]>({
    queryKey: ['wms-devoluciones'],
    queryFn: () => api.get('/wms/devoluciones/').then(r => r.data),
  })

  const procesarMut = useMutation({
    mutationFn: ({ id, estado }: { id: number; estado: string }) =>
      api.put(`/wms/devoluciones/${id}/procesar`, { estado }).then(r => r.data),
    onSuccess: (d: Devolucion) => {
      toast.success(d?.nota_credito_id ? 'Devolución procesada: nota crédito emitida en Finanzas' : 'Devolución procesada')
      qc.invalidateQueries({ queryKey: ['wms-devoluciones'] })
    },
    onError: (err: any) => toast.error(mensajeDeError(err, 'Error al procesar devolución')),
  })

  const TIPO_CFG = DEV_TIPO_CFG

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Box>
          <Typography fontSize={15} fontWeight={700}>Devoluciones</Typography>
          <Typography fontSize={12} color="text.secondary">Gestión de devoluciones de clientes y proveedores</Typography>
        </Box>
        <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={() => setOpenNew(true)}
          sx={{ borderRadius: '8px', textTransform: 'none', borderColor: alpha(WMS_COLOR, 0.5), color: WMS_COLOR }}>
          Nueva Devolución
        </Button>
      </Stack>

      {isLoading ? (
        <Box display="flex" justifyContent="center" py={3}><CircularProgress size={24} sx={{ color: WMS_COLOR }} /></Box>
      ) : devoluciones.length === 0 ? (
        <Typography fontSize={13} color="text.secondary" textAlign="center" py={3}>Sin devoluciones registradas</Typography>
      ) : (
        <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '12px' }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                {['N° Devolución', 'Tipo', 'Estado', 'Motivo', 'Fecha recepción', 'Acción'].map(h => (
                  <TableCell key={h} sx={{ fontSize: 11, fontWeight: 700, color: '#6B7280', py: 1.25 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {devoluciones.map(d => {
                const tipoCfg = TIPO_CFG[d.tipo] ?? { label: d.tipo, color: '#374151', bg: '#F3F4F6' }
                return (
                  <TableRow key={d.id} hover
                    onClick={() => setDetalleDev(d)}
                    sx={{ '&:last-child td': { border: 0 }, cursor: 'pointer', '&:hover': { bgcolor: alpha(WMS_COLOR, 0.035) } }}>
                    <TableCell sx={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 700 }}>{d.numero_devolucion}</TableCell>
                    <TableCell>
                      <Chip label={tipoCfg.label} size="small" sx={{ bgcolor: tipoCfg.bg, color: tipoCfg.color, fontWeight: 700, fontSize: 10, height: 20 }} />
                    </TableCell>
                    <TableCell>
                      <Chip label={d.estado} size="small" sx={{ bgcolor: '#F3F4F6', color: '#374151', fontSize: 10, height: 20 }} />
                      {d.nota_credito_id ? <Chip label="nota crédito" size="small" color="success" variant="outlined" sx={{ ml: 0.5, fontSize: 10, height: 20 }} /> : null}
                    </TableCell>
                    <TableCell sx={{ fontSize: 12, maxWidth: 200 }}><Typography fontSize={12} noWrap>{d.motivo ?? '—'}</Typography></TableCell>
                    <TableCell sx={{ fontSize: 12 }}>{d.fecha_recepcion ?? '—'}</TableCell>
                    <TableCell onClick={e => e.stopPropagation()}>
                      {!DEV_ESTADOS_FINALES.has(d.estado) && (
                        <Stack direction="row" gap={0.75} alignItems="center">
                          <TextField select size="small" value={accion[d.id] ?? 'REINGRESADA'}
                            onChange={e => setAccion(a => ({ ...a, [d.id]: e.target.value }))}
                            sx={{ minWidth: 140, '& .MuiInputBase-root': { fontSize: 11 } }}>
                            {DEV_ACCIONES.map(a => <MenuItem key={a} value={a} sx={{ fontSize: 11 }}>{a}</MenuItem>)}
                          </TextField>
                          <Button size="small" variant="outlined" disabled={procesarMut.isPending}
                            sx={{ textTransform: 'none', fontSize: 11, borderColor: alpha(WMS_COLOR, 0.4), color: WMS_COLOR, whiteSpace: 'nowrap' }}
                            onClick={() => procesarMut.mutate({ id: d.id, estado: accion[d.id] ?? 'REINGRESADA' })}>
                            <ReturnIcon sx={{ fontSize: 13, mr: 0.5 }} /> Procesar
                          </Button>
                        </Stack>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <NuevoDevolucionDialog open={openNew} onClose={() => setOpenNew(false)} />

      <DetalleDevolucionDialog devolucion={detalleDev} onClose={() => setDetalleDev(null)} />
    </Box>
  )
}

// ─── Main page ─────────────────────────────────────────────────────────────────
// Factura un despacho que salió sin factura: pide el precio (sin IVA) de lo que
// la orden no traía; si el aviso era por NIT o resolución, basta corregirlo y facturar.
function FacturarDialog({ despacho, onClose }: { despacho: Despacho | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [precios, setPrecios] = useState<Record<number, string>>({})
  const mut = useMutation({
    mutationFn: () => api.post(`/wms/despachos/${despacho!.id}/facturar`, {
      precios: Object.fromEntries(Object.entries(precios).filter(([, v]) => Number(v) > 0).map(([k, v]) => [k, Number(v)])),
    }).then(r => r.data),
    onSuccess: (d: Despacho) => {
      toast.success(`Factura electrónica ${d.factura_numero} emitida`)
      qc.invalidateQueries({ queryKey: ['wms-despachos'] }); setPrecios({}); onClose()
    },
    onError: (err: any) => toast.error(mensajeDeError(err, 'No se pudo facturar')),
  })
  const productos = Array.from(new Map((despacho?.detalles ?? []).map(x => [x.producto_id, x])).values())
  return (
    <Dialog open={!!despacho} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Facturar despacho {despacho?.numero_despacho}</DialogTitle>
      <DialogContent>
        {despacho?.aviso_factura && <Alert severity="warning" sx={{ mb: 2 }}>{despacho.aviso_factura}</Alert>}
        <Typography fontSize={13} color="text.secondary" mb={1.5}>
          Precio unitario sin IVA de lo que la orden no traía con precio (déjelo vacío para usar el de la orden):
        </Typography>
        {productos.map(x => (
          <TextField key={x.producto_id} fullWidth size="small" type="number" sx={{ mb: 1.5 }}
            label={`${x.producto?.sku ?? x.producto_id} · ${x.producto?.nombre ?? ''} (${x.cantidad} und)`}
            value={precios[x.producto_id] ?? ''} onChange={e => setPrecios(p => ({ ...p, [x.producto_id]: e.target.value }))} />
        ))}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={mut.isPending} onClick={() => mut.mutate()} sx={{ bgcolor: WMS_COLOR }}>Emitir factura</Button>
      </DialogActions>
    </Dialog>
  )
}

export default function WMSDespacho() {
  const qc = useQueryClient()
  const [openNew, setOpenNew] = useState(false)
  const [showDevoluciones, setShowDevoluciones] = useState(false)
  const [detailDespacho, setDetailDespacho] = useState<Despacho | null>(null)
  const [facturar, setFacturar] = useState<Despacho | null>(null)

  const { data: despachos = [], isLoading } = useQuery<Despacho[]>({
    queryKey: ['wms-despachos'],
    queryFn: () => api.get('/wms/despachos/').then(r => r.data),
  })

  const transicionMut = useMutation({
    mutationFn: ({ id, estado }: { id: number; estado: string }) => {
      const body: Record<string, unknown> = { estado }
      // Al confirmar entrega registramos la fecha real (hoy) explícitamente
      if (estado === 'ENTREGADO') body.fecha_entrega_real = new Date().toISOString().slice(0, 10)
      return api.put(`/wms/despachos/${id}/estado`, body).then(r => r.data)
    },
    onSuccess: (updated) => {
      toast.success('Estado actualizado')
      qc.invalidateQueries({ queryKey: ['wms-despachos'] })
      if (detailDespacho && updated.id === detailDespacho.id) {
        setDetailDespacho(prev => prev ? { ...prev, estado: updated.estado, fecha_entrega_real: updated.fecha_entrega_real ?? prev.fecha_entrega_real } : null)
      }
    },
    onError: (err: any) => toast.error(mensajeDeError(err, 'Error al actualizar estado')),
  })

  const handleTransicion = (id: number, estado: string) => {
    transicionMut.mutate({ id, estado })
  }

  const counts = {
    preparando:    despachos.filter(d => d.estado === 'PREPARANDO').length,
    listos:        despachos.filter(d => d.estado === 'LISTO').length,
    enTransito:    despachos.filter(d => d.estado === 'EN_TRANSITO').length,
    entregadosHoy: despachos.filter(d => d.estado === 'ENTREGADO' && d.fecha_despacho?.startsWith(new Date().toISOString().slice(0, 10))).length,
  }

  return (
    <Layout title="WMS — Despacho y Distribución">
      <Box mb={3}>
        <Typography fontSize={22} fontWeight={800} color="text.primary" letterSpacing="-0.03em">
          Despacho y Distribución
        </Typography>
        <Typography fontSize={13} color="text.secondary" mt={0.25}>
          Gestión de despachos, transportadoras y devoluciones
        </Typography>
      </Box>

      {/* Summary cards */}
      <Stack direction="row" gap={2} mb={3} flexWrap="wrap">
        <StatCard label="Preparando" value={counts.preparando} color={WMS_COLOR} />
        <StatCard label="Listos" value={counts.listos} color="#D97706" />
        <StatCard label="En tránsito" value={counts.enTransito} color="#EA580C" />
        <StatCard label="Entregados hoy" value={counts.entregadosHoy} color="#059669" />
      </Stack>

      {/* Main table header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography fontSize={15} fontWeight={700}>Despachos</Typography>
        <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={() => setOpenNew(true)}
          sx={{ textTransform: 'none', bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1E3A8A' }, borderRadius: '8px' }}>
          Nuevo Despacho
        </Button>
      </Stack>

      {/* Main table */}
      {isLoading ? (
        <Box display="flex" justifyContent="center" py={4}><CircularProgress sx={{ color: WMS_COLOR }} /></Box>
      ) : (
        <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '12px', mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                {['N° Despacho', 'Orden', 'Transportadora', 'Placa', 'Conductor', 'F. Despacho', 'F. Entrega Est.', 'Estado', 'Factura', 'Peso (kg)', 'Notas', 'Acción'].map(h => (
                  <TableCell key={h} sx={{ fontSize: 11, fontWeight: 700, color: '#6B7280', py: 1.25, whiteSpace: 'nowrap' }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {despachos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={12} align="center" sx={{ py: 4 }}>
                    <Stack alignItems="center" gap={1}>
                      <AssignmentIcon sx={{ fontSize: 32, color: '#D1D5DB' }} />
                      <Typography fontSize={13} color="text.secondary">Sin despachos registrados</Typography>
                    </Stack>
                  </TableCell>
                </TableRow>
              ) : despachos.map(d => (
                <TableRow key={d.id} hover
                  onClick={() => setDetailDespacho(d)}
                  sx={{ '&:last-child td': { border: 0 }, cursor: 'pointer', '&:hover': { bgcolor: alpha(WMS_COLOR, 0.035) } }}>
                  <TableCell sx={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 700, color: WMS_COLOR }}>{d.numero_despacho}</TableCell>
                  <TableCell sx={{ fontSize: 12 }}>{`#${d.orden_id}`}</TableCell>
                  <TableCell sx={{ fontSize: 12 }}>{d.transportadora_nombre ?? '—'}</TableCell>
                  <TableCell sx={{ fontSize: 12, fontFamily: 'monospace' }}>{d.vehiculo_placa ?? '—'}</TableCell>
                  <TableCell sx={{ fontSize: 12 }}>{d.conductor_nombre ?? '—'}</TableCell>
                  <TableCell sx={{ fontSize: 12, whiteSpace: 'nowrap' }}>{d.fecha_despacho ?? '—'}</TableCell>
                  <TableCell sx={{ fontSize: 12, whiteSpace: 'nowrap' }}>{d.fecha_entrega_estimada ?? '—'}</TableCell>
                  <TableCell><EstadoChip estado={d.estado} /></TableCell>
                  <TableCell onClick={e => e.stopPropagation()} sx={{ whiteSpace: 'nowrap' }}>
                    {d.factura_numero
                      ? <Chip size="small" color="success" variant="outlined" label={d.factura_numero} />
                      : d.aviso_factura
                        ? <Tooltip title={d.aviso_factura}>
                            <Button size="small" color="warning" variant="outlined" onClick={() => setFacturar(d)}
                              sx={{ textTransform: 'none', fontSize: 12, py: 0 }}>Facturar</Button>
                          </Tooltip>
                        : <Typography fontSize={12} color="text.secondary">—</Typography>}
                  </TableCell>
                  <TableCell sx={{ fontSize: 12 }}>{d.peso_total_kg != null ? `${d.peso_total_kg} kg` : '—'}</TableCell>
                  <TableCell sx={{ fontSize: 12, maxWidth: 160 }}>
                    <Tooltip title={d.notas ?? ''}>
                      <Typography fontSize={12} noWrap>{d.notas ?? '—'}</Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell onClick={e => e.stopPropagation()}>
                    <EstadoButton despacho={d} onTransition={handleTransicion} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Devoluciones collapsible section */}
      <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '12px', overflow: 'hidden' }}>
        <Box
          onClick={() => setShowDevoluciones(v => !v)}
          sx={{
            px: 2.5, py: 1.75, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            cursor: 'pointer', bgcolor: '#FAFAFA', '&:hover': { bgcolor: '#F3F4F6' },
          }}
        >
          <Stack direction="row" gap={1} alignItems="center">
            <ReturnIcon sx={{ fontSize: 16, color: WMS_COLOR }} />
            <Typography fontSize={14} fontWeight={700}>Devoluciones</Typography>
          </Stack>
          {showDevoluciones ? <ExpandLessIcon sx={{ fontSize: 18, color: '#9CA3AF' }} /> : <ExpandMoreIcon sx={{ fontSize: 18, color: '#9CA3AF' }} />}
        </Box>
        <Collapse in={showDevoluciones}>
          <Box p={2.5}><DevolucionesSection /></Box>
        </Collapse>
      </Paper>

      <NuevoDespachoDialog open={openNew} onClose={() => setOpenNew(false)} />
      <FacturarDialog despacho={facturar} onClose={() => setFacturar(null)} />

      <DetalleDialog
        despacho={detailDespacho}
        onClose={() => setDetailDespacho(null)}
        onTransition={handleTransicion}
      />
    </Layout>
  )
}
