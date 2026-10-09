import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import { CssBaseline, Box, Typography, Button } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { theme } from '@/theme/theme'
import { useAuthStore } from '@/store/authStore'
import { Distintivo } from '@/components/Logotipo'
import { ACENTO, PALETA } from '@/config/marca'

// Prefijo de ruta → clave de permiso del rol.
// Gana el prefijo más largo: /configuracion/usuarios exige 'usuarios' aunque
// /configuracion exija 'configuracion'.
const ROUTE_PERM_MAP: Record<string, string> = {
  '/wms':                      'wms',
  '/tms':                      'tms',
  '/fletes':                   'tms',
  '/pos':                      'pos',
  '/configuracion/usuarios':   'usuarios',
  '/configuracion/roles':      'usuarios',
  '/configuracion/empresa':    'configuracion',
  '/configuracion/catalogos':  'configuracion',
}

/** El centro de configuración lo ve quien tenga cualquiera de los dos permisos. */
const PERMISOS_CENTRO = ['usuarios', 'configuracion']

// Prefijo de ruta → módulo contratado por la empresa.
const ROUTE_MODULO_MAP: Record<string, string> = {
  '/wms': 'wms', '/tms': 'tms', '/fletes': 'tms', '/pos': 'pos',
}

const Login = React.lazy(() => import('@/pages/Login'))
const Inicio = React.lazy(() => import('@/pages/Inicio'))
const Soporte = React.lazy(() => import('@/pages/Soporte'))
const Usuarios = React.lazy(() => import('@/pages/Usuarios'))
const ConfiguracionCentro = React.lazy(() => import('@/pages/ConfiguracionCentro'))
const ConfiguracionEmpresa = React.lazy(() => import('@/pages/ConfiguracionEmpresa'))
const Catalogos = React.lazy(() => import('@/pages/Catalogos'))
const Roles = React.lazy(() => import('@/pages/Roles'))
const ScannerMovil = React.lazy(() => import('@/pages/ScannerMovil'))
const PortalDepositante = React.lazy(() => import('@/pages/PortalDepositante'))

const WMSDashboard = React.lazy(() => import('@/pages/WMSDashboard'))
const WMSProductos = React.lazy(() => import('@/pages/WMSProductos'))
const WMSRecepcion = React.lazy(() => import('@/pages/WMSRecepcion'))
const WMSInventario = React.lazy(() => import('@/pages/WMSInventario'))
const WMSPicking = React.lazy(() => import('@/pages/WMSPicking'))
const WMSCanalesVenta = React.lazy(() => import('@/pages/WMSCanalesVenta'))
const WMSPedidosEnLinea = React.lazy(() => import('@/pages/WMSPedidosEnLinea'))
const WMSDespacho = React.lazy(() => import('@/pages/WMSDespacho'))
const WMSTrazabilidad = React.lazy(() => import('@/pages/WMSTrazabilidad'))
const WMSTareas = React.lazy(() => import('@/pages/WMSTareas'))
const WMSEstibas = React.lazy(() => import('@/pages/WMSEstibas'))
const WMSCubicaje = React.lazy(() => import('@/pages/WMSCubicaje'))
const WMSIndicadores = React.lazy(() => import('@/pages/WMSIndicadores'))
const WMSSlotting = React.lazy(() => import('@/pages/WMSSlotting'))
const WMSOlas = React.lazy(() => import('@/pages/WMSOlas'))
const WMSEmpaque = React.lazy(() => import('@/pages/WMSEmpaque'))
const WMSMaquila = React.lazy(() => import('@/pages/WMSMaquila'))
const WMSMapa = React.lazy(() => import('@/pages/WMSMapa'))
const WMSConstructor = React.lazy(() => import('@/pages/WMSConstructor'))
const WMSFrentes = React.lazy(() => import('@/pages/WMSFrentes'))
const WMSConsolidacion = React.lazy(() => import('@/pages/WMSConsolidacion'))
const TMSAsignacionCarga = React.lazy(() => import('@/pages/TMSAsignacionCarga'))
const PersonalTablero = React.lazy(() => import('@/pages/personal/PersonalTablero'))
const PersonalMiTurno = React.lazy(() => import('@/pages/personal/PersonalMiTurno'))
const PersonalProgramacion = React.lazy(() => import('@/pages/personal/PersonalProgramacion'))
const PersonalEstaciones = React.lazy(() => import('@/pages/personal/PersonalEstaciones'))
const PersonalPersonas = React.lazy(() => import('@/pages/personal/PersonalPersonas'))
const PersonalKiosco = React.lazy(() => import('@/pages/personal/PersonalKiosco'))
const PersonalProductividad = React.lazy(() => import('@/pages/personal/PersonalProductividad'))
const WMSFacturacion3PL = React.lazy(() => import('@/pages/WMSFacturacion3PL'))
const WMSTraslados = React.lazy(() => import('@/pages/WMSTraslados'))
const WMSVencimientos = React.lazy(() => import('@/pages/WMSVencimientos'))
const WMSConfig = React.lazy(() => import('@/pages/WMSConfig'))

