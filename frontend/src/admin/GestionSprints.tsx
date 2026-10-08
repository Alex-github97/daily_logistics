/**
 * Backlog, planeación de sprints y métricas ágiles.
 *
 * El sprint y el backlog van en la MISMA pantalla porque planear es mover cosas
 * entre las dos listas: en dos pantallas separadas hay que recordar de memoria
 * qué había en la otra.
 *
 * Las gráficas van en SVG a mano, como el Gantt. Una librería de gráficas para
 * dibujar dos líneas y unas barras no compensa lo que pesa.
 */
import { useMemo, useState } from 'react'
import {
  Box, Card, Stack, Typography, Chip, Button, IconButton, Skeleton, Alert, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions, Divider, MenuItem,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  Add, PlayArrow, Flag, ArrowUpward, ArrowDownward, Speed, TrendingDown,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { DialogoConfirmar } from './GestionDialogos'
import {
  gestionApi, mensajeDeError,
  type Incidencia, type Metricas, type Proyecto, type Sprint,
} from './api'

const COLOR_CATEGORIA: Record<string, string> = {
  SIN_CLASIFICAR: PALETA.acero,
  POR_HACER: PALETA.grafito,
  EN_CURSO: COLOR_MODULO,
  TERMINADO: ESTADO.exito,
}

// ─── Fila ─────────────────────────────────────────────────────────────────────

function Fila({
  t, onAbrir, acciones,
}: {
  t: Incidencia
  onAbrir: (id: number) => void
  acciones: React.ReactNode
}) {
  return (
    <Stack
      direction="row" alignItems="center" spacing={1}
      sx={{
        px: 1.25, py: 0.75, borderRadius: 1.5,
        borderLeft: `3px solid ${t.color_prioridad || PALETA.niebla}`,
        bgcolor: PALETA.lienzo, mb: 0.5,
        '&:hover': { bgcolor: PALETA.bruma },
      }}
    >
      {t.icono && <Typography variant="caption">{t.icono}</Typography>}
      <Typography
        variant="caption" onClick={() => onAbrir(t.id)}
        sx={{
          fontFamily: 'monospace', fontWeight: 700, fontSize: 10.5,
          color: PALETA.acero, cursor: 'pointer', flexShrink: 0,
        }}
      >
        {t.clave}
      </Typography>
      <Typography
        variant="body2" noWrap onClick={() => onAbrir(t.id)}
        sx={{ flex: 1, minWidth: 0, cursor: 'pointer', fontSize: 13 }}
      >
        {t.resumen}
      </Typography>

      <Chip label={t.estado ?? '—'} size="small" sx={{
        height: 18, fontSize: 9.5, fontWeight: 700,
        bgcolor: `${COLOR_CATEGORIA[t.categoria ?? ''] ?? PALETA.acero}1F`,
        color: COLOR_CATEGORIA[t.categoria ?? ''] ?? PALETA.acero,
      }} />

      {t.puntos != null ? (
        <Chip label={t.puntos} size="small" sx={{
          height: 18, minWidth: 26, fontSize: 9.5, fontWeight: 800,
          bgcolor: `${COLOR_MODULO}1A`, color: COLOR_MODULO,
        }} />
      ) : (
        <Tooltip title="Sin estimar: no puede entrar a un sprint con compromiso">
          <Chip label="—" size="small" sx={{
            height: 18, minWidth: 26, fontSize: 9.5,
            bgcolor: `${ESTADO.alerta}1F`, color: ESTADO.alerta,
          }} />
        </Tooltip>
      )}

      {acciones}
    </Stack>
  )
}

// ─── Gráficas ─────────────────────────────────────────────────────────────────

function Burndown({ datos, nota }: {
  datos: Metricas['burndown']; nota?: string | null
}) {
  if (!datos.length) {
    return (
      <Alert severity="info" sx={{ fontSize: 12.5 }}>
        {nota || 'No hay datos para dibujar el avance.'}
      </Alert>
    )
  }

  const W = 520, H = 180, M = { t: 10, r: 10, b: 22, l: 34 }
  const max = Math.max(...datos.map(d => Math.max(d.ideal, d.real ?? 0)), 1)
  const x = (i: number) => M.l + (i * (W - M.l - M.r)) / Math.max(datos.length - 1, 1)
  const y = (v: number) => M.t + (H - M.t - M.b) * (1 - v / max)

  const lineaIdeal = datos.map((d, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(d.ideal)}`).join(' ')
  // La línea real se corta donde se acaban los datos: prolongarla en plano hace
  // creer que el trabajo se detuvo, cuando lo que pasa es que el día no llegó.
  const reales = datos.map((d, i) => ({ i, v: d.real })).filter(p => p.v != null)
  const lineaReal = reales.map((p, k) => `${k ? 'L' : 'M'} ${x(p.i)} ${y(p.v!)}`).join(' ')

  return (
    <Box sx={{ overflowX: 'auto' }}>
      <svg width={W} height={H} style={{ display: 'block', minWidth: W }}>
        {[0, 0.5, 1].map(f => (
          <g key={f}>
            <line x1={M.l} y1={y(max * f)} x2={W - M.r} y2={y(max * f)}
              stroke={PALETA.niebla} strokeWidth={1} />
            <text x={M.l - 6} y={y(max * f) + 3} textAnchor="end"
              fontSize={9} fill={PALETA.acero}>
              {Math.round(max * f)}
            </text>
          </g>
        ))}
        <path d={lineaIdeal} fill="none" stroke={PALETA.acero} strokeWidth={1.5}
          strokeDasharray="4 3" />
        {reales.length > 0 && (
          <path d={lineaReal} fill="none" stroke={COLOR_MODULO} strokeWidth={2.5} />
        )}
        {reales.map(p => (
          <circle key={p.i} cx={x(p.i)} cy={y(p.v!)} r={2.5} fill={COLOR_MODULO} />
        ))}
        {datos.map((d, i) => (
          i % Math.ceil(datos.length / 6) === 0 && (
            <text key={i} x={x(i)} y={H - 6} textAnchor="middle" fontSize={9}
              fill={PALETA.acero}>
              {d.fecha.slice(8, 10)}/{d.fecha.slice(5, 7)}
            </text>
          )
        ))}
      </svg>
    </Box>
  )
}

function Velocidad({ datos }: { datos: Metricas['velocidad'] }) {
  if (!datos.length) {
    return (
      <Alert severity="info" sx={{ fontSize: 12.5 }}>
        La velocidad aparece cuando se cierre el primer sprint. Se congela al
        cerrar, así que no cambia si después alguien reestima algo viejo.
      </Alert>
    )
  }

  const W = 520, H = 180, M = { t: 10, r: 10, b: 30, l: 34 }
  const max = Math.max(...datos.flatMap(d => [d.comprometidos, d.completados]), 1)
  const ancho = (W - M.l - M.r) / datos.length
  const y = (v: number) => M.t + (H - M.t - M.b) * (1 - v / max)

  return (
    <Box sx={{ overflowX: 'auto' }}>
      <svg width={W} height={H} style={{ display: 'block', minWidth: W }}>
        {[0, 0.5, 1].map(f => (
          <line key={f} x1={M.l} y1={y(max * f)} x2={W - M.r} y2={y(max * f)}
            stroke={PALETA.niebla} strokeWidth={1} />
        ))}
        {datos.map((d, i) => {
          const x0 = M.l + i * ancho
          const w = ancho * 0.32
          return (
            <g key={i}>
              <rect x={x0 + ancho * 0.15} y={y(d.comprometidos)} width={w}
                height={H - M.b - y(d.comprometidos)} fill={`${PALETA.acero}66`} rx={2}>
                <title>{`Comprometidos: ${d.comprometidos}`}</title>
              </rect>
              <rect x={x0 + ancho * 0.15 + w + 3} y={y(d.completados)} width={w}
                height={H - M.b - y(d.completados)} fill={COLOR_MODULO} rx={2}>
                <title>{`Completados: ${d.completados}`}</title>
              </rect>
              <text x={x0 + ancho / 2} y={H - 8} textAnchor="middle" fontSize={9}
                fill={PALETA.acero}>
                {d.sprint.length > 12 ? d.sprint.slice(0, 11) + '…' : d.sprint}
              </text>
            </g>
          )
        })}
      </svg>
      <Stack direction="row" spacing={2} mt={0.5}>
        <Leyenda color={`${PALETA.acero}66`} texto="Comprometidos" />
        <Leyenda color={COLOR_MODULO} texto="Completados" />
      </Stack>
    </Box>
  )
}

function Leyenda({ color, texto }: { color: string; texto: string }) {
  return (
    <Stack direction="row" spacing={0.5} alignItems="center">
      <Box sx={{ width: 12, height: 9, bgcolor: color, borderRadius: 0.5 }} />
      <Typography variant="caption" sx={{ color: PALETA.acero, fontSize: 10.5 }}>
        {texto}
      </Typography>
    </Stack>
  )
}

// ─── La pantalla ──────────────────────────────────────────────────────────────

export default function GestionSprints({
  proyecto, onAbrir,
}: {
  proyecto: Proyecto
  onAbrir: (id: number) => void
}) {
  const qc = useQueryClient()
  const [creando, setCreando] = useState(false)
  const [cerrando, setCerrando] = useState(false)
  const [nombre, setNombre] = useState('')
  const [objetivo, setObjetivo] = useState('')
  const [inicio, setInicio] = useState('')
  const [fin, setFin] = useState('')

  const { data: bl, isLoading } = useQuery({
    queryKey: ['gestion', 'backlog', proyecto.id],
    queryFn: () => gestionApi.backlog(proyecto.id),
  })
  const { data: sprints } = useQuery({
    queryKey: ['gestion', 'sprints', proyecto.id],
    queryFn: () => gestionApi.sprints(proyecto.id),
  })
  const { data: metricas } = useQuery({
    queryKey: ['gestion', 'metricas', proyecto.id],
    queryFn: () => gestionApi.metricas(proyecto.id),
  })

  function refrescar() {
    qc.invalidateQueries({ queryKey: ['gestion', 'backlog', proyecto.id] })
    qc.invalidateQueries({ queryKey: ['gestion', 'sprints', proyecto.id] })
    qc.invalidateQueries({ queryKey: ['gestion', 'metricas', proyecto.id] })
  }

  const crear = useMutation({
    mutationFn: () => gestionApi.crearSprint(proyecto.id, {
      nombre, objetivo: objetivo || null,
      inicio: inicio || null, fin: fin || null,
    }),
    onSuccess: () => {
      toast.success('Sprint creado')
      setCreando(false); setNombre(''); setObjetivo(''); setInicio(''); setFin('')
      refrescar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear el sprint')),
  })

  const mover = useMutation({
    mutationFn: ({ ids, sprintId }: { ids: number[]; sprintId: number | null }) =>
      gestionApi.moverAlSprint(ids, sprintId),
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo mover')),
  })

  const activar = useMutation({
    mutationFn: gestionApi.activarSprint,
    onSuccess: s => { toast.success(`«${s.nombre}» activo`); refrescar() },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo activar')),
  })

  const cerrar = useMutation({
    mutationFn: gestionApi.cerrarSprint,
    onSuccess: s => {
      toast.success(
        `«${s.nombre}» cerrado con ${s.puntos_completados} de ${s.puntos_comprometidos} puntos. ` +
        `Lo que no se terminó volvió al backlog.`, { duration: 6000 })
      refrescar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo cerrar')),
  })

  const planeados = useMemo(
    () => (sprints ?? []).filter(s => s.estado === 'PLANEADO'), [sprints])

  if (isLoading) return <Skeleton variant="rounded" height={420} />

  const activo = bl?.sprint ?? null

  return (
    <Stack spacing={2.5}>
      {/* ── El sprint en curso ── */}
      <Card variant="outlined" sx={{ borderRadius: 2, p: 2 }}>
        {activo ? (
          <>
            <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" useFlexGap>
              <Chip label="EN CURSO" size="small" sx={{
                height: 20, fontSize: 9.5, fontWeight: 800,
                bgcolor: `${ESTADO.exito}1F`, color: ESTADO.exito,
              }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                {activo.nombre}
              </Typography>
              {activo.inicio && (
                <Typography variant="caption" sx={{ color: PALETA.acero }}>
                  {activo.inicio} → {activo.fin ?? 'sin fecha de fin'}
                </Typography>
              )}
              <Box sx={{ flex: 1 }} />
              <Cifra etiqueta="Comprometidos" valor={activo.puntos_comprometidos ?? 0} />
              <Cifra etiqueta="Hechos" valor={activo.puntos_hechos} color={ESTADO.exito} />
              <Cifra etiqueta="Total" valor={activo.puntos_totales} />
              <Button
                size="small" variant="outlined" startIcon={<Flag />}
                disabled={cerrar.isPending}
                onClick={() => setCerrando(true)}
                sx={{ textTransform: 'none' }}
              >
                Cerrar sprint
              </Button>
            </Stack>
            {activo.objetivo && (
              <Typography variant="body2" sx={{ mt: 0.75, color: PALETA.grafito }}>
                {activo.objetivo}
              </Typography>
            )}
            {!!activo.sin_estimar && (
              <Alert severity="warning" sx={{ mt: 1.5, py: 0.25, fontSize: 12.5 }}>
                {activo.sin_estimar} sin estimar. No cuentan para el compromiso ni
                para la velocidad.
              </Alert>
            )}

            <Divider sx={{ my: 1.5 }} />
            {bl?.en_sprint.map(t => (
              <Fila key={t.id} t={t} onAbrir={onAbrir} acciones={
                <Tooltip title="Sacar del sprint">
                  <IconButton size="small"
                    onClick={() => mover.mutate({ ids: [t.id], sprintId: null })}>
                    <ArrowDownward sx={{ fontSize: 15 }} />
                  </IconButton>
                </Tooltip>
              } />
            ))}
            {!bl?.en_sprint.length && (
              <Typography variant="caption" sx={{ color: PALETA.acero }}>
                El sprint está vacío. Suba trabajo desde el backlog.
              </Typography>
            )}
          </>
        ) : (
          <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap" useFlexGap>
            <Typography variant="body2" sx={{ color: PALETA.grafito, flex: 1 }}>
              No hay ningún sprint en curso.
              {planeados.length
                ? ' Active uno de los planeados para empezar.'
                : ' Cree uno para empezar a planear.'}
            </Typography>
            {planeados.map(s => (
              <Button
                key={s.id} size="small" variant="outlined" startIcon={<PlayArrow />}
                disabled={activar.isPending} onClick={() => activar.mutate(s.id)}
                sx={{ textTransform: 'none' }}
              >
                Activar «{s.nombre}»
              </Button>
            ))}
            <Button size="small" variant="contained" startIcon={<Add />}
              onClick={() => setCreando(true)} sx={{ textTransform: 'none' }}>
              Nuevo sprint
            </Button>
          </Stack>
        )}
      </Card>

      {/* ── Backlog ── */}
      <Card variant="outlined" sx={{ borderRadius: 2, p: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
            BACKLOG
          </Typography>
          <Chip label={bl?.backlog.length ?? 0} size="small"
            sx={{ height: 18, fontSize: 9.5, bgcolor: PALETA.niebla }} />
          <Box sx={{ flex: 1 }} />
          {!activo && (
            <Button size="small" startIcon={<Add />} onClick={() => setCreando(true)}
              sx={{ textTransform: 'none' }}>
              Nuevo sprint
            </Button>
          )}
        </Stack>

        {bl?.backlog.map(t => (
          <Fila key={t.id} t={t} onAbrir={onAbrir} acciones={
            activo ? (
              <Tooltip title={`Subir a «${activo.nombre}»`}>
                <IconButton size="small"
                  onClick={() => mover.mutate({ ids: [t.id], sprintId: activo.id })}>
                  <ArrowUpward sx={{ fontSize: 15 }} />
                </IconButton>
              </Tooltip>
            ) : planeados.length ? (
              <TextField
                select size="small" value="" sx={{ width: 120 }}
                SelectProps={{ displayEmpty: true, renderValue: () => 'Sprint…' }}
                onChange={e => mover.mutate({
                  ids: [t.id], sprintId: Number(e.target.value),
                })}
              >
                {planeados.map(s => (
                  <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>
                ))}
              </TextField>
            ) : null
          } />
        ))}
        {!bl?.backlog.length && (
          <Typography variant="caption" sx={{ color: PALETA.acero }}>
            El backlog está vacío.
          </Typography>
        )}
      </Card>

      {/* ── Métricas ── */}
      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2}>
        <Card variant="outlined" sx={{ borderRadius: 2, p: 2, flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" spacing={0.75} mb={1}>
            <TrendingDown sx={{ fontSize: 16, color: PALETA.acero }} />
            <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
              AVANCE DEL SPRINT
            </Typography>
          </Stack>
          <Typography variant="caption" sx={{ color: PALETA.acero, display: 'block', mb: 1 }}>
            Sale del historial de cambios, no del estado de hoy: sobre el estado
            actual, la curva mostraría el pasado como si siempre hubiera sido así.
          </Typography>
          <Burndown datos={metricas?.burndown ?? []} nota={metricas?.burndown_nota} />
        </Card>

        <Card variant="outlined" sx={{ borderRadius: 2, p: 2, flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" spacing={0.75} mb={1}>
            <Speed sx={{ fontSize: 16, color: PALETA.acero }} />
            <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
              VELOCIDAD
            </Typography>
            {metricas?.tiempo_ciclo_dias != null && (
              <>
                <Box sx={{ flex: 1 }} />
                <Tooltip title="De que empieza a que se resuelve. Medir desde que se creó incluiría la espera en el backlog, que depende de otra cosa.">
                  <Chip label={`ciclo ${metricas.tiempo_ciclo_dias} d`} size="small"
                    sx={{ height: 18, fontSize: 9.5, bgcolor: PALETA.niebla }} />
                </Tooltip>
              </>
            )}
          </Stack>
          <Velocidad datos={metricas?.velocidad ?? []} />
        </Card>
      </Stack>

      {/* ── Carga ── */}
      {!!metricas?.carga.length && (
        <Card variant="outlined" sx={{ borderRadius: 2, p: 2 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1.5 }}>
            QUIÉN TIENE QUÉ
          </Typography>
          <Stack spacing={0.75}>
            {metricas.carga.map(c => {
              const tope = Math.max(...metricas.carga.map(x => x.abiertas), 1)
              return (
                <Stack key={c.usuario} direction="row" alignItems="center" spacing={1}>
                  <Typography variant="caption" sx={{ width: 130, fontSize: 12 }} noWrap>
                    {c.usuario}
                  </Typography>
                  <Box sx={{ flex: 1, height: 14, bgcolor: PALETA.bruma, borderRadius: 1 }}>
                    <Box sx={{
                      width: `${(c.abiertas / tope) * 100}%`, height: '100%',
                      bgcolor: c.usuario === 'sin asignar' ? ESTADO.alerta : COLOR_MODULO,
                      borderRadius: 1,
                    }} />
                  </Box>
                  <Typography variant="caption" sx={{
                    width: 76, textAlign: 'right', fontSize: 11, color: PALETA.acero,
                  }}>
                    {c.abiertas} · {c.puntos} pt
                  </Typography>
                </Stack>
              )
            })}
          </Stack>
        </Card>
      )}

      <DialogoConfirmar
        abierto={cerrando} onCerrar={() => setCerrando(false)}
        titulo={`¿Cerrar «${activo?.nombre ?? ''}»?`}
        mensaje="Lo que no esté terminado vuelve al backlog, y la velocidad queda congelada con lo que se completó."
        advertencia="No se puede reabrir. Es a propósito: si se pudiera, la velocidad histórica cambiaría cada vez que alguien tocara un sprint viejo."
        textoBoton="Cerrar sprint"
        onAceptar={() => activo && cerrar.mutate(activo.id)}
      />

      {/* ── Alta de sprint ── */}
      <Dialog open={creando} onClose={() => setCreando(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Nuevo sprint</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <TextField size="small" label="Nombre" fullWidth autoFocus required
              value={nombre} onChange={e => setNombre(e.target.value)} />
            <TextField
              size="small" label="Objetivo" fullWidth multiline minRows={2}
              value={objetivo} onChange={e => setObjetivo(e.target.value)}
              helperText="Un sprint sin objetivo es una lista de tareas."
            />
            <Stack direction="row" spacing={2}>
              <TextField size="small" type="date" label="Inicio" fullWidth
                InputLabelProps={{ shrink: true }}
                value={inicio} onChange={e => setInicio(e.target.value)} />
              <TextField
                size="small" type="date" label="Fin" fullWidth
                InputLabelProps={{ shrink: true }}
                value={fin} onChange={e => setFin(e.target.value)}
                helperText="Sin fecha de fin no hay curva de avance."
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreando(false)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button variant="contained" disabled={!nombre.trim() || crear.isPending}
            onClick={() => crear.mutate()} sx={{ textTransform: 'none' }}>
            Crear
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}

function Cifra({ etiqueta, valor, color }: {
  etiqueta: string; valor: number; color?: string
}) {
  return (
    <Box sx={{ textAlign: 'right' }}>
      <Typography variant="caption" sx={{
        display: 'block', fontSize: 9, fontWeight: 800, letterSpacing: '0.07em',
        color: PALETA.acero,
      }}>
        {etiqueta.toUpperCase()}
      </Typography>
      <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1, color }}>
        {valor}
      </Typography>
    </Box>
  )
}
