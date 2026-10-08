/**
 * El formulario de incidencias, dibujado desde la configuración.
 *
 * No hay una sola condición del tipo `if (tipo === 'ERROR')` en este archivo, y
 * es a propósito: con veinte tipos de incidencia eso serían veinte ramas
 * repartidas por tres componentes, y agregar un campo obligaría a desplegar.
 *
 * El servidor devuelve las secciones con sus campos, sus opciones ya resueltas,
 * los valores por defecto y —al editar— lo que hay guardado. Acá solo se recorre
 * eso y se dibuja el control que corresponda a cada tipo. Un campo nuevo aparece
 * solo; uno archivado desaparece solo.
 *
 * Cuando cambia el proyecto o el tipo se vuelve a pedir el esquema: los campos
 * que dependen del proyecto —sprint, épica, versión, componente— traen otras
 * opciones. Cada campo declara de qué depende, así que esa regla tampoco está
 * escrita acá.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Autocomplete, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, MenuItem, Skeleton, Stack, Switch, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import { ExpandMore, Bolt, Tune } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import {
  gestionApi, mensajeDeError,
  type CampoDeFormulario, type EsquemaFormulario, type Proyecto,
} from './api'

/** Los que se dibujan con un selector de opciones. */
const DE_SELECCION = new Set([
  'LISTA', 'LISTA_MULTIPLE', 'USUARIO', 'USUARIOS', 'PROYECTO', 'INCIDENCIA',
  'TIPO_INCIDENCIA', 'SPRINT', 'EPICA', 'VERSION', 'COMPONENTE', 'PRIORIDAD',
  'ESTADO',
])

/** Lo mínimo para dar de alta algo sin pensarlo mucho. El resto queda a un clic.
 *
 *  No es una lista de campos privilegiados: es qué secciones abre la creación
 *  rápida. Si el administrador mueve un campo a «Información principal», entra
 *  en la rápida solo. */
const RAPIDA = new Set(['PRINCIPAL'])


// ─── Un campo ─────────────────────────────────────────────────────────────────

