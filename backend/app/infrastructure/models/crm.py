import enum
import sqlalchemy as sa
from app.infrastructure.models.base import Base, TimestampMixin


# ──────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────

class EstadoClienteEnum(str, enum.Enum):
    PROSPECTO        = "PROSPECTO"
    LEAD             = "LEAD"
    CLIENTE_ACTIVO   = "CLIENTE_ACTIVO"
    CLIENTE_INACTIVO = "CLIENTE_INACTIVO"
    EXCLIENTE        = "EXCLIENTE"

class TipoClienteEnum(str, enum.Enum):
    EMPRESA          = "EMPRESA"
    PERSONA_NATURAL  = "PERSONA_NATURAL"
    GOBIERNO         = "GOBIERNO"

class SegmentoClienteEnum(str, enum.Enum):
    CORPORATIVO = "CORPORATIVO"
    MEDIANA     = "MEDIANA"
    PEQUENA     = "PEQUENA"
    ESTRATEGICO = "ESTRATEGICO"

class EstadoLeadEnum(str, enum.Enum):
    FRIO       = "FRIO"
    TIBIO      = "TIBIO"
    CALIENTE   = "CALIENTE"
    CONVERTIDO = "CONVERTIDO"
    DESCARTADO = "DESCARTADO"

class EstadoOportunidadEnum(str, enum.Enum):
    IDENTIFICACION = "IDENTIFICACION"
    CALIFICACION   = "CALIFICACION"
    PROPUESTA      = "PROPUESTA"
    NEGOCIACION    = "NEGOCIACION"
    CIERRE_GANADO  = "CIERRE_GANADO"
    CIERRE_PERDIDO = "CIERRE_PERDIDO"

class EstadoCotizacionEnum(str, enum.Enum):
    BORRADOR  = "BORRADOR"
    ENVIADA   = "ENVIADA"
    APROBADA  = "APROBADA"
    RECHAZADA = "RECHAZADA"
    VENCIDA   = "VENCIDA"

class EstadoContratoEnum(str, enum.Enum):
    BORRADOR  = "BORRADOR"
    ACTIVO    = "ACTIVO"
    VENCIDO   = "VENCIDO"
    RENOVADO  = "RENOVADO"
    TERMINADO = "TERMINADO"

class EstadoTicketEnum(str, enum.Enum):
    ABIERTO    = "ABIERTO"
    EN_PROCESO = "EN_PROCESO"
    ESCALADO   = "ESCALADO"
    RESUELTO   = "RESUELTO"
    CERRADO    = "CERRADO"

class TipoTicketEnum(str, enum.Enum):
    PQRS      = "PQRS"
    RECLAMO   = "RECLAMO"
    SOLICITUD = "SOLICITUD"
    INCIDENTE = "INCIDENTE"
    CONSULTA  = "CONSULTA"

class TipoInteraccionEnum(str, enum.Enum):
    LLAMADA    = "LLAMADA"
    EMAIL      = "EMAIL"
    WHATSAPP   = "WHATSAPP"
    REUNION    = "REUNION"
    CHAT       = "CHAT"
    FORMULARIO = "FORMULARIO"

class TipoCampanaEnum(str, enum.Enum):
    EMAIL_MARKETING = "EMAIL_MARKETING"
    EVENTO          = "EVENTO"
    PROMOCION       = "PROMOCION"
    COMERCIAL       = "COMERCIAL"

class TipoEncuestaEnum(str, enum.Enum):
    NPS  = "NPS"
    CSAT = "CSAT"
    CES  = "CES"

class NivelRiesgoClienteEnum(str, enum.Enum):
    BAJO    = "BAJO"
    MEDIO   = "MEDIO"
    ALTO    = "ALTO"
    CRITICO = "CRITICO"


# ──────────────────────────────────────────
# MODELS — FK-safe order: parents before children
# ──────────────────────────────────────────

