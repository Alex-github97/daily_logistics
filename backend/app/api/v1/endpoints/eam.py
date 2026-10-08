from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.inventario_kardex import sincronizar_orden, revertir_orden
from app.infrastructure.models.eam import (
    EAMTipoTrabajo, EAMActividad, EAMRepuesto, EAMFallaCatalogo,
    EAMCausaCatalogo, EAMSolucionCatalogo, EAMContratista,
    EAMActivo, EAMComponente, EAMDocumentoActivo,
    EAMChecklistPlantilla, EAMChecklistPregunta,
    EAMPlanMantenimiento, EAMPlanDetalle, EAMPlanActivo, EAMPlanRepuesto,
    EAMOrdenTrabajo, EAMChecklistEjecucion, EAMChecklistRespuesta,
    EAMOTMaterial, EAMOTManoObra,
    EAMMuestraAceite, EAMNeumatico, EAMMovimientoNeumatico,
    EAMBodegaNeumatico, EAMDanoNeumaticoCatalogo, EAMNeumaticoCatalogo, EAMActivo,
    EAMInspeccionNeumatico, EAMReencaucheLote, EAMReencaucheDetalle, EAMNeumaticoConfig,
    EAMRegistroCombustible, EAMGarantia, EAMGarantiaReclamacion, EAMFMEA,
    EAMCalibracion, EAMKPIDiario,
    EAMZonaNeumatico, EAMBandaReencauche, EAMMotivoFinVida,
    EAMAjusteNeumaticoCatalogo, EAMAjusteNeumatico,
    EAMEsquemaVehiculo, EAMEsquemaAsignacion,
    EAMTrabajoNeumatico, EAMPeriodicidadTrabajoNeumatico, EAMTrabajoRealizadoNeumatico,
    EAMReesculturado, EAMVidaNeumatico,
    EAMCongeladoNeumatico, EAMCongeladoDetalleNeumatico,
    EAMTipoActivo,
    EAMMarcaNeumatico, EAMDimensionNeumatico, EAMReferenciaNeumatico, EAMReferenciaDimension,
    EAMMarcaActivo, EAMLineaActivo, EAMModeloActivo, EAMMotorActivo, EAMTipoCombustible,
    EAMCatalogoActivo,
)
from app.infrastructure.models.tms import TMSVehiculo
from app.infrastructure.models.flota import FlotaVehiculo
from app.infrastructure.models.checklist import ChkEjecucion
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/eam", tags=["eam"])


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class TipoTrabajoCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None