export function Campo({
  campo, valor, onCambio, error,
}: {
  campo: CampoDeFormulario
  valor: any
  onCambio: (v: any) => void
  error?: string
}) {
  const comun = {
    size: 'small' as const,
    fullWidth: true,
    label: campo.nombre,
    required: campo.obligatorio,
    disabled: campo.solo_lectura,
    error: !!error,
    helperText: error || campo.ayuda || undefined,
  }

  // ── Selección, venga de un catálogo o de una entidad ──
  if (DE_SELECCION.has(campo.tipo)) {
    const opciones = campo.opciones ?? []

    if (campo.multiple) {
      const puestos = Array.isArray(valor) ? valor : []
      return (
        <Autocomplete
          multiple size="small" disabled={campo.solo_lectura}
          options={opciones} disableCloseOnSelect
          getOptionLabel={o => o.etiqueta}
          isOptionEqualToValue={(o, v) => o.valor === v.valor}
          value={opciones.filter(o => puestos.includes(o.valor))}
          onChange={(_, v) => onCambio(v.map(o => o.valor))}
          renderTags={(vs, getProps) => vs.map((o, i) => (
            <Chip {...getProps({ index: i })} key={o.valor} label={o.etiqueta}
              size="small" sx={{ height: 20, fontSize: 10.5 }} />
          ))}
          renderInput={p => <TextField {...p} {...comun} />}
        />
      )
    }

    // Con muchas opciones, un desplegable obliga a recorrer una lista a ciegas.
    if (opciones.length > 8) {
      return (
        <Autocomplete
          size="small" disabled={campo.solo_lectura} options={opciones}
          getOptionLabel={o => o.etiqueta}
          isOptionEqualToValue={(o, v) => o.valor === v.valor}
          value={opciones.find(o => o.valor === String(valor ?? '')) ?? null}
          onChange={(_, v) => onCambio(v?.valor ?? null)}
          renderOption={(props, o) => (
            <li {...props} key={o.valor}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" noWrap>{o.etiqueta}</Typography>
                {o.pista && (
                  <Typography variant="caption" sx={{ color: PALETA.acero }}>
                    {o.pista}
                  </Typography>
                )}
              </Box>
            </li>
          )}
          renderInput={p => <TextField {...p} {...comun} />}
        />
      )
    }

    return (
      <TextField {...comun} select value={valor ?? ''}
        onChange={e => onCambio(e.target.value || null)}>
        {/* Vacío borra el valor. Es distinto de no tocar el campo, y hay que
            poder hacer las dos cosas. */}
        <MenuItem value=""><em>Sin definir</em></MenuItem>
        {opciones.map(o => (
          <MenuItem key={o.valor} value={o.valor}>
            <Stack direction="row" alignItems="center" spacing={1}>
              {o.color && (
                <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: o.color }} />
              )}
              <span>{o.etiqueta}</span>
              {o.pista && (
                <Typography variant="caption" sx={{ color: PALETA.acero }}>
                  {o.pista}
                </Typography>
              )}
            </Stack>
          </MenuItem>
        ))}
        {!opciones.length && (
          <MenuItem disabled value="">
            <em>No hay opciones todavía</em>
          </MenuItem>
        )}
      </TextField>
    )
  }

  switch (campo.tipo) {
    case 'BOOLEANO':
      return (
        <FormControlLabel
          control={
            <Switch size="small" disabled={campo.solo_lectura}
              checked={valor === true || valor === 'true'}
              onChange={e => onCambio(e.target.checked)} />
          }
          label={
            <Box>
              <Typography variant="body2">{campo.nombre}</Typography>
              {(error || campo.ayuda) && (
                <Typography variant="caption"
                  sx={{ color: error ? ESTADO.peligro : PALETA.acero }}>
                  {error || campo.ayuda}
                </Typography>
              )}
            </Box>
          }
        />
      )

    case 'ETIQUETAS':
      return (
        <Autocomplete
          multiple freeSolo size="small" disabled={campo.solo_lectura}
          options={(campo.opciones ?? []).map(o => o.valor)}
          value={Array.isArray(valor) ? valor : []}
          onChange={(_, v) => onCambio(v.map(x => String(x).trim()).filter(Boolean))}
          renderTags={(vs, getProps) => vs.map((v, i) => (
            <Chip {...getProps({ index: i })} key={v} label={v} size="small"
              sx={{ height: 20, fontSize: 10.5 }} />
          ))}
          renderInput={p => <TextField {...p} {...comun}
            helperText={error || campo.ayuda || 'Escriba y pulse Enter'} />}
        />
      )

    case 'TEXTO_LARGO':
    case 'TEXTO_RICO':
      return (
        <TextField {...comun} multiline minRows={campo.tipo === 'TEXTO_RICO' ? 5 : 3}
          value={valor ?? ''} onChange={e => onCambio(e.target.value)} />
      )

    case 'NUMERO':
    case 'DECIMAL':
      return (
        <TextField
          {...comun} type="number"
          inputProps={{
            min: campo.validacion?.min, max: campo.validacion?.max,
            step: campo.tipo === 'DECIMAL' ? 'any' : 1,
          }}
          value={valor ?? ''} onChange={e => onCambio(e.target.value)}
        />
      )

    case 'FECHA':
    case 'FECHA_HORA':
      return (
        <TextField
          {...comun} type={campo.tipo === 'FECHA' ? 'date' : 'datetime-local'}
          InputLabelProps={{ shrink: true }}
          value={String(valor ?? '').slice(0, campo.tipo === 'FECHA' ? 10 : 16)}
          onChange={e => onCambio(e.target.value || null)}
        />
      )

    case 'CORREO':
      return (
        <TextField {...comun} type="email" value={valor ?? ''}
          onChange={e => onCambio(e.target.value)} />
      )

    case 'URL':
      return (
        <TextField {...comun} value={valor ?? ''}
          placeholder="https://…"
          onChange={e => onCambio(e.target.value)} />
      )

    default:
      return (
        <TextField {...comun} value={valor ?? ''}
          onChange={e => onCambio(e.target.value)} />
      )
  }
}


