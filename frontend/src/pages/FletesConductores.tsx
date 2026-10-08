import React, { useState } from 'react'
import {
  Box, Paper, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, IconButton, Stack, Chip, Tooltip, CircularProgress, Collapse, alpha, Divider,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  DirectionsBus as ConductorIcon,
  DirectionsCar as VehiculoIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  CheckCircle as LinkedIcon,
  RadioButtonUnchecked as UnlinkedIcon,
  Phone as PhoneIcon,
  Badge as CedulaIcon,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'

import { COLOR_MODULO } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'
const FT_COLOR = COLOR_MODULO

const TIPOS_VEHICULO = [
  { value: 'TRACTOCAMION',    label: 'Tractocamión' },
  { value: 'CAMION_SENCILLO', label: 'Camión Sencillo' },
  { value: 'DOBLETROQUE',     label: 'Dobletroque' },
  { value: 'PATINETA',        label: 'Patineta' },
  { value: 'TURBO',           label: 'Turbo' },
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

interface Conductor { id: number; nombre: string; apellido: string; cedula?: string; telefono?: string; usuario_id?: number }
interface VehiculoFlete { id: number; conductor_id: number; placa: string; tipo_vehiculo: string; tipo_carroceria?: string; marca?: string; modelo?: string; anio?: number; capacidad_kg?: number; observaciones?: string }

const tipoLabel = (v: string) => TIPOS_VEHICULO.find(t => t.value === v)?.label ?? v
const carroceriaLabel = (v?: string) => v ? (TIPOS_CARROCERIA.find(t => t.value === v)?.label ?? v) : ''

const EMPTY_VEH = { placa: '', tipo_vehiculo: '', tipo_carroceria: '', marca: '', modelo: '', anio: '', capacidad_kg: '', observaciones: '' }

export default function FletesConductores() {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<number | null>(null)
  const [vehDialog, setVehDialog] = useState<{ conductorId: number; veh?: VehiculoFlete } | null>(null)
  const [vehForm, setVehForm] = useState(EMPTY_VEH)
  const [deleteVeh, setDeleteVeh] = useState<VehiculoFlete | null>(null)

  const { data: conductores = [], isLoading } = useQuery<Conductor[]>({
    queryKey: ['conductores'],
    queryFn: () => api.get('/fletes/conductores/').then(r => r.data),
  })

  const { data: todosVehiculos = [] } = useQuery<VehiculoFlete[]>({
    queryKey: ['vehiculos-flete-todos'],
    queryFn: () => api.get('/fletes/vehiculos/').then(r => r.data),
  })

  const vehiculosPorConductor = (conductorId: number) =>
    todosVehiculos.filter(v => v.conductor_id === conductorId)

  const openVehDialog = (conductorId: number, veh?: VehiculoFlete) => {
    setVehDialog({ conductorId, veh })
    if (veh) {
      setVehForm({
        placa: veh.placa, tipo_vehiculo: veh.tipo_vehiculo,
        tipo_carroceria: veh.tipo_carroceria ?? '', marca: veh.marca ?? '',
        modelo: veh.modelo ?? '', anio: veh.anio ? String(veh.anio) : '',
        capacidad_kg: veh.capacidad_kg ? String(veh.capacidad_kg) : '',
        observaciones: veh.observaciones ?? '',
      })
    } else {
      setVehForm(EMPTY_VEH)
    }
  }

  const createVehMut = useMutation({
    mutationFn: (data: object) => api.post('/fletes/vehiculos/', data).then(r => r.data),
    onSuccess: () => {
      toast.success('Vehículo registrado')
      qc.invalidateQueries({ queryKey: ['vehiculos-flete-todos'] })
      setVehDialog(null)
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al registrar vehículo')),
  })

  const updateVehMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) =>
      api.put(`/fletes/vehiculos/${id}`, data).then(r => r.data),
    onSuccess: () => {
      toast.success('Vehículo actualizado')
      qc.invalidateQueries({ queryKey: ['vehiculos-flete-todos'] })
      setVehDialog(null)
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al actualizar vehículo')),
  })

  const deleteVehMut = useMutation({
    mutationFn: (id: number) => api.delete(`/fletes/vehiculos/${id}`),
    onSuccess: () => {
      toast.success('Vehículo eliminado')
      qc.invalidateQueries({ queryKey: ['vehiculos-flete-todos'] })
      setDeleteVeh(null)
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'Error al eliminar vehículo')),
  })

  const handleVehSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!vehForm.placa || !vehForm.tipo_vehiculo) { toast.error('Placa y tipo de vehículo son obligatorios'); return }
    const payload: Record<string, unknown> = {
      placa: vehForm.placa.toUpperCase(),
      tipo_vehiculo: vehForm.tipo_vehiculo,
      conductor_id: vehDialog!.conductorId,
    }
    if (vehForm.tipo_carroceria) payload.tipo_carroceria = vehForm.tipo_carroceria
    if (vehForm.marca) payload.marca = vehForm.marca
    if (vehForm.modelo) payload.modelo = vehForm.modelo
    if (vehForm.anio) payload.anio = Number(vehForm.anio)
    if (vehForm.capacidad_kg) payload.capacidad_kg = Number(vehForm.capacidad_kg)
    if (vehForm.observaciones) payload.observaciones = vehForm.observaciones

    if (vehDialog?.veh) updateVehMut.mutate({ id: vehDialog.veh.id, data: payload })
    else createVehMut.mutate(payload)
  }

  const isMutating = createVehMut.isPending || updateVehMut.isPending

  return (
    <Layout title="Conductores y Vehículos">
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography fontSize={22} fontWeight={800} color="text.primary" letterSpacing="-0.03em">
            Conductores y Vehículos
          </Typography>
          <Typography fontSize={13} color="text.secondary" mt={0.25}>
            Gestión de conductores y sus vehículos para el módulo de fletes
          </Typography>
        </Box>
      </Stack>

      {/* KPIs */}
      <Grid container spacing={2} mb={3}>
        {[
          { label: 'Conductores', count: conductores.length, color: FT_COLOR },
          { label: 'Con cuenta de usuario', count: conductores.filter(c => c.usuario_id).length, color: '#1A1A1A' },
          { label: 'Vehículos registrados', count: todosVehiculos.length, color: '#3B82F6' },
        ].map(k => (
          <Grid key={k.label} size={{ xs: 6, md: 4 }}>
            <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 2.5 }}>
              <Typography fontSize={28} fontWeight={800} color={k.color} lineHeight={1}>{k.count}</Typography>
              <Typography fontSize={12} color="text.secondary" mt={0.25}>{k.label}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      {/* Aviso sobre creación */}
      <Paper elevation={0} sx={{ bgcolor: alpha(FT_COLOR, 0.06), border: `1px solid ${alpha(FT_COLOR, 0.25)}`, borderRadius: '12px', p: 2, mb: 3 }}>
        <Typography fontSize={13} color="text.secondary">
          <strong style={{ color: FT_COLOR }}>Nota:</strong> Los conductores se crean desde el módulo de{' '}
          <strong>Configuración → Usuarios</strong> seleccionando el rol <strong>Conductor</strong>,
          o desde el módulo de <strong>Control de Estibas → Manifiestos</strong>.
          Aquí puedes registrar y gestionar sus vehículos para el despacho de fletes.
        </Typography>
      </Paper>

      {/* Lista de conductores */}
      {isLoading ? (
        <Box display="flex" justifyContent="center" py={8}><CircularProgress sx={{ color: FT_COLOR }} /></Box>
      ) : conductores.length === 0 ? (
        <Box textAlign="center" py={10}>
          <ConductorIcon sx={{ fontSize: 56, color: '#D1D5DB', mb: 2 }} />
          <Typography color="text.secondary">No hay conductores registrados en el sistema</Typography>
        </Box>
      ) : (
        <Stack gap={1.5}>
          {conductores.map(conductor => {
            const vehiculos = vehiculosPorConductor(conductor.id)
            const isOpen = expanded === conductor.id
            return (
              <Paper key={conductor.id} elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', overflow: 'hidden' }}>
                {/* Fila del conductor */}
                <Stack
                  direction="row" alignItems="center" gap={2} p={2}
                  sx={{ cursor: 'pointer', '&:hover': { bgcolor: '#FAFAFA' } }}
                  onClick={() => setExpanded(isOpen ? null : conductor.id)}
                >
                  <Box sx={{
                    width: 44, height: 44, borderRadius: '12px', flexShrink: 0,
                    bgcolor: alpha(FT_COLOR, 0.12),
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <ConductorIcon sx={{ fontSize: 22, color: FT_COLOR }} />
                  </Box>

                  <Box flex={1} minWidth={0}>
                    <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
                      <Typography fontWeight={700} fontSize={14}>
                        {conductor.nombre} {conductor.apellido}
                      </Typography>
                      {conductor.usuario_id ? (
                        <Chip
                          icon={<LinkedIcon sx={{ fontSize: 13 }} />}
                          label="Con acceso al sistema"
                          size="small"
                          sx={{ bgcolor: alpha('#1A1A1A', 0.1), color: '#1A1A1A', fontSize: 10, height: 20 }}
                        />
                      ) : (
                        <Chip
                          icon={<UnlinkedIcon sx={{ fontSize: 13 }} />}
                          label="Sin acceso al sistema"
                          size="small"
                          sx={{ bgcolor: '#F3F4F6', color: '#9CA3AF', fontSize: 10, height: 20 }}
                        />
                      )}
                    </Stack>
                    <Stack direction="row" gap={2} mt={0.25} flexWrap="wrap">
                      {conductor.cedula && (
                        <Stack direction="row" gap={0.5} alignItems="center">
                          <CedulaIcon sx={{ fontSize: 12, color: '#9CA3AF' }} />
                          <Typography fontSize={12} color="text.secondary">CC {conductor.cedula}</Typography>
                        </Stack>
                      )}
                      {conductor.telefono && (
                        <Stack direction="row" gap={0.5} alignItems="center">
                          <PhoneIcon sx={{ fontSize: 12, color: '#9CA3AF' }} />
                          <Typography fontSize={12} color="text.secondary">{conductor.telefono}</Typography>
                        </Stack>
                      )}
                    </Stack>
                  </Box>

                  <Stack direction="row" gap={1} alignItems="center">
                    <Chip
                      icon={<VehiculoIcon sx={{ fontSize: 14 }} />}
                      label={`${vehiculos.length} vehículo${vehiculos.length !== 1 ? 's' : ''}`}
                      size="small"
                      sx={{ bgcolor: alpha('#3B82F6', 0.1), color: '#3B82F6', fontSize: 11 }}
                    />
                    <Button
                      size="small" variant="outlined"
                      startIcon={<AddIcon />}
                      onClick={e => { e.stopPropagation(); openVehDialog(conductor.id) }}
                      sx={{
                        borderRadius: '8px', textTransform: 'none', fontSize: 12,
                        borderColor: alpha(FT_COLOR, 0.5), color: FT_COLOR,
                        '&:hover': { borderColor: FT_COLOR, bgcolor: alpha(FT_COLOR, 0.05) },
                      }}
                    >
                      Agregar vehículo
                    </Button>
                    {isOpen ? <CollapseIcon sx={{ color: '#9CA3AF' }} /> : <ExpandIcon sx={{ color: '#9CA3AF' }} />}
                  </Stack>
                </Stack>

                {/* Panel de vehículos */}
                <Collapse in={isOpen}>
                  <Divider />
                  <Box p={2} bgcolor="#FAFAFA">
                    {vehiculos.length === 0 ? (
                      <Typography fontSize={13} color="text.secondary" textAlign="center" py={1}>
                        Este conductor no tiene vehículos registrados
                      </Typography>
                    ) : (
                      <Grid container spacing={1.5}>
                        {vehiculos.map(veh => (
                          <Grid key={veh.id} size={{ xs: 12, sm: 6, md: 4 }}>
                            <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '10px', p: 2 }}>
                              <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                                <Box>
                                  <Typography fontWeight={700} fontSize={15} letterSpacing="0.05em" color="#1F2937">
                                    {veh.placa}
                                  </Typography>
                                  <Stack direction="row" gap={0.5} flexWrap="wrap" mt={0.5}>
                                    <Chip label={tipoLabel(veh.tipo_vehiculo)} size="small" sx={{ height: 18, fontSize: 10 }} />
                                    {veh.tipo_carroceria && (
                                      <Chip label={carroceriaLabel(veh.tipo_carroceria)} size="small" variant="outlined" sx={{ height: 18, fontSize: 10 }} />
                                    )}
                                  </Stack>
                                </Box>
                                <Stack direction="row" gap={0.25}>
                                  <Tooltip title="Editar">
                                    <IconButton size="small" onClick={() => openVehDialog(conductor.id, veh)}>
                                      <EditIcon sx={{ fontSize: 15, color: '#9CA3AF' }} />
                                    </IconButton>
                                  </Tooltip>
                                  <Tooltip title="Eliminar">
                                    <IconButton size="small" onClick={() => setDeleteVeh(veh)}>
                                      <DeleteIcon sx={{ fontSize: 15, color: '#EF4444' }} />
                                    </IconButton>
                                  </Tooltip>
                                </Stack>
                              </Stack>
                              {(veh.marca || veh.modelo || veh.anio) && (
                                <Typography fontSize={11} color="text.secondary" mt={0.75}>
                                  {[veh.marca, veh.modelo, veh.anio].filter(Boolean).join(' · ')}
                                </Typography>
                              )}
                              {veh.capacidad_kg && (
                                <Typography fontSize={11} color="text.secondary">
                                  Capacidad: {veh.capacidad_kg.toLocaleString()} kg
                                </Typography>
                              )}
                            </Paper>
                          </Grid>
                        ))}
                      </Grid>
                    )}
                  </Box>
                </Collapse>
              </Paper>
            )
          })}
        </Stack>
      )}

      {/* Dialog vehículo */}
      <Dialog open={!!vehDialog} onClose={() => setVehDialog(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>
          {vehDialog?.veh ? 'Editar Vehículo' : 'Registrar Vehículo'}
        </DialogTitle>
        <Box component="form" onSubmit={handleVehSubmit}>
          <DialogContent>
            <Grid container spacing={2} pt={0.5}>
              <Grid size={6}>
                <TextField
                  label="Placa *" fullWidth size="small"
                  value={vehForm.placa}
                  onChange={e => setVehForm(f => ({ ...f, placa: e.target.value.toUpperCase() }))}
                  inputProps={{ style: { textTransform: 'uppercase' } }}
                />
              </Grid>
              <Grid size={6}>
                <TextField
                  select label="Tipo de Vehículo *" fullWidth size="small"
                  value={vehForm.tipo_vehiculo}
                  onChange={e => setVehForm(f => ({ ...f, tipo_vehiculo: e.target.value }))}
                >
                  {TIPOS_VEHICULO.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
                </TextField>
              </Grid>
              <Grid size={6}>
                <TextField
                  select label="Tipo de Carrocería" fullWidth size="small"
                  value={vehForm.tipo_carroceria}
                  onChange={e => setVehForm(f => ({ ...f, tipo_carroceria: e.target.value }))}
                >
                  <MenuItem value=""><em>Sin especificar</em></MenuItem>
                  {TIPOS_CARROCERIA.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
                </TextField>
              </Grid>
              <Grid size={6}>
                <TextField
                  label="Marca" fullWidth size="small"
                  value={vehForm.marca}
                  onChange={e => setVehForm(f => ({ ...f, marca: e.target.value }))}
                />
              </Grid>
              <Grid size={4}>
                <TextField
                  label="Modelo" fullWidth size="small"
                  value={vehForm.modelo}
                  onChange={e => setVehForm(f => ({ ...f, modelo: e.target.value }))}
                />
              </Grid>
              <Grid size={4}>
                <TextField
                  label="Año" type="number" fullWidth size="small"
                  inputProps={{ min: 1950, max: 2030 }}
                  value={vehForm.anio}
                  onChange={e => setVehForm(f => ({ ...f, anio: e.target.value }))}
                />
              </Grid>
              <Grid size={4}>
                <TextField
                  label="Capacidad (kg)" type="number" fullWidth size="small"
                  inputProps={{ min: 0 }}
                  value={vehForm.capacidad_kg}
                  onChange={e => setVehForm(f => ({ ...f, capacidad_kg: e.target.value }))}
                />
              </Grid>
              <Grid size={12}>
                <TextField
                  label="Observaciones" fullWidth size="small" multiline rows={2}
                  value={vehForm.observaciones}
                  onChange={e => setVehForm(f => ({ ...f, observaciones: e.target.value }))}
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
            <Button size="small" onClick={() => setVehDialog(null)} sx={{ textTransform: 'none' }}>Cancelar</Button>
            <Button
              type="submit" size="small" variant="contained" disabled={isMutating}
              startIcon={isMutating ? <CircularProgress size={14} color="inherit" /> : undefined}
              sx={{ textTransform: 'none', bgcolor: FT_COLOR, '&:hover': { bgcolor: '#D97706' } }}
            >
              {vehDialog?.veh ? 'Guardar cambios' : 'Registrar vehículo'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>

      {/* Confirm delete vehículo */}
      <Dialog open={!!deleteVeh} onClose={() => setDeleteVeh(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>Eliminar Vehículo</DialogTitle>
        <DialogContent>
          <Typography fontSize={14} color="text.secondary">
            ¿Eliminar el vehículo con placa <strong>{deleteVeh?.placa}</strong>?
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          <Button size="small" onClick={() => setDeleteVeh(null)} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button
            size="small" variant="contained" color="error"
            disabled={deleteVehMut.isPending}
            onClick={() => deleteVeh && deleteVehMut.mutate(deleteVeh.id)}
            sx={{ textTransform: 'none' }}
          >
            Eliminar
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
