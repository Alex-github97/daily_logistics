/**
 * La barra de filtros: escribir la expresión, o armarla a clics.
 *
 * Las dos son la MISMA cosa vista de dos formas, no dos caminos: el constructor
 * visual genera el texto y el texto es lo que se manda. Un segundo camino que no
 * pasara por la validación del servidor sería justo por donde entraría lo que la
 * primera rechaza.
 *
 * Los campos y los operadores los sirve el servidor. Tenerlos escritos acá haría
 * que la pantalla ofreciera cosas que el servidor no acepta, y quien las usara
 * concluiría que el filtro está roto.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Box, Stack, Button, IconButton, Popover, MenuItem, Chip, Typography, Divider, Tooltip, CircularProgress, Autocomplete,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  FilterAlt, Add, Close, BookmarkBorder, Bookmark, PlayArrow, HelpOutline,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { DialogoTexto } from './GestionDialogos'
import {
  gestionApi, mensajeDeError,
  type CampoConsultable, type FiltroGuardado,
} from './api'

/** Los operadores que no llevan valor. */
const SIN_VALOR = new Set(['ES VACIO', 'NO ES VACIO'])
/** Los que llevan una lista. */
const CON_LISTA = new Set(['EN', 'NO EN'])

function entrecomillar(valor: string): string {
  const limpio = valor.trim()
  if (!limpio) return '""'
  // Un número entra tal cual; lo demás va entre comillas para que un espacio o
  // un acento no rompan el análisis.
  if (/^-?\d+(\.\d+)?$/.test(limpio)) return limpio
  return `"${limpio.replace(/"/g, '\\"')}"`
}

// ─── Constructor visual ───────────────────────────────────────────────────────

function Constructor({
  campos, onAgregar, onCerrar,
}: {
  campos: CampoConsultable[]
  onAgregar: (fragmento: string) => void
  onCerrar: () => void
}) {
  const [campo, setCampo] = useState<CampoConsultable | null>(null)
  const [operador, setOperador] = useState('')
  const [valor, setValor] = useState('')

  const operadores = campo?.operadores ?? []

  function agregar() {
    if (!campo || !operador) return
    if (SIN_VALOR.has(operador)) {
      onAgregar(`${campo.clave} ${operador}`)
    } else if (CON_LISTA.has(operador)) {
      const partes = valor.split(',').map(v => v.trim()).filter(Boolean)
      if (!partes.length) return
      onAgregar(`${campo.clave} ${operador} (${partes.map(entrecomillar).join(', ')})`)
    } else {
      if (!valor.trim()) return
      onAgregar(`${campo.clave} ${operador} ${entrecomillar(valor)}`)
    }
    setValor('')
    onCerrar()
  }

  return (
    <Box sx={{ p: 2, width: 340 }}>
      <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 700 }}>
        Agregar una condición
      </Typography>

      <Stack spacing={1.5}>
        <Autocomplete
          size="small" options={campos} value={campo}
          getOptionLabel={c => c.etiqueta}
          groupBy={c => (c.personalizado ? 'Configurables' : 'Del sistema')}
          onChange={(_, v) => {
            setCampo(v)
            setOperador(v?.operadores[0] ?? '')
            setValor('')
          }}
          renderInput={p => <TextField {...p} label="Campo" autoFocus />}
        />

        <TextField
          select size="small" label="Condición" value={operador}
          disabled={!campo}
          onChange={e => setOperador(e.target.value)}
        >
          {operadores.map(o => (
            <MenuItem key={o} value={o}>{o}</MenuItem>
          ))}
        </TextField>

        {!SIN_VALOR.has(operador) && (
          <TextField
            size="small" label={CON_LISTA.has(operador) ? 'Valores' : 'Valor'}
            helperText={CON_LISTA.has(operador) ? 'Separados por comas' : undefined}
            value={valor} disabled={!campo}
            onChange={e => setValor(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') agregar() }}
          />
        )}

        <Button
          size="small" variant="contained" startIcon={<Add />}
          disabled={!campo || !operador}
          onClick={agregar}
        >
          Agregar al filtro
        </Button>
      </Stack>
    </Box>
  )
}

// ─── Ayuda ────────────────────────────────────────────────────────────────────

