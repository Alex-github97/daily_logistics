/**
 * Soporte técnico, del lado del cliente — /soporte
 *
 * Es una página y no un panel flotante a propósito: describir un problema toma
 * tiempo, y un popup taparía justo la pantalla que se está intentando explicar.
 * Acá se puede abrir el reporte, adjuntar el pantallazo y seguir mirando.
 */
import { useRef, useState } from 'react'
import {
  Box, Card, Typography, Stack, Button, MenuItem, Chip, Alert, Skeleton, Divider, IconButton, Tooltip, LinearProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  Add, ArrowBack, AttachFile, Send, InsertDriveFile, Download, SupportAgent,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { apiClient as api } from '@/api/client'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'

interface Adjunto { id: number; nombre: string; tamano?: number | null }
interface Mensaje {
  id: number; autor: string; es_soporte: boolean; cuerpo: string
  interno: boolean; creado_en: string; adjuntos: Adjunto[]
}
interface Ticket {
  id: number; numero: string; asunto: string; estado: string; criticidad: string
  categoria?: string | null; modulo?: string | null; impacto?: string | null
  created_at?: string | null; ultima_actividad?: string | null
  mensajes: number; conversacion?: Mensaje[]
}

const IMPACTOS = [
  { v: 'CONSULTA', l: 'Es una duda, no me bloquea' },
  { v: 'MOLESTIA', l: 'Me molesta pero puedo seguir' },
  { v: 'BLOQUEA_TAREA', l: 'No puedo terminar una tarea' },
  { v: 'OPERACION_DETENIDA', l: 'Tengo la operación detenida' },
]

const CATEGORIAS = ['Error', 'Duda', 'Solicitud de cambio', 'Datos incorrectos',
                    'Capacitación', 'Otro']

const COLOR_ESTADO: Record<string, string> = {
  NUEVO: COLOR_MODULO,
  EN_PROGRESO: ESTADO.alerta,
  ESPERANDO_CLIENTE: ESTADO.informacion,
  RESUELTO: ESTADO.exito,
  CERRADO: PALETA.acero,
}
const NOMBRE_ESTADO: Record<string, string> = {
  NUEVO: 'Recibido',
  EN_PROGRESO: 'En atención',
  ESPERANDO_CLIENTE: 'Esperando su respuesta',
  RESUELTO: 'Resuelto',
  CERRADO: 'Cerrado',
}
const COLOR_CRIT: Record<string, string> = {
  BAJA: PALETA.acero, MEDIA: COLOR_MODULO,
  ALTA: ESTADO.alerta, CRITICA: ESTADO.peligro,
}

const cuando = (iso?: string | null) => {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  return isNaN(d.getTime()) ? '' :
    d.toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' })
}

const peso = (b?: number | null) =>
  !b ? '' : b < 1024 ? `${b} B` : b < 1048576 ? `${Math.round(b / 1024)} KB`
    : `${(b / 1048576).toFixed(1)} MB`

/** Descarga pasando por la API: los adjuntos no se sirven por carpeta pública. */
async function descargar(adjunto: Adjunto) {
  try {
    const r = await api.get(`/soporte/adjuntos/${adjunto.id}`, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url; a.download = adjunto.nombre
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  } catch {
    toast.error('No se pudo descargar el archivo')
  }
}

// ─── Nuevo requerimiento ──────────────────────────────────────────────────────

const VACIO = { asunto: '', descripcion: '', categoria: 'Error', modulo: '', impacto: 'MOLESTIA' }

function NuevoTicket({ onCreado, onCancelar }: {
  onCreado: (t: Ticket) => void
  onCancelar: () => void
}) {
  const qc = useQueryClient()
  const [f, setF] = useState({ ...VACIO })
  const [archivos, setArchivos] = useState<File[]>([])
  const entrada = useRef<HTMLInputElement>(null)

  const crear = useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/soporte/tickets', f)
      if (archivos.length) {
        const cuerpo = new FormData()
        archivos.forEach(a => cuerpo.append('archivos', a))
        await api.post(`/soporte/tickets/${data.id}/adjuntos`, cuerpo)
      }
      return data as Ticket
    },
    onSuccess: t => {
      qc.invalidateQueries({ queryKey: ['mis-tickets'] })
      toast.success(`Requerimiento ${t.numero} enviado`)
      onCreado(t)
    },
    onError: (e: any) =>
      toast.error(e?.response?.data?.detail ?? 'No se pudo enviar el requerimiento'),
  })

  const set = (k: keyof typeof VACIO) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Card sx={{ borderRadius: 3, p: 3 }}>
      <Stack direction="row" alignItems="center" spacing={1} mb={2}>
        <IconButton onClick={onCancelar} size="small"><ArrowBack /></IconButton>
        <Typography variant="h6" fontWeight={800}>Nuevo requerimiento</Typography>
      </Stack>

      <Stack spacing={2.5}>
        <TextField
          label="Asunto" value={f.asunto} onChange={set('asunto')} fullWidth required
          placeholder="En una línea, qué pasó"
          helperText="Es lo primero que ve el equipo de soporte"
        />
        <TextField
          label="Qué pasó" value={f.descripcion} onChange={set('descripcion')}
          fullWidth required multiline rows={6}
          placeholder={'Qué estaba haciendo, qué esperaba que pasara y qué pasó.\n'
            + 'Si sale un mensaje de error, cópielo tal cual.'}
        />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField select label="Tipo" value={f.categoria} onChange={set('categoria')} fullWidth>
            {CATEGORIAS.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
          </TextField>
          <TextField
            label="Módulo" value={f.modulo} onChange={set('modulo')} fullWidth
            placeholder="EAM, WMS, TMS…"
          />
        </Stack>
        <TextField
          select label="¿Cuánto lo afecta?" value={f.impacto} onChange={set('impacto')} fullWidth
          helperText="Con esto soporte ordena la cola; la prioridad final la asigna el equipo"
        >
          {IMPACTOS.map(i => <MenuItem key={i.v} value={i.v}>{i.l}</MenuItem>)}
        </TextField>

        <Box>
          <Button
            startIcon={<AttachFile />} variant="outlined" size="small"
            onClick={() => entrada.current?.click()}
            sx={{ textTransform: 'none' }}
          >
            Adjuntar archivos
          </Button>
          <Typography variant="caption" color="text.secondary" display="block" mt={0.75}>
            Pantallazos, Excel, PDF, JSON… Un pantallazo del error suele ahorrar
            varios mensajes de ida y vuelta.
          </Typography>
          <input
            ref={entrada} type="file" hidden multiple
            onChange={e => {
              setArchivos(a => [...a, ...Array.from(e.target.files ?? [])])
              e.target.value = ''
            }}
          />
          {archivos.length > 0 && (
            <Stack direction="row" flexWrap="wrap" gap={0.75} mt={1.25}>
              {archivos.map((a, i) => (
                <Chip
                  key={i} label={`${a.name} · ${peso(a.size)}`} size="small"
                  onDelete={() => setArchivos(x => x.filter((_, j) => j !== i))}
                />
              ))}
            </Stack>
          )}
        </Box>

        {crear.isPending && <LinearProgress sx={{ borderRadius: 99 }} />}
        <Stack direction="row" spacing={1.5}>
          <Button
            variant="contained" startIcon={<Send />} onClick={() => crear.mutate()}
            disabled={crear.isPending || !f.asunto.trim() || !f.descripcion.trim()}
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            {crear.isPending ? 'Enviando…' : 'Enviar a soporte'}
          </Button>
          <Button onClick={onCancelar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        </Stack>
      </Stack>
    </Card>
  )
}

