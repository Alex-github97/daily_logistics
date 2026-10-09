/** WMS · consolidación de salida por destino y TMS · solicitudes de transporte y cargue de vehículos. */
import { apiClient as api } from './client'

const datos = <T,>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface OrdenPorConsolidar {
  id: number; numero: string; cliente: string | null; almacen_id: number; canal: string | null; prioridad: string
  pedido: string | null; plataforma: string | null; destino: string | null; destino_ciudad: string | null
  destino_direccion: string | null; destino_contacto: string | null; destino_telefono: string | null
  unidades: number; productos: number; peso_kg: number | null; volumen_m3: number | null
  consolidado_id: number | null; consolidado: string | null
}
export interface Consolidado {
  id: number; codigo: string; almacen_id: number; destino: string; destino_ciudad: string | null; estado: string
  individual: boolean; modo_despacho: string | null; modo_nombre: string | null; transportadora_id: number | null
  transportadora: string | null; guia: string | null; bultos: number; peso_kg: number | null; volumen_m3: number | null
  solicitud: string | null; cargue_id: number | null; viaje_id: number | null; notas: string | null; creado: string | null
  ordenes: { orden_id: number; numero: string | null; pedido: string | null; direccion: string | null; contacto: string | null; peso_kg: number | null; volumen_m3: number | null }[]
}
export interface Solicitud {
  id: number; codigo: string; almacen: string | null; almacen_id: number; modo_despacho: string; modo_nombre: string
  transportadora: string | null; estado: string; creada: string | null; notas: string | null; consolidados: number
  pendientes: number; en_cargue: number; despachados: number; bultos: number; peso_kg: number; volumen_m3: number
}
export interface Capacidad {
  ok: boolean; motivos: string[]; avisos: string[]; capacidad_kg: number | null; capacidad_m3: number | null
  uso_kg_pct: number | null; uso_m3_pct: number | null; cargado_kg: number; cargado_m3: number; tipo_nombre: string
}
export interface Cargue {
  id: number; codigo: string; almacen_id: number; modo_despacho: string; modo_nombre: string; tercerizado: boolean
  vehiculo_id: number | null; vehiculo: string | null; transportadora_id: number | null; transportadora: string | null
  placa_tercero: string | null; estado: string; notas: string | null; viaje_id: number | null; viaje: string | null
  consolidados: Consolidado[]; destinos: { destino: string; consolidados: number; pedidos: number; bultos: number }[]
  totales: { consolidados: number; pedidos: number; bultos: number; peso_kg: number; volumen_m3: number; sin_peso: boolean; sin_volumen: boolean }
  capacidad: Capacidad | null
}
export type CargueIn = { almacen_id: number; modo_despacho: string; vehiculo_id?: number | null; transportadora_id?: number | null; placa_tercero?: string | null; notas?: string | null }

