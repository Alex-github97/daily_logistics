import React from 'react'
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  Chip,
  Stack,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  alpha,
  LinearProgress,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  Inventory2,
  LocalShipping,
  CheckCircle,
  WarningAmber,
  MoveToInbox,
  OutboundOutlined,
  Engineering,
  TrendingUp,
  Warehouse,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { apiClient as api } from '@/api/client'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const WMS_COLOR = COLOR_MODULO

// ─── Types ───────────────────────────────────────────────────────────────────

interface WMSKPIs {
  ot_pct: number
  if_pct: number
  otif_pct: number
  perfect_order_rate: number
  fill_rate: number
  inventory_accuracy: number
  ordenes_entregadas_total?: number
  ordenes_on_time?: number
  ordenes_in_full?: number
  ordenes_otif?: number
  otif_base?: number
  ordenes_perfect?: number
  perfect_base?: number
  unidades_solicitadas?: number
  unidades_despachadas?: number
  ubicaciones_contadas?: number
  ubicaciones_correctas?: number
  pending_recepciones: number
  pending_ordenes_salida: number
  ordenes_por_estado: Record<string, number>
  urgent_recepciones?: number
  priority_breakdown?: { alta: number; media: number; baja: number }
  active_pickers?: number
  active_picking_tasks?: number
  recent_ordenes_compra?: OrdenCompra[]
  recent_ordenes_salida?: OrdenSalida[]
}

interface WMSAlert {
  id: number
  tipo: string
  mensaje: string
  severidad: 'error' | 'warning' | 'info'
  fecha: string
}

interface OrdenCompra {
  id: number
  numero_oc: string
  proveedor_nombre: string
  estado: string
  fecha_esperada: string
}

interface OrdenSalida {
  id: number
  numero_orden: string
  cliente_nombre: string
  estado: string
  prioridad: string
}

// ─── Helper: KPI colour ───────────────────────────────────────────────────────

function kpiColor(value: number, greenThreshold = 95, yellowThreshold = 85) {
  if (value >= greenThreshold) return '#16A34A'
  if (value >= yellowThreshold) return '#D97706'
  return '#DC2626'
}

// ─── Local sub-components ─────────────────────────────────────────────────────

interface KPICardProps {
  label: string
  value: number
  target?: number
  icon: React.ReactElement
  greenAt?: number
  yellowAt?: number
  /** Cuántos casos entran en el cálculo; con 0 no hay dato (no es un 0 %). */
  base?: number
  /** «12 de 15 órdenes»: de dónde sale el número. */
  detalle?: string
  /** Qué falta para que el indicador tenga datos. */
  sinDatos?: string
}

