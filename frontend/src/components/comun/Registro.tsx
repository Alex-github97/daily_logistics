/**
 * Piezas para pantallas de registro: formulario declarativo, CRUD con avisos,
 * cifra de encabezado y título de página.
 *
 * Nacen del desmaquetado de SST: diez pantallas con el mismo patrón —una lista,
 * un «Nuevo», editar y retirar— que en la maqueta repetían cada una su propio
 * formulario a mano, y varias con un «Guardar» que no guardaba. Declarar los
 * campos una vez y dejar que el formulario haga la conversión (vacío → nulo,
 * texto → número) quita la clase de error más común de esas pantallas.
 */
import React, { useState } from 'react'
import {
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, FormControlLabel, Switch, Paper, alpha, Autocomplete, Divider, Table, TableBody, TableCell, TableHead, TableRow, LinearProgress, IconButton, Tooltip, Chip,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import Grid from '@mui/material/Grid2'
import { Add, Edit, DeleteForever } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { CatalogoAuto } from '@/components/catalogo/CatalogoAuto'
import { Paginacion, usePaginacion } from '@/components/comun/HerramientasTabla'

export type TipoCampo = 'texto' | 'area' | 'numero' | 'fecha' | 'seleccion' | 'interruptor'
  /** Valor del catálogo maestro (se guarda el nombre). */
  | 'catalogo' | 'multicatalogo'
  /** Usuario(s) de la plataforma (se guarda el id). Opciones en `personas`. */
  | 'persona' | 'personas'
  /** Otro registro, con búsqueda (se guarda el id). Opciones en `opciones`. */
  | 'referencia' | 'referencias'
  /** Solo un título que agrupa los campos que siguen. */
  | 'seccion'

export interface Persona { id: number; nombre: string; cargo?: string | null }

export interface Campo {
  clave: string
  etiqueta: string
  tipo?: TipoCampo
  opciones?: [string | number, string][]
  catalogo?: { modulo: string; tipo: string; agregar?: boolean }
  personas?: Persona[]
  obligatorio?: boolean
  ancho?: 12 | 8 | 6 | 4 | 3
  ayuda?: string
  min?: number
  max?: number
  /** Si devuelve texto, el campo muestra ese error y no deja guardar. */
  validar?: (v: any, todos: Record<string, any>) => string | null
}

export const errorApi = (e: any, porDefecto = 'No se pudo guardar') => {
  const d = e?.response?.data?.detail
  return typeof d === 'string' ? d : Array.isArray(d) ? 'Revisa los datos del formulario' : porDefecto
}

/** Del registro al formulario: todo como texto para los TextField. */
const LISTAS: TipoCampo[] = ['personas', 'multicatalogo', 'referencias']
const IDS: TipoCampo[] = ['persona', 'referencia']

const aFormulario = (campos: Campo[], r?: Record<string, any> | null) =>
  Object.fromEntries(campos.filter(c => c.tipo !== 'seccion').map(c => {
    const v = r?.[c.clave]
    if (c.tipo === 'interruptor') return [c.clave, !!v]
    if (LISTAS.includes(c.tipo!)) return [c.clave, Array.isArray(v) ? v : []]
    if (IDS.includes(c.tipo!)) return [c.clave, v ?? null]
    if (c.tipo === 'catalogo') return [c.clave, v ?? null]
    if (v == null) return [c.clave, '']
    if (c.tipo === 'fecha') return [c.clave, String(v).slice(0, 10)]
    return [c.clave, String(v)]
  }))

/** Del formulario a la API: vacío → nulo, números como números. */
const aCuerpo = (campos: Campo[], f: Record<string, any>) =>
  Object.fromEntries(campos.filter(c => c.tipo !== 'seccion').map(c => {
    const v = f[c.clave]
    if (c.tipo === 'interruptor') return [c.clave, !!v]
    if (LISTAS.includes(c.tipo!)) return [c.clave, v ?? []]
    if (IDS.includes(c.tipo!)) return [c.clave, v == null || v === '' ? null : Number(v)]
    if (c.tipo === 'catalogo') return [c.clave, v || null]
    if (typeof v === 'string' && v.trim() === '') return [c.clave, null]
    if (c.tipo === 'numero') return [c.clave, Number(v)]
    if (c.tipo === 'seleccion' && c.opciones?.length && typeof c.opciones[0][0] === 'number') return [c.clave, Number(v)]
    return [c.clave, typeof v === 'string' ? v.trim() : v]
  }))

export function FormularioRegistro({ abierto, titulo, campos, registro, valoresIniciales, onGuardar, onCerrar, pie, ancho = 'sm' }: {
  abierto: boolean; titulo: string; campos: Campo[]
  /** Ancho del diálogo; los formularios con secciones van mejor en `md`. */
  ancho?: 'sm' | 'md' | 'lg'
  registro?: Record<string, any> | null
  valoresIniciales?: Record<string, any>
  onGuardar: (cuerpo: Record<string, any>) => Promise<unknown>
  onCerrar: () => void
  /** Algo que mostrar debajo de los campos, calculado de lo que se escribe. */
  pie?: (valores: Record<string, any>) => React.ReactNode
}) {
  const [f, setF] = useState<Record<string, any>>({})
  const [guardando, setGuardando] = useState(false)
  const [abiertoAntes, setAbiertoAntes] = useState(false)
  if (abierto && !abiertoAntes) {
    setAbiertoAntes(true)
    setF({ ...aFormulario(campos, registro), ...(registro ? {} : valoresIniciales ?? {}) })
  }
  if (!abierto && abiertoAntes) setAbiertoAntes(false)

  const error = (c: Campo): string | null => {
    if (c.tipo === 'seccion') return null
    const v = f[c.clave]
    const vacio = v === '' || v == null || (Array.isArray(v) && v.length === 0)
    if (c.obligatorio && vacio && c.tipo !== 'interruptor') return 'Obligatorio'
    if (c.tipo === 'numero' && !vacio) {
      const n = Number(v)
      if (!Number.isFinite(n)) return 'Debe ser un número'
      if (c.min != null && n < c.min) return `Mínimo ${c.min}`
      if (c.max != null && n > c.max) return `Máximo ${c.max}`
    }
    return c.validar ? c.validar(v, f) : null
  }
  const hayError = campos.some(c => error(c))

  const guardar = async () => {
    setGuardando(true)
    try { await onGuardar(aCuerpo(campos, f)); onCerrar() }
    catch (e) { toast.error(errorApi(e)) }
    finally { setGuardando(false) }
  }

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth={ancho} fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>{titulo}</DialogTitle>
      <DialogContent>
        <Grid container spacing={2} sx={{ pt: 1 }}>
          {campos.map(c => {
            const err = error(c)
            // Solo se muestra el «Obligatorio» cuando el campo ya se tocó o
            // tiene algo: un formulario nuevo no debe abrir todo en rojo.
            const mostrar = err && !(err === 'Obligatorio' && f[`_${c.clave}`] !== true)
            const comun = {
              label: c.etiqueta, fullWidth: true, size: 'small' as const, required: c.obligatorio,
              value: f[c.clave] ?? '', error: !!mostrar, helperText: mostrar ? err : c.ayuda,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [c.clave]: e.target.value, [`_${c.clave}`]: true }),
            }
            const poner = (v: any) => setF({ ...f, [c.clave]: v, [`_${c.clave}`]: true })
            if (c.tipo === 'seccion') return (
              <Grid key={c.clave} size={12}>
                <Divider textAlign="left" sx={{ mt: 1, '&::before': { width: 0 } }}>
                  <Typography sx={{ fontSize: 11.5, fontWeight: 800, letterSpacing: 0.6, color: 'text.secondary', textTransform: 'uppercase' }}>{c.etiqueta}</Typography>
                </Divider>
              </Grid>
            )
            return (
              <Grid key={c.clave} size={{ xs: 12, sm: c.ancho ?? 12 }}>
                {c.tipo === 'catalogo' || c.tipo === 'multicatalogo' ? (
                  <CatalogoAuto modulo={c.catalogo!.modulo} tipo={c.catalogo!.tipo} label={c.etiqueta}
                    valor={f[c.clave] ?? (c.tipo === 'multicatalogo' ? [] : null)} onChange={poner}
                    multiple={c.tipo === 'multicatalogo'} agregar={c.catalogo!.agregar ?? true}
                    requerido={c.obligatorio} error={!!mostrar} ayuda={mostrar ? err! : c.ayuda} />
                ) : c.tipo === 'persona' || c.tipo === 'personas' ? (
                  <SelectorPersona multiple={c.tipo === 'personas'} etiqueta={c.etiqueta} personas={c.personas ?? []}
                    valor={f[c.clave]} onChange={poner} requerido={c.obligatorio}
                    error={!!mostrar} ayuda={mostrar ? err! : c.ayuda} />
                ) : c.tipo === 'referencias' ? (
                  <Autocomplete multiple size="small" fullWidth options={c.opciones ?? []}
                    value={(c.opciones ?? []).filter(([v]) => ((f[c.clave] ?? []) as any[]).map(String).includes(String(v)))}
                    getOptionLabel={o => o[1]} isOptionEqualToValue={(a, b) => a[0] === b[0]}
                    onChange={(_, os) => poner(os.map(o => o[0]))}
                    renderInput={p => <TextField {...p} label={c.etiqueta} helperText={mostrar ? err : c.ayuda} error={!!mostrar} />} />
                ) : c.tipo === 'referencia' ? (
                  <Autocomplete size="small" fullWidth options={c.opciones ?? []}
                    value={(c.opciones ?? []).find(([v]) => String(v) === String(f[c.clave])) ?? null}
                    getOptionLabel={o => o[1]} isOptionEqualToValue={(a, b) => a[0] === b[0]}
                    onChange={(_, o) => poner(o ? o[0] : null)}
                    renderInput={p => <TextField {...p} label={c.etiqueta} required={c.obligatorio} error={!!mostrar}
                      helperText={mostrar ? err : c.ayuda} />} />
                ) : c.tipo === 'interruptor' ? (
                  <FormControlLabel label={c.etiqueta}
                    control={<Switch checked={!!f[c.clave]} onChange={e => setF({ ...f, [c.clave]: e.target.checked })} />} />
                ) : c.tipo === 'seleccion' ? (
                  <TextField select {...comun}>
                    {!c.obligatorio && <MenuItem value=""><em>—</em></MenuItem>}
                    {c.opciones?.map(([v, l]) => <MenuItem key={String(v)} value={String(v)}>{l}</MenuItem>)}
                  </TextField>
                ) : (
                  <TextField {...comun}
                    type={c.tipo === 'numero' ? 'number' : c.tipo === 'fecha' ? 'date' : 'text'}
                    multiline={c.tipo === 'area'} minRows={c.tipo === 'area' ? 2 : undefined}
                    InputLabelProps={c.tipo === 'fecha' ? { shrink: true } : undefined}
                    inputProps={c.tipo === 'numero' ? { min: c.min, max: c.max } : undefined} />
                )}
              </Grid>
            )
          })}
        </Grid>
        {pie && <Box mt={2}>{pie(f)}</Box>}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} color="inherit">Cancelar</Button>
        <Button variant="contained" disabled={hayError || guardando} onClick={guardar}>Guardar</Button>
      </DialogActions>
    </Dialog>
  )
}

