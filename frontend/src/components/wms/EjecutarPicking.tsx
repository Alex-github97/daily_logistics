/**
 * Ejecución de una tarea de picking, con tres formas de registrar lo alistado:
 *
 *   - Selección manual: cada línea tiene botones (+1 unidad, +1 caja, «todo»,
 *     «no hay») y campo de cantidad.
 *   - Escáner: se puede escanear la ubicación donde se está parado y luego los
 *     códigos de unidad, caja o máster; cada lectura suma a su línea.
 *   - Radiofrecuencia (RFID): cada etiqueta distinta cuenta una sola vez.
 *
 * Las líneas van en orden de ubicación (el recorrido). Al confirmar, todo se
 * registra junto: lo que quede en 0 sin marcar «no hay» sigue pendiente.
 */
import { useMemo, useRef, useState } from 'react'
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, IconButton,
  InputAdornment, LinearProgress, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography, alpha,
} from '@mui/material'
import {
  Add, Remove, DoneAll, Block, Undo, TouchApp, QrCodeScanner, Sensors, Place,
} from '@mui/icons-material'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { TextField } from '@/components/comun/Desplegables'
import { CampoEscaner, type Lectura } from '@/components/wms/Escaner'
import { useLectorGlobal } from '@/components/comun/LectorGlobal'
import { PanelRFID } from '@/components/wms/ArticulosRecepcion'
import { equivalencia, useNiveles } from '@/components/wms/empaques'
import { apiClient as api } from '@/api/client'
import { COLOR_MODULO } from '@/config/marca'

export interface DetallePicking {
  id: number
  producto_id: number
  producto?: { sku: string; nombre: string }
  ubicacion_id: number
  ubicacion?: { codigo: string }
  cantidad_solicitada: number
  cantidad_pickeada: number
  confirmado: boolean
}
export interface TareaParaEjecutar { id: number; orden_id: number; detalles: DetallePicking[] }

interface Registro { cantidad: number; noHay: boolean; codigo?: string; ubicacionLeida?: string }

const num = (n: number) => n.toLocaleString('es-CO', { maximumFractionDigits: 2 })

