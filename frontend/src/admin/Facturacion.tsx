/**
 * Facturas y notas crédito de una empresa.
 *
 * Una factura emitida no se corrige editándola: se emite una nota crédito que
 * la disminuye, y las dos quedan en el historial. Y no se borra: una factura
 * que desaparece deja un hueco en el consecutivo que después nadie sabe
 * explicar, así que lo más que se puede hacer es anularla.
 */
import { Fragment, useState } from 'react'
import {
  Box, Card, Typography, Stack, Button, TextField, Alert, Chip, Tooltip,
  Table, TableBody, TableCell, TableHead, TableRow, IconButton, Collapse,
  Dialog, DialogTitle, DialogContent, DialogActions, Skeleton,
} from '@mui/material'
import {
  ReceiptLong, Block, Undo, KeyboardArrowDown, KeyboardArrowRight,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  consolaApi, mensajeDeError,
  type Empresa, type Factura, type NotaCredito,
} from './api'

const pesos = (v: string | number, moneda = 'COP') => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return new Intl.NumberFormat('es-CO', {
    style: 'currency', currency: moneda, maximumFractionDigits: 0,
  }).format(n)
}

const dia = (f?: string | null) => {
  if (!f) return '—'
  const [a, m, d] = f.split('-').map(Number)
  return Number.isFinite(a) ? `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${a}` : f
}

/** El primer y el último día del mes anterior, que es lo que suele facturarse. */
function mesPasado() {
  const hoy = new Date()
  const primero = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1)
  const ultimo = new Date(hoy.getFullYear(), hoy.getMonth(), 0)
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return { desde: iso(primero), hasta: iso(ultimo) }
}

// ─── Emitir factura ───────────────────────────────────────────────────────────

