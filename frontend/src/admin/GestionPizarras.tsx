/**
 * Pizarras: tableros de indicadores armados por quien los usa.
 *
 * Cada recuadro se apoya en el mismo lenguaje de filtros que la lista, y cada
 * cifra se puede pulsar para abrir la lista que la produjo. Ese enlace es lo que
 * hace que la pizarra sirva: un número que no se puede desglosar es un número en
 * el que nadie confía, y termina ignorándose.
 *
 * Los cálculos vienen del servidor. Contar en el navegador exigiría bajarse todas
 * las incidencias para sumar seis números.
 */
import { useState } from 'react'
import {
  Box, Card, Stack, Typography, Button, IconButton, MenuItem, Skeleton, Alert, Dialog, DialogTitle, DialogContent, DialogActions, Tooltip, Chip, Divider,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { Add, Close, Dashboard, OpenInNew } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { DialogoConfirmar } from './GestionDialogos'
import {
  gestionApi, mensajeDeError,
  type Pizarra, type Proyecto, type Widget,
} from './api'

const PALETA_BARRAS = [
  COLOR_MODULO, ESTADO.exito, ESTADO.alerta, ESTADO.peligro,
  PALETA.grafito, '#7C3AED', '#0891B2', PALETA.acero,
]

// ─── Un recuadro ──────────────────────────────────────────────────────────────

function Recuadro({
  widget, onQuitar, onAbrirLista, onAbrir,
}: {
  widget: Widget
  onQuitar: (id: number) => void
  onAbrirLista: (expresion: string) => void
  onAbrir: (id: number) => void
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['gestion', 'widget', widget.id],
    queryFn: () => gestionApi.datosWidget(widget.id),
  })

  return (
    <Card variant="outlined" sx={{
      borderRadius: 2, p: 1.75, height: '100%',
      display: 'flex', flexDirection: 'column',
    }}>
      <Stack direction="row" alignItems="flex-start" spacing={0.5} mb={1}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" sx={{
            fontWeight: 800, letterSpacing: '0.05em', fontSize: 10,
            color: PALETA.acero,
          }} noWrap>
            {widget.titulo.toUpperCase()}
          </Typography>
          {widget.expresion && (
            <Typography variant="caption" sx={{
              display: 'block', fontFamily: 'monospace', fontSize: 9.5,
              color: PALETA.acero, opacity: 0.75,
            }} noWrap>
              {widget.expresion}
            </Typography>
          )}
        </Box>
        <Tooltip title="Ver la lista completa detrás de este número">
          <IconButton size="small" onClick={() => onAbrirLista(widget.expresion)}>
            <OpenInNew sx={{ fontSize: 13 }} />
          </IconButton>
        </Tooltip>
        <IconButton size="small" onClick={() => onQuitar(widget.id)}>
          <Close sx={{ fontSize: 13 }} />
        </IconButton>
      </Stack>

      {isLoading && <Skeleton height={60} />}
      {error && (
        <Alert severity="warning" sx={{ py: 0, fontSize: 11.5 }}>
          {mensajeDeError(error, 'No se pudo calcular')}
        </Alert>
      )}

      {data?.tipo === 'CONTADOR' && (
        <Box sx={{ flex: 1, display: 'flex', alignItems: 'center' }}>
          <Box>
            <Typography sx={{ fontSize: 40, fontWeight: 800, lineHeight: 1 }}>
              {data.valor}
            </Typography>
            {!!data.puntos && (
              <Typography variant="caption" sx={{ color: PALETA.acero }}>
                {data.puntos} puntos
              </Typography>
            )}
          </Box>
        </Box>
      )}

      {data?.tipo === 'AGRUPADO' && (
        <Stack spacing={0.6} sx={{ flex: 1 }}>
          {(() => {
            const tope = Math.max(...(data.grupos ?? []).map(g => g.cuantas), 1)
            return (data.grupos ?? []).map((g, i) => (
              <Stack key={g.etiqueta} direction="row" alignItems="center" spacing={1}>
                <Typography variant="caption" sx={{ width: 92, fontSize: 11 }} noWrap>
                  {g.etiqueta}
                </Typography>
                <Box sx={{ flex: 1, height: 13, bgcolor: PALETA.bruma, borderRadius: 0.75 }}>
                  <Box sx={{
                    width: `${(g.cuantas / tope) * 100}%`, height: '100%',
                    bgcolor: PALETA_BARRAS[i % PALETA_BARRAS.length], borderRadius: 0.75,
                  }} />
                </Box>
                <Typography variant="caption" sx={{
                  width: 26, textAlign: 'right', fontWeight: 700, fontSize: 11,
                }}>
                  {g.cuantas}
                </Typography>
              </Stack>
            ))
          })()}
          {!data.grupos?.length && (
            <Typography variant="caption" sx={{ color: PALETA.acero }}>
              Nada que cumpla el filtro.
            </Typography>
          )}
        </Stack>
      )}

      {data?.tipo === 'CARGA' && (
        <Stack spacing={0.6} sx={{ flex: 1 }}>
          {(() => {
            const tope = Math.max(...(data.personas ?? []).map(p => p.cuantas), 1)
            return (data.personas ?? []).map(p => (
              <Stack key={p.usuario} direction="row" alignItems="center" spacing={1}>
                <Typography variant="caption" sx={{ width: 92, fontSize: 11 }} noWrap>
                  {p.usuario}
                </Typography>
                <Box sx={{ flex: 1, height: 13, bgcolor: PALETA.bruma, borderRadius: 0.75 }}>
                  <Box sx={{
                    width: `${(p.cuantas / tope) * 100}%`, height: '100%',
                    bgcolor: p.usuario === 'sin asignar' ? ESTADO.alerta : COLOR_MODULO,
                    borderRadius: 0.75,
                  }} />
                </Box>
                <Typography variant="caption" sx={{
                  width: 26, textAlign: 'right', fontWeight: 700, fontSize: 11,
                }}>
                  {p.cuantas}
                </Typography>
              </Stack>
            ))
          })()}
        </Stack>
      )}

      {data?.tipo === 'LISTA' && (
        <Stack spacing={0.4} sx={{ flex: 1 }}>
          {(data.filas ?? []).map(t => (
            <Stack key={t.id} direction="row" spacing={0.75} alignItems="center"
              onClick={() => onAbrir(t.id)}
              sx={{ cursor: 'pointer', '&:hover': { opacity: 0.7 } }}>
              <Typography variant="caption" sx={{
                fontFamily: 'monospace', fontSize: 9.5, fontWeight: 700,
                color: PALETA.acero,
              }}>
                {t.clave}
              </Typography>
              <Typography variant="caption" noWrap sx={{ flex: 1, fontSize: 11.5 }}>
                {t.resumen}
              </Typography>
            </Stack>
          ))}
          {!data.filas?.length && (
            <Typography variant="caption" sx={{ color: PALETA.acero }}>
              Nada que cumpla el filtro.
            </Typography>
          )}
        </Stack>
      )}
    </Card>
  )
}

