/**
 * WMS · Traslados entre almacenes
 *
 * Un traslado lleva varias líneas y genera un solo viaje del TMS. Al
 * despacharlo, la mercancía queda EN TRÁNSITO hacia el destino: sigue siendo
 * inventario, pero no se vende ni se alista hasta que el destino la recibe y
 * dice cuánto llegó. Lo que no llega sale como faltante (y en Finanzas, merma).
 */
import { useMemo, useState } from 'react'
import {
  Box, Typography, MenuItem, Button, Chip, Stack, Alert, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, IconButton, Table, TableHead, TableRow, TableCell, TableBody, ToggleButtonGroup, ToggleButton,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { LocalShipping, Add, Delete, Inventory } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import SugerenciaVehiculo from '@/components/tms/SugerenciaVehiculo'
import { BotonPDF } from '@/components/comun/BotonPDF'
import { Encabezado, TablaRegistros, Cifra, errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms, fechaHora, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'
import { type ItemEscaneado } from '@/components/wms/Escaner'
import { ArmadoEnvio } from '@/components/wms/ArmadoEnvio'
import { equivalencia, useNiveles } from '@/components/wms/empaques'

const COLOR = COLOR_MODULO

interface LineaT {
  id: number; producto_id: number; sku: string; producto: string; lote: string | null; cantidad: number
  cantidad_recibida: number | null; ubicacion_origen: string; ubicacion_destino_id: number | null; ubicacion_destino: string | null
}
interface Traslado {
  id: number; numero: string; estado: string; almacen_origen_id: number; almacen_origen: string; almacen_destino_id: number
  almacen_destino: string; tms_codigo: string | null; despachado_en: string; recibido_en: string | null; notas: string | null
  lineas: LineaT[]
}
interface Existencia {
  id: number; producto_id: number; ubicacion_id: number; lote_id: number | null; contenedor_id: number | null
  cantidad_disponible: number; producto?: { sku: string; nombre: string }; ubicacion?: { codigo: string }
  lote?: { numero_lote: string } | null
}
interface LineaNueva { existencia: Existencia | null; cantidad: string; destino: number | '' }

const traslados = (p: Record<string, unknown>) => api.get<Traslado[]>('/wms/traslados', { params: p }).then(r => r.data)

export default function WMSTraslados() {
  const qc = useQueryClient()
  const niveles = useNiveles()
  /** «24 und» → «2 cajas», para verificar los movimientos en empaques. */
  const eq = (pid: number, cantidad: number) => equivalencia(cantidad, niveles.get(pid))
  /** El empaque más grande que la cantidad completa exacto (24 → caja de 12); 1 si va en unidades. */
  const multiploDe = (pid: number, cantidad: number) =>
    Math.max(1, ...(niveles.get(pid) ?? []).filter(n => n.nivel !== 'UNIDAD' && cantidad % n.unidades === 0).map(n => n.unidades))
  const [estado, setEstado] = useState('EN_TRANSITO')
  const lista = useQuery({ queryKey: ['traslados', estado], queryFn: () => traslados(estado ? { estado } : {}) })
  const todos = useQuery({ queryKey: ['traslados', 'resumen'], queryFn: () => traslados({}) })
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const zonas = useQuery({ queryKey: ['wms-zonas'], queryFn: () => api.get<any[]>('/wms/zonas/').then(r => r.data) })
  const ubicaciones = useQuery({ queryKey: ['wms-ubicaciones'], queryFn: wms.ubicaciones })
  const [ver, setVer] = useState<Traslado | null>(null)
  const [nuevo, setNuevo] = useState(false)
  const [form, setForm] = useState({ origen: '' as number | '', destino: '' as number | '', tms: true, notas: '' })
  const [lineas, setLineas] = useState<LineaNueva[]>([{ existencia: null, cantidad: '', destino: '' }])
  const [recibo, setRecibo] = useState<Record<number, { cantidad: string; destino: number | '' }>>({})
  const [enviando, setEnviando] = useState(false)
  // Escaneo: lo que se va a enviar, por producto; luego se reparte por ubicación.
  const [escaneados, setEscaneados] = useState<ItemEscaneado[]>([])
  const [faltantes, setFaltantes] = useState<{ sku: string; nombre: string; solicitado: number; disponible: number }[]>([])
  const [asignando, setAsignando] = useState(false)
  // Lo que se armó por última vez (para saber si la lista cambió desde entonces).
  const [armadoDe, setArmadoDe] = useState('')
  const huella = (xs: ItemEscaneado[]) => JSON.stringify(xs.filter(x => x.cantidad > 0).map(x => [x.producto_id, x.cantidad]))

  const stock = useQuery({
    queryKey: ['wms-stock-almacen', form.origen], enabled: !!form.origen,
    queryFn: () => api.get<Existencia[]>('/wms/inventario/', { params: { almacen_id: form.origen } }).then(r => r.data),
  })
  // Ubicaciones guardables de un almacén: ni tránsito, ni recepción, ni despacho.
  const guardables = (almacenId?: number | '') => {
    const zs = new Map((zonas.data ?? []).map(z => [z.id, z]))
    return (ubicaciones.data ?? []).filter(u => {
      const z = zs.get(u.zona_id)
      return z && z.almacen_id === almacenId && !['TRANSITO', 'RECEPCION', 'DESPACHO'].includes(z.tipo)
    })
  }
  const destinoUbic = useMemo(() => guardables(form.destino), [form.destino, zonas.data, ubicaciones.data])  // eslint-disable-line react-hooks/exhaustive-deps
  const disponibles = (stock.data ?? []).filter(e => e.cantidad_disponible > 0)
  const enTransito = (todos.data ?? []).filter(t => t.estado === 'EN_TRANSITO')
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['traslados'] }); qc.invalidateQueries({ queryKey: ['wms-stock-almacen'] }) }

  const abrirNuevo = () => {
    setForm({ origen: almacenes.data?.[0]?.id ?? '', destino: almacenes.data?.[1]?.id ?? '', tms: true, notas: '' })
    setLineas([{ existencia: null, cantidad: '', destino: '' }]); setEscaneados([]); setFaltantes([]); setNuevo(true)
  }

  // Reparte lo escaneado entre las ubicaciones del origen (FEFO) y arma las líneas.
  const asignarEscaneo = async (): Promise<LineaNueva[]> => {
    const pedir = escaneados.filter(x => x.cantidad > 0)
    if (!form.origen || !pedir.length) return []
    setAsignando(true)
    try {
      const r = await api.post<{ lineas: { inventario_id: number | null; cantidad: number }[]; faltantes: typeof faltantes }>(
        '/wms/escaneo/asignar-origen',
        { almacen_id: form.origen, lineas: pedir.map(x => ({ producto_id: x.producto_id, cantidad: x.cantidad, multiplo: multiploDe(x.producto_id, x.cantidad) })) },
      ).then(x => x.data)
      const fresco = await stock.refetch()
      const existencias = new Map((fresco.data ?? []).map(e => [e.id, e]))
      const nuevas: LineaNueva[] = r.lineas
        .map(l => ({ existencia: (l.inventario_id && existencias.get(l.inventario_id)) || null, cantidad: String(l.cantidad), destino: '' as const }))
        .filter(l => l.existencia)
      setLineas(nuevas.length ? nuevas : [{ existencia: null, cantidad: '', destino: '' }])
      setFaltantes(r.faltantes)
      setArmadoDe(huella(escaneados))
      if (nuevas.length) toast.success(`${nuevas.length} movimiento(s) armados por ubicación`)
      if (r.faltantes.length) toast.error('Hay productos sin existencias suficientes en el origen')
      return nuevas
    } catch (e) { toast.error(errorApi(e)); return [] } finally { setAsignando(false) }
  }
  const crear = async () => {
    let fuente = lineas
    const sinMovimientos = !lineas.some(l => l.existencia && Number(l.cantidad) > 0)
    if (escaneados.some(x => x.cantidad > 0) && huella(escaneados) !== armadoDe) {
      // La lista cambió desde el último armado: se rearman los movimientos.
      fuente = await asignarEscaneo()
      if (!sinMovimientos) {
        toast('Se actualizaron los movimientos por ubicación. Revíselos y despache.', { icon: 'ℹ️' })
        return
      }
    }
    const validas = fuente.filter(l => l.existencia && Number(l.cantidad) > 0)
    if (!validas.length) { toast.error('Agregue al menos una línea con cantidad.'); return }
    setEnviando(true)
    try {
      const t = await api.post<Traslado>('/wms/traslados', {
        almacen_origen_id: form.origen, almacen_destino_id: form.destino, gestion_transporte: form.tms ? 'TMS' : 'NINGUNA',
        notas: form.notas || undefined,
        lineas: validas.map(l => ({
          producto_id: l.existencia!.producto_id, ubicacion_origen_id: l.existencia!.ubicacion_id, lote_id: l.existencia!.lote_id,
          contenedor_id: l.existencia!.contenedor_id, cantidad: Number(l.cantidad), ubicacion_destino_id: l.destino || undefined,
        })),
      }).then(r => r.data)
      toast.success(`Traslado ${t.numero} en tránsito${t.tms_codigo ? ` · viaje ${t.tms_codigo}` : ''}`)
      setNuevo(false); refrescar(); abrir(t)
    } catch (e) { toast.error(errorApi(e)) } finally { setEnviando(false) }
  }
  const abrir = (t: Traslado) => {
    setVer(t)
    setRecibo(Object.fromEntries(t.lineas.map(l => [l.id, { cantidad: String(l.cantidad), destino: l.ubicacion_destino_id ?? '' }])))
  }
  const recibir = async () => {
    if (!ver) return
    setEnviando(true)
    try {
      const t = await api.post<Traslado>(`/wms/traslados/${ver.id}/recibir`, {
        lineas: ver.lineas.map(l => ({ detalle_id: l.id, cantidad_recibida: Number(recibo[l.id]?.cantidad ?? l.cantidad),
                                       ubicacion_destino_id: recibo[l.id]?.destino || undefined })),
      }).then(r => r.data)
      const falta = t.lineas.reduce((s, l) => s + (l.cantidad - (l.cantidad_recibida ?? 0)), 0)
      toast.success(falta > 0 ? `Recibido con faltante de ${num(falta)} und (registrado como merma)` : 'Traslado recibido completo')
      setVer(t); refrescar()
    } catch (e) { toast.error(errorApi(e)) } finally { setEnviando(false) }
  }

  return (
    <Layout title="WMS — Traslados">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<LocalShipping sx={{ fontSize: 28 }} />} titulo="Traslados entre almacenes" color={COLOR}
          subtitulo="La mercancía viaja en tránsito, con un solo viaje del TMS, hasta que el destino la recibe"
          accion="Nuevo traslado" onAccion={abrirNuevo} />
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="En tránsito" valor={enTransito.length} color="#D97706" sub="Traslados sin recibir" /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Unidades en camino" color="#0369A1"
            valor={num(enTransito.reduce((s, t) => s + t.lineas.reduce((a, l) => a + l.cantidad, 0), 0))} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Recibidos" valor={(todos.data ?? []).filter(t => t.estado === 'RECIBIDO').length} color="#15803D" /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Con faltante" color="#DC2626"
            valor={(todos.data ?? []).filter(t => t.lineas.some(l => l.cantidad_recibida != null && l.cantidad_recibida < l.cantidad)).length} /></Grid>
        </Grid>
        <ToggleButtonGroup size="small" exclusive value={estado} onChange={(_, v) => v !== null && setEstado(v)} sx={{ mb: 1.5 }}>
          <ToggleButton value="EN_TRANSITO">En tránsito</ToggleButton>
          <ToggleButton value="RECIBIDO">Recibidos</ToggleButton>
          <ToggleButton value="">Todos</ToggleButton>
        </ToggleButtonGroup>
        <TablaRegistros filas={lista.data ?? []} cargando={lista.isLoading} vacio="Sin traslados" etiqueta={t => t.numero} onFila={abrir}
          columnas={[
            { titulo: 'Traslado', valor: t => <Typography fontFamily="monospace" fontWeight={700} fontSize={13}>{t.numero}</Typography> },
            { titulo: 'De', valor: t => t.almacen_origen },
            { titulo: 'A', valor: t => t.almacen_destino },
            { titulo: 'Líneas', valor: t => t.lineas.length, alinear: 'right' },
            { titulo: 'Unidades', valor: t => num(t.lineas.reduce((s, l) => s + l.cantidad, 0)), alinear: 'right' },
            { titulo: 'Viaje TMS', valor: t => t.tms_codigo ?? '—' },
            { titulo: 'Salió', valor: t => fechaHora(t.despachado_en) },
            { titulo: 'Estado', valor: t => <Chip size="small" label={t.estado === 'EN_TRANSITO' ? 'en tránsito' : 'recibido'}
              color={t.estado === 'EN_TRANSITO' ? 'warning' : 'success'} /> },
          ]} />
      </Box>

      <Dialog open={nuevo} onClose={() => setNuevo(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Nuevo traslado</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid size={{ xs: 12, md: 3 }}>
              <TextField select fullWidth size="small" label="Sale de" value={form.origen}
                onChange={e => { setForm(f => ({ ...f, origen: Number(e.target.value) })); setLineas([{ existencia: null, cantidad: '', destino: '' }]); setEscaneados([]); setFaltantes([]); setArmadoDe('') }}>
                {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, md: 3 }}>
              <TextField select fullWidth size="small" label="Va a" value={form.destino}
                onChange={e => setForm(f => ({ ...f, destino: Number(e.target.value) }))}>
                {(almacenes.data ?? []).filter(a => a.id !== form.origen).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, md: 2 }}>
              <TextField select fullWidth size="small" label="Transporte" value={form.tms ? 'TMS' : 'NINGUNA'}
                onChange={e => setForm(f => ({ ...f, tms: e.target.value === 'TMS' }))}>
                <MenuItem value="TMS">Programar viaje en TMS</MenuItem>
                <MenuItem value="NINGUNA">Lo gestiona otro</MenuItem>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              <TextField fullWidth size="small" label="Notas" value={form.notas} onChange={e => setForm(f => ({ ...f, notas: e.target.value }))} />
            </Grid>
          </Grid>
          <Box sx={{ mt: 2.5 }}>
            <ArmadoEnvio stock={stock.data ?? []} items={escaneados} onCambio={setEscaneados}
              cargando={stock.isLoading} sinOrigen={!form.origen} />
          </Box>
          {escaneados.length > 0 && (
            <Button variant="contained" size="small" sx={{ mt: 1.5, textTransform: 'none', fontWeight: 700 }}
              disabled={!form.origen || asignando} onClick={asignarEscaneo}>
              {asignando ? 'Asignando…' : huella(escaneados) === armadoDe ? 'Volver a armar movimientos' : 'Armar movimientos por ubicación (FEFO)'}
            </Button>
          )}
          {faltantes.length > 0 && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              Sin existencias suficientes en el origen: {faltantes.map(f => `${f.sku} (pidió ${num(f.solicitado)}, hay ${num(f.disponible)})`).join(' · ')}
            </Alert>
          )}
          {form.tms && (() => {
            const desdeLineas = lineas.filter(l => l.existencia && Number(l.cantidad) > 0)
              .map(l => ({ producto_id: l.existencia!.producto_id, cantidad: Number(l.cantidad) }))
            const carga = desdeLineas.length ? desdeLineas : escaneados.filter(x => x.cantidad > 0).map(x => ({ producto_id: x.producto_id, cantidad: x.cantidad }))
            return carga.length ? <Box sx={{ mt: 2 }}><SugerenciaVehiculo fuente={{ lineas: carga }} titulo="Carga del traslado y vehículo sugerido" /></Box> : null
          })()}
          <Typography fontWeight={700} sx={{ mt: 2.5 }}>Movimientos por ubicación</Typography>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1 }}>
            De dónde sale cada producto. Se arman solos desde la lista de arriba (primero lo que vence primero); también puede ajustarlos o agregarlos a mano.
          </Typography>
          {lineas.map((l, i) => (
            <Stack key={i} direction={{ xs: 'column', md: 'row' }} gap={1.5} mb={1.5} alignItems="center">
              <Autocomplete sx={{ flex: 3, width: '100%' }} size="small" options={disponibles} value={l.existencia}
                loading={stock.isLoading} noOptionsText={form.origen ? 'Sin existencias disponibles' : 'Elija el almacén de origen'}
                getOptionLabel={e => `${e.producto?.sku} · ${e.producto?.nombre} — ${e.ubicacion?.codigo}${e.lote ? ` · lote ${e.lote.numero_lote}` : ''} (${num(e.cantidad_disponible)} disp.)`}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                onChange={(_, v) => setLineas(ls => ls.map((x, j) => j === i ? { ...x, existencia: v, cantidad: v ? String(v.cantidad_disponible) : '' } : x))}
                renderInput={p => <TextField {...p} label="Producto y ubicación de origen" />} />
              <TextField sx={{ flex: 1, width: '100%' }} size="small" type="number" label="Cantidad" value={l.cantidad}
                error={!!l.existencia && Number(l.cantidad) > l.existencia.cantidad_disponible}
                helperText={l.existencia && Number(l.cantidad) > l.existencia.cantidad_disponible ? 'Más de lo disponible'
                  : l.existencia && eq(l.existencia.producto_id, Number(l.cantidad)) ? `= ${eq(l.existencia.producto_id, Number(l.cantidad))}` : undefined}
                onChange={e => setLineas(ls => ls.map((x, j) => j === i ? { ...x, cantidad: e.target.value } : x))} />
              <TextField select sx={{ flex: 1.5, width: '100%' }} size="small" label="Dónde se guardará (opcional)" value={l.destino}
                onChange={e => setLineas(ls => ls.map((x, j) => j === i ? { ...x, destino: Number(e.target.value) || '' } : x))}>
                <MenuItem value="">Se decide al recibir</MenuItem>
                {destinoUbic.map(u => <MenuItem key={u.id} value={u.id}>{u.codigo}</MenuItem>)}
              </TextField>
              <IconButton aria-label="Quitar línea" onClick={() => setLineas(ls => ls.length > 1 ? ls.filter((_, j) => j !== i) : ls)}><Delete /></IconButton>
            </Stack>
          ))}
          <Button startIcon={<Add />} onClick={() => setLineas(ls => [...ls, { existencia: null, cantidad: '', destino: '' }])}>Agregar línea</Button>
          <Alert severity="info" sx={{ mt: 2 }}>
            La mercancía sale ya del origen y queda en tránsito hacia el destino: no se podrá vender ni alistar allá hasta que se reciba.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNuevo(false)}>Cancelar</Button>
          <Button variant="contained" disabled={enviando || !form.origen || !form.destino} onClick={crear} sx={{ bgcolor: COLOR }}>Despachar traslado</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!ver} onClose={() => setVer(null)} maxWidth="md" fullWidth>
        {ver && <>
          <DialogTitle>
            Traslado {ver.numero} <Chip size="small" sx={{ ml: 1 }} label={ver.estado === 'EN_TRANSITO' ? 'en tránsito' : 'recibido'}
              color={ver.estado === 'EN_TRANSITO' ? 'warning' : 'success'} />
          </DialogTitle>
          <DialogContent>
            <Typography color="text.secondary" fontSize={14} mb={1.5}>
              {ver.almacen_origen} → {ver.almacen_destino}{ver.tms_codigo ? ` · viaje ${ver.tms_codigo}` : ''} · salió {fechaHora(ver.despachado_en)}
              {ver.recibido_en ? ` · recibido ${fechaHora(ver.recibido_en)}` : ''}{ver.notas ? ` · ${ver.notas}` : ''}
            </Typography>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>Producto</TableCell><TableCell>Lote</TableCell><TableCell>Salió de</TableCell>
                <TableCell align="right">Enviado</TableCell><TableCell align="right">Llegó</TableCell><TableCell>Se guarda en</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {ver.lineas.map(l => (
                  <TableRow key={l.id}>
                    <TableCell>{l.sku} · {l.producto}</TableCell>
                    <TableCell>{l.lote ?? '—'}</TableCell>
                    <TableCell>{l.ubicacion_origen}</TableCell>
                    <TableCell align="right">
                      {num(l.cantidad)}
                      {eq(l.producto_id, l.cantidad) && <Typography component="div" sx={{ fontSize: 11.5, color: COLOR, fontWeight: 600 }}>= {eq(l.producto_id, l.cantidad)}</Typography>}
                    </TableCell>
                    <TableCell align="right" sx={{ width: 120 }}>
                      {ver.estado === 'EN_TRANSITO'
                        ? <TextField size="small" type="number" value={recibo[l.id]?.cantidad ?? ''} inputProps={{ 'aria-label': `Llegó de ${l.sku}`, min: 0, max: l.cantidad }}
                            onChange={e => setRecibo(r => ({ ...r, [l.id]: { ...r[l.id], cantidad: e.target.value } }))} />
                        : <Box component="span" sx={{ color: (l.cantidad_recibida ?? 0) < l.cantidad ? '#DC2626' : undefined, fontWeight: 700 }}>{num(l.cantidad_recibida)}</Box>}
                    </TableCell>
                    <TableCell sx={{ minWidth: 170 }}>
                      {ver.estado === 'EN_TRANSITO'
                        ? <TextField select size="small" fullWidth value={recibo[l.id]?.destino ?? ''} inputProps={{ 'aria-label': `Ubicación de ${l.sku}` }}
                            onChange={e => setRecibo(r => ({ ...r, [l.id]: { ...r[l.id], destino: Number(e.target.value) || '' } }))}>
                            <MenuItem value="">Almacenamiento (automática)</MenuItem>
                            {guardables(ver.almacen_destino_id).map(u => <MenuItem key={u.id} value={u.id}>{u.codigo}</MenuItem>)}
                          </TextField>
                        : l.ubicacion_destino ?? '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {ver.estado === 'EN_TRANSITO' && <Alert severity="warning" icon={<Inventory />} sx={{ mt: 2 }}>
              Escriba lo que llegó de verdad. Lo que falte sale del tránsito como faltante y, si la mercancía es propia, Finanzas lo registra como merma.
            </Alert>}
          </DialogContent>
          <DialogActions>
            <BotonPDF tipo="traslado" id={ver.id} etiqueta="Traslado en PDF" />
            <Button onClick={() => setVer(null)}>Cerrar</Button>
            {ver.estado === 'EN_TRANSITO' && <Button variant="contained" disabled={enviando} onClick={recibir} sx={{ bgcolor: COLOR }}>Recibir en {ver.almacen_destino}</Button>}
          </DialogActions>
        </>}
      </Dialog>
    </Layout>
  )
}