const TMSDashboard = React.lazy(() => import('@/pages/TMSDashboard'))
const TMSViajes = React.lazy(() => import('@/pages/TMSViajes'))
const TMSPlaneacion = React.lazy(() => import('@/pages/TMSPlaneacion'))
const TMSDespachos = React.lazy(() => import('@/pages/TMSDespachos'))
const TMSTracking = React.lazy(() => import('@/pages/TMSTracking'))
const TMSVehiculos = React.lazy(() => import('@/pages/TMSVehiculos'))
const TMSConductores = React.lazy(() => import('@/pages/TMSConductores'))
const TMSTorreControl = React.lazy(() => import('@/pages/TMSTorreControl'))
const TMSRutas = React.lazy(() => import('@/pages/TMSRutas'))
const TMSDocumentos = React.lazy(() => import('@/pages/TMSDocumentos'))
const TMSCostos = React.lazy(() => import('@/pages/TMSCostos'))
const TMSOTIF = React.lazy(() => import('@/pages/TMSOTIF'))
const TMSLiquidaciones = React.lazy(() => import('@/pages/TMSLiquidaciones'))
const TMSConfig = React.lazy(() => import('@/pages/TMSConfig'))
const Fletes = React.lazy(() => import('@/pages/Fletes'))
const FletesGeneradores = React.lazy(() => import('@/pages/FletesGeneradores'))
const FletesConductores = React.lazy(() => import('@/pages/FletesConductores'))

const POSVenta = React.lazy(() => import('@/pages/POSVenta'))
const POSTurnos = React.lazy(() => import('@/pages/POSTurnos'))
const POSVentas = React.lazy(() => import('@/pages/POSVentas'))
const POSDashboard = React.lazy(() => import('@/pages/POSDashboard'))
const POSConfig = React.lazy(() => import('@/pages/POSConfig'))

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30000, retry: 1, refetchOnWindowFocus: false } },
})

function SinAcceso() {
  const navigate = useNavigate()
  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', bgcolor: PALETA.bruma, p: 3 }}>
      <Box sx={{ textAlign: 'center', maxWidth: 420 }}>
        <Distintivo tamano={56} />
        <Typography sx={{ mt: 2, fontSize: 26, fontWeight: 800, color: PALETA.tinta }}>Acceso restringido</Typography>
        <Typography sx={{ mt: 1, color: PALETA.grafito }}>
          Tu usuario o tu empresa no tienen habilitada esta sección. Si crees que es un error, habla con tu administrador.
        </Typography>
        <Box sx={{ mt: 3, display: 'flex', gap: 1.5, justifyContent: 'center' }}>
          <Button variant="outlined" onClick={() => navigate(-1)} sx={{ textTransform: 'none', borderRadius: 99 }}>Volver</Button>
          <Button variant="contained" onClick={() => navigate('/inicio')} sx={{ textTransform: 'none', borderRadius: 99 }}>Ir al inicio</Button>
        </Box>
      </Box>
    </Box>
  )
}

function RutaPortal() {
  const { isAuthenticated, portal } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (!portal) return <Navigate to="/inicio" replace />
  return <PortalDepositante />
}

function RutaLogin() {
  const { isAuthenticated, portal } = useAuthStore()
  if (isAuthenticated) return <Navigate to={portal ? '/portal' : '/inicio'} replace />
  return <Login />
}

function Protegida({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user, portal, modulos } = useAuthStore()
  const { pathname } = useLocation()

  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (portal) return <Navigate to="/portal" replace />
  if (user?.permisos === undefined) return <Navigate to="/login" replace />

  // El módulo debe estar contratado por la empresa (el servidor también lo exige).
  const prefijoModulo = Object.keys(ROUTE_MODULO_MAP).find(p => pathname === p || pathname.startsWith(p + '/'))
  if (prefijoModulo && !(modulos.includes('*') || modulos.includes(ROUTE_MODULO_MAP[prefijoModulo]))) {
    return <Navigate to="/sin-acceso" replace />
  }

  if (user.rol === 'ADMINISTRADOR') return <>{children}</>

  if (pathname === '/configuracion' && !PERMISOS_CENTRO.some(p => user.permisos[p])) {
    return <Navigate to="/sin-acceso" replace />
  }
  const prefijo = Object.keys(ROUTE_PERM_MAP)
    .filter(p => pathname === p || pathname.startsWith(p + '/'))
    .sort((a, b) => b.length - a.length)[0]
  if (prefijo && !user.permisos[ROUTE_PERM_MAP[prefijo]]) return <Navigate to="/sin-acceso" replace />
  return <>{children}</>
}

function Cargando() {
  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', bgcolor: PALETA.bruma }}>
      <Box sx={{ textAlign: 'center' }}>
        <Box sx={{ animation: 'pulseSoft 1.4s ease-in-out infinite', display: 'inline-block' }}>
          <Distintivo tamano={52} />
        </Box>
        <Typography sx={{ mt: 1.5, fontSize: 13, fontWeight: 600, color: ACENTO.base }}>Cargando…</Typography>
      </Box>
    </Box>
  )
}