/** Lista y mutaciones de un recurso con la forma listar/crear/editar/retirar. */
export function useCrud<T extends { id: number }>(clave: unknown[], api: {
  listar: (p?: any) => Promise<T[]>
  crear: (d: any) => Promise<T>
  editar: (id: number, d: any) => Promise<T>
  retirar: (id: number) => Promise<unknown>
}, nombre: string, invalidarTambien: unknown[][] = [], femenino = false) {
  const o = femenino ? 'a' : 'o'
  const qc = useQueryClient()
  const lista = useQuery({ queryKey: clave, queryFn: () => api.listar() })
  const refrescar = () => { qc.invalidateQueries({ queryKey: clave }); invalidarTambien.forEach(k => qc.invalidateQueries({ queryKey: k })) }
  const guardar = async (registro: T | null, cuerpo: any) => {
    const r = registro ? await api.editar(registro.id, cuerpo) : await api.crear(cuerpo)
    toast.success(registro ? `${nombre} actualizad${o}` : `${nombre} registrad${o}`)
    refrescar()
    return r
  }
  const retirar = useMutation({
    mutationFn: (id: number) => api.retirar(id),
    onSuccess: () => { toast.success(`${nombre} retirad${o}`); refrescar() },
    onError: (e: any) => toast.error(errorApi(e, 'No se pudo retirar')),
  })
  return { ...lista, datos: lista.data ?? [], guardar, retirar, refrescar }
}

