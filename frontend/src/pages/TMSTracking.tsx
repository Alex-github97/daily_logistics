import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Stack,
  Chip,
  TextField,
  InputAdornment,
  LinearProgress,
  Divider,
  Paper,
  Avatar,
  alpha,
  Grid,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material'
import {
  Search,
  LocalShipping,
  PersonPin,
  GpsFixed,
  Schedule,
  ArrowForward,
  FiberManualRecord,
  DirectionsBus,
  PlayArrow,
  CheckCircle,
  Warning,
  Error as ErrorIcon,
  RadioButtonUnchecked,
  LocationOn,
  Speed,
  MyLocation,
  Route,
  Map as MapIcon,
  TripOrigin,
  Flag,
  NavigateNext,
} from '@mui/icons-material'
import { Layout } from '@/components/layout/Layout'
import { apiClient as api } from '@/api/client'
import { listaDe } from '@/utils/listaApi'
import { MapaSeguimiento } from '@/components/mapa/MapaSeguimiento'
import { avanceSobreRuta, retrasoMinutos, duracionLegible } from '@/utils/geo'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO

// ─── Types ───────────────────────────────────────────────────────────────────

type EstadoViaje = 'NORMAL' | 'DEMORADO' | 'CRITICO'
type TipoEvento = 'SALIDA' | 'LLEGADA' | 'INCIDENTE' | 'GPS'
type EstadoParada = 'PENDIENTE' | 'EN_CURSO' | 'COMPLETADA'

interface Parada {
  secuencia: number
  ciudad: string
  estado: EstadoParada
  horaEstimada: string
  horaReal: string | null
}

interface EventoTracking {
  id: number
  timestamp: string
  tipo: TipoEvento
  descripcion: string
  lat: number
  lng: number
}

interface ViajeTracking {
  codigo: string
  conductor: string
  placa: string
  origen: string
  destino: string
  estado: EstadoViaje
  porcentaje: number
  etaEstimada: string
  ultimaActualizacion: string
  velocidadActual: number
  ciudadActual: string
  latActual: number
  lngActual: number
  origenPunto: { lat: number; lng: number } | null
  destinoPunto: { lat: number; lng: number } | null
  paradas: Parada[]
  eventos: EventoTracking[]
}

// ─── Lo que devuelve el API, y cómo se traduce a lo que pinta la pantalla ────

interface ViajeAPI {
  id: number
  codigo: string
  estado: string
  origen_ciudad: string | null
  destino_ciudad: string | null
  conductor_nombre: string | null
  vehiculo_placa: string | null
  fecha_real_cargue: string | null
  fecha_programada_entrega: string | null
  origen_lat?: number | null
  origen_lng?: number | null
  destino_lat?: number | null
  destino_lng?: number | null
}

interface EventoAPI {
  id: number
  tipo_evento: string
  descripcion: string | null
  lat: number | null
  lng: number | null
  velocidad_kmh: number | null
  timestamp: string
}

interface ParadaAPI {
  id: number
  secuencia: number
  ciudad: string
  direccion?: string | null
  estado: string
  lat: number | null
  lng: number | null
  tiempo_estimado_llegada: string | null
  tiempo_real_llegada: string | null
}

const hora = (iso: string | null) =>
  iso ? aFecha(iso).toLocaleTimeString('es-CO',
    { hour: '2-digit', minute: '2-digit' }) : '—'

/** Hace cuánto llegó el último reporte. */
function desdeHace(iso: string | null): string {
  if (!iso) return 'sin reportes'
  const minutos = Math.round((Date.now() - Date.parse(iso)) / 60000)
  if (!Number.isFinite(minutos)) return 'sin reportes'
  if (minutos < 1) return 'hace un momento'
  if (minutos < 60) return `hace ${minutos} min`
  const horas = Math.round(minutos / 60)
  if (horas < 24) return `hace ${horas} h`
  return `hace ${Math.round(horas / 24)} d`
}

/**
 * Avance estimado por reloj. Es el RESPALDO, no la medida principal.
 *
 * El tiempo transcurrido y la distancia recorrida son cosas distintas: un viaje
 * demorado da 100% por reloj mientras el camión sigue a mitad de camino en el
 * mapa. Eso fue exactamente lo que se vio en pantalla —barra al 100% y camión
 * por la mitad— y es lo que se corrige midiendo por distancia donde hay
 * coordenadas. Acá solo se responde «cuánto debería llevar» cuando no hay
 * ninguna posición reportada, y la pantalla lo rotula como estimado.
 */
