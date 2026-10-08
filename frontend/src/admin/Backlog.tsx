/**
 * Backlog priorizado y planeación de sprints.
 *
 * El orden del backlog ES la priorización: lo de arriba es lo próximo. Por eso
 * se arrastra en vez de tener un campo "prioridad" — con un campo, veinte cosas
 * quedan en "alta" y el orden vuelve a ser una discusión.
 *
 * Las filas se definen en el ámbito del módulo, no dentro del padre: definidas
 * adentro, React las remonta en cada render y eso cancela el arrastre.
 */
import { useState } from 'react'
import {
  Box, Card, Typography, Stack, Chip, Skeleton, Alert, Button, MenuItem, IconButton, Tooltip, Divider, Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  DragIndicator, Add, PlayArrow, Flag, BugReport, AutoAwesome, Task, HelpOutline,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  agilApi, mensajeDeError, type Tarjeta, type SprintAgil,
} from './api'

const PUNTOS = [1, 2, 3, 5, 8, 13, 21]
const TIPOS = ['ERROR', 'MEJORA', 'TAREA', 'CONSULTA']

const COLOR_CRIT: Record<string, string> = {
  BAJA: PALETA.acero, MEDIA: COLOR_MODULO, ALTA: ESTADO.alerta, CRITICA: ESTADO.peligro,
}
const ICONO_TIPO: Record<string, JSX.Element> = {
  ERROR: <BugReport sx={{ fontSize: 15, color: ESTADO.peligro }} />,
  MEJORA: <AutoAwesome sx={{ fontSize: 15, color: COLOR_MODULO }} />,
  TAREA: <Task sx={{ fontSize: 15, color: PALETA.grafito }} />,
  CONSULTA: <HelpOutline sx={{ fontSize: 15, color: PALETA.acero }} />,
}

// ─── Fila del backlog ─────────────────────────────────────────────────────────

