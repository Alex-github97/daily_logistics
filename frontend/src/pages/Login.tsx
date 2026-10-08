/**
 * Ingreso a Daily Logistics.
 *
 * Es multicliente: primero se indica la empresa (su código decide en qué
 * esquema se busca al usuario) y luego las credenciales. Los dos pasos viven en
 * la misma tarjeta; la empresa elegida se recuerda en este equipo.
 */
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, TextField, Button, Typography, InputAdornment, IconButton, Alert, CircularProgress, Chip, alpha,
} from '@mui/material'
import {
  Visibility, VisibilityOff, LockOutlined, PersonOutline, ApartmentRounded, ArrowForward, SwapHoriz,
  Warehouse, LocalShipping, PointOfSale,
} from '@mui/icons-material'
import { useAuthStore } from '@/store/authStore'
import { clienteGuardado, guardarCliente, olvidarCliente, resolverCliente, ClientePublico } from '@/api/cliente'
import { Logotipo } from '@/components/Logotipo'
import { ACENTO, DEGRADADO, DESTELLO, MARCA, PALETA } from '@/config/marca'

const MODULOS = [
  { icono: <Warehouse />, sigla: 'WMS', texto: 'Almacén: recepción, inventario, picking y despacho' },
  { icono: <LocalShipping />, sigla: 'TMS', texto: 'Transporte: viajes, flota, tracking y liquidación' },
  { icono: <PointOfSale />, sigla: 'POS', texto: 'Punto de venta: caja, turnos y facturación' },
]

