/**
 * Elegir del catálogo —y, si falta el valor, agregarlo sin salir del
 * formulario—. Es la diferencia entre una lista que se administra y una que
 * obliga a abandonar lo que se estaba registrando para ir a Configuración.
 *
 * Guarda el NOMBRE del valor (lo que almacenan las tablas); el servidor lo
 * valida contra el catálogo.
 */
import { useState } from 'react'
import { Autocomplete, TextField, createFilterOptions } from '@mui/material'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient as api } from '@/api/client'
import { useCatalogo } from './SelectorCatalogo'

type Opcion = { nombre: string; nuevo?: boolean }
const filtro = createFilterOptions<Opcion>()

export function CatalogoAuto({
  modulo, tipo, label, valor, onChange, multiple = false, agregar = true,
  requerido, error, ayuda,
}: {
  modulo: string; tipo: string; label: string
  valor: string | string[] | null
  onChange: (v: any) => void
  multiple?: boolean
  /** Permite crear el valor desde aquí. Apagado para catálogos compartidos
   *  que solo se administran en un sitio (procesos, áreas). */
  agregar?: boolean
  requerido?: boolean; error?: boolean; ayuda?: string
}) {
  const qc = useQueryClient()
  const { data: items = [], isLoading } = useCatalogo(modulo, tipo)
  const [creando, setCreando] = useState(false)
  const opciones: Opcion[] = items.map(i => ({ nombre: i.nombre }))
  const actual = multiple
    ? ((valor as string[]) ?? []).map(n => ({ nombre: n }))
    : valor ? { nombre: valor as string } : null

  const crear = async (nombre: string) => {
    setCreando(true)
    try {
      await api.post('/catalogos', { modulo, tipo, nombre })
      await qc.invalidateQueries({ queryKey: ['catalogo', modulo, tipo] })
      toast.success(`«${nombre}» agregado al catálogo`)
      return true
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'No se pudo agregar al catálogo')
      return false
    } finally { setCreando(false) }
  }

  return (
    <Autocomplete<Opcion, boolean, false, false>
      multiple={multiple} size="small" fullWidth loading={isLoading || creando}
      options={opciones} value={actual as any}
      isOptionEqualToValue={(a, b) => a.nombre === b.nombre}
      getOptionLabel={o => (o.nuevo ? `Agregar «${o.nombre}» al catálogo` : o.nombre)}
      filterOptions={(ops, params) => {
        const f = filtro(ops, params)
        const t = params.inputValue.trim()
        if (agregar && t && !ops.some(o => o.nombre.toLowerCase() === t.toLowerCase())) f.push({ nombre: t, nuevo: true })
        return f
      }}
      onChange={async (_, v: any) => {
        if (multiple) {
          const lista: Opcion[] = v ?? []
          const nuevo = lista.find(o => o.nuevo)
          if (nuevo && !(await crear(nuevo.nombre))) return
          onChange(lista.map(o => o.nombre))
        } else {
          if (v?.nuevo && !(await crear(v.nombre))) return
          onChange(v ? v.nombre : null)
        }
      }}
      noOptionsText={agregar ? 'Escriba para agregar' : 'Sin valores: se agregan en Configuración'}
      renderInput={p => <TextField {...p} label={label} required={requerido} error={error}
        helperText={ayuda} />}
    />
  )
}
