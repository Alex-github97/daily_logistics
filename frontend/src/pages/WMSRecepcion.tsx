import React, { useState } from 'react'
import {
  Box, Card, CardContent, Typography, Button, Table, TableBody, TableCell, TableHead, TableRow, TablePagination, IconButton, Tooltip, Chip, MenuItem, InputLabel, Alert, Dialog, DialogTitle, DialogContent, DialogActions, Stack, Tab, Tabs, alpha, Divider, InputAdornment,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Add,
  Search,
  CheckCircleOutline,
  DeleteOutline,
  EditOutlined,
  MoveToInbox,
  OutboundOutlined,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { NumeroAutomatico } from '@/components/comun/NumeroAutomatico'
import { BotonPDF } from '@/components/comun/BotonPDF'
import { Layout } from '@/components/layout/Layout'
import {
  ArticulosRecepcion, LINEA_VACIA, nombreNovedad, problemasRecepcion, type LineaRecepcion,
} from '@/components/wms/ArticulosRecepcion'
import { ChipEstadoOC, useEstadosOC } from '@/api/estadosOC'
import { apiClient as api } from '@/api/client'
import toast from 'react-hot-toast'
import { format, parseISO } from 'date-fns'

/** Una fecha sin hora («2026-10-15») es ese día en hora local. Con new Date()
 *  se toma como medianoche UTC y en Colombia se mostraba el día anterior. */
const fechaLocal = (s: string) => (/^\d{4}-\d{2}-\d{2}$/.test(s) ? parseISO(s) : aFecha(s))
import { es } from 'date-fns/locale'

import { COLOR_MODULO } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'
import { aFecha } from '@/utils/fechas'
const WMS_COLOR = COLOR_MODULO

// ─── Types ───────────────────────────────────────────────────────────────────

interface Proveedor {
  id: number
  nombre: string
}

interface Almacen {
  id: number
  nombre: string
}

interface Producto {
  id: number
  nombre: string
  sku: string
  requiere_lote?: boolean
}

interface Zona {
  id: number
  nombre?: string
  almacen_id: number
}

interface Ubicacion {
  id: number
  codigo: string
  pasillo?: string
  estanteria?: string
  nivel?: string
  posicion?: string
  zona_id: number
}

interface Lote {
  id: number
  numero_lote?: string
  codigo?: string
}

interface LineaOC {
  /** Línea ya guardada (al editar una OC); sin id es nueva. */
  id?: number
  producto_id: number
  cantidad_solicitada: number
  precio_unitario: number
  unidad_medida: string
}

const UNIDADES_MEDIDA = ['UNIDAD', 'CAJA', 'PALLET', 'KG', 'LITRO', 'METRO', 'PAQUETE', 'DOCENA']

interface OrdenCompraDetalle {
  id?: number
  producto_id?: number
  producto?: { sku?: string; nombre?: string }
  cantidad_solicitada?: number
  cantidad_recibida?: number
  precio_unitario?: number
  unidad_medida?: string
}

interface OrdenCompra {
  id: number
  numero_oc: string
  proveedor_id: number
  proveedor_nombre: string
  proveedor?: { nombre?: string }
  almacen_id: number
  almacen?: { nombre?: string }
  fecha_emision: string
  fecha_esperada: string
  /** Código de un estado configurable (WMS › Configuración › Estados de OC). */
  estado: string
  notas: string
  lineas?: LineaOC[]
  detalles?: OrdenCompraDetalle[]
  /** Estado inicial, sin recepciones ni cambios de estado: se puede corregir o eliminar. */
  editable?: boolean
}


interface RecepcionDetalle {
  producto?: { sku?: string; nombre?: string }
  lote?: { numero_lote?: string }
  cantidad_esperada?: number
  cantidad_recibida?: number
  ubicacion?: { codigo?: string }
  estado_calidad?: string
  novedad?: string | null
  notas?: string | null
}

interface Recepcion {
  id: number
  numero_recepcion: string
  tipo: string
  orden_compra_id: number | null
  numero_oc?: string
  almacen_id: number
  almacen_nombre: string
  almacen?: { nombre?: string }
  fecha_recepcion: string
  estado: string
  operario: string
  notas: string
  detalles?: RecepcionDetalle[]
}

// ─── Empty form shapes ────────────────────────────────────────────────────────

const EMPTY_OC = {
  numero_oc: '',
  proveedor_id: '',
  almacen_id: '',
  fecha_emision: format(new Date(), 'yyyy-MM-dd'),
  fecha_esperada: '',
  notas: '',
}

const EMPTY_LINEA_OC: LineaOC = {
  producto_id: 0,
  cantidad_solicitada: 1,
  precio_unitario: 0,
  unidad_medida: 'UNIDAD',
}

const EMPTY_RECEPCION = {
  numero_recepcion: '',
  tipo: 'CONTRA_OC' as string,
  orden_compra_id: '' as string | number,
  almacen_id: '',
  fecha_recepcion: format(new Date(), 'yyyy-MM-dd'),
  muelle: '',
  notas: '',
}

const EMPTY_LINEA_REC: LineaRecepcion = {
  producto_id: 0,
  cantidad_esperada: 1,
  cantidad_recibida: 0,
  lote_id: null,
  ubicacion_id: null,
  estado_calidad: 'APROBADO',
  notas: '',
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Convierte el `detail` de un error de axios/FastAPI en un texto legible.
 *  Un 422 de FastAPI trae `detail` como arreglo de objetos `{ msg, loc, ... }`. */

/** Formatea una fecha de forma segura; null/undefined/invalid → '—'. */
function fmtFecha(x?: string | null): string {
  if (!x) return '—'
  const d = fechaLocal(x)
  if (isNaN(d.getTime())) return '—'
  return format(d, 'dd MMM yyyy', { locale: es })
}

/** Par etiqueta/valor uniforme para las cabeceras de los diálogos de detalle. */
function DetalleCampo({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box>
      <Typography sx={{ fontSize: 11, fontWeight: 600, color: 'text.secondary' }}>{label}</Typography>
      <Typography sx={{ fontSize: 13, color: 'text.primary', mt: 0.25 }}>{value ?? '—'}</Typography>
    </Box>
  )
}

/** Encabezado de sección uniforme para los diálogos de detalle. */
function SeccionTitulo({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary' }}
    >
      {children}
    </Typography>
  )
}

// ─── Chips ────────────────────────────────────────────────────────────────────


const REC_ESTADO_COLOR: Record<string, 'primary' | 'info' | 'warning' | 'success' | 'default' | 'error'> = {
  BORRADOR: 'default',
  EN_PROCESO: 'info',
  COMPLETA: 'success',
  RECHAZADA: 'error',
}

const CALIDAD_COLOR: Record<string, 'success' | 'error' | 'warning' | 'info'> = {
  APROBADO: 'success',
  RECHAZADO: 'error',
  CUARENTENA: 'warning',
  INSPECCION: 'info',
}

// ─── Tab 1: Órdenes de Compra ─────────────────────────────────────────────────

function OrdenesCompraTab() {
  const queryClient = useQueryClient()
  const estadosOC = useEstadosOC()

  const cambiarEstado = useMutation({
    mutationFn: ({ id, estado }: { id: number; estado: string }) =>
      api.post(`/wms/ordenes-compra/${id}/estado`, { estado }).then((r) => r.data),
    onSuccess: (r: any) => {
      toast.success('Estado de la orden actualizado')
      setDetalleOC((d) => (d && d.id === r.id ? { ...d, estado: r.estado } : d))
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes-compra'] })
    },
    onError: (err: any) => toast.error(mensajeDeError(err, 'No se pudo cambiar el estado')),
  })

  // Filters
  const [search, setSearch] = useState('')
  const [estadoFilter, setEstadoFilter] = useState('TODOS')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(50)

  // Dialog
  const [openDialog, setOpenDialog] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_OC })
  const [lineas, setLineas] = useState<LineaOC[]>([])
  const [formError, setFormError] = useState('')

  // Detail dialog
  const [detalleOC, setDetalleOC] = useState<OrdenCompra | null>(null)
  // Edición (mismo formulario que «Nueva OC») y eliminación
  const [editando, setEditando] = useState<OrdenCompra | null>(null)
  const [eliminar, setEliminar] = useState<OrdenCompra | null>(null)

  // Queries
  const { data: ordenes = [], isLoading } = useQuery<OrdenCompra[]>({
    queryKey: ['wms-ordenes-compra'],
    queryFn: () => api.get('/wms/ordenes-compra/').then((r) => r.data),
  })

  const { data: proveedores = [] } = useQuery<Proveedor[]>({
    queryKey: ['wms-proveedores'],
    queryFn: () => api.get('/wms/proveedores/').then((r) => r.data),
  })

  const { data: almacenes = [] } = useQuery<Almacen[]>({
    queryKey: ['wms-almacenes'],
    queryFn: () => api.get('/wms/almacenes/').then((r) => r.data),
  })

  const { data: productos = [] } = useQuery<Producto[]>({
    queryKey: ['wms-productos'],
    queryFn: () => api.get('/wms/productos/').then((r) => r.data),
  })

  // Mutation
  const createOC = useMutation({
    mutationFn: (data: any) => api.post('/wms/ordenes-compra/', data).then((r) => r.data),
    onSuccess: (oc: { numero_oc?: string }) => {
      toast.success(oc?.numero_oc ? `Orden de compra ${oc.numero_oc} creada` : 'Orden de compra creada')
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes-compra'] })
      handleClose()
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail ?? 'Error al crear la orden'
      setFormError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    },
  })

  // Cierre sin la guarda de «guardando»: en onSuccess la mutación todavía
  // figura en curso y handleClose no cerraba el formulario.
  function cerrarFormulario() {
    setOpenDialog(false); setEditando(null); setForm({ ...EMPTY_OC }); setLineas([]); setFormError('')
  }
  const editOC = useMutation({
    mutationFn: (data: any) => api.put(`/wms/ordenes-compra/${editando!.id}/edicion`, data).then((r) => r.data),
    onSuccess: (r: { numero_oc?: string }) => {
      toast.success(`Orden de compra ${r?.numero_oc ?? ''} actualizada`)
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes-compra'] })
      cerrarFormulario()
    },
    onError: (err: any) => setFormError(mensajeDeError(err, 'No se pudo guardar la orden')),
  })
  const deleteOC = useMutation({
    mutationFn: (oc: OrdenCompra) => api.delete(`/wms/ordenes-compra/${oc.id}`).then((r) => r.data),
    onSuccess: (r: { numero_oc?: string }) => {
      toast.success(`Orden de compra ${r?.numero_oc ?? ''} eliminada`)
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes-compra'] })
      setEliminar(null); setDetalleOC(null)
    },
    onError: (err: any) => toast.error(mensajeDeError(err, 'No se pudo eliminar la orden')),
  })

  function abrirEdicion(o: OrdenCompra) {
    setDetalleOC(null)
    setEditando(o)
    setForm({
      numero_oc: o.numero_oc, proveedor_id: String(o.proveedor_id), almacen_id: String(o.almacen_id),
      fecha_emision: o.fecha_emision?.slice(0, 10) ?? '', fecha_esperada: o.fecha_esperada?.slice(0, 10) ?? '', notas: o.notas ?? '',
    })
    setLineas((o.detalles ?? []).map((d) => ({
      id: d.id, producto_id: d.producto_id ?? 0, cantidad_solicitada: Number(d.cantidad_solicitada) || 0,
      precio_unitario: Number(d.precio_unitario) || 0, unidad_medida: d.unidad_medida || 'UNIDAD',
    })))
    setFormError('')
    setOpenDialog(true)
  }

  // Filtered rows
  const filtered = ordenes.filter((o) => {
    const matchSearch =
      !search ||
      o.numero_oc.toLowerCase().includes(search.toLowerCase()) ||
      (o.proveedor?.nombre ?? o.proveedor_nombre)?.toLowerCase().includes(search.toLowerCase())
    const matchEstado = estadoFilter === 'TODOS' || o.estado === estadoFilter
    return matchSearch && matchEstado
  })

  const paginated = filtered.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)

  function handleClose() {
    if (createOC.isPending || editOC.isPending) return
    setOpenDialog(false)
    setEditando(null)
    setForm({ ...EMPTY_OC })
    setLineas([])
    setFormError('')
  }

  function handleSubmit() {
    setFormError('')
    if (!form.proveedor_id || !form.almacen_id || !form.fecha_esperada) {
      setFormError('Proveedor, almacén y fecha esperada son obligatorios')
      return
    }
    const validas = lineas.filter((l) => l.producto_id > 0 && l.cantidad_solicitada > 0)
    if (validas.length === 0) {
      setFormError('Agrega al menos un artículo con producto y cantidad válidos')
      return
    }
    const detalles = validas.map((l) => ({
      id: l.id,
      producto_id: Number(l.producto_id),
      cantidad_solicitada: Number(l.cantidad_solicitada),
      precio_unitario: Number(l.precio_unitario) || 0,
      unidad_medida: l.unidad_medida || 'UNIDAD',
    }))
    if (editando) {
      editOC.mutate({
        proveedor_id: Number(form.proveedor_id), almacen_id: Number(form.almacen_id),
        fecha_emision: form.fecha_emision || undefined, fecha_esperada: form.fecha_esperada || undefined,
        notas: form.notas || null, detalles,
      })
      return
    }
    createOC.mutate({
      numero_oc: form.numero_oc || undefined,
      proveedor_id: Number(form.proveedor_id),
      almacen_id: Number(form.almacen_id),
      fecha_emision: form.fecha_emision || undefined,
      fecha_esperada: form.fecha_esperada || undefined,
      notas: form.notas || undefined,
      detalles,
    })
  }

  function addLinea() {
    setLineas((prev) => [...prev, { ...EMPTY_LINEA_OC }])
  }

  function updateLinea(idx: number, field: keyof LineaOC, value: any) {
    setLineas((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)))
  }

  function removeLinea(idx: number) {
    setLineas((prev) => prev.filter((_, i) => i !== idx))
  }

  return (
    <Box>
      {/* Toolbar */}
      <Stack direction="row" spacing={2} mb={2} flexWrap="wrap" alignItems="center">
        <TextField
          size="small"
          placeholder="Buscar N° OC o proveedor…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0) }}
          sx={{ minWidth: 240 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search sx={{ fontSize: 18, color: 'text.disabled' }} />
              </InputAdornment>
            ),
          }}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>Estado</InputLabel>
          <Select
            value={estadoFilter}
            label="Estado"
            onChange={(e) => { setEstadoFilter(e.target.value); setPage(0) }}
          >
            <MenuItem value="TODOS">Todos</MenuItem>
            {estadosOC.estados.map((e) => (
              <MenuItem key={e.codigo} value={e.codigo}>{e.nombre}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <Box sx={{ flexGrow: 1 }} />
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => setOpenDialog(true)}
          sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: alpha(WMS_COLOR, 0.85) } }}
        >
          Nueva OC
        </Button>
      </Stack>

      {/* Table */}
      <Card elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px' }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#F9FAFB', '& th': { fontSize: 12, fontWeight: 700, color: 'text.secondary', py: 1.5 } }}>
                <TableCell>N° OC</TableCell>
                <TableCell>Proveedor</TableCell>
                <TableCell>Fecha Emisión</TableCell>
                <TableCell>Fecha Esperada</TableCell>
                <TableCell>Estado</TableCell>
                <TableCell>Notas</TableCell>
                <TableCell align="right">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {isLoading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 7 }).map((_, j) => (
                        <TableCell key={j}>
                          <Box sx={{ bgcolor: '#F3F4F6', height: 14, borderRadius: 1 }} />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : paginated.length === 0
                ? (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 6, color: 'text.secondary', fontSize: 13 }}>
                      No se encontraron órdenes de compra
                    </TableCell>
                  </TableRow>
                )
                : paginated.map((o) => (
                  <TableRow
                    key={o.id}
                    hover
                    onClick={() => setDetalleOC(o)}
                    sx={{ cursor: 'pointer', '& td': { fontSize: 12, py: 1 } }}
                  >
                    <TableCell sx={{ fontWeight: 700, color: WMS_COLOR }}>{o.numero_oc}</TableCell>
                    <TableCell>{o.proveedor?.nombre ?? o.proveedor_nombre ?? '—'}</TableCell>
                    <TableCell>
                      {o.fecha_emision ? format(fechaLocal(o.fecha_emision), 'dd MMM yyyy', { locale: es }) : '—'}
                    </TableCell>
                    <TableCell>
                      {o.fecha_esperada ? format(fechaLocal(o.fecha_esperada), 'dd MMM yyyy', { locale: es }) : '—'}
                    </TableCell>
                    <TableCell>
                      <ChipEstadoOC codigo={o.estado} estados={estadosOC.porCodigo} />
                    </TableCell>
                    <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {o.notas || '—'}
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: 'nowrap' }} onClick={(e) => e.stopPropagation()}>
                      <BotonPDF tipo="oc" id={o.id} etiqueta="Orden de compra en PDF" icono />
                      {o.editable ? (
                        <>
                          <Tooltip title="Editar (proveedor, fechas, artículos, cantidades y precios)">
                            <IconButton size="small" onClick={() => abrirEdicion(o)}><EditOutlined fontSize="small" /></IconButton>
                          </Tooltip>
                          <Tooltip title="Eliminar orden">
                            <IconButton size="small" color="error" onClick={() => setEliminar(o)}><DeleteOutline fontSize="small" /></IconButton>
                          </Tooltip>
                        </>
                      ) : (
                        <Tooltip title="Ya tuvo recepciones o cambios de estado: solo admite cambios de estado (p. ej. Anulada)">
                          <Typography component="span" sx={{ fontSize: 11, color: 'text.disabled' }}>Bloqueada</Typography>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              }
            </TableBody>
          </Table>
        </Box>
        <TablePagination
          component="div"
          count={filtered.length}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => { setRowsPerPage(+e.target.value); setPage(0) }}
          rowsPerPageOptions={[25, 50, 100, 200]}
          labelRowsPerPage="Por página:"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} de ${count}`}
          sx={{ fontSize: 12 }}
        />
      </Card>

      {/* ── Create OC Dialog ───────────────────────────────────────────── */}
      <Dialog open={openDialog} onClose={handleClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
          {editando ? `Editar orden de compra ${editando.numero_oc}` : 'Nueva Orden de Compra'}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 400 }}>
            {editando
              ? 'Sigue en su estado inicial y sin recepciones: puede corregir proveedor, fechas, artículos, cantidades y precios'
              : 'Registra los artículos solicitados al proveedor y su fecha esperada de llegada'}
          </Typography>
        </DialogTitle>
        <DialogContent dividers sx={{ px: 3, py: 2.5 }}>
          <Grid container spacing={2.5} sx={{ pt: 0.5 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              {editando
                ? <TextField label="Número de orden de compra" fullWidth size="small" value={editando.numero_oc} InputProps={{ readOnly: true }} helperText="El número no cambia" />
                : <NumeroAutomatico tipo="OC" etiqueta="Número de orden de compra" />}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Proveedor *</InputLabel>
                <Select
                  value={form.proveedor_id}
                  label="Proveedor *"
                  onChange={(e) => setForm((f) => ({ ...f, proveedor_id: e.target.value as string }))}
                >
                  {proveedores.map((p) => (
                    <MenuItem key={p.id} value={p.id}>{p.nombre}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Almacén *</InputLabel>
                <Select
                  value={form.almacen_id}
                  label="Almacén *"
                  onChange={(e) => setForm((f) => ({ ...f, almacen_id: e.target.value as string }))}
                >
                  {almacenes.map((a) => (
                    <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Fecha Emisión"
                type="date"
                fullWidth
                size="small"
                value={form.fecha_emision}
                onChange={(e) => setForm((f) => ({ ...f, fecha_emision: e.target.value }))}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Fecha Esperada *"
                type="date"
                fullWidth
                size="small"
                value={form.fecha_esperada}
                onChange={(e) => setForm((f) => ({ ...f, fecha_esperada: e.target.value }))}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                label="Notas"
                fullWidth
                size="small"
                multiline
                rows={2}
                value={form.notas}
                onChange={(e) => setForm((f) => ({ ...f, notas: e.target.value }))}
              />
            </Grid>

            {/* Line items */}
            <Grid size={{ xs: 12 }}>
              <Divider sx={{ mb: 1.5 }} />
              <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary', mb: 0.5 }}>
                  Artículos
                </Typography>
                <Button variant="outlined" size="small" startIcon={<Add />} onClick={addLinea}>
                  Agregar artículo
                </Button>
              </Stack>
              {lineas.length === 0 ? (
                <Typography fontSize={12} color="text.secondary" align="center" sx={{ py: 2 }}>
                  Sin artículos. Haz clic en "Agregar artículo" para añadir.
                </Typography>
              ) : (
                <Box sx={{ maxHeight: 340, overflowY: 'auto', pr: 0.5 }}>
                  {lineas.map((l, idx) => (
                    <Box
                      key={idx}
                      sx={{ p: 1.5, mb: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2, bgcolor: 'action.hover' }}
                    >
                      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                        <Typography variant="caption" fontWeight={700}>Línea {idx + 1}</Typography>
                        <Tooltip title="Eliminar">
                          <IconButton size="small" color="error" onClick={() => removeLinea(idx)}>
                            <DeleteOutline fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                      <Grid container spacing={2}>
                        <Grid size={{ xs: 12, sm: 6 }}>
                          <FormControl size="small" fullWidth>
                            <InputLabel>Producto</InputLabel>
                            <Select
                              value={l.producto_id || ''}
                              label="Producto"
                              onChange={(e) => updateLinea(idx, 'producto_id', Number(e.target.value))}
                            >
                              {productos.map((p) => (
                                <MenuItem key={p.id} value={p.id}>{p.nombre} ({p.sku})</MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                          <TextField
                            label="Cantidad"
                            type="number"
                            size="small"
                            fullWidth
                            value={l.cantidad_solicitada}
                            onChange={(e) => updateLinea(idx, 'cantidad_solicitada', Number(e.target.value))}
                            inputProps={{ min: 1 }}
                          />
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                          <FormControl size="small" fullWidth>
                            <InputLabel>Unidad</InputLabel>
                            <Select
                              value={l.unidad_medida}
                              label="Unidad"
                              onChange={(e) => updateLinea(idx, 'unidad_medida', e.target.value)}
                            >
                              {UNIDADES_MEDIDA.map((u) => (
                                <MenuItem key={u} value={u}>{u}</MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 4 }}>
                          <TextField
                            label="Precio Unit."
                            type="number"
                            size="small"
                            fullWidth
                            value={l.precio_unitario}
                            onChange={(e) => updateLinea(idx, 'precio_unitario', Number(e.target.value))}
                            inputProps={{ min: 0, step: 0.01 }}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                          />
                        </Grid>
                        <Grid size={{ xs: 6, sm: 8 }}>
                          <TextField
                            label="Subtotal"
                            size="small"
                            fullWidth
                            value={`$ ${((Number(l.cantidad_solicitada) || 0) * (Number(l.precio_unitario) || 0)).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                            InputProps={{ readOnly: true }}
                            sx={{ '& .MuiInputBase-input': { fontWeight: 600 } }}
                          />
                        </Grid>
                      </Grid>
                    </Box>
                  ))}
                  <Stack direction="row" justifyContent="flex-end" alignItems="baseline" spacing={1} sx={{ mt: 0.5, pr: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">Total OC:</Typography>
                    <Typography fontWeight={700} color={WMS_COLOR}>
                      $ {lineas.reduce((acc, l) => acc + (Number(l.cantidad_solicitada) || 0) * (Number(l.precio_unitario) || 0), 0).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </Typography>
                  </Stack>
                </Box>
              )}
            </Grid>

            {formError && (
              <Grid size={{ xs: 12 }}>
                <Alert severity="error" sx={{ py: 0.5 }}>{formError}</Alert>
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={handleClose} disabled={createOC.isPending || editOC.isPending}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={createOC.isPending || editOC.isPending}
            sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: alpha(WMS_COLOR, 0.85) } }}
          >
            {createOC.isPending || editOC.isPending ? 'Guardando...' : editando ? 'Guardar cambios' : 'Crear OC'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Detail OC Dialog ───────────────────────────────────────────── */}
      <Dialog
        open={!!detalleOC}
        onClose={() => setDetalleOC(null)}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        {detalleOC && (
          <>
            <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap">
                <span>Orden de Compra {detalleOC.numero_oc}</span>
                <ChipEstadoOC codigo={detalleOC.estado} estados={estadosOC.porCodigo} />
                <Box sx={{ flex: 1 }} />
                <TextField
                  select size="small" label="Cambiar estado" value={detalleOC.estado} sx={{ minWidth: 200 }}
                  disabled={cambiarEstado.isPending}
                  onChange={(e) => {
                    if (e.target.value && e.target.value !== detalleOC.estado) {
                      cambiarEstado.mutate({ id: detalleOC.id, estado: String(e.target.value) })
                    }
                  }}
                >
                  {estadosOC.estados.filter((e) => e.activo || e.codigo === detalleOC.estado).map((e) => (
                    <MenuItem key={e.codigo} value={e.codigo}>{e.nombre}</MenuItem>
                  ))}
                </TextField>
              </Stack>
            </DialogTitle>
            <DialogContent dividers sx={{ px: 3, py: 2.5 }}>
              {/* Cabecera */}
              <SeccionTitulo>Información general</SeccionTitulo>
              <Grid container spacing={2} sx={{ mt: 0.5, mb: 2.5 }}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo
                    label="Proveedor"
                    value={detalleOC.proveedor?.nombre ?? detalleOC.proveedor_nombre}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo label="Almacén" value={detalleOC.almacen?.nombre} />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo label="Fecha Emisión" value={fmtFecha(detalleOC.fecha_emision)} />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo label="Fecha Esperada" value={fmtFecha(detalleOC.fecha_esperada)} />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <DetalleCampo label="Notas" value={detalleOC.notas || '—'} />
                </Grid>
              </Grid>

              {/* Artículos */}
              <Divider sx={{ mb: 2 }} />
              <SeccionTitulo>Artículos</SeccionTitulo>
              {!detalleOC.detalles || detalleOC.detalles.length === 0 ? (
                <Typography fontSize={12} color="text.secondary" sx={{ py: 2 }}>
                  Esta orden no tiene artículos registrados.
                </Typography>
              ) : (
                <Box sx={{ overflowX: 'auto', mt: 1 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ '& th': { fontSize: 11, fontWeight: 700, color: 'text.secondary' } }}>
                        <TableCell>Producto</TableCell>
                        <TableCell align="right">Solicitada</TableCell>
                        <TableCell align="right">Recibida</TableCell>
                        <TableCell>Unidad</TableCell>
                        <TableCell align="right">Precio Unit.</TableCell>
                        <TableCell align="right">Subtotal</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {detalleOC.detalles.map((d, i) => {
                        const cant = Number(d.cantidad_solicitada) || 0
                        const precio = Number(d.precio_unitario) || 0
                        return (
                          <TableRow key={i} sx={{ '& td': { fontSize: 12 } }}>
                            <TableCell>
                              <Typography sx={{ fontSize: 12, fontWeight: 600 }}>
                                {d.producto?.nombre ?? '—'}
                              </Typography>
                              {d.producto?.sku && (
                                <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
                                  {d.producto.sku}
                                </Typography>
                              )}
                            </TableCell>
                            <TableCell align="right">{cant}</TableCell>
                            <TableCell align="right">{Number(d.cantidad_recibida) || 0}</TableCell>
                            <TableCell>{d.unidad_medida ?? '—'}</TableCell>
                            <TableCell align="right">
                              $ {precio.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>
                              $ {(cant * precio).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                  <Stack direction="row" justifyContent="flex-end" alignItems="baseline" spacing={1} sx={{ mt: 1, pr: 1 }}>
                    <Typography variant="caption" color="text.secondary">Total OC:</Typography>
                    <Typography fontWeight={700} color={WMS_COLOR}>
                      $ {detalleOC.detalles.reduce((acc, d) => acc + (Number(d.cantidad_solicitada) || 0) * (Number(d.precio_unitario) || 0), 0).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </Typography>
                  </Stack>
                </Box>
              )}
            </DialogContent>
            <DialogActions sx={{ px: 3, py: 2 }}>
              {detalleOC.editable && (
                <>
                  <Button color="error" startIcon={<DeleteOutline />} onClick={() => setEliminar(detalleOC)}>Eliminar</Button>
                  <Button startIcon={<EditOutlined />} onClick={() => abrirEdicion(detalleOC)}>Editar</Button>
                  <Box sx={{ flex: 1 }} />
                </>
              )}
              <BotonPDF tipo="oc" id={detalleOC.id} />
              <Button onClick={() => setDetalleOC(null)}>Cerrar</Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      {/* ── Confirmar eliminación ─────────────────────────────────────── */}
      <Dialog open={!!eliminar} onClose={() => !deleteOC.isPending && setEliminar(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>¿Eliminar la orden de compra {eliminar?.numero_oc}?</DialogTitle>
        <DialogContent>
          <Typography fontSize={14}>
            Se elimina con sus artículos. El número {eliminar?.numero_oc} no se vuelve a usar y queda registrado quién la eliminó.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEliminar(null)} disabled={deleteOC.isPending}>Cancelar</Button>
          <Button color="error" variant="contained" disabled={deleteOC.isPending} onClick={() => eliminar && deleteOC.mutate(eliminar)}>
            {deleteOC.isPending ? 'Eliminando…' : 'Eliminar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Tab 2: Recepciones ───────────────────────────────────────────────────────

/** Fila del detalle de una recepción. Se extrae como componente para poder
 *  cargar los lotes del producto seleccionado con su propio `useQuery`. */
function RecepcionesTab() {
  const queryClient = useQueryClient()
  const estadosOC = useEstadosOC()

  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(50)

  const [openDialog, setOpenDialog] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_RECEPCION })
  const [lineas, setLineas] = useState<LineaRecepcion[]>([])
  const [formError, setFormError] = useState('')

  // Detail dialog
  const [detalleRec, setDetalleRec] = useState<Recepcion | null>(null)

  // Queries
  const { data: recepciones = [], isLoading } = useQuery<Recepcion[]>({
    queryKey: ['wms-recepciones'],
    queryFn: () => api.get('/wms/recepciones/').then((r) => r.data),
  })

  const { data: ordenesCompra = [] } = useQuery<OrdenCompra[]>({
    queryKey: ['wms-ordenes-compra'],
    queryFn: () => api.get('/wms/ordenes-compra/').then((r) => r.data),
  })

  const { data: almacenes = [] } = useQuery<Almacen[]>({
    queryKey: ['wms-almacenes'],
    queryFn: () => api.get('/wms/almacenes/').then((r) => r.data),
  })

  const { data: productos = [] } = useQuery<Producto[]>({
    queryKey: ['wms-productos'],
    queryFn: () => api.get('/wms/productos/').then((r) => r.data),
  })

  // Zonas del almacén seleccionado (para acotar las ubicaciones disponibles)
  const { data: zonas = [] } = useQuery<Zona[]>({
    queryKey: ['wms-zonas', form.almacen_id],
    queryFn: () => api.get(`/wms/zonas/?almacen_id=${form.almacen_id}`).then((r) => r.data),
    enabled: !!form.almacen_id,
  })

  const { data: ubicaciones = [] } = useQuery<Ubicacion[]>({
    queryKey: ['wms-ubicaciones'],
    queryFn: () => api.get('/wms/ubicaciones/').then((r) => r.data),
  })

  // Ubicaciones filtradas por las zonas del almacén elegido; si aún no hay
  // zonas cargadas se ofrecen todas las ubicaciones para no bloquear al usuario.
  const zonaIds = new Set(zonas.map((z) => z.id))
  const ubicacionesFiltradas =
    zonas.length > 0 ? ubicaciones.filter((u) => zonaIds.has(u.zona_id)) : ubicaciones

  // Create recepcion
  const createRec = useMutation({
    mutationFn: (data: any) => api.post('/wms/recepciones/', data).then((r) => r.data),
    onSuccess: (rec: { numero_recepcion?: string }) => {
      toast.success(rec?.numero_recepcion ? `Recepción ${rec.numero_recepcion} registrada` : 'Recepción registrada')
      queryClient.invalidateQueries({ queryKey: ['wms-recepciones'] })
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes-compra'] })
      queryClient.invalidateQueries({ queryKey: ['wms-kpis'] })
      handleClose()
    },
    onError: (err: any) => {
      setFormError(mensajeDeError(err, 'Error al registrar la recepción'))
    },
  })

  // Completar recepcion
  const completarRec = useMutation({
    mutationFn: (id: number) => api.post(`/wms/recepciones/${id}/completar`).then((r) => r.data),
    onSuccess: (r: any) => {
      toast.success(
        r?.detalles?.some((d: any) => d.contenedor_id)
          ? 'Recepción completada: quedó en la zona de recepción con sus tareas de ubicación (WMS · Tareas de bodega)'
          : 'Recepción completada — stock actualizado')
      queryClient.invalidateQueries({ queryKey: ['wms-recepciones'] })
      queryClient.invalidateQueries({ queryKey: ['wms-ordenes-compra'] })
      queryClient.invalidateQueries({ queryKey: ['wms-kpis'] })
    },
    onError: (err: any) => {
      toast.error(mensajeDeError(err, 'Error al completar la recepción'))
    },
  })

  const filtered = recepciones.filter((r) => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      r.numero_recepcion?.toLowerCase().includes(q) ||
      r.almacen_nombre?.toLowerCase().includes(q) ||
      r.operario?.toLowerCase().includes(q) ||
      r.numero_oc?.toLowerCase().includes(q)
    )
  })

  const paginated = filtered.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)

  function handleClose() {
    if (createRec.isPending) return
    setOpenDialog(false)
    setForm({ ...EMPTY_RECEPCION })
    setLineas([])
    setFormError('')
  }

  function handleSubmit() {
    setFormError('')
    if (!form.almacen_id) {
      setFormError('El almacén es obligatorio')
      return
    }
    if (lineas.length === 0) {
      setFormError('Agrega al menos una línea de recepción')
      return
    }
    const problemas = problemasRecepcion(lineas, !!form.orden_compra_id)
    if (problemas.length) {
      setFormError(problemas[0])
      return
    }
    for (const l of lineas) {
      if (!(Number(l.cantidad_recibida) > 0) && !(Number(l.cantidad_esperada) > 0) && !l.novedad) {
        setFormError('Cada línea debe tener una cantidad recibida o esperada, o una novedad')
        return
      }
    }

    const detalles = lineas.map((l) => ({
      producto_id: Number(l.producto_id),
      cantidad_esperada: Number(l.cantidad_esperada) || 0,
      cantidad_recibida: Number(l.cantidad_recibida) || 0,
      lote_id: l.lote_id != null ? Number(l.lote_id) : null,
      ubicacion_id: l.ubicacion_id != null ? Number(l.ubicacion_id) : null,
      estado_calidad: l.estado_calidad,
      notas: l.notas || '',
      novedad: l.novedad || null,
    }))

    const payload: any = {
      tipo: form.tipo,
      almacen_id: Number(form.almacen_id),
      orden_compra_id: form.orden_compra_id ? Number(form.orden_compra_id) : null,
      fecha_recepcion: form.fecha_recepcion || undefined,
      muelle: form.muelle || undefined,
      notas: form.notas || '',
      detalles,
    }
    // El backend autogenera el número si va vacío; sólo lo enviamos si el usuario lo llenó.
    if (form.numero_recepcion.trim()) {
      payload.numero_recepcion = form.numero_recepcion.trim()
    }

    createRec.mutate(payload)
  }

  // Al elegir una OC se cargan sus artículos con lo que falta por recibir.
  function elegirOC(valor: string | number) {
    const oc = ordenesCompra.find((o) => o.id === Number(valor))
    const hayRegistrado = lineas.some((l) => (Number(l.cantidad_recibida) || 0) > 0)
    if (hayRegistrado && !window.confirm('Ya hay cantidades registradas. ¿Reemplazar los artículos por los de la orden elegida?')) return
    setFormError('')
    setForm((f) => ({
      ...f,
      orden_compra_id: valor,
      tipo: oc ? 'CONTRA_OC' : f.tipo,
      almacen_id: oc?.almacen_id ? String(oc.almacen_id) : f.almacen_id,
    }))
    if (!oc) {
      setLineas((prev) => prev.filter((l) => !l.de_oc))
      return
    }
    setLineas(
      (oc.detalles ?? [])
        .map((d) => ({
          ...LINEA_VACIA,
          producto_id: Number(d.producto_id),
          cantidad_esperada: Math.max(0, (Number(d.cantidad_solicitada) || 0) - (Number(d.cantidad_recibida) || 0)),
          de_oc: true,
        }))
        .filter((l) => l.producto_id > 0 && l.cantidad_esperada > 0),
    )
  }

  function addLinea() {
    setLineas((prev) => [...prev, { ...EMPTY_LINEA_REC }])
  }


  function updateLinea(idx: number, field: keyof LineaRecepcion, value: any) {
    setLineas((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)))
  }

  function removeLinea(idx: number) {
    setLineas((prev) => prev.filter((_, i) => i !== idx))
  }

  return (
    <Box>
      {/* Toolbar */}
      <Stack direction="row" spacing={2} mb={2} flexWrap="wrap" alignItems="center">
        <TextField
          size="small"
          placeholder="Buscar recepción, almacén u operario…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0) }}
          sx={{ minWidth: 260 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search sx={{ fontSize: 18, color: 'text.disabled' }} />
              </InputAdornment>
            ),
          }}
        />
        <Box sx={{ flexGrow: 1 }} />
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => setOpenDialog(true)}
          sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: alpha(WMS_COLOR, 0.85) } }}
        >
          Nueva Recepción
        </Button>
      </Stack>

      {/* Table */}
      <Card elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px' }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#F9FAFB', '& th': { fontSize: 12, fontWeight: 700, color: 'text.secondary', py: 1.5 } }}>
                <TableCell>N° Recepción</TableCell>
                <TableCell>Tipo</TableCell>
                <TableCell>OC Referencia</TableCell>
                <TableCell>Almacén</TableCell>
                <TableCell>Fecha</TableCell>
                <TableCell>Estado</TableCell>
                <TableCell>Operario</TableCell>
                <TableCell align="center">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {isLoading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 8 }).map((_, j) => (
                        <TableCell key={j}>
                          <Box sx={{ bgcolor: '#F3F4F6', height: 14, borderRadius: 1 }} />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : paginated.length === 0
                ? (
                  <TableRow>
                    <TableCell colSpan={8} align="center" sx={{ py: 6, color: 'text.secondary', fontSize: 13 }}>
                      No se encontraron recepciones
                    </TableCell>
                  </TableRow>
                )
                : paginated.map((r) => (
                  <TableRow
                    key={r.id}
                    hover
                    onClick={() => setDetalleRec(r)}
                    sx={{ cursor: 'pointer', '& td': { fontSize: 12, py: 1 } }}
                  >
                    <TableCell sx={{ fontWeight: 700, color: WMS_COLOR }}>{r.numero_recepcion}</TableCell>
                    <TableCell>
                      <Chip
                        label={r.tipo}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: 10, fontWeight: 600, borderColor: WMS_COLOR, color: WMS_COLOR }}
                      />
                    </TableCell>
                    <TableCell>{r.numero_oc || '—'}</TableCell>
                    <TableCell>{r.almacen_nombre}</TableCell>
                    <TableCell>
                      {r.fecha_recepcion ? format(fechaLocal(r.fecha_recepcion), 'dd MMM yyyy', { locale: es }) : '—'}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={r.estado}
                        size="small"
                        color={REC_ESTADO_COLOR[r.estado] ?? 'default'}
                        sx={{ fontSize: 11, fontWeight: 600 }}
                      />
                    </TableCell>
                    <TableCell>{r.operario || '—'}</TableCell>
                    <TableCell align="center" onClick={(e) => e.stopPropagation()}>
                      {r.estado !== 'COMPLETA' && r.estado !== 'RECHAZADA' && (
                        <Tooltip title="Completar Recepción">
                          <IconButton
                            size="small"
                            color="success"
                            disabled={completarRec.isPending}
                            onClick={(e) => { e.stopPropagation(); completarRec.mutate(r.id) }}
                          >
                            <CheckCircleOutline fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              }
            </TableBody>
          </Table>
        </Box>
        <TablePagination
          component="div"
          count={filtered.length}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => { setRowsPerPage(+e.target.value); setPage(0) }}
          rowsPerPageOptions={[25, 50, 100, 200]}
          labelRowsPerPage="Por página:"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} de ${count}`}
          sx={{ fontSize: 12 }}
        />
      </Card>

      {/* ── Create Recepcion Dialog ────────────────────────────────────── */}
      <Dialog open={openDialog} onClose={handleClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 0.5 }}>
          Nueva Recepción
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 400 }}>
            Registra los artículos recibidos y su ubicación en bodega
          </Typography>
        </DialogTitle>
        <DialogContent dividers sx={{ px: 3, py: 2.5 }}>
          <Grid container spacing={2.5} sx={{ pt: 0.5 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <NumeroAutomatico tipo="REC" etiqueta="Número de recepción" />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Tipo *</InputLabel>
                <Select
                  value={form.tipo}
                  label="Tipo *"
                  onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))}
                >
                  <MenuItem value="CONTRA_OC">Contra OC</MenuItem>
                  <MenuItem value="ASN">ASN</MenuItem>
                  <MenuItem value="CIEGA">Ciega</MenuItem>
                  <MenuItem value="PARCIAL">Parcial</MenuItem>
                  <MenuItem value="CONSOLIDADA">Consolidada</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Orden de Compra (opcional)</InputLabel>
                <Select
                  value={form.orden_compra_id}
                  label="Orden de Compra (opcional)"
                  onChange={(e) => elegirOC(e.target.value as string | number)}
                >
                  <MenuItem value=""><em>Sin OC asociada</em></MenuItem>
                  {ordenesCompra
                    .filter((o) => estadosOC.admiteRecepcion(o.estado))
                    .map((o) => (
                      <MenuItem key={o.id} value={o.id}>
                        {o.numero_oc} — {o.proveedor?.nombre ?? o.proveedor_nombre}
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Almacén *</InputLabel>
                <Select
                  value={form.almacen_id}
                  label="Almacén *"
                  onChange={(e) => setForm((f) => ({ ...f, almacen_id: e.target.value as string }))}
                >
                  {almacenes.map((a) => (
                    <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Fecha Recepción *"
                type="date"
                fullWidth
                size="small"
                value={form.fecha_recepcion}
                onChange={(e) => setForm((f) => ({ ...f, fecha_recepcion: e.target.value }))}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Muelle"
                fullWidth
                size="small"
                value={form.muelle}
                onChange={(e) => setForm((f) => ({ ...f, muelle: e.target.value }))}
                helperText="La hora de llegada se toma al registrar la recepción"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                label="Notas"
                fullWidth
                size="small"
                multiline
                rows={2}
                value={form.notas}
                onChange={(e) => setForm((f) => ({ ...f, notas: e.target.value }))}
              />
            </Grid>

            {/* Artículos: selección manual, escáner o RFID */}
            <Grid size={{ xs: 12 }}>
              <Divider sx={{ mb: 1.5 }} />
              <ArticulosRecepcion
                lineas={lineas}
                setLineas={setLineas}
                productos={productos}
                ubicaciones={ubicacionesFiltradas}
                conOC={!!form.orden_compra_id}
              />
            </Grid>

            {formError && (
              <Grid size={{ xs: 12 }}>
                <Alert severity="error" sx={{ py: 0.5 }}>{formError}</Alert>
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={handleClose} disabled={createRec.isPending}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={createRec.isPending}
            sx={{ bgcolor: WMS_COLOR, '&:hover': { bgcolor: alpha(WMS_COLOR, 0.85) } }}
          >
            {createRec.isPending ? 'Guardando...' : 'Crear Recepción'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Detail Recepcion Dialog ────────────────────────────────────── */}
      <Dialog
        open={!!detalleRec}
        onClose={() => setDetalleRec(null)}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        {detalleRec && (
          <>
            <DialogTitle sx={{ fontWeight: 700, fontSize: 16, pb: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap">
                <span>Recepción {detalleRec.numero_recepcion}</span>
                <Chip
                  label={detalleRec.estado}
                  size="small"
                  color={REC_ESTADO_COLOR[detalleRec.estado] ?? 'default'}
                  sx={{ fontSize: 11, fontWeight: 600 }}
                />
              </Stack>
            </DialogTitle>
            <DialogContent dividers sx={{ px: 3, py: 2.5 }}>
              {/* Cabecera */}
              <SeccionTitulo>Información general</SeccionTitulo>
              <Grid container spacing={2} sx={{ mt: 0.5, mb: 2.5 }}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo label="Tipo" value={detalleRec.tipo} />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo label="OC Referencia" value={detalleRec.numero_oc || '—'} />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo
                    label="Almacén"
                    value={detalleRec.almacen?.nombre ?? detalleRec.almacen_nombre}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo label="Fecha Recepción" value={fmtFecha(detalleRec.fecha_recepcion)} />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetalleCampo label="Operario" value={detalleRec.operario || '—'} />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <DetalleCampo label="Notas" value={detalleRec.notas || '—'} />
                </Grid>
              </Grid>

              {/* Artículos */}
              <Divider sx={{ mb: 2 }} />
              <SeccionTitulo>Artículos</SeccionTitulo>
              {!detalleRec.detalles || detalleRec.detalles.length === 0 ? (
                <Typography fontSize={12} color="text.secondary" sx={{ py: 2 }}>
                  Esta recepción no tiene artículos registrados.
                </Typography>
              ) : (
                <Box sx={{ overflowX: 'auto', mt: 1 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ '& th': { fontSize: 11, fontWeight: 700, color: 'text.secondary' } }}>
                        <TableCell>Producto</TableCell>
                        <TableCell>Lote</TableCell>
                        <TableCell align="right">Esperada</TableCell>
                        <TableCell align="right">Recibida</TableCell>
                        <TableCell>Ubicación</TableCell>
                        <TableCell>Calidad</TableCell>
                        <TableCell>Novedad</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {detalleRec.detalles.map((d, i) => (
                        <TableRow key={i} sx={{ '& td': { fontSize: 12 } }}>
                          <TableCell>
                            <Typography sx={{ fontSize: 12, fontWeight: 600 }}>
                              {d.producto?.nombre ?? '—'}
                            </Typography>
                            {d.producto?.sku && (
                              <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
                                {d.producto.sku}
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell>{d.lote?.numero_lote ?? '—'}</TableCell>
                          <TableCell align="right">{Number(d.cantidad_esperada) || 0}</TableCell>
                          <TableCell align="right">{Number(d.cantidad_recibida) || 0}</TableCell>
                          <TableCell>{d.ubicacion?.codigo ?? '—'}</TableCell>
                          <TableCell>
                            {d.estado_calidad ? (
                              <Chip
                                label={d.estado_calidad}
                                size="small"
                                color={CALIDAD_COLOR[d.estado_calidad] ?? 'default'}
                                sx={{ fontSize: 10, fontWeight: 600 }}
                              />
                            ) : (
                              '—'
                            )}
                          </TableCell>
                          <TableCell>
                            {d.novedad ? (
                              <Tooltip title={d.notas || ''}>
                                <Chip label={nombreNovedad(d.novedad)} size="small" color="warning" variant="outlined" sx={{ fontSize: 10, fontWeight: 600 }} />
                              </Tooltip>
                            ) : '—'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </DialogContent>
            <DialogActions sx={{ px: 3, py: 2 }}>
              <BotonPDF tipo="recepcion" id={detalleRec.id} etiqueta="Acta de recepción (PDF)" />
              <Button onClick={() => setDetalleRec(null)}>Cerrar</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Box>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WMSRecepcion() {
  const [tab, setTab] = useState(0)

  return (
    <Layout title="WMS — Recepción de Mercancía">
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>

        {/* Header */}
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: '10px',
              bgcolor: alpha(WMS_COLOR, 0.12),
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <MoveToInbox sx={{ color: WMS_COLOR, fontSize: 22 }} />
          </Box>
          <Box>
            <Typography fontSize={22} fontWeight={800} color="text.primary">
              Recepción de Mercancía
            </Typography>
            <Typography fontSize={12} color="text.secondary">
              Gestión de órdenes de compra y recepciones en almacén
            </Typography>
          </Box>
        </Stack>

        {/* Tabs */}
        <Card elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px' }}>
          <Box sx={{ borderBottom: '1px solid #E5E7EB' }}>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              sx={{
                px: 2,
                '& .MuiTab-root': { fontSize: 13, fontWeight: 600, textTransform: 'none', minHeight: 48 },
                '& .Mui-selected': { color: WMS_COLOR },
                '& .MuiTabs-indicator': { bgcolor: WMS_COLOR },
              }}
            >
              <Tab
                icon={<OutboundOutlined sx={{ fontSize: 18 }} />}
                iconPosition="start"
                label="Órdenes de Compra"
              />
              <Tab
                icon={<MoveToInbox sx={{ fontSize: 18 }} />}
                iconPosition="start"
                label="Recepciones"
              />
            </Tabs>
          </Box>
          <CardContent sx={{ p: { xs: 1.5, sm: 2.5 } }}>
            {tab === 0 && <OrdenesCompraTab />}
            {tab === 1 && <RecepcionesTab />}
          </CardContent>
        </Card>

      </Box>
    </Layout>
  )
}
