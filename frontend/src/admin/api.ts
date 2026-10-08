/**
 * La API de la consola del operador.
 *
 * Habla solo con `/plataforma/*`, que es lo que administra el acceso de las
 * empresas. Deliberadamente no toca ningún endpoint operativo: la consola
 * administra quién entra, no qué hay dentro.
 */
import axios from 'axios'

export interface Empresa {
  id: number
  codigo: string
  nombre: string
  esquema: string
  nit?: string | null
  logo_url?: string | null
  color?: string | null
  activo: boolean
  es_operador: boolean
  suspendido_desde?: string | null
  usuarios: number
  usuarios_activos: number
}

export interface UsuarioDeEmpresa {
  id: number
  nombre: string
  apellido: string
  email: string
  username: string
  rol: string
  cargo?: string | null
  activo: boolean
  bloqueado?: boolean | null
  ultimo_login?: string | null
}

/** Una casilla que puede marcarse en un perfil. La lista la sirve el servidor:
 *  tenerla escrita acá fue lo que la dejó desincronizada con la del portal. */
export interface PermisoDePerfil {
  clave: string
  nombre: string
  grupo: string
}

export interface PerfilDeEmpresa {
  id: number
  nombre: string
  label?: string | null
  descripcion?: string | null
  color?: string | null
  permisos: Record<string, boolean>
  /** Los que trae toda empresa de fábrica: se pueden ajustar pero no eliminar. */
  es_sistema: boolean
  total_usuarios: number
}

export interface ClaveEntregada {
  username: string
  clave_temporal: string
}

export interface AsientoBitacora {
  id: number
  fecha: string
  actor: string
  actor_empresa: string
  accion: string
  empresa_codigo?: string | null
  detalle?: string | null
}


// ─── La relación comercial ────────────────────────────────────────────────────

export interface Contrato {
  tarifa_mensual: string
  moneda: string
  iva_pct: string
  dia_corte: number
  inicio?: string | null
  fin?: string | null
  notas?: string | null
}

export interface ModuloContratado {
  clave: string
  nombre: string
  activo: boolean
  /** Los esenciales no se pueden quitar: sin ellos nadie entra. */
  esencial: boolean
}

export interface Contacto {
  id?: number
  nombre: string
  cargo?: string | null
  email?: string | null
  telefono?: string | null
  principal: boolean
  notas?: string | null
}

export interface Documento {
  id?: number
  tipo?: string | null
  nombre: string
  archivo?: string | null
  vence?: string | null
  notas?: string | null
}

export interface Pago {
  id?: number
  /** A qué factura se aplica; vacío = anticipo sin factura todavía. */
  factura_id?: number | null
  fecha: string
  monto: string
  moneda: string
  periodo_desde?: string | null
  periodo_hasta?: string | null
  metodo?: string | null
  referencia?: string | null
  notas?: string | null
}

export interface Cartera {
  tarifa_mensual: string
  moneda: string
  iva_pct: string
  total_con_iva: string
  pagado_total: string
  cubierto_hasta?: string | null
  dias_en_mora: number
  al_dia: boolean
  /** Sin ningún pago con periodo no se puede afirmar nada sobre la mora. */
  hay_datos: boolean
}

export interface Uso {
  usuarios: number
  usuarios_activos: number
  ultimo_ingreso?: string | null
  activos_30d: number
  conteos: Record<string, number>
}


// ─── Facturación y contabilidad ───────────────────────────────────────────────
//
// Control contable interno: NO es facturación electrónica ante la DIAN. El
// número legal se guarda en `numero_externo` para poder cruzar las dos cosas.

export interface Factura {
  id: number
  numero: string
  numero_externo?: string | null
  fecha: string
  periodo_desde?: string | null
  periodo_hasta?: string | null
  subtotal: string
  iva_pct: string
  iva_valor: string
  total: string
  moneda: string
  anulada: boolean
  concepto?: string | null
  notas?: string | null
  acreditado: string
  pagado: string
  saldo: string
}

export interface NotaCredito {
  id?: number
  factura_id: number
  numero?: string
  numero_externo?: string | null
  fecha?: string | null
  valor: string
  moneda?: string
  motivo: string
  notas?: string | null
}

export interface FilaCliente {
  cliente_id: number
  codigo: string
  nombre: string
  activo: boolean
  tarifa_mensual: string
  facturado: string
  acreditado: string
  recaudado: string
  saldo: string
  facturas: number
  dias_mora: number
}

export interface FilaMes {
  mes: string
  facturado: string
  acreditado: string
  recaudado: string
}

export interface Contabilidad {
  facturado: string
  acreditado: string
  recaudado: string
  por_cobrar: string
  ingreso_recurrente: string
  empresas_activas: number
  empresas_en_mora: number
  clientes: FilaCliente[]
  meses: FilaMes[]
}


// ─── Mesa de ayuda ────────────────────────────────────────────────────────────

export interface Adjunto {
  id: number
  nombre: string
  tipo_mime?: string | null
  tamano?: number | null
  creado_en: string
  mensaje_id?: number | null
}

export interface MensajeSoporte {
  id: number
  autor: string
  autor_nombre?: string | null
  es_soporte: boolean
  cuerpo: string
  /** Nota del equipo: el cliente no la ve. */
  interno: boolean
  creado_en: string
  adjuntos: Adjunto[]
}

export interface Ticket {
  id: number
  numero: string
  asunto: string
  estado: string
  criticidad: string
  categoria?: string | null
  modulo?: string | null
  impacto?: string | null
  autor: string
  autor_nombre?: string | null
  cliente_codigo: string
  asignado_a?: string | null
  created_at?: string | null
  ultima_actividad?: string | null
  primera_respuesta_en?: string | null
  mensajes: number
  conversacion?: MensajeSoporte[]
}

