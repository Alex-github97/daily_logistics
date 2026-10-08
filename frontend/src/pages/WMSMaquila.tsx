/**
 * WMS · Maquila (servicios de valor agregado)
 *
 * Recetas de kits, reempaque, etiquetado y desarme; órdenes que reservan sus
 * componentes, los consumen al terminar y producen el resultado con su costo;
 * cuánto se puede hacer con lo que hay contra lo que piden las órdenes; y el
 * resumen por depositante para facturar el servicio.
 */
import { useEffect, useState } from 'react'
import {
  Box, Typography, MenuItem, Button, Chip, Stack, Alert, Tabs, Tab, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, IconButton,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { Handyman, Add, Delete, PlayArrow, Done, Close } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, errorApi } from '@/components/comun/Registro'
import { sug } from '@/api/wmsSugerencias'
import { wms, fechaHora, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const TIPOS: Record<string, string> = { KIT: 'Armar kit', REEMPAQUE: 'Reempaque', ETIQUETADO: 'Etiquetado', DESARME: 'Desarme' }
const pesos = (v?: number | null) => v == null ? '—' : v.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })

function Ordenes({ almacen }: { almacen: number }) {
  const qc = useQueryClient()
  const ordenes = useQuery({ queryKey: ['maq-ordenes', almacen], queryFn: () => sug.ordenesMaquila({ almacen_id: almacen }) })
  const recetas = useQuery({ queryKey: ['maq-recetas'], queryFn: sug.recetas })
  const [nueva, setNueva] = useState<{ receta: any | null; cantidad: string }>({ receta: null, cantidad: '' })
  const [abrir, setAbrir] = useState(false)
  const posible = useQuery({ queryKey: ['maq-posible', nueva.receta?.id, almacen], enabled: !!nueva.receta, queryFn: () => sug.posible(nueva.receta.id, almacen) })
  const [terminar, setTerminar] = useState<any | null>(null)
  const [fin, setFin] = useState({ cantidad: '', ubicacion: '' })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['maq-ordenes'] })
  const accion = async (f: () => Promise<unknown>, ok: string) => { try { await f(); toast.success(ok); refrescar() } catch (e) { toast.error(errorApi(e)) } }
  return <>
    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}><Button variant="contained" startIcon={<Add />} sx={{ bgcolor: COLOR }} onClick={() => setAbrir(true)}>Nueva orden</Button></Box>
    <TablaRegistros filas={ordenes.data ?? []} cargando={ordenes.isLoading} vacio="Sin órdenes de maquila" etiqueta={(o: any) => o.numero}
      extra={(o: any) => <>
        {o.estado === 'PLANEADA' && <Button size="small" startIcon={<PlayArrow />} onClick={() => accion(() => sug.iniciarMaquila(o.id), 'Componentes reservados: orden en proceso')}>Iniciar</Button>}
        {o.estado === 'EN_PROCESO' && <Button size="small" startIcon={<Done />} onClick={() => { setTerminar(o); setFin({ cantidad: String(o.cantidad_plan), ubicacion: '' }) }}>Terminar</Button>}
        {['PLANEADA', 'EN_PROCESO'].includes(o.estado) && <Button size="small" color="inherit" startIcon={<Close />} onClick={() => accion(() => sug.cancelarMaquila(o.id), 'Orden cancelada; reservas liberadas')}>Cancelar</Button>}
      </>}
      columnas={[
        { titulo: 'Orden', valor: (o: any) => <Typography fontFamily="monospace" fontWeight={700} fontSize={13}>{o.numero}</Typography> },
        { titulo: 'Receta', valor: (o: any) => <>{o.receta} <Chip size="small" label={TIPOS[o.tipo] ?? o.tipo} sx={{ height: 18, fontSize: 10 }} /></> },
        { titulo: 'Plan', valor: (o: any) => num(o.cantidad_plan), alinear: 'right' }, { titulo: 'Hecho', valor: (o: any) => num(o.cantidad_hecha), alinear: 'right' },
        { titulo: 'Estado', valor: (o: any) => <Chip size="small" label={o.estado.toLowerCase()} color={o.estado === 'TERMINADA' ? 'success' : o.estado === 'EN_PROCESO' ? 'info' : 'default'} /> },
        { titulo: 'Costo unitario', valor: (o: any) => pesos(o.costo_unitario), alinear: 'right' },
        { titulo: 'Min. estándar / reales', valor: (o: any) => `${num(o.minutos_estandar)} / ${num(o.minutos_reales)}` },
        { titulo: 'Destino', valor: (o: any) => o.ubicacion_destino ?? '' }, { titulo: 'Creada', valor: (o: any) => fechaHora(o.creada) },
      ]} />
    <Dialog open={abrir} onClose={() => setAbrir(false)} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Nueva orden de maquila</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
        <Autocomplete size="small" options={(recetas.data ?? []).filter(r => r.activo)} value={nueva.receta} onChange={(_, v) => setNueva({ ...nueva, receta: v })}
          getOptionLabel={(r: any) => `${r.codigo} · ${r.nombre}`} renderInput={p => <TextField {...p} label="Receta" />} />
        {posible.data && <Alert severity={posible.data.maximo ? 'info' : 'warning'}>
          Con lo disponible se pueden hacer <b>{posible.data.maximo}</b>
          {posible.data.cuello_de_botella ? ` (limita el componente ${posible.data.cuello_de_botella.producto_id}: hay ${num(posible.data.cuello_de_botella.disponible)})` : ''}.
          {posible.data.demanda_pendiente != null && <> Las órdenes piden {num(posible.data.demanda_pendiente)} y hay {num(posible.data.existencia_resultado)}: se sugieren <b>{posible.data.sugerido}</b>.</>}
          {!!posible.data.sugerido && <Button size="small" sx={{ ml: 1 }} onClick={() => setNueva({ ...nueva, cantidad: String(posible.data.sugerido) })}>Usar</Button>}
        </Alert>}
        <TextField size="small" type="number" label="Cantidad a producir" value={nueva.cantidad} onChange={e => setNueva({ ...nueva, cantidad: e.target.value })} />
      </DialogContent>
      <DialogActions><Button color="inherit" onClick={() => setAbrir(false)}>Cancelar</Button>
        <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!nueva.receta || !(Number(nueva.cantidad) > 0)} onClick={async () => {
          try { const o = await sug.crearOrdenMaquila({ receta_id: nueva.receta.id, almacen_id: almacen, cantidad: Number(nueva.cantidad) })
            toast.success(`Orden ${o.numero} planeada`); setAbrir(false); setNueva({ receta: null, cantidad: '' }); refrescar() } catch (e) { toast.error(errorApi(e)) }
        }}>Crear</Button></DialogActions>
    </Dialog>
    <Dialog open={!!terminar} onClose={() => setTerminar(null)} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Terminar {terminar?.numero}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
        <TextField size="small" type="number" label={`Cantidad hecha (plan ${num(terminar?.cantidad_plan)})`} value={fin.cantidad} onChange={e => setFin({ ...fin, cantidad: e.target.value })}
          helperText="Si se hizo menos, lo que no se usó vuelve a estar disponible" />
        <TextField size="small" label="Escanee dónde queda lo producido" value={fin.ubicacion} onChange={e => setFin({ ...fin, ubicacion: e.target.value })} />
      </DialogContent>
      <DialogActions><Button color="inherit" onClick={() => setTerminar(null)}>Volver</Button>
        <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!(Number(fin.cantidad) > 0) || !fin.ubicacion.trim()} onClick={async () => {
          try { const o = await sug.terminarMaquila(terminar.id, { cantidad_hecha: Number(fin.cantidad), ubicacion_codigo: fin.ubicacion.trim() })
            toast.success(`Terminada: ${num(o.cantidad_hecha)} a ${pesos(o.costo_unitario)} c/u`); setTerminar(null); refrescar() } catch (e) { toast.error(errorApi(e)) }
        }}>Terminar</Button></DialogActions>
    </Dialog>
  </>
}

