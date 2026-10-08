/**
 * WMS · Constructor de bodega: el layout de cada almacén (estanterías, áreas,
 * muros, columnas) y de ahí sus ubicaciones y la bodega 3D. Es el mismo editor
 * de la pestaña «Constructor» del mapa, con página propia en el menú.
 */
import { useEffect, useState } from 'react'
import { Box, MenuItem, Stack, Typography } from '@mui/material'
import { Architecture } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { Encabezado } from '@/components/comun/Registro'
import { TextField } from '@/components/comun/Desplegables'
import { wms } from '@/api/wmsTrazable'
import { COLOR_MODULO } from '@/config/marca'
import ConstructorBodega from '@/components/wms/ConstructorBodega'

export default function WMSConstructor() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const almacenes = useQuery({ queryKey: ['wms-almacenes'], queryFn: wms.almacenes })
  const [almacen, setAlmacen] = useState<number | ''>(Number(params.get('almacen')) || '')
  useEffect(() => { if (!almacen && almacenes.data?.length) setAlmacen(almacenes.data[0].id) }, [almacenes.data, almacen])
  const elegir = (id: number) => { setAlmacen(id); setParams({ almacen: String(id) }, { replace: true }) }
  return (
    <Layout title="WMS — Constructor de bodega">
      <Box sx={{ p: 3 }}>
        <Encabezado icono={<Architecture sx={{ fontSize: 28 }} />} titulo="Constructor de bodega" color={COLOR_MODULO}
          subtitulo="Dibuje el layout del almacén en metros: estanterías, áreas, muros y columnas. De aquí salen las ubicaciones del WMS y la bodega 3D." />
        <Stack direction="row" gap={1.5} mb={2} alignItems="center" flexWrap="wrap">
          <TextField select size="small" label="Almacén" value={almacen} onChange={e => elegir(Number(e.target.value))} sx={{ minWidth: 260 }}>
            {(almacenes.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          <Typography fontSize={12.5} color="text.secondary">Los cambios se guardan por almacén · el plano de fondo se carga en Mapa de bodega › Plano.</Typography>
        </Stack>
        {!!almacen && <ConstructorBodega key={almacen} almacen={Number(almacen)} onVer3D={() => navigate('/wms/mapa')} />}
      </Box>
    </Layout>
  )
}