export function EjecutarPicking({ tarea, onCerrar, onConfirmado }: {
  tarea: TareaParaEjecutar
  onCerrar: () => void
  onConfirmado: () => void
}) {
  const niveles = useNiveles()
  const [modo, setModo] = useState<'MANUAL' | 'ESCANER' | 'RFID'>('MANUAL')
  // Una lectura del lector en modo manual pasa sola a modo escáner y se procesa.
  const [lecturaPendiente, setLecturaPendiente] = useState<string | null>(null)
  useLectorGlobal(c => { setLecturaPendiente(c); setModo('ESCANER') }, modo !== 'ESCANER')
  const [reg, setRegEstado] = useState<Record<number, Registro>>({})
  // Espejo síncrono: el RFID entrega varias lecturas en el mismo instante y cada
  // una tiene que ver lo que sumó la anterior.
  const regRef = useRef<Record<number, Registro>>({})
  const setReg = (nuevo: Record<number, Registro>) => { regRef.current = nuevo; setRegEstado(nuevo) }
  const [ubicacion, setUbicacion] = useState('')
  const [aviso, setAviso] = useState('')
  const refUbic = useRef<HTMLInputElement>(null)

  // Recorrido: pendientes primero, en orden de ubicación.
  const lineas = useMemo(() => [...tarea.detalles].sort((a, b) =>
    Number(a.confirmado) - Number(b.confirmado) ||
    (a.ubicacion?.codigo ?? '').localeCompare(b.ubicacion?.codigo ?? '', 'es', { numeric: true })), [tarea.detalles])
  const pendientes = lineas.filter(l => !l.confirmado)

  const r = (id: number): Registro => reg[id] ?? { cantidad: 0, noHay: false }
  const fijar = (id: number, c: Partial<Registro>) =>
    setReg({ ...regRef.current, [id]: { ...(regRef.current[id] ?? { cantidad: 0, noHay: false }), ...c } })

  // Escáner / RFID: suma a las líneas del producto (primero la de la ubicación
  // escaneada), sin pasar de lo pedido; lo que sobra pasa a la siguiente línea.
  const leido = (l: Lectura) => {
    const delProducto = pendientes.filter(d => d.producto_id === l.producto_id)
    if (!delProducto.length) {
      setAviso(`${l.nombre} no está en esta tarea (o ya se confirmó).`)
      return
    }
    const ub = ubicacion.trim().toUpperCase()
    const orden = ub ? [...delProducto].sort((a, b) =>
      Number((b.ubicacion?.codigo ?? '').toUpperCase() === ub) - Number((a.ubicacion?.codigo ?? '').toUpperCase() === ub)) : delProducto
    let resto = l.total
    const sig = { ...regRef.current }
    {
      for (const d of orden) {
        if (resto <= 0) break
        const actual = sig[d.id] ?? { cantidad: 0, noHay: false }
        const cabe = d.cantidad_solicitada - actual.cantidad
        if (cabe <= 0) continue
        const tomar = Math.min(cabe, resto)
        sig[d.id] = { ...actual, cantidad: actual.cantidad + tomar, noHay: false, codigo: l.codigo,
                      ubicacionLeida: ub && (d.ubicacion?.codigo ?? '').toUpperCase() === ub ? ub : actual.ubicacionLeida }
        resto -= tomar
      }
    }
    setReg(sig)
    setAviso(resto > 0 ? `Se leyó más de lo pedido de ${l.nombre}: sobran ${num(resto)} und (no se suman).` : '')
  }

  const confirmar = useMutation({
    mutationFn: () => {
      const enviar = pendientes
        .filter(d => r(d.id).cantidad > 0 || r(d.id).noHay)
        .map(d => ({
          detalle_id: d.id, cantidad: r(d.id).noHay ? 0 : r(d.id).cantidad,
          producto_codigo: r(d.id).codigo, ubicacion_codigo: r(d.id).ubicacionLeida,
        }))
      return api.post(`/wms/picking-tareas/${tarea.id}/confirmar-lote`, { lineas: enviar }).then(x => x.data)
    },
    onSuccess: (t: { estado: string }) => {
      toast.success(t.estado === 'COMPLETADA' ? 'Tarea de picking completada' : 'Alistamiento registrado')
      onConfirmado()
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo confirmar el alistamiento'),
  })

  const marcadas = pendientes.filter(d => r(d.id).cantidad > 0 || r(d.id).noHay).length
  const totalPedido = pendientes.reduce((s, d) => s + d.cantidad_solicitada, 0)
  const totalAlistado = pendientes.reduce((s, d) => s + (r(d.id).noHay ? 0 : r(d.id).cantidad), 0)

  return (
    <Dialog open onClose={onCerrar} maxWidth="lg" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 800 }}>
        Ejecutar picking · tarea #{tarea.id}
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
          {pendientes.length} líneas pendientes · {num(totalAlistado)} de {num(totalPedido)} und alistadas
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} gap={1.5} mb={1.5}>
          <LinearProgress variant="determinate" value={totalPedido ? Math.min(100, (totalAlistado / totalPedido) * 100) : 0}
            sx={{ flex: 1, height: 8, borderRadius: 9, bgcolor: '#EEF2FF' }} />
          <ToggleButtonGroup size="small" exclusive value={modo} onChange={(_, v) => v && setModo(v)}>
            <ToggleButton value="MANUAL" sx={{ textTransform: 'none', gap: 0.6 }}><TouchApp fontSize="small" /> Selección manual</ToggleButton>
            <ToggleButton value="ESCANER" sx={{ textTransform: 'none', gap: 0.6 }}><QrCodeScanner fontSize="small" /> Escáner</ToggleButton>
            <ToggleButton value="RFID" sx={{ textTransform: 'none', gap: 0.6 }}><Sensors fontSize="small" /> Radiofrecuencia</ToggleButton>
          </ToggleButtonGroup>
        </Stack>

        {modo !== 'MANUAL' && (
          <TextField inputRef={refUbic} size="small" fullWidth sx={{ mb: 1.5 }} value={ubicacion}
            label="Ubicación donde está (opcional): escanéela para verificarla"
            onChange={e => setUbicacion(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); setUbicacion(ubicacion.trim().toUpperCase()) } }}
            InputProps={{ startAdornment: <InputAdornment position="start"><Place sx={{ color: COLOR_MODULO }} /></InputAdornment> }}
            helperText={ubicacion && !pendientes.some(d => (d.ubicacion?.codigo ?? '').toUpperCase() === ubicacion.trim().toUpperCase())
              ? 'Esa ubicación no tiene líneas pendientes en esta tarea' : 'Lo que escanee después se suma primero a las líneas de esta ubicación'} />
        )}
        {modo === 'ESCANER' && <Box sx={{ mb: 1.5 }}><CampoEscaner onLeido={leido} lecturaInicial={lecturaPendiente} autoFocus={false} ayuda="Escanee la unidad, la caja o el máster: suma a la línea del producto." /></Box>}
        {modo === 'RFID' && <Box sx={{ mb: 1.5 }}><PanelRFID onLeido={leido} /></Box>}
        {aviso && <Alert severity="warning" sx={{ mb: 1.5, py: 0 }} onClose={() => setAviso('')}>{aviso}</Alert>}

        {lineas.map(d => {
          const reg1 = r(d.id)
          const c = d.confirmado ? d.cantidad_pickeada : reg1.cantidad
          const empaques = (niveles.get(d.producto_id) ?? []).filter(n => n.nivel !== 'UNIDAD')
          const eq = equivalencia(c, niveles.get(d.producto_id))
          const estado = d.confirmado ? { t: 'Confirmada', col: '#16A34A' }
            : reg1.noHay ? { t: 'No hay', col: '#64748B' }
            : c >= d.cantidad_solicitada ? { t: 'Completa', col: '#16A34A' }
            : c > 0 ? { t: `Faltan ${num(d.cantidad_solicitada - c)}`, col: '#D97706' }
            : { t: 'Pendiente', col: '#94A3B8' }
          const enUbicacion = !!ubicacion && (d.ubicacion?.codigo ?? '').toUpperCase() === ubicacion.trim().toUpperCase()
          return (
            <Box key={d.id} data-producto={d.producto?.sku ?? ''} data-ubicacion={d.ubicacion?.codigo ?? ''}
              sx={{ p: 1.5, mb: 1, borderRadius: 2, border: '1px solid', borderColor: enUbicacion ? COLOR_MODULO : '#E2E8F0',
                bgcolor: d.confirmado ? '#F8FAFC' : enUbicacion ? alpha(COLOR_MODULO, 0.04) : '#FFF', opacity: d.confirmado || reg1.noHay ? 0.7 : 1 }}>
              <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} alignItems={{ md: 'center' }}>
                <Box sx={{ minWidth: 90 }}>
                  <Typography sx={{ fontSize: 11, color: 'text.secondary', fontWeight: 700 }}>UBICACIÓN</Typography>
                  <Typography sx={{ fontSize: 18, fontWeight: 800, fontFamily: 'monospace', color: COLOR_MODULO }}>{d.ubicacion?.codigo ?? '—'}</Typography>
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Stack direction="row" gap={1} alignItems="center">
                    <Typography sx={{ fontWeight: 700, fontSize: 14 }} noWrap>{d.producto?.nombre}</Typography>
                    <Chip size="small" label={estado.t} sx={{ fontWeight: 700, fontSize: 11, color: estado.col, bgcolor: alpha(estado.col, 0.1) }} />
                  </Stack>
                  <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
                    <span style={{ fontFamily: 'monospace' }}>{d.producto?.sku}</span> · pedido <b>{num(d.cantidad_solicitada)}</b> ·
                    alistado <b style={{ color: '#0B1120' }}>{num(c)}</b>{eq && <span style={{ color: COLOR_MODULO }}> (= {eq})</span>}
                  </Typography>
                </Box>
                {!d.confirmado && (
                  <Stack direction="row" gap={0.6} flexWrap="wrap" alignItems="center">
                    <Tooltip title="Quitar 1 unidad"><span>
                      <IconButton size="small" disabled={c <= 0 || reg1.noHay} onClick={() => fijar(d.id, { cantidad: c - 1 })} sx={{ border: '1px solid #E2E8F0' }}><Remove fontSize="small" /></IconButton>
                    </span></Tooltip>
                    <Button size="small" variant="outlined" startIcon={<Add />} disabled={c >= d.cantidad_solicitada}
                      onClick={() => fijar(d.id, { cantidad: c + 1, noHay: false })} sx={{ textTransform: 'none', fontWeight: 700 }}>1 und</Button>
                    {empaques.map(n => (
                      <Button key={n.nivel} size="small" variant="outlined" startIcon={<Add />} disabled={c + n.unidades > d.cantidad_solicitada}
                        onClick={() => fijar(d.id, { cantidad: c + n.unidades, noHay: false })} sx={{ textTransform: 'none', fontWeight: 700 }}>
                        1 {n.nombre.toLowerCase()} ({num(n.unidades)})
                      </Button>
                    ))}
                    {c < d.cantidad_solicitada && (
                      <Button size="small" variant="contained" startIcon={<DoneAll />} onClick={() => fijar(d.id, { cantidad: d.cantidad_solicitada, noHay: false })}
                        sx={{ textTransform: 'none', fontWeight: 700 }}>Todo ({num(d.cantidad_solicitada - c)})</Button>
                    )}
                    <TextField size="small" type="number" label="Cantidad" value={c} sx={{ width: 100 }} disabled={reg1.noHay}
                      inputProps={{ min: 0, max: d.cantidad_solicitada }}
                      onChange={e => fijar(d.id, { cantidad: Math.min(d.cantidad_solicitada, Math.max(0, Number(e.target.value) || 0)) })} />
                    {reg1.noHay ? (
                      <Tooltip title="Deshacer «no hay»"><IconButton size="small" onClick={() => fijar(d.id, { noHay: false })}><Undo fontSize="small" /></IconButton></Tooltip>
                    ) : (
                      <Tooltip title="No hay en la ubicación: libera lo reservado"><IconButton size="small" onClick={() => fijar(d.id, { noHay: true, cantidad: 0 })}><Block fontSize="small" /></IconButton></Tooltip>
                    )}
                  </Stack>
                )}
              </Stack>
            </Box>
          )
        })}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 1.5, gap: 1 }}>
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mr: 'auto' }}>
          Las líneas que deje en 0 (sin marcar «no hay») quedan pendientes para después.
        </Typography>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cerrar</Button>
        <Button variant="contained" disabled={!marcadas || confirmar.isPending} onClick={() => confirmar.mutate()}
          sx={{ textTransform: 'none', fontWeight: 700, minWidth: 190 }}>
          {confirmar.isPending ? <CircularProgress size={20} color="inherit" /> : `Confirmar ${marcadas} ${marcadas === 1 ? 'línea' : 'líneas'}`}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