function avancePorReloj(viaje: ViajeAPI): number {
  const salida = viaje.fecha_real_cargue ? Date.parse(viaje.fecha_real_cargue) : NaN
  const llegada = viaje.fecha_programada_entrega
    ? Date.parse(viaje.fecha_programada_entrega) : NaN
  if (!Number.isFinite(salida) || !Number.isFinite(llegada) || llegada <= salida) return 0
  return Math.max(0, Math.min(100,
    Math.round((Date.now() - salida) / (llegada - salida) * 100)))
}

/** Un viaje va mal si ya pasó su hora de entrega y sigue rodando. */
function situacion(viaje: ViajeAPI): EstadoViaje {
  const llegada = viaje.fecha_programada_entrega
    ? Date.parse(viaje.fecha_programada_entrega) : NaN
  if (!Number.isFinite(llegada)) return 'NORMAL'
  const horasDeMas = (Date.now() - llegada) / 3_600_000
  if (horasDeMas > 6) return 'CRITICO'
  if (horasDeMas > 0) return 'DEMORADO'
  return 'NORMAL'
}

const TIPO_EVENTO: Record<string, TipoEvento> = {
  SALIDA_ORIGEN: 'SALIDA',
  LLEGADA_DESTINO: 'LLEGADA',
  LLEGADA_PARADA: 'LLEGADA',
  SALIDA_PARADA: 'SALIDA',
  INCIDENTE: 'INCIDENTE',
  RETRASO: 'INCIDENTE',
  PARADA_NO_PROGRAMADA: 'INCIDENTE',
  DETENCION: 'INCIDENTE',
  ACTUALIZACION_GPS: 'GPS',
}

const ESTADO_PARADA: Record<string, EstadoParada> = {
  PENDIENTE: 'PENDIENTE',
  EN_CURSO: 'EN_CURSO',
  COMPLETADA: 'COMPLETADA',
  SALTADA: 'PENDIENTE',
}

function estadoConfig(estado: EstadoViaje) {
  switch (estado) {
    case 'NORMAL':
      return { label: 'NORMAL', color: '#16a34a', bg: alpha('#16a34a', 0.12) }
    case 'DEMORADO':
      return { label: 'DEMORADO', color: '#d97706', bg: alpha('#d97706', 0.12) }
    case 'CRITICO':
      return { label: 'CRÍTICO', color: '#dc2626', bg: alpha('#dc2626', 0.12) }
  }
}

function eventoConfig(tipo: TipoEvento) {
  switch (tipo) {
    case 'SALIDA':
      return { color: TMS_COLOR, bg: alpha(TMS_COLOR, 0.14), icon: <PlayArrow sx={{ fontSize: 14 }} /> }
    case 'LLEGADA':
      return { color: '#16a34a', bg: alpha('#16a34a', 0.14), icon: <CheckCircle sx={{ fontSize: 14 }} /> }
    case 'INCIDENTE':
      return { color: '#dc2626', bg: alpha('#dc2626', 0.14), icon: <ErrorIcon sx={{ fontSize: 14 }} /> }
    case 'GPS':
      return { color: '#6b7280', bg: alpha('#6b7280', 0.14), icon: <GpsFixed sx={{ fontSize: 14 }} /> }
  }
}

function paradaConfig(estado: EstadoParada) {
  switch (estado) {
    case 'PENDIENTE':
      return { color: '#6b7280', icon: <RadioButtonUnchecked sx={{ fontSize: 18 }} /> }
    case 'EN_CURSO':
      return { color: '#d97706', icon: <FiberManualRecord sx={{ fontSize: 18, color: '#d97706' }} /> }
    case 'COMPLETADA':
      return { color: '#16a34a', icon: <CheckCircle sx={{ fontSize: 18, color: '#16a34a' }} /> }
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function BlinkingDot({ color }: { color: string }) {
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        bgcolor: color,
        mr: 0.7,
        flexShrink: 0,
        animation: 'blink 1.4s ease-in-out infinite',
        '@keyframes blink': {
          '0%, 100%': { opacity: 1 },
          '50%': { opacity: 0.2 },
        },
      }}
    />
  )
}

