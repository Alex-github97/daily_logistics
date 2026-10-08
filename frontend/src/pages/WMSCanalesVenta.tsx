/**
 * WMS · Canales de venta — /wms/canales
 *
 * Conexiones con los marketplaces y tiendas (MercadoLibre, Shopify,
 * WooCommerce, VTEX, Rappi), el webhook genérico y la importación de archivos.
 * Cada canal descuenta de un almacén: lo disponible allí (sin lo comprometido
 * ni lo que está en staging de salida) es lo que se publica como stock.
 */
import { useMemo, useState } from 'react'
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider,
  FormControlLabel, IconButton, InputAdornment, MenuItem, Paper, Stack, Switch, Tab, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Tabs, Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  Add, CheckCircle, ContentCopy, Edit, ErrorOutline, Hub, Link as LinkIcon, Refresh, Storefront, Sync, ViewList,
} from '@mui/icons-material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { apiClient } from '@/api/client'
import { canalesApi, Conector, Publicacion, TipoCanal, fechaCorta } from '@/api/canales'
import { ACENTO, ESTADO, PALETA } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'

interface Almacen { id: number; codigo: string; nombre: string }
interface Nivel { nivel: string; nombre: string; unidades: number; codigo: string }
interface Producto { id: number; sku: string; nombre: string; niveles: Nivel[] }

const COLOR_TIPO: Record<string, string> = {
  MERCADOLIBRE: '#EAB308', SHOPIFY: '#16A34A', WOOCOMMERCE: '#7C3AED', VTEX: '#E11D48',
  RAPPI: '#F97316', WEBHOOK: '#0EA5E9', ARCHIVO: '#475569',
}
const OCULTO = '••••••'

// ─── Formulario del canal ──────────────────────────────────────────────────────

