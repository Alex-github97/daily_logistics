import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Stack,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableContainer,
  Chip,
  Button,
  alpha,
  Divider,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  LocalShipping,
  EventNote,
  DirectionsBus,
  PersonPin,
  CheckCircle,
  Schedule,
  AttachMoney,
  Warning,
  VisibilityOutlined,
  Circle,
} from '@mui/icons-material'
import { Layout } from '@/components/layout/Layout'
import { apiClient as api } from '@/api/client'
import { listaDe } from '@/utils/listaApi'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO

// ─── Types ───────────────────────────────────────────────────────────────────

interface KPI {
  label: string
  value: string | number
  icon: React.ReactNode
  color: string
  sub?: string
}

interface Viaje {
  id: number
  codigo: string
  estado: string
  origen_ciudad: string | null
  destino_ciudad: string | null
  conductor_nombre: string | null
  vehiculo_placa: string | null
  descripcion_carga: string | null
  fecha_real_cargue: string | null
  fecha_programada_entrega: string | null
  fecha_real_entrega: string | null
  otif_on_time: boolean | null
  otif_in_full: boolean | null
}

interface Alerta {
  id: number
  nivel: 'CRITICA' | 'ALTA' | 'MEDIA' | 'BAJA' | 'INFO'
  tipo?: string
  mensaje: string
  viaje_codigo: string | null
  conductor_id?: number | null
  vehiculo_placa?: string | null
}

interface KPIs {
  viajes_hoy: number
  viajes_en_transito: number
  viajes_completados_hoy: number
  vehiculos_activos: number
  conductores_activos: number
  otif_rate: number
  on_time_rate: number
  entregados_mes?: number
  costo_promedio_km: number
  alertas_criticas: number
}

// ─── Cálculos sobre lo que devuelve el API ───────────────────────────────────

const pesos = (v: number) =>
  new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP',
    maximumFractionDigits: 0 }).format(v || 0)

const hora = (iso: string | null) =>
  iso ? aFecha(iso).toLocaleTimeString('es-CO',
    { hour: '2-digit', minute: '2-digit' }) : '—'

/**
 * Cuánto lleva recorrido un viaje, en porcentaje del tiempo previsto.
 *
 * Se calcula del reloj y no de un dato guardado porque no hay ninguno: la
 * posición real llega por eventos de GPS sueltos, y estimarla desde ahí sería
 * prometer una precisión que el dato no tiene. El tiempo transcurrido sobre el
 * tiempo previsto es una aproximación honesta y es lo que un despachador usa
 * cuando mira la pantalla.
 */
function avance(viaje: Viaje): number {
  const salida = viaje.fecha_real_cargue ? Date.parse(viaje.fecha_real_cargue) : NaN
  const llegada = viaje.fecha_programada_entrega
    ? Date.parse(viaje.fecha_programada_entrega) : NaN
  if (!Number.isFinite(salida) || !Number.isFinite(llegada) || llegada <= salida) return 0
  return Math.max(0, Math.min(100, Math.round((Date.now() - salida) / (llegada - salida) * 100)))
}

/** Un viaje va tarde si ya pasó su hora de entrega y sigue en tránsito. */
function situacion(viaje: Viaje): 'EN_TRANSITO' | 'DEMORADO' | 'EN_RIESGO' {
  const llegada = viaje.fecha_programada_entrega
    ? Date.parse(viaje.fecha_programada_entrega) : NaN
  if (!Number.isFinite(llegada)) return 'EN_TRANSITO'
  const horasDeMas = (Date.now() - llegada) / 3_600_000
  if (horasDeMas > 6) return 'EN_RIESGO'
  if (horasDeMas > 0) return 'DEMORADO'
  return 'EN_TRANSITO'
}

// ─── Sub-components ───────────────────────────────────────────────────────────

