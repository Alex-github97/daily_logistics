"""AGS - Agenda de Servicios.

Modulo para negocios de servicios con cita previa: salones de belleza,
barberias, spa, plomeros, albaniles, tecnicos a domicilio.

La idea central es que el negocio preconfigura su catalogo de servicios
(con precio y duracion), su equipo y los horarios de cada persona; sobre eso
la agenda calcula disponibilidad real y cada cita atendida se convierte en un
ingreso trazable por cliente, por profesional y por servicio.
"""
import enum
import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


# ──────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────

class EstadoCitaEnum(str, enum.Enum):
    AGENDADA   = "AGENDADA"      # reservada, sin confirmar
    CONFIRMADA = "CONFIRMADA"    # el cliente confirmo que viene
    EN_CURSO   = "EN_CURSO"      # se esta atendiendo
    COMPLETADA = "COMPLETADA"    # atendida y cobrada
    CANCELADA  = "CANCELADA"     # cancelada con aviso
    NO_ASISTIO = "NO_ASISTIO"    # el cliente no llego (no-show)


class LugarServicioEnum(str, enum.Enum):
    LOCAL     = "LOCAL"       # en el establecimiento
    DOMICILIO = "DOMICILIO"   # en la direccion del cliente


class OrigenCitaEnum(str, enum.Enum):
    MOSTRADOR = "MOSTRADOR"
    TELEFONO  = "TELEFONO"
    WHATSAPP  = "WHATSAPP"
    ONLINE    = "ONLINE"      # autoagendada por el cliente
    RECURRENTE = "RECURRENTE"  # generada desde una cita periodica


class MedioPagoEnum(str, enum.Enum):
    EFECTIVO     = "EFECTIVO"
    NEQUI        = "NEQUI"
    DAVIPLATA    = "DAVIPLATA"
    TRANSFERENCIA = "TRANSFERENCIA"
    TARJETA      = "TARJETA"
    QR           = "QR"
    CREDITO      = "CREDITO"    # queda por cobrar


class TipoPagoEnum(str, enum.Enum):
    ANTICIPO = "ANTICIPO"   # abono antes de terminar (obras, trabajos largos)
    PAGO     = "PAGO"       # pago del servicio
    PROPINA  = "PROPINA"


# ──────────────────────────────────────────
# CONFIGURACION DEL NEGOCIO
# ──────────────────────────────────────────

class AGSConfig(Base, TimestampMixin):
    """Parametros del negocio. Fila unica (id=1)."""
    __tablename__ = "ags_config"

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    nombre_negocio = sa.Column(sa.String(160), nullable=False, default="Mi negocio")
    tipo_negocio   = sa.Column(sa.String(60), default="SALON_BELLEZA")
    nit            = sa.Column(sa.String(40), nullable=True)
    telefono       = sa.Column(sa.String(40), nullable=True)
    direccion      = sa.Column(sa.String(200), nullable=True)
    ciudad         = sa.Column(sa.String(80), nullable=True)

    # Ventana de atencion y granularidad de la agenda
    hora_apertura  = sa.Column(sa.String(5), default="08:00")
    hora_cierre    = sa.Column(sa.String(5), default="19:00")
    dias_laborales = sa.Column(sa.JSON, nullable=True)   # [1,2,3,4,5,6] lunes=1..domingo=7
    intervalo_agenda_min = sa.Column(sa.Integer, default=30)

    # Dinero
    moneda            = sa.Column(sa.String(8), default="COP")
    iva_pct           = sa.Column(sa.Float, default=0)
    comision_defecto_pct = sa.Column(sa.Float, default=0)

    # Politicas de agenda
    permite_sobrecupo      = sa.Column(sa.Boolean, default=False)  # permitir 2 citas a la vez
    anticipacion_minima_min = sa.Column(sa.Integer, default=0)     # no agendar con menos de X min
    tolerancia_no_show_min  = sa.Column(sa.Integer, default=15)

    # Plantilla del recordatorio de WhatsApp
    mensaje_recordatorio = sa.Column(
        sa.Text,
        default="Hola {cliente}, le recordamos su cita en {negocio} "
                "el {fecha} a las {hora} para {servicio}. Cualquier cambio nos avisa.",
    )

    # ── Reserva online (el cliente se agenda a si mismo) ──────────────
    # La pagina publica se sirve en /reservar/{slug} y no pide login. Se
    # entrega apagada: el negocio decide cuando abrirla.
    reserva_online_activa = sa.Column(sa.Boolean, default=False)
    slug = sa.Column(sa.String(80), nullable=True, unique=True, index=True)
    mensaje_bienvenida = sa.Column(sa.Text, nullable=True)

    # Limites que evitan que la agenda publica se llene de reservas basura
    dias_max_anticipacion = sa.Column(sa.Integer, default=30)
    max_citas_pendientes_cliente = sa.Column(sa.Integer, default=3)

    # Politica de cancelacion desde la pagina publica
    permite_cancelar_online = sa.Column(sa.Boolean, default=True)
    horas_min_cancelacion = sa.Column(sa.Integer, default=4)

    # Si esta activo, la cita online entra como AGENDADA y el negocio la
    # confirma; si no, entra ya CONFIRMADA.
    requiere_confirmacion_online = sa.Column(sa.Boolean, default=True)


