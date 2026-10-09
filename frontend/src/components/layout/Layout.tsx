/**
 * Marco de todas las pantallas de Daily Logistics.
 *
 * A diferencia de la plataforma madre (panel lateral), aquí la navegación vive
 * arriba, en dos franjas:
 *   1. Barra de módulos (oscura): logo, WMS · TMS · POS · Administración, y la
 *      sesión.
 *   2. Barra de secciones (clara): las secciones del módulo activo, cada una
 *      con su menú desplegable de pantallas.
 * Debajo, una cabecera de página con la ruta de migas y el título.
 */
import React, { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Box, Button, ButtonBase, Typography, Menu, MenuItem, ListItemText, Avatar,
  IconButton, Tooltip, Divider, LinearProgress, Drawer, List, ListItemButton, ListSubheader, alpha,
} from '@mui/material'
import {
  KeyboardArrowDown, Logout, SupportAgent, Menu as MenuIcon, ChevronRight, HomeRounded, Business,
} from '@mui/icons-material'
import { useIsFetching, useIsMutating } from '@tanstack/react-query'
import { useAuthStore } from '@/store/authStore'
import { clienteGuardado } from '@/api/cliente'
import { Logotipo } from '@/components/Logotipo'
import { ACENTO, DEGRADADO, DESTELLO, PALETA } from '@/config/marca'
import { NAVEGACION, ModuloNav, SeccionNav, coincide, itemActivo, moduloDeRuta } from './navegacion'
import { DetectorLector } from '@/components/comun/LectorGlobal'

interface LayoutProps {
  children: React.ReactNode
  title?: string
  noPadding?: boolean
}

const MODULOS_CONTRATABLES = ['wms', 'tms', 'pos', 'wfm']

/**
 * Los módulos que este usuario puede ver, ya con sus secciones filtradas:
 * cada pantalla exige que la empresa tenga contratado su módulo y que el rol
 * tenga el permiso. Una sección sin pantallas visibles desaparece.
 */
export function useModulosVisibles(): ModuloNav[] {
  const { user, modulos } = useAuthStore()
  const esAdmin = user?.rol === 'ADMINISTRADOR'
  return useMemo(() => {
    const contratado = (clave: string) =>
      !MODULOS_CONTRATABLES.includes(clave) || modulos.includes('*') || modulos.includes(clave)
    const permitido = (permiso?: string) => esAdmin || !permiso || !!user?.permisos?.[permiso]

    return NAVEGACION
      .filter(m => contratado(m.clave))
      .filter(m => esAdmin || !m.permisos || m.permisos.some(p => user?.permisos?.[p]))
      .map(m => ({
        ...m,
        secciones: m.secciones
          .map(s => ({
            ...s,
            items: s.items.filter(i => permitido(i.permiso) && (!i.permiso || contratado(i.permiso))),
          }))
          .filter(s => s.items.length > 0),
      }))
  }, [user, modulos, esAdmin])
}

