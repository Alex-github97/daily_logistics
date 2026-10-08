/**
 * Campo de escaneo para el WMS.
 *
 * Un lector de código de barras se comporta como un teclado: escribe el código
 * y presiona Enter. Este campo toma el código, lo resuelve en el servidor
 * (`/wms/codigos/{código}`) y entrega el producto, el nivel (unidad, caja,
 * máster, estiba) y cuántas unidades representa. Quien lo usa decide qué hacer
 * con eso: sumarlo a una recepción, a un traslado o a una orden de salida.
 *
 * El campo «× cantidad» sirve para escanear una vez y sumar varias (p. ej.
 * 10 cajas iguales: escribir 10 y escanear una).
 */
import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Chip, InputAdornment, Stack, TextField, Typography, alpha } from '@mui/material'
import { QrCodeScanner } from '@mui/icons-material'
import { apiClient } from '@/api/client'
import { COLOR_MODULO } from '@/config/marca'
import { useLectorGlobal } from '@/components/comun/LectorGlobal'

export interface CodigoResuelto {
  codigo: string
  producto_id: number
  sku: string
  nombre: string
  nivel: string
  nivel_nombre: string
  unidades: number
  requiere_lote: boolean
  unidad_medida: string
}

/** Una lectura: el código resuelto y cuántas veces se leyó (el multiplicador). */
export interface Lectura extends CodigoResuelto {
  veces: number
  /** Unidades base que suma esta lectura: unidades del nivel × veces. */
  total: number
}

export function CampoEscaner({
  onLeido, ayuda = 'Escanee unidades, cajas o másters: cada código suma las unidades que contiene.', autoFocus = true, lecturaInicial,
}: {
  onLeido: (l: Lectura) => void
  ayuda?: string
  autoFocus?: boolean
  /** Código leído antes de que el campo existiera (se pasó a modo escáner por esa lectura). */
  lecturaInicial?: string | null
}) {
  const [codigo, setCodigo] = useState('')
  const [veces, setVeces] = useState('1')
  const [ultimo, setUltimo] = useState<Lectura | null>(null)
  const [error, setError] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const ref = useRef<HTMLInputElement>(null)
  // Lecturas hechas con el cursor fuera del campo también llegan aquí.
  useLectorGlobal(c => { leer(c) })
  useEffect(() => { if (lecturaInicial) leer(lecturaInicial) }, [lecturaInicial])  // eslint-disable-line react-hooks/exhaustive-deps

  const tiempos = useRef<number[]>([])
  const auto = useRef<number | undefined>(undefined)
  const leer = async (leido?: string) => {
    window.clearTimeout(auto.current)
    const c = (leido ?? codigo).trim()
    if (!c || ocupado) return
    setOcupado(true); setError('')
    try {
      const r = await apiClient.get<CodigoResuelto>(`/wms/codigos/${encodeURIComponent(c)}`).then(x => x.data)
      const n = Math.max(1, Math.floor(Number(veces) || 1))
      const lectura: Lectura = { ...r, veces: n, total: r.unidades * n }
      setUltimo(lectura)
      onLeido(lectura)
      setVeces('1')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? `No se reconoce el código ${c}`)
      setUltimo(null)
    } finally {
      setCodigo('')
      setOcupado(false)
      ref.current?.focus()
    }
  }

  return (
    <Box sx={{ p: 1.5, borderRadius: 2, border: `1px dashed ${alpha(COLOR_MODULO, 0.5)}`, bgcolor: alpha(COLOR_MODULO, 0.04) }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5}>
        <TextField
          inputRef={ref} autoFocus={autoFocus} fullWidth size="small" value={codigo} disabled={ocupado}
          placeholder="Escanee o escriba el código y presione Enter"
          onChange={e => {
            const v = e.target.value
            setCodigo(v)
            // Lector sin Enter al final: si el texto llegó en ráfaga, se lee solo.
            const ahora = performance.now()
            tiempos.current = [...tiempos.current.slice(-20), ahora]
            window.clearTimeout(auto.current)
            const t = tiempos.current
            const rafaga = t.length >= 6 && (t[t.length - 1] - t[t.length - 6]) / 5 < 35
            if (rafaga && v.trim().length >= 6) auto.current = window.setTimeout(() => leer(v), 150)
          }}
          onKeyDown={e => { if (e.key === 'Enter' || (e.key === 'Tab' && codigo.trim())) { e.preventDefault(); leer() } }}
          InputProps={{ startAdornment: <InputAdornment position="start"><QrCodeScanner sx={{ color: COLOR_MODULO }} /></InputAdornment> }}
        />
        <TextField
          size="small" type="number" label="× cantidad" value={veces} sx={{ width: { sm: 120 } }}
          inputProps={{ min: 1 }} onChange={e => setVeces(e.target.value)}
        />
      </Stack>
      <Typography sx={{ fontSize: 12, color: 'text.secondary', mt: 0.8 }}>{ayuda}</Typography>
      {ultimo && (
        <Stack direction="row" alignItems="center" gap={1} mt={1} flexWrap="wrap">
          <Chip size="small" color="success" label={`+${ultimo.total.toLocaleString('es-CO')} und`} sx={{ fontWeight: 800 }} />
          <Typography sx={{ fontSize: 13 }}>
            <b>{ultimo.nombre}</b> · {ultimo.nivel_nombre}
            {ultimo.unidades > 1 ? ` de ${ultimo.unidades.toLocaleString('es-CO')} und` : ''}
            {ultimo.veces > 1 ? ` × ${ultimo.veces}` : ''} · <span style={{ fontFamily: 'monospace' }}>{ultimo.codigo}</span>
          </Typography>
        </Stack>
      )}
      {error && <Alert severity="error" sx={{ mt: 1, py: 0 }}>{error}</Alert>}
    </Box>
  )
}