const KPICard = ({ label, value, icon, color, sub }: KPI) => (
  <Paper elevation={0} className="hover-lift" sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 2.5, height: '100%' }}>
    <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
      <Box>
        <Typography className="text-gradient" fontSize={28} fontWeight={800} color={color} lineHeight={1} sx={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
        <Typography fontSize={12} color="text.secondary" mt={0.5}>{label}</Typography>
        {sub && <Typography fontSize={11} color="text.secondary" mt={0.25}>{sub}</Typography>}
      </Box>
      <Box sx={{ width: 40, height: 40, borderRadius: '10px', bgcolor: alpha(color, 0.1), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {React.cloneElement(icon as React.ReactElement, { sx: { fontSize: 20, color } })}
      </Box>
    </Stack>
  </Paper>
)

const estadoChip = (estado: 'EN_TRANSITO' | 'DEMORADO' | 'EN_RIESGO') => {
  const map = {
    EN_TRANSITO: { label: 'En Tránsito', color: '#0369A1', bg: '#E0F2FE' },
    DEMORADO: { label: 'Demorado', color: '#B45309', bg: '#FEF3C7' },
    EN_RIESGO: { label: 'En Riesgo', color: '#B91C1C', bg: '#FEE2E2' },
  }
  const s = map[estado]
  return <Chip label={s.label} size="small" sx={{ bgcolor: s.bg, color: s.color, fontWeight: 700, fontSize: 11 }} />
}

const nivelColor = (nivel: Alerta['nivel']) => {
  if (nivel === 'CRITICA') return { icon: '#DC2626', bg: '#FEF2F2', border: '#FECACA' }
  if (nivel === 'ALTA') return { icon: '#D97706', bg: '#FFFBEB', border: '#FDE68A' }
  return { icon: '#2563EB', bg: '#EFF6FF', border: '#BFDBFE' }
}

const otifChip = (viaje: Viaje) => {
  // Tarde manda sobre incompleta: si llegó tarde Y sin todo, lo primero que hay
  // que resolver es el atraso.
  const s = viaje.otif_on_time === false
    ? { label: 'TARDE', color: '#B91C1C', bg: '#FEE2E2' }
    : viaje.otif_in_full === false
    ? { label: 'INCOMPLETA', color: '#C2410C', bg: '#FFEDD5' }
    : { label: 'ON TIME', color: '#15803D', bg: '#DCFCE7' }
  return <Chip label={s.label} size="small" sx={{ bgcolor: s.bg, color: s.color, fontWeight: 700, fontSize: 10 }} />
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function TMSDashboard() {
  const navegar = useNavigate()
  const qc = useQueryClient()

  // Atender una alerta es dos cosas a la vez: ir a ver de qué se trata y dejar
  // de verla en la lista. Antes el botón guardaba el id en un estado que nadie
  // leía —`const [, setSelectedAlerta]`—, así que no hacía absolutamente nada.
  const marcarLeida = useMutation({
    mutationFn: (id: number) => api.put(`/tms/alertas/${id}/leer`),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['tms-alertas'] })
      qc.invalidateQueries({ queryKey: ['tms-kpis'] })
    },
  })

  const atender = (alerta: Alerta) => {
    marcarLeida.mutate(alerta.id)
    if (alerta.viaje_codigo) {
      navegar(`/tms/viajes?q=${encodeURIComponent(alerta.viaje_codigo)}`)
    } else if (alerta.conductor_id) {
      navegar('/tms/conductores')
    } else if (alerta.vehiculo_placa) {
      navegar(`/tms/vehiculos?q=${encodeURIComponent(alerta.vehiculo_placa)}`)
    }
  }

  // Se refresca solo: esto es una torre de control y el rótulo dice «en vivo».
  const { data: kpi } = useQuery<KPIs>({
    queryKey: ['tms-kpis'],
    queryFn: () => api.get('/tms/dashboard/kpis').then((r: { data: KPIs }) => r.data),
    refetchInterval: 60_000,
  })

  const { data: enTransito } = useQuery<Viaje[]>({
    queryKey: ['tms-viajes-transito'],
    queryFn: () => api.get('/tms/viajes',
      { params: { estado: 'EN_TRANSITO', per_page: 20 } })
      .then((r: { data: unknown }) => listaDe<Viaje>(r.data)),
    refetchInterval: 60_000,
  })

  const { data: alertas } = useQuery<Alerta[]>({
    queryKey: ['tms-alertas'],
    queryFn: () => api.get('/tms/alertas', { params: { leida: false } })
      .then((r: { data: unknown }) => listaDe<Alerta>(r.data)),
    refetchInterval: 60_000,
  })

  const { data: entregados } = useQuery<Viaje[]>({
    queryKey: ['tms-entregados'],
    queryFn: () => api.get('/tms/viajes',
      { params: { estado: 'ENTREGADO', per_page: 20 } })
      .then((r: { data: unknown }) => listaDe<Viaje>(r.data)),
  })

  const viajes = enTransito ?? []
  // Las alertas que importan primero. El API ya devuelve solo las no leídas.
  const avisos = (alertas ?? [])
    .filter(a => a.nivel === 'CRITICA' || a.nivel === 'ALTA' || a.nivel === 'MEDIA')
    .slice(0, 8)
  const criticalCount = kpi?.alertas_criticas ?? 0

  // Las entregas de hoy. Si hoy todavía no hay ninguna, se muestran las últimas
  // que hubo: una torre de control a las siete de la mañana no puede quedarse en
  // blanco hasta que llegue el primer camión.
  const hoy = new Date().toDateString()
  const deHoy = (entregados ?? []).filter(
    v => v.fecha_real_entrega && aFecha(v.fecha_real_entrega).toDateString() === hoy)
  const entregas = (deHoy.length ? deHoy : (entregados ?? [])).slice(0, 8)
  const tituloEntregas = deHoy.length ? 'Entregas Completadas Hoy' : 'Últimas Entregas'

  const sinEntregas = kpi != null && (kpi.entregados_mes ?? 0) === 0
  const kpis: KPI[] = [
    { label: 'Viajes en Tránsito', value: kpi?.viajes_en_transito ?? 0, icon: <LocalShipping />, color: TMS_COLOR },
    { label: 'Viajes Programados Hoy', value: kpi?.viajes_hoy ?? 0, icon: <EventNote />, color: '#7C3AED' },
    { label: 'Vehículos Activos', value: kpi?.vehiculos_activos ?? 0, icon: <DirectionsBus />, color: '#0891B2' },
    { label: 'Conductores en Ruta', value: kpi?.conductores_activos ?? 0, icon: <PersonPin />, color: '#059669' },
    { label: 'OTIF Rate', value: sinEntregas ? 'Sin datos' : `${(kpi?.otif_rate ?? 0).toFixed(1)}%`, icon: <CheckCircle />,
      color: sinEntregas ? '#94A3B8' : (kpi?.otif_rate ?? 0) >= 95 ? '#16A34A' : '#D97706',
      sub: sinEntregas ? 'Sin viajes entregados este mes' : `Meta: ≥95% · ${kpi?.entregados_mes} entregas` },
    { label: 'On Time Rate', value: sinEntregas ? 'Sin datos' : `${(kpi?.on_time_rate ?? 0).toFixed(1)}%`, icon: <Schedule />,
      color: sinEntregas ? '#94A3B8' : '#0369A1', sub: 'Este mes' },
    { label: 'Costo/Km Promedio', value: pesos(kpi?.costo_promedio_km ?? 0), icon: <AttachMoney />, color: '#92400E', sub: 'COP/km' },
    { label: 'Alertas Críticas', value: criticalCount, icon: <Warning />, color: criticalCount > 0 ? '#DC2626' : '#16A34A', sub: criticalCount > 0 ? 'Requieren atención' : 'Sin alertas' },
  ]

  return (
    <Layout>
      <Box sx={{ p: 3, maxWidth: 1600, mx: 'auto' }}>
        {/* Header */}
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
          <Box>
            <Typography variant="h5" fontWeight={800} color={TMS_COLOR}>Torre de Control TMS</Typography>
            <Typography variant="body2" color="text.secondary">
              Monitoreo en tiempo real del transporte — {new Date().toLocaleDateString('es-CO', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </Typography>
          </Box>
          <Chip
            icon={<Circle sx={{ fontSize: '10px !important', color: '#16A34A !important' }} />}
            label="EN VIVO"
            size="small"
            sx={{ bgcolor: '#DCFCE7', color: '#16A34A', fontWeight: 700, fontSize: 11 }}
          />
        </Stack>

        {/* KPIs */}
        <Grid container spacing={2} mb={3} className="anim-stagger">
          {kpis.map((kpi, i) => (
            <Grid key={i} size={{ xs: 12, sm: 6, md: 3 }}>
              <KPICard {...kpi} />
            </Grid>
          ))}
        </Grid>

        {/* Main content: Viajes Activos + Alertas */}
        <Grid container spacing={2} mb={2}>
          {/* Tabla de Viajes Activos */}
          <Grid size={{ xs: 12, md: 7 }}>
            <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', overflow: 'hidden' }}>
              <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid #F3F4F6' }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography fontWeight={700} fontSize={15}>Viajes Activos</Typography>
                  <Chip label={`${viajes.length} viajes`} size="small" sx={{ bgcolor: alpha(TMS_COLOR, 0.1), color: TMS_COLOR, fontWeight: 600 }} />
                </Stack>
              </Box>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Código</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Ruta</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Conductor</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Placa</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Estado</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>ETA</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>% Comp.</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {viajes.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary', fontSize: 13 }}>
                          Ningún viaje en tránsito en este momento
                        </TableCell>
                      </TableRow>
                    )}
                    {viajes.map((v) => {
                      const estado = situacion(v)
                      const pct = avance(v)
                      return (
                      <TableRow key={v.id} hover>
                        <TableCell><Typography fontSize={12} fontWeight={600} color={TMS_COLOR}>{v.codigo}</Typography></TableCell>
                        <TableCell>
                          <Typography fontSize={12}>{v.origen_ciudad ?? '—'}</Typography>
                          <Typography fontSize={11} color="text.secondary">→ {v.destino_ciudad ?? '—'}</Typography>
                        </TableCell>
                        <TableCell><Typography fontSize={12}>{v.conductor_nombre ?? '—'}</Typography></TableCell>
                        <TableCell><Chip label={v.vehiculo_placa ?? '—'} size="small" sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 11 }} /></TableCell>
                        <TableCell>{estadoChip(estado)}</TableCell>
                        <TableCell><Typography fontSize={12} fontWeight={600}>{hora(v.fecha_programada_entrega)}</Typography></TableCell>
                        <TableCell>
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <Box sx={{ flex: 1, height: 6, bgcolor: '#E5E7EB', borderRadius: 3, overflow: 'hidden' }}>
                              <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: estado === 'EN_RIESGO' ? '#DC2626' : estado === 'DEMORADO' ? '#D97706' : TMS_COLOR, borderRadius: 3 }} />
                            </Box>
                            <Typography fontSize={11} fontWeight={600}>{pct}%</Typography>
                          </Stack>
                        </TableCell>
                      </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Grid>

          {/* Panel de Alertas */}
          <Grid size={{ xs: 12, md: 5 }}>
            <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', overflow: 'hidden', height: '100%' }}>
              <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid #F3F4F6' }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography fontWeight={700} fontSize={15}>Alertas Activas</Typography>
                  <Chip label={`${criticalCount} críticas`} size="small" sx={{ bgcolor: '#FEE2E2', color: '#DC2626', fontWeight: 700 }} />
                </Stack>
              </Box>
              <Stack spacing={0} divider={<Divider />}>
                {avisos.length === 0 && (
                  <Box sx={{ px: 2, py: 4, textAlign: 'center', color: 'text.secondary', fontSize: 13 }}>
                    Sin alertas sin leer
                  </Box>
                )}
                {avisos.map((alerta) => {
                  const c = nivelColor(alerta.nivel as 'CRITICA' | 'ALTA' | 'MEDIA')
                  return (
                    <Box key={alerta.id} sx={{ px: 2, py: 1.5, bgcolor: c.bg, borderLeft: `3px solid ${c.icon}` }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                        <Box flex={1}>
                          <Stack direction="row" alignItems="center" spacing={0.5} mb={0.25}>
                            <Warning sx={{ fontSize: 14, color: c.icon }} />
                            <Chip label={alerta.nivel} size="small" sx={{ bgcolor: 'transparent', color: c.icon, fontWeight: 800, fontSize: 10, border: `1px solid ${c.icon}`, height: 18 }} />
                            {alerta.viaje_codigo && <Typography fontSize={11} color="text.secondary">{alerta.viaje_codigo}</Typography>}
                          </Stack>
                          <Typography fontSize={12}>{alerta.mensaje}</Typography>
                        </Box>
                        <Button size="small" variant="outlined" sx={{ fontSize: 11, py: 0.25, px: 1, minWidth: 'auto', borderColor: c.icon, color: c.icon, '&:hover': { borderColor: c.icon, bgcolor: alpha(c.icon, 0.08) } }} onClick={() => atender(alerta)}>
                          Ver
                        </Button>
                      </Stack>
                    </Box>
                  )
                })}
              </Stack>
            </Paper>
          </Grid>
        </Grid>

        {/* Últimas Entregas */}
        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', overflow: 'hidden' }}>
          <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid #F3F4F6' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography fontWeight={700} fontSize={15}>{tituloEntregas}</Typography>
              <Stack direction="row" spacing={1}>
                <Chip label={`${entregas.filter(e => e.otif_on_time !== false).length} On Time`} size="small" sx={{ bgcolor: '#DCFCE7', color: '#15803D', fontWeight: 700, fontSize: 11 }} />
                <Chip label={`${entregas.filter(e => e.otif_on_time === false).length} Tarde`} size="small" sx={{ bgcolor: '#FEE2E2', color: '#B91C1C', fontWeight: 700, fontSize: 11 }} />
              </Stack>
            </Stack>
          </Box>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                  <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Viaje</TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Carga</TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Destino</TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Hora Entrega</TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>OTIF</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entregas.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary', fontSize: 13 }}>
                      Todavía no hay entregas registradas
                    </TableCell>
                  </TableRow>
                )}
                {entregas.map((e) => (
                  <TableRow key={e.id} hover>
                    <TableCell><Typography fontSize={12} fontWeight={600} color={TMS_COLOR}>{e.codigo}</Typography></TableCell>
                    <TableCell><Typography fontSize={12}>{e.descripcion_carga ?? '—'}</Typography></TableCell>
                    <TableCell><Typography fontSize={12}>{e.destino_ciudad ?? '—'}</Typography></TableCell>
                    <TableCell><Typography fontSize={12} fontWeight={600}>{hora(e.fecha_real_entrega)}</Typography></TableCell>
                    <TableCell>{otifChip(e)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Box>
    </Layout>
  )
}
