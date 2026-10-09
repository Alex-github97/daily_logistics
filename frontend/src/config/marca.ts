/**
 * Identidad de Daily Logistics, en un solo lugar.
 *
 * La herramienta es multicliente: el nombre y el logo de la empresa que la usa
 * salen del registro de clientes. Lo de acá es la marca del producto.
 *
 * Todas las pantallas toman sus colores de este archivo, así que cambiar la
 * paleta aquí cambia la herramienta entera.
 */
export const MARCA = {
  nombre: 'Daily Logistics',
  /** Como se escribe en el logo. */
  logotipo: 'daily logistics',
  corto: 'DAILY',
  /** Dos letras, para el distintivo cuadrado. */
  sigla: 'DL',
  lema: 'Almacén · Transporte · Punto de venta',
  descripcion: 'La operación logística de cada día, en un solo lugar.',
  get legal() {
    return `© ${new Date().getFullYear()} Daily Logistics`
  },
} as const

/** Neutros azul noche: estructura, texto y superficies. */
export const PALETA = {
  abismo: '#05070F',
  tinta: '#0B1120',
  carbon: '#1E293B',
  grafito: '#475569',
  acero: '#94A3B8',
  niebla: '#E2E8F0',
  bruma: '#F4F6FB',
  lienzo: '#FFFFFF',
} as const

/** El color de lo pulsable y lo activo. */
export const ACENTO = {
  base: '#4F46E5',
  profundo: '#3730A3',
  claro: '#22D3EE',
  vapor: '#EEF2FF',
} as const

/** Segundo color de marca: detalles, indicador de pestaña activa, logo. */
export const DESTELLO = {
  base: '#22D3EE',
  suave: '#CFFAFE',
} as const

/** Degradado de marca (índigo → violeta → cian) para barras y acentos. */
export const DEGRADADO = 'linear-gradient(90deg, #4F46E5 0%, #7C3AED 50%, #06B6D4 100%)'

/** Colores con significado: no son decoración. */
export const ESTADO = {
  exito: '#16A34A',
  alerta: '#D97706',
  peligro: '#DC2626',
  informacion: '#0EA5E9',
} as const

export const COLOR_MODULO = ACENTO.base
export const COLOR_MODULO_CLARO = ACENTO.profundo
export const COLOR_MODULO_SOBRE_OSCURO = ACENTO.claro

/** Series de las gráficas, ordenadas por contraste. */
export const SERIES = [
  '#4F46E5', // índigo
  '#06B6D4', // cian
  '#8B5CF6', // violeta
  '#0B1120', // tinta
  '#38BDF8', // celeste
  '#A78BFA', // lavanda
  '#94A3B8', // acero
  '#475569', // grafito
] as const

/** Superficies, de la más profunda a la más elevada. */
export const SUPERFICIE = {
  espacios: PALETA.abismo,
  barra: PALETA.tinta,
  divisorOscuro: 'rgba(255,255,255,0.10)',
  contenido: PALETA.bruma,
  tarjeta: PALETA.lienzo,
  divisor: PALETA.niebla,
} as const

/** Los módulos que vende Daily Logistics, con su identidad en la barra superior. */
export const MODULOS_DL = [
  { clave: 'wms', sigla: 'WMS', nombre: 'Almacén', ruta: '/wms', permiso: 'wms',
    descripcion: 'Recepción, inventario, picking y despacho.' },
  { clave: 'tms', sigla: 'TMS', nombre: 'Transporte', ruta: '/tms', permiso: 'tms',
    descripcion: 'Viajes, flota, rutas, tracking y liquidaciones.' },
  { clave: 'pos', sigla: 'POS', nombre: 'Punto de venta', ruta: '/pos', permiso: 'pos',
    descripcion: 'Venta en mostrador, turnos de caja y facturación.' },
  { clave: 'wfm', sigla: 'WFM', nombre: 'Personal', ruta: '/personal', permiso: 'wfm',
    descripcion: 'Jornadas, estaciones de trabajo, tareas de cada persona y productividad.' },
] as const