function TripCard({ viaje, selected, onClick }: { viaje: ViajeTracking; selected: boolean; onClick: () => void }) {
  const est = estadoConfig(viaje.estado)
  return (
    <Box
      onClick={onClick}
      sx={{
        p: 1.5,
        borderRadius: 2,
        cursor: 'pointer',
        border: '1px solid',
        borderColor: selected ? TMS_COLOR : '#E5E7EB',
        bgcolor: selected ? alpha(TMS_COLOR, 0.10) : '#F8FAFC',
        transition: 'all 0.18s',
        '&:hover': { borderColor: alpha(TMS_COLOR, 0.5), bgcolor: alpha(TMS_COLOR, 0.06) },
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.8}>
        <Chip
          label={viaje.codigo}
          size="small"
          sx={{ bgcolor: alpha(TMS_COLOR, 0.18), color: TMS_COLOR, fontWeight: 700, fontSize: 11, height: 22 }}
        />
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <BlinkingDot color={est.color} />
          <Typography variant="caption" sx={{ color: est.color, fontWeight: 600, fontSize: 10 }}>
            {est.label}
          </Typography>
        </Box>
      </Stack>

      <Stack direction="row" alignItems="center" spacing={0.5} mb={0.4}>
        <PersonPin sx={{ fontSize: 13, color: '#64748B' }} />
        <Typography variant="caption" sx={{ color: '#334155', fontSize: 11 }}>
          {viaje.conductor}
        </Typography>
      </Stack>

      <Stack direction="row" alignItems="center" spacing={0.5} mb={0.8}>
        <Typography variant="caption" sx={{ color: '#1E293B', fontWeight: 600, fontSize: 12 }}>
          {viaje.origen}
        </Typography>
        <ArrowForward sx={{ fontSize: 12, color: '#64748B' }} />
        <Typography variant="caption" sx={{ color: '#1E293B', fontWeight: 600, fontSize: 12 }}>
          {viaje.destino}
        </Typography>
      </Stack>

      <Box mb={0.6}>
        <Stack direction="row" justifyContent="space-between" mb={0.3}>
          {/* «Previsto por horario», no «progreso»: la tarjeta no tiene las
              coordenadas de cada viaje —pedirlas serían tantas consultas como
              viajes en la lista— así que esto es lo que DEBERÍA llevar según el
              reloj, no lo que lleva. El avance real, medido sobre el mapa, está
              en el detalle. */}
          <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>
            Previsto por horario
          </Typography>
          <Typography variant="caption" sx={{ color: '#334155', fontWeight: 700, fontSize: 10 }}>
            {viaje.porcentaje}%
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={viaje.porcentaje}
          sx={{
            height: 5,
            borderRadius: 3,
            bgcolor: '#E5E7EB',
            '& .MuiLinearProgress-bar': { bgcolor: est.color, borderRadius: 3 },
          }}
        />
      </Box>

      <Stack direction="row" alignItems="center" spacing={0.5}>
        <Schedule sx={{ fontSize: 12, color: '#64748B' }} />
        <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>
          ETA: <strong style={{ color: '#1E293B' }}>{viaje.etaEstimada}</strong>
        </Typography>
      </Stack>
    </Box>
  )
}

function EmptyDetail() {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 2,
        color: '#64748B',
      }}
    >
      <MapIcon sx={{ fontSize: 72, color: alpha(TMS_COLOR, 0.25) }} />
      <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 500 }}>
        Selecciona un viaje para ver el tracking
      </Typography>
      <Typography variant="body2" sx={{ color: '#64748B', textAlign: 'center', maxWidth: 300 }}>
        Haz clic en cualquier viaje de la lista para visualizar su posición actual, eventos y paradas programadas.
      </Typography>
    </Box>
  )
}