export interface ResumenSoporte {
  abiertos: number
  sin_responder: number
  criticos: number
  por_estado: Record<string, number>
  por_criticidad: Record<string, number>
}


// ─── Gestión ágil ─────────────────────────────────────────────────────────────

export interface Tarjeta {
  id: number
  numero: string
  asunto: string
  estado: string
  criticidad: string
  tipo_trabajo?: string | null
  puntos?: number | null
  sprint_id?: number | null
  epica_id?: number | null
  orden?: number | null
  etiquetas?: string[] | null
  asignado_a?: string | null
  cliente_codigo: string
  autor: string
  modulo?: string | null
  created_at?: string | null
  ultima_actividad?: string | null
}

export interface ColumnaTablero {
  estado: string
  titulo: string
  orden: number
  /** Vacío = sin límite. Cuando se alcanza, el servidor rechaza el movimiento. */
  limite_wip?: number | null
  cantidad: number
  puntos: number
  tarjetas: Tarjeta[]
}

export interface Tablero {
  sprint?: {
    id: number; nombre: string; objetivo?: string | null
    inicio?: string | null; fin?: string | null; estado: string
  } | null
  columnas: ColumnaTablero[]
}

export interface SprintAgil {
  id?: number
  nombre: string
  objetivo?: string | null
  inicio?: string | null
  fin?: string | null
  estado: string
  puntos_comprometidos?: number | null
  puntos_completados?: number | null
  cerrado_en?: string | null
  total_solicitudes: number
  puntos_en_curso: number
  puntos_hechos: number
}

export interface EpicaAgil {
  id?: number
  nombre: string
  descripcion?: string | null
  color?: string | null
  archivada: boolean
  solicitudes: number
  puntos: number
}

export interface MetricasAgiles {
  burndown: { fecha: string; ideal: number; real?: number | null }[]
  velocidad: { sprint: string; comprometidos: number; completados: number }[]
  tiempo_ciclo_promedio?: number | null
  tiempo_entrega_promedio?: number | null
  por_tipo: Record<string, number>
}


// ─── Gestión de proyectos e incidencias ───────────────────────────────────────
//
// Es distinto de la mesa de ayuda, y a propósito: el ticket guarda lo que
// escribió el cliente y su asunto no se toca nunca; la incidencia es el trabajo
// que decidimos hacer y su título se reescribe a medida que se entiende mejor el
// pedido. Por eso son dos cosas unidas por un vínculo y no una sola.

export interface Proyecto {
  id: number
  clave: string
  nombre: string
  descripcion?: string | null
  icono?: string | null
  color?: string | null
  lider?: string | null
  workflow_id?: number | null
  restringido: boolean
  incidencia_automatica: boolean
  archivado: boolean
  abiertas: number
  total: number
  mi_rol?: string | null
}

export interface Incidencia {
  id: number
  clave: string
  proyecto_id: number
  resumen: string
  tipo?: string | null
  tipo_id?: number | null
  icono?: string | null
  estado?: string | null
  estado_id?: number | null
  categoria?: string | null
  color_estado?: string | null
  prioridad?: string | null
  prioridad_id?: number | null
  color_prioridad?: string | null
  asignado?: string | null
  reporta?: string | null
  puntos?: number | null
  padre_id?: number | null
  sprint_id?: number | null
  etiquetas: string[]
  campos: Record<string, any>
  vence?: string | null
  actualizado?: string | null
  ticket_id?: number | null
}

export interface PaginaIncidencias {
  resultados: Incidencia[]
  /** Vacío = no hay más. Se pagina por cursor, no por número de página. */
  siguiente?: string | null
  total?: number | null
  orden?: { campo: string; ascendente: boolean } | null
}

/** Una transición del flujo, ya evaluada para quien mira.
 *  Las que no pasan las condiciones ni se devuelven; las que fallan una
 *  validación llegan con `lista: false` y el motivo, porque esconder un botón
 *  sin decir por qué se lee como que la herramienta está rota. */
export interface TransicionDisponible {
  id: number
  nombre: string
  destino_id: number
  destino: string
  categoria: string
  color?: string | null
  lista: boolean
  impedimentos: string[]
}

export interface OpcionCampo {
  valor: string
  etiqueta: string
  color?: string | null
}

export interface DefinicionCampo {
  clave: string
  nombre: string
  descripcion?: string | null
  ayuda?: string | null
  tipo: string
  obligatorio: boolean
  solo_lectura: boolean
  validacion: Record<string, any>
  valor_defecto?: any
  filtrable: boolean
  orden: number
  opciones: OpcionCampo[]
}

export interface ComentarioGestion {
  id: number
  autor: string
  cuerpo: string
  interno: boolean
  editado: boolean
  created_at?: string | null
}

export interface AdjuntoGestion {
  id: number
  nombre: string
  tipo_mime?: string | null
  tamano?: number | null
  subido_por?: string | null
  creado?: string | null
}

export interface AsientoHistorial {
  campo: string
  anterior?: string | null
  nuevo?: string | null
  autor?: string | null
  creado?: string | null
}

export interface DetalleIncidencia {
  incidencia: Incidencia
  descripcion?: string | null
  /** De qué nivel es: EPICA, NORMAL o SUBTAREA. Decide qué puede colgar de ella. */
  nivel?: string | null
  /** Cuándo se PLANEA empezarla. Con `vence` forma la barra del Gantt; es
   *  distinto de `iniciado`, que es cuándo empezó de verdad. */
  inicio_plan?: string | null
  iniciado?: string | null
  resuelto?: string | null
  creado?: string | null
  proyecto: { id: number; clave: string; nombre: string }
  definicion_campos: DefinicionCampo[]
  transiciones: TransicionDisponible[]
  comentarios: ComentarioGestion[]
  adjuntos: AdjuntoGestion[]
  historial: AsientoHistorial[]
  subtareas: Incidencia[]
  vinculos: { id: number; tipo: string; sentido: string; otra?: Incidencia | null }[]
}

