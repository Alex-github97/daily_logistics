/**
 * El tablero por estados del flujo.
 *
 * Las columnas NO están escritas acá: salen del workflow del proyecto, que es
 * configurable. Un tablero con columnas fijas obliga a tocar código cada vez que
 * un equipo cambia cómo trabaja, que es justo lo que este módulo evita.
 *
 * Al soltar una tarjeta se busca la transición que lleva a esa columna y se
 * aplica con sus reglas. No se cambia el estado por la vía directa: si se
 * pudiera, el motor de workflow —los límites de trabajo en curso, quién puede
 * mover qué— sería una sugerencia.
 *
 * Las tarjetas y las columnas se definen en el ámbito del módulo y no dentro del
 * padre: definidas adentro, React las trata como tipos nuevos en cada render, las
 * desmonta y las vuelve a montar, y eso cancela el arrastre a mitad de camino.
 */
import { useMemo, useState } from 'react'
import {
  Box, Card, Stack, Typography, Chip, Skeleton, Alert, Tooltip,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  gestionApi, mensajeDeError,
  type EstadoFlujo, type Incidencia, type Proyecto,
} from './api'

const COLOR_CATEGORIA: Record<string, string> = {
  SIN_CLASIFICAR: PALETA.acero,
  POR_HACER: PALETA.grafito,
  EN_CURSO: COLOR_MODULO,
  TERMINADO: ESTADO.exito,
}

function Tarjeta({
  t, onArrastrar, onAbrir,
}: {
  t: Incidencia
  onArrastrar: (t: Incidencia) => void
  onAbrir: (id: number) => void
}) {
  return (
    <Card
      draggable
      onDragStart={e => {
        e.dataTransfer.effectAllowed = 'move'
        // Firefox no inicia el arrastre si no se escribe algo en dataTransfer.
        e.dataTransfer.setData('text/plain', String(t.id))
        onArrastrar(t)
      }}
      onClick={() => onAbrir(t.id)}
      sx={{
        p: 1.25, mb: 1, borderRadius: 2, cursor: 'grab',
        borderLeft: `3px solid ${t.color_prioridad || PALETA.acero}`,
        '&:active': { cursor: 'grabbing' },
        '&:hover': { boxShadow: 3 },
      }}
    >
      <Stack direction="row" alignItems="center" spacing={0.5}>
        <Typography variant="caption" sx={{
          fontFamily: 'monospace', fontWeight: 700, color: PALETA.acero, fontSize: 10.5,
        }}>
          {t.clave}
        </Typography>
        {t.icono && <Typography variant="caption">{t.icono}</Typography>}
      </Stack>
      <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.4, lineHeight: 1.35 }}>
        {t.resumen}
      </Typography>
      <Stack direction="row" spacing={0.5} mt={1} flexWrap="wrap" useFlexGap>
        {t.puntos != null && (
          <Chip label={`${t.puntos} pt`} size="small" sx={{
            height: 18, fontSize: 9.5, fontWeight: 800,
            bgcolor: `${COLOR_MODULO}1A`, color: COLOR_MODULO,
          }} />
        )}
        {t.asignado && (
          <Chip label={t.asignado} size="small"
            sx={{ height: 18, fontSize: 9.5, bgcolor: PALETA.niebla }} />
        )}
        {t.ticket_id && (
          <Chip label="soporte" size="small" variant="outlined"
            sx={{ height: 18, fontSize: 9 }} />
        )}
      </Stack>
    </Card>
  )
}

function Columna({
  estado, tarjetas, onSoltar, onAbrir, onArrastrar,
}: {
  estado: EstadoFlujo
  tarjetas: Incidencia[]
  onSoltar: (estadoId: number) => void
  onAbrir: (id: number) => void
  onArrastrar: (t: Incidencia) => void
}) {
  const [encima, setEncima] = useState(false)
  const color = COLOR_CATEGORIA[estado.categoria] ?? PALETA.acero
  const lleno = estado.limite_wip != null && tarjetas.length >= estado.limite_wip

  return (
    <Box
      onDragOver={e => { e.preventDefault(); setEncima(true) }}
      onDragLeave={() => setEncima(false)}
      onDrop={e => { e.preventDefault(); setEncima(false); onSoltar(estado.id) }}
      sx={{
        width: 280, flexShrink: 0, p: 1, borderRadius: 2,
        bgcolor: encima ? `${COLOR_MODULO}0F` : PALETA.bruma,
        border: `1px solid ${encima ? COLOR_MODULO : 'transparent'}`,
        transition: 'background-color .15s, border-color .15s',
      }}
    >
      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ px: 0.5, mb: 1 }}>
        <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: color }} />
        <Typography variant="caption" sx={{ fontWeight: 800, letterSpacing: '0.04em' }}>
          {estado.nombre.toUpperCase()}
        </Typography>
        <Typography variant="caption" sx={{ color: PALETA.acero }}>
          {tarjetas.length}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {estado.limite_wip != null && (
          <Tooltip title="Límite de trabajo en curso. Lo hace cumplir el servidor: al llegar al tope, la incidencia no se deja mover acá.">
            <Chip label={`${tarjetas.length}/${estado.limite_wip}`} size="small" sx={{
              height: 17, fontSize: 9.5, fontWeight: 800,
              bgcolor: lleno ? `${ESTADO.alerta}22` : PALETA.niebla,
              color: lleno ? ESTADO.alerta : PALETA.grafito,
            }} />
          </Tooltip>
        )}
      </Stack>

      <Box sx={{ minHeight: 80 }}>
        {tarjetas.map(t => (
          <Tarjeta key={t.id} t={t} onAbrir={onAbrir} onArrastrar={onArrastrar} />
        ))}
      </Box>
    </Box>
  )
}

export default function GestionTablero({
  proyecto, onAbrir,
}: {
  proyecto: Proyecto
  onAbrir: (id: number) => void
}) {
  const qc = useQueryClient()
  const [arrastrada, setArrastrada] = useState<Incidencia | null>(null)

  const { data: config } = useQuery({
    queryKey: ['gestion', 'config', proyecto.id],
    queryFn: () => gestionApi.configuracion(proyecto.id),
    staleTime: 5 * 60_000,
  })

  const { data: pagina, isLoading } = useQuery({
    queryKey: ['gestion', 'tablero', proyecto.id],
    queryFn: () => gestionApi.listar({ proyecto_id: proyecto.id, limite: 100 }),
  })

  const estados: EstadoFlujo[] = useMemo(() => {
    const wf = config?.workflows.find(w => w.id === proyecto.workflow_id)
      ?? config?.workflows.find(w => w.por_defecto)
      ?? config?.workflows[0]
    return wf?.estados ?? []
  }, [config, proyecto.workflow_id])

  const mover = useMutation({
    mutationFn: async ({ id, estadoId }: { id: number; estadoId: number }) => {
      // Se pregunta al servidor qué transiciones hay: la que lleva a esa columna
      // puede no existir, o existir y no estar disponible para quien la mueve.
      const detalle = await gestionApi.detalle(id)
      const t = detalle.transiciones.find(x => x.destino_id === estadoId)
      if (!t) {
        throw new Error(
          `Desde «${detalle.incidencia.estado}» no hay ningún movimiento hacia ` +
          `esa columna. Reviselo en la configuración del flujo.`)
      }
      if (!t.lista) throw new Error(t.impedimentos.join('; '))
      return gestionApi.transicionar(id, t.id)
    },
    onSuccess: r => {
      toast.success(`Ahora está en «${r.incidencia.estado}»`)
      qc.invalidateQueries({ queryKey: ['gestion', 'tablero', proyecto.id] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo mover')),
  })

  if (isLoading) {
    return (
      <Stack direction="row" spacing={2}>
        {[0, 1, 2, 3].map(i => (
          <Skeleton key={i} variant="rounded" width={280} height={320} />
        ))}
      </Stack>
    )
  }

  if (!estados.length) {
    return (
      <Alert severity="info">
        Este proyecto todavía no tiene un flujo con estados. Asígnele uno en la
        configuración del proyecto.
      </Alert>
    )
  }

  const porEstado = new Map<number, Incidencia[]>()
  estados.forEach(e => porEstado.set(e.id, []))
  ;(pagina?.resultados ?? []).forEach(t => {
    if (t.estado_id != null && porEstado.has(t.estado_id)) {
      porEstado.get(t.estado_id)!.push(t)
    }
  })

  return (
    <Box sx={{ overflowX: 'auto', pb: 1 }}>
      <Stack direction="row" spacing={1.5} sx={{ minWidth: 'min-content' }}>
        {estados.map(e => (
          <Columna
            key={e.id} estado={e} tarjetas={porEstado.get(e.id) ?? []}
            onAbrir={onAbrir} onArrastrar={setArrastrada}
            onSoltar={estadoId => {
              if (arrastrada && arrastrada.estado_id !== estadoId) {
                mover.mutate({ id: arrastrada.id, estadoId })
              }
              setArrastrada(null)
            }}
          />
        ))}
      </Stack>
    </Box>
  )
}
