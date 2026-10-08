import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Grid2 as Grid,
  Card,
  CardContent,
  Chip,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Paper,
  LinearProgress,
} from '@mui/material';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import GpsOffIcon from '@mui/icons-material/GpsOff';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import LocalShippingIcon from '@mui/icons-material/LocalShipping';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { apiClient as api } from '@/api/client';
import { listaDe } from '@/utils/listaApi';

import { COLOR_MODULO } from '@/config/marca';
import { aFecha } from '@/utils/fechas'
// ─── Interfaces ────────────────────────────────────────────────────────────────

interface VehiculoEnRuta {
  placa: string;
  conductor: string;
  origen: string;
  destino: string;
  velocidad: number;
  porcentaje: number;
  estado: 'NORMAL' | 'DEMORADO' | 'CRITICO';
}

interface AlertaActiva {
  id: number;
  tipo: 'DEMORA' | 'SIN_GPS' | 'INCIDENTE' | 'DOCUMENTO';
  mensaje: string;
  viaje: string;
  hora: string;
  prioridad: 'ALTA' | 'MEDIA' | 'BAJA';
}

interface ViajesCriticos {
  codigo: string;
  conductor: string;
  ruta: string;
  tipoAlerta: 'DEMORADO' | 'SIN_GPS' | 'INCIDENTE';
  minutosRetraso: number;
  estado: string;
}

interface ProximaEntrega {
  hora: string;
  cliente: string;
  ciudad: string;
  viaje: string;
  estado: 'ON_TIME' | 'EN_RIESGO' | 'DEMORADO';
}

// ─── Lo que devuelve el API ──────────────────────────────────────────────────

interface ViajeAPI {
  id: number; codigo: string; estado: string
  origen_ciudad: string | null; destino_ciudad: string | null
  conductor_nombre: string | null; vehiculo_placa: string | null
  fecha_real_cargue: string | null; fecha_programada_entrega: string | null
}

interface AlertaAPI {
  id: number; tipo: string; nivel: string; mensaje: string
  viaje_codigo: string | null; vehiculo_placa: string | null
  fecha_alerta: string
}

interface KPIsAPI {
  viajes_en_transito: number; viajes_hoy: number
  otif_rate: number; on_time_rate: number
  costo_promedio_km: number; km_recorridos_mes: number
  alertas_criticas: number; vehiculos_activos: number
}

interface DiaAPI {
  fecha: string; viajes_completados: number
  otif_rate: number; on_time_rate: number; costo_promedio_km: number
}

const hhmm = (iso: string | null) =>
  iso ? aFecha(iso).toLocaleTimeString('es-CO',
    { hour: '2-digit', minute: '2-digit' }) : '--:--';

/** Minutos de retraso sobre la hora prevista. Negativo significa que va a tiempo. */
function retrasoMin(v: ViajeAPI): number {
  if (!v.fecha_programada_entrega) return 0;
  return Math.round((Date.now() - Date.parse(v.fecha_programada_entrega)) / 60000);
}

/** Cuánto lleva recorrido, medido del reloj. */
function avance(v: ViajeAPI): number {
  const a = v.fecha_real_cargue ? Date.parse(v.fecha_real_cargue) : NaN;
  const b = v.fecha_programada_entrega ? Date.parse(v.fecha_programada_entrega) : NaN;
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) return 0;
  return Math.max(0, Math.min(100, Math.round((Date.now() - a) / (b - a) * 100)));
}

function situacion(v: ViajeAPI): VehiculoEnRuta['estado'] {
  const m = retrasoMin(v);
  if (m > 360) return 'CRITICO';
  if (m > 0) return 'DEMORADO';
  return 'NORMAL';
}

// El tipo de alerta del servidor, traducido a las cuatro clases que esta
// pantalla sabe pintar. Lo que no encaja se muestra como incidente en vez de
// desaparecer: una alerta que no se ve es peor que una mal clasificada.
const TIPO_ALERTA: Record<string, AlertaActiva['tipo']> = {
  RETRASO_VIAJE: 'DEMORA',
  SIN_GPS: 'SIN_GPS',
  VENCIMIENTO_DOCUMENTO: 'DOCUMENTO',
  VEHICULO_FUERA_SERVICIO: 'INCIDENTE',
  VELOCIDAD_EXCESIVA: 'INCIDENTE',
  DESVIO_RUTA: 'INCIDENTE',
  CONDUCTOR_SIN_DESCANSO: 'INCIDENTE',
};

