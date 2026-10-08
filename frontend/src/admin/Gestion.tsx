/**
 * Proyectos e incidencias.
 *
 * El trabajo interno del equipo: lo que llega por el chat de soporte y se decide
 * hacer, más lo que nadie pidió pero hay que hacer igual.
 *
 * La lista se pagina por cursor y no por número de página. Con una lista que
 * cambia mientras se recorre, «página 3» se salta o repite filas; el cursor
 * apunta a una posición concreta del orden y sigue siendo correcto aunque entren
 * incidencias nuevas mientras alguien baja.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Box, Stack, Typography, Button, Chip, Card, Table, TableBody, TableCell, TableHead, TableRow, Skeleton, Alert, Tabs, Tab, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Tooltip,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  Add, ViewList, ViewKanban, FolderOpen, Refresh, ArrowDownward,
  Timeline, Speed, Dashboard, Settings,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  gestionApi, mensajeDeError,
  type Incidencia, type Proyecto, type ConfiguracionGestion,
} from './api'
import { BarraDeFiltro } from './GestionFiltro'
import GestionDetalle from './GestionDetalle'
import GestionTablero from './GestionTablero'
import GestionGantt from './GestionGantt'
import GestionSprints from './GestionSprints'
import GestionPizarras from './GestionPizarras'
import GestionConfig from './GestionConfig'
import GestionFormulario from './GestionFormulario'
import { aFecha } from '@/utils/fechas'

const COLOR_CATEGORIA: Record<string, string> = {
  SIN_CLASIFICAR: PALETA.acero,
  POR_HACER: PALETA.grafito,
  EN_CURSO: COLOR_MODULO,
  TERMINADO: ESTADO.exito,
}

function cuando(iso?: string | null): string {
  if (!iso) return '—'
  return aFecha(iso).toLocaleString('es-CO', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

// ─── Lista ────────────────────────────────────────────────────────────────────

function Lista({
  proyecto, expresion, onAbrir,
}: {
  proyecto: Proyecto
  expresion: string
  onAbrir: (id: number) => void
}) {
  const [paginas, setPaginas] = useState<Incidencia[][]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hayMas, setHayMas] = useState(false)
  const [total, setTotal] = useState<number | null>(null)
  const [cargando, setCargando] = useState(false)

  // El filtro siempre lleva el proyecto: la barra escribe condiciones sobre lo
  // que ya está acotado, no sobre toda la base.
  const consulta = useMemo(() => {
    const base = `proyecto = "${proyecto.clave}"`
    return expresion.trim() ? `${base} Y ${expresion.trim()}` : base
  }, [proyecto.clave, expresion])

  async function traer(desde: string | null) {
    setCargando(true)
    try {
      const p = await gestionApi.buscar({
        expresion: consulta, limite: 25, cursor: desde, con_total: desde == null,
      })
      setPaginas(anteriores => (desde == null ? [p.resultados] : [...anteriores, p.resultados]))
      setCursor(p.siguiente ?? null)
      setHayMas(!!p.siguiente)
      if (desde == null) setTotal(p.total ?? null)
    } catch (e: any) {
      toast.error(mensajeDeError(e, 'No se pudo consultar'))
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => { traer(null) }, [consulta])

  const filas = paginas.flat()

  if (cargando && !filas.length) {
    return <Skeleton variant="rounded" height={280} />
  }

  return (
    <Card variant="outlined" sx={{ borderRadius: 2 }}>
      <Table size="small">
        <TableHead>
          <TableRow sx={{ bgcolor: PALETA.bruma }}>
            <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 92 }}>CLAVE</TableCell>
            <TableCell sx={{ fontWeight: 800, fontSize: 11 }}>TÍTULO</TableCell>
            <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 130 }}>ESTADO</TableCell>
            <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 110 }}>PRIORIDAD</TableCell>
            <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 130 }}>RESPONSABLE</TableCell>
            <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 60 }} align="right">PT</TableCell>
            <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 120 }}>ACTUALIZADA</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {filas.map(t => (
            <TableRow
              key={t.id} hover onClick={() => onAbrir(t.id)}
              sx={{ cursor: 'pointer' }}
            >
              <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                {t.clave}
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={0.75} alignItems="center">
                  {t.icono && <span>{t.icono}</span>}
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                    {t.resumen}
                  </Typography>
                  {t.ticket_id && (
                    <Chip label="soporte" size="small" variant="outlined"
                      sx={{ height: 16, fontSize: 8.5 }} />
                  )}
                </Stack>
              </TableCell>
              <TableCell>
                <Chip label={t.estado ?? '—'} size="small" sx={{
                  height: 20, fontSize: 10.5, fontWeight: 700,
                  bgcolor: `${COLOR_CATEGORIA[t.categoria ?? ''] ?? PALETA.acero}1F`,
                  color: COLOR_CATEGORIA[t.categoria ?? ''] ?? PALETA.acero,
                }} />
              </TableCell>
              <TableCell>
                <Typography variant="caption" sx={{ color: t.color_prioridad || 'inherit', fontWeight: 600 }}>
                  {t.prioridad ?? '—'}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="caption" sx={{ color: t.asignado ? 'inherit' : PALETA.acero }}>
                  {t.asignado ?? 'sin asignar'}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography variant="caption" sx={{
                  fontWeight: 700, color: t.puntos == null ? PALETA.acero : 'inherit',
                }}>
                  {t.puntos ?? '—'}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="caption" sx={{ color: PALETA.acero }}>
                  {cuando(t.actualizado)}
                </Typography>
              </TableCell>
            </TableRow>
          ))}
          {!filas.length && !cargando && (
            <TableRow>
              <TableCell colSpan={7} sx={{ py: 4, textAlign: 'center' }}>
                <Typography variant="body2" sx={{ color: PALETA.acero }}>
                  No hay incidencias que cumplan el filtro.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Stack direction="row" alignItems="center" spacing={1}
        sx={{ px: 2, py: 1, borderTop: `1px solid ${PALETA.niebla}` }}>
        <Typography variant="caption" sx={{ color: PALETA.acero }}>
          {filas.length}{total != null ? ` de ${total}` : ''}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {hayMas && (
          <Button size="small" startIcon={<ArrowDownward sx={{ fontSize: 14 }} />}
            disabled={cargando} onClick={() => traer(cursor)}
            sx={{ textTransform: 'none' }}>
            Cargar más
          </Button>
        )}
      </Stack>
    </Card>
  )
}

// ─── La pantalla ──────────────────────────────────────────────────────────────

export default function Gestion() {
  const qc = useQueryClient()
  const [proyectoId, setProyectoId] = useState<number | null>(null)
  const [vista, setVista] = useState(0)
  const [expresion, setExpresion] = useState('')
  const [aplicada, setAplicada] = useState('')
  const [abierta, setAbierta] = useState<number | null>(null)
  const [creando, setCreando] = useState(false)

  const { data: proyectos, isLoading, error } = useQuery({
    queryKey: ['gestion', 'proyectos'],
    queryFn: () => gestionApi.proyectos(),
  })

  useEffect(() => {
    if (proyectos?.length && proyectoId == null) setProyectoId(proyectos[0].id)
  }, [proyectos, proyectoId])

  const proyecto = proyectos?.find(p => p.id === proyectoId) ?? null

  const { data: config } = useQuery({
    queryKey: ['gestion', 'config', proyectoId],
    queryFn: () => gestionApi.configuracion(proyectoId!),
    enabled: proyectoId != null,
    staleTime: 5 * 60_000,
  })

  if (isLoading) return <Skeleton variant="rounded" height={400} />

  if (error) {
    return (
      <Alert severity="error">
        {mensajeDeError(error, 'No se pudieron cargar los proyectos')}
      </Alert>
    )
  }

  if (!proyectos?.length) {
    return (
      <Alert severity="info" icon={<FolderOpen />}>
        Todavía no hay ningún proyecto. El primero se crea con el flujo estándar
        que ya trae la plataforma.
      </Alert>
    )
  }

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={2} mb={2} flexWrap="wrap" useFlexGap>
        <TextField
          select size="small" value={proyectoId ?? ''} sx={{ minWidth: 260 }}
          onChange={e => { setProyectoId(Number(e.target.value)); setExpresion(''); setAplicada('') }}
        >
          {proyectos.map(p => (
            <MenuItem key={p.id} value={p.id}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <span>{p.icono}</span>
                <span>{p.nombre}</span>
                <Chip label={p.abiertas} size="small" sx={{
                  height: 17, fontSize: 9.5, fontWeight: 800, bgcolor: PALETA.niebla,
                }} />
                {p.restringido && (
                  <Chip label="restringido" size="small" variant="outlined"
                    sx={{ height: 17, fontSize: 8.5 }} />
                )}
              </Stack>
            </MenuItem>
          ))}
        </TextField>

        <Tabs value={vista} onChange={(_, v) => setVista(v)}
          sx={{ minHeight: 34, '& .MuiTab-root': { minHeight: 34, textTransform: 'none' } }}>
          <Tab icon={<ViewList sx={{ fontSize: 16 }} />} iconPosition="start" label="Lista" />
          <Tab icon={<ViewKanban sx={{ fontSize: 16 }} />} iconPosition="start" label="Tablero" />
          <Tab icon={<Speed sx={{ fontSize: 16 }} />} iconPosition="start" label="Sprints" />
          <Tab icon={<Timeline sx={{ fontSize: 16 }} />} iconPosition="start" label="Gantt" />
          <Tab icon={<Dashboard sx={{ fontSize: 16 }} />} iconPosition="start" label="Pizarras" />
          <Tab icon={<Settings sx={{ fontSize: 16 }} />} iconPosition="start" label="Configuración" />
        </Tabs>

        <Box sx={{ flex: 1 }} />

        <Tooltip title="Volver a consultar">
          <IconButton size="small" onClick={() => qc.invalidateQueries({ queryKey: ['gestion'] })}>
            <Refresh fontSize="small" />
          </IconButton>
        </Tooltip>
        {vista < 4 && (
          <Button size="small" variant="contained" startIcon={<Add />}
            disabled={!proyecto} onClick={() => setCreando(true)}
            sx={{ textTransform: 'none' }}>
            Nueva incidencia
          </Button>
        )}
      </Stack>

      {proyecto?.descripcion && (
        <Typography variant="caption" sx={{ color: PALETA.acero, display: 'block', mb: 2 }}>
          {proyecto.descripcion}
        </Typography>
      )}

      {vista === 0 && (
        <>
          <Box sx={{ mb: 1 }}>
            <BarraDeFiltro
              expresion={expresion} onCambio={setExpresion}
              onBuscar={() => setAplicada(expresion)}
            />
          </Box>
          {proyecto && (
            <Lista proyecto={proyecto} expresion={aplicada} onAbrir={setAbierta} />
          )}
        </>
      )}

      {vista === 1 && proyecto && (
        <GestionTablero proyecto={proyecto} onAbrir={setAbierta} />
      )}

      {vista === 2 && proyecto && (
        <GestionSprints proyecto={proyecto} onAbrir={setAbierta} />
      )}

      {vista === 3 && proyecto && (
        <GestionGantt proyecto={proyecto} onAbrir={setAbierta} />
      )}

      {vista === 4 && (
        <GestionPizarras
          proyecto={proyecto} onAbrir={setAbierta}
          onAbrirLista={expresion => {
            // Cualquier cifra de una pizarra se puede abrir como lista: un
            // numero que no se puede desglosar es un numero en el que nadie
            // confia, y termina ignorandose.
            setExpresion(expresion); setAplicada(expresion); setVista(0)
          }}
        />
      )}

      {vista === 5 && <GestionConfig />}

      {proyecto && (
        <GestionFormulario
          abierto={creando} proyecto={proyecto} proyectos={proyectos}
          onCerrar={() => setCreando(false)} onGuardada={setAbierta}
        />
      )}

      <GestionDetalle incidenciaId={abierta} onCerrar={() => setAbierta(null)} />
    </Box>
  )
}
