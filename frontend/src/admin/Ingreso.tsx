/**
 * Entrada a la consola del operador.
 *
 * A diferencia del portal, acá no hay paso previo de empresa separado: quien
 * entra ya sabe cuál es la suya, y pedirla en dos pantallas solo alargaría el
 * camino de la única empresa que usa esta consola.
 */
import { useState } from 'react'
import {
  Box, Card, CardContent, TextField, Button, Typography, Stack, Alert, CircularProgress,
} from '@mui/material'
import { Logotipo } from '@/components/Logotipo'
import { PALETA } from '@/config/marca'
import { consolaApi, sesion, mensajeDeError } from './api'

export default function Ingreso() {
  const [empresa, setEmpresa] = useState('')
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const entrar = async () => {
    if (!empresa.trim() || !usuario.trim() || !clave) {
      setError('Complete los tres campos')
      return
    }
    setCargando(true); setError('')
    try {
      sesion.guardar(await consolaApi.ingresar(empresa.trim().toLowerCase(), usuario.trim(), clave))
      location.reload()
    } catch (e: any) {
      setError(mensajeDeError(e, 'No se pudo entrar'))
    } finally {
      setCargando(false)
    }
  }

  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: `radial-gradient(900px 500px at 15% 10%, rgba(34, 211, 238,0.18), transparent 60%), linear-gradient(135deg, ${PALETA.abismo} 0%, ${PALETA.tinta} 60%, #3730A3 100%)`, p: 2,
    }}>
      <Card sx={{ width: '100%', maxWidth: 420, borderRadius: 4, boxShadow: 8 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={1} alignItems="center" mb={3}>
            <Logotipo tamano={20} />
            <Typography variant="h6" fontWeight={700} sx={{ mt: 1.5 }}>
              Consola maestra
            </Typography>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              Empresas, módulos contratados y usuarios maestros de Daily Logistics.
            </Typography>
          </Stack>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <Stack spacing={2}>
            <TextField
              label="Empresa operadora" value={empresa} autoFocus fullWidth
              onChange={e => setEmpresa(e.target.value)}
              inputProps={{ style: { textTransform: 'lowercase' } }}
              disabled={cargando}
            />
            <TextField
              label="Usuario" value={usuario} fullWidth
              onChange={e => setUsuario(e.target.value)} disabled={cargando}
            />
            <TextField
              label="Contraseña" type="password" value={clave} fullWidth
              onChange={e => setClave(e.target.value)} disabled={cargando}
              onKeyDown={e => { if (e.key === 'Enter') entrar() }}
            />
            <Button
              variant="contained" size="large" onClick={entrar} disabled={cargando}
              sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700, py: 1.2 }}
            >
              {cargando ? <CircularProgress size={22} color="inherit" /> : 'Entrar'}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}
