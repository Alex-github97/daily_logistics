/**
 * Lector de códigos de barras en toda la aplicación.
 *
 * Un lector USB (láser, infrarrojo o imager) en modo teclado «escribe» el
 * código muy rápido —un carácter cada pocos milisegundos— y casi siempre
 * termina con Enter o Tab. Antes, la lectura solo servía si el cursor estaba
 * dentro de un campo «Escáner»; en cualquier otra parte se perdía sin aviso.
 *
 * - `DetectorLector` (va una vez en el Layout) reconoce esas ráfagas aunque el
 *   cursor no esté en ningún campo.
 * - Si la pantalla tiene un campo de escaneo (`useLectorGlobal`), la lectura
 *   va a ese campo: recepción, traslados, picking, armado de órdenes…
 * - Si no, se abre «Lectura del escáner»: qué producto es, cuánto hay y dónde;
 *   y si el código no existe, permite asignarlo a un producto o crear uno.
 */
import { useEffect, useRef, useState } from 'react'
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem,
  Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import { QrCodeScanner } from '@mui/icons-material'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { apiClient } from '@/api/client'
import { ACENTO, PALETA } from '@/config/marca'

type Manejador = (codigo: string) => void
const pila: Manejador[] = []

/** Recibe las lecturas del lector mientras el componente está montado. */
export function useLectorGlobal(manejador: Manejador, activo = true) {
  const ref = useRef(manejador)
  ref.current = manejador
  useEffect(() => {
    if (!activo) return
    const f: Manejador = c => ref.current(c)
    pila.push(f)
    return () => { const i = pila.lastIndexOf(f); if (i >= 0) pila.splice(i, 1) }
  }, [activo])
}

const RAFAGA_MS = 50     // entre teclas: un lector va a menos de 30 ms, una persona a más de 80
const MINIMO = 3         // caracteres para considerar que es un código
const SIN_FIN_MS = 150   // lectores sin Enter final: se da por terminado tras esta pausa

const editable = (el: EventTarget | null) => {
  const e = el as HTMLElement | null
  if (!e) return false
  const tag = e.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.isContentEditable
}

interface Resuelto { codigo: string; producto_id: number; sku: string; nombre: string; nivel: string; nivel_nombre: string; unidades: number }
interface Posicion { ubicacion_codigo?: string; ubicacion?: { codigo: string }; cantidad_disponible: number; cantidad_reservada: number; lote?: { numero_lote: string } | null }
interface ProductoLista { id: number; sku: string; nombre: string; niveles: { nivel: string; nombre: string; unidades: number }[] }

