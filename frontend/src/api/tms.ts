/**
 * Las vistas de conjunto del transporte: costos, OTIF, planeación y documentos.
 *
 * Las otras pantallas de TMS arman sus URL con `apiClient` directamente; estas
 * cuatro eran maqueta y nacen con sus rutas en un solo sitio.
 */
import { apiClient } from './client'

const get = <T,>(ruta: string, params?: Record<string, unknown>) =>
  apiClient.get<T>(ruta, { params }).then(r => r.data)

export interface CostoDesglose {
  id: number
  combustible: number; peajes: number; viaticos: number
  horas_extras: number; mantenimiento: number; costos_indirectos: number
  valor_flete_cobrado: number; notas?: string | null
  /** Calculados por el servidor con la distancia actual del viaje. */
  costo_total: number; margen: number
  margen_pct: number | null; costo_por_km: number | null
}

export interface ViajeCosto {
  viaje_id: number; codigo: string; estado: string
  origen?: string | null; destino?: string | null; conductor?: string | null
  distancia_km?: number | null; num_entregas?: number | null
  valor_flete?: number | null; fecha?: string | null
  costo: CostoDesglose | null
}

export type ComponentesCosto = Pick<CostoDesglose,
  'combustible' | 'peajes' | 'viaticos' | 'horas_extras' | 'mantenimiento' | 'costos_indirectos' | 'valor_flete_cobrado'>
  & { notas?: string | null }

export interface ViajeOTIF {
  viaje_id: number; codigo: string
  cliente?: string | null; conductor?: string | null
  origen?: string | null; destino?: string | null
  fecha_programada?: string | null; fecha_real?: string | null
  horas_retraso?: number | null
  /** null = no se sabe (sin fecha programada / nadie lo confirmó). */
  on_time: boolean | null; in_full: boolean | null; otif: boolean | null
  motivo?: string | null
}

export interface ResumenOTIF {
  on_time_rate: number; in_full_rate: number; otif_rate: number
  total: number; sin_confirmar_in_full: number
}

export interface Planeacion {
  pendientes: {
    viaje_id: number; codigo: string; cliente?: string | null
    origen?: string | null; destino?: string | null
    peso_kg?: number | null; volumen_m3?: number | null
    tipo_servicio?: string | null
    fecha_cargue?: string | null; fecha_entrega?: string | null
    valor_flete?: number | null
  }[]
  vehiculos: {
    id: number; placa: string; tipo?: string | null; estado: string
    capacidad_kg?: number | null; volumen_m3?: number | null
    carga_asignada_kg: number; capacidad_libre_kg?: number | null
    carga_asignada_m3?: number; capacidad_libre_m3?: number | null
    viaje_activo?: string | null
  }[]
  conductores: {
    id: number; nombre: string; licencia?: string | null
    licencia_vence?: string | null; licencia_vencida: boolean
    viaje_activo?: string | null
  }[]
}

export interface DocumentoTMS {
  id: number; viaje_id: number; tipo_documento: string
  numero?: string | null; fecha_emision?: string | null
  archivo_url?: string | null; estado: string; observaciones?: string | null
}

export interface ViajeResumen {
  id: number; codigo: string; estado: string
  origen_ciudad?: string | null; destino_ciudad?: string | null
  conductor_nombre?: string | null; vehiculo_placa?: string | null
  fecha_programada_cargue?: string | null
}

export interface PendienteDocs {
  viaje_id: number; codigo: string; estado: string
  origen?: string | null; destino?: string | null
  fecha_programada?: string | null; faltantes: string[]
}

export interface POD {
  id: number; viaje_id: number; codigo_viaje: string
  destino?: string | null; conductor?: string | null
  receptor_nombre?: string | null; receptor_documento?: string | null
  lat?: number | null; lng?: number | null; fecha_hora?: string | null
  foto_url?: string | null; firma_url?: string | null
  observaciones?: string | null
}

