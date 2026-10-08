/**
 * Datos de la empresa — /configuracion/empresa
 *
 * Los usan las facturas del POS, de los despachos WMS y de la facturación 3PL.
 * Al guardarlos por primera vez el servidor siembra el plan de cuentas.
 */
import { useEffect, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, CircularProgress, TextField, Typography } from '@mui/material'
import Grid from '@mui/material/Grid2'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Layout } from '@/components/layout/Layout'
import { apiClient } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { PALETA } from '@/config/marca'

const CAMPOS = {
  razon_social: '', nit: '', nombre_comercial: '', ciudad: '', direccion: '',
  telefono: '', email: '', regimen_fiscal: '', sector: '',
}
type Empresa = typeof CAMPOS & { id?: number }

export default function ConfiguracionEmpresa() {
  const qc = useQueryClient()
  const esAdmin = useAuthStore(s => s.user?.rol === 'ADMINISTRADOR')
  const [f, setF] = useState<Empresa>(CAMPOS)

  const { data, isLoading } = useQuery<Empresa | null>({
    queryKey: ['configuracion-empresa'],
    queryFn: () => apiClient.get('/configuracion/empresa').then(r => r.data),
  })

  useEffect(() => {
    if (data) setF(Object.fromEntries(Object.keys(CAMPOS).map(k => [k, (data as any)[k] ?? ''])) as Empresa)
  }, [data])

  const guardar = useMutation({
    mutationFn: () => apiClient.put('/configuracion/empresa',
      Object.fromEntries(Object.entries(f).map(([k, v]) => [k, typeof v === 'string' && v.trim() === '' ? null : v]))),
    onSuccess: () => {
      toast.success(data ? 'Datos de la empresa actualizados' : 'Empresa registrada: ya se puede facturar')
      qc.invalidateQueries({ queryKey: ['configuracion-empresa'] })
      qc.invalidateQueries({ queryKey: ['configuracion-resumen'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo guardar'),
  })

  const campo = (k: keyof typeof CAMPOS, label: string, req = false, size = 6) => (
    <Grid size={{ xs: 12, sm: size }}>
      <TextField fullWidth size="small" label={label} required={req} value={f[k] ?? ''}
        disabled={!esAdmin} onChange={e => setF({ ...f, [k]: e.target.value })} />
    </Grid>
  )

  return (
    <Layout title="Datos de la empresa">
      <Box sx={{ maxWidth: 820 }}>
        {!isLoading && !data && (
          <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }}>
            La empresa aún no tiene datos de facturación. Sin ellos el POS no puede facturar y los despachos
            del WMS quedan con la factura pendiente.
          </Alert>
        )}
        {!esAdmin && (
          <Alert severity="info" sx={{ mb: 2, borderRadius: 2 }}>Solo un administrador puede modificar estos datos.</Alert>
        )}
        <Card sx={{ borderRadius: 3, border: `1px solid ${PALETA.niebla}` }} elevation={0}>
          <CardContent sx={{ p: 3 }}>
            {isLoading ? <CircularProgress size={26} /> : (
              <>
                <Typography sx={{ fontWeight: 800, mb: 2 }}>Identificación</Typography>
                <Grid container spacing={2}>
                  {campo('razon_social', 'Razón social', true, 8)}
                  {campo('nit', 'NIT', true, 4)}
                  {campo('nombre_comercial', 'Nombre comercial')}
                  {campo('regimen_fiscal', 'Régimen fiscal')}
                  {campo('sector', 'Sector')}
                </Grid>
                <Typography sx={{ fontWeight: 800, mt: 3, mb: 2 }}>Contacto</Typography>
                <Grid container spacing={2}>
                  {campo('ciudad', 'Ciudad', false, 4)}
                  {campo('direccion', 'Dirección', false, 8)}
                  {campo('telefono', 'Teléfono')}
                  {campo('email', 'Correo de facturación')}
                </Grid>
                {esAdmin && (
                  <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end' }}>
                    <Button variant="contained" disabled={!f.razon_social.trim() || f.nit.trim().length < 3 || guardar.isPending}
                      onClick={() => guardar.mutate()} sx={{ textTransform: 'none', fontWeight: 700, minWidth: 160 }}>
                      {guardar.isPending ? <CircularProgress size={20} color="inherit" /> : data ? 'Guardar cambios' : 'Registrar empresa'}
                    </Button>
                  </Box>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </Box>
    </Layout>
  )
}
