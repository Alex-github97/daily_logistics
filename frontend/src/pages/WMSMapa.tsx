/**
 * WMS · Mapa de la bodega — «gemelo digital»
 *
 * Al cargar un plano, el servidor lo vectoriza (SVG de muros, racks y zonas);
 * al calibrar la foto de una estantería, la endereza y la vectoriza también.
 * Sobre esos SVG se dibuja el estado vivo del inventario:
 *
 *  - Plano: cada estantería es un bloque luminoso con su ocupación.
 *  - Estantería: como la foto ya está enderezada, cada celda es un rectángulo
 *    exacto con su código, producto, unidades y barra de ocupación.
 *
 * La pestaña «Foto original» conserva la foto con la cuadrícula proyectada en
 * perspectiva (homografía): ahí se calibran las 4 esquinas y se asignan celdas.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Box, Paper, Typography, MenuItem, Button, Chip, Stack, Alert, Tabs, Tab, Dialog, DialogTitle, DialogContent, DialogActions,
  Autocomplete, Tooltip, LinearProgress, ToggleButton, ToggleButtonGroup, FormControlLabel, Switch, alpha,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Map as MapaIcon, AddPhotoAlternate, Search, Straighten, AutoFixHigh, CropFree, ViewInAr, PhotoCamera, Refresh, Architecture } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { Encabezado, errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'
import { wms, num } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'
import Bodega3D from '@/components/wms/Bodega3D'
import ConstructorBodega from '@/components/wms/ConstructorBodega'

const COLOR = COLOR_MODULO
type Punto = [number, number]

// Paleta del gemelo digital (fondo claro)
const NEON = { fondo: '#F8FAFC', panel: '#FFFFFF', borde: '#E2E8F0', cian: '#4F46E5', texto: '#0F172A', tenue: '#64748B' }
const ESTADOS: Record<string, { color: string; texto: string }> = {
  VACIA: { color: '#94A3B8', texto: 'Vacía' }, OCUPADA: { color: '#10B981', texto: 'Ocupada' },
  CASI_LLENA: { color: '#F59E0B', texto: 'Casi llena (> 80 %)' }, LLENA: { color: '#EF4444', texto: 'Llena (> 95 %)' },
  BLOQUEADA: { color: '#A855F7', texto: 'Bloqueada' }, SIN_ASIGNAR: { color: '#CBD5E1', texto: 'Sin ubicación asignada' },
}
const BUSCADO = '#2563EB'
const colorPct = (p?: number | null) => p == null ? '#64748B' : p > 90 ? '#EF4444' : p > 70 ? '#F59E0B' : '#10B981'

/** Escenario claro con cuadrícula suave. */
const escenario = {
  position: 'relative', borderRadius: 3, overflow: 'hidden', border: `1px solid ${NEON.borde}`,
  bgcolor: NEON.fondo,
  backgroundImage: `linear-gradient(rgba(100,116,139,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(100,116,139,0.08) 1px, transparent 1px)`,
  backgroundSize: '28px 28px, 28px 28px',
} as const

const ANIMACIONES = {
  '@keyframes pulso': { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.45 } },
  '@keyframes barrido': { '0%': { transform: 'translateY(-100%)' }, '100%': { transform: 'translateY(100%)' } },
}

/** Homografía del cuadrado unitario al cuadrilátero [arriba-izq, arriba-der, abajo-der, abajo-izq]. */
function homografia(q: Punto[]) {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = q
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3
  const dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3
  let g = 0, h = 0
  if (Math.abs(dx3) > 1e-12 || Math.abs(dy3) > 1e-12) {
    const det = dx1 * dy2 - dx2 * dy1
    g = (dx3 * dy2 - dx2 * dy3) / det
    h = (dx1 * dy3 - dx3 * dy1) / det
  }
  const a = x1 - x0 + g * x1, b = x3 - x0 + h * x3, c = x0
  const d = y1 - y0 + g * y1, e = y3 - y0 + h * y3, f = y0
  return (u: number, v: number): Punto => {
    const w = g * u + h * v + 1
    return [(a * u + b * v + c) / w, (d * u + e * v + f) / w]
  }
}

function celdaPoligono(H: (u: number, v: number) => Punto, fila: number, col: number, filas: number, cols: number) {
  const u0 = col / cols, u1 = (col + 1) / cols, v0 = fila / filas, v1 = (fila + 1) / filas
  return [H(u0, v0), H(u1, v0), H(u1, v1), H(u0, v1)].map(p => p.join(',')).join(' ')
}

/** La imagen se pide con la sesión (no está en una carpeta pública) y se muestra como blob. */
function useImagen(ruta?: string | null) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!ruta) { setUrl(null); return }
    let vivo = true, creado: string | null = null
    api.get(ruta, { responseType: 'blob' }).then(r => { if (vivo) { creado = URL.createObjectURL(r.data); setUrl(creado) } }).catch(() => vivo && setUrl(null))
    return () => { vivo = false; if (creado) URL.revokeObjectURL(creado) }
  }, [ruta])
  return url
}

function puntoDe(e: React.MouseEvent, el: HTMLElement): Punto {
  const r = el.getBoundingClientRect()
  return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]
}

