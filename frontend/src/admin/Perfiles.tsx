/**
 * Los perfiles de una empresa: qué pantallas ve cada persona.
 *
 * Es distinto de los módulos, y conviene no confundirlos. Los módulos dicen qué
 * **contrató** la empresa; el perfil dice qué puede hacer **cada quien** dentro
 * de lo contratado. Los dos tienen que permitirlo para que alguien entre: si el
 * módulo no está contratado da igual el perfil, y si el perfil no lo permite da
 * igual que esté contratado.
 *
 * Las casillas no están escritas acá sino que las sirve el servidor. Tenerlas
 * escritas en la pantalla fue justamente lo que las dejó desincronizadas: había
 * módulos que el portal exigía para dejar entrar y que el servidor descartaba
 * al guardar, así que un perfil con ellos no funcionaba y no había forma de
 * saber por qué.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Box, Card, Typography, Button, Stack, Chip, IconButton, Tooltip, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, Skeleton,
  Checkbox, FormControlLabel, Divider, Table, TableBody, TableCell, TableHead,
  TableRow,
} from '@mui/material'
import {
  Add, Edit, DeleteOutline, Shield, Lock, DoneAll, RemoveDone,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  consolaApi, mensajeDeError,
  type Empresa, type PerfilDeEmpresa, type PermisoDePerfil,
} from './api'

/* ── El editor de un perfil ────────────────────────────────────────────────── */

const VACIO = { nombre: '', descripcion: '', color: '#6366f1' }

