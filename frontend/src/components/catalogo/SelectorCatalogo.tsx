/**
 * Desplegables contra el catálogo maestro, para cualquier módulo.
 *
 * Reemplazan los campos de texto libre de clasificación. Guardan el nombre y no
 * el id, que es lo que ya almacenan las tablas de cada módulo; el backend valida
 * y normaliza contra el catálogo al guardar.
 */
import { useMemo } from 'react'
import {
  MenuItem, Typography, Stack,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { useQuery } from '@tanstack/react-query'
import { apiClient as api } from '@/api/client'

export interface ValorCatalogo {
  id: number
  modulo: string
  tipo: string
  nombre: string
  codigo?: string | null
  padre_id?: number | null
  padre_nombre?: string | null
  orden?: number | null
  color?: string | null
  metadatos?: Record<string, unknown> | null
  activo?: boolean
  total_hijos?: number
}

export interface RegistroCatalogo {
  modulo: string
  tipo: string
  label: string
  descripcion: string
  padre?: string | null
  total: number
}

/** Valores de un catálogo. Hook compartido para no repetir la query. */
export function useCatalogo(
  modulo: string, tipo: string, padreId?: number | null, habilitado = true,
) {
  return useQuery<ValorCatalogo[]>({
    queryKey: ['catalogo', modulo, tipo, padreId ?? null],
    queryFn: () => api.get('/catalogos', {
      params: {
        modulo, tipo, solo_activos: true,
        ...(padreId != null ? { padre_id: padreId } : {}),
      },
    }).then(r => r.data),
    enabled: habilitado && Boolean(modulo) && Boolean(tipo),
  })
}

/**
 * Un solo desplegable. Si el valor guardado no está en el catálogo — porque se
 * escribió a mano antes de que la lista existiera — se agrega como opción
 * marcada, en vez de vaciar el campo en silencio al editar.
 */
export function SelectorCatalogo({
  modulo, tipo, label, valor, onChange, onChangeEvento,
  padreId, requerido = false, deshabilitado = false, ayuda, sx,
}: {
  modulo: string
  tipo: string
  label: string
  valor: string
  onChange?: (nombre: string, item?: ValorCatalogo) => void
  /**
   * Adaptador para las páginas cuyo handler está escrito al estilo
   * `onChange={f('ciudad')}`, donde `f` devuelve un manejador que espera un
   * ChangeEvent. Permite reemplazar el TextField sin reescribir el manejo de
   * estado de la página. El tipo va suelto a propósito: del otro lado hay
   * handlers de React tipados con el evento completo.
   */
  onChangeEvento?: (e: any) => void
  /** Acota al nivel de arriba (las ciudades de un departamento). */
  padreId?: number | null
  requerido?: boolean
  deshabilitado?: boolean
  ayuda?: string
  /** Se pasa tal cual al campo, para conservar el layout donde reemplaza a un
   *  TextField que traía su propio sx (flex, minWidth…). */
  sx?: object
}) {
  const { data: items = [] } = useCatalogo(modulo, tipo, padreId, !deshabilitado)

  const huerfano = Boolean(valor) && !items.some(i => i.nombre === valor)

  return (
    <TextField
      select size="small" fullWidth sx={sx}
      label={requerido ? `${label} *` : label}
      value={valor} disabled={deshabilitado}
      onChange={e => {
        const nombre = e.target.value
        onChange?.(nombre, items.find(i => i.nombre === nombre))
        onChangeEvento?.({ target: { value: nombre, name: tipo } })
      }}
      helperText={
        huerfano
          ? 'Valor fuera del catálogo; se conserva hasta que lo cambie'
          : items.length === 0 && !deshabilitado
            ? (ayuda ?? 'Sin valores. Agréguelos en la configuración del módulo.')
            : ayuda
      }
    >
      <MenuItem value="">Sin especificar</MenuItem>
      {huerfano && (
        <MenuItem value={valor}>
          {valor}
          <Typography component="span" variant="caption" color="warning.main" sx={{ ml: 0.75 }}>
            · fuera del catálogo
          </Typography>
        </MenuItem>
      )}
      {items.map(i => (
        <MenuItem key={i.id} value={i.nombre}>
          {i.nombre}
          {i.codigo && (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.75 }}>
              · {i.codigo}
            </Typography>
          )}
        </MenuItem>
      ))}
    </TextField>
  )
}

