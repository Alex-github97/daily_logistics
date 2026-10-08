/**
 * POS · Configuración
 *
 * - Cajas: de qué almacén vende, con qué lista de precios, con qué resolución
 *   DIAN numera y cuánto descuento puede dar el cajero.
 * - Listas y precios: precio al público (IVA incluido) por producto, con el
 *   código de barras y la tarifa de IVA del producto y el margen sobre el costo
 *   promedio del inventario.
 * - Zonas vendibles: qué zonas de cada almacén puede vender el POS (recepción,
 *   cuarentena y despacho no).
 * - Resoluciones de facturación DIAN: prefijo, rango, vigencia y clave técnica.
 */
import { useEffect, useState } from 'react'
import {
  Box, Tabs, Tab, Switch, Button, MenuItem, Typography, Alert, Chip,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { Settings, Save, Add } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { apiClient } from '@/api/client'
import { pos, pesos } from '@/api/pos'
import { Encabezado, TablaRegistros, FormularioRegistro, errorApi, type Campo } from '@/components/comun/Registro'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO

function Cajas() {
  const qc = useQueryClient()
  const cajas = useQuery({ queryKey: ['pos', 'cajas'], queryFn: pos.cajas })
  const listas = useQuery({ queryKey: ['pos', 'listas'], queryFn: pos.listas })
  const res = useQuery({ queryKey: ['pos', 'resoluciones'], queryFn: pos.resoluciones })
  const almacenes = useQuery({ queryKey: ['wms', 'almacenes'], queryFn: () => apiClient.get('/wms/almacenes/').then(r => r.data) })
  const [dlg, setDlg] = useState<{ abierto: boolean; r: any }>({ abierto: false, r: null })
  const campos: Campo[] = [
    { clave: 'codigo', etiqueta: 'Código', obligatorio: true, ancho: 4 },
    { clave: 'nombre', etiqueta: 'Nombre', obligatorio: true, ancho: 8 },
    { clave: 'almacen_id', etiqueta: 'Almacén del que vende', tipo: 'seleccion', obligatorio: true, ancho: 6,
      opciones: (almacenes.data ?? []).map((a: any) => [a.id, a.nombre] as [number, string]) },
    { clave: 'lista_id', etiqueta: 'Lista de precios', tipo: 'seleccion', obligatorio: true, ancho: 6,
      opciones: (listas.data ?? []).map(l => [l.id, l.nombre] as [number, string]) },
    { clave: 'resolucion_id', etiqueta: 'Resolución de facturación', tipo: 'seleccion', ancho: 8,
      opciones: (res.data ?? []).filter(r => r.tipo_documento !== 'NOTA_CREDITO').map(r => [r.id, `${r.prefijo} ${r.desde}–${r.hasta} · ${r.numero_resolucion}`] as [number, string]),
      ayuda: 'Sin resolución la caja no puede facturar' },
    { clave: 'descuento_maximo', etiqueta: 'Descuento máximo del cajero (%)', tipo: 'numero', min: 0, max: 100, ancho: 4 },
    { clave: 'activa', etiqueta: 'Activa', tipo: 'interruptor' },
  ]
  const guardar = async (c: any) => {
    if (dlg.r) await pos.editarCaja(dlg.r.id, c); else await pos.crearCaja(c)
    toast.success('Caja guardada'); qc.invalidateQueries({ queryKey: ['pos'] })
  }
  return <>
    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}><Button startIcon={<Add />} variant="contained" sx={{ bgcolor: COLOR }} onClick={() => setDlg({ abierto: true, r: null })}>Nueva caja</Button></Box>
    <TablaRegistros filas={cajas.data ?? []} cargando={cajas.isLoading} vacio="Sin cajas" etiqueta={(c: any) => c.nombre}
      onEditar={(c: any) => setDlg({ abierto: true, r: c })}
      columnas={[
        { titulo: 'Código', valor: (c: any) => c.codigo }, { titulo: 'Caja', valor: (c: any) => c.nombre },
        { titulo: 'Almacén', valor: (c: any) => c.almacen_nombre },
        { titulo: 'Zonas vendibles', valor: (c: any) => c.zonas_vendibles ? `${c.zonas_vendibles} ubicaciones` : <Chip size="small" color="warning" label="Ninguna" /> },
        { titulo: 'Lista', valor: (c: any) => c.lista_nombre }, { titulo: 'Resolución', valor: (c: any) => c.resolucion ?? <Chip size="small" color="warning" label="Sin resolución" /> },
        { titulo: 'Dto. máx.', valor: (c: any) => `${c.descuento_maximo}%` },
        { titulo: 'Turno', valor: (c: any) => c.turno_abierto ? `Abierto · ${c.turno_abierto.cajero}` : 'Cerrada' },
      ]} />
    <FormularioRegistro abierto={dlg.abierto} titulo={dlg.r ? 'Editar caja' : 'Nueva caja'} campos={campos} registro={dlg.r}
      valoresIniciales={{ activa: true, descuento_maximo: 0 }} onGuardar={guardar} onCerrar={() => setDlg({ abierto: false, r: null })} />
  </>
}

