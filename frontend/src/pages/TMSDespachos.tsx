/**
 * Los despachos del TMS: el viaje en su etapa de salida.
 *
 * POR QUÉ NO HAY UNA ENTIDAD «DESPACHO»
 * En el TMS un despacho no es una tabla aparte, es el mismo viaje en tres
 * momentos: el que aún no sale, el que va rodando y el que ya llegó. Crearle una
 * entidad propia habría producido dos verdades sobre el mismo hecho —el viaje y
 * su despacho— que tarde o temprano se contradicen: una dice entregado y la otra
 * en tránsito, y nadie sabe cuál creer.
 *
 * Esta pantalla estaba maquetada, y con nombres de empresas reales inventados
 * como clientes. Eso es peor que estar vacía: quien la ve piensa que está
 * mirando la operación.
 */
import React, { useMemo, useState } from 'react'
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, IconButton, LinearProgress, Paper,
  Stack, Tab, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Tabs, TextField, Tooltip, Typography, alpha,
} from '@mui/material'
import {
  Assignment, Close, LocalShipping, Place, ReportProblem, Visibility,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { apiClient as api } from '@/api/client'
import { listaDe } from '@/utils/listaApi'
import { mensajeDeError } from '@/utils/errorApi'
import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

const TMS_COLOR = COLOR_MODULO

interface ViajeAPI {
  id: number
  codigo: string
  estado: string
  origen_ciudad: string | null
  destino_ciudad: string | null
  conductor_nombre: string | null
  vehiculo_placa: string | null
  descripcion_carga: string | null
  peso_kg: number | null
  num_entregas: number
  distancia_km: number | null
  valor_flete: number | null
  fecha_programada_cargue: string | null
  fecha_real_cargue: string | null
  fecha_programada_entrega: string | null
  fecha_real_entrega: string | null
  otif_on_time: boolean | null
  otif_in_full: boolean | null
}

interface ParadaAPI {
  id: number; secuencia: number; ciudad: string; direccion: string | null
  tipo: string; estado: string
  tiempo_estimado_llegada: string | null; tiempo_real_llegada: string | null
}

interface DocumentoAPI {
  id: number; tipo_documento: string; numero: string | null
  estado: string; fecha_emision: string | null
}

const HOY = new Date().toISOString().split('T')[0]

const kg = (n: number | null) => `${(n || 0).toLocaleString('es-CO')} kg`
const pesos = (n: number | null) =>
  new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP',
    maximumFractionDigits: 0 }).format(n || 0)
const fecha = (iso: string | null) =>
  iso ? aFecha(iso).toLocaleDateString('es-CO',
    { day: '2-digit', month: 'short' }) : '—'
