import React, { useState } from 'react'
import {
  Box, Card, CardContent, Typography, Button, Chip, CircularProgress,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  FormControlLabel, Checkbox, Table, TableBody, TableCell, TableHead, TableRow,
  IconButton, Tooltip, alpha, Divider, Tab, Tabs, Switch,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  Add, Edit, Delete, AdminPanelSettings, Check, Close, Group,
  Inventory2, LocalShipping, DirectionsCar, Build, Warehouse, People,
  Route, Description, VerifiedUser, Policy, School, Business,
  Construction, PrecisionManufacturing, BarChart, MonetizationOn, Remove,
  Security, EventAvailable, PointOfSale,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'

const PRIMARY = '#1A1A1A'

/* ─── Definición de grupos de módulos ────────────────────────────────────── */

interface PermDef { key: string; label: string }
interface ModuleGroup {
  key: string; label: string; abbr: string; color: string
  Icon: React.ElementType
  perms: PermDef[]
}

// Permisos de Daily Logistics: los tres módulos operativos y la configuración.
const MODULE_GROUPS: ModuleGroup[] = [
  {
    key: 'wms', label: 'Almacén WMS', abbr: 'WMS', color: '#4F46E5',
    Icon: Warehouse,
    perms: [{ key: 'wms', label: 'Almacén: recepción, inventario, salida y configuración' }],
  },
  {
    key: 'tms', label: 'Transporte TMS', abbr: 'TMS', color: '#0891B2',
    Icon: Route,
    perms: [{ key: 'tms', label: 'Transporte: viajes, flota, conductores, fletes y configuración' }],
  },
  {
    key: 'pos', label: 'Punto de Venta', abbr: 'POS', color: '#7C3AED',
    Icon: PointOfSale,
    perms: [{ key: 'pos', label: 'Punto de venta: caja, turnos, ventas y configuración' }],
  },
  {
    key: 'config', label: 'Configuración', abbr: 'CFG', color: '#B91C1C',
    Icon: AdminPanelSettings,
    perms: [
      { key: 'usuarios', label: 'Usuarios y roles' },
      { key: 'configuracion', label: 'Configuración general: empresa y catálogos' },
    ],
  },
]

const ALL_PERM_KEYS = MODULE_GROUPS.flatMap(g => g.perms.map(p => p.key))
const DEFAULT_PERMISOS = Object.fromEntries(ALL_PERM_KEYS.map(k => [k, false]))

const countEnabled = (perms: Record<string, boolean>, group: ModuleGroup) =>
  group.perms.filter(p => perms?.[p.key]).length

const PRESET_COLORS = [
  '#DC2626', '#D97706', '#2563EB', '#7C3AED', '#6B7280',
  '#1A1A1A', '#0891B2', '#DB2777', '#EA580C', '#4F46E5',
]

const emptyForm = {
  nombre: '', label: '', descripcion: '', color: '#4F46E5',
  permisos: { ...DEFAULT_PERMISOS },
}

/* ─── Dialog permisos ─────────────────────────────────────────────────────── */

interface RolDialogProps {
  open: boolean; title: string; form: any; setForm: (f: any) => void
  onClose: () => void; onSave: () => void; loading: boolean
  esNuevo: boolean; esSistema?: boolean
}

function RolDialog({ open, title, form, setForm, onClose, onSave, loading, esNuevo, esSistema }: RolDialogProps) {
  const [tab, setTab] = useState(0)
  const perms: Record<string, boolean> = { ...DEFAULT_PERMISOS, ...(form.permisos || {}) }

  const togglePerm = (key: string) =>
    setForm({ ...form, permisos: { ...perms, [key]: !perms[key] } })

  const toggleGroup = (group: ModuleGroup, value: boolean) => {
    const next = { ...perms }
    group.perms.forEach(p => { next[p.key] = value })
    setForm({ ...form, permisos: next })
  }

  const toggleAll = (value: boolean) =>
    setForm({ ...form, permisos: Object.fromEntries(ALL_PERM_KEYS.map(k => [k, value])) })

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth
      PaperProps={{ sx: { borderRadius: '12px' } }}>
      <DialogTitle sx={{ fontWeight: 700, pb: 0 }}>{title}</DialogTitle>
      <Box sx={{ px: 3 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}
          sx={{ borderBottom: '1px solid #E2E8F0', '& .MuiTab-root': { fontSize: 13, minWidth: 0 }, '& .MuiTabs-indicator': { bgcolor: PRIMARY } }}>
          <Tab label="Datos básicos" />
          <Tab label="Permisos del sistema" />
        </Tabs>
      </Box>

      <DialogContent sx={{ pt: 2 }}>
        {/* ── Tab 0: Datos básicos ── */}
        {tab === 0 && (
          <Grid container spacing={2}>
            {!esSistema && (
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth size="small" label="Nombre interno (sin espacios)"
                  value={form.nombre || ''}
                  onChange={e => setForm({ ...form, nombre: e.target.value })}
                  helperText="Se guardará en mayúsculas. Ej: JEFE_BODEGA"
                  disabled={!esNuevo && esSistema} />
              </Grid>
            )}
            <Grid size={{ xs: 12, sm: esSistema ? 12 : 6 }}>
              <TextField fullWidth size="small" label="Etiqueta visible"
                value={form.label || ''}
                onChange={e => setForm({ ...form, label: e.target.value })}
                helperText="Nombre que verán los usuarios" />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField fullWidth size="small" label="Descripción" multiline rows={2}
                value={form.descripcion || ''}
                onChange={e => setForm({ ...form, descripcion: e.target.value })} />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Typography sx={{ fontSize: 12, fontWeight: 600, color: '#64748B', mb: 1 }}>
                Color identificador
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                {PRESET_COLORS.map(c => (
                  <Box key={c} onClick={() => setForm({ ...form, color: c })}
                    sx={{ width: 28, height: 28, borderRadius: '50%', bgcolor: c, cursor: 'pointer',
                      border: form.color === c ? '3px solid #1E293B' : '2px solid transparent',
                      boxShadow: form.color === c ? `0 0 0 2px white, 0 0 0 4px ${c}` : 'none',
                      transition: 'box-shadow 0.15s' }} />
                ))}
                <Box sx={{ width: 28, height: 28, borderRadius: '50%',
                  background: 'linear-gradient(135deg, #f00, #0f0, #00f)',
                  cursor: 'pointer', position: 'relative', overflow: 'hidden' }}>
                  <input type="color" value={form.color || '#4F46E5'}
                    onChange={e => setForm({ ...form, color: e.target.value })}
                    style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' }} />
                </Box>
                <Box sx={{ width: 28, height: 28, borderRadius: '50%', bgcolor: form.color, border: '2px solid #E2E8F0' }} />
              </Box>
            </Grid>
          </Grid>
        )}

        {/* ── Tab 1: Permisos ── */}
        {tab === 1 && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
              <Typography sx={{ fontSize: 13, color: '#64748B' }}>
                {ALL_PERM_KEYS.filter(k => perms[k]).length} de {ALL_PERM_KEYS.length} permisos activos
              </Typography>
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button size="small" onClick={() => toggleAll(true)} sx={{ fontSize: 11, color: PRIMARY }}>
                  Activar todos
                </Button>
                <Button size="small" onClick={() => toggleAll(false)} sx={{ fontSize: 11, color: '#94A3B8' }}>
                  Desactivar todos
                </Button>
              </Box>
            </Box>

            <Box sx={{ maxHeight: 440, overflowY: 'auto', pr: 0.5 }}>
              {MODULE_GROUPS.map(group => {
                const enabled = countEnabled(perms, group)
                const total   = group.perms.length
                const allOn   = enabled === total
                const isMulti = total > 1
                return (
                  <Box key={group.key} sx={{ mb: 1.5, border: '1px solid #E2E8F0', borderRadius: '8px', overflow: 'hidden' }}>
                    {/* Group header */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, py: 1,
                      bgcolor: enabled > 0 ? alpha(group.color, 0.06) : '#FAFAFA',
                      borderBottom: isMulti && enabled > 0 ? '1px solid #E2E8F0' : 'none' }}>
                      <Box sx={{ width: 32, height: 32, borderRadius: '8px',
                        bgcolor: alpha(group.color, 0.12), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <group.Icon sx={{ fontSize: 16, color: group.color }} />
                      </Box>
                      <Box sx={{ flex: 1 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography sx={{ fontWeight: 700, fontSize: 13 }}>{group.label}</Typography>
                          <Chip label={group.abbr} size="small"
                            sx={{ fontSize: 9, height: 17, bgcolor: alpha(group.color, 0.12), color: group.color, fontWeight: 700 }} />
                          {isMulti && (
                            <Chip label={`${enabled}/${total}`} size="small"
                              sx={{ fontSize: 9, height: 17,
                                bgcolor: allOn ? alpha(group.color, 0.12) : enabled > 0 ? '#FEF9C3' : '#F1F5F9',
                                color: allOn ? group.color : enabled > 0 ? '#92400E' : '#94A3B8',
                                fontWeight: 700 }} />
                          )}
                        </Box>
                      </Box>
                      {isMulti ? (
                        <Box sx={{ display: 'flex', gap: 0.75 }}>
                          <Button size="small" onClick={() => toggleGroup(group, true)}
                            sx={{ fontSize: 10, py: 0.25, px: 1, color: group.color, minWidth: 0,
                              bgcolor: alpha(group.color, 0.08), '&:hover': { bgcolor: alpha(group.color, 0.16) } }}>
                            Todo
                          </Button>
                          <Button size="small" onClick={() => toggleGroup(group, false)}
                            sx={{ fontSize: 10, py: 0.25, px: 1, color: '#94A3B8', minWidth: 0 }}>
                            Ninguno
                          </Button>
                        </Box>
                      ) : (
                        <Switch
                          size="small"
                          checked={!!perms[group.perms[0].key]}
                          onChange={() => togglePerm(group.perms[0].key)}
                          sx={{ '& .MuiSwitch-switchBase.Mui-checked': { color: group.color },
                            '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { bgcolor: group.color } }}
                        />
                      )}
                    </Box>

                    {/* Multi-perm group: show individual checkboxes */}
                    {isMulti && (
                      <Box sx={{ px: 2, py: 1 }}>
                        <Grid container>
                          {group.perms.map(p => (
                            <Grid size={{ xs: 6, sm: 4, md: 3 }} key={p.key}>
                              <FormControlLabel
                                control={
                                  <Checkbox size="small" checked={!!perms[p.key]}
                                    onChange={() => togglePerm(p.key)}
                                    sx={{ color: '#CBD5E1', '&.Mui-checked': { color: group.color }, p: 0.5 }} />
                                }
                                label={<Typography sx={{ fontSize: 12 }}>{p.label}</Typography>}
                                sx={{ m: 0, py: 0.25 }}
                              />
                            </Grid>
                          ))}
                        </Grid>
                      </Box>
                    )}
                  </Box>
                )
              })}
            </Box>
          </Box>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2, pt: 1 }}>
        <Button onClick={onClose} sx={{ color: '#64748B' }}>Cancelar</Button>
        <Button variant="contained" disabled={loading} onClick={onSave}
          sx={{ bgcolor: PRIMARY, '&:hover': { bgcolor: '#1A1A1A' } }}>
          {loading ? 'Guardando...' : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

/* ─── Componente principal ───────────────────────────────────────────────── */

export default function Roles() {
  const queryClient = useQueryClient()
  const [mainTab, setMainTab]     = useState(0)
  const [openCreate, setOpenCreate] = useState(false)
  const [openEdit, setOpenEdit]   = useState<any>(null)
  const [openDelete, setOpenDelete] = useState<any>(null)
  const [form, setForm]           = useState<any>(emptyForm)

  const { data: roles = [], isLoading } = useQuery({
    queryKey: ['roles'],
    queryFn: () => apiClient.get('/roles/').then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (body: any) => apiClient.post('/roles/', body).then(r => r.data),
    onSuccess: () => {
      toast.success('Rol creado exitosamente')
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setOpenCreate(false); setForm(emptyForm)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al crear el rol'),
  })

  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: any }) =>
      apiClient.put(`/roles/${id}`, body).then(r => r.data),
    onSuccess: () => {
      toast.success('Rol actualizado')
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setOpenEdit(null)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al actualizar el rol'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/roles/${id}`),
    onSuccess: () => {
      toast.success('Rol eliminado')
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setOpenDelete(null)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al eliminar el rol'),
  })

  const openEditDialog = (rol: any) =>
    setOpenEdit({ ...rol, permisos: { ...DEFAULT_PERMISOS, ...(rol.permisos || {}) } })

  const handleCreate = () => {
    if (!form.nombre?.trim()) { toast.error('El nombre interno del rol es obligatorio'); return }
    createMutation.mutate({
      nombre: form.nombre, label: form.label || form.nombre,
      descripcion: form.descripcion, color: form.color, permisos: form.permisos,
    })
  }

  const handleEdit = () => {
    if (!openEdit) return
    editMutation.mutate({
      id: openEdit.id,
      body: {
        nombre: openEdit.es_sistema ? undefined : openEdit.nombre,
        label: openEdit.label, descripcion: openEdit.descripcion,
        color: openEdit.color, permisos: openEdit.permisos,
      },
    })
  }

  if (isLoading) {
    return (
      <Layout title="Roles y Permisos">
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
          <CircularProgress sx={{ color: PRIMARY }} />
        </Box>
      </Layout>
    )
  }

  return (
    <Layout title="Roles y Permisos">
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="body2" sx={{ color: '#64748B' }}>
          Gestión de roles y permisos de acceso por módulo del sistema
        </Typography>
        <Button variant="contained" startIcon={<Add />}
          onClick={() => { setForm({ ...emptyForm, permisos: { ...DEFAULT_PERMISOS } }); setOpenCreate(true) }}
          sx={{ bgcolor: PRIMARY, '&:hover': { bgcolor: '#1A1A1A' } }}>
          Nuevo Rol
        </Button>
      </Box>

      {/* Tabs principales */}
      <Tabs value={mainTab} onChange={(_, v) => setMainTab(v)}
        sx={{ mb: 2.5, borderBottom: '1px solid #E2E8F0',
          '& .MuiTab-root': { fontSize: 13 }, '& .MuiTabs-indicator': { bgcolor: PRIMARY } }}>
        <Tab label="Roles del sistema" />
        <Tab label="Matriz de permisos" />
      </Tabs>

      {/* ── Tab 0: Cards de roles ── */}
      {mainTab === 0 && (
        <Grid container spacing={2}>
          {roles.map((rol: any) => {
            const totalActivos = ALL_PERM_KEYS.filter(k => rol.permisos?.[k]).length
            return (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={rol.id}>
                <Card sx={{ borderRadius: '12px', border: `1px solid ${alpha(rol.color || '#6B7280', 0.2)}`,
                  borderTop: `4px solid ${rol.color || '#6B7280'}`, height: '100%' }}>
                  <CardContent sx={{ p: '20px !important' }}>
                    {/* Header del card */}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <AdminPanelSettings sx={{ color: rol.color || '#6B7280', fontSize: 20 }} />
                        <Typography sx={{ fontWeight: 700, fontSize: 14 }}>{rol.label || rol.nombre}</Typography>
                        {rol.es_sistema && (
                          <Chip label="Sistema" size="small"
                            sx={{ fontSize: 9, height: 16, bgcolor: alpha(rol.color || '#6B7280', 0.1), color: rol.color || '#6B7280' }} />
                        )}
                      </Box>
                      <Box sx={{ display: 'flex', gap: 0.5 }}>
                        <Tooltip title="Editar permisos">
                          <IconButton size="small" onClick={() => openEditDialog(rol)} sx={{ color: '#64748B' }}>
                            <Edit sx={{ fontSize: 16 }} />
                          </IconButton>
                        </Tooltip>
                        {!rol.es_sistema && (
                          <Tooltip title="Eliminar rol">
                            <IconButton size="small" onClick={() => setOpenDelete(rol)}
                              sx={{ color: '#94A3B8', '&:hover': { color: '#EF4444', bgcolor: alpha('#EF4444', 0.06) } }}>
                              <Delete sx={{ fontSize: 16 }} />
                            </IconButton>
                          </Tooltip>
                        )}
                      </Box>
                    </Box>

                    <Typography sx={{ fontSize: 12, color: '#64748B', mb: 1.5, minHeight: 36, lineHeight: 1.5 }}>
                      {rol.descripcion || '—'}
                    </Typography>

                    {/* Módulos con acceso */}
                    <Box sx={{ mb: 1.5 }}>
                      <Typography sx={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em', mb: 0.75 }}>
                        Módulos con acceso
                      </Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {MODULE_GROUPS.filter(g => countEnabled(rol.permisos || {}, g) > 0).slice(0, 8).map(g => (
                          <Tooltip key={g.key}
                            title={g.perms.length > 1
                              ? `${countEnabled(rol.permisos || {}, g)}/${g.perms.length} secciones`
                              : g.label}>
                            <Chip
                              label={g.abbr} size="small"
                              icon={<g.Icon sx={{ fontSize: '12px !important', color: `${g.color} !important` }} />}
                              sx={{ fontSize: 9, height: 20, bgcolor: alpha(g.color, 0.1), color: g.color, fontWeight: 700,
                                '& .MuiChip-icon': { ml: '4px' } }} />
                          </Tooltip>
                        ))}
                        {MODULE_GROUPS.filter(g => countEnabled(rol.permisos || {}, g) > 0).length > 8 && (
                          <Chip label={`+${MODULE_GROUPS.filter(g => countEnabled(rol.permisos || {}, g) > 0).length - 8}`}
                            size="small" sx={{ fontSize: 9, height: 20, bgcolor: '#F1F5F9', color: '#64748B', fontWeight: 700 }} />
                        )}
                        {MODULE_GROUPS.filter(g => countEnabled(rol.permisos || {}, g) > 0).length === 0 && (
                          <Typography sx={{ fontSize: 11, color: '#CBD5E1', fontStyle: 'italic' }}>Sin permisos asignados</Typography>
                        )}
                      </Box>
                    </Box>

                    <Divider sx={{ my: 1.5 }} />

                    {/* Footer del card */}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography sx={{ fontSize: 11, color: '#94A3B8' }}>
                        <strong style={{ color: '#64748B' }}>{totalActivos}</strong> de {ALL_PERM_KEYS.length} permisos activos
                      </Typography>
                      <Tooltip title={`${rol.total_usuarios} usuario(s) con este rol`}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, cursor: 'default' }}>
                          <Group sx={{ fontSize: 13, color: '#94A3B8' }} />
                          <Typography sx={{ fontSize: 11, color: '#94A3B8', fontWeight: 700 }}>
                            {rol.total_usuarios}
                          </Typography>
                        </Box>
                      </Tooltip>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            )
          })}
        </Grid>
      )}

      {/* ── Tab 1: Matriz de permisos ── */}
      {mainTab === 1 && (
        <Card sx={{ borderRadius: '12px' }}>
          <Box sx={{ p: 2, borderBottom: '1px solid #E2E8F0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography sx={{ fontWeight: 700, fontSize: 14 }}>Matriz de permisos — módulos × roles</Typography>
            <Typography sx={{ fontSize: 12, color: '#94A3B8' }}>
              {MODULE_GROUPS.length} módulos · {roles.length} roles
            </Typography>
          </Box>
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: '#F8FAFC' }}>
                  <TableCell sx={{ fontWeight: 700, minWidth: 220, fontSize: 12, borderRight: '1px solid #E2E8F0' }}>
                    Módulo del Sistema
                  </TableCell>
                  {roles.map((rol: any) => (
                    <TableCell key={rol.id} align="center"
                      sx={{ fontWeight: 700, minWidth: 120, borderRight: '1px solid #F1F5F9' }}>
                      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: rol.color || '#6B7280' }} />
                        <Typography sx={{ fontSize: 11, fontWeight: 700, color: rol.color || '#6B7280', lineHeight: 1.2 }}>
                          {rol.label || rol.nombre}
                        </Typography>
                      </Box>
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {MODULE_GROUPS.map((group, idx) => (
                  <TableRow key={group.key}
                    sx={{ bgcolor: idx % 2 === 0 ? '#FFF' : '#FAFAFA',
                      '&:hover': { bgcolor: alpha(group.color, 0.03) } }}>
                    {/* Módulo header */}
                    <TableCell sx={{ borderRight: '1px solid #E2E8F0', py: 1.25 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                        <Box sx={{ width: 28, height: 28, borderRadius: '6px',
                          bgcolor: alpha(group.color, 0.12), display: 'flex', alignItems: 'center', justifyContent: 'center',
                          flexShrink: 0 }}>
                          <group.Icon sx={{ fontSize: 14, color: group.color }} />
                        </Box>
                        <Box>
                          <Typography sx={{ fontSize: 12, fontWeight: 700, lineHeight: 1.2 }}>{group.label}</Typography>
                          {group.perms.length > 1 && (
                            <Typography sx={{ fontSize: 10, color: '#94A3B8' }}>{group.perms.length} secciones</Typography>
                          )}
                        </Box>
                        <Chip label={group.abbr} size="small"
                          sx={{ fontSize: 9, height: 16, bgcolor: alpha(group.color, 0.1), color: group.color, fontWeight: 700 }} />
                      </Box>
                    </TableCell>

                    {/* Celdas por rol */}
                    {roles.map((rol: any) => {
                      const en  = countEnabled(rol.permisos || {}, group)
                      const tot = group.perms.length
                      const pct = tot > 0 ? en / tot : 0
                      return (
                        <TableCell key={rol.id} align="center"
                          sx={{ borderRight: '1px solid #F1F5F9', py: 1 }}>
                          {en === 0 ? (
                            <Remove sx={{ color: '#E2E8F0', fontSize: 16 }} />
                          ) : en === tot ? (
                            <Box sx={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              width: 22, height: 22, borderRadius: '50%', bgcolor: alpha(group.color, 0.12) }}>
                              <Check sx={{ color: group.color, fontSize: 14 }} />
                            </Box>
                          ) : (
                            <Tooltip title={`${en} de ${tot} secciones habilitadas`}>
                              <Chip label={`${en}/${tot}`} size="small"
                                sx={{ fontSize: 9, height: 18, fontWeight: 700,
                                  bgcolor: alpha('#F59E0B', 0.12), color: '#D97706',
                                  cursor: 'default' }} />
                            </Tooltip>
                          )}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>

          {/* Leyenda */}
          <Box sx={{ p: 2, borderTop: '1px solid #E2E8F0', display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            {[
              { icon: <Check sx={{ color: PRIMARY, fontSize: 14 }} />, bg: alpha(PRIMARY, 0.1), label: 'Acceso total al módulo' },
              { icon: <Typography sx={{ fontSize: 9, fontWeight: 700, color: '#D97706' }}>N/T</Typography>, bg: alpha('#F59E0B', 0.1), label: 'Acceso parcial (algunas secciones)' },
              { icon: <Remove sx={{ color: '#CBD5E1', fontSize: 14 }} />, bg: 'transparent', label: 'Sin acceso' },
            ].map((l, i) => (
              <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Box sx={{ width: 22, height: 22, borderRadius: '50%', bgcolor: l.bg,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #E2E8F0' }}>
                  {l.icon}
                </Box>
                <Typography sx={{ fontSize: 11, color: '#64748B' }}>{l.label}</Typography>
              </Box>
            ))}
          </Box>
        </Card>
      )}

      {/* ── Dialog Crear ── */}
      <RolDialog
        open={openCreate} title="Nuevo Rol"
        form={form} setForm={setForm}
        onClose={() => setOpenCreate(false)} onSave={handleCreate}
        loading={createMutation.isPending} esNuevo />

      {/* ── Dialog Editar ── */}
      {openEdit && (
        <RolDialog
          open={!!openEdit} title={`Editar: ${openEdit.label || openEdit.nombre}`}
          form={openEdit} setForm={setOpenEdit}
          onClose={() => setOpenEdit(null)} onSave={handleEdit}
          loading={editMutation.isPending} esNuevo={false} esSistema={openEdit.es_sistema} />
      )}

      {/* ── Dialog Eliminar ── */}
      <Dialog open={!!openDelete} onClose={() => setOpenDelete(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Eliminar Rol</DialogTitle>
        <DialogContent>
          <Typography sx={{ fontSize: 13 }}>
            ¿Seguro que deseas eliminar el rol{' '}
            <strong>{openDelete?.label || openDelete?.nombre}</strong>?
            Esta acción no se puede deshacer.
          </Typography>
          {openDelete?.total_usuarios > 0 && (
            <Box sx={{ mt: 1.5, p: 1.5, bgcolor: alpha('#EF4444', 0.06),
              borderRadius: '8px', border: `1px solid ${alpha('#EF4444', 0.2)}` }}>
              <Typography sx={{ fontSize: 12, color: '#EF4444', fontWeight: 600 }}>
                ⚠ {openDelete.total_usuarios} usuario(s) tienen este rol. El servidor rechazará la eliminación.
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenDelete(null)}>Cancelar</Button>
          <Button variant="contained" color="error" disabled={deleteMutation.isPending}
            onClick={() => deleteMutation.mutate(openDelete.id)}>
            {deleteMutation.isPending ? 'Eliminando...' : 'Eliminar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
