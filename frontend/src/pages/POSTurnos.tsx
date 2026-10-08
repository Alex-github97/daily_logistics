/**
 * POS · Turnos y arqueo
 *
 * El turno abierto muestra cuánto debería haber por medio de pago (base +
 * ventas − devoluciones ± movimientos de efectivo). Al cerrar, el cajero cuenta
 * lo que tiene; la diferencia queda registrada y, si la hay, debe explicarla.
 */
import { useState } from 'react'
import {
  Box, Paper, Typography, Button, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, Alert, Chip,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { AccountBalanceWallet, Lock, SwapVert } from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { pos, pesos } from '@/api/pos'
import { Encabezado, TablaRegistros, Cifra, errorApi } from '@/components/comun/Registro'
import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'

const COLOR = COLOR_MODULO

export default function POSTurnos() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const turno = useQuery({ queryKey: ['pos', 'turno'], queryFn: pos.turnoActual })
  const historial = useQuery({ queryKey: ['pos', 'turnos'], queryFn: () => pos.turnos() })
  const medios = useQuery({ queryKey: ['pos', 'medios'], queryFn: pos.medios, staleTime: Infinity })
  const nombre = (m: string) => medios.data?.find(x => x.valor === m)?.nombre ?? m
  const t = turno.data
  const [mov, setMov] = useState(false)
  const [m, setM] = useState({ tipo: 'RETIRO', monto: '', motivo: '' })
  const [cerrar, setCerrar] = useState(false)
  const [contado, setContado] = useState<Record<string, string>>({})
  const [obs, setObs] = useState('')
  const refrescar = () => qc.invalidateQueries({ queryKey: ['pos'] })

  const registrarMov = async () => {
    try { await pos.movimientoCaja(t!.id, { tipo: m.tipo, monto: Number(m.monto), motivo: m.motivo }); toast.success('Movimiento registrado'); setMov(false); setM({ tipo: 'RETIRO', monto: '', motivo: '' }); refrescar() }
    catch (e) { toast.error(errorApi(e)) }
  }
  const esperado = t?.resumen.esperado ?? {}
  const diferencias = Object.fromEntries(Object.keys(esperado).map(k => [k, (Number(contado[k] ?? 0) || 0) - esperado[k]]))
  const hayDiferencia = Object.values(diferencias).some(v => Math.abs(v) >= 0.01)
  const cerrarTurno = async () => {
    try {
      const r = await pos.cerrarTurno(t!.id, { contado: Object.fromEntries(Object.entries(contado).map(([k, v]) => [k, Number(v) || 0])), observaciones: obs || undefined })
      toast.success(r.diferencia ? `Turno cerrado con diferencia de ${pesos(r.diferencia)}` : 'Turno cerrado y cuadrado')
      setCerrar(false); setContado({}); setObs(''); refrescar()
    } catch (e) { toast.error(errorApi(e)) }
  }

  return (
    <Layout>
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<AccountBalanceWallet sx={{ fontSize: 28 }} />} titulo="Turnos y arqueo" subtitulo="POS · Apertura, movimientos de efectivo y cierre" color={COLOR} />
        {!t ? (
          <Alert severity="info" sx={{ mb: 3 }} action={<Button onClick={() => nav('/pos')}>Abrir turno</Button>}>No tiene un turno abierto.</Alert>
        ) : (
          <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, mb: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 2 }}>
              <Typography sx={{ fontWeight: 800, fontSize: 18 }}>{t.caja_nombre}</Typography>
              <Chip size="small" color="success" label="Abierto" />
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>desde {aFecha(t.apertura).toLocaleString('es-CO')} · base {pesos(t.base_inicial)}</Typography>
              <Box sx={{ flex: 1 }} />
              <Button startIcon={<SwapVert />} onClick={() => setMov(true)}>Entrada / salida de efectivo</Button>
              <Button variant="contained" startIcon={<Lock />} onClick={() => setCerrar(true)} sx={{ bgcolor: COLOR }}>Cerrar turno</Button>
            </Box>
            <Grid container spacing={2}>
              <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Ventas" valor={t.resumen.ventas} color={COLOR} /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Vendido" valor={pesos(t.resumen.total_ventas)} color="#15803D" /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Devoluciones" valor={pesos(t.resumen.total_devoluciones)} color="#DC2626" /></Grid>
              <Grid size={{ xs: 6, md: 3 }}><Cifra etiqueta="Efectivo esperado en caja" valor={pesos(esperado.EFECTIVO)} color="#0369A1" /></Grid>
            </Grid>
            <Typography sx={{ fontWeight: 700, fontSize: 13, mt: 2, mb: 0.5 }}>Esperado por medio de pago</Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {Object.entries(esperado).map(([k, v]) => <Chip key={k} label={`${nombre(k)}: ${pesos(v)}`} />)}
            </Box>
          </Paper>
        )}
        <Typography sx={{ fontWeight: 700, mb: 1 }}>Historial de turnos</Typography>
        <TablaRegistros filas={historial.data ?? []} cargando={historial.isLoading} vacio="Sin turnos" etiqueta={(x: any) => `turno ${x.id}`}
          columnas={[
            { titulo: 'Caja', valor: (x: any) => x.caja_nombre },
            { titulo: 'Cajero', valor: (x: any) => x.cajero },
            { titulo: 'Apertura', valor: (x: any) => aFecha(x.apertura).toLocaleString('es-CO') },
            { titulo: 'Cierre', valor: (x: any) => x.cierre ? aFecha(x.cierre).toLocaleString('es-CO') : 'Abierto' },
            { titulo: 'Ventas', valor: (x: any) => pesos(x.resumen.total_ventas), alinear: 'right' },
            { titulo: 'Diferencia', alinear: 'right', valor: (x: any) => x.diferencia == null ? '—'
              : <Box sx={{ color: Math.abs(x.diferencia) >= 0.01 ? '#DC2626' : '#15803D', fontWeight: 700 }}>{pesos(x.diferencia)}</Box> },
            { titulo: 'Observaciones', valor: (x: any) => x.observaciones ?? '' },
          ]} />

        <Dialog open={mov} onClose={() => setMov(false)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Movimiento de efectivo</DialogTitle>
          <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
            <TextField select size="small" label="Tipo" value={m.tipo} onChange={e => setM({ ...m, tipo: e.target.value })}>
              <MenuItem value="RETIRO">Salida (consignación, pago menor…)</MenuItem><MenuItem value="INGRESO">Entrada (cambio, sencillo…)</MenuItem>
            </TextField>
            <TextField size="small" type="number" label="Monto" value={m.monto} onChange={e => setM({ ...m, monto: e.target.value })} />
            <TextField size="small" label="Motivo" value={m.motivo} onChange={e => setM({ ...m, motivo: e.target.value })} />
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setMov(false)}>Cancelar</Button>
            <Button variant="contained" disabled={!(Number(m.monto) > 0) || m.motivo.trim().length < 3} onClick={registrarMov}>Registrar</Button></DialogActions>
        </Dialog>

        <Dialog open={cerrar} onClose={() => setCerrar(false)} maxWidth="sm" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>Arqueo y cierre</DialogTitle>
          <DialogContent>
            <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1.5 }}>Cuente lo que tiene por cada medio. El sistema compara contra lo esperado.</Typography>
            {Object.entries(esperado).map(([k, v]) => (
              <Box key={k} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                <Typography sx={{ width: 140, fontSize: 13.5 }}>{nombre(k)}</Typography>
                <Typography sx={{ width: 120, fontSize: 12.5, color: 'text.secondary' }}>esperado {pesos(v)}</Typography>
                <TextField size="small" type="number" label="Contado" value={contado[k] ?? ''} onChange={e => setContado({ ...contado, [k]: e.target.value })} sx={{ flex: 1 }} />
                <Typography sx={{ width: 110, fontSize: 12.5, textAlign: 'right', fontWeight: 700,
                  color: Math.abs(diferencias[k]) >= 0.01 ? '#DC2626' : '#15803D' }}>{contado[k] != null ? pesos(diferencias[k]) : ''}</Typography>
              </Box>
            ))}
            <TextField fullWidth multiline minRows={2} size="small" label={hayDiferencia ? 'Explique la diferencia (obligatorio)' : 'Observaciones'}
              value={obs} onChange={e => setObs(e.target.value)} sx={{ mt: 1 }} />
          </DialogContent>
          <DialogActions><Button color="inherit" onClick={() => setCerrar(false)}>Cancelar</Button>
            <Button variant="contained" disabled={hayDiferencia && !obs.trim()} onClick={cerrarTurno} sx={{ bgcolor: COLOR }}>Cerrar turno</Button></DialogActions>
        </Dialog>
      </Box>
    </Layout>
  )
}