function MapaDelViaje({ viaje, eventos, paradas, entregaPrevista }: {
  viaje: ViajeTracking
  eventos: EventoAPI[]
  paradas: ParadaAPI[]
  entregaPrevista: string | null
}) {
  // El rastro son los puntos que reportó el vehículo, en orden.
  const recorrido = eventos
    .filter(e => e.lat != null && e.lng != null)
    .slice()
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .map(e => ({ lat: e.lat as number, lng: e.lng as number }))

  // Origen: la bodega (primera parada). Destino: la última dirección de compra.
  // Si las paradas aún no tienen punto, se usa el del viaje.
  const enOrden = paradas.slice().sort((a, b) => a.secuencia - b.secuencia)
  const origen = enOrden[0]
  const destino = enOrden.length > 1 ? enOrden[enOrden.length - 1] : undefined
  // La bodega se nombra por su nombre («CEDI Bogotá — Cra 68…»); una entrega, por la dirección de compra.
  const rotulo = (p: ParadaAPI) => p.direccion ? `${p.ciudad} · ${p.direccion.split(' — ')[0]}` : p.ciudad
  const ultimo = recorrido.length ? recorrido[recorrido.length - 1] : null
  const intermedias = enOrden.slice(1, -1)
    .filter(p => p.lat != null && p.lng != null)
    .map(p => ({ lat: p.lat as number, lng: p.lng as number, etiqueta: rotulo(p), numero: p.secuencia - 1,
                 hecha: (ESTADO_PARADA[p.estado] ?? 'PENDIENTE') === 'COMPLETADA' }))

  // El avance se mide por DISTANCIA desde la última posición reportada, no por
  // reloj. Medido por reloj, un viaje demorado marcaba 100% mientras el camión
  // aparecía a mitad de camino en el mismo panel: la barra y el mapa decían
  // cosas distintas del mismo viaje.
  const puntoOrigen = origen && origen.lat != null && origen.lng != null
    ? { lat: origen.lat, lng: origen.lng } : viaje.origenPunto
  const puntoDestino = destino && destino.lat != null && destino.lng != null
    ? { lat: destino.lat, lng: destino.lng } : viaje.destinoPunto
  const avanceReal = avanceSobreRuta(puntoOrigen, ultimo, puntoDestino)

  // El retraso es un dato aparte, y se dice aparte: un viaje puede ir al 40% del
  // camino y con tres horas de retraso, y hay que poder leer las dos cosas.
  const retraso = retrasoMinutos(entregaPrevista)

  const cajas = [
    { icono: <MyLocation sx={{ fontSize: 15 }} />, titulo: 'Posición',
      valor: ultimo ? `${ultimo.lat.toFixed(4)}, ${ultimo.lng.toFixed(4)}` : '—' },
    { icono: <Speed sx={{ fontSize: 15 }} />, titulo: 'Velocidad',
      valor: viaje.velocidadActual ? `${viaje.velocidadActual} km/h` : '—' },
    { icono: <LocationOn sx={{ fontSize: 15 }} />, titulo: 'Destino',
      valor: viaje.destino },
  ]

  return (
    <Paper elevation={0} sx={{ bgcolor: '#111C36', borderRadius: 2, p: 2.5 }}>
      <Stack direction="row" spacing={1.5} mb={2} flexWrap="wrap" useFlexGap>
        {cajas.map((c, i) => (
          <Box key={i} sx={{
            flex: '1 1 150px', bgcolor: 'rgba(255,255,255,.06)',
            border: '1px solid rgba(148,163,184,.22)', borderRadius: 1.5,
            px: 1.75, py: 1.25,
          }}>
            <Stack direction="row" alignItems="center" spacing={0.75} mb={0.5}
                   sx={{ color: '#BFDBFE' }}>
              {c.icono}
              <Typography sx={{ fontSize: 11.5 }}>{c.titulo}</Typography>
            </Stack>
            <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: 15,
                              fontVariantNumeric: 'tabular-nums' }}>
              {c.valor}
            </Typography>
          </Box>
        ))}
      </Stack>

      <MapaSeguimiento
        origen={puntoOrigen ? { ...puntoOrigen, etiqueta: origen ? rotulo(origen) : viaje.origen } : null}
        destino={puntoDestino ? { ...puntoDestino, etiqueta: destino ? rotulo(destino) : viaje.destino } : null}
        paradas={intermedias}
        recorrido={recorrido}
        actual={ultimo
          ? { ...ultimo, etiqueta: `${viaje.codigo} · ${viaje.placa}` } : null}
        altura={330}
        color="#60A5FA"
        marcaActual="camion"
        avancePct={avanceReal ?? undefined}
      />

      {retraso > 0 && (
        // Se dice el retraso con todas sus letras. Antes quedaba escondido
        // dentro del porcentaje, que subía a 100% y se leía como «ya llegó».
        <Box sx={{ mt: 1.5, px: 1.75, py: 1.1, borderRadius: 1.5,
                   bgcolor: 'rgba(239,68,68,.14)',
                   border: '1px solid rgba(239,68,68,.35)' }}>
          <Typography sx={{ color: '#FCA5A5', fontSize: 13, fontWeight: 700 }}>
            {duracionLegible(retraso)} de retraso sobre la hora prevista de entrega
          </Typography>
        </Box>
      )}

      {avanceReal == null && (
        <Box sx={{ mt: 1.5, px: 1.75, py: 1.1, borderRadius: 1.5,
                   bgcolor: 'rgba(148,163,184,.12)' }}>
          <Typography sx={{ color: '#CBD5E1', fontSize: 12.5 }}>
            Sin posición reportada: no se puede calcular cuánto lleva recorrido.
          </Typography>
        </Box>
      )}

      <Stack direction="row" alignItems="center" justifyContent="space-between"
             sx={{ mt: 1.5 }}>
        <Typography sx={{ color: '#94A3B8', fontSize: 11 }}>
          Avance medido sobre la distancia entre origen y destino, desde la
          última posición reportada.
        </Typography>
        <Typography sx={{ color: '#94A3B8', fontSize: 11 }}>
          {viaje.ultimaActualizacion}
        </Typography>
      </Stack>
    </Paper>
  )
}

