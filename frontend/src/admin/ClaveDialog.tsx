/**
 * La clave temporal, mostrada una sola vez.
 *
 * No se guarda en claro en ninguna parte: si se cierra este cuadro sin
 * copiarla, la única salida es restablecerla otra vez. Por eso el aviso es
 * explícito y el botón de cerrar dice lo que hace.
 */
import { useState } from 'react'
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Typography,
  Alert, IconButton, Tooltip,
} from '@mui/material'
import { ContentCopy, Check } from '@mui/icons-material'
import { PALETA } from '@/config/marca'
import type { ClaveEntregada } from './api'

export function ClaveDialog({
  acceso, empresa, onCerrar,
}: {
  acceso: ClaveEntregada | null
  empresa?: string
  onCerrar: () => void
}) {
  const [copiado, setCopiado] = useState(false)

  const copiar = async () => {
    if (!acceso) return
    const texto = [
      empresa ? `Empresa: ${empresa}` : null,
      `Usuario: ${acceso.username}`,
      `Contraseña temporal: ${acceso.clave_temporal}`,
    ].filter(Boolean).join('\n')
    try {
      await navigator.clipboard.writeText(texto)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2500)
    } catch {
      // Sin permiso de portapapeles queda visible en pantalla para copiarla a mano.
    }
  }

  return (
    <Dialog open={!!acceso} onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Acceso creado</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          Esta contraseña se muestra <strong>una sola vez</strong>. Cópiela ahora;
          si la pierde, tendrá que restablecerla de nuevo.
        </Alert>

        <Box sx={{
          bgcolor: PALETA.bruma, borderRadius: 2, p: 2,
          border: `1px solid ${PALETA.niebla}`, position: 'relative',
        }}>
          {empresa && (
            <Typography variant="caption" color="text.secondary" display="block">
              Empresa: <strong>{empresa}</strong>
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary" display="block">
            Usuario: <strong>{acceso?.username}</strong>
          </Typography>
          <Typography sx={{
            mt: 1, fontFamily: 'monospace', fontSize: 19, fontWeight: 700,
            letterSpacing: '0.06em', wordBreak: 'break-all', pr: 4,
          }}>
            {acceso?.clave_temporal}
          </Typography>
          <Tooltip title={copiado ? 'Copiado' : 'Copiar'}>
            <IconButton onClick={copiar} sx={{ position: 'absolute', top: 8, right: 8 }} size="small">
              {copiado ? <Check fontSize="small" color="success" /> : <ContentCopy fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Box>

        <Typography variant="caption" color="text.secondary" display="block" mt={2}>
          Entréguela por un canal seguro. Quien la reciba debería cambiarla apenas entre.
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} variant="contained" sx={{ textTransform: 'none' }}>
          Ya la copié, cerrar
        </Button>
      </DialogActions>
    </Dialog>
  )
}
