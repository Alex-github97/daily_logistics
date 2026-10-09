/** WFM · Personal operativo: estaciones, personas, programación, jornadas, kiosco y productividad. */
import { apiClient as api } from './client'
import type { TareaOp } from './tareasBodega'

const datos = <T,>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface Estacion {
  id: number; codigo: string; nombre: string; tipo: string; almacen_id: number | null; funciones: string[]; zonas: number[]
  requiere_montacargas: boolean; capacidad: number; color: string | null; activo: boolean; notas: string | null
}
export type EstacionIn = Omit<Estacion, 'id'>
export interface Persona {
  usuario_id: number; nombre: string; username: string; rol: string; carne: string | null; cargo: string | null
  habilidades: string[]; almacen_id: number | null; estacion_id: number | null; activo: boolean; con_perfil: boolean
  jornada: { id: number; estado: string; estacion_id: number | null } | null
}
export interface Programacion {
  id: number; fecha: string; turno: string; hora_inicio: string | null; hora_fin: string | null; usuario_id: number
  persona: string; estacion_id: number; estacion: string; notas: string | null
}
export interface Pausa { motivo: string; inicio: string; fin: string | null; min: number }
export interface Tramo { estacion_id: number | null; estacion: string | null; inicio: string; fin: string | null; min: number }
export interface Jornada {
  id: number; usuario_id: number; persona?: string; almacen_id: number; estado: 'ACTIVA' | 'PAUSADA' | 'CERRADA'
  inicio: string; fin: string | null; estacion_id: number | null; estacion: string | null; estacion_codigo: string | null
  funciones: string[]; zonas: number[]; montacargas: boolean; cierre_auto: boolean; origen: string | null
  pausa_actual: Pausa | null; minutos: number; pausa_min: number; productivo_min: number; sin_tarea_min: number
  utilizacion_pct: number | null; tareas: number; por_tipo: Record<string, number>; tareas_hora: number | null
  pausas: Pausa[]; tramos: Tramo[]; tarea?: TareaOp | null
}
export interface MiJornada {
  jornada: Jornada | null
  programado: { estacion_id: number; estacion: string | null; turno: string; hora_inicio: string | null; hora_fin: string | null } | null
  perfil: { carne: string | null; habilidades: string[]; estacion_id: number | null; almacen_id: number | null } | null
}
export interface MisTareas {
  actual: TareaOp | null; en_cola: number; hechas_hoy: number
  picking: { id: number; orden_id: number; tipo: string; estado: string; items: number; asignada: string | null }[]
}
export interface ProdPersona {
  usuario_id: number; persona?: string; jornadas: number; horas: number; minutos: number; pausa_min: number
  productivo_min: number; tareas: number; por_tipo: Record<string, number>; utilizacion_pct: number | null; tareas_hora: number | null
}
export interface ProdEstacion { estacion_id: number | null; estacion: string; horas: number; minutos: number; personas: number }
export interface TableroEstacion extends Estacion {
  programados: { usuario_id: number; persona: string; turno: string; hora_inicio: string | null; hora_fin: string | null; presente: boolean; programacion_id: number }[]
  trabajando: Jornada[]; en_cola: number
}
export interface Tablero {
  estaciones: TableroEstacion[]; sin_estacion: Jornada[]
  ausentes: { usuario_id: number; persona: string; estacion_id: number; turno: string; hora_inicio: string | null }[]
  resumen: { programados: number; presentes: number; en_pausa: number; con_tarea: number; ausentes: number; en_cola: number }
}

