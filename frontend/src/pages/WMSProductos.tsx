/**
 * WMS · Maestro de productos — /wms/productos
 *
 * El listado maestro de todo lo que entra al almacén y termina en el POS. Al
 * crear un producto se genera su SKU y los códigos de cada nivel de empaque
 * (unidad, caja, máster, estiba), listos para imprimir. Desde el listado se
 * reimprimen las etiquetas de uno o varios productos.
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, InputAdornment, MenuItem, Paper, Stack, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography, Alert, Divider,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Add, Edit, Print, QrCode2, Search, Inventory2 } from '@mui/icons-material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { apiClient as api } from '@/api/client'
import { CodigoBarras, Etiqueta, imprimirEtiquetas } from '@/components/wms/CodigoBarras'
import { COLOR_MODULO, PALETA } from '@/config/marca'

interface Nivel { nivel: string; nombre: string; unidades: number; codigo: string; contiene?: string | null }
interface Producto {
  id: number; sku: string; nombre: string; descripcion?: string | null; categoria?: string | null
  familia?: string | null; unidad_medida: string; peso_kg?: number | null; requiere_lote: boolean
  requiere_serial: boolean; requiere_refrigeracion: boolean; vida_util_dias?: number | null; tarifa_iva: number
  depositante_id?: number | null; codigo_barras?: string | null; activo: boolean; existencia: number; niveles: Nivel[]
}

const num = (n: number) => n.toLocaleString('es-CO', { maximumFractionDigits: 2 })

interface CatalogoItem { id: number; nombre: string; activo?: boolean }
interface FamiliaItem extends CatalogoItem { categoria_id: number }

const etiquetasDe = (p: Producto, niveles?: string[]): Etiqueta[] =>
  p.niveles.filter(n => !niveles || niveles.includes(n.nivel)).map(n => ({
    nombre: p.nombre, sku: p.sku, nivel: n.nombre, contiene: n.contiene, codigo: n.codigo,
  }))

// ─── Formulario ───────────────────────────────────────────────────────────────

interface Jerarquia {
  caja: boolean; porCaja: string; codCaja: string
  master: boolean; porMaster: string; codMaster: string
  estiba: boolean; porEstiba: string; codEstiba: string
}

const FORM_VACIO = {
  nombre: '', sku: '', categoria: '', familia: '', descripcion: '', unidad_medida: 'UNIDAD', peso_kg: '',
  tarifa_iva: '19', vida_util_dias: '', requiere_lote: false, requiere_serial: false, requiere_refrigeracion: false,
  codigo_barras: '', depositante_id: '' as number | '', activo: true,
}
const JER_VACIA: Jerarquia = {
  caja: false, porCaja: '12', codCaja: '', master: false, porMaster: '4', codMaster: '',
  estiba: false, porEstiba: '20', codEstiba: '',
}

/** Unidades base de cada nivel, según la jerarquía elegida. */
function totales(j: Jerarquia) {
  const caja = j.caja ? Number(j.porCaja) || 0 : 0
  const master = j.master ? (Number(j.porMaster) || 0) * (caja || 1) : 0
  const estiba = j.estiba ? (Number(j.porEstiba) || 0) * (master || caja || 1) : 0
  return { caja, master, estiba }
}

function jerarquiaDe(p: Producto): Jerarquia {
  const u = (n: string) => p.niveles.find(x => x.nivel === n)
  const caja = u('CAJA'), master = u('MASTER'), estiba = u('ESTIBA')
  const autoCod = (n: Nivel | undefined, suf: string) => n && n.codigo !== `${p.sku}-${suf}` ? n.codigo : ''
  return {
    caja: !!caja, porCaja: String(caja?.unidades ?? 12), codCaja: autoCod(caja, 'CJ'),
    master: !!master, porMaster: String(master ? master.unidades / (caja?.unidades ?? 1) : 4), codMaster: autoCod(master, 'MS'),
    estiba: !!estiba, porEstiba: String(estiba ? estiba.unidades / (master?.unidades ?? caja?.unidades ?? 1) : 20),
    codEstiba: autoCod(estiba, 'ES'),
  }
}

function ProductoDialog({ open, producto, onClose, onGuardado, codigoInicial }: {
  open: boolean; producto: Producto | null; onClose: () => void; onGuardado: (p: Producto) => void
  /** Código de barras leído con el escáner que todavía no existe en el maestro. */
  codigoInicial?: string | null
}) {
  const qc = useQueryClient()
  const editando = !!producto
  const [f, setF] = useState(FORM_VACIO)
  const [j, setJ] = useState<Jerarquia>(JER_VACIA)
  const depositantes = useQuery({ queryKey: ['wms-depositantes'], queryFn: () => api.get<any[]>('/wms/depositantes').then(r => r.data) })
  // Categoría y familia salen de los catálogos (Configuración del WMS): así
  // no aparecen «Bebidas», «bebidas» y «BEBIDAS» como tres categorías.
  const cats = useQuery<CatalogoItem[]>({ queryKey: ['wms-categorias'], queryFn: () => api.get('/wms/categorias-producto/').then(r => r.data) })
  const fams = useQuery<FamiliaItem[]>({ queryKey: ['wms-familias'], queryFn: () => api.get('/wms/familias-producto/').then(r => r.data) })
  const categoriaSel = (cats.data ?? []).find(c => c.nombre.toLowerCase() === f.categoria.toLowerCase())
  const familiasDe = (fams.data ?? []).filter(x => x.activo !== false && categoriaSel && x.categoria_id === categoriaSel.id)
  const [nuevoCat, setNuevoCat] = useState<{ tipo: 'categoria' | 'familia'; nombre: string } | null>(null)
  const crearCatalogo = async () => {
    if (!nuevoCat?.nombre.trim()) return
    try {
      if (nuevoCat.tipo === 'categoria') {
        const c = await api.post('/wms/categorias-producto/', { nombre: nuevoCat.nombre.trim(), activo: true }).then(r => r.data)
        await qc.invalidateQueries({ queryKey: ['wms-categorias'] })
        setF(x => ({ ...x, categoria: c.nombre, familia: '' }))
      } else {
        const c = await api.post('/wms/familias-producto/', { nombre: nuevoCat.nombre.trim(), categoria_id: categoriaSel!.id, activo: true }).then(r => r.data)
        await qc.invalidateQueries({ queryKey: ['wms-familias'] })
        setF(x => ({ ...x, familia: c.nombre }))
      }
      toast.success(`${nuevoCat.tipo === 'categoria' ? 'Categoría' : 'Familia'} creada en el catálogo`)
      setNuevoCat(null)
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'No se pudo crear') }
  }

  useEffect(() => {
    if (!open) return
    if (producto) {
      setF({
        nombre: producto.nombre, sku: producto.sku, categoria: producto.categoria ?? '', familia: producto.familia ?? '',
        descripcion: producto.descripcion ?? '', unidad_medida: producto.unidad_medida, peso_kg: producto.peso_kg?.toString() ?? '',
        tarifa_iva: String(producto.tarifa_iva), vida_util_dias: producto.vida_util_dias?.toString() ?? '',
        requiere_lote: producto.requiere_lote, requiere_serial: producto.requiere_serial,
        requiere_refrigeracion: producto.requiere_refrigeracion,
        codigo_barras: producto.codigo_barras && producto.codigo_barras !== producto.sku ? producto.codigo_barras : '',
        depositante_id: producto.depositante_id ?? '', activo: producto.activo,
      })
      setJ(jerarquiaDe(producto))
    } else {
      setF({ ...FORM_VACIO, codigo_barras: codigoInicial ?? '' }); setJ(JER_VACIA)
    }
  }, [open, producto])

  const t = totales(j)
  const guardar = useMutation({
    mutationFn: () => {
      const niveles = [
        j.caja && { nivel: 'CAJA', unidades: t.caja, codigo_barras: j.codCaja || null },
        j.master && { nivel: 'MASTER', unidades: t.master, codigo_barras: j.codMaster || null },
        j.estiba && { nivel: 'ESTIBA', unidades: t.estiba, codigo_barras: j.codEstiba || null },
      ].filter(Boolean)
      const cuerpo = {
        ...f, sku: editando ? undefined : (f.sku.trim() || null),
        categoria: f.categoria || null, familia: f.familia || null, descripcion: f.descripcion || null,
        peso_kg: f.peso_kg ? Number(f.peso_kg) : null, tarifa_iva: Number(f.tarifa_iva) || 0,
        vida_util_dias: f.vida_util_dias ? Number(f.vida_util_dias) : null,
        codigo_barras: f.codigo_barras.trim() || null, depositante_id: f.depositante_id || null, niveles,
      }
      return (editando ? api.put(`/wms/maestro/productos/${producto!.id}`, cuerpo) : api.post('/wms/maestro/productos', cuerpo))
        .then(r => r.data as Producto)
    },
    onSuccess: p => {
      toast.success(editando ? 'Producto actualizado' : `Producto creado · SKU ${p.sku}`)
      qc.invalidateQueries({ queryKey: ['wms-maestro'] })
      qc.invalidateQueries({ queryKey: ['wms-productos'] })
      onGuardado(p)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo guardar el producto'),
  })

  const jerarquiaMal = (j.caja && t.caja <= 1) || (j.master && t.master <= (t.caja || 1)) ||
    (j.estiba && t.estiba <= (t.master || t.caja || 1))
  const set = (k: keyof typeof FORM_VACIO, v: unknown) => setF(x => ({ ...x, [k]: v }))
  const setJer = (k: keyof Jerarquia, v: unknown) => setJ(x => ({ ...x, [k]: v }))

  const filaNivel = (activo: keyof Jerarquia, por: keyof Jerarquia, cod: keyof Jerarquia, titulo: string,
                     etiquetaPor: string, total: number, sufijo: string) => (
    <Grid container spacing={1.5} alignItems="center" sx={{ mb: 1 }}>
      <Grid size={{ xs: 12, sm: 3 }}>
        <FormControlLabel label={<b>{titulo}</b>}
          control={<Switch checked={j[activo] as boolean} onChange={e => setJer(activo, e.target.checked)} />} />
      </Grid>
      <Grid size={{ xs: 6, sm: 3 }}>
        <TextField fullWidth size="small" type="number" label={etiquetaPor} disabled={!j[activo]}
          value={j[por]} onChange={e => setJer(por, e.target.value)} inputProps={{ min: 2 }} />
      </Grid>
      <Grid size={{ xs: 6, sm: 2 }}>
        <Typography sx={{ fontSize: 13, color: j[activo] ? PALETA.tinta : PALETA.acero }}>
          = <b>{num(total)}</b> und
        </Typography>
      </Grid>
      <Grid size={{ xs: 12, sm: 4 }}>
        <TextField fullWidth size="small" label="Código del fabricante (opcional)" disabled={!j[activo]}
          placeholder={`Automático: ${f.sku || 'SKU'}-${sufijo}`} value={j[cod]} onChange={e => setJer(cod, e.target.value)} />
      </Grid>
    </Grid>
  )

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 800 }}>{editando ? `Editar ${producto!.sku}` : 'Nuevo producto'}</DialogTitle>
      <DialogContent dividers>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, sm: 8 }}>
            <TextField fullWidth size="small" required autoFocus label="Nombre" value={f.nombre} onChange={e => set('nombre', e.target.value)} />
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField fullWidth size="small" label="SKU" value={f.sku} disabled={editando}
              placeholder="Automático" helperText={editando ? 'El SKU no se cambia' : 'Vacío = se genera solo'}
              onChange={e => set('sku', e.target.value.toUpperCase())} />
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Stack direction="row" gap={0.5} alignItems="flex-start">
              <TextField select fullWidth size="small" label="Categoría" value={f.categoria}
                helperText={!editando ? 'Define el prefijo del SKU' : undefined}
                onChange={e => setF(x => ({ ...x, categoria: e.target.value, familia: '' }))}>
                <MenuItem value="">Sin categoría</MenuItem>
                {(cats.data ?? []).filter(c => c.activo !== false).map(c => <MenuItem key={c.id} value={c.nombre}>{c.nombre}</MenuItem>)}
                {f.categoria && !categoriaSel && <MenuItem value={f.categoria}>{f.categoria} (fuera del catálogo)</MenuItem>}
              </TextField>
              <Tooltip title="Crear categoría en el catálogo"><IconButton size="small" sx={{ mt: 0.5 }} onClick={() => setNuevoCat({ tipo: 'categoria', nombre: '' })}><Add fontSize="small" /></IconButton></Tooltip>
            </Stack>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Stack direction="row" gap={0.5} alignItems="flex-start">
              <TextField select fullWidth size="small" label="Familia" value={f.familia} disabled={!categoriaSel}
                helperText={!categoriaSel ? 'Elija primero la categoría' : undefined} onChange={e => set('familia', e.target.value)}>
                <MenuItem value="">Sin familia</MenuItem>
                {familiasDe.map(x => <MenuItem key={x.id} value={x.nombre}>{x.nombre}</MenuItem>)}
                {f.familia && !familiasDe.some(x => x.nombre === f.familia) && <MenuItem value={f.familia}>{f.familia} (fuera del catálogo)</MenuItem>}
              </TextField>
              <Tooltip title="Crear familia en esta categoría"><span><IconButton size="small" sx={{ mt: 0.5 }} disabled={!categoriaSel} onClick={() => setNuevoCat({ tipo: 'familia', nombre: '' })}><Add fontSize="small" /></IconButton></span></Tooltip>
            </Stack>
          </Grid>
          <Grid size={{ xs: 6, sm: 2 }}>
            <TextField fullWidth size="small" label="Unidad" value={f.unidad_medida} onChange={e => set('unidad_medida', e.target.value.toUpperCase())} />
          </Grid>
          <Grid size={{ xs: 6, sm: 2 }}>
            <TextField fullWidth size="small" type="number" label="IVA %" value={f.tarifa_iva} onChange={e => set('tarifa_iva', e.target.value)} />
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <TextField fullWidth size="small" label="Código de barras del fabricante (unidad)" value={f.codigo_barras}
              placeholder="EAN opcional; si no, el SKU" onChange={e => set('codigo_barras', e.target.value)} />
          </Grid>
          <Grid size={{ xs: 6, sm: 2 }}>
            <TextField fullWidth size="small" type="number" label="Peso kg" value={f.peso_kg} onChange={e => set('peso_kg', e.target.value)} />
          </Grid>
          <Grid size={{ xs: 6, sm: 2 }}>
            <TextField fullWidth size="small" type="number" label="Vida útil (días)" value={f.vida_util_dias} onChange={e => set('vida_util_dias', e.target.value)} />
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <TextField select fullWidth size="small" label="Dueño de la mercancía" value={f.depositante_id}
              onChange={e => set('depositante_id', e.target.value === '' ? '' : Number(e.target.value))}>
              <MenuItem value="">Propia</MenuItem>
              {(depositantes.data ?? []).filter(d => !d.propio).map(d => <MenuItem key={d.id} value={d.id}>{d.nombre}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={12}>
            <Stack direction="row" gap={2} flexWrap="wrap">
              <FormControlLabel label="Maneja lote / vencimiento" control={<Checkbox checked={f.requiere_lote} onChange={e => set('requiere_lote', e.target.checked)} />} />
              <FormControlLabel label="Maneja serial" control={<Checkbox checked={f.requiere_serial} onChange={e => set('requiere_serial', e.target.checked)} />} />
              <FormControlLabel label="Refrigerado" control={<Checkbox checked={f.requiere_refrigeracion} onChange={e => set('requiere_refrigeracion', e.target.checked)} />} />
              {editando && <FormControlLabel label="Activo" control={<Switch checked={f.activo} onChange={e => set('activo', e.target.checked)} />} />}
            </Stack>
          </Grid>
        </Grid>

        <Divider sx={{ my: 2 }} />
        <Typography sx={{ fontWeight: 800, mb: 0.5 }}>Jerarquía de empaque</Typography>
        <Typography sx={{ fontSize: 13, color: PALETA.grafito, mb: 1.5 }}>
          La <b>unidad</b> siempre existe. Cada nivel superior tiene su propio SKU y código de barras: al escanearlo en
          una recepción, traslado o despacho suma todas las unidades que contiene.
        </Typography>
        {filaNivel('caja', 'porCaja', 'codCaja', 'Caja', 'Unidades por caja', t.caja, 'CJ')}
        {filaNivel('master', 'porMaster', 'codMaster', 'Caja máster', j.caja ? 'Cajas por máster' : 'Unidades por máster', t.master, 'MS')}
        {filaNivel('estiba', 'porEstiba', 'codEstiba', 'Estiba',
          j.master ? 'Másters por estiba' : j.caja ? 'Cajas por estiba' : 'Unidades por estiba', t.estiba, 'ES')}
        {jerarquiaMal && <Alert severity="warning" sx={{ mt: 1 }}>Cada nivel debe contener más unidades que el anterior.</Alert>}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button variant="contained" disabled={f.nombre.trim().length < 2 || jerarquiaMal || guardar.isPending}
          onClick={() => guardar.mutate()} sx={{ textTransform: 'none', fontWeight: 700, minWidth: 150 }}>
          {guardar.isPending ? <CircularProgress size={20} color="inherit" /> : editando ? 'Guardar cambios' : 'Crear producto'}
        </Button>
      </DialogActions>
      <Dialog open={!!nuevoCat} onClose={() => setNuevoCat(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>
          {nuevoCat?.tipo === 'categoria' ? 'Nueva categoría' : `Nueva familia en ${categoriaSel?.nombre ?? ''}`}
        </DialogTitle>
        <DialogContent>
          <TextField autoFocus fullWidth size="small" label="Nombre" sx={{ mt: 1 }} value={nuevoCat?.nombre ?? ''}
            onChange={e => setNuevoCat(x => x && { ...x, nombre: e.target.value })}
            onKeyDown={e => { if (e.key === 'Enter') crearCatalogo() }}
            helperText="Queda en el catálogo de Configuración del WMS para todos los productos" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNuevoCat(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!nuevoCat?.nombre.trim()} onClick={crearCatalogo}>Crear</Button>
        </DialogActions>
      </Dialog>
    </Dialog>
  )
}

// ─── Códigos de un producto ───────────────────────────────────────────────────

function CodigosDialog({ producto, nuevo, onClose }: { producto: Producto | null; nuevo: boolean; onClose: () => void }) {
  const [copias, setCopias] = useState('1')
  const [niveles, setNiveles] = useState<string[] | null>(null)
  if (!producto) return null
  const elegidos = niveles ?? producto.niveles.map(n => n.nivel)
  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 800 }}>
        {nuevo ? 'Producto creado: códigos listos para imprimir' : `Códigos de ${producto.nombre}`}
      </DialogTitle>
      <DialogContent dividers>
        <Typography sx={{ mb: 2 }}><b>{producto.nombre}</b> · SKU <span style={{ fontFamily: 'monospace' }}>{producto.sku}</span></Typography>
        <Grid container spacing={2}>
          {producto.niveles.map(n => (
            <Grid key={n.nivel} size={{ xs: 12, sm: 6 }}>
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, opacity: elegidos.includes(n.nivel) ? 1 : 0.45 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Box>
                    <Typography sx={{ fontWeight: 800 }}>{n.nombre}</Typography>
                    <Typography sx={{ fontSize: 12.5, color: PALETA.grafito }}>{n.contiene ?? '1 unidad'}</Typography>
                  </Box>
                  <Checkbox checked={elegidos.includes(n.nivel)}
                    onChange={e => setNiveles(e.target.checked ? [...elegidos, n.nivel] : elegidos.filter(x => x !== n.nivel))} />
                </Stack>
                <Box sx={{ textAlign: 'center', mt: 1 }}><CodigoBarras valor={n.codigo} alto={56} /></Box>
              </Paper>
            </Grid>
          ))}
        </Grid>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
        <TextField size="small" type="number" label="Copias por código" value={copias} sx={{ width: 150, mr: 'auto' }}
          inputProps={{ min: 1 }} onChange={e => setCopias(e.target.value)} />
        <Button onClick={onClose} sx={{ textTransform: 'none' }}>Cerrar</Button>
        <Button variant="contained" startIcon={<Print />} disabled={!elegidos.length}
          onClick={() => imprimirEtiquetas(etiquetasDe(producto, elegidos), Number(copias) || 1)}
          sx={{ textTransform: 'none', fontWeight: 700 }}>
          Imprimir etiquetas
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function WMSProductos() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [codigoNuevo, setCodigoNuevo] = useState<string | null>(null)
  const [categoria, setCategoria] = useState('')
  const [soloActivos, setSoloActivos] = useState(true)
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set())
  const [form, setForm] = useState<{ open: boolean; producto: Producto | null }>({ open: false, producto: null })
  const [codigos, setCodigos] = useState<{ producto: Producto; nuevo: boolean } | null>(null)
  const [imprimir, setImprimir] = useState(false)
  const [niveles, setNiveles] = useState<string[]>(['UNIDAD', 'CAJA', 'MASTER', 'ESTIBA'])
  const [copias, setCopias] = useState('1')
  // Desde «Lectura del escáner»: crear un producto con el código que se leyó.
  useEffect(() => {
    if (params.get('nuevo')) {
      setCodigoNuevo(params.get('codigo')); setForm({ open: true, producto: null }); setParams({}, { replace: true })
    } else if (params.get('q')) {
      setQ(params.get('q') ?? ''); setParams({}, { replace: true })
    }
  }, [params])  // eslint-disable-line react-hooks/exhaustive-deps

  const lista = useQuery<Producto[]>({
    queryKey: ['wms-maestro', soloActivos],
    queryFn: () => api.get('/wms/maestro/productos', { params: soloActivos ? { activo: true } : {} }).then(r => r.data),
  })
  const catalogoCat = useQuery<{ id: number; nombre: string }[]>({ queryKey: ['wms-categorias'], queryFn: () => api.get('/wms/categorias-producto/').then(r => r.data) })
  const categorias = useMemo(() => Array.from(new Set([...(catalogoCat.data ?? []).map(c => c.nombre),
    ...(lista.data ?? []).map(p => p.categoria).filter(Boolean)])) as string[], [lista.data, catalogoCat.data])
  const filtrados = useMemo(() => {
    const t = q.trim().toLowerCase()
    return (lista.data ?? []).filter(p =>
      (!categoria || p.categoria === categoria) &&
      (!t || p.sku.toLowerCase().includes(t) || p.nombre.toLowerCase().includes(t) ||
        p.niveles.some(n => n.codigo.toLowerCase().includes(t))))
  }, [lista.data, q, categoria])

  const elegidos = (lista.data ?? []).filter(p => seleccion.has(p.id))
  const todos = filtrados.length > 0 && filtrados.every(p => seleccion.has(p.id))
  const alternar = (id: number) => setSeleccion(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  return (
    <Layout title="Maestro de productos">
      <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} mb={2} alignItems={{ md: 'center' }}>
        <TextField size="small" placeholder="Buscar por SKU, nombre o código de barras" value={q} onChange={e => setQ(e.target.value)}
          sx={{ flex: 1, minWidth: 260 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
        <TextField select size="small" label="Categoría" value={categoria} onChange={e => setCategoria(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">Todas</MenuItem>
          {categorias.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
        </TextField>
        <FormControlLabel label="Solo activos" control={<Switch checked={soloActivos} onChange={e => setSoloActivos(e.target.checked)} />} />
        <Button variant="outlined" startIcon={<Print />} disabled={!elegidos.length} onClick={() => setImprimir(true)}
          sx={{ textTransform: 'none', fontWeight: 700 }}>
          Imprimir códigos{elegidos.length ? ` (${elegidos.length})` : ''}
        </Button>
        <Button variant="contained" startIcon={<Add />} onClick={() => setForm({ open: true, producto: null })}
          sx={{ textTransform: 'none', fontWeight: 700 }}>
          Nuevo producto
        </Button>
      </Stack>

      <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox checked={todos} indeterminate={!todos && filtrados.some(p => seleccion.has(p.id))}
                  onChange={e => setSeleccion(e.target.checked ? new Set(filtrados.map(p => p.id)) : new Set())} />
              </TableCell>
              <TableCell>SKU</TableCell>
              <TableCell>Producto</TableCell>
              <TableCell>Categoría</TableCell>
              <TableCell>Empaques y códigos</TableCell>
              <TableCell align="right">Existencia</TableCell>
              <TableCell align="right">IVA</TableCell>
              <TableCell align="center">Acciones</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {lista.isLoading ? (
              <TableRow><TableCell colSpan={8} align="center" sx={{ py: 5 }}><CircularProgress size={26} /></TableCell></TableRow>
            ) : filtrados.length === 0 ? (
              <TableRow><TableCell colSpan={8} align="center" sx={{ py: 6 }}>
                <Inventory2 sx={{ fontSize: 40, color: PALETA.acero }} />
                <Typography sx={{ color: PALETA.grafito, mt: 1 }}>
                  {(lista.data ?? []).length ? 'Ningún producto coincide con la búsqueda.' : 'Aún no hay productos. Cree el primero con «Nuevo producto».'}
                </Typography>
              </TableCell></TableRow>
            ) : filtrados.map(p => (
              <TableRow key={p.id} hover selected={seleccion.has(p.id)} sx={{ opacity: p.activo ? 1 : 0.55 }}>
                <TableCell padding="checkbox"><Checkbox checked={seleccion.has(p.id)} onChange={() => alternar(p.id)} /></TableCell>
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700 }}>{p.sku}</TableCell>
                <TableCell>
                  <Typography sx={{ fontWeight: 600, fontSize: 14 }}>{p.nombre}</Typography>
                  <Typography sx={{ fontSize: 12, color: PALETA.acero }}>
                    {p.unidad_medida}{p.requiere_lote ? ' · con lote' : ''}{!p.activo ? ' · inactivo' : ''}
                  </Typography>
                </TableCell>
                <TableCell>{p.categoria ?? '—'}</TableCell>
                <TableCell>
                  <Stack direction="row" gap={0.5} flexWrap="wrap">
                    {p.niveles.map(n => (
                      <Tooltip key={n.nivel} title={`${n.codigo}${n.contiene ? ` · ${n.contiene}` : ''}`}>
                        <Chip size="small" variant="outlined" label={n.nivel === 'UNIDAD' ? 'Unidad' : `${n.nombre} ×${num(n.unidades)}`}
                          sx={{ borderColor: COLOR_MODULO, color: COLOR_MODULO, fontWeight: 600 }} />
                      </Tooltip>
                    ))}
                  </Stack>
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{num(p.existencia)}</TableCell>
                <TableCell align="right">{num(p.tarifa_iva)}%</TableCell>
                <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>
                  <Tooltip title="Ver e imprimir códigos">
                    <IconButton size="small" onClick={() => setCodigos({ producto: p, nuevo: false })}><QrCode2 fontSize="small" /></IconButton>
                  </Tooltip>
                  <Tooltip title="Editar">
                    <IconButton size="small" onClick={() => setForm({ open: true, producto: p })}><Edit fontSize="small" /></IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography sx={{ fontSize: 12, color: PALETA.acero, mt: 1 }}>
        {filtrados.length} de {(lista.data ?? []).length} productos · los mismos que vende el POS
      </Typography>

      <ProductoDialog
        open={form.open} producto={form.producto} codigoInicial={form.producto ? null : codigoNuevo}
        onClose={() => { setForm({ open: false, producto: null }); setCodigoNuevo(null) }}
        onGuardado={p => { const nuevo = !form.producto; setForm({ open: false, producto: null }); if (nuevo) setCodigos({ producto: p, nuevo: true }) }}
      />
      {codigos && <CodigosDialog producto={codigos.producto} nuevo={codigos.nuevo} onClose={() => setCodigos(null)} />}

      <Dialog open={imprimir} onClose={() => setImprimir(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>Imprimir códigos de {elegidos.length} producto(s)</DialogTitle>
        <DialogContent dividers>
          <Typography sx={{ fontSize: 13, mb: 1 }}>Qué niveles imprimir (solo los que cada producto tenga):</Typography>
          {[['UNIDAD', 'Unidad'], ['CAJA', 'Caja'], ['MASTER', 'Caja máster'], ['ESTIBA', 'Estiba']].map(([k, l]) => (
            <FormControlLabel key={k} label={l} sx={{ display: 'block' }}
              control={<Checkbox checked={niveles.includes(k)} onChange={e => setNiveles(n => e.target.checked ? [...n, k] : n.filter(x => x !== k))} />} />
          ))}
          <TextField size="small" type="number" label="Copias por código" value={copias} sx={{ mt: 1.5 }}
            inputProps={{ min: 1 }} onChange={e => setCopias(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImprimir(false)} sx={{ textTransform: 'none' }}>Cancelar</Button>
          <Button variant="contained" startIcon={<Print />} disabled={!niveles.length} sx={{ textTransform: 'none', fontWeight: 700 }}
            onClick={() => {
              const ets = elegidos.flatMap(p => etiquetasDe(p, niveles))
              if (!ets.length) { toast.error('Los productos elegidos no tienen esos niveles.'); return }
              imprimirEtiquetas(ets, Number(copias) || 1); setImprimir(false)
            }}>
            Imprimir
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
