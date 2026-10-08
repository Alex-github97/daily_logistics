/**
 * Detalle de un viaje, con lo que se registra durante el recorrido.
 *
 * Antes el detalle solo MOSTRABA paradas, tracking, documentos y costos: no
 * había cómo agregar un seguimiento, reportar una novedad o subir la remesa,
 * aunque el servidor tenía las rutas para todo. Tampoco se veían las alertas
 * del viaje ni la prueba de entrega.
 *
 * Cada pestaña trae su propio formulario y se refresca sola al guardar.
 * Las novedades (incidente, retraso, detención, parada no programada) son
 * eventos del tracking: van en la misma línea de tiempo porque son parte de
 * la historia del viaje, y separadas se pierde el orden en que ocurrieron.
 */
import React, { useState } from 'react'
import {
  Box, Typography, Stack, Paper, Chip, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, IconButton, Tooltip, Tabs, Tab, CircularProgress, Divider, Alert, alpha,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  Close, LocalShipping, Description, Route, Timeline, Inventory, AttachMoney,
  NotificationsActive, AssignmentTurnedIn, Add, DeleteForever, CheckCircle, PlayArrow,
  DoneAll, ReportProblem, Edit,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Link as RouterLink } from 'react-router-dom'
import { tmsApi } from '@/api/tms'
import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

const TMS_COLOR = COLOR_MODULO

export interface ViajeDetalleDatos {
  id: number; codigo: string; estado: string; tipo_servicio?: string | null
  valor_flete?: number | null; origen_ciudad?: string | null; destino_ciudad?: string | null
  conductor_nombre?: string | null; vehiculo_placa?: string | null; vehiculo_id?: number | null
  distancia_km?: number | null; peso_kg?: number | null
  fecha_programada_cargue?: string | null; fecha_programada_entrega?: string | null
  fecha_real_cargue?: string | null; fecha_real_entrega?: string | null
  notas?: string | null
}

