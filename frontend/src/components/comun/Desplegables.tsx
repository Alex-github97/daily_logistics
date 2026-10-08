/**
 * Desplegables buscables para toda la herramienta.
 *
 * Reemplazan a `TextField select`, `Select` y `FormControl` de MUI con la misma
 * forma de uso: las pantallas siguen escribiendo
 *
 *     <TextField select label="Almacén" value={v} onChange={e => …}>
 *       <MenuItem value={1}>Bodega norte</MenuItem>
 *     </TextField>
 *
 * y por dentro se dibuja un campo donde se puede escribir para filtrar las
 * opciones. Solo cambia el import de la pantalla.
 *
 * Casos que se dejan como desplegable clásico de MUI (porque no son una
 * elección simple): selección múltiple, `native` y `renderValue` propio.
 */
import React from 'react'
import {
  Autocomplete, Box, FormHelperText,
  FormControl as MuiFormControl, FormControlProps,
  Select as MuiSelect, SelectProps,
  TextField as MuiTextField, TextFieldProps,
} from '@mui/material'

interface Opcion { value: unknown; label: string; disabled?: boolean }

/** El texto visible de un nodo (para mostrar y filtrar la opción). */
function texto(n: React.ReactNode): string {
  if (n === null || n === undefined || typeof n === 'boolean') return ''
  if (typeof n === 'string' || typeof n === 'number') return String(n)
  if (Array.isArray(n)) return n.map(texto).join('')
  if (React.isValidElement(n)) return texto((n.props as { children?: React.ReactNode }).children)
  return ''
}

/** Las opciones: cada hijo con `value` (MenuItem), incluso dentro de fragmentos o listas. */
function opcionesDe(children: React.ReactNode): Opcion[] {
  const salida: Opcion[] = []
  const recorrer = (nodo: React.ReactNode) => {
    React.Children.forEach(nodo, hijo => {
      if (!React.isValidElement(hijo)) return
      const props = hijo.props as { value?: unknown; children?: React.ReactNode; disabled?: boolean }
      if (hijo.type === React.Fragment) { recorrer(props.children); return }
      if ('value' in props) {
        salida.push({ value: props.value, label: texto(props.children).trim() || String(props.value ?? ''), disabled: props.disabled })
      }
    })
  }
  recorrer(children)
  return salida
}

const igual = (a: unknown, b: unknown) => a === b || (a !== null && a !== undefined && b !== null && b !== undefined && String(a) === String(b))

interface BuscableProps {
  opciones: Opcion[]
  value: unknown
  onElegir: (v: unknown) => void
  label?: React.ReactNode
  placeholder?: string
  size?: 'small' | 'medium'
  fullWidth?: boolean
  disabled?: boolean
  required?: boolean
  error?: boolean
  helperText?: React.ReactNode
  name?: string
  autoFocus?: boolean
  sx?: TextFieldProps['sx']
  InputLabelProps?: TextFieldProps['InputLabelProps']
  variant?: TextFieldProps['variant']
  margin?: TextFieldProps['margin']
  onBlur?: TextFieldProps['onBlur']
}

function Buscable({ opciones, value, onElegir, label, placeholder, size, fullWidth, disabled, required, error,
  helperText, name, autoFocus, sx, InputLabelProps, variant, margin, onBlur }: BuscableProps) {
  const elegida = opciones.find(o => igual(o.value, value)) ?? null
  // Si hay una opción "vacía" (Todos, Ninguno…) se puede limpiar el campo; si no, no.
  const vacia = opciones.find(o => o.value === '' || o.value === null || o.value === undefined)
  return (
    <Autocomplete
      options={opciones}
      value={elegida}
      onChange={(_, o) => onElegir(o ? o.value : (vacia ? vacia.value : ''))}
      getOptionLabel={o => o.label}
      getOptionDisabled={o => !!o.disabled}
      isOptionEqualToValue={(a, b) => igual(a.value, b.value)}
      disableClearable={!vacia}
      disabled={disabled}
      size={size}
      fullWidth={fullWidth}
      sx={sx}
      autoHighlight
      openOnFocus
      noOptionsText="Sin coincidencias"
      slotProps={{ paper: { sx: { minWidth: 220 } } }}
      renderOption={(props, o) => {
        const { key, ...resto } = props as React.HTMLAttributes<HTMLLIElement> & { key: React.Key }
        return <li key={key} {...resto}>{o.label || ' '}</li>
      }}
      renderInput={params => (
        <MuiTextField
          {...params} label={label} placeholder={placeholder} required={required} error={error}
          helperText={helperText} name={name} autoFocus={autoFocus} InputLabelProps={{ ...params.InputLabelProps, ...InputLabelProps }}
          variant={variant} margin={margin} onBlur={onBlur}
        />
      )}
    />
  )
}

