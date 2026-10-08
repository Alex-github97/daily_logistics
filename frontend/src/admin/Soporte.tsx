/**
 * Mesa de ayuda, del lado del equipo — consola del operador.
 *
 * La cola es de todas las empresas y se ordena por última actividad, no por
 * fecha de creación: lo que acaba de moverse es lo que necesita atención.
 *
 * La criticidad la fija acá el equipo y no quien reporta. Todo el mundo cree
 * que lo suyo es urgente; si la decidiera el usuario, la cola dejaría de
 * ordenar nada.
 */
import { useRef, useState } from 'react'
import {
  Box, Card, Typography, Stack, Button, MenuItem, Chip, Skeleton, Table, TableBody, TableCell, TableHead, TableRow, IconButton, Tooltip, Divider, FormControlLabel, Switch, Alert, Tabs, Tab,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  ArrowBack, AttachFile, Send, InsertDriveFile, Download, SupportAgent, Refresh,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { soporteApi, gestionApi, mensajeDeError, type Ticket, type Adjunto } from './api'
import Tablero from './Tablero'
import Backlog from './Backlog'
import MetricasAgiles from './MetricasAgiles'

const ESTADOS = ['NUEVO', 'EN_PROGRESO', 'ESPERANDO_CLIENTE', 'RESUELTO', 'CERRADO']
const CRITICIDADES = ['BAJA', 'MEDIA', 'ALTA', 'CRITICA']

const NOMBRE_ESTADO: Record<string, string> = {
  NUEVO: 'Nuevo', EN_PROGRESO: 'En progreso',
  ESPERANDO_CLIENTE: 'Esperando cliente', RESUELTO: 'Resuelto', CERRADO: 'Cerrado',
}
const COLOR_ESTADO: Record<string, string> = {
  NUEVO: COLOR_MODULO, EN_PROGRESO: ESTADO.alerta,
  ESPERANDO_CLIENTE: PALETA.grafito, RESUELTO: ESTADO.exito, CERRADO: PALETA.acero,
}
const COLOR_CRIT: Record<string, string> = {
  BAJA: PALETA.acero, MEDIA: COLOR_MODULO, ALTA: ESTADO.alerta, CRITICA: ESTADO.peligro,
}

const cuando = (iso?: string | null) => {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  return isNaN(d.getTime()) ? '—'
    : d.toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })
}

/** Cuánto lleva esperando, que es lo que de verdad importa en una cola. */
const espera = (iso?: string | null) => {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z').getTime()
  if (isNaN(d)) return ''
  const h = Math.floor((Date.now() - d) / 3600000)
  if (h < 1) return 'hace minutos'
  if (h < 24) return `hace ${h} h`
  return `hace ${Math.floor(h / 24)} d`
}

const peso = (b?: number | null) =>
  !b ? '' : b < 1024 ? `${b} B` : b < 1048576 ? `${Math.round(b / 1024)} KB`
    : `${(b / 1048576).toFixed(1)} MB`

async function descargar(a: Adjunto) {
  try {
    const datos = await soporteApi.descargarAdjunto(a.id)
    const url = URL.createObjectURL(datos)
    const el = document.createElement('a')
    el.href = url; el.download = a.nombre
    document.body.appendChild(el); el.click(); el.remove()
    URL.revokeObjectURL(url)
  } catch {
    toast.error('No se pudo descargar el archivo')
  }
}

// ─── Ficha del ticket ─────────────────────────────────────────────────────────

/** Convierte la solicitud en trabajo interno del equipo.
 *
 *  Copia el asunto del cliente como titulo de la incidencia y deja el ticket
 *  intacto: el cliente sigue viendo en su conversacion exactamente lo que
 *  escribio. Llamarla dos veces devuelve la misma incidencia, no crea otra, asi
 *  que el boton no necesita saber si ya se pulso antes.
 */