function MenuSeccion({ seccion, ruta, onIr }: { seccion: SeccionNav; ruta: string; onIr: (r: string) => void }) {
  const [ancla, setAncla] = useState<HTMLElement | null>(null)
  const activa = seccion.items.some(i => coincide(ruta, i))
  const unica = seccion.items.length === 1

  return (
    <>
      <ButtonBase
        onClick={e => (unica ? onIr(seccion.items[0].ruta) : setAncla(e.currentTarget))}
        sx={{
          position: 'relative', height: 46, px: 1.6, gap: 0.3, flexShrink: 0,
          fontSize: 13.5, fontWeight: activa ? 700 : 500, fontFamily: 'inherit',
          color: activa ? PALETA.tinta : PALETA.grafito,
          borderRadius: 0,
          '&:hover': { color: PALETA.tinta, bgcolor: alpha(ACENTO.base, 0.05) },
          '&::after': {
            content: '""', position: 'absolute', left: 12, right: 12, bottom: 0, height: 3,
            borderRadius: '3px 3px 0 0', bgcolor: activa ? DESTELLO.base : 'transparent',
          },
        }}
      >
        {seccion.titulo}
        {!unica && <KeyboardArrowDown sx={{ fontSize: 17, opacity: 0.6 }} />}
      </ButtonBase>
      {!unica && (
        <Menu
          anchorEl={ancla} open={!!ancla} onClose={() => setAncla(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
          transformOrigin={{ vertical: 'top', horizontal: 'left' }}
          slotProps={{ paper: { sx: { mt: 0.5, minWidth: 220, borderRadius: 2.5, border: `1px solid ${PALETA.niebla}` } } }}
        >
          {seccion.items.map(item => {
            const sel = coincide(ruta, item)
            return (
              <MenuItem
                key={item.ruta} selected={sel}
                onClick={() => { setAncla(null); onIr(item.ruta) }}
                sx={{ fontSize: 13.5, py: 1, borderLeft: `3px solid ${sel ? ACENTO.base : 'transparent'}` }}
              >
                <ListItemText primaryTypographyProps={{ fontSize: 13.5, fontWeight: sel ? 700 : 500 }}>
                  {item.etiqueta}
                </ListItemText>
              </MenuItem>
            )
          })}
        </Menu>
      )}
    </>
  )
}

export function Layout({ children, title, noPadding = false }: LayoutProps) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { user, logout } = useAuthStore()
  const visibles = useModulosVisibles()
  const empresa = clienteGuardado()
  const [anclaUsuario, setAnclaUsuario] = useState<HTMLElement | null>(null)
  const [cajon, setCajon] = useState(false)
  const ocupado = useIsFetching() + useIsMutating() > 0

  // El módulo de la ruta, con las secciones que este usuario puede ver.
  const delaRuta = moduloDeRuta(pathname)
  const modulo = visibles.find(m => m.clave === delaRuta?.clave) ?? delaRuta
  const activo = itemActivo(pathname, modulo)
  const iniciales = `${user?.nombre?.[0] ?? ''}${user?.apellido?.[0] ?? ''}`.toUpperCase()
  const titulo = title ?? activo?.item.etiqueta ?? modulo?.nombre ?? ''

  const ir = (r: string) => { setCajon(false); navigate(r) }

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', bgcolor: PALETA.bruma }}>
      <DetectorLector />
      <Box component="header" sx={{ position: 'sticky', top: 0, zIndex: 1100 }}>
        {/* ── 1. Barra de módulos ─────────────────────────────────────────── */}
        <Box sx={{
          height: 60, px: { xs: 1.5, md: 3 }, display: 'flex', alignItems: 'center', gap: 2,
          bgcolor: PALETA.abismo,
          backgroundImage: `
            radial-gradient(600px 120px at 85% 0%, ${alpha('#7C3AED', 0.35)}, transparent 70%),
            radial-gradient(500px 120px at 30% 100%, ${alpha(DESTELLO.base, 0.12)}, transparent 70%),
            linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px),
            linear-gradient(90deg, ${PALETA.abismo} 0%, ${PALETA.tinta} 60%, #1E1B4B 100%)`,
          backgroundSize: 'auto, auto, 24px 24px, 24px 24px, auto',
          borderBottom: '1px solid transparent',
          borderImage: `${DEGRADADO} 1`,
        }}>
          <IconButton onClick={() => setCajon(true)} sx={{ display: { md: 'none' }, color: '#FFF' }}>
            <MenuIcon />
          </IconButton>
          <ButtonBase onClick={() => ir('/inicio')} sx={{ borderRadius: 2, p: 0.5 }}>
            <Logotipo tamano={17} claro />
          </ButtonBase>

          <Box sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', gap: 0.5, ml: 2 }}>
            <Button
              onClick={() => ir('/inicio')}
              startIcon={<HomeRounded sx={{ fontSize: 18 }} />}
              sx={pill(pathname === '/inicio')}
            >
              Inicio
            </Button>
            {visibles.map(m => (
              <Button key={m.clave} onClick={() => ir(m.inicio)} sx={pill(modulo?.clave === m.clave)}>
                <Box component="span" sx={{
                  fontSize: 10.5, fontWeight: 800, letterSpacing: '0.06em', mr: 0.9, px: 0.7, py: 0.15,
                  borderRadius: 1, bgcolor: modulo?.clave === m.clave ? DESTELLO.base : 'rgba(255,255,255,0.12)',
                  color: modulo?.clave === m.clave ? PALETA.tinta : '#FFF',
                }}>
                  {m.sigla}
                </Box>
                {m.nombre}
              </Button>
            ))}
          </Box>

          <Box sx={{ flex: 1 }} />

          {empresa && (
            <Box sx={{
              display: { xs: 'none', lg: 'flex' }, alignItems: 'center', gap: 0.8, px: 1.3, py: 0.5,
              borderRadius: 99, border: '1px solid rgba(255,255,255,0.16)', color: 'rgba(255,255,255,0.85)',
            }}>
              <Business sx={{ fontSize: 16 }} />
              <Typography sx={{ fontSize: 12.5, fontWeight: 600 }}>{empresa.nombre}</Typography>
            </Box>
          )}
          <Tooltip title="Mesa de ayuda">
            <IconButton onClick={() => ir('/soporte')} sx={{ color: 'rgba(255,255,255,0.8)' }}>
              <SupportAgent fontSize="small" />
            </IconButton>
          </Tooltip>
          <ButtonBase
            onClick={e => setAnclaUsuario(e.currentTarget)}
            sx={{ borderRadius: 99, pl: 0.5, pr: { xs: 0.5, sm: 1.5 }, py: 0.5, gap: 1, '&:hover': { bgcolor: 'rgba(255,255,255,0.08)' } }}
          >
            <Avatar sx={{ width: 32, height: 32, fontSize: 13, fontWeight: 800, bgcolor: DESTELLO.base, color: PALETA.tinta }}>
              {iniciales || '?'}
            </Avatar>
            <Box sx={{ display: { xs: 'none', sm: 'block' }, textAlign: 'left' }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: '#FFF', lineHeight: 1.2 }}>
                {user?.nombre} {user?.apellido}
              </Typography>
              <Typography sx={{ fontSize: 11, color: 'rgba(255,255,255,0.6)', lineHeight: 1.2 }}>
                {user?.rol?.replace(/_/g, ' ').toLowerCase()}
              </Typography>
            </Box>
          </ButtonBase>
          <Menu
            anchorEl={anclaUsuario} open={!!anclaUsuario} onClose={() => setAnclaUsuario(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            slotProps={{ paper: { sx: { mt: 1, minWidth: 220, borderRadius: 2.5 } } }}
          >
            <Box sx={{ px: 2, py: 1 }}>
              <Typography sx={{ fontWeight: 700, fontSize: 14 }}>{user?.username}</Typography>
              <Typography sx={{ fontSize: 12, color: PALETA.acero }}>{user?.email}</Typography>
            </Box>
            <Divider />
            <MenuItem onClick={() => { setAnclaUsuario(null); logout(); navigate('/login') }} sx={{ fontSize: 13.5, color: '#B91C1C', gap: 1 }}>
              <Logout fontSize="small" /> Cerrar sesión
            </MenuItem>
          </Menu>
        </Box>

        {/* ── 2. Barra de secciones del módulo activo ─────────────────────── */}
        {modulo && (
          <Box sx={{
            height: 46, px: { xs: 1, md: 3 }, display: 'flex', alignItems: 'center',
            bgcolor: '#FFFFFF', borderBottom: `1px solid ${PALETA.niebla}`,
            overflowX: 'auto', overflowY: 'hidden', '&::-webkit-scrollbar': { height: 0 },
          }}>
            {modulo.secciones.map(s => (
              <MenuSeccion key={s.titulo} seccion={s} ruta={pathname} onIr={ir} />
            ))}
          </Box>
        )}
        <Box sx={{ height: 2, bgcolor: ocupado ? 'transparent' : PALETA.bruma }}>
          {ocupado && <LinearProgress sx={{ height: 2, bgcolor: 'transparent', '& .MuiLinearProgress-bar': { bgcolor: DESTELLO.base } }} />}
        </Box>
      </Box>

      {/* ── Cabecera de la página ─────────────────────────────────────────── */}
      {titulo && !noPadding && (
        <Box sx={{ px: { xs: 2, md: 4 }, pt: 2.5, pb: 0.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: PALETA.acero, fontSize: 12, fontWeight: 600 }}>
            {modulo && <span>{modulo.sigla} · {modulo.nombre}</span>}
            {activo && (<><ChevronRight sx={{ fontSize: 15 }} /><span>{activo.seccion.titulo}</span></>)}
          </Box>
          <Typography component="h1" sx={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em', color: PALETA.tinta, mt: 0.3 }}>
            {titulo}
          </Typography>
        </Box>
      )}

      <Box
        component="main"
        className="anim-page-in"
        sx={{
          flex: 1, minHeight: 0,
          p: noPadding ? 0 : { xs: 2, md: 4 }, pt: noPadding ? 0 : 2,
          overflow: noPadding ? 'hidden' : 'visible',
          display: noPadding ? 'flex' : 'block', flexDirection: 'column',
        }}
      >
        {children}
      </Box>

      {/* ── Navegación en pantallas pequeñas ──────────────────────────────── */}
      <Drawer anchor="top" open={cajon} onClose={() => setCajon(false)}>
        <List sx={{ maxHeight: '80vh', overflow: 'auto' }}>
          <ListItemButton onClick={() => ir('/inicio')}>Inicio</ListItemButton>
          {visibles.map(m => (
            <React.Fragment key={m.clave}>
              <ListSubheader sx={{ fontWeight: 800 }}>{m.sigla} · {m.nombre}</ListSubheader>
              {m.secciones.flatMap(s => s.items).map(i => (
                <ListItemButton key={i.ruta} selected={coincide(pathname, i)} onClick={() => ir(i.ruta)} sx={{ pl: 4, fontSize: 14 }}>
                  {i.etiqueta}
                </ListItemButton>
              ))}
            </React.Fragment>
          ))}
        </List>
      </Drawer>
    </Box>
  )
}

function pill(activo: boolean) {
  return {
    height: 36, px: 1.6, borderRadius: 99, textTransform: 'none' as const,
    fontSize: 13.5, fontWeight: activo ? 700 : 500, whiteSpace: 'nowrap' as const,
    color: activo ? '#FFFFFF' : 'rgba(255,255,255,0.72)',
    bgcolor: activo ? 'rgba(255,255,255,0.14)' : 'transparent',
    '&:hover': { bgcolor: 'rgba(255,255,255,0.10)', color: '#FFF' },
  }
}
