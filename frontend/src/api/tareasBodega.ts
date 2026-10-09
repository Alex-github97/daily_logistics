/** WMS · frentes de picking, reabastecimiento y asignación dirigida de tareas (las jornadas son de WFM · Personal). */
import { apiClient as api } from './client'
import type { Tarea } from './wmsTrazable'

const datos = <T,>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface TareaOp extends Tarea {
  operario_id?: number | null; contenedor_origen?: string | null; aprobada_por?: string | null; aprobada?: string | null
  asignada?: string | null; origen_confirmado?: boolean; jornada_id?: number | null; en_curso_min?: number | null
}
export interface ConfigTareas {
  reabastecimiento_activo: boolean; requiere_aprobacion: boolean; picking_solo_frentes: boolean
  picking_reserva_si_falta: boolean; picking_excluir_pos: boolean; exigir_escaneo_origen: boolean
  liberar_asignada_min: number; alerta_en_curso_min: number; nivel_montacargas: number
}
export interface Frente {
  id: number; almacen_id: number; producto_id: number; sku?: string; producto?: string; ubicacion_id: number
  ubicacion?: string; zona?: string; sala_pos: boolean; unidad: string; minimo: number; maximo: number
  prioridad: number; activo: boolean; tareas_abiertas: number; factor: number | null; minimo_u: number
  maximo_u: number; actual: number; en_camino: number; estado: 'OK' | 'BAJO' | 'AGOTADO' | 'SOBRE' | 'SIN_EMPAQUE'
  pct: number | null
}
export type FrenteIn = Pick<Frente, 'almacen_id' | 'producto_id' | 'ubicacion_id' | 'unidad' | 'minimo' | 'maximo' | 'prioridad' | 'activo'>
export const bodega = {
  config: (almacen_id: number) => datos<ConfigTareas>(api.get('/wms/config-tareas', { params: { almacen_id } })),
  guardarConfig: (almacen_id: number, d: ConfigTareas) => datos<ConfigTareas>(api.put('/wms/config-tareas', d, { params: { almacen_id } })),
  frentes: (almacen_id: number) => datos<Frente[]>(api.get('/wms/frentes', { params: { almacen_id } })),
  crearFrente: (d: FrenteIn) => datos<Frente>(api.post('/wms/frentes', d)),
  editarFrente: (id: number, d: FrenteIn) => datos<Frente>(api.put(`/wms/frentes/${id}`, d)),
  borrarFrente: (id: number) => api.delete(`/wms/frentes/${id}`),
  evaluar: (almacen_id: number) => datos<{ creadas: number[]; sin_reserva: number[]; frentes: number }>(api.post('/wms/reabastecimiento/evaluar', null, { params: { almacen_id } })),
  tareas: (p: Record<string, unknown>) => datos<TareaOp[]>(api.get('/wms/tareas', { params: p })),
  aprobar: (ids: number[]) => datos<{ aprobadas: number }>(api.post('/wms/tareas/aprobar', { ids })),
  rechazar: (id: number, motivo: string) => datos<TareaOp>(api.post(`/wms/tareas/${id}/rechazar`, { motivo })),
  reasignar: (id: number, operario_id: number | null) => datos<TareaOp>(api.post(`/wms/tareas/${id}/reasignar`, { operario_id })),
  cancelar: (id: number, motivo: string) => datos<TareaOp>(api.post(`/wms/tareas/${id}/cancelar`, { motivo })),
  siguiente: () => datos<{ tarea: TareaOp | null }>(api.post('/wms/tareas/siguiente')),
  confirmarOrigen: (id: number, codigo: string) => datos<TareaOp>(api.post(`/wms/tareas/${id}/confirmar-origen`, { codigo })),
  completar: (id: number, d: { ubicacion_codigo: string; motivo_desvio?: string; cantidad?: number }) => datos<TareaOp>(api.post(`/wms/tareas/${id}/completar`, d)),
  novedad: (id: number, tipo: string, detalle?: string) => datos<TareaOp>(api.post(`/wms/tareas/${id}/novedad`, { tipo, detalle })),
}

export const TIPO_TAREA: Record<string, string> = { UBICACION: 'Ubicar', REABASTECIMIENTO: 'Reabastecer', MOVIMIENTO: 'Mover' }
export const ESTADO_TAREA: Record<string, { t: string; c: string }> = {
  POR_APROBAR: { t: 'Por aprobar', c: '#9333EA' }, PENDIENTE: { t: 'En cola', c: '#D97706' },
  ASIGNADA: { t: 'Asignada', c: '#0891B2' }, EN_CURSO: { t: 'En curso', c: '#2563EB' },
  COMPLETADA: { t: 'Completada', c: '#15803D' }, CANCELADA: { t: 'Cancelada', c: '#64748B' }, RECHAZADA: { t: 'Rechazada', c: '#DC2626' },
}
export const minutos = (m?: number | null) => m == null ? '—' : m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`
export const MOTIVOS_PAUSA: Record<string, string> = {
  DESCANSO: 'Descanso', ALMUERZO: 'Almuerzo', CAPACITACION: 'Capacitación', REUNION: 'Reunión', OTRO: 'Otro',
}
