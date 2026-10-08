/**
 * Mapa de navegación de Daily Logistics.
 *
 * Cada módulo tiene secciones y cada sección sus pantallas. La barra superior
 * muestra los módulos; la segunda barra, las secciones del módulo activo (un
 * menú desplegable por sección).
 */

export interface ItemNav {
  etiqueta: string
  ruta: string
  /** La ruta solo se marca activa si coincide exacto (p. ej. el tablero). */
  exacta?: boolean
  /** Permiso del rol que exige esta pantalla (si no, el del módulo). */
  permiso?: string
}

export interface SeccionNav {
  titulo: string
  items: ItemNav[]
}

export interface ModuloNav {
  clave: 'wms' | 'tms' | 'pos' | 'config'
  sigla: string
  nombre: string
  /** Prefijos de ruta que pertenecen al módulo. */
  prefijos: string[]
  inicio: string
  /** Permisos del rol que dan acceso (basta uno); los administradores ven todo. */
  permisos?: string[]
  secciones: SeccionNav[]
}

export const NAVEGACION: ModuloNav[] = [
  {
    clave: 'wms', sigla: 'WMS', nombre: 'Almacén', prefijos: ['/wms'], inicio: '/wms', permisos: ['wms'],
    secciones: [
      { titulo: 'Tablero', items: [{ etiqueta: 'Tablero del almacén', ruta: '/wms', exacta: true }] },
      { titulo: 'Productos', items: [{ etiqueta: 'Maestro de productos', ruta: '/wms/productos' }] },
      { titulo: 'Entrada', items: [{ etiqueta: 'Recepción', ruta: '/wms/recepcion' }] },
      {
        titulo: 'Almacenamiento', items: [
          { etiqueta: 'Inventario', ruta: '/wms/inventario' },
          { etiqueta: 'Mapa de bodega', ruta: '/wms/mapa' },
          { etiqueta: 'Constructor de bodega', ruta: '/wms/constructor' },
          { etiqueta: 'Tareas', ruta: '/wms/tareas' },
          { etiqueta: 'Estibas', ruta: '/wms/estibas' },
          { etiqueta: 'Cubicaje', ruta: '/wms/cubicaje' },
          { etiqueta: 'Slotting', ruta: '/wms/slotting' },
          { etiqueta: 'Maquila', ruta: '/wms/maquila' },
          { etiqueta: 'Traslados', ruta: '/wms/traslados' },
        ],
      },
      {
        titulo: 'Salida', items: [
          { etiqueta: 'Picking', ruta: '/wms/picking' },
          { etiqueta: 'Olas', ruta: '/wms/olas' },
          { etiqueta: 'Empaque', ruta: '/wms/empaque' },
          { etiqueta: 'Despacho', ruta: '/wms/despacho' },
        ],
      },
      {
        titulo: 'Ventas en línea', items: [
          { etiqueta: 'Pedidos en línea', ruta: '/wms/pedidos-en-linea' },
          { etiqueta: 'Canales de venta', ruta: '/wms/canales' },
        ],
      },
      {
        titulo: 'Control', items: [
          { etiqueta: 'Indicadores', ruta: '/wms/indicadores' },
          { etiqueta: 'Facturación 3PL', ruta: '/wms/facturacion' },
          { etiqueta: 'Trazabilidad', ruta: '/wms/trazabilidad' },
          { etiqueta: 'Vencimientos', ruta: '/wms/vencimientos' },
        ],
      },
      {
        titulo: 'Configuración', items: [
          { etiqueta: 'Configuración del WMS', ruta: '/wms/config' },
          { etiqueta: 'Constructor de bodega (layout)', ruta: '/wms/constructor' },
          { etiqueta: 'Integraciones (MercadoLibre, Shopify, Rappi…)', ruta: '/wms/canales' },
        ],
      },
    ],
  },
  {
    clave: 'tms', sigla: 'TMS', nombre: 'Transporte', prefijos: ['/tms', '/fletes'], inicio: '/tms', permisos: ['tms'],
    secciones: [
      { titulo: 'Tablero', items: [{ etiqueta: 'Tablero de transporte', ruta: '/tms', exacta: true }] },
      {
        titulo: 'Operación', items: [
          { etiqueta: 'Viajes', ruta: '/tms/viajes' },
          { etiqueta: 'Planeación', ruta: '/tms/planeacion' },
          { etiqueta: 'Despachos', ruta: '/tms/despachos' },
          { etiqueta: 'Tracking', ruta: '/tms/tracking' },
        ],
      },
      {
        titulo: 'Recursos', items: [
          { etiqueta: 'Vehículos', ruta: '/tms/vehiculos' },
          { etiqueta: 'Conductores', ruta: '/tms/conductores' },
        ],
      },
      {
        titulo: 'Red logística', items: [
          { etiqueta: 'Rutas', ruta: '/tms/rutas' },
          { etiqueta: 'Torre de control', ruta: '/tms/torre-control' },
        ],
      },
      {
        titulo: 'Financiero', items: [
          { etiqueta: 'Costos', ruta: '/tms/costos' },
          { etiqueta: 'OTIF', ruta: '/tms/otif' },
          { etiqueta: 'Liquidaciones', ruta: '/tms/liquidaciones' },
        ],
      },
      {
        titulo: 'Fletes', items: [
          { etiqueta: 'Despacho de fletes', ruta: '/fletes', exacta: true },
          { etiqueta: 'Generadores de carga', ruta: '/fletes/generadores' },
          { etiqueta: 'Conductores de fletes', ruta: '/fletes/conductores' },
        ],
      },
      {
        titulo: 'Configuración', items: [
          { etiqueta: 'Documentos', ruta: '/tms/documentos' },
          { etiqueta: 'Configuración del TMS', ruta: '/tms/config' },
        ],
      },
    ],
  },
  {
    clave: 'pos', sigla: 'POS', nombre: 'Punto de venta', prefijos: ['/pos'], inicio: '/pos', permisos: ['pos'],
    secciones: [
      {
        titulo: 'Operación', items: [
          { etiqueta: 'Vender', ruta: '/pos', exacta: true },
          { etiqueta: 'Turnos de caja', ruta: '/pos/turnos' },
          { etiqueta: 'Ventas', ruta: '/pos/ventas' },
        ],
      },
      { titulo: 'Analítica', items: [{ etiqueta: 'Tablero de ventas', ruta: '/pos/tablero' }] },
      { titulo: 'Configuración', items: [{ etiqueta: 'Configuración del POS', ruta: '/pos/config' }] },
    ],
  },
  {
    clave: 'config', sigla: 'CFG', nombre: 'Configuración', prefijos: ['/configuracion', '/soporte'],
    inicio: '/configuracion', permisos: ['usuarios', 'configuracion'],
    secciones: [
      { titulo: 'Resumen', items: [{ etiqueta: 'Centro de configuración', ruta: '/configuracion', exacta: true }] },
      {
        titulo: 'Empresa', items: [
          { etiqueta: 'Datos de la empresa', ruta: '/configuracion/empresa', permiso: 'configuracion' },
          { etiqueta: 'Catálogos maestros', ruta: '/configuracion/catalogos', permiso: 'configuracion' },
        ],
      },
      {
        titulo: 'Usuarios y roles', items: [
          { etiqueta: 'Usuarios', ruta: '/configuracion/usuarios', permiso: 'usuarios' },
          { etiqueta: 'Roles y permisos', ruta: '/configuracion/roles', permiso: 'usuarios' },
        ],
      },
      {
        titulo: 'Módulos', items: [
          { etiqueta: 'Configuración del WMS', ruta: '/wms/config', permiso: 'wms' },
          { etiqueta: 'Integraciones con tiendas virtuales', ruta: '/wms/canales', permiso: 'wms' },
          { etiqueta: 'Configuración del TMS', ruta: '/tms/config', permiso: 'tms' },
          { etiqueta: 'Conductores', ruta: '/tms/conductores', permiso: 'tms' },
          { etiqueta: 'Configuración del POS', ruta: '/pos/config', permiso: 'pos' },
        ],
      },
      { titulo: 'Soporte', items: [{ etiqueta: 'Mesa de ayuda', ruta: '/soporte' }] },
    ],
  },
]

export const coincide = (ruta: string, item: ItemNav) =>
  item.exacta ? ruta === item.ruta : ruta === item.ruta || ruta.startsWith(item.ruta + '/')

export const moduloDeRuta = (ruta: string): ModuloNav | undefined =>
  NAVEGACION.find(m => m.prefijos.some(p => ruta === p || ruta.startsWith(p + '/')))

/** La pantalla activa: gana la coincidencia más específica. */
export function itemActivo(ruta: string, modulo?: ModuloNav) {
  if (!modulo) return undefined
  let mejor: { seccion: SeccionNav; item: ItemNav } | undefined
  for (const seccion of modulo.secciones) {
    for (const item of seccion.items) {
      if (coincide(ruta, item) && (!mejor || item.ruta.length > mejor.item.ruta.length)) {
        mejor = { seccion, item }
      }
    }
  }
  return mejor
}
