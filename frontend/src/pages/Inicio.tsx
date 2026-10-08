/**
 * Inicio: la puerta a los módulos que la empresa tiene contratados.
 */
import { useNavigate } from 'react-router-dom'
import { Box, ButtonBase, Typography, alpha } from '@mui/material'
import { ArrowForward, Warehouse, LocalShipping, PointOfSale, AdminPanelSettings } from '@mui/icons-material'
import { Layout, useModulosVisibles } from '@/components/layout/Layout'
import { useAuthStore } from '@/store/authStore'
import { clienteGuardado } from '@/api/cliente'
import { ACENTO, DESTELLO, MODULOS_DL, PALETA } from '@/config/marca'

const ICONOS: Record<string, JSX.Element> = {
  wms: <Warehouse />, tms: <LocalShipping />, pos: <PointOfSale />, config: <AdminPanelSettings />,
}

export default function Inicio() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const visibles = useModulosVisibles()
  const empresa = clienteGuardado()
  const hora = new Date().getHours()
  const saludo = hora < 12 ? 'Buenos días' : hora < 19 ? 'Buenas tardes' : 'Buenas noches'

  return (
    <Layout noPadding>
      <Box sx={{ px: { xs: 2, md: 6 }, py: { xs: 3, md: 6 }, maxWidth: 1280, width: '100%', mx: 'auto' }}>
        <Typography sx={{ color: ACENTO.base, fontWeight: 700, fontSize: 13, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          {empresa?.nombre}
        </Typography>
        <Typography sx={{ fontSize: { xs: 28, md: 38 }, fontWeight: 800, letterSpacing: '-0.03em', color: PALETA.tinta, mt: 0.5 }}>
          {saludo}, {user?.nombre}<Box component="span" sx={{ color: DESTELLO.base }}>.</Box>
        </Typography>
        <Typography sx={{ color: PALETA.grafito, mt: 1, fontSize: 15.5 }}>
          ¿Por dónde empezamos hoy?
        </Typography>

        <Box sx={{
          mt: 4, display: 'grid', gap: 2.5,
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
        }}>
          {visibles.map(m => {
            const info = MODULOS_DL.find(x => x.clave === m.clave)
            const pantallas = m.secciones.flatMap(s => s.items)
            return (
              <ButtonBase
                key={m.clave}
                onClick={() => navigate(m.inicio)}
                sx={{
                  display: 'flex', flexDirection: 'column', alignItems: 'stretch', textAlign: 'left',
                  p: 3, borderRadius: 4, bgcolor: '#FFF', border: `1px solid ${PALETA.niebla}`,
                  transition: 'all .2s',
                  '&:hover': {
                    borderColor: ACENTO.base, transform: 'translateY(-3px)',
                    boxShadow: `0 20px 40px -24px ${alpha(ACENTO.profundo, 0.55)}`,
                    '& .dl-flecha': { transform: 'translateX(4px)', color: ACENTO.base },
                  },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Box sx={{
                    width: 48, height: 48, borderRadius: 3, display: 'grid', placeItems: 'center',
                    bgcolor: ACENTO.vapor, color: ACENTO.base, '& svg': { fontSize: 26 },
                  }}>
                    {ICONOS[m.clave]}
                  </Box>
                  <Box sx={{ flex: 1 }}>
                    <Typography sx={{ fontSize: 11.5, fontWeight: 800, letterSpacing: '0.08em', color: DESTELLO.base }}>
                      {m.sigla}
                    </Typography>
                    <Typography sx={{ fontSize: 19, fontWeight: 800, color: PALETA.tinta, letterSpacing: '-0.01em' }}>
                      {m.nombre}
                    </Typography>
                  </Box>
                  <ArrowForward className="dl-flecha" sx={{ color: PALETA.acero, transition: 'all .2s' }} />
                </Box>
                <Typography sx={{ mt: 1.5, fontSize: 13.5, color: PALETA.grafito, minHeight: 40 }}>
                  {info?.descripcion ?? 'Empresa, usuarios, roles, catálogos y la configuración de cada módulo.'}
                </Typography>
                <Box sx={{ mt: 2, display: 'flex', flexWrap: 'wrap', gap: 0.7 }}>
                  {pantallas.slice(0, 5).map(p => (
                    <Box key={p.ruta} sx={{
                      fontSize: 11.5, fontWeight: 600, px: 1, py: 0.35, borderRadius: 99,
                      bgcolor: PALETA.bruma, color: PALETA.grafito,
                    }}>
                      {p.etiqueta}
                    </Box>
                  ))}
                  {pantallas.length > 5 && (
                    <Box sx={{ fontSize: 11.5, fontWeight: 700, px: 1, py: 0.35, color: ACENTO.base }}>
                      +{pantallas.length - 5}
                    </Box>
                  )}
                </Box>
              </ButtonBase>
            )
          })}
        </Box>

        {visibles.length === 0 && (
          <Typography sx={{ mt: 4, color: PALETA.grafito }}>
            Tu usuario aún no tiene módulos asignados. Pide acceso a tu administrador.
          </Typography>
        )}
      </Box>
    </Layout>
  )
}