class CRMEjecutivoComercial(Base, TimestampMixin):
    __tablename__ = "crm_ejecutivo_comercial"
    id         = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo     = sa.Column(sa.String(20), unique=True, nullable=False)
    usuario_id = sa.Column(sa.Integer, nullable=True)
    nombre     = sa.Column(sa.String(120), nullable=False)
    email      = sa.Column(sa.String(120), nullable=True)
    telefono   = sa.Column(sa.String(40), nullable=True)
    region     = sa.Column(sa.String(80), nullable=True)
    meta_anual = sa.Column(sa.Numeric(18, 2), nullable=True)
    activo     = sa.Column(sa.Boolean, default=True)


class CRMCliente(Base, TimestampMixin):
    __tablename__ = "crm_cliente"
    id              = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo          = sa.Column(sa.String(20), unique=True, nullable=False)
    razon_social    = sa.Column(sa.String(200), nullable=False)
    nit             = sa.Column(sa.String(30), nullable=True)
    tipo            = sa.Column(sa.Enum(TipoClienteEnum), nullable=False, default=TipoClienteEnum.EMPRESA)
    segmento        = sa.Column(sa.Enum(SegmentoClienteEnum), nullable=True)
    estado          = sa.Column(sa.Enum(EstadoClienteEnum), nullable=False, default=EstadoClienteEnum.PROSPECTO)
    industria       = sa.Column(sa.String(80), nullable=True)
    pais            = sa.Column(sa.String(60), default="Colombia")
    ciudad          = sa.Column(sa.String(80), nullable=True)
    direccion       = sa.Column(sa.String(200), nullable=True)
    telefono        = sa.Column(sa.String(40), nullable=True)
    email           = sa.Column(sa.String(120), nullable=True)
    sitio_web       = sa.Column(sa.String(200), nullable=True)
    ejecutivo_id    = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    potencial_anual = sa.Column(sa.Numeric(18, 2), nullable=True)
    ingresos_ytd    = sa.Column(sa.Numeric(18, 2), default=0)
    health_score    = sa.Column(sa.Integer, default=50)
    lead_score      = sa.Column(sa.Integer, default=0)
    notas           = sa.Column(sa.Text, nullable=True)
    activo          = sa.Column(sa.Boolean, default=True)


class CRMContacto(Base, TimestampMixin):
    __tablename__ = "crm_contacto"
    id           = sa.Column(sa.Integer, primary_key=True, index=True)
    cliente_id   = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    nombre       = sa.Column(sa.String(120), nullable=False)
    cargo        = sa.Column(sa.String(80), nullable=True)
    email        = sa.Column(sa.String(120), nullable=True)
    telefono     = sa.Column(sa.String(40), nullable=True)
    whatsapp     = sa.Column(sa.String(40), nullable=True)
    linkedin     = sa.Column(sa.String(200), nullable=True)
    es_decisor   = sa.Column(sa.Boolean, default=False)
    es_principal = sa.Column(sa.Boolean, default=False)
    activo       = sa.Column(sa.Boolean, default=True)


class CRMLead(Base, TimestampMixin):
    __tablename__ = "crm_lead"
    id           = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo       = sa.Column(sa.String(20), unique=True, nullable=False)
    cliente_id   = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=True)
    ejecutivo_id = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    empresa      = sa.Column(sa.String(200), nullable=False)
    contacto     = sa.Column(sa.String(120), nullable=True)
    email        = sa.Column(sa.String(120), nullable=True)
    telefono     = sa.Column(sa.String(40), nullable=True)
    fuente       = sa.Column(sa.String(80), nullable=True)
    industria    = sa.Column(sa.String(80), nullable=True)
    estado       = sa.Column(sa.Enum(EstadoLeadEnum), nullable=False, default=EstadoLeadEnum.FRIO)
    score        = sa.Column(sa.Integer, default=0)
    potencial    = sa.Column(sa.Numeric(18, 2), nullable=True)
    notas        = sa.Column(sa.Text, nullable=True)
    convertido   = sa.Column(sa.Boolean, default=False)