function Kpi({ etiqueta, valor, color = NEON.cian, sub }: { etiqueta: string; valor: string; color?: string; sub?: string }) {
  return (
    <Box sx={{ flex: 1, minWidth: 140, px: 2, py: 1.25, borderRadius: 2, bgcolor: '#FFFFFF', border: '1px solid #E2E8F0', borderTop: `3px solid ${color}` }}>
      <Typography sx={{ fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: NEON.tenue, fontWeight: 700 }}>{etiqueta}</Typography>
      <Typography sx={{ fontSize: 24, fontWeight: 800, color, fontFamily: 'Consolas, monospace', lineHeight: 1.2 }}>{valor}</Typography>
      {sub && <Typography sx={{ fontSize: 11, color: NEON.tenue }}>{sub}</Typography>}
    </Box>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// Estantería — gemelo digital (foto enderezada + SVG + celdas exactas)
// ═════════════════════════════════════════════════════════════════════════════
function GemeloEstanteria({ est, fotoId, onCelda }: { est: any; fotoId: number; onCelda: (c: any) => void }) {
  const f = est.foto
  const svg = useImagen(`/wms/mapa/fotos/${fotoId}/svg`)
  const foto = useImagen(`/wms/mapa/fotos/${fotoId}/rectificada`)
  const [ratio, setRatio] = useState<number | null>(null)
  const filas = f.filas, cols = f.columnas
  if (!svg || !foto) return <LinearProgress />
  return (
    <Box sx={{ ...escenario, ...ANIMACIONES, p: { xs: 1.5, md: 2.5 }, pl: { xs: 4, md: 5.5 }, pb: { xs: 4, md: 5 } }}>
      <Box sx={{ position: 'relative', width: '100%', aspectRatio: ratio ? String(ratio) : undefined }}>
        <img src={foto} alt="" onLoad={e => setRatio(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.1, filter: 'grayscale(1)', mixBlendMode: 'multiply' }} draggable={false} />
        <img src={svg} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.4 }} draggable={false} />
        {/* línea de escaneo */}
        <Box sx={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
          <Box sx={{ position: 'absolute', left: 0, right: 0, height: '30%', animation: 'barrido 6s linear infinite',
            background: 'linear-gradient(to bottom, transparent, rgba(79,70,229,0.04), transparent)' }} />
        </Box>
        {/* reglas: niveles a la izquierda, posiciones abajo */}
        {Array.from({ length: filas }).map((_, i) => (
          <Typography key={`n${i}`} sx={{ position: 'absolute', left: { xs: -26, md: -34 }, top: `${((i + 0.5) / filas) * 100}%`, transform: 'translateY(-50%)',
            fontFamily: 'Consolas, monospace', fontSize: 12, fontWeight: 700, color: NEON.cian, opacity: 0.8 }}>N{filas - i}</Typography>
        ))}
        {Array.from({ length: cols }).map((_, j) => (
          <Typography key={`p${j}`} sx={{ position: 'absolute', bottom: { xs: -24, md: -30 }, left: `${((j + 0.5) / cols) * 100}%`, transform: 'translateX(-50%)',
            fontFamily: 'Consolas, monospace', fontSize: 12, fontWeight: 700, color: NEON.cian, opacity: 0.8 }}>P{j + 1}</Typography>
        ))}
        {/* celdas */}
        <Box sx={{ position: 'absolute', inset: 0, display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${filas}, 1fr)` }}>
          {est.celdas.filter((c: any) => c.fila < filas && c.columna < cols).map((c: any) => {
            const e = ESTADOS[c.estado] ?? ESTADOS.OCUPADA
            const color = c.resaltar ? BUSCADO : e.color
            const vacia = c.estado === 'VACIA' || c.estado === 'SIN_ASIGNAR'
            const pct = c.ocupacion_pct ?? (c.unidades > 0 ? 50 : 0)
            const top = c.contenido?.[0]
            return (
              <Tooltip key={`${c.fila}-${c.columna}`} placement="top" title={c.codigo ? <>
                <b>{c.codigo}</b> · {e.texto}{c.ocupacion_pct != null ? ` · ${c.ocupacion_pct}%` : ''}<br />
                {c.contenido.map((x: any) => <span key={x.sku}>{x.sku} · {x.nombre} × {num(x.unidades)}<br /></span>)}</> : 'Sin ubicación asignada (clic para asignar)'}>
                <Box onClick={() => onCelda(c)} sx={{
                  gridRow: c.fila + 1, gridColumn: c.columna + 1, m: { xs: 0.4, md: 0.75 }, borderRadius: 1.5, cursor: 'pointer', position: 'relative', overflow: 'hidden',
                  border: `1.5px ${c.estado === 'SIN_ASIGNAR' ? 'dashed' : 'solid'} ${alpha(color, vacia && !c.resaltar ? 0.45 : 0.95)}`,
                  bgcolor: alpha(color, vacia && !c.resaltar ? 0.04 : 0.16),
                  animation: c.resaltar || c.estado === 'LLENA' ? 'pulso 1.6s ease-in-out infinite' : undefined,
                  transition: 'transform .15s, box-shadow .15s', '&:hover': { transform: 'scale(1.02)', boxShadow: `0 4px 14px ${alpha(color, 0.35)}` },
                  display: 'flex', flexDirection: 'column', justifyContent: 'space-between', p: { xs: 0.5, md: 1 },
                }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={0.5}>
                    <Typography sx={{ fontFamily: 'Consolas, monospace', fontSize: { xs: 9.5, md: 12 }, fontWeight: 800, color: alpha(color, 1),
                      px: 0.6, borderRadius: 0.75, bgcolor: alpha('#FFFFFF', 0.9) }}>{c.codigo ?? '—'}</Typography>
                    {!vacia && <Typography sx={{ fontFamily: 'Consolas, monospace', fontSize: { xs: 9, md: 11 }, fontWeight: 700, color: NEON.texto,
                      px: 0.6, borderRadius: 0.75, bgcolor: alpha('#FFFFFF', 0.9) }}>{c.ocupacion_pct != null ? `${c.ocupacion_pct}%` : `${num(c.unidades)} u`}</Typography>}
                  </Stack>
                  {top ? (
                    <Box sx={{ px: 0.6, py: 0.3, borderRadius: 0.75, bgcolor: alpha('#FFFFFF', 0.9), display: { xs: 'none', sm: 'block' } }}>
                      <Typography noWrap sx={{ fontSize: 11.5, fontWeight: 700, color: NEON.texto }}>{top.nombre}</Typography>
                      <Typography noWrap sx={{ fontSize: 10.5, color: '#64748B', fontFamily: 'Consolas, monospace' }}>
                        {top.sku} · {num(top.unidades)} und{c.contenido.length > 1 ? ` · +${c.contenido.length - 1}` : ''}</Typography>
                    </Box>
                  ) : <Typography sx={{ fontSize: 11, color: NEON.tenue, textAlign: 'center', fontFamily: 'Consolas, monospace' }}>
                    {c.estado === 'SIN_ASIGNAR' ? 'SIN ASIGNAR' : 'LIBRE'}</Typography>}
                  <Box sx={{ height: 4, borderRadius: 2, bgcolor: alpha('#94A3B8', 0.18), overflow: 'hidden' }}>
                    <Box sx={{ height: '100%', width: `${Math.min(100, vacia ? 0 : pct)}%`, bgcolor: color }} />
                  </Box>
                </Box>
              </Tooltip>
            )
          })}
        </Box>
      </Box>
    </Box>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// Estantería — foto original con la cuadrícula en perspectiva (y calibración)
// ═════════════════════════════════════════════════════════════════════════════
function VistaFoto({ fotoId, almacen, productoId, onCalibrada }: { fotoId: number; almacen: number; productoId?: number; onCalibrada: () => void }) {
  const qc = useQueryClient()
  const est = useQuery({ queryKey: ['mapa-estado', fotoId, productoId], queryFn: () => api.get(`/wms/mapa/fotos/${fotoId}/estado`, { params: { producto_id: productoId } }).then(r => r.data) })
  const url = useImagen(`/wms/mapa/fotos/${fotoId}/imagen`)
  const ubicaciones = useQuery({ queryKey: ['mapa-ubic', almacen], queryFn: () => api.get('/wms/ubicaciones/').then(r => r.data) })
  const caja = useRef<HTMLDivElement>(null)
  const [vista, setVista] = useState<'gemelo' | 'foto'>('gemelo')
  const [modo, setModo] = useState<'ver' | 'esquinas'>('ver')
  const [puntos, setPuntos] = useState<Punto[]>([])
  const [grilla, setGrilla] = useState({ filas: '', columnas: '', pasillo: '', estanteria: '' })
  const [celda, setCelda] = useState<any | null>(null)
  const [asignar, setAsignar] = useState<any | null>(null)
  const f = est.data?.foto
  useEffect(() => { if (f) setGrilla({ filas: String(f.filas ?? ''), columnas: String(f.columnas ?? ''), pasillo: f.pasillo ?? '', estanteria: f.estanteria ?? '' }) }, [f?.id, f?.filas, f?.columnas])
  useEffect(() => { if (f && !f.vectorizada) setVista('foto') }, [f?.id, f?.vectorizada])
  const esquinas: Punto[] | null = modo === 'esquinas' ? (puntos.length === 4 ? puntos : null) : f?.esquinas ?? null
  const H = useMemo(() => esquinas ? homografia(esquinas) : null, [esquinas])
  const filas = Number(grilla.filas) || f?.filas || 0, cols = Number(grilla.columnas) || f?.columnas || 0
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['mapa-estado'] }); qc.invalidateQueries({ queryKey: ['mapa-fotos'] }); onCalibrada() }
  const abrirCelda = (c: any) => { setCelda(c); setAsignar((ubicaciones.data ?? []).find((u: any) => u.id === c.ubicacion_id) ?? null) }

  const guardarCalibracion = async () => {
    try {
      await api.put(`/wms/mapa/fotos/${fotoId}`, { esquinas: puntos.length === 4 ? puntos : f.esquinas, filas: Number(grilla.filas), columnas: Number(grilla.columnas),
        pasillo: grilla.pasillo || null, estanteria: grilla.estanteria || null })
      setModo('ver'); setPuntos([]); toast.success('Cuadrícula guardada: foto enderezada y vectorizada'); refrescar(); setVista('gemelo')
    } catch (e) { toast.error(errorApi(e)) }
  }
  const autoasignar = async () => {
    try { const r = await api.post(`/wms/mapa/fotos/${fotoId}/autoasignar`, { pasillo: grilla.pasillo || undefined, estanteria: grilla.estanteria || undefined }).then(r => r.data)
      toast.success(`${r.asignadas} de ${r.celdas} celdas asignadas${r.ubicaciones_fuera ? ` (${r.ubicaciones_fuera} ubicaciones no caben en la cuadrícula)` : ''}`); refrescar()
    } catch (e) { toast.error(errorApi(e)) }
  }
  const guardarCelda = async () => {
    try { await api.put(`/wms/mapa/fotos/${fotoId}/celdas`, [{ fila: celda.fila, columna: celda.columna, ubicacion_id: asignar?.id ?? null }])
      setCelda(null); refrescar() } catch (e) { toast.error(errorApi(e)) }
  }
  if (!est.data || !url) return <LinearProgress />
  const resumen = est.data.resumen as Record<string, number>
  const total = est.data.celdas.length || 1
  const ocupadas = est.data.celdas.filter((c: any) => !['VACIA', 'SIN_ASIGNAR'].includes(c.estado)).length
  const unidades = est.data.celdas.reduce((s: number, c: any) => s + (c.unidades || 0), 0)
  return (
    <Box>
      <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" mb={1.5}>
        <Typography fontWeight={800} fontSize={18}>{f.nombre}</Typography>
        <Chip size="small" label={`${f.filas ?? '?'} niveles × ${f.columnas ?? '?'} posiciones`} sx={{ fontFamily: 'Consolas, monospace' }} />
        <Box flex={1} />
        <ToggleButtonGroup size="small" exclusive value={vista} onChange={(_, v) => v && setVista(v)}>
          <ToggleButton value="gemelo" disabled={!f.vectorizada} sx={{ textTransform: 'none', gap: 0.5 }}><ViewInAr fontSize="small" />Gemelo digital</ToggleButton>
          <ToggleButton value="foto" sx={{ textTransform: 'none', gap: 0.5 }}><PhotoCamera fontSize="small" />Foto original</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Stack direction="row" gap={1.5} mb={1.5} flexWrap="wrap">
        <Kpi etiqueta="Ocupación" valor={`${Math.round((ocupadas / total) * 100)}%`} color={colorPct((ocupadas / total) * 100)} sub={`${ocupadas} de ${total} celdas`} />
        <Kpi etiqueta="Unidades" valor={num(unidades)} color="#818CF8" sub="en esta estantería" />
        <Kpi etiqueta="Libres" valor={String(resumen.VACIA ?? 0)} color="#64748B" sub="celdas vacías" />
        <Kpi etiqueta="Alertas" valor={String((resumen.LLENA ?? 0) + (resumen.BLOQUEADA ?? 0))} color="#F87171" sub="llenas o bloqueadas" />
      </Stack>

      {vista === 'gemelo' && f.vectorizada && <GemeloEstanteria est={est.data} fotoId={fotoId} onCelda={abrirCelda} />}

      {vista === 'foto' && <>
        <Stack direction="row" gap={1} alignItems="center" mb={1.5} flexWrap="wrap">
          {modo === 'ver' ? <Button size="small" startIcon={<CropFree />} onClick={() => { setModo('esquinas'); setPuntos([]) }}>{f.calibrada ? 'Recalibrar' : 'Calibrar cuadrícula'}</Button>
            : <Button size="small" color="inherit" onClick={() => { setModo('ver'); setPuntos([]) }}>Cancelar calibración</Button>}
          {modo === 'ver' && f.calibrada && <Button size="small" startIcon={<AutoFixHigh />} onClick={autoasignar}>Asignar celdas automáticamente</Button>}
          {modo === 'ver' && f.calibrada && <Typography fontSize={12} color="text.secondary">Nivel 1 = fila de abajo · posición 1 = columna izquierda · clic en una celda para cambiarla.</Typography>}
        </Stack>
        {modo === 'esquinas' && <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, borderRadius: 2 }}>
          <Typography fontSize={13} mb={1}>
            Haga clic en las 4 esquinas de la cara de la estantería, en este orden: <b>arriba-izquierda, arriba-derecha, abajo-derecha, abajo-izquierda</b>
            {' '}({puntos.length}/4). Al guardar, la foto se endereza y se convierte a SVG para el gemelo digital.
          </Typography>
          <Stack direction="row" gap={1} flexWrap="wrap">
            <TextField size="small" type="number" label="Niveles (filas)" value={grilla.filas} onChange={e => setGrilla({ ...grilla, filas: e.target.value })} sx={{ width: 130 }} />
            <TextField size="small" type="number" label="Posiciones (columnas)" value={grilla.columnas} onChange={e => setGrilla({ ...grilla, columnas: e.target.value })} sx={{ width: 160 }} />
            <TextField size="small" label="Pasillo" value={grilla.pasillo} onChange={e => setGrilla({ ...grilla, pasillo: e.target.value })} sx={{ width: 110 }} />
            <TextField size="small" label="Estantería" value={grilla.estanteria} onChange={e => setGrilla({ ...grilla, estanteria: e.target.value })} sx={{ width: 120 }} />
            <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={(puntos.length !== 4 && !f.esquinas) || !(Number(grilla.filas) > 0) || !(Number(grilla.columnas) > 0)} onClick={guardarCalibracion}>Guardar cuadrícula</Button>
            <Button size="small" onClick={() => setPuntos([])}>Volver a marcar</Button>
          </Stack>
        </Paper>}
        {modo === 'ver' && !f.calibrada && <Alert severity="info" sx={{ mb: 1.5 }}>Calibre la cuadrícula para ver la ocupación y generar el gemelo digital.</Alert>}
        <Box ref={caja} sx={{ ...escenario, userSelect: 'none', cursor: modo === 'esquinas' ? 'crosshair' : 'default' }}
          onClick={e => { if (modo === 'esquinas' && puntos.length < 4 && caja.current) setPuntos(p => [...p, puntoDe(e, caja.current!)]) }}>
          <img src={url} alt={f.nombre} style={{ width: '100%', display: 'block', filter: 'grayscale(0.3)' }} draggable={false} />
          <svg viewBox="0 0 1 1" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
            {H && filas > 0 && cols > 0 && est.data.celdas.filter((c: any) => c.fila < filas && c.columna < cols).map((c: any) => {
              const e = ESTADOS[c.estado] ?? ESTADOS.OCUPADA
              const color = c.resaltar ? BUSCADO : e.color
              const vacia = c.estado === 'VACIA' || c.estado === 'SIN_ASIGNAR'
              return (
                <Tooltip key={`${c.fila}-${c.columna}`} title={c.codigo ? <>
                  <b>{c.codigo}</b> · {e.texto}{c.ocupacion_pct != null ? ` · ${c.ocupacion_pct}%` : ''}<br />
                  {c.contenido.map((x: any) => <span key={x.sku}>{x.sku} × {num(x.unidades)}<br /></span>)}</> : 'Sin ubicación asignada (clic para asignar)'}>
                  <polygon points={celdaPoligono(H, c.fila, c.columna, filas, cols)}
                    fill={color} fillOpacity={vacia && !c.resaltar ? 0.06 : 0.38}
                    stroke={vacia && !c.resaltar ? NEON.cian : color} strokeOpacity={0.95}
                    strokeWidth={c.resaltar ? 3 : 1.4} strokeDasharray={c.estado === 'SIN_ASIGNAR' ? '4 3' : undefined} vectorEffect="non-scaling-stroke"
                    style={{ cursor: modo === 'ver' ? 'pointer' : 'crosshair' }}
                    onClick={ev => { if (modo === 'ver') { ev.stopPropagation(); abrirCelda(c) } }} />
                </Tooltip>
              )
            })}
            {modo === 'esquinas' && puntos.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={0.008} fill="#F59E0B" stroke="#fff" strokeWidth={1} vectorEffect="non-scaling-stroke" />)}
          </svg>
        </Box>
      </>}

      <Stack direction="row" gap={1.5} mt={1.25} flexWrap="wrap">
        {Object.entries(ESTADOS).map(([k, e]) => <Stack key={k} direction="row" gap={0.6} alignItems="center">
          <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: alpha(e.color, 0.35), border: `1.5px ${k === 'SIN_ASIGNAR' ? 'dashed' : 'solid'} ${e.color === '#CBD5E1' ? '#94A3B8' : e.color}` }} />
          <Typography fontSize={11.5}>{e.texto}</Typography></Stack>)}
        <Stack direction="row" gap={0.6} alignItems="center"><Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: alpha(BUSCADO, 0.35), border: `1.5px solid ${BUSCADO}` }} /><Typography fontSize={11.5}>Producto buscado</Typography></Stack>
      </Stack>

      <Dialog open={!!celda} onClose={() => setCelda(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>{celda?.codigo ?? 'Celda'} · nivel {celda ? filas - celda.fila : ''} · posición {celda ? celda.columna + 1 : ''}</DialogTitle>
        <DialogContent sx={{ pt: '8px !important' }}>
          {celda?.contenido?.length > 0 && <Stack gap={0.5} mb={1.5}>
            {celda.contenido.map((x: any) => <Typography key={x.sku} fontSize={13}><b style={{ fontFamily: 'Consolas, monospace' }}>{x.sku}</b> · {x.nombre} × {num(x.unidades)}</Typography>)}
          </Stack>}
          <Autocomplete size="small" options={ubicaciones.data ?? []} value={asignar} onChange={(_, v) => setAsignar(v)} getOptionLabel={(u: any) => u.codigo}
            renderInput={p => <TextField {...p} label="Ubicación de esta celda" />} />
        </DialogContent>
        <DialogActions><Button color="inherit" onClick={() => setCelda(null)}>Cerrar</Button><Button onClick={guardarCelda}>Guardar</Button></DialogActions>
      </Dialog>
    </Box>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// Estructura del constructor — vista de frente dibujada con sus datos
// ═════════════════════════════════════════════════════════════════════════════
function VistaEstructura({ id, almacen, productoId, onEditar }: { id: number; almacen: number; productoId?: number; onEditar: () => void }) {
  const est = useQuery({ queryKey: ['estructura-estado', id, productoId], refetchInterval: 30_000,
    queryFn: () => api.get(`/wms/layout/estructuras/${id}/estado`, { params: { producto_id: productoId } }).then(r => r.data) })
  const [vista, setVista] = useState<'esquema' | 'foto'>('esquema')
  if (!est.data) return <LinearProgress />
  const e = est.data.estructura, celdas: any[] = est.data.celdas
  const niveles: number = e.niveles_vista, posiciones: number = e.posiciones, modulos: number = e.modulos
  const resumen = est.data.resumen as Record<string, number>
  const vinculadas = celdas.filter(c => c.ubicacion_id).length
  const ocupadas = celdas.filter(c => !['VACIA', 'SIN_ASIGNAR'].includes(c.estado)).length
  const unidades = celdas.reduce((s, c) => s + (c.unidades || 0), 0)
  const total = vinculadas || celdas.length || 1
  const tipoNombre: Record<string, string> = { SELECTIVO: 'Rack selectivo', GONDOLA: 'Góndola', CANTILEVER: 'Cantiléver', PISO: 'Almacenamiento en piso' }
  return (
    <Box>
      <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" mb={1.5}>
        <Typography fontWeight={800} fontSize={18}>{e.nombre}</Typography>
        <Chip size="small" label={`${tipoNombre[e.tipo] ?? e.tipo} · ${niveles} ${e.tipo === 'PISO' ? 'nivel' : 'niveles'} × ${posiciones} posiciones`} sx={{ fontFamily: 'Consolas, monospace' }} />
        {e.zona && <Chip size="small" variant="outlined" label={`Zona ${e.zona}`} />}
        <Box flex={1} />
        {e.foto_id && <ToggleButtonGroup size="small" exclusive value={vista} onChange={(_, v) => v && setVista(v)}>
          <ToggleButton value="esquema" sx={{ textTransform: 'none', gap: 0.5 }}><ViewInAr fontSize="small" />Esquema</ToggleButton>
          <ToggleButton value="foto" sx={{ textTransform: 'none', gap: 0.5 }}><PhotoCamera fontSize="small" />Foto</ToggleButton>
        </ToggleButtonGroup>}
        <Button size="small" startIcon={<Architecture />} onClick={onEditar} sx={{ textTransform: 'none' }}>Editar en el constructor</Button>
      </Stack>

      {vista === 'foto' && e.foto_id ? <VistaFoto fotoId={e.foto_id} almacen={almacen} productoId={productoId} onCalibrada={() => est.refetch()} /> : <>
        <Stack direction="row" gap={1.5} mb={1.5} flexWrap="wrap">
          <Kpi etiqueta="Ocupación" valor={`${Math.round((ocupadas / total) * 100)}%`} color={colorPct((ocupadas / total) * 100)} sub={`${ocupadas} de ${total} posiciones`} />
          <Kpi etiqueta="Unidades" valor={num(unidades)} color="#818CF8" sub="en esta estructura" />
          <Kpi etiqueta="Libres" valor={String(resumen.VACIA ?? 0)} color="#64748B" sub="posiciones vacías" />
          <Kpi etiqueta="Alertas" valor={String((resumen.LLENA ?? 0) + (resumen.BLOQUEADA ?? 0))} color="#F87171" sub="llenas o bloqueadas" />
        </Stack>
        {vinculadas < celdas.length && <Alert severity="warning" sx={{ mb: 1.5 }} action={<Button size="small" color="inherit" onClick={onEditar}>Ir al constructor</Button>}>
          {celdas.length - vinculadas} posiciones aún no tienen ubicación del WMS: use «Generar ubicaciones» en el constructor.</Alert>}

        {/* alzado: postes en cada módulo, largueros bajo cada nivel */}
        <Box sx={{ ...escenario, p: { xs: 1.5, md: 2.5 }, pl: { xs: 4, md: 5.5 }, pb: { xs: 4, md: 5 } }}>
          <Box sx={{ position: 'relative', width: '100%', aspectRatio: `${Math.max(1.6, (posiciones * 1.15) / Math.max(1, niveles) * (e.tipo === 'GONDOLA' ? 1.4 : 1))}` , maxHeight: 640 }}>
            {/* estructura */}
            {e.tipo !== 'PISO' && Array.from({ length: modulos + 1 }).map((_, i) => (
              <Box key={`p${i}`} sx={{ position: 'absolute', top: -6, bottom: -4, left: `calc(${(i / modulos) * 100}% - 4px)`, width: 8, borderRadius: 1,
                bgcolor: i === 0 || i === modulos ? '#EA580C' : '#64748B', opacity: 0.9 }} />
            ))}
            {e.tipo !== 'PISO' && Array.from({ length: niveles }).map((_, i) => (
              <Box key={`l${i}`} sx={{ position: 'absolute', left: 0, right: 0, height: e.tipo === 'SELECTIVO' ? 7 : 5, top: `calc(${((i + 1) / niveles) * 100}% - 3px)`,
                bgcolor: e.tipo === 'SELECTIVO' ? '#F97316' : '#94A3B8', borderRadius: 0.5 }} />
            ))}
            {e.tipo === 'PISO' && <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: -4, height: 6, bgcolor: '#EAB308', borderRadius: 1 }} />}
            {Array.from({ length: niveles }).map((_, i) => (
              <Typography key={`n${i}`} sx={{ position: 'absolute', left: { xs: -26, md: -34 }, top: `${((i + 0.5) / niveles) * 100}%`, transform: 'translateY(-50%)',
                fontFamily: 'Consolas, monospace', fontSize: 12, fontWeight: 700, color: NEON.cian }}>N{niveles - i}</Typography>
            ))}
            {Array.from({ length: posiciones }).map((_, j) => (
              <Typography key={`q${j}`} sx={{ position: 'absolute', bottom: { xs: -26, md: -32 }, left: `${((j + 0.5) / posiciones) * 100}%`, transform: 'translateX(-50%)',
                fontFamily: 'Consolas, monospace', fontSize: 12, fontWeight: 700, color: NEON.cian }}>P{j + 1}</Typography>
            ))}
            {/* posiciones */}
            <Box sx={{ position: 'absolute', inset: 0, display: 'grid', gridTemplateColumns: `repeat(${posiciones}, 1fr)`, gridTemplateRows: `repeat(${niveles}, 1fr)` }}>
              {celdas.map(c => {
                const es = ESTADOS[c.estado] ?? ESTADOS.OCUPADA
                const color = c.resaltar ? BUSCADO : es.color
                const vacia = c.estado === 'VACIA' || c.estado === 'SIN_ASIGNAR'
                const pct = c.ocupacion_pct ?? (c.unidades > 0 ? 50 : 0)
                const top = c.contenido?.[0]
                return (
                  <Tooltip key={`${c.nivel}-${c.posicion}`} placement="top" title={c.codigo ? <>
                    <b>{c.codigo}</b> · {es.texto}{c.ocupacion_pct != null ? ` · ${c.ocupacion_pct}%` : ''}<br />
                    {c.contenido.map((x: any) => <span key={x.sku}>{x.sku} · {x.nombre} × {num(x.unidades)}<br /></span>)}</> : 'Sin ubicación del WMS (genérela en el constructor)'}>
                    <Box sx={{
                      gridRow: niveles - c.nivel + 1, gridColumn: c.posicion, m: { xs: '6px 7px 10px', md: '8px 10px 13px' }, borderRadius: 1.5, position: 'relative', overflow: 'hidden',
                      border: `1.5px ${c.estado === 'SIN_ASIGNAR' ? 'dashed' : 'solid'} ${alpha(color, vacia && !c.resaltar ? 0.5 : 0.95)}`,
                      bgcolor: vacia && !c.resaltar ? alpha('#FFFFFF', 0.85) : alpha(color, 0.14),
                      animation: c.resaltar || c.estado === 'LLENA' ? 'pulso 1.6s ease-in-out infinite' : undefined,
                      transition: 'transform .15s, box-shadow .15s', '&:hover': { transform: 'scale(1.02)', boxShadow: `0 4px 14px ${alpha(color, 0.35)}` },
                      display: 'flex', flexDirection: 'column', justifyContent: 'space-between', p: { xs: 0.5, md: 1 }, ...ANIMACIONES,
                    }}>
                      {/* llenado proporcional al volumen */}
                      {!vacia && <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${Math.max(8, Math.min(100, pct))}%`, bgcolor: alpha(color, 0.16), pointerEvents: 'none' }} />}
                      <Stack direction="row" justifyContent="space-between" alignItems="center" gap={0.5} sx={{ position: 'relative' }}>
                        <Typography sx={{ fontFamily: 'Consolas, monospace', fontSize: { xs: 9.5, md: 12 }, fontWeight: 800, color: vacia ? '#475569' : color,
                          px: 0.6, borderRadius: 0.75, bgcolor: alpha('#FFFFFF', 0.9) }}>{c.codigo ?? '—'}</Typography>
                        {!vacia && <Typography sx={{ fontFamily: 'Consolas, monospace', fontSize: { xs: 9, md: 11 }, fontWeight: 700, color: NEON.texto,
                          px: 0.6, borderRadius: 0.75, bgcolor: alpha('#FFFFFF', 0.9) }}>{c.ocupacion_pct != null ? `${c.ocupacion_pct}%` : `${num(c.unidades)} u`}</Typography>}
                      </Stack>
                      {top ? (
                        <Box sx={{ position: 'relative', px: 0.6, py: 0.3, borderRadius: 0.75, bgcolor: alpha('#FFFFFF', 0.92), display: { xs: 'none', sm: 'block' } }}>
                          <Typography noWrap sx={{ fontSize: 11.5, fontWeight: 700, color: NEON.texto }}>{top.nombre}</Typography>
                          <Typography noWrap sx={{ fontSize: 10.5, color: '#64748B', fontFamily: 'Consolas, monospace' }}>
                            {top.sku} · {num(top.unidades)} und{c.contenido.length > 1 ? ` · +${c.contenido.length - 1}` : ''}</Typography>
                        </Box>
                      ) : <Typography sx={{ position: 'relative', fontSize: 11, color: NEON.tenue, textAlign: 'center', fontFamily: 'Consolas, monospace' }}>
                        {c.estado === 'SIN_ASIGNAR' ? 'SIN UBICACIÓN' : 'LIBRE'}</Typography>}
                      <Box sx={{ position: 'relative', height: 4, borderRadius: 2, bgcolor: alpha('#94A3B8', 0.18), overflow: 'hidden' }}>
                        <Box sx={{ height: '100%', width: `${Math.min(100, vacia ? 0 : pct)}%`, bgcolor: color }} />
                      </Box>
                    </Box>
                  </Tooltip>
                )
              })}
            </Box>
          </Box>
        </Box>
        <Stack direction="row" gap={1.5} mt={1.25} flexWrap="wrap">
          {Object.entries(ESTADOS).map(([k, es]) => <Stack key={k} direction="row" gap={0.6} alignItems="center">
            <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: alpha(es.color, 0.35), border: `1.5px ${k === 'SIN_ASIGNAR' ? 'dashed' : 'solid'} ${es.color === '#CBD5E1' ? '#94A3B8' : es.color}` }} />
            <Typography fontSize={11.5}>{es.texto}</Typography></Stack>)}
          <Stack direction="row" gap={0.6} alignItems="center"><Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: alpha(BUSCADO, 0.35), border: `1.5px solid ${BUSCADO}` }} /><Typography fontSize={11.5}>Producto buscado</Typography></Stack>
        </Stack>
      </>}
    </Box>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// Plano — gemelo digital (SVG vectorizado + estanterías vivas)
