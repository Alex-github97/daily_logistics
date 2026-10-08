from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import date


class KPIResumen(BaseModel):
    total_estibas: int
    disponibles: int
    en_transito: int
    en_cliente: int
    pendiente_retorno: int
    danadas: int
    en_reparacion: int
    propias: int
    alquiladas: int
    alertas_activas: int
    movimientos_hoy: int
    manifiestos_activos: int
    edad_promedio_meses: float = 0.0
    total_costos_acumulados: float = 0.0
    faltantes: int = 0
    perdidas: int = 0
    valor_perdidas: float = 0.0
    tiempo_promedio_retorno_dias: float = 0.0


class DanoEstadistica(BaseModel):
    codigo: str
    descripcion: str
    cantidad: int
    porcentaje: float
    costo_total: Optional[float] = None


class MovimientoTendencia(BaseModel):
    fecha: date
    cargas: int
    descargas: int
    transferencias: int
    total: int


class UbicacionOcupacion(BaseModel):
    ubicacion_id: int
    nombre: str
    tipo: str
    total_estibas: int
    capacidad: Optional[int] = None
    porcentaje_ocupacion: Optional[float] = None


class AlertaResumen(BaseModel):
    id: int
    tipo: str
    nivel: str
    titulo: str
    fecha: str
    estiba_codigo: Optional[str] = None


class EdadDistribucion(BaseModel):
    rango: str
    cantidad: int
    porcentaje: float


class CostoMensual(BaseModel):
    mes: str
    costo_total: float
    cantidad_mantenimientos: int


class RetornoMensual(BaseModel):
    mes: str
    promedio_dias: float
    cantidad_retornos: int


class RetornoData(BaseModel):
    tiempo_promedio_dias: float
    retorno_por_mes: List[RetornoMensual]


class DashboardResponse(BaseModel):
    kpis: KPIResumen
    tendencia_movimientos: List[MovimientoTendencia]
    top_danos: List[DanoEstadistica]
    ocupacion_ubicaciones: List[UbicacionOcupacion]
    alertas_recientes: List[AlertaResumen]
    movimientos_recientes: List[Dict[str, Any]]
    edad_distribucion: List[EdadDistribucion] = []
    costos_por_mes: List[CostoMensual] = []
