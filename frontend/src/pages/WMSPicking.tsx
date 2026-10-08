import { Fragment, useState, type ReactNode } from 'react'
import {
  Box, Stack, Typography, Card, Tabs, Tab, MenuItem, Button, Table, TableHead, TableBody, TableRow, TableCell, Chip, IconButton, Skeleton, Alert, LinearProgress, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions, Divider, InputLabel, InputAdornment, Collapse, alpha,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import LocalShippingIcon from '@mui/icons-material/LocalShipping'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient as api } from '@/api/client'
import { type ItemEscaneado } from '@/components/wms/Escaner'
import { ArmadoEnvio, type StockOrigen } from '@/components/wms/ArmadoEnvio'
import { equivalencia, useNiveles } from '@/components/wms/empaques'
import { EjecutarPicking, type TareaParaEjecutar } from '@/components/wms/EjecutarPicking'
import { BotonPDF } from '@/components/comun/BotonPDF'
import { NumeroAutomatico } from '@/components/comun/NumeroAutomatico'
import { Layout } from '@/components/layout/Layout'

import { COLOR_MODULO } from '@/config/marca'

/** Estado de la línea (lo calcula el servidor con sus cantidades y el estado de la orden). */
const ESTADO_LINEA: Record<string, { t: string; c: string }> = {
  PENDIENTE: { t: 'Pendiente', c: '#64748B' },
  RESERVADO: { t: 'Reservado', c: '#7C3AED' },
  EN_PREPARACION: { t: 'En preparación', c: '#D97706' },
  PREPARADO: { t: 'Preparado', c: '#4F46E5' },
  DESPACHO_PARCIAL: { t: 'Despacho parcial', c: '#C2410C' },
  DESPACHADO: { t: 'Despachado', c: '#0EA5E9' },
  ENTREGA_PARCIAL: { t: 'Entrega parcial', c: '#B45309' },
  ENTREGADO: { t: 'Entregado', c: '#16A34A' },
  CANCELADO: { t: 'Cancelado', c: '#DC2626' },
}
import { mensajeDeError } from '@/utils/errorApi'
import { aFecha } from '@/utils/fechas'
// ─── Interfaces ───────────────────────────────────────────────────────────────

interface OrdenSalidaDetalle {
  producto_id: number
  producto?: { sku: string; nombre: string }
  cantidad_solicitada: number
  cantidad_preparada: number
  cantidad_despachada: number
  precio_unitario?: number
  estado: string
}

interface OrdenSalida {
  id: number
  numero_orden: string
  cliente?: { nombre: string }
  almacen?: { nombre: string }
  fecha_emision?: string | null
  fecha_requerida: string | null
  prioridad: 'URGENTE' | 'ALTA' | 'NORMAL' | 'BAJA'
  estado: string
  canal: string
  detalles?: OrdenSalidaDetalle[]
}

interface OrdenLinea {
  producto_id: string
  cantidad_solicitada: string
  precio_unitario: string
  lote_id: string
  /** Viene de la selección manual / escáner / RFID: la cantidad se cambia allá. */
  de_armado?: boolean
}

interface OrdenDetallePayload {
  producto_id: number
  cantidad_solicitada: number
  precio_unitario?: number
  lote_id: number | null
}

interface OrdenSalidaPayload {
  numero_orden?: string
  cliente_id: number
  almacen_id: number
  fecha_requerida?: string | null
  prioridad?: string
  canal?: string
  detalles: OrdenDetallePayload[]
}

interface TareaPickingDetalle {
  id: number
  producto_id: number
  producto?: { sku: string; nombre: string }
  ubicacion_id: number
  ubicacion?: { codigo: string; pasillo?: string }
  lote_id?: number | null
  cantidad_solicitada: number
  cantidad_pickeada: number
  confirmado: boolean
}

interface TareaPicking {
  id: number
  orden_id: number
  operario_id?: number
  tipo: 'SINGLE' | 'BATCH' | 'ZONE' | 'CLUSTER' | 'WAVE'
  estado: string
  items_pickeados: number
  ubicaciones_visitadas?: number
  detalles?: TareaPickingDetalle[]
}

interface Cliente { id: number; nombre: string }
interface Almacen { id: number; nombre: string }
interface Producto { id: number; nombre: string; sku: string; unidad_medida?: string }
interface Lote { id: number; producto_id: number; numero_lote: string }

// ─── Constants ────────────────────────────────────────────────────────────────

const WMS_COLOR = COLOR_MODULO

const PRIORIDAD_CONFIG: Record<string, { color: 'error' | 'warning' | 'info' | 'default'; label: string }> = {
  URGENTE: { color: 'error', label: 'Urgente' },
  ALTA:    { color: 'warning', label: 'Alta' },
  NORMAL:  { color: 'info', label: 'Normal' },
  BAJA:    { color: 'default', label: 'Baja' },
}

const EMPTY_ORDEN = {
  numero_orden: '',
  cliente_id: '',
  almacen_id: '',
  fecha_requerida: '',
  prioridad: 'NORMAL',
  canal: '',
}

// Formatea una fecha ISO a formato local; devuelve '—' si es null/indefinida/ inválida.
function formatFecha(value?: string | null): string {
  if (!value) return '—'
  const d = aFecha(value)
  return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('es-CO')
}