function Precios() {
  const qc = useQueryClient()
  const listas = useQuery({ queryKey: ['pos', 'listas'], queryFn: pos.listas })
  const [lista, setLista] = useState<number | ''>('')
  const [q, setQ] = useState('')
  const filas = useQuery({ queryKey: ['pos', 'precios', lista, q], enabled: !!lista, queryFn: () => pos.precios(Number(lista), q || undefined) })
  const [edicion, setEdicion] = useState<Record<number, any>>({})
  const [nueva, setNueva] = useState(false)
  useEffect(() => { if (!lista && listas.data?.length) setLista(listas.data[0].id) }, [listas.data, lista])
  const valor = (f: any, k: string) => edicion[f.producto_id]?.[k] ?? (f[k] ?? '')
  const poner = (f: any, k: string, v: string) => setEdicion(e => ({ ...e, [f.producto_id]: { ...(e[f.producto_id] ?? {}), [k]: v } }))
  const guardar = async () => {
    try {
      const cambios = Object.entries(edicion)
      const precios = cambios.filter(([, c]) => 'precio' in c).map(([id, c]) => ({ producto_id: Number(id), precio: c.precio === '' ? null : Number(c.precio) }))
      if (precios.length) await pos.guardarPrecios(Number(lista), precios)
      for (const [id, c] of cambios.filter(([, c]) => 'codigo_barras' in c || 'tarifa_iva' in c)) {
        const f = filas.data!.find(x => x.producto_id === Number(id))
        await pos.productoPOS(Number(id), { codigo_barras: (c.codigo_barras ?? f.codigo_barras) || null, tarifa_iva: Number(c.tarifa_iva ?? f.tarifa_iva) })
      }
      toast.success('Precios guardados'); setEdicion({}); qc.invalidateQueries({ queryKey: ['pos'] })
    } catch (e) { toast.error(errorApi(e)) }
  }
  return <>
    <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
      <TextField select size="small" label="Lista de precios" value={lista} onChange={e => { setLista(Number(e.target.value)); setEdicion({}) }} sx={{ minWidth: 240 }}>
        {(listas.data ?? []).map(l => <MenuItem key={l.id} value={l.id}>{l.nombre} ({l.productos})</MenuItem>)}
      </TextField>
      <Button size="small" startIcon={<Add />} onClick={() => setNueva(true)}>Nueva lista</Button>
      <TextField size="small" label="Buscar producto" value={q} onChange={e => setQ(e.target.value)} />
      <Box sx={{ flex: 1 }} />
      <Button variant="contained" startIcon={<Save />} disabled={!Object.keys(edicion).length} onClick={guardar} sx={{ bgcolor: COLOR }}>
        Guardar {Object.keys(edicion).length || ''} cambio(s)</Button>
    </Box>
    <Typography sx={{ fontSize: 12, color: 'text.secondary', mb: 1 }}>Precio al público con IVA incluido. Vacío = no se vende en esta lista. El margen es sobre el costo promedio del inventario.</Typography>
    <TablaRegistros filas={(filas.data ?? []).map(f => ({ ...f, id: f.producto_id }))} cargando={filas.isLoading} vacio="Sin productos en el WMS" etiqueta={(f: any) => f.nombre}
      columnas={[
        { titulo: 'SKU', valor: (f: any) => f.sku }, { titulo: 'Producto', valor: (f: any) => f.nombre },
        { titulo: 'Código de barras', valor: (f: any) => <TextField size="small" value={valor(f, 'codigo_barras')} onChange={e => poner(f, 'codigo_barras', e.target.value)} sx={{ width: 150 }} inputProps={{ 'aria-label': `Código de barras ${f.nombre}` }} /> },
        { titulo: 'IVA %', valor: (f: any) => <TextField select size="small" value={String(valor(f, 'tarifa_iva'))} onChange={e => poner(f, 'tarifa_iva', e.target.value)} sx={{ width: 90 }}>
          {['0', '5', '19'].map(v => <MenuItem key={v} value={v}>{v}%</MenuItem>)}</TextField> },
        { titulo: 'Costo promedio', valor: (f: any) => pesos(f.costo_promedio), alinear: 'right' },
        { titulo: 'Precio', valor: (f: any) => <TextField size="small" type="number" value={valor(f, 'precio')} onChange={e => poner(f, 'precio', e.target.value)} sx={{ width: 120 }} inputProps={{ 'aria-label': `Precio ${f.nombre}` }} /> },
        { titulo: 'Margen', valor: (f: any) => f.margen_pct == null ? '—' : <Box sx={{ color: f.margen_pct < 10 ? '#DC2626' : '#15803D', fontWeight: 700 }}>{f.margen_pct}%</Box>, alinear: 'right' },
      ]} />
    <FormularioRegistro abierto={nueva} titulo="Nueva lista de precios" campos={[{ clave: 'nombre', etiqueta: 'Nombre', obligatorio: true }, { clave: 'descripcion', etiqueta: 'Para qué es', tipo: 'area' }, { clave: 'activa', etiqueta: 'Activa', tipo: 'interruptor' }]}
      valoresIniciales={{ activa: true }} onGuardar={async c => { const l = await pos.crearLista(c); toast.success('Lista creada'); await qc.invalidateQueries({ queryKey: ['pos', 'listas'] }); setLista(l.id) }}
      onCerrar={() => setNueva(false)} />
  </>
}