// ─── El formulario ────────────────────────────────────────────────────────────

export default function GestionFormulario({
  abierto, proyecto, proyectos, incidenciaId, preseleccion, onCerrar, onGuardada,
}: {
  abierto: boolean
  proyecto: Proyecto | null
  proyectos: Proyecto[]
  /** Vacío = crear. Con id = editar. La misma pantalla sirve para las dos. */
  incidenciaId?: number | null
  /** Lo que llega ya decidido: el proyecto, el tipo y los campos que quien
   *  abre el formulario conoce. Lo usa la creación de subtareas, que sabe de
   *  qué cuelga y de qué nivel tiene que ser.
   *
   *  `niveles` acota qué tipos se ofrecen. No es una comodidad: la jerarquía
   *  la hace cumplir el servidor, y ofrecer un tipo que va a rechazar es
   *  hacer que la persona descubra la regla estrellándose contra ella. */
  preseleccion?: {
    proyecto_id: number
    tipo_id?: number | null
    niveles?: string[]
    campos?: Record<string, any>
    titulo?: string
  } | null
  onCerrar: () => void
  onGuardada: (id: number) => void
}) {
  const qc = useQueryClient()
  const editando = incidenciaId != null

  const [proyectoId, setProyectoId] = useState<number | null>(proyecto?.id ?? null)
  const [tipoId, setTipoId] = useState<number | null>(null)
  const [valores, setValores] = useState<Record<string, any>>({})
  const [problemas, setProblemas] = useState<string[]>([])
  const [completo, setCompleto] = useState(false)

  const { data: config } = useQuery({
    queryKey: ['gestion', 'config', proyectoId],
    queryFn: () => gestionApi.configuracion(proyectoId ?? undefined),
    enabled: abierto && proyectoId != null,
    staleTime: 5 * 60_000,
  })

  const { data: esquema, isLoading } = useQuery({
    queryKey: ['gestion', 'formulario', proyectoId, tipoId, incidenciaId],
    queryFn: () => gestionApi.formulario({
      proyecto_id: proyectoId ?? undefined,
      tipo_id: tipoId ?? undefined,
      incidencia_id: incidenciaId ?? undefined,
    }),
    enabled: abierto && (proyectoId != null || editando),
  })

  // Al abrir se parte de cero. Al editar, del proyecto y el tipo de la
  // incidencia, que llegan con el esquema.
  useEffect(() => {
    if (!abierto) return
    setProblemas([])
    setCompleto(editando)
    if (!editando) {
      setProyectoId(preseleccion?.proyecto_id ?? proyecto?.id ?? null)
      setTipoId(preseleccion?.tipo_id ?? null)
      setValores({})
    }
  }, [abierto, editando, proyecto?.id, preseleccion])

  useEffect(() => {
    if (!esquema) return
    if (esquema.proyecto_id && esquema.proyecto_id !== proyectoId) {
      setProyectoId(esquema.proyecto_id)
    }
    if (esquema.tipo_id && esquema.tipo_id !== tipoId) setTipoId(esquema.tipo_id)

    // Los valores arrancan de lo guardado —al editar— o del defecto que resuelve
    // el servidor. Se hace acá y no en cada control para que un campo que
    // aparece al cambiar de tipo llegue con su defecto puesto.
    const inicial: Record<string, any> = {}
    esquema.secciones.forEach(s => s.campos.forEach(c => {
      inicial[c.clave] = preseleccion?.campos?.[c.clave]
        ?? c.valor ?? c.defecto ?? null
    }))
    setValores(inicial)
  }, [esquema])

  // Cuando cambia el proyecto, lo que dependía de él puede haber quedado
  // apuntando a algo de otro proyecto. Se limpia en vez de dejarlo: el servidor
  // lo rechazaría, y descubrirlo al guardar es peor que verlo vaciarse.
  useEffect(() => {
    if (!esquema) return
    const dependientes = esquema.secciones
      .flatMap(s => s.campos)
      .filter(c => c.depende_de === 'proyecto')
    if (!dependientes.length) return

    setValores(previos => {
      let cambio = false
      const siguiente = { ...previos }
      dependientes.forEach(c => {
        const v = previos[c.clave]
        if (v == null || v === '' || (Array.isArray(v) && !v.length)) return
        const validas = new Set((c.opciones ?? []).map(o => o.valor))
        if (Array.isArray(v)) {
          const quedan = v.filter(x => validas.has(String(x)))
          if (quedan.length !== v.length) { siguiente[c.clave] = quedan; cambio = true }
        } else if (!validas.has(String(v))) {
          siguiente[c.clave] = null; cambio = true
        }
      })
      return cambio ? siguiente : previos
    })
  }, [esquema])

  // Los tipos que se pueden escoger. Cuando quien abre el formulario acota los
  // niveles —crear una subtarea de una épica— se ofrecen solo esos: la jerarquía
  // la hace cumplir el servidor, y ofrecer un tipo que va a rechazar es hacer
  // que la persona descubra la regla estrellándose contra ella.
  const tipos = useMemo(() => {
    const todos = config?.tipos ?? []
    const niveles = preseleccion?.niveles
    return niveles?.length ? todos.filter(t => niveles.includes(t.nivel)) : todos
  }, [config, preseleccion])

  // Con un solo tipo posible no hay nada que escoger.
  useEffect(() => {
    if (abierto && !editando && !tipoId && tipos.length === 1) setTipoId(tipos[0].id)
  }, [abierto, editando, tipoId, tipos])

  const guardar = useMutation({
    mutationFn: () => {
      // Solo lo que tiene valor y no es de solo lectura. Mandar los vacíos
      // borraría lo que otro acabe de poner mientras este formulario estaba
      // abierto.
      const editables = new Set(
        (esquema?.secciones ?? []).flatMap(s => s.campos)
          .filter(c => !c.solo_lectura).map(c => c.clave))
      const campos: Record<string, any> = {}
      Object.entries(valores).forEach(([k, v]) => {
        if (editables.has(k)) campos[k] = v
      })
      return editando
        ? gestionApi.editar(incidenciaId!, { campos })
        : gestionApi.crear({ proyecto_id: proyectoId, tipo_id: tipoId, campos })
    },
    onSuccess: inc => {
      toast.success(editando ? `${inc.clave} actualizada` : `Creada ${inc.clave}`)
      qc.invalidateQueries({ queryKey: ['gestion'] })
      onCerrar()
      onGuardada(inc.id)
    },
    onError: (e: any) => {
      const d = e?.response?.data?.detail
      if (d?.campos) {
        setProblemas(d.campos)
        // Si lo que falta está en una sección cerrada, abrirlas todas: si no,
        // el formulario dice «revise lo marcado» y no se ve nada marcado.
        setCompleto(true)
        return
      }
      toast.error(mensajeDeError(e, 'No se pudo guardar'))
    },
  })

  const errorDe = (campo: CampoDeFormulario) =>
    problemas.find(p => p.startsWith(`«${campo.nombre}»`))
      ?.replace(`«${campo.nombre}» `, '')

  const secciones = useMemo(
    () => (esquema?.secciones ?? []).filter(s => completo || RAPIDA.has(s.clave)),
    [esquema, completo])

  const ocultas = (esquema?.secciones.length ?? 0) - secciones.length

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="md" fullWidth
      PaperProps={{ sx: { borderRadius: 2 } }}>
      <DialogTitle sx={{ fontWeight: 700, pb: 1 }}>
        {preseleccion?.titulo ?? (editando ? 'Editar incidencia' : 'Nueva incidencia')}
        <Typography variant="caption" sx={{ display: 'block', color: PALETA.acero }}>
          Los campos de esta pantalla se definen en Configuración → Campos.
        </Typography>
      </DialogTitle>

      <DialogContent dividers>
        {/* ── La coordenada: qué formulario aplica ── */}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} mb={2.5}>
          <TextField
            select size="small" label="Proyecto" fullWidth required
            value={proyectoId ?? ''} disabled={editando || !!preseleccion}
            onChange={e => { setProyectoId(Number(e.target.value)); setTipoId(null) }}
            helperText={editando
              ? 'Una incidencia no cambia de proyecto: su clave ya está citada.'
              : preseleccion
                ? 'Una subtarea vive en el proyecto de su padre.'
                : undefined}
          >
            {proyectos.map(p => (
              <MenuItem key={p.id} value={p.id}>{p.icono} {p.nombre}</MenuItem>
            ))}
          </TextField>

          <TextField
            select size="small" label="Tipo" fullWidth required
            value={tipoId ?? ''} disabled={!proyectoId}
            onChange={e => setTipoId(Number(e.target.value))}
            helperText="De él dependen los campos que se piden."
          >
            {tipos.map(t => (
              <MenuItem key={t.id} value={t.id}>
                {t.icono} {t.nombre}
              </MenuItem>
            ))}
          </TextField>
        </Stack>

        {!proyectoId || !tipoId ? (
          <Alert severity="info" icon={<Tune />}>
            Escoja el proyecto y el tipo. El formulario se arma con lo que esté
            configurado para esa combinación.
          </Alert>
        ) : isLoading ? (
          <Stack spacing={2}>
            <Skeleton height={48} /><Skeleton height={48} /><Skeleton height={110} />
          </Stack>
        ) : (
          <>
            {!!problemas.length && (
              <Alert severity="warning" sx={{ mb: 2, py: 0.5 }}>
                Revise lo marcado en rojo.
              </Alert>
            )}

            <Stack spacing={2}>
              {secciones.map((seccion, i) => (
                <Box key={seccion.clave}>
                  {i > 0 && (
                    <Divider textAlign="left" sx={{ mb: 2 }}>
                      <Typography variant="caption" sx={{
                        fontWeight: 800, fontSize: 9.5, letterSpacing: '0.08em',
                        color: PALETA.acero,
                      }}>
                        {seccion.titulo.toUpperCase()}
                      </Typography>
                    </Divider>
                  )}
                  <Box sx={{
                    display: 'grid', gap: 2,
                    gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
                  }}>
                    {seccion.campos.map(campo => (
                      <Box key={campo.clave} sx={{
                        // Los textos largos ocupan el ancho completo: partidos en
                        // dos columnas quedan demasiado estrechos para escribir.
                        gridColumn: ['TEXTO_LARGO', 'TEXTO_RICO', 'ETIQUETAS']
                          .includes(campo.tipo) ? { sm: 'span 2' } : undefined,
                      }}>
                        <Campo
                          campo={campo} valor={valores[campo.clave]}
                          error={errorDe(campo)}
                          onCambio={v => setValores({ ...valores, [campo.clave]: v })}
                        />
                      </Box>
                    ))}
                  </Box>
                </Box>
              ))}
            </Stack>

            {ocultas > 0 && (
              <Button
                size="small" startIcon={<ExpandMore />} sx={{ mt: 2, textTransform: 'none' }}
                onClick={() => setCompleto(true)}
              >
                Formulario completo ({ocultas} secciones más)
              </Button>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        {completo && (esquema?.secciones.length ?? 0) > 1 && !editando && (
          <Button size="small" onClick={() => setCompleto(false)}
            sx={{ textTransform: 'none', color: PALETA.acero }}>
            Creación rápida
          </Button>
        )}
        <Box sx={{ flex: 1 }} />
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={!proyectoId || !tipoId || guardar.isPending}
          onClick={() => guardar.mutate()} sx={{ textTransform: 'none' }}
        >
          {editando ? 'Guardar' : 'Crear'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
