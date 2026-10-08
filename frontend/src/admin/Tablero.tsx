/**
 * Tablero Kanban del sprint en curso.
 *
 * Las tarjetas y las columnas se definen en el ámbito del módulo y NO dentro
 * del componente padre. Definidas adentro, React las trata como tipos nuevos en
 * cada render, las desmonta y las vuelve a montar — y eso cancela el arrastre
 * HTML5 a mitad de camino, con el síntoma de que "el tablero a veces no deja
 * soltar la tarjeta".
 */
import { useState } from 'react'
import {
  Box, Card, Typography, Stack, Chip, Skeleton, Alert, TextField,
  IconButton, Tooltip, Menu, MenuItem, Divider,
} from '@mui/material'
import { MoreVert, BugReport, AutoAwesome, Task, HelpOutline } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  agilApi, mensajeDeError,
  type Tarjeta, type ColumnaTablero, type Tablero as TableroDatos,
} from './api'

const PUNTOS = [1, 2, 3, 5, 8, 13, 21]

const COLOR_CRIT: Record<string, string> = {
  BAJA: PALETA.acero, MEDIA: COLOR_MODULO, ALTA: ESTADO.alerta, CRITICA: ESTADO.peligro,
}

const ICONO_TIPO: Record<string, JSX.Element> = {
  ERROR: <BugReport sx={{ fontSize: 14, color: ESTADO.peligro }} />,
  MEJORA: <AutoAwesome sx={{ fontSize: 14, color: COLOR_MODULO }} />,
  TAREA: <Task sx={{ fontSize: 14, color: PALETA.grafito }} />,
  CONSULTA: <HelpOutline sx={{ fontSize: 14, color: PALETA.acero }} />,
}

// ─── Tarjeta ──────────────────────────────────────────────────────────────────

function TarjetaKanban({
  t, onArrastrar, onEstimar,
}: {
  t: Tarjeta
  onArrastrar: (t: Tarjeta) => void
  onEstimar: (t: Tarjeta, puntos: number) => void
}) {
  const [menu, setMenu] = useState<null | HTMLElement>(null)

  return (
    <Card
      draggable
      onDragStart={e => {
        e.dataTransfer.effectAllowed = 'move'
        // Firefox no inicia el arrastre si no se escribe algo en dataTransfer.
        e.dataTransfer.setData('text/plain', String(t.id))
        onArrastrar(t)
      }}
      sx={{
        p: 1.25, mb: 1, borderRadius: 2, cursor: 'grab',
        borderLeft: `3px solid ${COLOR_CRIT[t.criticidad] ?? PALETA.acero}`,
        '&:active': { cursor: 'grabbing' },
        '&:hover': { boxShadow: 3 },
      }}
    >
      <Stack direction="row" alignItems="flex-start" spacing={0.5}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            {ICONO_TIPO[t.tipo_trabajo ?? 'ERROR']}
            <Typography variant="caption" sx={{
              fontFamily: 'monospace', fontWeight: 700, color: PALETA.acero,
            }}>
              {t.numero}
            </Typography>
          </Stack>
          <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.4, lineHeight: 1.35 }}>
            {t.asunto}
          </Typography>
        </Box>
        <IconButton size="small" onClick={e => setMenu(e.currentTarget)}>
          <MoreVert sx={{ fontSize: 16 }} />
        </IconButton>
      </Stack>

      <Stack direction="row" alignItems="center" spacing={0.5} mt={1} flexWrap="wrap" useFlexGap>
        <Chip label={t.cliente_codigo} size="small" variant="outlined"
          sx={{ height: 18, fontSize: 9.5, fontFamily: 'monospace' }} />
        {t.puntos != null ? (
          <Chip label={`${t.puntos} pt`} size="small" sx={{
            height: 18, fontSize: 9.5, fontWeight: 800,
            bgcolor: `${COLOR_MODULO}1A`, color: COLOR_MODULO,
          }} />
        ) : (
          <Tooltip title="Sin estimar: no puede entrar a un sprint con compromiso">
            <Chip label="sin estimar" size="small" sx={{
              height: 18, fontSize: 9.5, fontWeight: 700,
              bgcolor: `${ESTADO.alerta}1F`, color: ESTADO.alerta,
            }} />
          </Tooltip>
        )}
        {t.asignado_a && (
          <Chip label={t.asignado_a} size="small"
            sx={{ height: 18, fontSize: 9.5, bgcolor: PALETA.niebla }} />
        )}
      </Stack>

      <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
        <Typography variant="caption" sx={{ px: 2, py: 0.5, color: PALETA.acero }}>
          Estimar en puntos
        </Typography>
        {PUNTOS.map(p => (
          <MenuItem key={p} dense selected={t.puntos === p}
            onClick={() => { onEstimar(t, p); setMenu(null) }}>
            {p} {p === 1 ? 'punto' : 'puntos'}
          </MenuItem>
        ))}
      </Menu>
    </Card>
  )
}

