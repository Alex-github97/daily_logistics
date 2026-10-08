import { useState } from 'react'
import {
  Box, Typography, Card, CardContent, Stack, Tabs, Tab, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Skeleton, Alert, MenuItem, InputLabel, Button, Chip, IconButton, Collapse, Dialog, DialogTitle, DialogContent, DialogActions, alpha,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import Inventory2Icon from '@mui/icons-material/Inventory2'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp'
import CheckIcon from '@mui/icons-material/Check'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient as api } from '@/api/client'
import OcupacionBodega from '@/components/wms/OcupacionBodega'
import { Layout } from '@/components/layout/Layout'

import { COLOR_MODULO } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'
import { aFecha } from '@/utils/fechas'
// ─── Interfaces ───────────────────────────────────────────────────────────────

interface ProductoRef {
  id: number
  sku: string
  nombre: string
  unidad_medida?: string
}

interface UbicacionRef {
  id: number
  codigo: string
  pasillo?: string
  estanteria?: string
  nivel?: string
  posicion?: string
}

interface LoteRef {
  id: number
  numero_lote: string
  fecha_vencimiento?: string | null
}

interface StockItem {
  id: number
  producto_id: number
  producto?: ProductoRef
  ubicacion_id: number
  ubicacion?: UbicacionRef
  lote_id: number | null
  lote?: LoteRef | null
  cantidad_disponible: number
  contenedor_codigo?: string | null
  cantidad_reservada: number
  cantidad_bloqueada: number
  updated_at?: string
}

// Historial de movimientos (ajustes / transferencias) — WMSMovimientoResponse
interface Movimiento {
  id: number
  tipo: string
  producto_id: number
  producto?: ProductoRef
  ubicacion_origen_id: number | null
  ubicacion_destino_id: number | null
  lote_id: number | null
  cantidad: number
  referencia_documento?: string | null
  usuario_id?: number | null
  notas?: string | null
  created_at: string
}

interface ConteoDetalle {
  id: number
  producto?: { sku?: string; nombre?: string }
  ubicacion?: { codigo?: string }
  cantidad_sistema: number
  cantidad_fisica: number | null
  diferencia: number | null
}

interface Conteo {
  id: number
  almacen?: { nombre?: string }
  tipo: 'CICLICO' | 'GENERAL' | 'DIRIGIDO'
  estado: string
  fecha_programada: string
  operario_id?: number
  detalles?: ConteoDetalle[]
}

interface Producto {
  id: number
  nombre: string
  sku: string
}

interface Ubicacion {
  id: number
  codigo: string
  almacen_nombre?: string
}

interface Almacen {
  id: number
  nombre: string
}

interface MotivoMovimiento {
  id: number
  nombre: string
  tipo: string
}

// ─── Constants ────────────────────────────────────────────────────────────────

const WMS_COLOR = COLOR_MODULO

const EMPTY_AJUSTE = {
  producto_id: '',
  ubicacion_id: '',
  lote_id: '',
  cantidad_nueva: '',
  motivo: '',
  // DISPONIBLE, o BLOQUEADO para ajustar lo retenido (dar de baja lo dañado en cuarentena).
  estado: 'DISPONIBLE',
}

const EMPTY_TRANSFERENCIA = {
  producto_id: '',
  ubicacion_origen_id: '',
  ubicacion_destino_id: '',
  lote_id: '',
  cantidad: '',
  notas: '',
  gestion_transporte: 'NINGUNA',   // NINGUNA | TMS
  descripcion_carga: '',
}

const EMPTY_CONTEO = {
  almacen_id: '',
  tipo: 'CICLICO',
  fecha_programada: '',
  notas: '',
}

const EMPTY_RESERVA = {
  inv_id: '',        // fila de inventario seleccionada (producto+ubicacion+lote)
  cantidad: '',
  accion: 'RESERVAR',
  motivo_id: '',     // motivo del catálogo configurable
  detalle: '',       // contexto libre adicional
}

const ACCIONES_RESERVA: { value: string; label: string }[] = [
  { value: 'RESERVAR', label: 'Reservar (disponible → reservada)' },
  { value: 'LIBERAR', label: 'Liberar reserva (reservada → disponible)' },
  { value: 'BLOQUEAR', label: 'Bloquear (disponible → bloqueada)' },
  { value: 'DESBLOQUEAR', label: 'Desbloquear (bloqueada → disponible)' },
]

// ─── Component ────────────────────────────────────────────────────────────────

