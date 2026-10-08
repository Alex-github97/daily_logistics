/**
 * Constructor de bodega (WMS › Mapa de la bodega › Constructor).
 *
 * Editor en metros, estilo CAD: se arrastran estructuras desde la paleta
 * (rack selectivo, góndola, cantiléver, piso, áreas, muros, columnas) sobre el
 * plano del almacén, que queda de fondo para calcar. Cada estructura se
 * configura con parámetros (módulos, posiciones por módulo, niveles, medidas)
 * y de ahí salen las ubicaciones del WMS (botón «Generar ubicaciones», con
 * simulación previa) y la bodega 3D.
 *
 * Atajos: V seleccionar · H mano · M medir · R rotar 90° · Supr eliminar ·
 * Ctrl+D duplicar · Ctrl+C / Ctrl+V · Ctrl+Z / Ctrl+Y · Ctrl+A · Ctrl+S guardar ·
 * flechas mover (Shift = 1 m) · F encuadrar · Espacio + arrastrar = desplazar ·
 * Alt al arrastrar = sin imán.
 */
import type React from 'react'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Alert, Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider,
  FormControlLabel, IconButton, InputAdornment, LinearProgress, MenuItem, Slider, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, ToggleButton, ToggleButtonGroup, Tooltip, Typography, alpha,
} from '@mui/material'
import {
  NearMe, PanTool, Straighten, Undo, Redo, ContentCopy, DeleteOutline, RotateRight, ZoomIn, ZoomOut, FitScreen,
  GridOn, Save, AutoFixHigh, ViewInAr, Fullscreen, FullscreenExit, AlignHorizontalLeft, AlignHorizontalCenter,
  AlignHorizontalRight, AlignVerticalTop, AlignVerticalCenter, AlignVerticalBottom, ViewColumn as HorizontalDistribute,
  TableRows as VerticalDistribute, CalendarViewWeek, CloudDownload, Search, Layers, Tune, Close, WarningAmber, CheckCircle,
  SquareFoot,
} from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { TextField } from '@/components/comun/Desplegables'
import { errorApi } from '@/components/comun/Registro'
import { apiClient as api } from '@/api/client'

// ═════════════════════════════════════════════════════════════════════════════
// Modelo
// ═════════════════════════════════════════════════════════════════════════════
type Tipo = 'SELECTIVO' | 'GONDOLA' | 'CANTILEVER' | 'PISO' | 'ZONA' | 'MURO' | 'COLUMNA'
interface El {
  clave: string; id?: number; tipo: Tipo; nombre: string | null; pasillo: string | null; estanteria: string | null
  zona_id: number | null; ubicacion_id: number | null; foto_id: number | null; categoria: string | null; color: string | null
  x_m: number; y_m: number; rotacion: number; modulos: number; por_modulo: number; niveles: number
  frente_cm: number; fondo_cm: number; alto_nivel_cm: number; capacidad_kg: number | null; largo_m: number | null; ancho_m: number | null
  // del servidor (solo lectura)
  vinculadas?: number; ocupadas?: number; ocupacion_pct?: number | null; codigos?: string[]; sobrantes?: number
}
interface Config { ancho_m: number; largo_m: number; escala_m_px: number | null; plano_x_m: number; plano_y_m: number; patron_codigo: string }
interface Datos {
  almacen: { id: number; codigo: string; nombre: string }
  config: Config | null; elementos: (Omit<El, 'clave'> & { id: number })[]
  plano: { id: number; ancho: number; alto: number; vectorizado: boolean } | null
  zonas: { id: number; codigo: string; nombre: string; tipo: string }[]
  ubicaciones_area: { id: number; codigo: string }[]
  fotos: { id: number; nombre: string }[]
}

const CON_POSICIONES: Tipo[] = ['SELECTIVO', 'GONDOLA', 'CANTILEVER', 'PISO']
const esEstructura = (e: El) => CON_POSICIONES.includes(e.tipo)
const PALETA = ['#0EA5E9', '#8B5CF6', '#10B981', '#EC4899', '#F59E0B', '#3B82F6', '#F97316', '#14B8A6', '#A855F7', '#EF4444']
const ACENTO = '#4F46E5'
const GUIA = '#EC4899'

const CATALOGO: Record<Tipo, { nombre: string; desc: string; base: Partial<El> }> = {
  SELECTIVO: { nombre: 'Rack selectivo', desc: 'Estibas · vanos de 2,7 m', base: { modulos: 3, por_modulo: 1, niveles: 4, frente_cm: 270, fondo_cm: 100, alto_nivel_cm: 150, capacidad_kg: 1000 } },
  GONDOLA: { nombre: 'Góndola / estantería', desc: 'Carga liviana · picking', base: { modulos: 4, por_modulo: 1, niveles: 5, frente_cm: 100, fondo_cm: 50, alto_nivel_cm: 40, capacidad_kg: 80 } },
  CANTILEVER: { nombre: 'Cantiléver', desc: 'Tubos, perfiles, madera', base: { modulos: 3, por_modulo: 1, niveles: 4, frente_cm: 150, fondo_cm: 120, alto_nivel_cm: 100, capacidad_kg: 500 } },
  PISO: { nombre: 'Almacenamiento en piso', desc: 'Bloques de estibas apiladas', base: { modulos: 4, por_modulo: 1, niveles: 3, frente_cm: 120, fondo_cm: 100, alto_nivel_cm: 150, capacidad_kg: 1500 } },
  ZONA: { nombre: 'Área', desc: 'Recepción, despacho, staging…', base: { largo_m: 10, ancho_m: 6, categoria: 'RECEPCION' } },
  MURO: { nombre: 'Muro', desc: 'Cerramientos y divisiones', base: { largo_m: 10, ancho_m: 0.3 } },
  COLUMNA: { nombre: 'Columna', desc: 'Estructura del edificio', base: { largo_m: 0.5, ancho_m: 0.5 } },
}
const AREAS: Record<string, { nombre: string; color: string }> = {
  RECEPCION: { nombre: 'Recepción', color: '#F59E0B' }, DESPACHO: { nombre: 'Despacho', color: '#10B981' },
  STAGING: { nombre: 'Staging', color: '#06B6D4' }, CUARENTENA: { nombre: 'Cuarentena', color: '#EF4444' },
  SALA_VENTAS: { nombre: 'Sala de ventas', color: '#8B5CF6' }, MUELLE: { nombre: 'Muelle', color: '#64748B' },
  PASILLO: { nombre: 'Pasillo / vía', color: '#EAB308' }, OFICINAS: { nombre: 'Oficinas', color: '#94A3B8' },
  SERVICIOS: { nombre: 'Servicios', color: '#A8A29E' }, OTRA: { nombre: 'Otra', color: '#3B82F6' },
}

const rad = (g: number) => (g * Math.PI) / 180
const r2 = (n: number) => Math.round(n * 100) / 100
const fmt = (n: number, d = 1) => n.toLocaleString('es-CO', { maximumFractionDigits: d })
let contador = 0
const nuevaClave = () => `n${++contador}`

function dims(e: El): [number, number] {
  if (esEstructura(e)) return [(e.modulos * e.frente_cm) / 100, e.fondo_cm / 100]
  return [e.largo_m ?? 4, e.ancho_m ?? 4]
}
function aLocal(e: El, wx: number, wy: number): [number, number] {
  const r = -rad(e.rotacion), dx = wx - e.x_m, dy = wy - e.y_m
  return [dx * Math.cos(r) - dy * Math.sin(r), dx * Math.sin(r) + dy * Math.cos(r)]
}
function aMundo(e: El, lx: number, ly: number): [number, number] {
  const r = rad(e.rotacion)
  return [e.x_m + lx * Math.cos(r) - ly * Math.sin(r), e.y_m + lx * Math.sin(r) + ly * Math.cos(r)]
}
function caja(e: El) {
  const [L, F] = dims(e)
  const pts = [[-L / 2, -F / 2], [L / 2, -F / 2], [L / 2, F / 2], [-L / 2, F / 2]].map(([x, y]) => aMundo(e, x, y))
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1])
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) }
}
function contiene(e: El, wx: number, wy: number, holgura = 0) {
  const [L, F] = dims(e), [lx, ly] = aLocal(e, wx, wy)
  return Math.abs(lx) <= L / 2 + holgura && Math.abs(ly) <= F / 2 + holgura
}
const posicionesDe = (e: El) => (esEstructura(e) ? e.modulos * e.por_modulo * (e.tipo === 'PISO' ? 1 : e.niveles) : 0)
const nombreDe = (e: El) => e.nombre || (esEstructura(e) ? [e.pasillo, e.estanteria].filter(Boolean).join('-') : CATALOGO[e.tipo].nombre) || CATALOGO[e.tipo].nombre
const ORDEN_DIBUJO: Record<Tipo, number> = { ZONA: 0, PISO: 1, MURO: 2, COLUMNA: 3, CANTILEVER: 4, GONDOLA: 5, SELECTIVO: 6 }

function colorDe(e: El, indice: Map<string, number>): string {
  if (e.color) return e.color
  if (e.tipo === 'ZONA') return AREAS[e.categoria ?? 'OTRA']?.color ?? AREAS.OTRA.color
  if (e.tipo === 'MURO') return '#475569'
  if (e.tipo === 'COLUMNA') return '#334155'
  return PALETA[(indice.get(e.clave) ?? 0) % PALETA.length]
}

function siguiente(texto: string | null, paso = 1): string | null {
  if (!texto) return texto
  const m = texto.match(/^(.*?)(\d+)$/)
  if (m) return m[1] + String(Number(m[2]) + paso).padStart(m[2].length, '0')
  if (/^[A-Z]$/.test(texto)) return String.fromCharCode(Math.min(90, texto.charCodeAt(0) + paso))
  return texto
}

function codigoEjemplo(patron: string, alm: string, e: Partial<El>, zona = 'ZONA', nivel = 1, posicion = 1) {
  try {
    return patron.replace(/\{(\w+)(?::0?(\d+)d)?\}/g, (_, k: string, ancho?: string) => {
      const v: any = { almacen: alm, zona, pasillo: e.pasillo ?? '', estanteria: e.estanteria ?? '', nivel, posicion }[k]
      if (v === undefined) throw new Error(k)
      return ancho ? String(v).padStart(Number(ancho), '0') : String(v)
    }).replace(/^[-_. ]+|[-_. ]+$/g, '')
  } catch { return '— patrón inválido —' }
}

/** Imagen protegida (con sesión) como blob. */
function useBlob(ruta: string | null) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!ruta) { setUrl(null); return }
    let vivo = true, creado: string | null = null
    api.get(ruta, { responseType: 'blob' }).then(r => { if (vivo) { creado = URL.createObjectURL(r.data); setUrl(creado) } }).catch(() => vivo && setUrl(null))
    return () => { vivo = false; if (creado) URL.revokeObjectURL(creado) }
  }, [ruta])
  return url
}

