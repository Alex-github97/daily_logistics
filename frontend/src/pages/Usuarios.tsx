import React, { useState } from 'react'
import {
  Box, Card, Typography, Button, Table, TableBody, TableCell, TableHead, TableRow, Chip, Skeleton, Dialog, DialogTitle, DialogContent, DialogActions, InputLabel, MenuItem, Avatar, alpha, IconButton, Tooltip,
} from '@mui/material'
import { TextField, FormControl, Select } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Add, Edit, Lock, Close, AdminPanelSettings } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'

import { mensajeDeError } from '@/utils/errorApi'
const PRIMARY = '#1A1A1A'

const getInitials = (nombre: string, apellido: string) =>
  `${nombre?.[0] ?? ''}${apellido?.[0] ?? ''}`.toUpperCase()

const emptyForm = {
  nombre: '', apellido: '', email: '', username: '', password: '', rol: 'CONSULTA',
  telefono: '', cargo: '',
}

export default function Usuarios() {
  const navigate = useNavigate()
  const currentUser = useAuthStore(s => s.user)
  const queryClient = useQueryClient()

  const [openCreate, setOpenCreate] = useState(false)
  const [openEdit, setOpenEdit] = useState(false)
  const [openPwd, setOpenPwd] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [form, setForm] = useState(emptyForm)
  const [editForm, setEditForm] = useState<any>({})
  const [newPwd, setNewPwd] = useState('')

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ['usuarios'],
    queryFn: () => apiClient.get('/usuarios/').then(r => r.data),
  })

  // Roles dinámicos desde la BD
  const { data: roles = [] } = useQuery({
    queryKey: ['roles'],
    queryFn: () => apiClient.get('/roles/').then(r => r.data),
  })

  // Helpers para buscar label/color de un rol por su nombre (enum)
  const rolLabel = (nombre: string) => {
    const r = roles.find((x: any) => x.nombre === nombre)
    return r?.label || nombre
  }
  const rolColor = (nombre: string) => {
    const r = roles.find((x: any) => x.nombre === nombre)
    return r?.color || '#64748B'
  }


  const createMutation = useMutation({
    mutationFn: (body: any) => apiClient.post('/usuarios/', body).then(r => r.data),
    onSuccess: () => {
      toast.success('Usuario creado')
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      setOpenCreate(false)
      setForm(emptyForm)
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error creando usuario')),
  })

  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: any }) =>
      apiClient.put(`/usuarios/${id}`, body).then(r => r.data),
    onSuccess: () => {
      toast.success('Usuario actualizado')
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      setOpenEdit(false)
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error actualizando usuario')),
  })

  const resetPwdMutation = useMutation({
    mutationFn: ({ id, pwd }: { id: number; pwd: string }) =>
      apiClient.put(`/usuarios/${id}/reset-password`, { nueva_password: pwd }),
    onSuccess: () => {
      toast.success('Contraseña restablecida')
      setOpenPwd(false)
      setNewPwd('')
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error restableciendo contraseña')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/usuarios/${id}`),
    onSuccess: () => {
      toast.success('Usuario desactivado')
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error desactivando usuario'),
  })

  const handleCreate = () => {
    if (!form.nombre || !form.email || !form.username || !form.password) {
      toast.error('Nombre, email, usuario y contraseña son obligatorios')
      return
    }
    createMutation.mutate(form)
  }

  const openEditDialog = (u: any) => {
    setSelected(u)
    setEditForm({
      nombre: u.nombre, apellido: u.apellido, email: u.email,
      rol: u.rol, telefono: u.telefono || '', cargo: u.cargo || '',
    })
    setOpenEdit(true)
  }

  // KPI por roles del sistema (primeros 3 no-consulta)
  const kpiRoles = roles
    .filter((r: any) => r.nombre !== 'CONSULTA')
    .slice(0, 3)

  return (
    <Layout title="Usuarios">
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2.5 }}>
        <Typography variant="body2" sx={{ color: '#64748B' }}>
          Gestión de acceso y roles al sistema
        </Typography>
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          <Button variant="outlined" startIcon={<AdminPanelSettings />}
            onClick={() => navigate('/configuracion/roles')}
            sx={{ borderColor: PRIMARY, color: PRIMARY }}>
            Roles
          </Button>
          <Button variant="contained" startIcon={<Add />} onClick={() => setOpenCreate(true)}
            sx={{ bgcolor: PRIMARY, '&:hover': { bgcolor: '#1A1A1A' } }}>
            Nuevo Usuario
          </Button>
        </Box>
      </Box>

      {/* KPI */}
      <Grid container spacing={2} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 6, sm: 3 }}>
          <Card sx={{ p: 2, textAlign: 'center', borderRadius: '12px' }}>
            <Typography sx={{ fontSize: 28, fontWeight: 800, color: PRIMARY }}>
              {isLoading ? '—' : usuarios.length}
            </Typography>
            <Typography sx={{ fontSize: 11, color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>
              Usuarios activos
            </Typography>
          </Card>
        </Grid>
        {kpiRoles.map((r: any) => (
          <Grid size={{ xs: 6, sm: 3 }} key={r.nombre}>
            <Card sx={{ p: 2, textAlign: 'center', borderRadius: '12px' }}>
              <Typography sx={{ fontSize: 28, fontWeight: 800, color: r.color }}>
                {isLoading ? '—' : usuarios.filter((u: any) => u.rol === r.nombre).length}
              </Typography>
              <Typography sx={{ fontSize: 11, color: '#64748B', fontWeight: 600, textTransform: 'uppercase', lineHeight: 1.2 }}>
                {r.label || r.nombre}
              </Typography>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Tabla */}
      <Card>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Usuario</TableCell>
                <TableCell>Email</TableCell>
                <TableCell>Username</TableCell>
                <TableCell>Cargo</TableCell>
                <TableCell>Rol</TableCell>
                <TableCell>Teléfono</TableCell>
                <TableCell align="right">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((_, j) => (
                      <TableCell key={j}><Skeleton /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : usuarios.map((u: any) => {
                const color = rolColor(u.rol)
                return (
                  <TableRow key={u.id} hover>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <Avatar sx={{ width: 32, height: 32, bgcolor: color, fontSize: 13, fontWeight: 700 }}>
                          {getInitials(u.nombre, u.apellido)}
                        </Avatar>
                        <Typography sx={{ fontWeight: 600, fontSize: 13 }}>
                          {u.nombre} {u.apellido}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell><Typography sx={{ fontSize: 12 }}>{u.email}</Typography></TableCell>
                    <TableCell>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: 12, color: '#475569' }}>
                        @{u.username}
                      </Typography>
                    </TableCell>
                    <TableCell><Typography sx={{ fontSize: 12 }}>{u.cargo || '—'}</Typography></TableCell>
                    <TableCell>
                      <Chip
                        label={rolLabel(u.rol)}
                        size="small"
                        sx={{
                          bgcolor: alpha(color, 0.12),
                          color,
                          fontWeight: 700,
                          fontSize: 10,
                        }}
                      />
                    </TableCell>
                    <TableCell><Typography sx={{ fontSize: 12 }}>{u.telefono || '—'}</Typography></TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 0.5 }}>
                        <Tooltip title="Editar">
                          <IconButton size="small" onClick={() => openEditDialog(u)} sx={{ color: '#64748B' }}>
                            <Edit fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Restablecer contraseña">
                          <IconButton
                            size="small"
                            onClick={() => { setSelected(u); setNewPwd(''); setOpenPwd(true) }}
                            sx={{ color: '#64748B' }}
                          >
                            <Lock fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        {u.id !== currentUser?.id && (
                          <Tooltip title="Desactivar usuario">
                            <IconButton
                              size="small"
                              onClick={() => deleteMutation.mutate(u.id)}
                              sx={{ color: '#94A3B8', '&:hover': { color: '#EF4444', bgcolor: alpha('#EF4444', 0.06) } }}
                            >
                              <Close fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Box>
      </Card>

      {/* Dialog Crear */}
      <Dialog open={openCreate} onClose={() => setOpenCreate(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Nuevo Usuario</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            {[
              { label: 'Nombre', key: 'nombre' },
              { label: 'Apellido', key: 'apellido' },
              { label: 'Email', key: 'email', type: 'email' },
              { label: 'Username', key: 'username' },
              { label: 'Contraseña', key: 'password', type: 'password' },
              { label: 'Teléfono', key: 'telefono' },
              { label: 'Cargo', key: 'cargo' },
            ].map(f => (
              <Grid size={{ xs: 12, sm: 6 }} key={f.key}>
                <TextField
                  fullWidth size="small" label={f.label} type={f.type || 'text'}
                  value={(form as any)[f.key]}
                  onChange={e => setForm({ ...form, [f.key]: e.target.value })}
                />
              </Grid>
            ))}
            <Grid size={{ xs: 12 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Rol</InputLabel>
                <Select value={form.rol} label="Rol" onChange={e => setForm({ ...form, rol: e.target.value })}>
                  {roles.map((r: any) => (
                    <MenuItem key={r.nombre} value={r.nombre}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: r.color }} />
                        {r.label || r.nombre}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenCreate(false)}>Cancelar</Button>
          <Button
            variant="contained" onClick={handleCreate} disabled={createMutation.isPending}
            sx={{ bgcolor: PRIMARY, '&:hover': { bgcolor: '#1A1A1A' } }}
          >
            {createMutation.isPending ? 'Creando...' : 'Crear'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Dialog Editar */}
      <Dialog open={openEdit} onClose={() => setOpenEdit(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Editar Usuario</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            {[
              { label: 'Nombre', key: 'nombre' },
              { label: 'Apellido', key: 'apellido' },
              { label: 'Email', key: 'email', type: 'email' },
              { label: 'Teléfono', key: 'telefono' },
              { label: 'Cargo', key: 'cargo' },
            ].map(f => (
              <Grid size={{ xs: 12, sm: 6 }} key={f.key}>
                <TextField
                  fullWidth size="small" label={f.label} type={f.type || 'text'}
                  value={editForm[f.key] || ''}
                  onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })}
                />
              </Grid>
            ))}
            <Grid size={{ xs: 12 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Rol</InputLabel>
                <Select
                  value={editForm.rol || ''}
                  label="Rol"
                  onChange={e => setEditForm({ ...editForm, rol: e.target.value })}
                >
                  {roles.map((r: any) => (
                    <MenuItem key={r.nombre} value={r.nombre}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: r.color }} />
                        {r.label || r.nombre}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenEdit(false)}>Cancelar</Button>
          <Button
            variant="contained" disabled={editMutation.isPending}
            onClick={() => editMutation.mutate({ id: selected.id, body: editForm })}
            sx={{ bgcolor: PRIMARY, '&:hover': { bgcolor: '#1A1A1A' } }}
          >
            {editMutation.isPending ? 'Guardando...' : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Dialog Reset Password */}
      <Dialog open={openPwd} onClose={() => setOpenPwd(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Restablecer Contraseña</DialogTitle>
        <DialogContent>
          <Typography sx={{ mb: 2, fontSize: 13, color: '#64748B' }}>
            Nueva contraseña para {selected?.nombre} {selected?.apellido}
          </Typography>
          <TextField
            fullWidth size="small" label="Nueva contraseña" type="password"
            value={newPwd} onChange={e => setNewPwd(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenPwd(false)}>Cancelar</Button>
          <Button
            variant="contained" disabled={resetPwdMutation.isPending}
            onClick={() => resetPwdMutation.mutate({ id: selected.id, pwd: newPwd })}
            sx={{ bgcolor: PRIMARY, '&:hover': { bgcolor: '#1A1A1A' } }}
          >
            {resetPwdMutation.isPending ? 'Restableciendo...' : 'Restablecer'}
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
