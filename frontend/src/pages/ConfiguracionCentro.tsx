/**
 * Centro de configuración — /configuracion
 *
 * El punto de entrada para dejar lista la herramienta: muestra qué está
 * configurado y qué falta, en el orden en que conviene hacerlo, y lleva a cada
 * pantalla. Solo ofrece lo que el usuario puede abrir.
 */
import { useNavigate } from 'react-router-dom'
import { Box, ButtonBase, Chip, LinearProgress, Typography, alpha } from '@mui/material'
import {
  Apartment, Group, AdminPanelSettings, ListAlt, Warehouse, LocalShipping, PointOfSale,
  Badge, CheckCircle, RadioButtonUnchecked, ArrowForward,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Layout, useModulosVisibles } from '@/components/layout/Layout'
import { apiClient } from '@/api/client'
import { ACENTO, PALETA } from '@/config/marca'

interface Resumen {
  empresa: boolean; usuarios: number; roles: number; almacenes: number; productos: number
  vehiculos: number; conductores: number; cajas: number; resoluciones: number
}

interface Tarjeta {
  ruta: string
  titulo: string
  texto: string
  icono: JSX.Element
  grupo: string
  /** Si está lista, y el dato que lo demuestra. */
  estado?: (r: Resumen) => { listo: boolean; dato: string }
}

const TARJETAS: Tarjeta[] = [
  {
    grupo: 'Empresa', ruta: '/configuracion/empresa', titulo: 'Datos de la empresa', icono: <Apartment />,
    texto: 'Razón social, NIT y datos de contacto. Los usan las facturas del POS y del WMS.',
    estado: r => ({ listo: r.empresa, dato: r.empresa ? 'Registrados' : 'Pendiente' }),
  },
  {
    grupo: 'Empresa', ruta: '/configuracion/catalogos', titulo: 'Catálogos maestros', icono: <ListAlt />,
    texto: 'Listas controladas compartidas y de WMS, TMS y POS.',
  },
  {
    grupo: 'Usuarios y roles', ruta: '/configuracion/roles', titulo: 'Roles y permisos', icono: <AdminPanelSettings />,
    texto: 'Qué puede ver cada perfil: WMS, TMS, POS, usuarios y configuración.',
    estado: r => ({ listo: r.roles > 0, dato: `${r.roles} roles` }),
  },
  {
    grupo: 'Usuarios y roles', ruta: '/configuracion/usuarios', titulo: 'Usuarios', icono: <Group />,
    texto: 'Cree a cada persona, asígnele su rol y restablezca contraseñas.',
    estado: r => ({ listo: r.usuarios > 1, dato: `${r.usuarios} activos` }),
  },
  {
    grupo: 'Módulos', ruta: '/wms/config', titulo: 'Almacén (WMS)', icono: <Warehouse />,
    texto: 'Almacenes, zonas, ubicaciones, depositantes y tarifas 3PL. Los productos se crean en WMS › Productos.',
    estado: r => ({ listo: r.almacenes > 0 && r.productos > 0, dato: `${r.almacenes} almacenes · ${r.productos} productos` }),
  },
  {
    grupo: 'Módulos', ruta: '/tms/config', titulo: 'Transporte (TMS)', icono: <LocalShipping />,
    texto: 'Zonas, tipos de servicio, parámetros OTIF y documentos requeridos.',
    estado: r => ({ listo: r.vehiculos > 0, dato: `${r.vehiculos} vehículos` }),
  },
  {
    grupo: 'Módulos', ruta: '/tms/conductores', titulo: 'Conductores', icono: <Badge />,
    texto: 'Conductores con su licencia y los vehículos que pueden manejar.',
    estado: r => ({ listo: r.conductores > 0, dato: `${r.conductores} activos` }),
  },
  {
    grupo: 'Módulos', ruta: '/pos/config', titulo: 'Punto de venta (POS)', icono: <PointOfSale />,
    texto: 'Cajas, listas de precios, zonas vendibles y resoluciones DIAN.',
    estado: r => ({ listo: r.cajas > 0 && r.resoluciones > 0, dato: `${r.cajas} cajas · ${r.resoluciones} resoluciones` }),
  },
]