// ═════════════════════════════════════════════════════════════════════════════
// Iconos de la paleta
// ═════════════════════════════════════════════════════════════════════════════
function IconoTipo({ tipo, size = 44 }: { tipo: Tipo; size?: number }) {
  const s = { width: size, height: size * 0.72 }
  const comun = { fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  switch (tipo) {
    case 'SELECTIVO': return <svg viewBox="0 0 44 32" style={s}>
      {[6, 18, 30, 40].map(x => <line key={x} x1={x} y1={4} x2={x} y2={29} stroke="#475569" strokeWidth={2} />)}
      {[10, 18, 26].map(y => <line key={y} x1={5} y1={y} x2={41} y2={y} stroke="#F97316" strokeWidth={2.4} />)}
      <rect x={8} y={12} width={8} height={5.5} rx={0.8} fill="#0EA5E9" opacity={0.85} /><rect x={20} y={20} width={8} height={5.5} rx={0.8} fill="#0EA5E9" opacity={0.85} />
      <rect x={32} y={4} width={7} height={5.5} rx={0.8} fill="#0EA5E9" opacity={0.5} /></svg>
    case 'GONDOLA': return <svg viewBox="0 0 44 32" style={s}>
      <rect x={5} y={4} width={34} height={25} rx={1.5} {...comun} stroke="#475569" strokeWidth={1.8} />
      {[10, 15, 20, 25].map(y => <line key={y} x1={5} y1={y} x2={39} y2={y} stroke="#94A3B8" strokeWidth={1.6} />)}
      {[[8, 6], [14, 11], [22, 16], [30, 21], [12, 21], [27, 6]].map(([x, y], i) => <rect key={i} x={x} y={y + 0.5} width={4} height={3.5} rx={0.6} fill="#8B5CF6" opacity={0.8} />)}</svg>
    case 'CANTILEVER': return <svg viewBox="0 0 44 32" style={s}>
      {[12, 30].map(x => <g key={x}><line x1={x} y1={4} x2={x} y2={29} stroke="#475569" strokeWidth={2.4} />
        {[9, 16, 23].map(y => <line key={y} x1={x} y1={y} x2={x + 9} y2={y - 1.5} stroke="#64748B" strokeWidth={1.8} />)}</g>)}
      {[8.5, 15.5].map(y => <line key={y} x1={10} y1={y} x2={42} y2={y} stroke="#B45309" strokeWidth={2} />)}
      <line x1={4} y1={29.5} x2={40} y2={29.5} stroke="#475569" strokeWidth={2} /></svg>
    case 'PISO': return <svg viewBox="0 0 44 32" style={s}>
      {[[5, 17], [17, 17], [29, 17], [5, 6], [17, 6]].map(([x, y], i) => <g key={i}>
        <rect x={x} y={y} width={10} height={9} rx={0.8} fill="#10B981" opacity={i > 2 ? 0.55 : 0.85} />
        <rect x={x} y={y + 9} width={10} height={1.8} fill="#A16207" /></g>)}
      <rect x={3} y={3} width={38} height={27} rx={2} {...comun} stroke="#94A3B8" strokeDasharray="3 2" /></svg>
    case 'ZONA': return <svg viewBox="0 0 44 32" style={s}>
      <rect x={4} y={4} width={36} height={24} rx={2.5} fill="#F59E0B" fillOpacity={0.15} stroke="#F59E0B" strokeWidth={1.8} strokeDasharray="4 2.5" />
      <line x1={10} y1={13} x2={30} y2={13} stroke="#B45309" strokeWidth={2} /><line x1={10} y1={19} x2={23} y2={19} stroke="#D97706" strokeWidth={1.6} opacity={0.7} /></svg>
    case 'MURO': return <svg viewBox="0 0 44 32" style={s}>
      <path d="M5 26 V7 H39 V26" {...comun} stroke="#475569" strokeWidth={4.5} /><path d="M17 26 v-8 h10 v8" {...comun} stroke="#CBD5E1" strokeWidth={1.4} /></svg>
    case 'COLUMNA': return <svg viewBox="0 0 44 32" style={s}>
      {[[9, 7], [29, 7], [9, 21], [29, 21]].map(([x, y], i) => <rect key={i} x={x} y={y} width={5} height={5} fill="#334155" />)}
      <rect x={4} y={3} width={36} height={26} rx={1.5} {...comun} stroke="#CBD5E1" strokeDasharray="2 2" /></svg>
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Campos del inspector
// ═════════════════════════════════════════════════════════════════════════════
function Numero({ etiqueta, valor, onCambio, unidad, min, max, paso = 1, decimales = 2, ancho }: {
  etiqueta: string; valor: number | null; onCambio: (v: number | null) => void; unidad?: string; min?: number; max?: number
  paso?: number; decimales?: number; ancho?: number | string
}) {
  const [texto, setTexto] = useState(valor == null ? '' : String(r2(valor)))
  const editando = useRef(false)
  useEffect(() => { if (!editando.current) setTexto(valor == null ? '' : String(Math.round(valor * 10 ** decimales) / 10 ** decimales)) }, [valor, decimales])
  return (
    <TextField size="small" label={etiqueta} value={texto} type="number" sx={{ width: ancho ?? '100%' }}
      inputProps={{ step: paso, min, max, style: { fontFamily: 'Consolas, monospace', fontSize: 13 } }}
      InputProps={unidad ? { endAdornment: <InputAdornment position="end"><Typography fontSize={11.5} color="text.secondary">{unidad}</Typography></InputAdornment> } : undefined}
      onFocus={() => { editando.current = true }}
      onBlur={() => { editando.current = false; setTexto(valor == null ? '' : String(r2(valor))) }}
      onChange={e => {
        setTexto(e.target.value)
        if (e.target.value === '') { onCambio(null); return }
        const n = Number(e.target.value)
        if (Number.isFinite(n) && (min == null || n >= min) && (max == null || n <= max)) onCambio(n)
      }} />
  )
}

function Seccion({ titulo, children, accion }: { titulo: string; children: ReactNode; accion?: ReactNode }) {
  return (
    <Box sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
      <Stack direction="row" alignItems="center" mb={1.1}>
        <Typography sx={{ fontSize: 10.5, letterSpacing: '0.1em', fontWeight: 800, color: 'text.secondary', textTransform: 'uppercase', flex: 1 }}>{titulo}</Typography>
        {accion}
      </Stack>
      {children}
    </Box>
  )
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <Box sx={{ px: 1.1, py: 0.8, borderRadius: 1.5, bgcolor: '#F8FAFC', border: '1px solid', borderColor: 'divider' }}>
      <Typography sx={{ fontSize: 10.5, color: 'text.secondary' }}>{etiqueta}</Typography>
      <Typography sx={{ fontSize: 14, fontWeight: 800, fontFamily: 'Consolas, monospace' }}>{valor}</Typography>
    </Box>
  )
}

function Herramienta({ titulo, atajo, activo, onClick, disabled, children }: {
  titulo: string; atajo?: string; activo?: boolean; onClick: () => void; disabled?: boolean; children: ReactNode
}) {
  return (
    <Tooltip arrow title={<Stack direction="row" gap={1} alignItems="center">{titulo}{atajo && <Box component="kbd" sx={{ px: 0.6, py: 0.1, borderRadius: 0.75,
      bgcolor: 'rgba(255,255,255,0.18)', fontFamily: 'Consolas, monospace', fontSize: 11 }}>{atajo}</Box>}</Stack>}>
      <span>
        <IconButton size="small" aria-label={titulo} onClick={onClick} disabled={disabled}
          sx={{ borderRadius: 1.5, width: 34, height: 34, color: activo ? ACENTO : '#334155', bgcolor: activo ? alpha(ACENTO, 0.1) : 'transparent',
            '&:hover': { bgcolor: activo ? alpha(ACENTO, 0.16) : '#F1F5F9' } }}>{children}</IconButton>
      </span>
    </Tooltip>
  )
}
const Separador = () => <Divider orientation="vertical" flexItem sx={{ mx: 0.75, my: 0.5 }} />

// ═════════════════════════════════════════════════════════════════════════════
// Constructor
// ═════════════════════════════════════════════════════════════════════════════
type Modo = 'seleccionar' | 'mano' | 'medir' | 'calibrar' | `colocar:${Tipo}`
type Arrastre =
  | { tipo: 'pan'; sx: number; sy: number; pan0: { x: number; y: number } }
  | { tipo: 'mover'; wx: number; wy: number; origen: Map<string, [number, number]>; primero: string; antes: Snap; movido: boolean }
  | { tipo: 'marco'; wx: number; wy: number; cx: number; cy: number; sumar: boolean }
  | { tipo: 'rotar'; clave: string; antes: Snap }
  | { tipo: 'estirar'; clave: string; esquina: [number, number]; orig: El; antes: Snap }
  | { tipo: 'regla'; a: [number, number]; b: [number, number] }
interface Snap { els: El[]; config: Config }

const REGLA = 24

export default function ConstructorBodega({ almacen, onVer3D, seleccionInicial }: { almacen: number; onVer3D?: () => void; seleccionInicial?: number | null }) {
  const qc = useQueryClient()
  const datos = useQuery<Datos>({ queryKey: ['wms-layout', almacen], queryFn: () => api.get('/wms/layout', { params: { almacen_id: almacen } }).then(r => r.data) })
  const d = datos.data

  // ── estado del documento ──
  const [els, setEls] = useState<El[]>([])
  const [config, setConfig] = useState<Config>({ ancho_m: 40, largo_m: 30, escala_m_px: null, plano_x_m: 0, plano_y_m: 0, patron_codigo: '{pasillo}-{estanteria}-{posicion}-{nivel}' })
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [sucio, setSucio] = useState(false)
  const pasado = useRef<Snap[]>([]), futuro = useRef<Snap[]>([])
  const [, setVersion] = useState(0)
  const ultimaFusion = useRef<{ clave: string; t: number } | null>(null)
  const portapapeles = useRef<El[]>([])

  // ── vista ──
  const lienzo = useRef<HTMLDivElement>(null)
  const raiz = useRef<HTMLDivElement>(null)
  const [tam, setTam] = useState({ w: 0, h: 0 })
  const [zoom, setZoom] = useState(12)            // px por metro
  const [pan, setPan] = useState({ x: 60, y: 60 })
  const [modo, setModo] = useState<Modo>('seleccionar')
  const [arrastre, setArrastre] = useState<Arrastre | null>(null)
  const [cursor, setCursor] = useState<[number, number] | null>(null)
  const [guias, setGuias] = useState<{ x?: number; y?: number }>({})
  const [iman, setIman] = useState(true)
  const [paso, setPaso] = useState(0.1)
  const [verPlano, setVerPlano] = useState<'original' | 'vector' | 'oculto'>('original')
  const [opacidadPlano, setOpacidadPlano] = useState(0.55)
  const [verOcupacion, setVerOcupacion] = useState(false)
  const [completa, setCompleta] = useState(false)
  const [buscar, setBuscar] = useState('')
  const espacio = useRef(false)

  // ── diálogos ──
  const [serie, setSerie] = useState<{ cantidad: number; modo: 'espalda' | 'simple'; pasillo: number; espalda: number; direccion: 1 | -1; numerar: 'estanteria' | 'pasillo' } | null>(null)
  const [calibrar, setCalibrar] = useState<{ medido: number; real: string } | null>(null)
  const [generar, setGenerar] = useState<{ cargando: boolean; renombrar: boolean; res?: any } | null>(null)
  const [guardando, setGuardando] = useState(false)

  const planoRuta = d?.plano ? (verPlano === 'vector' && d.plano.vectorizado ? `/wms/mapa/plano/${d.plano.id}/svg` : `/wms/mapa/plano/${d.plano.id}/imagen`) : null
  const planoUrl = useBlob(verPlano === 'oculto' ? null : planoRuta)

  // ── cargar del servidor ──
  const cargar = useCallback((x: Datos, conservarSeleccion = false) => {
    const lista: El[] = x.elementos.map(e => ({ ...e, clave: `e${e.id}` } as El))
    setEls(lista)
    const cfg = x.config ?? { ancho_m: 40, largo_m: 30, escala_m_px: null, plano_x_m: 0, plano_y_m: 0, patron_codigo: '{pasillo}-{estanteria}-{posicion}-{nivel}' }
    if (!x.config && x.plano) cfg.escala_m_px = cfg.ancho_m / x.plano.ancho
    setConfig(cfg)
    if (!conservarSeleccion) setSel(new Set())
    pasado.current = []; futuro.current = []; setSucio(false); setVersion(v => v + 1)
  }, [])
  const cargado = useRef<number | null>(null)
  useEffect(() => {
    if (!d || cargado.current === almacen) return
    cargado.current = almacen
    cargar(d)
    if (seleccionInicial) setSel(new Set([`e${seleccionInicial}`]))
  }, [d, almacen, cargar, seleccionInicial])

  // tamaño del lienzo
  useEffect(() => {
    const el = lienzo.current
    if (!el) return
    const ro = new ResizeObserver(() => setTam({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [d])     // el lienzo aparece cuando llegan los datos

  const encuadrar = useCallback((caja?: { x0: number; y0: number; x1: number; y1: number }) => {
    const b = caja ?? { x0: 0, y0: 0, x1: config.ancho_m, y1: config.largo_m }
    const w = Math.max(1, b.x1 - b.x0), h = Math.max(1, b.y1 - b.y0)
    const z = Math.min((tam.w - REGLA - 80) / w, (tam.h - REGLA - 80) / h)
    const zz = Math.max(2, Math.min(200, z))
    setZoom(zz)
    setPan({ x: REGLA + (tam.w - REGLA - w * zz) / 2 - b.x0 * zz, y: REGLA + (tam.h - REGLA - h * zz) / 2 - b.y0 * zz })
  }, [config.ancho_m, config.largo_m, tam.w, tam.h])
  const encuadrado = useRef<number | null>(null)
  useEffect(() => {
    if (d && tam.w > 100 && encuadrado.current !== almacen && config) { encuadrado.current = almacen; encuadrar() }
  }, [d, tam.w, almacen, encuadrar, config])

  // ── historia ──
  const instantanea = (): Snap => ({ els, config })
  const registrar = (antes: Snap = instantanea()) => {
    pasado.current.push(antes); if (pasado.current.length > 200) pasado.current.shift()
    futuro.current = []; setSucio(true); setVersion(v => v + 1)
  }
  const deshacer = () => {
    const s = pasado.current.pop(); if (!s) return
    futuro.current.push(instantanea()); setEls(s.els); setConfig(s.config); setSucio(true); setVersion(v => v + 1)
  }
  const rehacer = () => {
    const s = futuro.current.pop(); if (!s) return
    pasado.current.push(instantanea()); setEls(s.els); setConfig(s.config); setSucio(true); setVersion(v => v + 1)
  }
  /** Cambio desde el inspector: los cambios seguidos del mismo campo se agrupan en un solo deshacer. */
  const cambiar = (claves: string[], parche: Partial<El> | ((e: El) => Partial<El>), campo?: string) => {
    const ahora = Date.now(), k = `${claves.join(',')}:${campo ?? ''}`
    if (!(campo && ultimaFusion.current && ultimaFusion.current.clave === k && ahora - ultimaFusion.current.t < 900)) registrar()
    ultimaFusion.current = campo ? { clave: k, t: ahora } : null
    setSucio(true)
    setEls(prev => prev.map(e => claves.includes(e.clave) ? { ...e, ...(typeof parche === 'function' ? parche(e) : parche) } : e))
  }
  const cambiarConfig = (parche: Partial<Config>, campo?: string) => {
    const ahora = Date.now(), k = `cfg:${campo ?? ''}`
    if (!(campo && ultimaFusion.current && ultimaFusion.current.clave === k && ahora - ultimaFusion.current.t < 900)) registrar()
    ultimaFusion.current = campo ? { clave: k, t: ahora } : null
    setSucio(true); setConfig(c => ({ ...c, ...parche }))
  }

  // ── derivados ──
  const indice = useMemo(() => { const m = new Map<string, number>(); els.filter(esEstructura).forEach((e, i) => m.set(e.clave, i)); return m }, [els])
  const ordenados = useMemo(() => [...els].sort((a, b) => ORDEN_DIBUJO[a.tipo] - ORDEN_DIBUJO[b.tipo]), [els])
  const seleccion = useMemo(() => els.filter(e => sel.has(e.clave)), [els, sel])
  const uno = seleccion.length === 1 ? seleccion[0] : null
  const totales = useMemo(() => {
    const est = els.filter(esEstructura)
    return {
      estructuras: est.length, posiciones: est.reduce((s, e) => s + posicionesDe(e), 0),
      huella: est.reduce((s, e) => { const [L, F] = dims(e); return s + L * F }, 0),
      volumen: est.reduce((s, e) => s + posicionesDe(e) * (e.frente_cm / e.por_modulo) * e.fondo_cm * (e.tipo === 'PISO' ? e.alto_nivel_cm * e.niveles : e.alto_nivel_cm) / 1e6, 0),
      sinZona: est.filter(e => !e.zona_id).length,
    }
  }, [els])

  // ── coordenadas ──
  const aMundoPx = (sx: number, sy: number): [number, number] => [(sx - pan.x) / zoom, (sy - pan.y) / zoom]
  const aPantalla = (wx: number, wy: number): [number, number] => [wx * zoom + pan.x, wy * zoom + pan.y]
  const puntoEvento = (e: React.PointerEvent | PointerEvent | WheelEvent): [number, number] => {
    const b = lienzo.current!.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]
  }
  const ajustar = (v: number, alt = false) => (iman && !alt ? Math.round(v / paso) * paso : v)

  // zoom con la rueda (no pasivo, para evitar el scroll de la página)
  useEffect(() => {
    const el = lienzo.current
    if (!el) return
    const rueda = (e: WheelEvent) => {
      e.preventDefault()
      const b = el.getBoundingClientRect(), sx = e.clientX - b.left, sy = e.clientY - b.top
      setZoom(z0 => {
        const z = Math.max(2, Math.min(250, z0 * Math.exp(-e.deltaY * 0.0016)))
        setPan(p => ({ x: sx - ((sx - p.x) / z0) * z, y: sy - ((sy - p.y) / z0) * z }))
        return z
      })
    }
    el.addEventListener('wheel', rueda, { passive: false })
    return () => el.removeEventListener('wheel', rueda)
  }, [d])

  const tocado = (wx: number, wy: number): El | null => {
    for (let i = ordenados.length - 1; i >= 0; i--) {
      const e = ordenados[i]
      if (contiene(e, wx, wy, e.tipo === 'MURO' || e.tipo === 'COLUMNA' ? 4 / zoom : 0)) return e
    }
    return null
  }

  // ── colocar una estructura nueva ──
  const plantilla = (tipo: Tipo, wx: number, wy: number): El => {
    const base = CATALOGO[tipo].base
    const ultimo = [...els].reverse().find(e => e.tipo === tipo) ?? [...els].reverse().find(esEstructura)
    let pasillo = ultimo?.pasillo ?? 'A', estanteria: string | null = null, zona_id = ultimo?.zona_id ?? null
    if (CON_POSICIONES.includes(tipo)) {
      const usados = new Set(els.filter(e => e.pasillo === pasillo).map(e => e.estanteria))
      let n = 1; while (usados.has(String(n).padStart(2, '0'))) n++
      estanteria = String(n).padStart(2, '0')
      if (!zona_id) zona_id = d?.zonas.find(z => z.tipo === 'ALMACENAMIENTO')?.id ?? null
    } else { pasillo = null as any; zona_id = null }
    const e: El = {
      clave: nuevaClave(), tipo, nombre: null, pasillo, estanteria, zona_id, ubicacion_id: null, foto_id: null,
      categoria: (base.categoria as string) ?? null, color: null, x_m: wx, y_m: wy, rotacion: 0,
      modulos: base.modulos ?? 1, por_modulo: base.por_modulo ?? 1, niveles: base.niveles ?? 1, frente_cm: base.frente_cm ?? 270,
      fondo_cm: base.fondo_cm ?? 100, alto_nivel_cm: base.alto_nivel_cm ?? 150, capacidad_kg: base.capacidad_kg ?? null,
      largo_m: base.largo_m ?? null, ancho_m: base.ancho_m ?? null,
    }
    if (tipo === 'ZONA') e.nombre = AREAS[e.categoria ?? 'OTRA'].nombre
    return e
  }
  const colocarEn = (e: El, alt: boolean): El => {
    const [L, F] = dims(e)
    return { ...e, x_m: r2(ajustar(e.x_m - L / 2, alt) + L / 2), y_m: r2(ajustar(e.y_m - F / 2, alt) + F / 2) }
  }

  // ── imán a otras estructuras (guías) ──
  const imanes = (mov: El, moviendo: Set<string>, alt: boolean) => {
    if (!iman || alt) return { dx: 0, dy: 0, gx: undefined as number | undefined, gy: undefined as number | undefined }
    const b = caja(mov), tol = 8 / zoom
    const xs = [b.x0, (b.x0 + b.x1) / 2, b.x1], ys = [b.y0, (b.y0 + b.y1) / 2, b.y1]
    let mejorX: { d: number; v: number } | null = null, mejorY: { d: number; v: number } | null = null
    for (const o of els) {
      if (moviendo.has(o.clave)) continue
      const c = caja(o)
      for (const ox of [c.x0, (c.x0 + c.x1) / 2, c.x1]) for (const x of xs) {
        const dd = ox - x; if (Math.abs(dd) < tol && (!mejorX || Math.abs(dd) < Math.abs(mejorX.d))) mejorX = { d: dd, v: ox }
      }
      for (const oy of [c.y0, (c.y0 + c.y1) / 2, c.y1]) for (const y of ys) {
        const dd = oy - y; if (Math.abs(dd) < tol && (!mejorY || Math.abs(dd) < Math.abs(mejorY.d))) mejorY = { d: dd, v: oy }
      }
    }
    return { dx: mejorX?.d ?? 0, dy: mejorY?.d ?? 0, gx: mejorX?.v, gy: mejorY?.v }
  }

  // ── punteros ──
  const abajo = (ev: React.PointerEvent) => {
    raiz.current?.focus({ preventScroll: true })
    const [sx, sy] = puntoEvento(ev), [wx, wy] = aMundoPx(sx, sy)
    ;(ev.target as Element).setPointerCapture?.(ev.pointerId)
    if (ev.button === 1 || ev.button === 2 || modo === 'mano' || espacio.current) {
      setArrastre({ tipo: 'pan', sx, sy, pan0: pan }); return
    }
    if (modo === 'medir' || modo === 'calibrar') { setArrastre({ tipo: 'regla', a: [wx, wy], b: [wx, wy] }); return }
    if (modo.startsWith('colocar:')) {
      const tipo = modo.split(':')[1] as Tipo
      const nuevo = colocarEn(plantilla(tipo, wx, wy), ev.altKey)
      registrar(); setEls(p => [...p, nuevo]); setSel(new Set([nuevo.clave]))
      if (!ev.shiftKey) setModo('seleccionar')
      return
    }
    const t = tocado(wx, wy)
    if (t) {
      let nueva = new Set(sel)
      if (ev.shiftKey || ev.ctrlKey || ev.metaKey) { nueva.has(t.clave) ? nueva.delete(t.clave) : nueva.add(t.clave) }
      else if (!nueva.has(t.clave)) nueva = new Set([t.clave])
      setSel(nueva)
      if (!nueva.has(t.clave)) return
      const origen = new Map<string, [number, number]>()
      els.filter(e => nueva.has(e.clave)).forEach(e => origen.set(e.clave, [e.x_m, e.y_m]))
      setArrastre({ tipo: 'mover', wx, wy, origen, primero: t.clave, antes: instantanea(), movido: false })
    } else {
      if (!(ev.shiftKey || ev.ctrlKey)) setSel(new Set())
      setArrastre({ tipo: 'marco', wx, wy, cx: wx, cy: wy, sumar: ev.shiftKey || ev.ctrlKey })
    }
  }
  const movimiento = (ev: React.PointerEvent) => {
    const [sx, sy] = puntoEvento(ev), [wx, wy] = aMundoPx(sx, sy)
    setCursor([wx, wy])
    const a = arrastre
    if (!a) return
    if (a.tipo === 'pan') { setPan({ x: a.pan0.x + sx - a.sx, y: a.pan0.y + sy - a.sy }); return }
    if (a.tipo === 'regla') { setArrastre({ ...a, b: [wx, wy] }); return }
    if (a.tipo === 'marco') { setArrastre({ ...a, cx: wx, cy: wy }); return }
    if (a.tipo === 'mover') {
      let dx = wx - a.wx, dy = wy - a.wy
      if (!a.movido && Math.hypot(dx, dy) * zoom < 3) return
      if (ev.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0 }
      const prim = els.find(e => e.clave === a.primero)!
      const [ox, oy] = a.origen.get(a.primero)!
      // la rejilla: el borde de la estructura principal cae en la rejilla
      const tent = { ...prim, x_m: ox + dx, y_m: oy + dy }, bb = caja(tent)
      dx += ajustar(bb.x0, ev.altKey) - bb.x0; dy += ajustar(bb.y0, ev.altKey) - bb.y0
      const g = imanes({ ...prim, x_m: ox + dx, y_m: oy + dy }, new Set(a.origen.keys()), ev.altKey)
      if (g.gx !== undefined) dx += g.dx
      if (g.gy !== undefined) dy += g.dy
      setGuias({ x: g.gx, y: g.gy })
      setEls(prev => prev.map(e => { const o = a.origen.get(e.clave); return o ? { ...e, x_m: r2(o[0] + dx), y_m: r2(o[1] + dy) } : e }))
      if (!a.movido) setArrastre({ ...a, movido: true })
      return
    }
    if (a.tipo === 'rotar') {
      const e = els.find(x => x.clave === a.clave)!
      let ang = (Math.atan2(wy - e.y_m, wx - e.x_m) * 180) / Math.PI + 90
      if (!ev.shiftKey) ang = Math.round(ang / 15) * 15
      ang = ((ang % 360) + 360) % 360
      setEls(prev => prev.map(x => x.clave === a.clave ? { ...x, rotacion: r2(ang) } : x))
      return
    }
    if (a.tipo === 'estirar') {
      const o = a.orig, [lx, ly] = aLocal(o, wx, wy), [L, F] = dims(o)
      if (esEstructura(o)) {
        // estirar por el extremo derecho: módulos enteros, el izquierdo queda fijo
        const largo = Math.max(o.frente_cm / 100, lx + L / 2)
        const modulos = Math.max(1, Math.round(largo / (o.frente_cm / 100)))
        const nuevoL = (modulos * o.frente_cm) / 100
        const [cx, cy] = aMundo(o, -L / 2 + nuevoL / 2, 0)
        setEls(prev => prev.map(x => x.clave === a.clave ? { ...x, modulos, x_m: r2(cx), y_m: r2(cy) } : x))
      } else {
        const [ax, ay] = [-a.esquina[0] * L / 2, -a.esquina[1] * F / 2]       // esquina opuesta, fija
        const bx = ajustar(lx - ax, ev.altKey) + ax, by = ajustar(ly - ay, ev.altKey) + ay
        const largo = Math.max(0.2, Math.abs(bx - ax)), ancho = Math.max(0.1, Math.abs(by - ay))
        const [cx, cy] = aMundo(o, (ax + bx) / 2, (ay + by) / 2)
        setEls(prev => prev.map(x => x.clave === a.clave ? { ...x, largo_m: r2(largo), ancho_m: r2(ancho), x_m: r2(cx), y_m: r2(cy) } : x))
      }
    }
  }
  const arriba = () => {
    const a = arrastre
    setArrastre(null); setGuias({})
    if (!a) return
    if (a.tipo === 'mover' && a.movido) registrar(a.antes)
    if (a.tipo === 'rotar' || a.tipo === 'estirar') registrar(a.antes)
    if (a.tipo === 'marco') {
      const x0 = Math.min(a.wx, a.cx), x1 = Math.max(a.wx, a.cx), y0 = Math.min(a.wy, a.cy), y1 = Math.max(a.wy, a.cy)
      if ((x1 - x0) * zoom < 3 && (y1 - y0) * zoom < 3) return
      const dentro = els.filter(e => { const b = caja(e); return b.x0 >= x0 && b.x1 <= x1 && b.y0 >= y0 && b.y1 <= y1 }).map(e => e.clave)
      setSel(s => new Set([...(a.sumar ? s : []), ...dentro]))
    }
    if (a.tipo === 'regla' && modo === 'calibrar') {
      const medido = Math.hypot(a.b[0] - a.a[0], a.b[1] - a.a[1])
      if (medido * zoom > 10) setCalibrar({ medido, real: '' })
    }
  }
  const empezarRotar = (ev: React.PointerEvent, e: El) => {
    ev.stopPropagation(); (ev.target as Element).setPointerCapture?.(ev.pointerId)
    setArrastre({ tipo: 'rotar', clave: e.clave, antes: instantanea() })
  }
  const empezarEstirar = (ev: React.PointerEvent, e: El, esquina: [number, number]) => {
    ev.stopPropagation(); (ev.target as Element).setPointerCapture?.(ev.pointerId)
    setArrastre({ tipo: 'estirar', clave: e.clave, esquina, orig: e, antes: instantanea() })
  }

  // ── acciones ──
  const eliminar = () => {
    if (!sel.size) return
    const conMercancia = seleccion.filter(e => (e.ocupadas ?? 0) > 0)
    if (conMercancia.length) { toast.error(`${conMercancia.map(nombreDe).join(', ')} tiene mercancía: muévala antes de quitar la estructura.`); return }
    registrar(); setEls(p => p.filter(e => !sel.has(e.clave))); setSel(new Set())
  }
  const copias = (lista: El[], dx: number, dy: number, numerar = true): El[] => lista.map(e => ({
    ...e, clave: nuevaClave(), id: undefined, vinculadas: 0, ocupadas: 0, ocupacion_pct: null, codigos: [], sobrantes: 0,
    x_m: r2(e.x_m + dx), y_m: r2(e.y_m + dy), foto_id: null, ubicacion_id: null,
    estanteria: numerar && esEstructura(e) ? siguienteLibre(e.pasillo, e.estanteria) : e.estanteria,
    nombre: esEstructura(e) ? null : e.nombre,
  }))
  const siguienteLibre = (pasillo: string | null, est: string | null, extra: El[] = []) => {
    const usados = new Set([...els, ...extra].filter(x => x.pasillo === pasillo).map(x => x.estanteria))
    let n = siguiente(est) ?? est
    for (let i = 0; i < 500 && usados.has(n); i++) n = siguiente(n)
    return n
  }
  const duplicar = () => {
    if (!seleccion.length) return
    const b = seleccion.map(caja), alto = Math.max(...b.map(x => x.y1)) - Math.min(...b.map(x => x.y0))
    const nuevos = copias(seleccion, 0, r2(alto + (seleccion.every(esEstructura) ? 3.2 : 1)))
    registrar(); setEls(p => [...p, ...nuevos]); setSel(new Set(nuevos.map(e => e.clave)))
  }
  const copiar = () => { portapapeles.current = seleccion.map(e => ({ ...e })); if (seleccion.length) toast.success(`${seleccion.length} copiada(s)`) }
  const pegar = () => {
    if (!portapapeles.current.length) return
    const nuevos = copias(portapapeles.current, 1, 1)
    portapapeles.current = nuevos.map(e => ({ ...e }))
    registrar(); setEls(p => [...p, ...nuevos]); setSel(new Set(nuevos.map(e => e.clave)))
  }
  const rotar = (g: number) => { if (seleccion.length) cambiar([...sel], e => ({ rotacion: (((e.rotacion + g) % 360) + 360) % 360 })) }
  const mover = (dx: number, dy: number) => { if (seleccion.length) cambiar([...sel], e => ({ x_m: r2(e.x_m + dx), y_m: r2(e.y_m + dy) }), 'flechas') }
  const alinear = (como: 'izq' | 'cx' | 'der' | 'arr' | 'cy' | 'aba') => {
    if (seleccion.length < 2) return
    const cajas = new Map(seleccion.map(e => [e.clave, caja(e)]))
    const todas = [...cajas.values()]
    const ref = { izq: Math.min(...todas.map(b => b.x0)), der: Math.max(...todas.map(b => b.x1)), arr: Math.min(...todas.map(b => b.y0)),
      aba: Math.max(...todas.map(b => b.y1)), cx: (Math.min(...todas.map(b => b.x0)) + Math.max(...todas.map(b => b.x1))) / 2,
      cy: (Math.min(...todas.map(b => b.y0)) + Math.max(...todas.map(b => b.y1))) / 2 }[como]
    cambiar([...sel], e => {
      const b = cajas.get(e.clave)!
      if (como === 'izq') return { x_m: r2(e.x_m + ref - b.x0) }
      if (como === 'der') return { x_m: r2(e.x_m + ref - b.x1) }
      if (como === 'cx') return { x_m: r2(e.x_m + ref - (b.x0 + b.x1) / 2) }
      if (como === 'arr') return { y_m: r2(e.y_m + ref - b.y0) }
      if (como === 'aba') return { y_m: r2(e.y_m + ref - b.y1) }
      return { y_m: r2(e.y_m + ref - (b.y0 + b.y1) / 2) }
    })
  }
  const distribuir = (eje: 'x' | 'y') => {
    if (seleccion.length < 3) return
    const lista = seleccion.map(e => ({ e, b: caja(e) })).sort((p, q) => eje === 'x' ? p.b.x0 - q.b.x0 : p.b.y0 - q.b.y0)
    const tam0 = lista.reduce((s, { b }) => s + (eje === 'x' ? b.x1 - b.x0 : b.y1 - b.y0), 0)
    const ini = eje === 'x' ? lista[0].b.x0 : lista[0].b.y0, fin = eje === 'x' ? lista[lista.length - 1].b.x1 : lista[lista.length - 1].b.y1
    const hueco = (fin - ini - tam0) / (lista.length - 1)
    let cursorEje = ini
    const nuevo = new Map<string, number>()
    for (const { e, b } of lista) {
      nuevo.set(e.clave, eje === 'x' ? e.x_m + cursorEje - b.x0 : e.y_m + cursorEje - b.y0)
      cursorEje += (eje === 'x' ? b.x1 - b.x0 : b.y1 - b.y0) + hueco
    }
    cambiar([...sel], e => eje === 'x' ? { x_m: r2(nuevo.get(e.clave)!) } : { y_m: r2(nuevo.get(e.clave)!) })
  }

  // serie: copias perpendiculares a la estructura, en pares espalda con espalda o filas simples
  const vistaSerie = useMemo<El[]>(() => {
    if (!serie || !uno) return []
    const [, F] = dims(uno), out: El[] = []
    const rot = rad(uno.rotacion), nx = -Math.sin(rot) * serie.direccion, ny = Math.cos(rot) * serie.direccion
    let off = 0, pasillo = uno.pasillo, est = uno.estanteria
    const extra: El[] = []
    // ¿La estructura de partida ya tiene pareja espalda con espalda del otro lado? Entonces la serie arranca con pasillo.
    const yaEnPar = serie.modo === 'espalda' && els.some(o => {
      if (o.clave === uno.clave || !esEstructura(o) || Math.abs(((o.rotacion - uno.rotacion) % 180 + 180) % 180) > 1) return false
      const [lx, ly] = aLocal(uno, o.x_m, o.y_m), [Lo, Fo] = dims(o)
      const lado = -serie.direccion * ly
      return lado > 0 && lado <= (F + Fo) / 2 + 0.6 && Math.abs(lx) < (dims(uno)[0] + Lo) / 2
    })
    for (let i = 1; i <= serie.cantidad; i++) {
      const espalda = (i % 2 === 1) !== yaEnPar
      off += serie.modo === 'espalda' ? (espalda ? F + serie.espalda : F + serie.pasillo) : F + serie.pasillo
      if (serie.numerar === 'pasillo') {
        if (serie.modo !== 'espalda' || !espalda) pasillo = siguiente(pasillo)
      } else est = siguienteLibre(pasillo, est, extra)
      const e: El = { ...uno, clave: nuevaClave(), id: undefined, vinculadas: 0, ocupadas: 0, ocupacion_pct: null, codigos: [], foto_id: null,
        x_m: r2(uno.x_m + nx * off), y_m: r2(uno.y_m + ny * off), pasillo, estanteria: est, nombre: null }
      out.push(e); extra.push(e)
    }
    return out
  }, [serie, uno]) // eslint-disable-line react-hooks/exhaustive-deps
  const aplicarSerie = () => { registrar(); setEls(p => [...p, ...vistaSerie]); setSel(new Set(vistaSerie.map(e => e.clave))); setSerie(null) }

  const aplicarCalibracion = () => {
    const real = Number(calibrar?.real?.replace(',', '.'))
    if (!calibrar || !(real > 0) || !config.escala_m_px) return
    const f = real / calibrar.medido
    cambiarConfig({ escala_m_px: config.escala_m_px * f, plano_x_m: r2(config.plano_x_m * f), plano_y_m: r2(config.plano_y_m * f) })
    if (d?.plano) {
      const w = d.plano.ancho * config.escala_m_px * f, h = d.plano.alto * config.escala_m_px * f
      setConfig(c => ({ ...c, ancho_m: Math.max(c.ancho_m, r2(w + c.plano_x_m)), largo_m: Math.max(c.largo_m, r2(h + c.plano_y_m)) }))
    }
    setCalibrar(null); setModo('seleccionar'); toast.success('Escala del plano calibrada')
  }

  // ── guardar y generar ──
  const guardar = async (): Promise<boolean> => {
    setGuardando(true)
    try {
      const cuerpo = {
        config, elementos: els.map(e => ({
          id: e.id ?? null, clave: e.clave, tipo: e.tipo, nombre: e.nombre, pasillo: e.pasillo, estanteria: e.estanteria, zona_id: e.zona_id,
          ubicacion_id: e.ubicacion_id, foto_id: e.foto_id, categoria: e.categoria, color: e.color, x_m: e.x_m, y_m: e.y_m, rotacion: e.rotacion,
          modulos: e.modulos, por_modulo: e.por_modulo, niveles: e.niveles, frente_cm: e.frente_cm, fondo_cm: e.fondo_cm,
          alto_nivel_cm: e.alto_nivel_cm, capacidad_kg: e.capacidad_kg, largo_m: e.largo_m, ancho_m: e.ancho_m,
        })),
      }
      const r = await api.put('/wms/layout', cuerpo, { params: { almacen_id: almacen } }).then(x => x.data)
      const ids: Record<string, number> = r.ids ?? {}
      const info = new Map<number, any>(r.elementos.map((e: any) => [e.id, e]))
      const conId = (lista: El[]) => lista.map(e => {
        const id = e.id ?? ids[e.clave]
        const s = id ? info.get(id) : null
        return { ...e, id, ...(s ? { vinculadas: s.vinculadas, ocupadas: s.ocupadas, ocupacion_pct: s.ocupacion_pct, codigos: s.codigos, sobrantes: s.sobrantes } : {}) }
      })
      setEls(conId)
      pasado.current = pasado.current.map(s => ({ ...s, els: conId(s.els) }))
      futuro.current = futuro.current.map(s => ({ ...s, els: conId(s.els) }))
      setSucio(false)
      qc.invalidateQueries({ queryKey: ['mapa-3d'] })
      toast.success(r.desactivadas ? `Layout guardado · ${r.desactivadas} ubicaciones vacías desactivadas` : 'Layout guardado')
      return true
    } catch (e) { toast.error(errorApi(e)); return false } finally { setGuardando(false) }
  }
  const simular = async (renombrar: boolean) => {
    setGenerar({ cargando: true, renombrar })
    if (sucio && !(await guardar())) { setGenerar(null); return }
    try {
      const res = await api.post('/wms/layout/generar', { simular: true, renombrar }, { params: { almacen_id: almacen } }).then(x => x.data)
      setGenerar({ cargando: false, renombrar, res })
    } catch (e) { toast.error(errorApi(e)); setGenerar(null) }
  }
  const ejecutar = async () => {
    if (!generar) return
    setGenerar({ ...generar, cargando: true })
    try {
      const r = await api.post('/wms/layout/generar', { simular: false, renombrar: generar.renombrar }, { params: { almacen_id: almacen } }).then(x => x.data)
      toast.success(`Ubicaciones: ${r.totales.crear ?? 0} creadas · ${r.totales.actualizar ?? 0} actualizadas · ${r.totales.adoptar ?? 0} adoptadas`)
      setGenerar(null)
      cargado.current = null
      await qc.invalidateQueries({ queryKey: ['wms-layout', almacen] })
      qc.invalidateQueries({ queryKey: ['mapa-3d'] })
    } catch (e) { toast.error(errorApi(e)); setGenerar(g => g && { ...g, cargando: false }) }
  }
  const importar = async () => {
    try {
      const r = await api.post('/wms/layout/importar', null, { params: { almacen_id: almacen } }).then(x => x.data)
      cargar(r); qc.setQueryData(['wms-layout', almacen], r); encuadrado.current = null
      toast.success(`${r.elementos.length} estructuras importadas desde las ubicaciones existentes`)
    } catch (e) { toast.error(errorApi(e)) }
  }

  // ── teclado ──
  const tecla = (ev: React.KeyboardEvent) => {
    const t = ev.target as HTMLElement
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable) return
    const k = ev.key.toLowerCase(), ctrl = ev.ctrlKey || ev.metaKey
    const hecho = () => { ev.preventDefault(); ev.stopPropagation() }
    if (k === ' ') { espacio.current = true; hecho(); return }
    if (ctrl && k === 'z' && !ev.shiftKey) { deshacer(); return hecho() }
    if (ctrl && (k === 'y' || (k === 'z' && ev.shiftKey))) { rehacer(); return hecho() }
    if (ctrl && k === 'd') { duplicar(); return hecho() }
    if (ctrl && k === 'c') { copiar(); return hecho() }
    if (ctrl && k === 'v') { pegar(); return hecho() }
    if (ctrl && k === 'a') { setSel(new Set(els.map(e => e.clave))); return hecho() }
    if (ctrl && k === 's') { guardar(); return hecho() }
    if (ctrl) return
    if (k === 'delete' || k === 'backspace') { eliminar(); return hecho() }
    if (k === 'escape') { setModo('seleccionar'); setSel(new Set()); setSerie(null); return hecho() }
    if (k === 'v') { setModo('seleccionar'); return hecho() }
    if (k === 'h') { setModo('mano'); return hecho() }
    if (k === 'm') { setModo('medir'); return hecho() }
    if (k === 'r') { rotar(ev.shiftKey ? -90 : 90); return hecho() }
    if (k === 'f') { encuadrar(seleccion.length ? unir(seleccion.map(caja), 2) : undefined); return hecho() }
    if (k === '+' || k === '=') { zoomEn(1.25); return hecho() }
    if (k === '-') { zoomEn(0.8); return hecho() }
    const p = ev.shiftKey ? 1 : paso
    if (k === 'arrowleft') { mover(-p, 0); return hecho() }
    if (k === 'arrowright') { mover(p, 0); return hecho() }
    if (k === 'arrowup') { mover(0, -p); return hecho() }
    if (k === 'arrowdown') { mover(0, p); return hecho() }
  }
  const zoomEn = (f: number) => {
    const cx = tam.w / 2, cy = tam.h / 2
    setZoom(z0 => { const z = Math.max(2, Math.min(250, z0 * f)); setPan(p => ({ x: cx - ((cx - p.x) / z0) * z, y: cy - ((cy - p.y) / z0) * z })); return z })
  }
  const unir = (cs: { x0: number; y0: number; x1: number; y1: number }[], margen = 0) => ({
    x0: Math.min(...cs.map(c => c.x0)) - margen, y0: Math.min(...cs.map(c => c.y0)) - margen,
    x1: Math.max(...cs.map(c => c.x1)) + margen, y1: Math.max(...cs.map(c => c.y1)) + margen,
  })

  useEffect(() => {
    const salir = () => setCompleta(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', salir)
    return () => document.removeEventListener('fullscreenchange', salir)
  }, [])
  // aviso al salir con cambios sin guardar
  useEffect(() => {
    if (!sucio) return
    const antes = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', antes)
    return () => window.removeEventListener('beforeunload', antes)
  }, [sucio])

  if (datos.isLoading || !d) return <LinearProgress />

  // ═════════════════════════════════════════════════════════════════════════
  // Dibujo
  // ═════════════════════════════════════════════════════════════════════════
  const sw = { vectorEffect: 'non-scaling-stroke' as const }
  const fantasma = modo.startsWith('colocar:') && cursor ? colocarEn(plantilla(modo.split(':')[1] as Tipo, cursor[0], cursor[1]), false) : null

  const dibujar = (e: El, opciones: { fantasma?: boolean } = {}) => {
    const [L, F] = dims(e), color = colorDe(e, indice)
    const marcada = sel.has(e.clave)
    const op = opciones.fantasma ? 0.55 : 1
    const partes: React.ReactNode[] = []
    if (e.tipo === 'ZONA') {
      partes.push(<rect key="f" x={-L / 2} y={-F / 2} width={L} height={F} rx={Math.min(0.4, L / 10)} fill={color} fillOpacity={0.12}
        stroke={color} strokeWidth={1.6} strokeDasharray="7 4" {...sw} />)
    } else if (e.tipo === 'MURO' || e.tipo === 'COLUMNA') {
      partes.push(<rect key="f" x={-L / 2} y={-F / 2} width={L} height={F} fill={color} />)
    } else {
      const mod = e.frente_cm / 100, pos = mod / e.por_modulo
      partes.push(<rect key="f" x={-L / 2} y={-F / 2} width={L} height={F} fill={color} fillOpacity={e.tipo === 'PISO' ? 0.06 : 0.13}
        stroke={color} strokeWidth={1.3} strokeDasharray={e.tipo === 'PISO' ? '5 3' : undefined} {...sw} />)
      if (verOcupacion && e.ocupacion_pct != null && !opciones.fantasma) {
        const pct = Math.min(100, e.ocupacion_pct) / 100
        const cs = pct > 0.9 ? '#EF4444' : pct > 0.7 ? '#F59E0B' : '#10B981'
        partes.push(<rect key="o" x={-L / 2} y={-F / 2} width={L * pct} height={F} fill={cs} fillOpacity={0.45} />)
      }
      if (e.tipo === 'PISO') {
        for (let i = 0; i < e.modulos * e.por_modulo; i++) {
          partes.push(<rect key={`p${i}`} x={-L / 2 + i * pos + pos * 0.06} y={-F / 2 + F * 0.06} width={pos * 0.88} height={F * 0.88} rx={0.05}
            fill={color} fillOpacity={0.28} stroke={color} strokeOpacity={0.6} strokeWidth={0.8} {...sw} />)
        }
      } else {
        for (let i = 1; i < e.modulos * e.por_modulo; i++) {
          if (i % e.por_modulo) partes.push(<line key={`d${i}`} x1={-L / 2 + i * pos} y1={-F / 2} x2={-L / 2 + i * pos} y2={F / 2} stroke={color} strokeOpacity={0.45} strokeDasharray="2 2" strokeWidth={0.8} {...sw} />)
        }
        if (e.tipo === 'SELECTIVO') {
          partes.push(<line key="b1" x1={-L / 2} y1={-F / 2} x2={L / 2} y2={-F / 2} stroke="#F97316" strokeWidth={2.4} {...sw} />)
          partes.push(<line key="b2" x1={-L / 2} y1={F / 2} x2={L / 2} y2={F / 2} stroke="#F97316" strokeWidth={2.4} {...sw} />)
        }
        if (e.tipo === 'GONDOLA') partes.push(<line key="esp" x1={-L / 2} y1={0} x2={L / 2} y2={0} stroke="#475569" strokeWidth={1.6} {...sw} />)
        if (e.tipo === 'CANTILEVER') partes.push(<line key="esp" x1={-L / 2} y1={0} x2={L / 2} y2={0} stroke="#475569" strokeWidth={2.6} {...sw} />)
        for (let i = 0; i <= e.modulos; i++) {
          const x = -L / 2 + i * mod
          if (e.tipo === 'CANTILEVER') {
            partes.push(<line key={`a${i}`} x1={x} y1={-F / 2} x2={x} y2={F / 2} stroke="#64748B" strokeWidth={1.4} {...sw} />)
          } else {
            const t = Math.max(0.08, Math.min(0.14, 3 / zoom))
            for (const y of [-F / 2, F / 2]) partes.push(<rect key={`c${i}${y}`} x={x - t / 2} y={y - t / 2} width={t} height={t} fill={i === 0 || i === e.modulos ? '#EA580C' : '#334155'} />)
            if (i > 0 && i < e.modulos) partes.push(<line key={`m${i}`} x1={x} y1={-F / 2} x2={x} y2={F / 2} stroke={color} strokeOpacity={0.7} strokeWidth={1} {...sw} />)
          }
        }
      }
    }
    return (
      <g key={e.clave + (opciones.fantasma ? 'g' : '')} transform={`translate(${e.x_m} ${e.y_m}) rotate(${e.rotacion})`} opacity={op}
        style={{ pointerEvents: 'none' }}>
        {partes}
        {marcada && <rect x={-L / 2} y={-F / 2} width={L} height={F} fill="none" stroke={ACENTO} strokeWidth={2} {...sw} />}
      </g>
    )
  }

  // regla (escala en pantalla)
  const pasosRegla = [0.5, 1, 2, 5, 10, 20, 50, 100, 200]
  const pasoMenor = pasosRegla.find(s => s * zoom >= 9) ?? 200
  const pasoMayor = pasoMenor * (pasoMenor === 2 || pasoMenor === 20 ? 5 : pasoMenor === 0.5 ? 2 : 5)
  const [vx0, vy0] = aMundoPx(0, 0), [vx1, vy1] = aMundoPx(tam.w, tam.h)
  const lineasX: number[] = [], lineasY: number[] = []
  for (let x = Math.floor(vx0 / pasoMenor) * pasoMenor; x <= vx1; x += pasoMenor) lineasX.push(r2(x))
  for (let y = Math.floor(vy0 / pasoMenor) * pasoMenor; y <= vy1; y += pasoMenor) lineasY.push(r2(y))
  const esMayor = (v: number) => Math.abs(v / pasoMayor - Math.round(v / pasoMayor)) < 1e-6

  const plano = d.plano && config.escala_m_px && planoUrl
    ? { x: config.plano_x_m, y: config.plano_y_m, w: d.plano.ancho * config.escala_m_px, h: d.plano.alto * config.escala_m_px } : null

  const cursorLienzo = arrastre?.tipo === 'pan' ? 'grabbing' : modo === 'mano' || espacio.current ? 'grab'
    : modo === 'seleccionar' ? (cursor && tocado(cursor[0], cursor[1]) ? 'move' : 'default') : 'crosshair'

  const listaCapas = els.filter(e => !buscar || nombreDe(e).toLowerCase().includes(buscar.toLowerCase()))
  const zonaDe = (id: number | null) => d.zonas.find(z => z.id === id)

  // ═════════════════════════════════════════════════════════════════════════
  // Interfaz
  // ═════════════════════════════════════════════════════════════════════════
  return (
    <Box ref={raiz} tabIndex={0} onKeyDown={tecla} onKeyUp={e => { if (e.key === ' ') espacio.current = false }}
      sx={{ outline: 'none', border: '1px solid', borderColor: 'divider', borderRadius: completa ? 0 : 3, overflow: 'hidden', bgcolor: '#fff',
        display: 'flex', flexDirection: 'column', height: completa ? '100vh' : { xs: 760, md: 'max(680px, calc(100vh - 130px))' },
        boxShadow: '0 1px 2px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.06)' }}>

      {/* ── Barra de herramientas ── */}
      <Stack direction="row" alignItems="center" sx={{ px: 1, py: 0.6, borderBottom: '1px solid', borderColor: 'divider', bgcolor: '#FCFCFD', gap: 0.25, flexWrap: 'wrap' }}>
        <Herramienta titulo="Seleccionar y mover" atajo="V" activo={modo === 'seleccionar'} onClick={() => setModo('seleccionar')}><NearMe fontSize="small" sx={{ transform: 'scaleX(-1)' }} /></Herramienta>
        <Herramienta titulo="Desplazar la vista" atajo="H" activo={modo === 'mano'} onClick={() => setModo('mano')}><PanTool fontSize="small" /></Herramienta>
        <Herramienta titulo="Medir distancias" atajo="M" activo={modo === 'medir'} onClick={() => setModo('medir')}><Straighten fontSize="small" /></Herramienta>
        <Herramienta titulo="Calibrar la escala del plano (trace una medida conocida)" activo={modo === 'calibrar'} disabled={!d.plano} onClick={() => setModo('calibrar')}><SquareFoot fontSize="small" /></Herramienta>
        <Separador />
        <Herramienta titulo="Deshacer" atajo="Ctrl+Z" disabled={!pasado.current.length} onClick={deshacer}><Undo fontSize="small" /></Herramienta>
        <Herramienta titulo="Rehacer" atajo="Ctrl+Y" disabled={!futuro.current.length} onClick={rehacer}><Redo fontSize="small" /></Herramienta>
        <Separador />
        <Herramienta titulo="Duplicar" atajo="Ctrl+D" disabled={!seleccion.length} onClick={duplicar}><ContentCopy fontSize="small" /></Herramienta>
        <Herramienta titulo="Crear en serie (filas de estanterías con pasillos)" disabled={!uno || !esEstructura(uno)}
          onClick={() => setSerie({ cantidad: 3, modo: 'espalda', pasillo: 3.2, espalda: 0.1, direccion: 1, numerar: 'estanteria' })}><CalendarViewWeek fontSize="small" /></Herramienta>
        <Herramienta titulo="Rotar 90°" atajo="R" disabled={!seleccion.length} onClick={() => rotar(90)}><RotateRight fontSize="small" /></Herramienta>
        <Herramienta titulo="Eliminar" atajo="Supr" disabled={!seleccion.length} onClick={eliminar}><DeleteOutline fontSize="small" /></Herramienta>
        <Separador />
        <Herramienta titulo={iman ? 'Imán activo (Alt al arrastrar lo suspende)' : 'Imán apagado'} activo={iman} onClick={() => setIman(v => !v)}><GridOn fontSize="small" /></Herramienta>
        <TextField select size="small" value={paso} onChange={e => setPaso(Number(e.target.value))} sx={{ width: 92, '& .MuiInputBase-input': { py: 0.6, fontSize: 12.5 } }}>
          {[0.05, 0.1, 0.25, 0.5, 1].map(p => <MenuItem key={p} value={p}>{p < 1 ? `${p * 100} cm` : '1 m'}</MenuItem>)}
        </TextField>
        <Separador />
        <Herramienta titulo="Alejar" atajo="−" onClick={() => zoomEn(0.8)}><ZoomOut fontSize="small" /></Herramienta>
        <Typography sx={{ fontSize: 12, fontFamily: 'Consolas, monospace', width: 46, textAlign: 'center', color: '#475569' }}>{Math.round((zoom / 12) * 100)}%</Typography>
        <Herramienta titulo="Acercar" atajo="+" onClick={() => zoomEn(1.25)}><ZoomIn fontSize="small" /></Herramienta>
        <Herramienta titulo="Encuadrar la bodega (o la selección)" atajo="F" onClick={() => encuadrar(seleccion.length ? unir(seleccion.map(caja), 2) : undefined)}><FitScreen fontSize="small" /></Herramienta>
        <Herramienta titulo={completa ? 'Salir de pantalla completa' : 'Pantalla completa'} onClick={() => completa ? document.exitFullscreen() : raiz.current?.requestFullscreen()}>
          {completa ? <FullscreenExit fontSize="small" /> : <Fullscreen fontSize="small" />}</Herramienta>
        <Box flex={1} />
        {sucio ? <Chip size="small" label="Cambios sin guardar" sx={{ bgcolor: '#FEF3C7', color: '#92400E', fontWeight: 600, mr: 1 }} />
          : <Chip size="small" icon={<CheckCircle sx={{ fontSize: 15 }} />} label="Guardado" sx={{ bgcolor: '#ECFDF5', color: '#047857', fontWeight: 600, mr: 1, '& .MuiChip-icon': { color: '#10B981' } }} />}
        {onVer3D && <Button size="small" startIcon={<ViewInAr />} onClick={async () => { if (!sucio || await guardar()) onVer3D() }} sx={{ textTransform: 'none', mr: 0.5 }}>Ver en 3D</Button>}
        <Button size="small" variant="outlined" startIcon={<AutoFixHigh />} onClick={() => simular(false)} sx={{ textTransform: 'none', mr: 0.75, borderRadius: 2 }}>Generar ubicaciones</Button>
        <Button size="small" variant="contained" startIcon={guardando ? <CircularProgress size={14} color="inherit" /> : <Save />} disabled={guardando || !sucio}
          onClick={guardar} sx={{ textTransform: 'none', bgcolor: ACENTO, borderRadius: 2, boxShadow: 'none', '&:hover': { bgcolor: '#4338CA', boxShadow: 'none' } }}>Guardar</Button>
      </Stack>

      <Box sx={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* ── Paleta y capas ── */}
        <Box sx={{ width: 248, borderRight: '1px solid', borderColor: 'divider', display: { xs: 'none', md: 'flex' }, flexDirection: 'column', bgcolor: '#FCFCFD', minHeight: 0 }}>
          <Box sx={{ p: 1.5, pb: 1 }}>
            <Typography sx={{ fontSize: 10.5, letterSpacing: '0.1em', fontWeight: 800, color: 'text.secondary', mb: 1 }}>ESTRUCTURAS</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.75 }}>
              {(Object.keys(CATALOGO) as Tipo[]).map(t => {
                const activo = modo === `colocar:${t}`
                return (
                  <Tooltip key={t} placement="right" arrow title={<><b>{CATALOGO[t].nombre}</b><br />{CATALOGO[t].desc}<br /><i>Clic en la paleta y luego en el plano · Shift para colocar varias</i></>}>
                    <Box role="button" aria-label={`Agregar ${CATALOGO[t].nombre}`} onClick={() => setModo(activo ? 'seleccionar' : `colocar:${t}`)}
                      sx={{ cursor: 'pointer', p: 0.75, pt: 1, borderRadius: 2, border: '1px solid', borderColor: activo ? ACENTO : 'divider', bgcolor: activo ? alpha(ACENTO, 0.06) : '#fff',
                        textAlign: 'center', transition: 'all .12s', '&:hover': { borderColor: activo ? ACENTO : '#CBD5E1', boxShadow: '0 2px 8px rgba(15,23,42,0.06)', transform: 'translateY(-1px)' } }}>
                      <IconoTipo tipo={t} />
                      <Typography sx={{ fontSize: 11, fontWeight: 700, lineHeight: 1.15, mt: 0.25, color: activo ? ACENTO : '#1E293B' }}>{CATALOGO[t].nombre}</Typography>
                    </Box>
                  </Tooltip>
                )
              })}
            </Box>
          </Box>
          <Divider />
          <Stack direction="row" alignItems="center" sx={{ px: 1.5, pt: 1.25, pb: 0.5 }} gap={0.75}>
            <Layers sx={{ fontSize: 16, color: 'text.secondary' }} />
            <Typography sx={{ fontSize: 10.5, letterSpacing: '0.1em', fontWeight: 800, color: 'text.secondary', flex: 1 }}>CAPAS · {els.length}</Typography>
          </Stack>
          <Box sx={{ px: 1.5, pb: 1 }}>
            <TextField size="small" fullWidth placeholder="Buscar…" value={buscar} onChange={e => setBuscar(e.target.value)}
              InputProps={{ startAdornment: <InputAdornment position="start"><Search sx={{ fontSize: 17 }} /></InputAdornment> }}
              sx={{ '& .MuiInputBase-input': { py: 0.6, fontSize: 12.5 } }} />
          </Box>
          <Box sx={{ flex: 1, overflowY: 'auto', px: 0.75, pb: 1 }}>
            {listaCapas.map(e => {
              const activo = sel.has(e.clave), color = colorDe(e, indice)
              return (
                <Stack key={e.clave} direction="row" alignItems="center" gap={1} onClick={ev => {
                  setSel(s => ev.shiftKey ? new Set([...s, e.clave]) : new Set([e.clave]))
                  if (!ev.shiftKey) { const b = caja(e); const [sx, sy] = aPantalla((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
                    if (sx < REGLA || sy < REGLA || sx > tam.w || sy > tam.h) setPan(p => ({ x: p.x + tam.w / 2 - sx, y: p.y + tam.h / 2 - sy })) }
                }}
                  sx={{ px: 1, py: 0.55, borderRadius: 1.5, cursor: 'pointer', bgcolor: activo ? alpha(ACENTO, 0.08) : 'transparent', '&:hover': { bgcolor: activo ? alpha(ACENTO, 0.12) : '#F1F5F9' } }}>
                  <Box sx={{ width: 9, height: 9, borderRadius: e.tipo === 'ZONA' ? 0.5 : '2px', bgcolor: color, flexShrink: 0, outline: e.tipo === 'ZONA' ? `1px dashed ${color}` : undefined, outlineOffset: 1 }} />
                  <Typography noWrap sx={{ fontSize: 12.5, fontWeight: activo ? 700 : 500, flex: 1, color: activo ? ACENTO : '#1E293B' }}>{nombreDe(e)}</Typography>
                  {esEstructura(e) && <Typography sx={{ fontSize: 10.5, fontFamily: 'Consolas, monospace', color: 'text.secondary' }}>{posicionesDe(e)}</Typography>}
                  {esEstructura(e) && !e.zona_id && <Tooltip title="Sin zona del WMS"><WarningAmber sx={{ fontSize: 14, color: '#F59E0B' }} /></Tooltip>}
                </Stack>
              )
            })}
          </Box>
        </Box>

        {/* ── Lienzo ── */}
        <Box ref={lienzo} onPointerDown={abajo} onPointerMove={movimiento} onPointerUp={arriba} onPointerLeave={() => setCursor(null)}
          onContextMenu={e => e.preventDefault()}
          sx={{ flex: 1, position: 'relative', overflow: 'hidden', bgcolor: '#EEF1F6', cursor: cursorLienzo, touchAction: 'none', userSelect: 'none' }}>
          <svg width={tam.w} height={tam.h} style={{ display: 'block', position: 'absolute', inset: 0 }}>
            <defs>
              <filter id="sombraPiso" x="-5%" y="-5%" width="110%" height="110%"><feDropShadow dx="0" dy="2" stdDeviation="6" floodColor="#0F172A" floodOpacity="0.10" /></filter>
            </defs>
            {/* piso */}
            <rect x={pan.x} y={pan.y} width={config.ancho_m * zoom} height={config.largo_m * zoom} fill="#FFFFFF" filter="url(#sombraPiso)" />
            {/* rejilla */}
            <g>
              {lineasX.map(x => <line key={`x${x}`} x1={x * zoom + pan.x} y1={0} x2={x * zoom + pan.x} y2={tam.h} stroke={esMayor(x) ? '#CBD5E1' : '#E2E8F0'} strokeOpacity={esMayor(x) ? 0.9 : 0.6} strokeWidth={1} />)}
              {lineasY.map(y => <line key={`y${y}`} x1={0} y1={y * zoom + pan.y} x2={tam.w} y2={y * zoom + pan.y} stroke={esMayor(y) ? '#CBD5E1' : '#E2E8F0'} strokeOpacity={esMayor(y) ? 0.9 : 0.6} strokeWidth={1} />)}
            </g>
            <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
              {plano && <image href={planoUrl!} x={plano.x} y={plano.y} width={plano.w} height={plano.h} opacity={opacidadPlano} preserveAspectRatio="none"
                style={{ mixBlendMode: 'multiply', filter: verPlano === 'original' ? 'grayscale(1)' : undefined }} />}
              <rect x={0} y={0} width={config.ancho_m} height={config.largo_m} fill="none" stroke="#94A3B8" strokeWidth={1} strokeDasharray="6 4" {...sw} />
              {ordenados.map(e => dibujar(e))}
              {fantasma && dibujar(fantasma, { fantasma: true })}
              {vistaSerie.map(e => dibujar(e, { fantasma: true }))}
              {/* guías */}
              {guias.x !== undefined && <line x1={guias.x} y1={vy0} x2={guias.x} y2={vy1} stroke={GUIA} strokeWidth={1} strokeDasharray="4 3" {...sw} />}
              {guias.y !== undefined && <line x1={vx0} y1={guias.y} x2={vx1} y2={guias.y} stroke={GUIA} strokeWidth={1} strokeDasharray="4 3" {...sw} />}
              {/* marco de selección */}
              {arrastre?.tipo === 'marco' && <rect x={Math.min(arrastre.wx, arrastre.cx)} y={Math.min(arrastre.wy, arrastre.cy)} width={Math.abs(arrastre.cx - arrastre.wx)}
                height={Math.abs(arrastre.cy - arrastre.wy)} fill={alpha(ACENTO, 0.08)} stroke={ACENTO} strokeWidth={1} strokeDasharray="4 3" {...sw} />}
              {/* regla de medir / calibrar */}
              {arrastre?.tipo === 'regla' && <g>
                <line x1={arrastre.a[0]} y1={arrastre.a[1]} x2={arrastre.b[0]} y2={arrastre.b[1]} stroke={modo === 'calibrar' ? '#F59E0B' : ACENTO} strokeWidth={2} {...sw} />
                {[arrastre.a, arrastre.b].map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={4 / zoom} fill="#fff" stroke={modo === 'calibrar' ? '#F59E0B' : ACENTO} strokeWidth={2} {...sw} />)}
              </g>}
            </g>

            {/* etiquetas (derechas, en pantalla) */}
            {ordenados.map(e => {
              if (e.tipo === 'MURO' || e.tipo === 'COLUMNA') return null
              const b = caja(e), wpx = (b.x1 - b.x0) * zoom, hpx = (b.y1 - b.y0) * zoom
              if (wpx < 34 || hpx < 12) return null
              const [sx, sy] = aPantalla((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
              const sub = esEstructura(e) ? `${e.modulos * e.por_modulo}×${e.tipo === 'PISO' ? e.niveles + ' alt' : e.niveles}` : null
              const grande = wpx > 90 && hpx > 22
              const color = colorDe(e, indice)
              // que el rótulo no se salga de la estructura
              const cabe = Math.max(3, Math.floor((wpx - 8) / 7))
              const texto = (t: string) => t.length > cabe ? t.slice(0, Math.max(1, cabe - 1)) + '…' : t
              return (
                <g key={`t${e.clave}`} style={{ pointerEvents: 'none' }}>
                  <text x={sx} y={sy + (grande && sub ? -1 : 4)} textAnchor="middle" fontSize={e.tipo === 'ZONA' ? 12 : 11.5} fontWeight={800}
                    fill={e.tipo === 'ZONA' ? color : '#0F172A'} style={{ fontFamily: 'Inter, system-ui, sans-serif', paintOrder: 'stroke' }} stroke="#fff" strokeWidth={3} strokeOpacity={0.85}>
                    {texto(`${nombreDe(e)}${!grande && sub ? ` · ${sub}` : ''}`)}</text>
                  {grande && sub && <text x={sx} y={sy + 12} textAnchor="middle" fontSize={10} fill="#475569" style={{ fontFamily: 'Consolas, monospace', paintOrder: 'stroke' }}
                    stroke="#fff" strokeWidth={3} strokeOpacity={0.85}>{sub}{verOcupacion && e.ocupacion_pct != null ? ` · ${Math.round(e.ocupacion_pct)}%` : ''}</text>}
                </g>
              )
            })}

            {/* asas de la selección */}
            {uno && !arrastre?.tipo.match(/mover|marco/) && (() => {
              const [L, F] = dims(uno)
              const toPx = (lx: number, ly: number) => aPantalla(...aMundo(uno, lx, ly))
              const [tx, ty] = toPx(0, -F / 2)
              const r = rad(uno.rotacion), nx = Math.sin(r), ny = -Math.cos(r)
              const hx = tx + nx * 26, hy = ty + ny * 26
              const asas: { p: [number, number]; esq: [number, number]; cursor: string }[] = esEstructura(uno)
                ? [{ p: toPx(L / 2, 0), esq: [1, 0], cursor: 'ew-resize' }]
                : uno.tipo === 'COLUMNA' ? [] : [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => ({ p: toPx((a * L) / 2, (b * F) / 2), esq: [a, b] as [number, number], cursor: 'nwse-resize' }))
              return (
                <g>
                  <line x1={tx} y1={ty} x2={hx} y2={hy} stroke={ACENTO} strokeWidth={1.2} />
                  <circle cx={hx} cy={hy} r={6.5} fill="#fff" stroke={ACENTO} strokeWidth={1.8} style={{ cursor: 'grab' }} onPointerDown={ev => empezarRotar(ev, uno)} />
                  {asas.map((a, i) => (
                    <rect key={i} x={a.p[0] - 5} y={a.p[1] - 5} width={10} height={10} rx={2} fill="#fff" stroke={ACENTO} strokeWidth={1.8}
                      style={{ cursor: a.cursor }} onPointerDown={ev => empezarEstirar(ev, uno, a.esq)}>
                      <title>{esEstructura(uno) ? 'Arrastre para agregar o quitar módulos' : 'Arrastre para cambiar el tamaño'}</title>
                    </rect>
                  ))}
                  {arrastre?.tipo === 'rotar' && <g>
                    <rect x={hx + 10} y={hy - 11} width={44} height={20} rx={4} fill="#0F172A" />
                    <text x={hx + 32} y={hy + 3} textAnchor="middle" fontSize={11} fill="#fff" style={{ fontFamily: 'Consolas, monospace' }}>{Math.round(uno.rotacion)}°</text>
                  </g>}
                  {arrastre?.tipo === 'estirar' && esEstructura(uno) && (() => { const [px, py] = toPx(L / 2, 0); return <g>
                    <rect x={px + 10} y={py - 11} width={92} height={20} rx={4} fill="#0F172A" />
                    <text x={px + 56} y={py + 3} textAnchor="middle" fontSize={11} fill="#fff" style={{ fontFamily: 'Consolas, monospace' }}>{uno.modulos} mód · {fmt(L)} m</text></g> })()}
                </g>
              )
            })()}

            {/* medida de la regla */}
            {arrastre?.tipo === 'regla' && (() => {
              const [ax, ay] = aPantalla(...arrastre.a), [bx, by] = aPantalla(...arrastre.b)
              const dist = Math.hypot(arrastre.b[0] - arrastre.a[0], arrastre.b[1] - arrastre.a[1])
              return <g><rect x={(ax + bx) / 2 - 36} y={(ay + by) / 2 - 26} width={72} height={20} rx={4} fill="#0F172A" />
                <text x={(ax + bx) / 2} y={(ay + by) / 2 - 12} textAnchor="middle" fontSize={11.5} fill="#fff" style={{ fontFamily: 'Consolas, monospace' }}>{fmt(dist, 2)} m</text></g>
            })()}

            {/* reglas */}
            <g style={{ pointerEvents: 'none' }}>
              <rect x={0} y={0} width={tam.w} height={REGLA} fill="#FCFCFD" />
              <rect x={0} y={0} width={REGLA} height={tam.h} fill="#FCFCFD" />
              <line x1={0} y1={REGLA} x2={tam.w} y2={REGLA} stroke="#E2E8F0" /><line x1={REGLA} y1={0} x2={REGLA} y2={tam.h} stroke="#E2E8F0" />
              {lineasX.map(x => { const px = x * zoom + pan.x; if (px < REGLA) return null; const may = esMayor(x)
                return <g key={`rx${x}`}><line x1={px} y1={may ? 10 : 17} x2={px} y2={REGLA} stroke="#94A3B8" />{may && <text x={px + 3} y={11} fontSize={9.5} fill="#64748B" style={{ fontFamily: 'Consolas, monospace' }}>{fmt(x)}</text>}</g> })}
              {lineasY.map(y => { const py = y * zoom + pan.y; if (py < REGLA) return null; const may = esMayor(y)
                return <g key={`ry${y}`}><line x1={may ? 10 : 17} y1={py} x2={REGLA} y2={py} stroke="#94A3B8" />{may && <text x={11} y={py + 3} fontSize={9.5} fill="#64748B" transform={`rotate(-90 11 ${py + 3})`} style={{ fontFamily: 'Consolas, monospace' }}>{fmt(y)}</text>}</g> })}
              {cursor && <><line x1={aPantalla(cursor[0], 0)[0]} y1={0} x2={aPantalla(cursor[0], 0)[0]} y2={REGLA} stroke={ACENTO} strokeWidth={1.5} />
                <line x1={0} y1={aPantalla(0, cursor[1])[1]} x2={REGLA} y2={aPantalla(0, cursor[1])[1]} stroke={ACENTO} strokeWidth={1.5} /></>}
              <rect x={0} y={0} width={REGLA} height={REGLA} fill="#F1F5F9" />
              <text x={REGLA / 2} y={REGLA / 2 + 4} textAnchor="middle" fontSize={10} fontWeight={700} fill="#64748B">m</text>
            </g>
          </svg>

          {/* aviso del modo */}
          {modo !== 'seleccionar' && modo !== 'mano' && <Box sx={{ position: 'absolute', top: REGLA + 12, left: '50%', transform: 'translateX(-50%)', px: 1.75, py: 0.75,
            borderRadius: 5, bgcolor: '#0F172A', color: '#fff', fontSize: 12.5, boxShadow: '0 6px 20px rgba(15,23,42,0.25)', display: 'flex', alignItems: 'center', gap: 1, pointerEvents: 'none' }}>
            {modo === 'medir' ? 'Arrastre para medir una distancia' : modo === 'calibrar' ? 'Trace sobre el plano una medida que conozca (p. ej. un muro)'
              : `Clic para colocar ${CATALOGO[modo.split(':')[1] as Tipo].nombre.toLowerCase()} · Shift para varias · Esc para terminar`}
          </Box>}

          {/* bodega vacía */}
          {!els.length && <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
            <Box sx={{ pointerEvents: 'auto', bgcolor: '#fff', borderRadius: 3, p: 3, maxWidth: 440, textAlign: 'center', border: '1px solid', borderColor: 'divider', boxShadow: '0 12px 40px rgba(15,23,42,0.12)' }}>
              <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, mb: 1.5 }}><IconoTipo tipo="SELECTIVO" size={56} /><IconoTipo tipo="GONDOLA" size={56} /><IconoTipo tipo="PISO" size={56} /></Box>
              <Typography fontWeight={800} fontSize={18}>Construya su bodega</Typography>
              <Typography fontSize={13.5} color="text.secondary" mt={0.75} mb={2}>
                Arrastre estanterías desde la paleta {d.plano ? 'sobre el plano' : ''} y configúrelas con sus medidas. Al final, «Generar ubicaciones» crea las ubicaciones del WMS.
              </Typography>
              <Stack direction="row" gap={1} justifyContent="center" flexWrap="wrap">
                <Button variant="contained" startIcon={<CloudDownload />} onClick={importar} sx={{ textTransform: 'none', bgcolor: ACENTO, boxShadow: 'none' }}>Importar ubicaciones existentes</Button>
                <Button variant="outlined" onClick={() => setModo('colocar:SELECTIVO')} sx={{ textTransform: 'none' }}>Empezar en blanco</Button>
              </Stack>
            </Box>
          </Box>}

          {/* barra de estado */}
          <Stack direction="row" alignItems="center" gap={2} sx={{ position: 'absolute', left: REGLA, right: 0, bottom: 0, height: 28, px: 1.5, bgcolor: alpha('#FFFFFF', 0.92),
            borderTop: '1px solid', borderColor: 'divider', fontSize: 11.5, color: '#475569', fontFamily: 'Consolas, monospace', backdropFilter: 'blur(4px)', pointerEvents: 'none' }}>
            <span>X {cursor ? fmt(cursor[0], 2) : '—'} m</span><span>Y {cursor ? fmt(cursor[1], 2) : '—'} m</span>
            <span>Piso {fmt(config.ancho_m)} × {fmt(config.largo_m)} m</span>
            <Box flex={1} />
            <span>{totales.estructuras} estructuras</span><span>{fmt(totales.posiciones, 0)} posiciones</span>
            <span>{fmt(totales.volumen)} m³ útiles</span>
            <span>{fmt((totales.huella / Math.max(1, config.ancho_m * config.largo_m)) * 100)}% del piso</span>
            {seleccion.length > 0 && <span style={{ color: ACENTO, fontWeight: 700 }}>{seleccion.length} seleccionada(s)</span>}
          </Stack>
        </Box>

        {/* ── Inspector ── */}
        <Box sx={{ width: 312, borderLeft: '1px solid', borderColor: 'divider', overflowY: 'auto', bgcolor: '#fff', display: { xs: 'none', sm: 'block' } }}>
          {uno ? Inspector({ e: uno }) : seleccion.length > 1 ? InspectorVarios() : InspectorBodega()}
        </Box>
      </Box>

      {/* ── Diálogo: serie ── */}
      <Dialog open={!!serie} onClose={() => setSerie(null)} maxWidth="xs" fullWidth hideBackdrop PaperProps={{ sx: { position: 'absolute', right: 330, top: 120, m: 0, borderRadius: 3, boxShadow: '0 20px 50px rgba(15,23,42,0.25)' } }}>
        <DialogTitle sx={{ fontWeight: 800, pb: 0.5 }}>Crear en serie</DialogTitle>
        {serie && <DialogContent sx={{ pt: '12px !important' }}>
          <Typography fontSize={12.5} color="text.secondary" mb={2}>Copias de {uno ? nombreDe(uno) : ''} hacia un lado, con la vista previa en el plano.</Typography>
          <Stack gap={1.75}>
            <Stack direction="row" gap={1.5}>
              <Numero etiqueta="Cantidad" valor={serie.cantidad} min={1} max={60} decimales={0} onCambio={v => v && setSerie({ ...serie, cantidad: Math.round(v) })} />
              <TextField select size="small" fullWidth label="Hacia" value={serie.direccion} onChange={e => setSerie({ ...serie, direccion: Number(e.target.value) as 1 | -1 })}>
                <MenuItem value={1}>Un lado</MenuItem><MenuItem value={-1}>El otro lado</MenuItem>
              </TextField>
            </Stack>
            <ToggleButtonGroup exclusive fullWidth size="small" value={serie.modo} onChange={(_, v) => v && setSerie({ ...serie, modo: v })}>
              <ToggleButton value="espalda" sx={{ textTransform: 'none' }}>Espalda con espalda</ToggleButton>
              <ToggleButton value="simple" sx={{ textTransform: 'none' }}>Filas sencillas</ToggleButton>
            </ToggleButtonGroup>
            <Stack direction="row" gap={1.5}>
              <Numero etiqueta="Ancho de pasillo" valor={serie.pasillo} unidad="m" min={0.5} max={20} paso={0.1} onCambio={v => v && setSerie({ ...serie, pasillo: v })} />
              {serie.modo === 'espalda' && <Numero etiqueta="Holgura espalda" valor={serie.espalda} unidad="m" min={0} max={2} paso={0.05} onCambio={v => v != null && setSerie({ ...serie, espalda: v })} />}
            </Stack>
            <TextField select size="small" label="Numeración" value={serie.numerar} onChange={e => setSerie({ ...serie, numerar: e.target.value as any })}>
              <MenuItem value="estanteria">Siguiente estantería del mismo pasillo (01, 02, 03…)</MenuItem>
              <MenuItem value="pasillo">Un pasillo nuevo por {serie.modo === 'espalda' ? 'par' : 'fila'} (A, B, C…)</MenuItem>
            </TextField>
            <Alert severity="info" icon={false} sx={{ fontSize: 12.5 }}>
              Se crearán <b>{vistaSerie.length}</b> estructuras: {vistaSerie.slice(0, 4).map(e => nombreDe(e)).join(', ')}{vistaSerie.length > 4 ? '…' : ''}
              {' '}· {fmt(vistaSerie.reduce((s, e) => s + posicionesDe(e), 0), 0)} posiciones.
            </Alert>
          </Stack>
        </DialogContent>}
        <DialogActions sx={{ px: 3, pb: 2 }}><Button color="inherit" onClick={() => setSerie(null)}>Cancelar</Button>
          <Button variant="contained" onClick={aplicarSerie} sx={{ bgcolor: ACENTO, boxShadow: 'none' }}>Crear</Button></DialogActions>
      </Dialog>

      {/* ── Diálogo: calibrar ── */}
      <Dialog open={!!calibrar} onClose={() => setCalibrar(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>Calibrar la escala del plano</DialogTitle>
        <DialogContent>
          <Typography fontSize={13} color="text.secondary" mb={2}>La línea trazada mide {calibrar ? fmt(calibrar.medido, 2) : ''} m con la escala actual. ¿Cuánto mide en la realidad?</Typography>
          <TextField autoFocus size="small" fullWidth label="Medida real" value={calibrar?.real ?? ''} onChange={e => calibrar && setCalibrar({ ...calibrar, real: e.target.value })}
            onKeyDown={e => { if (e.key === 'Enter') aplicarCalibracion() }}
            InputProps={{ endAdornment: <InputAdornment position="end">m</InputAdornment> }} />
        </DialogContent>
        <DialogActions><Button color="inherit" onClick={() => setCalibrar(null)}>Cancelar</Button><Button onClick={aplicarCalibracion}>Aplicar escala</Button></DialogActions>
      </Dialog>

      {/* ── Diálogo: generar ubicaciones ── */}
      <Dialog open={!!generar} onClose={() => !generar?.cargando && setGenerar(null)} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}><AutoFixHigh sx={{ color: ACENTO }} />Generar ubicaciones del WMS
          <Box flex={1} /><IconButton size="small" onClick={() => setGenerar(null)} disabled={generar?.cargando}><Close fontSize="small" /></IconButton></DialogTitle>
        <DialogContent>
          {!generar?.res ? <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress size={28} /><Typography mt={1.5} color="text.secondary" fontSize={13}>Calculando…</Typography></Box> : (() => {
            const t = generar.res.totales
            const tarjetas = [['Por crear', t.crear, '#4F46E5'], ['Se actualizan', t.actualizar, '#0EA5E9'], ['Se adoptan (mismo código)', t.adoptar, '#10B981'],
              ['Se desactivan', t.desactivar, '#64748B'], ['Conflictos', t.conflictos, '#EF4444']] as [string, number, string][]
            return <>
              <Typography fontSize={13} color="text.secondary" mb={2}>Esto es lo que va a pasar con las ubicaciones al aplicar el layout (patrón <b style={{ fontFamily: 'Consolas, monospace' }}>{config.patron_codigo}</b>).
                Las ubicaciones con mercancía nunca se borran.</Typography>
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 1, mb: 2 }}>
                {tarjetas.map(([k, v, c]) => <Box key={k} sx={{ p: 1.25, borderRadius: 2, border: '1px solid', borderColor: 'divider', borderTop: `3px solid ${c}` }}>
                  <Typography sx={{ fontSize: 22, fontWeight: 800, color: v ? c : '#94A3B8', fontFamily: 'Consolas, monospace' }}>{v ?? 0}</Typography>
                  <Typography sx={{ fontSize: 11, color: 'text.secondary', lineHeight: 1.2 }}>{k}</Typography></Box>)}
              </Box>
              <Box sx={{ maxHeight: 280, overflowY: 'auto', border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                <Table size="small" stickyHeader>
                  <TableHead><TableRow>{['Estructura', 'Códigos', 'Crear', 'Actualizar', 'Adoptar', 'Desactivar', 'Conflictos'].map(h => <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, bgcolor: '#F8FAFC' }}>{h}</TableCell>)}</TableRow></TableHead>
                  <TableBody>{generar.res.elementos.map((r: any) => <TableRow key={r.elemento_id} hover>
                    <TableCell sx={{ fontWeight: 700, fontSize: 12.5 }}>{r.nombre}</TableCell>
                    <TableCell sx={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>{r.codigos?.length ? `${r.codigos[0]} … ${r.codigos[1]}` : '—'}</TableCell>
                    {['crear', 'actualizar', 'adoptar', 'desactivar', 'conflictos'].map(k => <TableCell key={k} sx={{ fontFamily: 'Consolas, monospace', fontSize: 12.5,
                      color: r[k] ? (k === 'conflictos' ? '#DC2626' : '#0F172A') : '#CBD5E1', fontWeight: r[k] ? 700 : 400 }}>{r[k]}</TableCell>)}
                  </TableRow>)}</TableBody>
                </Table>
              </Box>
              {generar.res.conflictos.length > 0 && <Alert severity="warning" sx={{ mt: 2 }}>
                <b>Estas posiciones se omiten:</b>
                <Box component="ul" sx={{ m: 0, pl: 2.5 }}>{generar.res.conflictos.slice(0, 8).map((c: any, i: number) => <li key={i}><b>{c.elemento}</b>: {c.detalle}</li>)}</Box>
              </Alert>}
              <FormControlLabel sx={{ mt: 1.5 }} control={<Checkbox size="small" checked={generar.renombrar} onChange={e => simular(e.target.checked)} />}
                label={<Typography fontSize={13}>Renombrar las ubicaciones existentes al patrón {t.renombrar ? <b>({t.renombrar})</b> : ''} <Typography component="span" fontSize={12} color="text.secondary">— cambia los códigos ya impresos en etiquetas</Typography></Typography>} />
            </>
          })()}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5 }}>
          <Button color="inherit" onClick={() => setGenerar(null)} disabled={generar?.cargando}>Cancelar</Button>
          <Button variant="contained" onClick={ejecutar} disabled={!generar?.res || generar.cargando}
            startIcon={generar?.cargando && generar.res ? <CircularProgress size={14} color="inherit" /> : <AutoFixHigh />} sx={{ bgcolor: ACENTO, boxShadow: 'none', textTransform: 'none' }}>
            Aplicar a las ubicaciones</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )

  // ═════════════════════════════════════════════════════════════════════════
  // Inspectores: funciones internas (comparten el estado del constructor). Se
  // llaman como funciones, no como <Componente/>, para que no se remonten en
  // cada tecla y los campos no pierdan el foco.
  // ═════════════════════════════════════════════════════════════════════════
  function Inspector({ e }: { e: El }) {
    const k = [e.clave]
    const [L, F] = dims(e)
    const color = colorDe(e, indice)
    const zona = zonaDe(e.zona_id)
    const ejemplo = (n: number, p: number) => codigoEjemplo(config.patron_codigo, d!.almacen.codigo, e, zona?.codigo, n, p)
    const niv = e.tipo === 'PISO' ? 1 : e.niveles, total = e.modulos * e.por_modulo
    return (
      <Box>
        <Stack direction="row" alignItems="center" gap={1.25} sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider', bgcolor: '#FCFCFD' }}>
          <Box sx={{ p: 0.5, borderRadius: 1.5, bgcolor: '#fff', border: '1px solid', borderColor: 'divider', display: 'flex' }}><IconoTipo tipo={e.tipo} size={36} /></Box>
          <Box flex={1} minWidth={0}>
            <Typography noWrap fontWeight={800} fontSize={15}>{nombreDe(e)}</Typography>
            <Typography fontSize={11.5} color="text.secondary">{CATALOGO[e.tipo].nombre}{e.id ? ` · #${e.id}` : ' · nueva'}</Typography>
          </Box>
          <Tooltip title="Color"><Box component="label" sx={{ width: 22, height: 22, borderRadius: 1, bgcolor: color, cursor: 'pointer', border: '2px solid #fff', boxShadow: '0 0 0 1px #CBD5E1', position: 'relative' }}>
            <input type="color" value={color} onChange={ev => cambiar(k, { color: ev.target.value }, 'color')} style={{ opacity: 0, position: 'absolute', inset: 0, cursor: 'pointer' }} />
          </Box></Tooltip>
        </Stack>

        {esEstructura(e) ? <>
          <Seccion titulo="Identificación">
            <Stack gap={1.25}>
              <Stack direction="row" gap={1}>
                <TextField size="small" label="Pasillo" value={e.pasillo ?? ''} onChange={ev => cambiar(k, { pasillo: ev.target.value.toUpperCase() || null }, 'pasillo')} />
                <TextField size="small" label="Estantería" value={e.estanteria ?? ''} onChange={ev => cambiar(k, { estanteria: ev.target.value.toUpperCase() || null }, 'estanteria')} />
              </Stack>
              <TextField select size="small" label="Zona del WMS" value={e.zona_id ?? ''} error={!e.zona_id} helperText={!e.zona_id ? 'Necesaria para generar sus ubicaciones' : undefined}
                onChange={ev => cambiar(k, { zona_id: Number(ev.target.value) || null })}>
                {d!.zonas.map(z => <MenuItem key={z.id} value={z.id}>{z.codigo} · {z.nombre}</MenuItem>)}
              </TextField>
              <TextField size="small" label="Nombre (opcional)" placeholder={[e.pasillo, e.estanteria].filter(Boolean).join('-')} value={e.nombre ?? ''}
                onChange={ev => cambiar(k, { nombre: ev.target.value || null }, 'nombre')} />
            </Stack>
          </Seccion>
          <Seccion titulo="Estructura">
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.25 }}>
              <Numero etiqueta={e.tipo === 'PISO' ? 'Posiciones' : 'Módulos (vanos)'} valor={e.modulos} min={1} max={200} decimales={0} onCambio={v => v && cambiar(k, { modulos: Math.round(v) }, 'modulos')} />
              {e.tipo !== 'PISO' && <Numero etiqueta="Posiciones / módulo" valor={e.por_modulo} min={1} max={10} decimales={0} onCambio={v => v && cambiar(k, { por_modulo: Math.round(v) }, 'por_modulo')} />}
              <Numero etiqueta={e.tipo === 'PISO' ? 'Estibas apiladas' : 'Niveles'} valor={e.niveles} min={1} max={30} decimales={0} onCambio={v => v && cambiar(k, { niveles: Math.round(v) }, 'niveles')} />
              <Numero etiqueta={e.tipo === 'PISO' ? 'Frente por posición' : 'Frente del módulo'} valor={e.frente_cm} unidad="cm" min={10} max={2000} onCambio={v => v && cambiar(k, { frente_cm: v }, 'frente')} />
              <Numero etiqueta="Fondo" valor={e.fondo_cm} unidad="cm" min={5} max={2000} onCambio={v => v && cambiar(k, { fondo_cm: v }, 'fondo')} />
              <Numero etiqueta={e.tipo === 'PISO' ? 'Alto por estiba' : 'Alto por nivel'} valor={e.alto_nivel_cm} unidad="cm" min={10} max={1500} onCambio={v => v && cambiar(k, { alto_nivel_cm: v }, 'alto')} />
              <Numero etiqueta="Capacidad / posición" valor={e.capacidad_kg} unidad="kg" min={0} onCambio={v => cambiar(k, { capacidad_kg: v }, 'cap')} />
            </Box>
          </Seccion>
        </> : <Seccion titulo={e.tipo === 'ZONA' ? 'Área' : 'Medidas'}>
          <Stack gap={1.25}>
            {e.tipo === 'ZONA' && <>
              <TextField select size="small" label="Tipo de área" value={e.categoria ?? 'OTRA'} onChange={ev => cambiar(k, { categoria: ev.target.value, color: null,
                nombre: !e.nombre || Object.values(AREAS).some(a => a.nombre === e.nombre) ? AREAS[ev.target.value].nombre : e.nombre })}>
                {Object.entries(AREAS).map(([c, a]) => <MenuItem key={c} value={c}><Box component="span" sx={{ display: 'inline-block', width: 10, height: 10, borderRadius: 0.5, bgcolor: a.color, mr: 1 }} />{a.nombre}</MenuItem>)}
              </TextField>
              <TextField size="small" label="Nombre" value={e.nombre ?? ''} onChange={ev => cambiar(k, { nombre: ev.target.value || null }, 'nombre')} />
              <TextField select size="small" label="Ubicación del WMS (opcional)" value={e.ubicacion_id ?? ''} helperText="Para ver su ocupación en la bodega 3D"
                onChange={ev => cambiar(k, { ubicacion_id: Number(ev.target.value) || null })}>
                <MenuItem value="">— ninguna —</MenuItem>
                {d!.ubicaciones_area.map(u => <MenuItem key={u.id} value={u.id}>{u.codigo}</MenuItem>)}
              </TextField>
            </>}
            {e.tipo === 'MURO' && <TextField size="small" label="Nombre" value={e.nombre ?? ''} onChange={ev => cambiar(k, { nombre: ev.target.value || null }, 'nombre')} />}
            <Stack direction="row" gap={1}>
              <Numero etiqueta={e.tipo === 'MURO' ? 'Largo' : 'Ancho'} valor={e.largo_m} unidad="m" min={0.1} max={2000} paso={0.1} onCambio={v => v && cambiar(k, { largo_m: v }, 'largo')} />
              <Numero etiqueta={e.tipo === 'MURO' ? 'Espesor' : 'Largo'} valor={e.ancho_m} unidad="m" min={0.05} max={2000} paso={0.05} onCambio={v => v && cambiar(k, { ancho_m: v }, 'ancho')} />
            </Stack>
          </Stack>
        </Seccion>}

        <Seccion titulo="Posición en el piso">
          <Stack gap={1.25}>
            <Stack direction="row" gap={1}>
              <Numero etiqueta="X (centro)" valor={e.x_m} unidad="m" paso={0.1} onCambio={v => v != null && cambiar(k, { x_m: v }, 'x')} />
              <Numero etiqueta="Y (centro)" valor={e.y_m} unidad="m" paso={0.1} onCambio={v => v != null && cambiar(k, { y_m: v }, 'y')} />
            </Stack>
            <Stack direction="row" gap={1} alignItems="center">
              <Numero etiqueta="Rotación" valor={e.rotacion} unidad="°" min={0} max={360} decimales={1} ancho={110} onCambio={v => v != null && cambiar(k, { rotacion: v % 360 }, 'rot')} />
              <ToggleButtonGroup size="small" exclusive value={[0, 90, 180, 270].includes(Math.round(e.rotacion)) ? Math.round(e.rotacion) : null} onChange={(_, v) => v != null && cambiar(k, { rotacion: v })}>
                {[0, 90, 180, 270].map(g => <ToggleButton key={g} value={g} sx={{ px: 0.9, fontSize: 11.5, fontFamily: 'Consolas, monospace' }}>{g}°</ToggleButton>)}
              </ToggleButtonGroup>
            </Stack>
          </Stack>
        </Seccion>

        {esEstructura(e) && <Seccion titulo="Resumen">
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.75 }}>
            <Dato etiqueta="Posiciones" valor={fmt(posicionesDe(e), 0)} />
            <Dato etiqueta="Huella" valor={`${fmt(L, 2)} × ${fmt(F, 2)} m`} />
            <Dato etiqueta="Altura" valor={`${fmt((e.alto_nivel_cm * e.niveles) / 100, 2)} m`} />
            <Dato etiqueta="Volumen útil" valor={`${fmt(posicionesDe(e) * (e.frente_cm / e.por_modulo) * e.fondo_cm * (e.tipo === 'PISO' ? e.alto_nivel_cm * e.niveles : e.alto_nivel_cm) / 1e6)} m³`} />
            {e.capacidad_kg != null && <Dato etiqueta="Carga total" valor={`${fmt((posicionesDe(e) * e.capacidad_kg) / 1000)} t`} />}
            {e.ocupacion_pct != null && <Dato etiqueta="Ocupación" valor={`${Math.round(e.ocupacion_pct)}%`} />}
          </Box>
        </Seccion>}

        {esEstructura(e) && <Seccion titulo="Ubicaciones del WMS">
          <Stack gap={1}>
            <Stack direction="row" justifyContent="space-between"><Typography fontSize={12.5} color="text.secondary">Vinculadas</Typography>
              <Typography fontSize={12.5} fontWeight={700} fontFamily="Consolas, monospace">{e.vinculadas ?? 0} / {niv * total}</Typography></Stack>
            <LinearProgress variant="determinate" value={Math.min(100, ((e.vinculadas ?? 0) / Math.max(1, niv * total)) * 100)}
              sx={{ height: 6, borderRadius: 3, bgcolor: '#F1F5F9', '& .MuiLinearProgress-bar': { bgcolor: (e.vinculadas ?? 0) >= niv * total ? '#10B981' : ACENTO } }} />
            <Typography fontSize={12} color="text.secondary">Códigos: <b style={{ fontFamily: 'Consolas, monospace', color: '#0F172A' }}>{e.codigos?.length ? e.codigos[0] : ejemplo(1, 1)}</b> … <b style={{ fontFamily: 'Consolas, monospace', color: '#0F172A' }}>{e.codigos?.length ? e.codigos[1] : ejemplo(niv, total)}</b></Typography>
            {(e.vinculadas ?? 0) < niv * total && <Alert severity="info" icon={false} sx={{ py: 0.25, fontSize: 12 }}>Faltan {niv * total - (e.vinculadas ?? 0)} ubicaciones: guarde y use «Generar ubicaciones».</Alert>}
            {(e.sobrantes ?? 0) > 0 && <Alert severity="warning" icon={false} sx={{ py: 0.25, fontSize: 12 }}>{e.sobrantes} ubicaciones quedaron fuera de la estructura: «Generar ubicaciones» las desactiva si están vacías.</Alert>}
            <TextField select size="small" label="Foto de referencia (opcional)" value={e.foto_id ?? ''} onChange={ev => cambiar(k, { foto_id: Number(ev.target.value) || null })}>
              <MenuItem value="">— ninguna —</MenuItem>
              {d!.fotos.map(f => <MenuItem key={f.id} value={f.id}>{f.nombre}</MenuItem>)}
            </TextField>
          </Stack>
        </Seccion>}
        <Box sx={{ p: 2 }}>
          <Button fullWidth color="error" variant="outlined" startIcon={<DeleteOutline />} onClick={eliminar} sx={{ textTransform: 'none', borderRadius: 2 }}>Quitar del layout</Button>
        </Box>
      </Box>
    )
  }

  function InspectorVarios() {
    const est = seleccion.filter(esEstructura)
    const claves = est.map(e => e.clave)
    const comun = <K extends keyof El>(campo: K) => est.length && est.every(e => e[campo] === est[0][campo]) ? est[0][campo] : null
    return (
      <Box>
        <Box sx={{ px: 2, py: 1.75, borderBottom: '1px solid', borderColor: 'divider', bgcolor: '#FCFCFD' }}>
          <Typography fontWeight={800} fontSize={15}>{seleccion.length} elementos</Typography>
          <Typography fontSize={12} color="text.secondary">{est.length} estructuras · {fmt(est.reduce((s, e) => s + posicionesDe(e), 0), 0)} posiciones</Typography>
        </Box>
        <Seccion titulo="Organizar">
          <Stack direction="row" flexWrap="wrap" gap={0.25}>
            <Herramienta titulo="Alinear a la izquierda" onClick={() => alinear('izq')}><AlignHorizontalLeft fontSize="small" /></Herramienta>
            <Herramienta titulo="Centrar horizontalmente" onClick={() => alinear('cx')}><AlignHorizontalCenter fontSize="small" /></Herramienta>
            <Herramienta titulo="Alinear a la derecha" onClick={() => alinear('der')}><AlignHorizontalRight fontSize="small" /></Herramienta>
            <Herramienta titulo="Alinear arriba" onClick={() => alinear('arr')}><AlignVerticalTop fontSize="small" /></Herramienta>
            <Herramienta titulo="Centrar verticalmente" onClick={() => alinear('cy')}><AlignVerticalCenter fontSize="small" /></Herramienta>
            <Herramienta titulo="Alinear abajo" onClick={() => alinear('aba')}><AlignVerticalBottom fontSize="small" /></Herramienta>
            <Herramienta titulo="Distribuir horizontalmente" disabled={seleccion.length < 3} onClick={() => distribuir('x')}><HorizontalDistribute fontSize="small" /></Herramienta>
            <Herramienta titulo="Distribuir verticalmente" disabled={seleccion.length < 3} onClick={() => distribuir('y')}><VerticalDistribute fontSize="small" /></Herramienta>
          </Stack>
        </Seccion>
        {est.length > 0 && <Seccion titulo="Editar en bloque">
          <Stack gap={1.25}>
            <TextField select size="small" label="Zona del WMS" value={comun('zona_id') ?? ''} onChange={ev => cambiar(claves, { zona_id: Number(ev.target.value) || null })}>
              {d!.zonas.map(z => <MenuItem key={z.id} value={z.id}>{z.codigo} · {z.nombre}</MenuItem>)}
            </TextField>
            <TextField size="small" label="Pasillo" value={(comun('pasillo') as string) ?? ''} placeholder="(varios)" onChange={ev => cambiar(claves, { pasillo: ev.target.value.toUpperCase() || null }, 'pasillo')} />
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.25 }}>
              <Numero etiqueta="Niveles" valor={comun('niveles') as number | null} min={1} max={30} decimales={0} onCambio={v => v && cambiar(claves, { niveles: Math.round(v) }, 'niveles')} />
              <Numero etiqueta="Módulos" valor={comun('modulos') as number | null} min={1} max={200} decimales={0} onCambio={v => v && cambiar(claves, { modulos: Math.round(v) }, 'modulos')} />
              <Numero etiqueta="Fondo" valor={comun('fondo_cm') as number | null} unidad="cm" min={5} onCambio={v => v && cambiar(claves, { fondo_cm: v }, 'fondo')} />
              <Numero etiqueta="Alto por nivel" valor={comun('alto_nivel_cm') as number | null} unidad="cm" min={10} onCambio={v => v && cambiar(claves, { alto_nivel_cm: v }, 'alto')} />
            </Box>
          </Stack>
        </Seccion>}
        <Box sx={{ p: 2 }}><Button fullWidth color="error" variant="outlined" startIcon={<DeleteOutline />} onClick={eliminar} sx={{ textTransform: 'none', borderRadius: 2 }}>Quitar {seleccion.length} del layout</Button></Box>
      </Box>
    )
  }

  function InspectorBodega() {
    const tokens = ['{almacen}', '{zona}', '{pasillo}', '{estanteria}', '{posicion}', '{nivel}', '{nivel:02d}']
    return (
      <Box>
        <Stack direction="row" alignItems="center" gap={1.25} sx={{ px: 2, py: 1.75, borderBottom: '1px solid', borderColor: 'divider', bgcolor: '#FCFCFD' }}>
          <Tune sx={{ color: ACENTO }} />
          <Box><Typography fontWeight={800} fontSize={15}>{d!.almacen.nombre}</Typography>
            <Typography fontSize={11.5} color="text.secondary">Configuración de la bodega</Typography></Box>
        </Stack>
        <Seccion titulo="Indicadores">
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.75 }}>
            <Dato etiqueta="Estructuras" valor={String(totales.estructuras)} />
            <Dato etiqueta="Posiciones" valor={fmt(totales.posiciones, 0)} />
            <Dato etiqueta="Volumen útil" valor={`${fmt(totales.volumen)} m³`} />
            <Dato etiqueta="Piso ocupado" valor={`${fmt((totales.huella / Math.max(1, config.ancho_m * config.largo_m)) * 100)}%`} />
          </Box>
          {totales.sinZona > 0 && <Alert severity="warning" sx={{ mt: 1.25, py: 0, fontSize: 12 }}>{totales.sinZona} estructura(s) sin zona del WMS.</Alert>}
          <FormControlLabel sx={{ mt: 1 }} control={<Checkbox size="small" checked={verOcupacion} onChange={e => setVerOcupacion(e.target.checked)} />}
            label={<Typography fontSize={13}>Ver la ocupación sobre el plano</Typography>} />
        </Seccion>
        <Seccion titulo="Piso">
          <Stack direction="row" gap={1}>
            <Numero etiqueta="Ancho" valor={config.ancho_m} unidad="m" min={2} max={2000} paso={0.5} onCambio={v => v && cambiarConfig({ ancho_m: v }, 'ancho')} />
            <Numero etiqueta="Largo" valor={config.largo_m} unidad="m" min={2} max={2000} paso={0.5} onCambio={v => v && cambiarConfig({ largo_m: v }, 'largo')} />
          </Stack>
        </Seccion>
        <Seccion titulo="Plano de fondo">
          {d!.plano ? <Stack gap={1.25}>
            <ToggleButtonGroup exclusive fullWidth size="small" value={verPlano} onChange={(_, v) => v && setVerPlano(v)}>
              <ToggleButton value="original" sx={{ textTransform: 'none', fontSize: 12 }}>Original</ToggleButton>
              <ToggleButton value="vector" disabled={!d!.plano.vectorizado} sx={{ textTransform: 'none', fontSize: 12 }}>Vectorizado</ToggleButton>
              <ToggleButton value="oculto" sx={{ textTransform: 'none', fontSize: 12 }}>Oculto</ToggleButton>
            </ToggleButtonGroup>
            <Box sx={{ px: 0.5 }}><Typography fontSize={11.5} color="text.secondary">Opacidad</Typography>
              <Slider size="small" value={opacidadPlano} min={0.1} max={1} step={0.05} onChange={(_, v) => setOpacidadPlano(v as number)} sx={{ color: ACENTO }} /></Box>
            <Stack direction="row" gap={1}>
              <Numero etiqueta="Desplazar X" valor={config.plano_x_m} unidad="m" paso={0.1} onCambio={v => v != null && cambiarConfig({ plano_x_m: v }, 'px')} />
              <Numero etiqueta="Desplazar Y" valor={config.plano_y_m} unidad="m" paso={0.1} onCambio={v => v != null && cambiarConfig({ plano_y_m: v }, 'py')} />
            </Stack>
            <Typography fontSize={12} color="text.secondary">
              Escala: 1 px = {config.escala_m_px ? fmt(config.escala_m_px * 100, 2) : '?'} cm · el plano mide {config.escala_m_px ? `${fmt(d!.plano.ancho * config.escala_m_px)} × ${fmt(d!.plano.alto * config.escala_m_px)} m` : '—'}
            </Typography>
            <Button size="small" variant="outlined" startIcon={<SquareFoot />} onClick={() => setModo('calibrar')} sx={{ textTransform: 'none' }}>Calibrar con una medida conocida</Button>
          </Stack> : <Typography fontSize={12.5} color="text.secondary">Cargue el plano en la pestaña «Plano» para calcar encima.</Typography>}
        </Seccion>
        <Seccion titulo="Codificación de ubicaciones">
          <TextField size="small" fullWidth label="Patrón" value={config.patron_codigo} onChange={e => cambiarConfig({ patron_codigo: e.target.value }, 'patron')}
            inputProps={{ style: { fontFamily: 'Consolas, monospace', fontSize: 13 } }} />
          <Stack direction="row" flexWrap="wrap" gap={0.5} mt={1}>
            {tokens.map(t => <Chip key={t} size="small" label={t} variant="outlined" onClick={() => cambiarConfig({ patron_codigo: config.patron_codigo + t })}
              sx={{ fontFamily: 'Consolas, monospace', fontSize: 11 }} />)}
          </Stack>
          <Box sx={{ mt: 1.25, p: 1, borderRadius: 1.5, bgcolor: '#F8FAFC', border: '1px dashed #CBD5E1' }}>
            <Typography fontSize={11} color="text.secondary">Ejemplo · pasillo A, estantería 01, posición 2, nivel 3</Typography>
            <Typography fontSize={15} fontWeight={800} fontFamily="Consolas, monospace">{codigoEjemplo(config.patron_codigo, d!.almacen.codigo, { pasillo: 'A', estanteria: '01' }, 'ZONA', 3, 2)}</Typography>
          </Box>
        </Seccion>
        <Seccion titulo="Atajos">
          <Box sx={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 1.5, rowGap: 0.5, fontSize: 12 }}>
            {[['V / H / M', 'Seleccionar · mano · medir'], ['Shift + clic', 'Agregar a la selección'], ['Arrastrar vacío', 'Seleccionar con marco'], ['R', 'Rotar 90°'], ['Ctrl + D', 'Duplicar'],
              ['Flechas', `Mover ${paso < 1 ? paso * 100 + ' cm' : '1 m'} (Shift: 1 m)`], ['Alt', 'Arrastrar sin imán'], ['Espacio', 'Desplazar la vista'], ['F', 'Encuadrar'], ['Ctrl + S', 'Guardar']].map(([a, b]) => <Fragment key={a}>
              <Box key={a} component="kbd" sx={{ fontFamily: 'Consolas, monospace', fontSize: 11, px: 0.75, py: 0.1, borderRadius: 0.75, bgcolor: '#F1F5F9', border: '1px solid #E2E8F0', whiteSpace: 'nowrap', justifySelf: 'start' }}>{a}</Box>
              <Typography key={b} fontSize={12} color="text.secondary">{b}</Typography></Fragment>)}
          </Box>
        </Seccion>
      </Box>
    )
  }
}
