/**
 * Lo que la empresa paga: tarifa, estado de cuenta y pagos recibidos.
 *
 * El estado de cuenta se calcula sobre el **periodo que cubre cada pago**, no
 * sobre la fecha en que se pagó: un cliente puede pagar tarde tres meses juntos
 * y estar al día, y otro puede pagar puntual un solo mes y estar descubierto.
 */
import { useState } from 'react'
import {
  Box, Card, Typography, Stack, Button, Alert, Skeleton, Chip, Table, TableBody, TableCell, TableHead, TableRow, IconButton, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, Divider,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { Add, Delete } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { consolaApi, mensajeDeError, type Empresa, type Pago } from './api'
import Facturacion from './Facturacion'

const METODOS = ['Transferencia', 'PSE', 'Efectivo', 'Cheque', 'Tarjeta', 'Otro']

const pesos = (v: string | number, moneda = 'COP') => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return new Intl.NumberFormat('es-CO', {
    style: 'currency', currency: moneda, maximumFractionDigits: 0,
  }).format(n)
}

const dia = (f?: string | null) => {
  if (!f) return '—'
  // Las fechas llegan como YYYY-MM-DD. Construir un Date con esa cadena la
  // interpreta en UTC y en Colombia se ve un día antes, así que se parte a mano.
  const [a, m, d] = f.split('-').map(Number)
  return Number.isFinite(a) ? `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${a}` : f
}

const PAGO_VACIO = (): Pago => ({
  fecha: new Date().toISOString().slice(0, 10),
  monto: '', moneda: 'COP',
  periodo_desde: '', periodo_hasta: '', metodo: 'Transferencia', referencia: '', notas: '',
})

// ─── Registrar un pago ────────────────────────────────────────────────────────