function DialogoFactura({
  empresa, abierto, onCerrar,
}: { empresa: Empresa; abierto: boolean; onCerrar: () => void }) {
  const qc = useQueryClient()
  const inicial = mesPasado()
  const [f, setF] = useState({
    periodo_desde: inicial.desde, periodo_hasta: inicial.hasta,
    subtotal: '', concepto: '', numero_externo: '',
  })

  const emitir = useMutation({
    mutationFn: () => consolaApi.emitirFactura(empresa.id, {
      periodo_desde: f.periodo_desde || null,
      periodo_hasta: f.periodo_hasta || null,
      // Vacío = se toma la tarifa del contrato.
      subtotal: f.subtotal.trim() ? f.subtotal : null,
      concepto: f.concepto || null,
      numero_externo: f.numero_externo || null,
    }),
    onSuccess: fa => {
      qc.invalidateQueries({ queryKey: ['facturas', empresa.id] })
      qc.invalidateQueries({ queryKey: ['contabilidad'] })
      onCerrar()
      toast.success(`Factura ${fa.numero} emitida`)
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const set = (k: keyof typeof f) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Emitir factura</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 2 }}>
          Los valores se congelan al emitirla: si la tarifa sube el mes que viene,
          esta factura no cambia.
        </Alert>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={2}>
            <TextField
              label="Periodo desde" type="date" value={f.periodo_desde}
              onChange={set('periodo_desde')} fullWidth InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Periodo hasta" type="date" value={f.periodo_hasta}
              onChange={set('periodo_hasta')} fullWidth InputLabelProps={{ shrink: true }}
            />
          </Stack>
          <TextField
            label="Valor sin IVA" value={f.subtotal} onChange={set('subtotal')} fullWidth
            helperText="Déjelo vacío para usar la tarifa del contrato"
          />
          <TextField label="Concepto" value={f.concepto} onChange={set('concepto')} fullWidth
            placeholder="Servicio de plataforma" />
          <TextField
            label="N.º de la factura electrónica" value={f.numero_externo}
            onChange={set('numero_externo')} fullWidth
            helperText="El número que le dio su proveedor de facturación electrónica, para cruzar"
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" onClick={() => emitir.mutate()} disabled={emitir.isPending}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          {emitir.isPending ? 'Emitiendo…' : 'Emitir factura'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Emitir nota crédito ──────────────────────────────────────────────────────

function DialogoNota({
  empresa, factura, onCerrar,
}: { empresa: Empresa; factura: Factura | null; onCerrar: () => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState({ valor: '', motivo: '', numero_externo: '' })
  const [listo, setListo] = useState<number | null>(null)

  if (factura && listo !== factura.id) {
    setListo(factura.id)
    setF({ valor: '', motivo: '', numero_externo: '' })
  }

  const disponible = factura
    ? Number(factura.total) - Number(factura.acreditado)
    : 0

  const emitir = useMutation({
    mutationFn: () => consolaApi.emitirNota(empresa.id, {
      factura_id: factura!.id, valor: f.valor, motivo: f.motivo,
      numero_externo: f.numero_externo || null,
    } as NotaCredito),
    onSuccess: n => {
      qc.invalidateQueries({ queryKey: ['facturas', empresa.id] })
      qc.invalidateQueries({ queryKey: ['notas', empresa.id] })
      qc.invalidateQueries({ queryKey: ['contabilidad'] })
      onCerrar()
      toast.success(`Nota crédito ${n.numero} emitida`)
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const set = (k: keyof typeof f) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))
  const excede = Number(f.valor) > disponible

  return (
    <Dialog open={!!factura} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>
        Nota crédito sobre {factura?.numero}
      </DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          Una factura emitida no se corrige: se disminuye con una nota crédito y
          las dos quedan en el historial.
        </Alert>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Box sx={{ bgcolor: PALETA.bruma, borderRadius: 2, p: 1.5 }}>
            <Typography variant="caption" color="text.secondary">
              Factura de {pesos(factura?.total ?? 0)} · ya acreditado {pesos(factura?.acreditado ?? 0)}
            </Typography>
            <Typography variant="body2" fontWeight={700}>
              Disponible para acreditar: {pesos(disponible)}
            </Typography>
          </Box>
          <TextField
            label="Valor" value={f.valor} onChange={set('valor')} fullWidth required
            error={excede}
            helperText={excede ? `No puede pasar de ${pesos(disponible)}` : ' '}
          />
          <TextField
            label="Motivo" value={f.motivo} onChange={set('motivo')} fullWidth required
            multiline rows={2}
            placeholder="Descuento comercial acordado, servicio no prestado, error en el valor…"
            helperText="Es lo primero que se pregunta al revisar la cuenta"
          />
          <TextField
            label="N.º de la nota crédito electrónica" value={f.numero_externo}
            onChange={set('numero_externo')} fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" color="warning" onClick={() => emitir.mutate()}
          disabled={emitir.isPending || !f.valor.trim() || !f.motivo.trim() || excede}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Emitir nota crédito
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── El listado ───────────────────────────────────────────────────────────────

export default function Facturacion({ empresa }: { empresa: Empresa }) {
  const qc = useQueryClient()
  const [nueva, setNueva] = useState(false)
  const [notaSobre, setNotaSobre] = useState<Factura | null>(null)
  const [abierta, setAbierta] = useState<number | null>(null)

  const { data: facturas = [], isLoading } = useQuery({
    queryKey: ['facturas', empresa.id], queryFn: () => consolaApi.facturas(empresa.id),
  })
  const { data: notas = [] } = useQuery({
    queryKey: ['notas', empresa.id], queryFn: () => consolaApi.notasCredito(empresa.id),
  })

  const anular = useMutation({
    mutationFn: (id: number) => consolaApi.anularFactura(empresa.id, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['facturas', empresa.id] })
      qc.invalidateQueries({ queryKey: ['contabilidad'] })
      toast.success('Factura anulada')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  if (isLoading) return <Skeleton variant="rectangular" height={280} sx={{ borderRadius: 3 }} />

  return (
    <Box>
      <Card sx={{ borderRadius: 3 }}>
        <Stack direction="row" alignItems="center" sx={{ p: 2.5, pb: 1.5 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" fontWeight={800}>Facturas</Typography>
            <Typography variant="caption" color="text.secondary">
              Control interno · no reemplaza a la facturación electrónica
            </Typography>
          </Box>
          <Button
            startIcon={<ReceiptLong />} size="small" variant="contained"
            onClick={() => setNueva(true)} sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            Emitir factura
          </Button>
        </Stack>

        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell width={36} />
              <TableCell sx={{ fontWeight: 700 }}>NÚMERO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>PERIODO</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">TOTAL</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">NOTAS CR.</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">PAGADO</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">SALDO</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {facturas.map(f => {
              const suyas = notas.filter(n => n.factura_id === f.id)
              const desplegada = abierta === f.id
              return (
                <Fragment key={f.id}>
                  <TableRow hover sx={{ opacity: f.anulada ? 0.55 : 1 }}>
                    <TableCell>
                      {suyas.length > 0 && (
                        <IconButton size="small" onClick={() => setAbierta(desplegada ? null : f.id)}>
                          {desplegada ? <KeyboardArrowDown fontSize="small" />
                                      : <KeyboardArrowRight fontSize="small" />}
                        </IconButton>
                      )}
                    </TableCell>
                    <TableCell sx={{ fontWeight: 700, fontFamily: 'monospace' }}>
                      {f.numero}
                      {f.anulada && (
                        <Chip label="Anulada" size="small" sx={{
                          ml: 1, height: 18, fontSize: 10, fontWeight: 700,
                          bgcolor: `${ESTADO.peligro}1A`, color: ESTADO.peligro,
                        }} />
                      )}
                      {f.numero_externo && (
                        <Typography variant="caption" color="text.secondary" display="block">
                          FE {f.numero_externo}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap', color: PALETA.grafito }}>
                      {dia(f.periodo_desde)} → {dia(f.periodo_hasta)}
                    </TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                      {pesos(f.total, f.moneda)}
                    </TableCell>
                    <TableCell align="right" sx={{
                      fontVariantNumeric: 'tabular-nums',
                      color: Number(f.acreditado) > 0 ? ESTADO.alerta : PALETA.acero,
                    }}>
                      {Number(f.acreditado) > 0 ? `−${pesos(f.acreditado, f.moneda)}` : '—'}
                    </TableCell>
                    <TableCell align="right" sx={{
                      fontVariantNumeric: 'tabular-nums',
                      color: Number(f.pagado) > 0 ? ESTADO.exito : PALETA.acero,
                    }}>
                      {Number(f.pagado) > 0 ? `−${pesos(f.pagado, f.moneda)}` : '—'}
                    </TableCell>
                    <TableCell align="right" sx={{
                      fontWeight: 800, fontVariantNumeric: 'tabular-nums',
                      color: Number(f.saldo) > 0 ? ESTADO.peligro : ESTADO.exito,
                    }}>
                      {pesos(f.saldo, f.moneda)}
                    </TableCell>
                    <TableCell align="right">
                      {!f.anulada && (
                        <>
                          <Tooltip title="Emitir nota crédito sobre esta factura">
                            <IconButton size="small" onClick={() => setNotaSobre(f)}>
                              <Undo fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Anular (conserva el número)">
                            <IconButton size="small" onClick={() => anular.mutate(f.id)}>
                              <Block fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </>
                      )}
                    </TableCell>
                  </TableRow>

                  {suyas.length > 0 && (
                    <TableRow>
                      <TableCell colSpan={8} sx={{ py: 0, borderBottom: desplegada ? undefined : 'none' }}>
                        <Collapse in={desplegada} unmountOnExit>
                          <Box sx={{ py: 1.5, pl: 4 }}>
                            {suyas.map(n => (
                              <Stack key={n.id} direction="row" spacing={2} alignItems="baseline"
                                sx={{ py: 0.5 }}>
                                <Typography variant="body2" sx={{
                                  fontFamily: 'monospace', fontWeight: 700, minWidth: 110,
                                }}>
                                  {n.numero}
                                </Typography>
                                <Typography variant="body2" sx={{
                                  color: ESTADO.alerta, fontWeight: 700, minWidth: 110,
                                }}>
                                  −{pesos(n.valor)}
                                </Typography>
                                <Typography variant="body2" sx={{ color: PALETA.grafito }}>
                                  {dia(n.fecha)} · {n.motivo}
                                </Typography>
                              </Stack>
                            ))}
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              )
            })}
            {facturas.length === 0 && (
              <TableRow>
                <TableCell colSpan={8}>
                  <Box sx={{ textAlign: 'center', py: 4, color: PALETA.acero }}>
                    <ReceiptLong sx={{ fontSize: 36, opacity: 0.4 }} />
                    <Typography variant="body2" mt={1}>Todavía no se ha facturado nada</Typography>
                    <Typography variant="caption">
                      La factura toma la tarifa del contrato; defínala primero si está en cero.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <DialogoFactura empresa={empresa} abierto={nueva} onCerrar={() => setNueva(false)} />
      <DialogoNota empresa={empresa} factura={notaSobre} onCerrar={() => setNotaSobre(null)} />
    </Box>
  )
}