function EventTimeline({ eventos }: { eventos: EventoTracking[] }) {
  return (
    <Box>
      <Typography variant="subtitle2" sx={{ color: '#1E293B', fontWeight: 700, mb: 1.5, fontSize: 13 }}>
        Línea de Eventos
      </Typography>
      <Stack spacing={0}>
        {eventos.map((ev, idx) => {
          const cfg = eventoConfig(ev.tipo)
          const isLast = idx === eventos.length - 1
          return (
            <Box key={ev.id} sx={{ display: 'flex', gap: 1.5 }}>
              {/* Connector */}
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <Avatar
                  sx={{
                    width: 28, height: 28, bgcolor: cfg.bg,
                    color: cfg.color, border: `1.5px solid ${alpha(cfg.color, 0.4)}`,
                  }}
                >
                  {cfg.icon}
                </Avatar>
                {!isLast && (
                  <Box sx={{ width: 1.5, flexGrow: 1, bgcolor: '#E5E7EB', my: 0.3 }} />
                )}
              </Box>
              {/* Content */}
              <Box sx={{ pb: isLast ? 0 : 1.5, pt: 0.2, minWidth: 0 }}>
                <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                  <Chip
                    label={ev.tipo}
                    size="small"
                    sx={{
                      bgcolor: cfg.bg, color: cfg.color, fontWeight: 700,
                      fontSize: 9, height: 18, border: `1px solid ${alpha(cfg.color, 0.3)}`,
                    }}
                  />
                  <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>
                    {ev.timestamp}
                  </Typography>
                </Stack>
                <Typography variant="body2" sx={{ color: '#334155', fontSize: 12, mt: 0.3, lineHeight: 1.4 }}>
                  {ev.descripcion}
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>
                  {ev.lat.toFixed(4)}, {ev.lng.toFixed(4)}
                </Typography>
              </Box>
            </Box>
          )
        })}
      </Stack>
    </Box>
  )
}