function Zonas() {
  const qc = useQueryClient()
  const zonas = useQuery({ queryKey: ['pos', 'zonas'], queryFn: pos.zonas })
  const marcar = async (z: any, v: boolean) => {
    try { await pos.marcarZona(z.id, v); qc.invalidateQueries({ queryKey: ['pos'] }) } catch (e) { toast.error(errorApi(e)) }
  }
  return <>
    <Alert severity="info" sx={{ mb: 2 }}>El POS de un almacén solo vende lo que está en sus zonas vendibles. Recepción, cuarentena y despacho nunca se venden.</Alert>
    <TablaRegistros filas={zonas.data ?? []} cargando={zonas.isLoading} vacio="Sin zonas en el WMS" etiqueta={(z: any) => z.nombre}
      columnas={[
        { titulo: 'Almacén', valor: (z: any) => z.almacen_nombre }, { titulo: 'Código', valor: (z: any) => z.codigo },
        { titulo: 'Zona', valor: (z: any) => z.nombre }, { titulo: 'Tipo', valor: (z: any) => z.tipo },
        { titulo: 'Se vende en el POS', valor: (z: any) => <Switch checked={!!z.vendible_pos} onChange={e => marcar(z, e.target.checked)}
          disabled={['RECEPCION', 'CUARENTENA', 'DESPACHO'].includes((z.tipo ?? '').toUpperCase())} inputProps={{ 'aria-label': `Vendible ${z.nombre}` }} /> },
      ]} />
  </>
}

