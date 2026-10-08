/**
 * El reloj de trabajo de una incidencia, y el salto libre entre estados.
 *
 * EL RELOJ
 * Tres botones: empezar, pausar, terminar. Cada persona tiene el suyo —dos
 * pueden trabajar la misma incidencia a la vez y cada una cuenta sus horas—, y
 * el tiempo lo mide el servidor: si lo llevara el navegador, cerrar la pestaña
 * perdería el tramo.
 *
 * **No condiciona nada.** Se puede cerrar una incidencia sin haber tocado el
 * reloj. En cuanto un registro de tiempo se vuelve un trámite obligatorio, la
 * gente lo rellena de cualquier forma para poder seguir, y entonces mide peor
 * que no tenerlo.
 *
 * EL SALTO DE ESTADO
 * El flujo declarado describe el camino normal y para eso sirve. Pero el trabajo
 * real se devuelve: una revisión encuentra algo, alguien movió la tarjeta por
 * error. Sin una salida, eso se resuelve creando otra incidencia, y entonces el
 * historial de la original miente porque nunca vuelve atrás. Acá se puede ir a
 * cualquier estado, y queda anotado que fue un movimiento manual.
 */
import { useEffect, useState } from 'react'
import {
  Box, Button, Chip, Divider, Menu, MenuItem, Stack, Tooltip, Typography,
} from '@mui/material'
import {
  PlayArrow, Pause, Stop, Timer, SwapHoriz, Check,
} from '@mui/icons-material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { gestionApi, mensajeDeError } from './api'
import { PALETA } from '@/config/marca'

interface EstadoFlujo {
  id: number; nombre: string; categoria: string
  color?: string | null; actual: boolean
}

/** «2 h 14 min». Los segundos sobran para leer cuánto se trabajó. */
export function duracion(segundos: number): string {
  const s = Math.max(0, Math.round(segundos))
  if (s < 60) return `${s} s`
  const minutos = Math.floor(s / 60)
  if (minutos < 60) return `${minutos} min`
  const horas = Math.floor(minutos / 60)
  const resto = minutos % 60
  return resto ? `${horas} h ${resto} min` : `${horas} h`
}

const COLOR_CATEGORIA: Record<string, string> = {
  SIN_CLASIFICAR: '#8C8C8C',
  POR_HACER: '#64748B',
  EN_CURSO: '#2563EB',
  EN_REVISION: '#7C3AED',
  TERMINADO: '#16A34A',
  DESCARTADA: '#94A3B8',
}

