from app.infrastructure.models.base import TimestampMixin, SoftDeleteMixin
from app.infrastructure.models.rol import Rol, ROLES_DEFECTO, MODULOS_SISTEMA
from app.infrastructure.models.usuario import Usuario, RolUsuario
from app.infrastructure.models.ubicacion import Ubicacion, TipoUbicacion
from app.infrastructure.models.proveedor import Proveedor, Contrato, TipoProveedor, EstadoContrato
from app.infrastructure.models.estiba import Estiba, EstadoEstiba, TipoPropietario, TipoEstiba, NivelDano, EstibaStockMinimo
from app.infrastructure.models.vehiculo import Vehiculo, Transportadora, Conductor, TipoVehiculo
from app.infrastructure.models.manifiesto import Manifiesto, EstadoManifiesto, ManifiestoHistorial, TipoCambioEstado
from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento
from app.infrastructure.models.dano import CodigoDano, EventoDano, ResponsableDano, AccionRecomendada
from app.infrastructure.models.alerta import Alerta, TipoAlerta, NivelAlerta
from app.infrastructure.models.auditoria import RegistroAuditoria
from app.infrastructure.models.flete import (
    GeneradorCarga, VehiculoFlete, Flete, Enturnamiento,
    TipoVehiculoFlete, TipoCarroceria, EstadoFlete, EstadoEnturnamiento,
)
from app.infrastructure.models.flota import (
    FlotaMarca, FlotaTipoVehiculo, FlotaTipoCombustible, FlotaCentroCosto,
    FlotaProveedor, FlotaVehiculo, FlotaMedicion, FlotaDocumentoVehiculo,
    FlotaPersonal, FlotaDocumentoPersonal, FlotaRegistroCombustible,
    FlotaTipoTrabajo, FlotaOrdenTrabajo, FlotaOrdenTrabajoDetalle,
    FlotaRepuesto, FlotaRutinaMantenimiento, FlotaRutinaDetalleTrabajo,
    FlotaRutinaDetalleRepuesto, FlotaSecuenciaMantenimiento, FlotaSecuenciaRutina,
    FlotaGrupoVehiculo, FlotaAsignacionSecuencia, FlotaModoFalla, FlotaUmbralCBM,
)
from app.infrastructure.models.personal import (
    PerEstacion, PerPerfil, PerProgramacion, PerJornada, PerJornadaPausa, PerJornadaTramo,
)
from app.infrastructure.models.wms import (
    WMSAlmacen, WMSZona, WMSUbicacion, WMSProducto, WMSLote, WMSSerie,
    WMSProveedor, WMSCliente, WMSTransportadora,
    WMSOrdenCompra, WMSOrdenCompraDetalle, WMSRecepcion, WMSRecepcionDetalle,
    WMSInventarioUbicacion, WMSMovimientoInventario, WMSConteoInventario, WMSConteoDetalle,
    WMSOrdenSalida, WMSOrdenSalidaDetalle, WMSPickingTarea, WMSPickingDetalle,
    WMSDespacho, WMSDespachoDetalle, WMSHistorialEstado, WMSDevolucion, WMSDevolucionDetalle,
    WMSEventoTrazabilidad, WMSKPIDiario,
)
from app.infrastructure.models.locative import (
    LocativaSede, LocativaEspacio, LocativaCategoria, LocativaModoFalla,
    LocativaProveedor, LocativaActivo, LocativaActivoDocumento,
    LocativaCatalogoTarea, LocativaOrdenTrabajo, LocativaOTChecklist, LocativaOTMaterial,
    LocativaRegistroFalla, LocativaRiesgo, LocativaRiesgoTratamiento,
    LocativaMedidor, LocativaLecturaEnergia,
)
from app.infrastructure.models.hcm import (
    HCMEmpresa, HCMSede, HCMArea, HCMCargo, HCMCentroCosto,
    HCMColaborador, HCMColaboradorHistorial, HCMContrato,
    HCMConductor, HCMConductorVehiculoTipo, HCMConductorCobertura,
    HCMConductorDocumento, HCMConductorAccidente,
    HCMNominaPeriodo, HCMNominaDetalle, HCMNovedad, HCMLiquidacion,
    HCMIncapacidad, HCMVacacion,
    HCMVacante, HCMPostulacion, HCMEntrevista,
    HCMEvaluacion, HCMEvaluacionDetalle,
    HCMCapacitacion, HCMColaboradorCapacitacion,
    HCMSSTIncidente, HCMSSTRiesgo, HCMSSTInspeccion,
    HCMKPIDiario,
)
from app.infrastructure.models.tms import (
    TMSZona, TMSTipoServicio, TMSVehiculo, TMSViaje, TMSParada,
    TMSEvento, TMSDocumento, TMSPOD, TMSRuta, TMSPuntoRuta,
    TMSCostoViaje, TMSLiquidacion, TMSOTIFRegistro, TMSAlerta, TMSKPIDiario,
)
from app.infrastructure.models.dms import (
    DMSCarpeta, DMSCategoria, DMSTipoDocumento, DMSCampoMetadato,
    DMSDocumento, DMSVersion, DMSMetadatoValor, DMSFirma,
    DMSWorkflow, DMSWorkflowPaso, DMSInstancia, DMSInstanciaPaso,
    DMSExpediente, DMSExpedienteDocumento, DMSRetencion,
    DMSAuditoria, DMSNotificacion, DMSKPIDiario,
)
from app.infrastructure.models.qms import (
    QMSProceso, QMSProcedimiento, QMSIndicador, QMSMetaIndicador,
    QMSMedicionIndicador, QMSNoConformidad, QMSHallazgo, QMSAuditoria,
    QMSAuditoriaHallazgo, QMSCAPA, QMSCAPATarea, QMSRiesgo,
    QMSQueja, QMSEvaluacionProveedor, QMSCambio, QMSMejora,
    QMSEncuesta, QMSEncuestaRespuesta, QMSCompetenciaProceso, QMSKPIDiario,
)
from app.infrastructure.models.grc import (
    GRCComite, GRCPolitica, GRCObligacion, GRCControl, GRCRiesgo,
    GRCRiesgoControl, GRCTratamiento, GRCMatrizCumplimiento, GRCEvidencia,
    GRCAuditoria, GRCHallazgo, GRCPlanAccion, GRCIncidente,
    GRCContinuidad, GRCSimulacro, GRCTercero, GRCEvaluacionTercero,
    GRCComiteMiembro, GRCComiteSesion, GRCPoliticaAceptacion, GRCPruebaControl,
    GRCKri, GRCKriMedicion, GRCVinculo, GRCHistorial, GRCEscala, GRCBandaRiesgo, GRCParametro,
)
from app.infrastructure.models.lms import (
    LMSFacultad, LMSEscuela, LMSPrograma, LMSInstructor,
    LMSCurso, LMSModulo, LMSContenido,
    LMSCompetencia, LMSCursoCompetencia, LMSMatrizCompetencia,
    LMSRutaAprendizaje, LMSRutaCurso, LMSProgramaCurso,
    LMSInscripcion, LMSProgreso,
    LMSEvaluacion, LMSPregunta, LMSOpcionRespuesta,
    LMSEvaluacionPregunta, LMSIntentoEvaluacion, LMSRespuesta,
    LMSCertificacion, LMSCertificadoUsuario,
    LMSInsignia, LMSInsigniaUsuario,
    LMSForo, LMSHiloForo, LMSComentario,
    LMSKPIDiario,
)
from app.infrastructure.models.crm import (
    CRMEjecutivoComercial, CRMCliente, CRMContacto, CRMLead,
    CRMOportunidad, CRMCotizacion, CRMCotizacionItem, CRMContrato,
    CRMContratoSLA, CRMTicket, CRMInteraccion, CRMCampana, CRMCampanaCliente,
    CRMEncuesta, CRMCuentaClave, CRMObjetivoComercial, CRMActividad,
    CRMRiesgoCliente, CRMSaludCliente, CRMKPIDiario,
)
from app.infrastructure.models.eam import (
    EAMTipoTrabajo, EAMActividad, EAMRepuesto, EAMFallaCatalogo,
    EAMCausaCatalogo, EAMSolucionCatalogo, EAMContratista,
    EAMActivo, EAMComponente, EAMDocumentoActivo,
    EAMChecklistPlantilla, EAMChecklistPregunta,
    EAMPlanMantenimiento, EAMPlanDetalle,
    EAMOrdenTrabajo, EAMChecklistEjecucion, EAMChecklistRespuesta,
    EAMOTMaterial, EAMOTManoObra,
    EAMMuestraAceite, EAMNeumatico, EAMMovimientoNeumatico,
    EAMRegistroCombustible, EAMMetaRendimiento, EAMGarantia, EAMFMEA,
    EAMCalibracion, EAMKPIDiario,
)
# Inventario del CMMS: bodegas con jerarquia geografica, existencias por bodega
# y kardex. `eam_repuesto.stock_actual` pasa a ser un espejo de la suma.
from app.infrastructure.models.inventario import (
    InvBodega, InvExistencia, InvMotivo, InvMovimiento,
)
# Checklists: reemplaza a las tablas `eam_checklist_*` de arriba, que eran un
# esqueleto sin forma de responder nada y quedaron vacías en todos los esquemas.
from app.infrastructure.models.checklist import (
    ChkClasificacion, ChkOpcion, ChkSistema, ChkPregunta,
    ChkCategoria, ChkHallazgo,
    ChkPlantilla, ChkPlantillaTipo, ChkPlantillaPregunta,
    ChkEjecucion, ChkRespuesta, ChkFoto, ChkProgramacion,
)
# Lubricación: vive en su propio archivo porque `eam.py` ya pasa de 1.300
# líneas, pero cuelga del mismo CMMS (activos, componentes y órdenes).
from app.infrastructure.models.lubricacion import (
    LubeMarca, LubeTipoCompartimento, LubeProducto, LubeAplicacion,
    LubeParametro, LubeLimite, LubeLaboratorio, LubeMetodoMuestreo,
    LubeMotivoDrenaje, LubeModoFalla,
    LubeCompartimento, LubeCarga, LubeRelleno,
    LubeMuestra, LubeResultado, LubeDiagnostico,
)
from app.infrastructure.models.mes import (
    MESPlanta, MESLinea, MESTurno, MESCeldaTrabajo, MESEquipo,
    MESOperario, MESCertificacion, MESProducto, MESBOM, MESBOMDetalle,
    MESReceta, MESRecetaDetalle, MESOperacion, MESOrdenProduccion,
    MESOrdenOperacion, MESLote, MESEjecucion, MESParada,
    MESConsumoMaterial, MESWIP, MESInspeccion, MESDefecto,
    MESScrap, MESOEERegistro, MESChecklistPlantilla, MESChecklistPregunta,
    MESChecklistEjecucion, MESKPIDiario,
    MESFlujoNodo, MESFlujoConexion,
)
from app.infrastructure.models.aps import (
    APSUbicacion, APSProducto, APSRecurso, APSRestriccion, APSParametro,
    APSPronostico, APSDetallePeriodo, APSColaboracion, APSEscenario,
    APSPlanMaestro, APSPlanDetalle, APSMRP, APSCapacidad, APSCargaCapacidad,
    APSInventarioOptimo, APSOrdenSugerida, APSSimulacion, APSResultadoSimulacion,
    APSAlerta, APSSOIPCiclo, APSSOIPRevision, APSDistribucion, APSTransporte,
    APSAuditoria, APSConsenso, APSKPIDiario,
)
from app.infrastructure.models.scm import (
    ScmSolicitudCompra, ScmSolicitudItem, ScmOrdenCompra, ScmOrdenItem, ScmEvaluacionProveedor,
    EstadoSolicitudSCM, PrioridadSCM, EstadoOrdenSCM, CategoriaSCM, ClasificacionProveedor,
)
from app.infrastructure.models.sst import (
    SstIncidente, SstRiesgo, SstInspeccion, SstEntregaEPP, SstCapacitacion, SstDocumento,
    TipoIncidenteSST, GravedadSST, EstadoIncidenteSST, ClasePeligroSST, NivelRiesgoSST,
    EstadoInspeccionSST, TipoEPP, EstadoCapacitacionSST, TipoDocumentoSST,
)
from app.infrastructure.models.catalogo import (
    CatalogoMaestro, CATALOGOS_REGISTRO, MODULO_GLOBAL,
    catalogos_de, buscar_registro, MODULOS_CON_CATALOGO,
)
# Registro de clientes y mesa de ayuda: viven en el esquema de la plataforma.
from app.infrastructure.models.plataforma import (  # noqa: F401
    PlataformaCliente, PlataformaBitacora, PlataformaMiembro, PlataformaLanding,
)
from app.infrastructure.models.soporte import (  # noqa: F401
    SoporteTicket, SoporteMensaje, SoporteAdjunto,
    SoporteEpica, SoporteSprint, SoporteEvento, SoporteColumna,
)
from app.infrastructure.models.gestion import (  # noqa: F401
    GPWorkflow, GPEstado, GPTransicion,
    GPProyecto, GPProyectoMiembro, GPTipoIncidencia, GPPrioridad,
    GPCampo, GPCampoOpcion, GPEsquemaCampo,
    GPIncidencia, GPSprint, GPComentario, GPAdjunto, GPVinculo, GPHistorial,
    GPFiltro, GPPizarra, GPWidget,
    GPVersion, GPComponente, GPTipoVinculo,
)
# El nucleo contable: terceros, periodos, reglas y trazabilidad. Va aparte
# de `erp` porque ese archivo ya cubre los documentos, pero es el mismo modulo.
from app.infrastructure.models.erp_nucleo import (  # noqa: F401
    ERPTercero, ERPPeriodo, ERPReglaContable, ERPReglaImpuesto,
    ERPParametroFiscal, ERPEventoContable, ERPConsecutivo,
)
from app.infrastructure.models.erp_gestion import (  # noqa: F401
    ERPEscenario, ERPInductor, ERPDistribucionABC,
)
from app.infrastructure.models.erp_facturacion import (  # noqa: F401
    ERPResolucionFacturacion, ERPNotaCreditoCliente, ERPLineaNotaCredito,
)
from app.infrastructure.models.pos import (  # noqa: F401
    POSListaPrecio, POSPrecio, POSCaja, POSTurno, POSMovimientoCaja, POSVenta,
    POSVentaLinea, POSPago, POSDevolucion,
)
from app.infrastructure.models.ags import (
    AGSConfig, AGSCategoriaServicio, AGSServicio,
    AGSProfesional, AGSProfesionalServicio, AGSHorarioProfesional, AGSAusencia,
    AGSCliente, AGSCita, AGSCitaServicio, AGSCitaMaterial, AGSPagoCita,
    EstadoCitaEnum, LugarServicioEnum, OrigenCitaEnum, MedioPagoEnum, TipoPagoEnum,
)

__all__ = [
    "TimestampMixin", "SoftDeleteMixin",
    "Rol", "ROLES_DEFECTO", "MODULOS_SISTEMA",
    "Usuario", "RolUsuario",
    "Ubicacion", "TipoUbicacion",
    "Proveedor", "Contrato", "TipoProveedor", "EstadoContrato",
    "Estiba", "EstadoEstiba", "TipoPropietario", "TipoEstiba", "NivelDano",
    "Vehiculo", "Transportadora", "Conductor", "TipoVehiculo",
    "Manifiesto", "EstadoManifiesto", "ManifiestoHistorial", "TipoCambioEstado",
    "Movimiento", "TipoMovimiento",
    "CodigoDano", "EventoDano", "ResponsableDano", "AccionRecomendada",
    "Alerta", "TipoAlerta", "NivelAlerta",
    "RegistroAuditoria",
    "GeneradorCarga", "VehiculoFlete", "Flete", "Enturnamiento",
    "TipoVehiculoFlete", "TipoCarroceria", "EstadoFlete", "EstadoEnturnamiento",
]

# Daily Logistics: canales de venta en línea (marketplaces y tiendas).
from app.infrastructure.models import marketplace  # noqa: E402,F401