function Resoluciones() {
  const qc = useQueryClient()
  const res = useQuery({ queryKey: ['pos', 'resoluciones'], queryFn: pos.resoluciones })
  const [dlg, setDlg] = useState<{ abierto: boolean; r: any }>({ abierto: false, r: null })
  const campos: Campo[] = [
    { clave: 'tipo_documento', etiqueta: 'Documento', tipo: 'seleccion', obligatorio: true, ancho: 6,
      opciones: [['POS', 'Documento equivalente POS electrónico'], ['FACTURA_VENTA', 'Factura electrónica de venta'], ['NOTA_CREDITO', 'Notas crédito']] },
    { clave: 'numero_resolucion', etiqueta: 'Número de la resolución DIAN', obligatorio: true, ancho: 6 },
    { clave: 'fecha_resolucion', etiqueta: 'Fecha de la resolución', tipo: 'fecha', obligatorio: true, ancho: 4 },
    { clave: 'prefijo', etiqueta: 'Prefijo', obligatorio: true, ancho: 4 },
    { clave: 'ambiente', etiqueta: 'Ambiente', tipo: 'seleccion', obligatorio: true, ancho: 4, opciones: [['2', 'Pruebas (habilitación)'], ['1', 'Producción']] },
    { clave: 'desde', etiqueta: 'Desde el número', tipo: 'numero', min: 1, obligatorio: true, ancho: 6 },
    { clave: 'hasta', etiqueta: 'Hasta el número', tipo: 'numero', min: 1, obligatorio: true, ancho: 6 },
    { clave: 'vigencia_desde', etiqueta: 'Vigente desde', tipo: 'fecha', obligatorio: true, ancho: 6 },
    { clave: 'vigencia_hasta', etiqueta: 'Vigente hasta', tipo: 'fecha', obligatorio: true, ancho: 6 },
    { clave: 'clave_tecnica', etiqueta: 'Clave técnica (factura) o PIN del software (POS)', ayuda: 'La entrega la DIAN; entra al cálculo del CUFE' },
    { clave: 'aviso_restantes', etiqueta: 'Avisar cuando queden (números)', tipo: 'numero', min: 0, ancho: 6 },
    { clave: 'activa', etiqueta: 'Activa', tipo: 'interruptor' },
  ]
  const guardar = async (c: any) => {
    if (dlg.r) await pos.editarResolucion(dlg.r.id, c); else await pos.crearResolucion(c)
    toast.success('Resolución guardada'); qc.invalidateQueries({ queryKey: ['pos'] })
  }
  return <>
    <Alert severity="warning" sx={{ mb: 2 }}>
      La numeración y el CUFE se generan con la fórmula de la DIAN, pero los documentos todavía no se transmiten: quedan «por transmitir»
      hasta conectar un proveedor tecnológico de facturación electrónica.
    </Alert>
    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}><Button startIcon={<Add />} variant="contained" sx={{ bgcolor: COLOR }} onClick={() => setDlg({ abierto: true, r: null })}>Nueva resolución</Button></Box>
    <TablaRegistros filas={res.data ?? []} cargando={res.isLoading} vacio="Sin resoluciones registradas" etiqueta={(r: any) => r.numero_resolucion}
      onEditar={(r: any) => setDlg({ abierto: true, r })}
      columnas={[
        { titulo: 'Documento', valor: (r: any) => r.tipo_documento }, { titulo: 'Resolución', valor: (r: any) => r.numero_resolucion },
        { titulo: 'Rango', valor: (r: any) => `${r.prefijo}${r.desde} – ${r.prefijo}${r.hasta}` },
        { titulo: 'Siguiente', valor: (r: any) => r.siguiente ?? 'Agotada' }, { titulo: 'Quedan', valor: (r: any) => r.restantes, alinear: 'right' },
        { titulo: 'Vigencia', valor: (r: any) => `${r.vigencia_desde} a ${r.vigencia_hasta}` },
        { titulo: 'Ambiente', valor: (r: any) => r.ambiente === '1' ? 'Producción' : 'Pruebas' },
        { titulo: 'Estado', valor: (r: any) => <Chip size="small" color={r.vigente ? (r.alerta ? 'warning' : 'success') : 'error'}
          label={r.vigente ? (r.alerta ? 'Por vencer o agotarse' : 'Vigente') : 'No vigente'} /> },
      ]} />
    <FormularioRegistro abierto={dlg.abierto} titulo={dlg.r ? 'Editar resolución' : 'Nueva resolución de facturación'} campos={campos} registro={dlg.r} ancho="md"
      valoresIniciales={{ tipo_documento: 'POS', ambiente: '2', activa: true, aviso_restantes: 100 }}
      onGuardar={guardar} onCerrar={() => setDlg({ abierto: false, r: null })} />
  </>
}

export default function POSConfig() {
  const [tab, setTab] = useState(0)
  return (
    <Layout>
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Settings sx={{ fontSize: 28 }} />} titulo="Configuración del POS" subtitulo="Cajas, precios, zonas vendibles y resoluciones DIAN" color={COLOR} />
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="Cajas" /><Tab label="Listas y precios" /><Tab label="Zonas vendibles" /><Tab label="Resoluciones DIAN" />
        </Tabs>
        {tab === 0 && <Cajas />}
        {tab === 1 && <Precios />}
        {tab === 2 && <Zonas />}
        {tab === 3 && <Resoluciones />}
      </Box>
    </Layout>
  )
}
