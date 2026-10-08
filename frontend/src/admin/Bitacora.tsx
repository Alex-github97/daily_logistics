/**
 * Lo que el operador ha hecho sobre las empresas.
 *
 * Existe porque esta consola permite crear usuarios dentro de cualquier empresa
 * y devolverles la clave: eso alcanza para entrar a la cuenta de un cliente, y
 * un poder así tiene que dejar rastro consultable.
 */
import {
  Box, Card, Typography, Table, TableBody, TableCell, TableHead, TableRow,
  Chip, Skeleton, Stack,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { consolaApi } from './api'
import { aFecha } from '@/utils/fechas'

/** Cada acción con su nombre en castellano y el color de su gravedad. */
const ACCIONES: Record<string, { texto: string; color: string }> = {
  'empresa.alta':          { texto: 'Alta de empresa',        color: COLOR_MODULO },
  'empresa.edicion':       { texto: 'Edición de empresa',     color: PALETA.grafito },
  'empresa.suspension':    { texto: 'Suspensión',             color: ESTADO.peligro },
  'empresa.reactivacion':  { texto: 'Reactivación',           color: ESTADO.exito },
  'usuario.alta':          { texto: 'Alta de usuario',        color: COLOR_MODULO },
  'usuario.edicion':       { texto: 'Edición de usuario',     color: PALETA.grafito },
  'usuario.clave':         { texto: 'Clave restablecida',     color: ESTADO.alerta },
}

const fecha = (iso: string) => {
  const d = aFecha(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })
}

export default function Bitacora() {
  const { data: asientos = [], isLoading } = useQuery({
    queryKey: ['bitacora'], queryFn: () => consolaApi.bitacora(),
  })

  return (
    <Box>
      <Stack mb={2.5}>
        <Typography variant="h6" fontWeight={800}>Bitácora</Typography>
        <Typography variant="caption" color="text.secondary">
          Cada acción del operador sobre una empresa o sus usuarios. No se puede editar ni borrar.
        </Typography>
      </Stack>

      <Card sx={{ borderRadius: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>FECHA</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ACCIÓN</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>EMPRESA</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>QUIÉN</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>DETALLE</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && [0, 1, 2].map(i => (
              <TableRow key={i}><TableCell colSpan={5}><Skeleton height={28} /></TableCell></TableRow>
            ))}
            {asientos.map(a => {
              const meta = ACCIONES[a.accion] ?? { texto: a.accion, color: PALETA.grafito }
              return (
                <TableRow key={a.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                    {fecha(a.fecha)}
                  </TableCell>
                  <TableCell>
                    <Chip label={meta.texto} size="small" sx={{
                      fontWeight: 700, fontSize: 11,
                      bgcolor: `${meta.color}1A`, color: meta.color,
                    }} />
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                    {a.empresa_codigo ?? '—'}
                  </TableCell>
                  <TableCell sx={{ color: PALETA.grafito }}>
                    {a.actor} · {a.actor_empresa}
                  </TableCell>
                  <TableCell sx={{ color: PALETA.grafito }}>{a.detalle ?? '—'}</TableCell>
                </TableRow>
              )
            })}
            {!isLoading && asientos.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Typography variant="body2" sx={{ textAlign: 'center', py: 4, color: PALETA.acero }}>
                    Todavía no hay movimientos registrados
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </Box>
  )
}