export interface EstadoFlujo {
  id: number
  clave: string
  nombre: string
  categoria: string
  color?: string | null
  orden: number
  inicial: boolean
  limite_wip?: number | null
}

export interface ConfiguracionGestion {
  tipos: {
    id: number; clave: string; nombre: string; icono?: string | null
    color?: string | null; nivel: string; workflow_id?: number | null
    proyecto_id?: number | null
  }[]
  prioridades: {
    id: number; clave: string; nombre: string; color?: string | null
    orden: number; por_defecto: boolean
  }[]
  workflows: {
    id: number; nombre: string; descripcion?: string | null
    por_defecto: boolean; estados: EstadoFlujo[]
  }[]
  campos: DefinicionCampo[]
  vocabulario: Record<string, string[]>
  reglas: Record<string, { clave: string; nombre: string; config: any }[]>
}

/** Un campo tal como puede nombrarse en un filtro. La lista la sirve el
 *  servidor: si la pantalla tuviera la suya, ofrecería campos que el servidor
 *  rechaza y quien los use concluiría que el filtro está roto. */
export interface CampoConsultable {
  clave: string
  etiqueta: string
  tipo: string
  ordenable: boolean
  personalizado: boolean
  operadores: string[]
}

export interface CatalogoConsultas {
  campos: CampoConsultable[]
  funciones: { nombre: string; descripcion: string }[]
  topes: Record<string, number>
}

export interface FiltroGuardado {
  id: number
  nombre: string
  descripcion?: string | null
  expresion: string
  columnas: string[]
  orden_por?: string | null
  orden_asc: boolean
  autor: string
  compartido: boolean
}

