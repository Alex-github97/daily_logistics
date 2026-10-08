/**
 * Las empresas de la plataforma y la gente de cada una.
 *
 * La columna de usuarios no es decorativa: una empresa en cero no la puede usar
 * nadie, y esa era la situación en la que quedaba toda empresa recién creada
 * antes de que el alta incluyera a su primer administrador.
 */
import { useEffect, useState } from 'react'
import {
  Box, Card, Typography, Button, Table, TableBody, TableCell, TableHead, TableRow, Chip, IconButton, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions, Stack, Alert, Skeleton, MenuItem, Tabs, Tab,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  Add, Business, Block, PlayArrow, Key, PersonAdd, ArrowBack, Edit,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  consolaApi, mensajeDeError, sesion,
  type Empresa, type ClaveEntregada, type UsuarioDeEmpresa,
} from './api'
import { ClaveDialog } from './ClaveDialog'
import Modulos from './Modulos'
import Comercial from './Comercial'
import Directorio from './Directorio'
import Uso from './Uso'
import Perfiles from './Perfiles'

/** Los que trae toda empresa de fábrica. Solo se usan mientras la lista
 *  real de la empresa está cargando: la de verdad se pide al servidor,
 *  porque un perfil creado a medida no aparecía acá y uno eliminado se
 *  seguía ofreciendo. */
const ROLES = ['ADMINISTRADOR', 'SUPERVISOR_LOGISTICO', 'OPERADOR_BODEGA', 'AUDITOR', 'CONSULTA', 'CONDUCTOR']

const VACIA = {
  codigo: '', nombre: '', nit: '',
  admin_nombre: 'Administrador', admin_apellido: '', admin_email: '', admin_username: 'admin',
}

// ─── Alta de empresa ──────────────────────────────────────────────────────────