const evento = (value: unknown, name?: string) =>
  ({ target: { value, name }, currentTarget: { value, name } }) as unknown as React.ChangeEvent<HTMLInputElement>

/** `TextField` de MUI; con `select`, buscable. */
export function TextField(props: TextFieldProps) {
  const sp = (props.SelectProps ?? {}) as SelectProps
  if (!props.select || sp.multiple || sp.native || sp.renderValue) return <MuiTextField {...props} />
  const { children, value, onChange, label, placeholder, size, fullWidth, disabled, required, error, helperText,
    name, autoFocus, sx, InputLabelProps, variant, margin, onBlur } = props
  return (
    <Buscable
      opciones={opcionesDe(children)} value={value}
      onElegir={v => onChange?.(evento(v, name))}
      label={label} placeholder={placeholder} size={size as BuscableProps['size']} fullWidth={fullWidth}
      disabled={disabled} required={required} error={error} helperText={helperText} name={name}
      autoFocus={autoFocus} sx={sx} InputLabelProps={InputLabelProps} variant={variant} margin={margin} onBlur={onBlur}
    />
  )
}

/** `Select` de MUI; buscable salvo múltiple, nativo o con `renderValue` propio. */
export function Select<V = unknown>(props: SelectProps<V> & { __desdeFormControl?: Partial<BuscableProps> }) {
  const { __desdeFormControl: fc, ...resto } = props
  if (resto.multiple || resto.native || resto.renderValue) return <MuiSelect<V> {...resto} />
  return (
    <Buscable
      opciones={opcionesDe(resto.children)} value={resto.value}
      onElegir={v => (resto.onChange as ((e: unknown, c?: unknown) => void) | undefined)?.(evento(v, resto.name), null)}
      label={resto.label} size={(fc?.size ?? resto.size) as BuscableProps['size']} fullWidth={fc?.fullWidth ?? resto.fullWidth}
      disabled={fc?.disabled ?? resto.disabled} required={fc?.required ?? resto.required} error={fc?.error ?? resto.error}
      helperText={fc?.helperText} name={resto.name} autoFocus={resto.autoFocus} sx={fc?.sx ?? resto.sx}
    />
  )
}

/**
 * `FormControl` de MUI. Si envuelve uno de estos `Select` buscables, el campo
 * ya trae su propia etiqueta: se omite el `InputLabel` de afuera (si no, se
 * vería dos veces) y se le pasan tamaño, ancho y estado al campo.
 */
export function FormControl(props: FormControlProps) {
  const hijos = React.Children.toArray(props.children)
  const sel = hijos.find(h => React.isValidElement(h) && h.type === Select) as React.ReactElement<SelectProps> | undefined
  const p = sel?.props
  if (!sel || p?.multiple || p?.native || p?.renderValue) return <MuiFormControl {...props} />
  const ayuda = hijos.find(h => React.isValidElement(h) && h.type === FormHelperText)
  const { size, fullWidth, disabled, required, error, sx } = props
  return (
    <Box sx={{ display: fullWidth ? 'block' : 'inline-block', width: fullWidth ? '100%' : undefined, minWidth: 0 }}>
      {React.cloneElement(sel as React.ReactElement<SelectProps & { __desdeFormControl?: Partial<BuscableProps> }>, {
        __desdeFormControl: { size: size as BuscableProps['size'], fullWidth: true, disabled, required, error, sx,
                              helperText: ayuda ? texto(ayuda) : undefined },
      })}
    </Box>
  )
}