const P = (el: React.ReactNode) => <Protegida>{el}</Protegida>

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Toaster
          position="bottom-right"
          toastOptions={{
            duration: 4000,
            style: {
              fontFamily: '"Plus Jakarta Sans", sans-serif', fontSize: 13.5, fontWeight: 500,
              borderRadius: 14, padding: '10px 14px', background: PALETA.tinta, color: '#FFF',
            },
            success: { iconTheme: { primary: '#22D3EE', secondary: PALETA.tinta } },
            error: { iconTheme: { primary: '#F87171', secondary: PALETA.tinta }, duration: 5000 },
          }}
        />
        <BrowserRouter>
          <Suspense fallback={<Cargando />}>
            <Routes>
              <Route path="/login" element={<RutaLogin />} />
              <Route path="/empresa" element={<Navigate to="/login" replace />} />
              <Route path="/sin-acceso" element={<SinAcceso />} />
              <Route path="/portal" element={<RutaPortal />} />
              <Route path="/scanner-movil" element={<ScannerMovil />} />

              <Route path="/" element={<Navigate to="/inicio" replace />} />
              <Route path="/inicio" element={P(<Inicio />)} />
              {/* Configuración general */}
              <Route path="/configuracion" element={P(<ConfiguracionCentro />)} />
              <Route path="/configuracion/empresa" element={P(<ConfiguracionEmpresa />)} />
              <Route path="/configuracion/catalogos" element={P(<Catalogos />)} />
              <Route path="/configuracion/usuarios" element={P(<Usuarios />)} />
              <Route path="/configuracion/roles" element={P(<Roles />)} />
              <Route path="/soporte" element={P(<Soporte />)} />
              {/* Rutas anteriores */}
              <Route path="/usuarios" element={<Navigate to="/configuracion/usuarios" replace />} />
              <Route path="/usuarios/roles" element={<Navigate to="/configuracion/roles" replace />} />

              <Route path="/wms" element={P(<WMSDashboard />)} />
              <Route path="/wms/productos" element={P(<WMSProductos />)} />
              <Route path="/wms/recepcion" element={P(<WMSRecepcion />)} />
              <Route path="/wms/inventario" element={P(<WMSInventario />)} />
              <Route path="/wms/picking" element={P(<WMSPicking />)} />
              <Route path="/wms/canales" element={P(<WMSCanalesVenta />)} />
              <Route path="/wms/pedidos-en-linea" element={P(<WMSPedidosEnLinea />)} />
              <Route path="/wms/despacho" element={P(<WMSDespacho />)} />
              <Route path="/wms/trazabilidad" element={P(<WMSTrazabilidad />)} />
              <Route path="/wms/tareas" element={P(<WMSTareas />)} />
              <Route path="/wms/estibas" element={P(<WMSEstibas />)} />
              <Route path="/wms/cubicaje" element={P(<WMSCubicaje />)} />
              <Route path="/wms/indicadores" element={P(<WMSIndicadores />)} />
              <Route path="/wms/slotting" element={P(<WMSSlotting />)} />
              <Route path="/wms/olas" element={P(<WMSOlas />)} />
              <Route path="/wms/empaque" element={P(<WMSEmpaque />)} />
              <Route path="/wms/maquila" element={P(<WMSMaquila />)} />
              <Route path="/wms/mapa" element={P(<WMSMapa />)} />
              <Route path="/wms/constructor" element={P(<WMSConstructor />)} />
              <Route path="/wms/frentes" element={P(<WMSFrentes />)} />
              <Route path="/wms/consolidacion" element={P(<WMSConsolidacion />)} />
              <Route path="/tms/asignacion-carga" element={P(<TMSAsignacionCarga />)} />
              {/* WFM · Personal (las jornadas salieron del WMS: las rutas viejas redirigen) */}
              <Route path="/wms/mi-jornada" element={<Navigate to="/personal/mi-turno" replace />} />
              <Route path="/wms/jornadas" element={<Navigate to="/personal/productividad" replace />} />
              <Route path="/personal" element={P(<PersonalTablero />)} />
              <Route path="/personal/mi-turno" element={P(<PersonalMiTurno />)} />
              <Route path="/personal/programacion" element={P(<PersonalProgramacion />)} />
              <Route path="/personal/estaciones" element={P(<PersonalEstaciones />)} />
              <Route path="/personal/personas" element={P(<PersonalPersonas />)} />
              <Route path="/personal/kiosco" element={P(<PersonalKiosco />)} />
              <Route path="/personal/productividad" element={P(<PersonalProductividad />)} />
              <Route path="/wms/facturacion" element={P(<WMSFacturacion3PL />)} />
              <Route path="/wms/traslados" element={P(<WMSTraslados />)} />
              <Route path="/wms/vencimientos" element={P(<WMSVencimientos />)} />
              <Route path="/wms/config" element={P(<WMSConfig />)} />

              <Route path="/tms" element={P(<TMSDashboard />)} />
              <Route path="/tms/viajes" element={P(<TMSViajes />)} />
              <Route path="/tms/planeacion" element={P(<TMSPlaneacion />)} />
              <Route path="/tms/despachos" element={P(<TMSDespachos />)} />
              <Route path="/tms/tracking" element={P(<TMSTracking />)} />
              <Route path="/tms/vehiculos" element={P(<TMSVehiculos />)} />
              <Route path="/tms/conductores" element={P(<TMSConductores />)} />
              <Route path="/tms/torre-control" element={P(<TMSTorreControl />)} />
              <Route path="/tms/rutas" element={P(<TMSRutas />)} />
              <Route path="/tms/documentos" element={P(<TMSDocumentos />)} />
              <Route path="/tms/costos" element={P(<TMSCostos />)} />
              <Route path="/tms/otif" element={P(<TMSOTIF />)} />
              <Route path="/tms/liquidaciones" element={P(<TMSLiquidaciones />)} />
              <Route path="/tms/config" element={P(<TMSConfig />)} />
              <Route path="/fletes" element={P(<Fletes />)} />
              <Route path="/fletes/generadores" element={P(<FletesGeneradores />)} />
              <Route path="/fletes/conductores" element={P(<FletesConductores />)} />

              <Route path="/pos" element={P(<POSVenta />)} />
              <Route path="/pos/turnos" element={P(<POSTurnos />)} />
              <Route path="/pos/ventas" element={P(<POSVentas />)} />
              <Route path="/pos/tablero" element={P(<POSDashboard />)} />
              <Route path="/pos/config" element={P(<POSConfig />)} />

              <Route path="*" element={<Navigate to="/inicio" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
