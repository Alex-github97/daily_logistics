"""
WFM · Personal operativo — Modelos
Prefijo de tabla: per_

Las personas que operan (bodega, caja, conducción…): su perfil (carné y
habilidades), las estaciones de trabajo, la programación del día (quién va a
qué estación), las jornadas con sus pausas y el tiempo en cada estación.
Las tareas de los demás módulos (las del WMS, por ejemplo) se asignan a quien
tiene la jornada abierta, según su estación.
"""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from app.infrastructure.models.base import Base, TimestampMixin

# Lo que una persona sabe hacer (y se exige en ciertas estaciones).
HABILIDADES = ("MONTACARGAS", "RECEPCION", "UBICACION", "REABASTECIMIENTO", "PICKING", "EMPAQUE", "DESPACHO",
               "CONTEO", "CAJA", "CONDUCCION")
# Tipos de tarea del WMS que una estación recibe por «tomar siguiente».
FUNCIONES_WMS = ("UBICACION", "REABASTECIMIENTO", "MOVIMIENTO")


class PerEstacion(Base, TimestampMixin):
    """Un puesto de trabajo: «Recepción muelle 1», «Montacargas pasillo A»,
    «Picking frentes», «Caja 1»… Define qué tareas recibe quien está en ella y
    en qué zonas."""
    __tablename__ = "per_estaciones"
    id                   = Column(Integer, primary_key=True, index=True)
    codigo               = Column(String(30), nullable=False, unique=True)
    nombre               = Column(String(120), nullable=False)
    # RECEPCION / UBICACION / REABASTECIMIENTO / PICKING / EMPAQUE / DESPACHO / CONTEO / CAJA / CONDUCCION / GENERAL
    tipo                 = Column(String(20), nullable=False, default="GENERAL")
    almacen_id           = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=True, index=True)
    # Tareas del WMS que recibe (UBICACION, REABASTECIMIENTO, MOVIMIENTO) y zonas (vacío = todas).
    funciones            = Column(JSON, nullable=True)
    zonas                = Column(JSON, nullable=True)
    requiere_montacargas = Column(Boolean, nullable=False, default=False)
    capacidad            = Column(Integer, nullable=False, default=1)      # personas a la vez
    color                = Column(String(9), nullable=True)
    activo               = Column(Boolean, nullable=False, default=True)
    notas                = Column(Text, nullable=True)


class PerPerfil(Base, TimestampMixin):
    """El perfil operativo de un usuario: carné (para marcar en el kiosco),
    cargo, habilidades y su estación habitual."""
    __tablename__ = "per_perfiles"
    id                   = Column(Integer, primary_key=True, index=True)
    usuario_id           = Column(Integer, ForeignKey("usuarios.id"), nullable=False, unique=True)
    carne                = Column(String(40), nullable=True, unique=True)
    cargo                = Column(String(80), nullable=True)
    habilidades          = Column(JSON, nullable=True)
    almacen_id           = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=True)
    estacion_id          = Column(Integer, ForeignKey("per_estaciones.id", ondelete="SET NULL"), nullable=True)
    activo               = Column(Boolean, nullable=False, default=True)


class PerProgramacion(Base, TimestampMixin):
    """Quién va a qué estación un día (y en qué horario)."""
    __tablename__ = "per_programacion"
    __table_args__ = (UniqueConstraint("fecha", "usuario_id", "turno", name="uq_per_programacion"),)
    id          = Column(Integer, primary_key=True, index=True)
    fecha       = Column(Date, nullable=False, index=True)
    turno       = Column(String(20), nullable=False, default="DIA")     # DIA / MANANA / TARDE / NOCHE
    hora_inicio = Column(String(5), nullable=True)                      # «06:00»
    hora_fin    = Column(String(5), nullable=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    estacion_id = Column(Integer, ForeignKey("per_estaciones.id", ondelete="CASCADE"), nullable=False, index=True)
    notas       = Column(String(200), nullable=True)


class PerJornada(Base, TimestampMixin):
    """La jornada de una persona: desde que marca la entrada hasta la salida.
    Solo con la jornada ACTIVA (no en pausa) recibe tareas."""
    __tablename__ = "per_jornadas"
    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    almacen_id  = Column(Integer, ForeignKey("wms_almacenes.id"), nullable=False, index=True)
    # ACTIVA / PAUSADA / CERRADA
    estado      = Column(String(10), nullable=False, default="ACTIVA", index=True)
    inicio      = Column(DateTime(timezone=True), nullable=False)
    fin         = Column(DateTime(timezone=True), nullable=True)
    estacion_id = Column(Integer, ForeignKey("per_estaciones.id", ondelete="SET NULL"), nullable=True)
    # Sin estación: lo que la persona eligió al entrar.
    funciones   = Column(JSON, nullable=True)
    zonas       = Column(JSON, nullable=True)
    montacargas = Column(Boolean, nullable=False, default=False)
    cierre_auto = Column(Boolean, nullable=False, default=False)
    # KIOSCO (carné) / APP (su propio dispositivo) / SUPERVISOR
    origen      = Column(String(12), nullable=True)
    notas       = Column(Text, nullable=True)


class PerJornadaPausa(Base, TimestampMixin):
    __tablename__ = "per_jornada_pausas"
    id         = Column(Integer, primary_key=True, index=True)
    jornada_id = Column(Integer, ForeignKey("per_jornadas.id", ondelete="CASCADE"), nullable=False, index=True)
    # DESCANSO / ALMUERZO / CAPACITACION / REUNION / OTRO
    motivo     = Column(String(20), nullable=False)
    inicio     = Column(DateTime(timezone=True), nullable=False)
    fin        = Column(DateTime(timezone=True), nullable=True)


class PerJornadaTramo(Base, TimestampMixin):
    """Cuánto estuvo la persona en cada estación durante la jornada (cambia
    cuando el supervisor la mueve)."""
    __tablename__ = "per_jornada_tramos"
    id          = Column(Integer, primary_key=True, index=True)
    jornada_id  = Column(Integer, ForeignKey("per_jornadas.id", ondelete="CASCADE"), nullable=False, index=True)
    estacion_id = Column(Integer, ForeignKey("per_estaciones.id", ondelete="SET NULL"), nullable=True)
    inicio      = Column(DateTime(timezone=True), nullable=False)
    fin         = Column(DateTime(timezone=True), nullable=True)