// ─── Columna ──────────────────────────────────────────────────────────────────

function Columna({
  c, arrastrada, onSoltar, onEstimar, onArrastrar, onLimite,
}: {
  c: ColumnaTablero
  arrastrada: Tarjeta | null
  onSoltar: (estado: string) => void
  onEstimar: (t: Tarjeta, puntos: number) => void
  onArrastrar: (t: Tarjeta) => void
  onLimite: (estado: string, limite: number | null) => void
}) {
  const [encima, setEncima] = useState(false)
  const [editando, setEditando] = useState(false)

  const lleno = c.limite_wip != null && c.cantidad >= c.limite_wip
  const puedeSoltar = arrastrada && arrastrada.estado !== c.estado

  return (
    <Box
      onDragOver={e => { if (puedeSoltar) { e.preventDefault(); setEncima(true) } }}
      onDragLeave={() => setEncima(false)}
      onDrop={e => { e.preventDefault(); setEncima(false); onSoltar(c.estado) }}
      sx={{
        minWidth: 268, width: 268, flexShrink: 0,
        bgcolor: encima && puedeSoltar ? `${COLOR_MODULO}0F` : PALETA.bruma,
        border: `1px solid ${encima && puedeSoltar ? COLOR_MODULO : PALETA.niebla}`,
        borderRadius: 3, p: 1.25, transition: 'background-color .12s, border-color .12s',
      }}
    >
      <Stack direction="row" alignItems="center" spacing={0.5} mb={1.25}>
        <Typography variant="caption" fontWeight={800} sx={{ flex: 1 }}>
          {c.titulo.toUpperCase()}
        </Typography>
        <Chip label={c.cantidad} size="small" sx={{ height: 18, fontSize: 10, fontWeight: 700 }} />
        {c.puntos > 0 && (
          <Chip label={`${c.puntos} pt`} size="small" sx={{
            height: 18, fontSize: 10, bgcolor: `${COLOR_MODULO}14`, color: COLOR_MODULO,
          }} />
        )}
      </Stack>

      {editando ? (
        <TextField
          size="small" autoFocus fullWidth type="number" label="Límite (vacío = sin límite)"
          defaultValue={c.limite_wip ?? ''}
          onBlur={e => {
            const v = e.target.value.trim()
            onLimite(c.estado, v ? Number(v) : null)
            setEditando(false)
          }}
          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
          sx={{ mb: 1 }}
        />
      ) : (
        c.limite_wip != null && (
          <Tooltip title="Límite de trabajo en curso. Clic para cambiarlo.">
            <Chip
              label={`WIP ${c.cantidad}/${c.limite_wip}`} size="small"
              onClick={() => setEditando(true)}
              sx={{
                mb: 1, height: 20, fontSize: 10, fontWeight: 700, cursor: 'pointer',
                bgcolor: lleno ? `${ESTADO.peligro}1A` : `${PALETA.acero}26`,
                color: lleno ? ESTADO.peligro : PALETA.grafito,
              }}
            />
          </Tooltip>
        )
      )}

      {lleno && (
        <Alert severity="warning" sx={{ mb: 1, py: 0, fontSize: 11 }}>
          Al límite. Termine algo antes de empezar otra cosa.
        </Alert>
      )}

      <Box sx={{ minHeight: 60, maxHeight: 520, overflowY: 'auto' }}>
        {c.tarjetas.map(t => (
          <TarjetaKanban key={t.id} t={t} onArrastrar={onArrastrar} onEstimar={onEstimar} />
        ))}
        {c.tarjetas.length === 0 && (
          <Typography variant="caption" sx={{
            display: 'block', textAlign: 'center', py: 3, color: PALETA.acero,
          }}>
            {puedeSoltar ? 'Suelte aquí' : 'Vacío'}
          </Typography>
        )}
      </Box>
    </Box>
  )
}