function DialogoPerfil({
  empresa, perfil, abierto, permisos, onCerrar,
}: {
  empresa: Empresa
  /** Vacío = uno nuevo. */
  perfil: PerfilDeEmpresa | null
  abierto: boolean
  permisos: PermisoDePerfil[]
  onCerrar: () => void
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ ...VACIO })
  const [marcados, setMarcados] = useState<Record<string, boolean>>({})

  // Se rellena al abrir y no al montar: la fila puede cambiar por debajo
  // mientras el diálogo está cerrado.
  useEffect(() => {
    if (!abierto) return
    setForm(perfil
      ? {
          nombre: perfil.nombre,
          descripcion: perfil.descripcion ?? '',
          color: perfil.color ?? '#6366f1',
        }
      : { ...VACIO })
    setMarcados(perfil?.permisos ?? {})
  }, [abierto, perfil])

  const porGrupo = useMemo(() => {
    const g: Record<string, PermisoDePerfil[]> = {}
    for (const p of permisos) (g[p.grupo] ??= []).push(p)
    return g
  }, [permisos])

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        nombre: form.nombre.trim(),
        descripcion: form.descripcion.trim() || null,
        color: form.color,
        permisos: marcados,
      }
      return perfil
        ? consolaApi.editarPerfil(empresa.id, perfil.id, cuerpo)
        : consolaApi.crearPerfil(empresa.id, cuerpo)
    },
    onSuccess: () => {
      toast.success(perfil ? 'Perfil actualizado' : 'Perfil creado')
      qc.invalidateQueries({ queryKey: ['perfiles', empresa.id] })
      qc.invalidateQueries({ queryKey: ['usuarios', empresa.id] })
      onCerrar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  // El perfil de administrador se puede renombrar y describir, pero sus
  // permisos no se tocan: es el único que puede volver a repartirlos dentro de
  // la empresa, y dejarlo corto la deja sin quien administre a su propia gente.
  const esAdministrador = perfil?.nombre === 'ADMINISTRADOR'
  const total = permisos.filter(p => marcados[p.clave]).length

  const alternarGrupo = (grupo: string, valor: boolean) =>
    setMarcados(m => {
      const nuevo = { ...m }
      for (const p of porGrupo[grupo]) nuevo[p.clave] = valor
      return nuevo
    })

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="md" fullWidth>
      <DialogTitle sx={{ fontWeight: 800, fontSize: 17 }}>
        {perfil ? `Perfil ${perfil.nombre}` : 'Nuevo perfil'}
        <Typography variant="caption" display="block" color="text.secondary">
          {empresa.nombre} · {esAdministrador
            ? 'acceso total a lo que la empresa tenga contratado'
            : `${total} de ${permisos.length} pantallas habilitadas`}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} mb={2}>
          <TextField
            size="small" label="Nombre *" fullWidth value={form.nombre}
            onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
            helperText="Se guarda en mayúsculas, como los demás perfiles"
          />
          <TextField
            size="small" label="Descripción" fullWidth value={form.descripcion}
            onChange={e => setForm(f => ({ ...f, descripcion: e.target.value }))}
          />
          <TextField
            size="small" label="Color" type="color" sx={{ width: 90 }}
            value={form.color}
            onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
          />
        </Stack>

        {esAdministrador && (
          <Alert severity="info" icon={<Lock fontSize="small" />}
            sx={{ mb: 2, py: 0.4, fontSize: 12.5 }}>
            El portal deja pasar a quien tenga este perfil sin mirar las
            casillas: un administrador ve todo lo que la empresa tenga
            contratado, marque lo que marque acá. Por eso están bloqueadas —
            recortarlas no cambiaría nada y sí haría creer que sí—. El nombre y
            la descripción sí se pueden cambiar. Para dar acceso limitado, cree
            otro perfil.
          </Alert>
        )}

        {Object.entries(porGrupo).map(([grupo, lista]) => {
          const todos = lista.every(p => marcados[p.clave])
          return (
            <Box key={grupo} mb={2}>
              <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
                <Typography sx={{
                  fontSize: 11, fontWeight: 800, letterSpacing: '.06em',
                  color: PALETA.grafito, textTransform: 'uppercase',
                }}>
                  {grupo}
                </Typography>
                <Chip size="small" label={`${lista.filter(p => marcados[p.clave]).length}/${lista.length}`}
                  sx={{ height: 17, fontSize: 10, fontWeight: 700 }} />
                <Box sx={{ flex: 1 }} />
                <Tooltip title={todos ? 'Quitar todo el grupo' : 'Marcar todo el grupo'}>
                  <span>
                    <IconButton size="small" disabled={esAdministrador}
                      onClick={() => alternarGrupo(grupo, !todos)}>
                      {todos ? <RemoveDone sx={{ fontSize: 16 }} />
                             : <DoneAll sx={{ fontSize: 16 }} />}
                    </IconButton>
                  </span>
                </Tooltip>
              </Stack>
              <Box sx={{
                display: 'grid', gap: 0.25,
                gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr' },
              }}>
                {lista.map(p => (
                  <FormControlLabel
                    key={p.clave}
                    control={
                      <Checkbox
                        size="small" disabled={esAdministrador}
                        checked={Boolean(marcados[p.clave])}
                        onChange={e => setMarcados(m => ({ ...m, [p.clave]: e.target.checked }))}
                      />
                    }
                    label={<Typography sx={{ fontSize: 12.5 }}>{p.nombre}</Typography>}
                  />
                ))}
              </Box>
              <Divider sx={{ mt: 1 }} />
            </Box>
          )
        })}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" sx={{ textTransform: 'none', fontWeight: 700 }}
          disabled={!form.nombre.trim() || guardar.isPending}
          onClick={() => guardar.mutate()}
        >
          {perfil ? 'Guardar cambios' : 'Crear perfil'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

/* ── La pestaña ────────────────────────────────────────────────────────────── */

export default function Perfiles({ empresa }: { empresa: Empresa }) {
  const qc = useQueryClient()
  const [editando, setEditando] = useState<PerfilDeEmpresa | null>(null)
  const [abierto, setAbierto] = useState(false)

  const { data: permisos = [] } = useQuery({
    queryKey: ['permisos-perfil'],
    queryFn: () => consolaApi.permisosDePerfil(),
    // La lista de casillas no cambia de una empresa a otra ni cada minuto.
    staleTime: 10 * 60 * 1000,
  })

  const { data: perfiles = [], isLoading } = useQuery({
    queryKey: ['perfiles', empresa.id],
    queryFn: () => consolaApi.perfiles(empresa.id),
  })

  const borrar = useMutation({
    mutationFn: (id: number) => consolaApi.borrarPerfil(empresa.id, id),
    onSuccess: () => {
      toast.success('Perfil eliminado')
      qc.invalidateQueries({ queryKey: ['perfiles', empresa.id] })
    },
    // El servidor impide borrar los del sistema y los que tienen gente adentro;
    // el mensaje dice cuál de las dos cosas pasó y qué hacer antes.
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const abrir = (p: PerfilDeEmpresa | null) => { setEditando(p); setAbierto(true) }

  return (
    <Box>
      <Stack direction="row" alignItems="flex-end" spacing={2} mb={2}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Qué pantallas ve cada persona dentro de esta empresa. Un perfil solo
            puede dar acceso a módulos que la empresa tenga contratados: los dos
            tienen que permitirlo.
          </Typography>
        </Box>
        <Button
          startIcon={<Add />} variant="contained" onClick={() => abrir(null)}
          sx={{ textTransform: 'none', fontWeight: 700, flexShrink: 0 }}
        >
          Nuevo perfil
        </Button>
      </Stack>

      <Card sx={{ borderRadius: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>PERFIL</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>DESCRIPCIÓN</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>PANTALLAS</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>USUARIOS</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>ACCIONES</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && [0, 1, 2].map(i => (
              <TableRow key={i}><TableCell colSpan={5}><Skeleton height={28} /></TableCell></TableRow>
            ))}
            {perfiles.map(p => {
              const cuantas = Object.values(p.permisos).filter(Boolean).length
              return (
                <TableRow key={p.id} hover>
                  <TableCell>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Box sx={{
                        width: 8, height: 8, borderRadius: '50%',
                        bgcolor: p.color || COLOR_MODULO, flexShrink: 0,
                      }} />
                      <Typography sx={{ fontWeight: 700, fontSize: 13 }}>
                        {p.nombre}
                      </Typography>
                      {p.es_sistema && (
                        <Tooltip title="Viene con la plataforma: se puede ajustar pero no eliminar">
                          <Shield sx={{ fontSize: 14, color: PALETA.acero }} />
                        </Tooltip>
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ color: PALETA.grafito, fontSize: 12.5 }}>
                    {p.descripcion || '—'}
                  </TableCell>
                  <TableCell>
                    {/* El portal deja pasar a ADMINISTRADOR sin mirar sus
                        casillas, así que contarlas acá diría «16 de 33» de
                        alguien que en realidad lo ve todo. Se dice lo que
                        pasa de verdad. */}
                    {p.nombre === 'ADMINISTRADOR' ? (
                      <Chip
                        size="small" label="Acceso total"
                        sx={{
                          fontSize: 11, fontWeight: 700,
                          bgcolor: `${ESTADO.exito}1A`, color: ESTADO.exito,
                        }}
                      />
                    ) : (
                      <Chip
                        size="small" label={`${cuantas} de ${permisos.length}`}
                        sx={{
                          fontSize: 11, fontWeight: 700,
                          bgcolor: cuantas === 0 ? `${PALETA.acero}26` : `${COLOR_MODULO}1A`,
                          color: cuantas === 0 ? PALETA.grafito : COLOR_MODULO,
                        }}
                      />
                    )}
                  </TableCell>
                  <TableCell>
                    <Typography sx={{ fontSize: 13, fontWeight: 600 }}>
                      {p.total_usuarios}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="Editar el perfil y sus permisos">
                      <IconButton size="small" onClick={() => abrir(p)}>
                        <Edit fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={
                      p.es_sistema ? 'Los perfiles de la plataforma no se eliminan'
                      : p.total_usuarios ? 'Tiene usuarios: cámbieles el perfil primero'
                      : 'Eliminar'
                    }>
                      <span>
                        <IconButton
                          size="small" color="error"
                          disabled={p.es_sistema || p.total_usuarios > 0 || borrar.isPending}
                          onClick={() => borrar.mutate(p.id)}
                        >
                          <DeleteOutline fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              )
            })}
            {!isLoading && perfiles.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Alert severity="warning" sx={{ my: 1 }}>
                    Esta empresa no tiene ningún perfil, así que sus usuarios no
                    pueden ver nada. Cree al menos uno.
                  </Alert>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <DialogoPerfil
        empresa={empresa} perfil={editando} abierto={abierto}
        permisos={permisos} onCerrar={() => setAbierto(false)}
      />
    </Box>
  )
}