class TipoTrabajoResponse(TipoTrabajoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class ActividadCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class ActividadResponse(ActividadCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class RepuestoCreate(BaseModel):
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    unidad_medida: Optional[str] = None
    costo_unitario: Optional[float] = 0
    stock_minimo: Optional[int] = 0
    stock_actual: Optional[int] = 0
    proveedor_ppal: Optional[str] = None

class RepuestoResponse(RepuestoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class FallaCreate(BaseModel):
    codigo: Optional[str] = None
    descripcion: str
    tipo_activo: Optional[str] = None

class FallaResponse(FallaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class CausaCreate(BaseModel):
    descripcion: str

class CausaResponse(CausaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class SolucionCreate(BaseModel):
    descripcion: str

class SolucionResponse(SolucionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class ContratistaCreate(BaseModel):
    nombre: str
    nit: Optional[str] = None
    tipo: Optional[str] = None
    especialidad: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None
    calificacion: Optional[float] = 5.0

class ContratistaResponse(ContratistaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class ActivoCreate(BaseModel):
    # Opcionales porque el alta ya no los pide: el codigo se genera consecutivo
    # por tipo de activo y el nombre se compone de la ficha tecnica. Siguen
    # siendo obligatorios en la tabla, asi que se rellenan antes de guardar.
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    tipo_activo: Optional[str] = None
    estado: Optional[str] = "OPERATIVO"
    criticidad: Optional[str] = "MEDIA"
    parent_id: Optional[int] = None
    marca: Optional[str] = None
    linea: Optional[str] = None
    modelo: Optional[str] = None
    anio: Optional[int] = None
    numero_serie: Optional[str] = None
    numero_motor: Optional[str] = None
    numero_chasis: Optional[str] = None
    numero_carroceria: Optional[str] = None
    observaciones: Optional[str] = None
    observaciones_adicionales: Optional[str] = None
    cuenta_contable: Optional[str] = None
    centro_costo: Optional[str] = None
    placa: Optional[str] = None
    color: Optional[str] = None
    fecha_adquisicion: Optional[date] = None
    costo_adquisicion: Optional[float] = None
    valor_libro: Optional[float] = None
    vida_util_anios: Optional[int] = None
    vida_util_km: Optional[float] = None
    ubicacion: Optional[str] = None
    sede: Optional[str] = None
    area: Optional[str] = None
    responsable: Optional[str] = None
    odometro_actual: Optional[float] = 0
    horometro_actual: Optional[float] = 0
    tipo_combustible: Optional[str] = None
    capacidad_combustible: Optional[float] = None
    numero_ejes: Optional[int] = None
    layout_llantas: Optional[List[int]] = None
    tiene_repuesto: Optional[bool] = True
    cantidad_repuestos: Optional[int] = 1
    motor_marca: Optional[str] = None
    motor_linea: Optional[str] = None
    motor_cc: Optional[float] = None

class ActivoResponse(ActivoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool
    origen: Optional[str] = "EAM"
    origen_id: Optional[int] = None

class TipoActivoCreate(BaseModel):
    codigo: str
    nombre: str
    usa_llantas: Optional[bool] = False

class TipoActivoResponse(TipoActivoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class VehiculoCombinadoResponse(BaseModel):
    origen: str            # EAM | TMS | FLOTA
    flota: str             # PROPIA | EXTERNA
    id: int                # id en la tabla de origen (eam_activo.id si origen=EAM)
    activo_id: Optional[int] = None   # eam_activo.id ya vinculado, si existe (permite usarlo en Neumáticos sin re-vincular)
    codigo: Optional[str] = None      # código del activo EAM (identifica los que no tienen placa)
    nombre: Optional[str] = None
    placa: Optional[str] = None
    tipo: Optional[str] = None
    marca: Optional[str] = None
    linea: Optional[str] = None
    modelo: Optional[str] = None
    anio: Optional[int] = None
    numero_ejes: Optional[int] = None
    layout_llantas: Optional[List[int]] = None   # llantas por eje ya asignadas al activo
    tiene_repuesto: Optional[bool] = None
    capacidad_kg: Optional[float] = None
    estado: Optional[str] = None
    motor_marca: Optional[str] = None
    motor_linea: Optional[str] = None
    motor_cc: Optional[float] = None
    propietario: Optional[str] = None

class VincularExternoRequest(BaseModel):
    origen: str      # TMS | FLOTA
    origen_id: int

class ComponenteCreate(BaseModel):
    activo_id: int
    nombre: str
    descripcion: Optional[str] = None
    numero_parte: Optional[str] = None
    marca: Optional[str] = None
    estado: Optional[str] = "BUENO"
    criticidad: Optional[str] = "MEDIA"
    vida_util_horas: Optional[float] = None
    horas_actuales: Optional[float] = 0

class ComponenteResponse(ComponenteCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class ChecklistPlantillaCreate(BaseModel):
    nombre: str
    tipo_activo: Optional[str] = None
    descripcion: Optional[str] = None

class ChecklistPlantillaResponse(ChecklistPlantillaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class ChecklistPreguntaCreate(BaseModel):
    plantilla_id: int
    orden: Optional[int] = 0
    seccion: Optional[str] = None
    pregunta: str
    tipo_respuesta: Optional[str] = "SI_NO"
    requiere_foto: Optional[bool] = False
    requiere_firma: Optional[bool] = False
    critica: Optional[bool] = False

class ChecklistPreguntaResponse(ChecklistPreguntaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool

class PlanTareaItem(BaseModel):
    """Trabajo de la rutina: solo mano de obra."""
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    descripcion: str
    actividad_id: Optional[int] = None
    tiempo_estimado: Optional[float] = None
    costo_mano_obra: float = 0
    orden: int = 0

class PlanRepuestoItem(BaseModel):
    """Material que consume la rutina cada vez que se ejecuta."""
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    repuesto_id: Optional[int] = None
    descripcion: str
    cantidad: float = 1
    unidad: Optional[str] = None
    costo_unitario: float = 0
    orden: int = 0

class PlanMantenimientoCreate(BaseModel):
    nombre: str
    # Alcance: un activo puntual, o los niveles del catálogo que apliquen.
    activo_id: Optional[int] = None
    tipo_activo: Optional[str] = None
    marca: Optional[str] = None
    linea: Optional[str] = None
    tipo_mant: Optional[str] = "TIEMPO"
    frecuencia: Optional[int] = None
    unidad: Optional[str] = None
    tipo_ot: Optional[str] = "PREVENTIVA"
    checklist_id: Optional[int] = None
    descripcion: Optional[str] = None
    costo_estimado: Optional[float] = None
    tareas: List[PlanTareaItem] = []
    repuestos: List[PlanRepuestoItem] = []

class PlanMantenimientoResponse(PlanMantenimientoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool
    # Costo de referencia, sumado del detalle. `costo_estimado` se deja como lo
    # escribió el usuario, por si quiere anotar un valor negociado.
    costo_mano_obra: float = 0
    costo_repuestos: float = 0
    costo_calculado: float = 0
    # Cuántos activos cubre el alcance y cómo están repartidos.
    activos_cubiertos: int = 0
    vencidas: int = 0
    proximas: int = 0
    sin_ejecutar: int = 0

class CumplimientoActivo(BaseModel):
    """Estado de una rutina en un activo. Se calcula contra la lectura de hoy."""
    model_config = ConfigDict(from_attributes=True)
    plan_id: int
    plan_nombre: str
    frecuencia: Optional[int] = None
    unidad: Optional[str] = None
    tipo_ot: Optional[str] = None
    activo_id: int
    activo_codigo: Optional[str] = None
    activo_nombre: Optional[str] = None
    odometro_activo: Optional[float] = None
    horometro_activo: Optional[float] = None
    ultima_ejecucion_fecha: Optional[datetime] = None
    ultima_ejecucion_odometro: Optional[float] = None
    ultima_ot_id: Optional[int] = None
    proxima_fecha: Optional[datetime] = None
    proximo_odometro: Optional[float] = None
    proximo_horometro: Optional[float] = None
    faltante: Optional[float] = None
    unidad_faltante: Optional[str] = None
    estado_rutina: str = "SIN_EJECUTAR"
    # El detalle viaja con el cumplimiento para que la OT pueda copiarlo sin
    # tener que ir a buscar el plan aparte.
    tareas: List[PlanTareaItem] = []
    repuestos: List[PlanRepuestoItem] = []

class OTTrabajoItem(BaseModel):
    """Una línea de eam_ot_mano_obra. `contratista_id` en None = taller interno."""
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    actividad: str
    tecnico: Optional[str] = None
    contratista_id: Optional[int] = None
    tipo_trabajo_id: Optional[int] = None
    sistema: Optional[str] = None
    subsistema: Optional[str] = None
    horas: Optional[float] = None
    tarifa_hora: Optional[float] = None
    costo_total: float = 0
    observaciones: Optional[str] = None

class OTRepuestoItem(BaseModel):
    """Una línea de eam_ot_material. `contratista_id` en None = taller interno."""
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    repuesto_id: Optional[int] = None
    contratista_id: Optional[int] = None
    descripcion: str
    cantidad: float = 1
    unidad: Optional[str] = None
    costo_unit: float = 0
    costo_total: float = 0
    # De qué bodega sale el repuesto. Vacío = la bodega por defecto. Una línea
    # sin `repuesto_id` es material suelto y no descuenta inventario.
    bodega_id: Optional[int] = None

class OTCreate(BaseModel):
    # El número lo asigna el servidor; se acepta si viene para no romper a
    # quien ya lo mandaba.
    numero: Optional[str] = None
    activo_id: int
    tipo_ot: Optional[str] = "CORRECTIVA"
    tipo_trabajo_id: Optional[int] = None
    estado: Optional[str] = "PENDIENTE"
    prioridad: Optional[str] = "MEDIA"
    descripcion: str
    falla_id: Optional[int] = None
    causa_id: Optional[int] = None
    solucion_id: Optional[int] = None
    plan_id: Optional[int] = None
    contratista_id: Optional[int] = None
    tecnico_asignado: Optional[str] = None
    fecha_requerida: Optional[datetime] = None
    odometro: Optional[float] = None
    horometro: Optional[float] = None
    tiempo_estimado_horas: Optional[float] = None
    observaciones: Optional[str] = None
    creado_por: Optional[str] = None
    centro_costo: Optional[str] = None
    ciudad: Optional[str] = None
    afecta_disponibilidad: bool = True
    es_falla: bool = False
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    fecha_posible_cierre: Optional[datetime] = None
    costo_servicios: float = 0
    trabajos: List[OTTrabajoItem] = []
    repuestos: List[OTRepuestoItem] = []

class OTResponse(OTCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero: str
    costo_mano_obra: float
    costo_repuestos: float
    costo_servicios: float
    costo_total: float
    tiempo_real_horas: Optional[float] = None

class OTEstadoUpdate(BaseModel):
    estado: str
    observaciones: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    tiempo_real_horas: Optional[float] = None

class MuestraAceiteCreate(BaseModel):
    activo_id: int
    componente_id: Optional[int] = None
    numero_muestra: str
    fecha_toma: datetime
    tipo_lubricante: Optional[str] = None
    horas_aceite: Optional[float] = None
    horas_equipo: Optional[float] = None
    odometro: Optional[float] = None
    laboratorio: Optional[str] = None
    hierro_ppm: Optional[float] = None
    cobre_ppm: Optional[float] = None
    aluminio_ppm: Optional[float] = None
    silicio_ppm: Optional[float] = None
    sodio_ppm: Optional[float] = None
    agua_pct: Optional[float] = None
    viscosidad_40: Optional[float] = None
    viscosidad_100: Optional[float] = None
    contaminacion: Optional[str] = "NORMAL"
    diagnostico: Optional[str] = None
    recomendacion: Optional[str] = None
    alerta: Optional[bool] = False

class MuestraAceiteResponse(MuestraAceiteCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class NeumaticCreate(BaseModel):
    codigo: str
    marca: Optional[str] = None
    referencia: Optional[str] = None
    medida: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = "ALMACENADO"
    activo_id: Optional[int] = None
    posicion: Optional[str] = None
    bodega_id: Optional[int] = None
    vida_util_km: Optional[float] = None
    profundidad_diseño: Optional[float] = None
    profundidad_actual: Optional[float] = None
    costo: Optional[float] = None
    proveedor: Optional[str] = None
    tipo_uso: Optional[str] = None            # DIRECCIONAL/TRACCION/REMOLQUE/MULTIPOSICION/REPUESTO
    presion_recomendada: Optional[float] = None
    zona_id: Optional[int] = None
    dot: Optional[str] = None
    tipo_rin: Optional[str] = None
    # Vida con la que entra: VN (vida nueva) o R{n} (n-esimo reencauche).
    # `reencauches` = 0 -> VN; 1..n -> R1..Rn
    reencauches: Optional[int] = 0
    # Llanta que ingresa ya usada: se toman su profundidad y kilometraje reales
    es_usada: Optional[bool] = False
    km_actual: Optional[float] = None

class NeumaticUpdate(BaseModel):
    marca: Optional[str] = None
    referencia: Optional[str] = None
    medida: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    bodega_id: Optional[int] = None
    posicion: Optional[str] = None
    vida_util_km: Optional[float] = None
    profundidad_diseño: Optional[float] = None
    profundidad_actual: Optional[float] = None
    km_actual: Optional[float] = None
    costo: Optional[float] = None
    proveedor: Optional[str] = None
    tipo_uso: Optional[str] = None
    presion_recomendada: Optional[float] = None
    zona_id: Optional[int] = None
    motivo_fin_vida_id: Optional[int] = None
    dot: Optional[str] = None
    tipo_rin: Optional[str] = None

class NeumaticResponse(NeumaticCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    km_inicio: float
    km_actual: float
    km_total: float
    reencauches: int
    dano_id: Optional[int] = None
    motivo_baja: Optional[str] = None
    motivo_fin_vida_id: Optional[int] = None
    fecha_baja: Optional[date] = None
    presion_actual: Optional[float] = None
    orientacion: Optional[str] = None
    profundidad_externa: Optional[float] = None
    profundidad_interna: Optional[float] = None

# ── Bodegas de neumáticos ──
class BodegaNeumaticoCreate(BaseModel):
    codigo: str
    nombre: str
    ubicacion: Optional[str] = None
    capacidad: Optional[int] = None
    activo: bool = True

class BodegaNeumaticoResponse(BodegaNeumaticoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# ── Catálogo de daños de neumático ──
class DanoNeumaticoCreate(BaseModel):
    codigo: str
    nombre: str
    severidad: str = "MODERADO"   # LEVE/MODERADO/GRAVE
    descripcion: Optional[str] = None
    accion: str = "INSPECCION"    # REENCAUCHE/DESCARTE/INSPECCION
    activo: bool = True

class DanoNeumaticoResponse(DanoNeumaticoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# ── Movimiento de neumático (rotación/instalación/etc.) ──
class MovNeumaticoCreate(BaseModel):
    neumatico_id: int
    tipo_movimiento: str          # INSTALACION/ROTACION/DESMONTAJE/REENCAUCHE/BAJA/ALMACENAMIENTO
    fecha: datetime               # fecha y hora del movimiento (obligatoria)
    activo_id: Optional[int] = None       # vehículo destino (instalación/rotación)
    posicion: Optional[str] = None        # posición destino
    bodega_id: Optional[int] = None       # bodega destino (desmontaje/almacenamiento)
    km_odometro: Optional[float] = None
    horometro: Optional[float] = None     # para equipos que no llevan odómetro
    dano_id: Optional[int] = None         # para BAJA/REENCAUCHE
    motivo_fin_vida_id: Optional[int] = None   # para BAJA (catálogo estructurado)
    motivo: Optional[str] = None
    observaciones: Optional[str] = None
    tecnico: Optional[str] = None

class MovNeumaticoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    neumatico_id: int
    tipo_movimiento: str
    activo_id: Optional[int] = None
    posicion_origen: Optional[str] = None
    posicion: Optional[str] = None
    bodega_id: Optional[int] = None
    km_odometro: Optional[float] = None
    horometro: Optional[float] = None
    fecha: Optional[datetime] = None
    observaciones: Optional[str] = None
    tecnico: Optional[str] = None

class PosicionLayout(BaseModel):
    codigo: str
    label: str
    eje: int
    lado: str
    numero: Optional[int] = None

# ── Catálogo de atributos de neumático (marca/medida/referencia/vida) ──
class CatalogoNeuCreate(BaseModel):
    tipo: str                 # MARCA / MEDIDA / REFERENCIA / VIDA
    nombre: str
    valor: Optional[float] = None
    activo: bool = True

class CatalogoNeuResponse(CatalogoNeuCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# ── Inspecciones ──
class InspeccionNeuCreate(BaseModel):
    fecha: datetime
    profundidad_izq: Optional[float] = None
    profundidad_centro: Optional[float] = None
    profundidad_der: Optional[float] = None
    presion_psi: Optional[float] = None
    km_odometro: Optional[float] = None
    posicion: Optional[str] = None
    estado_visual: Optional[str] = None      # BUENO/REGULAR/CRITICO
    observaciones: Optional[str] = None
    tecnico: Optional[str] = None

class InspeccionNeuResponse(InspeccionNeuCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    neumatico_id: int
    profundidad_min: Optional[float] = None

# ── Reencauche ──
class ReencaucheLoteCreate(BaseModel):
    codigo: str
    fecha_envio: date
    proveedor: Optional[str] = None
    remision: Optional[str] = None
    observaciones: Optional[str] = None

class ReencaucheLoteResponse(ReencaucheLoteCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    estado: str

class ReencaucheDetalleCreate(BaseModel):
    neumatico_id: int
    banda: Optional[str] = None       # legacy: texto libre si no viene del catálogo
    banda_id: Optional[int] = None

class ReencaucheDetalleUpdate(BaseModel):
    resultado: str                # REENCAUCHADA/REMANENTE/RECHAZO
    profundidad_nueva: Optional[float] = None
    vida_remanente_km: Optional[float] = None
    costo: Optional[float] = None
    dano_id: Optional[int] = None    # requerido si RECHAZO
    motivo_fin_vida_id: Optional[int] = None   # requerido si RECHAZO

class ReencaucheDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lote_id: int
    neumatico_id: int
    banda: Optional[str] = None
    banda_id: Optional[int] = None
    resultado: str
    profundidad_nueva: Optional[float] = None
    vida_remanente_km: Optional[float] = None
    costo: Optional[float] = None

# ── Configuración global ──
class NeuConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    montaje_estricto: bool = True
    profundidad_minima: float = 3.0
    presion_min: float = 90.0
    presion_max: float = 120.0
    umbral_desalineacion: float = 2.0

# ── Zonas de llantas ──
class ZonaNeumaticoCreate(BaseModel):
    codigo: str
    nombre: str
    activo: bool = True

class ZonaNeumaticoResponse(ZonaNeumaticoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# ── Bandas de reencauche ──
class BandaReencaucheCreate(BaseModel):
    marca: str
    referencia: Optional[str] = None
    dimension: Optional[str] = None
    profundidad_original: Optional[float] = None
    profundidad_minima: Optional[float] = None
    tipo_posicion: Optional[str] = None
    sentido_rotacion: Optional[str] = None
    reesculturable: bool = False
    costo_defecto: Optional[float] = None
    presion_minima: Optional[float] = None
    presion_maxima: Optional[float] = None
    comentarios: Optional[str] = None
    activo: bool = True

class BandaReencaucheResponse(BandaReencaucheCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# ── Motivos de fin de vida ──
class MotivoFinVidaCreate(BaseModel):
    nombre: str
    aplica_descarte: bool = True
    aplica_fin_vida: bool = True
    activo: bool = True

class MotivoFinVidaResponse(MotivoFinVidaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# ── Ajustes de valor ──
class AjusteNeuCatalogoCreate(BaseModel):
    nombre: str
    activo: bool = True

class AjusteNeuCatalogoResponse(AjusteNeuCatalogoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class AjusteNeuCreate(BaseModel):
    motivo_id: int
    fecha: date
    valor: float
    comentarios: Optional[str] = None

class AjusteNeuResponse(AjusteNeuCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    neumatico_id: int

# ── Esquemas de vehículo ──
class EsquemaVehiculoCreate(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    tipo_activo: Optional[str] = None
    numero_ejes: int = 2
    layout: Optional[List[int]] = None   # llantas por eje, en orden; None = patrón clásico
    tiene_repuesto: bool = True
    cantidad_repuestos: int = 1
    observaciones: Optional[str] = None
    activo: bool = True

class EsquemaVehiculoResponse(EsquemaVehiculoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class EsquemaAsignacionCreate(BaseModel):
    activo_id: int
    esquema_id: int
    fecha_vigencia: date
    observaciones: Optional[str] = None

class EsquemaAsignacionResponse(EsquemaAsignacionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# ── Trabajos y periodicidad ──
class TrabajoNeumaticoCreate(BaseModel):
    nombre: str
    observaciones: Optional[str] = None
    es_predeterminado: bool = False
    activo: bool = True

class TrabajoNeumaticoResponse(TrabajoNeumaticoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class PeriodicidadTrabajoCreate(BaseModel):
    trabajo_id: int
    tipo_activo: Optional[str] = None
    valor: float
    unidad: str = "KILOMETROS"
    activo: bool = True

class PeriodicidadTrabajoResponse(PeriodicidadTrabajoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class TrabajoRealizadoCreate(BaseModel):
    trabajo_id: int
    fecha: datetime
    km_odometro: Optional[float] = None
    cantidad: int = 1
    costo_unitario: Optional[float] = None
    proveedor: Optional[str] = None
    observaciones: Optional[str] = None

class TrabajoRealizadoResponse(TrabajoRealizadoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    neumatico_id: int

# ── Reesculturado (re-grooving) ──
class ReesculturadoCreate(BaseModel):
    fecha: datetime
    km_odometro: Optional[float] = None
    proveedor: Optional[str] = None
    costo: Optional[float] = None
    profundidad_nueva: float

class ReesculturadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    neumatico_id: int
    fecha: datetime
    km_odometro: Optional[float] = None
    proveedor: Optional[str] = None
    costo: Optional[float] = None
    profundidad_anterior: Optional[float] = None
    profundidad_nueva: Optional[float] = None
    deshecho: bool
    fecha_deshecho: Optional[datetime] = None

# ── Recuperar banda ──
class RecuperarBandaCreate(BaseModel):
    neumatico_destino_id: int
    fecha: datetime
    mm_transferidos: Optional[float] = None
    costo_transferido: Optional[float] = None
    observaciones: Optional[str] = None

# ── Cambiar zona ──
class CambiarZonaCreate(BaseModel):
    zona_id: int
    fecha: datetime
    observaciones: Optional[str] = None

# ── Vidas de la llanta ──
class VidaNeumaticoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    neumatico_id: int
    numero_vida: int
    tipo: str
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    km_inicio: float
    km_fin: Optional[float] = None
    costo: Optional[float] = None
    profundidad_inicial: Optional[float] = None
    profundidad_final: Optional[float] = None
    motivo_cierre_id: Optional[int] = None

# ── Congelar datos (snapshot histórico) ──
class CongeladoCreate(BaseModel):
    descripcion: Optional[str] = None

class CongeladoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha: datetime
    descripcion: Optional[str] = None

class CongeladoDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    congelado_id: int
    neumatico_id: int
    codigo: str
    marca: Optional[str] = None
    medida: Optional[str] = None
    estado: Optional[str] = None
    km_total: Optional[float] = None
    costo: Optional[float] = None
    costo_neto: Optional[float] = None
    cpk: Optional[float] = None
    costo_mm: Optional[float] = None
    mm_gastados: Optional[float] = None

# ── Indicadores / alertas ──
class IndicadorNeuResponse(BaseModel):
    neumatico_id: int
    codigo: str
    marca: Optional[str] = None
    medida: Optional[str] = None
    estado: Optional[str] = None
    posicion: Optional[str] = None
    km_total: float
    costo: Optional[float] = None
    ajustes: Optional[float] = None             # total de ajustes (deducciones) aplicados
    costo_neto: Optional[float] = None          # costo - ajustes, usado para cpk/costo_mm
    cpk: Optional[float] = None                 # costo neto por km
    costo_mm: Optional[float] = None            # costo neto por mm gastado
    mm_gastados: Optional[float] = None
    vida_util_km: Optional[float] = None
    km_proyectado: Optional[float] = None       # proyección de vida (km)
    pct_desgaste: Optional[float] = None        # % de desgaste

class AlertaNeuResponse(BaseModel):
    neumatico_id: int
    codigo: str
    tipo: str                 # PROFUNDIDAD / PRESION / DESALINEACION
    severidad: str            # ALTA / MEDIA
    mensaje: str
    posicion: Optional[str] = None
    activo_id: Optional[int] = None

# Los esquemas del registro de combustible se retiraron: viven en
# `combustible.py`. Ademas se llamaban igual que los del catalogo de tipos de
# combustible mas abajo, asi que el segundo tapaba al primero y el endpoint de
# registros respondia con el esquema equivocado. Un solo nombre, un solo sitio.

class GarantiaCreate(BaseModel):
    activo_id: Optional[int] = None
    tipo: Optional[str] = None
    descripcion: str
    proveedor: Optional[str] = None
    numero_garantia: Optional[str] = None
    fecha_inicio: date
    fecha_fin: date
    condiciones: Optional[str] = None
    estado: Optional[str] = "VIGENTE"
    valor_cubierto: Optional[float] = None
    # Qué cubre, una por línea; el resto es a quién llamar y quién responde.
    cobertura: Optional[str] = None
    contacto_proveedor: Optional[str] = None
    telefono_proveedor: Optional[str] = None
    documento: Optional[str] = None
    responsable: Optional[str] = None

class GarantiaResponse(GarantiaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reclamaciones: int
    # Calculados: ver el comentario de la sección de garantías. Los días pueden
    # ser negativos —eso es una garantía vencida— y por eso no van sin signo.
    dias_restantes: Optional[int] = None
    ultimo_reclamo: Optional[date] = None
    activo_codigo: Optional[str] = None

class CalibracionCreate(BaseModel):
    activo_id: int
    tipo_instrumento: Optional[str] = None
    numero_certificado: Optional[str] = None
    laboratorio: Optional[str] = None
    acreditacion: Optional[str] = None
    fecha_calibracion: date
    fecha_vencimiento: date
    resultado: Optional[str] = None
    estado: Optional[str] = "VIGENTE"
    incertidumbre: Optional[str] = None
    observaciones: Optional[str] = None

class CalibracionResponse(CalibracionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class ChecklistEjecucionCreate(BaseModel):
    plantilla_id: int
    activo_id: int
    ot_id: Optional[int] = None
    ejecutado_por: Optional[str] = None

class ChecklistEjecucionResponse(ChecklistEjecucionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    estado: Optional[str] = None
    pct_conforme: float
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None


# ─── Dashboard / KPIs ─────────────────────────────────────────────────────────

@router.get("/dashboard/kpis")
async def get_dashboard_kpis(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count(EAMActivo.id)).where(EAMActivo.activo == True))
    operativos = await db.scalar(
        select(func.count(EAMActivo.id)).where(
            and_(EAMActivo.activo == True, EAMActivo.estado == "OPERATIVO")
        )
    )
    en_mant = await db.scalar(
        select(func.count(EAMActivo.id)).where(
            and_(EAMActivo.activo == True, EAMActivo.estado == "EN_MANTENIMIENTO")
        )
    )
    ots_abiertas = await db.scalar(
        select(func.count(EAMOrdenTrabajo.id)).where(
            EAMOrdenTrabajo.estado.in_(["PENDIENTE", "ASIGNADA", "EN_EJECUCION", "EN_ESPERA_REPUESTOS"])
        )
    )
    ots_completadas = await db.scalar(
        select(func.count(EAMOrdenTrabajo.id)).where(EAMOrdenTrabajo.estado == "COMPLETADA")
    )
    garantias_vigentes = await db.scalar(
        select(func.count(EAMGarantia.id)).where(EAMGarantia.estado == "VIGENTE")
    )
    alertas_aceite = await db.scalar(
        select(func.count(EAMMuestraAceite.id)).where(EAMMuestraAceite.alerta == True)
    )
    calibraciones_vencidas = await db.scalar(
        select(func.count(EAMCalibracion.id)).where(EAMCalibracion.estado == "VENCIDA")
    )
    total_s = total or 0
    operativos_s = operativos or 0
    disponibilidad = round((operativos_s / total_s * 100) if total_s > 0 else 0, 1)
    return {
        "total_activos": total_s,
        "activos_operativos": operativos_s,
        "activos_mantenimiento": en_mant or 0,
        "disponibilidad_pct": disponibilidad,
        "ots_abiertas": ots_abiertas or 0,
        "ots_completadas": ots_completadas or 0,
        "garantias_vigentes": garantias_vigentes or 0,
        "alertas_aceite": alertas_aceite or 0,
        "calibraciones_vencidas": calibraciones_vencidas or 0,
    }


# ─── Catálogos ────────────────────────────────────────────────────────────────

@router.get("/catalogos/tipos-trabajo", response_model=List[TipoTrabajoResponse])
async def list_tipos_trabajo(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMTipoTrabajo).where(EAMTipoTrabajo.activo == True))
    return result.scalars().all()

@router.post("/catalogos/tipos-trabajo", response_model=TipoTrabajoResponse)
async def create_tipo_trabajo(data: TipoTrabajoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMTipoTrabajo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/catalogos/actividades", response_model=List[ActividadResponse])
async def list_actividades(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMActividad).where(EAMActividad.activo == True))
    return result.scalars().all()

@router.post("/catalogos/actividades", response_model=ActividadResponse)
async def create_actividad(data: ActividadCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMActividad(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/catalogos/repuestos", response_model=List[RepuestoResponse])
async def list_repuestos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMRepuesto).where(EAMRepuesto.activo == True))
    return result.scalars().all()

@router.post("/catalogos/repuestos", response_model=RepuestoResponse)
async def create_repuesto(data: RepuestoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMRepuesto(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/catalogos/fallas", response_model=List[FallaResponse])
async def list_fallas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMFallaCatalogo).where(EAMFallaCatalogo.activo == True))
    return result.scalars().all()

@router.post("/catalogos/fallas", response_model=FallaResponse)
async def create_falla(data: FallaCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMFallaCatalogo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/catalogos/causas", response_model=List[CausaResponse])
async def list_causas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMCausaCatalogo).where(EAMCausaCatalogo.activo == True))
    return result.scalars().all()

@router.post("/catalogos/causas", response_model=CausaResponse)
async def create_causa(data: CausaCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMCausaCatalogo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/catalogos/soluciones", response_model=List[SolucionResponse])
async def list_soluciones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMSolucionCatalogo).where(EAMSolucionCatalogo.activo == True))
    return result.scalars().all()

@router.post("/catalogos/soluciones", response_model=SolucionResponse)
async def create_solucion(data: SolucionCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMSolucionCatalogo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


def _registrar_edicion_catalogo(ruta: str, modelo, esquema_create, esquema_response, etiqueta: str):
    """Agrega el PUT y el DELETE de un catálogo del CMMS.

    El alta y el listado ya estaban escritos uno por uno arriba; lo que faltaba
    para poder administrarlos desde la configuración era editar y desactivar.
    Se registran en bucle porque los cinco catálogos hacen exactamente lo mismo.
    """

    @router.put(f"/catalogos/{ruta}/{{item_id}}", response_model=esquema_response)
    async def _actualizar(item_id: int, data: esquema_create, db: AsyncSession = Depends(get_db)):
        obj = await db.get(modelo, item_id)
        if not obj or not obj.activo:
            raise HTTPException(404, f"{etiqueta} no encontrado")
        for k, v in data.model_dump().items():
            setattr(obj, k, v)
        await db.commit(); await db.refresh(obj)
        return obj

    @router.delete(f"/catalogos/{ruta}/{{item_id}}", status_code=204)
    async def _eliminar(item_id: int, db: AsyncSession = Depends(get_db)):
        obj = await db.get(modelo, item_id)
        if not obj or not obj.activo:
            raise HTTPException(404, f"{etiqueta} no encontrado")
        # Baja lógica: las OTs ya cerradas apuntan a estas filas por id.
        obj.activo = False
        await db.commit()


for _ruta, _modelo, _create, _response, _etiqueta in [
    ("actividades", EAMActividad, ActividadCreate, ActividadResponse, "Actividad"),
    ("repuestos", EAMRepuesto, RepuestoCreate, RepuestoResponse, "Repuesto"),
    ("fallas", EAMFallaCatalogo, FallaCreate, FallaResponse, "Falla"),
    ("causas", EAMCausaCatalogo, CausaCreate, CausaResponse, "Causa"),
    ("soluciones", EAMSolucionCatalogo, SolucionCreate, SolucionResponse, "Solución"),
    ("tipos-trabajo", EAMTipoTrabajo, TipoTrabajoCreate, TipoTrabajoResponse, "Tipo de trabajo"),
]:
    _registrar_edicion_catalogo(_ruta, _modelo, _create, _response, _etiqueta)


# ─── Contratistas ─────────────────────────────────────────────────────────────

@router.get("/contratistas", response_model=List[ContratistaResponse])
async def list_contratistas(
    incluir_inactivos: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Contratistas. Por defecto solo los activos; la pantalla de configuracion
    pide tambien los inactivos para poder reactivarlos."""
    q = select(EAMContratista)
    if not incluir_inactivos:
        q = q.where(EAMContratista.activo == True)
    result = await db.execute(q.order_by(EAMContratista.nombre))
    return result.scalars().all()

@router.post("/contratistas", response_model=ContratistaResponse, status_code=201)
async def create_contratista(data: ContratistaCreate, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre del contratista es obligatorio.")
    r = await db.execute(select(EAMContratista).where(
        func.lower(EAMContratista.nombre) == nombre.lower()))
    existente = r.scalar_one_or_none()
    if existente is not None:
        raise HTTPException(400, "Ya existe un contratista llamado '%s'%s."
                                 % (existente.nombre,
                                    " (esta inactivo, puede reactivarlo)"
                                    if not existente.activo else ""))
    valores = data.model_dump()
    valores["nombre"] = nombre
    obj = EAMContratista(**valores)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/contratistas/{contratista_id}", response_model=ContratistaResponse)
async def update_contratista(
    contratista_id: int, data: ContratistaCreate, db: AsyncSession = Depends(get_db),
):
    obj = await db.get(EAMContratista, contratista_id)
    if obj is None:
        raise HTTPException(404, "Contratista no encontrado")
    valores = data.model_dump(exclude_unset=True)
    nombre = (valores.get("nombre") or "").strip()
    if "nombre" in valores:
        if not nombre:
            raise HTTPException(400, "El nombre del contratista es obligatorio.")
        r = await db.execute(select(EAMContratista).where(
            func.lower(EAMContratista.nombre) == nombre.lower(),
            EAMContratista.id != contratista_id))
        if r.scalar_one_or_none() is not None:
            raise HTTPException(400, "Ya existe otro contratista llamado '%s'." % nombre)
        valores["nombre"] = nombre
    for k, v in valores.items():
        setattr(obj, k, v.strip() if isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return obj


class EstadoContratistaIn(BaseModel):
    activo: bool


@router.put("/contratistas/{contratista_id}/estado", response_model=ContratistaResponse)
async def cambiar_estado_contratista(
    contratista_id: int, data: EstadoContratistaIn, db: AsyncSession = Depends(get_db),
):
    """Activa o desactiva. Se separa del PUT para poder reactivar un contratista
    sin tener que reenviar toda su ficha."""
    obj = await db.get(EAMContratista, contratista_id)
    if obj is None:
        raise HTTPException(404, "Contratista no encontrado")
    obj.activo = data.activo
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/contratistas/{contratista_id}", status_code=204)
async def delete_contratista(contratista_id: int, db: AsyncSession = Depends(get_db)):
    """Borra el contratista. Si tiene ordenes de trabajo se desactiva: borrarlo
    dejaria esas ordenes sin a quien atribuirlas."""
    obj = await db.get(EAMContratista, contratista_id)
    if obj is None:
        raise HTTPException(404, "Contratista no encontrado")
    r = await db.execute(select(func.count()).select_from(EAMOrdenTrabajo).where(
        EAMOrdenTrabajo.contratista_id == contratista_id))
    ots = r.scalar() or 0
    if ots > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj); await db.commit()


# ─── Activos ──────────────────────────────────────────────────────────────────

@router.get("/activos", response_model=List[ActivoResponse])
async def list_activos(
    tipo_activo: Optional[str] = None,
    estado: Optional[str] = None,
    criticidad: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(EAMActivo).where(EAMActivo.activo == True)
    if tipo_activo:
        q = q.where(EAMActivo.tipo_activo == tipo_activo)
    if estado:
        q = q.where(EAMActivo.estado == estado)
    if criticidad:
        q = q.where(EAMActivo.criticidad == criticidad)
    result = await db.execute(q)
    return result.scalars().all()

@router.get("/vehiculos-combinados", response_model=List[VehiculoCombinadoResponse])
async def list_vehiculos_combinados(
    flota: Optional[str] = None,        # PROPIA | EXTERNA
    usa_llantas: Optional[bool] = None,  # filtra PROPIA por el catálogo de tipos; TMS/Flota siempre son vehículo
    db: AsyncSession = Depends(get_db),
):
    """Tabla unificada de vehículos: flota PROPIA (activos EAM/CMMS con placa)
    + flota EXTERNA (vehículos registrados en TMS y en Gestión de Flotas).
    Los de origen EAM que ya son espejo de uno externo (origen != 'EAM') no se
    repiten como PROPIA — figuran como el externo, con `activo_id` ya resuelto."""
    filas: List[VehiculoCombinadoResponse] = []
    tipos_con_llantas: set = set()
    if usa_llantas:
        r = await db.execute(select(EAMTipoActivo.codigo).where(EAMTipoActivo.usa_llantas == True))
        tipos_con_llantas = {c for c, in r.all()}

    espejos: dict[tuple, EAMActivo] = {}
    if flota in (None, "PROPIA"):
        # Para la vista de flota se exige placa (es un listado de vehículos), pero
        # cuando se piden los que usan llantas el criterio válido es el tipo de
        # activo: un montacargas o equipo de patio lleva llantas y no tiene placa.
        q_propia = select(EAMActivo).where(EAMActivo.activo == True)
        if not usa_llantas:
            q_propia = q_propia.where(EAMActivo.placa.isnot(None))
        res = await db.execute(q_propia)
        for a in res.scalars().all():
            if a.origen and a.origen != "EAM" and a.origen_id:
                espejos[(a.origen, a.origen_id)] = a
                continue   # es espejo de un externo: se representa como TMS/FLOTA, no como PROPIA
            if usa_llantas and a.tipo_activo not in tipos_con_llantas:
                continue
            filas.append(VehiculoCombinadoResponse(
                origen="EAM", flota="PROPIA", id=a.id, activo_id=a.id,
                codigo=a.codigo, nombre=a.nombre, placa=a.placa, tipo=a.tipo_activo,
                marca=a.marca, modelo=a.modelo, anio=a.anio, numero_ejes=a.numero_ejes,
                layout_llantas=a.layout_llantas, tiene_repuesto=a.tiene_repuesto,
                capacidad_kg=a.capacidad_combustible, estado=a.estado,
                motor_marca=a.motor_marca, motor_linea=a.motor_linea, motor_cc=a.motor_cc,
                propietario=a.responsable,
            ))
    if flota in (None, "EXTERNA"):
        res = await db.execute(select(TMSVehiculo).where(TMSVehiculo.deleted_at.is_(None)))
        for v in res.scalars().all():
            espejo = espejos.get(("TMS", v.id))
            filas.append(VehiculoCombinadoResponse(
                origen="TMS", flota="EXTERNA", id=v.id, activo_id=espejo.id if espejo else None,
                placa=v.placa, tipo=v.tipo_vehiculo.value if v.tipo_vehiculo else None,
                marca=v.marca, modelo=v.modelo, anio=v.anio,
                numero_ejes=espejo.numero_ejes if espejo else v.num_ejes,
                layout_llantas=espejo.layout_llantas if espejo else None,
                tiene_repuesto=espejo.tiene_repuesto if espejo else None,
                capacidad_kg=v.capacidad_kg,
                estado=v.estado_operativo.value if v.estado_operativo else None,
                propietario=v.propietario,
            ))
        res = await db.execute(
            select(FlotaVehiculo)
            .options(selectinload(FlotaVehiculo.marca), selectinload(FlotaVehiculo.tipo_vehiculo))
            .where(FlotaVehiculo.deleted_at.is_(None))
        )
        for v in res.scalars().all():
            espejo = espejos.get(("FLOTA", v.id))
            filas.append(VehiculoCombinadoResponse(
                origen="FLOTA", flota="EXTERNA", id=v.id, activo_id=espejo.id if espejo else None,
                placa=v.placa, tipo=v.tipo_vehiculo.nombre if v.tipo_vehiculo else None,
                marca=v.marca.nombre if v.marca else None, modelo=str(v.modelo) if v.modelo else None,
                numero_ejes=espejo.numero_ejes if espejo else None,
                layout_llantas=espejo.layout_llantas if espejo else None,
                tiene_repuesto=espejo.tiene_repuesto if espejo else None,
                estado="BAJA" if v.fecha_baja else "OPERATIVO",
            ))
    return filas


@router.post("/activos/vincular-externo", response_model=ActivoResponse)
async def vincular_activo_externo(data: VincularExternoRequest, db: AsyncSession = Depends(get_db)):
    """Crea (o devuelve, si ya existe) el activo EAM 'espejo' de un vehículo
    registrado originalmente en TMS o en Gestión de Flotas — para poder llevarle
    historial de mantenimiento/neumáticos sin duplicar su registro maestro."""
    origen = data.origen.upper()
    if origen not in ("TMS", "FLOTA"):
        raise HTTPException(400, "Origen inválido, debe ser TMS o FLOTA")

    existente_r = await db.execute(
        select(EAMActivo).where(EAMActivo.origen == origen, EAMActivo.origen_id == data.origen_id)
    )
    existente = existente_r.scalar_one_or_none()
    if existente:
        return existente

    if origen == "TMS":
        fuente = await db.get(TMSVehiculo, data.origen_id)
        if not fuente:
            raise HTTPException(404, "Vehículo TMS no encontrado")
        placa, marca, modelo, numero_ejes = fuente.placa, fuente.marca, fuente.modelo, fuente.num_ejes
    else:
        r = await db.execute(
            select(FlotaVehiculo).options(selectinload(FlotaVehiculo.marca))
            .where(FlotaVehiculo.id == data.origen_id)
        )
        fuente = r.scalar_one_or_none()
        if not fuente:
            raise HTTPException(404, "Vehículo de Flota no encontrado")
        placa = fuente.placa
        marca = fuente.marca.nombre if fuente.marca else None
        modelo = str(fuente.modelo) if fuente.modelo else None
        numero_ejes = None

    codigo = f"{origen}-{placa or data.origen_id}"
    obj = EAMActivo(
        codigo=codigo, nombre=f"Vehículo {placa or data.origen_id}", tipo_activo="VEHICULO",
        placa=placa, marca=marca, modelo=modelo, numero_ejes=numero_ejes,
        origen=origen, origen_id=data.origen_id,
    )
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ── Catálogo de tipos de activo (jerarquía: qué tipos usan llantas) ──
@router.get("/tipos-activo", response_model=List[TipoActivoResponse])
async def list_tipos_activo(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMTipoActivo).where(EAMTipoActivo.activo == True).order_by(EAMTipoActivo.nombre))
    return r.scalars().all()

@router.post("/tipos-activo", response_model=TipoActivoResponse)
async def crear_tipo_activo(data: TipoActivoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMTipoActivo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/tipos-activo/{tid}", response_model=TipoActivoResponse)
async def actualizar_tipo_activo(tid: int, data: TipoActivoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMTipoActivo, tid)
    if not obj:
        raise HTTPException(404, "Tipo de activo no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/tipos-activo/{tid}", status_code=204)
async def desactivar_tipo_activo(tid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMTipoActivo, tid)
    if obj:
        obj.activo = False
        await db.commit()

# Prefijo del codigo por tipo de activo. Lo que no este aca usa ACT.
PREFIJO_CODIGO_ACTIVO = {
    "VEHICULO": "VEH", "REMOLQUE": "REM", "MOTOCICLETA": "MOT",
    "MONTACARGAS": "MON", "EQUIPO_PATIO": "EQP",
    "INFRAESTRUCTURA": "INF", "BODEGA": "BOD", "EDIFICACION": "EDI",
}


async def _generar_codigo_activo(db: AsyncSession, tipo_activo: Optional[str]) -> str:
    """Codigo consecutivo por tipo: VEH-0001, MON-0001…

    Se busca el mayor consecutivo ya usado con ese prefijo en lugar de contar
    filas, para que borrar un activo no haga que el siguiente repita un codigo.
    """
    prefijo = PREFIJO_CODIGO_ACTIVO.get((tipo_activo or "").upper(), "ACT")
    r = await db.execute(select(EAMActivo.codigo).where(
        EAMActivo.codigo.like("%s-%%" % prefijo)))
    mayor = 0
    for (codigo,) in r.all():
        sufijo = (codigo or "").split("-")[-1]
        if sufijo.isdigit():
            mayor = max(mayor, int(sufijo))
    return "%s-%04d" % (prefijo, mayor + 1)


def _componer_nombre_activo(valores: dict, codigo: str) -> str:
    """Nombre legible a partir de la ficha tecnica.

    El alta ya no pide un nombre: con marca, linea, placa y ano se arma algo mas
    util y mas uniforme que lo que se escribiria a mano.
    """
    partes = [p for p in [valores.get("marca"), valores.get("linea")] if p]
    etiqueta = " ".join(partes)
    placa = valores.get("placa")
    anio = valores.get("anio")
    if placa:
        etiqueta = "%s %s" % (etiqueta, placa) if etiqueta else str(placa)
    elif anio:
        etiqueta = "%s %s" % (etiqueta, anio) if etiqueta else str(anio)
    return etiqueta.strip() or codigo


@router.post("/activos", response_model=ActivoResponse)
async def create_activo(data: ActivoCreate, db: AsyncSession = Depends(get_db)):
    valores = data.model_dump()
    try:
        await _resolver_catalogo_activo(db, valores)
    except ValueError as e:
        raise HTTPException(400, str(e))

    codigo = (valores.get("codigo") or "").strip()
    if not codigo:
        codigo = await _generar_codigo_activo(db, valores.get("tipo_activo"))
    else:
        rc = await db.execute(select(EAMActivo).where(EAMActivo.codigo == codigo))
        if rc.scalar_one_or_none() is not None:
            raise HTTPException(400, "El codigo '%s' ya esta registrado." % codigo)
    valores["codigo"] = codigo
    if not (valores.get("nombre") or "").strip():
        valores["nombre"] = _componer_nombre_activo(valores, codigo)

    obj = EAMActivo(**valores)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/activos/{activo_id}", response_model=ActivoResponse)
async def get_activo(activo_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMActivo, activo_id)
    if not obj:
        raise HTTPException(404, "Activo no encontrado")
    return obj

@router.put("/activos/{activo_id}", response_model=ActivoResponse)
async def update_activo(activo_id: int, data: ActivoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMActivo, activo_id)
    if not obj:
        raise HTTPException(404, "Activo no encontrado")
    valores = data.model_dump(exclude_unset=True)
    # Se valida sobre la jerarquia completa, no solo sobre lo que llego: cambiar
    # la marca sin cambiar la linea dejaria una combinacion que no existe.
    if any(c in valores for c in ("marca", "linea", "modelo", "tipo_activo")):
        completo = {
            "marca": valores.get("marca", obj.marca),
            "linea": valores.get("linea", obj.linea),
            "modelo": valores.get("modelo", obj.modelo),
            "tipo_activo": valores.get("tipo_activo", obj.tipo_activo),
            "motor_marca": valores.get("motor_marca", obj.motor_marca),
            "motor_linea": valores.get("motor_linea", obj.motor_linea),
            "motor_cc": valores.get("motor_cc", obj.motor_cc),
            "tipo_combustible": valores.get("tipo_combustible", obj.tipo_combustible),
            "capacidad_combustible": valores.get("capacidad_combustible", obj.capacidad_combustible),
            "numero_ejes": valores.get("numero_ejes", obj.numero_ejes),
            "vida_util_anios": valores.get("vida_util_anios", obj.vida_util_anios),
            "vida_util_km": valores.get("vida_util_km", obj.vida_util_km),
        }
        try:
            await _resolver_catalogo_activo(db, completo)
        except ValueError as e:
            raise HTTPException(400, str(e))
        valores.update(completo)
    for k, v in valores.items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/activos/{activo_id}", status_code=204)
async def delete_activo(activo_id: int, db: AsyncSession = Depends(get_db)):
    """Baja lógica del activo (activo=False): conserva el histórico de órdenes de
    trabajo, movimientos de neumáticos y demás registros que lo referencian.
    Se bloquea si todavía tiene llantas montadas u órdenes de trabajo abiertas,
    para no dejar registros huérfanos apuntando a un activo dado de baja."""
    obj = await db.get(EAMActivo, activo_id)
    if not obj:
        raise HTTPException(404, "Activo no encontrado")

    r = await db.execute(
        select(func.count()).select_from(EAMNeumatico)
        .where(EAMNeumatico.activo_id == activo_id, EAMNeumatico.estado == "INSTALADO")
    )
    montadas = r.scalar() or 0
    if montadas:
        raise HTTPException(409, f"El activo tiene {montadas} llanta(s) montada(s). Desmóntalas antes de darlo de baja.")

    r = await db.execute(
        select(func.count()).select_from(EAMOrdenTrabajo)
        # COMPLETADA es el estado final real; CERRADA queda por datos viejos.
        .where(EAMOrdenTrabajo.activo_id == activo_id,
               EAMOrdenTrabajo.estado.notin_(["COMPLETADA", "CERRADA", "CANCELADA"]))
    )
    ots_abiertas = r.scalar() or 0
    if ots_abiertas:
        raise HTTPException(409, f"El activo tiene {ots_abiertas} orden(es) de trabajo abierta(s). Ciérralas o cancélalas antes de darlo de baja.")

    obj.activo = False
    await db.commit()


@router.get("/activos/{activo_id}/componentes", response_model=List[ComponenteResponse])
async def get_componentes_activo(activo_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMComponente).where(EAMComponente.activo_id == activo_id))
    return result.scalars().all()

@router.post("/activos/{activo_id}/componentes", response_model=ComponenteResponse)
async def add_componente(activo_id: int, data: ComponenteCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMComponente(**{**data.model_dump(), "activo_id": activo_id})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ─── Checklists ───────────────────────────────────────────────────────────────

@router.get("/checklists/plantillas", response_model=List[ChecklistPlantillaResponse])
async def list_plantillas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMChecklistPlantilla).where(EAMChecklistPlantilla.activo == True))
    return result.scalars().all()

@router.post("/checklists/plantillas", response_model=ChecklistPlantillaResponse)
async def create_plantilla(data: ChecklistPlantillaCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMChecklistPlantilla(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/checklists/plantillas/{plantilla_id}/preguntas", response_model=List[ChecklistPreguntaResponse])
async def list_preguntas(plantilla_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EAMChecklistPregunta)
        .where(and_(EAMChecklistPregunta.plantilla_id == plantilla_id, EAMChecklistPregunta.activo == True))
        .order_by(EAMChecklistPregunta.orden)
    )
    return result.scalars().all()

@router.post("/checklists/plantillas/{plantilla_id}/preguntas", response_model=ChecklistPreguntaResponse)
async def add_pregunta(plantilla_id: int, data: ChecklistPreguntaCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMChecklistPregunta(**{**data.model_dump(), "plantilla_id": plantilla_id})
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/checklists/ejecuciones", response_model=List[ChecklistEjecucionResponse])
async def list_ejecuciones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EAMChecklistEjecucion).order_by(EAMChecklistEjecucion.id.desc()).limit(100))
    return result.scalars().all()

@router.post("/checklists/ejecuciones", response_model=ChecklistEjecucionResponse)
async def create_ejecucion(data: ChecklistEjecucionCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMChecklistEjecucion(**data.model_dump(), estado="EN_CURSO")
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ─── Planes de mantenimiento ──────────────────────────────────────────────────

def _cumplimiento(
    plan: EAMPlanMantenimiento, activo: EAMActivo, prog: Optional[EAMPlanActivo]
) -> CumplimientoActivo:
    """Cuánto le falta a un activo para su próxima rutina, contra su lectura de
    hoy.

    Se calcula al vuelo y no se guarda: el activo sigue rodando entre una OT y
    la siguiente, así que un valor almacenado nacería viejo.
    """
    base = CumplimientoActivo(
        plan_id=plan.id, plan_nombre=plan.nombre,
        frecuencia=plan.frecuencia, unidad=plan.unidad, tipo_ot=plan.tipo_ot,
        activo_id=activo.id, activo_codigo=activo.codigo, activo_nombre=activo.nombre,
        odometro_activo=activo.odometro_actual, horometro_activo=activo.horometro_actual,
        tareas=[PlanTareaItem.model_validate(t) for t in sorted(plan.tareas, key=lambda x: x.orden or 0)],
        repuestos=[PlanRepuestoItem.model_validate(r) for r in sorted(plan.repuestos, key=lambda x: x.orden or 0)],
    )
    if prog is None or prog.ultima_ejecucion_fecha is None:
        return base

    base.ultima_ejecucion_fecha = prog.ultima_ejecucion_fecha
    base.ultima_ejecucion_odometro = prog.ultima_ejecucion_odometro
    base.ultima_ot_id = prog.ultima_ot_id
    base.proxima_fecha = prog.proxima_fecha
    base.proximo_odometro = prog.proximo_odometro
    base.proximo_horometro = prog.proximo_horometro

    frecuencia = plan.frecuencia or 0
    if prog.proximo_odometro is not None:
        faltante = prog.proximo_odometro - (activo.odometro_actual or 0)
        unidad = "KM"
    elif prog.proximo_horometro is not None:
        faltante = prog.proximo_horometro - (activo.horometro_actual or 0)
        unidad = "HORAS"
    elif prog.proxima_fecha is not None:
        faltante = (prog.proxima_fecha - datetime.now()).days
        unidad = "DIAS"
        frecuencia = frecuencia * _DIAS_POR_UNIDAD.get((plan.unidad or "").upper(), 1)
    else:
        return base

    # Se avisa en el último 10% del intervalo, con un mínimo razonable para que
    # una frecuencia corta no deje la alerta en cero.
    umbral = max(frecuencia * 0.1, 1 if unidad == "DIAS" else 50)
    base.faltante = round(faltante, 1)
    base.unidad_faltante = unidad
    base.estado_rutina = "VENCIDA" if faltante < 0 else ("PROXIMA" if faltante <= umbral else "AL_DIA")
    return base


async def _cobertura(
    db: AsyncSession, planes: List[EAMPlanMantenimiento]
) -> dict[int, List[CumplimientoActivo]]:
    """Qué activos cubre cada rutina y cómo va cada uno.

    Se resuelve en memoria: el alcance compara texto por niveles y la flota de
    un CMMS cabe de sobra, así que no vale la pena armarlo en SQL.
    """
    if not planes:
        return {}
    activos = (await db.execute(select(EAMActivo))).scalars().all()
    progs = (await db.execute(
        select(EAMPlanActivo).where(EAMPlanActivo.plan_id.in_([p.id for p in planes]))
    )).scalars().all()
    por_clave = {(p.plan_id, p.activo_id): p for p in progs}

    salida: dict[int, List[CumplimientoActivo]] = {}
    for plan in planes:
        cubiertos = [a for a in activos if _plan_cubre(plan, a)]
        salida[plan.id] = [
            _cumplimiento(plan, a, por_clave.get((plan.id, a.id))) for a in cubiertos
        ]
    return salida


@router.get("/planes", response_model=List[PlanMantenimientoResponse])
async def list_planes(db: AsyncSession = Depends(get_db)):
    planes = (await db.execute(
        select(EAMPlanMantenimiento).where(EAMPlanMantenimiento.activo == True)
        .order_by(EAMPlanMantenimiento.nombre)
    )).scalars().all()
    cobertura = await _cobertura(db, planes)

    salida = []
    for p in planes:
        filas = cobertura.get(p.id, [])
        salida.append(PlanMantenimientoResponse.model_validate(p).model_copy(update={
            **_costos_plan(p),
            "activos_cubiertos": len(filas),
            "vencidas": sum(1 for f in filas if f.estado_rutina == "VENCIDA"),
            "proximas": sum(1 for f in filas if f.estado_rutina == "PROXIMA"),
            "sin_ejecutar": sum(1 for f in filas if f.estado_rutina == "SIN_EJECUTAR"),
        }))
    return salida


@router.get("/planes/cumplimiento", response_model=List[CumplimientoActivo])
async def cumplimiento_rutinas(
    activo_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Una fila por (rutina, activo cubierto).

    Con `activo_id` devuelve las rutinas que le aplican a ese equipo — es lo que
    consulta el formulario de la OT — y con `plan_id`, la flota que cubre una
    rutina.
    """
    q = select(EAMPlanMantenimiento).where(EAMPlanMantenimiento.activo == True)
    if plan_id is not None:
        q = q.where(EAMPlanMantenimiento.id == plan_id)
    planes = (await db.execute(q)).scalars().all()
    cobertura = await _cobertura(db, planes)

    filas = [f for lista in cobertura.values() for f in lista]
    if activo_id is not None:
        filas = [f for f in filas if f.activo_id == activo_id]
    # Primero lo que ya se pasó, después lo que está por vencer.
    orden = {"VENCIDA": 0, "PROXIMA": 1, "SIN_EJECUTAR": 2, "AL_DIA": 3}
    filas.sort(key=lambda f: (orden.get(f.estado_rutina, 9), f.faltante if f.faltante is not None else 1e12))
    return filas


@router.delete("/planes/{plan_id}", status_code=204)
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMPlanMantenimiento, plan_id)
    if not obj or not obj.activo:
        raise HTTPException(404, "Plan no encontrado")
    # Baja lógica: las OTs ya hechas apuntan al plan por id.
    obj.activo = False
    await db.commit()

def _aplicar_detalle(obj: EAMPlanMantenimiento, data: PlanMantenimientoCreate) -> None:
    """Se reemplaza completo, igual que las líneas de la OT: el formulario manda
    trabajos y repuestos enteros."""
    obj.tareas.clear()
    for i, t in enumerate(data.tareas):
        obj.tareas.append(EAMPlanDetalle(
            descripcion=t.descripcion, actividad_id=t.actividad_id,
            tiempo_estimado=t.tiempo_estimado, costo_mano_obra=t.costo_mano_obra or 0,
            orden=t.orden or i,
        ))
    obj.repuestos.clear()
    for i, r in enumerate(data.repuestos):
        obj.repuestos.append(EAMPlanRepuesto(
            repuesto_id=r.repuesto_id, descripcion=r.descripcion,
            cantidad=r.cantidad or 0, unidad=r.unidad,
            costo_unitario=r.costo_unitario or 0, orden=r.orden or i,
        ))


def _costos_plan(plan: EAMPlanMantenimiento) -> dict:
    mo = sum(t.costo_mano_obra or 0 for t in plan.tareas)
    rep = sum((r.cantidad or 0) * (r.costo_unitario or 0) for r in plan.repuestos)
    return {"costo_mano_obra": mo, "costo_repuestos": rep, "costo_calculado": mo + rep}


def _validar_alcance(data: PlanMantenimientoCreate) -> None:
    if not data.activo_id and not (data.tipo_activo or data.marca or data.linea):
        raise HTTPException(
            400,
            "Defina el alcance de la rutina: un activo puntual, o al menos el "
            "tipo de activo al que aplica",
        )


async def _con_cobertura(
    db: AsyncSession, plan: EAMPlanMantenimiento
) -> PlanMantenimientoResponse:
    filas = (await _cobertura(db, [plan])).get(plan.id, [])
    return PlanMantenimientoResponse.model_validate(plan).model_copy(update={
        **_costos_plan(plan),
        "activos_cubiertos": len(filas),
        "vencidas": sum(1 for f in filas if f.estado_rutina == "VENCIDA"),
        "proximas": sum(1 for f in filas if f.estado_rutina == "PROXIMA"),
        "sin_ejecutar": sum(1 for f in filas if f.estado_rutina == "SIN_EJECUTAR"),
    })


@router.post("/planes", response_model=PlanMantenimientoResponse)
async def create_plan(data: PlanMantenimientoCreate, db: AsyncSession = Depends(get_db)):
    _validar_alcance(data)
    obj = EAMPlanMantenimiento(**data.model_dump(exclude={"tareas", "repuestos"}))
    _aplicar_detalle(obj, data)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return await _con_cobertura(db, obj)

@router.put("/planes/{plan_id}", response_model=PlanMantenimientoResponse)
async def update_plan(plan_id: int, data: PlanMantenimientoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMPlanMantenimiento, plan_id)
    if not obj:
        raise HTTPException(404, "Plan no encontrado")
    _validar_alcance(data)
    for k, v in data.model_dump(exclude={"tareas", "repuestos"}).items():
        setattr(obj, k, v)
    _aplicar_detalle(obj, data)
    await db.commit(); await db.refresh(obj)
    return await _con_cobertura(db, obj)


# ─── Órdenes de trabajo ───────────────────────────────────────────────────────

@router.get("/ots", response_model=List[OTResponse])
async def list_ots(
    estado: Optional[str] = None,
    tipo_ot: Optional[str] = None,
    activo_id: Optional[int] = None,
    prioridad: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(EAMOrdenTrabajo).order_by(EAMOrdenTrabajo.id.desc())
    if estado:
        q = q.where(EAMOrdenTrabajo.estado == estado)
    if tipo_ot:
        q = q.where(EAMOrdenTrabajo.tipo_ot == tipo_ot)
    if activo_id:
        q = q.where(EAMOrdenTrabajo.activo_id == activo_id)
    if prioridad:
        q = q.where(EAMOrdenTrabajo.prioridad == prioridad)
    result = await db.execute(q.limit(200))
    return result.scalars().all()

async def _generar_numero_ot(db: AsyncSession) -> str:
    """Consecutivo del año. Se toma el sufijo más alto, no la cantidad de OTs:
    contando, la primera OT borrada repite número y choca con el UNIQUE."""
    anio = datetime.now().year
    patron = f"OT-{anio}-"
    r = await db.execute(
        select(EAMOrdenTrabajo.numero).where(EAMOrdenTrabajo.numero.like(f"{patron}%"))
    )
    maximo = 0
    for (numero,) in r.all():
        sufijo = (numero or "")[len(patron):]
        if sufijo.isdigit():
            maximo = max(maximo, int(sufijo))
    return f"{patron}{maximo + 1:04d}"


async def _validar_activo(db: AsyncSession, activo_id: int) -> EAMActivo:
    activo = await db.get(EAMActivo, activo_id)
    if not activo:
        raise HTTPException(400, f"El activo {activo_id} no existe")
    return activo


def _avanzar_medidores(activo: EAMActivo, odometro, horometro) -> None:
    """Lleva al activo la lectura tomada en la OT.

    Solo hacia adelante: un odómetro no retrocede, así que un dígito de más
    escrito por error no puede dejar al activo con un kilometraje menor del que
    ya tenía — y de paso evita que una OT vieja capturada tarde pise la lectura
    buena.
    """
    if odometro is not None and odometro > (activo.odometro_actual or 0):
        activo.odometro_actual = odometro
    if horometro is not None and horometro > (activo.horometro_actual or 0):
        activo.horometro_actual = horometro


# Cada unidad del plan se proyecta sobre un medidor distinto.
_DIAS_POR_UNIDAD = {"DIAS": 1, "SEMANAS": 7, "MESES": 30, "ANIOS": 365, "AÑOS": 365}


def _plan_cubre(plan: EAMPlanMantenimiento, activo: EAMActivo) -> bool:
    """¿La rutina aplica a este activo?

    Si nombra un activo puntual, manda ese. Si no, se comparan los niveles
    declarados — tipo, marca, línea — y el nivel que esté vacío no restringe:
    una rutina con solo el tipo cubre a todos los vehículos, y agregarle la
    marca la acota a esa marca.
    """
    if plan.activo_id:
        return plan.activo_id == activo.id
    niveles = (
        (plan.tipo_activo, activo.tipo_activo),
        (plan.marca, activo.marca),
        (plan.linea, activo.linea),
    )
    declarado = False
    for esperado, real in niveles:
        if not esperado:
            continue
        declarado = True
        if (real or "").strip().upper() != esperado.strip().upper():
            return False
    # Sin ningún nivel ni activo, la rutina no cubre a nadie: es más seguro que
    # aplicarla a toda la planta por un campo que se olvidaron de llenar.
    return declarado


async def _programacion(
    db: AsyncSession, plan_id: int, activo_id: int, crear: bool = False
) -> Optional[EAMPlanActivo]:
    r = await db.execute(
        select(EAMPlanActivo).where(
            EAMPlanActivo.plan_id == plan_id, EAMPlanActivo.activo_id == activo_id
        )
    )
    prog = r.scalar_one_or_none()
    if prog is None and crear:
        prog = EAMPlanActivo(plan_id=plan_id, activo_id=activo_id)
        db.add(prog)
    return prog


async def _sellar_rutina(db: AsyncSession, ot: EAMOrdenTrabajo, activo: EAMActivo) -> None:
    """Cierra la rutina que la OT vino a cumplir, para ese activo, y calcula la
    siguiente.

    Se dispara solo cuando la OT queda COMPLETADA: una rutina cuenta como
    cumplida cuando el trabajo se hizo, no cuando se programó. El cumplimiento
    se guarda contra el activo de la OT y no contra el plan, porque la misma
    rutina cubre a varios equipos y cada uno vence por su cuenta.

    La base del cálculo es la lectura de la OT; si no trae, se usa la del
    activo, que ya viene de la última OT registrada.
    """
    if not ot.plan_id or (ot.estado or "").upper() != "COMPLETADA":
        return
    plan = await db.get(EAMPlanMantenimiento, ot.plan_id)
    if not plan:
        return
    prog = await _programacion(db, plan.id, activo.id, crear=True)

    fecha = ot.fecha_fin or datetime.now()
    odometro = ot.odometro if ot.odometro is not None else activo.odometro_actual
    horometro = ot.horometro if ot.horometro is not None else activo.horometro_actual

    prog.ultima_ejecucion_fecha = fecha
    prog.ultima_ejecucion_odometro = odometro
    prog.ultima_ejecucion_horometro = horometro
    prog.ultima_ot_id = ot.id

    unidad = (plan.unidad or "").upper()
    frecuencia = plan.frecuencia or 0
    # Se limpia lo que no aplique, para que no queden vencimientos viejos de
    # cuando el plan se medía de otra forma.
    prog.proximo_odometro = None
    prog.proximo_horometro = None
    prog.proxima_fecha = None
    if frecuencia <= 0:
        return
    if unidad == "KM":
        prog.proximo_odometro = (odometro or 0) + frecuencia
    elif unidad == "HORAS":
        prog.proximo_horometro = (horometro or 0) + frecuencia
    elif unidad in _DIAS_POR_UNIDAD:
        prog.proxima_fecha = fecha + timedelta(days=frecuencia * _DIAS_POR_UNIDAD[unidad])


def _recalcular_costos(obj: EAMOrdenTrabajo) -> None:
    """La mano de obra y los repuestos salen de las líneas, no se escriben a
    mano: así el total de la OT siempre cuadra con su detalle."""
    obj.costo_mano_obra = sum(t.costo_total or 0 for t in obj.trabajos)
    obj.costo_repuestos = sum(r.costo_total or 0 for r in obj.repuestos)
    obj.costo_total = (
        (obj.costo_mano_obra or 0) + (obj.costo_repuestos or 0) + (obj.costo_servicios or 0)
    )


def _aplicar_lineas(obj: EAMOrdenTrabajo, data: OTCreate) -> None:
    """Las líneas se reemplazan completas: el formulario manda el detalle
    entero, así que reconciliar fila por fila solo agregaría estados raros."""
    obj.trabajos.clear()
    obj.repuestos.clear()
    for t in data.trabajos:
        # Si vienen horas y tarifa, manda el producto; si no, el costo suelto.
        costo = t.costo_total or 0
        if t.horas and t.tarifa_hora:
            costo = t.horas * t.tarifa_hora
        obj.trabajos.append(EAMOTManoObra(
            actividad=t.actividad,
            # El técnico solo aplica al taller interno: si la línea la hizo un
            # contratista, guardar además un técnico propio confunde el reporte.
            tecnico=None if t.contratista_id else t.tecnico,
            contratista_id=t.contratista_id,
            tipo_trabajo_id=t.tipo_trabajo_id,
            sistema=t.sistema, subsistema=t.subsistema,
            horas=t.horas, tarifa_hora=t.tarifa_hora, costo_total=costo,
            observaciones=t.observaciones,
        ))
    for r in data.repuestos:
        cantidad = r.cantidad or 0
        obj.repuestos.append(EAMOTMaterial(
            repuesto_id=r.repuesto_id, descripcion=r.descripcion,
            contratista_id=r.contratista_id,
            bodega_id=getattr(r, "bodega_id", None),
            cantidad=cantidad, unidad=r.unidad, costo_unit=r.costo_unit or 0,
            costo_total=cantidad * (r.costo_unit or 0),
        ))


def _payload_ot(data: OTCreate) -> dict:
    """El técnico responsable es del taller interno. Si la OT se le entrega a un
    contratista, se descarta para que no queden los dos responsables a la vez."""
    payload = data.model_dump(exclude={"trabajos", "repuestos", "numero"})
    if payload.get("contratista_id"):
        payload["tecnico_asignado"] = None
    return payload


@router.post("/ots", response_model=OTResponse)
async def create_ot(data: OTCreate, db: AsyncSession = Depends(get_db)):
    activo = await _validar_activo(db, data.activo_id)
    obj = EAMOrdenTrabajo(**_payload_ot(data))
    obj.numero = data.numero or await _generar_numero_ot(db)
    _aplicar_lineas(obj, data)
    _recalcular_costos(obj)
    db.add(obj)
    # La lectura de la OT es la fuente del kilometraje del activo.
    _avanzar_medidores(activo, obj.odometro, obj.horometro)
    await db.flush()          # para que la rutina pueda guardar ultima_ot_id
    await _sellar_rutina(db, obj, activo)
    # El material sale de la bodega al quedar en la orden. Se reconcilia en vez
    # de descontar a secas: las lineas se reconstruyen en cada guardado, asi que
    # descontar sin comparar duplicaria la salida en la segunda edicion.
    await sincronizar_orden(db, obj)
    await db.commit(); await db.refresh(obj)
    return obj

@router.get("/ots/{ot_id}", response_model=OTResponse)
async def get_ot(ot_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMOrdenTrabajo, ot_id)
    if not obj:
        raise HTTPException(404, "OT no encontrada")
    return obj

@router.put("/ots/{ot_id}", response_model=OTResponse)
async def update_ot(ot_id: int, data: OTCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMOrdenTrabajo, ot_id)
    if not obj:
        raise HTTPException(404, "OT no encontrada")
    activo = await _validar_activo(db, data.activo_id)
    for k, v in _payload_ot(data).items():
        setattr(obj, k, v)
    _aplicar_lineas(obj, data)
    _recalcular_costos(obj)
    _avanzar_medidores(activo, obj.odometro, obj.horometro)
    await _sellar_rutina(db, obj, activo)
    await db.flush()
    await sincronizar_orden(db, obj)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/ots/{ot_id}", status_code=204)
async def delete_ot(ot_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMOrdenTrabajo, ot_id)
    if not obj:
        raise HTTPException(404, "OT no encontrada")
    # El material vuelve a la bodega. Dejarlo descontado convertiria el
    # inventario en un faltante permanente que nadie puede explicar.
    await revertir_orden(db, ot_id)
    # Una inspeccion que reprueba genera su orden y guarda a cual apunta. Si
    # despues se borra la orden, esa referencia queda colgando y el borrado
    # reventaba con un 500 sin decir por que. Se suelta el vinculo: la
    # inspeccion conserva su propio registro y la orden se puede borrar.
    await db.execute(
        update(ChkEjecucion).where(ChkEjecucion.ot_id == ot_id).values(ot_id=None)
    )
    await db.delete(obj)
    await db.commit()

@router.put("/ots/{ot_id}/estado")
async def update_ot_estado(ot_id: int, data: OTEstadoUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMOrdenTrabajo, ot_id)
    if not obj:
        raise HTTPException(404, "OT no encontrada")
    obj.estado = data.estado
    if data.observaciones:
        obj.observaciones = data.observaciones
    if data.fecha_inicio:
        obj.fecha_inicio = data.fecha_inicio
    if data.fecha_fin:
        obj.fecha_fin = data.fecha_fin
    if data.tiempo_real_horas:
        obj.tiempo_real_horas = data.tiempo_real_horas
    # Mover la OT a COMPLETADA en el Kanban es la forma normal de cerrarla, así
    # que la rutina también se sella acá y no solo desde el formulario.
    activo = await db.get(EAMActivo, obj.activo_id)
    if activo:
        await _sellar_rutina(db, obj, activo)
    await db.commit(); await db.refresh(obj)
    return obj


# ─── Lubricación / Aceites ────────────────────────────────────────────────────

@router.get("/aceite/muestras", response_model=List[MuestraAceiteResponse])
async def list_muestras(activo_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(EAMMuestraAceite).order_by(EAMMuestraAceite.fecha_toma.desc())
    if activo_id:
        q = q.where(EAMMuestraAceite.activo_id == activo_id)
    result = await db.execute(q.limit(200))
    return result.scalars().all()

@router.post("/aceite/muestras", response_model=MuestraAceiteResponse)
async def create_muestra(data: MuestraAceiteCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMMuestraAceite(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ─── Neumáticos ───────────────────────────────────────────────────────────────

def _lado_suffixes(n: int) -> List[str]:
    """Sufijos de código para `n` llantas de un mismo lado de un eje, de afuera
    hacia adentro: 1→[''], 2→['-EXT','-INT'], 3→['-EXT','-INT2','-INT'], etc."""
    if n <= 0:
        return []
    if n == 1:
        return [""]
    if n == 2:
        return ["-EXT", "-INT"]
    return ["-EXT"] + [f"-INT{i}" for i in range(2, n)] + ["-INT"]


def _sufijo_label(suf: str) -> str:
    return "" if not suf else " " + suf.lstrip("-").replace("INT", "Int ").replace("EXT", "Ext").strip()


def _generar_posiciones(
    numero_ejes: Optional[int], tiene_repuesto: bool,
    layout: Optional[List[int]] = None, cantidad_repuestos: int = 1,
) -> List[dict]:
    """Layout de posiciones de neumáticos. Si `layout` trae la cantidad de
    llantas por cada eje (ej. [2,4,4]), genera posiciones a la medida de esa
    configuración real (soporta ejes simples, duales o con más llantas por
    lado). Si no, usa el patrón clásico: eje 1 direccional (2 llantas), ejes
    2..N duales (4 llantas) — se mantiene igual por compatibilidad con activos
    ya configurados antes de que existiera `layout`."""
    pos: List[dict] = []
    numero = 0

    def _add(codigo: str, label: str, eje: int, lado: str) -> None:
        nonlocal numero
        numero += 1
        pos.append({"codigo": codigo, "label": f"Pos. {numero} · {label}", "eje": eje, "lado": lado, "numero": numero})

    if layout:
        for eje, cantidad in enumerate(layout, start=1):
            izq = (cantidad + 1) // 2
            der = cantidad - izq
            for suf in _lado_suffixes(izq):
                _add(f"E{eje}-IZQ{suf}", f"Eje {eje} · Izq{_sufijo_label(suf)}", eje, "IZQ")
            for suf in reversed(_lado_suffixes(der)):
                _add(f"E{eje}-DER{suf}", f"Eje {eje} · Der{_sufijo_label(suf)}", eje, "DER")
    else:
        for eje in range(1, (numero_ejes or 0) + 1):
            if eje == 1:
                _add("E1-IZQ", "Eje 1 · Izq", 1, "IZQ")
                _add("E1-DER", "Eje 1 · Der", 1, "DER")
            else:
                _add(f"E{eje}-IZQ-EXT", f"Eje {eje} · Izq Ext", eje, "IZQ")
                _add(f"E{eje}-IZQ-INT", f"Eje {eje} · Izq Int", eje, "IZQ")
                _add(f"E{eje}-DER-INT", f"Eje {eje} · Der Int", eje, "DER")
                _add(f"E{eje}-DER-EXT", f"Eje {eje} · Der Ext", eje, "DER")

    if tiene_repuesto:
        for r in range(max(1, cantidad_repuestos)):
            codigo = "REPUESTO" if r == 0 else f"REPUESTO{r + 1}"
            label = "Repuesto" if r == 0 else f"Repuesto {r + 1}"
            pos.append({"codigo": codigo, "label": label, "eje": 0, "lado": "-", "numero": None})
    return pos


def _eje_de_posicion(posicion: str) -> Optional[int]:
    """Deduce el número de eje a partir del código de posición (E{n}-...)."""
    if not posicion:
        return None
    if posicion.upper().startswith("REPUESTO"):
        return 0
    if posicion.upper().startswith("E"):
        try:
            return int(posicion[1:].split("-")[0])
        except (ValueError, IndexError):
            return None
    return None


def _validar_montaje(tipo_uso: Optional[str], posicion: str) -> Optional[str]:
    """Valida que el tipo de uso de la llanta sea compatible con la posición.
    Regla (montaje estricto): DIRECCIONAL solo en eje 1; TRACCION/REMOLQUE no en eje 1.
    MULTIPOSICION y sin clasificar se permiten en cualquier posición."""
    uso = (tipo_uso or "").upper()
    eje = _eje_de_posicion(posicion)
    if eje is None or eje == 0:      # repuesto o desconocido: permitido
        return None
    if uso == "DIRECCIONAL" and eje != 1:
        return "Una llanta DIRECCIONAL solo puede montarse en el eje 1 (dirección)."
    if uso in ("TRACCION", "REMOLQUE") and eje == 1:
        return f"Una llanta {uso} no puede montarse en el eje 1 (dirección)."
    return None


ZONA_LOCAL = ZoneInfo("America/Bogota")


def _fecha_naive(fecha):
    """Deja la fecha sin zona horaria, en hora local de Colombia.

    El navegador manda la fecha en UTC (`...Z`) pero estas tablas la guardan sin
    zona, así que compararlas directamente revienta con "can't compare
    offset-naive and offset-aware datetimes". Se convierte a hora local antes de
    soltar la zona para que lo guardado coincida con la hora que el usuario
    escribió en pantalla.
    """
    if fecha is None or fecha.tzinfo is None:
        return fecha
    return fecha.astimezone(ZONA_LOCAL).replace(tzinfo=None)


def _validar_lectura(
    activo: "EAMActivo", neu: "EAMNeumatico", km: Optional[float], horas: Optional[float],
) -> Optional[str]:
    """La lectura no puede retroceder.

    Un odómetro no baja, así que un valor menor al que ya tiene el equipo —o al
    último registrado para la llanta— es un error de digitación. Se rechaza en
    vez de ignorarlo: aceptarlo deja el recorrido de la llanta en cero y el CPK
    sale mal, que es justo lo que estos registros existen para calcular.
    """
    for etiqueta, valor, actual_equipo, actual_llanta in (
        ("odómetro", km, activo.odometro_actual, neu.km_actual),
        ("horómetro", horas, activo.horometro_actual, None),
    ):
        if valor is None:
            continue
        if valor < 0:
            return f"El {etiqueta} no puede ser negativo."
        if actual_equipo is not None and valor < actual_equipo:
            return (
                f"El {etiqueta} registrado ({valor:,.0f}) es menor que el del equipo "
                f"({actual_equipo:,.0f}). Verifique la lectura."
            ).replace(",", ".")
        if actual_llanta is not None and valor < actual_llanta:
            return (
                f"El {etiqueta} registrado ({valor:,.0f}) es menor que el último de la "
                f"llanta {neu.codigo} ({actual_llanta:,.0f}). Verifique la lectura."
            ).replace(",", ".")
    return None


# Los tres surcos que se miden, con el nombre que se ve en pantalla. Va en un
# solo sitio para que el mensaje de error y el formulario digan lo mismo.
SURCOS = (
    ("profundidad_izq", "externo"),
    ("profundidad_centro", "centro"),
    ("profundidad_der", "interno"),
)


async def _referencia_profundidad(db: AsyncSession, neu: "EAMNeumatico") -> dict:
    """Contra qué se compara una profundidad nueva.

    No basta con «la última inspección»: hay dos operaciones donde la
    profundidad SUBE con toda razón y comparar contra lo anterior las
    rechazaría. Un reencauche pone banda nueva —y abre otra vida— y un
    reesculturado talla surco sobre la goma que quedaba. Así que la referencia
    es la última medición posterior a la más reciente de esas dos operaciones.

    Devuelve también la profundidad de diseño y la mínima de retiro, porque quien
    va a medir necesita las tres cosas a la vez: contra qué venía, de dónde
    partió y en qué punto hay que bajar la llanta.
    """
    # Desde cuándo vale comparar.
    vida = await _vida_abierta(db, neu.id)
    corte = vida.fecha_inicio if vida else None
    origen_corte = "reencauche" if vida and (vida.tipo or "").upper() == "REENCAUCHADA" else "inicio de vida"

    resc = (await db.execute(
        select(EAMReesculturado)
        .where(EAMReesculturado.neumatico_id == neu.id,
               EAMReesculturado.deshecho.is_(False))
        .order_by(EAMReesculturado.fecha.desc()).limit(1)
    )).scalar_one_or_none()
    if resc and (corte is None or resc.fecha > corte):
        corte, origen_corte = resc.fecha, "reesculturado"

    consulta = select(EAMInspeccionNeumatico).where(
        EAMInspeccionNeumatico.neumatico_id == neu.id)
    if corte is not None:
        consulta = consulta.where(EAMInspeccionNeumatico.fecha >= corte)
    insp = (await db.execute(
        consulta.order_by(EAMInspeccionNeumatico.fecha.desc()).limit(1)
    )).scalar_one_or_none()

    cfg = await _get_config_neu(db)
    base = {
        "profundidad_diseno": neu.profundidad_diseño,
        "profundidad_minima": cfg.profundidad_minima,
        "tolerancia": getattr(cfg, "tolerancia_profundidad", None) or 0.5,
        "reencauches": neu.reencauches or 0,
    }

    if insp is not None:
        return {
            **base, "origen": "inspección", "fecha": insp.fecha,
            "profundidad_izq": insp.profundidad_izq,
            "profundidad_centro": insp.profundidad_centro,
            "profundidad_der": insp.profundidad_der,
            "km_odometro": insp.km_odometro,
        }

    # Sin inspección posterior al corte, la referencia es la propia operación que
    # dejó la llanta con labrado nuevo.
    if corte is not None and resc is not None and origen_corte == "reesculturado":
        valor = resc.profundidad_nueva
        # Los TRES surcos quedan en el valor nuevo. Tomar acá los hombros de la
        # ficha usaría los milímetros de ANTES de reesculturar —que es lo que la
        # ficha sigue guardando— y rechazaría la primera medición posterior, que
        # es justo la que hay que poder registrar.
        return {**base, "origen": origen_corte, "fecha": corte,
                "profundidad_izq": valor, "profundidad_centro": valor,
                "profundidad_der": valor, "km_odometro": neu.km_actual}

    return {
        **base, "origen": origen_corte if corte is not None else "ficha",
        "fecha": corte,
        "profundidad_izq": neu.profundidad_externa,
        "profundidad_centro": neu.profundidad_actual,
        "profundidad_der": neu.profundidad_interna,
        "km_odometro": neu.km_actual,
    }


def _validar_profundidad(referencia: dict, izq, centro, der,
                         codigo: str) -> Optional[str]:
    """Una profundidad no puede subir. El labrado no vuelve a crecer.

    Antes se aceptaba cualquier valor, y una llanta que «ganaba» milímetros
    arruinaba dos cosas a la vez: el mm/km con el que se decide cuándo bajarla, y
    la alerta de profundidad mínima, que dejaba de dispararse. Y no se notaba,
    porque el dato entraba bien formado.

    El aumento se compara surco por surco y no contra el mínimo de los tres: una
    llanta que se desgasta por un hombro puede tener el centro igual y el hombro
    en caída, y mirar solo el mínimo escondería el dato equivocado del otro.
    """
    tolerancia = referencia.get("tolerancia") or 0.5
    minima = referencia.get("profundidad_minima")
    diseno = referencia.get("profundidad_diseno")
    nuevos = {"profundidad_izq": izq, "profundidad_centro": centro,
              "profundidad_der": der}

    for campo, nombre in SURCOS:
        valor = nuevos.get(campo)
        if valor is None:
            continue
        if valor < 0:
            return f"La profundidad del surco {nombre} no puede ser negativa."
        # Por encima del diseño es imposible salvo que la ficha esté mal, y
        # decirlo así ahorra buscar el error en el sitio equivocado.
        if diseno and valor > diseno + tolerancia:
            return (
                f"La profundidad del surco {nombre} ({valor:g} mm) supera la de "
                f"diseño de la llanta {codigo} ({diseno:g} mm). Verifique la "
                f"medición, o corrija la profundidad de diseño en la ficha."
            )
        anterior = referencia.get(campo)
        if anterior is None:
            continue
        if valor > anterior + tolerancia:
            return (
                f"La profundidad del surco {nombre} ({valor:g} mm) es MAYOR que la "
                f"última registrada ({anterior:g} mm) de la llanta {codigo}. El "
                f"labrado no crece: revise la medición. Si la llanta se reencauchó "
                f"o se reesculturó, registre esa operación primero y la referencia "
                f"queda actualizada."
            )
    return None


async def _validar_fecha_movimiento(db: AsyncSession, neu: "EAMNeumatico", fecha) -> Optional[str]:
    fecha = _fecha_naive(fecha)
    """No permite registrar un movimiento con fecha anterior a una inspección o a
    otro movimiento ya registrados para la misma llanta (evita romper el orden
    cronológico del historial)."""
    insp_r = await db.execute(
        select(EAMInspeccionNeumatico.fecha).where(EAMInspeccionNeumatico.neumatico_id == neu.id)
        .order_by(EAMInspeccionNeumatico.fecha.desc()).limit(1)
    )
    ultima_insp = insp_r.scalar_one_or_none()
    if ultima_insp and fecha < ultima_insp:
        return f"Existe una inspección posterior ({ultima_insp:%Y-%m-%d %H:%M}) a la fecha de este movimiento. Corrige la fecha."

    mov_r = await db.execute(
        select(EAMMovimientoNeumatico.fecha).where(EAMMovimientoNeumatico.neumatico_id == neu.id)
        .order_by(EAMMovimientoNeumatico.fecha.desc()).limit(1)
    )
    ultimo_mov = mov_r.scalar_one_or_none()
    if ultimo_mov and fecha < ultimo_mov:
        return f"Existe un movimiento posterior ({ultimo_mov:%Y-%m-%d %H:%M}) registrado para esta llanta. Los movimientos deben registrarse en orden cronológico."
    return None


async def _get_config_neu(db: AsyncSession) -> EAMNeumaticoConfig:
    """Obtiene (o crea) la fila única de configuración del módulo de llantas."""
    cfg = await db.get(EAMNeumaticoConfig, 1)
    if not cfg:
        cfg = EAMNeumaticoConfig(id=1)
        db.add(cfg); await db.commit(); await db.refresh(cfg)
    return cfg


# ── Bodegas de neumáticos ──
@router.get("/neumaticos/bodegas", response_model=List[BodegaNeumaticoResponse])
async def list_bodegas_neumatico(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMBodegaNeumatico).order_by(EAMBodegaNeumatico.nombre))
    return r.scalars().all()

@router.post("/neumaticos/bodegas", response_model=BodegaNeumaticoResponse)
async def create_bodega_neumatico(data: BodegaNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMBodegaNeumatico(**data.model_dump()); db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/bodegas/{bid}", response_model=BodegaNeumaticoResponse)
async def update_bodega_neumatico(bid: int, data: BodegaNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMBodegaNeumatico, bid)
    if not obj: raise HTTPException(404, "Bodega no encontrada")
    for k, v in data.model_dump().items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/neumaticos/bodegas/{bid}", status_code=204)
async def delete_bodega_neumatico(bid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMBodegaNeumatico, bid)
    if obj:
        cnt = await db.execute(select(func.count(EAMNeumatico.id)).where(EAMNeumatico.bodega_id == bid))
        if (cnt.scalar() or 0) > 0:
            raise HTTPException(409, "No se puede eliminar: hay neumáticos en esta bodega")
        await db.delete(obj); await db.commit()


# ── Catálogo de daños de neumático ──
@router.get("/neumaticos/danos-catalogo", response_model=List[DanoNeumaticoResponse])
async def list_danos_neumatico(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMDanoNeumaticoCatalogo).order_by(EAMDanoNeumaticoCatalogo.nombre))
    return r.scalars().all()

@router.post("/neumaticos/danos-catalogo", response_model=DanoNeumaticoResponse)
async def create_dano_neumatico(data: DanoNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMDanoNeumaticoCatalogo(**data.model_dump()); db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/danos-catalogo/{did}", response_model=DanoNeumaticoResponse)
async def update_dano_neumatico(did: int, data: DanoNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMDanoNeumaticoCatalogo, did)
    if not obj: raise HTTPException(404, "Daño no encontrado")
    for k, v in data.model_dump().items(): setattr(obj, k, v)
    await db.commit(); await db.refresh(obj); return obj

@router.delete("/neumaticos/danos-catalogo/{did}", status_code=204)
async def delete_dano_neumatico(did: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMDanoNeumaticoCatalogo, did)
    if obj: await db.delete(obj); await db.commit()


# -- Catalogo jerarquico de llantas y bandas ------------------------------------
# marca -> referencia -> (referencia + dimension) -> profundidad inicial.
# `ambito` = LLANTA | BANDA: las bandas de reencauche usan el mismo catalogo con
# sus propias marcas y referencias.

class MarcaNeuCreate(BaseModel):
    nombre: str
    ambito: str = "LLANTA"
    activo: bool = True

class MarcaNeuResponse(MarcaNeuCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class DimensionNeuCreate(BaseModel):
    nombre: str
    ambito: str = "LLANTA"
    activo: bool = True

class DimensionNeuResponse(DimensionNeuCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class ReferenciaNeuCreate(BaseModel):
    marca_id: int
    nombre: str
    ambito: str = "LLANTA"
    tipo_uso: Optional[str] = None
    activo: bool = True

class ReferenciaNeuResponse(ReferenciaNeuCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    marca_nombre: Optional[str] = None

class ReferenciaDimensionCreate(BaseModel):
    referencia_id: int
    dimension_id: int
    profundidad_inicial: float
    profundidad_minima: Optional[float] = None
    vida_util_km: Optional[float] = None
    presion_recomendada: Optional[float] = None
    activo: bool = True

class ReferenciaDimensionResponse(ReferenciaDimensionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dimension_nombre: Optional[str] = None


@router.get("/neumaticos/catalogo/marcas", response_model=List[MarcaNeuResponse])
async def list_marcas_neu(ambito: str = "LLANTA", db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMMarcaNeumatico)
        .where(EAMMarcaNeumatico.ambito == ambito.upper(), EAMMarcaNeumatico.activo == True)
        .order_by(EAMMarcaNeumatico.nombre)
    )
    return r.scalars().all()

@router.post("/neumaticos/catalogo/marcas", response_model=MarcaNeuResponse)
async def crear_marca_neu(data: MarcaNeuCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMMarcaNeumatico(**data.model_dump())
    obj.ambito = obj.ambito.upper()
    obj.nombre = obj.nombre.strip()
    db.add(obj)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(409, "La marca '%s' ya existe en %s" % (data.nombre, obj.ambito))
    await db.refresh(obj)
    return obj

@router.delete("/neumaticos/catalogo/marcas/{mid}", status_code=204)
async def eliminar_marca_neu(mid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMarcaNeumatico, mid)
    if obj:
        obj.activo = False
        await db.commit()


@router.get("/neumaticos/catalogo/dimensiones", response_model=List[DimensionNeuResponse])
async def list_dimensiones_neu(ambito: str = "LLANTA", db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMDimensionNeumatico)
        .where(EAMDimensionNeumatico.ambito == ambito.upper(), EAMDimensionNeumatico.activo == True)
        .order_by(EAMDimensionNeumatico.nombre)
    )
    return r.scalars().all()

@router.post("/neumaticos/catalogo/dimensiones", response_model=DimensionNeuResponse)
async def crear_dimension_neu(data: DimensionNeuCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMDimensionNeumatico(**data.model_dump())
    obj.ambito = obj.ambito.upper()
    obj.nombre = obj.nombre.strip()
    db.add(obj)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(409, "La dimension '%s' ya existe en %s" % (data.nombre, obj.ambito))
    await db.refresh(obj)
    return obj

@router.delete("/neumaticos/catalogo/dimensiones/{did}", status_code=204)
async def eliminar_dimension_neu(did: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMDimensionNeumatico, did)
    if obj:
        obj.activo = False
        await db.commit()


@router.get("/neumaticos/catalogo/referencias", response_model=List[ReferenciaNeuResponse])
async def list_referencias_neu(
    ambito: str = "LLANTA", marca_id: Optional[int] = None, db: AsyncSession = Depends(get_db),
):
    q = (
        select(EAMReferenciaNeumatico, EAMMarcaNeumatico.nombre)
        .join(EAMMarcaNeumatico, EAMMarcaNeumatico.id == EAMReferenciaNeumatico.marca_id)
        .where(EAMReferenciaNeumatico.ambito == ambito.upper(), EAMReferenciaNeumatico.activo == True)
    )
    if marca_id:
        q = q.where(EAMReferenciaNeumatico.marca_id == marca_id)
    r = await db.execute(q.order_by(EAMReferenciaNeumatico.nombre))
    salida = []
    for ref, marca_nombre in r.all():
        item = ReferenciaNeuResponse.model_validate(ref)
        item.marca_nombre = marca_nombre
        salida.append(item)
    return salida

@router.post("/neumaticos/catalogo/referencias", response_model=ReferenciaNeuResponse)
async def crear_referencia_neu(data: ReferenciaNeuCreate, db: AsyncSession = Depends(get_db)):
    marca = await db.get(EAMMarcaNeumatico, data.marca_id)
    if not marca:
        raise HTTPException(404, "La marca no existe")
    obj = EAMReferenciaNeumatico(**data.model_dump())
    obj.ambito = obj.ambito.upper()
    obj.nombre = obj.nombre.strip()
    db.add(obj)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(409, "La referencia '%s' ya existe para la marca %s" % (data.nombre, marca.nombre))
    await db.refresh(obj)
    return obj

@router.delete("/neumaticos/catalogo/referencias/{rid}", status_code=204)
async def eliminar_referencia_neu(rid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMReferenciaNeumatico, rid)
    if obj:
        obj.activo = False
        await db.commit()


@router.get("/neumaticos/catalogo/referencias/{rid}/dimensiones", response_model=List[ReferenciaDimensionResponse])
async def list_dimensiones_de_referencia(rid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMReferenciaDimension, EAMDimensionNeumatico.nombre)
        .join(EAMDimensionNeumatico, EAMDimensionNeumatico.id == EAMReferenciaDimension.dimension_id)
        .where(EAMReferenciaDimension.referencia_id == rid, EAMReferenciaDimension.activo == True)
        .order_by(EAMDimensionNeumatico.nombre)
    )
    salida = []
    for rd, dim_nombre in r.all():
        item = ReferenciaDimensionResponse.model_validate(rd)
        item.dimension_nombre = dim_nombre
        salida.append(item)
    return salida

@router.post("/neumaticos/catalogo/referencia-dimension", response_model=ReferenciaDimensionResponse)
async def crear_referencia_dimension(data: ReferenciaDimensionCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(EAMReferenciaNeumatico, data.referencia_id):
        raise HTTPException(404, "La referencia no existe")
    if not await db.get(EAMDimensionNeumatico, data.dimension_id):
        raise HTTPException(404, "La dimension no existe")
    if data.profundidad_inicial is None or data.profundidad_inicial <= 0:
        raise HTTPException(400, "La profundidad inicial debe ser mayor que cero")
    obj = EAMReferenciaDimension(**data.model_dump())
    db.add(obj)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(409, "Esa referencia ya tiene configurada esa dimension")
    await db.refresh(obj)
    return obj

@router.put("/neumaticos/catalogo/referencia-dimension/{rdid}", response_model=ReferenciaDimensionResponse)
async def actualizar_referencia_dimension(rdid: int, data: ReferenciaDimensionCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMReferenciaDimension, rdid)
    if not obj:
        raise HTTPException(404, "Combinacion no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/catalogo/referencia-dimension/{rdid}", status_code=204)
async def eliminar_referencia_dimension(rdid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMReferenciaDimension, rdid)
    if obj:
        await db.delete(obj)
        await db.commit()


async def _resolver_catalogo_llanta(
    db: AsyncSession, marca, referencia, medida, ambito: str = "LLANTA",
):
    """Valida marca/referencia/medida contra el catalogo y devuelve la fila de
    referencia+dimension (de donde sale la profundidad inicial). Lanza ValueError
    con un mensaje entendible: quien llama decide si es 409 o error de fila."""
    if not marca or not str(marca).strip():
        raise ValueError("La marca es obligatoria")
    if not medida or not str(medida).strip():
        raise ValueError("La dimension/medida es obligatoria")

    r = await db.execute(select(EAMMarcaNeumatico).where(
        func.lower(EAMMarcaNeumatico.nombre) == str(marca).strip().lower(),
        EAMMarcaNeumatico.ambito == ambito, EAMMarcaNeumatico.activo == True,
    ))
    obj_marca = r.scalar_one_or_none()
    if not obj_marca:
        raise ValueError("La marca '%s' no esta en el catalogo" % marca)

    r = await db.execute(select(EAMDimensionNeumatico).where(
        func.lower(EAMDimensionNeumatico.nombre) == str(medida).strip().lower(),
        EAMDimensionNeumatico.ambito == ambito, EAMDimensionNeumatico.activo == True,
    ))
    obj_dim = r.scalar_one_or_none()
    if not obj_dim:
        raise ValueError("La dimension '%s' no esta en el catalogo" % medida)

    if not referencia or not str(referencia).strip():
        raise ValueError("La referencia es obligatoria")
    r = await db.execute(select(EAMReferenciaNeumatico).where(
        EAMReferenciaNeumatico.marca_id == obj_marca.id,
        func.lower(EAMReferenciaNeumatico.nombre) == str(referencia).strip().lower(),
        EAMReferenciaNeumatico.activo == True,
    ))
    obj_ref = r.scalar_one_or_none()
    if not obj_ref:
        raise ValueError(
            "La referencia '%s' no pertenece a la marca '%s'" % (referencia, obj_marca.nombre)
        )

    r = await db.execute(select(EAMReferenciaDimension).where(
        EAMReferenciaDimension.referencia_id == obj_ref.id,
        EAMReferenciaDimension.dimension_id == obj_dim.id,
        EAMReferenciaDimension.activo == True,
    ))
    obj_rd = r.scalar_one_or_none()
    if not obj_rd:
        raise ValueError(
            "La referencia '%s' no tiene configurada la dimension '%s'"
            % (obj_ref.nombre, obj_dim.nombre)
        )
    return obj_marca, obj_ref, obj_dim, obj_rd


# -- Catalogo de atributos (marca/medida/referencia/vida) --
@router.get("/neumaticos/catalogo", response_model=List[CatalogoNeuResponse])
async def list_catalogo_neumatico(tipo: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = select(EAMNeumaticoCatalogo)
    if tipo:
        q = q.where(EAMNeumaticoCatalogo.tipo == tipo.upper())
    r = await db.execute(q.order_by(EAMNeumaticoCatalogo.tipo, EAMNeumaticoCatalogo.nombre))
    return r.scalars().all()

@router.post("/neumaticos/catalogo", response_model=CatalogoNeuResponse)
async def create_catalogo_neumatico(data: CatalogoNeuCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMNeumaticoCatalogo(**data.model_dump()); obj.tipo = obj.tipo.upper()
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/catalogo/{cid}", status_code=204)
async def delete_catalogo_neumatico(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMNeumaticoCatalogo, cid)
    if obj: await db.delete(obj); await db.commit()


# ── Pila de descarte (neumáticos dados de baja) ──
@router.get("/neumaticos/descarte", response_model=List[NeumaticResponse])
async def list_descarte_neumatico(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMNeumatico).where(EAMNeumatico.estado == "BAJA").order_by(EAMNeumatico.fecha_baja.desc()))
    return r.scalars().all()


class ConfigEjes(BaseModel):
    numero_ejes: int
    tiene_repuesto: bool = True

@router.put("/neumaticos/config-ejes/{activo_id}")
async def config_ejes_vehiculo(activo_id: int, data: ConfigEjes, db: AsyncSession = Depends(get_db)):
    """Configura el número de ejes y repuesto de un vehículo (no destructivo)."""
    activo = await db.get(EAMActivo, activo_id)
    if not activo:
        raise HTTPException(404, "Activo no encontrado")
    if data.numero_ejes < 1 or data.numero_ejes > 6:
        raise HTTPException(400, "El número de ejes debe estar entre 1 y 6")
    activo.numero_ejes = data.numero_ejes
    activo.tiene_repuesto = data.tiene_repuesto
    await db.commit()
    return {"id": activo.id, "numero_ejes": activo.numero_ejes, "tiene_repuesto": activo.tiene_repuesto}


# ── Layout de posiciones por vehículo ──
@router.get("/neumaticos/layout/{activo_id}", response_model=List[PosicionLayout])
async def layout_neumaticos(activo_id: int, db: AsyncSession = Depends(get_db)):
    activo = await db.get(EAMActivo, activo_id)
    if not activo:
        raise HTTPException(404, "Activo no encontrado")
    return _generar_posiciones(
        activo.numero_ejes, activo.tiene_repuesto if activo.tiene_repuesto is not None else True,
        layout=activo.layout_llantas, cantidad_repuestos=activo.cantidad_repuestos or 1,
    )


# ── Movimiento (instalación / rotación / desmontaje / reencauche / baja) ──
@router.post("/neumaticos/movimiento", response_model=MovNeumaticoResponse)
async def crear_movimiento_neumatico(data: MovNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, data.neumatico_id)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    tipo = (data.tipo_movimiento or "").upper()
    posicion_origen = neu.posicion

    # Se normaliza una sola vez: lo que se compara es lo que se guarda.
    data.fecha = _fecha_naive(data.fecha)
    err_fecha = await _validar_fecha_movimiento(db, neu, data.fecha)
    if err_fecha:
        raise HTTPException(409, err_fecha)

    if data.bodega_id is not None:
        # eam_neumatico.bodega_id no tiene llave foránea, así que un id
        # inexistente entraba sin más y dejaba la llanta en una bodega fantasma.
        bodega = await db.get(EAMBodegaNeumatico, data.bodega_id)
        if not bodega:
            raise HTTPException(400, f"La bodega {data.bodega_id} no existe")

    if tipo in ("INSTALACION", "ROTACION"):
        # La lectura del equipo al montar es lo que después permite calcular el
        # recorrido de la llanta y su costo por kilómetro. Sin ella, la vida de
        # la llanta arranca sin punto de partida y el CPK no se puede sacar.
        if data.km_odometro is None and data.horometro is None:
            raise HTTPException(
                400,
                "Registre el odómetro o el horómetro del equipo al montar la llanta: "
                "es el punto de partida para calcular su recorrido.",
            )

    # La lectura se comprueba en CUALQUIER movimiento que la traiga, no solo al
    # montar. Antes solo se revisaba en montaje y rotación, así que un desmontaje
    # o una baja con el odómetro hacia atrás entraban sin más —y la baja es la que
    # CIERRA la vida de la llanta con ese kilómetro, o sea que el recorrido total
    # y el costo por kilómetro salían mal justo en el momento de calcularlos.
    if data.km_odometro is not None or data.horometro is not None:
        activo_lectura = await db.get(EAMActivo, data.activo_id or neu.activo_id)
        if activo_lectura:
            err_lectura = _validar_lectura(activo_lectura, neu, data.km_odometro, data.horometro)
            if err_lectura:
                raise HTTPException(409, err_lectura)

    if tipo == "INSTALACION":
        if neu.estado == "BAJA":
            raise HTTPException(409, f"La llanta {neu.codigo} fue descartada y no se puede montar.")
        if neu.estado == "REENCAUCHE":
            raise HTTPException(409, f"La llanta {neu.codigo} está en proceso de reencauche y no se puede montar.")
        if neu.estado == "INSTALADO" and neu.activo_id and neu.activo_id != data.activo_id:
            raise HTTPException(409, f"La llanta {neu.codigo} ya está instalada en otro vehículo (posición {neu.posicion}). Desmóntala primero.")
        if data.activo_id and data.posicion:
            ocupada_r = await db.execute(
                select(EAMNeumatico).where(
                    EAMNeumatico.activo_id == data.activo_id, EAMNeumatico.posicion == data.posicion,
                    EAMNeumatico.estado == "INSTALADO", EAMNeumatico.id != neu.id,
                )
            )
            ocupante = ocupada_r.scalar_one_or_none()
            if ocupante:
                raise HTTPException(409, f"La posición {data.posicion} ya está ocupada por la llanta {ocupante.codigo}.")
        cfg = await _get_config_neu(db)
        if cfg.montaje_estricto and data.posicion:
            err = _validar_montaje(neu.tipo_uso, data.posicion)
            if err:
                raise HTTPException(409, err)
        neu.estado = "INSTALADO"; neu.activo_id = data.activo_id
        neu.posicion = data.posicion; neu.bodega_id = None
        if data.km_odometro is not None:
            neu.km_actual = data.km_odometro
    elif tipo == "ROTACION":
        if data.activo_id and data.posicion:
            ocupada_r = await db.execute(
                select(EAMNeumatico).where(
                    EAMNeumatico.activo_id == data.activo_id, EAMNeumatico.posicion == data.posicion,
                    EAMNeumatico.estado == "INSTALADO", EAMNeumatico.id != neu.id,
                )
            )
            ocupante = ocupada_r.scalar_one_or_none()
            if ocupante:
                raise HTTPException(409, f"La posición {data.posicion} ya está ocupada por la llanta {ocupante.codigo}. Usa la rotación por intercambio.")
        cfg = await _get_config_neu(db)
        if cfg.montaje_estricto and data.posicion:
            err = _validar_montaje(neu.tipo_uso, data.posicion)
            if err:
                raise HTTPException(409, err)
        neu.estado = "INSTALADO"; neu.activo_id = data.activo_id
        neu.posicion = data.posicion; neu.bodega_id = None
        if data.km_odometro is not None:
            neu.km_actual = data.km_odometro
    elif tipo in ("DESMONTAJE", "ALMACENAMIENTO"):
        neu.estado = "ALMACENADO"; neu.activo_id = None; neu.posicion = None
        neu.bodega_id = data.bodega_id
    elif tipo == "REENCAUCHE":
        neu.estado = "REENCAUCHE"; neu.activo_id = None; neu.posicion = None
        neu.bodega_id = data.bodega_id
        neu.reencauches = (neu.reencauches or 0) + 1
        if data.dano_id: neu.dano_id = data.dano_id
    elif tipo == "VOLTEO":
        # Voltear la llanta en la MISMA posición: invierte el sentido de montaje
        # para emparejar el desgaste irregular entre hombros (interno ↔ externo).
        if neu.estado != "INSTALADO" or not neu.posicion:
            raise HTTPException(409, "Solo se puede voltear una llanta instalada en un vehículo")
        neu.orientacion = "INVERTIDA" if (neu.orientacion or "NORMAL") == "NORMAL" else "NORMAL"
        neu.profundidad_externa, neu.profundidad_interna = neu.profundidad_interna, neu.profundidad_externa
        data.posicion = neu.posicion   # se mantiene en la misma posición
    elif tipo == "BAJA":
        neu.estado = "BAJA"; neu.activo_id = None; neu.posicion = None; neu.bodega_id = None
        neu.dano_id = data.dano_id; neu.motivo_baja = data.motivo
        neu.motivo_fin_vida_id = data.motivo_fin_vida_id
        neu.fecha_baja = data.fecha.date()
        vida_actual = await _vida_abierta(db, neu.id)
        if vida_actual:
            vida_actual.fecha_fin = data.fecha
            vida_actual.km_fin = data.km_odometro if data.km_odometro is not None else neu.km_actual
            vida_actual.profundidad_final = neu.profundidad_actual
            vida_actual.motivo_cierre_id = data.motivo_fin_vida_id
    else:
        raise HTTPException(400, f"Tipo de movimiento inválido: {tipo}")

    mov = EAMMovimientoNeumatico(
        neumatico_id=neu.id, tipo_movimiento=tipo, activo_id=data.activo_id or neu.activo_id,
        posicion_origen=posicion_origen, posicion=data.posicion, bodega_id=data.bodega_id,
        km_odometro=data.km_odometro, horometro=data.horometro, fecha=data.fecha,
        observaciones=(data.observaciones or data.motivo or (f"Volteo: orientación → {neu.orientacion}" if tipo == "VOLTEO" else None)),
        tecnico=data.tecnico,
    )
    db.add(mov)

    # La lectura tomada acá vale igual que la de una OT, así que también avanza
    # el medidor del equipo. Solo hacia adelante, por lo mismo.
    activo_mov_id = data.activo_id or neu.activo_id
    if activo_mov_id and (data.km_odometro is not None or data.horometro is not None):
        activo_mov = await db.get(EAMActivo, activo_mov_id)
        if activo_mov:
            _avanzar_medidores(activo_mov, data.km_odometro, data.horometro)

    await db.commit(); await db.refresh(mov)
    return mov


# ── Descartes masivos (BAJA, carga por archivo plano, referenciando la llanta por código) ──
class BajaBulkItem(BaseModel):
    codigo: str
    fecha: datetime
    dano_id: Optional[int] = None
    motivo_fin_vida_id: Optional[int] = None
    motivo: Optional[str] = None
    km_odometro: Optional[float] = None

class BajaBulkCreate(BaseModel):
    items: List[BajaBulkItem]

@router.post("/neumaticos/baja/bulk")
async def dar_baja_masivo(data: BajaBulkCreate, db: AsyncSession = Depends(get_db)):
    exitosos = 0
    errores = []
    for i, item in enumerate(data.items):
        try:
            async with db.begin_nested():
                r = await db.execute(select(EAMNeumatico).where(EAMNeumatico.codigo == item.codigo))
                neu = r.scalar_one_or_none()
                if not neu:
                    raise ValueError(f"Llanta con código '{item.codigo}' no encontrada")
                if neu.estado == "BAJA":
                    raise ValueError(f"La llanta {item.codigo} ya está dada de baja")
                err_fecha = await _validar_fecha_movimiento(db, neu, item.fecha)
                if err_fecha:
                    raise ValueError(err_fecha)
                # La baja cierra la vida de la llanta con este kilometraje: si
                # va hacia atrás, el recorrido total de esa vida queda mal y con
                # él el costo por kilómetro. Se revisa acá y no solo en la
                # pantalla, porque esta ruta se alimenta de un archivo.
                if item.km_odometro is not None and neu.activo_id:
                    activo_baja = await db.get(EAMActivo, neu.activo_id)
                    if activo_baja:
                        err_lectura = _validar_lectura(activo_baja, neu, item.km_odometro, None)
                        if err_lectura:
                            raise ValueError(err_lectura)
                posicion_origen = neu.posicion
                activo_id_origen = neu.activo_id
                neu.estado = "BAJA"; neu.activo_id = None; neu.posicion = None; neu.bodega_id = None
                neu.dano_id = item.dano_id; neu.motivo_baja = item.motivo
                neu.motivo_fin_vida_id = item.motivo_fin_vida_id
                neu.fecha_baja = item.fecha.date()
                vida_actual = await _vida_abierta(db, neu.id)
                if vida_actual:
                    vida_actual.fecha_fin = item.fecha
                    vida_actual.km_fin = item.km_odometro if item.km_odometro is not None else neu.km_actual
                    vida_actual.profundidad_final = neu.profundidad_actual
                    vida_actual.motivo_cierre_id = item.motivo_fin_vida_id
                db.add(EAMMovimientoNeumatico(
                    neumatico_id=neu.id, tipo_movimiento="BAJA", activo_id=activo_id_origen,
                    posicion_origen=posicion_origen, posicion=None, bodega_id=None,
                    km_odometro=item.km_odometro, fecha=item.fecha, observaciones=item.motivo,
                ))
            exitosos += 1
        except Exception as e:
            errores.append({"fila": i + 2, "codigo": item.codigo, "mensaje": str(e)})
    await db.commit()
    return {"total": len(data.items), "exitosos": exitosos, "errores": errores}


class RotacionIntercambio(BaseModel):
    neumatico_a_id: int
    neumatico_b_id: int
    fecha: datetime
    km_odometro: Optional[float] = None
    tecnico: Optional[str] = None
    observaciones: Optional[str] = None

@router.post("/neumaticos/rotacion-intercambio")
async def rotacion_intercambio(data: RotacionIntercambio, db: AsyncSession = Depends(get_db)):
    """Intercambia dos llantas instaladas: cada una toma la posición de la otra
    (rotación clásica), validando el montaje estricto para ambas."""
    a = await db.get(EAMNeumatico, data.neumatico_a_id)
    b = await db.get(EAMNeumatico, data.neumatico_b_id)
    if not a or not b:
        raise HTTPException(404, "Neumático no encontrado")
    if a.estado != "INSTALADO" or b.estado != "INSTALADO":
        raise HTTPException(409, "Ambas llantas deben estar instaladas para intercambiarse")
    data.fecha = _fecha_naive(data.fecha)
    for neu in (a, b):
        err_fecha = await _validar_fecha_movimiento(db, neu, data.fecha)
        if err_fecha:
            raise HTTPException(409, f"{neu.codigo}: {err_fecha}")
    pos_a, pos_b = a.posicion, b.posicion
    veh_a, veh_b = a.activo_id, b.activo_id
    cfg = await _get_config_neu(db)
    if cfg.montaje_estricto:
        for neu, pos in ((a, pos_b), (b, pos_a)):
            err = _validar_montaje(neu.tipo_uso, pos)
            if err:
                raise HTTPException(409, f"{neu.codigo}: {err}")
    # Intercambio de posiciones (y vehículo, por si son distintos)
    a.posicion, a.activo_id = pos_b, veh_b
    b.posicion, b.activo_id = pos_a, veh_a
    if data.km_odometro is not None:
        a.km_actual = b.km_actual = data.km_odometro
    obs = data.observaciones or f"Intercambio de rotación: {a.codigo} ⇄ {b.codigo}"
    for neu, origen, destino, veh in ((a, pos_a, pos_b, veh_b), (b, pos_b, pos_a, veh_a)):
        db.add(EAMMovimientoNeumatico(
            neumatico_id=neu.id, tipo_movimiento="ROTACION", activo_id=veh,
            posicion_origen=origen, posicion=destino, km_odometro=data.km_odometro,
            fecha=data.fecha, observaciones=obs, tecnico=data.tecnico,
        ))
    await db.commit()
    return {"ok": True, "a": {"codigo": a.codigo, "posicion": a.posicion}, "b": {"codigo": b.codigo, "posicion": b.posicion}}


class RotacionDestino(BaseModel):
    neumatico_id: int
    """Posición final. En None, la llanta sale del vehículo a bodega."""
    posicion: Optional[str] = None
    # Medición tomada al desmontar. Rotar es el momento en que la llanta está
    # en la mano, así que se aprovecha para dejar la inspección del día.
    profundidad_izq: Optional[float] = None
    profundidad_centro: Optional[float] = None
    profundidad_der: Optional[float] = None
    presion_psi: Optional[float] = None
    estado_visual: Optional[str] = None
    observaciones: Optional[str] = None

class RotacionPlan(BaseModel):
    activo_id: int
    fecha: datetime
    destinos: List[RotacionDestino]
    km_odometro: Optional[float] = None
    horometro: Optional[float] = None
    bodega_id: Optional[int] = None       # destino de las que salen
    tecnico: Optional[str] = None
    observaciones: Optional[str] = None


@router.post("/neumaticos/rotacion-plan")
async def rotacion_plan(data: RotacionPlan, db: AsyncSession = Depends(get_db)):
    """Aplica una rotación completa de una sola vez.

    Se recibe la foto final — qué llanta queda en qué posición — en vez de un
    movimiento por paso. Es lo que permite el almacén de rotación de la
    pantalla: mientras se acomodan las llantas no se toca la base, y al
    confirmar todo entra junto.

    Hacerlo por pasos obligaría a desmontar y volver a montar cada llanta, y
    cada desmontaje cierra un tramo de vida de la llanta: el historial quedaría
    lleno de bajas y altas que nunca ocurrieron, y el CPK saldría mal.
    """
    activo = await db.get(EAMActivo, data.activo_id)
    if not activo:
        raise HTTPException(404, "Vehículo no encontrado")
    if data.km_odometro is None and data.horometro is None:
        raise HTTPException(
            400,
            "Registre el odómetro o el horómetro del equipo: es la lectura con la "
            "que queda el tramo de cada llanta.",
        )
    if not data.destinos:
        raise HTTPException(400, "No hay llantas que mover")
    data.fecha = _fecha_naive(data.fecha)

    # Dos llantas no pueden terminar en la misma posición.
    ocupadas: dict[str, int] = {}
    for d in data.destinos:
        if not d.posicion:
            continue
        if d.posicion in ocupadas:
            raise HTTPException(409, f"Dos llantas quedarían en la posición {d.posicion}")
        ocupadas[d.posicion] = d.neumatico_id

    posiciones_validas = {
        p["codigo"]
        for p in _generar_posiciones(
            activo.numero_ejes,
            activo.tiene_repuesto if activo.tiene_repuesto is not None else True,
            layout=activo.layout_llantas, cantidad_repuestos=activo.cantidad_repuestos or 1,
        )
    }
    for pos in ocupadas:
        if pos not in posiciones_validas:
            raise HTTPException(400, f"La posición {pos} no existe en este vehículo")

    if data.bodega_id is not None:
        bodega = await db.get(EAMBodegaNeumatico, data.bodega_id)
        if not bodega:
            raise HTTPException(400, f"La bodega {data.bodega_id} no existe")

    ids = [d.neumatico_id for d in data.destinos]
    filas = (await db.execute(select(EAMNeumatico).where(EAMNeumatico.id.in_(ids)))).scalars().all()
    por_id = {n.id: n for n in filas}
    faltan = [i for i in ids if i not in por_id]
    if faltan:
        raise HTTPException(404, f"Neumático(s) no encontrado(s): {faltan}")

    cfg = await _get_config_neu(db)
    for d in data.destinos:
        neu = por_id[d.neumatico_id]
        if neu.estado == "BAJA":
            raise HTTPException(409, f"La llanta {neu.codigo} fue descartada y no se puede mover.")
        # La rotación es un solo evento con una sola fecha, pero cada llanta
        # trae su propio historial: basta que una tenga algo posterior para que
        # la fecha esté mal. Se valida antes de tocar nada, para no dejar media
        # rotación aplicada.
        err_fecha = await _validar_fecha_movimiento(db, neu, data.fecha)
        if err_fecha:
            raise HTTPException(409, f"{neu.codigo}: {err_fecha}")
        err_lectura = _validar_lectura(activo, neu, data.km_odometro, data.horometro)
        if err_lectura:
            raise HTTPException(409, err_lectura)
        if d.posicion and cfg.montaje_estricto:
            err = _validar_montaje(neu.tipo_uso, d.posicion)
            if err:
                raise HTTPException(409, f"{neu.codigo}: {err}")

    # Una llanta que hoy está en el vehículo y no aparece en el plan se queda
    # donde está: el plan solo describe lo que se movió.
    origen = {n.id: (n.posicion, n.activo_id, n.estado) for n in filas}
    obs = data.observaciones or "Rotación de llantas"
    movimientos = 0
    inspecciones = 0
    for d in data.destinos:
        neu = por_id[d.neumatico_id]
        pos_origen, veh_origen, estado_origen = origen[neu.id]
        if d.posicion:
            # Entra o cambia de posición dentro del vehículo.
            tipo = "ROTACION" if estado_origen == "INSTALADO" else "INSTALACION"
            neu.estado = "INSTALADO"
            neu.activo_id = data.activo_id
            neu.posicion = d.posicion
            neu.bodega_id = None
        else:
            tipo = "DESMONTAJE"
            neu.estado = "ALMACENADO"
            neu.activo_id = None
            neu.posicion = None
            neu.bodega_id = data.bodega_id
        if data.km_odometro is not None:
            neu.km_actual = data.km_odometro
            neu.km_total = max(0.0, (neu.km_actual or 0) - (neu.km_inicio or 0))
        db.add(EAMMovimientoNeumatico(
            neumatico_id=neu.id, tipo_movimiento=tipo,
            activo_id=data.activo_id if d.posicion else veh_origen,
            posicion_origen=pos_origen, posicion=d.posicion, bodega_id=data.bodega_id if not d.posicion else None,
            km_odometro=data.km_odometro, horometro=data.horometro,
            fecha=data.fecha, observaciones=obs, tecnico=data.tecnico,
        ))
        movimientos += 1

        # La medición del día queda como inspección de la llanta, con la misma
        # convención del resto del módulo: izq = hombro externo, der = interno.
        medido = any(v is not None for v in (
            d.profundidad_izq, d.profundidad_centro, d.profundidad_der, d.presion_psi,
        ))
        if medido or d.estado_visual:
            db.add(EAMInspeccionNeumatico(
                neumatico_id=neu.id, fecha=data.fecha,
                # La posición de la que venía: es donde se desgastó lo que se mide.
                posicion=pos_origen,
                profundidad_izq=d.profundidad_izq,
                profundidad_centro=d.profundidad_centro,
                profundidad_der=d.profundidad_der,
                presion_psi=d.presion_psi,
                km_odometro=data.km_odometro,
                estado_visual=d.estado_visual,
                observaciones=d.observaciones or "Medición tomada en la rotación",
                tecnico=data.tecnico,
            ))
            pmin = _min_prof(d.profundidad_izq, d.profundidad_centro, d.profundidad_der)
            if pmin is not None:
                neu.profundidad_actual = pmin
            if d.profundidad_izq is not None:
                neu.profundidad_externa = d.profundidad_izq
            if d.profundidad_der is not None:
                neu.profundidad_interna = d.profundidad_der
            if d.presion_psi is not None:
                neu.presion_actual = d.presion_psi
            inspecciones += 1

    _avanzar_medidores(activo, data.km_odometro, data.horometro)
    await db.commit()
    return {"ok": True, "movimientos": movimientos, "inspecciones": inspecciones}


class MovimientoBitacora(BaseModel):
    """Una línea de la bitácora: movimientos reales más el alta de cada llanta."""
    id: Optional[int] = None          # None en el alta, que no es una fila de movimiento
    neumatico_id: int
    neumatico_codigo: str
    tipo_movimiento: str
    fecha: Optional[datetime] = None
    posicion_origen: Optional[str] = None
    posicion: Optional[str] = None
    activo_id: Optional[int] = None
    activo_codigo: Optional[str] = None
    bodega_id: Optional[int] = None
    bodega_nombre: Optional[str] = None
    km_odometro: Optional[float] = None
    horometro: Optional[float] = None
    tecnico: Optional[str] = None
    observaciones: Optional[str] = None
    """El alta se deriva de la llanta, así que no se corrige desde acá."""
    editable: bool = True


class MovimientoUpdate(BaseModel):
    """Solo se corrigen los datos del registro.

    El tipo y las posiciones no: son los que definen dónde quedó la llanta, y
    cambiarlos por aquí dejaría el estado actual sin relación con su historia.
    Para mover una llanta está la pantalla del vehículo.
    """
    fecha: Optional[datetime] = None
    km_odometro: Optional[float] = None
    horometro: Optional[float] = None
    tecnico: Optional[str] = None
    observaciones: Optional[str] = None


async def _recalcular_recorrido(db: AsyncSession, neu: EAMNeumatico) -> None:
    """Reconstruye el kilometraje de la llanta desde lo que quedó registrado.

    Se llama tras corregir o borrar: si el dato que fijaba el recorrido cambió,
    dejarlo como estaba haría que el CPK siguiera saliendo del valor viejo.
    """
    lecturas = []
    r = await db.execute(
        select(EAMMovimientoNeumatico.km_odometro)
        .where(EAMMovimientoNeumatico.neumatico_id == neu.id,
               EAMMovimientoNeumatico.km_odometro.isnot(None))
    )
    lecturas += [x for (x,) in r.all() if x is not None]
    r = await db.execute(
        select(EAMInspeccionNeumatico.km_odometro)
        .where(EAMInspeccionNeumatico.neumatico_id == neu.id,
               EAMInspeccionNeumatico.km_odometro.isnot(None))
    )
    lecturas += [x for (x,) in r.all() if x is not None]
    neu.km_actual = max(lecturas) if lecturas else (neu.km_inicio or 0)
    neu.km_total = max(0.0, (neu.km_actual or 0) - (neu.km_inicio or 0))


@router.get("/neumaticos/movimientos", response_model=List[MovimientoBitacora])
async def bitacora_movimientos(
    neumatico_id: Optional[int] = None,
    activo_id: Optional[int] = None,
    tipo_movimiento: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    """Bitácora completa: todo lo que le pasó a cada llanta, en un solo lugar.

    Incluye el alta de la llanta como primera línea de su historia, aunque no
    sea una fila de movimiento: sin ella la bitácora arrancaría en el aire.
    """
    neus = (await db.execute(select(EAMNeumatico))).scalars().all()
    por_neu = {n.id: n for n in neus}
    activos = {a.id: a for a in (await db.execute(select(EAMActivo))).scalars().all()}
    bodegas = {b.id: b for b in (await db.execute(select(EAMBodegaNeumatico))).scalars().all()}

    q = select(EAMMovimientoNeumatico)
    if neumatico_id is not None:
        q = q.where(EAMMovimientoNeumatico.neumatico_id == neumatico_id)
    if activo_id is not None:
        q = q.where(EAMMovimientoNeumatico.activo_id == activo_id)
    if tipo_movimiento:
        q = q.where(EAMMovimientoNeumatico.tipo_movimiento == tipo_movimiento.upper())
    movs = (await db.execute(q)).scalars().all()

    filas: List[MovimientoBitacora] = []
    for m in movs:
        neu = por_neu.get(m.neumatico_id)
        if not neu:
            continue
        activo = activos.get(m.activo_id) if m.activo_id else None
        bodega = bodegas.get(m.bodega_id) if m.bodega_id else None
        filas.append(MovimientoBitacora(
            id=m.id, neumatico_id=m.neumatico_id, neumatico_codigo=neu.codigo,
            tipo_movimiento=m.tipo_movimiento or "—", fecha=m.fecha,
            posicion_origen=m.posicion_origen, posicion=m.posicion,
            activo_id=m.activo_id, activo_codigo=activo.codigo if activo else None,
            bodega_id=m.bodega_id, bodega_nombre=bodega.nombre if bodega else None,
            km_odometro=m.km_odometro, horometro=m.horometro,
            tecnico=m.tecnico, observaciones=m.observaciones,
        ))

    # El alta de cada llanta, para que la historia empiece por el principio.
    if tipo_movimiento in (None, "", "ALTA"):
        for n in neus:
            if neumatico_id is not None and n.id != neumatico_id:
                continue
            if activo_id is not None:
                continue
            filas.append(MovimientoBitacora(
                id=None, neumatico_id=n.id, neumatico_codigo=n.codigo,
                # created_at viene con zona y los movimientos sin ella; se
                # igualan para poder ordenarlos juntos.
                tipo_movimiento="ALTA", fecha=_fecha_naive(n.created_at),
                km_odometro=n.km_inicio, editable=False,
                observaciones="Alta de la llanta en el sistema",
            ))

    filas.sort(key=lambda f: (_fecha_naive(f.fecha) or datetime.min), reverse=True)
    return filas[:limit]


@router.put("/neumaticos/movimientos/{mov_id}", response_model=MovNeumaticoResponse)
async def corregir_movimiento(mov_id: int, data: MovimientoUpdate, db: AsyncSession = Depends(get_db)):
    mov = await db.get(EAMMovimientoNeumatico, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    neu = await db.get(EAMNeumatico, mov.neumatico_id)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")

    cambios = data.model_dump(exclude_unset=True)
    if "fecha" in cambios and cambios["fecha"] is not None:
        cambios["fecha"] = _fecha_naive(cambios["fecha"])
    for k, v in cambios.items():
        setattr(mov, k, v)

    await db.flush()
    await _recalcular_recorrido(db, neu)
    await db.commit(); await db.refresh(mov)
    return mov


@router.delete("/neumaticos/movimientos/{mov_id}", status_code=204)
async def eliminar_movimiento(mov_id: int, db: AsyncSession = Depends(get_db)):
    """Borra un movimiento y deja la llanta como la dejó el anterior.

    Si el que se borra era el último, la llanta vuelve a donde estaba antes:
    quitar el registro sin devolverla dejaría el estado actual contando una
    historia que ya no existe.
    """
    mov = await db.get(EAMMovimientoNeumatico, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    neu = await db.get(EAMNeumatico, mov.neumatico_id)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")

    ultimo = (await db.execute(
        select(EAMMovimientoNeumatico)
        .where(EAMMovimientoNeumatico.neumatico_id == neu.id)
        .order_by(EAMMovimientoNeumatico.fecha.desc(), EAMMovimientoNeumatico.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    era_el_ultimo = ultimo is not None and ultimo.id == mov.id

    await db.delete(mov)
    await db.flush()

    if era_el_ultimo:
        previo = (await db.execute(
            select(EAMMovimientoNeumatico)
            .where(EAMMovimientoNeumatico.neumatico_id == neu.id)
            .order_by(EAMMovimientoNeumatico.fecha.desc(), EAMMovimientoNeumatico.id.desc())
            .limit(1)
        )).scalar_one_or_none()
        if previo is None:
            # Sin historia: la llanta vuelve a estar solo dada de alta.
            neu.estado = "ALMACENADO"
            neu.activo_id = None
            neu.posicion = None
        elif (previo.tipo_movimiento or "").upper() in ("INSTALACION", "ROTACION"):
            neu.estado = "INSTALADO"
            neu.activo_id = previo.activo_id
            neu.posicion = previo.posicion
            neu.bodega_id = None
        elif (previo.tipo_movimiento or "").upper() in ("DESMONTAJE", "ALMACENAMIENTO"):
            neu.estado = "ALMACENADO"
            neu.activo_id = None
            neu.posicion = None
            neu.bodega_id = previo.bodega_id

    await _recalcular_recorrido(db, neu)
    await db.commit()


@router.get("/neumaticos/{nid}/movimientos", response_model=List[MovNeumaticoResponse])
async def list_movimientos_neumatico(nid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMMovimientoNeumatico).where(EAMMovimientoNeumatico.neumatico_id == nid)
        .order_by(EAMMovimientoNeumatico.fecha.desc())
    )
    return r.scalars().all()


# ── Configuración global del módulo ──
@router.get("/neumaticos/config", response_model=NeuConfigSchema)
async def get_config_neumatico(db: AsyncSession = Depends(get_db)):
    return await _get_config_neu(db)

@router.put("/neumaticos/config", response_model=NeuConfigSchema)
async def update_config_neumatico(data: NeuConfigSchema, db: AsyncSession = Depends(get_db)):
    cfg = await _get_config_neu(db)
    for k, v in data.model_dump().items():
        setattr(cfg, k, v)
    await db.commit(); await db.refresh(cfg)
    return cfg


# ── Zonas de llantas ──
@router.get("/neumaticos/zonas", response_model=List[ZonaNeumaticoResponse])
async def list_zonas_neumatico(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMZonaNeumatico).order_by(EAMZonaNeumatico.nombre))
    return r.scalars().all()

@router.post("/neumaticos/zonas", response_model=ZonaNeumaticoResponse)
async def create_zona_neumatico(data: ZonaNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMZonaNeumatico(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/zonas/{zid}", response_model=ZonaNeumaticoResponse)
async def update_zona_neumatico(zid: int, data: ZonaNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMZonaNeumatico, zid)
    if not obj:
        raise HTTPException(404, "Zona no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/zonas/{zid}", status_code=204)
async def delete_zona_neumatico(zid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMZonaNeumatico, zid)
    if obj:
        await db.delete(obj); await db.commit()


# ── Bandas de reencauche ──
@router.get("/neumaticos/bandas-reencauche", response_model=List[BandaReencaucheResponse])
async def list_bandas_reencauche(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMBandaReencauche).order_by(EAMBandaReencauche.marca))
    return r.scalars().all()

@router.post("/neumaticos/bandas-reencauche", response_model=BandaReencaucheResponse)
async def create_banda_reencauche(data: BandaReencaucheCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMBandaReencauche(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/bandas-reencauche/{bid}", response_model=BandaReencaucheResponse)
async def update_banda_reencauche(bid: int, data: BandaReencaucheCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMBandaReencauche, bid)
    if not obj:
        raise HTTPException(404, "Banda no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/bandas-reencauche/{bid}", status_code=204)
async def delete_banda_reencauche(bid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMBandaReencauche, bid)
    if obj:
        await db.delete(obj); await db.commit()


# ── Motivos de fin de vida ──
@router.get("/neumaticos/motivos-fin-vida", response_model=List[MotivoFinVidaResponse])
async def list_motivos_fin_vida(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMMotivoFinVida).order_by(EAMMotivoFinVida.nombre))
    return r.scalars().all()

@router.post("/neumaticos/motivos-fin-vida", response_model=MotivoFinVidaResponse)
async def create_motivo_fin_vida(data: MotivoFinVidaCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMMotivoFinVida(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/motivos-fin-vida/{mid}", response_model=MotivoFinVidaResponse)
async def update_motivo_fin_vida(mid: int, data: MotivoFinVidaCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMotivoFinVida, mid)
    if not obj:
        raise HTTPException(404, "Motivo no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/motivos-fin-vida/{mid}", status_code=204)
async def delete_motivo_fin_vida(mid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMotivoFinVida, mid)
    if obj:
        await db.delete(obj); await db.commit()


# ── Ajustes de valor (catálogo + aplicación por llanta) ──
@router.get("/neumaticos/ajustes-catalogo", response_model=List[AjusteNeuCatalogoResponse])
async def list_ajustes_catalogo(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMAjusteNeumaticoCatalogo).order_by(EAMAjusteNeumaticoCatalogo.nombre))
    return r.scalars().all()

@router.post("/neumaticos/ajustes-catalogo", response_model=AjusteNeuCatalogoResponse)
async def create_ajuste_catalogo(data: AjusteNeuCatalogoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMAjusteNeumaticoCatalogo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/ajustes-catalogo/{aid}", response_model=AjusteNeuCatalogoResponse)
async def update_ajuste_catalogo(aid: int, data: AjusteNeuCatalogoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMAjusteNeumaticoCatalogo, aid)
    if not obj:
        raise HTTPException(404, "Categoría de ajuste no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/ajustes-catalogo/{aid}", status_code=204)
async def delete_ajuste_catalogo(aid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMAjusteNeumaticoCatalogo, aid)
    if obj:
        await db.delete(obj); await db.commit()

@router.get("/neumaticos/{nid}/ajustes", response_model=List[AjusteNeuResponse])
async def list_ajustes_neumatico(nid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMAjusteNeumatico).where(EAMAjusteNeumatico.neumatico_id == nid)
        .order_by(EAMAjusteNeumatico.fecha.desc())
    )
    return r.scalars().all()

@router.post("/neumaticos/{nid}/ajustes", response_model=AjusteNeuResponse)
async def create_ajuste_neumatico(nid: int, data: AjusteNeuCreate, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    obj = EAMAjusteNeumatico(neumatico_id=nid, **data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ── Esquemas de vehículo (plantillas reutilizables) ──
@router.get("/neumaticos/esquemas", response_model=List[EsquemaVehiculoResponse])
async def list_esquemas_vehiculo(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMEsquemaVehiculo).order_by(EAMEsquemaVehiculo.nombre))
    return r.scalars().all()

@router.post("/neumaticos/esquemas", response_model=EsquemaVehiculoResponse)
async def create_esquema_vehiculo(data: EsquemaVehiculoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMEsquemaVehiculo(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/esquemas/{eid}", response_model=EsquemaVehiculoResponse)
async def update_esquema_vehiculo(eid: int, data: EsquemaVehiculoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMEsquemaVehiculo, eid)
    if not obj:
        raise HTTPException(404, "Esquema no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/esquemas/{eid}", status_code=204)
async def delete_esquema_vehiculo(eid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMEsquemaVehiculo, eid)
    if obj:
        await db.delete(obj); await db.commit()

@router.get("/neumaticos/esquemas/asignaciones/{activo_id}", response_model=List[EsquemaAsignacionResponse])
async def list_esquema_asignaciones(activo_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMEsquemaAsignacion).where(EAMEsquemaAsignacion.activo_id == activo_id)
        .order_by(EAMEsquemaAsignacion.fecha_vigencia.desc())
    )
    return r.scalars().all()

@router.post("/neumaticos/esquemas/asignar", response_model=EsquemaAsignacionResponse)
async def asignar_esquema_vehiculo(data: EsquemaAsignacionCreate, db: AsyncSession = Depends(get_db)):
    """Asigna un esquema de llantas a un vehículo: aplica número de ejes/repuesto
    directamente sobre el activo (reutiliza el generador de layout existente) y
    deja registro histórico de la vigencia."""
    activo = await db.get(EAMActivo, data.activo_id)
    if not activo:
        raise HTTPException(404, "Vehículo no encontrado")
    esquema = await db.get(EAMEsquemaVehiculo, data.esquema_id)
    if not esquema:
        raise HTTPException(404, "Esquema no encontrado")
    activo.numero_ejes = esquema.numero_ejes
    activo.layout_llantas = esquema.layout
    activo.tiene_repuesto = esquema.tiene_repuesto
    activo.cantidad_repuestos = esquema.cantidad_repuestos
    obj = EAMEsquemaAsignacion(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ── Trabajos de llantas y periodicidad ──
@router.get("/neumaticos/trabajos", response_model=List[TrabajoNeumaticoResponse])
async def list_trabajos_neumatico(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMTrabajoNeumatico).order_by(EAMTrabajoNeumatico.nombre))
    return r.scalars().all()

@router.post("/neumaticos/trabajos", response_model=TrabajoNeumaticoResponse)
async def create_trabajo_neumatico(data: TrabajoNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMTrabajoNeumatico(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/trabajos/{tid}", response_model=TrabajoNeumaticoResponse)
async def update_trabajo_neumatico(tid: int, data: TrabajoNeumaticoCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMTrabajoNeumatico, tid)
    if not obj:
        raise HTTPException(404, "Trabajo no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/trabajos/{tid}", status_code=204)
async def delete_trabajo_neumatico(tid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMTrabajoNeumatico, tid)
    if obj:
        await db.delete(obj); await db.commit()

@router.get("/neumaticos/trabajos/periodicidad", response_model=List[PeriodicidadTrabajoResponse])
async def list_periodicidad_trabajos(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMPeriodicidadTrabajoNeumatico))
    return r.scalars().all()

@router.post("/neumaticos/trabajos/periodicidad", response_model=PeriodicidadTrabajoResponse)
async def create_periodicidad_trabajo(data: PeriodicidadTrabajoCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMPeriodicidadTrabajoNeumatico(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.delete("/neumaticos/trabajos/periodicidad/{pid}", status_code=204)
async def delete_periodicidad_trabajo(pid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMPeriodicidadTrabajoNeumatico, pid)
    if obj:
        await db.delete(obj); await db.commit()

@router.get("/neumaticos/{nid}/trabajos", response_model=List[TrabajoRealizadoResponse])
async def list_trabajos_realizados(nid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMTrabajoRealizadoNeumatico).where(EAMTrabajoRealizadoNeumatico.neumatico_id == nid)
        .order_by(EAMTrabajoRealizadoNeumatico.fecha.desc())
    )
    return r.scalars().all()

@router.post("/neumaticos/{nid}/trabajos", response_model=TrabajoRealizadoResponse)
async def create_trabajo_realizado(nid: int, data: TrabajoRealizadoCreate, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    obj = EAMTrabajoRealizadoNeumatico(neumatico_id=nid, **data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ── Ciclo de vida: reesculturado, recuperar banda, cambiar zona, vidas ──

async def _get_or_create_ajuste_motivo(db: AsyncSession, nombre: str) -> EAMAjusteNeumaticoCatalogo:
    r = await db.execute(select(EAMAjusteNeumaticoCatalogo).where(EAMAjusteNeumaticoCatalogo.nombre == nombre))
    obj = r.scalar_one_or_none()
    if not obj:
        obj = EAMAjusteNeumaticoCatalogo(nombre=nombre, activo=True)
        db.add(obj)
        await db.flush()
    return obj

async def _vida_abierta(db: AsyncSession, neumatico_id: int) -> Optional[EAMVidaNeumatico]:
    r = await db.execute(
        select(EAMVidaNeumatico)
        .where(EAMVidaNeumatico.neumatico_id == neumatico_id, EAMVidaNeumatico.fecha_fin.is_(None))
        .order_by(EAMVidaNeumatico.numero_vida.desc())
    )
    return r.scalars().first()

@router.post("/neumaticos/{nid}/reesculturar", response_model=ReesculturadoResponse)
async def reesculturar_neumatico(nid: int, data: ReesculturadoCreate, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    obj = EAMReesculturado(
        neumatico_id=nid, fecha=data.fecha, km_odometro=data.km_odometro,
        proveedor=data.proveedor, costo=data.costo,
        profundidad_anterior=neu.profundidad_actual, profundidad_nueva=data.profundidad_nueva,
    )
    neu.profundidad_actual = data.profundidad_nueva
    # Se tallan los tres surcos, no solo el central: dejar los hombros con los
    # milímetros de antes hacía que el reporte de desgaste irregular mostrara una
    # diferencia entre hombros que ya no existía.
    neu.profundidad_externa = data.profundidad_nueva
    neu.profundidad_interna = data.profundidad_nueva
    if data.costo:
        neu.costo = (neu.costo or 0) + data.costo
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/reesculturado/{resc_id}/deshacer", response_model=ReesculturadoResponse)
async def deshacer_reesculturado(resc_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMReesculturado, resc_id)
    if not obj:
        raise HTTPException(404, "Registro de reesculturado no encontrado")
    if obj.deshecho:
        raise HTTPException(409, "Este reesculturado ya fue deshecho")
    neu = await db.get(EAMNeumatico, obj.neumatico_id)
    if neu:
        neu.profundidad_actual = obj.profundidad_anterior
        if obj.costo:
            neu.costo = max((neu.costo or 0) - obj.costo, 0)
    obj.deshecho = True
    obj.fecha_deshecho = datetime.utcnow()
    await db.commit(); await db.refresh(obj)
    return obj

@router.get("/neumaticos/{nid}/reesculturados", response_model=List[ReesculturadoResponse])
async def list_reesculturados(nid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMReesculturado).where(EAMReesculturado.neumatico_id == nid)
        .order_by(EAMReesculturado.fecha.desc())
    )
    return r.scalars().all()

@router.post("/neumaticos/{nid}/recuperar-banda")
async def recuperar_banda(nid: int, data: RecuperarBandaCreate, db: AsyncSession = Depends(get_db)):
    """Transfiere la banda en buen estado de una carcasa dañada (origen) hacia
    otra llanta destino: mueve mm/costo proporcional y descarta la llanta origen."""
    origen = await db.get(EAMNeumatico, nid)
    destino = await db.get(EAMNeumatico, data.neumatico_destino_id)
    if not origen or not destino:
        raise HTTPException(404, "Neumático no encontrado")
    if origen.id == destino.id:
        raise HTTPException(400, "El origen y destino deben ser llantas distintas")

    mm = data.mm_transferidos if data.mm_transferidos is not None else origen.profundidad_actual
    costo = data.costo_transferido or 0

    if mm is not None:
        destino.profundidad_actual = mm
        if destino.profundidad_diseño is None or destino.profundidad_diseño < mm:
            destino.profundidad_diseño = mm
    if costo:
        destino.costo = (destino.costo or 0) + costo
        motivo = await _get_or_create_ajuste_motivo(db, "Recuperación de banda")
        db.add(EAMAjusteNeumatico(
            neumatico_id=origen.id, motivo_id=motivo.id, fecha=data.fecha.date(),
            valor=costo, comentarios=data.observaciones or f"Banda recuperada hacia {destino.codigo}",
        ))

    origen.estado = "BAJA"
    origen.motivo_baja = f"Recuperación de banda hacia {destino.codigo}"
    origen.fecha_baja = data.fecha.date()
    origen.activo_id = None; origen.posicion = None

    vida = await _vida_abierta(db, origen.id)
    if vida:
        vida.fecha_fin = data.fecha
        vida.km_fin = origen.km_actual
        vida.profundidad_final = origen.profundidad_actual

    obs = data.observaciones or f"Recuperación de banda: {origen.codigo} → {destino.codigo}"
    db.add(EAMMovimientoNeumatico(neumatico_id=origen.id, tipo_movimiento="RECUPERACION_BANDA", fecha=data.fecha, observaciones=obs))
    db.add(EAMMovimientoNeumatico(neumatico_id=destino.id, tipo_movimiento="RECUPERACION_BANDA", fecha=data.fecha, observaciones=obs))

    await db.commit()
    return {"ok": True, "origen": origen.codigo, "destino": destino.codigo, "mm_transferidos": mm, "costo_transferido": costo}

@router.post("/neumaticos/{nid}/cambiar-zona")
async def cambiar_zona_neumatico(nid: int, data: CambiarZonaCreate, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    zona = await db.get(EAMZonaNeumatico, data.zona_id)
    if not zona:
        raise HTTPException(404, "Zona no encontrada")
    zona_anterior = neu.zona_id
    neu.zona_id = data.zona_id
    db.add(EAMMovimientoNeumatico(
        neumatico_id=nid, tipo_movimiento="CAMBIO_ZONA", fecha=data.fecha,
        observaciones=data.observaciones or f"Cambio de zona → {zona.nombre}",
    ))
    await db.commit()
    return {"ok": True, "zona_id": neu.zona_id, "zona_anterior_id": zona_anterior}

@router.get("/neumaticos/{nid}/vidas", response_model=List[VidaNeumaticoResponse])
async def list_vidas_neumatico(nid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMVidaNeumatico).where(EAMVidaNeumatico.neumatico_id == nid)
        .order_by(EAMVidaNeumatico.numero_vida.desc())
    )
    return r.scalars().all()


# ── Informe consolidado y Histórico de la llanta ──

@router.get("/neumaticos/{nid}/informe")
async def informe_neumatico(nid: int, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")

    mov_r = await db.execute(
        select(EAMMovimientoNeumatico).where(EAMMovimientoNeumatico.neumatico_id == nid)
        .order_by(EAMMovimientoNeumatico.fecha.asc())
    )
    movimientos = mov_r.scalars().all()

    montajes_rotaciones, ubicaciones, zonas_hist = [], [], []
    km_anterior = None
    for m in movimientos:
        if m.tipo_movimiento in ("INSTALACION", "ROTACION", "DESMONTAJE", "VOLTEO"):
            distancia = None
            if km_anterior is not None and m.km_odometro is not None:
                distancia = max(m.km_odometro - km_anterior, 0)
            if m.km_odometro is not None:
                km_anterior = m.km_odometro
            montajes_rotaciones.append({
                "id": m.id, "tipo": m.tipo_movimiento, "fecha": m.fecha, "activo_id": m.activo_id,
                "posicion_origen": m.posicion_origen, "posicion": m.posicion,
                "km_odometro": m.km_odometro, "distancia_recorrida": distancia,
                "observaciones": m.observaciones, "tecnico": m.tecnico,
            })
        if m.bodega_id:
            ubicaciones.append({"id": m.id, "fecha": m.fecha, "bodega_id": m.bodega_id, "observaciones": m.observaciones})
        if m.tipo_movimiento == "CAMBIO_ZONA":
            zonas_hist.append({"id": m.id, "fecha": m.fecha, "observaciones": m.observaciones})

    insp_r = await db.execute(
        select(EAMInspeccionNeumatico).where(EAMInspeccionNeumatico.neumatico_id == nid)
        .order_by(EAMInspeccionNeumatico.fecha.desc())
    )
    trab_r = await db.execute(
        select(EAMTrabajoRealizadoNeumatico).where(EAMTrabajoRealizadoNeumatico.neumatico_id == nid)
        .order_by(EAMTrabajoRealizadoNeumatico.fecha.desc())
    )

    return {
        "neumatico_id": neu.id, "codigo": neu.codigo,
        "montajes_rotaciones": montajes_rotaciones,
        "ubicaciones": ubicaciones,
        "zonas": zonas_hist,
        "inspecciones": [InspeccionNeuResponse.model_validate(i) for i in insp_r.scalars().all()],
        "trabajos": [TrabajoRealizadoResponse.model_validate(t) for t in trab_r.scalars().all()],
    }

@router.get("/neumaticos/{nid}/historico")
async def historico_neumatico(nid: int, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")

    vidas_r = await db.execute(
        select(EAMVidaNeumatico).where(EAMVidaNeumatico.neumatico_id == nid).order_by(EAMVidaNeumatico.numero_vida)
    )
    vidas = vidas_r.scalars().all()

    resc_r = await db.execute(
        select(EAMReesculturado).where(EAMReesculturado.neumatico_id == nid, EAMReesculturado.deshecho == False)  # noqa: E712
    )
    costo_reesculturados = sum((r.costo or 0) for r in resc_r.scalars().all())

    trab_r = await db.execute(select(EAMTrabajoRealizadoNeumatico).where(EAMTrabajoRealizadoNeumatico.neumatico_id == nid))
    costo_trabajos = sum((t.costo_unitario or 0) * (t.cantidad or 1) for t in trab_r.scalars().all())

    ajustes_r = await db.execute(select(EAMAjusteNeumatico).where(EAMAjusteNeumatico.neumatico_id == nid))
    costo_ajustes = sum(a.valor for a in ajustes_r.scalars().all())

    veh_r = await db.execute(
        select(EAMMovimientoNeumatico.activo_id).where(
            EAMMovimientoNeumatico.neumatico_id == nid, EAMMovimientoNeumatico.activo_id.isnot(None)
        ).distinct()
    )
    vehiculos_ids = [v for (v,) in veh_r.all()]

    costo_nueva = next((v.costo for v in vidas if v.tipo == "NUEVA"), None)
    costo_reencauches = sum((v.costo or 0) for v in vidas if v.tipo == "REENCAUCHADA")

    ubicacion_actual = "—"
    if neu.activo_id:
        ubicacion_actual = f"Vehículo #{neu.activo_id}" + (f" · {neu.posicion}" if neu.posicion else "")
    elif neu.bodega_id:
        bodega = await db.get(EAMBodegaNeumatico, neu.bodega_id)
        ubicacion_actual = bodega.nombre if bodega else f"Bodega #{neu.bodega_id}"

    return {
        "informacion_basica": {
            "id": neu.id, "codigo": neu.codigo, "marca": neu.marca, "referencia": neu.referencia,
            "medida": neu.medida, "estado": neu.estado, "ubicacion_actual": ubicacion_actual,
        },
        "resumen_estadistico": {
            "numero_vidas": len(vidas),
            "numero_reencauches": neu.reencauches,
            "vehiculos_distintos": len(vehiculos_ids),
            "km_total_acumulado": neu.km_total,
            "costo_nueva": costo_nueva,
            "costo_reencauches": round(costo_reencauches, 2) if costo_reencauches else costo_reencauches,
            "costo_reesculturados": round(costo_reesculturados, 2) if costo_reesculturados else costo_reesculturados,
            "costo_trabajos": round(costo_trabajos, 2) if costo_trabajos else costo_trabajos,
            "costo_ajustes": round(costo_ajustes, 2) if costo_ajustes else costo_ajustes,
        },
        "vidas": [VidaNeumaticoResponse.model_validate(v) for v in vidas],
    }


# ── Congelar datos (snapshot histórico para comparación) ──

@router.post("/neumaticos/congelar", response_model=CongeladoResponse)
async def crear_congelado(data: CongeladoCreate, db: AsyncSession = Depends(get_db)):
    cfg = await _get_config_neu(db)
    r = await db.execute(select(EAMNeumatico).where(EAMNeumatico.estado != "BAJA"))
    neumaticos = r.scalars().all()

    ajustes_r = await db.execute(
        select(EAMAjusteNeumatico.neumatico_id, func.sum(EAMAjusteNeumatico.valor))
        .group_by(EAMAjusteNeumatico.neumatico_id)
    )
    ajustes_map = {nid: total or 0 for nid, total in ajustes_r.all()}

    congelado = EAMCongeladoNeumatico(fecha=datetime.utcnow(), descripcion=data.descripcion)
    db.add(congelado)
    await db.flush()

    for n in neumaticos:
        km = n.km_total or 0
        pd_ = n.profundidad_diseño
        pa = n.profundidad_actual
        mm_gastados = (pd_ - pa) if (pd_ is not None and pa is not None) else None
        ajustes = ajustes_map.get(n.id, 0)
        costo_neto = max((n.costo or 0) - ajustes, 0) if (n.costo or ajustes) else None
        cpk = (costo_neto / km) if (costo_neto and km > 0) else None
        costo_mm = (costo_neto / mm_gastados) if (costo_neto and mm_gastados and mm_gastados > 0) else None
        db.add(EAMCongeladoDetalleNeumatico(
            congelado_id=congelado.id, neumatico_id=n.id, codigo=n.codigo, marca=n.marca, medida=n.medida,
            estado=n.estado, km_total=km, costo=n.costo, costo_neto=costo_neto,
            cpk=round(cpk, 2) if cpk else None, costo_mm=round(costo_mm, 2) if costo_mm else None,
            mm_gastados=round(mm_gastados, 1) if mm_gastados is not None else None,
        ))

    await db.commit()
    await db.refresh(congelado)
    return congelado

@router.get("/neumaticos/congelados", response_model=List[CongeladoResponse])
async def list_congelados(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMCongeladoNeumatico).order_by(EAMCongeladoNeumatico.fecha.desc()))
    return r.scalars().all()

@router.get("/neumaticos/congelados/{cid}/detalle", response_model=List[CongeladoDetalleResponse])
async def list_congelado_detalle(cid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMCongeladoDetalleNeumatico).where(EAMCongeladoDetalleNeumatico.congelado_id == cid)
        .order_by(EAMCongeladoDetalleNeumatico.codigo)
    )
    return r.scalars().all()

@router.delete("/neumaticos/congelados/{cid}", status_code=204)
async def delete_congelado(cid: int, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sa_delete
    obj = await db.get(EAMCongeladoNeumatico, cid)
    if obj:
        await db.execute(sa_delete(EAMCongeladoDetalleNeumatico).where(EAMCongeladoDetalleNeumatico.congelado_id == cid))
        await db.delete(obj)
        await db.commit()


# ── Importación y eliminación masiva de llantas ──

class NeumaticoBulkCreate(BaseModel):
    items: List[NeumaticCreate]

class NeumaticoBulkDeleteRequest(BaseModel):
    ids: List[int]
    confirmacion: str

async def _eliminar_neumatico_con_hijos(db: AsyncSession, nid: int) -> None:
    from sqlalchemy import delete as sa_delete
    for modelo in (
        EAMMovimientoNeumatico, EAMInspeccionNeumatico, EAMVidaNeumatico,
        EAMReesculturado, EAMAjusteNeumatico, EAMTrabajoRealizadoNeumatico,
        EAMReencaucheDetalle, EAMCongeladoDetalleNeumatico,
    ):
        await db.execute(sa_delete(modelo).where(modelo.neumatico_id == nid))
    await db.execute(sa_delete(EAMNeumatico).where(EAMNeumatico.id == nid))

def _mensaje_error_fila(e: Exception, codigo: Optional[str] = None) -> str:
    """Traduce los errores de base de datos a algo entendible para el usuario.
    Sin esto, la interfaz mostraba el volcado completo de SQLAlchemy (SQL,
    parámetros y traza) dentro del listado de errores de la carga masiva."""
    texto = str(e)
    if "UniqueViolationError" in texto or "duplicate key value" in texto:
        return f"El código {codigo} ya está registrado." if codigo else "El código ya está registrado."
    if "ForeignKeyViolationError" in texto or "violates foreign key" in texto:
        return "Alguna referencia no existe (bodega, zona o catálogo). Verifica los datos de la fila."
    if "NotNullViolationError" in texto or "null value in column" in texto:
        return "Faltan datos obligatorios en la fila."
    if "invalid input syntax" in texto or "DataError" in texto:
        return "Hay un valor con formato inválido (por ejemplo texto donde se espera un número)."
    # Caso no contemplado: se recorta para no volcar la traza entera en pantalla.
    return texto.splitlines()[0][:200] if texto else "Error al procesar la fila."


@router.post("/neumaticos/bulk")
async def crear_neumaticos_masivo(data: NeumaticoBulkCreate, db: AsyncSession = Depends(get_db)):
    exitosos = 0
    errores = []
    for i, item in enumerate(data.items):
        try:
            valores = await _preparar_neumatico(db, item)
            async with db.begin_nested():
                obj = EAMNeumatico(**valores)
                db.add(obj)
                await db.flush()
                reencauches = obj.reencauches or 0
                db.add(EAMVidaNeumatico(
                    neumatico_id=obj.id,
                    numero_vida=reencauches + 1,
                    tipo="NUEVA" if reencauches == 0 else "REENCAUCHADA",
                    fecha_inicio=datetime.utcnow(), km_inicio=obj.km_inicio or 0,
                    costo=obj.costo, profundidad_inicial=obj.profundidad_diseño,
                ))
            exitosos += 1
        except ValueError as e:
            errores.append({"fila": i + 2, "codigo": item.codigo, "mensaje": str(e)})
        except Exception as e:
            errores.append({"fila": i + 2, "codigo": item.codigo, "mensaje": _mensaje_error_fila(e, item.codigo)})
    await db.commit()
    return {"total": len(data.items), "exitosos": exitosos, "errores": errores}

@router.post("/neumaticos/bulk-delete")
async def eliminar_neumaticos_masivo(data: NeumaticoBulkDeleteRequest, db: AsyncSession = Depends(get_db)):
    if data.confirmacion.strip().upper() != "ELIMINAR":
        raise HTTPException(400, "Debes escribir ELIMINAR para confirmar")
    eliminados = 0
    for nid in data.ids:
        obj = await db.get(EAMNeumatico, nid)
        if obj:
            await _eliminar_neumatico_con_hijos(db, nid)
            eliminados += 1
    await db.commit()
    return {"eliminados": eliminados, "solicitados": len(data.ids)}


# ── Inspecciones ──
def _min_prof(*vals) -> Optional[float]:
    xs = [v for v in vals if v is not None]
    return min(xs) if xs else None

@router.post("/neumaticos/{nid}/inspecciones", response_model=InspeccionNeuResponse)
async def crear_inspeccion(nid: int, data: InspeccionNeuCreate, db: AsyncSession = Depends(get_db)):
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    # Una inspección con fecha anterior al último movimiento mediría la llanta
    # en una posición donde ya no estaba, y además pisaría la profundidad actual
    # con un dato viejo.
    data.fecha = _fecha_naive(data.fecha)
    mov_r = await db.execute(
        select(EAMMovimientoNeumatico.fecha).where(EAMMovimientoNeumatico.neumatico_id == nid)
        .order_by(EAMMovimientoNeumatico.fecha.desc()).limit(1)
    )
    ultimo_mov = mov_r.scalar_one_or_none()
    if ultimo_mov and data.fecha < ultimo_mov:
        raise HTTPException(
            409,
            f"La llanta tuvo un movimiento posterior ({ultimo_mov:%Y-%m-%d %H:%M}) a la fecha de "
            "esta inspección. Corrige la fecha.",
        )
    # La lectura tampoco puede retroceder: es la que fija el recorrido acumulado
    # de la llanta.
    if data.km_odometro is not None and neu.activo_id:
        activo_insp = await db.get(EAMActivo, neu.activo_id)
        if activo_insp:
            err_lectura = _validar_lectura(activo_insp, neu, data.km_odometro, None)
            if err_lectura:
                raise HTTPException(409, err_lectura)
    referencia = await _referencia_profundidad(db, neu)
    err_prof = _validar_profundidad(
        referencia, data.profundidad_izq, data.profundidad_centro,
        data.profundidad_der, neu.codigo)
    if err_prof:
        raise HTTPException(409, err_prof)

    obj = EAMInspeccionNeumatico(neumatico_id=nid, **data.model_dump())
    if obj.posicion is None:
        obj.posicion = neu.posicion
    db.add(obj)
    # Actualiza el estado actual del neumático con la última medición.
    # Convención: profundidad_izq = hombro EXTERNO, profundidad_der = hombro INTERNO.
    pmin = _min_prof(data.profundidad_izq, data.profundidad_centro, data.profundidad_der)
    if pmin is not None:
        neu.profundidad_actual = pmin
    if data.profundidad_izq is not None:
        neu.profundidad_externa = data.profundidad_izq
    if data.profundidad_der is not None:
        neu.profundidad_interna = data.profundidad_der
    if data.presion_psi is not None:
        neu.presion_actual = data.presion_psi
    if data.km_odometro is not None:
        neu.km_actual = data.km_odometro
        neu.km_total = max(0.0, (neu.km_actual or 0) - (neu.km_inicio or 0))
    await db.commit(); await db.refresh(obj)
    r = InspeccionNeuResponse.model_validate(obj)
    r.profundidad_min = _min_prof(obj.profundidad_izq, obj.profundidad_centro, obj.profundidad_der)
    return r


# ── Inspecciones masivas (carga por archivo plano, referenciando la llanta por código) ──
class InspeccionBulkItem(BaseModel):
    codigo: str
    fecha: datetime
    profundidad_izq: Optional[float] = None
    profundidad_centro: Optional[float] = None
    profundidad_der: Optional[float] = None
    presion_psi: Optional[float] = None
    km_odometro: Optional[float] = None
    estado_visual: Optional[str] = None
    tecnico: Optional[str] = None
    observaciones: Optional[str] = None

class InspeccionBulkCreate(BaseModel):
    items: List[InspeccionBulkItem]

@router.post("/neumaticos/inspecciones/bulk")
async def crear_inspecciones_masivo(data: InspeccionBulkCreate, db: AsyncSession = Depends(get_db)):
    exitosos = 0
    errores = []
    for i, item in enumerate(data.items):
        try:
            async with db.begin_nested():
                r = await db.execute(select(EAMNeumatico).where(EAMNeumatico.codigo == item.codigo))
                neu = r.scalar_one_or_none()
                if not neu:
                    raise ValueError(f"Llanta con código '{item.codigo}' no encontrada")
                # Un archivo con mil filas es justo donde un dato equivocado pasa
                # sin que nadie lo mire, así que la carga masiva valida lo mismo
                # que la pantalla: la lectura no retrocede y el labrado no crece.
                if item.km_odometro is not None and neu.activo_id:
                    activo_bulk = await db.get(EAMActivo, neu.activo_id)
                    if activo_bulk:
                        err_lectura = _validar_lectura(activo_bulk, neu, item.km_odometro, None)
                        if err_lectura:
                            raise ValueError(err_lectura)
                referencia = await _referencia_profundidad(db, neu)
                err_prof = _validar_profundidad(
                    referencia, item.profundidad_izq, item.profundidad_centro,
                    item.profundidad_der, neu.codigo)
                if err_prof:
                    raise ValueError(err_prof)
                obj = EAMInspeccionNeumatico(
                    neumatico_id=neu.id, posicion=neu.posicion, fecha=item.fecha,
                    profundidad_izq=item.profundidad_izq, profundidad_centro=item.profundidad_centro,
                    profundidad_der=item.profundidad_der, presion_psi=item.presion_psi,
                    km_odometro=item.km_odometro, estado_visual=item.estado_visual,
                    tecnico=item.tecnico, observaciones=item.observaciones,
                )
                db.add(obj)
                pmin = _min_prof(item.profundidad_izq, item.profundidad_centro, item.profundidad_der)
                if pmin is not None:
                    neu.profundidad_actual = pmin
                if item.profundidad_izq is not None:
                    neu.profundidad_externa = item.profundidad_izq
                if item.profundidad_der is not None:
                    neu.profundidad_interna = item.profundidad_der
                if item.presion_psi is not None:
                    neu.presion_actual = item.presion_psi
                if item.km_odometro is not None:
                    neu.km_actual = item.km_odometro
                    neu.km_total = max(0.0, (neu.km_actual or 0) - (neu.km_inicio or 0))
            exitosos += 1
        except Exception as e:
            errores.append({"fila": i + 2, "codigo": item.codigo, "mensaje": str(e)})
    await db.commit()
    return {"total": len(data.items), "exitosos": exitosos, "errores": errores}

class ReferenciaProfundidadResponse(BaseModel):
    """Lo que hay que tener a la vista antes de anotar una profundidad."""
    neumatico_id: int
    codigo: str
    origen: str                       # inspección / reesculturado / reencauche / ficha
    fecha: Optional[datetime] = None
    profundidad_izq: Optional[float] = None
    profundidad_centro: Optional[float] = None
    profundidad_der: Optional[float] = None
    km_odometro: Optional[float] = None
    profundidad_diseno: Optional[float] = None
    profundidad_minima: Optional[float] = None
    tolerancia: float = 0.5
    reencauches: int = 0


@router.get("/neumaticos/{nid}/referencia-profundidad",
            response_model=ReferenciaProfundidadResponse)
async def referencia_profundidad(nid: int, db: AsyncSession = Depends(get_db)):
    """La última profundidad de cada surco, para mostrarla al medir.

    Existe porque el formulario pedía tres números sin decir contra qué. Quien
    mide no puede saber si 8,5 mm está bien o es un error de un dígito sin ver
    que la vez pasada iban 9,2; y sin esa referencia el error se anota, se
    guarda y solo aparece meses después como un desgaste imposible.

    Devuelve también de dónde sale la referencia: no es lo mismo comparar contra
    la medición del mes pasado que contra un reencauche reciente.
    """
    neu = await db.get(EAMNeumatico, nid)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    ref = await _referencia_profundidad(db, neu)
    return ReferenciaProfundidadResponse(
        neumatico_id=nid, codigo=neu.codigo, **ref)


@router.get("/neumaticos/referencias-profundidad",
            response_model=List[ReferenciaProfundidadResponse])
async def referencias_profundidad(
    activo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Lo mismo, para todas las llantas de un vehículo de una vez.

    La inspección de sesión mide las seis o diez llantas del vehículo en una
    sola pantalla; pedir la referencia de cada una por separado sería una
    llamada por fila y la tabla se llenaría a pedazos.
    """
    consulta = select(EAMNeumatico).where(EAMNeumatico.estado != "BAJA")
    if activo_id:
        consulta = consulta.where(EAMNeumatico.activo_id == activo_id)
    neumaticos = list((await db.execute(consulta)).scalars().all())
    salida = []
    for neu in neumaticos:
        ref = await _referencia_profundidad(db, neu)
        salida.append(ReferenciaProfundidadResponse(
            neumatico_id=neu.id, codigo=neu.codigo, **ref))
    return salida


@router.get("/neumaticos/{nid}/inspecciones", response_model=List[InspeccionNeuResponse])
async def list_inspecciones(nid: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(EAMInspeccionNeumatico).where(EAMInspeccionNeumatico.neumatico_id == nid)
        .order_by(EAMInspeccionNeumatico.fecha.asc())
    )
    out = []
    for i in r.scalars().all():
        resp = InspeccionNeuResponse.model_validate(i)
        resp.profundidad_min = _min_prof(i.profundidad_izq, i.profundidad_centro, i.profundidad_der)
        out.append(resp)
    return out


# ── Indicadores / CPK ──
@router.get("/neumaticos/indicadores", response_model=List[IndicadorNeuResponse])
async def indicadores_neumaticos(db: AsyncSession = Depends(get_db)):
    cfg = await _get_config_neu(db)
    r = await db.execute(select(EAMNeumatico).where(EAMNeumatico.estado != "BAJA"))
    neumaticos = r.scalars().all()

    ajustes_r = await db.execute(
        select(EAMAjusteNeumatico.neumatico_id, func.sum(EAMAjusteNeumatico.valor))
        .group_by(EAMAjusteNeumatico.neumatico_id)
    )
    ajustes_map = {nid: total or 0 for nid, total in ajustes_r.all()}

    out: List[IndicadorNeuResponse] = []
    for n in neumaticos:
        km = n.km_total or 0
        pd = n.profundidad_diseño
        pa = n.profundidad_actual
        mm_gastados = (pd - pa) if (pd is not None and pa is not None) else None
        usable = (pd - cfg.profundidad_minima) if pd is not None else None
        ajustes = ajustes_map.get(n.id, 0)
        costo_neto = max((n.costo or 0) - ajustes, 0) if (n.costo or ajustes) else None
        cpk = (costo_neto / km) if (costo_neto and km > 0) else None
        costo_mm = (costo_neto / mm_gastados) if (costo_neto and mm_gastados and mm_gastados > 0) else None
        km_proy = None
        if mm_gastados and mm_gastados > 0 and km > 0 and usable and usable > 0:
            km_proy = round(usable * km / mm_gastados, 0)
        pct = round(mm_gastados / usable * 100, 1) if (mm_gastados is not None and usable and usable > 0) else None
        out.append(IndicadorNeuResponse(
            neumatico_id=n.id, codigo=n.codigo, marca=n.marca, medida=n.medida,
            estado=n.estado, posicion=n.posicion, km_total=km, costo=n.costo,
            ajustes=round(ajustes, 2) if ajustes else None,
            costo_neto=round(costo_neto, 2) if costo_neto is not None else None,
            cpk=round(cpk, 2) if cpk else None, costo_mm=round(costo_mm, 2) if costo_mm else None,
            mm_gastados=round(mm_gastados, 1) if mm_gastados is not None else None,
            vida_util_km=n.vida_util_km, km_proyectado=km_proy, pct_desgaste=pct,
        ))
    return out


class UltimaInspeccionResponse(BaseModel):
    neumatico_id: int
    codigo: str
    marca: Optional[str] = None
    referencia: Optional[str] = None
    medida: Optional[str] = None
    estado: Optional[str] = None
    # Ubicacion actual
    activo_id: Optional[int] = None
    vehiculo: Optional[str] = None
    posicion: Optional[str] = None
    # Vida en curso: VN o R{n}
    vida: Optional[str] = None
    # Ultima inspeccion registrada
    fecha_ultima: Optional[datetime] = None
    profundidad_min: Optional[float] = None
    presion_psi: Optional[float] = None
    tecnico: Optional[str] = None
    dias_desde: Optional[int] = None
    # Metricas de la vida actual
    km_vida: Optional[float] = None
    costo_vida: Optional[float] = None
    cpk: Optional[float] = None


@router.get("/neumaticos/inspecciones/ultimas", response_model=List[UltimaInspeccionResponse])
async def ultimas_inspecciones(db: AsyncSession = Depends(get_db)):
    """Una fila por llanta con su ultima inspeccion y los indicadores de la vida
    en curso: profundidad minima medida, kilometraje recorrido en esa vida y CPK.
    Se ordena por fecha de inspeccion descendente; las que nunca se inspeccionaron
    quedan al final."""
    r = await db.execute(select(EAMNeumatico).where(EAMNeumatico.estado != "BAJA"))
    neumaticos = r.scalars().all()
    if not neumaticos:
        return []
    ids = [n.id for n in neumaticos]

    # Ultima inspeccion de cada llanta
    r = await db.execute(
        select(EAMInspeccionNeumatico)
        .where(EAMInspeccionNeumatico.neumatico_id.in_(ids))
        .order_by(EAMInspeccionNeumatico.neumatico_id, EAMInspeccionNeumatico.fecha.desc())
    )
    ultima_por_llanta = {}
    for insp in r.scalars().all():
        if insp.neumatico_id not in ultima_por_llanta:
            ultima_por_llanta[insp.neumatico_id] = insp

    # Vida abierta de cada llanta (para km y costo de esa vida)
    r = await db.execute(
        select(EAMVidaNeumatico)
        .where(EAMVidaNeumatico.neumatico_id.in_(ids), EAMVidaNeumatico.fecha_fin.is_(None))
    )
    vida_por_llanta = {v.neumatico_id: v for v in r.scalars().all()}

    # Nombre del vehiculo donde esta montada
    activos_ids = [n.activo_id for n in neumaticos if n.activo_id]
    vehiculos = {}
    if activos_ids:
        r = await db.execute(select(EAMActivo).where(EAMActivo.id.in_(activos_ids)))
        for a in r.scalars().all():
            vehiculos[a.id] = a.placa or a.codigo

    ahora = datetime.utcnow()
    salida: List[UltimaInspeccionResponse] = []
    for n in neumaticos:
        insp = ultima_por_llanta.get(n.id)
        vida = vida_por_llanta.get(n.id)

        # Con registro de vida se toma el km recorrido desde que inicio esa vida.
        # Las llantas anteriores al registro de vidas no lo tienen: para esas se
        # usa el km acumulado de la llanta, que es la mejor aproximacion y es el
        # mismo criterio que usa el calculo de indicadores.
        if vida is not None and n.km_actual is not None:
            km_vida = max(0.0, (n.km_actual or 0) - (vida.km_inicio or 0))
        else:
            km_vida = n.km_total
        costo_vida = (vida.costo if vida is not None else None) or n.costo
        cpk = (costo_vida / km_vida) if (costo_vida and km_vida and km_vida > 0) else None

        reenc = n.reencauches or 0
        dias = None
        if insp is not None and insp.fecha is not None:
            dias = max(0, (ahora - insp.fecha).days)

        salida.append(UltimaInspeccionResponse(
            neumatico_id=n.id, codigo=n.codigo, marca=n.marca, referencia=n.referencia,
            medida=n.medida, estado=n.estado,
            activo_id=n.activo_id, vehiculo=vehiculos.get(n.activo_id), posicion=n.posicion,
            vida="VN" if reenc == 0 else "R%d" % reenc,
            fecha_ultima=insp.fecha if insp is not None else None,
            profundidad_min=_min_prof(
                insp.profundidad_izq, insp.profundidad_centro, insp.profundidad_der
            ) if insp is not None else n.profundidad_actual,
            presion_psi=insp.presion_psi if insp is not None else n.presion_actual,
            tecnico=insp.tecnico if insp is not None else None,
            dias_desde=dias,
            km_vida=round(km_vida, 1) if km_vida is not None else None,
            costo_vida=costo_vida,
            cpk=round(cpk, 2) if cpk else None,
        ))

    # Mas reciente primero; sin inspeccion al final
    salida.sort(key=lambda x: (x.fecha_ultima is None, -(x.fecha_ultima.timestamp() if x.fecha_ultima else 0)))
    return salida


class InspeccionHistorialResponse(BaseModel):
    id: int
    neumatico_id: int
    codigo: str
    marca: Optional[str] = None
    referencia: Optional[str] = None
    medida: Optional[str] = None
    estado_llanta: Optional[str] = None
    vida: Optional[str] = None
    activo_id: Optional[int] = None
    vehiculo: Optional[str] = None
    posicion: Optional[str] = None
    fecha: Optional[datetime] = None
    profundidad_izq: Optional[float] = None
    profundidad_centro: Optional[float] = None
    profundidad_der: Optional[float] = None
    profundidad_min: Optional[float] = None
    presion_psi: Optional[float] = None
    km_odometro: Optional[float] = None
    estado_visual: Optional[str] = None
    observaciones: Optional[str] = None
    tecnico: Optional[str] = None


@router.get("/neumaticos/inspecciones", response_model=List[InspeccionHistorialResponse])
async def historial_inspecciones(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    activo_id: Optional[int] = None,
    neumatico_id: Optional[int] = None,
    limite: int = 5000,
    db: AsyncSession = Depends(get_db),
):
    """Todas las inspecciones registradas (no solo la ultima de cada llanta),
    de la mas reciente a la mas antigua, con los datos de la llanta y del
    vehiculo donde estaba montada."""
    q = select(EAMInspeccionNeumatico, EAMNeumatico).join(
        EAMNeumatico, EAMNeumatico.id == EAMInspeccionNeumatico.neumatico_id
    )
    if desde is not None:
        q = q.where(EAMInspeccionNeumatico.fecha >= desde)
    if hasta is not None:
        q = q.where(EAMInspeccionNeumatico.fecha <= hasta)
    if activo_id is not None:
        q = q.where(EAMNeumatico.activo_id == activo_id)
    if neumatico_id is not None:
        q = q.where(EAMInspeccionNeumatico.neumatico_id == neumatico_id)
    r = await db.execute(q.order_by(EAMInspeccionNeumatico.fecha.desc()).limit(limite))
    filas = r.all()

    activos_ids = {n.activo_id for _, n in filas if n.activo_id}
    vehiculos = {}
    if activos_ids:
        ra = await db.execute(select(EAMActivo).where(EAMActivo.id.in_(activos_ids)))
        for a in ra.scalars().all():
            vehiculos[a.id] = a.placa or a.codigo

    salida = []
    for insp, n in filas:
        reenc = n.reencauches or 0
        salida.append(InspeccionHistorialResponse(
            id=insp.id, neumatico_id=n.id, codigo=n.codigo, marca=n.marca,
            referencia=n.referencia, medida=n.medida, estado_llanta=n.estado,
            vida="VN" if reenc == 0 else "R%d" % reenc,
            activo_id=n.activo_id, vehiculo=vehiculos.get(n.activo_id),
            posicion=insp.posicion or n.posicion,
            fecha=insp.fecha,
            profundidad_izq=insp.profundidad_izq, profundidad_centro=insp.profundidad_centro,
            profundidad_der=insp.profundidad_der,
            profundidad_min=_min_prof(insp.profundidad_izq, insp.profundidad_centro, insp.profundidad_der),
            presion_psi=insp.presion_psi, km_odometro=insp.km_odometro,
            estado_visual=insp.estado_visual, observaciones=insp.observaciones, tecnico=insp.tecnico,
        ))
    return salida


# -- Reportes de neumaticos ----------------------------------------------------

class LlantaEnPosicionReporte(BaseModel):
    posicion: str
    posicion_label: Optional[str] = None
    numero: Optional[int] = None
    eje: Optional[int] = None
    lado: Optional[str] = None
    neumatico_id: Optional[int] = None
    codigo: Optional[str] = None
    marca: Optional[str] = None
    referencia: Optional[str] = None
    medida: Optional[str] = None
    vida: Optional[str] = None
    profundidad_min: Optional[float] = None
    presion_psi: Optional[float] = None
    fecha_inspeccion: Optional[datetime] = None
    observaciones: Optional[str] = None
    alerta: Optional[str] = None


class VehiculoReporte(BaseModel):
    activo_id: int
    codigo: str
    placa: Optional[str] = None
    nombre: Optional[str] = None
    numero_ejes: Optional[int] = None
    layout: Optional[List[int]] = None
    tiene_repuesto: Optional[bool] = None
    cantidad_repuestos: Optional[int] = None
    odometro: Optional[float] = None
    posiciones: List[LlantaEnPosicionReporte] = []
    observaciones: List[str] = []
    total_posiciones: int = 0
    posiciones_ocupadas: int = 0
    criticas: int = 0


@router.get("/neumaticos/reportes/estado-flota", response_model=List[VehiculoReporte])
async def reporte_estado_flota(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    activo_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Estado actual de la flota: por cada vehiculo, su esquema de posiciones con
    la llanta montada en cada una, la profundidad de su ultima inspeccion dentro
    del periodo y las observaciones registradas."""
    cfg = await _get_config_neu(db)

    q = select(EAMActivo).where(EAMActivo.activo == True, EAMActivo.numero_ejes.isnot(None))
    if activo_id is not None:
        q = q.where(EAMActivo.id == activo_id)
    r = await db.execute(q.order_by(EAMActivo.codigo))
    activos = r.scalars().all()
    if not activos:
        return []

    r = await db.execute(select(EAMNeumatico).where(
        EAMNeumatico.estado == "INSTALADO",
        EAMNeumatico.activo_id.in_([a.id for a in activos]),
    ))
    montadas = r.scalars().all()
    por_activo_pos = {(n.activo_id, n.posicion): n for n in montadas}

    # Ultima inspeccion de cada llanta dentro del periodo pedido
    ultima_insp = {}
    if montadas:
        qi = select(EAMInspeccionNeumatico).where(
            EAMInspeccionNeumatico.neumatico_id.in_([n.id for n in montadas])
        )
        if desde is not None:
            qi = qi.where(EAMInspeccionNeumatico.fecha >= desde)
        if hasta is not None:
            qi = qi.where(EAMInspeccionNeumatico.fecha <= hasta)
        ri = await db.execute(qi.order_by(
            EAMInspeccionNeumatico.neumatico_id, EAMInspeccionNeumatico.fecha.desc()
        ))
        for insp in ri.scalars().all():
            if insp.neumatico_id not in ultima_insp:
                ultima_insp[insp.neumatico_id] = insp

    salida: List[VehiculoReporte] = []
    for a in activos:
        posiciones_layout = _generar_posiciones(
            a.numero_ejes, a.tiene_repuesto if a.tiene_repuesto is not None else True,
            layout=a.layout_llantas, cantidad_repuestos=a.cantidad_repuestos or 1,
        )
        filas: List[LlantaEnPosicionReporte] = []
        observaciones: List[str] = []
        criticas = 0
        ocupadas = 0

        for p in posiciones_layout:
            n = por_activo_pos.get((a.id, p["codigo"]))
            fila = LlantaEnPosicionReporte(
                posicion=p["codigo"], posicion_label=p.get("label"),
                numero=p.get("numero"), eje=p.get("eje"), lado=p.get("lado"),
            )
            if n is not None:
                ocupadas += 1
                insp = ultima_insp.get(n.id)
                prof = None
                if insp is not None:
                    prof = _min_prof(insp.profundidad_izq, insp.profundidad_centro, insp.profundidad_der)
                if prof is None:
                    prof = n.profundidad_actual
                reenc = n.reencauches or 0
                fila.neumatico_id = n.id
                fila.codigo = n.codigo
                fila.marca = n.marca
                fila.referencia = n.referencia
                fila.medida = n.medida
                fila.vida = "VN" if reenc == 0 else "R%d" % reenc
                fila.profundidad_min = prof
                fila.presion_psi = insp.presion_psi if insp is not None else n.presion_actual
                fila.fecha_inspeccion = insp.fecha if insp is not None else None
                fila.observaciones = insp.observaciones if insp is not None else None

                if prof is not None and prof <= cfg.profundidad_minima:
                    fila.alerta = "Profundidad en o bajo el minimo (%s mm)" % cfg.profundidad_minima
                    criticas += 1
                elif insp is None:
                    fila.alerta = "Sin inspeccion en el periodo"

                if fila.observaciones:
                    etiqueta = p.get("label") or p["codigo"]
                    observaciones.append("%s (%s): %s" % (etiqueta, n.codigo, fila.observaciones))
                if fila.alerta:
                    etiqueta = p.get("label") or p["codigo"]
                    observaciones.append("%s (%s): %s" % (etiqueta, n.codigo, fila.alerta))
            filas.append(fila)

        salida.append(VehiculoReporte(
            activo_id=a.id, codigo=a.codigo, placa=a.placa, nombre=a.nombre,
            numero_ejes=a.numero_ejes, layout=a.layout_llantas,
            tiene_repuesto=a.tiene_repuesto, cantidad_repuestos=a.cantidad_repuestos,
            odometro=a.odometro_actual, posiciones=filas, observaciones=observaciones,
            total_posiciones=len(filas), posiciones_ocupadas=ocupadas, criticas=criticas,
        ))
    return salida


class ComposicionItem(BaseModel):
    grupo: str
    valor: str
    cantidad: int
    porcentaje: float


@router.get("/neumaticos/reportes/composicion", response_model=List[ComposicionItem])
async def reporte_composicion(
    solo_montadas: bool = True, db: AsyncSession = Depends(get_db),
):
    """Composicion de las llantas: como se reparte el parque por marca, medida,
    vida (VN/R) y estado. Por defecto solo las que estan a piso (montadas)."""
    q = select(EAMNeumatico).where(EAMNeumatico.estado != "BAJA")
    if solo_montadas:
        q = q.where(EAMNeumatico.estado == "INSTALADO")
    r = await db.execute(q)
    llantas = r.scalars().all()
    total = len(llantas)
    if total == 0:
        return []

    def contar(clave):
        conteo = {}
        for n in llantas:
            v = clave(n) or "Sin dato"
            conteo[v] = conteo.get(v, 0) + 1
        return conteo

    grupos = [
        ("Marca", contar(lambda n: n.marca)),
        ("Medida", contar(lambda n: n.medida)),
        ("Referencia", contar(lambda n: n.referencia)),
        ("Vida", contar(lambda n: "VN" if (n.reencauches or 0) == 0 else "R%d" % n.reencauches)),
        ("Estado", contar(lambda n: n.estado)),
        ("Tipo de uso", contar(lambda n: n.tipo_uso)),
    ]
    salida: List[ComposicionItem] = []
    for nombre, conteo in grupos:
        for valor, cantidad in sorted(conteo.items(), key=lambda kv: -kv[1]):
            salida.append(ComposicionItem(
                grupo=nombre, valor=str(valor), cantidad=cantidad,
                porcentaje=round(cantidad / total * 100, 1),
            ))
    return salida


# ──────────────────────────────────────────
# CATALOGO DE VEHICULOS (tipo > marca > linea > modelo)
# ──────────────────────────────────────────
#
# Mismo criterio que el catalogo de llantas: el dato se preconfigura y en la
# creacion del activo se elige de listas encadenadas, para que la ficha tecnica
# no termine con "Kenworth", "KENWORTH" y "Ken worth" como tres marcas.


class MarcaActivoBase(BaseModel):
    nombre: str
    tipo_activo: Optional[str] = None
    activo: Optional[bool] = True


class MarcaActivoResponse(MarcaActivoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total_lineas: int = 0


@router.get("/catalogo-vehiculos/marcas", response_model=List[MarcaActivoResponse])
async def listar_marcas_activo(
    tipo_activo: Optional[str] = None,
    solo_activas: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Marcas del catalogo. Si se pasa un tipo se devuelven las de ese tipo mas
    las generales (tipo nulo), que sirven para cualquiera."""
    q = select(EAMMarcaActivo)
    if tipo_activo:
        q = q.where(or_(EAMMarcaActivo.tipo_activo == tipo_activo,
                        EAMMarcaActivo.tipo_activo.is_(None)))
    if solo_activas:
        q = q.where(EAMMarcaActivo.activo == True)
    r = await db.execute(q.order_by(EAMMarcaActivo.nombre))
    marcas = r.scalars().all()

    rl = await db.execute(select(EAMLineaActivo.marca_id, func.count())
                          .group_by(EAMLineaActivo.marca_id))
    conteo = {mid: n for mid, n in rl.all()}

    salida = []
    for m in marcas:
        item = MarcaActivoResponse.model_validate(m)
        item.total_lineas = conteo.get(m.id, 0)
        salida.append(item)
    return salida


@router.post("/catalogo-vehiculos/marcas", response_model=MarcaActivoResponse, status_code=201)
async def crear_marca_activo(data: MarcaActivoBase, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre de la marca es obligatorio.")
    r = await db.execute(select(EAMMarcaActivo).where(
        func.lower(EAMMarcaActivo.nombre) == nombre.lower(),
        EAMMarcaActivo.tipo_activo == data.tipo_activo,
    ))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "La marca '%s' ya esta registrada%s."
                                 % (nombre, " para ese tipo de activo" if data.tipo_activo else ""))
    obj = EAMMarcaActivo(nombre=nombre, tipo_activo=data.tipo_activo,
                         activo=data.activo if data.activo is not None else True)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return MarcaActivoResponse.model_validate(obj)


@router.put("/catalogo-vehiculos/marcas/{mid}", response_model=MarcaActivoResponse)
async def actualizar_marca_activo(mid: int, data: MarcaActivoBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMarcaActivo, mid)
    if obj is None:
        raise HTTPException(404, "Marca no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v.strip() if isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return MarcaActivoResponse.model_validate(obj)


@router.delete("/catalogo-vehiculos/marcas/{mid}", status_code=204)
async def eliminar_marca_activo(mid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMarcaActivo, mid)
    if obj is None:
        raise HTTPException(404, "Marca no encontrada")
    r = await db.execute(select(func.count()).select_from(EAMActivo).where(
        func.lower(EAMActivo.marca) == obj.nombre.lower()))
    usados = r.scalar() or 0
    if usados > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj); await db.commit()


class LineaActivoBase(BaseModel):
    marca_id: int
    nombre: str
    activo: Optional[bool] = True


class LineaActivoResponse(LineaActivoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    marca: Optional[str] = None
    total_modelos: int = 0


@router.get("/catalogo-vehiculos/lineas", response_model=List[LineaActivoResponse])
async def listar_lineas_activo(
    marca_id: Optional[int] = None,
    solo_activas: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(EAMLineaActivo)
    if marca_id is not None:
        q = q.where(EAMLineaActivo.marca_id == marca_id)
    if solo_activas:
        q = q.where(EAMLineaActivo.activo == True)
    r = await db.execute(q.order_by(EAMLineaActivo.nombre))
    lineas = r.scalars().all()

    rm = await db.execute(select(EAMMarcaActivo))
    marcas = {m.id: m.nombre for m in rm.scalars().all()}
    rmo = await db.execute(select(EAMModeloActivo.linea_id, func.count())
                           .group_by(EAMModeloActivo.linea_id))
    conteo = {lid: n for lid, n in rmo.all()}

    salida = []
    for l in lineas:
        item = LineaActivoResponse.model_validate(l)
        item.marca = marcas.get(l.marca_id)
        item.total_modelos = conteo.get(l.id, 0)
        salida.append(item)
    return salida


@router.post("/catalogo-vehiculos/lineas", response_model=LineaActivoResponse, status_code=201)
async def crear_linea_activo(data: LineaActivoBase, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre de la linea es obligatorio.")
    marca = await db.get(EAMMarcaActivo, data.marca_id)
    if marca is None:
        raise HTTPException(404, "La marca indicada no existe.")
    r = await db.execute(select(EAMLineaActivo).where(
        EAMLineaActivo.marca_id == data.marca_id,
        func.lower(EAMLineaActivo.nombre) == nombre.lower(),
    ))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "La linea '%s' ya existe en %s." % (nombre, marca.nombre))
    obj = EAMLineaActivo(marca_id=data.marca_id, nombre=nombre,
                         activo=data.activo if data.activo is not None else True)
    db.add(obj); await db.commit(); await db.refresh(obj)
    item = LineaActivoResponse.model_validate(obj)
    item.marca = marca.nombre
    return item


@router.put("/catalogo-vehiculos/lineas/{lid}", response_model=LineaActivoResponse)
async def actualizar_linea_activo(lid: int, data: LineaActivoBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMLineaActivo, lid)
    if obj is None:
        raise HTTPException(404, "Linea no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v.strip() if isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    item = LineaActivoResponse.model_validate(obj)
    marca = await db.get(EAMMarcaActivo, obj.marca_id)
    item.marca = marca.nombre if marca else None
    return item


@router.delete("/catalogo-vehiculos/lineas/{lid}", status_code=204)
async def eliminar_linea_activo(lid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMLineaActivo, lid)
    if obj is None:
        raise HTTPException(404, "Linea no encontrada")
    r = await db.execute(select(func.count()).select_from(EAMActivo).where(
        func.lower(EAMActivo.linea) == obj.nombre.lower()))
    if (r.scalar() or 0) > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj); await db.commit()


class ModeloActivoBase(BaseModel):
    linea_id: int
    nombre: str
    anio_desde: Optional[int] = None
    anio_hasta: Optional[int] = None
    motor_id: Optional[int] = None
    tipo_combustible: Optional[str] = None
    capacidad_combustible: Optional[float] = None
    numero_ejes: Optional[int] = None
    esquema_codigo: Optional[str] = None
    vida_util_anios: Optional[int] = None
    vida_util_km: Optional[float] = None
    capacidad_kg: Optional[float] = None
    activo: Optional[bool] = True


class ModeloActivoResponse(ModeloActivoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    linea: Optional[str] = None
    marca: Optional[str] = None
    motor: Optional[str] = None


@router.get("/catalogo-vehiculos/modelos", response_model=List[ModeloActivoResponse])
async def listar_modelos_activo(
    linea_id: Optional[int] = None,
    solo_activos: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(EAMModeloActivo)
    if linea_id is not None:
        q = q.where(EAMModeloActivo.linea_id == linea_id)
    if solo_activos:
        q = q.where(EAMModeloActivo.activo == True)
    r = await db.execute(q.order_by(EAMModeloActivo.nombre))
    modelos = r.scalars().all()

    rl = await db.execute(select(EAMLineaActivo))
    lineas = {l.id: l for l in rl.scalars().all()}
    rm = await db.execute(select(EAMMarcaActivo))
    marcas = {m.id: m.nombre for m in rm.scalars().all()}
    rmo = await db.execute(select(EAMMotorActivo))
    motores = {mo.id: mo.nombre for mo in rmo.scalars().all()}

    salida = []
    for mo in modelos:
        item = ModeloActivoResponse.model_validate(mo)
        linea = lineas.get(mo.linea_id)
        item.linea = linea.nombre if linea else None
        item.marca = marcas.get(linea.marca_id) if linea else None
        item.motor = motores.get(mo.motor_id) if mo.motor_id else None
        salida.append(item)
    return salida


async def _armar_modelo_response(db: AsyncSession, obj: EAMModeloActivo) -> "ModeloActivoResponse":
    """Completa marca, linea y motor. El GET los resolvia en lote y el POST/PUT
    no, asi que devolvian el modelo a medias."""
    item = ModeloActivoResponse.model_validate(obj)
    linea = await db.get(EAMLineaActivo, obj.linea_id)
    if linea is not None:
        item.linea = linea.nombre
        marca = await db.get(EAMMarcaActivo, linea.marca_id)
        item.marca = marca.nombre if marca else None
    if obj.motor_id:
        motor = await db.get(EAMMotorActivo, obj.motor_id)
        item.motor = motor.nombre if motor else None
    return item


@router.post("/catalogo-vehiculos/modelos", response_model=ModeloActivoResponse, status_code=201)
async def crear_modelo_activo(data: ModeloActivoBase, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre del modelo es obligatorio.")
    linea = await db.get(EAMLineaActivo, data.linea_id)
    if linea is None:
        raise HTTPException(404, "La linea indicada no existe.")
    r = await db.execute(select(EAMModeloActivo).where(
        EAMModeloActivo.linea_id == data.linea_id,
        func.lower(EAMModeloActivo.nombre) == nombre.lower(),
    ))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "El modelo '%s' ya existe en la linea %s." % (nombre, linea.nombre))
    valores = data.model_dump()
    valores["nombre"] = nombre
    obj = EAMModeloActivo(**valores)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return await _armar_modelo_response(db, obj)


@router.put("/catalogo-vehiculos/modelos/{moid}", response_model=ModeloActivoResponse)
async def actualizar_modelo_activo(moid: int, data: ModeloActivoBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMModeloActivo, moid)
    if obj is None:
        raise HTTPException(404, "Modelo no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v.strip() if isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return await _armar_modelo_response(db, obj)


@router.delete("/catalogo-vehiculos/modelos/{moid}", status_code=204)
async def eliminar_modelo_activo(moid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMModeloActivo, moid)
    if obj is None:
        raise HTTPException(404, "Modelo no encontrado")
    r = await db.execute(select(func.count()).select_from(EAMActivo).where(
        func.lower(EAMActivo.modelo) == obj.nombre.lower()))
    if (r.scalar() or 0) > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj); await db.commit()


class MotorActivoBase(BaseModel):
    nombre: str
    marca: Optional[str] = None
    cilindraje_cc: Optional[float] = None
    potencia_hp: Optional[float] = None
    activo: Optional[bool] = True


class MotorActivoResponse(MotorActivoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.get("/catalogo-vehiculos/motores/marcas", response_model=List[str])
async def listar_marcas_motor(solo_activos: bool = True, db: AsyncSession = Depends(get_db)):
    """Marcas de motor distintas. Es el primer nivel de la cascada
    marca de motor > linea de motor que se usa al crear el activo."""
    q = select(EAMMotorActivo.marca).where(EAMMotorActivo.marca.isnot(None))
    if solo_activos:
        q = q.where(EAMMotorActivo.activo == True)
    r = await db.execute(q.distinct().order_by(EAMMotorActivo.marca))
    return [m for (m,) in r.all() if m and m.strip()]


@router.get("/catalogo-vehiculos/motores", response_model=List[MotorActivoResponse])
async def listar_motores(
    solo_activos: bool = False,
    marca: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(EAMMotorActivo)
    if solo_activos:
        q = q.where(EAMMotorActivo.activo == True)
    if marca:
        q = q.where(func.lower(EAMMotorActivo.marca) == marca.strip().lower())
    r = await db.execute(q.order_by(EAMMotorActivo.nombre))
    return r.scalars().all()


@router.post("/catalogo-vehiculos/motores", response_model=MotorActivoResponse, status_code=201)
async def crear_motor(data: MotorActivoBase, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre del motor es obligatorio.")
    r = await db.execute(select(EAMMotorActivo).where(
        func.lower(EAMMotorActivo.nombre) == nombre.lower()))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "El motor '%s' ya esta registrado." % nombre)
    valores = data.model_dump(); valores["nombre"] = nombre
    obj = EAMMotorActivo(**valores)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.put("/catalogo-vehiculos/motores/{moid}", response_model=MotorActivoResponse)
async def actualizar_motor(moid: int, data: MotorActivoBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMotorActivo, moid)
    if obj is None:
        raise HTTPException(404, "Motor no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v.strip() if isinstance(v, str) else v)
    await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/catalogo-vehiculos/motores/{moid}", status_code=204)
async def eliminar_motor(moid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMMotorActivo, moid)
    if obj is None:
        raise HTTPException(404, "Motor no encontrado")
    r = await db.execute(select(func.count()).select_from(EAMModeloActivo).where(
        EAMModeloActivo.motor_id == moid))
    if (r.scalar() or 0) > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj); await db.commit()


class CombustibleBase(BaseModel):
    nombre: str
    activo: Optional[bool] = True


class CombustibleResponse(CombustibleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.get("/catalogo-vehiculos/combustibles", response_model=List[CombustibleResponse])
async def listar_combustibles(solo_activos: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(EAMTipoCombustible)
    if solo_activos:
        q = q.where(EAMTipoCombustible.activo == True)
    r = await db.execute(q.order_by(EAMTipoCombustible.nombre))
    return r.scalars().all()


@router.post("/catalogo-vehiculos/combustibles", response_model=CombustibleResponse, status_code=201)
async def crear_combustible(data: CombustibleBase, db: AsyncSession = Depends(get_db)):
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre del combustible es obligatorio.")
    r = await db.execute(select(EAMTipoCombustible).where(
        func.lower(EAMTipoCombustible.nombre) == nombre.lower()))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "El combustible '%s' ya esta registrado." % nombre)
    obj = EAMTipoCombustible(nombre=nombre,
                             activo=data.activo if data.activo is not None else True)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


@router.delete("/catalogo-vehiculos/combustibles/{cid}", status_code=204)
async def eliminar_combustible(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMTipoCombustible, cid)
    if obj is None:
        raise HTTPException(404, "Combustible no encontrado")
    r = await db.execute(select(func.count()).select_from(EAMActivo).where(
        func.lower(EAMActivo.tipo_combustible) == obj.nombre.lower()))
    if (r.scalar() or 0) > 0:
        obj.activo = False
        await db.commit()
        return
    await db.delete(obj); await db.commit()


# -- Resolucion del activo contra el catalogo ---------------------------------

async def _resolver_catalogo_activo(db: AsyncSession, valores: dict) -> None:
    """Valida marca/linea/modelo contra el catalogo y hereda la ficha tecnica.

    Modifica `valores` en sitio. Se aplica igual que en las llantas: el nombre
    se normaliza a como esta escrito en el catalogo, para que reportar por
    marca no dependa de como lo escribio quien registro el activo. Los datos
    tecnicos del modelo (motor, combustible, ejes, vida util) se copian solo si
    el activo no traia el suyo, de modo que un caso particular pueda
    sobreescribirlos.

    Lanza ValueError con un mensaje entendible cuando el valor no esta en el
    catalogo, para no dejar entrar texto libre por la puerta de atras.
    """
    marca_txt = (valores.get("marca") or "").strip()
    linea_txt = (valores.get("linea") or "").strip()
    modelo_txt = (valores.get("modelo") or "").strip()
    tipo = valores.get("tipo_activo")

    if not marca_txt:
        # Sin marca no hay jerarquia que validar; linea y modelo quedan sueltos
        # solo si tampoco vinieron.
        if linea_txt or modelo_txt:
            raise ValueError("Indique la marca antes de la linea o el modelo.")
        return

    r = await db.execute(select(EAMMarcaActivo).where(
        func.lower(EAMMarcaActivo.nombre) == marca_txt.lower()))
    candidatas = r.scalars().all()
    if not candidatas:
        raise ValueError("La marca '%s' no esta en el catalogo. Agreguela en la "
                         "configuracion del CMMS antes de usarla." % marca_txt)
    # Se prefiere la marca del tipo pedido; si no hay, la general
    marca = next((m for m in candidatas if tipo and m.tipo_activo == tipo), None)
    if marca is None:
        marca = next((m for m in candidatas if m.tipo_activo is None), None)
    if marca is None:
        raise ValueError("La marca '%s' no esta habilitada para el tipo de activo "
                         "'%s'." % (marca_txt, tipo or "sin tipo"))
    valores["marca"] = marca.nombre

    if not linea_txt:
        if modelo_txt:
            raise ValueError("Indique la linea antes del modelo.")
        return

    r = await db.execute(select(EAMLineaActivo).where(
        EAMLineaActivo.marca_id == marca.id,
        func.lower(EAMLineaActivo.nombre) == linea_txt.lower()))
    linea = r.scalar_one_or_none()
    if linea is None:
        raise ValueError("La linea '%s' no pertenece a la marca '%s'."
                         % (linea_txt, marca.nombre))
    valores["linea"] = linea.nombre

    if not modelo_txt:
        return

    r = await db.execute(select(EAMModeloActivo).where(
        EAMModeloActivo.linea_id == linea.id,
        func.lower(EAMModeloActivo.nombre) == modelo_txt.lower()))
    modelo = r.scalar_one_or_none()
    if modelo is None:
        raise ValueError("El modelo '%s' no existe en la linea '%s' de %s."
                         % (modelo_txt, linea.nombre, marca.nombre))
    valores["modelo"] = modelo.nombre

    # Herencia de la ficha tecnica: solo lo que el activo no trajo
    if modelo.motor_id and not valores.get("motor_marca") and not valores.get("motor_linea"):
        motor = await db.get(EAMMotorActivo, modelo.motor_id)
        if motor is not None:
            valores["motor_marca"] = motor.marca
            valores["motor_linea"] = motor.nombre
            if valores.get("motor_cc") in (None, 0):
                valores["motor_cc"] = motor.cilindraje_cc
    for campo in ("tipo_combustible", "capacidad_combustible", "numero_ejes",
                  "vida_util_anios", "vida_util_km"):
        if valores.get(campo) in (None, "", 0) and getattr(modelo, campo, None) is not None:
            valores[campo] = getattr(modelo, campo)


# -- Catalogos organizativos y contables del activo ---------------------------
#
# Una sola tabla con discriminador para sede, area, ubicacion, responsable,
# cuenta contable y centro de costo: comparten forma y solo cambian de
# significado. Existen por lo mismo que el resto del catalogo, si la ubicacion
# se escribe a mano "Bodega Norte", "bodega norte" y "Bod. Norte" cuentan como
# tres y ningun reporte por ubicacion cuadra.

TIPOS_CATALOGO_ACTIVO = [
    "SEDE", "AREA", "UBICACION", "RESPONSABLE", "CUENTA_CONTABLE", "CENTRO_COSTO",
]


class CatalogoActivoBase(BaseModel):
    tipo: str
    nombre: str
    codigo: Optional[str] = None
    activo: Optional[bool] = True


class CatalogoActivoResponse(CatalogoActivoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    en_uso: int = 0


CAMPO_POR_TIPO = {
    "SEDE": "sede", "AREA": "area", "UBICACION": "ubicacion",
    "RESPONSABLE": "responsable", "CUENTA_CONTABLE": "cuenta_contable",
    "CENTRO_COSTO": "centro_costo",
}


@router.get("/catalogo-vehiculos/generales", response_model=List[CatalogoActivoResponse])
async def listar_catalogo_activo(
    tipo: Optional[str] = None,
    solo_activos: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Valores de un catalogo organizativo. Sin `tipo` devuelve todos, para que
    la pantalla de configuracion los muestre agrupados en una sola consulta."""
    if tipo and tipo.upper() not in TIPOS_CATALOGO_ACTIVO:
        raise HTTPException(400, "Tipo de catalogo no valido: %s. Use uno de: %s."
                                 % (tipo, ", ".join(TIPOS_CATALOGO_ACTIVO)))
    q = select(EAMCatalogoActivo)
    if tipo:
        q = q.where(EAMCatalogoActivo.tipo == tipo.upper())
    if solo_activos:
        q = q.where(EAMCatalogoActivo.activo == True)
    r = await db.execute(q.order_by(EAMCatalogoActivo.tipo, EAMCatalogoActivo.nombre))
    filas = r.scalars().all()
    if not filas:
        return []

    # Cuantos activos usan cada valor: es lo que decide si se puede borrar
    conteos: dict = {}
    for t in {f.tipo for f in filas}:
        campo = CAMPO_POR_TIPO.get(t)
        if not campo:
            continue
        col = getattr(EAMActivo, campo)
        rc = await db.execute(select(col, func.count()).where(col.isnot(None)).group_by(col))
        for valor, n in rc.all():
            conteos[(t, (valor or "").strip().lower())] = n

    salida = []
    for f in filas:
        item = CatalogoActivoResponse.model_validate(f)
        item.en_uso = conteos.get((f.tipo, f.nombre.strip().lower()), 0)
        salida.append(item)
    return salida


@router.post("/catalogo-vehiculos/generales", response_model=CatalogoActivoResponse, status_code=201)
async def crear_catalogo_activo(data: CatalogoActivoBase, db: AsyncSession = Depends(get_db)):
    tipo = (data.tipo or "").upper()
    if tipo not in TIPOS_CATALOGO_ACTIVO:
        raise HTTPException(400, "Tipo de catalogo no valido: %s." % data.tipo)
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio.")
    r = await db.execute(select(EAMCatalogoActivo).where(
        EAMCatalogoActivo.tipo == tipo,
        func.lower(EAMCatalogoActivo.nombre) == nombre.lower(),
    ))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "'%s' ya esta registrado en ese catalogo." % nombre)
    obj = EAMCatalogoActivo(tipo=tipo, nombre=nombre, codigo=(data.codigo or None),
                            activo=data.activo if data.activo is not None else True)
    db.add(obj); await db.commit(); await db.refresh(obj)
    return CatalogoActivoResponse.model_validate(obj)


@router.put("/catalogo-vehiculos/generales/{cid}", response_model=CatalogoActivoResponse)
async def actualizar_catalogo_activo(cid: int, data: CatalogoActivoBase, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMCatalogoActivo, cid)
    if obj is None:
        raise HTTPException(404, "Valor no encontrado")
    valores = data.model_dump(exclude_unset=True)
    valores.pop("tipo", None)   # el tipo no se cambia: seria mover de catalogo
    nombre_previo = obj.nombre
    for k, v in valores.items():
        setattr(obj, k, v.strip() if isinstance(v, str) else v)

    # Si se renombra un valor en uso, se arrastra a los activos que lo tienen:
    # dejarlos con el nombre viejo los sacaria de la lista y del reporte.
    if obj.nombre != nombre_previo:
        campo = CAMPO_POR_TIPO.get(obj.tipo)
        if campo:
            col = getattr(EAMActivo, campo)
            ra = await db.execute(select(EAMActivo).where(func.lower(col) == nombre_previo.lower()))
            for a in ra.scalars().all():
                setattr(a, campo, obj.nombre)

    await db.commit(); await db.refresh(obj)
    return CatalogoActivoResponse.model_validate(obj)


@router.delete("/catalogo-vehiculos/generales/{cid}", status_code=204)
async def eliminar_catalogo_activo(cid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMCatalogoActivo, cid)
    if obj is None:
        raise HTTPException(404, "Valor no encontrado")
    campo = CAMPO_POR_TIPO.get(obj.tipo)
    if campo:
        col = getattr(EAMActivo, campo)
        r = await db.execute(select(func.count()).select_from(EAMActivo).where(
            func.lower(col) == obj.nombre.lower()))
        if (r.scalar() or 0) > 0:
            # Se desactiva: borrarlo dejaria activos apuntando a un valor que ya
            # no existe en la lista.
            obj.activo = False
            await db.commit()
            return
    await db.delete(obj); await db.commit()


# -- Alertas (profundidad / presion / desalineacion) --
@router.get("/neumaticos/alertas", response_model=List[AlertaNeuResponse])
async def alertas_neumaticos(db: AsyncSession = Depends(get_db)):
    cfg = await _get_config_neu(db)
    r = await db.execute(select(EAMNeumatico).where(EAMNeumatico.estado != "BAJA"))
    neus = r.scalars().all()
    alertas: List[AlertaNeuResponse] = []
    for n in neus:
        if n.profundidad_actual is not None and n.profundidad_actual <= cfg.profundidad_minima:
            alertas.append(AlertaNeuResponse(
                neumatico_id=n.id, codigo=n.codigo, tipo="PROFUNDIDAD", severidad="ALTA",
                mensaje=f"Profundidad {n.profundidad_actual}mm ≤ mínimo {cfg.profundidad_minima}mm",
                posicion=n.posicion, activo_id=n.activo_id))
        if n.presion_actual is not None and (n.presion_actual < cfg.presion_min or n.presion_actual > cfg.presion_max):
            alertas.append(AlertaNeuResponse(
                neumatico_id=n.id, codigo=n.codigo, tipo="PRESION", severidad="MEDIA",
                mensaje=f"Presión {n.presion_actual}psi fuera de rango [{cfg.presion_min}-{cfg.presion_max}]",
                posicion=n.posicion, activo_id=n.activo_id))
    # Desalineación: por (vehículo, eje) comparar profundidades instaladas
    grupos: dict = {}
    for n in neus:
        if n.estado == "INSTALADO" and n.activo_id and n.profundidad_actual is not None:
            eje = _eje_de_posicion(n.posicion or "")
            if eje and eje > 0:
                grupos.setdefault((n.activo_id, eje), []).append(n)
    for (activo_id, eje), items in grupos.items():
        if len(items) < 2:
            continue
        profs = [i.profundidad_actual for i in items]
        dif = max(profs) - min(profs)
        if dif > cfg.umbral_desalineacion:
            peor = min(items, key=lambda x: x.profundidad_actual)
            alertas.append(AlertaNeuResponse(
                neumatico_id=peor.id, codigo=peor.codigo, tipo="DESALINEACION", severidad="MEDIA",
                mensaje=f"Diferencia de {round(dif,1)}mm en el eje {eje} (umbral {cfg.umbral_desalineacion}mm)",
                posicion=peor.posicion, activo_id=activo_id))
    return alertas


# ── Reencauche (lotes y detalle) ──
@router.get("/neumaticos/reencauche", response_model=List[ReencaucheLoteResponse])
async def list_reencauche_lotes(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMReencaucheLote).order_by(EAMReencaucheLote.fecha_envio.desc()))
    return r.scalars().all()

@router.post("/neumaticos/reencauche", response_model=ReencaucheLoteResponse)
async def create_reencauche_lote(data: ReencaucheLoteCreate, db: AsyncSession = Depends(get_db)):
    # El lote se identifica por su numero de remision, asi que repetirlo es un
    # error de digitacion frecuente. Se avisa antes de que la restriccion unica
    # de la tabla devuelva un error de base de datos sin contexto.
    r = await db.execute(select(EAMReencaucheLote).where(
        EAMReencaucheLote.codigo == data.codigo))
    existente = r.scalar_one_or_none()
    if existente is not None:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un lote con la remision %s (enviado el %s). "
                   "Verifique el numero o abra el lote existente."
                   % (existente.codigo, existente.fecha_envio),
        )
    obj = EAMReencaucheLote(**data.model_dump(), estado="ABIERTO")
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.get("/neumaticos/reencauche/{lote_id}/detalle", response_model=List[ReencaucheDetalleResponse])
async def list_reencauche_detalle(lote_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(EAMReencaucheDetalle).where(EAMReencaucheDetalle.lote_id == lote_id))
    return r.scalars().all()

@router.post("/neumaticos/reencauche/{lote_id}/detalle", response_model=ReencaucheDetalleResponse)
async def add_reencauche_detalle(lote_id: int, data: ReencaucheDetalleCreate, db: AsyncSession = Depends(get_db)):
    lote = await db.get(EAMReencaucheLote, lote_id)
    if not lote:
        raise HTTPException(404, "Lote no encontrado")
    if lote.estado == "CERRADO":
        raise HTTPException(409, "El lote está cerrado")
    neu = await db.get(EAMNeumatico, data.neumatico_id)
    if not neu:
        raise HTTPException(404, "Neumático no encontrado")
    obj = EAMReencaucheDetalle(
        lote_id=lote_id, neumatico_id=data.neumatico_id,
        banda=data.banda, banda_id=data.banda_id, resultado="PENDIENTE",
    )
    # el neumático pasa a estado REENCAUCHE mientras está en el proceso
    neu.estado = "REENCAUCHE"; neu.activo_id = None; neu.posicion = None
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj

@router.put("/neumaticos/reencauche/detalle/{det_id}", response_model=ReencaucheDetalleResponse)
async def procesar_reencauche_detalle(det_id: int, data: ReencaucheDetalleUpdate, db: AsyncSession = Depends(get_db)):
    det = await db.get(EAMReencaucheDetalle, det_id)
    if not det:
        raise HTTPException(404, "Detalle no encontrado")
    neu = await db.get(EAMNeumatico, det.neumatico_id)
    resultado = data.resultado.upper()
    costo = data.costo
    if costo is None and det.banda_id:
        banda = await db.get(EAMBandaReencauche, det.banda_id)
        if banda and banda.costo_defecto:
            costo = banda.costo_defecto
    det.resultado = resultado
    det.profundidad_nueva = data.profundidad_nueva
    det.vida_remanente_km = data.vida_remanente_km
    det.costo = costo
    if neu:
        if resultado == "REENCAUCHADA":
            vida_anterior = await _vida_abierta(db, neu.id)
            if vida_anterior:
                vida_anterior.fecha_fin = datetime.utcnow()
                vida_anterior.km_fin = neu.km_actual
                vida_anterior.profundidad_final = neu.profundidad_actual
            neu.reencauches = (neu.reencauches or 0) + 1
            neu.estado = "ALMACENADO"
            if data.profundidad_nueva is not None:
                neu.profundidad_actual = data.profundidad_nueva
                neu.profundidad_diseño = data.profundidad_nueva
            neu.km_inicio = neu.km_actual or 0     # reinicia el conteo de vida
            neu.km_total = 0
            if costo:
                neu.costo = costo
            db.add(EAMVidaNeumatico(
                neumatico_id=neu.id, numero_vida=(vida_anterior.numero_vida + 1) if vida_anterior else (neu.reencauches + 1),
                tipo="REENCAUCHADA", fecha_inicio=datetime.utcnow(), km_inicio=0,
                costo=costo, profundidad_inicial=data.profundidad_nueva,
            ))
        elif resultado == "REMANENTE":
            neu.estado = "ALMACENADO"
            if data.vida_remanente_km is not None:
                neu.vida_util_km = data.vida_remanente_km
        elif resultado == "RECHAZO":
            neu.estado = "BAJA"; neu.motivo_baja = "Rechazado en reencauche"
            neu.dano_id = data.dano_id
            neu.motivo_fin_vida_id = data.motivo_fin_vida_id
            vida_actual = await _vida_abierta(db, neu.id)
            if vida_actual:
                vida_actual.fecha_fin = datetime.utcnow()
                vida_actual.km_fin = neu.km_actual
                vida_actual.profundidad_final = neu.profundidad_actual
                vida_actual.motivo_cierre_id = data.motivo_fin_vida_id
    await db.commit(); await db.refresh(det)
    return det

@router.put("/neumaticos/reencauche/{lote_id}/cerrar", response_model=ReencaucheLoteResponse)
async def cerrar_reencauche_lote(lote_id: int, db: AsyncSession = Depends(get_db)):
    lote = await db.get(EAMReencaucheLote, lote_id)
    if not lote:
        raise HTTPException(404, "Lote no encontrado")
    lote.estado = "CERRADO"
    await db.commit(); await db.refresh(lote)
    return lote


@router.get("/neumaticos", response_model=List[NeumaticResponse])
async def list_neumaticos(
    estado: Optional[str] = None,
    activo_id: Optional[int] = None,
    bodega_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(EAMNeumatico)
    if estado:
        q = q.where(EAMNeumatico.estado == estado)
    if activo_id is not None:
        q = q.where(EAMNeumatico.activo_id == activo_id)
    if bodega_id is not None:
        q = q.where(EAMNeumatico.bodega_id == bodega_id)
    result = await db.execute(q.order_by(EAMNeumatico.codigo))
    return result.scalars().all()

async def _preparar_neumatico(db: AsyncSession, data: "NeumaticCreate") -> dict:
    """Valida contra el catalogo y completa los datos derivados de una llanta:
    profundidad de diseno segun referencia+dimension, profundidad actual segun
    sea nueva o usada, y coherencia del numero de reencauches."""
    _, ref, dim, rd = await _resolver_catalogo_llanta(db, data.marca, data.referencia, data.medida)

    valores = data.model_dump()
    # Se normalizan a los nombres del catalogo (evita duplicados por mayusculas)
    valores["marca"] = (await db.get(EAMMarcaNeumatico, ref.marca_id)).nombre
    valores["referencia"] = ref.nombre
    valores["medida"] = dim.nombre
    # La profundidad inicial la manda el catalogo, no quien captura
    valores["profundidad_diseño"] = rd.profundidad_inicial
    # El tipo de uso es propio del diseno de la llanta: lo define la referencia
    # en el catalogo, no quien registra cada unidad.
    valores["tipo_uso"] = ref.tipo_uso
    if rd.vida_util_km and not valores.get("vida_util_km"):
        valores["vida_util_km"] = rd.vida_util_km
    if rd.presion_recomendada and not valores.get("presion_recomendada"):
        valores["presion_recomendada"] = rd.presion_recomendada

    reencauches = valores.get("reencauches") or 0
    if reencauches < 0:
        raise ValueError("El numero de reencauches no puede ser negativo")
    valores["reencauches"] = reencauches

    es_usada = bool(valores.get("es_usada"))
    prof_actual = valores.get("profundidad_actual")
    if es_usada:
        if prof_actual is None:
            raise ValueError("Una llanta usada requiere la profundidad actual")
        if prof_actual > rd.profundidad_inicial:
            raise ValueError(
                "La profundidad actual (%s mm) no puede superar la inicial de la referencia (%s mm)"
                % (prof_actual, rd.profundidad_inicial)
            )
        if valores.get("km_actual") is None:
            raise ValueError("Una llanta usada requiere el kilometraje actual")
    else:
        # Nueva: arranca con la profundidad de diseno y sin kilometraje recorrido
        valores["profundidad_actual"] = rd.profundidad_inicial
        valores["km_actual"] = valores.get("km_actual") or 0

    km_actual = valores.get("km_actual") or 0
    valores["km_inicio"] = 0
    valores["km_actual"] = km_actual
    valores["km_total"] = km_actual
    return valores


@router.post("/neumaticos", response_model=NeumaticResponse)
async def create_neumatico(data: NeumaticCreate, db: AsyncSession = Depends(get_db)):
    try:
        valores = await _preparar_neumatico(db, data)
    except ValueError as e:
        raise HTTPException(409, str(e))
    obj = EAMNeumatico(**valores)
    db.add(obj); await db.commit(); await db.refresh(obj)
    reencauches = obj.reencauches or 0
    db.add(EAMVidaNeumatico(
        neumatico_id=obj.id,
        numero_vida=reencauches + 1,
        tipo="NUEVA" if reencauches == 0 else "REENCAUCHADA",
        fecha_inicio=datetime.utcnow(), km_inicio=obj.km_inicio or 0,
        costo=obj.costo, profundidad_inicial=obj.profundidad_diseño,
    ))
    await db.commit()
    return obj

@router.put("/neumaticos/{nid}", response_model=NeumaticResponse)
async def update_neumatico(nid: int, data: NeumaticUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMNeumatico, nid)
    if not obj:
        raise HTTPException(404, "Neumático no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit(); await db.refresh(obj)
    return obj


# ─── Combustible ──────────────────────────────────────────────────────────────

# Combustible vive en `combustible.py`: transacciones, rendimiento
# tanque a tanque y metas de km/galon por marca, linea y motor.


# ─── Garantías ────────────────────────────────────────────────────────────────

#
# EL ESTADO Y LOS DÍAS SE CALCULAN, NO SE GUARDAN
#
# Una garantía guardada como VIGENTE sigue diciendo VIGENTE el día después de
# vencerse: el estado depende de la fecha de hoy, y no hay nada que corra a
# medianoche a corregir la columna. Lo mismo con los días restantes. Así que de
# la columna `estado` solo se respeta lo que una persona decidió —RECLAMADA,
# CANCELADA— y el resto sale de comparar `fecha_fin` con hoy.
#
# Es exactamente el error que tenía la pantalla cuando estaba maquetada: traía
# «209 días restantes» escrito a mano, y ese número envejecía solo.

ESTADOS_MANUALES_GARANTIA = ("RECLAMADA", "CANCELADA")

# Ventana de aviso. Noventa días es el tiempo mínimo razonable para alcanzar a
# inspeccionar el equipo, abrir el reclamo y que el proveedor responda antes de
# que la cobertura se cierre.
DIAS_AVISO_GARANTIA = 90


async def _garantia_a_salida(g: EAMGarantia, hoy: date,
                             activos: dict, conteos: dict) -> dict:
    dias = (g.fecha_fin - hoy).days if g.fecha_fin else None
    if g.estado in ESTADOS_MANUALES_GARANTIA:
        estado = g.estado
    elif dias is not None and dias < 0:
        estado = "VENCIDA"
    else:
        estado = "VIGENTE"
    n, ultimo = conteos.get(g.id, (0, None))
    return {
        "id": g.id, "activo_id": g.activo_id, "tipo": g.tipo,
        "descripcion": g.descripcion, "proveedor": g.proveedor,
        "numero_garantia": g.numero_garantia,
        "fecha_inicio": g.fecha_inicio, "fecha_fin": g.fecha_fin,
        "condiciones": g.condiciones, "valor_cubierto": g.valor_cubierto,
        "cobertura": g.cobertura, "contacto_proveedor": g.contacto_proveedor,
        "telefono_proveedor": g.telefono_proveedor, "documento": g.documento,
        "responsable": g.responsable,
        "estado": estado, "dias_restantes": dias,
        "activo_codigo": activos.get(g.activo_id),
        # Contados desde la tabla de reclamos, no leídos de la columna.
        "reclamaciones": n, "ultimo_reclamo": ultimo,
    }


async def _contexto_garantias(db: AsyncSession, ids: List[int]) -> tuple:
    """Códigos de activo y conteo de reclamos, en dos consultas y no en 2N."""
    r = await db.execute(select(EAMActivo.id, EAMActivo.codigo))
    activos = {aid: cod for aid, cod in r.all()}
    conteos: dict = {}
    if ids:
        r = await db.execute(
            select(EAMGarantiaReclamacion.garantia_id,
                   func.count(EAMGarantiaReclamacion.id),
                   func.max(EAMGarantiaReclamacion.fecha))
            .where(EAMGarantiaReclamacion.garantia_id.in_(ids))
            .group_by(EAMGarantiaReclamacion.garantia_id))
        conteos = {gid: (n, ultimo) for gid, n, ultimo in r.all()}
    return activos, conteos


@router.get("/garantias", response_model=List[GarantiaResponse])
async def list_garantias(estado: Optional[str] = None,
                         activo_id: Optional[int] = None,
                         db: AsyncSession = Depends(get_db)):
    q = select(EAMGarantia).order_by(EAMGarantia.fecha_fin)
    if activo_id:
        q = q.where(EAMGarantia.activo_id == activo_id)
    filas = list((await db.execute(q)).scalars().all())
    activos, conteos = await _contexto_garantias(db, [g.id for g in filas])
    hoy = date.today()
    salida = [await _garantia_a_salida(g, hoy, activos, conteos) for g in filas]
    # El filtro va sobre el estado calculado y no sobre la columna: pedir las
    # vencidas y recibir las que la columna dice vigentes sería inexplicable.
    if estado:
        salida = [g for g in salida if g["estado"] == estado]
    return salida


@router.get("/garantias/resumen")
async def resumen_garantias(db: AsyncSession = Depends(get_db)):
    """Los números del encabezado, calculados donde están los datos.

    Se calcula acá y no sumando en la pantalla porque la pantalla solo tiene la
    página que está viendo: con paginación, los totales saldrían mal.
    """
    filas = list((await db.execute(select(EAMGarantia))).scalars().all())
    hoy = date.today()
    from app.core.parametros_eam import leer_parametros_eam
    aviso = (await leer_parametros_eam(db))['garantia_dias_aviso']
    vigentes = por_vencer = vencidas = reclamadas = 0
    valor_total = 0.0
    #
    # RECLAMADA NO SACA A UNA GARANTÍA DE VIGENTE
    #
    # Son dos cosas distintas: vigente dice si todavía cubre, y reclamada dice
    # si hay una gestión abierta con el proveedor. Una garantía reclamada sigue
    # cubriendo —de hecho es la que más hay que vigilar—.
    #
    # Contarlas aparte era un error visible: la garantía reclamada que se vencía
    # en 45 días desaparecía del contador «Por vencer» y seguía apareciendo en
    # la pestaña «Por vencer», que usa la otra ruta. Dos números distintos para
    # lo mismo en la misma pantalla. Ahora las dos cuentan con la misma regla
    # que `/garantias/por-vencer`: lo que no está cancelado y no ha vencido.
    #
    for g in filas:
        dias = (g.fecha_fin - hoy).days if g.fecha_fin else None
        if g.estado == "RECLAMADA":
            reclamadas += 1
        if g.estado == "CANCELADA":
            continue
        if dias is not None and dias < 0:
            vencidas += 1
            continue
        vigentes += 1
        if dias is not None and dias <= aviso:
            por_vencer += 1
        # El valor cubierto suma solo lo que todavía cubre algo: sumar las
        # vencidas infla la cifra con cobertura que ya no existe.
        valor_total += g.valor_cubierto or 0

    r = await db.execute(select(
        func.count(EAMGarantiaReclamacion.id),
        func.coalesce(func.sum(EAMGarantiaReclamacion.monto_solicitado), 0),
        func.coalesce(func.sum(EAMGarantiaReclamacion.monto_recuperado), 0)))
    n_rec, solicitado, recuperado = r.one()

    return {
        "vigentes": vigentes, "por_vencer": por_vencer, "vencidas": vencidas,
        "reclamadas": reclamadas, "valor_cubierto": valor_total,
        "total": len(filas), "dias_aviso": aviso,
        "reclamos": n_rec, "monto_solicitado": float(solicitado),
        "monto_recuperado": float(recuperado),
        # La tasa se calcula acá para que la pantalla no divida por cero.
        "tasa_recuperacion": round(float(recuperado) / float(solicitado) * 100, 1)
                             if solicitado else 0.0,
    }


@router.get("/garantias/por-vencer", response_model=List[GarantiaResponse])
async def garantias_por_vencer(dias: Optional[int] = Query(None, ge=1, le=365),
                               db: AsyncSession = Depends(get_db)):
    """Las que se vencen dentro de la ventana, lo más próximo primero.

    Se excluye lo ya vencido a propósito: esta lista es de lo que todavía se
    puede reclamar, y mezclarle lo que ya no tiene remedio la vuelve inútil.
    """
    hoy = date.today()
    if dias is None:
        from app.core.parametros_eam import leer_parametros_eam
        dias = int((await leer_parametros_eam(db))['garantia_dias_aviso'])
    q = (select(EAMGarantia)
         .where(and_(EAMGarantia.fecha_fin >= hoy,
                     EAMGarantia.fecha_fin <= hoy + timedelta(days=dias),
                     EAMGarantia.estado.notin_(("CANCELADA",))))
         .order_by(EAMGarantia.fecha_fin))
    filas = list((await db.execute(q)).scalars().all())
    activos, conteos = await _contexto_garantias(db, [g.id for g in filas])
    return [await _garantia_a_salida(g, hoy, activos, conteos) for g in filas]


@router.get("/garantias/{gid}", response_model=GarantiaResponse)
async def obtener_garantia(gid: int, db: AsyncSession = Depends(get_db)):
    g = await db.get(EAMGarantia, gid)
    if not g:
        raise HTTPException(404, "Esa garantía no existe")
    activos, conteos = await _contexto_garantias(db, [gid])
    return await _garantia_a_salida(g, date.today(), activos, conteos)


async def _numero_garantia(db: AsyncSession) -> str:
    """Consecutivo del año, tomado del mayor que haya en uso.

    Lo que esto garantiza es que el número no choque con ninguna garantía viva,
    y por eso además se valida que no exista. Lo que NO garantiza es que un
    número no se reutilice: al borrar la última garantía del año, la siguiente
    vuelve a tomar ese número. Se acepta porque solo se puede borrar una
    garantía sin reclamaciones —o sea, una que no tiene historia— y porque la
    alternativa es una secuencia por año en la base para un consecutivo que
    casi siempre lo trae escrito el contrato del proveedor.
    """
    prefijo = f"GAR-{date.today().year}-"
    r = await db.execute(select(func.max(EAMGarantia.numero_garantia))
                         .where(EAMGarantia.numero_garantia.like(f"{prefijo}%")))
    ultimo = r.scalar()
    siguiente = 1
    if ultimo:
        try:
            siguiente = int(str(ultimo).rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            siguiente = 1
    return f"{prefijo}{siguiente:04d}"


async def _numero_libre(db: AsyncSession, numero: str, excluir: Optional[int] = None) -> None:
    q = select(func.count()).select_from(EAMGarantia).where(
        func.lower(EAMGarantia.numero_garantia) == numero.lower())
    if excluir:
        q = q.where(EAMGarantia.id != excluir)
    if (await db.execute(q)).scalar():
        raise HTTPException(409, f"Ya hay una garantía con el número «{numero}»")


@router.post("/garantias", response_model=GarantiaResponse, status_code=201)
async def create_garantia(data: GarantiaCreate, db: AsyncSession = Depends(get_db)):
    if data.fecha_fin < data.fecha_inicio:
        raise HTTPException(400, "La garantía no puede vencer antes de empezar")
    campos = data.model_dump()
    numero = (campos.get("numero_garantia") or "").strip()
    if numero:
        await _numero_libre(db, numero)
    else:
        numero = await _numero_garantia(db)
    campos["numero_garantia"] = numero
    campos.pop("estado", None)
    obj = EAMGarantia(**campos, estado="VIGENTE")
    db.add(obj); await db.commit(); await db.refresh(obj)
    activos, conteos = await _contexto_garantias(db, [obj.id])
    return await _garantia_a_salida(obj, date.today(), activos, conteos)


@router.put("/garantias/{gid}", response_model=GarantiaResponse)
async def actualizar_garantia(gid: int, data: GarantiaCreate,
                              db: AsyncSession = Depends(get_db)):
    g = await db.get(EAMGarantia, gid)
    if not g:
        raise HTTPException(404, "Esa garantía no existe")
    if data.fecha_fin < data.fecha_inicio:
        raise HTTPException(400, "La garantía no puede vencer antes de empezar")

    # `numero_garantia` y `estado` quedan fuera de la edición general, y por
    # motivos distintos:
    #
    #  - El NÚMERO es opcional en el esquema, así que un formulario que no lo
    #    manda lo dejaría en nulo: editar la descripción borraría el número del
    #    contrato. Solo se cambia si viene con algo escrito.
    #  - El ESTADO se cambia por su propia ruta. Si viniera del formulario, al
    #    editar una garantía reclamada se borraría ese hecho sin que nadie lo
    #    pidiera.
    campos = data.model_dump(exclude={"estado", "numero_garantia"})
    numero = (data.numero_garantia or "").strip()
    if numero and numero != (g.numero_garantia or ""):
        await _numero_libre(db, numero, excluir=gid)
        g.numero_garantia = numero
    for campo, valor in campos.items():
        setattr(g, campo, valor)
    await db.commit(); await db.refresh(g)
    activos, conteos = await _contexto_garantias(db, [gid])
    return await _garantia_a_salida(g, date.today(), activos, conteos)


class EstadoGarantiaIn(BaseModel):
    estado: str


@router.patch("/garantias/{gid}/estado", response_model=GarantiaResponse)
async def cambiar_estado_garantia(gid: int, data: EstadoGarantiaIn,
                                  db: AsyncSession = Depends(get_db)):
    g = await db.get(EAMGarantia, gid)
    if not g:
        raise HTTPException(404, "Esa garantía no existe")
    validos = ("VIGENTE", "RECLAMADA", "CANCELADA")
    if data.estado not in validos:
        raise HTTPException(
            400, f"Estado no válido. VENCIDA no se pone a mano: sale de la fecha. "
                 f"Válidos: {', '.join(validos)}")
    g.estado = data.estado
    await db.commit(); await db.refresh(g)
    activos, conteos = await _contexto_garantias(db, [gid])
    return await _garantia_a_salida(g, date.today(), activos, conteos)


@router.delete("/garantias/{gid}", status_code=204)
async def eliminar_garantia(gid: int, db: AsyncSession = Depends(get_db)):
    g = await db.get(EAMGarantia, gid)
    if not g:
        raise HTTPException(404, "Esa garantía no existe")
    r = await db.execute(select(func.count(EAMGarantiaReclamacion.id))
                         .where(EAMGarantiaReclamacion.garantia_id == gid))
    n = r.scalar() or 0
    # Se niega en vez de arrastrar los reclamos: un reclamo es la historia de
    # una plata que se pidió y se recuperó, y eso no se borra de refilón al
    # limpiar una lista de garantías.
    if n:
        raise HTTPException(
            409,
            f"Esa garantía tiene {n} {'reclamación' if n == 1 else 'reclamaciones'}. "
            "Bórrelas primero, o cancele la garantía en vez de borrarla.")
    # Los documentos adjuntos se van con la garantía: la base los borra en
    # cascada, pero el archivo en disco quedaría huérfano si no se quita aquí.
    from pathlib import Path
    from app.core.config import settings
    from app.infrastructure.models.eam import EAMAdjuntoGarantia
    rutas = [Path(settings.UPLOAD_DIR) / a.ruta for a in (await db.execute(
        select(EAMAdjuntoGarantia).where(EAMAdjuntoGarantia.garantia_id == gid))).scalars().all()]
    await db.delete(g); await db.commit()
    for ruta in rutas:
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass


# ─── Reclamaciones de garantía ────────────────────────────────────────────────

def _reclamo_a_salida(r: EAMGarantiaReclamacion, g: Optional[EAMGarantia],
                      hoy: date, activos: dict) -> dict:
    # Días de gestión: hasta el cierre si cerró, y hasta hoy si sigue abierto.
    # Un reclamo abierto tiene que ir subiendo, que es lo que delata al
    # proveedor que no responde.
    fin = r.fecha_cierre or hoy
    return {
        "id": r.id, "garantia_id": r.garantia_id, "fecha": r.fecha,
        "descripcion": r.descripcion, "monto_solicitado": r.monto_solicitado,
        "monto_recuperado": r.monto_recuperado, "estado": r.estado,
        "responsable": r.responsable, "resolucion": r.resolucion,
        "fecha_cierre": r.fecha_cierre,
        "dias_gestion": (fin - r.fecha).days if r.fecha else None,
        "abierto": r.fecha_cierre is None,
        "numero_garantia": g.numero_garantia if g else None,
        "proveedor": g.proveedor if g else None,
        "activo_codigo": activos.get(g.activo_id) if g else None,
    }


class ReclamacionCreate(BaseModel):
    garantia_id: int
    fecha: Optional[date] = None
    descripcion: str
    monto_solicitado: Optional[float] = None
    monto_recuperado: Optional[float] = None
    estado: str = "EN_PROCESO"
    responsable: Optional[str] = None
    resolucion: Optional[str] = None
    fecha_cierre: Optional[date] = None


ESTADOS_RECLAMO = ("EN_PROCESO", "APROBADA", "RECHAZADA", "CERRADA")
# Un reclamo aprobado o rechazado ya tiene respuesta del proveedor: la gestión
# terminó ahí, aunque el dinero llegue después.
ESTADOS_RECLAMO_CERRADOS = ("APROBADA", "RECHAZADA", "CERRADA")


@router.get("/garantias-reclamaciones")
async def list_reclamaciones(garantia_id: Optional[int] = None,
                             estado: Optional[str] = None,
                             db: AsyncSession = Depends(get_db)):
    q = select(EAMGarantiaReclamacion).order_by(EAMGarantiaReclamacion.fecha.desc())
    if garantia_id:
        q = q.where(EAMGarantiaReclamacion.garantia_id == garantia_id)
    if estado:
        q = q.where(EAMGarantiaReclamacion.estado == estado)
    filas = list((await db.execute(q)).scalars().all())

    garantias: dict = {}
    if filas:
        r = await db.execute(select(EAMGarantia).where(
            EAMGarantia.id.in_({x.garantia_id for x in filas})))
        garantias = {g.id: g for g in r.scalars().all()}
    r = await db.execute(select(EAMActivo.id, EAMActivo.codigo))
    activos = {aid: cod for aid, cod in r.all()}

    hoy = date.today()
    return [_reclamo_a_salida(x, garantias.get(x.garantia_id), hoy, activos)
            for x in filas]


@router.post("/garantias-reclamaciones", status_code=201)
async def create_reclamacion(data: ReclamacionCreate, db: AsyncSession = Depends(get_db)):
    g = await db.get(EAMGarantia, data.garantia_id)
    if not g:
        raise HTTPException(400, "Esa garantía no existe")
    if data.estado not in ESTADOS_RECLAMO:
        raise HTTPException(400, f"Estado no válido: {', '.join(ESTADOS_RECLAMO)}")
    campos = data.model_dump()
    campos["fecha"] = campos.get("fecha") or date.today()
    if campos["estado"] in ESTADOS_RECLAMO_CERRADOS and not campos.get("fecha_cierre"):
        campos["fecha_cierre"] = date.today()
    obj = EAMGarantiaReclamacion(**campos)
    db.add(obj)
    # Reclamar mueve la garantía a RECLAMADA, que es su estado real: hay una
    # gestión abierta con el proveedor. Solo si no está cancelada.
    if g.estado != "CANCELADA":
        g.estado = "RECLAMADA"
    await db.commit(); await db.refresh(obj)
    r = await db.execute(select(EAMActivo.id, EAMActivo.codigo))
    return _reclamo_a_salida(obj, g, date.today(), {a: c for a, c in r.all()})


@router.put("/garantias-reclamaciones/{rid}")
async def actualizar_reclamacion(rid: int, data: ReclamacionCreate,
                                 db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMGarantiaReclamacion, rid)
    if not obj:
        raise HTTPException(404, "Esa reclamación no existe")
    if data.estado not in ESTADOS_RECLAMO:
        raise HTTPException(400, f"Estado no válido: {', '.join(ESTADOS_RECLAMO)}")
    for campo, valor in data.model_dump(exclude={"garantia_id"}).items():
        setattr(obj, campo, valor)
    obj.fecha = obj.fecha or date.today()
    # Cerrar sin fecha de cierre dejaría los días de gestión creciendo para
    # siempre sobre un reclamo que ya terminó.
    if obj.estado in ESTADOS_RECLAMO_CERRADOS and not obj.fecha_cierre:
        obj.fecha_cierre = date.today()
    if obj.estado == "EN_PROCESO":
        obj.fecha_cierre = None
    await db.commit(); await db.refresh(obj)
    g = await db.get(EAMGarantia, obj.garantia_id)
    r = await db.execute(select(EAMActivo.id, EAMActivo.codigo))
    return _reclamo_a_salida(obj, g, date.today(), {a: c for a, c in r.all()})


@router.delete("/garantias-reclamaciones/{rid}", status_code=204)
async def eliminar_reclamacion(rid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(EAMGarantiaReclamacion, rid)
    if not obj:
        raise HTTPException(404, "Esa reclamación no existe")
    garantia_id = obj.garantia_id
    await db.delete(obj); await db.commit()
    # Si era el último reclamo, la garantía deja de estar reclamada: se queda
    # en RECLAMADA para siempre si no se devuelve el estado acá.
    r = await db.execute(select(func.count(EAMGarantiaReclamacion.id))
                         .where(EAMGarantiaReclamacion.garantia_id == garantia_id))
    if (r.scalar() or 0) == 0:
        g = await db.get(EAMGarantia, garantia_id)
        if g and g.estado == "RECLAMADA":
            g.estado = "VIGENTE"
            await db.commit()


# ─── Calibraciones ────────────────────────────────────────────────────────────

@router.get("/calibraciones", response_model=List[CalibracionResponse])
async def list_calibraciones(estado: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = select(EAMCalibracion)
    if estado:
        q = q.where(EAMCalibracion.estado == estado)
    result = await db.execute(q)
    return result.scalars().all()

@router.post("/calibraciones", response_model=CalibracionResponse)
async def create_calibracion(data: CalibracionCreate, db: AsyncSession = Depends(get_db)):
    obj = EAMCalibracion(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@router.get("/kpis/diarios")
async def list_kpis_diarios(limit: int = 30, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EAMKPIDiario).order_by(EAMKPIDiario.fecha.desc()).limit(limit)
    )
    return result.scalars().all()
