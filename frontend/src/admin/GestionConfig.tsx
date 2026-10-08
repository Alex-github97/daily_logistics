/**
 * La configuración: proyectos, flujos, estados, tipos y campos.
 *
 * Es la mitad que convierte el módulo en configurable de verdad. Sin ella,
 * cambiar cómo trabaja un equipo exigía entrar a la base a mano, y eso significa
 * que en la práctica nadie lo cambia.
 *
 * Va detrás de `gestion.configurar`, aparte de `gestion.trabajar`: cambiar un
 * workflow afecta a las incidencias que ya existen —una transición que
 * desaparece deja tarjetas sin salida— y eso no es mover una tarjeta.
 */
import { useEffect, useState } from 'react'
import {
  Box, Card, Stack, Typography, Button, IconButton, MenuItem, Chip, Skeleton, Alert, Tabs, Tab, Dialog, DialogTitle, DialogContent, DialogActions, Tooltip, Divider, Switch, FormControlLabel, Table, TableBody, TableCell, TableHead, TableRow,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { Add, Delete, DeleteOutline, Archive, Bolt, ArrowForward } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { DialogoTexto, DialogoConfirmar } from './GestionDialogos'
import {
  gestionApi, mensajeDeError,
  type ConfiguracionGestion, type Proyecto,
} from './api'

const COLOR_CATEGORIA: Record<string, string> = {
  SIN_CLASIFICAR: PALETA.acero,
  POR_HACER: PALETA.grafito,
  EN_CURSO: COLOR_MODULO,
  TERMINADO: ESTADO.exito,
}

const AYUDA_CATEGORIA: Record<string, string> = {
  SIN_CLASIFICAR: 'Fuera del backlog, del tablero y de las métricas de entrega.',
  POR_HACER: 'Pendiente. Cuenta en el backlog.',
  EN_CURSO: 'Trabajo activo. Es lo que cuenta para el tiempo de ciclo.',
  TERMINADO: 'Cerrada. Cuenta como completada en la velocidad.',
}

// ─── Proyectos ────────────────────────────────────────────────────────────────

function Proyectos({ config }: { config?: ConfiguracionGestion }) {
  const qc = useQueryClient()
  const [creando, setCreando] = useState(false)
  const [clave, setClave] = useState('')
  // Si la persona escribió la clave a mano, deja de proponerse: sobrescribir lo
  // que alguien acaba de teclear es de las cosas más molestas de un formulario.
  const [claveTocada, setClaveTocada] = useState(false)
  const [aEliminar, setAEliminar] = useState<Proyecto | null>(null)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [workflowId, setWorkflowId] = useState<number | ''>('')
  const [restringido, setRestringido] = useState(false)
  const [automatica, setAutomatica] = useState(false)

  const { data: proyectos } = useQuery({
    queryKey: ['gestion', 'proyectos', 'todos'],
    queryFn: () => gestionApi.proyectos(true),
  })

  // La clave se pide al servidor con lo que se lleva escrito del nombre. Va con
  // un respiro de medio segundo: pedirla en cada tecla son diez consultas para
  // escribir «Desarrollos» y ninguna aporta más que la última.
  useEffect(() => {
    if (claveTocada || !creando) return
    const nombreLimpio = nombre.trim()
    if (nombreLimpio.length < 2) { setClave(''); return }
    const id = setTimeout(() => {
      gestionApi.claveSugerida(nombreLimpio)
        .then(c => { if (!claveTocada) setClave(c) })
        .catch(() => { /* si falla, el servidor la deduce igual al crear */ })
    }, 500)
    return () => clearTimeout(id)
  }, [nombre, claveTocada, creando])

  const crear = useMutation({
    mutationFn: () => gestionApi.crearProyecto({
      // Vacía significa «dedúcela»: el servidor tiene la última palabra sobre
      // que sea única, y así no hay dos sitios decidiendo lo mismo.
      clave: clave.trim() || null,
      nombre, descripcion: descripcion || null,
      workflow_id: workflowId || null,
      restringido, incidencia_automatica: automatica,
    }),
    onSuccess: () => {
      toast.success('Proyecto creado')
      setCreando(false); setClave(''); setNombre(''); setDescripcion('')
      setClaveTocada(false)
      qc.invalidateQueries({ queryKey: ['gestion'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear')),
  })

  const eliminar = useMutation({
    mutationFn: ({ id, forzar }: { id: number; forzar: boolean }) =>
      gestionApi.eliminarProyecto(id, forzar),
    onSuccess: () => {
      toast.success('Proyecto eliminado')
      setAEliminar(null)
      qc.invalidateQueries({ queryKey: ['gestion'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo eliminar')),
  })

  const editar = useMutation({
    mutationFn: ({ id, cambios }: { id: number; cambios: Record<string, unknown> }) =>
      gestionApi.editarProyecto(id, cambios),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gestion'] }),
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo guardar')),
  })

  return (
    <Box>
      <Stack direction="row" alignItems="center" mb={1.5}>
        <Typography variant="caption" sx={{ color: PALETA.acero, flex: 1 }}>
          La clave del proyecto es el prefijo de las claves visibles: con «ERP» las
          incidencias se llaman ERP-1, ERP-2…
        </Typography>
        <Button size="small" variant="contained" startIcon={<Add />}
          onClick={() => setCreando(true)} sx={{ textTransform: 'none' }}>
          Nuevo proyecto
        </Button>
      </Stack>

      <Card variant="outlined" sx={{ borderRadius: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: PALETA.bruma }}>
              <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 80 }}>CLAVE</TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11 }}>NOMBRE</TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11 }}>FLUJO</TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 130 }} align="center">
                RECIBE SOPORTE
              </TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 110 }} align="center">
                RESTRINGIDO
              </TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 90 }} align="right">
                ABIERTAS
              </TableCell>
              <TableCell sx={{ width: 56 }} />
            </TableRow>
          </TableHead>
          <TableBody>
            {proyectos?.map(p => (
              <TableRow key={p.id} hover>
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                  {p.clave}
                </TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{
                    fontWeight: 600, opacity: p.archivado ? 0.5 : 1,
                  }}>
                    {p.icono} {p.nombre}
                    {p.archivado && (
                      <Chip label="archivado" size="small" variant="outlined"
                        sx={{ ml: 1, height: 16, fontSize: 8.5 }} />
                    )}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="caption">
                    {config?.workflows.find(w => w.id === p.workflow_id)?.nombre
                      ?? <em style={{ color: PALETA.acero }}>el que esté por defecto</em>}
                  </Typography>
                </TableCell>
                <TableCell align="center">
                  <Tooltip title="Cada solicitud del chat crea aquí su incidencia, sin clasificar. Solo un proyecto debería tenerlo.">
                    <Switch
                      size="small" checked={p.incidencia_automatica}
                      onChange={e => editar.mutate({
                        id: p.id, cambios: { incidencia_automatica: e.target.checked },
                      })}
                    />
                  </Tooltip>
                </TableCell>
                <TableCell align="center">
                  <Tooltip title="Solo lo ven sus miembros. Hay que agregar al menos uno antes de restringirlo.">
                    <Switch
                      size="small" checked={p.restringido}
                      onChange={e => editar.mutate({
                        id: p.id, cambios: { restringido: e.target.checked },
                      })}
                    />
                  </Tooltip>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="caption" sx={{ fontWeight: 700 }}>
                    {p.abiertas} / {p.total}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Eliminar el proyecto">
                    <IconButton size="small" onClick={() => setAEliminar(p)}
                                sx={{ color: PALETA.acero,
                                      '&:hover': { color: '#DC2626' } }}>
                      <DeleteOutline sx={{ fontSize: 17 }} />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Dialog open={!!aEliminar} onClose={() => setAEliminar(null)}
              maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          ¿Eliminar «{aEliminar?.nombre}»?
        </DialogTitle>
        <DialogContent>
          {/* Se dice exactamente qué se pierde. «¿Está seguro?» no es una
              pregunta que nadie pueda responder: la respuesta depende de si hay
              trabajo dentro, y eso lo sabe el sistema, no la persona. */}
          <Typography variant="body2" sx={{ color: PALETA.grafito }}>
            {(aEliminar?.total ?? 0) > 0
              ? `Tiene ${aEliminar?.total} incidencia(s) con su historial, sus
                 comentarios y sus adjuntos. Todo eso se pierde y no se puede
                 recuperar. Si solo quiere quitarlo de la vista, archívelo.`
              : 'No tiene incidencias, así que no se pierde nada.'}
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setAEliminar(null)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button
            variant="contained" color="error" disabled={eliminar.isPending}
            sx={{ textTransform: 'none' }}
            onClick={() => aEliminar && eliminar.mutate({
              id: aEliminar.id, forzar: (aEliminar.total ?? 0) > 0,
            })}
          >
            {(aEliminar?.total ?? 0) > 0
              ? `Eliminar y perder ${aEliminar?.total}` : 'Eliminar'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={creando} onClose={() => setCreando(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Nuevo proyecto</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            {/* El nombre va primero: es lo que la persona tiene en la
                cabeza. La clave se propone a partir de él y solo se toca si de
                verdad se quiere otra. */}
            <TextField size="small" label="Nombre" fullWidth required autoFocus
              value={nombre} onChange={e => setNombre(e.target.value)} />
            <TextField
              size="small" label="Clave" fullWidth
              value={clave} onChange={e => { setClaveTocada(true); setClave(e.target.value.toUpperCase()) }}
              inputProps={{ maxLength: 12 }}
              helperText={claveTocada
                ? 'Letras y números. Es el prefijo: ERP-1, ERP-2…'
                : `Se propone sola. Sus incidencias serán ${clave || 'XXX'}-1, ${clave || 'XXX'}-2…`}
            />
            <TextField size="small" label="Descripción" fullWidth multiline minRows={2}
              value={descripcion} onChange={e => setDescripcion(e.target.value)} />
            <TextField select size="small" label="Flujo" fullWidth value={workflowId}
              onChange={e => setWorkflowId(Number(e.target.value))}>
              <MenuItem value=""><em>El que esté por defecto</em></MenuItem>
              {config?.workflows.map(w => (
                <MenuItem key={w.id} value={w.id}>{w.nombre}</MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={<Switch size="small" checked={restringido}
                onChange={e => setRestringido(e.target.checked)} />}
              label={<Typography variant="body2">Solo para sus miembros</Typography>}
            />
            <FormControlLabel
              control={<Switch size="small" checked={automatica}
                onChange={e => setAutomatica(e.target.checked)} />}
              label={<Typography variant="body2">Recibe las solicitudes de soporte</Typography>}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreando(false)} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button variant="contained" disabled={!clave.trim() || !nombre.trim() || crear.isPending}
            onClick={() => crear.mutate()} sx={{ textTransform: 'none' }}>Crear</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Flujos ───────────────────────────────────────────────────────────────────

function Flujos({ config }: { config?: ConfiguracionGestion }) {
  const qc = useQueryClient()
  const [wfId, setWfId] = useState<number | null>(null)
  const [nuevoEstado, setNuevoEstado] = useState(false)
  const [nuevoFlujo, setNuevoFlujo] = useState(false)
  const [porBorrar, setPorBorrar] = useState<{ id: number; nombre: string } | null>(null)
  const [clave, setClave] = useState('')
  const [nombre, setNombre] = useState('')
  const [categoria, setCategoria] = useState('POR_HACER')
  const [wip, setWip] = useState('')

  const wf = config?.workflows.find(w => w.id === wfId) ?? config?.workflows[0] ?? null

  const refrescar = () => qc.invalidateQueries({ queryKey: ['gestion'] })

  const crearWf = useMutation({
    mutationFn: (n: string) => gestionApi.crearWorkflow({ nombre: n }),
    onSuccess: () => { toast.success('Flujo creado con sus estados de arranque'); refrescar() },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear')),
  })

  const crearEstado = useMutation({
    mutationFn: () => gestionApi.crearEstado(wf!.id, {
      clave: clave.toUpperCase(), nombre, categoria,
      orden: (wf?.estados.length ?? 0),
      limite_wip: wip ? Number(wip) : null,
    }),
    onSuccess: () => {
      setNuevoEstado(false); setClave(''); setNombre(''); setWip('')
      refrescar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear el estado')),
  })

  const editarEstado = useMutation({
    mutationFn: ({ id, cuerpo }: { id: number; cuerpo: Record<string, unknown> }) =>
      gestionApi.editarEstado(id, cuerpo),
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo guardar')),
  })

  const borrarEstado = useMutation({
    mutationFn: gestionApi.borrarEstado,
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo borrar')),
  })

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1.5} mb={2} flexWrap="wrap" useFlexGap>
        <TextField select size="small" sx={{ minWidth: 220 }} value={wf?.id ?? ''}
          onChange={e => setWfId(Number(e.target.value))}>
          {config?.workflows.map(w => (
            <MenuItem key={w.id} value={w.id}>
              {w.nombre}{w.por_defecto ? ' · por defecto' : ''}
            </MenuItem>
          ))}
        </TextField>
        <Button size="small" startIcon={<Add />} sx={{ textTransform: 'none' }}
          onClick={() => setNuevoFlujo(true)}>
          Nuevo flujo
        </Button>
        <Box sx={{ flex: 1 }} />
        {wf && (
          <Button size="small" variant="contained" startIcon={<Add />}
            onClick={() => setNuevoEstado(true)} sx={{ textTransform: 'none' }}>
            Agregar estado
          </Button>
        )}
      </Stack>

      {!wf && <Alert severity="info">No hay flujos. Cree uno.</Alert>}

      {wf && (
        <>
          <Typography variant="caption" sx={{ color: PALETA.acero, display: 'block', mb: 1.5 }}>
            La categoría no es una etiqueta: de ella depende si el estado cuenta
            como trabajo en curso o como terminado en el tiempo de ciclo, la
            velocidad y el backlog.
          </Typography>

          <Stack direction="row" spacing={1} sx={{ overflowX: 'auto', pb: 1 }}>
            {wf.estados.map((e, i) => (
              <Stack key={e.id} direction="row" alignItems="center" spacing={1}>
                <Card variant="outlined" sx={{
                  borderRadius: 2, p: 1.5, minWidth: 190,
                  borderTop: `3px solid ${COLOR_CATEGORIA[e.categoria] ?? PALETA.acero}`,
                }}>
                  <Stack direction="row" alignItems="center" spacing={0.5}>
                    <Typography variant="body2" sx={{ fontWeight: 700, flex: 1 }}>
                      {e.nombre}
                    </Typography>
                    {e.inicial && (
                      <Tooltip title="Acá entran las incidencias nuevas">
                        <Bolt sx={{ fontSize: 14, color: ESTADO.alerta }} />
                      </Tooltip>
                    )}
                    <IconButton size="small"
                      onClick={() => setPorBorrar({ id: e.id, nombre: e.nombre })}>
                      <Delete sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Stack>

                  <Typography variant="caption" sx={{
                    fontFamily: 'monospace', fontSize: 9.5, color: PALETA.acero,
                    display: 'block',
                  }}>
                    {e.clave}
                  </Typography>

                  <TextField
                    select size="small" fullWidth sx={{ mt: 1 }} value={e.categoria}
                    onChange={ev => editarEstado.mutate({
                      id: e.id,
                      cuerpo: { ...e, categoria: ev.target.value },
                    })}
                  >
                    {(config?.vocabulario.categorias_estado ?? []).map(c => (
                      <MenuItem key={c} value={c}>
                        <Tooltip title={AYUDA_CATEGORIA[c] ?? ''} placement="right">
                          <span>{c}</span>
                        </Tooltip>
                      </MenuItem>
                    ))}
                  </TextField>

                  <TextField
                    size="small" fullWidth type="number" sx={{ mt: 1 }}
                    label="Límite en curso" defaultValue={e.limite_wip ?? ''}
                    onBlur={ev => {
                      const v = ev.target.value ? Number(ev.target.value) : null
                      if (v !== (e.limite_wip ?? null)) {
                        editarEstado.mutate({ id: e.id, cuerpo: { ...e, limite_wip: v } })
                      }
                    }}
                    helperText="Vacío = sin límite"
                  />
                </Card>
                {i < wf.estados.length - 1 && (
                  <ArrowForward sx={{ fontSize: 16, color: PALETA.niebla }} />
                )}
              </Stack>
            ))}
          </Stack>
        </>
      )}

      <DialogoTexto
        abierto={nuevoFlujo} onCerrar={() => setNuevoFlujo(false)}
        titulo="Nuevo flujo" etiqueta="Nombre del flujo"
        ayuda="Nace con Por hacer, En curso y Hecho, y sus transiciones. Se ajusta después."
        onAceptar={n => crearWf.mutate(n)}
      />

      <DialogoConfirmar
        abierto={!!porBorrar} onCerrar={() => setPorBorrar(null)}
        titulo={`¿Borrar «${porBorrar?.nombre ?? ''}»?`}
        mensaje="El estado desaparece del flujo, junto con las transiciones que entran o salen de él."
        advertencia="Si hay incidencias en ese estado, el servidor lo impide: muévalas primero."
        textoBoton="Borrar" peligroso
        onAceptar={() => porBorrar && borrarEstado.mutate(porBorrar.id)}
      />

      <Dialog open={nuevoEstado} onClose={() => setNuevoEstado(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Agregar estado</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <TextField size="small" label="Clave" fullWidth autoFocus required
              value={clave} onChange={e => setClave(e.target.value.toUpperCase())} />
            <TextField size="small" label="Nombre" fullWidth required
              value={nombre} onChange={e => setNombre(e.target.value)} />
            <TextField select size="small" label="Categoría" fullWidth value={categoria}
              onChange={e => setCategoria(e.target.value)}
              helperText={AYUDA_CATEGORIA[categoria]}>
              {(config?.vocabulario.categorias_estado ?? []).map(c => (
                <MenuItem key={c} value={c}>{c}</MenuItem>
              ))}
            </TextField>
            <TextField size="small" type="number" label="Límite de trabajo en curso"
              fullWidth value={wip} onChange={e => setWip(e.target.value)}
              helperText="Lo hace cumplir el servidor. Vacío = sin límite." />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setNuevoEstado(false)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button variant="contained" disabled={!clave.trim() || !nombre.trim()}
            onClick={() => crearEstado.mutate()} sx={{ textTransform: 'none' }}>
            Agregar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Campos ───────────────────────────────────────────────────────────────────

function Campos({ config }: { config?: ConfiguracionGestion }) {
  const qc = useQueryClient()
  const [creando, setCreando] = useState(false)
  const [clave, setClave] = useState('')
  const [nombre, setNombre] = useState('')
  const [tipo, setTipo] = useState('TEXTO')
  const [ayuda, setAyuda] = useState('')
  const [filtrable, setFiltrable] = useState(true)
  const [opciones, setOpciones] = useState('')

  const refrescar = () => qc.invalidateQueries({ queryKey: ['gestion'] })

  const crear = useMutation({
    mutationFn: () => gestionApi.crearCampo({
      clave, nombre, tipo, ayuda: ayuda || null, filtrable, ordenable: filtrable,
      opciones: opciones.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
        const [valor, etiqueta] = l.split('|').map(s => s.trim())
        return { valor: valor.toUpperCase(), etiqueta: etiqueta || valor }
      }),
    }),
    onSuccess: c => {
      toast.success(`Campo «${c.nombre}» creado. Ya se puede usar en los filtros.`)
      setCreando(false); setClave(''); setNombre(''); setAyuda(''); setOpciones('')
      refrescar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear el campo')),
  })

  const editar = useMutation({
    mutationFn: ({ id, cuerpo }: { id: number; cuerpo: Record<string, unknown> }) =>
      gestionApi.editarCampo(id, cuerpo),
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo guardar')),
  })

  const archivar = useMutation({
    mutationFn: gestionApi.archivarCampo,
    onSuccess: refrescar,
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo archivar')),
  })

  const esLista = tipo === 'LISTA' || tipo === 'LISTA_MULTIPLE'

  return (
    <Box>
      <Stack direction="row" alignItems="center" mb={1.5}>
        <Typography variant="caption" sx={{ color: PALETA.acero, flex: 1, maxWidth: 620 }}>
          Marcar un campo como filtrable crea su índice; desmarcarlo lo borra. Así
          se decide qué se puede consultar rápido sin escribir SQL, y no se paga un
          índice por cada campo que nadie filtra.
        </Typography>
        <Button size="small" variant="contained" startIcon={<Add />}
          onClick={() => setCreando(true)} sx={{ textTransform: 'none' }}>
          Nuevo campo
        </Button>
      </Stack>

      <Card variant="outlined" sx={{ borderRadius: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: PALETA.bruma }}>
              <TableCell sx={{ fontWeight: 800, fontSize: 11 }}>CLAVE</TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11 }}>NOMBRE</TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 130 }}>TIPO</TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 100 }} align="center">
                FILTRABLE
              </TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 11, width: 60 }} />
            </TableRow>
          </TableHead>
          <TableBody>
            {config?.campos.map(c => (
              <TableRow key={c.clave} hover>
                <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{c.clave}</TableCell>
                <TableCell>
                  <Typography variant="body2">{c.nombre}</Typography>
                  {c.ayuda && (
                    <Typography variant="caption" sx={{ color: PALETA.acero }}>
                      {c.ayuda}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Chip label={c.tipo} size="small"
                    sx={{ height: 18, fontSize: 9.5, bgcolor: PALETA.niebla }} />
                </TableCell>
                <TableCell align="center">
                  <Chip
                    label={c.filtrable ? 'sí' : 'no'} size="small"
                    sx={{
                      height: 18, fontSize: 9.5, fontWeight: 700,
                      bgcolor: c.filtrable ? `${ESTADO.exito}1F` : PALETA.niebla,
                      color: c.filtrable ? ESTADO.exito : PALETA.acero,
                    }}
                  />
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Archivar: los valores ya escritos se quedan">
                    <span>
                      <IconButton size="small" disabled>
                        <Archive sx={{ fontSize: 15 }} />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {!config?.campos.length && (
              <TableRow>
                <TableCell colSpan={5} sx={{ py: 3, textAlign: 'center' }}>
                  <Typography variant="body2" sx={{ color: PALETA.acero }}>
                    No hay campos configurables todavía.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <Dialog open={creando} onClose={() => setCreando(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Nuevo campo</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <TextField
              size="small" label="Clave" fullWidth autoFocus required
              value={clave}
              onChange={e => setClave(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))}
              helperText="Con esto se nombra el campo en un filtro. Minúsculas y guion bajo."
            />
            <TextField size="small" label="Nombre visible" fullWidth required
              value={nombre} onChange={e => setNombre(e.target.value)} />
            <TextField select size="small" label="Tipo" fullWidth value={tipo}
              onChange={e => setTipo(e.target.value)}>
              {(config?.vocabulario.tipos_campo ?? []).map(t => (
                <MenuItem key={t} value={t}>{t}</MenuItem>
              ))}
            </TextField>

            {esLista && (
              <TextField
                size="small" label="Opciones" fullWidth multiline minRows={3}
                value={opciones} onChange={e => setOpciones(e.target.value)}
                placeholder={'S1 | Bloqueante\nS2 | Grave'}
                helperText="Una por línea. «clave | etiqueta», o solo la clave."
              />
            )}

            <TextField size="small" label="Ayuda" fullWidth
              value={ayuda} onChange={e => setAyuda(e.target.value)}
              helperText="Se muestra bajo el campo en el formulario." />

            <FormControlLabel
              control={<Switch size="small" checked={filtrable}
                onChange={e => setFiltrable(e.target.checked)} />}
              label={
                <Typography variant="body2">
                  Se puede filtrar y ordenar por él
                </Typography>
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreando(false)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button
            variant="contained" disabled={!clave.trim() || !nombre.trim() || crear.isPending}
            onClick={() => crear.mutate()} sx={{ textTransform: 'none' }}
          >
            Crear
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── Tipos ────────────────────────────────────────────────────────────────────

function Tipos({ config }: { config?: ConfiguracionGestion }) {
  const qc = useQueryClient()
  const [creando, setCreando] = useState(false)
  const [clave, setClave] = useState('')
  const [nombre, setNombre] = useState('')
  const [icono, setIcono] = useState('')
  const [nivel, setNivel] = useState('NORMAL')

  const crear = useMutation({
    mutationFn: () => gestionApi.crearTipo({
      clave: clave.toUpperCase(), nombre, icono: icono || null, nivel,
      orden: (config?.tipos.length ?? 0),
    }),
    onSuccess: () => {
      toast.success('Tipo creado')
      setCreando(false); setClave(''); setNombre(''); setIcono('')
      qc.invalidateQueries({ queryKey: ['gestion'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo crear')),
  })

  return (
    <Box>
      <Stack direction="row" alignItems="center" mb={1.5}>
        <Typography variant="caption" sx={{ color: PALETA.acero, flex: 1, maxWidth: 620 }}>
          El nivel decide la jerarquía: una subtarea cuelga de una normal, y una
          normal de una épica. El servidor lo hace cumplir.
        </Typography>
        <Button size="small" variant="contained" startIcon={<Add />}
          onClick={() => setCreando(true)} sx={{ textTransform: 'none' }}>
          Nuevo tipo
        </Button>
      </Stack>

      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        {config?.tipos.map(t => (
          <Card key={t.id} variant="outlined" sx={{
            borderRadius: 2, p: 1.5, minWidth: 180,
            borderLeft: `3px solid ${t.color || PALETA.niebla}`,
          }}>
            <Stack direction="row" alignItems="center" spacing={0.75}>
              <Typography variant="h6">{t.icono}</Typography>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>{t.nombre}</Typography>
                <Typography variant="caption" sx={{
                  fontFamily: 'monospace', fontSize: 9.5, color: PALETA.acero,
                }}>
                  {t.clave} · {t.nivel}
                </Typography>
              </Box>
            </Stack>
          </Card>
        ))}
      </Stack>

      <Dialog open={creando} onClose={() => setCreando(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Nuevo tipo de incidencia</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <TextField size="small" label="Clave" fullWidth autoFocus required
              value={clave} onChange={e => setClave(e.target.value.toUpperCase())} />
            <TextField size="small" label="Nombre" fullWidth required
              value={nombre} onChange={e => setNombre(e.target.value)} />
            <TextField size="small" label="Icono" fullWidth value={icono}
              onChange={e => setIcono(e.target.value)}
              helperText="Un carácter o emoji: ● ▲ ■ ◆" />
            <TextField select size="small" label="Nivel" fullWidth value={nivel}
              onChange={e => setNivel(e.target.value)}>
              {(config?.vocabulario.niveles ?? []).map(n => (
                <MenuItem key={n} value={n}>{n}</MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreando(false)} sx={{ textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button variant="contained" disabled={!clave.trim() || !nombre.trim()}
            onClick={() => crear.mutate()} sx={{ textTransform: 'none' }}>
            Crear
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// ─── La pantalla ──────────────────────────────────────────────────────────────

export default function GestionConfig() {
  const [pestana, setPestana] = useState(0)

  const { data: config, isLoading } = useQuery({
    queryKey: ['gestion', 'config', null],
    queryFn: () => gestionApi.configuracion(),
  })

  if (isLoading) return <Skeleton variant="rounded" height={340} />

  return (
    <Box>
      <Tabs value={pestana} onChange={(_, v) => setPestana(v)}
        sx={{ mb: 2.5, borderBottom: `1px solid ${PALETA.niebla}`,
              '& .MuiTab-root': { textTransform: 'none', fontWeight: 700, minHeight: 40 } }}>
        <Tab label="Proyectos" />
        <Tab label="Flujos y estados" />
        <Tab label="Tipos" />
        <Tab label="Campos" />
      </Tabs>

      {pestana === 0 && <Proyectos config={config} />}
      {pestana === 1 && <Flujos config={config} />}
      {pestana === 2 && <Tipos config={config} />}
      {pestana === 3 && <Campos config={config} />}
    </Box>
  )
}
