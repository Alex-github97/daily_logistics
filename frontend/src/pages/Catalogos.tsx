/**
 * Catálogos maestros — /configuracion/catalogos
 *
 * Clonado de la plataforma madre. En Daily Logistics solo se muestran los
 * catálogos compartidos y los de WMS, TMS y POS.
 */
import { useMemo, useState } from 'react'
import {
  Box, Typography, Stack, Card, CardContent, Chip, MenuItem, alpha, Alert,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Inventory2, Public, Insights } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { COLOR_MODULO } from '@/config/marca'
import { apiClient as api } from '@/api/client'
import { AdminCatalogos } from '@/components/catalogo/AdminCatalogos'
import type { RegistroCatalogo } from '@/components/catalogo/SelectorCatalogo'

const COLOR = COLOR_MODULO

// Los catálogos que administra Daily Logistics.
const MODULOS_DL = ['GLOBAL', 'WMS', 'TMS', 'POS']

const NOMBRE_MODULO: Record<string, string> = {
  GLOBAL: 'Compartidos (todos los módulos)',
  HCM: 'Gestión Humana',
  WMS: 'Almacén WMS',
  TMS: 'Transporte TMS',
  SST: 'Seguridad y Salud',
  QMS: 'Calidad QMS',
  GRC: 'Gobierno GRC',
  LMS: 'Aprendizaje LMS',
  DMS: 'Documentos DMS',
  SCM: 'Cadena de Suministro',
  ERP: 'ERP Financiero',
  MES: 'Manufactura MES',
  APS: 'Planeación APS',
  CRM: 'CRM Clientes',
  EAM: 'CMMS / EAM Mantenimiento',
  CI: 'Control de Estibas',
  POS: 'Punto de venta POS',
  AGS: 'Agenda de Servicios',
  FLOTA: 'Gestión de Flotas',
  LOCATIVA: 'Mantenimiento Locativo',
}

export default function Catalogos() {
  const [modulo, setModulo] = useState('GLOBAL')

  const { data: registro = [] } = useQuery<RegistroCatalogo[]>({
    queryKey: ['catalogo-registro-todos'],
    queryFn: () => api.get('/catalogos/registro').then(r => r.data),
  })

  const modulos = useMemo(() => {
    const unicos = Array.from(new Set(registro.map(r => r.modulo))).filter(m => MODULOS_DL.includes(m))
    // GLOBAL primero: es el que afecta a todos
    return unicos.sort((a, b) => (a === 'GLOBAL' ? -1 : b === 'GLOBAL' ? 1 : a.localeCompare(b)))
  }, [registro])

  const resumen = useMemo(() => {
    const delModulo = registro.filter(r => r.modulo === modulo)
    return {
      catalogos: delModulo.length,
      valores: delModulo.reduce((s, r) => s + r.total, 0),
      vacios: delModulo.filter(r => r.total === 0).length,
      totalPlataforma: registro.filter(r => MODULOS_DL.includes(r.modulo)).reduce((s, r) => s + r.total, 0),
    }
  }, [registro, modulo])

  return (
    <Layout title="Catálogos maestros">
      <Box className="anim-page-in">
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between"
          alignItems={{ md: 'center' }} gap={2} mb={2}>
          <Typography variant="body2" color="text.secondary">
            Las listas controladas de la herramienta, en un solo lugar
          </Typography>
          <TextField
            select size="small" label="Módulo" value={modulo}
            onChange={e => setModulo(e.target.value)}
            sx={{ minWidth: 280 }}
          >
            {modulos.map(m => (
              <MenuItem key={m} value={m}>{NOMBRE_MODULO[m] ?? m}</MenuItem>
            ))}
          </TextField>
        </Stack>

        <Grid container spacing={2} mb={2}>
          {[
            { t: 'Catálogos del módulo', v: String(resumen.catalogos), i: <Inventory2 />, c: COLOR },
            { t: 'Valores configurados', v: String(resumen.valores), i: <Insights />, c: '#16A34A' },
            { t: 'Sin configurar', v: String(resumen.vacios), i: <Public />,
              c: resumen.vacios > 0 ? '#CA8A04' : '#64748B' },
            { t: 'Valores en la plataforma', v: String(resumen.totalPlataforma), i: <Inventory2 />, c: '#0891B2' },
          ].map(k => (
            <Grid key={k.t} size={{ xs: 6, md: 3 }}>
              <Card sx={{ borderLeft: `4px solid ${k.c}` }}>
                <CardContent sx={{ p: 1.8 }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Box>
                      <Typography variant="caption" color="text.secondary">{k.t}</Typography>
                      <Typography variant="h5" fontWeight={800}>{k.v}</Typography>
                    </Box>
                    <Box sx={{ color: k.c, opacity: 0.65 }}>{k.i}</Box>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        {modulo === 'GLOBAL' && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Los catálogos compartidos los usan todos los módulos. Renombrar o desactivar un
            valor acá se refleja en toda la herramienta.
          </Alert>
        )}

        <Card sx={{ bgcolor: '#FFFFFF' }}>
          <CardContent>
            {/* Al ver GLOBAL no se repiten los compartidos dentro de la lista */}
            <AdminCatalogos
              key={modulo} modulo={modulo} color={COLOR}
              incluirGlobales={modulo === 'GLOBAL'}
            />
          </CardContent>
        </Card>
      </Box>
    </Layout>
  )
}
