"""
Lo que entra a la API de GRC.

Solo lo que una persona escribe o elige. Lo que el sistema calcula (código,
niveles, prioridad, residual, efectividad del control, fechas de próxima
prueba, nivel de riesgo del tercero, estado vencido) no se recibe: si se
aceptara, el formulario podría contradecir al cálculo.

Las personas llegan como id de usuario; las clasificaciones, como el nombre del
valor del catálogo, que el servidor valida.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.infrastructure.models.grc import (
    EfectividadControlGRCEnum, EstadoAuditoriaGRCEnum, EstadoCumplimientoGRCEnum,
    EstadoHallazgoGRCEnum, EstadoRiesgoGRCEnum, SeveridadGRCEnum, TipoControlGRCEnum,
    TratamientoRiesgoGRCEnum,
)

class _Base(BaseModel):
    model_config = {"extra": "forbid"}


class ComiteIn(_Base):
    nombre: str = Field(min_length=1, max_length=200)
    tipo: Optional[str] = None
    periodicidad: Optional[str] = None
    presidente_id: Optional[int] = None
    secretario_id: Optional[int] = None
    quorum_minimo: Optional[int] = Field(default=None, ge=1)
    descripcion: Optional[str] = None
    miembros: List[int] = []


class SesionIn(_Base):
    comite_id: int
    fecha: date
    asistentes: List[int] = []
    temas: Optional[str] = None
    decisiones: Optional[str] = None
    proxima: Optional[date] = None
    acta_url: Optional[str] = None
    riesgos: List[int] = []     # riesgos revisados en la sesión


class PoliticaIn(_Base):
    nombre: str = Field(min_length=1, max_length=300)
    tipo: Optional[str] = None
    version: str = "1.0"
    propietario_id: Optional[int] = None
    aprobador_id: Optional[int] = None
    fecha_vigencia: Optional[date] = None
    fecha_revision: Optional[date] = None
    periodicidad_revision: Optional[str] = None
    alcance: Optional[str] = None
    descripcion: Optional[str] = None
    dms_documento_id: Optional[int] = None
    aceptaciones_requeridas: bool = False


class CambioEstadoIn(_Base):
    estado: str
    comentario: Optional[str] = None


class ObligacionIn(_Base):
    nombre: str = Field(min_length=1, max_length=300)
    tipo: Optional[str] = None
    marco: Optional[str] = None
    articulo: Optional[str] = None
    pais: Optional[str] = None
    proceso: Optional[str] = None
    area: Optional[str] = None
    descripcion: Optional[str] = None
    fecha_vigencia: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    periodicidad: Optional[str] = None
    responsable_id: Optional[int] = None


class CumplimientoIn(_Base):
    obligacion_id: int
    proceso: Optional[str] = None
    area: Optional[str] = None
    responsable_id: Optional[int] = None
    estado: EstadoCumplimientoGRCEnum = EstadoCumplimientoGRCEnum.EN_EVALUACION
    puntaje: Optional[int] = Field(default=None, ge=0, le=100)
    ultima_evaluacion: Optional[date] = None
    evidencias: Optional[str] = None
    observaciones: Optional[str] = None


class ControlIn(_Base):
    nombre: str = Field(min_length=1, max_length=300)
    tipo: Optional[TipoControlGRCEnum] = None
    descripcion: Optional[str] = None
    proceso: Optional[str] = None
    area: Optional[str] = None
    responsable_id: Optional[int] = None
    frecuencia: Optional[str] = None
    periodicidad_prueba: Optional[str] = None
    automatizado: bool = False


class PruebaIn(_Base):
    control_id: int
    tipo: Literal["diseno", "efectividad"] = "efectividad"
    fecha: date
    probador_id: Optional[int] = None
    resultado: EfectividadControlGRCEnum
    muestra: Optional[int] = Field(default=None, ge=0)
    excepciones: Optional[int] = Field(default=None, ge=0)
    procedimiento: Optional[str] = None
    conclusion: Optional[str] = None

    @field_validator("resultado")
    @classmethod
    def _probado(cls, v):
        if v == EfectividadControlGRCEnum.NO_PROBADO:
            raise ValueError("Una prueba registrada tiene un resultado: efectivo, parcial o inefectivo")
        return v


class RiesgoIn(_Base):
    nombre: str = Field(min_length=1, max_length=300)
    descripcion: Optional[str] = None
    causas: Optional[str] = None
    consecuencias: Optional[str] = None
    tipo: Optional[str] = None
    proceso: Optional[str] = None
    area: Optional[str] = None
    responsable_id: Optional[int] = None
    probabilidad_inherente: Optional[int] = Field(default=None, ge=1, le=5)
    impacto_inherente: Optional[int] = Field(default=None, ge=1, le=5)
    estado: EstadoRiesgoGRCEnum = EstadoRiesgoGRCEnum.IDENTIFICADO
    tratamiento: Optional[TratamientoRiesgoGRCEnum] = None
    comite_id: Optional[int] = None
    tercero_id: Optional[int] = None
    fecha_revision: Optional[date] = None


class TratamientoIn(_Base):
    riesgo_id: int
    tipo: Optional[TratamientoRiesgoGRCEnum] = None
    descripcion: Optional[str] = None
    responsable_id: Optional[int] = None
    fecha_objetivo: Optional[date] = None
    avance: int = Field(default=0, ge=0, le=100)
    evidencia_url: Optional[str] = None


class KriIn(_Base):
    riesgo_id: int
    nombre: str = Field(min_length=1, max_length=300)
    unidad: Optional[str] = None
    direccion: Literal["sube", "baja"] = "sube"
    umbral_alerta: Decimal
    umbral_critico: Decimal
    periodicidad: Optional[str] = None
    responsable_id: Optional[int] = None
    descripcion: Optional[str] = None


class MedicionKriIn(_Base):
    periodo: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    valor: Decimal
    nota: Optional[str] = None


class EvidenciaIn(_Base):
    nombre: str = Field(min_length=1, max_length=300)
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    url: Optional[str] = None
    fecha_emision: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    responsable_id: Optional[int] = None
    referencia_tipo: str
    referencia_id: int


class AuditoriaIn(_Base):
    nombre: str = Field(min_length=1, max_length=300)
    tipo: Optional[str] = None
    estado: EstadoAuditoriaGRCEnum = EstadoAuditoriaGRCEnum.PLANIFICADA
    auditor_lider_id: Optional[int] = None
    equipo: List[int] = []
    proceso: Optional[str] = None
    area: Optional[str] = None
    marco: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    fecha_reporte: Optional[date] = None
    alcance: Optional[str] = None
    criterios: Optional[str] = None
    presupuesto: Optional[Decimal] = Field(default=None, ge=0)
    observaciones: Optional[str] = None


class HallazgoIn(_Base):
    auditoria_id: Optional[int] = None
    incidente_id: Optional[int] = None
    riesgo_id: Optional[int] = None
    control_id: Optional[int] = None
    titulo: str = Field(min_length=1, max_length=300)
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    severidad: Optional[SeveridadGRCEnum] = None
    proceso: Optional[str] = None
    area: Optional[str] = None
    responsable_id: Optional[int] = None
    fecha_limite: Optional[date] = None
    estado: EstadoHallazgoGRCEnum = EstadoHallazgoGRCEnum.ABIERTO
    impacto: Optional[str] = None
    recomendacion: Optional[str] = None
    causa_raiz: Optional[str] = None

    @field_validator("estado")
    @classmethod
    def _sin_vencido(cls, v):
        # «Vencido» lo calcula el servidor con la fecha límite; no se elige.
        return EstadoHallazgoGRCEnum.ABIERTO if v == EstadoHallazgoGRCEnum.VENCIDO else v


class PlanIn(_Base):
    hallazgo_id: int
    accion: str = Field(min_length=1)
    responsable_id: Optional[int] = None
    fecha_objetivo: Optional[date] = None
    avance: int = Field(default=0, ge=0, le=100)
    evidencia: Optional[str] = None
    observaciones: Optional[str] = None


ESTADOS_INCIDENTE = ("abierto", "en_investigacion", "contenido", "cerrado")


class IncidenteIn(_Base):
    titulo: str = Field(min_length=1, max_length=300)
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    severidad: Optional[SeveridadGRCEnum] = None
    urgencia: Optional[SeveridadGRCEnum] = None
    impacto: Optional[str] = None
    perdida_estimada: Optional[Decimal] = Field(default=None, ge=0)
    proceso: Optional[str] = None
    area: Optional[str] = None
    riesgo_id: Optional[int] = None
    control_id: Optional[int] = None
    reportado_por_id: Optional[int] = None
    responsable_id: Optional[int] = None
    fecha_ocurrencia: Optional[datetime] = None
    estado: Literal["abierto", "en_investigacion", "contenido", "cerrado"] = "abierto"
    causa_raiz: Optional[str] = None
    acciones_tomadas: Optional[str] = None
    lecciones_aprendidas: Optional[str] = None


class ContinuidadIn(_Base):
    proceso: str = Field(min_length=1)
    criticidad: Optional[SeveridadGRCEnum] = None
    rto_horas: Optional[int] = Field(default=None, ge=0)
    rpo_horas: Optional[int] = Field(default=None, ge=0)
    mtpd_horas: Optional[int] = Field(default=None, ge=0)
    impacto_financiero_hora: Optional[Decimal] = Field(default=None, ge=0)
    impacto_operativo: Optional[str] = None
    sistemas_criticos: List[str] = []
    responsable_id: Optional[int] = None
    plan_contingencia: Optional[str] = None
    estado_plan: Literal["activo", "en_actualizacion", "inactivo"] = "activo"
    ultima_revision: Optional[date] = None
    periodicidad_revision: Optional[str] = None


class SimulacroIn(_Base):
    continuidad_id: Optional[int] = None
    nombre: str = Field(min_length=1, max_length=300)
    fecha: Optional[date] = None
    tipo: Optional[str] = None
    resultado: Optional[str] = None
    coordinador_id: Optional[int] = None
    participantes: List[int] = []
    rto_logrado_horas: Optional[int] = Field(default=None, ge=0)
    observaciones: Optional[str] = None
    lecciones: Optional[str] = None


class TerceroIn(_Base):
    nombre: str = Field(min_length=1, max_length=300)
    nit: Optional[str] = None
    tipo: Optional[str] = None
    pais: Optional[str] = None
    sector: Optional[str] = None
    contacto: Optional[str] = None
    contacto_email: Optional[str] = None
    proveedor_id: Optional[int] = None
    cliente_id: Optional[int] = None
    responsable_id: Optional[int] = None
    criticidad: Optional[SeveridadGRCEnum] = None
    estado: Literal["activo", "en_evaluacion", "suspendido", "retirado"] = "activo"


class EvaluacionIn(_Base):
    tercero_id: int
    periodo: Optional[str] = None
    fecha: Optional[date] = None
    cumplimiento_legal: Optional[int] = Field(default=None, ge=0, le=100)
    riesgo_reputacional: Optional[int] = Field(default=None, ge=0, le=100)
    solidez_financiera: Optional[int] = Field(default=None, ge=0, le=100)
    seguridad_info: Optional[int] = Field(default=None, ge=0, le=100)
    evaluador_id: Optional[int] = None
    observaciones: Optional[str] = None


class VinculoIn(_Base):
    origen_tipo: str
    origen_id: int
    destino_tipo: str
    destino_id: int
    nota: Optional[str] = None


class RiesgoControlIn(_Base):
    control_id: int
    observaciones: Optional[str] = None


class EscalaIn(_Base):
    eje: Literal["probabilidad", "impacto"]
    valor: int = Field(ge=1, le=5)
    nombre: str = Field(min_length=1, max_length=60)
    descripcion: Optional[str] = None


class BandaIn(_Base):
    prioridad: Literal["baja", "media", "alta", "critica"]
    minimo: int = Field(ge=1, le=25)
    color: Optional[str] = None
    respuesta: Optional[str] = None


class ApetitoIn(_Base):
    categoria: str
    apetito: Optional[int] = Field(default=None, ge=1, le=25)
