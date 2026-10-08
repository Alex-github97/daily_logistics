/**
 * WMS · Cubicaje
 *
 * - Estación: lo que el cubicador acaba de medir aparece solo; se asigna al
 *   producto y nivel de empaque elegidos, o se usa para calibrar.
 * - Productos: los niveles de empaque (unidad, caja, máster, estiba) con sus
 *   medidas, peso y código; desde ahí se calcula cuántas cajas van por estiba.
 * - La ocupación de la bodega (m², m³, posiciones) está en WMS › Inventario › Ocupación de bodega.
 * - Cubicadores: los equipos, su token y su calibración.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Box, Paper, Typography, Tabs, Tab, MenuItem, Autocomplete, Button, Chip, Stack, Alert, Dialog, DialogTitle, DialogContent, DialogActions, FormControlLabel, Checkbox, LinearProgress, IconButton, Tooltip,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Straighten, Scale, ContentCopy, Tune, Delete, ViewInAr } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, Cifra, FormularioRegistro, errorApi, type Campo } from '@/components/comun/Registro'
import { cubicaje, NIVEL_TXT, dims, type Nivel, type Empaque, type ProductoCubicaje, type Medicion, type Cubicador } from '@/api/wmsCubicaje'
import { wms, fechaHora, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO

// ── Estación ─────────────────────────────────────────────────────────────────
function Estacion() {
  const qc = useQueryClient()
  const cubicadores = useQuery({ queryKey: ['cub-equipos'], queryFn: cubicaje.cubicadores })
  const productos = useQuery({ queryKey: ['cub-productos-lista'], queryFn: () => cubicaje.productos({}) })
  const [equipo, setEquipo] = useState<number | ''>('')
  useEffect(() => { if (!equipo && cubicadores.data?.length) setEquipo(cubicadores.data[0].id) }, [cubicadores.data, equipo])
  const mediciones = useQuery({ queryKey: ['cub-mediciones', equipo], enabled: !!equipo, refetchInterval: 1500,
    queryFn: () => cubicaje.mediciones(Number(equipo)) })
  const [producto, setProducto] = useState<ProductoCubicaje | null>(null)
  const [escaneo, setEscaneo] = useState('')
  const [nivel, setNivel] = useState<Nivel>('UNIDAD')
  const [unidades, setUnidades] = useState('')
  const [calibrar, setCalibrar] = useState<Medicion | null>(null)
  const [cal, setCal] = useState({ largo_mm: '', ancho_mm: '', alto_mm: '', peso_g: '' })
  const c = cubicadores.data?.find(x => x.id === equipo)
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['cub-mediciones'] }); qc.invalidateQueries({ queryKey: ['cub-equipos'] }); qc.invalidateQueries({ queryKey: ['cub-productos'] }) }

  const buscar = () => {
    const t = escaneo.trim().toUpperCase()
    const p = productos.data?.find(x => x.sku.toUpperCase() === t || (x.codigo_barras ?? '').toUpperCase() === t)
    if (p) { setProducto(p); setEscaneo('') } else toast.error('No hay un producto con ese código')
  }
  const asignar = async (m: Medicion, aceptar = false) => {
    if (!producto) { toast.error('Elija primero el producto'); return }
    try {
      await cubicaje.asignar(m.id, { producto_id: producto.id, nivel, unidades: nivel === 'UNIDAD' ? undefined : Number(unidades), aceptar_inestable: aceptar })
      toast.success(`${producto.sku}: ${NIVEL_TXT[nivel].toLowerCase()} = ${dims(m.largo_cm, m.ancho_cm, m.alto_cm)}`)
      refrescar()
    } catch (e) { toast.error(errorApi(e)) }
  }
  const confirmarCalibracion = async () => {
    const d = Object.fromEntries(Object.entries(cal).filter(([, v]) => v !== '').map(([k, v]) => [k, Number(v)]))
    try { await cubicaje.calibrar(calibrar!.id, d); toast.success('Calibración actualizada'); setCalibrar(null); refrescar() }
    catch (e) { toast.error(errorApi(e)) }
  }

  if (cubicadores.data && !cubicadores.data.length)
    return <Alert severity="info">No hay cubicadores registrados. Créelo en la pestaña Cubicadores y emita su token.</Alert>
  return (
    <>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mb: 2 }}>
        <Grid container spacing={1.5} alignItems="center">
          <Grid size={{ xs: 12, md: 3 }}>
            <TextField select fullWidth size="small" label="Cubicador" value={equipo} onChange={e => setEquipo(Number(e.target.value))}>
              {(cubicadores.data ?? []).map(x => <MenuItem key={x.id} value={x.id}>{x.codigo} · {x.nombre}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, md: 2 }}>
            <TextField fullWidth size="small" label="Escanear producto" value={escaneo} onChange={e => setEscaneo(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') buscar() }} />
          </Grid>
          <Grid size={{ xs: 12, md: 3 }}>
            <Autocomplete size="small" options={productos.data ?? []} value={producto} onChange={(_, v) => setProducto(v)}
              getOptionLabel={p => `${p.sku} · ${p.nombre}`} isOptionEqualToValue={(a, b) => a.id === b.id}
              renderInput={p => <TextField {...p} label="Producto" />} />
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}>
            <TextField select fullWidth size="small" label="Nivel" value={nivel} onChange={e => setNivel(e.target.value as Nivel)}>
              {(['UNIDAD', 'CAJA', 'MASTER'] as Nivel[]).map(n => <MenuItem key={n} value={n}>{NIVEL_TXT[n]}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}>
            <TextField fullWidth size="small" type="number" label="Unidades que lleva" value={nivel === 'UNIDAD' ? '1' : unidades}
              disabled={nivel === 'UNIDAD'} onChange={e => setUnidades(e.target.value)} />
          </Grid>
        </Grid>
        {c && <Stack direction="row" gap={1} mt={1.5} flexWrap="wrap" alignItems="center">
          {(['x', 'y', 'z', 'peso'] as const).map(k => <Chip key={k} size="small" color={c.calibrado[k] ? 'success' : 'warning'}
            label={`${{ x: 'Largo', y: 'Ancho', z: 'Alto', peso: 'Báscula' }[k]}: ${c.calibrado[k] ? 'calibrado' : 'sin calibrar'}`} />)}
          <Typography fontSize={12} color="text.secondary">Última conexión: {fechaHora(c.ultima_conexion)}{c.firmware ? ` · firmware ${c.firmware}` : ''}</Typography>
        </Stack>}
      </Paper>
      <Typography fontWeight={700} mb={1}>Mediciones por asignar <Typography component="span" fontSize={12} color="text.secondary">(se actualiza sola)</Typography></Typography>
      {mediciones.data && !mediciones.data.length && <Alert severity="info">Ponga la pieza en la esquina y pulse MEDIR en el equipo.</Alert>}
      <Grid container spacing={1.5}>
        {(mediciones.data ?? []).map(m => (
          <Grid key={m.id} size={{ xs: 12, md: 6, lg: 4 }}>
            <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, borderLeft: `4px solid ${m.estable ? '#15803D' : '#D97706'}` }}>
              <Stack direction="row" alignItems="center" gap={1}>
                <Straighten sx={{ color: COLOR }} />
                <Typography fontWeight={800} fontSize={20}>{dims(m.largo_cm, m.ancho_cm, m.alto_cm)}</Typography>
              </Stack>
              <Typography fontSize={13} color="text.secondary">
                <Scale sx={{ fontSize: 14, verticalAlign: 'middle' }} /> {m.peso_kg != null ? `${num(m.peso_kg)} kg` : 'sin peso'}
                {m.volumen_m3 ? ` · ${num(m.volumen_m3)} m³` : ''} · {fechaHora(m.fecha)}
              </Typography>
              <Chip size="small" sx={{ mt: 1 }} color={m.estable ? 'success' : 'warning'}
                label={m.estable ? `Estable (±${m.dispersion_mm} mm)` : `Inestable (±${m.dispersion_mm} mm): repita`} />
              <Stack direction="row" gap={1} mt={1.5} flexWrap="wrap">
                <Button size="small" variant="contained" sx={{ bgcolor: COLOR }} disabled={!producto || (!m.estable)} onClick={() => asignar(m)}>
                  Asignar{producto ? ` a ${producto.sku}` : ''}</Button>
                {!m.estable && producto && <Button size="small" color="warning" onClick={() => asignar(m, true)}>Asignar igual</Button>}
                <Button size="small" startIcon={<Tune />} onClick={() => { setCalibrar(m); setCal({ largo_mm: '', ancho_mm: '', alto_mm: '', peso_g: '' }) }}>Usar para calibrar</Button>
                <Tooltip title="Descartar"><IconButton size="small" onClick={async () => { await cubicaje.descartar(m.id); refrescar() }}><Delete fontSize="small" /></IconButton></Tooltip>
              </Stack>
            </Paper>
          </Grid>
        ))}
      </Grid>
      <Dialog open={!!calibrar} onClose={() => setCalibrar(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Calibrar con esta medición</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
          <Typography fontSize={13} color="text.secondary">
            Escriba las medidas REALES del bloque patrón (mm) y su peso (g). Para la tara, mida con la báscula vacía y ponga 0 g.
            Deje vacío lo que no quiera calibrar.
          </Typography>
          <Stack direction="row" gap={1}>
            <TextField size="small" type="number" label="Largo real (mm)" value={cal.largo_mm} onChange={e => setCal({ ...cal, largo_mm: e.target.value })} />
            <TextField size="small" type="number" label="Ancho real (mm)" value={cal.ancho_mm} onChange={e => setCal({ ...cal, ancho_mm: e.target.value })} />
          </Stack>
          <Stack direction="row" gap={1}>
            <TextField size="small" type="number" label="Alto real (mm)" value={cal.alto_mm} onChange={e => setCal({ ...cal, alto_mm: e.target.value })} />
            <TextField size="small" type="number" label="Peso real (g)" value={cal.peso_g} onChange={e => setCal({ ...cal, peso_g: e.target.value })} />
          </Stack>
        </DialogContent>
        <DialogActions><Button color="inherit" onClick={() => setCalibrar(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!Object.values(cal).some(v => v !== '')} onClick={confirmarCalibracion} sx={{ bgcolor: COLOR }}>Calibrar</Button></DialogActions>
      </Dialog>
    </>
  )
}

// ── Productos y empaques ─────────────────────────────────────────────────────
function EditorEmpaques({ producto, onCerrar }: { producto: ProductoCubicaje; onCerrar: () => void }) {
  const qc = useQueryClient()
  const emps = useQuery({ queryKey: ['cub-empaques', producto.id], queryFn: () => cubicaje.empaques(producto.id) })
  const [filas, setFilas] = useState<Empaque[]>([])
  const [estiba, setEstiba] = useState<any>(null)
  const [param, setParam] = useState({ nivel: 'CAJA', alto_max_cm: '150', peso_max_kg: '1000' })
  useEffect(() => {
    if (emps.data) {
      const por = Object.fromEntries(emps.data.map(e => [e.nivel, e]))
      setFilas((['UNIDAD', 'CAJA', 'MASTER'] as Nivel[]).map(n => por[n] ?? { nivel: n, unidades: n === 'UNIDAD' ? 1 : 0 }))
    }
  }, [emps.data])
  const poner = (i: number, k: keyof Empaque, v: string) => setFilas(fs => fs.map((f, j) => j === i ? { ...f, [k]: v === '' ? null : (k === 'codigo_barras' ? v : Number(v)) } : f))
  const guardar = async () => {
    const usar = filas.filter(f => f.nivel === 'UNIDAD' || (f.unidades && f.unidades > 0))
    const estibaActual = emps.data?.find(e => e.nivel === 'ESTIBA')
    try {
      await cubicaje.guardarEmpaques(producto.id, [...usar.map(f => ({ ...f, unidades: f.nivel === 'UNIDAD' ? 1 : Number(f.unidades) })),
        ...(estibaActual ? [estibaActual] : [])])
      toast.success('Empaques guardados'); qc.invalidateQueries({ queryKey: ['cub-'] }); qc.invalidateQueries({ queryKey: ['cub-productos'] }); qc.invalidateQueries({ queryKey: ['cub-empaques'] })
    } catch (e) { toast.error(errorApi(e)) }
  }
  const calcular = async (guardarlo: boolean) => {
    try {
      const r = await cubicaje.estiba({ producto_id: producto.id, nivel: param.nivel, alto_max_cm: Number(param.alto_max_cm), peso_max_kg: Number(param.peso_max_kg), guardar: guardarlo })
      setEstiba(r); if (guardarlo) { toast.success('Nivel estiba guardado'); qc.invalidateQueries({ queryKey: ['cub-empaques'] }); qc.invalidateQueries({ queryKey: ['cub-productos'] }) }
    } catch (e) { toast.error(errorApi(e)) }
  }
  const est = emps.data?.find(e => e.nivel === 'ESTIBA')
  return (
    <Dialog open onClose={onCerrar} maxWidth="md" fullWidth>
      <DialogTitle sx={{ fontWeight: 800 }}>{producto.sku} · {producto.nombre}</DialogTitle>
      <DialogContent>
        <Typography fontWeight={700} fontSize={13} mb={1}>Niveles de empaque</Typography>
        {filas.map((f, i) => (
          <Grid container spacing={1} key={f.nivel} sx={{ mb: 1 }} alignItems="center">
            <Grid size={{ xs: 12, md: 1.5 }}><Typography fontSize={13} fontWeight={600}>{NIVEL_TXT[f.nivel]}</Typography>
              {f.fuente && <Typography fontSize={10.5} color="text.secondary">{f.fuente === 'CUBICADOR' ? 'medido con cubicador' : 'manual'}</Typography>}</Grid>
            <Grid size={{ xs: 4, md: 1.5 }}><TextField size="small" type="number" label="Unidades" value={f.nivel === 'UNIDAD' ? 1 : (f.unidades || '')} disabled={f.nivel === 'UNIDAD'} onChange={e => poner(i, 'unidades', e.target.value)} /></Grid>
            <Grid size={{ xs: 4, md: 1.5 }}><TextField size="small" type="number" label="Largo cm" value={f.largo_cm ?? ''} onChange={e => poner(i, 'largo_cm', e.target.value)} /></Grid>
            <Grid size={{ xs: 4, md: 1.5 }}><TextField size="small" type="number" label="Ancho cm" value={f.ancho_cm ?? ''} onChange={e => poner(i, 'ancho_cm', e.target.value)} /></Grid>
            <Grid size={{ xs: 4, md: 1.5 }}><TextField size="small" type="number" label="Alto cm" value={f.alto_cm ?? ''} onChange={e => poner(i, 'alto_cm', e.target.value)} /></Grid>
            <Grid size={{ xs: 4, md: 1.5 }}><TextField size="small" type="number" label="Peso kg" value={f.peso_kg ?? ''} onChange={e => poner(i, 'peso_kg', e.target.value)} /></Grid>
            <Grid size={{ xs: 4, md: 3 }}><TextField size="small" fullWidth label="Código de barras" value={f.codigo_barras ?? ''} onChange={e => poner(i, 'codigo_barras', e.target.value)} /></Grid>
          </Grid>
        ))}
        <Typography fontSize={11.5} color="text.secondary">Deje en 0 las unidades de un nivel que el producto no tiene. Si corrige a mano una medida del cubicador, queda como manual.</Typography>
        <Box sx={{ mt: 3, p: 2, bgcolor: '#F8FAFC', borderRadius: 2 }}>
          <Typography fontWeight={700} fontSize={13} mb={1}><ViewInAr sx={{ fontSize: 16, verticalAlign: 'middle' }} /> Armado de estiba (120 × 100 cm)</Typography>
          {est && <Typography fontSize={13} mb={1}>Guardado: {est.cajas_por_cama} cajas por cama × {est.camas} camas = {num(est.unidades)} unidades</Typography>}
          <Stack direction="row" gap={1} flexWrap="wrap">
            <TextField select size="small" label="Con el nivel" value={param.nivel} onChange={e => setParam({ ...param, nivel: e.target.value })} sx={{ width: 150 }}>
              {['UNIDAD', 'CAJA', 'MASTER'].map(n => <MenuItem key={n} value={n}>{NIVEL_TXT[n as Nivel]}</MenuItem>)}
            </TextField>
            <TextField size="small" type="number" label="Alto máximo (cm)" value={param.alto_max_cm} onChange={e => setParam({ ...param, alto_max_cm: e.target.value })} sx={{ width: 150 }} />
            <TextField size="small" type="number" label="Peso máximo (kg)" value={param.peso_max_kg} onChange={e => setParam({ ...param, peso_max_kg: e.target.value })} sx={{ width: 150 }} />
            <Button onClick={() => calcular(false)}>Calcular</Button>
            {estiba?.cajas > 0 && <Button variant="outlined" onClick={() => calcular(true)}>Guardar como nivel estiba</Button>}
          </Stack>
          {estiba && <Alert severity={estiba.cajas ? 'success' : 'warning'} sx={{ mt: 1.5 }}>
            {estiba.cajas ? <><b>{estiba.ti} por cama × {estiba.hi} camas = {estiba.cajas}</b> ({estiba.patron}). Limita: {estiba.limita}. Alto total {estiba.alto_total_cm} cm
              {estiba.peso_total_kg ? `, ${estiba.peso_total_kg} kg` : ''}. Aprovechamiento de la base {estiba.aprovechamiento_base_pct}%, cúbico {estiba.aprovechamiento_cubico_pct}%.</> : estiba.limita}
          </Alert>}
        </Box>
      </DialogContent>
      <DialogActions><Button color="inherit" onClick={onCerrar}>Cerrar</Button><Button variant="contained" onClick={guardar} sx={{ bgcolor: COLOR }}>Guardar empaques</Button></DialogActions>
    </Dialog>
  )
}

function Productos() {
  const [q, setQ] = useState('')
  const [sinMedir, setSinMedir] = useState(false)
  const lista = useQuery({ queryKey: ['cub-productos', q, sinMedir], queryFn: () => cubicaje.productos({ q: q || undefined, solo_sin_medir: sinMedir }) })
  const [editar, setEditar] = useState<ProductoCubicaje | null>(null)
  return (
    <>
      <Stack direction="row" gap={1.5} mb={2} alignItems="center">
        <TextField size="small" label="Buscar producto" value={q} onChange={e => setQ(e.target.value)} />
        <FormControlLabel control={<Checkbox size="small" checked={sinMedir} onChange={e => setSinMedir(e.target.checked)} />} label="Solo los que faltan por medir" />
      </Stack>
      <TablaRegistros filas={lista.data ?? []} cargando={lista.isLoading} vacio="Sin productos" etiqueta={p => p.sku} onEditar={p => setEditar(p)}
        columnas={[
          { titulo: 'SKU', valor: p => p.sku }, { titulo: 'Producto', valor: p => p.nombre },
          { titulo: 'Unidad', valor: p => dims(p.unidad?.largo_cm, p.unidad?.ancho_cm, p.unidad?.alto_cm) },
          { titulo: 'Peso', valor: p => p.peso_kg != null ? `${num(p.peso_kg)} kg` : '—', alinear: 'right' },
          { titulo: 'Volumen', valor: p => p.volumen_m3 != null ? `${num(p.volumen_m3)} m³` : '—', alinear: 'right' },
          { titulo: 'Niveles', valor: p => p.niveles.map(n => NIVEL_TXT[n]).join(', ') || '—' },
          { titulo: 'Estiba', valor: p => p.estiba ? `${p.estiba.ti}×${p.estiba.hi} · ${num(p.estiba.unidades)} und` : '—' },
          { titulo: 'Estado', valor: p => <Chip size="small" color={p.medido ? 'success' : 'warning'} label={p.medido ? (p.fuente === 'CUBICADOR' ? 'Cubicador' : 'Manual') : 'Sin medir'} /> },
        ]} />
      {editar && <EditorEmpaques producto={editar} onCerrar={() => setEditar(null)} />}
    </>
  )
}

// ── Cubicadores ──────────────────────────────────────────────────────────────
function Cubicadores() {
  const qc = useQueryClient()
  const lista = useQuery({ queryKey: ['cub-equipos'], queryFn: cubicaje.cubicadores })
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [dlg, setDlg] = useState<{ abierto: boolean; r: Cubicador | null }>({ abierto: false, r: null })
  const [token, setToken] = useState<string | null>(null)
  const campos: Campo[] = [
    { clave: 'codigo', etiqueta: 'Código', obligatorio: true, ancho: 4 }, { clave: 'nombre', etiqueta: 'Nombre', obligatorio: true, ancho: 8 },
    { clave: 'almacen_id', etiqueta: 'Almacén', tipo: 'seleccion', ancho: 6, opciones: (almacenes.data ?? []).map(a => [a.id, a.nombre] as [number, string]) },
    { clave: 'tolerancia_mm', etiqueta: 'Tolerancia de estabilidad (mm)', tipo: 'numero', min: 0.5, max: 20, ancho: 6 },
    { clave: 'notas', etiqueta: 'Notas', tipo: 'area' }, { clave: 'activo', etiqueta: 'Activo', tipo: 'interruptor' },
  ]
  const refrescar = () => qc.invalidateQueries({ queryKey: ['cub-equipos'] })
  return (
    <>
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}><Button variant="contained" sx={{ bgcolor: COLOR }} onClick={() => setDlg({ abierto: true, r: null })}>Nuevo cubicador</Button></Box>
      <TablaRegistros filas={lista.data ?? []} cargando={lista.isLoading} vacio="Sin cubicadores" etiqueta={c => c.codigo} onEditar={c => setDlg({ abierto: true, r: c })}
        extra={c => <>
          <Button size="small" onClick={async () => { try { const t = await cubicaje.emitirToken(c.id); setToken(t.token); refrescar() } catch (e) { toast.error(errorApi(e)) } }}>
            {c.tiene_token ? 'Nuevo token' : 'Emitir token'}</Button>
          <Button size="small" color="warning" onClick={async () => { try { await cubicaje.reiniciarCalibracion(c.id); toast.success('Calibración reiniciada'); refrescar() } catch (e) { toast.error(errorApi(e)) } }}>Reiniciar calibración</Button>
        </>}
        columnas={[
          { titulo: 'Código', valor: c => c.codigo }, { titulo: 'Nombre', valor: c => c.nombre },
          { titulo: 'Calibración', valor: c => <Stack direction="row" gap={0.5}>{(['x', 'y', 'z', 'peso'] as const).map(k =>
            <Chip key={k} size="small" color={c.calibrado[k] ? 'success' : 'default'} label={k === 'peso' ? 'kg' : k.toUpperCase()} sx={{ height: 20 }} />)}</Stack> },
          { titulo: 'Base X/Y/Z (mm)', valor: c => [c.base_x_mm, c.base_y_mm, c.base_z_mm].map(v => v == null ? '—' : num(v)).join(' / ') },
          { titulo: 'Escala', valor: c => [c.escala_x, c.escala_y, c.escala_z].map(v => num(v)).join(' / ') },
          { titulo: 'Token', valor: c => c.tiene_token ? `emitido ${fechaHora(c.token_emitido_en)}` : 'sin token' },
          { titulo: 'Última conexión', valor: c => fechaHora(c.ultima_conexion) },
          { titulo: 'Estado', valor: c => c.activo ? 'Activo' : 'Inactivo' },
        ]} />
      <FormularioRegistro abierto={dlg.abierto} titulo={dlg.r ? 'Editar cubicador' : 'Nuevo cubicador'} campos={campos} registro={dlg.r}
        valoresIniciales={{ activo: true, tolerancia_mm: 2 }} onCerrar={() => setDlg({ abierto: false, r: null })}
        onGuardar={async c => { if (dlg.r) await cubicaje.editarCubicador(dlg.r.id, c); else await cubicaje.crearCubicador(c); toast.success('Cubicador guardado'); refrescar() }} />
      <Dialog open={!!token} onClose={() => setToken(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Token del cubicador</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>Cópielo ahora en <b>config.h</b> (TOKEN_CUBICADOR): no se vuelve a mostrar. El token anterior quedó revocado.</Alert>
          <TextField fullWidth multiline minRows={3} value={token ?? ''} InputProps={{ readOnly: true, sx: { fontFamily: 'monospace', fontSize: 12 } }} />
        </DialogContent>
        <DialogActions>
          <Button startIcon={<ContentCopy />} onClick={() => { navigator.clipboard?.writeText(token ?? ''); toast.success('Copiado') }}>Copiar</Button>
          <Button onClick={() => setToken(null)}>Listo</Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

export default function WMSCubicaje() {
  const [tab, setTab] = useState(0)
  return (
    <Layout title="WMS — Cubicaje">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Straighten sx={{ fontSize: 28 }} />} titulo="Cubicaje" color={COLOR}
          subtitulo="Medidas y peso por nivel de empaque y armado de estibas" />
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="Estación" /><Tab label="Productos" /><Tab label="Cubicadores" />
        </Tabs>
        {tab === 0 && <Estacion />}
        {tab === 1 && <Productos />}
        {tab === 2 && <Cubicadores />}
      </Box>
    </Layout>
  )
}