export const gestionApi = {
  proyectos: (incluirArchivados = false) =>
    api.get<Proyecto[]>('/gestion/proyectos', {
      params: { incluir_archivados: incluirArchivados },
    }).then(r => r.data),

  crearProyecto: (cuerpo: Record<string, unknown>) =>
    api.post<Proyecto>('/gestion/proyectos', cuerpo).then(r => r.data),

  /** La clave que el servidor usaría para ese nombre. Se consulta mientras se
   *  escribe, para que quien crea el proyecto vea el prefijo de sus incidencias
   *  antes de confirmar. */
  claveSugerida: (nombre: string) =>
    api.get<{ clave: string }>('/gestion/proyectos/clave-sugerida',
      { params: { nombre } }).then(r => r.data.clave),

  eliminarProyecto: (id: number, forzar = false) =>
    api.delete(`/gestion/proyectos/${id}`, { params: { forzar } }),

  editarProyecto: (id: number, cambios: Record<string, unknown>) =>
    api.put<Proyecto>(`/gestion/proyectos/${id}`, cambios).then(r => r.data),

  /** A quién se le puede asignar trabajo. Sale del equipo de la consola y no de
   *  un campo de texto: con texto libre, «juan» y «Juan» son dos responsables
   *  distintos y la carga por persona se reparte en dos. */
  personas: () =>
    api.get<Persona[]>('/gestion/personas').then(r => r.data),

  /** De qué puede colgar una incidencia de ese nivel. La regla de jerarquía es
   *  del servidor: una lista armada acá ofrecería padres que rechaza al guardar. */
  padresPosibles: (proyectoId: number, nivel: string) =>
    api.get<PadrePosible[]>(`/gestion/proyectos/${proyectoId}/padres`,
      { params: { nivel } }).then(r => r.data),

  /** Las etiquetas que ya se usan, para proponerlas. Sin esto cada quien inventa
   *  la suya —«regresion», «regresión», «regr»— y dejan de agrupar nada. */
  etiquetas: (proyectoId?: number) =>
    api.get<{ etiqueta: string; usos: number }[]>('/gestion/etiquetas',
      { params: { proyecto_id: proyectoId } }).then(r => r.data),

  /** El esquema del formulario para un proyecto y un tipo. Se vuelve a pedir
   *  cuando cambie cualquiera de los dos. */
  formulario: (params: Record<string, unknown>) =>
    api.get<EsquemaFormulario>('/gestion/formulario', { params }).then(r => r.data),

  vocabularioCampos: () =>
    api.get<{
      tipos: { clave: string; entidad?: string | null; multiple: boolean }[]
      secciones: { clave: string; titulo: string }[]
      entidades: string[]
      defectos: { clave: string; nombre: string }[]
    }>('/gestion/formulario/vocabulario').then(r => r.data),

  versiones: (proyectoId: number) =>
    api.get<VersionProyecto[]>(`/gestion/proyectos/${proyectoId}/versiones`)
      .then(r => r.data),
  crearVersion: (proyectoId: number, cuerpo: Record<string, unknown>) =>
    api.post<VersionProyecto>(`/gestion/proyectos/${proyectoId}/versiones`, cuerpo)
      .then(r => r.data),
  archivarVersion: (id: number) => api.delete(`/gestion/versiones/${id}`),

  componentes: (proyectoId: number) =>
    api.get<ComponenteProyecto[]>(`/gestion/proyectos/${proyectoId}/componentes`)
      .then(r => r.data),
  crearComponente: (proyectoId: number, cuerpo: Record<string, unknown>) =>
    api.post<ComponenteProyecto>(`/gestion/proyectos/${proyectoId}/componentes`, cuerpo)
      .then(r => r.data),
  archivarComponente: (id: number) => api.delete(`/gestion/componentes/${id}`),

  tiposVinculo: () =>
    api.get<TipoDeVinculo[]>('/gestion/tipos-vinculo').then(r => r.data),

  configuracion: (proyectoId?: number) =>
    api.get<ConfiguracionGestion>('/gestion/configuracion', {
      params: { proyecto_id: proyectoId },
    }).then(r => r.data),

  // ─── Incidencias ────────────────────────────────────────────────────────────

  listar: (filtros: Record<string, unknown>) =>
    api.get<PaginaIncidencias>('/gestion/incidencias', { params: filtros })
      .then(r => r.data),

  detalle: (id: number) =>
    api.get<DetalleIncidencia>(`/gestion/incidencias/${id}`).then(r => r.data),

  crear: (cuerpo: Record<string, unknown>) =>
    api.post<Incidencia>('/gestion/incidencias', cuerpo).then(r => r.data),

  editar: (id: number, cambios: Record<string, unknown>) =>
    api.put<Incidencia>(`/gestion/incidencias/${id}`, cambios).then(r => r.data),

  transicionar: (id: number, transicionId: number, comentario?: string) =>
    api.post<{ incidencia: Incidencia; transiciones: TransicionDisponible[] }>(
      `/gestion/incidencias/${id}/transicion`,
      { transicion_id: transicionId, comentario: comentario || null },
    ).then(r => r.data),

  comentar: (id: number, cuerpo: string, interno: boolean) =>
    api.post<ComentarioGestion>(`/gestion/incidencias/${id}/comentarios`,
      { cuerpo, interno, menciones: [] }).then(r => r.data),

  adjuntar: (id: number, cuerpo: FormData) =>
    api.post<AdjuntoGestion[]>(`/gestion/incidencias/${id}/adjuntos`, cuerpo)
      .then(r => r.data),

  descargarAdjunto: (id: number) =>
    api.get(`/gestion/adjuntos/${id}`, { responseType: 'blob' })
      .then(r => r.data as Blob),

  borrarAdjunto: (id: number) => api.delete(`/gestion/adjuntos/${id}`),

  /** Todos los estados del flujo, para poder saltar a cualquiera. */
  estadosDelFlujo: (id: number) =>
    api.get(`/gestion/incidencias/${id}/estados`).then(r => r.data),

  moverAEstado: (id: number, estado_id: number, comentario?: string) =>
    api.post(`/gestion/incidencias/${id}/estado`, { estado_id, comentario })
      .then(r => r.data),

  // ── El reloj de trabajo ──
  tiempo: (id: number) =>
    api.get(`/gestion/incidencias/${id}/tiempo`).then(r => r.data),
  iniciarTiempo: (id: number) =>
    api.post(`/gestion/incidencias/${id}/tiempo/iniciar`).then(r => r.data),
  pausarTiempo: (id: number, nota?: string) =>
    api.post(`/gestion/incidencias/${id}/tiempo/pausar`, { nota }).then(r => r.data),
  finalizarTiempo: (id: number, nota?: string) =>
    api.post(`/gestion/incidencias/${id}/tiempo/finalizar`, { nota }).then(r => r.data),

  desdeTicket: (ticketId: number) =>
    api.post<Incidencia>(`/gestion/tickets/${ticketId}/incidencia`).then(r => r.data),

  // ─── El lenguaje de filtros ─────────────────────────────────────────────────

  buscar: (cuerpo: Record<string, unknown>) =>
    api.post<PaginaIncidencias>('/gestion/incidencias/buscar', cuerpo).then(r => r.data),

  /** Comprueba una expresión sin ejecutarla, para marcar el error mientras se
   *  escribe en vez de devolver una lista vacía sin explicación. */
  validar: (expresion: string) =>
    api.post<{ valido: boolean; mensaje?: string | null; posicion?: number | null }>(
      '/gestion/incidencias/validar', { expresion }).then(r => r.data),

  camposConsultables: () =>
    api.get<CatalogoConsultas>('/gestion/consultas/campos').then(r => r.data),

  filtros: () => api.get<FiltroGuardado[]>('/gestion/filtros').then(r => r.data),
  guardarFiltro: (cuerpo: Record<string, unknown>) =>
    api.post<FiltroGuardado>('/gestion/filtros', cuerpo).then(r => r.data),
  borrarFiltro: (id: number) => api.delete(`/gestion/filtros/${id}`),

  // ─── Sprints y backlog ──────────────────────────────────────────────────────

  sprints: (proyectoId: number) =>
    api.get<Sprint[]>(`/gestion/proyectos/${proyectoId}/sprints`).then(r => r.data),
  crearSprint: (proyectoId: number, cuerpo: Record<string, unknown>) =>
    api.post<Sprint>(`/gestion/proyectos/${proyectoId}/sprints`, cuerpo).then(r => r.data),
  activarSprint: (id: number) =>
    api.post<Sprint>(`/gestion/sprints/${id}/activar`).then(r => r.data),
  cerrarSprint: (id: number) =>
    api.post<Sprint>(`/gestion/sprints/${id}/cerrar`).then(r => r.data),

  backlog: (proyectoId: number) =>
    api.get<BacklogResponse>(`/gestion/proyectos/${proyectoId}/backlog`).then(r => r.data),
  moverAlSprint: (ids: number[], sprintId: number | null) =>
    api.put('/gestion/backlog/sprint', { ids, sprint_id: sprintId }).then(r => r.data),
  reordenarBacklog: (ids: number[]) =>
    api.put('/gestion/backlog/orden', { ids }).then(r => r.data),

  // ─── Gantt y métricas ───────────────────────────────────────────────────────

  gantt: (proyectoId: number, params: Record<string, unknown> = {}) =>
    api.get<GanttDatos>(`/gestion/proyectos/${proyectoId}/gantt`, { params })
      .then(r => r.data),
  fijarPlan: (id: number, inicio: string | null, vence: string | null) =>
    api.put(`/gestion/incidencias/${id}/plan`,
      { inicio_plan: inicio, vence }).then(r => r.data),

  metricas: (proyectoId: number) =>
    api.get<Metricas>(`/gestion/proyectos/${proyectoId}/metricas`).then(r => r.data),

  // ─── Pizarras ───────────────────────────────────────────────────────────────

  pizarras: () => api.get<Pizarra[]>('/gestion/pizarras').then(r => r.data),
  crearPizarra: (cuerpo: Record<string, unknown>) =>
    api.post<Pizarra>('/gestion/pizarras', cuerpo).then(r => r.data),
  borrarPizarra: (id: number) => api.delete(`/gestion/pizarras/${id}`),
  catalogoWidgets: () =>
    api.get<{ tipos: { clave: string; nombre: string; descripcion: string }[]
              agrupaciones: string[] }>('/gestion/pizarras/catalogo').then(r => r.data),
  agregarWidget: (pizarraId: number, cuerpo: Record<string, unknown>) =>
    api.post<Widget>(`/gestion/pizarras/${pizarraId}/widgets`, cuerpo).then(r => r.data),
  quitarWidget: (id: number) => api.delete(`/gestion/widgets/${id}`),
  datosWidget: (id: number) =>
    api.get<DatosWidget>(`/gestion/widgets/${id}/datos`).then(r => r.data),

  // ─── Configuración ──────────────────────────────────────────────────────────

  crearWorkflow: (cuerpo: Record<string, unknown>) =>
    api.post<{ id: number; nombre: string }>('/gestion/config/workflows', cuerpo)
      .then(r => r.data),
  crearEstado: (workflowId: number, cuerpo: Record<string, unknown>) =>
    api.post(`/gestion/config/workflows/${workflowId}/estados`, cuerpo).then(r => r.data),
  editarEstado: (id: number, cuerpo: Record<string, unknown>) =>
    api.put(`/gestion/config/estados/${id}`, cuerpo).then(r => r.data),
  borrarEstado: (id: number) => api.delete(`/gestion/config/estados/${id}`),
  crearTransicion: (workflowId: number, cuerpo: Record<string, unknown>) =>
    api.post(`/gestion/config/workflows/${workflowId}/transiciones`, cuerpo).then(r => r.data),
  borrarTransicion: (id: number) => api.delete(`/gestion/config/transiciones/${id}`),

  crearTipo: (cuerpo: Record<string, unknown>) =>
    api.post('/gestion/config/tipos', cuerpo).then(r => r.data),
  editarTipo: (id: number, cuerpo: Record<string, unknown>) =>
    api.put(`/gestion/config/tipos/${id}`, cuerpo).then(r => r.data),
  archivarTipo: (id: number) => api.delete(`/gestion/config/tipos/${id}`),
  crearPrioridad: (cuerpo: Record<string, unknown>) =>
    api.post('/gestion/config/prioridades', cuerpo).then(r => r.data),

  crearCampo: (cuerpo: Record<string, unknown>) =>
    api.post<{ id: number; clave: string; nombre: string }>('/gestion/config/campos', cuerpo)
      .then(r => r.data),
  editarCampo: (id: number, cuerpo: Record<string, unknown>) =>
    api.put(`/gestion/config/campos/${id}`, cuerpo).then(r => r.data),
  archivarCampo: (id: number) => api.delete(`/gestion/config/campos/${id}`),
}

