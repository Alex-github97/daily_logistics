import React, { useMemo, useState } from 'react'
import {
  Box, Paper, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, IconButton, Stack, Chip, Tooltip, Table, TableBody, TableCell, TableHead, TableRow, TableContainer, alpha, Divider, CircularProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import {
  AttachMoney, Add, Visibility, Send, CheckCircle, Cancel, CreditCard, ArrowForward, Download,
} from '@mui/icons-material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { Layout } from '@/components/layout/Layout'
import toast from 'react-hot-toast'
import { exportarPDF } from '@/utils/exportar'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO
const fmt = (n: number) => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(n || 0)

type LiqEstado = 'BORRADOR' | 'PENDIENTE' | 'APROBADA' | 'PAGADA' | 'RECHAZADA'

interface Liquidacion {
  id: number
  viaje_id: number
  viaje_codigo: string
  viaje_origen: string
  viaje_destino: string
  conductor: string
  periodo: string
  valor_flete: number
  bonificaciones: number
  descuentos: number
  anticipos: number
  total: number
  estado: LiqEstado
  fecha_pago?: string | null
  notas?: string | null
}

function estadoChip(estado: LiqEstado) {
  const map: Record<LiqEstado, { label: string; color: 'default' | 'warning' | 'primary' | 'success' | 'error' }> = {
    BORRADOR: { label: 'Borrador', color: 'default' },
    PENDIENTE: { label: 'Pendiente', color: 'warning' },
    APROBADA: { label: 'Aprobada', color: 'primary' },
    PAGADA: { label: 'Pagada', color: 'success' },
    RECHAZADA: { label: 'Rechazada', color: 'error' },
  }
  const m = map[estado] ?? { label: estado, color: 'default' as const }
  return <Chip label={m.label} color={m.color} size="small" />
}
const fmtFecha = (s?: string | null) => { if (!s) return '—'; const d = aFecha(s); return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('es-CO') }

export default function TMSLiquidaciones() {
  const qc = useQueryClient()
  const [filtroEstado, setFiltroEstado] = useState('')
  const [filtroConductor, setFiltroConductor] = useState('')
  const [openNueva, setOpenNueva] = useState(false)
  const [openVer, setOpenVer] = useState<Liquidacion | null>(null)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ viaje_id: '', conductor_hcm_id: '', conductor_nombre: '', periodo: '', valor_flete: 0, bonificaciones: 0, descuentos: 0, anticipos: 0, notas: '' })

  // El filtro va al servidor: filtrar en el navegador obliga a bajar el año
  // entero de liquidaciones para mostrar una pantalla.
  const { data: rawLiqs = [], isLoading } = useQuery<any[]>({
    queryKey: ['tms-liquidaciones', filtroEstado],
    queryFn: () => apiClient.get('/tms/liquidaciones', {
      params: { limite: 200, ...(filtroEstado ? { estado: filtroEstado } : {}) },
    }).then((r) => r.data),
  })

  // Los totales se cuentan en la base, no sumando la lista.
  //
  // Sumándola, los cuatro indicadores de arriba solo eran ciertos si la lista
  // venía completa —2.800 liquidaciones, casi un megabyte— y cualquier tope que
  // se le pusiera después los habría dejado mal sin que nadie lo notara: no
  // habrían desaparecido, habrían mentido.
  const { data: resumen } = useQuery<{
    cantidad_total: number; total_pendiente: number; total_pagado: number
    en_proceso: number; por_liquidar: number
  }>({
    queryKey: ['tms-liquidaciones-resumen'],
    queryFn: () => apiClient.get('/tms/liquidaciones/resumen').then((r) => r.data),
  })
  const { data: viajesData } = useQuery<{ items: any[] }>({ queryKey: ['tms-viajes'], queryFn: () => apiClient.get('/tms/viajes', { params: { per_page: 100 } }).then((r) => r.data) })
  const viajes = viajesData?.items ?? []

  const viajeMap = useMemo(() => { const m = new Map<number, any>(); viajes.forEach((v) => m.set(v.id, v)); return m }, [viajes])

  const liquidaciones: Liquidacion[] = useMemo(() => rawLiqs.map((l) => {
    const vj = viajeMap.get(l.viaje_id)
    return {
      id: l.id, viaje_id: l.viaje_id,
      viaje_codigo: vj?.codigo || `Viaje #${l.viaje_id}`,
      viaje_origen: vj?.origen_ciudad || '—', viaje_destino: vj?.destino_ciudad || '—',
      conductor: l.conductor_nombre || (vj?.conductor_nombre) || '—',
      periodo: l.periodo || '—',
      valor_flete: l.valor_flete, bonificaciones: l.bonificaciones, descuentos: l.descuentos, anticipos: l.anticipos,
      total: l.total_a_pagar, estado: l.estado, fecha_pago: l.pagado_en, notas: l.notas,
    }
  }), [rawLiqs, viajeMap])

  const conductores = [...new Set(liquidaciones.map((l) => l.conductor).filter((c) => c && c !== '—'))]

  const filtered = liquidaciones.filter((l) => {
    if (filtroEstado && l.estado !== filtroEstado) return false
    if (filtroConductor && l.conductor !== filtroConductor) return false
    return true
  })

  const totalPendiente = resumen?.total_pendiente ?? 0
  const totalPagado = resumen?.total_pagado ?? 0
  const enProceso = resumen?.en_proceso ?? 0
  const pendientesN = resumen?.por_liquidar ?? 0

  const refetch = () => {
    qc.invalidateQueries({ queryKey: ['tms-liquidaciones'] })
    // Aprobar o pagar mueve los totales, no solo la fila: sin esto los
    // indicadores de arriba se quedan con la cifra anterior.
    qc.invalidateQueries({ queryKey: ['tms-liquidaciones-resumen'] })
  }

  async function accion(l: Liquidacion, tipo: 'revisar' | 'aprobar' | 'rechazar' | 'pagar') {
    try {
      if (tipo === 'aprobar') await apiClient.post(`/tms/liquidaciones/${l.id}/aprobar`)
      else if (tipo === 'pagar') await apiClient.post(`/tms/liquidaciones/${l.id}/pagar`)
      else if (tipo === 'revisar') await apiClient.put(`/tms/liquidaciones/${l.id}`, { estado: 'PENDIENTE' })
      else if (tipo === 'rechazar') await apiClient.put(`/tms/liquidaciones/${l.id}`, { estado: 'RECHAZADA' })
      toast.success('Liquidación actualizada'); refetch()
    } catch (e: any) { toast.error(e.response?.data?.detail || 'No se pudo actualizar') }
  }

  async function guardarNueva() {
    if (!form.viaje_id) { toast.error('Seleccione un viaje'); return }
    setSaving(true)
    try {
      await apiClient.post('/tms/liquidaciones', {
        viaje_id: Number(form.viaje_id),
        conductor_hcm_id: form.conductor_hcm_id ? Number(form.conductor_hcm_id) : undefined,
        periodo: form.periodo || undefined,
        valor_flete: Number(form.valor_flete) || 0,
        bonificaciones: Number(form.bonificaciones) || 0,
        descuentos: Number(form.descuentos) || 0,
        anticipos: Number(form.anticipos) || 0,
        notas: form.notas || undefined,
      })
      toast.success('Liquidación creada como Borrador')
      setOpenNueva(false); refetch()
      setForm({ viaje_id: '', conductor_hcm_id: '', conductor_nombre: '', periodo: '', valor_flete: 0, bonificaciones: 0, descuentos: 0, anticipos: 0, notas: '' })
    } catch (e: any) { toast.error(e.response?.data?.detail || 'No se pudo crear') }
    finally { setSaving(false) }
  }

  const formTotal = Number(form.valor_flete) + Number(form.bonificaciones) - Number(form.descuentos) - Number(form.anticipos)

  return (
    <Layout>
      <Box sx={{ p: 3, bgcolor: '#F8FAFC', minHeight: '100vh' }}>
        {/* Header */}
        <Stack direction="row" alignItems="center" gap={1.5} mb={3}>
          <Box sx={{ bgcolor: alpha(TMS_COLOR, 0.1), borderRadius: 2, p: 1, display: 'flex' }}><CreditCard sx={{ color: TMS_COLOR, fontSize: 28 }} /></Box>
          <Box>
            <Typography variant="h5" fontWeight={700} color="#0F172A">Liquidaciones TMS</Typography>
            <Typography variant="body2" color="text.secondary">Liquidaciones de conductores y viajes</Typography>
          </Box>
        </Stack>

        {/* KPIs */}
        <Grid container spacing={2} mb={3}>
          {[
            { label: 'Total por Pagar', value: fmt(totalPendiente), color: '#D97706' },
            { label: 'Pagado (histórico)', value: fmt(totalPagado), color: '#059669' },
            { label: 'En Proceso', value: String(enProceso), color: TMS_COLOR },
            { label: 'Liquidaciones Pendientes', value: String(pendientesN), color: '#7C3AED' },
          ].map((kpi) => (
            <Grid key={kpi.label} size={{ xs: 12, sm: 6, md: 3 }}>
              <Paper elevation={0} sx={{ p: 2.5, border: `1px solid ${alpha(kpi.color, 0.3)}`, borderRadius: 2, bgcolor: alpha(kpi.color, 0.04) }}>
                <Typography fontSize={12} color="text.secondary">{kpi.label}</Typography>
                <Typography variant="h6" fontWeight={700} color={kpi.color}>{kpi.value}</Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>

        {/* Toolbar */}
        <Stack direction="row" gap={2} mb={2} flexWrap="wrap" alignItems="center">
          <Button variant="contained" startIcon={<Add />} onClick={() => setOpenNueva(true)} sx={{ bgcolor: TMS_COLOR }}>Nueva Liquidación</Button>
          <TextField select size="small" label="Estado" value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)} sx={{ minWidth: 150 }}>
            <MenuItem value="">Todos</MenuItem>
            {['BORRADOR', 'PENDIENTE', 'APROBADA', 'PAGADA', 'RECHAZADA'].map((e) => <MenuItem key={e} value={e}>{e}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Conductor" value={filtroConductor} onChange={(e) => setFiltroConductor(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">Todos</MenuItem>
            {conductores.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
          </TextField>
        </Stack>

        {/* Tabla */}
        <Paper elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2 }}>
          <TableContainer>
            <Table size="small">
              <TableHead sx={{ bgcolor: '#F8FAFC' }}>
                <TableRow>
                  {['ID', 'Viaje', 'Conductor', 'Período', 'Flete', 'Bonif.', 'Desc.', 'Anticipos', 'Total a Pagar', 'Estado', 'Acciones'].map((h, i) => (
                    <TableCell key={h} align={i >= 4 && i <= 8 ? 'right' : 'left'}><b>{h}</b></TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {isLoading ? (
                  <TableRow><TableCell colSpan={11} align="center" sx={{ py: 5 }}><CircularProgress size={26} /></TableCell></TableRow>
                ) : filtered.length === 0 ? (
                  <TableRow><TableCell colSpan={11} align="center" sx={{ py: 4, color: 'text.secondary' }}>{liquidaciones.length === 0 ? 'Aún no hay liquidaciones. Crea la primera.' : 'Sin resultados con los filtros aplicados.'}</TableCell></TableRow>
                ) : filtered.map((l) => (
                  <TableRow key={l.id} hover sx={{ cursor: 'pointer' }} onClick={() => setOpenVer(l)}>
                    <TableCell sx={{ fontSize: 12 }}>#{l.id}</TableCell>
                    <TableCell>
                      <Stack direction="row" alignItems="center" gap={0.4}>
                        <Typography fontSize={11} fontWeight={700}>{l.viaje_codigo}</Typography>
                        <ArrowForward sx={{ fontSize: 10, color: TMS_COLOR }} />
                        <Typography fontSize={10} color="text.secondary">{l.viaje_destino}</Typography>
                      </Stack>
                    </TableCell>
                    <TableCell sx={{ fontSize: 12 }}>{l.conductor}</TableCell>
                    <TableCell sx={{ fontSize: 12 }}>{l.periodo}</TableCell>
                    <TableCell align="right" sx={{ fontSize: 12 }}>{fmt(l.valor_flete)}</TableCell>
                    <TableCell align="right" sx={{ fontSize: 12, color: 'success.main' }}>{l.bonificaciones > 0 ? `+${fmt(l.bonificaciones)}` : '—'}</TableCell>
                    <TableCell align="right" sx={{ fontSize: 12, color: l.descuentos > 0 ? 'error.main' : 'text.primary' }}>{l.descuentos > 0 ? `-${fmt(l.descuentos)}` : '—'}</TableCell>
                    <TableCell align="right" sx={{ fontSize: 12, color: l.anticipos > 0 ? 'warning.main' : 'text.primary' }}>{l.anticipos > 0 ? `-${fmt(l.anticipos)}` : '—'}</TableCell>
                    <TableCell align="right"><Typography fontSize={12} fontWeight={700} color={TMS_COLOR}>{fmt(l.total)}</Typography></TableCell>
                    <TableCell>{estadoChip(l.estado)}</TableCell>
                    <TableCell onClick={(ev) => ev.stopPropagation()}>
                      <Stack direction="row" gap={0.3}>
                        <Tooltip title="Ver detalle"><IconButton size="small" onClick={() => setOpenVer(l)}><Visibility fontSize="small" /></IconButton></Tooltip>
                        {l.estado === 'BORRADOR' && <Tooltip title="Enviar a Revisión"><IconButton size="small" onClick={() => accion(l, 'revisar')} sx={{ color: 'warning.main' }}><Send fontSize="small" /></IconButton></Tooltip>}
                        {l.estado === 'PENDIENTE' && (
                          <>
                            <Tooltip title="Aprobar"><IconButton size="small" onClick={() => accion(l, 'aprobar')} sx={{ color: 'primary.main' }}><CheckCircle fontSize="small" /></IconButton></Tooltip>
                            <Tooltip title="Rechazar"><IconButton size="small" onClick={() => accion(l, 'rechazar')} sx={{ color: 'error.main' }}><Cancel fontSize="small" /></IconButton></Tooltip>
                          </>
                        )}
                        {l.estado === 'APROBADA' && <Tooltip title="Marcar como Pagada"><IconButton size="small" onClick={() => accion(l, 'pagar')} sx={{ color: 'success.main' }}><AttachMoney fontSize="small" /></IconButton></Tooltip>}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        {/* ── Dialog Nueva Liquidación ── */}
        <Dialog open={openNueva} onClose={() => setOpenNueva(false)} maxWidth="sm" fullWidth>
          <DialogTitle>Nueva Liquidación</DialogTitle>
          <DialogContent>
            <Stack gap={2} mt={1}>
              <TextField select label="Viaje *" value={form.viaje_id} onChange={(e) => {
                const v = viajeMap.get(Number(e.target.value))
                setForm((f) => ({ ...f, viaje_id: e.target.value, conductor_hcm_id: v?.conductor_hcm_id ? String(v.conductor_hcm_id) : '', conductor_nombre: v?.conductor_nombre || '', valor_flete: v?.valor_flete || f.valor_flete }))
              }}>
                {viajes.length === 0 && <MenuItem value="" disabled>No hay viajes disponibles</MenuItem>}
                {viajes.map((v) => <MenuItem key={v.id} value={String(v.id)}>{v.codigo} | {v.origen_ciudad || '—'} → {v.destino_ciudad || '—'}</MenuItem>)}
              </TextField>
              <TextField label="Conductor" value={form.conductor_nombre} disabled />
              <TextField label="Período (ej: 2026-08)" value={form.periodo} onChange={(e) => setForm((f) => ({ ...f, periodo: e.target.value }))} />
              <Stack direction="row" gap={2}>
                <TextField label="Valor Flete" type="number" value={form.valor_flete} onChange={(e) => setForm((f) => ({ ...f, valor_flete: Number(e.target.value) }))} fullWidth />
                <TextField label="Bonificaciones" type="number" value={form.bonificaciones} onChange={(e) => setForm((f) => ({ ...f, bonificaciones: Number(e.target.value) }))} fullWidth />
              </Stack>
              <Stack direction="row" gap={2}>
                <TextField label="Descuentos" type="number" value={form.descuentos} onChange={(e) => setForm((f) => ({ ...f, descuentos: Number(e.target.value) }))} fullWidth />
                <TextField label="Anticipos" type="number" value={form.anticipos} onChange={(e) => setForm((f) => ({ ...f, anticipos: Number(e.target.value) }))} fullWidth />
              </Stack>
              <Divider />
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography fontWeight={700}>Total a Pagar:</Typography>
                <Typography fontWeight={700} fontSize={18} color={formTotal >= 0 ? TMS_COLOR : 'error.main'}>{fmt(formTotal)}</Typography>
              </Stack>
              <TextField label="Notas" multiline rows={2} value={form.notas} onChange={(e) => setForm((f) => ({ ...f, notas: e.target.value }))} />
              <Typography fontSize={11} color="text.secondary">Estado inicial: BORRADOR</Typography>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpenNueva(false)} disabled={saving}>Cancelar</Button>
            <Button variant="contained" onClick={guardarNueva} disabled={saving} sx={{ bgcolor: TMS_COLOR }}>{saving ? 'Creando…' : 'Crear Liquidación'}</Button>
          </DialogActions>
        </Dialog>

        {/* ── Dialog Ver Liquidación ── */}
        <Dialog open={!!openVer} onClose={() => setOpenVer(null)} maxWidth="sm" fullWidth>
          {openVer && (
            <>
              <DialogTitle>Liquidación #{openVer.id}</DialogTitle>
              <DialogContent>
                <Stack gap={1.5}>
                  <Stack direction="row" justifyContent="space-between"><Typography color="text.secondary" fontSize={13}>Viaje:</Typography><Typography fontWeight={600} fontSize={13}>{openVer.viaje_codigo} | {openVer.viaje_origen} → {openVer.viaje_destino}</Typography></Stack>
                  <Stack direction="row" justifyContent="space-between"><Typography color="text.secondary" fontSize={13}>Conductor:</Typography><Typography fontWeight={600} fontSize={13}>{openVer.conductor}</Typography></Stack>
                  <Stack direction="row" justifyContent="space-between"><Typography color="text.secondary" fontSize={13}>Período:</Typography><Typography fontWeight={600} fontSize={13}>{openVer.periodo}</Typography></Stack>
                  <Stack direction="row" justifyContent="space-between"><Typography color="text.secondary" fontSize={13}>Estado:</Typography>{estadoChip(openVer.estado)}</Stack>
                  {openVer.fecha_pago && <Stack direction="row" justifyContent="space-between"><Typography color="text.secondary" fontSize={13}>Fecha de Pago:</Typography><Typography fontWeight={600} fontSize={13}>{fmtFecha(openVer.fecha_pago)}</Typography></Stack>}
                  <Divider />
                  {[
                    { label: 'Valor Flete', value: fmt(openVer.valor_flete), color: 'text.primary' },
                    { label: 'Bonificaciones', value: `+${fmt(openVer.bonificaciones)}`, color: 'success.main' },
                    { label: 'Descuentos', value: `-${fmt(openVer.descuentos)}`, color: 'error.main' },
                    { label: 'Anticipos', value: `-${fmt(openVer.anticipos)}`, color: 'warning.main' },
                  ].map((row) => (
                    <Stack key={row.label} direction="row" justifyContent="space-between"><Typography fontSize={13}>{row.label}</Typography><Typography fontSize={13} color={row.color}>{row.value}</Typography></Stack>
                  ))}
                  <Divider />
                  <Stack direction="row" justifyContent="space-between"><Typography fontWeight={700}>Total a Pagar:</Typography><Typography fontWeight={700} fontSize={16} color={TMS_COLOR}>{fmt(openVer.total)}</Typography></Stack>
                  {openVer.notas && <Typography fontSize={12} color="text.secondary" mt={1}><b>Notas:</b> {openVer.notas}</Typography>}
                </Stack>
              </DialogContent>
              <DialogActions>
                <Button startIcon={<Download />} onClick={() => exportarPDF({
                  archivo: `liquidacion-${openVer.viaje_codigo}`,
                  titulo: `Liquidación ${openVer.viaje_codigo}`,
                  subtitulo: `${openVer.conductor} · ${openVer.periodo}`,
                  color: TMS_COLOR,
                  columnas: [{ key: 'campo', header: 'Concepto' }, { key: 'valor', header: 'Valor' }],
                  filas: [
                    { campo: 'Viaje', valor: `${openVer.viaje_codigo} | ${openVer.viaje_origen} → ${openVer.viaje_destino}` },
                    { campo: 'Conductor', valor: openVer.conductor },
                    { campo: 'Período', valor: openVer.periodo },
                    { campo: 'Estado', valor: openVer.estado },
                    { campo: 'Fecha de pago', valor: fmtFecha(openVer.fecha_pago) },
                    { campo: 'Valor flete', valor: fmt(openVer.valor_flete) },
                    { campo: 'Bonificaciones', valor: `+${fmt(openVer.bonificaciones)}` },
                    { campo: 'Descuentos', valor: `-${fmt(openVer.descuentos)}` },
                    { campo: 'Anticipos', valor: `-${fmt(openVer.anticipos)}` },
                    { campo: 'Total a pagar', valor: fmt(openVer.total) },
                  ],
                })}>Descargar</Button>
                <Button onClick={() => setOpenVer(null)}>Cerrar</Button>
              </DialogActions>
            </>
          )}
        </Dialog>
      </Box>
    </Layout>
  )
}