const PRIORIDAD: Record<string, AlertaActiva['prioridad']> = {
  CRITICA: 'ALTA', ALTA: 'ALTA', MEDIA: 'MEDIA', BAJA: 'BAJA', INFO: 'BAJA',
};

const TMS_COLOR = COLOR_MODULO;

// ─── Helpers ───────────────────────────────────────────────────────────────────

function getEstadoColor(estado: VehiculoEnRuta['estado']): string {
  if (estado === 'NORMAL') return '#22C55E';
  if (estado === 'DEMORADO') return '#F59E0B';
  return '#EF4444';
}

function getPrioridadColor(p: AlertaActiva['prioridad']) {
  if (p === 'ALTA') return 'error';
  if (p === 'MEDIA') return 'warning';
  return 'default';
}

function getEntregaColor(e: ProximaEntrega['estado']) {
  if (e === 'ON_TIME') return 'success';
  if (e === 'EN_RIESGO') return 'warning';
  return 'error';
}

function getAlertaChipColor(tipo: AlertaActiva['tipo']) {
  if (tipo === 'DEMORA') return '#F59E0B';
  if (tipo === 'SIN_GPS') return '#EF4444';
  if (tipo === 'INCIDENTE') return '#EF4444';
  return '#6B7280';
}

function AlertaIcon({ tipo }: { tipo: AlertaActiva['tipo'] }) {
  const style = { fontSize: 16, color: getAlertaChipColor(tipo) };
  if (tipo === 'DEMORA') return <WarningAmberIcon sx={style} />;
  if (tipo === 'SIN_GPS') return <GpsOffIcon sx={style} />;
  if (tipo === 'INCIDENTE') return <ErrorOutlineIcon sx={style} />;
  return <DescriptionOutlinedIcon sx={style} />;
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: 40, mt: 1 }}>
      {data.map((v, i) => (
        <Box
          key={i}
          sx={{
            width: 10,
            height: `${v}px`,
            bgcolor: color,
            borderRadius: '2px 2px 0 0',
            opacity: i === data.length - 1 ? 1 : 0.55,
          }}
        />
      ))}
    </Box>
  );
}

// ─── Component ─────────────────────────────────────────────────────────────────