/** Una opción de un campo de selección. Viene resuelta del servidor, venga de un
 *  catálogo propio o de una entidad. */
export interface OpcionDeCampo {
  valor: string
  etiqueta: string
  pista?: string | null
  color?: string | null
}

/** Un campo tal como aplica a un proyecto y un tipo concretos.
 *
 *  La pantalla no sabe qué campos existen: recorre esto y dibuja. Es lo que hace
 *  que agregar un campo, moverlo de sección o marcarlo obligatorio no toque el
 *  frontend. */
export interface CampoDeFormulario {
  clave: string
  nombre: string
  descripcion?: string | null
  ayuda?: string | null
  tipo: string
  multiple: boolean
  obligatorio: boolean
  solo_lectura: boolean
  del_sistema: boolean
  validacion: Record<string, any>
  opciones: OpcionDeCampo[]
  /** De qué otra cosa dependen sus opciones. Cuando cambia eso, se vuelve a
   *  pedir el esquema y se limpia lo que haya quedado apuntando a otro sitio. */
  depende_de?: string | null
  /** Lo guardado, al editar. */
  valor?: any
  /** Lo que se propone al crear. Las señales —@yo, @sprint_activo— las resuelve
   *  el servidor: el navegador no sabe cuál es el sprint activo. */
  defecto?: any
}

export interface SeccionDeFormulario {
  clave: string
  titulo: string
  campos: CampoDeFormulario[]
}

export interface EsquemaFormulario {
  proyecto_id?: number | null
  tipo_id?: number | null
  secciones: SeccionDeFormulario[]
}

export interface VersionProyecto {
  id: number
  proyecto_id: number
  nombre: string
  descripcion?: string | null
  fecha?: string | null
  liberada: boolean
  archivada: boolean
  orden: number
  incidencias: number
}

export interface ComponenteProyecto {
  id: number
  proyecto_id: number
  nombre: string
  descripcion?: string | null
  responsable?: string | null
  color?: string | null
  archivado: boolean
  orden: number
}

/** Cómo se pueden relacionar dos incidencias. El nombre inverso es lo que
 *  permite leer el vínculo desde el otro lado sin guardarlo dos veces. */
export interface TipoDeVinculo {
  clave: string
  nombre: string
  inverso: string
}

export interface Persona {
  usuario: string
  nombre: string
  rol: string
  soy_yo: boolean
}

export interface PadrePosible {
  id: number
  clave: string
  resumen: string
}