function CanalDialog({ open, conector, tipos, almacenes, onClose }: {
  open: boolean; conector: Conector | null; tipos: TipoCanal[]; almacenes: Almacen[]; onClose: () => void
}) {
  const qc = useQueryClient()
  const [f, setF] = useState(() => ({
    tipo: conector?.tipo ?? 'MERCADOLIBRE', nombre: conector?.nombre ?? '', almacen_id: conector?.almacen_id ?? (almacenes[0]?.id ?? ''),
    credenciales: { ...(conector?.credenciales ?? {}) } as Record<string, string>,
    api_base: conector?.config?.api_base ?? '', colchon_stock: String(conector?.colchon_stock ?? 0),
    sincronizar_stock: conector?.sincronizar_stock ?? true, importar_pedidos: conector?.importar_pedidos ?? true,
    activo: conector?.activo ?? true,
  }))
  const tipo = tipos.find(t => t.tipo === f.tipo)
  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        tipo: f.tipo, nombre: f.nombre, almacen_id: Number(f.almacen_id), credenciales: f.credenciales,
        config: f.api_base.trim() ? { ...(conector?.config ?? {}), api_base: f.api_base.trim() } : {},
        colchon_stock: Number(f.colchon_stock) || 0, sincronizar_stock: f.sincronizar_stock,
        importar_pedidos: f.importar_pedidos, activo: f.activo,
      }
      return conector ? canalesApi.actualizar(conector.id, cuerpo) : canalesApi.crear(cuerpo)
    },
    onSuccess: () => { toast.success(conector ? 'Canal actualizado' : 'Canal creado'); qc.invalidateQueries({ queryKey: ['canales'] }); onClose() },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const listo = f.nombre.trim().length >= 2 && !!f.almacen_id

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ fontWeight: 800 }}>{conector ? `Editar canal · ${conector.nombre}` : 'Nuevo canal de venta'}</DialogTitle>
      <DialogContent dividers>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField select fullWidth size="small" label="Plataforma" value={f.tipo} disabled={!!conector}
              onChange={e => setF({ ...f, tipo: e.target.value, credenciales: {} })}>
              {tipos.map(t => <MenuItem key={t.tipo} value={t.tipo}>{t.nombre}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField fullWidth size="small" label="Nombre del canal" placeholder="Ej. Tienda oficial MercadoLibre"
              value={f.nombre} onChange={e => setF({ ...f, nombre: e.target.value })} />
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField select fullWidth size="small" label="Almacén que despacha" value={f.almacen_id}
              onChange={e => setF({ ...f, almacen_id: Number(e.target.value) })}>
              {almacenes.map(a => <MenuItem key={a.id} value={a.id}>{a.codigo} · {a.nombre}</MenuItem>)}
            </TextField>
          </Grid>
          {tipo?.capacidades.notas.length ? (
            <Grid size={12}>
              <Alert severity="info" icon={<Hub />} sx={{ '& ul': { m: 0, pl: 2 } }}>
                <ul>{tipo.capacidades.notas.map(n => <li key={n}><Typography sx={{ fontSize: 13 }}>{n}</Typography></li>)}</ul>
              </Alert>
            </Grid>
          ) : null}
          {tipo?.campos.map(c => (
            <Grid key={c.clave} size={{ xs: 12, md: 6 }}>
              <TextField fullWidth size="small" label={c.etiqueta} type={c.secreto && f.credenciales[c.clave] !== OCULTO ? 'password' : 'text'}
                value={f.credenciales[c.clave] ?? ''} autoComplete="off"
                onFocus={() => { if (f.credenciales[c.clave] === OCULTO) setF({ ...f, credenciales: { ...f.credenciales, [c.clave]: '' } }) }}
                onChange={e => setF({ ...f, credenciales: { ...f.credenciales, [c.clave]: e.target.value } })}
                helperText={c.secreto && conector?.credenciales[c.clave] === OCULTO ? 'Guardado. Escriba solo si va a cambiarlo.' : undefined} />
            </Grid>
          ))}
          <Grid size={12}><Divider /></Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField fullWidth size="small" type="number" label="Colchón de stock (unidades)" value={f.colchon_stock}
              onChange={e => setF({ ...f, colchon_stock: e.target.value })}
              helperText="Se publican menos unidades que las reales para no sobrevender" />
          </Grid>
          <Grid size={{ xs: 12, md: 8 }}>
            <Stack direction="row" flexWrap="wrap" columnGap={2}>
              <FormControlLabel label="Traer pedidos" control={<Switch checked={f.importar_pedidos}
                disabled={!tipo?.capacidades.pedidos_api} onChange={e => setF({ ...f, importar_pedidos: e.target.checked })} />} />
              <FormControlLabel label="Publicar stock" control={<Switch checked={f.sincronizar_stock}
                disabled={!tipo?.capacidades.stock} onChange={e => setF({ ...f, sincronizar_stock: e.target.checked })} />} />
              <FormControlLabel label="Activo" control={<Switch checked={f.activo} onChange={e => setF({ ...f, activo: e.target.checked })} />} />
            </Stack>
          </Grid>
          {!['WEBHOOK', 'ARCHIVO'].includes(f.tipo) && (
            <Grid size={12}>
              <TextField fullWidth size="small" label="URL de API alterna (opcional: entorno de pruebas / sandbox)"
                value={f.api_base} onChange={e => setF({ ...f, api_base: e.target.value })} />
            </Grid>
          )}
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!listo || guardar.isPending} onClick={() => guardar.mutate()}>
          {guardar.isPending ? <CircularProgress size={18} /> : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Publicaciones (mapeo SKU) ─────────────────────────────────────────────────

function FilaPublicacion({ p, productos }: { p: Publicacion; productos: Producto[] }) {
  const qc = useQueryClient()
  const [producto, setProducto] = useState<number | ''>(p.producto_id ?? '')
  const [unidades, setUnidades] = useState(String(p.unidades))
  const prod = productos.find(x => x.id === producto)
  const cambiado = (producto || null) !== p.producto_id || Number(unidades) !== p.unidades
  const guardar = useMutation({
    mutationFn: () => canalesApi.actualizarPublicacion(p.id, { producto_id: producto || null, unidades: Number(unidades) || 1, activo: p.activo }),
    onSuccess: () => { toast.success('Mapeo guardado'); qc.invalidateQueries({ queryKey: ['canales'] }) },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  return (
    <TableRow hover sx={{ bgcolor: p.producto_id ? undefined : alpha(ESTADO.alerta, 0.05) }}>
      <TableCell>
        <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{p.titulo ?? '—'}</Typography>
        <Typography sx={{ fontSize: 11, color: PALETA.acero, fontFamily: 'monospace' }}>
          {p.ref_externa}{p.ref_variante ? ` / ${p.ref_variante}` : ''}
        </Typography>
      </TableCell>
      <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{p.sku_externo ?? '—'}</TableCell>
      <TableCell sx={{ minWidth: 240 }}>
        <TextField select fullWidth size="small" label="Producto del maestro" value={producto}
          onChange={e => { const id = Number(e.target.value) || ''; setProducto(id); setUnidades('1') }}>
          <MenuItem value="">Sin mapear</MenuItem>
          {productos.map(x => <MenuItem key={x.id} value={x.id}>{x.sku} · {x.nombre}</MenuItem>)}
        </TextField>
      </TableCell>
      <TableCell sx={{ minWidth: 170 }}>
        <TextField size="small" type="number" label="Unidades por venta" value={unidades} onChange={e => setUnidades(e.target.value)}
          sx={{ width: 140 }} />
        {prod && prod.niveles.length > 1 && (
          <Stack direction="row" gap={0.5} mt={0.5} flexWrap="wrap">
            {prod.niveles.map(n => (
              <Chip key={n.nivel} size="small" label={`${n.nivel === 'UNIDAD' ? 'Unidad' : n.nombre} ×${n.unidades}`}
                onClick={() => setUnidades(String(n.unidades))} variant={Number(unidades) === n.unidades ? 'filled' : 'outlined'}
                sx={{ fontSize: 11 }} />
            ))}
          </Stack>
        )}
      </TableCell>
      <TableCell align="right">
        <Typography sx={{ fontWeight: 700 }}>{p.ultimo_stock_enviado ?? '—'}</Typography>
        <Typography sx={{ fontSize: 11, color: p.ultimo_error ? ESTADO.peligro : PALETA.acero }}>
          {p.ultimo_error ? <Tooltip title={p.ultimo_error}><span>Error al publicar</span></Tooltip> : fechaCorta(p.ultimo_envio)}
        </Typography>
      </TableCell>
      <TableCell align="center">
        <Button size="small" variant="contained" disabled={!cambiado || guardar.isPending} onClick={() => guardar.mutate()}>Guardar</Button>
      </TableCell>
    </TableRow>
  )
}

function PublicacionesDialog({ conector, onClose }: { conector: Conector; onClose: () => void }) {
  const qc = useQueryClient()
  const [nueva, setNueva] = useState({ ref_externa: '', sku_externo: '', titulo: '' })
  const pubs = useQuery({ queryKey: ['canales', 'pubs', conector.id], queryFn: () => canalesApi.publicaciones(conector.id) })
  const productos = useQuery<Producto[]>({
    queryKey: ['wms-maestro', true],
    queryFn: () => apiClient.get('/wms/maestro/productos', { params: { activo: true } }).then(r => r.data),
  })
  const traer = useMutation({
    mutationFn: () => canalesApi.traerPublicaciones(conector.id),
    onSuccess: r => { toast.success(`${r.leidas} publicaciones leídas · ${r.nuevas} nuevas · ${r.mapeadas} mapeadas por SKU`); qc.invalidateQueries({ queryKey: ['canales'] }) },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const crear = useMutation({
    mutationFn: () => canalesApi.crearPublicacion(conector.id, { ...nueva, unidades: 1 }),
    onSuccess: () => { setNueva({ ref_externa: '', sku_externo: '', titulo: '' }); qc.invalidateQueries({ queryKey: ['canales'] }) },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const sinMapear = (pubs.data ?? []).filter(p => !p.producto_id).length

  return (
    <Dialog open onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ fontWeight: 800 }}>
        Publicaciones · {conector.nombre}
        <Typography sx={{ fontSize: 13, color: PALETA.grafito }}>
          Cada publicación de la plataforma apunta a un producto del maestro. Si la publicación vende una caja,
          indique cuántas unidades descuenta cada venta (el stock publicado se divide por ese número).
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} mb={2} alignItems={{ md: 'center' }}>
          {conector.capacidades.publicaciones && (
            <Button variant="contained" startIcon={traer.isPending ? <CircularProgress size={16} color="inherit" /> : <Refresh />}
              disabled={traer.isPending} onClick={() => traer.mutate()}>Traer de la plataforma</Button>
          )}
          <Box flex={1} />
          {sinMapear > 0 && <Chip color="warning" label={`${sinMapear} sin mapear`} />}
        </Stack>
        <Paper variant="outlined" sx={{ p: 1.5, mb: 2, borderRadius: 2 }}>
          <Typography sx={{ fontSize: 13, fontWeight: 700, mb: 1 }}>Agregar publicación a mano</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} gap={1}>
            <TextField size="small" label="ID en la plataforma" value={nueva.ref_externa} onChange={e => setNueva({ ...nueva, ref_externa: e.target.value })} />
            <TextField size="small" label="SKU en la plataforma" value={nueva.sku_externo} onChange={e => setNueva({ ...nueva, sku_externo: e.target.value })} />
            <TextField size="small" label="Título" value={nueva.titulo} onChange={e => setNueva({ ...nueva, titulo: e.target.value })} sx={{ flex: 1 }} />
            <Button variant="outlined" startIcon={<Add />} disabled={!nueva.ref_externa.trim() || crear.isPending} onClick={() => crear.mutate()}>Agregar</Button>
          </Stack>
        </Paper>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Publicación</TableCell><TableCell>SKU plataforma</TableCell><TableCell>Producto</TableCell>
                <TableCell>Equivalencia</TableCell><TableCell align="right">Stock publicado</TableCell><TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {pubs.isLoading ? (
                <TableRow><TableCell colSpan={6} align="center"><CircularProgress size={24} /></TableCell></TableRow>
              ) : !(pubs.data ?? []).length ? (
                <TableRow><TableCell colSpan={6} align="center" sx={{ py: 4, color: PALETA.grafito }}>
                  Aún no hay publicaciones. {conector.capacidades.publicaciones ? 'Use «Traer de la plataforma».' : 'Agréguelas a mano.'}
                </TableCell></TableRow>
              ) : (pubs.data ?? []).map(p => <FilaPublicacion key={p.id} p={p} productos={productos.data ?? []} />)}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cerrar</Button></DialogActions>
    </Dialog>
  )
}

// ─── Tarjeta del canal ─────────────────────────────────────────────────────────

function TarjetaCanal({ c, almacen, onEditar, onPublicaciones }: {
  c: Conector; almacen?: Almacen; onEditar: () => void; onPublicaciones: () => void
}) {
  const qc = useQueryClient()
  const color = COLOR_TIPO[c.tipo] ?? ACENTO.base
  const probar = useMutation({
    mutationFn: () => canalesApi.probar(c.id),
    onSuccess: r => { r.ok ? toast.success(r.detalle) : toast.error(r.detalle); qc.invalidateQueries({ queryKey: ['canales'] }) },
  })
  const sync = useMutation({
    mutationFn: () => canalesApi.sincronizar(c.id),
    onSuccess: r => {
      if (r.error) toast.error(r.error)
      else toast.success(`Pedidos nuevos: ${r.pedidos ?? 0} · stock publicado: ${r.stock_enviado ?? 0}${r.stock_errores ? ` (${r.stock_errores} con error)` : ''}`)
      qc.invalidateQueries({ queryKey: ['canales'] })
    },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const autorizar = useMutation({
    mutationFn: () => canalesApi.autorizarML(c.id),
    onSuccess: r => { window.open(r.url, '_blank', 'noopener') },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const ok = c.estado_conexion === 'OK'
  const copiar = () => navigator.clipboard?.writeText(c.url_webhook).then(() => toast.success('URL copiada'))

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, height: '100%', borderTop: `4px solid ${color}`, opacity: c.activo ? 1 : 0.6 }}>
      <Stack direction="row" alignItems="flex-start" gap={1}>
        <Box sx={{ width: 40, height: 40, borderRadius: 2, bgcolor: alpha(color, 0.14), color, display: 'grid', placeItems: 'center' }}>
          <Storefront />
        </Box>
        <Box flex={1} minWidth={0}>
          <Typography sx={{ fontWeight: 800, fontSize: 16 }} noWrap>{c.nombre}</Typography>
          <Typography sx={{ fontSize: 12, color: PALETA.grafito }}>{c.tipo_nombre} · {almacen ? `${almacen.codigo} · ${almacen.nombre}` : '—'}</Typography>
        </Box>
        <Chip size="small" icon={ok ? <CheckCircle /> : c.estado_conexion === 'ERROR' ? <ErrorOutline /> : undefined}
          label={ok ? 'Conectado' : c.estado_conexion === 'ERROR' ? 'Con error' : 'Sin probar'}
          sx={{ fontWeight: 700, bgcolor: alpha(ok ? ESTADO.exito : c.estado_conexion === 'ERROR' ? ESTADO.peligro : PALETA.acero, 0.12),
            color: ok ? ESTADO.exito : c.estado_conexion === 'ERROR' ? ESTADO.peligro : PALETA.grafito }} />
      </Stack>
      {c.ultimo_error && <Alert severity="error" sx={{ mt: 1.5, py: 0, fontSize: 12, wordBreak: 'break-word' }}>{c.ultimo_error}</Alert>}
      {c.tipo === 'MERCADOLIBRE' && !c.autorizado && (
        <Alert severity="warning" sx={{ mt: 1.5, py: 0, fontSize: 12 }}>Falta autorizar la cuenta de MercadoLibre.</Alert>
      )}
      <Stack direction="row" gap={3} mt={1.5}>
        <Box><Typography sx={{ fontSize: 22, fontWeight: 800 }}>{c.pedidos_abiertos ?? 0}</Typography>
          <Typography sx={{ fontSize: 11, color: PALETA.grafito }}>pedidos abiertos</Typography></Box>
        {c.capacidades.stock && (
          <Box><Typography sx={{ fontSize: 22, fontWeight: 800 }}>{c.publicaciones_mapeadas ?? 0}</Typography>
            <Typography sx={{ fontSize: 11, color: PALETA.grafito }}>publicaciones mapeadas</Typography></Box>
        )}
        <Box><Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.6 }}>{fechaCorta(c.ultima_sync_pedidos)}</Typography>
          <Typography sx={{ fontSize: 11, color: PALETA.grafito }}>últimos pedidos</Typography></Box>
        {c.capacidades.stock && (
          <Box><Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.6 }}>{fechaCorta(c.ultima_sync_stock)}</Typography>
            <Typography sx={{ fontSize: 11, color: PALETA.grafito }}>último stock</Typography></Box>
        )}
      </Stack>
      {c.capacidades.webhook && (
        <TextField fullWidth size="small" label="URL de avisos (webhook) para la plataforma" value={c.url_webhook} sx={{ mt: 1.5 }}
          InputProps={{ readOnly: true, sx: { fontSize: 12, fontFamily: 'monospace' },
            endAdornment: <InputAdornment position="end"><IconButton size="small" onClick={copiar}><ContentCopy fontSize="small" /></IconButton></InputAdornment> }} />
      )}
      <Stack direction="row" gap={1} mt={1.5} flexWrap="wrap">
        {c.tipo === 'MERCADOLIBRE' && (
          <Button size="small" variant={c.autorizado ? 'outlined' : 'contained'} color="warning" startIcon={<LinkIcon />}
            onClick={() => autorizar.mutate()}>{c.autorizado ? 'Reautorizar' : 'Autorizar cuenta'}</Button>
        )}
        <Button size="small" variant="outlined" onClick={() => probar.mutate()} disabled={probar.isPending}>Probar conexión</Button>
        {(c.capacidades.pedidos_api || c.capacidades.stock) && (
          <Button size="small" variant="outlined" startIcon={sync.isPending ? <CircularProgress size={14} /> : <Sync />}
            disabled={sync.isPending} onClick={() => sync.mutate()}>Sincronizar ahora</Button>
        )}
        {c.capacidades.stock && <Button size="small" variant="outlined" startIcon={<ViewList />} onClick={onPublicaciones}>Publicaciones</Button>}
        <Box flex={1} />
        <Tooltip title="Editar"><IconButton size="small" onClick={onEditar}><Edit fontSize="small" /></IconButton></Tooltip>
      </Stack>
    </Paper>
  )
}

// ─── Página ────────────────────────────────────────────────────────────────────

/** La gestión de canales, sin el marco de página: también vive como pestaña
 *  «Integraciones» de la Configuración del WMS. */
export function GestionCanales() {
  const [tab, setTab] = useState(0)
  const [form, setForm] = useState<{ open: boolean; conector: Conector | null }>({ open: false, conector: null })
  const [pubs, setPubs] = useState<Conector | null>(null)
  const [filtroBit, setFiltroBit] = useState<number | ''>('')
  const tipos = useQuery({ queryKey: ['canales', 'tipos'], queryFn: canalesApi.tipos, staleTime: 300_000 })
  const conectores = useQuery({ queryKey: ['canales', 'conectores'], queryFn: canalesApi.conectores, refetchInterval: 30_000 })
  const almacenes = useQuery<Almacen[]>({ queryKey: ['wms-almacenes'], queryFn: () => apiClient.get('/wms/almacenes/').then(r => r.data) })
  const bitacora = useQuery({ queryKey: ['canales', 'bitacora', filtroBit], queryFn: () => canalesApi.bitacora(filtroBit || undefined), enabled: tab === 1 })
  const porAlmacen = useMemo(() => new Map((almacenes.data ?? []).map(a => [a.id, a])), [almacenes.data])
  const nombreCanal = useMemo(() => new Map((conectores.data ?? []).map(c => [c.id, c.nombre])), [conectores.data])

  return (
    <>
      <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} mb={2} alignItems={{ md: 'center' }}>
        <Box flex={1}>
          <Typography sx={{ fontSize: 13, color: PALETA.grafito, maxWidth: 820 }}>
            Los pedidos de cada canal entran solos, comprometen inventario del almacén elegido y pasan al
            <b> staging de salida</b> después del picking. El stock disponible se publica en cada plataforma cada vez que cambia.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={() => setForm({ open: true, conector: null })}
          disabled={!tipos.data || !almacenes.data?.length} sx={{ textTransform: 'none', fontWeight: 700 }}>Nuevo canal</Button>
      </Stack>
      {almacenes.data && !almacenes.data.length && <Alert severity="warning" sx={{ mb: 2 }}>Cree primero un almacén en Configuración del WMS.</Alert>}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Canales" /><Tab label="Bitácora de integración" />
      </Tabs>

      {tab === 0 && (conectores.isLoading ? <CircularProgress /> : !(conectores.data ?? []).length ? (
        <Paper variant="outlined" sx={{ p: 5, textAlign: 'center', borderRadius: 3 }}>
          <Storefront sx={{ fontSize: 44, color: PALETA.acero }} />
          <Typography sx={{ fontWeight: 700, mt: 1 }}>Aún no hay canales de venta</Typography>
          <Typography sx={{ color: PALETA.grafito, fontSize: 14 }}>
            Conecte MercadoLibre, Shopify, WooCommerce, VTEX o Rappi, o cree un canal «Importación de archivos» para cargar pedidos desde Excel o CSV.
          </Typography>
        </Paper>
      ) : (
        <Grid container spacing={2}>
          {(conectores.data ?? []).map(c => (
            <Grid key={c.id} size={{ xs: 12, lg: 6 }}>
              <TarjetaCanal c={c} almacen={porAlmacen.get(c.almacen_id)} onEditar={() => setForm({ open: true, conector: c })}
                onPublicaciones={() => setPubs(c)} />
            </Grid>
          ))}
        </Grid>
      ))}

      {tab === 1 && (
        <>
          <TextField select size="small" label="Canal" value={filtroBit} onChange={e => setFiltroBit(Number(e.target.value) || '')} sx={{ minWidth: 240, mb: 2 }}>
            <MenuItem value="">Todos</MenuItem>
            {(conectores.data ?? []).map(c => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
          </TextField>
          <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3 }}>
            <Table size="small">
              <TableHead><TableRow><TableCell>Fecha</TableCell><TableCell>Canal</TableCell><TableCell>Tipo</TableCell><TableCell>Detalle</TableCell></TableRow></TableHead>
              <TableBody>
                {(bitacora.data ?? []).map(b => (
                  <TableRow key={b.id} hover>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{fechaCorta(b.fecha)}</TableCell>
                    <TableCell>{b.conector_id ? nombreCanal.get(b.conector_id) ?? b.conector_id : '—'}</TableCell>
                    <TableCell><Chip size="small" label={b.tipo} sx={{ fontSize: 11, fontWeight: 700,
                      bgcolor: alpha(b.ok ? ACENTO.base : ESTADO.peligro, 0.1), color: b.ok ? ACENTO.profundo : ESTADO.peligro }} /></TableCell>
                    <TableCell sx={{ fontSize: 13, color: b.ok ? undefined : ESTADO.peligro }}>{b.mensaje}</TableCell>
                  </TableRow>
                ))}
                {!bitacora.isLoading && !(bitacora.data ?? []).length && (
                  <TableRow><TableCell colSpan={4} align="center" sx={{ py: 4, color: PALETA.grafito }}>Sin registros</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}

      {form.open && tipos.data && (
        <CanalDialog open conector={form.conector} tipos={tipos.data} almacenes={almacenes.data ?? []}
          onClose={() => setForm({ open: false, conector: null })} />
      )}
      {pubs && <PublicacionesDialog conector={pubs} onClose={() => setPubs(null)} />}
    </>
  )
}

export default function WMSCanalesVenta() {
  return <Layout title="Canales de venta"><GestionCanales /></Layout>
}