export function BarraDeTrabajo({ incidenciaId, onCambio }: {
  incidenciaId: number
  onCambio: () => void
}) {
  const qc = useQueryClient()
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  const [ahora, setAhora] = useState(Date.now())

  const { data: tiempo } = useQuery({
    queryKey: ['gestion', 'tiempo', incidenciaId],
    queryFn: () => gestionApi.tiempo(incidenciaId),
  })
  const { data: estados } = useQuery<EstadoFlujo[]>({
    queryKey: ['gestion', 'estados-flujo', incidenciaId],
    queryFn: () => gestionApi.estadosDelFlujo(incidenciaId),
  })

  const corriendo = tiempo?.corriendo ?? null

  // El contador avanza en pantalla mientras hay un tramo abierto. Solo entonces:
  // un intervalo permanente redibuja la pantalla cada segundo sin motivo.
  useEffect(() => {
    if (!corriendo) return
    const id = setInterval(() => setAhora(Date.now()), 1000)
    return () => clearInterval(id)
  }, [corriendo])

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['gestion', 'tiempo', incidenciaId] })
    onCambio()
  }

  // Los tres relojes van explícitos y no salen de una fábrica: `useMutation` es
  // un hook, y envolverlo en una función que se llama tres veces funciona solo
  // mientras nadie ponga una condición delante. Escrito así no hay forma de
  // romperlo sin darse cuenta.
  const iniciar = useMutation({
    mutationFn: () => gestionApi.iniciarTiempo(incidenciaId),
    onSuccess: () => { toast.success('Reloj en marcha'); refrescar() },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo iniciar')),
  })
  const pausar = useMutation({
    mutationFn: () => gestionApi.pausarTiempo(incidenciaId),
    onSuccess: (r: any) => {
      toast.success(`Pausado tras ${r?.minutos ?? 0} min`); refrescar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo pausar')),
  })
  const finalizar = useMutation({
    mutationFn: () => gestionApi.finalizarTiempo(incidenciaId),
    onSuccess: (r: any) => {
      toast.success(`Trabajo finalizado · ${r?.minutos ?? 0} min`); refrescar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo finalizar')),
  })

  const mover = useMutation({
    mutationFn: (estadoId: number) => gestionApi.moverAEstado(incidenciaId, estadoId),
    onSuccess: () => {
      toast.success('Estado actualizado')
      setMenu(null)
      qc.invalidateQueries({ queryKey: ['gestion', 'estados-flujo', incidenciaId] })
      onCambio()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo mover')),
  })

  const enVivo = corriendo
    ? Math.floor((ahora - Date.parse(corriendo.inicio)) / 1000)
    : 0
  const total = (tiempo?.total_segundos ?? 0) + enVivo
  const actual = estados?.find(e => e.actual)

  return (
    <Box sx={{
      border: '1px solid', borderColor: PALETA.niebla, borderRadius: 2,
      px: 1.5, py: 1.25, bgcolor: corriendo ? '#EFF6FF' : PALETA.bruma,
    }}>
      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
        <Timer sx={{ fontSize: 18, color: corriendo ? '#2563EB' : PALETA.acero }} />
        <Box sx={{ minWidth: 92 }}>
          <Typography sx={{ fontSize: 16, fontWeight: 800,
                            fontVariantNumeric: 'tabular-nums',
                            color: corriendo ? '#2563EB' : 'inherit' }}>
            {duracion(total)}
          </Typography>
          <Typography sx={{ fontSize: 10.5, color: PALETA.acero }}>
            {corriendo ? 'trabajando ahora' : 'tiempo registrado'}
          </Typography>
        </Box>

        {corriendo ? (
          <>
            <Button size="small" variant="outlined" startIcon={<Pause />}
                    disabled={pausar.isPending}
                    onClick={() => pausar.mutate()}
                    sx={{ textTransform: 'none' }}>
              Pausar
            </Button>
            <Button size="small" variant="contained" startIcon={<Stop />}
                    disabled={finalizar.isPending}
                    onClick={() => finalizar.mutate()}
                    sx={{ textTransform: 'none' }}>
              Terminar
            </Button>
          </>
        ) : (
          <Button size="small" variant="contained" startIcon={<PlayArrow />}
                  disabled={iniciar.isPending}
                  onClick={() => iniciar.mutate()}
                  sx={{ textTransform: 'none' }}>
            {total > 0 ? 'Reanudar' : 'Empezar'}
          </Button>
        )}

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

        <Button
          size="small" variant="outlined" startIcon={<SwapHoriz />}
          onClick={e => setMenu(e.currentTarget)}
          sx={{ textTransform: 'none' }}
        >
          {actual?.nombre ?? 'Mover a…'}
        </Button>
        <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
          {/* Todos los estados, no solo los siguientes: volver atrás es parte
              del trabajo real y no una excepción que haya que esconder. */}
          {estados?.map(e => (
            <MenuItem key={e.id} disabled={e.actual || mover.isPending}
                      onClick={() => mover.mutate(e.id)}>
              <Box sx={{
                width: 9, height: 9, borderRadius: '50%', mr: 1.25,
                bgcolor: e.color || COLOR_CATEGORIA[e.categoria] || '#94A3B8',
              }} />
              {e.nombre}
              {e.actual && <Check sx={{ fontSize: 15, ml: 1, color: PALETA.acero }} />}
            </MenuItem>
          ))}
        </Menu>

        {!!tiempo?.por_persona?.length && (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap
                 sx={{ ml: 'auto' }}>
            {tiempo.por_persona.slice(0, 4).map((p: any) => (
              <Tooltip key={p.usuario} title={`${p.usuario}: ${duracion(p.segundos)}`}>
                <Chip size="small" variant="outlined"
                      label={`${p.usuario} · ${duracion(p.segundos)}`}
                      sx={{ height: 20, fontSize: 10.5 }} />
              </Tooltip>
            ))}
          </Stack>
        )}
      </Stack>
    </Box>
  )
}