export const consolidacion = {
  porConsolidar: (almacen_id?: number) => datos<OrdenPorConsolidar[]>(api.get('/wms/consolidacion/por-consolidar', { params: { almacen_id } })),
  destino: (oid: number, d: { destino: string; ciudad?: string | null; direccion?: string | null; contacto?: string | null; telefono?: string | null }) =>
    datos<OrdenPorConsolidar>(api.put(`/wms/consolidacion/ordenes/${oid}/destino`, d)),
  consolidar: (orden_ids: number[], individual = false) => datos<Consolidado[]>(api.post('/wms/consolidacion/consolidados', { orden_ids, individual })),
  agregar: (cid: number, orden_ids: number[]) => datos<Consolidado>(api.post(`/wms/consolidacion/consolidados/${cid}/ordenes`, { orden_ids })),
  quitarOrden: (cid: number, oid: number) => datos<Consolidado>(api.delete(`/wms/consolidacion/consolidados/${cid}/ordenes/${oid}`)),
  cerrar: (cid: number, bultos: number, notas?: string) => datos<Consolidado>(api.post(`/wms/consolidacion/consolidados/${cid}/cerrar`, { bultos, notas })),
  reabrir: (cid: number) => datos<Consolidado>(api.post(`/wms/consolidacion/consolidados/${cid}/reabrir`)),
  anular: (cid: number) => api.post(`/wms/consolidacion/consolidados/${cid}/anular`),
  modo: (ids: number[], modo: string, transportadora_id?: number | null, guia?: string | null) =>
    datos<Consolidado[]>(api.post('/wms/consolidacion/modo', { ids, modo, transportadora_id, guia })),
  solicitar: (ids: number[], notas?: string) => datos<{ solicitudes: { codigo: string; modo: string; consolidados: number }[] }>(api.post('/wms/consolidacion/solicitar-transporte', { ids, notas })),
  consolidados: (p: Record<string, unknown>) => datos<Consolidado[]>(api.get('/wms/consolidacion/consolidados', { params: p })),
  modos: () => datos<{ clave: string; nombre: string; tercerizado: boolean }[]>(api.get('/wms/consolidacion/modos')),
  etiqueta: async (cid: number) => {
    const r = await api.get(`/wms/consolidacion/consolidados/${cid}/etiqueta`, { responseType: 'blob' })
    window.open(URL.createObjectURL(r.data), '_blank')
  },
  // TMS
  solicitudes: (p: Record<string, unknown>) => datos<Solicitud[]>(api.get('/tms/solicitudes-transporte', { params: p })),
  cargaPendiente: (p: Record<string, unknown>) => datos<Consolidado[]>(api.get('/tms/carga-pendiente', { params: p })),
  devolver: (cid: number, motivo: string) => api.post(`/tms/carga-pendiente/${cid}/devolver`, { motivo }),
  cargues: (estado = 'ARMANDO') => datos<Cargue[]>(api.get('/tms/cargues', { params: { estado } })),
  cargue: (id: number) => datos<Cargue>(api.get(`/tms/cargues/${id}`)),
  crearCargue: (d: CargueIn) => datos<Cargue>(api.post('/tms/cargues', d)),
  editarCargue: (id: number, d: CargueIn) => datos<Cargue>(api.put(`/tms/cargues/${id}`, d)),
  asignar: (id: number, d: { codigo?: string; consolidado_id?: number }) => datos<Cargue>(api.post(`/tms/cargues/${id}/asignar`, d)),
  quitar: (id: number, consolidado_id: number) => datos<Cargue>(api.post(`/tms/cargues/${id}/quitar`, { consolidado_id })),
  cancelarCargue: (id: number) => api.post(`/tms/cargues/${id}/cancelar`),
  confirmar: (id: number, d: { fecha_programada_entrega?: string | null; notas?: string | null }) =>
    datos<{ viaje_id: number; viaje: string; despachos: number; paradas: number; cargue: Cargue }>(api.post(`/tms/cargues/${id}/confirmar`, d)),
}

export const MODOS: Record<string, { nombre: string; corto: string; color: string; tercerizado: boolean }> = {
  PAQUETEO_URBANO_PROPIO: { nombre: 'Paqueteo urbano propio', corto: 'Urbano propio', color: '#0891B2', tercerizado: false },
  PAQUETEO_URBANO_TERCERO: { nombre: 'Paqueteo urbano tercerizado', corto: 'Urbano tercero', color: '#7C3AED', tercerizado: true },
  PAQUETEO_NACIONAL_TERCERO: { nombre: 'Paqueteo nacional tercerizado', corto: 'Nacional tercero', color: '#DB2777', tercerizado: true },
  FLOTA_PROPIA: { nombre: 'Viaje con flota propia', corto: 'Flota propia', color: '#EA580C', tercerizado: false },
}
export const ESTADO_CONS: Record<string, { t: string; c: string }> = {
  ABIERTO: { t: 'Consolidando', c: '#D97706' }, CERRADO: { t: 'Cerrado', c: '#2563EB' }, SOLICITADO: { t: 'Transporte solicitado', c: '#7C3AED' },
  EN_CARGUE: { t: 'En cargue', c: '#0891B2' }, DESPACHADO: { t: 'Despachado', c: '#15803D' }, ENTREGADO: { t: 'Entregado', c: '#047857' },
  ANULADO: { t: 'Anulado', c: '#94A3B8' },
}