export const tmsApi = {
  costos: (f?: { fecha_desde?: string; fecha_hasta?: string }) => get<ViajeCosto[]>('/tms/costos', f),
  crearCostos: (viaje_id: number, d: ComponentesCosto) =>
    apiClient.post('/tms/costos', { viaje_id, ...d }).then(r => r.data),
  editarCostos: (costo_id: number, d: ComponentesCosto) =>
    apiClient.put(`/tms/costos/${costo_id}`, d).then(r => r.data),

  otif: (f?: { fecha_desde?: string; fecha_hasta?: string }) => get<ViajeOTIF[]>('/tms/otif/viajes', f),
  resumenOtif: (f?: { fecha_desde?: string; fecha_hasta?: string }) => get<ResumenOTIF>('/tms/otif/resumen', f),
  confirmarInFull: (viaje_id: number, in_full: boolean | null, motivo?: string | null) =>
    apiClient.put(`/tms/viajes/${viaje_id}/in-full`, { in_full, motivo }).then(r => r.data),

  planeacion: () => get<Planeacion>('/tms/planeacion'),
  asignar: (d: { viaje_id: number; vehiculo_id: number; conductor_hcm_id: number }) =>
    apiClient.post('/tms/planeacion/asignar', d).then(r => r.data),

  viajes: (f?: { estado?: string; per_page?: number }) =>
    get<{ items: ViajeResumen[]; total: number }>('/tms/viajes', { per_page: 100, ...f }),
  viaje: (id: number) => get<ViajeResumen>(`/tms/viajes/${id}`),
  documentos: (viaje_id: number) => get<DocumentoTMS[]>(`/tms/viajes/${viaje_id}/documentos`),
  crearDocumento: (d: Partial<DocumentoTMS>) => apiClient.post<DocumentoTMS>('/tms/documentos', d).then(r => r.data),
  editarDocumento: (id: number, d: Partial<DocumentoTMS>) =>
    apiClient.put<DocumentoTMS>(`/tms/documentos/${id}`, d).then(r => r.data),
  borrarDocumento: (id: number) => apiClient.delete(`/tms/documentos/${id}`),
  pendientesDocs: () => get<PendienteDocs[]>('/tms/documentos/pendientes'),
  pods: () => get<POD[]>('/tms/pod'),
  crearPod: (d: Partial<POD> & { viaje_id: number }) => apiClient.post('/tms/pod', d).then(r => r.data),

  // ── Lo que se registra dentro de un viaje ──
  /** El servidor responde 404 mientras no haya prueba de entrega: aquí es «todavía no», no un error. */
  pod: (viaje_id: number) => get<POD>(`/tms/viajes/${viaje_id}/pod`)
    .catch((e: any) => (e?.response?.status === 404 ? null : Promise.reject(e))),
  paradas: (viaje_id: number) => get<ParadaTMS[]>(`/tms/viajes/${viaje_id}/paradas`),
  crearParada: (d: Partial<ParadaTMS> & { viaje_id: number }) => apiClient.post('/tms/paradas', d).then(r => r.data),
  estadoParada: (id: number, estado: string, extra?: { tiempo_real_llegada?: string; tiempo_real_salida?: string }) =>
    apiClient.put(`/tms/paradas/${id}/estado`, null, { params: { estado, ...extra } }).then(r => r.data),
  borrarParada: (id: number) => apiClient.delete(`/tms/paradas/${id}`),
  eventos: (viaje_id: number) => get<EventoTMS[]>(`/tms/viajes/${viaje_id}/eventos`),
  crearEvento: (d: Partial<EventoTMS> & { viaje_id: number; tipo_evento: string }) =>
    apiClient.post('/tms/eventos', d).then(r => r.data),
  alertas: (f?: { viaje_id?: number; leida?: boolean }) => get<AlertaTMS[]>('/tms/alertas', f),
  crearAlerta: (d: Partial<AlertaTMS> & { tipo: string; nivel: string; mensaje: string }) =>
    apiClient.post('/tms/alertas', d).then(r => r.data),
  leerAlerta: (id: number) => apiClient.put(`/tms/alertas/${id}/leer`).then(r => r.data),
}

export interface ParadaTMS {
  id: number; viaje_id: number; secuencia: number; tipo: string
  ciudad: string; direccion?: string | null; estado: string
  tiempo_estimado_llegada?: string | null; tiempo_real_llegada?: string | null
  tiempo_real_salida?: string | null
  contacto?: string | null; telefono_contacto?: string | null; observaciones?: string | null
}

export interface EventoTMS {
  id: number; viaje_id: number; parada_id?: number | null
  tipo_evento: string; descripcion?: string | null
  lat?: number | null; lng?: number | null; velocidad_kmh?: number | null
  timestamp?: string | null; created_at?: string | null
}

export interface AlertaTMS {
  id: number; tipo: string; nivel: string; mensaje: string
  viaje_id?: number | null; vehiculo_id?: number | null
  leida: boolean; fecha_alerta?: string | null
}