class CRMOportunidad(Base, TimestampMixin):
    __tablename__ = "crm_oportunidad"
    id               = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo           = sa.Column(sa.String(20), unique=True, nullable=False)
    cliente_id       = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    lead_id          = sa.Column(sa.Integer, sa.ForeignKey("crm_lead.id"), nullable=True)
    ejecutivo_id     = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    nombre           = sa.Column(sa.String(200), nullable=False)
    descripcion      = sa.Column(sa.Text, nullable=True)
    estado           = sa.Column(sa.Enum(EstadoOportunidadEnum), nullable=False, default=EstadoOportunidadEnum.IDENTIFICACION)
    probabilidad     = sa.Column(sa.Integer, default=10)
    valor_estimado   = sa.Column(sa.Numeric(18, 2), nullable=True)
    valor_contratado = sa.Column(sa.Numeric(18, 2), nullable=True)
    servicio         = sa.Column(sa.String(100), nullable=True)
    fecha_esperada   = sa.Column(sa.Date, nullable=True)
    fecha_cierre     = sa.Column(sa.Date, nullable=True)
    motivo_perdida   = sa.Column(sa.String(200), nullable=True)


class CRMCotizacion(Base, TimestampMixin):
    __tablename__ = "crm_cotizacion"
    id              = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo          = sa.Column(sa.String(20), unique=True, nullable=False)
    version         = sa.Column(sa.Integer, default=1)
    oportunidad_id  = sa.Column(sa.Integer, sa.ForeignKey("crm_oportunidad.id"), nullable=True)
    cliente_id      = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    ejecutivo_id    = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    estado          = sa.Column(sa.Enum(EstadoCotizacionEnum), nullable=False, default=EstadoCotizacionEnum.BORRADOR)
    subtotal        = sa.Column(sa.Numeric(18, 2), default=0)
    iva             = sa.Column(sa.Numeric(18, 2), default=0)
    total           = sa.Column(sa.Numeric(18, 2), default=0)
    validez_dias    = sa.Column(sa.Integer, default=30)
    fecha_envio     = sa.Column(sa.Date, nullable=True)
    fecha_vencimiento = sa.Column(sa.Date, nullable=True)
    notas           = sa.Column(sa.Text, nullable=True)


class CRMCotizacionItem(Base, TimestampMixin):
    __tablename__ = "crm_cotizacion_item"
    id              = sa.Column(sa.Integer, primary_key=True, index=True)
    cotizacion_id   = sa.Column(sa.Integer, sa.ForeignKey("crm_cotizacion.id"), nullable=False)
    descripcion     = sa.Column(sa.String(300), nullable=False)
    unidad          = sa.Column(sa.String(30), nullable=True)
    cantidad        = sa.Column(sa.Numeric(14, 4), default=1)
    precio_unitario = sa.Column(sa.Numeric(18, 2), default=0)
    descuento_pct   = sa.Column(sa.Numeric(6, 2), default=0)
    total           = sa.Column(sa.Numeric(18, 2), default=0)


class CRMContrato(Base, TimestampMixin):
    __tablename__ = "crm_contrato"
    id              = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo          = sa.Column(sa.String(20), unique=True, nullable=False)
    cliente_id      = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    oportunidad_id  = sa.Column(sa.Integer, sa.ForeignKey("crm_oportunidad.id"), nullable=True)
    ejecutivo_id    = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    nombre          = sa.Column(sa.String(200), nullable=False)
    estado          = sa.Column(sa.Enum(EstadoContratoEnum), nullable=False, default=EstadoContratoEnum.BORRADOR)
    tipo_servicio   = sa.Column(sa.String(100), nullable=True)
    valor_mensual   = sa.Column(sa.Numeric(18, 2), nullable=True)
    valor_total     = sa.Column(sa.Numeric(18, 2), nullable=True)
    fecha_inicio    = sa.Column(sa.Date, nullable=True)
    fecha_fin       = sa.Column(sa.Date, nullable=True)
    duracion_meses  = sa.Column(sa.Integer, nullable=True)
    auto_renovacion = sa.Column(sa.Boolean, default=False)
    dms_documento_id= sa.Column(sa.Integer, nullable=True)
    notas           = sa.Column(sa.Text, nullable=True)


