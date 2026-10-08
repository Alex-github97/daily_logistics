/**
 * TMS · Documentos y pruebas de entrega
 *
 * Era una maqueta: dos viajes con documentos escritos a mano, una búsqueda
 * que solo encontraba esos dos, y «Guardar» y «Registrar POD» que mostraban
 * el aviso sin guardar nada.
 *
 * Ahora se elige cualquier viaje real y se le registran documentos y la
 * prueba de entrega con los mismos formularios del detalle del viaje: una sola
 * forma de hacerlo, aunque se llegue por dos caminos. Qué le falta a cada
 * viaje lo calcula el servidor según su estado.
 */
import { useState } from 'react'
import {
  Box, Paper, Typography, Stack, Tabs, Tab, Chip, Button, Autocomplete, TextField,
  Table, TableBody, TableCell, TableHead, TableRow, TableContainer, alpha, LinearProgress, Divider,
} from '@mui/material'
import { Description, ArrowForward, Warning } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { tmsApi, type ViajeResumen } from '@/api/tms'
import { DocumentosTab, EntregaTab } from '@/components/tms/ViajeDetalle'

import { COLOR_MODULO } from '@/config/marca'
import { aFecha } from '@/utils/fechas'
const TMS_COLOR = COLOR_MODULO
const fmtFecha = (s?: string | null) => (s ? aFecha(s).toLocaleString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')
const VIVO = new Set(['PROGRAMADO', 'ASIGNADO', 'EN_TRANSITO', 'ENTREGADO'])

export default function TMSDocumentos() {
  const [tab, setTab] = useState(0)
  const [viaje, setViaje] = useState<ViajeResumen | null>(null)

  const { data: viajesResp, isLoading: cargandoViajes } = useQuery({ queryKey: ['tms-viajes-docs'], queryFn: () => tmsApi.viajes() })
  const viajes = viajesResp?.items ?? []
  const { data: pods = [], isLoading: cargandoPods } = useQuery({ queryKey: ['tms-pods'], queryFn: tmsApi.pods })
  const { data: pendientes = [], isLoading: cargandoPend } = useQuery({ queryKey: ['tms-docs-pendientes'], queryFn: tmsApi.pendientesDocs })

  // El viaje puede no estar entre los últimos cien de la lista: se trae aparte.
  const irAViaje = async (id: number) => {
    setViaje(viajes.find(x => x.id === id) ?? await tmsApi.viaje(id))
    setTab(0)
  }

  return (
    <Layout>
      <Box sx={{ p: 3 }}>
        <Stack direction="row" alignItems="center" gap={1.5} mb={3}>
          <Box sx={{ bgcolor: alpha(TMS_COLOR, 0.1), borderRadius: 2, p: 1, display: 'flex' }}><Description sx={{ color: TMS_COLOR, fontSize: 28 }} /></Box>
          <Box>
            <Typography variant="h5" fontWeight={700}>Documentos de transporte</Typography>
            <Typography variant="body2" color="text.secondary">Remesas, manifiestos, cumplidos y pruebas de entrega por viaje</Typography>
          </Box>
          {pendientes.length > 0 && <Chip icon={<Warning />} label={`${pendientes.length} viajes con documentos pendientes`} sx={{ ml: 'auto', bgcolor: '#FEF3C7', color: '#B45309', fontWeight: 700 }} />}
        </Stack>

        <Paper elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: '1px solid #E2E8F0', px: 2 }}>
            <Tab label="Documentos por viaje" />
            <Tab label={`Pruebas de entrega (${pods.length})`} />
            <Tab label={`Pendientes (${pendientes.length})`} />
          </Tabs>

          {tab === 0 && (
            <Box sx={{ p: 2.5 }}>
              <Autocomplete
                options={viajes} loading={cargandoViajes} value={viaje} onChange={(_, v) => setViaje(v)}
                getOptionLabel={v => `${v.codigo} · ${v.origen_ciudad ?? '—'} → ${v.destino_ciudad ?? '—'}`}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                renderInput={p => <TextField {...p} size="small" label="Buscar viaje por código o ciudad" />}
                sx={{ maxWidth: 520, mb: 2 }}
              />
              {!viaje ? (
                <Typography fontSize={13} color="text.secondary">Elige un viaje para ver y registrar sus documentos.</Typography>
              ) : (
                <>
                  <Paper elevation={0} sx={{ p: 2, bgcolor: alpha(TMS_COLOR, 0.04), border: `1px solid ${alpha(TMS_COLOR, 0.15)}`, borderRadius: 2, mb: 2 }}>
                    <Stack direction="row" gap={3} flexWrap="wrap">
                      {[['Viaje', viaje.codigo], ['Estado', viaje.estado], ['Ruta', `${viaje.origen_ciudad ?? '—'} → ${viaje.destino_ciudad ?? '—'}`],
                        ['Conductor', viaje.conductor_nombre ?? '—'], ['Vehículo', viaje.vehiculo_placa ?? '—']].map(([l, v]) => (
                        <Box key={l}><Typography fontSize={11} color="text.secondary">{l}</Typography><Typography fontSize={13} fontWeight={600}>{v}</Typography></Box>
                      ))}
                    </Stack>
                  </Paper>
                  <Typography fontWeight={700} fontSize={14}>Documentos</Typography>
                  <DocumentosTab key={`d${viaje.id}`} viaje={viaje} editable={VIVO.has(viaje.estado)} />
                  <Divider sx={{ my: 2 }} />
                  <Typography fontWeight={700} fontSize={14}>Prueba de entrega</Typography>
                  <EntregaTab key={`p${viaje.id}`} viaje={viaje} editable={VIVO.has(viaje.estado)} />
                </>
              )}
            </Box>
          )}

          {tab === 1 && (
            <Box sx={{ p: 2 }}>
              {cargandoPods && <LinearProgress />}
              <TableContainer>
                <Table size="small">
                  <TableHead sx={{ bgcolor: '#F8FAFC' }}>
                    <TableRow><TableCell><b>Viaje</b></TableCell><TableCell><b>Destino</b></TableCell><TableCell><b>Conductor</b></TableCell>
                      <TableCell><b>Recibió</b></TableCell><TableCell><b>Fecha y hora</b></TableCell><TableCell><b>Observaciones</b></TableCell><TableCell /></TableRow>
                  </TableHead>
                  <TableBody>
                    {!cargandoPods && pods.length === 0 && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>Todavía no hay pruebas de entrega registradas</TableCell></TableRow>}
                    {pods.map(p => (
                      <TableRow key={p.id} hover>
                        <TableCell><b>{p.codigo_viaje}</b></TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{p.destino ?? '—'}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{p.conductor ?? '—'}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{p.receptor_nombre ?? '—'}{p.receptor_documento ? ` (${p.receptor_documento})` : ''}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{fmtFecha(p.fecha_hora)}</TableCell>
                        <TableCell sx={{ fontSize: 12, maxWidth: 240 }}>{p.observaciones ?? '—'}</TableCell>
                        <TableCell>{p.foto_url && <Button size="small" href={p.foto_url} target="_blank" rel="noopener">Foto</Button>}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {tab === 2 && (
            <Box sx={{ p: 2 }}>
              {cargandoPend && <LinearProgress />}
              <Typography fontSize={12} color="text.secondary" mb={1.5}>
                Antes de salir, un viaje necesita remesa y manifiesto; entregado, además el cumplido y la prueba de entrega.
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead sx={{ bgcolor: '#F8FAFC' }}>
                    <TableRow><TableCell><b>Viaje</b></TableCell><TableCell><b>Estado</b></TableCell><TableCell><b>Ruta</b></TableCell>
                      <TableCell><b>Cargue</b></TableCell><TableCell><b>Faltan</b></TableCell><TableCell /></TableRow>
                  </TableHead>
                  <TableBody>
                    {!cargandoPend && pendientes.length === 0 && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>Ningún viaje tiene documentos pendientes</TableCell></TableRow>}
                    {pendientes.map(p => (
                      <TableRow key={p.viaje_id} hover>
                        <TableCell><b>{p.codigo}</b></TableCell>
                        <TableCell><Chip label={p.estado} size="small" sx={{ fontSize: 11 }} /></TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{p.origen} → {p.destino}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{fmtFecha(p.fecha_programada)}</TableCell>
                        <TableCell><Stack direction="row" gap={0.5} flexWrap="wrap">{p.faltantes.map(f => <Chip key={f} label={f} size="small" color="warning" variant="outlined" sx={{ fontSize: 10.5 }} />)}</Stack></TableCell>
                        <TableCell><Button size="small" endIcon={<ArrowForward />} onClick={() => irAViaje(p.viaje_id)} sx={{ color: TMS_COLOR }}>Completar</Button></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </Paper>
      </Box>
    </Layout>
  )
}
