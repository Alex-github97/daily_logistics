import React, { useState } from 'react'
import {
  Box, Paper, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, IconButton, Stack, Tabs, Tab, Tooltip, CircularProgress, alpha, Switch, FormControlLabel, Chip, Autocomplete,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Add as AddIcon, Edit as EditIcon, Delete as DeleteIcon, Architecture } from '@mui/icons-material'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import { GestionCanales } from '@/pages/WMSCanalesVenta'
import toast from 'react-hot-toast'

import { COLOR_MODULO } from '@/config/marca'
import { AdminCatalogos } from '@/components/catalogo/AdminCatalogos'
import { mensajeDeError } from '@/utils/errorApi'
import { useEstadosOC, type EstadoOC } from '@/api/estadosOC'
import { TablaRegistros, FormularioRegistro, type Campo } from '@/components/comun/Registro'
const WMS_COLOR = COLOR_MODULO

// ─── Generic catalog hook ──────────────────────────────────────────────────────
function useCatalog<T extends { id: number }>(endpoint: string, queryKey: string[]) {
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery<T[]>({
    queryKey,
    queryFn: () => api.get(endpoint).then(r => r.data),
  })
  const create = useMutation({
    mutationFn: (d: object) => api.post(endpoint, d).then(r => r.data),
    onSuccess: () => { toast.success('Registro creado'); qc.invalidateQueries({ queryKey }) },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al crear')),
  })
  const update = useMutation({
    mutationFn: ({ id, d }: { id: number; d: object }) => api.put(`${endpoint}${id}`, d).then(r => r.data),
    onSuccess: () => { toast.success('Registro actualizado'); qc.invalidateQueries({ queryKey }) },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al actualizar')),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`${endpoint}${id}`),
    onSuccess: () => { toast.success('Registro eliminado'); qc.invalidateQueries({ queryKey }) },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al eliminar')),
  })
  return { data, isLoading, create, update, remove }
}

// ─── Generic item type ────────────────────────────────────────────────────────
interface SimpleItem { id: number; nombre: string; [key: string]: unknown }

// ─── Generic item card ─────────────────────────────────────────────────────────
function ItemCard({
  item, extraLabels, onEdit, onDelete, accion,
}: {
  item: SimpleItem
  extraLabels?: { key: string; label: string }[]
  onEdit: () => void
  onDelete: () => void
  accion?: React.ReactNode
}) {
  return (
    <Paper elevation={0} sx={{
      border: '1px solid #E5E7EB', borderRadius: '10px', p: 2,
      '&:hover': { borderColor: alpha(WMS_COLOR, 0.3) }, transition: 'border-color 0.12s',
    }}>
      <Stack direction="row" alignItems="center" gap={1}>
        <Box flex={1}>
          <Typography fontSize={13} fontWeight={600}>{item.nombre ?? (item.codigo as string) ?? String(item.id)}</Typography>
          {extraLabels?.map(el => item[el.key] != null && (
            <Typography key={el.key} fontSize={11} color="text.secondary">
              {el.label}: {String(item[el.key])}
            </Typography>
          ))}
        </Box>
        {accion}
        <Tooltip title="Editar">
          <IconButton size="small" onClick={onEdit}><EditIcon sx={{ fontSize: 14, color: '#9CA3AF' }} /></IconButton>
        </Tooltip>
        <Tooltip title="Eliminar">
          <IconButton size="small" onClick={onDelete}><DeleteIcon sx={{ fontSize: 14, color: '#EF4444' }} /></IconButton>
        </Tooltip>
      </Stack>
    </Paper>
  )
}

// ─── Confirm delete dialog ─────────────────────────────────────────────────────
function ConfirmDelete({ open, title, onConfirm, onCancel, loading }: { open: boolean; title: string; onConfirm: () => void; onCancel: () => void; loading: boolean }) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>Eliminar {title}</DialogTitle>
      <DialogContent><Typography fontSize={13} color="text.secondary">¿Confirmar eliminación?</Typography></DialogContent>
      <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
        <Button size="small" onClick={onCancel} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button size="small" variant="contained" color="error" disabled={loading} onClick={onConfirm} sx={{ textTransform: 'none' }}>Eliminar</Button>
      </DialogActions>
    </Dialog>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Helper: CatalogSection — sección genérica nombre + campo extra opcional
// ═══════════════════════════════════════════════════════════════════════════════
interface TipoSimple extends SimpleItem { nombre: string; descripcion?: string; abreviatura?: string; activo: boolean }
interface FamiliaItem extends SimpleItem { nombre: string; categoria_id: number; categoria_nombre?: string; activo: boolean }
interface CategoriaItem extends SimpleItem { nombre: string; activo: boolean }

function TiposZonaSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<TipoSimple>('/wms/tipos-zona/', ['wms-tipos-zona'])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<TipoSimple | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ nombre: '', descripcion: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: TipoSimple) => {
    if (item) { setEditing(item); setForm({ nombre: item.nombre, descripcion: (item.descripcion as string) ?? '' }) }
    else { setEditing(null); setForm({ nombre: '', descripcion: '' }) }
    setOpen(true)
  }
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre) { toast.error('El nombre es obligatorio'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }
  return (
    <SectionShell title="Tipos de Zona" subtitle="Clasificaciones de zonas dentro de los almacenes" onNew={() => openDialog()} isLoading={isLoading}>
      {items.map(item => (
        <ItemCard key={item.id} item={item} extraLabels={[{ key: 'descripcion', label: 'Descripción' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Tipo de Zona' : 'Nuevo Tipo de Zona'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Nombre *" size="small" fullWidth value={form.nombre} onChange={e => set('nombre', e.target.value)} />
            <TextField label="Descripción" size="small" fullWidth value={form.descripcion} onChange={e => set('descripcion', e.target.value)} />
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Tipo de Zona" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

function TiposUbicacionSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<TipoSimple>('/wms/tipos-ubicacion/', ['wms-tipos-ubicacion'])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<TipoSimple | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ nombre: '', descripcion: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: TipoSimple) => {
    if (item) { setEditing(item); setForm({ nombre: item.nombre, descripcion: (item.descripcion as string) ?? '' }) }
    else { setEditing(null); setForm({ nombre: '', descripcion: '' }) }
    setOpen(true)
  }
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre) { toast.error('El nombre es obligatorio'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }
  return (
    <SectionShell title="Tipos de Ubicación" subtitle="Clasificaciones de posiciones dentro de las zonas" onNew={() => openDialog()} isLoading={isLoading}>
      {items.map(item => (
        <ItemCard key={item.id} item={item} extraLabels={[{ key: 'descripcion', label: 'Descripción' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Tipo de Ubicación' : 'Nuevo Tipo de Ubicación'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Nombre *" size="small" fullWidth value={form.nombre} onChange={e => set('nombre', e.target.value)} />
            <TextField label="Descripción" size="small" fullWidth value={form.descripcion} onChange={e => set('descripcion', e.target.value)} />
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Tipo de Ubicación" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

function UnidadesMedidaSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<TipoSimple>('/wms/unidades-medida/', ['wms-unidades-medida'])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<TipoSimple | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ nombre: '', abreviatura: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: TipoSimple) => {
    if (item) { setEditing(item); setForm({ nombre: item.nombre, abreviatura: (item.abreviatura as string) ?? '' }) }
    else { setEditing(null); setForm({ nombre: '', abreviatura: '' }) }
    setOpen(true)
  }
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre) { toast.error('El nombre es obligatorio'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }
  return (
    <SectionShell title="Unidades de Medida" subtitle="Unidades para productos e inventario" onNew={() => openDialog()} isLoading={isLoading}>
      {items.map(item => (
        <ItemCard key={item.id} item={item} extraLabels={[{ key: 'abreviatura', label: 'Abreviatura' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Unidad de Medida' : 'Nueva Unidad de Medida'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Nombre * (ej: Kilogramo)" size="small" fullWidth value={form.nombre} onChange={e => set('nombre', e.target.value)} />
            <TextField label="Abreviatura (ej: kg)" size="small" fullWidth value={form.abreviatura} onChange={e => set('abreviatura', e.target.value)} inputProps={{ maxLength: 15 }} />
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Unidad de Medida" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

interface MotivoItem extends SimpleItem { nombre: string; tipo: string }

function MotivosMovimientoSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<MotivoItem>('/wms/motivos-movimiento/', ['wms-motivos-movimiento'])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<MotivoItem | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ nombre: '', tipo: 'RESERVA' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: MotivoItem) => {
    if (item) { setEditing(item); setForm({ nombre: item.nombre, tipo: item.tipo ?? 'RESERVA' }) }
    else { setEditing(null); setForm({ nombre: '', tipo: 'RESERVA' }) }
    setOpen(true)
  }
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre) { toast.error('El nombre es obligatorio'); return }
    if (editing) update.mutate({ id: editing.id, d: form }, { onSuccess: () => setOpen(false) })
    else create.mutate(form, { onSuccess: () => setOpen(false) })
  }
  return (
    <SectionShell title="Motivos de Reserva / Bloqueo" subtitle="Causas configurables para reservar o bloquear inventario" onNew={() => openDialog()} isLoading={isLoading}>
      {items.map(item => (
        <ItemCard key={item.id} item={item} extraLabels={[{ key: 'tipo', label: 'Aplica a' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Motivo' : 'Nuevo Motivo'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Nombre *" size="small" fullWidth value={form.nombre} onChange={e => set('nombre', e.target.value)} />
            <TextField select label="Aplica a *" size="small" fullWidth value={form.tipo} onChange={e => set('tipo', e.target.value)}>
              <MenuItem value="RESERVA">Reserva</MenuItem>
              <MenuItem value="BLOQUEO">Bloqueo</MenuItem>
            </TextField>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Motivo" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

function CategoriasSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<CategoriaItem>('/wms/categorias-producto/', ['wms-categorias'])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<CategoriaItem | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [nombre, setNombre] = useState('')

  const openDialog = (item?: CategoriaItem) => {
    if (item) { setEditing(item); setNombre(item.nombre) }
    else { setEditing(null); setNombre('') }
    setOpen(true)
  }
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!nombre) { toast.error('El nombre es obligatorio'); return }
    if (editing) update.mutate({ id: editing.id, d: { nombre } }, { onSuccess: () => setOpen(false) })
    else create.mutate({ nombre }, { onSuccess: () => setOpen(false) })
  }
  return (
    <SectionShell title="Categorías de Producto" subtitle="Agrupaciones principales del catálogo de productos" onNew={() => openDialog()} isLoading={isLoading}>
      {items.map(item => (
        <ItemCard key={item.id} item={item} onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Categoría' : 'Nueva Categoría'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><TextField label="Nombre *" size="small" fullWidth value={nombre} onChange={e => setNombre(e.target.value)} sx={{ mt: 0.5 }} /></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Categoría" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

function FamiliasSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<FamiliaItem>('/wms/familias-producto/', ['wms-familias'])
  const { data: categorias = [] } = useQuery<CategoriaItem[]>({ queryKey: ['wms-categorias'], queryFn: () => api.get('/wms/categorias-producto/').then(r => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<FamiliaItem | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ nombre: '', categoria_id: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: FamiliaItem) => {
    if (item) { setEditing(item); setForm({ nombre: item.nombre, categoria_id: item.categoria_id.toString() }) }
    else { setEditing(null); setForm({ nombre: '', categoria_id: '' }) }
    setOpen(true)
  }
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre) { toast.error('El nombre es obligatorio'); return }
    if (!form.categoria_id) { toast.error('La categoría es obligatoria'); return }
    const payload = { nombre: form.nombre, categoria_id: Number(form.categoria_id) }
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }
  return (
    <SectionShell title="Familias de Producto" subtitle="Subagrupaciones dentro de cada categoría" onNew={() => openDialog()} isLoading={isLoading}>
      {items.map(item => (
        <ItemCard key={item.id} item={item} extraLabels={[{ key: 'categoria_nombre', label: 'Categoría' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Familia' : 'Nueva Familia'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Nombre *" size="small" fullWidth value={form.nombre} onChange={e => set('nombre', e.target.value)} />
            <TextField select label="Categoría *" size="small" fullWidth value={form.categoria_id} onChange={e => set('categoria_id', e.target.value)}>
              <MenuItem value="">Seleccionar categoría</MenuItem>
              {categorias.map(c => <MenuItem key={c.id} value={c.id.toString()}>{c.nombre}</MenuItem>)}
            </TextField>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Familia" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 1: Países
// ═══════════════════════════════════════════════════════════════════════════════
interface Pais extends SimpleItem { nombre: string; codigo_iso?: string; activo: boolean }

function PaisesSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<Pais>('/wms/paises/', ['wms-paises'])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Pais | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ nombre: '', codigo_iso: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: Pais) => {
    if (item) { setEditing(item); setForm({ nombre: item.nombre, codigo_iso: (item.codigo_iso as string) ?? '' }) }
    else { setEditing(null); setForm({ nombre: '', codigo_iso: '' }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre) { toast.error('El nombre es obligatorio'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Países" subtitle="Catálogo de países para almacenes y contactos" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Pais[]).map(item => (
        <ItemCard key={item.id} item={item}
          extraLabels={[{ key: 'codigo_iso', label: 'Código ISO' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar País' : 'Nuevo País'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Nombre *" size="small" fullWidth value={form.nombre} onChange={e => set('nombre', e.target.value)} />
            <TextField label="Código ISO (ej: CO, US)" size="small" fullWidth value={form.codigo_iso} onChange={e => set('codigo_iso', e.target.value)} inputProps={{ maxLength: 5 }} />
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="País" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 2: Ciudades
// ═══════════════════════════════════════════════════════════════════════════════
interface Ciudad extends SimpleItem { nombre: string; pais_id: number; pais_nombre?: string; activo: boolean }

function CiudadesSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<Ciudad>('/wms/ciudades/', ['wms-ciudades'])
  const { data: paises = [] } = useQuery<Pais[]>({ queryKey: ['wms-paises'], queryFn: () => api.get('/wms/paises/').then(r => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Ciudad | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ nombre: '', pais_id: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: Ciudad) => {
    if (item) { setEditing(item); setForm({ nombre: item.nombre, pais_id: item.pais_id.toString() }) }
    else { setEditing(null); setForm({ nombre: '', pais_id: '' }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre) { toast.error('El nombre es obligatorio'); return }
    if (!form.pais_id) { toast.error('El país es obligatorio'); return }
    const payload = { nombre: form.nombre, pais_id: Number(form.pais_id) }
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Ciudades" subtitle="Catálogo de ciudades para almacenes y contactos" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Ciudad[]).map(item => (
        <ItemCard key={item.id} item={item}
          extraLabels={[{ key: 'pais_nombre', label: 'País' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Ciudad' : 'Nueva Ciudad'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Nombre *" size="small" fullWidth value={form.nombre} onChange={e => set('nombre', e.target.value)} />
            <TextField select label="País *" size="small" fullWidth value={form.pais_id} onChange={e => set('pais_id', e.target.value)}>
              <MenuItem value="">Seleccionar país</MenuItem>
              {(paises as Pais[]).map(p => <MenuItem key={p.id} value={p.id.toString()}>{p.nombre}</MenuItem>)}
            </TextField>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Ciudad" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 3: Almacenes
// ═══════════════════════════════════════════════════════════════════════════════
interface Almacen extends SimpleItem { codigo: string; nombre: string; direccion?: string; ciudad?: string; pais?: string; flujo_recepcion?: string }

function AlmacenesSection() {
  const navigate = useNavigate()
  const { data: items, isLoading, create, update, remove } = useCatalog<Almacen>('/wms/almacenes/', ['wms-almacenes'])
  const { data: paises = [] } = useQuery<Pais[]>({ queryKey: ['wms-paises'], queryFn: () => api.get('/wms/paises/').then(r => r.data) })
  const { data: ciudades = [] } = useQuery<Ciudad[]>({ queryKey: ['wms-ciudades'], queryFn: () => api.get('/wms/ciudades/').then(r => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Almacen | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ codigo: '', nombre: '', direccion: '', ciudad: '', pais: '', flujo_recepcion: 'DIRECTO' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const ciudadesFiltradas = (paises as Pais[]).length > 0 && form.pais
    ? (ciudades as Ciudad[]).filter(c => {
        const p = (paises as Pais[]).find(p => p.nombre === form.pais)
        return p ? c.pais_id === p.id : true
      })
    : (ciudades as Ciudad[])

  const openDialog = (item?: Almacen) => {
    if (item) { setEditing(item); setForm({ codigo: item.codigo, nombre: item.nombre, direccion: item.direccion ?? '', ciudad: item.ciudad ?? '', pais: item.pais ?? '', flujo_recepcion: item.flujo_recepcion ?? 'DIRECTO' }) }
    else { setEditing(null); setForm({ codigo: '', nombre: '', direccion: '', ciudad: '', pais: '', flujo_recepcion: 'DIRECTO' }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.codigo || !form.nombre) { toast.error('Código y nombre son obligatorios'); return }
    if (!form.pais) { toast.error('El país es obligatorio'); return }
    if (!form.ciudad) { toast.error('La ciudad es obligatoria'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Almacenes" subtitle="Instalaciones físicas del WMS" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Almacen[]).map(item => (
        <ItemCard key={item.id} item={item}
          extraLabels={[{ key: 'codigo', label: 'Código' }, { key: 'ciudad', label: 'Ciudad' }, { key: 'pais', label: 'País' }, { key: 'flujo_recepcion', label: 'Recepción' }]}
          accion={<Button size="small" variant="outlined" startIcon={<Architecture sx={{ fontSize: 16 }} />} onClick={() => navigate(`/wms/constructor?almacen=${item.id}`)}
            sx={{ textTransform: 'none', borderRadius: 2, mr: 0.5 }}>Diseñar bodega</Button>}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Almacén' : 'Nuevo Almacén'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <Stack direction="row" gap={1.5}>
              <TextField label="Código *" size="small" value={form.codigo} onChange={e => set('codigo', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Nombre *" size="small" value={form.nombre} onChange={e => set('nombre', e.target.value)} sx={{ flex: 2 }} />
            </Stack>
            <TextField label="Dirección" size="small" value={form.direccion} onChange={e => set('direccion', e.target.value)} fullWidth />
            <TextField select label="País *" size="small" fullWidth value={form.pais}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => { set('pais', e.target.value); set('ciudad', '') }}>
              <MenuItem value="">Seleccionar país</MenuItem>
              {(paises as Pais[]).map(p => <MenuItem key={p.id} value={p.nombre}>{p.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Ciudad *" size="small" fullWidth value={form.ciudad}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('ciudad', e.target.value)} disabled={!form.pais}>
              <MenuItem value="">Seleccionar ciudad</MenuItem>
              {ciudadesFiltradas.map(c => <MenuItem key={c.id} value={c.nombre}>{c.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Cómo entra la mercancía" size="small" fullWidth value={form.flujo_recepcion}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('flujo_recepcion', e.target.value)}
              helperText={form.flujo_recepcion === 'DIRIGIDO'
                ? 'Se recibe en la zona de recepción, en una estiba (LPN) por línea, y una tarea indica dónde ubicarla. Requiere zona de RECEPCION.'
                : 'La recepción deja la mercancía directamente en su ubicación.'}>
              <MenuItem value="DIRECTO">Directo a la ubicación</MenuItem>
              <MenuItem value="DIRIGIDO">Ubicación dirigida (con tareas)</MenuItem>
            </TextField>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Almacén" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 2: Zonas
// ═══════════════════════════════════════════════════════════════════════════════
interface Zona extends SimpleItem { codigo: string; nombre: string; almacen_id?: number; tipo?: string; temperatura_controlada?: boolean }

function ZonasSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<Zona>('/wms/zonas/', ['wms-zonas'])
  const { data: almacenes = [] } = useQuery<Almacen[]>({ queryKey: ['wms-almacenes'], queryFn: () => api.get('/wms/almacenes/').then((r: { data: Almacen[] }) => r.data) })
  const { data: tiposZona = [] } = useQuery<TipoSimple[]>({ queryKey: ['wms-tipos-zona'], queryFn: () => api.get('/wms/tipos-zona/').then((r: { data: TipoSimple[] }) => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Zona | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ codigo: '', nombre: '', almacen_id: '', tipo: '', temperatura_controlada: false })
  const set = (k: string, v: string | boolean) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: Zona) => {
    if (item) { setEditing(item); setForm({ codigo: item.codigo, nombre: item.nombre, almacen_id: item.almacen_id?.toString() ?? '', tipo: item.tipo ?? '', temperatura_controlada: item.temperatura_controlada ?? false }) }
    else { setEditing(null); setForm({ codigo: '', nombre: '', almacen_id: '', tipo: '', temperatura_controlada: false }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.codigo || !form.nombre) { toast.error('Código y nombre son obligatorios'); return }
    if (!form.tipo) { toast.error('El tipo de zona es obligatorio'); return }
    if (!form.almacen_id) { toast.error('El almacén es obligatorio'); return }
    const payload: Record<string, unknown> = { codigo: form.codigo, nombre: form.nombre, tipo: form.tipo, temperatura_controlada: form.temperatura_controlada, almacen_id: Number(form.almacen_id) }
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Zonas" subtitle="Divisiones internas de los almacenes" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Zona[]).map(item => (
        <ItemCard key={item.id} item={item}
          extraLabels={[{ key: 'codigo', label: 'Código' }, { key: 'tipo', label: 'Tipo' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Zona' : 'Nueva Zona'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <Stack direction="row" gap={1.5}>
              <TextField label="Código *" size="small" value={form.codigo} onChange={e => set('codigo', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Nombre *" size="small" value={form.nombre} onChange={e => set('nombre', e.target.value)} sx={{ flex: 2 }} />
            </Stack>
            <TextField select label="Almacén *" fullWidth size="small" value={form.almacen_id} onChange={e => set('almacen_id', e.target.value)}>
              <MenuItem value="" disabled>Seleccionar almacén</MenuItem>
              {(almacenes as Almacen[]).map(a => <MenuItem key={a.id} value={a.id.toString()}>{a.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Tipo *" fullWidth size="small" value={form.tipo} onChange={e => set('tipo', e.target.value)}>
              <MenuItem value="">Seleccionar tipo</MenuItem>
              {(tiposZona as TipoSimple[]).map(t => <MenuItem key={t.id} value={t.nombre}>{t.nombre}</MenuItem>)}
            </TextField>
            <FormControlLabel
              control={<Switch checked={form.temperatura_controlada} onChange={e => set('temperatura_controlada', e.target.checked)} sx={{ '& .MuiSwitch-switchBase.Mui-checked': { color: WMS_COLOR }, '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { bgcolor: WMS_COLOR } }} />}
              label={<Typography fontSize={13}>Temperatura controlada</Typography>}
            />
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Zona" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 3: Ubicaciones
// ═══════════════════════════════════════════════════════════════════════════════
interface Ubicacion extends SimpleItem { codigo: string; nombre: string; zona_id?: number; pasillo?: string; estanteria?: string; nivel?: string; posicion?: string; tipo?: string; capacidad_kg?: number; capacidad_m3?: number; largo_cm?: number; ancho_cm?: number; alto_cm?: number; orden_recorrido?: number }

function UbicacionesSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<Ubicacion>('/wms/ubicaciones/', ['wms-ubicaciones'])
  const { data: zonas = [] } = useQuery<Zona[]>({ queryKey: ['wms-zonas'], queryFn: () => api.get('/wms/zonas/').then((r: { data: Zona[] }) => r.data) })
  const { data: tiposUbic = [] } = useQuery<TipoSimple[]>({ queryKey: ['wms-tipos-ubicacion'], queryFn: () => api.get('/wms/tipos-ubicacion/').then((r: { data: TipoSimple[] }) => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Ubicacion | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ codigo: '', zona_id: '', pasillo: '', estanteria: '', nivel: '', posicion: '', tipo: '', capacidad_kg: '', capacidad_m3: '', largo_cm: '', ancho_cm: '', alto_cm: '', orden_recorrido: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: Ubicacion) => {
    if (item) {
      setEditing(item)
      setForm({ codigo: item.codigo, zona_id: item.zona_id?.toString() ?? '', pasillo: item.pasillo ?? '', estanteria: item.estanteria ?? '', nivel: item.nivel ?? '', posicion: item.posicion ?? '', tipo: item.tipo ?? '', capacidad_kg: item.capacidad_kg?.toString() ?? '', capacidad_m3: item.capacidad_m3?.toString() ?? '', largo_cm: item.largo_cm?.toString() ?? '', ancho_cm: item.ancho_cm?.toString() ?? '', alto_cm: item.alto_cm?.toString() ?? '', orden_recorrido: item.orden_recorrido?.toString() ?? '' })
    } else {
      setEditing(null)
      setForm({ codigo: '', zona_id: '', pasillo: '', estanteria: '', nivel: '', posicion: '', tipo: '', capacidad_kg: '', capacidad_m3: '', largo_cm: '', ancho_cm: '', alto_cm: '', orden_recorrido: '' })
    }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.codigo) { toast.error('El código es obligatorio'); return }
    if (!form.zona_id) { toast.error('La zona es obligatoria'); return }
    const payload: Record<string, unknown> = { codigo: form.codigo, zona_id: Number(form.zona_id) }
    if (form.pasillo) payload.pasillo = form.pasillo
    if (form.estanteria) payload.estanteria = form.estanteria
    if (form.nivel) payload.nivel = form.nivel
    if (form.posicion) payload.posicion = form.posicion
    if (form.tipo) payload.tipo = form.tipo
    if (form.capacidad_kg) payload.capacidad_kg = Number(form.capacidad_kg)
    if (form.capacidad_m3) payload.capacidad_m3 = Number(form.capacidad_m3)
    if (form.largo_cm) payload.largo_cm = Number(form.largo_cm)
    if (form.ancho_cm) payload.ancho_cm = Number(form.ancho_cm)
    if (form.alto_cm) payload.alto_cm = Number(form.alto_cm)
    if (form.orden_recorrido) payload.orden_recorrido = Number(form.orden_recorrido)
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Ubicaciones" subtitle="Posiciones físicas dentro de las zonas" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Ubicacion[]).map(item => (
        <ItemCard key={item.id} item={{ ...item, nombre: item.codigo }}
          extraLabels={[{ key: 'tipo', label: 'Tipo' }, { key: 'pasillo', label: 'Pasillo' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Ubicación' : 'Nueva Ubicación'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <Stack direction="row" gap={1.5}>
              <TextField label="Código *" size="small" value={form.codigo} onChange={e => set('codigo', e.target.value)} sx={{ flex: 1 }} />
              <TextField select label="Zona *" size="small" value={form.zona_id} onChange={e => set('zona_id', e.target.value)} sx={{ flex: 2 }}>
                <MenuItem value="" disabled>Seleccionar zona</MenuItem>
                {zonas.map(z => <MenuItem key={z.id} value={z.id.toString()}>{z.nombre}</MenuItem>)}
              </TextField>
            </Stack>
            <Stack direction="row" gap={1.5}>
              <TextField label="Pasillo" size="small" value={form.pasillo} onChange={e => set('pasillo', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Estantería" size="small" value={form.estanteria} onChange={e => set('estanteria', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Nivel" size="small" value={form.nivel} onChange={e => set('nivel', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Posición" size="small" value={form.posicion} onChange={e => set('posicion', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <TextField select label="Tipo" fullWidth size="small" value={form.tipo} onChange={e => set('tipo', e.target.value)}>
              <MenuItem value="">Sin tipo</MenuItem>
              {(tiposUbic as TipoSimple[]).map(t => <MenuItem key={t.id} value={t.nombre}>{t.nombre}</MenuItem>)}
            </TextField>
            <Stack direction="row" gap={1.5}>
              <TextField label="Capacidad (kg)" size="small" type="number" value={form.capacidad_kg} onChange={e => set('capacidad_kg', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Capacidad (m³)" size="small" type="number" value={form.largo_cm && form.ancho_cm && form.alto_cm ? (Number(form.largo_cm) * Number(form.ancho_cm) * Number(form.alto_cm) / 1e6).toFixed(3) : form.capacidad_m3}
                disabled={!!(form.largo_cm && form.ancho_cm && form.alto_cm)} helperText={form.largo_cm && form.ancho_cm && form.alto_cm ? 'Sale de las medidas' : ''}
                onChange={e => set('capacidad_m3', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <Stack direction="row" gap={1.5}>
              <TextField label="Frente (cm)" size="small" type="number" value={form.largo_cm} onChange={e => set('largo_cm', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Fondo (cm)" size="small" type="number" value={form.ancho_cm} onChange={e => set('ancho_cm', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Alto libre (cm)" size="small" type="number" value={form.alto_cm} onChange={e => set('alto_cm', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <Stack direction="row" gap={1.5}>
              <TextField label="Orden en el recorrido de alistamiento" size="small" type="number" value={form.orden_recorrido} onChange={e => set('orden_recorrido', e.target.value)} fullWidth
                helperText="Opcional. Vacío: se deduce del pasillo y la posición (serpentina). El nivel 1 o 2 cuenta como zona dorada." />
            </Stack>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Ubicación" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 4: Productos
// ═══════════════════════════════════════════════════════════════════════════════
interface Producto extends SimpleItem { sku: string; nombre: string; categoria?: string; familia?: string; unidad_medida?: string; peso_kg?: number; volumen_m3?: number; requiere_refrigeracion?: boolean; requiere_serial?: boolean; requiere_lote?: boolean; vida_util_dias?: number; depositante_id?: number | null }

function ProductosSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<Producto>('/wms/productos/', ['wms-productos'])
  const { data: categorias = [] } = useQuery<CategoriaItem[]>({ queryKey: ['wms-categorias'], queryFn: () => api.get('/wms/categorias-producto/').then((r: { data: CategoriaItem[] }) => r.data) })
  const { data: familias = [] } = useQuery<FamiliaItem[]>({ queryKey: ['wms-familias'], queryFn: () => api.get('/wms/familias-producto/').then((r: { data: FamiliaItem[] }) => r.data) })
  const { data: unidades = [] } = useQuery<TipoSimple[]>({ queryKey: ['wms-unidades-medida'], queryFn: () => api.get('/wms/unidades-medida/').then((r: { data: TipoSimple[] }) => r.data) })
  const { data: depositantes = [] } = useQuery<Depositante[]>({ queryKey: ['wms-depositantes'], queryFn: () => api.get('/wms/depositantes').then((r: { data: Depositante[] }) => r.data) })
  const nombreDep = (id?: number | null) => depositantes.find(d => d.id === id)?.nombre ?? ''
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Producto | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ sku: '', nombre: '', categoria: '', familia: '', unidad_medida: '', peso_kg: '', volumen_m3: '', vida_util_dias: '', depositante_id: '', requiere_refrigeracion: false, requiere_serial: false, requiere_lote: false })
  const set = (k: string, v: string | boolean) => setForm(f => ({ ...f, [k]: v }))

  const familiasFiltradas = form.categoria
    ? (familias as FamiliaItem[]).filter(f => {
        const cat = (categorias as CategoriaItem[]).find(c => c.nombre === form.categoria)
        return cat ? f.categoria_id === cat.id : true
      })
    : (familias as FamiliaItem[])

  const openDialog = (item?: Producto) => {
    if (item) {
      setEditing(item)
      setForm({ sku: item.sku, nombre: item.nombre, categoria: item.categoria ?? '', familia: item.familia ?? '', unidad_medida: item.unidad_medida ?? '', peso_kg: item.peso_kg?.toString() ?? '', volumen_m3: item.volumen_m3?.toString() ?? '', vida_util_dias: item.vida_util_dias?.toString() ?? '', depositante_id: item.depositante_id?.toString() ?? '', requiere_refrigeracion: item.requiere_refrigeracion ?? false, requiere_serial: item.requiere_serial ?? false, requiere_lote: item.requiere_lote ?? false })
    } else {
      setEditing(null)
      setForm({ sku: '', nombre: '', categoria: '', familia: '', unidad_medida: '', peso_kg: '', volumen_m3: '', vida_util_dias: '', depositante_id: '', requiere_refrigeracion: false, requiere_serial: false, requiere_lote: false })
    }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.sku || !form.nombre) { toast.error('SKU y nombre son obligatorios'); return }
    const payload: Record<string, unknown> = {
      sku: form.sku, nombre: form.nombre,
      requiere_refrigeracion: form.requiere_refrigeracion,
      requiere_serial: form.requiere_serial,
      requiere_lote: form.requiere_lote,
    }
    if (form.categoria) payload.categoria = form.categoria
    if (form.familia) payload.familia = form.familia
    if (form.unidad_medida) payload.unidad_medida = form.unidad_medida
    if (form.peso_kg) payload.peso_kg = Number(form.peso_kg)
    if (form.volumen_m3) payload.volumen_m3 = Number(form.volumen_m3)
    if (form.vida_util_dias) payload.vida_util_dias = Number(form.vida_util_dias)
    if (form.depositante_id) payload.depositante_id = Number(form.depositante_id)
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  const switchSx = { '& .MuiSwitch-switchBase.Mui-checked': { color: WMS_COLOR }, '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { bgcolor: WMS_COLOR } }

  return (
    <SectionShell title="Productos" subtitle="Catálogo de SKUs del WMS" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Producto[]).map(item => (
        <ItemCard key={item.id} item={{ ...item, nombre: item.nombre, depositante: nombreDep(item.depositante_id) }}
          extraLabels={[{ key: 'sku', label: 'SKU' }, { key: 'depositante', label: 'Dueño' }, { key: 'categoria', label: 'Categoría' }, { key: 'unidad_medida', label: 'Unidad' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Producto' : 'Nuevo Producto'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <Stack direction="row" gap={1.5}>
              <TextField label="SKU *" size="small" value={form.sku} onChange={e => set('sku', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Nombre *" size="small" value={form.nombre} onChange={e => set('nombre', e.target.value)} sx={{ flex: 2 }} />
            </Stack>
            <TextField select label="Depositante (dueño de la mercancía)" size="small" fullWidth value={form.depositante_id}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('depositante_id', e.target.value)}
              helperText="Vacío = mercancía propia. No se puede cambiar mientras el producto tenga existencias.">
              <MenuItem value="">Mercancía propia</MenuItem>
              {depositantes.filter(d => d.activo).map(d => <MenuItem key={d.id} value={d.id.toString()}>{d.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Categoría" size="small" fullWidth value={form.categoria}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => { set('categoria', e.target.value); set('familia', '') }}>
              <MenuItem value="">Sin categoría</MenuItem>
              {(categorias as CategoriaItem[]).map(c => <MenuItem key={c.id} value={c.nombre}>{c.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Familia" size="small" fullWidth value={form.familia}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('familia', e.target.value)} disabled={!form.categoria}>
              <MenuItem value="">Sin familia</MenuItem>
              {familiasFiltradas.map(f => <MenuItem key={f.id} value={f.nombre}>{f.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Unidad de medida" size="small" fullWidth value={form.unidad_medida}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('unidad_medida', e.target.value)}>
              <MenuItem value="">Sin unidad</MenuItem>
              {(unidades as TipoSimple[]).map(u => <MenuItem key={u.id} value={u.nombre}>{u.nombre}{u.abreviatura ? ` (${u.abreviatura})` : ''}</MenuItem>)}
            </TextField>
            <Stack direction="row" gap={1.5}>
              <TextField label="Peso (kg)" size="small" type="number" value={form.peso_kg} onChange={e => set('peso_kg', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Volumen (m³)" size="small" type="number" value={form.volumen_m3} onChange={e => set('volumen_m3', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Vida útil (días)" size="small" type="number" value={form.vida_util_dias} onChange={e => set('vida_util_dias', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <Stack direction="row" gap={2} flexWrap="wrap">
              <FormControlLabel control={<Switch checked={form.requiere_refrigeracion} onChange={e => set('requiere_refrigeracion', e.target.checked)} sx={switchSx} />} label={<Typography fontSize={12}>Requiere refrigeración</Typography>} />
              <FormControlLabel control={<Switch checked={form.requiere_serial} onChange={e => set('requiere_serial', e.target.checked)} sx={switchSx} />} label={<Typography fontSize={12}>Requiere serial</Typography>} />
              <FormControlLabel control={<Switch checked={form.requiere_lote} onChange={e => set('requiere_lote', e.target.checked)} sx={switchSx} />} label={<Typography fontSize={12}>Requiere lote</Typography>} />
            </Stack>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Producto" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 5: Lotes
// ═══════════════════════════════════════════════════════════════════════════════
interface Lote extends SimpleItem { numero_lote: string; producto_id?: number; fecha_fabricacion?: string; fecha_vencimiento?: string; proveedor_lote?: string }

function LotesSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<Lote>('/wms/lotes/', ['wms-lotes'])
  const { data: productos = [] } = useQuery<Producto[]>({ queryKey: ['wms-productos'], queryFn: () => api.get('/wms/productos/').then(r => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Lote | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ numero_lote: '', producto_id: '', fecha_fabricacion: '', fecha_vencimiento: '', proveedor_lote: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: Lote) => {
    if (item) { setEditing(item); setForm({ numero_lote: item.numero_lote, producto_id: item.producto_id?.toString() ?? '', fecha_fabricacion: item.fecha_fabricacion ?? '', fecha_vencimiento: item.fecha_vencimiento ?? '', proveedor_lote: item.proveedor_lote ?? '' }) }
    else { setEditing(null); setForm({ numero_lote: '', producto_id: '', fecha_fabricacion: '', fecha_vencimiento: '', proveedor_lote: '' }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.numero_lote) { toast.error('El número de lote es obligatorio'); return }
    const payload: Record<string, unknown> = { numero_lote: form.numero_lote }
    if (form.producto_id) payload.producto_id = Number(form.producto_id)
    if (form.fecha_fabricacion) payload.fecha_fabricacion = form.fecha_fabricacion
    if (form.fecha_vencimiento) payload.fecha_vencimiento = form.fecha_vencimiento
    if (form.proveedor_lote) payload.proveedor_lote = form.proveedor_lote
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Lotes" subtitle="Trazabilidad por número de lote" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Lote[]).map(item => (
        <ItemCard key={item.id} item={{ ...item, nombre: item.numero_lote }}
          extraLabels={[{ key: 'fecha_vencimiento', label: 'Vencimiento' }, { key: 'proveedor_lote', label: 'Proveedor' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Lote' : 'Nuevo Lote'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <TextField label="Número de lote *" fullWidth size="small" value={form.numero_lote} onChange={e => set('numero_lote', e.target.value)} />
            <TextField select label="Producto" fullWidth size="small" value={form.producto_id} onChange={e => set('producto_id', e.target.value)}>
              <MenuItem value="">Sin producto</MenuItem>
              {productos.map(p => <MenuItem key={p.id} value={p.id.toString()}>{p.nombre} ({p.sku})</MenuItem>)}
            </TextField>
            <Stack direction="row" gap={1.5}>
              <TextField label="Fecha fabricación" size="small" type="date" value={form.fecha_fabricacion} onChange={e => set('fecha_fabricacion', e.target.value)} sx={{ flex: 1 }} InputLabelProps={{ shrink: true }} />
              <TextField label="Fecha vencimiento" size="small" type="date" value={form.fecha_vencimiento} onChange={e => set('fecha_vencimiento', e.target.value)} sx={{ flex: 1 }} InputLabelProps={{ shrink: true }} />
            </Stack>
            <TextField label="Proveedor del lote" fullWidth size="small" value={form.proveedor_lote} onChange={e => set('proveedor_lote', e.target.value)} />
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Lote" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 6: Proveedores WMS
// ═══════════════════════════════════════════════════════════════════════════════
interface ProveedorWMS extends SimpleItem { codigo: string; nombre: string; nit?: string; contacto?: string; email?: string; telefono?: string; ciudad?: string; pais?: string }

function ProveedoresWMSSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<ProveedorWMS>('/wms/proveedores/', ['wms-proveedores'])
  const { data: paises = [] } = useQuery<Pais[]>({ queryKey: ['wms-paises'], queryFn: () => api.get('/wms/paises/').then((r: { data: Pais[] }) => r.data) })
  const { data: ciudades = [] } = useQuery<Ciudad[]>({ queryKey: ['wms-ciudades'], queryFn: () => api.get('/wms/ciudades/').then((r: { data: Ciudad[] }) => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ProveedorWMS | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ codigo: '', nombre: '', nit: '', contacto: '', email: '', telefono: '', ciudad: '', pais: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const ciudadesFiltradas = form.pais
    ? (ciudades as Ciudad[]).filter(c => { const p = (paises as Pais[]).find(p => p.nombre === form.pais); return p ? c.pais_id === p.id : true })
    : (ciudades as Ciudad[])

  const openDialog = (item?: ProveedorWMS) => {
    if (item) { setEditing(item); setForm({ codigo: item.codigo, nombre: item.nombre, nit: item.nit ?? '', contacto: item.contacto ?? '', email: item.email ?? '', telefono: item.telefono ?? '', ciudad: item.ciudad ?? '', pais: item.pais ?? '' }) }
    else { setEditing(null); setForm({ codigo: '', nombre: '', nit: '', contacto: '', email: '', telefono: '', ciudad: '', pais: '' }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.codigo || !form.nombre) { toast.error('Código y nombre son obligatorios'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Proveedores" subtitle="Empresas proveedoras de mercancía" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as ProveedorWMS[]).map(item => (
        <ItemCard key={item.id} item={item}
          extraLabels={[{ key: 'codigo', label: 'Código' }, { key: 'nit', label: 'NIT' }, { key: 'ciudad', label: 'Ciudad' }, { key: 'pais', label: 'País' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Proveedor' : 'Nuevo Proveedor'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <Stack direction="row" gap={1.5}>
              <TextField label="Código *" size="small" value={form.codigo} onChange={e => set('codigo', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Nombre *" size="small" value={form.nombre} onChange={e => set('nombre', e.target.value)} sx={{ flex: 2 }} />
            </Stack>
            <Stack direction="row" gap={1.5}>
              <TextField label="NIT" size="small" value={form.nit} onChange={e => set('nit', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Contacto" size="small" value={form.contacto} onChange={e => set('contacto', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <Stack direction="row" gap={1.5}>
              <TextField label="Email" size="small" type="email" value={form.email} onChange={e => set('email', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Teléfono" size="small" value={form.telefono} onChange={e => set('telefono', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <TextField select label="País" size="small" fullWidth value={form.pais}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => { set('pais', e.target.value); set('ciudad', '') }}>
              <MenuItem value="">Sin país</MenuItem>
              {(paises as Pais[]).map(p => <MenuItem key={p.id} value={p.nombre}>{p.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Ciudad" size="small" fullWidth value={form.ciudad}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('ciudad', e.target.value)} disabled={!form.pais}>
              <MenuItem value="">Sin ciudad</MenuItem>
              {ciudadesFiltradas.map(c => <MenuItem key={c.id} value={c.nombre}>{c.nombre}</MenuItem>)}
            </TextField>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Proveedor" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 7: Clientes WMS
// ═══════════════════════════════════════════════════════════════════════════════
interface ClienteWMS extends SimpleItem { codigo: string; nombre: string; nit?: string; contacto?: string; email?: string; telefono?: string; ciudad?: string; pais?: string; segmento?: string }

function ClientesWMSSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<ClienteWMS>('/wms/clientes/', ['wms-clientes'])
  const { data: paises = [] } = useQuery<Pais[]>({ queryKey: ['wms-paises'], queryFn: () => api.get('/wms/paises/').then((r: { data: Pais[] }) => r.data) })
  const { data: ciudades = [] } = useQuery<Ciudad[]>({ queryKey: ['wms-ciudades'], queryFn: () => api.get('/wms/ciudades/').then((r: { data: Ciudad[] }) => r.data) })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ClienteWMS | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ codigo: '', nombre: '', nit: '', contacto: '', email: '', telefono: '', ciudad: '', pais: '', segmento: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const ciudadesFiltradas = form.pais
    ? (ciudades as Ciudad[]).filter(c => { const p = (paises as Pais[]).find(p => p.nombre === form.pais); return p ? c.pais_id === p.id : true })
    : (ciudades as Ciudad[])

  const openDialog = (item?: ClienteWMS) => {
    if (item) { setEditing(item); setForm({ codigo: item.codigo, nombre: item.nombre, nit: item.nit ?? '', contacto: item.contacto ?? '', email: item.email ?? '', telefono: item.telefono ?? '', ciudad: item.ciudad ?? '', pais: item.pais ?? '', segmento: item.segmento ?? '' }) }
    else { setEditing(null); setForm({ codigo: '', nombre: '', nit: '', contacto: '', email: '', telefono: '', ciudad: '', pais: '', segmento: '' }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.codigo || !form.nombre) { toast.error('Código y nombre son obligatorios'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Clientes" subtitle="Clientes que reciben mercancía del WMS" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as ClienteWMS[]).map(item => (
        <ItemCard key={item.id} item={item}
          extraLabels={[{ key: 'codigo', label: 'Código' }, { key: 'nit', label: 'NIT' }, { key: 'segmento', label: 'Segmento' }, { key: 'ciudad', label: 'Ciudad' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Cliente' : 'Nuevo Cliente'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <Stack direction="row" gap={1.5}>
              <TextField label="Código *" size="small" value={form.codigo} onChange={e => set('codigo', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Nombre *" size="small" value={form.nombre} onChange={e => set('nombre', e.target.value)} sx={{ flex: 2 }} />
            </Stack>
            <Stack direction="row" gap={1.5}>
              <TextField label="NIT" size="small" value={form.nit} onChange={e => set('nit', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Segmento" size="small" value={form.segmento} onChange={e => set('segmento', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <Stack direction="row" gap={1.5}>
              <TextField label="Contacto" size="small" value={form.contacto} onChange={e => set('contacto', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Teléfono" size="small" value={form.telefono} onChange={e => set('telefono', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <TextField label="Email" size="small" type="email" fullWidth value={form.email} onChange={e => set('email', e.target.value)} />
            <TextField select label="País" size="small" fullWidth value={form.pais}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => { set('pais', e.target.value); set('ciudad', '') }}>
              <MenuItem value="">Sin país</MenuItem>
              {(paises as Pais[]).map(p => <MenuItem key={p.id} value={p.nombre}>{p.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Ciudad" size="small" fullWidth value={form.ciudad}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('ciudad', e.target.value)} disabled={!form.pais}>
              <MenuItem value="">Sin ciudad</MenuItem>
              {ciudadesFiltradas.map(c => <MenuItem key={c.id} value={c.nombre}>{c.nombre}</MenuItem>)}
            </TextField>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Cliente" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 8: Transportadoras
// ═══════════════════════════════════════════════════════════════════════════════
interface Transportadora extends SimpleItem { codigo: string; nombre: string; nit?: string; contacto?: string; telefono?: string }

function TransportadorasSection() {
  const { data: items, isLoading, create, update, remove } = useCatalog<Transportadora>('/wms/transportadoras/', ['wms-transportadoras'])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Transportadora | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [form, setForm] = useState({ codigo: '', nombre: '', nit: '', contacto: '', telefono: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const openDialog = (item?: Transportadora) => {
    if (item) { setEditing(item); setForm({ codigo: item.codigo, nombre: item.nombre, nit: item.nit ?? '', contacto: item.contacto ?? '', telefono: item.telefono ?? '' }) }
    else { setEditing(null); setForm({ codigo: '', nombre: '', nit: '', contacto: '', telefono: '' }) }
    setOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.codigo || !form.nombre) { toast.error('Código y nombre son obligatorios'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) update.mutate({ id: editing.id, d: payload }, { onSuccess: () => setOpen(false) })
    else create.mutate(payload, { onSuccess: () => setOpen(false) })
  }

  return (
    <SectionShell title="Transportadoras" subtitle="Empresas de transporte y logística" onNew={() => openDialog()} isLoading={isLoading}>
      {(items as Transportadora[]).map(item => (
        <ItemCard key={item.id} item={item}
          extraLabels={[{ key: 'codigo', label: 'Código' }, { key: 'nit', label: 'NIT' }, { key: 'telefono', label: 'Teléfono' }]}
          onEdit={() => openDialog(item)} onDelete={() => setDeleteId(item.id)} />
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar Transportadora' : 'Nueva Transportadora'}</DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent><Stack gap={1.5} pt={0.5}>
            <Stack direction="row" gap={1.5}>
              <TextField label="Código *" size="small" value={form.codigo} onChange={e => set('codigo', e.target.value)} sx={{ flex: 1 }} />
              <TextField label="Nombre *" size="small" value={form.nombre} onChange={e => set('nombre', e.target.value)} sx={{ flex: 2 }} />
            </Stack>
            <TextField label="NIT" fullWidth size="small" value={form.nit} onChange={e => set('nit', e.target.value)} />
            <Stack direction="row" gap={1.5}>
              <TextField label="Contacto" size="small" value={form.contacto} onChange={e => set('contacto', e.target.value)} sx={{ flex: 2 }} />
              <TextField label="Teléfono" size="small" value={form.telefono} onChange={e => set('telefono', e.target.value)} sx={{ flex: 1 }} />
            </Stack>
          </Stack></DialogContent>
          <CrudActions onCancel={() => setOpen(false)} isPending={create.isPending || update.isPending} editing={!!editing} />
        </Box>
      </Dialog>
      <ConfirmDelete open={deleteId !== null} title="Transportadora" onConfirm={() => { if (deleteId) remove.mutate(deleteId, { onSuccess: () => setDeleteId(null) }) }} onCancel={() => setDeleteId(null)} loading={remove.isPending} />
    </SectionShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 9: Devoluciones (read-only list)
// ═══════════════════════════════════════════════════════════════════════════════
interface Devolucion { id: number; numero_devolucion: string; tipo: string; estado: string; motivo?: string; fecha_recepcion?: string }

function DevolucionesListSection() {
  const { data: devoluciones = [], isLoading } = useQuery<Devolucion[]>({
    queryKey: ['wms-devoluciones'],
    queryFn: () => api.get('/wms/devoluciones/').then(r => r.data),
  })

  const TIPO_CFG: Record<string, { color: string; bg: string }> = {
    CLIENTE:   { color: '#1E40AF', bg: '#DBEAFE' },
    PROVEEDOR: { color: '#4338CA', bg: '#E0E7FF' },
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Box>
          <Typography fontSize={14} fontWeight={700}>Devoluciones</Typography>
          <Typography fontSize={12} color="text.secondary">Registro histórico de todas las devoluciones</Typography>
        </Box>
      </Stack>

      {isLoading ? (
        <Box display="flex" justifyContent="center" py={3}><CircularProgress size={24} sx={{ color: WMS_COLOR }} /></Box>
      ) : devoluciones.length === 0 ? (
        <Typography fontSize={13} color="text.secondary" textAlign="center" py={2}>Sin devoluciones registradas</Typography>
      ) : (
        <Stack gap={1.5}>
          {devoluciones.map(d => {
            const cfg = TIPO_CFG[d.tipo] ?? { color: '#374151', bg: '#F3F4F6' }
            return (
              <Paper key={d.id} elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '10px', p: 1.5 }}>
                <Stack direction="row" alignItems="center" gap={1}>
                  <Box flex={1}>
                    <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
                      <Typography fontSize={13} fontWeight={700} fontFamily="monospace">{d.numero_devolucion}</Typography>
                      <Chip label={d.tipo} size="small" sx={{ bgcolor: cfg.bg, color: cfg.color, fontWeight: 700, fontSize: 10, height: 20 }} />
                      <Chip label={d.estado} size="small" sx={{ bgcolor: '#F3F4F6', color: '#374151', fontSize: 10, height: 20 }} />
                    </Stack>
                    {d.motivo && <Typography fontSize={11} color="text.secondary" mt={0.25}>{d.motivo}</Typography>}
                    {d.fecha_recepcion && <Typography fontSize={11} color="text.secondary">Recepción: {d.fecha_recepcion}</Typography>}
                  </Box>
                </Stack>
              </Paper>
            )
          })}
        </Stack>
      )}
    </Box>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Depositantes (operación 3PL)
// ═══════════════════════════════════════════════════════════════════════════════
interface Depositante { id: number; codigo: string; nombre: string; nit?: string; contacto?: string; email?: string
  telefono?: string; propio: boolean; notas?: string; activo: boolean; productos: number; unidades: number
  ubicaciones: number; valor: number }

function DepositantesSection() {
  const qc = useQueryClient()
  const { data: items = [], isLoading } = useQuery<Depositante[]>({ queryKey: ['wms-depositantes'], queryFn: () => api.get('/wms/depositantes').then(r => r.data) })
  const [dlg, setDlg] = useState<{ abierto: boolean; r: Depositante | null }>({ abierto: false, r: null })
  const [portal, setPortal] = useState<Depositante | null>(null)
  const usuariosPortal = useQuery<any[]>({ queryKey: ['wms-portal-usuarios', portal?.id], enabled: !!portal,
    queryFn: () => api.get(`/wms/depositantes/${portal!.id}/usuarios`).then(r => r.data) })
  const usuarios = useQuery<any[]>({ queryKey: ['usuarios-lista'], enabled: !!portal, queryFn: () => api.get('/usuarios/').then(r => r.data) })
  const [nuevoUsuario, setNuevoUsuario] = useState<any | null>(null)
  const vincular = async () => {
    try { await api.post(`/wms/depositantes/${portal!.id}/usuarios`, { usuario_id: nuevoUsuario.id }); setNuevoUsuario(null)
      toast.success('Usuario agregado al portal: al entrar solo verá la mercancía de este cliente'); qc.invalidateQueries({ queryKey: ['wms-portal-usuarios'] })
    } catch (e) { toast.error(mensajeDeError(e, 'No se pudo vincular')) }
  }
  const desvincular = async (uid: number) => {
    try { await api.delete(`/wms/depositantes/${portal!.id}/usuarios/${uid}`); toast.success('Usuario retirado del portal'); qc.invalidateQueries({ queryKey: ['wms-portal-usuarios'] }) }
    catch (e) { toast.error(mensajeDeError(e, 'No se pudo retirar')) }
  }
  const campos: Campo[] = [
    { clave: 'codigo', etiqueta: 'Código', obligatorio: true, ancho: 4 },
    { clave: 'nombre', etiqueta: 'Razón social', obligatorio: true, ancho: 8 },
    { clave: 'nit', etiqueta: 'NIT', ancho: 6 },
    { clave: 'contacto', etiqueta: 'Contacto', ancho: 6 },
    { clave: 'email', etiqueta: 'Correo', ancho: 6 },
    { clave: 'telefono', etiqueta: 'Teléfono', ancho: 6 },
    { clave: 'propio', etiqueta: 'Es la mercancía propia de la empresa', tipo: 'interruptor' },
    { clave: 'notas', etiqueta: 'Condiciones del servicio', tipo: 'area' },
    { clave: 'activo', etiqueta: 'Activo', tipo: 'interruptor' },
  ]
  const guardar = async (c: Record<string, unknown>) => {
    if (dlg.r) await api.put(`/wms/depositantes/${dlg.r.id}`, c); else await api.post('/wms/depositantes', c)
    toast.success('Depositante guardado'); qc.invalidateQueries({ queryKey: ['wms-depositantes'] })
  }
  const pesos = (v: number) => v.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })
  return (
    <Box>
      <Stack direction="row" alignItems="center" gap={2} mb={0.25}>
        <Typography fontSize={14} fontWeight={700}>Depositantes</Typography>
        <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={() => setDlg({ abierto: true, r: null })}
          sx={{ borderRadius: '8px', textTransform: 'none', borderColor: alpha(WMS_COLOR, 0.5), color: WMS_COLOR }}>Nuevo</Button>
      </Stack>
      <Typography fontSize={12} color="text.secondary" mb={2}>
        Dueños de la mercancía almacenada. Cada producto es de un solo depositante y cada documento (orden, recepción, despacho) también:
        así el inventario de un cliente nunca se mezcla con el de otro.
      </Typography>
      <TablaRegistros filas={items} cargando={isLoading} vacio="Sin depositantes" etiqueta={d => d.nombre}
        onEditar={d => setDlg({ abierto: true, r: d })}
        extra={d => d.propio ? null : <Button size="small" onClick={() => setPortal(d)}>Usuarios del portal</Button>}
        columnas={[
          { titulo: 'Código', valor: d => d.codigo },
          { titulo: 'Depositante', valor: d => <>{d.nombre}{d.propio && <Chip size="small" label="Propio" sx={{ ml: 1, height: 18, fontSize: 10 }} />}</> },
          { titulo: 'NIT', valor: d => d.nit ?? '' },
          { titulo: 'Productos', valor: d => d.productos, alinear: 'right' },
          { titulo: 'Unidades en bodega', valor: d => d.unidades.toLocaleString('es-CO'), alinear: 'right' },
          { titulo: 'Ubicaciones', valor: d => d.ubicaciones, alinear: 'right' },
          { titulo: 'Valor al costo', valor: d => pesos(d.valor), alinear: 'right' },
          { titulo: 'Estado', valor: d => d.activo ? 'Activo' : 'Inactivo' },
        ]} />
      <FormularioRegistro abierto={dlg.abierto} titulo={dlg.r ? 'Editar depositante' : 'Nuevo depositante'} campos={campos}
        registro={dlg.r} valoresIniciales={{ activo: true, propio: false }} onGuardar={guardar}
        onCerrar={() => setDlg({ abierto: false, r: null })} />
      <Dialog open={!!portal} onClose={() => setPortal(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Portal de clientes · {portal?.nombre}</DialogTitle>
        <DialogContent>
          <Typography fontSize={13} color="text.secondary" mb={2}>
            Estas personas entran a la plataforma y solo ven el inventario, los movimientos, las órdenes y las facturas de este
            cliente. Créelas en Usuarios (rol Consulta) y agréguelas aquí. Un administrador no puede ser usuario del portal.
          </Typography>
          {(usuariosPortal.data ?? []).map(u => (
            <Stack key={u.id} direction="row" alignItems="center" gap={1} sx={{ py: 0.75, borderBottom: '1px solid #F1F5F9' }}>
              <Box flex={1}><Typography fontSize={13} fontWeight={600}>{u.nombre}</Typography>
                <Typography fontSize={12} color="text.secondary">{u.username} · {u.email}</Typography></Box>
              <Button size="small" color="error" onClick={() => desvincular(u.id)}>Retirar</Button>
            </Stack>
          ))}
          {usuariosPortal.data && !usuariosPortal.data.length && <Typography fontSize={13} mb={1}>Todavía no hay usuarios del portal.</Typography>}
          <Stack direction="row" gap={1} mt={2}>
            <Autocomplete size="small" sx={{ flex: 1 }} options={(usuarios.data ?? []).filter((u: any) => u.rol !== 'ADMINISTRADOR')} value={nuevoUsuario}
              onChange={(_, v) => setNuevoUsuario(v)} getOptionLabel={(u: any) => `${u.nombre} ${u.apellido} (${u.username})`}
              renderInput={pr => <TextField {...pr} label="Agregar usuario" />} />
            <Button disabled={!nuevoUsuario} onClick={vincular}>Agregar</Button>
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setPortal(null)}>Cerrar</Button></DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Shared helper components ──────────────────────────────────────────────────

// ─── Estados de la orden de compra (configurables) ────────────────────────────
function EstadosOCSection() {
  const qc = useQueryClient()
  const { estados, roles, isLoading } = useEstadosOC()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<EstadoOC | null>(null)
  const VACIO = { nombre: '', codigo: '', color: '#4F46E5', orden: '100', rol: '', activo: true }
  const [form, setForm] = useState(VACIO)
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['wms-estados-oc'] }); qc.invalidateQueries({ queryKey: ['wms-ordenes-compra'] }) }

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = { ...form, orden: Number(form.orden) || 0, rol: form.rol || null, codigo: form.codigo || null }
      return editing ? api.put(`/wms/estados-oc/${editing.id}`, cuerpo) : api.post('/wms/estados-oc', cuerpo)
    },
    onSuccess: () => { toast.success(editing ? 'Estado actualizado' : 'Estado creado'); refrescar(); setOpen(false) },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo guardar el estado')),
  })
  const eliminar = useMutation({
    mutationFn: (id: number) => api.delete(`/wms/estados-oc/${id}`),
    onSuccess: () => { toast.success('Estado eliminado'); refrescar() },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo eliminar')),
  })
  const abrir = (e?: EstadoOC) => {
    setEditing(e ?? null)
    setForm(e ? { nombre: e.nombre, codigo: e.codigo, color: e.color, orden: String(e.orden), rol: e.rol ?? '', activo: e.activo } : VACIO)
    setOpen(true)
  }

  return (
    <SectionShell title="Estados de la orden de compra"
      subtitle="Nombre, color y orden de cada estado. El rol indica cuándo el sistema mueve la orden a ese estado; los estados sin rol se asignan a mano."
      onNew={() => abrir()} isLoading={isLoading}>
      {estados.map(e => (
        <Paper key={e.id} elevation={0} sx={{ p: 1.5, border: '1px solid #E5E7EB', borderRadius: 2, opacity: e.activo ? 1 : 0.55 }}>
          <Stack direction="row" alignItems="center" gap={1.5}>
            <Box sx={{ width: 14, height: 14, borderRadius: '50%', bgcolor: e.color, flexShrink: 0 }} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography fontWeight={700} fontSize={14}>{e.nombre}
                <Typography component="span" fontSize={11.5} color="text.secondary" sx={{ ml: 1, fontFamily: 'monospace' }}>{e.codigo}</Typography>
              </Typography>
              <Typography fontSize={12} color="text.secondary">
                {e.rol ? `Automático · ${e.rol_descripcion}` : 'Manual'}{e.usos ? ` · ${e.usos} orden(es)` : ''}{!e.activo ? ' · inactivo' : ''}
              </Typography>
            </Box>
            {e.obligatorio && <Chip size="small" label="Requerido por el sistema" sx={{ fontSize: 10.5 }} />}
            <IconButton size="small" onClick={() => abrir(e)}><EditIcon fontSize="small" /></IconButton>
            <IconButton size="small" disabled={e.obligatorio || e.usos > 0} onClick={() => eliminar.mutate(e.id)}><DeleteIcon fontSize="small" /></IconButton>
          </Stack>
        </Paper>
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 15 }}>{editing ? 'Editar estado' : 'Nuevo estado'}</DialogTitle>
        <DialogContent><Stack gap={1.5} pt={0.5}>
          <TextField label="Nombre *" size="small" fullWidth value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} />
          <TextField label="Código" size="small" fullWidth value={form.codigo} disabled={!!editing}
            helperText={editing ? 'El código no se cambia: es lo que guardan las órdenes' : 'Vacío = se toma del nombre'}
            onChange={e => setForm(f => ({ ...f, codigo: e.target.value.toUpperCase() }))} />
          <Stack direction="row" gap={1.5}>
            <TextField label="Color" size="small" type="color" value={form.color} sx={{ width: 110 }}
              onChange={e => setForm(f => ({ ...f, color: e.target.value }))} />
            <TextField label="Orden" size="small" type="number" value={form.orden} sx={{ flex: 1 }}
              onChange={e => setForm(f => ({ ...f, orden: e.target.value }))} />
          </Stack>
          <TextField select label="Rol (cuándo lo asigna el sistema)" size="small" fullWidth value={form.rol}
            disabled={!!editing?.obligatorio}
            helperText={editing?.obligatorio ? 'Para mover este rol, asígnelo a otro estado' : 'Si el rol ya lo tiene otro estado, pasa a este'}
            onChange={e => setForm(f => ({ ...f, rol: String(e.target.value) }))}>
            <MenuItem value="">Ninguno (estado manual)</MenuItem>
            {roles.map(r => <MenuItem key={r.rol} value={r.rol}>{r.descripcion}</MenuItem>)}
          </TextField>
          {editing && (
            <FormControlLabel label="Activo" disabled={editing.obligatorio}
              control={<Switch checked={form.activo} onChange={e => setForm(f => ({ ...f, activo: e.target.checked }))} />} />
          )}
        </Stack></DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" disabled={form.nombre.trim().length < 2 || guardar.isPending} onClick={() => guardar.mutate()}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </SectionShell>
  )
}

function SectionShell({ title, subtitle, onNew, isLoading, children }: { title: string; subtitle: string; onNew: () => void; isLoading: boolean; children: React.ReactNode }) {
  return (
    <Box>
      <Box mb={2.5}>
        <Stack direction="row" alignItems="center" gap={2} mb={0.25}>
          <Typography fontSize={14} fontWeight={700}>{title}</Typography>
          <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={onNew}
            sx={{ borderRadius: '8px', textTransform: 'none', borderColor: alpha(WMS_COLOR, 0.5), color: WMS_COLOR, flexShrink: 0 }}>
            Nuevo
          </Button>
        </Stack>
        <Typography fontSize={12} color="text.secondary">{subtitle}</Typography>
      </Box>
      {isLoading ? (
        <Box display="flex" justifyContent="center" py={3}><CircularProgress size={24} sx={{ color: WMS_COLOR }} /></Box>
      ) : (
        <Stack gap={1.5}>{children}</Stack>
      )}
    </Box>
  )
}

function CrudActions({ onCancel, isPending, editing }: { onCancel: () => void; isPending: boolean; editing: boolean }) {
  return (
    <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
      <Button size="small" onClick={onCancel} sx={{ textTransform: 'none' }}>Cancelar</Button>
      <Button type="submit" size="small" variant="contained" disabled={isPending}
        startIcon={isPending ? <CircularProgress size={12} color="inherit" /> : undefined}
        sx={{ textTransform: 'none', bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1E3A8A' } }}>
        {editing ? 'Guardar' : 'Crear'}
      </Button>
    </DialogActions>
  )
}

// ─── Main page ─────────────────────────────────────────────────────────────────
export default function WMSConfig() {
  const [tab, setTab] = useState(() => new URLSearchParams(window.location.search).get('tab') === 'integraciones' ? 20 : 0)

  const tabs = [
    'Países', 'Ciudades', 'Tipos Zona', 'Tipos Ubic.', 'Unidades', 'Categorías', 'Familias',
    'Almacenes', 'Zonas', 'Ubicaciones', 'Productos', 'Lotes',
    'Proveedores', 'Clientes', 'Transportadoras', 'Devoluciones', 'Motivos Res./Bloq.', 'Catálogos', 'Depositantes', 'Estados de OC', 'Integraciones (tiendas virtuales)']

  const GUIDE = [
    { step: '1', text: 'Configura Países y Ciudades — se usan en almacenes, proveedores y clientes.' },
    { step: '2', text: 'Crea Tipos de Zona (Recepción, Almacenamiento...) y Tipos de Ubicación (Pallet, Suelo...).' },
    { step: '3', text: 'Define Unidades de Medida, Categorías y Familias para el catálogo de productos.' },
    { step: '4', text: 'Crea los Almacenes físicos seleccionando país y ciudad del catálogo.' },
    { step: '5', text: 'Divide cada almacén en Zonas usando los tipos pre-configurados.' },
    { step: '6', text: 'Define Ubicaciones (pasillos, estanterías, niveles) dentro de cada zona.' },
    { step: '7', text: 'Si guarda mercancía de terceros, cree los Depositantes; luego registre los Productos con su dueño, SKU, categoría y unidad.' },
    { step: '8', text: 'Los Lotes permiten rastrear mercancía por fecha de vencimiento y origen.' },
    { step: '9', text: 'Registra Proveedores y Clientes con ciudad y país del catálogo.' },
  ]

  return (
    <Layout title="WMS — Configuración">
      <Box mb={3}>
        <Typography fontSize={22} fontWeight={800} color="text.primary" letterSpacing="-0.03em">
          Configuración WMS
        </Typography>
        <Typography fontSize={13} color="text.secondary" mt={0.25}>
          Catálogos y parámetros del módulo de gestión de almacenes
        </Typography>
      </Box>

      <Tabs
        value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto"
        sx={{ mb: 3, borderBottom: '1px solid #E5E7EB', '& .MuiTabs-indicator': { bgcolor: WMS_COLOR } }}
      >
        {tabs.map((label, i) => (
          <Tab key={i} label={label}
            sx={{ textTransform: 'none', fontWeight: 600, fontSize: 13, '&.Mui-selected': { color: WMS_COLOR } }} />
        ))}
      </Tabs>

        {tab === 17 && <AdminCatalogos modulo="WMS" color={COLOR_MODULO} />}
        {tab === 20 && <GestionCanales />}

      {tab !== 20 && <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 8 }}>
          {tab === 0  && <PaisesSection />}
          {tab === 1  && <CiudadesSection />}
          {tab === 2  && <TiposZonaSection />}
          {tab === 3  && <TiposUbicacionSection />}
          {tab === 4  && <UnidadesMedidaSection />}
          {tab === 5  && <CategoriasSection />}
          {tab === 6  && <FamiliasSection />}
          {tab === 7  && <AlmacenesSection />}
          {tab === 8  && <ZonasSection />}
          {tab === 9  && <UbicacionesSection />}
          {tab === 10 && <ProductosSection />}
          {tab === 11 && <LotesSection />}
          {tab === 12 && <ProveedoresWMSSection />}
          {tab === 13 && <ClientesWMSSection />}
          {tab === 14 && <TransportadorasSection />}
          {tab === 15 && <DevolucionesListSection />}
          {tab === 16 && <MotivosMovimientoSection />}
          {tab === 18 && <DepositantesSection />}
          {tab === 19 && <EstadosOCSection />}
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          <Paper elevation={0} sx={{ border: `1px solid ${alpha(WMS_COLOR, 0.2)}`, borderRadius: '14px', p: 2.5, bgcolor: alpha(WMS_COLOR, 0.03) }}>
            <Typography fontSize={13} fontWeight={700} color={WMS_COLOR} mb={1}>
              Guia de configuracion
            </Typography>
            <Stack gap={1}>
              {GUIDE.map(g => (
                <Stack key={g.step} direction="row" gap={1} alignItems="flex-start">
                  <Box sx={{ width: 18, height: 18, borderRadius: '50%', bgcolor: WMS_COLOR, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, mt: 0.1 }}>
                    <Typography fontSize={10} color="#FFF" fontWeight={700}>{g.step}</Typography>
                  </Box>
                  <Typography fontSize={12} color="text.secondary">{g.text}</Typography>
                </Stack>
              ))}
            </Stack>
          </Paper>
        </Grid>
      </Grid>}
    </Layout>
  )
}