const fmt = (n?: number | null) => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n || 0)
const fmtFecha = (s?: string | null) => {
  if (!s) return '—'
  const d = aFecha(s)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
const errorDe = (e: any) => toast.error(e?.response?.data?.detail
  ? (typeof e.response.data.detail === 'string' ? e.response.data.detail : 'Revisa los datos del formulario')
  : 'No se pudo guardar')
/** Un datetime-local ("2026-09-29T14:30") con la zona del navegador. */
const aISO = (v: string) => (v ? aFecha(v).toISOString() : undefined)
const ahoraLocal = () => {
  const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

// ── Catálogos (enums del servidor) ──
const HITOS = [
  ['SALIDA_ORIGEN', 'Salida de origen'], ['LLEGADA_PARADA', 'Llegada a parada'],
  ['SALIDA_PARADA', 'Salida de parada'], ['ACTUALIZACION_GPS', 'Reporte de posición'],
  ['LLEGADA_DESTINO', 'Llegada a destino'],
]
const NOVEDADES = [
  ['INCIDENTE', 'Incidente'], ['RETRASO', 'Retraso'], ['DETENCION', 'Detención'],
  ['PARADA_NO_PROGRAMADA', 'Parada no programada'],
]
const ETIQUETA_EVENTO = Object.fromEntries([...HITOS, ...NOVEDADES])
const ES_NOVEDAD = new Set(NOVEDADES.map(n => n[0]))
const TIPOS_PARADA = [['ORIGEN', 'Origen'], ['PARADA_INTERMEDIA', 'Parada intermedia'], ['DESTINO', 'Destino'], ['CROSS_DOCK', 'Cross dock']]
const TIPOS_DOC = ['REMESA', 'MANIFIESTO', 'CUMPLIDO', 'POD', 'FACTURA', 'SEGURO', 'PERMISO', 'CARTA_PORTE']
const ESTADOS_DOC = ['PENDIENTE', 'GENERADO', 'FIRMADO', 'RECHAZADO', 'ANULADO']
const TIPOS_ALERTA = [
  ['RETRASO_VIAJE', 'Retraso del viaje'], ['DESVIO_RUTA', 'Desvío de ruta'], ['SIN_GPS', 'Sin señal GPS'],
  ['VELOCIDAD_EXCESIVA', 'Velocidad excesiva'], ['CONDUCTOR_SIN_DESCANSO', 'Conductor sin descanso'],
  ['VEHICULO_FUERA_SERVICIO', 'Vehículo fuera de servicio'], ['VENCIMIENTO_DOCUMENTO', 'Vencimiento de documento'],
]
const NIVELES = ['CRITICA', 'ALTA', 'MEDIA', 'BAJA', 'INFO']
const COLOR_NIVEL: Record<string, string> = { CRITICA: '#DC2626', ALTA: '#EA580C', MEDIA: '#D97706', BAJA: '#0369A1', INFO: '#6B7280' }
const COLOR_PARADA: Record<string, string> = { PENDIENTE: '#6B7280', EN_CURSO: '#D97706', COMPLETADA: '#15803D', SALTADA: '#DC2626' }
// Mientras el viaje está vivo se registra; cerrado o cancelado, solo se consulta.
const VIVO = new Set(['PROGRAMADO', 'ASIGNADO', 'EN_TRANSITO', 'ENTREGADO'])

const Vacio = ({ children }: { children: React.ReactNode }) =>
  <Typography color="text.secondary" fontSize={13} py={2} textAlign="center">{children}</Typography>
const Cargando = () => <Box textAlign="center" py={4}><CircularProgress size={24} /></Box>

// ─── Paradas ─────────────────────────────────────────────────────────────────
function ParadasTab({ viaje, editable }: { viaje: ViajeDetalleDatos; editable: boolean }) {
  const qc = useQueryClient()
  const clave = ['tms-paradas', viaje.id]
  const { data: paradas = [], isLoading } = useQuery({ queryKey: clave, queryFn: () => tmsApi.paradas(viaje.id) })
  const [abierto, setAbierto] = useState(false)
  const [f, setF] = useState({ tipo: 'PARADA_INTERMEDIA', ciudad: '', direccion: '', eta: '', contacto: '', telefono: '', observaciones: '' })
  const refrescar = () => qc.invalidateQueries({ queryKey: clave })

  const crear = useMutation({
    mutationFn: () => tmsApi.crearParada({
      viaje_id: viaje.id, secuencia: (paradas.reduce((m, p) => Math.max(m, p.secuencia), 0)) + 1,
      tipo: f.tipo, ciudad: f.ciudad.trim(), direccion: f.direccion.trim() || null,
      tiempo_estimado_llegada: aISO(f.eta) ?? null, contacto: f.contacto.trim() || null,
      telefono_contacto: f.telefono.trim() || null, observaciones: f.observaciones.trim() || null,
    }),
    onSuccess: () => { toast.success('Parada agregada'); refrescar(); setAbierto(false) },
    onError: errorDe,
  })
  const estado = useMutation({
    mutationFn: ({ id, e }: { id: number; e: string }) => {
      const ahora = new Date().toISOString()
      return tmsApi.estadoParada(id, e, e === 'EN_CURSO' ? { tiempo_real_llegada: ahora } : e === 'COMPLETADA' ? { tiempo_real_salida: ahora } : undefined)
    },
    onSuccess: () => { toast.success('Parada actualizada'); refrescar() },
    onError: errorDe,
  })
  const borrar = useMutation({
    mutationFn: (id: number) => tmsApi.borrarParada(id),
    onSuccess: () => { toast.success('Parada eliminada'); refrescar() },
    onError: errorDe,
  })

  return (
    <Box mt={1}>
      {editable && (
        <Stack direction="row" justifyContent="flex-end" mb={1}>
          <Button size="small" startIcon={<Add />} onClick={() => { setF({ tipo: paradas.length ? 'PARADA_INTERMEDIA' : 'ORIGEN', ciudad: '', direccion: '', eta: '', contacto: '', telefono: '', observaciones: '' }); setAbierto(true) }} sx={{ color: TMS_COLOR }}>
            Agregar parada
          </Button>
        </Stack>
      )}
      {isLoading ? <Cargando /> : paradas.length === 0 ? <Vacio>Este viaje no tiene paradas registradas.</Vacio> : (
        <Stack spacing={1}>
          {[...paradas].sort((a, b) => a.secuencia - b.secuencia).map(p => (
            <Paper key={p.id} elevation={0} sx={{ p: 1.5, border: '1px solid #E5E7EB', borderRadius: 2 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip label={p.secuencia} size="small" sx={{ bgcolor: TMS_COLOR, color: '#fff', fontWeight: 700, width: 28, height: 28 }} />
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography fontSize={13} fontWeight={600}>{p.ciudad} <Typography component="span" fontSize={11} color="text.secondary">({p.tipo.replace('_', ' ').toLowerCase()})</Typography></Typography>
                  <Typography fontSize={11} color="text.secondary">
                    {[p.direccion, p.tiempo_estimado_llegada && `ETA ${fmtFecha(p.tiempo_estimado_llegada)}`,
                      p.tiempo_real_llegada && `llegó ${fmtFecha(p.tiempo_real_llegada)}`,
                      p.tiempo_real_salida && `salió ${fmtFecha(p.tiempo_real_salida)}`, p.contacto].filter(Boolean).join(' · ') || '—'}
                  </Typography>
                </Box>
                <Chip label={p.estado.replace('_', ' ')} size="small" sx={{ fontWeight: 600, fontSize: 11, bgcolor: alpha(COLOR_PARADA[p.estado] ?? '#6B7280', 0.12), color: COLOR_PARADA[p.estado] ?? '#6B7280' }} />
                {editable && p.estado === 'PENDIENTE' && (
                  <Tooltip title="Marcar llegada"><IconButton size="small" aria-label={`Llegada a ${p.ciudad}`} onClick={() => estado.mutate({ id: p.id, e: 'EN_CURSO' })}><PlayArrow fontSize="small" /></IconButton></Tooltip>
                )}
                {editable && ['PENDIENTE', 'EN_CURSO'].includes(p.estado) && (<>
                  <Tooltip title="Marcar completada"><IconButton size="small" aria-label={`Completar ${p.ciudad}`} onClick={() => estado.mutate({ id: p.id, e: 'COMPLETADA' })}><DoneAll fontSize="small" sx={{ color: '#15803D' }} /></IconButton></Tooltip>
                  <Tooltip title="Saltar parada"><IconButton size="small" aria-label={`Saltar ${p.ciudad}`} onClick={() => estado.mutate({ id: p.id, e: 'SALTADA' })}><Close fontSize="small" /></IconButton></Tooltip>
                </>)}
                {editable && p.estado === 'PENDIENTE' && (
                  <Tooltip title="Eliminar"><IconButton size="small" aria-label={`Eliminar parada ${p.ciudad}`} onClick={() => { if (window.confirm(`¿Eliminar la parada en ${p.ciudad}?`)) borrar.mutate(p.id) }}><DeleteForever fontSize="small" sx={{ color: '#DC2626' }} /></IconButton></Tooltip>
                )}
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
      <Dialog open={abierto} onClose={() => setAbierto(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Agregar parada</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid size={{ xs: 12, sm: 5 }}>
              <TextField select label="Tipo" fullWidth size="small" value={f.tipo} onChange={e => setF({ ...f, tipo: e.target.value })}>
                {TIPOS_PARADA.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 7 }}><TextField label="Ciudad" required fullWidth size="small" value={f.ciudad} onChange={e => setF({ ...f, ciudad: e.target.value })} /></Grid>
            <Grid size={{ xs: 12 }}><TextField label="Dirección" fullWidth size="small" value={f.direccion} onChange={e => setF({ ...f, direccion: e.target.value })} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Llegada estimada" type="datetime-local" fullWidth size="small" InputLabelProps={{ shrink: true }} value={f.eta} onChange={e => setF({ ...f, eta: e.target.value })} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Contacto" fullWidth size="small" value={f.contacto} onChange={e => setF({ ...f, contacto: e.target.value })} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Teléfono" fullWidth size="small" value={f.telefono} onChange={e => setF({ ...f, telefono: e.target.value })} /></Grid>
            <Grid size={{ xs: 12 }}><TextField label="Observaciones" fullWidth size="small" multiline minRows={2} value={f.observaciones} onChange={e => setF({ ...f, observaciones: e.target.value })} /></Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(false)}>Cancelar</Button>
          <Button variant="contained" disabled={!f.ciudad.trim() || crear.isPending} onClick={() => crear.mutate()} sx={{ bgcolor: TMS_COLOR }}>Guardar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Tracking y novedades ────────────────────────────────────────────────────
function TrackingTab({ viaje, editable, onCambioViaje }: { viaje: ViajeDetalleDatos; editable: boolean; onCambioViaje: () => void }) {
  const qc = useQueryClient()
  const clave = ['tms-eventos', viaje.id]
  const { data: eventos = [], isLoading } = useQuery({ queryKey: clave, queryFn: () => tmsApi.eventos(viaje.id) })
  const [abierto, setAbierto] = useState<null | 'hito' | 'novedad'>(null)
  const [f, setF] = useState({ tipo: '', descripcion: '', lat: '', lng: '', velocidad: '' })

  const abrir = (tipo: 'hito' | 'novedad') => {
    setF({ tipo: tipo === 'hito' ? (viaje.estado === 'ASIGNADO' ? 'SALIDA_ORIGEN' : 'ACTUALIZACION_GPS') : 'RETRASO', descripcion: '', lat: '', lng: '', velocidad: '' })
    setAbierto(tipo)
  }
  const numero = (v: string) => (v.trim() === '' ? null : Number(v))
  const coordMal = (f.lat !== '' && (Number(f.lat) < -90 || Number(f.lat) > 90)) || (f.lng !== '' && (Number(f.lng) < -180 || Number(f.lng) > 180))
  const faltaDescripcion = abierto === 'novedad' && !f.descripcion.trim()

  const crear = useMutation({
    mutationFn: () => tmsApi.crearEvento({
      viaje_id: viaje.id, tipo_evento: f.tipo, descripcion: f.descripcion.trim() || null,
      lat: numero(f.lat), lng: numero(f.lng), velocidad_kmh: numero(f.velocidad),
    }),
    onSuccess: () => {
      toast.success(abierto === 'novedad' ? 'Novedad registrada' : 'Seguimiento registrado')
      qc.invalidateQueries({ queryKey: clave })
      // La llegada a destino entrega el viaje en el servidor.
      if (f.tipo === 'LLEGADA_DESTINO') onCambioViaje()
      setAbierto(null)
    },
    onError: errorDe,
  })

  return (
    <Box mt={1}>
      {editable && (
        <Stack direction="row" justifyContent="flex-end" gap={1} mb={1}>
          <Button size="small" startIcon={<Add />} onClick={() => abrir('hito')} sx={{ color: TMS_COLOR }}>Registrar seguimiento</Button>
          <Button size="small" startIcon={<ReportProblem />} color="warning" onClick={() => abrir('novedad')}>Reportar novedad</Button>
        </Stack>
      )}
      {isLoading ? <Cargando /> : eventos.length === 0 ? <Vacio>Sin eventos de tracking registrados.</Vacio> : (
        <Stack spacing={1}>
          {[...eventos].sort((a, b) => (b.timestamp ?? '').localeCompare(a.timestamp ?? '')).map(ev => {
            const novedad = ES_NOVEDAD.has(ev.tipo_evento)
            return (
              <Stack key={ev.id} direction="row" spacing={2} alignItems="flex-start">
                <Typography fontSize={12} fontWeight={600} color="text.secondary" sx={{ minWidth: 118 }}>{fmtFecha(ev.timestamp)}</Typography>
                <Box sx={{ width: 3, bgcolor: novedad ? '#D97706' : TMS_COLOR, borderRadius: 1, mt: 0.5, alignSelf: 'stretch', opacity: novedad ? 0.8 : 0.3 }} />
                <Box>
                  <Stack direction="row" gap={1} alignItems="center">
                    <Typography fontSize={13} fontWeight={600}>{ETIQUETA_EVENTO[ev.tipo_evento] ?? ev.tipo_evento}</Typography>
                    {novedad && <Chip label="Novedad" size="small" sx={{ height: 18, fontSize: 10, bgcolor: alpha('#D97706', 0.12), color: '#B45309' }} />}
                  </Stack>
                  {ev.descripcion && <Typography fontSize={12} color="text.secondary">{ev.descripcion}</Typography>}
                  {(ev.lat != null || ev.velocidad_kmh != null) && (
                    <Typography fontSize={11} color="text.disabled">
                      {[ev.lat != null && ev.lng != null && `${ev.lat.toFixed(5)}, ${ev.lng.toFixed(5)}`, ev.velocidad_kmh != null && `${ev.velocidad_kmh} km/h`].filter(Boolean).join(' · ')}
                    </Typography>
                  )}
                </Box>
              </Stack>
            )
          })}
        </Stack>
      )}
      <Dialog open={!!abierto} onClose={() => setAbierto(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{abierto === 'novedad' ? 'Reportar novedad' : 'Registrar seguimiento'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid size={{ xs: 12 }}>
              <TextField select label={abierto === 'novedad' ? 'Tipo de novedad' : 'Evento'} fullWidth size="small" value={f.tipo} onChange={e => setF({ ...f, tipo: e.target.value })}>
                {(abierto === 'novedad' ? NOVEDADES : HITOS).map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
              </TextField>
            </Grid>
            {f.tipo === 'LLEGADA_DESTINO' && viaje.estado === 'EN_TRANSITO' && (
              <Grid size={{ xs: 12 }}><Alert severity="info">Registrar la llegada a destino marca el viaje como ENTREGADO.</Alert></Grid>
            )}
            <Grid size={{ xs: 12 }}>
              <TextField label={abierto === 'novedad' ? 'Qué pasó' : 'Descripción'} required={abierto === 'novedad'} fullWidth size="small" multiline minRows={2}
                value={f.descripcion} onChange={e => setF({ ...f, descripcion: e.target.value })} />
            </Grid>
            <Grid size={{ xs: 6, sm: 4 }}><TextField label="Latitud" type="number" fullWidth size="small" value={f.lat} onChange={e => setF({ ...f, lat: e.target.value })} /></Grid>
            <Grid size={{ xs: 6, sm: 4 }}><TextField label="Longitud" type="number" fullWidth size="small" value={f.lng} onChange={e => setF({ ...f, lng: e.target.value })} /></Grid>
            <Grid size={{ xs: 12, sm: 4 }}><TextField label="Velocidad (km/h)" type="number" fullWidth size="small" value={f.velocidad} onChange={e => setF({ ...f, velocidad: e.target.value })} /></Grid>
            {coordMal && <Grid size={{ xs: 12 }}><Typography fontSize={12} color="error">La latitud va de -90 a 90 y la longitud de -180 a 180.</Typography></Grid>}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!f.tipo || coordMal || faltaDescripcion || crear.isPending} onClick={() => crear.mutate()} sx={{ bgcolor: TMS_COLOR }}>Guardar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Documentos ──────────────────────────────────────────────────────────────
export function DocumentosTab({ viaje, editable }: { viaje: ViajeDetalleDatos; editable: boolean }) {
  const qc = useQueryClient()
  const clave = ['tms-docs', viaje.id]
  const { data: documentos = [], isLoading } = useQuery({ queryKey: clave, queryFn: () => tmsApi.documentos(viaje.id) })
  const [dlg, setDlg] = useState<{ abierto: boolean; id: number | null }>({ abierto: false, id: null })
  const [f, setF] = useState({ tipo_documento: 'REMESA', numero: '', fecha_emision: '', estado: 'GENERADO', archivo_url: '', observaciones: '' })
  const refrescar = () => { qc.invalidateQueries({ queryKey: clave }); qc.invalidateQueries({ queryKey: ['tms-docs-pendientes'] }) }

  const abrir = (d?: any) => {
    setF(d ? { tipo_documento: d.tipo_documento, numero: d.numero ?? '', fecha_emision: d.fecha_emision ?? '', estado: d.estado, archivo_url: d.archivo_url ?? '', observaciones: d.observaciones ?? '' }
      : { tipo_documento: 'REMESA', numero: '', fecha_emision: new Date().toISOString().slice(0, 10), estado: 'GENERADO', archivo_url: '', observaciones: '' })
    setDlg({ abierto: true, id: d?.id ?? null })
  }
  const guardar = useMutation({
    mutationFn: async () => {
      const cuerpo = {
        tipo_documento: f.tipo_documento, numero: f.numero.trim() || null,
        fecha_emision: f.fecha_emision || null, archivo_url: f.archivo_url.trim() || null,
        observaciones: f.observaciones.trim() || null,
      }
      if (dlg.id) return tmsApi.editarDocumento(dlg.id, { ...cuerpo, estado: f.estado })
      // El alta no acepta estado: se crea y, si no es el de por defecto, se ajusta.
      const nuevo = await tmsApi.crearDocumento({ viaje_id: viaje.id, ...cuerpo })
      return nuevo.estado !== f.estado ? tmsApi.editarDocumento(nuevo.id, { estado: f.estado }) : nuevo
    },
    onSuccess: () => { toast.success(dlg.id ? 'Documento actualizado' : 'Documento agregado'); refrescar(); setDlg({ abierto: false, id: null }) },
    onError: errorDe,
  })
  const borrar = useMutation({
    mutationFn: (id: number) => tmsApi.borrarDocumento(id),
    onSuccess: () => { toast.success('Documento eliminado'); refrescar() },
    onError: errorDe,
  })

  return (
    <Box mt={1}>
      {editable && (
        <Stack direction="row" justifyContent="flex-end" mb={1}>
          <Button size="small" startIcon={<Add />} onClick={() => abrir()} sx={{ color: TMS_COLOR }}>Agregar documento</Button>
        </Stack>
      )}
      {isLoading ? <Cargando /> : documentos.length === 0 ? <Vacio>Sin documentos asociados al viaje.</Vacio> : (
        <Stack spacing={1}>
          {documentos.map(doc => (
            <Paper key={doc.id} elevation={0} sx={{ p: 1.5, border: '1px solid #E5E7EB', borderRadius: 2 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                  <Description sx={{ fontSize: 16, color: TMS_COLOR }} />
                  <Box sx={{ minWidth: 0 }}>
                    <Typography fontSize={13}>{doc.tipo_documento}{doc.numero ? ` — ${doc.numero}` : ''}</Typography>
                    <Typography fontSize={11} color="text.secondary" noWrap>
                      {[doc.fecha_emision, doc.observaciones].filter(Boolean).join(' · ') || '—'}
                    </Typography>
                  </Box>
                </Stack>
                <Stack direction="row" alignItems="center" gap={0.5}>
                  {doc.archivo_url && <Button size="small" href={doc.archivo_url} target="_blank" rel="noopener">Abrir</Button>}
                  <Chip label={doc.estado} size="small" sx={{ fontWeight: 600, fontSize: 11 }} />
                  {editable && <IconButton size="small" aria-label={`Editar ${doc.tipo_documento}`} onClick={() => abrir(doc)}><Edit fontSize="small" /></IconButton>}
                  {editable && <IconButton size="small" aria-label={`Eliminar ${doc.tipo_documento}`} onClick={() => { if (window.confirm(`¿Eliminar ${doc.tipo_documento} ${doc.numero ?? ''}?`)) borrar.mutate(doc.id) }}><DeleteForever fontSize="small" sx={{ color: '#DC2626' }} /></IconButton>}
                </Stack>
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
      <Dialog open={dlg.abierto} onClose={() => setDlg({ abierto: false, id: null })} maxWidth="sm" fullWidth>
        <DialogTitle>{dlg.id ? 'Editar documento' : 'Agregar documento'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Tipo de documento" fullWidth size="small" value={f.tipo_documento} onChange={e => setF({ ...f, tipo_documento: e.target.value })}>
                {TIPOS_DOC.map(t => <MenuItem key={t} value={t}>{t.replace('_', ' ')}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Número" fullWidth size="small" value={f.numero} onChange={e => setF({ ...f, numero: e.target.value })} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}><TextField label="Fecha de emisión" type="date" fullWidth size="small" InputLabelProps={{ shrink: true }} value={f.fecha_emision} onChange={e => setF({ ...f, fecha_emision: e.target.value })} /></Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Estado" fullWidth size="small" value={f.estado} onChange={e => setF({ ...f, estado: e.target.value })}>
                {ESTADOS_DOC.map(t => <MenuItem key={t} value={t}>{t}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}><TextField label="Enlace al archivo" placeholder="https://…" fullWidth size="small" value={f.archivo_url} onChange={e => setF({ ...f, archivo_url: e.target.value })} /></Grid>
            <Grid size={{ xs: 12 }}><TextField label="Observaciones" fullWidth size="small" multiline minRows={2} value={f.observaciones} onChange={e => setF({ ...f, observaciones: e.target.value })} /></Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlg({ abierto: false, id: null })}>Cancelar</Button>
          <Button variant="contained" disabled={guardar.isPending} onClick={() => guardar.mutate()} sx={{ bgcolor: TMS_COLOR }}>Guardar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Alertas ─────────────────────────────────────────────────────────────────
function AlertasTab({ viaje, editable }: { viaje: ViajeDetalleDatos; editable: boolean }) {
  const qc = useQueryClient()
  const clave = ['tms-alertas-viaje', viaje.id]
  const { data: alertas = [], isLoading } = useQuery({ queryKey: clave, queryFn: () => tmsApi.alertas({ viaje_id: viaje.id }) })
  const [abierto, setAbierto] = useState(false)
  const [f, setF] = useState({ tipo: 'RETRASO_VIAJE', nivel: 'MEDIA', mensaje: '' })
  const refrescar = () => { qc.invalidateQueries({ queryKey: clave }); qc.invalidateQueries({ queryKey: ['tms-alertas'] }) }

  const crear = useMutation({
    mutationFn: () => tmsApi.crearAlerta({ ...f, mensaje: f.mensaje.trim(), viaje_id: viaje.id, vehiculo_id: viaje.vehiculo_id ?? null }),
    onSuccess: () => { toast.success('Alerta creada'); refrescar(); setAbierto(false) },
    onError: errorDe,
  })
  const leer = useMutation({
    mutationFn: (id: number) => tmsApi.leerAlerta(id),
    onSuccess: () => { toast.success('Alerta atendida'); refrescar() },
    onError: errorDe,
  })

  return (
    <Box mt={1}>
      {editable && (
        <Stack direction="row" justifyContent="flex-end" mb={1}>
          <Button size="small" startIcon={<Add />} onClick={() => { setF({ tipo: 'RETRASO_VIAJE', nivel: 'MEDIA', mensaje: '' }); setAbierto(true) }} sx={{ color: TMS_COLOR }}>Crear alerta</Button>
        </Stack>
      )}
      {isLoading ? <Cargando /> : alertas.length === 0 ? <Vacio>Este viaje no tiene alertas.</Vacio> : (
        <Stack spacing={1}>
          {alertas.map(a => (
            <Paper key={a.id} elevation={0} sx={{ p: 1.5, border: `1px solid ${alpha(COLOR_NIVEL[a.nivel] ?? '#6B7280', a.leida ? 0.15 : 0.4)}`, borderRadius: 2, opacity: a.leida ? 0.65 : 1 }}>
              <Stack direction="row" alignItems="center" gap={1}>
                <Chip label={a.nivel} size="small" sx={{ fontWeight: 700, fontSize: 10, height: 20, bgcolor: alpha(COLOR_NIVEL[a.nivel] ?? '#6B7280', 0.12), color: COLOR_NIVEL[a.nivel] ?? '#6B7280' }} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography fontSize={13} fontWeight={600}>{a.mensaje}</Typography>
                  <Typography fontSize={11} color="text.secondary">{(TIPOS_ALERTA.find(t => t[0] === a.tipo)?.[1]) ?? a.tipo} · {fmtFecha(a.fecha_alerta)}</Typography>
                </Box>
                {a.leida ? <Chip label="Atendida" size="small" icon={<CheckCircle />} sx={{ fontSize: 11 }} />
                  : <Button size="small" onClick={() => leer.mutate(a.id)}>Marcar atendida</Button>}
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
      <Dialog open={abierto} onClose={() => setAbierto(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Crear alerta</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid size={{ xs: 12, sm: 7 }}>
              <TextField select label="Tipo" fullWidth size="small" value={f.tipo} onChange={e => setF({ ...f, tipo: e.target.value })}>
                {TIPOS_ALERTA.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 5 }}>
              <TextField select label="Nivel" fullWidth size="small" value={f.nivel} onChange={e => setF({ ...f, nivel: e.target.value })}>
                {NIVELES.map(n => <MenuItem key={n} value={n}>{n}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}><TextField label="Mensaje" required fullWidth size="small" multiline minRows={2} value={f.mensaje} onChange={e => setF({ ...f, mensaje: e.target.value })} /></Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(false)}>Cancelar</Button>
          <Button variant="contained" disabled={!f.mensaje.trim() || crear.isPending} onClick={() => crear.mutate()} sx={{ bgcolor: TMS_COLOR }}>Guardar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Entrega (POD) ───────────────────────────────────────────────────────────
export function EntregaTab({ viaje, editable }: { viaje: ViajeDetalleDatos; editable: boolean }) {
  const qc = useQueryClient()
  const clave = ['tms-pod', viaje.id]
  const { data: pod, isLoading } = useQuery({ queryKey: clave, queryFn: () => tmsApi.pod(viaje.id) })
  const [f, setF] = useState({ receptor_nombre: '', receptor_documento: '', fecha_hora: ahoraLocal(), foto_url: '', observaciones: '' })
  const crear = useMutation({
    mutationFn: () => tmsApi.crearPod({
      viaje_id: viaje.id, receptor_nombre: f.receptor_nombre.trim(), receptor_documento: f.receptor_documento.trim() || null,
      fecha_hora: aISO(f.fecha_hora) ?? null, foto_url: f.foto_url.trim() || null, observaciones: f.observaciones.trim() || null,
    }),
    onSuccess: () => {
      toast.success('Prueba de entrega registrada')
      qc.invalidateQueries({ queryKey: clave }); qc.invalidateQueries({ queryKey: ['tms-pods'] }); qc.invalidateQueries({ queryKey: ['tms-docs-pendientes'] })
    },
    onError: errorDe,
  })

  if (isLoading) return <Cargando />
  if (pod) return (
    <Grid container spacing={2} mt={0}>
      {[['Recibió', pod.receptor_nombre || '—'], ['Documento', pod.receptor_documento || '—'], ['Fecha y hora', fmtFecha(pod.fecha_hora)],
        ['Ubicación', pod.lat != null && pod.lng != null ? `${pod.lat.toFixed(5)}, ${pod.lng.toFixed(5)}` : '—']].map(([l, v]) => (
        <Grid key={l} size={{ xs: 12, sm: 6 }}><Typography fontSize={12} color="text.secondary">{l}</Typography><Typography fontWeight={600}>{v}</Typography></Grid>
      ))}
      {pod.observaciones && <Grid size={{ xs: 12 }}><Typography fontSize={12} color="text.secondary">Observaciones</Typography><Typography fontSize={13}>{pod.observaciones}</Typography></Grid>}
      {pod.foto_url && <Grid size={{ xs: 12 }}><Button size="small" href={pod.foto_url} target="_blank" rel="noopener">Ver foto de la entrega</Button></Grid>}
    </Grid>
  )
  if (!editable || !['EN_TRANSITO', 'ENTREGADO'].includes(viaje.estado)) {
    return <Vacio>La prueba de entrega se registra cuando el viaje está en tránsito o entregado.</Vacio>
  }
  return (
    <Box mt={1}>
      <Typography fontSize={13} color="text.secondary" mb={2}>Quién recibió la carga y cuándo. Sin esta prueba, el viaje figura con documentos pendientes.</Typography>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 7 }}><TextField label="Nombre de quien recibe" required fullWidth size="small" value={f.receptor_nombre} onChange={e => setF({ ...f, receptor_nombre: e.target.value })} /></Grid>
        <Grid size={{ xs: 12, sm: 5 }}><TextField label="Documento" fullWidth size="small" value={f.receptor_documento} onChange={e => setF({ ...f, receptor_documento: e.target.value })} /></Grid>
        <Grid size={{ xs: 12, sm: 6 }}><TextField label="Fecha y hora de entrega" type="datetime-local" fullWidth size="small" InputLabelProps={{ shrink: true }} value={f.fecha_hora} onChange={e => setF({ ...f, fecha_hora: e.target.value })} /></Grid>
        <Grid size={{ xs: 12, sm: 6 }}><TextField label="Enlace a la foto" fullWidth size="small" value={f.foto_url} onChange={e => setF({ ...f, foto_url: e.target.value })} /></Grid>
        <Grid size={{ xs: 12 }}><TextField label="Observaciones" fullWidth size="small" multiline minRows={2} value={f.observaciones} onChange={e => setF({ ...f, observaciones: e.target.value })} /></Grid>
        <Grid size={{ xs: 12 }}>
          <Button variant="contained" startIcon={<AssignmentTurnedIn />} disabled={!f.receptor_nombre.trim() || crear.isPending} onClick={() => crear.mutate()} sx={{ bgcolor: TMS_COLOR }}>
            Registrar prueba de entrega
          </Button>
        </Grid>
      </Grid>
    </Box>
  )
}

// ─── Costos (consulta; se editan en el Motor de costos) ─────────────────────
function CostosTab({ viaje }: { viaje: ViajeDetalleDatos }) {
  const { data: lista = [], isLoading } = useQuery({ queryKey: ['tms-costos-lista', 'viaje', viaje.id], queryFn: () => tmsApi.costos() })
  const c = lista.find(v => v.viaje_id === viaje.id)?.costo
  if (isLoading) return <Cargando />
  if (!c) return (
    <Box textAlign="center" py={3}>
      <Typography color="text.secondary" fontSize={13} mb={1}>Este viaje aún no tiene costos registrados.</Typography>
      <Button size="small" component={RouterLink} to="/tms/costos" sx={{ color: TMS_COLOR }}>Registrarlos en el motor de costos</Button>
    </Box>
  )
  return (
    <Stack spacing={1} mt={1}>
      {[['Combustible', c.combustible], ['Peajes', c.peajes], ['Viáticos', c.viaticos], ['Horas extras', c.horas_extras], ['Mantenimiento', c.mantenimiento], ['Costos indirectos', c.costos_indirectos]].map(([l, v]) => (
        <Stack key={l as string} direction="row" justifyContent="space-between" sx={{ py: 1, borderBottom: '1px solid #F3F4F6' }}>
          <Typography fontSize={13}>{l}</Typography><Typography fontSize={13} fontWeight={600}>{fmt(v as number)}</Typography>
        </Stack>
      ))}
      <Stack direction="row" justifyContent="space-between" sx={{ pt: 1 }}><Typography fontWeight={700}>Costo total</Typography><Typography fontWeight={700} color={TMS_COLOR}>{fmt(c.costo_total)}</Typography></Stack>
      <Stack direction="row" justifyContent="space-between"><Typography fontSize={13}>Flete cobrado</Typography><Typography fontSize={13} fontWeight={600}>{fmt(c.valor_flete_cobrado)}</Typography></Stack>
      <Stack direction="row" justifyContent="space-between"><Typography fontWeight={700}>Margen</Typography><Typography fontWeight={700} color={c.margen >= 0 ? '#15803D' : '#DC2626'}>{fmt(c.margen)}{c.margen_pct != null ? ` (${c.margen_pct.toFixed(1)}%)` : ''}</Typography></Stack>
      <Box textAlign="right"><Button size="small" component={RouterLink} to="/tms/costos" sx={{ color: TMS_COLOR }}>Editar en el motor de costos</Button></Box>
    </Stack>
  )
}

// ─── Diálogo ─────────────────────────────────────────────────────────────────
export function ViajeDetalleDialog({ viaje, open, onClose, onAccion, estadoChip, onCambioViaje }: {
  viaje: ViajeDetalleDatos | null; open: boolean; onClose: () => void
  onAccion: (accion: string, id: number) => void
  estadoChip: (estado: string) => React.ReactNode
  onCambioViaje: () => void
}) {
  const [tab, setTab] = useState(0)
  if (!viaje) return null
  const editable = VIVO.has(viaje.estado)

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack direction="row" alignItems="center" spacing={1}>
            <LocalShipping sx={{ color: TMS_COLOR }} />
            <Typography fontWeight={700}>{viaje.codigo}</Typography>
            {estadoChip(viaje.estado)}
          </Stack>
          <IconButton size="small" aria-label="Cerrar detalle" onClick={onClose}><Close /></IconButton>
        </Stack>
      </DialogTitle>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ px: 3, borderBottom: '1px solid #E5E7EB' }}>
        <Tab icon={<Description />} iconPosition="start" label="Información" sx={{ fontSize: 13 }} />
        <Tab icon={<Route />} iconPosition="start" label="Paradas" sx={{ fontSize: 13 }} />
        <Tab icon={<Timeline />} iconPosition="start" label="Tracking y novedades" sx={{ fontSize: 13 }} />
        <Tab icon={<Inventory />} iconPosition="start" label="Documentos" sx={{ fontSize: 13 }} />
        <Tab icon={<NotificationsActive />} iconPosition="start" label="Alertas" sx={{ fontSize: 13 }} />
        <Tab icon={<AssignmentTurnedIn />} iconPosition="start" label="Entrega (POD)" sx={{ fontSize: 13 }} />
        <Tab icon={<AttachMoney />} iconPosition="start" label="Costos" sx={{ fontSize: 13 }} />
      </Tabs>
      <DialogContent sx={{ minHeight: 300 }}>
        {!editable && tab > 0 && tab < 6 && (
          <Alert severity="info" sx={{ mb: 1 }}>El viaje está {viaje.estado.toLowerCase()}: su historia se consulta pero ya no se modifica.</Alert>
        )}
        {tab === 0 && (
          <Grid container spacing={2} mt={0}>
            {[
              ['Valor flete', fmt(viaje.valor_flete)], ['Origen', viaje.origen_ciudad || '—'], ['Destino', viaje.destino_ciudad || '—'],
              ['Conductor', viaje.conductor_nombre || '—'], ['Placa', viaje.vehiculo_placa || '—'],
              ['Distancia', viaje.distancia_km ? `${viaje.distancia_km} km` : '—'], ['Peso', viaje.peso_kg ? `${viaje.peso_kg} kg` : '—'],
              ['Cargue programado', fmtFecha(viaje.fecha_programada_cargue)], ['Entrega programada', fmtFecha(viaje.fecha_programada_entrega)],
              ['Cargue real', fmtFecha(viaje.fecha_real_cargue)], ['Entrega real', fmtFecha(viaje.fecha_real_entrega)],
            ].map(([label, value]) => (
              <Grid key={label} size={{ xs: 12, md: 6 }}>
                <Typography fontSize={12} color="text.secondary">{label}</Typography>
                <Typography fontWeight={600}>{value}</Typography>
              </Grid>
            ))}
            {viaje.notas && (
              <Grid size={{ xs: 12 }}><Divider sx={{ mb: 1 }} /><Typography fontSize={12} color="text.secondary">Notas</Typography><Typography fontSize={13}>{viaje.notas}</Typography></Grid>
            )}
          </Grid>
        )}
        {tab === 1 && <ParadasTab viaje={viaje} editable={editable} />}
        {tab === 2 && <TrackingTab viaje={viaje} editable={editable && viaje.estado !== 'PROGRAMADO'} onCambioViaje={onCambioViaje} />}
        {tab === 3 && <DocumentosTab viaje={viaje} editable={editable} />}
        {tab === 4 && <AlertasTab viaje={viaje} editable={editable} />}
        {tab === 5 && <EntregaTab viaje={viaje} editable={editable} />}
        {tab === 6 && <CostosTab viaje={viaje} />}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
        {viaje.estado === 'PROGRAMADO' && <Button variant="outlined" size="small" onClick={() => { onAccion('ASIGNADO', viaje.id); onClose() }}>Asignar</Button>}
        {viaje.estado === 'ASIGNADO' && <Button variant="contained" size="small" sx={{ bgcolor: TMS_COLOR }} onClick={() => { onAccion('EN_TRANSITO', viaje.id); onClose() }}>Iniciar</Button>}
        {viaje.estado === 'EN_TRANSITO' && <Button variant="contained" size="small" color="success" onClick={() => { onAccion('ENTREGADO', viaje.id); onClose() }}>Registrar entrega</Button>}
        {viaje.estado === 'ENTREGADO' && <Button variant="outlined" size="small" onClick={() => { onAccion('CERRADO', viaje.id); onClose() }}>Cerrar</Button>}
        {['PROGRAMADO', 'ASIGNADO'].includes(viaje.estado) && <Button variant="outlined" size="small" color="error" onClick={() => { onAccion('CANCELADO', viaje.id); onClose() }}>Cancelar</Button>}
        <Button onClick={onClose}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  )
}
