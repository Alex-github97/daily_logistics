/**
 * Armado de un envío (traslado entre bodegas), con tres formas de registrar:
 *
 *   - Selección manual: lista del stock disponible en el origen, con botones
 *     y campo de cantidad.
 *   - Escáner: código de barras de la unidad, la caja o el máster.
 *   - Radiofrecuencia (RFID): cada etiqueta distinta cuenta una sola vez.
 *
 * «Contar en» permite registrar en cajas, másters o estibas en vez de
 * unidades: se escribe «2 cajas» y por dentro se guardan 24 unidades. Los
 * productos que no tienen ese empaque se siguen contando en unidades.
 *
 * Las tres formas alimentan la misma lista por producto. Quien la usa decide
 * después de qué ubicaciones sale cada producto (FEFO).
 */
import { useMemo, useState } from 'react'
import {
  Alert, Box, Button, Chip, IconButton, InputAdornment, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography, alpha,
} from '@mui/material'
import { Add, Remove, DoneAll, DeleteOutline, Search, TouchApp, QrCodeScanner, Sensors } from '@mui/icons-material'
import { TextField } from '@/components/comun/Desplegables'
import { CampoEscaner, agregarLectura, textoDesglose, type ItemEscaneado, type Lectura } from '@/components/wms/Escaner'
import { useLectorGlobal } from '@/components/comun/LectorGlobal'
import { PanelRFID } from '@/components/wms/ArticulosRecepcion'
import { NOMBRE_CONTAR, equivalencia, factor, plural, useNiveles, type Contar } from '@/components/wms/empaques'
import { COLOR_MODULO } from '@/config/marca'

export interface StockOrigen {
  producto_id: number
  cantidad_disponible: number
  producto?: { sku: string; nombre: string }
}

const num = (n: number) => n.toLocaleString('es-CO', { maximumFractionDigits: 2 })
const mayus = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)

/** Cambia la cantidad (en unidades) de un producto en la lista; la crea o la quita si queda en 0. */
function fijar(items: ItemEscaneado[], p: { producto_id: number; sku: string; nombre: string }, cantidad: number,
               motivo = 'Manual'): ItemEscaneado[] {
  const c = Math.max(0, cantidad)
  const i = items.findIndex(x => x.producto_id === p.producto_id)
  if (c === 0) return items.filter(x => x.producto_id !== p.producto_id)
  if (i < 0) return [...items, { ...p, cantidad: c, desglose: { [motivo]: 1 } }]
  return items.map((x, j) => (j === i ? { ...x, cantidad: c, desglose: { ...x.desglose, [motivo]: 1 } } : x))
}