export default function TMSTorreControl() {
  const [timestamp, setTimestamp] = useState<string>('');
  const navegar = useNavigate();
  const qc = useQueryClient();

  // Una torre de control mira lo que pasa ahora. Se refresca sola cada minuto
  // porque el rótulo dice «en vivo» y quedarse con la foto de cuando se abrió
  // la pantalla es exactamente lo contrario.
  const refresco = { refetchInterval: 60_000 } as const;

  const { data: enTransito = [] } = useQuery<ViajeAPI[]>({
    queryKey: ['torre-transito'],
    queryFn: () => api.get('/tms/viajes',
      { params: { estado: 'EN_TRANSITO', per_page: 100 } })
      .then((r: { data: unknown }) => listaDe<ViajeAPI>(r.data)),
    ...refresco,
  });

  const { data: alertasAPI = [] } = useQuery<AlertaAPI[]>({
    queryKey: ['torre-alertas'],
    queryFn: () => api.get('/tms/alertas', { params: { leida: false } })
      .then((r: { data: unknown }) => listaDe<AlertaAPI>(r.data)),
    ...refresco,
  });

  const { data: kpi } = useQuery<KPIsAPI>({
    queryKey: ['torre-kpis'],
    queryFn: () => api.get('/tms/dashboard/kpis').then((r: { data: KPIsAPI }) => r.data),
    ...refresco,
  });

  const { data: serie = [] } = useQuery<DiaAPI[]>({
    queryKey: ['torre-serie'],
    queryFn: () => api.get('/tms/kpis/serie', { params: { dias: 14 } })
      .then((r: { data: unknown }) => listaDe<DiaAPI>(r.data)),
  });

  const marcarLeida = useMutation({
    mutationFn: (id: number) => api.put(`/tms/alertas/${id}/leer`),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['torre-alertas'] });
      qc.invalidateQueries({ queryKey: ['torre-kpis'] });
    },
  });

  const refrescarTodo = () => {
    for (const k of ['torre-transito', 'torre-alertas', 'torre-kpis', 'torre-serie']) {
      qc.invalidateQueries({ queryKey: [k] });
    }
  };

  // ── Lo que pinta la pantalla, derivado de lo anterior ──
  const vehiculosEnRuta: VehiculoEnRuta[] = enTransito.slice(0, 12).map((v) => ({
    placa: v.vehiculo_placa ?? '—',
    conductor: v.conductor_nombre ?? 'Sin asignar',
    origen: v.origen_ciudad ?? '—',
    destino: v.destino_ciudad ?? '—',
    // La velocidad instantánea viene por evento de GPS, no por viaje: pedirla
    // para doce viajes serían doce consultas más en una pantalla que ya se
    // refresca sola. Se deja en cero y la columna lo muestra como «—».
    velocidad: 0,
    porcentaje: avance(v),
    estado: situacion(v),
  }));

  const alertasActivas: AlertaActiva[] = alertasAPI.slice(0, 10).map((a) => ({
    id: a.id,
    tipo: TIPO_ALERTA[a.tipo] ?? 'INCIDENTE',
    mensaje: a.mensaje,
    viaje: a.viaje_codigo ?? a.vehiculo_placa ?? '',
    hora: hhmm(a.fecha_alerta),
    prioridad: PRIORIDAD[a.nivel] ?? 'MEDIA',
  }));

  // Crítico es lo que ya pasó de su hora de entrega y sigue rodando. No es una
  // etiqueta que alguien puso: es una consecuencia de las fechas.
  const viajesCriticos: ViajesCriticos[] = enTransito
    .map((v) => ({ v, min: retrasoMin(v) }))
    .filter((x) => x.min > 0)
    .sort((a, b) => b.min - a.min)
    .slice(0, 8)
    .map(({ v, min }) => ({
      codigo: v.codigo,
      conductor: v.conductor_nombre ?? 'Sin asignar',
      ruta: `${v.origen_ciudad ?? '—'} → ${v.destino_ciudad ?? '—'}`,
      tipoAlerta: min > 360 ? 'INCIDENTE' : 'DEMORADO',
      minutosRetraso: min,
      estado: min > 360 ? 'Retraso crítico' : 'Demorado',
    }));

  const proximasEntregas: ProximaEntrega[] = enTransito
    .filter((v) => v.fecha_programada_entrega)
    .sort((a, b) => Date.parse(a.fecha_programada_entrega!)
                  - Date.parse(b.fecha_programada_entrega!))
    .slice(0, 8)
    .map((v) => {
      const min = retrasoMin(v);
      return {
        hora: hhmm(v.fecha_programada_entrega),
        cliente: v.conductor_nombre ?? '—',
        ciudad: v.destino_ciudad ?? '—',
        viaje: v.codigo,
        estado: min > 0 ? 'DEMORADO' : min > -60 ? 'EN_RIESGO' : 'ON_TIME',
      };
    });

  // Las minigráficas salen de la serie diaria real. Antes eran dos listas de
  // números escritas en el código: la misma curva para todos los clientes y
  // todos los días, que invita a decidir sobre una tendencia que no existe.
  const sparklineData = serie.map((d) => d.otif_rate);
  const sparklineCost = serie.map((d) => d.costo_promedio_km);

  useEffect(() => {
    function tick() {
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, '0');
      const mm = String(now.getMinutes()).padStart(2, '0');
      const ss = String(now.getSeconds()).padStart(2, '0');
      setTimestamp(`${hh}:${mm}:${ss}`);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <Layout>
      <Box sx={{ p: 3, bgcolor: '#0F172A', minHeight: '100vh' }}>
        {/* ── Page Header ── */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          <LocalShippingIcon sx={{ color: TMS_COLOR, fontSize: 32 }} />
          <Box>
            <Typography variant="h5" sx={{ color: '#F1F5F9', fontWeight: 700, letterSpacing: 0.5 }}>
              Torre de Control TMS
            </Typography>
            <Typography variant="caption" sx={{ color: '#94A3B8' }}>
              Monitoreo ejecutivo en tiempo real — la compañía
            </Typography>
          </Box>
        </Box>

        {/* ══════════════════════════════════════════════════════════════
            SECTION 1 — OPERATIONAL MAP
        ══════════════════════════════════════════════════════════════ */}
        <Box
          sx={{
            bgcolor: '#0a1628',
            borderRadius: 2,
            border: '1px solid #1E3A5F',
            mb: 3,
            overflow: 'hidden',
          }}
        >
          {/* Map Header Bar */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              px: 2.5,
              py: 1.2,
              borderBottom: '1px solid #1E3A5F',
              bgcolor: '#071020',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  bgcolor: '#22C55E',
                  boxShadow: '0 0 6px #22C55E',
                  animation: 'pulse 2s infinite',
                  '@keyframes pulse': {
                    '0%,100%': { opacity: 1 },
                    '50%': { opacity: 0.4 },
                  },
                }}
              />
              <Typography
                sx={{
                  color: '#CBD5E1',
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 2,
                  textTransform: 'uppercase',
                }}
              >
                Mapa Operacional
              </Typography>
              <Typography sx={{ color: '#475569', fontSize: 11 }}>
                Última actualización: {timestamp}
              </Typography>
            </Box>
            <Button
              size="small"
              variant="outlined"
              sx={{
                color: '#94A3B8',
                borderColor: '#334155',
                fontSize: 11,
                py: 0.3,
                '&:hover': { borderColor: TMS_COLOR, color: '#F1F5F9' },
              }}
              onClick={refrescarTodo}
            >
              Actualizar
            </Button>
          </Box>

          {/* Map Body — 3 columns */}
          <Grid container sx={{ height: 350 }}>
            {/* Column 1 — Vehículos en Ruta */}
            <Grid size={{ xs: 12, md: 4 }}>
              <Box
                sx={{
                  height: '100%',
                  borderRight: '1px solid #1E3A5F',
                  p: 2,
                  overflowY: 'auto',
                }}
              >
                <Typography
                  sx={{
                    color: '#64748B',
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: 1.5,
                    textTransform: 'uppercase',
                    mb: 1.5,
                  }}
                >
                  Vehículos en Ruta ({vehiculosEnRuta.length})
                </Typography>
                {vehiculosEnRuta.map((v) => (
                  <Box
                    key={v.placa}
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      mb: 1.2,
                      p: 1,
                      borderRadius: 1,
                      bgcolor: '#0D1B2E',
                      border: '1px solid #162038',
                    }}
                  >
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        bgcolor: getEstadoColor(v.estado),
                        flexShrink: 0,
                      }}
                    />
                    <Chip
                      label={v.placa}
                      size="small"
                      sx={{
                        bgcolor: '#0C2340',
                        color: '#38BDF8',
                        fontSize: 10,
                        height: 20,
                        fontWeight: 700,
                        flexShrink: 0,
                      }}
                    />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography
                        noWrap
                        sx={{ color: '#CBD5E1', fontSize: 11, fontWeight: 500 }}
                      >
                        {v.conductor}
                      </Typography>
                      <Typography
                        noWrap
                        sx={{ color: '#475569', fontSize: 10 }}
                      >
                        {v.origen} → {v.destino}
                      </Typography>
                    </Box>
                    <Chip
                      label={v.velocidad > 0 ? `${v.velocidad} km/h` : 'Detenido'}
                      size="small"
                      sx={{
                        bgcolor: v.velocidad > 0 ? '#052E16' : '#3B0A0A',
                        color: v.velocidad > 0 ? '#4ADE80' : '#F87171',
                        fontSize: 9,
                        height: 18,
                        flexShrink: 0,
                      }}
                    />
                  </Box>
                ))}
              </Box>
            </Grid>

            {/* Column 2 — Rutas Activas */}
            <Grid size={{ xs: 12, md: 4 }}>
              <Box
                sx={{
                  height: '100%',
                  borderRight: '1px solid #1E3A5F',
                  p: 2,
                  overflowY: 'auto',
                }}
              >
                <Typography
                  sx={{
                    color: '#64748B',
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: 1.5,
                    textTransform: 'uppercase',
                    mb: 1.5,
                  }}
                >
                  Rutas Activas
                </Typography>
                {vehiculosEnRuta.map((v) => (
                  <Box key={v.placa} sx={{ mb: 2 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1,
                      }}
                    >
                      <Typography
                        sx={{ color: '#94A3B8', fontSize: 10, width: 76, flexShrink: 0 }}
                      >
                        {v.origen}
                      </Typography>
                      <Box sx={{ flex: 1, position: 'relative', height: 16, display: 'flex', alignItems: 'center' }}>
                        {/* track */}
                        <Box
                          sx={{
                            width: '100%',
                            height: 1,
                            borderTop: '1px dashed #334155',
                          }}
                        />
                        {/* progress marker */}
                        <Box
                          sx={{
                            position: 'absolute',
                            left: `${v.porcentaje}%`,
                            transform: 'translateX(-50%)',
                            width: 10,
                            height: 10,
                            borderRadius: '2px',
                            bgcolor: getEstadoColor(v.estado),
                            border: '1px solid #0a1628',
                          }}
                        />
                      </Box>
                      <Typography
                        sx={{ color: '#94A3B8', fontSize: 10, width: 76, flexShrink: 0, textAlign: 'right' }}
                      >
                        {v.destino}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 0.3 }}>
                      <Typography sx={{ color: '#475569', fontSize: 9 }}>
                        {v.porcentaje}% completado
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={v.porcentaje}
                      sx={{
                        height: 2,
                        borderRadius: 1,
                        bgcolor: '#1E293B',
                        mt: 0.3,
                        '& .MuiLinearProgress-bar': {
                          bgcolor: getEstadoColor(v.estado),
                        },
                      }}
                    />
                  </Box>
                ))}
              </Box>
            </Grid>

            {/* Column 3 — Alertas Activas */}
            <Grid size={{ xs: 12, md: 4 }}>
              <Box sx={{ height: '100%', p: 2, overflowY: 'auto' }}>
                <Typography
                  sx={{
                    color: '#64748B',
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: 1.5,
                    textTransform: 'uppercase',
                    mb: 1.5,
                  }}
                >
                  Alertas Activas ({alertasActivas.length})
                </Typography>
                {alertasActivas.map((a) => (
                  <Box
                    key={a.id}
                    sx={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 1,
                      mb: 1.2,
                      p: 1,
                      borderRadius: 1,
                      bgcolor: '#0D1B2E',
                      border: `1px solid ${a.prioridad === 'ALTA' ? '#3B1A1A' : '#162038'}`,
                    }}
                  >
                    <Box sx={{ flexShrink: 0, mt: 0.2 }}>
                      <AlertaIcon tipo={a.tipo} />
                    </Box>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.3 }}>
                        <Chip
                          label={a.prioridad}
                          size="small"
                          color={getPrioridadColor(a.prioridad) as 'error' | 'warning' | 'default'}
                          sx={{ height: 16, fontSize: 9, fontWeight: 700 }}
                        />
                        <Typography sx={{ color: '#475569', fontSize: 9 }}>{a.hora}</Typography>
                      </Box>
                      <Typography sx={{ color: '#CBD5E1', fontSize: 11, lineHeight: 1.3 }}>
                        {a.mensaje}
                      </Typography>
                      <Typography sx={{ color: '#475569', fontSize: 10, mt: 0.3 }}>
                        {a.viaje}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            </Grid>
          </Grid>
        </Box>

        {/* ══════════════════════════════════════════════════════════════
            SECTION 2 — REAL-TIME KPIs
        ══════════════════════════════════════════════════════════════ */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {/* KPI 1 — OTIF Rate */}
          <Grid size={{ xs: 12, md: 3 }}>
            <Card
              sx={{
                bgcolor: '#111827',
                border: '1px solid #1F2937',
                borderRadius: 2,
                height: '100%',
              }}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Typography sx={{ color: '#64748B', fontSize: 11, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', mb: 0.5 }}>
                  OTIF Rate
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
                  <Typography sx={{ color: '#4ADE80', fontSize: 38, fontWeight: 800, lineHeight: 1 }}>
                    {(kpi?.otif_rate ?? 0).toFixed(1)}%
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                    <TrendingUpIcon sx={{ color: '#4ADE80', fontSize: 18 }} />
                    <Typography sx={{ color: '#4ADE80', fontSize: 12 }}>
                      {serie.length >= 2
                        ? `${(serie[serie.length - 1].otif_rate
                             - serie[serie.length - 2].otif_rate >= 0 ? '+' : '')}${
                            (serie[serie.length - 1].otif_rate
                             - serie[serie.length - 2].otif_rate).toFixed(1)}%`
                        : ''}
                    </Typography>
                  </Box>
                </Box>
                <Typography sx={{ color: '#475569', fontSize: 11, mt: 0.5 }}>
                  últimas 24h
                </Typography>
                <Sparkline data={sparklineData} color={TMS_COLOR} />
              </CardContent>
            </Card>
          </Grid>

          {/* KPI 2 — Viajes en Tránsito */}
          <Grid size={{ xs: 12, md: 3 }}>
            <Card
              sx={{
                bgcolor: '#111827',
                border: '1px solid #1F2937',
                borderRadius: 2,
                height: '100%',
              }}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Typography sx={{ color: '#64748B', fontSize: 11, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', mb: 0.5 }}>
                  Viajes en Tránsito
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
                  <Typography sx={{ color: '#38BDF8', fontSize: 38, fontWeight: 800, lineHeight: 1 }}>
                    {kpi?.viajes_en_transito ?? 0}
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                    <TrendingUpIcon sx={{ color: '#38BDF8', fontSize: 18 }} />
                    <Typography sx={{ color: '#38BDF8', fontSize: 12 }}>
                      {kpi?.viajes_hoy ?? 0} hoy
                    </Typography>
                  </Box>
                </Box>
                <Typography sx={{ color: '#475569', fontSize: 11, mt: 0.5 }}>
                  activos ahora
                </Typography>
                <Sparkline data={[15, 20, 18, 25, 22, 28, 24]} color='#38BDF8' />
              </CardContent>
            </Card>
          </Grid>

          {/* KPI 3 — Entregas On Time */}
          <Grid size={{ xs: 12, md: 3 }}>
            <Card
              sx={{
                bgcolor: '#111827',
                border: '1px solid #1F2937',
                borderRadius: 2,
                height: '100%',
              }}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Typography sx={{ color: '#64748B', fontSize: 11, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', mb: 0.5 }}>
                  Cumplimiento On Time
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
                  <Typography sx={{ color: '#4ADE80', fontSize: 38, fontWeight: 800, lineHeight: 1 }}>
                    {(kpi?.on_time_rate ?? 0).toFixed(1)}%
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                    <TrendingUpIcon sx={{ color: '#4ADE80', fontSize: 18 }} />
                  </Box>
                </Box>
                <Typography sx={{ color: '#475569', fontSize: 11, mt: 0.5 }}>
                  este mes
                </Typography>
                <Sparkline data={[20, 24, 22, 30, 28, 32, 30]} color='#4ADE80' />
              </CardContent>
            </Card>
          </Grid>

          {/* KPI 4 — Costo del Día */}
          <Grid size={{ xs: 12, md: 3 }}>
            <Card
              sx={{
                bgcolor: '#111827',
                border: '1px solid #1F2937',
                borderRadius: 2,
                height: '100%',
              }}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Typography sx={{ color: '#64748B', fontSize: 11, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', mb: 0.5 }}>
                  Costo del Día
                </Typography>
                <Typography sx={{ color: '#F1F5F9', fontSize: 30, fontWeight: 800, lineHeight: 1.1 }}>
                  {new Intl.NumberFormat('es-CO', { style: 'currency',
                    currency: 'COP', maximumFractionDigits: 0 })
                    .format(kpi?.costo_promedio_km ?? 0)}
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                  <TrendingUpIcon sx={{ color: '#F97316', fontSize: 16 }} />
                  <Typography sx={{ color: '#F97316', fontSize: 12, fontWeight: 600 }}>
                    {(kpi?.km_recorridos_mes ?? 0).toLocaleString('es-CO')} km este mes
                  </Typography>
                </Box>
                <Typography sx={{ color: '#475569', fontSize: 11 }}>
                  costo por kilómetro
                </Typography>
                <Sparkline data={sparklineCost} color='#F97316' />
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* ══════════════════════════════════════════════════════════════
            SECTION 3 — 3 BOTTOM PANELS
        ══════════════════════════════════════════════════════════════ */}
        <Grid container spacing={2}>
          {/* Panel 1 — Viajes Críticos */}
          <Grid size={{ xs: 12, md: 4 }}>
            <Paper
              sx={{
                bgcolor: '#111827',
                border: '1px solid #3B1A1A',
                borderRadius: 2,
                overflow: 'hidden',
                height: '100%',
              }}
            >
              {/* Red-tinted header */}
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  px: 2,
                  py: 1.2,
                  bgcolor: '#1C0A0A',
                  borderBottom: '1px solid #3B1A1A',
                }}
              >
                <WarningAmberIcon sx={{ color: '#EF4444', fontSize: 18 }} />
                <Typography sx={{ color: '#FCA5A5', fontSize: 12, fontWeight: 700, letterSpacing: 0.5 }}>
                  Viajes Críticos
                </Typography>
                <Chip
                  label={viajesCriticos.length}
                  size="small"
                  sx={{
                    ml: 'auto',
                    bgcolor: '#7F1D1D',
                    color: '#FCA5A5',
                    fontSize: 10,
                    height: 18,
                    fontWeight: 700,
                  }}
                />
              </Box>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {['Código', 'Conductor', 'Ruta', 'Alerta', 'Retraso'].map((h) => (
                        <TableCell
                          key={h}
                          sx={{
                            color: '#475569',
                            fontSize: 10,
                            fontWeight: 700,
                            letterSpacing: 0.5,
                            textTransform: 'uppercase',
                            borderBottom: '1px solid #1F2937',
                            py: 0.8,
                            px: 1.5,
                          }}
                        >
                          {h}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {viajesCriticos.map((vc) => (
                      <TableRow
                        key={vc.codigo}
                        sx={{
                          '&:hover': { bgcolor: '#1A0A0A' },
                          '& td': { borderBottom: '1px solid #1F2937' },
                        }}
                      >
                        <TableCell sx={{ px: 1.5, py: 1 }}>
                          <Typography sx={{ color: '#38BDF8', fontSize: 10, fontWeight: 600 }}>
                            {vc.codigo.replace('VJ-20240619-', 'VJ-')}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ px: 1.5, py: 1 }}>
                          <Typography noWrap sx={{ color: '#CBD5E1', fontSize: 11, maxWidth: 80 }}>
                            {vc.conductor.split(' ')[0]}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ px: 1.5, py: 1 }}>
                          <Typography noWrap sx={{ color: '#94A3B8', fontSize: 10, maxWidth: 100 }}>
                            {vc.ruta}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ px: 1.5, py: 1 }}>
                          <Chip
                            label={vc.tipoAlerta}
                            size="small"
                            sx={{
                              bgcolor:
                                vc.tipoAlerta === 'DEMORADO'
                                  ? '#431407'
                                  : '#3B0A0A',
                              color:
                                vc.tipoAlerta === 'DEMORADO'
                                  ? '#FB923C'
                                  : '#F87171',
                              fontSize: 9,
                              height: 18,
                              fontWeight: 700,
                            }}
                          />
                        </TableCell>
                        <TableCell sx={{ px: 1.5, py: 1 }}>
                          <Typography sx={{ color: '#EF4444', fontSize: 11, fontWeight: 700 }}>
                            {vc.minutosRetraso} min
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Paper>
          </Grid>

          {/* Panel 2 — Próximas Entregas */}
          <Grid size={{ xs: 12, md: 4 }}>
            <Paper
              sx={{
                bgcolor: '#111827',
                border: '1px solid #1F2937',
                borderRadius: 2,
                overflow: 'hidden',
                height: '100%',
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  px: 2,
                  py: 1.2,
                  bgcolor: '#0C1A2E',
                  borderBottom: '1px solid #1E3A5F',
                }}
              >
                <Typography sx={{ color: '#93C5FD', fontSize: 12, fontWeight: 700, letterSpacing: 0.5 }}>
                  Próximas Entregas
                </Typography>
                <Typography sx={{ color: '#475569', fontSize: 11, ml: 0.5 }}>
                  — próximas 4 horas
                </Typography>
                <Chip
                  label={proximasEntregas.length}
                  size="small"
                  sx={{
                    ml: 'auto',
                    bgcolor: '#0C2340',
                    color: '#38BDF8',
                    fontSize: 10,
                    height: 18,
                    fontWeight: 700,
                  }}
                />
              </Box>
              <Box sx={{ p: 1.5 }}>
                {proximasEntregas.map((pe, i) => (
                  <Box
                    key={i}
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1.5,
                      py: 1.2,
                      px: 1,
                      borderBottom:
                        i < proximasEntregas.length - 1
                          ? '1px solid #1F2937'
                          : 'none',
                    }}
                  >
                    {/* Time */}
                    <Box sx={{ width: 40, flexShrink: 0, textAlign: 'center' }}>
                      <Typography
                        sx={{
                          color: TMS_COLOR,
                          fontSize: 13,
                          fontWeight: 800,
                          lineHeight: 1,
                        }}
                      >
                        {pe.hora}
                      </Typography>
                    </Box>
                    {/* Divider */}
                    <Box
                      sx={{
                        width: 2,
                        height: 32,
                        bgcolor:
                          pe.estado === 'ON_TIME'
                            ? '#22C55E'
                            : pe.estado === 'EN_RIESGO'
                            ? '#F59E0B'
                            : '#EF4444',
                        borderRadius: 1,
                        flexShrink: 0,
                      }}
                    />
                    {/* Info */}
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography noWrap sx={{ color: '#F1F5F9', fontSize: 12, fontWeight: 600 }}>
                        {pe.cliente}
                      </Typography>
                      <Typography sx={{ color: '#475569', fontSize: 10 }}>
                        {pe.ciudad} · {pe.viaje.replace('VJ-20240619-', 'VJ-')}
                      </Typography>
                    </Box>
                    {/* Status */}
                    <Chip
                      label={
                        pe.estado === 'ON_TIME'
                          ? 'A tiempo'
                          : pe.estado === 'EN_RIESGO'
                          ? 'En riesgo'
                          : 'Demorado'
                      }
                      size="small"
                      color={getEntregaColor(pe.estado) as 'success' | 'warning' | 'error'}
                      sx={{ fontSize: 10, height: 20, fontWeight: 700 }}
                    />
                  </Box>
                ))}
              </Box>
            </Paper>
          </Grid>

          {/* Panel 3 — Resumen Diario */}
          <Grid size={{ xs: 12, md: 4 }}>
            <Paper
              sx={{
                bgcolor: '#111827',
                border: '1px solid #1F2937',
                borderRadius: 2,
                overflow: 'hidden',
                height: '100%',
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  px: 2,
                  py: 1.2,
                  bgcolor: '#0C1A2E',
                  borderBottom: '1px solid #1E3A5F',
                }}
              >
                <Typography sx={{ color: '#93C5FD', fontSize: 12, fontWeight: 700, letterSpacing: 0.5 }}>
                  Resumen Diario
                </Typography>
                <Typography sx={{ color: '#475569', fontSize: 11, ml: 0.5 }}>
                  — {new Date().toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })}
                </Typography>
              </Box>
              <Box sx={{ p: 2 }}>
                {/* Todo sale del último día con registro. Antes eran ocho
                    cifras escritas a mano que no cambiaban nunca. El desglose
                    de combustible y peajes no está acá porque se costea por
                    viaje, no por día: inventarle un total diario habría sido
                    una cifra sin nada detrás. */}
                {[
                  { label: 'Viajes completados hoy',
                    value: String(kpi?.viajes_hoy ?? 0), color: '#4ADE80' },
                  { label: 'Viajes en tránsito',
                    value: String(kpi?.viajes_en_transito ?? 0), color: '#38BDF8' },
                  { label: 'Vehículos activos',
                    value: String(kpi?.vehiculos_activos ?? 0), color: '#A78BFA' },
                  { label: 'Km recorridos (mes)',
                    value: `${(kpi?.km_recorridos_mes ?? 0).toLocaleString('es-CO')} km`,
                    color: TMS_COLOR },
                  { label: 'Costo por kilómetro',
                    value: new Intl.NumberFormat('es-CO', { style: 'currency',
                      currency: 'COP', maximumFractionDigits: 0 })
                      .format(kpi?.costo_promedio_km ?? 0), color: '#F1F5F9' },
                  { label: 'Alertas sin leer',
                    value: String(alertasAPI.length), color: '#F1F5F9' },
                  { label: 'Alertas críticas',
                    value: String(kpi?.alertas_criticas ?? 0), color: '#EF4444' },
                  { label: 'OTIF del mes',
                    value: `${(kpi?.otif_rate ?? 0).toFixed(1)}%`, color: '#4ADE80' },
                ].map((row, i, arr) => (
                  <Box
                    key={row.label}
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      py: 1,
                      borderBottom:
                        i < arr.length - 1 ? '1px solid #1F2937' : 'none',
                    }}
                  >
                    <Typography sx={{ color: '#94A3B8', fontSize: 12 }}>
                      {row.label}
                    </Typography>
                    <Typography
                      sx={{ color: row.color, fontSize: 13, fontWeight: 700 }}
                    >
                      {row.value}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Paper>
          </Grid>
        </Grid>

        {/* Footer */}
        <Box sx={{ mt: 3, textAlign: 'center' }}>
          <Typography sx={{ color: '#1E3A5F', fontSize: 11 }}>
            la compañía — Sistema TMS Torre de Control · Datos en tiempo real
          </Typography>
        </Box>
      </Box>
    </Layout>
  );
}