# ──────────────────────────────────────────
# CATALOGO DE SERVICIOS
# ──────────────────────────────────────────

class AGSCategoriaServicio(Base, TimestampMixin):
    __tablename__ = "ags_categoria_servicio"
    __table_args__ = (UniqueConstraint("nombre", name="uq_ags_categoria_nombre"),)

    id     = sa.Column(sa.Integer, primary_key=True, index=True)
    nombre = sa.Column(sa.String(120), nullable=False)
    descripcion = sa.Column(sa.Text, nullable=True)
    color  = sa.Column(sa.String(9), default="#A21CAF")
    orden  = sa.Column(sa.Integer, default=0)
    activo = sa.Column(sa.Boolean, default=True, nullable=False)


class AGSServicio(Base, TimestampMixin):
    """Servicio con precio y duracion preconfigurados.

    La duracion es lo que permite que la agenda calcule la hora de fin y
    detecte cruces; el precio es lo que alimenta los ingresos.
    """
    __tablename__ = "ags_servicio"
    __table_args__ = (UniqueConstraint("codigo", name="uq_ags_servicio_codigo"),)

    id     = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo = sa.Column(sa.String(40), nullable=False, index=True)
    nombre = sa.Column(sa.String(160), nullable=False)
    categoria_id = sa.Column(sa.Integer, sa.ForeignKey("ags_categoria_servicio.id", ondelete="SET NULL"), nullable=True)
    descripcion  = sa.Column(sa.Text, nullable=True)

    duracion_min = sa.Column(sa.Integer, nullable=False, default=30)
    precio       = sa.Column(sa.Float, nullable=False, default=0)
    costo_insumos = sa.Column(sa.Float, default=0)      # para calcular margen real
    comision_pct  = sa.Column(sa.Float, nullable=True)  # override de la comision del profesional

    # Los oficios a domicilio (plomeria, albanileria) necesitan direccion y
    # suelen cobrar materiales aparte de la mano de obra.
    permite_domicilio = sa.Column(sa.Boolean, default=False)
    cobra_materiales  = sa.Column(sa.Boolean, default=False)
    requiere_anticipo = sa.Column(sa.Boolean, default=False)

    color  = sa.Column(sa.String(9), nullable=True)
    activo = sa.Column(sa.Boolean, default=True, nullable=False)


# ──────────────────────────────────────────
# EQUIPO
# ──────────────────────────────────────────

class AGSProfesional(Base, TimestampMixin):
    """Quien presta el servicio: estilista, barbero, plomero, oficial."""
    __tablename__ = "ags_profesional"
    __table_args__ = (UniqueConstraint("codigo", name="uq_ags_profesional_codigo"),)

    id     = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo = sa.Column(sa.String(40), nullable=False, index=True)
    nombre = sa.Column(sa.String(160), nullable=False)
    documento = sa.Column(sa.String(40), nullable=True)
    telefono  = sa.Column(sa.String(40), nullable=True)
    email     = sa.Column(sa.String(160), nullable=True)
    especialidad = sa.Column(sa.String(120), nullable=True)

    color = sa.Column(sa.String(9), default="#A21CAF")   # para distinguirlo en la agenda
    comision_pct = sa.Column(sa.Float, default=0)
    salario_base = sa.Column(sa.Float, default=0)
    fecha_ingreso = sa.Column(sa.Date, nullable=True)

    acepta_domicilio = sa.Column(sa.Boolean, default=False)
    notas  = sa.Column(sa.Text, nullable=True)
    activo = sa.Column(sa.Boolean, default=True, nullable=False)