export function ArmadoEnvio({ stock, items, onCambio, cargando, sinOrigen, titulo = 'Qué se envía', avisoSinOrigen = 'Elija primero el almacén de origen.' }: {
  /** Existencias disponibles del almacén de origen (pueden venir varias filas por producto). */
  stock: StockOrigen[]
  items: ItemEscaneado[]
  onCambio: (items: ItemEscaneado[]) => void
  cargando?: boolean
  sinOrigen?: boolean
  titulo?: string
  avisoSinOrigen?: string
}) {
  const [modo, setModo] = useState<'MANUAL' | 'ESCANER' | 'RFID'>('MANUAL')
  // Una lectura del lector en modo manual pasa sola a modo escáner y se procesa.
  const [lecturaPendiente, setLecturaPendiente] = useState<string | null>(null)
  useLectorGlobal(c => { setLecturaPendiente(c); setModo('ESCANER') }, modo !== 'ESCANER')
  const [contar, setContar] = useState<Contar>('UNIDAD')
  const [buscar, setBuscar] = useState('')
  const niveles = useNiveles()

  // Disponible por producto en el origen.
  const disponibles = useMemo(() => {
    const m = new Map<number, { producto_id: number; sku: string; nombre: string; disponible: number }>()
    for (const e of stock) {
      if (!(e.cantidad_disponible > 0)) continue
      const x = m.get(e.producto_id) ?? { producto_id: e.producto_id, sku: e.producto?.sku ?? '', nombre: e.producto?.nombre ?? `#${e.producto_id}`, disponible: 0 }
      x.disponible += e.cantidad_disponible
      m.set(e.producto_id, x)
    }
    return Array.from(m.values()).sort((a, b) => a.nombre.localeCompare(b.nombre))
  }, [stock])
  const dispDe = (pid: number) => disponibles.find(d => d.producto_id === pid)?.disponible ?? 0
  const cantDe = (pid: number) => items.find(x => x.producto_id === pid)?.cantidad ?? 0

  /** En qué se cuenta este producto: el empaque elegido, o unidades si no lo tiene. */
  const unidadDe = (pid: number): { c: Contar; f: number } => {
    const f = factor(niveles.get(pid), contar)
    return f > 0 ? { c: contar, f } : { c: 'UNIDAD', f: 1 }
  }
  // Los empaques que existen: en los productos del origen o, si aún no hay origen,
  // en cualquier producto del maestro (para no ofrecer los que nadie tiene).
  const hayNivel = (c: Contar) => c === 'UNIDAD' || (disponibles.length
    ? disponibles.some(d => factor(niveles.get(d.producto_id), c) > 0)
    : Array.from(niveles.values()).some(n => factor(n, c) > 0))

  const filtrados = disponibles.filter(d => {
    const t = buscar.trim().toLowerCase()
    return !t || d.nombre.toLowerCase().includes(t) || d.sku.toLowerCase().includes(t)
  })
  const leido = (l: Lectura) => onCambio(agregarLectura(items, l))
  const total = items.reduce((s, x) => s + x.cantidad, 0)
  const excedidos = items.filter(x => x.cantidad > dispDe(x.producto_id))

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} gap={1.5} mb={1.5}>
        <Typography fontWeight={700}>{titulo}</Typography>
        <ToggleButtonGroup size="small" exclusive value={modo} onChange={(_, v) => v && setModo(v)}>
          <ToggleButton value="MANUAL" sx={{ textTransform: 'none', gap: 0.6 }}><TouchApp fontSize="small" /> Selección manual</ToggleButton>
          <ToggleButton value="ESCANER" sx={{ textTransform: 'none', gap: 0.6 }}><QrCodeScanner fontSize="small" /> Escáner</ToggleButton>
          <ToggleButton value="RFID" sx={{ textTransform: 'none', gap: 0.6 }}><Sensors fontSize="small" /> Radiofrecuencia</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Stack direction="row" alignItems="center" gap={1.5} mb={1.5} flexWrap="wrap">
        <Typography sx={{ fontSize: 13, fontWeight: 600 }}>Contar en:</Typography>
        <ToggleButtonGroup size="small" exclusive value={contar} onChange={(_, v) => v && setContar(v)}>
          {(['UNIDAD', 'CAJA', 'MASTER', 'ESTIBA'] as Contar[]).map(c => (
            <ToggleButton key={c} value={c} disabled={!hayNivel(c)} sx={{ textTransform: 'none', px: 1.5 }}>
              {mayus(NOMBRE_CONTAR[c][1])}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        {contar !== 'UNIDAD' && (
          <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
            Los botones y cantidades van en {NOMBRE_CONTAR[contar][1]}; los productos sin ese empaque se cuentan en unidades.
          </Typography>
        )}
      </Stack>

      {sinOrigen && <Alert severity="info" sx={{ mb: 1.5 }}>{avisoSinOrigen}</Alert>}

      {modo === 'MANUAL' && !sinOrigen && (
        <Box sx={{ mb: 1.5 }}>
          <TextField size="small" fullWidth placeholder="Buscar producto disponible en el origen" value={buscar}
            onChange={e => setBuscar(e.target.value)}
            InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
          <Box sx={{ mt: 1, maxHeight: 300, overflowY: 'auto', border: '1px solid #E2E8F0', borderRadius: 2 }}>
            {cargando ? (
              <Typography sx={{ p: 2, fontSize: 13 }}>Cargando existencias…</Typography>
            ) : filtrados.length === 0 ? (
              <Typography sx={{ p: 2, fontSize: 13, color: 'text.secondary' }}>
                {disponibles.length ? 'Ningún producto coincide.' : 'El almacén de origen no tiene existencias disponibles.'}
              </Typography>
            ) : filtrados.map((d, i) => {
              const c = cantDe(d.producto_id)
              const { c: en, f } = unidadDe(d.producto_id)
              const completos = Math.floor(d.disponible / f) * f          // solo empaques completos
              const p = { producto_id: d.producto_id, sku: d.sku, nombre: d.nombre }
              const eqDisp = equivalencia(d.disponible, niveles.get(d.producto_id))
              return (
                <Stack key={d.producto_id} data-producto={d.sku} direction={{ xs: 'column', md: 'row' }} gap={1} alignItems={{ md: 'center' }}
                  sx={{ px: 1.5, py: 1, borderTop: i ? '1px solid #E2E8F0' : 'none', bgcolor: c > 0 ? alpha(COLOR_MODULO, 0.04) : '#FFF' }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{ fontWeight: 700, fontSize: 13.5 }} noWrap>{d.nombre}</Typography>
                    <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
                      <span style={{ fontFamily: 'monospace' }}>{d.sku}</span> · disponible <b>{num(d.disponible)} und</b>{eqDisp && ` (${eqDisp})`}
                      {c > 0 && <> · se envía <b style={{ color: c > d.disponible ? '#DC2626' : COLOR_MODULO }}>{num(c)} und</b></>}
                    </Typography>
                    {en !== contar && <Typography sx={{ fontSize: 11.5, color: '#B45309' }}>Sin {NOMBRE_CONTAR[contar][0]}: se cuenta en unidades</Typography>}
                  </Box>
                  <Stack direction="row" gap={0.6} flexWrap="wrap" alignItems="center">
                    <Tooltip title={`Quitar 1 ${NOMBRE_CONTAR[en][0]}`}><span>
                      <IconButton size="small" disabled={c < f} onClick={() => onCambio(fijar(items, p, c - f))} sx={{ border: '1px solid #E2E8F0' }}><Remove fontSize="small" /></IconButton>
                    </span></Tooltip>
                    <Button size="small" variant="outlined" startIcon={<Add />} disabled={c + f > d.disponible}
                      onClick={() => onCambio(fijar(items, p, c + f))} sx={{ textTransform: 'none', fontWeight: 700 }}>
                      1 {NOMBRE_CONTAR[en][0]}{f > 1 ? ` (${num(f)})` : ''}
                    </Button>
                    {completos > 0 && c < completos && (
                      <Button size="small" variant="contained" startIcon={<DoneAll />} onClick={() => onCambio(fijar(items, p, completos))}
                        sx={{ textTransform: 'none', fontWeight: 700 }}>Todo ({plural(completos / f, en)})</Button>
                    )}
                    <TextField size="small" type="number" label={mayus(NOMBRE_CONTAR[en][1])} value={c / f} sx={{ width: 104 }}
                      inputProps={{ min: 0, step: 1 }}
                      onChange={e => onCambio(fijar(items, p, (Number(e.target.value) || 0) * f))} />
                  </Stack>
                </Stack>
              )
            })}
          </Box>
        </Box>
      )}
      {modo === 'ESCANER' && (
        <Box sx={{ mb: 1.5 }}>
          <CampoEscaner onLeido={leido} lecturaInicial={lecturaPendiente} ayuda="Escanee cajas o unidades: cada código suma las unidades que contiene." />
        </Box>
      )}
      {modo === 'RFID' && <Box sx={{ mb: 1.5 }}><PanelRFID onLeido={leido} /></Box>}

      {/* Lo que se va a enviar */}
      {items.length > 0 && (
        <Box sx={{ border: '1px solid #E2E8F0', borderRadius: 2, overflow: 'hidden' }}>
          {items.map((x, i) => {
            const disp = dispDe(x.producto_id)
            const excede = x.cantidad > disp
            const { c: en, f } = unidadDe(x.producto_id)
            const eq = equivalencia(x.cantidad, niveles.get(x.producto_id))
            return (
              <Stack key={x.producto_id} direction="row" alignItems="center" gap={1.5}
                sx={{ px: 1.5, py: 1, borderTop: i ? '1px solid #E2E8F0' : 'none', bgcolor: i % 2 ? '#F8FAFC' : '#FFF' }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: 13.5, fontWeight: 700 }} noWrap>{x.nombre}</Typography>
                  <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
                    <span style={{ fontFamily: 'monospace' }}>{x.sku}</span> · {textoDesglose(x.desglose)} · disponible {num(disp)} und
                  </Typography>
                </Box>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography sx={{ fontSize: 13.5, fontWeight: 800 }}>{num(x.cantidad)} und</Typography>
                  {eq && <Typography sx={{ fontSize: 12, color: COLOR_MODULO, fontWeight: 600 }}>= {eq}</Typography>}
                </Box>
                {excede && <Chip size="small" color="error" label={`Supera lo disponible en ${num(x.cantidad - disp)}`} />}
                <TextField size="small" type="number" label={mayus(NOMBRE_CONTAR[en][1])} value={x.cantidad / f} sx={{ width: 104 }}
                  inputProps={{ min: 0 }} onChange={e => onCambio(fijar(items, x, (Number(e.target.value) || 0) * f))} />
                <Tooltip title="Quitar"><IconButton size="small" color="error" onClick={() => onCambio(items.filter(y => y.producto_id !== x.producto_id))}>
                  <DeleteOutline fontSize="small" /></IconButton></Tooltip>
              </Stack>
            )
          })}
          <Box sx={{ px: 1.5, py: 1, bgcolor: alpha(COLOR_MODULO, 0.06), display: 'flex', justifyContent: 'space-between' }}>
            <Typography sx={{ fontSize: 13, fontWeight: 700 }}>{items.length} {items.length === 1 ? 'producto' : 'productos'}</Typography>
            <Typography sx={{ fontSize: 13, fontWeight: 800 }}>{num(total)} unidades</Typography>
          </Box>
        </Box>
      )}
      {excedidos.length > 0 && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          Algunos productos superan lo disponible en el origen: se enviará solo lo que haya.
        </Alert>
      )}
    </Box>
  )
}
