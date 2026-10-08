/**
 * Métricas del equipo: burndown, velocidad y tiempos.
 *
 * Las tres responden preguntas distintas y conviene no confundirlas:
 *   · Burndown: ¿vamos a alcanzar en este sprint?
 *   · Velocidad: ¿cuánto cabe de verdad en un sprint?
 *   · Tiempo de ciclo: ¿cuánto tardamos en terminar algo una vez empezado?
 *
 * El tiempo de ciclo es el que el equipo puede mejorar. El de entrega incluye
 * la espera en el backlog, que depende de cómo se prioriza, no de cómo se
 * trabaja — por eso se muestran separados.
 */
import {
  Box, Card, Typography, Stack, Skeleton, Alert, Chip, Divider, Tooltip,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { agilApi, type MetricasAgiles as Datos } from './api'

function Cifra({ etiqueta, valor, pie, color }: {
  etiqueta: string; valor: string; pie?: string; color?: string
}) {
  return (
    <Box sx={{ flex: 1, minWidth: 150 }}>
      <Typography variant="caption" color="text.secondary">{etiqueta}</Typography>
      <Typography variant="h6" fontWeight={800} sx={{
        fontVariantNumeric: 'tabular-nums', color: color ?? PALETA.tinta, lineHeight: 1.3,
      }}>
        {valor}
      </Typography>
      {pie && <Typography variant="caption" color="text.secondary">{pie}</Typography>}
    </Box>
  )
}

export default function MetricasAgiles() {
  const { data, isLoading } = useQuery<Datos>({
    queryKey: ['agil-metricas'], queryFn: agilApi.metricas,
  })

  if (isLoading || !data) {
    return <Skeleton variant="rectangular" height={400} sx={{ borderRadius: 3 }} />
  }

  const topeVel = Math.max(1, ...data.velocidad.flatMap(v => [v.comprometidos, v.completados]))
  const topeBurn = Math.max(1, ...data.burndown.map(p => p.ideal))
  const totalTipos = Object.values(data.por_tipo).reduce((a, b) => a + b, 0)

  return (
    <Box>
      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <Cifra
            etiqueta="Tiempo de ciclo" color={COLOR_MODULO}
            valor={data.tiempo_ciclo_promedio != null
              ? `${data.tiempo_ciclo_promedio} días` : 'sin datos'}
            pie="desde que se empieza hasta que se resuelve"
          />
          <Divider orientation="vertical" flexItem />
          <Cifra
            etiqueta="Tiempo de entrega"
            valor={data.tiempo_entrega_promedio != null
              ? `${data.tiempo_entrega_promedio} días` : 'sin datos'}
            pie="desde que el cliente lo pide; incluye la espera en el backlog"
          />
          <Divider orientation="vertical" flexItem />
          <Cifra
            etiqueta="Abiertas" valor={String(totalTipos)}
            pie="solicitudes sin cerrar"
          />
        </Stack>
      </Card>

      {/* Burndown */}
      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
        <Typography variant="subtitle2" fontWeight={800} mb={0.5}>
          Burndown del sprint activo
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Puntos que faltan por terminar. La línea gris es el ritmo ideal.
        </Typography>

        {data.burndown.length === 0 ? (
          <Alert severity="info" sx={{ mt: 2 }}>
            No hay sprint activo con fechas. Active uno para ver su avance día a día.
          </Alert>
        ) : (
          <Box sx={{ mt: 2 }}>
            <Stack direction="row" alignItems="flex-end" spacing={0.5} sx={{ height: 180 }}>
              {data.burndown.map(p => (
                <Tooltip
                  key={p.fecha}
                  title={`${p.fecha} · ideal ${p.ideal} pt${
                    p.real != null ? ` · real ${p.real} pt` : ''}`}
                >
                  <Box sx={{ flex: 1, minWidth: 4, height: '100%', position: 'relative' }}>
                    <Box sx={{
                      position: 'absolute', bottom: 0, width: '100%',
                      height: `${(p.ideal / topeBurn) * 100}%`,
                      bgcolor: PALETA.niebla, borderRadius: '2px 2px 0 0',
                    }} />
                    {p.real != null && (
                      <Box sx={{
                        position: 'absolute', bottom: 0, width: '60%', left: '20%',
                        height: `${(p.real / topeBurn) * 100}%`,
                        bgcolor: p.real > p.ideal ? ESTADO.alerta : ESTADO.exito,
                        borderRadius: '2px 2px 0 0',
                      }} />
                    )}
                  </Box>
                </Tooltip>
              ))}
            </Stack>
            <Stack direction="row" spacing={2} mt={1.5}>
              <Stack direction="row" spacing={0.75} alignItems="center">
                <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: PALETA.niebla }} />
                <Typography variant="caption">Ideal</Typography>
              </Stack>
              <Stack direction="row" spacing={0.75} alignItems="center">
                <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: ESTADO.exito }} />
                <Typography variant="caption">Real, al ritmo o mejor</Typography>
              </Stack>
              <Stack direction="row" spacing={0.75} alignItems="center">
                <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: ESTADO.alerta }} />
                <Typography variant="caption">Real, por detrás</Typography>
              </Stack>
            </Stack>
          </Box>
        )}
      </Card>

      {/* Velocidad */}
      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
        <Typography variant="subtitle2" fontWeight={800} mb={0.5}>Velocidad</Typography>
        <Typography variant="caption" color="text.secondary">
          Lo comprometido contra lo completado, por sprint cerrado. Es lo que dice
          cuánto cabe de verdad en la próxima iteración.
        </Typography>

        {data.velocidad.length === 0 ? (
          <Alert severity="info" sx={{ mt: 2 }}>
            Todavía no hay sprints cerrados. La velocidad aparece al cerrar el primero.
          </Alert>
        ) : (
          <Stack spacing={1.5} mt={2}>
            {data.velocidad.map(v => (
              <Box key={v.sprint}>
                <Stack direction="row" alignItems="baseline" spacing={1} mb={0.5}>
                  <Typography variant="caption" fontWeight={700} sx={{ minWidth: 110 }}>
                    {v.sprint}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    comprometidos {v.comprometidos} · completados {v.completados}
                  </Typography>
                  {v.completados < v.comprometidos && (
                    <Chip label={`${v.comprometidos - v.completados} pt no cupieron`}
                      size="small" sx={{
                        height: 17, fontSize: 9.5, fontWeight: 700,
                        bgcolor: `${ESTADO.alerta}1F`, color: ESTADO.alerta,
                      }} />
                  )}
                </Stack>
                <Stack spacing={0.4}>
                  <Box sx={{
                    height: 8, borderRadius: 99, bgcolor: PALETA.niebla,
                    width: `${(v.comprometidos / topeVel) * 100}%`, minWidth: 3,
                  }} />
                  <Box sx={{
                    height: 8, borderRadius: 99, bgcolor: ESTADO.exito,
                    width: `${(v.completados / topeVel) * 100}%`, minWidth: 3,
                  }} />
                </Stack>
              </Box>
            ))}
          </Stack>
        )}
      </Card>

      {/* Composición */}
      <Card sx={{ borderRadius: 3, p: 2.5 }}>
        <Typography variant="subtitle2" fontWeight={800} mb={0.5}>
          En qué se va el trabajo
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Solicitudes abiertas por tipo. Mucho «error» sostenido significa que se
          está apagando incendios en vez de construir.
        </Typography>
        <Stack direction="row" spacing={1} mt={2} flexWrap="wrap" useFlexGap>
          {Object.entries(data.por_tipo).map(([tipo, n]) => (
            <Chip
              key={tipo}
              label={`${tipo.toLowerCase()}: ${n}`}
              sx={{
                fontWeight: 700,
                bgcolor: tipo === 'ERROR' ? `${ESTADO.peligro}1A` : `${COLOR_MODULO}14`,
                color: tipo === 'ERROR' ? ESTADO.peligro : COLOR_MODULO,
              }}
            />
          ))}
          {totalTipos === 0 && (
            <Typography variant="body2" color="text.secondary">
              No hay solicitudes abiertas.
            </Typography>
          )}
        </Stack>
      </Card>
    </Box>
  )
}