// Formatea un valor monetario en pesos.
function formatMoneda(value: number): string {
  return `$ ${value.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

// Extrae un mensaje legible del error de axios (soporta detail string o array 422 de FastAPI).

// ─── Component ────────────────────────────────────────────────────────────────

export default function WMSPicking() {
  const queryClient = useQueryClient()

  // ── Tab state ──
  const [tab, setTab] = useState(0)

  // ── Filter state ──
  const [filtrosOrdenes, setFiltrosOrdenes] = useState({ estado: '', prioridad: '', cliente: '' })
  const [filtrosTareas, setFiltrosTareas] = useState({ estado: '' })

  // ── Dialog state ──
  const [openOrdenDialog, setOpenOrdenDialog] = useState(false)
  const [ordenForm, setOrdenForm] = useState({ ...EMPTY_ORDEN })
  const [lineas, setLineas] = useState<OrdenLinea[]>([{ producto_id: '', cantidad_solicitada: '', precio_unitario: '', lote_id: '' }])

  // ── Expandable tarea ──
  const [expandedTarea, setExpandedTarea] = useState<number | null>(null)
  // Confirmación por escaneo: el operario escanea la ubicación y el producto;
  // el servidor rechaza si no coinciden con la línea.
  const [confirmando, setConfirmando] = useState<{ tareaId: number; detalle: TareaPickingDetalle } | null>(null)
  const [escaneo, setEscaneo] = useState({ ubicacion: '', producto: '', cantidad: '' })
  // Confirmación: si ya se escaneó algo, la cantidad se arma con las lecturas.
  const [leyendo, setLeyendo] = useState(false)
  const [errorLectura, setErrorLectura] = useState('')
  // Tarea abierta en la pantalla de ejecución (manual / escáner / RFID).
  const [ejecutando, setEjecutando] = useState<TareaParaEjecutar | null>(null)
  const niveles = useNiveles()

  // Armado de la orden (selección manual / escáner / RFID), en unidades.
  const [armado, setArmado] = useState<ItemEscaneado[]>([])

  // ── Detalle de orden (dialog) ──
  const [detalleOrden, setDetalleOrden] = useState<OrdenSalida | null>(null)

  // ─── Queries ──────────────────────────────────────────────────────────────

  const { data: ordenes, isLoading: loadingOrdenes, isError: errorOrdenes } = useQuery<OrdenSalida[]>({
    queryKey: ['wms-ordenes', filtrosOrdenes],
    queryFn: async () => {
      // Con tope: sin él la pantalla pedía las 3.258 órdenes del año con todas
      // sus líneas, más de un megabyte, para pintar una tabla.
      const params: Record<string, string> = { limite: '200' }
      if (filtrosOrdenes.estado)    params.estado    = filtrosOrdenes.estado
      if (filtrosOrdenes.prioridad) params.prioridad = filtrosOrdenes.prioridad
      if (filtrosOrdenes.cliente)   params.cliente   = filtrosOrdenes.cliente
      const res = await api.get('/wms/ordenes-salida/', { params })
      return res.data
    },
  })

  const { data: tareas, isLoading: loadingTareas, isError: errorTareas } = useQuery<TareaPicking[]>({
    queryKey: ['wms-tareas', filtrosTareas],
    queryFn: async () => {
      const params: Record<string, string> = { limite: '200' }
      if (filtrosTareas.estado) params.estado = filtrosTareas.estado
      const res = await api.get('/wms/picking-tareas/', { params })
      return res.data
    },
  })

  const { data: clientes } = useQuery<Cliente[]>({
    queryKey: ['wms-clientes'],
    queryFn: async () => {
      const res = await api.get('/wms/clientes/')
      return res.data
    },
  })

  const { data: almacenes } = useQuery<Almacen[]>({
    queryKey: ['wms-almacenes'],
    queryFn: async () => {
      const res = await api.get('/wms/almacenes/')
      return res.data
    },
  })

  const { data: productos } = useQuery<Producto[]>({
    queryKey: ['wms-productos'],
    queryFn: async () => {
      const res = await api.get('/wms/productos/')
      return res.data
    },
  })

  const stockAlmacen = useQuery<StockOrigen[]>({
    queryKey: ['wms-stock-almacen', ordenForm.almacen_id],
    enabled: !!ordenForm.almacen_id,
    queryFn: () => api.get('/wms/inventario/', { params: { almacen_id: ordenForm.almacen_id } }).then(r => r.data),
  })

  const { data: lotes } = useQuery<Lote[]>({
    queryKey: ['wms-lotes'],
    queryFn: async () => {
      const res = await api.get('/wms/lotes/')
      return res.data
    },
  })

  // ─── Mutations ────────────────────────────────────────────────────────────

  const mutCrearOrden = useMutation({
    mutationFn: async (body: OrdenSalidaPayload) => {
      const res = await api.post('/wms/ordenes-salida/', body)
      return res.data
    },
    onSuccess: (o: { numero_orden?: string }) => {
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes'] })
      toast.success(o?.numero_orden ? `Orden ${o.numero_orden} creada` : 'Orden creada')
      setOrdenForm({ ...EMPTY_ORDEN })
      setLineas([{ producto_id: '', cantidad_solicitada: '', precio_unitario: '', lote_id: '' }])
      setArmado([])
      setOpenOrdenDialog(false)
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error, 'No se pudo crear la orden')),
  })

  const mutGenerarPicking = useMutation({
    mutationFn: async (id: number) => {
      const res = await api.post(`/wms/ordenes-salida/${id}/generar-picking`)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes'] })
      queryClient.invalidateQueries({ queryKey: ['wms-tareas'] })
      toast.success('Picking generado')
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error, 'No se pudo generar el picking')),
  })

  const mutConfirmarItem = useMutation({
    mutationFn: async ({ tareaId, detalle_id, cantidad_pickeada, ubicacion_codigo, producto_codigo }:
      { tareaId: number; detalle_id: number; cantidad_pickeada: number; ubicacion_codigo?: string; producto_codigo?: string }) => {
      const res = await api.post(`/wms/picking-tareas/${tareaId}/confirmar-item`, { detalle_id, cantidad_pickeada, ubicacion_codigo, producto_codigo })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wms-tareas'] })
      toast.success('Item confirmado')
      setConfirmando(null)
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error, 'No se pudo confirmar el item')),
  })

  // ─── Helpers ──────────────────────────────────────────────────────────────

  const addLinea = () => {
    setLineas(prev => [...prev, { producto_id: '', cantidad_solicitada: '', precio_unitario: '', lote_id: '' }])
  }

  // Lo armado (selección manual, escáner, RFID) se vuelve líneas del pedido;
  // se conservan el precio y el lote ya escritos. Las líneas agregadas a mano
  // (productos sin stock, por ejemplo) no se tocan.
  const cambiarArmado = (items: ItemEscaneado[]) => {
    setArmado(items)
    setLineas(prev => {
      const previas = new Map(prev.filter(l => l.de_armado).map(l => [l.producto_id, l]))
      const armadas: OrdenLinea[] = items.filter(x => x.cantidad > 0).map(x => ({
        precio_unitario: '', lote_id: '', ...previas.get(String(x.producto_id)),
        producto_id: String(x.producto_id), cantidad_solicitada: String(x.cantidad), de_armado: true,
      }))
      const manuales = prev.filter(l => !l.de_armado && l.producto_id)
      const todas = [...armadas, ...manuales]
      return todas.length ? todas : [{ producto_id: '', cantidad_solicitada: '', precio_unitario: '', lote_id: '' }]
    })
  }

  const removeLinea = (index: number) => {
    const l = lineas[index]
    if (l?.de_armado) setArmado(a => a.filter(x => String(x.producto_id) !== l.producto_id))
    setLineas(prev => prev.filter((_, i) => i !== index))
  }

  const updateLinea = (index: number, field: keyof OrdenLinea, value: string) => {
    setLineas(prev => prev.map((l, i) => i === index ? { ...l, [field]: value } : l))
  }

  const handleCrearOrden = () => {
    if (!ordenForm.cliente_id) {
      toast.error('El cliente es requerido')
      return
    }
    if (!ordenForm.almacen_id) {
      toast.error('El almacén es requerido')
      return
    }
    const lineasValidas = lineas.every(
      l => l.producto_id && Number(l.cantidad_solicitada) > 0,
    )
    if (lineas.length === 0 || !lineasValidas) {
      toast.error('Cada línea requiere un producto y una cantidad mayor a 0')
      return
    }

    const payload: OrdenSalidaPayload = {
      cliente_id: Number(ordenForm.cliente_id),
      almacen_id: Number(ordenForm.almacen_id),
      prioridad: ordenForm.prioridad,
      canal: ordenForm.canal || undefined,
      detalles: lineas.map(l => ({
        producto_id: Number(l.producto_id),
        cantidad_solicitada: Number(l.cantidad_solicitada),
        precio_unitario: l.precio_unitario ? Number(l.precio_unitario) : undefined,
        lote_id: l.lote_id ? Number(l.lote_id) : null,
      })),
    }
    if (ordenForm.numero_orden.trim()) payload.numero_orden = ordenForm.numero_orden.trim()
    if (ordenForm.fecha_requerida) payload.fecha_requerida = ordenForm.fecha_requerida

    mutCrearOrden.mutate(payload)
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <Layout>
      <Box sx={{ p: 3, bgcolor: '#F0F2F5', minHeight: '100vh' }}>

        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          <LocalShippingIcon sx={{ color: WMS_COLOR, fontSize: 32 }} />
          <Box>
            <Typography variant="h5" fontWeight={700} color={WMS_COLOR}>
              Picking y Órdenes de Salida
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Gestión de órdenes salientes y tareas de picking
            </Typography>
          </Box>
        </Box>

        {/* Tabs */}
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{
            mb: 2,
            '& .MuiTabs-indicator': { bgcolor: WMS_COLOR },
            '& .Mui-selected': { color: `${WMS_COLOR} !important` },
          }}
        >
          <Tab label="Órdenes de Salida" />
          <Tab label="Tareas de Picking" />
        </Tabs>

        {/* ── TAB 0: Órdenes de Salida ─────────────────────────────────────── */}
        {tab === 0 && (
          <Box>
            {/* Filters */}
            <Card sx={{ p: 2, mb: 2 }}>
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
                <TextField
                  select
                  label="Estado"
                  size="small"
                  value={filtrosOrdenes.estado}
                  onChange={e => setFiltrosOrdenes(prev => ({ ...prev, estado: e.target.value }))}
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="">Todos</MenuItem>
                  <MenuItem value="PENDIENTE">Pendiente</MenuItem>
                  <MenuItem value="EN_PICKING">En Picking</MenuItem>
                  <MenuItem value="EMPACANDO">Empacando</MenuItem>
                  <MenuItem value="DESPACHADO">Despachado</MenuItem>
                  <MenuItem value="ENTREGADO">Entregado</MenuItem>
                  <MenuItem value="CANCELADO">Cancelado</MenuItem>
                </TextField>

                <TextField
                  select
                  label="Prioridad"
                  size="small"
                  value={filtrosOrdenes.prioridad}
                  onChange={e => setFiltrosOrdenes(prev => ({ ...prev, prioridad: e.target.value }))}
                  sx={{ minWidth: 140 }}
                >
                  <MenuItem value="">Todas</MenuItem>
                  <MenuItem value="URGENTE">Urgente</MenuItem>
                  <MenuItem value="ALTA">Alta</MenuItem>
                  <MenuItem value="NORMAL">Normal</MenuItem>
                  <MenuItem value="BAJA">Baja</MenuItem>
                </TextField>

                <TextField
                  label="Cliente"
                  size="small"
                  value={filtrosOrdenes.cliente}
                  onChange={e => setFiltrosOrdenes(prev => ({ ...prev, cliente: e.target.value }))}
                  sx={{ minWidth: 180 }}
                />

                <Box sx={{ flexGrow: 1 }} />

                <Button
                  variant="contained"
                  startIcon={<AddIcon />}
                  sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1E3A8A' } }}
                  onClick={() => setOpenOrdenDialog(true)}
                >
                  Nueva Orden
                </Button>
              </Box>
            </Card>

            {/* Ordenes Table */}
            <Card>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: alpha(WMS_COLOR, 0.06) }}>
                      <TableCell sx={{ fontWeight: 700 }}># Orden</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Cliente</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Almacén</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Fecha Req.</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Prioridad</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Estado</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Canal</TableCell>
                      <TableCell sx={{ fontWeight: 700 }} align="center">Items</TableCell>
                      <TableCell sx={{ fontWeight: 700, minWidth: 140 }}>Progreso</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Acciones</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {loadingOrdenes ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <TableRow key={i}>
                          {Array.from({ length: 10 }).map((__, j) => (
                            <TableCell key={j}><Skeleton variant="text" /></TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : errorOrdenes ? (
                      <TableRow>
                        <TableCell colSpan={10}>
                          <Alert severity="error">Error al cargar las órdenes de salida</Alert>
                        </TableCell>
                      </TableRow>
                    ) : (ordenes ?? []).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={10} align="center">
                          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                            No hay órdenes de salida
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ) : (
                      (ordenes ?? []).map(orden => {
                        const detalles = orden.detalles ?? []
                        const totalItems = detalles.length
                        const qtySolicitada = detalles.reduce((s, d) => s + (d.cantidad_solicitada ?? 0), 0)
                        const qtyPreparada = detalles.reduce((s, d) => s + (d.cantidad_preparada ?? 0), 0)
                        const progreso = qtySolicitada > 0
                          ? (qtyPreparada / qtySolicitada) * 100
                          : 0

                        const estadoColor: Record<string, 'warning' | 'info' | 'primary' | 'success' | 'default' | 'error'> = {
                          PENDIENTE: 'warning',
                          EN_PICKING: 'info',
                          EMPACANDO: 'primary',
                          DESPACHADO: 'success',
                          ENTREGADO: 'default',
                          CANCELADO: 'error',
                        }

                        return (
                          <TableRow
                            key={orden.id}
                            hover
                            onClick={() => setDetalleOrden(orden)}
                            sx={{ cursor: 'pointer' }}
                          >
                            <TableCell>
                              <Typography fontWeight={600} variant="body2">
                                {orden.numero_orden}
                              </Typography>
                            </TableCell>
                            <TableCell>{orden.cliente?.nombre ?? '-'}</TableCell>
                            <TableCell>{orden.almacen?.nombre ?? '-'}</TableCell>
                            <TableCell>{formatFecha(orden.fecha_requerida)}</TableCell>
                            <TableCell>
                              <Chip
                                size="small"
                                color={PRIORIDAD_CONFIG[orden.prioridad]?.color ?? 'default'}
                                label={PRIORIDAD_CONFIG[orden.prioridad]?.label ?? orden.prioridad}
                              />
                            </TableCell>
                            <TableCell>
                              <Chip
                                size="small"
                                color={estadoColor[orden.estado] ?? 'default'}
                                label={orden.estado}
                              />
                            </TableCell>
                            <TableCell>
                              <Chip size="small" variant="outlined" label={orden.canal || '-'} />
                            </TableCell>
                            <TableCell align="center">{totalItems}</TableCell>
                            <TableCell>
                              <LinearProgress
                                variant="determinate"
                                value={progreso}
                                sx={{ height: 8, borderRadius: 4 }}
                              />
                              <Typography variant="caption" color="text.secondary">
                                {qtyPreparada}/{qtySolicitada}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              {(orden.estado === 'PENDIENTE' || orden.estado === 'EN_PICKING') && (
                                <Tooltip title="Generar Picking">
                                  <span>
                                    <IconButton
                                      size="small"
                                      disabled={mutGenerarPicking.isPending}
                                      onClick={e => { e.stopPropagation(); mutGenerarPicking.mutate(orden.id) }}
                                      sx={{ color: WMS_COLOR }}
                                    >
                                      <PlayArrowIcon fontSize="small" />
                                    </IconButton>
                                  </span>
                                </Tooltip>
                              )}
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </Box>
            </Card>
          </Box>
        )}

        {/* ── TAB 1: Tareas de Picking ──────────────────────────────────────── */}
        {tab === 1 && (
          <Box>
            {/* Filters */}
            <Card sx={{ p: 2, mb: 2 }}>
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
                <TextField
                  select
                  label="Estado"
                  size="small"
                  value={filtrosTareas.estado}
                  onChange={e => setFiltrosTareas(prev => ({ ...prev, estado: e.target.value }))}
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="">Todos</MenuItem>
                  <MenuItem value="PENDIENTE">Pendiente</MenuItem>
                  <MenuItem value="EN_PROGRESO">En Progreso</MenuItem>
                  <MenuItem value="COMPLETADA">Completada</MenuItem>
                  <MenuItem value="CANCELADA">Cancelada</MenuItem>
                </TextField>
              </Box>
            </Card>

            {/* Tareas Table */}
            <Card>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: alpha(WMS_COLOR, 0.06) }}>
                      <TableCell sx={{ fontWeight: 700 }}>ID</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Orden</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Tipo</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Operario</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Estado</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Ubic.</TableCell>
                      <TableCell sx={{ fontWeight: 700, minWidth: 140 }}>Progreso</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Detalle</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {loadingTareas ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <TableRow key={i}>
                          {Array.from({ length: 8 }).map((__, j) => (
                            <TableCell key={j}><Skeleton variant="text" /></TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : errorTareas ? (
                      <TableRow>
                        <TableCell colSpan={8}>
                          <Alert severity="error">Error al cargar las tareas de picking</Alert>
                        </TableCell>
                      </TableRow>
                    ) : (tareas ?? []).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} align="center">
                          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                            No hay tareas de picking
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ) : (
                      (tareas ?? []).map(tarea => {
                        const tipoColor: Record<string, 'default' | 'info' | 'warning' | 'secondary' | 'primary'> = {
                          SINGLE:  'default',
                          BATCH:   'info',
                          ZONE:    'warning',
                          CLUSTER: 'secondary',
                          WAVE:    'primary',
                        }

                        const estadoTareaColor: Record<string, 'warning' | 'info' | 'primary' | 'success' | 'error'> = {
                          PENDIENTE:   'warning',
                          EN_PROGRESO: 'primary',
                          COMPLETADA:  'success',
                          CANCELADA:   'error',
                        }

                        const detallesTarea = tarea.detalles ?? []
                        const totalItemsTarea = detallesTarea.length
                        const progreso = totalItemsTarea > 0
                          ? (tarea.items_pickeados / totalItemsTarea) * 100
                          : 0

                        const isExpanded = expandedTarea === tarea.id

                        return (
                          <Fragment key={tarea.id}>
                            <TableRow key={tarea.id} hover>
                              <TableCell>
                                <Typography fontWeight={600} variant="body2" color={WMS_COLOR}>
                                  {tarea.id}
                                </Typography>
                              </TableCell>
                              <TableCell>{`#${tarea.orden_id}`}</TableCell>
                              <TableCell>
                                <Chip
                                  size="small"
                                  color={tipoColor[tarea.tipo] ?? 'default'}
                                  label={tarea.tipo}
                                />
                              </TableCell>
                              <TableCell>{tarea.operario_id ? `#${tarea.operario_id}` : '-'}</TableCell>
                              <TableCell>
                                <Chip
                                  size="small"
                                  color={estadoTareaColor[tarea.estado] ?? 'default'}
                                  label={tarea.estado}
                                />
                              </TableCell>
                              <TableCell>{tarea.ubicaciones_visitadas ?? '-'}</TableCell>
                              <TableCell>
                                <LinearProgress
                                  variant="determinate"
                                  value={progreso}
                                  sx={{ height: 8, borderRadius: 4 }}
                                />
                                <Typography variant="caption" color="text.secondary">
                                  {tarea.items_pickeados}/{totalItemsTarea}
                                </Typography>
                              </TableCell>
                              <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                <BotonPDF tipo="picking" id={tarea.id} etiqueta="Hoja de picking (PDF)" icono />
                                {tarea.estado !== 'COMPLETADA' && tarea.estado !== 'CANCELADA' && (
                                  <Button size="small" variant="contained" sx={{ mr: 1, textTransform: 'none', fontWeight: 700 }}
                                    onClick={() => setEjecutando(tarea as unknown as TareaParaEjecutar)}>
                                    Ejecutar
                                  </Button>
                                )}
                                <IconButton
                                  size="small"
                                  onClick={() => setExpandedTarea(isExpanded ? null : tarea.id)}
                                >
                                  {isExpanded ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
                                </IconButton>
                              </TableCell>
                            </TableRow>

                            {/* Expandable row */}
                            <TableRow key={`${tarea.id}-expand`}>
                              <TableCell colSpan={8} sx={{ py: 0, border: isExpanded ? undefined : 0 }}>
                                <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                                  <Box sx={{ bgcolor: alpha(WMS_COLOR, 0.03), p: 2 }}>
                                    <Typography fontWeight={600} variant="body2" sx={{ mb: 1 }}>
                                      Líneas de Picking
                                    </Typography>

                                    {detallesTarea.length === 0 ? (
                                      <Typography variant="body2" color="text.secondary">
                                        Sin detalle disponible
                                      </Typography>
                                    ) : (
                                      <Table size="small">
                                        <TableHead>
                                          <TableRow>
                                            <TableCell sx={{ fontWeight: 700 }}>Producto</TableCell>
                                            <TableCell sx={{ fontWeight: 700 }}>Ubicación</TableCell>
                                            <TableCell sx={{ fontWeight: 700 }}>Solicitado</TableCell>
                                            <TableCell sx={{ fontWeight: 700 }}>Pickeado</TableCell>
                                            <TableCell sx={{ fontWeight: 700 }}>Estado</TableCell>
                                            <TableCell sx={{ fontWeight: 700 }}>Acción</TableCell>
                                          </TableRow>
                                        </TableHead>
                                        <TableBody>
                                          {detallesTarea.map(detalle => (
                                            <TableRow key={detalle.id} hover>
                                              <TableCell>{detalle.producto?.nombre ?? '-'}</TableCell>
                                              <TableCell>
                                                <Chip
                                                  size="small"
                                                  variant="outlined"
                                                  label={detalle.ubicacion?.codigo ?? '-'}
                                                />
                                              </TableCell>
                                              <TableCell>{detalle.cantidad_solicitada}</TableCell>
                                              <TableCell>{detalle.cantidad_pickeada}</TableCell>
                                              <TableCell>
                                                {detalle.confirmado ? (
                                                  <Chip
                                                    size="small"
                                                    color="success"
                                                    label="Confirmado"
                                                    icon={<CheckCircleIcon />}
                                                  />
                                                ) : (
                                                  <Chip
                                                    size="small"
                                                    color="warning"
                                                    label="Pendiente"
                                                    icon={<HourglassEmptyIcon />}
                                                  />
                                                )}
                                              </TableCell>
                                              <TableCell>
                                                {!detalle.confirmado && (
                                                  <Button
                                                    size="small"
                                                    variant="outlined"
                                                    onClick={() => {
                                                      setConfirmando({ tareaId: tarea.id, detalle })
                                                      setEscaneo({ ubicacion: '', producto: '', cantidad: String(detalle.cantidad_solicitada) }); setLeyendo(false); setErrorLectura('')
                                                    }}
                                                  >
                                                    Confirmar
                                                  </Button>
                                                )}
                                              </TableCell>
                                            </TableRow>
                                          ))}
                                        </TableBody>
                                      </Table>
                                    )}
                                  </Box>
                                </Collapse>
                              </TableCell>
                            </TableRow>
                          </Fragment>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </Box>
            </Card>
          </Box>
        )}

        {/* ── Dialog: Nueva Orden de Salida ─────────────────────────────────── */}
        <Dialog
          open={openOrdenDialog}
          onClose={() => setOpenOrdenDialog(false)}
          maxWidth="md"
          fullWidth
          PaperProps={{ sx: { borderRadius: 3 } }}
        >
          <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
            Nueva Orden de Salida
          </DialogTitle>
          <Typography variant="caption" color="text.secondary" sx={{ px: 3, pb: 1, display: 'block' }}>
            Registra los datos del cliente y las líneas de producto a despachar.
          </Typography>
          <DialogContent dividers sx={{ px: 3, py: 2.5 }}>

            {/* Section 1 — Datos de la Orden */}
            <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary', mb: 0.5 }}>
              DATOS DE LA ORDEN
            </Typography>
            <Grid container spacing={2.5} sx={{ mt: 0.5 }}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <NumeroAutomatico tipo="OS" etiqueta="Número de orden" />
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Cliente</InputLabel>
                  <Select
                    label="Cliente"
                    value={ordenForm.cliente_id}
                    onChange={e => setOrdenForm(prev => ({ ...prev, cliente_id: e.target.value }))}
                  >
                    <MenuItem value="">Seleccionar</MenuItem>
                    {(clientes ?? []).map(c => (
                      <MenuItem key={c.id} value={String(c.id)}>{c.nombre}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Almacén</InputLabel>
                  <Select
                    label="Almacén"
                    value={ordenForm.almacen_id}
                    onChange={e => setOrdenForm(prev => ({ ...prev, almacen_id: e.target.value }))}
                  >
                    <MenuItem value="">Seleccionar</MenuItem>
                    {(almacenes ?? []).map(a => (
                      <MenuItem key={a.id} value={String(a.id)}>{a.nombre}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  label="Fecha Requerida"
                  type="date"
                  fullWidth
                  size="small"
                  value={ordenForm.fecha_requerida}
                  onChange={e => setOrdenForm(prev => ({ ...prev, fecha_requerida: e.target.value }))}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Prioridad</InputLabel>
                  <Select
                    label="Prioridad"
                    value={ordenForm.prioridad}
                    onChange={e => setOrdenForm(prev => ({ ...prev, prioridad: e.target.value }))}
                  >
                    <MenuItem value="URGENTE">Urgente</MenuItem>
                    <MenuItem value="ALTA">Alta</MenuItem>
                    <MenuItem value="NORMAL">Normal</MenuItem>
                    <MenuItem value="BAJA">Baja</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  label="Canal"
                  fullWidth
                  size="small"
                  value={ordenForm.canal}
                  onChange={e => setOrdenForm(prev => ({ ...prev, canal: e.target.value }))}
                />
              </Grid>
            </Grid>

            <Divider sx={{ my: 1.5 }} />

            {/* Section 2 — Líneas de Pedido */}
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
              <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary' }}>
                LÍNEAS DE PEDIDO
              </Typography>
              <Button
                variant="outlined"
                size="small"
                startIcon={<AddIcon />}
                onClick={addLinea}
              >
                Agregar Línea
              </Button>
            </Box>
            <Box sx={{ mt: 1, mb: 1.5 }}>
              <ArmadoEnvio stock={stockAlmacen.data ?? []} items={armado} onCambio={cambiarArmado}
                cargando={stockAlmacen.isLoading} sinOrigen={!ordenForm.almacen_id}
                titulo="Qué se despacha" avisoSinOrigen="Elija primero el almacén desde donde se despacha." />
            </Box>
            <Typography sx={{ fontSize: 12, color: 'text.secondary', mb: 1 }}>
              Las líneas se llenan solas con lo de arriba (cantidad en unidades). Use «Agregar línea» para productos sin stock.
            </Typography>

            <Box sx={{ maxHeight: 340, overflowY: 'auto', pr: 0.5, mt: 1 }}>
              {lineas.map((linea, index) => (
                <Box
                  key={index}
                  sx={{ p: 1.5, mb: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2, bgcolor: 'action.hover' }}
                >
                  <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                    <Typography variant="caption" fontWeight={700}>
                      Línea {index + 1}
                    </Typography>
                    <IconButton
                      size="small"
                      color="error"
                      disabled={lineas.length === 1}
                      onClick={() => removeLinea(index)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Stack>

                  {(() => {
                    const prod = (productos ?? []).find(p => String(p.id) === linea.producto_id)
                    const unidad = prod?.unidad_medida ?? 'UNIDAD'
                    const lotesProd = (lotes ?? []).filter(lt => String(lt.producto_id) === linea.producto_id)
                    const subtotal = (Number(linea.cantidad_solicitada) || 0) * (Number(linea.precio_unitario) || 0)
                    return (
                      <Grid container spacing={2} alignItems="center">
                        <Grid size={{ xs: 12, sm: 6 }}>
                          <FormControl fullWidth size="small">
                            <InputLabel>Producto</InputLabel>
                            <Select
                              label="Producto"
                              value={linea.producto_id}
                              disabled={!!linea.de_armado}
                              onChange={e => { updateLinea(index, 'producto_id', e.target.value); updateLinea(index, 'lote_id', '') }}
                            >
                              <MenuItem value="">Seleccionar</MenuItem>
                              {(productos ?? []).map(p => (
                                <MenuItem key={p.id} value={String(p.id)}>
                                  {p.sku} — {p.nombre}
                                </MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        </Grid>

                        <Grid size={{ xs: 6, sm: 3 }}>
                          <TextField
                            label="Cantidad"
                            type="number"
                            fullWidth
                            size="small"
                            value={linea.cantidad_solicitada}
                            onChange={e => updateLinea(index, 'cantidad_solicitada', e.target.value)}
                            inputProps={{ min: 0 }}
                            InputProps={{ readOnly: !!linea.de_armado }}
                            helperText={equivalencia(Number(linea.cantidad_solicitada) || 0, niveles.get(Number(linea.producto_id)))
                              ? `= ${equivalencia(Number(linea.cantidad_solicitada) || 0, niveles.get(Number(linea.producto_id)))}`
                              : linea.de_armado ? 'Desde la selección' : undefined}
                          />
                        </Grid>

                        <Grid size={{ xs: 6, sm: 3 }}>
                          <TextField
                            label="Unidad"
                            fullWidth
                            size="small"
                            value={unidad}
                            InputProps={{ readOnly: true }}
                          />
                        </Grid>

                        <Grid size={{ xs: 12, sm: 6 }}>
                          <FormControl fullWidth size="small">
                            <InputLabel>Lote (opcional)</InputLabel>
                            <Select
                              label="Lote (opcional)"
                              value={linea.lote_id}
                              onChange={e => updateLinea(index, 'lote_id', e.target.value)}
                              disabled={!linea.producto_id}
                            >
                              <MenuItem value=""><em>Sin lote</em></MenuItem>
                              {lotesProd.map(lt => (
                                <MenuItem key={lt.id} value={String(lt.id)}>{lt.numero_lote}</MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        </Grid>

                        <Grid size={{ xs: 6, sm: 3 }}>
                          <TextField
                            label="Precio Unit."
                            type="number"
                            fullWidth
                            size="small"
                            value={linea.precio_unitario}
                            onChange={e => updateLinea(index, 'precio_unitario', e.target.value)}
                            inputProps={{ min: 0 }}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                          />
                        </Grid>

                        <Grid size={{ xs: 6, sm: 3 }}>
                          <TextField
                            label="Subtotal"
                            fullWidth
                            size="small"
                            value={`$ ${subtotal.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                            InputProps={{ readOnly: true }}
                            sx={{ '& .MuiInputBase-input': { fontWeight: 600 } }}
                          />
                        </Grid>
                      </Grid>
                    )
                  })()}
                </Box>
              ))}
              <Stack direction="row" justifyContent="flex-end" alignItems="baseline" spacing={1} sx={{ mt: 0.5, pr: 0.5 }}>
                <Typography variant="caption" color="text.secondary">Total pedido:</Typography>
                <Typography fontWeight={700} sx={{ color: WMS_COLOR }}>
                  $ {lineas.reduce((acc, l) => acc + (Number(l.cantidad_solicitada) || 0) * (Number(l.precio_unitario) || 0), 0).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </Typography>
              </Stack>
            </Box>

          </DialogContent>
          <DialogActions sx={{ px: 3, py: 2 }}>
            <Button onClick={() => setOpenOrdenDialog(false)}>
              Cancelar
            </Button>
            <Button
              variant="contained"
              sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1E3A8A' } }}
              onClick={handleCrearOrden}
              disabled={mutCrearOrden.isPending}
            >
              Crear Orden
            </Button>
          </DialogActions>
        </Dialog>

        {/* ── Dialog: Detalle de Orden de Salida ────────────────────────────── */}
        <Dialog
          open={!!detalleOrden}
          onClose={() => setDetalleOrden(null)}
          maxWidth="md"
          fullWidth
          PaperProps={{ sx: { borderRadius: 3 } }}
        >
          {detalleOrden && (() => {
            const estadoColor: Record<string, 'warning' | 'info' | 'primary' | 'success' | 'default' | 'error'> = {
              PENDIENTE: 'warning',
              EN_PICKING: 'info',
              EMPACANDO: 'primary',
              DESPACHADO: 'success',
              ENTREGADO: 'default',
              CANCELADO: 'error',
            }
            const detalles = detalleOrden.detalles ?? []
            const totalPedido = detalles.reduce(
              (acc, d) => acc + (d.cantidad_solicitada ?? 0) * (d.precio_unitario ?? 0),
              0,
            )
            const sectionHeaderSx = {
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: 0.4,
              textTransform: 'uppercase' as const,
              color: 'text.secondary',
            }
            const Campo = ({ label, value }: { label: string; value: ReactNode }) => (
              <Grid size={{ xs: 12, sm: 6 }}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" fontWeight={600}>{value}</Typography>
              </Grid>
            )

            return (
              <>
                <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 1 }}>
                  <Stack direction="row" alignItems="center" flexWrap="wrap" spacing={1}>
                    <span>Orden {detalleOrden.numero_orden}</span>
                    <Chip
                      size="small"
                      color={estadoColor[detalleOrden.estado] ?? 'default'}
                      label={detalleOrden.estado}
                    />
                    <Chip
                      size="small"
                      color={PRIORIDAD_CONFIG[detalleOrden.prioridad]?.color ?? 'default'}
                      label={PRIORIDAD_CONFIG[detalleOrden.prioridad]?.label ?? detalleOrden.prioridad}
                    />
                  </Stack>
                </DialogTitle>
                <DialogContent dividers sx={{ px: 3, py: 2.5 }}>

                  {/* Section 1 — Datos de la Orden */}
                  <Typography sx={{ ...sectionHeaderSx, mb: 1 }}>
                    DATOS DE LA ORDEN
                  </Typography>
                  <Grid container spacing={2}>
                    <Campo label="Cliente" value={detalleOrden.cliente?.nombre ?? '—'} />
                    <Campo label="Almacén" value={detalleOrden.almacen?.nombre ?? '—'} />
                    <Campo label="Fecha Emisión" value={formatFecha(detalleOrden.fecha_emision)} />
                    <Campo label="Fecha Requerida" value={formatFecha(detalleOrden.fecha_requerida)} />
                    <Campo label="Canal" value={detalleOrden.canal || '—'} />
                    <Campo
                      label="Prioridad"
                      value={PRIORIDAD_CONFIG[detalleOrden.prioridad]?.label ?? detalleOrden.prioridad}
                    />
                    <Campo label="Estado" value={detalleOrden.estado} />
                  </Grid>

                  <Divider sx={{ my: 2 }} />

                  {/* Section 2 — Líneas */}
                  <Typography sx={{ ...sectionHeaderSx, mb: 1 }}>
                    LÍNEAS
                  </Typography>

                  {detalles.length === 0 ? (
                    <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                      Esta orden no tiene líneas registradas.
                    </Typography>
                  ) : (
                    <Box sx={{ overflowX: 'auto' }}>
                      <Table size="small">
                        <TableHead>
                          <TableRow sx={{ bgcolor: alpha(WMS_COLOR, 0.06) }}>
                            <TableCell sx={{ fontWeight: 700 }}>Producto</TableCell>
                            <TableCell sx={{ fontWeight: 700 }} align="right">Solic.</TableCell>
                            <TableCell sx={{ fontWeight: 700 }} align="right">Prep.</TableCell>
                            <TableCell sx={{ fontWeight: 700 }} align="right">Desp.</TableCell>
                            <TableCell sx={{ fontWeight: 700 }} align="right">Precio</TableCell>
                            <TableCell sx={{ fontWeight: 700 }} align="right">Subtotal</TableCell>
                            <TableCell sx={{ fontWeight: 700 }}>Estado</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {detalles.map((d, i) => {
                            const solicitada = d.cantidad_solicitada ?? 0
                            const preparada = d.cantidad_preparada ?? 0
                            const precio = d.precio_unitario ?? 0
                            const subtotal = solicitada * precio
                            const progreso = solicitada > 0 ? (preparada / solicitada) * 100 : 0
                            return (
                              <TableRow key={d.producto_id ?? i} hover>
                                <TableCell>
                                  <Typography variant="body2" fontWeight={600}>
                                    {d.producto?.sku ?? '—'}
                                    {d.producto?.nombre ? ` — ${d.producto.nombre}` : ''}
                                  </Typography>
                                  <Box sx={{ mt: 0.5, maxWidth: 220 }}>
                                    <LinearProgress
                                      variant="determinate"
                                      value={progreso}
                                      sx={{ height: 6, borderRadius: 3 }}
                                    />
                                    <Typography variant="caption" color="text.secondary">
                                      {preparada}/{solicitada} preparado
                                    </Typography>
                                  </Box>
                                </TableCell>
                                <TableCell align="right">{solicitada}</TableCell>
                                <TableCell align="right">{preparada}</TableCell>
                                <TableCell align="right">{d.cantidad_despachada ?? 0}</TableCell>
                                <TableCell align="right">{formatMoneda(precio)}</TableCell>
                                <TableCell align="right">{formatMoneda(subtotal)}</TableCell>
                                <TableCell>
                                  {(() => {
                                    const e = ESTADO_LINEA[d.estado ?? ''] ?? { t: d.estado ?? '—', c: '#64748B' }
                                    return <Chip size="small" label={e.t} sx={{ fontWeight: 700, fontSize: 11, color: e.c, bgcolor: alpha(e.c, 0.1), border: `1px solid ${alpha(e.c, 0.35)}` }} />
                                  })()}
                                </TableCell>
                              </TableRow>
                            )
                          })}
                        </TableBody>
                      </Table>
                      <Stack direction="row" justifyContent="flex-end" alignItems="baseline" spacing={1} sx={{ mt: 1.5, pr: 0.5 }}>
                        <Typography variant="caption" color="text.secondary">Total pedido:</Typography>
                        <Typography fontWeight={700} sx={{ color: WMS_COLOR }}>
                          {formatMoneda(totalPedido)}
                        </Typography>
                      </Stack>
                    </Box>
                  )}

                </DialogContent>
                <DialogActions sx={{ px: 3, py: 2 }}>
                  <BotonPDF tipo="orden-salida" id={detalleOrden.id} etiqueta="Orden en PDF" />
                  <Button onClick={() => setDetalleOrden(null)}>
                    Cerrar
                  </Button>
                </DialogActions>
              </>
            )
          })()}
        </Dialog>

      </Box>
      {ejecutando && (
        <EjecutarPicking
          tarea={ejecutando}
          onCerrar={() => setEjecutando(null)}
          onConfirmado={() => {
            setEjecutando(null)
            queryClient.invalidateQueries({ queryKey: ['wms-tareas'] })
            queryClient.invalidateQueries({ queryKey: ['wms-ordenes'] })
          }}
        />
      )}
      <Dialog open={!!confirmando} onClose={() => setConfirmando(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Confirmar alistamiento</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
          <Typography fontSize={13} color="text.secondary">
            {confirmando?.detalle.producto?.sku} · {confirmando?.detalle.producto?.nombre} — en <b>{confirmando?.detalle.ubicacion?.codigo}</b>
          </Typography>
          <TextField autoFocus size="small" label="Escanee la ubicación" value={escaneo.ubicacion}
            onChange={e => setEscaneo({ ...escaneo, ubicacion: e.target.value })}
            helperText="Si escanea, el sistema rechaza una ubicación equivocada" />
          <TextField size="small" label="Escanee el producto (unidad, caja o máster) y Enter" value={escaneo.producto}
            onChange={e => setEscaneo({ ...escaneo, producto: e.target.value })}
            onKeyDown={async e => {
              if (e.key !== 'Enter' || !confirmando || !escaneo.producto.trim()) return
              e.preventDefault()
              const codigo = escaneo.producto.trim()
              try {
                const r = await api.get(`/wms/codigos/${encodeURIComponent(codigo)}`).then(x => x.data)
                if (r.producto_id !== confirmando.detalle.producto_id) {
                  setErrorLectura(`Producto equivocado: ${r.nombre}. La línea es ${confirmando.detalle.producto?.nombre}.`)
                  return
                }
                setErrorLectura('')
                // La primera lectura reemplaza lo sugerido; las siguientes suman.
                setEscaneo(x => ({ ...x, producto: codigo, cantidad: String((leyendo ? Number(x.cantidad) || 0 : 0) + r.unidades) }))
                setLeyendo(true)
              } catch (err: any) {
                setErrorLectura(err?.response?.data?.detail ?? `No se reconoce el código ${codigo}`)
              }
            }}
            error={!!errorLectura} helperText={errorLectura || 'Cada lectura suma: una caja de 12 suma 12'} />
          {confirmando && (() => {
            const nv = niveles.get(confirmando.detalle.producto_id) ?? []
            const sumar = (n: number) => {
              setEscaneo(x => ({ ...x, cantidad: String((leyendo ? Number(x.cantidad) || 0 : 0) + n) }))
              setLeyendo(true)
            }
            return (
              <Stack direction="row" gap={0.8} flexWrap="wrap">
                <Button size="small" variant="outlined" onClick={() => sumar(1)} sx={{ textTransform: 'none', fontWeight: 700 }}>+1 und</Button>
                {nv.filter(n => n.nivel !== 'UNIDAD').map(n => (
                  <Button key={n.nivel} size="small" variant="outlined" onClick={() => sumar(n.unidades)} sx={{ textTransform: 'none', fontWeight: 700 }}>
                    +1 {n.nombre.toLowerCase()} ({n.unidades})
                  </Button>
                ))}
                <Button size="small" color="inherit" onClick={() => { setEscaneo(x => ({ ...x, cantidad: '0' })); setLeyendo(true) }} sx={{ textTransform: 'none' }}>
                  Empezar en 0
                </Button>
              </Stack>
            )
          })()}
          <TextField size="small" type="number" label={`Cantidad alistada (de ${confirmando?.detalle.cantidad_solicitada ?? ''})`}
            value={escaneo.cantidad} onChange={e => { setEscaneo({ ...escaneo, cantidad: e.target.value }); setLeyendo(true) }}
            error={Number(escaneo.cantidad) > (confirmando?.detalle.cantidad_solicitada ?? 0)}
            helperText={Number(escaneo.cantidad) > (confirmando?.detalle.cantidad_solicitada ?? 0)
              ? 'Es más de lo solicitado'
              : [confirmando && equivalencia(Number(escaneo.cantidad) || 0, niveles.get(confirmando.detalle.producto_id))
                  ? `= ${equivalencia(Number(escaneo.cantidad) || 0, niveles.get(confirmando.detalle.producto_id))}` : '',
                 'Si alista menos, lo que sobra vuelve a quedar disponible'].filter(Boolean).join(' · ')} />
        </DialogContent>
        <DialogActions>
          <Button color="inherit" onClick={() => setConfirmando(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!(Number(escaneo.cantidad) > 0) || Number(escaneo.cantidad) > (confirmando?.detalle.cantidad_solicitada ?? 0) || mutConfirmarItem.isPending}
            onClick={() => confirmando && mutConfirmarItem.mutate({
              tareaId: confirmando.tareaId, detalle_id: confirmando.detalle.id, cantidad_pickeada: Number(escaneo.cantidad),
              ubicacion_codigo: escaneo.ubicacion.trim() || undefined, producto_codigo: escaneo.producto.trim() || undefined })}>
            Confirmar</Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
