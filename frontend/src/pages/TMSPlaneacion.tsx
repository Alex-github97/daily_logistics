/**
 * TMS · Planificación de transporte
 *
 * Era una maqueta: órdenes, vehículos y conductores escritos a mano, horas
 * trabajadas inventadas, y «Crear viaje» solo quitaba la tarjeta de la lista.
 *
 * Ahora la cola son los viajes PROGRAMADOS reales. La capacidad libre de cada
 * vehículo la calcula el servidor con los viajes que ya tiene asignados, y si
 * un conductor está ocupado se sabe por su viaje activo. Al asignar, el
 * servidor vuelve a comprobar todo —capacidad, licencia, conductor libre— y
 * pasa el viaje a ASIGNADO en un solo paso.
 *
 * Las «horas trabajadas» de la maqueta se quitaron: el sistema no registra la
 * jornada del conductor, y un número inventado no puede decidir quién sale.
 */
import { useState } from 'react'
import {
  Box, Typography, Stack, Paper, Chip, Button, Tabs, Tab, alpha, Divider, Alert, MenuItem, LinearProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { DirectionsBus, Person, CheckCircle, WarningAmber, Schedule, FmdGood, AssignmentTurnedIn } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { tmsApi, type Planeacion } from '@/api/tms'
import { apiClient } from '@/api/client'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO
const fmt = (n?: number | null) => (n == null ? '—' : new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n))
const kg = (n?: number | null) => (n == null ? '—' : `${n.toLocaleString('es-CO')} kg`)

type Pendiente = Planeacion['pendientes'][number]
type Vehiculo = Planeacion['vehiculos'][number]
type Conductor = Planeacion['conductores'][number]

