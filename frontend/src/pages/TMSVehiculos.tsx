import React, { useState, useMemo } from 'react'
import {
  Box, Card, CardContent, Typography, Stack, Chip, Button, InputAdornment, MenuItem, InputLabel, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Tabs, Tab, Paper, Divider, alpha, Tooltip,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Search,
  Add,
  LocalShipping,
  Visibility,
  Edit,
  SwapHoriz,
  Close,
  DirectionsCar,
  Build,
  Description,
  History,
  CheckCircle,
  Cancel,
  Warning,
  Info,
  FiberManualRecord,
  CalendarToday,
  Assignment,
  Speed,
  ScaleOutlined,
  Business,
} from '@mui/icons-material'
import { Layout } from '@/components/layout/Layout'
import { VehiculosCombinados } from '@/components/VehiculosCombinados'
import { apiClient as api } from '@/api/client'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { CircularProgress } from '@mui/material'

import { COLOR_MODULO } from '@/config/marca'
const TMS_COLOR = COLOR_MODULO

// ─── Types ───────────────────────────────────────────────────────────────────

type TipoVehiculo =
  | 'MOTOCICLETA'
  | 'AUTOMOVIL'
  | 'CAMIONETA'
  | 'VAN'
  | 'CAMION_SENCILLO'
  | 'DOBLE_TROQUE'
  | 'TRACTOCAMION'
  | 'REMOLQUE'
  | 'SEMIRREMOLQUE'
  | 'CARROTANQUE'
  | 'REFRIGERADO'
  | 'PLATAFORMA'
  | 'PORTACONTENEDOR'

type TipoCarroceria =
  | 'FURGON'
  | 'ESTACAS'
  | 'VOLCO'
  | 'CISTERNA'
  | 'REFRIGERADA'
  | 'PLATAFORMA'
  | 'CONTENEDOR'
  | 'ESPECIAL'

type EstadoOperativo =
  | 'DISPONIBLE'
  | 'EN_VIAJE'
  | 'EN_MANTENIMIENTO'
  | 'FUERA_SERVICIO'

interface ViajeHistorico {
  codigo: string
  origen: string
  destino: string
  fecha: string
  estado: 'COMPLETADO' | 'EN_CURSO' | 'CANCELADO'
  conductor: string
}

interface Documento {
  tipo: string
  numero: string
  vencimiento: string
  estado: 'VIGENTE' | 'POR_VENCER' | 'VENCIDO'
}

interface Vehiculo {
  id: number
  placa: string
  tipoVehiculo: TipoVehiculo
  tipoCarroceria: TipoCarroceria
  marca: string
  modelo: string
  anio: number
  configuracion: string
  capacidadKg: number
  volumenM3: number
  numEjes: number
  pesoBrutoKg: number
  empresa: string
  estadoOperativo: EstadoOperativo
  viajesHistorico: ViajeHistorico[]
  documentos: Documento[]
}

// ─── Constants ────────────────────────────────────────────────────────────────

const TIPOS_VEHICULO: TipoVehiculo[] = [
  'MOTOCICLETA', 'AUTOMOVIL', 'CAMIONETA', 'VAN', 'CAMION_SENCILLO',
  'DOBLE_TROQUE', 'TRACTOCAMION', 'REMOLQUE', 'SEMIRREMOLQUE',
  'CARROTANQUE', 'REFRIGERADO', 'PLATAFORMA', 'PORTACONTENEDOR',
]

const TIPOS_CARROCERIA: TipoCarroceria[] = [
  'FURGON', 'ESTACAS', 'VOLCO', 'CISTERNA', 'REFRIGERADA', 'PLATAFORMA', 'CONTENEDOR', 'ESPECIAL',
]

const ESTADOS_OPERATIVOS: EstadoOperativo[] = [
  'DISPONIBLE', 'EN_VIAJE', 'EN_MANTENIMIENTO', 'FUERA_SERVICIO',
]

// ─── Mock Data ────────────────────────────────────────────────────────────────

// ─── Helpers ──────────────────────────────────────────────────────────────────

function estadoChip(estado: EstadoOperativo) {
  switch (estado) {
    case 'DISPONIBLE':
      return { label: 'Disponible', color: '#16a34a', bg: alpha('#16a34a', 0.12) }
    case 'EN_VIAJE':
      return { label: 'En Viaje', color: TMS_COLOR, bg: alpha(TMS_COLOR, 0.12) }
    case 'EN_MANTENIMIENTO':
      return { label: 'En Mantenimiento', color: '#d97706', bg: alpha('#d97706', 0.12) }
    case 'FUERA_SERVICIO':
      return { label: 'Fuera de Servicio', color: '#dc2626', bg: alpha('#dc2626', 0.12) }
  }
}

function docEstadoChip(estado: Documento['estado']) {
  switch (estado) {
    case 'VIGENTE': return { color: '#16a34a', bg: alpha('#16a34a', 0.12), icon: <CheckCircle sx={{ fontSize: 14 }} /> }
    case 'POR_VENCER': return { color: '#d97706', bg: alpha('#d97706', 0.12), icon: <Warning sx={{ fontSize: 14 }} /> }
    case 'VENCIDO': return { color: '#dc2626', bg: alpha('#dc2626', 0.12), icon: <Cancel sx={{ fontSize: 14 }} /> }
  }
}

