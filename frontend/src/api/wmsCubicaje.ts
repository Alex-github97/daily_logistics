/** WMS · Cubicaje: cubicadores, mediciones, empaques, estibas y ocupación. */
import { apiClient as api } from './client'

const datos = <T,>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type Nivel = 'UNIDAD' | 'CAJA' | 'MASTER' | 'ESTIBA'
export interface Cubicador {
  id: number; codigo: string; nombre: string; almacen_id?: number | null; activo: boolean; tiene_token: boolean
  token_emitido_en?: string | null; ultima_conexion?: string | null; firmware?: string | null; tolerancia_mm: number
  notas?: string | null; base_x_mm?: number | null; base_y_mm?: number | null; base_z_mm?: number | null
  escala_x: number; escala_y: number; escala_z: number; tara_crudo?: number | null; escala_peso?: number | null
  calibrado: { x: boolean; y: boolean; z: boolean; peso: boolean }; muestras: Record<string, number>
}
export interface Medicion {
  id: number; fecha: string; largo_cm?: number | null; ancho_cm?: number | null; alto_cm?: number | null
  peso_kg?: number | null; estable: boolean; dispersion_mm?: number | null; estado: string; producto?: string | null
  nivel?: string | null; volumen_m3?: number | null
}
export interface Empaque {
  id?: number; nivel: Nivel; unidades: number; largo_cm?: number | null; ancho_cm?: number | null; alto_cm?: number | null
  peso_kg?: number | null; volumen_m3?: number | null; codigo_barras?: string | null; cajas_por_cama?: number | null
  camas?: number | null; apilable?: boolean; max_apilado?: number | null; fuente?: string; medido_en?: string | null
}
export interface ProductoCubicaje {
  id: number; sku: string; nombre: string; codigo_barras?: string | null; depositante_id?: number | null
  niveles: Nivel[]; medido: boolean; fuente?: string | null; unidad?: Empaque | null; peso_kg?: number | null
  volumen_m3?: number | null; estiba?: { ti: number; hi: number; unidades: number } | null
}
export interface Ocupacion {
  id: number; codigo: string; zona: string; zona_tipo: string; almacen_id: number; largo_cm?: number | null
  ancho_cm?: number | null; alto_cm?: number | null; capacidad_m3?: number | null; ocupado_m3: number; unidades: number
  skus: number; unidades_sin_volumen: number; ocupacion_pct?: number | null
}

export const cubicaje = {
  cubicadores: () => datos<Cubicador[]>(api.get('/wms/cubicadores')),
  crearCubicador: (d: Record<string, unknown>) => datos<Cubicador>(api.post('/wms/cubicadores', d)),
  editarCubicador: (id: number, d: Record<string, unknown>) => datos<Cubicador>(api.put(`/wms/cubicadores/${id}`, d)),
  emitirToken: (id: number) => datos<{ token: string; aviso: string }>(api.post(`/wms/cubicadores/${id}/token`)),
  reiniciarCalibracion: (id: number) => datos<Cubicador>(api.post(`/wms/cubicadores/${id}/calibracion/reiniciar`)),
  mediciones: (id: number, estado = 'PENDIENTE') => datos<Medicion[]>(api.get(`/wms/cubicadores/${id}/mediciones`, { params: { estado } })),
  asignar: (mid: number, d: { producto_id: number; nivel: Nivel; unidades?: number; codigo_barras?: string; aceptar_inestable?: boolean }) =>
    datos<Empaque>(api.post(`/wms/mediciones/${mid}/asignar`, d)),
  descartar: (mid: number) => datos<unknown>(api.post(`/wms/mediciones/${mid}/descartar`)),
  calibrar: (mid: number, d: { largo_mm?: number; ancho_mm?: number; alto_mm?: number; peso_g?: number }) =>
    datos<Cubicador>(api.post(`/wms/mediciones/${mid}/calibrar`, d)),
  empaques: (pid: number) => datos<Empaque[]>(api.get(`/wms/productos/${pid}/empaques`)),
  guardarEmpaques: (pid: number, d: Empaque[]) => datos<Empaque[]>(api.put(`/wms/productos/${pid}/empaques`, d)),
  estiba: (d: Record<string, unknown>) => datos<any>(api.post('/wms/cubicaje/estiba', d)),
  productos: (p: Record<string, unknown>) => datos<ProductoCubicaje[]>(api.get('/wms/cubicaje/productos', { params: p })),
  ocupacion: (almacen_id?: number) => datos<Ocupacion[]>(api.get('/wms/cubicaje/ubicaciones', { params: { almacen_id } })),
  resumen: (almacen_id?: number) => datos<any>(api.get('/wms/cubicaje/resumen', { params: { almacen_id } })),
}

export const NIVEL_TXT: Record<Nivel, string> = { UNIDAD: 'Unidad', CAJA: 'Caja', MASTER: 'Caja máster', ESTIBA: 'Estiba' }
export const dims = (l?: number | null, a?: number | null, h?: number | null) =>
  l && a && h ? `${l} × ${a} × ${h} cm` : '—'