function Recetas() {
  const qc = useQueryClient()
  const recetas = useQuery({ queryKey: ['maq-recetas'], queryFn: sug.recetas })
  const productos = useQuery({ queryKey: ['wms-productos-lista'], queryFn: wms.productos })
  const vacia = { id: null as number | null, codigo: '', nombre: '', tipo: 'KIT', resultado: null as any, minutos_por_unidad: '0', costo_mano_obra_unidad: '0', instrucciones: '', activo: true,
    componentes: [] as { producto: any | null; cantidad: string }[] }
  const [f, setF] = useState<typeof vacia | null>(null)
  const abrir = (r?: any) => setF(r ? { id: r.id, codigo: r.codigo, nombre: r.nombre, tipo: r.tipo, activo: r.activo, instrucciones: r.instrucciones ?? '',
    resultado: (productos.data ?? []).find(p => p.id === r.producto_resultado_id) ?? null, minutos_por_unidad: String(r.minutos_por_unidad),
    costo_mano_obra_unidad: String(r.costo_mano_obra_unidad),
    componentes: r.componentes.map((c: any) => ({ producto: (productos.data ?? []).find(p => p.id === c.producto_id) ?? null, cantidad: String(c.cantidad) })) } : { ...vacia, componentes: [{ producto: null, cantidad: '1' }] })
  const guardar = async () => {
    const d = { codigo: f!.codigo, nombre: f!.nombre, tipo: f!.tipo, producto_resultado_id: f!.resultado?.id, activo: f!.activo,
      minutos_por_unidad: Number(f!.minutos_por_unidad), costo_mano_obra_unidad: Number(f!.costo_mano_obra_unidad), instrucciones: f!.instrucciones || null,
      componentes: f!.componentes.filter(c => c.producto).map(c => ({ producto_id: c.producto.id, cantidad: Number(c.cantidad) })) }
    try { if (f!.id) await sug.editarReceta(f!.id, d); else await sug.crearReceta(d); toast.success('Receta guardada'); setF(null); qc.invalidateQueries({ queryKey: ['maq-recetas'] }) }
    catch (e) { toast.error(errorApi(e)) }
  }
  const etiquetaProd = (p: any) => `${p.sku} · ${p.nombre}`
  return <>
    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}><Button variant="contained" startIcon={<Add />} sx={{ bgcolor: COLOR }} onClick={() => abrir()}>Nueva receta</Button></Box>
    <TablaRegistros filas={recetas.data ?? []} cargando={recetas.isLoading} vacio="Sin recetas" etiqueta={(r: any) => r.codigo} onEditar={abrir}
      columnas={[
        { titulo: 'Código', valor: (r: any) => r.codigo }, { titulo: 'Receta', valor: (r: any) => r.nombre },
        { titulo: 'Tipo', valor: (r: any) => TIPOS[r.tipo] ?? r.tipo }, { titulo: 'Resultado', valor: (r: any) => r.resultado_sku },
        { titulo: 'Componentes', valor: (r: any) => r.componentes.map((c: any) => `${c.sku} × ${num(c.cantidad)}`).join(', ') },
        { titulo: 'Min./und', valor: (r: any) => num(r.minutos_por_unidad), alinear: 'right' },
        { titulo: 'Mano de obra/und', valor: (r: any) => pesos(r.costo_mano_obra_unidad), alinear: 'right' },
        { titulo: 'Costo estándar/und', valor: (r: any) => pesos(r.costo_estandar_unidad), alinear: 'right' },
      ]} />
    <Dialog open={!!f} onClose={() => setF(null)} maxWidth="md" fullWidth>
      {f && <>
        <DialogTitle sx={{ fontWeight: 700 }}>{f.id ? 'Editar receta' : 'Nueva receta'}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
          <Stack direction="row" gap={1.5}>
            <TextField size="small" label="Código" value={f.codigo} onChange={e => setF({ ...f, codigo: e.target.value })} sx={{ width: 160 }} />
            <TextField size="small" label="Nombre" value={f.nombre} onChange={e => setF({ ...f, nombre: e.target.value })} sx={{ flex: 1 }} />
            <TextField select size="small" label="Tipo" value={f.tipo} onChange={e => setF({ ...f, tipo: e.target.value })} sx={{ width: 170 }}>
              {Object.entries(TIPOS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
            </TextField>
          </Stack>
          <Autocomplete size="small" options={productos.data ?? []} value={f.resultado} onChange={(_, v) => setF({ ...f, resultado: v })} getOptionLabel={etiquetaProd}
            renderInput={p => <TextField {...p} label={f.tipo === 'DESARME' ? 'Producto que se desarma' : 'Producto resultante'} />} />
          <Typography fontSize={13} fontWeight={700}>{f.tipo === 'DESARME' ? 'Lo que sale de cada unidad' : 'Componentes por unidad'}</Typography>
          {f.componentes.map((c, i) => (
            <Stack key={i} direction="row" gap={1} alignItems="center">
              <Autocomplete size="small" sx={{ flex: 1 }} options={productos.data ?? []} value={c.producto} getOptionLabel={etiquetaProd}
                onChange={(_, v) => setF({ ...f, componentes: f.componentes.map((x, j) => j === i ? { ...x, producto: v } : x) })} renderInput={p => <TextField {...p} label="Componente" />} />
              <TextField size="small" type="number" label="Cantidad" value={c.cantidad} sx={{ width: 120 }}
                onChange={e => setF({ ...f, componentes: f.componentes.map((x, j) => j === i ? { ...x, cantidad: e.target.value } : x) })} />
              <IconButton size="small" aria-label="Quitar componente" onClick={() => setF({ ...f, componentes: f.componentes.filter((_, j) => j !== i) })}><Delete fontSize="small" /></IconButton>
            </Stack>
          ))}
          <Button size="small" startIcon={<Add />} sx={{ alignSelf: 'flex-start' }} onClick={() => setF({ ...f, componentes: [...f.componentes, { producto: null, cantidad: '1' }] })}>Agregar componente</Button>
          <Stack direction="row" gap={1.5}>
            <TextField size="small" type="number" label="Minutos estándar por unidad" value={f.minutos_por_unidad} onChange={e => setF({ ...f, minutos_por_unidad: e.target.value })} />
            <TextField size="small" type="number" label="Mano de obra por unidad" value={f.costo_mano_obra_unidad} onChange={e => setF({ ...f, costo_mano_obra_unidad: e.target.value })} />
          </Stack>
          <TextField size="small" multiline minRows={2} label="Instrucciones" value={f.instrucciones} onChange={e => setF({ ...f, instrucciones: e.target.value })} />
        </DialogContent>
        <DialogActions><Button color="inherit" onClick={() => setF(null)}>Cancelar</Button>
          <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!f.codigo || !f.nombre || !f.resultado || !f.componentes.some(c => c.producto)} onClick={guardar}>Guardar</Button></DialogActions>
      </>}
    </Dialog>
  </>
}