export interface Sprint {
  id: number
  proyecto_id: number
  nombre: string
  objetivo?: string | null
  inicio?: string | null
  fin?: string | null
  estado: string
  /** Se sella al ARRANCAR: calculado al cerrar incluiría lo que se metió a
   *  mitad de camino y el sprint siempre parecería bien planeado. */
  puntos_comprometidos?: number | null
  /** Se congela al cerrar: si se recalculara, reestimar algo viejo cambiaría
   *  la historia. */
  puntos_completados?: number | null
  cerrado_en?: string | null
  total: number
  puntos_totales: number
  puntos_hechos: number
  sin_estimar: number
}

export interface BacklogResponse {
  sprint?: Sprint | null
  en_sprint: Incidencia[]
  backlog: Incidencia[]
}

export interface BarraGantt {
  id: number
  clave: string
  resumen: string
  tipo?: string | null
  icono?: string | null
  estado?: string | null
  categoria?: string | null
  color?: string | null
  asignado?: string | null
  puntos?: number | null
  nivel: string
  padre_id?: number | null
  /** El plan */
  inicio_plan?: string | null
  vence?: string | null
  /** Lo que de verdad pasó */
  iniciado?: string | null
  resuelto?: string | null
  bloquea_a: number[]
  /** Quién la está frenando. Se calcula en el servidor y no invirtiendo el mapa
   *  acá: invertirlo obliga a tener cargadas TODAS las barras, cosa que deja de
   *  ser cierta en cuanto se filtra por sprint. */
  depende_de: number[]
  /** De 0 a 1. En una tarea con hijas es la fracción terminada; en una hoja,
   *  todo o nada. No se inventa un punto medio para lo que está en curso. */
  avance: number
  hijas: number
}

export interface GanttDatos {
  desde?: string | null
  hasta?: string | null
  barras: BarraGantt[]
  /** Las que no tienen ninguna fecha. Se listan aparte en vez de esconderlas:
   *  desaparecer de la pantalla se lee como que se perdieron. */
  sin_fechas: Incidencia[]
}

export interface Metricas {
  velocidad: { sprint: string; comprometidos: number; completados: number }[]
  burndown: { fecha: string; ideal: number; real?: number | null }[]
  burndown_nota?: string | null
  sprint_activo?: Sprint | null
  tiempo_ciclo_dias?: number | null
  por_tipo: Record<string, number>
  por_categoria: Record<string, number>
  carga: { usuario: string; abiertas: number; puntos: number }[]
}

export interface Widget {
  id: number
  pizarra_id: number
  tipo: string
  titulo: string
  expresion: string
  agrupar_por?: string | null
  config: Record<string, any>
  x: number
  y: number
  ancho: number
  alto: number
}

export interface Pizarra {
  id: number
  nombre: string
  descripcion?: string | null
  proyecto_id?: number | null
  autor: string
  compartida: boolean
  widgets: Widget[]
}

export interface DatosWidget {
  tipo: string
  valor?: number
  puntos?: number
  filas?: Incidencia[]
  agrupar_por?: string | null
  grupos?: { etiqueta: string; cuantas: number; puntos: number }[]
  personas?: { usuario: string; cuantas: number; puntos: number }[]
}


// ─── Equipo de la consola ─────────────────────────────────────────────────────

export interface MiembroEquipo {
  id: number
  usuario: string
  nombre?: string | null
  email?: string | null
  rol: string
  activo: boolean
  notas?: string | null
}

export interface RolConsola {
  clave: string
  nombre: string
  descripcion: string
  permisos: string[]
}

export interface Candidato {
  username: string
  nombre: string
  email?: string | null
  ya_es_miembro: boolean
}

export interface QuienSoy {
  usuario: string
  rol: string
  permisos: string[]
  /** True mientras el equipo no se haya formalizado. */
  implicito: boolean
}


// ─── Página pública ───────────────────────────────────────────────────────────

export interface EstadoLanding {
  contenido: Record<string, any>
  actualizado_en?: string | null
  actualizado_por?: string | null
}

const api = axios.create({ baseURL: '/api/v1' })

const CLAVE_SESION = 'dl_admin_sesion'

export interface Sesion {
  token: string
  usuario: string
  empresa: string
}

export const sesion = {
  leer(): Sesion | null {
    try {
      const cru = localStorage.getItem(CLAVE_SESION)
      return cru ? JSON.parse(cru) : null
    } catch {
      // Un navegador con el almacenamiento bloqueado no debe romper la consola:
      // simplemente no hay sesión guardada y se vuelve a pedir el ingreso.
      return null
    }
  },
  guardar(s: Sesion) {
    try { localStorage.setItem(CLAVE_SESION, JSON.stringify(s)) } catch { /* sin persistencia */ }
  },
  cerrar() {
    try { localStorage.removeItem(CLAVE_SESION) } catch { /* nada que borrar */ }
  },
}

