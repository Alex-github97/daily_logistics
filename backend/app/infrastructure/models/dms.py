"""
Módulo DMS (Document Management System) — Modelos de base de datos
Prefijo de tabla: dms_
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, Numeric,
    BigInteger, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin


# ─── Enums ─────────────────────────────────────────────────────────────────────

class EstadoDocumentoDMSEnum(str, enum.Enum):
    BORRADOR    = "BORRADOR"
    EN_REVISION = "EN_REVISION"
    APROBADO    = "APROBADO"
    PUBLICADO   = "PUBLICADO"
    OBSOLETO    = "OBSOLETO"
    ARCHIVADO   = "ARCHIVADO"


class TipoFirmaDMSEnum(str, enum.Enum):
    ELECTRONICA = "ELECTRONICA"
    DIGITAL     = "DIGITAL"
    APROBACION  = "APROBACION"


class EstadoFirmaDMSEnum(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    FIRMADO   = "FIRMADO"
    RECHAZADO = "RECHAZADO"


class EstadoInstanciaDMSEnum(str, enum.Enum):
    EN_CURSO   = "EN_CURSO"
    COMPLETADO = "COMPLETADO"
    RECHAZADO  = "RECHAZADO"
    CANCELADO  = "CANCELADO"


class TipoExpedienteDMSEnum(str, enum.Enum):
    EMPLEADO  = "EMPLEADO"
    CONDUCTOR = "CONDUCTOR"
    VEHICULO  = "VEHICULO"
    CLIENTE   = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"
    PROYECTO  = "PROYECTO"


class AccionAuditoriaDMSEnum(str, enum.Enum):
    CREACION      = "CREACION"
    VISUALIZACION = "VISUALIZACION"
    DESCARGA      = "DESCARGA"
    MODIFICACION  = "MODIFICACION"
    ELIMINACION   = "ELIMINACION"
    FIRMA         = "FIRMA"
    APROBACION    = "APROBACION"
    RECHAZO       = "RECHAZO"
    IMPRESION     = "IMPRESION"
    VERSION_NUEVA = "VERSION_NUEVA"


# ─── Modelos ───────────────────────────────────────────────────────────────────

class DMSCarpeta(Base, TimestampMixin, SoftDeleteMixin):
    """Estructura de carpetas/directorios del DMS."""
    __tablename__ = "dms_carpeta"

    id            = Column(Integer, primary_key=True, index=True)
    nombre        = Column(String(200), nullable=False)
    descripcion   = Column(Text, nullable=True)
    padre_id      = Column(Integer, ForeignKey("dms_carpeta.id"), nullable=True)
    ruta          = Column(String(500), nullable=True)
    icono         = Column(String(50), nullable=True)
    color         = Column(String(7), nullable=True)
    es_publica    = Column(Boolean, default=False)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    padre       = relationship("DMSCarpeta", remote_side="DMSCarpeta.id", back_populates="subcarpetas")
    subcarpetas = relationship("DMSCarpeta", back_populates="padre")
    documentos  = relationship("DMSDocumento", back_populates="carpeta")
    creado_por  = relationship("Usuario", foreign_keys=[creado_por_id])


class DMSCategoria(Base, TimestampMixin):
    """Categorías de clasificación de documentos."""
    __tablename__ = "dms_categoria"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    codigo      = Column(String(50), nullable=True, unique=True)
    icono       = Column(String(50), nullable=True)
    color       = Column(String(7), nullable=True)
    activo      = Column(Boolean, default=True)

    tipos_documento = relationship("DMSTipoDocumento", back_populates="categoria")


class DMSTipoDocumento(Base, TimestampMixin):
    """Tipos de documentos con sus reglas de negocio."""
    __tablename__ = "dms_tipo_documento"

    id                       = Column(Integer, primary_key=True, index=True)
    nombre                   = Column(String(200), nullable=False)
    descripcion              = Column(Text, nullable=True)
    categoria_id             = Column(Integer, ForeignKey("dms_categoria.id"), nullable=False)
    codigo                   = Column(String(50), nullable=True)
    extensiones_permitidas   = Column(String(200), nullable=True)
    requiere_firma           = Column(Boolean, default=False)
    requiere_aprobacion      = Column(Boolean, default=False)
    dias_vigencia            = Column(Integer, nullable=True)
    activo                   = Column(Boolean, default=True)

    categoria       = relationship("DMSCategoria", back_populates="tipos_documento")
    campos_metadato = relationship("DMSCampoMetadato", back_populates="tipo_documento")
    documentos      = relationship("DMSDocumento", back_populates="tipo_documento")
    workflows       = relationship("DMSWorkflow", back_populates="tipo_documento")
    retenciones     = relationship("DMSRetencion", back_populates="tipo_documento")


class DMSCampoMetadato(Base, TimestampMixin):
    """Campos de metadatos configurables por tipo de documento."""
    __tablename__ = "dms_campo_metadato"

    id                 = Column(Integer, primary_key=True, index=True)
    tipo_documento_id  = Column(Integer, ForeignKey("dms_tipo_documento.id"), nullable=False)
    nombre             = Column(String(100), nullable=False)
    etiqueta           = Column(String(200), nullable=False)
    # texto / numero / fecha / booleano / lista
    tipo_dato          = Column(String(50), nullable=False, default="texto")
    opciones           = Column(Text, nullable=True)   # JSON serializado
    requerido          = Column(Boolean, default=False)
    orden              = Column(Integer, default=0)

    tipo_documento = relationship("DMSTipoDocumento", back_populates="campos_metadato")
    valores        = relationship("DMSMetadatoValor", back_populates="campo")


class DMSDocumento(Base, TimestampMixin, SoftDeleteMixin):
    """Documento principal del DMS."""
    __tablename__ = "dms_documento"

    id                     = Column(Integer, primary_key=True, index=True)
    codigo                 = Column(String(50), nullable=True, unique=True, index=True)
    nombre                 = Column(String(500), nullable=False)
    descripcion            = Column(Text, nullable=True)
    tipo_documento_id      = Column(Integer, ForeignKey("dms_tipo_documento.id"), nullable=True)
    carpeta_id             = Column(Integer, ForeignKey("dms_carpeta.id"), nullable=True)
    estado                 = Column(SAEnum(EstadoDocumentoDMSEnum), default=EstadoDocumentoDMSEnum.BORRADOR)
    version_actual         = Column(String(20), default="1.0")
    version_numero         = Column(Integer, default=1)
    tags                   = Column(String(500), nullable=True)
    es_confidencial        = Column(Boolean, default=False)
    permite_descarga       = Column(Boolean, default=True)
    permite_impresion      = Column(Boolean, default=True)
    fecha_vigencia_inicio  = Column(DateTime, nullable=True)
    fecha_vigencia_fin     = Column(DateTime, nullable=True)
    propietario_id         = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    # Referencias a módulos externos
    hcm_colaborador_id     = Column(Integer, nullable=True)
    hcm_conductor_id       = Column(Integer, nullable=True)
    tms_vehiculo_id        = Column(Integer, nullable=True)
    modulo_origen          = Column(String(50), nullable=True)
    referencia_externa_id  = Column(Integer, nullable=True)

    tipo_documento        = relationship("DMSTipoDocumento", back_populates="documentos")
    carpeta               = relationship("DMSCarpeta", back_populates="documentos")
    propietario           = relationship("Usuario", foreign_keys=[propietario_id])
    versiones             = relationship("DMSVersion", back_populates="documento")
    metadatos             = relationship("DMSMetadatoValor", back_populates="documento")
    firmas                = relationship("DMSFirma", back_populates="documento")
    instancias            = relationship("DMSInstancia", back_populates="documento")
    expediente_documentos = relationship("DMSExpedienteDocumento", back_populates="documento")
    auditorias            = relationship("DMSAuditoria", back_populates="documento")
    notificaciones        = relationship("DMSNotificacion", back_populates="documento")


class DMSVersion(Base, TimestampMixin):
    """Versiones de un documento con almacenamiento de archivo."""
    __tablename__ = "dms_version"

    id              = Column(Integer, primary_key=True, index=True)
    documento_id    = Column(Integer, ForeignKey("dms_documento.id"), nullable=False)
    numero_version  = Column(String(20), nullable=False)
    version_numero  = Column(Integer, nullable=False)
    es_mayor        = Column(Boolean, default=False)
    nombre_archivo  = Column(String(500), nullable=False)
    ruta_archivo    = Column(String(1000), nullable=True)
    url_archivo     = Column(String(1000), nullable=True)
    tamanio_bytes   = Column(BigInteger, nullable=True)
    tipo_mime       = Column(String(100), nullable=True)
    hash_md5        = Column(String(32), nullable=True)
    comentario      = Column(Text, nullable=True)
    ocr_texto       = Column(Text, nullable=True)
    creado_por_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    documento   = relationship("DMSDocumento", back_populates="versiones")
    creado_por  = relationship("Usuario", foreign_keys=[creado_por_id])
    firmas      = relationship("DMSFirma", back_populates="version")
    auditorias  = relationship("DMSAuditoria", back_populates="version")


class DMSMetadatoValor(Base, TimestampMixin):
    """Valores de metadatos por documento y campo."""
    __tablename__ = "dms_metadato_valor"

    id              = Column(Integer, primary_key=True, index=True)
    documento_id    = Column(Integer, ForeignKey("dms_documento.id"), nullable=False)
    campo_id        = Column(Integer, ForeignKey("dms_campo_metadato.id"), nullable=False)
    valor_texto     = Column(Text, nullable=True)
    valor_numero    = Column(Numeric(18, 4), nullable=True)
    valor_fecha     = Column(DateTime, nullable=True)
    valor_booleano  = Column(Boolean, nullable=True)

    documento = relationship("DMSDocumento", back_populates="metadatos")
    campo     = relationship("DMSCampoMetadato", back_populates="valores")


class DMSFirma(Base, TimestampMixin):
    """Registro de firmas electrónicas o digitales sobre documentos."""
    __tablename__ = "dms_firma"

    id            = Column(Integer, primary_key=True, index=True)
    documento_id  = Column(Integer, ForeignKey("dms_documento.id"), nullable=False)
    version_id    = Column(Integer, ForeignKey("dms_version.id"), nullable=True)
    firmante_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo_firma    = Column(SAEnum(TipoFirmaDMSEnum), nullable=False)
    estado        = Column(SAEnum(EstadoFirmaDMSEnum), default=EstadoFirmaDMSEnum.PENDIENTE)
    fecha_firma   = Column(DateTime, nullable=True)
    ip_firma      = Column(String(45), nullable=True)
    dispositivo   = Column(String(200), nullable=True)
    observaciones = Column(Text, nullable=True)
    orden         = Column(Integer, default=0)

    documento = relationship("DMSDocumento", back_populates="firmas")
    version   = relationship("DMSVersion", back_populates="firmas")
    firmante  = relationship("Usuario", foreign_keys=[firmante_id])


class DMSWorkflow(Base, TimestampMixin):
    """Definición de flujos de aprobación de documentos."""
    __tablename__ = "dms_workflow"

    id                 = Column(Integer, primary_key=True, index=True)
    nombre             = Column(String(200), nullable=False)
    descripcion        = Column(Text, nullable=True)
    tipo_documento_id  = Column(Integer, ForeignKey("dms_tipo_documento.id"), nullable=True)
    activo             = Column(Boolean, default=True)
    dias_limite        = Column(Integer, nullable=True)

    tipo_documento = relationship("DMSTipoDocumento", back_populates="workflows")
    pasos          = relationship("DMSWorkflowPaso", back_populates="workflow")
    instancias     = relationship("DMSInstancia", back_populates="workflow")


class DMSWorkflowPaso(Base, TimestampMixin):
    """Pasos individuales de un workflow de documentos."""
    __tablename__ = "dms_workflow_paso"

    id               = Column(Integer, primary_key=True, index=True)
    workflow_id      = Column(Integer, ForeignKey("dms_workflow.id"), nullable=False)
    nombre           = Column(String(200), nullable=False)
    # revision / aprobacion / firma / notificacion
    tipo             = Column(String(50), nullable=False)
    orden            = Column(Integer, default=0)
    responsable_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    responsable_rol  = Column(String(100), nullable=True)
    dias_limite      = Column(Integer, nullable=True)
    es_obligatorio   = Column(Boolean, default=True)

    workflow      = relationship("DMSWorkflow", back_populates="pasos")
    responsable   = relationship("Usuario", foreign_keys=[responsable_id])
    instancia_pasos = relationship("DMSInstanciaPaso", back_populates="paso")


class DMSInstancia(Base, TimestampMixin):
    """Instancia activa de un workflow sobre un documento concreto."""
    __tablename__ = "dms_instancia"

    id                  = Column(Integer, primary_key=True, index=True)
    workflow_id         = Column(Integer, ForeignKey("dms_workflow.id"), nullable=False)
    documento_id        = Column(Integer, ForeignKey("dms_documento.id"), nullable=False)
    estado              = Column(SAEnum(EstadoInstanciaDMSEnum), default=EstadoInstanciaDMSEnum.EN_CURSO)
    iniciado_por_id     = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    paso_actual         = Column(Integer, default=0)
    fecha_inicio        = Column(DateTime, default=datetime.utcnow)
    fecha_limite        = Column(DateTime, nullable=True)
    fecha_fin           = Column(DateTime, nullable=True)
    comentario_cierre   = Column(Text, nullable=True)

    workflow      = relationship("DMSWorkflow", back_populates="instancias")
    documento     = relationship("DMSDocumento", back_populates="instancias")
    iniciado_por  = relationship("Usuario", foreign_keys=[iniciado_por_id])
    pasos         = relationship("DMSInstanciaPaso", back_populates="instancia")


class DMSInstanciaPaso(Base, TimestampMixin):
    """Estado de cada paso dentro de una instancia de workflow."""
    __tablename__ = "dms_instancia_paso"

    id                  = Column(Integer, primary_key=True, index=True)
    instancia_id        = Column(Integer, ForeignKey("dms_instancia.id"), nullable=False)
    paso_id             = Column(Integer, ForeignKey("dms_workflow_paso.id"), nullable=False)
    estado              = Column(String(50), default="pendiente")
    asignado_a_id       = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_asignacion    = Column(DateTime, nullable=True)
    fecha_respuesta     = Column(DateTime, nullable=True)
    comentario          = Column(Text, nullable=True)
    accion              = Column(String(50), nullable=True)

    instancia   = relationship("DMSInstancia", back_populates="pasos")
    paso        = relationship("DMSWorkflowPaso", back_populates="instancia_pasos")
    asignado_a  = relationship("Usuario", foreign_keys=[asignado_a_id])


class DMSExpediente(Base, TimestampMixin, SoftDeleteMixin):
    """Expediente agrupador de documentos por entidad (empleado, vehículo, etc.)."""
    __tablename__ = "dms_expediente"

    id                  = Column(Integer, primary_key=True, index=True)
    codigo              = Column(String(50), nullable=True, unique=True, index=True)
    nombre              = Column(String(500), nullable=False)
    tipo                = Column(SAEnum(TipoExpedienteDMSEnum), nullable=False)
    estado              = Column(String(50), default="activo")
    descripcion         = Column(Text, nullable=True)
    # Referencias externas
    hcm_colaborador_id  = Column(Integer, nullable=True)
    hcm_conductor_id    = Column(Integer, nullable=True)
    tms_vehiculo_id     = Column(Integer, nullable=True)
    propietario_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    completitud_pct     = Column(Numeric(5, 2), default=0)

    propietario          = relationship("Usuario", foreign_keys=[propietario_id])
    expediente_documentos = relationship("DMSExpedienteDocumento", back_populates="expediente")


class DMSExpedienteDocumento(Base, TimestampMixin):
    """Asociación de documentos a expedientes con tipo requerido."""
    __tablename__ = "dms_expediente_documento"

    id               = Column(Integer, primary_key=True, index=True)
    expediente_id    = Column(Integer, ForeignKey("dms_expediente.id"), nullable=False)
    documento_id     = Column(Integer, ForeignKey("dms_documento.id"), nullable=False)
    tipo_requerido   = Column(String(200), nullable=True)
    es_obligatorio   = Column(Boolean, default=False)

    expediente = relationship("DMSExpediente", back_populates="expediente_documentos")
    documento  = relationship("DMSDocumento", back_populates="expediente_documentos")


class DMSRetencion(Base, TimestampMixin):
    """Política de retención documental por tipo de documento."""
    __tablename__ = "dms_retencion"

    id                       = Column(Integer, primary_key=True, index=True)
    nombre                   = Column(String(200), nullable=False)
    tipo_documento_id        = Column(Integer, ForeignKey("dms_tipo_documento.id"), nullable=True)
    dias_retencion_activo    = Column(Integer, nullable=False)
    dias_retencion_total     = Column(Integer, nullable=False)
    # archivar / eliminar / notificar
    accion_vencimiento       = Column(String(50), default="archivar")
    normativa                = Column(String(200), nullable=True)
    activo                   = Column(Boolean, default=True)

    tipo_documento = relationship("DMSTipoDocumento", back_populates="retenciones")


class DMSAuditoria(Base, TimestampMixin):
    """Registro de auditoría inmutable de todas las acciones sobre documentos."""
    __tablename__ = "dms_auditoria"

    id           = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    documento_id = Column(Integer, ForeignKey("dms_documento.id"), nullable=True)
    version_id   = Column(Integer, ForeignKey("dms_version.id"), nullable=True)
    usuario_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    accion       = Column(SAEnum(AccionAuditoriaDMSEnum), nullable=False)
    detalle      = Column(Text, nullable=True)
    ip_origen    = Column(String(45), nullable=True)
    user_agent   = Column(String(500), nullable=True)

    documento = relationship("DMSDocumento", back_populates="auditorias")
    version   = relationship("DMSVersion", back_populates="auditorias")
    usuario   = relationship("Usuario", foreign_keys=[usuario_id])


class DMSNotificacion(Base, TimestampMixin):
    """Notificaciones del DMS enviadas a usuarios."""
    __tablename__ = "dms_notificacion"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    documento_id = Column(Integer, ForeignKey("dms_documento.id"), nullable=True)
    tipo        = Column(String(100), nullable=False)
    titulo      = Column(String(200), nullable=False)
    mensaje     = Column(Text, nullable=False)
    leida       = Column(Boolean, default=False)
    accion_url  = Column(String(500), nullable=True)

    usuario   = relationship("Usuario", foreign_keys=[usuario_id])
    documento = relationship("DMSDocumento", back_populates="notificaciones")


class DMSKPIDiario(Base, TimestampMixin):
    """KPIs diarios agregados del módulo DMS."""
    __tablename__ = "dms_kpi_diario"

    id                      = Column(Integer, primary_key=True, index=True)
    fecha                   = Column(DateTime, nullable=False)
    total_documentos        = Column(Integer, default=0)
    documentos_creados      = Column(Integer, default=0)
    documentos_aprobados    = Column(Integer, default=0)
    documentos_vencidos     = Column(Integer, default=0)
    firmas_pendientes       = Column(Integer, default=0)
    firmas_completadas      = Column(Integer, default=0)
    workflows_activos       = Column(Integer, default=0)
    tamanio_total_mb        = Column(Numeric(18, 2), default=0)
