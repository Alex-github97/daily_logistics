/**
 * Alta y edición de conductores desde el TMS.
 *
 * Daily Logistics no tiene Gestión Humana: aquí se registra en un solo paso la
 * persona y su licencia. El servidor (`/tms/conductores`) crea por debajo el
 * colaborador que exige el modelo.
 */
import { useEffect, useState } from 'react'
import {
  Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, Switch, Typography, CircularProgress,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient } from '@/api/client'
import { COLOR_MODULO } from '@/config/marca'

export interface ConductorEditable {
  id: number
  tipo_documento?: string | null
  colaborador_documento?: string | null
  nombres?: string | null
  apellidos?: string | null
  colaborador_telefono?: string | null
  email?: string | null
  colaborador_ciudad?: string | null
  num_licencia: string
  tipo_licencia: string
  fecha_expedicion_licencia?: string | null
  fecha_vencimiento_licencia: string
  anos_experiencia: number
  restricciones?: string | null
  vehiculos_tipos: string[]
  coberturas: string[]
  activo_conduccion: boolean
}

const TIPOS_DOC = ['CC', 'CE', 'PA', 'TI', 'NIT']
const CATEGORIAS = ['A1', 'A2', 'B1', 'B2', 'B3', 'C1', 'C2', 'C3']
const VEHICULOS: [string, string][] = [
  ['MOTOCICLETA', 'Motocicleta'], ['AUTOMOVIL', 'Automóvil'], ['CAMIONETA', 'Camioneta'],
  ['CAMION_RIGIDO', 'Camión rígido'], ['TRACTOCAMION', 'Tractocamión'], ['DOBLE_TROQUE', 'Doble troque'],
  ['ARTICULADO', 'Articulado'], ['MONTACARGAS', 'Montacargas'], ['REACH_STACKER', 'Reach stacker'],
  ['EQUIPO_ESPECIAL', 'Equipo especial'],
]
const COBERTURAS: [string, string][] = [
  ['URBANA', 'Urbana'], ['METROPOLITANA', 'Metropolitana'], ['REGIONAL', 'Regional'],
  ['NACIONAL', 'Nacional'], ['INTERNACIONAL', 'Internacional'],
]

const VACIO = {
  tipo_documento: 'CC', numero_documento: '', nombres: '', apellidos: '', telefono: '', email: '', ciudad: '',
  num_licencia: '', tipo_licencia: 'C2', fecha_expedicion_licencia: '', fecha_vencimiento_licencia: '',
  anos_experiencia: 0, restricciones: '', vehiculos_tipos: [] as string[], coberturas: [] as string[],
  activo_conduccion: true,
}