api.interceptors.request.use(cfg => {
  const s = sesion.leer()
  if (s) cfg.headers.Authorization = `Bearer ${s.token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  e => {
    // 401 es sesión vencida; 403 es «esta empresa no opera la plataforma», que
    // no se arregla volviendo a entrar y por eso no cierra la sesión.
    if (e?.response?.status === 401) {
      // Sin sesión abierta el 401 es una clave equivocada en el ingreso: se
      // deja pasar para que la pantalla muestre el error.
      if (sesion.leer()) {
        sesion.cerrar()
        location.reload()
      }
    }
    return Promise.reject(e)
  },
)

// El traductor es el mismo de la aplicación: se reexporta para no volver a
// escribirlo. La copia que había acá solo tomaba el PRIMER mensaje de una
// validación y no sabía qué decir ante un 500 ni ante la falta de respuesta,
// que en una consola de administración es justo cuando hace falta distinguir si
// el problema es del servidor o de lo que uno escribió.
export { mensajeDeError } from '@/utils/errorApi'

export const consolaApi = {
  /** Lo que se rompió en los navegadores, agrupado por mensaje. */
  fallos: (dias = 30, incluirAtendidos = false) =>
    api.get('/plataforma/fallos', {
      params: { dias, incluir_atendidos: incluirAtendidos },
    }).then(r => r.data),

  falloAIncidencia: (cuerpo: {
    firma: string; resumen?: string; proyecto_id?: number
  }) => api.post('/plataforma/fallos/incidencia', cuerpo).then(r => r.data),

  async ingresar(empresa: string, usuario: string, clave: string): Promise<Sesion> {
    const { data } = await axios.post('/api/v1/auth/login',
      { username: usuario, password: clave },
      { headers: { 'X-Cliente': empresa } })
    if (!data.es_operador) {
      throw new Error(
        'Esa empresa no opera la plataforma. Esta consola es solo para quien la administra.')
    }
    return { token: data.access_token, usuario, empresa }
  },

  empresas: () => api.get<Empresa[]>('/plataforma/empresas').then(r => r.data),

  crearEmpresa: (cuerpo: Record<string, unknown>) =>
    api.post<{ empresa: Empresa; acceso: ClaveEntregada }>('/plataforma/empresas', cuerpo)
      .then(r => r.data),

  editarEmpresa: (id: number, cuerpo: Record<string, unknown>) =>
    api.put<Empresa>(`/plataforma/empresas/${id}`, cuerpo).then(r => r.data),

  cambiarEstado: (id: number, activo: boolean) =>
    api.put<Empresa>(`/plataforma/empresas/${id}/estado`, null, { params: { activo } })
      .then(r => r.data),

  usuarios: (id: number) =>
    api.get<UsuarioDeEmpresa[]>(`/plataforma/empresas/${id}/usuarios`).then(r => r.data),

  crearUsuario: (id: number, cuerpo: Record<string, unknown>) =>
    api.post<ClaveEntregada>(`/plataforma/empresas/${id}/usuarios`, cuerpo).then(r => r.data),

  editarUsuario: (id: number, usuarioId: number, cuerpo: Record<string, unknown>) =>
    api.put<UsuarioDeEmpresa>(`/plataforma/empresas/${id}/usuarios/${usuarioId}`, cuerpo)
      .then(r => r.data),

  restablecerClave: (id: number, usuarioId: number) =>
    api.post<ClaveEntregada>(`/plataforma/empresas/${id}/usuarios/${usuarioId}/clave`)
      .then(r => r.data),

  // ─── Perfiles de una empresa ───────────────────────────────────────────────
  //
  // Qué pantallas ve cada persona dentro de su empresa. Es distinto de los
  // módulos: aquellos dicen qué contrató la empresa y estos qué puede hacer
  // cada quien dentro de lo contratado. Los dos tienen que permitirlo.

  permisosDePerfil: () =>
    api.get<PermisoDePerfil[]>('/plataforma/permisos-perfil').then(r => r.data),

  perfiles: (id: number) =>
    api.get<PerfilDeEmpresa[]>(`/plataforma/empresas/${id}/perfiles`).then(r => r.data),

  crearPerfil: (id: number, cuerpo: Record<string, unknown>) =>
    api.post<PerfilDeEmpresa>(`/plataforma/empresas/${id}/perfiles`, cuerpo).then(r => r.data),

  editarPerfil: (id: number, perfilId: number, cuerpo: Record<string, unknown>) =>
    api.put<PerfilDeEmpresa>(`/plataforma/empresas/${id}/perfiles/${perfilId}`, cuerpo)
      .then(r => r.data),

  borrarPerfil: (id: number, perfilId: number) =>
    api.delete(`/plataforma/empresas/${id}/perfiles/${perfilId}`).then(r => r.data),

  // ─── Comercial ──────────────────────────────────────────────────────────────

  contrato: (id: number) =>
    api.get<Contrato>(`/plataforma/empresas/${id}/contrato`).then(r => r.data),
  guardarContrato: (id: number, c: Partial<Contrato>) =>
    api.put<Contrato>(`/plataforma/empresas/${id}/contrato`, c).then(r => r.data),

  modulos: (id: number) =>
    api.get<ModuloContratado[]>(`/plataforma/empresas/${id}/modulos`).then(r => r.data),
  guardarModulos: (id: number, claves: string[]) =>
    api.put<ModuloContratado[]>(`/plataforma/empresas/${id}/modulos`, { claves }).then(r => r.data),

  contactos: (id: number) =>
    api.get<Contacto[]>(`/plataforma/empresas/${id}/contactos`).then(r => r.data),
  crearContacto: (id: number, c: Contacto) =>
    api.post<Contacto>(`/plataforma/empresas/${id}/contactos`, c).then(r => r.data),
  borrarContacto: (id: number, contactoId: number) =>
    api.delete(`/plataforma/empresas/${id}/contactos/${contactoId}`),

  documentos: (id: number) =>
    api.get<Documento[]>(`/plataforma/empresas/${id}/documentos`).then(r => r.data),
  crearDocumento: (id: number, d: Documento) =>
    api.post<Documento>(`/plataforma/empresas/${id}/documentos`, d).then(r => r.data),
  borrarDocumento: (id: number, docId: number) =>
    api.delete(`/plataforma/empresas/${id}/documentos/${docId}`),

  pagos: (id: number) =>
    api.get<Pago[]>(`/plataforma/empresas/${id}/pagos`).then(r => r.data),
  registrarPago: (id: number, p: Pago) =>
    api.post<Pago>(`/plataforma/empresas/${id}/pagos`, p).then(r => r.data),
  borrarPago: (id: number, pagoId: number) =>
    api.delete(`/plataforma/empresas/${id}/pagos/${pagoId}`),

  cartera: (id: number) =>
    api.get<Cartera>(`/plataforma/empresas/${id}/cartera`).then(r => r.data),

  uso: (id: number) =>
    api.get<Uso>(`/plataforma/empresas/${id}/uso`).then(r => r.data),

  // ─── Facturación ────────────────────────────────────────────────────────────

  facturas: (id: number) =>
    api.get<Factura[]>(`/plataforma/empresas/${id}/facturas`).then(r => r.data),
  emitirFactura: (id: number, cuerpo: Record<string, unknown>) =>
    api.post<Factura>(`/plataforma/empresas/${id}/facturas`, cuerpo).then(r => r.data),
  anularFactura: (id: number, facturaId: number) =>
    api.post<Factura>(`/plataforma/empresas/${id}/facturas/${facturaId}/anular`).then(r => r.data),

  notasCredito: (id: number) =>
    api.get<NotaCredito[]>(`/plataforma/empresas/${id}/notas-credito`).then(r => r.data),
  emitirNota: (id: number, n: NotaCredito) =>
    api.post<NotaCredito>(`/plataforma/empresas/${id}/notas-credito`, n).then(r => r.data),

  contabilidad: (desde?: string, hasta?: string) =>
    api.get<Contabilidad>('/plataforma/contabilidad', { params: { desde, hasta } })
      .then(r => r.data),

  bitacora: (empresa?: string) =>
    api.get<AsientoBitacora[]>('/plataforma/bitacora', { params: { empresa, limite: 300 } })
      .then(r => r.data),
}

export const soporteApi = {
  cola: (filtros: Record<string, unknown>) =>
    api.get<Ticket[]>('/soporte/cola', { params: filtros }).then(r => r.data),

  ticket: (id: number) =>
    api.get<Ticket>(`/soporte/cola/${id}`).then(r => r.data),

  clasificar: (id: number, cambios: Record<string, unknown>) =>
    api.put<Ticket>(`/soporte/cola/${id}`, cambios).then(r => r.data),

  responder: (id: number, cuerpo: string, interno: boolean) =>
    api.post<Ticket>(`/soporte/cola/${id}/mensajes`, { cuerpo, interno }).then(r => r.data),

  adjuntar: (id: number, cuerpo: FormData) =>
    api.post<Ticket>(`/soporte/tickets/${id}/adjuntos`, cuerpo).then(r => r.data),

  // Los adjuntos no se sirven por carpeta pública: la descarga pasa por la API,
  // que comprueba de quién es el ticket.
  descargarAdjunto: (id: number) =>
    api.get(`/soporte/adjuntos/${id}`, { responseType: 'blob' }).then(r => r.data as Blob),

  resumen: () => api.get<ResumenSoporte>('/soporte/resumen').then(r => r.data),
}

export const agilApi = {
  tablero: (sprintId?: number) =>
    api.get<Tablero>('/soporte/agil/tablero', { params: { sprint_id: sprintId } })
      .then(r => r.data),

  mover: (id: number, estado: string, ordenAnterior?: number, ordenSiguiente?: number) =>
    api.put<Tarjeta>(`/soporte/agil/tickets/${id}/mover`, {
      estado, orden_anterior: ordenAnterior ?? null, orden_siguiente: ordenSiguiente ?? null,
    }).then(r => r.data),

  actualizar: (id: number, cambios: Record<string, unknown>) =>
    api.put<Tarjeta>(`/soporte/agil/tickets/${id}`, cambios).then(r => r.data),

  backlog: () => api.get<Tarjeta[]>('/soporte/agil/backlog').then(r => r.data),
  reordenar: (ids: number[]) =>
    api.put<Tarjeta[]>('/soporte/agil/backlog/orden', { ids }).then(r => r.data),

  sprints: () => api.get<SprintAgil[]>('/soporte/agil/sprints').then(r => r.data),
  crearSprint: (s: Partial<SprintAgil>) =>
    api.post<SprintAgil>('/soporte/agil/sprints', s).then(r => r.data),
  activarSprint: (id: number) =>
    api.post<SprintAgil>(`/soporte/agil/sprints/${id}/activar`).then(r => r.data),
  cerrarSprint: (id: number) =>
    api.post<SprintAgil>(`/soporte/agil/sprints/${id}/cerrar`).then(r => r.data),

  epicas: () => api.get<EpicaAgil[]>('/soporte/agil/epicas').then(r => r.data),
  crearEpica: (e: Partial<EpicaAgil>) =>
    api.post<EpicaAgil>('/soporte/agil/epicas', e).then(r => r.data),

  configurarColumna: (estado: string, cambios: Record<string, unknown>) =>
    api.put(`/soporte/agil/columnas/${estado}`, cambios).then(r => r.data),

  metricas: () => api.get<MetricasAgiles>('/soporte/agil/metricas').then(r => r.data),
}

export const equipoApi = {
  quienSoy: () => api.get<QuienSoy>('/plataforma/equipo/quien-soy').then(r => r.data),
  roles: () => api.get<RolConsola[]>('/plataforma/equipo/roles').then(r => r.data),
  listar: () => api.get<MiembroEquipo[]>('/plataforma/equipo').then(r => r.data),
  candidatos: () => api.get<Candidato[]>('/plataforma/equipo/candidatos').then(r => r.data),
  agregar: (cuerpo: Record<string, unknown>) =>
    api.post<MiembroEquipo>('/plataforma/equipo', cuerpo).then(r => r.data),
  editar: (id: number, cambios: Record<string, unknown>) =>
    api.put<MiembroEquipo>(`/plataforma/equipo/${id}`, cambios).then(r => r.data),
  quitar: (id: number) => api.delete(`/plataforma/equipo/${id}`),
}

export const landingApi = {
  estado: () => api.get<EstadoLanding>('/landing/estado').then(r => r.data),
  inicial: () => api.get<Record<string, any>>('/landing/inicial').then(r => r.data),
  publicar: (contenido: Record<string, any>) =>
    api.put<EstadoLanding>('/landing/contenido', { contenido }).then(r => r.data),
}