/** Suma lecturas por producto: lo que se arma al escanear (traslados, salidas). */
export interface ItemEscaneado {
  producto_id: number
  sku: string
  nombre: string
  cantidad: number
  /** Desglose: cuántas lecturas de cada nivel (p. ej. { Caja: 3, Unidad: 2 }). */
  desglose: Record<string, number>
}

export function agregarLectura(items: ItemEscaneado[], l: Lectura): ItemEscaneado[] {
  const i = items.findIndex(x => x.producto_id === l.producto_id)
  if (i < 0) {
    return [...items, { producto_id: l.producto_id, sku: l.sku, nombre: l.nombre, cantidad: l.total,
                        desglose: { [l.nivel_nombre]: l.veces } }]
  }
  return items.map((x, j) => j !== i ? x : {
    ...x, cantidad: x.cantidad + l.total,
    desglose: { ...x.desglose, [l.nivel_nombre]: (x.desglose[l.nivel_nombre] ?? 0) + l.veces },
  })
}

const PLURAL: Record<string, string> = {
  Unidad: 'unidades', Caja: 'cajas', 'Caja máster': 'cajas máster', Estiba: 'estibas',
}

export const textoDesglose = (d: Record<string, number>) =>
  Object.entries(d).map(([n, v]) => n === 'Manual'
    ? 'selección manual'
    : `${v} ${v === 1 ? n.toLowerCase() : PLURAL[n] ?? n.toLowerCase()}`).join(' + ')

/**
 * Escáner + lista acumulada: lo que se arma al escanear para un traslado o una
 * orden de salida. Las cantidades se pueden corregir a mano antes de usarla.
 */
export function ListaEscaneo({
  items, onCambio, ayuda,
}: {
  items: ItemEscaneado[]
  onCambio: (items: ItemEscaneado[]) => void
  ayuda?: string
}) {
  const total = items.reduce((s, x) => s + x.cantidad, 0)
  return (
    <Box>
      <CampoEscaner onLeido={l => onCambio(agregarLectura(items, l))} ayuda={ayuda} />
      {items.length > 0 && (
        <Box sx={{ mt: 1.5, border: '1px solid #E2E8F0', borderRadius: 2, overflow: 'hidden' }}>
          {items.map((x, i) => (
            <Stack key={x.producto_id} direction="row" alignItems="center" gap={1.5}
              sx={{ px: 1.5, py: 1, borderTop: i ? '1px solid #E2E8F0' : 'none', bgcolor: i % 2 ? '#F8FAFC' : '#FFF' }}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontSize: 13.5, fontWeight: 700 }} noWrap>{x.nombre}</Typography>
                <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
                  <span style={{ fontFamily: 'monospace' }}>{x.sku}</span> · {textoDesglose(x.desglose)}
                </Typography>
              </Box>
              <TextField size="small" type="number" label="Unidades" value={x.cantidad} sx={{ width: 120 }}
                inputProps={{ min: 0 }}
                onChange={e => onCambio(items.map(y => y.producto_id === x.producto_id ? { ...y, cantidad: Number(e.target.value) || 0 } : y))} />
              <Chip size="small" label="Quitar" variant="outlined" onClick={() => onCambio(items.filter(y => y.producto_id !== x.producto_id))} />
            </Stack>
          ))}
          <Box sx={{ px: 1.5, py: 1, bgcolor: alpha(COLOR_MODULO, 0.06), display: 'flex', justifyContent: 'space-between' }}>
            <Typography sx={{ fontSize: 13, fontWeight: 700 }}>{items.length} producto(s)</Typography>
            <Typography sx={{ fontSize: 13, fontWeight: 800 }}>{total.toLocaleString('es-CO')} unidades</Typography>
          </Box>
        </Box>
      )}
    </Box>
  )
}
