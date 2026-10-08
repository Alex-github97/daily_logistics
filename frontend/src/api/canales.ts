/**
 * Canales de venta en línea (marketplaces, tiendas, webhook y archivos).
 */
import { apiClient } from '@/api/client'
import { aFecha } from '@/utils/fechas'

export interface Capacidades {
  pedidos_api: boolean; stock: boolean; envio: boolean; entrega: boolean; publicaciones: boolean
  webhook: boolean; oauth: boolean; notas: string[]
}
export interface TipoCanal {
  tipo: string; nombre: string; campos: { clave: string; etiqueta: string; secreto: boolean }[]; capacidades: Capacidades
}
export interface Conector {
  id: number; tipo: string; tipo_nombre: string; nombre: string; activo: boolean; almacen_id: number
  cliente_id: number | null; credenciales: Record<string, string>; config: Record<string, string>
  colchon_stock: number; sincronizar_stock: boolean; importar_pedidos: boolean
  estado_conexion: string | null; ultimo_error: string | null
  ultima_sync_pedidos: string | null; ultima_sync_stock: string | null
  url_webhook: string; autorizado: boolean | null; capacidades: Capacidades
  publicaciones_mapeadas?: number; pedidos_abiertos?: number
}
export interface Publicacion {
  id: number; conector_id: number; ref_externa: string; ref_variante: string; sku_externo: string | null
  titulo: string | null; producto_id: number | null; producto: { sku: string; nombre: string } | null
  unidades: number; activo: boolean; ultimo_stock_enviado: number | null; ultimo_envio: string | null; ultimo_error: string | null
}
export interface LineaPedido {
  id: number; sku_externo: string | null; titulo: string | null; cantidad: number; precio: number | null
  producto_id: number | null; producto: { sku: string; nombre: string } | null; unidades: number | null
}
export interface Pedido {
  id: number; conector_id: number; canal: string | null; tipo: string | null; pedido_externo: string
  estado: string; etapa: string; estado_externo: string | null; novedad: string | null; fecha_pedido: string | null
  comprador: string | null; telefono: string | null; direccion: string | null; ciudad: string | null
  total: number | null; orden_salida_id: number | null; numero_orden: string | null; despacho_id: number | null
  tracking: string | null; almacen_id: number | null; lineas?: LineaPedido[]
}
export interface Bitacora { id: number; conector_id: number | null; fecha: string; tipo: string; ok: boolean; mensaje: string }

export const canalesApi = {
  tipos: () => apiClient.get<TipoCanal[]>('/wms/canales/tipos').then(r => r.data),
  conectores: () => apiClient.get<Conector[]>('/wms/canales/conectores').then(r => r.data),
  crear: (d: unknown) => apiClient.post<Conector>('/wms/canales/conectores', d).then(r => r.data),
  actualizar: (id: number, d: unknown) => apiClient.put<Conector>(`/wms/canales/conectores/${id}`, d).then(r => r.data),
  probar: (id: number) => apiClient.post<{ ok: boolean; detalle: string }>(`/wms/canales/conectores/${id}/probar`).then(r => r.data),
  sincronizar: (id: number) => apiClient.post<{ pedidos?: number; stock_enviado?: number; stock_errores?: number; error?: string }>(
    `/wms/canales/conectores/${id}/sincronizar`, null, { timeout: 120000 }).then(r => r.data),
  autorizarML: (id: number) => apiClient.get<{ url: string }>(`/wms/canales/conectores/${id}/mercadolibre/autorizar`).then(r => r.data),
  publicaciones: (id: number) => apiClient.get<Publicacion[]>(`/wms/canales/conectores/${id}/publicaciones`).then(r => r.data),
  traerPublicaciones: (id: number) => apiClient.post<{ leidas: number; nuevas: number; mapeadas: number }>(
    `/wms/canales/conectores/${id}/publicaciones/traer`, null, { timeout: 120000 }).then(r => r.data),
  crearPublicacion: (id: number, d: unknown) => apiClient.post<Publicacion>(`/wms/canales/conectores/${id}/publicaciones`, d).then(r => r.data),
  actualizarPublicacion: (id: number, d: unknown) => apiClient.put<Publicacion>(`/wms/canales/publicaciones/${id}`, d).then(r => r.data),
  pedidos: (params: Record<string, unknown>) => apiClient.get<Pedido[]>('/wms/canales/pedidos', { params }).then(r => r.data),
  porDespachar: (almacen_id?: number | '') => apiClient.get<{ pedidos: Pedido[]; staging: { sku: string; nombre: string; almacen: string; unidades: number }[] }>(
    '/wms/canales/por-despachar', { params: almacen_id ? { almacen_id } : {} }).then(r => r.data),
  reprocesar: (id: number) => apiClient.post<Pedido>(`/wms/canales/pedidos/${id}/reprocesar`).then(r => r.data),
  cancelar: (id: number, motivo: string) => apiClient.post(`/wms/canales/pedidos/${id}/cancelar`, { motivo }).then(r => r.data),
  despachar: (pedido_ids: number[]) => apiClient.post<{ resultados: { pedido_id: number; pedido?: string; ok: boolean; despacho?: string; tracking?: string; detalle?: string }[] }>(
    '/wms/canales/despachar', { pedido_ids }, { timeout: 120000 }).then(r => r.data),
  bitacora: (conector_id?: number) => apiClient.get<Bitacora[]>('/wms/canales/bitacora', { params: conector_id ? { conector_id } : {} }).then(r => r.data),
}

/** Etapa del pedido en la salida, con su nombre técnico y su color. */
export const ETAPAS: Record<string, { nombre: string; color: string; ayuda: string }> = {
  RECIBIDO: { nombre: 'Recibido', color: '#64748B', ayuda: 'Llegó y está por comprometerse' },
  CON_NOVEDAD: { nombre: 'Con novedad', color: '#DC2626', ayuda: 'SKU sin mapear o stock insuficiente' },
  COMPROMETIDO: { nombre: 'Inventario comprometido', color: '#D97706', ayuda: 'Unidades reservadas; falta el picking' },
  EN_STAGING: { nombre: 'En staging de salida', color: '#4F46E5', ayuda: 'Alistado y listo para despachar' },
  DESPACHADO: { nombre: 'Despachado', color: '#0EA5E9', ayuda: 'Salió en un viaje del TMS' },
  ENTREGADO: { nombre: 'Entregado', color: '#16A34A', ayuda: 'El TMS confirmó la entrega' },
  CANCELADO: { nombre: 'Cancelado', color: '#94A3B8', ayuda: 'Reserva liberada' },
}

export const fechaCorta = (s: string | null) =>
  s ? aFecha(s).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