// ─── Tablero ──────────────────────────────────────────────────────────────────

export default function Tablero() {
  const qc = useQueryClient()
  const [arrastrada, setArrastrada] = useState<Tarjeta | null>(null)

  const { data, isLoading } = useQuery<TableroDatos>({
    queryKey: ['agil-tablero'], queryFn: () => agilApi.tablero(),
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['agil-tablero'] })
    qc.invalidateQueries({ queryKey: ['agil-metricas'] })
    qc.invalidateQueries({ queryKey: ['agil-sprints'] })
  }

  const mover = useMutation({
    mutationFn: ({ id, estado }: { id: number; estado: string }) =>
      agilApi.mover(id, estado),
    onSuccess: refrescar,
    // El servidor rechaza si la columna llegó a su límite; el mensaje explica
    // qué hacer, así que se muestra tal cual.
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const estimar = useMutation({
    mutationFn: ({ id, puntos }: { id: number; puntos: number }) =>
      agilApi.actualizar(id, { puntos }),
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const limite = useMutation({
    mutationFn: ({ estado, valor }: { estado: string; valor: number | null }) =>
      agilApi.configurarColumna(estado, { limite_wip: valor }),
    onSuccess: () => { refrescar(); toast.success('Límite actualizado') },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  if (isLoading || !data) {
    return <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 3 }} />
  }

  return (
    <Box>
      {data.sprint ? (
        <Card sx={{ borderRadius: 3, p: 2, mb: 2 }}>
          <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap" useFlexGap>
            <Box sx={{ flex: 1, minWidth: 220 }}>
              <Typography variant="subtitle2" fontWeight={800}>{data.sprint.nombre}</Typography>
              {data.sprint.objetivo && (
                <Typography variant="caption" color="text.secondary">
                  {data.sprint.objetivo}
                </Typography>
              )}
            </Box>
            <Chip label={data.sprint.estado} size="small" sx={{
              fontWeight: 700, bgcolor: `${ESTADO.exito}1A`, color: ESTADO.exito,
            }} />
            {data.sprint.inicio && (
              <Typography variant="caption" color="text.secondary">
                {data.sprint.inicio} → {data.sprint.fin}
              </Typography>
            )}
          </Stack>
        </Card>
      ) : (
        <Alert severity="info" sx={{ mb: 2 }}>
          No hay ningún sprint activo. El tablero muestra lo que está en curso fuera
          de sprint; para trabajar por iteraciones, cree uno en la pestaña Sprints.
        </Alert>
      )}

      <Box sx={{ display: 'flex', gap: 1.5, overflowX: 'auto', pb: 1 }}>
        {data.columnas.map(c => (
          <Columna
            key={c.estado} c={c} arrastrada={arrastrada}
            onArrastrar={setArrastrada}
            onSoltar={estado => {
              if (arrastrada && arrastrada.estado !== estado) {
                mover.mutate({ id: arrastrada.id, estado })
              }
              setArrastrada(null)
            }}
            onEstimar={(t, puntos) => estimar.mutate({ id: t.id, puntos })}
            onLimite={(estado, valor) => limite.mutate({ estado, valor })}
          />
        ))}
      </Box>

      <Divider sx={{ my: 2 }} />
      <Typography variant="caption" color="text.secondary">
        Arrastre las tarjetas entre columnas. El límite de trabajo en curso se hace
        cumplir en el servidor: si una columna está llena, el movimiento se rechaza.
      </Typography>
    </Box>
  )
}