export default function WMSInventario() {
  const queryClient = useQueryClient()

  // ── State ──────────────────────────────────────────────────────────────────

  const [tab, setTab] = useState(0)
  const [filtros, setFiltros] = useState({
    almacen_id: '',
    zona: '',
    producto: '',
  })
  const [ajusteForm, setAjusteForm] = useState({ ...EMPTY_AJUSTE })
  const [transForm, setTransForm] = useState({ ...EMPTY_TRANSFERENCIA })
  const [conteoForm, setConteoForm] = useState({ ...EMPTY_CONTEO })
  const [reservaForm, setReservaForm] = useState({ ...EMPTY_RESERVA })
  const [openConteoDialog, setOpenConteoDialog] = useState(false)
  const [expandedConteo, setExpandedConteo] = useState<number | null>(null)
  const [fisicaInput, setFisicaInput] = useState<Record<number, string>>({})
  const [detalleStock, setDetalleStock] = useState<StockItem | null>(null)
  const [detalleMov, setDetalleMov] = useState<Movimiento | null>(null)

  // ── Queries ─────────────────────────────────────────────────────────────────

  const stockQuery = useQuery<StockItem[]>({
    queryKey: ['wms-stock', filtros],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (filtros.almacen_id) params.almacen_id = filtros.almacen_id
      if (filtros.zona) params.zona = filtros.zona
      if (filtros.producto) params.producto = filtros.producto
      const res = await api.get('/wms/inventario/', { params })
      return res.data
    },
  })

  const ajustesQuery = useQuery<Movimiento[]>({
    queryKey: ['wms-ajustes'],
    queryFn: async () => {
      const res = await api.get('/wms/inventario/ajustes/')
      return res.data
    },
  })

  const transferenciasQuery = useQuery<Movimiento[]>({
    queryKey: ['wms-transferencias'],
    queryFn: async () => {
      const res = await api.get('/wms/inventario/transferencias/')
      return res.data
    },
  })

  const conteosQuery = useQuery<Conteo[]>({
    queryKey: ['wms-conteos'],
    queryFn: async () => {
      const res = await api.get('/wms/conteos/')
      return res.data
    },
  })

  const productosQuery = useQuery<Producto[]>({
    queryKey: ['wms-productos'],
    queryFn: async () => {
      const res = await api.get('/wms/productos/')
      return res.data
    },
  })

  const ubicacionesQuery = useQuery<Ubicacion[]>({
    queryKey: ['wms-ubicaciones'],
    queryFn: async () => {
      const res = await api.get('/wms/ubicaciones/')
      return res.data
    },
  })

  const almacenesQuery = useQuery<Almacen[]>({
    queryKey: ['wms-almacenes'],
    queryFn: async () => {
      const res = await api.get('/wms/almacenes/')
      return res.data
    },
  })

  const motivosQuery = useQuery<MotivoMovimiento[]>({
    queryKey: ['wms-motivos-movimiento'],
    queryFn: async () => {
      const res = await api.get('/wms/motivos-movimiento/', { params: { activo: true } })
      return res.data
    },
  })

  // ── Mutations ───────────────────────────────────────────────────────────────

  const mutAjuste = useMutation({
    mutationFn: (data: typeof EMPTY_AJUSTE) =>
      api.post('/wms/inventario/ajuste/', {
        producto_id: Number(data.producto_id),
        ubicacion_id: Number(data.ubicacion_id),
        lote_id: data.lote_id ? Number(data.lote_id) : null,
        cantidad_nueva: Number(data.cantidad_nueva),
        motivo: data.motivo || undefined,
        estado: data.estado,
      }),
    onSuccess: () => {
      toast.success('Ajuste registrado correctamente')
      setAjusteForm({ ...EMPTY_AJUSTE })
      queryClient.invalidateQueries({ queryKey: ['wms-stock'] })
      queryClient.invalidateQueries({ queryKey: ['wms-ajustes'] })
    },
    onError: (e: any) => { toast.error(mensajeDeError(e, 'Error al registrar el ajuste')) },
  })

  const mutTransferencia = useMutation({
    mutationFn: (data: typeof EMPTY_TRANSFERENCIA) =>
      api.post('/wms/inventario/transferencia/', {
        producto_id: Number(data.producto_id),
        ubicacion_origen_id: Number(data.ubicacion_origen_id),
        ubicacion_destino_id: Number(data.ubicacion_destino_id),
        lote_id: data.lote_id ? Number(data.lote_id) : null,
        cantidad: Number(data.cantidad),
        notas: data.notas || undefined,
        gestion_transporte: data.gestion_transporte,
        descripcion_carga: data.descripcion_carga || undefined,
      }).then(r => r.data),
    onSuccess: (mov: Movimiento) => {
      const ref = mov?.referencia_documento || ''
      // Entre almacenes es un traslado: queda en tránsito hasta que el destino lo recibe.
      if (ref.startsWith('TRL-')) toast.success(`Traslado ${ref} en tránsito: el destino lo recibe en WMS → Traslados`, { duration: 6000 })
      else if (ref.includes('TMS:')) toast.success(`Traslado registrado — viaje TMS ${ref.split('TMS:')[1]} creado`)
      else toast.success('Transferencia registrada correctamente')
      setTransForm({ ...EMPTY_TRANSFERENCIA })
      queryClient.invalidateQueries({ queryKey: ['wms-stock'] })
      queryClient.invalidateQueries({ queryKey: ['wms-transferencias'] })
    },
    onError: (e: any) => { toast.error(mensajeDeError(e, 'Error al registrar la transferencia')) },
  })

  const mutConteo = useMutation({
    mutationFn: (data: typeof EMPTY_CONTEO) =>
      api.post('/wms/conteos/', {
        almacen_id: Number(data.almacen_id),
        tipo: data.tipo,
        fecha_programada: data.fecha_programada || new Date().toISOString().slice(0, 10),
        notas: data.notas || undefined,
        detalles: [],
      }).then((r) => r.data),
    onSuccess: (creado: Conteo) => {
      const n = creado?.detalles?.length ?? 0
      toast.success(n > 0
        ? `Conteo creado — ${n} ítems listos para capturar el físico`
        : 'Conteo creado (el almacén no tiene stock para contar)')
      setConteoForm({ ...EMPTY_CONTEO })
      setOpenConteoDialog(false)
      queryClient.invalidateQueries({ queryKey: ['wms-conteos'] })
      // Despliega automáticamente el conteo recién creado para capturar el físico
      if (creado?.id) setExpandedConteo(creado.id)
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg = typeof detail === 'string' ? detail
        : Array.isArray(detail) ? detail.map((d: { msg?: string }) => d?.msg ?? '').join('; ')
        : 'Error al crear el conteo'
      toast.error(msg)
    },
  })

  const mutCompletarConteo = useMutation({
    mutationFn: (id: number) =>
      api.put(`/wms/conteos/${id}/completar`),
    onSuccess: () => {
      toast.success('Conteo completado — inventario reconciliado')
      queryClient.invalidateQueries({ queryKey: ['wms-conteos'] })
    },
    onError: (e: any) => { toast.error(mensajeDeError(e, 'Error al completar el conteo')) },
  })

  const mutCapturarConteo = useMutation({
    mutationFn: ({ conteoId, detalleId, cantidad_fisica }: { conteoId: number; detalleId: number; cantidad_fisica: number }) =>
      api.put(`/wms/conteos/${conteoId}/detalles/${detalleId}`, { cantidad_fisica }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wms-conteos'] })
    },
    onError: (e: any) => { toast.error(mensajeDeError(e, 'Error al guardar la cantidad física')) },
  })

  const mutReservaBloqueo = useMutation({
    mutationFn: (payload: {
      producto_id: number; ubicacion_id: number; lote_id: number | null
      cantidad: number; accion: string; motivo?: string
    }) => api.post('/wms/inventario/reserva-bloqueo/', payload),
    onSuccess: () => {
      toast.success('Movimiento de reserva/bloqueo aplicado')
      setReservaForm((f) => ({ ...EMPTY_RESERVA, accion: f.accion }))
      queryClient.invalidateQueries({ queryKey: ['wms-stock'] })
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Error al aplicar el movimiento')
    },
  })

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const stockItems = stockQuery.data ?? []
  const ajustes = ajustesQuery.data ?? []
  const transferencias = transferenciasQuery.data ?? []
  const conteos = conteosQuery.data ?? []
  const productos = productosQuery.data ?? []
  const ubicaciones = ubicacionesQuery.data ?? []
  const almacenes = almacenesQuery.data ?? []
  const motivos = motivosQuery.data ?? []

  const totalDisponible = stockItems.reduce((s, i) => s + i.cantidad_disponible, 0)
  const totalReservada = stockItems.reduce((s, i) => s + i.cantidad_reservada, 0)
  const totalBloqueada = stockItems.reduce((s, i) => s + i.cantidad_bloqueada, 0)
  const totalGeneral = totalDisponible + totalReservada + totalBloqueada

  const tipoBadgeColor = (tipo: string) => {
    if (tipo === 'CICLICO') return 'primary'
    if (tipo === 'GENERAL') return 'success' // teal-ish via MUI success
    if (tipo === 'DIRIGIDO') return 'secondary'
    return 'default'
  }

  const estadoBadgeColor = (
    estado: string
  ): 'warning' | 'info' | 'success' | 'error' | 'default' => {
    if (estado === 'PROGRAMADO') return 'warning'
    if (estado === 'EN_PROCESO') return 'info'
    if (estado === 'COMPLETO') return 'success'
    if (estado === 'CANCELADO') return 'error'
    return 'default'
  }

  const formatDate = (dateStr: string) => {
    try {
      return aFecha(dateStr).toLocaleDateString('es-CO')
    } catch {
      return dateStr
    }
  }

  const ubicacionLabel = (id: number | null | undefined) => {
    if (id == null) return '-'
    const u = ubicaciones.find((x) => x.id === id)
    return u ? u.codigo : `#${id}`
  }

  const isNum = (v: string) => v.trim() !== '' && !Number.isNaN(Number(v))

  const ajusteValido =
    isNum(ajusteForm.producto_id) &&
    isNum(ajusteForm.ubicacion_id) &&
    isNum(ajusteForm.cantidad_nueva) &&
    Number(ajusteForm.cantidad_nueva) >= 0

  const transValido =
    isNum(transForm.producto_id) &&
    isNum(transForm.ubicacion_origen_id) &&
    isNum(transForm.ubicacion_destino_id) &&
    isNum(transForm.cantidad) &&
    Number(transForm.cantidad) > 0

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <Layout>
      <Box sx={{ p: 3, bgcolor: '#F0F2F5', minHeight: '100vh' }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          <Inventory2Icon sx={{ color: WMS_COLOR, fontSize: 36 }} />
          <Box>
            <Typography variant="h5" fontWeight={700} color={WMS_COLOR}>
              Gestión de Inventario WMS
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Control de stock, ajustes, transferencias y conteos
            </Typography>
          </Box>
        </Box>

        {/* Tabs */}
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{
            mb: 3,
            borderBottom: 1,
            borderColor: 'divider',
            '& .MuiTabs-indicator': { bgcolor: WMS_COLOR },
          }}
        >
          {['Stock en Tiempo Real', 'Ajustes', 'Transferencias', 'Conteos de Inventario', 'Reservas y Bloqueos', 'Ocupación de bodega (m²)'].map(
            (label) => (
              <Tab
                key={label}
                label={label}
                sx={{
                  textTransform: 'none',
                  fontWeight: 600,
                  '&.Mui-selected': { color: WMS_COLOR },
                }}
              />
            )
          )}
        </Tabs>

        {tab === 5 && <OcupacionBodega />}

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* TAB 0 — Stock en Tiempo Real                                      */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        {tab === 0 && (
          <Box>
            {/* Filter card */}
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Grid container spacing={2} alignItems="center">
                  <Grid size={{ xs: 12, md: 4 }}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Almacén</InputLabel>
                      <Select
                        label="Almacén"
                        value={filtros.almacen_id}
                        onChange={(e) =>
                          setFiltros((f) => ({ ...f, almacen_id: e.target.value }))
                        }
                      >
                        <MenuItem value="">Todos</MenuItem>
                        {almacenes.map((a) => (
                          <MenuItem key={a.id} value={String(a.id)}>
                            {a.nombre}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid size={{ xs: 12, md: 4 }}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Zona"
                      value={filtros.zona}
                      onChange={(e) => setFiltros((f) => ({ ...f, zona: e.target.value }))}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 4 }}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Buscar producto"
                      value={filtros.producto}
                      onChange={(e) =>
                        setFiltros((f) => ({ ...f, producto: e.target.value }))
                      }
                    />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Stock error */}
            {stockQuery.isError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                Error al cargar el stock
              </Alert>
            )}

            {/* Stock table */}
            <Card>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: alpha(WMS_COLOR, 0.08) }}>
                      <TableCell sx={{ fontWeight: 700 }}>SKU</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Producto</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Ubicación</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Lote</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Estiba</TableCell>
                      <TableCell sx={{ fontWeight: 700 }} align="right">
                        Disponible
                      </TableCell>
                      <TableCell sx={{ fontWeight: 700 }} align="right">
                        Reservada
                      </TableCell>
                      <TableCell sx={{ fontWeight: 700 }} align="right">
                        Bloqueada
                      </TableCell>
                      <TableCell sx={{ fontWeight: 700 }} align="right">
                        Total
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {stockQuery.isLoading
                      ? Array.from({ length: 6 }).map((_, idx) => (
                          <TableRow key={idx}>
                            {Array.from({ length: 8 }).map((__, ci) => (
                              <TableCell key={ci}>
                                <Skeleton variant="text" />
                              </TableCell>
                            ))}
                          </TableRow>
                        ))
                      : stockItems.map((item) => {
                          const total =
                            item.cantidad_disponible +
                            item.cantidad_reservada +
                            item.cantidad_bloqueada
                          return (
                            <TableRow
                              key={item.id}
                              hover
                              onClick={() => setDetalleStock(item)}
                              sx={{ cursor: 'pointer' }}
                            >
                              <TableCell>
                                <Typography variant="body2" fontFamily="monospace">
                                  {item.producto?.sku ?? '-'}
                                </Typography>
                              </TableCell>
                              <TableCell>{item.producto?.nombre ?? '-'}</TableCell>
                              <TableCell>
                                {item.ubicacion?.codigo ?? '-'}
                                {item.ubicacion &&
                                (item.ubicacion.pasillo ||
                                  item.ubicacion.estanteria ||
                                  item.ubicacion.nivel ||
                                  item.ubicacion.posicion) ? (
                                  <Typography variant="caption" color="text.secondary" display="block">
                                    {[
                                      item.ubicacion.pasillo,
                                      item.ubicacion.estanteria,
                                      item.ubicacion.nivel,
                                      item.ubicacion.posicion,
                                    ]
                                      .filter(Boolean)
                                      .join(' · ')}
                                  </Typography>
                                ) : null}
                              </TableCell>
                              <TableCell>{item.lote?.numero_lote ?? '-'}</TableCell>
                              <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{item.contenedor_codigo ?? '-'}</TableCell>
                              <TableCell align="right">
                                <Chip
                                  label={item.cantidad_disponible}
                                  size="small"
                                  color="success"
                                  variant="outlined"
                                />
                              </TableCell>
                              <TableCell align="right">
                                <Chip
                                  label={item.cantidad_reservada}
                                  size="small"
                                  color="warning"
                                  variant="outlined"
                                />
                              </TableCell>
                              <TableCell align="right">
                                <Chip
                                  label={item.cantidad_bloqueada}
                                  size="small"
                                  color="error"
                                  variant="outlined"
                                />
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="body2" fontWeight={600}>
                                  {total}
                                </Typography>
                              </TableCell>
                            </TableRow>
                          )
                        })}

                    {/* Summary row */}
                    {!stockQuery.isLoading && stockItems.length > 0 && (
                      <TableRow
                        sx={{ bgcolor: alpha(WMS_COLOR, 0.05) }}
                      >
                        <TableCell colSpan={5} sx={{ fontWeight: 700 }}>
                          Stock Total
                        </TableCell>
                        <TableCell align="right">
                          <Chip
                            label={totalDisponible}
                            size="small"
                            color="success"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Chip
                            label={totalReservada}
                            size="small"
                            color="warning"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Chip
                            label={totalBloqueada}
                            size="small"
                            color="error"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography fontWeight={700}>{totalGeneral}</Typography>
                        </TableCell>
                      </TableRow>
                    )}

                    {!stockQuery.isLoading && stockItems.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={9} align="center">
                          <Typography color="text.secondary" py={2}>
                            No hay registros de stock
                          </Typography>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Box>
            </Card>
          </Box>
        )}

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* TAB 1 — Ajustes                                                   */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        {tab === 1 && (
          <Grid container spacing={2}>
            {/* Left: Nuevo Ajuste */}
            <Grid size={{ xs: 12, md: 5 }}>
              <Card>
                <CardContent>
                  <Box
                    sx={{
                      borderRadius: 2,
                      p: 2,
                      border: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Typography
                      sx={{
                        fontSize: 12,
                        fontWeight: 700,
                        letterSpacing: 0.4,
                        textTransform: 'uppercase',
                        color: 'text.secondary',
                        mb: 1,
                      }}
                    >
                      REGISTRAR AJUSTE
                    </Typography>

                    <Grid container spacing={2}>
                      <Grid size={{ xs: 12 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Producto</InputLabel>
                          <Select
                            label="Producto"
                            value={ajusteForm.producto_id}
                            onChange={(e) =>
                              setAjusteForm((f) => ({ ...f, producto_id: e.target.value }))
                            }
                          >
                            <MenuItem value="">Seleccionar...</MenuItem>
                            {productos.map((p) => (
                              <MenuItem key={p.id} value={String(p.id)}>
                                {p.sku} — {p.nombre}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Ubicación</InputLabel>
                          <Select
                            label="Ubicación"
                            value={ajusteForm.ubicacion_id}
                            onChange={(e) =>
                              setAjusteForm((f) => ({ ...f, ubicacion_id: e.target.value }))
                            }
                          >
                            <MenuItem value="">Seleccionar...</MenuItem>
                            {ubicaciones.map((u) => (
                              <MenuItem key={u.id} value={String(u.id)}>
                                {u.codigo}
                                {u.almacen_nombre ? ` (${u.almacen_nombre})` : ''}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField
                          fullWidth
                          size="small"
                          label="Lote ID (opcional)"
                          value={ajusteForm.lote_id}
                          onChange={(e) =>
                            setAjusteForm((f) => ({ ...f, lote_id: e.target.value }))
                          }
                        />
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField
                          select
                          fullWidth
                          size="small"
                          label="Qué se ajusta"
                          value={ajusteForm.estado}
                          helperText={ajusteForm.estado === 'BLOQUEADO'
                            ? 'Lo retenido (cuarentena): llevarlo a 0 es dar de baja lo dañado'
                            : 'Lo disponible para vender y alistar'}
                          onChange={(e) => setAjusteForm((f) => ({ ...f, estado: e.target.value }))}
                        >
                          <MenuItem value="DISPONIBLE">Disponible</MenuItem>
                          <MenuItem value="BLOQUEADO">Retenido / cuarentena</MenuItem>
                        </TextField>
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField
                          fullWidth
                          size="small"
                          label="Nueva cantidad (stock resultante)"
                          type="number"
                          helperText="Si la mercancía es propia, Finanzas registra la diferencia como merma o sobrante"
                          inputProps={{ min: 0 }}
                          value={ajusteForm.cantidad_nueva}
                          onChange={(e) =>
                            setAjusteForm((f) => ({ ...f, cantidad_nueva: e.target.value }))
                          }
                        />
                      </Grid>

                      <Grid size={{ xs: 12 }}>
                        <TextField
                          fullWidth
                          size="small"
                          label="Motivo"
                          multiline
                          rows={2}
                          value={ajusteForm.motivo}
                          onChange={(e) =>
                            setAjusteForm((f) => ({ ...f, motivo: e.target.value }))
                          }
                        />
                      </Grid>

                      <Grid size={{ xs: 12 }} sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
                        <Button
                          variant="contained"
                          disabled={mutAjuste.isPending || !ajusteValido}
                          onClick={() => mutAjuste.mutate(ajusteForm)}
                          sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1e3a8a' } }}
                        >
                          {mutAjuste.isPending ? 'Registrando...' : 'Registrar Ajuste'}
                        </Button>
                      </Grid>
                    </Grid>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* Right: Historial */}
            <Grid size={{ xs: 12, md: 7 }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" fontWeight={700} mb={2}>
                    Historial de Ajustes
                  </Typography>

                  {ajustesQuery.isError && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      Error al cargar los ajustes
                    </Alert>
                  )}

                  <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow sx={{ bgcolor: alpha(WMS_COLOR, 0.08) }}>
                          <TableCell sx={{ fontWeight: 700 }}>Producto</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Ubicación</TableCell>
                          <TableCell sx={{ fontWeight: 700 }} align="right">
                            Cantidad
                          </TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Referencia</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Fecha</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Notas</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {ajustesQuery.isLoading
                          ? Array.from({ length: 5 }).map((_, idx) => (
                              <TableRow key={idx}>
                                {Array.from({ length: 6 }).map((__, ci) => (
                                  <TableCell key={ci}>
                                    <Skeleton variant="text" />
                                  </TableCell>
                                ))}
                              </TableRow>
                            ))
                          : ajustes.map((a) => (
                              <TableRow
                                key={a.id}
                                hover
                                onClick={() => setDetalleMov(a)}
                                sx={{ cursor: 'pointer' }}
                              >
                                <TableCell>{a.producto?.nombre ?? `#${a.producto_id}`}</TableCell>
                                <TableCell>
                                  {ubicacionLabel(a.ubicacion_destino_id ?? a.ubicacion_origen_id)}
                                </TableCell>
                                <TableCell align="right">
                                  <Typography variant="body2" fontWeight={600}>
                                    {a.cantidad}
                                  </Typography>
                                </TableCell>
                                <TableCell>{a.referencia_documento ?? '-'}</TableCell>
                                <TableCell>{formatDate(a.created_at)}</TableCell>
                                <TableCell>{a.notas ?? '-'}</TableCell>
                              </TableRow>
                            ))}
                        {!ajustesQuery.isLoading && ajustes.length === 0 && (
                          <TableRow>
                            <TableCell colSpan={6} align="center">
                              <Typography color="text.secondary" py={2}>
                                Sin ajustes registrados
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* TAB 2 — Transferencias                                            */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        {tab === 2 && (
          <Grid container spacing={2}>
            {/* Left: Nueva Transferencia */}
            <Grid size={{ xs: 12, md: 5 }}>
              <Card>
                <CardContent>
                  <Box
                    sx={{
                      borderRadius: 2,
                      p: 2,
                      border: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Typography
                      sx={{
                        fontSize: 12,
                        fontWeight: 700,
                        letterSpacing: 0.4,
                        textTransform: 'uppercase',
                        color: 'text.secondary',
                        mb: 1,
                      }}
                    >
                      REGISTRAR TRANSFERENCIA
                    </Typography>

                    <Grid container spacing={2}>
                      <Grid size={{ xs: 12 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Producto</InputLabel>
                          <Select
                            label="Producto"
                            value={transForm.producto_id}
                            onChange={(e) =>
                              setTransForm((f) => ({ ...f, producto_id: e.target.value }))
                            }
                          >
                            <MenuItem value="">Seleccionar...</MenuItem>
                            {productos.map((p) => (
                              <MenuItem key={p.id} value={String(p.id)}>
                                {p.sku} — {p.nombre}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Ubicación Origen</InputLabel>
                          <Select
                            label="Ubicación Origen"
                            value={transForm.ubicacion_origen_id}
                            onChange={(e) =>
                              setTransForm((f) => ({
                                ...f,
                                ubicacion_origen_id: e.target.value,
                              }))
                            }
                          >
                            <MenuItem value="">Seleccionar...</MenuItem>
                            {ubicaciones.map((u) => (
                              <MenuItem key={u.id} value={String(u.id)}>
                                {u.codigo}
                                {u.almacen_nombre ? ` (${u.almacen_nombre})` : ''}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Ubicación Destino</InputLabel>
                          <Select
                            label="Ubicación Destino"
                            value={transForm.ubicacion_destino_id}
                            onChange={(e) =>
                              setTransForm((f) => ({
                                ...f,
                                ubicacion_destino_id: e.target.value,
                              }))
                            }
                          >
                            <MenuItem value="">Seleccionar...</MenuItem>
                            {ubicaciones.map((u) => (
                              <MenuItem key={u.id} value={String(u.id)}>
                                {u.codigo}
                                {u.almacen_nombre ? ` (${u.almacen_nombre})` : ''}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField
                          fullWidth
                          size="small"
                          label="Lote ID (opcional)"
                          value={transForm.lote_id}
                          onChange={(e) =>
                            setTransForm((f) => ({ ...f, lote_id: e.target.value }))
                          }
                        />
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField
                          fullWidth
                          size="small"
                          label="Cantidad"
                          type="number"
                          value={transForm.cantidad}
                          onChange={(e) =>
                            setTransForm((f) => ({ ...f, cantidad: e.target.value }))
                          }
                        />
                      </Grid>

                      <Grid size={{ xs: 12 }}>
                        <TextField
                          fullWidth
                          size="small"
                          label="Notas"
                          multiline
                          rows={2}
                          value={transForm.notas}
                          onChange={(e) =>
                            setTransForm((f) => ({ ...f, notas: e.target.value }))
                          }
                        />
                      </Grid>

                      <Grid size={{ xs: 12, sm: 6 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Gestión de transporte</InputLabel>
                          <Select
                            label="Gestión de transporte"
                            value={transForm.gestion_transporte}
                            onChange={(e) => setTransForm((f) => ({ ...f, gestion_transporte: e.target.value }))}
                          >
                            <MenuItem value="NINGUNA">No gestionar en la plataforma</MenuItem>
                            <MenuItem value="TMS">Gestionar por TMS (crea viaje)</MenuItem>
                          </Select>
                        </FormControl>
                      </Grid>
                      {transForm.gestion_transporte === 'TMS' && (
                        <Grid size={{ xs: 12, sm: 6 }}>
                          <TextField
                            fullWidth size="small" label="Descripción de la carga"
                            value={transForm.descripcion_carga}
                            onChange={(e) => setTransForm((f) => ({ ...f, descripcion_carga: e.target.value }))}
                          />
                        </Grid>
                      )}
                      {transForm.gestion_transporte === 'TMS' && (
                        <Grid size={{ xs: 12 }}>
                          <Alert severity="info" sx={{ py: 0 }}>
                            Se creará un <b>viaje en el módulo TMS</b> (origen y destino según los almacenes de las ubicaciones) para gestionar el transporte de este traslado.
                          </Alert>
                        </Grid>
                      )}

                      <Grid size={{ xs: 12 }} sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
                        <Button
                          variant="contained"
                          disabled={mutTransferencia.isPending || !transValido}
                          onClick={() => mutTransferencia.mutate(transForm)}
                          sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1e3a8a' } }}
                        >
                          {mutTransferencia.isPending ? 'Registrando...' : 'Registrar Transferencia'}
                        </Button>
                      </Grid>
                    </Grid>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* Right: Transferencias Recientes */}
            <Grid size={{ xs: 12, md: 7 }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" fontWeight={700} mb={2}>
                    Transferencias Recientes
                  </Typography>

                  {transferenciasQuery.isError && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      Error al cargar las transferencias
                    </Alert>
                  )}

                  <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow sx={{ bgcolor: alpha(WMS_COLOR, 0.08) }}>
                          <TableCell sx={{ fontWeight: 700 }}>Producto</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Origen</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Destino</TableCell>
                          <TableCell sx={{ fontWeight: 700 }} align="right">
                            Cantidad
                          </TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Fecha</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Notas</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {transferenciasQuery.isLoading
                          ? Array.from({ length: 5 }).map((_, idx) => (
                              <TableRow key={idx}>
                                {Array.from({ length: 6 }).map((__, ci) => (
                                  <TableCell key={ci}>
                                    <Skeleton variant="text" />
                                  </TableCell>
                                ))}
                              </TableRow>
                            ))
                          : transferencias.map((t) => (
                              <TableRow
                                key={t.id}
                                hover
                                onClick={() => setDetalleMov(t)}
                                sx={{ cursor: 'pointer' }}
                              >
                                <TableCell>{t.producto?.nombre ?? `#${t.producto_id}`}</TableCell>
                                <TableCell>{ubicacionLabel(t.ubicacion_origen_id)}</TableCell>
                                <TableCell>{ubicacionLabel(t.ubicacion_destino_id)}</TableCell>
                                <TableCell align="right">
                                  <Typography variant="body2" fontWeight={600}>
                                    {t.cantidad}
                                  </Typography>
                                </TableCell>
                                <TableCell>{formatDate(t.created_at)}</TableCell>
                                <TableCell>{t.notas ?? '-'}</TableCell>
                              </TableRow>
                            ))}
                        {!transferenciasQuery.isLoading && transferencias.length === 0 && (
                          <TableRow>
                            <TableCell colSpan={6} align="center">
                              <Typography color="text.secondary" py={2}>
                                Sin transferencias registradas
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* TAB 3 — Conteos de Inventario                                     */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        {tab === 3 && (
          <Box>
            {/* Header row */}
            <Box
              sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}
            >
              <Typography variant="h6" fontWeight={700}>
                Conteos de Inventario
              </Typography>
              <Button
                variant="contained"
                onClick={() => setOpenConteoDialog(true)}
                sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1e3a8a' } }}
              >
                Nuevo Conteo
              </Button>
            </Box>

            {conteosQuery.isError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                Error al cargar los conteos
              </Alert>
            )}

            <Card>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: alpha(WMS_COLOR, 0.08) }}>
                      <TableCell sx={{ width: 48 }} />
                      <TableCell sx={{ fontWeight: 700 }}>Almacén</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Tipo</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Estado</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Fecha Programada</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Operario</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>Acciones</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {conteosQuery.isLoading
                      ? Array.from({ length: 4 }).map((_, idx) => (
                          <TableRow key={idx}>
                            {Array.from({ length: 7 }).map((__, ci) => (
                              <TableCell key={ci}>
                                <Skeleton variant="text" />
                              </TableCell>
                            ))}
                          </TableRow>
                        ))
                      : conteos.map((conteo) => (
                          <>
                            <TableRow key={conteo.id} hover>
                              <TableCell>
                                <IconButton
                                  size="small"
                                  onClick={() =>
                                    setExpandedConteo(
                                      expandedConteo === conteo.id ? null : conteo.id
                                    )
                                  }
                                >
                                  {expandedConteo === conteo.id ? (
                                    <KeyboardArrowUpIcon fontSize="small" />
                                  ) : (
                                    <KeyboardArrowDownIcon fontSize="small" />
                                  )}
                                </IconButton>
                              </TableCell>
                              <TableCell>{conteo.almacen?.nombre ?? '-'}</TableCell>
                              <TableCell>
                                <Chip
                                  label={conteo.tipo}
                                  size="small"
                                  color={tipoBadgeColor(conteo.tipo) as 'primary' | 'success' | 'secondary' | 'default'}
                                  variant="outlined"
                                />
                              </TableCell>
                              <TableCell>
                                <Chip
                                  label={conteo.estado}
                                  size="small"
                                  color={estadoBadgeColor(conteo.estado)}
                                />
                              </TableCell>
                              <TableCell>{formatDate(conteo.fecha_programada)}</TableCell>
                              <TableCell>{conteo.operario_id ? `#${conteo.operario_id}` : '-'}</TableCell>
                              <TableCell>
                                {conteo.estado !== 'COMPLETO' && conteo.estado !== 'CANCELADO' && (
                                  <Stack direction="row" spacing={1}>
                                    <Button
                                      size="small"
                                      variant="text"
                                      onClick={() =>
                                        setExpandedConteo(
                                          expandedConteo === conteo.id ? null : conteo.id
                                        )
                                      }
                                    >
                                      Capturar
                                    </Button>
                                    <Button
                                      size="small"
                                      variant="outlined"
                                      color="success"
                                      disabled={
                                        mutCompletarConteo.isPending ||
                                        !(conteo.detalles ?? []).some((d) => d.cantidad_fisica !== null)
                                      }
                                      onClick={() => mutCompletarConteo.mutate(conteo.id)}
                                    >
                                      Completar
                                    </Button>
                                  </Stack>
                                )}
                              </TableCell>
                            </TableRow>

                            {/* Expandable detail row */}
                            <TableRow key={`detail-${conteo.id}`}>
                              <TableCell colSpan={7} sx={{ p: 0, border: 0 }}>
                                <Collapse
                                  in={expandedConteo === conteo.id}
                                  timeout="auto"
                                  unmountOnExit
                                >
                                  <Box
                                    sx={{
                                      bgcolor: alpha(WMS_COLOR, 0.03),
                                      p: 2,
                                      borderTop: `1px solid ${alpha(WMS_COLOR, 0.15)}`,
                                    }}
                                  >
                                    <Typography
                                      variant="subtitle2"
                                      fontWeight={700}
                                      mb={1}
                                      color={WMS_COLOR}
                                    >
                                      Detalle del Conteo
                                    </Typography>
                                    {(() => {
                                      const dets = conteo.detalles ?? []
                                      const capturados = dets.filter((d) => d.cantidad_fisica !== null)
                                      const novedades = capturados.filter((d) => (d.diferencia ?? 0) !== 0)
                                      if (novedades.length > 0) {
                                        return (
                                          <Alert severity="warning" sx={{ mb: 1.5 }}>
                                            <strong>{novedades.length}</strong> ítem(s) con novedad (físico ≠ sistema):{' '}
                                            {novedades.slice(0, 4).map((d) => `${d.producto?.nombre ?? d.producto?.sku ?? 'ítem'} (${(d.diferencia ?? 0) > 0 ? '+' : ''}${d.diferencia})`).join(', ')}
                                            {novedades.length > 4 ? '…' : ''}. Al completar se ajustará el inventario.
                                          </Alert>
                                        )
                                      }
                                      if (capturados.length > 0 && capturados.length === dets.length) {
                                        return <Alert severity="success" sx={{ mb: 1.5 }}>Conteo sin novedades: el físico coincide con el sistema en todos los ítems.</Alert>
                                      }
                                      if (dets.length > 0) {
                                        return <Alert severity="info" sx={{ mb: 1.5 }}>Captura la cantidad física de cada ítem; las diferencias se marcarán como novedad.</Alert>
                                      }
                                      return null
                                    })()}
                                    {conteo.detalles && conteo.detalles.length > 0 ? (
                                      <Table size="small">
                                        <TableHead>
                                          <TableRow>
                                            <TableCell sx={{ fontWeight: 600 }}>Producto</TableCell>
                                            <TableCell sx={{ fontWeight: 600 }}>Ubicación</TableCell>
                                            <TableCell sx={{ fontWeight: 600 }} align="right">
                                              Sistema
                                            </TableCell>
                                            <TableCell sx={{ fontWeight: 600 }} align="right">
                                              Física
                                            </TableCell>
                                            <TableCell sx={{ fontWeight: 600 }} align="right">
                                              Diferencia
                                            </TableCell>
                                          </TableRow>
                                        </TableHead>
                                        <TableBody>
                                          {conteo.detalles.map((d) => {
                                            const editable = conteo.estado !== 'COMPLETO' && conteo.estado !== 'CANCELADO'
                                            const inputVal = fisicaInput[d.id] ?? (d.cantidad_fisica ?? '').toString()
                                            const guardar = () => {
                                              const v = inputVal.trim()
                                              if (v === '' || Number(v) < 0) return
                                              if (Number(v) === d.cantidad_fisica) return
                                              mutCapturarConteo.mutate({ conteoId: conteo.id, detalleId: d.id, cantidad_fisica: Number(v) })
                                            }
                                            return (
                                            <TableRow key={d.id}>
                                              <TableCell>{d.producto?.nombre ?? d.producto?.sku ?? '-'}</TableCell>
                                              <TableCell>{d.ubicacion?.codigo ?? '-'}</TableCell>
                                              <TableCell align="right">
                                                {d.cantidad_sistema}
                                              </TableCell>
                                              <TableCell align="right">
                                                {editable ? (
                                                  <TextField
                                                    type="number"
                                                    size="small"
                                                    variant="standard"
                                                    value={inputVal}
                                                    placeholder="—"
                                                    onChange={(e) => setFisicaInput((prev) => ({ ...prev, [d.id]: e.target.value }))}
                                                    onBlur={guardar}
                                                    onKeyDown={(e) => { if (e.key === 'Enter') { guardar(); (e.target as HTMLInputElement).blur() } }}
                                                    inputProps={{ min: 0, style: { textAlign: 'right', width: 70 } }}
                                                  />
                                                ) : (
                                                  d.cantidad_fisica ?? '-'
                                                )}
                                              </TableCell>
                                              <TableCell align="right">
                                                {d.cantidad_fisica === null ? (
                                                  <Typography variant="caption" color="text.disabled">Pendiente</Typography>
                                                ) : d.diferencia !== null && d.diferencia !== 0 ? (
                                                  <Chip
                                                    label={d.diferencia > 0 ? `+${d.diferencia}` : d.diferencia}
                                                    size="small"
                                                    color="error"
                                                    variant="outlined"
                                                  />
                                                ) : (
                                                  <Chip
                                                    icon={<CheckIcon />}
                                                    label="OK"
                                                    size="small"
                                                    color="success"
                                                    variant="outlined"
                                                  />
                                                )}
                                              </TableCell>
                                            </TableRow>
                                          )})}
                                        </TableBody>
                                      </Table>
                                    ) : (
                                      <Typography color="text.secondary" variant="body2">
                                        Sin detalle disponible
                                      </Typography>
                                    )}
                                  </Box>
                                </Collapse>
                              </TableCell>
                            </TableRow>
                          </>
                        ))}

                    {!conteosQuery.isLoading && conteos.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} align="center">
                          <Typography color="text.secondary" py={2}>
                            Sin conteos registrados
                          </Typography>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Box>
            </Card>
          </Box>
        )}

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* TAB 4 — Reservas y Bloqueos                                       */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        {tab === 4 && (() => {
          const invSel = stockItems.find((i) => String(i.id) === reservaForm.inv_id)
          const cantNum = Number(reservaForm.cantidad)
          const reservaValida = !!invSel && cantNum > 0
          const invLabel = (i: StockItem) =>
            `${i.producto?.sku ?? '#' + i.producto_id} — ${i.producto?.nombre ?? ''} @ ${i.ubicacion?.codigo ?? '#' + i.ubicacion_id}` +
            (i.lote?.numero_lote ? ` · ${i.lote.numero_lote}` : '') +
            `  (disp ${i.cantidad_disponible} / res ${i.cantidad_reservada} / blq ${i.cantidad_bloqueada})`
          // Los motivos aplicables dependen de la acción: reservar/liberar → RESERVA; bloquear/desbloquear → BLOQUEO
          const tipoMotivo = reservaForm.accion === 'BLOQUEAR' || reservaForm.accion === 'DESBLOQUEAR' ? 'BLOQUEO' : 'RESERVA'
          const motivosFiltrados = motivos.filter((m) => m.tipo === tipoMotivo)
          const aplicar = () => {
            if (!invSel) return
            const motivoNombre = motivos.find((m) => String(m.id) === reservaForm.motivo_id)?.nombre
            const motivo = [motivoNombre, reservaForm.detalle.trim() || undefined].filter(Boolean).join(' — ') || undefined
            mutReservaBloqueo.mutate({
              producto_id: invSel.producto_id,
              ubicacion_id: invSel.ubicacion_id,
              lote_id: invSel.lote_id,
              cantidad: cantNum,
              accion: reservaForm.accion,
              motivo,
            })
          }
          return (
          <Grid container spacing={2}>
            {/* Left: formulario */}
            <Grid size={{ xs: 12, md: 5 }}>
              <Card>
                <CardContent>
                  <Box sx={{ borderRadius: 2, p: 2, border: '1px solid', borderColor: 'divider' }}>
                    <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary', mb: 1 }}>
                      RESERVAR / BLOQUEAR STOCK
                    </Typography>
                    <Grid container spacing={2}>
                      <Grid size={{ xs: 12 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Acción</InputLabel>
                          <Select
                            label="Acción"
                            value={reservaForm.accion}
                            onChange={(e) => setReservaForm((f) => ({ ...f, accion: e.target.value }))}
                          >
                            {ACCIONES_RESERVA.map((a) => (
                              <MenuItem key={a.value} value={a.value}>{a.label}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid size={{ xs: 12 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Registro de inventario</InputLabel>
                          <Select
                            label="Registro de inventario"
                            value={reservaForm.inv_id}
                            onChange={(e) => setReservaForm((f) => ({ ...f, inv_id: e.target.value }))}
                          >
                            <MenuItem value="">Seleccionar...</MenuItem>
                            {stockItems.map((i) => (
                              <MenuItem key={i.id} value={String(i.id)}>{invLabel(i)}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField
                          fullWidth size="small" label="Cantidad" type="number"
                          inputProps={{ min: 0 }}
                          value={reservaForm.cantidad}
                          onChange={(e) => setReservaForm((f) => ({ ...f, cantidad: e.target.value }))}
                        />
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Motivo</InputLabel>
                          <Select
                            label="Motivo"
                            value={reservaForm.motivo_id}
                            onChange={(e) => setReservaForm((f) => ({ ...f, motivo_id: e.target.value }))}
                          >
                            <MenuItem value=""><em>Sin especificar</em></MenuItem>
                            {motivosFiltrados.map((m) => (
                              <MenuItem key={m.id} value={String(m.id)}>{m.nombre}</MenuItem>
                            ))}
                          </Select>
                          {motivosFiltrados.length === 0 && (
                            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                              Configura motivos en Configuración → Motivos Res./Bloq.
                            </Typography>
                          )}
                        </FormControl>
                      </Grid>
                      <Grid size={{ xs: 12 }}>
                        <TextField
                          fullWidth size="small" label="Detalle / contexto (opcional)" multiline rows={2}
                          placeholder="Amplía la causa: cliente, documento, observación…"
                          value={reservaForm.detalle}
                          onChange={(e) => setReservaForm((f) => ({ ...f, detalle: e.target.value }))}
                        />
                      </Grid>
                      <Grid size={{ xs: 12 }} sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
                        <Button
                          variant="contained"
                          disabled={mutReservaBloqueo.isPending || !reservaValida}
                          onClick={aplicar}
                          sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1e3a8a' } }}
                        >
                          {mutReservaBloqueo.isPending ? 'Aplicando...' : 'Aplicar'}
                        </Button>
                      </Grid>
                    </Grid>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* Right: estado actual del inventario seleccionado */}
            <Grid size={{ xs: 12, md: 7 }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" fontWeight={700} mb={2}>
                    Estado del inventario seleccionado
                  </Typography>
                  {invSel ? (
                    <Grid container spacing={2}>
                      <Grid size={{ xs: 12 }}>
                        <Typography variant="body2" color="text.secondary">
                          {invSel.producto?.sku} — {invSel.producto?.nombre} @ {invSel.ubicacion?.codigo}
                          {invSel.lote?.numero_lote ? ` · Lote ${invSel.lote.numero_lote}` : ''}
                        </Typography>
                      </Grid>
                      {[
                        { label: 'Disponible', val: invSel.cantidad_disponible, color: 'success' as const },
                        { label: 'Reservada', val: invSel.cantidad_reservada, color: 'warning' as const },
                        { label: 'Bloqueada', val: invSel.cantidad_bloqueada, color: 'error' as const },
                      ].map((k) => (
                        <Grid key={k.label} size={{ xs: 4 }}>
                          <Box sx={{ p: 2, borderRadius: 2, border: '1px solid', borderColor: 'divider', textAlign: 'center' }}>
                            <Typography variant="caption" color="text.secondary">{k.label}</Typography>
                            <Typography variant="h5" fontWeight={700} color={`${k.color}.main`}>{k.val}</Typography>
                          </Box>
                        </Grid>
                      ))}
                    </Grid>
                  ) : (
                    <Alert severity="info">
                      Selecciona producto y ubicación (con stock existente) para ver disponible, reservada y bloqueada.
                      La reserva y el bloqueo mueven cantidades sin cambiar el total.
                    </Alert>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
          )
        })()}

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* Dialog — Nuevo Conteo                                             */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        <Dialog
          open={openConteoDialog}
          onClose={() => setOpenConteoDialog(false)}
          maxWidth="sm"
          fullWidth
          PaperProps={{ sx: { borderRadius: 3 } }}
        >
          <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
            Nuevo Conteo de Inventario
            <Typography variant="caption" color="text.secondary" display="block">
              Programa un conteo físico para conciliar el stock del almacén
            </Typography>
          </DialogTitle>
          <DialogContent dividers>
            <Grid container spacing={2} sx={{ pt: 0.5 }}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Almacén</InputLabel>
                  <Select
                    label="Almacén"
                    value={conteoForm.almacen_id}
                    onChange={(e) =>
                      setConteoForm((f) => ({ ...f, almacen_id: e.target.value }))
                    }
                  >
                    <MenuItem value="">Seleccionar...</MenuItem>
                    {almacenes.map((a) => (
                      <MenuItem key={a.id} value={String(a.id)}>
                        {a.nombre}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Tipo</InputLabel>
                  <Select
                    label="Tipo"
                    value={conteoForm.tipo}
                    onChange={(e) =>
                      setConteoForm((f) => ({ ...f, tipo: e.target.value }))
                    }
                  >
                    <MenuItem value="CICLICO">Cíclico</MenuItem>
                    <MenuItem value="GENERAL">General</MenuItem>
                    <MenuItem value="DIRIGIDO">Dirigido</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  fullWidth
                  size="small"
                  label="Fecha Programada"
                  type="date"
                  InputLabelProps={{ shrink: true }}
                  value={conteoForm.fecha_programada}
                  onChange={(e) =>
                    setConteoForm((f) => ({ ...f, fecha_programada: e.target.value }))
                  }
                />
              </Grid>

              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  size="small"
                  label="Notas"
                  multiline
                  rows={3}
                  value={conteoForm.notas}
                  onChange={(e) =>
                    setConteoForm((f) => ({ ...f, notas: e.target.value }))
                  }
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions sx={{ px: 3, py: 2 }}>
            <Button onClick={() => setOpenConteoDialog(false)}>Cancelar</Button>
            <Button
              variant="contained"
              disabled={mutConteo.isPending}
              onClick={() => mutConteo.mutate(conteoForm)}
              sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1e3a8a' } }}
            >
              {mutConteo.isPending ? 'Creando...' : 'Crear Conteo'}
            </Button>
          </DialogActions>
        </Dialog>

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* Dialog — Detalle de Stock                                         */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        <Dialog
          open={!!detalleStock}
          onClose={() => setDetalleStock(null)}
          maxWidth="sm"
          fullWidth
          PaperProps={{ sx: { borderRadius: 3 } }}
        >
          {detalleStock && (() => {
            const s = detalleStock
            const total =
              s.cantidad_disponible + s.cantidad_reservada + s.cantidad_bloqueada
            const ruta = s.ubicacion
              ? [
                  s.ubicacion.pasillo,
                  s.ubicacion.estanteria,
                  s.ubicacion.nivel,
                  s.ubicacion.posicion,
                ]
                  .filter(Boolean)
                  .join(' · ')
              : ''
            const sectionSx = {
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: 0.4,
              textTransform: 'uppercase',
              color: 'text.secondary',
            } as const
            const cantidades = [
              { label: 'Disponible', val: s.cantidad_disponible, color: 'success' as const },
              { label: 'Reservada', val: s.cantidad_reservada, color: 'warning' as const },
              { label: 'Bloqueada', val: s.cantidad_bloqueada, color: 'error' as const },
            ]
            return (
              <>
                <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
                  {s.producto?.sku ?? '-'} — {s.producto?.nombre ?? '-'}
                  {s.producto?.unidad_medida ? (
                    <Typography variant="caption" color="text.secondary" display="block">
                      Unidad de medida: {s.producto.unidad_medida}
                    </Typography>
                  ) : null}
                </DialogTitle>
                <DialogContent dividers>
                  <Typography sx={{ ...sectionSx, mb: 1 }}>Ubicación y lote</Typography>
                  <Grid container spacing={2} sx={{ mb: 1 }}>
                    <Grid size={{ xs: 6 }}>
                      <Typography variant="caption" color="text.secondary">Ubicación</Typography>
                      <Typography variant="body2" fontWeight={600}>{s.ubicacion?.codigo ?? '-'}</Typography>
                    </Grid>
                    <Grid size={{ xs: 6 }}>
                      <Typography variant="caption" color="text.secondary">Ruta</Typography>
                      <Typography variant="body2" fontWeight={600}>{ruta || '-'}</Typography>
                    </Grid>
                    <Grid size={{ xs: 6 }}>
                      <Typography variant="caption" color="text.secondary">Lote</Typography>
                      <Typography variant="body2" fontWeight={600}>{s.lote?.numero_lote ?? '-'}</Typography>
                    </Grid>
                    <Grid size={{ xs: 6 }}>
                      <Typography variant="caption" color="text.secondary">Vencimiento</Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {s.lote?.fecha_vencimiento ? formatDate(s.lote.fecha_vencimiento) : '-'}
                      </Typography>
                    </Grid>
                  </Grid>

                  <Typography sx={{ ...sectionSx, mt: 2, mb: 1 }}>Cantidades</Typography>
                  <Grid container spacing={2}>
                    {cantidades.map((k) => (
                      <Grid key={k.label} size={{ xs: 4 }}>
                        <Box sx={{ p: 2, borderRadius: 2, border: '1px solid', borderColor: 'divider', textAlign: 'center' }}>
                          <Typography variant="caption" color="text.secondary">{k.label}</Typography>
                          <Typography variant="h5" fontWeight={700} color={`${k.color}.main`}>{k.val}</Typography>
                        </Box>
                      </Grid>
                    ))}
                    <Grid size={{ xs: 12 }}>
                      <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: alpha(WMS_COLOR, 0.06), display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="body2" fontWeight={600} color={WMS_COLOR}>Total</Typography>
                        <Typography variant="h6" fontWeight={700} color={WMS_COLOR}>{total}</Typography>
                      </Box>
                    </Grid>
                  </Grid>

                  {s.updated_at ? (
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
                      Última actualización: {formatDate(s.updated_at)}
                    </Typography>
                  ) : null}
                </DialogContent>
                <DialogActions sx={{ px: 3, py: 2 }}>
                  <Button onClick={() => setDetalleStock(null)}>Cerrar</Button>
                </DialogActions>
              </>
            )
          })()}
        </Dialog>

        {/* ══════════════════════════════════════════════════════════════════ */}
        {/* Dialog — Detalle de Movimiento (ajuste / transferencia)           */}
        {/* ══════════════════════════════════════════════════════════════════ */}
        <Dialog
          open={!!detalleMov}
          onClose={() => setDetalleMov(null)}
          maxWidth="sm"
          fullWidth
          PaperProps={{ sx: { borderRadius: 3 } }}
        >
          {detalleMov && (() => {
            const m = detalleMov
            const pares: { label: string; value: string | number }[] = [
              { label: 'Producto', value: m.producto?.nombre ?? `#${m.producto_id}` },
              { label: 'SKU', value: m.producto?.sku ?? '-' },
              { label: 'Origen', value: ubicacionLabel(m.ubicacion_origen_id) },
              { label: 'Destino', value: ubicacionLabel(m.ubicacion_destino_id) },
              { label: 'Cantidad', value: m.cantidad },
              { label: 'Referencia', value: m.referencia_documento ?? '-' },
              { label: 'Fecha', value: formatDate(m.created_at) },
            ]
            return (
              <>
                <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
                  Movimiento {m.tipo} #{m.id}
                </DialogTitle>
                <DialogContent dividers>
                  <Grid container spacing={2}>
                    {pares.map((p) => (
                      <Grid key={p.label} size={{ xs: 6 }}>
                        <Typography variant="caption" color="text.secondary">{p.label}</Typography>
                        <Typography variant="body2" fontWeight={600}>{p.value}</Typography>
                      </Grid>
                    ))}
                    <Grid size={{ xs: 12 }}>
                      <Typography variant="caption" color="text.secondary">Notas</Typography>
                      <Typography variant="body2" fontWeight={600}>{m.notas ?? '-'}</Typography>
                    </Grid>
                  </Grid>
                </DialogContent>
                <DialogActions sx={{ px: 3, py: 2 }}>
                  <Button onClick={() => setDetalleMov(null)}>Cerrar</Button>
                </DialogActions>
              </>
            )
          })()}
        </Dialog>
      </Box>
    </Layout>
  )
}
