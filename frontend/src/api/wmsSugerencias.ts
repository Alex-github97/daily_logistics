/** WMS · Sugerencias: slotting, olas de alistamiento, empaque y maquila. */
import { apiClient as api } from './client'

const datos = <T,>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface Sugerencia {
  tipo: 'ACERCAR' | 'ALEJAR'; producto_id: number; sku: string; clase: string; lineas: number; lote_id?: number | null
  cantidad: number; origen_id: number; origen: string; destino_id: number; destino: string; razon: string
}
export interface Parada {
  ubicacion_id: number; ubicacion: string; puesto: number; producto_id: number; sku: string; producto: string
  lote_id?: number | null; lote?: string | null; contenedor_id?: number | null; contenedor?: string | null
  cantidad: number; alistado: number; hecha: boolean
  reparto: { orden: string; tarea_id: number; detalle_id: number; cantidad: number; alistado: number | null }[]
}
export interface Ola {
  id: number; codigo: string; almacen_id: number; estado: string; criterio?: string; creada?: string; completada_en?: string | null
  ordenes: { orden_id: number; numero: string; tarea_id: number; prioridad: string; estado_tarea: string; lineas: number; sin_existencia: boolean }[]
  paradas?: Parada[]; visitas_ola?: number; visitas_orden_por_orden?: number; recorrido_ola?: number
  recorrido_orden_por_orden?: number; ahorro_recorrido_pct?: number | null
}
export interface Bulto {
  numero?: number; caja_id?: number | null; caja?: string; largo_cm?: number | null; ancho_cm?: number | null
  alto_cm?: number | null; peso_kg?: number | null; peso_volumetrico_kg?: number; peso_facturable_kg?: number
  llenado_pct?: number; contenido: { producto_id: number; sku?: string; cantidad: number }[]
}

export const sug = {
  recorrido: (almacen_id: number) => datos<any[]>(api.get('/wms/slotting/ubicaciones', { params: { almacen_id } })),
  abc: (almacen_id: number, dias = 90) => datos<any[]>(api.get('/wms/slotting/abc', { params: { almacen_id, dias } })),
  sugerencias: (almacen_id: number, dias = 90) => datos<Sugerencia[]>(api.get('/wms/slotting/sugerencias', { params: { almacen_id, dias } })),
  aplicar: (almacen_id: number, movimientos: Sugerencia[]) => datos<{ tareas: number[]; omitidas: number }>(api.post('/wms/slotting/aplicar', {
    almacen_id, movimientos: movimientos.map(m => ({ producto_id: m.producto_id, lote_id: m.lote_id, cantidad: m.cantidad,
      origen_id: m.origen_id, destino_id: m.destino_id, razon: m.razon })) })),
  olas: (p: Record<string, unknown>) => datos<Ola[]>(api.get('/wms/olas', { params: p })),
  ola: (id: number) => datos<Ola>(api.get(`/wms/olas/${id}`)),
  crearOla: (d: Record<string, unknown>) => datos<Ola>(api.post('/wms/olas', d)),
  parada: (id: number, d: Record<string, unknown>) => datos<Ola>(api.post(`/wms/olas/${id}/parada`, d)),
  cajas: () => datos<any[]>(api.get('/wms/cajas-empaque')),
  crearCaja: (d: Record<string, unknown>) => datos<any>(api.post('/wms/cajas-empaque', d)),
  editarCaja: (id: number, d: Record<string, unknown>) => datos<any>(api.put(`/wms/cajas-empaque/${id}`, d)),
  sugerirEmpaque: (oid: number) => datos<any>(api.post(`/wms/ordenes-salida/${oid}/empaque/sugerir`)),
  confirmarEmpaque: (oid: number, bultos: Bulto[]) => datos<any>(api.post(`/wms/ordenes-salida/${oid}/empaque/confirmar`, { bultos })),
  empaque: (oid: number) => datos<any>(api.get(`/wms/ordenes-salida/${oid}/empaque`)),
  recetas: () => datos<any[]>(api.get('/wms/maquila/recetas')),
  crearReceta: (d: Record<string, unknown>) => datos<any>(api.post('/wms/maquila/recetas', d)),
  editarReceta: (id: number, d: Record<string, unknown>) => datos<any>(api.put(`/wms/maquila/recetas/${id}`, d)),
  posible: (id: number, almacen_id: number) => datos<any>(api.get(`/wms/maquila/recetas/${id}/posible`, { params: { almacen_id } })),
  ordenesMaquila: (p: Record<string, unknown>) => datos<any[]>(api.get('/wms/maquila/ordenes', { params: p })),
  crearOrdenMaquila: (d: Record<string, unknown>) => datos<any>(api.post('/wms/maquila/ordenes', d)),
  iniciarMaquila: (id: number) => datos<any>(api.post(`/wms/maquila/ordenes/${id}/iniciar`)),
  terminarMaquila: (id: number, d: Record<string, unknown>) => datos<any>(api.post(`/wms/maquila/ordenes/${id}/terminar`, d)),
  cancelarMaquila: (id: number) => datos<any>(api.post(`/wms/maquila/ordenes/${id}/cancelar`)),
  resumenMaquila: (p: Record<string, unknown>) => datos<any[]>(api.get('/wms/maquila/resumen', { params: p })),
}
