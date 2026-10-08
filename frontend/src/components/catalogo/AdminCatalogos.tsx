/**
 * Administración de los catálogos de un módulo.
 *
 * Se arma sola desde el registro que declara el backend: agregar un catálogo
 * nuevo a un módulo es una línea en `CATALOGOS_REGISTRO` y aparece acá sin
 * tocar esta pantalla.
 *
 * Los catálogos con jerarquía se navegan por niveles (país → departamento →
 * ciudad); los planos son una lista.
 */
import { useMemo, useState } from 'react'
import {
  Box, Card, CardContent, Typography, Stack, Chip, Button, TextField, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions, alpha, Alert, Tooltip,
  InputAdornment, Switch, FormControlLabel, Divider,
} from '@mui/material'
import Grid from '@mui/material/Grid2'
import {
  Add as AddIcon, DeleteForever as DeleteIcon, Edit as EditIcon,
  ChevronRight, Search as SearchIcon, AccountTree, ArrowBack,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient as api } from '@/api/client'
import type { RegistroCatalogo, ValorCatalogo } from './SelectorCatalogo'
import { CargueMasivo, type ColumnaPlantilla } from './CargueMasivo'

export function AdminCatalogos({
  modulo, color = '#1A1A1A', titulo, incluirGlobales = true,
}: {
  /** Código del módulo (HCM, WMS, TMS…). */
  modulo: string
  color?: string
  titulo?: string
  /** Si es false, oculta los catálogos compartidos (GLOBAL). */
  incluirGlobales?: boolean
}) {
  const qc = useQueryClient()
  const [seleccionado, setSeleccionado] = useState<RegistroCatalogo | null>(null)
  // Camino recorrido en un catálogo con jerarquía, para el rastro de migas
  const [ruta, setRuta] = useState<ValorCatalogo[]>([])
  const [busqueda, setBusqueda] = useState('')

  const [dlg, setDlg] = useState<{ abierto: boolean; item: ValorCatalogo | null }>(
    { abierto: false, item: null })
  const [form, setForm] = useState({ nombre: '', codigo: '', activo: true })
  const [wasOpen, setWasOpen] = useState(false)

  if (dlg.abierto && !wasOpen) {
    setWasOpen(true)
    setForm(dlg.item
      ? { nombre: dlg.item.nombre, codigo: dlg.item.codigo ?? '', activo: dlg.item.activo !== false }
      : { nombre: '', codigo: '', activo: true })
  }
  if (!dlg.abierto && wasOpen) setWasOpen(false)

  const { data: registro = [] } = useQuery<RegistroCatalogo[]>({
    queryKey: ['catalogo-registro', modulo],
    queryFn: () => api.get('/catalogos/registro', { params: { modulo } }).then(r => r.data),
  })

  const visibles = useMemo(
    () => registro.filter(r => incluirGlobales || r.modulo !== 'GLOBAL'),
    [registro, incluirGlobales],
  )

  // Los catálogos hijos no se listan aparte: se llega a ellos bajando por el padre
  const raices = useMemo(() => {
    const tiposHijos = new Set(visibles.filter(r => r.padre).map(r => r.tipo))
    return visibles.filter(r => !r.padre || !visibles.some(x => x.tipo === r.padre) === false
      ? !r.padre
      : !tiposHijos.has(r.tipo))
  }, [visibles])

  /** Catálogo hijo directo del tipo dado, si existe. */
  const hijoDe = (tipo: string) => visibles.find(r => r.padre === tipo) ?? null

  // Nivel que se está viendo: la raíz elegida, o el hijo del último de la ruta
  const nivelActual = useMemo(() => {
    if (!seleccionado) return null
    if (ruta.length === 0) return seleccionado
    return hijoDe(ruta[ruta.length - 1].tipo)
  }, [seleccionado, ruta, visibles])

  const padreId = ruta.length > 0 ? ruta[ruta.length - 1].id : null

  const { data: valores = [] } = useQuery<ValorCatalogo[]>({
    queryKey: ['catalogo-admin', nivelActual?.modulo, nivelActual?.tipo, padreId],
    queryFn: () => api.get('/catalogos', {
      params: {
        modulo: nivelActual!.modulo, tipo: nivelActual!.tipo,
        ...(padreId != null ? { padre_id: padreId } : {}),
      },
    }).then(r => r.data),
    enabled: Boolean(nivelActual),
  })

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ['catalogo-admin'] })
    qc.invalidateQueries({ queryKey: ['catalogo-registro'] })
    qc.invalidateQueries({ queryKey: ['catalogo'] })   // los selectores de los formularios
  }
  const err = (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo guardar')

  const mutGuardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        modulo: nivelActual!.modulo, tipo: nivelActual!.tipo,
        nombre: form.nombre.trim(), codigo: form.codigo.trim() || null,
        padre_id: padreId, activo: form.activo,
      }
      return dlg.item
        ? api.put(`/catalogos/${dlg.item.id}`, {
            nombre: cuerpo.nombre, codigo: cuerpo.codigo, activo: cuerpo.activo,
          }).then(r => r.data)
        : api.post('/catalogos', cuerpo).then(r => r.data)
    },
    onSuccess: () => {
      toast.success(dlg.item ? 'Valor actualizado' : 'Valor agregado')
      invalidar()
      setDlg({ abierto: false, item: null })
    },
    onError: err,
  })

  const mutBorrar = useMutation({
    mutationFn: (id: number) => api.delete(`/catalogos/${id}`),
    onSuccess: () => {
      toast.success('Valor eliminado. Si tenía dependientes, quedó desactivado.')
      invalidar()
    },
    onError: err,
  })

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    if (!q) return valores
    return valores.filter(v =>
      v.nombre.toLowerCase().includes(q) || (v.codigo ?? '').toLowerCase().includes(q))
  }, [valores, busqueda])

  // ── Lista de catálogos del módulo ──
  if (!seleccionado) {
    return (
      <Box>
        {titulo && <Typography variant="subtitle2" fontWeight={800} mb={0.5}>{titulo}</Typography>}
        <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
          Estos son los valores que se ofrecen en los formularios del módulo. Los marcados como
          <strong> compartidos</strong> los usan todos los módulos, así que cambiarlos afecta a
          toda la plataforma.
        </Alert>
        <Grid container spacing={2}>
          {raices.map(r => (
            <Grid key={`${r.modulo}:${r.tipo}`} size={{ xs: 12, sm: 6, md: 4 }}>
              <Card
                onClick={() => { setSeleccionado(r); setRuta([]); setBusqueda('') }}
                sx={{
                  height: '100%', cursor: 'pointer', bgcolor: '#FFFFFF',
                  border: `1px solid ${alpha(color, 0.2)}`,
                  transition: 'all .15s',
                  '&:hover': { borderColor: color, transform: 'translateY(-1px)', boxShadow: 2 },
                }}
              >
                <CardContent sx={{ p: 2 }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
                    <Box sx={{ minWidth: 0 }}>
                      <Stack direction="row" alignItems="center" gap={0.6}>
                        <Typography variant="subtitle2" fontWeight={800} noWrap>{r.label}</Typography>
                        {hijoDe(r.tipo) && (
                          <Tooltip title={`Tiene niveles: ${hijoDe(r.tipo)!.label}`}>
                            <AccountTree sx={{ fontSize: 14, color }} />
                          </Tooltip>
                        )}
                      </Stack>
                      <Typography variant="caption" color="text.secondary" display="block">
                        {r.descripcion}
                      </Typography>
                      <Stack direction="row" gap={0.5} mt={0.7}>
                        <Chip size="small" label={`${r.total} valor(es)`}
                          sx={{ height: 19, fontSize: 10, bgcolor: alpha(color, 0.12), color }} />
                        {r.modulo === 'GLOBAL' && (
                          <Chip size="small" label="compartido" sx={{ height: 19, fontSize: 10 }} />
                        )}
                      </Stack>
                    </Box>
                    <ChevronRight sx={{ color: 'text.disabled', flexShrink: 0 }} />
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
          {raices.length === 0 && (
            <Grid size={12}>
              <Typography variant="body2" color="text.secondary" textAlign="center" py={3}>
                Este módulo no tiene catálogos declarados.
              </Typography>
            </Grid>
          )}
        </Grid>
      </Box>
    )
  }

  // ── Valores de un catálogo ──
  const hijo = nivelActual ? hijoDe(nivelActual.tipo) : null

  // Cuando el catálogo tiene padre, la plantilla lo pide por nombre: quien
  // llena un Excel escribe "Antioquia", no el número interno del registro.
  const padreDe = nivelActual?.padre
    ? registro.find(r => r.tipo === nivelActual.padre)
    : null
  const columnasPlantilla: ColumnaPlantilla[] = [
    { clave: 'nombre', titulo: 'Nombre', requerida: true,
      ayuda: 'El valor tal como aparecerá en los formularios', ejemplo: 'Ejemplo' },
    ...(padreDe ? [{
      clave: 'padre', titulo: padreDe.label.replace(/s$/, ''), requerida: true,
      ayuda: `Debe existir ya en ${padreDe.label}. Cárguelos primero.`,
      ejemplo: '',
    } as ColumnaPlantilla] : []),
    { clave: 'codigo', titulo: 'Código', ayuda: 'Opcional: código interno, DANE, PUC…' },
  ]

  return (
    <Box>
      <Stack direction="row" alignItems="center" gap={1} mb={1.5} flexWrap="wrap">
        <Button size="small" startIcon={<ArrowBack />}
          onClick={() => {
            if (ruta.length > 0) setRuta(ruta.slice(0, -1))
            else setSeleccionado(null)
          }}
          sx={{ textTransform: 'none' }}>
          {ruta.length > 0 ? 'Subir un nivel' : 'Todos los catálogos'}
        </Button>
        <Typography variant="body2" fontWeight={700}>
          {seleccionado.label}
        </Typography>
        {ruta.map(r => (
          <Stack key={r.id} direction="row" alignItems="center" gap={0.5}>
            <ChevronRight sx={{ fontSize: 15, color: 'text.disabled' }} />
            <Typography variant="body2" fontWeight={700}>{r.nombre}</Typography>
          </Stack>
        ))}
        {nivelActual && ruta.length > 0 && (
          <Chip size="small" label={nivelActual.label} sx={{ height: 20, fontSize: 10.5 }} />
        )}
      </Stack>

      <Stack direction="row" gap={1.5} mb={1.5} flexWrap="wrap" alignItems="center">
        <TextField
          size="small" placeholder="Buscar…" value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          sx={{ minWidth: 240, flex: 1 }}
          InputProps={{
            startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 16 }} /></InputAdornment>,
          }}
        />
        <Typography variant="caption" color="text.secondary">
          {filtrados.length} de {valores.length}
        </Typography>
        <Button variant="contained" size="small" startIcon={<AddIcon />}
          onClick={() => setDlg({ abierto: true, item: null })}
          sx={{ bgcolor: color, textTransform: 'none' }}>
          Agregar
        </Button>
      </Stack>

      {nivelActual && (
        <Box sx={{ mb: 1.5 }}>
          <CargueMasivo
            compacto
            titulo={nivelActual.label}
            nombreArchivo={`plantilla-${nivelActual.modulo.toLowerCase()}-${nivelActual.tipo.toLowerCase()}`}
            color={color}
            columnas={columnasPlantilla}
            onImportar={filas => api.post('/catalogos/importar', {
              modulo: nivelActual.modulo, tipo: nivelActual.tipo, filas,
            }).then(r => r.data)}
            onListo={() => qc.invalidateQueries({ queryKey: ['catalogo-admin'] })}
          />
        </Box>
      )}

      {hijo && (
        <Alert severity="info" sx={{ mb: 1.5, py: 0.3 }}>
          Cada valor puede abrirse para administrar sus <strong>{hijo.label.toLowerCase()}</strong>.
        </Alert>
      )}

      <Stack spacing={0.5}>
        {filtrados.length === 0 && (
          <Typography variant="body2" color="text.disabled" textAlign="center" py={3}>
            {valores.length === 0 ? 'Sin valores. Agregue el primero.' : 'Ninguno coincide.'}
          </Typography>
        )}
        {filtrados.map(v => (
          <Stack key={v.id} direction="row" alignItems="center" gap={0.5}
            sx={{
              px: 1.2, py: 0.8, borderRadius: 1, border: '1px solid #E5E7EB',
              bgcolor: '#FFFFFF', opacity: v.activo === false ? 0.5 : 1,
              cursor: hijo ? 'pointer' : 'default',
              '&:hover': hijo ? { borderColor: color, bgcolor: alpha(color, 0.04) } : {},
            }}
            onClick={hijo ? () => { setRuta([...ruta, v]); setBusqueda('') } : undefined}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" fontWeight={600} noWrap>{v.nombre}</Typography>
              {(v.codigo || (v.total_hijos ?? 0) > 0 || v.activo === false) && (
                <Typography variant="caption" color="text.secondary" noWrap display="block">
                  {[
                    v.codigo,
                    (v.total_hijos ?? 0) > 0 && hijo
                      ? `${v.total_hijos} ${hijo.label.toLowerCase()}`
                      : null,
                    v.activo === false ? 'inactivo' : null,
                  ].filter(Boolean).join(' · ')}
                </Typography>
              )}
            </Box>
            <IconButton size="small" onClick={e => { e.stopPropagation(); setDlg({ abierto: true, item: v }) }}>
              <EditIcon sx={{ fontSize: 15 }} />
            </IconButton>
            <IconButton size="small" onClick={e => {
              e.stopPropagation()
              if (window.confirm(`¿Eliminar "${v.nombre}"?`)) mutBorrar.mutate(v.id)
            }}>
              <DeleteIcon sx={{ fontSize: 15 }} />
            </IconButton>
            {hijo && <ChevronRight sx={{ fontSize: 16, color: 'text.disabled' }} />}
          </Stack>
        ))}
      </Stack>

      <Dialog open={dlg.abierto} onClose={() => setDlg({ abierto: false, item: null })}
        maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, fontSize: 16 }}>
          {dlg.item ? 'Editar valor' : `Agregar a ${nivelActual?.label.toLowerCase()}`}
          {ruta.length > 0 && (
            <Typography variant="caption" color="text.secondary" display="block">
              dentro de {ruta[ruta.length - 1].nombre}
            </Typography>
          )}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} pt={0.5}>
            <TextField label="Nombre *" size="small" fullWidth autoFocus
              value={form.nombre}
              onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} />
            <TextField label="Código (opcional)" size="small" fullWidth
              value={form.codigo}
              onChange={e => setForm(f => ({ ...f, codigo: e.target.value }))}
              helperText="Código DANE, cuenta del PUC, abreviatura…" />
            <FormControlLabel
              control={<Switch checked={form.activo}
                onChange={e => setForm(f => ({ ...f, activo: e.target.checked }))} />}
              label={<Typography variant="body2">Activo</Typography>} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setDlg({ abierto: false, item: null })}>Cancelar</Button>
          <Button variant="contained" disabled={!form.nombre.trim() || mutGuardar.isPending}
            onClick={() => mutGuardar.mutate()} sx={{ bgcolor: color }}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
