/**
 * El equipo de la consola y sus roles.
 *
 * Es distinto de los usuarios de una empresa: `Empresas → Usuarios` dice quién
 * puede entrar a la plataforma de esa empresa; esto dice quién además
 * administra la plataforma entera y hasta dónde llega.
 *
 * El equipo se arma sobre gente que ya tiene con qué entrar. Por eso se elige
 * de una lista y no se inventan credenciales acá.
 */
import { useState } from 'react'
import {
  Box, Card, Typography, Stack, Button, Chip, Table, TableBody, TableCell, TableHead, TableRow, IconButton, Tooltip, Skeleton, Alert, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, Divider, Accordion, AccordionSummary, AccordionDetails, Switch, FormControlLabel,
} from '@mui/material'
import { TextField } from '@/components/comun/Desplegables'
import {
  PersonAdd, Delete, ExpandMore, Shield, CheckCircle, RemoveCircleOutline,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { PALETA, ESTADO, COLOR_MODULO } from '@/config/marca'
import { equipoApi, mensajeDeError, type MiembroEquipo, type RolConsola } from './api'

const COLOR_ROL: Record<string, string> = {
  PROPIETARIO: ESTADO.peligro,
  ADMINISTRADOR: COLOR_MODULO,
  COMERCIAL: ESTADO.alerta,
  SOPORTE: ESTADO.exito,
  CONSULTA: PALETA.acero,
}

// ─── Agregar a alguien ────────────────────────────────────────────────────────

function DialogoNuevo({
  abierto, onCerrar, roles,
}: { abierto: boolean; onCerrar: () => void; roles: RolConsola[] }) {
  const qc = useQueryClient()
  const [usuario, setUsuario] = useState('')
  const [rol, setRol] = useState('SOPORTE')

  const { data: candidatos = [] } = useQuery({
    queryKey: ['equipo-candidatos'], queryFn: equipoApi.candidatos, enabled: abierto,
  })

  const agregar = useMutation({
    mutationFn: () => equipoApi.agregar({ usuario, rol }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['equipo'] })
      qc.invalidateQueries({ queryKey: ['equipo-candidatos'] })
      setUsuario(''); onCerrar(); toast.success('Miembro agregado')
    },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const libres = candidatos.filter(c => !c.ya_es_miembro)
  const elegido = roles.find(r => r.clave === rol)

  return (
    <Dialog open={abierto} onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Agregar al equipo</DialogTitle>
      <DialogContent>
        {libres.length === 0 ? (
          <Alert severity="info" sx={{ mt: 1 }}>
            Todos los usuarios de la empresa operadora ya hacen parte del equipo.
            Para sumar a alguien nuevo, créelo primero en Empresas → Usuarios.
          </Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select label="Persona" value={usuario} fullWidth required
              onChange={e => setUsuario(e.target.value)}
              helperText="Solo aparece quien ya puede iniciar sesión en la empresa operadora"
            >
              {libres.map(c => (
                <MenuItem key={c.username} value={c.username}>
                  {c.nombre} · {c.username}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="Rol" value={rol} fullWidth
              onChange={e => setRol(e.target.value)}>
              {roles.map(r => (
                <MenuItem key={r.clave} value={r.clave}>{r.nombre}</MenuItem>
              ))}
            </TextField>
            {elegido && (
              <Alert severity="info" icon={<Shield />}>
                <strong>{elegido.nombre}.</strong> {elegido.descripcion}
              </Alert>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCerrar} sx={{ textTransform: 'none' }}>Cancelar</Button>
        <Button
          variant="contained" onClick={() => agregar.mutate()}
          disabled={agregar.isPending || !usuario}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Agregar
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function Equipo() {
  const qc = useQueryClient()
  const [nuevo, setNuevo] = useState(false)

  const { data: yo } = useQuery({ queryKey: ['quien-soy'], queryFn: equipoApi.quienSoy })
  const { data: roles = [] } = useQuery({ queryKey: ['equipo-roles'], queryFn: equipoApi.roles })
  const { data: miembros = [], isLoading } = useQuery<MiembroEquipo[]>({
    queryKey: ['equipo'], queryFn: equipoApi.listar,
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['equipo'] })
    qc.invalidateQueries({ queryKey: ['quien-soy'] })
  }

  const cambiar = useMutation({
    mutationFn: ({ id, cambios }: { id: number; cambios: Record<string, unknown> }) =>
      equipoApi.editar(id, cambios),
    onSuccess: () => { refrescar(); toast.success('Miembro actualizado') },
    // El servidor impide dejar la consola sin propietario y quitarse a uno
    // mismo el acceso; el mensaje explica cuál de los dos es.
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  const quitar = useMutation({
    mutationFn: (id: number) => equipoApi.quitar(id),
    onSuccess: () => { refrescar(); toast.success('Acceso retirado') },
    onError: (e: any) => toast.error(mensajeDeError(e)),
  })

  return (
    <Box>
      <Stack direction="row" alignItems="center" mb={2.5}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" fontWeight={800}>Equipo de la consola</Typography>
          <Typography variant="caption" color="text.secondary">
            Quién administra la plataforma y hasta dónde llega
          </Typography>
        </Box>
        <Button
          startIcon={<PersonAdd />} variant="contained" onClick={() => setNuevo(true)}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          Agregar al equipo
        </Button>
      </Stack>

      {yo?.implicito && (
        <Alert severity="warning" sx={{ mb: 2.5 }}>
          <strong>El equipo todavía no está formalizado.</strong> Mientras esta lista
          esté vacía, cualquier administrador de la empresa operadora entra con acceso
          total. Agréguese a usted mismo como Propietario y a los demás con el rol que
          les corresponda; desde ahí manda esta lista.
        </Alert>
      )}

      <Card sx={{ borderRadius: 3, mb: 2.5 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>USUARIO</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>NOMBRE</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ROL</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>ACCESO</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && [0, 1].map(i => (
              <TableRow key={i}><TableCell colSpan={5}><Skeleton height={28} /></TableCell></TableRow>
            ))}
            {miembros.map(m => (
              <TableRow key={m.id} hover>
                <TableCell sx={{ fontWeight: 700, fontFamily: 'monospace' }}>
                  {m.usuario}
                  {m.usuario === yo?.usuario && (
                    <Chip label="usted" size="small" sx={{
                      ml: 1, height: 17, fontSize: 9.5, bgcolor: PALETA.niebla,
                    }} />
                  )}
                </TableCell>
                <TableCell sx={{ color: PALETA.grafito }}>{m.nombre ?? '—'}</TableCell>
                <TableCell>
                  <TextField
                    select size="small" value={m.rol} sx={{ minWidth: 156 }}
                    onChange={e => cambiar.mutate({ id: m.id, cambios: { rol: e.target.value } })}
                  >
                    {roles.map(r => (
                      <MenuItem key={r.clave} value={r.clave}>{r.nombre}</MenuItem>
                    ))}
                  </TextField>
                </TableCell>
                <TableCell>
                  <FormControlLabel
                    control={
                      <Switch
                        size="small" checked={m.activo}
                        onChange={e =>
                          cambiar.mutate({ id: m.id, cambios: { activo: e.target.checked } })}
                      />
                    }
                    label={
                      <Typography variant="caption" sx={{
                        color: m.activo ? ESTADO.exito : PALETA.acero, fontWeight: 700,
                      }}>
                        {m.activo ? 'Activo' : 'Suspendido'}
                      </Typography>
                    }
                  />
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Quitarle el acceso a la consola (no borra su usuario)">
                    <IconButton size="small" onClick={() => quitar.mutate(m.id)}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && miembros.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Box sx={{ textAlign: 'center', py: 4, color: PALETA.acero }}>
                    <Shield sx={{ fontSize: 38, opacity: 0.4 }} />
                    <Typography variant="body2" mt={1}>
                      El equipo está vacío
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {/* Qué puede cada rol */}
      <Typography variant="subtitle2" fontWeight={800} mb={1}>Qué puede cada rol</Typography>
      {roles.map(r => (
        <Accordion key={r.clave} disableGutters sx={{
          borderRadius: 2, mb: 0.75, '&:before': { display: 'none' },
          border: `1px solid ${PALETA.niebla}`,
        }}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ flex: 1 }}>
              <Chip label={r.nombre} size="small" sx={{
                fontWeight: 700, minWidth: 118,
                bgcolor: `${COLOR_ROL[r.clave] ?? PALETA.acero}1A`,
                color: COLOR_ROL[r.clave] ?? PALETA.acero,
              }} />
              <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                {r.descripcion}
              </Typography>
              <Chip label={`${r.permisos.length} permisos`} size="small" variant="outlined"
                sx={{ fontSize: 10 }} />
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Stack direction="row" flexWrap="wrap" gap={0.75}>
              {r.permisos.map(p => (
                <Chip key={p} label={p} size="small" icon={<CheckCircle sx={{ fontSize: 13 }} />}
                  sx={{ fontSize: 10.5, bgcolor: `${ESTADO.exito}14`, color: ESTADO.exito }} />
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}

      <Divider sx={{ my: 2.5 }} />
      <Alert severity="info" icon={<RemoveCircleOutline />}>
        Los roles se hacen cumplir en el servidor, no ocultando botones: si alguien
        con rol de soporte pide la contabilidad por su cuenta, el servidor la rechaza
        igual.
      </Alert>

      <DialogoNuevo abierto={nuevo} onCerrar={() => setNuevo(false)} roles={roles} />
    </Box>
  )
}