export interface SeleccionJerarquia {
  /** Nombre elegido en cada nivel, por tipo. */
  nombres: Record<string, string>
  /** Id elegido en cada nivel, para poder acotar el nivel siguiente. */
  ids: Record<string, number | null>
}

export const JERARQUIA_VACIA: SeleccionJerarquia = { nombres: {}, ids: {} }

/**
 * Cadena de desplegables encadenados: cada nivel se habilita con el anterior y
 * cambiarlo invalida los de abajo.
 *
 * Se usa para geografía (país → departamento → ciudad), para sede → área y para
 * cualquier catálogo que el registro declare con padre.
 */
export function SelectorCatalogoJerarquico({
  modulo, niveles, valor, onChange, requerido = false, anchoNivel,
}: {
  modulo: string
  /** Del más general al más específico. */
  niveles: { tipo: string; label: string }[]
  valor: SeleccionJerarquia
  onChange: (v: SeleccionJerarquia) => void
  requerido?: boolean
  /** Columnas de la rejilla por nivel; por defecto se reparte el ancho. */
  anchoNivel?: number
}) {
  const ancho = anchoNivel ?? Math.max(Math.floor(12 / Math.max(niveles.length, 1)), 3)

  const elegir = (indice: number, nombre: string, item?: ValorCatalogo) => {
    // Los niveles de abajo dejan de tener sentido: se limpian
    const nombres: Record<string, string> = {}
    const ids: Record<string, number | null> = {}
    for (let i = 0; i < indice; i++) {
      const t = niveles[i].tipo
      nombres[t] = valor.nombres[t] ?? ''
      ids[t] = valor.ids[t] ?? null
    }
    nombres[niveles[indice].tipo] = nombre
    ids[niveles[indice].tipo] = item?.id ?? null
    onChange({ nombres, ids })
  }

  return (
    <Grid container spacing={2}>
      {niveles.map((n, i) => {
        const padreTipo = i > 0 ? niveles[i - 1].tipo : undefined
        const padreId = padreTipo ? valor.ids[padreTipo] : undefined
        const bloqueado = i > 0 && !padreId
        return (
          <Grid key={n.tipo} size={{ xs: 12, sm: ancho }}>
            <SelectorCatalogo
              modulo={modulo} tipo={n.tipo} label={n.label}
              valor={valor.nombres[n.tipo] ?? ''}
              onChange={(nombre, item) => elegir(i, nombre, item)}
              padreId={padreId}
              requerido={requerido && i === niveles.length - 1}
              deshabilitado={bloqueado}
              ayuda={bloqueado ? `Elija ${niveles[i - 1].label.toLowerCase()} primero` : undefined}
            />
          </Grid>
        )
      })}
    </Grid>
  )
}

/** Atajo para el caso más común: país → departamento → ciudad. */
export function SelectorUbicacionGeografica({
  valor, onChange, requerido = false,
}: {
  valor: SeleccionJerarquia
  onChange: (v: SeleccionJerarquia) => void
  requerido?: boolean
}) {
  const niveles = useMemo(() => [
    { tipo: 'PAIS', label: 'País' },
    { tipo: 'DEPARTAMENTO', label: 'Departamento' },
    { tipo: 'CIUDAD', label: 'Ciudad' },
  ], [])
  return (
    <SelectorCatalogoJerarquico
      modulo="GLOBAL" niveles={niveles} valor={valor}
      onChange={onChange} requerido={requerido} anchoNivel={4}
    />
  )
}
