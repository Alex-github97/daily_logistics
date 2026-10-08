import React, { useState } from 'react'
import {
  Box, Paper, Typography, Button, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, IconButton, Stack, Chip, Tooltip,
  CircularProgress, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  CorporateFare as GeneradorIcon,
  LocationOn as CityIcon,
  Phone as PhoneIcon,
  Email as EmailIcon,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'

import { COLOR_MODULO } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'
const FT_COLOR = COLOR_MODULO

interface GeneradorCarga {
  id: number
  nombre: string
  nit?: string
  contacto?: string
  telefono?: string
  email?: string
  ciudad?: string
  activo: boolean
  created_at: string
}

const EMPTY_FORM = { nombre: '', nit: '', contacto: '', telefono: '', email: '', ciudad: '' }

export default function FletesGeneradores() {
  const qc = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<GeneradorCarga | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [deleteConfirm, setDeleteConfirm] = useState<GeneradorCarga | null>(null)

  const { data: generadores = [], isLoading } = useQuery<GeneradorCarga[]>({
    queryKey: ['fletes-generadores'],
    queryFn: () => api.get('/fletes/generadores/').then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (data: object) => api.post('/fletes/generadores/', data).then(r => r.data),
    onSuccess: () => {
      toast.success('Generador creado')
      qc.invalidateQueries({ queryKey: ['fletes-generadores'] })
      handleClose()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al crear el generador')),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) =>
      api.put(`/fletes/generadores/${id}`, data).then(r => r.data),
    onSuccess: () => {
      toast.success('Generador actualizado')
      qc.invalidateQueries({ queryKey: ['fletes-generadores'] })
      handleClose()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al actualizar')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/fletes/generadores/${id}`),
    onSuccess: () => {
      toast.success('Generador eliminado')
      qc.invalidateQueries({ queryKey: ['fletes-generadores'] })
      setDeleteConfirm(null)
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al eliminar')),
  })

  const handleOpen = (gen?: GeneradorCarga) => {
    if (gen) {
      setEditing(gen)
      setForm({ nombre: gen.nombre, nit: gen.nit ?? '', contacto: gen.contacto ?? '', telefono: gen.telefono ?? '', email: gen.email ?? '', ciudad: gen.ciudad ?? '' })
    } else {
      setEditing(null)
      setForm(EMPTY_FORM)
    }
    setDialogOpen(true)
  }

  const handleClose = () => { setDialogOpen(false); setEditing(null); setForm(EMPTY_FORM) }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nombre.trim()) { toast.error('El nombre es obligatorio'); return }
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (editing) updateMut.mutate({ id: editing.id, data: payload })
    else createMut.mutate(payload)
  }

  const isPending = createMut.isPending || updateMut.isPending

  return (
    <Layout title="Generadores de Carga">
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography fontSize={22} fontWeight={800} color="text.primary" letterSpacing="-0.03em">
            Generadores de Carga
          </Typography>
          <Typography fontSize={13} color="text.secondary" mt={0.25}>
            Empresas y clientes que generan fletes de transporte
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => handleOpen()}
          sx={{
            borderRadius: '10px', textTransform: 'none', fontWeight: 600,
            bgcolor: FT_COLOR, '&:hover': { bgcolor: '#D97706' },
            boxShadow: `0 4px 12px ${alpha(FT_COLOR, 0.4)}`,
          }}
        >
          Nuevo Generador
        </Button>
      </Stack>

      {/* KPI strip */}
      <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 2.5, mb: 3 }}>
        <Stack direction="row" gap={4}>
          <Box>
            <Typography fontSize={28} fontWeight={800} color={FT_COLOR} lineHeight={1}>{generadores.length}</Typography>
            <Typography fontSize={12} color="text.secondary" mt={0.25}>Generadores registrados</Typography>
          </Box>
          <Box>
            <Typography fontSize={28} fontWeight={800} color="#1A1A1A" lineHeight={1}>
              {generadores.filter(g => g.ciudad).length}
            </Typography>
            <Typography fontSize={12} color="text.secondary" mt={0.25}>Con ciudad registrada</Typography>
          </Box>
        </Stack>
      </Paper>

      {/* Grid de tarjetas */}
      {isLoading ? (
        <Box display="flex" justifyContent="center" py={8}><CircularProgress sx={{ color: FT_COLOR }} /></Box>
      ) : generadores.length === 0 ? (
        <Box textAlign="center" py={10}>
          <GeneradorIcon sx={{ fontSize: 56, color: '#D1D5DB', mb: 2 }} />
          <Typography color="text.secondary" fontSize={15}>No hay generadores de carga registrados</Typography>
          <Button
            variant="outlined" startIcon={<AddIcon />} onClick={() => handleOpen()}
            sx={{ mt: 2, borderRadius: '10px', textTransform: 'none', borderColor: FT_COLOR, color: FT_COLOR }}
          >
            Crear el primero
          </Button>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {generadores.map(gen => (
            <Grid key={gen.id} size={{ xs: 12, sm: 6, md: 4 }}>
              <Paper
                elevation={0}
                sx={{
                  border: '1px solid #E5E7EB', borderRadius: '14px', p: 2.5,
                  transition: 'all 0.15s', '&:hover': { boxShadow: '0 4px 20px rgba(0,0,0,0.08)', borderColor: alpha(FT_COLOR, 0.4) },
                }}
              >
                <Stack direction="row" alignItems="flex-start" justifyContent="space-between" mb={1.5}>
                  <Stack direction="row" gap={1.5} alignItems="center">
                    <Box sx={{
                      width: 40, height: 40, borderRadius: '10px',
                      bgcolor: alpha(FT_COLOR, 0.12),
                      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}>
                      <GeneradorIcon sx={{ fontSize: 20, color: FT_COLOR }} />
                    </Box>
                    <Box>
                      <Typography fontWeight={700} fontSize={14} lineHeight={1.3}>{gen.nombre}</Typography>
                      {gen.nit && (
                        <Typography fontSize={11} color="text.secondary">NIT: {gen.nit}</Typography>
                      )}
                    </Box>
                  </Stack>
                  <Stack direction="row" gap={0.5}>
                    <Tooltip title="Editar">
                      <IconButton size="small" onClick={() => handleOpen(gen)}>
                        <EditIcon fontSize="small" sx={{ color: '#9CA3AF' }} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Eliminar">
                      <IconButton size="small" onClick={() => setDeleteConfirm(gen)}>
                        <DeleteIcon fontSize="small" sx={{ color: '#EF4444' }} />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Stack>

                <Stack gap={0.75}>
                  {gen.ciudad && (
                    <Stack direction="row" alignItems="center" gap={0.75}>
                      <CityIcon sx={{ fontSize: 14, color: '#9CA3AF' }} />
                      <Typography fontSize={12} color="text.secondary">{gen.ciudad}</Typography>
                    </Stack>
                  )}
                  {gen.telefono && (
                    <Stack direction="row" alignItems="center" gap={0.75}>
                      <PhoneIcon sx={{ fontSize: 14, color: '#9CA3AF' }} />
                      <Typography fontSize={12} color="text.secondary">{gen.telefono}</Typography>
                    </Stack>
                  )}
                  {gen.email && (
                    <Stack direction="row" alignItems="center" gap={0.75}>
                      <EmailIcon sx={{ fontSize: 14, color: '#9CA3AF' }} />
                      <Typography fontSize={12} color="text.secondary">{gen.email}</Typography>
                    </Stack>
                  )}
                  {gen.contacto && (
                    <Typography fontSize={12} color="text.secondary">Contacto: {gen.contacto}</Typography>
                  )}
                </Stack>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Dialog crear/editar */}
      <Dialog open={dialogOpen} onClose={handleClose} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>
          {editing ? 'Editar Generador de Carga' : 'Nuevo Generador de Carga'}
        </DialogTitle>
        <Box component="form" onSubmit={handleSubmit}>
          <DialogContent>
            <Grid container spacing={2} pt={0.5}>
              <Grid size={8}>
                <TextField label="Nombre *" fullWidth size="small" value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} />
              </Grid>
              <Grid size={4}>
                <TextField label="NIT" fullWidth size="small" value={form.nit} onChange={e => setForm(f => ({ ...f, nit: e.target.value }))} />
              </Grid>
              <Grid size={6}>
                <TextField label="Ciudad" fullWidth size="small" value={form.ciudad} onChange={e => setForm(f => ({ ...f, ciudad: e.target.value }))} />
              </Grid>
              <Grid size={6}>
                <TextField label="Teléfono" fullWidth size="small" value={form.telefono} onChange={e => setForm(f => ({ ...f, telefono: e.target.value }))} />
              </Grid>
              <Grid size={6}>
                <TextField label="Email" fullWidth size="small" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
              </Grid>
              <Grid size={6}>
                <TextField label="Contacto (persona)" fullWidth size="small" value={form.contacto} onChange={e => setForm(f => ({ ...f, contacto: e.target.value }))} />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
            <Button size="small" onClick={handleClose} sx={{ textTransform: 'none' }}>Cancelar</Button>
            <Button
              type="submit" size="small" variant="contained" disabled={isPending}
              startIcon={isPending ? <CircularProgress size={14} color="inherit" /> : undefined}
              sx={{ textTransform: 'none', bgcolor: FT_COLOR, '&:hover': { bgcolor: '#D97706' } }}
            >
              {editing ? 'Guardar cambios' : 'Crear generador'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>

      {/* Dialog confirmar eliminación */}
      <Dialog open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>Eliminar Generador</DialogTitle>
        <DialogContent>
          <Typography fontSize={14} color="text.secondary">
            ¿Seguro que deseas eliminar <strong>{deleteConfirm?.nombre}</strong>?
            Los fletes asociados perderán este vínculo.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          <Button size="small" onClick={() => setDeleteConfirm(null)} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button
            size="small" variant="contained" color="error"
            disabled={deleteMut.isPending}
            onClick={() => deleteConfirm && deleteMut.mutate(deleteConfirm.id)}
            sx={{ textTransform: 'none' }}
          >
            Eliminar
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
