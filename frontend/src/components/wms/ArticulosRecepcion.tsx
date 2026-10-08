/**
 * Artículos de una recepción, con tres formas de registrar lo que llega:
 *
 *   - Selección manual: cada artículo tiene botones (+1 unidad, +1 caja,
 *     «recibir todo») y un campo de cantidad.
 *   - Escáner: código de barras de la unidad, la caja o el máster.
 *   - Radiofrecuencia (RFID): lecturas de etiquetas; cada etiqueta distinta
 *     cuenta una sola vez aunque el lector la lea muchas veces.
 *
 * Si la recepción es contra una orden de compra, los artículos de la OC llegan
 * ya cargados con lo pendiente. Cada línea puede llevar una NOVEDAD (faltante,
 * sobrante, dañado…) o marcarse como NO RECIBIDA. Un sobrante sin novedad no
 * deja guardar: o se acepta con novedad, o se recibe solo lo pedido.
 */
import { useMemo, useRef, useState } from 'react'
import {
  Alert, Box, Button, Chip, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, IconButton,
  LinearProgress, MenuItem, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography, alpha,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  Add, Remove, DoneAll, ReportProblem, Block, Undo, ExpandMore, ExpandLess, DeleteOutline,
  TouchApp, QrCodeScanner, Sensors,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { TextField } from '@/components/comun/Desplegables'
import { CampoEscaner, type Lectura } from '@/components/wms/Escaner'
import { useLectorGlobal } from '@/components/comun/LectorGlobal'
import { apiClient as api } from '@/api/client'
import { COLOR_MODULO } from '@/config/marca'

export interface LineaRecepcion {
  producto_id: number
  cantidad_esperada: number
  cantidad_recibida: number
  lote_id: number | null
  ubicacion_id: number | null
  estado_calidad: 'APROBADO' | 'RECHAZADO' | 'CUARENTENA' | 'INSPECCION'
  notas: string
  novedad?: string | null
  /** La línea viene de la orden de compra (no se cambia el producto ni se borra). */
  de_oc?: boolean
}

interface ProductoBasico { id: number; nombre: string; sku: string; requiere_lote?: boolean }
interface UbicacionBasica { id: number; codigo: string }
interface NivelMaestro { nivel: string; nombre: string; unidades: number }

export const NOVEDADES: [string, string][] = [
  ['FALTANTE', 'Faltante'], ['SOBRANTE', 'Sobrante'], ['NO_SOLICITADO', 'No solicitado en la OC'],
  ['DANADO', 'Dañado'], ['VENCIDO', 'Vencido / próximo a vencer'], ['PRODUCTO_EQUIVOCADO', 'Producto equivocado'],
  ['NO_RECIBIDO', 'No recibido'], ['OTRO', 'Otro'],
]
export const nombreNovedad = (n?: string | null) => NOVEDADES.find(([k]) => k === n)?.[1] ?? n ?? ''

export const LINEA_VACIA: LineaRecepcion = {
  producto_id: 0, cantidad_esperada: 0, cantidad_recibida: 0, lote_id: null, ubicacion_id: null,
  estado_calidad: 'APROBADO', notas: '', novedad: null, de_oc: false,
}

const num = (n: number) => n.toLocaleString('es-CO', { maximumFractionDigits: 2 })

/** El estado de una línea, para pintarla y para validar. */
function estadoLinea(l: LineaRecepcion, conOC: boolean) {
  const e = Number(l.cantidad_esperada) || 0
  const r = Number(l.cantidad_recibida) || 0
  if (l.novedad === 'NO_RECIBIDO') return { texto: 'No recibido', color: '#64748B', bloquea: false }
  if (conOC && e === 0 && r > 0) return { texto: l.novedad ? 'No solicitado · con novedad' : 'No solicitado', color: '#D97706', bloquea: false }
  if (e > 0 && r > e) return l.novedad
    ? { texto: `Sobrante ${num(r - e)} · con novedad`, color: '#D97706', bloquea: false }
    : { texto: `Sobrante ${num(r - e)} sin novedad`, color: '#DC2626', bloquea: true }
  if (e > 0 && r === e) return { texto: l.novedad ? `Completo · ${nombreNovedad(l.novedad)}` : 'Completo', color: '#16A34A', bloquea: false }
  if (e > 0 && r > 0) return { texto: `Faltan ${num(e - r)}${l.novedad ? ` · ${nombreNovedad(l.novedad)}` : ''}`, color: '#D97706', bloquea: false }
  if (e > 0) return { texto: l.novedad ? nombreNovedad(l.novedad) : 'Pendiente', color: l.novedad ? '#D97706' : '#94A3B8', bloquea: false }
  return { texto: l.novedad ? nombreNovedad(l.novedad) : r > 0 ? 'Recibido' : 'Sin cantidad', color: r > 0 ? '#16A34A' : '#94A3B8', bloquea: false }
}

/** Mensajes que impiden guardar la recepción. */
export function problemasRecepcion(lineas: LineaRecepcion[], conOC: boolean): string[] {
  const p: string[] = []
  lineas.forEach((l, i) => {
    if (!(l.producto_id > 0)) p.push(`Línea ${i + 1}: elija el producto.`)
    if (estadoLinea(l, conOC).bloquea) {
      p.push(`Línea ${i + 1}: llegó más de lo pedido. Acéptelo con novedad o reciba solo lo pedido.`)
    }
  })
  return p
}

// ─── Novedad ──────────────────────────────────────────────────────────────────

function DialogoNovedad({ linea, nombre, preset, onCerrar, onGuardar }: {
  linea: LineaRecepcion | null; nombre: string; preset?: string
  onCerrar: () => void; onGuardar: (cambios: Partial<LineaRecepcion>) => void
}) {
  const [tipo, setTipo] = useState(preset ?? linea?.novedad ?? 'FALTANTE')
  const [calidad, setCalidad] = useState<LineaRecepcion['estado_calidad']>(linea?.estado_calidad ?? 'APROBADO')
  const [nota, setNota] = useState(linea?.notas ?? '')
  if (!linea) return null
  const noRecibir = tipo === 'NO_RECIBIDO'
  return (
    <Dialog open onClose={onCerrar} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 800, fontSize: 16 }}>{noRecibir ? 'No recibir artículo' : 'Registrar novedad'}</DialogTitle>
      <DialogContent dividers>
        <Typography sx={{ fontSize: 13.5, mb: 2 }}><b>{nombre}</b></Typography>
        <Stack gap={2}>
          <TextField select size="small" fullWidth label="Tipo de novedad" value={tipo} onChange={e => setTipo(String(e.target.value))}>
            {NOVEDADES.map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
          </TextField>
          {!noRecibir && (
            <TextField select size="small" fullWidth label="Qué se hace con la mercancía" value={calidad}
              onChange={e => setCalidad(e.target.value as LineaRecepcion['estado_calidad'])}
              helperText={calidad === 'RECHAZADO' ? 'Rechazada: no entra al inventario.' : calidad === 'CUARENTENA' ? 'Entra a la zona de cuarentena.' : 'Entra al inventario disponible.'}>
              <MenuItem value="APROBADO">Ingresar al inventario</MenuItem>
              <MenuItem value="CUARENTENA">Ingresar a cuarentena</MenuItem>
              <MenuItem value="INSPECCION">Ingresar para inspección</MenuItem>
              <MenuItem value="RECHAZADO">Rechazar (no ingresa)</MenuItem>
            </TextField>
          )}
          {noRecibir && <Alert severity="info" sx={{ py: 0 }}>La línea queda en 0: no entra nada al inventario y se registra el motivo.</Alert>}
          <TextField size="small" fullWidth multiline minRows={2} label={noRecibir ? 'Motivo' : 'Observación'} value={nota}
            onChange={e => setNota(e.target.value)} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 1.5 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button variant="contained" sx={{ textTransform: 'none', fontWeight: 700 }}
          onClick={() => onGuardar(noRecibir
            ? { novedad: 'NO_RECIBIDO', cantidad_recibida: 0, notas: nota }
            : { novedad: tipo, estado_calidad: calidad, notas: nota })}>
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Una línea ────────────────────────────────────────────────────────────────

function TarjetaLinea({ linea, indice, productos, ubicaciones, niveles, conOC, onCambio, onQuitar, onNovedad }: {
  linea: LineaRecepcion; indice: number; productos: ProductoBasico[]; ubicaciones: UbicacionBasica[]
  niveles: NivelMaestro[]; conOC: boolean
  onCambio: (c: Partial<LineaRecepcion>) => void; onQuitar: () => void; onNovedad: (preset?: string) => void
}) {
  const [abierta, setAbierta] = useState(!linea.de_oc && !(linea.producto_id > 0))
  const prod = productos.find(p => p.id === linea.producto_id)
  const e = Number(linea.cantidad_esperada) || 0
  const r = Number(linea.cantidad_recibida) || 0
  const est = estadoLinea(linea, conOC)
  const noRecibida = linea.novedad === 'NO_RECIBIDO'
  const sumar = (n: number) => onCambio({ cantidad_recibida: Math.max(0, r + n), ...(noRecibida ? { novedad: null } : {}) })
  const empaques = niveles.filter(n => n.nivel !== 'UNIDAD')

  const lotes = useQuery<{ id: number; numero_lote?: string }[]>({
    queryKey: ['wms-lotes', linea.producto_id],
    queryFn: () => api.get(`/wms/lotes/?producto_id=${linea.producto_id}`).then(x => x.data),
    enabled: !!prod?.requiere_lote && linea.producto_id > 0,
  })

  return (
    <Box data-producto={prod?.sku ?? ''} sx={{ p: 1.5, mb: 1.2, borderRadius: 2, border: '1px solid', borderColor: est.bloquea ? '#FCA5A5' : '#E2E8F0',
      bgcolor: noRecibida ? '#F8FAFC' : '#FFF', opacity: noRecibida ? 0.75 : 1 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} alignItems={{ md: 'center' }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" gap={1}>
            <Typography sx={{ fontWeight: 700, fontSize: 14 }} noWrap>
              {prod ? prod.nombre : `Línea ${indice + 1} · elija el producto`}
            </Typography>
            <Chip size="small" label={est.texto}
              sx={{ fontWeight: 700, fontSize: 11, color: est.color, bgcolor: alpha(est.color, 0.1), border: `1px solid ${alpha(est.color, 0.3)}` }} />
          </Stack>
          <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
            {prod && <span style={{ fontFamily: 'monospace' }}>{prod.sku}</span>}
            {e > 0 && <> · pedido <b>{num(e)}</b></>} · recibido <b style={{ color: '#0B1120' }}>{num(r)}</b>
          </Typography>
          {e > 0 && (
            <LinearProgress variant="determinate" value={Math.min(100, (r / e) * 100)}
              sx={{ mt: 0.6, height: 5, borderRadius: 9, bgcolor: '#EEF2FF',
                '& .MuiLinearProgress-bar': { bgcolor: r > e ? '#D97706' : r === e ? '#16A34A' : COLOR_MODULO } }} />
          )}
        </Box>

        {/* Botones de selección manual */}
        <Stack direction="row" gap={0.6} flexWrap="wrap" alignItems="center">
          <Tooltip title="Quitar 1 unidad"><span>
            <IconButton size="small" disabled={r <= 0 || noRecibida} onClick={() => sumar(-1)} sx={{ border: '1px solid #E2E8F0' }}><Remove fontSize="small" /></IconButton>
          </span></Tooltip>
          <Button size="small" variant="outlined" startIcon={<Add />} disabled={!prod} onClick={() => sumar(1)}
            sx={{ textTransform: 'none', fontWeight: 700 }}>1 und</Button>
          {empaques.map(n => (
            <Button key={n.nivel} size="small" variant="outlined" startIcon={<Add />} onClick={() => sumar(n.unidades)}
              sx={{ textTransform: 'none', fontWeight: 700 }}>
              1 {n.nombre.toLowerCase()} ({num(n.unidades)})
            </Button>
          ))}
          {e > r && (
            <Button size="small" variant="contained" startIcon={<DoneAll />} onClick={() => onCambio({ cantidad_recibida: e, novedad: noRecibida ? null : linea.novedad })}
              sx={{ textTransform: 'none', fontWeight: 700 }}>Todo ({num(e - r)})</Button>
          )}
          <TextField size="small" type="number" label="Cantidad" value={r} sx={{ width: 104 }} disabled={noRecibida}
            inputProps={{ min: 0 }} onChange={ev => onCambio({ cantidad_recibida: Math.max(0, Number(ev.target.value) || 0) })} />
          <Tooltip title="Registrar novedad">
            <IconButton size="small" onClick={() => onNovedad()} sx={{ color: linea.novedad && !noRecibida ? '#D97706' : undefined }}><ReportProblem fontSize="small" /></IconButton>
          </Tooltip>
          {noRecibida ? (
            <Tooltip title="Volver a recibir"><IconButton size="small" onClick={() => onCambio({ novedad: null })}><Undo fontSize="small" /></IconButton></Tooltip>
          ) : (
            <Tooltip title="No recibir"><IconButton size="small" onClick={() => onNovedad('NO_RECIBIDO')}><Block fontSize="small" /></IconButton></Tooltip>
          )}
          <Tooltip title={abierta ? 'Ocultar detalle' : 'Ubicación, lote, calidad'}>
            <IconButton size="small" onClick={() => setAbierta(a => !a)}>{abierta ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}</IconButton>
          </Tooltip>
          {!linea.de_oc && (
            <Tooltip title="Eliminar línea"><IconButton size="small" color="error" onClick={onQuitar}><DeleteOutline fontSize="small" /></IconButton></Tooltip>
          )}
        </Stack>
      </Stack>

      {/* Atajos cuando llega más de lo pedido */}
      {est.bloquea && (
        <Stack direction="row" gap={1} mt={1} flexWrap="wrap">
          <Button size="small" color="warning" variant="outlined" sx={{ textTransform: 'none' }}
            onClick={() => onCambio({ novedad: 'SOBRANTE' })}>Aceptar sobrante con novedad</Button>
          <Button size="small" variant="outlined" sx={{ textTransform: 'none' }}
            onClick={() => onCambio({ cantidad_recibida: e })}>Recibir solo lo pedido ({num(e)})</Button>
        </Stack>
      )}
      {!est.bloquea && e > 0 && r > 0 && r < e && !linea.novedad && (
        <Button size="small" color="warning" sx={{ mt: 0.5, textTransform: 'none' }}
          onClick={() => onCambio({ novedad: 'FALTANTE' })}>Registrar faltante de {num(e - r)}</Button>
      )}
      {linea.novedad && linea.notas && (
        <Typography sx={{ fontSize: 12, color: 'text.secondary', mt: 0.5 }}>Novedad: {linea.notas}</Typography>
      )}

      <Collapse in={abierta}>
        <Grid container spacing={1.5} sx={{ mt: 1 }}>
          {!linea.de_oc && (
            <Grid size={{ xs: 12, md: 4 }}>
              <TextField select size="small" fullWidth label="Producto" value={linea.producto_id || ''}
                onChange={ev => onCambio({ producto_id: Number(ev.target.value), lote_id: null })}>
                {productos.map(p => <MenuItem key={p.id} value={p.id}>{p.nombre} ({p.sku})</MenuItem>)}
              </TextField>
            </Grid>
          )}
          {!linea.de_oc && (
            <Grid size={{ xs: 6, md: 2 }}>
              <TextField size="small" fullWidth type="number" label="Esperada" value={e}
                onChange={ev => onCambio({ cantidad_esperada: Math.max(0, Number(ev.target.value) || 0) })} />
            </Grid>
          )}
          <Grid size={{ xs: 6, md: 3 }}>
            <TextField select size="small" fullWidth label="Ubicación" value={linea.ubicacion_id ?? ''}
              onChange={ev => onCambio({ ubicacion_id: ev.target.value === '' ? null : Number(ev.target.value) })}>
              <MenuItem value="">Por defecto del almacén</MenuItem>
              {ubicaciones.map(u => <MenuItem key={u.id} value={u.id}>{u.codigo}</MenuItem>)}
            </TextField>
          </Grid>
          {prod?.requiere_lote && (
            <Grid size={{ xs: 6, md: 3 }}>
              <TextField select size="small" fullWidth label="Lote" value={linea.lote_id ?? ''}
                onChange={ev => onCambio({ lote_id: ev.target.value === '' ? null : Number(ev.target.value) })}>
                <MenuItem value="">Sin lote</MenuItem>
                {(lotes.data ?? []).map(lt => <MenuItem key={lt.id} value={lt.id}>{lt.numero_lote ?? `Lote #${lt.id}`}</MenuItem>)}
              </TextField>
            </Grid>
          )}
          <Grid size={{ xs: 6, md: 3 }}>
            <TextField select size="small" fullWidth label="Calidad" value={linea.estado_calidad}
              onChange={ev => onCambio({ estado_calidad: ev.target.value as LineaRecepcion['estado_calidad'] })}>
              <MenuItem value="APROBADO">Aprobado</MenuItem>
              <MenuItem value="CUARENTENA">Cuarentena</MenuItem>
              <MenuItem value="INSPECCION">Inspección</MenuItem>
              <MenuItem value="RECHAZADO">Rechazado</MenuItem>
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, md: linea.de_oc ? 6 : 12 }}>
            <TextField size="small" fullWidth label="Notas" value={linea.notas} onChange={ev => onCambio({ notas: ev.target.value })} />
          </Grid>
        </Grid>
      </Collapse>
    </Box>
  )
}

// ─── RFID ─────────────────────────────────────────────────────────────────────

interface ResueltoRFID extends Lectura { epc: string }

export function PanelRFID({ onLeido }: { onLeido: (l: Lectura) => void }) {
  const [vistos] = useState(() => new Set<string>())
  const [stats, setStats] = useState({ lecturas: 0, unicas: 0, reconocidas: 0 })
  const [desconocidos, setDesconocidos] = useState<string[]>([])
  const [campo, setCampo] = useState('')
  const [lote, setLote] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const ref = useRef<HTMLInputElement>(null)

  const procesar = async (crudas: string[]) => {
    const limpias = crudas.map(x => x.replace(/\s+/g, '').toUpperCase()).filter(Boolean)
    const nuevas = Array.from(new Set(limpias.filter(x => !vistos.has(x))))
    nuevas.forEach(x => vistos.add(x))
    setStats(s => ({ ...s, lecturas: s.lecturas + limpias.length, unicas: vistos.size }))
    if (!nuevas.length) return
    setOcupado(true)
    try {
      const r = await api.post<{ resueltos: ResueltoRFID[]; desconocidos: string[] }>('/wms/rfid/resolver', { lecturas: nuevas }).then(x => x.data)
      r.resueltos.forEach(x => onLeido({ ...x, veces: 1, total: x.unidades }))
      setStats(s => ({ ...s, reconocidas: s.reconocidas + r.resueltos.length }))
      if (r.desconocidos.length) setDesconocidos(d => [...d, ...r.desconocidos].slice(-50))
    } finally {
      setOcupado(false)
      ref.current?.focus()
    }
  }

  return (
    <Box sx={{ p: 1.5, borderRadius: 2, border: `1px dashed ${alpha(COLOR_MODULO, 0.5)}`, bgcolor: alpha(COLOR_MODULO, 0.04) }}>
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1 }}>
        Con el lector RFID conectado (modo teclado), haga clic en el campo y pase la mercancía por el lector: cada etiqueta
        cuenta una sola vez aunque se lea varias veces. Se aceptan EPC SGTIN-96 (GS1) y etiquetas grabadas con el código del producto.
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5}>
        <TextField inputRef={ref} fullWidth size="small" value={campo} placeholder="Lecturas RFID (Enter por cada etiqueta)"
          InputProps={{ startAdornment: <Sensors sx={{ color: COLOR_MODULO, mr: 1 }} /> }}
          onChange={e => setCampo(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); const v = campo; setCampo(''); procesar([v]) } }} />
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5} mt={1.5} alignItems={{ sm: 'flex-start' }}>
        <TextField fullWidth size="small" multiline minRows={2} maxRows={5} value={lote}
          label="O pegue un lote de lecturas exportado por el lector (una por línea)" onChange={e => setLote(e.target.value)} />
        <Button variant="outlined" disabled={!lote.trim() || ocupado} sx={{ textTransform: 'none', whiteSpace: 'nowrap' }}
          onClick={() => { const v = lote.split(/[\n,;]+/); setLote(''); procesar(v) }}>Procesar lote</Button>
      </Stack>
      <Stack direction="row" gap={1} mt={1.2} flexWrap="wrap" alignItems="center">
        <Chip size="small" label={`${stats.lecturas} ${stats.lecturas === 1 ? 'lectura' : 'lecturas'}`} />
        <Chip size="small" label={`${stats.unicas} ${stats.unicas === 1 ? 'etiqueta única' : 'etiquetas únicas'}`} />
        <Chip size="small" color="success" label={`${stats.reconocidas} ${stats.reconocidas === 1 ? 'reconocida' : 'reconocidas'}`} />
        {desconocidos.length > 0 && <Chip size="small" color="error" label={`${desconocidos.length} sin producto`} />}
        {ocupado && <Typography sx={{ fontSize: 12 }}>Procesando…</Typography>}
      </Stack>
      {desconocidos.length > 0 && (
        <Alert severity="warning" sx={{ mt: 1, py: 0 }}>
          Etiquetas sin producto: {desconocidos.slice(-5).join(', ')}{desconocidos.length > 5 ? '…' : ''}
        </Alert>
      )}
    </Box>
  )
}