class CRMContratoSLA(Base, TimestampMixin):
    __tablename__ = "crm_contrato_sla"
    id                  = sa.Column(sa.Integer, primary_key=True, index=True)
    contrato_id         = sa.Column(sa.Integer, sa.ForeignKey("crm_contrato.id"), nullable=False)
    indicador           = sa.Column(sa.String(100), nullable=False)
    objetivo            = sa.Column(sa.Numeric(8, 2), nullable=False)
    unidad              = sa.Column(sa.String(30), nullable=True)
    valor_actual        = sa.Column(sa.Numeric(8, 2), nullable=True)
    penalizacion        = sa.Column(sa.String(200), nullable=True)
    frecuencia_medicion = sa.Column(sa.String(40), nullable=True)
    activo              = sa.Column(sa.Boolean, default=True)


class CRMTicket(Base, TimestampMixin):
    __tablename__ = "crm_ticket"
    id                   = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo               = sa.Column(sa.String(20), unique=True, nullable=False)
    cliente_id           = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    contrato_id          = sa.Column(sa.Integer, sa.ForeignKey("crm_contrato.id"), nullable=True)
    contacto_id          = sa.Column(sa.Integer, sa.ForeignKey("crm_contacto.id"), nullable=True)
    ejecutivo_id         = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    tipo                 = sa.Column(sa.Enum(TipoTicketEnum), nullable=False, default=TipoTicketEnum.SOLICITUD)
    estado               = sa.Column(sa.Enum(EstadoTicketEnum), nullable=False, default=EstadoTicketEnum.ABIERTO)
    prioridad            = sa.Column(sa.String(20), default="MEDIA")
    asunto               = sa.Column(sa.String(300), nullable=False)
    descripcion          = sa.Column(sa.Text, nullable=True)
    canal                = sa.Column(sa.String(40), nullable=True)
    fecha_limite         = sa.Column(sa.DateTime(timezone=True), nullable=True)
    fecha_resolucion     = sa.Column(sa.DateTime(timezone=True), nullable=True)
    tiempo_respuesta_hrs = sa.Column(sa.Numeric(8, 2), nullable=True)
    tiempo_solucion_hrs  = sa.Column(sa.Numeric(8, 2), nullable=True)
    qms_nc_id            = sa.Column(sa.Integer, nullable=True)
    satisfaccion         = sa.Column(sa.Integer, nullable=True)


class CRMInteraccion(Base, TimestampMixin):
    __tablename__ = "crm_interaccion"
    id                = sa.Column(sa.Integer, primary_key=True, index=True)
    cliente_id        = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    contacto_id       = sa.Column(sa.Integer, sa.ForeignKey("crm_contacto.id"), nullable=True)
    ticket_id         = sa.Column(sa.Integer, sa.ForeignKey("crm_ticket.id"), nullable=True)
    oportunidad_id    = sa.Column(sa.Integer, sa.ForeignKey("crm_oportunidad.id"), nullable=True)
    ejecutivo_id      = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    tipo              = sa.Column(sa.Enum(TipoInteraccionEnum), nullable=False)
    asunto            = sa.Column(sa.String(300), nullable=True)
    descripcion       = sa.Column(sa.Text, nullable=True)
    duracion_min      = sa.Column(sa.Integer, nullable=True)
    resultado         = sa.Column(sa.String(200), nullable=True)
    proximo_paso      = sa.Column(sa.String(200), nullable=True)
    fecha_interaccion = sa.Column(sa.DateTime(timezone=True), nullable=True)


class CRMCampana(Base, TimestampMixin):
    __tablename__ = "crm_campana"
    id                 = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo             = sa.Column(sa.String(20), unique=True, nullable=False)
    nombre             = sa.Column(sa.String(200), nullable=False)
    tipo               = sa.Column(sa.Enum(TipoCampanaEnum), nullable=False)
    descripcion        = sa.Column(sa.Text, nullable=True)
    fecha_inicio       = sa.Column(sa.Date, nullable=True)
    fecha_fin          = sa.Column(sa.Date, nullable=True)
    presupuesto        = sa.Column(sa.Numeric(18, 2), nullable=True)
    leads_generados    = sa.Column(sa.Integer, default=0)
    conversiones       = sa.Column(sa.Integer, default=0)
    ingresos_generados = sa.Column(sa.Numeric(18, 2), default=0)
    activa             = sa.Column(sa.Boolean, default=True)


