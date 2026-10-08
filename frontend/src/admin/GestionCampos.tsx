/**
 * El formulario de los campos configurables.
 *
 * No hay una lista de campos escrita acá: la definición llega del servidor, que
 * es el mismo sitio del que sale la validación. Si la pantalla tuviera su propia
 * idea de qué campos existen, tarde o temprano aceptaría algo que el servidor
 * descarta y quien lo escribió perdería lo tecleado sin entender por qué.
 *
 * Por eso agregar un campo nuevo no toca este archivo: se define en la
 * configuración y aparece solo.
 */
import {
  Box, MenuItem, Switch, FormControlLabel, Chip, Stack, Typography, OutlinedInput, InputLabel, FormHelperText,
} from '@mui/material'
import { TextField, Select, FormControl } from '@/components/comun/Desplegables'
import { PALETA } from '@/config/marca'
import type { DefinicionCampo } from './api'

/** Los errores que devuelve el servidor vienen por campo, con el nombre visible
 *  por delante: se buscan por ahí para poder pintarlos bajo su control. */
export function errorDe(campo: DefinicionCampo, problemas: string[]): string | undefined {
  return problemas.find(p => p.startsWith(`«${campo.nombre}»`))
    ?.replace(`«${campo.nombre}» `, '')
}

export function CamposDinamicos({
  definicion, valores, onCambio, problemas = [], soloLectura = false,
}: {
  definicion: DefinicionCampo[]
  valores: Record<string, any>
  onCambio: (clave: string, valor: any) => void
  problemas?: string[]
  soloLectura?: boolean
}) {
  if (!definicion.length) return null

  return (
    <Stack spacing={2}>
      {definicion.map(campo => {
        const valor = valores[campo.clave]
        const error = errorDe(campo, problemas)
        const bloqueado = soloLectura || campo.solo_lectura
        const comun = {
          size: 'small' as const,
          fullWidth: true,
          label: campo.nombre,
          required: campo.obligatorio,
          disabled: bloqueado,
          error: !!error,
          helperText: error || campo.ayuda || undefined,
        }

        switch (campo.tipo) {
          case 'BOOLEANO':
            return (
              <Box key={campo.clave}>
                <FormControlLabel
                  control={
                    <Switch
                      size="small" disabled={bloqueado}
                      checked={valor === true || valor === 'true'}
                      onChange={e => onCambio(campo.clave, e.target.checked)}
                    />
                  }
                  label={campo.nombre}
                />
                {(error || campo.ayuda) && (
                  <FormHelperText error={!!error}>{error || campo.ayuda}</FormHelperText>
                )}
              </Box>
            )

          case 'LISTA':
            return (
              <TextField
                key={campo.clave} {...comun} select
                value={valor ?? ''}
                onChange={e => onCambio(campo.clave, e.target.value || null)}
              >
                {/* Vacío borra el valor. Es distinto de no tocar el campo, y hay
                    que poder hacer las dos cosas. */}
                <MenuItem value=""><em>Sin definir</em></MenuItem>
                {campo.opciones.map(o => (
                  <MenuItem key={o.valor} value={o.valor}>{o.etiqueta}</MenuItem>
                ))}
              </TextField>
            )

          case 'LISTA_MULTIPLE':
            return (
              <FormControl key={campo.clave} size="small" fullWidth error={!!error}
                disabled={bloqueado}>
                <InputLabel>{campo.nombre}</InputLabel>
                <Select
                  multiple label={campo.nombre}
                  value={Array.isArray(valor) ? valor : []}
                  input={<OutlinedInput label={campo.nombre} />}
                  onChange={e => onCambio(campo.clave, e.target.value)}
                  renderValue={sel => (
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {(sel as string[]).map(v => (
                        <Chip key={v} size="small" sx={{ height: 20, fontSize: 11 }}
                          label={campo.opciones.find(o => o.valor === v)?.etiqueta ?? v} />
                      ))}
                    </Stack>
                  )}
                >
                  {campo.opciones.map(o => (
                    <MenuItem key={o.valor} value={o.valor}>{o.etiqueta}</MenuItem>
                  ))}
                </Select>
                {(error || campo.ayuda) && (
                  <FormHelperText>{error || campo.ayuda}</FormHelperText>
                )}
              </FormControl>
            )

          case 'ETIQUETAS':
            return (
              <TextField
                key={campo.clave} {...comun}
                helperText={error || campo.ayuda || 'Separadas por comas'}
                value={Array.isArray(valor) ? valor.join(', ') : (valor ?? '')}
                onChange={e => onCambio(
                  campo.clave,
                  e.target.value.split(',').map(t => t.trim()).filter(Boolean))}
              />
            )

          case 'TEXTO_LARGO':
            return (
              <TextField key={campo.clave} {...comun} multiline minRows={3}
                value={valor ?? ''} onChange={e => onCambio(campo.clave, e.target.value)} />
            )

          case 'NUMERO':
          case 'DECIMAL':
            return (
              <TextField
                key={campo.clave} {...comun} type="number"
                inputProps={{
                  min: campo.validacion?.min, max: campo.validacion?.max,
                  step: campo.tipo === 'DECIMAL' ? 'any' : 1,
                }}
                value={valor ?? ''}
                onChange={e => onCambio(campo.clave, e.target.value)}
              />
            )

          case 'FECHA':
          case 'FECHA_HORA':
            return (
              <TextField
                key={campo.clave} {...comun}
                type={campo.tipo === 'FECHA' ? 'date' : 'datetime-local'}
                InputLabelProps={{ shrink: true }}
                value={(valor ?? '').toString().slice(0, campo.tipo === 'FECHA' ? 10 : 16)}
                onChange={e => onCambio(campo.clave, e.target.value)}
              />
            )

          default:
            return (
              <TextField key={campo.clave} {...comun}
                value={valor ?? ''} onChange={e => onCambio(campo.clave, e.target.value)} />
            )
        }
      })}
    </Stack>
  )
}

/** Lo que se muestra de un campo en el detalle, ya legible. */
export function ValorLegible({ campo, valor }: { campo: DefinicionCampo; valor: any }) {
  if (valor === null || valor === undefined || valor === '' ||
      (Array.isArray(valor) && !valor.length)) {
    return <Typography variant="body2" sx={{ color: PALETA.acero }}>—</Typography>
  }

  if (campo.tipo === 'BOOLEANO') {
    return <Typography variant="body2">{valor ? 'Sí' : 'No'}</Typography>
  }

  if (campo.tipo === 'LISTA') {
    const o = campo.opciones.find(x => x.valor === valor)
    return (
      <Chip size="small" label={o?.etiqueta ?? String(valor)}
        sx={{ height: 20, fontSize: 11, bgcolor: o?.color ? `${o.color}1F` : PALETA.niebla,
              color: o?.color || 'inherit' }} />
    )
  }

  if (Array.isArray(valor)) {
    return (
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
        {valor.map(v => (
          <Chip key={String(v)} size="small" label={
            campo.opciones.find(o => o.valor === v)?.etiqueta ?? String(v)}
            sx={{ height: 20, fontSize: 11, bgcolor: PALETA.niebla }} />
        ))}
      </Stack>
    )
  }

  return <Typography variant="body2">{String(valor)}</Typography>
}
