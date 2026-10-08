/**
 * Lo que se está rompiendo en los navegadores de los clientes.
 *
 * POR QUÉ EXISTE
 * Antes uno se enteraba de un error cuando un cliente llamaba, y solo de los
 * errores de los clientes que se molestan en llamar. Los demás simplemente
 * dejan de usar la pantalla. Acá llegan solos, con la ruta, la empresa y cuántas
 * veces pasó.
 *
 * POR QUÉ AGRUPADOS
 * Quinientas apariciones del mismo error son un problema, no quinientos. La
 * lista se ordena por frecuencia y no por fecha: lo que más se repite es lo que
 * hay que arreglar primero, aunque el último caso sea de anteayer.
 *
 * POR QUÉ CONVERTIR A MANO
 * Convertir cada fallo en incidencia automáticamente llenaría el tablero de
 * duplicados y de rarezas de un solo navegador. Quien revisa decide cuál merece
 * trabajo, y al convertirlo el grupo deja de aparecer como nuevo.
 */
import { useState } from 'react'
import {
  Alert, Box, Button, Card, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { BugReport, ArrowForward } from '@mui/icons-material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { consolaApi, gestionApi, mensajeDeError } from './api'
import { PALETA } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

interface Fallo {
  firma: string
  mensaje: string
  veces: number
  empresas: string[]
  rutas: string[]
  primera: string | null
  ultima: string | null
  referencia: string | null
  incidencia_id: number | null
  incidencia_clave: string | null
}

/** «Ocurrió 3 veces en 2 empresas.» El plural se decide, no se deja en
 *  «vez/veces»: una plantilla con las dos formas a la vez se lee como un
 *  descuido y le resta seriedad a la pantalla que reporta los errores. */
function alcance(f: Fallo | null): string {
  if (!f) return ''
  const veces = f.veces === 1 ? 'Ocurrió una vez' : `Ocurrió ${f.veces} veces`
  const n = f.empresas.length
  const donde = n === 0 ? '' : n === 1 ? `, en ${f.empresas[0]}`
    : `, en ${n} empresas`
  return `${veces}${donde}.`
}

/** La bitácora guarda el código de la empresa, que a veces llega con el prefijo
 *  del esquema. Se quita para mostrar: quien lee la consola conoce «demoflota»,
 *  no «cli_demoflota». */
const sinPrefijo = (codigo: string) => codigo.replace(/^cli_/, '')

const cuando = (iso: string | null) =>
  iso ? aFecha(iso).toLocaleString('es-CO',
    { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export default function Fallos() {
  const qc = useQueryClient()
  const [dias, setDias] = useState(30)
  const [verAtendidos, setVerAtendidos] = useState(false)
  const [convertir, setConvertir] = useState<Fallo | null>(null)
  const [resumen, setResumen] = useState('')
  const [proyectoId, setProyectoId] = useState<number | ''>('')

  const { data: fallos, isLoading } = useQuery({
    queryKey: ['plataforma', 'fallos', dias, verAtendidos],
    queryFn: () => consolaApi.fallos(dias, verAtendidos),
    refetchInterval: 120_000,
  })

  const { data: proyectos } = useQuery({
    queryKey: ['gestion', 'proyectos', 'todos'],
    queryFn: () => gestionApi.proyectos(false),
  })

  const crear = useMutation({
    mutationFn: () => consolaApi.falloAIncidencia({
      firma: convertir!.firma,
      resumen: resumen.trim() || undefined,
      proyecto_id: proyectoId || undefined,
    }),
    onSuccess: (r: any) => {
      toast.success(r.mensaje ?? 'Incidencia creada')
      setConvertir(null); setResumen(''); setProyectoId('')
      qc.invalidateQueries({ queryKey: ['plataforma', 'fallos'] })
      qc.invalidateQueries({ queryKey: ['gestion'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear')),
  })

  const abrir = (f: Fallo) => {
    setConvertir(f)
    setResumen(`Fallo de interfaz: ${f.mensaje}`.slice(0, 160))
    setProyectoId('')
  }

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between"
             sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 800 }}>
            Fallos de la interfaz
          </Typography>
          <Typography variant="body2" sx={{ color: PALETA.grafito }}>
            Pantallas que se rompieron en el navegador de alguien. Llegan solas.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <TextField
            select size="small" label="Período" value={dias}
            onChange={e => setDias(Number(e.target.value))} sx={{ width: 150 }}
          >
            <MenuItem value={1}>Último día</MenuItem>
            <MenuItem value={7}>Última semana</MenuItem>
            <MenuItem value={30}>Último mes</MenuItem>
            <MenuItem value={90}>Últimos 3 meses</MenuItem>
          </TextField>
          <Button size="small" variant={verAtendidos ? 'contained' : 'outlined'}
                  onClick={() => setVerAtendidos(v => !v)}
                  sx={{ textTransform: 'none' }}>
            {verAtendidos ? 'Ocultar atendidos' : 'Ver atendidos'}
          </Button>
        </Stack>
      </Stack>

      {isLoading ? (
        <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress /></Box>
      ) : !fallos?.length ? (
        // El vacío aquí es una buena noticia y conviene decirlo así: en una
        // lista de errores, «no hay nada» se lee como «esto no funciona».
        <Alert severity="success" sx={{ fontSize: 14 }}>
          Ningún fallo reportado en este período. Cuando una pantalla se rompa en
          el navegador de un cliente, aparecerá aquí sola.
        </Alert>
      ) : (
        <Card variant="outlined" sx={{ borderRadius: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: PALETA.bruma }}>
                <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 70 }} align="center">
                  VECES
                </TableCell>
                <TableCell sx={{ fontWeight: 800, fontSize: 11 }}>QUÉ FALLÓ</TableCell>
                <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 210 }}>
                  DÓNDE
                </TableCell>
                <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 150 }}>
                  EMPRESAS
                </TableCell>
                <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 130 }}>
                  ÚLTIMA VEZ
                </TableCell>
                <TableCell sx={{ width: 150 }} />
              </TableRow>
            </TableHead>
            <TableBody>
              {fallos.map((f: Fallo) => (
                <TableRow key={f.firma} hover>
                  <TableCell align="center">
                    <Chip
                      label={f.veces} size="small"
                      sx={{
                        fontWeight: 800, height: 22,
                        // El color viene del alcance, no de un umbral inventado:
                        // un fallo que toca a varias empresas es peor que uno
                        // que se repite mucho en una sola.
                        bgcolor: f.empresas.length > 1 ? '#FEE2E2'
                          : f.veces >= 10 ? '#FEF3C7' : PALETA.bruma,
                        color: f.empresas.length > 1 ? '#B91C1C'
                          : f.veces >= 10 ? '#B45309' : PALETA.grafito,
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
                      {f.mensaje}
                    </Typography>
                    {f.referencia && (
                      <Typography variant="caption" sx={{ color: PALETA.acero,
                                                          fontFamily: 'ui-monospace, monospace' }}>
                        ref. {f.referencia}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.25}>
                      {f.rutas.slice(0, 3).map(r => (
                        <Typography key={r} variant="caption"
                                    sx={{ fontFamily: 'ui-monospace, monospace',
                                          fontSize: 11 }}>
                          {r}
                        </Typography>
                      ))}
                      {f.rutas.length > 3 && (
                        <Typography variant="caption" sx={{ color: PALETA.acero }}>
                          y {f.rutas.length - 3} más
                        </Typography>
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {f.empresas.length === 0 ? (
                        <Typography variant="caption" sx={{ color: PALETA.acero }}>
                          sin identificar
                        </Typography>
                      ) : f.empresas.map(e => (
                        <Chip key={e} label={sinPrefijo(e)} size="small"
                              variant="outlined"
                              sx={{ height: 18, fontSize: 10 }} />
                      ))}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Tooltip title={`Primera vez: ${cuando(f.primera)}`}>
                      <Typography variant="caption">{cuando(f.ultima)}</Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right">
                    {f.incidencia_clave ? (
                      <Chip size="small" label={f.incidencia_clave}
                            sx={{ fontWeight: 700, fontSize: 11,
                                  bgcolor: '#DCFCE7', color: '#15803D' }} />
                    ) : (
                      <Button size="small" variant="outlined"
                              endIcon={<ArrowForward sx={{ fontSize: 14 }} />}
                              onClick={() => abrir(f)}
                              sx={{ textTransform: 'none', fontSize: 12 }}>
                        Crear incidencia
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <Dialog open={!!convertir} onClose={() => setConvertir(null)}
              maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <BugReport sx={{ color: '#B45309' }} />
            Convertir en incidencia
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Alert severity="info" sx={{ fontSize: 13 }}>
              {alcance(convertir)} La incidencia se crea con el recuento, las
              pantallas afectadas y las empresas, para poder reproducirlo sin
              volver aquí.
            </Alert>
            <TextField
              size="small" label="Título de la incidencia" fullWidth multiline
              minRows={2} value={resumen}
              onChange={e => setResumen(e.target.value)}
              helperText="Reescríbalo como lo entendería quien lo va a arreglar."
            />
            <TextField
              select size="small" label="Proyecto" fullWidth value={proyectoId}
              onChange={e => setProyectoId(Number(e.target.value) || '')}
            >
              <MenuItem value=""><em>El que recibe las solicitudes</em></MenuItem>
              {proyectos?.map((p: any) => (
                <MenuItem key={p.id} value={p.id}>{p.clave} · {p.nombre}</MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setConvertir(null)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button variant="contained" disabled={crear.isPending}
                  onClick={() => crear.mutate()} sx={{ textTransform: 'none' }}>
            {crear.isPending ? 'Creando…' : 'Crear incidencia'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
