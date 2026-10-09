from sqlalchemy import Column, Integer, String, Boolean, Text, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin

# Permisos de Daily Logistics: un permiso por módulo, más la administración.
MODULOS_SISTEMA = ["wms", "tms", "pos", "wfm", "usuarios", "configuracion"]


def _permisos(*activos: str) -> dict:
    return {m: m in activos for m in MODULOS_SISTEMA}


ROLES_DEFECTO = [
    {
        "nombre": "ADMINISTRADOR",
        "label": "Administrador",
        "descripcion": "Acceso total: módulos, usuarios, roles y configuración de la empresa.",
        "color": "#DC2626",
        "es_sistema": True,
        "permisos": _permisos(*MODULOS_SISTEMA),
    },
    {
        "nombre": "SUPERVISOR_LOGISTICO",
        "label": "Supervisor Logístico",
        "descripcion": "Supervisa almacén, transporte, punto de venta y personal; aprueba excepciones.",
        "color": "#D97706",
        "es_sistema": True,
        "permisos": _permisos("wms", "tms", "pos", "wfm"),
    },
    {
        "nombre": "OPERADOR_BODEGA",
        "label": "Operador de Bodega",
        "descripcion": "Recibe, ubica, cuenta, alista, empaca y despacha en el WMS.",
        "color": "#2563EB",
        "es_sistema": True,
        "permisos": _permisos("wms", "wfm"),
    },
    {
        "nombre": "PLANEADOR_TRANSPORTE",
        "label": "Planeador de Transporte",
        "descripcion": "Planea viajes, asigna vehículos y conductores y hace seguimiento en el TMS.",
        "color": "#0891B2",
        "es_sistema": True,
        "permisos": _permisos("tms"),
    },
    {
        "nombre": "CAJERO",
        "label": "Cajero",
        "descripcion": "Abre y cierra su turno de caja y vende en el POS.",
        "color": "#16A34A",
        "es_sistema": True,
        "permisos": _permisos("pos", "wfm"),
    },
    {
        "nombre": "AUDITOR",
        "label": "Auditor",
        "descripcion": "Consulta los módulos para auditoría y control.",
        "color": "#7C3AED",
        "es_sistema": True,
        "permisos": _permisos("wms", "tms", "pos", "wfm"),
    },
    {
        "nombre": "CONSULTA",
        "label": "Consulta",
        "descripcion": "Consulta de almacén y transporte.",
        "color": "#6B7280",
        "es_sistema": True,
        "permisos": _permisos("wms", "tms"),
    },
    {
        "nombre": "CONDUCTOR",
        "label": "Conductor",
        "descripcion": "Perfil para conductores: sus viajes en el TMS.",
        "color": "#0EA5E9",
        "es_sistema": True,
        "permisos": _permisos("tms", "wfm"),
    },
]

class Rol(Base, TimestampMixin):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), unique=True, nullable=False)
    label = Column(String(150), nullable=True)
    descripcion = Column(Text, nullable=True)
    color = Column(String(20), default="#6366f1", nullable=False)
    permisos = Column(JSON, nullable=False, default=dict)
    es_sistema = Column(Boolean, default=False, nullable=False)

    usuarios = relationship("Usuario", back_populates="rol_obj", lazy="dynamic")
