/**
 * Con quién se habla en esa empresa y qué papeles hay firmados.
 *
 * Los documentos guardan la referencia y la fecha de vencimiento, no el archivo:
 * lo que un operador necesita saber de un contrato es que existe y cuándo se le
 * acaba, y eso debe verse sin abrir nada.
 */
import { useState } from 'react'
import {
  Box, Card, Typography, Stack, Button, Table, TableBody, TableCell, TableHead, TableRow, IconButton, Tooltip, Chip, Dialog, DialogTitle, DialogContent, DialogActions, FormControlLabel, Checkbox, MenuItem,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { Add, Delete, Star } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { consolaApi, mensajeDeError, type Empresa, type Contacto, type Documento } from './api'

const TIPOS_DOC = ['Contrato', 'RUT', 'Cámara de Comercio', 'Acuerdo de confidencialidad',
                   'Orden de compra', 'Otro']

const dia = (f?: string | null) => {
  if (!f) return '—'
  const [a, m, d] = f.split('-').map(Number)
  return Number.isFinite(a) ? `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${a}` : f
}

/** Días que faltan para una fecha; negativo si ya pasó. */
const diasHasta = (f?: string | null): number | null => {
  if (!f) return null
  const [a, m, d] = f.split('-').map(Number)
  if (!Number.isFinite(a)) return null
  const objetivo = new Date(a, m - 1, d)
  const hoy = new Date()
  hoy.setHours(0, 0, 0, 0)
  return Math.round((objetivo.getTime() - hoy.getTime()) / 86400000)
}

const CONTACTO_VACIO = (): Contacto =>
  ({ nombre: '', cargo: '', email: '', telefono: '', principal: false, notas: '' })

const DOC_VACIO = (): Documento =>
  ({ tipo: 'Contrato', nombre: '', vence: '', notas: '' })

// ─── Contactos ────────────────────────────────────────────────────────────────

function DialogoContacto({
  empresa, abierto, onCerrar,
}: { empresa: Empresa; abierto: boolean; onCerrar: () => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState<Contacto>(CONTACTO_VACIO())

  const crear = useMutation({
    mutationFn: () => consolaApi.crearContacto(empresa.id, f),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contactos', empresa.id] })
      setF(CONTACTO_VACIO()); onCerrar(); toast.success('Contacto agregado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const set = (k: keyof Contacto) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Nuevo contacto</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="Nombre" value={f.nombre} onChange={set('nombre')} fullWidth required />
          <TextField label="Cargo" value={f.cargo ?? ''} onChange={set('cargo')} fullWidth />
          <Stack direction="row" spacing={2}>
            <TextField label="Correo" value={f.email ?? ''} onChange={set('email')} fullWidth />
            <TextField label="Teléfono" value={f.telefono ?? ''} onChange={set('telefono')} fullWidth />
          </Stack>
          <FormControlLabel
            control={
              <Checkbox
                checked={f.principal}
                onChange={e => setF(p => ({ ...p, principal: e.target.checked }))}
              />
            }
            label={
              <Typography variant="body2">
                Es el contacto principal
                <Typography variant="caption" color="text.secondary" display="block">
                  Solo puede haber uno: marcarlo aquí se lo quita al que lo tenga.
                </Typography>
              </Typography>
            }
          />
          <TextField label="Notas" value={f.notas ?? ''} onChange={set('notas')}
            fullWidth multiline rows={2} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" onClick={() => crear.mutate()}
          disabled={crear.isPending || !f.nombre.trim()}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Agregar
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Documentos ───────────────────────────────────────────────────────────────

function DialogoDocumento({
  empresa, abierto, onCerrar,
}: { empresa: Empresa; abierto: boolean; onCerrar: () => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState<Documento>(DOC_VACIO())

  const crear = useMutation({
    mutationFn: () => consolaApi.crearDocumento(empresa.id, { ...f, vence: f.vence || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documentos', empresa.id] })
      setF(DOC_VACIO()); onCerrar(); toast.success('Documento registrado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const set = (k: keyof Documento) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Registrar documento</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField select label="Tipo" value={f.tipo ?? ''} onChange={set('tipo')} fullWidth>
            {TIPOS_DOC.map(t => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </TextField>
          <TextField label="Nombre" value={f.nombre} onChange={set('nombre')} fullWidth required
            placeholder="Contrato marco 2026" />
          <TextField
            label="Vence" type="date" value={f.vence ?? ''} onChange={set('vence')}
            fullWidth InputLabelProps={{ shrink: true }}
            helperText="Deje vacío si no vence"
          />
          <TextField label="Notas" value={f.notas ?? ''} onChange={set('notas')}
            fullWidth multiline rows={2} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" onClick={() => crear.mutate()}
          disabled={crear.isPending || !f.nombre.trim()}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Registrar
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── La pestaña ───────────────────────────────────────────────────────────────

export default function Directorio({ empresa }: { empresa: Empresa }) {
  const qc = useQueryClient()
  const [nuevoContacto, setNuevoContacto] = useState(false)
  const [nuevoDoc, setNuevoDoc] = useState(false)

  const { data: contactos = [] } = useQuery({
    queryKey: ['contactos', empresa.id], queryFn: () => consolaApi.contactos(empresa.id),
  })
  const { data: documentos = [] } = useQuery({
    queryKey: ['documentos', empresa.id], queryFn: () => consolaApi.documentos(empresa.id),
  })

  const borrarContacto = useMutation({
    mutationFn: (id: number) => consolaApi.borrarContacto(empresa.id, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contactos', empresa.id] }); toast.success('Contacto eliminado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })
  const borrarDoc = useMutation({
    mutationFn: (id: number) => consolaApi.borrarDocumento(empresa.id, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documentos', empresa.id] }); toast.success('Documento eliminado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  return (
    <Box>
      <Card sx={{ borderRadius: 3, mb: 2.5 }}>
        <Stack direction="row" alignItems="center" sx={{ p: 2.5, pb: 1.5 }}>
          <Typography variant="subtitle2" fontWeight={800} sx={{ flex: 1 }}>Contactos</Typography>
          <Button startIcon={<Add />} size="small" variant="contained"
            onClick={() => setNuevoContacto(true)} sx={{ textTransform: 'none', fontWeight: 700 }}>
            Nuevo contacto
          </Button>
        </Stack>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>NOMBRE</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>CARGO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>CORREO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>TELÉFONO</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {contactos.map(c => (
              <TableRow key={c.id} hover>
                <TableCell sx={{ fontWeight: 700 }}>
                  {c.principal && (
                    <Tooltip title="Contacto principal">
                      <Star sx={{ fontSize: 15, color: COLOR_MODULO, mr: 0.5, verticalAlign: -2 }} />
                    </Tooltip>
                  )}
                  {c.nombre}
                </TableCell>
                <TableCell sx={{ color: PALETA.grafito }}>{c.cargo ?? '—'}</TableCell>
                <TableCell sx={{ color: PALETA.grafito }}>{c.email ?? '—'}</TableCell>
                <TableCell sx={{ color: PALETA.grafito }}>{c.telefono ?? '—'}</TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={() => c.id && borrarContacto.mutate(c.id)}>
                    <Delete fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
            {contactos.length === 0 && (
              <TableRow><TableCell colSpan={5}>
                <Typography variant="body2" sx={{ textAlign: 'center', py: 3, color: PALETA.acero }}>
                  Sin contactos registrados
                </Typography>
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <Card sx={{ borderRadius: 3 }}>
        <Stack direction="row" alignItems="center" sx={{ p: 2.5, pb: 1.5 }}>
          <Typography variant="subtitle2" fontWeight={800} sx={{ flex: 1 }}>Documentos</Typography>
          <Button startIcon={<Add />} size="small" variant="contained"
            onClick={() => setNuevoDoc(true)} sx={{ textTransform: 'none', fontWeight: 700 }}>
            Registrar documento
          </Button>
        </Stack>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>TIPO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>NOMBRE</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>VENCE</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {documentos.map(d => {
              const dias = diasHasta(d.vence)
              return (
                <TableRow key={d.id} hover>
                  <TableCell>
                    <Chip label={d.tipo ?? 'Otro'} size="small" variant="outlined" sx={{ fontSize: 11 }} />
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>{d.nombre}</TableCell>
                  <TableCell>
                    {dias === null ? (
                      <Typography variant="body2" sx={{ color: PALETA.acero }}>No vence</Typography>
                    ) : (
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2">{dia(d.vence)}</Typography>
                        {dias < 0 && (
                          <Chip label="Vencido" size="small" sx={{
                            height: 19, fontSize: 10, fontWeight: 700,
                            bgcolor: `${ESTADO.peligro}1A`, color: ESTADO.peligro,
                          }} />
                        )}
                        {dias >= 0 && dias <= 30 && (
                          <Chip label={`Faltan ${dias} d`} size="small" sx={{
                            height: 19, fontSize: 10, fontWeight: 700,
                            bgcolor: `${ESTADO.alerta}1F`, color: ESTADO.alerta,
                          }} />
                        )}
                      </Stack>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => d.id && borrarDoc.mutate(d.id)}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              )
            })}
            {documentos.length === 0 && (
              <TableRow><TableCell colSpan={4}>
                <Typography variant="body2" sx={{ textAlign: 'center', py: 3, color: PALETA.acero }}>
                  Sin documentos registrados
                </Typography>
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <DialogoContacto empresa={empresa} abierto={nuevoContacto}
        onCerrar={() => setNuevoContacto(false)} />
      <DialogoDocumento empresa={empresa} abierto={nuevoDoc} onCerrar={() => setNuevoDoc(false)} />
    </Box>
  )
}