const horaFecha = (iso: string | null) =>
  iso ? aFecha(iso).toLocaleString('es-CO',
    { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

/**
 * Cuánto lleva recorrido, medido del reloj.
 *
 * No hay un porcentaje guardado en ninguna parte, y calcularlo de la distancia
 * exigiría saber por dónde va el vehículo sobre la carretera, que es un dato que
 * el GPS no da: da puntos sueltos. El tiempo transcurrido sobre el previsto es
 * una aproximación honesta y es la que usa un despachador.
 */
function avance(v: ViajeAPI): number {
  const a = v.fecha_real_cargue ? Date.parse(v.fecha_real_cargue) : NaN
  const b = v.fecha_programada_entrega ? Date.parse(v.fecha_programada_entrega) : NaN
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) return 0
  return Math.max(0, Math.min(100, Math.round((Date.now() - a) / (b - a) * 100)))
}

/** Urgente es lo que carga hoy o ya debió cargar. */
const esUrgente = (v: ViajeAPI) =>
  !!v.fecha_programada_cargue && v.fecha_programada_cargue.split('T')[0] <= HOY

const ESTADO_CHIP: Record<string, { label: string; color: string; bg: string }> = {
  PROGRAMADO:  { label: 'Programado',  color: '#4B5563', bg: '#F3F4F6' },
  ASIGNADO:    { label: 'Asignado',    color: '#6D28D9', bg: '#EDE9FE' },
  EN_TRANSITO: { label: 'En tránsito', color: '#0369A1', bg: '#E0F2FE' },
  ENTREGADO:   { label: 'Entregado',   color: '#15803D', bg: '#DCFCE7' },
  CERRADO:     { label: 'Cerrado',     color: '#374151', bg: '#E5E7EB' },
  CANCELADO:   { label: 'Cancelado',   color: '#B91C1C', bg: '#FEE2E2' },
}

function chipEstado(estado: string) {
  const e = ESTADO_CHIP[estado] ?? { label: estado, color: '#4B5563', bg: '#F3F4F6' }
  return <Chip label={e.label} size="small"
               sx={{ bgcolor: e.bg, color: e.color, fontWeight: 700, fontSize: 11 }} />
}

// ─── El detalle de un viaje ──────────────────────────────────────────────────

function DetalleViaje({ viaje, onCerrar }: { viaje: ViajeAPI; onCerrar: () => void }) {
  // Las paradas y los documentos se piden solo del viaje abierto: traerlos de
  // todos por adelantado serían miles de filas para mostrar unas pocas.
  const { data: paradas = [] } = useQuery<ParadaAPI[]>({
    queryKey: ['tms-paradas', viaje.id],
    queryFn: () => api.get(`/tms/viajes/${viaje.id}/paradas`)
      .then((r: { data: unknown }) => listaDe<ParadaAPI>(r.data)),
  })
  const { data: documentos = [] } = useQuery<DocumentoAPI[]>({
    queryKey: ['tms-documentos', viaje.id],
    queryFn: () => api.get(`/tms/viajes/${viaje.id}/documentos`)
      .then((r: { data: unknown }) => listaDe<DocumentoAPI>(r.data)),
  })

  const dato = (t: string, v: React.ReactNode) => (
    <Box>
      <Typography sx={{ fontSize: 11.5, color: 'text.secondary' }}>{t}</Typography>
      <Typography sx={{ fontSize: 14, fontWeight: 700 }}>{v}</Typography>
    </Box>
  )

  return (
    <Dialog open onClose={onCerrar} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack direction="row" spacing={1.25} alignItems="center">
            <LocalShipping sx={{ color: TMS_COLOR }} />
            <Box>
              <Typography fontWeight={800} fontSize={17}>{viaje.codigo}</Typography>
              <Typography fontSize={13} color="text.secondary">
                {viaje.origen_ciudad} → {viaje.destino_ciudad}
              </Typography>
            </Box>
          </Stack>
          <IconButton size="small" onClick={onCerrar}><Close /></IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap sx={{ mb: 2.5 }}>
          {dato('Estado', chipEstado(viaje.estado))}
          {dato('Conductor', viaje.conductor_nombre ?? '—')}
          {dato('Placa', viaje.vehiculo_placa ?? '—')}
          {dato('Peso', kg(viaje.peso_kg))}
          {dato('Distancia', viaje.distancia_km ? `${viaje.distancia_km} km` : '—')}
          {dato('Flete', pesos(viaje.valor_flete))}
          {dato('Entregas', viaje.num_entregas)}
        </Stack>

        {viaje.descripcion_carga && (
          <Alert severity="info" sx={{ mb: 2.5, fontSize: 13.5 }}>
            {viaje.descripcion_carga}
          </Alert>
        )}

        <Typography fontSize={12} fontWeight={800} color="text.secondary" mb={1}>
          RUTA Y PARADAS
        </Typography>
        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: 2,
                                   mb: 2.5, overflow: 'hidden' }}>
          {paradas.length === 0 ? (
            <Box sx={{ p: 2, color: 'text.secondary', fontSize: 13 }}>
              Este viaje no tiene paradas registradas.
            </Box>
          ) : paradas.slice().sort((a, b) => a.secuencia - b.secuencia).map((p, i) => (
            <Stack key={p.id} direction="row" spacing={1.5} alignItems="center"
                   sx={{ px: 2, py: 1.25,
                         borderBottom: i < paradas.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
              <Place sx={{ fontSize: 18,
                           color: p.estado === 'COMPLETADA' ? '#16A34A' : '#94A3B8' }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography fontSize={13.5} fontWeight={700}>{p.ciudad}</Typography>
                <Typography fontSize={12} color="text.secondary" noWrap>
                  {p.direccion ?? p.tipo.replace(/_/g, ' ').toLowerCase()}
                </Typography>
              </Box>
              <Box sx={{ textAlign: 'right' }}>
                <Typography fontSize={12} color="text.secondary">
                  prevista {horaFecha(p.tiempo_estimado_llegada)}
                </Typography>
                <Typography fontSize={12.5} fontWeight={700}>
                  {p.tiempo_real_llegada ? horaFecha(p.tiempo_real_llegada) : 'sin llegar'}
                </Typography>
              </Box>
            </Stack>
          ))}
        </Paper>

        <Typography fontSize={12} fontWeight={800} color="text.secondary" mb={1}>
          DOCUMENTOS
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {documentos.length === 0 ? (
            <Typography fontSize={13} color="text.secondary">
              Todavía no se ha generado ningún documento para este viaje.
            </Typography>
          ) : documentos.map(d => (
            <Chip key={d.id}
                  label={`${d.tipo_documento} ${d.numero ?? ''} · ${d.estado.toLowerCase()}`}
                  size="small"
                  sx={{ bgcolor: d.estado === 'FIRMADO' ? '#DCFCE7' : '#FEF3C7',
                        color: d.estado === 'FIRMADO' ? '#15803D' : '#B45309',
                        fontWeight: 700, fontSize: 11.5 }} />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onCerrar}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Confirmar la salida ─────────────────────────────────────────────────────

function DespacharDialog({ viaje, onCerrar, onHecho }: {
  viaje: ViajeAPI; onCerrar: () => void; onHecho: () => void
}) {
  const [sellos, setSellos] = useState('')
  const [notas, setNotas] = useState('')

  const despachar = useMutation({
    mutationFn: () => {
      // El servidor exige que el viaje pase por ASIGNADO antes de salir. Se
      // encadenan las dos transiciones acá y no se relaja la regla en el
      // backend: esa validación es la que impide que un viaje salga sin
      // vehículo ni conductor.
      const observacion = [sellos && `Sellos: ${sellos}`, notas]
        .filter(Boolean).join(' · ')
      const paso = (estado: string) =>
        api.put(`/tms/viajes/${viaje.id}/estado`,
                null, { params: { estado, notas: observacion || undefined } })
      return viaje.estado === 'PROGRAMADO'
        ? paso('ASIGNADO').then(() => paso('EN_TRANSITO'))
        : paso('EN_TRANSITO')
    },
    onSuccess: () => { toast.success(`${viaje.codigo} salió a ruta`); onHecho() },
    onError: (e) => toast.error(mensajeDeError(e, 'No se pudo despachar el viaje')),
  })

  return (
    <Dialog open onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack direction="row" spacing={1} alignItems="center">
            <Assignment sx={{ color: TMS_COLOR }} />
            <Typography fontWeight={800}>Despachar {viaje.codigo}</Typography>
          </Stack>
          <IconButton size="small" onClick={onCerrar}><Close /></IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Typography fontSize={13.5} color="text.secondary" mb={2.5}>
          {viaje.origen_ciudad} → {viaje.destino_ciudad} · {kg(viaje.peso_kg)} ·
          conductor {viaje.conductor_nombre ?? 'sin asignar'} ·
          placa {viaje.vehiculo_placa ?? 'sin asignar'}
        </Typography>

        {!viaje.conductor_nombre || !viaje.vehiculo_placa ? (
          <Alert severity="warning" sx={{ mb: 2, fontSize: 13.5 }}>
            Este viaje no tiene conductor o vehículo asignado. Asígnelos antes de
            despacharlo, o el registro quedará sin responsable.
          </Alert>
        ) : null}

        <Stack spacing={2}>
          <TextField label="Sellos de seguridad" value={sellos} fullWidth
                     onChange={(e) => setSellos(e.target.value)}
                     placeholder="Separados por coma" />
          <TextField label="Observaciones de salida" value={notas} fullWidth
                     multiline rows={2}
                     onChange={(e) => setNotas(e.target.value)} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onCerrar}>Cancelar</Button>
        <Button variant="contained" disabled={despachar.isPending}
                onClick={() => despachar.mutate()}>
          {despachar.isPending ? 'Despachando…' : 'Confirmar salida'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── La pantalla ─────────────────────────────────────────────────────────────

export default function TMSDespachos() {
  const qc = useQueryClient()
  const navegar = useNavigate()
  const [tab, setTab] = useState(0)
  const [detalle, setDetalle] = useState<ViajeAPI | null>(null)
  const [despachar, setDespachar] = useState<ViajeAPI | null>(null)

  const pedir = (estado: string) =>
    api.get('/tms/viajes', { params: { estado, per_page: 100 } })
      .then((r: { data: unknown }) => listaDe<ViajeAPI>(r.data))

  const { data: programados = [], isLoading: c1 } = useQuery<ViajeAPI[]>({
    queryKey: ['tms-desp-programados'], queryFn: () => pedir('PROGRAMADO'),
  })
  const { data: asignados = [], isLoading: c2 } = useQuery<ViajeAPI[]>({
    queryKey: ['tms-desp-asignados'], queryFn: () => pedir('ASIGNADO'),
  })
  const { data: enTransito = [], isLoading: c3 } = useQuery<ViajeAPI[]>({
    queryKey: ['tms-desp-transito'], queryFn: () => pedir('EN_TRANSITO'),
    refetchInterval: 60_000,
  })
  const { data: entregados = [], isLoading: c4 } = useQuery<ViajeAPI[]>({
    queryKey: ['tms-desp-entregados'], queryFn: () => pedir('ENTREGADO'),
  })

  const cargando = c1 || c2 || c3 || c4
  const pendientes = useMemo(
    () => [...programados, ...asignados].sort((a, b) =>
      (a.fecha_programada_cargue ?? '').localeCompare(b.fecha_programada_cargue ?? '')),
    [programados, asignados])
  const urgentes = pendientes.filter(esUrgente).length

  const refrescar = () => {
    for (const k of ['tms-desp-programados', 'tms-desp-asignados',
                     'tms-desp-transito', 'tms-desp-entregados', 'tms-kpis']) {
      qc.invalidateQueries({ queryKey: [k] })
    }
  }

  const encabezado = (cols: string[]) => (
    <TableHead>
      <TableRow sx={{ bgcolor: '#F9FAFB' }}>
        {cols.map(c => (
          <TableCell key={c} sx={{ fontWeight: 700, fontSize: 12 }}>{c}</TableCell>
        ))}
      </TableRow>
    </TableHead>
  )

  const vacio = (cols: number, texto: string) => (
    <TableRow>
      <TableCell colSpan={cols} align="center"
                 sx={{ py: 5, color: 'text.secondary', fontSize: 13.5 }}>
        {texto}
      </TableCell>
    </TableRow>
  )

  return (
    <Layout>
      <Box sx={{ p: 3, maxWidth: 1600, mx: 'auto' }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
          <Box>
            <Typography variant="h5" fontWeight={800} color={TMS_COLOR}>
              Gestión de Despachos
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {pendientes.length} por despachar · {enTransito.length} en ruta ·
              {' '}{entregados.length} entregados sin cerrar
            </Typography>
          </Box>
          {urgentes > 0 && (
            <Chip label={`${urgentes} cargan hoy o antes`}
                  sx={{ bgcolor: '#FEE2E2', color: '#DC2626', fontWeight: 700 }} />
          )}
        </Stack>

        <Paper elevation={0} sx={{ border: '1px solid #E5E7EB', borderRadius: '14px',
                                   overflow: 'hidden' }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)}
                sx={{ px: 2, borderBottom: '1px solid #F3F4F6', bgcolor: '#F9FAFB' }}>
            <Tab label={`Por Despachar (${pendientes.length})`}
                 sx={{ fontSize: 13, fontWeight: 600 }} />
            <Tab label={`En Ruta (${enTransito.length})`}
                 sx={{ fontSize: 13, fontWeight: 600 }} />
            <Tab label={`Entregados (${entregados.length})`}
                 sx={{ fontSize: 13, fontWeight: 600 }} />
          </Tabs>

          {cargando ? (
            <Box sx={{ p: 6, textAlign: 'center' }}><CircularProgress /></Box>
          ) : (
            <TableContainer>
              {tab === 0 && (
                <Table size="small">
                  {encabezado(['Viaje', 'Ruta', 'Carga', 'Peso', 'Cargue', 'Estado', ''])}
                  <TableBody>
                    {pendientes.length === 0
                      ? vacio(7, 'No hay viajes pendientes de despachar. Programe uno desde «Viajes».')
                      : pendientes.map(v => (
                      <TableRow key={v.id} hover>
                        <TableCell>
                          <Typography fontSize={12.5} fontWeight={700} color={TMS_COLOR}>
                            {v.codigo}
                          </Typography>
                          {esUrgente(v) && (
                            <Chip label="Urgente" size="small"
                                  sx={{ bgcolor: '#FEE2E2', color: '#DC2626',
                                        fontWeight: 700, fontSize: 10, height: 18 }} />
                          )}
                        </TableCell>
                        <TableCell>
                          <Typography fontSize={12.5}>{v.origen_ciudad}</Typography>
                          <Typography fontSize={11.5} color="text.secondary">
                            → {v.destino_ciudad}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography fontSize={12.5} noWrap sx={{ maxWidth: 260 }}>
                            {v.descripcion_carga ?? '—'}
                          </Typography>
                        </TableCell>
                        <TableCell><Typography fontSize={12.5}>{kg(v.peso_kg)}</Typography></TableCell>
                        <TableCell><Typography fontSize={12.5}>
                          {fecha(v.fecha_programada_cargue)}
                        </Typography></TableCell>
                        <TableCell>{chipEstado(v.estado)}</TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                            <Tooltip title="Ver detalle">
                              <IconButton size="small" sx={{ color: TMS_COLOR }}
                                          onClick={() => setDetalle(v)}>
                                <Visibility sx={{ fontSize: 16 }} />
                              </IconButton>
                            </Tooltip>
                            <Button size="small" variant="contained"
                                    onClick={() => setDespachar(v)}
                                    sx={{ fontSize: 11.5, py: 0.3 }}>
                              Despachar
                            </Button>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              {tab === 1 && (
                <Table size="small">
                  {encabezado(['Viaje', 'Ruta', 'Conductor', 'Placa', 'Avance', ''])}
                  <TableBody>
                    {enTransito.length === 0
                      ? vacio(6, 'Ningún viaje en ruta en este momento.')
                      : enTransito.map(v => {
                      const pct = avance(v)
                      return (
                        <TableRow key={v.id} hover>
                          <TableCell>
                            <Typography fontSize={12.5} fontWeight={700} color={TMS_COLOR}>
                              {v.codigo}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography fontSize={12.5}>
                              {v.origen_ciudad} → {v.destino_ciudad}
                            </Typography>
                          </TableCell>
                          <TableCell><Typography fontSize={12.5}>
                            {v.conductor_nombre ?? '—'}
                          </Typography></TableCell>
                          <TableCell>
                            <Chip label={v.vehiculo_placa ?? '—'} size="small"
                                  sx={{ fontFamily: 'monospace', fontWeight: 700,
                                        fontSize: 11 }} />
                          </TableCell>
                          <TableCell sx={{ minWidth: 160 }}>
                            <LinearProgress variant="determinate" value={pct}
                              sx={{ height: 6, borderRadius: 3, mb: 0.5,
                                    bgcolor: '#E5E7EB',
                                    '& .MuiLinearProgress-bar': {
                                      bgcolor: pct >= 100 ? '#D97706' : TMS_COLOR } }} />
                            <Typography fontSize={11}>
                              {pct}% · llega {horaFecha(v.fecha_programada_entrega)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                              <Tooltip title="Ver detalle">
                                <IconButton size="small" sx={{ color: TMS_COLOR }}
                                            onClick={() => setDetalle(v)}>
                                  <Visibility sx={{ fontSize: 16 }} />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Seguir en el mapa">
                                <IconButton size="small" sx={{ color: '#0369A1' }}
                                            onClick={() => navegar('/tms/tracking')}>
                                  <Place sx={{ fontSize: 16 }} />
                                </IconButton>
                              </Tooltip>
                            </Stack>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              )}

              {tab === 2 && (
                <Table size="small">
                  {encabezado(['Viaje', 'Ruta', 'Salida', 'Entrega', 'Cumplimiento', ''])}
                  <TableBody>
                    {entregados.length === 0
                      ? vacio(6, 'No hay viajes entregados pendientes de cierre.')
                      : entregados.map(v => (
                      <TableRow key={v.id} hover>
                        <TableCell>
                          <Typography fontSize={12.5} fontWeight={700} color={TMS_COLOR}>
                            {v.codigo}
                          </Typography>
                        </TableCell>
                        <TableCell><Typography fontSize={12.5}>
                          {v.origen_ciudad} → {v.destino_ciudad}
                        </Typography></TableCell>
                        <TableCell><Typography fontSize={12.5}>
                          {horaFecha(v.fecha_real_cargue)}
                        </Typography></TableCell>
                        <TableCell><Typography fontSize={12.5}>
                          {horaFecha(v.fecha_real_entrega)}
                        </Typography></TableCell>
                        <TableCell>
                          {v.otif_on_time === false ? (
                            <Chip label="TARDE" size="small"
                                  sx={{ bgcolor: '#FEE2E2', color: '#B91C1C',
                                        fontWeight: 700, fontSize: 10 }} />
                          ) : v.otif_in_full === false ? (
                            <Chip label="INCOMPLETA" size="small"
                                  sx={{ bgcolor: '#FFEDD5', color: '#C2410C',
                                        fontWeight: 700, fontSize: 10 }} />
                          ) : (
                            <Chip label="ON TIME" size="small"
                                  sx={{ bgcolor: '#DCFCE7', color: '#15803D',
                                        fontWeight: 700, fontSize: 10 }} />
                          )}
                        </TableCell>
                        <TableCell align="right">
                          <Tooltip title="Ver detalle">
                            <IconButton size="small" sx={{ color: TMS_COLOR }}
                                        onClick={() => setDetalle(v)}>
                              <Visibility sx={{ fontSize: 16 }} />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </TableContainer>
          )}
        </Paper>

        {detalle && <DetalleViaje viaje={detalle} onCerrar={() => setDetalle(null)} />}
        {despachar && (
          <DespacharDialog viaje={despachar}
                           onCerrar={() => setDespachar(null)}
                           onHecho={() => { setDespachar(null); refrescar() }} />
        )}
      </Box>
    </Layout>
  )
}