function Resumen({ almacen }: { almacen: number }) {
  const hoy = new Date()
  const [desde, setDesde] = useState(new Date(hoy.getFullYear(), hoy.getMonth(), 1).toLocaleDateString('en-CA'))
  const [hasta, setHasta] = useState(hoy.toLocaleDateString('en-CA'))
  const r = useQuery({ queryKey: ['maq-resumen', almacen, desde, hasta], queryFn: () => sug.resumenMaquila({ almacen_id: almacen, desde, hasta }) })
  return <>
    <Stack direction="row" gap={1.5} mb={2}>
      <TextField size="small" type="date" label="Desde" value={desde} onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }} />
      <TextField size="small" type="date" label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }} />
    </Stack>
    <TablaRegistros filas={(r.data ?? []).map((x: any, i: number) => ({ ...x, id: i + 1 }))} cargando={r.isLoading} vacio="Sin maquila terminada en el periodo" etiqueta={(x: any) => x.depositante}
      columnas={[
        { titulo: 'Depositante', valor: (x: any) => x.depositante }, { titulo: 'Órdenes', valor: (x: any) => x.ordenes, alinear: 'right' },
        { titulo: 'Unidades', valor: (x: any) => num(x.unidades), alinear: 'right' },
        { titulo: 'Minutos estándar', valor: (x: any) => num(x.minutos_estandar), alinear: 'right' },
        { titulo: 'Minutos reales', valor: (x: any) => num(x.minutos_reales), alinear: 'right' },
        { titulo: 'Eficiencia', valor: (x: any) => x.eficiencia_pct == null ? '—' : `${x.eficiencia_pct}%`, alinear: 'right' },
        { titulo: 'Mano de obra a facturar', valor: (x: any) => pesos(x.mano_obra), alinear: 'right' },
      ]} />
  </>
}

export default function WMSMaquila() {
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const [tab, setTab] = useState(0)
  return (
    <Layout title="WMS — Maquila">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Handyman sx={{ fontSize: 28 }} />} titulo="Maquila" color={COLOR} subtitulo="Kits, reempaque, etiquetado y desarme con su consumo y su costo" />
        <Stack direction="row" gap={1.5} mb={2}>
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(Number(e.target.value))} sx={{ minWidth: 240 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
        </Stack>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Órdenes" /><Tab label="Recetas" /><Tab label="Resumen por depositante" /></Tabs>
        {!!almacen && tab === 0 && <Ordenes almacen={Number(almacen)} />}
        {tab === 1 && <Recetas />}
        {!!almacen && tab === 2 && <Resumen almacen={Number(almacen)} />}
      </Box>
    </Layout>
  )
}