function DialogoPago({
  empresa, abierto, onCerrar,
}: {
  empresa: Empresa
  abierto: boolean
  onCerrar: () => void
}) {
  const qc = useQueryClient()
  const [f, setF] = useState<Pago>(PAGO_VACIO())

  // Solo se ofrecen las facturas que todavía deben algo: aplicar un pago a una
  // ya saldada es casi siempre un error de dedo.
  const { data: facturas = [] } = useQuery({
    queryKey: ['facturas', empresa.id], queryFn: () => consolaApi.facturas(empresa.id),
  })
  const pendientes = facturas.filter(x => !x.anulada && Number(x.saldo) > 0)

  const registrar = useMutation({
    mutationFn: () => consolaApi.registrarPago(empresa.id, {
      ...f,
      periodo_desde: f.periodo_desde || null,
      periodo_hasta: f.periodo_hasta || null,
      factura_id: f.factura_id || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pagos', empresa.id] })
      qc.invalidateQueries({ queryKey: ['cartera', empresa.id] })
      // El saldo de la factura cambia con el pago.
      qc.invalidateQueries({ queryKey: ['facturas', empresa.id] })
      qc.invalidateQueries({ queryKey: ['contabilidad'] })
      setF(PAGO_VACIO()); onCerrar()
      toast.success('Pago registrado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const set = (k: keyof Pago) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Registrar pago</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={2}>
            <TextField
              label="Fecha del pago" type="date" value={f.fecha} onChange={set('fecha')}
              fullWidth InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Monto" value={f.monto} onChange={set('monto')} fullWidth required
              placeholder="2201500"
            />
          </Stack>
          <TextField
            select label="Aplicar a la factura" fullWidth
            value={f.factura_id ?? ''}
            onChange={e => {
              const id = e.target.value ? Number(e.target.value) : null
              const fa = facturas.find(x => x.id === id)
              // Al elegir factura se traen su periodo y su saldo: es lo que se
              // iba a escribir a mano, y así el pago queda cuadrado.
              setF(p => ({
                ...p,
                factura_id: id,
                monto: fa && !String(p.monto).trim() ? fa.saldo : p.monto,
                periodo_desde: fa?.periodo_desde ?? p.periodo_desde,
                periodo_hasta: fa?.periodo_hasta ?? p.periodo_hasta,
              }))
            }}
            helperText={pendientes.length === 0
              ? 'No hay facturas con saldo; el pago quedará como anticipo'
              : 'Déjelo vacío si es un anticipo sin factura'}
          >
            <MenuItem value="">— Anticipo, sin factura —</MenuItem>
            {pendientes.map(x => (
              <MenuItem key={x.id} value={x.id}>
                {x.numero} · saldo {pesos(x.saldo, x.moneda)}
              </MenuItem>
            ))}
          </TextField>

          <Alert severity="info" sx={{ py: 0.5 }}>
            El periodo es lo que decide si la empresa está al día, no la fecha del pago.
          </Alert>
          <Stack direction="row" spacing={2}>
            <TextField
              label="Periodo desde" type="date" value={f.periodo_desde ?? ''}
              onChange={set('periodo_desde')} fullWidth InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Periodo hasta" type="date" value={f.periodo_hasta ?? ''}
              onChange={set('periodo_hasta')} fullWidth InputLabelProps={{ shrink: true }}
            />
          </Stack>
          <Stack direction="row" spacing={2}>
            <TextField select label="Método" value={f.metodo ?? ''} onChange={set('metodo')} fullWidth>
              {METODOS.map(m => <MenuItem key={m} value={m}>{m}</MenuItem>)}
            </TextField>
            <TextField
              label="Referencia" value={f.referencia ?? ''} onChange={set('referencia')}
              fullWidth placeholder="N.º de factura o comprobante"
            />
          </Stack>
          <TextField label="Notas" value={f.notas ?? ''} onChange={set('notas')} fullWidth multiline rows={2} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" onClick={() => registrar.mutate()}
          disabled={registrar.isPending || !String(f.monto).trim()}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Registrar
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Tarifa y estado de cuenta ────────────────────────────────────────────────

export default function Comercial({ empresa }: { empresa: Empresa }) {
  const qc = useQueryClient()
  const [nuevo, setNuevo] = useState(false)
  const [borrador, setBorrador] = useState<Record<string, string> | null>(null)

  const { data: contrato, isLoading } = useQuery({
    queryKey: ['contrato', empresa.id], queryFn: () => consolaApi.contrato(empresa.id),
  })
  const { data: cartera } = useQuery({
    queryKey: ['cartera', empresa.id], queryFn: () => consolaApi.cartera(empresa.id),
  })
  const { data: pagos = [] } = useQuery({
    queryKey: ['pagos', empresa.id], queryFn: () => consolaApi.pagos(empresa.id),
  })

  const guardar = useMutation({
    mutationFn: () => consolaApi.guardarContrato(empresa.id, {
      tarifa_mensual: campo('tarifa_mensual'),
      iva_pct: campo('iva_pct'),
      dia_corte: Number(campo('dia_corte')) as any,
      moneda: campo('moneda'),
      inicio: (campo('inicio') || null) as any,
      notas: campo('notas'),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contrato', empresa.id] })
      qc.invalidateQueries({ queryKey: ['cartera', empresa.id] })
      setBorrador(null)
      toast.success('Contrato guardado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const borrarPago = useMutation({
    mutationFn: (id: number) => consolaApi.borrarPago(empresa.id, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pagos', empresa.id] })
      qc.invalidateQueries({ queryKey: ['cartera', empresa.id] })
      // El saldo de la factura cambia con el pago.
      qc.invalidateQueries({ queryKey: ['facturas', empresa.id] })
      qc.invalidateQueries({ queryKey: ['contabilidad'] })
      toast.success('Pago anulado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const campo = (k: string) =>
    borrador?.[k] ?? String((contrato as any)?.[k] ?? '')
  const set = (k: string) => (e: any) =>
    setBorrador(p => ({ ...(p ?? {}), [k]: e.target.value }))

  if (isLoading) return <Skeleton variant="rectangular" height={340} sx={{ borderRadius: 3 }} />

  return (
    <Box>
      {/* Estado de cuenta */}
      {cartera && (
        <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} alignItems="center">
            <Box sx={{ flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Tarifa mensual</Typography>
              <Typography variant="h6" fontWeight={800} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {pesos(cartera.tarifa_mensual, cartera.moneda)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {pesos(cartera.total_con_iva, cartera.moneda)} con IVA del {Number(cartera.iva_pct)}%
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', sm: 'block' } }} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Pagado en total</Typography>
              <Typography variant="h6" fontWeight={800} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {pesos(cartera.pagado_total, cartera.moneda)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {pagos.length} {pagos.length === 1 ? 'pago' : 'pagos'} registrados
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', sm: 'block' } }} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Estado</Typography>
              <Box mt={0.5}>
                {!cartera.hay_datos ? (
                  <Chip label="Sin datos" size="small" sx={{
                    fontWeight: 700, bgcolor: `${PALETA.acero}26`, color: PALETA.grafito,
                  }} />
                ) : cartera.al_dia ? (
                  <Chip label="Al día" size="small" sx={{
                    fontWeight: 700, bgcolor: `${ESTADO.exito}1A`, color: ESTADO.exito,
                  }} />
                ) : (
                  <Chip label={`${cartera.dias_en_mora} días en mora`} size="small" sx={{
                    fontWeight: 700, bgcolor: `${ESTADO.peligro}1A`, color: ESTADO.peligro,
                  }} />
                )}
              </Box>
              <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
                {cartera.hay_datos
                  ? `Cubierto hasta ${dia(cartera.cubierto_hasta)}`
                  : 'Ningún pago tiene periodo registrado'}
              </Typography>
            </Box>
          </Stack>
        </Card>
      )}

      {/* Tarifa */}
      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
        <Typography variant="subtitle2" fontWeight={800} mb={2}>Condiciones</Typography>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Tarifa mensual" value={campo('tarifa_mensual')} onChange={set('tarifa_mensual')}
              fullWidth size="small" helperText="Tarifa plana por empresa, no por usuario"
            />
            <TextField label="Moneda" value={campo('moneda')} onChange={set('moneda')}
              fullWidth size="small" />
            <TextField label="IVA %" value={campo('iva_pct')} onChange={set('iva_pct')}
              fullWidth size="small" helperText="0 si no es responsable de IVA" />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Día de corte" value={campo('dia_corte')} onChange={set('dia_corte')}
              fullWidth size="small" helperText="Entre 1 y 28"
            />
            <TextField
              label="Inicio del contrato" type="date" value={campo('inicio')} onChange={set('inicio')}
              fullWidth size="small" InputLabelProps={{ shrink: true }}
            />
          </Stack>
          <TextField label="Notas" value={campo('notas')} onChange={set('notas')}
            fullWidth size="small" multiline rows={2} />
          <Box>
            <Button
              variant="contained" disabled={!borrador || guardar.isPending}
              onClick={() => guardar.mutate()}
              sx={{ textTransform: 'none', fontWeight: 700 }}
            >
              Guardar condiciones
            </Button>
          </Box>
        </Stack>
      </Card>

      {/* Facturas y notas crédito */}
      <Box sx={{ mb: 2.5 }}><Facturacion empresa={empresa} /></Box>

      {/* Pagos */}
      <Card sx={{ borderRadius: 3 }}>
        <Stack direction="row" alignItems="center" sx={{ p: 2.5, pb: 1.5 }}>
          <Typography variant="subtitle2" fontWeight={800} sx={{ flex: 1 }}>
            Pagos recibidos
          </Typography>
          <Button
            startIcon={<Add />} size="small" variant="contained" onClick={() => setNuevo(true)}
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            Registrar pago
          </Button>
        </Stack>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>FECHA</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>MONTO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>PERIODO CUBIERTO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>MÉTODO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>REFERENCIA</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {pagos.map(p => (
              <TableRow key={p.id} hover>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{dia(p.fecha)}</TableCell>
                <TableCell sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                  {pesos(p.monto, p.moneda)}
                </TableCell>
                <TableCell sx={{ color: PALETA.grafito, whiteSpace: 'nowrap' }}>
                  {p.periodo_hasta ? `${dia(p.periodo_desde)} → ${dia(p.periodo_hasta)}` : '—'}
                </TableCell>
                <TableCell>{p.metodo ?? '—'}</TableCell>
                <TableCell sx={{ color: PALETA.grafito }}>{p.referencia ?? '—'}</TableCell>
                <TableCell align="right">
                  <Tooltip title="Anular este pago">
                    <IconButton size="small" onClick={() => p.id && borrarPago.mutate(p.id)}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {pagos.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" sx={{ textAlign: 'center', py: 3, color: PALETA.acero }}>
                    Todavía no hay pagos registrados
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <DialogoPago empresa={empresa} abierto={nuevo} onCerrar={() => setNuevo(false)} />
    </Box>
  )
}
