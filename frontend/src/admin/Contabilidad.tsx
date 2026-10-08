/**
 * La contabilidad de toda la plataforma, sin entrar cliente por cliente.
 *
 * Responde a lo que un operador mira primero: cuánto entra al mes, cuánto está
 * pendiente de cobro y quién debe. Los clientes vienen ordenados por saldo, así
 * que lo que hay que perseguir queda arriba.
 */
import { useState } from 'react'
import {
  Box, Card, Typography, Stack, Table, TableBody, TableCell, TableHead,
  TableRow, Chip, Skeleton, TextField, Divider, Tooltip, Alert,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { consolaApi } from './api'

const pesos = (v: string | number) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return new Intl.NumberFormat('es-CO', {
    style: 'currency', currency: 'COP', maximumFractionDigits: 0,
  }).format(n)
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
               'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

const nombreMes = (clave: string) => {
  const [a, m] = clave.split('-').map(Number)
  return Number.isFinite(m) ? `${MESES[m - 1]} ${a}` : clave
}

function Cifra({ etiqueta, valor, pie, color }: {
  etiqueta: string; valor: string; pie?: string; color?: string
}) {
  return (
    <Box sx={{ flex: 1, minWidth: 150 }}>
      <Typography variant="caption" color="text.secondary">{etiqueta}</Typography>
      <Typography variant="h6" fontWeight={800} sx={{
        fontVariantNumeric: 'tabular-nums', color: color ?? PALETA.tinta, lineHeight: 1.3,
      }}>
        {valor}
      </Typography>
      {pie && <Typography variant="caption" color="text.secondary">{pie}</Typography>}
    </Box>
  )
}

export default function Contabilidad() {
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['contabilidad', desde, hasta],
    queryFn: () => consolaApi.contabilidad(desde || undefined, hasta || undefined),
  })

  if (isLoading || !data) {
    return <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 3 }} />
  }

  // Para las barras del histórico: la escala la fija el mes más alto.
  const tope = Math.max(
    1, ...data.meses.map(m => Math.max(Number(m.facturado), Number(m.recaudado))))

  const conSaldo = data.clientes.filter(c => Number(c.saldo) > 0)

  return (
    <Box>
      <Stack direction="row" alignItems="flex-end" spacing={2} mb={2.5} flexWrap="wrap" useFlexGap>
        <Box sx={{ flex: 1, minWidth: 220 }}>
          <Typography variant="h6" fontWeight={800}>Contabilidad</Typography>
          <Typography variant="caption" color="text.secondary">
            Todas las empresas juntas · control interno, no facturación electrónica
          </Typography>
        </Box>
        <TextField
          label="Desde" type="date" size="small" value={desde}
          onChange={e => setDesde(e.target.value)} InputLabelProps={{ shrink: true }}
        />
        <TextField
          label="Hasta" type="date" size="small" value={hasta}
          onChange={e => setHasta(e.target.value)} InputLabelProps={{ shrink: true }}
        />
      </Stack>

      {/* Las cifras de arriba */}
      <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <Cifra etiqueta="Facturado" valor={pesos(data.facturado)}
            pie="sin las facturas anuladas" />
          <Divider orientation="vertical" flexItem />
          <Cifra etiqueta="Notas crédito" valor={pesos(data.acreditado)}
            color={Number(data.acreditado) > 0 ? ESTADO.alerta : undefined}
            pie="rebajado de lo facturado" />
          <Divider orientation="vertical" flexItem />
          <Cifra etiqueta="Recaudado" valor={pesos(data.recaudado)}
            color={ESTADO.exito} pie="pagos recibidos" />
          <Divider orientation="vertical" flexItem />
          <Cifra etiqueta="Por cobrar" valor={pesos(data.por_cobrar)}
            color={Number(data.por_cobrar) > 0 ? ESTADO.peligro : ESTADO.exito}
            pie="facturado − notas − recaudado" />
        </Stack>
        <Divider sx={{ my: 2 }} />
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <Cifra
            etiqueta="Ingreso recurrente mensual" valor={pesos(data.ingreso_recurrente)}
            color={COLOR_MODULO}
            pie={`suma de las tarifas de ${data.empresas_activas} empresas activas`}
          />
          <Divider orientation="vertical" flexItem />
          <Cifra
            etiqueta="Empresas en mora" valor={String(data.empresas_en_mora)}
            color={data.empresas_en_mora > 0 ? ESTADO.peligro : ESTADO.exito}
            pie="con facturas vencidas sin saldar"
          />
        </Stack>
      </Card>

      {/* Histórico por mes */}
      {data.meses.length > 0 && (
        <Card sx={{ borderRadius: 3, p: 2.5, mb: 2.5 }}>
          <Typography variant="subtitle2" fontWeight={800} mb={2}>Mes a mes</Typography>
          <Stack spacing={1.25}>
            {data.meses.map(m => (
              <Box key={m.mes}>
                <Stack direction="row" alignItems="baseline" spacing={1} mb={0.5}>
                  <Typography variant="caption" sx={{ minWidth: 62, fontWeight: 700 }}>
                    {nombreMes(m.mes)}
                  </Typography>
                  <Typography variant="caption" sx={{ color: COLOR_MODULO, fontWeight: 700 }}>
                    {pesos(m.facturado)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">facturado ·</Typography>
                  <Typography variant="caption" sx={{ color: ESTADO.exito, fontWeight: 700 }}>
                    {pesos(m.recaudado)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">recaudado</Typography>
                  {Number(m.acreditado) > 0 && (
                    <Typography variant="caption" sx={{ color: ESTADO.alerta, fontWeight: 700 }}>
                      · −{pesos(m.acreditado)} en notas
                    </Typography>
                  )}
                </Stack>
                <Stack spacing={0.4}>
                  <Tooltip title={`Facturado: ${pesos(m.facturado)}`}>
                    <Box sx={{
                      height: 7, borderRadius: 99, bgcolor: COLOR_MODULO,
                      width: `${(Number(m.facturado) / tope) * 100}%`, minWidth: 2,
                    }} />
                  </Tooltip>
                  <Tooltip title={`Recaudado: ${pesos(m.recaudado)}`}>
                    <Box sx={{
                      height: 7, borderRadius: 99, bgcolor: ESTADO.exito,
                      width: `${(Number(m.recaudado) / tope) * 100}%`, minWidth: 2,
                    }} />
                  </Tooltip>
                </Stack>
              </Box>
            ))}
          </Stack>
        </Card>
      )}

      {/* Por cliente */}
      <Card sx={{ borderRadius: 3 }}>
        <Stack sx={{ p: 2.5, pb: 1.5 }}>
          <Typography variant="subtitle2" fontWeight={800}>Por cliente</Typography>
          <Typography variant="caption" color="text.secondary">
            Ordenados por saldo: lo que hay que perseguir queda arriba
          </Typography>
        </Stack>

        {conSaldo.length === 0 && data.clientes.length > 0 && (
          <Alert severity="success" sx={{ mx: 2.5, mb: 2 }}>
            Ningún cliente tiene saldo pendiente.
          </Alert>
        )}

        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>EMPRESA</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">TARIFA</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">FACTURADO</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">NOTAS CR.</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">RECAUDADO</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">SALDO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>MORA</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.clientes.map(c => (
              <TableRow key={c.cliente_id} hover sx={{ opacity: c.activo ? 1 : 0.6 }}>
                <TableCell>
                  <Typography variant="body2" fontWeight={700}>{c.nombre}</Typography>
                  <Typography variant="caption" sx={{
                    fontFamily: 'monospace', color: PALETA.acero,
                  }}>
                    {c.codigo}{!c.activo && ' · suspendida'}
                  </Typography>
                </TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {Number(c.tarifa_mensual) > 0 ? pesos(c.tarifa_mensual) : '—'}
                </TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {pesos(c.facturado)}
                  <Typography variant="caption" color="text.secondary" display="block">
                    {c.facturas} {c.facturas === 1 ? 'factura' : 'facturas'}
                  </Typography>
                </TableCell>
                <TableCell align="right" sx={{
                  fontVariantNumeric: 'tabular-nums',
                  color: Number(c.acreditado) > 0 ? ESTADO.alerta : PALETA.acero,
                }}>
                  {Number(c.acreditado) > 0 ? `−${pesos(c.acreditado)}` : '—'}
                </TableCell>
                <TableCell align="right" sx={{
                  fontVariantNumeric: 'tabular-nums', color: ESTADO.exito,
                }}>
                  {pesos(c.recaudado)}
                </TableCell>
                <TableCell align="right" sx={{
                  fontWeight: 800, fontVariantNumeric: 'tabular-nums',
                  color: Number(c.saldo) > 0 ? ESTADO.peligro : PALETA.acero,
                }}>
                  {Number(c.saldo) > 0 ? pesos(c.saldo) : '—'}
                </TableCell>
                <TableCell>
                  {c.dias_mora > 0 ? (
                    <Chip label={`${c.dias_mora} días`} size="small" sx={{
                      fontWeight: 700, fontSize: 11,
                      bgcolor: `${ESTADO.peligro}1A`, color: ESTADO.peligro,
                    }} />
                  ) : (
                    <Typography variant="caption" sx={{ color: PALETA.acero }}>—</Typography>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data.clientes.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" sx={{ textAlign: 'center', py: 4, color: PALETA.acero }}>
                    Todavía no hay empresas
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </Box>
  )
}
