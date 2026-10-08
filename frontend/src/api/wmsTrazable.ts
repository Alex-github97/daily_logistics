/** WMS trazable: depositantes, estibas (LPN), tareas, kárdex y recorrido de lote. */
import { apiClient as api } from './client'
import { aFecha } from '@/utils/fechas'

const datos = <T,>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface Movimiento {
  id: number; fecha: string; tipo: string; producto_id: number; sku?: string; producto?: string; lote?: string
  cantidad: number; origen?: string | null; destino?: string | null; estado_origen?: string | null
  estado_destino?: string | null; contenedor?: string | null; contenedor_destino?: string | null
  saldo_origen?: number | null; saldo_destino?: number | null; documento_tipo?: string | null
  documento_id?: number | null; referencia?: string | null; tarea_id?: number | null; costo_unitario?: number | null
  usuario?: string | null; notas?: string | null; efecto?: number; saldo?: number
}
export interface Kardex {
  saldo_inicial: number; saldo_final: number; movimientos: Movimiento[]; total_movimientos: number
  completo: boolean; existencia_actual: number | null; diferencia: number | null
}
export interface Tarea {
  id: number; tipo: string; estado: string; prioridad: number; almacen_id: number; producto_id?: number
  sku?: string; producto?: string; lote?: string; contenedor_id?: number; contenedor?: string; cantidad?: number
  origen?: string; sugerida_id?: number; sugerida?: string; razon_sugerencia?: string; destino?: string
  motivo_desvio?: string; documento_tipo?: string; documento_id?: number; operario?: string; creada?: string
  iniciada?: string; terminada?: string; espera_min?: number | null; ejecucion_min?: number | null; notas?: string
}
export interface Contenedor {
  id: number; codigo: string; tipo: string; estado: string; almacen_id: number; almacen?: string
  ubicacion_id?: number; ubicacion?: string; depositante_id?: number; depositante?: string
  documento_tipo?: string; documento_id?: number; creado?: string; lineas: number; unidades: number; notas?: string
  contenido?: { producto_id: number; sku?: string; producto?: string; lote_id?: number; lote?: string
    disponible: number; reservado: number; bloqueado: number }[]
  historia?: Movimiento[]
}
export interface Recorrido {
  lote: { id: number; numero: string; vence?: string; fabricado?: string; activo: boolean }
  producto?: { id: number; sku: string; nombre: string }; depositante?: string
  origen: { recepcion: string; recepcion_id: number; fecha: string; estado: string; orden_compra?: string
    proveedor?: string; cantidad: number; calidad: string }[]
  destino: { fecha: string; tipo: string; a_quien: string; contacto?: string; documento?: string; cantidad: number }[]
  clientes: { a_quien: string; contacto?: string; cantidad: number; documentos: string[]; ultima: string }[]
  queda: { ubicacion: string; contenedor?: string; disponible: number; reservado: number; bloqueado: number }[]
  recibido: number; salido: number; en_bodega: number
}

export const wms = {
  depositantes: () => datos<any[]>(api.get('/wms/depositantes')),
  almacenes: () => datos<any[]>(api.get('/wms/almacenes/')),
  productos: () => datos<any[]>(api.get('/wms/productos/')),
  lotes: () => datos<any[]>(api.get('/wms/lotes/')),
  ubicaciones: () => datos<any[]>(api.get('/wms/ubicaciones/')),
  kardex: (p: Record<string, unknown>) => datos<Kardex>(api.get('/wms/kardex', { params: p })),
  documento: (tipo: string, id: number) => datos<Movimiento[]>(api.get('/wms/trazabilidad/documento', { params: { tipo, id } })),
  recorrido: (loteId: number) => datos<Recorrido>(api.get(`/wms/trazabilidad/lote/${loteId}/recorrido`)),
  retenerLote: (loteId: number, motivo: string) => datos<any>(api.post(`/wms/trazabilidad/lote/${loteId}/retener`, { motivo })),
  tareas: (p: Record<string, unknown>) => datos<Tarea[]>(api.get('/wms/tareas', { params: p })),
  iniciarTarea: (id: number) => datos<Tarea>(api.post(`/wms/tareas/${id}/iniciar`)),
  completarTarea: (id: number, d: { ubicacion_codigo: string; motivo_desvio?: string }) => datos<Tarea>(api.post(`/wms/tareas/${id}/completar`, d)),
  cancelarTarea: (id: number, motivo: string) => datos<Tarea>(api.post(`/wms/tareas/${id}/cancelar`, { motivo })),
  resugerir: (id: number) => datos<Tarea>(api.post(`/wms/tareas/${id}/resugerir`)),
  contenedores: (p: Record<string, unknown>) => datos<Contenedor[]>(api.get('/wms/contenedores', { params: p })),
  contenedor: (id: number) => datos<Contenedor>(api.get(`/wms/contenedores/${id}`)),
  contenedorPorCodigo: (codigo: string) => datos<Contenedor>(api.get(`/wms/contenedores/codigo/${encodeURIComponent(codigo)}`)),
  crearContenedor: (d: Record<string, unknown>) => datos<Contenedor>(api.post('/wms/contenedores', d)),
  moverContenedor: (id: number, ubicacion_codigo: string) => datos<Contenedor>(api.post(`/wms/contenedores/${id}/mover`, { ubicacion_codigo })),
  agregarAContenedor: (id: number, d: { producto_id: number; lote_id?: number | null; cantidad: number }) => datos<Contenedor>(api.post(`/wms/contenedores/${id}/agregar`, d)),
  cerrarContenedor: (id: number) => datos<Contenedor>(api.post(`/wms/contenedores/${id}/cerrar`)),
}

export const TIPO_MOV: Record<string, string> = {
  RECEPCION: 'Recepción', UBICACION: 'Ubicación', TRANSFERENCIA: 'Traslado', AJUSTE: 'Ajuste', CONTEO: 'Conteo',
  RESERVA: 'Reserva', LIBERACION: 'Liberación', BLOQUEO: 'Bloqueo', DESBLOQUEO: 'Desbloqueo', DESPACHO: 'Salida',
  DEVOLUCION: 'Devolución', CONSOLIDACION: 'Armado de estiba', CROSS_DOCKING: 'Cross-docking',
}

export const fechaHora = (s?: string | null) => s ? aFecha(s).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' }) : '—'
export const num = (v?: number | null) => v == null ? '—' : v.toLocaleString('es-CO', { maximumFractionDigits: 3 })