function TripStops({ paradas }: { paradas: Parada[] }) {
  return (
    <Box>
      <Typography variant="subtitle2" sx={{ color: '#1E293B', fontWeight: 700, mb: 1.5, fontSize: 13 }}>
        Paradas del Viaje
      </Typography>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        {paradas.map((p) => {
          const cfg = paradaConfig(p.estado)
          return (
            <Box
              key={p.secuencia}
              sx={{
                flex: '1 1 140px',
                minWidth: 130,
                bgcolor: '#F8FAFC',
                border: '1px solid',
                borderColor: alpha(cfg.color, 0.3),
                borderRadius: 2,
                p: 1.5,
              }}
            >
              <Stack direction="row" alignItems="center" spacing={0.8} mb={0.5}>
                <Box sx={{ color: cfg.color, lineHeight: 1 }}>{cfg.icon}</Box>
                <Typography variant="caption" sx={{ color: '#1E293B', fontWeight: 700, fontSize: 12 }}>
                  {p.ciudad}
                </Typography>
              </Stack>
              <Chip
                label={p.estado.replace('_', ' ')}
                size="small"
                sx={{
                  bgcolor: alpha(cfg.color, 0.12), color: cfg.color,
                  fontWeight: 600, fontSize: 9, height: 18, mb: 0.8,
                }}
              />
              <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10, display: 'block' }}>
                Est.: {p.horaEstimada}
              </Typography>
              {p.horaReal && (
                <Typography variant="caption" sx={{ color: p.estado === 'COMPLETADA' ? '#16a34a' : '#d97706', fontSize: 10, display: 'block' }}>
                  Real: {p.horaReal}
                </Typography>
              )}
            </Box>
          )
        })}
      </Stack>
    </Box>
  )
}