class CRMCampanaCliente(Base, TimestampMixin):
    __tablename__ = "crm_campana_cliente"
    id          = sa.Column(sa.Integer, primary_key=True, index=True)
    campana_id  = sa.Column(sa.Integer, sa.ForeignKey("crm_campana.id"), nullable=False)
    cliente_id  = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    enviado     = sa.Column(sa.Boolean, default=False)
    abierto     = sa.Column(sa.Boolean, default=False)
    respondido  = sa.Column(sa.Boolean, default=False)
    convertido  = sa.Column(sa.Boolean, default=False)


class CRMEncuesta(Base, TimestampMixin):
    __tablename__ = "crm_encuesta"
    id              = sa.Column(sa.Integer, primary_key=True, index=True)
    codigo          = sa.Column(sa.String(20), unique=True, nullable=False)
    cliente_id      = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    ticket_id       = sa.Column(sa.Integer, sa.ForeignKey("crm_ticket.id"), nullable=True)
    tipo            = sa.Column(sa.Enum(TipoEncuestaEnum), nullable=False)
    puntaje         = sa.Column(sa.Integer, nullable=True)
    comentario      = sa.Column(sa.Text, nullable=True)
    respondida      = sa.Column(sa.Boolean, default=False)
    fecha_envio     = sa.Column(sa.Date, nullable=True)
    fecha_respuesta = sa.Column(sa.Date, nullable=True)


class CRMCuentaClave(Base, TimestampMixin):
    __tablename__ = "crm_cuenta_clave"
    id              = sa.Column(sa.Integer, primary_key=True, index=True)
    cliente_id      = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False, unique=True)
    ejecutivo_id    = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    objetivo_anual  = sa.Column(sa.Numeric(18, 2), nullable=True)
    ingreso_actual  = sa.Column(sa.Numeric(18, 2), nullable=True)
    estrategia      = sa.Column(sa.Text, nullable=True)
    proxima_reunion = sa.Column(sa.Date, nullable=True)
    nivel_riesgo    = sa.Column(sa.Enum(NivelRiesgoClienteEnum), default=NivelRiesgoClienteEnum.BAJO)


class CRMObjetivoComercial(Base, TimestampMixin):
    __tablename__ = "crm_objetivo_comercial"
    id            = sa.Column(sa.Integer, primary_key=True, index=True)
    ejecutivo_id  = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=False)
    periodo       = sa.Column(sa.String(20), nullable=False)
    tipo_objetivo = sa.Column(sa.String(60), nullable=False)
    meta          = sa.Column(sa.Numeric(18, 2), nullable=False)
    logrado       = sa.Column(sa.Numeric(18, 2), default=0)
    porcentaje    = sa.Column(sa.Numeric(6, 2), default=0)


class CRMActividad(Base, TimestampMixin):
    __tablename__ = "crm_actividad"
    id                = sa.Column(sa.Integer, primary_key=True, index=True)
    cliente_id        = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=True)
    oportunidad_id    = sa.Column(sa.Integer, sa.ForeignKey("crm_oportunidad.id"), nullable=True)
    ticket_id         = sa.Column(sa.Integer, sa.ForeignKey("crm_ticket.id"), nullable=True)
    ejecutivo_id      = sa.Column(sa.Integer, sa.ForeignKey("crm_ejecutivo_comercial.id"), nullable=True)
    tipo              = sa.Column(sa.String(50), nullable=False)
    asunto            = sa.Column(sa.String(200), nullable=False)
    descripcion       = sa.Column(sa.Text, nullable=True)
    fecha_vencimiento = sa.Column(sa.DateTime(timezone=True), nullable=True)
    completada        = sa.Column(sa.Boolean, default=False)
    prioridad         = sa.Column(sa.String(20), default="MEDIA")