class AGSProfesionalServicio(Base, TimestampMixin):
    """Que servicios sabe prestar cada profesional."""
    __tablename__ = "ags_profesional_servicio"
    __table_args__ = (
        UniqueConstraint("profesional_id", "servicio_id", name="uq_ags_prof_servicio"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    profesional_id = sa.Column(sa.Integer, sa.ForeignKey("ags_profesional.id", ondelete="CASCADE"), nullable=False, index=True)
    servicio_id    = sa.Column(sa.Integer, sa.ForeignKey("ags_servicio.id", ondelete="CASCADE"), nullable=False, index=True)


class AGSHorarioProfesional(Base, TimestampMixin):
    """Jornada habitual por dia de la semana. Base del calculo de disponibilidad.

    Se permiten varias franjas por dia para modelar la hora de almuerzo
    (ej. 08:00-12:00 y 14:00-18:00).
    """
    __tablename__ = "ags_horario_profesional"
    __table_args__ = (
        UniqueConstraint("profesional_id", "dia_semana", "hora_inicio", name="uq_ags_horario_prof_dia"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    profesional_id = sa.Column(sa.Integer, sa.ForeignKey("ags_profesional.id", ondelete="CASCADE"), nullable=False, index=True)
    dia_semana  = sa.Column(sa.Integer, nullable=False)   # 1=lunes ... 7=domingo
    hora_inicio = sa.Column(sa.String(5), nullable=False)  # "08:00"
    hora_fin    = sa.Column(sa.String(5), nullable=False)  # "12:00"
    activo = sa.Column(sa.Boolean, default=True, nullable=False)


class AGSAusencia(Base, TimestampMixin):
    """Bloqueo de agenda: vacaciones, incapacidad, permiso, dia festivo."""
    __tablename__ = "ags_ausencia"

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    profesional_id = sa.Column(sa.Integer, sa.ForeignKey("ags_profesional.id", ondelete="CASCADE"), nullable=True, index=True)
    # profesional_id nulo = cierra el negocio completo (festivo, mantenimiento)
    fecha_inicio = sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    fecha_fin    = sa.Column(sa.DateTime(timezone=True), nullable=False)
    motivo = sa.Column(sa.String(160), nullable=True)
    tipo   = sa.Column(sa.String(40), default="PERMISO")


# ──────────────────────────────────────────
# CLIENTES
# ──────────────────────────────────────────

class AGSCliente(Base, TimestampMixin):
    __tablename__ = "ags_cliente"
    __table_args__ = (UniqueConstraint("codigo", name="uq_ags_cliente_codigo"),)

    id     = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo = sa.Column(sa.String(40), nullable=False, index=True)
    nombre = sa.Column(sa.String(160), nullable=False, index=True)
    documento = sa.Column(sa.String(40), nullable=True)
    telefono  = sa.Column(sa.String(40), nullable=True, index=True)
    email     = sa.Column(sa.String(160), nullable=True)
    direccion = sa.Column(sa.String(200), nullable=True)
    barrio    = sa.Column(sa.String(120), nullable=True)
    ciudad    = sa.Column(sa.String(80), nullable=True)
    fecha_nacimiento = sa.Column(sa.Date, nullable=True)

    como_nos_conocio = sa.Column(sa.String(80), nullable=True)
    acepta_recordatorios = sa.Column(sa.Boolean, default=True)
    notas  = sa.Column(sa.Text, nullable=True)   # alergias, preferencias, tono de tinte
    activo = sa.Column(sa.Boolean, default=True, nullable=False)


# ──────────────────────────────────────────
# CITAS
# ──────────────────────────────────────────

class AGSCita(Base, TimestampMixin):
    __tablename__ = "ags_cita"
    __table_args__ = (UniqueConstraint("codigo", name="uq_ags_cita_codigo"),)

    id     = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo = sa.Column(sa.String(40), nullable=False, index=True)

    cliente_id     = sa.Column(sa.Integer, sa.ForeignKey("ags_cliente.id", ondelete="RESTRICT"), nullable=False, index=True)
    profesional_id = sa.Column(sa.Integer, sa.ForeignKey("ags_profesional.id", ondelete="RESTRICT"), nullable=False, index=True)

    fecha_inicio = sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    fecha_fin    = sa.Column(sa.DateTime(timezone=True), nullable=False)
    duracion_min = sa.Column(sa.Integer, nullable=False, default=30)

    lugar = sa.Column(sa.String(20), default=LugarServicioEnum.LOCAL.value)
    direccion_servicio = sa.Column(sa.String(200), nullable=True)

    estado = sa.Column(sa.String(20), default=EstadoCitaEnum.AGENDADA.value, nullable=False, index=True)
    origen = sa.Column(sa.String(20), default=OrigenCitaEnum.MOSTRADOR.value)

    # Dinero: subtotal de servicios + materiales - descuento + propina = total
    subtotal         = sa.Column(sa.Float, default=0)
    descuento        = sa.Column(sa.Float, default=0)
    descuento_motivo = sa.Column(sa.String(160), nullable=True)
    total_materiales = sa.Column(sa.Float, default=0)
    propina          = sa.Column(sa.Float, default=0)
    total            = sa.Column(sa.Float, default=0)

    pagado     = sa.Column(sa.Boolean, default=False, index=True)
    total_pagado = sa.Column(sa.Float, default=0)
    medio_pago = sa.Column(sa.String(20), nullable=True)
    fecha_pago = sa.Column(sa.DateTime(timezone=True), nullable=True)

    comision_profesional = sa.Column(sa.Float, default=0)
    # La parte del total que es IVA. Los precios al público ya lo incluyen
    # (así lo exige el estatuto del consumidor): no se suma, se discrimina.
    iva_incluido = sa.Column(sa.Float, default=0)

    notas = sa.Column(sa.Text, nullable=True)
    motivo_cancelacion = sa.Column(sa.String(200), nullable=True)
    recordatorio_enviado = sa.Column(sa.Boolean, default=False)
    creado_por = sa.Column(sa.String(120), nullable=True)

    # Fechas reales de atencion (para medir puntualidad y duracion efectiva)
    hora_llegada = sa.Column(sa.DateTime(timezone=True), nullable=True)
    hora_inicio_real = sa.Column(sa.DateTime(timezone=True), nullable=True)
    hora_fin_real    = sa.Column(sa.DateTime(timezone=True), nullable=True)


class AGSCitaServicio(Base, TimestampMixin):
    """Servicios incluidos en la cita.

    Guarda copia del nombre y del precio del momento: si manana suben la
    tarifa, los ingresos historicos no cambian.
    """
    __tablename__ = "ags_cita_servicio"

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    cita_id     = sa.Column(sa.Integer, sa.ForeignKey("ags_cita.id", ondelete="CASCADE"), nullable=False, index=True)
    servicio_id = sa.Column(sa.Integer, sa.ForeignKey("ags_servicio.id", ondelete="SET NULL"), nullable=True)

    nombre_servicio = sa.Column(sa.String(160), nullable=False)
    cantidad        = sa.Column(sa.Float, default=1)
    precio_unitario = sa.Column(sa.Float, default=0)
    subtotal        = sa.Column(sa.Float, default=0)
    duracion_min    = sa.Column(sa.Integer, default=0)
    comision_pct    = sa.Column(sa.Float, nullable=True)


class AGSCitaMaterial(Base, TimestampMixin):
    """Materiales cobrados al cliente (tuberia, cemento, tinte, keratina)."""
    __tablename__ = "ags_cita_material"

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    cita_id = sa.Column(sa.Integer, sa.ForeignKey("ags_cita.id", ondelete="CASCADE"), nullable=False, index=True)
    descripcion     = sa.Column(sa.String(200), nullable=False)
    cantidad        = sa.Column(sa.Float, default=1)
    precio_unitario = sa.Column(sa.Float, default=0)
    subtotal        = sa.Column(sa.Float, default=0)


class AGSPagoCita(Base, TimestampMixin):
    """Cada movimiento de dinero de la cita: anticipos y pago final.

    Tenerlos por separado permite trabajos largos que se pagan por partes
    (una obra de albanileria) y cuadrar la caja por medio de pago.
    """
    __tablename__ = "ags_pago_cita"

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    cita_id = sa.Column(sa.Integer, sa.ForeignKey("ags_cita.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha   = sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    monto   = sa.Column(sa.Float, nullable=False, default=0)
    medio_pago = sa.Column(sa.String(20), default=MedioPagoEnum.EFECTIVO.value)
    tipo       = sa.Column(sa.String(20), default=TipoPagoEnum.PAGO.value)
    referencia = sa.Column(sa.String(80), nullable=True)   # numero de aprobacion / comprobante
    notas      = sa.Column(sa.Text, nullable=True)
    registrado_por = sa.Column(sa.String(120), nullable=True)