function FilaBacklog({
  t, sprints, onArrastrar, onSoltarSobre, onCambiar,
}: {
  t: Tarjeta
  sprints: SprintAgil[]
  onArrastrar: (t: Tarjeta) => void
  onSoltarSobre: (t: Tarjeta) => void
  onCambiar: (id: number, cambios: Record<string, unknown>) => void
}) {
  const [encima, setEncima] = useState(false)
  const abiertos = sprints.filter(s => s.estado !== 'CERRADO')

  return (
    <Card
      draggable
      onDragStart={e => {
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', String(t.id))
        onArrastrar(t)
      }}
      onDragOver={e => { e.preventDefault(); setEncima(true) }}
      onDragLeave={() => setEncima(false)}
      onDrop={e => { e.preventDefault(); setEncima(false); onSoltarSobre(t) }}
      sx={{
        p: 1.25, mb: 0.75, borderRadius: 2,
        borderLeft: `3px solid ${COLOR_CRIT[t.criticidad] ?? PALETA.acero}`,
        borderTop: encima ? `2px solid ${COLOR_MODULO}` : '2px solid transparent',
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
        <DragIndicator sx={{ fontSize: 17, color: PALETA.acero, cursor: 'grab' }} />
        {ICONO_TIPO[t.tipo_trabajo ?? 'ERROR']}
        <Typography variant="caption" sx={{
          fontFamily: 'monospace', fontWeight: 700, color: PALETA.acero, minWidth: 96,
        }}>
          {t.numero}
        </Typography>
        <Typography variant="body2" sx={{ flex: 1, minWidth: 180, fontWeight: 600 }}>
          {t.asunto}
        </Typography>
        <Chip label={t.cliente_codigo} size="small" variant="outlined"
          sx={{ height: 20, fontSize: 10, fontFamily: 'monospace' }} />

        <TextField
          select size="small" value={t.tipo_trabajo ?? 'ERROR'} sx={{ width: 118 }}
          onChange={e => onCambiar(t.id, { tipo_trabajo: e.target.value })}
        >
          {TIPOS.map(x => <MenuItem key={x} value={x} dense>{x}</MenuItem>)}
        </TextField>

        <TextField
          select size="small" value={t.puntos ?? ''} sx={{ width: 92 }}
          onChange={e => onCambiar(t.id, { puntos: Number(e.target.value) })}
          label={t.puntos == null ? 'Estimar' : undefined}
        >
          {PUNTOS.map(p => <MenuItem key={p} value={p} dense>{p} pt</MenuItem>)}
        </TextField>

        {abiertos.length > 0 && (
          <TextField
            select size="small" value="" sx={{ width: 132 }} label="Al sprint"
            onChange={e => onCambiar(t.id, { sprint_id: Number(e.target.value) })}
          >
            {abiertos.map(s => (
              <MenuItem key={s.id} value={s.id} dense>{s.nombre}</MenuItem>
            ))}
          </TextField>
        )}
      </Stack>
    </Card>
  )
}

// ─── Nuevo sprint ─────────────────────────────────────────────────────────────

function DialogoSprint({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const qc = useQueryClient()
  const hoy = new Date().toISOString().slice(0, 10)
  const enDos = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10)
  const [f, setF] = useState({ nombre: '', objetivo: '', inicio: hoy, fin: enDos })

  const crear = useMutation({
    mutationFn: () => agilApi.crearSprint(f),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agil-sprints'] })
      setF({ nombre: '', objetivo: '', inicio: hoy, fin: enDos })
      onCerrar(); toast.success('Sprint creado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const set = (k: keyof typeof f) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Nuevo sprint</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="Nombre" value={f.nombre} onChange={set('nombre')} fullWidth required
            placeholder="Sprint 12" />
          <TextField
            label="Objetivo" value={f.objetivo} onChange={set('objetivo')} fullWidth
            multiline rows={2}
            placeholder="Qué queremos lograr en esta iteración"
            helperText="Un sprint sin objetivo es solo una lista de tareas"
          />
          <Stack direction="row" spacing={2}>
            <TextField label="Inicio" type="date" value={f.inicio} onChange={set('inicio')}
              fullWidth InputLabelProps={{ shrink: true }} />
            <TextField label="Fin" type="date" value={f.fin} onChange={set('fin')}
              fullWidth InputLabelProps={{ shrink: true }} />
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button variant="contained" onClick={() => crear.mutate()}
          disabled={crear.isPending || !f.nombre.trim()}
          sx={{ textTransform: 'none', fontWeight: 700 }}>Crear</Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function Backlog() {
  const qc = useQueryClient()
  const [arrastrada, setArrastrada] = useState<Tarjeta | null>(null)
  const [nuevoSprint, setNuevoSprint] = useState(false)

  const { data: backlog = [], isLoading } = useQuery<Tarjeta[]>({
    queryKey: ['agil-backlog'], queryFn: agilApi.backlog,
  })
  const { data: sprints = [] } = useQuery<SprintAgil[]>({
    queryKey: ['agil-sprints'], queryFn: agilApi.sprints,
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['agil-backlog'] })
    qc.invalidateQueries({ queryKey: ['agil-sprints'] })
    qc.invalidateQueries({ queryKey: ['agil-tablero'] })
    qc.invalidateQueries({ queryKey: ['agil-metricas'] })
  }

  const cambiar = useMutation({
    mutationFn: ({ id, cambios }: { id: number; cambios: Record<string, unknown> }) =>
      agilApi.actualizar(id, cambios),
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const reordenar = useMutation({
    mutationFn: (ids: number[]) => agilApi.reordenar(ids),
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const activar = useMutation({
    mutationFn: (id: number) => agilApi.activarSprint(id),
    onSuccess: () => { refrescar(); toast.success('Sprint activado') },
    // El servidor rechaza si está vacío, si hay algo sin estimar o si ya hay
    // otro activo; el mensaje dice cuál de los tres es.
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const cerrar = useMutation({
    mutationFn: (id: number) => agilApi.cerrarSprint(id),
    onSuccess: s => {
      refrescar()
      toast.success(`Sprint cerrado: ${s.puntos_completados} de ${s.puntos_comprometidos} puntos`)
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const soltarSobre = (destino: Tarjeta) => {
    if (!arrastrada || arrastrada.id === destino.id) { setArrastrada(null); return }
    const ids = backlog.map(t => t.id).filter(id => id !== arrastrada.id)
    const donde = ids.indexOf(destino.id)
    ids.splice(donde, 0, arrastrada.id)
    reordenar.mutate(ids)
    setArrastrada(null)
  }

  const sinEstimar = backlog.filter(t => t.puntos == null).length
  const totalPuntos = backlog.reduce((s, t) => s + (t.puntos ?? 0), 0)

  return (
    <Box>
      {/* Sprints */}
      <Stack direction="row" alignItems="center" mb={1.5}>
        <Typography variant="subtitle2" fontWeight={800} sx={{ flex: 1 }}>Sprints</Typography>
        <Button startIcon={<Add />} size="small" variant="contained"
          onClick={() => setNuevoSprint(true)}
          sx={{ textTransform: 'none', fontWeight: 700 }}>Nuevo sprint</Button>
      </Stack>

      <Stack spacing={1} mb={3}>
        {sprints.filter(s => s.estado !== 'CERRADO').map(s => (
          <Card key={s.id} sx={{ borderRadius: 3, p: 1.75 }}>
            <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" useFlexGap>
              <Flag sx={{
                fontSize: 18, color: s.estado === 'ACTIVO' ? ESTADO.exito : PALETA.acero,
              }} />
              <Box sx={{ flex: 1, minWidth: 180 }}>
                <Typography variant="body2" fontWeight={700}>{s.nombre}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {s.objetivo || 'Sin objetivo definido'}
                </Typography>
              </Box>
              <Chip label={s.estado} size="small" sx={{
                fontWeight: 700, fontSize: 10.5,
                bgcolor: s.estado === 'ACTIVO' ? `${ESTADO.exito}1A` : `${PALETA.acero}26`,
                color: s.estado === 'ACTIVO' ? ESTADO.exito : PALETA.grafito,
              }} />
              <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {s.total_solicitudes} solicitudes · {s.puntos_hechos}/{s.puntos_en_curso} pt
              </Typography>
              {s.estado === 'PLANEADO' ? (
                <Button size="small" startIcon={<PlayArrow />} variant="outlined"
                  onClick={() => s.id && activar.mutate(s.id)}
                  sx={{ textTransform: 'none' }}>Activar</Button>
              ) : (
                <Button size="small" color="warning" variant="outlined"
                  onClick={() => s.id && cerrar.mutate(s.id)}
                  sx={{ textTransform: 'none' }}>Cerrar sprint</Button>
              )}
            </Stack>
          </Card>
        ))}
        {sprints.filter(s => s.estado !== 'CERRADO').length === 0 && (
          <Alert severity="info">
            No hay sprints abiertos. Cree uno, arrástrele solicitudes del backlog y actívelo.
          </Alert>
        )}
      </Stack>

      <Divider sx={{ mb: 2 }} />

      {/* Backlog */}
      <Stack direction="row" alignItems="center" mb={1.5} flexWrap="wrap" useFlexGap>
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle2" fontWeight={800}>Backlog</Typography>
          <Typography variant="caption" color="text.secondary">
            El orden es la prioridad: lo de arriba es lo próximo. Arrastre para reordenar.
          </Typography>
        </Box>
        <Chip label={`${backlog.length} solicitudes`} size="small" />
        <Chip label={`${totalPuntos} pt estimados`} size="small" sx={{
          bgcolor: `${COLOR_MODULO}14`, color: COLOR_MODULO, fontWeight: 700,
        }} />
        {sinEstimar > 0 && (
          <Chip label={`${sinEstimar} sin estimar`} size="small" sx={{
            bgcolor: `${ESTADO.alerta}1F`, color: ESTADO.alerta, fontWeight: 700,
          }} />
        )}
      </Stack>

      {isLoading && <Skeleton variant="rectangular" height={220} sx={{ borderRadius: 3 }} />}

      {!isLoading && backlog.length === 0 && (
        <Card sx={{ borderRadius: 3, p: 4, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            El backlog está vacío: todo lo abierto ya está en un sprint.
          </Typography>
        </Card>
      )}

      {backlog.map(t => (
        <FilaBacklog
          key={t.id} t={t} sprints={sprints}
          onArrastrar={setArrastrada}
          onSoltarSobre={soltarSobre}
          onCambiar={(id, cambios) => cambiar.mutate({ id, cambios })}
        />
      ))}

      <DialogoSprint abierto={nuevoSprint} onCerrar={() => setNuevoSprint(false)} />
    </Box>
  )
}