function TripDetail({ viaje, viajeId, entregaPrevista }: {
  viaje: ViajeTracking; viajeId: number; entregaPrevista: string | null
}) {
  const est = estadoConfig(viaje.estado)

  // Los eventos y las paradas se piden solo del viaje abierto. Traerlos de
  // todos por adelantado serían miles de puntos de GPS para mostrar uno.
  const { data: eventos = [] } = useQuery<EventoAPI[]>({
    queryKey: ['tms-eventos', viajeId],
    queryFn: () => api.get(`/tms/viajes/${viajeId}/eventos`)
      .then((r: { data: unknown }) => listaDe<EventoAPI>(r.data)),
    refetchInterval: 60_000,
  })
  const { data: paradas = [] } = useQuery<ParadaAPI[]>({
    queryKey: ['tms-paradas', viajeId],
    queryFn: () => api.get(`/tms/viajes/${viajeId}/paradas`)
      .then((r: { data: unknown }) => listaDe<ParadaAPI>(r.data)),
  })

  const conGps = eventos.filter(e => e.lat != null && e.lng != null)
  const ultimo = conGps.length
    ? conGps.reduce((a, b) => (Date.parse(b.timestamp) > Date.parse(a.timestamp) ? b : a))
    : null

  const conDatos: ViajeTracking = {
    ...viaje,
    velocidadActual: Math.round(ultimo?.velocidad_kmh ?? 0),
    ultimaActualizacion: desdeHace(ultimo?.timestamp ?? null),
  }

  const linea: EventoTracking[] = eventos
    .filter(e => TIPO_EVENTO[e.tipo_evento] !== 'GPS')
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
    .map(e => ({
      id: e.id,
      timestamp: hora(e.timestamp),
      tipo: TIPO_EVENTO[e.tipo_evento] ?? 'GPS',
      descripcion: e.descripcion ?? e.tipo_evento.replace(/_/g, ' ').toLowerCase(),
      lat: e.lat ?? 0, lng: e.lng ?? 0,
    }))

  const listaParadas: Parada[] = paradas
    .slice()
    .sort((a, b) => a.secuencia - b.secuencia)
    .map(p => ({
      secuencia: p.secuencia, ciudad: p.direccion ? `${p.ciudad} · ${p.direccion.split(' — ')[0]}` : p.ciudad,
      estado: ESTADO_PARADA[p.estado] ?? 'PENDIENTE',
      horaEstimada: hora(p.tiempo_estimado_llegada),
      horaReal: p.tiempo_real_llegada ? hora(p.tiempo_real_llegada) : null,
    }))
  return (
    <Stack spacing={2.5} sx={{ height: '100%', overflowY: 'auto', pr: 0.5 }}>
      {/* Header */}
      <Box>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" mb={1}>
          <Box>
            <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
              <Chip
                label={viaje.codigo}
                sx={{ bgcolor: alpha(TMS_COLOR, 0.2), color: TMS_COLOR, fontWeight: 700, fontSize: 13, height: 28 }}
              />
              <Box sx={{ display: 'flex', alignItems: 'center', px: 1.2, py: 0.4, borderRadius: 5, bgcolor: est.bg }}>
                <BlinkingDot color={est.color} />
                <Typography variant="caption" sx={{ color: est.color, fontWeight: 700, fontSize: 11 }}>
                  {est.label}
                </Typography>
              </Box>
            </Stack>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700 }}>
                {viaje.origen}
              </Typography>
              <ArrowForward sx={{ color: TMS_COLOR }} />
              <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700 }}>
                {viaje.destino}
              </Typography>
            </Stack>
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Typography variant="caption" sx={{ color: '#64748B', fontSize: 10 }}>Última actualización</Typography>
            <Typography variant="body2" sx={{ color: '#334155', fontSize: 12 }}>{conDatos.ultimaActualizacion}</Typography>
          </Box>
        </Stack>

        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          {[
            { icon: <PersonPin sx={{ fontSize: 14 }} />, label: 'Conductor', value: viaje.conductor },
            { icon: <DirectionsBus sx={{ fontSize: 14 }} />, label: 'Placa', value: viaje.placa },
            { icon: <Schedule sx={{ fontSize: 14 }} />, label: 'ETA', value: viaje.etaEstimada },
          ].map((item, i) => (
            <Stack key={i} direction="row" alignItems="center" spacing={0.5}
              sx={{ bgcolor: '#F8FAFC', border: '1px solid #E5E7EB', borderRadius: 1.5, px: 1.5, py: 0.8 }}>
              <Box sx={{ color: '#64748B' }}>{item.icon}</Box>
              <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>{item.label}:</Typography>
              <Typography variant="caption" sx={{ color: '#1E293B', fontWeight: 600, fontSize: 11 }}>{item.value}</Typography>
            </Stack>
          ))}
        </Stack>
      </Box>

      <MapaDelViaje viaje={conDatos} eventos={eventos} paradas={paradas}
                    entregaPrevista={entregaPrevista} />
      <EventTimeline eventos={linea} />
      <Divider sx={{ borderColor: '#E5E7EB' }} />
      <TripStops paradas={listaParadas} />
    </Stack>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function TMSTracking() {
  const [search, setSearch] = useState('')
  const [ver, setVer] = useState<'EN_TRANSITO' | 'ASIGNADO' | 'PROGRAMADO'>('EN_TRANSITO')
  const [selectedCodigo, setSelectedCodigo] = useState<string | null>(null)

  // Los viajes que van rodando. Se refresca solo: la pantalla dice «en tiempo
  // real» y quedarse con la foto del momento en que se abrió sería mentir.
  const { data: crudos = [], isLoading } = useQuery<ViajeAPI[]>({
    queryKey: ['tms-tracking', ver],
    queryFn: () => api.get('/tms/viajes',
      { params: { estado: ver, per_page: 100 } })
      .then((r: { data: unknown }) => listaDe<ViajeAPI>(r.data)),
    refetchInterval: 60_000,
  })

  const viajes = useMemo(() => crudos.map((v) => ({
    api: v,
    vista: {
      codigo: v.codigo,
      conductor: v.conductor_nombre ?? 'Sin asignar',
      placa: v.vehiculo_placa ?? '—',
      origen: v.origen_ciudad ?? '—',
      destino: v.destino_ciudad ?? '—',
      estado: situacion(v),
      porcentaje: avancePorReloj(v),
      etaEstimada: hora(v.fecha_programada_entrega),
      ultimaActualizacion: 'sin reportes',
      velocidadActual: 0,
      ciudadActual: v.destino_ciudad ?? '—',
      latActual: 0, lngActual: 0,
      origenPunto: v.origen_lat != null && v.origen_lng != null ? { lat: v.origen_lat, lng: v.origen_lng } : null,
      destinoPunto: v.destino_lat != null && v.destino_lng != null ? { lat: v.destino_lat, lng: v.destino_lng } : null,
      paradas: [], eventos: [],
    } as ViajeTracking,
  })), [crudos])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return viajes
    return viajes.filter(({ vista }) =>
      vista.codigo.toLowerCase().includes(q) ||
      vista.conductor.toLowerCase().includes(q) ||
      vista.placa.toLowerCase().includes(q) ||
      vista.origen.toLowerCase().includes(q) ||
      vista.destino.toLowerCase().includes(q))
  }, [search, viajes])

  const seleccionado = useMemo(
    () => viajes.find((v) => v.vista.codigo === selectedCodigo) ?? null,
    [selectedCodigo, viajes])

  return (
    <Layout>
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: '#F0F2F5', p: 0 }}>
        {/* Page Header */}
        <Box sx={{ px: 3, pt: 2.5, pb: 1.5, borderBottom: '1px solid', borderColor: '#E5E7EB' }}>
          <Stack direction="row" alignItems="center" spacing={1.5} mb={0.3}>
            <Box
              sx={{
                width: 36, height: 36, borderRadius: 2, bgcolor: alpha(TMS_COLOR, 0.2),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Route sx={{ color: TMS_COLOR, fontSize: 20 }} />
            </Box>
            <Box>
              <Typography variant="h6" sx={{ color: '#1E293B', fontWeight: 700, lineHeight: 1.2 }}>
                Tracking en Tiempo Real
              </Typography>
              <Typography variant="caption" sx={{ color: '#64748B', fontSize: 11 }}>
                {viajes.length} {ver === 'EN_TRANSITO' ? 'viajes en tránsito' : ver === 'ASIGNADO' ? 'viajes por salir' : 'viajes programados'} · TMS — Módulo de Seguimiento
              </Typography>
            </Box>
          </Stack>
        </Box>

        {/* Body */}
        <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Left Panel */}
          <Box
            sx={{
              width: '35%',
              minWidth: 280,
              maxWidth: 400,
              borderRight: '1px solid',
              borderColor: '#E5E7EB',
              display: 'flex',
              flexDirection: 'column',
              bgcolor: 'background.paper',
            }}
          >
            <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: '#E5E7EB' }}>
              <ToggleButtonGroup size="small" exclusive fullWidth value={ver} onChange={(_, v) => { if (v) { setVer(v); setSelectedCodigo(null) } }} sx={{ mb: 1.25 }}>
                <ToggleButton value="EN_TRANSITO" sx={{ textTransform: 'none', fontSize: 12 }}>En ruta</ToggleButton>
                <ToggleButton value="ASIGNADO" sx={{ textTransform: 'none', fontSize: 12 }}>Por salir</ToggleButton>
                <ToggleButton value="PROGRAMADO" sx={{ textTransform: 'none', fontSize: 12 }}>Programados</ToggleButton>
              </ToggleButtonGroup>
              <TextField
                fullWidth
                size="small"
                placeholder="Buscar por código o conductor..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search sx={{ fontSize: 16, color: '#64748B' }} />
                    </InputAdornment>
                  ),
                  sx: {
                    fontSize: 13,
                    '&:hover fieldset': { borderColor: alpha(TMS_COLOR, 0.4) },
                    '&.Mui-focused fieldset': { borderColor: TMS_COLOR },
                  },
                }}
              />
            </Box>

            <Box sx={{ flex: 1, overflowY: 'auto', p: 1.5 }}>
              <Stack spacing={1}>
                {isLoading ? (
                  <Typography variant="body2" sx={{ color: '#64748B', textAlign: 'center', mt: 4 }}>
                    Cargando viajes…
                  </Typography>
                ) : filtered.length === 0 ? (
                  <Typography variant="body2" sx={{ color: '#64748B', textAlign: 'center', mt: 4 }}>
                    {search
                      ? 'No se encontraron viajes con ese criterio'
                      : ver === 'EN_TRANSITO' ? 'Ningún viaje en tránsito en este momento' : 'No hay viajes en este estado'}
                  </Typography>
                ) : (
                  filtered.map(({ api: v, vista }) => (
                    <TripCard
                      key={v.id}
                      viaje={vista}
                      selected={selectedCodigo === vista.codigo}
                      onClick={() => setSelectedCodigo(vista.codigo)}
                    />
                  ))
                )}
              </Stack>
            </Box>
          </Box>

          {/* Right Panel */}
          <Box
            sx={{
              flex: 1,
              overflowY: 'auto',
              p: 3,
              bgcolor: '#F0F2F5',
            }}
          >
            {seleccionado
              ? <TripDetail viaje={seleccionado.vista} viajeId={seleccionado.api.id}
                            entregaPrevista={seleccionado.api.fecha_programada_entrega} />
              : <EmptyDetail />}
          </Box>
        </Box>
      </Box>
    </Layout>
  )
}
