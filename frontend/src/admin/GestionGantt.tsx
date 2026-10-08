/**
 * Diagrama de Gantt: jerárquico, con zoom y arrastrable.
 *
 * Dibujado a mano en SVG. Una librería habría traído su propio sistema de
 * estilos, su propia forma de manejar el arrastre y varios cientos de kB, para
 * resolver algo que es una escala de tiempo y unos rectángulos.
 *
 * Cuatro decisiones que gobiernan el archivo:
 *
 *  · **Cada fila lleva dos barras: el plan y lo real.** Con una sola no se puede
 *    ver si el plan se está cumpliendo, que es lo único que un Gantt sirve para
 *    responder.
 *  · **La jerarquía se despliega.** Una épica con doce subtareas ocupa una fila
 *    hasta que a alguien le interesa abrirla; con todo desplegado siempre, el
 *    diagrama deja de caber en la pantalla el primer mes.
 *  · **Las barras se arrastran para reprogramar.** Es lo que hace que el Gantt
 *    sea una herramienta y no un informe: mover una fecha en un formulario y
 *    volver a mirar el diagrama son dos pasos que nadie da.
 *  · **El avance no se inventa.** En una tarea con hijas es la fracción
 *    terminada; en una hoja, todo o nada. Un porcentaje que nadie midió es peor
 *    que no tener porcentaje.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, Box, Button, Chip, IconButton, Skeleton, Stack, Tooltip, Typography,
} from '@mui/material'
import {
  Add, ChevronRight, ExpandMore, Remove, CenterFocusStrong, Link as Cadena,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { gestionApi, mensajeDeError, type BarraGantt, type Proyecto } from './api'
import { aFecha } from '@/utils/fechas'

const ALTO_FILA = 38
const ANCHO_ETIQUETAS = 300
const ALTO_ESCALA = 46

/** Píxeles por día. El zoom es continuo: los saltos fijos obligan a elegir entre
 *  «no cabe» y «no se distingue». */
const PX_MIN = 2
const PX_MAX = 64
const PX_INICIAL = 26

const COLOR_CATEGORIA: Record<string, string> = {
  SIN_CLASIFICAR: PALETA.acero,
  POR_HACER: '#7C6CF5',
  EN_CURSO: COLOR_MODULO,
  TERMINADO: ESTADO.exito,
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
               'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

function aDia(iso?: string | null): Date | null {
  if (!iso) return null
  const d = aFecha(iso)
  return isNaN(d.getTime()) ? null : new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function dias(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86400000)
}

function sumar(d: Date, n: number): Date {
  const r = aFecha(d)
  r.setDate(r.getDate() + n)
  return r
}

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Una fila ya aplanada del árbol, con su profundidad. */
interface Fila {
  barra: BarraGantt
  nivel: number
  tieneHijas: boolean
  abierta: boolean
}

/** Arma el árbol por `padre_id` y lo aplana respetando lo desplegado.
 *
 *  Las que no tienen padre visible cuelgan de la raíz: al filtrar por sprint
 *  puede llegar una subtarea cuya madre quedó fuera, y esconderla porque «falta
 *  su padre» sería perderla sin decirlo. */
function aplanar(barras: BarraGantt[], abiertas: Set<number>): Fila[] {
  const presentes = new Set(barras.map(b => b.id))
  const hijasDe = new Map<number | null, BarraGantt[]>()
  barras.forEach(b => {
    const padre = b.padre_id != null && presentes.has(b.padre_id) ? b.padre_id : null
    if (!hijasDe.has(padre)) hijasDe.set(padre, [])
    hijasDe.get(padre)!.push(b)
  })

  const filas: Fila[] = []
  function recorrer(padre: number | null, nivel: number) {
    const grupo = hijasDe.get(padre) ?? []
    grupo.forEach(b => {
      const hijas = hijasDe.get(b.id) ?? []
      const abierta = abiertas.has(b.id)
      filas.push({ barra: b, nivel, tieneHijas: hijas.length > 0, abierta })
      if (abierta) recorrer(b.id, nivel + 1)
    })
  }
  recorrer(null, 0)
  return filas
}

// ─── La pantalla ──────────────────────────────────────────────────────────────

export default function GestionGantt({
  proyecto, onAbrir,
}: {
  proyecto: Proyecto
  onAbrir: (id: number) => void
}) {
  const qc = useQueryClient()
  const [px, setPx] = useState(PX_INICIAL)
  const [conTerminadas, setConTerminadas] = useState(true)
  const [abiertas, setAbiertas] = useState<Set<number>>(new Set())
  const [resaltada, setResaltada] = useState<number | null>(null)
  const [arrastre, setArrastre] = useState<{
    id: number; modo: 'mover' | 'inicio' | 'fin'; desdeX: number
    inicio: Date; fin: Date; deltaDias: number
  } | null>(null)

  const lienzo = useRef<HTMLDivElement | null>(null)
  const pxRef = useRef(px)
  pxRef.current = px

  const { data, isLoading } = useQuery({
    queryKey: ['gestion', 'gantt', proyecto.id, conTerminadas],
    queryFn: () => gestionApi.gantt(proyecto.id, { incluir_terminadas: conTerminadas }),
  })

  const reprogramar = useMutation({
    mutationFn: ({ id, inicio, fin }: { id: number; inicio: string; fin: string }) =>
      gestionApi.fijarPlan(id, inicio, fin),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gestion', 'gantt', proyecto.id] }),
    onError: (e: any) => {
      toast.error(mensajeDeError(e, 'No se pudo reprogramar'))
      qc.invalidateQueries({ queryKey: ['gestion', 'gantt', proyecto.id] })
    },
  })

  // Al llegar, se abren las que tienen hijas: un diagrama que arranca todo
  // cerrado obliga a hacer clic en cada fila para saber si hay algo dentro.
  useEffect(() => {
    if (!data?.barras.length) return
    setAbiertas(previas => (previas.size ? previas
      : new Set(data.barras.filter(b => b.hijas > 0).map(b => b.id))))
  }, [data])

  const filas = useMemo(
    () => aplanar(data?.barras ?? [], abiertas), [data, abiertas])

  const plano = useMemo(() => {
    if (!data?.barras.length) return null
    const momentos: Date[] = []
    data.barras.forEach(b => {
      ;[b.inicio_plan, b.vence, b.iniciado, b.resuelto].forEach(f => {
        const d = aDia(f)
        if (d) momentos.push(d)
      })
    })
    // Hoy siempre entra: un Gantt donde no se ve el día de hoy no dice si algo
    // va tarde, que es la mitad de para qué se mira.
    const ahora = new Date()
    momentos.push(new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate()))

    const min = sumar(new Date(Math.min(...momentos.map(d => d.getTime()))), -3)
    const max = sumar(new Date(Math.max(...momentos.map(d => d.getTime()))), 4)
    return { min, max, total: Math.max(dias(min, max), 1) }
  }, [data])

  // ── Zoom con la rueda ──
  //
  // El listener va nativo y NO pasivo: React los registra como pasivos y ahí
  // `preventDefault()` no hace nada, con lo que la página entera se desplaza en
  // vez de acercarse el diagrama.
  const acercarEn = useCallback((factor: number, xRaton: number) => {
    const caja = lienzo.current
    if (!caja) return
    const anterior = pxRef.current
    const siguiente = Math.min(PX_MAX, Math.max(PX_MIN, anterior * factor))
    if (siguiente === anterior) return
    // El día bajo el cursor se queda donde está: si no, acercarse desplaza el
    // diagrama y hay que volver a buscar dónde se estaba mirando.
    const diaBajoElRaton = (caja.scrollLeft + xRaton) / anterior
    setPx(siguiente)
    requestAnimationFrame(() => {
      if (lienzo.current) {
        lienzo.current.scrollLeft = diaBajoElRaton * siguiente - xRaton
      }
    })
  }, [])

  useEffect(() => {
    const caja = lienzo.current
    if (!caja) return
    function alRodar(e: WheelEvent) {
      if (!e.ctrlKey && !e.metaKey) return
      e.preventDefault()
      const r = caja!.getBoundingClientRect()
      acercarEn(Math.exp(-e.deltaY * 0.002), e.clientX - r.left)
    }
    caja.addEventListener('wheel', alRodar, { passive: false })
    return () => caja.removeEventListener('wheel', alRodar)
  }, [acercarEn, filas.length])

  // ── Arrastrar para reprogramar ──
  useEffect(() => {
    if (!arrastre) return
    function alMover(e: PointerEvent) {
      const corridos = Math.round((e.clientX - arrastre!.desdeX) / pxRef.current)
      if (corridos !== arrastre!.deltaDias) {
        setArrastre({ ...arrastre!, deltaDias: corridos })
      }
    }
    function alSoltar() {
      const { id, modo, inicio, fin, deltaDias } = arrastre!
      setArrastre(null)
      if (!deltaDias) return
      const nuevoInicio = modo === 'fin' ? inicio : sumar(inicio, deltaDias)
      const nuevoFin = modo === 'inicio' ? fin : sumar(fin, deltaDias)
      if (nuevoFin < nuevoInicio) {
        toast.error('El fin no puede quedar antes del inicio.')
        return
      }
      reprogramar.mutate({ id, inicio: iso(nuevoInicio), fin: iso(nuevoFin) })
    }
    document.addEventListener('pointermove', alMover)
    document.addEventListener('pointerup', alSoltar, { once: true })
    return () => {
      document.removeEventListener('pointermove', alMover)
      document.removeEventListener('pointerup', alSoltar)
    }
  }, [arrastre, reprogramar])

  // Al abrir, centrado en hoy: lo pasado suele estar cerrado y lo interesante
  // empieza donde está el cursor rojo.
  const centrado = useRef(false)
  useLayoutEffect(() => {
    if (centrado.current || !plano || !lienzo.current) return
    const hoy = new Date()
    const x = dias(plano.min, new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())) * px
    lienzo.current.scrollLeft = Math.max(0, x - lienzo.current.clientWidth * 0.35)
    centrado.current = true
  }, [plano, px])

  if (isLoading) return <Skeleton variant="rounded" height={380} />

  if (!data?.barras.length) {
    return (
      <Box>
        <Alert severity="info" sx={{ mb: 2 }}>
          Todavía no hay ninguna incidencia con fechas. Póngale fecha de inicio y
          de vencimiento a alguna —desde su detalle— y aparecerá acá.
        </Alert>
        {!!data?.sin_fechas.length && <SinFechas filas={data.sin_fechas} onAbrir={onAbrir} />}
      </Box>
    )
  }

  const { min, total } = plano!
  const ancho = total * px
  const alto = filas.length * ALTO_FILA
  const hoy = new Date()
  const xHoy = dias(min, new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())) * px

  const posicion = new Map(filas.map((f, i) => [f.barra.id, i]))

  /** El tramo de una barra, con el desplazamiento del arrastre en curso. */
  function tramo(b: BarraGantt, cual: 'plan' | 'real') {
    const desde = cual === 'plan' ? b.inicio_plan : b.iniciado
    const hasta = cual === 'plan' ? b.vence
      : (b.resuelto ?? (b.iniciado ? new Date().toISOString() : null))
    let a = aDia(desde)
    let z = aDia(hasta)
    if (!a && !z) return null
    a = a ?? z!
    z = z ?? a!

    if (cual === 'plan' && arrastre?.id === b.id && arrastre.deltaDias) {
      if (arrastre.modo !== 'fin') a = sumar(a, arrastre.deltaDias)
      if (arrastre.modo !== 'inicio') z = sumar(z, arrastre.deltaDias)
    }

    const x = dias(min, a) * px
    // Con una sola fecha se dibuja un día: una barra invisible es
    // indistinguible de no tener fechas.
    const w = Math.max((dias(a, z) + 1) * px, Math.max(px * 0.9, 6))
    return { x, w, hito: dias(a, z) === 0 }
  }

  // Las marcas de la escala se eligen según el zoom: con 3 px por día no caben
  // los números, y con 40 sobra sitio para el día de la semana.
  const marcas: { x: number; texto: string; sub?: string; fuerte: boolean }[] = []
  const paso = px >= 22 ? 1 : px >= 9 ? 7 : 30
  for (let i = 0; i <= total; i++) {
    const d = sumar(min, i)
    const esLunes = d.getDay() === 1
    const esPrimero = d.getDate() === 1
    if (paso === 1) {
      marcas.push({
        x: i * px, texto: String(d.getDate()),
        sub: px >= 34 ? ['do', 'lu', 'ma', 'mi', 'ju', 'vi', 'sá'][d.getDay()] : undefined,
        fuerte: esPrimero,
      })
    } else if (paso === 7 && esLunes) {
      marcas.push({ x: i * px, texto: `${d.getDate()} ${MESES[d.getMonth()]}`, fuerte: esPrimero })
    } else if (paso === 30 && esPrimero) {
      marcas.push({ x: i * px, texto: `${MESES[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`, fuerte: true })
    }
  }

  // Los meses, en una banda propia: con el zoom fino, los números de día solos
  // no dicen de qué mes se está hablando.
  const bandaMeses: { x: number; ancho: number; texto: string }[] = []
  for (let i = 0; i <= total; i++) {
    const d = sumar(min, i)
    if (i === 0 || d.getDate() === 1) {
      const finMes = new Date(d.getFullYear(), d.getMonth() + 1, 0)
      const hasta = Math.min(dias(min, finMes) + 1, total)
      bandaMeses.push({
        x: i * px, ancho: Math.max((hasta - i) * px, 0),
        texto: `${MESES[d.getMonth()]} ${d.getFullYear()}`,
      })
    }
  }

  // Lo que hay que resaltar: la fila señalada y todo lo que la frena o depende
  // de ella. Es la respuesta a «¿por qué esto no avanza?».
  const cadena = new Set<number>()
  if (resaltada != null) {
    cadena.add(resaltada)
    const b = data.barras.find(x => x.id === resaltada)
    b?.bloquea_a.forEach(x => cadena.add(x))
    b?.depende_de.forEach(x => cadena.add(x))
  }

  return (
    <Box>
      {/* ── Barra de herramientas ── */}
      <Stack direction="row" alignItems="center" spacing={1} mb={1.5} flexWrap="wrap" useFlexGap>
        <Stack direction="row" alignItems="center" spacing={0.25}
          sx={{ border: `1px solid ${PALETA.niebla}`, borderRadius: 1.5, px: 0.25 }}>
          <Tooltip title="Alejar">
            <IconButton size="small" onClick={() => acercarEn(0.7, (lienzo.current?.clientWidth ?? 0) / 2)}>
              <Remove sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
          <Typography variant="caption" sx={{
            width: 62, textAlign: 'center', color: PALETA.acero, fontSize: 10.5,
          }}>
            {px >= 22 ? 'días' : px >= 9 ? 'semanas' : 'meses'}
          </Typography>
          <Tooltip title="Acercar">
            <IconButton size="small" onClick={() => acercarEn(1.4, (lienzo.current?.clientWidth ?? 0) / 2)}>
              <Add sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Stack>

        <Tooltip title="Volver a hoy">
          <IconButton size="small" onClick={() => {
            if (!lienzo.current) return
            lienzo.current.scrollLeft = Math.max(0, xHoy - lienzo.current.clientWidth * 0.35)
          }}>
            <CenterFocusStrong sx={{ fontSize: 17 }} />
          </IconButton>
        </Tooltip>

        <Button size="small" sx={{ textTransform: 'none' }}
          onClick={() => setAbiertas(
            abiertas.size ? new Set() : new Set(data.barras.filter(b => b.hijas > 0).map(b => b.id)))}>
          {abiertas.size ? 'Contraer todo' : 'Desplegar todo'}
        </Button>

        <Button size="small" onClick={() => setConTerminadas(!conTerminadas)}
          sx={{ textTransform: 'none' }}>
          {conTerminadas ? 'Ocultar terminadas' : 'Mostrar terminadas'}
        </Button>

        <Box sx={{ flex: 1 }} />

        <Typography variant="caption" sx={{ color: PALETA.acero, fontSize: 10.5 }}>
          Ctrl + rueda para acercar · arrastre una barra para reprogramar
        </Typography>
      </Stack>

      <Box sx={{
        display: 'flex', border: `1px solid ${PALETA.niebla}`, borderRadius: 2,
        overflow: 'hidden', bgcolor: PALETA.lienzo,
      }}>
        {/* ── Columna fija: la jerarquía ── */}
        <Box sx={{ width: ANCHO_ETIQUETAS, flexShrink: 0, borderRight: `1px solid ${PALETA.niebla}` }}>
          <Box sx={{
            height: ALTO_ESCALA, borderBottom: `1px solid ${PALETA.niebla}`,
            bgcolor: PALETA.bruma, display: 'flex', alignItems: 'flex-end', px: 1.5, pb: 0.75,
          }}>
            <Typography variant="caption" sx={{
              fontWeight: 800, fontSize: 9.5, letterSpacing: '0.08em', color: PALETA.acero,
            }}>
              {filas.length} DE {data.barras.length}
            </Typography>
          </Box>

          {filas.map(f => {
            const color = COLOR_CATEGORIA[f.barra.categoria ?? ''] ?? PALETA.acero
            const enCadena = cadena.size > 0 && cadena.has(f.barra.id)
            return (
              <Stack
                key={f.barra.id} direction="row" alignItems="center" spacing={0.5}
                onMouseEnter={() => setResaltada(f.barra.id)}
                onMouseLeave={() => setResaltada(null)}
                sx={{
                  height: ALTO_FILA, px: 1, borderBottom: `1px solid ${PALETA.bruma}`,
                  pl: 1 + f.nivel * 1.75,
                  bgcolor: enCadena ? `${COLOR_MODULO}0F` : 'transparent',
                  opacity: cadena.size > 0 && !enCadena ? 0.45 : 1,
                  transition: 'background-color .12s, opacity .12s',
                }}
              >
                {f.tieneHijas ? (
                  <IconButton size="small" sx={{ p: 0.15 }}
                    onClick={() => setAbiertas(previas => {
                      const s = new Set(previas)
                      s.has(f.barra.id) ? s.delete(f.barra.id) : s.add(f.barra.id)
                      return s
                    })}>
                    {f.abierta
                      ? <ExpandMore sx={{ fontSize: 15 }} />
                      : <ChevronRight sx={{ fontSize: 15 }} />}
                  </IconButton>
                ) : (
                  <Box sx={{ width: 19, flexShrink: 0 }} />
                )}

                <Box sx={{
                  width: 4, height: 18, borderRadius: 1, bgcolor: color, flexShrink: 0,
                }} />

                <Box sx={{ minWidth: 0, flex: 1, cursor: 'pointer' }}
                  onClick={() => onAbrir(f.barra.id)}>
                  <Typography variant="caption" noWrap sx={{
                    display: 'block', fontSize: 12,
                    fontWeight: f.nivel === 0 && f.tieneHijas ? 700 : 500,
                  }}>
                    {f.barra.icono ? `${f.barra.icono} ` : ''}{f.barra.resumen}
                  </Typography>
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <Typography variant="caption" sx={{
                      fontFamily: 'monospace', fontSize: 9.5, color: PALETA.acero,
                    }}>
                      {f.barra.clave}
                    </Typography>
                    {f.barra.asignado && (
                      <Typography variant="caption" noWrap
                        sx={{ fontSize: 9.5, color: PALETA.acero }}>
                        · {f.barra.asignado}
                      </Typography>
                    )}
                    {!!f.barra.depende_de.length && (
                      <Tooltip title={`Depende de ${f.barra.depende_de.length} incidencia(s)`}>
                        <Cadena sx={{ fontSize: 11, color: ESTADO.alerta }} />
                      </Tooltip>
                    )}
                  </Stack>
                </Box>
              </Stack>
            )
          })}
        </Box>

        {/* ── El lienzo ── */}
        <Box ref={lienzo} sx={{ flex: 1, overflowX: 'auto' }}>
          <Box sx={{ width: ancho, minWidth: '100%' }}>
            {/* Escala */}
            <Box sx={{
              height: ALTO_ESCALA, position: 'relative',
              borderBottom: `1px solid ${PALETA.niebla}`, bgcolor: PALETA.bruma,
            }}>
              {bandaMeses.map((m, i) => (
                <Box key={i} sx={{
                  position: 'absolute', left: m.x, top: 4, width: m.ancho,
                  borderLeft: i ? `1px solid ${PALETA.niebla}` : 'none', pl: 0.75,
                }}>
                  <Typography variant="caption" noWrap sx={{
                    fontSize: 10, fontWeight: 800, color: PALETA.grafito,
                    letterSpacing: '0.04em',
                  }}>
                    {m.ancho > 48 ? m.texto.toUpperCase() : ''}
                  </Typography>
                </Box>
              ))}
              {marcas.map((m, i) => (
                <Box key={i} sx={{ position: 'absolute', left: m.x, top: 22, width: px }}>
                  <Typography variant="caption" sx={{
                    display: 'block', fontSize: 9.5, textAlign: paso === 1 ? 'center' : 'left',
                    pl: paso === 1 ? 0 : 0.5,
                    color: m.fuerte ? PALETA.tinta : PALETA.acero,
                    fontWeight: m.fuerte ? 700 : 400, whiteSpace: 'nowrap',
                  }}>
                    {m.texto}
                  </Typography>
                  {m.sub && (
                    <Typography variant="caption" sx={{
                      display: 'block', fontSize: 8, textAlign: 'center', color: PALETA.acero,
                    }}>
                      {m.sub}
                    </Typography>
                  )}
                </Box>
              ))}
            </Box>

            <svg width={ancho} height={alto} style={{ display: 'block' }}>
              <defs>
                <marker id="punta" markerWidth="7" markerHeight="7" refX="6" refY="3.5"
                  orient="auto">
                  <path d="M0,0 L7,3.5 L0,7 Z" fill={ESTADO.alerta} />
                </marker>
                <linearGradient id="progreso" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.28" />
                  <stop offset="100%" stopColor="#000000" stopOpacity="0.08" />
                </linearGradient>
              </defs>

              {/* Fines de semana, en su propia banda: el trabajo no avanza ahí y
                  verlo explica por qué una barra de cinco días cubre una semana. */}
              {px >= 8 && Array.from({ length: total }, (_, i) => {
                const d = sumar(min, i)
                if (d.getDay() !== 0 && d.getDay() !== 6) return null
                return (
                  <rect key={`f${i}`} x={i * px} y={0} width={px} height={alto}
                    fill={PALETA.bruma} />
                )
              })}

              {/* Rejilla */}
              {marcas.map((m, i) => (
                <line key={`g${i}`} x1={m.x} y1={0} x2={m.x} y2={alto}
                  stroke={m.fuerte ? PALETA.niebla : PALETA.bruma} strokeWidth={1} />
              ))}
              {filas.map((_, i) => (
                <line key={`h${i}`} x1={0} y1={(i + 1) * ALTO_FILA}
                  x2={ancho} y2={(i + 1) * ALTO_FILA}
                  stroke={PALETA.bruma} strokeWidth={1} />
              ))}

              {/* Flechas de precedencia. Debajo de las barras para no taparlas. */}
              {filas.map((f, i) => f.barra.bloquea_a.map(destino => {
                const j = posicion.get(destino)
                if (j === undefined) return null
                const desde = tramo(f.barra, 'plan') ?? tramo(f.barra, 'real')
                const hasta = tramo(filas[j].barra, 'plan') ?? tramo(filas[j].barra, 'real')
                if (!desde || !hasta) return null
                const x1 = desde.x + desde.w
                const y1 = i * ALTO_FILA + ALTO_FILA / 2
                const x2 = hasta.x
                const y2 = j * ALTO_FILA + ALTO_FILA / 2
                const medio = x1 + Math.max((x2 - x1) / 2, 10)
                const viva = cadena.size === 0
                  || (cadena.has(f.barra.id) && cadena.has(destino))
                return (
                  <path
                    key={`v${f.barra.id}-${destino}`}
                    d={`M ${x1} ${y1} H ${medio} V ${y2} H ${x2}`}
                    fill="none" stroke={ESTADO.alerta}
                    strokeWidth={viva ? 1.5 : 1}
                    strokeOpacity={viva ? 0.9 : 0.18}
                    strokeDasharray="4 3" markerEnd="url(#punta)"
                  />
                )
              }))}

              {/* Las barras */}
              {filas.map((f, i) => {
                const b = f.barra
                const y = i * ALTO_FILA
                const plan = tramo(b, 'plan')
                const real = tramo(b, 'real')
                const color = COLOR_CATEGORIA[b.categoria ?? ''] ?? PALETA.acero
                const enCadena = cadena.size === 0 || cadena.has(b.id)
                const vencida = b.vence && !b.resuelto &&
                  aDia(b.vence)! < new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())
                const arrastrando = arrastre?.id === b.id

                return (
                  <g key={b.id} opacity={enCadena ? 1 : 0.28}
                    onMouseEnter={() => setResaltada(b.id)}
                    onMouseLeave={() => setResaltada(null)}>

                    {plan && plan.hito ? (
                      // Un hito: empieza y termina el mismo día. Un rectángulo de
                      // un día se confunde con una tarea corta; el rombo no.
                      <g
                        style={{ cursor: 'grab' }}
                        onPointerDown={e => {
                          e.preventDefault()
                          setArrastre({
                            id: b.id, modo: 'mover', desdeX: e.clientX,
                            inicio: aDia(b.inicio_plan)!, fin: aDia(b.vence)!,
                            deltaDias: 0,
                          })
                        }}
                        onClick={() => !arrastre && onAbrir(b.id)}
                      >
                        <rect x={plan.x - 1} y={y + 6} width={plan.w + 2}
                          height={ALTO_FILA - 12} fill="transparent" />
                        <path
                          d={`M ${plan.x + plan.w / 2} ${y + 8}
                              L ${plan.x + plan.w / 2 + 9} ${y + ALTO_FILA / 2}
                              L ${plan.x + plan.w / 2} ${y + ALTO_FILA - 8}
                              L ${plan.x + plan.w / 2 - 9} ${y + ALTO_FILA / 2} Z`}
                          fill={vencida ? ESTADO.peligro : color}
                          stroke={PALETA.lienzo} strokeWidth={1.5}
                        />
                      </g>
                    ) : plan ? (
                      <g style={{ cursor: arrastrando ? 'grabbing' : 'grab' }}>
                        {/* El plan */}
                        <rect
                          x={plan.x} y={y + 8} width={plan.w} height={ALTO_FILA - 16}
                          rx={4}
                          fill={`${color}22`}
                          stroke={vencida ? ESTADO.peligro : `${color}88`}
                          strokeWidth={vencida ? 1.5 : 1}
                          strokeDasharray={vencida ? '4 2' : undefined}
                          onPointerDown={e => {
                            e.preventDefault()
                            setArrastre({
                              id: b.id, modo: 'mover', desdeX: e.clientX,
                              inicio: aDia(b.inicio_plan) ?? aDia(b.vence)!,
                              fin: aDia(b.vence) ?? aDia(b.inicio_plan)!,
                              deltaDias: 0,
                            })
                          }}
                          onClick={() => !arrastre?.deltaDias && onAbrir(b.id)}
                        />

                        {/* El avance, dentro del plan */}
                        {b.avance > 0 && (
                          <>
                            <rect
                              x={plan.x} y={y + 8} width={plan.w * b.avance}
                              height={ALTO_FILA - 16} rx={4} fill={color}
                              pointerEvents="none"
                            />
                            <rect
                              x={plan.x} y={y + 8} width={plan.w * b.avance}
                              height={ALTO_FILA - 16} rx={4} fill="url(#progreso)"
                              pointerEvents="none"
                            />
                          </>
                        )}

                        {/* Los tiradores de los extremos */}
                        {plan.w > 16 && (['inicio', 'fin'] as const).map(cual => (
                          <rect
                            key={cual}
                            x={cual === 'inicio' ? plan.x : plan.x + plan.w - 6}
                            y={y + 8} width={6} height={ALTO_FILA - 16}
                            fill="transparent" style={{ cursor: 'ew-resize' }}
                            onPointerDown={e => {
                              e.preventDefault()
                              e.stopPropagation()
                              setArrastre({
                                id: b.id, modo: cual, desdeX: e.clientX,
                                inicio: aDia(b.inicio_plan) ?? aDia(b.vence)!,
                                fin: aDia(b.vence) ?? aDia(b.inicio_plan)!,
                                deltaDias: 0,
                              })
                            }}
                          />
                        ))}
                      </g>
                    ) : null}

                    {/* Lo real, más delgado y encima: así se comparan de un
                        vistazo sin que una tape a la otra. */}
                    {real && !plan?.hito && (
                      <rect x={real.x} y={y + ALTO_FILA - 11} width={real.w} height={4}
                        rx={2} fill={color} pointerEvents="none" />
                    )}

                    {/* El nombre, a la derecha de la barra cuando cabe */}
                    {plan && px >= 10 && (
                      <text
                        x={plan.x + plan.w + 7} y={y + ALTO_FILA / 2 + 3.5}
                        fontSize={10.5} fill={PALETA.acero} pointerEvents="none"
                      >
                        {b.puntos != null ? `${b.puntos} pt` : ''}
                        {b.avance > 0 && b.avance < 1 ? `  ${Math.round(b.avance * 100)}%` : ''}
                      </text>
                    )}

                    <title>
                      {`${b.clave} · ${b.resumen}\n`}
                      {`Estado: ${b.estado ?? '—'}  ·  Responsable: ${b.asignado ?? 'sin asignar'}\n`}
                      {b.inicio_plan || b.vence
                        ? `Plan: ${(b.inicio_plan ?? '').slice(0, 10)} → ${(b.vence ?? '').slice(0, 10)}\n`
                        : 'Sin plan\n'}
                      {b.iniciado
                        ? `Real: ${b.iniciado.slice(0, 10)} → ${(b.resuelto ?? 'en curso').slice(0, 10)}\n`
                        : 'Todavía no ha empezado\n'}
                      {b.hijas ? `${Math.round(b.avance * 100)}% de ${b.hijas} subtareas\n` : ''}
                      {b.depende_de.length ? `Depende de ${b.depende_de.length}\n` : ''}
                      {arrastrando ? '' : 'Arrastre para reprogramar'}
                    </title>
                  </g>
                )
              })}

              {/* Hoy, encima de todo */}
              <line x1={xHoy} y1={0} x2={xHoy} y2={alto}
                stroke={ESTADO.peligro} strokeWidth={1.5} />
            </svg>
          </Box>
        </Box>
      </Box>

      {/* ── Leyenda ── */}
      <Stack direction="row" spacing={2} mt={1.25} flexWrap="wrap" useFlexGap
        alignItems="center">
        {Object.entries(COLOR_CATEGORIA).map(([clave, color]) => (
          <Leyenda key={clave} color={color} texto={
            { SIN_CLASIFICAR: 'Sin clasificar', POR_HACER: 'Por hacer',
              EN_CURSO: 'En curso', TERMINADO: 'Hecho' }[clave] ?? clave} />
        ))}
        <Box sx={{ width: 1, height: 14, bgcolor: PALETA.niebla }} />
        <Leyenda color={ESTADO.peligro} texto="Vencida / hoy" />
        <Leyenda color={ESTADO.alerta} texto="Precedencia" />
        {arrastre && (
          <Chip size="small" label={
            arrastre.deltaDias
              ? `${arrastre.deltaDias > 0 ? '+' : ''}${arrastre.deltaDias} días`
              : 'arrastre para mover'
          } sx={{ height: 20, fontSize: 10.5, bgcolor: `${COLOR_MODULO}22`, color: COLOR_MODULO }} />
        )}
      </Stack>

      {!!data.sin_fechas.length && (
        <Box sx={{ mt: 2 }}>
          <SinFechas filas={data.sin_fechas} onAbrir={onAbrir} />
        </Box>
      )}
    </Box>
  )
}

function Leyenda({ color, texto }: { color: string; texto: string }) {
  return (
    <Stack direction="row" spacing={0.6} alignItems="center">
      <Box sx={{ width: 12, height: 9, bgcolor: color, borderRadius: 0.5 }} />
      <Typography variant="caption" sx={{ color: PALETA.acero, fontSize: 10.5 }}>
        {texto}
      </Typography>
    </Stack>
  )
}

/** Las que no tienen ninguna fecha.
 *
 *  Se listan y no se esconden: desaparecer de la pantalla se lee como que se
 *  perdieron, y lo que hace falta es justo lo contrario —verlas para poder
 *  ponerles fecha—. */
function SinFechas({ filas, onAbrir }: { filas: any[]; onAbrir: (id: number) => void }) {
  return (
    <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: PALETA.bruma }}>
      <Typography variant="caption" sx={{ fontWeight: 800, color: PALETA.acero }}>
        SIN FECHAS ({filas.length}) — no salen en el diagrama hasta que se les ponga plan
      </Typography>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap mt={1}>
        {filas.map(t => (
          <Chip
            key={t.id} size="small" label={`${t.clave} ${t.resumen}`}
            onClick={() => onAbrir(t.id)}
            sx={{ height: 22, fontSize: 11, maxWidth: 320 }}
          />
        ))}
      </Stack>
    </Box>
  )
}