// ─── Sección completa ─────────────────────────────────────────────────────────

export function ArticulosRecepcion({ lineas, setLineas, productos, ubicaciones, conOC }: {
  lineas: LineaRecepcion[]
  setLineas: (f: (prev: LineaRecepcion[]) => LineaRecepcion[]) => void
  productos: ProductoBasico[]
  ubicaciones: UbicacionBasica[]
  conOC: boolean
}) {
  const [modo, setModo] = useState<'MANUAL' | 'ESCANER' | 'RFID'>('MANUAL')
  // Una lectura del lector en modo manual pasa sola a modo escáner y se procesa.
  const [lecturaPendiente, setLecturaPendiente] = useState<string | null>(null)
  useLectorGlobal(c => { setLecturaPendiente(c); setModo('ESCANER') }, modo !== 'ESCANER')
  const [novedad, setNovedad] = useState<{ indice: number; preset?: string } | null>(null)
  const maestro = useQuery<{ id: number; niveles: NivelMaestro[] }[]>({
    queryKey: ['wms-maestro', true],
    queryFn: () => api.get('/wms/maestro/productos', { params: { activo: true } }).then(r => r.data),
    staleTime: 60_000,
  })
  const niveles = useMemo(() => new Map((maestro.data ?? []).map(p => [p.id, p.niveles])), [maestro.data])

  const cambiar = (i: number, c: Partial<LineaRecepcion>) => setLineas(prev => prev.map((l, j) => (j === i ? { ...l, ...c } : l)))

  // Escáner y RFID: suman a la línea del producto; si no está en la OC, la crean como «no solicitado».
  const leido = (l: Lectura) => setLineas(prev => {
    const i = prev.findIndex(x => x.producto_id === l.producto_id && x.lote_id == null)
    if (i < 0) {
      return [...prev, { ...LINEA_VACIA, producto_id: l.producto_id, cantidad_recibida: l.total,
                         novedad: conOC ? 'NO_SOLICITADO' : null }]
    }
    return prev.map((x, j) => (j !== i ? x : {
      ...x, cantidad_recibida: (Number(x.cantidad_recibida) || 0) + l.total,
      novedad: x.novedad === 'NO_RECIBIDO' ? null : x.novedad,
    }))
  })

  const resumen = useMemo(() => {
    const est = lineas.map(l => estadoLinea(l, conOC))
    return {
      completas: lineas.filter(l => l.cantidad_esperada > 0 && l.cantidad_recibida === l.cantidad_esperada && l.novedad !== 'NO_RECIBIDO').length,
      novedades: lineas.filter(l => l.novedad).length,
      pendientes: lineas.filter(l => l.cantidad_esperada > 0 && l.cantidad_recibida < l.cantidad_esperada && l.novedad !== 'NO_RECIBIDO').length,
      bloqueos: est.filter(e => e.bloquea).length,
      unidades: lineas.reduce((s, l) => s + (Number(l.cantidad_recibida) || 0), 0),
    }
  }, [lineas, conOC])

  const lineaNovedad = novedad ? lineas[novedad.indice] : null

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} gap={1.5} mb={1.5}>
        <Typography sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', color: 'text.secondary' }}>
          Artículos {conOC ? 'de la orden de compra' : ''}
        </Typography>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
          <ToggleButtonGroup size="small" exclusive value={modo} onChange={(_, v) => v && setModo(v)}>
            <ToggleButton value="MANUAL" sx={{ textTransform: 'none', gap: 0.6 }}><TouchApp fontSize="small" /> Selección manual</ToggleButton>
            <ToggleButton value="ESCANER" sx={{ textTransform: 'none', gap: 0.6 }}><QrCodeScanner fontSize="small" /> Escáner</ToggleButton>
            <ToggleButton value="RFID" sx={{ textTransform: 'none', gap: 0.6 }}><Sensors fontSize="small" /> Radiofrecuencia</ToggleButton>
          </ToggleButtonGroup>
          <Button size="small" variant="outlined" startIcon={<Add />} sx={{ textTransform: 'none' }}
            onClick={() => setLineas(prev => [...prev, { ...LINEA_VACIA, novedad: conOC ? 'NO_SOLICITADO' : null }])}>
            Agregar artículo
          </Button>
        </Stack>
      </Stack>

      {modo === 'ESCANER' && (
        <Box sx={{ mb: 1.5 }}>
          <CampoEscaner onLeido={leido} lecturaInicial={lecturaPendiente} ayuda="Escanee lo que llega: cada caja o máster suma todas sus unidades a la línea del producto." />
        </Box>
      )}
      {modo === 'RFID' && <Box sx={{ mb: 1.5 }}><PanelRFID onLeido={leido} /></Box>}

      {lineas.length > 0 && (
        <Stack direction="row" gap={1} mb={1.2} flexWrap="wrap" alignItems="center">
          <Chip size="small" label={`${lineas.length} ${lineas.length === 1 ? 'artículo' : 'artículos'}`} />
          {conOC && <Chip size="small" color="success" variant="outlined" label={`${resumen.completas} ${resumen.completas === 1 ? 'completo' : 'completos'}`} />}
          {conOC && <Chip size="small" variant="outlined" label={`${resumen.pendientes} ${resumen.pendientes === 1 ? 'pendiente' : 'pendientes'}`} />}
          <Chip size="small" color="warning" variant="outlined" label={`${resumen.novedades} con novedad`} />
          <Chip size="small" label={`${num(resumen.unidades)} unidades recibidas`} sx={{ fontWeight: 700 }} />
          <Box sx={{ flex: 1 }} />
          {conOC && resumen.pendientes > 0 && (
            <Button size="small" startIcon={<DoneAll />} sx={{ textTransform: 'none', fontWeight: 700 }}
              onClick={() => setLineas(prev => prev.map(l => (l.cantidad_esperada > l.cantidad_recibida && l.novedad !== 'NO_RECIBIDO'
                ? { ...l, cantidad_recibida: l.cantidad_esperada } : l)))}>
              Recibir todo lo pendiente
            </Button>
          )}
        </Stack>
      )}

      {lineas.length === 0 ? (
        <Typography fontSize={13} color="text.secondary" align="center" sx={{ py: 3 }}>
          {conOC ? 'La orden de compra no tiene artículos pendientes.'
            : 'Elija una orden de compra para cargar sus artículos, escanee lo que llega o use «Agregar artículo».'}
        </Typography>
      ) : (
        <Box sx={{ maxHeight: 420, overflowY: 'auto', pr: 0.5 }}>
          {lineas.map((l, i) => (
            <TarjetaLinea key={i} linea={l} indice={i} productos={productos} ubicaciones={ubicaciones}
              niveles={niveles.get(l.producto_id) ?? []} conOC={conOC}
              onCambio={c => cambiar(i, c)} onQuitar={() => setLineas(prev => prev.filter((_, j) => j !== i))}
              onNovedad={preset => setNovedad({ indice: i, preset })} />
          ))}
        </Box>
      )}

      {novedad && lineaNovedad && (
        <DialogoNovedad
          key={`${novedad.indice}-${novedad.preset ?? ''}`}
          linea={lineaNovedad} preset={novedad.preset}
          nombre={productos.find(p => p.id === lineaNovedad.producto_id)?.nombre ?? `Línea ${novedad.indice + 1}`}
          onCerrar={() => setNovedad(null)}
          onGuardar={c => { cambiar(novedad.indice, c); setNovedad(null) }}
        />
      )}
    </Box>
  )
}