export function Cifra({ etiqueta, valor, color, sub }: { etiqueta: string; valor: React.ReactNode; color: string; sub?: string }) {
  return (
    <Paper elevation={0} sx={{ p: 2, borderRadius: 2, border: `1px solid ${alpha(color, 0.25)}`, height: '100%' }}>
      <Typography sx={{ fontSize: 24, fontWeight: 800, color, lineHeight: 1.1 }}>{valor}</Typography>
      <Typography sx={{ fontSize: 12, color: 'text.secondary', mt: 0.5 }}>{etiqueta}</Typography>
      {sub && <Typography sx={{ fontSize: 11, color: 'text.disabled' }}>{sub}</Typography>}
    </Paper>
  )
}

export function Encabezado({ icono, titulo, subtitulo, color, accion, onAccion }: {
  icono: React.ReactNode; titulo: string; subtitulo: string; color: string
  accion?: string; onAccion?: () => void
}) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3, gap: 2, flexWrap: 'wrap' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box sx={{ color, display: 'flex' }}>{icono}</Box>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, lineHeight: 1 }}>{titulo}</Typography>
          <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{subtitulo}</Typography>
        </Box>
      </Box>
      {accion && <Button variant="contained" startIcon={<Add />} onClick={onAccion} sx={{ bgcolor: color, '&:hover': { bgcolor: color, filter: 'brightness(0.9)' } }}>{accion}</Button>}
    </Box>
  )
}