// ─── La pantalla ──────────────────────────────────────────────────────────────

export default function GestionPizarras({
  proyecto, onAbrir, onAbrirLista,
}: {
  proyecto: Proyecto | null
  onAbrir: (id: number) => void
  onAbrirLista: (expresion: string) => void
}) {
  const qc = useQueryClient()
  const [seleccionada, setSeleccionada] = useState<number | null>(null)
  const [creando, setCreando] = useState(false)
  const [nombrePizarra, setNombrePizarra] = useState('')
  const [agregando, setAgregando] = useState(false)
  const [borrando, setBorrando] = useState(false)

  const [tipo, setTipo] = useState('CONTADOR')
  const [titulo, setTitulo] = useState('')
  const [expresion, setExpresion] = useState('')
  const [agruparPor, setAgruparPor] = useState('estado')
  const [ancho, setAncho] = useState(3)

  const { data: pizarras, isLoading } = useQuery({
    queryKey: ['gestion', 'pizarras'],
    queryFn: gestionApi.pizarras,
  })
  const { data: catalogo } = useQuery({
    queryKey: ['gestion', 'catalogo-widgets'],
    queryFn: gestionApi.catalogoWidgets,
    staleTime: 10 * 60_000,
  })

  const actual = pizarras?.find(p => p.id === seleccionada)
    ?? pizarras?.[0] ?? null

  const crearPizarra = useMutation({
    mutationFn: () => gestionApi.crearPizarra({
      nombre: nombrePizarra, proyecto_id: proyecto?.id ?? null, compartida: true,
    }),
    onSuccess: p => {
      toast.success('Pizarra creada')
      setCreando(false); setNombrePizarra(''); setSeleccionada(p.id)
      qc.invalidateQueries({ queryKey: ['gestion', 'pizarras'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear')),
  })

  const agregar = useMutation({
    mutationFn: () => gestionApi.agregarWidget(actual!.id, {
      tipo, titulo, expresion,
      agrupar_por: tipo === 'AGRUPADO' ? agruparPor : null,
      ancho, alto: 1,
      y: (actual?.widgets.length ?? 0),
    }),
    onSuccess: () => {
      setAgregando(false); setTitulo(''); setExpresion('')
      qc.invalidateQueries({ queryKey: ['gestion', 'pizarras'] })
    },
    onError: (e: any) => {
      const d = e?.response?.data?.detail
      toast.error(d?.consulta ? `El filtro no es válido: ${d.consulta}`
                              : mensajeDeError(e, 'No se pudo agregar'))
    },
  })

  const quitar = useMutation({
    mutationFn: gestionApi.quitarWidget,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gestion', 'pizarras'] }),
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo quitar')),
  })

  const borrarPizarra = useMutation({
    mutationFn: gestionApi.borrarPizarra,
    onSuccess: () => {
      setSeleccionada(null)
      qc.invalidateQueries({ queryKey: ['gestion', 'pizarras'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo borrar')),
  })

  if (isLoading) return <Skeleton variant="rounded" height={340} />

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1.5} mb={2} flexWrap="wrap" useFlexGap>
        {pizarras?.length ? (
          <TextField
            select size="small" sx={{ minWidth: 240 }}
            value={actual?.id ?? ''} onChange={e => setSeleccionada(Number(e.target.value))}
          >
            {pizarras.map(p => (
              <MenuItem key={p.id} value={p.id}>
                {p.nombre}
                {p.compartida && (
                  <Chip label="compartida" size="small" variant="outlined"
                    sx={{ ml: 1, height: 16, fontSize: 8.5 }} />
                )}
              </MenuItem>
            ))}
          </TextField>
        ) : null}

        <Button size="small" startIcon={<Add />} onClick={() => setCreando(true)}
          sx={{ textTransform: 'none' }}>
          Nueva pizarra
        </Button>

        <Box sx={{ flex: 1 }} />

        {actual && (
          <>
            <Button size="small" variant="contained" startIcon={<Add />}
              onClick={() => setAgregando(true)} sx={{ textTransform: 'none' }}>
              Agregar recuadro
            </Button>
            <Button size="small" color="inherit"
              onClick={() => setBorrando(true)}
              sx={{ textTransform: 'none', color: PALETA.acero }}>
              Borrar
            </Button>
          </>
        )}
      </Stack>

      {!pizarras?.length && (
        <Alert severity="info" icon={<Dashboard />}>
          Todavía no hay pizarras. Cree una y agréguele recuadros: cada uno se
          apoya en el mismo lenguaje de filtros de la lista, y su cifra se puede
          abrir para ver qué hay detrás.
        </Alert>
      )}

      {actual && !actual.widgets.length && (
        <Alert severity="info">
          «{actual.nombre}» está vacía. Agréguele un recuadro.
        </Alert>
      )}

      {actual && !!actual.widgets.length && (
        <Box sx={{
          display: 'grid', gap: 2,
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(6, 1fr)', lg: 'repeat(12, 1fr)' },
        }}>
          {actual.widgets.map(w => (
            <Box key={w.id} sx={{
              gridColumn: {
                xs: 'span 1',
                sm: `span ${Math.min(w.ancho, 6)}`,
                lg: `span ${w.ancho}`,
              },
              minHeight: 132,
            }}>
              <Recuadro widget={w} onQuitar={id => quitar.mutate(id)}
                onAbrirLista={onAbrirLista} onAbrir={onAbrir} />
            </Box>
          ))}
        </Box>
      )}

      <DialogoConfirmar
        abierto={borrando} onCerrar={() => setBorrando(false)}
        titulo={`¿Borrar «${actual?.nombre ?? ''}»?`}
        mensaje="Se borra la pizarra con todos sus recuadros."
        advertencia="Las incidencias no se tocan: una pizarra solo mira, no guarda nada propio."
        textoBoton="Borrar" peligroso
        onAceptar={() => actual && borrarPizarra.mutate(actual.id)}
      />

      {/* ── Nueva pizarra ── */}
      <Dialog open={creando} onClose={() => setCreando(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Nueva pizarra</DialogTitle>
        <DialogContent>
          <TextField
            size="small" label="Nombre" fullWidth autoFocus sx={{ mt: 0.5 }}
            value={nombrePizarra} onChange={e => setNombrePizarra(e.target.value)}
            helperText={proyecto
              ? `Sus recuadros darán por supuesto el proyecto «${proyecto.nombre}».`
              : 'Sin proyecto: sus recuadros abarcan todo lo que usted puede ver.'}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreando(false)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button variant="contained" disabled={!nombrePizarra.trim()}
            onClick={() => crearPizarra.mutate()} sx={{ textTransform: 'none' }}>
            Crear
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Nuevo recuadro ── */}
      <Dialog open={agregando} onClose={() => setAgregando(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Agregar recuadro</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <TextField select size="small" label="Qué muestra" fullWidth value={tipo}
              onChange={e => setTipo(e.target.value)}>
              {(catalogo?.tipos ?? []).map(t => (
                <MenuItem key={t.clave} value={t.clave}>
                  <Box>
                    <Typography variant="body2">{t.nombre}</Typography>
                    <Typography variant="caption" sx={{ color: PALETA.acero }}>
                      {t.descripcion}
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </TextField>

            {tipo === 'AGRUPADO' && (
              <TextField select size="small" label="Agrupar por" fullWidth
                value={agruparPor} onChange={e => setAgruparPor(e.target.value)}>
                {(catalogo?.agrupaciones ?? []).map(a => (
                  <MenuItem key={a} value={a}>{a}</MenuItem>
                ))}
              </TextField>
            )}

            <TextField size="small" label="Título" fullWidth required
              value={titulo} onChange={e => setTitulo(e.target.value)} />

            <TextField
              size="small" label="Filtro" fullWidth
              value={expresion} onChange={e => setExpresion(e.target.value)}
              InputProps={{ sx: { fontFamily: 'monospace', fontSize: 13 } }}
              placeholder='categoria != "TERMINADO" Y prioridad = "ALTA"'
              helperText="El mismo lenguaje de la lista. Vacío = todo. Se comprueba al guardar."
            />

            <TextField select size="small" label="Ancho" fullWidth value={ancho}
              onChange={e => setAncho(Number(e.target.value))}>
              <MenuItem value={3}>Un cuarto</MenuItem>
              <MenuItem value={4}>Un tercio</MenuItem>
              <MenuItem value={6}>La mitad</MenuItem>
              <MenuItem value={12}>Todo el ancho</MenuItem>
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setAgregando(false)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button variant="contained" disabled={!titulo.trim() || agregar.isPending}
            onClick={() => agregar.mutate()} sx={{ textTransform: 'none' }}>
            Agregar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