/** Ilustración: una red de rutas con paradas, en movimiento suave. */
function RedDeRutas() {
  return (
    <Box component="svg" viewBox="0 0 400 300" sx={{ width: '100%', maxWidth: 420, height: 'auto', opacity: 0.95 }}>
      <defs>
        <linearGradient id="dl-ruta" x1="0" x2="1">
          <stop offset="0" stopColor={ACENTO.claro} stopOpacity="0.15" />
          <stop offset="1" stopColor={ACENTO.claro} stopOpacity="0.8" />
        </linearGradient>
      </defs>
      {[0, 1, 2, 3, 4, 5].map(i => (
        <line key={i} x1="0" x2="400" y1={40 + i * 45} y2={40 + i * 45} stroke="rgba(255,255,255,0.05)" />
      ))}
      <path d="M30 240 C 110 240, 120 150, 200 150 S 300 60, 370 60" fill="none" stroke="url(#dl-ruta)" strokeWidth="3"
        strokeDasharray="8 8" style={{ animation: 'dlFlujo 2.4s linear infinite' }} />
      <path d="M30 120 C 120 120, 150 210, 230 220 S 330 200, 370 250" fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="2"
        strokeDasharray="4 10" style={{ animation: 'dlFlujo 3.6s linear infinite' }} />
      {[[30, 240], [200, 150], [370, 60], [30, 120], [230, 220], [370, 250]].map(([x, y], i) => (
        <g key={i}>
          <circle cx={x} cy={y} r="12" fill={i === 2 ? DESTELLO.base : ACENTO.claro} opacity="0.18" />
          <circle cx={x} cy={y} r="5.5" fill={i === 2 ? DESTELLO.base : '#FFFFFF'} />
        </g>
      ))}
      <style>{`@keyframes dlFlujo { to { stroke-dashoffset: -64; } }`}</style>
    </Box>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [empresa, setEmpresa] = useState<ClientePublico | null>(clienteGuardado())
  const [codigo, setCodigo] = useState('')
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState('')

  const elegirEmpresa = async (e: React.FormEvent) => {
    e.preventDefault()
    const limpio = codigo.trim().toLowerCase()
    if (!limpio) return
    setCargando(true); setError('')
    try {
      const c = await resolverCliente(limpio)
      guardarCliente(c)
      setEmpresa(c)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'No encontramos una empresa con ese código.')
    } finally {
      setCargando(false)
    }
  }

  const ingresar = async (e: React.FormEvent) => {
    e.preventDefault()
    setCargando(true); setError('')
    try {
      await login(usuario.trim(), clave)
      const { portal } = useAuthStore.getState()
      navigate(portal ? '/portal' : '/inicio')
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'No fue posible iniciar sesión.')
    } finally {
      setCargando(false)
    }
  }

  const cambiarEmpresa = () => {
    olvidarCliente(); setEmpresa(null); setCodigo(''); setError('')
  }

  const campo = {
    '& .MuiOutlinedInput-root': {
      borderRadius: 3, bgcolor: '#FFF',
      '& fieldset': { borderColor: PALETA.niebla },
      '&:hover fieldset': { borderColor: ACENTO.base },
    },
  }

  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: { xs: 2, md: 4 },
      bgcolor: PALETA.bruma,
      backgroundImage: `radial-gradient(${alpha(ACENTO.base, 0.10)} 1px, transparent 1px)`,
      backgroundSize: '22px 22px',
    }}>
      <Box sx={{
        width: '100%', maxWidth: 1040, minHeight: 600, display: 'flex', borderRadius: 6, overflow: 'hidden',
        bgcolor: '#FFF', boxShadow: '0 40px 80px -30px rgba(5, 7, 15,0.35), 0 0 0 1px rgba(5, 7, 15,0.04)',
      }}>
        {/* ── Panel de marca ─────────────────────────────────────────────── */}
        <Box sx={{
          flex: '0 0 46%', display: { xs: 'none', md: 'flex' }, flexDirection: 'column', p: 5, color: '#FFF',
          bgcolor: PALETA.abismo,
          backgroundImage: `
            radial-gradient(420px 320px at 90% 5%, rgba(124,58,237,0.45), transparent 70%),
            radial-gradient(380px 300px at 0% 100%, rgba(6,182,212,0.30), transparent 70%),
            linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)`,
          backgroundSize: 'auto, auto, 28px 28px, 28px 28px',
          position: 'relative',
        }}>
          <Logotipo tamano={22} claro conLema />
          <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', my: 3 }}>
            <RedDeRutas />
          </Box>
          <Typography sx={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.2, color: '#FFFFFF' }}>
            Tu operación logística,
            <Box component="span" sx={{ color: DESTELLO.base }}> todos los días.</Box>
          </Typography>
          <Box sx={{ mt: 2.5, display: 'flex', flexDirection: 'column', gap: 1.2 }}>
            {MODULOS.map(m => (
              <Box key={m.sigla} sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Box sx={{
                  width: 34, height: 34, borderRadius: 2, display: 'grid', placeItems: 'center',
                  bgcolor: 'rgba(255,255,255,0.08)', color: ACENTO.claro, '& svg': { fontSize: 19 },
                }}>
                  {m.icono}
                </Box>
                <Typography sx={{ fontSize: 13.5, color: 'rgba(255,255,255,0.8)' }}>
                  <b style={{ color: '#FFF' }}>{m.sigla}</b> · {m.texto}
                </Typography>
              </Box>
            ))}
          </Box>
        </Box>

        {/* ── Formulario ─────────────────────────────────────────────────── */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', px: { xs: 3, sm: 7 }, py: 5 }}>
          <Box sx={{ display: { md: 'none' }, mb: 4 }}><Logotipo tamano={20} /></Box>

          {/* Indicador de pasos */}
          <Box sx={{ display: 'flex', gap: 1, mb: 4 }}>
            {[0, 1].map(i => (
              <Box key={i} sx={{
                height: 5, borderRadius: 9, transition: 'all .3s',
                width: (empresa ? 1 : 0) === i ? 44 : 20,
                bgcolor: i === 0 || empresa ? ACENTO.base : PALETA.niebla,
              }} />
            ))}
          </Box>

          {!empresa ? (
            <Box component="form" onSubmit={elegirEmpresa}>
              <Typography sx={{ fontSize: 13, fontWeight: 700, color: ACENTO.base, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                Paso 1 de 2
              </Typography>
              <Typography sx={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.03em', color: PALETA.tinta, mt: 0.5 }}>
                ¿A qué empresa entras?
              </Typography>
              <Typography sx={{ color: PALETA.acero, mt: 1, mb: 3.5, fontSize: 14.5 }}>
                Escribe el código de tu empresa. Tu administrador te lo entregó junto con tu usuario.
              </Typography>
              <TextField
                fullWidth autoFocus label="Código de empresa" value={codigo}
                onChange={e => setCodigo(e.target.value)} sx={campo}
                InputProps={{ startAdornment: <InputAdornment position="start"><ApartmentRounded sx={{ color: PALETA.acero }} /></InputAdornment> }}
              />
              {error && <Alert severity="error" sx={{ mt: 2, borderRadius: 3 }}>{error}</Alert>}
              <Button
                type="submit" fullWidth variant="contained" disabled={cargando || !codigo.trim()}
                endIcon={cargando ? undefined : <ArrowForward />}
                sx={boton}
              >
                {cargando ? <CircularProgress size={22} sx={{ color: '#FFF' }} /> : 'Continuar'}
              </Button>
            </Box>
          ) : (
            <Box component="form" onSubmit={ingresar}>
              <Typography sx={{ fontSize: 13, fontWeight: 700, color: ACENTO.base, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                Paso 2 de 2
              </Typography>
              <Typography sx={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.03em', color: PALETA.tinta, mt: 0.5 }}>
                Hola de nuevo
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.5, mb: 3.5, flexWrap: 'wrap' }}>
                <Chip
                  icon={<ApartmentRounded />}
                  label={empresa.nombre}
                  sx={{ fontWeight: 700, bgcolor: ACENTO.vapor, color: ACENTO.profundo, '& .MuiChip-icon': { color: ACENTO.base } }}
                />
                <Button size="small" startIcon={<SwapHoriz />} onClick={cambiarEmpresa}
                  sx={{ textTransform: 'none', color: PALETA.grafito }}>
                  Cambiar empresa
                </Button>
              </Box>
              <TextField
                fullWidth autoFocus label="Usuario" value={usuario} onChange={e => setUsuario(e.target.value)}
                autoComplete="username" sx={{ ...campo, mb: 2 }}
                InputProps={{ startAdornment: <InputAdornment position="start"><PersonOutline sx={{ color: PALETA.acero }} /></InputAdornment> }}
              />
              <TextField
                fullWidth label="Contraseña" type={verClave ? 'text' : 'password'} value={clave}
                onChange={e => setClave(e.target.value)} autoComplete="current-password" sx={campo}
                InputProps={{
                  startAdornment: <InputAdornment position="start"><LockOutlined sx={{ color: PALETA.acero }} /></InputAdornment>,
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton onClick={() => setVerClave(v => !v)} edge="end" size="small">
                        {verClave ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
              {error && <Alert severity="error" sx={{ mt: 2, borderRadius: 3 }}>{error}</Alert>}
              <Button
                type="submit" fullWidth variant="contained" disabled={cargando || !usuario || !clave}
                endIcon={cargando ? undefined : <ArrowForward />}
                sx={boton}
              >
                {cargando ? <CircularProgress size={22} sx={{ color: '#FFF' }} /> : 'Ingresar'}
              </Button>
            </Box>
          )}

          <Typography sx={{ mt: 'auto', pt: 5, fontSize: 12, color: PALETA.acero }}>
            {MARCA.legal}
          </Typography>
        </Box>
      </Box>
    </Box>
  )
}

const boton = {
  mt: 3, height: 52, borderRadius: 3, textTransform: 'none', fontSize: 15.5, fontWeight: 700,
  background: DEGRADADO, boxShadow: `0 14px 30px -12px ${alpha('#7C3AED', 0.75)}`,
  '&:hover': { background: DEGRADADO, filter: 'brightness(1.1)' },
  '&.Mui-disabled': { background: PALETA.niebla, color: PALETA.acero },
}