function viajeEstadoChip(estado: ViajeHistorico['estado']) {
  switch (estado) {
    case 'COMPLETADO': return { color: '#16a34a', bg: alpha('#16a34a', 0.12) }
    case 'EN_CURSO': return { color: TMS_COLOR, bg: alpha(TMS_COLOR, 0.12) }
    case 'CANCELADO': return { color: '#dc2626', bg: alpha('#dc2626', 0.12) }
  }
}

function formatNum(n: number): string {
  return n.toLocaleString('es-CO')
}

function tipoLabel(tipo: TipoVehiculo): string {
  return tipo.replace(/_/g, ' ')
}

// ─── Empty Form ───────────────────────────────────────────────────────────────

const EMPTY_FORM: Omit<Vehiculo, 'id' | 'viajesHistorico' | 'documentos'> = {
  placa: '',
  tipoVehiculo: 'CAMION_SENCILLO',
  tipoCarroceria: 'FURGON',
  marca: '',
  modelo: '',
  anio: 2024,
  configuracion: '',
  capacidadKg: 0,
  volumenM3: 0,
  numEjes: 2,
  pesoBrutoKg: 0,
  empresa: '',
  estadoOperativo: 'DISPONIBLE',
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KPICard({ label, value, color, icon }: { label: string; value: number; color: string; icon: React.ReactNode }) {
  return (
    <Card
      sx={{
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: alpha(color, 0.25),
        borderRadius: 2,
        flex: 1,
        minWidth: 140,
      }}
    >
      <CardContent sx={{ p: '14px 18px !important' }}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Box
            sx={{
              width: 40, height: 40, borderRadius: 2,
              bgcolor: alpha(color, 0.15), display: 'flex',
              alignItems: 'center', justifyContent: 'center', color,
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

// ─── Tab Panels ───────────────────────────────────────────────────────────────

interface TabPanelProps { children?: React.ReactNode; index: number; value: number }
function TabPanel({ children, value, index }: TabPanelProps) {
  return (
    <Box role="tabpanel" hidden={value !== index} sx={{ pt: 2 }}>
      {value === index && children}
    </Box>
  )
}

// ─── Dialog: Ver Vehículo ─────────────────────────────────────────────────────

function VerVehiculoDialog({ vehiculo, open, onClose }: { vehiculo: Vehiculo | null; open: boolean; onClose: () => void }) {
  const [tab, setTab] = useState(0)
  if (!vehiculo) return null
  const est = estadoChip(vehiculo.estadoOperativo)

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{
      sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: '#E5E7EB', borderRadius: 3 }
    }}>
      <DialogTitle sx={{ color: '#1E293B', pb: 0 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Box
              sx={{
                width: 40, height: 40, borderRadius: 2, bgcolor: alpha(TMS_COLOR, 0.2),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <LocalShipping sx={{ color: TMS_COLOR, fontSize: 22 }} />
            </Box>
            <Box>
              <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700, lineHeight: 1.2 }}>
                {vehiculo.placa}
              </Typography>
              <Typography variant="caption" sx={{ color: '#64748B' }}>
                {tipoLabel(vehiculo.tipoVehiculo)} · {vehiculo.marca} {vehiculo.modelo}
              </Typography>
            </Box>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Chip label={est.label} size="small" sx={{ bgcolor: est.bg, color: est.color, fontWeight: 700 }} />
            <IconButton onClick={onClose} sx={{ color: '#64748B' }}><Close /></IconButton>
          </Stack>
        </Stack>
      </DialogTitle>

      <Box sx={{ px: 3, pt: 1 }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{
            '& .MuiTab-root': { color: '#64748B', fontSize: 13, textTransform: 'none', minHeight: 40 },
            '& .Mui-selected': { color: TMS_COLOR },
            '& .MuiTabs-indicator': { bgcolor: TMS_COLOR },
          }}
        >
          <Tab icon={<Info sx={{ fontSize: 16 }} />} iconPosition="start" label="Información" />
          <Tab icon={<History sx={{ fontSize: 16 }} />} iconPosition="start" label="Historial de Viajes" />
          <Tab icon={<Description sx={{ fontSize: 16 }} />} iconPosition="start" label="Documentos" />
        </Tabs>
        <Divider sx={{ borderColor: '#E5E7EB' }} />
      </Box>

      <DialogContent sx={{ px: 3, pt: 1 }}>
        {/* Tab 0: Información */}
        <TabPanel value={tab} index={0}>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12 }}>
              <Typography variant="caption" sx={{ color: TMS_COLOR, fontWeight: 700, textTransform: 'uppercase', fontSize: 10, letterSpacing: 1 }}>
                Identificación del Vehículo
              </Typography>
            </Grid>
            {[
              { label: 'Placa', value: vehiculo.placa },
              { label: 'Tipo Vehículo', value: tipoLabel(vehiculo.tipoVehiculo) },
              { label: 'Tipo Carrocería', value: vehiculo.tipoCarroceria },
              { label: 'Marca', value: vehiculo.marca },
              { label: 'Modelo', value: vehiculo.modelo },
              { label: 'Año', value: String(vehiculo.anio) },
              { label: 'Configuración', value: vehiculo.configuracion },
            ].map((item) => (
              <Grid key={item.label} size={{ xs: 12, sm: 6, md: 4 }}>
                <Box sx={{ bgcolor: '#F8FAFC', borderRadius: 1.5, p: 1.5 }}>
                  <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>{item.label}</Typography>
                  <Typography variant="body2" sx={{ color: '#1E293B', fontWeight: 600, mt: 0.2 }}>{item.value}</Typography>
                </Box>
              </Grid>
            ))}

            <Grid size={{ xs: 12 }} sx={{ mt: 1 }}>
              <Typography variant="caption" sx={{ color: TMS_COLOR, fontWeight: 700, textTransform: 'uppercase', fontSize: 10, letterSpacing: 1 }}>
                Capacidades Técnicas
              </Typography>
            </Grid>
            {[
              { label: 'Capacidad (kg)', value: formatNum(vehiculo.capacidadKg) + ' kg' },
              { label: 'Volumen (m³)', value: vehiculo.volumenM3 > 0 ? `${vehiculo.volumenM3} m³` : 'N/A' },
              { label: 'N° Ejes', value: String(vehiculo.numEjes) },
              { label: 'Peso Bruto', value: formatNum(vehiculo.pesoBrutoKg) + ' kg' },
            ].map((item) => (
              <Grid key={item.label} size={{ xs: 12, sm: 6, md: 3 }}>
                <Box sx={{ bgcolor: '#F8FAFC', borderRadius: 1.5, p: 1.5 }}>
                  <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>{item.label}</Typography>
                  <Typography variant="body2" sx={{ color: '#1E293B', fontWeight: 600, mt: 0.2 }}>{item.value}</Typography>
                </Box>
              </Grid>
            ))}

            <Grid size={{ xs: 12 }} sx={{ mt: 1 }}>
              <Typography variant="caption" sx={{ color: TMS_COLOR, fontWeight: 700, textTransform: 'uppercase', fontSize: 10, letterSpacing: 1 }}>
                Propietario
              </Typography>
            </Grid>
            <Grid size={{ xs: 12, sm: 8 }}>
              <Box sx={{ bgcolor: '#F8FAFC', borderRadius: 1.5, p: 1.5 }}>
                <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>Empresa / Propietario</Typography>
                <Typography variant="body2" sx={{ color: '#1E293B', fontWeight: 600, mt: 0.2 }}>{vehiculo.empresa}</Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <Box sx={{ bgcolor: '#F8FAFC', borderRadius: 1.5, p: 1.5 }}>
                <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>Estado Operativo</Typography>
                <Box sx={{ mt: 0.4 }}>
                  <Chip label={est.label} size="small" sx={{ bgcolor: est.bg, color: est.color, fontWeight: 700, fontSize: 11 }} />
                </Box>
              </Box>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Tab 1: Historial */}
        <TabPanel value={tab} index={1}>
          {vehiculo.viajesHistorico.length === 0 ? (
            <Typography variant="body2" sx={{ color: '#64748B', textAlign: 'center', mt: 4 }}>
              Sin historial de viajes registrado
            </Typography>
          ) : (
            <TableContainer component={Paper} sx={{ bgcolor: 'transparent', boxShadow: 'none' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {['Código', 'Origen', 'Destino', 'Fecha', 'Conductor', 'Estado'].map((h) => (
                      <TableCell key={h} sx={{ color: '#64748B', fontSize: 11, fontWeight: 700, borderBottom: `1px solid #E5E7EB`, py: 1 }}>
                        {h}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {vehiculo.viajesHistorico.map((v) => {
                    const ec = viajeEstadoChip(v.estado)
                    return (
                      <TableRow key={v.codigo} sx={{ '&:hover': { bgcolor: '#F8FAFC' } }}>
                        <TableCell sx={{ color: TMS_COLOR, fontWeight: 700, fontSize: 12, borderBottom: `1px solid #E5E7EB` }}>
                          {v.codigo}
                        </TableCell>
                        <TableCell sx={{ color: '#334155', fontSize: 12, borderBottom: `1px solid #E5E7EB` }}>{v.origen}</TableCell>
                        <TableCell sx={{ color: '#334155', fontSize: 12, borderBottom: `1px solid #E5E7EB` }}>{v.destino}</TableCell>
                        <TableCell sx={{ color: '#64748B', fontSize: 11, borderBottom: `1px solid #E5E7EB` }}>{v.fecha}</TableCell>
                        <TableCell sx={{ color: '#334155', fontSize: 12, borderBottom: `1px solid #E5E7EB` }}>{v.conductor}</TableCell>
                        <TableCell sx={{ borderBottom: `1px solid #E5E7EB` }}>
                          <Chip
                            label={v.estado.replace('_', ' ')}
                            size="small"
                            sx={{ bgcolor: ec.bg, color: ec.color, fontWeight: 700, fontSize: 10, height: 20 }}
                          />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </TabPanel>

        {/* Tab 2: Documentos */}
        <TabPanel value={tab} index={2}>
          <Stack spacing={1.5}>
            {vehiculo.documentos.map((doc, i) => {
              const dc = docEstadoChip(doc.estado)
              return (
                <Box
                  key={i}
                  sx={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    bgcolor: '#F8FAFC', borderRadius: 2, p: 1.5,
                    border: '1px solid', borderColor: alpha(dc.color, 0.2),
                  }}
                >
                  <Stack direction="row" alignItems="center" spacing={1.5}>
                    <Box
                      sx={{
                        width: 36, height: 36, borderRadius: 1.5,
                        bgcolor: alpha(dc.color, 0.15), display: 'flex',
                        alignItems: 'center', justifyContent: 'center', color: dc.color,
                      }}
                    >
                      <Description sx={{ fontSize: 18 }} />
                    </Box>
                    <Box>
                      <Typography variant="body2" sx={{ color: '#1E293B', fontWeight: 700, fontSize: 13 }}>
                        {doc.tipo}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
                        N°: {doc.numero}
                      </Typography>
                    </Box>
                  </Stack>
                  <Stack alignItems="flex-end" spacing={0.5}>
                    <Chip
                      icon={<Box sx={{ color: `${dc.color} !important`, display: 'flex' }}>{dc.icon}</Box>}
                      label={doc.estado.replace('_', ' ')}
                      size="small"
                      sx={{ bgcolor: dc.bg, color: dc.color, fontWeight: 700, fontSize: 10, height: 22 }}
                    />
                    <Stack direction="row" alignItems="center" spacing={0.4}>
                      <CalendarToday sx={{ fontSize: 11, color: '#64748B' }} />
                      <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>
                        Vence: {doc.vencimiento}
                      </Typography>
                    </Stack>
                  </Stack>
                </Box>
              )
            })}
          </Stack>
        </TabPanel>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} variant="outlined" size="small"
          sx={{ color: '#64748B', borderColor: '#E5E7EB', '&:hover': { borderColor: '#64748B', bgcolor: '#F8FAFC' } }}>
          Cerrar
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Dialog: Registrar/Editar Vehículo ────────────────────────────────────────

function FormVehiculoDialog({
  open, onClose, initial, title, onSave, saving
}: {
  open: boolean
  onClose: () => void
  initial: Omit<Vehiculo, 'id' | 'viajesHistorico' | 'documentos'>
  title: string
  onSave: (form: Omit<Vehiculo, 'id' | 'viajesHistorico' | 'documentos'>) => void
  saving: boolean
}) {
  const [form, setForm] = useState({ ...initial })

  React.useEffect(() => {
    setForm({ ...initial })
  }, [initial, open])

  function field(key: keyof typeof form, value: unknown) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const inputSx = {
    '& .MuiInputBase-root': { fontSize: 13 },
    '& .MuiInputLabel-root': { fontSize: 13 },
    '& .MuiInputLabel-root.Mui-focused': { color: TMS_COLOR },
    '& .MuiOutlinedInput-root:hover fieldset': { borderColor: alpha(TMS_COLOR, 0.4) },
    '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: TMS_COLOR },
  }

  const sectionTitle = (label: string) => (
    <Grid size={{ xs: 12 }}>
      <Typography variant="caption" sx={{
        color: TMS_COLOR, fontWeight: 700, textTransform: 'uppercase',
        fontSize: 10, letterSpacing: 1, display: 'block', mt: 1
      }}>
        {label}
      </Typography>
      <Divider sx={{ borderColor: alpha(TMS_COLOR, 0.2), mt: 0.5 }} />
    </Grid>
  )

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{
      sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: '#E5E7EB', borderRadius: 3 }
    }}>
      <DialogTitle sx={{ color: '#1E293B' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Box sx={{ width: 36, height: 36, borderRadius: 2, bgcolor: alpha(TMS_COLOR, 0.2), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <LocalShipping sx={{ color: TMS_COLOR, fontSize: 20 }} />
            </Box>
            <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700 }}>{title}</Typography>
          </Stack>
          <IconButton onClick={onClose} sx={{ color: '#64748B' }}><Close /></IconButton>
        </Stack>
      </DialogTitle>

      <DialogContent sx={{ px: 3, pt: 0 }}>
        <Grid container spacing={2} sx={{ mt: 0 }}>
          {/* Identificación */}
          {sectionTitle('Identificación')}

          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField fullWidth size="small" label="Placa *" value={form.placa}
              onChange={(e) => field('placa', e.target.value.toUpperCase())}
              sx={inputSx} inputProps={{ maxLength: 7, style: { textTransform: 'uppercase' } }} />
          </Grid>

          <Grid size={{ xs: 12, sm: 4 }}>
            <FormControl fullWidth size="small" sx={inputSx}>
              <InputLabel>Tipo Vehículo</InputLabel>
              <Select value={form.tipoVehiculo} label="Tipo Vehículo"
                onChange={(e) => field('tipoVehiculo', e.target.value as TipoVehiculo)}
              >

                {TIPOS_VEHICULO.map((t) => (
                  <MenuItem key={t} value={t} sx={{ fontSize: 13 }}>{tipoLabel(t)}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid size={{ xs: 12, sm: 4 }}>
            <FormControl fullWidth size="small" sx={inputSx}>
              <InputLabel>Tipo Carrocería</InputLabel>
              <Select value={form.tipoCarroceria} label="Tipo Carrocería"
                onChange={(e) => field('tipoCarroceria', e.target.value as TipoCarroceria)}
              >

                {TIPOS_CARROCERIA.map((t) => (
                  <MenuItem key={t} value={t} sx={{ fontSize: 13 }}>{t}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField fullWidth size="small" label="Marca" value={form.marca}
              onChange={(e) => field('marca', e.target.value)} sx={inputSx} />
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField fullWidth size="small" label="Modelo" value={form.modelo}
              onChange={(e) => field('modelo', e.target.value)} sx={inputSx} />
          </Grid>
          <Grid size={{ xs: 12, sm: 2 }}>
            <TextField fullWidth size="small" label="Año" type="number" value={form.anio}
              onChange={(e) => field('anio', Number(e.target.value))} sx={inputSx}
              inputProps={{ min: 2000, max: 2030 }} />
          </Grid>
          <Grid size={{ xs: 12, sm: 2 }}>
            <TextField fullWidth size="small" label="Configuración" value={form.configuracion}
              onChange={(e) => field('configuracion', e.target.value)}
              placeholder="Ej: 6x4" sx={inputSx} />
          </Grid>

          {/* Capacidades */}
          {sectionTitle('Capacidades')}

          <Grid size={{ xs: 12, sm: 3 }}>
            <TextField fullWidth size="small" label="Capacidad (kg)" type="number" value={form.capacidadKg}
              onChange={(e) => field('capacidadKg', Number(e.target.value))} sx={inputSx}
              inputProps={{ min: 0 }} />
          </Grid>
          <Grid size={{ xs: 12, sm: 3 }}>
            <TextField fullWidth size="small" label="Volumen (m³)" type="number" value={form.volumenM3}
              onChange={(e) => field('volumenM3', Number(e.target.value))} sx={inputSx}
              inputProps={{ min: 0 }} />
          </Grid>
          <Grid size={{ xs: 12, sm: 3 }}>
            <TextField fullWidth size="small" label="N° Ejes" type="number" value={form.numEjes}
              onChange={(e) => field('numEjes', Number(e.target.value))} sx={inputSx}
              inputProps={{ min: 1, max: 10 }} />
          </Grid>
          <Grid size={{ xs: 12, sm: 3 }}>
            <TextField fullWidth size="small" label="Peso Bruto (kg)" type="number" value={form.pesoBrutoKg}
              onChange={(e) => field('pesoBrutoKg', Number(e.target.value))} sx={inputSx}
              inputProps={{ min: 0 }} />
          </Grid>

          {/* Propietario */}
          {sectionTitle('Propietario')}

          <Grid size={{ xs: 12, sm: 8 }}>
            <TextField fullWidth size="small" label="Empresa / Propietario" value={form.empresa}
              onChange={(e) => field('empresa', e.target.value)} sx={inputSx} />
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <FormControl fullWidth size="small" sx={inputSx}>
              <InputLabel>Estado Operativo</InputLabel>
              <Select value={form.estadoOperativo} label="Estado Operativo"
                onChange={(e) => field('estadoOperativo', e.target.value as EstadoOperativo)}
              >

                {ESTADOS_OPERATIVOS.map((e) => (
                  <MenuItem key={e} value={e} sx={{ fontSize: 13 }}>{e.replace(/_/g, ' ')}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
        <Button onClick={onClose} variant="outlined" size="small"
          sx={{ color: '#64748B', borderColor: '#E5E7EB', '&:hover': { borderColor: '#64748B', bgcolor: '#F8FAFC' } }}>
          Cancelar
        </Button>
        <Button
          variant="contained" size="small"
          disabled={saving || !form.placa}
          sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#0284c7' }, fontWeight: 700 }}
          onClick={() => onSave(form)}
        >
          {saving ? 'Guardando…' : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Dialog: Cambiar Estado ────────────────────────────────────────────────────

function CambiarEstadoDialog({
  vehiculo, open, onClose, onConfirm
}: {
  vehiculo: Vehiculo | null
  open: boolean
  onClose: () => void
  onConfirm: (id: number, estado: EstadoOperativo) => void
}) {
  const [nuevoEstado, setNuevoEstado] = useState<EstadoOperativo>('DISPONIBLE')

  React.useEffect(() => {
    if (vehiculo) setNuevoEstado(vehiculo.estadoOperativo)
  }, [vehiculo, open])

  if (!vehiculo) return null

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth PaperProps={{
      sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: '#E5E7EB', borderRadius: 3 }
    }}>
      <DialogTitle sx={{ color: '#1E293B' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="h6" sx={{ fontWeight: 700 }}>Cambiar Estado — {vehiculo.placa}</Typography>
          <IconButton onClick={onClose} sx={{ color: '#64748B' }}><Close /></IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <FormControl fullWidth size="small" sx={{ mt: 1,
          '& .MuiInputLabel-root.Mui-focused': { color: TMS_COLOR },
          '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: TMS_COLOR },
        }}>
          <InputLabel>Nuevo Estado Operativo</InputLabel>
          <Select
            value={nuevoEstado}
            label="Nuevo Estado Operativo"
            onChange={(e) => setNuevoEstado(e.target.value as EstadoOperativo)}
          >
            {ESTADOS_OPERATIVOS.map((e) => {
              const c = estadoChip(e)
              return (
                <MenuItem key={e} value={e} sx={{ fontSize: 13 }}>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <FiberManualRecord sx={{ fontSize: 10, color: c.color }} />
                    <span>{e.replace(/_/g, ' ')}</span>
                  </Stack>
                </MenuItem>
              )
            })}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
        <Button onClick={onClose} variant="outlined" size="small"
          sx={{ color: '#64748B', borderColor: '#E5E7EB', '&:hover': { borderColor: '#64748B', bgcolor: '#F8FAFC' } }}>
          Cancelar
        </Button>
        <Button
          variant="contained" size="small"
          sx={{ bgcolor: TMS_COLOR, '&:hover': { bgcolor: '#0284c7' }, fontWeight: 700 }}
          onClick={() => { onConfirm(vehiculo.id, nuevoEstado); onClose() }}
        >
          Confirmar
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Mapeo backend <-> VM ─────────────────────────────────────────────────────

function mapVehiculo(v: any): Vehiculo {
  return {
    id: v.id,
    placa: v.placa,
    tipoVehiculo: v.tipo_vehiculo,
    tipoCarroceria: v.tipo_carroceria || 'FURGON',
    marca: v.marca || '',
    modelo: v.modelo || '',
    anio: v.anio || 0,
    configuracion: v.configuracion || '',
    capacidadKg: v.capacidad_kg || 0,
    volumenM3: v.volumen_m3 || 0,
    numEjes: v.num_ejes || 0,
    pesoBrutoKg: v.peso_bruto_kg || 0,
    empresa: v.propietario || '—',
    estadoOperativo: v.estado_operativo,
    viajesHistorico: [],
    documentos: [],
  }
}

function vehiculoToPayload(f: Omit<Vehiculo, 'id' | 'viajesHistorico' | 'documentos'>): any {
  return {
    placa: f.placa,
    tipo_vehiculo: f.tipoVehiculo,
    tipo_carroceria: f.tipoCarroceria || undefined,
    marca: f.marca || undefined,
    modelo: f.modelo || undefined,
    anio: f.anio ? Number(f.anio) : undefined,
    configuracion: f.configuracion || undefined,
    capacidad_kg: f.capacidadKg ? Number(f.capacidadKg) : undefined,
    volumen_m3: f.volumenM3 ? Number(f.volumenM3) : undefined,
    num_ejes: f.numEjes ? Number(f.numEjes) : undefined,
    peso_bruto_kg: f.pesoBrutoKg ? Number(f.pesoBrutoKg) : undefined,
    propietario: f.empresa && f.empresa !== '—' ? f.empresa : undefined,
  }
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function TMSVehiculos() {
  const qc = useQueryClient()
  const { data: rawVehiculos = [], isLoading } = useQuery<any[]>({
    queryKey: ['tms-vehiculos'],
    queryFn: () => api.get('/tms/vehiculos').then((r) => r.data),
  })
  const vehiculos = useMemo(() => rawVehiculos.map(mapVehiculo), [rawVehiculos])
  const [search, setSearch] = useState('')
  const [filterTipo, setFilterTipo] = useState<TipoVehiculo | ''>('')
  const [filterEstado, setFilterEstado] = useState<EstadoOperativo | ''>('')

  const [verOpen, setVerOpen] = useState(false)
  const [verVehiculo, setVerVehiculo] = useState<Vehiculo | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [formTitle, setFormTitle] = useState('Registrar Vehículo')
  const [formInitial, setFormInitial] = useState<Omit<Vehiculo, 'id' | 'viajesHistorico' | 'documentos'>>(EMPTY_FORM)
  const [editId, setEditId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)

  const [estadoOpen, setEstadoOpen] = useState(false)
  const [estadoVehiculo, setEstadoVehiculo] = useState<Vehiculo | null>(null)
  const [vista, setVista] = useState(0)   // 0 = flota TMS · 1 = flota combinada

  const filtered = useMemo(() => {
    return vehiculos.filter((v) => {
      const q = search.toLowerCase()
      const matchSearch = !q || v.placa.toLowerCase().includes(q) || v.empresa.toLowerCase().includes(q) || v.marca.toLowerCase().includes(q)
      const matchTipo = !filterTipo || v.tipoVehiculo === filterTipo
      const matchEstado = !filterEstado || v.estadoOperativo === filterEstado
      return matchSearch && matchTipo && matchEstado
    })
  }, [vehiculos, search, filterTipo, filterEstado])

  const kpis = useMemo(() => ({
    total: vehiculos.length,
    disponibles: vehiculos.filter((v) => v.estadoOperativo === 'DISPONIBLE').length,
    enViaje: vehiculos.filter((v) => v.estadoOperativo === 'EN_VIAJE').length,
    mantenimiento: vehiculos.filter((v) => v.estadoOperativo === 'EN_MANTENIMIENTO' || v.estadoOperativo === 'FUERA_SERVICIO').length,
  }), [vehiculos])

  function handleVer(v: Vehiculo) { setVerVehiculo(v); setVerOpen(true) }
  function handleEditar(v: Vehiculo) {
    const { id, viajesHistorico, documentos, ...rest } = v
    setEditId(id); setFormInitial(rest); setFormTitle(`Editar — ${v.placa}`); setFormOpen(true)
  }
  function handleNuevo() { setEditId(null); setFormInitial({ ...EMPTY_FORM }); setFormTitle('Registrar Vehículo'); setFormOpen(true) }
  function handleCambiarEstado(v: Vehiculo) { setEstadoVehiculo(v); setEstadoOpen(true) }

  async function handleGuardar(form: Omit<Vehiculo, 'id' | 'viajesHistorico' | 'documentos'>) {
    setSaving(true)
    try {
      const payload = vehiculoToPayload(form)
      if (editId) await api.put(`/tms/vehiculos/${editId}`, payload)
      else await api.post('/tms/vehiculos', payload)
      toast.success(editId ? 'Vehículo actualizado' : 'Vehículo registrado')
      qc.invalidateQueries({ queryKey: ['tms-vehiculos'] })
      setFormOpen(false)
    } catch (e: any) { toast.error(e.response?.data?.detail || 'No se pudo guardar el vehículo') }
    finally { setSaving(false) }
  }

  async function handleConfirmarEstado(id: number, estado: EstadoOperativo) {
    try {
      await api.put(`/tms/vehiculos/${id}/estado`, null, { params: { estado_operativo: estado } })
      toast.success('Estado actualizado')
      qc.invalidateQueries({ queryKey: ['tms-vehiculos'] })
    } catch (e: any) { toast.error(e.response?.data?.detail || 'No se pudo cambiar el estado') }
  }

  const selectSx = {
    '& .MuiInputBase-root': { fontSize: 13 },
    '& .MuiInputLabel-root': { fontSize: 13 },
    '& .MuiInputLabel-root.Mui-focused': { color: TMS_COLOR },
    '& .MuiOutlinedInput-root:hover fieldset': { borderColor: alpha(TMS_COLOR, 0.4) },
    '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: TMS_COLOR },
  }

  return (
    <Layout>
      <Box sx={{ minHeight: '100%', bgcolor: '#F0F2F5', p: 3 }}>
        {/* Header */}
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" mb={3}>
          <Box>
            <Stack direction="row" alignItems="center" spacing={1.5} mb={0.3}>
              <Box sx={{ width: 36, height: 36, borderRadius: 2, bgcolor: alpha(TMS_COLOR, 0.2), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <LocalShipping sx={{ color: TMS_COLOR, fontSize: 20 }} />
              </Box>
              <Box>
                <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700, lineHeight: 1.2 }}>
                  Gestión de Vehículos
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
                  TMS — Administración de Flota Vehicular
                </Typography>
              </Box>
            </Stack>
          </Box>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={handleNuevo}
            sx={{
              bgcolor: TMS_COLOR, fontWeight: 700, fontSize: 13,
              '&:hover': { bgcolor: '#0284c7' }, borderRadius: 2, px: 2,
            }}
          >
            Registrar Vehículo
          </Button>
        </Stack>

        {/* Selector de vista */}
        <Tabs value={vista} onChange={(_, v) => setVista(v)} sx={{ mb: 2,
          '& .MuiTab-root': { color: '#64748B', fontWeight: 600, fontSize: 13, textTransform: 'none' },
          '& .Mui-selected': { color: TMS_COLOR }, '& .MuiTabs-indicator': { bgcolor: TMS_COLOR } }}>
          <Tab label="Flota TMS" />
          <Tab label="Flota combinada (propia + externa)" />
        </Tabs>

        {vista === 1 && <VehiculosCombinados color={TMS_COLOR} colorDark="#0284c7" />}

        {vista === 0 && (<>
        {/* KPIs */}
        <Stack direction="row" spacing={1.5} mb={3} flexWrap="wrap" useFlexGap>
          <KPICard label="Total Vehículos" value={kpis.total} color={TMS_COLOR} icon={<LocalShipping sx={{ fontSize: 20 }} />} />
          <KPICard label="Disponibles" value={kpis.disponibles} color="#16a34a" icon={<CheckCircle sx={{ fontSize: 20 }} />} />
          <KPICard label="En Viaje" value={kpis.enViaje} color="#2563eb" icon={<Speed sx={{ fontSize: 20 }} />} />
          <KPICard label="Mant. / Fuera Servicio" value={kpis.mantenimiento} color="#d97706" icon={<Build sx={{ fontSize: 20 }} />} />
        </Stack>

        {/* Toolbar */}
        <Stack direction="row" spacing={1.5} mb={2} flexWrap="wrap" useFlexGap>
          <TextField
            size="small"
            placeholder="Buscar por placa, empresa o marca..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ flex: 1, minWidth: 220, ...selectSx }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search sx={{ fontSize: 16, color: '#64748B' }} />
                </InputAdornment>
              ),
            }}
          />

          <FormControl size="small" sx={{ minWidth: 180, ...selectSx }}>
            <InputLabel>Tipo Vehículo</InputLabel>
            <Select
              value={filterTipo}
              label="Tipo Vehículo"
              onChange={(e) => setFilterTipo(e.target.value as TipoVehiculo | '')}
              >
              <MenuItem value="" sx={{ fontSize: 13 }}>Todos los tipos</MenuItem>
              {TIPOS_VEHICULO.map((t) => (
                <MenuItem key={t} value={t} sx={{ fontSize: 13 }}>{tipoLabel(t)}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 180, ...selectSx }}>
            <InputLabel>Estado Operativo</InputLabel>
            <Select
              value={filterEstado}
              label="Estado Operativo"
              onChange={(e) => setFilterEstado(e.target.value as EstadoOperativo | '')}
              >
              <MenuItem value="" sx={{ fontSize: 13 }}>Todos los estados</MenuItem>
              {ESTADOS_OPERATIVOS.map((e) => (
                <MenuItem key={e} value={e} sx={{ fontSize: 13 }}>{e.replace(/_/g, ' ')}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>

        {/* Table */}
        <Paper
          sx={{
            bgcolor: 'background.paper', border: '1px solid',
            borderColor: '#E5E7EB', borderRadius: 2, overflow: 'hidden',
          }}
        >
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: '#F8FAFC' }}>
                  {['Placa', 'Tipo Vehículo', 'Carrocería', 'Marca / Modelo / Año', 'Capacidad', 'Estado', 'Empresa / Propietario', 'Acciones'].map((h) => (
                    <TableCell
                      key={h}
                      sx={{
                        color: '#64748B', fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: 0.5, borderBottom: `1px solid #E5E7EB`,
                        py: 1.2, px: 2, whiteSpace: 'nowrap',
                      }}
                    >
                      {h}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={8} sx={{ textAlign: 'center', py: 5, borderBottom: 'none' }}><CircularProgress size={26} /></TableCell>
                  </TableRow>
                ) : filtered.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} sx={{ textAlign: 'center', py: 5, color: '#64748B', borderBottom: 'none' }}>
                      {vehiculos.length === 0 ? 'Aún no hay vehículos registrados. Usa “Registrar Vehículo”.' : 'No se encontraron vehículos con los filtros aplicados'}
                    </TableCell>
                  </TableRow>
                ) : (
                  filtered.map((v) => {
                    const est = estadoChip(v.estadoOperativo)
                    return (
                      <TableRow
                        key={v.id}
                        onClick={() => handleVer(v)}
                        sx={{
                          cursor: 'pointer',
                          '&:hover': { bgcolor: '#F8FAFC' },
                          '&:last-child td': { borderBottom: 'none' },
                        }}
                      >
                        <TableCell sx={{ borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2 }}>
                          <Chip
                            label={v.placa}
                            size="small"
                            sx={{ bgcolor: alpha(TMS_COLOR, 0.18), color: TMS_COLOR, fontWeight: 800, fontSize: 12, height: 24 }}
                          />
                        </TableCell>
                        <TableCell sx={{ color: '#334155', fontSize: 12, borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2, whiteSpace: 'nowrap' }}>
                          {tipoLabel(v.tipoVehiculo)}
                        </TableCell>
                        <TableCell sx={{ color: '#64748B', fontSize: 12, borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2 }}>
                          {v.tipoCarroceria}
                        </TableCell>
                        <TableCell sx={{ borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2 }}>
                          <Typography variant="body2" sx={{ color: '#1E293B', fontWeight: 600, fontSize: 12 }}>
                            {v.marca} {v.modelo}
                          </Typography>
                          <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>{v.anio} · {v.configuracion}</Typography>
                        </TableCell>
                        <TableCell sx={{ color: '#334155', fontSize: 12, borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2, whiteSpace: 'nowrap' }}>
                          {formatNum(v.capacidadKg)} kg
                        </TableCell>
                        <TableCell sx={{ borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2 }}>
                          <Chip
                            label={est.label}
                            size="small"
                            sx={{ bgcolor: est.bg, color: est.color, fontWeight: 700, fontSize: 11, height: 22 }}
                          />
                        </TableCell>
                        <TableCell sx={{ color: '#64748B', fontSize: 12, borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2 }}>
                          <Stack direction="row" alignItems="center" spacing={0.5}>
                            <Business sx={{ fontSize: 13, color: '#64748B' }} />
                            <span>{v.empresa}</span>
                          </Stack>
                        </TableCell>
                        <TableCell sx={{ borderBottom: `1px solid #E5E7EB`, px: 2, py: 1.2 }} onClick={e => e.stopPropagation()}>
                          <Stack direction="row" spacing={0.3}>
                            <Tooltip title="Ver detalle">
                              <IconButton size="small" onClick={() => handleVer(v)}
                                sx={{ color: TMS_COLOR, '&:hover': { bgcolor: alpha(TMS_COLOR, 0.1) }, width: 28, height: 28 }}>
                                <Visibility sx={{ fontSize: 15 }} />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Editar">
                              <IconButton size="small" onClick={() => handleEditar(v)}
                                sx={{ color: '#64748B', '&:hover': { bgcolor: alpha('#64748B', 0.1) }, width: 28, height: 28 }}>
                                <Edit sx={{ fontSize: 15 }} />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Cambiar estado">
                              <IconButton size="small" onClick={() => handleCambiarEstado(v)}
                                sx={{ color: '#d97706', '&:hover': { bgcolor: alpha('#d97706', 0.1) }, width: 28, height: 28 }}>
                                <SwapHoriz sx={{ fontSize: 15 }} />
                              </IconButton>
                            </Tooltip>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </TableContainer>

          {filtered.length > 0 && (
            <Box sx={{ px: 2, py: 1.2, borderTop: `1px solid #E5E7EB` }}>
              <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
                Mostrando {filtered.length} de {vehiculos.length} vehículos
              </Typography>
            </Box>
          )}
        </Paper>
        </>)}

        {/* Dialogs */}
        <VerVehiculoDialog vehiculo={verVehiculo} open={verOpen} onClose={() => setVerOpen(false)} />
        <FormVehiculoDialog open={formOpen} onClose={() => setFormOpen(false)} initial={formInitial} title={formTitle} onSave={handleGuardar} saving={saving} />
        <CambiarEstadoDialog
          vehiculo={estadoVehiculo}
          open={estadoOpen}
          onClose={() => setEstadoOpen(false)}
          onConfirm={handleConfirmarEstado}
        />
      </Box>
    </Layout>
  )
}