export function ConductorFormDialog({
  open, conductor, onClose,
}: {
  open: boolean
  /** null = conductor nuevo. */
  conductor: ConductorEditable | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [f, setF] = useState(VACIO)
  const editando = !!conductor

  useEffect(() => {
    if (!open) return
    setF(conductor ? {
      tipo_documento: conductor.tipo_documento ?? 'CC',
      numero_documento: conductor.colaborador_documento ?? '',
      nombres: conductor.nombres ?? '',
      apellidos: conductor.apellidos ?? '',
      telefono: conductor.colaborador_telefono ?? '',
      email: conductor.email ?? '',
      ciudad: conductor.colaborador_ciudad ?? '',
      num_licencia: conductor.num_licencia,
      tipo_licencia: conductor.tipo_licencia,
      fecha_expedicion_licencia: conductor.fecha_expedicion_licencia ?? '',
      fecha_vencimiento_licencia: conductor.fecha_vencimiento_licencia,
      anos_experiencia: conductor.anos_experiencia ?? 0,
      restricciones: conductor.restricciones ?? '',
      vehiculos_tipos: conductor.vehiculos_tipos ?? [],
      coberturas: conductor.coberturas ?? [],
      activo_conduccion: conductor.activo_conduccion,
    } : VACIO)
  }, [open, conductor])

  const set = (k: keyof typeof VACIO, v: unknown) => setF(prev => ({ ...prev, [k]: v }))
  const alternar = (k: 'vehiculos_tipos' | 'coberturas', v: string) =>
    setF(prev => ({ ...prev, [k]: prev[k].includes(v) ? prev[k].filter(x => x !== v) : [...prev[k], v] }))

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        ...f,
        anos_experiencia: Number(f.anos_experiencia) || 0,
        telefono: f.telefono || null, email: f.email || null, ciudad: f.ciudad || null,
        restricciones: f.restricciones || null,
      }
      return editando
        ? apiClient.put(`/tms/conductores/${conductor!.id}`, cuerpo)
        : apiClient.post('/tms/conductores', cuerpo)
    },
    onSuccess: () => {
      toast.success(editando ? 'Conductor actualizado' : 'Conductor creado')
      qc.invalidateQueries({ queryKey: ['tms-conductores'] })
      qc.invalidateQueries({ queryKey: ['hcm-conductores'] })
      onClose()
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo guardar el conductor'),
  })

  const vence = f.fecha_vencimiento_licencia
  const expide = f.fecha_expedicion_licencia
  const fechasMal = !!vence && !!expide && vence <= expide
  const completo = f.numero_documento.trim().length >= 3 && f.nombres.trim() && f.apellidos.trim()
    && f.num_licencia.trim().length >= 3 && expide && vence && !fechasMal

  const seccion = (t: string) => (
    <Typography sx={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: COLOR_MODULO, mt: 1 }}>
      {t}
    </Typography>
  )

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 800 }}>{editando ? 'Editar conductor' : 'Nuevo conductor'}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {seccion('Datos personales')}
          <Grid container spacing={2}>
            <Grid size={{ xs: 4, sm: 2 }}>
              <TextField select fullWidth size="small" label="Tipo" value={f.tipo_documento} onChange={e => set('tipo_documento', e.target.value)}>
                {TIPOS_DOC.map(t => <MenuItem key={t} value={t}>{t}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 8, sm: 4 }}>
              <TextField fullWidth size="small" required label="Número de documento" value={f.numero_documento} onChange={e => set('numero_documento', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField fullWidth size="small" required label="Nombres" value={f.nombres} onChange={e => set('nombres', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField fullWidth size="small" required label="Apellidos" value={f.apellidos} onChange={e => set('apellidos', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField fullWidth size="small" label="Teléfono" value={f.telefono} onChange={e => set('telefono', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField fullWidth size="small" label="Correo" type="email" value={f.email} onChange={e => set('email', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField fullWidth size="small" label="Ciudad" value={f.ciudad} onChange={e => set('ciudad', e.target.value)} />
            </Grid>
          </Grid>

          {seccion('Licencia de conducción')}
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField fullWidth size="small" required label="Número de licencia" value={f.num_licencia} onChange={e => set('num_licencia', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 6, sm: 2 }}>
              <TextField select fullWidth size="small" label="Categoría" value={f.tipo_licencia} onChange={e => set('tipo_licencia', e.target.value)}>
                {CATEGORIAS.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 6, sm: 2 }}>
              <TextField fullWidth size="small" type="number" label="Años de experiencia" value={f.anos_experiencia}
                inputProps={{ min: 0, max: 70 }} onChange={e => set('anos_experiencia', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 6, sm: 2 }}>
              <TextField fullWidth size="small" required type="date" label="Expedición" InputLabelProps={{ shrink: true }}
                value={f.fecha_expedicion_licencia} onChange={e => set('fecha_expedicion_licencia', e.target.value)} />
            </Grid>
            <Grid size={{ xs: 6, sm: 2 }}>
              <TextField fullWidth size="small" required type="date" label="Vencimiento" InputLabelProps={{ shrink: true }}
                value={f.fecha_vencimiento_licencia} onChange={e => set('fecha_vencimiento_licencia', e.target.value)}
                error={fechasMal} helperText={fechasMal ? 'Debe ser posterior a la expedición' : undefined} />
            </Grid>
            <Grid size={12}>
              <TextField fullWidth size="small" label="Restricciones (opcional)" value={f.restricciones} onChange={e => set('restricciones', e.target.value)} />
            </Grid>
          </Grid>

          {seccion('Vehículos que puede conducir')}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {VEHICULOS.map(([v, l]) => (
              <Chip key={v} label={l} clickable onClick={() => alternar('vehiculos_tipos', v)}
                color={f.vehiculos_tipos.includes(v) ? 'primary' : 'default'}
                variant={f.vehiculos_tipos.includes(v) ? 'filled' : 'outlined'} />
            ))}
          </Box>

          {seccion('Cobertura de operación')}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {COBERTURAS.map(([v, l]) => (
              <FormControlLabel key={v} label={l}
                control={<Checkbox size="small" checked={f.coberturas.includes(v)} onChange={() => alternar('coberturas', v)} />} />
            ))}
          </Box>

          {editando && (
            <FormControlLabel
              control={<Switch checked={f.activo_conduccion} onChange={e => set('activo_conduccion', e.target.checked)} />}
              label={f.activo_conduccion ? 'Activo para asignar viajes' : 'Inactivo: no aparece en la planeación'}
            />
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button variant="contained" disabled={!completo || guardar.isPending} onClick={() => guardar.mutate()}
          sx={{ textTransform: 'none', fontWeight: 700, minWidth: 140 }}>
          {guardar.isPending ? <CircularProgress size={20} color="inherit" /> : editando ? 'Guardar cambios' : 'Crear conductor'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