export default function ConfiguracionCentro() {
  const navigate = useNavigate()
  const visibles = useModulosVisibles()
  const { data: resumen } = useQuery<Resumen>({
    queryKey: ['configuracion-resumen'],
    queryFn: () => apiClient.get('/configuracion/resumen').then(r => r.data),
  })

  // Solo las pantallas que este usuario puede abrir.
  const rutasPermitidas = new Set(
    visibles.find(m => m.clave === 'config')?.secciones.flatMap(s => s.items.map(i => i.ruta)) ?? [],
  )
  const tarjetas = TARJETAS.filter(t => rutasPermitidas.has(t.ruta))
  const conEstado = tarjetas.filter(t => t.estado && resumen)
  const listas = conEstado.filter(t => t.estado!(resumen!).listo).length
  const grupos = Array.from(new Set(tarjetas.map(t => t.grupo)))

  return (
    <Layout title="Centro de configuración">
      <Typography sx={{ color: PALETA.grafito, mb: 2.5, maxWidth: 760 }}>
        Todo lo que necesita la herramienta para operar, en el orden recomendado: primero la empresa,
        luego los usuarios y sus roles, y por último cada módulo.
      </Typography>

      {conEstado.length > 0 && (
        <Box sx={{ mb: 3, p: 2.5, bgcolor: '#FFF', borderRadius: 3, border: `1px solid ${PALETA.niebla}`, maxWidth: 760 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography sx={{ fontWeight: 700 }}>Puesta en marcha</Typography>
            <Typography sx={{ fontWeight: 700, color: ACENTO.base }}>{listas} de {conEstado.length} listas</Typography>
          </Box>
          <LinearProgress variant="determinate" value={(listas / conEstado.length) * 100}
            sx={{ height: 8, borderRadius: 9, bgcolor: ACENTO.vapor }} />
        </Box>
      )}

      {grupos.map(g => (
        <Box key={g} sx={{ mb: 3 }}>
          <Typography sx={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: ACENTO.base, mb: 1.2 }}>
            {g}
          </Typography>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' } }}>
            {tarjetas.filter(t => t.grupo === g).map(t => {
              const est = t.estado && resumen ? t.estado(resumen) : null
              return (
                <ButtonBase key={t.ruta} onClick={() => navigate(t.ruta)} sx={{
                  display: 'flex', flexDirection: 'column', alignItems: 'stretch', textAlign: 'left',
                  p: 2.2, borderRadius: 3, bgcolor: '#FFF', border: `1px solid ${PALETA.niebla}`, transition: 'all .2s',
                  '&:hover': { borderColor: ACENTO.base, boxShadow: `0 14px 30px -20px ${alpha(ACENTO.profundo, 0.6)}`,
                    '& .flecha': { color: ACENTO.base, transform: 'translateX(3px)' } },
                }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2 }}>
                    <Box sx={{ width: 38, height: 38, borderRadius: 2, display: 'grid', placeItems: 'center',
                      bgcolor: ACENTO.vapor, color: ACENTO.base }}>{t.icono}</Box>
                    <Typography sx={{ flex: 1, fontWeight: 800, fontSize: 15, color: PALETA.tinta }}>{t.titulo}</Typography>
                    <ArrowForward className="flecha" sx={{ fontSize: 18, color: PALETA.acero, transition: 'all .2s' }} />
                  </Box>
                  <Typography sx={{ mt: 1.2, fontSize: 13, color: PALETA.grafito, flex: 1 }}>{t.texto}</Typography>
                  {est && (
                    <Chip
                      size="small"
                      icon={est.listo ? <CheckCircle /> : <RadioButtonUnchecked />}
                      label={est.dato}
                      sx={{
                        mt: 1.5, alignSelf: 'flex-start', fontWeight: 700,
                        bgcolor: est.listo ? '#DCFCE7' : '#FEF3C7', color: est.listo ? '#15803D' : '#B45309',
                        '& .MuiChip-icon': { color: 'inherit' },
                      }}
                    />
                  )}
                </ButtonBase>
              )
            })}
          </Box>
        </Box>
      ))}
    </Layout>
  )
}
