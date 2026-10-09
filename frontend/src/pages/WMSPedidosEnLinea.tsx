/**
 * WMS · Pedidos en línea — /wms/pedidos-en-linea
 *
 * El recorrido de un pedido de marketplace dentro del almacén:
 *
 *   recibido → inventario comprometido (reservado, falta picking)
 *            → staging de salida (alistado, «por despachar»)
 *            → despachado (viaje en el TMS, la plataforma recibe la guía)
 *            → entregado (lo confirma el TMS)
 *
 * Aquí también se importan pedidos desde Excel o CSV.
 */
import { Fragment, useMemo, useRef, useState } from 'react'
import {
  Alert, Box, Button, Checkbox, Chip, CircularProgress, Collapse, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, InputAdornment, Link, MenuItem, Paper, Stack, Tab, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Tabs, Tooltip, Typography, alpha,
} from '@mui/material'
import {
  Block, Download, KeyboardArrowDown, KeyboardArrowRight, LocalShipping, Replay, Search, UploadFile, Warehouse,
} from '@mui/icons-material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { TextField } from '@/components/comun/Desplegables'
import { apiClient } from '@/api/client'
import { canalesApi, ETAPAS, Pedido, fechaCorta } from '@/api/canales'
import SugerenciaVehiculo from '@/components/tms/SugerenciaVehiculo'
import { ACENTO, ESTADO, PALETA } from '@/config/marca'
import { mensajeDeError } from '@/utils/errorApi'

interface Almacen { id: number; codigo: string; nombre: string }
const pesos = (n: number | null) => n == null ? '—' : n.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })

function ChipEtapa({ etapa }: { etapa: string }) {
  const e = ETAPAS[etapa] ?? { nombre: etapa, color: PALETA.grafito, ayuda: '' }
  return (
    <Tooltip title={e.ayuda}>
      <Chip size="small" label={e.nombre} sx={{ fontWeight: 700, fontSize: 11, bgcolor: alpha(e.color, 0.12), color: e.color, border: `1px solid ${alpha(e.color, 0.35)}` }} />
    </Tooltip>
  )
}

