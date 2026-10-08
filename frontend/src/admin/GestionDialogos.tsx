/**
 * Los dos diálogos que se repiten: pedir un texto y confirmar algo.
 *
 * Existen para no usar `prompt()` ni `confirm()` del navegador. No es cuestión
 * de estética: los nativos se pintan con los colores del sistema operativo,
 * salen anclados a la barra de direcciones en vez de sobre la aplicación,
 * bloquean el hilo mientras están abiertos, y no admiten ninguna explicación más
 * allá de una línea. En una pantalla de configuración —donde lo que se confirma
 * suele ser irreversible— esa línea no alcanza.
 */
import { useEffect, useState } from 'react'
import {
  Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField,
  Typography, Alert,
} from '@mui/material'
import { PALETA } from '@/config/marca'

export function DialogoTexto({
  abierto, titulo, etiqueta, ayuda, valorInicial = '', textoBoton = 'Crear',
  onCerrar, onAceptar,
}: {
  abierto: boolean
  titulo: string
  etiqueta: string
  ayuda?: string
  valorInicial?: string
  textoBoton?: string
  onCerrar: () => void
  onAceptar: (valor: string) => void
}) {
  const [valor, setValor] = useState(valorInicial)

  // Se limpia al abrir y no al cerrar: si se limpiara al cerrar, el campo se
  // vaciaría a la vista mientras el diálogo se está desvaneciendo.
  useEffect(() => { if (abierto) setValor(valorInicial) }, [abierto, valorInicial])

  function aceptar() {
    if (!valor.trim()) return
    onAceptar(valor.trim())
    onCerrar()
  }

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>{titulo}</DialogTitle>
      <DialogContent>
        <TextField
          size="small" fullWidth autoFocus label={etiqueta} helperText={ayuda}
          sx={{ mt: 0.5 }}
          value={valor} onChange={e => setValor(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') aceptar() }}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button variant="contained" disabled={!valor.trim()} onClick={aceptar}
          sx={{ textTransform: 'none' }}>
          {textoBoton}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export function DialogoConfirmar({
  abierto, titulo, mensaje, advertencia, textoBoton = 'Continuar', peligroso = false,
  onCerrar, onAceptar,
}: {
  abierto: boolean
  titulo: string
  mensaje: string
  /** Lo que no se puede deshacer. Va aparte y resaltado: mezclado con el resto
   *  del texto, es justo la línea que nadie lee. */
  advertencia?: string
  textoBoton?: string
  peligroso?: boolean
  onCerrar: () => void
  onAceptar: () => void
}) {
  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>{titulo}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ color: PALETA.grafito }}>
          {mensaje}
        </Typography>
        {advertencia && (
          <Alert severity="warning" sx={{ mt: 1.5, py: 0.5, fontSize: 12.5 }}>
            {advertencia}
          </Alert>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" color={peligroso ? 'error' : 'primary'}
          onClick={() => { onAceptar(); onCerrar() }}
          sx={{ textTransform: 'none' }}
        >
          {textoBoton}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
