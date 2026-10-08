import React, { useState } from 'react'
import {
  Box, Paper, Typography, Button, TextField, Stack, Chip, CircularProgress, alpha, Tab, Tabs,
} from '@mui/material'
import {
  Search as SearchIcon,
  Inbox as InboxIcon,
  LocalShipping as TruckIcon,
  Edit as EditIcon,
  SwapHoriz as SwapIcon,
  AssignmentReturn as ReturnIcon,
  Inventory as InventoryIcon,
  LocationOn as LocationIcon,
  QrCode as QrIcon,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'
import toast from 'react-hot-toast'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const WMS_COLOR = COLOR_MODULO

// ─── Types ─────────────────────────────────────────────────────────────────────
interface EventoTrazabilidad {
  id: number
  tipo_evento: 'RECEPCION' | 'DESPACHO' | 'AJUSTE' | 'TRANSFERENCIA' | 'DEVOLUCION'
  descripcion: string
  fecha_hora: string
  usuario_nombre?: string
  datos_adicionales?: Record<string, unknown>
}

interface TrazabilidadProducto {
  nombre: string
  sku: string
  stock_total: number
  eventos: EventoTrazabilidad[]
}

interface TrazabilidadLote {
  numero_lote: string
  fecha_vencimiento?: string
  estado: string
  eventos: EventoTrazabilidad[]
}

interface TrazabilidadUbicacion {
  codigo: string
  zona: string
  capacidad?: number
  eventos: EventoTrazabilidad[]
}

type TrazabilidadResult = TrazabilidadProducto | TrazabilidadLote | TrazabilidadUbicacion | null

// ─── Event icon & color ────────────────────────────────────────────────────────
const EVENTO_CFG = {
  RECEPCION:    { Icon: InboxIcon,    color: '#059669', bg: '#D1FAE5', label: 'Recepción'    },
  DESPACHO:     { Icon: TruckIcon,    color: WMS_COLOR,  bg: '#DBEAFE', label: 'Despacho'    },
  AJUSTE:       { Icon: EditIcon,     color: '#D97706', bg: '#FEF3C7', label: 'Ajuste'       },
  TRANSFERENCIA:{ Icon: SwapIcon,     color: '#7C3AED', bg: '#EDE9FE', label: 'Transferencia'},
  DEVOLUCION:   { Icon: ReturnIcon,   color: '#DC2626', bg: '#FEE2E2', label: 'Devolución'   },
} as const

// ─── Header card based on search type ─────────────────────────────────────────
function ProductoHeader({ data }: { data: TrazabilidadProducto }) {
  return (
    <Paper elevation={0} sx={{ border: `1px solid ${alpha(WMS_COLOR, 0.25)}`, borderRadius: '12px', p: 2.5, mb: 3, bgcolor: alpha(WMS_COLOR, 0.03) }}>
      <Stack direction="row" gap={2} alignItems="center">
        <Box sx={{ width: 44, height: 44, borderRadius: '10px', bgcolor: alpha(WMS_COLOR, 0.1), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <InventoryIcon sx={{ color: WMS_COLOR, fontSize: 22 }} />
        </Box>
        <Box flex={1}>
          <Typography fontSize={16} fontWeight={800} color="text.primary">{data.nombre}</Typography>
          <Stack direction="row" gap={2} mt={0.5}>
            <Typography fontSize={12} color="text.secondary">SKU: <b>{data.sku}</b></Typography>
            <Typography fontSize={12} color="text.secondary">Stock total: <b>{data.stock_total}</b> uds.</Typography>
          </Stack>
        </Box>
      </Stack>
    </Paper>
  )
}

function LoteHeader({ data }: { data: TrazabilidadLote }) {
  return (
    <Paper elevation={0} sx={{ border: `1px solid ${alpha(WMS_COLOR, 0.25)}`, borderRadius: '12px', p: 2.5, mb: 3, bgcolor: alpha(WMS_COLOR, 0.03) }}>
      <Stack direction="row" gap={2} alignItems="center">
        <Box sx={{ width: 44, height: 44, borderRadius: '10px', bgcolor: alpha(WMS_COLOR, 0.1), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <QrIcon sx={{ color: WMS_COLOR, fontSize: 22 }} />
        </Box>
        <Box flex={1}>
          <Typography fontSize={16} fontWeight={800} color="text.primary">Lote {data.numero_lote}</Typography>
          <Stack direction="row" gap={2} mt={0.5}>
            {data.fecha_vencimiento && (
              <Typography fontSize={12} color="text.secondary">Vencimiento: <b>{data.fecha_vencimiento}</b></Typography>
            )}
            <Chip label={data.estado} size="small" sx={{ height: 20, fontSize: 10, fontWeight: 700 }} />
          </Stack>
        </Box>
      </Stack>
    </Paper>
  )
}

function UbicacionHeader({ data }: { data: TrazabilidadUbicacion }) {
  return (
    <Paper elevation={0} sx={{ border: `1px solid ${alpha(WMS_COLOR, 0.25)}`, borderRadius: '12px', p: 2.5, mb: 3, bgcolor: alpha(WMS_COLOR, 0.03) }}>
      <Stack direction="row" gap={2} alignItems="center">
        <Box sx={{ width: 44, height: 44, borderRadius: '10px', bgcolor: alpha(WMS_COLOR, 0.1), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <LocationIcon sx={{ color: WMS_COLOR, fontSize: 22 }} />
        </Box>
        <Box flex={1}>
          <Typography fontSize={16} fontWeight={800} color="text.primary">{data.codigo}</Typography>
          <Stack direction="row" gap={2} mt={0.5}>
            <Typography fontSize={12} color="text.secondary">Zona: <b>{data.zona}</b></Typography>
            {data.capacidad != null && (
              <Typography fontSize={12} color="text.secondary">Capacidad: <b>{data.capacidad} kg</b></Typography>
            )}
          </Stack>
        </Box>
      </Stack>
    </Paper>
  )
}

// ─── Timeline event item ───────────────────────────────────────────────────────
function TimelineItem({ evento, isLast }: { evento: EventoTrazabilidad; isLast: boolean }) {
  const cfg = EVENTO_CFG[evento.tipo_evento] ?? { Icon: InboxIcon, color: '#6B7280', bg: '#F3F4F6', label: evento.tipo_evento }
  const { Icon } = cfg

  const fecha = aFecha(evento.fecha_hora)
  const fechaStr = fecha.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
  const horaStr  = fecha.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })

  const datosStr = evento.datos_adicionales
    ? Object.entries(evento.datos_adicionales).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(' · ')
    : null

  return (
    <Stack direction="row" gap={2}>
      {/* Timeline spine */}
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, width: 32 }}>
        <Box sx={{ width: 32, height: 32, borderRadius: '50%', bgcolor: cfg.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', border: `2px solid ${cfg.color}`, flexShrink: 0 }}>
          <Icon sx={{ fontSize: 15, color: cfg.color }} />
        </Box>
        {!isLast && <Box sx={{ width: 2, flex: 1, bgcolor: '#E5E7EB', mt: 0.5 }} />}
      </Box>

      {/* Content */}
      <Box pb={isLast ? 0 : 2.5} flex={1}>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" mb={0.25}>
          <Chip label={cfg.label} size="small" sx={{ bgcolor: cfg.bg, color: cfg.color, fontWeight: 700, fontSize: 10, height: 20 }} />
          <Typography fontSize={11} color="text.secondary">{fechaStr} — {horaStr}</Typography>
          {evento.usuario_nombre && (
            <Typography fontSize={11} color="text.secondary">· {evento.usuario_nombre}</Typography>
          )}
        </Stack>
        <Typography fontSize={13} fontWeight={500} color="text.primary">{evento.descripcion}</Typography>
        {datosStr && (
          <Typography fontSize={11} color="text.secondary" mt={0.25} fontFamily="monospace">{datosStr}</Typography>
        )}
      </Box>
    </Stack>
  )
}

// ─── Results panel ─────────────────────────────────────────────────────────────
function ResultsPanel({ tabIndex, result, isLoading }: { tabIndex: number; result: TrazabilidadResult; isLoading: boolean }) {
  if (isLoading) {
    return <Box display="flex" justifyContent="center" py={6}><CircularProgress sx={{ color: WMS_COLOR }} /></Box>
  }
  if (!result) return null

  const eventos: EventoTrazabilidad[] = (result as { eventos?: EventoTrazabilidad[] }).eventos ?? []

  return (
    <Box>
      {tabIndex === 0 && <ProductoHeader data={result as TrazabilidadProducto} />}
      {tabIndex === 1 && <LoteHeader data={result as TrazabilidadLote} />}
      {tabIndex === 2 && <UbicacionHeader data={result as TrazabilidadUbicacion} />}

      <Typography fontSize={14} fontWeight={700} mb={2}>
        Historial de eventos ({eventos.length})
      </Typography>

      {eventos.length === 0 ? (
        <Typography fontSize={13} color="text.secondary" textAlign="center" py={3}>Sin eventos registrados</Typography>
      ) : (
        <Box>
          {eventos.map((ev, idx) => (
            <TimelineItem key={ev.id} evento={ev} isLast={idx === eventos.length - 1} />
          ))}
        </Box>
      )}
    </Box>
  )
}

// ─── Main page ─────────────────────────────────────────────────────────────────
export default function BitacoraEventos() {
  const [tabIndex, setTabIndex] = useState(0)
  const [inputs, setInputs] = useState(['', '', ''])
  const [queries, setQueries] = useState(['', '', ''])

  const setInput = (i: number, v: string) => setInputs(arr => { const next = [...arr]; next[i] = v; return next })

  const handleSearch = (i: number) => {
    if (!inputs[i].trim()) { toast.error('Ingrese un valor para buscar'); return }
    setQueries(arr => { const next = [...arr]; next[i] = inputs[i].trim(); return next })
  }

  const handleKeyDown = (i: number, e: React.KeyboardEvent) => { if (e.key === 'Enter') handleSearch(i) }

  // Query by SKU
  const { data: productoResult, isFetching: loadingProd } = useQuery<TrazabilidadProducto>({
    queryKey: ['wms-traz-producto', queries[0]],
    queryFn: () => api.get(`/wms/trazabilidad/producto/${queries[0]}`).then(r => r.data),
    enabled: !!queries[0],
    retry: false,
  })

  // Query by Lote
  const { data: loteResult, isFetching: loadingLote } = useQuery<TrazabilidadLote>({
    queryKey: ['wms-traz-lote', queries[1]],
    queryFn: () => api.get(`/wms/trazabilidad/lote/${queries[1]}`).then(r => r.data),
    enabled: !!queries[1],
    retry: false,
  })

  // Query by Ubicacion
  const { data: ubicacionResult, isFetching: loadingUbic } = useQuery<TrazabilidadUbicacion>({
    queryKey: ['wms-traz-ubicacion', queries[2]],
    queryFn: () => api.get(`/wms/trazabilidad/ubicacion/${queries[2]}`).then(r => r.data),
    enabled: !!queries[2],
    retry: false,
  })

  const results: TrazabilidadResult[] = [
    productoResult ?? null,
    loteResult ?? null,
    ubicacionResult ?? null,
  ]
  const loadings = [loadingProd, loadingLote, loadingUbic]

  const TABS = [
    { label: 'Por SKU / Producto', placeholder: 'Ej. SKU-001', icon: <InventoryIcon sx={{ fontSize: 16 }} /> },
    { label: 'Por Lote',           placeholder: 'Ej. LOT-2024-001', icon: <QrIcon sx={{ fontSize: 16 }} /> },
    { label: 'Por Ubicación',      placeholder: 'Ej. A-01-01-01', icon: <LocationIcon sx={{ fontSize: 16 }} /> },
  ]

  const currentResult = results[tabIndex]
  const isLoading    = loadings[tabIndex]
  const hasResult    = !!currentResult || isLoading
  const hasSearched  = !!queries[tabIndex]

  return (
    <Box>
      <Typography fontSize={12.5} color="text.secondary" mb={2}>
        Bitácora de eventos (quién hizo qué y cuándo) por producto, lote o ubicación.
      </Typography>

      {/* Search panel */}
      <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', mb: 3, overflow: 'hidden' }}>
        <Tabs
          value={tabIndex}
          onChange={(_, v) => setTabIndex(v)}
          sx={{
            borderBottom: '1px solid #E5E7EB',
            '& .MuiTabs-indicator': { bgcolor: WMS_COLOR },
            px: 2,
          }}
        >
          {TABS.map((t, i) => (
            <Tab
              key={i}
              label={t.label}
              icon={t.icon}
              iconPosition="start"
              sx={{ textTransform: 'none', fontWeight: 600, fontSize: 13, '&.Mui-selected': { color: WMS_COLOR }, minHeight: 48 }}
            />
          ))}
        </Tabs>

        <Box p={2.5}>
          {TABS.map((t, i) => (
            <Box key={i} display={tabIndex === i ? 'block' : 'none'}>
              <Stack direction="row" gap={1.5}>
                <TextField
                  fullWidth
                  size="small"
                  placeholder={t.placeholder}
                  value={inputs[i]}
                  onChange={e => setInput(i, e.target.value)}
                  onKeyDown={e => handleKeyDown(i, e)}
                  InputProps={{
                    sx: { borderRadius: '8px', fontSize: 13 },
                  }}
                />
                <Button
                  variant="contained"
                  startIcon={<SearchIcon />}
                  onClick={() => handleSearch(i)}
                  disabled={loadings[i]}
                  sx={{
                    textTransform: 'none', fontWeight: 600, borderRadius: '8px', whiteSpace: 'nowrap',
                    bgcolor: WMS_COLOR, '&:hover': { bgcolor: '#1E3A8A' }, minWidth: 120,
                  }}
                >
                  {loadings[i] ? <CircularProgress size={16} color="inherit" /> : 'Buscar'}
                </Button>
              </Stack>
            </Box>
          ))}
        </Box>
      </Paper>

      {/* Results */}
      {hasResult ? (
        <ResultsPanel tabIndex={tabIndex} result={currentResult} isLoading={isLoading} />
      ) : hasSearched && !isLoading ? (
        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px', p: 5 }}>
          <Stack alignItems="center" gap={1.5}>
            <SearchIcon sx={{ fontSize: 40, color: '#D1D5DB' }} />
            <Typography fontSize={14} fontWeight={600} color="text.secondary">Sin resultados</Typography>
            <Typography fontSize={13} color="text.secondary">No se encontró información para "{queries[tabIndex]}"</Typography>
          </Stack>
        </Paper>
      ) : !hasSearched ? (
        <Paper elevation={0} sx={{ border: '1px dashed #D1D5DB', borderRadius: '14px', p: 5, bgcolor: '#FAFAFA' }}>
          <Stack alignItems="center" gap={2}>
            <Box sx={{ width: 56, height: 56, borderRadius: '14px', bgcolor: alpha(WMS_COLOR, 0.08), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <SearchIcon sx={{ fontSize: 28, color: WMS_COLOR }} />
            </Box>
            <Box textAlign="center">
              <Typography fontSize={14} fontWeight={700} color="text.primary" mb={0.5}>
                Busca el historial de trazabilidad
              </Typography>
              <Typography fontSize={13} color="text.secondary" maxWidth={480}>
                Ingrese un SKU, número de lote o código de ubicación para ver el historial completo de trazabilidad.
              </Typography>
            </Box>
          </Stack>
        </Paper>
      ) : null}
    </Box>
  )
}