function KPICard({ label, value, target = 100, icon, greenAt = 95, yellowAt = 85, base, detalle, sinDatos }: KPICardProps) {
  const vacio = base === 0
  const color = vacio ? '#94A3B8' : kpiColor(value, greenAt, yellowAt)
  const pct = vacio ? 0 : Math.min(value, 100)

  return (
    <Paper
      elevation={0}
      className="hover-lift"
      sx={{
        border: '1px solid #E5E7EB',
        borderRadius: '14px',
        p: 2.5,
        height: '100%',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Box>
          <Typography className={vacio ? undefined : 'text-gradient'} fontSize={vacio ? 26 : 40} fontWeight={800} color={color} lineHeight={vacio ? 1.55 : 1} sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {vacio ? 'Sin datos' : `${value.toFixed(1)}%`}
          </Typography>
          <Typography fontSize={12} color="text.secondary" mt={0.5}>
            {label}
          </Typography>
          <Typography fontSize={11} color="text.disabled" mt={0.25}>
            {vacio ? (sinDatos ?? 'Aún no hay operaciones para calcularlo') : `Meta: ${target}%${detalle ? ` · ${detalle}` : ''}`}
          </Typography>
        </Box>
        <Box
          sx={{
            width: 44,
            height: 44,
            borderRadius: '11px',
            bgcolor: alpha(color, 0.1),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          {React.cloneElement(icon, { sx: { fontSize: 22, color } })}
        </Box>
      </Stack>

      {/* Progress bar at bottom */}
      <Box sx={{ position: 'absolute', bottom: 0, left: 0, right: 0 }}>
        <LinearProgress
          variant="determinate"
          value={pct}
          sx={{
            height: 4,
            borderRadius: 0,
            bgcolor: alpha(color, 0.15),
            '& .MuiLinearProgress-bar': { bgcolor: color },
          }}
        />
      </Box>
    </Paper>
  )
}

interface StatCardProps {
  label: string
  count: number
  icon: React.ReactElement
  color: string
  sublabel?: string
  urgent?: boolean
}

function StatCard({ label, count, icon, color, sublabel, urgent }: StatCardProps) {
  return (
    <Paper
      elevation={0}
      sx={{
        border: `1px solid ${urgent ? '#FCA5A5' : '#E5E7EB'}`,
        borderRadius: '14px',
        p: 2.5,
        height: '100%',
        bgcolor: urgent ? alpha('#DC2626', 0.03) : 'background.paper',
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Box>
          <Typography fontSize={36} fontWeight={800} color={color}>
            {count}
          </Typography>
          <Typography fontSize={13} fontWeight={600} color="text.primary" mt={0.25}>
            {label}
          </Typography>
          {sublabel && (
            <Typography fontSize={11} color="text.secondary" mt={0.25}>
              {sublabel}
            </Typography>
          )}
        </Box>
        <Box
          sx={{
            width: 44,
            height: 44,
            borderRadius: '11px',
            bgcolor: alpha(color, 0.1),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          {React.cloneElement(icon, { sx: { fontSize: 22, color } })}
        </Box>
      </Stack>
      {urgent && (
        <Chip
          label="URGENTE"
          size="small"
          color="error"
          sx={{ mt: 1, fontSize: 10, height: 20, fontWeight: 700 }}
        />
      )}
    </Paper>
  )
}

// ─── Estado chips ─────────────────────────────────────────────────────────────

const OC_ESTADO_COLORS: Record<string, 'default' | 'primary' | 'warning' | 'success' | 'error'> = {
  PENDIENTE: 'primary',
  PARCIAL: 'warning',
  COMPLETA: 'success',
  CANCELADA: 'default',
}

const ORDEN_PRIORIDAD_COLORS: Record<string, 'default' | 'error' | 'warning' | 'info'> = {
  ALTA: 'error',
  MEDIA: 'warning',
  BAJA: 'info',
}

function EstadoChip({ estado }: { estado: string }) {
  return (
    <Chip
      label={estado}
      size="small"
      color={OC_ESTADO_COLORS[estado] ?? 'default'}
      sx={{ fontSize: 11, fontWeight: 600 }}
    />
  )
}

function PrioridadChip({ prioridad }: { prioridad: string }) {
  return (
    <Chip
      label={prioridad}
      size="small"
      color={ORDEN_PRIORIDAD_COLORS[prioridad] ?? 'default'}
      sx={{ fontSize: 11, fontWeight: 600 }}
    />
  )
}

// ─── Skeleton KPI row ─────────────────────────────────────────────────────────

function SkeletonKPI() {
  return (
    <Paper
      elevation={0}
      sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 2.5, height: '100%' }}
    >
      <Box sx={{ bgcolor: '#F3F4F6', height: 40, borderRadius: 1, mb: 1, width: '60%' }} />
      <Box sx={{ bgcolor: '#F3F4F6', height: 14, borderRadius: 1, width: '80%' }} />
    </Paper>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WMSDashboard() {
  const {
    data: kpis,
    isLoading,
    error,
  } = useQuery<WMSKPIs>({
    queryKey: ['wms-kpis'],
    queryFn: () => api.get('/wms/dashboard/kpis').then((r) => r.data),
    refetchInterval: 60_000,
  })

  const { data: alertas } = useQuery<WMSAlert[]>({
    queryKey: ['wms-alertas'],
    queryFn: () => api.get('/wms/dashboard/alertas').then((r) => r.data),
    refetchInterval: 60_000,
  })

  const recentOC: OrdenCompra[] = kpis?.recent_ordenes_compra ?? []
  const recentOS: OrdenSalida[] = kpis?.recent_ordenes_salida ?? []

  return (
    <Layout title="WMS — Dashboard Ejecutivo">
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>

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
            <Warehouse sx={{ color: WMS_COLOR, fontSize: 22 }} />
          </Box>
          <Box>
            <Typography fontSize={22} fontWeight={800} color="text.primary">
              WMS Dashboard
            </Typography>
            <Typography fontSize={12} color="text.secondary">
              Indicadores logísticos en tiempo real
            </Typography>
          </Box>
        </Stack>

        {/* Alerts */}
        {alertas && alertas.length > 0 && (
          <Stack spacing={1}>
            {alertas.slice(0, 3).map((a) => (
              <Alert key={a.id} severity={a.severidad} sx={{ py: 0.5, fontSize: 13 }}>
                {a.mensaje}
              </Alert>
            ))}
          </Stack>
        )}

        {error && (
          <Alert severity="error">
            No se pudieron cargar los KPIs. Verifique la conexión con el servidor.
          </Alert>
        )}

        {/* ── Row 1: KPI Cards (entrada escalonada) ─────────────────────── */}
        <Box>
          <Typography fontSize={13} fontWeight={700} color="text.secondary" mb={1.5} sx={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Indicadores de Servicio
          </Typography>
          <Grid container spacing={2} className="anim-stagger">
            {/* OT% */}
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
              {isLoading ? (
                <SkeletonKPI />
              ) : (
                <KPICard
                  label="On-Time Delivery (OT%)"
                  base={kpis?.ordenes_entregadas_total} detalle={`${kpis?.ordenes_on_time ?? 0} de ${kpis?.ordenes_entregadas_total ?? 0} entregas`}
                  sinDatos="Sin órdenes entregadas en los últimos 90 días"
                  value={kpis?.ot_pct ?? 0}
                  icon={<LocalShipping />}
                />
              )}
            </Grid>

            {/* IF% */}
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
              {isLoading ? (
                <SkeletonKPI />
              ) : (
                <KPICard
                  label="In-Full Delivery (IF%)"
                  base={kpis?.ordenes_entregadas_total} detalle={`${kpis?.ordenes_in_full ?? 0} de ${kpis?.ordenes_entregadas_total ?? 0} completas`}
                  sinDatos="Sin órdenes entregadas en los últimos 90 días"
                  value={kpis?.if_pct ?? 0}
                  icon={<Inventory2 />}
                />
              )}
            </Grid>

            {/* OTIF% */}
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
              {isLoading ? (
                <SkeletonKPI />
              ) : (
                <KPICard
                  label="OTIF%"
                  base={kpis?.otif_base} detalle={`${kpis?.ordenes_otif ?? 0} de ${kpis?.otif_base ?? 0} órdenes`}
                  sinDatos="Sin órdenes entregadas con fecha requerida"
                  value={kpis?.otif_pct ?? 0}
                  icon={<CheckCircle />}
                />
              )}
            </Grid>

            {/* Perfect Order Rate */}
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
              {isLoading ? (
                <SkeletonKPI />
              ) : (
                <KPICard
                  label="Perfect Order Rate"
                  base={kpis?.perfect_base} detalle={`${kpis?.ordenes_perfect ?? 0} de ${kpis?.perfect_base ?? 0} órdenes`}
                  sinDatos="Sin órdenes entregadas con fecha requerida"
                  value={kpis?.perfect_order_rate ?? 0}
                  icon={<TrendingUp />}
                />
              )}
            </Grid>

            {/* Fill Rate */}
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
              {isLoading ? (
                <SkeletonKPI />
              ) : (
                <KPICard
                  label="Fill Rate"
                  base={kpis?.unidades_solicitadas} detalle={`${Math.round(kpis?.unidades_despachadas ?? 0).toLocaleString('es-CO')} de ${Math.round(kpis?.unidades_solicitadas ?? 0).toLocaleString('es-CO')} und`}
                  sinDatos="Sin órdenes despachadas en el período"
                  value={kpis?.fill_rate ?? 0}
                  icon={<OutboundOutlined />}
                  greenAt={98}
                  yellowAt={90}
                />
              )}
            </Grid>

            {/* Inventory Accuracy */}
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
              {isLoading ? (
                <SkeletonKPI />
              ) : (
                <KPICard
                  label="Inventory Accuracy"
                  base={kpis?.ubicaciones_contadas} detalle={`${kpis?.ubicaciones_correctas ?? 0} de ${kpis?.ubicaciones_contadas ?? 0} posiciones`}
                  sinDatos="Sin conteos de inventario completados (WMS › Inventario › Conteos)"
                  value={kpis?.inventory_accuracy ?? 0}
                  icon={<WarningAmber />}
                  greenAt={99}
                  yellowAt={95}
                />
              )}
            </Grid>
          </Grid>
        </Box>

        {/* ── Row 2: Stat Cards ──────────────────────────────────────────── */}
        <Box>
          <Typography fontSize={13} fontWeight={700} color="text.secondary" mb={1.5} sx={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Estado Operacional
          </Typography>
          {isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress size={32} sx={{ color: WMS_COLOR }} />
            </Box>
          ) : (
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 4 }}>
                <StatCard
                  label="Recepciones Pendientes"
                  count={kpis?.pending_recepciones ?? 0}
                  icon={<MoveToInbox />}
                  color={WMS_COLOR}
                  sublabel="Órdenes de compra por recibir"
                  urgent={(kpis?.urgent_recepciones ?? 0) > 0}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 4 }}>
                <StatCard
                  label="Órdenes de Salida Pendientes"
                  count={kpis?.pending_ordenes_salida ?? 0}
                  icon={<OutboundOutlined />}
                  color="#7C3AED"
                  sublabel={
                    kpis?.priority_breakdown
                      ? `Alta: ${kpis.priority_breakdown.alta} · Media: ${kpis.priority_breakdown.media} · Baja: ${kpis.priority_breakdown.baja}`
                      : 'Pendientes de despacho'
                  }
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 4 }}>
                <StatCard
                  label="Tareas de Picking Activas"
                  count={kpis?.active_picking_tasks ?? 0}
                  icon={<Engineering />}
                  color="#0891B2"
                  sublabel={
                    kpis?.active_pickers !== undefined
                      ? `${kpis.active_pickers} operario(s) en curso`
                      : 'En proceso'
                  }
                />
              </Grid>
            </Grid>
          )}
        </Box>

        {/* ── Row 3: Recent orders tables ───────────────────────────────── */}
        <Grid container spacing={2}>
          {/* Recent inbound OCs */}
          <Grid size={{ xs: 12, md: 6 }}>
            <Card elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', height: '100%' }}>
              <CardContent sx={{ p: 0 }}>
                <Box sx={{ px: 2.5, pt: 2.5, pb: 1.5 }}>
                  <Typography fontWeight={700} fontSize={14}>
                    Órdenes de Compra Recientes
                  </Typography>
                  <Typography fontSize={12} color="text.secondary">
                    Últimas recepciones programadas
                  </Typography>
                </Box>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ '& th': { fontSize: 11, fontWeight: 700, color: 'text.secondary', py: 1 } }}>
                        <TableCell>N° OC</TableCell>
                        <TableCell>Proveedor</TableCell>
                        <TableCell>Estado</TableCell>
                        <TableCell>Fecha Esp.</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {isLoading
                        ? Array.from({ length: 5 }).map((_, i) => (
                            <TableRow key={i}>
                              {Array.from({ length: 4 }).map((_, j) => (
                                <TableCell key={j}>
                                  <Box sx={{ bgcolor: '#F3F4F6', height: 14, borderRadius: 1 }} />
                                </TableCell>
                              ))}
                            </TableRow>
                          ))
                        : recentOC.length === 0
                        ? (
                          <TableRow>
                            <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary', fontSize: 13 }}>
                              Sin órdenes recientes
                            </TableCell>
                          </TableRow>
                        )
                        : recentOC.map((oc) => (
                          <TableRow key={oc.id} hover sx={{ '& td': { fontSize: 12, py: 1 } }}>
                            <TableCell sx={{ fontWeight: 600, color: WMS_COLOR }}>{oc.numero_oc}</TableCell>
                            <TableCell>{oc.proveedor_nombre}</TableCell>
                            <TableCell>
                              <EstadoChip estado={oc.estado} />
                            </TableCell>
                            <TableCell>
                              {oc.fecha_esperada
                                ? format(aFecha(oc.fecha_esperada), 'dd MMM', { locale: es })
                                : '—'}
                            </TableCell>
                          </TableRow>
                        ))
                      }
                    </TableBody>
                  </Table>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Recent outbound orders */}
          <Grid size={{ xs: 12, md: 6 }}>
            <Card elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', height: '100%' }}>
              <CardContent sx={{ p: 0 }}>
                <Box sx={{ px: 2.5, pt: 2.5, pb: 1.5 }}>
                  <Typography fontWeight={700} fontSize={14}>
                    Órdenes de Salida Recientes
                  </Typography>
                  <Typography fontSize={12} color="text.secondary">
                    Últimos despachos y entregas
                  </Typography>
                </Box>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ '& th': { fontSize: 11, fontWeight: 700, color: 'text.secondary', py: 1 } }}>
                        <TableCell>N° Orden</TableCell>
                        <TableCell>Cliente</TableCell>
                        <TableCell>Estado</TableCell>
                        <TableCell>Prioridad</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {isLoading
                        ? Array.from({ length: 5 }).map((_, i) => (
                            <TableRow key={i}>
                              {Array.from({ length: 4 }).map((_, j) => (
                                <TableCell key={j}>
                                  <Box sx={{ bgcolor: '#F3F4F6', height: 14, borderRadius: 1 }} />
                                </TableCell>
                              ))}
                            </TableRow>
                          ))
                        : recentOS.length === 0
                        ? (
                          <TableRow>
                            <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary', fontSize: 13 }}>
                              Sin órdenes recientes
                            </TableCell>
                          </TableRow>
                        )
                        : recentOS.map((os) => (
                          <TableRow key={os.id} hover sx={{ '& td': { fontSize: 12, py: 1 } }}>
                            <TableCell sx={{ fontWeight: 600, color: '#7C3AED' }}>{os.numero_orden}</TableCell>
                            <TableCell>{os.cliente_nombre}</TableCell>
                            <TableCell>
                              <EstadoChip estado={os.estado} />
                            </TableCell>
                            <TableCell>
                              <PrioridadChip prioridad={os.prioridad} />
                            </TableCell>
                          </TableRow>
                        ))
                      }
                    </TableBody>
                  </Table>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

      </Box>
    </Layout>
  )
}
