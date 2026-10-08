/**
 * WMS · Ubicación inteligente (slotting)
 *
 * Clasificación ABC por líneas alistadas, el recorrido de la bodega con las
 * ubicaciones preferentes (frente del recorrido, niveles de la cintura al
 * pecho) y las reubicaciones sugeridas: acercar lo que más se mueve, sacar de
 * lo preferente lo que no se mueve. Las aceptadas se vuelven tareas de bodega.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Box, Paper, Typography, MenuItem, Button, Chip, Stack, Alert, Tabs, Tab, Checkbox, Tooltip,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { AutoAwesome } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, TablaRegistros, Cifra, errorApi } from '@/components/comun/Registro'
import { sug, type Sugerencia } from '@/api/wmsSugerencias'
import { wms, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'

const COLOR = COLOR_MODULO
const CLASE_COLOR: Record<string, string> = { A: '#15803D', B: '#D97706', C: '#64748B' }

export default function WMSSlotting() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const [dias, setDias] = useState(90)
  const [tab, setTab] = useState(0)
  const abc = useQuery({ queryKey: ['slot-abc', almacen, dias], enabled: !!almacen, queryFn: () => sug.abc(Number(almacen), dias) })
  const sugs = useQuery({ queryKey: ['slot-sug', almacen, dias], enabled: !!almacen, queryFn: () => sug.sugerencias(Number(almacen), dias) })
  const ruta = useQuery({ queryKey: ['slot-ruta', almacen], enabled: !!almacen && tab === 2, queryFn: () => sug.recorrido(Number(almacen)) })
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set())
  useEffect(() => { setMarcadas(new Set((sugs.data ?? []).map((_, i) => i))) }, [sugs.data])
  const conteo = useMemo(() => {
    const d = abc.data ?? []
    return { A: d.filter(x => x.clase === 'A').length, B: d.filter(x => x.clase === 'B').length, C: d.filter(x => x.clase === 'C').length,
      afuera: d.filter(x => x.clase === 'A' && !x.en_preferente).length }
  }, [abc.data])
  const aplicar = async () => {
    const elegidas = (sugs.data ?? []).filter((_, i) => marcadas.has(i))
    try {
      const r = await sug.aplicar(Number(almacen), elegidas)
      toast.success(`${r.tareas.length} tareas creadas${r.omitidas ? ` (${r.omitidas} ya tenían tarea abierta)` : ''}: hágalas en Tareas de bodega`)
      qc.invalidateQueries({ queryKey: ['slot-sug'] })
    } catch (e) { toast.error(errorApi(e)) }
  }
  return (
    <Layout title="WMS — Ubicación inteligente">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<AutoAwesome sx={{ fontSize: 28 }} />} titulo="Ubicación inteligente (slotting)" color={COLOR}
          subtitulo="Lo que más se mueve, al frente y a la altura de la mano" />
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => setAlmacen(Number(e.target.value))} sx={{ minWidth: 240 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Historia para el ABC" value={dias} onChange={e => setDias(Number(e.target.value))} sx={{ minWidth: 180 }}>
            {[30, 60, 90, 180, 365].map(d => <MenuItem key={d} value={d}>Últimos {d} días</MenuItem>)}
          </TextField>
        </Stack>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Clase A (80 % de las líneas)" valor={conteo.A} color={CLASE_COLOR.A} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Clase B (siguiente 15 %)" valor={conteo.B} color={CLASE_COLOR.B} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Clase C" valor={conteo.C} color={CLASE_COLOR.C} /></Grid>
          <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="A fuera de lo preferente" valor={conteo.afuera} color="#DC2626" sub={`${sugs.data?.length ?? 0} reubicaciones sugeridas`} /></Grid>
        </Grid>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Reubicaciones sugeridas" /><Tab label="Clasificación ABC" /><Tab label="Recorrido" /></Tabs>
        {tab === 0 && <>
          {sugs.data && !sugs.data.length && <Alert severity="success">No hay reubicaciones que sugerir: lo que más se mueve ya está en lo preferente.</Alert>}
          {!!sugs.data?.length && <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
            <Button variant="contained" disabled={!marcadas.size} onClick={aplicar} sx={{ bgcolor: COLOR }}>Crear {marcadas.size} tareas de movimiento</Button></Box>}
          <TablaRegistros filas={(sugs.data ?? []).map((s, i) => ({ ...s, id: i }))} cargando={sugs.isLoading} vacio="" etiqueta={(s: Sugerencia) => s.sku}
            columnas={[
              { titulo: '', valor: (s: any) => <Checkbox size="small" checked={marcadas.has(s.id)} onChange={e => setMarcadas(m => { const n = new Set(m); e.target.checked ? n.add(s.id) : n.delete(s.id); return n })} /> },
              { titulo: 'Acción', valor: (s: Sugerencia) => <Chip size="small" color={s.tipo === 'ACERCAR' ? 'success' : 'default'} label={s.tipo === 'ACERCAR' ? 'Acercar' : 'Alejar'} /> },
              { titulo: 'Producto', valor: (s: Sugerencia) => <><b>{s.sku}</b> <Chip size="small" label={s.clase} sx={{ bgcolor: CLASE_COLOR[s.clase], color: '#fff', height: 18 }} /></> },
              { titulo: 'Cantidad', valor: (s: Sugerencia) => num(s.cantidad), alinear: 'right' },
              { titulo: 'De → a', valor: (s: Sugerencia) => <Typography fontFamily="monospace" fontSize={13}>{s.origen} → {s.destino}</Typography> },
              { titulo: 'Por qué', valor: (s: Sugerencia) => <Typography fontSize={12} color="text.secondary">{s.razon}</Typography> },
            ]} />
        </>}
        {tab === 1 && <TablaRegistros filas={(abc.data ?? []).map((x: any) => ({ ...x, id: x.producto_id }))} cargando={abc.isLoading} vacio="Sin movimiento ni existencias" etiqueta={(x: any) => x.sku}
          columnas={[
            { titulo: 'Clase', valor: (x: any) => <Chip size="small" label={x.clase} sx={{ bgcolor: CLASE_COLOR[x.clase], color: '#fff' }} /> },
            { titulo: 'SKU', valor: (x: any) => x.sku }, { titulo: 'Producto', valor: (x: any) => x.nombre },
            { titulo: 'Líneas', valor: (x: any) => x.lineas, alinear: 'right' }, { titulo: 'Participación', valor: (x: any) => `${x.participacion_pct}%`, alinear: 'right' },
            { titulo: 'Unidades', valor: (x: any) => num(x.unidades), alinear: 'right' },
            { titulo: 'Dónde está', valor: (x: any) => x.ubicaciones.join(', ') || '—' },
            { titulo: 'En preferente', valor: (x: any) => x.en_preferente ? 'Sí' : (x.clase === 'A' ? <Chip size="small" color="error" label="No" /> : 'No') },
          ]} />}
        {tab === 2 && <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
          <Typography fontSize={13} color="text.secondary" mb={1.5}>
            Orden de recorrido (serpentina por pasillos, o el configurado en cada ubicación). Las verdes son preferentes: el primer 30 % del recorrido en niveles 1 y 2.
          </Typography>
          <Stack direction="row" gap={0.75} flexWrap="wrap">
            {(ruta.data ?? []).map((u: any) => (
              <Tooltip key={u.id} title={`Puesto ${u.puesto + 1}${u.nivel ? ` · nivel ${u.nivel}` : ''} · ${num(u.unidades)} und`}>
                <Chip size="small" label={`${u.puesto + 1}. ${u.codigo}`} variant={u.unidades ? 'filled' : 'outlined'}
                  sx={{ fontFamily: 'monospace', borderColor: u.preferente ? '#15803D' : undefined, bgcolor: u.unidades ? (u.preferente ? '#DCFCE7' : '#F1F5F9') : undefined }} />
              </Tooltip>
            ))}
          </Stack>
        </Paper>}
      </Box>
    </Layout>
  )
}