/** Urgencia por la fecha de cargue: se calcula, no se guarda. */
function urgencia(p: Pendiente) {
  if (!p.fecha_cargue) return { label: 'SIN FECHA', color: '#6B7280', bg: '#F3F4F6', orden: 3 }
  const dias = Math.floor((aFecha(p.fecha_cargue).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000)
  if (dias < 0) return { label: 'ATRASADO', color: '#991B1B', bg: '#FEE2E2', orden: 0 }
  if (dias === 0) return { label: 'HOY', color: '#DC2626', bg: '#FEE2E2', orden: 1 }
  if (dias === 1) return { label: 'MAÑANA', color: '#D97706', bg: '#FEF3C7', orden: 2 }
  return { label: `EN ${dias} DÍAS`, color: '#0369A1', bg: '#E0F2FE', orden: 3 }
}

export default function TMSPlaneacion() {
  const qc = useQueryClient()
  const [sel, setSel] = useState<Pendiente | null>(null)
  const [veh, setVeh] = useState<Vehiculo | null>(null)
  const [cond, setCond] = useState<Conductor | null>(null)
  const [tab, setTab] = useState(0)
  const [filtro, setFiltro] = useState('TODOS')

  const { data, isLoading } = useQuery({ queryKey: ['tms-planeacion'], queryFn: tmsApi.planeacion })
  const pendientes = [...(data?.pendientes ?? [])].sort((a, b) => urgencia(a).orden - urgencia(b).orden)
  const vehiculos = data?.vehiculos ?? []
  const conductores = data?.conductores ?? []
  const filtrados = pendientes.filter(p => filtro === 'TODOS' || urgencia(p).label === filtro || (filtro === 'PROXIMOS' && urgencia(p).orden === 3))

  // Peso y volumen: el servidor bloquea igual, aquí solo se adelanta el aviso.
  const sinCapacidad = (v: Vehiculo, p: Pendiente | null) =>
    !!(p?.peso_kg && v.capacidad_libre_kg != null && v.capacidad_libre_kg < p.peso_kg)
    || !!(p?.volumen_m3 && v.capacidad_libre_m3 != null && v.capacidad_libre_m3 < p.volumen_m3)
  const aptos = useQuery<{ recomendado: { tipo: string; nombre: string } | null }>({
    queryKey: ['tms-aptos', sel?.viaje_id], enabled: !!sel,
    queryFn: () => apiClient.get(`/tms/viajes/${sel!.viaje_id}/vehiculos-aptos`).then(r => r.data),
  })
  const tipoSugerido = aptos.data?.recomendado
  const noDisponible = (c: Conductor) => c.licencia_vencida || !!c.viaje_activo

  const asignar = useMutation({
    mutationFn: () => tmsApi.asignar({ viaje_id: sel!.viaje_id, vehiculo_id: veh!.id, conductor_hcm_id: cond!.id }),
    onSuccess: () => {
      toast.success(`Viaje ${sel!.codigo} asignado a ${veh!.placa} con ${cond!.nombre}`)
      setSel(null); setVeh(null); setCond(null)
      qc.invalidateQueries({ queryKey: ['tms-planeacion'] })
      qc.invalidateQueries({ queryKey: ['tms-viajes'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo asignar'),
  })

  const puede = sel && veh && cond && !sinCapacidad(veh, sel) && !noDisponible(cond)
  const urgentesHoy = pendientes.filter(p => urgencia(p).orden <= 1).length

  return (
    <Layout>
      <Box sx={{ p: 3, maxWidth: 1600, mx: 'auto' }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
          <Box>
            <Typography variant="h5" fontWeight={800} color={TMS_COLOR}>Planificación de Transporte</Typography>
            <Typography variant="body2" color="text.secondary">{pendientes.length} viajes programados esperando vehículo y conductor</Typography>
          </Box>
          {urgentesHoy > 0 && <Chip icon={<Schedule />} label={`${urgentesHoy} para hoy o atrasados`} sx={{ bgcolor: '#FEE2E2', color: '#DC2626', fontWeight: 700 }} />}
        </Stack>
        {isLoading && <LinearProgress sx={{ mb: 2 }} />}

        <Grid container spacing={2} mb={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', overflow: 'hidden', height: '100%' }}>
              <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid #F3F4F6' }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
                  <Typography fontWeight={700} fontSize={15}>Viajes por asignar</Typography>
                  <Chip label={filtrados.length} size="small" sx={{ bgcolor: alpha(TMS_COLOR, 0.1), color: TMS_COLOR, fontWeight: 700 }} />
                </Stack>
                <TextField select size="small" label="Cargue" value={filtro} onChange={e => setFiltro(e.target.value)} sx={{ minWidth: 160 }}>
                  <MenuItem value="TODOS">Todos</MenuItem><MenuItem value="ATRASADO">Atrasados</MenuItem>
                  <MenuItem value="HOY">Hoy</MenuItem><MenuItem value="MAÑANA">Mañana</MenuItem><MenuItem value="PROXIMOS">Próximos días</MenuItem>
                </TextField>
              </Box>
              <Stack divider={<Divider />} sx={{ maxHeight: 520, overflowY: 'auto' }}>
                {!isLoading && filtrados.length === 0 && (
                  <Typography fontSize={13} color="text.secondary" p={3} textAlign="center">No hay viajes programados por asignar.</Typography>
                )}
                {filtrados.map(p => {
                  const u = urgencia(p)
                  const activo = sel?.viaje_id === p.viaje_id
                  return (
                    <Box key={p.viaje_id} role="button" aria-label={`Seleccionar ${p.codigo}`} onClick={() => { setSel(activo ? null : p); setVeh(null) }}
                      sx={{ px: 2, py: 1.5, cursor: 'pointer', bgcolor: activo ? alpha(TMS_COLOR, 0.06) : 'transparent', borderLeft: `3px solid ${activo ? TMS_COLOR : 'transparent'}`, '&:hover': { bgcolor: alpha(TMS_COLOR, 0.04) } }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                        <Box flex={1}>
                          <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
                            <Typography fontSize={13} fontWeight={700} color={TMS_COLOR}>{p.codigo}</Typography>
                            <Chip label={u.label} size="small" sx={{ bgcolor: u.bg, color: u.color, fontWeight: 800, fontSize: 10, height: 18 }} />
                          </Stack>
                          {p.cliente && <Typography fontSize={12} fontWeight={600}>{p.cliente}</Typography>}
                          <Stack direction="row" spacing={1} alignItems="center" mt={0.25}>
                            <FmdGood sx={{ fontSize: 12, color: 'text.secondary' }} />
                            <Typography fontSize={11} color="text.secondary">{p.origen || '—'} → {p.destino || '—'}</Typography>
                          </Stack>
                          <Stack direction="row" spacing={2} mt={0.5}>
                            <Typography fontSize={11} color="text.secondary"><b>{kg(p.peso_kg)}</b></Typography>
                            {p.volumen_m3 != null && <Typography fontSize={11} color="text.secondary"><b>{p.volumen_m3}</b> m³</Typography>}
                            {p.fecha_cargue && <Typography fontSize={11} color="text.secondary">Cargue: <b>{aFecha(p.fecha_cargue).toLocaleString('es-CO', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</b></Typography>}
                          </Stack>
                        </Box>
                        <Box textAlign="right">
                          <Typography fontSize={13} fontWeight={700} color={TMS_COLOR}>{fmt(p.valor_flete)}</Typography>
                          {activo && <Chip label="Seleccionado" size="small" sx={{ bgcolor: TMS_COLOR, color: '#fff', fontWeight: 700, fontSize: 10, mt: 0.5 }} />}
                        </Box>
                      </Stack>
                    </Box>
                  )
                })}
              </Stack>
            </Paper>
          </Grid>

          <Grid size={{ xs: 12, md: 6 }}>
            <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', overflow: 'hidden', height: '100%' }}>
              <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ px: 2, borderBottom: '1px solid #F3F4F6' }}>
                <Tab icon={<DirectionsBus />} iconPosition="start" label={`Vehículos (${vehiculos.length})`} sx={{ fontSize: 13 }} />
                <Tab icon={<Person />} iconPosition="start" label={`Conductores (${conductores.length})`} sx={{ fontSize: 13 }} />
              </Tabs>
              <Stack divider={<Divider />} sx={{ maxHeight: 560, overflowY: 'auto' }}>
                {tab === 0 && vehiculos.length === 0 && <Typography fontSize={13} color="text.secondary" p={3} textAlign="center">No hay vehículos disponibles o en viaje.</Typography>}
                {tab === 0 && vehiculos.map(v => {
                  const lleno = sinCapacidad(v, sel)
                  const activo = veh?.id === v.id
                  const pct = v.capacidad_kg ? Math.min(100, (v.carga_asignada_kg / v.capacidad_kg) * 100) : 0
                  return (
                    <Box key={v.id} role="button" aria-label={`Elegir vehículo ${v.placa}`} onClick={() => !lleno && setVeh(activo ? null : v)}
                      sx={{ px: 2, py: 1.5, cursor: lleno ? 'not-allowed' : 'pointer', opacity: lleno ? 0.5 : 1, bgcolor: activo ? alpha(TMS_COLOR, 0.06) : 'transparent', borderLeft: `3px solid ${activo ? TMS_COLOR : 'transparent'}` }}>
                      <Stack direction="row" justifyContent="space-between">
                        <Box>
                          <Typography fontSize={13} fontWeight={700}>{v.placa} <Typography component="span" fontSize={11} color="text.secondary">{v.tipo}</Typography></Typography>
                          <Typography fontSize={11} color="text.secondary">
                            Libre: <b>{kg(v.capacidad_libre_kg)}</b> de {kg(v.capacidad_kg)}
                            {v.capacidad_libre_m3 != null ? <> · <b>{v.capacidad_libre_m3.toLocaleString('es-CO', { maximumFractionDigits: 2 })} m³</b> de {v.volumen_m3?.toLocaleString('es-CO')} m³</> : ''}
                            {v.viaje_activo ? ` · en ${v.viaje_activo}` : ''}
                          </Typography>
                        </Box>
                        {lleno ? <Chip size="small" label="Sin capacidad" color="error" variant="outlined" />
                          : activo ? <CheckCircle sx={{ color: TMS_COLOR }} />
                          : tipoSugerido && v.tipo === tipoSugerido.tipo ? <Chip size="small" label="Tipo sugerido" color="primary" variant="outlined" /> : null}
                      </Stack>
                      {v.capacidad_kg != null && <Box sx={{ mt: 0.75, height: 5, borderRadius: 3, bgcolor: '#E5E7EB' }}><Box sx={{ height: 5, borderRadius: 3, width: `${pct}%`, bgcolor: pct > 90 ? '#DC2626' : TMS_COLOR }} /></Box>}
                    </Box>
                  )
                })}
                {tab === 1 && conductores.length === 0 && <Typography fontSize={13} color="text.secondary" p={3} textAlign="center">No hay conductores registrados en Gestión Humana.</Typography>}
                {tab === 1 && conductores.map(c => {
                  const no = noDisponible(c)
                  const activo = cond?.id === c.id
                  return (
                    <Box key={c.id} role="button" aria-label={`Elegir conductor ${c.nombre}`} onClick={() => !no && setCond(activo ? null : c)}
                      sx={{ px: 2, py: 1.5, cursor: no ? 'not-allowed' : 'pointer', opacity: no ? 0.5 : 1, bgcolor: activo ? alpha(TMS_COLOR, 0.06) : 'transparent', borderLeft: `3px solid ${activo ? TMS_COLOR : 'transparent'}` }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Box>
                          <Typography fontSize={13} fontWeight={700}>{c.nombre}</Typography>
                          <Typography fontSize={11} color="text.secondary">Licencia {c.licencia ?? '—'}{c.licencia_vence ? ` · vence ${c.licencia_vence}` : ''}</Typography>
                        </Box>
                        {c.licencia_vencida ? <Chip size="small" label="Licencia vencida" color="error" variant="outlined" />
                          : c.viaje_activo ? <Chip size="small" label={`En ${c.viaje_activo}`} />
                          : activo ? <CheckCircle sx={{ color: TMS_COLOR }} /> : <Chip size="small" label="Disponible" color="success" variant="outlined" />}
                      </Stack>
                    </Box>
                  )
                })}
              </Stack>
            </Paper>
          </Grid>
        </Grid>

        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 2.5 }}>
          <Typography fontWeight={700} mb={1.5}>Asignación</Typography>
          <Grid container spacing={2} alignItems="center">
            {[['Viaje', sel ? `${sel.codigo} · ${kg(sel.peso_kg)}` : 'Elige un viaje de la cola'],
              ['Vehículo', veh ? `${veh.placa} · ${kg(veh.capacidad_libre_kg)} libres` : 'Elige un vehículo'],
              ['Conductor', cond ? cond.nombre : 'Elige un conductor']].map(([l, v]) => (
              <Grid key={l} size={{ xs: 12, md: 3 }}>
                <Typography fontSize={11} color="text.secondary">{l}</Typography>
                <Typography fontSize={13} fontWeight={600}>{v}</Typography>
              </Grid>
            ))}
            <Grid size={{ xs: 12, md: 3 }} sx={{ textAlign: { md: 'right' } }}>
              <Button variant="contained" startIcon={<AssignmentTurnedIn />} disabled={!puede || asignar.isPending} onClick={() => asignar.mutate()} sx={{ bgcolor: TMS_COLOR }}>
                Asignar viaje
              </Button>
            </Grid>
          </Grid>
          {sel && tipoSugerido && <Alert severity="success" icon={<DirectionsBus />} sx={{ mt: 1.5 }}>Para este viaje se sugiere un vehículo tipo <b>{tipoSugerido.nombre}</b> (el más pequeño donde cabe en peso y volumen).</Alert>}
          {sel && !sel.peso_kg && <Alert severity="info" icon={<WarningAmber />} sx={{ mt: 1.5 }}>El viaje no tiene peso registrado: no se puede comprobar si cabe en el vehículo.</Alert>}
        </Paper>
      </Box>
    </Layout>
  )
}