export const personal = {
  estaciones: (almacen_id?: number) => datos<Estacion[]>(api.get('/personal/estaciones', { params: { almacen_id } })),
  crearEstacion: (d: EstacionIn) => datos<Estacion>(api.post('/personal/estaciones', d)),
  editarEstacion: (id: number, d: EstacionIn) => datos<Estacion>(api.put(`/personal/estaciones/${id}`, d)),
  borrarEstacion: (id: number) => api.delete(`/personal/estaciones/${id}`),
  personas: () => datos<Persona[]>(api.get('/personal/personas')),
  guardarPersona: (uid: number, d: Pick<Persona, 'carne' | 'cargo' | 'habilidades' | 'almacen_id' | 'estacion_id' | 'activo'>) => datos<{ carne: string }>(api.put(`/personal/personas/${uid}`, d)),
  generarCarne: (uid: number) => datos<{ carne: string }>(api.post(`/personal/personas/${uid}/carne`)),
  programacion: (fecha: string, almacen_id?: number) => datos<Programacion[]>(api.get('/personal/programacion', { params: { fecha, almacen_id } })),
  programar: (d: { fecha: string; usuario_id: number; estacion_id: number; turno: string; hora_inicio?: string | null; hora_fin?: string | null }) =>
    datos<{ id: number; aviso: string | null }>(api.post('/personal/programacion', d)),
  desprogramar: (id: number) => api.delete(`/personal/programacion/${id}`),
  copiar: (desde: string, hacia: string) => datos<{ copiadas: number }>(api.post('/personal/programacion/copiar', { desde, hacia })),
  miJornada: () => datos<MiJornada>(api.get('/personal/mi-jornada')),
  misTareas: () => datos<MisTareas>(api.get('/personal/mis-tareas')),
  iniciar: (d: { almacen_id?: number; estacion_id?: number | null; funciones: string[]; zonas: number[]; montacargas: boolean }) => datos<Jornada>(api.post('/personal/jornadas/iniciar', d)),
  pausar: (motivo: string) => datos<Jornada>(api.post('/personal/jornadas/pausar', { motivo })),
  reanudar: () => datos<Jornada>(api.post('/personal/jornadas/reanudar')),
  cerrar: () => datos<Jornada>(api.post('/personal/jornadas/cerrar')),
  cerrarDe: (id: number) => datos<Jornada>(api.post(`/personal/jornadas/${id}/cerrar`)),
  moverEstacion: (id: number, estacion_id: number | null) => datos<Jornada>(api.post(`/personal/jornadas/${id}/estacion`, { estacion_id })),
  jornadas: (p: Record<string, unknown>) => datos<Jornada[]>(api.get('/personal/jornadas', { params: p })),
  productividad: (p: Record<string, unknown>) => datos<{ personas: ProdPersona[]; estaciones: ProdEstacion[] }>(api.get('/personal/productividad', { params: p })),
  tablero: (almacen_id?: number) => datos<Tablero>(api.get('/personal/tablero', { params: { almacen_id } })),
  marcar: (carne: string) => datos<{ accion: 'ENTRADA' | 'SALIDA'; persona: string; estacion: string | null; jornada: Jornada }>(api.post('/personal/kiosco/marcar', { carne })),
}

export const TIPOS_ESTACION: Record<string, string> = {
  RECEPCION: 'Recepción', UBICACION: 'Ubicación / montacargas', REABASTECIMIENTO: 'Reabastecimiento', PICKING: 'Picking',
  EMPAQUE: 'Empaque', DESPACHO: 'Despacho', CONTEO: 'Conteo', CAJA: 'Caja POS', CONDUCCION: 'Conducción', GENERAL: 'General',
}
export const HABILIDADES: Record<string, string> = {
  MONTACARGAS: 'Montacargas', RECEPCION: 'Recepción', UBICACION: 'Ubicación', REABASTECIMIENTO: 'Reabastecimiento',
  PICKING: 'Picking', EMPAQUE: 'Empaque', DESPACHO: 'Despacho', CONTEO: 'Conteo', CAJA: 'Caja', CONDUCCION: 'Conducción',
}
export const FUNCIONES: Record<string, string> = { UBICACION: 'Ubicar lo recibido', REABASTECIMIENTO: 'Reabastecer frentes', MOVIMIENTO: 'Reubicar (slotting)' }
export const TURNOS: Record<string, string> = { DIA: 'Día completo', MANANA: 'Mañana', TARDE: 'Tarde', NOCHE: 'Noche' }