/** Fila de pedido con sus líneas desplegables. */
function FilaPedido({ p, seleccionable, marcado, onMarcar, acciones }: {
  p: Pedido; seleccionable?: boolean; marcado?: boolean; onMarcar?: () => void; acciones?: React.ReactNode
}) {
  const [abierto, setAbierto] = useState(false)
  return (
    <Fragment>
      <TableRow hover selected={marcado}>
        <TableCell padding="checkbox">
          {seleccionable ? <Checkbox checked={!!marcado} onChange={onMarcar} /> : (
            <IconButton size="small" onClick={() => setAbierto(!abierto)}>{abierto ? <KeyboardArrowDown /> : <KeyboardArrowRight />}</IconButton>
          )}
        </TableCell>
        <TableCell onClick={() => setAbierto(!abierto)} sx={{ cursor: 'pointer' }}>
          <Typography sx={{ fontWeight: 700, fontFamily: 'monospace' }}>{p.pedido_externo}</Typography>
          <Typography sx={{ fontSize: 11, color: PALETA.grafito }}>{p.canal} · {fechaCorta(p.fecha_pedido)}</Typography>
        </TableCell>
        <TableCell>
          <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{p.comprador ?? '—'}</Typography>
          <Typography sx={{ fontSize: 11, color: PALETA.grafito }}>{[p.direccion, p.ciudad].filter(Boolean).join(' · ') || '—'}</Typography>
        </TableCell>
        <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{p.numero_orden ?? '—'}</TableCell>
        <TableCell>
          <ChipEtapa etapa={p.etapa} />
          {p.novedad && <Typography sx={{ fontSize: 11, color: ESTADO.peligro, mt: 0.5, maxWidth: 260 }}>{p.novedad}</Typography>}
        </TableCell>
        <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{p.tracking ?? '—'}</TableCell>
        <TableCell align="right">{pesos(p.total)}</TableCell>
        <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{acciones}</TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={8} sx={{ py: 0, borderBottom: abierto ? undefined : 'none' }}>
          <Collapse in={abierto} unmountOnExit>
            <Table size="small" sx={{ my: 1, bgcolor: PALETA.bruma, borderRadius: 2 }}>
              <TableHead><TableRow>
                <TableCell>SKU plataforma</TableCell><TableCell>Descripción</TableCell><TableCell>Producto del maestro</TableCell>
                <TableCell align="right">Cantidad</TableCell><TableCell align="right">Unidades a descontar</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {(p.lineas ?? []).map(l => (
                  <TableRow key={l.id}>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{l.sku_externo ?? '—'}</TableCell>
                    <TableCell>{l.titulo ?? '—'}</TableCell>
                    <TableCell>{l.producto ? `${l.producto.sku} · ${l.producto.nombre}` : <Typography component="span" sx={{ color: ESTADO.peligro, fontSize: 13 }}>Sin mapear</Typography>}</TableCell>
                    <TableCell align="right">{l.cantidad}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 700 }}>{l.unidades ?? '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Collapse>
        </TableCell>
      </TableRow>
    </Fragment>
  )
}

function Cabecera({ check }: { check?: React.ReactNode }) {
  return (
    <TableHead><TableRow>
      <TableCell padding="checkbox">{check}</TableCell><TableCell>Pedido</TableCell><TableCell>Comprador y destino</TableCell>
      <TableCell>Orden de salida</TableCell><TableCell>Etapa</TableCell><TableCell>Guía (viaje TMS)</TableCell>
      <TableCell align="right">Total</TableCell><TableCell />
    </TableRow></TableHead>
  )
}

// ─── Importación desde Excel / CSV ─────────────────────────────────────────────

interface PrevPedido {
  pedido: string; comprador: string | null; ciudad: string | null; direccion: string | null; ya_existe: boolean; valido: boolean
  lineas: { sku: string; cantidad: number; producto: { sku: string; nombre: string; unidades: number } | null; error: string | null }[]
  [k: string]: unknown
}

function ImportarDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const archivoRef = useRef<HTMLInputElement>(null)
  const conectores = useQuery({ queryKey: ['canales', 'conectores'], queryFn: canalesApi.conectores })
  const [canal, setCanal] = useState<number | ''>('')
  const [prev, setPrev] = useState<{ pedidos: PrevPedido[]; validos: number; total: number } | null>(null)
  const elegido = canal || conectores.data?.find(c => c.tipo === 'ARCHIVO')?.id || ''

  const leer = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData()
      fd.append('archivo', f)
      fd.append('conector_id', String(elegido))
      return apiClient.post('/wms/canales/importar/previsualizar', fd).then(r => r.data)
    },
    onSuccess: setPrev,
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const confirmar = useMutation({
    mutationFn: () => apiClient.post('/wms/canales/importar/confirmar', {
      conector_id: Number(elegido), pedidos: (prev?.pedidos ?? []).filter(p => p.valido),
    }).then(r => r.data),
    onSuccess: r => { toast.success(`${r.importados} pedidos importados`); qc.invalidateQueries({ queryKey: ['canales'] }); onClose() },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const plantilla = () => apiClient.get('/wms/canales/importar/plantilla', { responseType: 'blob' }).then(r => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(r.data); a.download = 'plantilla_pedidos.xlsx'; a.click(); URL.revokeObjectURL(a.href)
  })

  return (
    <Dialog open onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ fontWeight: 800 }}>Importar pedidos desde Excel o CSV</DialogTitle>
      <DialogContent dividers>
        <Alert severity="info" sx={{ mb: 2 }}>
          Una fila por producto; las filas con el mismo número de <b>pedido</b> forman un solo pedido. Columnas obligatorias:
          <b> pedido, sku, cantidad</b>. Opcionales: fecha, comprador, documento, telefono, email, direccion, ciudad, precio, titulo.
          El SKU puede ser el del maestro, su código de barras o el código de una caja (descuenta las unidades de la caja).
        </Alert>
        <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} alignItems={{ md: 'center' }}>
          <TextField select size="small" label="Canal al que pertenecen" value={elegido} onChange={e => { setCanal(Number(e.target.value)); setPrev(null) }} sx={{ minWidth: 280 }}>
            {(conectores.data ?? []).map(c => <MenuItem key={c.id} value={c.id}>{c.nombre} ({c.tipo_nombre})</MenuItem>)}
          </TextField>
          <Button variant="outlined" startIcon={<Download />} onClick={plantilla}>Descargar plantilla</Button>
          <Button variant="contained" startIcon={leer.isPending ? <CircularProgress size={16} color="inherit" /> : <UploadFile />}
            disabled={!elegido || leer.isPending} onClick={() => archivoRef.current?.click()}>Elegir archivo</Button>
          <input ref={archivoRef} type="file" hidden accept=".xlsx,.xls,.csv,.txt"
            onChange={e => { const f = e.target.files?.[0]; if (f) leer.mutate(f); e.target.value = '' }} />
        </Stack>
        {!(conectores.data ?? []).length && !conectores.isLoading && (
          <Alert severity="warning" sx={{ mt: 2 }}>Cree primero un canal (por ejemplo de tipo «Importación de archivos») en Canales de venta.</Alert>
        )}
        {prev && (
          <>
            <Typography sx={{ mt: 2, mb: 1, fontWeight: 700 }}>
              {prev.validos} de {prev.total} pedidos listos para importar
            </Typography>
            <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 380 }}>
              <Table size="small" stickyHeader>
                <TableHead><TableRow><TableCell>Pedido</TableCell><TableCell>Comprador</TableCell><TableCell>Líneas</TableCell><TableCell>Estado</TableCell></TableRow></TableHead>
                <TableBody>
                  {prev.pedidos.map(p => (
                    <TableRow key={p.pedido} sx={{ bgcolor: p.valido ? undefined : alpha(ESTADO.peligro, 0.05) }}>
                      <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700 }}>{p.pedido}</TableCell>
                      <TableCell>{p.comprador ?? '—'}<Typography sx={{ fontSize: 11, color: PALETA.grafito }}>{[p.direccion, p.ciudad].filter(Boolean).join(' · ')}</Typography></TableCell>
                      <TableCell>
                        {p.lineas.map((l, i) => (
                          <Typography key={i} sx={{ fontSize: 12, color: l.error ? ESTADO.peligro : undefined }}>
                            {l.cantidad} × {l.sku} {l.producto ? `→ ${l.producto.nombre}${l.producto.unidades > 1 ? ` (×${l.producto.unidades} und)` : ''}` : ''}{l.error ? ` — ${l.error}` : ''}
                          </Typography>
                        ))}
                      </TableCell>
                      <TableCell>{p.ya_existe ? <Chip size="small" label="Ya importado" /> : p.valido
                        ? <Chip size="small" color="success" label="Listo" /> : <Chip size="small" color="error" label="Con errores" />}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!prev?.validos || confirmar.isPending} onClick={() => confirmar.mutate()}>
          {confirmar.isPending ? <CircularProgress size={18} /> : `Importar ${prev?.validos ?? 0} pedidos`}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Página ────────────────────────────────────────────────────────────────────