function DialogoLectura({ codigo, onClose }: { codigo: string; onClose: () => void }) {
  const nav = useNavigate()
  const [r, setR] = useState<Resuelto | null>(null)
  const [error, setError] = useState('')
  const [stock, setStock] = useState<Posicion[] | null>(null)
  const [productos, setProductos] = useState<ProductoLista[]>([])
  const [destino, setDestino] = useState<ProductoLista | null>(null)
  const [nivel, setNivel] = useState('UNIDAD')
  const [guardando, setGuardando] = useState(false)

  const resolver = async () => {
    setError(''); setR(null); setStock(null)
    try {
      const x = await apiClient.get<Resuelto>(`/wms/codigos/${encodeURIComponent(codigo)}`).then(y => y.data)
      setR(x)
      apiClient.get<Posicion[]>('/wms/inventario/', { params: { producto_id: x.producto_id } }).then(y => setStock(y.data)).catch(() => setStock([]))
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Código no reconocido')
      apiClient.get<ProductoLista[]>('/wms/maestro/productos', { params: { activo: true } }).then(y => setProductos(y.data)).catch(() => {})
    }
  }
  useEffect(() => { resolver() }, [codigo])  // eslint-disable-line react-hooks/exhaustive-deps

  const asignar = async () => {
    if (!destino) return
    setGuardando(true)
    try {
      await apiClient.post(`/wms/codigos/${encodeURIComponent(codigo)}/asignar`, { producto_id: destino.id, nivel })
      toast.success(`Código ${codigo} asignado a ${destino.nombre}`)
      await resolver()
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'No se pudo asignar') } finally { setGuardando(false) }
  }
  const total = (stock ?? []).reduce((s, p) => s + (p.cantidad_disponible || 0), 0)
  const reservado = (stock ?? []).reduce((s, p) => s + (p.cantidad_reservada || 0), 0)

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
        <QrCodeScanner sx={{ color: ACENTO.base }} /> Lectura del escáner
        <Chip size="small" label={codigo} sx={{ fontFamily: 'monospace', fontWeight: 700, ml: 'auto' }} />
      </DialogTitle>
      <DialogContent dividers>
        {!r && !error && <CircularProgress size={22} />}
        {r && (
          <>
            <Typography sx={{ fontSize: 18, fontWeight: 800 }}>{r.nombre}</Typography>
            <Typography sx={{ fontSize: 13, color: PALETA.grafito, mb: 1.5 }}>
              SKU <b style={{ fontFamily: 'monospace' }}>{r.sku}</b> · {r.nivel_nombre}{r.unidades > 1 ? ` de ${r.unidades.toLocaleString('es-CO')} unidades` : ''}
            </Typography>
            <Stack direction="row" gap={1} mb={1.5}>
              <Chip color="success" label={`Disponible: ${total.toLocaleString('es-CO')} und`} sx={{ fontWeight: 700 }} />
              {reservado > 0 && <Chip color="warning" label={`Reservado: ${reservado.toLocaleString('es-CO')} und`} />}
              {r.unidades > 1 && <Chip variant="outlined" label={`= ${Math.floor(total / r.unidades).toLocaleString('es-CO')} ${r.nivel_nombre.toLowerCase()}s`} />}
            </Stack>
            {stock && stock.length > 0 && (
              <Table size="small">
                <TableHead><TableRow><TableCell>Ubicación</TableCell><TableCell>Lote</TableCell><TableCell align="right">Disponible</TableCell><TableCell align="right">Reservado</TableCell></TableRow></TableHead>
                <TableBody>
                  {stock.filter(p => p.cantidad_disponible || p.cantidad_reservada).slice(0, 10).map((p, i) => (
                    <TableRow key={i}>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{p.ubicacion?.codigo ?? p.ubicacion_codigo ?? '—'}</TableCell>
                      <TableCell>{p.lote?.numero_lote ?? '—'}</TableCell>
                      <TableCell align="right">{p.cantidad_disponible.toLocaleString('es-CO')}</TableCell>
                      <TableCell align="right">{(p.cantidad_reservada || 0).toLocaleString('es-CO')}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            <Alert severity="info" sx={{ mt: 2, fontSize: 13 }}>
              El lector funciona. Para registrar movimientos, escanee dentro de Recepción, Traslados, Picking o Pedidos:
              allí cada lectura suma unidades al documento.
            </Alert>
          </>
        )}
        {error && (
          <>
            <Alert severity="warning" sx={{ mb: 2 }}>
              {error} El lector funciona, pero este código no está registrado en el maestro (suele pasar con el código de barras
              del fabricante).
            </Alert>
            <Typography sx={{ fontWeight: 700, fontSize: 14, mb: 1 }}>Asignar este código a un producto existente</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={1}>
              <Autocomplete sx={{ flex: 1 }} size="small" options={productos} value={destino}
                getOptionLabel={o => `${o.sku} · ${o.nombre}`} onChange={(_, v) => { setDestino(v); setNivel('UNIDAD') }}
                renderInput={p => <TextField {...p} label="Producto" />} />
              <TextField select size="small" label="Es el código de" value={nivel} onChange={e => setNivel(e.target.value)} sx={{ minWidth: 150 }}>
                {(destino?.niveles ?? [{ nivel: 'UNIDAD', nombre: 'Unidad', unidades: 1 }]).map(n => (
                  <MenuItem key={n.nivel} value={n.nivel}>{n.nivel === 'UNIDAD' ? 'La unidad' : `${n.nombre} (${n.unidades} und)`}</MenuItem>
                ))}
              </TextField>
              <Button variant="contained" disabled={!destino || guardando} onClick={asignar}>Asignar</Button>
            </Stack>
          </>
        )}
      </DialogContent>
      <DialogActions>
        {error && <Button onClick={() => { onClose(); nav(`/wms/productos?nuevo=1&codigo=${encodeURIComponent(codigo)}`) }}>Crear producto con este código</Button>}
        {r && <Button onClick={() => { onClose(); nav(`/wms/productos?q=${encodeURIComponent(r.sku)}`) }}>Ver en el maestro</Button>}
        <Box flex={1} />
        <Button variant="contained" onClick={onClose}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  )
}

export function DetectorLector() {
  const [lectura, setLectura] = useState<string | null>(null)
  const buf = useRef<{ texto: string; ultimo: number; rapido: boolean }>({ texto: '', ultimo: 0, rapido: true })
  const temporizador = useRef<number | undefined>(undefined)

  useEffect(() => {
    const entregar = (codigo: string) => {
      const c = codigo.trim()
      if (c.length < MINIMO) return
      const destino = pila[pila.length - 1]
      if (destino) destino(c)
      else setLectura(c)
    }
    const alTeclear = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey) return
      if (editable(e.target)) { buf.current = { texto: '', ultimo: 0, rapido: true }; return }
      const ahora = performance.now()
      const b = buf.current
      if (e.key === 'Enter' || e.key === 'Tab') {
        if (b.texto.length >= MINIMO && b.rapido && ahora - b.ultimo < 300) {
          e.preventDefault(); e.stopPropagation()
          window.clearTimeout(temporizador.current)
          const c = b.texto
          buf.current = { texto: '', ultimo: 0, rapido: true }
          entregar(c)
        }
        return
      }
      if (e.key.length !== 1) return
      const seguido = b.texto && ahora - b.ultimo < RAFAGA_MS
      buf.current = seguido ? { texto: b.texto + e.key, ultimo: ahora, rapido: b.rapido } : { texto: e.key, ultimo: ahora, rapido: true }
      // Lectores configurados sin Enter al final: la ráfaga termina sola.
      window.clearTimeout(temporizador.current)
      temporizador.current = window.setTimeout(() => {
        const x = buf.current
        if (x.texto.length >= 6) { buf.current = { texto: '', ultimo: 0, rapido: true }; entregar(x.texto) }
      }, SIN_FIN_MS)
    }
    window.addEventListener('keydown', alTeclear, true)
    return () => { window.removeEventListener('keydown', alTeclear, true); window.clearTimeout(temporizador.current) }
  }, [])

  return lectura ? <DialogoLectura codigo={lectura} onClose={() => setLectura(null)} /> : null
}