// ─── Conversación ─────────────────────────────────────────────────────────────

function Conversacion({ ticketId, onVolver }: { ticketId: number; onVolver: () => void }) {
  const qc = useQueryClient()
  const [texto, setTexto] = useState('')
  const [archivos, setArchivos] = useState<File[]>([])
  const entrada = useRef<HTMLInputElement>(null)

  const { data: t, isLoading } = useQuery<Ticket>({
    queryKey: ['ticket', ticketId],
    queryFn: () => api.get(`/soporte/tickets/${ticketId}`).then(r => r.data),
    // El cliente deja la pantalla abierta esperando respuesta.
    refetchInterval: 30000,
  })

  const responder = useMutation({
    mutationFn: async () => {
      if (archivos.length) {
        const cuerpo = new FormData()
        archivos.forEach(a => cuerpo.append('archivos', a))
        if (texto.trim()) cuerpo.append('cuerpo', texto.trim())
        await api.post(`/soporte/tickets/${ticketId}/adjuntos`, cuerpo)
      } else {
        await api.post(`/soporte/tickets/${ticketId}/mensajes`, { cuerpo: texto.trim() })
      }
    },
    onSuccess: () => {
      setTexto(''); setArchivos([])
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['mis-tickets'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo enviar'),
  })

  if (isLoading || !t) return <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 3 }} />

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1.5} mb={2}>
        <IconButton onClick={onVolver}><ArrowBack /></IconButton>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
            <Typography variant="caption" sx={{
              fontFamily: 'monospace', fontWeight: 700, color: PALETA.grafito,
            }}>
              {t.numero}
            </Typography>
            <Chip label={NOMBRE_ESTADO[t.estado] ?? t.estado} size="small" sx={{
              height: 20, fontSize: 11, fontWeight: 700,
              bgcolor: `${COLOR_ESTADO[t.estado] ?? PALETA.acero}1A`,
              color: COLOR_ESTADO[t.estado] ?? PALETA.acero,
            }} />
            <Chip label={`Prioridad ${t.criticidad.toLowerCase()}`} size="small" sx={{
              height: 20, fontSize: 11, fontWeight: 700,
              bgcolor: `${COLOR_CRIT[t.criticidad] ?? PALETA.acero}1A`,
              color: COLOR_CRIT[t.criticidad] ?? PALETA.acero,
            }} />
          </Stack>
          <Typography variant="h6" fontWeight={800} sx={{ mt: 0.25 }}>{t.asunto}</Typography>
        </Box>
      </Stack>

      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2 }}>
        <Stack spacing={2}>
          {(t.conversacion ?? []).map(m => (
            <Box key={m.id} sx={{
              alignSelf: m.es_soporte ? 'flex-start' : 'flex-end',
              maxWidth: '85%',
              bgcolor: m.es_soporte ? `${COLOR_MODULO}0F` : PALETA.bruma,
              border: `1px solid ${m.es_soporte ? `${COLOR_MODULO}33` : PALETA.niebla}`,
              borderRadius: 2, p: 1.75,
            }}>
              <Stack direction="row" alignItems="center" spacing={0.75} mb={0.75}>
                {m.es_soporte && <SupportAgent sx={{ fontSize: 15, color: COLOR_MODULO }} />}
                <Typography variant="caption" fontWeight={700} sx={{
                  color: m.es_soporte ? COLOR_MODULO : PALETA.grafito,
                }}>
                  {m.es_soporte ? 'Soporte técnico' : m.autor}
                </Typography>
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

      <Card sx={{ borderRadius: 3, p: 2.5 }}>
        <TextField
          fullWidth multiline rows={3} value={texto} onChange={e => setTexto(e.target.value)}
          placeholder="Escriba su respuesta…"
        />
        {archivos.length > 0 && (
          <Stack direction="row" flexWrap="wrap" gap={0.75} mt={1.25}>
            {archivos.map((a, i) => (
              <Chip key={i} label={`${a.name} · ${peso(a.size)}`} size="small"
                onDelete={() => setArchivos(x => x.filter((_, j) => j !== i))} />
            ))}
          </Stack>
        )}
        <Stack direction="row" spacing={1} mt={1.5}>
          <Tooltip title="Adjuntar archivos">
            <IconButton onClick={() => entrada.current?.click()}><AttachFile /></IconButton>
          </Tooltip>
          <input
            ref={entrada} type="file" hidden multiple
            onChange={e => {
              setArchivos(a => [...a, ...Array.from(e.target.files ?? [])])
              e.target.value = ''
            }}
          />
          <Box sx={{ flex: 1 }} />
          <Button
            variant="contained" startIcon={<Send />} onClick={() => responder.mutate()}
            disabled={responder.isPending || (!texto.trim() && archivos.length === 0)}
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            Enviar
          </Button>
        </Stack>
      </Card>
    </Box>
  )
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function Soporte() {
  const [vista, setVista] = useState<'lista' | 'nuevo'>('lista')
  const [abierto, setAbierto] = useState<number | null>(null)

  const { data: tickets = [], isLoading } = useQuery<Ticket[]>({
    queryKey: ['mis-tickets'],
    queryFn: () => api.get('/soporte/mis-tickets').then(r => r.data),
  })

  return (
    <Layout title="Soporte técnico">
      <Box sx={{ maxWidth: 980, mx: 'auto' }}>
        {abierto !== null ? (
          <Conversacion ticketId={abierto} onVolver={() => setAbierto(null)} />
        ) : vista === 'nuevo' ? (
          <NuevoTicket
            onCancelar={() => setVista('lista')}
            onCreado={t => { setVista('lista'); setAbierto(t.id) }}
          />
        ) : (
          <>
            <Stack direction="row" alignItems="center" mb={2.5}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h6" fontWeight={800}>Soporte técnico</Typography>
                <Typography variant="caption" color="text.secondary">
                  Escriba al equipo y siga acá la respuesta
                </Typography>
              </Box>
              <Button
                startIcon={<Add />} variant="contained" onClick={() => setVista('nuevo')}
                sx={{ textTransform: 'none', fontWeight: 700 }}
              >
                Nuevo requerimiento
              </Button>
            </Stack>

            {isLoading && <Skeleton variant="rectangular" height={200} sx={{ borderRadius: 3 }} />}

            {!isLoading && tickets.length === 0 && (
              <Card sx={{ borderRadius: 3, p: 5, textAlign: 'center' }}>
                <SupportAgent sx={{ fontSize: 44, color: PALETA.acero, opacity: 0.5 }} />
                <Typography variant="body2" color="text.secondary" mt={1.5}>
                  Todavía no ha escrito a soporte.
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Cuando algo no funcione o tenga una duda, cuéntenoslo desde acá.
                </Typography>
              </Card>
            )}

            <Stack spacing={1.25}>
              {tickets.map(t => (
                <Card
                  key={t.id} onClick={() => setAbierto(t.id)}
                  sx={{
                    borderRadius: 3, p: 2, cursor: 'pointer',
                    transition: 'box-shadow .15s ease',
                    '&:hover': { boxShadow: 4 },
                  }}
                >
                  <Stack direction="row" alignItems="center" spacing={2}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
                        <Typography variant="caption" sx={{
                          fontFamily: 'monospace', fontWeight: 700, color: PALETA.acero,
                        }}>
                          {t.numero}
                        </Typography>
                        <Chip label={NOMBRE_ESTADO[t.estado] ?? t.estado} size="small" sx={{
                          height: 19, fontSize: 10.5, fontWeight: 700,
                          bgcolor: `${COLOR_ESTADO[t.estado] ?? PALETA.acero}1A`,
                          color: COLOR_ESTADO[t.estado] ?? PALETA.acero,
                        }} />
                      </Stack>
                      <Typography variant="body2" fontWeight={700} sx={{ mt: 0.4 }}>
                        {t.asunto}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t.mensajes} {t.mensajes === 1 ? 'mensaje' : 'mensajes'}
                        {t.ultima_actividad && ` · última actividad ${cuando(t.ultima_actividad)}`}
                      </Typography>
                    </Box>
                    <Chip label={t.criticidad} size="small" sx={{
                      fontSize: 10.5, fontWeight: 700,
                      bgcolor: `${COLOR_CRIT[t.criticidad] ?? PALETA.acero}1A`,
                      color: COLOR_CRIT[t.criticidad] ?? PALETA.acero,
                    }} />
                  </Stack>
                </Card>
              ))}
            </Stack>

            <Divider sx={{ my: 3 }} />
            <Alert severity="info">
              La prioridad final la asigna el equipo de soporte al revisar el caso,
              no se toma del formulario. Lo que usted indica es cuánto lo afecta.
            </Alert>
          </>
        )}
      </Box>
    </Layout>
  )
}