function Ayuda({ funciones }: { funciones: { nombre: string; descripcion: string }[] }) {
  return (
    <Box sx={{ p: 2, maxWidth: 420 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
        Cómo se escribe un filtro
      </Typography>
      <Typography variant="body2" sx={{ mb: 1.5, color: PALETA.grafito }}>
        Condiciones unidas por <b>Y</b> y <b>O</b>, con paréntesis si hace falta
        agrupar. <b>NO</b> niega un bloque entero.
      </Typography>
      <Box sx={{
        fontFamily: 'monospace', fontSize: 12, bgcolor: PALETA.bruma, p: 1.25,
        borderRadius: 1, mb: 1.5, whiteSpace: 'pre-wrap', lineHeight: 1.8,
      }}>
        {'proyecto = "ERP" Y asignado = yo()\n'}
        {'prioridad EN ("ALTA", "CRITICA")\n'}
        {'estado NO EN ("Hecho") Y vence < hoy()\n'}
        {'texto CONTIENE "llantas" ORDENAR POR vence ASC'}
      </Box>
      <Typography variant="caption" sx={{ fontWeight: 700, color: PALETA.acero }}>
        FUNCIONES
      </Typography>
      <Stack spacing={0.25} mt={0.5}>
        {funciones.map(f => (
          <Typography key={f.nombre} variant="caption" sx={{ color: PALETA.grafito }}>
            <code style={{ fontWeight: 700 }}>{f.nombre}</code> — {f.descripcion}
          </Typography>
        ))}
      </Stack>
    </Box>
  )
}

// ─── La barra ─────────────────────────────────────────────────────────────────

export function BarraDeFiltro({
  expresion, onCambio, onBuscar,
}: {
  expresion: string
  onCambio: (e: string) => void
  onBuscar: () => void
}) {
  const qc = useQueryClient()
  const [constructor, setConstructor] = useState<null | HTMLElement>(null)
  const [ayuda, setAyuda] = useState<null | HTMLElement>(null)
  const [guardados, setGuardados] = useState<null | HTMLElement>(null)
  const [revision, setRevision] = useState<{ valido: boolean; mensaje?: string | null } | null>(null)
  const [revisando, setRevisando] = useState(false)
  const [guardandoNombre, setGuardandoNombre] = useState(false)

  const { data: catalogo } = useQuery({
    queryKey: ['gestion', 'campos-consulta'],
    queryFn: gestionApi.camposConsultables,
    staleTime: 5 * 60_000,
  })
  const { data: filtros } = useQuery({
    queryKey: ['gestion', 'filtros'],
    queryFn: gestionApi.filtros,
  })

  // Se valida mientras se escribe, con una pausa para no llamar en cada tecla.
  // Sin esto, el error solo aparece al buscar y se lee como una lista vacía sin
  // motivo, que es la peor forma de decir «hay una errata en la línea 1».
  useEffect(() => {
    if (!expresion.trim()) { setRevision(null); return }
    setRevisando(true)
    const t = setTimeout(async () => {
      try {
        setRevision(await gestionApi.validar(expresion))
      } catch {
        setRevision(null)
      } finally {
        setRevisando(false)
      }
    }, 400)
    return () => { clearTimeout(t); setRevisando(false) }
  }, [expresion])

  const guardar = useMutation({
    mutationFn: (nombre: string) =>
      gestionApi.guardarFiltro({ nombre, expresion, compartido: true }),
    onSuccess: () => {
      toast.success('Filtro guardado')
      qc.invalidateQueries({ queryKey: ['gestion', 'filtros'] })
    },
    onError: (e: any) => toast.error(mensajeDeError(e, 'No se pudo guardar el filtro')),
  })

  const borrar = useMutation({
    mutationFn: gestionApi.borrarFiltro,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gestion', 'filtros'] }),
  })

  const roto = revision && !revision.valido

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <TextField
          size="small" fullWidth placeholder='proyecto = "SOP" Y asignado = yo()'
          value={expresion}
          onChange={e => onCambio(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !roto) onBuscar() }}
          error={!!roto}
          helperText={roto ? revision?.mensaje : ' '}
          InputProps={{
            sx: { fontFamily: 'monospace', fontSize: 13 },
            endAdornment: revisando
              ? <CircularProgress size={14} />
              : revision?.valido
                ? <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: ESTADO.exito }} />
                : null,
          }}
        />

        <Tooltip title="Agregar una condición a clics">
          <IconButton size="small" onClick={e => setConstructor(e.currentTarget)}
            sx={{ mt: 0.5 }}>
            <FilterAlt fontSize="small" />
          </IconButton>
        </Tooltip>

        <Tooltip title="Filtros guardados">
          <IconButton size="small" onClick={e => setGuardados(e.currentTarget)}
            sx={{ mt: 0.5 }}>
            <Bookmark fontSize="small" />
          </IconButton>
        </Tooltip>

        <Tooltip title="Cómo se escribe">
          <IconButton size="small" onClick={e => setAyuda(e.currentTarget)}
            sx={{ mt: 0.5 }}>
            <HelpOutline fontSize="small" />
          </IconButton>
        </Tooltip>

        <Button
          size="small" variant="contained" startIcon={<PlayArrow />}
          disabled={!!roto} onClick={onBuscar} sx={{ mt: 0.5, whiteSpace: 'nowrap' }}
        >
          Buscar
        </Button>
      </Stack>

      <Popover
        open={!!constructor} anchorEl={constructor} onClose={() => setConstructor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Constructor
          campos={catalogo?.campos ?? []}
          onCerrar={() => setConstructor(null)}
          onAgregar={fragmento => {
            const base = expresion.trim()
            onCambio(base ? `${base} Y ${fragmento}` : fragmento)
          }}
        />
      </Popover>

      <Popover open={!!ayuda} anchorEl={ayuda} onClose={() => setAyuda(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}>
        <Ayuda funciones={catalogo?.funciones ?? []} />
      </Popover>

      <Popover open={!!guardados} anchorEl={guardados} onClose={() => setGuardados(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <Box sx={{ p: 1.5, width: 340 }}>
          <Button
            size="small" fullWidth startIcon={<BookmarkBorder />}
            disabled={!expresion.trim() || !!roto || guardar.isPending}
            onClick={() => { setGuardados(null); setGuardandoNombre(true) }}
          >
            Guardar el filtro actual
          </Button>
          <Divider sx={{ my: 1 }} />
          {!filtros?.length && (
            <Typography variant="caption" sx={{ color: PALETA.acero, px: 1 }}>
              Todavía no hay filtros guardados.
            </Typography>
          )}
          {filtros?.map(f => (
            <FilaGuardado
              key={f.id} filtro={f}
              onUsar={() => { onCambio(f.expresion); setGuardados(null); onBuscar() }}
              onBorrar={() => borrar.mutate(f.id)}
            />
          ))}
        </Box>
      </Popover>

      <DialogoTexto
        abierto={guardandoNombre} onCerrar={() => setGuardandoNombre(false)}
        titulo="Guardar filtro" etiqueta="Nombre"
        ayuda="Se guarda compartido: cualquiera del equipo puede usarlo."
        textoBoton="Guardar"
        onAceptar={n => guardar.mutate(n)}
      />
    </Box>
  )
}

function FilaGuardado({
  filtro, onUsar, onBorrar,
}: {
  filtro: FiltroGuardado
  onUsar: () => void
  onBorrar: () => void
}) {
  return (
    <Stack direction="row" alignItems="center" spacing={0.5}
      sx={{ px: 1, py: 0.6, borderRadius: 1, '&:hover': { bgcolor: PALETA.bruma } }}>
      <Box sx={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={onUsar}>
        <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
          {filtro.nombre}
        </Typography>
        <Typography variant="caption" sx={{
          fontFamily: 'monospace', fontSize: 10.5, color: PALETA.acero,
          display: 'block', overflow: 'hidden', textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {filtro.expresion || 'sin condiciones'}
        </Typography>
      </Box>
      {filtro.compartido && (
        <Chip label="compartido" size="small"
          sx={{ height: 16, fontSize: 9, bgcolor: `${COLOR_MODULO}14`, color: COLOR_MODULO }} />
      )}
      <IconButton size="small" onClick={onBorrar}>
        <Close sx={{ fontSize: 14 }} />
      </IconButton>
    </Stack>
  )
}
