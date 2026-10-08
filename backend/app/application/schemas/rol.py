"""
Los perfiles de una empresa: qué pantallas ve cada persona.

Las claves de permiso NO se listan acá. Vivían escritas en este archivo, en el
mapa de rutas del portal y en las casillas de la pantalla, y las tres listas se
desincronizaron: ERP, SCM y SST se podían marcar, el portal los exigía para
dejar entrar, y este esquema los descartaba en silencio al guardar. Un perfil
con esos módulos no funcionaba y no había manera de averiguar por qué.

Ahora la lista está una sola vez, en `core/permisos_perfil.py`, y acá se acepta
un mapa libre que se normaliza contra ella: lo que no exista se descarta y lo
que falte queda en «no».
"""
from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.permisos_perfil import normalizar


class RolCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    label: Optional[str] = None
    descripcion: Optional[str] = None
    color: str = "#6366f1"
    permisos: Dict[str, bool] = {}

    @field_validator("permisos", mode="before")
    @classmethod
    def _solo_las_conocidas(cls, v):
        return normalizar(v)


class RolUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    label: Optional[str] = None
    descripcion: Optional[str] = None
    color: Optional[str] = None
    permisos: Optional[Dict[str, bool]] = None

    @field_validator("permisos", mode="before")
    @classmethod
    def _solo_las_conocidas(cls, v):
        return None if v is None else normalizar(v)


class RolResponse(BaseModel):
    id: int
    nombre: str
    label: Optional[str] = None
    descripcion: Optional[str] = None
    color: str
    permisos: Dict[str, bool]
    es_sistema: bool
    total_usuarios: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