function DialogoNuevaEmpresa({
  abierto, onCerrar, onCreada,
}: {
  abierto: boolean
  onCerrar: () => void
  onCreada: (acceso: ClaveEntregada, empresa: string) => void
}) {
  const [f, setF] = useState({ ...VACIA })
  const qc = useQueryClient()

  const crear = useMutation({
    mutationFn: () => consolaApi.crearEmpresa({ ...f, nit: f.nit || null }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['empresas'] })
      onCreada(r.acceso, r.empresa.codigo)
      setF({ ...VACIA })
      onCerrar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const cambiar = (k: keyof typeof VACIA) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Nueva empresa</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 2 }}>
          El código será el nombre del esquema donde vivirán sus datos, así que
          <strong> no se puede cambiar después</strong>. Solo minúsculas, dígitos y
          guion bajo, empezando por letra.
        </Alert>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Código" value={f.codigo} onChange={cambiar('codigo')} fullWidth required
            inputProps={{ style: { textTransform: 'lowercase' }, maxLength: 40 }}
            helperText="Es lo que la empresa escribirá al entrar al portal"
          />
          <TextField label="Nombre" value={f.nombre} onChange={cambiar('nombre')} fullWidth required />
          <TextField label="NIT (opcional)" value={f.nit} onChange={cambiar('nit')} fullWidth />

          <Typography variant="subtitle2" sx={{ pt: 1, fontWeight: 700 }}>
            Primer administrador
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
            Va en el mismo paso a propósito: una empresa sin usuarios no la puede usar nadie.
          </Typography>
          <Stack direction="row" spacing={2}>
            <TextField label="Nombre" value={f.admin_nombre} onChange={cambiar('admin_nombre')} fullWidth />
            <TextField label="Apellido" value={f.admin_apellido} onChange={cambiar('admin_apellido')} fullWidth />
          </Stack>
          <TextField
            label="Usuario" value={f.admin_username} onChange={cambiar('admin_username')} fullWidth required
            inputProps={{ style: { textTransform: 'lowercase' } }}
          />
          <TextField
            label="Correo" type="email" value={f.admin_email} onChange={cambiar('admin_email')}
            fullWidth required
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" onClick={() => crear.mutate()}
          disabled={crear.isPending || !f.codigo.trim() || !f.nombre.trim() || !f.admin_email.trim()}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          {crear.isPending ? 'Creando el esquema…' : 'Crear empresa'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Alta de usuario dentro de una empresa ────────────────────────────────────

const USUARIO_VACIO = { nombre: '', apellido: '', email: '', username: '', rol: 'CONSULTA', cargo: '' }

function DialogoNuevoUsuario({
  empresa, abierto, perfiles, onCerrar, onCreado,
}: {
  empresa: Empresa | null
  abierto: boolean
  /** Los perfiles que existen en ESTA empresa, no una lista fija. */
  perfiles: string[]
  onCerrar: () => void
  onCreado: (acceso: ClaveEntregada) => void
}) {
  const [f, setF] = useState({ ...USUARIO_VACIO })
  const qc = useQueryClient()

  const crear = useMutation({
    mutationFn: () => consolaApi.crearUsuario(empresa!.id, { ...f, cargo: f.cargo || null }),
    onSuccess: a => {
      qc.invalidateQueries({ queryKey: ['usuarios', empresa?.id] })
      qc.invalidateQueries({ queryKey: ['empresas'] })
      onCreado(a); setF({ ...USUARIO_VACIO }); onCerrar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const cambiar = (k: keyof typeof USUARIO_VACIO) => (e: any) =>
    setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>
        Nuevo usuario en {empresa?.nombre}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={2}>
            <TextField label="Nombre" value={f.nombre} onChange={cambiar('nombre')} fullWidth required />
            <TextField label="Apellido" value={f.apellido} onChange={cambiar('apellido')} fullWidth />
          </Stack>
          <TextField
            label="Usuario" value={f.username} onChange={cambiar('username')} fullWidth required
            inputProps={{ style: { textTransform: 'lowercase' } }}
          />
          <TextField label="Correo" type="email" value={f.email} onChange={cambiar('email')} fullWidth required />
          <TextField select label="Rol" value={f.rol} onChange={cambiar('rol')} fullWidth>
            {perfiles.map(r => <MenuItem key={r} value={r}>{r}</MenuItem>)}
          </TextField>
          <TextField label="Cargo (opcional)" value={f.cargo} onChange={cambiar('cargo')} fullWidth />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" onClick={() => crear.mutate()}
          disabled={crear.isPending || !f.nombre.trim() || !f.username.trim() || !f.email.trim()}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Crear usuario
        </Button>
      </DialogActions>
    </Dialog>
  )
}


function DialogoConfirmarClave({
  usuario, esMiCuenta, onCerrar, onConfirmar, ocupado,
}: {
  usuario: UsuarioDeEmpresa | null
  esMiCuenta: boolean
  onCerrar: () => void
  onConfirmar: () => void
  ocupado: boolean
}) {
  return (
    <Dialog open={!!usuario} onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Restablecer contraseña</DialogTitle>
      <DialogContent>
        {esMiCuenta ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            <strong>Es la cuenta con la que usted está conectado.</strong> Su contraseña
            actual dejará de servir de inmediato y la nueva se muestra una sola vez:
            si cierra ese aviso sin copiarla, quedará fuera del sistema.
          </Alert>
        ) : (
          <Alert severity="warning" sx={{ mb: 2 }}>
            La contraseña actual de <strong>{usuario?.username}</strong> dejará de servir
            de inmediato. La nueva se muestra una sola vez.
          </Alert>
        )}
        <Typography variant="body2" color="text.secondary">
          Úselo cuando esa persona perdió el acceso, no para cambiar una contraseña
          que todavía funciona.
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" color={esMiCuenta ? 'error' : 'warning'}
          onClick={onConfirmar} disabled={ocupado}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          {esMiCuenta ? 'Entiendo, restablecer la mía' : 'Restablecer'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Ficha de una empresa: su gente ───────────────────────────────────────────

/**
 * Editar un usuario de una empresa.
 *
 * La consola sabía crear usuarios y restablecerles la clave, pero no
 * corregirlos: un correo mal escrito o un cambio de perfil obligaba a crear
 * otro usuario y desactivar el anterior. El servidor ya aceptaba la edición
 * desde el primer día; lo que faltaba era por dónde pedirla.
 */
function DialogoEditarUsuario({
  empresa, usuario, perfiles, onCerrar,
}: {
  empresa: Empresa
  usuario: UsuarioDeEmpresa | null
  perfiles: string[]
  onCerrar: () => void
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ nombre: '', apellido: '', email: '', rol: '', cargo: '' })

  useEffect(() => {
    if (!usuario) return
    setForm({
      nombre: usuario.nombre ?? '', apellido: usuario.apellido ?? '',
      email: usuario.email ?? '', rol: usuario.rol ?? '',
      cargo: usuario.cargo ?? '',
    })
  }, [usuario])

  const guardar = useMutation({
    mutationFn: () => consolaApi.editarUsuario(empresa.id, usuario!.id, {
      nombre: form.nombre.trim(), apellido: form.apellido.trim(),
      email: form.email.trim(), rol: form.rol,
      cargo: form.cargo.trim() || null,
    }),
    onSuccess: () => {
      toast.success('Usuario actualizado')
      qc.invalidateQueries({ queryKey: ['usuarios', empresa.id] })
      qc.invalidateQueries({ queryKey: ['perfiles', empresa.id] })
      onCerrar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  // El nombre de usuario no se edita: es con lo que la persona entra y lo que
  // queda escrito en la bitácora. Cambiarlo rompería el rastro de lo que hizo.
  return (
    <Dialog open={Boolean(usuario)} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 800, fontSize: 17 }}>
        Editar usuario
        <Typography variant="caption" display="block" color="text.secondary">
          {usuario?.username} · {empresa.nombre}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              size="small" label="Nombre *" fullWidth value={form.nombre}
              onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
            />
            <TextField
              size="small" label="Apellido" fullWidth value={form.apellido}
              onChange={e => setForm(f => ({ ...f, apellido: e.target.value }))}
            />
          </Stack>
          <TextField
            size="small" label="Correo *" type="email" fullWidth value={form.email}
            onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              select size="small" label="Perfil" fullWidth value={form.rol}
              onChange={e => setForm(f => ({ ...f, rol: e.target.value }))}
              helperText="Los perfiles se administran en la pestaña Perfiles"
            >
              {perfiles.map(r => <MenuItem key={r} value={r}>{r}</MenuItem>)}
              {/* Si tiene un perfil que ya no existe, se muestra igual: vaciar
                  el campo en silencio le cambiaría los permisos sin avisar. */}
              {form.rol && !perfiles.includes(form.rol) && (
                <MenuItem value={form.rol}>{form.rol} (ya no existe)</MenuItem>
              )}
            </TextField>
            <TextField
              size="small" label="Cargo" fullWidth value={form.cargo}
              onChange={e => setForm(f => ({ ...f, cargo: e.target.value }))}
            />
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" sx={{ textTransform: 'none', fontWeight: 700 }}
          disabled={!form.nombre.trim() || !form.email.trim() || guardar.isPending}
          onClick={() => guardar.mutate()}
        >
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  )
}


function PestanaUsuarios({
  empresa, onClave,
}: {
  empresa: Empresa
  onClave: (a: ClaveEntregada) => void
}) {
  const qc = useQueryClient()
  const [nuevo, setNuevo] = useState(false)
  const [porEditar, setPorEditar] = useState<UsuarioDeEmpresa | null>(null)
  const [porRestablecer, setPorRestablecer] = useState<UsuarioDeEmpresa | null>(null)
  const yo = sesion.leer()

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ['usuarios', empresa.id],
    queryFn: () => consolaApi.usuarios(empresa.id),
  })

  // Los perfiles que existen de verdad en ESTA empresa, para no ofrecer al
  // asignar uno que no está y para no esconder uno que sí.
  const { data: perfiles = [] } = useQuery({
    queryKey: ['perfiles', empresa.id],
    queryFn: () => consolaApi.perfiles(empresa.id),
  })
  const nombresDePerfil = perfiles.length ? perfiles.map(p => p.nombre) : ROLES

  const clave = useMutation({
    mutationFn: (uid: number) => consolaApi.restablecerClave(empresa.id, uid),
    onSuccess: a => { setPorRestablecer(null); onClave(a) },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const estado = useMutation({
    mutationFn: ({ uid, activo }: { uid: number; activo: boolean }) =>
      consolaApi.editarUsuario(empresa.id, uid, { activo }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['usuarios', empresa.id] })
      qc.invalidateQueries({ queryKey: ['empresas'] })
      toast.success('Usuario actualizado')
    },
    // El servidor impide dejar a una empresa sin administrador activo; el
    // mensaje explica por qué y qué hacer antes.
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  return (
    <Box>
      <Stack direction="row" justifyContent="flex-end" mb={2}>
        <Button
          startIcon={<PersonAdd />} variant="contained" onClick={() => setNuevo(true)}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Nuevo usuario
        </Button>
      </Stack>

      <Card sx={{ borderRadius: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>USUARIO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>NOMBRE</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>CORREO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ROL</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ESTADO</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>ACCIONES</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && [0, 1, 2].map(i => (
              <TableRow key={i}><TableCell colSpan={6}><Skeleton height={28} /></TableCell></TableRow>
            ))}
            {!isLoading && usuarios.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Alert severity="warning" sx={{ my: 1 }}>
                    Esta empresa no tiene ningún usuario, así que nadie puede entrar a ella.
                    Cree al menos un administrador.
                  </Alert>
                </TableCell>
              </TableRow>
            )}
            {usuarios.map(u => (
              <TableRow key={u.id} hover>
                <TableCell sx={{ fontWeight: 700 }}>{u.username}</TableCell>
                <TableCell>{`${u.nombre} ${u.apellido}`.trim()}</TableCell>
                <TableCell sx={{ color: PALETA.grafito }}>{u.email}</TableCell>
                <TableCell>
                  <Chip label={u.rol} size="small" variant="outlined" sx={{ fontSize: 11 }} />
                </TableCell>
                <TableCell>
                  <Chip
                    label={u.activo ? 'Activo' : 'Inactivo'} size="small"
                    sx={{
                      fontSize: 11, fontWeight: 700,
                      bgcolor: u.activo ? `${ESTADO.exito}1A` : `${PALETA.acero}26`,
                      color: u.activo ? ESTADO.exito : PALETA.grafito,
                    }}
                  />
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Editar nombre, correo, perfil y cargo">
                    <IconButton size="small" onClick={() => setPorEditar(u)}>
                      <Edit fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Restablecer contraseña">
                    <IconButton
                      size="small" onClick={() => setPorRestablecer(u)}
                      disabled={clave.isPending}
                    >
                      <Key fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={u.activo ? 'Desactivar' : 'Activar'}>
                    <IconButton
                      size="small"
                      onClick={() => estado.mutate({ uid: u.id, activo: !u.activo })}
                      disabled={estado.isPending}
                    >
                      {u.activo ? <Block fontSize="small" /> : <PlayArrow fontSize="small" />}
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <DialogoNuevoUsuario
        empresa={empresa} abierto={nuevo} perfiles={nombresDePerfil}
        onCerrar={() => setNuevo(false)} onCreado={onClave}
      />
      <DialogoEditarUsuario
        empresa={empresa} usuario={porEditar} perfiles={nombresDePerfil}
        onCerrar={() => setPorEditar(null)}
      />
      <DialogoConfirmarClave
        usuario={porRestablecer}
        esMiCuenta={!!yo && yo.empresa === empresa.codigo && yo.usuario === porRestablecer?.username}
        ocupado={clave.isPending}
        onCerrar={() => setPorRestablecer(null)}
        onConfirmar={() => porRestablecer && clave.mutate(porRestablecer.id)}
      />
    </Box>
  )
}


// ─── Ficha completa de una empresa ────────────────────────────────────────────

const PESTANAS = ['Usuarios', 'Perfiles', 'Módulos', 'Comercial', 'Contactos y documentos', 'Uso'] as const

function FichaEmpresa({
  empresa, onVolver, onClave,
}: {
  empresa: Empresa
  onVolver: () => void
  onClave: (a: ClaveEntregada) => void
}) {
  const [pestana, setPestana] = useState(0)

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1.5} mb={1}>
        <IconButton onClick={onVolver}><ArrowBack /></IconButton>
        <Box sx={{ flex: 1 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="h6" fontWeight={800}>{empresa.nombre}</Typography>
            {!empresa.activo && (
              <Chip label="Suspendida" size="small" sx={{
                fontWeight: 700, fontSize: 11,
                bgcolor: `${ESTADO.peligro}1A`, color: ESTADO.peligro,
              }} />
            )}
          </Stack>
          <Typography variant="caption" color="text.secondary">
            código «{empresa.codigo}» · esquema {empresa.esquema}
            {empresa.nit ? ` · NIT ${empresa.nit}` : ''}
          </Typography>
        </Box>
      </Stack>

      <Tabs
        value={pestana} onChange={(_, v) => setPestana(v)}
        variant="scrollable" scrollButtons="auto"
        sx={{ mb: 2.5, borderBottom: `1px solid ${PALETA.niebla}`,
              '& .MuiTab-root': { textTransform: 'none', fontWeight: 700, minHeight: 44 } }}
      >
        {PESTANAS.map(p => <Tab key={p} label={p} />)}
      </Tabs>

      {pestana === 0 && <PestanaUsuarios empresa={empresa} onClave={onClave} />}
      {pestana === 1 && <Perfiles empresa={empresa} />}
      {pestana === 2 && <Modulos empresa={empresa} />}
      {pestana === 3 && <Comercial empresa={empresa} />}
      {pestana === 4 && <Directorio empresa={empresa} />}
      {pestana === 5 && <Uso empresa={empresa} />}
    </Box>
  )
}

// ─── Edición de los datos de la empresa ───────────────────────────────────────

function DialogoEditar({
  empresa, onCerrar,
}: {
  empresa: Empresa | null
  onCerrar: () => void
}) {
  const qc = useQueryClient()
  const [f, setF] = useState({ nombre: '', nit: '', logo_url: '' })
  const [listo, setListo] = useState<number | null>(null)

  // Se siembra el formulario la primera vez que se abre para cada empresa; sin
  // esto, reabrirlo mostraría los datos de la anterior.
  if (empresa && listo !== empresa.id) {
    setListo(empresa.id)
    setF({ nombre: empresa.nombre, nit: empresa.nit ?? '', logo_url: empresa.logo_url ?? '' })
  }

  const guardar = useMutation({
    mutationFn: () => consolaApi.editarEmpresa(empresa!.id, {
      nombre: f.nombre, nit: f.nit || null, logo_url: f.logo_url || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['empresas'] })
      toast.success('Empresa actualizada'); onCerrar()
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  return (
    <Dialog open={!!empresa} onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Editar empresa</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Código" value={empresa?.codigo ?? ''} fullWidth disabled
            helperText="No se puede cambiar: es el nombre del esquema de sus datos"
          />
          <TextField label="Nombre" value={f.nombre} fullWidth
            onChange={e => setF(p => ({ ...p, nombre: e.target.value }))} />
          <TextField label="NIT" value={f.nit} fullWidth
            onChange={e => setF(p => ({ ...p, nit: e.target.value }))} />
          <TextField label="URL del logo" value={f.logo_url} fullWidth
            onChange={e => setF(p => ({ ...p, logo_url: e.target.value }))}
            helperText="Se muestra en la pantalla de ingreso de esa empresa" />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button variant="contained" onClick={() => guardar.mutate()} disabled={guardar.isPending}
          sx={{ textTransform: 'none', fontWeight: 700 }}>Guardar</Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Listado ──────────────────────────────────────────────────────────────────

export default function Empresas() {
  const qc = useQueryClient()
  const [abierta, setAbierta] = useState<Empresa | null>(null)
  const [editando, setEditando] = useState<Empresa | null>(null)
  const [nueva, setNueva] = useState(false)
  const [acceso, setAcceso] = useState<{ a: ClaveEntregada; empresa?: string } | null>(null)

  const { data: empresas = [], isLoading } = useQuery({
    queryKey: ['empresas'], queryFn: consolaApi.empresas,
  })

  const estado = useMutation({
    mutationFn: ({ id, activo }: { id: number; activo: boolean }) =>
      consolaApi.cambiarEstado(id, activo),
    onSuccess: e => {
      qc.invalidateQueries({ queryKey: ['empresas'] })
      toast.success(e.activo ? 'Empresa reactivada' : 'Empresa suspendida')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  // La ficha reemplaza al listado: son dos vistas del mismo espacio.
  if (abierta) {
    const viva = empresas.find(e => e.id === abierta.id) ?? abierta
    return (
      <>
        <FichaEmpresa
          empresa={viva} onVolver={() => setAbierta(null)}
          onClave={a => setAcceso({ a, empresa: viva.codigo })}
        />
        <ClaveDialog
          acceso={acceso?.a ?? null} empresa={acceso?.empresa} onCerrar={() => setAcceso(null)}
        />
      </>
    )
  }

  return (
    <Box>
      <Stack direction="row" alignItems="center" mb={2.5}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" fontWeight={800}>Empresas</Typography>
          <Typography variant="caption" color="text.secondary">
            {empresas.length} en la plataforma
          </Typography>
        </Box>
        <Button
          startIcon={<Add />} variant="contained" onClick={() => setNueva(true)}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Nueva empresa
        </Button>
      </Stack>

      <Card sx={{ borderRadius: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>CÓDIGO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>NOMBRE</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>USUARIOS</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ESTADO</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>ACCIONES</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && [0, 1, 2].map(i => (
              <TableRow key={i}><TableCell colSpan={5}><Skeleton height={30} /></TableCell></TableRow>
            ))}
            {empresas.map(e => (
              <TableRow
                key={e.id} hover sx={{ cursor: 'pointer' }}
                onClick={() => setAbierta(e)}
              >
                <TableCell sx={{ fontWeight: 700, fontFamily: 'monospace' }}>
                  {e.codigo}
                  {e.es_operador && (
                    <Chip label="operadora" size="small" sx={{
                      ml: 1, height: 18, fontSize: 10, fontWeight: 700,
                      bgcolor: `${COLOR_MODULO}1A`, color: COLOR_MODULO,
                    }} />
                  )}
                </TableCell>
                <TableCell>{e.nombre}</TableCell>
                <TableCell>
                  {e.usuarios === 0 ? (
                    <Tooltip title="Sin usuarios: nadie puede entrar a esta empresa">
                      <Chip label="0" size="small" sx={{
                        height: 20, fontWeight: 800,
                        bgcolor: `${ESTADO.alerta}1F`, color: ESTADO.alerta,
                      }} />
                    </Tooltip>
                  ) : (
                    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                      {e.usuarios_activos} de {e.usuarios}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Chip
                    label={e.activo ? 'Activa' : 'Suspendida'} size="small"
                    sx={{
                      fontWeight: 700, fontSize: 11,
                      bgcolor: e.activo ? `${ESTADO.exito}1A` : `${ESTADO.peligro}1A`,
                      color: e.activo ? ESTADO.exito : ESTADO.peligro,
                    }}
                  />
                </TableCell>
                <TableCell align="right" onClick={ev => ev.stopPropagation()}>
                  <Tooltip title="Editar">
                    <IconButton size="small" onClick={() => setEditando(e)}>
                      <Edit fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={e.es_operador
                    ? 'La empresa operadora no se puede suspender'
                    : (e.activo ? 'Suspender el acceso' : 'Reactivar')}>
                    <span>
                      <IconButton
                        size="small" disabled={e.es_operador || estado.isPending}
                        onClick={() => estado.mutate({ id: e.id, activo: !e.activo })}
                      >
                        {e.activo ? <Block fontSize="small" /> : <PlayArrow fontSize="small" />}
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && empresas.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Box sx={{ textAlign: 'center', py: 4, color: PALETA.acero }}>
                    <Business sx={{ fontSize: 40, opacity: 0.4 }} />
                    <Typography variant="body2" mt={1}>Todavía no hay empresas</Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <DialogoNuevaEmpresa
        abierto={nueva} onCerrar={() => setNueva(false)}
        onCreada={(a, empresa) => setAcceso({ a, empresa })}
      />
      <DialogoEditar empresa={editando} onCerrar={() => setEditando(null)} />
      <ClaveDialog
        acceso={acceso?.a ?? null} empresa={acceso?.empresa} onCerrar={() => setAcceso(null)}
      />
    </Box>
  )
}
