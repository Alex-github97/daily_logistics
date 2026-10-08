/** Cliente del POS y de las resoluciones de facturación del ERP. */
import { apiClient as api } from './client'

const datos = <T,>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface ProductoCatalogo {
  producto_id: number; sku: string; nombre: string; codigo_barras?: string | null; unidad: string
  precio: number; tarifa_iva: number; disponible: number; imagen_url?: string | null
}
export interface Turno {
  id: number; caja_id: number; caja_nombre: string; cajero: string; apertura: string; base_inicial: number
  cierre?: string | null; estado: 'ABIERTO' | 'CERRADO'; esperado?: Record<string, number> | null
  contado?: Record<string, number> | null; diferencia?: number | null; observaciones?: string | null
  resumen: { esperado: Record<string, number>; ventas: number; total_ventas: number; total_devoluciones: number; movimientos: Record<string, number> }
}
export interface Venta {
  id: number; numero: string; fecha: string; caja_nombre: string; cajero: string; cliente_nombre: string
  cliente_documento?: string | null; subtotal: number; descuento: number; impuestos: number; total: number
  costo_total: number; recibido?: number | null; cambio: number; estado: string; cufe?: string | null
  lineas?: { id: number; producto_id: number; descripcion: string; cantidad: number; precio_unitario: number
    descuento_pct: number; tarifa_iva: number; base: number; iva: number; total: number; cantidad_devuelta: number }[]
  pagos?: { medio: string; nombre: string; monto: number; referencia?: string | null }[]
  emisor?: { razon_social: string; nit: string; direccion?: string; telefono?: string } | null
  resolucion?: string | null
}

export const pos = {
  medios: () => datos<{ valor: string; nombre: string }[]>(api.get('/pos/medios')),
  cajas: () => datos<any[]>(api.get('/pos/cajas')),
  crearCaja: (d: any) => datos<any>(api.post('/pos/cajas', d)),
  editarCaja: (id: number, d: any) => datos<any>(api.put(`/pos/cajas/${id}`, d)),
  listas: () => datos<any[]>(api.get('/pos/listas')),
  crearLista: (d: any) => datos<any>(api.post('/pos/listas', d)),
  editarLista: (id: number, d: any) => datos<any>(api.put(`/pos/listas/${id}`, d)),
  precios: (lid: number, q?: string) => datos<any[]>(api.get(`/pos/listas/${lid}/precios`, { params: { q } })),
  guardarPrecios: (lid: number, d: { producto_id: number; precio: number | null }[]) => datos<any>(api.put(`/pos/listas/${lid}/precios`, d)),
  zonas: () => datos<any[]>(api.get('/pos/zonas')),
  marcarZona: (id: number, vendible_pos: boolean) => datos<any>(api.put(`/pos/zonas/${id}`, { vendible_pos })),
  productoPOS: (id: number, d: { codigo_barras: string | null; tarifa_iva: number }) => datos<any>(api.put(`/pos/productos/${id}`, d)),
  catalogo: (cid: number, q?: string) => datos<ProductoCatalogo[]>(api.get(`/pos/cajas/${cid}/catalogo`, { params: { q } })),
  turnoActual: () => datos<Turno | null>(api.get('/pos/turnos/actual')),
  turnos: (p?: any) => datos<Turno[]>(api.get('/pos/turnos', { params: p })),
  abrirTurno: (caja_id: number, base_inicial: number) => datos<Turno>(api.post('/pos/turnos/abrir', { caja_id, base_inicial })),
  movimientoCaja: (tid: number, d: { tipo: string; monto: number; motivo: string }) => datos<Turno>(api.post(`/pos/turnos/${tid}/movimientos`, d)),
  cerrarTurno: (tid: number, d: { contado: Record<string, number>; observaciones?: string }) => datos<any>(api.post(`/pos/turnos/${tid}/cerrar`, d)),
  vender: (d: any) => datos<Venta>(api.post('/pos/ventas', d)),
  ventas: (p?: any) => datos<Venta[]>(api.get('/pos/ventas', { params: p })),
  venta: (id: number) => datos<Venta>(api.get(`/pos/ventas/${id}`)),
  devolver: (d: any) => datos<any>(api.post('/pos/devoluciones', d)),
  devoluciones: (p?: any) => datos<any[]>(api.get('/pos/devoluciones', { params: p })),
  tablero: (p?: any) => datos<any>(api.get('/pos/tablero', { params: p })),
  resoluciones: () => datos<any[]>(api.get('/erp/resoluciones')),
  crearResolucion: (d: any) => datos<any>(api.post('/erp/resoluciones', d)),
  editarResolucion: (id: number, d: any) => datos<any>(api.put(`/erp/resoluciones/${id}`, d)),
  notasCredito: () => datos<any[]>(api.get('/erp/notas-credito')),
}

export const pesos = (v?: number | null) =>
  v == null ? '—' : v.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })
