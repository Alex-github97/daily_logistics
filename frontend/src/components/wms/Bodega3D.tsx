/**
 * Bodega virtual 3D (WMS › Mapa de bodega › Bodega 3D).
 *
 * Si el almacén tiene layout (pestaña Constructor), la bodega sale de ahí: cada
 * estructura con su tipo (rack selectivo, góndola, cantiléver, piso), sus
 * medidas y su lugar en metros, más las áreas, muros y columnas. Si no, de las
 * fotos calibradas y sus marcas en el plano.
 * Cada estantería tiene su color; las celdas se «llenan» de ese color en la
 * proporción de su ocupación, y una caja fantasma muestra la capacidad total.
 * El piso es el plano vectorizado.
 *
 * Navegación: arrastrar = girar · clic derecho o Shift + arrastrar = desplazar ·
 * rueda = zoom · W A S D / flechas = caminar · Q / E = girar · modo «Caminar»
 * pone la cámara a la altura de una persona.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Button, Chip, LinearProgress, Stack, ToggleButton, ToggleButtonGroup, Typography, alpha } from '@mui/material'
import { CenterFocusStrong, DirectionsWalk, Edit, Fullscreen, Map as MapaIcon, ThreeDRotation, OpenInNew } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { apiClient as api } from '@/api/client'
import { area as areaPol, cajaDe, muestrear, type Pt, type XY } from './geometria'

const PALETA = ['#0EA5E9', '#8B5CF6', '#10B981', '#EC4899', '#F59E0B', '#3B82F6', '#F97316', '#14B8A6', '#A855F7', '#EF4444']
const SEMAFORO: Record<string, string> = {
  VACIA: '#CBD5E1', OCUPADA: '#10B981', CASI_LLENA: '#F59E0B', LLENA: '#EF4444', BLOQUEADA: '#A855F7', SIN_ASIGNAR: '#E2E8F0',
}
const BUSCADO = '#3B82F6'
const fmt = (n: number) => n.toLocaleString('es-CO', { maximumFractionDigits: 1 })

interface Celda { nivel: number; posicion: number; codigo: string | null; estado: string; ocupacion_pct: number | null; unidades: number;
  contenido: { sku: string; nombre: string; unidades: number }[]; resaltar: boolean }
interface Rack { id: string; elemento_id: number | null; foto_id: number | null; tipo: string; color: string | null; por_modulo: number
  nombre: string; niveles: number; posiciones: number; frente_m: number; fondo_m: number; alto_nivel_m: number;
  largo_m: number; alto_m: number; ocupadas: number; celdas_total: number; ocupacion_pct: number; unidades: number;
  x: number; z: number; rotacion: number; celdas: Celda[] }
interface Area { id: string; tipo: 'ZONA' | 'MURO' | 'COLUMNA' | 'POLIMURO' | 'POLIZONA'; nombre: string | null; categoria: string | null; color: string | null
  x: number; z: number; largo_m: number; ancho_m: number; rotacion: number; ocupacion: { ocupacion_pct: number | null; unidades: number } | null
  forma?: { puntos: Pt[]; cerrado: boolean } | null; espesor_m?: number }
interface Escena { piso: { ancho_m: number; largo_m: number; plano_id: number | null; plano_rect?: { x: number; y: number; w: number; h: number } | null; contorno?: Pt[] | null } | null
  racks: Rack[]; areas?: Area[]; origen?: string
  resumen: { estanterias: number; posiciones: number; ocupadas: number; unidades: number } }
const COLOR_AREA: Record<string, string> = {
  RECEPCION: '#F59E0B', DESPACHO: '#10B981', STAGING: '#06B6D4', CUARENTENA: '#EF4444', SALA_VENTAS: '#8B5CF6',
  MUELLE: '#64748B', PASILLO: '#EAB308', OFICINAS: '#94A3B8', SERVICIOS: '#A8A29E', OTRA: '#3B82F6', NO_TRANSITABLE: '#64748B',
}

/** Rótulo plano para pintar sobre el piso (áreas). */
function rotuloPiso(texto: string, color: string, ancho: number): THREE.Mesh {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 192
  const g = c.getContext('2d')!
  g.font = 'bold 84px Inter, Arial, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'
  g.fillStyle = color; g.globalAlpha = 0.85; g.fillText(texto.toUpperCase(), 512, 96, 1000)
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4
  const m = new THREE.Mesh(new THREE.PlaneGeometry(ancho, ancho * 0.1875), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }))
  m.rotation.x = -Math.PI / 2
  return m
}

/** Etiqueta flotante (sprite) con nombre, % y barra. */
function etiqueta(texto: string, pct: number, color: string): THREE.Sprite {
  const c = document.createElement('canvas'); c.width = 512; c.height = 160
  const g = c.getContext('2d')!
  g.fillStyle = 'rgba(255,255,255,0.95)'; g.strokeStyle = color; g.lineWidth = 6
  g.beginPath(); g.roundRect(6, 6, 500, 148, 26); g.fill(); g.stroke()
  g.fillStyle = '#0F172A'; g.font = 'bold 52px Consolas, monospace'; g.textBaseline = 'middle'
  g.fillText(texto, 30, 52)
  g.fillStyle = color; g.font = 'bold 46px Consolas, monospace'; g.textAlign = 'right'
  g.fillText(`${Math.round(pct)}%`, 482, 52)
  g.fillStyle = '#E2E8F0'; g.beginPath(); g.roundRect(30, 100, 452, 26, 13); g.fill()
  g.fillStyle = color; g.beginPath(); g.roundRect(30, 100, Math.max(26, 452 * Math.min(1, pct / 100)), 26, 13); g.fill()
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true }))
  s.scale.set(3.2, 1.0, 1); s.renderOrder = 10
  return s
}