export default function WMSPedidosEnLinea() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)
  const [almacen, setAlmacen] = useState<number | ''>('')
  const [marcados, setMarcados] = useState<Set<number>>(new Set())
  const [importar, setImportar] = useState(false)
  const [cancelar, setCancelar] = useState<Pedido | null>(null)
  const [motivo, setMotivo] = useState('')
  const [q, setQ] = useState('')
  const [estado, setEstado] = useState('')
  const [resultado, setResultado] = useState<{ pedido_id: number; pedido?: string; ok: boolean; despacho?: string; tracking?: string; detalle?: string }[] | null>(null)

  const almacenes = useQuery<Almacen[]>({ queryKey: ['wms-almacenes'], queryFn: () => apiClient.get('/wms/almacenes/').then(r => r.data) })
  const tablero = useQuery({ queryKey: ['canales', 'por-despachar', almacen], queryFn: () => canalesApi.porDespachar(almacen), refetchInterval: 20_000 })
  const todos = useQuery({
    queryKey: ['canales', 'pedidos', q, estado], enabled: tab === 2,
    queryFn: () => canalesApi.pedidos({ ...(q.trim() ? { q: q.trim() } : {}), ...(estado ? { estado } : {}) }),
  })
  const pedidos = tablero.data?.pedidos ?? []
  const listos = pedidos.filter(p => p.etapa === 'EN_STAGING')
  const comprometidos = pedidos.filter(p => p.etapa === 'COMPROMETIDO')
  const novedad = pedidos.filter(p => p.etapa === 'CON_NOVEDAD')
  const unidadesStaging = useMemo(() => (tablero.data?.staging ?? []).reduce((s, x) => s + x.unidades, 0), [tablero.data])

  const refrescar = () => qc.invalidateQueries({ queryKey: ['canales'] })
  const despachar = useMutation({
    mutationFn: () => canalesApi.despachar(Array.from(marcados)),
    onSuccess: r => { setResultado(r.resultados); setMarcados(new Set()); refrescar() },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const reprocesar = useMutation({
    mutationFn: (id: number) => canalesApi.reprocesar(id),
    onSuccess: p => { p.estado === 'CON_NOVEDAD' ? toast.error(p.novedad ?? 'Sigue con novedad') : toast.success('Inventario comprometido'); refrescar() },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const anular = useMutation({
    mutationFn: () => canalesApi.cancelar(cancelar!.id, motivo || 'Cancelado manualmente'),
    onSuccess: () => { toast.success('Pedido cancelado; las unidades vuelven a estar disponibles'); setCancelar(null); setMotivo(''); refrescar() },
    onError: (e) => toast.error(mensajeDeError(e)),
  })
  const marcar = (id: number) => setMarcados(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const todosMarcados = listos.length > 0 && listos.every(p => marcados.has(p.id))
  const btnCancelar = (p: Pedido) => (
    <Tooltip title="Cancelar pedido (libera la reserva)"><IconButton size="small" onClick={() => setCancelar(p)}><Block fontSize="small" /></IconButton></Tooltip>
  )

  const tarjetas = [
    { titulo: 'Inventario comprometido', valor: comprometidos.length, ayuda: 'reservados · falta el picking', color: ETAPAS.COMPROMETIDO.color },
    { titulo: 'En staging de salida', valor: listos.length, ayuda: `${unidadesStaging.toLocaleString('es-CO')} unidades por despachar`, color: ETAPAS.EN_STAGING.color },
    { titulo: 'Con novedad', valor: novedad.length, ayuda: 'SKU sin mapear o sin stock', color: ETAPAS.CON_NOVEDAD.color },
  ]

  return (
    <Layout title="Pedidos en línea">
      <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} mb={2} alignItems={{ md: 'center' }}>
        <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(Number(e.target.value) || '')} sx={{ minWidth: 220 }}>
          <MenuItem value="">Todos</MenuItem>
          {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.codigo} · {a.nombre}</MenuItem>)}
        </TextField>
        <Box flex={1} />
        <Button variant="outlined" startIcon={<UploadFile />} onClick={() => setImportar(true)} sx={{ textTransform: 'none', fontWeight: 700 }}>
          Importar Excel / CSV
        </Button>
      </Stack>

      <Stack direction={{ xs: 'column', md: 'row' }} gap={2} mb={2}>
        {tarjetas.map(t => (
          <Paper key={t.titulo} variant="outlined" sx={{ flex: 1, p: 2, borderRadius: 3, borderLeft: `4px solid ${t.color}` }}>
            <Typography sx={{ fontSize: 12, fontWeight: 700, color: PALETA.grafito, textTransform: 'uppercase', letterSpacing: 0.5 }}>{t.titulo}</Typography>
            <Typography sx={{ fontSize: 30, fontWeight: 800, color: t.color, lineHeight: 1.2 }}>{t.valor}</Typography>
            <Typography sx={{ fontSize: 12, color: PALETA.grafito }}>{t.ayuda}</Typography>
          </Paper>
        ))}
      </Stack>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label={`Por despachar (${listos.length})`} />
        <Tab label={`En preparación (${comprometidos.length + novedad.length})`} />
        <Tab label="Todos los pedidos" />
        <Tab label="Staging de salida" />
      </Tabs>

      {tab === 0 && (
        <>
          <Stack direction="row" alignItems="center" gap={1.5} mb={1.5}>
            <Typography sx={{ fontSize: 13, color: PALETA.grafito, flex: 1 }}>
              Pedidos alistados que esperan en el staging de salida. Se consolidan por destino, se les asigna el modo de despacho
              y se solicita el transporte al TMS, donde se cargan en los vehículos; la plataforma recibe la guía al confirmar el cargue.
            </Typography>
            <Button variant="contained" startIcon={<LocalShipping />} onClick={() => navigate('/wms/consolidacion')} sx={{ textTransform: 'none', fontWeight: 700 }}>
              Consolidar y despachar
            </Button>
          </Stack>
          {marcados.size > 0 && (
            <Box mb={1.5}>
              <SugerenciaVehiculo titulo={`Carga de ${marcados.size} pedido(s) seleccionado(s) y vehículo sugerido`}
                fuente={{ orden_ids: listos.filter(p => marcados.has(p.id) && p.orden_salida_id).map(p => p.orden_salida_id as number) }} />
            </Box>
          )}
          <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3 }}>
            <Table size="small">
              <Cabecera check={<Checkbox checked={todosMarcados} indeterminate={!todosMarcados && listos.some(p => marcados.has(p.id))}
                onChange={e => setMarcados(e.target.checked ? new Set(listos.map(p => p.id)) : new Set())} />} />
              <TableBody>
                {tablero.isLoading ? <TableRow><TableCell colSpan={8} align="center"><CircularProgress size={24} /></TableCell></TableRow>
                  : !listos.length ? <TableRow><TableCell colSpan={8} align="center" sx={{ py: 5, color: PALETA.grafito }}>
                    No hay pedidos en staging de salida. Los pedidos llegan aquí cuando se termina su picking.</TableCell></TableRow>
                  : listos.map(p => <FilaPedido key={p.id} p={p} seleccionable marcado={marcados.has(p.id)} onMarcar={() => marcar(p.id)} acciones={btnCancelar(p)} />)}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}

      {tab === 1 && (
        <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3 }}>
          <Table size="small">
            <Cabecera />
            <TableBody>
              {![...novedad, ...comprometidos].length && (
                <TableRow><TableCell colSpan={8} align="center" sx={{ py: 5, color: PALETA.grafito }}>Nada en preparación.</TableCell></TableRow>
              )}
              {[...novedad, ...comprometidos].map(p => (
                <FilaPedido key={p.id} p={p} acciones={<>
                  {p.etapa === 'CON_NOVEDAD' && (
                    <Tooltip title="Reintentar (después de mapear el SKU o recibir mercancía)">
                      <IconButton size="small" onClick={() => reprocesar.mutate(p.id)}><Replay fontSize="small" /></IconButton>
                    </Tooltip>
                  )}
                  {p.etapa === 'COMPROMETIDO' && (
                    <Link component="button" sx={{ fontSize: 12, mr: 1 }} onClick={() => navigate('/wms/picking')}>Ir al picking</Link>
                  )}
                  {btnCancelar(p)}
                </>} />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {tab === 2 && (
        <>
          <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} mb={1.5}>
            <TextField size="small" placeholder="Buscar por pedido, comprador o ciudad" value={q} onChange={e => setQ(e.target.value)} sx={{ flex: 1 }}
              InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
            <TextField select size="small" label="Etapa" value={estado} onChange={e => setEstado(e.target.value)} sx={{ minWidth: 220 }}>
              <MenuItem value="">Todas</MenuItem>
              {Object.entries(ETAPAS).filter(([k]) => k !== 'EN_STAGING').map(([k, v]) => <MenuItem key={k} value={k}>{v.nombre}</MenuItem>)}
            </TextField>
          </Stack>
          <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3 }}>
            <Table size="small">
              <Cabecera />
              <TableBody>
                {todos.isLoading ? <TableRow><TableCell colSpan={8} align="center"><CircularProgress size={24} /></TableCell></TableRow>
                  : !(todos.data ?? []).length ? <TableRow><TableCell colSpan={8} align="center" sx={{ py: 5, color: PALETA.grafito }}>Sin pedidos</TableCell></TableRow>
                  : (todos.data ?? []).map(p => <FilaPedido key={p.id} p={p} />)}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}

      {tab === 3 && (
        <>
          <Alert severity="info" icon={<Warehouse />} sx={{ mb: 2 }}>
            El <b>staging de salida</b> es la zona temporal (tipo despacho) donde quedan las unidades alistadas hasta que salen en un viaje.
            No es stock disponible: ya está vendido y no se publica en ningún canal. Cada almacén tiene la suya (código STG-…).
          </Alert>
          <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3 }}>
            <Table size="small">
              <TableHead><TableRow><TableCell>Almacén</TableCell><TableCell>SKU</TableCell><TableCell>Producto</TableCell><TableCell align="right">Unidades por despachar</TableCell></TableRow></TableHead>
              <TableBody>
                {(tablero.data?.staging ?? []).map(s => (
                  <TableRow key={`${s.almacen}-${s.sku}`} hover>
                    <TableCell>{s.almacen}</TableCell><TableCell sx={{ fontFamily: 'monospace' }}>{s.sku}</TableCell>
                    <TableCell>{s.nombre}</TableCell><TableCell align="right" sx={{ fontWeight: 800, color: ACENTO.base }}>{s.unidades.toLocaleString('es-CO')}</TableCell>
                  </TableRow>
                ))}
                {!(tablero.data?.staging ?? []).length && (
                  <TableRow><TableCell colSpan={4} align="center" sx={{ py: 4, color: PALETA.grafito }}>El staging de salida está vacío.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}

      {importar && <ImportarDialog onClose={() => setImportar(false)} />}

      <Dialog open={!!cancelar} onClose={() => setCancelar(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>Cancelar pedido {cancelar?.pedido_externo}</DialogTitle>
        <DialogContent>
          <Typography sx={{ fontSize: 14, mb: 2 }}>
            Se anula la orden de salida y las unidades reservadas vuelven a estar disponibles (y a publicarse en los canales).
            Si ya estaban en el staging de salida, quedan allí disponibles para reubicarlas.
          </Typography>
          <TextField fullWidth size="small" label="Motivo" value={motivo} onChange={e => setMotivo(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelar(null)}>Volver</Button>
          <Button color="error" variant="contained" disabled={anular.isPending} onClick={() => anular.mutate()}>Cancelar pedido</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!resultado} onClose={() => setResultado(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>Resultado del despacho</DialogTitle>
        <DialogContent>
          {(resultado ?? []).map(r => (
            <Alert key={r.pedido_id} severity={r.ok ? 'success' : 'error'} sx={{ mb: 1 }}>
              <b>{r.pedido ?? r.pedido_id}</b>: {r.ok ? `despacho ${r.despacho} · viaje TMS ${r.tracking}` : r.detalle}
            </Alert>
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => navigate('/tms/viajes')}>Ver viajes en el TMS</Button>
          <Button variant="contained" onClick={() => setResultado(null)}>Listo</Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