// ═════════════════════════════════════════════════════════════════════════════
function Plano({ almacen, fotos, onAbrir }: { almacen: number; fotos: any[]; onAbrir: (id: number) => void }) {
  const qc = useQueryClient()
  const plano = useQuery({ queryKey: ['mapa-plano', almacen], queryFn: () => api.get('/wms/mapa/plano', { params: { almacen_id: almacen } }).then(r => r.data) })
  const url = useImagen(plano.data ? `/wms/mapa/plano/${plano.data.id}/imagen` : null)
  const svg = useImagen(plano.data?.vectorizado ? `/wms/mapa/plano/${plano.data.id}/svg` : null)
  const caja = useRef<HTMLDivElement>(null)
  const [vista, setVista] = useState<'gemelo' | 'original'>('gemelo')
  const [textos, setTextos] = useState(true)
  const [dibujando, setDibujando] = useState(false)
  const [inicio, setInicio] = useState<Punto | null>(null)
  const [rect, setRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const [marca, setMarca] = useState({ etiqueta: '', foto_id: '' as number | '' })
  const subir = async (archivo: File) => {
    const fd = new FormData(); fd.append('almacen_id', String(almacen)); fd.append('archivo', archivo)
    try { const r = await api.post('/wms/mapa/plano', fd).then(r => r.data); toast.success(`Plano cargado y vectorizado (${r.trazos} trazos)`); qc.invalidateQueries({ queryKey: ['mapa-plano'] }) } catch (e) { toast.error(errorApi(e)) }
  }
  const reprocesar = async () => {
    try { await api.post('/wms/mapa/procesar', null, { params: { almacen_id: almacen } }); toast.success('Plano y estanterías vectorizados de nuevo')
      qc.invalidateQueries({ queryKey: ['mapa-plano'] }); qc.invalidateQueries({ queryKey: ['mapa-fotos'] }) } catch (e) { toast.error(errorApi(e)) }
  }
  const guardarMarca = async () => {
    const marcas = [...(plano.data.marcas ?? []).map((m: any) => ({ x: m.x, y: m.y, w: m.w, h: m.h, etiqueta: m.etiqueta, foto_id: m.foto_id })),
      { ...rect, etiqueta: marca.etiqueta, foto_id: marca.foto_id || null }]
    try { await api.put(`/wms/mapa/plano/${plano.data.id}/marcas`, marcas); setRect(null); setMarca({ etiqueta: '', foto_id: '' }); setDibujando(false)
      qc.invalidateQueries({ queryKey: ['mapa-plano'] }) } catch (e) { toast.error(errorApi(e)) }
  }
  const marcas: any[] = plano.data?.marcas ?? []
  const celdas = marcas.reduce((s, m) => s + (m.celdas ?? 0), 0)
  const ocupadas = marcas.reduce((s, m) => s + (m.ocupadas ?? 0), 0)
  const criticas = marcas.filter(m => (m.ocupacion_pct ?? 0) > 90).length
  const gemelo = vista === 'gemelo' && !!svg
  return (
    <Box>
      <Stack direction="row" gap={1} mb={1.5} alignItems="center" flexWrap="wrap">
        <Button component="label" size="small" startIcon={<AddPhotoAlternate />}>{plano.data ? 'Cambiar plano' : 'Cargar plano de la bodega'}
          <input hidden type="file" accept="image/*" onChange={e => e.target.files?.[0] && subir(e.target.files[0])} /></Button>
        {plano.data && <Button size="small" variant={dibujando ? 'contained' : 'text'} onClick={() => setDibujando(d => !d)}>{dibujando ? 'Arrastre sobre el plano…' : 'Marcar una estantería'}</Button>}
        {plano.data && <Button size="small" startIcon={<Refresh />} onClick={reprocesar}>Vectorizar de nuevo</Button>}
        <Box flex={1} />
        {plano.data && gemelo && <FormControlLabel control={<Switch size="small" checked={textos} onChange={e => setTextos(e.target.checked)} />} label={<Typography fontSize={13}>Textos del plano</Typography>} />}
        {plano.data && <ToggleButtonGroup size="small" exclusive value={vista} onChange={(_, v) => v && setVista(v)}>
          <ToggleButton value="gemelo" disabled={!plano.data.vectorizado} sx={{ textTransform: 'none', gap: 0.5 }}><ViewInAr fontSize="small" />Gemelo digital</ToggleButton>
          <ToggleButton value="original" sx={{ textTransform: 'none', gap: 0.5 }}><PhotoCamera fontSize="small" />Plano original</ToggleButton>
        </ToggleButtonGroup>}
      </Stack>
      {!plano.data && !plano.isLoading && <Alert severity="info">Cargue un plano o una foto cenital de la bodega: se convierte a SVG y encima se marcan las estanterías.</Alert>}
      {plano.data && <Stack direction="row" gap={1.5} mb={1.5} flexWrap="wrap">
        <Kpi etiqueta="Estanterías" valor={String(marcas.length)} color="#818CF8" sub="marcadas en el plano" />
        <Kpi etiqueta="Posiciones" valor={String(celdas)} color={NEON.cian} sub="celdas con ubicación" />
        <Kpi etiqueta="Ocupación" valor={celdas ? `${Math.round((ocupadas / celdas) * 100)}%` : '—'} color={colorPct(celdas ? (ocupadas / celdas) * 100 : null)} sub={`${ocupadas} posiciones ocupadas`} />
        <Kpi etiqueta="Críticas" valor={String(criticas)} color="#F87171" sub="estanterías > 90 %" />
      </Stack>}
      {plano.data && url && <Box ref={caja}
        sx={{ ...(gemelo ? escenario : { position: 'relative', borderRadius: 3, overflow: 'hidden', border: '1px solid #E2E8F0' }), ...ANIMACIONES,
          width: '100%', aspectRatio: `${plano.data.ancho} / ${plano.data.alto}`, userSelect: 'none', cursor: dibujando ? 'crosshair' : 'default' }}
        onMouseDown={e => { if (dibujando && caja.current) { setInicio(puntoDe(e, caja.current)); setRect(null) } }}
        onMouseMove={e => { if (dibujando && inicio && caja.current) { const p = puntoDe(e, caja.current); setRect({ x: Math.min(inicio[0], p[0]), y: Math.min(inicio[1], p[1]), w: Math.abs(p[0] - inicio[0]), h: Math.abs(p[1] - inicio[1]) }) } }}
        onMouseUp={() => setInicio(null)}>
        {gemelo ? <>
          {textos && <img src={url} alt="" draggable={false} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
            filter: 'grayscale(1)', mixBlendMode: 'multiply', opacity: 0.35 }} />}
          <img src={svg!} alt="Plano vectorizado" draggable={false} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
        </> : <img src={url} alt="Plano" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', filter: 'grayscale(1)' }} draggable={false} />}
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          {marcas.map((m: any, i: number) => {
            const color = colorPct(m.ocupacion_pct)
            return <Tooltip key={i} title={`${m.etiqueta}${m.ocupacion_pct != null ? ` · ${m.ocupadas}/${m.celdas} posiciones ocupadas (${m.ocupacion_pct}%)` : ''} · clic para ver la estantería`}>
              <rect x={m.x} y={m.y} width={m.w} height={m.h} rx={0.003} fill={color} fillOpacity={gemelo ? 0.2 : 0.35} stroke={color} strokeWidth={gemelo ? 2 : 2}
                vectorEffect="non-scaling-stroke" style={{ cursor: m.foto_id ? 'pointer' : 'default',
                  animation: gemelo && (m.ocupacion_pct ?? 0) > 90 ? 'pulso 1.6s ease-in-out infinite' : undefined }}
                onClick={() => m.foto_id && !dibujando && onAbrir(m.foto_id)} />
            </Tooltip>
          })}
          {rect && <rect x={rect.x} y={rect.y} width={rect.w} height={rect.h} fill="#2563EB" fillOpacity={0.25} stroke="#60A5FA" strokeWidth={2} vectorEffect="non-scaling-stroke" />}
        </svg>
        {marcas.map((m: any, i: number) => {
          const color = colorPct(m.ocupacion_pct)
          return (
            <Box key={i} sx={{ position: 'absolute', left: `${(m.x + m.w / 2) * 100}%`, top: `${(m.y + m.h / 2) * 100}%`, transform: 'translate(-50%, -50%)', pointerEvents: 'none',
              display: 'flex', alignItems: 'center', gap: 0.5, px: 0.6, py: 0.1, borderRadius: 1, whiteSpace: 'nowrap',
              bgcolor: alpha('#FFFFFF', 0.95), border: `1px solid ${alpha(color, 0.8)}`, boxShadow: '0 1px 4px rgba(15,23,42,0.15)' }}>
              <Typography sx={{ fontFamily: 'Consolas, monospace', fontSize: 11, fontWeight: 800, color: '#0F172A' }}>{m.etiqueta}</Typography>
              {m.ocupacion_pct != null && <>
                <Box sx={{ width: 34, height: 4, borderRadius: 2, bgcolor: alpha('#94A3B8', 0.25), overflow: 'hidden' }}>
                  <Box sx={{ height: '100%', width: `${Math.min(100, m.ocupacion_pct)}%`, bgcolor: color }} /></Box>
                <Typography sx={{ fontFamily: 'Consolas, monospace', fontSize: 10.5, fontWeight: 700, color }}>{m.ocupacion_pct}%</Typography>
              </>}
            </Box>
          )
        })}
      </Box>}
      <Dialog open={!!rect && !inicio && dibujando && rect.w > 0.005} onClose={() => setRect(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Marcar estantería</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
          <TextField size="small" label="Etiqueta (p. ej. Pasillo 3)" value={marca.etiqueta} onChange={e => setMarca({ ...marca, etiqueta: e.target.value })} />
          <TextField select size="small" label="Foto de la estantería" value={marca.foto_id} onChange={e => setMarca({ ...marca, foto_id: Number(e.target.value) })}>
            {fotos.map(f => <MenuItem key={f.id} value={f.id}>{f.nombre}</MenuItem>)}
          </TextField>
        </DialogContent>
        <DialogActions><Button color="inherit" onClick={() => setRect(null)}>Cancelar</Button><Button disabled={!marca.etiqueta.trim()} onClick={guardarMarca}>Guardar</Button></DialogActions>
      </Dialog>
    </Box>
  )
}

export default function WMSMapa() {
  const qc = useQueryClient()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>('')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const fotos = useQuery({ queryKey: ['mapa-fotos', almacen], enabled: !!almacen, queryFn: () => api.get('/wms/mapa/fotos', { params: { almacen_id: almacen } }).then(r => r.data) })
  const plano = useQuery({ queryKey: ['mapa-plano', almacen], enabled: !!almacen, queryFn: () => api.get('/wms/mapa/plano', { params: { almacen_id: almacen } }).then(r => r.data) })
  const ocupacionFoto = useMemo(() => new Map<number, number | null>((plano.data?.marcas ?? []).filter((m: any) => m.foto_id).map((m: any) => [m.foto_id, m.ocupacion_pct])), [plano.data])
  const [tab, setTab] = useState(0)
  const [foto, setFoto] = useState<number | null>(null)
  const [estructura, setEstructura] = useState<number | null>(null)
  const [editar, setEditar] = useState<number | null>(null)
  const estructuras = useQuery({ queryKey: ['layout-estructuras', almacen], enabled: !!almacen && tab === 3,
    queryFn: () => api.get('/wms/layout/estructuras', { params: { almacen_id: almacen } }).then(r => r.data as any[]) })
  const fotosLigadas = new Set((estructuras.data ?? []).map(e => e.foto_id).filter(Boolean))
  const fotosSueltas = (fotos.data ?? []).filter((f: any) => !fotosLigadas.has(f.id))
  const verFoto = (id: number) => { setFoto(id); setEstructura(null) }
  const verEstructura = (id: number) => { setEstructura(id); setFoto(null) }
  // Al abrir una foto que pertenece a una estructura, mostrar la estructura.
  useEffect(() => {
    if (!foto || !estructuras.data) return
    const e = estructuras.data.find(x => x.foto_id === foto)
    if (e) { setEstructura(e.id); setFoto(null) }
  }, [foto, estructuras.data])
  useEffect(() => {
    if (tab === 3 && !foto && !estructura && estructuras.data?.length) setEstructura(estructuras.data[0].id)
  }, [tab, foto, estructura, estructuras.data])
  const [nueva, setNueva] = useState<{ archivo: File | null; nombre: string; pasillo: string; estanteria: string } | null>(null)
  const [q, setQ] = useState('')
  const [busqueda, setBusqueda] = useState<any>(null)
  const subir = async () => {
    const fd = new FormData()
    fd.append('almacen_id', String(almacen)); fd.append('nombre', nueva!.nombre); fd.append('archivo', nueva!.archivo!)
    if (nueva!.pasillo) fd.append('pasillo', nueva!.pasillo)
    if (nueva!.estanteria) fd.append('estanteria', nueva!.estanteria)
    try { const r = await api.post('/wms/mapa/fotos', fd).then(r => r.data); toast.success('Foto cargada: ahora calibre su cuadrícula'); setNueva(null)
      qc.invalidateQueries({ queryKey: ['mapa-fotos'] }); setFoto(r.id); setTab(3) } catch (e) { toast.error(errorApi(e)) }
  }
  const buscar = async () => {
    if (!q.trim()) { setBusqueda(null); return }
    try { const r = await api.get('/wms/mapa/buscar', { params: { almacen_id: almacen, q } }).then(r => r.data); setBusqueda(r)
      if (r.fotos.length) { setFoto(r.fotos[0].foto_id); if (tab !== 0) setTab(3) } } catch (e) { toast.error(errorApi(e)) }
  }
  return (
    <Layout title="WMS — Mapa de la bodega">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<MapaIcon sx={{ fontSize: 28 }} />} titulo="Mapa de la bodega · gemelo digital" color={COLOR}
          subtitulo="Planos y estanterías vectorizados con la ocupación del inventario en vivo" />
        <Stack direction="row" gap={1.5} mb={2} flexWrap="wrap" alignItems="center">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => { setAlmacen(Number(e.target.value)); setFoto(null); setEstructura(null); setBusqueda(null) }} sx={{ minWidth: 240 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <TextField size="small" label="¿Dónde está? (SKU, nombre o código)" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') buscar() }}
            InputProps={{ endAdornment: <Search fontSize="small" /> }} sx={{ minWidth: 300 }} />
          <Box flex={1} />
          <Button variant="contained" startIcon={<AddPhotoAlternate />} sx={{ bgcolor: COLOR }} onClick={() => setNueva({ archivo: null, nombre: '', pasillo: '', estanteria: '' })}>Cargar foto de estantería</Button>
        </Stack>
        {busqueda && <Alert severity={busqueda.fotos.length ? 'info' : 'warning'} sx={{ mb: 2 }} onClose={() => { setBusqueda(null); setQ('') }}>
          {busqueda.productos.length ? <>{busqueda.productos.map((p: any) => p.sku).join(', ')}: en {busqueda.ubicaciones} ubicaciones
            {busqueda.fotos.length ? ` · fotos: ${busqueda.fotos.map((f: any) => `${f.nombre} (${f.celdas.length})`).join(', ')}` : ''}
            {busqueda.fuera_del_mapa ? ` · ${busqueda.fuera_del_mapa} no están en ninguna foto` : ''}</> : 'Ningún producto coincide.'}
        </Alert>}
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Bodega 3D" /><Tab label="Constructor" /><Tab label="Plano" /><Tab label="Estanterías" /></Tabs>
        {!!almacen && tab === 0 && <Bodega3D almacen={Number(almacen)} productoId={busqueda?.productos?.[0]?.id} onAbrir={id => { setFoto(id); setTab(3) }}
          onEditar={id => { setEditar(id); setTab(1) }} />}
        {!!almacen && tab === 1 && <ConstructorBodega key={almacen} almacen={Number(almacen)} seleccionInicial={editar} onVer3D={() => { setEditar(null); setTab(0) }} />}
        {!!almacen && tab === 2 && <Plano almacen={Number(almacen)} fotos={fotos.data ?? []} onAbrir={id => { setFoto(id); setTab(3) }} />}
        {!!almacen && tab === 3 && <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 3 }}>
            <Stack gap={1}>
              {(estructuras.data ?? []).length > 0 && <Typography sx={{ fontSize: 10.5, letterSpacing: '0.1em', fontWeight: 800, color: 'text.secondary' }}>ESTRUCTURAS DEL LAYOUT</Typography>}
              {(estructuras.data ?? []).map((e: any) => {
                const activa = estructura === e.id, pct = e.ocupacion_pct
                return (
                  <Paper key={`e${e.id}`} variant="outlined" role="button" aria-label={`Estructura ${e.nombre}`} onClick={() => verEstructura(e.id)}
                    sx={{ p: 1.25, borderRadius: 2, cursor: 'pointer', bgcolor: activa ? alpha(NEON.cian, 0.06) : undefined,
                      borderColor: activa ? NEON.cian : undefined, transition: 'all .15s' }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      <Typography fontSize={13} fontWeight={700} sx={{ color: activa ? NEON.cian : undefined }}>{e.nombre}</Typography>
                      <Stack direction="row" gap={0.5} alignItems="center">
                        {e.foto_id && <PhotoCamera sx={{ fontSize: 14, color: '#94A3B8' }} />}
                        <Architecture sx={{ fontSize: 15, color: activa ? NEON.cian : '#94A3B8' }} />
                      </Stack>
                    </Stack>
                    <Typography fontSize={11.5} sx={{ color: 'text.secondary', fontFamily: 'Consolas, monospace' }}>
                      {e.niveles_vista}×{e.posiciones} · {e.vinculadas}/{e.niveles_vista * e.posiciones} ubicaciones{e.pasillo ? ` · pasillo ${e.pasillo}` : ''}
                    </Typography>
                    <Box sx={{ mt: 0.75, height: 4, borderRadius: 2, bgcolor: alpha('#94A3B8', 0.25), overflow: 'hidden' }}>
                      <Box sx={{ height: '100%', width: `${Math.min(100, pct ?? 0)}%`, bgcolor: colorPct(pct) }} /></Box>
                  </Paper>
                )
              })}
              {(estructuras.data ?? []).length > 0 && fotosSueltas.length > 0 && <Typography sx={{ fontSize: 10.5, letterSpacing: '0.1em', fontWeight: 800, color: 'text.secondary', mt: 1 }}>FOTOS SIN ESTRUCTURA</Typography>}
              {fotosSueltas.map((f: any) => {
                const pct = ocupacionFoto.get(f.id)
                const activa = foto === f.id
                return (
                  <Paper key={f.id} variant="outlined" role="button" aria-label={`Estantería ${f.nombre}`} onClick={() => verFoto(f.id)}
                    sx={{ p: 1.25, borderRadius: 2, cursor: 'pointer', bgcolor: activa ? alpha(NEON.cian, 0.06) : undefined,
                      borderColor: activa ? NEON.cian : undefined, transition: 'all .15s' }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      <Typography fontSize={13} fontWeight={700} sx={{ color: activa ? NEON.cian : undefined }}>{f.nombre}</Typography>
                      {f.vectorizada && <ViewInAr sx={{ fontSize: 15, color: activa ? NEON.cian : '#94A3B8' }} />}
                    </Stack>
                    <Typography fontSize={11.5} sx={{ color: 'text.secondary', fontFamily: 'Consolas, monospace' }}>
                      {f.calibrada ? `${f.filas}×${f.columnas} · ${f.celdas_asignadas} celdas` : 'Sin calibrar'}{f.pasillo ? ` · pasillo ${f.pasillo}` : ''}
                    </Typography>
                    {pct != null && <Box sx={{ mt: 0.75, height: 4, borderRadius: 2, bgcolor: alpha('#94A3B8', 0.25), overflow: 'hidden' }}>
                      <Box sx={{ height: '100%', width: `${Math.min(100, pct)}%`, bgcolor: colorPct(pct) }} /></Box>}
                  </Paper>
                )
              })}
              {fotos.data && estructuras.data && !fotos.data.length && !estructuras.data.length && <Alert severity="info" action={<Button size="small" color="inherit" onClick={() => setTab(1)}>Constructor</Button>}>
                Arme las estanterías en el constructor (o cargue la foto frontal de cada una).</Alert>}
            </Stack>
          </Grid>
          <Grid size={{ xs: 12, md: 9 }}>
            {estructura ? <VistaEstructura key={`e${estructura}`} id={estructura} almacen={Number(almacen)} productoId={busqueda?.productos?.[0]?.id}
              onEditar={() => { setEditar(estructura); setTab(1) }} />
              : foto ? <VistaFoto key={foto} fotoId={foto} almacen={Number(almacen)} productoId={busqueda?.productos?.[0]?.id}
              onCalibrada={() => qc.invalidateQueries({ queryKey: ['mapa-fotos'] })} />
              : <Alert severity="info" icon={<Straighten />}>Elija una estantería.</Alert>}
          </Grid>
        </Grid>}
        <Dialog open={!!nueva} onClose={() => setNueva(null)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Foto de una estantería</DialogTitle>
          <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
            <Typography fontSize={13} color="text.secondary">Tómela de frente, con toda la cara de la estantería a la vista. Al calibrarla, se endereza y se convierte a SVG.</Typography>
            <Button component="label" variant="outlined" startIcon={<AddPhotoAlternate />}>{nueva?.archivo ? nueva.archivo.name : 'Elegir foto'}
              <input hidden type="file" accept="image/*" aria-label="Archivo de la foto" onChange={e => e.target.files?.[0] && setNueva(n => n && ({ ...n, archivo: e.target.files![0], nombre: n.nombre || e.target.files![0].name.replace(/\.[^.]+$/, '') }))} /></Button>
            <TextField size="small" label="Nombre (p. ej. Pasillo 3 · frente)" value={nueva?.nombre ?? ''} onChange={e => setNueva(n => n && ({ ...n, nombre: e.target.value }))} />
            <Stack direction="row" gap={1}>
              <TextField size="small" label="Pasillo" value={nueva?.pasillo ?? ''} onChange={e => setNueva(n => n && ({ ...n, pasillo: e.target.value }))} />
              <TextField size="small" label="Estantería" value={nueva?.estanteria ?? ''} onChange={e => setNueva(n => n && ({ ...n, estanteria: e.target.value }))} />
            </Stack>
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setNueva(null)}>Cancelar</Button>
            <Button variant="contained" sx={{ bgcolor: COLOR }} disabled={!nueva?.archivo || !nueva.nombre.trim()} onClick={subir}>Cargar</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