class CRMRiesgoCliente(Base, TimestampMixin):
    __tablename__ = "crm_riesgo_cliente"
    id               = sa.Column(sa.Integer, primary_key=True, index=True)
    cliente_id       = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    tipo_riesgo      = sa.Column(sa.String(80), nullable=False)
    nivel            = sa.Column(sa.Enum(NivelRiesgoClienteEnum), nullable=False, default=NivelRiesgoClienteEnum.BAJO)
    descripcion      = sa.Column(sa.Text, nullable=True)
    plan_mitigacion  = sa.Column(sa.Text, nullable=True)
    activo           = sa.Column(sa.Boolean, default=True)


class CRMSaludCliente(Base, TimestampMixin):
    __tablename__ = "crm_salud_cliente"
    id              = sa.Column(sa.Integer, primary_key=True, index=True)
    cliente_id      = sa.Column(sa.Integer, sa.ForeignKey("crm_cliente.id"), nullable=False)
    fecha_calculo   = sa.Column(sa.Date, nullable=False)
    health_score    = sa.Column(sa.Integer, default=0)
    score_otif      = sa.Column(sa.Integer, nullable=True)
    score_tickets   = sa.Column(sa.Integer, nullable=True)
    score_pagos     = sa.Column(sa.Integer, nullable=True)
    score_nps       = sa.Column(sa.Integer, nullable=True)
    score_contratos = sa.Column(sa.Integer, nullable=True)
    riesgo_churn    = sa.Column(sa.Numeric(6, 2), nullable=True)
    prediccion_ia   = sa.Column(sa.Text, nullable=True)


class CRMKPIDiario(Base, TimestampMixin):
    __tablename__ = "crm_kpi_diario"
    id                    = sa.Column(sa.Integer, primary_key=True, index=True)
    fecha                 = sa.Column(sa.Date, nullable=False)
    total_clientes        = sa.Column(sa.Integer, default=0)
    clientes_activos      = sa.Column(sa.Integer, default=0)
    total_leads           = sa.Column(sa.Integer, default=0)
    leads_calientes       = sa.Column(sa.Integer, default=0)
    pipeline_valor        = sa.Column(sa.Numeric(18, 2), default=0)
    oportunidades_activas = sa.Column(sa.Integer, default=0)
    tasa_conversion       = sa.Column(sa.Numeric(6, 2), default=0)
    win_rate              = sa.Column(sa.Numeric(6, 2), default=0)
    tickets_abiertos      = sa.Column(sa.Integer, default=0)
    tickets_escalados     = sa.Column(sa.Integer, default=0)
    nps_promedio          = sa.Column(sa.Numeric(6, 2), default=0)
    csat_promedio         = sa.Column(sa.Numeric(6, 2), default=0)
    contratos_activos     = sa.Column(sa.Integer, default=0)
    contratos_por_vencer  = sa.Column(sa.Integer, default=0)
    ingresos_mes          = sa.Column(sa.Numeric(18, 2), default=0)
    churn_rate            = sa.Column(sa.Numeric(6, 2), default=0)


class CRMParametro(Base, TimestampMixin):
    """Los umbrales con los que el módulo decide qué alertar y qué recomendar.

    POR QUÉ EN UNA TABLA Y NO EN EL CÓDIGO
    Porque no son verdades: son decisiones de cada empresa. Avisar de una
    renovación a cuarenta y cinco días le sirve a quien negocia con comités
    trimestrales y le sobra a quien renueva por correo. Con el umbral escrito en
    el código, cambiarlo exige un despliegue, y lo que pasa en la práctica es que
    nadie lo cambia y la gente aprende a ignorar las alertas.

    Un valor por clave, y el valor va como número. No hace falta más: todo lo que
    se configura aquí es un umbral.
    """
    __tablename__ = "crm_parametro"
    id          = sa.Column(sa.Integer, primary_key=True, index=True)
    clave       = sa.Column(sa.String(60), unique=True, nullable=False, index=True)
    valor       = sa.Column(sa.Numeric(12, 2), nullable=False)
    modificado_por = sa.Column(sa.String(80), nullable=True)