/** Forma plana (en el plano del piso) a partir de puntos (x, z) en metros. */
function formaPlana(pts: XY[], uv?: (x: number, z: number) => [number, number]): THREE.ShapeGeometry {
  const geo = new THREE.ShapeGeometry(new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, -z))))
  geo.rotateX(-Math.PI / 2)                        // (x, -z) → (x, 0, z)
  if (uv) {
    const pos = geo.attributes.position, uvs = geo.attributes.uv
    for (let i = 0; i < pos.count; i++) { const [u, v] = uv(pos.getX(i), pos.getZ(i)); uvs.setXY(i, u, v) }
    uvs.needsUpdate = true
  }
  return geo
}
/** Muro recto entre dos puntos (x, z). */
function tramoMuro(a: XY, b: XY, espesor: number, alto: number, mat: THREE.Material): THREE.Mesh | null {
  const largo = Math.hypot(b[0] - a[0], b[1] - a[1])
  if (largo < 1e-3) return null
  const m = new THREE.Mesh(new THREE.BoxGeometry(largo + espesor * 0.98, alto, espesor), mat)
  m.position.set((a[0] + b[0]) / 2, alto / 2, (a[1] + b[1]) / 2)
  m.rotation.y = -Math.atan2(b[1] - a[1], b[0] - a[0])
  m.castShadow = true; m.receiveShadow = true
  return m
}

async function blobUrl(ruta: string) {
  const r = await api.get(ruta, { responseType: 'blob' }); return URL.createObjectURL(r.data)
}
function cargar(url: string) {
  return new Promise<HTMLImageElement>((ok, mal) => { const i = new Image(); i.onload = () => ok(i); i.onerror = mal; i.src = url })
}