export interface Columna<T> {
  titulo: string
  valor: (r: T) => React.ReactNode
  alinear?: 'left' | 'right' | 'center'
}

/** Tabla de registros con editar y retirar. `extra` agrega botones por fila. */
export function TablaRegistros<T extends { id: number }>({ columnas, filas, cargando, vacio, etiqueta, onEditar, onRetirar, extra, onFila, paginar }: {
  columnas: Columna<T>[]; filas: T[]; cargando?: boolean; vacio: string
  /** Filas por página (p. ej. 100). Sin esto, la tabla muestra todo como antes. */
  paginar?: number
  /** Nombre corto del registro para los botones accesibles y la confirmación. */
  etiqueta: (r: T) => string
  onEditar?: (r: T) => void; onRetirar?: (r: T) => void
  extra?: (r: T) => React.ReactNode
  onFila?: (r: T) => void
}) {
  const acciones = !!(onEditar || onRetirar || extra)
  const pag = usePaginacion(filas, paginar || filas.length || 1)
  const visibles = paginar ? pag.filasPagina : filas
  return (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'auto' }}>
      {cargando && <LinearProgress />}
      <Table size="small">
        <TableHead><TableRow sx={{ '& th': { fontWeight: 700, fontSize: 12 } }}>
          {columnas.map(c => <TableCell key={c.titulo} align={c.alinear}>{c.titulo}</TableCell>)}
          {acciones && <TableCell />}
        </TableRow></TableHead>
        <TableBody>
          {!cargando && filas.length === 0 && (
            <TableRow><TableCell colSpan={columnas.length + (acciones ? 1 : 0)} align="center" sx={{ py: 3, color: 'text.secondary' }}>{vacio}</TableCell></TableRow>
          )}
          {visibles.map(r => (
            <TableRow key={r.id} hover onClick={onFila ? () => onFila(r) : undefined} sx={{ cursor: onFila ? 'pointer' : undefined, '& td': { fontSize: 12 } }}>
              {columnas.map(c => <TableCell key={c.titulo} align={c.alinear}>{c.valor(r)}</TableCell>)}
              {acciones && (
                <TableCell sx={{ whiteSpace: 'nowrap' }} onClick={e => e.stopPropagation()}>
                  {extra?.(r)}
                  {onEditar && <Tooltip title="Editar"><IconButton size="small" aria-label={`Editar ${etiqueta(r)}`} onClick={() => onEditar(r)}><Edit fontSize="small" /></IconButton></Tooltip>}
                  {onRetirar && <Tooltip title="Retirar"><IconButton size="small" aria-label={`Retirar ${etiqueta(r)}`}
                    onClick={() => { if (window.confirm(`¿Retirar «${etiqueta(r)}»?`)) onRetirar(r) }}><DeleteForever fontSize="small" sx={{ color: '#DC2626' }} /></IconButton></Tooltip>}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {paginar && filas.length > 0 && (
        <Paginacion total={filas.length} pagina={pag.pagina} porPagina={pag.porPagina} onPagina={pag.setPagina} onPorPagina={pag.setPorPagina} />
      )}
    </Paper>
  )
}

/** Etiqueta de color para un estado o nivel. */
export function Etiqueta({ texto, color }: { texto: string; color: string }) {
  return <Chip size="small" label={texto} sx={{ fontSize: 11, fontWeight: 700, bgcolor: alpha(color, 0.12), color }} />
}

/** «en_ejecucion» → «En ejecución» con el diccionario, o capitalizado. */
export const legible = (v?: string | null, dicc?: Record<string, string>) =>
  !v ? '—' : dicc?.[v] ?? (v.charAt(0).toUpperCase() + v.slice(1).toLowerCase().replace(/_/g, ' '))

export const fmtFecha =(s?: string | null) => (s ? new Date(`${s.slice(0, 10)}T12:00:00`).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' }) : '—')


/** Una o varias personas de una lista dada (usuarios con acceso al módulo). */
export function SelectorPersona({ etiqueta, personas, valor, onChange, multiple = false, requerido, error, ayuda }: {
  etiqueta: string; personas: Persona[]; valor: any; onChange: (v: any) => void
  multiple?: boolean; requerido?: boolean; error?: boolean; ayuda?: string
}) {
  const porId = new Map(personas.map(p => [p.id, p]))
  // Alguien que ya estaba asignado y perdió el acceso se sigue mostrando.
  const op = (id: number): Persona => porId.get(id) ?? { id, nombre: `Usuario #${id} (sin acceso)` }
  return (
    <Autocomplete<Persona, boolean>
      multiple={multiple} size="small" fullWidth options={personas}
      value={multiple ? ((valor ?? []) as number[]).map(op) : (valor ? op(Number(valor)) : null) as any}
      getOptionLabel={p => p.nombre} isOptionEqualToValue={(a, b) => a.id === b.id}
      renderOption={(props, p) => (
        <li {...props} key={p.id}>
          <Box>
            <Typography sx={{ fontSize: 13 }}>{p.nombre}</Typography>
            {p.cargo && <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>{p.cargo}</Typography>}
          </Box>
        </li>
      )}
      onChange={(_, v: any) => onChange(multiple ? (v as Persona[]).map(p => p.id) : v ? (v as Persona).id : null)}
      noOptionsText="Nadie con acceso al módulo coincide"
      renderInput={p => <TextField {...p} label={etiqueta} required={requerido} error={error} helperText={ayuda} />}
    />
  )
}
