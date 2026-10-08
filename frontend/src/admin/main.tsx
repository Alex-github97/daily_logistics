/**
 * Consola maestra de Daily Logistics.
 *
 * Aquí el operador de la plataforma da de alta empresas, les asigna los
 * módulos contratados (WMS, POS, TMS), crea sus usuarios maestros y atiende
 * soporte. El servidor comprueba en cada petición que quien entra pertenece a
 * la empresa operadora (`require_operador`).
 */
import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider, CssBaseline } from '@mui/material'
import { Box, Button, Typography, ButtonBase } from '@mui/material'
import { Logout, Apartment, SupportAgent, Groups, BugReport, History, AccountBalance, ViewKanban } from '@mui/icons-material'
import { Toaster } from 'react-hot-toast'
import { theme } from '@/theme/theme'
import { Logotipo } from '@/components/Logotipo'
import { DEGRADADO, DESTELLO, PALETA } from '@/config/marca'
import { sesion } from './api'
import Ingreso from './Ingreso'
import Empresas from './Empresas'
import Contabilidad from './Contabilidad'
import Soporte from './Soporte'
import Gestion from './Gestion'
import Equipo from './Equipo'
import Fallos from './Fallos'
import Bitacora from './Bitacora'
import '@/index.css'

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

const PESTANAS = [
  { etiqueta: 'Empresas y usuarios', icono: <Apartment fontSize="small" />, vista: <Empresas /> },
  { etiqueta: 'Contabilidad', icono: <AccountBalance fontSize="small" />, vista: <Contabilidad /> },
  { etiqueta: 'Soporte', icono: <SupportAgent fontSize="small" />, vista: <Soporte /> },
  { etiqueta: 'Proyectos', icono: <ViewKanban fontSize="small" />, vista: <Gestion /> },
  { etiqueta: 'Equipo operador', icono: <Groups fontSize="small" />, vista: <Equipo /> },
  { etiqueta: 'Fallos', icono: <BugReport fontSize="small" />, vista: <Fallos /> },
  { etiqueta: 'Bitácora', icono: <History fontSize="small" />, vista: <Bitacora /> },
]

function Consola() {
  const s = sesion.leer()
  const [pestana, setPestana] = useState(0)

  if (!s) return <Ingreso />

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: PALETA.bruma }}>
      <Box component="header" sx={{
        position: 'sticky', top: 0, zIndex: 1100,
        background: `radial-gradient(600px 140px at 85% 0%, rgba(124,58,237,0.35), transparent 70%), linear-gradient(90deg, ${PALETA.abismo} 0%, ${PALETA.tinta} 60%, #1E1B4B 100%)`,
        borderBottom: '1px solid transparent', borderImage: `${DEGRADADO} 1`,
      }}>
        <Box sx={{ height: 60, px: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
          <Logotipo tamano={17} claro />
          <Box sx={{
            fontSize: 10.5, fontWeight: 800, letterSpacing: '0.1em', px: 1, py: 0.3, borderRadius: 1,
            bgcolor: DESTELLO.base, color: PALETA.tinta,
          }}>
            CONSOLA MAESTRA
          </Box>
          <Box sx={{ flex: 1 }} />
          <Typography sx={{ fontSize: 12.5, color: 'rgba(255,255,255,0.75)' }}>
            {s.usuario} · {s.empresa}
          </Typography>
          <Button
            size="small" startIcon={<Logout />}
            sx={{ color: 'rgba(255,255,255,0.85)', textTransform: 'none', borderRadius: 99 }}
            onClick={() => { sesion.cerrar(); location.reload() }}
          >
            Salir
          </Button>
        </Box>
        <Box sx={{ px: 2, display: 'flex', gap: 0.5, overflowX: 'auto', pb: 1 }}>
          {PESTANAS.map((p, i) => (
            <ButtonBase
              key={p.etiqueta}
              onClick={() => setPestana(i)}
              sx={{
                gap: 0.8, px: 1.8, height: 36, borderRadius: 99, fontSize: 13.5, fontFamily: 'inherit',
                fontWeight: pestana === i ? 700 : 500, whiteSpace: 'nowrap',
                color: pestana === i ? PALETA.tinta : 'rgba(255,255,255,0.75)',
                bgcolor: pestana === i ? '#FFFFFF' : 'transparent',
                '&:hover': { bgcolor: pestana === i ? '#FFFFFF' : 'rgba(255,255,255,0.10)' },
              }}
            >
              {p.icono}{p.etiqueta}
            </ButtonBase>
          ))}
        </Box>
      </Box>

      <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1320, mx: 'auto' }}>
        {PESTANAS[pestana].vista}
      </Box>

      <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', pb: 3, color: PALETA.acero }}>
        Consola maestra · Daily Logistics
      </Typography>
    </Box>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Consola />
        <Toaster position="bottom-right" />
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