function ConvertirEnIncidencia({ ticketId }: { ticketId: number }) {
  const convertir = useMutation({
    mutationFn: () => gestionApi.desdeTicket(ticketId),
    onSuccess: inc => toast.success(
      `Es ${inc.clave}. Esta en Proyectos, sin clasificar.`, { duration: 5000 }),
    onError: (e: any) => toast.error(
      mensajeDeError(e, 'No se pudo convertir en incidencia')),
  })

  return (
    <Tooltip title="Pasarla al tablero del equipo como trabajo interno. El asunto del cliente no se toca.">
      <span>
        <Button
          size="small" variant="outlined" disabled={convertir.isPending}
          onClick={() => convertir.mutate()}
          sx={{ textTransform: 'none', whiteSpace: 'nowrap' }}
        >
          Convertir en incidencia
        </Button>
      </span>
    </Tooltip>
  )
}


function Ficha({ id, onVolver }: { id: number; onVolver: () => void }) {
  const qc = useQueryClient()
  const [texto, setTexto] = useState('')
  const [interno, setInterno] = useState(false)
  const [archivos, setArchivos] = useState<File[]>([])
  const entrada = useRef<HTMLInputElement>(null)

  const { data: t, isLoading } = useQuery<Ticket>({
    queryKey: ['soporte-ticket', id],
    queryFn: () => soporteApi.ticket(id),
    refetchInterval: 30000,
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['soporte-ticket', id] })
    qc.invalidateQueries({ queryKey: ['soporte-cola'] })
    qc.invalidateQueries({ queryKey: ['soporte-resumen'] })
  }

  const clasificar = useMutation({
    mutationFn: (cambios: Record<string, unknown>) => soporteApi.clasificar(id, cambios),
    onSuccess: () => { refrescar(); toast.success('Requerimiento actualizado') },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const responder = useMutation({
    mutationFn: async () => {
      if (archivos.length) {
        const cuerpo = new FormData()
        archivos.forEach(a => cuerpo.append('archivos', a))
        if (texto.trim()) cuerpo.append('cuerpo', texto.trim())
        await soporteApi.adjuntar(id, cuerpo)
      } else {
        await soporteApi.responder(id, texto.trim(), interno)
      }
    },
    onSuccess: () => { setTexto(''); setArchivos([]); setInterno(false); refrescar() },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  if (isLoading || !t) return <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 3 }} />

  // Nota: el asunto que se ve arriba es el del cliente y no cambia nunca. Al
  // convertir la solicitud en trabajo interno, ese asunto se COPIA al título de
  // la incidencia y desde ahí el equipo lo reescribe; acá sigue tal cual, que es
  // lo que el cliente ve en su conversación y la evidencia de qué pidió.

  return (
    <Box>
      <Stack direction="row" alignItems="flex-start" spacing={1.5} mb={2}>
        <IconButton onClick={onVolver}><ArrowBack /></IconButton>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="caption" sx={{
              fontFamily: 'monospace', fontWeight: 700, color: PALETA.grafito,
            }}>
              {t.numero}
            </Typography>
            <Chip label={t.cliente_codigo} size="small" variant="outlined"
              sx={{ height: 20, fontSize: 11, fontFamily: 'monospace' }} />
            {t.modulo && <Chip label={t.modulo} size="small" sx={{ height: 20, fontSize: 11 }} />}
            {!t.primera_respuesta_en && (
              <Chip label="Sin responder" size="small" sx={{
                height: 20, fontSize: 11, fontWeight: 700,
                bgcolor: `${ESTADO.peligro}1A`, color: ESTADO.peligro,
              }} />
            )}
          </Stack>
          <Typography variant="h6" fontWeight={800} sx={{ mt: 0.25 }}>{t.asunto}</Typography>
          <Typography variant="caption" color="text.secondary">
            Abierto por {t.autor} · {cuando(t.created_at)} · impacto declarado:{' '}
            {t.impacto ?? '—'}
          </Typography>
        </Box>
        <ConvertirEnIncidencia ticketId={t.id} />
        <Tooltip title="Actualizar">
          <IconButton onClick={refrescar}><Refresh /></IconButton>
        </Tooltip>
      </Stack>

      {/* Clasificación */}
      <Card sx={{ borderRadius: 3, p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField
            select label="Estado" size="small" value={t.estado} fullWidth
            onChange={e => clasificar.mutate({ estado: e.target.value })}
          >
            {ESTADOS.map(e => <MenuItem key={e} value={e}>{NOMBRE_ESTADO[e]}</MenuItem>)}
          </TextField>
          <TextField
            select label="Criticidad" size="small" value={t.criticidad} fullWidth
            onChange={e => clasificar.mutate({ criticidad: e.target.value })}
            helperText="La fija el equipo, no el cliente"
          >
            {CRITICIDADES.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
          </TextField>
          <TextField
            label="Asignado a" size="small" fullWidth defaultValue={t.asignado_a ?? ''}
            onBlur={e => {
              if (e.target.value !== (t.asignado_a ?? '')) {
                clasificar.mutate({ asignado_a: e.target.value || null })
              }
            }}
            helperText="Se guarda al salir del campo"
          />
        </Stack>
      </Card>

      {/* Conversación */}
      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2 }}>
        <Stack spacing={2}>
          {(t.conversacion ?? []).map(m => (
            <Box key={m.id} sx={{
              alignSelf: m.es_soporte ? 'flex-end' : 'flex-start',
              maxWidth: '85%',
              bgcolor: m.interno ? `${ESTADO.alerta}14`
                : m.es_soporte ? `${COLOR_MODULO}0F` : PALETA.bruma,
              border: `1px solid ${m.interno ? `${ESTADO.alerta}55`
                : m.es_soporte ? `${COLOR_MODULO}33` : PALETA.niebla}`,
              borderRadius: 2, p: 1.75,
            }}>
              <Stack direction="row" alignItems="center" spacing={0.75} mb={0.75}>
                {m.es_soporte && <SupportAgent sx={{ fontSize: 15, color: COLOR_MODULO }} />}
                <Typography variant="caption" fontWeight={700}>
                  {m.es_soporte ? `${m.autor} (soporte)` : m.autor}
                </Typography>
                {m.interno && (
                  <Chip label="Nota interna · el cliente no la ve" size="small" sx={{
                    height: 17, fontSize: 9.5, fontWeight: 700,
                    bgcolor: `${ESTADO.alerta}26`, color: ESTADO.alerta,
                  }} />
                )}
                <Typography variant="caption" color="text.secondary">
                  · {cuando(m.creado_en)}
                </Typography>
              </Stack>
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{m.cuerpo}</Typography>
              {m.adjuntos.length > 0 && (
                <Stack direction="row" flexWrap="wrap" gap={0.75} mt={1.25}>
                  {m.adjuntos.map(a => (
                    <Chip
                      key={a.id} size="small" icon={<InsertDriveFile sx={{ fontSize: 15 }} />}
                      label={`${a.nombre}${a.tamano ? ` · ${peso(a.tamano)}` : ''}`}
                      onClick={() => descargar(a)}
                      deleteIcon={<Download sx={{ fontSize: 15 }} />}
                      onDelete={() => descargar(a)}
                      sx={{ cursor: 'pointer', bgcolor: '#FFF' }}
                    />
                  ))}
                </Stack>
              )}
            </Box>
          ))}
        </Stack>
      </Card>

      {/* Responder */}
      <Card sx={{ borderRadius: 3, p: 2.5 }}>
        <TextField
          fullWidth multiline rows={3} value={texto} onChange={e => setTexto(e.target.value)}
          placeholder={interno ? 'Nota para el equipo…' : 'Respuesta para el cliente…'}
        />
        {archivos.length > 0 && (
          <Stack direction="row" flexWrap="wrap" gap={0.75} mt={1.25}>
            {archivos.map((a, i) => (
              <Chip key={i} label={`${a.name} · ${peso(a.size)}`} size="small"
                onDelete={() => setArchivos(x => x.filter((_, j) => j !== i))} />
            ))}
          </Stack>
        )}
        <Stack direction="row" spacing={1} alignItems="center" mt={1.5}>
          <Tooltip title="Adjuntar archivos">
            <IconButton onClick={() => entrada.current?.click()}><AttachFile /></IconButton>
          </Tooltip>
          <input ref={entrada} type="file" hidden multiple
            onChange={e => {
              setArchivos(a => [...a, ...Array.from(e.target.files ?? [])])
              e.target.value = ''
            }} />
          <FormControlLabel
            control={<Switch checked={interno} onChange={e => setInterno(e.target.checked)}
              disabled={archivos.length > 0} />}
            label={<Typography variant="caption">Nota interna</Typography>}
          />
          <Box sx={{ flex: 1 }} />
          <Button
            variant="contained" startIcon={<Send />} onClick={() => responder.mutate()}
            disabled={responder.isPending || (!texto.trim() && archivos.length === 0)}
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            {interno ? 'Guardar nota' : 'Responder'}
          </Button>
        </Stack>
        {archivos.length > 0 && interno && (
          <Alert severity="info" sx={{ mt: 1.5 }}>
            Un mensaje con adjuntos siempre va al cliente: los archivos se comparten con él.
          </Alert>
        )}
      </Card>
    </Box>
  )
}

// ─── Cola ─────────────────────────────────────────────────────────────────────

const VISTAS = ['Cola', 'Tablero', 'Backlog y sprints', 'Métricas'] as const

export default function Soporte() {
  const [vista, setVista] = useState(0)
  const [abierto, setAbierto] = useState<number | null>(null)
  const [estado, setEstado] = useState('')
  const [criticidad, setCriticidad] = useState('')
  const [buscar, setBuscar] = useState('')
  const [cerrados, setCerrados] = useState(false)

  const { data: resumen } = useQuery({
    queryKey: ['soporte-resumen'], queryFn: soporteApi.resumen, refetchInterval: 60000,
  })
  const { data: cola = [], isLoading } = useQuery<Ticket[]>({
    queryKey: ['soporte-cola', estado, criticidad, buscar, cerrados],
    queryFn: () => soporteApi.cola({
      estado: estado || undefined, criticidad: criticidad || undefined,
      buscar: buscar || undefined, incluir_cerrados: cerrados,
    }),
    refetchInterval: 60000,
  })

  if (abierto !== null) return <Ficha id={abierto} onVolver={() => setAbierto(null)} />

  return (
    <Box>
      <Stack mb={1}>
        <Typography variant="h6" fontWeight={800}>Gestión de solicitudes</Typography>
        <Typography variant="caption" color="text.secondary">
          Mesa de ayuda y trabajo del equipo, en un solo lugar
        </Typography>
      </Stack>

      <Tabs
        value={vista} onChange={(_, v) => setVista(v)} variant="scrollable" scrollButtons="auto"
        sx={{
          mb: 2.5, borderBottom: `1px solid ${PALETA.niebla}`,
          '& .MuiTab-root': { textTransform: 'none', fontWeight: 700, minHeight: 42 },
        }}
      >
        {VISTAS.map(v => <Tab key={v} label={v} />)}
      </Tabs>

      {vista === 1 && <Tablero />}
      {vista === 2 && <Backlog />}
      {vista === 3 && <MetricasAgiles />}

      {vista === 0 && (
      <>

      {resumen && (
        <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
            <Box sx={{ flex: 1, minWidth: 130 }}>
              <Typography variant="caption" color="text.secondary">Abiertos</Typography>
              <Typography variant="h6" fontWeight={800}>{resumen.abiertos}</Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box sx={{ flex: 1, minWidth: 130 }}>
              <Typography variant="caption" color="text.secondary">Sin primera respuesta</Typography>
              <Typography variant="h6" fontWeight={800} sx={{
                color: resumen.sin_responder > 0 ? ESTADO.peligro : ESTADO.exito,
              }}>
                {resumen.sin_responder}
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box sx={{ flex: 1, minWidth: 130 }}>
              <Typography variant="caption" color="text.secondary">Críticos</Typography>
              <Typography variant="h6" fontWeight={800} sx={{
                color: resumen.criticos > 0 ? ESTADO.peligro : PALETA.tinta,
              }}>
                {resumen.criticos}
              </Typography>
            </Box>
          </Stack>
        </Card>
      )}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} mb={2}>
        <TextField
          size="small" label="Buscar" value={buscar} onChange={e => setBuscar(e.target.value)}
          placeholder="Número o asunto" sx={{ flex: 1 }}
        />
        <TextField select size="small" label="Estado" value={estado}
          onChange={e => setEstado(e.target.value)} sx={{ minWidth: 170 }}>
          <MenuItem value="">Todos los abiertos</MenuItem>
          {ESTADOS.map(e => <MenuItem key={e} value={e}>{NOMBRE_ESTADO[e]}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Criticidad" value={criticidad}
          onChange={e => setCriticidad(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">Todas</MenuItem>
          {CRITICIDADES.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
        </TextField>
        <FormControlLabel
          control={<Switch checked={cerrados} onChange={e => setCerrados(e.target.checked)} />}
          label={<Typography variant="caption">Ver cerrados</Typography>}
        />
      </Stack>

      <Card sx={{ borderRadius: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>NÚMERO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>EMPRESA</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ASUNTO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>CRITICIDAD</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ESTADO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ASIGNADO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ACTIVIDAD</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && [0, 1, 2].map(i => (
              <TableRow key={i}><TableCell colSpan={7}><Skeleton height={28} /></TableCell></TableRow>
            ))}
            {cola.map(t => (
              <TableRow key={t.id} hover sx={{ cursor: 'pointer' }} onClick={() => setAbierto(t.id)}>
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {t.numero}
                  {!t.primera_respuesta_en && (
                    <Tooltip title="Todavía no ha recibido ninguna respuesta">
                      <Box component="span" sx={{
                        display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
                        bgcolor: ESTADO.peligro, ml: 0.75,
                      }} />
                    </Tooltip>
                  )}
                </TableCell>
                <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                  {t.cliente_codigo}
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}>{t.asunto}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t.autor}{t.modulo ? ` · ${t.modulo}` : ''} · {t.mensajes} mensajes
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip label={t.criticidad} size="small" sx={{
                    fontWeight: 700, fontSize: 10.5,
                    bgcolor: `${COLOR_CRIT[t.criticidad] ?? PALETA.acero}1A`,
                    color: COLOR_CRIT[t.criticidad] ?? PALETA.acero,
                  }} />
                </TableCell>
                <TableCell>
                  <Chip label={NOMBRE_ESTADO[t.estado] ?? t.estado} size="small" sx={{
                    fontWeight: 700, fontSize: 10.5,
                    bgcolor: `${COLOR_ESTADO[t.estado] ?? PALETA.acero}1A`,
                    color: COLOR_ESTADO[t.estado] ?? PALETA.acero,
                  }} />
                </TableCell>
                <TableCell sx={{ color: PALETA.grafito }}>{t.asignado_a ?? '—'}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap', color: PALETA.grafito }}>
                  {espera(t.ultima_actividad)}
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && cola.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Box sx={{ textAlign: 'center', py: 5, color: PALETA.acero }}>
                    <SupportAgent sx={{ fontSize: 40, opacity: 0.4 }} />
                    <Typography variant="body2" mt={1}>
                      No hay requerimientos que coincidan
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
      </>
      )}
    </Box>
  )
}