export default function Bodega3D({ almacen, productoId, onAbrir, onEditar }: {
  almacen: number; productoId?: number; onAbrir: (fotoId: number) => void; onEditar?: (elementoId: number) => void
}) {
  const escena = useQuery<Escena>({ queryKey: ['mapa-3d', almacen, productoId], refetchInterval: 30_000,
    queryFn: () => api.get('/wms/mapa/3d', { params: { almacen_id: almacen, producto_id: productoId } }).then(r => r.data) })
  const caja = useRef<HTMLDivElement>(null)
  const lienzo = useRef<HTMLDivElement>(null)
  const ctrl = useRef<{ vista: (v: 'iso' | 'aerea' | 'caminar') => void; enfocar: (r: Rack) => void } | null>(null)
  const [modoColor, setModoColor] = useState<'rack' | 'ocupacion'>('rack')
  const [hover, setHover] = useState<{ x: number; y: number; rack: Rack; celda: Celda } | null>(null)
  const [sel, setSel] = useState<Rack | null>(null)
  const [caminando, setCaminando] = useState(false)
  const caminandoRef = useRef(false)
  useEffect(() => { caminandoRef.current = caminando }, [caminando])
  const colorRack = useMemo(() => new Map((escena.data?.racks ?? []).map((r, i) => [r.id, r.color ?? PALETA[i % PALETA.length]])), [escena.data])

  useEffect(() => {
    const d = escena.data, host = lienzo.current
    if (!d || !host || !d.racks.length) return
    const ancho = d.piso?.ancho_m ?? 40, largo = d.piso?.largo_m ?? 30
    const W = () => host.clientWidth, H = () => host.clientHeight

    // ── Escena, cámara y luces ──
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#EEF2F7')
    scene.fog = new THREE.Fog('#EEF2F7', Math.max(ancho, largo) * 1.2, Math.max(ancho, largo) * 3)
    const camara = new THREE.PerspectiveCamera(45, W() / H(), 0.1, 800)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio)); renderer.setSize(W(), H())
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.toneMapping = THREE.NoToneMapping; renderer.outputColorSpace = THREE.SRGBColorSpace
    host.appendChild(renderer.domElement)
    scene.add(new THREE.HemisphereLight('#ffffff', '#CBD5E1', 1.7))
    const sol = new THREE.DirectionalLight('#ffffff', 1.3)
    sol.position.set(ancho * 0.3, 40, largo * 0.2); sol.castShadow = true
    sol.shadow.mapSize.set(2048, 2048)
    const ext = Math.max(ancho, largo) * 0.7
    Object.assign(sol.shadow.camera, { left: -ext, right: ext, top: ext, bottom: -ext, far: 150 })
    scene.add(sol)

    // ── Piso: cuadrícula de 1 m y, si hay plano, el plano en su rectángulo real.
    //    Con contorno, el piso toma la forma real del edificio y se levantan sus muros. ──
    const contorno = (d.piso?.contorno?.length ?? 0) >= 3 ? muestrear(d.piso!.contorno!, true) : null
    const pisoMat = new THREE.MeshStandardMaterial({ color: '#F8FAFC', roughness: 0.95, metalness: 0, side: THREE.DoubleSide })
    let piso: THREE.Mesh
    if (contorno) {
      const geo = formaPlana(contorno.map(([x, y]) => [x - ancho / 2, y - largo / 2] as XY),
        (x, z) => [(x + ancho / 2) / ancho, 1 - (z + largo / 2) / largo])
      piso = new THREE.Mesh(geo, pisoMat)
      // terreno exterior, tenue
      const fuera = new THREE.Mesh(new THREE.PlaneGeometry(ancho + 20, largo + 20), new THREE.MeshStandardMaterial({ color: '#E2E8F0', roughness: 1 }))
      fuera.rotation.x = -Math.PI / 2; fuera.position.y = -0.02; fuera.receiveShadow = true; scene.add(fuera)
      const matPerimetro = new THREE.MeshStandardMaterial({ color: '#CBD5E1', roughness: 0.85, transparent: true, opacity: 0.55 })
      contorno.forEach((q, i) => {
        const b = contorno[(i + 1) % contorno.length]
        const m = tramoMuro([q[0] - ancho / 2, q[1] - largo / 2], [b[0] - ancho / 2, b[1] - largo / 2], 0.3, 3, matPerimetro)
        if (m) { m.castShadow = false; scene.add(m) }
      })
    } else {
      piso = new THREE.Mesh(new THREE.PlaneGeometry(ancho, largo), pisoMat); piso.rotation.x = -Math.PI / 2
    }
    piso.receiveShadow = true; scene.add(piso)
    const urls: string[] = []
    const pintarPiso = (img?: HTMLImageElement, svg?: HTMLImageElement) => {
      const c = document.createElement('canvas'); c.width = 4096; c.height = Math.round(4096 * largo / ancho)
      const g = c.getContext('2d')!
      g.fillStyle = '#F8FAFC'; g.fillRect(0, 0, c.width, c.height)
      g.strokeStyle = 'rgba(100,116,139,0.14)'; g.lineWidth = 2
      const paso = c.width / ancho                       // una línea por metro
      for (let x = 0; x < c.width; x += paso) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, c.height); g.stroke() }
      for (let y = 0; y < c.height; y += paso) { g.beginPath(); g.moveTo(0, y); g.lineTo(c.width, y); g.stroke() }
      const pr = d.piso?.plano_rect
      const [rx, ry, rw, rh] = pr ? [pr.x * paso, pr.y * paso, pr.w * paso, pr.h * paso] : [0, 0, c.width, c.height]
      if (img) {
        // textos del plano original, tenues; encima los trazos vectorizados
        g.globalAlpha = 0.35; g.globalCompositeOperation = 'multiply'; g.filter = 'grayscale(1)'
        g.drawImage(img, rx, ry, rw, rh)
        g.globalAlpha = 1; g.globalCompositeOperation = 'source-over'; g.filter = 'none'
      }
      if (svg) g.drawImage(svg, rx, ry, rw, rh)
      const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = renderer.capabilities.getMaxAnisotropy()
      pisoMat.map?.dispose(); pisoMat.map = tex; pisoMat.color.set('#ffffff')
      pisoMat.needsUpdate = true
    }
    pintarPiso()
    if (d.piso?.plano_id) {
      ;(async () => {
        try {
          const [uSvg, uImg] = await Promise.all([blobUrl(`/wms/mapa/plano/${d.piso!.plano_id}/svg`), blobUrl(`/wms/mapa/plano/${d.piso!.plano_id}/imagen`)])
          urls.push(uSvg, uImg)
          const [svg, img] = await Promise.all([cargar(uSvg), cargar(uImg)])
          pintarPiso(img, svg)
        } catch { /* sin plano: queda la cuadrícula */ }
      })()
    }

    // ── Áreas, muros y columnas ──
    for (const a of d.areas ?? []) {
      const grupo = new THREE.Group()
      grupo.position.set(a.x - ancho / 2, 0, a.z - largo / 2)
      grupo.rotation.y = -(a.rotacion * Math.PI) / 180
      scene.add(grupo)
      if (a.tipo === 'POLIZONA' && a.forma?.puntos.length) {
        const veto = a.categoria === 'NO_TRANSITABLE'
        const color = a.color ?? COLOR_AREA[a.categoria ?? 'OTRA'] ?? COLOR_AREA.OTRA
        const lin = muestrear(a.forma.puntos, true)
        const placa = new THREE.Mesh(formaPlana(lin), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: veto ? 0.3 : 0.16, depthWrite: false, side: THREE.DoubleSide }))
        placa.position.y = 0.015; grupo.add(placa)
        const borde = new THREE.Line(new THREE.BufferGeometry().setFromPoints([...lin, lin[0]].map(([x, z]) => new THREE.Vector3(x, 0.03, z))),
          veto ? new THREE.LineBasicMaterial({ color }) : new THREE.LineDashedMaterial({ color, dashSize: 0.6, gapSize: 0.35 }))
        borde.computeLineDistances(); grupo.add(borde)
        const b = cajaDe(lin), pct = a.ocupacion?.ocupacion_pct
        if (areaPol(lin) > 2) {
          const rot = rotuloPiso(`${a.nombre ?? ''}${pct != null ? ` · ${Math.round(pct)}%` : ''}`, color, Math.min((b.x1 - b.x0) * 0.7, (b.y1 - b.y0) * 2.4))
          rot.position.set((b.x0 + b.x1) / 2, 0.04, (b.y0 + b.y1) / 2); grupo.add(rot)
        }
      } else if (a.tipo === 'POLIMURO' && a.forma?.puntos.length) {
        const mat = new THREE.MeshStandardMaterial({ color: '#CBD5E1', roughness: 0.8, transparent: true, opacity: 0.7 })
        const lin = muestrear(a.forma.puntos, a.forma.cerrado)
        const tramos = a.forma.cerrado ? lin.length : lin.length - 1
        for (let i = 0; i < tramos; i++) { const m = tramoMuro(lin[i], lin[(i + 1) % lin.length], a.espesor_m ?? 0.2, 2.4, mat); if (m) grupo.add(m) }
      } else if (a.tipo === 'ZONA') {
        const color = a.color ?? COLOR_AREA[a.categoria ?? 'OTRA'] ?? COLOR_AREA.OTRA
        const placa = new THREE.Mesh(new THREE.PlaneGeometry(a.largo_m, a.ancho_m),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.16, depthWrite: false }))
        placa.rotation.x = -Math.PI / 2; placa.position.y = 0.015; grupo.add(placa)
        const pts = [[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]].map(([x, z]) => new THREE.Vector3((x * a.largo_m) / 2, 0.03, (z * a.ancho_m) / 2))
        const borde = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color, dashSize: 0.6, gapSize: 0.35 }))
        borde.computeLineDistances(); grupo.add(borde)
        const pct = a.ocupacion?.ocupacion_pct
        const rot = rotuloPiso(`${a.nombre ?? ''}${pct != null ? ` · ${Math.round(pct)}%` : ''}`, color, Math.min(a.largo_m * 0.75, a.ancho_m * 2.6))
        rot.position.y = 0.04; grupo.add(rot)
      } else {
        const alto = a.tipo === 'MURO' ? 2.4 : 5.5
        const m = new THREE.Mesh(new THREE.BoxGeometry(a.largo_m, alto, a.ancho_m), new THREE.MeshStandardMaterial({
          color: a.tipo === 'MURO' ? '#CBD5E1' : '#D5DCE5', roughness: 0.8, transparent: a.tipo === 'MURO', opacity: a.tipo === 'MURO' ? 0.6 : 1 }))
        m.position.y = alto / 2; m.castShadow = a.tipo === 'COLUMNA'; m.receiveShadow = true; grupo.add(m)
      }
    }

    // ── Estanterías ──
    const matNaranja = new THREE.MeshStandardMaterial({ color: '#EA580C', roughness: 0.5, metalness: 0.5 })
    const matPoste = new THREE.MeshStandardMaterial({ color: '#64748B', roughness: 0.5, metalness: 0.4 })
    const matLarguero = new THREE.MeshStandardMaterial({ color: '#F97316', roughness: 0.45, metalness: 0.5 })
    const matArriostre = new THREE.LineBasicMaterial({ color: '#94A3B8', transparent: true, opacity: 0.8 })
    const matEstiba = new THREE.MeshStandardMaterial({ color: '#8B6B4A', roughness: 0.9 })
    const matEntrepano = new THREE.MeshStandardMaterial({ color: '#E2E8F0', roughness: 0.6, metalness: 0.2 })
    const matPanel = new THREE.MeshStandardMaterial({ color: '#CBD5E1', roughness: 0.7, transparent: true, opacity: 0.85 })
    const matDemarcacion = new THREE.LineBasicMaterial({ color: '#EAB308' })
    const interactivos: THREE.Object3D[] = []
    const pulsos: THREE.MeshStandardMaterial[] = []
    const etiquetas: THREE.Sprite[] = []
    for (const r of d.racks) {
      const grupo = new THREE.Group()
      grupo.position.set(r.x - ancho / 2, 0, r.z - largo / 2)
      grupo.rotation.y = -(r.rotacion * Math.PI) / 180
      scene.add(grupo)
      const tipo = r.tipo ?? 'SELECTIVO'
      const L = r.largo_m, F = Math.max(0.4, r.fondo_m), Ht = r.alto_m
      const Hn = tipo === 'PISO' ? Ht : r.alto_nivel_m      // en piso la «celda» es la pila completa
      const color = modoColor === 'rack' ? colorRack.get(r.id)! : '#94A3B8'
      const modulos = Math.max(1, Math.round(r.posiciones / (r.por_modulo || 1))), anchoMod = L / modulos
      if (tipo === 'SELECTIVO') {
        // postes (los extremos naranja, como en las bodegas reales)
        const posteGeo = new THREE.BoxGeometry(0.09, Ht + 0.25, 0.09)
        for (let i = 0; i <= modulos; i++) {
          const x = -L / 2 + i * anchoMod
          for (const z of [-F / 2, F / 2]) {
            const m = new THREE.Mesh(posteGeo, i === 0 || i === modulos ? matNaranja : matPoste)
            m.position.set(x, (Ht + 0.25) / 2, z); m.castShadow = true; grupo.add(m)
          }
          // arriostres en zigzag del marco lateral
          const pts: THREE.Vector3[] = []
          const tramos = Math.max(3, Math.round(Ht / 0.9))
          for (let k = 0; k < tramos; k++) {
            const y0 = (k / tramos) * Ht, y1 = ((k + 1) / tramos) * Ht
            pts.push(new THREE.Vector3(x, y0, k % 2 ? F / 2 : -F / 2), new THREE.Vector3(x, y1, k % 2 ? -F / 2 : F / 2))
          }
          grupo.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), matArriostre))
        }
        // largueros
        const largGeo = new THREE.BoxGeometry(L, 0.11, 0.06)
        for (let n = 1; n <= r.niveles; n++) {
          for (const z of [-F / 2, F / 2]) {
            const m = new THREE.Mesh(largGeo, matLarguero); m.position.set(0, n * Hn - 0.06, z); m.castShadow = true; grupo.add(m)
          }
        }
      } else if (tipo === 'GONDOLA') {
        // góndola: postes, entrepaños y panel central (doble cara)
        const posteGeo = new THREE.BoxGeometry(0.05, Ht + 0.1, 0.05)
        for (let i = 0; i <= modulos; i++) {
          const x = -L / 2 + i * anchoMod
          for (const z of [-F / 2, 0, F / 2]) {
            const m = new THREE.Mesh(posteGeo, matPoste); m.position.set(x, (Ht + 0.1) / 2, z); grupo.add(m)
          }
        }
        const entrepano = new THREE.BoxGeometry(L, 0.03, F)
        for (let n = 0; n <= r.niveles; n++) {
          const m = new THREE.Mesh(entrepano, matEntrepano); m.position.set(0, n * Hn + (n ? -0.015 : 0.06), 0); m.castShadow = true; grupo.add(m)
        }
        const panel = new THREE.Mesh(new THREE.BoxGeometry(L, Ht, 0.025), matPanel); panel.position.set(0, Ht / 2, 0); grupo.add(panel)
      } else if (tipo === 'CANTILEVER') {
        // columnas centrales con brazos a ambos lados
        const colGeo = new THREE.BoxGeometry(0.16, Ht + 0.2, 0.16), baseGeo = new THREE.BoxGeometry(0.16, 0.12, F), brazoGeo = new THREE.BoxGeometry(0.09, 0.07, F)
        for (let i = 0; i <= modulos; i++) {
          const x = -L / 2 + i * anchoMod
          const c = new THREE.Mesh(colGeo, matPoste); c.position.set(x, (Ht + 0.2) / 2, 0); c.castShadow = true; grupo.add(c)
          const b = new THREE.Mesh(baseGeo, matPoste); b.position.set(x, 0.06, 0); grupo.add(b)
          for (let n = 1; n <= r.niveles; n++) {
            const a = new THREE.Mesh(brazoGeo, matNaranja); a.position.set(x, n * Hn - 0.05, 0); a.castShadow = true; grupo.add(a)
          }
        }
      } else {
        // piso: solo la demarcación amarilla de cada posición
        const pts: THREE.Vector3[] = []
        for (let i = 0; i <= r.posiciones; i++) {
          const x = -L / 2 + i * r.frente_m
          pts.push(new THREE.Vector3(x, 0.02, -F / 2), new THREE.Vector3(x, 0.02, F / 2))
        }
        pts.push(new THREE.Vector3(-L / 2, 0.02, -F / 2), new THREE.Vector3(L / 2, 0.02, -F / 2), new THREE.Vector3(-L / 2, 0.02, F / 2), new THREE.Vector3(L / 2, 0.02, F / 2))
        grupo.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), matDemarcacion))
      }
      // celdas: capacidad (caja fantasma) + carga (llena según ocupación)
      const fantasmaMat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.45 })
      for (const c of r.celdas) {
        const cx = -L / 2 + (c.posicion - 0.5) * r.frente_m
        const y0 = (c.nivel - 1) * Hn + (c.nivel > 1 ? 0.02 : 0)
        const anchoC = r.frente_m * 0.88, fondoC = F * 0.86, altoC = Hn * 0.8
        const capacidad = new THREE.Mesh(new THREE.BoxGeometry(anchoC, altoC, fondoC),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.05, depthWrite: false }))
        capacidad.position.set(cx, y0 + 0.14 + altoC / 2, 0)
        capacidad.userData = { rack: r, celda: c }
        grupo.add(capacidad); interactivos.push(capacidad)
        const borde = new THREE.LineSegments(new THREE.EdgesGeometry(capacidad.geometry), fantasmaMat)
        borde.position.copy(capacidad.position); grupo.add(borde)
        const ocupada = !['VACIA', 'SIN_ASIGNAR'].includes(c.estado)
        if (!ocupada) continue
        // La posición ocupada se pinta completa (así el color de la estantería es su % de llenado);
        // la intensidad dice cuánto volumen usa la carga.
        const vol = Math.max(0, Math.min(1, c.ocupacion_pct != null ? c.ocupacion_pct / 100 : 0.5))
        const frac = 0.92
        if (tipo === 'SELECTIVO' || tipo === 'PISO') {
          const estiba = new THREE.Mesh(new THREE.BoxGeometry(anchoC, 0.13, fondoC), matEstiba)
          estiba.position.set(cx, y0 + 0.07, 0); estiba.castShadow = true; grupo.add(estiba)
        }
        const tono = c.resaltar ? BUSCADO : modoColor === 'rack' ? color : SEMAFORO[c.estado] ?? '#10B981'
        const mat = new THREE.MeshStandardMaterial({ color: tono, emissive: tono, emissiveIntensity: c.resaltar ? 0.6 : 0.05 + 0.15 * vol,
          roughness: 0.6, metalness: 0, transparent: true, opacity: 0.75 + 0.25 * vol })
        if (c.resaltar) pulsos.push(mat)
        const carga = new THREE.Mesh(new THREE.BoxGeometry(anchoC * 0.96, altoC * frac, fondoC * 0.96), mat)
        carga.position.set(cx, y0 + 0.14 + (altoC * frac) / 2, 0); carga.castShadow = true
        carga.userData = { rack: r, celda: c }
        grupo.add(carga); interactivos.push(carga)
        // líneas de cajas sobre la carga
        const lineas = new THREE.LineSegments(new THREE.EdgesGeometry(carga.geometry), new THREE.LineBasicMaterial({ color: '#0F172A', transparent: true, opacity: 0.25 }))
        lineas.position.copy(carga.position); grupo.add(lineas)
      }
      const s = etiqueta(r.nombre.replace(/^Estantería\s*/, ''), r.ocupacion_pct, modoColor === 'rack' ? colorRack.get(r.id)! : (r.ocupacion_pct > 90 ? '#EF4444' : r.ocupacion_pct > 70 ? '#F59E0B' : '#10B981'))
      s.position.set(r.x - ancho / 2, Ht + 1.2, r.z - largo / 2); scene.add(s); etiquetas.push(s)
    }

    // ── Controles ──
    const controles = new OrbitControls(camara, renderer.domElement)
    controles.enableDamping = true; controles.dampingFactor = 0.08
    controles.maxPolarAngle = Math.PI * 0.495; controles.minDistance = 1.5; controles.maxDistance = Math.max(ancho, largo) * 2.2
    controles.screenSpacePanning = false
    // Encuadre: la zona donde están las estanterías, no todo el edificio.
    const xs = d.racks.flatMap(r => [r.x - r.largo_m / 2, r.x + r.largo_m / 2]).map(x => x - ancho / 2)
    const zs = d.racks.flatMap(r => [r.z - 1.5, r.z + 1.5]).map(z => z - largo / 2)
    const bx0 = Math.min(...xs), bx1 = Math.max(...xs), bz0 = Math.min(...zs), bz1 = Math.max(...zs)
    const ext3 = Math.max(12, bx1 - bx0, bz1 - bz0)
    const vista = (v: 'iso' | 'aerea' | 'caminar') => {
      const cx = (bx0 + bx1) / 2, cz = (bz0 + bz1) / 2
      if (v === 'iso') { camara.position.set(cx - ext3 * 0.35, ext3 * 0.55, cz + ext3 * 0.85); controles.target.set(cx, 1.5, cz) }
      if (v === 'aerea') { camara.position.set(0, Math.max(ancho, largo) * 1.05, 0.01); controles.target.set(0, 0, 0) }
      if (v === 'caminar') {
        const r0 = d.racks[0]
        const px = r0.x - ancho / 2, pz = r0.z - largo / 2 + r0.fondo_m + 1.6
        camara.position.set(px - r0.largo_m * 0.8, 1.7, pz); controles.target.set(px + 2, 1.6, pz)
      }
      setCaminando(v === 'caminar')
      controles.update()
    }
    const enfocar = (r: Rack) => {
      const px = r.x - ancho / 2, pz = r.z - largo / 2
      controles.target.set(px, r.alto_m / 2, pz)
      camara.position.set(px + r.largo_m * 0.6, r.alto_m * 1.2, pz + r.largo_m * 1.1)
      controles.update()
    }
    ctrl.current = { vista, enfocar }
    vista('iso')

    // caminar con el teclado
    const teclas = new Set<string>()
    const abajo = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return
      const k = e.key.toLowerCase()
      if (['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) { teclas.add(k); e.preventDefault() }
    }
    const arriba = (e: KeyboardEvent) => teclas.delete(e.key.toLowerCase())
    host.tabIndex = 0
    host.addEventListener('keydown', abajo); host.addEventListener('keyup', arriba)

    // pasar el ratón: celda bajo el cursor
    const ray = new THREE.Raycaster(), mouse = new THREE.Vector2()
    let resaltado: THREE.Mesh | null = null
    const mover = (e: PointerEvent) => {
      const b = renderer.domElement.getBoundingClientRect()
      mouse.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1)
      ray.setFromCamera(mouse, camara)
      const hit = ray.intersectObjects(interactivos, false)[0]
      if (resaltado) { (resaltado.material as THREE.MeshBasicMaterial).opacity = resaltado.userData.base ?? (resaltado.material as THREE.MeshBasicMaterial).opacity; resaltado = null }
      if (hit) {
        const m = hit.object as THREE.Mesh
        const mat = m.material as THREE.MeshBasicMaterial
        m.userData.base = mat.opacity; mat.opacity = Math.min(1, mat.opacity + 0.25); resaltado = m
        setHover({ x: e.clientX - b.left, y: e.clientY - b.top, rack: m.userData.rack, celda: m.userData.celda })
        renderer.domElement.style.cursor = 'pointer'
      } else { setHover(null); renderer.domElement.style.cursor = 'grab' }
    }
    const clic = () => { if (resaltado) setSel(resaltado.userData.rack) }
    renderer.domElement.addEventListener('pointermove', mover)
    renderer.domElement.addEventListener('click', clic)

    const ro = new ResizeObserver(() => { camara.aspect = W() / H(); camara.updateProjectionMatrix(); renderer.setSize(W(), H()) })
    ro.observe(host)

    // bucle
    const reloj = new THREE.Clock()
    let vivo = true
    const adelante = new THREE.Vector3(), lado = new THREE.Vector3()
    const ciclo = () => {
      if (!vivo) return
      const dt = Math.min(0.05, reloj.getDelta())
      if (teclas.size) {
        const vel = (caminandoRef.current ? 4 : Math.max(6, camara.position.distanceTo(controles.target) * 0.8)) * dt
        camara.getWorldDirection(adelante); adelante.y = 0; adelante.normalize()
        lado.crossVectors(adelante, camara.up).normalize()
        const paso = new THREE.Vector3()
        if (teclas.has('w') || teclas.has('arrowup')) paso.add(adelante)
        if (teclas.has('s') || teclas.has('arrowdown')) paso.sub(adelante)
        if (teclas.has('d') || teclas.has('arrowright')) paso.add(lado)
        if (teclas.has('a') || teclas.has('arrowleft')) paso.sub(lado)
        if (paso.lengthSq()) { paso.normalize().multiplyScalar(vel); camara.position.add(paso); controles.target.add(paso) }
        if (teclas.has('q') || teclas.has('e')) {
          const ang = (teclas.has('q') ? 1 : -1) * dt * 1.2
          const off = camara.position.clone().sub(controles.target).applyAxisAngle(new THREE.Vector3(0, 1, 0), ang)
          camara.position.copy(controles.target).add(off)
        }
      }
      const t = reloj.elapsedTime
      for (const m of pulsos) m.emissiveIntensity = 0.5 + 0.5 * Math.sin(t * 4)
      const dist = camara.position.distanceTo(controles.target)
      for (const s of etiquetas) { const k = Math.max(0.6, Math.min(2.4, dist / 18)); s.scale.set(3.2 * k, 1.0 * k, 1) }
      controles.update()
      renderer.render(scene, camara)
      requestAnimationFrame(ciclo)
    }
    ciclo()
    return () => {
      vivo = false; ro.disconnect(); controles.dispose()
      host.removeEventListener('keydown', abajo); host.removeEventListener('keyup', arriba)
      scene.traverse(o => {
        const m = o as THREE.Mesh
        m.geometry?.dispose?.()
        const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : []
        mats.forEach((x: any) => { x.map?.dispose?.(); x.dispose?.() })
      })
      renderer.dispose(); renderer.domElement.remove()
      urls.forEach(u => URL.revokeObjectURL(u))
    }
  }, [escena.data, modoColor, colorRack])


  if (escena.isLoading) return <LinearProgress />
  const d = escena.data
  if (!d || !d.racks.length) return <Typography sx={{ p: 3, color: 'text.secondary' }}>Arme la bodega en la pestaña «Constructor» (o calibre una estantería en «Estanterías») para verla en 3D.</Typography>
  const pctTotal = d.resumen.posiciones ? (d.resumen.ocupadas / d.resumen.posiciones) * 100 : 0
  const pantallaCompleta = () => caja.current?.requestFullscreen?.()

  return (
    <Box ref={caja} sx={{ position: 'relative', borderRadius: 3, overflow: 'hidden', border: '1px solid #E2E8F0', bgcolor: '#EEF2F7' }}>
      <Box ref={lienzo} sx={{ width: '100%', height: { xs: 520, md: 720 }, outline: 'none', '&:fullscreen': { height: '100vh' } }} />

      {/* Panel superior izquierdo: resumen */}
      <Box sx={{ position: 'absolute', top: 14, left: 14, p: 1.5, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.94)', border: '1px solid #E2E8F0',
        backdropFilter: 'blur(6px)', boxShadow: '0 4px 16px rgba(15,23,42,0.08)', color: '#0F172A', minWidth: 230 }}>
        <Typography sx={{ fontSize: 10.5, letterSpacing: '0.14em', color: '#64748B', fontWeight: 700 }}>BODEGA VIRTUAL</Typography>
        <Typography sx={{ fontSize: 26, fontWeight: 800, fontFamily: 'Consolas, monospace', color: '#4F46E5' }}>{fmt(pctTotal)}% ocupada</Typography>
        <Typography sx={{ fontSize: 12, color: '#64748B' }}>{d.resumen.ocupadas} de {d.resumen.posiciones} posiciones · {d.resumen.estanterias} estanterías · {fmt(d.resumen.unidades)} und</Typography>
        <Stack gap={0.5} mt={1.2} sx={{ maxHeight: 230, overflowY: 'auto', pr: 0.5 }}>
          {d.racks.map(r => {
            const c = modoColor === 'rack' ? colorRack.get(r.id)! : (r.ocupacion_pct > 90 ? '#EF4444' : r.ocupacion_pct > 70 ? '#F59E0B' : '#10B981')
            return (
              <Stack key={r.id} direction="row" alignItems="center" gap={1} onClick={() => { setSel(r); ctrl.current?.enfocar(r) }}
                sx={{ cursor: 'pointer', px: 0.75, py: 0.4, borderRadius: 1, '&:hover': { bgcolor: 'rgba(100,116,139,0.10)' } }}>
                <Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: c }} />
                <Typography sx={{ fontSize: 12, fontFamily: 'Consolas, monospace', flex: 1, color: '#0F172A' }} noWrap>{r.nombre.replace(/^Estantería\s*/, '')}</Typography>
                <Box sx={{ width: 60, height: 5, borderRadius: 3, bgcolor: 'rgba(148,163,184,0.25)', overflow: 'hidden' }}>
                  <Box sx={{ height: '100%', width: `${Math.min(100, r.ocupacion_pct)}%`, bgcolor: c }} /></Box>
                <Typography sx={{ fontSize: 11, fontFamily: 'Consolas, monospace', color: c, width: 40, textAlign: 'right' }}>{Math.round(r.ocupacion_pct)}%</Typography>
              </Stack>
            )
          })}
        </Stack>
      </Box>

      {/* Barra de vistas */}
      <Stack direction="row" gap={1} sx={{ position: 'absolute', top: 14, right: 14 }} flexWrap="wrap" justifyContent="flex-end">
        <ToggleButtonGroup size="small" exclusive value={modoColor} onChange={(_, v) => v && setModoColor(v)}
          sx={{ bgcolor: 'rgba(255,255,255,0.94)', '& .MuiToggleButton-root': { color: '#64748B', borderColor: '#E2E8F0', textTransform: 'none', fontSize: 12 },
            '& .Mui-selected': { color: '#4F46E5 !important', bgcolor: 'rgba(79,70,229,0.10) !important' } }}>
          <ToggleButton value="rack">Color por estantería</ToggleButton>
          <ToggleButton value="ocupacion">Semáforo de ocupación</ToggleButton>
        </ToggleButtonGroup>
        {[['Isométrica', <ThreeDRotation key="i" />, 'iso'], ['Aérea', <MapaIcon key="a" />, 'aerea'], ['Caminar', <DirectionsWalk key="c" />, 'caminar']].map(([t, ic, v]) => (
          <Button key={v as string} size="small" startIcon={ic as any} onClick={() => { ctrl.current?.vista(v as any); lienzo.current?.focus() }}
            sx={{ bgcolor: 'rgba(255,255,255,0.94)', color: (v === 'caminar' && caminando) ? '#4F46E5' : '#0F172A', border: '1px solid #E2E8F0', textTransform: 'none',
              '&:hover': { bgcolor: 'rgba(79,70,229,0.08)' } }}>{t as string}</Button>
        ))}
        <Button size="small" onClick={pantallaCompleta} sx={{ minWidth: 0, bgcolor: 'rgba(255,255,255,0.94)', color: '#0F172A', border: '1px solid #E2E8F0' }}><Fullscreen fontSize="small" /></Button>
      </Stack>

      {/* Ayuda de navegación */}
      <Typography sx={{ position: 'absolute', bottom: 12, left: 14, fontSize: 11.5, color: '#64748B', bgcolor: 'rgba(255,255,255,0.85)', px: 1, py: 0.4, borderRadius: 1 }}>
        Arrastrar: girar · Clic derecho: desplazar · Rueda: zoom · W A S D / flechas: caminar · Q E: girar · clic en la bodega primero para usar el teclado
      </Typography>

      {/* Estantería seleccionada */}
      {sel && <Box sx={{ position: 'absolute', bottom: 14, right: 14, p: 1.5, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.97)', color: '#0F172A',
        border: `1px solid ${colorRack.get(sel.id)}`, boxShadow: '0 6px 20px rgba(15,23,42,0.12)', minWidth: 260 }}>
        <Stack direction="row" alignItems="center" gap={1}>
          <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: colorRack.get(sel.id) }} />
          <Typography fontWeight={800} sx={{ color: '#0F172A' }}>{sel.nombre}</Typography>
          <Box flex={1} />
          <Typography onClick={() => setSel(null)} sx={{ cursor: 'pointer', color: '#64748B' }}>✕</Typography>
        </Stack>
        <Typography sx={{ fontSize: 12, color: '#64748B', mt: 0.5, fontFamily: 'Consolas, monospace' }}>
          {sel.niveles} niveles × {sel.posiciones} posiciones · {fmt(sel.largo_m)} × {fmt(sel.fondo_m)} × {fmt(sel.alto_m)} m
        </Typography>
        <Stack direction="row" gap={1} mt={1}>
          <Chip size="small" label={`${Math.round(sel.ocupacion_pct)}% ocupada`} sx={{ bgcolor: alpha(colorRack.get(sel.id) ?? '#4F46E5', 0.2), color: '#0F172A' }} />
          <Chip size="small" label={`${sel.ocupadas}/${sel.celdas_total} posiciones`} sx={{ bgcolor: 'rgba(100,116,139,0.10)', color: '#0F172A' }} />
          <Chip size="small" label={`${fmt(sel.unidades)} und`} sx={{ bgcolor: 'rgba(100,116,139,0.10)', color: '#0F172A' }} />
        </Stack>
        <Stack direction="row" gap={1} mt={1.2}>
          <Button size="small" startIcon={<CenterFocusStrong />} onClick={() => ctrl.current?.enfocar(sel)} sx={{ color: '#4F46E5', textTransform: 'none' }}>Acercar</Button>
          {sel.foto_id && <Button size="small" startIcon={<OpenInNew />} onClick={() => onAbrir(sel.foto_id!)} sx={{ color: '#4F46E5', textTransform: 'none' }}>Ver foto</Button>}
          {sel.elemento_id && onEditar && <Button size="small" startIcon={<Edit />} onClick={() => onEditar(sel.elemento_id!)} sx={{ color: '#4F46E5', textTransform: 'none' }}>Editar</Button>}
        </Stack>
      </Box>}

      {/* Celda bajo el cursor */}
      {hover && <Box sx={{ position: 'absolute', left: hover.x + 16, top: hover.y + 12, pointerEvents: 'none', p: 1.2, borderRadius: 1.5, maxWidth: 280,
        bgcolor: 'rgba(255,255,255,0.98)', border: `1px solid ${colorRack.get(hover.rack.id)}`, color: '#0F172A' }}>
        <Typography sx={{ fontFamily: 'Consolas, monospace', fontWeight: 800, color: colorRack.get(hover.rack.id) }}>
          {hover.celda.codigo ?? 'Sin ubicación'} <span style={{ color: '#64748B', fontWeight: 400 }}>· N{hover.celda.nivel} P{hover.celda.posicion}</span>
        </Typography>
        <Typography sx={{ fontSize: 12, color: '#64748B' }}>
          {hover.celda.estado === 'VACIA' ? 'Libre' : hover.celda.estado === 'SIN_ASIGNAR' ? 'Sin ubicación asignada' : `${hover.celda.ocupacion_pct != null ? `${hover.celda.ocupacion_pct}% del volumen · ` : ''}${fmt(hover.celda.unidades)} und`}
        </Typography>
        {hover.celda.contenido.map(x => <Typography key={x.sku} sx={{ fontSize: 12 }} noWrap>{x.nombre} <span style={{ color: '#64748B' }}>× {fmt(x.unidades)}</span></Typography>)}
      </Box>}
    </Box>
  )
}
